from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict, Any
import yt_dlp
import time
from datetime import datetime

app = FastAPI(title="Professional Video Downloader API", version="1.2.0")

# إعدادات CORS للسماح لتطبيق الفلاتر بالاتصال
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# تخزين بسيط لتحديد عدد الطلبات (Rate Limiting)
rate_limit_storage: Dict[str, List[float]] = {}

# --- النماذج (Models) ---

class DownloadOption(BaseModel):
    quality: str
    url: str
    filesize: Optional[int] = None
    filesize_mb: float = 0
    extension: str = "mp4"
    height: int = 0
    bitrate: Optional[float] = None
    format_note: Optional[str] = None

class VideoInfo(BaseModel):
    title: str
    thumbnail: str
    duration: float
    platform: str
    download_options: Dict[str, Optional[DownloadOption]]
    all_formats_count: int = 0

class ExtractRequest(BaseModel):
    url: HttpUrl

class ExtractResponse(BaseModel):
    success: bool
    data: Optional[VideoInfo] = None
    error: Optional[str] = None

# --- الوظائف المساعدة ---

def check_rate_limit(client_ip: str) -> bool:
    current_time = time.time()
    if client_ip not in rate_limit_storage:
        rate_limit_storage[client_ip] = []
    
    # تنظيف الطلبات القديمة (أقدم من دقيقة)
    rate_limit_storage[client_ip] = [
        t for t in rate_limit_storage[client_ip] if current_time - t < 60
    ]
    
    if len(rate_limit_storage[client_ip]) >= 10: # حد أقصى 10 طلبات في الدقيقة
        return False
    
    rate_limit_storage[client_ip].append(current_time)
    return True

def extract_video_info(url: str) -> Dict[str, Any]:
    """استخراج معلومات الفيديو والروابط باستخدام yt-dlp"""
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'skip_download': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise Exception("Could not fetch info")

            all_formats = info.get('formats', [])
            
            # تصنيف الجودات إلى HD و SD
            hd_formats = []  # جودة عالية (720p فأعلى)
            sd_formats = []  # جودة موفرة (أقل من 720p)
            
            for f in all_formats:
                vcodec = f.get('vcodec', 'none')
                if vcodec == 'none':
                    continue
                    
                height = f.get('height') or 0
                filesize = f.get('filesize') or f.get('filesize_approx') or 0
                
                format_info = {
                    'quality': f"{height}p" if height > 0 else 'Unknown',
                    'url': f.get('url'),
                    'filesize': filesize,
                    'filesize_mb': round(filesize / (1024 * 1024), 2) if filesize else 0,
                    'extension': f.get('ext', 'mp4'),
                    'height': height,
                    'bitrate': f.get('tbr', 0),
                    'format_note': f.get('format_note', '')
                }
                
                if height >= 720:  # HD
                    hd_formats.append(format_info)
                elif height > 0:   # SD
                    sd_formats.append(format_info)
            
            # ترتيب الجودات تنازلياً
            hd_formats.sort(key=lambda x: x['height'], reverse=True)
            sd_formats.sort(key=lambda x: x['height'], reverse=True)
            
            # اختيار أفضل جودة HD وأفضل جودة SD
            best_hd = hd_formats[0] if hd_formats else None
            best_sd = sd_formats[0] if sd_formats else None
            
            # تحديد المنصة
            platform = info.get('extractor_key', 'unknown').lower()
            if 'youtube' in platform:
                platform = 'youtube'
                # ليوتيوب، نضمن وجود جودة منخفضة أيضاً
                if best_hd and not best_sd:
                    # البحث عن جودة 360p أو 480p
                    for f in all_formats:
                        height = f.get('height') or 0
                        if 360 <= height < 720:
                            best_sd = {
                                'quality': f"{height}p",
                                'url': f.get('url'),
                                'filesize': f.get('filesize') or 0,
                                'filesize_mb': round((f.get('filesize') or 0) / (1024 * 1024), 2),
                                'extension': f.get('ext', 'mp4'),
                                'height': height,
                                'bitrate': f.get('tbr', 0),
                                'format_note': f.get('format_note', '')
                            }
                            break
                            
            elif 'facebook' in platform:
                platform = 'facebook'
                # فيسبوك غالباً عنده عدة جودات
                if not best_sd and hd_formats and len(hd_formats) > 1:
                    # نأخذ أقل جودة HD كبديل SD
                    best_sd = hd_formats[-1]
                    
            elif 'instagram' in platform:
                platform = 'instagram'
            elif 'twitter' in platform or 'x' in platform:
                platform = 'twitter'
            elif 'tiktok' in platform:
                platform = 'tiktok'

            # تجهيز خيارات التحميل
            download_options = {
                'hd': best_hd,
                'sd': best_sd
            }
            
            # تنظيف البيانات
            clean_options = {}
            for key, option in download_options.items():
                if option:
                    clean_options[key] = DownloadOption(**option)
                else:
                    clean_options[key] = None

            return {
                'title': info.get('title', 'Video'),
                'thumbnail': info.get('thumbnail', ''),
                'duration': float(info.get('duration', 0) or 0),
                'platform': platform,
                'download_options': clean_options,
                'all_formats_count': len(all_formats)
            }
            
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- المسارات (Endpoints) ---

@app.post("/extract", response_model=ExtractResponse)
async def extract(request: Request, req_body: ExtractRequest):
    client_ip = request.client.host
    if not check_rate_limit(client_ip):
        return ExtractResponse(success=False, error="Rate limit exceeded. Please wait. Maximum 10 requests per minute.")

    try:
        data = extract_video_info(str(req_body.url))
        return ExtractResponse(success=True, data=VideoInfo(**data))
    except HTTPException as e:
        return ExtractResponse(success=False, error=e.detail)
    except Exception as e:
        return ExtractResponse(success=False, error=str(e))

@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/")
async def index():
    return {
        "message": "Professional Video Downloader API is running",
        "version": "1.2.0",
        "endpoints": {
            "/extract": "POST - Extract video info and download URLs (returns HD and SD options)",
            "/health": "GET - Check API health"
        },
        "features": {
            "quality_selection": "Returns both HD (720p+) and SD (<720p) options when available",
            "platforms_supported": ["youtube", "facebook", "instagram", "twitter", "tiktok"],
            "rate_limit": "10 requests per minute per IP"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
