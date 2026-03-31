
from flask import Flask, request, jsonify, send_file
import yt_dlp
import os
import re
import uuid
import threading
import time
from datetime import datetime
import requests

app = Flask(__name__)

# Configuration
DOWNLOAD_FOLDER = "/tmp/downloads"  # Use /tmp for cloud platforms
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# Store download progress
downloads_status = {}

# Enable CORS
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

def format_file_size(bytes):
    """Convert bytes to human readable format"""
    if not bytes:
        return "Unknown"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024
    return f"{bytes:.1f} GB"

def download_video_task(download_id, url, quality, is_audio):
    """Background task to download video"""
    try:
        downloads_status[download_id] = {
            "status": "downloading",
            "progress": 0,
            "title": "",
            "error": None
        }
        
        quality_num = quality.replace("p", "") if quality and not is_audio else None
        
        # Define progress hook
        def progress_hook(d):
            if d['status'] == 'downloading':
                if d.get('total_bytes'):
                    percent = (d['downloaded_bytes'] / d['total_bytes']) * 100
                elif d.get('total_bytes_estimate'):
                    percent = (d['downloaded_bytes'] / d['total_bytes_estimate']) * 100
                else:
                    percent = 0
                    
                downloads_status[download_id]["progress"] = percent
                
            elif d['status'] == 'finished':
                downloads_status[download_id]["progress"] = 100
        
        # Configure yt-dlp - بدون FFmpeg
        filename_template = os.path.join(DOWNLOAD_FOLDER, f'{download_id}_%(title)s.%(ext)s')
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'progress_hooks': [progress_hook],
            'outtmpl': filename_template,
            'noplaylist': True,
            'restrictfilenames': True,
        }
        
        if is_audio:
            # For audio, try to get best audio format
            ydl_opts['format'] = 'bestaudio/best'
        else:
            # For video, get best quality available
            if quality_num:
                ydl_opts['format'] = f'bestvideo[height<={quality_num}]+bestaudio/best[height<={quality_num}]'
            else:
                ydl_opts['format'] = 'best[height<=720]'  # Default to 720p
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract info and download
            info = ydl.extract_info(url, download=True)
            
            # Get downloaded file path
            filename = ydl.prepare_filename(info)
            
            # Check if file exists
            if os.path.exists(filename):
                file_size = os.path.getsize(filename)
            else:
                # Try to find the file
                for f in os.listdir(DOWNLOAD_FOLDER):
                    if download_id in f:
                        filename = os.path.join(DOWNLOAD_FOLDER, f)
                        file_size = os.path.getsize(filename)
                        break
                else:
                    filename = None
                    file_size = 0
            
            downloads_status[download_id].update({
                "status": "completed",
                "progress": 100,
                "title": info.get("title"),
                "filename": os.path.basename(filename) if filename else "unknown",
                "filepath": filename,
                "filesize": file_size
            })
            
    except Exception as e:
        downloads_status[download_id] = {
            "status": "error",
            "error": str(e),
            "progress": 0
        }

@app.route('/')
def test():
    return jsonify({
        "status": "running",
        "message": "Video Downloader API is working!",
        "version": "2.0"
    })

@app.route('/api/info', methods=['POST', 'GET', 'OPTIONS'])
def get_info():
    """Get video information and available formats"""
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    
    url = None
    if request.method == 'POST':
        data = request.json
        url = data.get("url") if data else None
    else:
        url = request.args.get("url")
    
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        
        # Filter formats: video + audio together
        formats = []
        seen_qualities = set()
        
        for f in info.get("formats", []):
            if (f.get("height") and 
                f.get("url") and 
                f.get("acodec") != "none" and
                f.get("vcodec") != "none"):
                
                quality = f"{f.get('height')}p"
                
                if quality not in seen_qualities:
                    seen_qualities.add(quality)
                    
                    filesize = f.get("filesize") or f.get("filesize_approx", 0)
                    
                    formats.append({
                        "quality": quality,
                        "ext": f.get("ext", "mp4"),
                        "filesize": filesize,
                        "filesize_text": format_file_size(filesize) if filesize else "Unknown",
                        "fps": f.get("fps"),
                        "format_note": f.get("format_note", "")
                    })
        
        # Sort by quality
        formats.sort(key=lambda x: int(x["quality"].replace("p", "")), reverse=True)
        
        # Audio formats
        audio_formats = []
        for f in info.get("formats", []):
            if (f.get("acodec") != "none" and 
                f.get("vcodec") == "none" and 
                f.get("url")):
                
                filesize = f.get("filesize") or f.get("filesize_approx", 0)
                audio_formats.append({
                    "quality": f"{f.get('abr', '128')}kbps" if f.get('abr') else "Audio",
                    "ext": f.get("ext", "m4a"),
                    "filesize": filesize,
                    "filesize_text": format_file_size(filesize) if filesize else "Unknown"
                })
        
        return jsonify({
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration"),
            "duration_text": f"{info.get('duration', 0) // 60}:{info.get('duration', 0) % 60:02d}",
            "channel": info.get("uploader"),
            "channel_url": info.get("uploader_url"),
            "views": info.get("view_count"),
            "formats": formats,
            "audio_formats": audio_formats
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/download/start', methods=['POST', 'OPTIONS'])
def start_download():
    """Start download in background"""
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    url = data.get("url")
    quality = data.get("quality", "720p")
    is_audio = data.get("is_audio", False)
    
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    # Generate unique download ID
    download_id = str(uuid.uuid4())
    
    # Start download in background thread
    thread = threading.Thread(
        target=download_video_task,
        args=(download_id, url, quality, is_audio)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "download_id": download_id,
        "message": "Download started"
    })

@app.route('/api/download/status/<download_id>', methods=['GET'])
def get_download_status(download_id):
    """Get download progress"""
    status = downloads_status.get(download_id)
    if not status:
        return jsonify({"error": "Download not found"}), 404
    
    return jsonify(status)

@app.route('/api/download/file/<download_id>', methods=['GET'])
def download_file(download_id):
    """Download the actual file after completion"""
    status = downloads_status.get(download_id)
    
    if not status:
        return jsonify({"error": "Download not found"}), 404
    
    if status.get("status") != "completed":
        return jsonify({"error": "Download not completed yet"}), 400
    
    filepath = status.get("filepath")
    filename = status.get("filename")
    
    if not filepath or not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404
    
    try:
        # Send file
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype='video/mp4'
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/download/cleanup/<download_id>', methods=['DELETE'])
def cleanup_download(download_id):
    """Delete downloaded file"""
    status = downloads_status.get(download_id)
    
    if status and status.get("filepath"):
        try:
            if os.path.exists(status["filepath"]):
                os.remove(status["filepath"])
            downloads_status.pop(download_id, None)
            return jsonify({"message": "Cleaned up successfully"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    return jsonify({"message": "Already cleaned up"})

@app.route('/api/platforms', methods=['GET'])
def get_supported_platforms():
    """Return list of supported platforms"""
    platforms = [
        {"name": "YouTube", "icon": "youtube", "domains": ["youtube.com", "youtu.be"]},
        {"name": "TikTok", "icon": "tiktok", "domains": ["tiktok.com"]},
        {"name": "Facebook", "icon": "facebook", "domains": ["facebook.com", "fb.watch"]},
        {"name": "Instagram", "icon": "instagram", "domains": ["instagram.com"]},
        {"name": "Twitter", "icon": "twitter", "domains": ["twitter.com", "x.com"]},
        {"name": "Vimeo", "icon": "vimeo", "domains": ["vimeo.com"]},
    ]
    return jsonify(platforms)

# Cleanup old downloads every hour
def cleanup_old_downloads():
    """Remove files older than 1 hour"""
    while True:
        time.sleep(3600)  # Every hour
        try:
            for filename in os.listdir(DOWNLOAD_FOLDER):
                filepath = os.path.join(DOWNLOAD_FOLDER, filename)
                if os.path.isfile(filepath):
                    # Remove files older than 1 hour
                    if time.time() - os.path.getctime(filepath) > 3600:
                        os.remove(filepath)
        except:
            pass

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_old_downloads, daemon=True)
cleanup_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
