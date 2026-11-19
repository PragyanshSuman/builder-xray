"""Small, strict parsing helpers. Unparseable input → None (and a log line), never a guess."""

from __future__ import annotations

import logging
import re
from datetime import date

log = logging.getLogger(__name__)

_DMY = re.compile(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})")
_INT = re.compile(r"-?\d+")


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


def parse_dmy(value: str | None, *, field: str = "", context: str = "") -> date | None:
    """Parse the first dd-mm-yyyy (or dd/mm/yyyy, dd.mm.yyyy) date in `value`."""
    text = clean_text(value)
    if text is None:
        return None
    m = _DMY.search(text)
    if not m:
        log.warning("unparseable date %r field=%s %s", text, field, context)
        return None
    day, month, year = (int(g) for g in m.groups())
    try:
        return date(year, month, day)
    except ValueError:
        log.warning("invalid date %r field=%s %s", text, field, context)
        return None


def parse_leading_int(value: str | None, *, field: str = "", context: str = "") -> int | None:
    """Parse the first integer in `value` (e.g. '0 (Under Registration - 0 )' → 0)."""
    text = clean_text(value)
    if text is None:
        return None
    m = _INT.search(text)
    if not m:
        log.warning("unparseable int %r field=%s %s", text, field, context)
        return None
    return int(m.group(0))


def trailing_parenthetical(value: str | None) -> str | None:
    """'09-09-2024 (Six months extension ...)' → 'Six months extension ...'."""
    text = clean_text(value)
    if text is None:
        return None
    m = re.search(r"\((.*)\)\s*$", text)
    return clean_text(m.group(1)) if m else None
