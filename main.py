import uuid
import os
import shutil
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
import yt_dlp

app = FastAPI(title="Advanced Video Downloader API")

# إعداد مجلد التحميل
DOWNLOAD_DIR = Path("temp_downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

class DownloadRequest(BaseModel):
    url: str
    quality: str = "best"  # خيارات: "best", "1080", "720", "480"

class InfoRequest(BaseModel):
    url: str

def cleanup_file(path: Path):
    """وظيفة خلفية لحذف الملف بعد إتمام الإرسال أو الفشل"""
    if path.exists():
        try:
            path.unlink()
            print(f"Removed temporary file: {path}")
        except Exception as e:
            print(f"Error deleting file {path}: {e}")

@app.get("/")
def root():
    return {
        "status": "online",
        "message": "FastAPI Video Downloader is ready",
        "usage": "/info (POST) or /download (POST)"
    }

@app.post("/info")
async def get_video_info(req: InfoRequest):
    ydl_opts = {
        "quiet": True, 
        "no_warnings": True,
        "skip_download": True,
    }
    
    try:
        # تشغيل yt-dlp في Thread منفصل لعدم تجميد التطبيق
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await run_in_threadpool(ydl.extract_info, req.url, download=False)
            return {
                "title": info.get("title", "Unknown"),
                "duration": info.get("duration", 0),
                "thumbnail": info.get("thumbnail", ""),
                "uploader": info.get("uploader", ""),
                "formats": [{"height": f.get("height"), "ext": f.get("ext")} 
                            for f in info.get("formats", []) if f.get("height")]
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not fetch info: {str(e)}")

@app.post("/download")
async def download_video(req: DownloadRequest, background_tasks: BackgroundTasks):
    file_id = str(uuid.uuid4())
    # استخدام قالب لاسم الملف يضمن الامتداد الصحيح
    output_template = str(DOWNLOAD_DIR / f"{file_id}.%(ext)s")

    # تحديد صيغة التحميل
    if req.quality == "best":
        format_selector = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    else:
        format_selector = f"bestvideo[height<={req.quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={req.quality}][ext=mp4]/best"

    ydl_opts = {
        "format": format_selector,
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # التحميل الفعلي للفيديو
            info = await run_in_threadpool(ydl.extract_info, req.url, download=True)
            title = info.get("title", "video")

        # البحث عن الملف الذي تم تحميله (لأن الامتداد قد يختلف قبل الدمج)
        downloaded_files = list(DOWNLOAD_DIR.glob(f"{file_id}.*"))
        if not downloaded_files:
            raise HTTPException(status_code=500, detail="File was not saved correctly")

        file_path = downloaded_files[0]
        safe_title = "".join(c for c in title if c.isalnum() or c in " -_")[:50]
        final_filename = f"{safe_title}.mp4"

        # مولد لقراءة الملف وإرساله كـ Stream
        def file_iterator(path: Path):
            with open(path, "rb") as f:
                yield from f
            # الحذف يتم عبر BackgroundTasks لضمان الأمان

        # إضافة مهمة حذف الملف في الخلفية بعد انتهاء الاستجابة
        background_tasks.add_task(cleanup_file, file_path)

        return StreamingResponse(
            file_iterator(file_path),
            media_type="video/mp4",
            headers={
                "Content-Disposition": f'attachment; filename="{final_filename}"',
                "Access-Control-Expose-Headers": "Content-Disposition"
            }
        )

    except Exception as e:
        # تنظيف أي ملفات قد تكون نُزلت جزئياً في حالة الخطأ
        for partial in DOWNLOAD_DIR.glob(f"{file_id}*"):
            partial.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Download failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
