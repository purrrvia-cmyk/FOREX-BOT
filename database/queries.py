"""Veritabanı CRUD operasyonları"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from database.connection import get_db

logger = logging.getLogger("BOT.DB")


class Queries:
    """Tüm DB okuma/yazma işlemleri"""

    # ── Sinyal ──────────────────────────────────
    def save_signal(self, data: Dict) -> int:
        sl_tp = data.get("sl_tp") or {}
        conn = get_db()
        try:
            cur = conn.execute("""
                INSERT INTO signals
                (instrument, timeframe, signal, net_score, conf_bull, conf_bear,
                 price, sl, tp1, tp2, rr1, rr2, reasons, daily_bias,
                 kill_zone, news_sentiment, news_impact, commentary)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                data.get("instrument"), data.get("timeframe", "1h"),
                data.get("signal"), data.get("net_score", 0),
                data.get("conf_bull", 0), data.get("conf_bear", 0),
                data.get("price", 0),
                sl_tp.get("sl"), sl_tp.get("tp1"), sl_tp.get("tp2"),
                sl_tp.get("rr1"), sl_tp.get("rr2"),
                json.dumps(data.get("reasons_bull", []) + data.get("reasons_bear", []),
                           ensure_ascii=False),
                data.get("daily_bias", {}).get("bias", ""),
                data.get("kill_zones", {}).get("active_zone", ""),
                data.get("news_sentiment", ""),
                data.get("news_impact", ""),
                data.get("commentary", ""),
            ))
            conn.commit()
            return cur.lastrowid
        except Exception as e:
            logger.error(f"Signal save: {e}")
            return 0
        finally:
            conn.close()

    def get_signals(self, instrument: str = None, signal_filter: str = None,
                    limit: int = 50) -> List[Dict]:
        conn = get_db()
        try:
            q = "SELECT * FROM signals WHERE 1=1"
            p = []
            if instrument:
                q += " AND instrument=?"; p.append(instrument)
            if signal_filter and signal_filter != "ALL":
                q += " AND signal=?"; p.append(signal_filter)
            q += " ORDER BY created_at DESC LIMIT ?"
            p.append(limit)
            return [dict(r) for r in conn.execute(q, p).fetchall()]
        finally:
            conn.close()

    # ── Trade ───────────────────────────────────
    def open_trade(self, **kw) -> int:
        conn = get_db()
        try:
            cur = conn.execute("""
                INSERT INTO trades
                (signal_id, instrument, direction, entry_price, current_price,
                 sl, tp1, tp2, initial_sl, lot_size, risk_usd, kill_zone, concepts_used, status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                kw.get("signal_id", 0), kw["instrument"], kw["direction"],
                kw["entry_price"], kw["entry_price"],
                kw["sl"], kw.get("tp1"), kw.get("tp2"), kw["sl"],
                kw.get("lot_size", 0), kw.get("risk_usd", 0),
                kw.get("kill_zone", ""), kw.get("concepts_used", ""),
                "OPEN",
            ))
            conn.commit()
            return cur.lastrowid
        except Exception as e:
            logger.error(f"Trade open: {e}")
            return 0
        finally:
            conn.close()

    def update_trade(self, trade_id: int, **kw):
        conn = get_db()
        try:
            sets = [f"{k}=?" for k in kw]
            vals = list(kw.values()) + [trade_id]
            conn.execute(f"UPDATE trades SET {','.join(sets)} WHERE id=?", vals)
            conn.commit()
        except Exception as e:
            logger.error(f"Trade update: {e}")
        finally:
            conn.close()

    def close_trade(self, trade_id: int, close_price: float, reason: str,
                    pnl_pips: float, pnl_usd: float, pnl_pct: float):
        conn = get_db()
        try:
            conn.execute("""
                UPDATE trades SET
                    status='CLOSED', close_price=?, close_reason=?,
                    pnl_pips=?, pnl_usd=?, pnl_pct=?,
                    closed_at=datetime('now','localtime')
                WHERE id=?
            """, (close_price, reason, pnl_pips, pnl_usd, pnl_pct, trade_id))
            conn.commit()
            self._update_daily_perf(pnl_usd)
        except Exception as e:
            logger.error(f"Trade close: {e}")
        finally:
            conn.close()

    def get_open_trades(self) -> List[Dict]:
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status='OPEN' ORDER BY opened_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_trades(self, instrument: str = None, status: str = None,
                   limit: int = 50) -> List[Dict]:
        conn = get_db()
        try:
            q = "SELECT * FROM trades WHERE 1=1"
            p = []
            if instrument:
                q += " AND instrument=?"; p.append(instrument)
            if status:
                q += " AND status=?"; p.append(status)
            q += " ORDER BY opened_at DESC LIMIT ?"
            p.append(limit)
            return [dict(r) for r in conn.execute(q, p).fetchall()]
        finally:
            conn.close()

    def get_trade_stats(self, days: int = 30) -> Dict:
        conn = get_db()
        try:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            rows = conn.execute(
                "SELECT * FROM trades WHERE status='CLOSED' AND closed_at>=?",
                (cutoff,),
            ).fetchall()
            if not rows:
                return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0,
                        "total_pnl": 0, "avg_pnl": 0, "best": 0, "worst": 0}
            trades = [dict(r) for r in rows]
            wins = [t for t in trades if t["pnl_usd"] > 0]
            losses = [t for t in trades if t["pnl_usd"] <= 0]
            total_pnl = sum(t["pnl_usd"] for t in trades)
            return {
                "total": len(trades),
                "wins": len(wins),
                "losses": len(losses),
                "win_rate": round(len(wins) / len(trades) * 100, 1),
                "total_pnl": round(total_pnl, 2),
                "avg_pnl": round(total_pnl / len(trades), 2),
                "best": round(max(t["pnl_usd"] for t in trades), 2),
                "worst": round(min(t["pnl_usd"] for t in trades), 2),
            }
        finally:
            conn.close()

    def get_signal_stats(self, days: int = 30) -> Dict:
        conn = get_db()
        try:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            rows = conn.execute(
                "SELECT signal, COUNT(*) as cnt FROM signals WHERE created_at>=? GROUP BY signal",
                (cutoff,),
            ).fetchall()
            stats = {r["signal"]: r["cnt"] for r in rows}
            return {"total": sum(stats.values()), "breakdown": stats}
        finally:
            conn.close()

    # ── Capital History ─────────────────────────
    def record_balance(self, balance: float, equity: float,
                       trade_id: int = None, event: str = ""):
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO capital_history (balance, equity, trade_id, event) VALUES (?,?,?,?)",
                (balance, equity, trade_id, event),
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Balance record: {e}")
        finally:
            conn.close()

    def get_balance_history(self, limit: int = 100, days: int = 30) -> List[Dict]:
        conn = get_db()
        try:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            rows = conn.execute(
                "SELECT * FROM capital_history WHERE timestamp>=? ORDER BY timestamp DESC LIMIT ?",
                (cutoff, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Learning ────────────────────────────────
    def save_learning_log(self, data: Dict):
        conn = get_db()
        try:
            conn.execute("""
                INSERT INTO learning_log
                (trade_id, instrument, direction, kill_zone, concepts,
                 tf_alignment, news_impact, result, pnl_usd, duration_min)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                data.get("trade_id"), data.get("instrument"),
                data.get("direction"), data.get("kill_zone"),
                data.get("concepts"), data.get("tf_alignment", 0),
                data.get("news_impact"), data.get("result"),
                data.get("pnl_usd", 0), data.get("duration_min", 0),
            ))
            conn.commit()
        except Exception as e:
            logger.error(f"Learning log: {e}")
        finally:
            conn.close()

    def get_learning_logs(self, limit: int = 200) -> List[Dict]:
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT * FROM learning_log ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_pattern_score(self, pattern_key: str) -> Optional[Dict]:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT * FROM pattern_scores WHERE pattern_key=?",
                (pattern_key,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def upsert_pattern_score(self, key: str, total: int, wins: int,
                             win_rate: float, bonus: int, disabled: int = 0,
                             disabled_until: str = None):
        conn = get_db()
        try:
            conn.execute("""
                INSERT INTO pattern_scores (pattern_key, total, wins, win_rate, bonus, disabled, disabled_until, updated_at)
                VALUES (?,?,?,?,?,?,?, datetime('now','localtime'))
                ON CONFLICT(pattern_key) DO UPDATE SET
                    total=?, wins=?, win_rate=?, bonus=?, disabled=?,
                    disabled_until=?, updated_at=datetime('now','localtime')
            """, (key, total, wins, win_rate, bonus, disabled, disabled_until,
                  total, wins, win_rate, bonus, disabled, disabled_until))
            conn.commit()
        except Exception as e:
            logger.error(f"Pattern score upsert: {e}")
        finally:
            conn.close()

    # ── Günlük Performans ──────────────────────
    def _update_daily_perf(self, pnl_usd: float):
        conn = get_db()
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            row = conn.execute(
                "SELECT * FROM daily_performance WHERE date=?", (today,)
            ).fetchone()
            if row:
                w = row["wins"] + (1 if pnl_usd > 0 else 0)
                l = row["losses"] + (1 if pnl_usd <= 0 else 0)
                t = w + l
                tp = row["total_pnl_usd"] + pnl_usd
                conn.execute("""
                    UPDATE daily_performance SET
                        total_trades=?, wins=?, losses=?, total_pnl_usd=?,
                        win_rate=?, best_trade_usd=?, worst_trade_usd=?
                    WHERE date=?
                """, (t, w, l, tp, round(w/t*100, 1) if t else 0,
                      max(row["best_trade_usd"], pnl_usd),
                      min(row["worst_trade_usd"], pnl_usd), today))
            else:
                is_w = 1 if pnl_usd > 0 else 0
                conn.execute("""
                    INSERT INTO daily_performance
                    (date, total_trades, wins, losses, total_pnl_usd, win_rate,
                     best_trade_usd, worst_trade_usd)
                    VALUES (?,1,?,?,?,?,?,?)
                """, (today, is_w, 1-is_w, pnl_usd,
                      100.0 if is_w else 0.0, max(pnl_usd, 0), min(pnl_usd, 0)))
            conn.commit()
        except Exception as e:
            logger.error(f"Daily perf: {e}")
        finally:
            conn.close()

    def get_daily_performance(self, days: int = 30, limit: int = 0) -> List[Dict]:
        conn = get_db()
        try:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            q = "SELECT * FROM daily_performance WHERE date>=? ORDER BY date DESC"
            params = [cutoff]
            if limit > 0:
                q += " LIMIT ?"
                params.append(limit)
            rows = conn.execute(q, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── News ────────────────────────────────────
    def save_news(self, item: Dict):
        conn = get_db()
        try:
            import hashlib
            news_id = item.get("id") or hashlib.md5(item.get("title", "").encode()).hexdigest()[:16]
            currencies = item.get("currencies", [])
            currency_str = ",".join(currencies) if isinstance(currencies, list) else str(currencies)
            conn.execute("""
                INSERT OR REPLACE INTO news
                (id,title,summary,source,url,published,currency,impact,sentiment,sentiment_score,fetched_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                news_id, item.get("title", ""), item.get("summary", ""),
                item.get("source", ""), item.get("link", item.get("url", "")),
                item.get("published", ""),
                currency_str, item.get("impact", "LOW"),
                item.get("sentiment", "NEUTRAL"), item.get("sentiment_score", 0),
                datetime.now().isoformat(),
            ))
            conn.commit()
        except Exception as e:
            logger.debug(f"News save: {e}")
        finally:
            conn.close()

    # ── Watchlist ───────────────────────────────
    def add_watchlist(self, instrument: str, direction: str = None,
                      note: str = "", target: float = None) -> int:
        conn = get_db()
        try:
            cur = conn.execute(
                "INSERT INTO watchlist (instrument,direction,note,target_price) VALUES (?,?,?,?)",
                (instrument, direction, note, target),
            )
            conn.commit()
            return cur.lastrowid
        except Exception as e:
            logger.error(f"Watchlist add: {e}")
            return 0
        finally:
            conn.close()

    def get_watchlist(self) -> List[Dict]:
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT * FROM watchlist WHERE active=1 ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def remove_watchlist(self, wl_id: int):
        conn = get_db()
        try:
            conn.execute("UPDATE watchlist SET active=0 WHERE id=?", (wl_id,))
            conn.commit()
        finally:
            conn.close()


# Singleton
db = Queries()
