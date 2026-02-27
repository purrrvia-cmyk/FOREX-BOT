# =====================================================
# FOREX ICT Trading Bot — Haber & Ekonomik Takvim
# =====================================================
# Piyasa haberlerini takip eder, yüksek etkili olaylar
# tespit eder, trading sinyallerine haber bilgisi ekler.
#
# Kaynaklar:
#  - ForexFactory RSS (high impact events)
#  - FXStreet RSS (anlık haberler)
#  - Investing.com RSS (analiz & yorumlar)
#  - Built-in major event takvimi (NFP, FOMC, ECB vb.)
# =====================================================

import logging
import sqlite3
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Optional

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from config import NEWS_CONFIG, FOREX_INSTRUMENTS

logger = logging.getLogger("FOREX-BOT.NEWS")


# ═══════════════════════════════════════════════════
# BUILT-IN MAJOR EVENT TAKVİMİ
# ═══════════════════════════════════════════════════
# Her ay tekrarlayan yüksek etkili olaylar
RECURRING_EVENTS = [
    # ABD
    {"name": "Non-Farm Payrolls (NFP)", "currency": "USD", "impact": "HIGH",
     "schedule": "İlk Cuma her ay", "avoid_pairs": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD", "XAUUSD"],
     "desc": "ABD istihdam verisi — en yüksek volatilite olayı, NFP öncesi 30dk ve sonrası 30dk işlem yapma!"},
    {"name": "FOMC Faiz Kararı", "currency": "USD", "impact": "HIGH",
     "schedule": "6 haftada bir Çarşamba", "avoid_pairs": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD", "XAUUSD"],
     "desc": "Fed faiz kararı — tüm USD paritelerinde aşırı volatilite"},
    {"name": "CPI (Tüketici Fiyat Endeksi)", "currency": "USD", "impact": "HIGH",
     "schedule": "Ayda bir (genelde 10-13 arası)", "avoid_pairs": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "XAUUSD"],
     "desc": "ABD enflasyon verisi — Fed politikası için kritik"},
    {"name": "ISM Manufacturing PMI", "currency": "USD", "impact": "MEDIUM",
     "schedule": "Her ayın ilk iş günü", "avoid_pairs": ["EURUSD", "USDJPY"],
     "desc": "ABD imalat PMI — ekonomik sağlık göstergesi"},
    {"name": "Retail Sales", "currency": "USD", "impact": "MEDIUM",
     "schedule": "Ayda bir (genelde 13-16 arası)", "avoid_pairs": ["EURUSD", "USDJPY"],
     "desc": "ABD perakende satışlar — tüketici harcama trendi"},
    # Avrupa
    {"name": "ECB Faiz Kararı", "currency": "EUR", "impact": "HIGH",
     "schedule": "6 haftada bir Perşembe", "avoid_pairs": ["EURUSD"],
     "desc": "Avrupa Merkez Bankası faiz kararı — EUR volatilitesi"},
    {"name": "Euro Bölgesi CPI", "currency": "EUR", "impact": "MEDIUM",
     "schedule": "Ayda bir", "avoid_pairs": ["EURUSD"],
     "desc": "Euro Bölgesi enflasyon verisi"},
    # İngiltere
    {"name": "BoE Faiz Kararı", "currency": "GBP", "impact": "HIGH",
     "schedule": "6 haftada bir Perşembe", "avoid_pairs": ["GBPUSD"],
     "desc": "İngiltere Merkez Bankası faiz kararı — GBP volatilitesi"},
    {"name": "UK CPI", "currency": "GBP", "impact": "MEDIUM",
     "schedule": "Ayda bir", "avoid_pairs": ["GBPUSD"],
     "desc": "İngiltere enflasyon verisi"},
    # Japonya
    {"name": "BoJ Faiz Kararı", "currency": "JPY", "impact": "HIGH",
     "schedule": "6-8 haftada bir", "avoid_pairs": ["USDJPY"],
     "desc": "Japonya Merkez Bankası faiz kararı — JPY volatilitesi"},
    # Avustralya
    {"name": "RBA Faiz Kararı", "currency": "AUD", "impact": "HIGH",
     "schedule": "Ayda bir Salı (Şubat hariç)", "avoid_pairs": ["AUDUSD"],
     "desc": "Avustralya Merkez Bankası faiz kararı"},
    # Kanada
    {"name": "BoC Faiz Kararı", "currency": "CAD", "impact": "HIGH",
     "schedule": "6 haftada bir Çarşamba", "avoid_pairs": ["USDCAD"],
     "desc": "Kanada Merkez Bankası faiz kararı"},
    # Genel
    {"name": "G7/G20 Zirvesi", "currency": "ALL", "impact": "HIGH",
     "schedule": "Yılda birkaç kez", "avoid_pairs": ["ALL"],
     "desc": "Küresel politika kararları — tüm piyasalarda volatilite"},
]

# ═══════════════════════════════════════════════════
# HABER DUYGU ANALİZİ KELİME LİSTELERİ
# ═══════════════════════════════════════════════════
BULLISH_KEYWORDS = {
    "USD": ["hawkish", "rate hike", "strong jobs", "beat expectations", "higher growth",
            "hot inflation", "strong gdp", "consumer confidence rises", "employment surges",
            "dollar strengthens", "fed tightening"],
    "EUR": ["ecb hawkish", "euro zone growth", "german surplus", "euro strengthens",
            "improved outlook", "ecb rate hike"],
    "GBP": ["boe hawkish", "uk growth", "pound strengthens", "strong uk data",
            "boe rate hike"],
    "JPY": ["boj tightening", "yen strengthens", "japan growth", "boj hawkish"],
    "AUD": ["rba hawkish", "australia growth", "iron ore rises", "aussie strengthens"],
    "CAD": ["boc hawkish", "oil prices rise", "canada employment beats", "loonie strengthens"],
    "CHF": ["snb hawkish", "swiss franc strengthens", "safe haven demand"],
    "NZD": ["rbnz hawkish", "new zealand growth", "dairy prices rise"],
    "XAU": ["gold rally", "safe haven", "inflation fears", "geopolitical risk",
            "central bank buying", "dollar weakness", "recession fears"],
}

BEARISH_KEYWORDS = {
    "USD": ["dovish", "rate cut", "weak jobs", "miss expectations", "lower growth",
            "soft inflation", "weak gdp", "consumer confidence drops", "unemployment rises",
            "dollar weakens", "fed easing"],
    "EUR": ["ecb dovish", "euro zone recession", "german deficit", "euro weakens",
            "worsened outlook", "ecb rate cut"],
    "GBP": ["boe dovish", "uk recession", "pound weakens", "weak uk data",
            "boe rate cut", "brexit"],
    "JPY": ["boj easing", "yen weakens", "japan recession", "boj dovish",
            "negative rates"],
    "AUD": ["rba dovish", "australia slowdown", "iron ore drops", "china slowdown"],
    "CAD": ["boc dovish", "oil prices drop", "canada unemployment rises"],
    "CHF": ["snb dovish", "risk-on sentiment"],
    "NZD": ["rbnz dovish", "new zealand slowdown", "dairy prices drop"],
    "XAU": ["gold sell-off", "risk appetite", "dollar strength", "rate hike",
            "hawkish fed", "yields rise"],
}


class NewsFetcher:
    """
    Forex Haber & Ekonomik Takvim modülü.
    RSS feed'lerden haber çeker, sentiment analizi yapar,
    yüksek etkili olayları takip eder.
    """

    def __init__(self, db_path="forex_bot.db"):
        self.db_path = db_path
        self._news_cache = []
        self._cache_time = None
        self._cache_ttl = 300  # 5 dakika
        self._init_db()

    def _init_db(self):
        """Haber tablosu oluştur"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS news (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    summary TEXT,
                    source TEXT,
                    url TEXT,
                    published TEXT,
                    currency TEXT,
                    impact TEXT DEFAULT 'UNKNOWN',
                    sentiment TEXT DEFAULT 'NEUTRAL',
                    sentiment_score REAL DEFAULT 0,
                    fetched_at TEXT
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"News DB init hatası: {e}")

    def fetch_rss_news(self) -> List[Dict]:
        """RSS kaynaklarından haber çek"""
        if not HAS_FEEDPARSER:
            logger.warning("feedparser kurulu değil — pip install feedparser")
            return []

        # Cache kontrol
        now = datetime.now()
        if self._cache_time and (now - self._cache_time).total_seconds() < self._cache_ttl:
            return self._news_cache

        feeds = NEWS_CONFIG.get("rss_feeds", {})
        all_news = []

        for source_name, url in feeds.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:15]:
                    title = entry.get("title", "")
                    summary = entry.get("summary", entry.get("description", ""))[:500]
                    published = entry.get("published", "")
                    link = entry.get("link", "")

                    news_id = hashlib.md5(f"{title}{published}".encode()).hexdigest()[:16]
                    currency = self._detect_currency(title + " " + summary)
                    sentiment, score = self._analyze_sentiment(title + " " + summary, currency)
                    impact = self._assess_impact(title, summary)

                    item = {
                        "id": news_id,
                        "title": title,
                        "summary": summary[:300],
                        "source": source_name,
                        "url": link,
                        "published": published,
                        "currency": currency,
                        "impact": impact,
                        "sentiment": sentiment,
                        "sentiment_score": score,
                    }
                    all_news.append(item)
                    self._save_news(item)

            except Exception as e:
                logger.error(f"RSS fetch hatası ({source_name}): {e}")
                continue

        # Tarihe göre sırala (en yeni önce)
        all_news.sort(key=lambda x: x.get("published", ""), reverse=True)
        self._news_cache = all_news
        self._cache_time = now
        return all_news

    def _detect_currency(self, text: str) -> str:
        """Haberdeki para birimini tespit et"""
        text_upper = text.upper()
        currency_keywords = {
            "USD": ["USD", "DOLLAR", "FED", "FOMC", "NFP", "US ECONOMY", "TREASURY",
                     "WALL STREET", "S&P", "DOW"],
            "EUR": ["EUR", "EURO", "ECB", "EUROZONE", "GERMAN", "FRANCE", "EU ECONOMY"],
            "GBP": ["GBP", "POUND", "BOE", "STERLING", "UK ECONOMY", "BRITISH", "LONDON"],
            "JPY": ["JPY", "YEN", "BOJ", "JAPAN", "NIKKEI", "TOKYO"],
            "AUD": ["AUD", "AUSSIE", "RBA", "AUSTRALIA", "IRON ORE"],
            "CAD": ["CAD", "LOONIE", "BOC", "CANADA", "CANADIAN", "OIL PRICE"],
            "CHF": ["CHF", "FRANC", "SNB", "SWISS", "SWITZERLAND"],
            "NZD": ["NZD", "KIWI", "RBNZ", "NEW ZEALAND", "DAIRY"],
            "XAU": ["GOLD", "XAU", "PRECIOUS METAL", "BULLION", "SAFE HAVEN"],
        }

        scores = {}
        for currency, keywords in currency_keywords.items():
            score = sum(1 for kw in keywords if kw in text_upper)
            if score > 0:
                scores[currency] = score

        if scores:
            return max(scores, key=scores.get)
        return "GENERAL"

    def _analyze_sentiment(self, text: str, currency: str) -> tuple:
        """
        Basit keyword-based sentiment analizi.
        Returns: (sentiment_label, score)  score: -1.0 ... +1.0
        """
        text_lower = text.lower()
        bull_score = 0
        bear_score = 0

        # Para birimine özel kelimeler
        bull_kws = BULLISH_KEYWORDS.get(currency, []) + BULLISH_KEYWORDS.get("USD", [])
        bear_kws = BEARISH_KEYWORDS.get(currency, []) + BEARISH_KEYWORDS.get("USD", [])

        for kw in bull_kws:
            if kw.lower() in text_lower:
                bull_score += 1
        for kw in bear_kws:
            if kw.lower() in text_lower:
                bear_score += 1

        total = bull_score + bear_score
        if total == 0:
            return "NEUTRAL", 0.0

        score = (bull_score - bear_score) / total
        if score > 0.3:
            return "BULLISH", round(score, 2)
        elif score < -0.3:
            return "BEARISH", round(score, 2)
        return "NEUTRAL", round(score, 2)

    def _assess_impact(self, title: str, summary: str) -> str:
        """Haberin etkisini değerlendir"""
        text = (title + " " + summary).upper()
        high_impact = [
            "RATE DECISION", "INTEREST RATE", "NFP", "NON-FARM", "NONFARM",
            "CPI", "INFLATION", "GDP", "FOMC", "ECB", "BOE", "BOJ", "RBA",
            "EMPLOYMENT", "PAYROLL", "CENTRAL BANK", "MONETARY POLICY",
            "RECESSION", "CRISIS", "WAR", "SANCTIONS", "TARIFF",
            "DEFAULT", "EMERGENCY", "GEOPOLITICAL",
        ]
        medium_impact = [
            "PMI", "RETAIL SALES", "TRADE BALANCE", "HOUSING",
            "MANUFACTURING", "CONSUMER CONFIDENCE", "SENTIMENT",
            "INDUSTRIAL PRODUCTION", "SERVICES",
        ]

        for kw in high_impact:
            if kw in text:
                return "HIGH"
        for kw in medium_impact:
            if kw in text:
                return "MEDIUM"
        return "LOW"

    def _save_news(self, item: Dict):
        """Haberi veritabanına kaydet"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                INSERT OR REPLACE INTO news
                (id, title, summary, source, url, published, currency, impact, sentiment, sentiment_score, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item["id"], item["title"], item["summary"], item["source"],
                item["url"], item["published"], item["currency"],
                item["impact"], item["sentiment"], item["sentiment_score"],
                datetime.now().isoformat()
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"News save hatası: {e}")

    def get_upcoming_events(self) -> List[Dict]:
        """
        Yaklaşan yüksek etkili olayları döndür.
        Built-in takvimden + RSS'den birleştirilmiş.
        """
        events = []
        now = datetime.now()
        weekday = now.weekday()  # 0=Pazartesi

        for evt in RECURRING_EVENTS:
            events.append({
                "name": evt["name"],
                "currency": evt["currency"],
                "impact": evt["impact"],
                "schedule": evt["schedule"],
                "desc": evt["desc"],
                "avoid_pairs": evt["avoid_pairs"],
            })

        # RSS'den yüksek etkili haberler
        news = self.fetch_rss_news()
        for n in news[:20]:
            if n["impact"] == "HIGH":
                events.append({
                    "name": n["title"][:80],
                    "currency": n["currency"],
                    "impact": "HIGH",
                    "schedule": n["published"],
                    "desc": n["summary"][:200],
                    "avoid_pairs": [],
                    "source": n["source"],
                })

        return events

    def get_news_for_pair(self, instrument_key: str) -> Dict:
        """
        Belirli bir parite için filtrelenmiş haberler.
        Returns: {news: [...], sentiment: ..., should_trade: True/False}
        """
        inst = FOREX_INSTRUMENTS.get(instrument_key, {})
        pair_name = inst.get("name", instrument_key)
        base = pair_name[:3]
        quote = pair_name[3:6] if len(pair_name) >= 6 else "USD"

        relevant_currencies = {base, quote}
        if instrument_key == "XAUUSD":
            relevant_currencies = {"XAU", "USD"}

        all_news = self.fetch_rss_news()

        relevant_news = []
        total_sentiment = 0.0
        count = 0
        has_high_impact = False

        for n in all_news:
            if n["currency"] in relevant_currencies or n["currency"] == "GENERAL":
                relevant_news.append(n)
                total_sentiment += n["sentiment_score"]
                count += 1
                if n["impact"] == "HIGH":
                    has_high_impact = True

        # Tekrarlayan yüksek etkili olay kontrolü
        for evt in RECURRING_EVENTS:
            if instrument_key in evt.get("avoid_pairs", []) or "ALL" in evt.get("avoid_pairs", []):
                has_high_impact = True

        avg_sentiment = total_sentiment / count if count > 0 else 0

        if avg_sentiment > 0.3:
            pair_sentiment = "BULLISH"
        elif avg_sentiment < -0.3:
            pair_sentiment = "BEARISH"
        else:
            pair_sentiment = "NEUTRAL"

        # İşlem yapılmalı mı?
        should_trade = not has_high_impact  # Yüksek etkili haberde işlem yapma
        caution = ""
        if has_high_impact:
            caution = "⚠️ Yüksek etkili haber/olay — İşlem yapma veya SL daralt!"

        return {
            "instrument": instrument_key,
            "news": relevant_news[:10],
            "news_count": count,
            "sentiment": pair_sentiment,
            "avg_sentiment": round(avg_sentiment, 2),
            "has_high_impact": has_high_impact,
            "should_trade": should_trade,
            "caution": caution,
        }

    def get_market_commentary(self, instrument_key: str, signal_data: dict) -> str:
        """
        Haber + sinyal verilerine dayalı piyasa yorumu oluştur.
        Türkçe, detaylı, ICT perspektifli.
        """
        news_data = self.get_news_for_pair(instrument_key)
        inst = FOREX_INSTRUMENTS.get(instrument_key, {})
        pair_name = inst.get("name", instrument_key)

        lines = []
        lines.append(f"═══ {pair_name} — Piyasa Yorumu ═══")
        lines.append(f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        lines.append("")

        # 1. ICT Sinyal Özeti
        signal = signal_data.get("signal", "WAIT")
        net_score = signal_data.get("net_score", 0)
        if signal in ("STRONG_LONG", "LONG"):
            lines.append(f"📈 ICT SİNYAL: {signal} (Skor: +{net_score})")
        elif signal in ("STRONG_SHORT", "SHORT"):
            lines.append(f"📉 ICT SİNYAL: {signal} (Skor: {net_score})")
        else:
            lines.append(f"⏸️ ICT SİNYAL: BEKLE (Skor: {net_score})")

        # 2. Yapı Analizi
        ms = signal_data.get("market_structure", {})
        if ms.get("trend"):
            trend_tr = {"BULLISH": "Yükseliş", "BEARISH": "Düşüş", "NEUTRAL": "Nötr"}
            lines.append(f"📊 Piyasa Yapısı: {trend_tr.get(ms['trend'], ms['trend'])}")

        # 3. Daily Bias
        db = signal_data.get("daily_bias", {})
        if db.get("desc"):
            lines.append(f"📋 Günlük Bias: {db['desc']}")

        # 4. Kill Zone durumu
        kz = signal_data.get("kill_zones", {})
        if kz.get("is_kill_zone"):
            lines.append(f"🕐 {kz['active_zone']} Kill Zone AKTİF")
        else:
            lines.append(f"⏰ Kill Zone dışında ({kz.get('next_kz', '')})")

        # 5. Haber etkisi
        lines.append("")
        lines.append("── Haber Analizi ──")
        if news_data["has_high_impact"]:
            lines.append("⚠️ YÜKSEK ETKİLİ HABER/OLAY!")
            lines.append("İşlem GİRMEMEYİ veya SL daraltmayı düşün.")
        if news_data["news"]:
            lines.append(f"Haber Sentiment: {news_data['sentiment']} ({news_data['avg_sentiment']:+.2f})")
            for n in news_data["news"][:5]:
                impact_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(n["impact"], "⚪")
                lines.append(f"  {impact_icon} [{n['source']}] {n['title'][:60]}")
        else:
            lines.append("Alakalı haber bulunamadı.")

        # 6. ICT Sebepleri
        lines.append("")
        lines.append("── ICT Confluence Detayları ──")
        bull_reasons = signal_data.get("reasons_bull", [])
        bear_reasons = signal_data.get("reasons_bear", [])
        if bull_reasons:
            lines.append(f"🟢 Alış Sinyalleri ({signal_data.get('conf_bull', 0)} confluence):")
            for r in bull_reasons:
                lines.append(f"   • {r}")
        if bear_reasons:
            lines.append(f"🔴 Satış Sinyalleri ({signal_data.get('conf_bear', 0)} confluence):")
            for r in bear_reasons:
                lines.append(f"   • {r}")

        # 7. SL/TP
        sl_tp = signal_data.get("sl_tp")
        if sl_tp:
            lines.append("")
            lines.append("── Risk Yönetimi ──")
            lines.append(f"  SL: {sl_tp['sl']}")
            lines.append(f"  TP1: {sl_tp['tp1']} (RR: {sl_tp['rr1']})")
            lines.append(f"  TP2: {sl_tp['tp2']} (RR: {sl_tp['rr2']})")

        # 8. Premium/Discount
        pd_info = signal_data.get("premium_discount", {})
        if pd_info.get("zone"):
            zone_tr = {"PREMIUM": "Pahalı Bölge", "DISCOUNT": "Ucuz Bölge", "NEUTRAL": "Denge"}
            lines.append(f"\n📍 Fiyat Bölgesi: {zone_tr.get(pd_info['zone'], pd_info['zone'])} (%{pd_info.get('zone_pct', 50)})")

        # 9. Sonuç
        lines.append("")
        lines.append("── SONUÇ ──")
        if signal == "WAIT":
            lines.append("⏸️ Şu an net ICT confluence yok. Bekleme pozisyonunda kal.")
        elif not news_data["should_trade"]:
            lines.append("⚠️ Yüksek etkili haber nedeniyle DİKKAT! Pozisyon büyüklüğünü azalt veya bekle.")
        elif signal in ("STRONG_LONG", "STRONG_SHORT"):
            lines.append(f"✅ GÜÇLÜ sinyal! {signal_data.get('conf_bull' if 'LONG' in signal else 'conf_bear', 0)} confluence ile {'ALIŞ' if 'LONG' in signal else 'SATIŞ'} fırsatı.")
        else:
            lines.append(f"{'ALIŞ' if 'LONG' in signal else 'SATIŞ'} sinyali mevcut ancak STRONG değil — pozisyon küçük tut.")

        return "\n".join(lines)

    def get_all_pair_sentiments(self) -> Dict:
        """Tüm paritelerin haber sentiment'lerini döndür"""
        results = {}
        for key in FOREX_INSTRUMENTS:
            try:
                results[key] = self.get_news_for_pair(key)
            except Exception as e:
                logger.error(f"Sentiment hatası ({key}): {e}")
                results[key] = {"sentiment": "NEUTRAL", "avg_sentiment": 0, "should_trade": True}
        return results

    def get_recent_news(self, limit: int = 30) -> List[Dict]:
        """Son haberleri getir (tüm kaynaklardan)"""
        news = self.fetch_rss_news()
        return news[:limit]


# Singleton
news_fetcher = NewsFetcher()
