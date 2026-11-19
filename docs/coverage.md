# Source coverage

Per source: portal URL, robots.txt status, access method, tier, fields captured
(with the portal's meaning), known gaps, and whether CAPTCHA/blocking forced
"Index only".

| State / source | Tier | Status |
|---|---|---|
| Unified RERA portal (IN) | n/a | Inspected 2026-11-19: **no project-level data** (see below) |
| Maharashtra (MahaRERA) | A | Not started (M2) |
| Uttar Pradesh (UP-RERA) | A | Not started (M2) |

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
   - Not yet known: whether it hangs for browsers too (i.e. the endpoint is
     down) or only for non-browser clients. We will not disguise the client
     to find out.
3. A link to `dashboard.pmay-urban.gov.in/rera/login`, which is login-only. Off-limits.

**Page weight:** the home page is 21.4 MB, almost entirely an inline SVG map.
Never fetch it in automation; `stateRERA.html` (49 KB) has the directory.
