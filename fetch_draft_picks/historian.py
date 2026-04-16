"""historian.py — Append pick ownership changes to history JSON files."""
import json
import logging
from pathlib import Path

logger = logging.getLogger("fetch_draft_picks.historian")

_EMPTY = {"history": []}


def _load(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {"history": []}


def _save(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def append_current_history(accepted: list[dict], date_str: str, path: Path) -> None:
    """Append one history entry per accepted current-pick change."""
    data = _load(path)
    for c in accepted:
        from_abbr = c.get("_json_abbr") or (c.get("current") or {}).get("abbr")
        to_abbr   = c["proposed"]["abbr"]
        if not from_abbr or from_abbr == to_abbr:
            continue
        data["history"].append({
            "overall":       c["overall"],
            "round":         c.get("round", c["proposed"].get("round")),
            "pick_in_round": c.get("pick_in_round", c["proposed"].get("pick_in_round")),
            "date":          date_str,
            "from":          from_abbr,
            "to":            to_abbr,
        })
    _save(data, path)
    logger.info("[historian] current: appended %d entries", len(accepted))


def append_future_history(accepted: list[dict], date_str: str, path: Path) -> None:
    """Append one history entry per accepted future-pick change."""
    data = _load(path)
    for c in accepted:
        action = c.get("action")
        year   = c.get("year")
        round_ = c.get("round")
        orig   = c.get("original_abbr")

        if action == "add":
            from_abbr = orig
            to_abbr   = c.get("current_abbr")
        elif action == "update":
            ca        = c["current_abbr"]
            from_abbr = ca.get("current")
            to_abbr   = ca.get("proposed")
        elif action == "remove":
            from_abbr = c.get("current_abbr")
            to_abbr   = orig  # pick reverts to original team
        else:
            continue

        data["history"].append({
            "year":          year,
            "round":         round_,
            "original_abbr": orig,
            "date":          date_str,
            "from":          from_abbr,
            "to":            to_abbr,
        })
    _save(data, path)
    logger.info("[historian] future: appended %d entries", len(accepted))
