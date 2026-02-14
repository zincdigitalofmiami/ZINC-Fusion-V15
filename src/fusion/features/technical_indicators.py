"""
ZINC Fusion V15: Comprehensive Technical Indicators Module
============================================================
Uses the best of: ta, TA-Lib, pandas-ta, finta, stockstats, talipp

130+ indicators across 4 categories:
- MOMENTUM (30+): RSI, MACD, Stochastic, Williams %R, ROC, TSI, UO, PPO, etc.
- TREND (25+): SMA, EMA, ADX, Aroon, CCI, Ichimoku, PSAR, TRIX, VWMA, etc.
- VOLATILITY (20+): Bollinger, ATR, Keltner, Donchian, Ulcer Index, etc.
- VOLUME (15+): OBV, CMF, MFI, VWAP, Force Index, AD, etc.

Plus specialist bucket-specific indicators for Big-8 analysis.
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, List
import warnings

warnings.filterwarnings("ignore")

# Import available TA libraries
try:
    import ta  # noqa: F401
    from ta import trend, momentum, volatility, volume  # noqa: F401

    HAS_TA = True
except ImportError:
    HAS_TA = False

try:
    import talib

    HAS_TALIB = True
except ImportError:
    HAS_TALIB = False

try:
    import pandas_ta as pta  # noqa: F401

    HAS_PANDAS_TA = True
except ImportError:
    HAS_PANDAS_TA = False

try:
    from finta import TA as finta_ta

    HAS_FINTA = True
except ImportError:
    HAS_FINTA = False

try:
    from stockstats import StockDataFrame  # noqa: F401

    HAS_STOCKSTATS = True
except ImportError:
    HAS_STOCKSTATS = False


class ZincFusionIndicators:
    """
    Comprehensive Technical Indicator Calculator for ZINC Fusion V15

    Computes 130+ indicators organized by category and specialist bucket.
    Uses the best available library for each indicator type.
    """

    def __init__(self, df: pd.DataFrame):
        """
        Initialize with OHLCV DataFrame.

        Required columns: open, high, low, close, volume
        Optional: trade_date or date index
        """
        self.df = df.copy()
        self._validate_columns()
        self._normalize_column_names()

    def _validate_columns(self):
        """Ensure required OHLCV columns exist."""
        # Try common variations
        col_map = {
            "open": ["open", "Open", "OPEN", "o"],
            "high": ["high", "High", "HIGH", "h"],
            "low": ["low", "Low", "LOW", "l"],
            "close": ["close", "Close", "CLOSE", "c"],
            "volume": ["volume", "Volume", "VOLUME", "v", "vol"],
        }

        for target, variations in col_map.items():
            for var in variations:
                if var in self.df.columns:
                    if var != target:
                        self.df = self.df.rename(columns={var: target})
                    break

    def _normalize_column_names(self):
        """Lowercase all column names."""
        self.df.columns = [c.lower() for c in self.df.columns]

    # =========================================================================
    # MOMENTUM INDICATORS (30+)
    # =========================================================================

    def add_momentum_indicators(
        self,
        rsi_periods: list[int] | None = None,
        macd_params: tuple[int, int, int] = (12, 26, 9),
        stoch_period: int = 14,
    ) -> pd.DataFrame:
        """
        Add comprehensive momentum indicators.

        Indicators:
        - RSI (multiple periods)
        - MACD (line, signal, histogram)
        - Stochastic (K, D, slow)
        - Williams %R
        - ROC (Rate of Change)
        - TSI (True Strength Index)
        - UO (Ultimate Oscillator)
        - PPO (Percentage Price Oscillator)
        - Awesome Oscillator
        - KAMA (Kaufman Adaptive MA)
        - CCI (Commodity Channel Index)
        - CMO (Chande Momentum Oscillator)
        - MFI (Money Flow Index)
        - DPO (Detrended Price Oscillator)
        """
        if rsi_periods is None:
            rsi_periods = [7, 14, 21]
        df = self.df

        # RSI - Multiple periods for different timeframes
        for period in rsi_periods:
            if HAS_TA:
                df[f"rsi_{period}"] = momentum.rsi(df["close"], window=period)
            elif HAS_TALIB:
                df[f"rsi_{period}"] = talib.RSI(df["close"], timeperiod=period)

        # RSI Divergence signals
        if "rsi_14" in df.columns:
            df["rsi_14_oversold"] = (df["rsi_14"] < 30).astype(int)
            df["rsi_14_overbought"] = (df["rsi_14"] > 70).astype(int)
            df["rsi_14_momentum"] = df["rsi_14"].diff(5)

        # MACD - Classic trend-following momentum
        fast, slow, signal = macd_params
        if HAS_TA:
            macd_ind = momentum.MACD(
                df["close"], window_slow=slow, window_fast=fast, window_sign=signal
            )
            df["macd"] = macd_ind.macd()
            df["macd_signal"] = macd_ind.macd_signal()
            df["macd_histogram"] = macd_ind.macd_diff()
        elif HAS_TALIB:
            df["macd"], df["macd_signal"], df["macd_histogram"] = talib.MACD(
                df["close"], fastperiod=fast, slowperiod=slow, signalperiod=signal
            )

        # MACD crossover signals
        if "macd" in df.columns and "macd_signal" in df.columns:
            df["macd_cross_up"] = (
                (df["macd"] > df["macd_signal"])
                & (df["macd"].shift(1) <= df["macd_signal"].shift(1))
            ).astype(int)
            df["macd_cross_down"] = (
                (df["macd"] < df["macd_signal"])
                & (df["macd"].shift(1) >= df["macd_signal"].shift(1))
            ).astype(int)

        # Stochastic Oscillator - Overbought/Oversold
        if HAS_TA:
            stoch = momentum.StochasticOscillator(
                df["high"], df["low"], df["close"], window=stoch_period
            )
            df["stoch_k"] = stoch.stoch()
            df["stoch_d"] = stoch.stoch_signal()
        elif HAS_TALIB:
            df["stoch_k"], df["stoch_d"] = talib.STOCH(
                df["high"], df["low"], df["close"]
            )

        # Slow Stochastic
        if "stoch_k" in df.columns:
            df["stoch_k_slow"] = df["stoch_k"].rolling(3).mean()
            df["stoch_d_slow"] = df["stoch_d"].rolling(3).mean()

        # Williams %R
        if HAS_TA:
            df["williams_r"] = momentum.williams_r(
                df["high"], df["low"], df["close"], lbp=14
            )
        elif HAS_TALIB:
            df["williams_r"] = talib.WILLR(
                df["high"], df["low"], df["close"], timeperiod=14
            )

        # ROC - Rate of Change (multiple periods)
        for period in [5, 10, 20, 60]:
            if HAS_TA:
                df[f"roc_{period}"] = momentum.roc(df["close"], window=period)
            else:
                df[f"roc_{period}"] = df["close"].pct_change(period) * 100

        # TSI - True Strength Index
        if HAS_TA:
            df["tsi"] = momentum.tsi(df["close"], window_slow=25, window_fast=13)

        # Ultimate Oscillator
        if HAS_TA:
            df["ultimate_oscillator"] = momentum.ultimate_oscillator(
                df["high"], df["low"], df["close"], window1=7, window2=14, window3=28
            )
        elif HAS_TALIB:
            df["ultimate_oscillator"] = talib.ULTOSC(df["high"], df["low"], df["close"])

        # PPO - Percentage Price Oscillator
        if HAS_TA:
            df["ppo"] = momentum.ppo(df["close"], window_slow=26, window_fast=12)
            df["ppo_signal"] = momentum.ppo_signal(df["close"])
            df["ppo_histogram"] = momentum.ppo_hist(df["close"])

        # Awesome Oscillator
        if HAS_TA:
            df["awesome_oscillator"] = momentum.awesome_oscillator(
                df["high"], df["low"]
            )

        # KAMA - Kaufman Adaptive Moving Average
        if HAS_TA:
            df["kama"] = momentum.kama(df["close"], window=10)
        elif HAS_TALIB:
            df["kama"] = talib.KAMA(df["close"], timeperiod=10)

        # CCI - Commodity Channel Index (multiple periods)
        for period in [14, 20, 50]:
            if HAS_TA:
                df[f"cci_{period}"] = trend.cci(
                    df["high"], df["low"], df["close"], window=period
                )
            elif HAS_TALIB:
                df[f"cci_{period}"] = talib.CCI(
                    df["high"], df["low"], df["close"], timeperiod=period
                )

        # CMO - Chande Momentum Oscillator
        if HAS_TALIB:
            df["cmo"] = talib.CMO(df["close"], timeperiod=14)
        elif HAS_FINTA:
            df["cmo"] = finta_ta.CMO(self.df)

        # MFI - Money Flow Index (volume-weighted RSI)
        if HAS_TA:
            df["mfi"] = volume.money_flow_index(
                df["high"], df["low"], df["close"], df["volume"], window=14
            )
        elif HAS_TALIB:
            df["mfi"] = talib.MFI(
                df["high"], df["low"], df["close"], df["volume"], timeperiod=14
            )

        # DPO - Detrended Price Oscillator
        if HAS_TA:
            df["dpo"] = trend.dpo(df["close"], window=20)

        self.df = df
        return df

    # =========================================================================
    # TREND INDICATORS (25+)
    # =========================================================================

    def add_trend_indicators(
        self,
        sma_periods: list[int] | None = None,
        ema_periods: list[int] | None = None,
    ) -> pd.DataFrame:
        """
        Add comprehensive trend indicators.

        Indicators:
        - SMA (multiple periods)
        - EMA (multiple periods)
        - WMA (Weighted MA)
        - DEMA (Double EMA)
        - TEMA (Triple EMA)
        - VWMA (Volume Weighted MA)
        - ADX (Average Directional Index)
        - Aroon (Up/Down/Oscillator)
        - Ichimoku (Kinko Hyo) (complete)
        - PSAR (Parabolic SAR)
        - TRIX
        - Vortex Indicator
        - Mass Index
        - SuperTrend
        """
        if sma_periods is None:
            sma_periods = [5, 10, 20, 50, 100, 200]
        if ema_periods is None:
            ema_periods = [9, 12, 26, 50, 200]
        df = self.df

        # SMA - Simple Moving Averages
        for period in sma_periods:
            df[f"sma_{period}"] = df["close"].rolling(window=period).mean()

        # SMA Crossover signals (Golden/Death Cross)
        if "sma_50" in df.columns and "sma_200" in df.columns:
            df["golden_cross"] = (
                (df["sma_50"] > df["sma_200"])
                & (df["sma_50"].shift(1) <= df["sma_200"].shift(1))
            ).astype(int)
            df["death_cross"] = (
                (df["sma_50"] < df["sma_200"])
                & (df["sma_50"].shift(1) >= df["sma_200"].shift(1))
            ).astype(int)

        # Price vs MA signals
        for period in [20, 50, 200]:
            if f"sma_{period}" in df.columns:
                df[f"price_vs_sma_{period}"] = (
                    df["close"] / df[f"sma_{period}"] - 1
                ) * 100
                df[f"above_sma_{period}"] = (df["close"] > df[f"sma_{period}"]).astype(
                    int
                )

        # EMA - Exponential Moving Averages
        for period in ema_periods:
            df[f"ema_{period}"] = df["close"].ewm(span=period, adjust=False).mean()

        # WMA - Weighted Moving Average
        for period in [10, 20]:
            weights = np.arange(1, period + 1)
            df[f"wma_{period}"] = (
                df["close"]
                .rolling(period)
                .apply(lambda x, w=weights: np.dot(x, w) / w.sum(), raw=True)
            )

        # DEMA - Double EMA
        if HAS_TALIB:
            df["dema_20"] = talib.DEMA(df["close"], timeperiod=20)
        else:
            ema1 = df["close"].ewm(span=20, adjust=False).mean()
            df["dema_20"] = 2 * ema1 - ema1.ewm(span=20, adjust=False).mean()

        # TEMA - Triple EMA
        if HAS_TALIB:
            df["tema_20"] = talib.TEMA(df["close"], timeperiod=20)
        else:
            ema1 = df["close"].ewm(span=20, adjust=False).mean()
            ema2 = ema1.ewm(span=20, adjust=False).mean()
            ema3 = ema2.ewm(span=20, adjust=False).mean()
            df["tema_20"] = 3 * ema1 - 3 * ema2 + ema3

        # VWMA - Volume Weighted Moving Average
        for period in [20, 50]:
            df[f"vwma_{period}"] = (df["close"] * df["volume"]).rolling(
                period
            ).sum() / df["volume"].rolling(period).sum()

        # ADX - Average Directional Index (trend strength)
        if HAS_TA:
            adx_ind = trend.ADXIndicator(df["high"], df["low"], df["close"], window=14)
            df["adx"] = adx_ind.adx()
            df["adx_pos"] = adx_ind.adx_pos()  # +DI
            df["adx_neg"] = adx_ind.adx_neg()  # -DI
        elif HAS_TALIB:
            df["adx"] = talib.ADX(df["high"], df["low"], df["close"], timeperiod=14)
            df["adx_pos"] = talib.PLUS_DI(
                df["high"], df["low"], df["close"], timeperiod=14
            )
            df["adx_neg"] = talib.MINUS_DI(
                df["high"], df["low"], df["close"], timeperiod=14
            )

        # ADX trend signals
        if "adx" in df.columns:
            df["strong_trend"] = (df["adx"] > 25).astype(int)
            df["very_strong_trend"] = (df["adx"] > 50).astype(int)
            df["trend_direction"] = np.where(df["adx_pos"] > df["adx_neg"], 1, -1)

        # Aroon Indicator
        if HAS_TA:
            aroon = trend.AroonIndicator(df["close"], window=25)
            df["aroon_up"] = aroon.aroon_up()
            df["aroon_down"] = aroon.aroon_down()
            df["aroon_indicator"] = aroon.aroon_indicator()
        elif HAS_TALIB:
            df["aroon_down"], df["aroon_up"] = talib.AROON(
                df["high"], df["low"], timeperiod=25
            )
            df["aroon_indicator"] = df["aroon_up"] - df["aroon_down"]

        # Ichimoku (Kinko Hyo) (complete)
        if HAS_TA:
            ichimoku = trend.IchimokuIndicator(
                df["high"], df["low"], window1=9, window2=26, window3=52
            )
            df["ichimoku_a"] = ichimoku.ichimoku_a()  # Senkou Span A
            df["ichimoku_b"] = ichimoku.ichimoku_b()  # Senkou Span B
            df["ichimoku_base"] = ichimoku.ichimoku_base_line()  # Kijun-sen
            df["ichimoku_conv"] = ichimoku.ichimoku_conversion_line()  # Tenkan-sen

        # Ichimoku signals
        if "ichimoku_a" in df.columns and "ichimoku_b" in df.columns:
            df["ichimoku_cloud_green"] = (df["ichimoku_a"] > df["ichimoku_b"]).astype(
                int
            )
            df["price_above_cloud"] = (
                df["close"] > df[["ichimoku_a", "ichimoku_b"]].max(axis=1)
            ).astype(int)

        # PSAR - Parabolic SAR
        if HAS_TA:
            psar = trend.PSARIndicator(df["high"], df["low"], df["close"])
            df["psar"] = psar.psar()
            df["psar_up"] = psar.psar_up()
            df["psar_down"] = psar.psar_down()
        elif HAS_TALIB:
            df["psar"] = talib.SAR(df["high"], df["low"])

        # PSAR signals
        if "psar" in df.columns:
            df["psar_bullish"] = (df["close"] > df["psar"]).astype(int)

        # TRIX
        if HAS_TA:
            df["trix"] = trend.trix(df["close"], window=15)
        elif HAS_TALIB:
            df["trix"] = talib.TRIX(df["close"], timeperiod=15)

        # Vortex Indicator
        if HAS_TA:
            vortex = trend.VortexIndicator(
                df["high"], df["low"], df["close"], window=14
            )
            df["vortex_pos"] = vortex.vortex_indicator_pos()
            df["vortex_neg"] = vortex.vortex_indicator_neg()
            df["vortex_diff"] = vortex.vortex_indicator_diff()

        # Mass Index
        if HAS_TA:
            df["mass_index"] = trend.mass_index(
                df["high"], df["low"], window_fast=9, window_slow=25
            )

        # KST - Know Sure Thing
        if HAS_TA:
            kst = trend.KSTIndicator(df["close"])
            df["kst"] = kst.kst()
            df["kst_signal"] = kst.kst_sig()
            df["kst_diff"] = kst.kst_diff()

        # STC - Schaff Trend Cycle
        if HAS_TA:
            df["stc"] = trend.stc(df["close"])

        self.df = df
        return df

    # =========================================================================
    # VOLATILITY INDICATORS (20+)
    # =========================================================================

    def add_volatility_indicators(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        atr_periods: list[int] | None = None,
    ) -> pd.DataFrame:
        """
        Add comprehensive volatility indicators.

        Indicators:
        - Bollinger Bands (complete)
        - ATR (multiple periods)
        - Keltner Channels
        - Donchian Channels
        - Ulcer Index
        - Historical Volatility (multiple periods)
        - Normalized ATR (NATR)
        - True Range
        - Chaikin Volatility
        """
        if atr_periods is None:
            atr_periods = [7, 14, 21]
        df = self.df

        # Bollinger Bands
        if HAS_TA:
            bb = volatility.BollingerBands(
                df["close"], window=bb_period, window_dev=bb_std
            )
            df["bb_upper"] = bb.bollinger_hband()
            df["bb_middle"] = bb.bollinger_mavg()
            df["bb_lower"] = bb.bollinger_lband()
            df["bb_width"] = bb.bollinger_wband()
            df["bb_pct"] = bb.bollinger_pband()  # %B
            df["bb_hband_indicator"] = bb.bollinger_hband_indicator()
            df["bb_lband_indicator"] = bb.bollinger_lband_indicator()
        elif HAS_TALIB:
            df["bb_upper"], df["bb_middle"], df["bb_lower"] = talib.BBANDS(
                df["close"], timeperiod=bb_period, nbdevup=bb_std, nbdevdn=bb_std
            )
            df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]
            df["bb_pct"] = (df["close"] - df["bb_lower"]) / (
                df["bb_upper"] - df["bb_lower"]
            )

        # BB Squeeze detection
        if "bb_width" in df.columns:
            df["bb_squeeze"] = (
                df["bb_width"] < df["bb_width"].rolling(125).quantile(0.25)
            ).astype(int)

        # ATR - Average True Range (multiple periods)
        for period in atr_periods:
            if HAS_TA:
                df[f"atr_{period}"] = volatility.average_true_range(
                    df["high"], df["low"], df["close"], window=period
                )
            elif HAS_TALIB:
                df[f"atr_{period}"] = talib.ATR(
                    df["high"], df["low"], df["close"], timeperiod=period
                )

        # NATR - Normalized ATR (percentage)
        if HAS_TALIB:
            df["natr"] = talib.NATR(df["high"], df["low"], df["close"], timeperiod=14)
        elif "atr_14" in df.columns:
            df["natr"] = (df["atr_14"] / df["close"]) * 100

        # True Range
        if HAS_TALIB:
            df["true_range"] = talib.TRANGE(df["high"], df["low"], df["close"])
        else:
            df["true_range"] = pd.concat(
                [
                    df["high"] - df["low"],
                    abs(df["high"] - df["close"].shift(1)),
                    abs(df["low"] - df["close"].shift(1)),
                ],
                axis=1,
            ).max(axis=1)

        # Keltner Channels
        if HAS_TA:
            kc = volatility.KeltnerChannel(
                df["high"], df["low"], df["close"], window=20
            )
            df["kc_upper"] = kc.keltner_channel_hband()
            df["kc_middle"] = kc.keltner_channel_mband()
            df["kc_lower"] = kc.keltner_channel_lband()
            df["kc_width"] = kc.keltner_channel_wband()
            df["kc_pct"] = kc.keltner_channel_pband()

        # Donchian Channels
        if HAS_TA:
            dc = volatility.DonchianChannel(
                df["high"], df["low"], df["close"], window=20
            )
            df["dc_upper"] = dc.donchian_channel_hband()
            df["dc_middle"] = dc.donchian_channel_mband()
            df["dc_lower"] = dc.donchian_channel_lband()
            df["dc_width"] = dc.donchian_channel_wband()
            df["dc_pct"] = dc.donchian_channel_pband()

        # Ulcer Index
        if HAS_TA:
            df["ulcer_index"] = volatility.ulcer_index(df["close"], window=14)

        # Historical Volatility (annualized)
        for period in [10, 20, 60, 252]:
            returns = np.log(df["close"] / df["close"].shift(1))
            df[f"volatility_{period}d"] = (
                returns.rolling(period).std() * np.sqrt(252) * 100
            )

        # Volatility ratio (short-term vs long-term)
        if "volatility_10d" in df.columns and "volatility_60d" in df.columns:
            df["volatility_ratio"] = df["volatility_10d"] / df["volatility_60d"]

        # Chaikin Volatility
        if HAS_FINTA:
            df["chaikin_volatility"] = finta_ta.CHAIKIN_VOL(self.df, period=10)
        else:
            hl = df["high"] - df["low"]
            df["chaikin_volatility"] = (
                (hl.ewm(span=10).mean() - hl.ewm(span=10).mean().shift(10))
                / hl.ewm(span=10).mean().shift(10)
            ) * 100

        # Volatility regime detection
        if "volatility_20d" in df.columns:
            vol_percentile = df["volatility_20d"].rolling(252).rank(pct=True)
            df["volatility_regime"] = pd.cut(
                vol_percentile,
                bins=[0, 0.25, 0.5, 0.75, 1.0],
                labels=["low", "normal", "elevated", "high"],
            )

        self.df = df
        return df

    # =========================================================================
    # VOLUME INDICATORS (15+)
    # =========================================================================

    def add_volume_indicators(self) -> pd.DataFrame:
        """
        Add comprehensive volume indicators.

        Indicators:
        - OBV (On Balance Volume)
        - CMF (Chaikin Money Flow)
        - MFI (Money Flow Index)
        - VWAP (Volume Weighted Average Price)
        - Force Index
        - ADL (Accumulation/Distribution Line)
        - EMV (Ease of Movement)
        - NVI (Negative Volume Index)
        - PVI (Positive Volume Index)
        - VPT (Volume Price Trend)
        - Volume Rate of Change
        - Volume Z-Score
        """
        df = self.df

        # OBV - On Balance Volume
        if HAS_TA:
            df["obv"] = volume.on_balance_volume(df["close"], df["volume"])
        elif HAS_TALIB:
            df["obv"] = talib.OBV(df["close"], df["volume"])

        # OBV momentum
        if "obv" in df.columns:
            df["obv_sma_20"] = df["obv"].rolling(20).mean()
            df["obv_divergence"] = df["obv"] - df["obv_sma_20"]

        # CMF - Chaikin Money Flow
        if HAS_TA:
            df["cmf"] = volume.chaikin_money_flow(
                df["high"], df["low"], df["close"], df["volume"], window=20
            )

        # MFI already added in momentum, but ensure it exists
        if "mfi" not in df.columns and HAS_TA:
            df["mfi"] = volume.money_flow_index(
                df["high"], df["low"], df["close"], df["volume"], window=14
            )

        # VWAP - Volume Weighted Average Price (intraday reset assumed daily)
        cumulative_tp_vol = (
            ((df["high"] + df["low"] + df["close"]) / 3) * df["volume"]
        ).cumsum()
        cumulative_vol = df["volume"].cumsum()
        df["vwap"] = cumulative_tp_vol / cumulative_vol

        # Price vs VWAP
        df["price_vs_vwap"] = ((df["close"] / df["vwap"]) - 1) * 100

        # Force Index
        if HAS_TA:
            df["force_index"] = volume.force_index(df["close"], df["volume"], window=13)

        # ADL - Accumulation/Distribution Line
        if HAS_TA:
            df["adl"] = volume.acc_dist_index(
                df["high"], df["low"], df["close"], df["volume"]
            )
        elif HAS_TALIB:
            df["adl"] = talib.AD(df["high"], df["low"], df["close"], df["volume"])

        # EMV - Ease of Movement
        if HAS_TA:
            df["emv"] = volume.ease_of_movement(
                df["high"], df["low"], df["volume"], window=14
            )
            df["emv_sma"] = volume.sma_ease_of_movement(
                df["high"], df["low"], df["volume"], window=14
            )

        # NVI - Negative Volume Index
        if HAS_TA:
            df["nvi"] = volume.negative_volume_index(df["close"], df["volume"])

        # VPT - Volume Price Trend
        if HAS_TA:
            df["vpt"] = volume.volume_price_trend(df["close"], df["volume"])

        # Volume statistics
        df["volume_sma_20"] = df["volume"].rolling(20).mean()
        df["volume_sma_50"] = df["volume"].rolling(50).mean()
        df["volume_ratio"] = df["volume"] / df["volume_sma_20"]

        # Volume Z-Score (standardized volume)
        df["volume_zscore"] = (df["volume"] - df["volume"].rolling(50).mean()) / df[
            "volume"
        ].rolling(50).std()

        # Volume ROC
        df["volume_roc"] = df["volume"].pct_change(10) * 100

        # High volume flag
        df["high_volume"] = (df["volume"] > df["volume_sma_20"] * 1.5).astype(int)
        df["very_high_volume"] = (df["volume"] > df["volume_sma_20"] * 2.0).astype(int)

        self.df = df
        return df

    # =========================================================================
    # PRICE ACTION & PATTERNS
    # =========================================================================

    def add_price_action_indicators(self) -> pd.DataFrame:
        """
        Add price action and pattern recognition indicators.

        Indicators:
        - Returns (multiple periods)
        - Log returns
        - Price momentum
        - Gap analysis
        - Range analysis
        - Candlestick patterns (via TA-Lib if available)
        """
        df = self.df

        # Returns - Multiple periods
        for period in [1, 2, 3, 5, 10, 20, 60, 120, 252]:
            df[f"return_{period}d"] = df["close"].pct_change(period) * 100

        # Log returns
        for period in [1, 5, 20]:
            df[f"log_return_{period}d"] = (
                np.log(df["close"] / df["close"].shift(period)) * 100
            )

        # Lagged closes
        for lag in [1, 2, 3, 5, 10, 20]:
            df[f"close_lag_{lag}d"] = df["close"].shift(lag)

        # Price momentum (close vs past close)
        for period in [5, 10, 20, 60]:
            df[f"momentum_{period}d"] = df["close"] - df["close"].shift(period)

        # Gaps
        df["gap"] = df["open"] - df["close"].shift(1)
        df["gap_pct"] = (df["gap"] / df["close"].shift(1)) * 100
        df["gap_up"] = (df["gap_pct"] > 0.5).astype(int)
        df["gap_down"] = (df["gap_pct"] < -0.5).astype(int)

        # Range analysis
        df["daily_range"] = df["high"] - df["low"]
        df["daily_range_pct"] = (df["daily_range"] / df["close"]) * 100
        df["avg_range_20d"] = df["daily_range"].rolling(20).mean()
        df["range_expansion"] = (df["daily_range"] > df["avg_range_20d"] * 1.5).astype(
            int
        )

        # Body analysis (candlestick)
        df["body"] = df["close"] - df["open"]
        df["body_pct"] = (df["body"] / df["open"]) * 100
        df["upper_shadow"] = df["high"] - df[["open", "close"]].max(axis=1)
        df["lower_shadow"] = df[["open", "close"]].min(axis=1) - df["low"]

        # Candlestick patterns (TA-Lib)
        if HAS_TALIB:
            # Bullish patterns
            df["doji"] = talib.CDLDOJI(df["open"], df["high"], df["low"], df["close"])
            df["hammer"] = talib.CDLHAMMER(
                df["open"], df["high"], df["low"], df["close"]
            )
            df["engulfing"] = talib.CDLENGULFING(
                df["open"], df["high"], df["low"], df["close"]
            )
            df["morning_star"] = talib.CDLMORNINGSTAR(
                df["open"], df["high"], df["low"], df["close"]
            )
            df["piercing"] = talib.CDLPIERCING(
                df["open"], df["high"], df["low"], df["close"]
            )

            # Bearish patterns
            df["shooting_star"] = talib.CDLSHOOTINGSTAR(
                df["open"], df["high"], df["low"], df["close"]
            )
            df["evening_star"] = talib.CDLEVENINGSTAR(
                df["open"], df["high"], df["low"], df["close"]
            )
            df["dark_cloud"] = talib.CDLDARKCLOUDCOVER(
                df["open"], df["high"], df["low"], df["close"]
            )
            df["hanging_man"] = talib.CDLHANGINGMAN(
                df["open"], df["high"], df["low"], df["close"]
            )

            # Continuation patterns
            df["three_white_soldiers"] = talib.CDL3WHITESOLDIERS(
                df["open"], df["high"], df["low"], df["close"]
            )
            df["three_black_crows"] = talib.CDL3BLACKCROWS(
                df["open"], df["high"], df["low"], df["close"]
            )

        # Consecutive up/down days
        df["up_day"] = (df["close"] > df["close"].shift(1)).astype(int)
        df["down_day"] = (df["close"] < df["close"].shift(1)).astype(int)

        # Streak counter
        df["streak"] = (
            df["up_day"]
            .groupby((df["up_day"] != df["up_day"].shift()).cumsum())
            .cumsum()
        )
        df["streak"] = np.where(
            df["down_day"] == 1,
            -df["down_day"]
            .groupby((df["down_day"] != df["down_day"].shift()).cumsum())
            .cumsum(),
            df["streak"],
        )

        self.df = df
        return df

    # =========================================================================
    # SPECIALIST BUCKET INDICATORS
    # =========================================================================

    def add_crush_bucket_indicators(
        self, zs_df: Optional[pd.DataFrame] = None, zm_df: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """
        Add CRUSH bucket specific indicators.

        For soybean oil (ZL) analysis with soybeans (ZS) and soybean meal (ZM).
        """
        df = self.df

        if zs_df is not None and zm_df is not None:
            # Merge ZS and ZM data
            df = df.merge(
                zs_df[["trade_date", "close"]].rename(columns={"close": "zs_close"}),
                on="trade_date",
                how="left",
            )
            df = df.merge(
                zm_df[["trade_date", "close"]].rename(columns={"close": "zm_close"}),
                on="trade_date",
                how="left",
            )

            # Board crush calculation per CME formula ($/bushel):
            # = (meal × 0.022) + (oil × 0.11) − soybeans/100
            # ZL in ¢/lb × 0.11 (11 lbs oil/bu), ZM in $/ton × 0.022, ZS in ¢/bu ÷ 100
            oil_value = df["close"] * 0.11  # ZL × 0.11
            meal_value = df["zm_close"] * 0.022  # ZM × 0.022
            df["board_crush"] = (oil_value + meal_value) - (df["zs_close"] / 100)

            # Oil share = oil_value / (oil_value + meal_value)
            df["oil_share"] = oil_value / (oil_value + meal_value)

            # ZL/ZS ratio
            df["zl_zs_ratio"] = df["close"] / df["zs_close"]

            # ZM/ZS ratio
            df["zm_zs_ratio"] = df["zm_close"] / df["zs_close"]

            # Crush margin momentum
            if "board_crush" in df.columns:
                df["crush_margin_momentum_5d"] = df["board_crush"].pct_change(5) * 100
                df["crush_margin_momentum_20d"] = df["board_crush"].pct_change(20) * 100

        self.df = df
        return df

    def add_energy_bucket_indicators(
        self,
        cl_df: Optional[pd.DataFrame] = None,
        ho_df: Optional[pd.DataFrame] = None,
        rb_df: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """
        Add ENERGY/BIOFUEL bucket specific indicators.

        For energy complex analysis (crude oil, heating oil, gasoline).
        """
        df = self.df

        if cl_df is not None:
            df = df.merge(
                cl_df[["trade_date", "close"]].rename(columns={"close": "cl_close"}),
                on="trade_date",
                how="left",
            )

        if ho_df is not None:
            df = df.merge(
                ho_df[["trade_date", "close"]].rename(columns={"close": "ho_close"}),
                on="trade_date",
                how="left",
            )

        if rb_df is not None:
            df = df.merge(
                rb_df[["trade_date", "close"]].rename(columns={"close": "rb_close"}),
                on="trade_date",
                how="left",
            )

        # BOHO spread (Biodiesel vs Heating Oil)
        if "ho_close" in df.columns:
            df["boho_spread"] = df["close"] - df["ho_close"]
            df["boho_ratio"] = df["close"] / df["ho_close"]

        # ZL/CL correlation proxy
        if "cl_close" in df.columns:
            df["zl_cl_ratio"] = df["close"] / df["cl_close"]
            df["zl_cl_spread"] = df["close"] - df["cl_close"]

        # 3-2-1 Crack spread proxy (simplified)
        if all(col in df.columns for col in ["cl_close", "ho_close", "rb_close"]):
            df["crack_spread_321"] = (
                2 * df["rb_close"] + df["ho_close"] - 3 * df["cl_close"]
            )

        self.df = df
        return df

    # =========================================================================
    # COMPUTE ALL INDICATORS
    # =========================================================================

    def compute_all(self) -> pd.DataFrame:
        """
        Compute ALL technical indicators in one call.

        Returns DataFrame with 130+ indicator columns.
        """
        print("🔧 Computing ZINC Fusion V15 Technical Indicators...")

        print("   → Momentum indicators (30+)...")
        self.add_momentum_indicators()

        print("   → Trend indicators (25+)...")
        self.add_trend_indicators()

        print("   → Volatility indicators (20+)...")
        self.add_volatility_indicators()

        print("   → Volume indicators (15+)...")
        self.add_volume_indicators()

        print("   → Price action indicators...")
        self.add_price_action_indicators()

        # Count non-OHLCV columns
        indicator_cols = [
            c
            for c in self.df.columns
            if c
            not in [
                "open",
                "high",
                "low",
                "close",
                "volume",
                "trade_date",
                "date",
                "symbol",
            ]
        ]
        print(f"\n✅ Computed {len(indicator_cols)} technical indicators")

        return self.df

    def get_indicator_summary(self) -> Dict[str, List[str]]:
        """Return dictionary of indicator names grouped by category."""
        cols = self.df.columns.tolist()

        return {
            "momentum": [
                c
                for c in cols
                if any(
                    x in c.lower()
                    for x in [
                        "rsi",
                        "macd",
                        "stoch",
                        "williams",
                        "roc",
                        "tsi",
                        "uo",
                        "ppo",
                        "cci",
                        "cmo",
                        "mfi",
                        "dpo",
                        "kama",
                        "awesome",
                    ]
                )
            ],
            "trend": [
                c
                for c in cols
                if any(
                    x in c.lower()
                    for x in [
                        "sma",
                        "ema",
                        "wma",
                        "dema",
                        "tema",
                        "vwma",
                        "adx",
                        "aroon",
                        "ichimoku",
                        "psar",
                        "trix",
                        "vortex",
                        "mass",
                        "kst",
                        "stc",
                        "golden",
                        "death",
                        "above_sma",
                    ]
                )
            ],
            "volatility": [
                c
                for c in cols
                if any(
                    x in c.lower()
                    for x in [
                        "bb_",
                        "atr",
                        "kc_",
                        "dc_",
                        "ulcer",
                        "volatility",
                        "natr",
                        "true_range",
                        "chaikin_vol",
                        "squeeze",
                    ]
                )
            ],
            "volume": [
                c
                for c in cols
                if any(
                    x in c.lower()
                    for x in [
                        "obv",
                        "cmf",
                        "vwap",
                        "force",
                        "adl",
                        "emv",
                        "nvi",
                        "vpt",
                        "volume_",
                    ]
                )
            ],
            "price_action": [
                c
                for c in cols
                if any(
                    x in c.lower()
                    for x in [
                        "return_",
                        "log_return",
                        "momentum_",
                        "gap",
                        "range",
                        "body",
                        "shadow",
                        "doji",
                        "hammer",
                        "engulf",
                        "star",
                        "streak",
                        "close_lag",
                    ]
                )
            ],
            "specialist": [
                c
                for c in cols
                if any(
                    x in c.lower()
                    for x in [
                        "crush",
                        "oil_share",
                        "zl_zs",
                        "zm_zs",
                        "boho",
                        "crack",
                        "zl_cl",
                    ]
                )
            ],
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def compute_indicators_for_symbol(df: pd.DataFrame, symbol: str = "ZL") -> pd.DataFrame:
    """
    Compute all technical indicators for a single symbol DataFrame.

    Args:
        df: DataFrame with OHLCV data
        symbol: Symbol name for logging

    Returns:
        DataFrame with all indicators added
    """
    print(f"\n{'=' * 60}")
    print(f"Computing indicators for {symbol}")
    print(f"{'=' * 60}")

    calculator = ZincFusionIndicators(df)
    result = calculator.compute_all()

    summary = calculator.get_indicator_summary()
    print(f"\nIndicator breakdown:")
    for category, indicators in summary.items():
        print(f"  {category.upper()}: {len(indicators)} indicators")

    return result


def compute_indicators_for_all_symbols(
    ohlcv_df: pd.DataFrame, symbol_column: str = "symbol"
) -> pd.DataFrame:
    """
    Compute indicators for multiple symbols in a single DataFrame.

    Args:
        ohlcv_df: DataFrame with OHLCV data and symbol column
        symbol_column: Name of the symbol column

    Returns:
        DataFrame with all indicators for all symbols
    """
    results = []

    for symbol in ohlcv_df[symbol_column].unique():
        symbol_data = ohlcv_df[ohlcv_df[symbol_column] == symbol].copy()

        if len(symbol_data) < 252:  # Need at least 1 year for some indicators
            print(f"⚠️ Skipping {symbol}: insufficient data ({len(symbol_data)} rows)")
            continue

        symbol_data = compute_indicators_for_symbol(symbol_data, symbol)
        symbol_data[symbol_column] = symbol
        results.append(symbol_data)

    return pd.concat(results, ignore_index=True)


# =============================================================================
# MAIN - Test the module
# =============================================================================

if __name__ == "__main__":
    print("🚀 ZINC Fusion V15 Technical Indicators Module")
    print("=" * 60)

    # Test with existing data from Prisma Postgres
    import os
    import sys

    import psycopg2
    from dotenv import load_dotenv

    load_dotenv()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not set")
        sys.exit(1)

    try:
        conn = psycopg2.connect(database_url)
        df = pd.read_sql(
            """
            SELECT event_date as trade_date, symbol, open, high, low, close, volume
            FROM mkt.futures_1d
            WHERE symbol = 'ZL'
            ORDER BY event_date
        """,
            conn,
        )
        conn.close()
        print(f"✅ Loaded {len(df):,} rows from Prisma Cloud (ZL)")

        # Use df directly (already filtered to ZL)
        zl_df = df.copy()

        # Rename columns if needed
        if "trade_date" in zl_df.columns:
            zl_df = zl_df.sort_values("trade_date")

        # Compute all indicators
        result = compute_indicators_for_symbol(zl_df, "ZL")

        print(
            f"\n📊 Final DataFrame: {result.shape[0]:,} rows × {result.shape[1]} columns"
        )
        print(f"\n🎯 Sample indicator values (last row):")
        key_indicators = ["rsi_14", "macd", "adx", "bb_pct", "obv", "volatility_20d"]
        for ind in key_indicators:
            if ind in result.columns:
                print(f"   {ind}: {result[ind].iloc[-1]:.4f}")

    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nUsage: Import and use ZincFusionIndicators class")
        print(
            "  from technical_indicators import ZincFusionIndicators, compute_indicators_for_symbol"
        )
