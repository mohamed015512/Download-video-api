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

app = FastAPI(title="Video Downloader API")

# إعداد CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# إعدادات yt-dlp المحسنة لفيسبوك
YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'ignoreerrors': True,
    'extract_flat': False,
    'cookiefile': None,  # يمكن إضافة ملف cookies إذا لزم الأمر
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    }
}

# إعدادات خاصة لفيسبوك
FACEBOOK_OPTS = {
    **YDL_OPTS,
    'format': 'best[ext=mp4]/best',  # تفضيل صيغة mp4
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
        
        # اختيار الإعدادات المناسبة حسب نوع الرابط
        opts = FACEBOOK_OPTS if 'facebook.com' in url or 'fb.watch' in url else YDL_OPTS
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if info is None:
                return JSONResponse(
                    status_code=400,
                    content={"status": "error", "message": "لم يتم العثور على معلومات للفيديو"}
                )
            
            return {
                "status": "success",
                "platform": info.get("extractor_key", "unknown"),
                "title": info.get("title", "بدون عنوان")[:100],
                "duration": info.get("duration", 0),
                "message": "✓ الرابط صالح"
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
        
        # اختيار الإعدادات المناسبة حسب نوع الرابط
        opts = FACEBOOK_OPTS if 'facebook.com' in url or 'fb.watch' in url else YDL_OPTS
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if info is None:
                raise HTTPException(status_code=404, detail="لم يتم العثور على الفيديو")
            
            # استخراج المعلومات مع قيم افتراضية
            title = info.get("title") or "بدون عنوان"
            duration = info.get("duration") or 0
            thumbnail = info.get("thumbnail") or ""
            uploader = info.get("uploader") or info.get("channel") or "غير معروف"
            platform = info.get("extractor_key") or "unknown"
            
            # تنسيق المدة
            duration_formatted = f"{duration // 60}:{duration % 60:02d}" if duration else "غير معروف"
            
            return {
                "success": True,
                "title": title,
                "duration": duration,
                "duration_formatted": duration_formatted,
                "thumbnail": thumbnail,
                "uploader": uploader,
                "platform": platform,
            }
            
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"خطأ في yt-dlp: {str(e)}")
        raise HTTPException(status_code=400, detail=f"فشل تحميل الفيديو: {str(e)[:100]}")
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
        
        # إعدادات خاصة حسب المنصة
        if 'facebook.com' in url or 'fb.watch' in url:
            opts = {**FACEBOOK_OPTS, 'format': 'best[ext=mp4]/best'}
        else:
            opts = {**YDL_OPTS, 'format': quality}
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if info is None:
                raise HTTPException(status_code=404, detail="لم يتم العثور على الفيديو")
            
            download_url = None
            selected_quality = quality
            
            # محاولة الحصول على الرابط
            if info.get("url"):
                download_url = info.get("url")
            
            # البحث في الصيغ
            if not download_url and info.get("formats"):
                # تصفية الصيغ المناسبة
                video_formats = []
                for f in info["formats"]:
                    if f and f.get("vcodec") != "none":
                        video_formats.append(f)
                
                # ترتيب حسب الجودة
                video_formats.sort(key=lambda x: x.get('height', 0) or 0, reverse=True)
                
                if video_formats:
                    selected = video_formats[0]
                    download_url = selected.get('url')
                    if selected.get('height'):
                        selected_quality = f"{selected['height']}p"
            
            if not download_url:
                raise HTTPException(status_code=404, detail="تعذر استخراج رابط التحميل")
            
            # تنظيف اسم الملف
            title = info.get("title") or "facebook_video"
            title = re.sub(r'[<>:"/\\|?*]', '', title)[:50]
            
            return {
                "success": True,
                "title": title,
                "download_url": download_url,
                "quality": selected_quality,
                "duration": info.get("duration", 0),
                "platform": info.get("extractor_key", "facebook")
            }
            
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"خطأ في yt-dlp: {str(e)}")
        raise HTTPException(status_code=400, detail=f"فشل التحميل: {str(e)[:100]}")
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
