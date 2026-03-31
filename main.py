
from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

@app.route('/')
def test():
    return "Server is running!"

@app.route('/download', methods=['POST'])
def download():
    data = request.json
    url = data.get("url")
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    ydl_opts = {}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        formats = []
        for f in info.get("formats", []):
            if f.get("url"):
                formats.append({
                    "format": f.get("format_note"),
                    "quality": f.get("height"),
                    "url": f.get("url")
                })
        return jsonify({
            "title": info.get("title"),
            "formats": formats
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
