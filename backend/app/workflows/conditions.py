"""Evaluating edge conditions against an agent's structured output.

Conditions are data, not expressions: they are persisted, shown in the UI, and evaluated
here. Nothing in this module executes a string, which is the point — the payload it reads
came from a language model, and a workflow that `eval`'d model output would be handing
control of the process to whatever the model felt like writing.

Every operator is total: a missing path is a definite answer ("not there"), never an
error, because a model omitting an optional field is normal and must not fail a run.
"""

from __future__ import annotations

from collections.abc import Mapping, Sized
from typing import Any

from app.schemas.workflow import EdgeCondition

_MISSING = object()


def resolve_path(payload: Mapping[str, object], path: str) -> object:
    """Follow a dotted path, returning a sentinel when any step is absent.

    List indices are supported (``findings.0.severity``) because agent schemas describe
    arrays of records, and a condition on the first element is a reasonable thing to ask.
    """
    current: Any = payload
    for part in path.split("."):
        if isinstance(current, Mapping):
            if part not in current:
                return _MISSING
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                return _MISSING
            current = current[index]
        else:
            return _MISSING
    return current


def evaluate(condition: EdgeCondition, payload: Mapping[str, object]) -> bool:
    value = resolve_path(payload, condition.path)
    present = value is not _MISSING

    match condition.operator:
        case "exists":
            return present
        case "not_exists":
            return not present
        case "is_true":
            return value is True
        case "is_false":
            # Explicit false only. A missing field is not a denial, and treating it as
            # one would skip work on the strength of an omission.
            return value is False
        case "eq":
            return present and value == condition.value
        case "ne":
            return present and value != condition.value
        case "non_empty":
            return present and _size(value) > 0
        case "empty":
            return not present or _size(value) == 0
        case "contains":
            return present and _contains(value, condition.value)
        case _:
            return present and _compare(condition.operator, value, condition.value)


def describe(condition: EdgeCondition, source_key: str) -> str:
    """A human-readable reason, stored on a skipped node.

    "Skipped" is a success state in this product, so the user is owed a sentence
    explaining it rather than a status with no story.
    """
    if condition.description:
        return condition.description
    readable = {
        "exists": f"'{source_key}.{condition.path}' was absent",
        "not_exists": f"'{source_key}.{condition.path}' was present",
        "is_true": f"'{source_key}.{condition.path}' was not true",
        "is_false": f"'{source_key}.{condition.path}' was not false",
        "non_empty": f"'{source_key}.{condition.path}' was empty",
        "empty": f"'{source_key}.{condition.path}' was not empty",
    }
    return readable.get(
        condition.operator,
        f"'{source_key}.{condition.path}' did not satisfy {condition.operator} {condition.value!r}",
    )


def _size(value: object) -> int:
    if isinstance(value, Sized):
        return len(value)
    # A bare scalar counts as one item: `non_empty` on a single finding should hold.
    return 0 if value is None or value is False else 1


def _contains(haystack: object, needle: object) -> bool:
    if isinstance(haystack, str):
        return isinstance(needle, str) and needle in haystack
    if isinstance(haystack, list | tuple | set):
        return needle in haystack
    if isinstance(haystack, Mapping):
        return needle in haystack
    return False


def _compare(operator: str, left: object, right: object) -> bool:
    if not isinstance(left, int | float) or not isinstance(right, int | float):
        # Ordering a string against a number is a mistake in the condition, not a
        # runtime failure; treat it as unsatisfied so the workflow keeps going.
        return False
    if isinstance(left, bool) or isinstance(right, bool):
        return False
    match operator:
        case "gt":
            return left > right
        case "gte":
            return left >= right
        case "lt":
            return left < right
        case _:
            return left <= right
