"""Flask uygulama fabrikası"""

import os
from flask import Flask
from flask_socketio import SocketIO

socketio = SocketIO()


def create_app():
    app = Flask(__name__,
                template_folder=os.path.join(os.path.dirname(__file__), "templates"),
                static_folder=os.path.join(os.path.dirname(__file__), "static"))
    app.config["SECRET_KEY"] = "forex-bot-2024-secret"

    from database import init_db
    init_db()

    from web.routes import bp
    app.register_blueprint(bp)

    from web.websocket import register_events
    socketio.init_app(app, cors_allowed_origins="*", async_mode="threading")
    register_events(socketio)

    return app, socketio
