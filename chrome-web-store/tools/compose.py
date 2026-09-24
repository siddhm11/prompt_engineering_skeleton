"""Compose the Chrome Web Store images from the raw captures.

Every product image here is a crop of a real screenshot from capture.py; the
frames, headlines and tiles are drawn in HTML and rendered by Chromium at 2x,
then downsampled to the exact size the store asks for (24-bit PNG, no alpha).
"""
import base64
import json
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
RAW = HERE / "raw"
CROPS = HERE / "crops"
CROPS.mkdir(exist_ok=True)
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else HERE.parent / "images")

TEAL, BLUE, VIOLET = "#38CDAF", "#4B97CA", "#7159EB"
INK = "#0B0F14"

# The icon, redrawn as a vector: a teal→violet rounded tile with a ringed plus.
ICON_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="{TEAL}"/><stop offset=".5" stop-color="{BLUE}"/><stop offset="1" stop-color="{VIOLET}"/></linearGradient></defs>
<rect width="96" height="96" rx="22" fill="url(#g)"/>
<circle cx="48" cy="48" r="29.5" fill="none" stroke="#fff" stroke-width="8"/>
<path d="M48 34v28M34 48h28" stroke="#fff" stroke-width="8" stroke-linecap="round"/></svg>"""


def crop(name, keys, pad=24, out=None, extra=None):
    """Cut the union of the named rects (CSS px) out of a 2x capture."""
    meta = json.loads((RAW / f"{name}.json").read_text())
    rects = [meta[k] for k in keys if meta.get(k)]
    if extra:
        rects.append(extra)
    x0 = min(r[0] for r in rects) - pad
    y0 = min(r[1] for r in rects) - pad
    x1 = max(r[0] + r[2] for r in rects) + pad
    y1 = max(r[1] + r[3] for r in rects) + pad
    vw, vh = meta["viewport"]
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(vw, x1), min(vh, y1)
    im = Image.open(RAW / f"{name}.png")
    s = im.width / vw
    c = im.crop((round(x0 * s), round(y0 * s), round(x1 * s), round(y1 * s)))
    path = CROPS / f"{out or name}.png"
    c.save(path)
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode(), c.width / 2, c.height / 2


BASE_CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
* {{ box-sizing: border-box; margin: 0; }}
html, body {{ width: 100%; height: 100%; }}
body {{ font-family: Inter, system-ui, sans-serif; color: #fff; background: {INK}; overflow: hidden; position: relative;
  -webkit-font-smoothing: antialiased; }}
.glow {{ position: absolute; inset: 0; pointer-events: none;
  background: radial-gradient(900px 520px at 8% -10%, {TEAL}40, transparent 60%),
              radial-gradient(900px 600px at 105% 110%, {VIOLET}45, transparent 60%),
              radial-gradient(700px 400px at 60% 40%, {BLUE}14, transparent 70%); }}
.grain {{ position: absolute; inset: 0; opacity: .05; pointer-events: none;
  background-image: radial-gradient(#fff 0.6px, transparent 0.6px); background-size: 4px 4px; }}
.brand {{ display: flex; align-items: center; gap: 10px; font-weight: 600; font-size: 15px; color: #cfe9e3; letter-spacing: .01em; }}
.brand svg {{ width: 26px; height: 26px; }}
h1 {{ font-weight: 800; letter-spacing: -0.025em; line-height: 1.05; }}
.sub {{ color: #aab6c3; line-height: 1.45; }}
.shot {{ border-radius: 14px; overflow: hidden; box-shadow: 0 30px 80px -20px #000c, 0 0 0 1px #ffffff1f; background: #fff; }}
.shot img {{ display: block; width: 100%; height: auto; }}
.label {{ display: inline-flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; color: #d8e3ec;
  background: #ffffff12; border: 1px solid #ffffff1c; padding: 6px 12px; border-radius: 999px; margin-bottom: 12px; }}
.label i {{ width: 7px; height: 7px; border-radius: 50%; background: {TEAL}; display: inline-block; }}
.hl {{ background: linear-gradient(90deg, {TEAL}, #8fd3ff 60%, #b3a4ff); -webkit-background-clip: text; color: transparent; }}
"""


def page(body, w, h):
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{BASE_CSS}
    body {{ width: {w}px; height: {h}px; }}</style></head>
    <body><div class="glow"></div><div class="grain"></div>{body}</body></html>"""


def slide(eyebrow, title, sub, content):
    """A 1280x800 store screenshot: headline at the top, real UI below."""
    return f"""
    <div style="position:absolute; left:64px; top:52px; right:64px;">
      <div class="brand">{ICON_SVG}Prompt Memory<span style="opacity:.45; font-weight:500">· {eyebrow}</span></div>
      <h1 style="font-size:46px; margin-top:22px; max-width:1100px">{title}</h1>
      <p class="sub" style="font-size:19px; margin-top:12px; max-width:980px">{sub}</p>
    </div>
    <div style="position:absolute; left:64px; right:64px; top:236px; bottom:28px; display:flex; flex-direction:column; justify-content:center">{content}</div>"""


def img(uri, w, style=""):
    return f'<div class="shot" style="width:{w}px; {style}"><img src="{uri}"></div>'


def render(pw_page, html, w, h, path):
    pw_page.set_viewport_size({"width": w, "height": h})
    pw_page.set_content(html, wait_until="networkidle")
    pw_page.evaluate("document.fonts.ready")
    pw_page.wait_for_timeout(200)
    tmp = path.with_suffix(".2x.png")
    pw_page.screenshot(path=str(tmp))
    Image.open(tmp).convert("RGB").resize((w, h), Image.LANCZOS).save(path, optimize=True)
    tmp.unlink()
    print("  ", path.relative_to(OUT), f"{w}x{h}")


def screenshots():
    S = []
    # 1 — the rewrite, on ChatGPT
    u, cw, ch = crop("chatgpt-rewrite-1-card", ["card", "composer"], pad=26)
    w = 1060
    S.append(("01-rewrite-in-chatgpt", slide(
        "Rewrite",
        'Rough draft in. <span class="hl">Clear prompt out.</span>',
        "Click ⊕ beside the chat box. Read the rewrite, then replace your draft with it, or keep your own.",
        f'<div style="display:flex; justify-content:center">{img(u, w)}</div>')))

    # 2 — styles and versions, on Gemini
    u1, w1, h1 = crop("gemini-styles-1-deep", ["card"], pad=0)
    u2, w2, h2 = crop("gemini-styles-2-quick", ["card"], pad=0)
    col = 470
    S.append(("02-styles-and-versions", slide(
        "Styles",
        'Shorter, more detail, <span class="hl">or open-ended.</span>',
        "Try another style in one click. Every version stays on the card, so you can step back to the one you liked.",
        f'''<div style="display:flex; gap:44px; justify-content:center; align-items:flex-start">
          <div><div class="label"><i></i>First rewrite · Deep</div>{img(u1, col, "background:#111")}</div>
          <div style="align-self:center; font-size:34px; color:#5d6b79; padding-top:30px">→</div>
          <div><div class="label"><i></i>After “Shorter” · version 2 of 2</div>{img(u2, col, "background:#111")}</div></div>''')))

    # 3 — // saved prompts, on ChatGPT
    u1, w1, h1 = crop("chatgpt-slash-1-menu", ["caret", "composer"], pad=14)
    u2, w2, h2 = crop("chatgpt-slash-2-inserted", ["composer"], pad=14)
    S.append(("03-saved-prompts-with-slash", slide(
        "Library",
        'Your best prompts are <span class="hl">one // away.</span>',
        "Type // in the chat box to search your saved prompts, and press Enter to drop one in at the cursor.",
        f'''<div style="display:flex; flex-direction:column; gap:22px; width:860px; margin:0 auto">
          <div style="display:flex; gap:18px; align-items:flex-start"><div class="label" style="flex:none; width:128px; margin-top:4px">1 · Type //rev</div>{img(u1, 714)}</div>
          <div style="display:flex; gap:18px; align-items:flex-start"><div class="label" style="flex:none; width:128px; margin-top:4px">2 · Press Enter</div>{img(u2, 714)}</div></div>''')))

    # 4 — the same card on other sites
    u1, w1, h1 = crop("perplexity-1-card", ["card", "composer"], pad=12)
    u2, w2, h2 = crop("grok-1-creative", ["card", "composer"], pad=12)
    S.append(("04-works-where-you-chat", slide(
        "Everywhere",
        'Works where you <span class="hl">already chat.</span>',
        "ChatGPT, Claude, Gemini, Perplexity and Grok, with the same card, keys and library on every site.",
        f'''<div style="display:flex; gap:44px; justify-content:center; align-items:flex-start">
          <div><div class="label"><i></i>Perplexity · Deep</div>{img(u1, 540)}</div>
          <div><div class="label"><i></i>Grok · Creative</div>{img(u2, 540)}</div></div>''')))

    # 5 — setup and privacy
    u1, w1, h1 = crop("popup-1-signed-out", [], pad=0, extra=[0, 0, 400, 470])
    u2, w2, h2 = crop("chatgpt-library-2-privacy", ["library"], pad=0)
    S.append(("05-your-key-your-choice", slide(
        "Setup",
        'Your key. <span class="hl">Your choice.</span>',
        "Paste a Groq, Gemini or OpenRouter key and skip the account, or sign in with Google for a synced library. Each data setting has its own switch.",
        f'''<div style="display:flex; gap:48px; justify-content:center; align-items:flex-start">
          <div><div class="label"><i></i>The toolbar popup</div>{img(u1, 330, "background:#0d1117")}</div>
          <div><div class="label"><i></i>Privacy settings, in the library</div>{img(u2, 520, "background:#0d1117")}</div></div>''')))
    return S


def plain():
    """Unframed alternates: the raw 1280x800 captures, straight from the browser."""
    return ["chatgpt-rewrite-1-card", "gemini-styles-2-quick", "chatgpt-slash-1-menu",
            "perplexity-1-card", "chatgpt-library-1-sheet"]


def tiles():
    small = f"""
    <div style="position:absolute; left:34px; top:34px; width:74px; height:74px">{ICON_SVG}</div>
    <div style="position:absolute; left:34px; top:128px; right:28px">
      <h1 style="font-size:36px">Prompt Memory</h1>
      <p class="sub" style="font-size:17px; margin-top:10px; color:#c3cfdb">Rough draft in.<br><span class="hl" style="font-weight:700">Clear prompt out.</span></p>
    </div>"""
    u, cw, ch = crop("chatgpt-rewrite-1-card", ["card"], pad=0, out="tile-card")
    marquee = f"""
    <div style="position:absolute; left:84px; top:0; bottom:0; width:520px; display:flex; flex-direction:column; justify-content:center">
      <div style="width:84px; height:84px">{ICON_SVG}</div>
      <h1 style="font-size:60px; margin-top:28px">Prompt Memory</h1>
      <p class="sub" style="font-size:24px; margin-top:16px; color:#c3cfdb">Rough draft in. <span class="hl" style="font-weight:700">Clear prompt out.</span><br>Right inside ChatGPT, Claude, Gemini, Perplexity and Grok.</p>
    </div>
    <div style="position:absolute; left:660px; top:70px; width:760px; transform: rotate(-2deg); transform-origin: left top">
      <div class="shot" style="background:#111; border-radius:18px"><img src="{u}"></div></div>"""
    return [("small-promo-tile-440x280", small, 440, 280), ("marquee-promo-tile-1400x560", marquee, 1400, 560)]


def icon(pw_page, path, size=128, art=96):
    pad = (size - art) // 2
    html = f"""<!doctype html><style>html,body{{margin:0;background:transparent}}</style>
    <div style="width:{size}px;height:{size}px;padding:{pad}px;box-sizing:border-box">{ICON_SVG.replace('<svg ', f'<svg width="{art}" height="{art}" ')}</div>"""
    pw_page.set_viewport_size({"width": size, "height": size})
    pw_page.set_content(html)
    tmp = path.with_suffix(".2x.png")
    pw_page.screenshot(path=str(tmp), omit_background=True)
    Image.open(tmp).resize((size, size), Image.LANCZOS).save(path, optimize=True)
    tmp.unlink()
    print("  ", path.relative_to(OUT), f"{size}x{size} (transparent padding {pad}px)")


if __name__ == "__main__":
    (OUT / "screenshots").mkdir(parents=True, exist_ok=True)
    (OUT / "screenshots-unframed").mkdir(parents=True, exist_ok=True)
    (OUT / "promo-tiles").mkdir(parents=True, exist_ok=True)
    (OUT / "icon").mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(device_scale_factor=2)
        for name, body in screenshots():
            render(pg, page(body, 1280, 800), 1280, 800, OUT / "screenshots" / f"{name}.png")
        for name, body, w, h in tiles():
            render(pg, page(body, w, h), w, h, OUT / "promo-tiles" / f"{name}.png")
        icon(pg, OUT / "icon" / "store-icon-128.png")
        # Optional drop-in replacements for extension/icon{16,48,128}.png: Chrome's
        # guidance is edge-to-edge art at 16 and 48, and 96px art padded to 128.
        (OUT / "icon" / "extension-icons").mkdir(exist_ok=True)
        icon(pg, OUT / "icon" / "extension-icons" / "icon128.png")
        icon(pg, OUT / "icon" / "extension-icons" / "icon48.png", size=48, art=46)
        icon(pg, OUT / "icon" / "extension-icons" / "icon16.png", size=16, art=16)
        b.close()
    for i, name in enumerate(plain(), 1):
        Image.open(RAW / f"{name}.png").convert("RGB").resize((1280, 800), Image.LANCZOS).save(
            OUT / "screenshots-unframed" / f"{i:02d}-{name}.png", optimize=True)
        print("   screenshots-unframed", name)
