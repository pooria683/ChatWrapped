"""CLI smoke tests via subprocess."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import helpers  # noqa: E402


def run_cli(args, env_extra=None, cwd=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "chatwrapped", *args],
        capture_output=True, text=True, cwd=cwd or ROOT, env=env, timeout=120,
    )


@pytest.fixture
def export_dir(tmp_path):
    return helpers.make_all_exports(tmp_path / "exports")


def test_version():
    r = run_cli(["--version"])
    assert r.returncode == 0 and "chatwrapped" in r.stdout


def test_scan_ok(export_dir):
    r = run_cli(["scan", *[str(p) for p in export_dir]])
    assert r.returncode == 0
    assert "detected:" in r.stdout
    assert "6 conversations, 14 messages" in r.stdout
    assert "zero network calls" in r.stdout


def test_scan_json(export_dir):
    r = run_cli(["scan", *[str(p) for p in export_dir], "--json"])
    assert r.returncode == 0
    data = json.loads(r.stdout[r.stdout.index("{"):])
    assert data["totals"] == {"conversations": 6, "messages": 14}


def test_scan_garbage(tmp_path):
    bad = tmp_path / "junk.bin"
    bad.write_bytes(b"\x00\xff garbage")
    r = run_cli(["scan", str(bad)])
    assert r.returncode == 1
    assert "no known export format" in r.stdout


def test_build_outputs(export_dir, tmp_path):
    out = tmp_path / "wrapped"
    r = run_cli(["build", *[str(p) for p in export_dir], "-o", str(out)])
    assert r.returncode == 0, r.stderr
    for name in ("index.html", "stats.json", "share-card.svg"):
        assert (out / name).exists(), name
    stats = json.loads((out / "stats.json").read_text())
    assert stats["totals"]["messages"] == 14
    assert stats["meta"]["year"] == 2026
    html = (out / "index.html").read_text()
    assert "ChatWrapped" in html and "share-svg-source" in html
    svg = (out / "share-card.svg").read_text()
    assert 'width="1080"' in svg
    assert "nothing left your device" in r.stdout or "zero network calls" in r.stdout


def test_build_json_flag(export_dir, tmp_path):
    r = run_cli(["build", *[str(p) for p in export_dir], "-o", str(tmp_path / "w"), "--json", "--no-color"])
    assert r.returncode == 0, r.stderr
    stats = json.loads(r.stdout)
    assert stats["totals"]["conversations"] == 6


def test_build_redact(export_dir, tmp_path):
    out = tmp_path / "w"
    r = run_cli(["build", *[str(p) for p in export_dir], "-o", str(out), "--redact"])
    assert r.returncode == 0
    html = (out / "index.html").read_text()
    assert "Plan a 3-day trip" not in html
    assert "[redacted]" in html
    stats = json.loads((out / "stats.json").read_text())
    assert "Plan a 3-day trip" not in json.dumps(stats)


def test_build_year_filter(export_dir, tmp_path):
    r = run_cli(["build", *[str(p) for p in export_dir], "-o", str(tmp_path / "w"), "--year", "2026"])
    assert r.returncode == 0
    r = run_cli(["build", *[str(p) for p in export_dir], "-o", str(tmp_path / "w2"), "--year", "2025"])
    assert r.returncode == 1
    assert "2025" in r.stderr


def test_build_no_inputs(tmp_path):
    r = run_cli(["build", str(tmp_path)])
    assert r.returncode == 1


def test_config_roundtrip(tmp_path):
    env = {"XDG_CONFIG_HOME": str(tmp_path / "cfg")}
    r = run_cli(["config", "set", "rate", "my-model", "1.5", "4.0"], env_extra=env)
    assert r.returncode == 0
    r = run_cli(["config", "set", "year", "2026"], env_extra=env)
    assert r.returncode == 0
    r = run_cli(["config"], env_extra=env)
    assert r.returncode == 0
    assert "my-model" in r.stdout and "2026" in r.stdout
    cfg_file = tmp_path / "cfg" / "chatwrapped" / "config.json"
    data = json.loads(cfg_file.read_text())
    assert data["rates"]["my-model"] == {"input_per_mtok": 1.5, "output_per_mtok": 4.0}
    assert data["default_year"] == 2026
    r = run_cli(["config", "path"], env_extra=env)
    assert str(cfg_file) in r.stdout


def test_config_bad_usage(tmp_path):
    r = run_cli(["config", "set", "rate", "only-model"], env_extra={"XDG_CONFIG_HOME": str(tmp_path)})
    assert r.returncode == 2
