"""Automatic brand QA. Replaces Ran's manual approval: an item that fails here is never published."""
import colorsys
import json
import re
from pathlib import Path

RULES = json.load(open(Path(__file__).with_name("rules.json"), encoding="utf-8"))
HEX = re.compile(r"#([0-9a-fA-F]{6})\b")
TAG = re.compile(r"(?<!\w)#\w+")


def _is_orange(hex6: str) -> bool:
    r, g, b = (int(hex6[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return 12 <= h * 360 <= 36 and s > 0.5 and 0.2 < l < 0.85


def _store_claim_errors(caption: str, store: dict) -> list[str]:
    errs = []
    for name, key in (("App Store", "apple"), ("Google Play", "google")):
        if name in caption and "בקרוב" not in caption and store.get(key) != "live":
            errs.append(f"מוזכר {name} כזמין, אבל האפליקציה עוד לא שם")
    return errs


def check(item: dict, root: Path) -> list[str]:
    root = Path(root)
    app, network = item.get("app"), item.get("network")
    if app not in ("148", "beinenu", "bsora"):
        return [f"אפליקציה לא מוכרת: {app}"]
    rules = RULES[app]
    errs: list[str] = []
    caption = item.get("caption") or ""

    if network not in rules["networks"]:
        errs.append("לבשורה יש רק טיקטוק" if app == "bsora" else f"רשת לא מוכרת: {network}")

    for word in RULES["all"]["banned"] + rules["banned"]:
        if word in caption:
            errs.append(f"ביטוי אסור בכיתוב: \"{word}\"")

    if not any(c in caption for c in rules["cta"]):
        errs.append("אין קריאה לפעולה (" + " / ".join(rules["cta"]) + ")")

    store = json.load(open(root / "apps" / app / "store.json", encoding="utf-8"))
    errs += _store_claim_errors(caption, store)

    lim = RULES["limits"].get(network)
    if lim:
        if len(TAG.findall(caption)) > lim["hashtags"]:
            errs.append(f"יותר מ־{lim['hashtags']} האשטגים")
        if len(caption) > lim["chars"]:
            errs.append(f"הכיתוב ארוך מ־{lim['chars']} תווים")

    if rules.get("banned_orange") and item.get("script") is not None:
        blob = json.dumps(item["script"], ensure_ascii=False)
        bad = sorted({h for h in HEX.findall(blob) if _is_orange(h)})
        if bad:
            errs.append("צבע כתום אסור ב־148: " + ", ".join("#" + b for b in bad))

    if item.get("quotes"):
        if app == "148":
            approved = {(q["text"], q.get("author")) for q in
                        json.load(open(root / "apps/148/assets/quotes.json", encoding="utf-8"))}
            for q in item["quotes"]:
                if (q.get("text"), q.get("author")) not in approved:
                    errs.append("ציטוט שלא מופיע מילה במילה ב־quotes.json: " + (q.get("text") or "")[:40])
        else:
            errs.append("ציטוטים מותרים רק ב־148, מקובץ הציטוטים")

    return errs
