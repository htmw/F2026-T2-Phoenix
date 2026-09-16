"""Validating what a model returned.

This is the trust boundary. Everything upstream of it is untrusted text from a
non-deterministic system; everything downstream treats agent payloads as domain data.
A validation failure is an expected outcome with a defined handling path, never an
exception that escapes to a 500.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as SchemaValidationError

# Models often wrap JSON in fences despite instructions not to. Recovering from that is
# cheap and saves a retry; recovering from genuinely malformed output is not attempted.
_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


@dataclass(frozen=True, slots=True)
class ValidationOutcome:
    valid: bool
    payload: dict[str, object]
    error: str | None = None
    recovered_from_fence: bool = False


def extract_json_object(text: str) -> tuple[dict[str, object] | None, str | None, bool]:
    """Best-effort extraction of a single JSON object from model output.

    Returns (payload, error, recovered_from_fence).
    """
    stripped = text.strip()
    if not stripped:
        return None, "model returned empty output", False

    if (parsed := _try_parse(stripped)) is not None:
        return parsed, None, False

    match = _FENCE_PATTERN.search(stripped)
    if match and (parsed := _try_parse(match.group(1))) is not None:
        return parsed, None, True

    # Last resort: the outermost brace pair, which handles a stray sentence before or
    # after the object.
    start, end = stripped.find("{"), stripped.rfind("}")
    if start != -1 and end > start and (parsed := _try_parse(stripped[start : end + 1])):
        return parsed, None, True

    return None, "model output was not valid JSON", False


def _try_parse(candidate: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(candidate)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def validate_agent_output(text: str, output_schema: dict[str, object]) -> ValidationOutcome:
    """Parse and schema-check one agent response."""
    payload, error, recovered = extract_json_object(text)
    if payload is None:
        return ValidationOutcome(valid=False, payload={}, error=error)

    validator = Draft202012Validator(output_schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
    if errors:
        return ValidationOutcome(
            valid=False,
            payload=payload,
            error=_describe_errors(errors),
            recovered_from_fence=recovered,
        )

    return ValidationOutcome(valid=True, payload=payload, recovered_from_fence=recovered)


def _describe_errors(errors: list[SchemaValidationError]) -> str:
    """Render schema errors compactly enough to log and to feed back to the model."""
    described = []
    for error in errors[:5]:
        location = "/".join(str(part) for part in error.path) or "(root)"
        described.append(f"{location}: {error.message}")
    if len(errors) > 5:
        described.append(f"... and {len(errors) - 5} more")
    return "; ".join(described)
