"""Unified RERA portal (rera.mohua.gov.in), source code "IN".

The portal has no project-level data (docs/coverage.md). It is used for:
- the authoritative directory of State/UT RERA websites (`stateRERA.html`);
- per-state aggregate totals (dashboard API; currently down), added later.
"""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict

log = logging.getLogger(__name__)

DIRECTORY_URL = "https://rera.mohua.gov.in/stateRERA.html"

# Two-letter codes (vehicle-registration style, which RERA numbers commonly use).
STATE_CODES: dict[str, str] = {
    "andhra pradesh": "AP",
    "arunachal pradesh": "AR",
    "assam": "AS",
    "bihar": "BR",
    "chhattisgarh": "CG",
    "goa": "GA",
    "gujarat": "GJ",
    "haryana": "HR",
    "himachal pradesh": "HP",
    "jharkhand": "JH",
    "karnataka": "KA",
    "kerala": "KL",
    "madhya pradesh": "MP",
    "maharashtra": "MH",
    "manipur": "MN",
    "meghalaya": "ML",
    "mizoram": "MZ",
    "nagaland": "NL",
    "odisha": "OD",
    "punjab": "PB",
    "rajasthan": "RJ",
    "sikkim": "SK",
    "tamil nadu": "TN",
    "telangana": "TG",
    "tripura": "TR",
    "uttar pradesh": "UP",
    "uttarakhand": "UK",
    "west bengal": "WB",
    "andaman and nicobar islands": "AN",
    "andaman and nicobar": "AN",
    "chandigarh": "CH",
    "dadra and nagar haveli and daman and diu": "DH",
    "delhi": "DL",
    "jammu and kashmir": "JK",
    "ladakh": "LA",
    "lakshadweep": "LD",
    "puducherry": "PY",
}


class StatePortal(BaseModel):
    model_config = ConfigDict(frozen=True)

    serial: int
    name: str
    state_code: str | None
    portal_url: str | None  # None when the directory lists no website
    note: str | None  # e.g. "Website Not Setup", "Attached with Kerala RERA"
    source_url: str = DIRECTORY_URL


def _norm_name(name: str) -> str:
    name = name.lower().replace("&", " and ")
    name = re.sub(r"[^a-z ]+", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def _clean_url(href: str) -> str:
    return href.split("#", 1)[0].strip()


def parse_state_directory(html: str) -> list[StatePortal]:
    soup = BeautifulSoup(html, "html.parser")
    portals: list[StatePortal] = []
    for tr in soup.find_all("tr"):
        cells = tr.find_all("td", recursive=False)
        texts = [c.get_text(" ", strip=True) for c in cells]
        idx = next((i for i, t in enumerate(texts) if t.isdigit()), None)
        if idx is None or idx + 2 >= len(cells):
            continue
        name = texts[idx + 1]
        link_cell = cells[idx + 2]
        report_text = texts[idx + 3] if idx + 3 < len(texts) else ""
        anchor = link_cell.find("a", href=True)
        url = _clean_url(str(anchor["href"])) if anchor else None
        note: str | None = None
        if url is None:
            note = texts[idx + 2] or None
        elif "attached" in report_text.lower():
            note = report_text
        code = STATE_CODES.get(_norm_name(name))
        if code is None:
            log.warning("unknown State/UT name in directory: %r", name)
        portals.append(
            StatePortal(
                serial=int(texts[idx]),
                name=name,
                state_code=code,
                portal_url=url,
                note=note,
            )
        )
    return portals
