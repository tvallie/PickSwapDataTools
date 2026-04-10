"""differ.py — deterministic diffing of pick lists across sources and vs existing JSON."""


def diff_current_picks(sources: dict[str, list[dict]]) -> list[dict]:
    """Compare current-year pick lists from multiple sources.

    Args:
        sources: {source_name: [pick, ...]}

    Returns:
        List of conflict dicts, one per overall pick slot where sources disagree.
    """
    if len(sources) < 2:
        return []

    source_names = list(sources.keys())
    # Index each source by overall pick number
    indexed = {
        name: {p["overall"]: p for p in picks}
        for name, picks in sources.items()
    }

    all_overalls = sorted(
        {overall for picks in indexed.values() for overall in picks}
    )

    conflicts = []
    for overall in all_overalls:
        values = {
            name: indexed[name][overall]
            for name in source_names
            if overall in indexed[name]
        }
        # Compare team + abbr across sources
        abbrs = {v["abbr"] for v in values.values()}
        if len(abbrs) > 1:
            conflicts.append({
                "overall": overall,
                "round": next(iter(values.values()))["round"],
                "pick_in_round": next(iter(values.values()))["pick_in_round"],
                "values": {name: {"team": v["team"], "abbr": v["abbr"]}
                           for name, v in values.items()},
            })
    return conflicts


def compare_current_to_existing(
    scraped: list[dict], existing: list[dict]
) -> list[dict]:
    """Diff scraped consensus picks against the existing JSON.

    Returns proposed changes — picks where scraped data differs from existing.
    """
    existing_idx = {p["overall"]: p for p in existing}
    changes = []
    for pick in scraped:
        overall = pick["overall"]
        ex = existing_idx.get(overall)
        if ex is None:
            # New pick slot (e.g. comp pick added)
            changes.append({"overall": overall, "current": None, "proposed": pick})
        elif pick["abbr"] != ex["abbr"] or pick.get("is_comp") != ex.get("is_comp"):
            changes.append({
                "overall": overall,
                "round": pick["round"],
                "pick_in_round": pick["pick_in_round"],
                "current": {"team": ex["team"], "abbr": ex["abbr"],
                            "is_comp": ex.get("is_comp", False),
                            "original_team": ex.get("original_team", ex["team"])},
                "proposed": {"team": pick["team"], "abbr": pick["abbr"],
                             "is_comp": pick.get("is_comp", False),
                             "original_team": pick.get("original_team", pick["team"])},
            })
    return changes


def _future_key(pick: dict) -> tuple:
    return (pick["year"], pick["round"], pick["original_abbr"])


def diff_future_picks(sources: dict[str, list[dict]]) -> list[dict]:
    """Compare future traded picks from multiple sources."""
    if len(sources) < 2:
        return []

    indexed = {
        name: {_future_key(p): p["current_abbr"] for p in picks}
        for name, picks in sources.items()
    }
    all_keys = {k for idx in indexed.values() for k in idx}

    conflicts = []
    for key in sorted(all_keys):
        values = {name: idx[key] for name, idx in indexed.items() if key in idx}
        if len(set(values.values())) > 1:
            year, round_, orig = key
            conflicts.append({
                "year": year, "round": round_, "original_abbr": orig,
                "values": values,
            })
    return conflicts


def compare_future_to_existing(
    scraped: list[dict], existing: list[dict]
) -> list[dict]:
    """Diff scraped future picks against existing JSON. Returns proposed changes."""
    existing_idx = {_future_key(p): p for p in existing}
    scraped_idx  = {_future_key(p): p for p in scraped}

    changes = []
    # Detect updates and additions
    for key, pick in scraped_idx.items():
        ex = existing_idx.get(key)
        if ex is None:
            changes.append({"action": "add", **pick})
        elif pick["current_abbr"] != ex["current_abbr"]:
            year, round_, orig = key
            changes.append({
                "action": "update",
                "year": year, "round": round_, "original_abbr": orig,
                "current_abbr": {"current": ex["current_abbr"],
                                 "proposed": pick["current_abbr"]},
            })
    # Detect removals
    for key, ex in existing_idx.items():
        if key not in scraped_idx:
            changes.append({"action": "remove", **ex})
    return changes
