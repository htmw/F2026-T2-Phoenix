"""Google sign-in, session cookies, and account deletion.

The browser sends a Google ID token. This route verifies it, upserts the user by
``sub`` (never by email alone), and issues our own session JWT. A matching email on a
different Google subject is rejected so accounts cannot be linked automatically.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import OperatorDep, SessionDep, SettingsDep
from app.core.config import Settings
from app.core.google_auth import decode_google_id_token, verify_google_id_token
from app.core.identity import (
    SESSION_COOKIE,
    OperatorIdentity,
    issue_session_token,
    read_session_token,
    session_token_from_request,
)
from app.models.network import ArtifactRecord, MemoryRecord
from app.models.user import UserRecord
from app.services.file_generation import artifact_path

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(min_length=20, max_length=8_000)


class UserView(BaseModel):
    id: str
    email: str
    display_name: str | None
    picture_url: str | None


class LoginResponse(BaseModel):
    user: UserView
    session_token: str


def _view(user: UserRecord) -> UserView:
    return UserView(
        id=user.google_sub,
        email=user.email,
        display_name=user.display_name,
        picture_url=user.picture_url,
    )


def _set_session_cookie(response: Response, settings: SettingsDep, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )


async def operator_from_session(
    request: Request, settings: Settings, session: AsyncSession
) -> OperatorIdentity:
    """Resolve a Google session and reject revoked or mismatched versions."""
    token = session_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="sign in with Google",
            headers={"WWW-Authenticate": "Bearer"},
        )
    sub, version = read_session_token(token, settings)
    user = await session.get(UserRecord, sub)
    if user is None or user.session_version != version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="session is no longer valid",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return OperatorIdentity(
        id=user.google_sub,
        source="jwt",
        email=user.email,
        display_name=user.display_name,
    )


@router.post("/google", response_model=LoginResponse)
async def login_with_google(
    body: GoogleLoginRequest,
    request: Request,
    response: Response,
    settings: SettingsDep,
    session: SessionDep,
) -> LoginResponse:
    client_id = settings.google_client_id or ""
    test_key = getattr(request.app.state, "google_token_key", None)
    if test_key is not None and settings.environment in {"test", "development"}:
        identity = decode_google_id_token(body.id_token, client_id=client_id, key=test_key)
    else:
        identity = verify_google_id_token(body.id_token, client_id=client_id)

    existing_email = await session.scalar(
        select(UserRecord).where(UserRecord.email == identity.email)
    )
    if existing_email is not None and existing_email.google_sub != identity.sub:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="this email is already registered to a different Google account",
        )

    user = await session.get(UserRecord, identity.sub)
    now = datetime.now(UTC)
    if user is None:
        user = UserRecord(
            google_sub=identity.sub,
            email=identity.email,
            email_verified=True,
            display_name=identity.name,
            picture_url=identity.picture,
            session_version=1,
            last_login_at=now,
        )
        session.add(user)
    else:
        user.email = identity.email
        user.email_verified = True
        user.display_name = identity.name
        user.picture_url = identity.picture
        user.last_login_at = now
    await session.flush()

    token = issue_session_token(
        settings, sub=user.google_sub, version=user.session_version, email=user.email
    )
    _set_session_cookie(response, settings, token)
    return LoginResponse(user=_view(user), session_token=token)


@router.get("/me", response_model=UserView)
async def current_user(operator: OperatorDep, session: SessionDep) -> UserView:
    user = await session.get(UserRecord, operator.id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="sign in with Google")
    return _view(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(operator: OperatorDep, session: SessionDep, response: Response) -> Response:
    user = await session.get(UserRecord, operator.id)
    if user is not None:
        user.session_version += 1
        await session.flush()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    operator: OperatorDep, settings: SettingsDep, session: SessionDep, response: Response
) -> Response:
    """Delete the account, its memories, and its generated files."""
    artifacts = (
        await session.scalars(select(ArtifactRecord).where(ArtifactRecord.owner_id == operator.id))
    ).all()
    for artifact in artifacts:
        fmt = str((artifact.extra or {}).get("format") or "")
        if fmt:
            path = artifact_path(settings.artifact_dir, operator.id, artifact.id, fmt)
            if path.is_file():
                path.unlink()
        await session.delete(artifact)
    await session.execute(delete(MemoryRecord).where(MemoryRecord.operator_id == operator.id))
    user = await session.get(UserRecord, operator.id)
    if user is not None:
        await session.delete(user)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
