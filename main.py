
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

# الإعدادات العامة لـ yt-dlp مع إضافة مهلة زمنية
YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'ignoreerrors': True,
    'format': 'best',  # اختيار أفضل جودة مدمجة افتراضياً
    'socket_timeout': 30,  # مهلة 30 ثانية
}

@app.get("/")
def root():
    return {
        "message": "سيرفر تحميل الفيديوهات يعمل بنجاح ✅",
        "endpoints": ["/info", "/download", "/health"],
        "status": "online"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "video-downloader"}

@app.get("/info")
def get_video_info(url: str = Query(..., description="رابط الفيديو")):
    try:
        logger.info(f"طلب معلومات للرابط: {url}")
        
        # التحقق من صحة الرابط
        if not url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="الرابط غير صحيح")
        
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise HTTPException(status_code=404, detail="تعذر العثور على الفيديو")
            
            return {
                "success": True,
                "title": info.get("title", "بدون عنوان"),
                "duration": info.get("duration", 0),
                "thumbnail": info.get("thumbnail", ""),
                "uploader": info.get("uploader", "غير معروف"),
                "platform": info.get("extractor_key", "غير معروف"),
                "views": info.get("view_count", 0),
                "like_count": info.get("like_count", 0)
            }
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"خطأ في التحميل من yt-dlp: {str(e)}")
        raise HTTPException(status_code=400, detail="الرابط غير مدعوم أو غير صالح")
    except Exception as e:
        logger.error(f"خطأ في Info: {str(e)}")
        raise HTTPException(status_code=400, detail=f"حدث خطأ: {str(e)}")

@app.get("/download")
def get_download_url(
    url: str = Query(..., description="رابط الفيديو"),
    quality: Optional[str] = Query("best", description="الجودة المطلوبة (best, worst, bestvideo+bestaudio)")
):
    try:
        logger.info(f"طلب رابط تحميل: {url}")
        
        # التحقق من صحة الرابط
        if not url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="الرابط غير صحيح")
        
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
                    
                    # إضافة معلومات إضافية عن الجودة
                    selected_format = valid_formats[-1]
                    quality_info = selected_format.get('format_note', '')
                    if not quality_info and selected_format.get('height'):
                        quality_info = f"{selected_format['height']}p"

            if not download_url:
                raise HTTPException(status_code=404, detail="تعذر استخراج رابط التحميل")

            return {
                "success": True,
                "title": info.get("title", "video"),
                "download_url": download_url,
                "extension": info.get("ext", "mp4"),
                "duration": info.get("duration", 0),
                "quality": quality_info if 'quality_info' in locals() else quality,
                "platform": info.get("extractor_key", "unknown")
            }
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"خطأ في yt-dlp: {str(e)}")
        raise HTTPException(status_code=400, detail="الرابط غير مدعوم أو غير صالح")
    except Exception as e:
        logger.error(f"خطأ في Download: {str(e)}")
        raise HTTPException(status_code=400, detail=f"حدث خطأ: {str(e)}")

@app.get("/test")
def test_url(url: str = Query(..., description="رابط للاختبار")):
    """نقطة اختبار سريعة للتحقق من صحة الرابط"""
    try:
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "status": "success",
                "platform": info.get("extractor_key", "unknown"),
                "title": info.get("title", "No title")[:100],
                "message": "✓ الرابط صالح"
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"✗ الرابط غير صالح: {str(e)[:100]}"
        }

# تشغيل السيرفر - هذا الجزء هو الأهم لتجنب خطأ 127
if __name__ == "__main__":
    import uvicorn
    # السيرفر السحابي (مثل Render) يرسل رقم البورت في متغير بيئة يسمى PORT
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"بدء تشغيل السيرفر على البورت: {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)س
