# ZINC-FUSION-V15 Pulse Engine

## Overview

The Pulse Engine generates AI-powered Intel Drops for 11 specialist domains.
Each Intel Drop is pre-quantified intelligence that feeds into Alpha Stacks.

## Directory Structure

```
src/fusion/pulse/
├── __init__.py          # Module exports
├── schema.py            # Pydantic-style data classes + JSON schema
├── validators.py        # Response validation + error handling
├── engine.py            # Orchestration + AI integration
├── contracts/
│   ├── __init__.py      # Contract utilities
│   └── prompts/
│       ├── system.txt       # Shared system prompt (DEEP QUANT)
│       ├── crush.txt        # CRUSH specialist
│       ├── china.txt        # CHINA specialist
│       ├── fx.txt           # FX specialist
│       ├── fed.txt          # FED specialist
│       ├── tariff.txt       # TARIFF specialist
│       ├── energy.txt       # ENERGY specialist
│       ├── biofuel.txt      # BIOFUEL specialist
│       ├── palm.txt         # PALM specialist
│       ├── volatility.txt   # VOLATILITY specialist
│       ├── substitutes.txt  # SUBSTITUTES specialist
│       └── trump_effect.txt # TRUMP_EFFECT specialist
```

## 11 Specialist Domains

1. **CRUSH** - Soybean processing economics, margins, utilization
2. **CHINA** - Chinese demand, imports, policy, hog herd
3. **FX** - Currency dynamics (USD, BRL, CNY, ARS)
4. **FED** - Rates, liquidity, inflation, financial conditions
5. **TARIFF** - Trade policy, tariffs, sanctions, negotiations
6. **ENERGY** - Crude, diesel, refinery economics, biofuel blending
7. **BIOFUEL** - RFS, RINs, SAF, 45Z, renewable diesel
8. **PALM** - Malaysian/Indonesian palm oil, substitution
9. **VOLATILITY** - Vol regimes, skew, positioning, liquidity
10. **SUBSTITUTES** - Canola, sunflower, tallow, UCO competition
11. **TRUMP_EFFECT** - Macro-neural regime detector for policy

## Output Schema (pulse.v1)

```json
{
  "schema_version": "pulse.v1",
  "as_of_ts": "2026-01-09T14:00:00Z",
  "instrument": "CBOT:ZL",
  "domain": "BIOFUEL",
  "horizons": [
    {
      "horizon": "1W",
      "direction": 1,
      "pressure_cents": 0.85,
      "edge": 0.72,
      "driver_weights": {
        "technical": 0.15,
        "flows": 0.10,
        "macro": 0.08,
        "policy": 0.42,
        "weather": 0.05,
        "positioning": 0.12,
        "sentiment": 0.08
      },
      "top_drivers": [
        {
          "driver_id": "45z_credit_implementation",
          "label": "45Z Clean Fuel Credit uncertainty",
          "sign": 1,
          "weight": 0.22,
          "receipts": ["doc:treasury:45z-guidance"]
        }
      ],
      "regime_tags": ["policy_roulette"],
      "uncertainty_notes": ["EPA final rule timing uncertain"]
    }
  ],
  "benchmarks": [],
  "data_gaps": [],
  "quality_flags": ["OK"],
  "suggested_proto_stacks": [
    {
      "stack_name": "biofuel_policy_convergence",
      "signal_ids": ["rin_price", "rd_margin", "45z_uncertainty"],
      "rationale": "Three policy signals achieving lockstep"
    }
  ]
}
```

## Vocabulary

- **edge**: Confidence level (0-1)
- **pressure_cents**: Directional magnitude in cents/lb
- **receipts**: Evidence document IDs or URLs
- **proto_stacks**: Suggested Alpha Stack candidates
- **driver_weights**: Must sum to 1.0 (±0.01)

## Validation Rules

1. Output must be valid JSON only (no markdown)
2. Exactly 4 horizons in order: 1W, 1M, 3M, 6M
3. driver_weights must sum to 1.0 ± 0.01
4. edge must be between 0 and 1
5. direction must be -1 (SHORT), 0 (FLAT), or +1 (LONG)

## Integration

```python
from src.fusion.pulse import PulseEngine

engine = PulseEngine()

# Build prompt for a domain
prompt = engine.build_prompt(
    domain="BIOFUEL",
    as_of_ts="2026-01-09T14:00:00Z",
    signal_snapshot=signal_data,
    event_stream=events,
    receipt_ids=receipts,
    benchmark_summaries=benchmarks
)

# Send to AI (GPT, Grok, Claude)
response = ai_client.chat(
    system=engine.system_prompt,
    user=prompt
)

# Validate response
pulse_data = engine.validate_response(response.text)
```

## Database Storage (Prisma)

Intel Drops are stored in the `features.intel_drops` table:

```prisma
model IntelDrop {
  id              Int       @id @default(autoincrement())
  as_of_ts        DateTime
  domain          String
  horizon         String
  direction       Int
  pressure_cents  Float
  edge            Float
  driver_weights  Json
  top_drivers     Json
  regime_tags     String[]
  quality_flags   String[]
  data_gaps       String[]
  receipts        Json?
  quant_payload   Json
  source_model    String?
  created_at      DateTime  @default(now())
  
  @@unique([as_of_ts, domain, horizon])
  @@map("intel_drops")
  @@schema("features")
}
```

## Key Principles

1. **Go 100 feet deep** - Find drivers of drivers of drivers
2. **Neural connections** - Correlations humans miss
3. **Quantify everything** - No hand-waving
4. **Cite receipts** - Evidence for every claim
5. **Not limited to given sources** - Seek fire from anywhere
