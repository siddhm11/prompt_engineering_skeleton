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
    for m in re.finditer(rf"^function ({name_pattern})\s*\([^)]*\)\s*{{", src, re.M):
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
