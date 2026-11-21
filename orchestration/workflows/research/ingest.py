"""Inventory local research files and extract text for evidence matching."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO, StringIO
import json
from pathlib import Path, PurePosixPath
import stat
import subprocess
import unicodedata
import zipfile

MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_FILES = 250

FORMATS = {
    ".htm": "html", ".html": "html", ".pdf": "pdf", ".csv": "csv", ".json": "json",
    ".md": "markdown", ".markdown": "markdown", ".txt": "text", ".zip": "zip",
    ".jpg": "image", ".jpeg": "image", ".png": "image", ".gif": "image", ".webp": "image",
    ".tif": "image", ".tiff": "image",
}


@dataclass(frozen=True)
class Source:
    metadata: dict
    text: str | None = None


def normalize_text(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).split())


class BodyText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if tag in {"head", "script", "style", "template", "noscript"}:
            self.hidden.append(tag)

    def handle_endtag(self, tag):
        if self.hidden and tag == self.hidden[-1]:
            self.hidden.pop()

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def local_path(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Source path must be relative to the repository: {relative}")
    path = (root / path).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Source path escapes the repository: {relative}")
    return path


def _archive_entries(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    entries = {}
    total = 0
    for entry in archive.infolist():
        name = entry.filename
        path = PurePosixPath(name)
        mode = entry.external_attr >> 16
        if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or stat.S_ISLNK(mode):
            raise ValueError(f"Unsafe ZIP member: {name}")
        if entry.is_dir():
            continue
        if name in entries:
            raise ValueError(f"Duplicate ZIP member: {name}")
        total += entry.file_size
        if entry.file_size > MAX_FILE_BYTES or total > MAX_ARCHIVE_BYTES or len(entries) >= MAX_ARCHIVE_FILES:
            raise ValueError("ZIP exceeds research import limits")
        entries[name] = entry
    return entries


def _parse_content(data: bytes, kind: str) -> str | None:
    if kind == "image":
        from PIL import Image

        try:
            with Image.open(BytesIO(data)) as image:
                image.verify()
        except (Image.DecompressionBombError, SyntaxError) as error:
            raise ValueError(f"Invalid image: {error}") from error
        return None
    if kind == "pdf":
        result = subprocess.run(
            ["pdftotext", "-layout", "-", "-"], input=data, capture_output=True, check=True, timeout=30,
        )
        return result.stdout.decode("utf-8")
    text = data.decode("utf-8-sig")
    if kind == "html":
        parser = BodyText()
        parser.feed(text)
        parser.close()
        return "\n".join(part.strip() for part in parser.parts if part.strip())
    if kind == "json":
        json.loads(text)
    if kind == "csv":
        reader = csv.reader(StringIO(text), strict=True)
        header = next(reader, [])
        if not header or len(set(header)) != len(header):
            raise ValueError("CSV needs a nonempty unique header")
        if not all(len(row) == len(header) for row in reader):
            raise ValueError("CSV has rows with the wrong number of columns")
    return text


def parse_source(root: Path, spec: dict, provenance: str) -> Source:
    relative = spec.get("path")
    member = spec.get("archive_member")
    metadata = {
        "source_id": spec["id"], "original_path": relative, "archive_member": member,
        "sha256": None, "url": spec.get("url"), "publisher": spec.get("publisher"),
        "published_at": spec.get("published_at"), "collected_at": spec.get("collected_at"),
        "title": spec.get("title"), "type": spec.get("source_type"), "file_type": None,
        "provenance": provenance, "parse_status": "MISSING", "parse_notes": None,
        "access_scope": spec.get("access_scope"), "network_check": spec.get("network_check"),
        "available_transcript_path": spec.get("text_path"),
    }
    if not relative:
        metadata["parse_status"] = "LEAD_ONLY"
        return Source(metadata)
    try:
        path = local_path(root, relative)
        if not path.is_file():
            metadata["parse_notes"] = "Local source file is missing"
            return Source(metadata)
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("Source file exceeds research import limit")
        data = path.read_bytes()
        metadata["sha256"] = sha256(data).hexdigest()
        kind = FORMATS.get(path.suffix.lower())
        if kind == "zip":
            metadata["archive_sha256"] = metadata["sha256"]
            with zipfile.ZipFile(BytesIO(data)) as archive:
                entries = _archive_entries(archive)
                if member:
                    if member not in entries:
                        raise ValueError(f"ZIP member is missing: {member}")
                    data = archive.read(entries[member])
                    metadata["sha256"] = sha256(data).hexdigest()
                    kind = FORMATS.get(PurePosixPath(member).suffix.lower())
                else:
                    metadata["archive_members"] = list(entries)
        elif member:
            raise ValueError("archive_member requires a ZIP source")
        metadata["file_type"] = kind
        expected = spec.get("sha256")
        if expected and expected != metadata["sha256"]:
            raise ValueError("Source SHA-256 differs from the submitted digest")
        if kind is None or (kind == "zip" and member):
            metadata["parse_status"] = "UNSUPPORTED"
            return Source(metadata)
        text = None if kind == "zip" else _parse_content(data, kind)
        metadata["parse_status"] = "PARSED" if text is None or text.strip() else "EMPTY"
        return Source(metadata, text)
    except (OSError, RuntimeError, ValueError, TypeError, csv.Error, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        metadata.update(parse_status="PARSE_ERROR", parse_notes=str(error))
        return Source(metadata)
