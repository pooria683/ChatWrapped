"""Anthropic / Claude export parser.

Official exports ship as a zip containing ``conversations-000.zip`` (which
itself contains ``conversations.json``), plus optional ``projects`` and
``memories`` zips. A raw ``conversations.json`` is also accepted.

``conversations.json`` is a list of::

    {"uuid": ..., "name": ..., "created_at": ..., "updated_at": ...,
     "chat_messages": [{"uuid": ..., "text": ..., "sender": "human"|"assistant",
                        "created_at": ..., "updated_at": ...}, ...]}

Projects and memories are counted and reported as metadata, not conversations.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Any

from .base import (
    BaseParser,
    Conversation,
    Message,
    ParseWarning,
    is_zip,
    load_json_file,
    parse_time,
    read_json_bytes,
    walk_files,
    zip_members,
)

CONVERSATIONS_MEMBER_RE = re.compile(r"conversations(-\d+)?\.json$", re.IGNORECASE)


def looks_like_claude(payload: Any) -> bool:
    if not isinstance(payload, list) or not payload:
        return False
    dicts = [c for c in payload if isinstance(c, dict)]
    if not dicts:
        return False
    hits = sum(1 for c in dicts[:10] if isinstance(c.get("chat_messages"), list))
    return hits >= max(1, len(dicts[:10]) // 2)


def parse_conversations_payload(payload: Any, source: str) -> list[Conversation]:
    out: list[Conversation] = []
    if not isinstance(payload, list):
        return out
    for i, conv in enumerate(payload):
        if not isinstance(conv, dict):
            continue
        msgs = conv.get("chat_messages")
        if not isinstance(msgs, list):
            continue
        cid = str(conv.get("uuid") or conv.get("id") or f"claude-{i}")
        c = Conversation(
            id=cid,
            platform="claude",
            title=conv.get("name") or conv.get("title") or None,
            created_at=parse_time(conv.get("created_at")),
            updated_at=parse_time(conv.get("updated_at")),
            source=source,
        )
        skipped = 0
        for j, m in enumerate(msgs):
            if not isinstance(m, dict):
                skipped += 1
                continue
            sender = str(m.get("sender") or "").lower()
            if sender in ("human", "user"):
                role = "user"
            elif sender == "assistant":
                role = "assistant"
            else:
                skipped += 1
                continue
            text = m.get("text") or ""
            if not isinstance(text, str) or not text.strip():
                skipped += 1
                continue
            c.messages.append(
                Message(
                    id=str(m.get("uuid") or f"{cid}-{j}"),
                    conversation_id=cid,
                    role=role,
                    text=text.strip(),
                    created_at=parse_time(m.get("created_at")),
                    updated_at=parse_time(m.get("updated_at")),
                    model=m.get("model"),
                    meta={"sender": sender},
                )
            )
        c.meta["skipped_messages"] = skipped
        if c.messages:
            out.append(c)
    return out


def _safe_json(data: bytes) -> Any:
    try:
        return read_json_bytes(data)
    except Exception:
        return None


class ClaudeParser(BaseParser):
    platform = "claude"
    name = "Anthropic Claude"

    def detect(self, path: Path) -> bool:
        try:
            for f in walk_files(path):
                if is_zip(f):
                    for name, data in zip_members(f):
                        base = name.rsplit("/", 1)[-1].lower()
                        if base.endswith(".zip") and "conversation" in base:
                            if self._zip_has_claude(data):
                                return True
                        if CONVERSATIONS_MEMBER_RE.search(name) and looks_like_claude(_safe_json(data)):
                            return True
                elif f.suffix.lower() == ".json":
                    try:
                        if looks_like_claude(load_json_file(f)):
                            return True
                    except Exception:
                        continue
        except Exception:
            return False
        return False

    def _zip_has_claude(self, data: bytes) -> bool:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for info in zf.infolist():
                    if CONVERSATIONS_MEMBER_RE.search(info.filename):
                        try:
                            if looks_like_claude(read_json_bytes(zf.read(info))):
                                return True
                        except Exception:
                            continue
        except Exception:
            return False
        return False

    def parse_file(self, f: Path, warnings: list[ParseWarning]) -> list[Conversation]:
        out: list[Conversation] = []
        if is_zip(f):
            for name, data in zip_members(f):
                base = name.rsplit("/", 1)[-1].lower()
                if base.endswith(".zip") and "conversation" in base:
                    out.extend(self._parse_inner_zip(data, f"{f}!{name}", warnings))
                elif CONVERSATIONS_MEMBER_RE.search(name):
                    payload = _safe_json(data)
                    if looks_like_claude(payload):
                        out.extend(parse_conversations_payload(payload, f"{f}!{name}"))
                elif "project" in base:
                    n = self._count_in_container(data)
                    if n:
                        warnings.append(ParseWarning(f"{f}!{name}", f"found {n} project(s) — counted as metadata only"))
                elif "memor" in base:
                    n = self._count_in_container(data)
                    if n:
                        warnings.append(ParseWarning(f"{f}!{name}", f"found {n} memor(y/ies) — counted as metadata only"))
        elif f.suffix.lower() == ".json":
            try:
                payload = load_json_file(f)
            except Exception:
                return out
            if looks_like_claude(payload):
                out.extend(parse_conversations_payload(payload, str(f)))
        return out

    def _count_in_container(self, data: bytes) -> int:
        """Count list items in a plain-JSON or inner-zip member."""
        payload = _safe_json(data)
        if payload is not None:
            return _count_list(payload)
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for info in zf.infolist():
                    if not info.is_dir() and info.filename.lower().endswith(".json"):
                        n = _count_list(_safe_json(zf.read(info)))
                        if n:
                            return n
        except Exception:
            return 0
        return 0

    def _parse_inner_zip(self, data: bytes, source: str, warnings: list[ParseWarning]) -> list[Conversation]:
        out: list[Conversation] = []
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for info in zf.infolist():
                    if info.is_dir() or not CONVERSATIONS_MEMBER_RE.search(info.filename):
                        continue
                    if info.file_size > 512 * 1024 * 1024:
                        continue
                    payload = _safe_json(zf.read(info))
                    if looks_like_claude(payload):
                        out.extend(parse_conversations_payload(payload, f"{source}!{info.filename}"))
        except zipfile.BadZipFile:
            warnings.append(ParseWarning(source, "inner zip is corrupt; skipped"))
        return out


def _count_list(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("projects", "memories", "items", "data"):
            v = payload.get(key)
            if isinstance(v, list):
                return len(v)
    return 0
