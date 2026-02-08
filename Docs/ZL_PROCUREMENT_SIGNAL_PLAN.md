NOTE: Production is the dashboard/frontend, not the repo root.
# ZL Procurement Signal Plan (Draft)

Status: Draft for review. This document captures proposed monitoring and feature ideas
based on the latest strategy discussion. No schema or feature changes are implied.

## Intent

Build a focused, data-driven "Strategy" view for soybean oil (ZL) procurement that
tracks demand pressure, supply risk, and volatility without encoding buy/sell logic.

## Key Observations (From Discussion)

1) Plant-based demand tailwind implies palm oil dynamics are a critical substitute.
2) Agri-energy joint ventures are leading indicators of domestic oil demand lockup.
3) Volatility has been undervalued; it should be a primary risk driver, not a minor one.

## Proposed Signals (No Schema Changes)

### Substitutes / Palm Watch

- Track FCPO and related palm indicators to detect substitution pressure.
- Leverage existing palm specialist path (mkt.futures_1d + alt.profarmer_news / alt.policy_news).
- Add dashboard emphasis on palm vs ZL relative moves and divergence.

### Agri-Energy Partnerships (Leading Indicator)

- Maintain a watchlist of major crushers and energy firms (examples mentioned:
  ADM, Bunge, Chevron, Shell) and log JV announcements and expansions.
- Source via existing policy/news streams (`alt.policy_news`, `alt.profarmer_news`, `alt.executive_actions`) with entity + partnership tagging.
- Present as a "Demand Lockup" panel with timeline and intensity score.

### Volatility as Core Driver

- Promote volatility signals to first-class status on the strategy page.
- Use existing volatility data (econ.vol_indices_1d) and soy-complex specific vol
  where available in mkt.* / econ.* sources.
- Provide clear linkage to procurement risk rather than directional signaling.

## Data & Feature Notes (Proposed; Requires Approval)

- Entity extraction for JV/partnership events in `alt.policy_news` and `alt.profarmer_news`.
- A "Demand Lockup" feature derived from JV announcements and capacity headlines.
- A "Palm Substitution Pressure" feature using palm vs ZL price spreads.
- A "Volatility Regime" feature for procurement risk framing.

These are proposals only. Any new feature definitions require explicit approval.

## Dashboard Placement (Strategy Page)

- Panel 1: "Palm vs ZL Substitution" (price spread + trend)
- Panel 2: "Agri-Energy JV Tracker" (events + rolling intensity)
- Panel 3: "Volatility Regime" (risk level + recent shocks)

## Metrics (Model Evaluation Guidance)

- Prefer MAE/MASE and quantile coverage for model selection.
- Avoid MAPE as a primary metric for returns-based targets.

## Modeling Notes (Draft)

These notes capture the current modeling direction and need validation against
sources and internal experiments. They are not a commitment to new features.

### Principles

- Specialists should output scores/signals (or residuals), not direct price forecasts.
- Keep specialists lean: 1-2 strong signals beat 4-horizon predictions across 11 models.
- Core + meta-learner own the multi-horizon forecasts; specialists are inputs.
- Avoid overfitting by keeping the stacking layer shallow (weighted ensemble or ridge).

### Candidate Specialist Model Mapping (User-Provided; Needs Verification)

- Energy: VAR for ZL vs crude/RBOB spillovers.
- China: GPR on customs + shipping proxies.
- Biofuel policy: NLP sentiment score from EPA/USDA/policy text.
- Palm: error-correction model on ZL vs FCPO spread.
- Substitutes: random forest on price ratios across oils.
- Trump effect: event study or NLP sentiment to output a risk premium score.
- Fed: ARDL using rates and DXY.
- FX: LSTM on USD/BRL, USD/ARS, USD/CNY.
- Volatility: GARCH with VIX as an exogenous input.
- Tariff: rule-based or tree model on tariff schedules.
- Crush: XGBoost on crush margins (or TFT if multivariate structure is required).

### Core Training Policy (CPU-only, Full Model Zoo)

Core runs on CPU. Set guards **before** importing torch/autogluon:

```
TOKENIZERS_PARALLELISM=false
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
AUTOGLUON_DISABLE_RAY=1
PYTORCH_ENABLE_MPS_FALLBACK=1
PYTORCH_MPS_ENABLED=0
CUDA_VISIBLE_DEVICES=""
device = "cpu"
```

Core must try **ALL** AutoGluon-TimeSeries Model Zoo models via an explicit
`hyperparameters={...}` allowlist (model names may omit the “Model” suffix).
The full allowlist is maintained in `Docs/CORE_TRAINING_SPEC_LOCKED.md`.

AutoGluon trains the full allowlist, ranks models on validation/backtests, and
typically selects a **WeightedEnsemble** as best. No time limits are used.

Verification:
- `python -m fusion.core_training.run_pipeline --skip-matrix --horizons 5`
- `python -m fusion.core_training.run_pipeline --skip-matrix`
- Confirm logs show the full allowlist and a WeightedEnsemble selection

## Source Review TODO (Help Needed)

These claims are mostly verified but require a structured source review.
Add links/quotes and tag each statement with a source before using in outputs.

- Grease Connections soybean oil price guide (2025): https://greaseconnections.com/soybean-oil-price-guide-2025/
- CHS domestic soybean demand outlook (Aug 13, 2024): https://www.chsinc.com/news-and-stories/2024/08/13/domestic-soybean-demand-outlook
- IG trend-identification primer (Feb 10, 2025): https://www.ig.com/en/trading-strategies/understanding-market-trends-for-your-investing-decisions-250209
- USDA ERS Oil Crops Outlook (Dec 2025): URL needed
- 45Z tax credit policy uncertainty piece: URL needed
- Argus biofuel credit cut article: URL needed
- Foodcom soybean market review 2026: URL needed
- Mordor Intelligence market size report: URL needed
- Investing.com bullish 2026 note: URL needed
- Biodiesel Magazine USDA biofuel use report: URL needed
- Business Research Company market size report: URL needed
- StockInvest.us ZL forecast: URL needed
- ERS "Strong demand for soybean oil elevated U.S. prices in 2021 and 2022": URL needed

## Validation Path (When Implemented)

- Confirm data presence via Prisma queries against existing schemas.
- Verify coverage and null rates per signal table.
- For features: run `pytest -q` and targeted validation scripts.

## Open Questions

- Final watchlist for partnership tracking (confirm tickers/entities).
- Preferred volatility indices to prioritize for the strategy page.
- Confirm whether palm monitoring should be elevated in specialist weighting logic.
