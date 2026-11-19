# ADR-002: Build the national index from state portals, not the Unified RERA portal

- Status: accepted
- Date: 2026-11-19

## Context
Spec §5.1 assumed `rera.mohua.gov.in` could provide a per-project national
index (Tier C for every state). An inspection on 2026-11-19 (docs/coverage.md)
found it has **no project-level data**. It offers:
- a directory of 36 State/UT RERA websites (`stateRERA.html`), and
- per-state aggregate totals from `dashboard.pmay-urban.gov.in/v1/rera/reraDetailsAllState`,
  which was down for everyone on that date (confirmed by the user in a browser).

## Decision
1. The Unified RERA portal is source `IN`, used only for the **state portal
   directory** and, when the API responds, the **per-state totals** we compare
   our counts against.
2. Project records come from **each state's own portal**. "Tier C (index only)"
   now means: we list the state's projects from its public listing with
   minimal fields and link out, if its listing is publicly crawlable.
   If not, the state shows "Not covered" with a link to its portal.
3. Revised M1: (a) shared polite HTTP client and raw archive; (b) a survey of
   every state portal's robots.txt, reachability and access barriers
   (`bxr survey` → `docs/portal-survey.md`); (c) occasional retries of the
   totals API; (d) start Tier A states (MH, UP) as planned.
4. Six States/UTs have no RERA website (Arunachal Pradesh, Manipur, Mizoram,
   Nagaland, Sikkim, Ladakh). Five UTs share a neighbour's portal (Andaman &
   Nicobar → Tamil Nadu, Chandigarh → Delhi, DNH & DD → Maharashtra,
   Lakshadweep → Kerala). The coverage page must say so; we do not invent records.

## Consequences
- The "every project in India" promise depends on each state portal's
  accessibility; the survey and per-state inspections decide real coverage.
- The M1 acceptance check ("counts per state vs the portal's own totals")
  waits on the totals API coming back. Until then we compare against totals each
  state portal publishes itself, where it does.
