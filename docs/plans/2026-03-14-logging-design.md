# Logging Design — fetch_nfl_players.py

**Date:** 2026-03-14
**Status:** Approved

## Goal

Add error-only file logging to `fetch_nfl_players.py` so failures are captured persistently, especially when the script runs unattended via launchd.

## Decisions

| Question | Decision |
|---|---|
| Log location | Next to the script: `fetch_nfl_players.log` |
| Rotation | Size-based: 2 MB cap, 5 backups (.log.1–.log.5) |
| Log level | ERROR only (terminal print output unchanged) |
| Approach | Python stdlib `logging` + `RotatingFileHandler` |

## Implementation

### Logger setup (module level, below constants)

```python
import logging
from logging.handlers import RotatingFileHandler

_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetch_nfl_players.log")
_handler = RotatingFileHandler(_LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=5)
_handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(message)s"))
logger = logging.getLogger("fetch_nfl_players")
logger.setLevel(logging.ERROR)
logger.addHandler(_handler)
```

### Error sites patched

1. **`fetch_players()`** — `URLError` catch: add `logger.error(...)` before re-raising `SystemExit`
2. **`upload_to_server()`** — non-zero SCP exit: add `logger.error(...)` alongside existing print
3. **`main()`** — wrap body in `try/except Exception`: `logger.error("Unhandled exception", exc_info=True)` then re-raise

### Log entry format

```
2026-03-14 07:25:01,442  ERROR  Network error: <urlopen error [SSL: ...]>
2026-03-14 07:25:44,118  ERROR  Upload failed (exit code 255). Check SSH credentials.
2026-03-14 07:25:44,200  ERROR  Unhandled exception
Traceback (most recent call last): ...
```

## What Does Not Change

- All `print()` calls — terminal output is identical
- Script exit behavior — errors still abort the run
- No new dependencies (stdlib only)
