# Free-tier limits

Verified against official docs on **2026-11-19**. Re-check quarterly and
whenever a provider announces changes. Machine-readable copy:
`config/limits.yaml` (the code reads that file, not this one).

Design target: stay under **50%** of every limit. The pipeline stops at 50%
and resumes on the next run.

## Cloudflare (Workers Free plan)

Sources: [Workers limits](https://developers.cloudflare.com/workers/platform/limits/),
[Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/),
[Static asset limits changelog](https://developers.cloudflare.com/changelog/post/2025-09-02-increased-static-asset-limits/)

| Limit | Free value | Our 50% target | Notes |
|---|---|---|---|
| Worker requests | 100,000 / day (resets 00:00 UTC) | 50,000 / day | Over limit → Error 1027. Static asset hits are **not** counted. |
| CPU time | 10 ms / request | render < 5 ms | Network wait does not count. |
| Static assets | 20,000 files / Worker version | **19,000 hard gate** (build fails) | Spec gate; 50% would be 10,000 (see ADR-001). |
| Asset file size | 25 MiB / file | shards < 1 MiB | |
| Subrequests | 50 / invocation | ≤ 5 | |
| Static asset requests | Free, unlimited | n/a | Why pages are pre-built. |

## Cloudflare D1 (Free)

Sources: [D1 pricing](https://developers.cloudflare.com/d1/platform/pricing/),
[D1 limits](https://developers.cloudflare.com/d1/platform/limits/)

| Limit | Free value | Our 50% target |
|---|---|---|
| Rows read | 5,000,000 / day | 2,500,000 / day |
| Rows written | 100,000 / day | 50,000 / day |
| Storage | 5 GB total, 500 MB / database, 10 databases | 250 MB / database |

Index updates count as extra writes; unindexed scans count every row read.

## Cloudflare R2 (Free, Standard storage only)

Source: [R2 pricing](https://developers.cloudflare.com/r2/pricing/)

| Limit | Free value | Our 50% target |
|---|---|---|
| Storage | 10 GB-month | 5 GB |
| Class A ops (writes/lists) | 1,000,000 / month | 500,000 / month |
| Class B ops (reads) | 10,000,000 / month | 5,000,000 / month |
| Egress | Free | n/a |

R2 needs a payment method on file to enable. If you would rather not add one,
snapshots go to GitHub Release assets instead (ADR-001).

## GitHub Actions

Sources: [Actions limits](https://docs.github.com/en/actions/reference/limits),
[Actions billing](https://docs.github.com/billing/managing-billing-for-github-actions/about-billing-for-github-actions)

| Limit | Value | Our target |
|---|---|---|
| Standard runner minutes, **public** repo | Free, unlimited | Repo is public (ADR-001) |
| Job execution time | 6 h max | crawl jobs `timeout-minutes: 300` |
| Concurrent jobs (Free plan) | 20 | ≤ 4 |
| Release asset size | 2 GiB / file | snapshot files < 500 MB |

## Email

| Provider | Free limit | Our 50% target | Source |
|---|---|---|---|
| Brevo (primary) | 300 emails / day | 150 / day | [Brevo help](https://help.brevo.com/hc/en-us/articles/208580669) |
| Resend (fallback) | 3,000 / month, 100 / day | 50 / day | Resend pricing page: verify again at M5 |

## To verify when first used (not used in M0)

| Service | When | What to record |
|---|---|---|
| LLM free tier (e.g. Gemini / Groq / OpenRouter free) | M2 | RPM, RPD, tokens/day, and whether free-tier data may be used for training (affects provider choice) |
| Ollama (local fallback) | M2 | No limits; runs only on a self-hosted runner or locally |
| Telegram Bot API | M5 | Message rate limits (~30 msg/s overall, ~1 msg/s per chat, per FAQ) |
| Cloudflare Turnstile | M5 | Free widget limits |
| Razorpay | M5 | Per-transaction fee (%), no fixed fee |
