# StreamScope — Vercel yt-dlp proof of concept

A static frontend and a FastAPI Python function using yt-dlp to inspect public YouTube video metadata. **This version does not download files.** It avoids the unreliable approach of redirecting browsers to expiring media URLs.

## Deploy
1. Create a new GitHub repository.
2. Upload **the contents of this folder** to the repository root (not the enclosing folder).
3. In Vercel, import the repository. Framework Preset: **Other**. Root Directory: `./`. Leave build command and output directory blank/default.
4. Deploy. Visit `/` for the homepage and `/api/health` for an API health check.

## Notes
- Vercel serverless functions have runtime and resource limits; cloud IPs may be blocked by video platforms.
- Do not create a `pyproject.toml` for this setup. The Python entrypoint is `api/index.py`, a default-discovery location.
- Use only for content you own or have permission to access, and comply with platform terms.
- For actual downloadable MP4 files, use a separate long-running worker with FFmpeg, temporary storage, rate limiting and authenticated download URLs.
