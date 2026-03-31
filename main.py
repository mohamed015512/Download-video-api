
from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({"status": "running", "message": "Video Downloader API"})

@app.route('/api/info', methods=['POST'])
def get_info():
    try:
        data = request.get_json()
        url = data.get('url') if data else None
        
        if not url:
            return jsonify({"error": "No URL provided"}), 400
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        
        # Get video formats
        formats = []
        seen = set()
        
        for f in info.get('formats', []):
            height = f.get('height')
            if height and height > 0 and f.get('acodec') != 'none':
                quality = f"{height}p"
                if quality not in seen:
                    seen.add(quality)
                    formats.append({
                        "quality": quality,
                        "ext": f.get('ext', 'mp4'),
                        "filesize": f.get('filesize', 0)
                    })
        
        # Sort by quality
        formats.sort(key=lambda x: int(x['quality'].replace('p', '')), reverse=True)
        
        return jsonify({
            "title": info.get('title', 'Unknown'),
            "thumbnail": info.get('thumbnail', ''),
            "duration": info.get('duration', 0),
            "formats": formats
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
