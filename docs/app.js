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

let currentMode = "daily"; // 'daily' | 'vip' | 'recommendation'
let selectedDate = null;
let searchQuery = "";
let activeFilter = "all"; // 'all' | '3dot' | '2dot' | 'golden' | 'smc' | 'scalp'
let currentSort = "dot_desc"; // 'dot_desc' | 'gain_desc' | 'loss_asc' | 'vol_desc' | 'sym_asc'
let screenerTrendRange = 7; // Default 7 hari (in-memory, kembali ke 7 setiap kali buka web)

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

    // Update Rekomendasi Aranter badge count
    updateRecommendationCount();

    // Update Track Record badge count
    updateTrackRecordCount();

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

// Dropdown state for history dates (jika > 4 tanggal)
let isHistoryDropdownOpen = false;

function toggleHistoryDropdown(event) {
  if (event) event.stopPropagation();
  isHistoryDropdownOpen = !isHistoryDropdownOpen;
  const menu = document.getElementById("historyDropdownMenu");
  const chevron = document.getElementById("historyDropdownChevron");
  if (menu) {
    menu.classList.toggle("open", isHistoryDropdownOpen);
  }
  if (chevron) {
    chevron.classList.toggle("open", isHistoryDropdownOpen);
  }
}

function closeHistoryDropdown() {
  isHistoryDropdownOpen = false;
  const menu = document.getElementById("historyDropdownMenu");
  const chevron = document.getElementById("historyDropdownChevron");
  if (menu) menu.classList.remove("open");
  if (chevron) chevron.classList.remove("open");
}

// Global click-outside listener untuk menutup dropdown riwayat
document.addEventListener("click", (e) => {
  const wrapper = document.getElementById("historyDropdownWrapper");
  if (wrapper && !wrapper.contains(e.target) && isHistoryDropdownOpen) {
    closeHistoryDropdown();
  }
});

// Render Riwayat Per Tanggal (Maks 4 tombol langsung, selebihnya masuk dropdown khusus)
function renderSidebarHistory() {
  const container = document.getElementById("sidebarDateList");
  const availableDates = Object.keys(appData.daily_scans || {}).sort().reverse();

  if (availableDates.length === 0) {
    container.innerHTML = `<div style="font-size:12px; color:var(--text-dim); padding:6px 10px;">Menunggu scan 16:21 WIB</div>`;
    return;
  }

  // Jika tanggal <= 4, tampilkan semua secara langsung
  if (availableDates.length <= 4) {
    let html = "";
    availableDates.forEach((dateKey) => {
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
    return;
  }

  // Jika tanggal > 4: 4 tanggal pertama tampil langsung, sisanya masuk ke dropdown khusus
  const primaryDates = availableDates.slice(0, 4);
  const extraDates = availableDates.slice(4);

  // Cek apakah tanggal yang sedang aktif berada di dalam dropdown (extraDates)
  const isExtraActive = (currentMode === "daily" && extraDates.includes(selectedDate));
  const activeExtraScan = isExtraActive ? appData.daily_scans[selectedDate] : null;

  let html = "";

  // 1. Render 4 tanggal teratas
  primaryDates.forEach((dateKey) => {
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

  // 2. Render dropdown khusus untuk tanggal ke-5 dan seterusnya
  const triggerTitle = isExtraActive
    ? (activeExtraScan?.date_display || selectedDate)
    : `Riwayat Lainnya`;
  const triggerBadge = isExtraActive
    ? (activeExtraScan?.stocks ? activeExtraScan.stocks.length : (activeExtraScan?.summary?.total_screener || 0))
    : null;

  let extraItemsHtml = "";
  extraDates.forEach((dateKey) => {
    const scan = appData.daily_scans[dateKey];
    const isSelected = (currentMode === "daily" && dateKey === selectedDate);
    const dateLabel = scan.date_display || dateKey;
    const stockCount = scan.stocks ? scan.stocks.length : (scan.summary?.total_screener || 0);

    extraItemsHtml += `
      <button class="history-date-btn history-dropdown-item ${isSelected ? 'active' : ''}" onclick="selectHistoryDate('${dateKey}')">
        <div class="history-date-left">
          <span class="history-date-dot"></span>
          <span>${dateLabel}</span>
        </div>
        <span class="history-badge">${stockCount}</span>
      </button>
    `;
  });

  html += `
    <div class="history-dropdown-wrapper" id="historyDropdownWrapper">
      <button type="button" class="history-dropdown-trigger ${isExtraActive ? 'active' : ''}" onclick="toggleHistoryDropdown(event)" title="Buka pilihan tanggal lainnya">
        <div class="history-dropdown-trigger-left">
          <svg class="history-dropdown-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
            <line x1="16" y1="2" x2="16" y2="6"></line>
            <line x1="8" y1="2" x2="8" y2="6"></line>
            <line x1="3" y1="10" x2="18" y2="10"></line>
          </svg>
          <span class="history-dropdown-title">${triggerTitle}</span>
        </div>
        <div style="display:flex; align-items:center; gap:6px; flex-shrink:0;">
          ${triggerBadge !== null ? `<span class="history-badge">${triggerBadge}</span>` : `<span class="badge-mini" style="font-size:9.5px; padding:2px 5px;">+${extraDates.length}</span>`}
          <svg class="history-dropdown-chevron ${isHistoryDropdownOpen ? 'open' : ''}" id="historyDropdownChevron" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="6 9 12 15 18 9"></polyline>
          </svg>
        </div>
      </button>
      <div class="history-dropdown-menu ${isHistoryDropdownOpen ? 'open' : ''}" id="historyDropdownMenu">
        <div class="history-dropdown-menu-inner">
          ${extraItemsHtml}
        </div>
      </div>
    </div>
  `;

  container.innerHTML = html;
}

// Handler Saat Tanggal di Sidebar Diklik
function selectHistoryDate(dateKey) {
  selectedDate = dateKey;
  currentMode = "daily";
  if (currentSort === "score_desc") {
    currentSort = "dot_desc";
  }
  
  // Update state tombol menu utama
  document.getElementById("menuDailyBtn").classList.add("active");
  document.getElementById("menuVipBtn").classList.remove("active");
  const recBtn = document.getElementById("menuRecBtn");
  if (recBtn) recBtn.classList.remove("active");
  
  closeHistoryDropdown();
  renderSidebarHistory();
  renderMainView();
  toggleSidebar(false); // Close sidebar on mobile
}

// Handler Ganti Mode Utama (Daily vs Rekomendasi Aranter vs VIP 3-Dot)
function switchMainMode(mode) {
  currentMode = mode;
  applyGridCardMode(mode);
  document.getElementById("menuDailyBtn").classList.toggle("active", mode === "daily");
  document.getElementById("menuVipBtn").classList.toggle("active", mode === "vip");
  const recBtn = document.getElementById("menuRecBtn");
  if (recBtn) recBtn.classList.toggle("active", mode === "recommendation");
  const trackBtn = document.getElementById("menuTrackRecordBtn");
  if (trackBtn) trackBtn.classList.toggle("active", mode === "trackrecord");

  // Atur default sort sesuai mode
  if (mode === "recommendation") {
    currentSort = "score_desc";
  } else if (mode === "trackrecord") {
    currentSort = "gain_desc";
  } else if (currentSort === "score_desc") {
    currentSort = "dot_desc";
  }
  
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
  searchQuery = val ? val.trim() : "";
  const clearBtn = document.getElementById("searchClearBtn");
  if (clearBtn) {
    clearBtn.style.display = searchQuery ? "flex" : "none";
  }
  renderMainView();
}

function clearSearch() {
  const input = document.getElementById("globalSearchInput");
  if (input) {
    input.value = "";
    input.focus();
  }
  searchQuery = "";
  const clearBtn = document.getElementById("searchClearBtn");
  if (clearBtn) {
    clearBtn.style.display = "none";
  }
  renderMainView();
}

// Handler Sort Selector
function handleSortChange(sortVal) {
  currentSort = sortVal;
  renderMainView();
}

// Helper: Sinkronisasi opsi dropdown pengurutan sesuai mode yang aktif
function syncSortDropdownOptions() {
  const sortSel = document.getElementById("sortSelector");
  if (!sortSel) return;

  if (currentMode === "recommendation") {
    // Khusus Rekomendasi Aranter: hanya di menu ini opsi Skor Rekomendasi ditampilkan
    if (sortSel.dataset.mode !== "recommendation") {
      sortSel.innerHTML = `
        <option value="score_desc">Skor Rekomendasi (Tertinggi)</option>
        <option value="gain_desc">% Kenaikan Tertinggi</option>
        <option value="loss_asc">% Penurunan Terbesar</option>
        <option value="vol_desc">Volume Terbesar</option>
        <option value="sym_asc">Kode Saham (A-Z)</option>
      `;
      sortSel.dataset.mode = "recommendation";
    }
    if (currentSort !== "score_desc" && currentSort !== "gain_desc" && currentSort !== "loss_asc" && currentSort !== "vol_desc" && currentSort !== "sym_asc") {
      currentSort = "score_desc";
    }
  } else if (currentMode === "vip") {
    if (sortSel.dataset.mode !== "vip") {
      sortSel.innerHTML = `
        <option value="dot_desc">Sinyal Terbaru</option>
        <option value="gain_desc">% Kenaikan Tertinggi</option>
        <option value="loss_asc">% Penurunan Terbesar</option>
        <option value="vol_desc">Volume Terbesar</option>
        <option value="sym_asc">Kode Saham (A-Z)</option>
      `;
      sortSel.dataset.mode = "vip";
    }
    if (currentSort === "score_desc") {
      currentSort = "dot_desc";
    }
  } else if (currentMode === "trackrecord") {
    if (sortSel.dataset.mode !== "trackrecord") {
      sortSel.innerHTML = `
        <option value="gain_desc">% Kenaikan Tertinggi (Peak)</option>
        <option value="close_desc">Harga Close Tertinggi</option>
        <option value="vol_desc">Volume Terbesar</option>
        <option value="sym_asc">Kode Saham (A-Z)</option>
      `;
      sortSel.dataset.mode = "trackrecord";
    }
    if (currentSort !== "gain_desc" && currentSort !== "close_desc" && currentSort !== "vol_desc" && currentSort !== "sym_asc") {
      currentSort = "gain_desc";
    }
  } else {
    // Mode Screener Harian
    if (sortSel.dataset.mode !== "daily") {
      sortSel.innerHTML = `
        <option value="dot_desc">Dot Green Terbanyak</option>
        <option value="gain_desc">% Kenaikan Tertinggi</option>
        <option value="loss_asc">% Penurunan Terbesar</option>
        <option value="vol_desc">Volume Terbesar</option>
        <option value="sym_asc">Kode Saham (A-Z)</option>
      `;
      sortSel.dataset.mode = "daily";
    }
    if (currentSort === "score_desc") {
      currentSort = "dot_desc";
    }
  }
  sortSel.value = currentSort;
}

// Main View Render Engine
function renderMainView() {
  syncSortDropdownOptions();
  if (currentMode === "daily") {
    renderDailyView();
  } else if (currentMode === "recommendation") {
    renderRecommendationView();
  } else if (currentMode === "trackrecord") {
    renderTrackRecordView();
  } else {
    renderVipView();
  }
}

// Helper Deteksi DonAlt Golden Cross
function checkHasGolden(s) {
  if (!s || !s.timeframes) return false;
  return ['D', '60', '15'].some(tf => s.timeframes[tf]?.donalt?.golden);
}

// Helper Deteksi SMC Breakout Supply (BOS, CHoCH, Breakout Supply, atau Menguji Resisten)
function checkHasSmcBreakout(s) {
  if (!s || !s.timeframes) return false;
  return ['D', '60', '15'].some(tf => {
    const smc = s.timeframes[tf]?.smc;
    const st = smc?.status_7d || "";
    return st.includes("BREAKOUT") || 
           st.includes("BOS") || 
           st.includes("CHoCH") || 
           (st.includes("Supply") && !st.includes("Di Antara Demand & Supply"));
  });
}

// Helper Deteksi Scalping BUY (Bullish Trend atau histori sinyal BUY dari riwayat)
function checkHasScalpBuy(s, isVipMode = false) {
  if (!s || !s.timeframes) return false;
  return ['D', '60', '15'].some(tf => {
    const sc = s.timeframes[tf]?.scalping;
    if (!sc) return false;
    const trend = sc.trend || "";
    const isTrendBuy = trend.includes("BUY") || trend.includes("Green");
    const isUnreversedBuy = sc.buy != null && !sc.buy.reversed;
    const hasAnyBuy = sc.buy != null && Boolean(sc.buy.date || sc.buy.price);
    
    // Di mode VIP (Riwayat 30 Hari), saham yang memiliki histori sinyal BUY dari periode 30 hari ditampilkan
    if (isVipMode) {
      return isTrendBuy || hasAnyBuy;
    }
    // Di mode Daily scan, prioritaskan trend aktif BUY atau sinyal BUY yang belum reversal
    return isTrendBuy || isUnreversedBuy;
  });
}

// Helper Ekstraksi Informasi Breakout (Tipe, Harga, dan Timeframe)
function extractBreakoutInfo(smcObj, tfName = "") {
  if (!smcObj) return null;
  const st = typeof smcObj === 'string' ? smcObj : (smcObj.status_7d || '');
  if (!st) return null;

  // 1. Cek BOS (Break of Structure)
  const matchBos = st.match(/BOS:\s*(Rp\s*[\d\.,]+)(?:\s+tgl\s+([^)]+))?/i);
  if (matchBos) {
    return {
      type: "BOS",
      tf: tfName,
      price: matchBos[1].trim(),
      date: matchBos[2] ? matchBos[2].trim() : "",
      label: `Breakout BOS (${tfName}) @ ${matchBos[1].trim()}`
    };
  }

  // 2. Cek CHoCH (Change of Character)
  const matchChoch = st.match(/CHoCH:\s*(Rp\s*[\d\.,]+)(?:\s+tgl\s+([^)]+))?/i);
  if (matchChoch) {
    return {
      type: "CHoCH",
      tf: tfName,
      price: matchChoch[1].trim(),
      date: matchChoch[2] ? matchChoch[2].trim() : "",
      label: `Breakout CHoCH (${tfName}) @ ${matchChoch[1].trim()}`
    };
  }

  // 3. Cek BREAKOUT SUPPLY (Menembus Rp ...)
  const matchBreakout = st.match(/BREAKOUT\s+SUPPLY\s*\(Menembus\s*(Rp\s*[\d\.,]+)\)/i);
  if (matchBreakout) {
    return {
      type: "Breakout Supply",
      tf: tfName,
      price: matchBreakout[1].trim(),
      date: "",
      label: `Breakout Supply (${tfName}) @ ${matchBreakout[1].trim()}`
    };
  }

  // 4. Cek jika status BREAKOUT umum dengan level supply
  if (st.includes("BREAKOUT") && smcObj.supply) {
    const pStr = `Rp ${Number(smcObj.supply).toLocaleString('id-ID')}`;
    return {
      type: "Breakout Supply",
      tf: tfName,
      price: pStr,
      date: "",
      label: `Breakout Supply (${tfName}) @ ${pStr}`
    };
  }

  // 5. Cek Menguji Area Supply
  if (st.includes("Menguji Area Supply") && smcObj.supply) {
    const pStr = `Rp ${Math.round(smcObj.supply).toLocaleString('id-ID')}`;
    return {
      type: "Uji Resisten",
      tf: tfName,
      price: pStr,
      date: "",
      label: `Uji Supply (${tfName}) @ ${pStr}`
    };
  }

  return null;
}

// ============================================================================
// REKOMENDASI ARANTER ENGINE & HELPERS (5 KONFLUENSI INDIKATOR)
// ============================================================================

// Kamus Bulan Bahasa Indonesia
const INDO_MONTHS = {
  'Jan': 0, 'Feb': 1, 'Mar': 2, 'Apr': 3, 'Mei': 4, 'Jun': 5,
  'Jul': 6, 'Agu': 7, 'Sep': 8, 'Okt': 9, 'Nov': 10, 'Des': 11
};

// Parser Tanggal Fleksibel (Mendukung format Indonesia '16 Okt 2026' & ISO '2026-10-16')
function parseIndoDate(dateStr) {
  if (!dateStr || typeof dateStr !== 'string') return null;
  const m = dateStr.match(/(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})/);
  if (m) {
    const d = parseInt(m[1], 10);
    const mon = INDO_MONTHS[m[2]] != null ? INDO_MONTHS[m[2]] : 9;
    const y = parseInt(m[3], 10);
    return new Date(y, mon, d);
  }
  if (/^\d{4}-\d{2}-\d{2}/.test(dateStr)) return new Date(dateStr);
  return null;
}

// Helper: Cek Harga di Sekitar atau Condong ke Demand / Support
function checkIsNearOrLeaningDemand(s) {
  if (!s || !s.timeframes) return false;
  return ['D', '60', '15'].some(tf => {
    const smc = s.timeframes[tf]?.smc;
    if (!smc) return false;
    const st = smc.status_7d || "";
    // 1. Status eksplisit area demand, pantulan, atau support
    if (st.includes("Demand") || st.includes("Pantulan") || st.includes("Support")) return true;
    
    // 2. Condong ke demand daripada supply
    const pDem = smc.pct_to_demand;
    const pSup = smc.pct_to_supply;
    if (pDem != null && pSup != null && Math.abs(pDem) <= Math.abs(pSup)) return true;
    
    // 3. Jarak ke demand relatif dekat (<= 15%)
    if (pDem != null && Math.abs(pDem) <= 15) return true;
    
    return false;
  });
}

// Helper: Cek Sinyal Swing atau Scalping Minimal 1 BUY
function checkHasScalpSwingBuy(s) {
  if (!s || !s.timeframes) return false;
  return ['D', '60', '15'].some(tf => {
    const sc = s.timeframes[tf]?.scalping;
    if (!sc) return false;
    const trend = sc.trend || "";
    const isTrendBuy = trend.includes("BUY") || trend.includes("Green");
    const hasAnyBuy = sc.buy != null && Boolean(sc.buy.date || sc.buy.price);
    return isTrendBuy || hasAnyBuy;
  });
}

// Helper: Cek MACD Divergences Minimal 1 BUY (Bullish Divergence)
function checkHasMacdBuy(s) {
  if (!s || !s.timeframes) return false;
  return ['D', '60', '15'].some(tf => {
    const mb = s.timeframes[tf]?.macd?.bull;
    return mb != null && Boolean(mb.date || mb.price);
  });
}

// Helper: Hitung Skor Rekomendasi Aranter & Prioritas Kebaruan Indikator (Recency Score)
function calculateAranterScore(s, refDate) {
  const tf = s.timeframes || {};
  const indicatorDates = {};

  // 1. Golden Cross
  let latestGolden = null;
  ['D', '60', '15'].forEach(tfKey => {
    const dStr = tf[tfKey]?.donalt?.golden?.date;
    const d = parseIndoDate(dStr);
    if (d && (!latestGolden || d > latestGolden)) latestGolden = d;
  });
  if (latestGolden) indicatorDates.golden = latestGolden;

  // 2. Dot Green
  let latestDot = null;
  ['D', '60', '15'].forEach(tfKey => {
    const dStr = tf[tfKey]?.date;
    const d = parseIndoDate(dStr);
    if (d && (!latestDot || d > latestDot)) latestDot = d;
  });
  if (latestDot) indicatorDates.dot = latestDot;

  // 3. Scalping / Swing BUY
  let latestScalp = null;
  ['D', '60', '15'].forEach(tfKey => {
    const dStr = tf[tfKey]?.scalping?.buy?.date;
    const d = parseIndoDate(dStr);
    if (d && (!latestScalp || d > latestScalp)) latestScalp = d;
  });
  if (latestScalp) indicatorDates.scalp = latestScalp;

  // 4. MACD Bull Divergence
  let latestMacd = null;
  ['D', '60', '15'].forEach(tfKey => {
    const dStr = tf[tfKey]?.macd?.bull?.date;
    const d = parseIndoDate(dStr);
    if (d && (!latestMacd || d > latestMacd)) latestMacd = d;
  });
  if (latestMacd) indicatorDates.macd = latestMacd;

  const validDates = Object.values(indicatorDates);
  const maxDate = validDates.length ? new Date(Math.max(...validDates.map(d => d.getTime()))) : refDate;
  const avgDateMs = validDates.length ? (validDates.reduce((a, b) => a + b.getTime(), 0) / validDates.length) : refDate.getTime();
  const avgDate = new Date(avgDateMs);

  const daysAgoLatest = Math.max(0, (refDate.getTime() - maxDate.getTime()) / (1000 * 3600 * 24));
  const daysAgoAvg = Math.max(0, (refDate.getTime() - avgDate.getTime()) / (1000 * 3600 * 24));

  // Penilaian Kebaruan Sinyal (Recency):
  // Dasar nilai 100, terdepresiasi -2.5 per hari untuk sinyal paling baru & -1.5 per hari rata-rata sinyal
  let score = 100 - (daysAgoLatest * 2.5 + daysAgoAvg * 1.5);

  // Bonus konfluensi BOS / CHoCH Breakout
  let hasBOS = false;
  ['D', '60', '15'].forEach(tfKey => {
    const st = tf[tfKey]?.smc?.status_7d || "";
    if (st.includes("BOS") || st.includes("CHoCH") || st.includes("BREAKOUT")) hasBOS = true;
  });
  if (hasBOS) score += 3;

  // Bonus harga sangat dekat demand (<= 5%)
  let isVeryCloseDemand = false;
  ['D', '60', '15'].forEach(tfKey => {
    const pDem = tf[tfKey]?.smc?.pct_to_demand;
    if (pDem != null && Math.abs(pDem) <= 5) isVeryCloseDemand = true;
  });
  if (isVeryCloseDemand) score += 2;

  const finalScore = Math.min(99, Math.max(40, Math.round(score)));
  const latestDateFormatted = maxDate.toLocaleDateString("id-ID", { day: "numeric", month: "short" });

  return {
    score: finalScore,
    latestDate: maxDate,
    latestDateStr: latestDateFormatted,
    daysAgoLatest: Math.round(daysAgoLatest),
    dates: {
      golden: latestGolden ? latestGolden.toLocaleDateString("id-ID", { day: "numeric", month: "short" }) : "-",
      dot: latestDot ? latestDot.toLocaleDateString("id-ID", { day: "numeric", month: "short" }) : "-",
      scalp: latestScalp ? latestScalp.toLocaleDateString("id-ID", { day: "numeric", month: "short" }) : "-",
      macd: latestMacd ? latestMacd.toLocaleDateString("id-ID", { day: "numeric", month: "short" }) : "-"
    }
  };
}

// Helper: Mengambil Seluruh Saham 30 Hari yang Memenuhi Kriteria Rekomendasi Aranter
function getAranterRecommendations() {
  let refDate = new Date();
  if (appData.daily_scans) {
    const dates = Object.keys(appData.daily_scans).sort();
    if (dates.length > 0) {
      const d = parseIndoDate(dates[dates.length - 1]);
      if (d) refDate = d;
    }
  }

  const poolMap = new Map();

  // 1. Kumpulkan dari vip_3dot_history (arsip 30 hari)
  (appData.vip_3dot_history || []).forEach(item => {
    const stock = item.data || item;
    if (stock && stock.symbol && !poolMap.has(stock.symbol)) {
      poolMap.set(stock.symbol, {
        stock: stock,
        scan_date: item.scan_date,
        scan_date_display: item.scan_date_display
      });
    }
  });

  // 2. Kumpulkan dari daily_scans (30 hari terakhir)
  Object.entries(appData.daily_scans || {}).forEach(([dateKey, scanObj]) => {
    (scanObj.stocks || []).forEach(stock => {
      if (stock.count_green === 3 && !poolMap.has(stock.symbol)) {
        poolMap.set(stock.symbol, {
          stock: stock,
          scan_date: dateKey,
          scan_date_display: scanObj.date_display || dateKey
        });
      }
    });
  });

  const list = [];
  for (const [sym, entry] of poolMap.entries()) {
    const s = entry.stock;
    // 5 Filter Konfluensi Aranter:
    // 1. 3 Dot Green
    if (s.count_green !== 3) continue;
    // 2. Minimal 1 Golden Cross
    if (!checkHasGolden(s)) continue;
    // 3. Harga sekitaran / condong ke demand atau support
    if (!checkIsNearOrLeaningDemand(s)) continue;
    // 4. Swing atau Scalping minimal 1 BUY
    if (!checkHasScalpSwingBuy(s)) continue;
    // 5. MACD Divergences minimal 1 BUY (Bullish Div)
    if (!checkHasMacdBuy(s)) continue;

    const scoring = calculateAranterScore(s, refDate);
    s.aranterScore = scoring.score;
    s.aranterMetadata = scoring;

    list.push({
      symbol: s.symbol,
      data: s,
      scan_date: entry.scan_date,
      scan_date_display: entry.scan_date_display,
      aranterScore: scoring.score,
      aranterMetadata: scoring
    });
  }

  // Sort descending berdasarkan skor (indikator paling baru muncul di urutan paling atas)
  list.sort((a, b) => b.aranterScore - a.aranterScore);
  return list;
}

// Helper: Update Badge Counter di Sidebar Menu Rekomendasi Aranter
function updateRecommendationCount() {
  const count = getAranterRecommendations().length;
  const el = document.getElementById("recNavCount");
  if (el) el.innerText = count;
}

// ============================================================================
// TRACK RECORD ENGINE (Bukti Akurasi Sinyal Cuan >= +20%)
// ============================================================================

// Helper: Ambil Saham 3 Rally Good untuk Track Record (Opsi 2: Kenaikan dari Harga Close saat keluar sinyal di screener)
function getTrackRecordStocks() {
  const vipList = appData.vip_3dot_history || [];
  const dailyScans = appData.daily_scans || {};
  const sortedDates = Object.keys(dailyScans).sort();
  const results = [];

  vipList.forEach(item => {
    const s = item.data || item;
    if (!s || !s.symbol) return;
    const sym = s.symbol;

    // Rekam jejak kemunculan saham ini di scan harian (dari yang paling awal)
    const scanHistory = [];
    sortedDates.forEach(dKey => {
      const scan = dailyScans[dKey];
      const sFound = (scan.stocks || []).find(st => st.symbol === sym);
      if (sFound) {
        scanHistory.push({
          date: dKey,
          date_display: scan.date_display || dKey,
          close: Number(sFound.close) || 0,
          high: Number(sFound.high) || Number(sFound.close) || 0,
          low: Number(sFound.low) || Number(sFound.close) || 0,
          count_green: sFound.count_green || 0,
          stock: sFound
        });
      }
    });

    // Opsi 2 (Track Record): Entry adalah harga CLOSE pada hari pertama saham resmi masuk screener
    if (scanHistory.length < 2) {
      // Belum ada hari bursa berikutnya setelah terdeteksi di screener (Day 1)
      return;
    }

    const entryClose = scanHistory[0].close;
    const entryDateDisplay = scanHistory[0].date_display;

    // Subsequent days (Day >= 2):
    // Puncak kenaikan tertinggi dihitung dari harga HIGH (terbang tertinggi) hari-hari berikutnya
    const subsequentHighs = scanHistory.slice(1).map(p => p.high).filter(h => h > 0);
    const subsequentCloses = scanHistory.slice(1).map(p => p.close).filter(c => c > 0);

    if (entryClose <= 0 || subsequentHighs.length === 0) return;

    const peakHighPrice = Math.max(...subsequentHighs);
    const peakGain = ((peakHighPrice - entryClose) / entryClose) * 100;
    const peakClosePrice = Math.max(...subsequentCloses);
    const peakCloseGain = ((peakClosePrice - entryClose) / entryClose) * 100;

    // Syarat Kriteria Track Record: Minimal kenaikan peak high >= +8% dari harga close rekomendasi
    if (peakGain >= 8.0) {
      results.push({
        stock: s,
        vipItem: item,
        symbol: sym,
        name: s.name || sym,
        close: Number(s.close) || peakClosePrice,
        basePrice: entryClose,
        peakPrice: peakHighPrice, // Puncak Kenaikan Tertinggi (High)
        peakGain: Number(peakGain.toFixed(2)),
        peakClosePrice: peakClosePrice,
        peakCloseGain: Number(peakCloseGain.toFixed(2)),
        isLuxury: peakGain >= 25.0,
        detectedDate: entryDateDisplay || "Hari Pertama Sinyal"
      });
    }
  });

  return results.sort((a, b) => b.peakGain - a.peakGain);
}

// Helper: Update Badge Counter di Sidebar Menu Track Record
function updateTrackRecordCount() {
  const count = getTrackRecordStocks().length;
  const el = document.getElementById("trackRecordNavCount");
  if (el) el.innerText = count;
}

// Render Daily Mode (Data Harian)
function renderDailyView() {
  applyGridCardMode("daily");
  const scanData = appData.daily_scans[selectedDate];
  const grid = document.getElementById("stocksGrid");

  document.getElementById("pageMainHeading").innerText = "Screener ARA Hunter";
  document.getElementById("pageSubHeading").innerText = "Do Your Own Research !";

  if (!scanData) {
    document.getElementById("activeDateDisplay").innerText = "Standby Scan Rutin";
    document.getElementById("activeTimeDisplay").innerText = "16:21 WIB";
    document.getElementById("filterResultCount").innerText = "Menunggu data scan";
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">
          <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
        </div>
        <h3>Menunggu Jadwal Scan Saham Jam 16:21 WIB</h3>
        <p style="margin-top:6px; color:var(--text-muted); max-width:480px; margin-left:auto; margin-right:auto;">
          Bot Hunter AI otomatis aktif pasca penutupan bursa IDX jam 16:21 WIB untuk memindai seluruh saham dan memperbarui web secara real-time.
        </p>
      </div>
    `;
    updateTopMetrics(0, 0, 0, 0);
    return;
  }

  if (!scanData.stocks || scanData.stocks.length === 0) {
    document.getElementById("activeDateDisplay").innerText = scanData.date_display || selectedDate;
    document.getElementById("activeTimeDisplay").innerText = scanData.time_display || "16:21 WIB";
    document.getElementById("filterResultCount").innerText = "0 saham terkonfirmasi";
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">
          <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
        </div>
        <h3>Belum Ada Saham Minimal 2 Rally Good Hari Ini</h3>
        <p style="margin-top:6px; color:var(--text-muted); max-width:480px; margin-left:auto; margin-right:auto;">
          Scan tanggal ini telah selesai diproses. Belum ditemukan saham yang mengonfirmasi minimal 2 Rally Good sekaligus.
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
  let countSmc = 0;
  let countScalp = 0;
  scanData.stocks.forEach(s => {
    if (checkHasGolden(s)) countGolden++;
    if (checkHasSmcBreakout(s)) countSmc++;
    if (checkHasScalpBuy(s, false)) countScalp++;
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
  const countGoldEl = document.getElementById("countGoldenFilter");
  if (countGoldEl) countGoldEl.innerText = countGolden;
  const countSmcEl = document.getElementById("countSmcFilter");
  if (countSmcEl) countSmcEl.innerText = countSmc;
  const countScalpEl = document.getElementById("countScalpFilter");
  if (countScalpEl) countScalpEl.innerText = countScalp;

  // Filter Saham
  let filtered = scanData.stocks.filter(s => {
    // 1. Search filter (simbol kode saham atau nama emiten)
    if (searchQuery) {
      const q = searchQuery.toUpperCase();
      const matchSymbol = s.symbol && s.symbol.toUpperCase().includes(q);
      const matchName = s.name && s.name.toUpperCase().includes(q);
      if (!matchSymbol && !matchName) return false;
    }
    // 2. Sinyal filter
    if (activeFilter === "3dot" && s.count_green !== 3) return false;
    if (activeFilter === "2dot" && s.count_green !== 2) return false;
    if (activeFilter === "golden" && !checkHasGolden(s)) return false;
    if (activeFilter === "smc" && !checkHasSmcBreakout(s)) return false;
    if (activeFilter === "scalp" && !checkHasScalpBuy(s, false)) return false;
    return true;
  });

  // Sinkronisasi value dropdown urutkan di UI
  const sortSel = document.getElementById("sortSelector");
  if (sortSel && sortSel.value !== currentSort) {
    sortSel.value = currentSort;
  }

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
  applyGridCardMode("vip");
  const grid = document.getElementById("stocksGrid");
  const vipList = appData.vip_3dot_history || [];

  document.getElementById("pageMainHeading").innerText = "3 Rally Good 1 bulan terakhir";
  document.getElementById("pageSubHeading").innerText = "Do Your Own Research !";

  document.getElementById("activeDateDisplay").innerText = "Riwayat 1 Bulan Terakhir";
  document.getElementById("activeTimeDisplay").innerText = "30 Hari";

  // Hitung metric top & sidebar
  let countGolden = 0;
  let countSmc = 0;
  let countScalp = 0;
  vipList.forEach(item => {
    const s = item.data || {};
    if (checkHasGolden(s)) countGolden++;
    if (checkHasSmcBreakout(s)) countSmc++;
    if (checkHasScalpBuy(s, true)) countScalp++;
  });

  updateMetricCard(0, "VVIP 30 HARI", "tag-gold", vipList.length, "Full Rally Good", "Konfirmasi Multi-Timeframe");
  updateMetricCard(1, "BREAKOUT SMC", "tag-cyan", countSmc, "Breakout Supply / BOS", "Struktur Smart Money");
  updateMetricCard(2, "DONALT CROSS", "tag-green", countGolden, "Golden Cross Aktif", "EMA Bullish Reversal Signal");
  updateMetricCard(3, "SCALP & SWING", "tag-slate", countScalp, "Sinyal BUY Aktif", "Konfirmasi Scalping / Swing");

  // Sinkronisasi value dropdown urutkan di UI
  const sortSel = document.getElementById("sortSelector");
  if (sortSel && sortSel.value !== currentSort) {
    sortSel.value = currentSort;
  }

  // Update Sidebar Filter Counters
  document.getElementById("countAllFilter").innerText = vipList.length;
  document.getElementById("count3DotFilter").innerText = vipList.length;
  document.getElementById("count2DotFilter").innerText = 0;
  const countGoldEl = document.getElementById("countGoldenFilter");
  if (countGoldEl) countGoldEl.innerText = countGolden;
  const countSmcEl = document.getElementById("countSmcFilter");
  if (countSmcEl) countSmcEl.innerText = countSmc;
  const countScalpEl = document.getElementById("countScalpFilter");
  if (countScalpEl) countScalpEl.innerText = countScalp;

  // Filter VIP list berdasarkan search query & sinyal aktif
  let filtered = vipList.filter(item => {
    const s = item.data || {};
    // 1. Search filter (simbol kode saham atau nama emiten)
    if (searchQuery) {
      const q = searchQuery.toUpperCase();
      const matchSymbol = s.symbol && s.symbol.toUpperCase().includes(q);
      const matchName = s.name && s.name.toUpperCase().includes(q);
      if (!matchSymbol && !matchName) return false;
    }
    // 2. Sinyal filter
    if (activeFilter === "3dot" && s.count_green !== 3) return false;
    if (activeFilter === "2dot" && s.count_green !== 2) return false;
    if (activeFilter === "golden" && !checkHasGolden(s)) return false;
    if (activeFilter === "smc" && !checkHasSmcBreakout(s)) return false;
    if (activeFilter === "scalp" && !checkHasScalpBuy(s, true)) return false;
    return true;
  });

  // Sort VIP list sesuai opsi dropdown "Urutkan"
  filtered = sortVipList(filtered);

  document.getElementById("filterResultCount").innerText = `Menampilkan ${filtered.length} dari ${vipList.length} saham Full Rally Good`;

  if (filtered.length === 0) {
    if (vipList.length === 0) {
      grid.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#F59E0B" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>
          </div>
          <h3>Belum Ada Riwayat 3 Rally Good 1 Bulan Terakhir</h3>
          <p>Data akan terisi secara otomatis setiap kali bot scan mendeteksi saham dengan 3 Rally Good aktif.</p>
        </div>
      `;
    } else {
      grid.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.3-4.3"></path></svg>
          </div>
          <h3>Tidak Ditemukan Saham yang Cocok</h3>
          <p>Coba gunakan kata kunci lain atau pilih filter sinyal yang berbeda di sidebar kiri.</p>
        </div>
      `;
    }
    return;
  }

  grid.innerHTML = filtered.map(item => {
    return createStockCardHTML(item.data, item.scan_date_display);
  }).join("");
}

// Render Rekomendasi Aranter View (5 Konfluensi Indikator)
function renderRecommendationView() {
  const grid = document.getElementById("stocksGrid");
  const recList = getAranterRecommendations();

  document.getElementById("pageMainHeading").innerText = "Rekomendasi Aranter";
  document.getElementById("pageSubHeading").innerText = "Do Your Own Research !";

  document.getElementById("activeDateDisplay").innerText = "Rekomendasi Aranter";
  document.getElementById("activeTimeDisplay").innerText = "30 Hari Terakhir";

  // Hitung metric top & sidebar
  let countGolden = 0;
  let countSmc = 0;
  let countScalp = 0;
  recList.forEach(item => {
    const s = item.data || {};
    if (checkHasGolden(s)) countGolden++;
    if (checkHasSmcBreakout(s)) countSmc++;
    if (checkHasScalpBuy(s, true)) countScalp++;
  });

  applyGridCardMode("recommendation");
  const topStock = recList.length > 0 ? recList[0] : null;
  const topScore = topStock ? (topStock.aranterScore || 0) : 0;
  const topSymbol = topStock ? (topStock.data?.symbol || "") : "";

  updateMetricCard(0, "REKOMENDASI", "tag-green", recList.length, "Saham Pilihan Aranter", "Lolos 5 Konfluensi Ketat");
  updateMetricCard(1, "KONFLUENSI", "tag-cyan", "5 / 5", "Standar Emas Aranter", "3-Dot, GC, Demand, Scalp, MACD");
  updateMetricCard(2, "DONALT CROSS", "tag-gold", countGolden, "Golden Cross Aktif", "EMA Bullish Reversal");
  updateMetricCard(3, "SKOR TERATAS", "tag-slate", topScore ? `${topScore}` : "-", topSymbol ? `Skor Tertinggi (${topSymbol})` : "Skor Rekomendasi", "Kemunculan Sinyal Terbaru");

  // Sinkronisasi value dropdown urutkan di UI
  const sortSel = document.getElementById("sortSelector");
  if (sortSel && sortSel.value !== currentSort) {
    sortSel.value = currentSort;
  }

  // Update Sidebar Filter Counters
  document.getElementById("countAllFilter").innerText = recList.length;
  document.getElementById("count3DotFilter").innerText = recList.length;
  document.getElementById("count2DotFilter").innerText = 0;
  const countGoldEl = document.getElementById("countGoldenFilter");
  if (countGoldEl) countGoldEl.innerText = countGolden;
  const countSmcEl = document.getElementById("countSmcFilter");
  if (countSmcEl) countSmcEl.innerText = countSmc;
  const countScalpEl = document.getElementById("countScalpFilter");
  if (countScalpEl) countScalpEl.innerText = countScalp;

  // Filter rekomendasi berdasarkan search query & sinyal aktif
  let filtered = recList.filter(item => {
    const s = item.data || {};
    if (searchQuery) {
      const q = searchQuery.toUpperCase();
      const matchSymbol = s.symbol && s.symbol.toUpperCase().includes(q);
      const matchName = s.name && s.name.toUpperCase().includes(q);
      if (!matchSymbol && !matchName) return false;
    }
    if (activeFilter === "3dot" && s.count_green !== 3) return false;
    if (activeFilter === "2dot" && s.count_green !== 2) return false;
    if (activeFilter === "golden" && !checkHasGolden(s)) return false;
    if (activeFilter === "smc" && !checkHasSmcBreakout(s)) return false;
    if (activeFilter === "scalp" && !checkHasScalpBuy(s, true)) return false;
    return true;
  });

  // Sort sesuai opsi dropdown
  filtered = sortRecommendationList(filtered);

  document.getElementById("filterResultCount").innerText = `Menampilkan ${filtered.length} dari ${recList.length} saham Rekomendasi Aranter`;

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

  // Banner Informatif Konfluensi Aranter
  const bannerHtml = `
    <div class="breakout-banner-box" style="grid-column: 1 / -1; background: linear-gradient(135deg, rgba(16, 185, 129, 0.12), rgba(6, 95, 70, 0.05)); border: 1px solid rgba(16, 185, 129, 0.35);">
      <div class="breakout-banner-header" style="color:var(--brand-accent);">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>
        <span>STANDAR EMAS REKOMENDASI ARANTER</span>
      </div>
      <div class="breakout-banner-sub">
        Memenuhi <b>Rally Good 3-Dot</b>, <b>Golden Cross</b>, <b>Area Demand</b>, <b>Swing/Scalping</b>, dan <b>Sinyal Bull</b>.
      </div>
    </div>
  `;

  const cardsHtml = filtered.map(item => {
    return createStockCardHTML(item.data, item.scan_date_display);
  }).join("");

  grid.innerHTML = bannerHtml + cardsHtml;
}

// Render Track Record Mode (Bukti Saham 3 Rally Good Kenaikan >= +20%)
function renderTrackRecordView() {
  applyGridCardMode("trackrecord");
  const grid = document.getElementById("stocksGrid");
  const trackList = getTrackRecordStocks();

  document.getElementById("pageMainHeading").innerText = "Track Record";
  document.getElementById("pageSubHeading").innerText = "Do Your Own Research !";

  document.getElementById("activeDateDisplay").innerText = "Target Kenaikan \u2265 +8%";
  document.getElementById("activeTimeDisplay").innerText = "30 Hari Terakhir";

  // Hitung metrics
  const totalLolos = trackList.length;
  let maxGain = 0;
  let topStock = null;
  let sumGain = 0;

  trackList.forEach(item => {
    sumGain += item.peakGain;
    if (item.peakGain > maxGain) {
      maxGain = item.peakGain;
      topStock = item;
    }
  });

  const avgGain = totalLolos > 0 ? (sumGain / totalLolos) : 0;

  // HANYA 3 KARTU METRIK:
  // Card 0: Total Saham Lolos >= 8%
  updateMetricCard(
    0,
    "TARGET CUAN \u2265 8%",
    "tag-gold",
    `${totalLolos} Saham`,
    "Total Saham Lolos \u2265 8%",
    "Kenaikan dari harga close saat sinyal terdeteksi"
  );

  // Card 1: Rekor Cuan Tertinggi (Peak) + Close Price
  if (topStock) {
    updateMetricCard(
      1,
      "REKOR PEAK CUAN",
      "tag-green",
      `+${maxGain.toFixed(1)}% (${topStock.symbol})`,
      "Rekor Cuan Tertinggi (Peak High)",
      `Close: Rp ${Number(topStock.close).toLocaleString('id-ID')} \u2022 Entry: Rp ${Number(topStock.basePrice).toLocaleString('id-ID')} \u2794 Peak High: Rp ${Number(topStock.peakPrice).toLocaleString('id-ID')}`
    );
  } else {
    updateMetricCard(1, "REKOR PEAK CUAN", "tag-green", "-", "Rekor Cuan Tertinggi (Peak High)", "Belum ada rekor");
  }

  // Card 2 (metricCardGolden): Hidden by applyGridCardMode("trackrecord")

  // Card 3 (metricCardTotal, wide): Rata-rata Kenaikan
  updateMetricCard(
    3,
    "RATA-RATA CUAN",
    "tag-cyan",
    `+${avgGain.toFixed(1)}%`,
    "Rata-rata Kenaikan",
    `Rata-rata kenaikan puncak seluruh ${totalLolos} saham lolos target`
  );

  // Sinkronisasi value dropdown urutkan di UI
  const sortSel = document.getElementById("sortSelector");
  if (sortSel && sortSel.value !== currentSort) {
    sortSel.value = currentSort;
  }

  // Update Sidebar Filter Counters
  document.getElementById("countAllFilter").innerText = totalLolos;
  document.getElementById("count3DotFilter").innerText = totalLolos;
  document.getElementById("count2DotFilter").innerText = 0;

  let countGolden = 0;
  let countSmc = 0;
  let countScalp = 0;
  trackList.forEach(item => {
    if (checkHasGolden(item.stock)) countGolden++;
    if (checkHasSmcBreakout(item.stock)) countSmc++;
    if (checkHasScalpBuy(item.stock, true)) countScalp++;
  });
  const countGoldEl = document.getElementById("countGoldenFilter");
  if (countGoldEl) countGoldEl.innerText = countGolden;
  const countSmcEl = document.getElementById("countSmcFilter");
  if (countSmcEl) countSmcEl.innerText = countSmc;
  const countScalpEl = document.getElementById("countScalpFilter");
  if (countScalpEl) countScalpEl.innerText = countScalp;

  // Filter list berdasarkan search query & sinyal aktif
  let filtered = trackList.filter(item => {
    const s = item.stock || {};
    if (searchQuery) {
      const q = searchQuery.toUpperCase();
      const matchSymbol = s.symbol && s.symbol.toUpperCase().includes(q);
      const matchName = s.name && s.name.toUpperCase().includes(q);
      if (!matchSymbol && !matchName) return false;
    }
    if (activeFilter === "3dot" && s.count_green !== 3) return false;
    if (activeFilter === "2dot" && s.count_green !== 2) return false;
    if (activeFilter === "golden" && !checkHasGolden(s)) return false;
    if (activeFilter === "smc" && !checkHasSmcBreakout(s)) return false;
    if (activeFilter === "scalp" && !checkHasScalpBuy(s, true)) return false;
    return true;
  });

  // Sort list
  filtered.sort((a, b) => {
    if (currentSort === "gain_desc") {
      return b.peakGain - a.peakGain;
    } else if (currentSort === "close_desc") {
      return b.close - a.close;
    } else if (currentSort === "vol_desc") {
      return (Number(b.stock.volume) || 0) - (Number(a.stock.volume) || 0);
    } else if (currentSort === "sym_asc") {
      return a.symbol.localeCompare(b.symbol);
    }
    return b.peakGain - a.peakGain;
  });

  document.getElementById("filterResultCount").innerText = `Menampilkan ${filtered.length} dari ${totalLolos} saham lolos target \u2265 8%`;

  if (filtered.length === 0) {
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">
          <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#F59E0B" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="6"></circle><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"></path></svg>
        </div>
        <h3>Belum Ada Saham dengan Kenaikan \u2265 +8%</h3>
        <p>Saham 3 Rally Good akan otomatis masuk ke menu ini begitu mencapai target keuntungan minimal +8% sejak terdeteksi di screener.</p>
      </div>
    `;
    return;
  }

  const cardsHtml = filtered.map(item => {
    return createStockCardHTML(item.stock, item.detectedDate, {
      peakGain: item.peakGain,
      isLuxury: item.isLuxury,
      basePrice: item.basePrice,
      peakPrice: item.peakPrice,
      detectedDate: item.detectedDate
    });
  }).join("");

  grid.innerHTML = cardsHtml;
}

// Helper Sorting Logic
function sortStocks(stocks) {
  return [...stocks].sort((a, b) => {
    if (currentSort === "score_desc") {
      const scoreA = a.aranterScore || 0;
      const scoreB = b.aranterScore || 0;
      if (scoreB !== scoreA) return scoreB - scoreA;
      return (Number(b.change) || 0) - (Number(a.change) || 0);
    }
    if (currentSort === "dot_desc") {
      if ((b.count_green || 0) !== (a.count_green || 0)) {
        return (b.count_green || 0) - (a.count_green || 0);
      }
      return (Number(b.change) || 0) - (Number(a.change) || 0);
    }
    if (currentSort === "gain_desc") {
      return (Number(b.change) || 0) - (Number(a.change) || 0);
    }
    if (currentSort === "loss_asc") {
      return (Number(a.change) || 0) - (Number(b.change) || 0);
    }
    if (currentSort === "vol_desc") {
      return (Number(b.volume) || 0) - (Number(a.volume) || 0);
    }
    if (currentSort === "sym_asc") {
      return (a.symbol || "").localeCompare(b.symbol || "");
    }
    return 0;
  });
}

// Helper Sorting Logic untuk VVIP 3-Dot (1 Bulan)
function sortVipList(items) {
  return [...items].sort((itemA, itemB) => {
    const a = itemA.data || {};
    const b = itemB.data || {};

    if (currentSort === "score_desc") {
      const scoreA = itemA.aranterScore || a.aranterScore || 0;
      const scoreB = itemB.aranterScore || b.aranterScore || 0;
      if (scoreB !== scoreA) return scoreB - scoreA;
      return (Number(b.volume) || 0) - (Number(a.volume) || 0);
    }
    if (currentSort === "dot_desc") {
      const dateA = itemA.scan_date || "";
      const dateB = itemB.scan_date || "";
      if (dateB !== dateA) return dateB.localeCompare(dateA);
      return (Number(b.volume) || 0) - (Number(a.volume) || 0);
    }
    if (currentSort === "gain_desc") {
      return (Number(b.change) || 0) - (Number(a.change) || 0);
    }
    if (currentSort === "loss_asc") {
      return (Number(a.change) || 0) - (Number(b.change) || 0);
    }
    if (currentSort === "vol_desc") {
      return (Number(b.volume) || 0) - (Number(a.volume) || 0);
    }
    if (currentSort === "sym_asc") {
      return (a.symbol || "").localeCompare(b.symbol || "");
    }
    return 0;
  });
}

// Helper Sorting Logic Khusus Rekomendasi Aranter
function sortRecommendationList(items) {
  return [...items].sort((itemA, itemB) => {
    const a = itemA.data || itemA;
    const b = itemB.data || itemB;

    if (currentSort === "score_desc") {
      const scoreA = itemA.aranterScore || a.aranterScore || 0;
      const scoreB = itemB.aranterScore || b.aranterScore || 0;
      if (scoreB !== scoreA) return scoreB - scoreA;
      return (Number(b.volume) || 0) - (Number(a.volume) || 0);
    }
    if (currentSort === "gain_desc") {
      return (Number(b.change) || 0) - (Number(a.change) || 0);
    }
    if (currentSort === "loss_asc") {
      return (Number(a.change) || 0) - (Number(b.change) || 0);
    }
    if (currentSort === "vol_desc") {
      return (Number(b.volume) || 0) - (Number(a.volume) || 0);
    }
    if (currentSort === "sym_asc") {
      return (a.symbol || "").localeCompare(b.symbol || "");
    }
    return (itemB.aranterScore || b.aranterScore || 0) - (itemA.aranterScore || a.aranterScore || 0);
  });
}

// Helper: Update Top Metric Cards (Supports 4 Cards: VVIP, Radar Potensial, DonAlt Golden Cross, Saham Pilihan)
function updateMetricCard(cardIndex, tagText, tagClass, numberText, titleText, detailText, hideMeta = false) {
  const tagIds = ["statVipTag", "statPotTag", "statGoldenTag", "statTotalTag"];
  const numIds = ["statVipCount", "statPotCount", "statGoldenCount", "statTotalCount"];
  const titleIds = ["statVipTitle", "statPotTitle", "statGoldenTitle", "statTotalTitle"];
  const detailIds = ["statVipDetail", "statPotDetail", "statGoldenDetail", "statTotalDetail"];
  const metaIds = ["statVipMeta", "statPotMeta", "statGoldenMeta", "statTotalMeta"];

  const tagEl = document.getElementById(tagIds[cardIndex]);
  const numEl = document.getElementById(numIds[cardIndex]);
  const titleEl = document.getElementById(titleIds[cardIndex]);
  const detailEl = document.getElementById(detailIds[cardIndex]);
  const metaEl = document.getElementById(metaIds[cardIndex]);

  if (tagEl) {
    tagEl.innerText = tagText;
    if (tagClass) {
      tagEl.className = `metric-tag ${tagClass}`;
    }
  }
  if (numEl) numEl.innerText = numberText;
  if (titleEl) titleEl.innerText = titleText;
  if (detailEl) detailEl.innerText = detailText;
  if (metaEl) {
    metaEl.style.display = hideMeta ? "none" : "";
  }
}

// Helper: Switch Grid Card Mode (3 cards for Screener & Track Record, 4 cards for Rekomendasi Aranter & VIP)
function applyGridCardMode(mode) {
  const gridSection = document.getElementById("metricsGridSection");
  const cardGolden = document.getElementById("metricCardGolden");
  const cardTotal = document.getElementById("metricCardTotal");
  const periodFilter = document.getElementById("screenerPeriodFilter");
  const totalIcon = document.getElementById("statTotalIcon");
  const sparkBox = document.getElementById("statTotalSparkline");

  if (mode === "daily" || mode === "trackrecord") {
    // 3 Cards Mode (Screener Harian & Track Record)
    if (gridSection) gridSection.classList.remove("mode-4-cards");
    if (cardGolden) cardGolden.style.display = "none";
    if (cardTotal) cardTotal.classList.add("metric-card-wide");
    if (periodFilter) periodFilter.style.display = (mode === "daily") ? "inline-flex" : "none";
    if (totalIcon) totalIcon.style.display = (mode === "daily") ? "none" : "inline-flex";
    if (sparkBox) {
      if (mode === "daily") {
        sparkBox.style.display = "flex";
      } else {
        sparkBox.innerHTML = "";
        sparkBox.style.display = "none";
      }
    }
  } else {
    // 4 Cards Mode (VIP & Rekomendasi Aranter)
    if (gridSection) gridSection.classList.add("mode-4-cards");
    if (cardGolden) cardGolden.style.display = "flex";
    if (cardTotal) cardTotal.classList.remove("metric-card-wide");
    if (periodFilter) periodFilter.style.display = "none";
    if (totalIcon) totalIcon.style.display = "inline-flex";
    if (sparkBox) {
      sparkBox.innerHTML = "";
      sparkBox.style.display = "none";
    }
  }
}

// Global state untuk hover sparkline
window._activeScreenerCount = null;

// Handler tombol filter periode sparkline (7 Hari vs 30 Hari, default 7 hari)
function setScreenerPeriod(days) {
  screenerTrendRange = (days === 30) ? 30 : 7;
  const btn7 = document.getElementById("btnPeriod7");
  const btn30 = document.getElementById("btnPeriod30");
  if (btn7 && btn30) {
    if (screenerTrendRange === 7) {
      btn7.classList.add("active");
      btn30.classList.remove("active");
    } else {
      btn7.classList.remove("active");
      btn30.classList.add("active");
    }
  }
  renderScreenerTrendSparkline();
}

// Helper: Render Sparkline SVG Tren Saham Pilihan Lolos Sinyal (7 Hari atau 30 Hari Terakhir)
function renderScreenerTrendSparkline() {
  const sparkBox = document.getElementById("statTotalSparkline");
  if (!sparkBox) return;

  // Hanya tampil di mode Screener Harian biasa
  if (currentMode !== "daily") {
    sparkBox.innerHTML = "";
    sparkBox.style.display = "none";
    return;
  }
  sparkBox.style.display = "flex";

  // Pastikan tombol filter periode sesuai status aktif saat ini
  const btn7 = document.getElementById("btnPeriod7");
  const btn30 = document.getElementById("btnPeriod30");
  if (btn7 && btn30) {
    if (screenerTrendRange === 7) {
      btn7.classList.add("active");
      btn30.classList.remove("active");
    } else {
      btn7.classList.remove("active");
      btn30.classList.add("active");
    }
  }

  const dailyScans = appData.daily_scans || {};
  const datesAsc = Object.keys(dailyScans).sort();
  if (datesAsc.length === 0) {
    sparkBox.innerHTML = "";
    return;
  }

  // Ambil sesuai filter periode: default 7 hari terakhir, atau 30 hari terakhir
  const rangeCount = (screenerTrendRange === 30) ? 30 : 7;
  const rollingDates = datesAsc.slice(-rangeCount);
  const trendPoints = rollingDates.map(dateKey => {
    const scan = dailyScans[dateKey];
    const total = scan?.summary?.total_screener ?? (scan?.stocks ? scan.stocks.length : 0);
    return {
      date: dateKey,
      dateDisplay: scan?.date_display || dateKey,
      count: Number(total) || 0
    };
  });

  const oldestPoint = trendPoints[0];
  const latestPoint = trendPoints[trendPoints.length - 1];

  // Aturan Warna:
  // - Hijau jika nilai akhir >= nilai awal (tren naik / bertahan, misal 149 -> 157)
  // - Merah jika nilai akhir < nilai awal (tren turun, misal 149 -> 97)
  const isBullish = latestPoint.count >= oldestPoint.count;

  // Catat angka aktif saat ini untuk restore saat mouse leave
  const statNumEl = document.getElementById("statTotalCount");
  if (statNumEl) {
    window._activeScreenerCount = statNumEl.innerText;
  }

  sparkBox.innerHTML = generateInteractiveSparklineSVG(trendPoints, isBullish);
  attachSparklineHoverEvents(sparkBox, trendPoints, isBullish);
}

// Generator SVG Sparkline Halus dengan Area Gradient, Tik Bulat, dan Indikator Interaktif
function generateInteractiveSparklineSVG(trendPoints, isBullish) {
  if (!trendPoints || trendPoints.length === 0) return "";

  const width = 260;
  const height = 55;
  const padX = 8;
  const padY = 8;
  const strokeColor = isBullish ? "#16A34A" : "#DC2626";
  const gradId = isBullish ? "sparklineGradBullWide" : "sparklineGradBearWide";
  const gradRgb = isBullish ? "22, 163, 74" : "220, 38, 38";

  let coords = [];
  if (trendPoints.length === 1) {
    const val = trendPoints[0].count;
    coords = [
      { x: padX, y: height / 2, val: val, date: trendPoints[0].dateDisplay, pctX: 0 },
      { x: width - padX, y: height / 2, val: val, date: trendPoints[0].dateDisplay, pctX: 100 }
    ];
  } else {
    const counts = trendPoints.map(p => p.count);
    const min = Math.min(...counts);
    const max = Math.max(...counts);
    const range = (max - min) || 1;

    coords = trendPoints.map((p, idx) => {
      const x = padX + (idx / (trendPoints.length - 1)) * (width - 2 * padX);
      const y = (height - padY) - ((p.count - min) / range) * (height - 2 * padY);
      const pctX = (x / width) * 100;
      return {
        x: Number(x.toFixed(1)),
        y: Number(y.toFixed(1)),
        val: p.count,
        date: p.dateDisplay,
        pctX: Number(pctX.toFixed(1))
      };
    });
  }

  // Smooth Bezier Curve Path
  let pathLine = `M ${coords[0].x} ${coords[0].y}`;
  for (let i = 0; i < coords.length - 1; i++) {
    const p0 = coords[i];
    const p1 = coords[i + 1];
    const midX = (p0.x + p1.x) / 2;
    pathLine += ` C ${midX} ${p0.y}, ${midX} ${p1.y}, ${p1.x} ${p1.y}`;
  }

  const first = coords[0];
  const last = coords[coords.length - 1];
  const pathArea = `${pathLine} L ${last.x} ${height} L ${first.x} ${height} Z`;

  // Render "Tik" (circles at each date point)
  let ticksSvg = coords.map((c, idx) => {
    const isLast = (idx === coords.length - 1);
    const r = isLast ? 4 : 2.8;
    return `
      <circle class="spark-tick" data-idx="${idx}" cx="${c.x}" cy="${c.y}" r="${r}" fill="#FFFFFF" stroke="${strokeColor}" stroke-width="${isLast ? 2.2 : 1.8}"/>
      ${isLast ? `<circle cx="${c.x}" cy="${c.y}" r="7" fill="${strokeColor}" opacity="0.2"/>` : ''}
    `;
  }).join("");

  return `
    <div class="spark-floating-tooltip" id="sparkFloatingTooltip">
      <span class="spark-tooltip-date" id="sparkTooltipDate"></span>
      <span class="spark-tooltip-sep">•</span>
      <span class="spark-tooltip-count ${isBullish ? '' : 'bearish'}" id="sparkTooltipCount"></span>
    </div>
    <svg class="metric-sparkline-svg" id="sparklineSvgEl" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
      <defs>
        <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="rgba(${gradRgb}, 0.28)"/>
          <stop offset="100%" stop-color="rgba(${gradRgb}, 0.0)"/>
        </linearGradient>
      </defs>
      <!-- Area Gradient Fill -->
      <path d="${pathArea}" fill="url(#${gradId})"/>
      <!-- Curve Line -->
      <path d="${pathLine}" fill="none" stroke="${strokeColor}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
      <!-- Interactive Crosshair Guideline -->
      <line id="sparkCrosshair" x1="0" y1="2" x2="0" y2="${height - 2}" stroke="${strokeColor}" stroke-dasharray="2 2" stroke-width="1.2" opacity="0" style="transition: opacity 0.1s ease;"/>
      <!-- Ticks at each date -->
      <g class="spark-ticks-group">
        ${ticksSvg}
      </g>
      <!-- Focus Dot on Hover -->
      <circle id="sparkFocusDot" cx="0" cy="0" r="5.5" fill="${strokeColor}" stroke="#FFFFFF" stroke-width="2.5" opacity="0" style="transition: opacity 0.1s ease;"/>
      <!-- Invisible Mouse Target Overlay -->
      <rect id="sparkOverlayRect" x="0" y="0" width="${width}" height="${height}" fill="transparent" style="cursor:crosshair;"/>
    </svg>
  `;
}

// Handler Hover & Touch untuk Interaksi Ticks dan Tooltip
function attachSparklineHoverEvents(sparkBox, trendPoints, isBullish) {
  const overlay = sparkBox.querySelector("#sparkOverlayRect");
  const svg = sparkBox.querySelector("#sparklineSvgEl");
  const tooltip = sparkBox.querySelector("#sparkFloatingTooltip");
  const crosshair = sparkBox.querySelector("#sparkCrosshair");
  const focusDot = sparkBox.querySelector("#sparkFocusDot");
  const statNumEl = document.getElementById("statTotalCount");
  const tDateEl = sparkBox.querySelector("#sparkTooltipDate");
  const tCountEl = sparkBox.querySelector("#sparkTooltipCount");

  if (!overlay || !svg) return;

  const width = 260;
  const height = 55;
  const padX = 8;
  const padY = 8;
  const counts = trendPoints.map(p => p.count);
  const min = Math.min(...counts);
  const max = Math.max(...counts);
  const range = (max - min) || 1;

  const coords = trendPoints.map((p, idx) => {
    const x = padX + (idx / Math.max(1, trendPoints.length - 1)) * (width - 2 * padX);
    const y = (height - padY) - ((p.count - min) / range) * (height - 2 * padY);
    const pctX = (x / width) * 100;
    return { x, y, pctX, val: p.count, date: p.dateDisplay };
  });

  function handlePointerMove(e) {
    const rect = svg.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const relX = clientX - rect.left;
    const normX = Math.max(0, Math.min(width, (relX / rect.width) * width));

    // Cari titik terdekat
    let closest = coords[0];
    let minDist = Math.abs(coords[0].x - normX);
    for (let i = 1; i < coords.length; i++) {
      const dist = Math.abs(coords[i].x - normX);
      if (dist < minDist) {
        minDist = dist;
        closest = coords[i];
      }
    }

    // Tampilkan Crosshair & Focus Dot
    if (crosshair) {
      crosshair.setAttribute("x1", closest.x);
      crosshair.setAttribute("x2", closest.x);
      crosshair.style.opacity = "0.7";
    }
    if (focusDot) {
      focusDot.setAttribute("cx", closest.x);
      focusDot.setAttribute("cy", closest.y);
      focusDot.style.opacity = "1";
    }

    // Tampilkan Floating Tooltip
    if (tooltip && tDateEl && tCountEl) {
      tDateEl.innerText = closest.date;
      tCountEl.innerText = `${closest.val} Saham`;

      tooltip.classList.remove("align-right", "align-left");

      if (closest.pctX > 60) {
        // Berada di sisi kanan, posisikan tooltip ke dalam agar tidak kepotong di mobile
        tooltip.style.left = "auto";
        tooltip.style.right = "0px";
        tooltip.style.transform = "translate(0, -100%)";
        tooltip.classList.add("align-right");
      } else if (closest.pctX < 25) {
        // Berada di sisi kiri
        tooltip.style.left = "0px";
        tooltip.style.right = "auto";
        tooltip.style.transform = "translate(0, -100%)";
        tooltip.classList.add("align-left");
      } else {
        // Berada di tengah
        tooltip.style.left = `${closest.pctX}%`;
        tooltip.style.right = "auto";
        tooltip.style.transform = "translate(-50%, -100%)";
      }

      tooltip.classList.add("visible");
    }

    // Update Angka di Card
    if (statNumEl) {
      statNumEl.innerText = closest.val;
    }
  }

  function handlePointerLeave() {
    if (crosshair) crosshair.style.opacity = "0";
    if (focusDot) focusDot.style.opacity = "0";
    if (tooltip) tooltip.classList.remove("visible");
    if (statNumEl && window._activeScreenerCount !== null) {
      statNumEl.innerText = window._activeScreenerCount;
    }
  }

  overlay.addEventListener("mousemove", handlePointerMove);
  overlay.addEventListener("mouseleave", handlePointerLeave);
  overlay.addEventListener("touchstart", handlePointerMove, { passive: true });
  overlay.addEventListener("touchmove", handlePointerMove, { passive: true });
  overlay.addEventListener("touchend", handlePointerLeave);
}

// Backward-compatible updateTopMetrics helper (3 Cards in Screener)
function updateTopMetrics(vipCount, potCount, p3, p4, hideTotalMeta = false) {
  const totalCount = p4 !== undefined ? p4 : p3;
  const hideMeta = typeof p4 === "boolean" ? p4 : hideTotalMeta;

  applyGridCardMode("daily");
  updateMetricCard(0, "VVIP", "tag-gold", vipCount, "Full Rally Good", "Konfirmasi Daily + 1H + 15M");
  updateMetricCard(1, "RADAR POTENSIAL", "tag-cyan", potCount, "2 Rally good", "Siap pantau untuk konfirmasi ke-3");
  updateMetricCard(3, "SAHAM PILIHAN", "tag-slate", totalCount, "Lolos Seleksi Sinyal", "Kualifikasi 2 Rally Good", hideMeta);
  renderScreenerTrendSparkline();
}

// Helper: Generate HTML for Minimalist Stock Card
function createStockCardHTML(stock, vipDateLabel = null, trackRecordInfo = null) {
  const isVip = (currentMode === "trackrecord") ? false : (stock.count_green === 3);
  const tf = stock.timeframes || {};
  const isLuxury = Boolean(trackRecordInfo && trackRecordInfo.isLuxury);
  const cardClass = isLuxury ? "stock-card is-vip track-luxury-card" : (isVip ? "stock-card is-vip" : "stock-card");


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

  // Sinyal DonAlt Golden / Death Cross & Timeframe
  let donaltTfLabel = "";
  let goldenCross = null;
  let deathCross = null;

  if (tf15.donalt?.golden) {
    goldenCross = tf15.donalt.golden;
    donaltTfLabel = "15M";
  } else if (tf60.donalt?.golden) {
    goldenCross = tf60.donalt.golden;
    donaltTfLabel = "1H";
  } else if (tfD.donalt?.golden) {
    goldenCross = tfD.donalt.golden;
    donaltTfLabel = "1D";
  } else if (tf15.donalt?.death) {
    deathCross = tf15.donalt.death;
    donaltTfLabel = "15M";
  } else if (tf60.donalt?.death) {
    deathCross = tf60.donalt.death;
    donaltTfLabel = "1H";
  } else if (tfD.donalt?.death) {
    deathCross = tfD.donalt.death;
    donaltTfLabel = "1D";
  }

  let donaltChip = `<span class="badge-chip chip-neutral">-</span>`;
  if (goldenCross) {
    const gainExtra = goldenCross.gain_pct != null ? ` (+${goldenCross.gain_pct.toFixed(1)}%)` : "";
    donaltChip = `<span class="badge-chip chip-golden">Golden Cross${gainExtra}</span>`;
  } else if (deathCross) {
    donaltChip = `<span class="badge-chip chip-death">Death Cross</span>`;
  }

  // Sinyal SMC & Deteksi Breakout (Harga & Timeframe)
  let smcTfLabel = "1D";
  let smcStatus = tfD.smc?.status_7d || "";
  let breakoutEvent = null;

  // Prioritaskan mencari Breakout (BOS, CHoCH, Breakout Supply) di 1D, 1H, atau 15M
  for (const tfKey of ['D', '60', '15']) {
    const tfCode = tfKey === 'D' ? '1D' : (tfKey === '60' ? '1H' : '15M');
    const bo = extractBreakoutInfo(tf[tfKey]?.smc, tfCode);
    if (bo && (bo.type === 'BOS' || bo.type === 'CHoCH' || bo.type === 'Breakout Supply')) {
      breakoutEvent = bo;
      break;
    }
  }

  let smcChip = `<span class="badge-chip chip-neutral">-</span>`;
  let smcRowTitle = "SMC Area (1D):";

  if (breakoutEvent) {
    smcRowTitle = `Breakout (${breakoutEvent.tf}):`;
    smcChip = `<span class="badge-chip chip-smc-breakout">${breakoutEvent.type} @ ${breakoutEvent.price}</span>`;
  } else {
    if (!smcStatus && tf60.smc?.status_7d) {
      smcStatus = tf60.smc.status_7d;
      smcTfLabel = "1H";
    } else if (!smcStatus && tf15.smc?.status_7d) {
      smcStatus = tf15.smc.status_7d;
      smcTfLabel = "15M";
    }
    smcRowTitle = `SMC Area (${smcTfLabel}):`;
    if (smcStatus) {
      if (smcStatus.includes("BREAKOUT") || smcStatus.includes("BOS") || smcStatus.includes("CHoCH")) {
        smcChip = `<span class="badge-chip chip-smc-breakout">${smcStatus}</span>`;
      } else if (smcStatus.includes("DEMAND") || smcStatus.includes("Pantulan")) {
        smcChip = `<span class="badge-chip chip-smc-demand">${smcStatus}</span>`;
      } else {
        smcChip = `<span class="badge-chip chip-neutral">${smcStatus}</span>`;
      }
    }
  }

  // Sinyal Scalp & Swing Trend / Sinyal BUY
  let scalpTfLabel = "1H";
  let scalpTrend = tf60.scalping?.trend || "";
  let scalpBuyObj = tf60.scalping?.buy || null;

  if (!scalpTrend && tf15.scalping?.trend) {
    scalpTrend = tf15.scalping.trend;
    scalpBuyObj = tf15.scalping?.buy || null;
    scalpTfLabel = "15M";
  } else if (!scalpTrend && tfD.scalping?.trend) {
    scalpTrend = tfD.scalping.trend;
    scalpBuyObj = tfD.scalping?.buy || null;
    scalpTfLabel = "1D";
  }

  if (!scalpBuyObj) {
    for (const tfKey of ['15', '60', 'D']) {
      if (tf[tfKey]?.scalping?.buy) {
        scalpBuyObj = tf[tfKey].scalping.buy;
        scalpTfLabel = tfKey === 'D' ? '1D' : (tfKey === '60' ? '1H' : '15M');
        break;
      }
    }
  }

  let scalpChip = `<span class="badge-chip chip-neutral">-</span>`;
  if (scalpTrend.includes("BUY") || scalpTrend.includes("Green")) {
    scalpChip = `<span class="badge-chip chip-scalp-buy">BUY (${scalpTfLabel})</span>`;
  } else if (scalpBuyObj && scalpBuyObj.price) {
    scalpChip = `<span class="badge-chip chip-scalp-buy">BUY (${scalpTfLabel}) @ Rp ${scalpBuyObj.price}</span>`;
  } else if (scalpTrend.includes("SELL") || scalpTrend.includes("Red")) {
    scalpChip = `<span class="badge-chip chip-scalp-sell">SELL (${scalpTfLabel})</span>`;
  }

  // Sinyal MACD Divergence (Bullish BUY)
  let macdTfLabel = "";
  let macdBullObj = null;
  for (const tfKey of ['15', '60', 'D']) {
    if (tf[tfKey]?.macd?.bull && (tf[tfKey]?.macd?.bull?.date || tf[tfKey]?.macd?.bull?.price)) {
      macdBullObj = tf[tfKey].macd.bull;
      macdTfLabel = tfKey === 'D' ? '1D' : (tfKey === '60' ? '1H' : '15M');
      break;
    }
  }

  let macdChip = `<span class="badge-chip chip-neutral">-</span>`;
  if (macdBullObj) {
    const pStr = macdBullObj.price ? ` @ Rp ${macdBullObj.price}` : "";
    macdChip = `<span class="badge-chip chip-macd-buy">Bullish Div (${macdTfLabel})${pStr}</span>`;
  }

  // VIP or Track Record Date Notification
  let vipDateRow = "";
  if (trackRecordInfo) {
    const entryStr = trackRecordInfo.basePrice ? `Rp ${Number(trackRecordInfo.basePrice).toLocaleString('id-ID')}` : '-';
    const peakStr = trackRecordInfo.peakPrice ? `Rp ${Number(trackRecordInfo.peakPrice).toLocaleString('id-ID')}` : '-';
    vipDateRow = `
      <div style="font-size:11px; font-weight:600; color:var(--text-secondary); margin-top:3px; display:flex; align-items:center; gap:4px; flex-wrap:wrap;">
        <span>Entry Close: <b>${entryStr}</b> \u2794 Peak High: <b>${peakStr}</b></span>
        <span style="opacity:0.8;">(${trackRecordInfo.detectedDate})</span>
      </div>
    `;
  } else if (vipDateLabel) {
    vipDateRow = `
      <div style="font-size:11px; font-weight:600; color:var(--status-gold); margin-top:2px;">
        Terdeteksi VIP: ${vipDateLabel}
      </div>
    `;
  }

  return `
    <article class="${cardClass}" onclick="openStockDetail('${stock.symbol}')" title="Klik untuk melihat analisa detail lengkap">
      
      <!-- Card Header: Symbol & Price -->
      <div class="card-header-row">
        <div class="symbol-col">
          <div class="symbol-badge-box">
            <span class="symbol-text">${stock.symbol}</span>
            ${(stock.count_green === 3) ? `<span class="vip-badge-pill">3-DOT</span>` : (stock.count_green === 2 ? `<span class="vip-badge-pill" style="background:var(--status-cyan-bg); color:var(--status-cyan-text);">2-DOT</span>` : '')}
            ${trackRecordInfo ? `
              <span class="vip-badge-pill" style="${isLuxury ? 'background:linear-gradient(135deg, #F59E0B, #D97706); color:#fff; font-weight:800;' : 'background:var(--status-green-bg); color:var(--status-green-text); border:1px solid rgba(22,163,74,0.3); font-weight:700;'}">
                ${isLuxury ? '★ ' : ''}+${trackRecordInfo.peakGain.toFixed(1)}% PEAK
              </span>
            ` : ''}
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
          <span class="indicator-title">DonAlt EMA${donaltTfLabel ? ` (${donaltTfLabel})` : ''}:</span>
          <div class="indicator-val">${donaltChip}</div>
        </div>
        <div class="indicator-row">
          <span class="indicator-title">${smcRowTitle}</span>
          <div class="indicator-val">${smcChip}</div>
        </div>
        <div class="indicator-row">
          <span class="indicator-title">Scalp/Swing (${scalpTfLabel}):</span>
          <div class="indicator-val">${scalpChip}</div>
        </div>
        ${macdBullObj || currentMode === "recommendation" ? `
        <div class="indicator-row">
          <span class="indicator-title">MACD Div (${macdTfLabel || '15M'}):</span>
          <div class="indicator-val">${macdChip}</div>
        </div>
        ` : ''}
        ${trackRecordInfo ? `
        <div class="indicator-row">
          <span class="indicator-title">Realisasi Cuan:</span>
          <div class="indicator-val">
            <span class="badge-chip ${isLuxury ? 'chip-golden' : 'chip-scalp-buy'}">+${trackRecordInfo.peakGain.toFixed(1)}% Peak High (@ Rp ${trackRecordInfo.peakPrice})</span>
          </div>
        </div>
        ` : ''}
      </div>

      <!-- Card Footer: Volume, Hint, & Direct TradingView Button -->
      <div class="card-footer-row">
        <div class="volume-info">
          <span class="vol-label">Volume Transaksi</span>
          <span class="vol-val">${volFormatted}</span>
        </div>

        <div style="display:flex; align-items:center; gap:8px;">
          <span class="card-click-hint">Detail Analisa</span>
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

  // Cek apakah saham ini masuk dalam Rekomendasi Aranter (5 Konfluensi)
  const recItem = getAranterRecommendations().find(r => r.symbol === stock.symbol);
  const recScore = recItem ? recItem.aranterScore : (stock.aranterScore || null);
  const recMetadata = recItem ? recItem.aranterMetadata : (stock.aranterMetadata || null);

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
            ${active ? 'AKTIF' : 'BELUM AKTIF'}
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
      parts.push(`<span style="color:var(--status-green); font-weight:600;">Bull: ${bStr}</span>`);
    }
    if (bearList.length > 0) {
      const bStr = bearList.map(b => `${b.type || 'Bearish'} (${b.date || ''}${b.price ? ' @ Rp ' + b.price : ''})`).join(', ');
      parts.push(`<span style="color:var(--status-red); font-weight:600;">Bear: ${bStr}</span>`);
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
      parts.push(`<span style="color:var(--status-gold); font-weight:600;">Golden: ${g.date}${gainExtra}</span>`);
    }
    if (d && d.date) {
      parts.push(`<span style="color:var(--status-red); font-weight:600;">Death: ${d.date}</span>`);
    }
    return parts.length > 0 ? parts.join('<br>') : '<span style="color:var(--text-dim); font-size:11.5px;">- (Netral)</span>';
  }

  // Helper Parser Scalping per Timeframe (Menampilkan Waktu, Harga, dan Sinyal SELL/BUY)
  function formatScalpPerTf(scalpObj) {
    if (!scalpObj) return '<span style="color:var(--text-dim); font-size:11.5px;">- (Netral)</span>';
    const trend = scalpObj.trend || '';
    const sell = scalpObj.sell;
    const buy = scalpObj.buy;

    const parts = [];
    if (trend && trend !== '-') {
      const isBuy = trend.includes('BUY') || trend.includes('Green');
      const isSell = trend.includes('SELL') || trend.includes('Red');
      const trendColor = isBuy ? 'var(--status-green)' : (isSell ? 'var(--status-red)' : 'var(--text-secondary)');
      parts.push(`<span style="color:${trendColor}; font-weight:700;">Trend: ${trend}</span>`);
    }

    if (sell && sell.date) {
      const priceStr = sell.price ? ` @ Rp ${Number(sell.price).toLocaleString('id-ID')}` : '';
      parts.push(`<span style="color:var(--status-red); font-weight:600;">SELL: ${sell.date}${priceStr}</span>`);
    }

    if (buy && buy.date) {
      const priceStr = buy.price ? ` @ Rp ${Number(buy.price).toLocaleString('id-ID')}` : '';
      const gainStr = buy.gain_pct != null ? ` (${buy.gain_pct >= 0 ? '+' : ''}${buy.gain_pct.toFixed(1)}%)` : '';
      parts.push(`<span style="color:var(--status-green); font-weight:600;">BUY: ${buy.date}${priceStr}${gainStr}</span>`);
    }

    return parts.length > 0 ? parts.join('<br>') : '<span style="color:var(--text-dim); font-size:11.5px;">- (Netral)</span>';
  }

  // Helper Parser SMC per Timeframe (Menampilkan Level Resisten & Support beserta % dari Harga Sekarang & Breakout)
  function formatSmcPerTf(smcObj, curPrice, tfCode = "") {
    if (!smcObj) return '<span style="color:var(--text-dim); font-size:11.5px;">- (Data Area Belum Termuat)</span>';
    const statusText = typeof smcObj === 'string' ? smcObj : (smcObj.status_7d || '-');
    if (!statusText || statusText === '-') return '<span style="color:var(--text-dim); font-size:11.5px;">- (Data Area Belum Termuat)</span>';

    const sup = typeof smcObj === 'object' && smcObj.supply ? smcObj.supply : null;
    const dem = typeof smcObj === 'object' && smcObj.demand ? smcObj.demand : null;
    const pctSup = typeof smcObj === 'object' && smcObj.pct_to_supply != null ? smcObj.pct_to_supply : (sup && curPrice ? ((sup - curPrice) / curPrice * 100) : null);
    const pctDem = typeof smcObj === 'object' && smcObj.pct_to_demand != null ? smcObj.pct_to_demand : (dem && curPrice ? ((dem - curPrice) / curPrice * 100) : null);

    const bo = extractBreakoutInfo(smcObj, tfCode);

    let statusColor = "var(--text-secondary)";
    if (bo || statusText.includes("BREAKOUT")) statusColor = "var(--status-cyan)";
    else if (statusText.includes("DEMAND") || statusText.includes("Pantulan")) statusColor = "var(--status-green)";
    else if (statusText.includes("BREAKDOWN")) statusColor = "var(--status-red)";

    const parts = [];

    // Jika ada Breakout spesifik di timeframe ini, tampilkan badge breakout harga dan TF
    if (bo && (bo.type === 'BOS' || bo.type === 'CHoCH' || bo.type === 'Breakout Supply')) {
      parts.push(`
        <div class="breakout-smc-badge">
          🔥 BREAKOUT ${bo.type.toUpperCase()}${tfCode ? ` (${tfCode})` : ''} @ ${bo.price}${bo.date ? ` (tgl ${bo.date})` : ''}
        </div>
      `);
    }

    parts.push(`<div style="color:${statusColor}; font-weight:700;">${statusText}</div>`);

    const levels = [];
    if (sup) {
      const supPctStr = pctSup != null ? ` (${pctSup >= 0 ? '+' : ''}${pctSup.toFixed(1)}% dari harga sekarang)` : '';
      levels.push(`<span style="color:var(--status-cyan); font-weight:600;">Resisten (Supply): Rp ${Number(sup).toLocaleString('id-ID')}${supPctStr}</span>`);
    } else {
      levels.push(`<span style="color:var(--status-cyan); font-weight:600;">Resisten (Supply): Area Pantau Tertinggi</span>`);
    }
    if (dem) {
      const demPctStr = pctDem != null ? ` (${pctDem >= 0 ? '+' : ''}${pctDem.toFixed(1)}% dari harga sekarang)` : '';
      levels.push(`<span style="color:var(--status-green); font-weight:600;">Support (Demand): Rp ${Number(dem).toLocaleString('id-ID')}${demPctStr}</span>`);
    } else {
      levels.push(`<span style="color:var(--status-green); font-weight:600;">Support (Demand): Area Pantau Terendah</span>`);
    }

    if (levels.length > 0) {
      parts.push(`<div style="font-size:11px; margin-top:3px; line-height:1.45;">${levels.join('<br>')}</div>`);
    }

    return parts.join('');
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
  const smcD = tfD.smc || {};
  const smc60 = tf60.smc || {};
  const smc15 = tf15.smc || {};

  // Evaluasi MACD
  const macdD = tfD.macd || {};
  const macd60 = tf60.macd || {};
  const macd15 = tf15.macd || {};

  // Evaluasi Breakout di seluruh TF (1D, 1H, 15M)
  const allBreakouts = [];
  [
    { tf: '1D', smc: smcD },
    { tf: '1H', smc: smc60 },
    { tf: '15M', smc: smc15 }
  ].forEach(item => {
    const b = extractBreakoutInfo(item.smc, item.tf);
    if (b && (b.type === 'BOS' || b.type === 'CHoCH' || b.type === 'Breakout Supply')) {
      allBreakouts.push(b);
    }
  });

  const breakoutBannerHtml = allBreakouts.length > 0 ? `
    <div class="breakout-banner-box">
      <div class="breakout-banner-header">
        <span>🔥 BREAKOUT TERDETEKSI:</span>
        <span class="breakout-banner-sub">(Struktur Smart Money / Supply Tembus)</span>
      </div>
      <div class="breakout-banner-grid">
        ${allBreakouts.map(b => `
          <div class="breakout-pill-item">
            <span>${b.type} (${b.tf})</span>
            <span style="opacity:0.65;">@</span>
            <span class="breakout-pill-price">${b.price}</span>
            ${b.date ? `<span class="breakout-pill-date">(${b.date})</span>` : ''}
          </div>
        `).join('')}
      </div>
    </div>
  ` : '';

  const starIconSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px; flex-shrink:0;"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>`;

  // --------------------------------------------------------------------------
  // RIWAYAT PERFORMA SINYAL (30 HARI BURSA) - KHUSUS SAHAM 3 RALLY GOOD / VIP
  // --------------------------------------------------------------------------
  const vipEntry = (appData.vip_3dot_history || []).find(h => h.symbol === stock.symbol || h.data?.symbol === stock.symbol);
  const isVipTracked = Boolean(vipEntry) || stock.count_green === 3;
  let perfSectionHtml = '';

  if (isVipTracked) {
    const currentClose = Number(stock.close) || 0;

    // 1. METRIK OPSI 1: Kenaikan Setelah Dot Green (TradingView)
    let dotClosePrice = null;
    let dotDateDisplay = null;
    if (tf15.dot_close) {
      dotClosePrice = Number(tf15.dot_close);
      dotDateDisplay = cleanDate(tf15.date);
    } else if (tf60.dot_close) {
      dotClosePrice = Number(tf60.dot_close);
      dotDateDisplay = cleanDate(tf60.date);
    } else if (tfD.dot_close) {
      dotClosePrice = Number(tfD.dot_close);
      dotDateDisplay = cleanDate(tfD.date);
    } else if (vipEntry?.base_price) {
      dotClosePrice = Number(vipEntry.base_price);
      dotDateDisplay = vipEntry.scan_date_display || null;
    }

    const dotGainVal = (dotClosePrice && dotClosePrice > 0) ? (((currentClose - dotClosePrice) / dotClosePrice) * 100) : null;
    const dotGainSign = (dotGainVal !== null && dotGainVal > 0) ? "+" : "";
    const dotGainClass = dotGainVal > 0 ? "positive" : (dotGainVal < 0 ? "negative" : "neutral");

    // 2. METRIK OPSI 2: Kenaikan Setelah Masuk Rekomendasi Screener (Track Record)
    const dailyScans = appData.daily_scans || {};
    const sortedScanDates = Object.keys(dailyScans).sort();
    const scanHistory = [];
    sortedScanDates.forEach(dKey => {
      const scan = dailyScans[dKey];
      const sFound = (scan.stocks || []).find(st => st.symbol === stock.symbol);
      if (sFound) {
        scanHistory.push({
          date: dKey,
          date_display: scan.date_display ? scan.date_display.split(' ').slice(0, 2).join(' ') : dKey,
          full_date_display: scan.date_display || dKey,
          close: Number(sFound.close) || 0,
          high: Number(sFound.high) || Number(sFound.close) || 0,
          low: Number(sFound.low) || Number(sFound.close) || 0,
          change: Number(sFound.change) || 0,
          count_green: sFound.count_green || 0
        });
      }
    });

    let recEntryClose = null;
    let recEntryDateDisplay = null;
    let recPeakHigh = null;
    let recPeakGainVal = null;
    let recGainVal = null;

    if (scanHistory.length > 0) {
      recEntryClose = scanHistory[0].close;
      recEntryDateDisplay = scanHistory[0].full_date_display;
      if (recEntryClose > 0) {
        recGainVal = ((currentClose - recEntryClose) / recEntryClose) * 100;
        if (scanHistory.length > 1) {
          recPeakHigh = Math.max(...scanHistory.slice(1).map(h => h.high));
          recPeakGainVal = ((recPeakHigh - recEntryClose) / recEntryClose) * 100;
        }
      }
    }

    const recGainSign = (recGainVal !== null && recGainVal > 0) ? "+" : "";
    const recGainClass = recGainVal > 0 ? "positive" : (recGainVal < 0 ? "negative" : "neutral");

    // TENTUKAN DATA GRAFIK & TABEL PERFORMA (KRONOLOGIS BURSA)
    // Menggunakan riwayat scan bursa berurutan dari hari pertama saham masuk screener
    let perfHistory = [];
    let basePrice = null;
    let firstDetectedDate = null;

    if (vipEntry && Array.isArray(vipEntry.performance_history) && vipEntry.performance_history.length > 0) {
      basePrice = Number(vipEntry.base_price) || (Number(vipEntry.performance_history[0]?.close) || currentClose);
      firstDetectedDate = vipEntry.scan_date_display || vipEntry.performance_history[0]?.date_display;
      perfHistory = vipEntry.performance_history.map(item => ({
        ...item,
        high: Number(item.high) || Number(item.close) || 0,
        low: Number(item.low) || Number(item.close) || 0
      }));
    } else if (scanHistory.length > 0) {
      basePrice = recEntryClose || scanHistory[0].close;
      firstDetectedDate = recEntryDateDisplay || scanHistory[0].full_date_display;
      perfHistory = scanHistory.map((sh, idx) => {
        const cum = basePrice > 0 ? ((sh.close - basePrice) / basePrice) * 100 : 0;
        return {
          date: sh.date,
          date_display: sh.date_display,
          close: sh.close,
          high: sh.high,
          low: sh.low,
          daily_change_pct: idx === 0 ? 0.0 : sh.change,
          cumulative_gain_pct: Number(cum.toFixed(2)),
          count_green: sh.count_green
        };
      });
    }

    // Fallback jika perfHistory masih kosong
    if (perfHistory.length === 0) {
      basePrice = currentClose;
      firstDetectedDate = selectedDate || "Hari Ini";
      perfHistory = [{
        date: selectedDate || "today",
        date_display: "Hari Ini",
        close: basePrice,
        high: basePrice,
        low: basePrice,
        daily_change_pct: Number(changeVal.toFixed(2)),
        cumulative_gain_pct: 0.0,
        count_green: stock.count_green || 0
      }];
    }

    // Ringkasan Performa
    const latestPerf = perfHistory[perfHistory.length - 1];
    const totalCumGain = latestPerf ? Number(latestPerf.cumulative_gain_pct || 0) : 0;
    const cumSign = totalCumGain > 0 ? "+" : "";
    const cumClass = totalCumGain > 0 ? "positive" : (totalCumGain < 0 ? "negative" : "flat");
    const cumFormatted = `${cumSign}${totalCumGain.toFixed(2)}%`;
    const basePriceFormatted = basePrice ? "Rp " + Number(basePrice).toLocaleString("id-ID") : priceFormatted;
    const allPrices = perfHistory.map(item => Number(item.close) || 0);
    const allHighs = perfHistory.map(item => Number(item.high || item.close) || 0);
    const allLows = perfHistory.map(item => Number(item.low || item.close) || 0);
    const minPriceVal = allLows.length > 0 ? Math.min(...allLows) : 0;
    const maxPriceVal = allHighs.length > 0 ? Math.max(...allHighs) : 0;
    const entryPriceVal = Number(basePrice) || (allPrices[0] || 0);
    const latestPriceVal = latestPerf ? Number(latestPerf.close) : entryPriceVal;
    const minGainPct = entryPriceVal > 0 ? (((minPriceVal - entryPriceVal) / entryPriceVal) * 100) : 0;
    const maxGainPct = entryPriceVal > 0 ? (((maxPriceVal - entryPriceVal) / entryPriceVal) * 100) : 0;

  // Generator Chart Area Trendline Halus (Smooth Spline Curve)
  function generatePerfChartSvg(hist) {
    if (!hist || hist.length === 0) return '';
    const w = 600;
    const h = 135;
    const padL = 16;
    const padR = 64; // space for price text on right
    const padT = 16;
    const padB = 22; // space for date text on bottom

    const chartW = w - padL - padR;
    const chartH = h - padT - padB;
    const centerX = padL + chartW / 2;
    const centerY = padT + chartH / 2;

    const prices = hist.map(item => Number(item.close) || 0);

    // KONDISI KHUSUS: MASIH 1 HARI BURSA (Titik & Label Cukup di Tengah)
    if (hist.length === 1) {
      const pVal = prices[0];
      const dateText = hist[0].date_display || 'Hari ke-1';
      return `
        <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
          <!-- Garis Referensi Horizontal Tunggal di Tengah -->
          <line x1="${padL}" y1="${centerY.toFixed(1)}" x2="${(padL + chartW).toFixed(1)}" y2="${centerY.toFixed(1)}" stroke="var(--border-light)" stroke-dasharray="3 3" opacity="0.6" />
          <text x="${(padL + chartW + 6).toFixed(1)}" y="${(centerY + 3.5).toFixed(1)}" font-size="9.5" font-weight="700" fill="var(--status-green)" text-anchor="start">Rp ${pVal.toLocaleString('id-ID')}</text>

          <!-- Titik Tunggal di Tengah Canvas dengan Pulse Indicator -->
          <circle cx="${centerX.toFixed(1)}" cy="${centerY.toFixed(1)}" r="10" fill="rgba(16, 185, 129, 0.15)" stroke="var(--status-green)" stroke-width="1.2" opacity="0.7" />
          <circle cx="${centerX.toFixed(1)}" cy="${centerY.toFixed(1)}" r="5" fill="#ffffff" stroke="var(--status-green)" stroke-width="2.5">
            <title>${dateText}: Rp ${pVal.toLocaleString('id-ID')} (${hist[0].daily_change_pct > 0 ? '+' : ''}${hist[0].daily_change_pct}% hari ini • Modal Entry)</title>
          </circle>

          <!-- Sumbu X: CUKUP LABEL TANGGAL DI TENGAH -->
          <text x="${centerX.toFixed(1)}" y="${h - 5}" font-size="9" font-weight="700" fill="var(--text-secondary)" text-anchor="middle">${dateText}</text>
        </svg>
      `;
    }

    // KONDISI MULTI-HARI (> 1 HARI BURSA)
    const minP = Math.min(...prices);
    const maxP = Math.max(...prices);
    const rangeP = (maxP - minP) || 1;
    const midP = Math.round((maxP + minP) / 2);

    const points = hist.map((item, idx) => {
      const x = padL + (idx / (hist.length - 1)) * chartW;
      const y = padT + chartH - ((item.close - minP) / rangeP) * chartH;
      return { x, y, item, idx };
    });

    const isUp = (hist[hist.length - 1].close >= hist[0].close);
    const strokeColor = isUp ? '#10B981' : '#EF4444';
    const gradStart = isUp ? 'rgba(16, 185, 129, 0.35)' : 'rgba(239, 68, 68, 0.35)';
    const gradId = 'perfGradArea_' + (stock.symbol || 'sym').replace(/[^a-zA-Z0-9]/g, '');

    // Algoritma Smooth Spline Bezier Curve (Cubic Catmull-Rom)
    let splineD = `M ${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[i === 0 ? i : i - 1];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = points[i + 2 < points.length ? i + 2 : i + 1];
      const cp1x = p1.x + (p2.x - p0.x) / 6;
      const cp1y = p1.y + (p2.y - p0.y) / 6;
      const cp2x = p2.x - (p3.x - p1.x) / 6;
      const cp2y = p2.y - (p3.y - p1.y) / 6;
      splineD += ` C ${cp1x.toFixed(1)} ${cp1y.toFixed(1)}, ${cp2x.toFixed(1)} ${cp2y.toFixed(1)}, ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
    }
    const areaD = `${splineD} L ${(padL + chartW).toFixed(1)} ${(padT + chartH).toFixed(1)} L ${padL.toFixed(1)} ${(padT + chartH).toFixed(1)} Z`;

    const midY = (padT + padT + chartH) / 2;
    const startPt = points[0];
    const endPt = points[points.length - 1];

    return `
      <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
        <defs>
          <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="${gradStart}" />
            <stop offset="100%" stop-color="${gradStart}" stop-opacity="0" />
          </linearGradient>
          <filter id="glow_${gradId}" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="${strokeColor}" flood-opacity="0.35" />
          </filter>
        </defs>

        <!-- Horizontal Reference Gridlines & Price Tags -->
        <line x1="${padL}" y1="${padT}" x2="${padL + chartW}" y2="${padT}" stroke="var(--border-light)" stroke-dasharray="3 3" opacity="0.6" />
        <text x="${padL + chartW + 6}" y="${padT + 3.5}" font-size="9" font-weight="700" fill="var(--status-green)" text-anchor="start">Rp ${maxP.toLocaleString('id-ID')}</text>

        <line x1="${padL}" y1="${midY.toFixed(1)}" x2="${padL + chartW}" y2="${midY.toFixed(1)}" stroke="var(--border-light)" stroke-dasharray="2 4" opacity="0.4" />
        <text x="${padL + chartW + 6}" y="${(midY + 3.5).toFixed(1)}" font-size="8.5" font-weight="600" fill="var(--text-muted)" text-anchor="start">Rp ${midP.toLocaleString('id-ID')}</text>

        <line x1="${padL}" y1="${padT + chartH}" x2="${padL + chartW}" y2="${padT + chartH}" stroke="var(--border-light)" stroke-dasharray="3 3" opacity="0.6" />
        <text x="${padL + chartW + 6}" y="${padT + chartH + 3.5}" font-size="9" font-weight="700" fill="var(--status-red)" text-anchor="start">Rp ${minP.toLocaleString('id-ID')}</text>

        <!-- Shaded Area & Glowing Curve Line -->
        <path d="${areaD}" fill="url(#${gradId})" />
        <path d="${splineD}" fill="none" stroke="${strokeColor}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" filter="url(#glow_${gradId})" />

        <!-- Interactive Micro-Dots on All Points with Native Tooltips -->
        ${points.map(p => `
          <circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="2.5" fill="${strokeColor}" opacity="0.85" class="perf-chart-dot">
            <title>${p.item.date_display}: Rp ${Number(p.item.close).toLocaleString('id-ID')} (${p.item.daily_change_pct > 0 ? '+' : ''}${p.item.daily_change_pct}% hari ini • ${p.item.cumulative_gain_pct > 0 ? '+' : ''}${p.item.cumulative_gain_pct}% kumulatif)</title>
          </circle>
        `).join('')}

        <!-- Entry Dot Indicator (Day 1) -->
        <circle cx="${startPt.x.toFixed(1)}" cy="${startPt.y.toFixed(1)}" r="4" fill="#ffffff" stroke="${strokeColor}" stroke-width="2.2" />

        <!-- Current/Now Dot Indicator (Day 31) with Pulse Ring -->
        <circle cx="${endPt.x.toFixed(1)}" cy="${endPt.y.toFixed(1)}" r="4.5" fill="#ffffff" stroke="${strokeColor}" stroke-width="2.5" />
        <circle cx="${endPt.x.toFixed(1)}" cy="${endPt.y.toFixed(1)}" r="8" fill="none" stroke="${strokeColor}" stroke-width="1.5" opacity="0.5" />

        <!-- X-Axis Dates -->
        <text x="${padL}" y="${h - 5}" font-size="8.5" font-weight="600" fill="var(--text-muted)" text-anchor="start">${hist[0].date_display.split(' ').slice(0, 2).join(' ')} (Entry)</text>
        ${hist.length >= 3 ? `<text x="${(padL + chartW / 2).toFixed(1)}" y="${h - 5}" font-size="8.5" font-weight="600" fill="var(--text-muted)" text-anchor="middle">${hist[Math.floor(hist.length / 2)].date_display.split(' ').slice(0, 2).join(' ')}</text>` : ''}
        <text x="${(padL + chartW).toFixed(1)}" y="${h - 5}" font-size="8.5" font-weight="600" fill="var(--text-muted)" text-anchor="end">${hist[hist.length - 1].date_display.split(' ').slice(0, 2).join(' ')} (Hari ${hist.length})</text>
      </svg>
    `;
  }

  // Generator Baris Tabel Riwayat Harian
  const perfRowsHtml = perfHistory.map((item, idx) => {
    const dayChg = Number(item.daily_change_pct || 0);
    const daySign = dayChg > 0 ? "+" : "";
    const dayColor = dayChg > 0 ? "var(--status-green)" : (dayChg < 0 ? "var(--status-red)" : "var(--text-muted)");
    
    const cumG = Number(item.cumulative_gain_pct || 0);
    const cumGSign = cumG > 0 ? "+" : "";
    const cumGColor = cumG > 0 ? "var(--status-green)" : (cumG < 0 ? "var(--status-red)" : "var(--text-muted)");

    let dotBadge = `<span class="perf-badge-dot dot-off" style="color:var(--text-secondary); background:rgba(148, 163, 184, 0.15); border:1px solid rgba(148, 163, 184, 0.25);">⚪ Masa Pantau</span>`;
    if (idx === 0) {
      dotBadge = (currentMode === "trackrecord")
        ? `<span class="perf-badge-dot dot-3">🟢 Entry Screener</span>`
        : `<span class="perf-badge-dot dot-3">🟢 3-Dot Terdeteksi</span>`;
    } else if (item.count_green === 3) {
      dotBadge = `<span class="perf-badge-dot dot-3">🟢 3-Dot Aktif</span>`;
    }

    const itemHigh = Number(item.high) || 0;
    const itemLow = Number(item.low) || 0;
    const hasHighLow = itemHigh > 0 && itemLow > 0 && (itemHigh !== Number(item.close) || itemLow !== Number(item.close));
    const hlSub = hasHighLow 
      ? `<div style="font-size:10px; color:var(--text-muted); font-weight:500; margin-top:2px;">H: Rp ${itemHigh.toLocaleString('id-ID')} • L: Rp ${itemLow.toLocaleString('id-ID')}</div>`
      : '';

    return `
      <tr>
        <td style="font-weight:600;">${item.date_display || item.date}</td>
        <td>
          <div style="font-weight:700;">Rp ${Number(item.close || 0).toLocaleString('id-ID')}</div>
          ${hlSub}
        </td>
        <td style="color:${dayColor}; font-weight:700;">${daySign}${dayChg.toFixed(2)}%</td>
        <td style="color:${cumGColor}; font-weight:800;">${cumGSign}${cumG.toFixed(2)}%</td>
        <td>${dotBadge}</td>
      </tr>
    `;
  }).join('');

  const minGainSign = minGainPct > 0 ? "+" : "";
  const maxGainSign = maxGainPct > 0 ? "+" : "";

    const isDefaultPerfOpen = currentMode === "trackrecord";

    perfSectionHtml = `
    <!-- SECTION 6: RIWAYAT PERFORMA SINYAL (30 HARI BURSA) - COLLAPSIBLE ACCORDION -->
    <div class="modal-perf-section">
      <div class="modal-perf-header" onclick="togglePerfHistoryCollapse()">
        <div class="modal-perf-title-col">
          <div class="modal-perf-title-row">
            <span style="font-size:12.5px; font-weight:700; color:var(--text-primary); display:inline-flex; align-items:center; gap:6px;">
              <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--brand-primary)" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 20V10"></path><path d="M12 20V4"></path><path d="M6 20v-6"></path></svg>
              Riwayat Performa & Kenaikan Sinyal (30 Hari)
            </span>
            <span class="change-pill ${cumClass}" style="font-size:11px; padding:2px 8px;">Kumulatif: ${cumFormatted}</span>
          </div>
          <div class="modal-perf-subtitle">
            Deteksi Awal: <b>${firstDetectedDate || 'Aktif'}</b> • ${currentMode === 'trackrecord' ? 'Entry Screener' : 'Modal Entry'}: <b>${basePriceFormatted}</b> • Hari Terpantau: <b>${perfHistory.length} hari</b>
          </div>
        </div>
        <button type="button" class="perf-toggle-btn" id="perfToggleBtn" onclick="event.stopPropagation(); togglePerfHistoryCollapse();">
          <span>${isDefaultPerfOpen ? '▲' : '▼'}</span>
          <span>${isDefaultPerfOpen ? 'Tutup Riwayat' : 'Buka Grafik & Riwayat'}</span>
        </button>
      </div>

      <!-- Kontainer Grafik & Tabel (Default Terbuka di Track Record, Tertutup di mode lain) -->
      <div class="modal-perf-content" id="modalPerfContent" style="display: ${isDefaultPerfOpen ? 'flex' : 'none'};">
        
        <!-- Kenaikan Setelah Masuk Rekomendasi -->
        <div class="detail-info-card" style="margin-bottom: 14px; border-color: rgba(22, 163, 74, 0.4); background: linear-gradient(180deg, var(--bg-card) 0%, var(--brand-mint-subtle) 100%);">
          <div class="detail-info-head">
            <span>Kenaikan Setelah Masuk Rekomendasi</span>
          </div>
          <div class="detail-info-row">
            <span class="detail-info-label">Harga Close Entry:</span>
            <span class="detail-info-value">${recEntryClose ? `<b>Rp ${recEntryClose.toLocaleString('id-ID')}</b> ${recEntryDateDisplay ? `(${recEntryDateDisplay})` : ''}` : '-'}</span>
          </div>
          <div class="detail-info-row">
            <span class="detail-info-label">Kenaikan Saat Ini:</span>
            <span class="detail-info-value" style="color:var(--status-green); font-weight:800; font-size:13px;">${recGainVal !== null ? `${recGainSign}${recGainVal.toFixed(2)}%` : '-'}</span>
          </div>
          ${recPeakGainVal !== null && recPeakGainVal > 0 ? `
          <div class="detail-info-row">
            <span class="detail-info-label">Peak Cuan Realisasi:</span>
            <span class="detail-info-value" style="color:var(--status-green); font-weight:800; font-size:13px;">+${recPeakGainVal.toFixed(2)}% (Peak High: Rp ${recPeakHigh ? recPeakHigh.toLocaleString('id-ID') : '-'})</span>
          </div>
          ` : ''}
        </div>

        <!-- 4 KPI Stat Cards (Rapi & Tidak Bertumpuk) -->
        <div class="perf-kpi-grid">
          <div class="perf-kpi-card">
            <span class="perf-kpi-label">${currentMode === 'trackrecord' ? 'CLOSE ENTRY (SCREENER)' : 'MODAL ENTRY (DOT GREEN)'}</span>
            <span class="perf-kpi-val">Rp ${entryPriceVal.toLocaleString('id-ID')}</span>
            <span class="perf-kpi-sub">${perfHistory[0]?.date_display || 'Awal'}</span>
          </div>
          <div class="perf-kpi-card">
            <span class="perf-kpi-label">TERENDAH (LOW)</span>
            <span class="perf-kpi-val" style="color:var(--status-red);">Rp ${minPriceVal.toLocaleString('id-ID')}</span>
            <span class="perf-kpi-sub" style="color:var(--status-red);">${minGainSign}${minGainPct.toFixed(2)}%</span>
          </div>
          <div class="perf-kpi-card">
            <span class="perf-kpi-label">TERTINGGI (PEAK HIGH)</span>
            <span class="perf-kpi-val" style="color:var(--status-green);">Rp ${maxPriceVal.toLocaleString('id-ID')}</span>
            <span class="perf-kpi-sub" style="color:var(--status-green);">${maxGainSign}${maxGainPct.toFixed(2)}%</span>
          </div>
          <div class="perf-kpi-card highlight">
            <span class="perf-kpi-label">HARGA TERAKHIR</span>
            <span class="perf-kpi-val" style="color:var(--brand-primary);">Rp ${latestPriceVal.toLocaleString('id-ID')}</span>
            <span class="perf-kpi-sub" style="color:${cumClass === 'positive' ? 'var(--status-green)' : (cumClass === 'negative' ? 'var(--status-red)' : 'var(--text-muted)')}; font-weight:700;">${cumFormatted} Kumulatif</span>
          </div>
        </div>

        <!-- Professional Chart Box -->
        <div class="perf-chart-box">
          <div class="perf-chart-header">
            <span class="perf-chart-title" style="display:inline-flex; align-items:center; gap:6px;">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--status-cyan)" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"></polyline><polyline points="16 7 22 7 22 13"></polyline></svg>
              Kurva Pergerakan Harga Penutupan (Close)
            </span>
            <span class="perf-chart-dates">${perfHistory[0]?.date_display || ''} s/d ${perfHistory[perfHistory.length - 1]?.date_display || ''} (${perfHistory.length} Hari Bursa)</span>
          </div>
          <div class="perf-chart-svg-wrap">
            ${generatePerfChartSvg(perfHistory)}
          </div>
        </div>

        <!-- Tabel Riwayat Harian -->
        <div class="perf-table-wrap">
          <table class="perf-table">
            <thead>
              <tr>
                <th>Tanggal</th>
                <th>Harga Close</th>
                <th>Hari Ini (%)</th>
                <th>Total Kenaikan (%)</th>
                <th>Status Sinyal</th>
              </tr>
            </thead>
            <tbody>
              ${perfRowsHtml}
            </tbody>
          </table>
        </div>

        <div style="font-size:10.5px; color:var(--text-muted); line-height:1.6; padding: 6px 2px; display:flex; gap:6px; align-items:flex-start;">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--status-cyan)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0; margin-top:2px;"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
          <div>
            <b>Keterangan Status Sinyal:</b><br/>
            • <b>🟢 3-Dot Terdeteksi / Aktif:</b> Ketiga timeframe (Daily, 1H, 15M) aktif memunculkan sinyal Rally Good Dot Green.<br/>
            • <b>⚪ Masa Pantau:</b> Dot green padam di timeframe intraday, namun saham tetap aktif dipantau & diperbarui harganya selama 30 hari bursa.<br/>
            • <i>Jika saham memicu 3-Dot Green baru, siklus deteksi awal dan masa kedaluwarsa 30 hari akan di-reset otomatis.</i>
          </div>
        </div>

      </div>
    </div>
  `;
  }

  const modalHtml = `
    <div class="modal-dialog" onclick="event.stopPropagation()">
      
      <!-- Modal Header -->
      <div class="modal-header">
        <div class="modal-title-col">
          <div class="modal-symbol-row">
            <span class="modal-symbol-text">${stock.symbol}</span>
            ${isVip ? `<span class="vip-badge-pill" style="font-size:12px; padding:3px 10px;">FULL 3-DOT GREEN (VVIP)</span>` : (stock.count_green === 2 ? `<span class="vip-badge-pill" style="background:var(--status-cyan-bg); color:var(--status-cyan-text); font-size:12px; padding:3px 10px;">2-DOT GREEN (POTENSIAL)</span>` : '')}

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
        
        <!-- Banner Rekomendasi Aranter (Jika Memenuhi 5 Konfluensi) -->
        ${recScore ? `
          <div class="breakout-banner-box" style="background: linear-gradient(135deg, rgba(16, 185, 129, 0.12), rgba(6, 95, 70, 0.04)); border: 1px solid rgba(16, 185, 129, 0.35); margin-bottom: 16px;">
            <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px;">

                <span class="rec-score-pill" style="font-size:12px; padding:3px 10px;" title="Skor Rekomendasi: ${recScore}">${starIconSvg} : ${recScore}</span>


              ${recMetadata ? `
                <div style="font-size:11.5px; font-weight:600; color:var(--text-secondary);">
                  Sinyal Terakhir: <b style="color:var(--text-primary);">${recMetadata.latestDateStr}</b> (${recMetadata.daysAgoLatest === 0 ? 'Hari ini' : recMetadata.daysAgoLatest + ' hari lalu'})
                </div>
              ` : ''}
            </div>
            
            <div style="font-size:11.5px; color:var(--text-secondary); margin-top:6px; line-height:1.5;">
              Memenuhi <b>Rally Good 3-Dot</b>, <b>Golden Cross</b>, <b>Area Demand</b>, <b>Swing/Scalping</b>, dan <b>Sinyal Bull</b>.
            </div>

            ${recMetadata ? `
              <div style="display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; padding-top:8px; border-top:1px dashed rgba(16, 185, 129, 0.25); font-size:11px;">
                <span style="background:var(--bg-card); padding:3px 8px; border-radius:4px; border:1px solid var(--border-light);">Dot Green: <b>${recMetadata.dates.dot}</b></span>
                <span style="background:var(--bg-card); padding:3px 8px; border-radius:4px; border:1px solid var(--border-light);">Golden Cross: <b>${recMetadata.dates.golden}</b></span>
                <span style="background:var(--bg-card); padding:3px 8px; border-radius:4px; border:1px solid var(--border-light);">Scalp/Swing: <b>${recMetadata.dates.scalp}</b></span>
                <span style="background:var(--bg-card); padding:3px 8px; border-radius:4px; border:1px solid var(--border-light);">MACD Bull: <b>${recMetadata.dates.macd}</b></span>
              </div>
            ` : ''}
          </div>
        ` : ''}

        ${breakoutBannerHtml}

        <!-- SECTION 1: RALLYGOOD DOT GREEN PER TIMEFRAME (1D, 1H, 15M) -->
        <div class="modal-section">
          <div class="modal-sec-title">
            <span>Sinyal RallyGood Dot Green & Kenaikan Harga</span>
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
              <span>DonAlt EMA Golden & Death Cross</span>
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

          <!-- Scalp & Swing Trading Signal (1D, 1H, 15M) -->
          <div class="detail-info-card">
            <div class="detail-info-head">
              <span>Scalp & Swing Trading</span>
              <span class="modal-tf-status ${isScalpBuy ? 'active' : 'inactive'}">
                ${isScalpBuy ? 'BUY' : 'SELL'}
              </span>
            </div>

            <div class="detail-info-row">
              <span class="detail-info-label">Status Trend:</span>
              <span class="detail-info-value" style="color:${isScalpBuy ? 'var(--status-green)' : 'var(--status-red)'}; font-weight:700;">
                ${scalpTrend}
              </span>
            </div>
            <div class="detail-info-row">
              <span class="detail-info-label">Swing Trading (1D):</span>
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
              <span>Smart Money Concepts (SMC)</span>
              <span class="badge-mini">Supply & Demand</span>
            </div>

            <div class="detail-info-row">
              <span class="detail-info-label">SMC (1D):</span>
              <span class="detail-info-value">${formatSmcPerTf(smcD, stock.close, '1D')}</span>
            </div>
            <div class="detail-info-row">
              <span class="detail-info-label">SMC (1H):</span>
              <span class="detail-info-value">${formatSmcPerTf(smc60, stock.close, '1H')}</span>
            </div>
            <div class="detail-info-row">
              <span class="detail-info-label">SMC (15M):</span>
              <span class="detail-info-value">${formatSmcPerTf(smc15, stock.close, '15M')}</span>
            </div>
          </div>

          <!-- MACD Divergences (1D, 1H, 15M) -->
          <div class="detail-info-card">
            <div class="detail-info-head">
              <span>MACD Divergences</span>
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

        ${perfSectionHtml}

      </div>

      <!-- Modal Footer -->
      <div class="modal-footer">
        <a href="${tvUrl}" target="_blank" rel="noopener noreferrer" class="modal-tv-btn">
          <span>Buka Chart di TradingView</span>
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

function togglePerfHistoryCollapse() {
  const content = document.getElementById("modalPerfContent");
  const btn = document.getElementById("perfToggleBtn");
  if (!content) return;
  const isHidden = content.style.display === "none" || !content.style.display;
  if (isHidden) {
    content.style.display = "flex";
    if (btn) btn.innerHTML = `<span>▲</span><span>Tutup Riwayat</span>`;
  } else {
    content.style.display = "none";
    if (btn) btn.innerHTML = `<span>▼</span><span>Buka Grafik & Riwayat</span>`;
  }
}
window.togglePerfHistoryCollapse = togglePerfHistoryCollapse;

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
