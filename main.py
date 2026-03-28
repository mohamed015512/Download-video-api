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
            'quiet': True,
            'no_warnings': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # تحليل بيانات الفيديو
            info = ydl.extract_info(video_url, download=False)
            
            formats_list = []
            
            # استخراج قائمة الجودات (Formats)
            if 'formats' in info:
                for f in info['formats']:
                    # نختار الروابط اللي فيها فيديو وصوت مع بعض (Direct Links)
                    if f.get('url') and (f.get('vcodec') != 'none' and f.get('acodec') != 'none'):
                        quality = f.get('format_note') or f.get('quality_label') or f"{f.get('height')}p"
                        
                        # إضافة الجودة لو مش متكررة
                        if not any(item['quality'] == quality for item in formats_list):
                            formats_list.append({
                                "quality": quality,
                                "url": f.get('url'),
                                "extension": f.get('ext', 'mp4')
                            })

            # لو ملقاش جودات مفصلة، ياخد أفضل رابط متاح
            if not formats_list:
                download_url = info.get('url')
                if not download_url and 'formats' in info:
                    valid_f = [f for f in info['formats'] if f.get('url')]
                    if valid_f:
                        download_url = valid_f[-1]['url']
                
                if download_url:
                    formats_list.append({
                        "quality": "Best Quality",
                        "url": download_url,
                        "extension": info.get('ext', 'mp4')
                    })

            if not formats_list:
                return jsonify({"status": "error", "message": "Could not find any downloadable formats."}), 404

            # إرسال البيانات للتطبيق
            return jsonify({
                "status": "success",
                "title": info.get('title', 'No Title'),
                "thumbnail": info.get('thumbnail', ''),
                "formats": formats_list
            })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
