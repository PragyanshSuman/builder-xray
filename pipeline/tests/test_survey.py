from datetime import UTC, datetime

from bxr.adapters.unified_rera import StatePortal
from bxr.tools.survey import analyse_home, group_portals, render_markdown

HOME = """
<html><head><title>Example RERA (FAKE)</title></head><body>
<form><input type="hidden" name="__VIEWSTATE" value="x">
<input type="password" name="pw"><div class="g-recaptcha"></div></form>
<a href="/Projects/Search.aspx">Search Registered Projects</a>
<a href="/about">About us</a>
<a href="javascript:void(0)">Project (js)</a>
<a href="https://other.gov.in/project-list">Project list</a>
<p>Plenty of visible text so this is not mistaken for a JavaScript app shell.
Plenty of visible text so this is not mistaken for a JavaScript app shell.
Plenty of visible text so this is not mistaken for a JavaScript app shell.</p>
</body></html>
"""


def test_analyse_home_signals() -> None:
    s = analyse_home(HOME, "https://rera.example.gov.in/")
    assert s.title == "Example RERA (FAKE)"
    assert "g-recaptcha" in s.captcha_markers
    assert s.has_password_field
    assert s.aspnet_webforms
    assert not s.js_app_shell
    assert s.project_links == [
        ("Search Registered Projects", "https://rera.example.gov.in/Projects/Search.aspx"),
        ("Project list", "https://other.gov.in/project-list"),
    ]


def test_js_shell_detected() -> None:
    s = analyse_home(
        "<html><body><div id=root></div><script src=a.js></script></body></html>", "https://x/"
    )
    assert s.js_app_shell
    assert s.captcha_markers == []


def _p(serial: int, code: str, url: str | None, note: str | None = None) -> StatePortal:
    return StatePortal(serial=serial, name=code, state_code=code, portal_url=url, note=note)


def test_group_shared_portals() -> None:
    groups = group_portals(
        [
            _p(1, "KL", "https://rera.kerala.gov.in"),
            _p(2, "LD", "https://rera.kerala.gov.in/", "Attached with Kerala RERA"),
            _p(3, "DL", "https://rera.delhi.gov.in"),
            _p(4, "CH", "https://www.rera.delhi.gov.in/", "Attached with RERA for NCT of Delhi"),
            _p(5, "LA", None, "Website Not Setup"),
        ]
    )
    assert sorted(len(v) for v in groups.values()) == [2, 2]
    assert "rera.kerala.gov.in" in groups


def test_render_markdown_lists_missing_sites() -> None:
    md = render_markdown(
        [], [_p(5, "LA", None, "Website Not Setup")], datetime(2026, 11, 19, tzinfo=UTC)
    )
    assert "LA" in md and "Website Not Setup" in md
