# Builder X-Ray: product and engineering spec

Source of truth for scope. Copied from the original build brief (2026-11-19).
Decisions that refine or deviate from it are recorded in `docs/adr/`.

## 1. Product in one paragraph

A homebuyer searches a builder or project and sees: every project the builder
has registered in any state, original vs. revised completion dates, extensions,
construction progress from quarterly progress reports (QPRs), complaints/orders
counts, and a Trust Score where every number links to the official source page
and shows the date it was collected. Revenue: paid detailed reports (₹699),
"Buyer Plus" monitoring alerts (₹99/month), Pro subscriptions for agents/lawyers
(₹999/month), and a data API later. Builders cannot pay to change scores.

## 2. Non-negotiable constraints

### Cost
- Monthly running cost ₹0 at launch. Allowed: GitHub (repo + Actions),
  Cloudflare free plan (Workers with static assets, D1, R2 or GitHub Releases
  for snapshots, Web Analytics), a free LLM tier (pluggable provider), free
  email tier (Brevo or Resend), Telegram Bot API, Razorpay (per-transaction
  fees only).
- Do not use Vercel's free plan (non-commercial only) or any service that bills
  by default.
- Before using any free tier, check its current limits in the official docs and
  record them in `docs/limits.md`. Design to stay under 50% of each limit.

### Server load
- Page views never hit a database or call an LLM. All pages are pre-built HTML
  or rendered at the edge from pre-built JSON, then cached.
- Cloudflare free plan: max 20,000 static files per deployment, 100,000 Worker
  requests/day, 10 ms CPU per invocation. Static asset requests are free and
  unlimited. The build must fail if the deploy exceeds 19,000 files.
- Crawling is incremental and polite (§5). Heavy work runs only in GitHub Actions.

### Legal and ethical (hard rules)
- Collect only publicly accessible pages. Never log in, never bypass CAPTCHAs or
  rate limits, always honour robots.txt and site terms. Descriptive User-Agent
  with contact URL.
- If a state portal blocks automated access or requires CAPTCHA, do not work
  around it: mark that state "Index only" (from the national Unified RERA
  portal) and report it.
- Publish facts from official records only, each with source URL and
  collected-at date. No user reviews, no opinions, no adjectives like "fraud"
  or "scam".
- Never display names of individual complainants. Only counts and order outcomes.
- Link to original PDFs; do not rehost builders' documents.
- Every page footer: "Not a credit rating. Not legal or investment advice.
  Based on official RERA records as of {date}." Plus links to Methodology,
  Corrections and Right of Reply.
- Never invent data. Unparseable field → null + log. Unsure what a portal field
  means → ask.

## 3. Architecture

```
GitHub Actions (scheduled)                         Cloudflare (free)
┌──────────────────────────────────────────┐      ┌───────────────────────────────┐
│ discover → crawl → raw archive (hashes)  │      │ Static assets (≤19k files):   │
│ → parse (rules) → LLM extract (cached)   │      │  hubs, builder pages, top     │
│ → validate → entity resolution           │ ───▶ │  projects, JSON shards,       │
│ → score → Parquet snapshot (R2/Release)  │      │  search index shards          │
│ → export site data → Astro build → deploy│      │ Worker: renders long-tail     │
│ → diff → alerts (email/Telegram)         │      │  project pages from shards,   │
└──────────────────────────────────────────┘      │  payments API, watchlists     │
                                                   │ D1: users, watchlists, orders │
                                                   └───────────────────────────────┘
```

Data flows one way. The site never queries portals live.

## 4. Repository layout

```
/pipeline   Python 3.12, uv, ruff + mypy --strict, pytest (package: src/bxr)
  adapters/ core/ extract/ validate/ entities/ score/ export/ alerts/
/site       Astro (static output), zero client JS on content pages
/worker     Cloudflare Worker (TypeScript): long-tail rendering, payments, watchlists
/data       gitignored local working data (DuckDB, Parquet)
/fixtures   saved HTML/PDF samples per adapter for tests
/docs       methodology.md, limits.md, coverage.md, adr/, runbook.md
/config     limits.yaml, crawler.yaml
/.github/workflows  ci.yml, crawl-*.yml, build-deploy.yml, alerts.yml
```

## 5. Data pipeline

### 5.1 Source adapters

```python
class SourceAdapter(Protocol):
    state_code: str                      # "MH", "UP", "IN" for the national portal
    tier: Literal["A", "B", "C"]         # A full depth, B core, C index only
    def list_projects(self, since: date | None) -> Iterator[ProjectRef]: ...
    def fetch_project(self, ref: ProjectRef) -> RawDocumentSet: ...
    def parse(self, raw: RawDocumentSet) -> ParsedProject: ...
```

Order: (1) Unified RERA portal (`rera.mohua.gov.in`) → national index, Tier C
for all 35 states/UTs. (2) Maharashtra (MahaRERA) and Uttar Pradesh (UP-RERA)
→ Tier A. (3) Karnataka, Telangana, Haryana, Tamil Nadu, West Bengal, Gujarat
→ Tier B, then A.

Before each adapter: inspect the live portal manually (a few requests), save
10-20 representative pages to `/fixtures/<state>/`, document fields in
`docs/coverage.md`, write parser tests against fixtures first.

### 5.2 Polite crawling
- ≤ 1 request / 3 s per host (configurable), 1 concurrent connection per host,
  exponential backoff on 429/5xx, stop after 20 consecutive errors.
- Honour robots.txt (cached); send If-Modified-Since / ETag where supported.
- Incremental: fetch only new/changed detail pages. Full re-crawl at most once
  per quarter per state, spread over several days.
- Content-addressed raw archive (sha256) with URL, status, timestamp. Text over
  binaries where possible.

### 5.3 Extraction
- Rule-based HTML parsing first; LLM only for unstructured PDFs (QPRs, orders).
- Provider-agnostic `extract/llm.py`, strict pydantic JSON schema, temperature 0,
  source excerpt saved beside every extracted field.
- Cache by document hash: no document sent to an LLM twice. Token-bucket rate
  limiting. Local Ollama fallback.
- Golden set: 200 hand-verified projects. Field accuracy ≥ 98% before a state is
  published at Tier A.

### 5.4 Data model (Parquet, DuckDB)
- `builder_group(group_id, display_name, slug, created_at)`
- `promoter(promoter_id, group_id, legal_name, entity_type, cin_or_llpin, state_codes, match_confidence)`
- `project(project_id, rera_reg_no, state_code, promoter_id, name, district, city, pin, type, units_total, registered_on, original_completion, current_completion, completed_on, oc_uploaded, status, tier, source_url, collected_at)`
- `date_event(project_id, event_type{original|extension|revision|completion}, event_date, effective_from, source_url, collected_at)`
- `qpr(project_id, quarter, filed_on, progress_pct, source_url, collected_at)`
- `complaint_stat(project_id, complaints_count, orders_against_count, as_of, source_url)`
- `score(entity_type, entity_id, score, band, confidence, components_json, formula_version, computed_at)`
- Dated snapshots `snapshots/YYYY-MM-DD/*.parquet` to R2 (or GitHub Release
  assets). Never overwrite history.

### 5.5 Entity resolution
Group promoters by, in order: CIN/LLPIN, disclosed PAN fragments, shared
directors/partners (if public), registered address, normalised name similarity.
Auto-merge only on official identifiers; everything else → `review_queue.csv`.
Never merge on name alone.

### 5.6 Validation and change detection
Dates parse; completion ≥ registration; progress 0-100 and non-decreasing unless
explained; units > 0. Flag unusual jumps between snapshots; hold flagged
records from publishing until reviewed.

## 6. Trust Score v1.0 (exact, versioned)

| Component | Weight | Scaling |
|---|---|---|
| On-time delivery rate (completed by original date) | 30% | linear 0% → 0, 100% → 100 |
| Delay severity (median months beyond original date, completed + overdue ongoing) | 25% | 0 → 100, ≥36 → 0, linear |
| Construction pace (progress vs. time elapsed, ongoing) | 15% | ratio ≥1.0 → 100, ≤0.3 → 0 |
| Extension frequency (extensions per project) | 10% | 0 → 100, ≥3 → 0 |
| Disclosure discipline (QPRs filed on time) | 10% | share on time, linear |
| Complaints/orders per 100 registered units | 10% | 0 → 100, ≥10 → 0 |

Thresholds in `score/thresholds_v1.yaml`. Shrinkage per component:
`s_adj = (n*s + k*m) / (n + k)`, `k = 3`, `m` = state median.
Final = Σ weight × s_adj, rounded. Bands: 80-100 Strong documented record;
60-79 Mixed; 40-59 Weak; 0-39 Poor documented record. Confidence: High (≥5
completed), Medium (2-4), Low (1 or ongoing only). No score for builders with
no completed or overdue project. `docs/methodology.md` generates the public page.
Back-test: do low v1 scores predict more delay on later projects?

## 7. Website (Astro, static)

### 7.1 Pages
`/`, `/state/{state}/`, `/state/{state}/{district}/`, `/builder/{group}/`,
`/project/{state-code}/{rera-reg-slug}/`, `/compare/`, `/coverage/`,
`/methodology/`, `/corrections/`, `/right-of-reply/`, `/pricing/`, `/about/`,
`/privacy/`, `/terms/`, `/refunds/`.

### 7.2 Staying under 20,000 files
Pre-render home, hubs, builder pages and top N projects (N chosen so total ≤
19,000). Other projects: ~75 per JSON shard, `shard = hash(project_id) % SHARDS`.
Worker renders `/project/...` from the shard via the assets binding and caches
(`Cache-Control: public, s-maxage=604800, stale-while-revalidate=86400`).
Render < 5 ms CPU. Build prints file count and fails above 19,000.

### 7.3 SEO and performance
Unique titles/descriptions, canonicals, OG tags. JSON-LD: Organization, Place /
Residence, Dataset, BreadcrumbList, FAQPage (real FAQs only). Sitemaps ≤ 50,000
URLs each + index, including Worker-rendered URLs. Mobile 4G: LCP < 2.0 s,
CLS < 0.05, HTML < 60 KB gzipped, zero JS on content pages. WCAG 2.1 AA. Every
number links/tooltips to source + collected-at date. English first, i18n-ready.

### 7.4 Search
Prefix-sharded index (first two normalised letters → JSON, < 100 KB each),
ranked client-side with MiniSearch.

## 8. Paid features (Worker + D1)
Magic-link auth (signed, expiring tokens). Razorpay Orders API from the Worker;
verify checkout signature and webhook HMAC; idempotent orders in D1. Detailed
report rendered by the Worker with print CSS (browser Save as PDF). Buyer Plus /
Pro via Razorpay subscriptions, entitlements in D1. Watchlists in D1; alerts job
reads them via an authenticated endpoint, diffs snapshots, sends email/Telegram
in batches within limits. D1 tables: users, sessions, orders, entitlements,
watchlist_items, corrections. Rate-limit endpoints; Turnstile on forms.

## 9. Security and privacy
Secrets only in Actions/Worker secrets. Least-privilege tokens. Input
validation, CSP, HSTS, no inline scripts. Privacy notice, consent, account
deletion, retention policy (`docs/privacy.md`), grievance contact. Collect the
minimum: email, purchases, watchlist.

## 10. Testing and CI
Parser tests on fixtures; scoring incl. shrinkage edge cases; entity resolution;
shard routing. Golden-set evaluation blocks publishing if < 98%. Contract test
per adapter (opens a GitHub issue on structure change). Playwright smoke tests,
Lighthouse CI, link checker. Workflows: `ci.yml`, `crawl-<state>.yml`
(off-peak IST, staggered, concurrency groups), `build-deploy.yml`, `alerts.yml`.
Every workflow writes a run summary.

## 11. Cost and load guardrails (as code)
`config/limits.yaml`; pipeline tracks usage and stops at 50% of any daily limit,
resuming next run. Kill switches `CRAWL_ENABLED`, `LLM_ENABLED`,
`ALERTS_ENABLED`, `PAYMENTS_ENABLED`. Weekly usage report in the run summary.

## 12. Milestones (stop after each and report)
- **M0 Foundations:** CLAUDE.md, skeleton, tooling, CI, verified `docs/limits.md`.
  Accept: CI green, hello-world on `*.workers.dev`.
- **M1 National index:** Unified RERA adapter, polite client, raw archive,
  Tier C Parquet snapshot, per-state coverage. Accept: counts vs portal totals.
- **M2 MH + UP full depth:** adapters, fixtures, parsers, cached LLM QPR
  extraction, validation, golden set. Accept: ≥ 98% accuracy.
- **M3 Entities + Trust Score:** resolution + review queue, score v1.0,
  back-test, methodology. Accept: user reviews top 50 builders.
- **M4 Website:** hubs, pages, sharded long tail, search, compare, sitemaps,
  SEO, legal, coverage map. Accept: ≤ 19,000 files, Lighthouse ≥ 95 mobile,
  zero JS on content pages, every number sourced.
- **M5 Monetisation:** magic link, Razorpay test mode, report, Buyer Plus, Pro,
  watchlists, alerts, right of reply. Accept: e2e test purchase; simulated alert.
- **M6 Hardening + launch:** security review, policies, runbook, monitoring,
  Worker load test (< 5 ms CPU), D1 + snapshot restore drill.
  Accept: `docs/launch-checklist.md` fully ticked.
- **After launch:** Tier B states one at a time, MCA/IBBI enrichment, Hindi/Marathi.
