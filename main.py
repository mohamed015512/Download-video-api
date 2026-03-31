from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import yt_dlp
import uuid
from pathlib import Path

app = FastAPI(title="Video Downloader API")

DOWNLOAD_DIR = Path("/tmp/downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)


class DownloadRequest(BaseModel):
    url: str
    quality: str = "best"


class InfoRequest(BaseModel):
    url: str


@app.get("/")
def root():
    return {"status": "ok", "message": "Video Downloader API is running"}


@app.post("/info")
def get_video_info(req: InfoRequest):
    ydl_opts = {"quiet": True, "no_warnings": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)
            return {
                "title": info.get("title", "Unknown"),
                "duration": info.get("duration", 0),
                "thumbnail": info.get("thumbnail", ""),
                "uploader": info.get("uploader", ""),
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/download")
def download_video(req: DownloadRequest):
    file_id = str(uuid.uuid4())
    output_path = DOWNLOAD_DIR / f"{file_id}.%(ext)s"

    if req.quality == "best":
        format_selector = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    else:
        format_selector = f"bestvideo[height<={req.quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={req.quality}][ext=mp4]/best"

    ydl_opts = {
        "format": format_selector,
        "outtmpl": str(output_path),
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=True)
            title = info.get("title", "video")

        downloaded_files = list(DOWNLOAD_DIR.glob(f"{file_id}.*"))
        if not downloaded_files:
            raise HTTPException(status_code=500, detail="Download failed")

        file_path = downloaded_files[0]

        def file_generator():
            with open(file_path, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    yield chunk
            file_path.unlink(missing_ok=True)

        safe_title = "".join(c for c in title if c.isalnum() or c in " -_")[:50]

        return StreamingResponse(
            file_generator(),
            media_type="video/mp4",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_title}.mp4"',
                "X-File-Name": f"{safe_title}.mp4",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
