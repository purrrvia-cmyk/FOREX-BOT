"""Multi-TF sinyal üreteci: 1D → 4H → 1H → 15M → 5M + KZ filtresi"""

import logging
from datetime import datetime
from config.instruments import INSTRUMENTS
from config.ict_params import ICT
from core.confluence import calc_confluence
from core.sessions import detect_kill_zone, calc_daily_bias
from core.data_feed import feed

logger = logging.getLogger("BOT.SIGNAL")

TF_CHAIN = ["1d", "4h", "1h", "15m", "5m"]
# Her TF'de min skor eşikleri
TF_MIN_SCORE = {"1d": 15, "4h": 20, "1h": 25, "15m": 20, "5m": 15}


class SignalGenerator:
    """ICT Multi-TF sinyal zinciri"""

    def __init__(self, news_fetcher=None, learning_engine=None):
        self.news = news_fetcher
        self.learning = learning_engine

    def scan_instrument(self, key: str) -> dict:
        """Tek enstrüman: tam analiz"""
        # KZ kontrolü
        kz = detect_kill_zone()
        is_kz = kz["is_kill_zone"]

        # Daily bias
        daily = calc_daily_bias(feed, key)

        # HTF'den LTF'ye analiz
        analysis = {}
        aligned_dir = None  # HTF'den gelen yön

        for tf in TF_CHAIN:
            try:
                result = calc_confluence(key, tf)
                analysis[tf] = result

                if result.get("error"):
                    continue

                sig = result.get("signal", "WAIT")
                score = abs(result.get("net_score", 0))

                # İlk anlamlı TF'den yön belirle
                if aligned_dir is None and sig != "WAIT":
                    aligned_dir = "LONG" if "LONG" in sig else "SHORT"

            except Exception as e:
                logger.error(f"{key} {tf} hata: {e}")
                analysis[tf] = {"error": str(e)}

        # Final sinyal: 1H veya 15M entry
        entry_tf = "15m"
        entry_data = analysis.get(entry_tf, {})
        if entry_data.get("error") or entry_data.get("signal") == "WAIT":
            entry_tf = "1h"
            entry_data = analysis.get(entry_tf, {})

        final_signal = entry_data.get("signal", "WAIT")
        final_score = entry_data.get("net_score", 0)

        # ═══ FİLTRELER ═══

        # 1. HTF uyum kontrolü
        htf_1d = analysis.get("1d", {}).get("signal", "WAIT")
        htf_4h = analysis.get("4h", {}).get("signal", "WAIT")
        if final_signal != "WAIT":
            fs_dir = "LONG" if "LONG" in final_signal else "SHORT"
            if htf_1d != "WAIT" and ("LONG" in htf_1d) != (fs_dir == "LONG"):
                final_signal = "WAIT"
                logger.info(f"{key}: 1D ters yön → sinyal iptal")
            elif htf_4h != "WAIT" and ("LONG" in htf_4h) != (fs_dir == "LONG"):
                final_score = int(final_score * 0.7)  # 4H ters = skor düşür

        # 2. KZ filtresi
        if not is_kz and final_signal != "WAIT":
            non_kz_conf = ICT.get("non_kz_min_confluence", 6)
            non_kz_score = ICT.get("non_kz_min_score", 70)
            entry_conf = entry_data.get("conf_bull", 0) if "LONG" in final_signal else entry_data.get("conf_bear", 0)

            # KZ dışı: daily+4H uyumlu + yüksek confluence + daily bias match
            htf_aligned = (htf_1d != "WAIT" and htf_4h != "WAIT" and
                           ("LONG" in htf_1d) == ("LONG" in htf_4h))
            bias_aligned = (daily["bias"] != "NEUTRAL" and
                            ("LONG" in final_signal and daily["bias"] == "BULLISH") or
                            ("SHORT" in final_signal and daily["bias"] == "BEARISH"))

            if not (entry_conf >= non_kz_conf and abs(final_score) >= non_kz_score
                    and htf_aligned and bias_aligned):
                final_signal = "WAIT"
                logger.info(f"{key}: KZ dışı + yetersiz confluence → sinyal iptal")

        # 3. Haber filtresi
        if self.news and final_signal != "WAIT":
            news_ok = self._check_news(key, final_signal)
            if not news_ok:
                final_signal = "WAIT"

        # 4. Learning filtresi
        if self.learning and final_signal != "WAIT":
            learn_ok = self._check_learning(key, final_signal, entry_data)
            if not learn_ok:
                final_signal = "WAIT"

        return {
            "instrument": key,
            "name": INSTRUMENTS[key]["name"],
            "final_signal": final_signal,
            "final_score": final_score,
            "entry_tf": entry_tf,
            "kill_zone": kz,
            "daily_bias": daily,
            "analysis": {tf: {
                "signal": a.get("signal", "?"),
                "score": a.get("net_score", 0),
                "conf_bull": a.get("conf_bull", 0),
                "conf_bear": a.get("conf_bear", 0),
            } for tf, a in analysis.items() if not a.get("error")},
            "entry_data": entry_data,
            "timestamp": datetime.now().isoformat(),
        }

    def scan_all(self) -> list:
        """Tüm enstrümanları tara"""
        results = []
        for key in INSTRUMENTS:
            try:
                r = self.scan_instrument(key)
                results.append(r)
            except Exception as e:
                logger.error(f"Scan {key}: {e}")
        results.sort(key=lambda x: abs(x.get("final_score", 0)), reverse=True)
        return results

    def _check_news(self, key: str, signal: str) -> bool:
        """Habere karşı işlem açma"""
        try:
            sentiment = self.news.get_sentiment(key)
            if not sentiment:
                return True
            # Haberler net olarak karşı yöndeyse → iptal
            if signal in ("LONG", "STRONG_LONG") and sentiment.get("direction") == "BEARISH" and sentiment.get("strength", 0) > 3:
                logger.info(f"{key}: Güçlü BEARISH haberler → LONG iptal")
                return False
            if signal in ("SHORT", "STRONG_SHORT") and sentiment.get("direction") == "BULLISH" and sentiment.get("strength", 0) > 3:
                logger.info(f"{key}: Güçlü BULLISH haberler → SHORT iptal")
                return False
            return True
        except Exception:
            return True

    def _check_learning(self, key: str, signal: str, data: dict) -> bool:
        """Öğrenme: kötü performanslı konseptleri filtrele"""
        try:
            disabled = self.learning.get_disabled_patterns()
            concepts = data.get("reasons_bull" if "LONG" in signal else "reasons_bear", [])
            for c in concepts:
                for d in disabled:
                    if d in c:
                        logger.info(f"{key}: '{c}' konsepti devre dışı → sinyal iptal")
                        return False
            return True
        except Exception:
            return True
