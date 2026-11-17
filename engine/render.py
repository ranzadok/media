"""Render a short vertical video from a script file.

Usage:
  python3 render.py <script.json> <out.mp4>            full render (video + music)
  python3 render.py <script.json> <sheet.jpg> --sheet  contact sheet of key frames, for checking before a full render

The script names its app ("app"); the theme and assets come from that app's folder:
  <root>/<app>/חומרים/theme.json, logo.png, screenshots...
"""
import sys, os, json, subprocess, asyncio, wave, tempfile
import numpy as np
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "apps"))
ALIASES = {"148 ניצוץ יומי": "148", "בינינו": "beinenu", "בשורה": "bsora"}
FPS = 30
CHROME = next((p for p in ["/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"] if os.path.exists(p)), None)


def load(script_path):
    S = json.load(open(script_path, encoding="utf-8"))
    S["app"] = ALIASES.get(S["app"], S["app"])
    assets = os.path.join(ROOT, S["app"], "assets")
    T = json.load(open(os.path.join(assets, "theme.json"), encoding="utf-8"))
    return S, T, assets


async def frames(S, T, assets, out, sheet=False):
    async with async_playwright() as p:
        kw = {"executable_path": CHROME} if CHROME else {}
        b = await p.chromium.launch(args=["--force-color-profile=srgb", "--allow-file-access-from-files"], **kw)
        pg = await b.new_page(viewport={"width": 1080, "height": 1920})
        await pg.add_init_script("window.SCRIPT=%s;window.THEME=%s;window.ASSETS=%s;" % (
            json.dumps(S, ensure_ascii=False), json.dumps(T, ensure_ascii=False), json.dumps("file://" + assets)))
        await pg.goto("file://" + os.path.join(HERE, "template.html"))
        await pg.evaluate("document.fonts.ready")
        await pg.wait_for_timeout(500)
        dur = await pg.evaluate("window.DUR")
        scenes = await pg.evaluate("window.SCENES")
        if sheet:
            from PIL import Image
            ts = []
            for s in scenes:
                ts.append(s["a"] + (s["b"] - s["a"]) * 0.85)
            ims = []
            for t in ts:
                await pg.evaluate(f"render({t})")
                path = tempfile.mktemp(suffix=".jpg")
                await pg.screenshot(path=path, type="jpeg", quality=85)
                ims.append(Image.open(path).resize((360, 640)))
            sh = Image.new("RGB", (370 * len(ims), 640), "white")
            for i, im in enumerate(ims):
                sh.paste(im, (i * 370, 0))
            sh.save(out, quality=85)
        else:
            ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS),
                                   "-c:v", "mjpeg", "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
                                   "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
            for i in range(int(round(dur * FPS))):
                await pg.evaluate(f"render({i / FPS})")
                ff.stdin.write(await pg.screenshot(type="jpeg", quality=90))
            ff.stdin.close(); ff.wait()
            if ff.returncode:
                raise SystemExit("ffmpeg failed")
        await b.close()
        return dur, scenes


def music(dur, scenes, T, path, bpm=None):
    """Original synthesized bed: warm pad + bass + modern beat. Drums drop out in calm scenes."""
    SR = 44100; n = int(SR * dur); out = np.zeros(n)
    bpm = bpm or T.get("bpm", 88); beat = 60 / bpm; rng = np.random.default_rng(7)
    calm = [(s["a"], s["b"]) for s in scenes if s["type"] in ("words",) or s.get("calm")]
    def add(sig, st):
        s = int(st * SR); e = min(n, s + len(sig))
        if s < n: out[s:e] += sig[:e - s]
    chords = T.get("chords", [[220, 261.63, 329.63], [174.61, 220, 261.63], [196, 261.63, 329.63], [196, 246.94, 293.66]])
    bar = beat * 4
    for i in range(int(dur / (bar * 2)) + 1):
        ch = chords[i % len(chords)]; L = bar * 2 + .5; x = np.arange(int(SR * L)) / SR
        e = np.minimum(1, x / .8) * np.minimum(1, (L - x) / .8)
        add(.05 * e * sum(np.sin(2 * np.pi * f * x) + .3 * np.sin(4 * np.pi * f * x + .5) for f in ch), i * bar * 2)
        add(.10 * e * np.sin(np.pi * ch[0] * x), i * bar * 2)
    for k in range(int(dur / beat)):
        tb = k * beat
        if tb > dur - 1 or any(a < tb < b for a, b in calm):
            continue
        if k % 2 == 0:
            x = np.arange(int(SR * .35)) / SR
            add(.45 * np.sin(2 * np.pi * np.cumsum(50 + 90 * np.exp(-x * 30)) / SR) * np.exp(-x * 9), tb)
        else:
            x = np.arange(int(SR * .2)) / SR; add(.10 * rng.standard_normal(len(x)) * np.exp(-x * 25), tb)
        if tb > scenes[0]["b"]:
            for h in (0, .5):
                x = np.arange(int(SR * .06)) / SR; hh = np.diff(rng.standard_normal(len(x)), prepend=0)
                add(.035 * hh * np.exp(-x * 70), tb + h * beat)
    mel = T.get("melody", [659.25, 587.33, 523.25, 493.88, 523.25, 440])
    for a, b in calm:
        for j, st in enumerate(np.arange(a + .2, b - .3, beat)):
            f = mel[j % len(mel)]; x = np.arange(int(SR * .9)) / SR
            add(.07 * (np.sin(2 * np.pi * f * x) + .4 * np.sin(4 * np.pi * f * x)) * np.exp(-x * 4), st)
    for s in scenes:  # impact on stamps and scene starts with a hit
        if s.get("hit"):
            x = np.arange(int(SR * .8)) / SR
            add(.5 * np.sin(2 * np.pi * np.cumsum(40 + 120 * np.exp(-x * 20)) / SR) * np.exp(-x * 5), s["a"] + s.get("hitAt", 0))
    fo = np.ones(n); m = int(SR * min(2, dur / 4)); fo[-m:] = np.linspace(1, 0, m); out *= fo
    out = out / (np.max(np.abs(out)) or 1) * .8
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.stack([out, out], 1) * 32767).astype(np.int16).tobytes())


def main():
    script, out = sys.argv[1], sys.argv[2]
    S, T, assets = load(script)
    # stamp scenes get an impact hit at the stamp moment
    for s in S["scenes"]:
        if s.get("type") == "bubble" and s.get("stamp"):
            s["hit"] = True; s["hitAt"] = s.get("stampAt", s["dur"] * .68)
        if s.get("type") == "bubble" and s.get("style") == "calm":
            s["calm"] = True
    if "--sheet" in sys.argv:
        asyncio.run(frames(S, T, assets, out, sheet=True)); print("sheet", out); return
    tmpv = out + ".video.mp4"; tmpa = out + ".music.wav"; tmpo = out[:-4] + ".tmp.mp4"
    dur, scenes = asyncio.run(frames(S, T, assets, tmpv))
    for s, sc in zip(S["scenes"], scenes):
        sc.update({k: s[k] for k in ("hit", "hitAt", "calm") if k in s})
    music(dur, scenes, T, tmpa, S.get("bpm"))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmpv, "-i", tmpa, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                    "-af", "loudnorm=I=-14:TP=-1.5", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-shortest", tmpo], check=True)
    os.replace(tmpo, out)
    for f in (tmpv, tmpa):
        os.remove(f)
    print("done", out, round(dur, 1), "s")


if __name__ == "__main__":
    main()
