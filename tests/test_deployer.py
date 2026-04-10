"""Tests for fetch_draft_picks.deployer."""
import tempfile
from pathlib import Path
from fetch_draft_picks.deployer import archive_json


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
