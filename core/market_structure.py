"""ICT Market Structure: BOS, CHoCH, Swing H/L"""

import numpy as np
from config.ict_params import ICT


def detect_market_structure(df) -> dict:
    if len(df) < 20:
        return {"trend": "NEUTRAL", "bos": [], "choch": None,
                "swing_highs": [], "swing_lows": []}

    highs = df["high"].astype(float).values
    lows = df["low"].astype(float).values
    close = df["close"].astype(float).values
    lb = ICT["swing_lookback"]

    swing_highs, swing_lows = [], []
    for i in range(lb, len(df) - lb):
        if highs[i] == max(highs[i - lb:i + lb + 1]):
            swing_highs.append({"idx": i, "price": float(highs[i])})
        if lows[i] == min(lows[i - lb:i + lb + 1]):
            swing_lows.append({"idx": i, "price": float(lows[i])})

    trend = "NEUTRAL"
    bos_list = []
    choch = None

    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        hh = swing_highs[-1]["price"] > swing_highs[-2]["price"]
        hl = swing_lows[-1]["price"] > swing_lows[-2]["price"]
        lh = swing_highs[-1]["price"] < swing_highs[-2]["price"]
        ll = swing_lows[-1]["price"] < swing_lows[-2]["price"]

        if hh and hl:
            trend = "BULLISH"
        elif lh and ll:
            trend = "BEARISH"

        cur = close[-1]
        if swing_highs and cur > swing_highs[-1]["price"]:
            bos_list.append({"type": "BULLISH_BOS", "level": swing_highs[-1]["price"]})
        if swing_lows and cur < swing_lows[-1]["price"]:
            bos_list.append({"type": "BEARISH_BOS", "level": swing_lows[-1]["price"]})

        if len(swing_highs) >= 3 and len(swing_lows) >= 3:
            if (swing_highs[-3]["price"] < swing_highs[-2]["price"] and
                    swing_highs[-1]["price"] < swing_highs[-2]["price"]):
                choch = {"type": "BEARISH_CHOCH", "level": swing_lows[-2]["price"],
                         "desc": "CHoCH — yükselişten düşüşe geçiş"}
            if (swing_lows[-3]["price"] > swing_lows[-2]["price"] and
                    swing_lows[-1]["price"] > swing_lows[-2]["price"]):
                choch = {"type": "BULLISH_CHOCH", "level": swing_highs[-2]["price"],
                         "desc": "CHoCH — düşüşten yükselişe geçiş"}

    return {
        "trend": trend, "bos": bos_list, "choch": choch,
        "swing_highs": swing_highs[-4:],
        "swing_lows": swing_lows[-4:],
    }
