"""The User-Agent the crawler sends must match the one shown on the public crawler page."""

import re

import yaml

from bxr.config import REPO_ROOT


def _crawler_cfg() -> dict[str, object]:
    path = REPO_ROOT / "config" / "crawler.yaml"
    data: dict[str, object] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


def test_contact_url_is_real_https_page() -> None:
    url = str(_crawler_cfg()["contact_url"])
    assert url.startswith("https://")
    assert "example" not in url
    assert url.endswith("/about/crawler/")


def test_site_shows_the_same_user_agent() -> None:
    cfg = _crawler_cfg()
    expected = str(cfg["user_agent"]).format(contact_url=cfg["contact_url"])
    site_cfg = (REPO_ROOT / "site" / "src" / "config.ts").read_text(encoding="utf-8")
    match = re.search(r"CRAWLER_USER_AGENT\s*=\s*'([^']+)'", site_cfg)
    assert match, "CRAWLER_USER_AGENT not found in site/src/config.ts"
    assert match.group(1) == expected


def test_politeness_floor() -> None:
    cfg = _crawler_cfg()
    assert float(str(cfg["min_interval_seconds"])) >= 3.0
    assert cfg["max_concurrency_per_host"] == 1
    assert cfg["respect_robots_txt"] is True
