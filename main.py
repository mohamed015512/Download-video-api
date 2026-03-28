from flask import Flask, request, jsonifyimport yt_dlp

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
            # شلنا ignoreerrors عشان نعرف لو فيه خطأ حقيقي حصل
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # محاولة جلب البيانات
            try:
                info = ydl.extract_info(video_url, download=False)
            except Exception as e:
                return jsonify({"status": "error", "message": f"Could not extract video: {str(e)}"}), 400

            # التأكد إن info مش None (ده اللي بيسبب خطأ NoneType)
            if info is None:
                return jsonify({"status": "error", "message": "Failed to get video info from this link."}), 400

            # محاولة الحصول على رابط مباشر
            download_url = info.get('url')

            # لو الرابط مش موجود في المستوى الأول (مثلاً يوتيوب)، بنفحص formats
            if not download_url and 'formats' in info:
                # بنجيب الروابط اللي شغالة فعلاً
                valid_formats = [f for f in info['formats'] if f.get('url')]
                if valid_formats:
                    # بنختار رابط فيه فيديو وصوت مع بعض (أو آخر واحد)
                    download_url = valid_formats[-1]['url']

            if not download_url:
                return jsonify({"status": "error", "message": "Could not find a downloadable URL for this video."}), 404

            return jsonify({
                "status": "success",
                "download_url": download_url,
                "title": info.get('title', 'No Title'),
                "thumbnail": info.get('thumbnail', '')
            })

    except Exception as e:
        # لو حصل أي خطأ غير متوقع
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
