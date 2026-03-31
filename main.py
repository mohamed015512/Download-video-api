
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import yt_dlp
import logging
import os

# إعداد السجلات (Logs) لمتابعة أي أخطاء على السيرفر
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Video Downloader API",
    description="API لخدمة مشروع تحميل الفيديوهات",
    version="1.0.0"
)

# إعداد CORS للسماح لتطبيقك (Flutter/Web) بالوصول للسيرفر
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# الإعدادات العامة لـ yt-dlp
YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'ignoreerrors': True,
    'format': 'best', # اختيار أفضل جودة مدمجة افتراضياً
}

@app.get("/")
def root():
    return {
        "message": "سيرفر تحميل الفيديوهات يعمل بنجاح ✅",
        "endpoints": ["/info", "/download", "/health"]
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/info")
def get_video_info(url: str = Query(..., description="رابط الفيديو")):
    try:
        logger.info(f"طلب معلومات للرابط: {url}")
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise HTTPException(status_code=404, detail="تعذر العثور على الفيديو")
            
            return {
                "title": info.get("title", "بدون عنوان"),
                "duration": info.get("duration", 0),
                "thumbnail": info.get("thumbnail", ""),
                "uploader": info.get("uploader", "غير معروف"),
                "platform": info.get("extractor_key", "غير معروف")
            }
    except Exception as e:
        logger.error(f"خطأ في Info: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/download")
def get_download_url(
    url: str = Query(..., description="رابط الفيديو"),
    quality: Optional[str] = Query("best", description="الجودة المطلوبة")
):
    try:
        logger.info(f"طلب رابط تحميل: {url}")
        opts = {**YDL_OPTS, 'format': quality}
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise HTTPException(status_code=404, detail="الفيديو غير متاح")

            # محاولة العثور على رابط مباشر (Direct URL)
            download_url = info.get('url')
            
            # إذا لم يوجد رابط مباشر، نبحث في قائمة الصيغ (Formats)
            if not download_url and 'formats' in info:
                # تصفية الصيغ التي تحتوي على فيديو وصوت معاً لضمان التشغيل
                valid_formats = [f for f in info['formats'] if f.get('vcodec') != 'none' and f.get('acodec') != 'none']
                if not valid_formats:
                    valid_formats = [f for f in info['formats'] if f.get('vcodec') != 'none']
                
                if valid_formats:
                    # اختيار آخر صيغة (غالباً تكون الأعلى جودة)
                    download_url = valid_formats[-1].get('url')

            if not download_url:
                raise HTTPException(status_code=404, detail="تعذر استخراج رابط التحميل")

            return {
                "success": True,
                "title": info.get("title", "video"),
                "download_url": download_url,
                "extension": info.get("ext", "mp4"),
                "duration": info.get("duration", 0)
            }
    except Exception as e:
        logger.error(f"خطأ في Download: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

# تشغيل السيرفر - هذا الجزء هو الأهم لتجنب خطأ 127
if __name__ == "__main__":
    import uvicorn
    # السيرفر السحابي (مثل Cloud Run) يرسل رقم البورت في متغير بيئة يسمى PORT
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"بدء تشغيل السيرفر على البورت: {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
