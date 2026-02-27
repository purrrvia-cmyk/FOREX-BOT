"""Öğrenme motoru: kapanan işlemleri analiz et, pattern performansını izle"""

import logging
from datetime import datetime, timedelta
from config.capital import LEARNING
from database import db

logger = logging.getLogger("BOT.LEARN")


class LearningEngine:
    """Kendi kendine öğrenen sistem"""

    def __init__(self):
        self._disabled_cache = []
        self._last_analysis = None

    def analyze_trade(self, trade: dict):
        """Kapanan her işlemi analiz et ve logla"""
        concepts = trade.get("concepts_used", "")
        if not concepts:
            return

        pnl = trade.get("pnl_usd", 0)
        direction = trade.get("direction", "")
        kz = trade.get("kill_zone", "NONE")
        instrument = trade.get("instrument", "")

        # Her konsepti ayrı kaydet
        for concept in concepts.split(","):
            concept = concept.strip()
            if not concept:
                continue

            # Pattern score güncelle
            current = db.get_pattern_score(concept)
            if current:
                new_total = current["total_trades"] + 1
                new_wins = current["wins"] + (1 if pnl > 0 else 0)
                new_losses = current["losses"] + (1 if pnl < 0 else 0)
                new_pnl = current["total_pnl"] + pnl
                new_wr = round((new_wins / new_total) * 100, 1) if new_total > 0 else 0
            else:
                new_total = 1
                new_wins = 1 if pnl > 0 else 0
                new_losses = 1 if pnl < 0 else 0
                new_pnl = pnl
                new_wr = 100 if pnl > 0 else 0

            # Disable kontrolü (min 50 trade)
            disabled = False
            disabled_until = None
            if new_total >= LEARNING["min_trades_to_learn"]:
                if new_wr < LEARNING["disable_winrate"]:
                    disabled = True
                    disabled_until = (datetime.now() + timedelta(days=7)).isoformat()
                    logger.warning(f"⚠️ '{concept}' devre dışı: WR %{new_wr} < %{LEARNING['disable_winrate']}")
                elif new_wr < LEARNING["bad_winrate"]:
                    logger.info(f"📊 '{concept}' düşük performans: WR %{new_wr}")

            db.upsert_pattern_score(concept, {
                "total_trades": new_total, "wins": new_wins,
                "losses": new_losses, "total_pnl": round(new_pnl, 2),
                "winrate": new_wr, "disabled": disabled,
                "disabled_until": disabled_until,
            })

        # Learning log kaydet
        db.save_learning_log({
            "instrument": instrument, "direction": direction,
            "entry_score": trade.get("score", 0),
            "concepts_used": concepts, "kill_zone": kz,
            "pnl_usd": pnl,
            "notes": self._generate_notes(trade),
        })

    def _generate_notes(self, trade: dict) -> str:
        """İşlem notları oluştur"""
        pnl = trade.get("pnl_usd", 0)
        kz = trade.get("kill_zone", "NONE")
        notes = []

        if pnl > 0:
            notes.append("Karlı işlem")
        else:
            notes.append("Zararlı işlem")

        if kz == "NONE":
            notes.append("KZ dışı giriş")

        return " | ".join(notes)

    def get_disabled_patterns(self) -> list:
        """Devre dışı bırakılmış konseptler"""
        now = datetime.now().isoformat()
        patterns = []
        # DB'den kontrol et
        try:
            # Pattern scores tablosundan disable olanları al
            from database.connection import get_db
            conn = get_db()
            rows = conn.execute(
                "SELECT pattern FROM pattern_scores WHERE disabled=1 AND (disabled_until IS NULL OR disabled_until > ?)",
                (now,)
            ).fetchall()
            patterns = [r["pattern"] for r in rows]
        except Exception as e:
            logger.error(f"Disabled pattern hatası: {e}")
        return patterns

    def get_performance_summary(self) -> dict:
        """Genel performans özeti"""
        try:
            from database.connection import get_db
            conn = get_db()

            # En iyi konseptler
            best = conn.execute(
                "SELECT pattern, winrate, total_trades, total_pnl FROM pattern_scores "
                "WHERE total_trades >= 5 ORDER BY winrate DESC LIMIT 5"
            ).fetchall()

            # En kötü
            worst = conn.execute(
                "SELECT pattern, winrate, total_trades, total_pnl FROM pattern_scores "
                "WHERE total_trades >= 5 ORDER BY winrate ASC LIMIT 5"
            ).fetchall()

            # KZ performans
            kz_perf = conn.execute(
                "SELECT kill_zone, COUNT(*) as cnt, "
                "SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as wins, "
                "ROUND(SUM(pnl_usd), 2) as total_pnl "
                "FROM learning_log GROUP BY kill_zone"
            ).fetchall()

            # Genel
            total = conn.execute(
                "SELECT COUNT(*) as cnt, "
                "SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as wins, "
                "ROUND(SUM(pnl_usd), 2) as total_pnl "
                "FROM learning_log"
            ).fetchone()

            return {
                "best_patterns": [dict(r) for r in best],
                "worst_patterns": [dict(r) for r in worst],
                "kz_performance": [dict(r) for r in kz_perf],
                "total_analyzed": total["cnt"] if total else 0,
                "total_wins": total["wins"] if total else 0,
                "total_pnl": total["total_pnl"] if total else 0,
                "disabled_count": len(self.get_disabled_patterns()),
            }
        except Exception as e:
            logger.error(f"Performans özeti hatası: {e}")
            return {}

    def periodic_review(self):
        """Periyodik gözden geçirme — 50 trade kontrolü"""
        try:
            from database.connection import get_db
            conn = get_db()
            rows = conn.execute(
                "SELECT pattern, winrate, total_trades, disabled FROM pattern_scores "
                "WHERE total_trades >= ?", (LEARNING["min_trades_to_learn"],)
            ).fetchall()

            for r in rows:
                # Re-enable edilebilir mi?
                if r["disabled"] and r["winrate"] >= LEARNING["good_winrate"]:
                    db.upsert_pattern_score(r["pattern"], {
                        "disabled": False, "disabled_until": None,
                    })
                    logger.info(f"✅ '{r['pattern']}' yeniden aktif: WR %{r['winrate']}")

                # Yeni disable?
                if not r["disabled"] and r["winrate"] < LEARNING["disable_winrate"]:
                    db.upsert_pattern_score(r["pattern"], {
                        "disabled": True,
                        "disabled_until": (datetime.now() + timedelta(days=7)).isoformat(),
                    })
                    logger.warning(f"⚠️ '{r['pattern']}' devre dışı: WR %{r['winrate']}")

        except Exception as e:
            logger.error(f"Periyodik review hatası: {e}")
