"""16 ICT Konseptini birleştirip confluence skoru hesapla"""

import logging
from datetime import datetime

from config.instruments import INSTRUMENTS
from config.ict_params import ICT
from core.data_feed import feed
from core.indicators import calc_indicators
from core.market_structure import detect_market_structure
from core.order_blocks import (detect_order_blocks, detect_breaker_blocks,
                               detect_fvg, detect_displacement)
from core.liquidity import (detect_liquidity_sweeps, detect_inducement,
                            detect_smart_money_trap)
from core.sessions import (detect_kill_zone, detect_silver_bullet,
                           detect_amd, detect_judas, detect_asian_breakout,
                           calc_daily_bias, calc_ote, calc_premium_discount)
from core.sl_tp import calc_sl_tp

logger = logging.getLogger("BOT.ICT")


def calc_confluence(key: str, tf: str = "1h") -> dict:
    """Tek parite: 16 ICT konseptini çalıştır + skor üret"""
    df = feed.candles(key, tf)
    if df.empty or len(df) < 30:
        return {"error": "Yetersiz veri", "instrument": key}

    inst = INSTRUMENTS[key]
    cur = float(df["close"].iloc[-1])

    # Tüm analizler
    ms = detect_market_structure(df)
    obs = detect_order_blocks(df, cur)
    breakers = detect_breaker_blocks(df)
    fvgs = detect_fvg(df)
    disps = detect_displacement(df)
    sweeps = detect_liquidity_sweeps(df)
    inds = detect_inducement(df, ms)
    ote = calc_ote(df, ms)
    pd_zone = calc_premium_discount(df)
    kz = detect_kill_zone()
    sb = detect_silver_bullet()
    amd = detect_amd(df)
    judas = detect_judas(df)
    daily_bias = calc_daily_bias(feed, key)
    asian = detect_asian_breakout(df)
    smt = detect_smart_money_trap(df, ms)
    indicators = calc_indicators(df)

    # Skor
    bull, bear = 0, 0
    rb, rr = [], []
    cb, cbe = 0, 0

    # 1. Market Structure (30p)
    if ms["trend"] == "BULLISH":
        bull += 30; cb += 1; rb.append("Yapı: HH+HL yükseliş")
    elif ms["trend"] == "BEARISH":
        bear += 30; cbe += 1; rr.append("Yapı: LH+LL düşüş")

    for bos in ms["bos"]:
        if "BULLISH" in bos["type"]:
            bull += 10; cb += 1; rb.append(f"Bullish BOS @ {bos['level']:.5f}")
        else:
            bear += 10; cbe += 1; rr.append(f"Bearish BOS @ {bos['level']:.5f}")

    if ms["choch"]:
        if "BULLISH" in ms["choch"]["type"]:
            bull += 15; cb += 1; rb.append("Bullish CHoCH")
        else:
            bear += 15; cbe += 1; rr.append("Bearish CHoCH")

    # 2. Order Blocks (20p)
    active_obs = [o for o in obs if not o["mitigated"]]
    if any(o["type"] == "BULLISH_OB" and o["low"] <= cur <= o["high"] for o in active_obs):
        bull += 20; cb += 1; rb.append("Bullish OB içinde")
    if any(o["type"] == "BEARISH_OB" and o["low"] <= cur <= o["high"] for o in active_obs):
        bear += 20; cbe += 1; rr.append("Bearish OB içinde")

    # 3. Breaker (10p)
    if any(b["type"] == "BULLISH_BREAKER" for b in breakers):
        bull += 10; cb += 1; rb.append("Bullish Breaker")
    if any(b["type"] == "BEARISH_BREAKER" for b in breakers):
        bear += 10; cbe += 1; rr.append("Bearish Breaker")

    # 4. FVG (15p)
    active_fvg = [f for f in fvgs if not f["filled"] and f["idx"] >= len(df) - 15]
    bull_fvg = [f for f in active_fvg if f["type"] == "BULLISH_FVG"]
    bear_fvg = [f for f in active_fvg if f["type"] == "BEARISH_FVG"]
    if bull_fvg:
        pts = 15 if any(f["ce_tested"] for f in bull_fvg) else 10
        bull += pts; cb += 1; rb.append(f"{len(bull_fvg)} Bullish FVG")
    if bear_fvg:
        pts = 15 if any(f["ce_tested"] for f in bear_fvg) else 10
        bear += pts; cbe += 1; rr.append(f"{len(bear_fvg)} Bearish FVG")

    # 5. Displacement (10p)
    for d in [x for x in disps if x["idx"] >= len(df) - 5]:
        if "BULLISH" in d["type"]:
            bull += 10; cb += 1; rb.append(f"Bullish Disp ({d['body_mult']}x)")
        else:
            bear += 10; cbe += 1; rr.append(f"Bearish Disp ({d['body_mult']}x)")

    # 6. Sweeps (15p)
    for s in [x for x in sweeps if x["idx"] >= len(df) - 5]:
        if s["type"] == "SSL_SWEEP":
            bull += 15; cb += 1; rb.append("SSL sweep → bullish")
        elif s["type"] == "BSL_SWEEP":
            bear += 15; cbe += 1; rr.append("BSL sweep → bearish")

    # 7. Inducement (5p)
    if any(i["type"] == "BULLISH_INDUCEMENT" for i in inds):
        bull += 5; rb.append("Bullish Inducement")
    if any(i["type"] == "BEARISH_INDUCEMENT" for i in inds):
        bear += 5; rr.append("Bearish Inducement")

    # 8. OTE (10p)
    if ote:
        if ote["direction"] == "LONG" and ote["ote_bottom"] <= cur <= ote["ote_top"]:
            bull += 10; cb += 1; rb.append("OTE alım bölgesinde")
        elif ote["direction"] == "SHORT" and ote["ote_bottom"] <= cur <= ote["ote_top"]:
            bear += 10; cbe += 1; rr.append("OTE satış bölgesinde")

    # 9. Premium/Discount (10p)
    if pd_zone["zone"] == "DISCOUNT" and pd_zone["zone_pct"] > 60:
        bull += 10; cb += 1; rb.append(f"Discount %{pd_zone['zone_pct']}")
    elif pd_zone["zone"] == "PREMIUM" and pd_zone["zone_pct"] > 60:
        bear += 10; cbe += 1; rr.append(f"Premium %{pd_zone['zone_pct']}")

    # 10. Kill Zone (5p bonus)
    if kz["is_kill_zone"]:
        if bull > bear:
            bull += 5; rb.append(f"{kz['active_zone']} KZ aktif")
        elif bear > bull:
            bear += 5; rr.append(f"{kz['active_zone']} KZ aktif")

    # 11. Silver Bullet (5p)
    if sb["is_active"] and (bull_fvg or bear_fvg):
        if bull > bear:
            bull += 5; rb.append("Silver Bullet + FVG")
        else:
            bear += 5; rr.append("Silver Bullet + FVG")

    # 12. AMD (15p)
    if amd:
        if amd["direction"] == "LONG":
            bull += 15; cb += 1; rb.append("AMD Bullish")
        else:
            bear += 15; cbe += 1; rr.append("AMD Bearish")

    # 13. Judas (15p)
    if judas:
        if "BULLISH" in judas["type"]:
            bull += 15; cb += 1; rb.append("Judas → yukarı")
        else:
            bear += 15; cbe += 1; rr.append("Judas → aşağı")

    # 14. Daily Bias (15p)
    if daily_bias["bias"] == "BULLISH":
        bull += 15; cb += 1; rb.append("Günlük Bias: YÜKSELİŞ")
    elif daily_bias["bias"] == "BEARISH":
        bear += 15; cbe += 1; rr.append("Günlük Bias: DÜŞÜŞ")

    # 15. Asian Breakout (5p)
    if asian and asian["type"] != "INSIDE_RANGE":
        if "BULLISH" in asian["type"]:
            bull += 5; rb.append("Asian yukarı kırılım")
        else:
            bear += 5; rr.append("Asian aşağı kırılım")

    # 16. Smart Money Trap (15p)
    if smt:
        if smt["type"] == "BEAR_TRAP":
            bull += 15; cb += 1; rb.append("Bear Trap → LONG")
        elif smt["type"] == "BULL_TRAP":
            bear += 15; cbe += 1; rr.append("Bull Trap → SHORT")

    # RSI (5p)
    if indicators["rsi"] < 35:
        bull += 5; rb.append(f"RSI aşırı satım ({indicators['rsi']:.0f})")
    elif indicators["rsi"] > 65:
        bear += 5; rr.append(f"RSI aşırı alım ({indicators['rsi']:.0f})")

    # ═══ CEZALAR ═══
    if not kz["is_kill_zone"]:
        if bull > bear:
            bull -= 10; rb.append("KZ dışında (-10)")
        elif bear > bull:
            bear -= 10; rr.append("KZ dışında (-10)")

    if pd_zone["zone"] == "PREMIUM" and pd_zone["zone_pct"] > 75:
        bull -= 15; rb.append("Premium'da LONG riskli (-15)")
    elif pd_zone["zone"] == "DISCOUNT" and pd_zone["zone_pct"] > 75:
        bear -= 15; rr.append("Discount'ta SHORT riskli (-15)")

    if daily_bias["bias"] == "BEARISH" and bull > bear:
        bull -= 10; rb.append("HTF ters yön (-10)")
    elif daily_bias["bias"] == "BULLISH" and bear > bull:
        bear -= 10; rr.append("HTF ters yön (-10)")

    # ═══ SİNYAL KARARI ═══
    net = bull - bear
    mcs = ICT["min_confluence_strong"]
    mss = ICT["min_score_strong"]
    mcn = ICT["min_confluence_normal"]
    msn = ICT["min_score_normal"]

    if net >= mss and cb >= mcs:
        signal = "STRONG_LONG"
    elif net >= msn and cb >= mcn:
        signal = "LONG"
    elif net <= -mss and cbe >= mcs:
        signal = "STRONG_SHORT"
    elif net <= -msn and cbe >= mcn:
        signal = "SHORT"
    else:
        signal = "WAIT"

    sl_tp = calc_sl_tp(signal, cur, indicators["atr"], df, obs)

    return {
        "instrument": key, "name": inst["name"], "price": cur,
        "timeframe": tf, "signal": signal,
        "net_score": net, "bull_score": bull, "bear_score": bear,
        "conf_bull": cb, "conf_bear": cbe,
        "reasons_bull": rb, "reasons_bear": rr, "sl_tp": sl_tp,
        "market_structure": ms, "order_blocks": active_obs[:5],
        "breaker_blocks": breakers, "fvg": active_fvg[:6],
        "displacement": disps, "liquidity_sweeps": sweeps,
        "inducement": inds, "ote": ote, "premium_discount": pd_zone,
        "kill_zones": kz, "silver_bullet": sb, "amd": amd,
        "judas": judas, "daily_bias": daily_bias,
        "asian_breakout": asian, "smart_money_trap": smt,
        "indicators": indicators, "timestamp": datetime.now().isoformat(),
    }
