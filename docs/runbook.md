# Runbook

## Local setup (Windows / macOS / Linux)

| Tool | Version | Install |
|---|---|---|
| Python | 3.12 | python.org or `uv python install 3.12` |
| uv | ≥ 0.5 | `pip install uv` (or the official installer) |
| Node | 22.x (≥ 22.12) | nvm |
| git, gh | any recent | |

```sh
# Pipeline
cd pipeline
uv sync
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
uv run bxr status            # limits + kill switches

# Site
cd site
npm ci
npm run build                # → site/dist
npm run dev                  # http://localhost:4321

# File-count gate
cd pipeline && uv run bxr filecount ../site/dist

# Worker (serves site/dist)
cd worker
npm ci
npm run typecheck
npx wrangler dev             # local preview of Worker + assets
```

## Crawling

All network access goes through `bxr.core.http.PoliteClient`, which refuses to
run unless `CRAWL_ENABLED=1`. Raw responses land in `data/raw/` (gitignored).

```sh
cd pipeline
CRAWL_ENABLED=1 uv run bxr survey            # all State/UT portals, ~2 requests each
CRAWL_ENABLED=1 uv run bxr survey --only MH,UP
```

Output: `data/survey/YYYY-MM-DD.json` and `docs/portal-survey.md`.

## First deploy (one-time, ~5 minutes)

1. Create a free Cloudflare account. No payment method is needed for Workers.
2. **Account ID:** Cloudflare dashboard → Workers & Pages → copy *Account ID*.
3. **API token:** My Profile → API Tokens → Create Token → template
   *Edit Cloudflare Workers*. Restrict *Account Resources* to your account and
   *Zone Resources* to "All zones from an account" (or none if offered). Set a
   1-year expiry.
4. **workers.dev subdomain:** Workers & Pages → pick a subdomain once.
5. GitHub repo → Settings → Secrets and variables → Actions → add
   `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`.
6. Push to `main` (or run the *Deploy* workflow manually). The site goes live at
   `https://builder-xray.<subdomain>.workers.dev/`.

## Kill switches

Set as GitHub Actions *variables* (not secrets) or Worker vars. Every switch defaults to OFF.

| Variable | Stops |
|---|---|
| `CRAWL_ENABLED` | all portal fetching |
| `LLM_ENABLED` | all LLM extraction calls |
| `ALERTS_ENABLED` | email / Telegram sends |
| `PAYMENTS_ENABLED` | checkout endpoints (Worker returns 503) |

## Known follow-ups
- Upgrade Astro to latest once local Node ≥ 22.23.4 (ADR-001 §8).
- Replace placeholder `contact_url` in `config/crawler.yaml` before M1 crawling.
- Set the real domain in `site/astro.config.mjs` (`site:`) at M4.
