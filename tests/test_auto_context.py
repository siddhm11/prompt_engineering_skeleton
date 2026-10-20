"""
"Match my library automatically" off: neither saved prompts nor past rewrites
are searched, while what the user attached still reaches the model. On, or
unsaid by an older extension, retrieval runs as before.
"""

import pytest

from backend.models.schemas import EnhanceRequest
from backend.services import prompt_builder
from backend.services.memory_service import MemoryService

SAVED = {"a1": {"title": "About me", "content": "I'm a data analyst with 2 years of Python.", "user_id": "u1"}}


def fetch(pid, user_id):
    doc = SAVED.get(pid)
    return doc if doc and doc["user_id"] == user_id else None


@pytest.fixture
def searches(monkeypatch):
    calls = []
    monkeypatch.setattr(MemoryService, "search_saved_prompts",
                        lambda **kw: calls.append("saved") or [{"mongo_id": "s1", "title": "ATS", "content": "Make my resume ATS friendly.", "score": 0.5}])
    monkeypatch.setattr(MemoryService, "retrieve_passive_context",
                        lambda **kw: calls.append("passive") or [{"original": "whats jira", "refined": "Explain Jira.", "score": 0.59}])
    monkeypatch.setattr(MemoryService, "get_user_feedback_summary", lambda uid: "")
    return calls


def build(**kw):
    return prompt_builder._build_enhance_context(EnhanceRequest(prompt="what's Kibana", **kw), "u1", fetch)


def test_off_searches_neither_layer(searches):
    ctx = build(auto_context=False)
    assert searches == []
    assert ctx["similar_saved"] == [] and ctx["passive_matches"] == []
    assert "ATS" not in ctx["user_message"] and "Jira" not in ctx["user_message"]


def test_off_still_sends_what_the_user_attached(searches):
    ctx = build(auto_context=False, selected_prompt_ids=["a1"])
    assert searches == []
    assert "I'm a data analyst" in ctx["user_message"]


def test_on_and_unsaid_search_both_layers(searches):
    build(auto_context=True)
    build()   # an extension from before the switch sends nothing
    assert searches == ["saved", "passive", "saved", "passive"]


def test_off_leaves_a_retry_its_kept_context(searches):
    ctx = build(auto_context=False, reuse_context={"matched": [{"id": "a1", "score": 0.6}], "passive": []})
    assert searches == []
    assert [s["mongo_id"] for s in ctx["similar_saved"]] == ["a1"]
