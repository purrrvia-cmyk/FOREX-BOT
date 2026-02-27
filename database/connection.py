"""SQLite bağlantı yönetimi (WAL mode, thread-safe)"""

import sqlite3
import logging
from database.models import TABLES

logger = logging.getLogger("BOT.DB")
DB_PATH = "forex_bot.db"


def get_db(path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(path: str = DB_PATH):
    """Tüm tabloları oluştur"""
    conn = get_db(path)
    for name, ddl in TABLES.items():
        try:
            conn.execute(ddl)
        except Exception as e:
            logger.error(f"Tablo oluşturma hatası ({name}): {e}")
    conn.commit()
    conn.close()
    logger.info("Veritabanı tabloları hazır")
