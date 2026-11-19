# Builder X-Ray

An independent website that turns India's public RERA records into a
source-linked **Delivery Track Record Score** for builders and projects.
Every number links to its official source and shows the date it was collected.

> Not a credit rating. Not legal or investment advice.

**Status:** M0 (foundations) complete. No data is collected or published yet.
Live: https://builder-xray.prags-codes.workers.dev/

| Path | What |
|---|---|
| [`pipeline/`](pipeline/) | Python 3.12 data pipeline (`bxr`): crawl, parse, validate, score, export |
| [`site/`](site/) | Astro static site (zero client JS on content pages) |
| [`worker/`](worker/) | Cloudflare Worker serving the site and, later, long-tail pages and payments |
| [`config/`](config/) | Free-tier limits and crawler identity |
| [`docs/`](docs/) | [Spec](docs/spec.md), [limits](docs/limits.md), [runbook](docs/runbook.md), [ADRs](docs/adr/) |

Quick start: see [docs/runbook.md](docs/runbook.md). Project rules for
contributors and AI agents: [CLAUDE.md](CLAUDE.md).
