from pathlib import Path

import pytest

from bxr.adapters.unified_rera import StatePortal, parse_state_directory
from bxr.config import REPO_ROOT

FIXTURE = REPO_ROOT / "fixtures" / "in" / "stateRERA.html"


@pytest.fixture(scope="module")
def portals() -> list[StatePortal]:
    return parse_state_directory(Path(FIXTURE).read_text(encoding="utf-8"))


def _by(portals: list[StatePortal], code: str) -> StatePortal:
    return next(p for p in portals if p.state_code == code)


def test_all_36_states_and_uts_with_codes(portals: list[StatePortal]) -> None:
    assert len(portals) == 36
    assert [p.serial for p in portals] == list(range(1, 37))
    codes = [p.state_code for p in portals]
    assert None not in codes
    assert len(set(codes)) == 36


def test_known_portals(portals: list[StatePortal]) -> None:
    assert (
        _by(portals, "MH").portal_url == "https://maharera.maharashtra.gov.in/"
    )  # '#nolink' dropped
    assert _by(portals, "UP").portal_url == "https://up-rera.in"
    assert _by(portals, "HR").portal_url == "https://haryanarera.gov.in"
    assert _by(portals, "HR").note is None


def test_states_without_website(portals: list[StatePortal]) -> None:
    missing = sorted(p.state_code for p in portals if p.portal_url is None if p.state_code)
    assert missing == ["AR", "LA", "MN", "MZ", "NL", "SK"]
    assert _by(portals, "LA").note == "Website Not Setup"


def test_attached_uts(portals: list[StatePortal]) -> None:
    ld = _by(portals, "LD")
    assert ld.portal_url == "https://rera.kerala.gov.in/"
    assert ld.note == "Attached with Kerala RERA"
    assert _by(portals, "DH").note == "Attached with Maharashtra RERA"
