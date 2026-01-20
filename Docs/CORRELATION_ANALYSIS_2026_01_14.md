# ZINC-FUSION-V15: Correlation Analysis Results
## Date: 2026-01-14

This document records the empirical correlation analysis performed to inform specialist tagging decisions.

---

## 1. SIMPLE CORRELATIONS WITH ZL (2010-2025, N=4,007 days)

| Symbol | Name | Correlation | Category |
|--------|------|-------------|----------|
| ZS | Soybeans | **0.502** | Soy Complex |
| CL | Crude Oil | **0.287** | Energy |
| ZC | Corn | **0.280** | Grains/Biofuel |
| HG | Copper | **0.267** | Metals/China |
| SI | Silver | **0.226** | Metals |
| ZM | Soybean Meal | 0.147 | Soy Complex |
| GC | Gold | 0.138 | Metals |
| LE | Live Cattle | 0.111 | Livestock |
| HE | Lean Hogs | 0.051 | Livestock |
| GF | Feeder Cattle | 0.025 | Livestock |

---

## 2. REGIME-SPECIFIC CORRELATIONS

### High Volatility vs Low Volatility

| Symbol | All Days | High Vol | Low Vol | Insight |
|--------|----------|----------|---------|---------|
| ZS | 0.502 | **0.604** | 0.467 | Stronger in crisis |
| CL | 0.287 | **0.325** | 0.271 | Stronger in crisis |
| HG | 0.267 | **0.293** | 0.259 | Stronger in crisis |
| SI | 0.226 | **0.281** | 0.201 | Stronger in crisis |
| HE | 0.051 | **0.102** | 0.027 | 2x in high vol |
| LE | 0.111 | **0.135** | 0.105 | Slightly stronger |

**Insight:** Correlations increase during high volatility - important for risk management.

### Bull vs Bear Markets

| Symbol | Bull | Bear | Insight |
|--------|------|------|---------|
| ZS | **0.595** | 0.541 | Stronger in rallies |
| CL | 0.270 | **0.324** | Stronger in selloffs |
| HE | **0.103** | 0.056 | Stronger in rallies |

---

## 3. PREDICTIVE RELATIONSHIPS (Granger-style)

Does yesterday's return of X predict today's ZL return?

| Symbol | Beta | t-stat | p-value | Predictive? |
|--------|------|--------|---------|-------------|
| **HG (Copper)** | 0.034 | 2.09 | **0.037** | ✅ YES |
| **SI (Silver)** | 0.027 | 2.12 | **0.034** | ✅ YES |
| ZS | 0.017 | 1.06 | 0.288 | No |
| HE | -0.014 | -1.68 | 0.093 | No (marginal) |
| CL | 0.005 | 0.55 | 0.582 | No |
| ZC | 0.002 | 0.15 | 0.884 | No |

**Key Finding:** Copper and Silver have statistically significant predictive power for ZL.

---

## 4. ROLLING CORRELATION STABILITY (252-day window)

| Symbol | Mean | Std | Range | Stable? |
|--------|------|-----|-------|---------|
| ZS | 0.555 | 0.159 | 0.19-0.90 | Variable |
| CL | 0.294 | 0.099 | 0.10-0.56 | ✅ Stable |
| HG | 0.267 | 0.124 | 0.02-0.58 | Variable |
| SI | 0.238 | 0.093 | 0.01-0.39 | ✅ Stable |
| LE | 0.110 | 0.079 | -0.06-0.33 | ✅ Stable |
| HE | 0.050 | 0.092 | -0.19-0.28 | ✅ Stable |

---

## 5. CHINA LINKAGE ANALYSIS (2015-2025)

| Pair | Correlation | Interpretation |
|------|-------------|----------------|
| **HG ↔ FXI** | **0.370** | Copper is strong China proxy |
| HG ↔ KWEB | 0.302 | |
| SI ↔ FXI | 0.227 | Silver moderate China link |
| ZL ↔ FXI | 0.158 | ZL has some China exposure |

**Conclusion:** Copper (HG) is the strongest China industrial proxy among metals.

---

## 6. TAGGING RECOMMENDATIONS

### Based on Empirical Evidence:

| Symbol | Recommended Tags | Rationale |
|--------|------------------|-----------|
| **SI (Silver)** | `['volatility']` | Macro risk proxy, predicts ZL (p=0.034), stable correlation |
| **HG (Copper)** | `['china', 'volatility']` | Strong China proxy (r=0.37 with FXI), predicts ZL (p=0.037) |
| **CU (Copper mini)** | `['china', 'volatility']` | Same as HG |
| **HE (Lean Hogs)** | `['substitutes', 'crush']` | Feed demand linkage, 18% of US soy meal consumption |
| **LE (Live Cattle)** | `['substitutes']` | Protein demand, stable correlation |
| **GF (Feeder Cattle)** | `['substitutes']` | Protein demand, weak but stable |

### Key Changes from Original Proposal:
1. **Copper → add `china`** - Empirically validated as China proxy
2. **Livestock → keep `substitutes`** - Correlation is weak (0.02-0.11) but fundamental feed linkage is real
3. **Silver → keep `volatility` only** - Not strong enough for other tags

---

## 7. LAGGED CORRELATIONS

No significant lead-lag relationships found - all best correlations at Lag=0.
This means we should use **contemporaneous** features, not lagged.

---

## Appendix: Correlation Matrix (2010-2025)

```
        ZL     ZS     ZM     ZC     HE     LE     HG     SI     CL
ZL   1.000  0.502  0.147  0.280  0.051  0.111  0.267  0.226  0.287
ZS   0.502  1.000  0.425  0.520  0.102  0.142  0.305  0.243  0.304
ZM   0.147  0.425  1.000  0.324  0.074  0.049  0.144  0.079  0.164
ZC   0.280  0.520  0.324  1.000  0.096  0.094  0.307  0.213  0.288
HE   0.051  0.102  0.074  0.096  1.000  0.481  0.113  0.066  0.076
LE   0.111  0.142  0.049  0.094  0.481  1.000  0.119  0.081  0.076
HG   0.267  0.305  0.144  0.307  0.113  0.119  1.000  0.540  0.452
SI   0.226  0.243  0.079  0.213  0.066  0.081  0.540  1.000  0.338
CL   0.287  0.304  0.164  0.288  0.076  0.076  0.452  0.338  1.000
```

---

*Analysis performed using mkt.futures_1d and mkt.equity_1d data.*
*Scripts: correlation_analysis_zl.py, deep_correlation_analysis.py*
