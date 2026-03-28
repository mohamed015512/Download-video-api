
from flask import Flask, request, jsonify
import yt_dlp

# إنشاء تطبيق Flask
app = Flask(__name__)

# الصفحة الرئيسية
@app.route('/')
def home():
    return "API is running ✅"

# Endpoint لتحليل الفيديو
@app.route('/get_video', methods=['GET'])
def get_video():
    video_url = request.args.get('url')
    if not video_url:
        return jsonify({"status": "error", "message": "No URL provided"}), 400

    try:
        ydl_opts = {
            'format': 'best',  # أفضل جودة فيديو + صوت
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)

            # محاولة الحصول على رابط مباشر
            download_url = info.get('url')

            # لو الرابط مش موجود في المستوى الأول (مثلاً يوتيوب)، بنفحص formats
            if not download_url and 'formats' in info:
                valid_formats = [f for f in info['formats'] if f.get('url')]
                if valid_formats:
                    # غالباً آخر عنصر هو الأفضل
                    download_url = valid_formats[-1]['url']

            if not download_url:
                return jsonify({"status": "error", "message": "Could not find a downloadable URL"}), 404

            # رجعنا JSON جاهز للتطبيق
            return jsonify({
                "status": "success",
                "download_url": download_url,
                "title": info.get('title', 'Video'),
                "thumbnail": info.get('thumbnail', '')
            })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# لتشغيل السيرفر محلياً
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
