# SENTIMENT_PAGE_DATAFLOW

## Scope
This document defines the live `/sentiment` page data contract and math.
Primary objective: help a soybean oil buyer decide if federal/presidential policy flow is creating real procurement risk in the **ZL futures contract price**.

## Endpoints Called By `/sentiment`
1. `GET /api/sentiment/news`
2. `GET /api/sentiment/cot`
3. `GET /api/sentiment/metrics`
4. `POST /api/sentiment/narrative`

## Endpoint Data Lineage

### `GET /api/sentiment/news`
- Source tables:
- `alt.profarmer_news_event`
- `alt.legislation_1d`
- `alt.policy_news_event`
- `alt.executive_actions_event`
- `alt.econ_news_event`
- `econ.news_event`
- Derived:
- sentiment labels from `classifySentiment(...)`
- bullish/bearish/neutral aggregates

### `GET /api/sentiment/cot`
- Source table:
- `pos.cftc_1w`
- Derived:
- pct-of-open-interest fallback when source pct is missing

### `GET /api/sentiment/metrics`
- Source tables:
- `mkt.futures_1d` (ZL price + return/volatility/technical inputs)
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
- No direct DB writes/reads
- Consumes payload from page state (`fearGreed`, `trumpEffect`, `volatility`)
- Produces AI/static narrative text

## Policy Card Contract (Final)
Card title: **Policy Impact on ZL**

Card returns four ordered sections:
1. `zl_response`
2. `policy_activity`
3. `independent_confirmation`
4. `buyer_meaning`

Top-level schema emitted under `metrics.trumpEffect`:
- `title`
- `policy_window`:
- `anchor_date`
- `start_date_7d`
- `selected_feature_mode`
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
- `independent_confirmation`:
- `independent_policy_items_7d`
- `market_news_items_7d`
- `regulatory_follow_through_7d`
- `confirmation_score`
- `confirmation_band`
- `buyer_meaning`:
- `procurement_signal`
- `label`
- `rationale`

Legacy compatibility fields are still emitted (`weighted_action_score`, `total_actions_7d`, etc.) so existing consumers do not break.

## Exact Tables vs Context Tables

### Exact Tables (Primary Policy Action Counters)
Use only for primary presidential/federal action counting:
- `alt.executive_actions_event`
- `alt.legislation_1d` where `document_type = 'Presidential Document'`

These tables drive:
- `executive_orders_7d`
- `total_presidential_actions_7d`
- `other_presidential_actions_7d`
- `action_velocity`
- `action_acceleration`
- fallback-derived `weighted_action_score`

### Context Tables (Independent Confirmation)
Use for corroboration only, not primary action counts:
- `alt.policy_news_event`
- `alt.econ_news_event`
- `econ.news_event`
- `alt.legislation_1d` where `document_type <> 'Presidential Document'` (regulatory follow-through)

These tables drive:
- `independent_policy_items_7d`
- `market_news_items_7d`
- `regulatory_follow_through_7d`
- `confirmation_score`
- `confirmation_band`

## Trump/Policy Card Math

## 1) Feature-row selection
From `training.specialist_features_trump_effect`:
- `latest_any` = latest by `as_of_date`
- select `latest_any` unconditionally as the policy anchor row
- set `selection_mode` from `latest_any` completeness:
- `latest_valid` when both `weighted_action_score` and `action_velocity` are present
- `latest_fallback` when either field is missing (helper backfills from source action tables)

`policy_window.anchor_date` uses selected row `as_of_date`.

## 2) Action-source union (primary policy activity)
Window source set:
- `alt.executive_actions_event`
- `alt.legislation_1d` presidential documents mapped from title:
- `executive order` -> `executive_order`
- `proclamation` -> `proclamation`
- `memorandum` -> `memorandum`
- `nomination` or `appoint` -> `nomination`
- else -> `presidential_document`

Inclusive windows:
- 7d: `anchor_date - 6 days` through `anchor_date`
- 30d: `anchor_date - 29 days` through `anchor_date`
- previous-week velocity window: `anchor_date - 13 days` through `anchor_date - 7 days`

Policy activity math:
- `total_presidential_actions_7d` = count(all action rows in 7d)
- `executive_orders_7d` = count(`executive_order` in 7d)
- `other_presidential_actions_7d` = `total_presidential_actions_7d - executive_orders_7d`
- `action_velocity = total_presidential_actions_7d / 7`
- `action_acceleration = action_velocity - previous_week_velocity`
- `weighted_action_score = weighted_7d_sum / 10.0`

Weights:
- `executive_order = 3.0`
- `memorandum = 2.5`
- `presidential_document = 2.0`
- `proclamation = 1.5`
- `nomination = 1.0`

Sentiment math on action rows:
- use `zl_sentiment` when present
- else score text via `scoreZlSentiment(headline, content)`
- map bullish/bearish/neutral to `+1/-1/0`
- arithmetic averages for 7d and 30d
- if no qualifying rows, return `null`

## 3) ZL response math (anchor-coupled)
Source: `mkt.futures_1d` (`symbol='ZL'`)

Reference closes (latest close on or before each date):
- `close_anchor` on/<= `anchor_date`
- `close_prev_1d` on/<= `anchor_date - 1 day`
- `close_prev_5d` on/<= `anchor_date - 5 days`
- `close_start_7d` on/<= `anchor_date - 6 days`

Returns:
- `zl_return_7d_pct = ((close_anchor - close_start_7d) / close_start_7d) * 100`
- `zl_response_1d_pct = ((close_anchor - close_prev_1d) / close_prev_1d) * 100`
- `zl_response_5d_pct = ((close_anchor - close_prev_5d) / close_prev_5d) * 100`

Volatility:
- `realized_vol_21d_pct` from stddev(log-returns) annualized over trailing anchor-capped sample
- `abnormal_move_ratio = abs(zl_response_1d_pct) / (realized_vol_21d_pct / sqrt(252))`
- response band:
- `elevated` if ratio >= 1.5
- `active` if ratio >= 0.9
- else `muted`

## 4) Independent confirmation math
Inputs (7d window):
- `independent_policy_items_7d` from `alt.policy_news_event` + `alt.econ_news_event`
- `market_news_items_7d` from `econ.news_event`
- `regulatory_follow_through_7d` from non-presidential `alt.legislation_1d`

Rows qualify via specialist-tag overlap and/or explicit policy/ZL keyword patterns.

Score:
- `policy_norm = min(independent_policy_items_7d, 8) / 8`
- `market_norm = min(market_news_items_7d, 8) / 8`
- `reg_norm = min(regulatory_follow_through_7d, 4) / 4`
- `confirmation_score = round((policy_norm*0.45 + market_norm*0.35 + reg_norm*0.20) * 100)`

Band:
- `strong` if `confirmation_score >= 70`
- `mixed` if `40 <= confirmation_score < 70`
- `low` if `< 40`

## 5) Buyer meaning
`buyer_meaning` is a rule-based procurement interpretation from:
- policy activity intensity
- confirmation band
- ZL response signal/magnitude

Outputs are explicit labels/rationales (for non-expert comprehension), not opaque model text.

## Why The Card Was Reframed
The old card presentation over-weighted activity buckets and under-explained whether activity was independently corroborated or actually moving ZL. That made it easy to confuse policy headline volume with real procurement risk. The reframed contract makes ZL response first-class, isolates primary policy counters from context/confirmation, and forces an explicit buyer interpretation.

## What Chris Actually Needs
Chris needs to know whether to pull coverage forward, hold, or wait. That requires four separate answers in order:
1. Is ZL moving in the policy window?
2. Is policy activity materially high or low?
3. Is activity independently corroborated beyond primary-source output?
4. What is the procurement implication right now?

## ZL As Anchor
ZL price action is the anchor. Policy activity is an explanatory input, not an end in itself. The card is considered healthy only when it can separate:
- activity (what was announced)
- confirmation (what independent sources corroborate)
- market response (what ZL actually did)
- buyer meaning (what this changes for procurement timing)

## Known Caveats
- `/api/sentiment/metrics` requires authenticated access in production.
- If selected feature row is stale, card emits staleness status and should be treated as directional context.
- If no qualifying source rows exist in a window, nulls/zeros are returned by design rather than invented placeholders.
