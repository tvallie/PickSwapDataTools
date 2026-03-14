# PickSwap Data Tools

Utility scripts for generating and maintaining JSON data files used by the PickSwap iOS app.

## Scripts

### `fetch_nfl_players.py`

Pulls active NFL player data from the [Sleeper API](https://docs.sleeper.com/) and outputs a trimmed JSON file for upload to `pickswapapp.com/json/nfl_players.json`.

**Output fields:** `name`, `team`, `position`
**Filters:** Active players with a current roster assignment (no free agents)
**Sorted:** By team, then by player name

**Usage:**
```bash
python3 fetch_nfl_players.py
```

Output is written to `nfl_players.json` in the current directory.

**Custom output path:**
```bash
python3 fetch_nfl_players.py --output /path/to/nfl_players.json
```

**No dependencies** — uses only Python standard library (`json`, `urllib`).

## Workflow

1. Run the script to generate `nfl_players.json`
2. Upload to `https://pickswapapp.com/json/nfl_players.json`
3. The PickSwap iOS app fetches this file on launch and caches it locally

## Requirements

- Python 3.9+
- Internet access (fetches from `api.sleeper.app`)
