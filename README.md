# hugging_papers

Daily Hugging Face papers digest delivered to Telegram. Picks 3 trending papers each morning, summarizes them in three levels (short intro → detailed bullets → professor-style explanation), and sends them to a Telegram chat. Tracks what has been sent so nothing repeats.

## Architecture

```
HF /api/daily_papers ──► fetcher.py ──► state.py (dedup) ──► top 3 fresh
                                                                  │
                                                                  ▼
                                                          summarizer.py (DeepSeek)
                                                                  │
                                                                  ▼
                                                          telegram_sender.py
                                                                  │
                                                                  ▼
                                                          state.py (mark sent)
```

- **Source**: `huggingface.co/api/daily_papers`, with `?date=YYYY-MM-DD` fallback when fewer than 3 unseen papers remain today.
- **LLM**: DeepSeek (`deepseek-chat`) via its OpenAI-compatible endpoint.
- **Delivery**: Telegram Bot API, one message per paper, MarkdownV2 formatted.
- **Dedup**: `state/sent_papers.json` keeps every arXiv ID ever sent.
- **Scheduler**: macOS `launchd` plist firing at 10:00 daily. Portable shell script so a small Linux VPS can later run it via cron/systemd.

## Setup

1. **Activate venv and install deps** (already done if you ran the bootstrap):
   ```sh
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

2. **Create a Telegram bot**
   - DM [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token.
   - Send any message to your new bot, then visit `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `chat.id` from the response.

3. **Get a DeepSeek API key** at <https://platform.deepseek.com> (cheap; ~$0.001 per paper).

4. **Pass credentials via CLI flags** (no `.env` needed). The orchestrator takes:
   - `--deepseek-api-key` (required)
   - `--telegram-send true|false` (default `true`)
   - `--telegram-bot-token` and `--telegram-chat-id` (required when `--telegram-send true`).
     `--telegram-chat-id` accepts a comma-separated list to fan-out to multiple chats.
   - `--min-upvotes` (default `5`) — skip papers below this upvote count.
   - `--attach-pdf true|false` (default `false`) — also send the arXiv PDF as a Telegram document.
   - `--mode digest|recap` (default `digest`) — `recap` skips the fetcher/DeepSeek and resends
     a "best of the week" using stored summaries.
   - `--recap-days` (default `7`) — window for `--mode recap`.
   - `--schedule` — run as a long-lived daemon that fires the chosen mode daily at
     `SCHEDULE_HOUR:SCHEDULE_MINUTE` (Europe/Berlin, defaults to `10:00`).
     See section 7a below.
   - `--run-now` — only meaningful with `--schedule`; execute one run immediately on start
     before entering the sleep loop.

5. **Dry-run** (no Telegram, no state write — just prints the summaries):
   ```sh
   .venv/bin/python -m src.main \
       --deepseek-api-key "$DEEPSEEK_API_KEY" \
       --telegram-send false
   ```

6. **Real run** (sends to Telegram, updates state):
   ```sh
   .venv/bin/python -m src.main \
       --deepseek-api-key "$DEEPSEEK_API_KEY" \
       --telegram-send true \
       --telegram-bot-token "$TELEGRAM_BOT_TOKEN" \
       --telegram-chat-id "$TELEGRAM_CHAT_ID" \
       --min-upvotes 5 \
       --attach-pdf false
   ```

   **Weekly recap** (no fetcher, no DeepSeek call — reuses stored summaries; schedule on Sunday):
   ```sh
   .venv/bin/python -m src.main \
       --deepseek-api-key unused \
       --mode recap --recap-days 7 \
       --telegram-send true \
       --telegram-bot-token "$TELEGRAM_BOT_TOKEN" \
       --telegram-chat-id "$TELEGRAM_CHAT_ID"
   ```

7. **Schedule it.** Three options — pick whichever fits your environment:

   **a) Built-in scheduler (recommended, OS-agnostic).** `main.py` can run as a long-lived
   daemon that fires once a day on its own. No launchd / cron needed.
   ```sh
   .venv/bin/python -m src.main \
       --deepseek-api-key   "$DEEPSEEK_API_KEY" \
       --telegram-bot-token "$TELEGRAM_BOT_TOKEN" \
       --telegram-chat-id   "$TELEGRAM_CHAT_ID" \
       --schedule
   ```
   - Default fire time is **10:00 Europe/Berlin**. Override via env vars:
     `SCHEDULE_HOUR=8 SCHEDULE_MINUTE=30 .venv/bin/python -m src.main ... --schedule`
   - Add `--run-now` to execute one digest immediately on start, then enter the daily loop.
   - Sends a `🟢 scheduler started` ping to Telegram on startup; logs to `logs/run.log`.
   - Exits cleanly on `Ctrl+C` / `SIGTERM` (responsive within ~30s).
   - Run it under `nohup`, `tmux`, `screen`, or as a systemd unit on Linux to keep it alive
     across logouts.

   **b) macOS launchd** (legacy — fires the one-shot command daily):
   ```sh
   cp scripts/com.user.hugging-papers.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.user.hugging-papers.plist
   ```
   Logs land in `logs/launchd.out` and `logs/launchd.err`.

   **c) Linux cron** (legacy — fires the one-shot command daily):
   ```sh
   crontab -e
   # add (replace credentials):
   0 10 * * * cd /path/to/hugging_papers && .venv/bin/python -m src.main \
       --deepseek-api-key sk-xxx \
       --telegram-send true \
       --telegram-bot-token 1234:abc \
       --telegram-chat-id 12345 \
       >> logs/cron.log 2>&1
   ```
   Or use `scripts/run_daily.sh`, which forwards `DEEPSEEK_API_KEY`, `TELEGRAM_BOT_TOKEN`,
   `TELEGRAM_CHAT_ID`, and `TELEGRAM_SEND` from the environment to the CLI flags.

Everything else (fetcher, summarizer, sender, state) is pure Python with no platform-specific
dependencies.

## TODO

- [x] Verify Hugging Face papers API shape
- [x] Set up Python venv + skeleton (`requirements.txt`, `.env.example`, `.gitignore`)
- [x] Write this README
- [x] `src/state.py` — JSON-backed dedup store
- [x] `src/fetcher.py` — daily papers + date fallback
- [x] `src/summarizer.py` — DeepSeek 3-tier output
- [x] `src/telegram_sender.py` — MarkdownV2 sender with auto-split
- [x] `src/main.py` — orchestrator with `--dry-run`
- [x] `scripts/run_daily.sh` + `scripts/com.user.hugging-papers.plist`
- [x] End-to-end dry-run test
- [ ] **User action**: fill in `.env` with real credentials
- [ ] **User action**: pick a scheduler — run `python -m src.main ... --schedule` under
  nohup/tmux/systemd, or load the launchd plist / cron entry
- [ ] Optional: prometheus/healthcheck ping if running on VPS
- [ ] Optional: support inline PDF download + Telegram document attachment
- [ ] Optional: weekly digest mode (Sunday recap of week's papers)

## Implemented extras

- **Quality filter** — `--min-upvotes N` (default `5`) skips obscure papers. Threaded through the backfill loop so the fetcher keeps walking until it finds enough qualifying papers.
- **PDF attach** — `--attach-pdf true` also delivers `https://arxiv.org/pdf/{id}.pdf` via Telegram `sendDocument` with the paper title as the caption.
- **Weekly recap** — `--mode recap [--recap-days 7]` skips the fetcher + DeepSeek and re-formats the last week's stored summaries into a ranked "best of the week" digest. Schedule a second cron entry on Sunday.
- **Multiple chats** — `--telegram-chat-id "id1,id2,id3"` fans out every message (and PDF) to each chat.
- **Error notification** — unhandled exceptions and per-run failure summaries are sent as a short `⚠️ hugging_papers error:` message to the configured chats (plain text, no MarkdownV2 escaping needed).
