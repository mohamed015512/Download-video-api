from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional
import yt_dlp
import logging
import os
import re

# إعداد السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Video Downloader API",
    description="API لتحميل الفيديوهات من وسائل التواصل الاجتماعي",
    version="2.0.0"
)

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

# قائمة المواقع المدعومة
SUPPORTED_SITES = [
    "youtube.com", "youtu.be",
    "instagram.com", "instagr.am",
    "tiktok.com",
    "facebook.com", "fb.watch",
    "twitter.com", "x.com",
    "reddit.com",
    "vimeo.com",
    "dailymotion.com"
]

def is_supported_url(url: str) -> bool:
    """التحقق من أن الرابط من موقع مدعوم"""
    for site in SUPPORTED_SITES:
        if site in url.lower():
            return True
    return False

@app.get("/")
def root():
    return {
        "message": "سيرفر تحميل الفيديوهات يعمل بنجاح ✅",
        "status": "online",
        "version": "2.0.0",
        "endpoints": {
            "/health": "فحص صحة السيرفر",
            "/test": "اختبار صلاحية الرابط",
            "/info": "جلب معلومات الفيديو",
            "/download": "الحصول على رابط التحميل",
            "/supported": "قائمة المواقع المدعومة"
        }
    }

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "video-downloader-api",
        "version": "2.0.0"
    }

@app.get("/supported")
def get_supported_sites():
    """قائمة المواقع المدعومة"""
    return {
        "supported_sites": SUPPORTED_SITES,
        "count": len(SUPPORTED_SITES)
    }

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
        
        if not is_supported_url(url):
            return {
                "status": "warning",
                "message": "الرابط قد يكون من موقع غير مدعوم رسمياً",
                "supported_sites": SUPPORTED_SITES
            }
        
        opts = {**YDL_OPTS, 'extract_flat': True}
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            return {
                "status": "success",
                "platform": info.get("extractor_key", "unknown"),
                "title": info.get("title", "بدون عنوان")[:100],
                "duration": info.get("duration", 0),
                "thumbnail": info.get("thumbnail", ""),
                "message": "✓ الرابط صالح"
            }
            
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"خطأ في yt-dlp: {str(e)}")
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": f"الرابط غير مدعوم أو غير صالح: {str(e)[:100]}"}
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
            
            if not info:
                raise HTTPException(status_code=404, detail="لم يتم العثور على الفيديو")
            
            # تنسيق المدة
            duration = info.get("duration", 0)
            duration_formatted = f"{duration // 60}:{duration % 60:02d}" if duration else "غير معروف"
            
            return {
                "success": True,
                "title": info.get("title", "بدون عنوان"),
                "duration": duration,
                "duration_formatted": duration_formatted,
                "thumbnail": info.get("thumbnail", ""),
                "uploader": info.get("uploader", "غير معروف"),
                "platform": info.get("extractor_key", "غير معروف"),
                "views": info.get("view_count", 0),
                "like_count": info.get("like_count", 0),
                "description": info.get("description", "")[:200] if info.get("description") else "",
            }
            
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"خطأ في yt-dlp: {str(e)}")
        raise HTTPException(status_code=400, detail=f"الرابط غير مدعوم: {str(e)[:100]}")
    except Exception as e:
        logger.error(f"خطأ في Info: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/download")
def get_download_url(
    url: str = Query(..., description="رابط الفيديو"),
    quality: Optional[str] = Query("best", description="الجودة المطلوبة (best, worst, bestvideo+bestaudio)")
):
    """الحصول على رابط التحميل المباشر"""
    try:
        logger.info(f"جلب رابط التحميل: {url}")
        
        if not url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="الرابط غير صحيح")
        
        opts = {**YDL_OPTS, 'format': quality}
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise HTTPException(status_code=404, detail="الفيديو غير متاح")
            
            download_url = info.get('url')
            selected_quality = quality
            
            # إذا لم يوجد رابط مباشر، نبحث في قائمة الصيغ
            if not download_url and 'formats' in info:
                # تصفية الصيغ التي تحتوي على فيديو
                video_formats = [f for f in info['formats'] if f.get('vcodec') != 'none']
                
                if video_formats:
                    # اختيار أفضل صيغة حسب الجودة المطلوبة
                    if quality == "best":
                        selected = video_formats[-1]
                    elif quality == "worst":
                        selected = video_formats[0]
                    else:
                        selected = video_formats[-1]  # الافتراضي
                    
                    download_url = selected.get('url')
                    
                    # استخراج معلومات الجودة
                    if selected.get('height'):
                        selected_quality = f"{selected['height']}p"
                    elif selected.get('format_note'):
                        selected_quality = selected['format_note']
            
            if not download_url:
                raise HTTPException(status_code=404, detail="تعذر استخراج رابط التحميل")
            
            return {
                "success": True,
                "title": info.get("title", "video"),
                "download_url": download_url,
                "quality": selected_quality,
                "extension": info.get("ext", "mp4"),
                "duration": info.get("duration", 0),
                "platform": info.get("extractor_key", "unknown"),
                "filename": f"{info.get('title', 'video')[:50]}.mp4".replace('/', '_')
            }
            
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"خطأ في yt-dlp: {str(e)}")
        raise HTTPException(status_code=400, detail=f"الرابط غير مدعوم: {str(e)[:100]}")
    except Exception as e:
        logger.error(f"خطأ في Download: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

# تشغيل السيرفر
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"بدء تشغيل السيرفر على البورت: {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
