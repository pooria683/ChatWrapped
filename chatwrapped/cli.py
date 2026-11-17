"""ChatWrapped CLI — argparse entry point.

Commands:
  chatwrapped scan <paths...>                 inspect + validate exports
  chatwrapped build <paths...> -o wrapped/    generate the full report
  chatwrapped config [set rate MODEL IN OUT | set year YEAR | path | edit]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

from . import PRIVACY_NOTE, __version__
from .merge import detect_year, filter_year, merge
from .parsers import PARSERS, detect_path, parse_paths
from .stats import compute_stats, load_rates


def _config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "chatwrapped"


def _config_path() -> Path:
    return _config_dir() / "config.json"


def load_user_config() -> dict:
    p = _config_path()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def save_user_config(cfg: dict) -> Path:
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def effective_rates() -> dict:
    cfg = load_user_config()
    return load_rates(overrides=cfg.get("rates"))


def _print_warnings(warnings, file=sys.stderr) -> None:
    for w in warnings:
        print(f"  ⚠ {w.source}: {w.message}", file=file)


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------

def cmd_scan(args) -> int:
    paths = [Path(p).expanduser() for p in args.paths]
    found_any = False
    report = {"paths": [], "totals": {"conversations": 0, "messages": 0}}
    for p in paths:
        entry = {"path": str(p), "exists": p.exists(), "formats": [], "conversations": 0, "messages": 0, "warnings": []}
        if not p.exists():
            entry["warnings"].append("path not found")
            report["paths"].append(entry)
            print(f"✗ {p} — not found")
            continue
        names = detect_path(p)
        entry["formats"] = names
        if names:
            result = parse_paths([p])
            entry["conversations"] = len(result.conversations)
            entry["messages"] = result.message_count
            entry["warnings"] = [f"{w.source}: {w.message}" for w in result.warnings]
            report["totals"]["conversations"] += len(result.conversations)
            report["totals"]["messages"] += result.message_count
            found_any = True
            platforms = {}
            for c in result.conversations:
                platforms[c.platform] = platforms.get(c.platform, 0) + 1
            plat = ", ".join(f"{k}: {v} convs" for k, v in sorted(platforms.items()))
            print(f"✓ {p}")
            print(f"    detected: {', '.join(names)}")
            print(f"    {entry['conversations']} conversations, {entry['messages']} messages ({plat})")
            _print_warnings(result.warnings)
        else:
            entry["warnings"].append("no known export format recognized")
            print(f"? {p} — no known export format recognized")
        report["paths"].append(entry)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"\nTotal: {report['totals']['conversations']} conversations, {report['totals']['messages']} messages")
        if found_any:
            print(PRIVACY_NOTE)
    return 0 if found_any else 1


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def cmd_build(args) -> int:
    paths = [Path(p).expanduser() for p in args.paths]
    result = parse_paths(paths)
    if not result.conversations:
        print("✗ No conversations found in the given path(s). Run `chatwrapped scan <paths...>` to check what was detected.", file=sys.stderr)
        _print_warnings(result.warnings, file=sys.stderr)
        return 1

    ds = merge(result)
    if len(result.conversations) != len(ds.conversations):
        dupes = len(result.conversations) - len(ds.conversations)
        print(f"  merged {len(result.conversations)} raw conversations → {len(ds.conversations)} unique ({dupes} duplicate(s) removed)")

    cfg = load_user_config()
    year = args.year or cfg.get("default_year")
    if year is not None:
        ds = filter_year(ds, int(year))
        if not ds.conversations:
            print(f"✗ No conversations found for year {year}.", file=sys.stderr)
            return 1
    else:
        year = detect_year(ds)

    rates = effective_rates()
    stats = compute_stats(ds, year=year, rates=rates, redact=args.redact)

    out_dir = Path(args.output).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    from .render import build_share_card_svg, render_html, render_terminal

    share_svg = build_share_card_svg(stats, year)
    html = render_html(stats, share_svg=share_svg)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    (out_dir / "share-card.svg").write_text(share_svg, encoding="utf-8")
    (out_dir / "stats.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(stats, ensure_ascii=False))
    else:
        print(render_terminal(stats, use_color=args.color))
        print(f"  Wrote: {out_dir / 'index.html'}")
        print(f"         {out_dir / 'share-card.svg'}")
        print(f"         {out_dir / 'stats.json'}")
        if args.redact:
            print("  🔴 --redact: message excerpts are masked in all outputs.")
        print("  " + PRIVACY_NOTE)
    _print_warnings(ds.warnings, file=sys.stderr)

    if args.open:
        webbrowser.open((out_dir / "index.html").resolve().as_uri())
    return 0


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

def cmd_config(args) -> int:
    cfg = load_user_config()
    p = _config_path()
    action = args.action or []

    if not action:
        rates = effective_rates()
        print(f"config file: {p}")
        print(f"default year: {cfg.get('default_year', '(latest year in data)')}")
        print("rates (USD per 1M tokens, longest-slug match wins; 'default' = fallback):")
        for k in sorted(rates):
            v = rates[k]
            print(f"  {k:<24} in ${v['input_per_mtok']:<8} out ${v['output_per_mtok']}")
        print("\ncommands:")
        print("  chatwrapped config path                          show config file path")
        print("  chatwrapped config edit                          open config in $EDITOR")
        print("  chatwrapped config set rate MODEL IN OUT         set a model's $/1M tokens")
        print("  chatwrapped config set year 2026                 default --year for build")
        return 0

    if action[0] == "path":
        print(p)
        return 0
    if action[0] == "edit":
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            save_user_config(cfg)
        editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vi"
        try:
            return subprocess.call([editor, str(p)])
        except FileNotFoundError:
            print(f"no editor found (EDITOR={editor!r}); config file is at {p}", file=sys.stderr)
            return 1
    if action[0] == "set" and len(action) >= 2:
        kind = action[1]
        if kind == "rate" and len(action) == 5:
            model, rin, rout = action[2], float(action[3]), float(action[4])
            cfg.setdefault("rates", {})[model] = {"input_per_mtok": rin, "output_per_mtok": rout}
            saved = save_user_config(cfg)
            print(f"✓ rate for '{model}' set to in ${rin}/1M, out ${rout}/1M → {saved}")
            return 0
        if kind == "year" and len(action) == 3:
            try:
                y = int(action[2])
            except ValueError:
                print("year must be an integer, e.g. 2026", file=sys.stderr)
                return 2
            cfg["default_year"] = y
            saved = save_user_config(cfg)
            print(f"✓ default year set to {y} → {saved}")
            return 0
        print("usage: chatwrapped config set rate MODEL INPUT_PER_MTOK OUTPUT_PER_MTOK\n"
              "       chatwrapped config set year YEAR", file=sys.stderr)
        return 2
    print("unknown config action. Try: path | edit | set rate ... | set year ...", file=sys.stderr)
    return 2


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="chatwrapped",
        description="ChatWrapped — Spotify Wrapped for your AI chats. Reads official data exports 100% locally (zero network calls).",
    )
    ap.add_argument("--version", action="version", version=f"chatwrapped {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="inspect + validate export files")
    scan.add_argument("paths", nargs="+", help="export files/dirs (zips, conversations.json, Takeout folder…)")
    scan.add_argument("--json", action="store_true", help="machine-readable output")
    scan.set_defaults(func=cmd_scan)

    build = sub.add_parser("build", help="generate terminal summary + HTML story + JSON stats")
    build.add_argument("paths", nargs="+", help="export files/dirs")
    build.add_argument("-o", "--output", default="wrapped", help="output directory (default: ./wrapped)")
    build.add_argument("--year", type=int, default=None, help="restrict to one year, e.g. --year 2026")
    build.add_argument("--json", action="store_true", help="print full stats JSON to stdout")
    build.add_argument("--redact", action="store_true", help="mask message excerpts in all outputs")
    build.add_argument("--open", action="store_true", help="open the HTML report in your default browser")
    build.add_argument("--color", action="store_true", help="force colored terminal output")
    build.add_argument("--no-color", dest="color", action="store_false", help="disable colored terminal output")
    build.set_defaults(func=cmd_build, color=None)

    cfg = sub.add_parser("config", help="show or edit rates / default year")
    cfg.add_argument("action", nargs="*", help="path | edit | set rate MODEL IN OUT | set year YEAR")
    cfg.set_defaults(func=cmd_config)

    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
