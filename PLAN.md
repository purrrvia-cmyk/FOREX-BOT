# FOREX ICT/SMC Trading Bot — Mimari Plan

## 🎯 Hedef
$50 sermaye ile major forex paritelerde ICT/SMC stratejisi uygulayan,
Kill Zone bazlı işlem açan, dolar bazlı PnL gösteren, kendi kendine
öğrenen, mobil uyumlu (PWA) trading botu.

---

## 📁 Dosya Yapısı

```
FOREX-BOT/
│
├── main.py                     ← Tek giriş noktası (python main.py)
├── requirements.txt
├── .gitignore
│
├── config/
│   ├── __init__.py
│   ├── instruments.py          ← Major pariteler (EUR/USD, GBP/USD, XAU/USD vs.)
│   ├── ict_params.py           ← ICT strateji parametreleri
│   ├── kill_zones.py           ← Kill Zone & Silver Bullet saatleri
│   ├── capital.py              ← Sermaye ayarları ($50, kaldıraç, risk%)
│   └── news.py                 ← Haber kaynakları, keyword listeleri
│
├── core/                       ← ICT Analiz Motoru (16 konsept)
│   ├── __init__.py
│   ├── data_feed.py            ← yfinance veri çekme + cache
│   ├── indicators.py           ← RSI, EMA, ATR hesaplama
│   ├── market_structure.py     ← BOS, CHoCH, Swing H/L
│   ├── order_blocks.py         ← OB, Breaker Block, FVG, Displacement
│   ├── liquidity.py            ← Sweep, Inducement, Smart Money Trap
│   ├── sessions.py             ← Kill Zone, Silver Bullet, AMD, Judas
│   ├── confluence.py           ← 16 konsept birleştirme + skor
│   └── sl_tp.py                ← SL/TP hesaplama (ATR + Swing + OB)
│
├── trading/                    ← İşlem Yönetimi
│   ├── __init__.py
│   ├── signal_generator.py     ← Multi-TF sinyal (1D→4H→1H→15M→5M)
│   ├── capital_manager.py      ← $50 sermaye, lot hesabı, dolar PnL
│   ├── trade_manager.py        ← Pozisyon yönetimi (BE, trailing)
│   └── risk_manager.py         ← Max trade, cooldown, yön limiti
│
├── intelligence/               ← Haber + Öğrenme
│   ├── __init__.py
│   ├── news_fetcher.py         ← RSS haber çekme + sentiment
│   ├── economic_calendar.py    ← Ekonomik takvim (NFP, FOMC vs.)
│   └── learning_engine.py      ← Kendi kendine öğrenme sistemi
│
├── database/                   ← Veritabanı
│   ├── __init__.py
│   ├── connection.py           ← SQLite bağlantı + WAL mode
│   ├── models.py               ← Tablo tanımları (signals, trades, capital, learning)
│   └── queries.py              ← CRUD operasyonları
│
└── web/                        ← Web Arayüz (PWA)
    ├── __init__.py
    ├── app.py                  ← Flask app oluşturma
    ├── routes.py               ← REST API endpoint'leri
    ├── websocket.py            ← SocketIO gerçek zamanlı olaylar
    ├── templates/
    │   └── index.html          ← Tek sayfa uygulama (SPA)
    └── static/
        ├── manifest.json       ← PWA manifest (mobil uygulama)
        ├── sw.js               ← Service Worker (offline destek)
        ├── css/
        │   └── app.css         ← Modern dark theme
        ├── js/
        │   ├── app.js          ← Ana uygulama mantığı
        │   ├── charts.js       ← Grafik çizimi
        │   └── utils.js        ← Yardımcı fonksiyonlar
        └── icons/
            ├── icon-192.png    ← PWA ikon
            └── icon-512.png    ← PWA ikon büyük
```

---

## 💰 Sermaye Sistemi

| Parametre | Değer |
|-----------|-------|
| Başlangıç sermayesi | $50.00 |
| Kaldıraç | 1:2 |
| Efektif güç | $100.00 |
| Trade başına risk | %2 = $1.00 |
| Max eşzamanlı trade | 3 |
| Max aynı yön | 2 |
| Cooldown | 30 dakika |

### Lot Size Hesabı
```
lot_size = risk_amount / (sl_distance_pips × pip_value)

Örnek EURUSD:
  Risk = $1.00
  SL = 25 pip
  Pip value = $0.10 (micro lot)
  Lot = $1.00 / (25 × $0.10) = 0.40 micro lot = 0.004 standart lot
```

### PnL Gösterimi (Dolar bazlı)
- ❌ "~+45.2 pip" → böyle göstermeyecek
- ✅ "+$1.80" → böyle gösterecek
- Dashboard: "Bakiye: $52.30 | Bugün: +$2.30 | Toplam: +$4.60"

---

## 📊 Pariteler (Major + Gold + Silver)

| Parite | Kategori | Pip Size | Pip Value (micro) |
|--------|----------|----------|-------------------|
| EUR/USD | Major | 0.0001 | $0.10 |
| GBP/USD | Major | 0.0001 | $0.10 |
| USD/JPY | Major | 0.01 | ~$0.07 |
| USD/CHF | Major | 0.0001 | ~$0.10 |
| AUD/USD | Major | 0.0001 | $0.10 |
| NZD/USD | Major | 0.0001 | $0.10 |
| USD/CAD | Major | 0.0001 | ~$0.08 |
| XAU/USD | Altın | 0.01 | $0.10 |
| XAG/USD | Gümüş | 0.001 | $0.05 |

---

## ⏰ Kill Zone Sistemi

### Ana Kill Zone'lar (UTC)
| Session | UTC Saat | Açıklama |  
|---------|----------|----------|
| Asia | 00:00-06:00 | Range oluşumu, düşük volatilite |
| London | 07:00-10:00 | Trend başlangıcı, yüksek likidite |
| New York | 12:00-15:00 | London overlap, max volatilite |

### Silver Bullet Pencereleri (UTC)
| İsim | UTC Saat |
|------|----------|
| London SB | 08:00-09:00 |
| NY AM SB | 15:00-16:00 |
| NY PM SB | 19:00-20:00 |

### İşlem Kuralı
```
Kill Zone AKTİF → Minimum 3 confluence ile işlem aç
Kill Zone DIŞI  → İşlem AÇMA (sadece analiz yap)

İstisna: Kill Zone dışında 6+ confluence + STRONG sinyal → işlem açılabilir
```

---

## 🔍 Multi-TF Analiz Zinciri

```
1D (Daily)  → Genel trend yönü (BULLISH/BEARISH/NEUTRAL)
     ↓
4H           → Yapı teyidi (BOS/CHoCH aynı yönde mi?)
     ↓
1H           → Giriş bölgesi (OB, FVG, OTE tespiti)
     ↓
15M          → Hassas Giriş (FVG/OB refinement)
     ↓
5M           → Hassas Giriş son onay (displacement teyidi)
```

### Karar Mantığı
```
Daily BULLISH + 4H BULLISH + 1H FVG/OB = LONG hazırlık
  → 15M/5M'de BULLISH displacement + KZ aktif → LONG AÇ

Daily BEARISH + 4H BEARISH + 1H FVG/OB = SHORT hazırlık
  → 15M/5M'de BEARISH displacement + KZ aktif → SHORT AÇ

Daily NEUTRAL veya TF'ler uyumsuz → WAIT
```

---

## 🧠 Öğrenme Sistemi

### Her trade sonrası kaydedilen veriler:
- Hangi Kill Zone'da açıldı
- Hangi ICT konseptleri tetikledi (16 konsept listesi)
- Haber durumu (yüksek etki var mıydı)
- Multi-TF uyumu (kaç TF aynı yöndeydi)
- SL/TP mesafesi
- Sonuç (WIN/LOSS)
- Süre (ne kadar açık kaldı)
- Session (Asia/London/NY)

### Haftalık analiz:
- En çok kazandıran parite
- En çok kaybettiren parite
- En başarılı Kill Zone
- En başarılı konsept kombinasyonu
- Win rate < %30 olan pattern → geçici devre dışı

### Güven skoru adaptasyonu:
```
Pattern win_rate > %60 → confluence bonus +5
Pattern win_rate < %35 → confluence penalty -10
Pattern win_rate < %20 → pattern devre dışı (30 gün)
```

---

## 📱 PWA (Mobil Uygulama)

### Özellikler
- Telefona "Ana Ekrana Ekle" ile yüklenebilir
- Offline destek (service worker)
- Push notification desteği (sinyal gelince)
- Responsive tasarım (mobil öncelikli)
- Dark mode (varsayılan)
- Dokunmatik uyumlu büyük butonlar

### Sayfalar
1. **Dashboard** — Bakiye, açık pozisyonlar, günlük PnL
2. **Sinyaller** — Canlı sinyal listesi, confluence detayı
3. **İşlemler** — Açık ve geçmiş işlemler ($PnL)
4. **Analiz** — Parite detay analizi, ICT konseptleri
5. **Haberler** — Canlı haberler + ekonomik takvim
6. **Performans** — Günlük/haftalık/aylık grafik, öğrenme raporu
7. **Ayarlar** — Sermaye, risk, bildirim ayarları

### UI Tema
- Arka plan: Koyu siyah (#0a0a0f) → gradient (#12121a)
- Kartlar: Glassmorphism (yarı saydam, blur)
- Accent: Yeşil (#00d47e) kazanç, Kırmızı (#ff4757) kayıp
- Font: Inter (UI) + JetBrains Mono (sayılar)
- Animasyon: Smooth geçişler, glow efektler

---

## 🔄 Tarama Döngüsü

```
Her 2 dakikada bir:
  1. Kill Zone kontrolü → aktif mi?
  2. Haber kontrolü → yüksek etki var mı?
  3. 8 pariteyi tara (1D → 4H → 1H → 15M)
  4. Confluence skoru hesapla
  5. KZ aktif + skor yeterli + haber uygun → SİNYAL
  6. Sinyal varsa → lot size hesapla → trade aç
  7. Açık trade'leri güncelle (BE, trailing, SL/TP hit)
  8. Learning engine'e kaydet

Her 30 saniyede:
  - Açık trade'lerin fiyat güncellemesi
  - SL/TP hit kontrolü
  - BE / trailing stop güncelleme
```

---

## ⚡ Teknoloji

| Bileşen | Teknoloji |
|---------|-----------|
| Backend | Python 3.13 + Flask + SocketIO |
| Database | SQLite3 (WAL mode) |
| Veri | yfinance (gerçek zamanlı) |
| Haberler | RSS (ForexLive, FXStreet) |
| Frontend | HTML5 + CSS3 + Vanilla JS |
| Mobil | PWA (Progressive Web App) |
| Grafikler | Chart.js (lightweight) |

---

## ✅ Yapılacaklar Sırası

1. [ ] config/ → Tüm konfigürasyon dosyaları
2. [ ] database/ → Tablo yapıları + CRUD
3. [ ] core/ → ICT analiz motoru (16 konsept)
4. [ ] trading/ → Sinyal, sermaye, trade, risk yönetimi
5. [ ] intelligence/ → Haber, takvim, öğrenme
6. [ ] web/ → Flask + API + WebSocket
7. [ ] web/static/ → PWA + UI + CSS + JS
8. [ ] main.py → Giriş noktası
9. [ ] Test → Çalıştır, doğrula
10. [ ] Git → Commit + Push
