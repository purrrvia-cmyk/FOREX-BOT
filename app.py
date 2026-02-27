# =====================================================
# FOREX ICT Trading Bot — Web Dashboard (Flask)
# =====================================================
# Flask + SocketIO web uygulaması
# Gerçek zamanlı sinyal takibi, trade yönetimi,
# haber akışı ve performans görünümü.
# =====================================================

import logging
import threading
import time
import json
from datetime import datetime

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO

from config import FOREX_INSTRUMENTS, WEB_CONFIG
from signal_generator import signal_generator
from trade_manager import trade_manager
from news_fetcher import news_fetcher
from database import db
from ict_engine import ict_engine

# ═══ LOGGING ═══
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("FOREX-BOT")

# ═══ FLASK APP ═══
app = Flask(__name__)
app.config["SECRET_KEY"] = "forex-ict-bot-2024"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


# ════════════════════════════════════════
# BACKGROUND WORKERS
# ════════════════════════════════════════

scanner_running = False
scanner_interval = 120  # saniye (2 dakika)
trade_check_interval = 30  # saniye


def scanner_worker():
    """Arka planda tüm pariteleri tarar"""
    global scanner_running
    while scanner_running:
        try:
            results = signal_generator.scan_all("1h")
            active = [r for r in results if r.get("signal") not in ("WAIT", "ERROR")]
            socketio.emit("scan_update", {
                "results": _serialize(results),
                "active_count": len(active),
                "timestamp": datetime.now().isoformat(),
            })
            logger.info(f"Tarama tamamlandı: {len(active)}/{len(results)} aktif sinyal")
        except Exception as e:
            logger.error(f"Scanner hatası: {e}")

        time.sleep(scanner_interval)


def trade_checker_worker():
    """Açık trade'leri düzenli kontrol eder"""
    global scanner_running
    while scanner_running:
        try:
            updates = trade_manager.check_all_trades()
            if updates:
                portfolio = trade_manager.get_portfolio_summary()
                socketio.emit("trade_update", {
                    "updates": updates,
                    "portfolio": portfolio,
                })
        except Exception as e:
            logger.error(f"Trade checker hatası: {e}")

        time.sleep(trade_check_interval)


def _serialize(obj):
    """JSON serileştirme yardımcısı"""
    if isinstance(obj, list):
        return [_serialize(x) for x in obj]
    if isinstance(obj, dict):
        safe = {}
        for k, v in obj.items():
            try:
                json.dumps(v)
                safe[k] = v
            except (TypeError, ValueError):
                safe[k] = str(v)
        return safe
    return obj


# ════════════════════════════════════════
# WEB ROUTES
# ════════════════════════════════════════

@app.route("/")
def index():
    """Ana dashboard"""
    return render_template("index.html",
                           instruments=FOREX_INSTRUMENTS,
                           now=datetime.now().strftime("%d.%m.%Y %H:%M"))


@app.route("/api/dashboard")
def api_dashboard():
    """Dashboard özet verisi"""
    try:
        data = signal_generator.get_dashboard_data()
        return jsonify({"ok": True, "data": _serialize(data)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """Manuel tarama başlat"""
    tf = request.json.get("timeframe", "1h") if request.is_json else "1h"
    try:
        results = signal_generator.scan_all(tf)
        return jsonify({"ok": True, "results": _serialize(results),
                        "count": len(results)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/analyze/<instrument>")
def api_analyze(instrument):
    """Tek parite detaylı analiz"""
    tf = request.args.get("tf", "1h")
    try:
        data = signal_generator.get_pair_detail(instrument)
        return jsonify({"ok": True, "data": _serialize(data)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/signal/<instrument>", methods=["POST"])
def api_signal(instrument):
    """Tek parite sinyal üret"""
    tf = request.json.get("timeframe", "1h") if request.is_json else "1h"
    try:
        sig = signal_generator.generate_signal(instrument, tf)
        return jsonify({"ok": True, "signal": _serialize(sig)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/trades")
def api_trades():
    """Trade listesi"""
    status = request.args.get("status")
    instrument = request.args.get("instrument")
    try:
        trades = db.get_trades(instrument=instrument, status=status, limit=50)
        stats = db.get_trade_stats(30)
        return jsonify({"ok": True, "trades": trades, "stats": stats})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/trades/close/<int:trade_id>", methods=["POST"])
def api_close_trade(trade_id):
    """Trade elle kapat"""
    reason = request.json.get("reason", "MANUAL") if request.is_json else "MANUAL"
    try:
        result = trade_manager.force_close(trade_id, reason)
        if result:
            return jsonify({"ok": True, "result": result})
        return jsonify({"ok": False, "error": "Trade bulunamadı"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/portfolio")
def api_portfolio():
    """Portföy durumu"""
    try:
        portfolio = trade_manager.get_portfolio_summary()
        return jsonify({"ok": True, "portfolio": portfolio})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/signals")
def api_signals():
    """Sinyal geçmişi"""
    instrument = request.args.get("instrument")
    signal_filter = request.args.get("signal")
    try:
        signals = db.get_signals(instrument=instrument, signal_filter=signal_filter, limit=50)
        return jsonify({"ok": True, "signals": signals})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/news")
def api_news():
    """Haberler"""
    instrument = request.args.get("instrument")
    try:
        if instrument:
            data = news_fetcher.get_news_for_pair(instrument)
        else:
            data = {"news": news_fetcher.get_recent_news(30)}
        events = news_fetcher.get_upcoming_events()
        return jsonify({"ok": True, "data": _serialize(data), "events": _serialize(events[:15])})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/prices")
def api_prices():
    """Tüm fiyatlar"""
    try:
        prices = {}
        for key in FOREX_INSTRUMENTS:
            p = ict_engine.get_price(key)
            if p:
                prices[key] = p
        return jsonify({"ok": True, "prices": prices})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/performance")
def api_performance():
    """Performans istatistikleri"""
    days = int(request.args.get("days", 30))
    try:
        trade_stats = db.get_trade_stats(days)
        daily_perf = db.get_daily_performance(days)
        signal_stats = db.get_signal_stats(days)
        return jsonify({
            "ok": True,
            "trade_stats": trade_stats,
            "daily_performance": daily_perf,
            "signal_stats": signal_stats,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/watchlist", methods=["GET", "POST", "DELETE"])
def api_watchlist():
    """Watchlist yönetimi"""
    try:
        if request.method == "POST":
            data = request.json
            wl_id = db.add_to_watchlist(
                data["instrument"], data.get("direction"),
                data.get("note", ""), data.get("target_price"))
            return jsonify({"ok": True, "id": wl_id})
        elif request.method == "DELETE":
            wl_id = request.json.get("id")
            db.remove_from_watchlist(wl_id)
            return jsonify({"ok": True})
        else:
            items = db.get_watchlist()
            return jsonify({"ok": True, "watchlist": items})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/scanner/toggle", methods=["POST"])
def api_toggle_scanner():
    """Otomatik tarayıcıyı aç/kapa"""
    global scanner_running
    action = request.json.get("action", "toggle") if request.is_json else "toggle"

    if action == "start" or (action == "toggle" and not scanner_running):
        if not scanner_running:
            scanner_running = True
            threading.Thread(target=scanner_worker, daemon=True).start()
            threading.Thread(target=trade_checker_worker, daemon=True).start()
            logger.info("🚀 Otomatik tarayıcı BAŞLATILDI")
        return jsonify({"ok": True, "running": True})
    else:
        scanner_running = False
        logger.info("⏹️ Otomatik tarayıcı DURDURULDU")
        return jsonify({"ok": True, "running": False})


@app.route("/api/scanner/status")
def api_scanner_status():
    """Tarayıcı durumu"""
    return jsonify({"ok": True, "running": scanner_running})


# ════════════════════════════════════════
# SOCKETIO EVENTS
# ════════════════════════════════════════

@socketio.on("connect")
def handle_connect():
    logger.info("WebSocket bağlantısı kuruldu")
    socketio.emit("status", {"connected": True, "scanner_running": scanner_running})


@socketio.on("request_scan")
def handle_scan():
    """Manuel tarama talebi (WebSocket)"""
    try:
        results = signal_generator.scan_all("1h")
        active = [r for r in results if r.get("signal") not in ("WAIT", "ERROR")]
        socketio.emit("scan_update", {
            "results": _serialize(results),
            "active_count": len(active),
        })
    except Exception as e:
        socketio.emit("error", {"msg": str(e)})


# ════════════════════════════════════════
# MAIN
# ════════════════════════════════════════

if __name__ == "__main__":
    port = WEB_CONFIG.get("port", 5001)
    debug = WEB_CONFIG.get("debug", False)

    logger.info(f"""
╔══════════════════════════════════════════════════╗
║      FOREX ICT Trading Bot — Dashboard           ║
║      %100 ICT Uyumlu | 16 Konsept                ║
║      http://localhost:{port}                       ║
╚══════════════════════════════════════════════════╝
    """)

    socketio.run(app, host="0.0.0.0", port=port, debug=debug,
                 allow_unsafe_werkzeug=True)
