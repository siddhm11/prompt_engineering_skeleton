"""Whether a past rewrite is about the same thing as a short draft.

A short draft is mostly its frame. "what's Kibana" and a past "whats jira"
share only "what's", yet the multilingual MiniLM scores them 0.59, and a rare
name is split into word pieces that land on unrelated short prompts: "tell me
about logstash" scores 0.28 against a past "ATS". Past rewrites are themselves
mostly short questions, so they cleared the 0.20 gate and were spliced into
answers about something else entirely ("what's Kibana" answered about ATS).

No single score separates these: a gate high enough to drop "whats jira"
drops most real matches too (see evals/context_retrieval_short_questions.json).
What does is a shared word. For a draft of a few words, a past rewrite must
share one of them, or match very strongly. Longer drafts carry enough meaning
for the score alone, and saved prompts, written by the user as facts, are
often worded nothing like the draft that needs them, so neither is gated.

Pure functions, no model, so the eval runner applies exactly this rule.
"""

import re

# Words that frame a question rather than name its subject. English, plus the
# Hinglish frame ("kibana kya hai"), since that is how many users ask.
_FRAME_WORDS = frozenset("""
a an the is are was were be am what whats how why when where who which do does
did i my me we our you your it its this that these those to of for in on at by
and or with about tell explain give make please use used vs can could should
would will s t m re ve ll d kya hai h ka ki ke ko
""".split())

_SUFFIXES = ("ing", "ers", "er", "es", "ed", "s")


def _stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if len(word) > 4 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def content_words(text: str) -> set:
    """The words of text that name its subject, crudely stemmed."""
    return {
        _stem(word)
        for word in re.findall(r"[^\W_]+", (text or "").lower())
        if word not in _FRAME_WORDS and len(word) > 1
    }


def passive_match_keeps(query: str, past_prompt: str, score: float, *,
                        short_words: int, strong_score: float) -> bool:
    """Whether a past rewrite that cleared the score gate may be used.

    A draft of more than short_words content words keeps it on the score
    alone. A shorter one keeps it only when the two share a content word or
    the score reaches strong_score.
    """
    words = content_words(query)
    if len(words) > short_words:
        return True
    return score >= strong_score or bool(words & content_words(past_prompt))
