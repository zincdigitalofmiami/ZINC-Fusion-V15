# Stale Data Audit - 2026-03-11

> Superseded note (2026-03-11): This report is preserved as a historical snapshot.
> The old `db-guard-*` workflow and `CLOUD_DATABASE_URL` convention were removed later the same day.
> For current operational status, use `TO-DO/Audit/2026-03-11_forensic_db_inngest_operational_audit.md` and `TO-DO/Audit/AUDIT_INDEX.md`.

## Section 1 - Frontend Page-by-Page Stale Review

### Coverage checklist
- [x] frontend/src/app/page.tsx
- [x] frontend/src/app/login/page.tsx
- [x] frontend/src/app/dashboard/page.tsx
- [x] frontend/src/app/strategy/page.tsx
- [x] frontend/src/app/sentiment/page.tsx
- [x] frontend/src/app/legislation/page.tsx
- [x] frontend/src/app/vegas-intel/page.tsx
- [x] frontend/src/app/quant/page.tsx (returns notFound; no cards)

### Findings list (cards with stale data risk or explicit stale contracts)

1. Page: dashboard
- Card: Market Risk Factors (`ChrisTop4Drivers`)
- Files: frontend/src/app/dashboard/page.tsx, frontend/src/components/ChrisTop4Drivers.tsx, frontend/src/app/api/market-drivers/route.ts
- Stale contract: Uses `as_of_date`; day-bound cache via `getMorningRefreshBoundary()` in client and `AI_REFRESH_UTC_HOUR` day key on server.
- Risk: Daily cache can serve prior-day AI context until refresh boundary.

2. Page: dashboard
- Card: Hero chart (`LightweightZlCandlestickChart`)
- Files: frontend/src/components/LightweightZlCandlestickChart.tsx, frontend/src/app/api/zl/price-1d/route.ts, frontend/src/app/api/zl/live/route.ts
- Stale contract: `updated_at`, source fallback chain (`1m` -> `latest_price` -> daily), cache headers include `stale-while-revalidate` for 1d route.
- Risk: Intraday fallback to daily path can keep card operational with older market state.

3. Page: dashboard
- Card: L3 Probability Heatmap (`ProbabilityHeatmap`)
- Files: frontend/src/components/quant/ProbabilityHeatmap.tsx, frontend/src/app/api/zl/forecast-targets/route.ts
- Stale contract: Uses `as_of_date` with cache header `s-maxage=3600, stale-while-revalidate=3600`.
- Risk: Forecast targets may be up to an hour stale at edge plus source table staleness.

4. Page: strategy
- Card group: Executive summary + posture + driver strip + action card
- Files: frontend/src/app/strategy/page.tsx, frontend/src/app/api/zl/brief/route.ts
- Stale contract: Explicit `dataQuality` (`good|partial|poor`), `stalenessWarnings[]`, `dataStaleness.staleSources[]`, driver `source` (`live|stale|unavailable`).
- Risk: Partial data mode intentionally allows stale signals; card remains populated but quality downgraded.

5. Page: strategy
- Card: AI Market Context
- Files: frontend/src/app/strategy/page.tsx, frontend/src/app/api/zl/context/route.ts
- Stale contract: Client cache via localStorage boundary + server day-key cache (`AI_REFRESH_UTC_HOUR`); prompt includes stale acknowledgement path.
- Risk: Narrative may lag live driver changes until boundary invalidation.

6. Page: strategy
- Card: Driver tiles (per bucket)
- Files: frontend/src/app/strategy/page.tsx
- Stale contract: Each driver has `source` and optional `asOfDate`; stale badges shown when source is stale.
- Risk: Mixed freshness across buckets on the same screen.

7. Page: strategy
- Card: Weather Risk Array
- Files: frontend/src/components/viz/WeatherRiskArray.tsx, frontend/src/app/api/weather-risk/route.ts
- Stale contract: API is `no-store`, but card payload does not expose explicit source timestamp in UI.
- Risk: No visible age metadata for user verification.

8. Page: sentiment
- Card group: Fear & Greed, hero strip, Trump Effect, volatility narrative blocks
- Files: frontend/src/app/sentiment/page.tsx, frontend/src/app/api/sentiment/metrics/route.ts, frontend/src/app/api/sentiment/narrative/route.ts
- Stale contract: Uses `as_of`, trump status includes `selected_is_stale`, `selected_age_days`, `selection_mode` (`latest_valid|latest_fallback`), plus narrative cache boundary.
- Risk: `latest_fallback` mode can keep non-ideal records active; narrative cache can lag metrics refresh.

9. Page: sentiment
- Card: News + COT sections
- Files: frontend/src/app/sentiment/page.tsx, frontend/src/app/api/sentiment/news/route.ts, frontend/src/app/api/sentiment/cot/route.ts
- Stale contract: `as_of_date` fields with edge cache (`s-maxage` + `stale-while-revalidate`).
- Risk: Weekly COT and cached news can present lagged signal without strong freshness callout.

10. Page: legislation
- Card: Threat level + regime meter
- Files: frontend/src/app/legislation/page.tsx
- Stale contract: Displays TPU freshness (`regime.freshness.tpu_date`).
- Risk: Other components in same page do not expose equally explicit freshness metadata.

11. Page: legislation
- Card: Policy AI Briefing
- Files: frontend/src/components/policy/PolicyAiBriefing.tsx, frontend/src/app/api/policy/briefing/route.ts
- Stale contract: localStorage cache with morning boundary + route day-key cache.
- Risk: Same-day reuse by design; can lag rapid policy event changes.

12. Page: legislation
- Card: Policy Section Brief blocks
- Files: frontend/src/components/policy/PolicySectionBrief.tsx, frontend/src/app/api/policy/section-brief/route.ts
- Stale contract: localStorage cache with boundary and deterministic fallback text.
- Risk: Section brief can remain cached while underlying feed changed.

13. Page: legislation
- Card: Agency activity heatmap + executive actions list + policy news feed
- Files: frontend/src/app/legislation/page.tsx, frontend/src/components/policy/PolicyNewsFeed.tsx
- Stale contract: Event dates shown; no unified page-level last-refresh timestamp.
- Risk: User sees dated records but not ingestion-lag summary.

14. Page: vegas-intel
- Card group: Segment cards, events list, opportunities table
- Files: frontend/src/app/vegas-intel/page.tsx, frontend/src/app/api/vegas/route.ts
- Stale contract: `last_sync` from API and displayed in page header.
- Risk: Last sync shown as date string (no time granularity); underlying datasets may have differing ingest ages.

15. Global header
- Card: Status bar ticker
- Files: frontend/src/components/StatusBar.tsx, frontend/src/app/api/zl/live/route.ts
- Stale contract: `live` boolean, `source`, `updated_at`, `age_seconds` logic server-side.
- Risk: Fallback source can keep ticker live-looking if not interpreted with source metadata.

### Frontend pages with no stale-card surface
- frontend/src/app/page.tsx (routing shell)
- frontend/src/app/login/page.tsx (auth form only)
- frontend/src/app/quant/page.tsx (notFound)

---

## Section 2 - Local DB Stale Review

### Executed checks
1. Historical check: `make db-guard-local` (command removed on 2026-03-11)
- Result: PASS
- Evidence: `[PASS] mode=local endpoint=localhost:5432/zinc_fusion_v15_local db=zinc_fusion_v15_local message=ok`

2. `make db-parity-local`
- Result: PASS
- Evidence summary:
	- `forecasts.production_1d`: 24 rows, min `2026-01-22`, max `2026-08-27`
	- `training.matrix_1d`: 7,982 rows, min `1990-01-01`, max `2026-03-03`
	- `training.model_runs_event`: 14 rows, min `2025-03-31`, max `2026-02-13`
	- `training.oof_core_1d`: 964 rows, min `2023-10-19`, max `2026-02-20`
	- `training.specialist_signals_1d`: 85,411 rows, min `1990-01-01`, max `2026-03-03`
	- Notice confirms Big-11 specialist population: `distinct_buckets=11`

3. `.venv/bin/python scripts/data_gate_specialists.py --strict`
- Result: FAIL
- Reason: schema/table mismatch in local audit DB, not env. Missing tables referenced by data gate include:
	- `mkt.futures_1d`
	- `pos.cftc_1w`
	- `mkt.fx_1d`
	- `econ.rates_1d`
	- `econ.vol_indices_1d`
	- `supply.epa_rin_1d`
	- `supply.lcfs_1d`
- Summary: `0/11 specialists passed data gate`

4. `.venv/bin/python -m src.fusion.validators.run_all`
- Result: FAIL
- Reason: validator implementation/schema gaps:
	- `SchemaContractValidator` skipped (not implemented)
	- `FreshnessMonitor` skipped (not implemented)
	- Quarantine check failed: `ops.quarantined_record` table does not exist

5. Targeted stale SQL metrics (local DB)
- Result: PASS
- Query set executed against `LOCAL_DATABASE_URL` for key audit tables and freshness deltas.

### Local DB stale findings
- Row-level stale computation completed.

Key table recency (as of run date 2026-03-11):

| Table | Rows | Max date | Days stale |
|---|---:|---|---:|
| `forecasts.production_1d` | 24 | 2026-03-04 | 7 |
| `training.matrix_1d` | 7,982 | 2026-03-03 | 8 |
| `training.specialist_signals_1d` | 85,411 | 2026-03-03 | 8 |
| `training.oof_core_1d` | 964 | 2026-02-20 | 19 |
| `training.model_runs_event` | 14 | 2026-03-05 | 6 |

Forecast freshness by horizon (`forecasts.production_1d`):

| Horizon | Rows | Max `as_of_date` | Days stale |
|---:|---:|---|---:|
| 5 | 6 | 2026-03-04 | 7 |
| 21 | 6 | 2026-03-04 | 7 |
| 63 | 6 | 2026-03-04 | 7 |
| 126 | 6 | 2026-03-04 | 7 |

Specialist signal freshness by bucket (`training.specialist_signals_1d`):
- All 11 buckets have `max_as_of=2026-03-03`, each `8` days stale.

Ingest run lag snapshot (`ops.ingest_run`):
- `trump_effect_feature_refresh`: last completion `2026-03-09`, `2` days since completion, `1` run, `1` non-success.
- `google-news-daily`: last completion `2026-03-10`, `1` day since completion, `1` run, `1` non-success.

Interpretation:
- Local DB is reachable and internally consistent for core audit tables.
- Freshness lag is measurable (6-19 day span across key training/forecast assets).
- Reliability concern remains in ingest history due to recent non-success-only runs in `ops.ingest_run` sample.

### Local DB stale review gaps (pending execution when DB URL is available)
- Deep source-table freshness for each frontend card source table (beyond the key audit tables above).
- Full `ops.ingest_run` job inventory (all jobs, not top lag sample).

---

## Section 3 - Prisma DB Stale Review

### Executed checks
1. `make prisma-validate`
- Result: PASS
- Evidence: schema at `prisma/schema.prisma` is valid.

2. Historical check: `make db-guard-cloud` (command removed on 2026-03-11)
- Result at time of run: PASS with explicit cloud URL override
- Current status: superseded by direct `DATABASE_URL`-based parity tooling

3. Historical check: `make db-guard-shadow` (command removed on 2026-03-11)
- Result at time of run: PASS

### Prisma stale findings
- Schema-level: no Prisma schema validation errors.
- Cloud identity guard now passes when URL is explicitly supplied.
- Data-level stale SQL against cloud remains blocked: provided credential is redacted/incomplete for direct `psql` auth (prompted for password).
- Vercel CLI check completed:
	- `npx vercel whoami` succeeds (`zincdigitalofmiami`).
	- `npx vercel env pull --environment=production` returns 21 keys, but no DB connection key (`DATABASE_URL`, `POSTGRES_URL`, `DIRECT_DATABASE_URL`, `CLOUD_DATABASE_URL` all absent).
- Result: Vercel env pull cannot currently supply cloud DB credentials for Section 3 queries.
- Shadow DB identity is correctly configured for local Prisma workflows.

### Prisma stale review gaps (pending DB access)
- Cloud-target stale SQL (same recency metrics executed against cloud runtime DB).
- Cloud-vs-local freshness drift deltas for card-backed schemas.
- Non-redacted cloud credential for non-interactive SQL execution.

---

## Consolidated stale findings index

### Confirmed stale-prone card surfaces (from code contracts)
- Dashboard: Market Risk Factors, Hero Chart, Probability Heatmap
- Strategy: Executive summary/posture/drivers, AI context, weather risk
- Sentiment: Fear & Greed/Trump Effect/Volatility narratives, News, COT
- Legislation: Threat meter, AI briefing, section briefs, agency/news/action feeds
- Vegas Intel: segment/events/opportunities suite
- Global header: status ticker

### Execution blockers
- Historical blocker removed: `CLOUD_DATABASE_URL` / `.env.local.audit` workflow was deleted.
- Redacted/incomplete cloud credential prevents direct `psql` query execution.
- Historical blocker removed: workspace is now linked to `zinc-fusion-v15`, not orphan `frontend`.
- Local validators/data gate failures due to local schema/table coverage mismatches and unimplemented validator components.

### Next executable commands once URLs are provided
1. Export a full non-redacted cloud `DATABASE_URL` in-session for direct SQL checks.
2. Run cloud-target stale SQL for matrix/forecasts/signals/oof/ingest tables.
3. Compare cloud-vs-local stale deltas and append to the working forensic audit.
