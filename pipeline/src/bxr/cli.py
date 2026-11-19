"""Command-line entry point: `uv run bxr <command>`."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from bxr.config import Switch, is_enabled, load_limits
from bxr.tools.filecount import count_files


def _cmd_filecount(args: argparse.Namespace) -> int:
    limits = load_limits()
    report = count_files(Path(args.dist), limit=limits.gates.max_static_files)
    print(report.render())
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as fh:
            fh.write(f"### Deploy file count\n\n```\n{report.render()}\n```\n")
    return 0 if report.ok else 1


def _cmd_status(_: argparse.Namespace) -> int:
    limits = load_limits()
    print(f"limits verified on: {limits.verified_on}")
    print(f"stop at: {limits.stop_at_fraction:.0%} of each limit")
    for switch in Switch:
        print(f"{switch.value:<18} {'ON' if is_enabled(switch) else 'off'}")
    return 0


def _cmd_survey(args: argparse.Namespace) -> int:
    import json
    from datetime import UTC, datetime

    from bxr.adapters.unified_rera import parse_state_directory
    from bxr.config import DATA_DIR, REPO_ROOT, load_crawler_config
    from bxr.core.archive import RawArchive
    from bxr.core.http import CrawlDisabledError, PoliteClient
    from bxr.tools.survey import render_markdown, run_survey

    directory = Path(args.directory)
    portals = parse_state_directory(directory.read_text(encoding="utf-8"))
    if args.only:
        wanted = {c.strip().upper() for c in args.only.split(",")}
        portals = [p for p in portals if p.state_code in wanted]
    started = datetime.now(UTC)
    try:
        client = PoliteClient(load_crawler_config(), archive=RawArchive(DATA_DIR / "raw"))
    except CrawlDisabledError as exc:
        print(f"refusing to crawl: {exc}")
        return 2
    with client:
        checks = run_survey(client, portals)
    out_dir = DATA_DIR / "survey"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / f"{started:%Y-%m-%d}.json"
    out_json.write_text(
        json.dumps([c.model_dump(mode="json") for c in checks], indent=2), encoding="utf-8"
    )
    no_site = [p for p in portals if not p.portal_url]
    md = render_markdown(checks, no_site, started)
    (REPO_ROOT / "docs" / "portal-survey.md").write_text(md, encoding="utf-8")
    print(f"requests: {client.stats['requests']}  outcomes: {dict(client.stats)}")
    print(f"wrote {out_json} and docs/portal-survey.md")
    return 0


def _cmd_crawl_up(args: argparse.Namespace) -> int:
    from datetime import UTC, datetime

    from bxr.config import DATA_DIR, load_crawler_config
    from bxr.core.archive import RawArchive
    from bxr.core.http import CrawlDisabledError, PoliteClient
    from bxr.crawl.up import run_up_crawl

    try:
        client = PoliteClient(load_crawler_config(), archive=RawArchive(DATA_DIR / "raw"))
    except CrawlDisabledError as exc:
        print(f"refusing to crawl: {exc}")
        return 2
    with client:
        summary = run_up_crawl(client, DATA_DIR, max_details=args.max_details)
    log_dir = DATA_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    out = log_dir / f"crawl-up-{datetime.now(UTC):%Y%m%d-%H%M%S}.json"
    out.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    print(summary.model_dump_json(indent=2))
    return 1 if summary.aborted else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bxr", description="Builder X-Ray pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    fc = sub.add_parser("filecount", help="fail if a build dir exceeds the static file gate")
    fc.add_argument("dist", help="build output directory, e.g. ../site/dist")
    fc.set_defaults(func=_cmd_filecount)

    st = sub.add_parser("status", help="show limits config and kill switches")
    st.set_defaults(func=_cmd_status)

    sv = sub.add_parser("survey", help="first-look survey of every State/UT RERA portal")
    sv.add_argument(
        "--directory",
        default=str(Path(__file__).resolve().parents[3] / "fixtures" / "in" / "stateRERA.html"),
        help="saved copy of rera.mohua.gov.in/stateRERA.html",
    )
    sv.add_argument("--only", help="comma-separated state codes, e.g. MH,UP")
    sv.set_defaults(func=_cmd_survey)

    cu = sub.add_parser("crawl-up", help="incremental Uttar Pradesh crawl + snapshot")
    cu.add_argument(
        "--max-details",
        type=int,
        default=1200,
        help="max detail pages this run (1200 ≈ 1 h at 3 s/request)",
    )
    cu.set_defaults(func=_cmd_crawl_up)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
