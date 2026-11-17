"""Stats engine — pure Python, no LLM, no network.

Computes a JSON-serializable stats dict from a merged :class:`Dataset`.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .merge import Dataset
from .topics import tfidf_scores, topics_by_month, top_topics

SCHEMA_VERSION = 1
MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December",
}
NIGHT_START_HOUR = 23  # night window = 23:00–05:59
EARLY_END_HOUR = 6

DEFAULT_RATES_PATH = Path(__file__).resolve().parent / "rates.json"


def load_rates(path: Path | None = None, overrides: dict | None = None) -> dict:
    """Load packaged rates, optionally overlaid with user overrides."""
    p = path or DEFAULT_RATES_PATH
    try:
        rates = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        rates = {"default": {"input_per_mtok": 2.5, "output_per_mtok": 10.0}}
    rates = {k: v for k, v in rates.items() if not k.startswith("_")}
    if overrides:
        for k, v in overrides.items():
            if isinstance(v, dict) and "input_per_mtok" in v:
                rates[k] = v
    if "default" not in rates:
        rates["default"] = {"input_per_mtok": 2.5, "output_per_mtok": 10.0}
    return rates


def rate_for(model: Optional[str], rates: dict) -> tuple[str, dict]:
    """Longest-substring match of the model slug against the rate table."""
    if model:
        slug = model.lower()
        candidates = [(k, v) for k, v in rates.items() if k != "default" and k in slug]
        if candidates:
            candidates.sort(key=lambda kv: len(kv[0]), reverse=True)
            return candidates[0]
    return "default", rates["default"]


def est_tokens(text: str) -> int:
    """Rough token estimate: chars / 4."""
    return max(1, len(text) // 4) if text else 0


def _normalize_source(source: str) -> str:
    """Strip absolute dirs so reports are reproducible: 'dir/export.zip!member' -> 'export.zip!member'."""
    if not source:
        return source
    parts = source.split("!")
    head = Path(parts[0]).name or parts[0]
    return "!".join([head, *parts[1:]]) if len(parts) > 1 else head


def _truncate(text: str, n: int = 80) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _excerpt(text: str, redact: bool, n: int = 80) -> str:
    return "[redacted]" if redact else _truncate(text, n)


def _night_sort_key(dt: datetime) -> int:
    """Minutes since 22:00 — 3:47 AM ranks later into the night than 23:30."""
    minutes = dt.hour * 60 + dt.minute
    since_2200 = (minutes - 22 * 60) % (24 * 60)
    return since_2200


def _is_night(dt: datetime) -> bool:
    return dt.hour >= NIGHT_START_HOUR or dt.hour < EARLY_END_HOUR


def compute_stats(
    ds: Dataset,
    year: int | None = None,
    rates: dict | None = None,
    redact: bool = False,
    now: datetime | None = None,
) -> dict:
    rates = rates or load_rates()
    now = now or datetime.now(timezone.utc)
    messages = list(ds.messages)
    user_msgs = [m for m in messages if m.role == "user"]
    asst_msgs = [m for m in messages if m.role == "assistant"]

    words = sum(len(m.text.split()) for m in messages)
    chars = sum(len(m.text) for m in messages)
    tokens = sum(est_tokens(m.text) for m in messages)

    # ---- cost / model breakdown -------------------------------------------
    models: dict[str, dict[str, Any]] = {}
    total_cost = 0.0
    for m in messages:
        key = m.model or "unknown"
        entry = models.setdefault(key, {"messages": 0, "user_messages": 0, "assistant_messages": 0,
                                        "est_tokens": 0, "est_cost_usd": 0.0, "rate_key": None})
        entry["messages"] += 1
        entry["est_tokens"] += est_tokens(m.text)
        entry["user_messages" if m.role == "user" else "assistant_messages"] += 1
        rate_key, rate = rate_for(m.model, rates)
        entry["rate_key"] = rate_key
        tok = est_tokens(m.text)
        price = rate["input_per_mtok"] if m.role == "user" else rate["output_per_mtok"]
        entry["est_cost_usd"] += tok * price / 1_000_000
        total_cost += tok * price / 1_000_000
    for entry in models.values():
        entry["est_cost_usd"] = round(entry["est_cost_usd"], 4)
    models_sorted = dict(sorted(models.items(), key=lambda kv: kv[1]["est_tokens"], reverse=True))

    # ---- activity ----------------------------------------------------------
    per_day: Counter = Counter()
    per_month: Counter = Counter()
    per_weekday: Counter = Counter()
    for m in messages:
        if m.created_at is None:
            continue
        d = m.created_at.date().isoformat()
        per_day[d] += 1
        per_month[m.created_at.month] += 1
        per_weekday[m.created_at.weekday()] += 1  # Monday=0

    busiest_day = None
    if per_day:
        # max count, tie -> earliest date
        best_date, best_count = sorted(per_day.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        busiest_day = {"date": best_date, "messages": best_count}

    timed = [m for m in messages if m.created_at is not None]
    night_msgs = [m for m in timed if _is_night(m.created_at)]
    latest_night = None
    pool = night_msgs or timed
    if pool:
        m = max(pool, key=lambda m: _night_sort_key(m.created_at))
        conv = next((c for c in ds.conversations if c.id == m.conversation_id), None)
        latest_night = {
            "time": m.created_at.strftime("%H:%M"),
            "time_human": m.created_at.strftime("%-I:%M %p") if hasattr(m.created_at, "strftime") else m.created_at.strftime("%H:%M"),
            "date": m.created_at.date().isoformat(),
            "in_night_window": bool(night_msgs),
            "conversation_title": (conv.title if conv else None),
            "excerpt": _excerpt(m.text, redact),
            "model": m.model,
        }

    active_days = len(per_day)
    avg_per_active_day = round(len(messages) / active_days, 2) if active_days else 0.0

    # ---- topics ------------------------------------------------------------
    topics_overall = top_topics(user_msgs, 20)
    topics_month = topics_by_month(user_msgs, per_month=3, month_names=MONTH_NAMES)

    # ---- milestones --------------------------------------------------------
    first_conv = None
    convs_with_time = [c for c in ds.conversations if c.created_at is not None]
    if convs_with_time:
        c = min(convs_with_time, key=lambda c: c.created_at)
        first_user = next((m for m in c.messages if m.role == "user"), None)
        first_conv = {
            "title": c.title,
            "date": c.created_at.date().isoformat(),
            "platform": c.platform,
            "first_prompt": _excerpt(first_user.text, redact) if first_user else None,
        }
    elif messages:
        m = min(timed, key=lambda m: m.created_at) if timed else None
        if m is not None:
            conv = next((c for c in ds.conversations if c.id == m.conversation_id), None)
            first_conv = {
                "title": conv.title if conv else None,
                "date": m.created_at.date().isoformat(),
                "platform": conv.platform if conv else None,
                "first_prompt": _excerpt(m.text, redact),
            }

    longest_conv = None
    if ds.conversations:
        c = max(ds.conversations, key=lambda c: (len(c.messages), c.word_count()))
        longest_conv = {
            "title": c.title,
            "platform": c.platform,
            "messages": len(c.messages),
            "words": c.word_count(),
            "date": c.created_at.date().isoformat() if c.created_at else None,
        }

    # most-edited prompt: user messages sharing the same parent node (branches)
    most_edited = None
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for c in ds.conversations:
        for m in c.user_messages():
            if m.parent_id:
                groups[(c.id, m.parent_id)].append(m)
    edited = [(k, v) for k, v in groups.items() if len(v) > 1]
    if edited:
        (cid, _parent), versions = max(edited, key=lambda kv: len(kv[1]))
        conv = next((c for c in ds.conversations if c.id == cid), None)
        most_edited = {
            "versions": len(versions),
            "conversation_title": conv.title if conv else None,
            "prompt": _excerpt(sorted(versions, key=lambda m: m.created_at or m.created_at)[0].text, redact),
        }

    # ---- assemble ----------------------------------------------------------
    platforms = ds.platforms()
    years_present = sorted({m.created_at.year for m in timed} | {c.created_at.year for c in convs_with_time})

    return {
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "generated_at": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
            "year": year,
            "years_present": years_present,
            "platforms": platforms,
            "sources": sorted(_normalize_source(s) for s in ds.sources),
            "redacted": redact,
            "tool": "chatwrapped",
            "privacy": "parsed 100% locally; zero network calls",
            "warnings": sorted(f"{_normalize_source(w.source)}: {w.message}" for w in ds.warnings),
        },
        "totals": {
            "conversations": len(ds.conversations),
            "messages": len(messages),
            "user_messages": len(user_msgs),
            "assistant_messages": len(asst_msgs),
            "words": words,
            "chars": chars,
            "est_tokens": tokens,
            "est_cost_usd": round(total_cost, 4),
            "cost_note": "estimate only — user messages priced as input, assistant as output, chars/4 tokens",
        },
        "activity": {
            "per_day": dict(sorted(per_day.items())),
            "per_month": {MONTH_NAMES[k]: per_month[k] for k in sorted(per_month)},
            "per_month_num": {str(k): per_month[k] for k in sorted(per_month)},
            "per_weekday": {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][k]: per_weekday[k] for k in sorted(per_weekday)},
            "busiest_day": busiest_day,
            "active_days": active_days,
            "avg_messages_per_active_day": avg_per_active_day,
            "latest_night": latest_night,
        },
        "topics": {
            "overall": topics_overall,
            "by_month": topics_month,
        },
        "milestones": {
            "first_conversation": first_conv,
            "longest_conversation": longest_conv,
            "most_edited_prompt": most_edited,
            "latest_night_message": latest_night,
        },
        "models": models_sorted,
    }
