"""Generate a real file and download it only for its owner."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.dependencies import AbuseGuardDep, OperatorDep, SessionDep, SettingsDep
from app.domain.enums import ArtifactKind
from app.messaging.store import ArtifactStore
from app.models.network import ArtifactRecord
from app.schemas.memory import ArtifactCreate, ArtifactView
from app.services.file_generation import (
    FileGenerationError,
    artifact_path,
    detect_format,
    render_file,
    write_artifact,
)

router = APIRouter(tags=["files"])


class FileGenerateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    body: str = Field(default="", max_length=100_000)
    file_format: str | None = Field(default=None, max_length=32)
    prompt: str | None = Field(default=None, max_length=4_000)
    workflow_id: uuid.UUID | None = None


@router.post("/files", response_model=ArtifactView, status_code=status.HTTP_201_CREATED)
async def generate_file(
    body: FileGenerateRequest,
    session: SessionDep,
    operator: OperatorDep,
    settings: SettingsDep,
    _limits: AbuseGuardDep,
) -> ArtifactView:
    fmt = body.file_format or detect_format(body.prompt or "") or detect_format(body.title)
    if fmt is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="say which file you want: pdf, docx, xlsx, pptx, csv, py, zip, or json",
        )
    text = body.body.strip() or (body.prompt or "").strip() or body.title
    try:
        generated = render_file(file_format=fmt, title=body.title, body=text)
    except FileGenerationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None

    view = await ArtifactStore(session).register(
        ArtifactCreate(
            kind=ArtifactKind.FILE,
            created_by=operator.id,
            owner_id=operator.id,
            uri="artifact://pending",
            title=body.title,
            workflow_id=body.workflow_id,
            content_type=generated.content_type,
            extra={
                "filename": generated.filename,
                "format": generated.file_format,
                "download_path": "/api/v1/files/pending",
            },
            size_bytes=len(generated.data),
        )
    )
    row = await session.get(ArtifactRecord, view.id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="file was not stored"
        )
    row.uri = f"artifact://{view.id}"
    row.extra = {
        "filename": generated.filename,
        "format": generated.file_format,
        "download_path": f"/api/v1/files/{view.id}",
    }
    try:
        path = artifact_path(settings.artifact_dir, operator.id, view.id, generated.file_format)
        write_artifact(path, generated.data)
    except FileGenerationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await session.flush()
    return ArtifactView(
        id=view.id,
        kind=view.kind,
        created_by=view.created_by,
        owner_id=view.owner_id,
        uri=row.uri,
        title=view.title,
        workflow_id=view.workflow_id,
        content_type=view.content_type,
        extra=dict(row.extra),
        size_bytes=view.size_bytes,
        created_at=view.created_at,
    )


@router.get("/files/{artifact_id}")
async def download_file(
    artifact_id: uuid.UUID,
    session: SessionDep,
    operator: OperatorDep,
    settings: SettingsDep,
) -> FileResponse:
    row = await session.get(ArtifactRecord, artifact_id)
    if row is None or row.owner_id != operator.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")
    fmt = str((row.extra or {}).get("format") or "")
    filename = str((row.extra or {}).get("filename") or f"{artifact_id}.{fmt or 'bin'}")
    if not fmt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")
    try:
        path = artifact_path(settings.artifact_dir, operator.id, row.id, fmt)
    except FileGenerationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")
    return FileResponse(path, media_type=row.content_type, filename=filename)
