from pathlib import Path

import pytest
from pydantic import ValidationError

from bxr.config import LimitsConfig, Switch, is_enabled, load_limits


def test_repo_limits_file_loads() -> None:
    cfg = load_limits()
    assert cfg.stop_at_fraction == 0.5
    assert cfg.gates.max_static_files == 19000
    assert cfg.gates.max_static_files < cfg.limits["cf_static_files_per_version"]


def test_budget_applies_fraction() -> None:
    cfg = load_limits()
    assert cfg.budget("brevo_emails_per_day") == 150
    assert cfg.within_budget("brevo_emails_per_day", 149)
    assert not cfg.within_budget("brevo_emails_per_day", 150)


def test_unverified_limit_has_zero_budget() -> None:
    cfg = load_limits()
    assert cfg.limits["llm_requests_per_day"] == 0
    assert not cfg.within_budget("llm_requests_per_day", 0)


def test_unknown_keys_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "limits.yaml"
    bad.write_text(
        "verified_on: 2026-01-01\nstop_at_fraction: 0.5\nlimits: {}\n"
        "gates: {max_static_files: 1, worker_render_cpu_ms: 1}\ntypo: 1\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_limits(bad)


def test_fraction_must_be_at_most_one() -> None:
    with pytest.raises(ValidationError):
        LimitsConfig.model_validate(
            {
                "verified_on": "2026-01-01",
                "stop_at_fraction": 1.5,
                "limits": {},
                "gates": {"max_static_files": 1, "worker_render_cpu_ms": 1},
            }
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("true", True),
        (" TRUE ", True),
        ("yes", True),
        ("0", False),
        ("false", False),
        ("", False),
        ("nope", False),
    ],
)
def test_kill_switch_values(value: str, expected: bool) -> None:
    assert is_enabled(Switch.CRAWL, {"CRAWL_ENABLED": value}) is expected


def test_kill_switches_default_off() -> None:
    for switch in Switch:
        assert is_enabled(switch, {}) is False
