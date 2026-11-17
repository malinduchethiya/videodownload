from fastapi.testclient import TestClient
from fastapi import HTTPException
import app as module

client = TestClient(module.app)


def test_home_responds_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "ClipPort" in response.text
    assert "text/html" in response.headers["content-type"]


def test_static_assets():
    r = client.get("/static/app.js")
    assert r.status_code == 200
    assert "checkHealth" in r.text


def test_health_route():
    assert client.get("/api/health").json()["status"] == "ok"


def test_input_validation():
    for bad_url in ["http://youtube.com/watch?v=abcdefghijk", "https://example.com/watch?v=abcdefghijk", "https://youtube.com/playlist?list=xxx", "https://youtube.com/watch?v=wrong", "https://youtube.com.evil.com/watch?v=abcdefghijk"]:
        r = client.post("/api/info", json={"url": bad_url})
        assert r.status_code == 400
    assert module.normalized_youtube_url("https://youtu.be/abcdefghijk?t=30") == "https://www.youtube.com/watch?v=abcdefghijk"


def test_info_with_mock(monkeypatch):
    mock = {"id": "abcdefghijk", "title": "Example clip", "uploader": "Sample channel", "duration": 65, "formats": [
        {"format_id": "18", "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "protocol": "https", "height": 360, "filesize": 1200000, "url": "https://rr1.googlevideo.com/videoplayback?x=1"},
        {"format_id": "137", "ext": "mp4", "vcodec": "avc1", "acodec": "none", "protocol": "https", "height": 1080, "url": "https://rr1.googlevideo.com/videoplayback?x=2"},
    ]}
    monkeypatch.setattr(module, "extract_video", lambda u: mock)
    response = client.post("/api/info", json={"url": "https://youtu.be/abcdefghijk"})
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Example clip"
    assert data["formats"] == [{"id": "18", "height": 360, "label": "360p · MP4", "filesize": 1200000, "note": "Audio included"}]


def test_stream_download_with_mock(monkeypatch):
    import httpx
    mock = {"id": "abcdefghijk", "title": "My sample video", "formats": [
        {"format_id": "18", "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "protocol": "https", "height": 360, "url": "https://rr1.googlevideo.com/videoplayback?x=1"},
    ]}
    monkeypatch.setattr(module, "extract_video", lambda u: mock)
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"simulated mp4 bytes", headers={"content-type": "video/mp4"}))
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))
    r = client.get("/api/download", params={"url": "https://youtu.be/abcdefghijk", "format_id": "18"})
    assert r.status_code == 200
    assert r.content == b"simulated mp4 bytes"
    assert "attachment" in r.headers["content-disposition"]
    assert r.headers["content-type"] == "video/mp4"
