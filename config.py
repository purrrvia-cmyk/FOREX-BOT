# =====================================================
# FOREX ICT Trading Bot — Konfigürasyon
# =====================================================
# %100 ICT Uyumlu Forex Major Pariteler Botu
# Inner Circle Trader metodolojisi ile sinyal üretimi
# =====================================================

# ── FOREX MAJOR PARITELER ──
FOREX_INSTRUMENTS = {
    "EURUSD": {
        "yf_symbol": "EURUSD=X",
        "name": "EUR/USD",
        "category": "major",
        "pip_size": 0.0001,
        "icon": "€",
        "desc": "Euro / ABD Doları",
        "spread_avg": 1.0,  # ortalama spread (pip)
    },
    "GBPUSD": {
        "yf_symbol": "GBPUSD=X",
        "name": "GBP/USD",
        "category": "major",
        "pip_size": 0.0001,
        "icon": "£",
        "desc": "İngiliz Sterlini / ABD Doları",
        "spread_avg": 1.5,
    },
    "USDJPY": {
        "yf_symbol": "USDJPY=X",
        "name": "USD/JPY",
        "category": "major",
        "pip_size": 0.01,
        "icon": "¥",
        "desc": "ABD Doları / Japon Yeni",
        "spread_avg": 1.0,
    },
    "USDCHF": {
        "yf_symbol": "USDCHF=X",
        "name": "USD/CHF",
        "category": "major",
        "pip_size": 0.0001,
        "icon": "₣",
        "desc": "ABD Doları / İsviçre Frangı",
        "spread_avg": 1.5,
    },
    "AUDUSD": {
        "yf_symbol": "AUDUSD=X",
        "name": "AUD/USD",
        "category": "major",
        "pip_size": 0.0001,
        "icon": "A$",
        "desc": "Avustralya Doları / ABD Doları",
        "spread_avg": 1.5,
    },
    "NZDUSD": {
        "yf_symbol": "NZDUSD=X",
        "name": "NZD/USD",
        "category": "major",
        "pip_size": 0.0001,
        "icon": "NZ$",
        "desc": "Yeni Zelanda Doları / ABD Doları",
        "spread_avg": 2.0,
    },
    "USDCAD": {
        "yf_symbol": "USDCAD=X",
        "name": "USD/CAD",
        "category": "major",
        "pip_size": 0.0001,
        "icon": "C$",
        "desc": "ABD Doları / Kanada Doları",
        "spread_avg": 1.5,
    },
    "XAUUSD": {
        "yf_symbol": "GC=F",
        "name": "XAU/USD",
        "category": "commodity",
        "pip_size": 0.01,
        "icon": "🥇",
        "desc": "Altın / ABD Doları",
        "spread_avg": 3.0,
    },
}

# ── TIMEFRAME AYARLARI ──
TF_MAP = {
    "5m":  {"interval": "5m",  "period": "5d",  "label": "5 Dakika"},
    "15m": {"interval": "15m", "period": "5d",  "label": "15 Dakika"},
    "1h":  {"interval": "1h",  "period": "30d", "label": "1 Saat"},
    "4h":  {"interval": "1h",  "period": "60d", "label": "4 Saat"},  # 1h → 4h aggregate
    "1d":  {"interval": "1d",  "period": "6mo", "label": "Günlük"},
}

# ── ICT PARAMETRELERI ──
ICT_PARAMS = {
    # Market Structure
    "swing_lookback": 5,           # Swing H/L tespiti penceresi
    "structure_min_candles": 20,   # Min mum sayısı

    # Order Blocks
    "ob_min_strength": 2.0,        # OB minimum güç (next_move / avg_range)
    "ob_max_age": 30,              # OB max yaşı (mum sayısı)

    # FVG
    "fvg_max_age": 20,             # FVG max yaşı
    "fvg_ce_bonus": True,          # CE test edilmiş FVG'ye bonus puan

    # Displacement
    "disp_body_mult": 2.5,        # Displacement min body/avg oranı
    "disp_body_ratio": 0.7,       # Body/range min oranı

    # Liquidity Sweep
    "sweep_tolerance": 0.001,      # EQH/EQL toleransı (%0.1)
    "sweep_lookback": 15,          # Sweep arama penceresi

    # OTE (Fibonacci)
    "ote_fib_low": 0.618,         # OTE alt sınırı
    "ote_fib_high": 0.786,        # OTE üst sınırı

    # Premium/Discount
    "pd_lookback": 50,            # P/D hesaplama penceresi
    "pd_strong_threshold": 60,    # Güçlü zone eşiği (%)

    # Signal Generation
    "min_confluence_strong": 5,    # STRONG sinyal min confluence
    "min_score_strong": 55,        # STRONG sinyal min skor
    "min_confluence_normal": 3,    # Normal sinyal min confluence
    "min_score_normal": 30,        # Normal sinyal min skor

    # SL/TP
    "sl_atr_mult": 1.2,           # SL = ATR × bu değer
    "tp1_rr": 1.8,                # TP1 R:R oranı
    "tp2_rr": 3.0,                # TP2 R:R oranı

    # Trade Management
    "be_threshold_pct": 0.60,      # Breakeven tetikleme: TP'nin %60'ı
    "trailing_threshold_pct": 0.75, # Trailing tetikleme: TP'nin %75'i
    "trailing_lock_pct": 0.50,     # Trailing kâr kilitleme: %50

    # Risk Management
    "max_concurrent_trades": 3,    # Max eşzamanlı işlem
    "max_same_direction": 2,       # Max aynı yönde işlem
    "max_trade_duration_hours": 8, # Max trade süresi (forex = daha uzun)
    "signal_cooldown_minutes": 30, # Aynı paritede sinyal arası bekleme

    # Scanner
    "scan_interval_seconds": 120,  # Tarama aralığı (2 dk)
    "trade_check_interval": 30,    # Açık trade kontrol aralığı (30 sn)
}

# ── KILL ZONE SAATLERİ (EST bazlı) ──
KILL_ZONES = {
    "ASIAN":  {"est_start": 20, "est_end": 0,  "desc": "Asya seansı — düşük volatilite, range oluşumu"},
    "LONDON": {"est_start": 2,  "est_end": 5,  "desc": "London açılışı — yüksek likidite, trend başlangıcı"},
    "NEWYORK":{"est_start": 7,  "est_end": 10, "desc": "NY açılışı — London overlap, en volatil dönem"},
}

# ── SILVER BULLET PENCERELERİ (EST bazlı) ──
SILVER_BULLET = {
    "LONDON_SB":  {"est_start": 3,  "est_end": 4,  "desc": "London Silver Bullet — FVG giriş fırsatı"},
    "NY_AM_SB":   {"est_start": 10, "est_end": 11, "desc": "NY Sabah Silver Bullet"},
    "NY_PM_SB":   {"est_start": 14, "est_end": 15, "desc": "NY Öğleden Sonra Silver Bullet"},
}

# ── HABER KAYNAKLARI ──
NEWS_CONFIG = {
    "enabled": True,
    "rss_feeds": [
        "https://www.forexlive.com/feed/news",
        "https://www.fxstreet.com/rss/news",
    ],
    "high_impact_pause_minutes": 30,  # Yüksek etkili haber öncesi/sonrası trade askıya al
    "check_interval_seconds": 300,    # Haber kontrolü (5 dk)
}

# ── WEB APP ──
WEB_CONFIG = {
    "host": "0.0.0.0",
    "port": 5001,
    "debug": False,
}
