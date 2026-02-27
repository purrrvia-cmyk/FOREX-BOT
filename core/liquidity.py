"""ICT Liquidity: Sweep, Inducement, Smart Money Trap"""

import numpy as np
from config.ict_params import ICT


def detect_liquidity_sweeps(df) -> list:
    if len(df) < 20:
        return []
    h = df["high"].astype(float).values
    l = df["low"].astype(float).values
    c = df["close"].astype(float).values
    tol = ICT["sweep_tolerance"]
    sweeps = []

    for i in range(5, len(df) - 1):
        for j in range(max(0, i - 15), i - 3):
            if abs(h[j] - h[i - 1]) / max(h[j], 0.0001) < tol:
                if h[i] > h[j] * 1.001 and c[i] < h[j]:
                    sweeps.append({"type": "BSL_SWEEP", "level": float(h[j]),
                                   "sweep_price": float(h[i]), "idx": i})
                    break
            if abs(l[j] - l[i - 1]) / max(l[j], 0.0001) < tol:
                if l[i] < l[j] * 0.999 and c[i] > l[j]:
                    sweeps.append({"type": "SSL_SWEEP", "level": float(l[j]),
                                   "sweep_price": float(l[i]), "idx": i})
                    break
    return sweeps[-5:]


def detect_inducement(df, swing_data: dict) -> list:
    if len(df) < 20 or not swing_data.get("swing_highs") or not swing_data.get("swing_lows"):
        return []
    h = df["high"].astype(float).values
    l = df["low"].astype(float).values
    sh = swing_data["swing_highs"][-1]
    sl = swing_data["swing_lows"][-1]
    s = min(sh["idx"], sl["idx"])
    e = max(sh["idx"], sl["idx"])
    inds = []

    for i in range(s + 1, min(e, len(df) - 2)):
        if i < 2:
            continue
        if h[i] > h[i - 1] and h[i] > h[i + 1]:
            for k in range(i + 1, min(i + 5, len(df))):
                if h[k] > h[i]:
                    inds.append({"type": "BULLISH_INDUCEMENT", "level": float(h[i]), "idx": k})
                    break
        if l[i] < l[i - 1] and l[i] < l[i + 1]:
            for k in range(i + 1, min(i + 5, len(df))):
                if l[k] < l[i]:
                    inds.append({"type": "BEARISH_INDUCEMENT", "level": float(l[i]), "idx": k})
                    break
    return inds[-3:]


def detect_smart_money_trap(df, ms: dict):
    if len(df) < 10:
        return None
    h = df["high"].astype(float).values
    l = df["low"].astype(float).values
    c = df["close"].astype(float).values
    o = df["open"].astype(float).values

    for i in range(len(df) - 3, len(df)):
        if i < 2:
            continue
        wu = h[i] - max(c[i], o[i])
        wd = min(c[i], o[i]) - l[i]
        body = abs(c[i] - o[i])
        cr = h[i] - l[i]
        if cr == 0:
            continue
        if wu > body * 2 and wu > cr * 0.6 and c[i] < o[i]:
            return {"type": "BULL_TRAP", "idx": i, "level": float(h[i])}
        if wd > body * 2 and wd > cr * 0.6 and c[i] > o[i]:
            return {"type": "BEAR_TRAP", "idx": i, "level": float(l[i])}
    return None
