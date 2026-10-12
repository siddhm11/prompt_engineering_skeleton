"""Drive simple mode (Improve on the chat box) through the pill harness.

The harness runs the real content.js with chrome.* and both backends faked
(extension/tests/harness-shim.js). Checks what the first-run script does not:

  compare    You wrote / In the chat box now; Put mine back; Keep
  style      one Style row; picking one with a rewrite in the box redoes it
  library    a click inserts; context is in the row menu; no second style picker
  reuse      a long draft brings the save-it-once tip, with Save
  free tier  the menu offers sign-in, not controls that need an account

    python scripts/serve_harness.py      # in another terminal, port 8765
    python scripts/check_simple_mode.py  # PM_HARNESS_URL to point elsewhere
"""
import os
import sys

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("Playwright is not installed: pip install playwright")

BASE = os.environ.get("PM_HARNESS_URL", "http://localhost:8765/tests/pill-harness.html")
CHANNEL = os.environ.get("PM_BROWSER_CHANNEL", "chrome")
TOKEN = "eyJhbGciOiJub25lIn0.eyJleHAiOjQxMDI0NDQ4MDAsInN1YiI6InUxIn0.x"
SHORT = "yo how do i make my resume better for data science jobs, i have like 2 yrs exp"
LONG = ("I'm a data analyst with 2 years of experience in Python, SQL and Tableau, applying for data "
        "science roles in fintech. I've led one churn model project end to end. How should I rewrite "
        "my resume summary for these roles?")
checks = 0


def check(cond, msg):
    global checks
    checks += 1
    if not cond:
        raise AssertionError(msg)


def page_for(browser, query, store):
    pg = browser.new_page(viewport={"width": 1280, "height": 800})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{BASE}?{query}")
    pg.evaluate(f"localStorage.setItem('pm', JSON.stringify({store}))")
    pg.reload()
    pg.wait_for_selector("#pm-simple", timeout=8000)
    pg.wait_for_timeout(900)
    pg.errors = errors
    return pg


def box(pg):
    return pg.evaluate("document.getElementById('composer').innerText.trim()")


def bar(pg):
    return pg.evaluate("document.getElementById('pm-simple').innerText.replace(/\\s+/g, ' ').trim()")


def improve(pg, text):
    pg.evaluate("document.getElementById('composer').focus(); document.execCommand('selectAll'); document.execCommand('delete')")
    pg.click("#composer")
    pg.keyboard.type(text)
    pg.wait_for_timeout(200)
    pg.click("#pm-simple [data-act='improve']")
    pg.wait_for_function("(document.getElementById('pm-simple')?.innerText || '').includes('Undo')", timeout=8000)
    pg.wait_for_timeout(300)


def main():
    signed_in = ('{"pm_data_consent_v1": true, "pm_simple_mode": true, "token": "%s", "user_id": "u1", '
                 '"email": "u@example.com", "pm_tip_shows": {"simple": 1}, "pm_stats": {"rewrites": 3}}' % TOKEN)
    with sync_playwright() as p:
        b = p.chromium.launch(channel=CHANNEL, headless=True)

        # ── Compare ──────────────────────────────────────────────────────
        pg = page_for(b, "simple=1", signed_in)
        quick = pg.evaluate("FAKE.text.quick")
        deep = pg.evaluate("FAKE.text.deep")
        improve(pg, SHORT)
        check(box(pg) == quick, "Improve writes the rewrite into the box")
        pg.click("#pm-simple [data-act='compare']")
        pg.wait_for_selector("#pm-card.pm-card-compare", timeout=4000)
        card = pg.inner_text("#pm-card")
        check("You wrote" in card and SHORT in card and "In the chat box now" in card and quick in card,
              "Compare shows what was typed above what is in the box")
        foot = [t.strip() for t in pg.locator("#pm-card .pm-card-foot button").all_inner_texts()]
        check(foot == ["Keep the rewrite", "Put mine back", "Save"], f"three plain actions, got {foot}")
        check("Replace" not in card and "Discard" not in card, "none of the classic card's Replace or Discard")
        pg.click("#pm-cmp-undo")
        pg.wait_for_timeout(500)
        check(box(pg) == SHORT, f"Put mine back restores exactly what was typed, got {box(pg)!r}")
        check(pg.locator("#pm-card.pm-card-visible").count() == 0, "and closes the comparison")

        # ── Style: one row, and it redoes the rewrite in the box ─────────
        improve(pg, SHORT)
        pg.click("#pm-simple [data-act='more']")
        menu = pg.inner_text("#pm-simple-menu")
        check(menu.count("Quick") == 1 and menu.count("Deep") == 1, f"one Style row, not two: {menu!r}")
        check("Compare with your original" not in menu and "Attach saved prompts" not in menu,
              "no second Compare, no second way into the library")
        pg.click("#pm-simple-menu [data-act='style'][data-style='deep']")
        pg.wait_for_function(f"document.getElementById('composer').innerText.trim() === {deep!r}", timeout=8000)
        # Finished, not just written: until the bar says Undo the stream is
        # still settling, and a style picked then only changes the default.
        pg.wait_for_function("(document.getElementById('pm-simple')?.innerText || '').includes('Undo')", timeout=8000)
        check(True, "picking Deep with a rewrite in the box rewrites it as Deep")
        check(pg.evaluate("JSON.parse(localStorage.getItem('pm')).pm_simple_style") == "deep", "and makes Deep the default")
        pg.click("#pm-simple [data-act='more']")
        pg.click("#pm-simple-menu [data-act='style'][data-style='quick']")
        pg.wait_for_function(f"document.getElementById('composer').innerText.trim() === {quick!r}", timeout=4000)
        check(pg.evaluate("FAKE.calls.filter(m => m === 'quick').length") == 2,
              "switching back to a version already made costs no new request")

        # ── Library: a click inserts ─────────────────────────────────────
        pg.click("#pm-simple [data-act='undo']")
        pg.wait_for_timeout(300)
        pg.evaluate("document.getElementById('composer').focus(); document.execCommand('selectAll'); document.execCommand('delete')")
        pg.click("#pm-simple [data-act='more']")
        pg.click("#pm-simple-menu [data-act='library']")
        pg.wait_for_selector("#pm-library .pm-lib-row", timeout=5000)
        check(pg.locator("#pm-library.pm-lib-simple").count() == 1, "the library knows it is in simple mode")
        foot = pg.inner_text("#pm-lib-foot")
        check("add to context" not in foot and "insert" in foot.lower(), f"its keys say Enter inserts, got {foot!r}")
        pg.click("#pm-library .pm-lib-row[data-i='0'] [data-act='more']")
        check("Use as context" in pg.inner_text("#pm-library .pm-lib-rowmenu"), "context is in the row menu")
        pg.click("#pm-library .pm-lib-row[data-i='0'] [data-act='more']")
        pg.click("#pm-library .pm-lib-row[data-i='0'] .pm-lib-title")
        pg.wait_for_timeout(600)
        check(box(pg).startswith("Review this diff like a senior engineer"), f"a click puts the prompt in the box, got {box(pg)!r}")
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(200)
        pg.evaluate("togglePanel(true)")
        pg.wait_for_timeout(400)
        pg.click("#pm-lib-more")
        lm = pg.inner_text("#pm-library .pm-lib-menu")
        check("Rewrite style" not in lm, "the library's menu has no second style picker in simple mode")
        check(not pg.errors, f"page errors: {pg.errors}")
        pg.close()

        # ── Reuse: a long draft brings the save-it-once tip ──────────────
        pg = page_for(b, "simple=1", signed_in)
        improve(pg, LONG)
        pg.wait_for_selector("#pm-tip[data-tip='reuse']", timeout=4000)
        tip = pg.inner_text("#pm-tip")
        check("Typing this background often?" in tip and "//" in tip and "Save it" in tip, f"the reuse tip, got {tip!r}")
        pg.click("#pm-tip .pm-tip-primary")
        pg.wait_for_selector("#pm-edit-content", timeout=4000)
        check(pg.input_value("#pm-edit-content") == LONG, "Save it opens the editor with the draft in it")
        check(pg.inner_text(".pm-modal-title") == "Save for reuse", "under its own heading")
        pg.click("#pm-edit-cancel")
        improve(pg, LONG + " Also mention leadership.")
        pg.wait_for_timeout(600)
        check(pg.locator("#pm-tip[data-tip='reuse']").count() == 0, "acted on, it does not come back")
        check(not pg.errors, f"page errors: {pg.errors}")
        pg.close()

        # ── Free tier: the menu offers sign-in, nothing that needs it ────
        pg = page_for(b, "anon=1", '{"pm_data_consent_v1": true, "pm_simple_mode": true, "pm_tip_shows": {"simple": 1}}')
        improve(pg, SHORT)
        check("More detail" not in bar(pg), f"the free bar offers what the free tier can do, got {bar(pg)!r}")
        pg.click("#pm-simple [data-act='more']")
        menu = pg.inner_text("#pm-simple-menu")
        check("Sign in with Google for more" in menu and "Library" not in menu and "Style" not in menu,
              f"the free menu, got {menu!r}")
        pg.click("#pm-simple [data-act='more']")
        pg.click("#pm-simple [data-act='compare']")
        pg.wait_for_selector("#pm-card.pm-card-compare", timeout=4000)
        foot = [t.strip() for t in pg.locator("#pm-card .pm-card-foot button").all_inner_texts()]
        check(foot == ["Keep the rewrite", "Put mine back"], f"no Save without an account, got {foot}")
        check(not pg.errors, f"page errors: {pg.errors}")
        pg.close()
        b.close()
    print(f"{checks} simple-mode checks PASS")


if __name__ == "__main__":
    main()
