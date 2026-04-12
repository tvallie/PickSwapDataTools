"""Tests for fetch_draft_picks.deployer."""
import tempfile
from pathlib import Path
from unittest.mock import patch
from fetch_draft_picks.deployer import archive_json, upload_files


def test_archive_creates_file():
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "draft_order_current.json"
        archive_dir = Path(tmp) / "archive"
        src.write_text('{"test": 1}')
        archived = archive_json(src, archive_dir, date_str="2026-04-10")
        assert archived.exists()
        assert archived.name == "draft_order_current_2026-04-10.json"
        assert src.exists()  # original still present (copy, not move)


def test_archive_collision_appends_suffix():
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "draft_order_current.json"
        archive_dir = Path(tmp) / "archive"
        src.write_text('{"test": 1}')
        first  = archive_json(src, archive_dir, date_str="2026-04-10")
        src.write_text('{"test": 2}')
        second = archive_json(src, archive_dir, date_str="2026-04-10")
        assert first.name  == "draft_order_current_2026-04-10.json"
        assert second.name == "draft_order_current_2026-04-10_2.json"


def test_upload_calls_scp_for_each_file():
    files = ["/tmp/draft_order_current.json", "/tmp/archive/draft_order_current_2026-04-10.json"]
    with patch("fetch_draft_picks.deployer.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        results = upload_files(files)
    assert mock_run.call_count == len(files)
    assert all(r["success"] for r in results)


def test_upload_reports_failure():
    with patch("fetch_draft_picks.deployer.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        results = upload_files(["/tmp/draft_order_current.json"])
    assert not results[0]["success"]
