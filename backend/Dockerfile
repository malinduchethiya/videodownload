# Official Deno binary provides the JavaScript runtime yt-dlp needs for YouTube.
FROM denoland/deno:bin-2.9.8 AS deno

FROM python:3.12-slim-bookworm
COPY --from=deno /deno /usr/local/bin/deno

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

ENV PYTHONUNBUFFERED=1 \
    DENO_DIR=/tmp/deno-cache
RUN deno --version && ffmpeg -version | head -n 1
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-10000}"]
