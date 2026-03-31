from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import yt_dlp
import logging
import os

# إعداد السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Video Downloader API",
    description="API لتحميل الفيديوهات",
    version="1.0.0"
)

# إعداد CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# إعدادات yt-dlp الأساسية
YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'ignoreerrors': True,
}

@app.get("/")
def root():
    return {
        "message": "Server is running!",
        "endpoints": ["/health", "/info", "/download"]
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/info")
def get_video_info(url: str = Query(..., description="رابط الفيديو")):
    try:
        logger.info(f"جلب معلومات: {url}")
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise HTTPException(status_code=404, detail="لم يتم العثور على الفيديو")
            
            return {
                "title": info.get("title", "بدون عنوان"),
                "duration": info.get("duration", 0),
                "thumbnail": info.get("thumbnail", ""),
                "uploader": info.get("uploader", "غير معروف"),
            }
    except Exception as e:
        logger.error(f"خطأ: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/download")
def get_download_url(
    url: str = Query(..., description="رابط الفيديو"),
    quality: Optional[str] = Query("best", description="جودة الفيديو")
):
    try:
        logger.info(f"جلب رابط التحميل: {url}")
        opts = {**YDL_OPTS, 'format': quality}
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise HTTPException(status_code=404, detail="الفيديو غير متاح")

            download_url = info.get('url')
            
            if not download_url and 'formats' in info:
                valid_formats = [f for f in info['formats'] if f.get('vcodec') != 'none']
                if valid_formats:
                    download_url = valid_formats[-1].get('url')

            if not download_url:
                raise HTTPException(status_code=404, detail="تعذر استخراج رابط التحميل")

            return {
                "success": True,
                "title": info.get("title", "video"),
                "download_url": download_url,
                "duration": info.get("duration", 0)
            }
    except Exception as e:
        logger.error(f"خطأ: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

# نقطة اختبار بسيطة
@app.get("/test")
def test_url(url: str = Query(..., description="رابط للاختبار")):
    try:
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "status": "success",
                "title": info.get("title", "بدون عنوان")[:100],
                "message": "✓ الرابط صالح"
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"✗ خطأ: {str(e)[:100]}"
        }

# مهم جداً: هذا الجزء لتشغيل السيرفر
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"بدء السيرفر على البورت {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
