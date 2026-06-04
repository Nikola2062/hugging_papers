"""JSON-backed dedup store. Tracks arXiv IDs already pushed to Telegram."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

STATE_FILE = Path(__file__).resolve().parent.parent / "state" / "sent_papers.json"


def _load() -> dict:
    if not STATE_FILE.exists():
        return {"sent": []}
    with STATE_FILE.open() as f:
        return json.load(f)


def _save(data: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    with tmp.open("w") as f:
        json.dump(data, f, indent=2)
    tmp.replace(STATE_FILE)


def sent_ids() -> set[str]:
    return {entry["arxiv_id"] for entry in _load()["sent"]}


def is_sent(arxiv_id: str) -> bool:
    return arxiv_id in sent_ids()


def mark_sent(
    arxiv_id: str,
    title: str,
    *,
    upvotes: int = 0,
    arxiv_url: str = "",
    hf_url: str = "",
    short_intro: str = "",
) -> None:
    data = _load()
    data["sent"].append(
        {
            "arxiv_id": arxiv_id,
            "title": title,
            "upvotes": upvotes,
            "arxiv_url": arxiv_url,
            "hf_url": hf_url,
            "short_intro": short_intro,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _save(data)


def recent(days: int = 7) -> list[dict[str, Any]]:
    """Return entries sent within the last `days` days, newest first."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out: list[dict[str, Any]] = []
    for entry in _load()["sent"]:
        ts = entry.get("sent_at")
        if not ts:
            continue
        try:
            when = datetime.fromisoformat(ts)
        except ValueError:
            continue
        if when >= cutoff:
            out.append(entry)
    out.sort(key=lambda e: e.get("sent_at", ""), reverse=True)
    return out
