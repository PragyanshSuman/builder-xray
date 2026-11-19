"""Uttar Pradesh RERA (up-rera.in), Tier A. Field meanings: docs/coverage.md.

Pages used (all public, no login, robots.txt allows):
- `GET /projects`: every registered project in one table (≈15 MB).
- `GET /Projectsummary?...`: one project's details (link from the list).

Personal contact details shown on detail pages (mobile numbers, emails) are
never read into these models. A promoter's address is kept only for
non-individual applicants (companies, LLPs, firms), for entity resolution.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel, ConfigDict

from bxr.core.parsing import clean_text, parse_dmy, parse_leading_int, trailing_parenthetical

log = logging.getLogger(__name__)

STATE_CODE = "UP"
BASE_URL = "https://up-rera.in/"
LIST_URL = "https://up-rera.in/projects"
LIST_MAX_BYTES = 40_000_000  # the list page is ~15 MB; leave headroom

_QPR_FLAG = re.compile(r"\s*\(\s*Default on QPR\s*\)\s*", re.IGNORECASE)
_LIST_HEADERS = [
    "S.No",
    "Promoter Name",
    "Project Name",
    "RERA Reg.No.",
    "ProjectType",
    "District",
    "StartDate",
    "EndDate",
    "Registration Date",
    "Details",
]
_INDIVIDUAL_TYPES = re.compile(r"individual|proprietor", re.IGNORECASE)


REGISTERED_PROJECTS_TARGET = "ctl00$ContentPlaceHolder1$lnkRegisteredProjects"


class ListStructureError(RuntimeError):
    """The list page no longer looks like it did when the parser was written."""


def build_postback(home_html: str, page_url: str, event_target: str) -> tuple[str, dict[str, str]]:
    """Form submission a browser makes when a `__doPostBack(event_target)` link is clicked.

    Returns (action_url, fields). Raises ListStructureError if the link or form is missing.
    """
    if event_target not in home_html:
        raise ListStructureError(f"postback link {event_target!r} not found on home page")
    soup = BeautifulSoup(home_html, "html.parser")
    form = soup.find("form")
    if not isinstance(form, Tag):
        raise ListStructureError("no form on home page")
    fields = {
        str(i["name"]): str(i.get("value", ""))
        for i in form.find_all("input", attrs={"type": "hidden"})
        if i.get("name")
    }
    if "__VIEWSTATE" not in fields:
        raise ListStructureError("home page form has no __VIEWSTATE")
    fields["__EVENTTARGET"] = event_target
    fields["__EVENTARGUMENT"] = ""
    action = urljoin(page_url, str(form.get("action") or ""))
    return action, fields


def is_error_page(url: str) -> bool:
    return "servermaintenance" in url.lower() or "aspxerrorpath" in url.lower()


class UpListRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    rera_reg_no: str
    promoter_name: str | None
    project_name: str | None
    qpr_default_flag: bool  # portal appends "(Default on QPR)" to the name
    project_type: str | None
    district: str | None
    start_date: date | None
    end_date: date | None  # current completion date (after extensions)
    registered_on: date | None
    detail_url: str | None

    def content_hash(self) -> str:
        """Changes when any listed fact changes (detail_url excluded: it may rotate)."""
        payload = self.model_dump_json(exclude={"detail_url"})
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


class Extension(BaseModel):
    model_config = ConfigDict(frozen=True)

    seq: int | None
    from_date: date | None
    upto_date: date | None
    reason: str | None


class UpProjectDetail(BaseModel):
    model_config = ConfigDict(frozen=True)

    rera_reg_no: str | None
    project_name: str | None
    registered_on: date | None
    registration_kind: str | None  # "New" / "Ongoing" as shown ("Project Type")
    proposed_period_months: int | None
    proposed_start: date | None
    declared_completion: date | None  # original completion date
    extensions: list[Extension]
    state: str | None
    district: str | None
    tehsil: str | None
    promoter_name: str | None
    applicant_type: str | None
    promoter_address: str | None  # only for non-individual applicants
    promoter_project_count: int | None
    promoter_complaints: int | None
    project_complaints: int | None


# ---------------------------------------------------------------- list page
def _cell_text(td: Tag) -> str | None:
    return clean_text(td.get_text(" ", strip=True))


def parse_project_list(html: str, base_url: str = LIST_URL) -> list[UpListRow]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id=re.compile("grdPojDetail")) or soup.find("table")
    if not isinstance(table, Tag):
        raise ListStructureError("no project table found")
    rows = table.find_all("tr")
    if not rows:
        raise ListStructureError("project table has no rows")
    headers = [clean_text(c.get_text(" ", strip=True)) for c in rows[0].find_all(["th", "td"])]
    if headers != _LIST_HEADERS:
        raise ListStructureError(f"unexpected headers: {headers}")

    out: list[UpListRow] = []
    for tr in rows[1:]:
        tds = tr.find_all("td", recursive=False)
        if len(tds) != len(_LIST_HEADERS):
            continue
        reg = _cell_text(tds[3])
        if not reg:
            log.warning("list row without registration number skipped")
            continue
        raw_name = _cell_text(tds[2]) or ""
        flagged = bool(_QPR_FLAG.search(raw_name))
        name = clean_text(_QPR_FLAG.sub(" ", raw_name))
        anchor = tds[9].find("a", href=True)
        detail_url = None
        if isinstance(anchor, Tag):
            detail_url = urljoin(base_url, str(anchor["href"]))
        ctx = f"reg={reg}"
        out.append(
            UpListRow(
                rera_reg_no=reg,
                promoter_name=_cell_text(tds[1]),
                project_name=name,
                qpr_default_flag=flagged,
                project_type=_cell_text(tds[4]),
                district=_cell_text(tds[5]),
                start_date=parse_dmy(_cell_text(tds[6]), field="StartDate", context=ctx),
                end_date=parse_dmy(_cell_text(tds[7]), field="EndDate", context=ctx),
                registered_on=parse_dmy(_cell_text(tds[8]), field="RegistrationDate", context=ctx),
                detail_url=detail_url,
            )
        )
    if not out:
        raise ListStructureError("project table parsed to zero rows")
    return out


# -------------------------------------------------------------- detail page
_ID_PREFIX = "ctl00_ContentPlaceHolder1_"


def _by_id(soup: BeautifulSoup, suffix: str) -> str | None:
    el = soup.find(id=_ID_PREFIX + suffix)
    return clean_text(el.get_text(" ", strip=True)) if isinstance(el, Tag) else None


def _extensions(soup: BeautifulSoup, ctx: str) -> list[Extension]:
    table = soup.find(id=_ID_PREFIX + "grd_extension")
    if not isinstance(table, Tag):
        return []
    out: list[Extension] = []
    for tr in table.find_all("tr")[1:]:
        cells = [clean_text(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
        if len(cells) < 3:
            continue
        out.append(
            Extension(
                seq=parse_leading_int(cells[0], field="ext.seq", context=ctx),
                from_date=parse_dmy(cells[1], field="ext.from", context=ctx),
                upto_date=parse_dmy(cells[2], field="ext.upto", context=ctx),
                reason=trailing_parenthetical(cells[2]),
            )
        )
    return out


def parse_project_detail(html: str) -> UpProjectDetail:
    soup = BeautifulSoup(html, "html.parser")
    reg = _by_id(soup, "lblregno")
    ctx = f"reg={reg}"
    applicant_type = _by_id(soup, "LblAppicanttype")
    address = _by_id(soup, "Lbladdressapplicant")
    if applicant_type is None or _INDIVIDUAL_TYPES.search(applicant_type):
        address = None
    return UpProjectDetail(
        rera_reg_no=reg,
        project_name=_by_id(soup, "lblprojectname"),
        registered_on=parse_dmy(_by_id(soup, "prjregdate"), field="prjregdate", context=ctx),
        registration_kind=_by_id(soup, "prj_type"),
        proposed_period_months=parse_leading_int(
            _by_id(soup, "Lblpropeseperoid"), field="period", context=ctx
        ),
        proposed_start=parse_dmy(_by_id(soup, "lblpropesedDatestart"), field="start", context=ctx),
        declared_completion=parse_dmy(
            _by_id(soup, "Lblproposedenddt"), field="declared_completion", context=ctx
        ),
        extensions=_extensions(soup, ctx),
        state=_by_id(soup, "lblState"),
        district=_by_id(soup, "lbldistrict"),
        tehsil=_by_id(soup, "lbltechsil"),
        promoter_name=_by_id(soup, "Lblpromotername"),
        applicant_type=applicant_type,
        promoter_address=address,
        promoter_project_count=parse_leading_int(
            _by_id(soup, "lbltotalproject"), field="promoter_projects", context=ctx
        ),
        promoter_complaints=parse_leading_int(
            _by_id(soup, "lbltotalcomplaint"), field="promoter_complaints", context=ctx
        ),
        project_complaints=parse_leading_int(
            _by_id(soup, "lblprojectwisecomplaint"), field="project_complaints", context=ctx
        ),
    )
