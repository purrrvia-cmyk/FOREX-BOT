# =====================================================
# FOREX ICT Trading Bot — Veritabanı (SQLite)
# =====================================================
# Sinyal geçmişi, trade kayıtları, performans istatistikleri
# =====================================================

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger("FOREX-BOT.DB")

DB_PATH = "forex_bot.db"


class Database:
    """SQLite veritabanı yönetimi"""

    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_tables()

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_tables(self):
        conn = self._conn()
        try:
            # — SİNYALLER —
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    instrument TEXT NOT NULL,
                    timeframe TEXT DEFAULT '1h',
                    signal TEXT NOT NULL,
                    net_score INTEGER DEFAULT 0,
                    bull_score INTEGER DEFAULT 0,
                    bear_score INTEGER DEFAULT 0,
                    conf_bull INTEGER DEFAULT 0,
                    conf_bear INTEGER DEFAULT 0,
                    price REAL NOT NULL,
                    sl REAL,
                    tp1 REAL,
                    tp2 REAL,
                    rr1 REAL,
                    rr2 REAL,
                    reasons_bull TEXT,
                    reasons_bear TEXT,
                    daily_bias TEXT,
                    kill_zone TEXT,
                    news_sentiment TEXT,
                    news_impact TEXT,
                    commentary TEXT,
                    full_analysis TEXT,
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                )
            """)

            # — TRADE (İŞLEM) KAYITLARI —
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id INTEGER REFERENCES signals(id),
                    instrument TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    current_price REAL,
                    sl REAL NOT NULL,
                    tp1 REAL,
                    tp2 REAL,
                    initial_sl REAL,
                    be_triggered INTEGER DEFAULT 0,
                    trailing_active INTEGER DEFAULT 0,
                    trailing_sl REAL,
                    status TEXT DEFAULT 'OPEN',
                    close_price REAL,
                    close_reason TEXT,
                    pnl_pips REAL DEFAULT 0,
                    pnl_pct REAL DEFAULT 0,
                    opened_at TEXT DEFAULT (datetime('now', 'localtime')),
                    closed_at TEXT,
                    notes TEXT
                )
            """)

            # — PERFORMANS GÜNLÜKLERİ —
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT UNIQUE NOT NULL,
                    total_signals INTEGER DEFAULT 0,
                    total_trades INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0,
                    total_pnl_pips REAL DEFAULT 0,
                    win_rate REAL DEFAULT 0,
                    best_trade_pips REAL DEFAULT 0,
                    worst_trade_pips REAL DEFAULT 0,
                    avg_rr REAL DEFAULT 0,
                    notes TEXT
                )
            """)

            # — WATCHLIST —
            conn.execute("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    instrument TEXT NOT NULL,
                    direction TEXT,
                    note TEXT,
                    target_price REAL,
                    alert_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                )
            """)

            conn.commit()
            logger.info("Veritabanı tabloları hazır")
        except Exception as e:
            logger.error(f"DB init hatası: {e}")
        finally:
            conn.close()

    # ════════════════════════════════════
    # SİNYAL İŞLEMLERİ
    # ════════════════════════════════════

    def save_signal(self, data: Dict) -> int:
        """Sinyal kaydet, ID döndür"""
        conn = self._conn()
        try:
            sl_tp = data.get("sl_tp") or {}
            cur = conn.execute("""
                INSERT INTO signals
                (instrument, timeframe, signal, net_score, bull_score, bear_score,
                 conf_bull, conf_bear, price, sl, tp1, tp2, rr1, rr2,
                 reasons_bull, reasons_bear, daily_bias, kill_zone,
                 news_sentiment, news_impact, commentary, full_analysis)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                data.get("instrument"), data.get("timeframe", "1h"),
                data.get("signal"), data.get("net_score", 0),
                data.get("bull_score", 0), data.get("bear_score", 0),
                data.get("conf_bull", 0), data.get("conf_bear", 0),
                data.get("price", 0),
                sl_tp.get("sl"), sl_tp.get("tp1"), sl_tp.get("tp2"),
                sl_tp.get("rr1"), sl_tp.get("rr2"),
                json.dumps(data.get("reasons_bull", []), ensure_ascii=False),
                json.dumps(data.get("reasons_bear", []), ensure_ascii=False),
                data.get("daily_bias", {}).get("bias", ""),
                data.get("kill_zones", {}).get("active_zone", ""),
                data.get("news_sentiment", ""),
                data.get("news_impact", ""),
                data.get("commentary", ""),
                json.dumps(data, ensure_ascii=False, default=str),
            ))
            conn.commit()
            return cur.lastrowid
        except Exception as e:
            logger.error(f"Signal save hatası: {e}")
            return 0
        finally:
            conn.close()

    def get_signals(self, instrument: str = None, limit: int = 50,
                    signal_filter: str = None) -> List[Dict]:
        """Sinyalleri getir (filtreli)"""
        conn = self._conn()
        try:
            query = "SELECT * FROM signals WHERE 1=1"
            params = []
            if instrument:
                query += " AND instrument = ?"
                params.append(instrument)
            if signal_filter and signal_filter != "ALL":
                query += " AND signal = ?"
                params.append(signal_filter)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_signal_stats(self, days: int = 30) -> Dict:
        """Son X gün sinyal istatistikleri"""
        conn = self._conn()
        try:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            rows = conn.execute("""
                SELECT signal, COUNT(*) as cnt
                FROM signals WHERE created_at >= ? GROUP BY signal
            """, (cutoff,)).fetchall()
            stats = {r["signal"]: r["cnt"] for r in rows}
            total = sum(stats.values())
            return {"total": total, "breakdown": stats, "period_days": days}
        finally:
            conn.close()

    # ════════════════════════════════════
    # TRADE İŞLEMLERİ
    # ════════════════════════════════════

    def open_trade(self, signal_id: int, instrument: str, direction: str,
                   entry_price: float, sl: float, tp1: float, tp2: float = None) -> int:
        """Yeni trade aç"""
        conn = self._conn()
        try:
            cur = conn.execute("""
                INSERT INTO trades
                (signal_id, instrument, direction, entry_price, current_price,
                 sl, tp1, tp2, initial_sl, status)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (signal_id, instrument, direction, entry_price, entry_price,
                  sl, tp1, tp2, sl, "OPEN"))
            conn.commit()
            return cur.lastrowid
        except Exception as e:
            logger.error(f"Trade open hatası: {e}")
            return 0
        finally:
            conn.close()

    def update_trade(self, trade_id: int, **kwargs):
        """Trade güncelle (current_price, sl, trailing_sl, be_triggered vb.)"""
        conn = self._conn()
        try:
            sets = []
            vals = []
            for k, v in kwargs.items():
                sets.append(f"{k} = ?")
                vals.append(v)
            vals.append(trade_id)
            conn.execute(f"UPDATE trades SET {', '.join(sets)} WHERE id = ?", vals)
            conn.commit()
        except Exception as e:
            logger.error(f"Trade update hatası: {e}")
        finally:
            conn.close()

    def close_trade(self, trade_id: int, close_price: float, close_reason: str,
                    pnl_pips: float, pnl_pct: float):
        """Trade kapat"""
        conn = self._conn()
        try:
            conn.execute("""
                UPDATE trades SET
                    status = 'CLOSED', close_price = ?, close_reason = ?,
                    pnl_pips = ?, pnl_pct = ?, closed_at = datetime('now', 'localtime')
                WHERE id = ?
            """, (close_price, close_reason, pnl_pips, pnl_pct, trade_id))
            conn.commit()
            self._update_daily_perf(pnl_pips)
        except Exception as e:
            logger.error(f"Trade close hatası: {e}")
        finally:
            conn.close()

    def get_open_trades(self) -> List[Dict]:
        """Açık trade'leri getir"""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status = 'OPEN' ORDER BY opened_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_trades(self, instrument: str = None, status: str = None,
                   limit: int = 50) -> List[Dict]:
        """Trade'leri getir"""
        conn = self._conn()
        try:
            query = "SELECT * FROM trades WHERE 1=1"
            params = []
            if instrument:
                query += " AND instrument = ?"
                params.append(instrument)
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY opened_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_trade_stats(self, days: int = 30) -> Dict:
        """Trade performans istatistikleri"""
        conn = self._conn()
        try:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            rows = conn.execute("""
                SELECT * FROM trades
                WHERE status = 'CLOSED' AND closed_at >= ?
            """, (cutoff,)).fetchall()

            if not rows:
                return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0,
                        "total_pnl": 0, "avg_pnl": 0, "best": 0, "worst": 0, "avg_rr": 0}

            trades = [dict(r) for r in rows]
            wins = [t for t in trades if t["pnl_pips"] > 0]
            losses = [t for t in trades if t["pnl_pips"] <= 0]
            total_pnl = sum(t["pnl_pips"] for t in trades)
            best = max(t["pnl_pips"] for t in trades) if trades else 0
            worst = min(t["pnl_pips"] for t in trades) if trades else 0

            return {
                "total": len(trades),
                "wins": len(wins),
                "losses": len(losses),
                "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
                "total_pnl": round(total_pnl, 2),
                "avg_pnl": round(total_pnl / len(trades), 2) if trades else 0,
                "best": round(best, 2),
                "worst": round(worst, 2),
                "period_days": days,
            }
        finally:
            conn.close()

    # ════════════════════════════════════
    # GÜNLÜK PERFORMANS
    # ════════════════════════════════════

    def _update_daily_perf(self, pnl_pips: float):
        """Günlük performansı güncelle"""
        conn = self._conn()
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            existing = conn.execute(
                "SELECT * FROM daily_performance WHERE date = ?", (today,)
            ).fetchone()

            if existing:
                wins = existing["wins"] + (1 if pnl_pips > 0 else 0)
                losses = existing["losses"] + (1 if pnl_pips <= 0 else 0)
                total = wins + losses
                total_pnl = existing["total_pnl_pips"] + pnl_pips
                best = max(existing["best_trade_pips"], pnl_pips)
                worst = min(existing["worst_trade_pips"], pnl_pips)
                wr = round(wins / total * 100, 1) if total > 0 else 0

                conn.execute("""
                    UPDATE daily_performance SET
                        total_trades = ?, wins = ?, losses = ?,
                        total_pnl_pips = ?, win_rate = ?,
                        best_trade_pips = ?, worst_trade_pips = ?
                    WHERE date = ?
                """, (total, wins, losses, total_pnl, wr, best, worst, today))
            else:
                is_win = 1 if pnl_pips > 0 else 0
                conn.execute("""
                    INSERT INTO daily_performance
                    (date, total_trades, wins, losses, total_pnl_pips, win_rate,
                     best_trade_pips, worst_trade_pips)
                    VALUES (?, 1, ?, ?, ?, ?, ?, ?)
                """, (today, is_win, 1 - is_win, pnl_pips,
                      100.0 if is_win else 0.0, max(pnl_pips, 0), min(pnl_pips, 0)))
            conn.commit()
        except Exception as e:
            logger.error(f"Daily perf update hatası: {e}")
        finally:
            conn.close()

    def get_daily_performance(self, days: int = 30) -> List[Dict]:
        """Son X gün performans"""
        conn = self._conn()
        try:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            rows = conn.execute("""
                SELECT * FROM daily_performance WHERE date >= ?
                ORDER BY date DESC
            """, (cutoff,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ════════════════════════════════════
    # WATCHLIST
    # ════════════════════════════════════

    def add_to_watchlist(self, instrument: str, direction: str = None,
                         note: str = "", target_price: float = None) -> int:
        conn = self._conn()
        try:
            cur = conn.execute("""
                INSERT INTO watchlist (instrument, direction, note, target_price)
                VALUES (?, ?, ?, ?)
            """, (instrument, direction, note, target_price))
            conn.commit()
            return cur.lastrowid
        except Exception as e:
            logger.error(f"Watchlist add hatası: {e}")
            return 0
        finally:
            conn.close()

    def get_watchlist(self) -> List[Dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM watchlist WHERE alert_active = 1 ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def remove_from_watchlist(self, wl_id: int):
        conn = self._conn()
        try:
            conn.execute("UPDATE watchlist SET alert_active = 0 WHERE id = ?", (wl_id,))
            conn.commit()
        finally:
            conn.close()


# Singleton
db = Database()
