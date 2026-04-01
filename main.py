from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrlfrom typing import List, Optional, Dict, Any
import yt_dlp
import time
from datetime import datetime

app = FastAPI(title="Professional Video Downloader API", version="1.1.0")

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

class VideoFormat(BaseModel):
    quality: str
    url: str
    audio_url: Optional[str] = None  # رابط الصوت المنفصل للدمج
    filesize: Optional[int] = None
    extension: str
    format_note: Optional[str] = None
    has_audio: bool = True

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
            
            # 1. البحث عن أفضل رابط صوت متاح (لعملية الدمج في التطبيق)
            best_audio = None
            audio_only_formats = [f for f in all_formats if f.get('vcodec') == 'none' and f.get('acodec') != 'none']
            if audio_only_formats:
                # نختار أفضل جودة صوت (غالباً m4a لسهولة الدمج)
                best_audio = max(audio_only_formats, key=lambda x: x.get('abr', 0) or 0)
            
            formats_to_return = []
            seen_qualities = set()

            # 2. تصفية ومعالجة روابط الفيديو
            for f in all_formats:
                vcodec = f.get('vcodec', 'none')
                acodec = f.get('acodec', 'none')
                
                if vcodec != 'none': # إذا كان يحتوي على فيديو
                    height = f.get('height')
                    if not height: continue
                    
                    quality = f"{height}p"
                    has_audio = (acodec != 'none' and acodec is not None)
                    
                    # نرسل رابط الصوت إذا كان الفيديو صامتاً (مثل فيديوهات فيسبوك HD)
                    audio_url = None if has_audio else (best_audio['url'] if best_audio else None)

                    # تجنب تكرار نفس الجودة (نأخذ الأفضل)
                    if quality not in seen_qualities or has_audio:
                        seen_qualities.add(quality)
                        formats_to_return.append({
                            'quality': quality,
                            'url': f.get('url'),
                            'audio_url': audio_url,
                            'filesize': f.get('filesize'),
                            'extension': f.get('ext', 'mp4'),
                            'format_note': f.get('format_note', ''),
                            'has_audio': has_audio or (audio_url is not None)
                        })

            # ترتيب الجودات من الأعلى للأقل
            formats_to_return.sort(key=lambda x: int(x['quality'].replace('p','')) if 'p' in x['quality'] else 0, reverse=True)

            return {
                'title': info.get('title', 'Video'),
                'thumbnail': info.get('thumbnail', ''),
                'duration': float(info.get('duration', 0) or 0),
                'formats': formats_to_return,
                'platform': info.get('extractor_key', 'unknown').lower()
            }
            
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- المسارات (Endpoints) ---

@app.post("/extract", response_model=ExtractResponse)
async def extract(request: Request, req_body: ExtractRequest):
    client_ip = request.client.host
    if not check_rate_limit(client_ip):
        return ExtractResponse(success=False, error="Rate limit exceeded. Please wait.")

    try:
        data = extract_video_info(str(req_body.url))
        return ExtractResponse(success=True, data=VideoInfo(**data))
    except Exception as e:
        return ExtractResponse(success=False, error=str(e))

@app.get("/health")
async def health():
    return {"status": "healthy", "time": datetime.now().isoformat()}

@app.get("/")
async def index():
    return {"message": "API is running. Use /extract to get video info."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
