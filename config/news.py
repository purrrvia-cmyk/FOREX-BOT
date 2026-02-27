# ═══════════════════════════════════════
#  Haber & Ekonomik Takvim Ayarları
# ═══════════════════════════════════════

NEWS_CFG = {
    "enabled": True,
    "rss_feeds": {
        "ForexLive": "https://www.forexlive.com/feed/news",
        "FXStreet":  "https://www.fxstreet.com/rss/news",
    },
    "high_impact_pause_min": 30,
    "check_interval_sec": 300,
}

# Duygu analizi keyword listeleri
BULLISH_KW = {
    "USD": ["hawkish", "rate hike", "strong jobs", "beat expectations", "hot inflation",
            "strong gdp", "dollar strengthens", "fed tightening"],
    "EUR": ["ecb hawkish", "euro zone growth", "euro strengthens", "ecb rate hike"],
    "GBP": ["boe hawkish", "uk growth", "pound strengthens", "boe rate hike"],
    "JPY": ["boj tightening", "yen strengthens", "japan growth"],
    "AUD": ["rba hawkish", "australia growth", "iron ore rises"],
    "CAD": ["boc hawkish", "oil prices rise", "canada employment beats"],
    "CHF": ["snb hawkish", "swiss franc strengthens", "safe haven demand"],
    "NZD": ["rbnz hawkish", "new zealand growth", "dairy prices rise"],
    "XAU": ["gold rally", "safe haven", "inflation fears", "geopolitical risk",
            "central bank buying", "recession fears"],
    "XAG": ["silver rally", "industrial demand", "precious metals rise"],
}

BEARISH_KW = {
    "USD": ["dovish", "rate cut", "weak jobs", "miss expectations", "soft inflation",
            "weak gdp", "dollar weakens", "fed easing"],
    "EUR": ["ecb dovish", "euro zone recession", "euro weakens", "ecb rate cut"],
    "GBP": ["boe dovish", "uk recession", "pound weakens", "brexit"],
    "JPY": ["boj easing", "yen weakens", "japan recession", "negative rates"],
    "AUD": ["rba dovish", "australia slowdown", "iron ore drops", "china slowdown"],
    "CAD": ["boc dovish", "oil prices drop", "canada unemployment rises"],
    "CHF": ["snb dovish", "risk-on sentiment"],
    "NZD": ["rbnz dovish", "new zealand slowdown"],
    "XAU": ["gold sell-off", "risk appetite", "dollar strength", "yields rise"],
    "XAG": ["silver sell-off", "industrial slowdown", "precious metals drop"],
}
