"""ClipPort backend for a persistent Docker web service (Render or equivalent)."""
from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from collections import deque
from pathlib import Path
from threading import Lock
from time import monotonic
from urllib.parse import parse_qs, urlsplit

import yt_dlp
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

log = logging.getLogger("clipport")
logging.basicConfig(level=logging.INFO)

MAX_VIDEO_SECONDS = int(os.getenv("MAX_VIDEO_SECONDS", "1200"))
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "120"))
MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024
ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
VIDEO_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}\Z")
MAX_URL_LENGTH = 2048

app = FastAPI(title="ClipPort Download API", docs_url=None, redoc_url=None)
origin = os.getenv("FRONTEND_ORIGIN", "").strip().rstrip("/")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin] if origin else ["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Small in-process demo rate limit. Not a distributed or production-grade limiter.
_requests: dict[str, deque[float]] = {}
_requests_lock = Lock()
_download_lock = Lock()


class VideoRequest(BaseModel):
    url: str


def canonical_youtube_url(value: str) -> str:
    """Reject arbitrary network destinations; only accept canonical YouTube video IDs."""
    if not isinstance(value, str) or not 0 < len(value) <= MAX_URL_LENGTH:
        raise HTTPException(400, "Paste a valid YouTube video link.")
    try:
        parts = urlsplit(value.strip())
        if (
            parts.scheme != "https"
            or parts.hostname not in ALLOWED_HOSTS
            or parts.username is not None
            or parts.password is not None
            or parts.port is not None
        ):
            raise ValueError("Unsupported URL")
        if parts.hostname == "youtu.be":
            video_id = parts.path.strip("/")
        elif parts.path == "/watch":
            video_id = parse_qs(parts.query).get("v", [""])[0]
        else:
            match = re.fullmatch(r"/(?:shorts|live|embed)/([A-Za-z0-9_-]{11})/?", parts.path)
            video_id = match.group(1) if match else ""
        if not VIDEO_ID_RE.fullmatch(video_id):
            raise ValueError("Invalid video ID")
        return "https://www.youtube.com/watch?v=" + video_id
    except (ValueError, TypeError):
        raise HTTPException(400, "Only individual public YouTube video links are supported.")


def rate_limit(request: Request, limit: int, period: float) -> None:
    ip = request.client.host if request.client else "unknown"
    key = f"{ip}:{limit}:{period}"
    now = monotonic()
    with _requests_lock:
        queue = _requests.setdefault(key, deque())
        while queue and now - queue[0] >= period:
            queue.popleft()
        if len(queue) >= limit:
            raise HTTPException(429, "Too many requests. Try again later.")
        queue.append(now)
        # Bound dictionary growth for demo workloads.
        if len(_requests) > 5000:
            _requests.clear()


def options() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "cachedir": False,
        "socket_timeout": 20,
        "retries": 1,
        "extractor_retries": 1,
    }


def get_video(url: str) -> dict:
    try:
        with yt_dlp.YoutubeDL({**options(), "skip_download": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        if not isinstance(info, dict) or info.get("entries") is not None:
            raise ValueError("No single video was returned")
        seconds = info.get("duration")
        if seconds and float(seconds) > MAX_VIDEO_SECONDS:
            raise HTTPException(413, "This video is too long for the demo downloader.")
        return info
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("yt-dlp metadata extraction failed: %s", str(exc)[:400])
        raise HTTPException(502, "YouTube blocked extraction or no usable video information was returned. Cloud IP restrictions can still apply.") from exc


def available_mp4_heights(info: dict) -> list[int]:
    heights: set[int] = set()
    for f in info.get("formats") or []:
        if not isinstance(f, dict):
            continue
        if f.get("ext") != "mp4" or f.get("vcodec") in (None, "none"):
            continue
        height = f.get("height")
        if isinstance(height, int) and 0 < height <= 4320:
            heights.add(height)
    return sorted(heights, reverse=True)


def clean_filename(title: str) -> str:
    sanitized = re.sub(r"[^\w .()-]", "", title or "video", flags=re.UNICODE).strip(" .")
    return (sanitized[:90] or "video") + ".mp4"


def ascii_header_filename(title: str) -> str:
    name = clean_filename(title)
    name = name.encode("ascii", "ignore").decode("ascii").replace('"', "")
    return name if name != ".mp4" else "video.mp4"


def fetch_mp4(url: str, height: int, destination: Path) -> Path:
    """Download in Render filesystem. ffmpeg merges compatible MP4 video and M4A audio."""
    config = {
        **options(),
        "format": (
            f"bestvideo[ext=mp4][height<={height}]+bestaudio[ext=m4a]/"
            f"best[ext=mp4][height<={height}]"
        ),
        "merge_output_format": "mp4",
        "outtmpl": str(destination / "%(id)s.%(ext)s"),
        "max_filesize": MAX_FILE_BYTES,
        "ffmpeg_location": "/usr/bin",
        "overwrites": False,
    }
    try:
        with yt_dlp.YoutubeDL(config) as ydl:
            result = ydl.extract_info(url, download=True)
            if not isinstance(result, dict):
                raise ValueError("Download returned no video")
    except Exception as exc:
        log.warning("yt-dlp download failed: %s", str(exc)[:400])
        raise HTTPException(502, "Download failed. YouTube may be blocking this server or the selected quality is unavailable.") from exc

    output = destination / f"{result['id']}.mp4"
    if not output.is_file():
        candidates = list(destination.glob("*.mp4"))
        output = candidates[0] if candidates else output
    if not output.is_file() or output.stat().st_size == 0:
        raise HTTPException(502, "No MP4 file was produced by yt-dlp/FFmpeg.")
    if output.stat().st_size > MAX_FILE_BYTES:
        raise HTTPException(413, f"Result exceeds the {MAX_FILE_MB} MB demo file limit.")
    return output


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "deno": bool(shutil.which("deno")),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "yt_dlp": yt_dlp.version.__version__,
    }


@app.post("/api/info")
def info(payload: VideoRequest, request: Request):
    rate_limit(request, limit=12, period=300)
    url = canonical_youtube_url(payload.url)
    result = get_video(url)
    heights = available_mp4_heights(result)
    ident = str(result.get("id") or "")
    return {
        "title": result.get("title") or "Untitled video",
        "channel": result.get("uploader") or result.get("channel") or "YouTube",
        "duration": result.get("duration"),
        "thumbnail": f"https://i.ytimg.com/vi/{ident}/hqdefault.jpg" if VIDEO_ID_RE.fullmatch(ident) else None,
        "video_url": url,
        "formats": [{"id": str(h), "height": h, "label": f"{h}p · MP4", "filesize": None} for h in heights],
        "message": None if heights else "No MP4 video formats are available for this video.",
    }


@app.get("/api/download")
def download(
    request: Request,
    url: str = Query(..., max_length=MAX_URL_LENGTH),
    height: int = Query(..., ge=1, le=4320),
):
    rate_limit(request, limit=5, period=600)
    canonical = canonical_youtube_url(url)
    if not _download_lock.acquire(blocking=False):
        raise HTTPException(429, "The demo downloader is busy. Try again shortly.")

    temp_dir: str | None = None
    try:
        details = get_video(canonical)
        if height not in available_mp4_heights(details):
            raise HTTPException(400, "This video quality is unavailable. Analyze the link again.")
        temp_dir = tempfile.mkdtemp(prefix="clipport-")
        path = fetch_mp4(canonical, height, Path(temp_dir))
        filename = ascii_header_filename(details.get("title") or "video")

        def cleanup():
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            finally:
                _download_lock.release()

        return FileResponse(
            path,
            media_type="video/mp4",
            filename=filename,
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
            background=BackgroundTask(cleanup),
        )
    except Exception:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        _download_lock.release()
        raise
