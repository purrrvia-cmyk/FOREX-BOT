"""WebSocket olayları: canlı veri akışı"""

import logging
from flask_socketio import SocketIO, emit

logger = logging.getLogger("BOT.WS")


def register_events(sio: SocketIO):

    @sio.on("connect")
    def on_connect():
        logger.info("🔌 WebSocket bağlandı")
        emit("connected", {"msg": "FOREX-BOT v2.0 bağlandı"})

    @sio.on("disconnect")
    def on_disconnect():
        logger.info("🔌 WebSocket koptu")

    @sio.on("request_scan")
    def on_request_scan(data):
        key = data.get("instrument")
        if not key:
            return
        from trading.signal_generator import SignalGenerator
        sg = SignalGenerator()
        result = sg.scan_instrument(key)
        emit("scan_result", result)

    @sio.on("request_price")
    def on_request_price(data):
        key = data.get("instrument")
        if not key:
            return
        from core.data_feed import feed
        p = feed.price(key)
        emit("price_update", {"instrument": key, "price": p})

    @sio.on("request_status")
    def on_request_status():
        from trading import CapitalManager
        from core.sessions import detect_kill_zone, detect_silver_bullet
        from database import db
        cm = CapitalManager()
        emit("status_update", {
            "capital": cm.status(),
            "kill_zone": detect_kill_zone(),
            "silver_bullet": detect_silver_bullet(),
            "stats": db.get_trade_stats(),
        })
