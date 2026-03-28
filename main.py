from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

@app.route('/')
def home():
    return "API is running ✅"

@app.route('/get_video', methods=['GET'])
def get_video():
    video_url = request.args.get('url')
    if not video_url:
        return jsonify({"status": "error", "message": "No URL provided"}), 400

    try:
        ydl_opts = {
            'format': 'best',
            'quiet': True,
            'no_warnings': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(video_url, download=False)
            except Exception as e:
                return jsonify({"status": "error", "message": f"Could not extract video: {str(e)}"}), 400

            if info is None:
                return jsonify({"status": "error", "message": "Failed to get video info."}), 400

            download_url = info.get('url')

            if not download_url and 'formats' in info:
                valid_formats = [f for f in info['formats'] if f.get('url')]
                if valid_formats:
                    download_url = valid_formats[-1]['url']

            if not download_url:
                return jsonify({"status": "error", "message": "Could not find a downloadable URL."}), 404

            return jsonify({
                "status": "success",
                "download_url": download_url,
                "title": info.get('title', 'No Title'),
                "thumbnail": info.get('thumbnail', '')
            })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
