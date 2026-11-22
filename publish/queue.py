"""Publish queue: one JSON file per post under queue/<app>/<id>.json."""
import datetime
import json
import os
import shutil
from pathlib import Path

import requests

from . import guard, qa
from .networks import TerminalError, RetryableError, meta, buffer

MAX_ATTEMPTS = 3
EXT = {".mp4", ".png", ".jpg", ".jpeg"}


class Rejected(Exception):
    pass


class Paused(Exception):
    pass


def _accounts(root: Path) -> dict:
    return json.loads((root / "accounts.json").read_text(encoding="utf-8"))


def media_url(root: Path, path: str) -> str:
    base = _accounts(root)["pages_base"]
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER")
    if owner:
        base = base.replace("OWNER", owner)
    return base + path


def media_live(url: str) -> bool:
    try:
        return requests.head(url, timeout=20, allow_redirects=True).status_code == 200
    except requests.RequestException:
        return False


def _path(root: Path, app: str, iid: str) -> Path:
    return root / "queue" / app / f"{iid}.json"


def _save(root: Path, item: dict) -> None:
    p = _path(root, item["app"], item["id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(item, ensure_ascii=False, indent=1), encoding="utf-8")


def _all(root: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((root / "queue").glob("*/*.json"))]


def _dt(s: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(s).astimezone(guard.IL)


def _iso(dt: datetime.datetime) -> str:
    return dt.astimezone(guard.IL).isoformat(timespec="seconds")


def _slot(root: Path, item: dict, at: datetime.datetime) -> datetime.datetime:
    """First allowed time on a day with no other live item for the same app+network."""
    taken = {_dt(o["at"]).date() for o in _all(root)
             if o["app"] == item["app"] and o["network"] == item["network"]
             and o["id"] != item["id"] and o["status"] in ("queued", "publishing", "published")}
    at = guard.next_allowed(at)
    for _ in range(30):
        if at.date() not in taken:
            return at
        at = guard.next_allowed(at + datetime.timedelta(days=1))
    raise RuntimeError("no free day within 30 days")


def enqueue(root: Path, draft_path: Path, media: list[Path]) -> str:
    root = Path(root)
    if (root / "PAUSE").exists():
        raise Paused("הפרסום עצור (PAUSE)")
    item = json.loads(Path(draft_path).read_text(encoding="utf-8"))
    item.update(status="queued", attempts=0, error=None, remote_id=None)
    errs = qa.check(item, root)
    if not media:
        errs.append("אין קובץ מדיה")
    for m in media:
        if Path(m).suffix.lower() not in EXT:
            errs.append(f"סוג קובץ לא נתמך: {Path(m).name}")
    if errs:
        item.update(status="rejected", error="; ".join(errs), media=[])
        _save(root, item)
        raise Rejected(item["error"])
    rel = []
    for i, m in enumerate(media):
        name = item["id"] + (f"-{i + 1}" if len(media) > 1 else "") + Path(m).suffix.lower()
        dest = root / "m" / item["app"] / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(m, dest)
        rel.append(f"m/{item['app']}/{name}")
    item["media"] = rel
    item["at"] = _iso(_slot(root, item, _dt(item["at"])))
    _save(root, item)
    return item["id"]


def _send_facebook(acc, item, urls):
    return meta.post_facebook(acc["page_id"], os.environ[acc["token_secret"]], item, urls)


def _send_instagram(acc, item, urls):
    return meta.post_instagram(acc["ig_user_id"], os.environ[acc["token_secret"]], item, urls)


def _send_tiktok(acc, item, urls):
    return buffer.post_tiktok(acc["channel_id"], os.environ[acc.get("key_secret", "BUFFER_API_KEY")], item, urls)


def _send(acc, item, urls):
    """Accounts marked "via": "buffer" publish every network through their own Buffer key."""
    if acc.get("via") == "buffer":
        return buffer.post(acc["channel_id"], os.environ[acc.get("key_secret", "BUFFER_API_KEY")],
                           item, urls, service=item["network"])
    return SENDERS[item["network"]](acc, item, urls)


SENDERS = {"facebook": _send_facebook, "instagram": _send_instagram, "tiktok": _send_tiktok}


def _account(root: Path, item: dict) -> dict | None:
    acc = _accounts(root).get(item["app"], {}).get(item["network"])
    if not acc or not any(v for k, v in acc.items() if k not in ("token_secret", "key_secret", "via")):
        return None
    sec = acc.get("token_secret")
    if sec and not os.environ.get(sec):
        return None
    if (acc.get("via") == "buffer" or item["network"] == "tiktok") and not os.environ.get(acc.get("key_secret", "BUFFER_API_KEY")):
        return None
    return acc


def run(root: Path, now: datetime.datetime, on_publishing=None) -> list[str]:
    """Publish every queued item whose time has come. Returns the ids published."""
    root = Path(root)
    if (root / "PAUSE").exists():
        return []
    ready = []
    for item in _all(root):
        if item["status"] == "publishing":  # a previous run died mid-send: never risk a duplicate
            item.update(status="failed", error="ריצה קודמת נקטעה באמצע פרסום. צריך לבדוק ידנית אם עלה")
            _save(root, item)
            continue
        if item["status"] != "queued" or _dt(item["at"]) > now:
            continue
        ok, _ = guard.allowed(now)
        if not ok:
            item["at"] = _iso(guard.next_allowed(now))
            _save(root, item)
            continue
        acc = _account(root, item)
        if acc is None:
            item.update(status="failed", error=f"החשבון של {item['app']} ב־{item['network']} לא מחובר (חסר מזהה או סוד)")
            _save(root, item)
            continue
        urls = [media_url(root, m) for m in item["media"]]
        if not all(media_live(u) for u in urls):
            continue  # GitHub Pages not deployed yet; try next run without counting an attempt
        ready.append((item, acc, urls))

    for item, _, _ in ready:
        item["status"] = "publishing"
        _save(root, item)
    if ready and on_publishing:
        on_publishing([i["id"] for i, _, _ in ready])

    done = []
    for item, acc, urls in ready:
        try:
            item["remote_id"] = _send(acc, item, urls)
            item.update(status="published", error=None, published_at=_iso(now))
            done.append(item["id"])
        except TerminalError as e:
            item.update(status="failed", error=str(e))
        except (RetryableError, Exception) as e:  # unknown errors are treated as temporary
            item["attempts"] = item.get("attempts", 0) + 1
            item.update(status="failed" if item["attempts"] >= MAX_ATTEMPTS else "queued", error=str(e)[:300])
        _save(root, item)
    return done
