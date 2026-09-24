"""Capture raw 2x screenshots of the real extension on real chat sites.

    python capture.py [scene ...]      # default: every scene
Writes raw/<scene>-<n>.png at 2560x1600 (a 1280x800 viewport at 2x).
"""
import json
import sys
from pathlib import Path

from stage import REPLY, Stage, composer

OUT = Path(__file__).parent / "raw"
OUT.mkdir(exist_ok=True)

# ── The examples. Rough drafts people really type, and rewrites in each style. ──
JAPAN = "plan a 5 day japan trip in april, budget like 2k, not too touristy"
REPLY[("japan", "deep")] = (
    "Plan a 5-day trip to Japan for me in early April. My budget is about $2,000 excluding flights, "
    "and I'd rather avoid the most touristy spots. Suggest a day-by-day itinerary with where to stay "
    "each night, how to get between places, and a rough cost per day, and point out anything I should "
    "book ahead for cherry-blossom season.")
REACT = "why does my react app rerender so much"
REPLY[("react", "deep")] = (
    "My React app re-renders much more often than I expect. Help me find out why: explain the usual "
    "causes of unnecessary re-renders, show me how to confirm which one is happening with the React "
    "DevTools Profiler, and for each cause give the fix and when it is actually worth applying.")
REPLY[("react", "quick")] = "How do I find and stop unnecessary re-renders in my React app?"
LAPTOP = "best laptop for college under 800, coding and some gaming"
REPLY[("laptop", "deep")] = (
    "I'm a college student looking for a laptop under $800 that I'll use mainly for programming "
    "and occasionally for gaming. Recommend 3 to 4 current models, compare their CPU, GPU, RAM, "
    "battery life and weight, and tell me which trade-offs matter most for my use.")
PARTY = "ideas for my kid's 10th birthday party at home"
REPLY[("birthday", "creative")] = (
    "Help me dream up a 10th birthday party at home that my kid will talk about for months. Explore a "
    "few very different themes, from a backyard detective mystery to a DIY science lab, and imagine how "
    "each could shape the invitations, games and cake. What would make it feel like an adventure "
    "rather than just a party?")
REPLY[("birthday", "deep")] = REPLY[("birthday", "creative")]
REPLY[("birthday", "quick")] = "Give me fun, low-cost ideas for a 10th birthday party at home."


RECTS_JS = """() => {
  const r = (el) => { if (!el || el.hidden) return null; const b = el.getBoundingClientRect();
    return b.width && b.height ? [b.left, b.top, b.width, b.height] : null; };
  const box = [...document.querySelectorAll('#prompt-textarea, textarea, div[contenteditable=true][role=textbox]')]
    .find(e => e.offsetParent && e.getBoundingClientRect().width > 40);
  // The visible composer frame: the nearest ancestor that is clearly wider/taller than the text box.
  let frame = box;
  for (let el = box; el && el !== document.body; el = el.parentElement) {
    const b = el.getBoundingClientRect(), s = getComputedStyle(el);
    if ((parseFloat(s.borderRadius) >= 12 && (s.borderStyle !== 'none' || s.boxShadow !== 'none' || s.backgroundColor !== 'rgba(0, 0, 0, 0)'))) { frame = el; break; }
  }
  return { card: r(document.getElementById('pm-card')), caret: r(document.getElementById('pm-caret')),
           library: r(document.getElementById('pm-library')), pill: r(document.getElementById('pm-trigger')),
           composer: r(frame), viewport: [innerWidth, innerHeight] };
}"""


def shot(pg, name):
    pg.wait_for_timeout(350)
    pg.screenshot(path=str(OUT / f"{name}.png"))
    (OUT / f"{name}.json").write_text(json.dumps(pg.evaluate(RECTS_JS)))
    print("  ", name)


def wait_title(pg, prefix, timeout=25000):
    pg.wait_for_function(
        "p => (document.querySelector('#pm-card .pm-card-title')?.textContent || '').trim().toLowerCase().startsWith(p)",
        arg=prefix.lower(), timeout=timeout)
    pg.wait_for_timeout(600)


def dismiss(pg, *labels):
    for label in labels:
        btn = pg.get_by_role("button", name=label, exact=True)
        try:
            if btn.count():
                btn.first.click(timeout=2000)
                pg.wait_for_timeout(400)
        except Exception:
            pass


def open_site(st, url, banners=(), size=None):
    pg = st.page()
    if size:
        pg.set_viewport_size({"width": size[0], "height": size[1]})
    pg.goto(url, wait_until="domcontentloaded", timeout=60000)
    box = composer(pg)
    pg.wait_for_selector("#pm-trigger", state="attached", timeout=20000)
    pg.wait_for_timeout(2500)
    dismiss(pg, *banners)
    return pg, box


def close_signup(pg):
    """Perplexity asks logged-out visitors to sign up once they start typing."""
    pg.wait_for_timeout(1200)
    for sel in ("[role=dialog] button[aria-label*='lose']", "button[aria-label='Close']", "[data-testid*='close']"):
        loc = pg.locator(sel)
        try:
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=2000)
                pg.wait_for_timeout(500)
                return True
        except Exception:
            pass
    return False


def type_draft(pg, box, text):
    box.click()
    pg.keyboard.type(text, delay=12)
    pg.wait_for_timeout(700)


# ── scenes ──────────────────────────────────────────────────────────────────
def chatgpt_rewrite(st):
    st.sign_out(); st.set({"pm_mode": "deep"})
    pg, box = open_site(st, "https://chatgpt.com/")
    type_draft(pg, box, JAPAN)
    shot(pg, "chatgpt-rewrite-0-draft")
    pg.click("#pm-trigger")
    wait_title(pg, "rewrite · deep")
    shot(pg, "chatgpt-rewrite-1-card")
    pg.click("#pm-card-toggle")
    shot(pg, "chatgpt-rewrite-2-original")
    pg.click("#pm-card-toggle")
    pg.click("#pm-card-accept")
    pg.wait_for_timeout(1200)
    shot(pg, "chatgpt-rewrite-3-replaced")
    pg.close()


def gemini_styles(st):
    st.sign_out(); st.set({"pm_mode": "deep"})
    pg, box = open_site(st, "https://gemini.google.com/app")
    type_draft(pg, box, REACT)
    pg.click("#pm-trigger")
    wait_title(pg, "rewrite · deep")
    shot(pg, "gemini-styles-1-deep")
    pg.click("#pm-card-style-quick")
    wait_title(pg, "rewrite · quick")
    shot(pg, "gemini-styles-2-quick")
    pg.close()


def perplexity_replace(st):
    st.sign_out(); st.set({"pm_mode": "deep"})
    pg, box = open_site(st, "https://www.perplexity.ai/", banners=("Decline optional", "Got it"))
    type_draft(pg, box, LAPTOP)
    print("   signup closed:", close_signup(pg))
    pg.click("#pm-trigger")
    wait_title(pg, "rewrite · deep")
    shot(pg, "perplexity-1-card")
    pg.click("#pm-card-accept")
    pg.wait_for_timeout(1500)
    shot(pg, "perplexity-2-replaced")
    pg.close()


def grok_creative(st):
    st.sign_out(); st.set({"pm_mode": "creative"})
    pg, box = open_site(st, "https://grok.com/", banners=("Reject All",), size=(1280, 1080))
    type_draft(pg, box, PARTY)
    pg.click("#pm-trigger")
    wait_title(pg, "rewrite · creative")
    shot(pg, "grok-1-creative")
    pg.close()
    st.set({"pm_mode": "deep"})


def chatgpt_library(st):
    st.sign_in(); st.set({"pm_mode": "deep", "pm_slash": True, "pm_tracking": False})
    pg, box = open_site(st, "https://chatgpt.com/")
    type_draft(pg, box, "Here's the diff for the checkout refactor. ")
    pg.keyboard.type("//rev", delay=60)
    pg.wait_for_timeout(1200)
    shot(pg, "chatgpt-slash-1-menu")
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(1000)
    shot(pg, "chatgpt-slash-2-inserted")
    # The library sheet
    pg.keyboard.press("Meta+Shift+L")
    pg.wait_for_selector("#pm-library:not([hidden])", timeout=8000)
    pg.wait_for_function("!document.querySelector('#pm-library .pm-lib-skeleton')")
    shot(pg, "chatgpt-library-1-sheet")
    pg.click("#pm-lib-more")
    pg.wait_for_timeout(300)
    pg.get_by_role("menuitem", name="Privacy settings…").click()
    pg.wait_for_timeout(500)
    shot(pg, "chatgpt-library-2-privacy")
    pg.close()
    st.sign_out()


def popup(st):
    st.sign_out()
    pg = st.page()
    pg.set_viewport_size({"width": 400, "height": 760})
    pg.goto(f"chrome-extension://{st.ext_id}/popup.html")
    pg.wait_for_timeout(1200)
    shot(pg, "popup-1-signed-out")
    pg.close()


SCENES = {f.__name__: f for f in (chatgpt_rewrite, gemini_styles, perplexity_replace, grok_creative,
                                  chatgpt_library, popup)}

if __name__ == "__main__":
    names = sys.argv[1:] or list(SCENES)
    failed = []
    for n in names:
        print(n)
        st = Stage()   # a fresh profile per scene: no draft or chat text carries over
        try:
            SCENES[n](st)
        except Exception as e:  # keep going; report at the end
            failed.append(n)
            print("  FAILED:", str(e).splitlines()[0][:200])
        finally:
            st.close()
    sys.exit(1 if failed else 0)
