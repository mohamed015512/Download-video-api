from flask import Flask
import yt_dlp

app = Flask(__name__)

@app.route('/')
def test():
    return "Server is running!"

@app.route('/test_download')
def test_download():
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # مثال
    ydl_opts = {}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return f"Video title: {info['title']}"
    
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
