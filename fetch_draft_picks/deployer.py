"""deployer.py — archive JSON files and SCP to Bluehost."""
import shutil
import subprocess
import os
from pathlib import Path


def archive_json(src: Path, archive_dir: Path, date_str: str) -> Path:
    """Copy src to archive_dir with date appended to stem. Returns archive path."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    stem = src.stem  # e.g. "draft_order_current"
    candidate = archive_dir / f"{stem}_{date_str}.json"
    i = 2
    while candidate.exists():
        candidate = archive_dir / f"{stem}_{date_str}_{i}.json"
        i += 1
    shutil.copy2(src, candidate)
    return candidate
