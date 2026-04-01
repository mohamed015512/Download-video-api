from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict, Any
import yt_dlp
import asyncio
import time
from datetime import datetime

app = FastAPI(title="Video Downloader API", version="1.0.0")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production: specify your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting storage (simple version)
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
    duration: int
    formats: List[VideoFormat]
    platform: str

class ExtractRequest(BaseModel):
    url: HttpUrl

class ExtractResponse(BaseModel):
    success: bool
    data: Optional[VideoInfo] = None
    error: Optional[str] = None

# Rate limiting function
def check_rate_limit(client_ip: str) -> bool:
    current_time = time.time()
    if client_ip not in rate_limit_storage:
        rate_limit_storage[client_ip] = []
    
    # Clean old requests (older than 1 minute)
    rate_limit_storage[client_ip] = [
        timestamp for timestamp in rate_limit_storage[client_ip]
        if current_time - timestamp < 60
    ]
    
    # Max 5 requests per minute
    if len(rate_limit_storage[client_ip]) >= 5:
        return False
    
    rate_limit_storage[client_ip].append(current_time)
    return True

def extract_video_info(url: str) -> Dict[str, Any]:
    """Extract video information using yt-dlp without downloading"""
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'force_json': True,
        'no_color': True,
        'ignoreerrors': True,
        'format': 'bestvideo+bestaudio/best',
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise HTTPException(status_code=400, detail="Failed to extract video info")
            
            # Filter formats
            formats = []
            seen_qualities = set()
            
            for f in info.get('formats', []):
                # Check if format has both video and audio or is a combined format
                has_video = f.get('vcodec') != 'none'
                has_audio = f.get('acodec') != 'none'
                height = f.get('height')
                width = f.get('width')
                format_note = f.get('format_note', '')
                
                # Only include formats with video and audio (or best available)
                if (has_video and has_audio) or (has_video and not has_audio and height):
                    quality = ''
                    if height:
                        quality = f"{height}p"
                    elif format_note:
                        quality = format_note
                    else:
                        quality = 'Unknown'
                    
                    # Avoid duplicates
                    if quality not in seen_qualities:
                        seen_qualities.add(quality)
                        formats.append(VideoFormat(
                            quality=quality,
                            url=f.get('url', f.get('manifest_url', '')),
                            filesize=f.get('filesize'),
                            extension=f.get('ext', 'mp4'),
                            format_note=format_note
                        ))
            
            # Sort formats by quality
            def quality_to_number(q: str) -> int:
                try:
                    return int(q.replace('p', ''))
                except:
                    return 0
            
            formats.sort(key=lambda x: quality_to_number(x.quality), reverse=True)
            
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
            
            return {
                'title': info.get('title', 'Unknown Title'),
                'thumbnail': info.get('thumbnail', ''),
                'duration': info.get('duration', 0),
                'formats': [f.dict() for f in formats],
                'platform': platform
            }
            
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error extracting video: {str(e)}")

@app.post("/extract", response_model=ExtractResponse)
async def extract_video(request: ExtractRequest, background_tasks: BackgroundTasks):
    """
    Extract video information and direct download URLs
    """
    # Get client IP (for rate limiting)
    # In production, get from request.client.host
    client_ip = "default"
    
    # Rate limiting
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute.")
    
    try:
        # Extract video info
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

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
