"""Assemble the demo video and per-feature clips from record.py's screencast.

    python build_video.py OUTDIR
Writes OUTDIR/video/prompt-memory-demo-1080p.mp4, a YouTube thumbnail, and
OUTDIR/clips/*.mp4 + *.gif, one per feature.
"""
import json
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
from PIL import Image
from playwright.sync_api import sync_playwright

import compose as K

HERE = Path(__file__).parent
VID = HERE / "video"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else HERE.parent)
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS = 1920, 1080, 30
TL = json.loads((VID / "timeline.json").read_text())
FRAMES = TL["frames"]


def html_card(body):
    return K.page(body, W, H)


def render_png(pg, html, w, h, transparent=False):
    pg.set_viewport_size({"width": w, "height": h})
    pg.set_content(html, wait_until="networkidle")
    pg.evaluate("document.fonts.ready")
    pg.wait_for_timeout(150)
    tmp = VID / "_tmp.png"
    pg.screenshot(path=str(tmp), omit_background=transparent)
    return Image.open(tmp).convert("RGBA").copy()


CAPTION_CSS = """<style>@import url('https://fonts.googleapis.com/css2?family=Inter:wght@500;600&display=swap');
html,body{margin:0;background:transparent;width:1920px;height:1080px;font-family:Inter,system-ui}
.c{position:absolute;left:50%;bottom:64px;transform:translateX(-50%);white-space:nowrap;display:flex;align-items:center;gap:16px;
background:rgba(11,15,20,.88);color:#fff;font-size:38px;font-weight:600;letter-spacing:-.01em;padding:20px 34px 20px 28px;
border-radius:999px;box-shadow:0 18px 50px -12px rgba(0,0,0,.55),0 0 0 1px rgba(255,255,255,.08)}
.c i{width:14px;height:14px;border-radius:50%;background:#38CDAF;box-shadow:0 0 0 6px rgba(56,205,175,.22)}</style>"""


def build_assets():
    assets = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(device_scale_factor=1)
        for _, text in TL["captions"]:
            if text not in assets:
                assets[text] = render_png(pg, f"{CAPTION_CSS}<div class=c><i></i>{text}</div>", W, H, transparent=True)
        icon = K.ICON_SVG
        assets["__intro"] = render_png(pg, html_card(f"""
          <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center">
            <div style="width:150px;height:150px">{icon}</div>
            <h1 style="font-size:104px;margin-top:40px">Prompt Memory</h1>
            <p class="sub" style="font-size:42px;margin-top:22px;color:#c3cfdb">Rough draft in. <span class="hl" style="font-weight:700">Clear prompt out.</span></p>
          </div>"""), W, H).convert("RGB")
        assets["__outro"] = render_png(pg, html_card(f"""
          <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center">
            <div style="width:120px;height:120px">{icon}</div>
            <h1 style="font-size:84px;margin-top:34px">Prompt Memory</h1>
            <p class="sub" style="font-size:36px;margin-top:22px;color:#c3cfdb;line-height:1.5">Free with your own Groq, Gemini or OpenRouter key,<br>or sign in with Google for a synced library.</p>
            <p style="font-size:30px;margin-top:40px;color:#8fe3cf;font-weight:600">ChatGPT · Claude · Gemini · Perplexity · Grok</p>
            <p style="font-size:26px;margin-top:26px;color:#6f7d8b">Add to Chrome from the Chrome Web Store</p>
          </div>"""), W, H).convert("RGB")
        assets["__thumb"] = render_png(pg, html_card(f"""
          <div style="position:absolute;left:110px;top:0;bottom:0;width:900px;display:flex;flex-direction:column;justify-content:center">
            <div style="width:120px;height:120px">{icon}</div>
            <h1 style="font-size:116px;margin-top:40px;line-height:1">Rough draft in.<br><span class="hl">Clear prompt out.</span></h1>
            <p class="sub" style="font-size:40px;margin-top:34px;color:#c3cfdb">Prompt Memory for Chrome</p>
          </div>
          <div style="position:absolute;left:1060px;top:170px;width:1000px;transform:rotate(-2deg)">
            <div class="shot" style="background:#111;border-radius:22px"><img src="{K.crop('chatgpt-rewrite-1-card', ['card'], pad=0, out='thumb-card')[0]}"></div></div>"""),
            W, H).convert("RGB")
        b.close()
    return assets


def segments():
    """Split the recording at hard cuts; start each at its first clip mark."""
    cuts = [t for t, m in TL["marks"] if m == "cut"]
    starts = [t for t, m in TL["marks"] if m.startswith("clip:") and m.endswith(":start")]
    segs, prev = [], 0
    for c in cuts:
        s = min(t for t in starts if prev <= t < c) - 0.35
        segs.append((s, c))
        prev = c
    return segs


def source_frame(t, cache={}):
    """The latest screencast frame at wall-clock time t."""
    lo, hi = 0, len(FRAMES) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if FRAMES[mid][0] <= t:
            lo = mid
        else:
            hi = mid - 1
    name = FRAMES[lo][1]
    if name not in cache:
        cache.clear()
        cache[name] = Image.open(VID / "frames" / name).convert("RGB").resize((W, H), Image.LANCZOS) \
            if Image.open(VID / "frames" / name).size != (W, H) else Image.open(VID / "frames" / name).convert("RGB")
    return cache[name]


def caption_at(t):
    cur, since = None, None
    for ct, text in TL["captions"]:
        if ct <= t:
            cur, since = text, ct
    return cur, (t - since) if since else 0


def program(assets):
    """Yield (image, marks_hit) for every output frame at 30 fps."""
    fade = int(0.3 * FPS)

    def hold(img, secs, fade_in=True, fade_out=True):
        n = int(secs * FPS)
        black = Image.new("RGB", (W, H), K.INK)
        for i in range(n):
            a = 1.0
            if fade_in and i < fade:
                a = i / fade
            if fade_out and i >= n - fade:
                a = min(a, (n - 1 - i) / fade)
            yield (img if a >= 1 else Image.blend(black, img, a)), None

    yield from hold(assets["__intro"], 2.6, fade_in=True)
    segs = segments()
    for si, (s, e) in enumerate(segs):
        n = int((e - s) * FPS)
        for i in range(n):
            t = s + i / FPS
            frame = source_frame(t).copy()
            text, age = caption_at(t)
            if text and t < e - 0.25:
                layer = assets[text]
                a = min(1.0, age / 0.25)
                if a < 1:
                    layer = layer.copy()
                    layer.putalpha(layer.getchannel("A").point(lambda v: int(v * a)))
                frame.paste(layer, (0, 0), layer)
            # a short dip at each hard cut
            edge = min(i, n - 1 - i)
            if edge < 6:
                frame = Image.blend(Image.new("RGB", (W, H), K.INK), frame, edge / 6)
            yield frame, t
    yield from hold(assets["__outro"], 4.6, fade_out=True)


def encoder(path, scale=None):
    vf = ["-vf", f"scale={scale}:-2:flags=lanczos"] if scale else []
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", *vf, "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", str(path)]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


def gif(mp4, path, width=880, fps=15):
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(mp4), "-vf",
                    f"fps={fps},scale={width}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=192:stats_mode=diff[p];"
                    f"[b][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle", "-loop", "0", str(path)], check=True)


if __name__ == "__main__":
    (OUT / "video").mkdir(parents=True, exist_ok=True)
    (OUT / "clips").mkdir(parents=True, exist_ok=True)
    assets = build_assets()
    assets["__thumb"].save(OUT / "video" / "youtube-thumbnail-1920x1080.png", optimize=True)

    # One pass: every frame goes to the full demo, and to each feature clip whose span holds it.
    marks = {}
    for t, m in TL["marks"]:
        if m.startswith("clip:"):
            _, name, edge = m.split(":")
            marks.setdefault(name, {})[edge] = t
    order = {"rewrite": "1-rewrite", "styles": "2-styles-and-versions", "replace": "3-replace-draft",
             "slash": "4-saved-prompts-slash", "gemini": "5-gemini"}
    main = OUT / "video" / "prompt-memory-demo-1080p.mp4"
    procs = {"main": encoder(main)}
    spans = {}
    for name, span in marks.items():
        spans[name] = (span["start"] - 0.2, span["end"] + 0.3)
        procs[name] = encoder(OUT / "clips" / f"{order.get(name, name)}.mp4", scale=1280)
    counts = {k: 0 for k in procs}
    for img, t in program(assets):
        buf = img.tobytes()
        targets = ["main"] + [n for n, (a, b) in spans.items() if t is not None and a <= t <= b]
        for k in targets:
            procs[k].stdin.write(buf)
            counts[k] += 1
    for k, pr in procs.items():
        pr.stdin.close()
        pr.wait()
    print("  ", main.relative_to(OUT), f"{counts['main'] / FPS:.1f}s")
    for name in spans:
        mp4 = OUT / "clips" / f"{order.get(name, name)}.mp4"
        gif(mp4, mp4.with_suffix(".gif"))
        print("  ", mp4.relative_to(OUT), f"{counts[name] / FPS:.1f}s", "+ gif")
