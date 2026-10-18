"""Verify Google OpenID Connect ID tokens.

The browser obtains the token from Google. This module checks the signature, issuer,
audience, and expiry before any account is created or linked. Tests pass a local
public key so they never call Google.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import HTTPException, status
from jwt import PyJWKClient

from app.core.identity import validate_operator_id

GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")


@dataclass(frozen=True, slots=True)
class GoogleIdentity:
    sub: str
    email: str
    email_verified: bool
    name: str | None
    picture: str | None


def decode_google_id_token(token: str, *, client_id: str, key: object) -> GoogleIdentity:
    """Validate an ID token against ``key`` (a PEM, JWK, or cryptography public key)."""
    if not client_id.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GOOGLE_CLIENT_ID is not configured",
        )
    try:
        payload = jwt.decode(
            token,
            key,  # type: ignore[arg-type]
            algorithms=["RS256"],
            audience=client_id,
            issuer=list(GOOGLE_ISSUERS),
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google ID token has expired",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google ID token is invalid",
        ) from exc

    sub = payload.get("sub")
    email = payload.get("email")
    if not isinstance(sub, str) or not isinstance(email, str) or not email.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google ID token is missing sub or email",
        )
    if payload.get("email_verified") is not True:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google account email is not verified",
        )
    name = payload.get("name")
    picture = payload.get("picture")
    return GoogleIdentity(
        sub=validate_operator_id(sub),
        email=email.strip().lower(),
        email_verified=True,
        name=name if isinstance(name, str) and name.strip() else None,
        picture=picture if isinstance(picture, str) and picture.startswith("https://") else None,
    )


def verify_google_id_token(token: str, *, client_id: str) -> GoogleIdentity:
    """Fetch Google's certs and verify ``token``. Network is required."""
    signing_key = PyJWKClient(GOOGLE_CERTS_URL).get_signing_key_from_jwt(token)
    return decode_google_id_token(token, client_id=client_id, key=signing_key.key)
