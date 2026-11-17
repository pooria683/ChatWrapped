"""Render tests: self-containment, template sync, share card, goldens."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from chatwrapped.render import build_share_card_svg, load_template, render_html, render_terminal
from chatwrapped.stats import compute_stats, load_rates

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_HTML = Path(__file__).parent / "golden" / "story_2026.html"


def _stats(merged_dataset, fixed_now, redact=False):
    return compute_stats(merged_dataset, year=2026, rates=load_rates(), redact=redact, now=fixed_now)


def test_template_in_sync():
    pkg = (ROOT / "chatwrapped" / "render" / "wrapped_template.html").read_text(encoding="utf-8")
    repo = (ROOT / "wrapped_template.html").read_text(encoding="utf-8")
    assert pkg == repo == load_template()


def test_html_self_contained(merged_dataset, fixed_now):
    stats = _stats(merged_dataset, fixed_now)
    svg = build_share_card_svg(stats, 2026)
    html = render_html(stats, share_svg=svg)
    # no external resources of any kind
    assert "<script src" not in html.lower()
    assert "<link" not in html.lower()
    assert "@import" not in html
    assert "url(http" not in html
    urls = re.findall(r"https?://[^\s\"'<>)]+", html)
    assert all(u.startswith("http://www.w3.org/") for u in urls), urls  # only xmlns namespaces
    # placeholders all substituted
    assert "$CW_" not in html
    # key markers present
    for marker in ["ChatWrapped", "share-svg-source", "dl-png", "heatmap", "CW" ]:
        if marker == "CW":
            continue
        assert marker in html
    assert '"messages": 14' in html or '"messages":14' in html


def test_html_redact(merged_dataset, fixed_now):
    stats = _stats(merged_dataset, fixed_now, redact=True)
    html = render_html(stats, share_svg=build_share_card_svg(stats, 2026))
    assert "Plan a 3-day trip" not in html
    assert "[redacted]" in html


def test_share_card_svg_shape(merged_dataset, fixed_now):
    stats = _stats(merged_dataset, fixed_now)
    svg = build_share_card_svg(stats, 2026)
    assert svg.startswith("<svg")
    assert 'width="1080"' in svg and 'height="1920"' in svg
    assert "2026" in svg
    assert "14" in svg  # message count


def test_share_card_escapes_text():
    stats = {
        "totals": {"conversations": 1, "messages": 2, "words": 10, "est_tokens": 3, "est_cost_usd": 0.01},
        "activity": {"busiest_day": {"date": "2026-01-01", "messages": 2}, "latest_night": {"time": "03:47", "time_human": "3:47 AM", "date": "2026-01-01"}, "active_days": 1},
        "topics": {"overall": [{"term": "<script>alert(1)</script>", "score": 1.0}]},
        "meta": {"platforms": {"chatgpt": 1}, "years_present": [2026]},
        "models": {},
    }
    svg = build_share_card_svg(stats, 2026)
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg


def test_terminal_render(merged_dataset, fixed_now):
    stats = _stats(merged_dataset, fixed_now)
    out = render_terminal(stats, use_color=False)
    assert "\033[" not in out
    assert "Conversations" in out and "6" in out
    assert "Messages" in out and "14" in out
    assert "03:47" in out or "3:47 AM" in out
    colored = render_terminal(stats, use_color=True)
    assert "\033[" in colored


def test_golden_html(merged_dataset, fixed_now):
    stats = _stats(merged_dataset, fixed_now)
    svg = build_share_card_svg(stats, 2026)
    html = render_html(stats, share_svg=svg, generated="2026-12-01T12:00:00+00:00")
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN_HTML.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_HTML.write_text(html, encoding="utf-8")
        pytest.skip("golden updated")
    assert html == GOLDEN_HTML.read_text(encoding="utf-8")
