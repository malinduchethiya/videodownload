"""Local tests use simulated YouTube responses; no internet needed."""
import sys
import types
from pathlib import Path

try:
    import yt_dlp  # noqa
except ModuleNotFoundError:
    sys.modules["yt_dlp"] = types.SimpleNamespace(version=types.SimpleNamespace(__version__="test-stub"))

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as module
from fastapi.testclient import TestClient

client = TestClient(module.app)
VIDEO = "https://youtu.be/abcdefghijk"
MOCK = {
    "id": "abcdefghijk", "title": "My test video", "uploader": "Test Channel", "duration": 68,
    "formats": [
        {"format_id": "18", "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "height": 360},
        {"format_id": "137", "ext": "mp4", "vcodec": "avc1", "acodec": "none", "height": 1080},
        {"format_id": "248", "ext": "webm", "vcodec": "vp9", "acodec": "none", "height": 1080},
    ],
}


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "deno" in r.json() and "ffmpeg" in r.json()


def test_valid_url():
    assert module.canonical_youtube_url(VIDEO) == "https://www.youtube.com/watch?v=abcdefghijk"
    assert module.canonical_youtube_url("https://www.youtube.com/shorts/abcdefghijk") == "https://www.youtube.com/watch?v=abcdefghijk"


def test_invalid_urls():
    bads = [
        "http://youtube.com/watch?v=abcdefghijk",
        "https://youtube.com.evil.com/watch?v=abcdefghijk",
        "https://youtube.com/playlist?list=ABC",
        "https://youtube.com/watch?v=1",
        "https://example.com/?url=https://youtu.be/abcdefghijk",
        "https://127.0.0.1/video",
    ]
    for bad in bads:
        r = client.post("/api/info", json={"url": bad})
        assert r.status_code == 400, (bad, r.text)


def test_info(monkeypatch):
    monkeypatch.setattr(module, "get_video", lambda url: MOCK)
    r = client.post("/api/info", json={"url": VIDEO})
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "My test video"
    assert [f["height"] for f in data["formats"]] == [1080, 360]


def test_download_returns_mp4(monkeypatch):
    monkeypatch.setattr(module, "get_video", lambda url: MOCK)

    def write_fake_mp4(url, height, destination):
        assert height == 360
        dest = destination / "abcdefghijk.mp4"
        dest.write_bytes(b"not-real-mp4-test")
        return dest

    monkeypatch.setattr(module, "fetch_mp4", write_fake_mp4)
    r = client.get("/api/download", params={"url": VIDEO, "height": 360})
    assert r.status_code == 200, r.text
    assert r.content == b"not-real-mp4-test"
    assert "attachment" in r.headers["content-disposition"]
    assert "video/mp4" in r.headers["content-type"]


def test_invalid_quality(monkeypatch):
    monkeypatch.setattr(module, "get_video", lambda url: MOCK)
    r = client.get("/api/download", params={"url": VIDEO, "height": 720})
    assert r.status_code == 400


def test_cors():
    r = client.options("/api/info", headers={
        "Origin": "https://example.vercel.app",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert r.status_code in (200, 400)
