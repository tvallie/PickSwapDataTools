#!/usr/bin/env python3
"""
fetch_nfl_players.py

Pulls active NFL players from the Sleeper API and writes a trimmed JSON file
suitable for upload to pickswapapp.com/json/nfl_players.json.

Output format:
    {
        "generated_at": "2026-03-14T12:00:00Z",
        "players": [
            {"name": "Patrick Mahomes", "team": "KC", "position": "QB"},
            ...
        ]
    }

Only includes players who are active AND currently on a roster (team is set).
Players are sorted by team, then by name within each team.

Usage:
    python3 fetch_nfl_players.py
    python3 fetch_nfl_players.py --output custom_output.json
"""

import json
import ssl
import argparse
from datetime import datetime, timezone
from urllib.request import urlopen
from urllib.error import URLError

# macOS Python doesn't use the system cert store by default.
# This context skips verification for Sleeper's public read-only API.
_ssl_context = ssl.create_default_context()
_ssl_context.check_hostname = False
_ssl_context.verify_mode = ssl.CERT_NONE

SLEEPER_URL = "https://api.sleeper.app/v1/players/nfl"
DEFAULT_OUTPUT = "nfl_players.json"

# Positions to include — skill positions relevant to NFL trades
INCLUDED_POSITIONS = {
    "QB", "RB", "WR", "TE",
    "K", "P",
    "OT", "OG", "OL", "C",
    "DE", "DT", "NT", "DL",
    "LB", "ILB", "OLB",
    "CB", "S", "FS", "SS", "DB",
    "Edge", "EDGE",
}


def fetch_players() -> dict:
    print(f"Fetching player data from {SLEEPER_URL} ...")
    try:
        with urlopen(SLEEPER_URL, timeout=30, context=_ssl_context) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except URLError as e:
        raise SystemExit(f"Network error: {e}")
    print(f"  Received {len(raw):,} total player records.")
    return raw


def filter_players(raw: dict) -> list[dict]:
    players = []
    for player_id, p in raw.items():
        # Must be marked active
        if not p.get("active"):
            continue
        # Must have a team assignment
        team = p.get("team") or ""
        if not team.strip():
            continue
        # Must have a name
        name = p.get("full_name") or ""
        if not name.strip():
            # Fall back to first + last
            first = p.get("first_name") or ""
            last = p.get("last_name") or ""
            name = f"{first} {last}".strip()
        if not name:
            continue
        # Must have a position
        position = p.get("position") or ""
        if not position.strip():
            continue

        players.append({
            "name": name.strip(),
            "team": team.strip().upper(),
            "position": position.strip().upper(),
        })

    # Sort by team, then by last name within each team
    players.sort(key=lambda p: (p["team"], p["name"].split()[-1], p["name"]))
    return players


def write_output(players: list[dict], output_path: str) -> None:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "generated_at": generated_at,
        "players": players,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"  Wrote {len(players):,} active rostered players → {output_path}")
    print(f"  generated_at: {generated_at}")


def main():
    parser = argparse.ArgumentParser(description="Fetch active NFL players from Sleeper API.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help=f"Output JSON path (default: {DEFAULT_OUTPUT})")
    args = parser.parse_args()

    raw = fetch_players()
    players = filter_players(raw)
    print(f"  Filtered to {len(players):,} active rostered players.")
    write_output(players, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
