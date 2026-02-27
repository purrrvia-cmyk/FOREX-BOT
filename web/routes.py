"""Flask REST API rotaları"""

from flask import Blueprint, render_template, jsonify, request
from config.instruments import INSTRUMENTS
from config.kill_zones import KILL_ZONES, SILVER_BULLETS
from config.capital import CAPITAL
from database import db
from core.data_feed import feed
from core.sessions import detect_kill_zone, detect_silver_bullet

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    return render_template("index.html")


@bp.route("/manifest.json")
def manifest():
    return bp.send_static_file("manifest.json")


@bp.route("/sw.js")
def service_worker():
    from flask import send_from_directory, current_app
    return send_from_directory(current_app.static_folder, "sw.js",
                               mimetype="application/javascript")


# ── API ────────────────────────────────────────
@bp.route("/api/status")
def api_status():
    from trading import CapitalManager
    cm = CapitalManager()
    kz = detect_kill_zone()
    sb = detect_silver_bullet()
    stats = db.get_trade_stats()
    return jsonify({
        "capital": cm.status(),
        "kill_zone": kz,
        "silver_bullet": sb,
        "trade_stats": stats,
    })


@bp.route("/api/instruments")
def api_instruments():
    result = []
    for key, inst in INSTRUMENTS.items():
        p = feed.price(key)
        result.append({
            "key": key, "name": inst["name"], "cat": inst["cat"],
            "icon": inst["icon"], "price": p,
        })
    return jsonify(result)


@bp.route("/api/scan/<key>")
def api_scan(key):
    if key not in INSTRUMENTS:
        return jsonify({"error": "Geçersiz enstrüman"}), 404
    from trading.signal_generator import SignalGenerator
    sg = SignalGenerator()
    result = sg.scan_instrument(key)
    return jsonify(result)


@bp.route("/api/scan_all")
def api_scan_all():
    from trading.signal_generator import SignalGenerator
    sg = SignalGenerator()
    results = sg.scan_all()
    return jsonify(results)


@bp.route("/api/trades")
def api_trades():
    status = request.args.get("status", "all")
    limit = int(request.args.get("limit", 50))
    if status == "open":
        trades = db.get_open_trades()
    else:
        trades = db.get_trades(limit=limit)
    return jsonify(trades)


@bp.route("/api/signals")
def api_signals():
    limit = int(request.args.get("limit", 50))
    return jsonify(db.get_signals(limit=limit))


@bp.route("/api/balance_history")
def api_balance_history():
    limit = int(request.args.get("limit", 100))
    return jsonify(db.get_balance_history(limit=limit))


@bp.route("/api/daily_performance")
def api_daily_perf():
    limit = int(request.args.get("limit", 30))
    return jsonify(db.get_daily_performance(limit=limit))


@bp.route("/api/news")
def api_news():
    return jsonify(db.get_signals(limit=20))


@bp.route("/api/learning")
def api_learning():
    from intelligence.learning_engine import LearningEngine
    le = LearningEngine()
    return jsonify(le.get_performance_summary())


@bp.route("/api/watchlist", methods=["GET"])
def api_watchlist_get():
    return jsonify(db.get_watchlist())


@bp.route("/api/watchlist", methods=["POST"])
def api_watchlist_add():
    data = request.get_json()
    key = data.get("instrument")
    if key and key in INSTRUMENTS:
        db.add_watchlist(key)
        return jsonify({"ok": True})
    return jsonify({"error": "Geçersiz"}), 400


@bp.route("/api/watchlist/<key>", methods=["DELETE"])
def api_watchlist_del(key):
    db.remove_watchlist(key)
    return jsonify({"ok": True})
