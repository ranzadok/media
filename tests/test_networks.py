import json
import pytest
import responses
from publish.networks import TerminalError, RetryableError
from publish.networks import meta, buffer

G = "https://graph.facebook.com/v21.0"
TOKEN = "SECRET-TOKEN-123"
ITEM = {"id": "148-x", "type": "video", "caption": "שלום הלינק בביו", "at": "2026-11-18T19:30:00+02:00"}
URL = ["https://u.github.io/media/m/148/x.mp4"]

@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(meta, "POLL_SECONDS", 0)

@responses.activate
def test_facebook_video_uses_file_url():
    responses.post(f"{G}/111/videos", json={"id": "v1"})
    assert meta.post_facebook("111", TOKEN, ITEM, URL) == "v1"
    body = responses.calls[0].request.body
    assert "file_url" in body and "description" in body

@responses.activate
def test_facebook_image():
    responses.post(f"{G}/111/photos", json={"id": "p1", "post_id": "111_9"})
    assert meta.post_facebook("111", TOKEN, dict(ITEM, type="image"), ["https://x/a.png"]) == "111_9"

@responses.activate
def test_instagram_reel_waits_for_finished():
    responses.post(f"{G}/222/media", json={"id": "c1"})
    responses.get(f"{G}/c1", json={"status_code": "IN_PROGRESS"})
    responses.get(f"{G}/c1", json={"status_code": "IN_PROGRESS"})
    responses.get(f"{G}/c1", json={"status_code": "FINISHED"})
    responses.post(f"{G}/222/media_publish", json={"id": "m1"})
    assert meta.post_instagram("222", TOKEN, ITEM, URL) == "m1"
    assert "REELS" in responses.calls[0].request.body

@responses.activate
def test_instagram_container_error_is_terminal():
    responses.post(f"{G}/222/media", json={"id": "c1"})
    responses.get(f"{G}/c1", json={"status_code": "ERROR", "status": "bad video"})
    with pytest.raises(TerminalError):
        meta.post_instagram("222", TOKEN, ITEM, URL)

@responses.activate
def test_instagram_carousel():
    for i in range(2):
        responses.post(f"{G}/222/media", json={"id": f"k{i}"})
    responses.post(f"{G}/222/media", json={"id": "parent"})
    responses.get(f"{G}/parent", json={"status_code": "FINISHED"})
    responses.post(f"{G}/222/media_publish", json={"id": "m2"})
    assert meta.post_instagram("222", TOKEN, dict(ITEM, type="carousel"), ["https://x/1.png", "https://x/2.png"]) == "m2"
    assert "CAROUSEL" in responses.calls[2].request.body

@responses.activate
def test_auth_error_is_terminal():
    responses.post(f"{G}/111/videos", status=400,
                   json={"error": {"type": "OAuthException", "code": 190, "message": f"bad {TOKEN}"}})
    with pytest.raises(TerminalError) as e:
        meta.post_facebook("111", TOKEN, ITEM, URL)
    assert "הטוקן של מטא פג" in str(e.value)
    assert TOKEN not in str(e.value)

@responses.activate
def test_server_error_is_retryable():
    responses.post(f"{G}/111/videos", status=500, body="oops")
    with pytest.raises(RetryableError):
        meta.post_facebook("111", TOKEN, ITEM, URL)

@responses.activate
def test_tiktok_via_buffer():
    responses.post("https://api.buffer.com", json={"data": {"createPost": {"post": {"id": "b1", "dueAt": "x"}}}})
    assert buffer.post_tiktok("ch1", TOKEN, ITEM, URL) == "b1"
    sent = json.loads(responses.calls[0].request.body)["variables"]["i"]
    assert sent["channelId"] == "ch1" and sent["assets"][0]["video"]["url"] == URL[0]
    assert responses.calls[0].request.headers["Authorization"] == "Bearer " + TOKEN

@responses.activate
def test_buffer_mutation_error_is_terminal():
    responses.post("https://api.buffer.com", json={"data": {"createPost": {"message": "channel disconnected"}}})
    with pytest.raises(TerminalError) as e:
        buffer.post_tiktok("ch1", TOKEN, ITEM, URL)
    assert "channel disconnected" in str(e.value)
