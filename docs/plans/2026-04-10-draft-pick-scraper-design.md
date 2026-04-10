# Draft Pick Scraper — Design Document

**Date:** 2026-04-10
**Status:** Approved

## Overview

A modular Python CLI tool that scrapes NFL draft pick ownership and draft order from multiple sources, compares them deterministically, uses AI analysis on conflicts only, and interactively asks for approval before writing changes to `json/draft_order_current.json` and `json/future_pick_trades.json`.

## Package Structure

```
fetch_draft_picks/
├── __main__.py     # CLI entry, orchestration, interactive approval loop
├── scraper.py      # Python scraping + Claude browsing fallback, source registry
├── differ.py       # Deterministic diffing (current picks & future picks formats)
├── analyzer.py     # AI analysis, dynamic model selection, news scan
└── deployer.py     # Archive + SCP upload
```

**Run as:**
```bash
python3 -m fetch_draft_picks --current
python3 -m fetch_draft_picks --future
python3 -m fetch_draft_picks --all
```

## Data Flow

```
For each mode (current / future):

1. SCRAPE     — Try each registered source via Python; fall back to Claude browsing
                if any fail (per-source fallback, not whole-run)
2. DIFF       — Deterministic comparison across sources; flag every disagreement
3. LOAD       — Load existing JSON from json/
4. COMPARE    — Diff scraped consensus vs existing JSON; identify proposed changes
5. AI ANALYZE — Send only conflicting data + news search to Claude (model auto-selected)
                Skipped entirely if step 2 finds zero conflicts
6. PRESENT    — For each proposed change: show diff, sources, AI commentary; approve/reject/skip
7. ARCHIVE    — Copy current JSON to json/archive/<name>_YYYY-MM-DD.json
8. WRITE      — Write all approved changes to json/ (only after full approval pass)
9. UPLOAD     — Ask before SCP; uploads both live file and archive file to Bluehost
```

## Scraping Sources

### Current Year Draft Order
- `espn.com/nfl/draft/rounds/_/season/2026` — broad coverage, well-maintained
- `nfldraftbuzz.com/DraftOrder/2026` — dedicated draft order tracking
- `tankathon.com/nfl/full_draft` — full draft with trade info
- `prosportstransactions.com/football/DraftTrades/Years/2026.htm` — trade transaction records
- `si.com/nfl/updated-2026-nfl-draft-order-full-list-of-picks-all-seven-rounds` — full 7-round list
- `nflmockdraftdatabase.com` — detailed comp pick tracking
- `pro-football-reference.com` — authoritative historical/current data

### Future Pick Trades
- `overthecap.com/draft` — widely trusted for traded future picks
- `tankathon.com` — covers future picks too
- `nfltraderumors.co` — good for recent trade context
- `football.realgm.com/analysis/3656/NFL-Future-Draft-Picks-By-Team` — future picks by team

### News Cross-Reference (for AI context)
- `nfl.com/news`
- `espn.com`
- `profootballtalk.com`

Sources are defined in a registry in `scraper.py` — easy to add, remove, or reorder. Source order determines scraping priority. Sources will be validated and finalized during implementation.

## AI Model Selection

| Scenario | Model |
|---|---|
| No cross-source conflicts | No AI call |
| 1–3 simple conflicts, sources agree on most data | Haiku |
| 4–10 conflicts, or sources disagree on ≥2 items | Sonnet |
| 10+ conflicts, contradictory sources, or high-stakes picks (R1/R2) | Opus |

The tool announces which model it selected and why before making the API call.

## Interactive Approval Flow

For each proposed change:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROPOSED CHANGE  [3 of 7]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Pick #14 (Round 1, Pick 14)
  Current:   team=Indianapolis, abbr=IND
  Proposed:  team=New England,  abbr=NE   (original_team=Indianapolis)

Sources:
  ✓ tankathon.com          → NE
  ✓ overthecap.com         → NE
  ✗ pro-football-reference → IND  ← CONFLICT

AI Analysis (Sonnet):
  PFR appears to be outdated. PFT and ESPN both reported the
  IND→NE trade on Apr 3. Overthecap and Tankathon reflect the
  post-trade order. High confidence: accept NE.

[A]ccept  [R]eject  [S]kip  [Q]uit  >
```

- **Accept** — queues the change
- **Reject** — keeps existing value
- **Skip** — defers (prompts again at end of run)
- **Quit** — exits without writing anything

Changes are written to disk only after the full approval pass is complete. A mid-run quit leaves all JSON files untouched.

## Archiving

- Location: `json/archive/`
- Naming: `draft_order_current_YYYY-MM-DD.json` / `future_pick_trades_YYYY-MM-DD.json`
- Same-day collision: appends `_2`, `_3`, etc.
- Archive is written before the new JSON is saved

## SCP Deployment

Uses the same SSH config as `fetch_nfl_players.py`:
- Host: `67.20.76.241`, user: `vallieor`, key: `~/.ssh/id_ed25519`, `IdentitiesOnly=yes`
- Prompts before uploading:
  ```
  Ready to upload to Bluehost:
    → public_html/.../json/draft_order_current.json
    → public_html/.../json/archive/draft_order_current_2026-04-10.json

  Upload now? [Y]es / [N]o  >
  ```
- Uploads both the live file and the archive file
- Local files are written before upload attempt — no data loss on upload failure

## Logging

Log path: `~/Desktop/pickswap logs/fetch_draft_picks.log`
Rotating file handler: 2 MB max, 5 backups (matches existing script pattern)

Logs include:
- Per-source scrape result: status (OK / FAIL→fallback), method (python / claude), latency
- Per-conflict detail: which pick, what each source reported
- Per-source accuracy: whether each source agreed with the accepted value
- Model used per run and the reason for selection
- Approved and rejected changes
- Upload success/failure

Example log entries:
```
2026-04-10 14:32:01  INFO  [scraper] tankathon.com         OK  (python)   12.3s
2026-04-10 14:32:07  INFO  [scraper] pro-football-ref      FAIL→fallback  (claude-haiku)
2026-04-10 14:33:01  INFO  [conflict] Pick#14 round=1: IND(pfr) vs NE(tankathon,overthecap)
2026-04-10 14:33:01  INFO  [source-accuracy] tankathon.com      agreed_with_accepted=True
2026-04-10 14:33:01  INFO  [source-accuracy] pro-football-ref   agreed_with_accepted=False
2026-04-10 14:33:01  INFO  [model-used] sonnet  conflicts=3  high_stakes_rounds=1
2026-04-10 14:33:45  INFO  [change] ACCEPTED Pick#14 IND→NE
```

## JSON File Formats (existing, unchanged)

### draft_order_current.json
```json
{
  "year": 2026,
  "generated_at": "...",
  "comp_picks_available_date": "...",
  "picks": [
    {
      "overall": 1,
      "round": 1,
      "pick_in_round": 1,
      "team": "Las Vegas",
      "abbr": "LV",
      "is_comp": false,
      "original_team": "Las Vegas"
    }
  ]
}
```

### future_pick_trades.json
```json
{
  "generated_at": "...",
  "traded_picks": [
    {
      "year": 2027,
      "round": 1,
      "original_abbr": "IND",
      "current_abbr": "NYJ"
    }
  ]
}
```

## Notes

- No scheduled task initially — run manually until accuracy and reliability are validated
- Specific scraping selectors (CSS/XPath) per source to be determined during implementation
- Sources will be ranked by reliability over time using log data
