"""Facebook Page and Instagram publishing via the Meta Graph API."""
import time
import requests
from . import TerminalError, RetryableError, scrub

GRAPH = "https://graph.facebook.com/v21.0"
POLL_SECONDS = 10
POLL_LIMIT = 30  # 30 x 10s = 5 minutes


def _call(method: str, path: str, token: str, **params) -> dict:
    try:
        r = requests.request(method, f"{GRAPH}/{path}", data=params if method == "POST" else None,
                             params=None if method == "POST" else params,
                             headers={"Authorization": "Bearer " + token}, timeout=120)
    except requests.RequestException as e:
        raise RetryableError(scrub(f"מטא לא ענתה: {e}", token)) from None
    if r.status_code >= 500 or r.status_code == 429:
        raise RetryableError(f"מטא החזירה {r.status_code}")
    try:
        body = r.json()
    except ValueError:
        raise RetryableError(f"תשובה לא תקינה ממטא ({r.status_code})") from None
    err = body.get("error")
    if err:
        msg = scrub(str(err.get("message", "")), token)
        if err.get("code") in (190, 102) or err.get("type") == "OAuthException" and err.get("code") in (10, 200):
            raise TerminalError(f"הטוקן של מטא פג או חסרה הרשאה: {msg}")
        if err.get("code") in (4, 17, 32, 613) or err.get("is_transient"):
            raise RetryableError(f"מגבלת קצב של מטא: {msg}")
        raise TerminalError(f"מטא דחתה את הפוסט: {msg}")
    return body


def _text(item: dict) -> str:
    cap = item.get("caption", "")
    link = item.get("link")
    return cap if not link or link in cap else f"{cap}\n{link}"


def post_facebook(page_id: str, token: str, item: dict, media_urls: list[str]) -> str:
    if item["type"] == "video":
        body = _call("POST", f"{page_id}/videos", token, file_url=media_urls[0], description=_text(item))
    elif item["type"] == "image":
        body = _call("POST", f"{page_id}/photos", token, url=media_urls[0], caption=_text(item))
    else:
        raise TerminalError("קרוסלה לא נתמכת בפייסבוק בגרסה הזו")
    return body.get("post_id") or body["id"]


def _wait(container: str, token: str) -> None:
    for _ in range(POLL_LIMIT):
        st = _call("GET", container, token, fields="status_code,status")
        code = st.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise TerminalError(f"אינסטגרם לא הצליחה לעבד את הקובץ: {st.get('status', code)}")
        time.sleep(POLL_SECONDS)
    raise RetryableError("אינסטגרם עדיין מעבדת את הקובץ")


def post_instagram(ig_user_id: str, token: str, item: dict, media_urls: list[str]) -> str:
    cap = item.get("caption", "")
    t = item["type"]
    if t == "video":
        c = _call("POST", f"{ig_user_id}/media", token, media_type="REELS", video_url=media_urls[0],
                  caption=cap, share_to_feed="true")["id"]
    elif t == "image":
        c = _call("POST", f"{ig_user_id}/media", token, image_url=media_urls[0], caption=cap)["id"]
    elif t == "carousel":
        kids = []
        for u in media_urls:
            kw = {"video_url": u, "media_type": "VIDEO"} if u.endswith(".mp4") else {"image_url": u}
            kids.append(_call("POST", f"{ig_user_id}/media", token, is_carousel_item="true", **kw)["id"])
        c = _call("POST", f"{ig_user_id}/media", token, media_type="CAROUSEL",
                  children=",".join(kids), caption=cap)["id"]
    else:
        raise TerminalError(f"סוג לא מוכר: {t}")
    _wait(c, token)
    return _call("POST", f"{ig_user_id}/media_publish", token, creation_id=c)["id"]
