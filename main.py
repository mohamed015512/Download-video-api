from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import yt_dlp
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'ignoreerrors': True,
}

@app.get("/")
def root():
    return {"message": "Server is running!"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/info")
def info(url: str):
    try:
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            data = ydl.extract_info(url, download=False)
            return {
                "title": data.get("title", ""),
                "duration": data.get("duration", 0),
                "thumbnail": data.get("thumbnail", ""),
                "uploader": data.get("uploader", "")
            }
    except Exception as e:
        raise HTTPException(400, str(e))

@app.get("/download")
def download(url: str):
    try:
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            data = ydl.extract_info(url, download=False)
            video_url = data.get("url")
            if not video_url and "formats" in data:
                for f in data["formats"]:
                    if f.get("vcodec") != "none":
                        video_url = f.get("url")
                        break
            return {
                "success": True,
                "title": data.get("title", "video"),
                "download_url": video_url
            }
    except Exception as e:
        raise HTTPException(400, str(e))
