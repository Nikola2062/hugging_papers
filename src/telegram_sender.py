"""Send formatted paper digests to Telegram. MarkdownV2 with auto-split."""
from __future__ import annotations

import logging
import time
from typing import Iterable

import requests

from .fetcher import Paper
from .summarizer import Summary

log = logging.getLogger(__name__)

SEND_MESSAGE = "https://api.telegram.org/bot{token}/sendMessage"
SEND_DOCUMENT = "https://api.telegram.org/bot{token}/sendDocument"
MAX_LEN = 4000  # Telegram cap is 4096; leave headroom for split markers.

# MarkdownV2 reserves these. We must escape every one of them in plain text.
MDV2_SPECIAL = r"_*[]()~`>#+-=|{}.!\\"


def _esc(text: str) -> str:
    return "".join("\\" + c if c in MDV2_SPECIAL else c for c in text)


def format_message(paper: Paper, summary: Summary) -> str:
    title = _esc(paper.title)
    authors_line = _esc(", ".join(paper.authors[:5]) + (" et al." if len(paper.authors) > 5 else ""))
    arxiv = _esc(paper.arxiv_url)
    hf = _esc(paper.hf_url)
    upvotes = _esc(str(paper.upvotes))

    parts = [
        f"📄 *{title}*",
        f"_{authors_line}_" if authors_line else "",
        f"👍 {upvotes}  \\|  [arXiv]({arxiv})  \\|  [HF]({hf})",
        "",
        "*🎓 Professor's take*",
        _esc(summary.professor_explanation),
        "",
        "*🔹 Short intro*",
        _esc(summary.short_intro),
        "",
        "*🔸 Detailed summary*",
        _esc(summary.detailed_summary),
    ]
    return "\n".join(p for p in parts if p != "")


def format_recap(entries: list[dict], days: int) -> str:
    """Format a weekly digest from stored state entries. Top by upvotes."""
    ranked = sorted(entries, key=lambda e: int(e.get("upvotes") or 0), reverse=True)
    header = f"📚 *Weekly recap* — top papers from the last {days} days"
    if not ranked:
        return header + "\n\n" + _esc("(nothing sent in this window)")

    blocks: list[str] = [header, ""]
    for entry in ranked:
        title = _esc(entry.get("title", "") or entry.get("arxiv_id", ""))
        upvotes = _esc(str(entry.get("upvotes") or 0))
        arxiv = _esc(entry.get("arxiv_url") or f"https://arxiv.org/abs/{entry.get('arxiv_id', '')}")
        hf = _esc(entry.get("hf_url") or f"https://huggingface.co/papers/{entry.get('arxiv_id', '')}")
        intro = _esc(entry.get("short_intro", "") or "")

        block = [
            f"📄 *{title}*",
            f"👍 {upvotes}  \\|  [arXiv]({arxiv})  \\|  [HF]({hf})",
        ]
        if intro:
            block.append(intro)
        blocks.append("\n".join(block))
        blocks.append("")
    return "\n".join(blocks).rstrip()


def _split(text: str, limit: int = MAX_LEN) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        # Split on a paragraph boundary near the limit if possible.
        cut = remaining.rfind("\n\n", 0, limit)
        if cut == -1:
            cut = remaining.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


def _normalize_chats(chat_ids: str | Iterable[str]) -> list[str]:
    if isinstance(chat_ids, str):
        return [c.strip() for c in chat_ids.split(",") if c.strip()]
    return [str(c).strip() for c in chat_ids if str(c).strip()]


def send(text: str, *, token: str, chat_ids: str | Iterable[str], parse_mode: str | None = "MarkdownV2") -> bool:
    chats = _normalize_chats(chat_ids)
    if not token or not chats:
        raise RuntimeError("Telegram bot token and at least one chat id are required")

    url = SEND_MESSAGE.format(token=token)
    chunks = _split(text)
    ok = True
    for chat_id in chats:
        for i, chunk in enumerate(chunks):
            payload = {
                "chat_id": chat_id,
                "text": chunk,
                "disable_web_page_preview": True,
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode
            r = requests.post(url, json=payload, timeout=30)
            if not r.ok:
                log.error("telegram send failed (chat=%s): %s %s", chat_id, r.status_code, r.text)
                ok = False
            if i + 1 < len(chunks):
                time.sleep(0.5)  # be polite to Telegram's rate limit
    return ok


def send_document(doc_url: str, *, token: str, chat_ids: str | Iterable[str], caption: str | None = None) -> bool:
    chats = _normalize_chats(chat_ids)
    if not token or not chats:
        raise RuntimeError("Telegram bot token and at least one chat id are required")

    url = SEND_DOCUMENT.format(token=token)
    ok = True
    for chat_id in chats:
        payload = {"chat_id": chat_id, "document": doc_url}
        if caption:
            payload["caption"] = caption
        r = requests.post(url, json=payload, timeout=60)
        if not r.ok:
            log.error("telegram sendDocument failed (chat=%s): %s %s", chat_id, r.status_code, r.text)
            ok = False
    return ok


def send_paper(
    paper: Paper,
    summary: Summary,
    *,
    token: str,
    chat_ids: str | Iterable[str],
    attach_pdf: bool = False,
) -> bool:
    ok = send(format_message(paper, summary), token=token, chat_ids=chat_ids)
    if attach_pdf:
        pdf_url = f"https://arxiv.org/pdf/{paper.arxiv_id}.pdf"
        ok = send_document(pdf_url, token=token, chat_ids=chat_ids, caption=paper.title) and ok
    return ok


def send_error(message: str, *, token: str, chat_ids: str | Iterable[str]) -> bool:
    """Best-effort error ping. Plain text (no MarkdownV2) to avoid escape headaches."""
    chats = _normalize_chats(chat_ids)
    if not token or not chats:
        return False
    text = f"⚠️ hugging_papers error: {message}"[:MAX_LEN]
    try:
        return send(text, token=token, chat_ids=chats, parse_mode=None)
    except Exception as e:
        log.exception("error notification itself failed: %s", e)
        return False
