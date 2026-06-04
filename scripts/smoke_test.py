"""Offline smoke test: fetch papers, exercise state, format a Telegram message.

Does NOT call DeepSeek and does NOT send to Telegram. Run this before you
plug in credentials to confirm the wiring is good.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.fetcher import fetch_fresh
from src.summarizer import Summary
from src.telegram_sender import format_message


def main() -> int:
    papers = fetch_fresh(want=3)
    print(f"fetched {len(papers)} fresh papers")
    if not papers:
        print("nothing to test against — check network or HF API")
        return 1

    fake = Summary(
        short_intro="This is a placeholder short intro. Real summaries come from DeepSeek.",
        detailed_summary=(
            "- Bullet one about the method.\n"
            "- Bullet two about the dataset.\n"
            "- Bullet three about the headline result.\n"
            "- Bullet four about a limitation."
        ),
        professor_explanation=(
            "CONCERN: a fake one-paragraph explanation of why this matters.\n\n"
            "SOLUTION: a fake one-paragraph explanation of what they did.\n\n"
            "RESULT: a fake one-paragraph explanation of what they got."
        ),
    )

    for i, p in enumerate(papers, 1):
        print(f"\n--- paper {i}: {p.arxiv_id} ---")
        print(f"title: {p.title}")
        print(f"upvotes: {p.upvotes}")
        print(f"arxiv: {p.arxiv_url}")
        print(f"abstract length: {len(p.abstract)} chars")
        msg = format_message(p, fake)
        print(f"telegram message length: {len(msg)} chars")
        # show first 240 chars of the rendered message so we can eyeball escaping
        print("preview:")
        print(msg[:240] + ("..." if len(msg) > 240 else ""))

    return 0


if __name__ == "__main__":
    sys.exit(main())
