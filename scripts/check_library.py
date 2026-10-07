"""Drive the real content.js through the library in Chrome.

Uses extension/tests/pill-harness.html: its FAKE_API answers the Prompt Memory
server (saved prompts, history, usage, feedback) and logs every call. Checks
the sheet on the pill, // at the caret, and the rail of attached prompts:
what the user sees, what lands in the chat box, what is sent to the server,
and what survives a reload.

    pip install playwright
    python3 scripts/check_library.py [--shots DIR]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_card_styles import serve  # noqa: E402  (same quiet local server)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("Playwright is not installed: pip install playwright")

checks = 0


def check(cond, msg):
    global checks
    checks += 1
    if not cond:
        raise AssertionError(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", help="directory for screenshots")
    args = ap.parse_args()
    httpd = serve()
    url = f"http://127.0.0.1:{httpd.server_port}/extension/tests/pill-harness.html"

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        ev = page.evaluate

        def load():
            page.goto(url)
            page.wait_for_function("document.getElementById('pm-trigger') && document.getElementById('pm-library')")
            page.wait_for_timeout(300)

        def shot(name):
            if args.shots:
                Path(args.shots).mkdir(parents=True, exist_ok=True)
                page.wait_for_timeout(350)   # let the 150ms open animation finish
                page.screenshot(path=str(Path(args.shots) / f"{name}.png"))

        def open_lib():
            page.keyboard.press("Meta+Shift+L")
            page.wait_for_selector("#pm-library:not([hidden])")
            page.wait_for_function("!document.querySelector('#pm-library .pm-lib-skeleton')")

        def rows():
            return [t.strip() for t in page.locator("#pm-library .pm-lib-row .pm-lib-title").all_inner_texts()]

        def composer():
            return ev("document.getElementById('composer').textContent")

        def set_box(text):
            """Type into the mock chat box with the caret at the end, as a user would."""
            ev("""t => { const c = document.getElementById('composer'); c.focus(); c.textContent = t;
                   const r = document.createRange(); r.selectNodeContents(c); r.collapse(false);
                   const s = getSelection(); s.removeAllRanges(); s.addRange(r);
                   c.dispatchEvent(new InputEvent('input', { bubbles: true })); }""", text)

        def calls(method, path):
            return ev(f"FAKE_API.calls.filter(c => c.method === '{method}' && c.path.startsWith('{path}'))")

        def rect(sel):
            return ev(f"(() => {{ const r = document.querySelector('{sel}')?.getBoundingClientRect(); return r && {{ l: r.left, t: r.top, r: r.right, b: r.bottom }}; }})()")

        def overlaps(a, b):
            return a and b and a["l"] < b["r"] and a["r"] > b["l"] and a["t"] < b["b"] and a["b"] > b["t"]

        load()
        ev("localStorage.clear(); sessionStorage.clear()")
        load()

        # ── signed out ──
        open_lib()
        check(ev("document.getElementById('pm-library').dataset.page") == "signin", "signed out: the sign-in page")
        check(page.locator("#pm-lib-signin").count() == 1, "with a Sign in button")
        check(page.locator("#pm-lib-more").count() == 1, "and ⋯ still there (style, voice, privacy work without an account)")
        page.keyboard.press("Escape")
        set_box("hello ")
        page.keyboard.type("//rev")
        check(page.locator("#pm-caret").count() == 0, "signed out: // is just text")

        # ── signed in ──
        ev("localStorage.clear(); sessionStorage.clear(); H.signIn()")
        load()
        page.hover("#pm-trigger")
        page.wait_for_timeout(250)
        chip = page.inner_text("#pm-library-btn").strip()
        check(chip == "Library" and "☰" not in chip, f"the chip is drawn, not a typed ☰, got {chip!r}")
        check(page.locator("#pm-library-btn svg").count() == 1, "chip icon is an SVG")
        page.click("#pm-library-btn")
        page.wait_for_selector("#pm-library:not([hidden])")
        page.wait_for_function("!document.querySelector('#pm-library .pm-lib-skeleton')")
        check(page.get_attribute("#pm-library-btn", "aria-expanded") == "true", "chip reports the sheet open")
        check(ev("document.activeElement.id") == "pm-lib-q", "search has focus on open")
        check(rows() == ["Code review template",
                         "You are my writing editor. Cut every sentence that does not earn its place and keep my voice.",
                         "Explain like a teacher", "Bug report triage", "Product spec critic"],
              f"saved prompts listed, an untitled one by its own words, got {rows()}")
        check(ev("""(() => { const p = document.querySelectorAll('#pm-library .pm-lib-row')[0].querySelector('.pm-lib-preview');
                     return getComputedStyle(p).whiteSpace === 'nowrap' && p.textContent.startsWith('Review this diff'); })()"""),
              "a named prompt shows its name and a line of its text")
        check(ev("""getComputedStyle(document.querySelector('#pm-library .pm-lib-untitled')).webkitLineClamp === '2'"""),
              "an unnamed one shows two lines of its own words")
        check(page.locator("#pm-library .pm-lib-row >> nth=1").locator(".pm-lib-preview").count() == 0,
              "an untitled prompt is not split into a made-up title and the rest")
        check(page.get_attribute("#pm-lib-q", "placeholder") == "Search 5 prompts", "placeholder counts prompts")

        # ── a tray on the chat box ──
        page.wait_for_timeout(200)                # the 150ms open animation scales it
        lib, box, send = rect("#pm-library"), rect("form"), rect(".send")
        check(abs(lib["l"] - box["l"]) <= 1 and abs(lib["r"] - box["r"]) <= 1,
              f"the tray is as wide as the chat box and lines up with it ({lib} vs {box})")
        check(lib["b"] <= box["t"] and 36 <= box["t"] - lib["b"] <= 44,
              f"it stands on the chat box, over the row the context chips land on, got a {box['t'] - lib['b']:.0f}px gap")
        check(not overlaps(lib, send) and lib["t"] >= 0, "off the Send button, and inside the window")
        listr, detr = rect("#pm-lib-list"), rect("#pm-lib-detail")
        check(listr["r"] <= detr["l"] + 1 and detr["r"] - detr["l"] > 300, "two panes: the list, and the prompt beside it")
        check(len(calls("GET", "/saved-prompts")) == 1, "one fetch of saved prompts")
        tags = [t.strip() for t in page.locator("#pm-library .pm-tray-tags button").all_inner_texts()]
        check(tags[0] == "All" and "#coding" in tags and "#writing" in tags, f"a row of the user's tags to filter by, got {tags}")
        shot("1-open")

        # ── the highlighted prompt, whole, in its pane ──
        detail = lambda: page.inner_text("#pm-lib-detail")
        check("Review this diff like a senior engineer" in detail() and "#coding" in detail() and "2d ago" in detail(),
              "the pane shows the highlighted prompt whole, with its tags and age")
        page.locator("#pm-library .pm-lib-row >> nth=3").hover()
        page.wait_for_timeout(40)
        check("Bug report" not in detail(), "a pointer crossing a row on its way somewhere does not change the pane")
        page.wait_for_timeout(250)
        check("the one log line that would confirm each" in detail(), "resting on a row shows it in the pane")
        page.mouse.move(300, 150)
        page.focus("#pm-lib-q")
        page.keyboard.press("ArrowDown")
        check("three decisions it leaves unmade" in detail(), "↓ moves the pane with the highlight")
        page.click("#pm-lib-detail [data-act='attach']")
        check(ev("[...selectedIds]") == ["p5"] and "In context" in page.inner_text("#pm-lib-detail [data-act='attach']"),
              "the pane's Add to context adds it, and says it is in context")
        page.click("#pm-lib-detail [data-act='attach']")
        check(ev("selectedIds.size") == 0, "and takes it out again")
        page.click("#pm-lib-detail [data-act='pin']")
        groups = [g.strip().lower() for g in page.locator("#pm-library .pm-lib-group").all_inner_texts()]
        check(rows()[0] == "Product spec critic" and groups == ["pinned", "recent"],
              f"pinning puts it first, under Pinned, got {rows()[:2]} {groups}")
        check("three decisions" in detail(), "and the pane stays on it")
        page.click("#pm-lib-detail [data-act='pin']")
        check(rows()[0] == "Code review template" and page.locator("#pm-library .pm-lib-group").count() == 0, "unpinning puts it back")
        page.click("#pm-library .pm-tray-tags button[data-tagfilter='writing']")
        check(len(rows()) == 1 and rows()[0].startswith("You are my writing editor"), f"a tag filters the list in one click, got {rows()}")
        page.click("#pm-library .pm-tray-tags button[data-tagfilter='']")
        check(len(rows()) == 5, "All brings every prompt back")

        # the keys after a click (seen live: a click left them on <body>, deaf).
        # On the last row, the one used last above, so the order checked
        # further down is not disturbed.
        page.locator("#pm-library .pm-lib-row[data-i] >> nth=4").click()
        check(ev("document.activeElement.id") == "pm-lib-q", "a click on a row leaves the keyboard in the tray")
        page.keyboard.press("ArrowDown")
        check(ev("libSel") == 0, f"so ↓ still moves the highlight after it, got {ev('libSel')}")
        foot = page.inner_text("#pm-lib-foot")
        check("1 in context" in foot and "add to context" in foot and "insert" in foot,
              f"the foot keeps its keys beside what is in context, got {foot!r}")
        page.keyboard.press("ArrowUp")
        page.keyboard.press("Enter")
        check(ev("selectedIds.size") == 0, "and ↵ takes the clicked one back out")
        page.click("#pm-lib-detail [data-act='attach']")
        check(ev("document.activeElement.id") == "pm-lib-q", "a button in the pane, redrawn away, hands the keyboard back too")
        page.click("#pm-lib-detail [data-act='attach']")
        page.click("#pm-lib-detail .pm-detail-text")
        check(ev("document.activeElement.id") == "pm-lib-q", "and so does a click on the prompt's words")
        page.dblclick("#pm-lib-detail .pm-detail-text", position={"x": 12, "y": 10})   # on "Read", not the blank under the text
        check(ev("String(getSelection()).trim()") != "", "a double click selects a word to copy, and keeps it")
        page.keyboard.press("ArrowDown")
        check(ev("libSel") == 0 and ev("document.activeElement.id") == "pm-lib-q", "and ↓ still moves the list from there")
        page.keyboard.press("ArrowUp")

        # edit, in the pane
        page.fill("#pm-lib-q", "spec")
        page.click("#pm-lib-detail [data-act='edit']")
        page.wait_for_selector("#pm-ed-content")
        check(page.input_value("#pm-ed-title") == "Product spec critic", "Edit opens the prompt in the pane's editor")
        page.fill("#pm-ed-content", "Read this spec and list the three decisions it leaves unmade. Be blunt.")
        page.keyboard.press("Meta+Enter")
        page.wait_for_function("FAKE_API.calls.some(c => c.method === 'PUT')")
        put = [c for c in ev("FAKE_API.calls") if c["method"] == "PUT"][-1]
        check(put["path"] == "/saved-prompts/p5" and put["body"] == {"content": "Read this spec and list the three decisions it leaves unmade. Be blunt."},
              f"⌘↵ saves only what changed, got {put}")
        page.wait_for_function("!document.getElementById('pm-ed-content') && document.getElementById('pm-lib-detail').textContent.includes('Be blunt')")
        check(ev("document.activeElement.id") == "pm-lib-q", "and the pane shows the saved prompt, keyboard back in the search")
        page.fill("#pm-lib-q", "")

        # a narrow window: one pane at a time
        page.set_viewport_size({"width": 700, "height": 900})
        page.wait_for_timeout(150)
        check(page.is_visible("#pm-lib-list") and page.is_hidden("#pm-lib-detail"), "a narrow tray shows the list alone")
        page.focus("#pm-lib-q")
        page.keyboard.press("ArrowRight")
        check(page.is_hidden("#pm-lib-list") and page.is_visible("#pm-lib-detail"), "→ opens the prompt in its place")
        page.keyboard.press("Escape")
        check(page.is_visible("#pm-lib-list") and ev("panelOpen"), "esc goes back to the list before closing")
        page.click("#pm-library .pm-lib-row >> nth=2 >> .pm-lib-open")
        check(page.is_visible("#pm-lib-detail") and "Explain the concept" in detail(), "a row's › opens it too")
        page.click("#pm-lib-detail [data-act='listback']")
        check(page.is_visible("#pm-lib-list"), "and its ‹ goes back")
        page.set_viewport_size({"width": 1440, "height": 900})
        page.fill("#pm-lib-q", "a")
        page.fill("#pm-lib-q", "")

        # ── ways out, every one of them on screen or in the user's hands ──
        page.click("#pm-lib-close")
        check(not ev("panelOpen") and ev("document.activeElement.id") == "composer",
              "× closes the sheet and hands the keyboard back to the chat box")
        open_lib()
        check(rows()[0] == "Product spec critic", f"a prompt used last time comes first the next time, got {rows()[:2]}")
        check(ev("JSON.parse(localStorage.getItem('pm')).pm_lib_local.uses.p5") > 0, "kept on this device")
        page.mouse.move(700, 200)
        page.mouse.wheel(0, 200)
        page.wait_for_timeout(100)
        check(not ev("panelOpen"), "turning the wheel over the conversation closes it")
        open_lib()
        # hover() waits for a list that is not being redrawn: the sheet draws
        # again when the saved prompts and the usage count arrive.
        page.locator("#pm-lib-list").hover()
        page.mouse.wheel(0, 60)
        page.wait_for_timeout(100)
        check(ev("panelOpen"), "the wheel inside the sheet only scrolls it")
        ev("document.getElementById('composer').focus()")      # focus moved without a click
        page.keyboard.type("x")
        page.wait_for_timeout(50)
        check(not ev("panelOpen"), "typing in the chat box closes it")
        set_box("")
        open_lib()
        ev("H.stream()")
        page.wait_for_timeout(50)
        check(not ev("panelOpen") and page.locator("#pm-card").count() == 1, "a rewrite card coming up closes it")
        ev("closeCard()")
        open_lib()

        # search and keys, on the server's order again
        ev("libUses = {}; libOrderUses = {}; saveLibLocal(); renderLibrary(); focusLibrarySearch()")
        page.keyboard.type("bug")
        check(rows() == ["Bug report triage"], f"search by text, got {rows()}")
        page.fill("#pm-lib-q", "#writ")
        check(rows()[0].startswith("You are my writing editor") and len(rows()) == 1, f"#tag search, got {rows()}")
        page.fill("#pm-lib-q", "zzz")
        check("Nothing matches" in page.inner_text("#pm-library .pm-lib-list"), "no-match message")
        page.fill("#pm-lib-q", "")
        page.keyboard.press("ArrowDown")
        active = page.get_attribute("#pm-lib-q", "aria-activedescendant")
        check(active == "pm-lib-row-1", f"↓ moves the highlight (aria-activedescendant), got {active}")
        page.keyboard.press("ArrowUp")
        page.keyboard.press("ArrowUp")
        check(page.get_attribute("#pm-lib-q", "aria-activedescendant") == "pm-lib-row-4", "↑ wraps to the last row")

        # ↵ ticks a saved prompt as context, and the sheet stays open for more
        page.keyboard.press("ArrowDown")          # wraps back to the first row
        page.keyboard.press("Enter")
        check(page.locator("#pm-rail .pm-rail-chip").count() == 1, "↵ attaches: a chip on the rail")
        check(ev("panelOpen"), "and the sheet stays open, so more can be picked")
        lib, rail = rect("#pm-library"), rect("#pm-rail")
        check(lib["b"] <= rail["t"] and not overlaps(lib, rail), f"the tray rises to stand on the chip, so it shows ({lib['b']} vs {rail['t']})")
        check(page.inner_text("#pm-rail .pm-rail-label").strip() == "Context for ⊕", "the rail says what the chips are for")
        check(page.is_visible("#pm-trigger .pm-pill-ctx") and page.inner_text("#pm-trigger .pm-pill-ctx") == "1",
              "⊕ counts the context its next rewrite carries")
        check("with 1 saved prompt as context" in page.get_attribute("#pm-trigger", "aria-label"), "and says so to a screen reader")
        check(page.locator("#pm-rail .pm-rail-chip.pm-rail-new").count() == 1, "a newly ticked prompt pops onto the rail")
        check(page.inner_text("#pm-rail .pm-rail-chip").strip() == "Code review template", f"the rail names it, got {page.inner_text('#pm-rail .pm-rail-chip')!r} {ev('[...selectedIds]')}")
        foot = page.inner_text("#pm-lib-foot")
        check("1 in context" in foot, f"the foot says so, got {foot!r}")
        check("for your next ⊕ rewrite" in foot, "and what context is for, with the chat box empty")
        check(ev("[...selectedIds]") == ["p1"], "selected for the next rewrite")
        check(ev("JSON.parse(sessionStorage.getItem('pm')).pm_attached")[0]["title"] == "Code review template",
              "kept in session storage with its title")
        shot("2-attached")

        # insert into an empty box
        page.keyboard.press("ArrowDown")
        page.keyboard.press("ArrowDown")
        check(page.inner_text("#pm-lib-detail [data-act='insert']").strip() == "Insert", "empty box: the pane offers Insert")
        page.keyboard.press("Meta+Enter")
        page.wait_for_selector("#pm-library", state="hidden")
        # Insert gives the editor a frame to see the selection before clearing.
        page.wait_for_function("document.getElementById('composer').textContent.length > 0", timeout=3000)
        check(composer().startswith("Explain the concept step by step"), f"inserted, got {composer()!r}")
        page.wait_for_function("document.getElementById('pm-trigger').dataset.state === 'applied'", timeout=3000)
        check(True, "the pill says Inserted once the write is verified")

        # a half-written box: Replace, and the Save row
        set_box("Turn these meeting notes into action items with owners")
        page.click("#pm-trigger")        # dismiss the Inserted receipt first
        open_lib()
        check(rows()[0].startswith("Save “Turn these meeting notes"), f"the box offered as a Save row, got {rows()[0]!r}")
        page.keyboard.press("ArrowDown")
        verb = page.inner_text("#pm-lib-detail [data-act='insert']").strip()
        check(verb == "Replace", f"box has text: the pane offers Replace, got {verb!r}")
        page.keyboard.press("ArrowUp")
        # ↵ on the Save row opens the save form on it; ↵ again saves
        page.keyboard.press("Enter")
        page.wait_for_selector("#pm-save")
        check(ev("document.activeElement.id") == "pm-save-title", "the form opens with its name field focused")
        check(page.input_value("#pm-save-title") == "", "the name starts empty: an unnamed prompt shows its words")
        check("Turn these meeting notes" in page.inner_text("#pm-save .pm-save-snip"), "the form shows what it will save")
        check(ev("panelOpen"), "and the sheet stays open under it")
        tags = [t.strip() for t in page.locator("#pm-save-tags button").all_inner_texts()]
        check("#coding" in tags and "#writing" in tags, f"the user's own tags are one click away, got {tags}")
        page.click("#pm-save-tags button[data-tag='writing']")
        check(page.get_attribute("#pm-save-tags button[data-tag='writing']", "aria-pressed") == "true", "a click picks a tag")
        page.fill("#pm-save-newtags", "meetings, #notes")
        shot("5-save-form")
        page.focus("#pm-save-title")
        check(ev("panelOpen") and page.locator("#pm-save").count() == 1, "working in the form leaves the sheet open")
        page.keyboard.press("Enter")
        page.wait_for_function("FAKE_API.calls.some(c => c.method === 'POST' && c.path === '/saved-prompts')")
        post = calls("POST", "/saved-prompts")[-1]["body"]
        check("title" not in post and sorted(post.get("tags", [])) == ["meetings", "notes", "writing"],
              f"saved unnamed, with the picked and typed tags, got {post}")
        page.wait_for_selector("#pm-save", state="detached", timeout=3000)
        check(True, "the form goes once the server says yes")
        page.wait_for_function("!document.querySelector('#pm-library .pm-lib-row-save') && "
                               "document.querySelectorAll('#pm-library .pm-lib-row').length === 6")
        check("Undo" in page.inner_text(".pm-toast"), "the toast offers Undo")
        toast = rect(".pm-toast")
        for what, sel in (("the context chips", "#pm-rail"), ("the chat box", "form"), ("the open library", "#pm-library")):
            check(not overlaps(toast, rect(sel)), f"the toast stays off {what}")
        check(toast["r"] >= 1440 - 60, "and sits on the pill's side of the window")
        check("Turn these meeting notes" in rows()[0], f"saved and listed first, got {rows()[:2]}")
        check(not any(r.startswith("Save “") for r in rows()), "the Save row goes once saved")
        check("Rewrite with it" in page.inner_text("#pm-lib-foot"), "with text in the box, the foot offers the rewrite")
        # The harness routes rewrites to its fake direct path; that the ticked
        # ids ride with a server rewrite is checked in check_extension_e2e.py.
        before = ev("FAKE.calls.length")
        page.click("#pm-lib-foot [data-act='rewrite']")
        page.wait_for_function(f"FAKE.calls.length > {before}")
        check(ev("cardState") in ("streaming", "ready"), "Rewrite starts the rewrite of what is in the chat box")
        check(not ev("panelOpen"), "and the sheet goes as the card comes up")
        ev("closeCard()")
        open_lib()

        # delete, with an inline confirm
        page.fill("#pm-lib-q", "spec")
        page.click("#pm-lib-detail [data-act='ask']")
        check("Delete “Product spec critic”?" in page.inner_text("#pm-lib-detail .pm-lib-confirm"), "the pane asks first")
        page.click("#pm-lib-detail [data-act='keepit']")
        check(rows() == ["Product spec critic"] and page.locator("#pm-lib-detail .pm-lib-confirm").count() == 0, "Keep keeps it")
        page.click("#pm-lib-detail [data-act='ask']")
        page.click("#pm-lib-del")
        page.wait_for_function("FAKE_API.calls.some(c => c.method === 'DELETE')")
        page.wait_for_timeout(200)
        check(calls("DELETE", "/saved-prompts/p5"), "DELETE sent")
        check(rows() == [] or "Product spec critic" not in rows(), "and it is gone")
        page.fill("#pm-lib-q", "")

        # History (it was "Recent", which read as "recently saved")
        check([t.strip() for t in page.locator("#pm-library .pm-lib-views button").all_inner_texts()] == ["Saved", "History"],
              "the two lists are Saved and History")
        page.click("#pm-lib-view-recent")
        page.wait_for_function("document.querySelectorAll('#pm-library .pm-lib-row').length === 2")
        check(page.get_attribute("#pm-lib-q", "placeholder") == "Search your rewrite history", "History says what it holds")
        check(rows()[0].startswith("Show me how to sort"), f"past rewrites listed, got {rows()}")
        check("from “hw do i sort" in page.inner_text("#pm-library .pm-lib-row .pm-lib-preview"), "with what they came from")
        page.keyboard.press("Enter")
        page.wait_for_selector("#pm-library", state="hidden")
        page.wait_for_function("document.getElementById('composer').textContent.startsWith('Show me how to sort')", timeout=3000)
        check(composer().startswith("Show me how to sort"), "a recent rewrite inserts")
        page.wait_for_function("FAKE_API.calls.some(c => c.path === '/enhance/accept')")
        check(calls("POST", "/enhance/accept")[0]["body"]["log_id"] == "h1", "and is approved by its log id")

        # ── a centred chat box holding a long draft (ChatGPT's new chat, seen live) ──
        ev("""document.body.classList.add('center');
              const c = document.getElementById('composer');
              c.innerHTML = Array.from({ length: 6 }, (_, k) => '<div>line ' + (k + 1) + ' of a long draft in the chat box</div>').join('');""")
        page.wait_for_timeout(100)
        open_lib()
        page.wait_for_timeout(200)
        lib, send, box = rect("#pm-library"), rect(".send"), rect("form")
        check(lib["b"] - lib["t"] >= 330 and lib["b"] <= box["t"], f"with room above a centred box the tray stands on it, got {lib}")
        page.keyboard.press("Escape")
        page.set_viewport_size({"width": 1440, "height": 760})   # now there is not
        open_lib()
        page.wait_for_timeout(200)
        lib, send, box = rect("#pm-library"), rect(".send"), rect("form")
        check(ev("document.getElementById('pm-library').dataset.overBox") == "true" and lib["b"] - lib["t"] >= 400,
              f"without it, the tray comes down over the box's text to keep its height, got {lib['b'] - lib['t']:.0f}px")
        check(not overlaps(lib, send) and lib["t"] >= 0, "but never over Send, and inside the window")
        page.keyboard.press("Escape")
        page.set_viewport_size({"width": 1440, "height": 900})
        ev("document.body.classList.remove('center'); document.getElementById('composer').textContent = ''")
        page.wait_for_timeout(100)

        # ── the tray holds its size as chips land (seen live: a second pick shrank it) ──
        page.set_viewport_size({"width": 1440, "height": 820})
        ev("document.body.classList.add('center'); clearAttachments()")
        page.wait_for_timeout(100)
        open_lib()
        page.wait_for_timeout(200)
        sizes = [rect("#pm-library")]
        for i in range(4):
            page.locator("#pm-library .pm-lib-row[data-i]").nth(i).click()
            page.wait_for_timeout(150)
            sizes.append(rect("#pm-library"))
        check(all(sz == sizes[0] for sz in sizes), f"ticking one prompt after another neither moves nor shrinks the tray, got {sizes}")
        rail = rect("#pm-rail")
        check(rail["b"] - rail["t"] <= 27 and rail["b"] <= rect("form")["t"] and not overlaps(rail, rect("#pm-library")),
              f"the chips keep to their one row, between the tray and the box, got {rail}")
        more = page.locator("#pm-rail .pm-rail-more")
        titles = ev("[...selectedIds].map((id) => attachTitles.get(id))")
        n = int(more.inner_text().lstrip("+")) if more.count() == 1 else 0
        shown = page.locator("#pm-rail .pm-rail-chip:not([hidden])").count()
        check(n >= 1 and shown + n == 4 and more.get_attribute("title") == ", ".join(titles[:n]),
              f"the oldest fold into +{n}, which names them, got {shown} shown")
        check(page.locator("#pm-rail .pm-rail-chip:not([hidden])").last.inner_text().strip() == titles[-1],
              f"and the one just picked stays in view ({titles[-1]!r})")
        page.keyboard.press("Escape")
        page.wait_for_timeout(100)
        check(page.locator("#pm-rail .pm-rail-more").count() == 0 and page.locator("#pm-rail .pm-rail-chip[hidden]").count() == 0,
              "with the tray closed every chip shows again")
        ev("clearAttachments(); document.body.classList.remove('center')")
        page.set_viewport_size({"width": 1440, "height": 900})

        # ── drag its edges to size it, kept for next time ──
        open_lib()
        page.wait_for_timeout(200)
        before = rect("#pm-library")
        g = rect("#pm-library .pm-tray-grip-n")
        page.mouse.move((g["l"] + g["r"]) / 2, g["t"] + 3)
        page.mouse.down()
        page.mouse.move((g["l"] + g["r"]) / 2, g["t"] + 3 - 120, steps=6)
        page.mouse.up()
        after = rect("#pm-library")
        check(abs((after["b"] - after["t"]) - (before["b"] - before["t"]) - 120) <= 2 and abs(after["b"] - before["b"]) <= 1,
              f"dragging the top edge up makes it taller, its foot still on the box, got {before} -> {after}")
        g = rect("#pm-library .pm-tray-grip-e")
        page.mouse.move(g["r"] - 3, (g["t"] + g["b"]) / 2)
        page.mouse.down()
        page.mouse.move(g["r"] - 3 + 60, (g["t"] + g["b"]) / 2, steps=6)
        page.mouse.up()
        wide = rect("#pm-library")
        check(abs((wide["r"] - wide["l"]) - (after["r"] - after["l"]) - 120) <= 2
              and abs((wide["l"] + wide["r"]) / 2 - (after["l"] + after["r"]) / 2) <= 1,
              f"dragging a side widens it both ways, centred on the box, got {after} -> {wide}")
        check(ev("panelOpen"), "and resizing does not close it")
        g = rect("#pm-library .pm-tray-grip-n")
        page.mouse.move((g["l"] + g["r"]) / 2, g["t"] + 3)
        page.mouse.down()
        page.mouse.move((g["l"] + g["r"]) / 2, 1, steps=6)
        page.mouse.up()
        wide = rect("#pm-library")
        check(ev("panelOpen") and wide["t"] >= 12 and abs(wide["b"] - after["b"]) <= 1,
              f"dragged past the window's top it stops inside it, open, got {wide}")
        page.keyboard.press("Escape")
        check(ev("JSON.parse(localStorage.getItem('pm')).pm_tray_size")["h"] == round(wide["b"] - wide["t"]), "the size is kept on this device")
        load()
        open_lib()
        page.wait_for_timeout(200)
        check(rect("#pm-library") == wide, f"and the tray opens at it next time, got {rect('#pm-library')} not {wide}")
        page.set_viewport_size({"width": 1440, "height": 600})
        page.wait_for_timeout(150)
        small = rect("#pm-library")
        check(small["t"] >= 12 and small["b"] <= rect("form")["t"], f"in a shorter window it still fits above the box, got {small}")
        page.set_viewport_size({"width": 1440, "height": 900})
        page.dblclick("#pm-library .pm-tray-grip-n")
        page.wait_for_timeout(100)
        check(rect("#pm-library") == before, f"a double-click on an edge puts back the usual size, got {rect('#pm-library')}")
        check(ev("JSON.parse(localStorage.getItem('pm')).pm_tray_size") == {"w": 0, "h": 0}, "and forgets the dragged one")
        page.keyboard.press("Escape")

        # ── keys where they act: tooltips with keycaps ──
        open_lib()
        page.hover("#pm-lib-close")
        page.wait_for_timeout(120)
        check(page.locator("#pm-keytip:not([hidden])").count() == 0, "a pointer passing over a control does not pop a tip")
        page.wait_for_selector("#pm-keytip:not([hidden])", timeout=1500)
        check(page.inner_text("#pm-keytip span >> nth=0") == "Close" and page.locator("#pm-keytip kbd").all_inner_texts() == ["Esc"],
              "resting on × names it and draws its key")
        tip, btn = rect("#pm-keytip"), rect("#pm-lib-close")
        check(tip["b"] <= btn["t"], "above the control, not over it")
        check(page.get_attribute("#pm-lib-close", "title") is None, "and no native tooltip doubles it")
        page.hover("#pm-library .pm-lib-row[aria-checked] >> nth=0")     # a saved prompt, not the Save row
        page.wait_for_timeout(250)                                         # rests: the pane follows
        page.hover("#pm-lib-detail [data-act='insert']")
        page.wait_for_timeout(80)
        check(page.locator("#pm-keytip:not([hidden])").count() == 1 and "into the chat box" in page.inner_text("#pm-keytip"),
              "moving to the next control while warm shows its tip at once")
        check(len(page.locator("#pm-keytip kbd").all_inner_texts()) == 2, "⌘↵ drawn as its two keys")
        page.mouse.move(300, 150)
        page.wait_for_timeout(50)
        check(page.locator("#pm-keytip:not([hidden])").count() == 0, "and it goes with the pointer")
        page.keyboard.press("Escape")

        # ── the keyboard map ──
        ev("document.activeElement.blur()")          # on the page, not in a text box
        page.keyboard.press("?")
        page.wait_for_selector("#pm-keys .pm-keys")
        check(page.locator("#pm-keys .pm-kb-group").count() == 5, "? opens the map with every group side by side")
        check(page.inner_text("#pm-keys .pm-kb-here .pm-kb-cap").startswith("ANYWHERE ON THE PAGE") or
              page.inner_text("#pm-keys .pm-kb-here .pm-kb-cap").lower().startswith("anywhere on the page"),
              "it lights the group for where the user is")
        caps = page.locator("#pm-keys .pm-kb-group >> nth=0").locator(".pm-kb-row >> nth=0").locator("kbd").all_inner_texts()
        check(len(caps) == 3, f"a chord is drawn as the keys it is pressed with, got {caps}")
        check(ev("document.activeElement.closest('#pm-keys') !== null"), "the keyboard is in the map")
        page.keyboard.press("Escape")
        check(page.locator("#pm-keys").count() == 0, "esc closes it")
        page.hover("#pm-trigger")
        page.click("#pm-help-btn")
        page.wait_for_selector("#pm-keys .pm-keys")
        check(page.get_attribute("#pm-help-btn", "aria-expanded") == "true", "the Shortcuts chip opens it, and says so")
        page.mouse.click(20, 450)                    # the scrim
        check(page.locator("#pm-keys").count() == 0 and page.get_attribute("#pm-help-btn", "aria-expanded") == "false",
              "a click outside closes it")
        open_lib()
        page.click("#pm-lib-more")
        page.click("#pm-library [data-act='shortcuts']")
        page.wait_for_selector("#pm-keys .pm-keys")
        check("library" in page.inner_text("#pm-keys .pm-keys-here").lower(), "from the library's ⋯, the library's keys are lit")
        page.keyboard.press("Escape")
        check(ev("panelOpen") and ev("document.activeElement.id") == "pm-lib-q",
              "esc closes the map and gives the keyboard back to the library")
        page.keyboard.press("Escape")
        ev("window.FAKE_SHORTCUT = ''; assignedShortcut = null; document.activeElement.blur()")
        page.keyboard.press("?")
        page.wait_for_function("document.querySelector('#pm-keys .pm-kb-unset')")
        check("Not set" in page.inner_text("#pm-keys .pm-kb-unset"), "a rewrite key Chrome did not assign is not promised")
        shot("7-keymap")
        page.keyboard.press("Escape")
        ev("window.FAKE_SHORTCUT = undefined; assignedShortcut = null")

        # ── save a prompt already sent, from the conversation ──
        msg = page.locator("[data-message-author-role='user'] >> nth=0")
        msg.hover()
        page.wait_for_selector("#pm-msg-save:not([hidden])", timeout=2000)
        shot("6-bookmark")
        b = rect("#pm-msg-save")
        words = ev("""(() => { const r = document.createRange(); r.selectNodeContents(document.querySelector("[data-message-author-role='user']"));
                       const b = r.getBoundingClientRect(); return { l: b.left, t: b.top }; })()""")
        check(b["r"] <= words["l"] and abs(b["t"] - words["t"]) <= 8, f"resting on a sent prompt shows a bookmark beside its words ({b} vs {words})")
        page.mouse.move(300, 150)
        page.wait_for_timeout(450)
        check(page.is_hidden("#pm-msg-save"), "and it goes when the pointer does")
        msg.hover()
        page.wait_for_selector("#pm-msg-save:not([hidden])", timeout=2000)
        page.hover("#pm-msg-save")
        page.wait_for_timeout(400)
        check(page.is_visible("#pm-msg-save"), "crossing to the bookmark keeps it")
        page.click("#pm-msg-save")
        page.wait_for_selector("#pm-save")
        check("whitening gel" in page.inner_text("#pm-save .pm-save-snip"), "it opens the save form on that prompt")
        page.keyboard.press("Enter")
        page.wait_for_selector("#pm-save", state="detached", timeout=3000)
        post = calls("POST", "/saved-prompts")[-1]["body"]
        check(post["content"] == "can you check this whitening gel, is it safe for enamel", f"and saves its words, got {post}")
        new_id = ev("FAKE_API.prompts[0].id")
        page.click(".pm-toast .pm-toast-action")
        page.wait_for_function(f"FAKE_API.calls.some(c => c.method === 'DELETE' && c.path === '/saved-prompts/{new_id}')", timeout=3000)
        check(True, "Undo on its toast deletes what was just saved")
        # the way ChatGPT marks the user's side now, and Gemini with its hidden "You said"
        for sel, words in (("[data-markdown-text-tone='user-message'] p", "and how long should I use it each day"),
                           ("user-query .query-text", "which one is cheaper per week")):
            page.hover(sel)
            page.wait_for_selector("#pm-msg-save:not([hidden])", timeout=2000)
            page.hover("#pm-msg-save")
            page.click("#pm-msg-save")
            page.wait_for_selector("#pm-save")
            snip = page.inner_text("#pm-save .pm-save-snip").strip()
            check(snip == words, f"the bookmark reads {sel.split()[0]}'s words and nothing else, got {snip!r}")
            page.keyboard.press("Escape")
            page.wait_for_selector("#pm-save", state="detached")

        # ⋯: default style, count, privacy, feedback
        page.click("#pm-trigger")
        open_lib()
        page.click("#pm-lib-more")
        check("9 of 15 rewrites used today" in page.inner_text("#pm-library .pm-lib-menu"), "⋯ shows today's count")
        page.click("#pm-library [data-style='quick']")
        check(ev("currentMode") == "quick" and ev("JSON.parse(localStorage.getItem('pm')).pm_mode") == "quick",
              "⋯ sets and stores the default style")
        check(page.get_attribute("#pm-library [data-style='quick']", "aria-pressed") == "true", "and shows it")
        page.click("#pm-library [data-style='deep']")
        page.click("#pm-library [data-act='privacy']")
        check(ev("document.getElementById('pm-library').dataset.page") == "privacy", "privacy page")
        check(not page.is_checked("#pm-tracking-toggle") and page.is_checked("#pm-context-toggle") and page.is_checked("#pm-slash-toggle"),
              "switches show the current settings: tracking starts off, as the privacy policy says")
        check(ev("promptTrackingEnabled") is False, "and nothing is tracked until it is turned on")
        page.click("#pm-tracking-toggle")
        check(ev("JSON.parse(localStorage.getItem('pm')).pm_tracking") is True and ev("promptTrackingEnabled") is True,
              "tracking on is stored and applied")
        page.click("#pm-tracking-toggle")
        check(ev("JSON.parse(localStorage.getItem('pm')).pm_tracking") is False and ev("promptTrackingEnabled") is False,
              "and off again")
        page.keyboard.press("Escape")
        check(ev("document.getElementById('pm-library').dataset.page") == "list", "esc on a page goes back to the list")
        page.click("#pm-lib-more")
        page.click("#pm-library [data-act='feedback']")
        page.click("#pm-feedback-submit")
        check("few words" in page.inner_text("#pm-feedback-status"), "empty feedback is refused")
        page.fill("#pm-feedback-message", "The new library is easier to use.")
        page.click("#pm-feedback-submit")
        page.wait_for_function("document.getElementById('pm-feedback-status')?.textContent.includes('Sent')")
        check(calls("POST", "/feedback")[0]["body"]["message"] == "The new library is easier to use.", "feedback sent")
        page.click("#pm-lib-back")

        # closing
        page.keyboard.press("Escape")
        page.wait_for_selector("#pm-library", state="hidden")
        check(ev("document.activeElement.id") == "composer", "esc returns the keyboard to the chat box")
        open_lib()
        page.mouse.click(700, 200)
        page.wait_for_selector("#pm-library", state="hidden")
        check(True, "a click elsewhere closes it")

        # a low daily allowance shows in the foot
        ev("FAKE_API.usage = { count: 13, limit: 15 }")
        ev("clearAttachments()")
        open_lib()
        page.wait_for_function("document.getElementById('pm-lib-foot')?.textContent.includes('left today')")
        check("2 rewrites left today" in page.inner_text("#pm-lib-foot"), "the foot warns at three or fewer")
        page.keyboard.press("Escape")

        # ── // at the caret ──
        set_box("Before I merge, can you ")
        page.keyboard.type("//rev")
        page.wait_for_selector("#pm-caret")
        check([t.strip() for t in page.locator("#pm-caret .pm-lib-title").all_inner_texts()] == ["Code review template"],
              "//rev filters to the matching prompt")
        shot("3-slash")
        page.keyboard.press("Enter")
        page.wait_for_timeout(200)
        check(composer() == "Before I merge, can you Review this diff like a senior engineer: correctness first, then naming, "
                             "then tests. Flag anything that changes behaviour.", f"↵ inserts where // was, got {composer()!r}")
        check(page.locator("#pm-caret").count() == 0, "and closes")

        set_box("Please look at ")
        page.keyboard.type("//bug")
        page.wait_for_selector("#pm-caret")
        page.keyboard.press("Tab")
        page.wait_for_timeout(150)
        check(composer().strip() == "Please look at", f"⇥ attaches and drops the //query, got {composer()!r}")
        check("Bug report triage" in page.inner_text("#pm-rail"), "the rail names what ⇥ attached")

        set_box("hmm ")
        page.keyboard.type("//exp")
        page.wait_for_selector("#pm-caret")
        page.keyboard.press("Escape")
        check(page.locator("#pm-caret").count() == 0 and composer() == "hmm //exp", "esc closes and leaves the text alone")
        page.keyboard.type("l")
        check(page.locator("#pm-caret").count() == 0, "and stays shut while that // is still being typed")

        for text in ["see https://example.com/a", "a//b and c//d"]:
            set_box("")
            opened = False
            for ch in text:
                page.keyboard.type(ch)
                opened = opened or page.locator("#pm-caret").count() > 0
            check(not opened, f"{text!r} never opens the menu")

        set_box("x ")
        page.keyboard.type("//zzzz")
        page.wait_for_selector("#pm-caret")
        check("No saved prompt matches" in page.inner_text("#pm-caret"), "no match is said")
        prevented = ev("""(() => { const e = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
                          document.getElementById('composer').dispatchEvent(e); return e.defaultPrevented; })()""")
        check(prevented is False and page.locator("#pm-caret").count() == 0, "with nothing to pick, Enter is the host's (sends)")

        # ── // with more prompts than fit: it scrolls, and lists every match ──
        ev("""FAKE_API.prompts.push(...Array.from({ length: 10 }, (_, k) => ({ id: 'x' + k, title: 'Extra prompt ' + (k + 1),
                content: 'Extra body number ' + (k + 1) + '.', tags: ['extra'] }))); fetchSavedPrompts()""")
        page.wait_for_function("savedPrompts.length === 15")
        set_box("x ")
        page.keyboard.type("//extra")
        page.wait_for_selector("#pm-caret .pm-caret-row")
        check(page.locator("#pm-caret .pm-caret-row").count() == 10, "every match is listed, not the first six")
        check("10" in page.inner_text("#pm-caret .pm-caret-head b"), "the head counts the matches")
        check(ev("(() => { const l = document.querySelector('#pm-caret .pm-caret-list'); return l.scrollHeight > l.clientHeight; })()"),
              "ten rows overflow the menu, so it has to scroll")
        # hover() rather than a measured point: the menu redraws on every
        # selectionchange, and a box read mid-redraw comes back empty.
        page.locator("#pm-caret .pm-caret-list").hover()
        page.mouse.wheel(0, 160)
        page.wait_for_timeout(250)
        top = ev("document.querySelector('#pm-caret .pm-caret-list').scrollTop")
        check(top > 0, f"the wheel scrolls the list and it stays scrolled (scrollTop {top})")
        ev("window.dispatchEvent(new Event('scroll'))")
        check(ev("document.querySelector('#pm-caret .pm-caret-list').scrollTop") == top,
              "a page scroll moves the menu without redrawing it back to the top")
        for _ in range(9):
            page.keyboard.press("ArrowDown")
        sel_in_view = ev("""(() => { const l = document.querySelector('#pm-caret .pm-caret-list').getBoundingClientRect();
                              const r = document.querySelector('#pm-caret .pm-caret-row.pm-sel').getBoundingClientRect();
                              return r.top >= l.top - 1 && r.bottom <= l.bottom + 1; })()""")
        check(sel_in_view, "↓ past the fold keeps the highlighted row in view")
        check("Extra prompt 10" in page.inner_text("#pm-caret .pm-caret-row.pm-sel"), "↓×9 reaches the tenth prompt")
        page.keyboard.press("Enter")
        page.wait_for_timeout(200)
        check(composer() == "x Extra body number 10.", f"↵ inserts the tenth prompt, got {composer()!r}")
        ev("FAKE_API.prompts = FAKE_API.prompts.filter((p) => !String(p.id).startsWith('x')); fetchSavedPrompts()")
        page.wait_for_function("savedPrompts.length === 5")

        # ── the rail ──
        set_box("")
        page.wait_for_selector("#pm-rail:not([hidden])")
        rail, frame = rect("#pm-rail"), rect("form")
        check(rail["b"] <= frame["t"], f"the rail sits above the chat box's frame, not on it ({rail['b']} vs {frame['t']})")
        load()
        page.wait_for_selector("#pm-rail:not([hidden])")
        check("Bug report triage" in page.inner_text("#pm-rail"), "attachments survive a reload")
        ev("H.type(H.ORIG)")
        page.click("#pm-trigger")
        page.wait_for_function("cardState === 'ready'")
        page.wait_for_timeout(100)
        check(ev("document.getElementById('pm-rail').hidden") is True, "the rail steps aside for the card")
        page.click("#pm-card-min")
        page.wait_for_timeout(250)
        check(ev("document.getElementById('pm-rail').hidden") is False, "and returns when the card folds")
        ev("closeCard()")
        page.click("#pm-rail [data-act='railadd']")
        page.wait_for_selector("#pm-library:not([hidden])")
        check(True, "+ Context opens the library")
        page.keyboard.press("Escape")
        page.click("#pm-rail .pm-rail-chip button")
        check(page.locator("#pm-rail").count() == 0 and ev("selectedIds.size") == 0, "× on the chip detaches")

        # a deleted prompt is dropped from the attachments
        ev("toggleAttachment(savedPrompts.find(p => p.id === 'p4'))")
        ev("FAKE_API.prompts = FAKE_API.prompts.filter(p => p.id !== 'p4')")
        open_lib()
        page.wait_for_function("selectedIds.size === 0")
        check(page.locator("#pm-rail").count() == 0, "attachments whose prompt was deleted are forgotten")
        page.keyboard.press("Escape")

        if args.shots:
            page.click("text=light")
            ev("toggleAttachment(savedPrompts[0])")
            open_lib()
            shot("4-light-host")
            page.keyboard.press("Escape")
            page.click("text=light")
            ev("clearAttachments()")

        # ── a hostile host page ──
        ev("""document.head.insertAdjacentHTML('beforeend',
              '<style>button{width:32px!important;padding:0!important}input{border:3px solid red}</style>')""")
        page.hover("#pm-trigger")
        page.wait_for_timeout(250)
        w = ev("document.getElementById('pm-library-btn').getBoundingClientRect().width")
        check(w > 60, f"the chip keeps its size against host button rules, got {w}px")
        stack = ev("document.elementsFromPoint(1408, 860).map(e => e.id || e.tagName)[0]")
        check(stack in ("path", "svg", "SPAN", "pm-trigger"), f"⊕ stays clickable, top element {stack}")

        # ── the pill on the box's corner and the chips on its edge share a row (Claude, seen live) ──
        page.set_viewport_size({"width": 1000, "height": 800})
        ev("""clearAttachments(); savedPrompts.slice(0, 3).forEach((p) => toggleAttachment(p));
              H.type(H.ORIG); H.stream(); H.done(); hideCard();""")
        page.wait_for_timeout(400)
        pill, rail, box = rect("#pm-trigger"), rect("#pm-rail"), rect("form")
        check(pill["b"] <= box["t"] + 1, f"a wide pill steps up onto the box's corner here ({pill} vs {box})")
        check(not overlaps(rail, pill), f"and the chips stop short of it ({rail} vs {pill})")
        ev("closeCard(); clearAttachments()")
        page.set_viewport_size({"width": 1440, "height": 900})

        check(not errors, f"page errors: {errors}")
        page.close()
        reach_the_chip_from_anywhere(browser, url)
        keys_on_windows(browser, url)
        browser.close()
    httpd.shutdown()
    print(f"{checks} library checks PASS")


WINDOWS_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def keys_on_windows(browser, url):
    """The same tray on Windows: every key spelled the way a Windows keyboard
    prints it. Gluing Ctrl+ to Mac glyphs drew Ctrl+↵ and Ctrl+⇧V."""
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, user_agent=WINDOWS_UA)
    ctx.add_init_script("Object.defineProperty(navigator, 'platform', { get: () => 'Win32' })")
    page = ctx.new_page()
    page.goto(url)
    page.wait_for_function("document.getElementById('pm-library')")
    page.evaluate("localStorage.clear(); sessionStorage.clear(); H.signIn()")
    page.goto(url)
    page.wait_for_function("document.getElementById('pm-library')")
    page.wait_for_timeout(300)
    page.keyboard.press("Control+Shift+L")
    page.wait_for_selector("#pm-library:not([hidden])")
    page.wait_for_function("!document.querySelector('#pm-library .pm-lib-skeleton')")
    foot = page.locator("#pm-lib-foot kbd").all_inner_texts()
    check(foot[:2] == ["Enter", "Ctrl+Enter"], f"Windows: the tray's foot says Enter and Ctrl+Enter, got {foot}")
    page.hover("#pm-lib-detail [data-act='insert']")
    page.wait_for_selector("#pm-keytip:not([hidden])", timeout=1500)
    check(page.locator("#pm-keytip kbd").all_inner_texts() == ["Ctrl", "Enter"], "Windows: Insert's tooltip draws Ctrl and Enter")
    page.click("#pm-lib-more")
    check(page.inner_text(".pm-lib-mi[data-act='voice'] span") == "Ctrl+Shift+V", "Windows: the menu writes Ctrl+Shift+V")
    page.click("[data-act='shortcuts']")
    page.wait_for_selector("#pm-keys:not([hidden])")
    caps = page.locator("#pm-keys kbd").all_inner_texts()
    check(not any(c in ("↵", "⇧", "⌘", "⇥") for c in caps), f"Windows: no Mac glyph anywhere on the map, got {sorted(set(caps))}")
    check("Enter" in caps and "Shift" in caps and "Ctrl" in caps, "but Enter, Shift and Ctrl are there")
    ctx.close()


def reach_the_chip_from_anywhere(browser, url):
    """Hover ⊕, drift to the Library chip the way a hand does, click: the
    library must open wherever the pill is. The chip used to be revealed by a
    CSS :hover on ⊕, lost in the gap on the way over; this walks the pill
    through every dock, height, layout and width the chip's placement varies
    with, and approaches along a curved path that overshoots and comes back."""
    cases = 0
    for vw, vh in [(1440, 900), (1280, 720), (800, 600)]:
        page = browser.new_page(viewport={"width": vw, "height": vh})
        page.goto(url)
        page.wait_for_timeout(400)
        page.evaluate("localStorage.clear(); sessionStorage.clear(); H.signIn()")
        page.goto(url)
        page.wait_for_function("document.getElementById('pm-library')")
        page.wait_for_timeout(400)
        for layout in ("chat", "new-chat"):
            for draft in (False, True):
                for dock in ("right", "left"):
                    for bottom in (24, vh // 2 - 40, vh - 90):
                        page.mouse.move(5, 5)
                        page.evaluate("""([layout, draft, dock, bottom]) => {
                            togglePanel(false); closeCard();
                            document.body.classList.toggle('center', layout === 'new-chat');
                            if (draft) { H.type(H.ORIG); H.stream(); H.done(); hideCard(); } else { H.type(''); }
                            pillDock = dock; pillBottom = bottom; placePill();
                        }""", [layout, draft, dock, bottom])
                        page.wait_for_timeout(450)          # the chip's grace period runs out
                        where = f"{vw}x{vh} {layout} {'draft' if draft else 'idle'} dock-{dock} bottom-{bottom}"
                        box = lambda sel: page.evaluate(
                            f"(() => {{ const r = document.querySelector('{sel}').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }})()")
                        px, py = box("#pm-trigger")
                        page.mouse.move(px, py)
                        page.wait_for_timeout(200)
                        if page.evaluate("document.getElementById('pm-library-btn').hidden"):
                            continue                         # nowhere clear of the chat box: ⇧-click and ⌘⇧L remain
                        cx, cy = box("#pm-library-btn")
                        # A curved path that overshoots the chip and comes back, ~30 ms a step.
                        for i in range(1, 15):
                            f = i / 12
                            page.mouse.move(px + (cx - px) * f, py + (cy - py) * f + 14 * (f - f * f))
                            page.wait_for_timeout(30)
                        page.mouse.move(cx, cy)
                        page.wait_for_timeout(60)
                        page.mouse.down()
                        page.mouse.up()
                        page.wait_for_timeout(150)
                        check(page.evaluate("!document.getElementById('pm-library').hidden"),
                              f"{where}: hovering ⊕ then clicking the chip opens the library")
                        # It stays open with the pointer gone, and clicks inside it keep it open.
                        page.mouse.move(vw // 2, 30)
                        page.wait_for_timeout(500)
                        check(page.evaluate("!document.getElementById('pm-library').hidden"),
                              f"{where}: the library stays open when the pointer leaves")
                        head = page.evaluate("(() => { const r = document.querySelector('#pm-library .pm-lib-head').getBoundingClientRect(); return [r.left + 20, r.top + r.height / 2]; })()")
                        page.mouse.click(*head)
                        page.wait_for_timeout(100)
                        check(page.evaluate("!document.getElementById('pm-library').hidden"),
                              f"{where}: a click inside the library keeps it open")
                        page.keyboard.press("Escape")
                        page.mouse.move(5, vh // 2)
                        page.wait_for_timeout(700)
                        check(page.evaluate("getComputedStyle(document.getElementById('pm-library-btn')).opacity") == "0",
                              f"{where}: the chip goes away once the pointer has left both")
                        cases += 1
        page.close()
    check(cases >= 60, f"only {cases} placements were reachable to test")
    print(f"chip reached from {cases} pill placements")


if __name__ == "__main__":
    main()
