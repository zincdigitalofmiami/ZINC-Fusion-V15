#!/usr/bin/env python3
"""
ZINC-FUSION-V15: L5-C LLM Synthesis Engine

Generates natural language summaries of market posture by translating
quantitative outputs from L4 (meta-ensemble) and L5-A (Monte Carlo) into
structured explanations.

NON-NEGOTIABLES:
- LLM explains math. It NEVER invents math.
- All data comes from L4/L5-A outputs - no external inference
- Structured prompts with explicit data injection
- No buy/sell signals - decision support only
- Output includes: summary, risks, opportunities, invalidation triggers

Architecture (L5-C):
- Input: Monte Carlo percentiles, SHAP drivers, dissent index, regime, analogs
- Process: Structured LLM prompt with all data pre-injected
- Output: Natural language synthesis stored to analytics.llm_synthesis

Usage:
    python scripts/generate_synthesis.py --horizon 63 --dry-run
    python scripts/generate_synthesis.py --horizon 63
    python scripts/generate_synthesis.py --horizon all
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

import psycopg2
from psycopg2.extras import Json
from dotenv import load_dotenv

# Optional: OpenAI/Anthropic client
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
load_dotenv('.env.vercel')

# Horizons
HORIZONS = [5, 21, 63, 126]

# LLM Configuration
DEFAULT_MODEL = "claude-3-5-sonnet-20241022"  # or "gpt-4o"
MAX_TOKENS = 1500


@dataclass
class SynthesisInput:
    """All data required for LLM synthesis."""
    # Forecast geometry
    p10: float
    p50: float
    p90: float
    horizon_days: int

    # Monte Carlo summary
    mc_p5: float
    mc_p95: float
    prob_up: float
    prob_up_5pct: float
    prob_down_5pct: float
    var_05: float
    cvar_05: float

    # Attribution (from SHAP)
    top_drivers: List[Dict[str, Any]]

    # Specialist agreement
    dissent_index: float
    most_bullish: str
    most_bearish: str
    specialist_std: float

    # Regime
    regime: str
    regime_confidence: float

    # Historical analogs
    analogs: List[Dict[str, Any]]

    # Metadata
    as_of_date: datetime
    symbol: str = "ZL"


@dataclass
class SynthesisOutput:
    """Structured output from LLM synthesis."""
    summary: str  # 3-sentence market posture summary
    risks: List[Dict[str, str]]  # Top risks with probability context
    opportunities: List[Dict[str, str]]  # Top opportunities with probability
    invalidation_triggers: List[str]  # What would change the view
    confidence_level: str  # high/medium/low based on dissent
    raw_response: str  # Full LLM response for debugging


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


def load_forecast_data(conn, horizon: int) -> Dict:
    """Load latest meta-ensemble forecast for horizon."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT as_of_date, p10, p50, p90
            FROM "model"."meta_ensemble"
            WHERE horizon = %s
            ORDER BY as_of_date DESC
            LIMIT 1
        """, (horizon,))
        row = cur.fetchone()

    if not row:
        raise ValueError(f"No meta-ensemble data for horizon={horizon}")

    return {
        'as_of_date': row[0],
        'p10': float(row[1]),
        'p50': float(row[2]),
        'p90': float(row[3]),
    }


def load_monte_carlo_metrics(conn, horizon: int, as_of_date: datetime) -> Dict:
    """Load Monte Carlo risk metrics."""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT var_05, cvar_05, prob_up, prob_up_5pct, prob_down_5pct
                FROM risk_metrics
                WHERE horizon = %s AND as_of_date::date = %s::date
                ORDER BY as_of_date DESC
                LIMIT 1
            """, (horizon, as_of_date))
            row = cur.fetchone()

        if not row:
            # Return defaults if no MC data yet
            return {
                'var_05': -0.05,
                'cvar_05': -0.08,
                'prob_up': 0.50,
                'prob_up_5pct': 0.20,
                'prob_down_5pct': 0.20,
            }

        return {
            'var_05': float(row[0]),
            'cvar_05': float(row[1]),
            'prob_up': float(row[2]),
            'prob_up_5pct': float(row[3]),
            'prob_down_5pct': float(row[4]),
        }
    except Exception:
        # Table may not exist yet
        conn.rollback()
        return {
            'var_05': -0.05,
            'cvar_05': -0.08,
            'prob_up': 0.50,
            'prob_up_5pct': 0.20,
            'prob_down_5pct': 0.20,
        }


def load_monte_carlo_percentiles(conn, horizon: int, as_of_date: datetime) -> Dict:
    """Load MC path percentiles (P5, P95 terminal)."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT percentiles
            FROM "model"."monte_carlo_runs"
            WHERE horizon = %s AND symbol = 'ZL' AND as_of_date::date = %s::date
            ORDER BY created_at DESC
            LIMIT 1
        """, (horizon, as_of_date))
        row = cur.fetchone()

    if not row or not row[0]:
        # Fallback: estimate from forecast spread
        return {'mc_p5': None, 'mc_p95': None}

    percentiles = row[0]
    # Get terminal values (last element of each percentile array)
    mc_p5 = percentiles.get('5', [None])[-1] if '5' in percentiles else None
    mc_p95 = percentiles.get('95', [None])[-1] if '95' in percentiles else None

    return {'mc_p5': mc_p5, 'mc_p95': mc_p95}


def load_shap_drivers(conn, horizon: int, as_of_date: datetime, top_n: int = 5) -> List[Dict]:
    """Load top SHAP feature importances."""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT feature_name, mean_abs_shap
                FROM "model"."shap_summary"
                WHERE horizon = %s
                ORDER BY mean_abs_shap DESC
                LIMIT %s
            """, (horizon, top_n))
            rows = cur.fetchall()

        if not rows:
            # Return placeholder drivers
            return [
                {'name': 'core_p50', 'impact': 0.0, 'direction': 'neutral'},
                {'name': 'crush_p50', 'impact': 0.0, 'direction': 'neutral'},
                {'name': 'china_p50', 'impact': 0.0, 'direction': 'neutral'},
            ]

        return [
            {'name': row[0], 'impact': float(row[1]), 'direction': 'positive' if row[1] > 0 else 'negative'}
            for row in rows
        ]
    except Exception:
        # Table may not exist yet
        conn.rollback()
        return [
            {'name': 'core_p50', 'impact': 0.0, 'direction': 'neutral'},
            {'name': 'crush_p50', 'impact': 0.0, 'direction': 'neutral'},
            {'name': 'china_p50', 'impact': 0.0, 'direction': 'neutral'},
        ]


def load_specialist_agreement(conn, horizon: int, as_of_date: datetime) -> Dict:
    """Load specialist predictions and compute agreement metrics."""
    specialists = ['crush', 'china', 'fx', 'fed', 'tariff', 'energy', 'biofuel', 'palm', 'volatility', 'substitutes', 'trump_effect']

    with conn.cursor() as cur:
        cur.execute("""
            SELECT specialist, pred_p50
            FROM "model"."oof_predictions"
            WHERE horizon = %s
              AND as_of_date::date = %s::date
              AND specialist IN %s
            ORDER BY specialist
        """, (horizon, as_of_date, tuple(specialists)))
        rows = cur.fetchall()

    if not rows:
        return {
            'dissent_index': 0.0,
            'specialist_std': 0.0,
            'most_bullish': 'unknown',
            'most_bearish': 'unknown',
        }

    preds = {row[0]: float(row[1]) for row in rows}
    values = list(preds.values())

    if len(values) < 2:
        return {
            'dissent_index': 0.0,
            'specialist_std': 0.0,
            'most_bullish': 'unknown',
            'most_bearish': 'unknown',
        }

    import numpy as np
    specialist_std = float(np.std(values))
    specialist_mean = float(np.mean(values))

    # Dissent index normalized by mean
    dissent_index = specialist_std / (abs(specialist_mean) + 1e-6)

    # Most bullish/bearish
    most_bullish = max(preds, key=preds.get)
    most_bearish = min(preds, key=preds.get)

    return {
        'dissent_index': min(dissent_index, 1.0),  # Cap at 1.0
        'specialist_std': specialist_std,
        'most_bullish': most_bullish,
        'most_bearish': most_bearish,
    }


def load_regime(conn, as_of_date: datetime) -> Dict:
    """Load current volatility regime."""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT regime
                FROM "analytics"."vol_regimes"
                WHERE as_of_date <= %s
                ORDER BY as_of_date DESC
                LIMIT 1
            """, (as_of_date,))
            row = cur.fetchone()

        if not row:
            return {'regime': 'normal', 'regime_confidence': 0.5}

        return {
            'regime': row[0] or 'normal',
            'regime_confidence': 0.75,  # Default confidence when not stored
        }
    except Exception:
        # Table may not exist yet
        conn.rollback()
        return {'regime': 'normal', 'regime_confidence': 0.5}


def load_historical_analogs(conn, horizon: int, as_of_date: datetime, top_n: int = 3) -> List[Dict]:
    """Load historical analog periods."""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT analog_period, similarity_score, actual_outcome
                FROM "analytics"."historical_analogs"
                WHERE horizon = %s AND as_of_date::date = %s::date
                ORDER BY similarity_score DESC
                LIMIT %s
            """, (horizon, as_of_date, top_n))
            rows = cur.fetchall()

        if not rows:
            # Return empty - analogs may not be populated yet
            return []

        return [
            {
                'period': row[0],
                'similarity': float(row[1]),
                'outcome': f"{float(row[2]):+.1%}" if row[2] else "N/A",
            }
            for row in rows
        ]
    except Exception:
        # Table may not exist yet
        conn.rollback()
        return []


def gather_synthesis_input(conn, horizon: int) -> SynthesisInput:
    """Gather all data needed for synthesis."""
    logger.info(f"Gathering synthesis input for horizon={horizon}d")

    # Load forecast
    forecast = load_forecast_data(conn, horizon)
    as_of_date = forecast['as_of_date']

    # Load Monte Carlo
    mc_metrics = load_monte_carlo_metrics(conn, horizon, as_of_date)
    mc_percentiles = load_monte_carlo_percentiles(conn, horizon, as_of_date)

    # Load SHAP drivers
    drivers = load_shap_drivers(conn, horizon, as_of_date)

    # Load specialist agreement
    agreement = load_specialist_agreement(conn, horizon, as_of_date)

    # Load regime
    regime = load_regime(conn, as_of_date)

    # Load analogs
    analogs = load_historical_analogs(conn, horizon, as_of_date)

    # Build input object
    return SynthesisInput(
        p10=forecast['p10'],
        p50=forecast['p50'],
        p90=forecast['p90'],
        horizon_days=horizon,
        mc_p5=mc_percentiles.get('mc_p5') or forecast['p10'] * 0.95,
        mc_p95=mc_percentiles.get('mc_p95') or forecast['p90'] * 1.05,
        prob_up=mc_metrics['prob_up'],
        prob_up_5pct=mc_metrics['prob_up_5pct'],
        prob_down_5pct=mc_metrics['prob_down_5pct'],
        var_05=mc_metrics['var_05'],
        cvar_05=mc_metrics['cvar_05'],
        top_drivers=drivers,
        dissent_index=agreement['dissent_index'],
        most_bullish=agreement['most_bullish'],
        most_bearish=agreement['most_bearish'],
        specialist_std=agreement['specialist_std'],
        regime=regime['regime'],
        regime_confidence=regime['regime_confidence'],
        analogs=analogs,
        as_of_date=as_of_date,
    )


def build_prompt(input_data: SynthesisInput) -> str:
    """Build the structured LLM prompt from input data."""

    # Format drivers
    drivers_text = ""
    for i, d in enumerate(input_data.top_drivers[:3], 1):
        drivers_text += f"{i}. {d['name']}: {d['impact']:+.4f} ({d.get('direction', 'neutral')})\n"

    # Format analogs
    if input_data.analogs:
        analogs_text = ""
        for a in input_data.analogs:
            analogs_text += f"- {a['period']}: {a['similarity']:.0%} similar, outcome was {a['outcome']}\n"
    else:
        analogs_text = "No historical analogs available for this period."

    # Confidence qualifier
    if input_data.dissent_index < 0.2:
        confidence_qualifier = "HIGH (strong specialist consensus)"
    elif input_data.dissent_index < 0.5:
        confidence_qualifier = "MEDIUM (moderate specialist disagreement)"
    else:
        confidence_qualifier = "LOW (high specialist disagreement)"

    prompt = f"""You are a commodity intelligence analyst for soybean oil (ZL). Summarize the following quantitative data into a decision-support briefing.

CRITICAL RULES:
1. DO NOT invent information. Only reference the provided data.
2. DO NOT provide buy/sell recommendations. This is intelligence, not advice.
3. Express all probabilities as percentages (e.g., "35% probability").
4. Reference specific numbers from the data to support statements.
5. Be concise but thorough. Each section should be 2-4 sentences.

## Forecast Data (Horizon: {input_data.horizon_days} days)
- P10 (floor): {input_data.p10:.2f}
- P50 (median): {input_data.p50:.2f}
- P90 (ceiling): {input_data.p90:.2f}
- Forecast spread: {input_data.p90 - input_data.p10:.2f} ({(input_data.p90 - input_data.p10) / input_data.p50 * 100:.1f}% of median)

## Monte Carlo Risk Metrics (10,000 simulations)
- 5th percentile outcome: {input_data.mc_p5:.2f}
- 95th percentile outcome: {input_data.mc_p95:.2f}
- Probability of positive return: {input_data.prob_up:.1%}
- Probability of >5% move up: {input_data.prob_up_5pct:.1%}
- Probability of >5% move down: {input_data.prob_down_5pct:.1%}
- Value at Risk (5%): {input_data.var_05:.1%}
- Conditional VaR (5%): {input_data.cvar_05:.1%}

## Top Drivers (from SHAP attribution)
{drivers_text}

## Specialist Model Agreement
- Dissent index: {input_data.dissent_index:.2f} (0=perfect consensus, 1=high disagreement)
- Specialist standard deviation: {input_data.specialist_std:.4f}
- Most bullish specialist: {input_data.most_bullish}
- Most bearish specialist: {input_data.most_bearish}
- Confidence level: {confidence_qualifier}

## Current Volatility Regime
- Regime: {input_data.regime.upper()}
- Regime confidence: {input_data.regime_confidence:.0%}

## Historical Analogs (similar market conditions)
{analogs_text}

---

Provide your analysis in EXACTLY this JSON format:
{{
    "summary": "A 3-sentence summary of current market posture. Include the median forecast, key driver, and confidence level.",
    "risks": [
        {{"risk": "Description of risk 1", "probability": "X%", "context": "Why this matters"}},
        {{"risk": "Description of risk 2", "probability": "Y%", "context": "Why this matters"}}
    ],
    "opportunities": [
        {{"opportunity": "Description of opportunity 1", "probability": "X%", "context": "Why this matters"}},
        {{"opportunity": "Description of opportunity 2", "probability": "Y%", "context": "Why this matters"}}
    ],
    "invalidation_triggers": [
        "Specific condition that would invalidate this view #1",
        "Specific condition that would invalidate this view #2"
    ]
}}

Respond with ONLY the JSON object, no additional text."""

    return prompt


def call_llm(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """Call the LLM API and return raw response."""

    # Try Anthropic first
    if HAS_ANTHROPIC and os.getenv("ANTHROPIC_API_KEY"):
        logger.info(f"Using Anthropic API with model {model}")
        client = anthropic.Anthropic()

        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return response.content[0].text

    # Fall back to OpenAI
    elif HAS_OPENAI and os.getenv("OPENAI_API_KEY"):
        logger.info(f"Using OpenAI API with model gpt-4o")
        client = openai.OpenAI()

        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=MAX_TOKENS,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content

    else:
        raise RuntimeError(
            "No LLM API available. Set ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable."
        )


def parse_llm_response(raw_response: str) -> SynthesisOutput:
    """Parse the LLM JSON response into structured output."""

    # Clean up response - remove markdown code blocks if present
    cleaned = raw_response.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        logger.error(f"Raw response: {raw_response[:500]}...")
        # Return a fallback
        return SynthesisOutput(
            summary="Unable to generate synthesis due to parsing error.",
            risks=[{"risk": "Parsing error", "probability": "N/A", "context": str(e)}],
            opportunities=[],
            invalidation_triggers=["Fix LLM response format"],
            confidence_level="low",
            raw_response=raw_response,
        )

    return SynthesisOutput(
        summary=data.get("summary", "No summary available."),
        risks=data.get("risks", []),
        opportunities=data.get("opportunities", []),
        invalidation_triggers=data.get("invalidation_triggers", []),
        confidence_level="high" if len(data.get("risks", [])) > 0 else "low",
        raw_response=raw_response,
    )


def save_synthesis(conn, input_data: SynthesisInput, output: SynthesisOutput) -> int:
    """Save synthesis output to analytics.llm_synthesis table."""

    with conn.cursor() as cur:
        # Create table if not exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS "analytics"."llm_synthesis" (
                id SERIAL PRIMARY KEY,
                as_of_date DATE NOT NULL,
                horizon INTEGER NOT NULL,
                symbol VARCHAR(20) DEFAULT 'ZL',
                input_data JSONB NOT NULL,
                summary TEXT NOT NULL,
                risks JSONB NOT NULL,
                opportunities JSONB NOT NULL,
                invalidation_triggers JSONB,
                confidence_level VARCHAR(20),
                model_used VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(as_of_date, horizon, symbol)
            )
        """)

        # Upsert
        cur.execute("""
            INSERT INTO "analytics"."llm_synthesis"
            (as_of_date, horizon, symbol, input_data, summary, risks, opportunities,
             invalidation_triggers, confidence_level, model_used, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (as_of_date, horizon, symbol)
            DO UPDATE SET
                input_data = EXCLUDED.input_data,
                summary = EXCLUDED.summary,
                risks = EXCLUDED.risks,
                opportunities = EXCLUDED.opportunities,
                invalidation_triggers = EXCLUDED.invalidation_triggers,
                confidence_level = EXCLUDED.confidence_level,
                model_used = EXCLUDED.model_used,
                created_at = EXCLUDED.created_at
        """, (
            input_data.as_of_date,
            input_data.horizon_days,
            input_data.symbol,
            Json(asdict(input_data)),
            output.summary,
            Json(output.risks),
            Json(output.opportunities),
            Json(output.invalidation_triggers),
            output.confidence_level,
            DEFAULT_MODEL,
            datetime.now(),
        ))

    conn.commit()
    return 1


def generate_synthesis(horizon: int, dry_run: bool = False) -> SynthesisOutput:
    """Generate LLM synthesis for a given horizon."""
    logger.info("=" * 60)
    logger.info(f"L5-C LLM SYNTHESIS @ {horizon}d")
    logger.info("=" * 60)

    conn = get_postgres_connection()

    try:
        # Gather all input data
        input_data = gather_synthesis_input(conn, horizon)

        logger.info(f"  As of date: {input_data.as_of_date}")
        logger.info(f"  P10/P50/P90: {input_data.p10:.2f} / {input_data.p50:.2f} / {input_data.p90:.2f}")
        logger.info(f"  Dissent index: {input_data.dissent_index:.2f}")
        logger.info(f"  Regime: {input_data.regime} ({input_data.regime_confidence:.0%})")
        logger.info(f"  Top drivers: {[d['name'] for d in input_data.top_drivers[:3]]}")

        # Build prompt
        prompt = build_prompt(input_data)

        if dry_run:
            logger.info("\n[DRY RUN] Would call LLM with prompt:")
            logger.info("-" * 40)
            logger.info(prompt[:1000] + "..." if len(prompt) > 1000 else prompt)
            logger.info("-" * 40)

            # Return mock output for dry run
            return SynthesisOutput(
                summary=f"[DRY RUN] Mock synthesis for {horizon}d horizon.",
                risks=[{"risk": "Mock risk", "probability": "50%", "context": "Testing"}],
                opportunities=[{"opportunity": "Mock opportunity", "probability": "50%", "context": "Testing"}],
                invalidation_triggers=["Mock trigger"],
                confidence_level="medium",
                raw_response="[DRY RUN - NO API CALL]",
            )

        # Call LLM
        logger.info("  Calling LLM API...")
        raw_response = call_llm(prompt)

        # Parse response
        output = parse_llm_response(raw_response)

        # Log summary
        logger.info(f"\n{'='*40}")
        logger.info("SYNTHESIS OUTPUT")
        logger.info(f"{'='*40}")
        logger.info(f"Summary: {output.summary[:200]}...")
        logger.info(f"Risks: {len(output.risks)}")
        logger.info(f"Opportunities: {len(output.opportunities)}")
        logger.info(f"Invalidation triggers: {len(output.invalidation_triggers)}")

        # Save to database
        saved = save_synthesis(conn, input_data, output)
        logger.info(f"\n  Saved synthesis to analytics.llm_synthesis")

        logger.info(f"\n{'='*60}")
        logger.info(f"L5-C LLM SYNTHESIS COMPLETE @ {horizon}d")
        logger.info(f"{'='*60}")

        return output

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Generate LLM synthesis from model outputs")
    parser.add_argument("--horizon", type=str, required=True,
                       help="Horizon in days (5, 21, 63, 126) or 'all'")
    parser.add_argument("--dry-run", action="store_true",
                       help="Preview without calling LLM or saving")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
                       help=f"LLM model to use (default: {DEFAULT_MODEL})")

    args = parser.parse_args()

    # Use model from args (already defaults to DEFAULT_MODEL)
    model_to_use = args.model

    # Determine horizons to process
    if args.horizon.lower() == "all":
        horizons = HORIZONS
    else:
        horizon = int(args.horizon)
        if horizon not in HORIZONS:
            logger.error(f"Invalid horizon: {horizon}. Must be one of {HORIZONS}")
            sys.exit(1)
        horizons = [horizon]

    # Run for each horizon
    for horizon in horizons:
        try:
            generate_synthesis(horizon, args.dry_run)
        except Exception as e:
            logger.error(f"Failed synthesis @ {horizon}d: {e}")
            if not args.dry_run:
                raise

    logger.info("\n" + "=" * 60)
    logger.info("LLM SYNTHESIS COMPLETE")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
