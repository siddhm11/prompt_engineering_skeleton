"""Shared stage: the real unpacked extension in Playwright Chromium on real chat sites.

The only thing faked is the model's reply on the direct (bring-your-own-key)
route: api.groq.com answers with REPLY text as a real SSE stream, unless
PM_LIVE_KEY_FILE names a file holding a Groq key, in which case the request goes to Groq for real.
"""
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("PW_EXPERIMENTAL_SERVICE_WORKER_NETWORK_EVENTS", "1")
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "extension"
# A real Groq key, read from a file so it never lands in a shell history.
_kf = os.environ.get("PM_LIVE_KEY_FILE", "")
LIVE_KEY = Path(_kf).expanduser().read_text().strip() if _kf else ""

# What the fake provider answers, by the style marker in the system prompt.
REPLY = {}
SEEN = []   # every request the extension sent to the provider
# When HOLD["on"], replies wait in PENDING until release(): a video can show
# the "Rewriting…" state for as long as a real model call would take.
HOLD = {"on": False}
PENDING = []


def release():
    while PENDING:
        fn = PENDING.pop(0)
        fn()


def style_of(system):
    for s in ("quick", "deep", "creative"):
        if f"### MODE: {s.upper()}" in system:
            return s
    return "deep"


def provider(route):
    body = json.loads(route.request.post_data or "{}")
    system = body["messages"][0]["content"]
    user = body["messages"][-1]["content"]
    style = style_of(system)
    SEEN.append({"style": style, "user": user})
    if LIVE_KEY:
        route.continue_()
        return
    text = next((v for (k, s), v in REPLY.items() if s == style and k in user), None)
    text = text or next((v for (k, s), v in REPLY.items() if s == style), "…")
    words = text.split(" ")
    chunks = [" ".join(words[i:i + 2]) + (" " if i + 2 < len(words) else "") for i in range(0, len(words), 2)]
    sse = "".join(f"data: {json.dumps({'choices': [{'delta': {'content': c}}]})}\n\n" for c in chunks)
    send = lambda: route.fulfill(status=200, content_type="text/event-stream", body=sse + "data: [DONE]\n\n")
    PENDING.append(send) if HOLD["on"] else send()


# Sample content for the demo account's library.
SAVED = [
    {"id": "s1", "title": "Code review", "tags": ["coding"],
     "content": "Review this diff like a senior engineer: correctness first, then naming, then tests. Flag anything that changes behaviour."},
    {"id": "s2", "title": "Explain like a teacher", "tags": ["learning"],
     "content": "Explain the concept step by step with one concrete example, then the most common misconception."},
    {"id": "s3", "title": "Tighten my writing", "tags": ["writing"],
     "content": "Edit this for clarity: cut every sentence that does not earn its place, and keep my voice."},
    {"id": "s4", "title": "Bug triage", "tags": ["debug"],
     "content": "List the likely root causes ranked by probability, and the one log line that would confirm each."},
    {"id": "s5", "title": "Meeting to action items", "tags": ["work"],
     "content": "Turn these notes into action items with an owner and a due date, then list open questions."},
    {"id": "s6", "title": "Reverse interview", "tags": ["career"],
     "content": "Ask me one question at a time to understand what I need before giving any advice."},
]
HISTORY = []
USAGE = {"used": 3, "limit": 15}


def api(route):
    req, path = route.request, route.request.url.split(".hf.space", 1)[1]
    js = lambda b: route.fulfill(status=200, content_type="application/json", body=json.dumps(b))
    if req.method == "POST" and path.startswith("/enhance/stream"):
        body = json.loads(req.post_data or "{}")
        mode, prompt = body.get("mode", "deep"), body.get("prompt", "")
        text = next((v for (k, s), v in REPLY.items() if s == mode and k in prompt), None) \
            or next((v for (k, s), v in REPLY.items() if s == mode), "…")
        USAGE["used"] += 1
        words = text.split(" ")
        events = [{"token": " ".join(words[i:i + 2]) + (" " if i + 2 < len(words) else "")} for i in range(0, len(words), 2)]
        events.append({"done": True, "failed": False, "log_id": f"log-{USAGE['used']}", "latency": 0.9,
                       "mode": mode, "model": "demo", "usage_today": {"used": USAGE["used"], "limit": USAGE["limit"], "tier": "free"},
                       "context_used": {"selected": 0, "auto_matched": 0, "passive_matched": 0}})
        route.fulfill(status=200, content_type="text/event-stream", body="".join(f"data: {json.dumps(e)}\n\n" for e in events))
    elif req.method == "GET" and path.startswith("/saved-prompts"):
        js({"prompts": SAVED})
    elif req.method == "GET" and path.startswith("/enhance/history"):
        js({"history": HISTORY})
    elif req.method == "GET" and path.startswith("/enhance/usage"):
        js({"count": USAGE["used"], "limit": USAGE["limit"]})
    elif req.method == "GET" and path.startswith("/feedback/mine"):
        js({"feedback": []})
    else:
        js([] if req.method == "GET" else {})


class Stage:
    def __init__(self, headed=True, width=1280, height=800, scale=2, profile=None):
        self.pw = sync_playwright().start()
        self._tmp = None if profile else tempfile.TemporaryDirectory()
        self.ctx = self.pw.chromium.launch_persistent_context(
            profile or self._tmp.name, channel="chromium", headless=not headed,
            viewport={"width": width, "height": height}, device_scale_factor=scale,
            locale="en-US", color_scheme="light",
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}",
                  "--disable-blink-features=AutomationControlled", "--hide-scrollbars"],
        )
        self.ctx.route("https://api.groq.com/**", provider)
        self.ctx.route("https://siddhm11-prompt-engine.hf.space/**", api)
        self.sw = self.ctx.service_workers[0] if self.ctx.service_workers else self.ctx.wait_for_event("serviceworker")
        self.ext_id = self.sw.url.split("/")[2]
        self.byok()

    def byok(self):
        key = LIVE_KEY or "gsk_demo"
        self.sw.evaluate(f"""chrome.storage.local.set({{ byok_provider: 'groq', byok_key: {json.dumps(key)},
            pm_data_consent_v1: true, pm_onboarded: true }})""")

    def sign_in(self):
        """A demo account against the fake server below (the token expires in 2100)."""
        jwt = "eyJhbGciOiJub25lIn0.eyJleHAiOjQxMDI0NDQ4MDAsInN1YiI6InUxIn0.x"
        self.sw.evaluate(f"""chrome.storage.local.set({{ token: '{jwt}', user_id: 'u1', email: 'you@example.com' }})""")

    def sign_out(self):
        self.sw.evaluate("chrome.storage.local.remove(['token', 'user_id', 'email'])")

    def set(self, obj):
        self.sw.evaluate(f"chrome.storage.local.set({json.dumps(obj)})")

    def page(self):
        return self.ctx.new_page()

    def close(self):
        self.ctx.close()
        self.pw.stop()


COMPOSER = "#prompt-textarea:visible, form textarea:visible, textarea:visible, div[contenteditable='true'][role='textbox']:visible"


def composer(pg, timeout=40000):
    loc = pg.locator(COMPOSER).first
    loc.wait_for(timeout=timeout)
    return loc
