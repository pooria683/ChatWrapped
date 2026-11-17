"""Google Gemini (Takeout) export parser — EXPERIMENTAL, best effort.

Google Takeout archives are huge and loosely structured, so this parser only
looks at JSON files whose path contains a ``gemini`` segment (e.g.
``Takeout/Gemini Apps/...``) and tries a small set of known chat shapes:

* a list of conversations, each with ``messages``/``turns``: a list of
  ``{"role": "user"|"model", "parts": [{"text": ...} | "..."], ...}``;
* a top-level ``{"conversations": [...]}`` wrapper around the above.

Anything unrecognized is skipped with a warning — never an exception.
"""

from __future__ import annotations

import re
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

GEMINI_PATH_RE = re.compile(r"gemini", re.IGNORECASE)
MESSAGE_LIST_KEYS = ("messages", "turns", "chat")
ROLE_KEYS = ("role", "author")
TEXT_KEYS = ("parts", "text", "content", "message")


def _message_text(m: dict) -> str:
    for key in TEXT_KEYS:
        if key in m:
            t = extract_text(m[key])
            if t:
                return t
    return ""


def _message_role(m: dict) -> str | None:
    for key in ROLE_KEYS:
        r = str(m.get(key) or "").lower()
        if r in ("user", "human"):
            return "user"
        if r in ("model", "assistant", "gemini", "bot"):
            return "assistant"
    return None


def parse_gemini_payload(payload: Any, source: str) -> list[Conversation]:
    out: list[Conversation] = []
    if isinstance(payload, dict):
        for key in ("conversations", "chats", "data"):
            if isinstance(payload.get(key), list):
                return parse_gemini_payload(payload[key], source)
        return out
    if not isinstance(payload, list):
        return out
    for i, conv in enumerate(payload):
        if not isinstance(conv, dict):
            continue
        msg_list = None
        for key in MESSAGE_LIST_KEYS:
            if isinstance(conv.get(key), list):
                msg_list = conv[key]
                break
        if msg_list is None:
            continue
        cid = str(conv.get("id") or conv.get("uuid") or conv.get("conversation_id") or f"gemini-{i}")
        c = Conversation(
            id=cid,
            platform="gemini",
            title=conv.get("title") or conv.get("name") or None,
            created_at=parse_time(conv.get("created_at") or conv.get("create_time")),
            updated_at=parse_time(conv.get("updated_at") or conv.get("update_time")),
            source=source,
        )
        skipped = 0
        first_ts = None
        for j, m in enumerate(msg_list):
            if not isinstance(m, dict):
                skipped += 1
                continue
            role = _message_role(m)
            if role is None:
                skipped += 1
                continue
            text = _message_text(m)
            if not text:
                skipped += 1
                continue
            ts = parse_time(m.get("created_at") or m.get("create_time") or m.get("timestamp") or m.get("time"))
            if ts and (first_ts is None or ts < first_ts):
                first_ts = ts
            model = m.get("model") or conv.get("model")
            c.messages.append(
                Message(
                    id=str(m.get("id") or m.get("uuid") or f"{cid}-{j}"),
                    conversation_id=cid,
                    role=role,
                    text=text,
                    created_at=ts,
                    updated_at=parse_time(m.get("updated_at")),
                    model=model,
                )
            )
        if first_ts and c.created_at is None:
            c.created_at = first_ts
        c.meta["skipped_messages"] = skipped
        c.meta["experimental"] = True
        if c.messages:
            out.append(c)
    return out


def _safe_json(data: bytes) -> Any:
    try:
        return read_json_bytes(data)
    except Exception:
        return None


class GeminiParser(BaseParser):
    platform = "gemini"
    name = "Google Gemini (experimental)"

    def detect(self, path: Path) -> bool:
        try:
            for f in walk_files(path):
                if not GEMINI_PATH_RE.search(str(f)):
                    continue
                if is_zip(f):
                    for name, data in zip_members(f):
                        if name.lower().endswith(".json") and GEMINI_PATH_RE.search(name):
                            convs = parse_gemini_payload(_safe_json(data), name)
                            if convs:
                                return True
                elif f.suffix.lower() == ".json":
                    convs = parse_gemini_payload(_safe_json(f.read_bytes()[: 512 * 1024 * 1024 + 1]), str(f))
                    if convs:
                        return True
        except Exception:
            return False
        return False

    def parse_file(self, f: Path, warnings: list[ParseWarning]) -> list[Conversation]:
        out: list[Conversation] = []
        if not GEMINI_PATH_RE.search(str(f)):
            return out
        if is_zip(f):
            for name, data in zip_members(f):
                if name.lower().endswith(".json") and GEMINI_PATH_RE.search(name):
                    out.extend(parse_gemini_payload(_safe_json(data), f"{f}!{name}"))
        elif f.suffix.lower() == ".json":
            try:
                payload = load_json_file(f)
            except Exception:
                return out
            out.extend(parse_gemini_payload(payload, str(f)))
        return out
