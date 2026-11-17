# ClipPort — Vercel frontend + Render Docker backend

This is a **two-service project**, built to avoid the failures caused by running yt-dlp and media processing in Vercel Functions.

```
clipport-vercel-render/
├── frontend/                 # Static UI for Vercel
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   ├── config.js             # Update this after Render deployment
│   └── favicon.svg
└── backend/                  # Docker API for Render
    ├── Dockerfile            # Installs Deno, FFmpeg and Python dependencies
    ├── requirements.txt      # Includes yt-dlp[default] / yt-dlp-ejs
    ├── app.py                # FastAPI yt-dlp backend
    └── tests/
```

## 1. GitHub upload

1. Extract the ZIP file.
2. Open your repository: `https://github.com/malinduchethiya/videodownload`.
3. Remove the **old Python/FastAPI deployment files** in the repository root, including `app.py`, `pyproject.toml`, `vercel.json` and any `api/` directory. **Replace them with the contents of this ZIP.**
4. The GitHub repository root must contain `frontend/`, `backend/`, and `README.md`. Do not upload an extra outer folder.
5. Commit the changes.

## 2. Deploy backend on Render (first)

1. Go to <https://dashboard.render.com>.
2. Select **New > Web Service**; connect GitHub, select your `videodownload` repo.
3. Choose **Language: Docker**.
4. Set **Root Directory** to `backend`. Render should discover `backend/Dockerfile` inside that root. If necessary set Dockerfile Path to `./Dockerfile` (path is relative to the root directory).
5. Choose **Free** for small-scale testing, if offered. Free services sleep and do not provide persistent storage.
6. Add environment variable `FRONTEND_ORIGIN` with the EXACT origin of your Vercel site (e.g., `https://your-site.vercel.app`, no slash at the end). If you don't know it yet, leave unset temporarily (allows any origin) and add it after Vercel is deployed.
7. Leave Docker start command unset so Dockerfile's `CMD` controls startup.
8. Deploy. Render provides an HTTPS URL such as `https://clipport-api.onrender.com` (example only).
9. Visit `https://YOUR-RENDER-SERVICE.onrender.com/api/health`. The expected fields are `"status":"ok"`, `"deno":true`, `"ffmpeg":true` and the installed yt-dlp version.

> If Docker build fails, check Render's **Deploy** logs. If health works but YouTube extraction fails, check **Logs**. YouTube may block data-center IP addresses even when Deno and FFmpeg are installed.

## 3. Connect your frontend to Render

Open `frontend/config.js` in GitHub and replace the placeholder with the **actual** Render URL:

```js
window.CLIPPORT_API_URL = "https://YOUR-REAL-RENDER-URL.onrender.com";
```

Commit the change.

## 4. Deploy frontend to Vercel

1. Open your existing Vercel project connected to this GitHub repository.
2. **Settings > Build and Deployment:** change **Root Directory** to **`frontend`**.
3. Set **Framework Preset: Other** (not FastAPI), and remove old custom build command, output directory, or Python entrypoint settings.
4. Redeploy the latest commit using the project Deployment tab if needed.
5. Visit `/` and you should see the ClipPort UI. It now calls the Render API instead of a Vercel Python function.
6. In Render, set/update `FRONTEND_ORIGIN` to your exact final Vercel site origin and redeploy the backend. This avoids browser CORS errors.

## 5. Test

1. Open `https://YOUR-RENDER-URL.onrender.com/api/health` — confirm Deno and FFmpeg are `true`.
2. Open the Vercel website — header should say `Downloader online` once Render wakes up.
3. Paste an **individual public YouTube video URL that you are authorized to download**.
4. Select an offered MP4 quality, then download. The backend temporarily writes a file and delivers it to the browser, then deletes the temporary directory.
5. If the site says `YouTube blocked extraction`, inspect Render runtime logs. The absence of YouTube access from that server is not a Vercel bug.

## Limits and operational cautions

- **Not guaranteed to work for all YouTube videos:** YouTube may restrict Render's outbound IP addresses, require a login, or change its extraction challenges.
- **Free Render** may spin down after 15 idle minutes and take ~1 minute to wake. Downloading big files can time out, run out of disk/memory, or exhaust bandwidth.
- Demo defaults: **20-minute max duration**, **120 MB max final MP4**, **one download at a time** and basic request rate limiting. These are not a replacement for authentication, per-user quotas, abuse controls, or distributed job queues.
- This does **not** use cookies or bypass private video access. Follow platform terms and download only authorized content.
- Deno installed from official `denoland/deno:bin-2.9.8`; yt-dlp-ejs installed with `yt-dlp[default]`; FFmpeg installed through apt. Docker builds need Docker Hub and PyPI access.
- If you want high traffic or 4K, switch to a paid dedicated host, a job queue, temporary object storage and expiring download URLs; don't keep long-running downloads in a free web request.

## Optional local tests (Python)

```sh
cd backend
pip install -r requirements.txt pytest httpx
pytest -q
uvicorn app:app --reload
```

For local development, install Deno and FFmpeg separately (Docker builds install them for the hosted app).

## Troubleshooting guide

| Symptom | What to check |
| --- | --- |
| UI displays but "Set API URL" | `frontend/config.js` still has placeholder |
| Vercel responds 404 | Set Vercel Root Directory to `frontend`, preset Other |
| Backend health 404 | Set Render Root Directory to `backend`, select Docker |
| CORS error in browser | Set Render `FRONTEND_ORIGIN` to the exact Vercel HTTPS origin, without slash |
| `"deno":false` or `"ffmpeg":false` | Render service not using the provided `backend/Dockerfile` |
| YouTube extraction fails | Check Render logs; source may block cloud IP, video may be unavailable |
| HTTP 429 | Demo concurrency/rate limit reached; try later |
| HTTP 413 | Video longer than 20 minutes or exceeds file-size limit |
| Download stalls | Render free sleep/limits, huge file, or upstream failure |
