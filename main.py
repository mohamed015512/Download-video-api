from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import yt_dlp
import os
import json
import random
import requests
from functools import wraps
import time
from datetime import datetime

app = Flask(__name__)
CORS(app)  # للسماح لتطبيق Flutter بالتواصل مع السيرفر

# ========== الإعدادات ==========
# قائمة بـ User Agents مختلفة للتناوب
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
]

# مسار ملف الكوكيز (ارفع ملف cookies.txt إلى السيرفر)
COOKIES_FILE = "cookies.txt"

# متغير لتسجيل آخر طلب (للتحقق من صحة السيرفر)
last_request_time = datetime.now()

# ========== دوال مساعدة ==========
def get_random_user_agent():
    """إرجاع User Agent عشوائي"""
    return random.choice(USER_AGENTS)

def get_ydl_opts():
    """إعدادات yt-dlp المتقدمة"""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'user_agent': get_random_user_agent(),
        'socket_timeout': 30,
        'retries': 10,
        'fragment_retries': 10,
        'ignoreerrors': True,
        'nocheckcertificate': True,
        'prefer_insecure': False,
    }
    
    # إضافة الكوكيز إذا كان الملف موجوداً
    if os.path.exists(COOKIES_FILE):
        opts['cookiefile'] = COOKIES_FILE
        print("✅ Cookies file loaded")
    else:
        print("⚠️ No cookies file found. Bot detection may occur.")
    
    return opts

# ========== نقاط النهاية (Endpoints) ==========

@app.route('/', methods=['GET'])
def home():
    """الصفحة الرئيسية - معلومات عامة عن API"""
    return jsonify({
        "status": "success",
        "name": "Cup Video Downloader API",
        "version": "2.0.0",
        "message": "API is running successfully ✅",
        "endpoints": {
            "/health": "GET - Check server health",
            "/analyze": "GET - Analyze video and get direct URL",
            "/download": "GET - Stream video directly (bypass IP-lock)",
            "/info": "GET - Get full video information"
        },
        "server_time": datetime.now().isoformat()
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint لفحص صحة السيرفر - يستخدمه cron-job.org"""
    global last_request_time
    last_request_time = datetime.now()
    
    return jsonify({
        "status": "alive",
        "message": "Server is running",
        "last_ping": last_request_time.isoformat(),
        "uptime_seconds": (datetime.now() - last_request_time).seconds
    }), 200

@app.route('/analyze', methods=['GET'])
def analyze_video():
    """
    تحليل الفيديو وإرجاع أفضل رابط مباشر
    الاستخدام: GET /analyze?url=VIDEO_URL
    """
    video_url = request.args.get('url')
    
    if not video_url:
        return jsonify({
            "status": "error", 
            "message": "No URL provided. Please add ?url=YOUR_VIDEO_URL"
        }), 400

    try:
        print(f"📹 Analyzing: {video_url}")
        ydl_opts = get_ydl_opts()
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # استخراج معلومات الفيديو دون تحميله
            info = ydl.extract_info(video_url, download=False)
            
            # البحث عن أفضل جودة فيديو مع صوت مدمج
            best_video_url = None
            best_quality = None
            best_height = 0
            
            if 'formats' in info:
                for f in info['formats']:
                    # نبحث عن فيديو بصوت وجودة عالية
                    if (f.get('vcodec') != 'none' and 
                        f.get('acodec') != 'none' and
                        f.get('height') and
                        f.get('height') <= 1080):  # حد أقصى 1080p
                        
                        if f.get('height') > best_height:
                            best_video_url = f.get('url')
                            best_quality = f"{f.get('height')}p"
                            best_height = f.get('height')
            
            # إذا لم نجد فيديو بصوت، نستخدم أفضل فيديو متاح
            if not best_video_url:
                best_video_url = info.get('url')
                best_quality = "Default Quality"
            
            # حساب حجم الملف التقريبي
            file_size = 0
            if 'formats' in info:
                for f in info['formats']:
                    if f.get('url') == best_video_url:
                        file_size = f.get('filesize', 0)
                        break
            
            return jsonify({
                "status": "success",
                "title": info.get('title', 'No Title'),
                "thumbnail": info.get('thumbnail', ''),
                "duration": info.get('duration', 0),
                "video_url": best_video_url,
                "quality": best_quality,
                "file_size": file_size,
                "uploader": info.get('uploader', 'Unknown'),
                "view_count": info.get('view_count', 0)
            })

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error: {error_msg}")
        
        # رسائل مخصصة حسب نوع الخطأ
        if "Sign in to confirm" in error_msg or "bot" in error_msg.lower():
            error_msg = "⚠️ YouTube bot detection triggered. Please upload cookies.txt file to the server."
        elif "404" in error_msg:
            error_msg = "❌ Video not found. Please check the URL."
        elif "unavailable" in error_msg.lower():
            error_msg = "❌ This video is unavailable or private."
        
        return jsonify({
            "status": "error",
            "message": error_msg
        }), 500

@app.route('/download', methods=['GET'])
def download_video():
    """
    تحميل مباشر عبر السيرفر (يحل مشكلة IP-Locked)
    الاستخدام: GET /download?url=VIDEO_URL
    """
    video_url = request.args.get('url')
    
    if not video_url:
        return jsonify({"status": "error", "message": "No URL provided"}), 400
    
    def generate():
        """مولد (Generator) لإرسال الفيديو بشكل متقطع"""
        try:
            print(f"📥 Downloading: {video_url}")
            ydl_opts = get_ydl_opts()
            ydl_opts['format'] = 'best[height<=1080]'  # أفضل جودة حتى 1080p
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                video_url_direct = None
                
                # استخراج أفضل رابط مباشر
                if 'formats' in info:
                    best_height = 0
                    for f in info['formats']:
                        if (f.get('vcodec') != 'none' and 
                            f.get('acodec') != 'none' and
                            f.get('height') and
                            f.get('height') <= 1080 and
                            f.get('height') > best_height):
                            video_url_direct = f.get('url')
                            best_height = f.get('height')
                
                if not video_url_direct:
                    video_url_direct = info.get('url')
                
                if not video_url_direct:
                    error_msg = json.dumps({"error": "No video URL found"})
                    yield error_msg.encode()
                    return
                
                # تحميل الفيديو بشكل متقطع وإرساله
                headers = {'User-Agent': get_random_user_agent()}
                
                with requests.get(video_url_direct, headers=headers, stream=True, timeout=60) as r:
                    r.raise_for_status()
                    total_size = int(r.headers.get('content-length', 0))
                    downloaded = 0
                    
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            downloaded += len(chunk)
                            yield chunk
                            
                            # طباعة التقدم (للسيرفر لوغ)
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                if progress % 10 == 0:
                                    print(f"📊 Download progress: {progress:.1f}%")
                    
                    print(f"✅ Download completed: {downloaded / 1024 / 1024:.2f} MB")
                            
        except requests.exceptions.RequestException as e:
            error_msg = json.dumps({"error": f"Network error: {str(e)}"})
            yield error_msg.encode()
        except Exception as e:
            error_msg = json.dumps({"error": str(e)})
            yield error_msg.encode()
    
    # الحصول على عنوان الفيديو للتسمية
    try:
        ydl_opts = get_ydl_opts()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            filename = f"{info.get('title', 'video')[:50]}.mp4"
            # تنظيف اسم الملف من الأحرف غير المسموحة
            filename = "".join(c for c in filename if c.isalnum() or c in ' ._-')
    except:
        filename = "video.mp4"
    
    # إرجاع الفيديو كـ stream مباشر
    return Response(
        generate(), 
        mimetype='video/mp4',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Cache-Control': 'no-cache',
            'Accept-Ranges': 'bytes'
        }
    )

@app.route('/info', methods=['GET'])
def full_info():
    """
    الحصول على معلومات كاملة عن الفيديو (للمطورين)
    الاستخدام: GET /info?url=VIDEO_URL
    """
    video_url = request.args.get('url')
    
    if not video_url:
        return jsonify({"status": "error", "message": "No URL provided"}), 400
    
    try:
        print(f"ℹ️ Getting full info for: {video_url}")
        ydl_opts = get_ydl_opts()
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            
            # تنظيف البيانات لإرسالها
            clean_info = {
                "title": info.get('title'),
                "duration": info.get('duration'),
                "thumbnail": info.get('thumbnail'),
                "uploader": info.get('uploader'),
                "uploader_id": info.get('uploader_id'),
                "upload_date": info.get('upload_date'),
                "view_count": info.get('view_count'),
                "like_count": info.get('like_count'),
                "comment_count": info.get('comment_count'),
                "description": (info.get('description', '')[:500]),  # أول 500 حرف فقط
                "categories": info.get('categories', []),
                "tags": info.get('tags', [])[:10],  # أول 10 هاشتاجات
                "formats": []
            }
            
            if 'formats' in info:
                for f in info['formats']:
                    clean_info['formats'].append({
                        "quality": f.get('format_note') or f"{f.get('height')}p" if f.get('height') else "Audio",
                        "height": f.get('height'),
                        "width": f.get('width'),
                        "has_audio": f.get('acodec') != 'none',
                        "has_video": f.get('vcodec') != 'none',
                        "filesize": f.get('filesize'),
                        "extension": f.get('ext'),
                        "fps": f.get('fps')
                    })
            
            return jsonify({
                "status": "success",
                "data": clean_info
            })
            
    except Exception as e:
        print(f"❌ Error getting info: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/supported-sites', methods=['GET'])
def supported_sites():
    """إرجاع قائمة المواقع المدعومة من yt-dlp"""
    try:
        from yt_dlp.extractor import gen_extractors
        sites = [ie.IE_NAME for ie in gen_extractors() if ie.IE_NAME != 'generic']
        sites = sorted(set(sites))[:50]  # أول 50 موقع
        
        return jsonify({
            "status": "success",
            "total_sites": len(sites),
            "sites": sites
        })
    except:
        return jsonify({
            "status": "success",
            "message": "yt-dlp supports 1000+ sites including YouTube, Facebook, Instagram, TikTok, Twitter, Vimeo, Dailymotion, and more"
        })

# ========== معالجة الأخطاء العامة ==========
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "status": "error",
        "message": "Endpoint not found. Check / for available endpoints"
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "status": "error",
        "message": "Internal server error. Please try again later"
    }), 500

# ========== تشغيل السيرفر ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    print("=" * 50)
    print("🚀 Cup Video Downloader API")
    print("=" * 50)
    print(f"📍 Running on port: {port}")
    print(f"🐛 Debug mode: {debug_mode}")
    print(f"🍪 Cookies file: {'✅ Found' if os.path.exists(COOKIES_FILE) else '❌ Not found'}")
    print("=" * 50)
    print("📌 Available endpoints:")
    print("  GET  /                - API information")
    print("  GET  /health          - Health check")
    print("  GET  /analyze?url=... - Analyze video")
    print("  GET  /download?url=... - Download video")
    print("  GET  /info?url=...    - Full video info")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
