"""Merge multiple exports into one deduplicated timeline.

Dedupe rules:
* conversations are keyed by ``(platform, conversation_id)`` — when the same
  conversation appears in overlapping exports, the most recently updated /
  largest version wins;
* messages inside a conversation are deduped by message id, keeping the most
  recent version (by ``updated_at``, then ``created_at``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .parsers.base import Conversation, MIN_DT, ParseResult, ParseWarning


@dataclass
class Dataset:
    conversations: list[Conversation] = field(default_factory=list)
    warnings: list[ParseWarning] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    @property
    def messages(self):
        for c in self.conversations:
            yield from c.messages

    @property
    def message_count(self) -> int:
        return sum(len(c.messages) for c in self.conversations)

    def platforms(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in self.conversations:
            out[c.platform] = out.get(c.platform, 0) + 1
        return out


def _sort_key_dt(dt: datetime | None) -> datetime:
    return dt if dt is not None else MIN_DT


def _better(new: Conversation, cur: Conversation) -> bool:
    new_key = _sort_key_dt(new.updated_at or new.created_at)
    cur_key = _sort_key_dt(cur.updated_at or cur.created_at)
    if new_key != cur_key:
        return new_key > cur_key
    return len(new.messages) > len(cur.messages)


def merge(parsed: ParseResult) -> Dataset:
    by_key: dict[tuple[str, str], Conversation] = {}
    for c in parsed.conversations:
        key = (c.platform, c.id)
        cur = by_key.get(key)
        if cur is None or _better(c, cur):
            by_key[key] = c

    out: list[Conversation] = []
    for c in by_key.values():
        seen: dict[str, object] = {}
        # sort by version recency so the last write wins (most recent version)
        for m in sorted(c.messages, key=lambda m: _sort_key_dt(m.updated_at or m.created_at)):
            seen[m.id] = m
        c.messages = sorted(seen.values(), key=lambda m: (m.created_at is None, _sort_key_dt(m.created_at)))
        out.append(c)
    out.sort(key=lambda c: (c.created_at is None, _sort_key_dt(c.created_at)))
    return Dataset(
        conversations=out,
        warnings=list(parsed.warnings),
        sources=sorted({c.source for c in out if c.source}),
    )


def filter_year(ds: Dataset, year: int) -> Dataset:
    """Keep only conversations/messages that touch ``year`` (UTC)."""
    out: list[Conversation] = []
    for c in ds.conversations:
        msgs = [m for m in c.messages if m.created_at is not None and m.created_at.year == year]
        created_in_year = c.created_at is not None and c.created_at.year == year
        if not msgs and not created_in_year:
            continue
        if msgs and c.created_at is None:
            c.created_at = min(m.created_at for m in msgs)
        c.messages = msgs if msgs else c.messages
        out.append(c)
    return Dataset(conversations=out, warnings=list(ds.warnings), sources=list(ds.sources))


def detect_year(ds: Dataset) -> int | None:
    """The most recent year present in the data (UTC)."""
    years = [m.created_at.year for m in ds.messages if m.created_at is not None]
    years += [c.created_at.year for c in ds.conversations if c.created_at is not None]
    return max(years) if years else None
