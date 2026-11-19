from datetime import date

import pytest

from bxr.adapters.uttar_pradesh import (
    ListStructureError,
    UpListRow,
    UpProjectDetail,
    parse_project_detail,
    parse_project_list,
)
from bxr.config import REPO_ROOT

FIX = REPO_ROOT / "fixtures" / "up"


@pytest.fixture(scope="module")
def rows() -> list[UpListRow]:
    html = (FIX / "projects_list.trimmed.html").read_text(encoding="utf-8")
    return parse_project_list(html)


@pytest.fixture(scope="module")
def detail() -> UpProjectDetail:
    html = (FIX / "project_detail_UPRERAPRJ839360.html").read_text(encoding="utf-8")
    return parse_project_detail(html)


# ---------------------------------------------------------------- list page
def test_list_row_count_and_unique_ids(rows: list[UpListRow]) -> None:
    assert len(rows) == 30
    assert len({r.rera_reg_no for r in rows}) == 30


def test_list_first_row_fields(rows: list[UpListRow]) -> None:
    r = rows[0]
    assert r.rera_reg_no == "UPRERAPRJ13276"
    assert r.promoter_name == "G R CONSTRUCTIONS"
    assert r.project_name == "PARK ROYAL APARTMENT"
    assert r.qpr_default_flag is False
    assert r.project_type == "Residential"
    assert r.district == "Lucknow"
    assert r.start_date == date(2013, 6, 1)
    assert r.end_date == date(2016, 8, 30)
    assert r.registered_on == date(2017, 9, 29)
    assert r.detail_url and r.detail_url.startswith("https://up-rera.in/Projectsummary?")


def test_qpr_flag_split_from_name(rows: list[UpListRow]) -> None:
    r = rows[1]
    assert r.rera_reg_no == "UPRERAPRJ1870"
    assert r.project_name == "MAHAGUN MANTRA II"
    assert r.qpr_default_flag is True
    assert r.promoter_name and r.promoter_name.startswith("HEBE INFRASTRUCTURE PRIVATE LIMITED")
    assert all("Default on QPR" not in (x.project_name or "") for x in rows)


def test_all_dates_parsed(rows: list[UpListRow]) -> None:
    assert all(r.start_date and r.end_date and r.registered_on for r in rows)


def test_content_hash_ignores_detail_url(rows: list[UpListRow]) -> None:
    r = rows[0]
    assert r.model_copy(update={"detail_url": "https://x/other"}).content_hash() == r.content_hash()
    assert r.model_copy(update={"district": "Agra"}).content_hash() != r.content_hash()


def test_list_structure_change_fails_loudly() -> None:
    with pytest.raises(ListStructureError):
        parse_project_list("<html><table><tr><th>Name</th></tr></table></html>")
    with pytest.raises(ListStructureError):
        parse_project_list("<html><body>maintenance</body></html>")


# -------------------------------------------------------------- detail page
def test_detail_core_fields(detail: UpProjectDetail) -> None:
    assert detail.rera_reg_no == "UPRERAPRJ839360"
    assert detail.project_name == "VAISHNO CRYSTAL"
    assert detail.registered_on == date(2019, 6, 11)
    assert detail.registration_kind == "New"
    assert detail.proposed_period_months == 60
    assert detail.proposed_start == date(2019, 3, 11)
    assert detail.declared_completion == date(2024, 3, 10)
    assert (detail.state, detail.district, detail.tehsil) == ("Uttar Pradesh", "Aligarh", "Koil")


def test_detail_extensions(detail: UpProjectDetail) -> None:
    assert len(detail.extensions) == 1
    ext = detail.extensions[0]
    assert ext.seq == 1
    assert ext.from_date == date(2024, 3, 10)
    assert ext.upto_date == date(2024, 9, 9)
    assert ext.reason and ext.reason.startswith("Six months extension")


def test_detail_promoter_and_counts(detail: UpProjectDetail) -> None:
    assert detail.promoter_name == "JADON INFRATECH"
    assert detail.applicant_type == "Partnership Firm"
    assert detail.promoter_address and "ALIGARH" in detail.promoter_address
    assert detail.promoter_project_count == 1
    assert detail.promoter_complaints == 0
    assert detail.project_complaints == 0


def test_detail_has_no_contact_fields(detail: UpProjectDetail) -> None:
    dumped = detail.model_dump_json().lower()
    assert "mobile" not in dumped and "email" not in dumped
    assert "@" not in dumped


def test_individual_promoter_address_dropped() -> None:
    html = (FIX / "project_detail_UPRERAPRJ839360.html").read_text(encoding="utf-8")
    html = html.replace(">Partnership Firm<", ">Individual<")
    assert parse_project_detail(html).promoter_address is None


def test_detail_end_date_matches_list_semantics(detail: UpProjectDetail) -> None:
    # List "EndDate" for this project is 09-09-2024 = last extension's upto date.
    assert detail.extensions[-1].upto_date == date(2024, 9, 9)


def test_build_postback_from_home() -> None:
    from bxr.adapters.uttar_pradesh import REGISTERED_PROJECTS_TARGET, build_postback

    html = (FIX / "home.html").read_text(encoding="utf-8")
    action, fields = build_postback(html, "https://up-rera.in/", REGISTERED_PROJECTS_TARGET)
    assert action == "https://up-rera.in/"
    assert fields["__EVENTTARGET"] == REGISTERED_PROJECTS_TARGET
    assert {"__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"} <= set(fields)


def test_error_page_detection() -> None:
    from bxr.adapters.uttar_pradesh import is_error_page

    assert is_error_page("https://up-rera.in/servermaintenance.aspx?aspxerrorpath=/projects")
    assert not is_error_page("https://up-rera.in/projects")
