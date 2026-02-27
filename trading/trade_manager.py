"""İşlem yönetimi: açma, kapatma, BE/trailing, PnL ($)"""

import logging
from datetime import datetime
from config.instruments import INSTRUMENTS
from database import db

logger = logging.getLogger("BOT.TRADE")


class TradeManager:
    """İşlem açma/kapatma + BE + trailing"""

    def __init__(self, capital_manager):
        self.capital = capital_manager

    def open_trade(self, signal_data: dict) -> dict | None:
        """Sinyal verisinden işlem aç"""
        key = signal_data["instrument"]
        sig = signal_data["signal"]
        sl_tp = signal_data.get("sl_tp")
        if not sl_tp or sig == "WAIT":
            return None

        # Risk kontrolleri
        daily = self.capital.check_daily_limit()
        if not daily["allowed"]:
            logger.warning(f"❌ {key}: {daily['reason']}")
            return None

        max_open = self.capital.check_max_open()
        if not max_open["allowed"]:
            logger.warning(f"❌ {key}: {max_open['reason']}")
            return None

        # Aynı paritede açık işlem var mı?
        open_trades = db.get_open_trades()
        if any(t["instrument"] == key for t in open_trades):
            return None

        direction = sl_tp["direction"]
        entry = signal_data["price"]
        sl = sl_tp["sl"]
        tp1 = sl_tp["tp1"]
        tp2 = sl_tp["tp2"]
        sl_dist = abs(entry - sl)

        lot_info = self.capital.calc_lot_size(key, sl_dist)
        if lot_info["lot"] <= 0:
            logger.warning(f"❌ {key}: Lot hesaplanamadı")
            return None

        # Konseptleri kaydet
        reasons = signal_data.get("reasons_bull", []) if "LONG" in sig else signal_data.get("reasons_bear", [])
        concepts = ", ".join(reasons[:10])

        trade_data = {
            "instrument": key,
            "direction": direction,
            "entry_price": entry,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "lot_size": lot_info["lot"],
            "risk_usd": lot_info["risk_usd"],
            "score": signal_data.get("net_score", 0),
            "kill_zone": signal_data.get("kill_zones", {}).get("active_zone", "NONE"),
            "concepts_used": concepts,
        }

        db.open_trade(**trade_data)
        logger.info(f"✅ TRADE AÇILDI: {key} {direction} @ {entry} | "
                     f"SL: {sl} TP1: {tp1} TP2: {tp2} | "
                     f"Lot: {lot_info['lot']} Risk: ${lot_info['risk_usd']}")

        return trade_data

    def check_trades(self) -> list:
        """Açık işlemleri kontrol et: SL/TP/BE/Trailing"""
        from core.data_feed import feed
        closed = []
        open_trades = db.get_open_trades()

        for trade in open_trades:
            key = trade["instrument"]
            price_data = feed.price(key)
            if not price_data:
                continue

            cur = price_data["last"]
            direction = trade["direction"]
            entry = trade["entry_price"]
            sl = trade["sl"]
            tp = trade["tp1"]
            tp2 = trade.get("tp2", tp)

            hit_sl, hit_tp, hit_tp2 = False, False, False
            if direction == "LONG":
                hit_sl = cur <= sl
                hit_tp = cur >= tp
                hit_tp2 = cur >= tp2
            else:
                hit_sl = cur >= sl
                hit_tp = cur <= tp
                hit_tp2 = cur <= tp2

            if hit_sl:
                self._close_trade(trade, cur, "SL_HIT")
                closed.append({"trade": trade, "reason": "SL_HIT", "close": cur})
            elif hit_tp2:
                self._close_trade(trade, cur, "TP2_HIT")
                closed.append({"trade": trade, "reason": "TP2_HIT", "close": cur})
            elif hit_tp:
                # TP1 hit: yarısını kapat, kalanı BE'ye çek
                self._partial_close(trade, cur)
            else:
                # Trailing SL / BE check
                self._update_trailing(trade, cur)

        return closed

    def _close_trade(self, trade, close_price: float, reason: str):
        """İşlemi kapat, PnL hesapla ($)"""
        key = trade["instrument"]
        inst = INSTRUMENTS.get(key)
        if not inst:
            return

        entry = trade["entry_price"]
        direction = trade["direction"]
        lot = trade.get("lot_size", 0.01)
        pip = inst["pip"]
        pip_val = inst["pip_val"]

        if direction == "LONG":
            pips = (close_price - entry) / pip
        else:
            pips = (entry - close_price) / pip

        pnl_usd = round(pips * pip_val * lot, 2)
        pnl_pct = round(pnl_usd / self.capital.balance * 100, 2) if self.capital.balance > 0 else 0

        db.close_trade(trade["id"], close_price, reason, pips, pnl_usd, pnl_pct)
        self.capital.on_trade_close(pnl_usd)

        emoji = "🟢" if pnl_usd >= 0 else "🔴"
        logger.info(f"{emoji} {key} {direction} kapatıldı ({reason}) | PnL: ${pnl_usd:+.2f}")

    def _partial_close(self, trade, cur_price: float):
        """TP1'de yarısını kapat, kalanın SL'ini BE'ye çek"""
        entry = trade["entry_price"]
        direction = trade["direction"]

        # BE'ye çek
        new_sl = entry  # Entry fiyatını SL yap (breakeven)
        db.update_trade(trade["id"], sl=new_sl, status="BE_TRAILING")
        logger.info(f"🔄 {trade['instrument']} BE'ye çekildi (TP1 hit)")

    def _update_trailing(self, trade, cur_price: float):
        """Trailing SL güncelle"""
        direction = trade["direction"]
        entry = trade["entry_price"]
        current_sl = trade["sl"]
        tp = trade["tp1"]

        risk = abs(entry - current_sl)
        if risk == 0:
            return

        if direction == "LONG":
            profit_pips = cur_price - entry
            if profit_pips > risk * 1.5:
                new_sl = max(current_sl, entry + risk * 0.5)
                if new_sl > current_sl:
                    db.update_trade(trade["id"], sl=round(new_sl, 5))
        else:
            profit_pips = entry - cur_price
            if profit_pips > risk * 1.5:
                new_sl = min(current_sl, entry - risk * 0.5)
                if new_sl < current_sl:
                    db.update_trade(trade["id"], sl=round(new_sl, 5))

    def summary(self) -> dict:
        """Açık işlem özeti"""
        open_trades = db.get_open_trades()
        stats = db.get_trade_stats()
        return {
            "open_count": len(open_trades),
            "open_trades": open_trades,
            "stats": stats,
        }
