# Sentiment Page Dataflow (`/sentiment`)

## Scope
This document covers the live data path for `frontend/src/app/sentiment/page.tsx` and the endpoints it calls:
- `GET /api/sentiment/news`
- `GET /api/sentiment/cot`
- `GET /api/sentiment/metrics`
- `POST /api/sentiment/narrative`

## Endpoint Map
| Endpoint | Called By | Returns (high-level) | Source-backed vs Derived |
|---|---|---|---|
| `GET /api/sentiment/news` | `/sentiment` page load | Recent headlines + sentiment stats | Source-backed rows + derived sentiment classification |
| `GET /api/sentiment/cot` | `/sentiment` page load | Latest COT snapshot + 12-week history | Mostly source-backed, some derived pct fallback |
| `GET /api/sentiment/metrics` | `/sentiment` page load | Price/returns/volatility/technicals/positioning/crush/specialists/composite/fearGreed/trumpEffect | Mixed source-backed and derived |
| `POST /api/sentiment/narrative` | `/sentiment` after metrics load | Text narratives for fear/greed, trump effect, volatility | Derived from metrics payload (AI-backed when available, static fallback otherwise) |

## Source Tables By Endpoint

### `GET /api/sentiment/news`
Source tables:
- `alt.profarmer_news_event`
- `alt.legislation_1d`
- `alt.policy_news_event`
- `alt.executive_actions_event`
- `alt.econ_news_event`
- `econ.news_event`

Derived behavior:
- Sentiment label for each headline is computed via `classifySentiment(...)`.
- Response stats (`bullish`, `bearish`, `neutral`) are derived from classified rows.

### `GET /api/sentiment/cot`
Source table:
- `pos.cftc_1w`

Derived behavior:
- `managed_money.net_pct_oi` and `producers.net_pct_oi` use source pct when present; fallback derivation uses `net / open_interest`.
- `swaps.net_pct_oi` is derived as `swap_net / open_interest`.

### `GET /api/sentiment/metrics`
Source tables:
- `mkt.futures_1d` (price, returns, RSI inputs)
- `pos.cftc_1w` (positioning)
- `econ.vol_indices_1d` (VIX, OVX)
- `analytics.board_crush_1d` (crush/oil share)
- `training.specialist_signals_1d` (specialist signals)
- `training.specialist_features_trump_effect` (Trump feature row selection)
- `alt.executive_actions_event` (Trump fallback actions + sentiment ratio)
- `alt.legislation_1d` (Trump fallback presidential documents)
- `alt.policy_news_event`, `econ.news_event` (sentiment ratio)

Derived behavior:
- Moving averages, returns, RSI, z-scores, trend state.
- Composite specialist signal.
- Fear/Greed composite.
- Trump Effect payload assembly (details below).

### `POST /api/sentiment/narrative`
No direct DB query.
Input:
- The page posts selected metric payload sections (`fearGreed`, `trumpEffect`, `volatility`).

Derived behavior:
- AI narrative when API key/model path is available.
- Static template fallback when AI path unavailable/fails.

## Trump Effect Card Data Lineage
Code path:
- Route: `frontend/src/app/api/sentiment/metrics/route.ts`
- Helper: `frontend/src/app/api/sentiment/metrics/trump-effect.ts`
- Consumer: `frontend/src/app/sentiment/page.tsx`
- Narrative consumer: `frontend/src/app/api/sentiment/narrative/route.ts`

### Feature-row selection behavior
From `training.specialist_features_trump_effect`:
1. `latest_any`: latest row by `as_of_date`.
2. `latest_valid`: latest row where both `features.weighted_action_score` and `features.action_velocity` are present.
3. Selection mode:
- Use `latest_valid` when available.
- Else use `latest_any` (fallback).

Fields owned by feature JSON (when present):
- `weighted_action_score`
- `action_velocity`
- `action_acceleration`
- `total_actions_7d`
- `total_actions_30d`
- `eo_count_7d`

### Fallback action-source set (now complete)
Fallback derivation uses both canonical sources for the selected feature-row anchor date window:
- `alt.executive_actions_event`
- `alt.legislation_1d` filtered to `document_type = 'Presidential Document'`

Legislation title mapping:
- title contains `executive order` -> `executive_order`
- title contains `proclamation` -> `proclamation`
- title contains `memorandum` -> `memorandum`
- title contains `nomination` or `appoint` -> `nomination`
- else -> `presidential_document`

### Fallback windows (inclusive, anchor-date based)
Anchor date = selected feature row `as_of_date`.
- 7d window: `anchor_date - 6 days` through `anchor_date`
- 30d window: `anchor_date - 29 days` through `anchor_date`
- previous-week velocity window: `anchor_date - 13 days` through `anchor_date - 7 days`

### Fallback math
Counts:
- `eo_count_7d`
- `proclamation_count_7d`
- `memorandum_count_7d`
- `nomination_count_7d`
- `total_actions_7d`
- `total_actions_30d`

Velocity and acceleration:
- `action_velocity = total_actions_7d / 7`
- `previous_7d_velocity = previous_week_actions / 7`
- `action_acceleration = action_velocity - previous_7d_velocity`

Weighted score:
- `executive_order = 3.0`
- `memorandum = 2.5`
- `presidential_document = 2.0`
- `proclamation = 1.5`
- `nomination = 1.0`
- `weighted_action_score = weighted_7d_sum / 10.0`

Sentiment:
- Use `zl_sentiment` when present.
- Else infer via `scoreZlSentiment(headline, content)`.
- Mapping: bullish `+1`, bearish `-1`, neutral `0`.
- `avg_sentiment_7d` and `avg_sentiment_30d` are arithmetic means.
- If no qualifying rows in a window, return `null` for that average.

### Merge rule (source-backed first, fallback where missing)
For the final `trumpEffect` payload:
- Use feature-row value when present for feature-owned fields.
- Derive only missing feature-owned fields from fallback action math.
- Always derive document-type counts and sentiment averages from fallback action rows.

## What Was Wrong
The fallback derivation for the Trump card was incomplete. It only used `alt.executive_actions_event` and ignored presidential documents in `alt.legislation_1d`, while the canonical feature builder combines both sources. That created undercounting/mis-weighting when presidential documents existed only in legislation data.

## Current Correct Flow
The sentiment metrics route now derives Trump fallback metrics from the same action-source set used by the canonical feature builder (`alt.executive_actions_event` + presidential `alt.legislation_1d`), with aligned action-type mapping, aligned weights, and inclusive anchor-date windows. The `/sentiment` page and `/api/sentiment/narrative` contract remains unchanged.

## Known Caveats
- `GET /api/sentiment/metrics` may require authenticated app access; unauthenticated public calls can return unauthorized and are not sufficient to validate live card rendering.
- If both `latest_valid` and `latest_any` rows are stale, the route still emits data but flags staleness in `trumpEffectStatus`.
- If both source action tables have zero qualifying rows in a window, sentiment averages are `null` by design.
