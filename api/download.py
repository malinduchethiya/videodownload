
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from urllib.parse import urlparse
import yt_dlp

app = FastAPI()

@app.get("/api/download")
def download(url: str):
    parsed = urlparse(url)

    allowed_hosts = {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be"
    }

    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
        raise HTTPException(
            status_code=400,
            detail="Invalid YouTube URL"
        )

    try:
        options = {
            "format": "best[ext=mp4]/best",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True
        }

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)

        video_url = info.get("url")

        if not video_url:
            raise ValueError("No video stream available")

        return RedirectResponse(
            url=video_url,
            status_code=302
        )

    except Exception as error:
        print(f"yt-dlp error: {error}")
        raise HTTPException(
            status_code=502,
            detail="Unable to retrieve video stream"
        )
