# media · RYK

Automatic publishing for 148, בינינו and בשורה.

- `queue/<app>/<id>.json`: one file per post. Status: queued → publishing → published / failed / rejected.
- `python -m publish enqueue draft.json video.mp4`: automatic QA, Shabbat/holiday check, one post per day per page.
- `.github/workflows/publish.yml`: runs every 15 minutes and publishes what is due.
- **Stop everything:** create a file named `PAUSE` in the repo root. Delete it to resume.
