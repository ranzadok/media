import json, shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pytest
from publish import queue
from publish.networks import TerminalError, RetryableError

IL = ZoneInfo("Asia/Jerusalem")
REPO = Path(__file__).resolve().parents[1]

@pytest.fixture
def root(tmp_path, monkeypatch):
    shutil.copytree(REPO / "apps", tmp_path / "apps")
    acc = json.load(open(REPO / "accounts.json"))
    acc["pages_base"] = "https://ran.github.io/media/"
    acc["148"]["tiktok"]["channel_id"] = "ch148"
    acc["148"]["instagram"]["ig_user_id"] = "ig148"
    (tmp_path / "accounts.json").write_text(json.dumps(acc))
    monkeypatch.setenv("BUFFER_API_KEY", "k")
    monkeypatch.setenv("FB_TOKEN_148", "t")
    monkeypatch.setattr(queue, "media_live", lambda url: True)
    return tmp_path

def draft(root, at="2026-11-18T19:30:00+02:00", network="tiktok", caption="ניצוץ. הלינק בביו", **kw):
    p = root / "d.json"
    p.write_text(json.dumps({"id": "148-2026-11-18-01", "app": "148", "network": network, "type": "video",
                             "caption": caption, "at": at, **kw}, ensure_ascii=False))
    v = root / "v.mp4"; v.write_bytes(b"x")
    return p, [v]

def load(root, iid="148-2026-11-18-01"):
    return json.loads((root / "queue/148" / f"{iid}.json").read_text())

def test_enqueue_copies_media_and_queues(root):
    p, m = draft(root)
    assert queue.enqueue(root, p, m) == "148-2026-11-18-01"
    it = load(root)
    assert it["status"] == "queued" and it["media"] == ["m/148/148-2026-11-18-01.mp4"]
    assert (root / it["media"][0]).exists()

def test_enqueue_friday_moves_to_saturday_night(root):
    p, m = draft(root, at="2026-11-20T14:00:00+02:00")
    queue.enqueue(root, p, m)
    assert load(root)["at"] == "2026-11-21T23:00:00+02:00"

def test_second_item_same_day_moves_to_next_day(root):
    p, m = draft(root)
    queue.enqueue(root, p, m)
    d = json.loads(p.read_text()); d["id"] = "148-2026-11-18-02"; p.write_text(json.dumps(d, ensure_ascii=False))
    queue.enqueue(root, p, m)
    assert load(root, "148-2026-11-18-02")["at"] == "2026-11-19T19:30:00+02:00"

def test_rejected_item_saved_without_media(root):
    p, m = draft(root, caption="סגולה! הלינק בביו")
    with pytest.raises(queue.Rejected):
        queue.enqueue(root, p, m)
    it = load(root)
    assert it["status"] == "rejected" and "סגולה" in it["error"]
    assert not (root / "m").exists()

def test_pause_blocks_enqueue_and_run(root):
    (root / "PAUSE").write_text("")
    p, m = draft(root)
    with pytest.raises(queue.Paused):
        queue.enqueue(root, p, m)
    assert queue.run(root, datetime(2026, 11, 18, 20, tzinfo=IL)) == []

def _queued(root, **kw):
    p, m = draft(root, **kw)
    queue.enqueue(root, p, m)

def test_run_publishes_due_item(root, monkeypatch):
    _queued(root)
    seen = []
    monkeypatch.setitem(queue.SENDERS, "tiktok", lambda acc, item, urls: seen.append(urls) or "b1")
    assert queue.run(root, datetime(2026, 11, 18, 19, 45, tzinfo=IL)) == ["148-2026-11-18-01"]
    it = load(root)
    assert it["status"] == "published" and it["remote_id"] == "b1"
    assert seen == [["https://ran.github.io/media/m/148/148-2026-11-18-01.mp4"]]
    assert queue.run(root, datetime(2026, 11, 18, 20, tzinfo=IL)) == []  # not twice

def test_not_due_is_left(root, monkeypatch):
    _queued(root)
    monkeypatch.setitem(queue.SENDERS, "tiktok", lambda *a: pytest.fail("sent early"))
    queue.run(root, datetime(2026, 11, 18, 19, 0, tzinfo=IL))
    assert load(root)["status"] == "queued"

def test_due_item_inside_window_is_deferred(root, monkeypatch):
    _queued(root, at="2026-11-19T23:50:00+02:00")
    monkeypatch.setitem(queue.SENDERS, "tiktok", lambda *a: pytest.fail("posted on shabbat"))
    queue.run(root, datetime(2026, 11, 20, 12, 10, tzinfo=IL))
    it = load(root)
    assert it["status"] == "queued" and it["at"] == "2026-11-21T23:00:00+02:00"

def test_media_not_live_waits_without_retry_count(root, monkeypatch):
    _queued(root)
    monkeypatch.setattr(queue, "media_live", lambda url: False)
    monkeypatch.setitem(queue.SENDERS, "tiktok", lambda *a: pytest.fail("sent before media live"))
    queue.run(root, datetime(2026, 11, 18, 19, 45, tzinfo=IL))
    it = load(root)
    assert it["status"] == "queued" and it["attempts"] == 0

def test_retryable_three_times_fails(root, monkeypatch):
    _queued(root)
    def boom(*a): raise RetryableError("500")
    monkeypatch.setitem(queue.SENDERS, "tiktok", boom)
    for _ in range(3):
        queue.run(root, datetime(2026, 11, 18, 19, 45, tzinfo=IL))
    it = load(root)
    assert it["status"] == "failed" and it["attempts"] == 3

def test_terminal_fails_at_once(root, monkeypatch):
    _queued(root)
    def boom(*a): raise TerminalError("הטוקן של מטא פג")
    monkeypatch.setitem(queue.SENDERS, "tiktok", boom)
    queue.run(root, datetime(2026, 11, 18, 19, 45, tzinfo=IL))
    it = load(root)
    assert it["status"] == "failed" and "פג" in it["error"]

def test_missing_account_fails_clearly(root, monkeypatch):
    _queued(root, network="facebook")
    queue.run(root, datetime(2026, 11, 18, 19, 45, tzinfo=IL))
    it = load(root)
    assert it["status"] == "failed" and "לא מחובר" in it["error"]

def test_on_publishing_hook_runs_before_send(root, monkeypatch):
    _queued(root)
    order = []
    monkeypatch.setitem(queue.SENDERS, "tiktok", lambda *a: order.append("send") or "b1")
    queue.run(root, datetime(2026, 11, 18, 19, 45, tzinfo=IL),
              on_publishing=lambda ids: order.append(("mark", ids, load(root)["status"])))
    assert order[0] == ("mark", ["148-2026-11-18-01"], "publishing") and order[1] == "send"
