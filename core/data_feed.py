"""yfinance veri çekme + cache"""

import logging
import pandas as pd
import yfinance as yf
from datetime import datetime

from config.instruments import INSTRUMENTS, TF_MAP

logger = logging.getLogger("BOT.FEED")


class DataFeed:
    """Fiyat verisi çekme, cache'li"""

    def __init__(self):
        self._cache = {}
        self._ttl = 25  # saniye

    def candles(self, key: str, tf: str = "1h") -> pd.DataFrame:
        """Mum verisi çek/cache"""
        ck = f"{key}_{tf}"
        now = datetime.now().timestamp()
        if ck in self._cache:
            ts, data = self._cache[ck]
            if now - ts < self._ttl:
                return data

        inst = INSTRUMENTS.get(key)
        if not inst:
            return pd.DataFrame()

        tf_cfg = TF_MAP.get(tf, TF_MAP["1h"])
        try:
            ticker = yf.Ticker(inst["yf"])

            if tf_cfg.get("aggregate"):
                raw = ticker.history(period=tf_cfg["period"],
                                     interval=tf_cfg["interval"],
                                     auto_adjust=True)
                if raw.empty:
                    return pd.DataFrame()
                raw = raw.reset_index()
                raw.columns = [c.lower().replace(" ", "_") for c in raw.columns]
                ts_col = "datetime" if "datetime" in raw.columns else "date"
                raw = raw.rename(columns={ts_col: "timestamp"})
                raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True)
                n = tf_cfg["aggregate"]
                raw["group"] = raw["timestamp"].dt.floor(f"{n}h")
                df = raw.groupby("group").agg({
                    "timestamp": "first", "open": "first",
                    "high": "max", "low": "min",
                    "close": "last", "volume": "sum",
                }).reset_index(drop=True)
            else:
                raw = ticker.history(period=tf_cfg["period"],
                                     interval=tf_cfg["interval"],
                                     auto_adjust=True)
                if raw.empty:
                    return pd.DataFrame()
                raw = raw.reset_index()
                raw.columns = [c.lower().replace(" ", "_") for c in raw.columns]
                ts_col = "datetime" if "datetime" in raw.columns else "date"
                raw = raw.rename(columns={ts_col: "timestamp"})
                df = raw[["timestamp", "open", "high", "low", "close", "volume"]].copy()

            df = df.dropna(subset=["close"]).reset_index(drop=True)
            self._cache[ck] = (now, df)
            return df
        except Exception as e:
            logger.error(f"Veri hatası ({key} {tf}): {e}")
            return pd.DataFrame()

    def price(self, key: str) -> dict | None:
        """Anlık fiyat"""
        inst = INSTRUMENTS.get(key)
        if not inst:
            return None
        try:
            info = yf.Ticker(inst["yf"]).fast_info

            def _s(obj, *attrs):
                for a in attrs:
                    try:
                        v = getattr(obj, a, None)
                        if v and float(v) != 0:
                            return float(v)
                    except Exception:
                        continue
                return 0.0

            last = _s(info, "lastPrice", "last_price", "regularMarketPrice")
            prev = _s(info, "previousClose", "previous_close")
            if last == 0:
                last = prev
            return {
                "last": round(last, 5),
                "prev_close": round(prev, 5),
                "day_high": round(_s(info, "dayHigh", "day_high"), 5),
                "day_low": round(_s(info, "dayLow", "day_low"), 5),
            }
        except Exception as e:
            logger.error(f"Fiyat hatası ({key}): {e}")
            # Fallback: candle son kapanış
            try:
                df = self.candles(key, "15m")
                if not df.empty:
                    c = float(df["close"].iloc[-1])
                    return {"last": c, "prev_close": c, "day_high": c, "day_low": c}
            except Exception:
                pass
            return None

    def clear_cache(self):
        self._cache.clear()


# Singleton
feed = DataFeed()
