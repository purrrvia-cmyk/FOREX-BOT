"""RSS haber çekme + duygu analizi"""

import logging
import feedparser
from datetime import datetime, timedelta
from config.news import NEWS_CFG, BULLISH_KW, BEARISH_KW
from config.instruments import INSTRUMENTS
from database import db

logger = logging.getLogger("BOT.NEWS")

_CURRENCY_MAP = {
    "EURUSD": ["EUR", "USD"], "GBPUSD": ["GBP", "USD"],
    "USDJPY": ["USD", "JPY"], "USDCHF": ["USD", "CHF"],
    "AUDUSD": ["AUD", "USD"], "NZDUSD": ["NZD", "USD"],
    "USDCAD": ["USD", "CAD"], "XAUUSD": ["XAU", "USD"],
    "XAGUSD": ["XAG", "USD"],
}


class NewsFetcher:
    """RSS haberlerini çekip duygu analizi yap"""

    def __init__(self):
        self._cache = {}
        self._last_fetch = None
        self._interval = NEWS_CFG.get("check_interval_sec", 300)

    def fetch(self):
        """Tüm kaynakları çek"""
        now = datetime.now()
        if self._last_fetch and (now - self._last_fetch).seconds < self._interval:
            return

        all_news = []
        rss_feeds = NEWS_CFG.get("rss_feeds", {})
        for name, url in rss_feeds.items():
            try:
                f = feedparser.parse(url)
                for entry in f.entries[:10]:
                    title = entry.get("title", "").strip()
                    summary = entry.get("summary", "")[:200]
                    link = entry.get("link", "")
                    pub = entry.get("published", "")

                    if not title:
                        continue

                    text = f"{title} {summary}".upper()
                    sentiment = self._analyze(text)

                    all_news.append({
                        "title": title, "summary": summary,
                        "source": name, "link": link,
                        "published": pub, "sentiment": sentiment["direction"],
                        "impact": sentiment["impact"],
                        "currencies": sentiment["currencies"],
                    })
            except Exception as e:
                logger.error(f"Haber hatası ({name}): {e}")

        # DB kaydet
        for n in all_news:
            db.save_news(n)

        self._cache = self._group_by_currency(all_news)
        self._last_fetch = now
        logger.info(f"📰 {len(all_news)} haber güncellendi")

    def _analyze(self, text: str) -> dict:
        """Basit keyword-based duygu analizi"""
        bull_score, bear_score = 0, 0
        currencies = set()

        for ccy, keywords in BULLISH_KW.items():
            for kw in keywords:
                if kw in text:
                    bull_score += 1
                    currencies.add(ccy)

        for ccy, keywords in BEARISH_KW.items():
            for kw in keywords:
                if kw in text:
                    bear_score += 1
                    currencies.add(ccy)

        # High impact keywords
        high_impact = ["RATE DECISION", "NFP", "CPI", "GDP", "FOMC",
                       "ECB", "BOE", "BOJ", "RBA", "RBNZ", "EMPLOYMENT"]
        impact = "HIGH" if any(h in text for h in high_impact) else "MEDIUM"

        if bull_score > bear_score:
            direction = "BULLISH"
        elif bear_score > bull_score:
            direction = "BEARISH"
        else:
            direction = "NEUTRAL"

        return {
            "direction": direction,
            "strength": max(bull_score, bear_score),
            "impact": impact,
            "currencies": list(currencies),
        }

    def _group_by_currency(self, news_list: list) -> dict:
        grouped = {}
        for n in news_list:
            for ccy in n.get("currencies", []):
                if ccy not in grouped:
                    grouped[ccy] = []
                grouped[ccy].append(n)
        return grouped

    def get_sentiment(self, key: str) -> dict | None:
        """Parite için haber duygusu"""
        currencies = _CURRENCY_MAP.get(key, [])
        if not currencies:
            return None

        bull, bear = 0, 0
        relevant = []
        for ccy in currencies:
            items = self._cache.get(ccy, [])
            for item in items:
                relevant.append(item)
                if item["sentiment"] == "BULLISH":
                    w = 2 if item["impact"] == "HIGH" else 1
                    # USD haberi: ters etki (USD bull = EUR/USD bear)
                    if ccy == "USD" and not key.startswith("USD"):
                        bear += w
                    else:
                        bull += w
                elif item["sentiment"] == "BEARISH":
                    w = 2 if item["impact"] == "HIGH" else 1
                    if ccy == "USD" and not key.startswith("USD"):
                        bull += w
                    else:
                        bear += w

        if not relevant:
            return None

        direction = "BULLISH" if bull > bear else ("BEARISH" if bear > bull else "NEUTRAL")
        return {
            "direction": direction,
            "strength": max(bull, bear),
            "bull": bull, "bear": bear,
            "count": len(relevant),
            "latest": relevant[:3],
        }

    def get_all_news(self, limit: int = 20) -> list:
        """Son haberler"""
        all_items = []
        for ccy, items in self._cache.items():
            all_items.extend(items)
        # Deduplicate
        seen = set()
        unique = []
        for item in all_items:
            t = item["title"]
            if t not in seen:
                seen.add(t)
                unique.append(item)
        return sorted(unique, key=lambda x: x.get("published", ""), reverse=True)[:limit]
