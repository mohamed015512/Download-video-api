
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import yt_dlp
import logging

# إعداد السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# إنشاء تطبيق FastAPI
app = FastAPI(
    title="Video Downloader API",
    description="API لتحميل الفيديوهات من وسائل التواصل الاجتماعي",
    version="1.0.0"
)

# إعداد CORS للسماح للتطبيق بالتواصل مع السيرفر
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # في الإنتاج، حدد نطاق تطبيقك فقط
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# إعدادات yt-dlp
YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'ignoreerrors': True,
}

@app.get("/")
def root():
    """الصفحة الرئيسية للتحقق من عمل السيرفر"""
    return {
        "message": "مرحباً بك في سيرفر تحميل الفيديوهات",
        "status": "يعمل ✅",
        "endpoints": [
            "/health - للتحقق من صحة السيرفر",
            "/info?url=URL - للحصول على معلومات الفيديو",
            "/download?url=URL - للحصول على رابط التحميل"
        ]
    }

@app.get("/health")
def health_check():
    """التحقق من صحة السيرفر"""
    return {
        "status": "healthy",
        "message": "السيرفر يعمل بشكل جيد"
    }

@app.get("/info")
def get_video_info(url: str = Query(..., description="رابط الفيديو")):
    """
    الحصول على معلومات الفيديو (العنوان، المدة، الصور المصغرة)
    """
    try:
        logger.info(f"جلب معلومات الفيديو: {url}")
        
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise HTTPException(status_code=404, detail="لم يتم العثور على الفيديو")
            
            # استخراج المعلومات المطلوبة
            result = {
                "title": info.get("title", "بدون عنوان"),
                "duration": info.get("duration", 0),
                "thumbnail": info.get("thumbnail", ""),
                "uploader": info.get("uploader", "غير معروف"),
                "views": info.get("view_count", 0),
                "likes": info.get("like_count", 0),
                "formats_count": len(info.get("formats", []))
            }
            
            return result
            
    except Exception as e:
        logger.error(f"خطأ في جلب المعلومات: {str(e)}")
        raise HTTPException(status_code=400, detail=f"حدث خطأ: {str(e)}")

@app.get("/download")
def get_download_url(
    url: str = Query(..., description="رابط الفيديو"),
    quality: Optional[str] = Query("best[height<=720]", description="جودة الفيديو (مثال: best, worst, best[height<=480])")
):
    """
    الحصول على رابط التحميل المباشر للفيديو
    """
    try:
        logger.info(f"جلب رابط التحميل: {url} بجودة {quality}")
        
        # إعدادات مخصصة للتحميل
        opts = {
            **YDL_OPTS,
            'format': quality,
        }
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise HTTPException(status_code=404, detail="لم يتم العثور على الفيديو")
            
            # محاولة الحصول على رابط التحميل المباشر
            download_url = None
            
            # إذا كان format محدد
            if 'url' in info:
                download_url = info['url']
            # البحث في formats
            elif 'formats' in info and len(info['formats']) > 0:
                # اختيار أفضل صيغة حسب الطلب
                formats = info['formats']
                
                # فلترة الصيغ التي تحتوي على فيديو
                video_formats = [f for f in formats if f.get('vcodec') != 'none']
                
                if video_formats:
                    # اختيار الأول أو حسب الجودة
                    best_format = video_formats[0]
                    download_url = best_format.get('url')
            
            if not download_url:
                raise HTTPException(status_code=404, detail="لم يتم العثور على رابط تحميل")
            
            return {
                "success": True,
                "title": info.get("title", "فيديو"),
                "download_url": download_url,
                "quality": quality,
                "duration": info.get("duration", 0),
                "format": info.get("ext", "mp4")
            }
            
    except Exception as e:
        logger.error(f"خطأ في جلب رابط التحميل: {str(e)}")
        raise HTTPException(status_code=400, detail=f"حدث خطأ: {str(e)}")

@app.get("/test")
def test_url(url: str = Query(..., description="رابط للاختبار")):
    """
    نقطة اختبار بسيطة لفحص الروابط
    """
    try:
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            # محاولة استخراج المعلومات الأساسية فقط
            info = ydl.extract_info(url, download=False)
            
            return {
                "status": "success",
                "platform": info.get("extractor_key", "غير معروف"),
                "title": info.get("title", "بدون عنوان")[:100],
                "duration": info.get("duration", 0),
                "message": "✓ الرابط صالح ويمكن تحميله"
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"✗ الرابط غير صالح أو حدث خطأ: {str(e)[:100]}"
        }

# تشغيل السيرفر محلياً (للتطوير فقط)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
