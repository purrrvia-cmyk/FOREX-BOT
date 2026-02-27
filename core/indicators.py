"""Teknik göstergeler: RSI, EMA, ATR"""

import numpy as np
import pandas as pd


def calc_atr(df: pd.DataFrame, period: int = 14) -> float:
    if len(df) < period + 1:
        return 0.0
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    c = df["close"].astype(float)
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    return float(tr.ewm(alpha=1 / period, min_periods=period).mean().iloc[-1])


def calc_rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    ag = gain.ewm(alpha=1 / period, min_periods=period).mean()
    al = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = ag / al.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    v = rsi.iloc[-1]
    return float(v) if not np.isnan(v) else 50.0


def calc_indicators(df: pd.DataFrame) -> dict:
    close = df["close"].astype(float)
    atr = calc_atr(df)
    rsi = calc_rsi(close)
    ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
    ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
    ema200 = None
    if len(close) >= 200:
        ema200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])
    return {
        "rsi": rsi, "atr": atr,
        "ema20": ema20, "ema50": ema50, "ema200": ema200,
        "atr_pct": round(atr / float(close.iloc[-1]) * 100, 3) if atr > 0 else 0,
    }
