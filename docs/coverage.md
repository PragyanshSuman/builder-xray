# Source coverage

Per source: portal URL, robots.txt status, access method, tier, fields captured
(with the portal's meaning), known gaps, and whether CAPTCHA/blocking forced
"Index only".

| State / source | Tier | Status |
|---|---|---|
| Unified RERA portal (IN) | n/a | Inspected 2026-11-19: **no project-level data** (see below) |
| Maharashtra (MahaRERA) | A | robots.txt returns 403 → **paused, decision needed** |
| Uttar Pradesh (UP-RERA) | A | Reachable, robots.txt allows home → next: manual inspection (M2) |

## State portal survey, 2026-11-19

Full table: `docs/portal-survey.md` (generated). 59 requests, 26 distinct
portals, home page + robots.txt only.

| Class | States/UTs | Meaning |
|---|---|---|
| Reachable, no barrier on home page | BR, CG, GA, GJ, HR, HP, KA, OD, PB, RJ, TN (+AN), TG, UP, AS, TR, JK, PY | Candidates; each still needs a manual look at its project search pages |
| Reachable, CAPTCHA marker on home page | AP | Likely CAPTCHA on search, so probably not crawlable; confirm manually |
| **Bot-protection challenge** | KL (+LD) | Home returns 503 with a Prophaze JavaScript cookie challenge. **Not covered; we do not bypass it** (hard rule) |
| **robots.txt disallows all** | ML | `User-agent: * / Disallow: /`. **Not covered** |
| robots.txt 403 | MH (+DH) | Plain Apache "403 Forbidden" on `/robots.txt`. Home page not fetched (client treats 401/403 as disallow). Needs a decision |
| Old TLS (legacy renegotiation) | MP, WB | Our TLS library refuses the server's outdated handshake. A client compatibility issue, not access control |
| Unreachable (timeout) | UK, DL (+CH) | Retry later. May be down, or may block some networks |
| Directory URL dead | JH | `rera.jharkhand.gov.in` has no DNS; the same directory's annual-report link uses `jharera.jharkhand.gov.in`. Retry there |
| No website | AR, MN, MZ, NL, SK, LA | Listed "Website Not Setup" by MoHUA |

### Follow-up checks, 2026-11-19
- **MH:** `/robots.txt` → 403 on both `maharera.maharashtra.gov.in` and
  `www.maharera.maharashtra.gov.in`; home → 301 → `https://www.maharera.maharashtra.gov.in/`
  → 200 (65 KB) for BuilderXRayBot, no CAPTCHA or login. Public project search
  at `/projects-search-result`. Added as a documented exception in
  `config/crawler.yaml` (RFC 9309: unavailable robots.txt means no restrictions).
- **JH:** `jharera.jharkhand.gov.in/robots.txt` → 404 (allowed); home page →
  connection reset. Retry later.
- **UK, DL:** still no TCP connection on port 443 from India.

### Reachability from GitHub-hosted runners (US), 2026-11-19
Probe workflow `probe.yml`, one robots.txt request per host:

| Reachable from the US runner | Timed out (25 s) from the US runner, though reachable from India |
|---|---|
| UP (both hosts), TG, HR | KA, GJ, RJ, **MH**, TN, PB |

So scheduled crawls **cannot run on GitHub-hosted runners** for most
states, including Tier A Maharashtra. They need to run from a machine in India
(decision pending: ADR-003).

## Unified RERA portal: rera.mohua.gov.in (inspected 2026-11-19)

Requests made by hand: 6 total across 2 hosts, BuilderXRayBot User-Agent,
≥ 4 s apart. Fixtures: `fixtures/in/`.

**robots.txt:** none on either host (`rera.mohua.gov.in` → 404,
`dashboard.pmay-urban.gov.in` → returns its SPA HTML). No CAPTCHA, login wall
or bot challenge on any page fetched.

**What the portal is:** an informational site run by MoHUA (Ministry of
Housing and Urban Affairs): the Act, rules, notifications, Central Advisory
Council material, booklets. **It does not list or search individual
projects.** The spec assumed it could serve as a national per-project index
(Tier C). It can't.

**What it does have:**

1. `stateRERA.html`: a static table of **36 States/UTs** with each RERA
   website URL and annual-report link. Ladakh: "Website Not Setup";
   Lakshadweep: attached to Kerala RERA. Useful as the authoritative source
   directory.
2. `tracker.html` and the home page: per-State/UT **aggregate totals**: total
   projects, residential projects, residential units, carpet area, agents,
   complaints filed/disposed, and "as on date". These are loaded client-side from
   `GET https://dashboard.pmay-urban.gov.in/v1/rera/reraDetailsAllState`.
   - 2026-11-19: TCP connected in ~65 ms but **no response within 30 s or
     90 s** (2 attempts, 20 s apart). The same host answered `/robots.txt`
     instantly, so the server is reachable; this endpoint hangs.
   - 2026-11-19: the user opened `tracker.html` in a normal browser and the
     table stayed **empty**, so the endpoint is down for everyone. It is not
     blocking bots. It is OK to retry occasionally (a few requests at most per day).
3. A link to `dashboard.pmay-urban.gov.in/rera/login`, which is login-only. Off-limits.

**Page weight:** the home page is 21.4 MB, almost entirely an inline SVG map.
Never fetch it in automation; `stateRERA.html` (49 KB) has the directory.
