from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from urllib.parse import urlparse
import yt_dlp

app = FastAPI()

@app.get('/api/health')
def health():
    return {'status': 'ok'}

@app.get('/api/info')
def info(url: str):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'}:
        raise HTTPException(400, 'Enter a valid HTTPS YouTube URL')
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'noplaylist': True, 'skip_download': True, 'socket_timeout': 12}) as ydl:
            data = ydl.extract_info(url, download=False)
        return {'title': data.get('title'), 'duration': data.get('duration'), 'thumbnail': data.get('thumbnail'), 'uploader': data.get('uploader'), 'formats': [{'format_id': f.get('format_id'), 'ext': f.get('ext'), 'height': f.get('height'), 'has_audio': f.get('acodec') != 'none'} for f in data.get('formats', []) if f.get('vcodec') != 'none' and f.get('acodec') != 'none'][-15:]}
    except Exception as exc:
        print('Extraction failed:', type(exc).__name__, str(exc)[:500])
        raise HTTPException(502, 'Unable to retrieve video information. The source may block cloud servers.')
