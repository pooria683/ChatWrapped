#!/usr/bin/env python3
"""Generate a rich, deterministic synthetic export set for demos/tests.

Creates ``demo/exports/`` containing a fake but realistic year (2026) of
ChatGPT (legacy + nested-zip), Claude and Gemini Takeout exports, seeded so
every run produces identical data. No real user data involved.

Usage:  python examples/make_demo.py [outdir]   (default: demo/exports)
"""

from __future__ import annotations

import io
import json
import random
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOPICS = [
    ("Kyoto travel planning", ["Plan a 5-day Kyoto itinerary in April with temples",
                                "Best ramen spots near Nishiki market?",
                                "How much does the JR pass cost for a week?"]),
    ("Python async debugging", ["Why does my asyncio gather hang on the second run?",
                                 "Explain connection pool exhaustion in aiohttp",
                                 "Write a retry decorator with exponential backoff"]),
    ("Sourdough baking", ["My sourdough starter smells like acetone, is it dead?",
                          "Hydration ratio for a 75% whole wheat loaf?",
                          "How long to bulk ferment at 24C?"]),
    ("Half marathon training", ["Build a 12 week half marathon plan for a 2h goal",
                                 "Shin splints week 6 — keep running or rest?",
                                 "Best carb loading strategy the day before?"]),
    ("Portuguese learning", ["Explain the difference between ser and estar",
                              "Common false friends between English and Portuguese",
                              "How to order coffee like a local in Lisbon?"]),
    ("Mechanical keyboards", ["Linear vs tactile switches for typing?",
                              "Is a 65% layout good for programming?",
                              "Best budget keycap sets under 50 euros?"]),
]

MODELS_GPT = ["gpt-4o", "gpt-4o-mini", "gpt-5", "o3"]
MODELS_CLAUDE = ["claude-sonnet-4-20250514", "claude-haiku-4-20250514"]


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000Z")


def epoch(dt: datetime) -> float:
    return dt.timestamp()


def make_chatgpt_conversations(rng: random.Random) -> list[dict]:
    convs = []
    start = datetime(2026, 1, 3, 9, 0, tzinfo=timezone.utc)
    for i in range(60):
        title, prompts = TOPICS[i % len(TOPICS)]
        created = start + timedelta(days=rng.randint(0, 360), hours=rng.randint(0, 20))
        mapping = {}
        node = "root"
        mapping[node] = {"id": node, "message": None, "parent": None, "children": [], "create_time": epoch(created)}
        n_msgs = rng.randint(2, 6)
        parent = node
        for j in range(n_msgs):
            role = "user" if j % 2 == 0 else "assistant"
            nid = f"n{i}-{j}"
            if role == "user":
                text = prompts[rng.randint(0, len(prompts) - 1)]
                if rng.random() < 0.25 and j > 0:  # an edited prompt -> branch
                    mapping[parent]["children"].append(nid)
                    mapping[nid] = {
                        "id": nid,
                        "message": {"id": f"m{i}-{j}", "author": {"role": "user"},
                                    "content": {"content_type": "text", "parts": [text + " (rephrased)"]},
                                    "create_time": epoch(created + timedelta(minutes=j * 4 + 1))},
                        "parent": parent, "children": [],
                    }
                    parent = nid
                    continue
                text = text
            else:
                model = rng.choice(MODELS_GPT)
                text = (f"Great question about {title.lower()} — here is a detailed answer with steps, "
                        f"examples and edge cases. TL;DR: start small, measure, iterate.")
            msg = {"id": f"m{i}-{j}", "author": {"role": role},
                   "content": {"content_type": "text", "parts": [text]},
                   "create_time": epoch(created + timedelta(minutes=j * 4))}
            if role == "assistant":
                msg["metadata"] = {"model_slug": rng.choice(MODELS_GPT)}
            mapping[parent]["children"].append(nid)
            mapping[nid] = {"id": nid, "message": msg, "parent": parent, "children": []}
            parent = nid
        # sprinkle a system message (should be skipped)
        sid = f"n{i}-sys"
        mapping["root"]["children"].append(sid)
        mapping[sid] = {"id": sid, "message": {"id": f"m{i}-sys", "author": {"role": "system"},
                                                "content": {"content_type": "text", "parts": ["system prompt"]},
                                                "create_time": epoch(created)}, "parent": "root", "children": []}
        convs.append({"title": f"{title} #{i}", "create_time": epoch(created),
                      "update_time": epoch(created + timedelta(hours=2)),
                      "mapping": mapping, "id": f"gpt-conv-{i}"})
    # one very late-night conversation
    night = datetime(2026, 11, 14, 3, 47, tzinfo=timezone.utc)
    convs.append({
        "title": "3 AM thoughts", "create_time": epoch(night), "update_time": epoch(night + timedelta(minutes=9)),
        "id": "gpt-conv-night",
        "mapping": {
            "r": {"id": "r", "message": None, "parent": None, "children": ["u"], "create_time": epoch(night)},
            "u": {"id": "u", "parent": "r", "children": ["a"], "message": {
                "id": "mu", "author": {"role": "user"},
                "content": {"content_type": "text", "parts": ["What should I learn next at 3:47 AM?"]},
                "create_time": epoch(night)}},
            "a": {"id": "a", "parent": "u", "children": [], "message": {
                "id": "ma", "author": {"role": "assistant"},
                "content": {"content_type": "text", "parts": ["Sleep. But also: rust or zig are fun."]},
                "create_time": epoch(night + timedelta(minutes=2)),
                "metadata": {"model_slug": "gpt-4o"}}},
        },
    })
    return convs


def make_claude_conversations(rng: random.Random) -> list[dict]:
    convs = []
    start = datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc)
    for i in range(35):
        title, prompts = TOPICS[(i + 2) % len(TOPICS)]
        created = start + timedelta(days=rng.randint(0, 330), hours=rng.randint(0, 10))
        msgs = []
        for j in range(rng.randint(2, 5)):
            sender = "human" if j % 2 == 0 else "assistant"
            text = prompts[rng.randint(0, len(prompts) - 1)] if sender == "human" else \
                f"Here is a thoughtful take on {title.lower()}: consider context, constraints and trade-offs."
            msgs.append({"uuid": f"cm-{i}-{j}", "text": text, "sender": sender,
                         "created_at": iso(created + timedelta(minutes=j * 6)),
                         "updated_at": iso(created + timedelta(minutes=j * 6))})
        convs.append({"uuid": f"claude-conv-{i}", "name": f"{title} #{i}",
                      "created_at": iso(created), "updated_at": iso(created + timedelta(hours=1)),
                      "chat_messages": msgs})
    return convs


def make_gemini_conversations(rng: random.Random) -> list[dict]:
    convs = []
    start = datetime(2026, 5, 5, 8, 0, tzinfo=timezone.utc)
    for i in range(15):
        title, prompts = TOPICS[(i + 4) % len(TOPICS)]
        created = start + timedelta(days=rng.randint(0, 200))
        convs.append({
            "id": f"gemini-conv-{i}", "title": f"{title} #{i}", "created_at": iso(created),
            "messages": [
                {"role": "user", "parts": [{"text": prompts[rng.randint(0, len(prompts) - 1)]}],
                 "created_at": iso(created)},
                {"role": "model", "parts": [{"text": f"On {title.lower()}: practical advice follows."}],
                 "created_at": iso(created + timedelta(minutes=1)), "model": "gemini-2.5-flash"},
            ],
        })
    return convs


def zip_bytes(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def main() -> None:
    outdir = Path(sys.argv[1] if len(sys.argv) > 1 else "demo/exports")
    outdir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(20261116)

    gpt = make_chatgpt_conversations(rng)
    (outdir / "conversations.json").write_text(json.dumps(gpt), encoding="utf-8")

    # nested-zip style export with a subset (overlapping export -> dedupe demo)
    subset = gpt[:10] + gpt[-1:]
    inner = zip_bytes({"conversations.json": json.dumps(subset).encode()})
    (outdir / "chatgpt-online-activity.zip").write_bytes(zip_bytes({
        "User Online Activity/Conversations__demo1-chatgpt-0001.zip": inner,
        "User Online Activity/Conversations__demo2-chatgpt-0002.zip": zip_bytes({
            "conversations.json": json.dumps(gpt[10:20]).encode()}),
    }))

    claude = make_claude_conversations(rng)
    (outdir / "claude-export.zip").write_bytes(zip_bytes({
        "conversations-000.zip": zip_bytes({"conversations.json": json.dumps(claude).encode()}),
        "projects-000.zip": zip_bytes({"projects.json": json.dumps([
            {"uuid": "p1", "name": "Wrapped ideas", "prompts": ["brainstorm names"]}]).encode()}),
        "memories.json": json.dumps([{"text": "User likes dark mode."}]).encode(),
    }))

    gemini = make_gemini_conversations(rng)
    gem_dir = outdir / "Takeout" / "Gemini Apps" / "exports"
    gem_dir.mkdir(parents=True, exist_ok=True)
    (gem_dir / "chats.json").write_text(json.dumps(gemini), encoding="utf-8")

    total_msgs = sum(len(c.get("mapping", {})) for c in gpt) + sum(len(c["chat_messages"]) for c in claude) \
        + sum(len(c["messages"]) for c in gemini)
    print(f"demo exports written to {outdir}/ "
          f"({len(gpt)} chatgpt convs, {len(claude)} claude convs, {len(gemini)} gemini convs)")


if __name__ == "__main__":
    main()
