/**
 * HUNTER RADAR & RALLYGOOD — JAVASCRIPT DASHBOARD ENGINE
 * Mengelola rendering data 7 hari terakhir & 1 bulan khusus 3-Dot Green
 */

const CHART_BASE_URL = "https://www.tradingview.com/chart/6B2fiCnc/";

let appData = {
  last_updated: "-",
  daily_scans: {},
  vip_3dot_history: []
};

let currentMode = "daily"; // 'daily' | 'vip'
let selectedDate = null;
let searchQuery = "";
let activeFilter = "all"; // 'all' | '3dot' | '2dot' | 'golden' | 'smc'

// Inisialisasi saat halaman selesai dimuat
document.addEventListener("DOMContentLoaded", async () => {
  await loadDatabase();
});

// Load database JSON
async function loadDatabase() {
  try {
    const response = await fetch("data/history.json?v=" + Date.now());
    if (!response.ok) throw new Error("Gagal mengambil data/history.json");
    appData = await response.json();
    
    // Update badge last updated
    if (appData.last_updated) {
      document.getElementById("lastUpdatedText").innerText = "Update: " + appData.last_updated;
    }
    
    // Update VIP badge count
    const vipCount = (appData.vip_3dot_history || []).length;
    document.getElementById("vipBadgeCount").innerText = vipCount;

    // Pilih tanggal terbaru secara default
    const availableDates = Object.keys(appData.daily_scans || {}).sort().reverse();
    if (availableDates.length > 0) {
      selectedDate = availableDates[0];
    }

    renderDatePills();
    renderView();
  } catch (error) {
    console.error("Error loading data:", error);
    document.getElementById("stocksGrid").innerHTML = `
      <div class="empty-state">
        <div style="font-size: 40px; margin-bottom: 12px;">⚠️</div>
        <h3>Gagal Memuat Database Saham</h3>
        <p style="margin-top: 8px;">File data/history.json belum tersedia atau belum selesai dibuat oleh bot.</p>
      </div>
    `;
  }
}

// Render Date Pills (7 Hari Terakhir)
function renderDatePills() {
  const container = document.getElementById("datePillsContainer");
  const availableDates = Object.keys(appData.daily_scans || {}).sort().reverse();

  if (availableDates.length === 0) {
    container.innerHTML = `<span style="color: var(--text-dim); font-size: 13px;">Belum ada riwayat harian</span>`;
    return;
  }

  let html = "";
  availableDates.forEach((dateKey, index) => {
    const scan = appData.daily_scans[dateKey];
    const isSelected = dateKey === selectedDate;
    const label = scan.date_display || dateKey;
    const isToday = index === 0 ? " (Terbaru)" : "";
    html += `
      <button class="date-pill ${isSelected ? 'active' : ''}" onclick="selectDate('${dateKey}')">
        ${label}${isToday}
      </button>
    `;
  });
  container.innerHTML = html;
}

// Ganti Tanggal
function selectDate(dateKey) {
  selectedDate = dateKey;
  renderDatePills();
  renderView();
}

// Ganti Mode (Daily vs VIP 3-Dot)
function switchMode(mode) {
  currentMode = mode;
  document.getElementById("tabDailyBtn").classList.toggle("active", mode === "daily");
  document.getElementById("tabVipBtn").classList.toggle("active", mode === "vip");
  
  // Tampilkan / sembunyikan date pills
  document.getElementById("datePillsSection").style.display = mode === "daily" ? "flex" : "none";
  
  renderView();
}

// Search Handler
function handleSearch(val) {
  searchQuery = val.trim().toUpperCase();
  renderView();
}

// Filter Category
function filterCategory(filterType, element) {
  activeFilter = filterType;
  document.querySelectorAll(".filter-btn").forEach(btn => btn.classList.remove("active"));
  element.classList.add("active");
  renderView();
}

// Main Render Function
function renderView() {
  if (currentMode === "daily") {
    renderDailyView();
  } else {
    renderVipView();
  }
}

// Render Daily Mode (7 Hari)
function renderDailyView() {
  const scanData = appData.daily_scans[selectedDate];
  const grid = document.getElementById("stocksGrid");
  
  if (!scanData || !scanData.stocks || scanData.stocks.length === 0) {
    grid.innerHTML = `
      <div class="empty-state">
        <div style="font-size: 40px; margin-bottom: 12px;">📊</div>
        <h3>Belum Ada Data Saham untuk Tanggal Ini</h3>
        <p>Silakan pilih tanggal lain pada daftar di atas.</p>
      </div>
    `;
    updateSummaryStats(0, 0, 0);
    return;
  }

  // Update Summary Cards
  const summary = scanData.summary || {};
  updateSummaryStats(
    summary.count_3_dot || 0,
    summary.count_2_dot || 0,
    summary.total_screener || scanData.stocks.length
  );

  // Filter stocks
  let filtered = scanData.stocks.filter(s => {
    // 1. Filter Search
    if (searchQuery && !s.symbol.includes(searchQuery) && !s.name.includes(searchQuery)) {
      return false;
    }
    // 2. Filter Category
    if (activeFilter === "3dot" && s.count_green !== 3) return false;
    if (activeFilter === "2dot" && s.count_green !== 2) return false;
    if (activeFilter === "golden") {
      const hasGold = ['D', '60', '15'].some(tf => s.timeframes?.[tf]?.donalt?.golden);
      if (!hasGold) return false;
    }
    if (activeFilter === "smc") {
      const isBreakout = ['D', '60'].some(tf => {
        const smc = s.timeframes?.[tf]?.smc;
        return smc?.status_7d && smc.status_7d.includes("BREAKOUT");
      });
      if (!isBreakout) return false;
    }
    return true;
  });

  // Update Section Header Texts
  document.getElementById("sectionTitle").innerHTML = `📅 Analisa ${scanData.date_display} <span style="font-size:14px; font-weight:500; color:var(--text-muted);">(${scanData.time_display || '16:30 WIB'})</span>`;
  document.getElementById("sectionDesc").innerText = `Menampilkan ${filtered.length} saham yang lolos kriteria screener dan analisa indikator`;

  // Update filter counters
  document.getElementById("countAll").innerText = scanData.stocks.length;
  document.getElementById("count3DotFilter").innerText = summary.count_3_dot || 0;
  document.getElementById("count2DotFilter").innerText = summary.count_2_dot || 0;

  if (filtered.length === 0) {
    grid.innerHTML = `
      <div class="empty-state">
        <div style="font-size: 32px; margin-bottom: 8px;">🔍</div>
        <h3>Tidak Ada Saham yang Cocok</h3>
        <p>Coba ubah kata kunci pencarian atau filter kategori Anda.</p>
      </div>
    `;
    return;
  }

  // Render Stock Cards
  grid.innerHTML = filtered.map(stock => createStockCardHTML(stock)).join("");
}

// Render VIP 3-Dot Mode (1 Bulan)
function renderVipView() {
  const grid = document.getElementById("stocksGrid");
  const vipList = appData.vip_3dot_history || [];

  updateSummaryStats(vipList.length, "-", "30 Hari");

  document.getElementById("sectionTitle").innerHTML = `💎 Rekam Jejak 3-Dot Green (1 Bulan Terakhir)`;
  document.getElementById("sectionDesc").innerText = `Arsip lengkap seluruh saham yang berhasil mendapatkan konfirmasi 3 Timeframe sekaligus (Daily + 1H + 15M) dalam 30 hari terakhir.`;

  // Filter VIP list
  let filtered = vipList.filter(item => {
    const s = item.data;
    if (searchQuery && !s.symbol.includes(searchQuery) && !s.name.includes(searchQuery)) {
      return false;
    }
    return true;
  });

  document.getElementById("countAll").innerText = vipList.length;
  document.getElementById("count3DotFilter").innerText = vipList.length;
  document.getElementById("count2DotFilter").innerText = 0;

  if (filtered.length === 0) {
    grid.innerHTML = `
      <div class="empty-state">
        <div style="font-size: 40px; margin-bottom: 12px;">🌟</div>
        <h3>Belum Ada Saham 3 Dot Green dalam 30 Hari Terakhir</h3>
        <p>Data akan otomatis terisi setiap kali bot menemukan saham dengan konfirmasi 3 Timeframe.</p>
      </div>
    `;
    return;
  }

  grid.innerHTML = filtered.map(item => {
    return createStockCardHTML(item.data, item.scan_date_display);
  }).join("");
}

// Helper: Update Top Summary Stats
function updateSummaryStats(count3, count2, countTotal) {
  document.getElementById("stat3Dot").innerText = count3;
  document.getElementById("stat2Dot").innerText = count2;
  document.getElementById("statTotal").innerText = countTotal;
}

// Helper: Create HTML Card for a Stock
function createStockCardHTML(stock, vipDateLabel = null) {
  const isVip = stock.count_green === 3;
  const tf = stock.timeframes || {};
  
  // Format Price & Change
  const priceFormatted = "Rp " + Number(stock.close || 0).toLocaleString("id-ID");
  const changeVal = Number(stock.change || 0);
  const changeClass = changeVal > 0 ? "change-up" : (changeVal < 0 ? "change-down" : "change-flat");
  const changeSign = changeVal > 0 ? "+" : "";
  const changeFormatted = `${changeSign}${changeVal.toFixed(2)}%`;
  const volumeFormatted = Number(stock.volume || 0).toLocaleString("id-ID") + " lbr";

  // Dot Green Timeframes
  const dotD = tf.D?.status;
  const dot60 = tf['60']?.status;
  const dot15 = tf['15']?.status;

  // TradingView Direct Link
  const tvUrl = `${CHART_BASE_URL}?symbol=IDX%3A${stock.symbol}&interval=D`;

  // SMC Signals
  const smcStatus = tf.D?.smc?.status_7d || tf['60']?.smc?.status_7d || "";
  let smcBadgeHTML = "";
  if (smcStatus) {
    if (smcStatus.includes("BREAKOUT")) {
      smcBadgeHTML = `<span class="tag-pill pill-smc-breakout">🔥 ${smcStatus}</span>`;
    } else if (smcStatus.includes("DEMAND") || smcStatus.includes("Pantulan")) {
      smcBadgeHTML = `<span class="tag-pill pill-smc-demand">🟢 ${smcStatus}</span>`;
    } else {
      smcBadgeHTML = `<span style="color:var(--text-muted); font-size:11px;">${smcStatus}</span>`;
    }
  }

  // Golden / Death Cross
  const goldenCross = tf['15']?.donalt?.golden || tf['60']?.donalt?.golden || tf.D?.donalt?.golden;
  const deathCross = tf['15']?.donalt?.death || tf['60']?.donalt?.death || tf.D?.donalt?.death;
  let donaltBadgeHTML = "";
  if (goldenCross) {
    const gainExtra = goldenCross.gain_pct != null ? ` (${goldenCross.gain_pct > 0 ? '+' : ''}${goldenCross.gain_pct.toFixed(2)}%)` : "";
    donaltBadgeHTML = `<span class="tag-pill pill-golden">✨ Golden Cross${gainExtra}</span>`;
  } else if (deathCross) {
    donaltBadgeHTML = `<span class="tag-pill pill-death">⚠️ Death Cross</span>`;
  } else {
    donaltBadgeHTML = `<span style="color:var(--text-dim); font-size:11px;">-</span>`;
  }

  // Scalp Trend
  const scalpTrend = tf['60']?.scalping?.trend || tf['15']?.scalping?.trend || tf.D?.scalping?.trend || "-";
  let scalpTrendHTML = scalpTrend;
  if (scalpTrend.includes("BUY") || scalpTrend.includes("Green")) {
    scalpTrendHTML = `<span class="tag-pill pill-buy">🟢 ${scalpTrend}</span>`;
  } else if (scalpTrend.includes("SELL") || scalpTrend.includes("Red")) {
    scalpTrendHTML = `<span class="tag-pill pill-sell">🔴 ${scalpTrend}</span>`;
  }

  // MACD Divergences
  const macdBull = tf['15']?.macd?.bull || tf['60']?.macd?.bull || tf.D?.macd?.bull;
  const macdBear = tf['15']?.macd?.bear || tf['60']?.macd?.bear || tf.D?.macd?.bear;
  let macdHTML = "-";
  if (macdBull) {
    macdHTML = `<span style="color:var(--neon-green); font-weight:600;">🐂 ${macdBull.type || 'Bullish'} (${macdBull.date || ''})</span>`;
  } else if (macdBear) {
    macdHTML = `<span style="color:var(--neon-red); font-weight:600;">🐻 ${macdBear.type || 'Bearish'}</span>`;
  }

  // VIP Date Pill if in VIP mode
  const vipDateBadge = vipDateLabel ? `<div style="font-size:11px; color:var(--neon-gold); font-family:var(--font-mono); margin-bottom:4px;">📅 Terdeteksi 3-Dot: ${vipDateLabel}</div>` : '';

  return `
    <div class="stock-card ${isVip ? 'is-vip' : ''}">
      <div class="card-top">
        <div class="stock-identity">
          <div class="stock-sym-badge">${stock.symbol}</div>
          <div>
            ${vipDateBadge}
            <div class="stock-meta">${stock.name || stock.symbol} • Vol: ${volumeFormatted}</div>
          </div>
        </div>
        <div class="stock-price-block">
          <div class="stock-price">${priceFormatted}</div>
          <div class="stock-change ${changeClass}">${changeFormatted}</div>
        </div>
      </div>

      <!-- 3 Timeframe Dot Green Grid -->
      <div class="dot-status-grid">
        <div class="dot-item ${dotD ? 'has-dot' : ''}">
          <div class="dot-tf">Daily (1D)</div>
          <div class="dot-badge-text ${dotD ? 'dot-has' : 'dot-none'}">${dotD ? '🟢 ADA DOT' : '⚪ -'}</div>
          <div class="dot-date-text">${tf.D?.date || '-'}</div>
        </div>
        <div class="dot-item ${dot60 ? 'has-dot' : ''}">
          <div class="dot-tf">1 Jam (1H)</div>
          <div class="dot-badge-text ${dot60 ? 'dot-has' : 'dot-none'}">${dot60 ? '🟢 ADA DOT' : '⚪ -'}</div>
          <div class="dot-date-text">${tf['60']?.date || '-'}</div>
        </div>
        <div class="dot-item ${dot15 ? 'has-dot' : ''}">
          <div class="dot-tf">15 Menit (15M)</div>
          <div class="dot-badge-text ${dot15 ? 'dot-has' : 'dot-none'}">${dot15 ? '🟢 ADA DOT' : '⚪ -'}</div>
          <div class="dot-date-text">${tf['15']?.date || '-'}</div>
        </div>
      </div>

      <!-- Indicator Details Table -->
      <div class="indicator-details">
        <div class="indicator-row">
          <span class="ind-label">✨ EMA DonAlt Cross:</span>
          <span class="ind-val">${donaltBadgeHTML}</span>
        </div>
        <div class="indicator-row">
          <span class="ind-label">🎯 SMC Level & Status:</span>
          <span class="ind-val">${smcBadgeHTML || '-'}</span>
        </div>
        <div class="indicator-row">
          <span class="ind-label">⚔️ Scalping Trend:</span>
          <span class="ind-val">${scalpTrendHTML}</span>
        </div>
        <div class="indicator-row">
          <span class="ind-label">📊 MACD Divergence:</span>
          <span class="ind-val">${macdHTML}</span>
        </div>
      </div>

      <!-- Card Action Button -->
      <div class="card-bottom">
        <a href="${tvUrl}" target="_blank" rel="noopener noreferrer" class="btn-chart">
          Buka Chart TradingView ↗
        </a>
      </div>
    </div>
  `;
}
