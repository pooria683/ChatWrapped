"""Parser tests: detection, content handling, and graceful degradation."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from chatwrapped.parsers import PARSERS, detect_path, parse_paths
from chatwrapped.parsers.base import parse_time
from chatwrapped.parsers.chatgpt import ChatGPTParser, looks_like_chatgpt
from chatwrapped.parsers.claude import ClaudeParser, looks_like_claude


# ---------------------------------------------------------------- detection

def test_detect_chatgpt_legacy(chatgpt_legacy_path):
    assert "OpenAI ChatGPT" in detect_path(chatgpt_legacy_path)


def test_detect_chatgpt_nested_zip(chatgpt_nested_zip):
    assert "OpenAI ChatGPT" in detect_path(chatgpt_nested_zip)


def test_detect_claude_zip(claude_export_zip):
    assert "Anthropic Claude" in detect_path(claude_export_zip)


def test_detect_claude_raw_json(claude_raw_json):
    assert "Anthropic Claude" in detect_path(claude_raw_json)


def test_detect_gemini_takeout(gemini_takeout):
    assert any("Gemini" in n for n in detect_path(gemini_takeout))


def test_no_cross_detection(chatgpt_legacy_path, claude_raw_json, gemini_takeout):
    assert "Anthropic Claude" not in detect_path(chatgpt_legacy_path)
    assert "OpenAI ChatGPT" not in detect_path(claude_raw_json)
    assert "OpenAI ChatGPT" not in detect_path(gemini_takeout)


# ---------------------------------------------------------------- chatgpt

def test_chatgpt_legacy_parse(chatgpt_legacy_path):
    res = ChatGPTParser().parse(chatgpt_legacy_path)
    assert len(res.conversations) == 2
    kyoto = next(c for c in res.conversations if c.id == "conv-kyoto-1")
    assert kyoto.title == "Kyoto trip planning"
    assert kyoto.platform == "chatgpt"
    # system + tool messages skipped
    roles = sorted(m.role for m in kyoto.messages)
    assert roles == ["assistant", "assistant", "user", "user"]
    assert kyoto.meta["skipped_messages"] == 2
    # model metadata captured
    models = {m.model for m in kyoto.messages if m.role == "assistant"}
    assert models == {"gpt-4o"}
    # branches: both user versions kept, sharing parent 'root'
    users = kyoto.user_messages()
    assert len(users) == 2
    assert {u.parent_id for u in users} == {"root"}


def test_chatgpt_nested_zip_parse(chatgpt_nested_zip):
    res = ChatGPTParser().parse(chatgpt_nested_zip)
    assert len(res.conversations) == 1
    c = res.conversations[0]
    assert c.id == "conv-nested-1"
    assert [m.role for m in c.messages] == ["user", "assistant"]
    assert c.messages[1].model == "gpt-5"
    assert any("User Online Activity" in s for s in [c.source])


def test_chatgpt_detect_ignores_claude_json(claude_raw_json):
    assert not ChatGPTParser().detect(claude_raw_json)
    assert looks_like_chatgpt(json.loads(claude_raw_json.read_text())) is False


# ---------------------------------------------------------------- claude

def test_claude_zip_parse(claude_export_zip):
    res = ClaudeParser().parse(claude_export_zip)
    assert len(res.conversations) == 2
    by_id = {c.id: c for c in res.conversations}
    assert by_id["claude-uuid-1"].title == "Recipe ideas"
    assert by_id["claude-uuid-1"].platform == "claude"
    # empty assistant message skipped
    assert len(by_id["claude-uuid-2"].messages) == 2
    assert by_id["claude-uuid-2"].meta["skipped_messages"] == 1
    roles = [m.role for m in by_id["claude-uuid-1"].messages]
    assert roles == ["user", "assistant"]
    # projects/memories reported as warnings, not conversations
    msgs = " ".join(w.message for w in res.warnings)
    assert "2 project(s)" in msgs
    assert "2 memor" in msgs


def test_claude_raw_json(claude_raw_json):
    res = ClaudeParser().parse(claude_raw_json)
    assert len(res.conversations) == 2
    assert looks_like_claude(json.loads(claude_raw_json.read_text()))


def test_claude_detect_ignores_chatgpt(chatgpt_legacy_path):
    assert not ClaudeParser().detect(chatgpt_legacy_path)


# ---------------------------------------------------------------- gemini

def test_gemini_takeout_parse(gemini_takeout):
    from chatwrapped.parsers.gemini import GeminiParser

    res = GeminiParser().parse(gemini_takeout)
    assert len(res.conversations) == 1
    c = res.conversations[0]
    assert c.platform == "gemini"
    assert c.title == "Weekend hike"
    assert [m.role for m in c.messages] == ["user", "assistant"]
    assert "hike" in c.messages[0].text.lower()
    # non-gemini Takeout files ignored
    assert not any("MyActivity" in c.source for c in res.conversations)


# ---------------------------------------------------------------- helpers

def test_parse_time_variants():
    from datetime import datetime, timezone

    assert parse_time(1767225600) == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert parse_time("1767225600") == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert parse_time("2026-01-01T00:00:00Z") == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert parse_time("2026-01-01T01:00:00+01:00") == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert parse_time(None) is None
    assert parse_time("not a date") is None
    assert parse_time(10**20) is None
    assert parse_time(True) is None


# ---------------------------------------------------------------- robustness

MALFORMED = "malformed"


@pytest.fixture
def malformed_dir(tmp_path):
    d = tmp_path / MALFORMED
    d.mkdir()
    (d / "garbage.bin").write_bytes(b"\x00\x01\x02 not json at all \xff\xfe")
    (d / "truncated.json").write_text('{"conversations": [{"title": "x", "mapping": {"a": {', encoding="utf-8")
    (d / "empty.json").write_text("", encoding="utf-8")
    (d / "scalar.json").write_text("42", encoding="utf-8")
    (d / "fake.zip").write_bytes(b"PK\x03\x04 broken zip contents")
    with zipfile.ZipFile(d / "junk.zip", "w") as zf:
        zf.writestr("random/readme.txt", "hello")
        zf.writestr("conversations.json", "{not valid json")
    nested = io.BytesIO()
    with zipfile.ZipFile(nested, "w") as zf:
        zf.writestr("User Online Activity/Conversations__x-chatgpt-0001.zip", b"PK\x03\x04 corrupt")
    (d / "outer.zip").write_bytes(nested.getvalue())
    (d / "deep.json").write_text(json.dumps({"a": {"b": {"c": [1, 2, {"mapping": "nope"}]}}}), encoding="utf-8")
    (d / "nulls.json").write_text("[null, 42, \"str\", {}]", encoding="utf-8")
    return d


def test_parsers_never_raise_on_malformed(malformed_dir):
    """Property-style: no parser may raise on any malformed input."""
    for parser in PARSERS:
        res = parser.parse(malformed_dir)  # must not raise
        assert isinstance(res.conversations, list)
    res = parse_paths([malformed_dir, malformed_dir / "does-not-exist.zip"])
    assert res.conversations == []
    assert res.warnings  # problems were reported, not raised


def test_parse_paths_mixed(all_export_paths):
    res = parse_paths(all_export_paths)
    # legacy(2) + nested(1) + claude(2) + gemini(1) = 6 conversations
    assert len(res.conversations) == 6
    platforms = {c.platform for c in res.conversations}
    assert platforms == {"chatgpt", "claude", "gemini"}
