# ═══════════════════════════════════════
#  Major Pariteler + Altın + Gümüş
# ═══════════════════════════════════════

INSTRUMENTS = {
    "EURUSD": {
        "yf": "EURUSD=X",
        "name": "EUR/USD",
        "cat": "major",
        "pip": 0.0001,
        "pip_val": 0.10,       # $ per pip per micro lot (0.01)
        "spread": 1.0,
        "icon": "€",
    },
    "GBPUSD": {
        "yf": "GBPUSD=X",
        "name": "GBP/USD",
        "cat": "major",
        "pip": 0.0001,
        "pip_val": 0.10,
        "spread": 1.5,
        "icon": "£",
    },
    "USDJPY": {
        "yf": "USDJPY=X",
        "name": "USD/JPY",
        "cat": "major",
        "pip": 0.01,
        "pip_val": 0.07,
        "spread": 1.0,
        "icon": "¥",
    },
    "USDCHF": {
        "yf": "USDCHF=X",
        "name": "USD/CHF",
        "cat": "major",
        "pip": 0.0001,
        "pip_val": 0.10,
        "spread": 1.5,
        "icon": "₣",
    },
    "AUDUSD": {
        "yf": "AUDUSD=X",
        "name": "AUD/USD",
        "cat": "major",
        "pip": 0.0001,
        "pip_val": 0.10,
        "spread": 1.5,
        "icon": "A$",
    },
    "NZDUSD": {
        "yf": "NZDUSD=X",
        "name": "NZD/USD",
        "cat": "major",
        "pip": 0.0001,
        "pip_val": 0.10,
        "spread": 2.0,
        "icon": "NZ$",
    },
    "USDCAD": {
        "yf": "USDCAD=X",
        "name": "USD/CAD",
        "cat": "major",
        "pip": 0.0001,
        "pip_val": 0.08,
        "spread": 1.5,
        "icon": "C$",
    },
    "XAUUSD": {
        "yf": "GC=F",
        "name": "XAU/USD",
        "cat": "commodity",
        "pip": 0.01,
        "pip_val": 0.10,
        "spread": 3.0,
        "icon": "🥇",
    },
    "XAGUSD": {
        "yf": "SI=F",
        "name": "XAG/USD",
        "cat": "commodity",
        "pip": 0.001,
        "pip_val": 0.05,
        "spread": 3.5,
        "icon": "🥈",
        "fallback": True,   # veri sorunu olursa devre dışı
    },
}

# Timeframe haritası
TF_MAP = {
    "5m":  {"interval": "5m",  "period": "5d"},
    "15m": {"interval": "15m", "period": "5d"},
    "1h":  {"interval": "1h",  "period": "30d"},
    "4h":  {"interval": "1h",  "period": "60d", "aggregate": 4},
    "1d":  {"interval": "1d",  "period": "6mo"},
}
