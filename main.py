from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict, Any
import yt_dlp
import time
import re
import urllib.parse
from datetime import datetime
import subprocess
import os
import tempfile
import shutil
import random

app = FastAPI(
    title="CupGet Video Downloader API - Professional Edition",
    version="3.1.0",
    description="يدعم جميع صيغ الفيديو والمواقع مع كشف DRM"
)

# إعدادات CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# تخزين مؤقت للطلبات
rate_limit_storage: Dict[str, List[float]] = {}

# ============ قائمة User-Agents حقيقية لمتصفحات مختلفة ============
USER_AGENTS = [
    # Chrome على Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
    
    # Chrome على macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    
    # Firefox
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0',
    
    # Safari
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    
    # Edge
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
]

# ============ قائمة Accept Headers ============
ACCEPT_HEADERS = [
    'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
]

def get_random_user_agent() -> str:
    """إرجاع User-Agent عشوائي لتجنب الحظر"""
    return random.choice(USER_AGENTS)

def get_random_accept_header() -> str:
    """إرجاع Accept Header عشوائي"""
    return random.choice(ACCEPT_HEADERS)

# --- قوائم الصيغ المدعومة ---
ALL_VIDEO_EXTENSIONS = [
    '.mp4', '.mov', '.mkv', '.webm', '.avi', '.flv', '.wmv',
    '.m4v', '.mp4v', '.mpv', '.qt', '.m2ts', '.mts', '.ts',
    '.m2v', '.mpeg', '.mpg', '.vob', '.3gp', '.3g2', '.asf',
    '.divx', '.f4v', '.gifv', '.mxf', '.ogv', '.ogg', '.rm',
    '.rmvb', '.swf', '.wm', '.yuv', '.hevc', '.h265', '.av1',
]

HLS_EXTENSIONS = ['.m3u8', '.m3u']
DASH_EXTENSIONS = ['.mpd']

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
    is_direct: bool = False
    is_streaming: bool = False
    streaming_type: Optional[str] = None

class VideoInfo(BaseModel):
    title: str
    thumbnail: str
    duration: float
    platform: str
    download_options: Dict[str, Optional[DownloadOption]]
    is_drm_protected: bool = False
    drm_message: Optional[str] = None
    all_formats_count: int = 0
    is_streaming: bool = False
    streaming_warning: Optional[str] = None
    extracted_url: Optional[str] = None  # الرابط بعد فك التوجيه

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
    
    rate_limit_storage[client_ip] = [
        t for t in rate_limit_storage[client_ip] if current_time - t < 60
    ]
    
    if len(rate_limit_storage[client_ip]) >= 10:
        return False
    
    rate_limit_storage[client_ip].append(current_time)
    return True

def extract_final_url(url: str) -> str:
    """محاولة فك توجيه الرابط والحصول على الرابط النهائي"""
    try:
        import requests
        # استخدام User-Agent حقيقي لفك التوجيه
        headers = {
            'User-Agent': get_random_user_agent(),
            'Accept': get_random_accept_header(),
            'Accept-Language': 'en-US,en;q=0.9,ar;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        response = requests.head(url, headers=headers, allow_redirects=True, timeout=10)
        final_url = response.url
        
        # إذا لم ينجح HEAD، جرب GET
        if final_url == url:
            response = requests.get(url, headers=headers, allow_redirects=True, timeout=10, stream=True)
            final_url = response.url
            response.close()
        
        return final_url
    except Exception:
        return url

def extract_video_info_generic(url: str) -> Dict[str, Any]:
    """استخراج معلومات الفيديو باستخدام yt-dlp مع دعم جميع المواقع"""
    
    # محاولة فك توجيه الرابط أولاً
    final_url = extract_final_url(url)
    
    # إعدادات yt-dlp المتقدمة لمحاكاة المتصفح
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'extract_flat': False,
        'no_check_certificate': True,
        'prefer_insecure': False,
        'socket_timeout': 30,
        'retries': 10,
        'fragment_retries': 10,
        
        # 🔥 الأهم: محاكاة المتصفح الحقيقي
        'user_agent': get_random_user_agent(),
        'headers': {
            'Accept': get_random_accept_header(),
            'Accept-Language': 'en-US,en;q=0.9,ar;q=0.8,fr;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        },
        
        # تمكين المعالج العام للمواقع
        'force_generic_extractor': False,  # False = استخدام extractors مخصصة أولاً
        
        # إعدادات إضافية للروابط القصيرة
        'default_search': 'auto',
        'source_address': '0.0.0.0',
        
        # محاولة استخراج حتى لو بدا الموقع غير مدعوم
        'ignore_no_formats_error': True,
        
        # تمكين استخراج المعلومات الأساسية من HTML
        'extractor_args': {
            'generic': {
                'fragment': ['--no-playlist'],
                'no_playlist': ['--no-playlist'],
            }
        },
        
        # وقت إضافي للمواقع البطيئة
        'sleep_interval': 1,
        'max_sleep_interval': 3,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # محاولة استخراج المعلومات
            info = ydl.extract_info(final_url, download=False)
            
            if not info:
                raise Exception("Could not fetch video information")
            
            # التحقق من قوائم التشغيل
            if 'entries' in info and info['entries']:
                first_video = info['entries'][0]
                if first_video:
                    info = first_video
            
            # إذا لم نجد رابط فيديو، جرب طريقة بديلة
            if not info.get('url') and not info.get('formats'):
                # محاولة مع force_generic_extractor = True
                ydl_opts['force_generic_extractor'] = True
                with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                    info = ydl2.extract_info(final_url, download=False)
            
            all_formats = info.get('formats', [])
            
            # تصنيف الجودات
            hd_formats = []
            sd_formats = []
            
            for f in all_formats:
                vcodec = f.get('vcodec', 'none')
                if vcodec == 'none' and f.get('acodec') != 'none':
                    continue
                
                height = f.get('height') or 0
                filesize = f.get('filesize') or f.get('filesize_approx') or 0
                ext = f.get('ext', 'mp4')
                
                # التحقق من صحة الرابط
                url_value = f.get('url', '')
                if not url_value:
                    continue
                
                format_info = {
                    'quality': f"{height}p" if height > 0 else 'Auto',
                    'url': url_value,
                    'filesize': filesize,
                    'filesize_mb': round(filesize / (1024 * 1024), 2) if filesize else 0,
                    'extension': ext,
                    'height': height,
                    'bitrate': f.get('tbr', 0),
                    'format_note': f.get('format_note', ''),
                    'is_direct': True,
                    'is_streaming': False,
                    'streaming_type': None
                }
                
                if height >= 720 or (height == 0 and 'best' in str(f.get('format_note', '')).lower()):
                    hd_formats.append(format_info)
                elif height > 0:
                    sd_formats.append(format_info)
            
            # ترتيب الجودات
            hd_formats.sort(key=lambda x: x['height'], reverse=True)
            sd_formats.sort(key=lambda x: x['height'], reverse=True)
            
            best_hd = hd_formats[0] if hd_formats else None
            best_sd = sd_formats[0] if sd_formats else None
            
            # إذا لم نجد صيغ، نستخدم الرابط الأصلي
            if not best_hd and info.get('url'):
                best_hd = {
                    'quality': 'Original',
                    'url': info.get('url'),
                    'filesize': 0,
                    'filesize_mb': 0,
                    'extension': info.get('ext', 'mp4'),
                    'height': 0,
                    'bitrate': 0,
                    'format_note': 'الرابط الأصلي',
                    'is_direct': True,
                    'is_streaming': False,
                    'streaming_type': None
                }
            
            # تحديد المنصة
            platform = info.get('extractor_key', 'generic').lower()
            platform_map = {
                'youtube': 'youtube', 'facebook': 'facebook', 'instagram': 'instagram',
                'twitter': 'twitter', 'tiktok': 'tiktok', 'vimeo': 'vimeo',
                'dailymotion': 'dailymotion', 'twitch': 'twitch', 'reddit': 'reddit',
                'generic': 'web', 'genericmedia': 'web', 'generichttp': 'web'
            }
            platform = platform_map.get(platform, 'web')
            
            # تنظيف خيارات التحميل
            clean_options = {}
            for key, option in [('hd', best_hd), ('sd', best_sd)]:
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
                'is_drm_protected': False,
                'drm_message': None,
                'all_formats_count': len(all_formats),
                'is_streaming': False,
                'streaming_warning': None,
                'extracted_url': final_url
            }
            
    except Exception as e:
        error_msg = str(e)
        raise HTTPException(status_code=400, detail=error_msg)

# ============ API Endpoints ============

@app.post("/extract", response_model=ExtractResponse)
async def extract(request: Request, req_body: ExtractRequest):
    client_ip = request.client.host
    if not check_rate_limit(client_ip):
        return ExtractResponse(
            success=False, 
            error="تم تجاوز الحد المسموح. الرجاء الانتظار 10 طلبات كحد أقصى في الدقيقة"
        )
    
    url = str(req_body.url)
    
    # التحقق من الروابط المباشرة أولاً
    url_lower = url.lower()
    for ext in ALL_VIDEO_EXTENSIONS:
        if url_lower.endswith(ext):
            return ExtractResponse(
                success=True,
                data=VideoInfo(
                    title="Direct Video",
                    thumbnail="",
                    duration=0,
                    platform="direct",
                    download_options={
                        'hd': DownloadOption(
                            quality="Direct",
                            url=url,
                            extension=ext.replace('.', ''),
                            is_direct=True,
                            is_streaming=False,
                            streaming_type=None
                        ),
                        'sd': None
                    },
                    is_drm_protected=False,
                    all_formats_count=1,
                    extracted_url=url
                )
            )
    
    # محاولة الاستخراج باستخدام yt-dlp
    try:
        data = extract_video_info_generic(url)
        return ExtractResponse(success=True, data=VideoInfo(**data))
    except HTTPException as e:
        return ExtractResponse(success=False, error=e.detail)
    except Exception as e:
        return ExtractResponse(success=False, error=str(e))

@app.get("/supported-formats")
async def supported_formats():
    return {
        "success": True,
        "count": len(ALL_VIDEO_EXTENSIONS),
        "formats": ALL_VIDEO_EXTENSIONS
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "3.1.0"
    }

@app.get("/")
async def index():
    return {
        "message": "CupGet Video Downloader API - Professional Edition",
        "version": "3.1.0",
        "features": [
            "✅ دعم جميع صيغ الفيديو المباشرة",
            "✅ دعم آلاف المواقع عبر yt-dlp",
            "✅ محاكاة متصفح Chrome/Firefox/Safari",
            "✅ فك توجيه الروابط تلقائياً",
            "✅ نظام حماية من الطلبات المتكررة"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
