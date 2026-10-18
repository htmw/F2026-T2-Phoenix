"""Turn a file request into a real, validated artifact.

The model may supply the text. This module writes the bytes with a deterministic
serializer and refuses to report success unless the bytes match the requested format.
"""

from __future__ import annotations

import csv
import io
import json
import re
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

FileFormat = str

_FORMATS: dict[str, str] = {
    "pdf": "pdf",
    "docx": "docx",
    "word": "docx",
    "doc": "docx",
    "xlsx": "xlsx",
    "excel": "xlsx",
    "spreadsheet": "xlsx",
    "pptx": "pptx",
    "powerpoint": "pptx",
    "slides": "pptx",
    "csv": "csv",
    "py": "py",
    "python": "py",
    "zip": "zip",
    "json": "json",
}

_MIME = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "csv": "text/csv",
    "py": "text/x-python",
    "zip": "application/zip",
    "json": "application/json",
}

_SECRET = re.compile(r"(?i)\b(password|api[_ -]?key|secret|bearer|token)\b\s*[:=]")


@dataclass(frozen=True, slots=True)
class GeneratedFile:
    filename: str
    content_type: str
    data: bytes
    file_format: str


class FileGenerationError(ValueError):
    """The request could not be turned into a valid file."""


def detect_format(text: str) -> str | None:
    """Return a supported extension when the text explicitly asks for a file."""
    lowered = text.lower()
    patterns = (
        (r"\bpdf\b", "pdf"),
        (r"\b(word|docx)\b", "docx"),
        (r"\b(excel|xlsx|spreadsheet)\b", "xlsx"),
        (r"\b(powerpoint|pptx|slides)\b", "pptx"),
        (r"\bcsv\b", "csv"),
        (r"\b(python script|\.py)\b", "py"),
        (r"\bzip\b", "zip"),
        (r"\bjson\b", "json"),
    )
    for pattern, fmt in patterns:
        if re.search(pattern, lowered):
            return fmt
    return None


def normalize_format(value: str) -> str:
    key = value.strip().lower().lstrip(".")
    fmt = _FORMATS.get(key)
    if fmt is None:
        raise FileGenerationError(f"unsupported file format {value!r}")
    return fmt


def render_file(*, file_format: str, title: str, body: str) -> GeneratedFile:
    """Build ``file_format`` from ``title`` and ``body`` and validate the bytes."""
    fmt = normalize_format(file_format)
    safe_title = _safe_title(title)
    text = body.strip() or title.strip()
    if not text:
        raise FileGenerationError("file body is empty")
    if _SECRET.search(text):
        raise FileGenerationError("refusing to write a file that looks like it contains a secret")

    builders = {
        "pdf": _pdf,
        "docx": _docx,
        "xlsx": _xlsx,
        "pptx": _pptx,
        "csv": _csv,
        "py": _python,
        "zip": _zip,
        "json": _json,
    }
    data = builders[fmt](safe_title, text)
    validate_file(fmt, data)
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", safe_title).strip("-") or "deliverable"
    return GeneratedFile(
        filename=f"{stem[:60]}.{fmt}",
        content_type=_MIME[fmt],
        data=data,
        file_format=fmt,
    )


def validate_file(file_format: str, data: bytes) -> None:
    """Raise when ``data`` is empty or is not the format it claims to be."""
    if not data:
        raise FileGenerationError("generated file is empty")
    fmt = normalize_format(file_format)
    if fmt == "pdf":
        if not data.startswith(b"%PDF-") or b"%%EOF" not in data:
            raise FileGenerationError("PDF is not valid")
        return
    if fmt == "json":
        json.loads(data.decode("utf-8"))
        return
    if fmt == "csv":
        rows = list(csv.reader(io.StringIO(data.decode("utf-8"))))
        if not rows or not rows[0]:
            raise FileGenerationError("CSV is empty")
        return
    if fmt == "py":
        compile(data.decode("utf-8"), "<generated>", "exec")
        return
    if fmt in {"docx", "xlsx", "pptx", "zip"}:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            bad = archive.testzip()
            if bad is not None:
                raise FileGenerationError(f"archive member {bad} is corrupt")
            names = set(archive.namelist())
        required = {
            "docx": "word/document.xml",
            "xlsx": "xl/worksheets/sheet1.xml",
            "pptx": "ppt/slides/slide1.xml",
            "zip": None,
        }[fmt]
        if required is not None and required not in names:
            raise FileGenerationError(f"{fmt} is missing {required}")


def artifact_path(root: str | Path, owner_id: str, artifact_id: uuid.UUID, ext: str) -> Path:
    """Resolve a storage path that cannot escape ``root``."""
    base = Path(root).resolve()
    owner = owner_id.strip()
    if not owner or owner in {".", ".."} or "/" in owner or "\\" in owner:
        raise FileGenerationError("invalid artifact owner")
    extension = normalize_format(ext)
    directory = (base / owner).resolve()
    path = (directory / f"{artifact_id}.{extension}").resolve()
    if directory != base and base not in directory.parents:
        raise FileGenerationError("artifact path escaped the storage root")
    if path.parent != directory:
        raise FileGenerationError("artifact path escaped the owner directory")
    return path


def write_artifact(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _safe_title(title: str) -> str:
    cleaned = " ".join(title.split())
    return cleaned[:120] or "Deliverable"


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf(title: str, body: str) -> bytes:
    lines = [title, *body.splitlines()][:40]
    commands = ["BT", "/F1 12 Tf", "72 740 Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append("0 -16 Td")
        commands.append(f"({_pdf_escape(line[:100])}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", errors="replace")
    objects = [
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n",
        (
            b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
        ),
        b"4 0 obj<< /Length "
        + str(len(stream)).encode()
        + b" >>stream\n"
        + stream
        + b"\nendstream\nendobj\n",
        b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(output))
        output.extend(obj)
    xref = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(output)


def _docx(title: str, body: str) -> bytes:
    paragraphs = "".join(
        f"<w:p><w:r><w:t>{escape(line)}</w:t></w:r></w:p>" for line in [title, *body.splitlines()]
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraphs}</w:body></w:document>"
    )
    return _ooxml(
        {
            "[Content_Types].xml": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/word/document.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                "</Types>"
            ),
            "_rels/.rels": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                'Target="word/document.xml"/>'
                "</Relationships>"
            ),
            "word/document.xml": document,
        }
    )


def _xlsx(title: str, body: str) -> bytes:
    rows = ["Title", title, *body.splitlines()]
    sheet_rows = "".join(
        (
            f'<row r="{index}"><c r="A{index}" t="inlineStr"><is><t>'
            f"{escape(value)}</t></is></c></row>"
        )
        for index, value in enumerate(rows, start=1)
    )
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{sheet_rows}</sheetData></worksheet>"
    )
    return _ooxml(
        {
            "[Content_Types].xml": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                '<Override PartName="/xl/worksheets/sheet1.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                "</Types>"
            ),
            "_rels/.rels": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                'Target="xl/workbook.xml"/>'
                "</Relationships>"
            ),
            "xl/workbook.xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
            ),
            "xl/_rels/workbook.xml.rels": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                'Target="worksheets/sheet1.xml"/>'
                "</Relationships>"
            ),
            "xl/worksheets/sheet1.xml": sheet,
        }
    )


def _pptx(title: str, body: str) -> bytes:
    slide = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        "<p:cSld><p:spTree>"
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        "<p:grpSpPr/>"
        '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
        "<p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/>"
        f"<a:p><a:r><a:t>{escape(title)}</a:t></a:r></a:p>"
        f"<a:p><a:r><a:t>{escape(body[:2000])}</a:t></a:r></a:p>"
        "</p:txBody></p:sp></p:spTree></p:cSld></p:sld>"
    )
    return _ooxml(
        {
            "[Content_Types].xml": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/ppt/presentation.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
                '<Override PartName="/ppt/slides/slide1.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
                "</Types>"
            ),
            "_rels/.rels": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                'Target="ppt/presentation.xml"/>'
                "</Relationships>"
            ),
            "ppt/presentation.xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst></p:presentation>'
            ),
            "ppt/_rels/presentation.xml.rels": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
                'Target="slides/slide1.xml"/>'
                "</Relationships>"
            ),
            "ppt/slides/slide1.xml": slide,
        }
    )


def _csv(title: str, body: str) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["title", "content"])
    for line in body.splitlines() or [title]:
        writer.writerow([title, line])
    return buffer.getvalue().encode("utf-8")


def _python(title: str, body: str) -> bytes:
    comment = f"# {title}\n"
    source = body if "\n" in body or body.startswith(("def ", "import ", "#", '"""')) else body
    if not source.endswith("\n"):
        source += "\n"
    return (comment + source).encode("utf-8")


def _json(title: str, body: str) -> bytes:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = {"title": title, "content": body}
    return json.dumps(parsed, indent=2).encode("utf-8") + b"\n"


def _zip(title: str, body: str) -> bytes:
    inner = render_file(file_format="json", title=title, body=body)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(inner.filename, inner.data)
    return buffer.getvalue()


def _ooxml(parts: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in parts.items():
            archive.writestr(name, payload)
    return buffer.getvalue()
