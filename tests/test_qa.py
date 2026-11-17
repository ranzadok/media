import json
from pathlib import Path
import pytest
from publish.qa import check

ROOT = Path(__file__).resolve().parents[1]
Q148 = json.load(open(ROOT / "apps/148/assets/quotes.json", encoding="utf-8"))[0]

def item(app="148", network="tiktok", caption="ניצוץ אחד לבוקר. הלינק בביו #148", **kw):
    return {"app": app, "network": network, "caption": caption, **kw}

def test_clean_item_passes():
    assert check(item(), ROOT) == []

def test_148_segula_fails():
    errs = check(item(caption="סגולה לפרנסה. הלינק בביו"), ROOT)
    assert any("סגולה" in e for e in errs)

def test_quote_must_match_exactly():
    bad = dict(Q148, text=Q148["text"].replace(",", "", 1))
    assert any("ציטוט" in e for e in check(item(quotes=[bad]), ROOT))
    assert check(item(quotes=[Q148]), ROOT) == []

def test_orange_in_148_script_fails():
    errs = check(item(script={"scenes": [{"color": "#ff8a00"}]}), ROOT)
    assert any("כתום" in e for e in errs)

def test_gold_in_148_is_not_orange():
    assert check(item(script={"c": ["#e0c27d", "#ffd36b"]}), ROOT) == []

def test_beinenu_needs_cta():
    errs = check(item(app="beinenu", caption="עוד ריב על כלום."), ROOT)
    assert any("קריאה לפעולה" in e for e in errs)

@pytest.mark.parametrize("app,cta", [("148", "הלינק בביו"), ("beinenu", "הלינק בביו"), ("bsora", "עקבו")])
def test_available_for_download_banned_everywhere(app, cta):
    errs = check(item(app=app, caption=f"זמין להורדה! {cta}"), ROOT)
    assert any("זמין להורדה" in e for e in errs)

def test_app_store_claim_follows_store_status(tmp_path):
    import shutil
    shutil.copytree(ROOT / "apps", tmp_path / "apps")
    cap = "מהריב לחיבוק. הורדה חינם ב־App Store"
    assert check(item(app="beinenu", caption=cap), tmp_path) == []
    (tmp_path / "apps/beinenu/store.json").write_text('{"apple":"soon","google":"soon"}')
    assert any("App Store" in e for e in check(item(app="beinenu", caption=cap), tmp_path))

def test_instagram_caption_limits():
    tags = " ".join(f"#t{i}" for i in range(6))
    assert any("האשטגים" in e for e in check(item(network="instagram", caption="הלינק בביו " + tags), ROOT))
    long = "הלינק בביו " + "א" * 2200
    assert any("ארוך" in e for e in check(item(network="instagram", caption=long), ROOT))

def test_bsora_only_tiktok():
    errs = check(item(app="bsora", network="instagram", caption="עקבו"), ROOT)
    assert any("רק טיקטוק" in e for e in errs)

def test_unknown_app_fails():
    assert check(item(app="xyz"), ROOT)
