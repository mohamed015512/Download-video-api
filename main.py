from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict, Any
import yt_dlp
import time
from datetime import datetime

app = FastAPI(title="Video Downloader API", version="1.0.0")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting storage
rate_limit_storage: Dict[str, List[float]] = {}

# Models
class VideoFormat(BaseModel):
    quality: str
    url: str
    filesize: Optional[int] = None
    extension: str
    format_note: Optional[str] = None

class VideoInfo(BaseModel):
    title: str
    thumbnail: str
    duration: float
    formats: List[VideoFormat]
    platform: str

class ExtractRequest(BaseModel):
    url: HttpUrl

class ExtractResponse(BaseModel):
    success: bool
    data: Optional[VideoInfo] = None
    error: Optional[str] = None

def check_rate_limit(client_ip: str) -> bool:
    current_time = time.time()
    if client_ip not in rate_limit_storage:
        rate_limit_storage[client_ip] = []
    
    rate_limit_storage[client_ip] = [
        timestamp for timestamp in rate_limit_storage[client_ip]
        if current_time - timestamp < 60
    ]
    
    if len(rate_limit_storage[client_ip]) >= 5:
        return False
    
    rate_limit_storage[client_ip].append(current_time)
    return True

def extract_video_info(url: str) -> Dict[str, Any]:
    """Extract video information using yt-dlp without downloading"""
    
    # ✅ تحسين إعدادات yt-dlp للحصول على فيديو مع صوت
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'force_json': True,
        'no_color': True,
        'ignoreerrors': True,
        # ✅ إعدادات للحصول على فيديو مع صوت
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'merge_output_format': 'mp4',
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'geo_bypass': True,
        'socket_timeout': 30,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise HTTPException(status_code=400, detail="Failed to extract video info")
            
            # ✅ تحسين فلترة الفورمات - اختيار الفورمات التي تحتوي على فيديو وصوت
            formats = []
            seen_qualities = set()
            
            # محاولة الحصول على الفورمات المدمجة (video+audio)
            for f in info.get('formats', []):
                has_video = f.get('vcodec') != 'none'
                has_audio = f.get('acodec') != 'none'
                height = f.get('height')
                format_note = f.get('format_note', '')
                
                # ✅ الأفضلية للفورمات التي تحتوي على فيديو وصوت معاً
                if has_video and has_audio:
                    quality = ''
                    if height:
                        quality = f"{height}p"
                    elif format_note:
                        quality = format_note
                    else:
                        quality = 'Unknown'
                    
                    if quality not in seen_qualities:
                        seen_qualities.add(quality)
                        formats.append({
                            'quality': quality,
                            'url': f.get('url', f.get('manifest_url', '')),
                            'filesize': f.get('filesize'),
                            'extension': f.get('ext', 'mp4'),
                            'format_note': format_note
                        })
            
            # ✅ إذا لم نجد فورمات مدمجة، نستخدم أفضل فورمات فيديو + أفضل فورمات صوت
            if not formats:
                # البحث عن أفضل فورمات فيديو
                video_formats = [f for f in info.get('formats', []) if f.get('vcodec') != 'none']
                audio_formats = [f for f in info.get('formats', []) if f.get('acodec') != 'none']
                
                if video_formats and audio_formats:
                    # اختيار أفضل فورمات فيديو
                    best_video = max(video_formats, key=lambda x: x.get('height', 0) or 0)
                    best_audio = max(audio_formats, key=lambda x: x.get('abr', 0) or 0)
                    
                    height = best_video.get('height')
                    quality = f"{height}p" if height else "Best"
                    
                    formats.append({
                        'quality': quality,
                        'url': best_video.get('url', ''),
                        'filesize': best_video.get('filesize'),
                        'extension': 'mp4',
                        'format_note': 'Video only (audio will be downloaded separately in app)'
                    })
            
            # Sort formats by quality
            def quality_to_number(q: str) -> int:
                try:
                    return int(q.replace('p', ''))
                except:
                    return 0
            
            formats.sort(key=lambda x: quality_to_number(x['quality']), reverse=True)
            
            # Determine platform
            platform = 'unknown'
            if 'youtube.com' in url or 'youtu.be' in url:
                platform = 'youtube'
            elif 'instagram.com' in url:
                platform = 'instagram'
            elif 'twitter.com' in url or 'x.com' in url:
                platform = 'twitter'
            elif 'tiktok.com' in url:
                platform = 'tiktok'
            
            duration = info.get('duration', 0)
            if duration is None:
                duration = 0
            
            return {
                'title': info.get('title', 'Unknown Title'),
                'thumbnail': info.get('thumbnail', ''),
                'duration': float(duration),
                'formats': formats,
                'platform': platform
            }
            
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error extracting video: {str(e)}")

@app.post("/extract", response_model=ExtractResponse)
async def extract_video(request: ExtractRequest):
    """Extract video information and direct download URLs"""
    client_ip = "default"
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute.")
    
    try:
        video_data = extract_video_info(str(request.url))
        
        return ExtractResponse(
            success=True,
            data=VideoInfo(**video_data)
        )
        
    except HTTPException as e:
        return ExtractResponse(
            success=False,
            error=e.detail
        )
    except Exception as e:
        return ExtractResponse(
            success=False,
            error=f"Unexpected error: {str(e)}"
        )

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Video Downloader API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
