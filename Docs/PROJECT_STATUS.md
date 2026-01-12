# ZINC-FUSION-V15 Project Status

**Last Updated:** 2026-01-03

## What's WORKING

### Core Models (in `models/core_v15/`)
| Horizon | Status | WQL Score | Best Model | Path |
|---------|--------|-----------|------------|------|
| 5d | ✅ Complete | 0.0090 | WeightedEnsemble | `models/core_v15/horizon_5d` |
| 21d | ✅ Complete | 0.0115 | WeightedEnsemble | `models/core_v15/horizon_21d` |
| 63d | ❌ Incomplete | - | - | Needs training |
| 126d | ❌ Not started | - | - | Needs training |

### Database (Prisma Postgres)
- **Connection:** ✅ Working (`DATABASE_URL` in `.env`)
- **Host:** db.prisma.io:5432
- **Tables with data:**
  - `model.model_registry` - 18 models (4 with MASE scores)
  - `model.training_runs` - 6 runs
  - `model.data_quality_metrics` - 10 sources
  - `raw.*` tables - Market, FRED, Weather, etc.
  - `training.specialist_*` - 10 of 11 specialists populated

### Specialist Feature Tables
| Specialist | Status | Rows |
|------------|--------|------|
| biofuel | ✅ | 42K |
| china | ✅ | 27K |
| crush | ✅ | 23K |
| energy | ✅ | 45K |
| fed | ✅ | 48K |
| fx | ✅ | 80K |
| palm | ✅ | 24K |
| substitutes | ✅ | 42K |
| tariff | ✅ | 42K |
| volatility | ✅ | 35K |
| **trump_effect** | ❌ EMPTY | 0 |

### Grafana
- **Local:** Running at http://localhost:3000
- **Login:** admin / admin
- **Datasource:** Connected to Prisma Postgres ✅
- **Dashboard:** `ZINC-Fusion Model Registry` exists

---

## What's NOT WORKING / INCOMPLETE

1. **Trump Effect Features** - Table exists but EMPTY, needs feature generation
2. **Core 63d/126d Models** - Not trained yet
3. **Specialist Models** - None actually trained (only features exist)
4. **Grafana Dashboard** - May need manual refresh or query fix

---

## Key Files & Paths

```
models/
├── core_v15/           # ← CURRENT production models
│   ├── horizon_5d/     # ✅ Complete
│   ├── horizon_21d/    # ✅ Complete
│   └── horizon_63d/    # ❌ Incomplete
├── core_chronos2/      # Old/interrupted - IGNORE
├── core_chronos/       # Legacy - IGNORE
└── specialists/        # Not trained yet

src/fusion/
├── grafana_registry.py # MOVED to grafana/ folder
├── taxonomy.py         # 11 specialists defined
└── features/
    └── trump_effect.py # Trump effect feature engine

grafana/
├── start-grafana.sh    # Start script
├── dashboards/         # Dashboard JSON
└── provisioning/       # Datasource config
```

---

## Next Steps (Priority Order)

1. **Verify Grafana showing data** - Check dashboard queries
2. **Generate trump_effect features** - Populate the empty table
3. **Train 63d core model** - Complete the core set
4. **Train specialist models** - 11 specialists × 4 horizons

---

## Quick Commands

```bash
# Start Grafana
cd grafana && ./start-grafana.sh

# Check database connection
.venv/bin/python -c "import psycopg2; from dotenv import load_dotenv; import os; load_dotenv(); print(psycopg2.connect(os.getenv('DATABASE_URL')).cursor().execute('SELECT 1'))"

# Load a trained model
.venv/bin/python -c "from autogluon.timeseries import TimeSeriesPredictor; p = TimeSeriesPredictor.load('models/core_v15/horizon_21d'); print(p.leaderboard())"
```
