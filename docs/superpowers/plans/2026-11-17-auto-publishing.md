# פרסום אוטומטי מלא — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** כל פוסט שהסוכן היומי מפיק עובר בדיקה אוטומטית, נכנס לתור, ומתפרסם לבד בטיקטוק, באינסטגרם ובפייסבוק, בלי אישור של רן ובלי תלות במק.

**Architecture:** ריפו ציבורי `media` ב־GitHub מחזיק שלושה דברים: מנוע הסרטונים, חומרי המותג ותור פרסום (קובץ JSON לכל פוסט). הקבצים מוגשים מ־GitHub Pages. הסוכן היומי בענן מפיק, מריץ `python -m publish enqueue` ודוחף לריפו. GitHub Actions רץ כל 15 דקות ומפרסם פריטים שהגיע זמנם: פייסבוק ואינסטגרם דרך Meta Graph API, טיקטוק דרך Buffer GraphQL.

**שינוי מול מסמך העיצוב:** האינסטגרם עובר דרך Graph API ב־Actions ולא דרך Supermetrics. הסיבה: זה אותו טוקן של מטא שכבר נדרש לפייסבוק, ואין תלות בתוכנית של Supermetrics. כל הקריאות לרשתות יוצאות מ־Actions, כי הענן של הסוכן לא מגיע לשרתים של Buffer ומטא.

**Tech Stack:** Python 3.12, pytest, ‏`requests`, ‏`pyluach`, GitHub Actions, GitHub Pages, Meta Graph API v21.0, Buffer GraphQL (`https://api.buffer.com`).

**Spec:** `docs/superpowers/specs/2026-11-17-social-agency-design.md`

## Global Constraints
- **חלון אסור:** אין פרסום משישי 12:00 עד מוצאי שבת 23:00. בחג (יו״ט, ישראל) אין פרסום עד 23:00. בערב חג אין פרסום מ־12:00. אזור זמן `Asia/Jerusalem`. הבדיקה רצה פעמיים: בזמן ההכנסה לתור ובזמן הפרסום.
- **קצב:** לכל היותר פריט אחד ביום לכל צמד (app, network).
- **מזהי אפליקציות:** `148`, `beinenu`, `bsora`. התיקיות: `apps/148`, `apps/beinenu`, `apps/bsora`.
- **רשתות:** `tiktok`, `instagram`, `facebook`. בשורה: `tiktok` בלבד.
- **סודות:** כל מפתח נשמר כ־GitHub Secret ונקרא ממשתני סביבה. אף מפתח לא מודפס, לא נכתב ללוג ולא נכנס לקומיט.
- **קריאה לפעולה:** בכל כיתוב יש קישור עם `utm_source=<network>&utm_campaign=<item id>`, או "הלינק בביו" בטיקטוק ובאינסטגרם, ואז ה־UTM נכנס לשדה `link`.
- **"זמין להורדה":** אסור, חוץ מבינינו, שבה מותר "הורדה חינם ב־App Store". ‏`apps/<id>/store.json` הוא המקור: ‎`{"apple":"live"|"soon","google":"live"|"soon"}`.
- **מתג עצירה:** כשקיים הקובץ `PAUSE` בשורש הריפו, אין הכנסה לתור ואין פרסום.

## Review Focus
1. **פריט מתוזמן לשבת שהתעכב:** פריט ששובץ לחמישי 23:50, ו־Actions הריץ אותו רק בשישי 12:10. מצופה: לא מתפרסם, נדחה למוצאי שבת 23:00 ואילך. (Task 4, ‏`test_due_item_inside_window_is_deferred`)
2. **הקובץ עוד לא עלה ל־Pages:** Pages מתעדכן באיחור של עד כמה דקות אחרי הדחיפה. מצופה: לפני הפרסום יש בדיקת HEAD לכתובת, ואם היא לא 200 הפריט נשאר `queued` בלי לספור ניסיון. (Task 4, ‏`test_media_not_live_waits_without_retry_count`)
3. **שתי ריצות של Actions בו־זמנית:** מצופה: אין פרסום כפול. מוגדר `concurrency: publish` והסטטוס `publishing` נכתב ונדחף לפני הקריאה לרשת. (Task 5)
4. **כיתוב באינסטגרם מעל 2,200 תווים או עם יותר מ־5 האשטגים:** מצופה: נדחה כבר בבדיקה, לא נכשל בזמן הפרסום. (Task 2, ‏`test_instagram_caption_limits`)
5. **טוקן פג או נשלל:** מצופה: הפריט מסומן `failed` עם הודעה ברורה בעברית. ריצת הערב של המנכ״ל מדווחת על זה. אין לולאת ניסיונות. (Task 3, ‏`test_auth_error_is_terminal`)

---

### Task 1: הריפו, המנוע, החומרים ושומר השבת

**Files:**
- Create: `media/` (ריפו ציבורי `<user>/media`), ‏`media/engine/` (העתק של `מנוע/video/*` ו־`מנוע/fonts/*` מהמק), ‏`media/apps/{148,beinenu,bsora}/{brand.md,store.json,assets/*}` (העתק של `מותג.md` ושל `חומרים/` לכל אפליקציה)
- Create: `media/apps/bsora/assets/daily.json`: מערך `DAILY` ו־`AREAS` מתוך הארטיפקט של בשורה (`ea92c401-…`), כדי שמשפטי המזלות יילקחו מהאפליקציה עצמה.
- Create: `media/publish/__init__.py`, ‏`media/publish/guard.py`, ‏`media/tests/test_guard.py`, ‏`media/requirements.txt` (`requests`, ‏`pyluach`, ‏`pytest`)
- Modify: `media/engine/render.py`: ‏`ROOT` מצביע על `apps/`, ובמקום שם התיקייה בעברית מקבל מזהה (`"app": "148"`).

**Interfaces:**
- Produces: `guard.allowed(dt: datetime) -> tuple[bool, str]` (‏dt מודע לאזור זמן, ומומר ל־Asia/Jerusalem); ‏`guard.next_allowed(dt: datetime) -> datetime` (הרגע המותר הראשון ב־dt או אחריו, בצעדים של 15 דקות).

- [ ] **Step 1: Write failing tests** in `tests/test_guard.py`
  - `allowed(Fri 2026-11-20 11:59 IL)` מחזיר True; ‏`allowed(Fri 12:00)` מחזיר False; ‏`allowed(Sat 2026-11-21 22:59)` מחזיר False; ‏`allowed(Sat 23:00)` מחזיר True.
  - חנוכה הוא לא יו״ט: `allowed(2026-12-07 10:00)` מחזיר True.
  - פסח א׳ 2027 (‏2027-04-22): ‏`allowed(2027-04-21 12:30)` מחזיר False (ערב חג); ‏`allowed(2027-04-22 22:00)` מחזיר False; ‏`allowed(2027-04-22 23:00)` מחזיר True.
  - `next_allowed(Fri 2026-11-20 13:00)` מחזיר את `2026-11-21 23:00` IL.
- [ ] **Step 2:** Run `pytest tests/test_guard.py -v`. Expected: FAIL (module missing)
- [ ] **Step 3:** Implement `guard.py` by moving the logic from `מנוע/buffer.py`, with one change: if `pyluach` is missing, raise `ImportError` instead of silently allowing.
- [ ] **Step 4:** Run `pytest tests/test_guard.py -v`. Expected: PASS
- [ ] **Step 5:** Copy the engine and assets. Render `engine/examples/148_משפט-אחד.json` with `--sheet`. Expected: an image of 4 frames with the logo and the screen, as on the Mac.
- [ ] **Step 6:** Enable GitHub Pages (branch `main`, root). Add `.nojekyll`. Check that `https://<user>.github.io/media/apps/148/assets/logo.png` returns 200.
- [ ] **Step 7:** Commit `feat: media repo with engine, brand assets and shabbat guard`

### Task 2: הבדיקה האוטומטית (QA)

**Files:**
- Create: `media/publish/qa.py`, ‏`media/publish/rules.json`, ‏`media/tests/test_qa.py`

**Interfaces:**
- Consumes: `apps/<id>/store.json`, ‏`apps/148/assets/quotes.json`, ‏`apps/bsora/assets/daily.json`
- Produces: `qa.check(item: dict, root: Path) -> list[str]`. מחזירה רשימה של כשלים בעברית; רשימה ריקה פירושה עבר. בודקת את `caption`, ‏`script` (ה־JSON של הסרטון, אם יש) ו־`quotes` (רשימת `{text, author}` שהופיעו).

`rules.json`, לכל אפליקציה:
- `banned`: ביטויים אסורים.
  - כולם: `"זמין להורדה"`, ‏`"הכי טוב"`, ‏`"מובטח"`.
  - 148: `"סגולה"`, ‏`"ישועה"`, ‏`"הלכה:"`, ‏`"מותר"`, ‏`"אסור"`.
  - בינינו: `"טיפול"`, ‏`"מטפל"`, ‏`"ירפא"`, ‏`"מרפא"`.
  - בשורה: `"צפוי לך"`, ‏`"יקרה"`, ‏`"תזכה"`, ‏`"מזל רע"`, ‏`"מסוכן"`.
- `banned_colors`: ב־148 כל גוון כתום (hex שה־hue שלו 15°–45° וה־saturation שלו מעל 0.5, בתוך script/theme).
- `cta`: חובה שאחד מהם יופיע בכיתוב.
  - 148: `"הלינק בביו"`.
  - בינינו: `"App Store"` או `"הלינק בביו"`.
  - בשורה: `"הלינק בביו"` או `"עקבו"`.
- `max_hashtags`: ‏instagram 5, ‏tiktok 6, ‏facebook 3. ‏`max_caption`: ‏instagram 2200, ‏tiktok 2200, ‏facebook 5000.

- [ ] **Step 1: Write failing tests**
  - כיתוב של 148 עם "סגולה" נכשל עם הודעה שמכילה "סגולה".
  - ציטוט של 148 שאינו מופיע ב־`quotes.json` **בדיוק** (גם הבדל של פסיק אחד) נכשל.
  - ציטוט שמופיע בדיוק עובר.
  - script של 148 עם `#ff8a00` נכשל ("כתום").
  - כיתוב של בינינו בלי קריאה לפעולה נכשל.
  - "זמין להורדה" נכשל בכל אפליקציה.
  - כיתוב של בינינו עם "הורדה חינם ב־App Store" עובר כש־`store.json.apple == "live"`, ונכשל כש־`"soon"`.
  - `test_instagram_caption_limits`: שישה האשטגים, או 2,201 תווים, נכשלים.
  - פריט לבשורה ברשת `instagram` נכשל ("לבשורה יש רק טיקטוק").
- [ ] **Step 2:** Run `pytest tests/test_qa.py -v`. Expected: FAIL
- [ ] **Step 3:** Implement `check()`.
- [ ] **Step 4:** Run `pytest tests/test_qa.py -v`. Expected: PASS
- [ ] **Step 5:** Commit `feat: automatic brand QA replaces manual approval`

### Task 3: הלקוחות של הרשתות

**Files:**
- Create: `media/publish/networks/{__init__,meta,buffer}.py`, ‏`media/tests/test_networks.py` (HTTP מדומה עם `responses` או monkeypatch על `requests`)

**Interfaces:**
- Produces:
  - `meta.post_facebook(page_id: str, token: str, item: dict, media_urls: list[str]) -> str`
    - וידאו: ‏`POST /{page_id}/videos` עם `file_url` ו־`description`.
    - תמונה: ‏`POST /{page_id}/photos` עם `url` ו־`caption`.
    - מחזירה את מזהה הפוסט.
  - `meta.post_instagram(ig_user_id: str, token: str, item: dict, media_urls: list[str]) -> str`
    - וידאו: יוצרים container עם `media_type=REELS` ו־`video_url`.
    - תמונה: ‏`image_url`.
    - קרוסלה: ילדים עם `is_carousel_item=true`.
    - אחרי זה בודקים כל 10 שניות, עד 5 דקות, ש־`status_code == FINISHED`, ואז קוראים ל־`media_publish`.
    - מחזירה את media id.
  - `buffer.post_tiktok(channel_id: str, api_key: str, item: dict, media_urls: list[str]) -> str`: ‏`createPost` עם `mode: "shareNow"` ו־`assets.video.url`. מחזירה את post id.
  - `networks.TerminalError(Exception)`: שגיאת הרשאה, טוקן פג או מדיה שנדחתה. אין טעם לנסות שוב.
  - `networks.RetryableError(Exception)`: שגיאת 5xx, חריגה ממגבלת קצב או timeout.
- Graph API base: `https://graph.facebook.com/v21.0`.

- [ ] **Step 1: Write failing tests**
  - פייסבוק עם וידאו שולח `file_url` ומחזיר id.
  - אינסטגרם עם reel מחכה ל־`FINISHED` (שתי תשובות `IN_PROGRESS` ואז `FINISHED`) ואז מפרסם.
  - `ERROR` ב־container זורק `TerminalError`.
  - טיקטוק שולח `channelId` ו־`assets[0].video.url`.
  - `test_auth_error_is_terminal`: ‏Graph מחזיר `OAuthException code 190`, וזה זורק `TerminalError` עם הודעה שמכילה "הטוקן של מטא פג".
  - תשובת 500 זורקת `RetryableError`.
  - אף הודעת שגיאה לא מכילה את הטוקן.
- [ ] **Step 2:** Run `pytest tests/test_networks.py -v`. Expected: FAIL
- [ ] **Step 3:** Implement. The Buffer GraphQL call follows the format in `מנוע/buffer.py`.
- [ ] **Step 4:** Run `pytest tests/test_networks.py -v`. Expected: PASS
- [ ] **Step 5:** Commit `feat: meta and buffer publishing clients`

### Task 4: התור: הכנסה ופרסום

**Files:**
- Create: `media/publish/queue.py`, ‏`media/publish/__main__.py`, ‏`media/tests/test_queue.py`
- Create: `media/accounts.json`. אין בו סודות, רק מיפוי: ‎`{"148":{"facebook":{"page_id":"…","token_secret":"FB_TOKEN_148"},"instagram":{"ig_user_id":"…","token_secret":"FB_TOKEN_148"},"tiktok":{"channel_id":"…"}}, "beinenu":{…}, "bsora":{"tiktok":{…}}}`

**פורמט פריט:** `queue/<app>/<id>.json`
```json
{"id":"148-2026-11-18-01","app":"148","network":"instagram","type":"video|image|carousel",
 "media":["m/148/2026-11-18-01.mp4"],"caption":"…","link":"https://148morelight.com/?utm_source=instagram&utm_campaign=148-2026-11-18-01",
 "at":"2026-11-18T19:30:00+02:00","status":"queued|publishing|published|failed|rejected",
 "attempts":0,"error":null,"remote_id":null,"script":{…},"quotes":[…]}
```

**Interfaces:**
- Consumes: `guard.allowed`, ‏`guard.next_allowed`, ‏`qa.check`, ‏`meta.*`, ‏`buffer.post_tiktok`, ‏`TerminalError`, ‏`RetryableError`
- Produces:
  - CLI `python -m publish enqueue <draft.json> <media files…>`.
    - פריט שנכשל בבדיקה נשמר עם `status:"rejected"` ו־`error` שמפרט את הכשלים. ה־exit code הוא 2.
    - פריט שעבר: הקבצים מועתקים ל־`m/<app>/`, וה־`at` מוזז ל־`next_allowed` אם צריך. אם כבר יש פריט ל־(app, network) באותו יום, הפריט עובר ליום המותר הבא, באותה שעה. ה־exit code הוא 0, והמזהה מודפס.
  - CLI `python -m publish run --now <iso?>`: מפרסם כל פריט `queued` שה־`at` שלו ≤ now.
    - כשקיים `PAUSE` לא מפרסם כלום.
    - אם השעה אסורה, דוחה את `at` ל־`next_allowed`.
    - בודק HEAD לכל כתובת מדיה.
    - כותב `publishing`, ואחר כך `published` עם `remote_id`, או `failed` עם `error`.
    - `RetryableError` מעלה את `attempts`. אחרי 3 ניסיונות הסטטוס הופך ל־`failed`.
  - `queue.media_url(path: str) -> str` = `https://<user>.github.io/media/` + path. ה־user נקרא מ־`GITHUB_REPOSITORY_OWNER` או מ־`accounts.json.pages_base`.

- [ ] **Step 1: Write failing tests**
  - `enqueue` לשישי 14:00 מוזז למוצאי שבת 23:00.
  - פריט שני לאותו יום, app ו־network עובר למחר.
  - פריט שנכשל בבדיקה נשמר כ־`rejected` והקבצים שלו לא מועתקים.
  - `PAUSE` חוסם גם את `enqueue` וגם את `run`.
  - `test_due_item_inside_window_is_deferred`: ‏`at` = חמישי 23:50, ‏now = שישי 12:10. אחרי הריצה הסטטוס `queued` ו־`at` = שבת 23:00.
  - `test_media_not_live_waits_without_retry_count`: ‏HEAD מחזיר 404, ואחרי הריצה הסטטוס `queued` ו־`attempts == 0`.
  - `RetryableError` שלוש פעמים מוביל ל־`failed`.
  - `TerminalError` מוביל ל־`failed` מיד.
  - פריט `published` לא מתפרסם שוב.
- [ ] **Step 2:** Run `pytest tests/test_queue.py -v`. Expected: FAIL
- [ ] **Step 3:** Implement `queue.py` and `__main__.py`. Tokens are read from `os.environ[account.token_secret]`; the Buffer key from `BUFFER_API_KEY`.
- [ ] **Step 4:** Run `pytest -v` on the whole suite. Expected: PASS
- [ ] **Step 5:** Commit `feat: publish queue with enqueue and run`

### Task 5: הרובוט ב־GitHub Actions

**Files:**
- Create: `media/.github/workflows/publish.yml`, ‏`media/.github/workflows/tests.yml`, ‏`media/.github/workflows/prune.yml`

**`publish.yml`:**
- `on: schedule: "*/15 * * * *"` ו־`workflow_dispatch`.
- `concurrency: {group: publish, cancel-in-progress: false}`.
- `permissions: contents: write`.
- ריצה של `python -m publish run`. ה־env כולל את כל ה־secrets: ‏`FB_TOKEN_148`, ‏`FB_TOKEN_BEINENU` ו־`BUFFER_API_KEY`.
- אם `queue/` השתנה: ‏commit ו־push, עם המחבר `ryk-bot` וההודעה `publish: <ids>`.
- הסטטוס `publishing` נכתב ונדחף לפני הקריאה לרשת, כדי שריצה מקבילה לא תפרסם את אותו פריט.

**`tests.yml`:** ‏`pytest` בכל push.

**`prune.yml`:** פעם בשבוע. מוחק קבצים מ־`m/` של פריטים `published` מלפני יותר מ־30 יום, כדי שהריפו לא יגדל.

- [ ] **Step 1:** Write the workflows.
- [ ] **Step 2:** Push. Expected: `tests.yml` green.
- [ ] **Step 3:** Run `publish.yml` with `workflow_dispatch` while `PAUSE` exists. Expected: ריצה ירוקה, אין פרסום, אין קומיט.
- [ ] **Step 4:** Commit `ci: scheduled publisher, tests and media pruning`

### Task 6: חיבור הסוכן היומי

**Files:**
- Modify: `~/Documents/מערכת מדיה/מנוע/הוראות לסוכן היומי.md`
- Modify: הפרומפט של המשימה המתוזמנת `trig_014MooTQ9HuxV7B4E288eyb8` (עם `update_trigger`)
- Modify: `~/Documents/מערכת מדיה/בשורה/מותג.md`: מסירים את ⚠️ רק כשהטיקטוק של בשורה פתוח.
- Modify: `media/apps/*/brand.md`. מעכשיו זה המקור, והמק מקבל עותק.

**שינויים בהוראות:**
- כלל 5 (אישור עד 28.11) נמחק. במקומו: "החלטת הבעלים 17.11.2026: אין אישורים. כל פריט עובר `python -m publish enqueue`, ופריט שנדחה לא עולה."
- **שלב 2 החדש, בתחילת הריצה:**
  - מצרפים את הריפו עם `add_repo(owner, "media", access:"push")` ומשכפלים אותו.
  - אם קיים `PAUSE`, או `settings/publishing.paused == true` בדשבורד: מוודאים ש־`PAUSE` קיים בריפו, לא מתזמנים כלום וממשיכים רק למחקר.
- **שלב 4, הפקה:** מרנדרים מתוך `media/engine` בענן. אחרי בדיקה ויזואלית של הגיליון, יוצרים לכל רשת טיוטה (כיתוב מותאם), מריצים `enqueue` ודוחפים.
  - פריט `rejected` מתוקן פעם אחת. אם הוא נכשל שוב, הוא נרשם ביומן ולא עולה.
- **הדשבורד:**
  - כל פריט נרשם ב־`posts` עם status `scheduled` ו־`scheduledFor`. אין יותר `pending`.
  - פעם ביום הסוכן קורא את `queue/*` ומעדכן `published` או `failed` בדשבורד.
- **המק:** אם המק מחובר, מעתיקים אליו את הסרטון לתיקייה `פורסם/`. אם לא, ממשיכים בלי.
- **הסיכום:** ‏`runs/<date>` כולל כמה פריטים תוזמנו, כמה נדחו ולמה, וכמה נכשלו בפרסום.
- **המנכ״ל:** לפרומפט של `trig_01ExrHYEoZDWYKBtX4ZtxV6W` נוספת שורה: "קרא את queue של media ודווח על failed."

- [ ] **Step 1:** Edit the runbook and the brand files.
- [ ] **Step 2:** Update both prompts with `update_trigger`.
- [ ] **Step 3:** Add the document `settings/publishing = {paused:false}` to the dashboard, and a toggle button "עצירת פרסום" to the dashboard (publish with `edit_version`).
- [ ] **Step 4:** Fire the daily agent once (`fire_trigger`) while `PAUSE` exists. Expected: פריטים נכנסים לתור כ־`queued`, ושום דבר לא מתפרסם.

### Task 7: ההקמה עם רן (חשבונות וסודות)

רן עושה את הצעדים בדפדפן במק, ואני מדריך אחד אחד. הוא לא מקליד בשבילי סיסמאות.

- [ ] **Step 1:** GitHub: התחברות, יצירת הריפו `media` (ציבורי), והוספת secrets.
- [ ] **Step 2:** מטא:
  - לוודא ששני חשבונות האינסטגרם הם Business ומקושרים לעמודים.
  - לטפל בחסימה של האינסטגרם של 148.
  - לתקן את הקטגוריה של עמוד 148 ל"אפליקציה".
  - ליצור אפליקציית מפתחים (Business), עם `pages_manage_posts`, ‏`pages_read_engagement`, ‏`instagram_basic` ו־`instagram_content_publish`.
  - להפיק טוקן עמוד ארוך־טווח לכל עמוד ולשמור אותו כ־secret.
- [ ] **Step 3:** Buffer:
  - לחבר את הטיקטוק של בינינו ושל בשורה (של 148 כבר מחובר).
  - ליצור מפתח API ולשמור אותו כ־secret `BUFFER_API_KEY`.
  - למלא את `accounts.json` מתוך `python3 מנוע/buffer.py channels`.
- [ ] **Step 4:** Smoke test: פריט אחד לכל רשת עם `at` = עכשיו, ‏`workflow_dispatch`. בדיקה בעיניים שהפוסט עלה, והסטטוס `published`.
- [ ] **Step 5:** מוחקים את `PAUSE`. מכאן המערכת אוטומטית.

### Task 8: אימות

- [ ] `pytest -v` ירוק.
- [ ] בכל רשת שחוברה עלה פוסט אמיתי אחד.
- [ ] ריצה של `publish.yml` בשישי 12:15 (`--now` מדומה ב־dispatch) לא מפרסמת כלום.
- [ ] הסוכן היומי רץ כשהמק כבוי (התיקייה מנותקת) ועדיין הכניס פריטים לתור.
- [ ] בדשבורד רואים את הסטטוסים.
