"""SL/TP hesaplama: ATR + Swing + OB bazlı"""

from config.ict_params import ICT


def calc_sl_tp(signal: str, cur_price: float, atr: float, df, obs: list) -> dict | None:
    if signal == "WAIT" or atr == 0:
        return None

    sl_mult = ICT["sl_atr_mult"]
    tp1_rr = ICT["tp1_rr"]
    tp2_rr = ICT["tp2_rr"]

    swing_lb = min(20, len(df) - 1)
    recent_high = float(df["high"].iloc[-swing_lb:].max())
    recent_low = float(df["low"].iloc[-swing_lb:].min())

    active_obs = [o for o in obs if not o.get("mitigated", False)]
    ob_top = active_obs[-1].get("high") if active_obs else None
    ob_bottom = active_obs[-1].get("low") if active_obs else None

    if signal in ("STRONG_LONG", "LONG"):
        atr_sl = cur_price - atr * sl_mult
        swing_sl = recent_low - atr * 0.15
        candidates = [atr_sl, swing_sl]
        if ob_bottom:
            candidates.append(ob_bottom - atr * 0.1)
        sl = round(max(candidates), 5)
        if abs(cur_price - sl) < atr * 0.4:
            sl = round(atr_sl, 5)
        risk = abs(cur_price - sl)
        tp1 = round(cur_price + risk * tp1_rr, 5)
        tp2 = round(cur_price + risk * tp2_rr, 5)
    else:  # SHORT
        atr_sl = cur_price + atr * sl_mult
        swing_sl = recent_high + atr * 0.15
        candidates = [atr_sl, swing_sl]
        if ob_top:
            candidates.append(ob_top + atr * 0.1)
        sl = round(max(candidates), 5)
        if abs(sl - cur_price) < atr * 0.4:
            sl = round(atr_sl, 5)
        risk = abs(sl - cur_price)
        tp1 = round(cur_price - risk * tp1_rr, 5)
        tp2 = round(cur_price - risk * tp2_rr, 5)

    rr1 = round(abs(tp1 - cur_price) / risk, 2) if risk > 0 else 0
    rr2 = round(abs(tp2 - cur_price) / risk, 2) if risk > 0 else 0

    return {"sl": sl, "tp1": tp1, "tp2": tp2,
            "direction": "LONG" if "LONG" in signal else "SHORT",
            "rr1": rr1, "rr2": rr2}
