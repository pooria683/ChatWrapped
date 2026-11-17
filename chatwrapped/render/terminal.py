"""Compact colored terminal summary (ANSI, no dependencies)."""

from __future__ import annotations

import os
import sys


class _C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    MAGENTA = "\033[35m"
    YELLOW = "\033[33m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    BLUE = "\033[34m"


def _color_enabled(use_color: bool | None) -> bool:
    if use_color is not None:
        return use_color
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _fmt(n: int | float) -> str:
    if isinstance(n, float):
        return f"{n:,.2f}"
    return f"{n:,}"


def render_terminal(stats: dict, use_color: bool | None = None) -> str:
    c = _C()
    on = _color_enabled(use_color)

    def paint(code: str, s: str) -> str:
        return f"{code}{s}{c.RESET}" if on else s

    year = stats["meta"].get("year")
    title_year = f" {year}" if year else ""
    L: list[str] = []
    L.append("")
    L.append(paint(c.BOLD + c.MAGENTA, "  ✦ ChatWrapped" + (f" — your AI year in review{title_year}" if True else "")))
    L.append(paint(c.DIM, "  ─────────────────────────────────────────────"))
    t = stats["totals"]
    rows = [
        ("Conversations", _fmt(t["conversations"])),
        ("Messages", f"{_fmt(t['messages'])}  ({_fmt(t['user_messages'])} you / {_fmt(t['assistant_messages'])} AI)"),
        ("Words", _fmt(t["words"])),
        ("Est. tokens", f"{_fmt(t['est_tokens'])}  (chars/4)"),
        ("Est. cost", f"${t['est_cost_usd']:,.2f}  (estimate only)"),
    ]
    for label, value in rows:
        L.append(f"  {paint(c.CYAN, f'{label:<16}')} {paint(c.BOLD, value)}")

    a = stats["activity"]
    L.append("")
    L.append(paint(c.BOLD + c.YELLOW, "  Activity"))
    if a.get("busiest_day"):
        L.append(f"  Busiest day        {paint(c.BOLD, a['busiest_day']['date'])} ({a['busiest_day']['messages']} messages)")
    L.append(f"  Active days        {_fmt(a['active_days'])}  (avg {a['avg_messages_per_active_day']} msgs/active day)")
    ln = a.get("latest_night")
    if ln:
        L.append(f"  Latest night msg   {paint(c.BOLD, ln['time_human'])} on {ln['date']}")
    months = a.get("per_month", {})
    if months:
        busiest_month = max(months.items(), key=lambda kv: kv[1])
        L.append(f"  Busiest month      {busiest_month[0]} ({busiest_month[1]} messages)")

    topics = stats.get("topics", {}).get("overall", [])[:10]
    if topics:
        L.append("")
        L.append(paint(c.BOLD + c.YELLOW, "  Top topics"))
        L.append("  " + paint(c.GREEN, "  ·  ".join(x["term"] for x in topics)))

    ms = stats.get("milestones", {})
    L.append("")
    L.append(paint(c.BOLD + c.YELLOW, "  Milestones"))
    fc = ms.get("first_conversation")
    if fc:
        prompt = f" — “{fc['first_prompt']}”" if fc.get("first_prompt") else ""
        L.append(f"  First conversation {fc['date']} ({fc.get('platform')}){prompt}")
    lc = ms.get("longest_conversation")
    if lc:
        name = lc.get("title") or "untitled"
        L.append(f"  Longest chat       “{name}” — {lc['messages']} messages, {_fmt(lc['words'])} words")
    me = ms.get("most_edited_prompt")
    if me:
        L.append(f"  Most-edited prompt {me['versions']} versions — “{me['prompt']}”")

    models = stats.get("models", {})
    if len(models) > 1 or (models and "unknown" not in models):
        L.append("")
        L.append(paint(c.BOLD + c.YELLOW, "  Models"))
        for name, m in list(models.items())[:8]:
            L.append(f"  {paint(c.BLUE, f'{name:<28}')} {_fmt(m['messages']):>7} msgs  ${m['est_cost_usd']:>8,.2f}")

    plats = stats["meta"].get("platforms", {})
    if plats:
        L.append("")
        L.append(paint(c.DIM, "  Platforms: " + ", ".join(f"{k} ({v})" for k, v in sorted(plats.items()))))
    L.append("")
    return "\n".join(L)
