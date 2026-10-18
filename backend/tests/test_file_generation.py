"""Generated files are real bytes of the requested format, not a description."""

from __future__ import annotations

import uuid

import pytest

from app.services.file_generation import (
    FileGenerationError,
    artifact_path,
    detect_format,
    render_file,
    validate_file,
)


@pytest.mark.parametrize(
    "fmt",
    ["pdf", "docx", "xlsx", "pptx", "csv", "py", "zip", "json"],
)
def test_render_produces_a_valid_file(fmt: str, tmp_path: object) -> None:
    generated = render_file(
        file_format=fmt,
        title="Sprint report",
        body="print('hello')\n" if fmt == "py" else "Revenue grew.\nSecond line.",
    )
    assert generated.data
    assert generated.filename.endswith(f".{fmt}" if fmt != "py" else ".py")
    validate_file(fmt, generated.data)


def test_detects_an_explicit_pdf_request() -> None:
    assert detect_format("Create a PDF report for the board") == "pdf"


def test_refuses_secret_like_content() -> None:
    with pytest.raises(FileGenerationError):
        render_file(file_format="json", title="keys", body="api_key: sk-live-123")


def test_artifact_path_cannot_escape_the_root(tmp_path: object) -> None:
    from pathlib import Path

    root = Path(str(tmp_path))
    path = artifact_path(root, "alice", uuid.uuid4(), "pdf")
    assert root in path.parents
    with pytest.raises(FileGenerationError):
        artifact_path(root, "../alice", uuid.uuid4(), "pdf")
