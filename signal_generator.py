# =====================================================
# FOREX ICT Trading Bot — Sinyal Üretici
# =====================================================
# Multi-TF analiz + haber entegrasyonu + quality gate
# ile son sinyal kararı verir.
# =====================================================

import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional

from config import FOREX_INSTRUMENTS, ICT_PARAMS
from ict_engine import ict_engine
from news_fetcher import news_fetcher
from database import db
from trade_manager import trade_manager

logger = logging.getLogger("FOREX-BOT.SIGNAL")


class SignalGenerator:
    """
    ICT Sinyal Üretici:
    1. HTF (4h/1d) yapı + bias analizi
    2. LTF (1h/15m) giriş sinyali
    3. Haber filtresi (yüksek etkili haberde işlem yok)
    4. Kill Zone kontrolü
    5. Quality Gate (minimum confluence)
    6. Sinyal kayıt + yorum üretimi
    """

    def __init__(self):
        self.min_confluence = ICT_PARAMS.get("min_confluence_normal", 3)
        self.scan_interval = 60  # saniye
        self._last_scan = {}
        self._scan_lock = threading.Lock()

    def generate_signal(self, instrument_key: str, entry_tf: str = "1h") -> Dict:
        """
        Tek enstrüman için tam sinyal üret.

        Adımlar:
        1. ICT confluence analizi (entry TF)
        2. HTF daily bias teyidi
        3. Haber kontrolü
        4. Kill Zone kontrolü
        5. Quality Gate
        6. Yorum üretimi
        7. DB kayıt
        """
        logger.info(f"🔍 Sinyal üretiliyor: {instrument_key} ({entry_tf})")

        # 1. ICT Analiz
        analysis = ict_engine.calculate_confluence(instrument_key, entry_tf)
        if "error" in analysis:
            return {"instrument": instrument_key, "signal": "ERROR",
                    "reason": analysis["error"]}

        signal = analysis["signal"]

        # 2. HTF Bias teyidi (zaten calculate_confluence içinde yapılıyor)
        daily_bias = analysis.get("daily_bias", {})

        # 3. Haber kontrolü
        news_data = news_fetcher.get_news_for_pair(instrument_key)
        analysis["news_sentiment"] = news_data.get("sentiment", "NEUTRAL")
        analysis["news_impact"] = "HIGH" if news_data.get("has_high_impact") else "NORMAL"

        # Yüksek etkili haberde sinyali düşür
        if news_data.get("has_high_impact") and signal != "WAIT":
            original_signal = signal
            if signal in ("STRONG_LONG", "STRONG_SHORT"):
                signal = signal.replace("STRONG_", "")  # STRONG → normal
                analysis["signal"] = signal
                logger.info(f"⚠️ {instrument_key}: Yüksek etkili haber → {original_signal} → {signal}")
            else:
                signal = "WAIT"
                analysis["signal"] = signal
                logger.info(f"⚠️ {instrument_key}: Yüksek etkili haber → sinyal WAIT'e düşürüldü")

        # 4. Kill Zone kontrolü — KZ dışında STRONG sinyal olmaz
        kz = analysis.get("kill_zones", {})
        if not kz.get("is_kill_zone") and signal in ("STRONG_LONG", "STRONG_SHORT"):
            signal = signal.replace("STRONG_", "")
            analysis["signal"] = signal
            logger.info(f"⏰ {instrument_key}: Kill Zone dışı → {signal}")

        # 5. Quality Gate: Minimum confluence kontrolü
        conf_count = max(analysis.get("conf_bull", 0), analysis.get("conf_bear", 0))
        if signal != "WAIT" and conf_count < self.min_confluence:
            analysis["signal"] = "WAIT"
            signal = "WAIT"
            logger.info(f"🚫 {instrument_key}: Confluence yetersiz ({conf_count} < {self.min_confluence})")

        # 6. Yorum üret
        commentary = news_fetcher.get_market_commentary(instrument_key, analysis)
        analysis["commentary"] = commentary

        # 7. DB'ye kaydet
        signal_id = db.save_signal(analysis)
        analysis["signal_id"] = signal_id

        # 8. İşlem sinyali ise trade aç
        if signal != "WAIT":
            trade_id = trade_manager.open_new_trade(analysis, signal_id)
            analysis["trade_id"] = trade_id

        return analysis

    def scan_all(self, entry_tf: str = "1h") -> List[Dict]:
        """
        Tüm enstrümanları tara, sinyal üret.
        Returns: sinyal listesi
        """
        if not self._scan_lock.acquire(blocking=False):
            logger.info("⏳ Tarama zaten devam ediyor, atlanıyor")
            return []
        try:
            return self._scan_all_locked(entry_tf)
        finally:
            self._scan_lock.release()

    def _scan_all_locked(self, entry_tf: str) -> List[Dict]:
        logger.info(f"═══ FOREX TARAMA BAŞLIYOR ({entry_tf}) ═══")
        results = []

        for key in FOREX_INSTRUMENTS:
            try:
                sig = self.generate_signal(key, entry_tf)
                results.append(sig)

                if sig.get("signal") != "WAIT":
                    logger.info(
                        f"📢 {key}: {sig['signal']} (skor: {sig.get('net_score', 0)}, "
                        f"confluence: {max(sig.get('conf_bull', 0), sig.get('conf_bear', 0))})"
                    )
            except Exception as e:
                logger.error(f"Tarama hatası ({key}): {e}")
                results.append({"instrument": key, "signal": "ERROR", "reason": str(e)})

        # Trade kontrolü (ayrıca)
        trade_results = trade_manager.check_all_trades()
        if trade_results:
            for tr in trade_results:
                logger.info(f"Trade güncelleme: {tr}")

        active_signals = [r for r in results if r.get("signal") not in ("WAIT", "ERROR")]
        logger.info(
            f"═══ TARAMA TAMAM: {len(results)} parite, "
            f"{len(active_signals)} aktif sinyal ═══"
        )

        return results

    def get_dashboard_data(self) -> Dict:
        """
        Dashboard için özet veri.
        """
        # Son sinyaller
        recent_signals = db.get_signals(limit=20)

        # Açık trade'ler
        portfolio = trade_manager.get_portfolio_summary()

        # Performans
        trade_stats = db.get_trade_stats(30)
        signal_stats = db.get_signal_stats(30)

        # Haber özeti
        try:
            all_sentiments = news_fetcher.get_all_pair_sentiments()
        except Exception:
            all_sentiments = {}

        # Kill Zone
        kill_zone = ict_engine.detect_kill_zones()
        silver_bullet = ict_engine.detect_silver_bullet()

        # Güncel fiyatlar
        prices = {}
        for key in FOREX_INSTRUMENTS:
            try:
                p = ict_engine.get_price(key)
                if p:
                    prices[key] = p
            except Exception:
                pass

        return {
            "recent_signals": recent_signals[:15],
            "portfolio": portfolio,
            "trade_stats": trade_stats,
            "signal_stats": signal_stats,
            "news_sentiments": all_sentiments,
            "kill_zone": kill_zone,
            "silver_bullet": silver_bullet,
            "prices": prices,
            "instruments": {k: v["name"] for k, v in FOREX_INSTRUMENTS.items()},
            "timestamp": datetime.now().isoformat(),
        }

    def get_pair_detail(self, instrument_key: str) -> Dict:
        """Tek parite detaylı analiz"""
        analysis = ict_engine.calculate_confluence(instrument_key, "1h")
        news_data = news_fetcher.get_news_for_pair(instrument_key)
        commentary = news_fetcher.get_market_commentary(instrument_key, analysis)
        signals_history = db.get_signals(instrument=instrument_key, limit=20)
        trades_history = db.get_trades(instrument=instrument_key, limit=20)

        return {
            "analysis": analysis,
            "news": news_data,
            "commentary": commentary,
            "signal_history": signals_history,
            "trade_history": trades_history,
        }


# Singleton
signal_generator = SignalGenerator()
