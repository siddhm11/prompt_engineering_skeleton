"""Regression tests for Qdrant URL normalisation."""
import pytest
from backend.core.config import _normalise_qdrant_url as normalise


@pytest.mark.parametrize("raw,expected", [
    # The production bug: cloud host pasted without a port.
    ("https://abc-123.us-east.aws.cloud.qdrant.io",
     "https://abc-123.us-east.aws.cloud.qdrant.io:6333"),
    # Already correct — must not double up.
    ("https://abc-123.us-east.aws.cloud.qdrant.io:6333",
     "https://abc-123.us-east.aws.cloud.qdrant.io:6333"),
    # A deliberate non-default port is the operator's choice.
    ("https://abc-123.us-east.aws.cloud.qdrant.io:6334",
     "https://abc-123.us-east.aws.cloud.qdrant.io:6334"),
])
def test_cloud_urls(raw, expected):
    assert normalise(raw) == expected


@pytest.mark.parametrize("raw", [
    "http://localhost:6333",
    "http://127.0.0.1:6333",
    ":memory:",
    "",
    "https://my-proxy.example.com",              # not a qdrant cloud host
    "https://abc.cloud.qdrant.io/behind/a/path", # path implies a proxy route
])
def test_left_alone(raw):
    assert normalise(raw) == raw


def test_whitespace_is_stripped():
    assert normalise("  https://abc.cloud.qdrant.io  ") == "https://abc.cloud.qdrant.io:6333"


def test_none_is_survivable():
    assert normalise(None) == ""
