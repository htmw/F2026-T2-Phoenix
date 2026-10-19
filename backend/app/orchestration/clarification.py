"""Spotting briefs too vague to plan, and asking what the user actually wants.

Running a whole office of agents on "help me" just spends the user's money guessing.
The check is deliberately conservative: a brief passes as soon as it contains a single
word that carries meaning, so only pleasantries and filler are stopped.
"""

from __future__ import annotations

import re

_FILLER = frozenset(
    {
        "a", "an", "the", "me", "my", "i", "you", "we", "us", "it", "this", "that", "these",
        "those", "there", "here", "some", "any", "and", "or", "to", "for", "with", "of",
        "on", "in", "please", "pls", "plz", "can", "could", "would", "will", "should",
        "do", "does", "did", "be", "is", "are", "am", "help", "need", "want", "like",
        "something", "anything", "everything", "stuff", "thing", "things", "hi", "hello",
        "hey", "yo", "ok", "okay", "thanks", "thank", "test", "testing", "asap", "now",
        "just", "really", "very", "out", "up", "what", "how", "start", "go",
        "again", "more", "make", "get", "give", "let", "lets", "let's", "work",
    }
)  # fmt: skip

_WORD = re.compile(r"[a-z0-9][a-z0-9'.+#-]*")

CLARIFYING_QUESTION = (
    "Your brief is too vague to plan. What should the agents do? Describe the task and "
    'what you want back, for example "Review this Python function for security issues '
    'and suggest fixes" or "Clean this CSV and summarise the changes".'
)


def needs_clarification(brief: str) -> bool:
    """True when the brief contains no word that says what work is wanted."""
    words = _WORD.findall(brief.lower())
    return not any(word not in _FILLER and len(word) >= 2 for word in words)
