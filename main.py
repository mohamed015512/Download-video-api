from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional
import yt_dlp
import logging
import os

# إعداد السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Video Downloader API")

# إعداد CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# إعدادات yt-dlp
YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'ignoreerrors': True,
    'extract_flat': False,
}

@app.get("/")
def root():
    return {
        "message": "سيرفر تحميل الفيديوهات يعمل ✅",
        "endpoints": ["/health", "/test", "/info", "/download"]
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/test")
def test_url(url: str = Query(..., description="رابط الفيديو")):
    """اختبار صلاحية الرابط"""
    try:
        logger.info(f"اختبار الرابط: {url}")
        
        if not url.startswith(('http://', 'https://')):
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "الرابط يجب أن يبدأ بـ http:// أو https://"}
            )
        
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # التحقق من أن info ليس None
            if info is None:
                return JSONResponse(
                    status_code=400,
                    content={"status": "error", "message": "لم يتم العثور على معلومات للفيديو"}
                )
            
            return {
                "status": "success",
                "platform": info.get("extractor_key", "unknown"),
                "title": info.get("title", "بدون عنوان")[:100]
            }
            
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"خطأ في yt-dlp: {str(e)}")
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": f"الرابط غير مدعوم: {str(e)[:100]}"}
        )
    except Exception as e:
        logger.error(f"خطأ غير متوقع: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"حدث خطأ: {str(e)[:100]}"}
        )

@app.get("/info")
def get_video_info(url: str = Query(..., description="رابط الفيديو")):
    """الحصول على معلومات الفيديو"""
    try:
        logger.info(f"جلب معلومات: {url}")
        
        if not url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="الرابط غير صحيح")
        
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # التحقق الأساسي: إذا كان info يساوي None
            if info is None:
                raise HTTPException(status_code=404, detail="لم يتم العثور على الفيديو أو الرابط غير صالح")
            
            # استخراج المعلومات مع قيم افتراضية آمنة
            title = info.get("title") if info.get("title") else "بدون عنوان"
            duration = info.get("duration") if info.get("duration") else 0
            thumbnail = info.get("thumbnail") if info.get("thumbnail") else ""
            uploader = info.get("uploader") if info.get("uploader") else "غير معروف"
            platform = info.get("extractor_key") if info.get("extractor_key") else "غير معروف"
            
            return {
                "success": True,
                "title": title,
                "duration": duration,
                "thumbnail": thumbnail,
                "uploader": uploader,
                "platform": platform,
            }
            
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"خطأ في yt-dlp: {str(e)}")
        raise HTTPException(status_code=400, detail=f"الرابط غير مدعوم: {str(e)[:100]}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"خطأ في Info: {str(e)}")
        raise HTTPException(status_code=400, detail=f"حدث خطأ: {str(e)[:100]}")

@app.get("/download")
def get_download_url(
    url: str = Query(..., description="رابط الفيديو"),
    quality: Optional[str] = Query("best", description="الجودة المطلوبة")
):
    """الحصول على رابط التحميل المباشر"""
    try:
        logger.info(f"جلب رابط التحميل: {url}")
        
        if not url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="الرابط غير صحيح")
        
        opts = {**YDL_OPTS, 'format': quality}
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # التحقق الأساسي
            if info is None:
                raise HTTPException(status_code=404, detail="لم يتم العثور على الفيديو")
            
            # محاولة العثور على رابط التحميل
            download_url = None
            
            # الطريقة الأولى: رابط مباشر
            if info.get("url"):
                download_url = info.get("url")
            
            # الطريقة الثانية: البحث في الصيغ
            if not download_url and info.get("formats"):
                for f in info["formats"]:
                    if f and f.get("vcodec") != "none":
                        download_url = f.get("url")
                        if download_url:
                            break
            
            if not download_url:
                raise HTTPException(status_code=404, detail="تعذر استخراج رابط التحميل")
            
            title = info.get("title") if info.get("title") else "video"
            # تنظيف اسم الملف من الأحرف غير المسموحة
            title = "".join(c for c in title if c.isalnum() or c in " -_").strip()
            
            return {
                "success": True,
                "title": title,
                "download_url": download_url,
                "duration": info.get("duration", 0)
            }
            
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"خطأ في yt-dlp: {str(e)}")
        raise HTTPException(status_code=400, detail=f"الرابط غير مدعوم: {str(e)[:100]}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"خطأ في Download: {str(e)}")
        raise HTTPException(status_code=400, detail=f"حدث خطأ: {str(e)[:100]}")

# تشغيل السيرفر
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"بدء تشغيل السيرفر على البورت: {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
