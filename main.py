
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import yt_dlp
import logging
import re
import os
import tempfile
import requests
from datetime import datetime
from urllib.parse import urlparse
import json

# إعداد التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# تكوين CORS - يمكن تعديل origins حسب الحاجة
CORS(app, origins=['*'], supports_credentials=True)

# تكوين معدل الطلبات
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["60 per minute", "1000 per hour"]
)

# إعدادات التطبيق
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # حد أقصى 100MB
app.config['TEMP_FOLDER'] = tempfile.gettempdir()
app.config['DOWNLOAD_TIMEOUT'] = 30  # ثانية

# قائمة المواقع المدعومة (للتوثيق فقط)
SUPPORTED_SITES = [
    "YouTube", "Vimeo", "Dailymotion", "Facebook", "Instagram", "Twitter",
    "TikTok", "Twitch", "SoundCloud", "Bandcamp", "VK", "Bilibili", "Rumble"
]

# ============ دوال مساعدة ============

def sanitize_url(url):
    """تنظيف URL من أي محتوى ضار"""
    if not url:
        return None
    
    # إزالة المسافات
    url = url.strip()
    
    # إضافة البروتوكول إذا لم يكن موجوداً
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # التحقق من صحة URL
    try:
        result = urlparse(url)
        if not result.netloc:
            return None
    except:
        return None
    
    return url

def validate_url(url):
    """التحقق من صحة الرابط"""
    url = sanitize_url(url)
    if not url:
        return False, "Invalid URL format"
    
    # منع الروابط المحلية
    forbidden_domains = ['localhost', '127.0.0.1', '0.0.0.0', '::1']
    parsed = urlparse(url)
    if parsed.netloc in forbidden_domains:
        return False, "Local URLs are not allowed"
    
    return True, url

def get_video_info(url, options=None):
    """استخراج معلومات الفيديو"""
    if options is None:
        options = {}
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'ignoreerrors': True,
        'no_playlist': True,
        'noplaylist': True,
        'timeout': app.config['DOWNLOAD_TIMEOUT'],
    }
    
    # إضافة خيارات إضافية
    ydl_opts.update(options)
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return True, info
    except yt_dlp.utils.UnsupportedError:
        return False, "This website is not supported"
    except yt_dlp.utils.DownloadError as e:
        return False, f"Download error: {str(e)}"
    except yt_dlp.utils.ExtractorError as e:
        return False, f"Extractor error: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error in get_video_info: {str(e)}")
        return False, f"Unexpected error: {str(e)}"

def filter_formats(info):
    """تصفية التنسيقات المتاحة"""
    formats = []
    audio_formats = []
    seen_qualities = set()
    
    for f in info.get("formats", []):
        # التحقق من وجود رابط
        if not f.get("url"):
            continue
        
        # التحقق من وجود فيديو وصوت معاً
        has_video = f.get("vcodec") != "none" and f.get("vcodec") is not None
        has_audio = f.get("acodec") != "none" and f.get("acodec") is not None
        
        # تنسيقات الفيديو مع الصوت
        if has_video and has_audio:
            # تحديد الجودة
            quality = "unknown"
            if f.get("height"):
                quality = f"{f.get('height')}p"
            elif f.get("format_note"):
                quality = f.get("format_note")
            elif f.get("resolution"):
                quality = f.get("resolution")
            
            if quality not in seen_qualities:
                seen_qualities.add(quality)
                
                format_info = {
                    "quality": quality,
                    "ext": f.get("ext", "mp4"),
                    "url": f.get("url"),
                    "filesize": f.get("filesize"),
                    "format_note": f.get("format_note", ""),
                }
                
                # إضافة معلومات إضافية إن وجدت
                if f.get("fps"):
                    format_info["fps"] = f.get("fps")
                if f.get("tbr"):
                    format_info["bitrate"] = round(f.get("tbr"), 1)
                if f.get("width"):
                    format_info["width"] = f.get("width")
                if f.get("height"):
                    format_info["height"] = f.get("height")
                
                formats.append(format_info)
        
        # تنسيقات الصوت فقط
        elif has_audio and not has_video:
            audio_info = {
                "ext": f.get("ext", "m4a"),
                "url": f.get("url"),
                "filesize": f.get("filesize"),
            }
            
            # تحديد جودة الصوت
            if f.get("abr"):
                audio_info["quality"] = f"{f.get('abr')}kbps"
            elif f.get("format_note"):
                audio_info["quality"] = f.get("format_note")
            else:
                audio_info["quality"] = "Audio"
            
            audio_formats.append(audio_info)
    
    # ترتيب التنسيقات حسب الجودة (من الأعلى إلى الأقل)
    def sort_by_quality(f):
        try:
            if "p" in f.get("quality", ""):
                return -int(f["quality"].replace("p", ""))
            return 0
        except:
            return 0
    
    formats.sort(key=sort_by_quality)
    
    return formats, audio_formats

# ============ نقاط النهاية ============

@app.route('/', methods=['GET'])
def index():
    """نقطة النهاية الرئيسية"""
    return jsonify({
        "status": "running",
        "name": "Video Downloader API",
        "version": "1.0.0",
        "supported_sites": SUPPORTED_SITES,
        "endpoints": {
            "/": "GET - API information",
            "/download": "POST/GET - Get video information and formats",
            "/download/direct": "POST - Get direct download URL",
            "/download/audio": "POST - Get audio only URL",
            "/download/file": "POST - Download and serve file",
            "/health": "GET - Health check"
        },
        "limits": {
            "requests_per_minute": 60,
            "max_file_size": "100MB"
        }
    })

@app.route('/health', methods=['GET'])
def health_check():
    """فحص صحة الخادم"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "temp_folder": app.config['TEMP_FOLDER']
    })

@app.route('/download', methods=['POST', 'GET'])
@limiter.limit("30 per minute")
def download():
    """الحصول على معلومات الفيديو والتنسيقات المتاحة"""
    # معالجة الطلب
    if request.method == 'POST':
        data = request.get_json()
        url = data.get("url") if data else None
        options = data.get("options", {}) if data else {}
    else:  # GET
        url = request.args.get("url")
        options = {}
    
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    # التحقق من صحة الرابط
    is_valid, result = validate_url(url)
    if not is_valid:
        return jsonify({"error": result}), 400
    
    url = result
    logger.info(f"Download request for: {url}")
    
    # إعداد خيارات yt-dlp
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'timeout': app.config['DOWNLOAD_TIMEOUT'],
    }
    
    # إضافة خيارات المستخدم
    if options.get("cookies") and os.path.exists(options.get("cookies")):
        ydl_opts['cookiefile'] = options.get("cookies")
    
    if options.get("user_agent"):
        ydl_opts['user_agent'] = options.get("user_agent")
    
    if options.get("proxy"):
        ydl_opts['proxy'] = options.get("proxy")
    
    # استخراج المعلومات
    success, result = get_video_info(url, ydl_opts)
    if not success:
        return jsonify({"error": result}), 400
    
    info = result
    
    # تصفية التنسيقات
    formats, audio_formats = filter_formats(info)
    
    # تجهيز الرد
    response_data = {
        "success": True,
        "title": info.get("title", "Unknown"),
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "channel": info.get("uploader") or info.get("channel"),
        "channel_url": info.get("uploader_url") or info.get("channel_url"),
        "description": info.get("description", "")[:500],  # أول 500 حرف فقط
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "upload_date": info.get("upload_date"),
        "website": info.get("extractor"),
        "formats": formats,
        "audio_formats": audio_formats,
        "total_formats": len(formats) + len(audio_formats)
    }
    
    # إزالة القيم None
    response_data = {k: v for k, v in response_data.items() if v is not None}
    
    return jsonify(response_data)

@app.route('/download/direct', methods=['POST'])
@limiter.limit("20 per minute")
def download_direct():
    """الحصول على رابط تحميل مباشر"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request body"}), 400
    
    url = data.get("url")
    quality = data.get("quality", "best")
    format_type = data.get("format", "video")  # 'video' or 'audio'
    
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    # التحقق من صحة الرابط
    is_valid, result = validate_url(url)
    if not is_valid:
        return jsonify({"error": result}), 400
    
    url = result
    logger.info(f"Direct download request for: {url} (quality: {quality})")
    
    try:
        # إعداد خيارات التنسيق
        if format_type == "audio":
            format_spec = "bestaudio/best"
        elif quality == "best":
            format_spec = "bestvideo+bestaudio/best"
        elif quality == "worst":
            format_spec = "worstvideo+worstaudio/worst"
        else:
            # استخراج الرقم من الجودة (مثلاً "720p" -> 720)
            height = re.sub(r'[^0-9]', '', quality)
            if height:
                format_spec = f'bestvideo[height<={height}]+bestaudio/best[height<={height}]'
            else:
                format_spec = "bestvideo+bestaudio/best"
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': format_spec,
            'noplaylist': True,
            'timeout': app.config['DOWNLOAD_TIMEOUT'],
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # الحصول على رابط التحميل
            download_url = None
            if 'url' in info and info['url']:
                download_url = info['url']
            elif 'formats' in info:
                # البحث عن التنسيق المناسب
                target_height = int(quality.replace("p", "")) if quality != "best" else None
                for f in info['formats']:
                    if f.get('url'):
                        if format_type == "audio" and f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                            download_url = f['url']
                            break
                        elif format_type == "video":
                            if target_height and f.get('height') and int(f['height']) <= target_height:
                                download_url = f['url']
                                break
                            elif not target_height:
                                download_url = f['url']
                                break
            
            if not download_url:
                return jsonify({"error": "No downloadable URL found"}), 500
            
            # تحديد امتداد الملف
            ext = "mp4"
            if format_type == "audio":
                ext = "mp3"
            elif info.get("ext"):
                ext = info["ext"]
            
            return jsonify({
                "success": True,
                "title": info.get("title", "Unknown"),
                "thumbnail": info.get("thumbnail"),
                "download_url": download_url,
                "quality": quality,
                "format_type": format_type,
                "ext": ext,
                "filesize": info.get("filesize")
            })
            
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"Download error: {str(e)}")
        return jsonify({"error": f"Download error: {str(e)}"}), 400
    except yt_dlp.utils.ExtractorError as e:
        logger.error(f"Extractor error: {str(e)}")
        return jsonify({"error": f"Extractor error: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

@app.route('/download/audio', methods=['POST'])
@limiter.limit("20 per minute")
def download_audio():
    """الحصول على رابط تحميل الصوت فقط"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request body"}), 400
    
    url = data.get("url")
    quality = data.get("quality", "best")  # best, medium, low
    
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    # التحقق من صحة الرابط
    is_valid, result = validate_url(url)
    if not is_valid:
        return jsonify({"error": result}), 400
    
    url = result
    logger.info(f"Audio download request for: {url}")
    
    try:
        # إعداد خيارات جودة الصوت
        if quality == "best":
            format_spec = "bestaudio/best"
        elif quality == "medium":
            format_spec = "bestaudio[abr<=128]/bestaudio"
        elif quality == "low":
            format_spec = "bestaudio[abr<=64]/bestaudio"
        else:
            format_spec = "bestaudio/best"
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': format_spec,
            'noplaylist': True,
            'timeout': app.config['DOWNLOAD_TIMEOUT'],
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # البحث عن رابط الصوت
            audio_url = None
            audio_bitrate = None
            
            for f in info.get("formats", []):
                if f.get("acodec") != "none" and f.get("vcodec") == "none" and f.get("url"):
                    audio_url = f.get("url")
                    if f.get("abr"):
                        audio_bitrate = f.get("abr")
                    break
            
            if not audio_url:
                return jsonify({"error": "No audio format found"}), 500
            
            return jsonify({
                "success": True,
                "title": info.get("title", "Unknown"),
                "thumbnail": info.get("thumbnail"),
                "download_url": audio_url,
                "quality": f"{audio_bitrate}kbps" if audio_bitrate else quality,
                "ext": "mp3",
                "duration": info.get("duration"),
                "filesize": info.get("filesize")
            })
            
    except yt_dlp.utils.DownloadError as e:
        return jsonify({"error": f"Download error: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

@app.route('/download/file', methods=['POST'])
@limiter.limit("10 per minute")
def download_file():
    """تحميل الملف مباشرة من الخادم"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request body"}), 400
    
    url = data.get("url")
    quality = data.get("quality", "best")
    
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    # التحقق من صحة الرابط
    is_valid, result = validate_url(url)
    if not is_valid:
        return jsonify({"error": result}), 400
    
    url = result
    
    try:
        # إعداد خيارات التحميل
        if quality == "best":
            format_spec = "bestvideo+bestaudio/best"
        else:
            height = re.sub(r'[^0-9]', '', quality)
            if height:
                format_spec = f'bestvideo[height<={height}]+bestaudio/best[height<={height}]'
            else:
                format_spec = "bestvideo+bestaudio/best"
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': format_spec,
            'outtmpl': os.path.join(app.config['TEMP_FOLDER'], '%(title)s.%(ext)s'),
            'noplaylist': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if os.path.exists(filename):
                return send_file(
                    filename,
                    as_attachment=True,
                    download_name=info.get('title', 'video') + '.' + info.get('ext', 'mp4'),
                    mimetype='video/mp4'
                )
            else:
                return jsonify({"error": "File not found after download"}), 500
                
    except Exception as e:
        logger.error(f"Download file error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/download/info', methods=['POST'])
@limiter.limit("30 per minute")
def get_info_only():
    """الحصول على معلومات فقط بدون تنسيقات"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request body"}), 400
    
    url = data.get("url")
    
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    # التحقق من صحة الرابط
    is_valid, result = validate_url(url)
    if not is_valid:
        return jsonify({"error": result}), 400
    
    url = result
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,  # استخراج معلومات سريعة فقط
        'timeout': app.config['DOWNLOAD_TIMEOUT'],
    }
    
    success, result = get_video_info(url, ydl_opts)
    if not success:
        return jsonify({"error": result}), 400
    
    info = result
    
    response_data = {
        "success": True,
        "title": info.get("title"),
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "channel": info.get("uploader") or info.get("channel"),
        "website": info.get("extractor"),
        "url": info.get("webpage_url") or url
    }
    
    response_data = {k: v for k, v in response_data.items() if v is not None}
    
    return jsonify(response_data)

# ============ معالجة الأخطاء ============

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(429)
def rate_limit_exceeded(error):
    return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({"error": "Internal server error"}), 500

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"error": "Request entity too large"}), 413

# ============ تنظيف الملفات المؤقتة ============

def cleanup_temp_files():
    """تنظيف الملفات المؤقتة القديمة"""
    try:
        current_time = datetime.now().timestamp()
        for filename in os.listdir(app.config['TEMP_FOLDER']):
            filepath = os.path.join(app.config['TEMP_FOLDER'], filename)
            if os.path.isfile(filepath):
                # حذف الملفات الأقدم من ساعة
                if os.path.getmtime(filepath) < current_time - 3600:
                    os.remove(filepath)
                    logger.info(f"Cleaned up temp file: {filename}")
    except Exception as e:
        logger.error(f"Cleanup error: {str(e)}")

# جدولة التنظيف كل 30 دقيقة (في الإنتاج استخدم APScheduler أو celery)
# هنا مجرد مثال بسيط
import threading
import time

def scheduled_cleanup():
    while True:
        time.sleep(1800)  # 30 دقيقة
        cleanup_temp_files()

# تشغيل التنظيف في خيط منفصل
cleanup_thread = threading.Thread(target=scheduled_cleanup, daemon=True)
cleanup_thread.start()

# ============ تشغيل الخادم ============

if __name__ == "__main__":
    # قراءة إعدادات من متغيرات البيئة
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")
    debug = os.environ.get("DEBUG", "False").lower() == "true"
    
    logger.info(f"Starting server on {host}:{port} (debug={debug})")
    
    app.run(
        host=host,
        port=port,
        debug=debug,
        threaded=True
    )
