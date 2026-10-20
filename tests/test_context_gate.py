"""The shared-word gate on past rewrites for short drafts (services/context_gate.py)."""

import pytest

from backend.services.context_gate import content_words, passive_match_keeps


def keeps(query, past, score):
    return passive_match_keeps(query, past, score, short_words=4, strong_score=0.65)


def test_content_words_drop_the_question_frame():
    assert content_words("what's Kibana") == {"kibana"}
    assert content_words("whats jira") == {"jira"}
    assert content_words("kibana kya hai") == {"kibana"}
    assert content_words("How do I improve my ATS score?") == {"improve", "ats", "score"}


def test_content_words_stem_plurals_and_verb_forms():
    assert content_words("dashboards") == content_words("dashboard")
    assert content_words("rebalancing consumers") == {"rebalanc", "consum"}


# Scores below are what the production MiniLM gives these pairs.
@pytest.mark.parametrize("query, past, score", [
    ("what's Kibana", "whats jira", 0.48),
    ("whats kibana", "whats jira", 0.59),
    ("whats kibana", "ATS", 0.23),
    ("tell me about logstash", "ATS", 0.28),
    ("what's react", "ATS", 0.34),
])
def test_short_draft_drops_a_past_rewrite_sharing_only_its_frame(query, past, score):
    assert not keeps(query, past, score)


def test_short_draft_keeps_a_past_rewrite_sharing_a_word():
    assert keeps("what's an ATS", "what's an ATS score and how do I improve mine", 0.59)


def test_short_draft_keeps_a_very_strong_match_without_a_shared_word():
    assert keeps("whats kibana", "whats jira", 0.65)


def test_longer_draft_is_left_to_the_score():
    # Five content words: enough meaning that the score alone decides, which
    # keeps a past rewrite in another language reachable.
    assert keeps("Mejora este correo para mis lectores.", "Keep Spanish requests in Spanish", 0.26)
