"""Stats engine tests: hand-computed expectations + golden file."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from chatwrapped.stats import compute_stats, est_tokens, load_rates, rate_for

GOLDEN = Path(__file__).parent / "golden" / "stats_2026.json"


def test_totals_handcomputed(merged_dataset, fixed_now):
    stats = compute_stats(merged_dataset, year=2026, now=fixed_now)
    t = stats["totals"]
    assert t["conversations"] == 6
    assert t["messages"] == 14
    assert t["user_messages"] == 7
    assert t["assistant_messages"] == 7
    assert t["words"] > 0 and t["chars"] > 0
    assert t["est_tokens"] == sum(est_tokens(m.text) for m in merged_dataset.messages)
    assert t["est_cost_usd"] > 0


def test_activity(merged_dataset, fixed_now):
    stats = compute_stats(merged_dataset, year=2026, now=fixed_now)
    a = stats["activity"]
    assert a["busiest_day"] == {"date": "2026-01-01", "messages": 4}
    assert a["per_month"]["January"] == 4
    assert a["per_month"]["March"] == 2
    assert a["active_days"] == 6
    assert a["avg_messages_per_active_day"] == round(14 / 6, 2)
    ln = a["latest_night"]
    assert ln["time"] == "03:47"
    assert ln["time_human"] == "3:47 AM"
    assert ln["date"] == "2026-03-02"
    assert ln["in_night_window"] is True
    assert ln["conversation_title"] == "Async bug"


def test_milestones(merged_dataset, fixed_now):
    stats = compute_stats(merged_dataset, year=2026, now=fixed_now)
    ms = stats["milestones"]
    assert ms["first_conversation"]["date"] == "2026-01-01"
    assert ms["first_conversation"]["title"] == "Kyoto trip planning"
    assert ms["first_conversation"]["first_prompt"].startswith("Plan a 3-day trip to Kyoto")
    assert ms["longest_conversation"]["title"] == "Kyoto trip planning"
    assert ms["longest_conversation"]["messages"] == 4
    assert ms["most_edited_prompt"]["versions"] == 2
    assert ms["most_edited_prompt"]["prompt"] == "Plan a 3-day trip to Kyoto in April."


def test_models(merged_dataset, fixed_now):
    stats = compute_stats(merged_dataset, year=2026, now=fixed_now)
    models = stats["models"]
    assert models["gpt-4o"]["messages"] == 2
    assert models["gpt-5"]["messages"] == 1
    # longest-slug match: full slug maps to gpt-4o-mini, not gpt-4o
    assert models["gpt-4o-mini-2026-01-01"]["rate_key"] == "gpt-4o-mini"
    assert "unknown" in models and models["unknown"]["messages"] == 10


def test_redact_masks_excerpts(merged_dataset, fixed_now):
    stats = compute_stats(merged_dataset, year=2026, now=fixed_now, redact=True)
    blob = json.dumps(stats)
    assert "Plan a 3-day trip" not in blob
    assert "[redacted]" in blob
    assert stats["meta"]["redacted"] is True
    # counts still computed
    assert stats["totals"]["messages"] == 14


def test_rate_matching():
    rates = load_rates()
    assert rate_for("gpt-4o-mini-2024-07-18", rates)[0] == "gpt-4o-mini"
    assert rate_for("gpt-4o", rates)[0] == "gpt-4o"
    assert rate_for("claude-sonnet-4-20250514", rates)[0] == "claude-sonnet-4"
    assert rate_for(None, rates)[0] == "default"
    assert rate_for("some-unknown-model", rates)[0] == "default"


def test_golden_stats(merged_dataset, fixed_now):
    stats = compute_stats(merged_dataset, year=2026, rates=load_rates(), redact=False, now=fixed_now)
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        pytest.skip("golden updated")
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert stats == expected
