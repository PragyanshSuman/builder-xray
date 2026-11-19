from datetime import UTC, datetime
from pathlib import Path

from bxr.core.archive import RawArchive, sha256_hex

T = datetime(2026, 11, 19, tzinfo=UTC)


def _put(a: RawArchive, url: str, body: bytes) -> str:
    return a.put(
        url=url,
        final_url=url,
        status=200,
        content_type="text/html",
        body=body,
        truncated=False,
        fetched_at=T,
    ).sha256


def test_dedupes_bytes_but_logs_every_fetch(tmp_path: Path) -> None:
    a = RawArchive(tmp_path)
    d1 = _put(a, "https://x/1", b"same")
    d2 = _put(a, "https://x/2", b"same")
    assert d1 == d2 == sha256_hex(b"same")
    assert len(list((tmp_path / "objects").rglob("*"))) == 2  # one dir + one file
    assert [e.url for e in a.entries()] == ["https://x/1", "https://x/2"]


def test_roundtrip_and_layout(tmp_path: Path) -> None:
    a = RawArchive(tmp_path)
    d = _put(a, "https://x/", b"<html></html>")
    assert a.get(d) == b"<html></html>"
    assert a.object_path(d) == tmp_path / "objects" / d[:2] / d[2:]


def test_empty_archive_has_no_entries(tmp_path: Path) -> None:
    assert list(RawArchive(tmp_path).entries()) == []
