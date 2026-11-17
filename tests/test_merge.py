"""Merge / dedupe tests."""

from __future__ import annotations

from datetime import datetime, timezone

from chatwrapped.merge import detect_year, filter_year, merge
from chatwrapped.parsers.base import Conversation, Message, ParseResult


def _msg(mid, text, ts, updated=None, role="user"):
    return Message(id=mid, conversation_id="c1", role=role, text=text,
                   created_at=ts, updated_at=updated)


def _ts(y, m, d, h=0):
    return datetime(y, m, d, h, tzinfo=timezone.utc)


def test_merge_dedupes_conversations_by_platform_id():
    old = Conversation(id="c1", platform="chatgpt", title="old",
                       messages=[_msg("m1", "v1", _ts(2026, 1, 1))], updated_at=_ts(2026, 1, 1))
    new = Conversation(id="c1", platform="chatgpt", title="new",
                       messages=[_msg("m1", "v1", _ts(2026, 1, 1)), _msg("m2", "v2", _ts(2026, 1, 2))],
                       updated_at=_ts(2026, 2, 1))
    ds = merge(ParseResult(conversations=[old, new]))
    assert len(ds.conversations) == 1
    assert len(ds.conversations[0].messages) == 2  # newer/larger version wins


def test_merge_keeps_most_recent_message_version():
    c = Conversation(id="c1", platform="claude", messages=[
        _msg("m1", "edited later", _ts(2026, 1, 1), updated=_ts(2026, 3, 1)),
        _msg("m1", "original", _ts(2026, 1, 1), updated=_ts(2026, 1, 1)),
    ])
    ds = merge(ParseResult(conversations=[c]))
    assert len(ds.conversations[0].messages) == 1
    assert ds.conversations[0].messages[0].text == "edited later"


def test_merge_same_id_different_platform_kept():
    a = Conversation(id="x", platform="chatgpt", messages=[_msg("m", "a", _ts(2026, 1, 1))])
    b = Conversation(id="x", platform="claude", messages=[_msg("m", "b", _ts(2026, 1, 1))])
    ds = merge(ParseResult(conversations=[a, b]))
    assert len(ds.conversations) == 2


def test_merge_sorts_messages_by_time():
    c = Conversation(id="c", platform="chatgpt", messages=[
        _msg("b", "second", _ts(2026, 5, 5)),
        _msg("a", "first", _ts(2026, 1, 1)),
    ])
    ds = merge(ParseResult(conversations=[c]))
    assert [m.id for m in ds.conversations[0].messages] == ["a", "b"]


def test_filter_year(merged_dataset):
    ds2026 = filter_year(merged_dataset, 2026)
    assert len(ds2026.conversations) == len(merged_dataset.conversations)
    ds2025 = filter_year(merged_dataset, 2025)
    assert len(ds2025.conversations) == 0


def test_detect_year(merged_dataset):
    assert detect_year(merged_dataset) == 2026
