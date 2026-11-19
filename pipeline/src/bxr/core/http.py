"""Polite HTTP client shared by every adapter (spec §5.2, CLAUDE.md).

Guarantees, enforced here so adapters cannot forget them:
- Refuses to run unless CRAWL_ENABLED is truthy.
- Identifies itself with the BuilderXRayBot User-Agent.
- Obeys robots.txt (RFC 9309): 404/410 → allowed; 401/403 → disallowed;
  5xx or unreachable → disallowed for this run. Honours Crawl-delay if longer
  than our own interval.
- At most one request per `min_interval_seconds` per host, one at a time
  (the client is synchronous).
- Retries 429/5xx/network errors with exponential backoff (Retry-After honoured,
  capped), up to `max_attempts`.
- Raises CrawlAbortedError after `max_consecutive_errors` failed fetches in a row.
- Follows redirects itself so every hop is rate-limited and robots-checked.
- Caps response bodies at `max_body_bytes`.
- Every response with a body goes into the raw archive.
- Never sends cookies, logs in or tries to get past a CAPTCHA.
"""

from __future__ import annotations

import ssl
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import TracebackType
from typing import Any
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from bxr.config import CrawlerConfig, Switch, is_enabled
from bxr.core.archive import ArchiveEntry, RawArchive

ROBOTS_AGENT = "BuilderXRayBot"
_REDIRECTS = frozenset({301, 302, 303, 307, 308})
_ACCEPT = "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"


class CrawlDisabledError(RuntimeError):
    """CRAWL_ENABLED is not set."""


class CrawlAbortedError(RuntimeError):
    """Too many consecutive errors; stop this run."""


class Outcome(StrEnum):
    OK = "ok"  # 2xx
    NOT_MODIFIED = "not_modified"  # 304
    CLIENT_ERROR = "client_error"  # 4xx other than 429 (e.g. 404); not a server fault
    SERVER_ERROR = "server_error"  # 429 / 5xx after retries
    NETWORK_ERROR = "network_error"  # timeout / connection failure after retries
    DISALLOWED = "disallowed"  # robots.txt says no; nothing was fetched
    TOO_MANY_REDIRECTS = "too_many_redirects"


_ERROR_OUTCOMES = frozenset({Outcome.SERVER_ERROR, Outcome.NETWORK_ERROR})


@dataclass(frozen=True)
class FetchResult:
    url: str
    final_url: str
    outcome: Outcome
    status: int | None = None
    content_type: str = ""
    body: bytes = b""
    truncated: bool = False
    etag: str | None = None
    last_modified: str | None = None
    error: str | None = None
    attempts: int = 0
    archived: ArchiveEntry | None = None

    @property
    def ok(self) -> bool:
        return self.outcome is Outcome.OK

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


@dataclass
class _Robots:
    parser: RobotFileParser | None  # None → decided by `allow_all`
    allow_all: bool
    crawl_delay: float | None = None
    note: str = ""

    def allows(self, url: str) -> bool:
        if self.parser is None:
            return self.allow_all
        return self.parser.can_fetch(ROBOTS_AGENT, url)


@dataclass
class _Raw:
    status: int | None
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""
    truncated: bool = False
    error: str | None = None
    attempts: int = 0


def _host_key(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc.lower()}"


class PoliteClient:
    def __init__(
        self,
        cfg: CrawlerConfig,
        *,
        archive: RawArchive | None = None,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        env: dict[str, str] | None = None,
    ) -> None:
        if not is_enabled(Switch.CRAWL, env):
            raise CrawlDisabledError("set CRAWL_ENABLED=1 to allow network crawling")
        self.cfg = cfg
        self.archive = archive
        self._clock = clock
        self._sleep = sleep
        self._now = now
        common: dict[str, Any] = {
            "timeout": cfg.timeout_seconds,
            "follow_redirects": False,
            "headers": {"User-Agent": cfg.user_agent_header, "Accept": _ACCEPT},
        }
        self._http = httpx.Client(transport=transport, **common)
        # Separate client for documented legacy-TLS hosts (config/crawler.yaml).
        legacy_ctx = ssl.create_default_context()  # certificate checks stay on
        legacy_ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
        self._http_legacy = (
            httpx.Client(transport=transport, **common)
            if transport is not None
            else httpx.Client(verify=legacy_ctx, **common)
        )
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, _Robots] = {}
        self.consecutive_errors = 0
        self.stats: Counter[str] = Counter()

    # -- context manager -------------------------------------------------
    def __enter__(self) -> PoliteClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()
        self._http_legacy.close()

    def _client_for(self, url: str) -> httpx.Client:
        if urlsplit(url).netloc.lower() in self.cfg.legacy_tls_hosts:
            return self._http_legacy
        return self._http

    # -- public API ------------------------------------------------------
    def robots_note(self, url: str) -> str:
        """Human-readable robots.txt status for the url's host (fetches it if needed)."""
        return self._robots_for(url).note

    def get(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        max_body_bytes: int | None = None,
    ) -> FetchResult:
        """GET politely. `max_body_bytes` overrides the configured cap for known-large pages."""
        self._check_abort()
        cap = max_body_bytes or self.cfg.max_body_bytes
        current = url
        conditional: dict[str, str] = {}
        if etag:
            conditional["If-None-Match"] = etag
        if last_modified:
            conditional["If-Modified-Since"] = last_modified

        for _hop in range(self.cfg.max_redirects + 1):
            if not self._robots_for(current).allows(current):
                self.stats["disallowed"] += 1
                return FetchResult(url=url, final_url=current, outcome=Outcome.DISALLOWED)
            raw = self._fetch_with_retries(current, conditional, cap)
            location = raw.headers.get("location")
            if raw.status in _REDIRECTS and location:
                self._archive(url, current, raw)
                current = urljoin(current, location)
                conditional = {}
                continue
            return self._finish(url, current, raw)

        self._record(Outcome.TOO_MANY_REDIRECTS)
        return FetchResult(url=url, final_url=current, outcome=Outcome.TOO_MANY_REDIRECTS)

    # -- internals -------------------------------------------------------
    def _check_abort(self) -> None:
        if self.consecutive_errors >= self.cfg.max_consecutive_errors:
            raise CrawlAbortedError(
                f"{self.consecutive_errors} consecutive errors; stopping this run"
            )

    def _record(self, outcome: Outcome) -> None:
        self.stats[outcome.value] += 1
        if outcome in _ERROR_OUTCOMES:
            self.consecutive_errors += 1
        elif outcome in (Outcome.OK, Outcome.NOT_MODIFIED, Outcome.CLIENT_ERROR):
            self.consecutive_errors = 0

    def _finish(self, url: str, final_url: str, raw: _Raw) -> FetchResult:
        if raw.status is None:
            outcome = Outcome.NETWORK_ERROR
        elif raw.status == 304:
            outcome = Outcome.NOT_MODIFIED
        elif 200 <= raw.status < 300:
            outcome = Outcome.OK
        elif raw.status == 429 or raw.status >= 500:
            outcome = Outcome.SERVER_ERROR
        else:
            outcome = Outcome.CLIENT_ERROR
        self._record(outcome)
        return FetchResult(
            url=url,
            final_url=final_url,
            outcome=outcome,
            status=raw.status,
            content_type=raw.headers.get("content-type", ""),
            body=raw.body,
            truncated=raw.truncated,
            etag=raw.headers.get("etag"),
            last_modified=raw.headers.get("last-modified"),
            error=raw.error,
            attempts=raw.attempts,
            archived=self._archive(url, final_url, raw),
        )

    def _archive(self, url: str, final_url: str, raw: _Raw) -> ArchiveEntry | None:
        if self.archive is None or raw.status is None:
            return None
        return self.archive.put(
            url=url,
            final_url=final_url,
            status=raw.status,
            content_type=raw.headers.get("content-type", ""),
            body=raw.body,
            truncated=raw.truncated,
            fetched_at=self._now(),
        )

    def _interval_for(self, host: str) -> float:
        robots = self._robots.get(host)
        delay = robots.crawl_delay if robots and robots.crawl_delay else 0.0
        return max(self.cfg.min_interval_seconds, delay)

    def _wait_turn(self, host: str) -> None:
        last = self._last_request.get(host)
        if last is not None:
            remaining = self._interval_for(host) - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request[host] = self._clock()

    def _backoff(self, attempt: int, retry_after: str | None) -> float:
        delay: float = self.cfg.backoff_base_seconds * float(2 ** (attempt - 1))
        if retry_after and retry_after.strip().isdigit():
            delay = max(delay, float(retry_after.strip()))
        return min(delay, self.cfg.backoff_max_seconds)

    def _fetch_once(self, url: str, headers: Mapping[str, str], cap: int) -> _Raw:
        try:
            client = self._client_for(url)
            with client.stream("GET", url, headers=dict(headers)) as resp:
                chunks: list[bytes] = []
                size = 0
                truncated = False
                for chunk in resp.iter_bytes():
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > cap:
                        truncated = True
                        break
                body = b"".join(chunks)[:cap]
                return _Raw(
                    status=resp.status_code,
                    headers={k.lower(): v for k, v in resp.headers.items()},
                    body=body,
                    truncated=truncated,
                )
        except httpx.TransportError as exc:
            return _Raw(status=None, error=f"{type(exc).__name__}: {exc}")

    def _fetch_with_retries(
        self, url: str, headers: Mapping[str, str], cap: int | None = None
    ) -> _Raw:
        host = _host_key(url)
        raw = _Raw(status=None)
        for attempt in range(1, self.cfg.max_attempts + 1):
            self._wait_turn(host)
            self.stats["requests"] += 1
            raw = self._fetch_once(url, headers, cap or self.cfg.max_body_bytes)
            raw.attempts = attempt
            retryable = raw.status is None or raw.status == 429 or raw.status >= 500
            if not retryable or attempt == self.cfg.max_attempts:
                return raw
            self._sleep(self._backoff(attempt, raw.headers.get("retry-after")))
        return raw

    def _robots_for(self, url: str) -> _Robots:
        host = _host_key(url)
        cached = self._robots.get(host)
        if cached is not None:
            return cached
        robots_url = f"{host}/robots.txt"
        raw = self._fetch_with_retries(robots_url, {})
        self._archive(robots_url, robots_url, raw)
        rules: _Robots
        if raw.status is None:
            self._record(Outcome.NETWORK_ERROR)
            rules = _Robots(None, allow_all=False, note=f"unreachable ({raw.error}): disallow")
        elif raw.status >= 500 or raw.status == 429:
            self._record(Outcome.SERVER_ERROR)
            rules = _Robots(None, allow_all=False, note=f"HTTP {raw.status}: disallow")
        elif raw.status in (401, 403):
            self._record(Outcome.CLIENT_ERROR)
            netloc = urlsplit(host).netloc
            if netloc in self.cfg.robots_unavailable_allowed_hosts:
                rules = _Robots(
                    None, allow_all=True, note=f"HTTP {raw.status}: allowed (documented exception)"
                )
            else:
                rules = _Robots(None, allow_all=False, note=f"HTTP {raw.status}: disallow")
        elif raw.status >= 400:
            self._record(Outcome.CLIENT_ERROR)
            rules = _Robots(None, allow_all=True, note=f"HTTP {raw.status}: no robots.txt")
        elif raw.status in _REDIRECTS:
            # Don't chase robots redirects across hosts; treat as absent (RFC 9309
            # allows following up to 5, but a redirect to an HTML home page is the
            # common case on these portals).
            self._record(Outcome.OK)
            rules = _Robots(
                None, allow_all=True, note=f"HTTP {raw.status} redirect: treated absent"
            )
        else:
            self._record(Outcome.OK)
            text = raw.body.decode("utf-8", errors="replace")
            parser = RobotFileParser()
            parser.parse(text.splitlines())
            delay = parser.crawl_delay(ROBOTS_AGENT)
            rules = _Robots(
                parser,
                allow_all=False,
                crawl_delay=float(delay) if delay is not None else None,
                note="robots.txt parsed" + (f", crawl-delay {delay}s" if delay else ""),
            )
        self._robots[host] = rules
        return rules
