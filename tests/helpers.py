"""Materialize synthetic platform exports into a directory.

Used by both conftest fixtures and the CLI subprocess tests.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def make_chatgpt_legacy(root: Path) -> Path:
    p = root / "conversations.json"
    p.write_text(json.dumps(_fixture("chatgpt_legacy.json")), encoding="utf-8")
    return p


def make_chatgpt_nested(root: Path) -> Path:
    inner = json.dumps(_fixture("chatgpt_nested_inner.json")).encode("utf-8")
    outer = _zip_bytes({
        "User Online Activity/Conversations__a1b2c3-chatgpt-0001.zip": _zip_bytes({"conversations.json": inner}),
        "User Online Activity/other-activity.json": b"{}",
    })
    p = root / "chatgpt-export.zip"
    p.write_bytes(outer)
    return p


def make_claude_export(root: Path) -> Path:
    outer = _zip_bytes({
        "conversations-000.zip": _zip_bytes({
            "conversations.json": json.dumps(_fixture("claude_conversations.json")).encode("utf-8")
        }),
        "projects-000.zip": _zip_bytes({
            "projects.json": json.dumps(_fixture("claude_projects.json")).encode("utf-8")
        }),
        "memories.json": json.dumps(_fixture("claude_memories.json")).encode("utf-8"),
    })
    p = root / "claude-data-export.zip"
    p.write_bytes(outer)
    return p


def make_gemini_takeout(root: Path) -> Path:
    gem = root / "Takeout" / "Gemini Apps" / "exports"
    gem.mkdir(parents=True, exist_ok=True)
    (gem / "chats.json").write_text(json.dumps(_fixture("gemini_chats.json")), encoding="utf-8")
    search = root / "Takeout" / "Search"
    search.mkdir(parents=True, exist_ok=True)
    (search / "MyActivity.json").write_text('[{"time": "2026-01-01"}]', encoding="utf-8")
    return root / "Takeout"


def make_all_exports(root: Path) -> list[Path]:
    root.mkdir(parents=True, exist_ok=True)
    return [
        make_chatgpt_legacy(root),
        make_chatgpt_nested(root),
        make_claude_export(root),
        make_gemini_takeout(root),
    ]
