"""Operator identity — header for the UI; HS256 JWT ``sub`` for Bearer callers.

``X-Operator-Id`` remains the office UI path (localStorage). ``Authorization: Bearer``
must be a signed JWT whose ``sub`` claim is the operator id (ADR 0007). Opaque bearer
tokens are no longer accepted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

import jwt
from fastapi import HTTPException, Request, status

from app.core.config import Settings

OPERATOR_ID_HEADER = "X-Operator-Id"
_OPERATOR_ID_RE = re.compile(r"^[A-Za-z0-9_.:@-]{1,64}$")

IdentitySource = Literal["header", "jwt", "dev_default"]


@dataclass(frozen=True, slots=True)
class OperatorIdentity:
    """Who is calling. ``id`` is the durable ownership / actor key."""

    id: str
    source: IdentitySource


def validate_operator_id(value: str) -> str:
    cleaned = value.strip()
    if not _OPERATOR_ID_RE.fullmatch(cleaned):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "operator id must be 1–64 chars of letters, digits, or _ . : @ - "
                f"(got {value!r})"
            ),
        )
    return cleaned


def _secret(settings: Settings) -> str:
    raw = settings.jwt_secret
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    return raw.get_secret_value()


def operator_id_from_jwt(token: str, settings: Settings) -> str:
    """Decode an HS256 Bearer JWT and return the validated ``sub`` claim."""
    secret = _secret(settings)
    if not secret.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT_SECRET is not configured; cannot validate Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    options: dict[str, bool] = {"require": ["sub"]}
    decode_kwargs: dict[str, object] = {
        "algorithms": ["HS256"],
        "options": options,
    }
    if settings.jwt_audience:
        decode_kwargs["audience"] = settings.jwt_audience
    if settings.jwt_issuer:
        decode_kwargs["issuer"] = settings.jwt_issuer

    try:
        payload = jwt.decode(token, secret, **decode_kwargs)  # type: ignore[arg-type]
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer JWT has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer JWT is invalid",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer JWT missing string 'sub' claim",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return validate_operator_id(sub)


def resolve_operator(request: Request, settings: Settings) -> OperatorIdentity:
    """Resolve identity for this request, or 401 when auth is required and missing."""
    header = request.headers.get(OPERATOR_ID_HEADER)
    if header:
        return OperatorIdentity(id=validate_operator_id(header), source="header")

    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token:
            return OperatorIdentity(id=operator_id_from_jwt(token, settings), source="jwt")

    if settings.auth_mode == "off":
        return OperatorIdentity(
            id=validate_operator_id(settings.dev_operator_id),
            source="dev_default",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=(
            f"operator identity required: send {OPERATOR_ID_HEADER} "
            "or Authorization: Bearer <JWT>"
        ),
        headers={"WWW-Authenticate": "Bearer"},
    )
