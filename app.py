"""Single-entrypoint FastAPI site for Vercel. No rewrites or /api Python directory."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import yt_dlp
from fastapi import FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE = Path(__file__).resolve().parent
app = FastAPI(title="ClipPort", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("clipport")
MAX_URL_LENGTH = 2048
MAX_FILE_BYTES = 80 * 1024 * 1024  # Demo guardrail; no large downloads on Vercel
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


class VideoRequest(BaseModel):
    url: str


def normalized_youtube_url(url: str) -> str:
    """Only allow a single public YouTube video, never arbitrary remote URLs."""
    if not isinstance(url, str) or len(url) > MAX_URL_LENGTH:
        raise HTTPException(400, "Please paste a valid YouTube video URL.")
    try:
        parsed = urlsplit(url.strip())
        if parsed.scheme != "https" or parsed.hostname not in YOUTUBE_HOSTS or parsed.username or parsed.password or parsed.port:
            raise ValueError("invalid host")
        if parsed.hostname == "youtu.be":
            video_id = parsed.path.strip("/")
        elif parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        else:
            match = re.fullmatch(r"/(?:shorts|live|embed)/([A-Za-z0-9_-]{11})/?", parsed.path)
            video_id = match.group(1) if match else ""
        if not ID_RE.fullmatch(video_id):
            raise ValueError("invalid id")
        return f"https://www.youtube.com/watch?v={video_id}"
    except (ValueError, TypeError):
        raise HTTPException(400, "Only public YouTube video links are supported (not playlists).")


def extract_video(canonical_url: str) -> dict:
    """Metadata extraction, no writes. Can fail when YouTube blocks Vercel IPs or requires JS challenge runtime."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "ignoreerrors": False,
        "cachedir": False,
        "socket_timeout": 15,
        "retries": 1,
        "extractor_retries": 1,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(canonical_url, download=False)
        if not isinstance(info, dict) or "entries" in info:
            raise ValueError("Could not retrieve a single video.")
        return info
    except yt_dlp.utils.DownloadError as exc:
        log.warning("yt-dlp extraction failed: %s", str(exc)[:250])
        raise HTTPException(502, "YouTube didn't provide accessible video information. Vercel IP restrictions or a missing JS runtime may be responsible.")
    except Exception as exc:
        log.exception("Unexpected extraction failure")
        raise HTTPException(502, "Video information is currently unavailable.") from exc


def progressive_formats(info: dict) -> list[dict]:
    """Formats that already include audio + video. No FFmpeg on Vercel."""
    found = {}
    for f in info.get("formats") or []:
        if not isinstance(f, dict):
            continue
        fmt_url = f.get("url") or ""
        try:
            hostname = urlsplit(fmt_url).hostname or ""
        except ValueError:
            continue
        if (f.get("ext") != "mp4" or f.get("vcodec") in (None, "none") or
                f.get("acodec") in (None, "none") or not f.get("format_id") or
                f.get("protocol") not in ("http", "https") or
                not (hostname == "googlevideo.com" or hostname.endswith(".googlevideo.com"))):
            continue
        filesize = f.get("filesize") or f.get("filesize_approx")
        try:
            if filesize is not None and int(filesize) > MAX_FILE_BYTES:
                continue
        except (ValueError, TypeError):
            filesize = None
        height = int(f.get("height") or 0)
        if height < 1:
            continue
        fid = str(f["format_id"])
        candidate = {
            "id": fid,
            "height": height,
            "label": f"{height}p · MP4",
            "filesize": int(filesize) if filesize else None,
            "note": "Audio included"
        }
        # Prefer smaller progressive MP4s for this lightweight serverless demo.
        old = found.get(height)
        if old is None or (candidate["filesize"] or float("inf")) < (old["filesize"] or float("inf")):
            found[height] = candidate
    return sorted(found.values(), key=lambda f: f["height"], reverse=True)


def selected_format(info: dict, fmt_id: str) -> dict:
    allowed_ids = {item["id"] for item in progressive_formats(info)}
    if fmt_id not in allowed_ids:
        raise HTTPException(400, "That MP4 quality is unavailable. Analyze the URL again.")
    return next(f for f in info["formats"] if str(f.get("format_id")) == fmt_id)


def safe_name(title: str) -> str:
    name = re.sub(r"[^\w .()-]", "", title or "video", flags=re.UNICODE).strip(" .")
    return (name[:80] or "video") + ".mp4"


@app.get("/")
def home():
    return FileResponse(BASE / "static" / "index.html", media_type="text/html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(BASE / "static" / "favicon.svg", media_type="image/svg+xml")


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "clipport", "routes": ["/", "/api/health", "/api/info", "/api/download"]}


@app.post("/api/info")
def info(request: VideoRequest):
    canonical = normalized_youtube_url(request.url)
    data = extract_video(canonical)
    formats = progressive_formats(data)
    return {
        "title": data.get("title") or "Untitled video",
        "channel": data.get("uploader") or data.get("channel") or "YouTube",
        "duration": data.get("duration"),
        "thumbnail": (f"https://i.ytimg.com/vi/{data.get('id')}/hqdefault.jpg"
                      if ID_RE.fullmatch(str(data.get("id", ""))) else None),
        "video_url": canonical,
        "formats": formats,
        "message": None if formats else "No combined MP4 formats were available. Vercel cannot merge separate audio and video tracks.",
    }


@app.get("/api/download")
async def download(url: str = Query(..., max_length=MAX_URL_LENGTH), format_id: str = Query(..., max_length=30)):
    """Best-effort streamed MP4 attachment. Limited by upstream access, bandwidth and Vercel runtime."""
    canonical = normalized_youtube_url(url)
    data = await run_in_threadpool(extract_video, canonical)
    fmt = selected_format(data, format_id)
    upstream_url = fmt["url"]
    parsed = urlsplit(upstream_url)
    if parsed.scheme != "https" or not (parsed.hostname == "googlevideo.com" or parsed.hostname.endswith(".googlevideo.com")):
        raise HTTPException(502, "Upstream media host isn't supported.")
    upstream_headers = {}
    for key, value in (fmt.get("http_headers") or data.get("http_headers") or {}).items():
        if key.lower() in {"user-agent", "referer", "accept", "accept-language"} and isinstance(value, str):
            upstream_headers[key] = value
    # No auto-redirects: only trusted Google video media hosts are fetched.
    client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=False)
    try:
        upstream = await client.send(client.build_request("GET", upstream_url, headers=upstream_headers), stream=True)
        if upstream.status_code not in (200, 206):
            await upstream.aclose()
            await client.aclose()
            raise HTTPException(502, "Video host refused the download. Try another video or run yt-dlp locally.")
        size_header = upstream.headers.get("content-length")
        if size_header and size_header.isdecimal() and int(size_header) > MAX_FILE_BYTES:
            await upstream.aclose()
            await client.aclose()
            raise HTTPException(413, "File is too large for this Vercel demo (80 MB maximum).")
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        await client.aclose()
        log.warning("Upstream stream error: %s", str(exc)[:200])
        raise HTTPException(502, "Could not connect to video media host.") from exc

    async def chunks():
        total = 0
        try:
            async for part in upstream.aiter_bytes(chunk_size=65536):
                total += len(part)
                if total > MAX_FILE_BYTES:
                    log.warning("Stopped oversized stream")
                    break
                yield part
        finally:
            await upstream.aclose()
            await client.aclose()

    file_name = safe_name(data.get("title") or "video").encode("ascii", "ignore").decode("ascii") or "video.mp4"
    return StreamingResponse(chunks(), media_type="video/mp4", headers={
        "Content-Disposition": f'attachment; filename="{file_name}"',
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    })
