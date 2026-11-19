# ADR-001: Foundation stack and M0 choices

- Status: accepted
- Date: 2026-11-19

## Context
The spec requires zero running cost, near-zero server load and a one-way
pipeline from public RERA records to static pages. The user asked me to adapt
details for convenience; hard rules (legal, cost, load) are unchanged.

## Decisions

1. **Public GitHub repo.** Standard Actions runners are free and unlimited for
   public repos; crawl jobs would quickly exhaust a private repo's allowance.
   No secrets or raw data are committed, so publishing the code is safe.
2. **One Worker serves both static assets and dynamic routes** (`worker/`, with
   `assets.directory = ../site/dist`). Asset hits never invoke the Worker, so they
   don't count toward the 100k requests/day quota. There's no separate Pages project.
3. **Python package `bxr` in `pipeline/src/bxr/`** (src layout, uv, hatchling).
   Subpackages match spec §4 (`adapters`, `core`, `extract`, ...). The CLI
   is `uv run bxr ...`.
4. **The file-count gate is in Python** (`bxr filecount`), so it is unit-tested
   with the rest of the pipeline and reads the gate from `config/limits.yaml`.
5. **The static file gate stays at 19,000, not 50% of 20,000.** The spec sets 19,000
   explicitly. Static files cost nothing per request; the 50% rule protects
   metered quotas (requests, D1, email, LLM).
6. **Kill switches default OFF.** A crawl/LLM/alert/payment step runs only
   if its env var is explicitly truthy. A missing variable is fail-safe.
7. **Unverified limits are 0** in `config/limits.yaml` (e.g. LLM until M2), so any
   code that checks the budget stops instead of guessing.
8. **Astro pinned to `~7.3.8`.** Astro ≥ 7.4.2 requires Node ≥ 22.23.4, and the
   dev machine has Node 22.20 (an nvm download of a newer 22.x failed). There are two
   moderate advisories on 7.3.x: XSS via dynamic tag names (we don't use dynamic
   tag names) and the `@astrojs/node` image endpoint (not installed). Neither
   applies to a static build. **Upgrade to Astro latest once Node ≥ 22.23.4 is
   installed locally** (tracked in runbook).
9. **Strict CSP from day one** (`site/public/_headers`): no inline scripts or
   styles (`inlineStylesheets: 'never'`), HSTS, frame-ancestors none.
10. **Snapshots go to R2 if a payment method is added to the Cloudflare account,
    otherwise to GitHub Release assets.** This is decided at M1 with the user.

## Consequences
- Deploys need two GitHub secrets: `CLOUDFLARE_API_TOKEN` (Workers Scripts:Edit
  only) and `CLOUDFLARE_ACCOUNT_ID`. Until they are set, the deploy workflow
  builds and gates but skips the upload with a warning.
