"""Deploy file-count gate (spec §7.2).

Cloudflare Workers Free allows 20,000 static files per version. We fail the
build above the gate in config/limits.yaml (19,000) to keep headroom.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# Wrangler uploads everything in the assets dir except these control files.
_IGNORED = frozenset({".assetsignore", "_headers", "_redirects"})


@dataclass(frozen=True)
class FileCountReport:
    total: int
    limit: int
    by_section: dict[str, int]

    @property
    def ok(self) -> bool:
        return self.total <= self.limit

    def render(self) -> str:
        lines = [f"{'section':<30} {'files':>8}"]
        for section, count in sorted(self.by_section.items(), key=lambda kv: -kv[1]):
            lines.append(f"{section:<30} {count:>8}")
        status = "OK" if self.ok else "FAIL: over limit"
        lines.append(f"{'TOTAL':<30} {self.total:>8}  / {self.limit}  {status}")
        return "\n".join(lines)


def count_files(dist: Path, limit: int) -> FileCountReport:
    if not dist.is_dir():
        raise FileNotFoundError(f"build output not found: {dist}")
    sections: Counter[str] = Counter()
    for path in dist.rglob("*"):
        if not path.is_file() or path.name in _IGNORED:
            continue
        rel = path.relative_to(dist)
        section = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        sections[section] += 1
    return FileCountReport(total=sum(sections.values()), limit=limit, by_section=dict(sections))
