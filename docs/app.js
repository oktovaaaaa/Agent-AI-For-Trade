/**
 * HUNTER RADAR & RALLYGOOD — JAVASCRIPT DASHBOARD ENGINE
 * Minimalist UI dengan Sidebar History Per Tanggal & Filter Sinyal
 * Terinspirasi oleh Coinest / Clean Fintech Interface
 */

const CHART_BASE_URL = "https://www.tradingview.com/chart/6B2fiCnc/";

// State Management
let appData = {
  last_updated: "-",
  daily_scans: {},
  vip_3dot_history: []
};

let currentMode = "daily"; // 'daily' | 'vip'
let selectedDate = null;
let searchQuery = "";
let activeFilter = "all"; // 'all' | '3dot' | '2dot' | 'golden' | 'smc' | 'scalp'
let currentSort = "dot_desc"; // 'dot_desc' | 'gain_desc' | 'loss_asc' | 'vol_desc' | 'sym_asc'

// Inisialisasi saat DOM selesai dimuat
document.addEventListener("DOMContentLoaded", async () => {
  initTheme();
  await loadDatabase();
});

// Load Database JSON
async function loadDatabase() {
  try {
    const response = await fetch("data/history.json?v=" + Date.now());
    if (!response.ok) throw new Error("Gagal mengambil data/history.json");
    appData = await response.json();
    
    // Update footer & header info
    if (appData.last_updated) {
      document.getElementById("footerSyncText").innerText = "Update Terakhir: " + appData.last_updated;
    }
    
    // Update VIP badge count
    const vipCount = (appData.vip_3dot_history || []).length;
    document.getElementById("vipNavCount").innerText = vipCount;

    // Pilih tanggal terbaru secara default
    const availableDates = Object.keys(appData.daily_scans || {}).sort().reverse();
    if (availableDates.length > 0) {
      selectedDate = availableDates[0];
    }

    renderSidebarHistory();
    renderMainView();
  } catch (error) {
    console.error("Error loading data:", error);
    document.getElementById("stocksGrid").innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">⚠️</div>
        <h3>Gagal Memuat Database Saham</h3>
        <p>File <code>data/history.json</code> belum dapat diakses atau sedang diperbarui oleh bot scan.</p>
      </div>
    `;
  }
}

// Render Riwayat Per Tanggal (7 Hari Terakhir) di Left Sidebar
function renderSidebarHistory() {
  const container = document.getElementById("sidebarDateList");
  const availableDates = Object.keys(appData.daily_scans || {}).sort().reverse();

  if (availableDates.length === 0) {
    container.innerHTML = `<div style="font-size:12px; color:var(--text-dim); padding:6px 10px;">Belum ada riwayat harian</div>`;
    return;
  }

  let html = "";
  availableDates.forEach((dateKey, index) => {
    const scan = appData.daily_scans[dateKey];
    const isSelected = (currentMode === "daily" && dateKey === selectedDate);
    const dateLabel = scan.date_display || dateKey;
    const stockCount = scan.stocks ? scan.stocks.length : (scan.summary?.total_screener || 0);

    html += `
      <button class="history-date-btn ${isSelected ? 'active' : ''}" onclick="selectHistoryDate('${dateKey}')">
        <div class="history-date-left">
          <span class="history-date-dot"></span>
          <span>${dateLabel}</span>
        </div>
        <span class="history-badge">${stockCount}</span>
      </button>
    `;
  });

  container.innerHTML = html;
}

// Handler Saat Tanggal di Sidebar Diklik
function selectHistoryDate(dateKey) {
  selectedDate = dateKey;
  currentMode = "daily";
  
  // Update state tombol menu utama
  document.getElementById("menuDailyBtn").classList.add("active");
  document.getElementById("menuVipBtn").classList.remove("active");
  
  renderSidebarHistory();
  renderMainView();
  toggleSidebar(false); // Close sidebar on mobile
}

// Handler Ganti Mode Utama (Daily vs VIP 3-Dot)
function switchMainMode(mode) {
  currentMode = mode;
  document.getElementById("menuDailyBtn").classList.toggle("active", mode === "daily");
  document.getElementById("menuVipBtn").classList.toggle("active", mode === "vip");
  
  renderSidebarHistory();
  renderMainView();
  toggleSidebar(false);
}

// Handler Filter Sinyal di Sidebar
function setSidebarFilter(filterKey, element) {
  activeFilter = filterKey;
  document.querySelectorAll(".nav-subitem").forEach(item => item.classList.remove("active"));
  element.classList.add("active");
  renderMainView();
  toggleSidebar(false);
}

// Handler Search Input
function handleSearch(val) {
  searchQuery = val.trim().toUpperCase();
  document.getElementById("searchClearBtn").style.display = searchQuery ? "block" : "none";
  renderMainView();
}

function clearSearch() {
  document.getElementById("globalSearchInput").value = "";
  searchQuery = "";
  document.getElementById("searchClearBtn").style.display = "none";
  renderMainView();
}

// Handler Sort Selector
function handleSortChange(sortVal) {
  currentSort = sortVal;
  renderMainView();
}

// Main View Render Engine
function renderMainView() {
  if (currentMode === "daily") {
    renderDailyView();
  } else {
    renderVipView();
  }
}

// Render Daily Mode (Data Harian)
function renderDailyView() {
  const scanData = appData.daily_scans[selectedDate];
  const grid = document.getElementById("stocksGrid");

  document.getElementById("pageMainHeading").innerText = "Dashboard Rekomendasi Harian";
  document.getElementById("pageSubHeading").innerText = "Daftar saham yang lolos screener volume dan indikator teknikal";

  if (!scanData || !scanData.stocks || scanData.stocks.length === 0) {
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📊</div>
        <h3>Belum Ada Data Saham untuk Tanggal Ini</h3>
        <p>Silakan pilih tanggal lain pada riwayat di sidebar kiri.</p>
      </div>
    `;
    updateTopMetrics(0, 0, 0, 0);
    return;
  }

  // Active Date Bar Info
  document.getElementById("activeDateDisplay").innerText = scanData.date_display || selectedDate;
  document.getElementById("activeTimeDisplay").innerText = scanData.time_display || "16:30 WIB";

  // Hitung jumlah sinyal spesifik
  let countGolden = 0;
  scanData.stocks.forEach(s => {
    const hasGold = ['D', '60', '15'].some(tf => s.timeframes?.[tf]?.donalt?.golden);
    if (hasGold) countGolden++;
  });

  // Update Metric Cards
  const summary = scanData.summary || {};
  updateTopMetrics(
    summary.count_3_dot || 0,
    summary.count_2_dot || 0,
    countGolden,
    scanData.stocks.length
  );

  // Update Sidebar Filter Counters
  document.getElementById("countAllFilter").innerText = scanData.stocks.length;
  document.getElementById("count3DotFilter").innerText = summary.count_3_dot || 0;
  document.getElementById("count2DotFilter").innerText = summary.count_2_dot || 0;

  // Filter Saham
  let filtered = scanData.stocks.filter(s => {
    // 1. Search filter
    if (searchQuery && !s.symbol.includes(searchQuery) && !s.name.includes(searchQuery)) {
      return false;
    }
    // 2. Sinyal filter
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
    if (activeFilter === "scalp") {
      const isBuy = ['D', '60', '15'].some(tf => {
        const trend = s.timeframes?.[tf]?.scalping?.trend || "";
        return trend.includes("BUY") || trend.includes("Green");
      });
      if (!isBuy) return false;
    }
    return true;
  });

  // Sorting
  filtered = sortStocks(filtered);

  // Update Result Count text
  document.getElementById("filterResultCount").innerText = `Menampilkan ${filtered.length} dari ${scanData.stocks.length} saham`;

  if (filtered.length === 0) {
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🔍</div>
        <h3>Tidak Ditemukan Saham yang Cocok</h3>
        <p>Coba gunakan kata kunci lain atau pilih filter sinyal yang berbeda di sidebar kiri.</p>
      </div>
    `;
    return;
  }

  // Render Grid Cards
  grid.innerHTML = filtered.map(s => createStockCardHTML(s)).join("");
}

// Render VIP View (1 Bulan 3-Dot Green)
function renderVipView() {
  const grid = document.getElementById("stocksGrid");
  const vipList = appData.vip_3dot_history || [];

  document.getElementById("pageMainHeading").innerText = "💎 VIP 3-Dot Green (Riwayat 1 Bulan)";
  document.getElementById("pageSubHeading").innerText = "Arsip khusus saham yang berhasil mengonfirmasi 3 Timeframe (Daily + 1H + 15M) dalam 30 hari terakhir";

  document.getElementById("activeDateDisplay").innerText = "Riwayat 1 Bulan Terakhir";
  document.getElementById("activeTimeDisplay").innerText = "30 Hari";

  updateTopMetrics(vipList.length, "-", "-", "VIP");

  document.getElementById("countAllFilter").innerText = vipList.length;
  document.getElementById("count3DotFilter").innerText = vipList.length;
  document.getElementById("count2DotFilter").innerText = 0;

  // Filter VIP list
  let filtered = vipList.filter(item => {
    const s = item.data;
    if (searchQuery && !s.symbol.includes(searchQuery) && !s.name.includes(searchQuery)) {
      return false;
    }
    return true;
  });

  // Sort VIP list
  filtered.sort((a, b) => new Date(b.detected_at || 0) - new Date(a.detected_at || 0));

  document.getElementById("filterResultCount").innerText = `Menampilkan ${filtered.length} saham Full 3-Dot Green`;

  if (filtered.length === 0) {
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🌟</div>
        <h3>Belum Ada Riwayat VIP 3-Dot Green</h3>
        <p>Data akan terisi secara otomatis setiap kali bot scan mendeteksi saham dengan 3 Dot Green aktif.</p>
      </div>
    `;
    return;
  }

  grid.innerHTML = filtered.map(item => {
    return createStockCardHTML(item.data, item.scan_date_display);
  }).join("");
}

// Helper Sorting Logic
function sortStocks(stocks) {
  return [...stocks].sort((a, b) => {
    if (currentSort === "dot_desc") {
      if ((b.count_green || 0) !== (a.count_green || 0)) {
        return (b.count_green || 0) - (a.count_green || 0);
      }
      return (b.change || 0) - (a.change || 0);
    }
    if (currentSort === "gain_desc") {
      return (b.change || 0) - (a.change || 0);
    }
    if (currentSort === "loss_asc") {
      return (a.change || 0) - (b.change || 0);
    }
    if (currentSort === "vol_desc") {
      return (b.volume || 0) - (a.volume || 0);
    }
    if (currentSort === "sym_asc") {
      return a.symbol.localeCompare(b.symbol);
    }
    return 0;
  });
}

// Helper: Update Top Metric Cards
function updateTopMetrics(vipCount, potCount, goldenCount, totalCount) {
  document.getElementById("statVipCount").innerText = vipCount;
  document.getElementById("statPotCount").innerText = potCount;
  document.getElementById("statGoldenCount").innerText = goldenCount;
  document.getElementById("statTotalCount").innerText = totalCount;
}

// Helper: Generate HTML for Minimalist Stock Card
function createStockCardHTML(stock, vipDateLabel = null) {
  const isVip = stock.count_green === 3;
  const tf = stock.timeframes || {};

  // Formatter Harga & Kenaikan
  const priceFormatted = "Rp " + Number(stock.close || 0).toLocaleString("id-ID");
  const changeVal = Number(stock.change || 0);
  let changeClass = "flat";
  let changeSign = "";
  if (changeVal > 0) {
    changeClass = "positive";
    changeSign = "+";
  } else if (changeVal < 0) {
    changeClass = "negative";
  }
  const changeFormatted = `${changeSign}${changeVal.toFixed(2)}%`;

  // Format Volume
  const volVal = Number(stock.volume || 0);
  let volFormatted = volVal.toLocaleString("id-ID") + " lbr";
  if (volVal >= 1000000) {
    volFormatted = (volVal / 1000000).toFixed(1) + " Juta lbr";
  }

  // Timeframe Status
  const tfD = tf.D || {};
  const tf60 = tf['60'] || {};
  const tf15 = tf['15'] || {};

  // TradingView Link
  const tvUrl = `${CHART_BASE_URL}?symbol=IDX%3A${stock.symbol}&interval=D`;

  // Sinyal DonAlt Golden / Death Cross
  const goldenCross = tf15.donalt?.golden || tf60.donalt?.golden || tfD.donalt?.golden;
  const deathCross = tf15.donalt?.death || tf60.donalt?.death || tfD.donalt?.death;
  let donaltChip = `<span class="badge-chip chip-neutral">-</span>`;
  if (goldenCross) {
    const gainExtra = goldenCross.gain_pct != null ? ` (+${goldenCross.gain_pct.toFixed(1)}%)` : "";
    donaltChip = `<span class="badge-chip chip-golden">✨ Golden Cross${gainExtra}</span>`;
  } else if (deathCross) {
    donaltChip = `<span class="badge-chip chip-death">⚠️ Death Cross</span>`;
  }

  // Sinyal SMC (Smart Money Concepts)
  const smcStatus = tfD.smc?.status_7d || tf60.smc?.status_7d || "";
  let smcChip = `<span class="badge-chip chip-neutral">-</span>`;
  if (smcStatus) {
    if (smcStatus.includes("BREAKOUT")) {
      smcChip = `<span class="badge-chip chip-smc-breakout">🔥 ${smcStatus}</span>`;
    } else if (smcStatus.includes("DEMAND") || smcStatus.includes("Pantulan")) {
      smcChip = `<span class="badge-chip chip-smc-demand">🟢 ${smcStatus}</span>`;
    } else {
      smcChip = `<span class="badge-chip chip-neutral">${smcStatus}</span>`;
    }
  }

  // Sinyal Scalping Trend
  const scalpTrend = tf60.scalping?.trend || tf15.scalping?.trend || tfD.scalping?.trend || "";
  let scalpChip = `<span class="badge-chip chip-neutral">-</span>`;
  if (scalpTrend.includes("BUY") || scalpTrend.includes("Green")) {
    scalpChip = `<span class="badge-chip chip-scalp-buy">🟢 Scalp BUY</span>`;
  } else if (scalpTrend.includes("SELL") || scalpTrend.includes("Red")) {
    scalpChip = `<span class="badge-chip chip-scalp-sell">🔴 Scalp SELL</span>`;
  }

  // VIP Date Notification
  const vipDateRow = vipDateLabel ? `
    <div style="font-size:11px; font-weight:600; color:var(--status-gold); margin-top:2px;">
      📅 Terdeteksi VIP: ${vipDateLabel}
    </div>
  ` : "";

  return `
    <article class="stock-card ${isVip ? 'is-vip' : ''}">
      
      <!-- Card Header: Symbol & Price -->
      <div class="card-header-row">
        <div class="symbol-col">
          <div class="symbol-badge-box">
            <span class="symbol-text">${stock.symbol}</span>
            ${isVip ? `<span class="vip-badge-pill">💎 3-DOT</span>` : (stock.count_green === 2 ? `<span class="vip-badge-pill" style="background:var(--status-cyan-bg); color:var(--status-cyan-text);">⚡ 2-DOT</span>` : '')}
          </div>
          <span class="symbol-name">${stock.name || stock.symbol}</span>
          ${vipDateRow}
        </div>

        <div class="price-col">
          <span class="price-text">${priceFormatted}</span>
          <span class="change-pill ${changeClass}">${changeFormatted}</span>
        </div>
      </div>

      <!-- Timeframe Dot Green Status (1D, 1H, 15M) -->
      <div class="timeframe-dots-box">
        <div class="dots-label-row">
          <span>RALLYGOOD DOT GREEN</span>
          <span class="dots-status-count">${stock.count_green || 0} / 3 TF Aktif</span>
        </div>

        <div class="timeframes-grid">
          <!-- 1D Daily -->
          <div class="tf-item ${tfD.status ? 'active' : ''}">
            <div class="tf-header">
              <span class="tf-name">1D</span>
              <span class="tf-dot"></span>
            </div>
            <span class="tf-date" title="${tfD.date || '-'}">${tfD.date ? tfD.date.split(',')[0] : '-'}</span>
          </div>

          <!-- 1H (60m) -->
          <div class="tf-item ${tf60.status ? 'active' : ''}">
            <div class="tf-header">
              <span class="tf-name">1H</span>
              <span class="tf-dot"></span>
            </div>
            <span class="tf-date" title="${tf60.date || '-'}">${tf60.date ? tf60.date.split(',')[0] : '-'}</span>
          </div>

          <!-- 15M -->
          <div class="tf-item ${tf15.status ? 'active' : ''}">
            <div class="tf-header">
              <span class="tf-name">15M</span>
              <span class="tf-dot"></span>
            </div>
            <span class="tf-date" title="${tf15.date || '-'}">${tf15.date ? tf15.date.split(',')[0] : '-'}</span>
          </div>
        </div>
      </div>

      <!-- Indicator Highlights Row -->
      <div class="indicators-list">
        <div class="indicator-row">
          <span class="indicator-title">DonAlt EMA:</span>
          <div class="indicator-val">${donaltChip}</div>
        </div>
        <div class="indicator-row">
          <span class="indicator-title">SMC Area:</span>
          <div class="indicator-val">${smcChip}</div>
        </div>
        <div class="indicator-row">
          <span class="indicator-title">Scalp Signal:</span>
          <div class="indicator-val">${scalpChip}</div>
        </div>
      </div>

      <!-- Card Footer: Volume & Direct TradingView Button -->
      <div class="card-footer-row">
        <div class="volume-info">
          <span class="vol-label">Volume Transaksi</span>
          <span class="vol-val">${volFormatted}</span>
        </div>

        <a href="${tvUrl}" target="_blank" rel="noopener noreferrer" class="btn-chart">
          <span>Chart TV</span>
          <span>↗</span>
        </a>
      </div>

    </article>
  `;
}

// Theme Toggle (Light / Dark)
function initTheme() {
  const savedTheme = localStorage.getItem("hunter_theme") || "light";
  if (savedTheme === "dark") {
    document.body.classList.remove("light-theme");
    document.body.classList.add("dark-theme");
    document.getElementById("themeIcon").innerText = "☀️";
  } else {
    document.body.classList.remove("dark-theme");
    document.body.classList.add("light-theme");
    document.getElementById("themeIcon").innerText = "🌙";
  }
}

function toggleTheme() {
  if (document.body.classList.contains("dark-theme")) {
    document.body.classList.remove("dark-theme");
    document.body.classList.add("light-theme");
    localStorage.setItem("hunter_theme", "light");
    document.getElementById("themeIcon").innerText = "🌙";
  } else {
    document.body.classList.remove("light-theme");
    document.body.classList.add("dark-theme");
    localStorage.setItem("hunter_theme", "dark");
    document.getElementById("themeIcon").innerText = "☀️";
  }
}

// Mobile Sidebar Toggle
function toggleSidebar(forceState = null) {
  const sidebar = document.getElementById("appSidebar");
  const backdrop = document.getElementById("sidebarBackdrop");
  const shouldOpen = forceState !== null ? forceState : !sidebar.classList.contains("open");

  if (shouldOpen) {
    sidebar.classList.add("open");
    backdrop.classList.add("show");
  } else {
    sidebar.classList.remove("open");
    backdrop.classList.remove("show");
  }
}

// Reload Dashboard
function reloadDashboard() {
  loadDatabase();
}
