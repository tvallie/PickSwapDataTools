"""__main__.py — CLI entry point for fetch_draft_picks."""
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .scraper import (
    CURRENT_SOURCES, FUTURE_SOURCES, NEWS_URLS,
    scrape_all_sources, _fetch_news_snippets,
)
from .differ import (
    diff_current_picks, compare_current_to_existing,
    diff_future_picks, compare_future_to_existing,
)
from .analyzer import analyze_conflicts
from .deployer import archive_json, upload_files

REPO_ROOT   = Path(__file__).parent.parent
JSON_DIR    = REPO_ROOT / "json"
ARCHIVE_DIR = JSON_DIR / "archive"
CURRENT_JSON = JSON_DIR / "draft_order_current.json"
FUTURE_JSON  = JSON_DIR / "future_pick_trades.json"


# ── Logging ───────────────────────────────────────────────────────────────────
from logging.handlers import RotatingFileHandler
_LOG_PATH = os.path.expanduser("~/Desktop/pickswap logs/fetch_draft_picks.log")
os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
_handler = RotatingFileHandler(_LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=5)
_handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(message)s"))
_root_logger = logging.getLogger("fetch_draft_picks")
_root_logger.setLevel(logging.INFO)
_root_logger.addHandler(_handler)
logger = logging.getLogger("fetch_draft_picks.main")


# ── Approval loop ─────────────────────────────────────────────────────────────

def _print_separator():
    print("\n" + "━" * 54)


def _print_current_change(change: dict, idx: int, total: int, ai: dict):
    _print_separator()
    overall = change["overall"]
    print(f"PROPOSED CHANGE  [{idx} of {total}]")
    _print_separator()
    print(f"Pick #{overall}  (Round {change.get('round', '?')}, "
          f"Pick {change.get('pick_in_round', '?')})")
    curr = change.get("current")
    prop = change["proposed"]
    if curr:
        print(f"  Current:   team={curr['team']}, abbr={curr['abbr']}")
    else:
        print("  Current:   (new pick slot)")
    print(f"  Proposed:  team={prop['team']}, abbr={prop['abbr']}", end="")
    if prop.get("original_team") and prop["original_team"] != prop["team"]:
        print(f"  (original: {prop['original_team']})", end="")
    print()
    key = str(overall)
    if key in ai:
        a = ai[key]
        print(f"\nAI Analysis ({a.get('confidence', '?')} confidence):")
        print(f"  {a.get('summary', '')}")


def _print_future_change(change: dict, idx: int, total: int, ai: dict):
    _print_separator()
    print(f"PROPOSED CHANGE  [{idx} of {total}]")
    _print_separator()
    action = change["action"]
    if action == "add":
        print(f"ADD traded pick: {change['year']} R{change['round']} "
              f"{change['original_abbr']} → {change['current_abbr']}")
    elif action == "update":
        print(f"UPDATE {change['year']} R{change['round']} "
              f"(orig: {change['original_abbr']})")
        c = change["current_abbr"]
        print(f"  Current owner:  {c['current']}")
        print(f"  Proposed owner: {c['proposed']}")
    elif action == "remove":
        print(f"REMOVE traded pick: {change['year']} R{change['round']} "
              f"{change['original_abbr']} → {change['current_abbr']}")
    key = f"{change.get('year')}_{change.get('round')}_{change.get('original_abbr')}"
    if key in ai:
        a = ai[key]
        print(f"\nAI Analysis ({a.get('confidence', '?')} confidence):")
        print(f"  {a.get('summary', '')}")


def _prompt_user() -> str:
    while True:
        choice = input("\n[A]ccept  [R]eject  [S]kip  [Q]uit  > ").strip().upper()
        if choice in ("A", "R", "S", "Q"):
            return choice
        print("  Please enter A, R, S, or Q.")


def run_approval_loop(changes: list[dict], ai: dict, mode: str) -> list[dict] | None:
    """Interactive approval loop. Returns accepted changes, or None if user quit."""
    accepted, rejected, skipped = [], [], []
    pending = list(changes)

    while pending:
        total = len(pending)
        next_pending = []
        for i, change in enumerate(pending, 1):
            if mode == "current":
                _print_current_change(change, i, total, ai)
            else:
                _print_future_change(change, i, total, ai)
            choice = _prompt_user()
            if choice == "Q":
                print("\nQuitting. No changes written.")
                return None
            elif choice == "A":
                accepted.append(change)
                logger.info("[change] ACCEPTED %s", change)
            elif choice == "R":
                rejected.append(change)
                logger.info("[change] REJECTED %s", change)
            elif choice == "S":
                next_pending.append(change)

        if next_pending:
            print(f"\n{len(next_pending)} item(s) skipped. Review now? [Y/N] ", end="")
            if input().strip().upper() == "Y":
                pending = next_pending
            else:
                print(f"Skipping {len(next_pending)} item(s). They will not be written.")
                pending = []
        else:
            pending = []

    print(f"\n  Accepted: {len(accepted)}  Rejected: {len(rejected)}")
    return accepted


# ── Apply changes to JSON ─────────────────────────────────────────────────────

def apply_current_changes(accepted: list[dict], existing: dict) -> dict:
    idx = {p["overall"]: p for p in existing["picks"]}
    for change in accepted:
        overall = change["overall"]
        if change.get("current") is None:
            idx[overall] = change["proposed"]
        else:
            idx[overall].update(change["proposed"])
    existing["picks"] = [idx[k] for k in sorted(idx)]
    existing["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return existing


def apply_future_changes(accepted: list[dict], existing: dict) -> dict:
    from .differ import _future_key
    idx = {_future_key(p): p for p in existing["traded_picks"]}
    for change in accepted:
        key = (change.get("year"), change.get("round"), change.get("original_abbr"))
        if change["action"] == "add":
            idx[key] = {k: change[k] for k in ("year", "round", "original_abbr", "current_abbr")}
        elif change["action"] == "update":
            idx[key]["current_abbr"] = change["current_abbr"]["proposed"]
        elif change["action"] == "remove":
            idx.pop(key, None)
    existing["traded_picks"] = list(idx.values())
    existing["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return existing


# ── Source accuracy logging ───────────────────────────────────────────────────

def log_source_accuracy(scrape_results: list[dict], accepted: list[dict], mode: str):
    if mode == "current":
        accepted_abbrs = {c["overall"]: c["proposed"]["abbr"] for c in accepted}
        for res in scrape_results:
            if not res["picks"]:
                continue
            for pick in res["picks"]:
                overall = pick.get("overall")
                if overall in accepted_abbrs:
                    agreed = pick.get("abbr") == accepted_abbrs[overall]
                    logger.info(
                        "[source-accuracy] %-25s agreed_with_accepted=%-5s pick=%s",
                        res["source"], agreed, overall,
                    )


# ── Majority vote ─────────────────────────────────────────────────────────────

def _majority_vote_current(sources: dict[str, list[dict]]) -> list[dict]:
    from collections import Counter
    all_overalls = sorted({p["overall"] for picks in sources.values() for p in picks})
    result = []
    for overall in all_overalls:
        candidates = [
            next((p for p in picks if p["overall"] == overall), None)
            for picks in sources.values()
        ]
        candidates = [c for c in candidates if c]
        abbr_counts = Counter(c["abbr"] for c in candidates)
        winner_abbr = abbr_counts.most_common(1)[0][0]
        winner = next(c for c in candidates if c["abbr"] == winner_abbr)
        result.append(winner)
    return result


def _majority_vote_future(sources: dict[str, list[dict]]) -> list[dict]:
    from collections import Counter
    from .differ import _future_key
    all_keys = {_future_key(p) for picks in sources.values() for p in picks}
    result = []
    for key in sorted(all_keys):
        candidates = [
            next((p for p in picks if _future_key(p) == key), None)
            for picks in sources.values()
        ]
        candidates = [c for c in candidates if c]
        curr_counts = Counter(c["current_abbr"] for c in candidates)
        winner_curr = curr_counts.most_common(1)[0][0]
        year, round_, orig = key
        result.append({"year": year, "round": round_,
                        "original_abbr": orig, "current_abbr": winner_curr})
    return result


# ── Upload helper ─────────────────────────────────────────────────────────────

def _maybe_upload(paths: list[str]):
    print("\nReady to upload to Bluehost:")
    for p in paths:
        print(f"  → {p}")
    choice = input("\nUpload now? [Y]es / [N]o  > ").strip().upper()
    if choice == "Y":
        results = upload_files(paths)
        for r in results:
            status = "OK" if r["success"] else f"FAILED ({r['error']})"
            print(f"  {status} → {r['remote']}")
            if not r["success"]:
                logger.error("[upload] FAILED %s: %s", r["remote"], r["error"])
    else:
        print("  Upload skipped. Local files updated.")


# ── Main orchestration ────────────────────────────────────────────────────────

def run_current(dry_run: bool = False):
    print("\n=== Current Year Draft Order ===")
    print("Scraping sources...")
    results = scrape_all_sources(CURRENT_SOURCES)
    successful = {r["source"]: r["picks"] for r in results if r["picks"]}

    if len(successful) < 2:
        print(f"  ERROR: Only {len(successful)} source(s) returned data. Need ≥2 to diff.")
        sys.exit(1)

    print(f"  {len(successful)} sources scraped successfully.")
    cross_conflicts = diff_current_picks(successful)
    print(f"  Cross-source conflicts: {len(cross_conflicts)}")
    for c in cross_conflicts:
        logger.info("[conflict] Pick#%s round=%s: %s", c["overall"], c["round"],
                    {k: v["abbr"] for k, v in c["values"].items()})

    with open(CURRENT_JSON) as f:
        existing = json.load(f)

    consensus = _majority_vote_current(successful)
    changes = compare_current_to_existing(consensus, existing["picks"])
    print(f"  Proposed changes vs existing JSON: {len(changes)}")

    if not changes:
        print("  No changes needed.")
        return

    ai = {}
    if cross_conflicts:
        print("\nFetching news snippets for AI analysis...")
        news = _fetch_news_snippets(NEWS_URLS)
        ai = analyze_conflicts(cross_conflicts, news, mode="current")

    if dry_run:
        print("\n[Dry run] Changes that would be proposed:")
        for c in changes:
            print(f"  Pick#{c['overall']}: {c.get('current', {}).get('abbr', 'NEW')} → {c['proposed']['abbr']}")
        return

    accepted = run_approval_loop(changes, ai, mode="current")
    if accepted is None or not accepted:
        return

    log_source_accuracy(results, accepted, mode="current")

    date_str = datetime.now().strftime("%Y-%m-%d")
    archive_path = archive_json(CURRENT_JSON, ARCHIVE_DIR, date_str)
    print(f"\n  Archived → {archive_path.name}")

    updated = apply_current_changes(accepted, existing)
    with open(CURRENT_JSON, "w") as f:
        json.dump(updated, f, indent=2, ensure_ascii=False)
    print(f"  Written → {CURRENT_JSON.name}")

    _maybe_upload([str(CURRENT_JSON), str(archive_path)])


def run_future(dry_run: bool = False):
    print("\n=== Future Pick Trades ===")
    print("Scraping sources...")
    results = scrape_all_sources(FUTURE_SOURCES)
    successful = {r["source"]: r["picks"] for r in results if r["picks"]}

    if len(successful) < 2:
        print(f"  ERROR: Only {len(successful)} source(s) returned data. Need ≥2.")
        sys.exit(1)

    cross_conflicts = diff_future_picks(successful)
    print(f"  Cross-source conflicts: {len(cross_conflicts)}")
    for c in cross_conflicts:
        logger.info("[conflict] Future %s R%s %s: %s",
                    c["year"], c["round"], c["original_abbr"], c["values"])

    with open(FUTURE_JSON) as f:
        existing = json.load(f)

    consensus = _majority_vote_future(successful)
    changes = compare_future_to_existing(consensus, existing["traded_picks"])
    print(f"  Proposed changes vs existing JSON: {len(changes)}")

    if not changes:
        print("  No changes needed.")
        return

    ai = {}
    if cross_conflicts:
        print("\nFetching news snippets for AI analysis...")
        news = _fetch_news_snippets(NEWS_URLS)
        ai = analyze_conflicts(cross_conflicts, news, mode="future")

    if dry_run:
        for c in changes:
            print(f"  {c['action'].upper()} {c.get('year')} R{c.get('round')} "
                  f"{c.get('original_abbr')}")
        return

    accepted = run_approval_loop(changes, ai, mode="future")
    if accepted is None or not accepted:
        return

    date_str = datetime.now().strftime("%Y-%m-%d")
    archive_path = archive_json(FUTURE_JSON, ARCHIVE_DIR, date_str)
    print(f"\n  Archived → {archive_path.name}")

    updated = apply_future_changes(accepted, existing)
    with open(FUTURE_JSON, "w") as f:
        json.dump(updated, f, indent=2, ensure_ascii=False)
    print(f"  Written → {FUTURE_JSON.name}")

    _maybe_upload([str(FUTURE_JSON), str(archive_path)])


def main():
    parser = argparse.ArgumentParser(
        description="Scrape NFL draft pick data and update JSON files."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--current", action="store_true", help="Update current year draft order")
    group.add_argument("--future",  action="store_true", help="Update future pick trades")
    group.add_argument("--all",     action="store_true", help="Update both")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show proposed changes without writing or uploading")
    args = parser.parse_args()

    try:
        if args.current or args.all:
            run_current(dry_run=args.dry_run)
        if args.future or args.all:
            run_future(dry_run=args.dry_run)
    except KeyboardInterrupt:
        print("\nInterrupted. No changes written.")
        sys.exit(0)
    except Exception as e:
        logger.error("Unhandled exception: %s", e, exc_info=True)
        raise

    print("\nDone.")


if __name__ == "__main__":
    main()
