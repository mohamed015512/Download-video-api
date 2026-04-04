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

app = FastAPI(
    title="CupGet Video Downloader API - Professional Edition",
    version="3.0.0",
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

# --- قوائم الصيغ المدعومة ---

ALL_VIDEO_EXTENSIONS = [
    # صيغ شائعة
    '.mp4', '.mov', '.mkv', '.webm', '.avi', '.flv', '.wmv',
    
    # صيغ Apple / QuickTime
    '.m4v', '.mp4v', '.mpv', '.qt',
    
    # صيغ HD / Blu-ray
    '.m2ts', '.mts', '.ts', '.m2v', '.mpeg', '.mpg', '.vob',
    
    # صيغ متخصصة
    '.3gp', '.3g2',           # الهواتف المحمولة
    '.asf',                   # Windows Media
    '.divx',                  # DivX
    '.f4v', '.f4p', '.f4a', '.f4b',  # Adobe Flash
    '.gifv',                  # GIF متحرك عالي الجودة
    '.mxf',                   # Material Exchange Format
    '.ogv', '.ogg',           # Ogg Video
    '.rm', '.rmvb',           # RealMedia
    '.roq',                   # Id Software
    '.swf',                   # Shockwave Flash
    '.vivo',                  # VivoActive
    '.wm',                    # Windows Media
    '.yuv',                   # Raw YUV
    
    # صيغ متقدمة
    '.avchd',                 # AVCHD
    '.bik',                   # Bink Video
    '.cxi',                   # CineForm
    '.drc',                   # Dirac
    '.dv',                    # Digital Video
    '.hevc', '.h265',         # HEVC/H.265
    '.ivf',                   # IVF
    '.mjpeg', '.mjpg',        # MJPEG
    '.mk3d',                  # Matroska 3D
    '.nsv',                   # Nullsoft Streaming Video
    '.ogm',                   # Ogg Media
    '.rec',                   # Topfield PVR
    '.thp',                   # THP
    '.vid',                   # Generic Video
    '.viv',                   # VivoActive
    '.vp8', '.vp9',           # VP8/VP9
    '.av1',                   # AV1
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
    is_streaming: bool = False  # HLS أو DASH
    streaming_type: Optional[str] = None  # 'hls' أو 'dash'

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
        t for t inrate_limit_storage[client_ip] if current_time - t < 60
    ]
    
    if len(rate_limit_storage[client_ip]) >= 10:
        return False
    
    rate_limit_storage[client_ip].append(current_time)
    return True

def is_streaming_url(url: str) -> Optional[Dict[str, Any]]:
    """التحقق من روابط البث المباشر HLS و DASH"""
    url_lower = url.lower()
    
    for ext in HLS_EXTENSIONS:
        if ext in url_lower:
            return {
                'type': 'hls',
                'url': url,
                'warning': 'هذا الرابط من نوع HLS (بث متقطع). قد يحتاج إلى دمج المقاطع بعد التحميل.'
            }
    
    for ext in DASH_EXTENSIONS:
        if ext in url_lower:
            return {
                'type': 'dash',
                'url': url,
                'warning': 'هذا الرابط من نوع DASH (بث متكيف). قد يحتاج إلى معالجة خاصة.'
            }
    
    return None

def is_direct_video_url(url: str) -> Optional[Dict[str, Any]]:
    """التحقق من الروابط المباشرة لجميع صيغ الفيديو"""
    url_lower = url.lower()
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    
    for ext in ALL_VIDEO_EXTENSIONS:
        # التحقق من نهاية الرابط
        if url_lower.endswith(ext):
            return _create_direct_response(url, ext, path)
        
        # التحقق من وجود معلمات استعلام
        if f'{ext}?' in url_lower or f'{ext}&' in url_lower:
            return _create_direct_response(url, ext, path)
        
        # التحقق من وجود الامتداد في المسار
        if path.lower().endswith(ext):
            return _create_direct_response(url, ext, path)
    
    return None

def _create_direct_response(url: str, extension: str, path: str) -> Dict[str, Any]:
    """إنشاء استجابة للرابط المباشر"""
    filename = path.split('/')[-1].split('?')[0]
    ext_clean = extension.replace('.', '')
    
    # محاولة استخراج اسم أفضل
    title = filename.replace(extension, '').replace('_', ' ').replace('-', ' ')
    title = title.replace('%20', ' ').replace('+', ' ').strip()
    
    if not title or len(title) < 2:
        title = f"فيديو مباشر {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    return {
        'title': title.title(),
        'thumbnail': '',
        'duration': 0,
        'platform': 'direct',
        'download_options': {
            'hd': {
                'quality': f'Direct Video ({ext_clean.upper()})',
                'url': url,
                'filesize': None,
                'filesize_mb': 0,
                'extension': ext_clean,
                'height': 0,
                'bitrate': None,
                'format_note': 'رابط فيديو مباشر - تحميل فوري',
                'is_direct': True,
                'is_streaming': False,
                'streaming_type': None
            },
            'sd': None
        },
        'is_drm_protected': False,
        'all_formats_count': 1,
        'is_streaming': False,
        'streaming_warning': None
    }

def handle_streaming_url(url: str, stream_info: Dict[str, Any]) -> Dict[str, Any]:
    """معالجة روابط البث المباشر HLS/DASH"""
    return {
        'title': f'بث مباشر ({stream_info["type"].upper()})',
        'thumbnail': '',
        'duration': 0,
        'platform': 'streaming',
        'download_options': {
            'hd': {
                'quality': f'Streaming ({stream_info["type"].upper()})',
                'url': url,
                'filesize': None,
                'filesize_mb': 0,
                'extension': stream_info['type'],
                'height': 0,
                'bitrate': None,
                'format_note': stream_info['warning'],
                'is_direct': False,
                'is_streaming': True,
                'streaming_type': stream_info['type']
            },
            'sd': None
        },
        'is_drm_protected': False,
        'all_formats_count': 1,
        'is_streaming': True,
        'streaming_warning': stream_info['warning']
    }

def check_for_drm(error_message: str) -> bool:
    """التحقق من وجود DRM في رسائل الخطأ"""
    drm_keywords = [
        'drm', 'encrypted', 'license', 'widevine', 'playready',
        'fairplay', 'clearkey', 'cannot download', 'protected content',
        'decryption', 'encryption', 'no decrypt', 'DRM', '许可证'
    ]
    error_lower = error_message.lower()
    return any(keyword in error_lower for keyword in drm_keywords)

def extract_video_info_generic(url: str) -> Dict[str, Any]:
    """استخراج معلومات الفيديو باستخدام yt-dlp مع دعم جميع المواقع"""
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'extract_flat': False,
        'no_check_certificate': True,
        'prefer_insecure': False,
        'socket_timeout': 30,
        'retries': 5,
        'extract_flat': 'in_playlist',
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise Exception("Could not fetch video information")
            
            # التحقق من وجود DRM
            if info.get('_error') and check_for_drm(str(info.get('_error'))):
                return _create_drm_response(info)
            
            # التحقق من قوائم التشغيل
            if 'entries' in info and info['entries']:
                # نأخذ أول فيديو من قائمة التشغيل
                first_video = info['entries'][0]
                if first_video:
                    info = first_video
            
            all_formats = info.get('formats', [])
            
            # البحث عن روابط مباشرة في البيانات إذا لم توجد صيغ
            if not all_formats:
                if info.get('url'):
                    all_formats = [{
                        'url': info.get('url'),
                        'vcodec': 'avc1',
                        'height': 720,
                        'ext': info.get('ext', 'mp4')
                    }]
                elif info.get('requested_downloads'):
                    all_formats = info.get('requested_downloads')
            
            # تصنيف الجودات
            hd_formats = []
            sd_formats = []
            
            for f in all_formats:
                vcodec = f.get('vcodec', 'none')
                if vcodec == 'none' and f.get('acodec') != 'none':
                    # هذا صوت فقط، نتخطى
                    continue
                
                height = f.get('height') or 0
                filesize = f.get('filesize') or f.get('filesize_approx') or 0
                
                # تحديد الامتداد
                ext = f.get('ext', 'mp4')
                if ext not in ['mp4', 'mkv', 'webm', 'avi', 'mov']:
                    ext = 'mp4'  # افتراضي
                
                # التحقق مما إذا كانت صيغة البث
                is_streaming = False
                streaming_type = None
                url_value = f.get('url', '')
                
                if '.m3u8' in url_value.lower():
                    is_streaming = True
                    streaming_type = 'hls'
                elif '.mpd' in url_value.lower():
                    is_streaming = True
                    streaming_type = 'dash'
                
                format_info = {
                    'quality': f"{height}p" if height > 0 else 'Auto',
                    'url': url_value,
                    'filesize': filesize,
                    'filesize_mb': round(filesize / (1024 * 1024), 2) if filesize else 0,
                    'extension': ext,
                    'height': height,
                    'bitrate': f.get('tbr', 0),
                    'format_note': f.get('format_note', ''),
                    'is_direct': not is_streaming,
                    'is_streaming': is_streaming,
                    'streaming_type': streaming_type
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
                'dailymotion': 'dailymotion', 'twitch': 'twitch', 
                'generic': 'web', 'genericmedia': 'web'
            }
            platform = platform_map.get(platform, 'web')
            
            # تنظيف خيارات التحميل
            clean_options = {}
            for key, option in [('hd', best_hd), ('sd', best_sd)]:
                if option:
                    clean_options[key] = DownloadOption(**option)
                else:
                    clean_options[key] = None
            
            # تحذير للبث المباشر
            streaming_warning = None
            is_streaming = False
            if best_hd and best_hd.get('is_streaming'):
                is_streaming = True
                streaming_warning = 'هذا الفيديو من نوع البث المتقطع (HLS/DASH). قد لا يعمل التحميل المباشر على جميع الأجهزة.'
            
            return {
                'title': info.get('title', 'Video'),
                'thumbnail': info.get('thumbnail', ''),
                'duration': float(info.get('duration', 0) or 0),
                'platform': platform,
                'download_options': clean_options,
                'is_drm_protected': False,
                'drm_message': None,
                'all_formats_count': len(all_formats),
                'is_streaming': is_streaming,
                'streaming_warning': streaming_warning
            }
            
    except Exception as e:
        error_msg = str(e)
        if check_for_drm(error_msg):
            raise HTTPException(status_code=403, detail="DRM_PROTECTED")
        raise HTTPException(status_code=400, detail=error_msg)

def _create_drm_response(info: Dict[str, Any]) -> Dict[str, Any]:
    """إنشاء استجابة للفيديو المحمي بـ DRM"""
    return {
        'title': info.get('title', 'Video'),
        'thumbnail': info.get('thumbnail', ''),
        'duration': float(info.get('duration', 0) or 0),
        'platform': info.get('extractor_key', 'unknown').lower(),
        'download_options': {'hd': None, 'sd': None},
        'is_drm_protected': True,
        'drm_message': '⚠️ هذا الفيديو محمي بـ DRM (Digital Rights Management) ولا يمكن تحميله. هذه تقنية حماية للمحتوى تمنع النسخ والتحميل غير المصرح به.',
        'all_formats_count': 0,
        'is_streaming': False,
        'streaming_warning': None
    }

# --- API Endpoints ---

@app.post("/extract", response_model=ExtractResponse)
async def extract(request: Request, req_body: ExtractRequest):
    client_ip = request.client.host
    if not check_rate_limit(client_ip):
        return ExtractResponse(
            success=False, 
            error="تم تجاوز الحد المسموح. الرجاء الانتظار 10 طلبات كحد أقصى في الدقيقة"
        )
    
    url = str(req_body.url)
    
    # الخطوة 1: التحقق من الروابط المباشرة (جميع الصيغ)
    direct_result = is_direct_video_url(url)
    if direct_result:
        return ExtractResponse(
            success=True,
            data=VideoInfo(**direct_result)
        )
    
    # الخطوة 2: التحقق من روابط البث المباشر HLS/DASH
    streaming_result = is_streaming_url(url)
    if streaming_result:
        data = handle_streaming_url(url, streaming_result)
        return ExtractResponse(
            success=True,
            data=VideoInfo(**data)
        )
    
    # الخطوة 3: محاولة الاستخراج باستخدام yt-dlp
    try:
        data = extract_video_info_generic(url)
        return ExtractResponse(success=True, data=VideoInfo(**data))
    except HTTPException as e:
        if e.detail == "DRM_PROTECTED":
            return ExtractResponse(
                success=False,
                error="هذا الموقع يستخدم تقنية DRM لحماية المحتوى، التحميل غير ممكن. هذه حماية قانونية للمحتوى."
            )
        return ExtractResponse(success=False, error=e.detail)
    except Exception as e:
        return ExtractResponse(success=False, error=str(e))

@app.get("/supported-formats")
async def supported_formats():
    """إرجاع قائمة بجميع الصيغ المدعومة"""
    return {
        "success": True,
        "count": len(ALL_VIDEO_EXTENSIONS),
        "formats": ALL_VIDEO_EXTENSIONS,
        "streaming_formats": HLS_EXTENSIONS + DASH_EXTENSIONS,
        "note": "يدعم السيرفر جميع هذه الصيغ للروابط المباشرة بالإضافة إلى آلاف المواقع عبر yt-dlp"
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "3.0.0",
        "features": {
            "direct_links": len(ALL_VIDEO_EXTENSIONS),
            "streaming_support": True,
            "drm_detection": True,
            "rate_limit": "10 requests/minute"
        }
    }

@app.get("/")
async def index():
    return {
        "message": "CupGet Video Downloader API - Professional Edition",
        "version": "3.0.0",
        "developer": "Professional Video Downloader",
        "supported_formats_count": len(ALL_VIDEO_EXTENSIONS),
        "features": [
            "✅ دعم جميع صيغ الفيديو المباشرة (MP4, MOV, MKV, AVI, WEBM, FLV, WMV, وغيرها)",
            "✅ دعم صيغ HD و Blu-ray (M2TS, TS, VOB, M2V)",
            "✅ دعم الصيغ المتقدمة (HEVC/H.265, VP9, AV1)",
            "✅ دعم روابط البث المباشر HLS (.m3u8) و DASH (.mpd)",
            "✅ دعم آلاف المواقع عبر yt-dlp (يوتيوب، فيسبوك، انستقرام، تيك توك، تويتر)",
            "✅ دعم الروابط العامة والمواقع الإخبارية",
            "✅ كشف الحماية DRM مع رسائل مناسبة",
            "✅ خيارات HD و SD لكل الفيديوهات",
            "✅ نظام حماية من الطلبات المتكررة (Rate Limiting)"
        ],
        "endpoints": {
            "/extract": "POST - استخراج معلومات الفيديو وروابط التحميل",
            "/supported-formats": "GET - عرض جميع الصيغ المدعومة",
            "/health": "GET - التحقق من صحة السيرفر"
        },
        "example_request": {
            "url": "https://example.com/video.mp4"
        }
    }

if __name__ == "__main__":
    import uvicorn
    print(f"""
    ╔══════════════════════════════════════════════════════════════╗
    ║     CupGet Video Downloader API - Professional Edition      ║
    ║                         Version 3.0.0                        ║
    ╠══════════════════════════════════════════════════════════════╣
    ║  🎬 Supported Direct Formats: {len(ALL_VIDEO_EXTENSIONS)} formats      ║
    ║  📡 Streaming Support: HLS (.m3u8) + DASH (.mpd)            ║
    ║  🛡️ DRM Detection: Enabled                                   ║
    ║  🌐 Platform Support: 1000+ sites via yt-dlp                ║
    ╠══════════════════════════════════════════════════════════════╣
    ║  🚀 Server running on: http://0.0.0.0:8000                  ║
    ║  📖 API Docs: http://0.0.0.0:8000/docs                      ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
