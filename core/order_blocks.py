"""ICT Order Blocks, Breaker Blocks, FVG, Displacement"""

import numpy as np
from config.ict_params import ICT


def detect_order_blocks(df, cur_price=None) -> list:
    if len(df) < 10:
        return []
    o = df["open"].astype(float).values
    c = df["close"].astype(float).values
    h = df["high"].astype(float).values
    l = df["low"].astype(float).values
    blocks = []
    ms = ICT["ob_min_strength"]

    for i in range(2, len(df) - 2):
        cr = h[i] - l[i]
        if cr == 0:
            continue
        ar = np.mean([h[j] - l[j] for j in range(max(0, i - 10), i)])
        if ar == 0:
            continue
        nm = abs(c[min(i + 2, len(df) - 1)] - c[i])
        if nm <= ar * ms:
            continue

        if c[i] < o[i] and c[min(i + 2, len(df) - 1)] > c[i]:
            mit = False
            if cur_price is not None:
                for k in range(i + 3, len(df)):
                    if l[k] <= c[i]:
                        mit = True; break
            blocks.append({"type": "BULLISH_OB", "high": float(o[i]), "low": float(c[i]),
                           "idx": i, "strength": round(nm / ar, 1), "mitigated": mit})
        elif c[i] > o[i] and c[min(i + 2, len(df) - 1)] < c[i]:
            mit = False
            if cur_price is not None:
                for k in range(i + 3, len(df)):
                    if h[k] >= c[i]:
                        mit = True; break
            blocks.append({"type": "BEARISH_OB", "high": float(c[i]), "low": float(o[i]),
                           "idx": i, "strength": round(nm / ar, 1), "mitigated": mit})

    blocks.sort(key=lambda x: x["strength"], reverse=True)
    return blocks[:8]


def detect_breaker_blocks(df) -> list:
    if len(df) < 15:
        return []
    cur = float(df["close"].iloc[-1])
    obs = detect_order_blocks(df, cur)
    breakers = []
    for ob in obs:
        if not ob["mitigated"]:
            continue
        mid = (ob["high"] + ob["low"]) / 2
        if ob["type"] == "BULLISH_OB" and cur < mid:
            breakers.append({"type": "BEARISH_BREAKER", "high": ob["high"], "low": ob["low"]})
        elif ob["type"] == "BEARISH_OB" and cur > mid:
            breakers.append({"type": "BULLISH_BREAKER", "high": ob["high"], "low": ob["low"]})
    return breakers[:3]


def detect_fvg(df) -> list:
    if len(df) < 5:
        return []
    h = df["high"].astype(float).values
    l = df["low"].astype(float).values
    gaps = []

    for i in range(2, len(df)):
        # Bullish FVG
        if l[i] > h[i - 2]:
            ce = (l[i] + h[i - 2]) / 2
            filled = ce_tested = False
            for k in range(i + 1, len(df)):
                if l[k] <= h[i - 2]:
                    filled = True; break
                if l[k] <= ce:
                    ce_tested = True
            gaps.append({"type": "BULLISH_FVG", "top": float(l[i]), "bottom": float(h[i - 2]),
                         "ce": float(ce), "idx": i, "filled": filled, "ce_tested": ce_tested})
        # Bearish FVG
        if h[i] < l[i - 2]:
            ce = (l[i - 2] + h[i]) / 2
            filled = ce_tested = False
            for k in range(i + 1, len(df)):
                if h[k] >= l[i - 2]:
                    filled = True; break
                if h[k] >= ce:
                    ce_tested = True
            gaps.append({"type": "BEARISH_FVG", "top": float(l[i - 2]), "bottom": float(h[i]),
                         "ce": float(ce), "idx": i, "filled": filled, "ce_tested": ce_tested})
    return gaps[-12:]


def detect_displacement(df) -> list:
    if len(df) < 20:
        return []
    o = df["open"].astype(float).values
    c = df["close"].astype(float).values
    h = df["high"].astype(float).values
    l = df["low"].astype(float).values
    avg_b = np.mean([abs(c[i] - o[i]) for i in range(max(0, len(df) - 20), len(df))])
    if avg_b == 0:
        return []
    mult = ICT["disp_body_mult"]
    ratio = ICT["disp_body_ratio"]
    disps = []
    for i in range(len(df) - 15, len(df)):
        if i < 0:
            continue
        body = abs(c[i] - o[i])
        cr = h[i] - l[i]
        if cr == 0:
            continue
        if body > avg_b * mult and body / cr > ratio:
            d = "BULLISH" if c[i] > o[i] else "BEARISH"
            disps.append({"type": f"{d}_DISPLACEMENT", "idx": i,
                          "body_mult": round(body / avg_b, 1)})
    return disps[-5:]
