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

Also deploys to PickSwapWeb/json/nfl_players.json, archiving the previous
version to PickSwapWeb/json/prev_versions/nfl_players_YYYY-MM-DD.json.

Usage:
    python3 fetch_nfl_players.py                  # full run: fetch, deploy local, upload to server
    python3 fetch_nfl_players.py --no-upload      # skip Bluehost SCP upload
    python3 fetch_nfl_players.py --no-deploy      # skip PickSwapWeb local deploy
    python3 fetch_nfl_players.py --output x.json  # custom local output path
"""

import json
import os
import shutil
import ssl
import subprocess
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
WEB_JSON_DIR = os.path.expanduser("~/CodingProjects/PickSwapWeb/json")
WEB_OUTPUT = os.path.join(WEB_JSON_DIR, "nfl_players.json")
WEB_PREV_DIR = os.path.join(WEB_JSON_DIR, "prev_versions")

# Bluehost SSH config
SSH_HOST = "67.20.76.241"
SSH_USER = "vallieor"
REMOTE_JSON_DIR = "public_html/json"
REMOTE_OUTPUT = f"{SSH_USER}@{SSH_HOST}:{REMOTE_JSON_DIR}/nfl_players.json"


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


def build_payload(players: list[dict]) -> tuple[dict, str]:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "generated_at": generated_at,
        "players": players,
    }
    return payload, generated_at


def write_output(payload: dict, output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    count = len(payload["players"])
    print(f"  Wrote {count:,} active rostered players → {output_path}")


def deploy_to_web(payload: dict) -> None:
    """Archive the existing nfl_players.json (if any), then write the new one."""
    today = datetime.now().strftime("%Y-%m-%d")

    # Archive existing file if present
    if os.path.exists(WEB_OUTPUT):
        os.makedirs(WEB_PREV_DIR, exist_ok=True)
        archive_name = f"nfl_players_{today}.json"
        archive_path = os.path.join(WEB_PREV_DIR, archive_name)
        # Avoid clobbering an existing archive from the same day
        if os.path.exists(archive_path):
            i = 1
            while os.path.exists(archive_path):
                archive_name = f"nfl_players_{today}_{i}.json"
                archive_path = os.path.join(WEB_PREV_DIR, archive_name)
                i += 1
        shutil.move(WEB_OUTPUT, archive_path)
        print(f"  Archived previous file → prev_versions/{archive_name}")

    write_output(payload, WEB_OUTPUT)


def upload_to_server(local_path: str) -> None:
    """SCP the file to Bluehost. Will prompt for password unless SSH keys are configured."""
    print(f"\nUploading to {REMOTE_OUTPUT} ...")
    result = subprocess.run(
        ["scp", local_path, REMOTE_OUTPUT],
        check=False,
    )
    if result.returncode == 0:
        print(f"  Upload complete.")
    else:
        print(f"  Upload failed (exit code {result.returncode}). Check SSH credentials.")


def main():
    parser = argparse.ArgumentParser(description="Fetch active NFL players from Sleeper API.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT,
                        help=f"Local output JSON path (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--no-deploy", action="store_true",
                        help="Skip deploying to PickSwapWeb/json/")
    parser.add_argument("--no-upload", action="store_true",
                        help="Skip SCP upload to Bluehost")
    args = parser.parse_args()

    raw = fetch_players()
    players = filter_players(raw)
    print(f"  Filtered to {len(players):,} active rostered players.")

    payload, generated_at = build_payload(players)
    print(f"  generated_at: {generated_at}")

    # Write local output
    write_output(payload, args.output)

    # Deploy to PickSwapWeb
    if not args.no_deploy:
        print(f"\nDeploying to PickSwapWeb ...")
        deploy_to_web(payload)

    # Upload to Bluehost via SCP
    if not args.no_upload:
        upload_to_server(WEB_OUTPUT)

    print("\nDone.")


if __name__ == "__main__":
    main()
