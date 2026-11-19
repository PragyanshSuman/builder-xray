"""Source adapter contract (spec §5.1).

Models here are deliberately minimal for M0; they grow in M1/M2 alongside real
fixtures. Every parsed value must carry where it came from and when.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, HttpUrl

Tier = Literal["A", "B", "C"]


class ProjectRef(BaseModel):
    """Pointer to one project on a source portal (from a listing page)."""

    model_config = ConfigDict(frozen=True)

    state_code: str
    rera_reg_no: str
    detail_url: HttpUrl
    listing_updated_on: date | None = None


class RawDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: HttpUrl
    sha256: str
    status: int
    content_type: str
    fetched_at: datetime


class RawDocumentSet(BaseModel):
    model_config = ConfigDict(frozen=True)

    ref: ProjectRef
    documents: tuple[RawDocument, ...]


class ParsedProject(BaseModel):
    """Facts parsed from official records. Unknown → None, never guessed."""

    model_config = ConfigDict(frozen=True)

    rera_reg_no: str
    state_code: str
    name: str | None
    promoter_name: str | None
    registered_on: date | None
    original_completion: date | None
    current_completion: date | None
    source_url: HttpUrl
    collected_at: datetime


class SourceAdapter(Protocol):
    state_code: str  # "MH", "UP", or "IN" for the national portal
    tier: Tier

    def list_projects(self, since: date | None) -> Iterator[ProjectRef]: ...

    def fetch_project(self, ref: ProjectRef) -> RawDocumentSet: ...

    def parse(self, raw: RawDocumentSet) -> ParsedProject: ...
