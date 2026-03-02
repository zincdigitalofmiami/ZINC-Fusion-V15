# Plan: AI Feedback Loop — Cache Daily Analysis → Train Model

## Status: QUEUED (not started)

## Problem

The AI market context is stateless — it reasons from scratch every page load. It doesn't:
- Remember yesterday's analysis
- Know if its previous advice was correct
- Feed its signals into the ML ensemble for next training

## What This Builds

A **closed-loop feedback system** where:

1. Each day's AI analysis gets cached to the DB
2. After N days, we compare the AI's recommendation against actual ZL price movement
3. Those AI-derived features become columns in `build_matrix.py`
4. The 52-model ensemble learns patterns like: "when AI said VOLATILE + events STRONGLY_BULLISH, prices did X"

## Architecture

```
Daily cron (Inngest)
  → Call /api/zl/brief
  → Snapshot: posture, override, netScore, signal, velocity, top headlines, AI text
  → Store in analytics.ai_context_1d

Training pipeline (build_matrix.py)
  → Read ai_context_1d
  → Engineer features: ai_posture_encoded, ai_net_sentiment, ai_velocity_ratio, ai_override_active
  → Join to matrix on trade_date
  → Model trains on these + all existing 1,487 features
```

## Implementation Steps

### Step 1: DB Table

```sql
CREATE TABLE analytics.ai_context_1d (
  id SERIAL PRIMARY KEY,
  trade_date DATE NOT NULL UNIQUE,
  symbol TEXT NOT NULL DEFAULT 'ZL',

  -- Posture snapshot
  recommendation TEXT,          -- 'WAIT', 'LOCK IN COVERAGE', etc.
  override_reason TEXT,         -- NULL if no override
  override_active BOOLEAN DEFAULT FALSE,

  -- Event pulse snapshot
  event_velocity_ratio REAL,
  net_sentiment_score REAL,
  net_sentiment_signal TEXT,    -- 'STRONGLY_BULLISH', 'NEUTRAL', etc.
  bullish_count INT,
  bearish_count INT,
  neutral_count INT,
  events_24h INT,

  -- Top headlines (JSON array of {headline, source, sentiment, hoursAgo})
  top_headlines JSONB,

  -- AI output
  ai_context_text TEXT,         -- Full streamed text from Claude
  ai_model_used TEXT,           -- 'claude-sonnet-4-5-20250929'

  -- Forecast at time of snapshot
  forecast_1m_change_pct REAL,
  forecast_6m_change_pct REAL,
  current_price REAL,

  -- Outcome tracking (filled in later by backfill job)
  actual_1d_change_pct REAL,    -- What ZL actually did next day
  actual_7d_change_pct REAL,    -- What ZL did over next week
  actual_21d_change_pct REAL,   -- What ZL did over next month
  ai_was_correct BOOLEAN,       -- Did posture align with outcome?

  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Step 2: Inngest Cron — Daily Snapshot

New function: `aiContextSnapshotDaily` — runs weekdays at 4 PM CT (after market close).

1. Call `getEventPulse()` + `getRecommendation()` internally (not HTTP — direct function call)
2. Call `/api/zl/context` to get the AI text
3. INSERT into `analytics.ai_context_1d`

### Step 3: Inngest Cron — Outcome Backfill

New function: `aiOutcomeBackfillWeekly` — runs Sunday.

1. Find rows in `ai_context_1d` where `actual_7d_change_pct IS NULL` and `trade_date < NOW() - 7 days`
2. Look up actual ZL price from `analytics.price_1d` at trade_date + 1d, +7d, +21d
3. Compute actual change percentages
4. Set `ai_was_correct` based on whether posture aligned with price direction

### Step 4: Matrix Features

Add to `build_matrix.py`:

```python
# AI context features (from analytics.ai_context_1d)
ai_features = [
    'ai_override_active',           # Boolean: was event override firing?
    'ai_net_sentiment_score',       # Float: raw netScore
    'ai_velocity_ratio',            # Float: event velocity
    'ai_posture_encoded',           # Int: WAIT=2, VOLATILE=1, HOLD=0, ACCUMULATE=-1
    'ai_bullish_count',             # Int: count of bullish events
    'ai_bearish_count',             # Int: count of bearish events
    'ai_forecast_model_agreement',  # Float: does AI posture agree with model forecast?
    'ai_was_correct_7d_lag',        # Boolean: was yesterday's AI right? (lagged feedback)
]
```

### Step 5: Prompt Memory (Optional Enhancement)

Give the AI context prompt access to the last 3 days of cached analysis:

```
PREVIOUS ANALYSIS (for continuity):
- Yesterday: WAIT — VOLATILE, netScore 17.3, "model forecasts retracement"
- 2 days ago: HOLD, netScore 1.2, "stable markets"
- 3 days ago: HOLD, netScore 0.8, "calm conditions"
```

This lets the AI say "tensions have escalated since yesterday" or "the crisis appears to be deescalating" instead of always reasoning from zero.

## Files to Create/Modify

| File | Change |
|------|--------|
| `prisma/schema.prisma` | Add `AiContext1d` model in analytics schema |
| `frontend/src/inngest/ai-context-snapshot.ts` | New: daily snapshot cron |
| `frontend/src/inngest/ai-outcome-backfill.ts` | New: weekly outcome backfill |
| `frontend/src/inngest/functions.ts` | Register new functions |
| `fusion/core_training/build_matrix.py` | Add AI context features |
| `frontend/src/app/api/zl/context/route.ts` | Optional: inject previous days' analysis |

## Dependencies

- `analytics.ai_context_1d` table (migration)
- Existing `analytics.price_1d` for outcome tracking
- Existing event pulse + recommendation logic (already built)

## Estimated Effort

- DB table + migration: 30 min
- Snapshot cron: 1 hour
- Outcome backfill: 1 hour
- Matrix features: 2 hours
- Prompt memory: 1 hour
- Testing: 1 hour
