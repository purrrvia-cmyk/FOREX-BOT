"""Sermaye yönetimi: $50 başlangıç, lot hesaplama, risk kontrolü"""

import logging
from config.capital import CAPITAL
from config.instruments import INSTRUMENTS
from database import db

logger = logging.getLogger("BOT.CAPITAL")


class CapitalManager:
    """$50 sermaye + 1:2 kaldıraç + %2 risk"""

    def __init__(self):
        self.reload()

    def reload(self):
        """Bakiyeyi DB'den oku"""
        hist = db.get_balance_history(limit=1)
        if hist:
            self.balance = hist[0]["balance"]
            self.equity = hist[0]["equity"]
        else:
            self.balance = CAPITAL["initial_balance"]
            self.equity = CAPITAL["initial_balance"]
            db.record_balance(self.balance, self.equity, event="INIT")

    @property
    def buying_power(self) -> float:
        return self.balance * CAPITAL["leverage"]

    @property
    def risk_per_trade(self) -> float:
        return self.balance * (CAPITAL["risk_per_trade_pct"] / 100)

    def calc_lot_size(self, key: str, sl_distance: float) -> dict:
        """SL mesafesine göre lot hesapla"""
        inst = INSTRUMENTS.get(key)
        if not inst or sl_distance <= 0:
            return {"lot": 0, "risk_usd": 0, "reason": "Geçersiz input"}

        risk_usd = self.risk_per_trade
        pip = inst["pip"]
        pip_val = inst["pip_val"]
        sl_pips = sl_distance / pip

        # risk_usd = lot * sl_pips * pip_val
        lot = risk_usd / (sl_pips * pip_val) if (sl_pips * pip_val) > 0 else 0
        lot = round(lot, 2)

        # Kaldıraç kontrolü: toplam pozisyon ≤ buying power
        # Not: Forex mikro lot varsayılan 1000 birim
        position_value = lot * 1000 * inst.get("pip", 0.0001) * 10000  # ≈ nominal
        if position_value > self.buying_power:
            lot = round(self.buying_power / (1000 * inst.get("pip", 0.0001) * 10000), 2)
            lot = max(lot, 0.01)

        return {
            "lot": lot,
            "risk_usd": round(risk_usd, 2),
            "sl_pips": round(sl_pips, 1),
            "pip_val": pip_val,
            "buying_power": round(self.buying_power, 2),
        }

    def check_daily_limit(self) -> dict:
        """Günlük kaybı kontrol et"""
        daily = db.get_daily_performance(limit=1)
        if daily:
            today_pnl = daily[0].get("pnl_usd", 0)
            max_loss = self.balance * (CAPITAL["max_daily_loss_pct"] / 100)
            if today_pnl < 0 and abs(today_pnl) >= max_loss:
                return {"allowed": False, "reason": f"Günlük kayıp limiti (${abs(today_pnl):.2f}/${max_loss:.2f})"}
        return {"allowed": True}

    def check_max_open(self) -> dict:
        """Açık işlem limiti"""
        open_trades = db.get_open_trades()
        if len(open_trades) >= CAPITAL["max_open_trades"]:
            return {"allowed": False, "reason": f"Maks açık işlem ({CAPITAL['max_open_trades']})"}
        return {"allowed": True}

    def on_trade_close(self, pnl_usd: float):
        """Kapanan işlem sonrası bakiye güncelle"""
        self.balance = round(self.balance + pnl_usd, 2)
        self.equity = self.balance
        db.record_balance(self.balance, self.equity, event="TRADE_CLOSE")
        logger.info(f"💰 Bakiye güncellendi: ${self.balance}")

    def status(self) -> dict:
        return {
            "balance": self.balance,
            "equity": self.equity,
            "buying_power": self.buying_power,
            "risk_per_trade": round(self.risk_per_trade, 2),
            "max_daily_loss": round(self.balance * CAPITAL["max_daily_loss_pct"] / 100, 2),
        }
