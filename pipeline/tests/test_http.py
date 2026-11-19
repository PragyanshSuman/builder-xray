from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from bxr.config import CrawlerConfig, load_crawler_config
from bxr.core.archive import RawArchive
from bxr.core.http import CrawlAbortedError, CrawlDisabledError, Outcome, PoliteClient

ENV_ON = {"CRAWL_ENABLED": "1"}
Handler = Callable[[httpx.Request], httpx.Response]


class FakeTime:
    def __init__(self) -> None:
        self.t = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


def _cfg(**overrides: object) -> CrawlerConfig:
    base = load_crawler_config().model_dump()
    base.update(overrides)
    return CrawlerConfig.model_validate(base)


def _client(
    handler: Handler,
    ft: FakeTime,
    *,
    archive: RawArchive | None = None,
    log: list[httpx.Request] | None = None,
    **cfg: object,
) -> PoliteClient:
    def wrapped(req: httpx.Request) -> httpx.Response:
        if log is not None:
            log.append(req)
        ft.t += 0.1  # each request takes 100 ms
        return handler(req)

    return PoliteClient(
        _cfg(**cfg),
        archive=archive,
        transport=httpx.MockTransport(wrapped),
        clock=ft.clock,
        sleep=ft.sleep,
        now=lambda: datetime(2026, 11, 19, tzinfo=UTC),
        env=ENV_ON,
    )


def _no_robots(req: httpx.Request) -> httpx.Response | None:
    if req.url.path == "/robots.txt":
        return httpx.Response(404)
    return None


def test_refuses_without_kill_switch() -> None:
    with pytest.raises(CrawlDisabledError):
        PoliteClient(load_crawler_config(), env={})


def test_config_floors_enforced() -> None:
    with pytest.raises(ValueError):
        _cfg(min_interval_seconds=1.0)
    with pytest.raises(ValueError):
        _cfg(max_concurrency_per_host=2)


def test_sends_user_agent_and_rate_limits_per_host() -> None:
    ft = FakeTime()
    log: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        return _no_robots(req) or httpx.Response(200, text="ok")

    with _client(handler, ft, log=log) as c:
        assert c.get("https://a.gov.in/1").ok
        t_first = ft.t
        assert c.get("https://a.gov.in/2").ok
        assert c.get("https://b.gov.in/1").ok  # other host: robots + page, no wait for a.gov.in

    assert all(r.headers["user-agent"].startswith("BuilderXRayBot/") for r in log)
    assert [r.url.path for r in log] == ["/robots.txt", "/1", "/2", "/robots.txt", "/1"]
    # Second request to a.gov.in waited until 3 s after the previous request started.
    assert ft.sleeps and ft.sleeps[0] == pytest.approx(3.0 - 0.1)
    assert t_first < ft.t


def test_robots_disallow_blocks_without_fetching() -> None:
    ft = FakeTime()
    log: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
        return httpx.Response(200, text="ok")

    with _client(handler, ft, log=log) as c:
        r = c.get("https://a.gov.in/private/x")
        assert r.outcome is Outcome.DISALLOWED
        assert c.get("https://a.gov.in/public").ok
    assert [r.url.path for r in log] == ["/robots.txt", "/public"]


def test_robots_specific_agent_rule() -> None:
    ft = FakeTime()

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: BuilderXRayBot\nDisallow: /\n")
        return httpx.Response(200)

    with _client(handler, ft) as c:
        assert c.get("https://a.gov.in/").outcome is Outcome.DISALLOWED


@pytest.mark.parametrize(
    ("status", "allowed"), [(404, True), (410, True), (403, False), (503, False)]
)
def test_robots_status_handling(status: int, allowed: bool) -> None:
    ft = FakeTime()

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(status)
        return httpx.Response(200)

    with _client(handler, ft, max_attempts=1) as c:
        outcome = c.get("https://a.gov.in/page").outcome
    assert (outcome is Outcome.OK) is allowed
    if not allowed:
        assert outcome is Outcome.DISALLOWED


def test_robots_403_exception_only_for_listed_hosts() -> None:
    ft = FakeTime()

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(403)
        return httpx.Response(200)

    with _client(handler, ft, robots_unavailable_allowed_hosts=["ok.gov.in"]) as c:
        assert c.get("https://ok.gov.in/").outcome is Outcome.OK
        assert c.get("https://other.gov.in/").outcome is Outcome.DISALLOWED


def test_repo_exceptions_are_documented() -> None:
    cfg = load_crawler_config()
    assert "www.maharera.maharashtra.gov.in" in cfg.robots_unavailable_allowed_hosts
    assert cfg.legacy_tls_hosts == {"rera.mp.gov.in", "hira.wb.gov.in"}


def test_legacy_tls_client_only_for_listed_hosts() -> None:
    c = PoliteClient(load_crawler_config(), env=ENV_ON)
    try:
        assert c._client_for("https://rera.mp.gov.in/x") is c._http_legacy
        assert c._client_for("https://up-rera.in/x") is c._http
    finally:
        c.close()


def test_robots_crawl_delay_extends_interval() -> None:
    ft = FakeTime()

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nCrawl-delay: 10\n")
        return httpx.Response(200)

    with _client(handler, ft) as c:
        c.get("https://a.gov.in/1")
        c.get("https://a.gov.in/2")
    assert max(ft.sleeps) == pytest.approx(10 - 0.1)


def test_retries_5xx_with_backoff_then_succeeds() -> None:
    ft = FakeTime()
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if r := _no_robots(req):
            return r
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200, text="ok")

    with _client(handler, ft) as c:
        r = c.get("https://a.gov.in/x")
    assert r.ok and r.attempts == 3
    assert 5.0 in ft.sleeps and 10.0 in ft.sleeps  # base 5 s, doubled


def test_retry_after_honoured_and_capped() -> None:
    ft = FakeTime()
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if r := _no_robots(req):
            return r
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "99999"})
        return httpx.Response(200)

    with _client(handler, ft) as c:
        assert c.get("https://a.gov.in/x").ok
    assert 600.0 in ft.sleeps  # capped at backoff_max_seconds


def test_network_error_reported_not_raised() -> None:
    ft = FakeTime()

    def handler(req: httpx.Request) -> httpx.Response:
        if r := _no_robots(req):
            return r
        raise httpx.ReadTimeout("slow", request=req)

    with _client(handler, ft, max_attempts=2) as c:
        r = c.get("https://a.gov.in/x")
    assert r.outcome is Outcome.NETWORK_ERROR
    assert r.error and "ReadTimeout" in r.error


def test_aborts_after_consecutive_errors() -> None:
    ft = FakeTime()

    def handler(req: httpx.Request) -> httpx.Response:
        return _no_robots(req) or httpx.Response(500)

    with _client(handler, ft, max_attempts=1, max_consecutive_errors=3) as c:
        for i in range(3):
            assert c.get(f"https://a.gov.in/{i}").outcome is Outcome.SERVER_ERROR
        with pytest.raises(CrawlAbortedError):
            c.get("https://a.gov.in/again")


def test_404_resets_error_streak() -> None:
    ft = FakeTime()

    def handler(req: httpx.Request) -> httpx.Response:
        if r := _no_robots(req):
            return r
        return httpx.Response(404 if req.url.path == "/missing" else 500)

    with _client(handler, ft, max_attempts=1, max_consecutive_errors=2) as c:
        c.get("https://a.gov.in/1")
        assert c.get("https://a.gov.in/missing").outcome is Outcome.CLIENT_ERROR
        c.get("https://a.gov.in/2")  # streak is 1, not 2: no abort
        assert c.consecutive_errors == 1


def test_redirect_to_other_host_checks_its_robots() -> None:
    ft = FakeTime()
    log: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "a.gov.in":
            if req.url.path == "/robots.txt":
                return httpx.Response(404)
            return httpx.Response(302, headers={"Location": "https://b.gov.in/home"})
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        return httpx.Response(200)

    with _client(handler, ft, log=log) as c:
        r = c.get("https://a.gov.in/")
    assert r.outcome is Outcome.DISALLOWED
    assert r.final_url == "https://b.gov.in/home"
    assert "/home" not in [x.url.path for x in log if x.url.host == "b.gov.in"]


def test_conditional_get_and_304() -> None:
    ft = FakeTime()
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if r := _no_robots(req):
            return r
        seen.update({k: v for k, v in req.headers.items() if k.startswith("if-")})
        return httpx.Response(304)

    with _client(handler, ft) as c:
        r = c.get("https://a.gov.in/x", etag='"abc"', last_modified="Tue, 01 Jan 2026 00:00:00 GMT")
    assert r.outcome is Outcome.NOT_MODIFIED
    assert seen == {
        "if-none-match": '"abc"',
        "if-modified-since": "Tue, 01 Jan 2026 00:00:00 GMT",
    }


def test_body_truncated_at_cap(tmp_path: Path) -> None:
    ft = FakeTime()

    def handler(req: httpx.Request) -> httpx.Response:
        return _no_robots(req) or httpx.Response(200, content=b"x" * 5000)

    archive = RawArchive(tmp_path)
    with _client(handler, ft, archive=archive, max_body_bytes=1000) as c:
        r = c.get("https://a.gov.in/big")
    assert r.truncated and len(r.body) == 1000
    assert r.archived is not None and r.archived.truncated


def test_per_request_body_cap_override() -> None:
    ft = FakeTime()

    def handler(req: httpx.Request) -> httpx.Response:
        return _no_robots(req) or httpx.Response(200, content=b"x" * 5000)

    with _client(handler, ft, max_body_bytes=1000) as c:
        r = c.get("https://a.gov.in/big", max_body_bytes=10_000)
    assert not r.truncated and len(r.body) == 5000


def test_every_response_archived(tmp_path: Path) -> None:
    ft = FakeTime()

    def handler(req: httpx.Request) -> httpx.Response:
        return _no_robots(req) or httpx.Response(200, text="hello")

    archive = RawArchive(tmp_path)
    with _client(handler, ft, archive=archive) as c:
        r = c.get("https://a.gov.in/x")
    entries = list(archive.entries())
    assert [e.url for e in entries] == ["https://a.gov.in/robots.txt", "https://a.gov.in/x"]
    assert r.archived is not None
    assert archive.get(r.archived.sha256) == b"hello"


def test_post_form_redirect_becomes_get_and_is_archived(tmp_path: Path) -> None:
    ft = FakeTime()
    log: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if r := _no_robots(req):
            return r
        if req.method == "POST":
            assert b"a=1" in req.content
            return httpx.Response(302, headers={"Location": "/list"}, request=req)
        return httpx.Response(200, text="list", headers={"set-cookie": "s=1"})

    archive = RawArchive(tmp_path)
    with _client(handler, ft, archive=archive, log=log) as c:
        r = c.post_form("https://a.gov.in/", {"a": "1"})
    assert r.ok and r.final_url == "https://a.gov.in/list"
    assert [(x.method, x.url.path) for x in log] == [
        ("GET", "/robots.txt"),
        ("POST", "/"),
        ("GET", "/list"),
    ]
    assert [e.method for e in archive.entries()] == ["GET", "POST", "GET"]


def test_post_form_respects_robots() -> None:
    ft = FakeTime()

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        return httpx.Response(200)

    with _client(handler, ft) as c:
        assert c.post_form("https://a.gov.in/", {"a": "1"}).outcome is Outcome.DISALLOWED
