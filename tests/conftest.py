"""Shared pytest fixtures wrapping tests/helpers.py builders."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))  # for helpers.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root

import helpers  # noqa: E402


@pytest.fixture
def chatgpt_legacy_path(tmp_path) -> Path:
    return helpers.make_chatgpt_legacy(tmp_path)


@pytest.fixture
def chatgpt_nested_zip(tmp_path) -> Path:
    return helpers.make_chatgpt_nested(tmp_path)


@pytest.fixture
def claude_export_zip(tmp_path) -> Path:
    return helpers.make_claude_export(tmp_path)


@pytest.fixture
def claude_raw_json(tmp_path) -> Path:
    import json

    p = tmp_path / "claude-conversations.json"
    p.write_text(json.dumps(helpers._fixture("claude_conversations.json")), encoding="utf-8")
    return p


@pytest.fixture
def gemini_takeout(tmp_path) -> Path:
    return helpers.make_gemini_takeout(tmp_path)


@pytest.fixture
def all_export_paths(tmp_path):
    return helpers.make_all_exports(tmp_path)


@pytest.fixture
def merged_dataset(all_export_paths):
    from chatwrapped.merge import merge
    from chatwrapped.parsers import parse_paths

    return merge(parse_paths(all_export_paths))


@pytest.fixture
def fixed_now():
    from datetime import datetime, timezone

    return datetime(2026, 12, 1, 12, 0, 0, tzinfo=timezone.utc)
