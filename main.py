from flask import Flask, request, jsonify
import yt_dlp
import os

app = Flask(__name__)

# الصفحة الرئيسية للتأكد من عمل السيرفر
@app.route('/')
def home():
    return "Cup Video Downloader API is running ✅"

@app.route('/get_video', methods=['GET'])
def get_video():
    video_url = request.args.get('url')
    
    if not video_url:
        return jsonify({"status": "error", "message": "No URL provided"}), 400

    try:
        # إعدادات yt-dlp لاستخراج البيانات
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # استخراج معلومات الفيديو دون تحميله
            info = ydl.extract_info(video_url, download=False)
            
            # 1. البحث عن أفضل رابط صوت متاح (في حال كان الفيديو صامت)
            best_audio_url = None
            if 'formats' in info:
                # تصفية الروابط التي تحتوي على صوت فقط (audio only)
                audio_formats = [f for f in info['formats'] if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
                if audio_formats:
                    # نأخذ أفضل جودة صوت متاحة
                    best_audio_url = audio_formats[-1].get('url')

            formats_list = []
            
            # 2. استخراج جودات الفيديو المتاحة
            if 'formats' in info:
                for f in info['formats']:
                    # نختار فقط الروابط التي تحتوي على فيديو ولها جودة محددة
                    if f.get('url') and f.get('height'):
                        quality = f.get('format_note') or f"{f.get('height')}p"
                        
                        # التحقق هل هذا الرابط يحتوي على صوت أم صامت؟
                        has_audio = f.get('acodec') != 'none' and f.get('acodec') != 'undefined'
                        
                        formats_list.append({
                            "quality": quality,
                            "url": f.get('url'),
                            "audio_url": None if has_audio else best_audio_url,
                            "extension": f.get('ext', 'mp4')
                        })

            # 3. ترتيب الجودات وتصفية المكرر (من الأعلى للأقل)
            unique_formats = []
            seen_qualities = set()
            # نعكس القائمة لنبدأ بالجودات العالية
            for f in reversed(formats_list):
                if f['quality'] not in seen_qualities:
                    unique_formats.append(f)
                    seen_qualities.add(f['quality'])

            # إذا لم نجد فورمات منظمة، نأخذ الرابط الأساسي الذي توفره المكتبة
            if not unique_formats and info.get('url'):
                unique_formats.append({
                    "quality": "Default Quality",
                    "url": info.get('url'),
                    "audio_url": None,
                    "extension": info.get('ext', 'mp4')
                })

            # إرجاع النتيجة النهائية للتطبيق
            return jsonify({
                "status": "success",
                "title": info.get('title', 'No Title'),
                "thumbnail": info.get('thumbnail', ''),
                "formats": unique_formats
            })

    except Exception as e:
        # في حال حدوث خطأ أثناء التحليل
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

# لتشغيل السيرفر
if __name__ == "__main__":
    # استخدام Port من المتغيرات البيئية ليتوافق مع Render
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
