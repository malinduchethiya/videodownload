
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import yt_dlp
import json

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        url = query.get("url", [""])[0]

        parsed = urlparse(url)
        allowed_hosts = {
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "youtu.be"
        }

        if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
            self.send_json(400, {"error": "Enter a valid YouTube URL"})
            return

        try:
            options = {
                "format": "best[ext=mp4]/best",
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
            }

            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=False)
                video_url = info.get("url")

            if not video_url:
                raise ValueError("No downloadable stream found")

            self.send_response(302)
            self.send_header("Location", video_url)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        except Exception:
            self.send_json(502, {
                "error": "Unable to retrieve this video"
            })

    def send_json(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
