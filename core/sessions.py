"""ICT Sessions: Kill Zone, Silver Bullet, AMD, Judas, Asian Range, Daily Bias, OTE, P/D"""

import pandas as pd
import numpy as np
from datetime import datetime
from config.kill_zones import KILL_ZONES, SILVER_BULLETS
from config.ict_params import ICT


# ── Kill Zone ──────────────────────────────────
def detect_kill_zone() -> dict:
    now = datetime.utcnow()
    h = now.hour
    active = None
    zones = []
    for name, kz in KILL_ZONES.items():
        is_active = kz["start"] <= h < kz["end"]
        remaining = (kz["end"] - h - 1) * 60 + (60 - now.minute) if is_active else 0
        if is_active:
            active = name
        zones.append({"name": name, "label": kz["label"], "active": is_active,
                       "remaining_min": remaining})

    next_kz = None
    for name, kz in KILL_ZONES.items():
        if h < kz["start"]:
            mins = (kz["start"] - h) * 60 - now.minute
            next_kz = f"{kz['label']} {mins} dk sonra"
            break

    return {
        "active_zone": active,
        "is_kill_zone": active is not None,
        "zones": zones,
        "next_kz": next_kz or "Asia KZ yarın",
    }


# ── Silver Bullet ──────────────────────────────
def detect_silver_bullet() -> dict:
    now = datetime.utcnow()
    h = now.hour
    active = None
    windows = []
    for name, sb in SILVER_BULLETS.items():
        is_a = sb["start"] <= h < sb["end"]
        rem = (sb["end"] - h - 1) * 60 + (60 - now.minute) if is_a else 0
        if is_a:
            active = {"name": name, "label": sb["label"], "remaining": rem}
        windows.append({"name": name, "label": sb["label"], "active": is_a})
    return {"is_active": active is not None, "active": active, "windows": windows}


# ── AMD (Power of 3) ──────────────────────────
def detect_amd(df):
    if len(df) < 20:
        return None
    c = df["close"].astype(float).values
    h = df["high"].astype(float).values
    l = df["low"].astype(float).values
    lb = min(20, len(df) - 1)
    ae = int(lb * 0.4)
    ar = h[-lb:-lb + ae].max() - l[-lb:-lb + ae].min()
    fr = h[-lb:].max() - l[-lb:].min()
    if fr == 0:
        return None
    if ar / fr >= 0.4:
        return None
    me = int(lb * 0.7)
    if me <= ae:
        return None
    dc = c[-1]
    do = c[-lb + me] if me < lb else c[-1]
    direction = "LONG" if dc > do else "SHORT"
    if direction == "LONG" and l[-lb + ae:-lb + me].min() < l[-lb:-lb + ae].min():
        return {"pattern": "AMD_BULLISH", "direction": "LONG"}
    elif direction == "SHORT" and h[-lb + ae:-lb + me].max() > h[-lb:-lb + ae].max():
        return {"pattern": "AMD_BEARISH", "direction": "SHORT"}
    return None


# ── Judas Swing ────────────────────────────────
def detect_judas(df):
    if len(df) < 10:
        return None
    kz = detect_kill_zone()
    if not kz["is_kill_zone"]:
        return None
    o = df["open"].astype(float).values
    c = df["close"].astype(float).values
    t = min(8, len(df) - 1)
    s = max(2, t // 3)
    first = c[-t] - o[-t]
    last = c[-1] - c[-(t - s)]
    if first > 0 and last < 0 and abs(last) > abs(first) * 0.8:
        return {"type": "BEARISH_JUDAS", "kz": kz["active_zone"]}
    elif first < 0 and last > 0 and abs(last) > abs(first) * 0.8:
        return {"type": "BULLISH_JUDAS", "kz": kz["active_zone"]}
    return None


# ── Asian Range Breakout ───────────────────────
def detect_asian_breakout(df):
    if len(df) < 20:
        return None
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    # Son 20 barın ilk 8'i ≈ Asian range
    ah = float(h.iloc[-20:-12].max())
    al = float(l.iloc[-20:-12].min())
    if ah <= al:
        return None
    cur = float(df["close"].iloc[-1])
    if cur > ah:
        return {"type": "BULLISH_BREAKOUT", "asian_high": ah, "asian_low": al}
    elif cur < al:
        return {"type": "BEARISH_BREAKOUT", "asian_high": ah, "asian_low": al}
    return {"type": "INSIDE_RANGE", "asian_high": ah, "asian_low": al}


# ── Daily Bias ─────────────────────────────────
def calc_daily_bias(feed, key: str) -> dict:
    from core.market_structure import detect_market_structure
    df = feed.candles(key, "1d")
    if df.empty or len(df) < 20:
        return {"bias": "NEUTRAL", "desc": "Yetersiz günlük veri"}
    ms = detect_market_structure(df)
    pd_zone = calc_premium_discount(df)
    bias, desc = "NEUTRAL", "Günlük bias belirsiz"
    if ms["trend"] == "BULLISH":
        bias, desc = "BULLISH", "Günlük trend yükseliş — LONG öncelikli"
        if pd_zone["zone"] == "PREMIUM" and pd_zone["zone_pct"] > 70:
            desc += " (DİKKAT: Premium bölge)"
    elif ms["trend"] == "BEARISH":
        bias, desc = "BEARISH", "Günlük trend düşüş — SHORT öncelikli"
        if pd_zone["zone"] == "DISCOUNT" and pd_zone["zone_pct"] > 70:
            desc += " (DİKKAT: Discount bölge)"
    if ms["choch"]:
        d = "yükselişe" if "BULL" in ms["choch"]["type"] else "düşüşe"
        desc += f" | CHoCH: {d} dönüş!"
    return {"bias": bias, "desc": desc, "trend": ms["trend"],
            "zone": pd_zone["zone"], "zone_pct": pd_zone["zone_pct"]}


# ── OTE (Fib 0.618-0.786) ─────────────────────
def calc_ote(df, ms: dict):
    if not ms["swing_highs"] or not ms["swing_lows"]:
        return None
    sh = ms["swing_highs"][-1]
    sl = ms["swing_lows"][-1]
    sr = sh["price"] - sl["price"]
    if sr <= 0:
        return None
    fl, fh = ICT["ote_fib_low"], ICT["ote_fib_high"]
    if ms["trend"] == "BULLISH":
        return {"direction": "LONG",
                "ote_top": round(sh["price"] - sr * fl, 5),
                "ote_bottom": round(sh["price"] - sr * fh, 5)}
    elif ms["trend"] == "BEARISH":
        return {"direction": "SHORT",
                "ote_top": round(sl["price"] + sr * fh, 5),
                "ote_bottom": round(sl["price"] + sr * fl, 5)}
    return None


# ── Premium / Discount ─────────────────────────
def calc_premium_discount(df) -> dict:
    if len(df) < 20:
        return {"zone": "NEUTRAL", "zone_pct": 50, "equilibrium": 0}
    lb = min(ICT["pd_lookback"], len(df))
    rh = float(df["high"].iloc[-lb:].max())
    rl = float(df["low"].iloc[-lb:].min())
    eq = (rh + rl) / 2
    cur = float(df["close"].iloc[-1])
    if rh == rl:
        return {"zone": "NEUTRAL", "zone_pct": 50, "equilibrium": eq}
    if cur > eq:
        pct = (cur - eq) / (rh - eq) * 100
        zone = "PREMIUM"
    else:
        pct = (eq - cur) / (eq - rl) * 100
        zone = "DISCOUNT"
    return {"zone": zone, "zone_pct": round(min(pct, 100), 1),
            "equilibrium": round(eq, 5), "range_high": round(rh, 5),
            "range_low": round(rl, 5), "current": round(cur, 5)}
