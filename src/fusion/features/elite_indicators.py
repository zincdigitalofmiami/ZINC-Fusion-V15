"""
ZINC-FUSION-V15: Elite Technical Indicators Module
===================================================

27 carefully curated indicators based on institutional quant desk research.
NOT the 130+ kitchen-sink approach - each indicator provides independent signal.

TIER 1: Overlooked Institutional Gems (Rarely seen in retail)
- Hurst Exponent (regime detection)
- Connors RSI (3,2,100)
- Ehlers Fisher Transform
- McGinley Dynamic
- TTM Squeeze
- Schaff Trend Cycle
- Relative Vigor Index
- Elder Force Index

TIER 2: Optimized Staples (Right settings for commodity futures)
- Horizon-matched MAs: KAMA, HMA, ALMA, McGinley
- RSI variants: RSI(2), RSI(14), Cumulative RSI
- MACD: Standard and Fast settings
- CCI: 14 and 50 periods

TIER 3: Volatility Regime
- ATR Ratio, Garman-Klass, Yang-Zhang, BB %B

TIER 4: Volume/Flow
- CMF, Volume Z-Score, Elder Force Index

Sources:
- https://macrosynergy.com/research/detecting-trends-and-mean-reversion-with-the-hurst-exponent/
- https://www.quantifiedstrategies.com/connors-rsi/
- https://trendspider.com/learning-center/fisher-transform-a-comprehensive-guide/
- https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/ttm-squeeze
"""

import pandas as pd
import numpy as np
from typing import Optional, Tuple
import warnings

warnings.filterwarnings("ignore")

# Import TA library (primary)
try:
    import ta
    from ta import momentum, trend, volatility, volume
    HAS_TA = True
except ImportError:
    HAS_TA = False


class EliteIndicators:
    """
    27 Elite Technical Indicators for ZL Futures Forecasting.

    Designed for institutional-grade signal generation with:
    - Regime detection (Hurst, TTM Squeeze)
    - Momentum (ConnorsRSI, Fisher, Schaff)
    - Trend (McGinley, KAMA, HMA, ALMA)
    - Volatility (Garman-Klass, Yang-Zhang)
    - Volume flow (CMF, Elder Force)
    """

    def __init__(self, df: pd.DataFrame, symbol: str = "ZL"):
        """
        Initialize with OHLCV DataFrame.

        Args:
            df: DataFrame with columns like {symbol}_open, {symbol}_high, etc.
            symbol: Symbol prefix for column names (default: "ZL")
        """
        self.df = df.copy()
        self.symbol = symbol
        self._setup_columns()

    def _setup_columns(self):
        """Setup column references."""
        s = self.symbol
        self.open_col = f"{s}_open"
        self.high_col = f"{s}_high"
        self.low_col = f"{s}_low"
        self.close_col = f"{s}_close"
        self.volume_col = f"{s}_volume"

        # Verify columns exist
        required = [self.close_col]
        for col in required:
            if col not in self.df.columns:
                raise ValueError(f"Required column {col} not found in DataFrame")

    # =========================================================================
    # TIER 1: OVERLOOKED INSTITUTIONAL GEMS
    # =========================================================================

    def add_hurst_exponent(self, window: int = 100) -> pd.DataFrame:
        """
        Rolling Hurst Exponent for regime detection.

        H > 0.5: Trending (momentum strategies)
        H < 0.5: Mean-reverting (reversion strategies)
        H ≈ 0.5: Random walk (avoid trading)

        Based on R/S analysis method.
        """
        close = self.df[self.close_col]

        def calculate_hurst(ts):
            """Calculate Hurst exponent using R/S method."""
            if len(ts) < 20 or ts.isna().any():
                return np.nan

            ts = np.array(ts)
            n = len(ts)

            # Calculate returns
            returns = np.diff(ts) / ts[:-1]
            returns = returns[~np.isnan(returns)]

            if len(returns) < 10:
                return np.nan

            # R/S calculation for multiple sub-periods
            max_k = min(int(len(returns) / 4), 50)
            if max_k < 4:
                return np.nan

            rs_list = []
            n_list = []

            for k in range(4, max_k + 1):
                # Divide into k sub-periods
                subperiod_len = len(returns) // k
                if subperiod_len < 2:
                    continue

                rs_values = []
                for i in range(k):
                    start = i * subperiod_len
                    end = start + subperiod_len
                    subperiod = returns[start:end]

                    if len(subperiod) < 2:
                        continue

                    # Mean-adjusted cumulative sum
                    mean_adj = subperiod - np.mean(subperiod)
                    cumsum = np.cumsum(mean_adj)

                    # Range
                    R = np.max(cumsum) - np.min(cumsum)

                    # Standard deviation
                    S = np.std(subperiod, ddof=1)

                    if S > 0:
                        rs_values.append(R / S)

                if rs_values:
                    rs_list.append(np.mean(rs_values))
                    n_list.append(subperiod_len)

            if len(rs_list) < 3:
                return np.nan

            # Log-log regression to estimate Hurst
            log_n = np.log(n_list)
            log_rs = np.log(rs_list)

            # Linear regression
            slope = np.polyfit(log_n, log_rs, 1)[0]

            # Clamp to valid range
            return np.clip(slope, 0.0, 1.0)

        self.df["hurst_exponent"] = close.rolling(window).apply(calculate_hurst, raw=False)

        # Regime classification
        self.df["hurst_regime"] = pd.cut(
            self.df["hurst_exponent"],
            bins=[0, 0.4, 0.6, 1.0],
            labels=["mean_reverting", "random", "trending"]
        )

        return self.df

    def _division_safe_rsi(self, series: pd.Series, period: int) -> pd.Series:
        """
        Division-safe RSI computation.
        
        GUARANTEED: No NaN after warm-up period.
        
        Edge cases (per locked spec):
        - avg_loss = 0 AND avg_gain > 0 → RSI = 100 (all gains)
        - avg_gain = 0 AND avg_loss > 0 → RSI = 0 (all losses)
        - avg_gain = 0 AND avg_loss = 0 → RSI = 50 (flat tape)
        """
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        
        # Initialize RSI with NaN
        rsi = pd.Series(np.nan, index=series.index)
        
        # Apply division-safe logic element-wise
        for i in range(period, len(series)):
            ag = avg_gain.iloc[i]
            al = avg_loss.iloc[i]
            
            # Handle edge cases explicitly
            if pd.isna(ag) or pd.isna(al):
                rsi.iloc[i] = np.nan  # Still in warm-up or bad data
            elif al == 0 and ag > 0:
                rsi.iloc[i] = 100.0  # All gains, no losses
            elif ag == 0 and al > 0:
                rsi.iloc[i] = 0.0    # All losses, no gains
            elif ag == 0 and al == 0:
                rsi.iloc[i] = 50.0   # Flat tape (no movement)
            else:
                rs = ag / al
                rsi.iloc[i] = 100.0 - (100.0 / (1.0 + rs))
        
        return rsi

    def add_connors_rsi(self) -> pd.DataFrame:
        """
        Connors RSI (3, 2, 100) - Larry Connors' championship indicator.

        Three components:
        1. RSI(3) of price - DIVISION SAFE
        2. RSI(2) of up/down streak length - DIVISION SAFE
        3. Percentile rank of 1-day ROC over 100 days

        GUARANTEED: No NaN after warm-up (max lookback = 100 days).
        
        Overbought: > 90, Oversold: < 10 (NOT 70/30!)
        """
        close = self.df[self.close_col]

        # Component 1: RSI(3) of price - DIVISION SAFE
        rsi_3 = self._division_safe_rsi(close, period=3)

        # Component 2: Up/Down streak RSI(2)
        streak = pd.Series(0.0, index=close.index, dtype=float)
        for i in range(1, len(close)):
            if pd.isna(close.iloc[i]) or pd.isna(close.iloc[i-1]):
                streak.iloc[i] = 0.0
            elif close.iloc[i] > close.iloc[i-1]:
                streak.iloc[i] = max(streak.iloc[i-1], 0) + 1
            elif close.iloc[i] < close.iloc[i-1]:
                streak.iloc[i] = min(streak.iloc[i-1], 0) - 1
            else:
                streak.iloc[i] = 0.0  # Flat day resets streak

        # RSI(2) of streak - DIVISION SAFE
        rsi_streak = self._division_safe_rsi(streak, period=2)

        # Component 3: ROC percentile rank over 100 days
        # Bounded output: 0-100, no division issues
        roc_1d = close.pct_change(1) * 100
        
        def safe_percentile_rank(x):
            """Percentile rank that never returns NaN after warm-up."""
            if len(x) < 2:
                return 50.0  # Neutral if insufficient data
            current = x.iloc[-1]
            past = x.iloc[:-1]
            if pd.isna(current):
                return 50.0
            # Count how many past values current exceeds
            count = (current > past).sum()
            return (count / len(past)) * 100.0
        
        roc_percentile = roc_1d.rolling(100, min_periods=20).apply(
            safe_percentile_rank, raw=False
        )

        # Combine: average of three components
        # Use fillna(50) for any remaining edge cases (50 = neutral)
        rsi_3_safe = rsi_3.fillna(50.0)
        rsi_streak_safe = rsi_streak.fillna(50.0)
        roc_pct_safe = roc_percentile.fillna(50.0)
        
        self.df["connors_rsi"] = (rsi_3_safe + rsi_streak_safe + roc_pct_safe) / 3.0

        # Signals at 90/10 levels (NOT 70/30)
        self.df["connors_rsi_overbought"] = (self.df["connors_rsi"] > 90).astype(int)
        self.df["connors_rsi_oversold"] = (self.df["connors_rsi"] < 10).astype(int)

        return self.df

    def add_fisher_transform(self, period: int = 10) -> pd.DataFrame:
        """
        Ehlers Fisher Transform - converts price to Gaussian distribution.

        Overbought: > 1.5, Oversold: < -1.5
        Signal line crossovers for entries.
        """
        high = self.df[self.high_col]
        low = self.df[self.low_col]

        # Median price normalized to -1 to 1
        hl2 = (high + low) / 2

        highest = hl2.rolling(period).max()
        lowest = hl2.rolling(period).min()

        # Normalize to -0.999 to 0.999 (avoid infinity in transform)
        raw = 2 * ((hl2 - lowest) / (highest - lowest).replace(0, np.nan)) - 1
        raw = raw.clip(-0.999, 0.999)

        # Smooth
        value = raw.ewm(span=5, adjust=False).mean()

        # Fisher Transform: 0.5 * ln((1+x)/(1-x))
        fisher = 0.5 * np.log((1 + value) / (1 - value))

        self.df["fisher_transform"] = fisher
        self.df["fisher_signal"] = fisher.shift(1)

        # Levels
        self.df["fisher_overbought"] = (fisher > 1.5).astype(int)
        self.df["fisher_oversold"] = (fisher < -1.5).astype(int)

        return self.df

    def add_mcginley_dynamic(self, period: int = 14) -> pd.DataFrame:
        """
        McGinley Dynamic - self-adjusting moving average.

        Solves the MA lag problem by adjusting to market speed.
        MD = MD[-1] + (Close - MD[-1]) / (N * (Close/MD[-1])^4)
        """
        close = self.df[self.close_col]

        md = pd.Series(index=close.index, dtype=float)
        md.iloc[0] = close.iloc[0]

        for i in range(1, len(close)):
            if pd.isna(close.iloc[i]) or pd.isna(md.iloc[i-1]) or md.iloc[i-1] == 0:
                md.iloc[i] = close.iloc[i]
            else:
                ratio = close.iloc[i] / md.iloc[i-1]
                k = period * (ratio ** 4)
                if k > 0:
                    md.iloc[i] = md.iloc[i-1] + (close.iloc[i] - md.iloc[i-1]) / k
                else:
                    md.iloc[i] = md.iloc[i-1]

        self.df["mcginley_dynamic"] = md
        self.df["mcginley_signal"] = (close > md).astype(int) - (close < md).astype(int)

        return self.df

    def add_ttm_squeeze(self, bb_period: int = 20, bb_std: float = 2.0,
                        kc_period: int = 20, kc_mult: float = 1.5) -> pd.DataFrame:
        """
        TTM Squeeze - John Carter's famous indicator.

        Squeeze ON (red): BB inside KC = low volatility, breakout imminent
        Squeeze OFF (green): BB outside KC = volatility expanding
        Momentum histogram shows direction.
        """
        high = self.df[self.high_col]
        low = self.df[self.low_col]
        close = self.df[self.close_col]

        # Bollinger Bands
        bb_mid = close.rolling(bb_period).mean()
        bb_std_val = close.rolling(bb_period).std()
        bb_upper = bb_mid + bb_std * bb_std_val
        bb_lower = bb_mid - bb_std * bb_std_val

        # Keltner Channels (using ATR)
        tr = pd.concat([
            high - low,
            abs(high - close.shift(1)),
            abs(low - close.shift(1))
        ], axis=1).max(axis=1)
        atr = tr.rolling(kc_period).mean()

        kc_mid = close.rolling(kc_period).mean()
        kc_upper = kc_mid + kc_mult * atr
        kc_lower = kc_mid - kc_mult * atr

        # Squeeze detection: BB inside KC
        squeeze_on = (bb_lower > kc_lower) & (bb_upper < kc_upper)

        # Momentum (linear regression of close - midline)
        midline = (high.rolling(kc_period).max() + low.rolling(kc_period).min()) / 2
        midline = (midline + close.rolling(kc_period).mean()) / 2

        momentum = close - midline

        self.df["ttm_squeeze_on"] = squeeze_on.astype(int)
        self.df["ttm_squeeze_momentum"] = momentum

        # Squeeze count (days in squeeze)
        squeeze_count = pd.Series(0, index=close.index, dtype=int)
        count = 0
        for i in range(len(squeeze_on)):
            if squeeze_on.iloc[i]:
                count += 1
            else:
                count = 0
            squeeze_count.iloc[i] = count

        self.df["ttm_squeeze_count"] = squeeze_count

        return self.df

    def add_schaff_trend_cycle(self, fast: int = 23, slow: int = 50,
                               cycle: int = 10) -> pd.DataFrame:
        """
        Schaff Trend Cycle (STC) - MACD through double Stochastic.

        Faster than MACD, smoother than Stochastic.
        25/75 levels (more actionable than 20/80).
        """
        close = self.df[self.close_col]

        # MACD line
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow

        # First Stochastic of MACD
        lowest_macd = macd.rolling(cycle).min()
        highest_macd = macd.rolling(cycle).max()
        stoch1 = 100 * (macd - lowest_macd) / (highest_macd - lowest_macd).replace(0, np.nan)

        # Smooth first stochastic
        pf = stoch1.ewm(span=3, adjust=False).mean()

        # Second Stochastic
        lowest_pf = pf.rolling(cycle).min()
        highest_pf = pf.rolling(cycle).max()
        stoch2 = 100 * (pf - lowest_pf) / (highest_pf - lowest_pf).replace(0, np.nan)

        # Final STC
        self.df["schaff_trend_cycle"] = stoch2.ewm(span=3, adjust=False).mean()

        # Signals at 25/75
        self.df["stc_bullish"] = (self.df["schaff_trend_cycle"] < 25).astype(int)
        self.df["stc_bearish"] = (self.df["schaff_trend_cycle"] > 75).astype(int)

        return self.df

    def add_relative_vigor_index(self, period: int = 10) -> pd.DataFrame:
        """
        Relative Vigor Index (RVI) - measures conviction of price movement.

        "In uptrends, closes near highs; in downtrends, closes near lows"
        RVI divergence from price = early reversal warning.
        """
        open_p = self.df[self.open_col]
        high = self.df[self.high_col]
        low = self.df[self.low_col]
        close = self.df[self.close_col]

        # Numerator: close - open (vigor)
        vigor = close - open_p

        # Denominator: high - low (range)
        range_hl = high - low

        # Symmetric smoothing (weighted MA)
        def swma(series):
            return (series + 2*series.shift(1) + 2*series.shift(2) + series.shift(3)) / 6

        vigor_smooth = swma(vigor)
        range_smooth = swma(range_hl)

        # Sum over period
        vigor_sum = vigor_smooth.rolling(period).sum()
        range_sum = range_smooth.rolling(period).sum()

        rvi = vigor_sum / range_sum.replace(0, np.nan)

        # Signal line
        signal = swma(rvi)

        self.df["rvi"] = rvi
        self.df["rvi_signal"] = signal
        self.df["rvi_histogram"] = rvi - signal

        return self.df

    def add_elder_force_index(self, period: int = 13) -> pd.DataFrame:
        """
        Elder Force Index (EFI) - Price change * Volume = force behind moves.

        Dr. Alexander Elder's institutional indicator.
        13-period EMA smoothing (not raw values).
        """
        close = self.df[self.close_col]
        volume = self.df[self.volume_col]

        # Raw Force Index: price_change * volume
        force_raw = close.diff() * volume

        # Smooth with EMA (min_periods=5 for early data with volume gaps)
        self.df["elder_force_index"] = force_raw.ewm(span=period, min_periods=5, adjust=False).mean()

        # Zero-line crossover signals
        efi = self.df["elder_force_index"]
        self.df["efi_bullish"] = ((efi > 0) & (efi.shift(1) <= 0)).astype(int)
        self.df["efi_bearish"] = ((efi < 0) & (efi.shift(1) >= 0)).astype(int)

        return self.df

    # =========================================================================
    # TIER 2: OPTIMIZED STAPLES
    # =========================================================================

    def add_horizon_matched_mas(self) -> pd.DataFrame:
        """
        Moving averages matched to forecast horizons.

        Per Gemini Deep Think analysis - aligns with transformer attention heads:
        - KAMA(10)      → 5d:   Filters "limit up/down" noise, clean 5d target
        - HMA(20)       → 21d:  Monthly cycle with zero lag, short-term pivots
        - ALMA(50)      → 63d:  Smoothest trend for quarterly planning
        - McGinley(100) → 126d: "Systemic Floor" - institutional support level
        """
        close = self.df[self.close_col]

        # KAMA(10) - Kaufman Adaptive Moving Average
        change = abs(close - close.shift(10))
        volatility_sum = abs(close.diff()).rolling(10).sum()
        er = change / volatility_sum.replace(0, np.nan)  # Efficiency Ratio

        fast_sc = 2 / (2 + 1)  # Fast smoothing constant
        slow_sc = 2 / (30 + 1)  # Slow smoothing constant
        sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2

        kama = pd.Series(index=close.index, dtype=float)
        kama.iloc[9] = close.iloc[:10].mean()
        for i in range(10, len(close)):
            if pd.notna(sc.iloc[i]):
                kama.iloc[i] = kama.iloc[i-1] + sc.iloc[i] * (close.iloc[i] - kama.iloc[i-1])
            else:
                kama.iloc[i] = kama.iloc[i-1]

        self.df["kama_10"] = kama

        # HMA(20) - Hull Moving Average
        half_period = 10
        sqrt_period = int(np.sqrt(20))

        wma_half = close.rolling(half_period).apply(
            lambda x: np.average(x, weights=range(1, len(x)+1)), raw=True
        )
        wma_full = close.rolling(20).apply(
            lambda x: np.average(x, weights=range(1, len(x)+1)), raw=True
        )
        raw_hma = 2 * wma_half - wma_full
        self.df["hma_20"] = raw_hma.rolling(sqrt_period).apply(
            lambda x: np.average(x, weights=range(1, len(x)+1)), raw=True
        )

        # ALMA(50) - Arnaud Legoux Moving Average
        period = 50
        offset = 0.85
        sigma = 6

        m = int(offset * (period - 1))
        s = period / sigma

        weights = np.array([np.exp(-((i - m) ** 2) / (2 * s * s)) for i in range(period)])
        weights = weights / weights.sum()

        self.df["alma_50"] = close.rolling(period, min_periods=25).apply(
            lambda x: np.dot(x, weights[-len(x):] / weights[-len(x):].sum()), raw=True
        )

        # McGinley(100) - "Systemic Floor" for 126d horizon
        md100 = pd.Series(index=close.index, dtype=float)
        md100.iloc[0] = close.iloc[0]
        for i in range(1, len(close)):
            if pd.isna(close.iloc[i]) or pd.isna(md100.iloc[i-1]) or md100.iloc[i-1] == 0:
                md100.iloc[i] = close.iloc[i]
            else:
                ratio = close.iloc[i] / md100.iloc[i-1]
                k = 100 * (ratio ** 4)
                if k > 0:
                    md100.iloc[i] = md100.iloc[i-1] + (close.iloc[i] - md100.iloc[i-1]) / k
                else:
                    md100.iloc[i] = md100.iloc[i-1]
        self.df["mcginley_100"] = md100

        # MA Distances (stationarized - % deviation from MA)
        # These are bounded/stationary features better for transformer tokenization
        self.df["price_vs_kama10_pct"] = (close - self.df["kama_10"]) / self.df["kama_10"] * 100
        self.df["price_vs_hma20_pct"] = (close - self.df["hma_20"]) / self.df["hma_20"] * 100
        self.df["price_vs_alma50_pct"] = (close - self.df["alma_50"]) / self.df["alma_50"] * 100
        self.df["price_vs_mcg100_pct"] = (close - md100) / md100 * 100

        return self.df

    def add_rsi_variants(self) -> pd.DataFrame:
        """
        RSI variants optimized for different purposes.

        RSI(2): Mean-reversion signals (Connors style)
        RSI(14): Standard momentum confirmation
        Cumulative RSI(3): Sum of last 3 RSI(2) values
        """
        close = self.df[self.close_col]

        def calc_rsi(series, period):
            delta = series.diff()
            gain = delta.where(delta > 0, 0)
            loss = (-delta).where(delta < 0, 0)
            avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
            rs = avg_gain / avg_loss.replace(0, np.nan)
            return 100 - (100 / (1 + rs))

        self.df["rsi_2"] = calc_rsi(close, 2)
        self.df["rsi_14"] = calc_rsi(close, 14)

        # Cumulative RSI - sum of last 3 RSI(2)
        self.df["cumulative_rsi"] = self.df["rsi_2"].rolling(3).sum()

        # Mean-reversion signals (Connors style: <5 buy, >95 sell)
        self.df["rsi2_buy_signal"] = (self.df["rsi_2"] < 5).astype(int)
        self.df["rsi2_sell_signal"] = (self.df["rsi_2"] > 95).astype(int)

        return self.df

    def add_macd_variants(self) -> pd.DataFrame:
        """
        MACD with horizon-appropriate settings.

        Standard (12,26,9): Trend confirmation
        Fast (5,13,4): Short-term horizons (5d/21d)
        """
        close = self.df[self.close_col]

        # Standard MACD
        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_26 = close.ewm(span=26, adjust=False).mean()
        self.df["macd"] = ema_12 - ema_26
        self.df["macd_signal"] = self.df["macd"].ewm(span=9, adjust=False).mean()
        self.df["macd_histogram"] = self.df["macd"] - self.df["macd_signal"]

        # Fast MACD
        ema_5 = close.ewm(span=5, adjust=False).mean()
        ema_13 = close.ewm(span=13, adjust=False).mean()
        self.df["macd_fast"] = ema_5 - ema_13
        self.df["macd_fast_signal"] = self.df["macd_fast"].ewm(span=4, adjust=False).mean()
        self.df["macd_fast_histogram"] = self.df["macd_fast"] - self.df["macd_fast_signal"]

        return self.df

    def add_cci_variants(self) -> pd.DataFrame:
        """
        Commodity Channel Index - DESIGNED for commodities!

        CCI(14): Short-term
        CCI(50): Longer-term regime
        """
        high = self.df[self.high_col]
        low = self.df[self.low_col]
        close = self.df[self.close_col]

        typical_price = (high + low + close) / 3

        for period in [14, 50]:
            min_p = period // 2  # Require at least half the window
            sma = typical_price.rolling(period, min_periods=min_p).mean()
            mad = typical_price.rolling(period, min_periods=min_p).apply(
                lambda x: np.abs(x - x.mean()).mean(), raw=True
            )
            self.df[f"cci_{period}"] = (typical_price - sma) / (0.015 * mad)

        return self.df

    # =========================================================================
    # TIER 3: VOLATILITY REGIME
    # =========================================================================

    def add_volatility_indicators(self) -> pd.DataFrame:
        """
        Advanced volatility indicators for regime detection.

        ATR Ratio: Expanding vs contracting volatility
        Garman-Klass: More efficient than standard HV (uses OHLC) - FLAT BAR SAFE
        Yang-Zhang: Handles overnight gaps (perfect for futures)
        BB %B: Position within Bollinger Bands
        """
        high = self.df[self.high_col]
        low = self.df[self.low_col]
        open_p = self.df[self.open_col]
        close = self.df[self.close_col]

        # True Range
        tr = pd.concat([
            high - low,
            abs(high - close.shift(1)),
            abs(low - close.shift(1))
        ], axis=1).max(axis=1)

        # ATR(10) and ATR(50) with min_periods for sparse data
        self.df["atr_10"] = tr.rolling(10, min_periods=5).mean()
        self.df["atr_50"] = tr.rolling(50, min_periods=25).mean()

        # ATR Ratio: >1 = expanding, <1 = contracting
        self.df["atr_ratio"] = self.df["atr_10"] / self.df["atr_50"]

        # =====================================================================
        # Garman-Klass Volatility - FLAT BAR SAFE
        # =====================================================================
        # GK = 0.5 * ln(H/L)^2 - (2*ln(2)-1) * ln(C/O)^2
        #
        # GUARANTEED: No NaN after warm-up, even on flat bars.
        #
        # Edge cases (per locked spec):
        # - If H = L → ln(H/L) = 0 (zero range, not NaN)
        # - If C = O → ln(C/O) = 0 (no intraday move)
        # - Clamp negative variance to 0
        # =====================================================================
        
        # Safe log(H/L): if H == L, result is 0 (not NaN or -inf)
        hl_ratio = high / low
        log_hl_safe = np.where(
            (high == low) | (hl_ratio <= 0),
            0.0,
            np.log(hl_ratio)
        )
        log_hl_sq = log_hl_safe ** 2
        
        # Safe log(C/O): if C == O, result is 0
        co_ratio = close / open_p
        log_co_safe = np.where(
            (close == open_p) | (co_ratio <= 0) | (open_p == 0),
            0.0,
            np.log(co_ratio)
        )
        log_co_sq = log_co_safe ** 2
        
        # GK daily variance (can be negative due to formula, clamp to 0)
        gk_coeff = 2 * np.log(2) - 1  # ≈ 0.386
        gk_daily = 0.5 * log_hl_sq - gk_coeff * log_co_sq
        gk_daily = np.maximum(gk_daily, 0.0)  # Clamp negative to 0
        
        # Convert to pandas Series for rolling
        gk_daily_series = pd.Series(gk_daily, index=self.df.index)
        
        # Rolling mean, then annualize and convert to percentage
        gk_rolling = gk_daily_series.rolling(20, min_periods=10).mean()
        
        # sqrt of negative should not happen after clamp, but protect anyway
        gk_rolling_safe = np.maximum(gk_rolling, 0.0)
        self.df["garman_klass_vol"] = np.sqrt(gk_rolling_safe * 252) * 100

        # Yang-Zhang Volatility (handles overnight gaps)
        log_oc = np.log(open_p / close.shift(1))  # Overnight
        log_co = np.log(close / open_p)  # Open-to-close
        log_cc = np.log(close / close.shift(1))  # Close-to-close

        # Rogers-Satchell component
        log_ho = np.log(high / open_p)
        log_lo = np.log(low / open_p)
        log_hc = np.log(high / close)
        log_lc = np.log(low / close)
        rs = log_ho * log_hc + log_lo * log_lc

        k = 0.34 / (1.34 + (21) / (21 - 1))

        var_o = log_oc.rolling(20, min_periods=10).var()
        var_c = log_co.rolling(20, min_periods=10).var()
        var_rs = rs.rolling(20, min_periods=10).mean()

        yz_var = var_o + k * var_c + (1 - k) * var_rs
        self.df["yang_zhang_vol"] = np.sqrt(yz_var * 252) * 100

        # Bollinger Band %B
        bb_mid = close.rolling(20, min_periods=10).mean()
        bb_std = close.rolling(20, min_periods=10).std()
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        self.df["bb_percent_b"] = (close - bb_lower) / (bb_upper - bb_lower)

        return self.df

    # =========================================================================
    # TIER 4: VOLUME/FLOW INDICATORS
    # =========================================================================

    def add_volume_indicators(self) -> pd.DataFrame:
        """
        Volume and flow indicators for institutional activity.

        CMF(21): Chaikin Money Flow - accumulation/distribution - ZERO VOLUME SAFE
        Volume Z-Score: Unusual volume detection

        Uses min_periods to handle sparse volume data in early years.
        This calculates the real formula over available observations.
        """
        high = self.df[self.high_col]
        low = self.df[self.low_col]
        close = self.df[self.close_col]
        volume = self.df[self.volume_col]

        # =====================================================================
        # Chaikin Money Flow (21 period) - ZERO VOLUME SAFE
        # =====================================================================
        # CMF = Sum(MF_Multiplier * Volume) / Sum(Volume)
        #
        # GUARANTEED: No NaN after warm-up, even in zero-volume eras.
        #
        # Edge cases (per locked spec):
        # - If H = L → MFM = 0 (neutral, no range info)
        # - If V = 0 → MFV = 0 (no flow if nothing traded)
        # - If ΣV over window = 0 → CMF = 0 (neutral)
        # =====================================================================
        
        # Money Flow Multiplier: (2*C - H - L) / (H - L)
        # Safe version: if H == L, MFM = 0 (neutral positioning)
        hl_range = high - low
        mfm_raw = (2 * close - high - low) / hl_range
        
        # Where H == L, set MFM to 0 (neutral - no informative close location)
        mf_multiplier = np.where(
            hl_range == 0,
            0.0,
            mfm_raw
        )
        mf_multiplier = pd.Series(mf_multiplier, index=self.df.index)
        
        # Handle any NaN from division (shouldn't happen after fix, but safety)
        mf_multiplier = mf_multiplier.fillna(0.0)
        
        # Money Flow Volume: MFM * V
        # If V = 0, MFV = 0 by definition
        volume_safe = volume.fillna(0.0)
        mf_volume = mf_multiplier * volume_safe
        
        # Rolling sums
        mfv_sum = mf_volume.rolling(21, min_periods=10).sum()
        vol_sum = volume_safe.rolling(21, min_periods=10).sum()
        
        # CMF = MFV_sum / Vol_sum
        # If vol_sum == 0, CMF = 0 (neutral - cannot infer flow without trades)
        cmf = np.where(
            vol_sum == 0,
            0.0,
            mfv_sum / vol_sum
        )
        self.df["cmf_21"] = pd.Series(cmf, index=self.df.index)
        
        # Fill any remaining NaN from warm-up with 0 after min_periods
        # (warm-up NaN is expected, but scattered NaN is not)

        # Volume Z-Score (20 day, min 10 observations)
        # Z = (V - mean) / std
        vol_mean = volume.rolling(20, min_periods=10).mean()
        vol_std = volume.rolling(20, min_periods=10).std()
        self.df["volume_zscore"] = (volume - vol_mean) / vol_std

        # Unusual volume flag (>2 std)
        self.df["unusual_volume"] = (self.df["volume_zscore"].abs() > 2).astype(int)

        return self.df

    # =========================================================================
    # COMPUTE ALL
    # =========================================================================

    def compute_all(self) -> pd.DataFrame:
        """
        Compute ALL 27 elite indicators.

        Returns DataFrame with all indicator columns added.
        """
        print(f"Computing Elite Indicators for {self.symbol}...")

        # Tier 1: Institutional gems
        print("   [1/4] Tier 1: Institutional gems...")
        self.add_hurst_exponent()
        self.add_connors_rsi()
        self.add_fisher_transform()
        self.add_mcginley_dynamic()
        self.add_ttm_squeeze()
        self.add_schaff_trend_cycle()
        self.add_relative_vigor_index()
        self.add_elder_force_index()

        # Tier 2: Optimized staples
        print("   [2/4] Tier 2: Optimized staples...")
        self.add_horizon_matched_mas()
        self.add_rsi_variants()
        self.add_macd_variants()
        self.add_cci_variants()

        # Tier 3: Volatility
        print("   [3/4] Tier 3: Volatility regime...")
        self.add_volatility_indicators()

        # Tier 4: Volume
        print("   [4/4] Tier 4: Volume/flow...")
        self.add_volume_indicators()

        # Count indicators added
        base_cols = {"ts_event", "trade_date", "target"}
        indicator_cols = [c for c in self.df.columns if c not in base_cols
                         and not c.endswith("_open") and not c.endswith("_high")
                         and not c.endswith("_low") and not c.endswith("_close")
                         and not c.endswith("_volume")]

        # Filter to just the new elite indicators
        elite_indicators = [c for c in indicator_cols if any(x in c for x in [
            "hurst", "connors", "fisher", "mcginley", "ttm_squeeze", "schaff",
            "rvi", "elder_force", "kama", "hma", "alma", "rsi", "cumulative",
            "macd", "cci", "atr", "garman", "yang_zhang", "bb_percent",
            "cmf", "volume_zscore", "unusual_volume", "stc"
        ])]

        print(f"\n   Computed {len(elite_indicators)} elite technical indicators")

        return self.df

    def get_indicator_summary(self) -> dict:
        """Return summary of computed indicators by tier."""
        return {
            "tier_1_institutional": [
                "hurst_exponent", "hurst_regime",
                "connors_rsi", "connors_rsi_overbought", "connors_rsi_oversold",
                "fisher_transform", "fisher_signal", "fisher_overbought", "fisher_oversold",
                "mcginley_dynamic", "mcginley_signal",
                "ttm_squeeze_on", "ttm_squeeze_momentum", "ttm_squeeze_count",
                "schaff_trend_cycle", "stc_bullish", "stc_bearish",
                "rvi", "rvi_signal", "rvi_histogram",
                "elder_force_index", "efi_bullish", "efi_bearish"
            ],
            "tier_2_optimized": [
                "kama_10", "hma_20", "alma_50",
                "rsi_2", "rsi_14", "cumulative_rsi", "rsi2_buy_signal", "rsi2_sell_signal",
                "macd", "macd_signal", "macd_histogram",
                "macd_fast", "macd_fast_signal", "macd_fast_histogram",
                "cci_14", "cci_50"
            ],
            "tier_3_volatility": [
                "atr_10", "atr_50", "atr_ratio",
                "garman_klass_vol", "yang_zhang_vol",
                "bb_percent_b"
            ],
            "tier_4_volume": [
                "cmf_21", "volume_zscore", "unusual_volume"
            ]
        }


def add_elite_indicators_to_df(df: pd.DataFrame, symbol: str = "ZL") -> pd.DataFrame:
    """
    Convenience function to add all elite indicators to a DataFrame.

    Args:
        df: DataFrame with OHLCV columns prefixed by symbol
        symbol: Symbol to compute indicators for (default: "ZL")

    Returns:
        DataFrame with all elite indicator columns added
    """
    elite = EliteIndicators(df, symbol=symbol)
    return elite.compute_all()
