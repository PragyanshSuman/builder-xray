"""Shared configuration: free-tier limits and kill switches.

Limits come from `config/limits.yaml` (sourced in docs/limits.md). Kill switches
are environment variables and default to OFF: a feature runs only when its
variable is explicitly set to a truthy value.
"""

from __future__ import annotations

import os
from datetime import date
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LIMITS_PATH = REPO_ROOT / "config" / "limits.yaml"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


class Switch(StrEnum):
    CRAWL = "CRAWL_ENABLED"
    LLM = "LLM_ENABLED"
    ALERTS = "ALERTS_ENABLED"
    PAYMENTS = "PAYMENTS_ENABLED"


def is_enabled(switch: Switch, env: dict[str, str] | None = None) -> bool:
    """True only if the switch's env var is explicitly truthy."""
    source = os.environ if env is None else env
    return source.get(switch.value, "").strip().lower() in _TRUTHY


class Gates(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_static_files: int = Field(gt=0)
    worker_render_cpu_ms: float = Field(gt=0)


class LimitsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    verified_on: date
    stop_at_fraction: float = Field(gt=0, le=1)
    limits: dict[str, int]
    gates: Gates

    def budget(self, name: str) -> int:
        """Usable allowance for a limit after applying `stop_at_fraction`.

        A limit of 0 means "not yet verified": the budget is 0, so callers stop.
        """
        return int(self.limits[name] * self.stop_at_fraction)

    def within_budget(self, name: str, used: int) -> bool:
        return used < self.budget(name)


def load_limits(path: Path = DEFAULT_LIMITS_PATH) -> LimitsConfig:
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return LimitsConfig.model_validate(raw)


DEFAULT_CRAWLER_PATH = REPO_ROOT / "config" / "crawler.yaml"
DATA_DIR = REPO_ROOT / "data"


class CrawlerConfig(BaseModel):
    """Politeness settings (spec §5.2). Floors are enforced by validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_agent: str
    contact_url: str
    min_interval_seconds: float = Field(ge=3.0)
    max_concurrency_per_host: int = Field(ge=1, le=1)
    max_consecutive_errors: int = Field(gt=0, le=20)
    backoff_base_seconds: float = Field(gt=0)
    backoff_max_seconds: float = Field(gt=0)
    respect_robots_txt: bool
    timeout_seconds: float = Field(gt=0, le=120)
    max_attempts: int = Field(ge=1, le=5)
    max_body_bytes: int = Field(gt=0)
    max_redirects: int = Field(ge=0, le=10)
    robots_unavailable_allowed_hosts: frozenset[str] = frozenset()
    legacy_tls_hosts: frozenset[str] = frozenset()

    @property
    def user_agent_header(self) -> str:
        return self.user_agent.format(contact_url=self.contact_url)


def load_crawler_config(path: Path = DEFAULT_CRAWLER_PATH) -> CrawlerConfig:
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    cfg = CrawlerConfig.model_validate(raw)
    if not cfg.respect_robots_txt:
        raise ValueError("respect_robots_txt must be true (CLAUDE.md hard rule)")
    return cfg
