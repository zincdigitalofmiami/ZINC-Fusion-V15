# SENTIMENT_PAGE_DATAFLOW

## Scope
This document defines the live `/sentiment` page contract and math.
Primary objective: help a soybean-oil buyer decide if federal/presidential policy flow is creating real procurement risk in the **ZL futures contract price**.

## Endpoints Called By `/sentiment`
1. `GET /api/sentiment/news`
2. `GET /api/sentiment/cot`
3. `GET /api/sentiment/metrics`
4. `POST /api/sentiment/narrative`

## Endpoint Data Lineage

### `GET /api/sentiment/news`
Source tables:
- `alt.profarmer_news_event`
- `alt.legislation_1d`
- `alt.policy_news_event`
- `alt.executive_actions_event`
- `alt.econ_news_event`
- `econ.news_event`

Derived:
- `sentiment` via route classifier
- lane labels from canonical Google News lane tags (`specialist_tags` entries like `lane_<slug>`)
- legacy fallback lane parsing from `source` when old rows follow `google_news/<lane>/<publication>`

### `GET /api/sentiment/cot`
Source table:
- `pos.cftc_1w`

Derived:
- pct-of-open-interest fallback when source pct is missing

### `GET /api/sentiment/metrics`
Source tables:
- `mkt.futures_1d` (ZL closes + return/volatility anchors)
- `pos.cftc_1w`
- `econ.vol_indices_1d`
- `analytics.board_crush_1d`
- `training.specialist_signals_1d`
- `training.specialist_features_trump_effect`
- `alt.executive_actions_event`
- `alt.legislation_1d`
- `alt.policy_news_event`
- `alt.econ_news_event`
- `econ.news_event`

### `POST /api/sentiment/narrative`
- No direct DB reads/writes
- Consumes page payload (`fearGreed`, `trumpEffect`, `volatility`)
- Produces AI/static narrative text

## Policy Card Contract (Current)
Card title: **Impact on Soybean Oil Futures**

Ordered sections returned in `metrics.trumpEffect`:
1. `zl_response`
2. `policy_activity`
3. `procurement_outlook` (includes corroboration context)

Top-level schema:
- `title`
- `policy_window`:
  - `anchor_date`
  - `start_date_7d`
  - `selected_feature_mode` (`latest_valid` or `latest_fallback`)
- `zl_response`:
  - `anchor_price_date`
  - `anchor_window_start_date`
  - `zl_return_7d_pct`
  - `zl_response_1d_pct`
  - `zl_response_5d_pct`
  - `realized_vol_21d_pct`
  - `response_signal`
  - `abnormal_move_ratio`
- `policy_activity`:
  - `executive_orders_7d`
  - `total_presidential_actions_7d`
  - `other_presidential_actions_7d`
  - `action_velocity`
  - `action_acceleration`
  - `weighted_action_score`
  - `avg_sentiment_7d`
  - `avg_sentiment_30d`
- `procurement_outlook`:
  - `signal`
  - `label`
  - `summary`
  - `corroboration`:
    - `supporting_policy_items_7d`
    - `market_news_items_7d`
    - `regulatory_follow_through_7d`
    - `corroboration_score`
    - `corroboration_band`

Legacy scalar fields are still emitted (`weighted_action_score`, `total_actions_7d`, etc.) for compatibility.

## Exact Tables vs Context Tables

### Exact Tables (Primary Policy Action Counters)
Use only for primary action counts:
- `alt.executive_actions_event`
- `alt.legislation_1d` where `document_type = 'Presidential Document'`

These drive:
- `executive_orders_7d`
- `total_presidential_actions_7d`
- `other_presidential_actions_7d`
- `action_velocity`
- `action_acceleration`
- fallback-derived `weighted_action_score`

### Context Tables (Corroboration/Confirmation)
Use for corroboration context, not primary action counters:
- `alt.policy_news_event`
- `alt.econ_news_event`
- `econ.news_event`
- non-presidential `alt.legislation_1d`

These drive:
- `supporting_policy_items_7d`
- `market_news_items_7d`
- `regulatory_follow_through_7d`
- `corroboration_score`
- `corroboration_band`

## Google News Lane + Date Contract
Google News remains context-only and writes to `alt.policy_news_event`.

Ingestion lanes (from `googleNewsDaily`):
- `ice_immigration`
- `war_military`
- `soybean_oil`
- `soybean_agriculture`
- `trump_actions`
- `legislation`
- `biofuel`

Stored lane identity:
- Canonical row model: one dated row per article (`row_hash` article-level, not lane-level)
- `source = google_news/<publication>` for canonical rows
- lane attribution in `specialist_tags` via `lane_<lane>`
- legacy rows may still exist as `google_news/<lane>/<publication>`; consumers parse both forms

Date integrity rules:
- Missing `pubDate` rows are rejected.
- Invalid `pubDate` rows are rejected.
- Stale rows older than `MAX_NEWS_ITEM_AGE_DAYS` are rejected.
- Excessive future-skew rows are rejected.
- Inserted rows keep usable `event_date` and `published_at` for downstream ZL alignment.
- Same article matching multiple lanes is stored once with multiple lane tags (no per-lane row multiplication).

## Trump/Policy Card Math

### 1) Feature-row selection
From `training.specialist_features_trump_effect`:
- Select `latest_any` by `as_of_date` unconditionally.
- Set `selected_feature_mode` from `latest_any` completeness:
  - `latest_valid` when both `weighted_action_score` and `action_velocity` are present.
  - `latest_fallback` when either is missing (helper backfills from exact action sources).

### 2) Action-source union (primary policy activity)
Primary source set:
- `alt.executive_actions_event`
- presidential rows from `alt.legislation_1d`

Title mapping for `alt.legislation_1d` presidential rows:
- `executive order` -> `executive_order`
- `proclamation` -> `proclamation`
- `memorandum` -> `memorandum`
- `nomination` or `appoint` -> `nomination`
- else -> `presidential_document`

Inclusive windows anchored to `policy_window.anchor_date`:
- 7d: `anchor_date - 6 days` through `anchor_date`
- 30d: `anchor_date - 29 days` through `anchor_date`
- previous-week velocity: `anchor_date - 13 days` through `anchor_date - 7 days`

Policy activity formulas:
- `total_presidential_actions_7d = count(all action rows in 7d)`
- `executive_orders_7d = count(executive_order in 7d)`
- `other_presidential_actions_7d = total_presidential_actions_7d - executive_orders_7d`
- `action_velocity = total_presidential_actions_7d / 7`
- `action_acceleration = action_velocity - previous_week_velocity`
- `weighted_action_score = weighted_7d_sum / 10.0`

Weights:
- `executive_order = 3.0`
- `memorandum = 2.5`
- `presidential_document = 2.0`
- `proclamation = 1.5`
- `nomination = 1.0`

Action sentiment:
- use `zl_sentiment` when present
- otherwise `scoreZlSentiment(headline, content)`
- map `bullish/bearish/neutral -> +1/-1/0`
- 7d/30d arithmetic average
- return `null` when no qualifying rows

### 3) ZL response math
Source: `mkt.futures_1d` (`symbol='ZL'`)

Reference closes on/before each anchor-relative date:
- anchor day
- anchor -1d
- anchor -5d
- anchor -6d (7d window start)

Formulas:
- `zl_return_7d_pct = ((close_anchor - close_start_7d) / close_start_7d) * 100`
- `zl_response_1d_pct = ((close_anchor - close_prev_1d) / close_prev_1d) * 100`
- `zl_response_5d_pct = ((close_anchor - close_prev_5d) / close_prev_5d) * 100`
- `realized_vol_21d_pct` from annualized trailing log-return stddev
- `abnormal_move_ratio = abs(zl_response_1d_pct) / (realized_vol_21d_pct / sqrt(252))`

Response signal:
- `elevated` if ratio >= 1.5
- `active` if ratio >= 0.9
- else `muted`

### 4) Corroboration + procurement outlook
Corroboration inputs (7d):
- `supporting_policy_items_7d` from `alt.policy_news_event` + `alt.econ_news_event`
- `market_news_items_7d` from `econ.news_event`
- `regulatory_follow_through_7d` from non-presidential `alt.legislation_1d`

Score:
- `policy_norm = min(supporting_policy_items_7d, 8) / 8`
- `market_norm = min(market_news_items_7d, 8) / 8`
- `reg_norm = min(regulatory_follow_through_7d, 4) / 4`
- `corroboration_score = round((policy_norm*0.45 + market_norm*0.35 + reg_norm*0.20) * 100)`

Band:
- `strong` if `corroboration_score >= 70`
- `mixed` if `40 <= corroboration_score < 70`
- `low` if `< 40`

`procurement_outlook` derives final buyer-facing message from:
- policy activity intensity
- corroboration band/score
- ZL response magnitude/signal

## What Was Wrong
- Google News context previously multiplied rows across lanes when one article matched multiple lanes.
- That inflated raw daily `news_count` features in training because `build_matrix.py` counts rows by `event_date` across news tables.
- Google News date acceptance was too loose for training-sensitive `event_date` downstream use.
- Card copy split corroboration and buyer text as separate blocks; product direction moved this into a single procurement outlook section.

## Current Correct Flow
- Exact tables drive primary policy counters.
- Context/news tables drive corroboration only.
- Google News rows are canonicalized (one row/article), lane-tagged, and date-gated before insertion.
- Card stays ZL-anchored with procurement outlook that includes corroboration context.

## Known Caveats
- `/api/sentiment/metrics` requires authenticated production access.
- When selected feature row is partial, `selected_feature_mode=latest_fallback` and source-backed backfill is used.
- If no qualifying rows exist in a window, null/zero outputs are returned by design (no invented placeholders).
