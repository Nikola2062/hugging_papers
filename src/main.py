"""Orchestrator: fetch trending papers, summarize, deliver to Telegram, mark sent.

Usage:
    python -m src.main \
        --deepseek-api-key sk-xxx \
        --telegram-bot-token 1234:abc \
        --telegram-chat-id 12345,67890 \
        --telegram-send true \
        --min-upvotes 5 \
        --attach-pdf false \
        --mode digest

    # Disable Telegram delivery (prints summaries to stdout, skips state write):
    python -m src.main --deepseek-api-key sk-xxx --telegram-send false

    # Weekly recap (no fetch, no DeepSeek — reuses stored summaries):
    python -m src.main \
        --deepseek-api-key sk-unused \
        --mode recap --recap-days 7 \
        --telegram-bot-token 1234:abc --telegram-chat-id 12345
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from . import state, telegram_sender
from .fetcher import fetch_fresh
from .summarizer import summarize

ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = ROOT / "logs" / "run.log"


def _setup_logging() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout),
        ],
    )


def _str2bool(v: str) -> bool:
    s = v.strip().lower()
    if s in ("true", "t", "yes", "y", "1"):
        return True
    if s in ("false", "f", "no", "n", "0"):
        return False
    raise argparse.ArgumentTypeError(f"expected true/false, got {v!r}")


def _notify_error(log: logging.Logger, message: str, *, telegram_send: bool, token: str | None, chat_ids: str | None) -> None:
    if not (telegram_send and token and chat_ids):
        return
    try:
        telegram_sender.send_error(message, token=token, chat_ids=chat_ids)
    except Exception as e:
        log.exception("error notification failed: %s", e)


def _run_digest(
    *,
    log: logging.Logger,
    deepseek_api_key: str,
    telegram_send: bool,
    telegram_bot_token: str | None,
    telegram_chat_id: str | None,
    min_upvotes: int,
    attach_pdf: bool,
) -> int:
    want = int(os.environ.get("PAPERS_PER_DAY", "3"))
    papers = fetch_fresh(want=want, min_upvotes=min_upvotes)
    if not papers:
        log.warning("no fresh papers found (min_upvotes=%d); nothing to send", min_upvotes)
        return 0

    log.info("selected %d papers: %s", len(papers), [p.arxiv_id for p in papers])

    failures = 0
    for paper in papers:
        try:
            summary = summarize(paper, api_key=deepseek_api_key)
        except Exception as e:
            log.exception("summarize failed for %s: %s", paper.arxiv_id, e)
            failures += 1
            continue

        if not telegram_send:
            print("=" * 80)
            print(f"{paper.arxiv_id} — {paper.title} (👍 {paper.upvotes})")
            print(f"  {paper.arxiv_url}")
            print()
            print("[short_intro]")
            print(summary.short_intro)
            print()
            print("[detailed_summary]")
            print(summary.detailed_summary)
            print()
            print("[professor_explanation]")
            print(summary.professor_explanation)
            print()
            continue

        try:
            sent_ok = telegram_sender.send_paper(
                paper,
                summary,
                token=telegram_bot_token,
                chat_ids=telegram_chat_id,
                attach_pdf=attach_pdf,
            )
        except Exception as e:
            log.exception("telegram send failed for %s: %s", paper.arxiv_id, e)
            failures += 1
            continue

        if sent_ok:
            state.mark_sent(
                paper.arxiv_id,
                paper.title,
                upvotes=paper.upvotes,
                arxiv_url=paper.arxiv_url,
                hf_url=paper.hf_url,
                short_intro=summary.short_intro,
            )
            log.info("sent %s", paper.arxiv_id)
        else:
            failures += 1

    if failures and telegram_send:
        _notify_error(
            log,
            f"{failures}/{len(papers)} papers failed during digest run",
            telegram_send=telegram_send,
            token=telegram_bot_token,
            chat_ids=telegram_chat_id,
        )

    return 0 if failures == 0 else 1


def _run_recap(
    *,
    log: logging.Logger,
    telegram_send: bool,
    telegram_bot_token: str | None,
    telegram_chat_id: str | None,
    recap_days: int,
) -> int:
    entries = state.recent(days=recap_days)
    log.info("recap: %d entries in the last %d days", len(entries), recap_days)
    text = telegram_sender.format_recap(entries, days=recap_days)

    if not telegram_send:
        print(text)
        return 0

    try:
        ok = telegram_sender.send(text, token=telegram_bot_token, chat_ids=telegram_chat_id)
    except Exception as e:
        log.exception("recap send failed: %s", e)
        return 1
    return 0 if ok else 1


def run(
    *,
    deepseek_api_key: str,
    telegram_send: bool,
    telegram_bot_token: str | None,
    telegram_chat_id: str | None,
    min_upvotes: int,
    attach_pdf: bool,
    mode: str,
    recap_days: int,
) -> int:
    _setup_logging()
    log = logging.getLogger("main")

    if telegram_send and (not telegram_bot_token or not telegram_chat_id):
        log.error("--telegram-send true requires --telegram-bot-token and --telegram-chat-id")
        return 2

    try:
        if mode == "recap":
            return _run_recap(
                log=log,
                telegram_send=telegram_send,
                telegram_bot_token=telegram_bot_token,
                telegram_chat_id=telegram_chat_id,
                recap_days=recap_days,
            )
        return _run_digest(
            log=log,
            deepseek_api_key=deepseek_api_key,
            telegram_send=telegram_send,
            telegram_bot_token=telegram_bot_token,
            telegram_chat_id=telegram_chat_id,
            min_upvotes=min_upvotes,
            attach_pdf=attach_pdf,
        )
    except Exception as e:
        log.exception("unhandled error in run: %s", e)
        _notify_error(
            log,
            f"{type(e).__name__}: {e}",
            telegram_send=telegram_send,
            token=telegram_bot_token,
            chat_ids=telegram_chat_id,
        )
        return 1


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--deepseek-api-key", required=True, help="DeepSeek API key.")
    p.add_argument(
        "--telegram-send",
        type=_str2bool,
        default=True,
        metavar="true|false",
        help="Whether to actually send to Telegram. If false, output is printed to stdout and state is not updated.",
    )
    p.add_argument("--telegram-bot-token", default=None, help="Telegram bot token (required when --telegram-send true).")
    p.add_argument(
        "--telegram-chat-id",
        default=None,
        help="Telegram chat id(s). Comma-separated to fan-out to multiple chats. Required when --telegram-send true.",
    )
    p.add_argument(
        "--min-upvotes",
        type=int,
        default=5,
        help="Skip papers with fewer upvotes than this (default: 5).",
    )
    p.add_argument(
        "--attach-pdf",
        type=_str2bool,
        default=False,
        metavar="true|false",
        help="Also send the arXiv PDF as a Telegram document (default: false).",
    )
    p.add_argument(
        "--mode",
        choices=("digest", "recap"),
        default="digest",
        help="digest: fetch + summarize + send (default). recap: send a weekly digest of already-sent papers.",
    )
    p.add_argument(
        "--recap-days",
        type=int,
        default=7,
        help="Window (in days) for --mode recap (default: 7).",
    )
    args = p.parse_args()

    sys.exit(
        run(
            deepseek_api_key=args.deepseek_api_key,
            telegram_send=args.telegram_send,
            telegram_bot_token=args.telegram_bot_token,
            telegram_chat_id=args.telegram_chat_id,
            min_upvotes=args.min_upvotes,
            attach_pdf=args.attach_pdf,
            mode=args.mode,
            recap_days=args.recap_days,
        )
    )


if __name__ == "__main__":
    main()
