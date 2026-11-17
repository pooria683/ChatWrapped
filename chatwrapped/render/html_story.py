"""Render the self-contained HTML "Wrapped" story page.

Uses ``string.Template`` placeholders so the tool runs with zero dependencies
(Jinja2 is an optional extra but not required). The template ships twice —
inside the package (used when installed) and at the repo root
(``wrapped_template.html``); a test keeps them byte-identical.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from string import Template


def load_template() -> str:
    """Load the story template: package data first, repo root as fallback."""
    try:
        from importlib.resources import files

        return (files("chatwrapped.render") / "wrapped_template.html").read_text(encoding="utf-8")
    except Exception:
        pass
    p = Path(__file__).resolve().parents[2] / "wrapped_template.html"
    return p.read_text(encoding="utf-8")


def _year_label(stats: dict) -> str:
    y = stats["meta"].get("year")
    if y:
        return str(y)
    years = stats["meta"].get("years_present") or []
    return str(years[-1]) if years else "all time"


def render_html(
    stats: dict,
    share_svg: str | None = None,
    template: str | None = None,
    generated: str | None = None,
) -> str:
    """Return the full self-contained HTML document as a string."""
    tpl = template if template is not None else load_template()
    share_svg = share_svg or ""
    data_json = json.dumps(stats, ensure_ascii=False).replace("</", "<\\/")
    year = _year_label(stats)
    subs = {
        "CW_TITLE": f"ChatWrapped {year} — your AI year in review",
        "CW_YEAR": year,
        "CW_GENERATED": generated or stats["meta"].get("generated_at", ""),
        "CW_DATA": data_json,
        "CW_SHARE_SVG": share_svg,
        "CW_REDACTED": "true" if stats["meta"].get("redacted") else "false",
    }
    return Template(tpl).safe_substitute(subs)


def default_generated_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
