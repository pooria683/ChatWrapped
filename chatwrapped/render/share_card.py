"""1080x1920 SVG share card generator (pure string building, no deps)."""

from __future__ import annotations

from xml.sax.saxutils import escape

W, H = 1080, 1920

PLATFORM_COLORS = {
    "chatgpt": "#10a37f",
    "claude": "#d97757",
    "gemini": "#4285f4",
}


def _num(n) -> str:
    return f"{n:,}"


def build_share_card_svg(stats: dict, year: int | str | None = None) -> str:
    t = stats["totals"]
    a = stats["activity"]
    topics = [x["term"] for x in stats.get("topics", {}).get("overall", [])][:6]
    platforms = stats["meta"].get("platforms", {})
    year_label = str(year or (stats["meta"].get("years_present") or [""])[-1] or "all time")
    busiest = a.get("busiest_day") or {}
    night = a.get("latest_night") or {}
    models = list(stats.get("models", {}).items())[:3]

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif">'
    )
    # background
    parts.append(
        f'<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="#0b0f1a"/><stop offset="0.55" stop-color="#131a2e"/>'
        f'<stop offset="1" stop-color="#2a1240"/></linearGradient>'
        f'<linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="#a855f7"/><stop offset="1" stop-color="#ec4899"/></linearGradient></defs>'
    )
    parts.append(f'<rect width="{W}" height="{H}" fill="url(#bg)"/>')
    for i, (cx, cy, r, op) in enumerate([(900, 200, 420, 0.16), (140, 1500, 380, 0.12), (960, 1650, 260, 0.18)]):
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#accent)" opacity="{op}"/>')

    x = 90
    y = 150
    parts.append(f'<text x="{x}" y="{y}" fill="#a78bfa" font-size="34" font-weight="700" letter-spacing="6">CHATWRAPPED</text>')
    y += 150
    parts.append(f'<text x="{x}" y="{y}" fill="#ffffff" font-size="150" font-weight="800">{escape(year_label)}</text>')
    y += 70
    parts.append(f'<text x="{x}" y="{y}" fill="#94a3b8" font-size="40">your AI year in review</text>')

    # hero number
    y += 190
    parts.append(f'<text x="{x}" y="{y}" fill="#ffffff" font-size="190" font-weight="800">{_num(t["messages"])}</text>')
    y += 62
    parts.append(f'<text x="{x}" y="{y}" fill="#c4b5fd" font-size="44" font-weight="600">messages across {_num(t["conversations"])} conversations</text>')

    # stat grid
    y += 130
    cells = [
        (_num(t["words"]), "words written"),
        (_num(t["est_tokens"]), "est. tokens"),
        (f'${t["est_cost_usd"]:,.2f}', "est. cost*"),
        (str(a.get("active_days", 0)), "active days"),
    ]
    for i, (big, small) in enumerate(cells):
        cx = x + (i % 2) * 450
        cy = y + (i // 2) * 190
        parts.append(f'<text x="{cx}" y="{cy}" fill="#f0abfc" font-size="64" font-weight="800">{escape(big)}</text>')
        parts.append(f'<text x="{cx}" y="{cy + 48}" fill="#94a3b8" font-size="32">{escape(small)}</text>')
    y += 2 * 190 + 60

    # busiest day + night owl
    if busiest:
        parts.append(f'<text x="{x}" y="{y}" fill="#ffffff" font-size="36" font-weight="700">🔥 Busiest day: {escape(str(busiest.get("date")))} ({busiest.get("messages")} msgs)</text>')
        y += 66
    if night:
        parts.append(f'<text x="{x}" y="{y}" fill="#ffffff" font-size="36" font-weight="700">🌙 Latest night owl: {escape(str(night.get("time_human") or night.get("time")))}</text>')
        y += 90

    # topics
    if topics:
        parts.append(f'<text x="{x}" y="{y}" fill="#94a3b8" font-size="30" font-weight="700" letter-spacing="3">TOP TOPICS</text>')
        y += 64
        tx = x
        for term in topics:
            w = 34 + len(term) * 19
            if tx + w > W - 90:
                tx = x
                y += 66
            parts.append(f'<rect x="{tx}" y="{y - 34}" width="{w}" height="48" rx="24" fill="#ffffff" fill-opacity="0.10"/>')
            parts.append(f'<text x="{tx + 17}" y="{y}" fill="#e9d5ff" font-size="28" font-weight="600">{escape(term)}</text>')
            tx += w + 16
        y += 100

    # platform bars
    if platforms:
        total = sum(platforms.values()) or 1
        parts.append(f'<text x="{x}" y="{y}" fill="#94a3b8" font-size="30" font-weight="700" letter-spacing="3">PLATFORMS</text>')
        y += 56
        bx = x
        for name, count in sorted(platforms.items(), key=lambda kv: -kv[1]):
            w = max(24, int((W - 180) * count / total))
            color = PLATFORM_COLORS.get(name, "#64748b")
            parts.append(f'<rect x="{bx}" y="{y - 36}" width="{w}" height="52" rx="10" fill="{color}"/>')
            parts.append(f'<text x="{bx + w + 14}" y="{y}" fill="#e2e8f0" font-size="28" font-weight="600">{escape(name)} · {count}</text>')
            bx = 0
            y += 72
        y += 20

    # models
    if models:
        parts.append(f'<text x="{x}" y="{y}" fill="#94a3b8" font-size="30" font-weight="700" letter-spacing="3">TOP MODELS</text>')
        y += 58
        for name, m in models:
            parts.append(f'<text x="{x}" y="{y}" fill="#e2e8f0" font-size="32" font-weight="600">{escape(name)} — {_num(m["messages"])} msgs</text>')
            y += 52

    # footer
    fy = H - 110
    parts.append(f'<line x1="{x}" y1="{fy - 40}" x2="{W - 90}" y2="{fy - 40}" stroke="#ffffff" stroke-opacity="0.15"/>')
    parts.append(f'<text x="{x}" y="{fy}" fill="#94a3b8" font-size="30">100% local · zero network calls · nothing left your machine</text>')
    parts.append(f'<text x="{x}" y="{fy + 46}" fill="#64748b" font-size="26">*cost is an estimate · made with ChatWrapped</text>')
    parts.append("</svg>")
    return "".join(parts)
