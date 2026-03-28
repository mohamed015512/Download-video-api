@app.route('/get_video', methods=['GET'])
def get_video():
    video_url = request.args.get('url')
    if not video_url:
        return jsonify({"status": "error", "message": "No URL provided"}), 400

    try:
        ydl_opts = {
            'format': 'best', # بيحاول يجيب أفضل جودة مدمجة (فيديو وصوت)
            'quiet': True,
            'no_warnings': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            
            # محاولة جلب الرابط المباشر
            download_url = info.get('url')
            
            # لو الرابط مش موجود في المستوى الأول (زي يوتيوب)، بندور عليه في الفورمات
            if not download_url and 'formats' in info:
                # بنفلتر الفورمات اللي فيها روابط فعلية ونختار أخر واحدة (غالباً الأفضل)
                valid_formats = [f for f in info['formats'] if f.get('url')]
                if valid_formats:
                    download_url = valid_formats[-1]['url']

            if not download_url:
                return jsonify({"status": "error", "message": "Could not find a downloadable URL"}), 404

            return jsonify({
                "status": "success",
                "download_url": download_url,
                "title": info.get('title', 'Video')
            })
            
    except Exception as e:
        # بنرجع رسالة الخطأ الحقيقية عشان تظهر لك في التطبيق
        return jsonify({"status": "error", "message": str(e)}), 500
