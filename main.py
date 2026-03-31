from fastapi import FastAPI, HTTPException
import yt_dlp
import os

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Seal API is running!"}

@app.get("/fetch")
def fetch_video_info(url: str):
    """
    هذه الدالة تستقبل رابط الفيديو وتعيد معلوماته (العنوان، الصور، الروابط)
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            # استخراج المعلومات بدون تحميل الفيديو
            info = ydl.extract_info(url, download=False)
            
            return {
                "title": info.get('title'),
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration'),
                "uploader": info.get('uploader'),
                # جلب أفضل جودة فيديو متاحة برابط مباشر
                "download_url": info.get('url'), 
                "formats": [
                    {"id": f['format_id'], "ext": f['ext'], "resolution": f.get('resolution')}
                    for f in info.get('formats', []) if f.get('url')
                ]
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # تشغيل السيرفر على بورت 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
