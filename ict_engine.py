# =====================================================
# FOREX ICT Trading Bot — ICT Analiz Motoru
# =====================================================
# %100 ICT (Inner Circle Trader) Uyumlu
#
# 16 ICT Konsepti:
#   1.  Market Structure (BOS / CHoCH / Swing H-L)
#   2.  Order Blocks (OB) + Mitigation tracking
#   3.  Breaker Blocks (başarısız OB → S/R dönüşümü)
#   4.  Fair Value Gaps (FVG) + Consequent Encroachment
#   5.  Displacement (büyük momentum mumları)
#   6.  Liquidity Sweeps (EQH/EQL + stop hunt)
#   7.  Inducement (küçük likidite kapanları)
#   8.  Optimal Trade Entry (OTE) — Fib 0.618-0.786
#   9.  Premium / Discount Zones
#  10.  Kill Zones (London / NY / Asian sessions)
#  11.  ICT Silver Bullet windows
#  12.  Power of 3 / AMD (Accumulation-Manipulation-Distribution)
#  13.  Judas Swing (Kill Zone'da sahte hareket)
#  14.  Daily Bias (HTF trend teyidi)
#  15.  Asian Range + London Breakout
#  16.  Smart Money Trap detection
# =====================================================

import yfinance as yf
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
from config import FOREX_INSTRUMENTS, TF_MAP, ICT_PARAMS, KILL_ZONES, SILVER_BULLET

logger = logging.getLogger("FOREX-BOT.ICT")


class ICTEngine:
    """
    Tam ICT Uyumlu Forex Analiz Motoru.

    Her parite için 16 ICT konseptini analiz eder,
    confluence skoru hesaplar, yorum üretir.
    """

    def __init__(self):
        self._cache = {}
        self._cache_ttl = 30  # saniye

    # ================================================================
    #  VERİ ÇEKME (yfinance)
    # ================================================================

    def get_candles(self, instrument_key, timeframe="1h"):
        """yfinance'den mum verileri çek, cache'li"""
        cache_key = f"fx_{instrument_key}_{timeframe}"
        now = datetime.now().timestamp()
        if cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if now - ts < self._cache_ttl:
                return data

        inst = FOREX_INSTRUMENTS.get(instrument_key)
        if not inst:
            return pd.DataFrame()

        tf_cfg = TF_MAP.get(timeframe, TF_MAP["1h"])

        try:
            ticker = yf.Ticker(inst["yf_symbol"])

            if timeframe == "4h":
                raw = ticker.history(period=tf_cfg["period"], interval="1h", auto_adjust=True)
                if raw.empty:
                    return pd.DataFrame()
                raw = raw.reset_index()
                raw.columns = [c.lower().replace(" ", "_") for c in raw.columns]
                if "datetime" in raw.columns:
                    raw = raw.rename(columns={"datetime": "timestamp"})
                elif "date" in raw.columns:
                    raw = raw.rename(columns={"date": "timestamp"})
                raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True)
                raw["group"] = raw["timestamp"].dt.floor("4h")
                df = raw.groupby("group").agg({
                    "timestamp": "first", "open": "first",
                    "high": "max", "low": "min",
                    "close": "last", "volume": "sum"
                }).reset_index(drop=True)
            else:
                raw = ticker.history(period=tf_cfg["period"], interval=tf_cfg["interval"], auto_adjust=True)
                if raw.empty:
                    return pd.DataFrame()
                raw = raw.reset_index()
                raw.columns = [c.lower().replace(" ", "_") for c in raw.columns]
                if "datetime" in raw.columns:
                    raw = raw.rename(columns={"datetime": "timestamp"})
                elif "date" in raw.columns:
                    raw = raw.rename(columns={"date": "timestamp"})
                df = raw[["timestamp", "open", "high", "low", "close", "volume"]].copy()

            df = df.dropna(subset=["close"]).reset_index(drop=True)
            self._cache[cache_key] = (now, df)
            return df
        except Exception as e:
            logger.error(f"Veri çekme hatası ({instrument_key} {timeframe}): {e}")
            return pd.DataFrame()

    def get_price(self, instrument_key):
        """Anlık fiyat bilgisi"""
        inst = FOREX_INSTRUMENTS.get(instrument_key)
        if not inst:
            return None
        try:
            ticker = yf.Ticker(inst["yf_symbol"])
            info = ticker.fast_info

            def _safe(obj, *keys):
                for k in keys:
                    try:
                        v = getattr(obj, k, None) or (obj.get(k) if hasattr(obj, 'get') else None)
                        if v and float(v) != 0:
                            return float(v)
                    except Exception:
                        continue
                return 0.0

            last = _safe(info, "lastPrice", "last_price", "regularMarketPrice")
            prev = _safe(info, "previousClose", "previous_close")
            if last == 0:
                last = prev
            return {
                "last": round(last, 5),
                "prev_close": round(prev, 5),
                "day_high": round(_safe(info, "dayHigh", "day_high"), 5),
                "day_low": round(_safe(info, "dayLow", "day_low"), 5),
            }
        except Exception as e:
            logger.error(f"Fiyat hatası ({instrument_key}): {e}")
            try:
                df = self.get_candles(instrument_key, "15m")
                if not df.empty:
                    cp = float(df["close"].iloc[-1])
                    return {"last": cp, "prev_close": cp, "day_high": cp, "day_low": cp}
            except Exception:
                pass
            return None

    # ================================================================
    #  TEKNİK GÖSTERGELER (RSI, EMA, ATR)
    # ================================================================

    def calc_atr(self, df, period=14):
        """ATR hesapla"""
        if len(df) < period + 1:
            return 0.0
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        close = df["close"].astype(float)
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        return float(tr.ewm(alpha=1/period, min_periods=period).mean().iloc[-1])

    def calc_indicators(self, df):
        """RSI, EMA, ATR hesapla"""
        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)

        # RSI(14)
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss_s = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14).mean()
        avg_loss = loss_s.ewm(alpha=1/14, min_periods=14).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))

        # EMA
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()
        ema200 = close.ewm(span=200, adjust=False).mean() if len(close) >= 200 else pd.Series([np.nan]*len(close))

        # ATR
        atr = self.calc_atr(df, 14)

        return {
            "rsi": float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50,
            "ema20": float(ema20.iloc[-1]),
            "ema50": float(ema50.iloc[-1]),
            "ema200": float(ema200.iloc[-1]) if not np.isnan(ema200.iloc[-1]) else None,
            "atr": atr,
            "atr_pct": round(atr / float(close.iloc[-1]) * 100, 3) if atr > 0 else 0,
        }

    # ================================================================
    #  1. MARKET STRUCTURE (BOS / CHoCH / Swing H-L)
    # ================================================================

    def detect_market_structure(self, df):
        """
        ICT Piyasa Yapısı Analizi:
        - Swing High / Swing Low tespiti
        - BOS (Break of Structure): Yapı kırılımı
        - CHoCH (Change of Character): Trend dönüş sinyali

        BULLISH yapı: HH (Higher High) + HL (Higher Low)
        BEARISH yapı: LH (Lower High) + LL (Lower Low)
        """
        if len(df) < 20:
            return {"trend": "NEUTRAL", "bos": [], "choch": None,
                    "swing_highs": [], "swing_lows": []}

        highs = df["high"].astype(float).values
        lows = df["low"].astype(float).values
        close = df["close"].astype(float).values
        lookback = ICT_PARAMS.get("swing_lookback", 5)

        swing_highs = []
        swing_lows = []
        for i in range(lookback, len(df) - lookback):
            if highs[i] == max(highs[i-lookback:i+lookback+1]):
                swing_highs.append({"idx": i, "price": float(highs[i])})
            if lows[i] == min(lows[i-lookback:i+lookback+1]):
                swing_lows.append({"idx": i, "price": float(lows[i])})

        trend = "NEUTRAL"
        bos_list = []
        choch = None

        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            hh = swing_highs[-1]["price"] > swing_highs[-2]["price"]
            hl = swing_lows[-1]["price"] > swing_lows[-2]["price"]
            lh = swing_highs[-1]["price"] < swing_highs[-2]["price"]
            ll = swing_lows[-1]["price"] < swing_lows[-2]["price"]

            if hh and hl:
                trend = "BULLISH"
            elif lh and ll:
                trend = "BEARISH"

            # BOS tespiti
            cur_price = close[-1]
            if swing_highs and cur_price > swing_highs[-1]["price"]:
                bos_list.append({"type": "BULLISH_BOS", "level": swing_highs[-1]["price"]})
            if swing_lows and cur_price < swing_lows[-1]["price"]:
                bos_list.append({"type": "BEARISH_BOS", "level": swing_lows[-1]["price"]})

            # CHoCH tespiti: 3 swing noktasında trend değişimi
            if len(swing_highs) >= 3 and len(swing_lows) >= 3:
                if (swing_highs[-3]["price"] < swing_highs[-2]["price"] and
                        swing_highs[-1]["price"] < swing_highs[-2]["price"]):
                    choch = {
                        "type": "BEARISH_CHOCH",
                        "level": swing_lows[-2]["price"],
                        "desc": "Yükseliş trendinden düşüşe geçiş sinyali (CHoCH)"
                    }
                if (swing_lows[-3]["price"] > swing_lows[-2]["price"] and
                        swing_lows[-1]["price"] > swing_lows[-2]["price"]):
                    choch = {
                        "type": "BULLISH_CHOCH",
                        "level": swing_highs[-2]["price"],
                        "desc": "Düşüş trendinden yükselişe geçiş sinyali (CHoCH)"
                    }

        return {
            "trend": trend, "bos": bos_list, "choch": choch,
            "swing_highs": swing_highs[-4:] if swing_highs else [],
            "swing_lows": swing_lows[-4:] if swing_lows else [],
        }

    # ================================================================
    #  2. ORDER BLOCKS (OB) + Mitigation
    # ================================================================

    def detect_order_blocks(self, df, cur_price=None):
        """
        ICT Order Block Tespiti:
        - Büyük hareket öncesi son ters mum = OB
        - Bullish OB: Düşüş mumu + ardından güçlü yükseliş
        - Bearish OB: Yükseliş mumu + ardından güçlü düşüş
        - Mitigation: Fiyat OB'ye geri dönerse → mitigate olmuştur
        """
        if len(df) < 10:
            return []

        opens = df["open"].astype(float).values
        closes = df["close"].astype(float).values
        highs = df["high"].astype(float).values
        lows = df["low"].astype(float).values
        blocks = []
        min_strength = ICT_PARAMS.get("ob_min_strength", 2.0)

        for i in range(2, len(df) - 2):
            candle_range = highs[i] - lows[i]
            if candle_range == 0:
                continue
            avg_range = np.mean([highs[j] - lows[j] for j in range(max(0, i-10), i)])
            if avg_range == 0:
                continue
            next_move = abs(closes[min(i+2, len(df)-1)] - closes[i])

            if next_move > avg_range * min_strength:
                # Bullish OB: ayı mumu → boğa kırılımı
                if closes[i] < opens[i] and closes[min(i+2, len(df)-1)] > closes[i]:
                    mitigated = False
                    if cur_price is not None:
                        for k in range(i+3, len(df)):
                            if lows[k] <= closes[i]:
                                mitigated = True
                                break
                    blocks.append({
                        "type": "BULLISH_OB", "high": float(opens[i]),
                        "low": float(closes[i]), "idx": i,
                        "strength": round(next_move/avg_range, 1),
                        "mitigated": mitigated
                    })
                # Bearish OB: boğa mumu → ayı kırılımı
                elif closes[i] > opens[i] and closes[min(i+2, len(df)-1)] < closes[i]:
                    mitigated = False
                    if cur_price is not None:
                        for k in range(i+3, len(df)):
                            if highs[k] >= closes[i]:
                                mitigated = True
                                break
                    blocks.append({
                        "type": "BEARISH_OB", "high": float(closes[i]),
                        "low": float(opens[i]), "idx": i,
                        "strength": round(next_move/avg_range, 1),
                        "mitigated": mitigated
                    })

        blocks.sort(key=lambda x: x["strength"], reverse=True)
        return blocks[:8]

    # ================================================================
    #  3. BREAKER BLOCKS (başarısız OB → S/R)
    # ================================================================

    def detect_breaker_blocks(self, df):
        """
        ICT Breaker Block:
        - Mitigate olmuş OB'ler → rol değiştirir
        - Bullish OB kırılırsa → Bearish Breaker (direnç)
        - Bearish OB kırılırsa → Bullish Breaker (destek)
        """
        if len(df) < 15:
            return []

        obs = self.detect_order_blocks(df, cur_price=float(df["close"].iloc[-1]))
        breakers = []
        cur_price = float(df["close"].iloc[-1])

        for ob in obs:
            if ob["mitigated"]:
                mid = (ob["high"] + ob["low"]) / 2
                if ob["type"] == "BULLISH_OB" and cur_price < mid:
                    breakers.append({
                        "type": "BEARISH_BREAKER",
                        "high": ob["high"], "low": ob["low"],
                        "desc": "Kırılmış Bullish OB → Bearish Breaker (direnç görevi görür)"
                    })
                elif ob["type"] == "BEARISH_OB" and cur_price > mid:
                    breakers.append({
                        "type": "BULLISH_BREAKER",
                        "high": ob["high"], "low": ob["low"],
                        "desc": "Kırılmış Bearish OB → Bullish Breaker (destek görevi görür)"
                    })
        return breakers[:3]

    # ================================================================
    #  4. FVG + Consequent Encroachment (CE)
    # ================================================================

    def detect_fvg(self, df):
        """
        ICT Fair Value Gap (FVG):
        - 3 mum formasyonu: orta mum ile yan mumların fitilleri arasında boşluk
        - Bullish FVG: mum[i] low > mum[i-2] high → yukarı boşluk
        - Bearish FVG: mum[i] high < mum[i-2] low → aşağı boşluk
        - CE (Consequent Encroachment): FVG'nin %50 seviyesi (OTE noktası)
        """
        if len(df) < 5:
            return []

        highs = df["high"].astype(float).values
        lows = df["low"].astype(float).values
        gaps = []

        for i in range(2, len(df)):
            # Bullish FVG
            if lows[i] > highs[i-2]:
                gap_size = lows[i] - highs[i-2]
                ce_level = (lows[i] + highs[i-2]) / 2
                filled = False
                ce_tested = False
                for k in range(i+1, len(df)):
                    if lows[k] <= highs[i-2]:
                        filled = True
                        break
                    if lows[k] <= ce_level:
                        ce_tested = True
                status = "Dolduruldu" if filled else ("CE test edildi" if ce_tested else "Aktif")
                gaps.append({
                    "type": "BULLISH_FVG",
                    "top": float(lows[i]), "bottom": float(highs[i-2]),
                    "ce_level": float(ce_level),
                    "size": float(gap_size), "idx": i,
                    "filled": filled, "ce_tested": ce_tested,
                    "status": status,
                })
            # Bearish FVG
            if highs[i] < lows[i-2]:
                gap_size = lows[i-2] - highs[i]
                ce_level = (lows[i-2] + highs[i]) / 2
                filled = False
                ce_tested = False
                for k in range(i+1, len(df)):
                    if highs[k] >= lows[i-2]:
                        filled = True
                        break
                    if highs[k] >= ce_level:
                        ce_tested = True
                status = "Dolduruldu" if filled else ("CE test edildi" if ce_tested else "Aktif")
                gaps.append({
                    "type": "BEARISH_FVG",
                    "top": float(lows[i-2]), "bottom": float(highs[i]),
                    "ce_level": float(ce_level),
                    "size": float(gap_size), "idx": i,
                    "filled": filled, "ce_tested": ce_tested,
                    "status": status,
                })

        return gaps[-12:]

    # ================================================================
    #  5. DISPLACEMENT (büyük momentum mumları)
    # ================================================================

    def detect_displacement(self, df):
        """
        ICT Displacement:
        - Normalden çok büyük gövdeli mumlar (2.5x+ ortalama)
        - Kurumsal tarafın agresif pozisyon aldığını gösterir
        - Yön teyidi olarak kullanılır
        """
        if len(df) < 20:
            return []

        opens = df["open"].astype(float).values
        closes = df["close"].astype(float).values
        highs = df["high"].astype(float).values
        lows = df["low"].astype(float).values
        displacements = []

        avg_body = np.mean([abs(closes[i] - opens[i]) for i in range(max(0, len(df)-20), len(df))])
        if avg_body == 0:
            return []

        mult = ICT_PARAMS.get("disp_body_mult", 2.5)
        ratio_min = ICT_PARAMS.get("disp_body_ratio", 0.7)

        for i in range(len(df)-15, len(df)):
            if i < 0:
                continue
            body = abs(closes[i] - opens[i])
            candle_range = highs[i] - lows[i]
            if candle_range == 0:
                continue
            body_ratio = body / candle_range

            if body > avg_body * mult and body_ratio > ratio_min:
                direction = "BULLISH" if closes[i] > opens[i] else "BEARISH"
                displacements.append({
                    "type": f"{direction}_DISPLACEMENT",
                    "idx": i,
                    "body_mult": round(body / avg_body, 1),
                    "body_ratio": round(body_ratio, 2),
                })

        return displacements[-5:]

    # ================================================================
    #  6. LIQUIDITY SWEEPS (EQH/EQL + Stop Hunt)
    # ================================================================

    def detect_liquidity_sweeps(self, df):
        """
        ICT Likidite Süpürme:
        - EQH (Equal Highs): Aynı seviyede zirveler → BSL birikimi
        - EQL (Equal Lows): Aynı seviyede dipler → SSL birikimi
        - Fiyat bu seviyeleri geçip geri dönerse → likidite süpürüldü
        - BSL sweep → BEARISH dönüş beklenir
        - SSL sweep → BULLISH dönüş beklenir
        """
        if len(df) < 20:
            return []

        highs = df["high"].astype(float).values
        lows = df["low"].astype(float).values
        closes = df["close"].astype(float).values
        tolerance = ICT_PARAMS.get("sweep_tolerance", 0.001)
        sweeps = []

        for i in range(5, len(df) - 1):
            # BSL sweep
            for j in range(max(0, i-15), i-3):
                if abs(highs[j] - highs[i-1]) / max(highs[j], 0.0001) < tolerance:
                    if highs[i] > highs[j] * 1.001 and closes[i] < highs[j]:
                        sweeps.append({
                            "type": "BSL_SWEEP",
                            "level": float(highs[j]),
                            "sweep_price": float(highs[i]),
                            "idx": i,
                            "desc": "Buy-side likidite süpürüldü — zirveler üzerine çıkıp geri döndü"
                        })
                        break
            # SSL sweep
            for j in range(max(0, i-15), i-3):
                if abs(lows[j] - lows[i-1]) / max(lows[j], 0.0001) < tolerance:
                    if lows[i] < lows[j] * 0.999 and closes[i] > lows[j]:
                        sweeps.append({
                            "type": "SSL_SWEEP",
                            "level": float(lows[j]),
                            "sweep_price": float(lows[i]),
                            "idx": i,
                            "desc": "Sell-side likidite süpürüldü — dipler altına inip geri döndü"
                        })
                        break

        return sweeps[-5:]

    # ================================================================
    #  7. INDUCEMENT (küçük likidite kapanları)
    # ================================================================

    def detect_inducement(self, df, swing_data):
        """
        ICT Inducement:
        - Ana swing yapısı içindeki minor high/low kırılmaları
        - Smart money, retail trader'ları yanıltmak için küçük kırılımlar yapar
        """
        if len(df) < 20 or not swing_data.get("swing_highs") or not swing_data.get("swing_lows"):
            return []

        highs = df["high"].astype(float).values
        lows = df["low"].astype(float).values
        inducements = []

        last_sh = swing_data["swing_highs"][-1]
        last_sl = swing_data["swing_lows"][-1]
        start_idx = min(last_sh["idx"], last_sl["idx"])
        end_idx = max(last_sh["idx"], last_sl["idx"])

        mini_highs = []
        mini_lows = []
        for i in range(start_idx+1, min(end_idx, len(df)-1)):
            if i >= 2 and i < len(df) - 2:
                if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                    mini_highs.append({"idx": i, "price": float(highs[i])})
                if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                    mini_lows.append({"idx": i, "price": float(lows[i])})

        for mh in mini_highs:
            for k in range(mh["idx"]+1, min(mh["idx"]+5, len(df))):
                if highs[k] > mh["price"]:
                    inducements.append({
                        "type": "BULLISH_INDUCEMENT", "level": mh["price"], "idx": k,
                        "desc": "Minor high kırıldı — buy-side likidite toplandı"
                    })
                    break

        for ml in mini_lows:
            for k in range(ml["idx"]+1, min(ml["idx"]+5, len(df))):
                if lows[k] < ml["price"]:
                    inducements.append({
                        "type": "BEARISH_INDUCEMENT", "level": ml["price"], "idx": k,
                        "desc": "Minor low kırıldı — sell-side likidite toplandı"
                    })
                    break

        return inducements[-3:]

    # ================================================================
    #  8. OTE (Optimal Trade Entry — Fib 0.618-0.786)
    # ================================================================

    def calc_ote(self, df, ms):
        """
        ICT OTE (Optimal Trade Entry):
        - Son swing high-low arasında Fibonacci 0.618-0.786 bölgesi
        - BULLISH: Geri çekilme bölgesinden LONG giriş
        - BEARISH: Toparlanma bölgesinden SHORT giriş
        """
        if not ms["swing_highs"] or not ms["swing_lows"]:
            return None

        sh = ms["swing_highs"][-1]
        sl = ms["swing_lows"][-1]
        swing_range = sh["price"] - sl["price"]
        if swing_range <= 0:
            return None

        fib_low = ICT_PARAMS.get("ote_fib_low", 0.618)
        fib_high = ICT_PARAMS.get("ote_fib_high", 0.786)

        if ms["trend"] == "BULLISH":
            fib_618 = sh["price"] - swing_range * fib_low
            fib_786 = sh["price"] - swing_range * fib_high
            return {
                "direction": "LONG",
                "ote_top": round(fib_618, 5), "ote_bottom": round(fib_786, 5),
                "swing_high": sh["price"], "swing_low": sl["price"],
            }
        elif ms["trend"] == "BEARISH":
            fib_618 = sl["price"] + swing_range * fib_low
            fib_786 = sl["price"] + swing_range * fib_high
            return {
                "direction": "SHORT",
                "ote_top": round(fib_786, 5), "ote_bottom": round(fib_618, 5),
                "swing_high": sh["price"], "swing_low": sl["price"],
            }
        return None

    # ================================================================
    #  9. PREMIUM / DISCOUNT ZONES
    # ================================================================

    def calc_premium_discount(self, df):
        """
        ICT Premium/Discount:
        - Swing range'in equilibrium (denge) noktası = ortası
        - Denge üstü = Premium (pahalı → SHORT fırsatı)
        - Denge altı = Discount (ucuz → LONG fırsatı)
        """
        if len(df) < 20:
            return {"zone": "NEUTRAL", "zone_pct": 50, "equilibrium": 0,
                    "range_high": 0, "range_low": 0}

        lookback = min(ICT_PARAMS.get("pd_lookback", 50), len(df))
        range_high = float(df["high"].iloc[-lookback:].max())
        range_low = float(df["low"].iloc[-lookback:].min())
        eq = (range_high + range_low) / 2
        cur_price = float(df["close"].iloc[-1])

        if range_high == range_low:
            return {"zone": "NEUTRAL", "zone_pct": 50, "equilibrium": eq,
                    "range_high": range_high, "range_low": range_low, "current": cur_price}

        if cur_price > eq:
            pct = (cur_price - eq) / (range_high - eq) * 100
            zone = "PREMIUM"
        else:
            pct = (eq - cur_price) / (eq - range_low) * 100
            zone = "DISCOUNT"

        return {
            "zone": zone, "zone_pct": round(min(pct, 100), 1),
            "equilibrium": round(eq, 5),
            "range_high": round(range_high, 5),
            "range_low": round(range_low, 5),
            "current": round(cur_price, 5),
        }

    # ================================================================
    # 10. KILL ZONES (London / NY / Asian)
    # ================================================================

    def detect_kill_zones(self):
        """
        ICT Kill Zones (EST bazlı, DST uyumlu):
        - Asian: 20:00-00:00 EST → Düşük volatilite, range oluşumu
        - London: 02:00-05:00 EST → En yüksek likidite, trend başlangıcı
        - New York: 07:00-10:00 EST → London overlap, en volatil dönem

        Kill Zone dışında işlem riski yüksek — düşük kalite sinyaller.
        """
        now = datetime.utcnow()
        hour = now.hour
        minute = now.minute

        # DST tespiti (yaklaşık)
        month = now.month
        is_dst = 3 < month < 11
        if month == 3 and now.day >= 8:
            is_dst = True
        elif month == 11 and now.day < 7:
            is_dst = True
        dst_shift = 1 if is_dst else 0

        zones = []
        active = None

        kz_defs = [
            ("Asian", (0 - dst_shift) % 24, (5 - dst_shift) % 24,
             "Asya seansı — düşük volatilite, range oluşumu"),
            ("London", (7 - dst_shift) % 24, (10 - dst_shift) % 24,
             "London açılışı — yüksek likidite, trend başlangıcı"),
            ("New York", (12 - dst_shift) % 24, (15 - dst_shift) % 24,
             "NY açılışı — London overlap, en volatil dönem"),
        ]

        for name, start, end, desc in kz_defs:
            is_active = start <= hour < end
            remaining = 0
            if is_active:
                active = name.upper().replace(" ", "_")
                remaining = (end - hour - 1) * 60 + (60 - minute)
            zones.append({
                "name": f"{name} Kill Zone",
                "active": is_active,
                "start_utc": start, "end_utc": end,
                "remaining_min": remaining,
                "desc": desc,
            })

        next_kz = None
        for name, start, end, _ in kz_defs:
            if hour < start:
                mins_until = (start - hour) * 60 - minute
                next_kz = f"{name} KZ {mins_until} dk sonra"
                break

        return {
            "active_zone": active,
            "zones": zones,
            "is_kill_zone": active is not None,
            "next_kz": next_kz or "Asian KZ yarın",
        }

    # ================================================================
    # 11. ICT SILVER BULLET
    # ================================================================

    def detect_silver_bullet(self):
        """
        ICT Silver Bullet Pencereleri (EST bazlı):
        - London SB: 03:00-04:00 EST → FVG giriş fırsatı
        - NY AM SB: 10:00-11:00 EST → FVG giriş fırsatı
        - NY PM SB: 14:00-15:00 EST → FVG giriş fırsatı

        Silver Bullet saatinde FVG bazlı girişler çok güçlü olabilir.
        """
        now = datetime.utcnow()
        hour = now.hour
        minute = now.minute

        month = now.month
        is_dst = 3 < month < 11
        if month == 3 and now.day >= 8:
            is_dst = True
        elif month == 11 and now.day < 7:
            is_dst = True
        est_offset = 4 if is_dst else 5

        sb_windows = [
            {"name": "London Silver Bullet", "est_start": 3, "est_end": 4},
            {"name": "NY AM Silver Bullet", "est_start": 10, "est_end": 11},
            {"name": "NY PM Silver Bullet", "est_start": 14, "est_end": 15},
        ]

        active_sb = None
        for sb in sb_windows:
            sb["start_utc"] = sb["est_start"] + est_offset
            sb["end_utc"] = sb["est_end"] + est_offset
            sb["active"] = sb["start_utc"] <= hour < sb["end_utc"]
            if sb["active"]:
                remaining = (sb["end_utc"] - hour - 1) * 60 + (60 - minute)
                sb["remaining"] = remaining
                active_sb = sb

        return {
            "windows": sb_windows,
            "active": active_sb,
            "is_active": active_sb is not None,
        }

    # ================================================================
    # 12. POWER OF 3 / AMD (Accumulation-Manipulation-Distribution)
    # ================================================================

    def detect_amd_pattern(self, df):
        """
        ICT Power of 3 / AMD:
        - Accumulation: Dar range birikimi (%40 pencere)
        - Manipulation: Sahte kırılım, likidite avı (%30 pencere)
        - Distribution: Gerçek yön hareketi (%30 pencere)

        AMD Bullish: Birikme → aşağı manipülasyon → yukarı dağıtım
        AMD Bearish: Birikme → yukarı manipülasyon → aşağı dağıtım
        """
        if len(df) < 20:
            return None

        closes = df["close"].astype(float).values
        highs = df["high"].astype(float).values
        lows = df["low"].astype(float).values

        lookback = min(20, len(df) - 1)
        acc_end = int(lookback * 0.4)
        acc_range = highs[-lookback:-lookback+acc_end].max() - lows[-lookback:-lookback+acc_end].min()
        full_range = highs[-lookback:].max() - lows[-lookback:].min()

        if full_range == 0:
            return None

        acc_ratio = acc_range / full_range
        man_start = acc_end
        man_end = int(lookback * 0.7)
        if man_end <= man_start:
            return None

        dist_close = closes[-1]
        dist_open = closes[-lookback+man_end] if man_end < lookback else closes[-1]

        if acc_ratio < 0.4:
            direction = "BULLISH" if dist_close > dist_open else "BEARISH"
            if direction == "BULLISH" and lows[-lookback+man_start:-lookback+man_end].min() < lows[-lookback:-lookback+acc_end].min():
                return {"pattern": "AMD_BULLISH", "direction": "LONG",
                        "desc": "AMD Bullish: Birikme → aşağı manipülasyon → yukarı dağıtım"}
            elif direction == "BEARISH" and highs[-lookback+man_start:-lookback+man_end].max() > highs[-lookback:-lookback+acc_end].max():
                return {"pattern": "AMD_BEARISH", "direction": "SHORT",
                        "desc": "AMD Bearish: Birikme → yukarı manipülasyon → aşağı dağıtım"}
        return None

    # ================================================================
    # 13. JUDAS SWING
    # ================================================================

    def detect_judas_swing(self, df):
        """
        ICT Judas Swing:
        - Kill Zone açılışında ilk hareketin TERSİ gerçek yöndür
        - Boğa Judas: Önce aşağı sahte hareket → sonra yukarı gerçek hareket
        - Ayı Judas: Önce yukarı sahte hareket → sonra aşağı gerçek hareket
        """
        if len(df) < 10:
            return None

        kill = self.detect_kill_zones()
        if not kill["is_kill_zone"]:
            return None

        opens = df["open"].astype(float).values
        closes = df["close"].astype(float).values
        total = min(8, len(df) - 1)
        split = max(2, total // 3)

        first_move = closes[-total] - opens[-total]
        last_move = closes[-1] - closes[-(total - split)]
        kz_name = kill["active_zone"].replace("_", " ").title()

        if first_move > 0 and last_move < 0 and abs(last_move) > abs(first_move) * 0.8:
            return {"type": "BEARISH_JUDAS", "kill_zone": kill["active_zone"],
                    "desc": f"Judas Swing: {kz_name}'da yukarı sahte hareket → gerçek yön aşağı"}
        elif first_move < 0 and last_move > 0 and abs(last_move) > abs(first_move) * 0.8:
            return {"type": "BULLISH_JUDAS", "kill_zone": kill["active_zone"],
                    "desc": f"Judas Swing: {kz_name}'da aşağı sahte hareket → gerçek yön yukarı"}
        return None

    # ================================================================
    # 14. DAILY BIAS (HTF yön teyidi)
    # ================================================================

    def calc_daily_bias(self, instrument_key):
        """
        ICT Daily Bias:
        - Günlük TF'den yapı analizi → HTF trend yönü
        - İşlemler HTF yönüne uyumlu olmalı
        """
        df_daily = self.get_candles(instrument_key, "1d")
        if df_daily.empty or len(df_daily) < 20:
            return {"bias": "NEUTRAL", "desc": "Yetersiz günlük veri"}

        ms = self.detect_market_structure(df_daily)
        pd_zone = self.calc_premium_discount(df_daily)

        bias = "NEUTRAL"
        desc = "Günlük bias belirsiz"

        if ms["trend"] == "BULLISH":
            bias = "BULLISH"
            desc = "Günlük trend yükseliş — LONG öncelikli"
            if pd_zone["zone"] == "PREMIUM" and pd_zone["zone_pct"] > 70:
                desc += " (DİKKAT: Premium bölgede)"
        elif ms["trend"] == "BEARISH":
            bias = "BEARISH"
            desc = "Günlük trend düşüş — SHORT öncelikli"
            if pd_zone["zone"] == "DISCOUNT" and pd_zone["zone_pct"] > 70:
                desc += " (DİKKAT: Discount bölgede)"

        if ms["choch"]:
            choch_dir = "yükselişe" if "BULL" in ms["choch"]["type"] else "düşüşe"
            desc += f" | CHoCH: {choch_dir} dönüş!"

        return {"bias": bias, "desc": desc, "trend": ms["trend"],
                "zone": pd_zone["zone"], "zone_pct": pd_zone["zone_pct"]}

    # ================================================================
    # 15. ASIAN RANGE + LONDON BREAKOUT
    # ================================================================

    def detect_asian_range_breakout(self, df):
        """
        ICT Asian Range:
        - Asian session (00:00-08:00 UTC) range'ini belirle
        - London açılışında bu range kırılırsa → trend yönü belirlenir
        """
        if len(df) < 10:
            return None

        has_ts = "timestamp" in df.columns
        if has_ts:
            try:
                ts = pd.to_datetime(df["timestamp"], utc=True)
                today = ts.iloc[-1].normalize()
                asian_mask = (ts >= today) & (ts.dt.hour < 8)
                if asian_mask.sum() < 2:
                    yesterday = today - pd.Timedelta(days=1)
                    asian_mask = (ts >= yesterday) & (ts < yesterday + pd.Timedelta(hours=8))
                if asian_mask.sum() >= 2:
                    asian_df = df[asian_mask]
                    asian_high = float(asian_df["high"].max())
                    asian_low = float(asian_df["low"].min())
                else:
                    n = min(8, len(df) - 2)
                    asian_high = float(df["high"].iloc[-n-8:-n].max()) if len(df) > n+8 else float(df["high"].iloc[:8].max())
                    asian_low = float(df["low"].iloc[-n-8:-n].min()) if len(df) > n+8 else float(df["low"].iloc[:8].min())
            except Exception:
                asian_high = float(df["high"].iloc[-20:-12].max()) if len(df) >= 20 else float(df["high"].iloc[:8].max())
                asian_low = float(df["low"].iloc[-20:-12].min()) if len(df) >= 20 else float(df["low"].iloc[:8].min())
        else:
            if len(df) < 20:
                return None
            asian_high = float(df["high"].iloc[-20:-12].max())
            asian_low = float(df["low"].iloc[-20:-12].min())

        if asian_high <= asian_low:
            return None

        cur_price = float(df["close"].iloc[-1])
        if cur_price > asian_high:
            return {"type": "BULLISH_BREAKOUT",
                    "asian_high": round(asian_high, 5), "asian_low": round(asian_low, 5),
                    "desc": f"Asian Range yukarı kırıldı ({round(asian_low,5)} - {round(asian_high,5)})"}
        elif cur_price < asian_low:
            return {"type": "BEARISH_BREAKOUT",
                    "asian_high": round(asian_high, 5), "asian_low": round(asian_low, 5),
                    "desc": f"Asian Range aşağı kırıldı ({round(asian_low,5)} - {round(asian_high,5)})"}
        else:
            return {"type": "INSIDE_RANGE",
                    "asian_high": round(asian_high, 5), "asian_low": round(asian_low, 5),
                    "desc": f"Fiyat Asian Range içinde ({round(asian_low,5)} - {round(asian_high,5)})"}

    # ================================================================
    # 16. SMART MONEY TRAP
    # ================================================================

    def detect_smart_money_trap(self, df, ms):
        """
        ICT Smart Money Trap:
        - Retail trader'ları tuzağa düşüren formasyonlar
        - Bull Trap: Yukarı sahte kırılım + geri dönüş → SHORT sinyali
        - Bear Trap: Aşağı sahte kırılım + geri dönüş → LONG sinyali
        - Uzun fitil + ters kapanış = trap göstergesi
        """
        if len(df) < 10:
            return None

        highs = df["high"].astype(float).values
        lows = df["low"].astype(float).values
        closes = df["close"].astype(float).values
        opens = df["open"].astype(float).values

        for i in range(len(df)-3, len(df)):
            if i < 2:
                continue
            wick_up = highs[i] - max(closes[i], opens[i])
            wick_down = min(closes[i], opens[i]) - lows[i]
            body = abs(closes[i] - opens[i])
            candle_range = highs[i] - lows[i]
            if candle_range == 0:
                continue

            if wick_up > body * 2 and wick_up > candle_range * 0.6 and closes[i] < opens[i]:
                return {"type": "BULL_TRAP", "idx": i, "trap_level": float(highs[i]),
                        "desc": "Smart Money Trap: Yukarı sahte kırılım + geri dönüş → SHORT"}
            if wick_down > body * 2 and wick_down > candle_range * 0.6 and closes[i] > opens[i]:
                return {"type": "BEAR_TRAP", "idx": i, "trap_level": float(lows[i]),
                        "desc": "Smart Money Trap: Aşağı sahte kırılım + geri dönüş → LONG"}
        return None

    # ================================================================
    #  CONFLUENCE SKOR SİSTEMİ
    # ================================================================

    def calculate_confluence(self, instrument_key, timeframe="1h"):
        """
        Tüm 16 ICT konseptini birleştirerek confluence skoru hesaplar.
        Returns: Tam analiz sonucu dict
        """
        df = self.get_candles(instrument_key, timeframe)
        if df.empty or len(df) < 30:
            return {"error": "Yetersiz veri"}

        inst = FOREX_INSTRUMENTS[instrument_key]
        cur_price = float(df["close"].iloc[-1])

        # Tüm ICT analizleri çalıştır
        ms = self.detect_market_structure(df)
        obs = self.detect_order_blocks(df, cur_price)
        breakers = self.detect_breaker_blocks(df)
        fvgs = self.detect_fvg(df)
        displacements = self.detect_displacement(df)
        sweeps = self.detect_liquidity_sweeps(df)
        inducements = self.detect_inducement(df, ms)
        ote = self.calc_ote(df, ms)
        pd_zone = self.calc_premium_discount(df)
        kill = self.detect_kill_zones()
        silver_bullet = self.detect_silver_bullet()
        amd = self.detect_amd_pattern(df)
        judas = self.detect_judas_swing(df)
        daily_bias = self.calc_daily_bias(instrument_key)
        asian_bo = self.detect_asian_range_breakout(df)
        smt = self.detect_smart_money_trap(df, ms)
        indicators = self.calc_indicators(df)

        # Skor hesaplama
        bull_score = 0
        bear_score = 0
        reasons_bull = []
        reasons_bear = []
        conf_bull = 0
        conf_bear = 0

        # 1. Market Structure (30p)
        if ms["trend"] == "BULLISH":
            bull_score += 30; conf_bull += 1
            reasons_bull.append("Piyasa yapısı yükseliş trendinde (HH + HL)")
        elif ms["trend"] == "BEARISH":
            bear_score += 30; conf_bear += 1
            reasons_bear.append("Piyasa yapısı düşüş trendinde (LH + LL)")

        for bos in ms["bos"]:
            if "BULLISH" in bos["type"]:
                bull_score += 10; conf_bull += 1
                reasons_bull.append(f"Bullish BOS @ {bos['level']:.5f}")
            elif "BEARISH" in bos["type"]:
                bear_score += 10; conf_bear += 1
                reasons_bear.append(f"Bearish BOS @ {bos['level']:.5f}")

        if ms["choch"]:
            if "BULLISH" in ms["choch"]["type"]:
                bull_score += 15; conf_bull += 1
                reasons_bull.append("Bullish CHoCH — trend dönüşü!")
            elif "BEARISH" in ms["choch"]["type"]:
                bear_score += 15; conf_bear += 1
                reasons_bear.append("Bearish CHoCH — trend dönüşü!")

        # 2. Order Blocks (20p)
        active_obs = [ob for ob in obs if not ob["mitigated"]]
        bull_ob = [ob for ob in active_obs if ob["type"] == "BULLISH_OB" and ob["low"] <= cur_price <= ob["high"]]
        bear_ob = [ob for ob in active_obs if ob["type"] == "BEARISH_OB" and ob["low"] <= cur_price <= ob["high"]]
        if bull_ob:
            bull_score += 20; conf_bull += 1
            reasons_bull.append(f"Aktif Bullish OB içinde (güç: {bull_ob[0]['strength']}x)")
        if bear_ob:
            bear_score += 20; conf_bear += 1
            reasons_bear.append(f"Aktif Bearish OB içinde (güç: {bear_ob[0]['strength']}x)")

        # 3. Breaker Blocks (10p)
        if any(bb["type"] == "BULLISH_BREAKER" for bb in breakers):
            bull_score += 10; conf_bull += 1
            reasons_bull.append("Bullish Breaker Block desteği")
        if any(bb["type"] == "BEARISH_BREAKER" for bb in breakers):
            bear_score += 10; conf_bear += 1
            reasons_bear.append("Bearish Breaker Block direnci")

        # 4. FVG (15p)
        active_fvgs = [f for f in fvgs if not f["filled"] and f["idx"] >= len(df)-15]
        bull_fvg = [f for f in active_fvgs if f["type"] == "BULLISH_FVG"]
        bear_fvg = [f for f in active_fvgs if f["type"] == "BEARISH_FVG"]
        ce_bull = [f for f in bull_fvg if f["ce_tested"]]
        ce_bear = [f for f in bear_fvg if f["ce_tested"]]
        if bull_fvg:
            pts = 15 if ce_bull else 10
            bull_score += pts; conf_bull += 1
            reasons_bull.append(f"{len(bull_fvg)} Bullish FVG{' (CE test edildi)' if ce_bull else ''}")
        if bear_fvg:
            pts = 15 if ce_bear else 10
            bear_score += pts; conf_bear += 1
            reasons_bear.append(f"{len(bear_fvg)} Bearish FVG{' (CE test edildi)' if ce_bear else ''}")

        # 5. Displacement (10p)
        for d in [d for d in displacements if d["idx"] >= len(df)-5]:
            if "BULLISH" in d["type"]:
                bull_score += 10; conf_bull += 1
                reasons_bull.append(f"Bullish Displacement ({d['body_mult']}x)")
            else:
                bear_score += 10; conf_bear += 1
                reasons_bear.append(f"Bearish Displacement ({d['body_mult']}x)")

        # 6. Liquidity Sweeps (15p)
        for sw in [s for s in sweeps if s["idx"] >= len(df)-5]:
            if sw["type"] == "SSL_SWEEP":
                bull_score += 15; conf_bull += 1
                reasons_bull.append("SSL sweep — yükseliş dönüşü beklenir")
            elif sw["type"] == "BSL_SWEEP":
                bear_score += 15; conf_bear += 1
                reasons_bear.append("BSL sweep — düşüş dönüşü beklenir")

        # 7. Inducement (5p)
        if any(i["type"] == "BULLISH_INDUCEMENT" for i in inducements):
            bull_score += 5
            reasons_bull.append("Bullish Inducement")
        if any(i["type"] == "BEARISH_INDUCEMENT" for i in inducements):
            bear_score += 5
            reasons_bear.append("Bearish Inducement")

        # 8. OTE (10p)
        if ote:
            if ote["direction"] == "LONG" and ote["ote_bottom"] <= cur_price <= ote["ote_top"]:
                bull_score += 10; conf_bull += 1
                reasons_bull.append("Fiyat OTE alım bölgesinde (Fib 0.618-0.786)")
            elif ote["direction"] == "SHORT" and ote["ote_bottom"] <= cur_price <= ote["ote_top"]:
                bear_score += 10; conf_bear += 1
                reasons_bear.append("Fiyat OTE satış bölgesinde (Fib 0.618-0.786)")

        # 9. Premium/Discount (10p)
        if pd_zone["zone"] == "DISCOUNT" and pd_zone["zone_pct"] > 60:
            bull_score += 10; conf_bull += 1
            reasons_bull.append(f"Discount bölgesi (%{pd_zone['zone_pct']})")
        elif pd_zone["zone"] == "PREMIUM" and pd_zone["zone_pct"] > 60:
            bear_score += 10; conf_bear += 1
            reasons_bear.append(f"Premium bölgesi (%{pd_zone['zone_pct']})")

        # 10. Kill Zone (5p bonus)
        if kill["is_kill_zone"]:
            if bull_score > bear_score:
                bull_score += 5
                reasons_bull.append(f"{kill['active_zone']} Kill Zone aktif")
            elif bear_score > bull_score:
                bear_score += 5
                reasons_bear.append(f"{kill['active_zone']} Kill Zone aktif")

        # 11. Silver Bullet (5p)
        if silver_bullet["is_active"] and (bull_fvg or bear_fvg):
            if bull_score > bear_score:
                bull_score += 5
                reasons_bull.append("Silver Bullet + FVG confluence")
            else:
                bear_score += 5
                reasons_bear.append("Silver Bullet + FVG confluence")

        # 12. AMD (15p)
        if amd:
            if amd["direction"] == "LONG":
                bull_score += 15; conf_bull += 1
                reasons_bull.append("AMD Bullish pattern")
            elif amd["direction"] == "SHORT":
                bear_score += 15; conf_bear += 1
                reasons_bear.append("AMD Bearish pattern")

        # 13. Judas Swing (15p)
        if judas:
            if "BULLISH" in judas["type"]:
                bull_score += 15; conf_bull += 1
                reasons_bull.append("Judas Swing — gerçek yön yukarı")
            elif "BEARISH" in judas["type"]:
                bear_score += 15; conf_bear += 1
                reasons_bear.append("Judas Swing — gerçek yön aşağı")

        # 14. Daily Bias (15p)
        if daily_bias["bias"] == "BULLISH":
            bull_score += 15; conf_bull += 1
            reasons_bull.append(f"Günlük Bias: YÜKSELİŞ")
        elif daily_bias["bias"] == "BEARISH":
            bear_score += 15; conf_bear += 1
            reasons_bear.append(f"Günlük Bias: DÜŞÜŞ")

        # 15. Asian Breakout (5p)
        if asian_bo and asian_bo["type"] != "INSIDE_RANGE":
            if "BULLISH" in asian_bo["type"]:
                bull_score += 5
                reasons_bull.append("Asian Range yukarı kırıldı")
            elif "BEARISH" in asian_bo["type"]:
                bear_score += 5
                reasons_bear.append("Asian Range aşağı kırıldı")

        # 16. Smart Money Trap (15p)
        if smt:
            if smt["type"] == "BEAR_TRAP":
                bull_score += 15; conf_bull += 1
                reasons_bull.append(f"Smart Money Trap → LONG")
            elif smt["type"] == "BULL_TRAP":
                bear_score += 15; conf_bear += 1
                reasons_bear.append(f"Smart Money Trap → SHORT")

        # RSI konfirmasyon (5p)
        if indicators["rsi"] < 35:
            bull_score += 5
            reasons_bull.append(f"RSI aşırı satım ({indicators['rsi']:.1f})")
        elif indicators["rsi"] > 65:
            bear_score += 5
            reasons_bear.append(f"RSI aşırı alım ({indicators['rsi']:.1f})")

        # ═══ CEZALAR ═══
        if not kill["is_kill_zone"]:
            if bull_score > bear_score:
                bull_score -= 10
                reasons_bull.append("Kill Zone dışında — güvenilirlik düşük")
            elif bear_score > bull_score:
                bear_score -= 10
                reasons_bear.append("Kill Zone dışında — güvenilirlik düşük")

        if pd_zone["zone"] == "PREMIUM" and pd_zone["zone_pct"] > 75:
            bull_score -= 15
            reasons_bull.append("Premium bölgede ALIŞ riski yüksek")
        elif pd_zone["zone"] == "DISCOUNT" and pd_zone["zone_pct"] > 75:
            bear_score -= 15
            reasons_bear.append("Discount bölgede SATIŞ riski yüksek")

        if daily_bias["bias"] == "BEARISH" and bull_score > bear_score:
            bull_score -= 10
            reasons_bull.append("Günlük trend düşüşte — ALIŞ riskli")
        elif daily_bias["bias"] == "BULLISH" and bear_score > bull_score:
            bear_score -= 10
            reasons_bear.append("Günlük trend yükselişte — SATIŞ riskli")

        # ═══ SİNYAL KARARI ═══
        net_score = bull_score - bear_score
        min_conf_strong = ICT_PARAMS.get("min_confluence_strong", 5)
        min_score_strong = ICT_PARAMS.get("min_score_strong", 55)
        min_conf_normal = ICT_PARAMS.get("min_confluence_normal", 3)
        min_score_normal = ICT_PARAMS.get("min_score_normal", 30)

        if net_score >= min_score_strong and conf_bull >= min_conf_strong:
            signal = "STRONG_LONG"
        elif net_score >= min_score_normal and conf_bull >= min_conf_normal:
            signal = "LONG"
        elif net_score <= -min_score_strong and conf_bear >= min_conf_strong:
            signal = "STRONG_SHORT"
        elif net_score <= -min_score_normal and conf_bear >= min_conf_normal:
            signal = "SHORT"
        else:
            signal = "WAIT"

        # SL/TP hesapla
        atr = indicators["atr"]
        sl_tp = self._calc_sl_tp(signal, cur_price, atr, df, obs)

        return {
            "instrument": instrument_key,
            "name": inst["name"],
            "price": cur_price,
            "timeframe": timeframe,
            "signal": signal,
            "net_score": net_score,
            "bull_score": bull_score,
            "bear_score": bear_score,
            "conf_bull": conf_bull,
            "conf_bear": conf_bear,
            "reasons_bull": reasons_bull,
            "reasons_bear": reasons_bear,
            "sl_tp": sl_tp,
            "market_structure": ms,
            "order_blocks": [ob for ob in obs if not ob["mitigated"]][:5],
            "breaker_blocks": breakers,
            "fvg": {"bull": len(bull_fvg), "bear": len(bear_fvg), "active": active_fvgs[:6]},
            "displacement": displacements,
            "liquidity_sweeps": sweeps,
            "inducement": inducements,
            "ote": ote,
            "premium_discount": pd_zone,
            "kill_zones": kill,
            "silver_bullet": silver_bullet,
            "amd": amd,
            "judas": judas,
            "daily_bias": daily_bias,
            "asian_breakout": asian_bo,
            "smart_money_trap": smt,
            "indicators": indicators,
            "timestamp": datetime.now().isoformat(),
        }

    def _calc_sl_tp(self, signal, cur_price, atr, df, obs):
        """SL/TP hesapla: ATR + Swing + OB bazlı"""
        if signal == "WAIT" or atr == 0:
            return None

        sl_mult = ICT_PARAMS.get("sl_atr_mult", 1.2)
        tp1_rr = ICT_PARAMS.get("tp1_rr", 1.8)
        tp2_rr = ICT_PARAMS.get("tp2_rr", 3.0)

        swing_lookback = min(20, len(df) - 1)
        recent_high = float(df["high"].iloc[-swing_lookback:].max())
        recent_low = float(df["low"].iloc[-swing_lookback:].min())

        active_obs = [o for o in obs if not o.get("mitigated", False)]
        ob_top = active_obs[-1].get("high") if active_obs else None
        ob_bottom = active_obs[-1].get("low") if active_obs else None

        if signal in ("STRONG_LONG", "LONG"):
            atr_sl = cur_price - atr * sl_mult
            swing_sl = recent_low - atr * 0.15
            candidates = [atr_sl, swing_sl]
            if ob_bottom:
                candidates.append(ob_bottom - atr * 0.1)
            sl = round(max(candidates), 5)
            if abs(cur_price - sl) < atr * 0.4:
                sl = round(atr_sl, 5)
            risk = abs(cur_price - sl)
            tp1 = round(cur_price + risk * tp1_rr, 5)
            tp2 = round(cur_price + risk * tp2_rr, 5)
        else:
            atr_sl = cur_price + atr * sl_mult
            swing_sl = recent_high + atr * 0.15
            candidates = [atr_sl, swing_sl]
            if ob_top:
                candidates.append(ob_top + atr * 0.1)
            sl = round(min(candidates), 5)
            if abs(sl - cur_price) < atr * 0.4:
                sl = round(atr_sl, 5)
            risk = abs(sl - cur_price)
            tp1 = round(cur_price - risk * tp1_rr, 5)
            tp2 = round(cur_price - risk * tp2_rr, 5)

        rr1 = round(abs(tp1 - cur_price) / risk, 2) if risk > 0 else 0
        rr2 = round(abs(tp2 - cur_price) / risk, 2) if risk > 0 else 0

        return {"sl": sl, "tp1": tp1, "tp2": tp2,
                "direction": "LONG" if "LONG" in signal else "SHORT",
                "rr1": rr1, "rr2": rr2}

    def scan_all(self, timeframe="1h"):
        """Tüm enstrümanları tara"""
        results = []
        for key in FOREX_INSTRUMENTS:
            try:
                sig = self.calculate_confluence(key, timeframe)
                if "error" not in sig:
                    results.append(sig)
            except Exception as e:
                logger.error(f"Tarama hatası ({key}): {e}")
        return results


# Singleton
ict_engine = ICTEngine()
