# =====================================================
# FOREX ICT Trading Bot — Trade Manager
# =====================================================
# Açık pozisyonları yönetir:
#   - BE (Break-Even) taşıma
#   - Trailing Stop güncelleme
#   - SL/TP kontrolü
#   - Pozisyon kapatma
# =====================================================

import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional

from config import FOREX_INSTRUMENTS, ICT_PARAMS
from database import db
from ict_engine import ict_engine

logger = logging.getLogger("FOREX-BOT.TRADE")


class TradeManager:
    """
    Açık trade'leri yönetir.

    BE Kuralı:
      Fiyat TP yönünde [be_threshold]% ilerlerse → SL'yi giriş fiyatına taşı.

    Trailing Kuralı:
      Fiyat TP yönünde [trailing_threshold]% ilerlerse →
      SL'yi (şu anki ilerlemenin [trailing_lock_pct]%'ine) taşı.
    """

    def __init__(self):
        self.be_threshold = ICT_PARAMS.get("be_threshold_pct", 60) / 100
        self.trailing_threshold = ICT_PARAMS.get("trailing_threshold_pct", 75) / 100
        self.trailing_lock_pct = ICT_PARAMS.get("trailing_lock_pct", 50) / 100
        self._trade_lock = threading.Lock()

    def open_new_trade(self, signal_data: Dict, signal_id: int = None) -> Optional[int]:
        """
        Yeni sinyal geldiğinde trade aç.
        Kontroller:
         - WAIT sinyali → açma
         - Aynı enstrümanda açık trade → açma
         - Max eşzamanlı trade limiti → açma
         - Aynı yönde max trade limiti → açma
         - Cooldown süresi → açma
         - SL/TP yoksa → açma
         - SL yönü yanlışsa → açma
        """
        instrument = signal_data.get("instrument")
        signal = signal_data.get("signal", "WAIT")

        if signal == "WAIT":
            return None

        direction = "LONG" if "LONG" in signal else "SHORT"

        with self._trade_lock:
            return self._open_trade_locked(signal_data, signal_id, instrument, direction)

    def _open_trade_locked(self, signal_data, signal_id, instrument, direction):
        """Lock altında trade açma — race condition önlenir."""
        # Aynı enstrümanda açık trade var mı?
        open_trades = db.get_open_trades()
        for t in open_trades:
            if t["instrument"] == instrument:
                logger.info(f"{instrument} için zaten açık trade var (ID:{t['id']})")
                return None

        # Max eşzamanlı trade limiti
        max_concurrent = ICT_PARAMS.get("max_concurrent_trades", 3)
        if len(open_trades) >= max_concurrent:
            logger.info(f"Max eşzamanlı trade limiti ({max_concurrent}) dolu")
            return None

        # Aynı yönde max trade limiti
        max_same_dir = ICT_PARAMS.get("max_same_direction", 2)
        same_dir_count = sum(1 for t in open_trades if t["direction"] == direction)
        if same_dir_count >= max_same_dir:
            logger.info(f"Aynı yönde ({direction}) max {max_same_dir} trade limiti dolu")
            return None

        # Cooldown kontrolü: Son kapatılan trade'den beri bekleme süresi
        cooldown_min = ICT_PARAMS.get("signal_cooldown_minutes", 30)
        recent_trades = db.get_trades(instrument=instrument, limit=1)
        if recent_trades:
            last_trade = recent_trades[0]
            closed_at = last_trade.get("closed_at")
            if closed_at:
                try:
                    from datetime import datetime as dt_cls
                    closed_time = dt_cls.fromisoformat(closed_at)
                    elapsed = (datetime.now() - closed_time).total_seconds() / 60
                    if elapsed < cooldown_min:
                        logger.info(f"{instrument}: Cooldown aktif ({elapsed:.0f}/{cooldown_min} dk)")
                        return None
                except (ValueError, TypeError):
                    pass

        sl_tp = signal_data.get("sl_tp")
        if not sl_tp:
            logger.warning(f"{instrument}: SL/TP hesaplanamadı, trade açılmıyor")
            return None

        # SL yön kontrolü
        entry_price = signal_data.get("price", 0)
        sl_price = sl_tp["sl"]
        tp1_price = sl_tp["tp1"]
        if direction == "LONG":
            if sl_price >= entry_price:
                logger.warning(f"{instrument}: LONG SL ({sl_price}) >= entry ({entry_price}), trade açılmıyor")
                return None
            if tp1_price <= entry_price:
                logger.warning(f"{instrument}: LONG TP1 ({tp1_price}) <= entry ({entry_price}), trade açılmıyor")
                return None
        else:  # SHORT
            if sl_price <= entry_price:
                logger.warning(f"{instrument}: SHORT SL ({sl_price}) <= entry ({entry_price}), trade açılmıyor")
                return None
            if tp1_price >= entry_price:
                logger.warning(f"{instrument}: SHORT TP1 ({tp1_price}) >= entry ({entry_price}), trade açılmıyor")
                return None

        trade_id = db.open_trade(
            signal_id=signal_id or 0,
            instrument=instrument,
            direction=direction,
            entry_price=entry_price,
            sl=sl_tp["sl"],
            tp1=sl_tp["tp1"],
            tp2=sl_tp.get("tp2"),
        )

        if trade_id:
            logger.info(
                f"✅ YENİ TRADE #{trade_id}: {instrument} {direction} "
                f"@ {entry_price} | SL: {sl_tp['sl']} | TP1: {sl_tp['tp1']} | TP2: {sl_tp.get('tp2')}"
            )
        return trade_id

    def check_all_trades(self):
        """
        Tüm açık trade'leri kontrol et:
        1. Güncel fiyatı çek
        2. SL/TP hit kontrolü
        3. BE taşıma kontrolü
        4. Trailing stop güncelle
        """
        open_trades = db.get_open_trades()
        if not open_trades:
            return []

        results = []
        for trade in open_trades:
            try:
                result = self._check_single_trade(trade)
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"Trade check hatası (#{trade['id']}): {e}")

        return results

    def _check_single_trade(self, trade: Dict) -> Optional[Dict]:
        """Tek bir trade'i kontrol et"""
        instrument = trade["instrument"]
        trade_id = trade["id"]
        direction = trade["direction"]
        entry = trade["entry_price"]
        sl = trade["sl"]
        tp1 = trade["tp1"]
        tp2 = trade.get("tp2") or tp1

        # Güncel fiyat
        price_info = ict_engine.get_price(instrument)
        if not price_info:
            return None
        cur_price = price_info["last"]

        # Fiyat güncelle
        db.update_trade(trade_id, current_price=cur_price)

        pip_size = FOREX_INSTRUMENTS.get(instrument, {}).get("pip_size", 0.0001)

        if direction == "LONG":
            pnl_pips = (cur_price - entry) / pip_size
            tp_distance = tp1 - entry
            progress = (cur_price - entry) / tp_distance if tp_distance > 0 else 0

            # SL Hit
            if cur_price <= sl:
                return self._close_trade(trade_id, instrument, direction, entry, cur_price, sl, "SL_HIT", pip_size)

            # TP1 Hit
            if cur_price >= tp1:
                return self._close_trade(trade_id, instrument, direction, entry, cur_price, tp1, "TP1_HIT", pip_size)

            # TP2 Hit
            if tp2 and cur_price >= tp2:
                return self._close_trade(trade_id, instrument, direction, entry, cur_price, tp2, "TP2_HIT", pip_size)

            # BE Taşıma
            if not trade.get("be_triggered") and progress >= self.be_threshold:
                new_sl = entry + pip_size * 2  # 2 pip yukarı (spread koruması)
                db.update_trade(trade_id, sl=new_sl, be_triggered=1)
                logger.info(f"🔒 BE #{trade_id}: {instrument} SL → {new_sl:.5f} (entry + spread)")
                return {"action": "BE_MOVE", "trade_id": trade_id, "new_sl": new_sl}

            # Trailing Stop
            if trade.get("be_triggered") and progress >= self.trailing_threshold:
                locked_progress = progress * self.trailing_lock_pct
                new_sl = entry + tp_distance * locked_progress
                old_sl = trade.get("trailing_sl") or sl
                if new_sl > old_sl:
                    db.update_trade(trade_id, sl=new_sl, trailing_sl=new_sl, trailing_active=1)
                    logger.info(f"📈 TRAIL #{trade_id}: {instrument} SL → {new_sl:.5f}")
                    return {"action": "TRAILING_UPDATE", "trade_id": trade_id, "new_sl": new_sl}

        elif direction == "SHORT":
            pnl_pips = (entry - cur_price) / pip_size
            tp_distance = entry - tp1
            progress = (entry - cur_price) / tp_distance if tp_distance > 0 else 0

            # SL Hit
            if cur_price >= sl:
                return self._close_trade(trade_id, instrument, direction, entry, cur_price, sl, "SL_HIT", pip_size)

            # TP1 Hit
            if cur_price <= tp1:
                return self._close_trade(trade_id, instrument, direction, entry, cur_price, tp1, "TP1_HIT", pip_size)

            # TP2 Hit
            if tp2 and cur_price <= tp2:
                return self._close_trade(trade_id, instrument, direction, entry, cur_price, tp2, "TP2_HIT", pip_size)

            # BE Taşıma
            if not trade.get("be_triggered") and progress >= self.be_threshold:
                new_sl = entry - pip_size * 2
                db.update_trade(trade_id, sl=new_sl, be_triggered=1)
                logger.info(f"🔒 BE #{trade_id}: {instrument} SL → {new_sl:.5f}")
                return {"action": "BE_MOVE", "trade_id": trade_id, "new_sl": new_sl}

            # Trailing Stop
            if trade.get("be_triggered") and progress >= self.trailing_threshold:
                locked_progress = progress * self.trailing_lock_pct
                new_sl = entry - tp_distance * locked_progress
                old_sl = trade.get("trailing_sl") or sl
                if new_sl < old_sl:
                    db.update_trade(trade_id, sl=new_sl, trailing_sl=new_sl, trailing_active=1)
                    logger.info(f"📉 TRAIL #{trade_id}: {instrument} SL → {new_sl:.5f}")
                    return {"action": "TRAILING_UPDATE", "trade_id": trade_id, "new_sl": new_sl}

        return None

    def _close_trade(self, trade_id, instrument, direction, entry, cur_price, hit_price,
                     reason, pip_size) -> Dict:
        """Trade'i kapat"""
        if direction == "LONG":
            pnl_pips = round((hit_price - entry) / pip_size, 2)
        else:
            pnl_pips = round((entry - hit_price) / pip_size, 2)

        pnl_pct = round(pnl_pips * pip_size / entry * 100, 4)

        db.close_trade(trade_id, close_price=hit_price,
                       close_reason=reason, pnl_pips=pnl_pips, pnl_pct=pnl_pct)

        icon = "✅" if pnl_pips > 0 else "❌"
        logger.info(
            f"{icon} KAPANDI #{trade_id}: {instrument} {direction} "
            f"| {reason} @ {hit_price:.5f} | PnL: {pnl_pips:+.1f} pips ({pnl_pct:+.4f}%)"
        )

        return {
            "action": "CLOSED", "trade_id": trade_id,
            "instrument": instrument, "direction": direction,
            "reason": reason, "pnl_pips": pnl_pips, "pnl_pct": pnl_pct,
        }

    def force_close(self, trade_id: int, reason: str = "MANUAL") -> Optional[Dict]:
        """Trade'i elle kapat"""
        trades = db.get_trades(status="OPEN")
        trade = next((t for t in trades if t["id"] == trade_id), None)
        if not trade:
            return None

        price_info = ict_engine.get_price(trade["instrument"])
        if not price_info:
            return None

        pip_size = FOREX_INSTRUMENTS.get(trade["instrument"], {}).get("pip_size", 0.0001)
        return self._close_trade(
            trade_id, trade["instrument"], trade["direction"],
            trade["entry_price"], price_info["last"], price_info["last"],
            reason, pip_size
        )

    def get_portfolio_summary(self) -> Dict:
        """Açık pozisyon özeti"""
        open_trades = db.get_open_trades()
        total_pnl = 0
        positions = []

        for t in open_trades:
            pip_size = FOREX_INSTRUMENTS.get(t["instrument"], {}).get("pip_size", 0.0001)
            cur = t.get("current_price") or t["entry_price"]
            if t["direction"] == "LONG":
                pnl = (cur - t["entry_price"]) / pip_size
            else:
                pnl = (t["entry_price"] - cur) / pip_size
            total_pnl += pnl
            positions.append({
                "id": t["id"],
                "instrument": t["instrument"],
                "direction": t["direction"],
                "entry": t["entry_price"],
                "current": cur,
                "sl": t["sl"],
                "tp1": t["tp1"],
                "pnl_pips": round(pnl, 1),
                "be_triggered": bool(t.get("be_triggered")),
                "trailing_active": bool(t.get("trailing_active")),
            })

        return {
            "open_count": len(positions),
            "positions": positions,
            "total_unrealized_pnl": round(total_pnl, 1),
        }


# Singleton
trade_manager = TradeManager()
