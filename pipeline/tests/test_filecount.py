from pathlib import Path

import pytest

from bxr.cli import main
from bxr.tools.filecount import count_files


def _make(dist: Path, rel: str) -> None:
    p = dist / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")


def test_counts_by_section_and_ignores_control_files(tmp_path: Path) -> None:
    for rel in [
        "index.html",
        "_headers",
        "_redirects",
        "project/a/index.html",
        "project/b/index.html",
        "shards/0.json",
    ]:
        _make(tmp_path, rel)
    report = count_files(tmp_path, limit=10)
    assert report.total == 4
    assert report.by_section == {"(root)": 1, "project": 2, "shards": 1}
    assert report.ok


def test_fails_over_limit(tmp_path: Path) -> None:
    for i in range(4):
        _make(tmp_path, f"p/{i}.html")
    report = count_files(tmp_path, limit=3)
    assert not report.ok
    assert "FAIL" in report.render()


def test_exactly_at_limit_passes(tmp_path: Path) -> None:
    for i in range(3):
        _make(tmp_path, f"{i}.html")
    assert count_files(tmp_path, limit=3).ok


def test_missing_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        count_files(tmp_path / "nope", limit=1)


def test_cli_exit_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    _make(tmp_path, "index.html")
    assert main(["filecount", str(tmp_path)]) == 0
