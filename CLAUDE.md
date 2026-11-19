# Builder X-Ray: project rules

Independent site that turns India's public RERA records into a source-linked
Delivery Track Record Score (0-100) for builders and projects. Read this file
before every session. Full product spec: `docs/spec.md`.

## Hard rules (never break, never "work around")

### Legal and ethical
- Collect only publicly accessible pages. Never log in, never bypass CAPTCHAs,
  rate limits or bot checks. Always honour robots.txt and site terms.
- Crawler identifies itself with a descriptive User-Agent and contact URL
  (`config/crawler.yaml`).
- If a portal blocks automated access or needs a CAPTCHA: mark that state
  "Index only" (Tier C from the Unified RERA portal) and **report it to the user**.
- Publish facts from official records only, each with `source_url` and
  `collected_at`. No reviews, no opinions, no words like "fraud" or "scam".
- Never display names of individual complainants. Counts and order outcomes only.
- Link to original PDFs; never rehost builders' documents.
- Every page footer: "Not a credit rating. Not legal or investment advice. Based
  on official RERA records as of {date}." plus Methodology, Corrections and
  Right of Reply links.
- **Never invent data.** Unparseable field → store `null` and log it. Unsure
  what a portal field means → ask the user.
- Never hard-code real scores or present sample data as real. Fixtures used in
  demos must be obviously fake (e.g. "Example Builders Pvt Ltd (FAKE)").

### Cost and load
- Running cost is ₹0. Allowed: GitHub (repo + Actions), Cloudflare free plan
  (Workers + static assets, D1, R2, Web Analytics, Turnstile), a free LLM tier
  (pluggable) or local Ollama, Brevo/Resend free tier, Telegram Bot API,
  Razorpay (per-transaction fees only). No Vercel free plan; nothing that bills
  by default.
- Every free-tier limit lives in `config/limits.yaml` (sourced in
  `docs/limits.md`). Code stops gracefully at 50% of any limit.
- Page views never hit a database or an LLM. Pages are pre-built HTML or
  rendered by the Worker from pre-built JSON, then cached.
- Deploy must stay ≤ 19,000 static files (`bxr filecount` fails the build).
- Worker render < 5 ms CPU (free cap is 10 ms). Precompute in the pipeline.
- Kill switches: `CRAWL_ENABLED`, `LLM_ENABLED`, `ALERTS_ENABLED`,
  `PAYMENTS_ENABLED` (default: off unless set to `1`/`true`).

### Crawling politeness
- ≤ 1 request / 3 s per host, 1 connection per host, exponential backoff on
  429/5xx, abort a run after 20 consecutive errors.
- Incremental only; full re-crawl of a state at most once per quarter, spread
  over days. Store raw responses in the content-addressed archive (sha256).
- No document is ever sent to an LLM twice (cache by sha256).

### Security
- Secrets only in GitHub Actions secrets / Worker secrets. Never in code, logs
  or fixtures. Least-privilege tokens.

## How to work
- Milestones M0-M6 (see `docs/spec.md` §12). Stop after each and report:
  what was built, how to run it, test results, free-tier usage, risks, next plan.
- When a portal behaves unexpectedly, blocks access, or a legal question
  arises: **stop and ask**.
- Record significant decisions in `docs/adr/NNN-title.md`.
- Small commits with clear messages. Keep `README.md` and `docs/runbook.md` current.

## Layout and commands
- `pipeline/` Python 3.12, uv. Package `bxr` in `pipeline/src/bxr/`.
  - `cd pipeline && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`
- `site/` Astro static output, zero client JS on content pages.
  Strings in `site/src/i18n/`, never hard-coded in templates.
  - `cd site && npm ci && npm run build`
- `worker/` Cloudflare Worker (TypeScript) serving `site/dist` as static assets.
  - `cd worker && npm ci && npm run typecheck && npx wrangler deploy`
- File-count gate: `cd pipeline && uv run bxr filecount ../site/dist`
- `config/` shared YAML config (limits, crawler identity).
- `data/` is gitignored local working data.
