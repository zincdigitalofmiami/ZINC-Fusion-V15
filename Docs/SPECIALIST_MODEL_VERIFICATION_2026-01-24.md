# Specialist Model Verification Report
**Date**: 2026-01-24  
**Auditor**: Claude  
**Status**: ✅ ALL 11 SPECIALISTS VERIFIED

Specialists are **unaffected** by the Core CPU-only policy.

---

## SPECIALIST #1: CRUSH
**File**: `src/fusion/specialists/xgb_signals.py:197-387`  
**Model Type**: XGBRegressor (or GradientBoostingRegressor fallback)

```python
# Lines 240-258
def _create_model(self):
    if HAS_XGBOOST:
        return xgb.XGBRegressor(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1,
        )
    else:
        return GradientBoostingRegressor(...)
```

**Features**: 
- Board crush z-score
- Oil share z-score  
- Crush momentum (5d/21d/63d)
- WASDE fundamentals

**Target**: 21-day forward ZL return

**Signal Contract**: 
- `signal_1` = model prediction
- `signal_2` = 21d crush momentum

---

## SPECIALIST #2: CHINA
**File**: `src/fusion/specialists/xgb_signals.py:571-805`  
**Model Type**: GradientBoostingRegressor

```python
# Lines 621-630
def _create_model(self):
    return GradientBoostingRegressor(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        subsample=0.8,
        min_samples_split=10,
        random_state=42,
    )
```

**Features**:
- Copper z-score (HG)
- CNY z-score
- BRL z-score (Brazil competition)
- BDRY/SBLK shipping z-score (whichever available)
- Seasonality encoding

**Target**: 21-day forward ZL return

**Signal Contract**:
- `signal_1` = model prediction
- `signal_2` = Brazil competition score

---

## SPECIALIST #3: SUBSTITUTES
**File**: `src/fusion/specialists/xgb_signals.py:394-564`  
**Model Type**: RandomForestRegressor

```python
# Lines 433-442
def _create_model(self):
    return RandomForestRegressor(
        n_estimators=100,
        max_depth=6,
        min_samples_split=10,
        min_samples_leaf=5,
        random_state=42,
        n_jobs=-1,
    )
```

**Features**:
- Spread z-scores vs canola/palm/sunflower/rapeseed
- Ratio z-scores
- Spread momentum
- Cross-correlations

**Target**: 21-day forward ZL return

**Signal Contract**:
- `signal_1` = model prediction
- `signal_2` = ZL richness score

---

## SPECIALIST #4: FX
**File**: `src/fusion/specialists/ardl_signals.py:49-828`  
**Model Type**: statsmodels.tsa.ardl.ARDL (Autoregressive Distributed Lag)

```python
# Lines 495-506
model = ARDL(
    y.values,
    lags=ar_lag,
    exog=X.values,
    order=dl_lag,
    trend='c',
)
result = model.fit()
```

**Features**:
- DXY
- BRL/USD
- CNY/USD
- MXN/USD
- AUD/USD with dynamic correlation-weighted trade weights
- Carry trade signal from interest rate differentials
- Optimal lag selection via AIC/BIC

**Signal Contract**:
- `signal_1` = FX pressure index (ARDL-based)
- `signal_2` = carry trade signal

---

## SPECIALIST #5: FED
**File**: `src/fusion/specialists/ardl_signals.py:835-1082`  
**Model Type**: Weighted z-score composite (ridge-style)

```python
# Ridge implemented as weighted z-score composite:
# - Fed funds z-score (weight: 0.25)
# - 10Y yield z-score (weight: 0.20)
# - Yield curve 2s10s z-score (weight: 0.20)
# - Real rate z-score (weight: 0.15)
# - NFCI z-score (weight: 0.20)
```

**Features**:
- Fed funds
- DGS10
- DGS2
- DGS3MO (short end proxy)
- T10YIE (breakeven inflation, if available)
- NFCI
- Yield curve dynamics
- Real rates

**Signal Contract**:
- `signal_1` = rates regime score
- `signal_2` = regime change momentum

---

## SPECIALIST #6: VOLATILITY
**File**: `src/fusion/specialists/garch_signals.py:34-286`  
**Model Type**: GJR-GARCH(1,1) with Student-t errors

```python
# Lines 96-103
model = arch_model(
    returns_pct,
    mean='Constant',
    vol='GARCH',
    p=1, o=1, q=1,  # o=1 for asymmetric term (GJR)
    dist='t'
)
result = model.fit(disp='off', show_warning=False)
```

**Features**:
- Realized volatility (21d rolling)
- VIX z-score
- VIX term structure (VIX - VIX3M)
- OVX

**Extras**: Asymmetric volatility modeling (leverage effect), backwardation detection

**Signal Contract**:
- `signal_1` = volatility regime (0-3 scale)
- `signal_2` = regime change probability

---

## SPECIALIST #7: ENERGY
**File**: `src/fusion/specialists/var_signals.py:52-503`  
**Model Type**: statsmodels.tsa.api.VAR with IRF and FEVD

```python
# Lines 217-221
model = VAR(returns)
result = model.fit(optimal_lag)

# Lines 236-244 (REAL IRF)
irf = result.irf(self.irf_horizon)  # 21-period impulse response
fevd = result.fevd(self.irf_horizon)  # Forecast Error Variance Decomposition
```

**Features**:
- CL (crude)
- HO (heating oil)
- RB (gasoline)
- BOHO spread
- 3-2-1 crack spread

**Extras**: Diebold-Yilmaz spillover index, cumulative impulse response CL→HO

**Signal Contract**:
- `signal_1` = energy spillover score (IRF-based)
- `signal_2` = spillover momentum

---

## SPECIALIST #8: PALM
**File**: `src/fusion/specialists/ecm_signals.py:203-600`  
**Model Type**: Ridge Regression on ECM features + Engle-Granger cointegration

```python
# Lines 131-136
def _create_model(self):
    return Ridge(
        alpha=1.0,
        fit_intercept=True,
        random_state=42,
    )

# Lines 311-312 (cointegration test)
score, pvalue, _ = coint(combined["zl"], combined["cpo"])
model = OLS(combined["zl"], combined["cpo"]).fit()
hedge_ratio = model.params.iloc[0]
```

**Features**:
- ECM residual z-score
- Spread z-score
- Mean reversion speed (half-life)
- Spread momentum
- ZL-CPO correlation

**Signal Contract**:
- `signal_1` = model prediction
- `signal_2` = mean reversion speed

---

## SPECIALIST #9: TARIFF
**File**: `src/fusion/specialists/event_signals.py:27-209`  
**Model Type**: Rules-based on EPU thresholds

```python
# Lines 80-89 (spike detection)
def _detect_epu_spike(self, zscore: pd.Series, threshold: float = 2.0):
    spike = pd.Series(0.0, index=zscore.index)
    spike[zscore > threshold] = 1.0
    return spike

# Lines 92-115 (regime classification)
def _compute_tariff_regime(self, data):
    # 0 = Pre-trade war, 1 = Active trade war, 2 = Phase One, 3 = Trump 2.0
```

**Features**:
- USEPUINDXM
- EPUTRADE
- EMVTRADEPOLEMV (equity market vol - trade policy)

**Signal Contract**:
- `signal_1` = tariff risk score (weighted EPU z-scores)
- `signal_2` = EPU spike indicator

---

## SPECIALIST #10: BIOFUEL
**File**: `src/fusion/specialists/event_signals.py:216-419`  
**Model Type**: EMA-smoothed RIN/policy signals

```python
# Lines 314-325 (RIN momentum)
def _compute_rin_momentum(self, rin: pd.Series):
    fast_ema = rin.ewm(span=10, adjust=False).mean()
    slow_ema = rin.ewm(span=30, adjust=False).mean()
    momentum = (fast_ema - slow_ema) / slow_ema.replace(0, np.nan) * 100
    return momentum.clip(-50, 50)

# Line 381 (smoothing)
policy_smoothed = policy_pressure.ewm(span=21, adjust=False).mean()
```

**Features**:
- RIN D4/D6 prices
- LCFS credits
- Biodiesel margin proxy (ZL - HO spread)

**Signal Contract**:
- `signal_1` = policy pressure score (EMA-smoothed RIN z-score)
- `signal_2` = RIN momentum

---

## SPECIALIST #11: TRUMP_EFFECT
**File**: `src/fusion/specialists/event_signals.py:426-647`  
**Model Type**: Event study + EPU decomposition + proxy composites

```python
# Lines 511-547 (EPU decomposition)
def _compute_epu_decomposition(self, data):
    total_zscore = self.compute_zscore(total_epu, ...)
    trade_zscore = self.compute_zscore(trade_epu, ...)
    trade_share = trade_epu / total_epu  # Trade % of total EPU
    return total_zscore, trade_share, trade_zscore

# Lines 549-558 (regime detection)
def _is_trump_regime(self, idx):
    # Trump 1.0: 2017-01-20 to 2021-01-20
    # Trump 2.0: 2025-01-20 onwards
```

**Features**:
- EPU indices (daily/monthly)
- EPUTRADE
- VIX
- FXI (China ETF)

**Extras**: Regime-dependent weighting (more weight on trade tension during Trump eras)

**Signal Contract**:
- `signal_1` = event intensity (trade tension + china exposure)
- `signal_2` = trade uncertainty share

---

## Verification Summary

| # | Bucket | Model Class | File | Lines | Status |
|---|--------|-------------|------|-------|--------|
| 1 | crush | XGBRegressor | xgb_signals.py | 240-258 | ✅ |
| 2 | china | GradientBoostingRegressor | xgb_signals.py | 621-630 | ✅ |
| 3 | substitutes | RandomForestRegressor | xgb_signals.py | 433-442 | ✅ |
| 4 | fx | statsmodels ARDL | ardl_signals.py | 495-506 | ✅ |
| 5 | fed | Weighted z-score composite | ardl_signals.py | 975-1024 | ✅ |
| 6 | volatility | GJR-GARCH(1,1) | garch_signals.py | 96-103 | ✅ |
| 7 | energy | statsmodels VAR + IRF/FEVD | var_signals.py | 217-252 | ✅ |
| 8 | palm | Ridge + ECM cointegration | ecm_signals.py | 131-136, 311-312 | ✅ |
| 9 | tariff | Rules-based EPU thresholds | event_signals.py | 80-115 | ✅ |
| 10 | biofuel | EMA-smoothed RIN/LCFS | event_signals.py | 314-381 | ✅ |
| 11 | trump_effect | Event study + EPU decomp | event_signals.py | 511-558 | ✅ |

**ALL 11 SPECIALISTS VERIFIED ✅**

---

## Signal Contract (Universal)

All 11 specialists follow this contract:
- **signal_1** (required): Primary domain-specific signal
- **signal_2** (optional): Secondary signal or confidence indicator
- **confidence** (optional): Model confidence score (0-1)
- **Storage**: `training.specialist_signals_1d` table
- **Horizons**: NONE - specialists produce signals only, Core owns all horizon forecasting (5d/21d/63d/126d)

---

## Key Principle

Specialists are **signal generators**, NOT forecasters. They produce horizon-agnostic signals that feed into the Core model as input features. The Core model owns all horizon-specific forecasting logic.
