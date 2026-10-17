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

    // Pilih tanggal terbaru secara default yang memiliki data saham
    const availableDates = Object.keys(appData.daily_scans || {}).sort().reverse();
    const latestWithStocks = availableDates.find(d => (appData.daily_scans[d]?.stocks || []).length > 0) || availableDates[0];
    if (latestWithStocks) {
      selectedDate = latestWithStocks;
    }

    renderSidebarHistory();
    renderMainView();
  } catch (error) {
    console.error("Error loading data:", error);
    document.getElementById("stocksGrid").innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">
          <svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="#F59E0B" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="alert-svg"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
        </div>
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
    container.innerHTML = `<div style="font-size:12px; color:var(--text-dim); padding:6px 10px;">⏳ Menunggu scan 16:21 WIB</div>`;
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
    document.getElementById("activeDateDisplay").innerText = "Standby Scan Rutin";
    document.getElementById("activeTimeDisplay").innerText = "16:21 WIB";
    document.getElementById("filterResultCount").innerText = "Menunggu data scan jam 16:21 WIB";
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">
          <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
        </div>
        <h3>Menunggu Jadwal Scan Saham Jam 16:21 WIB</h3>
        <p style="margin-top:6px; color:var(--text-muted); max-width:480px; margin-left:auto; margin-right:auto;">
          Database telah dikosongkan. Bot Hunter AI otomatis aktif pasca penutupan bursa IDX jam 16:21 WIB untuk memindai seluruh saham dan memperbarui web secara real-time.
        </p>
      </div>
    `;
    updateTopMetrics(0, 0, 0, 0);
    return;
  }

  // Active Date Bar Info
  document.getElementById("activeDateDisplay").innerText = scanData.date_display || selectedDate;
  document.getElementById("activeTimeDisplay").innerText = scanData.time_display || "16:21 WIB";

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
        <div class="empty-icon">
          <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.3-4.3"></path></svg>
        </div>
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
        <div class="empty-icon">
          <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#F59E0B" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>
        </div>
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
    <article class="stock-card ${isVip ? 'is-vip' : ''}" onclick="openStockDetail('${stock.symbol}')" title="Klik untuk melihat analisa detail lengkap">
      
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
            <span class="tf-date" title="${tfD.date || '-'}">${tfD.date ? tfD.date.split(',')[0].replace(' (Kenaikan:', '') : '-'}</span>
          </div>

          <!-- 1H (60m) -->
          <div class="tf-item ${tf60.status ? 'active' : ''}">
            <div class="tf-header">
              <span class="tf-name">1H</span>
              <span class="tf-dot"></span>
            </div>
            <span class="tf-date" title="${tf60.date || '-'}">${tf60.date ? tf60.date.split(',')[0].replace(' (Kenaikan:', '') : '-'}</span>
          </div>

          <!-- 15M -->
          <div class="tf-item ${tf15.status ? 'active' : ''}">
            <div class="tf-header">
              <span class="tf-name">15M</span>
              <span class="tf-dot"></span>
            </div>
            <span class="tf-date" title="${tf15.date || '-'}">${tf15.date ? tf15.date.split(',')[0].replace(' (Kenaikan:', '') : '-'}</span>
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

      <!-- Card Footer: Volume, Hint, & Direct TradingView Button -->
      <div class="card-footer-row">
        <div class="volume-info">
          <span class="vol-label">Volume Transaksi</span>
          <span class="vol-val">${volFormatted}</span>
        </div>

        <div style="display:flex; align-items:center; gap:8px;">
          <span class="card-click-hint">Analisa 🔍</span>
          <a href="${tvUrl}" target="_blank" rel="noopener noreferrer" class="btn-chart" onclick="event.stopPropagation()">
            <span>Chart TV</span>
            <span>↗</span>
          </a>
        </div>
      </div>

    </article>
  `;
}

// ============================================================================
// MODAL DETAIL LENGKAP SAHAM (FULL ANALYSIS POPUP)
// ============================================================================

function findStockBySymbol(symbol) {
  // 1. Cek di scan tanggal aktif
  if (currentMode === "daily" && appData.daily_scans?.[selectedDate]?.stocks) {
    const found = appData.daily_scans[selectedDate].stocks.find(s => s.symbol === symbol);
    if (found) return found;
  }
  // 2. Cek di daftar VIP
  if (appData.vip_3dot_history) {
    const foundVip = appData.vip_3dot_history.find(h => h.symbol === symbol || h.data?.symbol === symbol);
    if (foundVip) return foundVip.data || foundVip;
  }
  // 3. Cek di seluruh riwayat harian
  for (const dKey of Object.keys(appData.daily_scans || {})) {
    const list = appData.daily_scans[dKey].stocks || [];
    const found = list.find(s => s.symbol === symbol);
    if (found) return found;
  }
  return null;
}

function openStockDetail(symbol) {
  const stock = findStockBySymbol(symbol);
  if (!stock) {
    alert("Data saham " + symbol + " tidak ditemukan.");
    return;
  }

  const tf = stock.timeframes || {};
  const tfD = tf.D || {};
  const tf60 = tf['60'] || {};
  const tf15 = tf['15'] || {};
  const isVip = stock.count_green === 3;

  // Format Harga & Kenaikan
  const priceFormatted = "Rp " + Number(stock.close || 0).toLocaleString("id-ID");
  const changeVal = Number(stock.change || 0);
  const changeSign = changeVal > 0 ? "+" : "";
  const changeClass = changeVal > 0 ? "positive" : (changeVal < 0 ? "negative" : "flat");
  const changeFormatted = `${changeSign}${changeVal.toFixed(2)}%`;

  // Volume
  const volVal = Number(stock.volume || 0);
  let volFormatted = volVal.toLocaleString("id-ID") + " lembar";
  if (volVal >= 1000000) {
    volFormatted = (volVal / 1000000).toFixed(2) + " Juta lembar";
  }

  // TradingView Link
  const tvUrl = `${CHART_BASE_URL}?symbol=IDX%3A${stock.symbol}&interval=D`;

  // Helper Parser Gain String
  function extractGain(dateStr, directGain) {
    if (directGain != null && typeof directGain === 'number') {
      return (directGain > 0 ? '+' : '') + directGain.toFixed(2) + '%';
    }
    if (!dateStr) return null;
    const match = dateStr.match(/Kenaikan:\s*([+-]?[\d\.]+%?)/i);
    if (match) return match[1].includes('%') ? match[1] : match[1] + '%';
    return null;
  }

  // Helper Parser Date Clean
  function cleanDate(dateStr) {
    if (!dateStr || dateStr === '-') return '-';
    return dateStr.replace(/\(Kenaikan:.*$/i, '').trim();
  }

  // Helper Render Timeframe Box
  function renderTfDetailCard(label, tfObj) {
    const active = tfObj.status;
    const dateText = cleanDate(tfObj.date);
    const gainText = extractGain(tfObj.date, tfObj.gain_pct);
    let gainClass = "neutral";
    if (gainText) {
      gainClass = gainText.startsWith('+') ? "positive" : (gainText.startsWith('-') ? "negative" : "neutral");
    }

    return `
      <div class="modal-tf-card ${active ? 'active' : ''}">
        <div class="modal-tf-card-head">
          <span class="modal-tf-title">${label}</span>
          <span class="modal-tf-status ${active ? 'active' : 'inactive'}">
            ${active ? '🟢 AKTIF' : '⚪ BELUM AKTIF'}
          </span>
        </div>

        <div class="modal-tf-gain-box">
          <span class="gain-label">Kenaikan Setelah Dot Green:</span>
          <span class="gain-val ${gainClass}">${gainText || (active ? 'Sinyal Baru Terkonfirmasi' : '-')}</span>
        </div>

        <div class="modal-tf-detail-text">
          <div><b>Waktu Sinyal:</b> ${dateText}</div>
          ${tfObj.dot_close ? `<div><b>Harga Saat Sinyal:</b> Rp ${Number(tfObj.dot_close).toLocaleString('id-ID')}</div>` : ''}
        </div>
      </div>
    `;
  }

  // Helper Parser MACD per Timeframe
  function formatMacdPerTf(macdObj) {
    if (!macdObj) return '<span style="color:var(--text-dim); font-size:11.5px;">- (Netral)</span>';
    const bullRaw = macdObj.bull;
    const bearRaw = macdObj.bear;
    const bullList = Array.isArray(bullRaw) ? bullRaw : (bullRaw && bullRaw.date ? [bullRaw] : []);
    const bearList = Array.isArray(bearRaw) ? bearRaw : (bearRaw && bearRaw.date ? [bearRaw] : []);
    const parts = [];
    if (bullList.length > 0) {
      const bStr = bullList.map(b => `${b.type || 'Bullish'} (${b.date || ''}${b.price ? ' @ Rp ' + b.price : ''})`).join(', ');
      parts.push(`<span style="color:var(--status-green); font-weight:600;">🐂 Bull: ${bStr}</span>`);
    }
    if (bearList.length > 0) {
      const bStr = bearList.map(b => `${b.type || 'Bearish'} (${b.date || ''}${b.price ? ' @ Rp ' + b.price : ''})`).join(', ');
      parts.push(`<span style="color:var(--status-red); font-weight:600;">🐻 Bear: ${bStr}</span>`);
    }
    return parts.length > 0 ? parts.join('<br>') : '<span style="color:var(--text-dim); font-size:11.5px;">- (Netral / Tidak Ada Divergensi)</span>';
  }

  // Helper Parser DonAlt per Timeframe
  function formatDonaltPerTf(donaltObj) {
    if (!donaltObj) return '<span style="color:var(--text-dim); font-size:11.5px;">- (Netral)</span>';
    const g = donaltObj.golden;
    const d = donaltObj.death;
    const parts = [];
    if (g && g.date) {
      const gainExtra = g.gain_pct != null ? ` (+${g.gain_pct.toFixed(1)}%)` : '';
      parts.push(`<span style="color:var(--status-gold); font-weight:600;">✨ Golden: ${g.date}${gainExtra}</span>`);
    }
    if (d && d.date) {
      parts.push(`<span style="color:var(--status-red); font-weight:600;">⚠️ Death: ${d.date}</span>`);
    }
    return parts.length > 0 ? parts.join('<br>') : '<span style="color:var(--text-dim); font-size:11.5px;">- (Netral)</span>';
  }

  // Helper Parser Scalping per Timeframe
  function formatScalpPerTf(scalpObj) {
    if (!scalpObj) return '<span style="color:var(--text-dim); font-size:11.5px;">- (Netral)</span>';
    const trend = scalpObj.trend || '';
    if (!trend || trend === '-') return '<span style="color:var(--text-dim); font-size:11.5px;">- (Netral)</span>';
    if (trend.includes('BUY') || trend.includes('Green')) {
      return `<span style="color:var(--status-green); font-weight:700;">🟢 ${trend}</span>`;
    }
    if (trend.includes('SELL') || trend.includes('Red')) {
      return `<span style="color:var(--status-red); font-weight:700;">🔴 ${trend}</span>`;
    }
    return `<span style="color:var(--text-secondary);">${trend}</span>`;
  }

  // Helper Parser SMC per Timeframe
  function formatSmcPerTf(smcObj) {
    const status = typeof smcObj === 'string' ? smcObj : (smcObj?.status_7d || '-');
    if (!status || status === '-') return '<span style="color:var(--text-dim); font-size:11.5px;">- (Area Normal)</span>';
    if (status.includes('BREAKOUT')) {
      return `<span style="color:var(--status-cyan); font-weight:700;">🔥 ${status}</span>`;
    }
    if (status.includes('DEMAND') || status.includes('Pantulan')) {
      return `<span style="color:var(--status-green); font-weight:600;">🟢 ${status}</span>`;
    }
    return `<span style="color:var(--text-secondary); font-size:11.5px;">${status}</span>`;
  }

  // Evaluasi DonAlt EMA Suite
  const donaltD = tfD.donalt || {};
  const donalt60 = tf60.donalt || {};
  const donalt15 = tf15.donalt || {};

  const hasGolden = (donaltD.golden || donalt60.golden || donalt15.golden);
  const hasDeath = (donaltD.death || donalt60.death || donalt15.death);

  // Evaluasi Scalping Signal
  const scalpD = tfD.scalping || {};
  const scalp60 = tf60.scalping || {};
  const scalp15 = tf15.scalping || {};

  const scalpTrend = scalp60.trend || scalp15.trend || scalpD.trend || "Netral";
  const isScalpBuy = scalpTrend.includes("BUY") || scalpTrend.includes("Green");

  // Evaluasi SMC
  const smcD = tfD.smc?.status_7d || "-";
  const smc60 = tf60.smc?.status_7d || "-";
  const smc15 = tf15.smc?.status_7d || "-";

  // Evaluasi MACD
  const macdD = tfD.macd || {};
  const macd60 = tf60.macd || {};
  const macd15 = tf15.macd || {};

  const modalHtml = `
    <div class="modal-dialog" onclick="event.stopPropagation()">
      
      <!-- Modal Header -->
      <div class="modal-header">
        <div class="modal-title-col">
          <div class="modal-symbol-row">
            <span class="modal-symbol-text">${stock.symbol}</span>
            ${isVip ? `<span class="vip-badge-pill" style="font-size:12px; padding:3px 10px;">💎 FULL 3-DOT GREEN (VIP)</span>` : (stock.count_green === 2 ? `<span class="vip-badge-pill" style="background:var(--status-cyan-bg); color:var(--status-cyan-text); font-size:12px; padding:3px 10px;">⚡ 2-DOT GREEN (POTENSIAL)</span>` : '')}
          </div>
          <span class="modal-name-text">${stock.name || stock.symbol} • Bursa Efek Indonesia (IDX)</span>
        </div>

        <div style="display:flex; align-items:center;">
          <div class="modal-price-col">
            <span class="modal-price-val">${priceFormatted}</span>
            <span class="change-pill ${changeClass}" style="font-size:13px; padding:4px 10px;">${changeFormatted}</span>
          </div>
          <button class="modal-close-btn" onclick="closeModal()" title="Tutup Modal (Esc)">✕</button>
        </div>
      </div>

      <!-- Modal Body -->
      <div class="modal-body">
        
        <!-- SECTION 1: RALLYGOOD DOT GREEN PER TIMEFRAME (1D, 1H, 15M) -->
        <div class="modal-section">
          <div class="modal-sec-title">
            <span>🟢 Sinyal RallyGood Dot Green & Kenaikan Harga</span>
            <span class="modal-sec-badge">${stock.count_green || 0} dari 3 Timeframe (1D, 1H, 15M)</span>
          </div>
          <div class="modal-tf-grid">
            ${renderTfDetailCard("1D", tfD)}
            ${renderTfDetailCard("1H", tf60)}
            ${renderTfDetailCard("15M", tf15)}
          </div>
        </div>

        <!-- SECTION 2 & 3: DONALT EMA + SCALPING SIGNAL -->
        <div class="detail-box-grid">
          
          <!-- DonAlt EMA Suite (1D, 1H, 15M) -->
          <div class="detail-info-card">
            <div class="detail-info-head">
              <span>✨ DonAlt EMA Golden & Death Cross</span>
              <span class="badge-mini">${hasGolden ? 'Bullish' : (hasDeath ? 'Bearish' : 'Netral')}</span>
            </div>
            
            <div class="detail-info-row">
              <span class="detail-info-label">DonAlt (1D):</span>
              <span class="detail-info-value">${formatDonaltPerTf(donaltD)}</span>
            </div>
            <div class="detail-info-row">
              <span class="detail-info-label">DonAlt (1H):</span>
              <span class="detail-info-value">${formatDonaltPerTf(donalt60)}</span>
            </div>
            <div class="detail-info-row">
              <span class="detail-info-label">DonAlt (15M):</span>
              <span class="detail-info-value">${formatDonaltPerTf(donalt15)}</span>
            </div>
          </div>

          <!-- Scalping & Trend Signal (1D, 1H, 15M) -->
          <div class="detail-info-card">
            <div class="detail-info-head">
              <span>⚡ Scalping Signal & Trend</span>
              <span class="modal-tf-status ${isScalpBuy ? 'active' : 'inactive'}">
                ${isScalpBuy ? '🟢 BUY' : '🔴 SELL'}
              </span>
            </div>

            <div class="detail-info-row">
              <span class="detail-info-label">Status Trend:</span>
              <span class="detail-info-value" style="color:${isScalpBuy ? 'var(--status-green)' : 'var(--status-red)'}; font-weight:700;">
                ${scalpTrend}
              </span>
            </div>
            <div class="detail-info-row">
              <span class="detail-info-label">Scalping (1D):</span>
              <span class="detail-info-value">${formatScalpPerTf(scalpD)}</span>
            </div>
            <div class="detail-info-row">
              <span class="detail-info-label">Scalping (1H):</span>
              <span class="detail-info-value">${formatScalpPerTf(scalp60)}</span>
            </div>
            <div class="detail-info-row">
              <span class="detail-info-label">Scalping (15M):</span>
              <span class="detail-info-value">${formatScalpPerTf(scalp15)}</span>
            </div>
            <div class="detail-info-row">
              <span class="detail-info-label">Volume Transaksi:</span>
              <span class="detail-info-value">${volFormatted}</span>
            </div>
          </div>

        </div>

        <!-- SECTION 4 & 5: SMART MONEY CONCEPTS (SMC) & MACD DIVERGENCE -->
        <div class="detail-box-grid">
          
          <!-- Smart Money Concepts (1D, 1H, 15M) -->
          <div class="detail-info-card">
            <div class="detail-info-head">
              <span>🌊 Smart Money Concepts (SMC)</span>
              <span class="badge-mini">Supply & Demand</span>
            </div>

            <div class="detail-info-row">
              <span class="detail-info-label">SMC (1D):</span>
              <span class="detail-info-value">${formatSmcPerTf(smcD)}</span>
            </div>
            <div class="detail-info-row">
              <span class="detail-info-label">SMC (1H):</span>
              <span class="detail-info-value">${formatSmcPerTf(smc60)}</span>
            </div>
            <div class="detail-info-row">
              <span class="detail-info-label">SMC (15M):</span>
              <span class="detail-info-value">${formatSmcPerTf(smc15)}</span>
            </div>
            <div class="detail-info-row">
              <span class="detail-info-label">Area Supply (Resisten):</span>
              <span class="detail-info-value" style="color:var(--status-cyan);">${smc60.includes('Supply') ? smc60.split('|')[0] : 'Area Pantau'}</span>
            </div>
            <div class="detail-info-row">
              <span class="detail-info-label">Area Demand (Support):</span>
              <span class="detail-info-value" style="color:var(--status-green);">${smc60.includes('Demand') ? smc60.split('|')[1] || smc60 : 'Area Pantau'}</span>
            </div>
          </div>

          <!-- MACD Divergences (1D, 1H, 15M) -->
          <div class="detail-info-card">
            <div class="detail-info-head">
              <span>📊 MACD Divergences</span>
              <span class="badge-mini">1D • 1H • 15M</span>
            </div>

            <div class="detail-info-row">
              <span class="detail-info-label">MACD (1D):</span>
              <span class="detail-info-value">${formatMacdPerTf(macdD)}</span>
            </div>
            <div class="detail-info-row">
              <span class="detail-info-label">MACD (1H):</span>
              <span class="detail-info-value">${formatMacdPerTf(macd60)}</span>
            </div>
            <div class="detail-info-row">
              <span class="detail-info-label">MACD (15M):</span>
              <span class="detail-info-value">${formatMacdPerTf(macd15)}</span>
            </div>
            <div class="detail-info-row">
              <span class="detail-info-label">Keterangan:</span>
              <span class="detail-info-value" style="font-size:11px; color:var(--text-muted);">
                Sinyal divergensi konfirmasi pembalikan arah harga (Bull / Bear Reversal)
              </span>
            </div>
          </div>

        </div>

      </div>

      <!-- Modal Footer -->
      <div class="modal-footer">
        <a href="${tvUrl}" target="_blank" rel="noopener noreferrer" class="modal-tv-btn">
          <span>Buka Chart Interaktif di TradingView</span>
          <span>↗</span>
        </a>
        <button class="modal-close-action-btn" onclick="closeModal()">Tutup</button>
      </div>

    </div>
  `;

  // Pastikan element modal backdrop ada di DOM
  let modalContainer = document.getElementById("detailModal");
  if (!modalContainer) {
    modalContainer = document.createElement("div");
    modalContainer.id = "detailModal";
    modalContainer.className = "modal-backdrop";
    modalContainer.onclick = function(e) {
      if (e.target === modalContainer) closeModal();
    };
    document.body.appendChild(modalContainer);
  }

  modalContainer.innerHTML = modalHtml;
  modalContainer.classList.add("open");
  document.body.style.overflow = "hidden"; // lock background scroll
}

function closeModal() {
  const modalContainer = document.getElementById("detailModal");
  if (modalContainer) {
    modalContainer.classList.remove("open");
  }
  document.body.style.overflow = "";
}

// Tutup modal dengan tombol Escape keyboard
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeModal();
  }
});

// Theme Toggle (Light / Dark) SVG Icons
const SUN_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="theme-svg sun-svg"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="m4.93 4.93 1.41 1.41"></path><path d="m17.66 17.66 1.41 1.41"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="m6.34 17.66-1.41 1.41"></path><path d="m19.07 4.93-1.41 1.41"></path></svg>`;

const MOON_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="theme-svg moon-svg"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"></path></svg>`;

function updateThemeIcon(isDark) {
  const icon = isDark ? SUN_SVG : MOON_SVG;
  const desk = document.getElementById("themeIcon");
  if (desk) desk.innerHTML = icon;
  const mob = document.getElementById("themeIconMobile");
  if (mob) mob.innerHTML = icon;
}

function initTheme() {
  const savedTheme = localStorage.getItem("hunter_theme") || "light";
  if (savedTheme === "dark") {
    document.body.classList.remove("light-theme");
    document.body.classList.add("dark-theme");
    updateThemeIcon(true);
  } else {
    document.body.classList.remove("dark-theme");
    document.body.classList.add("light-theme");
    updateThemeIcon(false);
  }
}

function toggleTheme() {
  if (document.body.classList.contains("dark-theme")) {
    document.body.classList.remove("dark-theme");
    document.body.classList.add("light-theme");
    localStorage.setItem("hunter_theme", "light");
    updateThemeIcon(false);
  } else {
    document.body.classList.remove("light-theme");
    document.body.classList.add("dark-theme");
    localStorage.setItem("hunter_theme", "dark");
    updateThemeIcon(true);
  }
}

// Mobile Sidebar Toggle
function toggleSidebar(forceState = null) {
  const sidebar = document.getElementById("appSidebar");
  const backdrop = document.getElementById("sidebarBackdrop");
  if (!sidebar || !backdrop) return;
  const shouldOpen = forceState !== null ? forceState : !sidebar.classList.contains("open");

  if (shouldOpen) {
    sidebar.classList.add("open");
    backdrop.classList.add("show");
    document.body.style.overflow = "hidden";
  } else {
    sidebar.classList.remove("open");
    backdrop.classList.remove("show");
    if (!document.getElementById("detailModal")?.classList.contains("open")) {
      document.body.style.overflow = "";
    }
  }
}

// Reload Dashboard
function reloadDashboard() {
  loadDatabase();
}
