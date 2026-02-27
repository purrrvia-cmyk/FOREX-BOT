"""Risk yönetimi: günlük/haftalık limitler, korelasyon kontrolü"""

import logging
from database import db
from config.capital import CAPITAL

logger = logging.getLogger("BOT.RISK")


class RiskManager:
    """Risk kontrol katmanı"""

    # Korelasyonlu pariteler — aynı yönde çift işlem açma
    CORRELATED = [
        {"EURUSD", "GBPUSD"},       # Pozitif korelasyon
        {"USDCHF", "USDJPY"},       # USD bazlı
        {"AUDUSD", "NZDUSD"},       # Commodity currencies
    ]

    def check_all(self, key: str, direction: str) -> dict:
        """Tüm risk kontrollerini çalıştır"""
        checks = [
            self.check_daily_loss(),
            self.check_correlation(key, direction),
            self.check_consecutive_loss(),
            self.check_weekly_loss(),
        ]
        for c in checks:
            if not c["allowed"]:
                return c
        return {"allowed": True}

    def check_daily_loss(self) -> dict:
        daily = db.get_daily_performance(limit=1)
        if daily:
            pnl = daily[0].get("pnl_usd", 0)
            max_loss = 50 * (CAPITAL["max_daily_loss_pct"] / 100)  # TODO: dinamik bakiye
            if pnl < 0 and abs(pnl) >= max_loss:
                return {"allowed": False, "reason": f"Günlük kayıp limiti: ${abs(pnl):.2f}"}
        return {"allowed": True}

    def check_weekly_loss(self) -> dict:
        daily = db.get_daily_performance(limit=5)
        if daily:
            total = sum(d.get("pnl_usd", 0) for d in daily)
            if total < -5.0:  # $5 haftalık limit (%10)
                return {"allowed": False, "reason": f"Haftalık kayıp: ${abs(total):.2f}"}
        return {"allowed": True}

    def check_correlation(self, key: str, direction: str) -> dict:
        """Korelasyonlu paritelerde aynı yönde işlem kontrolü"""
        open_trades = db.get_open_trades()
        for group in self.CORRELATED:
            if key in group:
                for t in open_trades:
                    if t["instrument"] in group and t["instrument"] != key:
                        if t["direction"] == direction:
                            return {"allowed": False,
                                    "reason": f"Korelasyon: {t['instrument']} zaten {direction}"}
        return {"allowed": True}

    def check_consecutive_loss(self) -> dict:
        """3 ardışık zarar → 1 saat bekleme"""
        trades = db.get_trades(limit=3)
        if len(trades) >= 3:
            all_loss = all(t.get("pnl_usd", 0) < 0 for t in trades[:3])
            if all_loss:
                return {"allowed": False, "reason": "3 ardışık zarar → cooldown"}
        return {"allowed": True}
