"""Publishing through Buffer's GraphQL API (TikTok, and Instagram/Facebook for apps routed via Buffer)."""
import datetime
import requests
from . import TerminalError, RetryableError, scrub

API = "https://api.buffer.com"
MUTATION = ("mutation($i:CreatePostInput!){createPost(input:$i){"
            "... on PostActionSuccess{post{id dueAt}} ... on MutationError{message}}}")


CHANNELS = "query($o:OrganizationId!){channels(input:{organizationId:$o}){id name service}}"
ACCOUNT = "query{account{organizations{id name}}}"


def _service_meta(service: str, item: dict) -> dict:
    """Buffer requires a post type for Instagram and Facebook."""
    video = item["type"] == "video"
    if service == "instagram":
        return {"instagram": {"type": "reel" if video else "post", "shouldShareToFeed": True}}
    if service == "facebook":
        return {"facebook": {"type": "reel" if video else "post"}}
    return {}


def _gql(api_key: str, query: str, variables: dict | None = None) -> dict:
    try:
        r = requests.post(API, json={"query": query, "variables": variables or {}},
                          headers={"Authorization": "Bearer " + api_key}, timeout=60)
    except requests.RequestException as e:
        raise RetryableError(scrub(f"Buffer לא ענה: {e}", api_key)) from None
    if r.status_code in (401, 403):
        raise TerminalError("המפתח של Buffer לא תקף")
    if r.status_code >= 500 or r.status_code == 429:
        raise RetryableError(f"Buffer החזיר {r.status_code}")
    body = r.json()
    if body.get("errors"):
        raise TerminalError(scrub("Buffer: " + str(body["errors"])[:300], api_key))
    return body.get("data") or {}


def list_channels(api_key: str) -> list[dict]:
    """[{org, id, name, service}] for every organization the key can see. Ids only, no secrets."""
    out = []
    for org in (_gql(api_key, ACCOUNT).get("account") or {}).get("organizations", []):
        for ch in _gql(api_key, CHANNELS, {"o": org["id"]}).get("channels", []):
            out.append({"org": org["name"], **ch})
    return out


def post(channel_id: str, api_key: str, item: dict, media_urls: list[str], service: str = "tiktok") -> str:
    meta = dict(_service_meta(service, item))
    if item.get("buffer_meta"):
        meta.update(item["buffer_meta"])
    item = dict(item, buffer_meta=meta) if meta else item
    return post_tiktok(channel_id, api_key, item, media_urls)


def post_tiktok(channel_id: str, api_key: str, item: dict, media_urls: list[str]) -> str:
    due = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=2)
    inp = {"channelId": channel_id, "text": item.get("caption", ""), "schedulingType": "automatic",
           "mode": "customScheduled", "dueAt": due.strftime("%Y-%m-%dT%H:%M:%S.000Z")}
    if item["type"] == "video":
        inp["assets"] = [{"video": {"url": media_urls[0]}}]
    else:
        inp["assets"] = [{"image": {"url": u}} for u in media_urls]
    if item.get("buffer_meta"):
        inp["metadata"] = item["buffer_meta"]
    try:
        r = requests.post(API, json={"query": MUTATION, "variables": {"i": inp}},
                          headers={"Authorization": "Bearer " + api_key}, timeout=60)
    except requests.RequestException as e:
        raise RetryableError(scrub(f"Buffer לא ענה: {e}", api_key)) from None
    if r.status_code in (401, 403):
        raise TerminalError("המפתח של Buffer לא תקף")
    if r.status_code >= 500 or r.status_code == 429:
        raise RetryableError(f"Buffer החזיר {r.status_code}")
    body = r.json()
    if body.get("errors"):
        raise TerminalError(scrub("Buffer: " + str(body["errors"])[:300], api_key))
    res = (body.get("data") or {}).get("createPost") or {}
    if "post" in res and res["post"]:
        return res["post"]["id"]
    raise TerminalError("Buffer דחה את הפוסט: " + scrub(str(res.get("message", res)), api_key))
