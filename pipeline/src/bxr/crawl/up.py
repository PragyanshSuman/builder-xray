"""Incremental Uttar Pradesh crawl: list page → selected detail pages → snapshot.

Each run:
1. Fetches the full project list once (one ~15 MB request).
2. Chooses detail pages to fetch, in priority order, up to `max_details`:
   new projects → projects whose list row changed → details older than
   `refresh_days` (oldest first). A first full pass is therefore spread over
   several nights automatically.
3. Parses each detail page and checks it is for the expected registration number.
4. Saves state after every detail page, so an interrupted run loses nothing.
5. Writes a dated Parquet snapshot of every listed project (detail fields null
   until fetched) plus an extensions table.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict

from bxr.adapters.uttar_pradesh import (
    BASE_URL,
    LIST_MAX_BYTES,
    LIST_URL,
    REGISTERED_PROJECTS_TARGET,
    STATE_CODE,
    ListStructureError,
    UpListRow,
    UpProjectDetail,
    build_postback,
    is_error_page,
    parse_project_detail,
    parse_project_list,
)
from bxr.core.http import CrawlAbortedError, PoliteClient

log = logging.getLogger(__name__)


class StateEntry(BaseModel):
    row_hash: str
    first_seen: date
    last_seen: date
    detail_row_hash: str | None = None  # row hash when the detail was last fetched
    detail_fetched_at: datetime | None = None
    detail_failures: int = 0


class StoredDetail(BaseModel):
    model_config = ConfigDict(frozen=True)

    detail: UpProjectDetail
    source_url: str
    collected_at: datetime
    raw_sha256: str | None


class CrawlSummary(BaseModel):
    started_at: datetime
    finished_at: datetime | None = None
    list_rows: int = 0
    list_qpr_flagged: int = 0
    new_projects: int = 0
    changed_rows: int = 0
    detail_queue: int = 0
    detail_attempted: int = 0
    detail_ok: int = 0
    detail_failed: int = 0
    details_on_file: int = 0
    aborted: str | None = None
    requests: int = 0
    snapshot_dir: str | None = None


def _key(reg: str) -> str:
    return reg.replace("/", "_")


class UpStore:
    """Local working state under data/state/up/ (gitignored)."""

    def __init__(self, data_dir: Path) -> None:
        self.root = data_dir / "state" / "up"
        self.details_dir = self.root / "details"
        self.index_path = self.root / "index.json"

    def load_index(self) -> dict[str, StateEntry]:
        if not self.index_path.exists():
            return {}
        raw = json.loads(self.index_path.read_text(encoding="utf-8"))
        return {k: StateEntry.model_validate(v) for k, v in raw.items()}

    def save_index(self, index: dict[str, StateEntry]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.index_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({k: v.model_dump(mode="json") for k, v in index.items()}),
            encoding="utf-8",
        )
        tmp.replace(self.index_path)

    def save_detail(self, reg: str, stored: StoredDetail) -> None:
        self.details_dir.mkdir(parents=True, exist_ok=True)
        path = self.details_dir / f"{_key(reg)}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(stored.model_dump_json(), encoding="utf-8")
        tmp.replace(path)

    def load_detail(self, reg: str) -> StoredDetail | None:
        path = self.details_dir / f"{_key(reg)}.json"
        if not path.exists():
            return None
        return StoredDetail.model_validate_json(path.read_text(encoding="utf-8"))


def select_for_detail(
    rows: list[UpListRow],
    index: dict[str, StateEntry],
    now: datetime,
    max_details: int,
    refresh_days: int = 90,
) -> list[UpListRow]:
    never, changed, stale = [], [], []
    cutoff = now - timedelta(days=refresh_days)
    for row in rows:
        if not row.detail_url:
            continue
        entry = index.get(row.rera_reg_no)
        if entry is None or entry.detail_fetched_at is None:
            never.append(row)
        elif entry.detail_row_hash != row.content_hash():
            changed.append(row)
        elif entry.detail_fetched_at < cutoff:
            stale.append((entry.detail_fetched_at, row))
    stale.sort(key=lambda pair: pair[0])
    queue = never + changed + [row for _, row in stale]
    return queue[:max_details]


# Snapshot schema: explicit so columns keep their types even when all-null.
PROJECT_SCHEMA = pa.schema(
    [
        ("project_id", pa.string()),
        ("state_code", pa.string()),
        ("rera_reg_no", pa.string()),
        ("name", pa.string()),
        ("promoter_name", pa.string()),
        ("project_type", pa.string()),
        ("registration_kind", pa.string()),
        ("district", pa.string()),
        ("tehsil", pa.string()),
        ("registered_on", pa.date32()),
        ("proposed_start", pa.date32()),
        ("original_completion", pa.date32()),
        ("current_completion", pa.date32()),
        ("proposed_period_months", pa.int32()),
        ("extension_count", pa.int32()),
        ("qpr_default_flag", pa.bool_()),
        ("applicant_type", pa.string()),
        ("promoter_address", pa.string()),
        ("promoter_project_count", pa.int32()),
        ("promoter_complaints", pa.int32()),
        ("project_complaints", pa.int32()),
        ("list_source_url", pa.string()),
        ("list_collected_at", pa.timestamp("s", tz="UTC")),
        ("detail_source_url", pa.string()),
        ("detail_collected_at", pa.timestamp("s", tz="UTC")),
        ("tier", pa.string()),
    ]
)

EXTENSION_SCHEMA = pa.schema(
    [
        ("project_id", pa.string()),
        ("seq", pa.int32()),
        ("from_date", pa.date32()),
        ("upto_date", pa.date32()),
        ("reason", pa.string()),
        ("source_url", pa.string()),
        ("collected_at", pa.timestamp("s", tz="UTC")),
    ]
)


def build_records(
    rows: list[UpListRow], store: UpStore, list_collected_at: datetime
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    projects: list[dict[str, object]] = []
    extensions: list[dict[str, object]] = []
    for row in rows:
        pid = f"{STATE_CODE}:{row.rera_reg_no}"
        stored = store.load_detail(row.rera_reg_no)
        d = stored.detail if stored else None
        projects.append(
            {
                "project_id": pid,
                "state_code": STATE_CODE,
                "rera_reg_no": row.rera_reg_no,
                "name": row.project_name,
                "promoter_name": row.promoter_name,
                "project_type": row.project_type,
                "registration_kind": d.registration_kind if d else None,
                "district": row.district,
                "tehsil": d.tehsil if d else None,
                "registered_on": row.registered_on,
                "proposed_start": row.start_date,
                "original_completion": d.declared_completion if d else None,
                "current_completion": row.end_date,
                "proposed_period_months": d.proposed_period_months if d else None,
                "extension_count": len(d.extensions) if d else None,
                "qpr_default_flag": row.qpr_default_flag,
                "applicant_type": d.applicant_type if d else None,
                "promoter_address": d.promoter_address if d else None,
                "promoter_project_count": d.promoter_project_count if d else None,
                "promoter_complaints": d.promoter_complaints if d else None,
                "project_complaints": d.project_complaints if d else None,
                "list_source_url": LIST_URL,
                "list_collected_at": list_collected_at,
                "detail_source_url": stored.source_url if stored else None,
                "detail_collected_at": stored.collected_at if stored else None,
                "tier": "A",
            }
        )
        if stored and d:
            for ext in d.extensions:
                extensions.append(
                    {
                        "project_id": pid,
                        "seq": ext.seq,
                        "from_date": ext.from_date,
                        "upto_date": ext.upto_date,
                        "reason": ext.reason,
                        "source_url": stored.source_url,
                        "collected_at": stored.collected_at,
                    }
                )
    return projects, extensions


def write_snapshot(
    data_dir: Path,
    day: date,
    projects: list[dict[str, object]],
    extensions: list[dict[str, object]],
) -> Path:
    out = data_dir / "snapshots" / day.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_pylist(projects, schema=PROJECT_SCHEMA), out / "up_projects.parquet"
    )
    pq.write_table(
        pa.Table.from_pylist(extensions, schema=EXTENSION_SCHEMA), out / "up_extensions.parquet"
    )
    return out


def run_up_crawl(
    client: PoliteClient,
    data_dir: Path,
    *,
    max_details: int,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    progress: Callable[[str], None] = print,
) -> CrawlSummary:
    summary = CrawlSummary(started_at=now())
    store = UpStore(data_dir)
    index = store.load_index()

    def stop(reason: str) -> CrawlSummary:
        summary.aborted = reason
        summary.requests = client.stats["requests"]
        summary.finished_at = now()
        progress(f"aborted: {reason}")
        return summary

    # Browser flow: home page (sets session) → "Registered Projects" postback → /projects.
    try:
        home = client.get(BASE_URL)
        listing = None
        if home.ok:
            action, fields = build_postback(home.text(), home.final_url, REGISTERED_PROJECTS_TARGET)
            listing = client.post_form(action, fields, max_body_bytes=LIST_MAX_BYTES)
        if (
            listing is None
            or not listing.ok
            or listing.truncated
            or is_error_page(listing.final_url)
        ):
            res = listing or home
            return stop(
                f"list fetch failed: {res.outcome} {res.status} final={res.final_url} "
                f"truncated={res.truncated} {res.error or ''}"
            )
        list_collected_at = now()
        rows = parse_project_list(listing.text(), base_url=listing.final_url)
    except (ListStructureError, CrawlAbortedError) as exc:
        return stop(f"{type(exc).__name__}: {exc}")
    summary.list_rows = len(rows)
    summary.list_qpr_flagged = sum(r.qpr_default_flag for r in rows)
    progress(f"list: {len(rows)} projects ({summary.list_qpr_flagged} flagged 'Default on QPR')")

    today = list_collected_at.date()
    for row in rows:
        h = row.content_hash()
        entry = index.get(row.rera_reg_no)
        if entry is None:
            summary.new_projects += 1
            index[row.rera_reg_no] = StateEntry(row_hash=h, first_seen=today, last_seen=today)
        else:
            if entry.row_hash != h:
                summary.changed_rows += 1
            entry.row_hash = h
            entry.last_seen = today
    store.save_index(index)

    queue = select_for_detail(rows, index, list_collected_at, max_details)
    summary.detail_queue = len(queue)
    progress(f"detail queue: {len(queue)} (cap {max_details})")

    try:
        for i, row in enumerate(queue, start=1):
            if row.detail_url is None:  # select_for_detail never queues these
                continue
            summary.detail_attempted += 1
            entry = index[row.rera_reg_no]
            result = client.get(row.detail_url)
            detail = parse_project_detail(result.text()) if result.ok else None
            if detail is None or detail.rera_reg_no != row.rera_reg_no:
                summary.detail_failed += 1
                entry.detail_failures += 1
                got = detail.rera_reg_no if detail else None
                log.warning(
                    "detail failed for %s: %s %s (page reg=%s)",
                    row.rera_reg_no,
                    result.outcome,
                    result.status,
                    got,
                )
            else:
                store.save_detail(
                    row.rera_reg_no,
                    StoredDetail(
                        detail=detail,
                        source_url=result.final_url,
                        collected_at=now(),
                        raw_sha256=result.archived.sha256 if result.archived else None,
                    ),
                )
                summary.detail_ok += 1
                entry.detail_fetched_at = now()
                entry.detail_row_hash = row.content_hash()
                entry.detail_failures = 0
            store.save_index(index)
            if i % 50 == 0:
                ok, failed = summary.detail_ok, summary.detail_failed
                progress(f"  details {i}/{len(queue)} ok={ok} failed={failed}")
    except CrawlAbortedError as exc:
        summary.aborted = str(exc)
        progress(f"aborted: {exc}")

    projects, extensions = build_records(rows, store, list_collected_at)
    summary.details_on_file = sum(1 for p in projects if p["detail_collected_at"] is not None)
    snap = write_snapshot(data_dir, today, projects, extensions)
    summary.snapshot_dir = str(snap)
    summary.requests = client.stats["requests"]
    summary.finished_at = now()
    return summary
