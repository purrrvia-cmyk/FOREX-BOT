"""Ekonomik takvim: yaklaşan yüksek etkili olaylar"""

import logging
import feedparser
from datetime import datetime

logger = logging.getLogger("BOT.CALENDAR")

CALENDAR_FEEDS = [
    {"name": "ForexFactory", "url": "https://nfs.faireconomy.media/ff_calendar_thisweek.json", "type": "json"},
]

# Etkili olaylar
HIGH_IMPACT_EVENTS = [
    "Non-Farm", "NFP", "CPI", "GDP", "Interest Rate", "FOMC",
    "ECB", "BOE", "BOJ", "RBA", "RBNZ", "Employment",
    "Retail Sales", "PMI", "Trade Balance", "PPI",
]


class EconomicCalendar:
    """Ekonomik takvim takibi"""

    def __init__(self):
        self._events = []
        self._last_fetch = None

    def fetch(self):
        """Takvim verisi çek"""
        now = datetime.now()
        if self._last_fetch and (now - self._last_fetch).seconds < 3600:
            return

        events = []
        try:
            import urllib.request
            import json
            req = urllib.request.Request(
                CALENDAR_FEEDS[0]["url"],
                headers={"User-Agent": "FOREX-BOT/2.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                for ev in data:
                    impact = ev.get("impact", "").lower()
                    if impact in ("high", "medium"):
                        events.append({
                            "title": ev.get("title", ""),
                            "country": ev.get("country", ""),
                            "date": ev.get("date", ""),
                            "time": ev.get("time", ""),
                            "impact": impact.upper(),
                            "forecast": ev.get("forecast", ""),
                            "previous": ev.get("previous", ""),
                        })
        except Exception as e:
            logger.error(f"Takvim hatası: {e}")

        self._events = events
        self._last_fetch = now
        logger.info(f"📅 {len(events)} ekonomik olay yüklendi")

    def upcoming(self, hours: int = 4) -> list:
        """Önümüzdeki N saat içindeki olaylar"""
        now = datetime.utcnow()
        upcoming = []
        for ev in self._events:
            try:
                dt_str = f"{ev['date']} {ev['time']}"
                # Format varies, try common ones
                for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M", "%b %d %H:%M"]:
                    try:
                        dt = datetime.strptime(dt_str.strip(), fmt)
                        break
                    except ValueError:
                        continue
                else:
                    continue
                dt = dt.replace(tzinfo=None)
                diff = (dt - now).total_seconds() / 3600
                if 0 <= diff <= hours:
                    ev["hours_until"] = round(diff, 1)
                    upcoming.append(ev)
            except Exception:
                continue
        return upcoming

    def is_safe_to_trade(self, key: str) -> dict:
        """Bu pariteyle ilgili yakın zamanda yüksek etkili olay var mı?"""
        upcoming = self.upcoming(hours=1)
        currency_map = {
            "USD": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD", "XAUUSD", "XAGUSD"],
            "EUR": ["EURUSD"], "GBP": ["GBPUSD"], "JPY": ["USDJPY"],
            "CHF": ["USDCHF"], "AUD": ["AUDUSD"], "NZD": ["NZDUSD"],
            "CAD": ["USDCAD"],
        }
        danger = []
        for ev in upcoming:
            country = ev.get("country", "").upper()
            for ccy, pairs in currency_map.items():
                if ccy in country and key in pairs and ev["impact"] == "HIGH":
                    danger.append(ev)
        if danger:
            return {"safe": False, "events": danger,
                    "reason": f"{len(danger)} yüksek etkili olay yaklaşıyor"}
        return {"safe": True}

    def get_events(self) -> list:
        return self._events
