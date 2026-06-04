"""Fetch trending papers from Hugging Face's daily papers feed.

Strategy: pull today's list. If after dedup we have fewer than `want` papers,
walk back day-by-day up to 14 days and merge results. Sort merged candidates
by upvotes (descending) so the most-loved unseen paper wins.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

import requests

from .state import is_sent

API = "https://huggingface.co/api/daily_papers"
FALLBACK_DAYS = 14
TIMEOUT = 20

log = logging.getLogger(__name__)


@dataclass
class Paper:
    arxiv_id: str
    title: str
    abstract: str
    authors: list[str]
    upvotes: int
    published_at: str
    hf_url: str
    arxiv_url: str


def _parse(entry: dict) -> Paper | None:
    paper = entry.get("paper") or {}
    arxiv_id = paper.get("id") or entry.get("id")
    if not arxiv_id:
        return None
    return Paper(
        arxiv_id=arxiv_id,
        title=paper.get("title") or entry.get("title", ""),
        abstract=paper.get("summary") or entry.get("summary", ""),
        authors=[a.get("name", "") for a in paper.get("authors", []) if a.get("name")],
        upvotes=int(paper.get("upvotes") or 0),
        published_at=paper.get("publishedAt") or entry.get("publishedAt", ""),
        hf_url=f"https://huggingface.co/papers/{arxiv_id}",
        arxiv_url=f"https://arxiv.org/abs/{arxiv_id}",
    )


def _fetch_day(day: date | None = None) -> list[Paper]:
    params = {"date": day.isoformat()} if day else {}
    try:
        r = requests.get(API, params=params, timeout=TIMEOUT)
        r.raise_for_status()
    except requests.RequestException as e:
        log.warning("fetch failed for %s: %s", day or "today", e)
        return []
    papers = [p for p in (_parse(e) for e in r.json()) if p is not None]
    log.info("fetched %d papers for %s", len(papers), day or "today")
    return papers


def _dedup_keep_order(papers: Iterable[Paper]) -> list[Paper]:
    seen: set[str] = set()
    out: list[Paper] = []
    for p in papers:
        if p.arxiv_id in seen:
            continue
        seen.add(p.arxiv_id)
        out.append(p)
    return out


def fetch_fresh(want: int = 3, min_upvotes: int = 0) -> list[Paper]:
    """Return up to `want` unseen papers with `upvotes >= min_upvotes`, ranked by upvotes."""

    def _qualifying(papers: list[Paper]) -> list[Paper]:
        return [p for p in papers if not is_sent(p.arxiv_id) and p.upvotes >= min_upvotes]

    candidates: list[Paper] = _fetch_day()
    fresh = _qualifying(candidates)

    if len(fresh) >= want:
        fresh.sort(key=lambda p: p.upvotes, reverse=True)
        return fresh[:want]

    # Walk backwards to fill the quota.
    today = date.today()
    for offset in range(1, FALLBACK_DAYS + 1):
        more = _fetch_day(today - timedelta(days=offset))
        candidates = _dedup_keep_order(candidates + more)
        fresh = _qualifying(candidates)
        if len(fresh) >= want:
            break

    fresh.sort(key=lambda p: p.upvotes, reverse=True)
    return fresh[:want]
