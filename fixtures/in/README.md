# Fixtures: Unified RERA portal (rera.mohua.gov.in)

Collected 2026-11-19 by hand (one request each, BuilderXRayBot User-Agent, ≥ 4 s apart).

| File | Source URL | Notes |
|---|---|---|
| `home.stripped.html` | https://rera.mohua.gov.in/ | Original 21.4 MB; 40 inline SVG map `d=` attributes (21.35 MB) replaced with a stub. Nothing else changed. |
| `stateRERA.html` | https://rera.mohua.gov.in/stateRERA.html | Directory of 36 State/UT RERA websites and annual-report links. |
| `tracker.html` | https://rera.mohua.gov.in/tracker.html | Per-state totals table shell; rows are filled client-side from `https://dashboard.pmay-urban.gov.in/v1/rera/reraDetailsAllState` (timed out, see docs/coverage.md). |

`robots.txt` on both hosts: none (rera.mohua.gov.in → 404; dashboard.pmay-urban.gov.in → SPA HTML).
