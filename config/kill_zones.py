# ═══════════════════════════════════════
#  Kill Zone & Silver Bullet (UTC)
# ═══════════════════════════════════════

KILL_ZONES = {
    "ASIA":     {"start": 0,  "end": 6,  "label": "Asia Session",    "volatility": "low"},
    "LONDON":   {"start": 7,  "end": 10, "label": "London Open",     "volatility": "high"},
    "NEW_YORK": {"start": 12, "end": 15, "label": "New York Open",   "volatility": "high"},
}

SILVER_BULLETS = {
    "LONDON_SB": {"start": 8,  "end": 9,  "label": "London Silver Bullet"},
    "NY_AM_SB":  {"start": 15, "end": 16, "label": "NY AM Silver Bullet"},
    "NY_PM_SB":  {"start": 19, "end": 20, "label": "NY PM Silver Bullet"},
}
