"""OpenAI / ChatGPT export parser.

Supports both official shapes:

* legacy single-file ``conversations.json`` — a list of conversations, each
  with a ``mapping`` of node-id -> node; nodes form a tree with branches
  (edits/regenerations appear as sibling nodes sharing a parent);
* the newer nested-zip layout
  ``User Online Activity/Conversations__*-chatgpt-0001.zip`` where each inner
  zip again contains a ``conversations.json``.

System and tool messages are skipped (counted in ``meta['skipped']``).
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
    extract_text,
    is_zip,
    load_json_file,
    parse_time,
    read_json_bytes,
    walk_files,
    zip_members,
)

NESTED_ZIP_RE = re.compile(r"conversations__.*chatgpt.*\.zip$", re.IGNORECASE)
CONVERSATIONS_JSON = "conversations.json"


def looks_like_chatgpt(payload: Any) -> bool:
    """Content sniff: a non-empty list of dicts that carry a ``mapping``."""
    if not isinstance(payload, list) or not payload:
        return False
    dicts = [c for c in payload if isinstance(c, dict)]
    if not dicts:
        return False
    hits = sum(1 for c in dicts[:10] if "mapping" in c)
    return hits >= max(1, len(dicts[:10]) // 2)


def parse_conversations_payload(payload: Any, source: str) -> list[Conversation]:
    out: list[Conversation] = []
    if not isinstance(payload, list):
        return out
    for i, conv in enumerate(payload):
        if not isinstance(conv, dict):
            continue
        mapping = conv.get("mapping")
        if not isinstance(mapping, dict):
            continue
        cid = str(conv.get("id") or conv.get("uuid") or f"chatgpt-{i}")
        c = Conversation(
            id=cid,
            platform="chatgpt",
            title=conv.get("title") or None,
            created_at=parse_time(conv.get("create_time")),
            updated_at=parse_time(conv.get("update_time")),
            source=source,
        )
        skipped = 0
        for node_id, node in mapping.items():
            if not isinstance(node, dict):
                continue
            msg = node.get("message")
            if not isinstance(msg, dict):
                continue
            role = ((msg.get("author") or {}).get("role") or "unknown").lower()
            if role in ("system", "tool"):
                skipped += 1
                continue
            content = msg.get("content") or {}
            ctype = content.get("content_type")
            if ctype in ("text", "multimodal_text"):
                text = extract_text(content.get("parts"))
            elif ctype == "code":
                text = content.get("text") or ""
            else:
                text = ""
            if not text:
                skipped += 1
                continue
            model = (msg.get("metadata") or {}).get("model_slug")
            c.messages.append(
                Message(
                    id=str(msg.get("id") or node_id),
                    conversation_id=cid,
                    role="user" if role == "user" else "assistant",
                    text=text,
                    created_at=parse_time(msg.get("create_time") or node.get("create_time")),
                    updated_at=parse_time(msg.get("update_time") or node.get("update_time")),
                    model=model,
                    parent_id=node.get("parent"),
                    meta={"node_id": node_id, "content_type": ctype},
                )
            )
        c.meta["skipped_messages"] = skipped
        if c.messages:
            out.append(c)
    return out


def _parse_json_payload(data: bytes, source: str) -> list[Conversation]:
    try:
        payload = read_json_bytes(data)
    except Exception:
        return []
    if looks_like_chatgpt(payload):
        return parse_conversations_payload(payload, source)
    return []


class ChatGPTParser(BaseParser):
    platform = "chatgpt"
    name = "OpenAI ChatGPT"

    def detect(self, path: Path) -> bool:
        try:
            for f in walk_files(path):
                if is_zip(f):
                    for name, data in zip_members(f):
                        if NESTED_ZIP_RE.search(name):
                            return True
                        if name.lower().endswith(CONVERSATIONS_JSON) and looks_like_chatgpt(_safe_json(data)):
                            return True
                elif f.suffix.lower() == ".json":
                    try:
                        if looks_like_chatgpt(load_json_file(f)):
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
                if NESTED_ZIP_RE.search(name):
                    out.extend(self._parse_nested_zip(data, f"{f}!{name}", warnings))
                elif name.lower().endswith(CONVERSATIONS_JSON):
                    out.extend(_parse_json_payload(data, f"{f}!{name}"))
        elif f.suffix.lower() == ".json":
            try:
                payload = load_json_file(f)
            except Exception:
                return out
            if looks_like_chatgpt(payload):
                out.extend(parse_conversations_payload(payload, str(f)))
        return out

    def _parse_nested_zip(self, data: bytes, source: str, warnings: list[ParseWarning]) -> list[Conversation]:
        out: list[Conversation] = []
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for info in zf.infolist():
                    if info.is_dir() or not info.filename.lower().endswith(".json"):
                        continue
                    if info.file_size > 512 * 1024 * 1024:
                        continue
                    out.extend(_parse_json_payload(zf.read(info), f"{source}!{info.filename}"))
        except zipfile.BadZipFile:
            warnings.append(ParseWarning(source, "nested zip is corrupt; skipped"))
        return out


def _safe_json(data: bytes) -> Any:
    try:
        return read_json_bytes(data)
    except Exception:
        return None
