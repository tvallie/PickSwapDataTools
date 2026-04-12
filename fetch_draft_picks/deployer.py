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


SSH_HOST    = "67.20.76.241"
SSH_USER    = "vallieor"
REMOTE_JSON = "public_html/website_3650ab54/json"
SSH_KEY     = os.path.expanduser("~/.ssh/id_ed25519")


def upload_files(local_paths: list[str]) -> list[dict]:
    """SCP each file to Bluehost. Returns list of {path, success, error}."""
    results = []
    env = os.environ.copy()
    env["SSH_AUTH_SOCK"] = ""  # prevent agent interference

    for path in local_paths:
        filename = os.path.basename(path)
        if "archive" in path.replace("\\", "/"):
            remote = f"{SSH_USER}@{SSH_HOST}:{REMOTE_JSON}/archive/{filename}"
        else:
            remote = f"{SSH_USER}@{SSH_HOST}:{REMOTE_JSON}/{filename}"

        result = subprocess.run(
            ["scp", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes", path, remote],
            check=False, env=env,
        )
        results.append({
            "path": path,
            "remote": remote,
            "success": result.returncode == 0,
            "error": None if result.returncode == 0 else f"exit code {result.returncode}",
        })
    return results
