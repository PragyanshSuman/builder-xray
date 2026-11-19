# ADR-003: Crawl from a machine in India (owner's PC), everything else on GitHub/Cloudflare

- Status: accepted (owner chose option a, 2026-11-19)
- Date: 2026-11-19

## Context
A probe from a GitHub-hosted runner (US IP, 2026-11-19) reached only UP, TG and HR.
MH, KA, GJ, RJ, TN and PB timed out, though all of them answer from India
(docs/coverage.md). Indian government portals commonly drop foreign traffic.

## Decision
- **Crawling runs on the owner's Windows PC in India** via a Windows scheduled
  task (`scripts/register-crawl-task.ps1` → `scripts/crawl-local.ps1`), nightly
  at 01:30 IST, with "start when available" so a missed run happens at next boot.
- The crawl job pushes its outputs (raw-archive summary, parsed Parquet snapshot)
  to **GitHub Release assets**. Parsing, validation, scoring, export, site build
  and deploy stay in **GitHub Actions**; they never contact portals.
- We never use VPNs or proxies to appear to be in India. Crawling from a real
  Indian machine with the honest BuilderXRayBot User-Agent is ordinary access.
  Disguising location to get past geo-blocking would be working around a block
  (CLAUDE.md hard rule).
- Upgrade path: an Oracle Cloud "Always Free" VM in Mumbai/Hyderabad (₹0, 24/7)
  if PC availability becomes a problem. A self-hosted GitHub runner on the PC was
  rejected: on a public repo, fork PRs could execute code on the owner's machine.

## Consequences
- Data freshness depends on the PC being on. Nightly with catch-up is enough
  for RERA data, which changes on quarterly/weekly cycles.
- The crawl machine needs `gh` authenticated with permission to upload release
  assets on this repo (it already is).
- `crawl-*.yml` workflows from spec §10 become `build-deploy.yml` triggered by
  a new release, not by a schedule.
