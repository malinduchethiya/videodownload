# ClipPort — single FastAPI app for Vercel

This package is a fresh replacement for the previous broken FastAPI/Vercel configurations.

## Important: why this layout works

Vercel's current FastAPI preset finds the root **`app.py`** module and its top-level **`app = FastAPI()`** instance. It routes **every request** to that ASGI app. That app explicitly handles **`/`**, **`/api/health`**, **`/api/info`**, **`/api/download`**, and serves local assets at **`/static/*`**.

**Do NOT add `vercel.json`, `pyproject.toml`, or an `api/` folder from earlier attempts.** There are no rewrites, alternate Python handlers, or static-build settings in this project.

## Deploy to GitHub and Vercel

1. **Delete all old files** in your GitHub repository, including any old `api/` or `api-disabled/` folder, `pyproject.toml`, `vercel.json`, and old `index.html`.
2. Unzip this package. Upload the **contents** directly to the repository root. `app.py` and `requirements.txt` must be at the root and the `static/` folder must contain its three files.
3. In Vercel, import the repository or let your existing Git-connected project redeploy. Set **Root Directory** to `./`. Set **Framework Preset** to FastAPI (or leave it as Auto if auto-detected). Leave **Build Command** and **Output Directory** **unset**; disable any old custom settings.
4. Once deployed, test `https://YOUR-DEPLOYMENT.vercel.app/api/health`. You should get `{"status":"ok", ...}`.
5. Open `https://YOUR-DEPLOYMENT.vercel.app/`. It should serve the HTML UI.
6. Test with a **public YouTube video you are authorized to download**.

If `/api/health` fails, find **Vercel Dashboard > Project > Logs > Runtime logs** and inspect the Python traceback.

## Local development

Python 3.12+ recommended:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
```

Visit `http://127.0.0.1:8000/` and `http://127.0.0.1:8000/api/health`.

## What works and what doesn't

- The homepage and health route work without connecting to YouTube.
- The app uses `yt-dlp` to inspect **single** public YouTube videos.
- When a **precombined MP4** is available, the download endpoint opens the upstream stream and forwards it with `Content-Disposition: attachment` so the browser can save it. Data is streamed without storing it in the Vercel filesystem.
- This demo has a **maximum 80 MB file** safeguard. Uncertain file sizes may be rejected or streams cut off at that limit. Vercel function timeouts and bandwidth can also stop downloads.
- It **cannot merge** separate high-resolution video and audio streams; there is **no FFmpeg** on Vercel.
- **YouTube can block cloud IPs**, require login, and impose JavaScript challenges. Since November 2025, full YouTube support in yt-dlp relies on a JS runtime like Deno and the EJS scripts. Vercel's Python runtime does **not** guarantee a compatible JS executable. Therefore video extraction may fail even though the deployment and health route work correctly. Installing `yt-dlp[default]` alone does not supply a JS runtime binary.
- For reliable downloads, use `yt-dlp` on your own PC or run it on a separate backend with a JS runtime, FFmpeg, and adequate bandwidth.
- This is a **learning/demo project**, not a production-ready public downloading service. Add authentication, quotas, rate limiting, and abuse protection before opening it broadly.

## Security

Only HTTPS video IDs on specified YouTube domains are accepted and canonicalized. The server will fetch only `*.googlevideo.com` upstream MP4 URLs provided by yt-dlp (no general-purpose proxy). No cookies, credentials, or private videos are supported. Use only for media you have the right to download and comply with applicable service terms.

## Tests

`python -m pytest tests -q` (after installing `pytest`). Tests mock video info; no network or YouTube credentials are needed.
