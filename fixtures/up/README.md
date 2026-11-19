# Fixtures: Uttar Pradesh RERA (up-rera.in)

Collected 2026-11-19 by hand with the BuilderXRayBot User-Agent, ≥ 5 s apart.
Real public records, trimmed and redacted. **Not demo data**: never shown on
the site as examples.

| File | Source | Changes from the original |
|---|---|---|
| `projects_list.trimmed.html` | `GET https://up-rera.in/projects` (after the "Registered Projects" postback redirect) | Kept the header + first 30 of 3,864 table rows; kept 20 of each filter checkbox list (4,176 project names, 2,236 promoters, 55 districts); `__VIEWSTATE`/`__EVENTVALIDATION` values replaced with `[stripped]`; emails → `redacted@example.invalid`, Indian mobile numbers → `9000000000` |
| `project_detail_UPRERAPRJ839360.html` | `https://up-rera.in/Projectsummary?…` (row 3's "Details" link) | Same redaction (hidden fields, emails, mobiles) |

Field meanings: `docs/coverage.md` → "Uttar Pradesh".
