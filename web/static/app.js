/* ═══════════════════════════════════════════════
   FOREX-BOT v2.0 — Main Application JS
   ═══════════════════════════════════════════════ */

// ── Socket.IO ──────────────────────────────
const socket = io();
let balanceChart = null;
let analysisChart = null;

socket.on("connect", () => {
    document.getElementById("ws-indicator").classList.replace("offline", "online");
    socket.emit("request_status");
    loadDashboard();
});
socket.on("disconnect", () => {
    document.getElementById("ws-indicator").classList.replace("online", "offline");
});

socket.on("status_update", (data) => updateStatus(data));
socket.on("scan_result", (data) => displayScanResult(data));
socket.on("price_update", (data) => updatePrice(data));
socket.on("new_signal", (data) => addSignalToList(data));
socket.on("trade_update", (data) => loadTrades());

// ── Tabs ────────────────────────────────────
document.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", () => {
        document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
        document.querySelectorAll(".tab-content").forEach(t => t.classList.remove("active"));
        tab.classList.add("active");
        const target = document.getElementById("tab-" + tab.dataset.tab);
        if (target) target.classList.add("active");

        if (tab.dataset.tab === "trades") loadTrades();
        if (tab.dataset.tab === "signals") loadSignals();
        if (tab.dataset.tab === "learning") loadLearning();
        if (tab.dataset.tab === "analysis") initAnalysis();
    });
});

// ── Dashboard ───────────────────────────────
async function loadDashboard() {
    try {
        const [status, instruments] = await Promise.all([
            fetch("/api/status").then(r => r.json()),
            fetch("/api/instruments").then(r => r.json())
        ]);
        updateStatus(status);
        renderInstruments(instruments);
        loadBalanceChart();
    } catch (e) {
        console.error("Dashboard yükleme hatası:", e);
    }
}

function updateStatus(data) {
    if (data.capital) {
        document.getElementById("stat-balance").textContent = "$" + (data.capital.balance || 50).toFixed(2);
        document.getElementById("balance-badge").textContent = "$" + (data.capital.balance || 50).toFixed(2);
    }
    if (data.trade_stats) {
        const s = data.trade_stats;
        document.getElementById("stat-winrate").textContent = (s.winrate || 0).toFixed(0) + "%";
        document.getElementById("stat-open-trades").textContent = s.open_trades || 0;
        document.getElementById("stat-daily-pnl").textContent = "$" + (s.daily_pnl || 0).toFixed(2);
        const pnlEl = document.getElementById("stat-daily-pnl");
        pnlEl.style.color = (s.daily_pnl || 0) >= 0 ? "var(--green)" : "var(--red)";
    }
    if (data.kill_zone) {
        updateKillZone(data.kill_zone);
    }
}

function updateKillZone(kz) {
    const badge = document.getElementById("kz-badge");
    const text = document.getElementById("kz-status-text");
    const timeline = document.getElementById("kz-timeline");

    if (kz.is_kill_zone) {
        badge.className = "badge badge-gold";
        badge.textContent = "KZ: " + kz.active_zone;
        text.className = "badge badge-gold";
        text.textContent = kz.active_zone + " AKTİF";
    } else {
        badge.className = "badge badge-dim";
        badge.textContent = "KZ: Pasif";
        text.className = "badge badge-dim";
        text.textContent = kz.next_kz || "Bekleniyor";
    }

    if (kz.zones && timeline) {
        timeline.innerHTML = kz.zones.map(z =>
            `<div class="kz-block ${z.active ? 'active' : ''}">
                <div class="kz-label">${z.label}</div>
                <div class="kz-time">${z.active ? z.remaining_min + ' dk' : ''}</div>
            </div>`
        ).join("");
    }
}

function renderInstruments(instruments) {
    const grid = document.getElementById("instrument-grid");
    if (!grid) return;
    grid.innerHTML = instruments.map(inst => {
        const p = inst.price || {};
        const last = p.last || 0;
        const prev = p.prev_close || last;
        const change = prev ? ((last - prev) / prev * 100) : 0;
        const dir = change >= 0 ? "up" : "down";
        return `<div class="inst-card" onclick="quickScan('${inst.key}')">
            <div class="inst-header">
                <span class="inst-name">${inst.key}</span>
                <span class="inst-icon">${inst.icon}</span>
            </div>
            <div class="inst-price" id="price-${inst.key}">${last.toFixed(inst.cat === 'metal' ? 2 : 5)}</div>
            <div class="inst-change ${dir}">${change >= 0 ? '+' : ''}${change.toFixed(2)}%</div>
        </div>`;
    }).join("");
}

function updatePrice(data) {
    const el = document.getElementById("price-" + data.instrument);
    if (el && data.price) el.textContent = data.price.last.toFixed(5);
}

// ── Balance Chart ───────────────────────────
async function loadBalanceChart() {
    try {
        const data = await fetch("/api/balance_history").then(r => r.json());
        const container = document.getElementById("balance-chart");
        if (!container || !data.length) return;
        container.innerHTML = "";

        balanceChart = LightweightCharts.createChart(container, {
            width: container.clientWidth, height: 250,
            layout: { background: { color: "transparent" }, textColor: "#9ca3af" },
            grid: { vertLines: { color: "rgba(255,255,255,0.03)" }, horzLines: { color: "rgba(255,255,255,0.03)" } },
            crosshair: { mode: 0 },
            rightPriceScale: { borderColor: "rgba(255,255,255,0.1)" },
            timeScale: { borderColor: "rgba(255,255,255,0.1)" },
        });

        const series = balanceChart.addAreaSeries({
            topColor: "rgba(16,185,129,0.3)", bottomColor: "rgba(16,185,129,0.01)",
            lineColor: "#10b981", lineWidth: 2,
        });

        const chartData = data.reverse().map((d, i) => ({
            time: Math.floor(new Date(d.created_at || Date.now()).getTime() / 1000) + i,
            value: d.balance
        }));
        if (chartData.length) series.setData(chartData);

        new ResizeObserver(() => {
            balanceChart.applyOptions({ width: container.clientWidth });
        }).observe(container);
    } catch (e) {
        console.error("Chart hatası:", e);
    }
}

// ── Signals ─────────────────────────────────
async function scanAll() {
    const list = document.getElementById("signal-list");
    list.innerHTML = '<div class="empty-state loading">Taranıyor...</div>';
    try {
        const results = await fetch("/api/scan_all").then(r => r.json());
        renderSignals(results);
    } catch (e) {
        list.innerHTML = '<div class="empty-state">Hata: ' + e.message + '</div>';
    }
}

async function loadSignals() {
    try {
        const data = await fetch("/api/signals?limit=30").then(r => r.json());
        // Signals from DB
    } catch (e) { console.error(e); }
}

function renderSignals(signals) {
    const list = document.getElementById("signal-list");
    if (!signals.length) {
        list.innerHTML = '<div class="empty-state">Sinyal bulunamadı</div>';
        return;
    }
    list.innerHTML = signals.map(s => {
        const sig = s.final_signal || "WAIT";
        const cls = sig.includes("LONG") ? "long" : (sig.includes("SHORT") ? "short" : "wait");
        const dirCls = cls;
        const score = Math.abs(s.final_score || 0);
        const reasons = s.entry_data ? (
            (s.entry_data.reasons_bull || []).concat(s.entry_data.reasons_bear || [])
        ).slice(0, 5).join(" • ") : "";
        const sltp = s.entry_data?.sl_tp;
        return `<div class="signal-item ${cls}">
            <div class="signal-top">
                <span class="signal-pair">${s.instrument} <small style="color:var(--text-dim)">${s.name || ''}</small></span>
                <span class="signal-dir ${dirCls}">${sig}</span>
            </div>
            <div class="signal-meta">
                <span>Skor: ${score}</span>
                <span>TF: ${s.entry_tf || '-'}</span>
                <span>Bias: ${s.daily_bias?.bias || '-'}</span>
                ${sltp ? `<span>SL: ${sltp.sl} TP: ${sltp.tp1}</span>` : ''}
            </div>
            ${reasons ? `<div class="signal-reasons">${reasons}</div>` : ''}
        </div>`;
    }).join("");
}

function addSignalToList(data) {
    renderSignals([data]);
}

function quickScan(key) {
    socket.emit("request_scan", { instrument: key });
}

// ── Trades ──────────────────────────────────
async function loadTrades() {
    try {
        const [open, all] = await Promise.all([
            fetch("/api/trades?status=open").then(r => r.json()),
            fetch("/api/trades?limit=30").then(r => r.json())
        ]);
        renderOpenTrades(open);
        renderTradeHistory(all);
    } catch (e) { console.error(e); }
}

function renderOpenTrades(trades) {
    const el = document.getElementById("open-trades-list");
    if (!trades.length) {
        el.innerHTML = '<div class="empty-state">Açık işlem yok</div>';
        return;
    }
    el.innerHTML = trades.map(t =>
        `<div class="trade-item">
            <div>
                <div class="trade-pair">${t.instrument} <span class="badge ${t.direction === 'LONG' ? 'badge-green' : 'badge-red'}">${t.direction}</span></div>
                <small style="color:var(--text-dim)">@ ${t.entry_price} | SL: ${t.sl} | TP: ${t.tp}</small>
            </div>
            <div class="trade-pnl">${t.lot_size || 0.01} lot</div>
        </div>`
    ).join("");
}

function renderTradeHistory(trades) {
    const el = document.getElementById("trade-history-list");
    const closed = trades.filter(t => t.status !== "OPEN");
    if (!closed.length) {
        el.innerHTML = '<div class="empty-state">Henüz kapanan işlem yok</div>';
        return;
    }
    el.innerHTML = closed.map(t => {
        const pnl = t.pnl_usd || 0;
        const cls = pnl >= 0 ? "positive" : "negative";
        return `<div class="trade-item">
            <div>
                <div class="trade-pair">${t.instrument} ${t.direction}</div>
                <small style="color:var(--text-dim)">${t.close_reason || ''}</small>
            </div>
            <div class="trade-pnl ${cls}">$${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}</div>
        </div>`;
    }).join("");
}

// ── Analysis ────────────────────────────────
async function initAnalysis() {
    const sel = document.getElementById("analysis-pair");
    if (sel.options.length <= 1) {
        try {
            const insts = await fetch("/api/instruments").then(r => r.json());
            sel.innerHTML = insts.map(i => `<option value="${i.key}">${i.key}</option>`).join("");
        } catch (e) { console.error(e); }
    }
    analyzeSelected();
}

async function analyzeSelected() {
    const key = document.getElementById("analysis-pair").value;
    if (!key) return;
    const details = document.getElementById("analysis-details");
    details.innerHTML = '<div class="loading">Analiz ediliyor...</div>';
    try {
        const data = await fetch("/api/scan/" + key).then(r => r.json());
        renderAnalysis(data);
    } catch (e) {
        details.innerHTML = '<div class="empty-state">Hata: ' + e.message + '</div>';
    }
}

function renderAnalysis(data) {
    const details = document.getElementById("analysis-details");
    const sig = data.final_signal || data.signal || "WAIT";
    const score = data.final_score || data.net_score || 0;
    const sltp = data.sl_tp || data.entry_data?.sl_tp;

    let html = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin:12px 0">
            <span style="font-size:1.2rem;font-weight:700">${data.instrument}</span>
            <span class="signal-dir ${sig.includes('LONG') ? 'long' : (sig.includes('SHORT') ? 'short' : 'wait')}">${sig} (${Math.abs(score)})</span>
        </div>`;

    // Multi-TF summary
    if (data.analysis) {
        html += '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px">';
        for (const [tf, a] of Object.entries(data.analysis)) {
            const s = a.signal || "?";
            const c = s.includes("LONG") ? "badge-green" : (s.includes("SHORT") ? "badge-red" : "badge-dim");
            html += `<span class="badge ${c}">${tf}: ${s} (${a.score || 0})</span>`;
        }
        html += '</div>';
    }

    // SL/TP
    if (sltp) {
        html += `<div class="card" style="margin:8px 0;padding:8px">
            <div style="font-size:0.8rem;color:var(--text-dim)">SL: ${sltp.sl} | TP1: ${sltp.tp1} | TP2: ${sltp.tp2} | RR: 1:${sltp.rr1}</div>
        </div>`;
    }

    // Reasons
    const ed = data.entry_data || data;
    const bulls = ed.reasons_bull || [];
    const bears = ed.reasons_bear || [];
    if (bulls.length || bears.length) {
        html += '<div class="analysis-concepts">';
        bulls.forEach(r => { html += `<span class="concept-tag bull">🟢 ${r}</span>`; });
        bears.forEach(r => { html += `<span class="concept-tag bear">🔴 ${r}</span>`; });
        html += '</div>';
    }

    details.innerHTML = html;
}

// ── Learning ────────────────────────────────
async function loadLearning() {
    try {
        const data = await fetch("/api/learning").then(r => r.json());
        renderLearning(data);
    } catch (e) { console.error(e); }
}

function renderLearning(data) {
    const summary = document.getElementById("learning-summary");
    const scores = document.getElementById("pattern-scores");

    summary.innerHTML = `
        <div class="card-row">
            <div class="stat-card card"><div class="stat-label">Toplam Analiz</div><div class="stat-value">${data.total_analyzed || 0}</div></div>
            <div class="stat-card card"><div class="stat-label">Kazanma</div><div class="stat-value">${data.total_wins || 0}</div></div>
            <div class="stat-card card"><div class="stat-label">Toplam P&L</div><div class="stat-value">$${(data.total_pnl || 0).toFixed(2)}</div></div>
            <div class="stat-card card"><div class="stat-label">Devre Dışı</div><div class="stat-value">${data.disabled_count || 0}</div></div>
        </div>`;

    // KZ Performance
    if (data.kz_performance?.length) {
        summary.innerHTML += '<h4 style="margin:10px 0 6px;font-size:0.85rem">Kill Zone Performansı</h4>';
        summary.innerHTML += data.kz_performance.map(k =>
            `<div class="trade-item"><span>${k.kill_zone || 'Bilinmiyor'}</span>
            <span>${k.wins}/${k.cnt} kazanma | $${(k.total_pnl || 0).toFixed(2)}</span></div>`
        ).join("");
    }

    // Best/Worst patterns
    let pHtml = '<div class="learn-grid">';
    if (data.best_patterns?.length) {
        pHtml += '<h4 style="grid-column:1/-1;font-size:0.85rem;color:var(--green)">En İyi Konseptler</h4>';
        data.best_patterns.forEach(p => {
            pHtml += `<div class="learn-card">
                <div class="learn-pattern">${p.pattern}</div>
                <div class="learn-stats">WR: %${p.winrate} | ${p.total_trades} işlem | $${(p.total_pnl || 0).toFixed(2)}</div>
                <div class="learn-bar"><div class="learn-bar-fill" style="width:${p.winrate}%;background:var(--green)"></div></div>
            </div>`;
        });
    }
    if (data.worst_patterns?.length) {
        pHtml += '<h4 style="grid-column:1/-1;font-size:0.85rem;color:var(--red);margin-top:8px">En Kötü Konseptler</h4>';
        data.worst_patterns.forEach(p => {
            pHtml += `<div class="learn-card">
                <div class="learn-pattern">${p.pattern}</div>
                <div class="learn-stats">WR: %${p.winrate} | ${p.total_trades} işlem | $${(p.total_pnl || 0).toFixed(2)}</div>
                <div class="learn-bar"><div class="learn-bar-fill" style="width:${p.winrate}%;background:var(--red)"></div></div>
            </div>`;
        });
    }
    pHtml += '</div>';
    scores.innerHTML = pHtml;
}

// ── Refresh ─────────────────────────────────
async function refreshPrices() {
    try {
        const instruments = await fetch("/api/instruments").then(r => r.json());
        renderInstruments(instruments);
    } catch (e) { console.error(e); }
}

// Auto-refresh every 30 seconds
setInterval(() => {
    socket.emit("request_status");
    refreshPrices();
}, 30000);

// ── PWA ─────────────────────────────────────
if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(e => console.log("SW:", e));
}
