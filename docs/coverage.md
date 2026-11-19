# Source coverage

Per source: portal URL, robots.txt status, access method, tier, fields captured
(with the portal's meaning), known gaps, and whether CAPTCHA/blocking forced
"Index only".

| State / source | Tier | Status |
|---|---|---|
| Unified RERA portal (IN) | n/a | Inspected 2026-11-19: **no project-level data** (see below) |
| Maharashtra (MahaRERA) | A | robots.txt returns 403 → **paused, decision needed** |
| Uttar Pradesh (UP-RERA) | A | Inspected 2026-11-19: **crawlable**, see below |

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

## Uttar Pradesh: up-rera.in (inspected 2026-11-19)

Requests: 4 by hand (home, Registered Projects postback, one detail page) plus
the survey's 2. Fixtures: `fixtures/up/` (trimmed; phones/emails redacted).

**robots.txt:** `User-agent: *` / `Disallow: /cgi-bin/`, so everything else is allowed.
No CAPTCHA or login on the list or detail pages. Reachable from GitHub's US
runners too.

**Project list:** home page "Registered Projects" is an ASP.NET postback
(`__EVENTTARGET=ctl00$ContentPlaceHolder1$lnkRegisteredProjects`) that
302-redirects to `GET /projects`. That one page (15.5 MB, so it needs a raised body cap)
lists **3,864** projects in a single table, with no pagination:

| Column | Meaning (as shown) | Notes |
|---|---|---|
| Promoter Name | promoter legal name | |
| Project Name | project name | 701 names carry the suffix **"(Default on QPR)"**, the portal's own flag. Store it as a separate boolean; strip it from the name |
| RERA Reg.No. | registration number | unique; formats `UPRERAPRJ<digits>` and `UPRERAPRJ<digits>/<mm>/<yyyy>` |
| ProjectType | Residential / Commercial / Mixed | 3,146 / 612 / 106 |
| District | district | |
| StartDate | proposed start date | dd-mm-yyyy |
| EndDate | **current** completion date, after extensions | matches "Extension Upto" on the detail page (1 sample; confirm in the golden set) |
| Registration Date | date registered with UP-RERA | |
| Details | link `Projectsummary?<5 encrypted params>` | works without a session or cookies |

Other public lists on the home page (same postback mechanism, not yet fetched):
Completed Projects, De-registered, NCLT, Abeyance, NCLT u/s 8, Registered Promoters, Agents.

**Project detail (`Projectsummary`):** Project Registration Date; Proposed
Period (months); Proposed Start Date; **Declared Date Of Completion** (the
original completion date); **Extension Granted** table (Sno, From, Upto, reason
text); district/tehsil; promoter name and applicant type (e.g. Partnership
Firm); promoter's number of projects; **total complaints against the promoter**
and **complaints for this project** (counts); document list with download links.
Also shown: promoter mobile/email. **Not stored, never published.**

**Scale:** ~3,900 detail pages at 1 request / 3 s ≈ 3.3 h for a first full pass.
Spread it over nights; afterwards fetch only new projects or those whose list
row changed.

**Live crawl, 2026-11-19 (`bxr crawl-up --max-details 5`):** home → postback
→ list: 3,864 projects, 701 flagged; 5/5 detail pages parsed and reg-number
verified; 10 requests in 72 s. Plain `GET /projects` without the postback
session redirects to `servermaintenance.aspx`, so the crawler uses the browser flow.

**Note for validation (M2):** "Ongoing" projects (registration kind shown on
the detail page) were already under construction when RERA began, so their
declared completion can precede their RERA registration date (e.g.
UPRERAPRJ13276: registered 2017-09-29, declared completion 2016-08-30). The
"completion ≥ registration" rule must apply only to "New" projects.
