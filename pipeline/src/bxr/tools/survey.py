"""State portal survey: first look at every State/UT RERA website.

For each distinct portal: robots.txt status, home page reachability, and
signals that matter for crawling: CAPTCHA markers, password fields (login
walls), ASP.NET WebForms postbacks, and links that look like project
search/listing pages. This is two requests per host (robots.txt + home page),
all through PoliteClient.

Signals are heuristics on the home page only. A CAPTCHA often lives on the
search page, not the home page, so each state still needs a manual
inspection before an adapter is written.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict

from bxr.adapters.unified_rera import StatePortal
from bxr.core.http import FetchResult, PoliteClient

_CAPTCHA = re.compile(
    r"g-recaptcha|recaptcha|hcaptcha|cf-turnstile|challenge-platform|captcha|"
    r"just a moment\.\.\.|attention required",
    re.IGNORECASE,
)
_PROJECT_HINT = re.compile(r"project|registered|search", re.IGNORECASE)


class HomeSignals(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str | None
    captcha_markers: list[str]
    has_password_field: bool
    aspnet_webforms: bool
    js_app_shell: bool
    project_links: list[tuple[str, str]]


class PortalCheck(BaseModel):
    model_config = ConfigDict(frozen=True)

    state_codes: list[str]
    names: list[str]
    portal_url: str
    https: bool
    robots: str
    outcome: str
    status: int | None
    final_url: str
    bytes: int
    truncated: bool
    error: str | None
    signals: HomeSignals | None
    checked_at: datetime


def analyse_home(html: str, base_url: str) -> HomeSignals:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else None
    markers = sorted({m.group(0).lower() for m in _CAPTCHA.finditer(html)})
    has_password = soup.find("input", attrs={"type": re.compile("^password$", re.I)}) is not None
    webforms = soup.find("input", attrs={"name": "__VIEWSTATE"}) is not None
    body_text = soup.body.get_text(" ", strip=True) if soup.body else ""
    js_shell = len(body_text) < 200 and len(soup.find_all("script")) > 0
    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = str(a["href"]).strip()
        text = a.get_text(" ", strip=True)[:80]
        if href.startswith(("javascript:", "mailto:", "#")):
            continue
        if not (_PROJECT_HINT.search(text) or _PROJECT_HINT.search(href)):
            continue
        absolute = urljoin(base_url, href)
        if absolute in seen:
            continue
        seen.add(absolute)
        links.append((text, absolute))
        if len(links) >= 8:
            break
    return HomeSignals(
        title=title,
        captcha_markers=markers,
        has_password_field=has_password,
        aspnet_webforms=webforms,
        js_app_shell=js_shell,
        project_links=links,
    )


def _portal_key(url: str) -> str:
    parts = urlsplit(url)
    host = parts.netloc.lower().removeprefix("www.")
    return host + (parts.path.rstrip("/") or "")


def group_portals(portals: Iterable[StatePortal]) -> dict[str, list[StatePortal]]:
    """Group states that share one website (e.g. Lakshadweep → Kerala RERA)."""
    groups: dict[str, list[StatePortal]] = {}
    for p in portals:
        if p.portal_url:
            groups.setdefault(_portal_key(p.portal_url), []).append(p)
    return groups


def _check(
    client: PoliteClient, members: list[StatePortal], now: Callable[[], datetime]
) -> PortalCheck:
    # Prefer the state that owns the site (no "Attached with ..." note) for the URL.
    owner = next((m for m in members if not m.note), members[0])
    url = owner.portal_url or ""
    robots = client.robots_note(url)
    result: FetchResult = client.get(url)
    signals = None
    if result.ok and result.body:
        signals = analyse_home(result.text(), result.final_url)
    return PortalCheck(
        state_codes=[m.state_code or "?" for m in members],
        names=[m.name for m in members],
        portal_url=url,
        https=url.startswith("https://"),
        robots=robots,
        outcome=result.outcome.value,
        status=result.status,
        final_url=result.final_url,
        bytes=len(result.body),
        truncated=result.truncated,
        error=result.error,
        signals=signals,
        checked_at=now(),
    )


def run_survey(
    client: PoliteClient,
    portals: list[StatePortal],
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    progress: Callable[[str], None] = print,
) -> list[PortalCheck]:
    checks: list[PortalCheck] = []
    groups = group_portals(portals)
    for i, members in enumerate(groups.values(), start=1):
        check = _check(client, members, now)
        progress(
            f"[{i}/{len(groups)}] {','.join(check.state_codes)} {check.portal_url} → "
            f"{check.outcome} {check.status or ''} robots: {check.robots}"
        )
        checks.append(check)
    return checks


def render_markdown(checks: list[PortalCheck], no_site: list[StatePortal], when: datetime) -> str:
    lines = [
        "# State RERA portal survey",
        "",
        f"Run: {when:%Y-%m-%d %H:%M} UTC. Two requests per host (robots.txt + home page) "
        "via `PoliteClient`. Generated by `bxr survey`; do not edit by hand.",
        "",
        "Signals are home-page heuristics only. Each state still needs a manual look "
        "before an adapter is written (CAPTCHAs often sit on search pages).",
        "",
        "| State/UT | Portal | robots.txt | Home | CAPTCHA marker | Login field | "
        "WebForms | JS shell |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c in checks:
        s = c.signals
        home = f"{c.outcome} {c.status or ''}".strip()
        if c.truncated:
            home += " (truncated)"
        if not c.https:
            home += ", HTTP only"
        lines.append(
            "| {codes} | {url} | {robots} | {home} | {cap} | {pw} | {wf} | {js} |".format(
                codes=", ".join(c.state_codes),
                url=c.portal_url,
                robots=c.robots,
                home=home,
                cap=", ".join(s.captcha_markers) if s and s.captcha_markers else "-",
                pw="yes" if s and s.has_password_field else "-",
                wf="yes" if s and s.aspnet_webforms else "-",
                js="yes" if s and s.js_app_shell else "-",
            )
        )
    lines += ["", "## No website listed", ""]
    lines += [f"- {p.name} ({p.state_code}): {p.note}" for p in no_site] or ["- none"]
    lines += ["", "## Project-looking links on each home page", ""]
    for c in checks:
        if c.signals and c.signals.project_links:
            lines.append(f"**{', '.join(c.state_codes)}** ({c.portal_url})")
            lines += [
                f"- {text or '(no text)'}: <{href}>" for text, href in c.signals.project_links
            ]
            lines.append("")
    return "\n".join(lines) + "\n"
