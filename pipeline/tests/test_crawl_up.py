from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pyarrow.parquet as pq

from bxr.adapters.uttar_pradesh import UpListRow, parse_project_list
from bxr.config import REPO_ROOT, load_crawler_config
from bxr.core.http import PoliteClient
from bxr.crawl.up import StateEntry, UpStore, run_up_crawl, select_for_detail

FIX = REPO_ROOT / "fixtures" / "up"
LIST_HTML = (FIX / "projects_list.trimmed.html").read_text(encoding="utf-8")
DETAIL_HTML = (FIX / "project_detail_UPRERAPRJ839360.html").read_text(encoding="utf-8")
NOW = datetime(2026, 11, 20, 1, 30, tzinfo=UTC)


def _rows() -> list[UpListRow]:
    return parse_project_list(LIST_HTML)


HOME_HTML = (FIX / "home.html").read_text(encoding="utf-8")
MAINTENANCE = "https://up-rera.in/servermaintenance.aspx?aspxerrorpath=/projects"


def _client(*, home_html: str = HOME_HTML) -> PoliteClient:
    """Mock of up-rera.in: /projects only works after the postback (session)."""
    session = {"postback": False}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /cgi-bin/\n")
        if req.method == "POST" and req.url.path == "/":
            form = dict(httpx.QueryParams(req.content.decode()))
            if form.get("__EVENTTARGET") == "ctl00$ContentPlaceHolder1$lnkRegisteredProjects":
                session["postback"] = True
                return httpx.Response(302, headers={"Location": "/projects"})
            return httpx.Response(200, text=home_html)
        if req.url.path == "/":
            return httpx.Response(200, text=home_html)
        if req.url.path == "/projects":
            if req.method != "GET":
                return httpx.Response(405)
            if not session["postback"]:
                return httpx.Response(302, headers={"Location": MAINTENANCE})
            return httpx.Response(200, text=LIST_HTML)
        if req.url.path == "/servermaintenance.aspx":
            return httpx.Response(200, text="<html>maintenance</html>")
        if req.url.path == "/Projectsummary":
            # Every detail link returns UPRERAPRJ839360's page: only row 3 matches.
            return httpx.Response(200, text=DETAIL_HTML)
        return httpx.Response(404)

    t = {"now": 0.0}

    def sleep(s: float) -> None:
        t["now"] += s

    return PoliteClient(
        load_crawler_config(),
        transport=httpx.MockTransport(handler),
        clock=lambda: t["now"],
        sleep=sleep,
        env={"CRAWL_ENABLED": "1"},
    )


def test_select_priorities() -> None:
    rows = _rows()[:4]
    a, b, c, d = rows
    index = {
        # b: fetched recently, unchanged → skip
        b.rera_reg_no: StateEntry(
            row_hash=b.content_hash(),
            first_seen=date(2026, 1, 1),
            last_seen=date(2026, 1, 1),
            detail_row_hash=b.content_hash(),
            detail_fetched_at=NOW - timedelta(days=1),
        ),
        # c: row changed since detail fetch → queue after new ones
        c.rera_reg_no: StateEntry(
            row_hash="new",
            first_seen=date(2026, 1, 1),
            last_seen=date(2026, 1, 1),
            detail_row_hash="old",
            detail_fetched_at=NOW - timedelta(days=1),
        ),
        # d: unchanged but stale → last
        d.rera_reg_no: StateEntry(
            row_hash=d.content_hash(),
            first_seen=date(2026, 1, 1),
            last_seen=date(2026, 1, 1),
            detail_row_hash=d.content_hash(),
            detail_fetched_at=NOW - timedelta(days=200),
        ),
    }
    queue = select_for_detail(rows, index, NOW, max_details=10)
    assert [r.rera_reg_no for r in queue] == [a.rera_reg_no, c.rera_reg_no, d.rera_reg_no]
    assert len(select_for_detail(rows, index, NOW, max_details=1)) == 1


def test_end_to_end_with_reg_mismatch_guard(tmp_path: Path) -> None:
    with _client() as client:
        summary = run_up_crawl(
            client, tmp_path, max_details=3, now=lambda: NOW, progress=lambda _: None
        )

    assert summary.aborted is None
    assert summary.list_rows == 30 and summary.new_projects == 30
    # Rows 1-2 got a page for a different project → rejected, not stored.
    assert (summary.detail_attempted, summary.detail_ok, summary.detail_failed) == (3, 1, 2)

    snap = Path(summary.snapshot_dir or "")
    projects = pq.read_table(snap / "up_projects.parquet").to_pylist()
    assert len(projects) == 30
    by_reg = {p["rera_reg_no"]: p for p in projects}
    vc = by_reg["UPRERAPRJ839360"]
    assert vc["original_completion"] == date(2024, 3, 10)
    assert vc["current_completion"] == date(2024, 9, 9)
    assert vc["extension_count"] == 1
    assert vc["detail_source_url"].startswith("https://up-rera.in/Projectsummary?")
    assert by_reg["UPRERAPRJ13276"]["original_completion"] is None  # not fetched / rejected
    exts = pq.read_table(snap / "up_extensions.parquet").to_pylist()
    assert [e["project_id"] for e in exts] == ["UP:UPRERAPRJ839360"]

    # Second run: the matched project is not refetched; failures are retried first.
    index = UpStore(tmp_path).load_index()
    assert index["UPRERAPRJ13276"].detail_failures == 1
    queue = select_for_detail(_rows(), index, NOW, max_details=100)
    assert "UPRERAPRJ839360" not in [r.rera_reg_no for r in queue]
    assert len(queue) == 29


def test_aborts_cleanly_when_postback_link_missing(tmp_path: Path) -> None:
    with _client(
        home_html="<html><form><input type=hidden name=__VIEWSTATE value=x></form></html>"
    ) as client:
        summary = run_up_crawl(
            client, tmp_path, max_details=3, now=lambda: NOW, progress=lambda _: None
        )
    assert summary.aborted and "lnkRegisteredProjects" in summary.aborted
    assert summary.snapshot_dir is None
