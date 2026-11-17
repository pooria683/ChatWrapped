"""Common parser interface and the normalized internal schema.

Every platform parser turns its official export format into the same
``Conversation`` / ``Message`` dataclasses so the stats engine never has to
care about platforms again.

Parsers must NEVER raise on malformed input: they catch everything, skip the
bad file, and record a warning instead.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

# Safety guard: never read a single zip member larger than this.
MAX_MEMBER_BYTES = 512 * 1024 * 1024

MIN_DT = datetime.min.replace(tzinfo=timezone.utc)


@dataclass
class Message:
    id: str
    conversation_id: str
    role: str  # "user" | "assistant"
    text: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model: Optional[str] = None
    parent_id: Optional[str] = None
    meta: dict = field(default_factory=dict)


@dataclass
class Conversation:
    id: str
    platform: str  # "chatgpt" | "claude" | "gemini"
    title: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    messages: list[Message] = field(default_factory=list)
    source: str = ""
    meta: dict = field(default_factory=dict)

    def user_messages(self) -> list[Message]:
        return [m for m in self.messages if m.role == "user"]

    def assistant_messages(self) -> list[Message]:
        return [m for m in self.messages if m.role == "assistant"]

    def word_count(self) -> int:
        return sum(len(m.text.split()) for m in self.messages)


@dataclass
class ParseWarning:
    source: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.source}: {self.message}"


@dataclass
class ParseResult:
    conversations: list[Conversation] = field(default_factory=list)
    warnings: list[ParseWarning] = field(default_factory=list)

    @property
    def message_count(self) -> int:
        return sum(len(c.messages) for c in self.conversations)


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

def parse_time(value: Any) -> Optional[datetime]:
    """Parse unix epochs (number or numeric string) and ISO-8601 strings."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if s.replace(".", "", 1).lstrip("-").isdigit():
            return parse_time(float(s))
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


def extract_text(parts: Any) -> str:
    """Flatten ChatGPT-style ``parts`` (strings and/or dicts) into text."""
    if parts is None:
        return ""
    if isinstance(parts, str):
        return parts.strip()
    out: list[str] = []
    if isinstance(parts, (list, tuple)):
        for p in parts:
            if isinstance(p, str):
                out.append(p)
            elif isinstance(p, dict):
                t = p.get("text") or p.get("content") or p.get("code") or ""
                if isinstance(t, str):
                    out.append(t)
                elif isinstance(t, list):
                    out.append(extract_text(t))
    elif isinstance(parts, dict):
        return extract_text([parts])
    return "\n".join(x.strip() for x in out if x and x.strip())


def walk_files(path: Path) -> Iterable[Path]:
    """Yield every regular file under ``path`` (or ``path`` itself)."""
    if path.is_dir():
        for p in sorted(path.rglob("*")):
            if p.is_file():
                yield p
    elif path.is_file():
        yield path


def read_json_bytes(data: bytes) -> Any:
    """Decode JSON bytes, tolerating a UTF-8 BOM."""
    if data[:3] == b"\xef\xbb\xbf":
        data = data[3:]
    return json.loads(data.decode("utf-8", errors="replace"))


def load_json_file(path: Path) -> Any:
    with open(path, "rb") as fh:
        return read_json_bytes(fh.read(MAX_MEMBER_BYTES + 1))


def zip_members(path: Path) -> list[tuple[str, bytes]]:
    """Return [(member_name, bytes)] for a zip, skipping oversized members."""
    out: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            if info.file_size > MAX_MEMBER_BYTES:
                continue
            out.append((info.filename, zf.read(info)))
    return out


def is_zip(path: Path) -> bool:
    try:
        return path.is_file() and zipfile.is_zipfile(path)
    except OSError:
        return False


class BaseParser:
    """Interface every platform parser implements.

    Subclasses implement :meth:`detect` (content sniff) and
    :meth:`parse_file` (turn one file into conversations). :meth:`parse` is a
    hardened wrapper that walks a path and NEVER raises on malformed input —
    bad files are skipped and recorded as warnings.
    """

    platform = "base"
    name = "Base parser"

    def detect(self, path: Path) -> bool:  # pragma: no cover - abstract
        raise NotImplementedError

    def parse_file(self, path: Path, warnings: list[ParseWarning]) -> list[Conversation]:
        return []

    def parse(self, path: Path) -> ParseResult:
        convs: list[Conversation] = []
        warnings: list[ParseWarning] = []
        try:
            for f in walk_files(path):
                try:
                    convs.extend(self.parse_file(f, warnings))
                except Exception as exc:  # noqa: BLE001 - graceful by contract
                    warnings.append(ParseWarning(str(f), f"skipped unreadable file ({exc.__class__.__name__})"))
        except Exception as exc:  # noqa: BLE001 - graceful by contract
            warnings.append(ParseWarning(str(path), f"could not read path ({exc.__class__.__name__})"))
        return ParseResult(conversations=convs, warnings=warnings)
