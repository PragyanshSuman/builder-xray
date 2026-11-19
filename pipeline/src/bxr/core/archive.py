"""Content-addressed raw archive (spec §5.2).

Bodies are stored once by sha256 under `<root>/objects/ab/cdef...`. Every fetch
(including repeats of identical content) appends one line to
`<root>/index.jsonl`, so we keep a complete fetch history without duplicating bytes.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class ArchiveEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: str = "GET"
    url: str
    final_url: str
    status: int
    content_type: str
    sha256: str
    size: int
    truncated: bool
    fetched_at: datetime


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class RawArchive:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.objects = root / "objects"
        self.index_path = root / "index.jsonl"

    def object_path(self, digest: str) -> Path:
        return self.objects / digest[:2] / digest[2:]

    def put(
        self,
        *,
        url: str,
        final_url: str,
        status: int,
        content_type: str,
        body: bytes,
        truncated: bool,
        fetched_at: datetime,
        method: str = "GET",
    ) -> ArchiveEntry:
        digest = sha256_hex(body)
        path = self.object_path(digest)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(body)
            tmp.replace(path)
        entry = ArchiveEntry(
            method=method,
            url=url,
            final_url=final_url,
            status=status,
            content_type=content_type,
            sha256=digest,
            size=len(body),
            truncated=truncated,
            fetched_at=fetched_at,
        )
        self.root.mkdir(parents=True, exist_ok=True)
        with self.index_path.open("a", encoding="utf-8") as fh:
            fh.write(entry.model_dump_json() + "\n")
        return entry

    def get(self, digest: str) -> bytes:
        return self.object_path(digest).read_bytes()

    def entries(self) -> Iterator[ArchiveEntry]:
        if not self.index_path.exists():
            return
        with self.index_path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield ArchiveEntry.model_validate(json.loads(line))
