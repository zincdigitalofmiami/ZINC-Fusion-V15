# Options & Volatility Features — Dashboard Design Reference

## Layer 2: Derived Features (Model Training)

Aggregated daily signals that move the needle:

| Feature | Description | Why It Matters |
|---------|-------------|----------------|
| `iv_atm` | At-the-money implied vol | Market's forward vol expectation |
| `iv_atm_z` | Z-score vs 63d rolling | Is vol elevated? |
| `iv_atm_pct` | Percentile rank (1yr) | Regime detection |
| `iv_skew_25d` | 25Δ put IV − 25Δ call IV | Tail risk premium |
| `iv_term_slope` | Front month vs 3rd month | Uncertainty timing |
| `iv_term_curve` | Full term structure (JSON) | Where fear is priced |
| `pcr_oi` | Put/Call OI ratio | Positioning sentiment |
| `pcr_vol` | Put/Call volume ratio | Flow sentiment |
| `iv_rv_spread` | IV minus realized vol | Overpriced/underpriced vol |
| `gamma_exposure_net` | Net dealer gamma | Flow-driven support/resistance |
| `vanna_exposure` | Vol sensitivity to spot | Reflexivity risk |

---

## Layer 3: Cross-Asset Vol Signals

Don't just use SOYB — capture contagion:

| ETF | Proxy For | Signal Value |
|-----|-----------|--------------|
| **SOYB** | Soybean/ZL direct | Primary |
| **DBA** | Agriculture basket | Sector sentiment |
| **CORN** | Corn (crush substitute) | Crush spread vol |
| **USO** | Crude oil | Energy/biofuel demand |
| **EEM** | Emerging markets | China/Brazil demand |
| **FXI** | China equities | Demand shock risk |

---

## Dashboard Visualization Ideas

### Volatility Surface (3D)
- X-axis: Strike price (moneyness)
- Y-axis: Days to expiration
- Z-axis / Color: Implied volatility
- Interactive hover showing exact IV, Greeks

### Term Structure Curve
- ATM IV plotted by expiration date
- Overlay historical percentile bands (10th/25th/75th/90th)
- Highlight inversions (backwardation = near-term fear)

### Vol Skew Chart
- 25-delta risk reversal over time
- Positive = calls bid (bullish sentiment)
- Negative = puts bid (tail hedging)

### Open Interest Heatmap
- Strike × Expiry grid
- Color intensity = OI concentration
- Highlights "max pain" and support/resistance levels

### Historical Vol Cone
- Current IV vs realized vol percentile bands
- Shows if options are cheap/expensive vs history

### Put/Call Ratio Dashboard
- PCR OI (positioning) vs PCR Volume (flow)
- Rolling averages with extremes highlighted
- Contrarian signal at extremes

---

## Data Source

- **Provider**: Massive.com (formerly Polygon.io)
- **API**: REST API with free tier (2 years historical)
- **Coverage**: OPRA (all US equity/ETF options)
- **Rate Limit**: 5 calls/min (free tier)
- **Tables**: 
  - `raw.options_equity_1d` (contract-level OHLCV)
  - `analytics.options_surface_1d` (computed IV grid)
  - `gold.options_features_1d` (derived features for training)
