
from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend access

@app.route('/')
def test():
    return "Server is running!"

@app.route('/download', methods=['POST', 'GET'])
def download():
    # Handle both POST and GET requests
    if request.method == 'POST':
        data = request.json
        url = data.get("url")
    else:  # GET
        url = request.args.get("url")
    
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    # Configure yt-dlp options
    ydl_opts = {
        'quiet': True,  # Suppress logs
        'no_warnings': True,  # Suppress warnings
        'extract_flat': False,  # Get full info
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        
        # Filter formats: video + audio together
        formats = []
        seen_qualities = set()
        
        for f in info.get("formats", []):
            # Must have video (height), audio (acodec not none), and URL
            if (f.get("height") and 
                f.get("url") and 
                f.get("acodec") != "none" and
                f.get("vcodec") != "none"):
                
                quality = f"{f.get('height')}p"
                
                # Avoid duplicate qualities (keep first found)
                if quality not in seen_qualities:
                    seen_qualities.add(quality)
                    
                    format_info = {
                        "quality": quality,
                        "ext": f.get("ext", "mp4"),
                        "url": f.get("url"),
                        "filesize": f.get("filesize"),
                        "format_note": f.get("format_note", ""),
                        "fps": f.get("fps"),
                        "tbr": f.get("tbr")  # Total bitrate
                    }
                    
                    # Remove None values
                    format_info = {k: v for k, v in format_info.items() if v is not None}
                    formats.append(format_info)
        
        # Sort by quality (highest first)
        formats.sort(key=lambda x: int(x["quality"].replace("p", "")), reverse=True)
        
        # Also provide best audio formats separately (optional)
        audio_formats = []
        for f in info.get("formats", []):
            if (f.get("acodec") != "none" and 
                f.get("vcodec") == "none" and 
                f.get("url")):
                audio_formats.append({
                    "quality": f.get("abr", "unknown") if f.get("abr") else f.get("format_note", "Audio"),
                    "ext": f.get("ext", "m4a"),
                    "url": f.get("url"),
                    "filesize": f.get("filesize")
                })
        
        response_data = {
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),  # 👈 Added thumbnail
            "duration": info.get("duration"),
            "channel": info.get("uploader"),
            "formats": formats,
            "audio_formats": audio_formats
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/download/direct', methods=['POST'])
def download_direct():
    """Alternative endpoint that downloads and streams the file"""
    data = request.json
    url = data.get("url")
    format_quality = data.get("quality")  # e.g., "720p"
    
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': f'bestvideo[height<={format_quality.replace("p", "")}]+bestaudio/best[height<={format_quality.replace("p", "")}]',
            'noplaylist': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            url_info = ydl.process_ie_result(info, download=False)
            
            # Get the direct download URL
            if 'url' in url_info:
                download_url = url_info['url']
            elif 'formats' in url_info and len(url_info['formats']) > 0:
                download_url = url_info['formats'][0]['url']
            else:
                return jsonify({"error": "No downloadable URL found"}), 500
            
            return jsonify({
                "title": info.get("title"),
                "thumbnail": info.get("thumbnail"),  # 👈 Added thumbnail here too
                "download_url": download_url,
                "quality": format_quality,
                "ext": info.get("ext", "mp4")
            })
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
