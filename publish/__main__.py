"""python -m publish enqueue <draft.json> <media...> | run [--now ISO] | status | channels [--key-secret NAME]"""
import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

from . import guard, queue

ROOT = Path(__file__).resolve().parents[1]


def _git_push(ids):
    """Called before any network call so a parallel run sees 'publishing'."""
    subprocess.run(["git", "add", "queue"], cwd=ROOT, check=True)
    subprocess.run(["git", "commit", "-qm", "publishing: " + " ".join(ids)], cwd=ROOT, check=True)
    subprocess.run(["git", "push", "-q"], cwd=ROOT, check=True)


def main():
    ap = argparse.ArgumentParser(prog="publish")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("enqueue"); e.add_argument("draft"); e.add_argument("media", nargs="+")
    r = sub.add_parser("run"); r.add_argument("--now"); r.add_argument("--push", action="store_true")
    sub.add_parser("status")
    c = sub.add_parser("channels"); c.add_argument("--key-secret", default="BUFFER_API_KEY")
    a = ap.parse_args()

    if a.cmd == "enqueue":
        try:
            print(queue.enqueue(ROOT, Path(a.draft), [Path(m) for m in a.media]))
        except queue.Rejected as ex:
            print("נדחה: " + str(ex), file=sys.stderr); sys.exit(2)
        except queue.Paused as ex:
            print(str(ex), file=sys.stderr); sys.exit(3)
    elif a.cmd == "run":
        now = (datetime.datetime.fromisoformat(a.now) if a.now
               else datetime.datetime.now(datetime.timezone.utc)).astimezone(guard.IL)
        done = queue.run(ROOT, now, on_publishing=_git_push if a.push else None)
        print(json.dumps({"published": done}, ensure_ascii=False))
    elif a.cmd == "channels":
        import os
        from .networks import buffer
        key = os.environ.get(a.key_secret)
        if not key:
            print(f"הסוד {a.key_secret} לא מוגדר", file=sys.stderr); sys.exit(1)
        for ch in buffer.list_channels(key):
            print(f"{ch['service']:10} {ch['name']:25} {ch['id']}  ({ch['org']})")
    else:
        for it in queue._all(ROOT):
            print(f"{it['status']:10} {it['at']}  {it['app']:7} {it['network']:9} {it['id']}  {it.get('error') or ''}")


if __name__ == "__main__":
    main()
