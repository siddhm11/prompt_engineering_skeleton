"""
Static checks over the extension source.

These exist because of a bug that no amount of Python testing could have found
and that a 64-agent code audit also missed: showSetupRequiredModal() built its
modal, inserted it, and wired up its buttons — but never added the `pm-visible`
class that .pm-modal-overlay needs to become opaque. A new user with no account
and no API key typed a prompt, pressed Enhance, and got nothing at all. No
modal, no toast, no console error. It was found by clicking the button on a
real page.

The checks are deliberately crude text analysis. They cannot verify behaviour,
but they catch the specific shape of "a modal that is built and never shown",
which is cheap insurance for a file with seven of them.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CONTENT_JS = (ROOT / "extension" / "content.js").read_text()
STYLES_CSS = (ROOT / "extension" / "styles.css").read_text()
MANIFEST = (ROOT / "extension" / "manifest.json").read_text()


def _function_bodies(src: str, name_pattern: str) -> dict:
    """Crude brace-matched extraction of top-level `function name(...) {...}`."""
    out = {}
    # `async function` too — missing it silently returned an empty dict, and
    # every assertion built on that dict then passed by looking at nothing.
    for m in re.finditer(rf"^(?:async\s+)?function ({name_pattern})\s*\([^)]*\)\s*{{", src, re.M):
        name, i, depth = m.group(1), m.end() - 1, 0
        while i < len(src):
            if src[i] == "{":
                depth += 1
            elif src[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        out[name] = src[m.start():i + 1]
    return out


MODALS = _function_bodies(CONTENT_JS, r"show\w*Modal")


def test_the_modal_functions_were_actually_found():
    """Guards the extraction itself — an empty dict would pass everything below."""
    assert len(MODALS) >= 3, f"only found {list(MODALS)}"


@pytest.mark.parametrize("name", sorted(MODALS))
def test_every_modal_makes_itself_visible(name):
    """
    A modal that never adds pm-visible is invisible: .pm-modal-overlay is
    opacity:0 / pointer-events:none until the class is present.
    """
    body = MODALS[name]
    if "getOrCreateModalOverlay" not in body and "pm-modal-overlay" not in body:
        pytest.skip(f"{name} does not own an overlay")
    assert "pm-visible" in body, (
        f"{name}() builds a modal but never adds the pm-visible class, "
        "so it is inserted into the page fully transparent and unclickable"
    )


def test_pm_visible_is_what_actually_reveals_the_overlay():
    """The premise of the test above: the class is load-bearing, not cosmetic."""
    assert re.search(r"\.pm-modal-overlay\s*{[^}]*opacity:\s*0", STYLES_CSS, re.S)
    assert re.search(r"\.pm-modal-overlay\.pm-visible\s*{[^}]*opacity:\s*1", STYLES_CSS, re.S)


def test_content_script_matches_cover_every_host_permission_site():
    """
    A site listed in host_permissions but missing from content_scripts.matches
    gets no UI at all. Both lists are hand-maintained.
    """
    import json
    m = json.loads(MANIFEST)
    matches = set(m["content_scripts"][0]["matches"])

    # host_permissions covers two different kinds of host: the chat sites the
    # UI is injected into, and the backends/providers the extension calls.
    # Only the first kind needs a matching content_scripts entry.
    BACKEND_HOSTS = r"(api\.|googleapis|openrouter|hf\.space|localhost|127\.0\.0\.1)"
    chat_hosts = {h for h in m["host_permissions"] if not re.search(BACKEND_HOSTS, h)}

    assert chat_hosts, "no chat hosts found — the exclusion regex is over-matching"
    assert chat_hosts <= matches, f"declared but never injected into: {chat_hosts - matches}"


def test_supported_matches_in_worker_track_the_manifest():
    """
    background.js re-lists the matched sites to re-inject into already-open
    tabs. If that list drifts from the manifest, existing tabs on the missing
    site stay dead after install.
    """
    import json
    worker = (ROOT / "extension" / "background.js").read_text()
    declared = set(json.loads(MANIFEST)["content_scripts"][0]["matches"])
    listed = set(re.findall(r'"(https://[^"]+)"',
                            re.search(r"SUPPORTED_MATCHES = \[(.*?)\]", worker, re.S).group(1)))
    assert listed == declared, f"drifted: only in manifest={declared - listed}, only in worker={listed - declared}"


def test_extension_origins_match_the_manifest():
    """
    config.EXTENSION_ORIGINS drives the production CORS allowlist warning. If it
    drifts from the manifest, either a platform is silently CORS-blocked in
    production or the warning names a site the extension no longer runs on.
    """
    import json
    from backend.core.config import settings

    from_manifest = []
    for pattern in json.loads(MANIFEST)["content_scripts"][0]["matches"]:
        origin = re.match(r"(https://[^/*]+)", pattern).group(1)
        if origin not in from_manifest:
            from_manifest.append(origin)

    assert set(settings.EXTENSION_ORIGINS) == set(from_manifest), (
        f"only in config={set(settings.EXTENSION_ORIGINS) - set(from_manifest)}, "
        f"only in manifest={set(from_manifest) - set(settings.EXTENSION_ORIGINS)}"
    )


# ── the same guard, for the inline card that replaced the modal ──

CARD_FNS = _function_bodies(CONTENT_JS, r"openCard|showDiffModal|showStreamingDiffModal|failStreamingModal")


def test_card_functions_were_found():
    assert "openCard" in CARD_FNS, "openCard not found — the guard below would be vacuous"


def test_opening_the_card_makes_it_visible():
    """
    Same defect class as the invisible setup modal: .pm-card is opacity:0 until
    pm-card-visible is added. Every path that shows the card goes through
    openCard(), so that is the one place the class has to be applied.
    """
    assert "pm-card-visible" in CARD_FNS["openCard"], (
        "openCard() builds and positions the card but never adds pm-card-visible, "
        "so it is inserted fully transparent"
    )


def test_card_visibility_class_is_load_bearing():
    assert re.search(r"\.pm-card\s*{[^}]*opacity:\s*0", STYLES_CSS, re.S)
    assert re.search(r"\.pm-card\.pm-card-visible\s*{[^}]*opacity:\s*1", STYLES_CSS, re.S)


def test_card_keymap_does_not_hijack_tab_when_closed():
    """
    Tab is the page's key, not ours. The handler must bail on idle state before
    it ever calls preventDefault, or the extension breaks tab navigation
    everywhere on six major sites.
    """
    handler = CONTENT_JS[CONTENT_JS.index('if (cardState === "idle") return;'):]
    guard = CONTENT_JS.index('if (cardState === "idle") return;')
    tab = CONTENT_JS.index('if (e.key === "Tab")', guard)
    assert guard < tab, "the idle guard must precede the Tab handler"


# ── stale rewrites ────────────────────────────────────────────────────────
# Editing the composer after a rewrite arrives leaves the card showing a
# rewrite of text that no longer exists. Accepting it then replaces what the
# user just typed — and reports success, correctly, because the write did land.
# Their work is what gets destroyed, so this is data loss, not untidiness.

def test_function_extraction_finds_async_functions():
    """Guards the helper itself. It matched only `function foo(`, so an async
    function came back as an empty dict and every assertion over it was
    vacuous."""
    assert "acceptCard" in _function_bodies(CONTENT_JS, r"acceptCard")


def test_accept_refuses_a_stale_rewrite():
    """The guard has to be inside acceptCard, not only on the keyboard path —
    the footer button calls it directly."""
    body = _function_bodies(CONTENT_JS, r"acceptCard")["acceptCard"]
    assert "cardStale" in body, "acceptCard does not check staleness at all"
    guard = body.index("cardStale")
    write = body.index("applyOrFallback")
    assert guard < write, "the staleness guard must precede the write"


def test_staleness_is_tracked_as_text_not_a_flag():
    """
    A boolean 'edited' flag cannot be un-set: undoing an edit would strand the
    card as stale forever, and a trailing space would trigger it. Comparing
    normalised text makes undo restore freshness for free.
    """
    body = _function_bodies(CONTENT_JS, r"refreshCardStaleness")["refreshCardStaleness"]
    assert "cardBasedOn" in body and "norm(" in body, \
        "staleness is not a normalised text comparison"


def test_editing_is_actually_listened_for():
    assert 'addEventListener("input", refreshCardStaleness' in CONTENT_JS, \
        "nothing recomputes staleness when the composer changes"


def test_redo_is_manual_not_automatic():
    """
    Re-running on every keystroke would spend a real model call per character
    against a ration of fifteen a day.
    """
    body = _function_bodies(CONTENT_JS, r"refreshCardStaleness")["refreshCardStaleness"]
    assert "handleEnhance" not in body, "staleness detection triggers an enhancement"


def test_the_stale_card_is_visually_distinct_and_labelled():
    assert "pm-card-stale" in CONTENT_JS
    assert "pm-card-stale-flag" in CONTENT_JS, "stale state is dimmed but never explained"
    assert re.search(r"\.pm-card\.pm-card-stale\s*{", STYLES_CSS), \
        "the stale class has no styling, so the state is invisible"


def test_a_rewrite_in_flight_lands_stale_if_the_prompt_moved():
    """
    Staleness is recomputed at render time rather than only on edit, so a
    rewrite the user edited underneath arrives dimmed instead of fresh-and-wrong.
    """
    body = _function_bodies(CONTENT_JS, r"showDiffModal")["showDiffModal"]
    assert "cardStale =" in body and "getCurrentInputText()" in body


# ── how the stale card looks ──────────────────────────────────────────────
# The first cut of the stale state was correct and unusable. It set
# `background` — not `background-color` — to a 5%-opaque tint, which dropped
# --pm-bg with it and left the card see-through: the host page's own buttons
# read straight through the rewrite, and in the light theme the keycaps went
# white-on-white over a dark page. Correct logic behind an unreadable surface
# is still a broken feature, so these are checks on the surface.


def _stale_css() -> str:
    """The `.pm-card.pm-card-stale { ... }` block."""
    m = re.search(r"\.pm-card\.pm-card-stale\s*{([^}]*)}", STYLES_CSS)
    assert m, "no stale card rule at all"
    return m.group(1)


def test_the_stale_block_was_actually_found():
    """Guards the extractor: an empty string would pass every check below."""
    assert "background" in _stale_css()


def test_the_stale_card_stays_opaque():
    """
    The tint must LAYER over the card's background, never replace it. A
    translucent card lets the host page through the rewrite it is showing.
    """
    block = _stale_css()
    assert not re.search(r"(?<!-)\bbackground\s*:", block), \
        "shorthand `background:` resets background-color — the card goes translucent"
    assert "background-color: var(--pm-bg)" in block, \
        "the stale card does not re-assert an opaque background"


def test_the_warn_palette_is_defined_in_both_themes():
    """
    Every stale colour was written as var(--pm-warn, #hardcoded). None of the
    tokens existed, so the fallback was always what rendered — one dark-tuned
    amber in both themes, at about 2:1 on the light card.
    """
    for token in ("--pm-warn", "--pm-warn-soft", "--pm-warn-border", "--pm-warn-wash"):
        assert STYLES_CSS.count(f"{token}:") >= 2, \
            f"{token} is not defined in both the dark and light blocks"
    assert not re.search(r"var\(--pm-warn[\w-]*,", STYLES_CSS), \
        "a --pm-warn token still carries a hardcoded fallback, which hides a missing token"


def test_the_stale_notice_sits_above_the_rewrite():
    """
    It qualifies the whole card. Printed under the body it read as a second
    content chip, indented beneath the very text it was invalidating.
    """
    body = _function_bodies(CONTENT_JS, r"showDiffModal")["showDiffModal"]
    render = body[body.index("openCard("):]
    assert re.search(r"openCard\(\s*staleFlag \+ body", render), \
        "the stale notice is rendered after the body it qualifies"


def test_the_stale_footer_still_lists_the_keys_that_still_work():
    """
    The stale footer was a separate, shorter list that dropped \\ original and
    ⌘S save — while both key handlers stayed live. A footer that stops listing
    working keys teaches you to stop reading it.
    """
    body = _function_bodies(CONTENT_JS, r"showDiffModal")["showDiffModal"]
    actions = body[body.index("const actions ="):body.index("openCard(")]
    for el in ("pm-card-toggle", "pm-card-save", "pm-card-close"):
        assert el in actions, f"{el} is missing from the one shared footer"
    # Accept is the only thing that differs between the two states.
    assert "pm-card-disabled" in body and "pm-card-redo" in body


def test_the_reading_position_survives_going_stale():
    """
    Going stale re-renders the card. Without this the rewrite scrolled back to
    the top exactly when the user edited in reaction to something they had
    scrolled down to read.
    """
    body = _function_bodies(CONTENT_JS, r"showDiffModal")["showDiffModal"]
    assert "scrollTop" in body, "the rewrite's scroll position is discarded on re-render"
    assert "textContent === prevContent" in body, \
        "scroll is restored without checking the text is the same text"


def test_the_card_is_never_positioned_over_the_composer():
    """
    positionCard clamped the card's TOP against the viewport bottom, so a card
    too tall to fit below slid upward over the composer — covering the text it
    is a comment on, and doing it precisely when the stale bar made it taller.
    The fix constrains the scrolling text instead.
    """
    body = _function_bodies(CONTENT_JS, r"positionCard")["positionCard"]
    assert "--pm-card-text-max" in body, \
        "nothing constrains the card's height to the room beside the composer"
    assert not re.search(r"Math\.min\(\s*box\.bottom \+ gap", body), \
        "the card's top is still clamped against the viewport, which walks it over the composer"
    assert "min(40vh, var(--pm-card-text-max" in STYLES_CSS, \
        "the height budget positionCard computes is never applied to the text"


# ── toasts ────────────────────────────────────────────────────────────────
# Every toast positioned itself, identically: `position: fixed; bottom: 80px;
# left: 50%`. Two at once therefore landed on the same pixels. Accepting a
# rewrite did exactly that — applyOrFallback raised "Applied" and the rating
# prompt covered it a frame later, so the answer to "did that work?" was never
# visible. And at z-index 100003 against the card's 2147483000, a toast raised
# while the card was open rendered behind it: ⌘S showed a sliver of "Saved to
# your library" poking out from under the card it was confirming.


def _css_block(selector: str) -> str:
    """
    The block for a rule whose selector is exactly `selector`.

    Naive matching grabs the wrong rule: `.pm-toast` also appears as the last
    entry of a grouped `.pm-panel, ..., .pm-toast { transition: ... }` selector,
    where it sits at the start of its own line and matches identically. Skipping
    matches preceded by a comma is what makes this the standalone rule.
    """
    for m in re.finditer(re.escape(selector) + r"\s*{([^}]*)}", STYLES_CSS):
        if STYLES_CSS[: m.start()].rstrip().endswith(","):
            continue
        return m.group(1)
    raise AssertionError(f"no standalone rule for {selector}")


def test_the_toast_blocks_were_actually_found():
    """Guards the extractor — an empty string passes every check below."""
    assert "position" in _css_block("#pm-toast-stack")
    assert "padding" in _css_block(".pm-toast")


def test_toasts_do_not_position_themselves():
    """
    Individually-positioned toasts stack on the same pixels. Layout is the
    container's job so that two toasts lay out instead of overlapping.
    """
    for sel in (".pm-toast", ".pm-feedback-toast"):
        block = _css_block(sel)
        assert "position: fixed" not in block, f"{sel} still positions itself"
        assert "bottom:" not in block, f"{sel} still pins itself to the viewport"


def test_the_toast_stack_outranks_the_card():
    """
    A toast that loses the z-index race to the card is an invisible message.
    """
    stack = _css_block("#pm-toast-stack")
    card = _css_block(".pm-card")
    stack_z = int(re.search(r"z-index:\s*(\d+)", stack).group(1))
    card_z = int(re.search(r"z-index:\s*(\d+)", card).group(1))
    assert stack_z > card_z, "toasts render behind the card"


def test_the_toast_stack_does_not_swallow_clicks():
    assert "pointer-events: none" in _css_block("#pm-toast-stack")
    assert "pointer-events: auto" in _css_block(".pm-feedback-toast"), \
        "the feedback toast has buttons but cannot receive clicks"


def test_accepting_raises_one_toast_not_two():
    """
    The confirmation and the rating prompt are one event. Two toasts for it
    meant the second covered the first.
    """
    body = _function_bodies(CONTENT_JS, r"acceptCard")["acceptCard"]
    assert "canRate ? null : " in body, \
        "applyOrFallback is not told to stay quiet when the feedback toast will confirm"
    apply_body = _function_bodies(CONTENT_JS, r"applyOrFallback")["applyOrFallback"]
    assert "if (successMessage) showToast" in apply_body, \
        "applyOrFallback toasts unconditionally, so accept still fires two"


def test_the_rating_prompt_is_skipped_when_it_cannot_be_sent():
    """Without a log_id the rating goes nowhere; asking anyway spends attention
    on nothing, and drops the confirmation to show a dead question."""
    body = _function_bodies(CONTENT_JS, r"acceptCard")["acceptCard"]
    assert "result.log_id" in body


def test_toasts_carry_a_theme():
    """
    Toasts set no data-pm-theme at all, so they resolved --pm-bg from :root and
    rendered dark for everyone regardless of the setting.
    """
    body = _function_bodies(CONTENT_JS, r"getOrCreateToastStack")["getOrCreateToastStack"]
    assert "data-pm-theme" in body and "pm_theme" in body


def test_switching_theme_repaints_the_card_and_the_toasts():
    """
    applyTheme listed the panel, trigger and overlays but not the card or the
    toasts — the two surfaces most likely to be on screen when you toggle.
    """
    body = _function_bodies(CONTENT_JS, r"applyTheme")["applyTheme"]
    assert "pm-card" in body and "pm-toast-stack" in body


def test_toasts_are_placed_above_the_card_not_over_it():
    """
    Anchoring to the card alone breaks the empty-chat layout, where the card
    renders BELOW the composer — the toast would land on the composer.
    """
    body = _function_bodies(CONTENT_JS, r"positionToasts")["positionToasts"]
    assert "findComposer()" in body and "pm-card" in body, \
        "positionToasts does not consider both anchors"
    assert "Math.min(...tops)" in body, \
        "the stack is not placed above the highest of card and composer"
