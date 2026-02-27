# ═══════════════════════════════════════
#  ICT / SMC Strateji Parametreleri
# ═══════════════════════════════════════

ICT = {
    # ── Market Structure ──
    "swing_lookback": 5,
    "structure_min_candles": 20,

    # ── Order Blocks ──
    "ob_min_strength": 2.0,
    "ob_max_age": 30,

    # ── FVG ──
    "fvg_max_age": 20,
    "fvg_ce_bonus": True,

    # ── Displacement ──
    "disp_body_mult": 2.5,
    "disp_body_ratio": 0.7,

    # ── Liquidity Sweep ──
    "sweep_tolerance": 0.001,
    "sweep_lookback": 15,

    # ── OTE (Fibonacci) ──
    "ote_fib_low": 0.618,
    "ote_fib_high": 0.786,

    # ── Premium/Discount ──
    "pd_lookback": 50,
    "pd_strong_threshold": 60,

    # ── Confluence Eşikleri ──
    "min_confluence_strong": 5,
    "min_score_strong": 55,
    "min_confluence_normal": 3,
    "min_score_normal": 30,

    # ── Kill Zone Dışı İstisna ──
    # KZ dışında bu confluence + daily+4H uyum + haber temiz → giriş izni
    "non_kz_min_confluence": 6,
    "non_kz_min_score": 70,

    # ── SL / TP ──
    "sl_atr_mult": 1.2,
    "tp1_rr": 1.8,
    "tp2_rr": 3.0,

    # ── Trade Management ──
    "be_threshold_pct": 60,
    "trailing_threshold_pct": 75,
    "trailing_lock_pct": 50,
}
