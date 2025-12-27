# ZINC-FUSION Dashboard

## Overview

Multi-page dashboard for ZL (Soybean Oil) procurement forecasting and decision support.

**Client:** US Oil Solutions  
**Purpose:** Probabilistic multi-horizon forecasts (1W/1M/3M/6M) supporting procurement timing and hedge sizing decisions.

---

## Dashboard Architecture

```
dashboard/
├── README.md                 # This file
├── pages/                    # Page components
│   ├── overview/             # Executive summary page
│   ├── crush/                # Crush spread analytics
│   ├── china/                # China demand signals
│   ├── palm/                 # Palm oil & substitution
│   ├── volatility/           # Volatility regime analysis
│   ├── energy/               # Energy complex
│   ├── biofuel/              # RIN & LCFS policy
│   ├── substitutes/          # Canola & alternatives
│   ├── fx/                   # Currency effects
│   ├── fed/                  # Macro/Fed policy
│   ├── tariff/               # Trade policy uncertainty
│   └── forecast/             # Model outputs & signals
├── components/               # Reusable UI components
│   ├── charts/               # Chart components
│   ├── indicators/           # Signal displays
│   ├── bands/                # Bollinger/percentile bands
│   └── layout/               # Layout components
├── hooks/                    # Data fetching hooks
├── utils/                    # Helper functions
├── styles/                   # Global styles
├── config/                   # Dashboard configuration
├── api/                      # API route handlers
└── assets/                   # Static assets
```

---

## Big-10 Bucket Feature Inventory

### Data Source
All dashboard features are computed in:
```
src/quickstart_etl/features/specialist_buckets.py
```

---

## 1. CRUSH Bucket (Chris Main)

**Page:** `/pages/crush/`

### Available Features

| Feature | Column Name | Type | Description |
|---------|-------------|------|-------------|
| **Bollinger Bands** | `crush_bb_upper`, `crush_bb_middle`, `crush_bb_lower` | Overlay | 20-day, 2σ bands on crush spread |
| **BB Position** | `crush_bb_pct` | 0-100 | Where price sits within bands |
| **Oil Share Bands** | `oil_share_bb_upper`, `oil_share_bb_middle`, `oil_share_bb_lower` | Overlay | Bands on ZL share of crush |
| **Percentile Bands** | `crush_pct_90`, `crush_pct_75`, `crush_pct_50`, `crush_pct_25`, `crush_pct_10` | Overlay | 252-day rolling percentiles |
| **Percentile Rank** | `crush_percentile` | 0-100 | Current percentile position |
| **Signal Strength** | `crush_signal_strength` | 0-100 | Confidence metric from z-score |
| **Squeeze Probability** | `crush_squeeze_prob` | 0-1 | Probability crush is compressed |
| **Wide Probability** | `crush_wide_prob` | 0-1 | Probability crush is elevated |
| **Composite Signal** | `crush_bucket_signal` | Float | Aggregated bucket signal |
| **Confidence** | `crush_bucket_confidence` | 0-100 | Signal confidence score |
| **Moving Averages** | `crush_sma_10`, `crush_sma_21`, `crush_sma_63`, `crush_sma_200` | Overlay | Simple moving averages |
| **EMAs** | `crush_ema_10`, `crush_ema_21` | Overlay | Exponential moving averages |
| **Divergence** | `crush_spread_divergence` | Float | Price vs crush divergence |

### Visualization Recommendations
- Primary chart: Crush spread with Bollinger Bands overlay
- Secondary: Oil share % with historical percentile bands
- Gauges: Squeeze/Wide probability meters
- Signal panel: Composite signal with confidence bar

---

## 2. CHINA Bucket (Chris Main)

**Page:** `/pages/china/`

### Available Features

| Feature | Column Name | Type | Description |
|---------|-------------|------|-------------|
| **Copper Bollinger** | `hg_bb_upper`, `hg_bb_middle`, `hg_bb_lower` | Overlay | 20-day, 2σ bands on HG copper |
| **BB Position** | `hg_bb_pct` | 0-100 | Copper position in bands |
| **Percentile Bands** | `hg_pct_90`, `hg_pct_75`, `hg_pct_50`, `hg_pct_25`, `hg_pct_10` | Overlay | 252-day rolling percentiles |
| **Percentile Rank** | `hg_percentile` | 0-100 | Current copper percentile |
| **Signal Strength** | `hg_signal_strength` | 0-100 | Confidence from z-score |
| **Bullish Probability** | `hg_bullish_prob` | 0-1 | Probability copper bullish |
| **Demand Regime** | `china_demand_regime` | Category | strong/moderate/weak classification |
| **CNY Devalue Prob** | `cny_devalue_prob` | 0-1 | Yuan devaluation risk |
| **Composite Signal** | `china_bucket_signal` | Float | Aggregated China signal |
| **Confidence** | `china_bucket_confidence` | 0-100 | Signal confidence score |
| **Correlations** | `hg_zl_corr_21d`, `hg_zl_corr_60d`, `hg_zl_corr_252d` | -1 to 1 | Rolling correlations |
| **Beta** | `hg_zl_beta_60d` | Float | ZL beta to copper |

### Visualization Recommendations
- Primary: Copper price with Bollinger overlay
- Regime indicator: Demand strength gauge (strong/moderate/weak)
- Probability panel: CNY devaluation risk meter
- Correlation tracker: Rolling correlation sparklines

---

## 3. PALM Bucket (Chris Main)

**Page:** `/pages/palm/`

### Available Features

| Feature | Column Name | Type | Description |
|---------|-------------|------|-------------|
| **Palm Bollinger** | `palm_bb_upper`, `palm_bb_middle`, `palm_bb_lower` | Overlay | 20-day, 2σ bands on palm oil |
| **BB Position** | `palm_bb_pct` | 0-100 | Palm position in bands |
| **ZL-Palm Spread BB** | `zl_palm_spread_bb_upper`, `zl_palm_spread_bb_middle`, `zl_palm_spread_bb_lower` | Overlay | Bands on ZL premium to palm |
| **Spread BB Position** | `zl_palm_spread_bb_pct` | 0-100 | Spread position in bands |
| **Percentile Bands** | `palm_pct_90`, `palm_pct_75`, `palm_pct_50`, `palm_pct_25`, `palm_pct_10` | Overlay | 252-day rolling percentiles |
| **Percentile Rank** | `palm_percentile` | 0-100 | Current palm percentile |
| **Signal Strength** | `palm_signal_strength` | 0-100 | Confidence from z-score |
| **Palm Premium Prob** | `palm_premium_prob` | 0-1 | Probability palm at premium |
| **ZL Premium Prob** | `zl_premium_prob` | 0-1 | Probability ZL at premium to palm |
| **Substitution Signal** | `palm_substitution_signal` | Float | Net substitution pressure |
| **Confidence** | `palm_bucket_confidence` | 0-100 | Signal confidence score |
| **Inventory Regime** | `palm_inventory_regime` | Category | tight/normal/surplus |
| **Production Regime** | `palm_production_regime` | Category | high/normal/low |
| **Moving Averages** | `palm_sma_10`, `palm_sma_21`, `palm_sma_63`, `palm_sma_200` | Overlay | Simple moving averages |
| **Support/Resistance** | `palm_52w_high`, `palm_52w_low`, `palm_range_position` | Levels | Key price levels |

### Visualization Recommendations
- Dual chart: Palm price + ZL-Palm spread with Bollinger overlays
- Regime panels: Inventory and production status indicators
- Probability gauges: Premium probabilities for both oils
- Key levels: 52-week high/low markers

---

## 4. VOLATILITY Bucket (Chris Main)

**Page:** `/pages/volatility/`

### Available Features

| Feature | Column Name | Type | Description |
|---------|-------------|------|-------------|
| **VIX Bollinger** | `vix_bb_upper`, `vix_bb_middle`, `vix_bb_lower` | Overlay | 20-day, 2σ bands on VIX |
| **VIX BB Position** | `vix_bb_pct` | 0-100 | VIX position in bands |
| **VIX Percentiles** | `vix_pct_90`, `vix_pct_75`, `vix_pct_50`, `vix_pct_25`, `vix_pct_10` | Overlay | 252-day rolling percentiles |
| **VIX Percentile Rank** | `vix_percentile` | 0-100 | Current VIX percentile |
| **Realized Vol BB** | `rv_bb_upper`, `rv_bb_middle`, `rv_bb_lower` | Overlay | Bands on realized volatility |
| **RV BB Position** | `rv_bb_pct` | 0-100 | RV position in bands |
| **RV Percentiles** | `rv_pct_90`, `rv_pct_75`, `rv_pct_50`, `rv_pct_25`, `rv_pct_10` | Overlay | RV percentile bands |
| **Fear Probability** | `vix_fear_prob` | 0-1 | Probability of elevated fear |
| **Complacent Probability** | `vix_complacent_prob` | 0-1 | Probability of complacency |
| **Crisis Probability** | `vix_crisis_prob` | 0-1 | Probability of crisis regime |
| **Composite Signal** | `vol_bucket_signal` | Float | Aggregated vol signal |
| **Confidence** | `vol_bucket_confidence` | 0-100 | Signal confidence score |
| **Signal Strength** | `vol_signal_strength` | 0-100 | Volatility signal strength |

### Visualization Recommendations
- Primary: VIX with Bollinger bands + percentile shading
- Overlay: Realized vs Implied volatility comparison
- Fear/Greed gauge: Three-state indicator (fear/neutral/complacent)
- Crisis alert: Prominent crisis probability display

---

## 5. ENERGY Bucket

**Page:** `/pages/energy/`

### Available Features

| Feature | Column Name | Type | Description |
|---------|-------------|------|-------------|
| **BOHO Bollinger** | `boho_bb_upper`, `boho_bb_middle`, `boho_bb_lower` | Overlay | Bands on bean oil/heating oil ratio |
| **BOHO BB Position** | `boho_bb_pct` | 0-100 | BOHO position in bands |
| **Crude Bollinger** | `cl_bb_upper`, `cl_bb_middle`, `cl_bb_lower` | Overlay | Bands on WTI crude |
| **Crude BB Position** | `cl_bb_pct` | 0-100 | Crude position in bands |
| **Crude Percentiles** | `cl_pct_90`, `cl_pct_75`, `cl_pct_50`, `cl_pct_25`, `cl_pct_10` | Overlay | Crude percentile bands |
| **Crack Spread BB** | `crack_bb_upper`, `crack_bb_middle`, `crack_bb_lower` | Overlay | Bands on crack spread |
| **Crack BB Position** | `crack_bb_pct` | 0-100 | Crack spread position |
| **Composite Signal** | `energy_bucket_signal` | Float | Aggregated energy signal |
| **Confidence** | `energy_bucket_confidence` | 0-100 | Signal confidence score |

### Visualization Recommendations
- Multi-panel: BOHO ratio, Crude, and Crack spread with bands
- Energy complex heatmap
- Regime classification display

---

## 6. BIOFUEL Bucket

**Page:** `/pages/biofuel/`

### Available Features

| Feature | Column Name | Type | Description |
|---------|-------------|------|-------------|
| **RIN D4 Bollinger** | `rin_d4_bb_upper`, `rin_d4_bb_middle`, `rin_d4_bb_lower` | Overlay | Bands on D4 RIN prices |
| **RIN BB Position** | `rin_d4_bb_pct` | 0-100 | RIN position in bands |
| **RIN Percentiles** | `rin_d4_pct_90`, `rin_d4_pct_75`, `rin_d4_pct_50`, `rin_d4_pct_25`, `rin_d4_pct_10` | Overlay | RIN percentile bands |
| **LCFS Bollinger** | `lcfs_bb_upper`, `lcfs_bb_middle`, `lcfs_bb_lower` | Overlay | Bands on CA LCFS credits |
| **LCFS BB Position** | `lcfs_bb_pct` | 0-100 | LCFS position in bands |
| **Composite Signal** | `biofuel_bucket_signal` | Float | Aggregated biofuel signal |

### Visualization Recommendations
- Dual chart: RIN prices + LCFS credits with bands
- Policy calendar overlay (RVO deadlines, etc.)
- Mandate compliance tracker

---

## 7. SUBSTITUTES Bucket

**Page:** `/pages/substitutes/`

### Available Features

| Feature | Column Name | Type | Description |
|---------|-------------|------|-------------|
| **Canola Bollinger** | `canola_bb_upper`, `canola_bb_middle`, `canola_bb_lower` | Overlay | Bands on canola oil |
| **Canola BB Position** | `canola_bb_pct` | 0-100 | Canola position in bands |
| **ZL-Canola Spread Z** | `zl_canola_spread_zscore` | Z-score | Spread standardized score |
| **Composite Signal** | `substitutes_bucket_signal` | Float | Aggregated substitution signal |

### Visualization Recommendations
- Spread chart: ZL vs Canola with historical context
- Substitution pressure indicator
- Relative value matrix

---

## 8. FX Bucket

**Page:** `/pages/fx/`

### Available Features

| Feature | Column Name | Type | Description |
|---------|-------------|------|-------------|
| **BRL Percentiles** | `brl_pct_90`, `brl_pct_75`, `brl_pct_50`, `brl_pct_25`, `brl_pct_10` | Overlay | BRL/USD percentile bands |
| **BRL Percentile Rank** | `brl_percentile` | 0-100 | Current BRL percentile |
| **BRL Stress Prob** | `brl_stress_prob` | 0-1 | Probability of BRL stress |
| **Composite Signal** | `fx_bucket_signal` | Float | Aggregated FX signal |

### Visualization Recommendations
- Currency chart: BRL/USD with percentile bands
- EM stress indicator panel
- Export competitiveness gauge

---

## 9. FED Bucket

**Page:** `/pages/fed/`

### Available Features

| Feature | Column Name | Type | Description |
|---------|-------------|------|-------------|
| **Fed Funds Percentiles** | `fed_funds_pct_90`, `fed_funds_pct_75`, `fed_funds_pct_50`, `fed_funds_pct_25`, `fed_funds_pct_10` | Overlay | Fed funds percentile bands |
| **Fed Funds Percentile** | `fed_funds_percentile` | 0-100 | Current fed funds percentile |
| **NFCI Percentiles** | `nfci_pct_90`, `nfci_pct_75`, `nfci_pct_50`, `nfci_pct_25`, `nfci_pct_10` | Overlay | NFCI percentile bands |
| **NFCI Percentile** | `nfci_percentile` | 0-100 | Current NFCI percentile |
| **Tight Conditions Prob** | `nfci_tight_prob` | 0-1 | Probability of tight conditions |
| **Composite Signal** | `fed_bucket_signal` | Float | Aggregated Fed/macro signal |
| **Signal Strength** | `fed_signal_strength` | 0-100 | Fed signal confidence |

### Visualization Recommendations
- Fed funds rate with historical bands
- Financial conditions index (NFCI) chart
- Policy tightness gauge
- FOMC calendar overlay

---

## 10. TARIFF Bucket

**Page:** `/pages/tariff/`

### Available Features

| Feature | Column Name | Type | Description |
|---------|-------------|------|-------------|
| **EPU Percentiles** | `epu_pct_90`, `epu_pct_75`, `epu_pct_50`, `epu_pct_25` | Overlay | Policy uncertainty bands |
| **EPU Percentile Rank** | `epu_percentile` | 0-100 | Current EPU percentile |
| **EPU Signal Strength** | `epu_signal_strength` | 0-100 | EPU confidence metric |
| **Trade Escalation Prob** | `trade_escalation_prob` | 0-1 | Probability of trade tensions |
| **Composite Signal** | `tariff_bucket_signal` | Float | Aggregated tariff signal |
| **Signal Strength** | `tariff_signal_strength` | 0-100 | Tariff signal confidence |

### Visualization Recommendations
- EPU index with historical percentile shading
- Trade tension escalation gauge
- Tariff timeline/calendar
- Policy announcement tracker

---

## Standard Component Library

### Chart Types Needed

1. **Time Series with Bands**
   - Bollinger Band overlay
   - Percentile band shading
   - Moving average lines

2. **Probability Gauges**
   - Semi-circular meters (0-100%)
   - Color-coded thresholds

3. **Signal Strength Bars**
   - Horizontal progress bars
   - Confidence indicators

4. **Regime Indicators**
   - Categorical status badges
   - Traffic light displays

5. **Correlation Matrices**
   - Heatmap grids
   - Rolling correlation sparklines

6. **Key Level Markers**
   - Support/resistance lines
   - 52-week high/low annotations

---

## Page Structure Template

Each bucket page should follow this structure:

```
/pages/{bucket}/
├── index.tsx              # Main page component
├── components/
│   ├── PrimaryChart.tsx   # Main visualization
│   ├── SignalPanel.tsx    # Composite signal display
│   ├── ProbabilityGauges.tsx
│   └── RegimeIndicator.tsx
├── hooks/
│   └── use{Bucket}Data.ts # Data fetching
└── utils/
    └── {bucket}Calculations.ts
```

---

## Data Flow

```
DuckDB (fusion.db)
    │
    ▼
specialist_buckets.py (Feature Computation)
    │
    ▼
API Layer (/api/buckets/{bucket})
    │
    ▼
Dashboard Pages (React/Vue/Next.js)
```

---

## Development Notes

### Framework Agnostic
This skeleton is designed to work with:
- Next.js (Vercel)
- Vite + React
- Vue 3 + Vite
- SvelteKit
- Remix

### Key Dependencies (suggested)
- Charting: Recharts, Plotly, or Highcharts
- UI: Tailwind CSS, shadcn/ui, or Material UI
- State: React Query / TanStack Query
- Tables: TanStack Table

---

## Next Steps

1. [ ] Choose framework (Next.js recommended for Vercel)
2. [ ] Set up API routes for data fetching
3. [ ] Build component library (bands, gauges, signals)
4. [ ] Implement Overview page (executive summary)
5. [ ] Build Chris's mains first: CRUSH, CHINA, PALM, VOLATILITY
6. [ ] Add remaining bucket pages
7. [ ] Implement forecast/model output page

---

*Generated: December 21, 2025*  
*Source: specialist_buckets.py Big-10 Dashboard Feature Implementation*
