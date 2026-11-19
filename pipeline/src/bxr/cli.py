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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bxr", description="Builder X-Ray pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    fc = sub.add_parser("filecount", help="fail if a build dir exceeds the static file gate")
    fc.add_argument("dist", help="build output directory, e.g. ../site/dist")
    fc.set_defaults(func=_cmd_filecount)

    st = sub.add_parser("status", help="show limits config and kill switches")
    st.set_defaults(func=_cmd_status)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
