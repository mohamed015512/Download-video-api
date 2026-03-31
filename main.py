
from flask import Flask, request, jsonify, send_file
import yt_dlp
import os
import uuid
import threading
import time
import json

app = Flask(__name__)

# Configuration
DOWNLOAD_FOLDER = "/tmp/downloads"
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

downloads_status = {}

# Enable CORS
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    return response

def format_file_size(bytes):
    if not bytes:
        return "Unknown"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024
    return f"{bytes:.1f} GB"

def download_video_task(download_id, url, quality, is_audio):
    try:
        downloads_status[download_id] = {
            "status": "downloading",
            "progress": 0,
            "title": "",
            "error": None
        }
        
        def progress_hook(d):
            if d['status'] == 'downloading':
                if d.get('total_bytes'):
                    percent = (d['downloaded_bytes'] / d['total_bytes']) * 100
                    downloads_status[download_id]["progress"] = percent
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'progress_hooks': [progress_hook],
            'outtmpl': f'{DOWNLOAD_FOLDER}/{download_id}_%(title)s.%(ext)s',
            'noplaylist': True,
            'format': 'best[height<=720]/best',  # Simple format
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            downloads_status[download_id].update({
                "status": "completed",
                "progress": 100,
                "title": info.get("title"),
                "filename": os.path.basename(filename),
                "filepath": filename
            })
            
    except Exception as e:
        downloads_status[download_id] = {
            "status": "error",
            "error": str(e),
            "progress": 0
        }

@app.route('/')
def test():
    return jsonify({"status": "running", "message": "Video Downloader API"})

@app.route('/api/info', methods=['POST', 'OPTIONS'])
def get_info():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    
    data = request.json
    if not data or not data.get("url"):
        return jsonify({"error": "No URL provided"}), 400
    
    try:
        ydl_opts = {'quiet': True, 'no_warnings': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(data["url"], download=False)
        
        formats = []
        for f in info.get("formats", []):
            if f.get("height") and f.get("acodec") != "none":
                formats.append({
                    "quality": f"{f.get('height')}p",
                    "ext": f.get("ext", "mp4"),
                    "filesize_text": format_file_size(f.get("filesize", 0))
                })
        
        # Remove duplicates
        unique_formats = {}
        for f in formats:
            if f["quality"] not in unique_formats:
                unique_formats[f["quality"]] = f
        
        return jsonify({
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration"),
            "formats": list(unique_formats.values())
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/download', methods=['POST', 'OPTIONS'])
def start_download():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    
    data = request.json
    if not data or not data.get("url"):
        return jsonify({"error": "No URL provided"}), 400
    
    download_id = str(uuid.uuid4())
    thread = threading.Thread(
        target=download_video_task,
        args=(download_id, data["url"], data.get("quality", "720p"), data.get("is_audio", False))
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({"download_id": download_id})

@app.route('/api/status/<download_id>', methods=['GET'])
def get_status(download_id):
    status = downloads_status.get(download_id)
    if not status:
        return jsonify({"error": "Not found"}), 404
    return jsonify(status)

@app.route('/api/file/<download_id>', methods=['GET'])
def get_file(download_id):
    status = downloads_status.get(download_id)
    if not status or status.get("status") != "completed":
        return jsonify({"error": "File not ready"}), 400
    
    filepath = status.get("filepath")
    if not filepath or not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404
    
    return send_file(filepath, as_attachment=True, download_name=status.get("filename"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
