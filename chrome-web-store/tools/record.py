"""Record the demo: the real extension on real chat sites, via Chrome's screencast.

    python record.py
Writes video/frames/*.jpg and video/timeline.json (frame times, captions, clip marks).
The viewport is 1280x720 at 1.5x, so frames arrive at 1920x1080.
"""
import base64
import json
import shutil
import time
from pathlib import Path

import capture as C
from stage import HOLD, REPLY, Stage, composer, release

HERE = Path(__file__).parent
VID = HERE / "video"
FRAMES = VID / "frames"
shutil.rmtree(FRAMES, ignore_errors=True)
FRAMES.mkdir(parents=True)

REPLY[("japan", "quick")] = "Plan a 5-day, $2,000 trip to Japan in early April that skips the most touristy spots."

TL = {"frames": [], "captions": [], "marks": []}

# A visible cursor with a click ripple, drawn in the page (Playwright's input has no cursor).
CURSOR_JS = r"""
(() => {
  const mk = () => {
    const c = document.createElement('div');
    c.id = '__demo_cursor';
    c.innerHTML = '<svg width="26" height="26" viewBox="0 0 24 24"><path d="M4 2l15 11.5-6.6.9 3.9 7.6-2.9 1.4-3.8-7.7L4 20z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    Object.assign(c.style, { position: 'fixed', left: '-40px', top: '-40px', zIndex: 2147483647, pointerEvents: 'none',
      transform: 'translate(-3px,-2px)', filter: 'drop-shadow(0 2px 3px rgba(0,0,0,.35))', transition: 'none' });
    return c;
  };
  let c;
  const ensure = () => { if (!c || !c.isConnected) c = mk(); if (document.documentElement.lastElementChild !== c) document.documentElement.appendChild(c); };
  addEventListener('mousemove', (e) => { ensure(); c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
  addEventListener('mousedown', (e) => {
    ensure();
    const r = document.createElement('div');
    Object.assign(r.style, { position: 'fixed', left: (e.clientX - 18) + 'px', top: (e.clientY - 18) + 'px', width: '36px', height: '36px',
      borderRadius: '50%', background: 'rgba(56,205,175,.45)', zIndex: 2147483646, pointerEvents: 'none', transform: 'scale(.3)',
      transition: 'transform .35s ease-out, opacity .45s ease-out' });
    document.documentElement.appendChild(r);
    requestAnimationFrame(() => { r.style.transform = 'scale(1.4)'; r.style.opacity = '0'; });
    setTimeout(() => r.remove(), 600);
  }, true);
})();
"""


class Rec:
    """Screencast one page into FRAMES, with wall-clock timestamps."""

    def __init__(self, pg):
        self.pg = pg
        self.cdp = pg.context.new_cdp_session(pg)
        self.cdp.on("Page.screencastFrame", self.frame)
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": 1920, "maxHeight": 1080,
                                               "everyNthFrame": 1})
        self.mouse = (1100, 650)

    def frame(self, ev):
        n = len(TL["frames"])
        path = FRAMES / f"{n:05d}.jpg"
        path.write_bytes(base64.b64decode(ev["data"]))
        TL["frames"].append([time.time(), path.name])
        try:
            self.cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
        except Exception:
            pass

    def stop(self):
        try:
            self.cdp.send("Page.stopScreencast")
        except Exception:
            pass
        TL["marks"].append([time.time(), "cut"])   # a hard cut to whatever comes next

    # ── human-paced input ──
    def wait(self, ms):
        self.pg.wait_for_timeout(ms)

    def move_to(self, target, steps=28):
        if isinstance(target, str):
            b = self.pg.locator(target).first.bounding_box()
            target = (b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
        x0, y0 = self.mouse
        x1, y1 = target
        for i in range(1, steps + 1):
            t = i / steps
            e = t * t * (3 - 2 * t)          # ease in-out
            self.pg.mouse.move(x0 + (x1 - x0) * e, y0 + (y1 - y0) * e)
            self.pg.wait_for_timeout(14)
        self.mouse = target

    def click(self, target, pause=260):
        self.move_to(target)
        self.wait(pause)
        self.pg.mouse.down()
        self.wait(70)
        self.pg.mouse.up()

    def type(self, text, delay=42):
        self.pg.keyboard.type(text, delay=delay)


def caption(text):
    TL["captions"].append([time.time(), text])


def mark(name):
    TL["marks"].append([time.time(), name])


def open_page(st, url, banners=()):
    pg = st.page()
    pg.set_viewport_size({"width": 1280, "height": 720})
    pg.goto(url, wait_until="domcontentloaded", timeout=60000)
    box = composer(pg)
    pg.wait_for_selector("#pm-trigger", state="attached", timeout=20000)
    pg.wait_for_timeout(2500)
    C.dismiss(pg, *banners)
    return pg, box


def rewrite_with_hold(r, target, ms=1100):
    HOLD["on"] = True
    r.click(target)
    r.wait(ms)
    release()
    HOLD["on"] = False


def scene_chatgpt(st):
    st.sign_out(); st.set({"pm_mode": "deep"})
    pg, box = open_page(st, "https://chatgpt.com/")
    r = Rec(pg)
    r.pg.mouse.move(*r.mouse)
    r.wait(600)
    mark("clip:rewrite:start")
    caption("Type the way you think.")
    r.click(box.bounding_box() and (box.bounding_box()["x"] + 60, box.bounding_box()["y"] + box.bounding_box()["height"] / 2))
    r.wait(300)
    r.type(C.JAPAN)
    r.wait(700)
    caption("Click ⊕ to rewrite it.")
    rewrite_with_hold(r, "#pm-trigger")
    pg.wait_for_selector("#pm-card .pm-card-title >> text=/Rewrite · Deep/i", timeout=15000)
    caption("A clearer prompt, with everything you meant.")
    r.move_to((1000, 560))
    r.wait(3200)
    mark("clip:rewrite:end")
    mark("clip:styles:start")
    caption("Too long? Try Shorter.")
    rewrite_with_hold(r, "#pm-card-style-quick", ms=900)
    pg.wait_for_selector("#pm-card .pm-card-title >> text=/Rewrite · Quick/i", timeout=15000)
    r.wait(1800)
    caption("Every version is kept. Step back any time.")
    r.click("#pm-card-ver-prev")
    r.wait(1600)
    r.click("#pm-card-ver-next")
    r.wait(1200)
    mark("clip:styles:end")
    mark("clip:replace:start")
    caption("Replace your draft, then send it as usual.")
    r.click("#pm-card-accept")
    r.wait(2600)
    mark("clip:replace:end")
    r.stop()
    pg.close()


def scene_slash(st):
    st.sign_in(); st.set({"pm_mode": "deep", "pm_slash": True, "pm_tracking": False})
    pg, box = open_page(st, "https://chatgpt.com/")
    r = Rec(pg)
    r.pg.mouse.move(*r.mouse)
    r.wait(500)
    mark("clip:slash:start")
    caption("Save the prompts that work. Type // to use one.")
    b = box.bounding_box()
    r.click((b["x"] + 60, b["y"] + b["height"] / 2))
    r.type("Here's the diff for the checkout refactor. ")
    r.wait(300)
    r.type("//rev", delay=150)
    r.wait(1800)
    caption("Enter drops it in at the cursor.")
    pg.keyboard.press("Enter")
    r.wait(2600)
    mark("clip:slash:end")
    r.stop()
    pg.close()
    st.sign_out()


def scene_sites(st):
    st.sign_out(); st.set({"pm_mode": "deep"})
    pg, box = open_page(st, "https://gemini.google.com/app")
    r = Rec(pg)
    r.pg.mouse.move(*r.mouse)
    r.wait(400)
    mark("clip:gemini:start")
    caption("The same card on Gemini, Claude, Perplexity and Grok.")
    b = box.bounding_box()
    r.click((b["x"] + 80, b["y"] + b["height"] / 2))
    r.type(C.REACT, delay=34)
    r.wait(400)
    rewrite_with_hold(r, "#pm-trigger", ms=900)
    pg.wait_for_selector("#pm-card .pm-card-title >> text=/Rewrite · Deep/i", timeout=15000)
    r.wait(2800)
    mark("clip:gemini:end")
    r.stop()
    pg.close()


if __name__ == "__main__":
    try:
        for scene in (scene_chatgpt, scene_slash, scene_sites):
            print(scene.__name__)
            st = Stage(scale=1.5, width=1280, height=720)   # fresh profile: nothing carries over
            st.ctx.add_init_script(CURSOR_JS)
            try:
                scene(st)
            finally:
                st.close()
    finally:
        (VID / "timeline.json").write_text(json.dumps(TL, indent=0))
        print(len(TL["frames"]), "frames;", len(TL["captions"]), "captions")
