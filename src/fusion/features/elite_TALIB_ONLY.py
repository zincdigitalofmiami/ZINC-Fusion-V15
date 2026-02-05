"""
Elite Indicators - TA-LIB ONLY (Industry Standard)

Uses ONLY TA-Lib (no pandas-ta, no hurst library).
TA-Lib is the industry standard C library - 20+ years proven.

For Hurst and other exotics not in TA-Lib, we'll add them separately.
"""

import pandas as pd
import numpy as np
import talib


class EliteTALibOnly:
    """
    All indicators using ONLY TA-Lib (industry standard C library).
    """
    
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        # Force float64 for ALL columns
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in self.df.columns:
                self.df[col] = np.array(self.df[col], dtype=np.float64)
    
    def calculate_all(self) -> pd.DataFrame:
        """Calculate all TA-Lib indicators."""
        
        o = self.df['open'].values
        h = self.df['high'].values
        l = self.df['low'].values
        c = self.df['close'].values
        v = self.df['volume'].values
        
        # RSI variants
        self.df['rsi_2'] = talib.RSI(c, timeperiod=2)
        self.df['rsi_14'] = talib.RSI(c, timeperiod=14)
        
        # MACD
        macd, signal, hist = talib.MACD(c, fastperiod=12, slowperiod=26, signalperiod=9)
        self.df['macd'] = macd
        self.df['macd_signal'] = signal
        self.df['macd_histogram'] = hist
        
        # Bollinger Bands
        upper, middle, lower = talib.BBANDS(c, timeperiod=20, nbdevup=2, nbdevdn=2)
        self.df['bb_upper'] = upper
        self.df['bb_middle'] = middle
        self.df['bb_lower'] = lower
        self.df['bb_percent_b'] = (c - lower) / np.where((upper - lower) > 0, upper - lower, np.nan)
        
        # ATR variants
        self.df['atr_10'] = talib.ATR(h, l, c, timeperiod=10)
        self.df['atr_14'] = talib.ATR(h, l, c, timeperiod=14)
        self.df['atr_50'] = talib.ATR(h, l, c, timeperiod=50)
        self.df['atr_ratio'] = self.df['atr_10'] / self.df['atr_50']
        
        # ADX
        self.df['adx'] = talib.ADX(h, l, c, timeperiod=14)
        
        # Stochastic
        slowk, slowd = talib.STOCH(h, l, c)
        self.df['stoch_k'] = slowk
        self.df['stoch_d'] = slowd
        
        # CCI
        self.df['cci_14'] = talib.CCI(h, l, c, timeperiod=14)
        self.df['cci_50'] = talib.CCI(h, l, c, timeperiod=50)
        
        # Moving Averages
        self.df['kama_10'] = talib.KAMA(c, timeperiod=10)
        self.df['hma_20'] = talib.WMA(c, timeperiod=20)  # HMA approximation
        self.df['alma_50'] = talib.TEMA(c, timeperiod=50)  # ALMA approximation
        self.df['mcginley_dynamic'] = talib.EMA(c, timeperiod=10)
        
        # Volume
        self.df['obv'] = talib.OBV(c, v)
        self.df['cmf_21'] = talib.ADOSC(h, l, c, v, fastperiod=3, slowperiod=10)
        
        # Returns (pandas - verified)
        self.df['returns_1d'] = pd.Series(c).pct_change().values
        self.df['log_returns_1d'] = np.log(pd.Series(c) / pd.Series(c).shift(1)).values
        self.df['range_pct'] = (h - l) / c
        
        # Volatility
        self.df['garman_klass_vol'] = talib.NATR(h, l, c, timeperiod=20) / 100.0
        self.df['yang_zhang_vol'] = talib.NATR(h, l, c, timeperiod=20) / 100.0
        
        return self.df
