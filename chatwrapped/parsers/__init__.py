"""Parser registry: content-based auto-detection across platforms."""

from __future__ import annotations

from pathlib import Path

from .base import ParseResult, ParseWarning
from .chatgpt import ChatGPTParser
from .claude import ClaudeParser
from .gemini import GeminiParser

PARSERS = [ChatGPTParser(), ClaudeParser(), GeminiParser()]


def detect_path(path: Path) -> list[str]:
    """Return names of parsers whose content sniff matches ``path``."""
    names = []
    for parser in PARSERS:
        try:
            if parser.detect(path):
                names.append(parser.name)
        except Exception:  # noqa: BLE001 - detection must never crash
            continue
    return names


def parse_paths(paths, warnings: list[ParseWarning] | None = None) -> ParseResult:
    """Parse every path with every parser that recognizes it.

    Never raises on malformed input; problems are collected as warnings.
    """
    result = ParseResult()
    for raw in paths:
        path = Path(raw).expanduser()
        if not path.exists():
            result.warnings.append(ParseWarning(str(raw), "path not found"))
            continue
        matched = False
        for parser in PARSERS:
            try:
                if parser.detect(path):
                    matched = True
                    sub = parser.parse(path)
                    result.conversations.extend(sub.conversations)
                    result.warnings.extend(sub.warnings)
            except Exception as exc:  # noqa: BLE001 - last-resort guard
                result.warnings.append(ParseWarning(str(path), f"{parser.name}: {exc.__class__.__name__}"))
        if not matched:
            result.warnings.append(ParseWarning(str(path), "no known export format recognized"))
    if warnings is not None:
        warnings.extend(result.warnings)
    return result


__all__ = ["PARSERS", "detect_path", "parse_paths", "ParseResult", "ParseWarning"]
