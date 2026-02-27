"""FOREX-BOT v2.0 — Ana Giriş Noktası"""

import logging
import time
import threading
from datetime import datetime

# ── Logging ─────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("forex_bot.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger("BOT")

# ── Imports ─────────────────────────────────
from database import init_db, db
from core.data_feed import feed
from trading.capital_manager import CapitalManager
from trading.trade_manager import TradeManager
from trading.signal_generator import SignalGenerator
from trading.risk_manager import RiskManager
from intelligence.news_fetcher import NewsFetcher
from intelligence.economic_calendar import EconomicCalendar
from intelligence.learning_engine import LearningEngine
from web.app import create_app, socketio
from config.instruments import INSTRUMENTS


def main():
    logger.info("=" * 50)
    logger.info("  FOREX-BOT v2.0 — ICT/SMC Trading System")
    logger.info("=" * 50)

    # DB init
    init_db()

    # Components
    capital = CapitalManager()
    news = NewsFetcher()
    calendar = EconomicCalendar()
    learning = LearningEngine()
    risk = RiskManager()
    signals = SignalGenerator(news_fetcher=news, learning_engine=learning)
    trades = TradeManager(capital)

    logger.info(f"💰 Bakiye: ${capital.balance:.2f} | Kaldıraç: {capital.buying_power:.0f}x")
    logger.info(f"📊 {len(INSTRUMENTS)} enstrüman aktif")

    # Flask app
    app, sio = create_app()

    # ── Background Scanner ──────────────────
    def scan_loop():
        """Ana tarama döngüsü — 2 dk ana, 30 sn giriş"""
        cycle = 0
        while True:
            try:
                cycle += 1
                logger.info(f"─── Döngü #{cycle} ───")

                # Haberleri güncelle (her 15 dk)
                if cycle % 8 == 1:
                    news.fetch()
                    calendar.fetch()

                # Öğrenme periyodik review (her 50 döngü)
                if cycle % 50 == 0:
                    learning.periodic_review()

                # Açık işlem kontrolü (her döngü)
                closed = trades.check_trades()
                for c in closed:
                    learning.analyze_trade(c["trade"])
                    sio.emit("trade_update", c, namespace="/")

                # Ana tarama (her 2 dk)
                results = signals.scan_all()
                for r in results:
                    sig = r.get("final_signal", "WAIT")
                    if sig != "WAIT":
                        key = r["instrument"]

                        # Risk kontrolü
                        direction = "LONG" if "LONG" in sig else "SHORT"
                        risk_check = risk.check_all(key, direction)
                        if not risk_check["allowed"]:
                            logger.info(f"⚠️ {key}: {risk_check['reason']}")
                            continue

                        # Takvim kontrolü
                        cal_check = calendar.is_safe_to_trade(key)
                        if not cal_check["safe"]:
                            logger.info(f"📅 {key}: {cal_check['reason']}")
                            continue

                        # Sinyal kaydet
                        db.save_signal({
                            "instrument": key,
                            "signal": sig,
                            "score": r.get("final_score", 0),
                            "reasons": str(r.get("entry_data", {}).get(
                                "reasons_bull" if "LONG" in sig else "reasons_bear", []))[:500],
                        })

                        # İşlem aç
                        entry_data = r.get("entry_data", r)
                        entry_data["instrument"] = key
                        entry_data["signal"] = sig
                        trade = trades.open_trade(entry_data)
                        if trade:
                            sio.emit("new_signal", r, namespace="/")

                # Status broadcast
                sio.emit("status_update", {
                    "capital": capital.status(),
                    "kill_zone": r.get("kill_zone", {}) if results else {},
                    "stats": db.get_trade_stats(),
                }, namespace="/")

                time.sleep(120)  # 2 dakika

            except Exception as e:
                logger.error(f"Döngü hatası: {e}", exc_info=True)
                time.sleep(30)

    # Start scanner thread
    scanner = threading.Thread(target=scan_loop, daemon=True)
    scanner.start()

    # Start Flask
    logger.info("🌐 Web arayüzü: http://localhost:5000")
    sio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    main()
