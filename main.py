import yt_dlp
from flask import Flask, request, jsonify
import os
import threading
import time
import requests

app = Flask(__name__)

# دالة سحرية تجعل السيرفر لا ينام (Keep Alive)
def keep_awake():
    while True:
        try:
            # السيرفر ينادي نفسه كل 10 دقائق ليبقى نشطاً
            requests.get("https://pureget-api.onrender.com/") 
        except:
            pass
        time.sleep(600)

@app.route('/')
def home():
    return "PureGet Server is Active!"

@app.route('/get_video', methods=['GET'])
def get_video():
    video_url = request.args.get('url')
    if not video_url:
        return jsonify({"status": "error", "message": "No URL"}), 400

    try:
        ydl_opts = {
            'format': 'best',
            'quiet': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...',
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            return jsonify({
                "status": "success",
                "download_url": info.get('url'),
                "title": info.get('title')
            })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # تشغيل منبه الاستيقاظ في الخلفية
    threading.Thread(target=keep_awake, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
