"""
Regression tests for memory_service.redact_secrets().

An API key pasted once into a chat box was logged to Mongo verbatim AND
embedded into Qdrant, where it was permanent and got spliced back into that
user's later, unrelated prompts as "related context".
"""

import pytest
from backend.services.memory_service import redact_secrets

SECRETS = [
    ("openai",        "my key is sk-abcdef1234567890ABCDEF and it works"),
    ("groq in env",   "GROQ_API_KEY=gsk_aBcD1234567890xyzXYZ0987654321"),
    ("groq bare",     "use gsk_aBcD1234567890xyzXYZ098 please"),
    ("anthropic",     "sk-ant-api03-AbCdEf1234567890xyz"),
    ("google",        "AIzaSyD-1234567890abcdefghijklmnopqrstuv"),
    ("github pat",    "ghp_ABCDEFGHIJ1234567890abcdefghij"),
    ("aws key id",    "AKIAIOSFODNN7EXAMPLE"),
    ("slack",         "xoxb-1234567890-ABCDEFGHIJKLM"),
    ("jwt",           "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghij12345"),
    ("labelled pwd",  'password: "hunter2hunter2hunter2"'),
]


@pytest.mark.parametrize("label,text", SECRETS, ids=[s[0] for s in SECRETS])
def test_secret_is_masked(label, text):
    out = redact_secrets(text)
    assert "[REDACTED]" in out, f"{label} was not masked"


@pytest.mark.parametrize("label,text", SECRETS, ids=[s[0] for s in SECRETS])
def test_no_raw_secret_survives(label, text):
    """The masked output must not still contain the credential body."""
    out = redact_secrets(text)
    for token in text.replace("=", " ").replace(":", " ").split():
        stripped = token.strip('"\'')
        if len(stripped) >= 16 and stripped not in ("[REDACTED]",):
            assert stripped not in out, f"{label} leaked {stripped!r}"


CLEAN = [
    "just a normal prompt about sorting a list in python",
    "write me a haiku about the secret garden",
    "explain the difference between a token and a lexeme",
    "my password manager keeps telling me to rotate things",
    "summarise this in 3 bullets",
]


@pytest.mark.parametrize("text", CLEAN)
def test_ordinary_prompts_are_untouched(text):
    """False positives silently corrupt the user's own text — worse than a miss."""
    assert redact_secrets(text) == text


def test_handles_none_and_empty():
    assert redact_secrets("") == ""
    assert redact_secrets(None) is None
