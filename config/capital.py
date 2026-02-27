# ═══════════════════════════════════════
#  Sermaye & Risk Yönetimi Ayarları
# ═══════════════════════════════════════

CAPITAL = {
    "initial_balance": 50.00,       # Başlangıç sermayesi ($)
    "leverage": 2,                  # Kaldıraç (1:2)
    "risk_per_trade_pct": 2.0,     # Trade başına risk (%)
    "max_concurrent_trades": 3,
    "max_same_direction": 2,
    "cooldown_minutes": 30,
    "max_daily_loss_pct": 6.0,     # Günlük max kayıp → durdur (%)
    "max_trade_duration_hours": 12,
    "scan_interval_sec": 120,       # 2dk — 1D/4H/1H tarama
    "trade_check_sec": 30,          # 30sn — açık trade kontrol
    "entry_scan_sec": 30,           # 30sn — aktif sinyalde 15M/5M giriş tarama
}

# Öğrenme motoru
LEARNING = {
    "min_trades_to_learn": 50,     # Bu sayıya kadar sadece kaydet, müdahale etme
    "good_winrate": 60,            # %60+ → bonus
    "bad_winrate": 35,             # %35- → ceza
    "disable_winrate": 20,         # %20- → pattern devre dışı (30 gün)
    "review_period_days": 7,       # Haftalık analiz
}
