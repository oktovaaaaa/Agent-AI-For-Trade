import os
import sys
import time
import datetime
import requests
import json
import asyncio
from pathlib import Path
import pandas as pd
import numpy as np
from PIL import Image
import pytz
from tradingview_screener import Query, Column
from playwright.async_api import async_playwright

# Pastikan console Windows mendukung output UTF-8 (Emoji & karakter Jepang)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ============================================================================
# KONFIGURASI BOT, TOKEN & AKUN TRADINGVIEW
# ============================================================================
FONNTE_TOKEN = os.environ.get("FONNTE_TOKEN", "7ci6H1WRqTDsJUAoFzq5")
NOMOR_WHATSAPP_TUJUAN = os.environ.get("NOMOR_WHATSAPP_TUJUAN", "6282111144710")

# Session Cookie TradingView (diambil dari browser Anda)
TRADINGVIEW_SESSIONID = os.environ.get("TRADINGVIEW_SESSIONID", "999m9aq36s5hhqv7yw2vfubqvqhxbmj9")

# URL Layout Chart TradingView Anda tempat indikator (人•ᴗ•)RallyGood terpasang
CHART_LAYOUT_URL = "https://www.tradingview.com/chart/6B2fiCnc/"

# Jadwal & Parameter Analisis
JAM_SCAN_WIB = 19               # Pukul 19.00 WIB setiap malam
MENIT_SCAN_WIB = 0
LOOKBACK_DAYS = 30              # Cek sinyal 1 bulan terakhir (30 hari)
LIMIT_SAHAM_SCAN = int(os.environ.get("LIMIT_SAHAM_SCAN", 0))           # 0 = Ambil seluruh saham lolos screener tanpa batas (bisa diatur misal 20, 50, atau 0 untuk semua)

# Timeframe yang dicek sesuai permintaan (1D, 1H, 15M)
TIMEFRAMES = [
    {"code": "D", "name": "Daily (1D)", "interval": "D"},
    {"code": "60", "name": "1 Jam (1H)", "interval": "60"},
    {"code": "15", "name": "15 Menit (15M)", "interval": "15"}
]

# Folder Penyimpanan Laporan
REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)
(REPORTS_DIR / "screenshots").mkdir(exist_ok=True)

WIB_TZ = pytz.timezone("Asia/Jakarta")

BULAN_INDONESIA = {
    1: "Januari", 2: "Februari", 3: "Maret", 4: "April",
    5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus",
    9: "September", 10: "Oktober", 11: "November", 12: "Desember"
}

BULAN_PENDEK = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "Mei", 6: "Jun", 7: "Jul", 8: "Agu",
    9: "Sep", 10: "Okt", 11: "Nov", 12: "Des"
}

def format_tanggal_id(dt):
    """Mengembalikan format tanggal Indonesia resmi, misal: 13 Oktober 2026"""
    return f"{dt.day} {BULAN_INDONESIA.get(dt.month, '')} {dt.year}"

def format_gain_header(tf_dict):
    """
    Menghasilkan string kenaikan persentase sejak Dot Green muncul (1D & 1H).
    Contoh: (1D: +12.50% | 1H: +5.20%) atau (1H: +18.89%) atau (1D: +4.00%)
    """
    parts = []
    if tf_dict.get('D', {}).get('status') and tf_dict['D'].get('gain_pct') is not None:
        parts.append(f"1D: {tf_dict['D']['gain_pct']:+.2f}%")
    if tf_dict.get('60', {}).get('status') and tf_dict['60'].get('gain_pct') is not None:
        parts.append(f"1H: {tf_dict['60']['gain_pct']:+.2f}%")
    if parts:
        return f" ({' | '.join(parts)})"
    return ""

def calculate_smc_levels_fallback(bars, cur_close):
    """Fallback kalkulasi Supply & Demand sederhana jika indikator belum termuat."""
    if not bars or len(bars) < 8 or not cur_close:
        return None
    last_time = bars[-1]['time']
    k = 5
    pivot_highs = []
    pivot_lows = []
    for i in range(k, len(bars) - k):
        high_i = bars[i]['high']
        low_i = bars[i]['low']
        if all(high_i >= bars[j]['high'] for j in range(i - k, i + k + 1) if j != i):
            pivot_highs.append(high_i)
        if all(low_i <= bars[j]['low'] for j in range(i - k, i + k + 1) if j != i):
            pivot_lows.append(low_i)
            
    sup_above = [p for p in pivot_highs if p > cur_close]
    nearest_supply = min(sup_above) if sup_above else (max(pivot_highs) if pivot_highs else None)
    
    dem_below = [p for p in pivot_lows if p < cur_close]
    nearest_demand = max(dem_below) if dem_below else (min(pivot_lows) if pivot_lows else None)
    
    pct_to_supply = ((nearest_supply - cur_close) / cur_close) * 100 if nearest_supply else 0
    pct_to_demand = -((cur_close - nearest_demand) / cur_close) * 100 if nearest_demand else 0
    
    status_7d = "⚪ Di Antara Demand & Supply"
    if nearest_supply and cur_close >= nearest_supply:
        status_7d = f"🔥 BREAKOUT SUPPLY (Menembus Rp {nearest_supply:.0f})"
    elif nearest_demand and cur_close <= nearest_demand:
        status_7d = f"⚠️ BREAKDOWN DEMAND (Menembus Rp {nearest_demand:.0f})"
    elif abs(pct_to_supply) <= 2.5:
        status_7d = "⚡ Menguji Area Supply (Dekat Resisten)"
    elif abs(pct_to_demand) <= 2.5:
        status_7d = "🟢 Di Area Demand (Potensi Pantulan)"
        
    return {
        "supply": nearest_supply,
        "demand": nearest_demand,
        "pct_to_supply": pct_to_supply,
        "pct_to_demand": pct_to_demand,
        "status_7d": status_7d
    }

def parse_real_smc_levels(smc_data, cur_close, recent_bars=None):
    """
    Menganalisa garis Supply, Demand, persentase jarak harga, dan status BOS / CHoCH / Breakout
    7 hari terakhir LANGSUNG dari indikator TradingView Ultimate SMC Suite milik akun pengguna.
    """
    if not cur_close or cur_close <= 0:
        return None
        
    supplies = smc_data.get("supplies", []) if smc_data else []
    demands = smc_data.get("demands", []) if smc_data else []
    bos_list = smc_data.get("bosList", []) if smc_data else []
    
    # Jika data indikator Ultimate SMC Suite tersedia langsung dari chart TradingView
    if supplies or demands:
        sup_above = [s['mid'] for s in supplies if s.get('mid', 0) >= cur_close]
        if sup_above:
            nearest_supply = min(sup_above)
        elif supplies:
            nearest_supply = max(s['mid'] for s in supplies)
        else:
            nearest_supply = None
            
        dem_below = [d['mid'] for d in demands if d.get('mid', 0) <= cur_close]
        if dem_below:
            nearest_demand = max(dem_below)
        elif demands:
            nearest_demand = min(d['mid'] for d in demands)
        else:
            nearest_demand = None
            
        pct_to_supply = ((nearest_supply - cur_close) / cur_close) * 100 if nearest_supply else 0
        pct_to_demand = -((cur_close - nearest_demand) / cur_close) * 100 if nearest_demand else 0
        
        # Deteksi aktivitas BOS / CHoCH dalam rentang 7 hari terakhir (1 minggu)
        now_ts = datetime.datetime.now(WIB_TZ).timestamp()
        week_sec = 7 * 86400
        recent_bos = [b for b in bos_list if b.get('timestamp') and (now_ts - b['timestamp']) <= week_sec]
        
        # Tentukan status Breakout / Breakdown / Area posisi
        if nearest_supply and cur_close >= nearest_supply:
            status_7d = f"🔥 BREAKOUT SUPPLY (Menembus Rp {nearest_supply:.0f})"
        elif nearest_demand and cur_close <= nearest_demand:
            status_7d = f"⚠️ BREAKDOWN DEMAND (Menembus Rp {nearest_demand:.0f})"
        elif abs(pct_to_supply) <= 2.5:
            status_7d = "⚡ Menguji Area Supply (Dekat Resisten)"
        elif abs(pct_to_demand) <= 2.5:
            status_7d = "🟢 Di Area Demand (Potensi Pantulan)"
        else:
            if recent_bos:
                latest_b = max(recent_bos, key=lambda x: x['timestamp'])
                b_dt = datetime.datetime.fromtimestamp(latest_b['timestamp'], WIB_TZ)
                b_month = BULAN_PENDEK.get(b_dt.month, b_dt.strftime("%b"))
                status_7d = f"⚪ Di Antara Demand & Supply ({latest_b['type']}: Rp {latest_b['price']:.0f} tgl {b_dt.day} {b_month})"
            else:
                status_7d = "⚪ Di Antara Demand & Supply"
                
        return {
            "supply": nearest_supply,
            "demand": nearest_demand,
            "pct_to_supply": pct_to_supply,
            "pct_to_demand": pct_to_demand,
            "status_7d": status_7d
        }
        
    # Fallback jika indikator belum sempat ter-render sempurna
    return calculate_smc_levels_fallback(recent_bars, cur_close)

def format_smc_wa(smc_1d, smc_1h=None):
    """Format tampilan SMC Supply, Demand & Status 7D untuk Timeframe 1D & 1H di WhatsApp."""
    if isinstance(smc_1d, dict) and smc_1h is None:
        smc_1h = smc_1d
        smc_1d = None
        
    lines = []
    if smc_1d and smc_1d.get('supply') and smc_1d.get('demand'):
        sup_d = f"Rp {smc_1d['supply']:.0f} ({smc_1d['pct_to_supply']:+.2f}%)"
        dem_d = f"Rp {smc_1d['demand']:.0f} ({smc_1d['pct_to_demand']:+.2f}%)"
        lines.append(f"🎯 1D: Sup {sup_d} | Dem {dem_d}")
        
    if smc_1h and smc_1h.get('supply') and smc_1h.get('demand'):
        sup_h = f"Rp {smc_1h['supply']:.0f} ({smc_1h['pct_to_supply']:+.2f}%)"
        dem_h = f"Rp {smc_1h['demand']:.0f} ({smc_1h['pct_to_demand']:+.2f}%)"
        lines.append(f"🎯 1H: Sup {sup_h} | Dem {dem_h}")
        
    status_info = None
    if smc_1h and ("BREAKOUT" in smc_1h.get('status_7d', '') or "BREAKDOWN" in smc_1h.get('status_7d', '')):
        status_info = f"📍 Status (1H): {smc_1h['status_7d']}"
    elif smc_1d and ("BREAKOUT" in smc_1d.get('status_7d', '') or "BREAKDOWN" in smc_1d.get('status_7d', '')):
        status_info = f"📍 Status (1D): {smc_1d['status_7d']}"
    elif smc_1h and smc_1h.get('status_7d'):
        status_info = f"📍 Status 7D : {smc_1h['status_7d']}"
    elif smc_1d and smc_1d.get('status_7d'):
        status_info = f"📍 Status 7D : {smc_1d['status_7d']}"
        
    if status_info:
        lines.append(status_info)
        
    if lines:
        return "\n".join(lines) + "\n"
    return ""

def bersihkan_screenshot():
    """Menghapus semua file screenshot gambar agar penyimpanan server/laptop tetap ringan dan hemat disk."""
    ss_dir = REPORTS_DIR / "screenshots"
    if ss_dir.exists():
        count = 0
        for file in ss_dir.glob("*.png"):
            try:
                file.unlink()
                count += 1
            except Exception:
                pass
        if count > 0:
            print(f"🧹 Berhasil membersihkan {count} file screenshot (penyimpanan server 100% hemat).")

# ============================================================================
# FUNSI KIRIM NOTIFIKASI WHATSAPP VIA FONNTE (1X PENGIRIMAN)
# ============================================================================
def kirim_whatsapp(pesan):
    """Mengirim pesan rangkuman ke WhatsApp via API Fonnte (dengan auto-chunking jika pesan panjang)."""
    if not FONNTE_TOKEN or FONNTE_TOKEN == "MASUKKAN_TOKEN_FONNTE_DI_SINI":
        print("[WARNING] Token Fonnte belum diisi. Pesan tidak terkirim.")
        return False
        
    url = "https://api.fonnte.com/send"
    headers = {"Authorization": FONNTE_TOKEN}
    
    # Pecah pesan jika melebihi batas karakter WhatsApp (maks 3500 karakter per pesan)
    chunks = []
    if len(pesan) > 3500:
        lines = pesan.split("\n")
        cur_chunk = ""
        for line in lines:
            if len(cur_chunk) + len(line) + 1 > 3500:
                chunks.append(cur_chunk.strip())
                cur_chunk = line + "\n"
            else:
                cur_chunk += line + "\n"
        if cur_chunk.strip():
            chunks.append(cur_chunk.strip())
    else:
        chunks = [pesan.strip()]
        
    success = True
    for idx, chunk in enumerate(chunks, 1):
        payload = {
            "target": NOMOR_WHATSAPP_TUJUAN,
            "message": chunk,
            "countryCode": "62"
        }
        try:
            response = requests.post(url, headers=headers, data=payload, timeout=20)
            res_json = response.json()
            if not res_json.get("status"):
                print(f"[ERROR] Gagal kirim WA Fonnte (bagian {idx}/{len(chunks)}): {res_json}")
                success = False
            else:
                part_info = f" (bagian {idx}/{len(chunks)})" if len(chunks) > 1 else ""
                print(f"[{datetime.datetime.now(WIB_TZ).strftime('%H:%M:%S WIB')}] ✅ Pesan WhatsApp{part_info} berhasil dikirim!")
            if len(chunks) > 1:
                time.sleep(1.5)
        except Exception as e:
            print(f"[EXCEPT] Error koneksi Fonnte: {e}")
            success = False
            
    return success

# ============================================================================
# TAHAP 1: SCREENER HUNTER (SAHAM ID Rp 10-1000 & VOLUME > AVG 10D)
# ============================================================================
def get_hunter_stocks():
    """Mengambil saham IDX dari TradingView Screener sesuai kriteria HUNTER."""
    print(f"\n[{datetime.datetime.now(WIB_TZ).strftime('%Y-%m-%d %H:%M:%S WIB')}] 🔎 Memulai Screener HUNTER Saham IDX...")
    try:
        q = (Query()
             .set_markets('indonesia')
             .select('name', 'close', 'volume', 'average_volume_10d_calc', 'change')
             .where(
                 Column('close').between(10, 1000),
                 Column('volume') > Column('average_volume_10d_calc'),
                 Column('volume').above_pct('premarket_volume', 5.0)
             )
             .order_by('volume', ascending=False))
             
        if LIMIT_SAHAM_SCAN and LIMIT_SAHAM_SCAN > 0:
            q = q.limit(LIMIT_SAHAM_SCAN)
        else:
            q = q.limit(500) # Ambil seluruh saham yang lolos kriteria HUNTER (153 saham)
        
        df_screener = q.get_scanner_data()[1]
        if df_screener.empty:
            print("ℹ️ Tidak ada saham yang lolos kriteria HUNTER hari ini.")
            return []
            
        tickers = []
        for _, row in df_screener.iterrows():
            ticker_name = str(row['ticker'])
            symbol = ticker_name.split(':')[-1] if ':' in ticker_name else ticker_name
            tickers.append({
                'symbol': symbol,
                'tv_symbol': f"IDX:{symbol}",
                'close': float(row['close']),
                'volume': float(row['volume']),
                'vol_10d': float(row['average_volume_10d_calc']),
                'change': float(row['change'])
            })
            
        # Pastikan DYAN ikut teranalisis sebagai pembanding jika belum ada di list
        if not any(t['symbol'] == 'DYAN' for t in tickers):
            tickers.append({
                'symbol': 'DYAN',
                'tv_symbol': 'IDX:DYAN',
                'close': 81.0,
                'volume': 210940000.0,
                'vol_10d': 150000000.0,
                'change': 3.85
            })
            
        print(f"✅ Ditemukan {len(tickers)} saham Hunter potensial untuk dianalisis.")
        return tickers
    except Exception as e:
        print(f"[ERROR] Screener TradingView gagal: {e}")
        return []

# ============================================================================
# TAHAP 2 & 3: BROWSER OTOMATIS & EKSTRAKSI DATA PERSIS DARI TRADINGVIEW
# ============================================================================

# ============================================================================
# TAHAP 3: BROWSER OTOMATIS MEMERIKSA CHART & MENGAMBIL TANGGAL ASLI
# ============================================================================
async def scan_stock_rallygood(page, stock_info):
    """
    Membuka chart TradingView untuk saham tertentu secara instan (setSymbol & setResolution),
    mendeteksi Dot Green, dan mengekstrak tanggal & jam persis kemunculannya langsung dari TradingView.
    """
    symbol = stock_info['symbol']
    results = {}
    now_dt = datetime.datetime.now(WIB_TZ)
    
    # 1. Ganti simbol saham secara instan di chart TradingView
    try:
        await page.evaluate('(s) => window._exposed_chartWidgetCollection?.activeChartWidget?.value()?.setSymbol(s)', f"IDX:{symbol}")
        await asyncio.sleep(1.2)
    except Exception:
        chart_url = f"{CHART_LAYOUT_URL}?symbol=IDX%3A{symbol}&interval=D"
        await page.goto(chart_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3.5)
    
    # 2. Cek setiap timeframe (D, 60, 15)
    for tf in TIMEFRAMES:
        tf_code = tf['code']
        tf_name = tf['name']
        
        print(f"   ↳ Mengecek {symbol} [{tf_name}]...", end="", flush=True)
        
        try:
            # Ganti resolusi / timeframe secara instan tanpa reload penuh
            await page.evaluate('(r) => window._exposed_chartWidgetCollection?.activeChartWidget?.value()?.setResolution(r)', tf['interval'])
            await asyncio.sleep(1.2)
            
            # Ambil data Dot Green beserta data indikator Ultimate SMC Suite asli
            eval_data = await page.evaluate('''async () => {
                try {
                    const chart = window._exposed_chartWidgetCollection?.activeChartWidget?.value();
                    if (!chart) return { dots: [], bars: [], smc: null };
                    const model = chart.model();
                    const ts = model.timeScale();
                    const ms = model.mainSeries();
                    const barsObj = ms && ms.bars ? ms.bars() : null;
                    const lastBar = barsObj && barsObj.last ? barsObj.last() : null;
                    const currentClose = lastBar && lastBar.value ? lastBar.value[4] : null;

                    const lastIdx = barsObj && barsObj.lastIndex ? barsObj.lastIndex() : (barsObj && barsObj.size ? barsObj.size() - 1 : 0);
                    const startIdx = Math.max(0, lastIdx - 80);
                    const recentBars = [];
                    if (barsObj && barsObj.valueAt) {
                        for (let i = startIdx; i <= lastIdx; i++) {
                            const b = barsObj.valueAt(i);
                            if (b && b.length >= 5) {
                                recentBars.push({ time: b[0], open: b[1], high: b[2], low: b[3], close: b[4], vol: b[5] });
                            }
                        }
                    }

                    // 1. Ekstraksi Dot Green dari indikator RallyGood
                    let dots = [];
                    const rallyStudies = model.panes().flatMap(p => p.dataSources()).filter(s => s.title && s.title().includes('RallyGood'));
                    if (rallyStudies.length > 0) {
                        const study = rallyStudies[0];
                        const greenPv = (study._paneViews || []).find(pv => pv._plotName === 'plot_2');
                        if (greenPv) {
                            const activeDots = (greenPv._items || []).filter(it => !isNaN(it.y));
                            dots = activeDots.map(dot => {
                                const tp = ts.indexToTimePoint(dot.timePointIndex);
                                let dotClose = null;
                                if (barsObj && barsObj.valueAt) {
                                    const bar = barsObj.valueAt(dot.timePointIndex);
                                    if (bar && bar.length > 4) {
                                        dotClose = bar[4];
                                    }
                                }
                                return {
                                    timestamp: tp,
                                    dotClose: dotClose,
                                    currentClose: currentClose
                                };
                            }).filter(d => d.timestamp !== null && d.timestamp !== undefined);
                        }
                    }

                    // 2. Ekstraksi Garis Supply, Demand, BOS & CHoCH LANGSUNG dari Ultimate SMC Suite
                    let smcData = null;
                    const smcStudy = model.panes().flatMap(p => p.dataSources()).find(s => s.title && s.title().includes('Ultimate SMC Suite'));
                    if (smcStudy && smcStudy._graphics && smcStudy._graphics._primitivesCollection) {
                        const prims = smcStudy._graphics._primitivesCollection;
                        const boxesInner = prims.dwgboxes?.get('boxes');
                        const labelsInner = prims.dwglabels?.get('labels');
                        
                        const boxDataObj = boxesInner?.get(false)?._primitivesDataById;
                        const labelDataObj = labelsInner?.get(false)?._primitivesDataById;
                        
                        const boxEntries = boxDataObj instanceof Map ? Array.from(boxDataObj.entries()) : Object.entries(boxDataObj || {});
                        const labelEntries = labelDataObj instanceof Map ? Array.from(labelDataObj.entries()) : Object.entries(labelDataObj || {});
                        
                        const parsedBoxes = boxEntries.map(([k, v]) => ({
                            type: v.t || "",
                            high: Math.max(v.y1, v.y2),
                            low: Math.min(v.y1, v.y2),
                            mid: (v.y1 + v.y2) / 2,
                            extendRight: v.ex === 'r',
                            barStart: v.x1,
                            barEnd: v.x2
                        }));
                        
                        let maxPineX = 0;
                        for (const b of parsedBoxes) {
                            if (b.barEnd > maxPineX) maxPineX = b.barEnd;
                            if (b.barStart > maxPineX) maxPineX = b.barStart;
                        }
                        for (const [, l] of labelEntries) {
                            if (l.x > maxPineX) maxPineX = l.x;
                        }
                        const offset = maxPineX - lastIdx;
                        
                        const supplies = parsedBoxes.filter(b => b.type === 'SUPPLY').map(s => ({
                            high: s.high,
                            low: s.low,
                            mid: s.mid
                        }));
                        const demands = parsedBoxes.filter(b => b.type === 'DEMAND').map(d => ({
                            high: d.high,
                            low: d.low,
                            mid: d.mid
                        }));
                        
                        const bosList = labelEntries
                            .filter(([, l]) => l.t && (l.t.includes('BOS') || l.t.includes('CHoCH')))
                            .map(([id, l]) => {
                                const localIdx = l.x - offset;
                                const bar = barsObj && barsObj.valueAt && localIdx >= 0 && localIdx <= lastIdx ? barsObj.valueAt(localIdx) : null;
                                const tp = bar ? bar[0] : null;
                                return {
                                    type: l.t,
                                    price: l.y,
                                    timestamp: tp,
                                    barsAgo: lastIdx - localIdx
                                };
                            });
                            
                        smcData = {
                            supplies: supplies,
                            demands: demands,
                            bosList: bosList
                        };
                    }

                    return { dots: dots, bars: recentBars, currentClose: currentClose, smc: smcData };
                } catch(e) {
                    return { dots: [], bars: [], currentClose: null, smc: null };
                }
            }''')
            
            dot_data = eval_data.get('dots', [])
            recent_bars = eval_data.get('bars', [])
            cur_close = eval_data.get('currentClose') or stock_info.get('close')
            smc_raw = eval_data.get('smc')
            smc_res = parse_real_smc_levels(smc_raw, cur_close, recent_bars)
            
            valid_dots = []
            for d in dot_data:
                tp = d.get('timestamp')
                if tp and isinstance(tp, (int, float)):
                    dot_dt = datetime.datetime.fromtimestamp(tp, WIB_TZ)
                    diff_days = (now_dt - dot_dt).total_seconds() / 86400
                    # SYARAT MUTLAK: Hanya terima jika muncul dalam rentang 30 hari terakhir
                    if 0 <= diff_days <= LOOKBACK_DAYS:
                        valid_dots.append({
                            "dt": dot_dt,
                            "dot_close": d.get("dotClose"),
                            "current_close": d.get("currentClose")
                        })
            
            if valid_dots:
                latest = max(valid_dots, key=lambda x: x["dt"])
                latest_dot = latest["dt"]
                b_str = BULAN_PENDEK.get(latest_dot.month, latest_dot.strftime("%b"))
                if tf_code == 'D':
                    date_display = f"{latest_dot.day} {b_str} {latest_dot.year}"
                else:
                    date_display = f"{latest_dot.day} {b_str} {latest_dot.year}, {latest_dot.strftime('%H:%M')} WIB"
                    
                dot_close = latest.get("dot_close")
                cur_close = latest.get("current_close") or stock_info["close"]
                gain_pct = None
                if dot_close and cur_close and dot_close > 0:
                    gain_pct = ((cur_close - dot_close) / dot_close) * 100
                    
                gain_info = f" (Kenaikan: {gain_pct:+.2f}%)" if gain_pct is not None else ""
                print(f" 🟢 ADA DOT GREEN! ({date_display}){gain_info}")
                results[tf_code] = {
                    "status": True,
                    "date": date_display,
                    "dot_close": dot_close,
                    "gain_pct": gain_pct,
                    "smc": smc_res
                }
            else:
                print(" ❌ Tidak ada")
                results[tf_code] = {
                    "status": False,
                    "date": None,
                    "gain_pct": None,
                    "smc": smc_res
                }
                    
        except Exception as e:
            print(f" ⚠️ Error: {e}")
            results[tf_code] = {"status": False, "date": None, "error": str(e)}
            
    return results

# ============================================================================
# TAHAP 4: EKSEKUSI UTAMA (SCAN HARIAN JAM 19.00 WIB)
# ============================================================================
async def run_daily_scan(send_wa=True):
    now_wib = datetime.datetime.now(WIB_TZ)
    date_str = now_wib.strftime("%Y%m%d")
    tgl_analisa_id = format_tanggal_id(now_wib)
    tgl_awal_id = format_tanggal_id(now_wib - datetime.timedelta(days=LOOKBACK_DAYS))
    
    print("\n" + "="*70)
    print(f"🚀 MEMULAI SCAN HARIAN HUNTER - RALLY GOD [{tgl_analisa_id} {now_wib.strftime('%H:%M WIB')}]")
    print("="*70)
    
    # Bersihkan file screenshot lama agar disk tetap bersih
    bersihkan_screenshot()
    
    # 1. Ambil saham lolos kriteria Screener HUNTER
    hunter_stocks = get_hunter_stocks()
    if not hunter_stocks:
        kirim_whatsapp(f"ℹ️ *SCAN HUNTER {date_display}*\nTidak ada saham IDX Rp 10-1000 yang lolos kriteria volume hari ini.")
        return
        
    hasil_deteksi = []
    
    # 2. Jalankan Browser dengan Playwright (Support Docker & Local Chrome/Edge)
    async with async_playwright() as p:
        browser_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu"
        ]
        browser = None
        for launch_opt in [{}, {"channel": "chrome"}, {"channel": "msedge"}]:
            try:
                browser = await p.chromium.launch(headless=True, args=browser_args, **launch_opt)
                break
            except Exception:
                continue
                
        if not browser:
            print("[ERROR] Tidak dapat membuka browser (Chromium/Chrome/Edge). Pastikan browser terpasang.")
            return
        
        context = await browser.new_context(
            viewport={"width": 1600, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Suntikkan Session Cookie TradingView jika disediakan
        if TRADINGVIEW_SESSIONID:
            print("🔑 Memuat Session Cookie TradingView...")
            await context.add_cookies([{
                "name": "sessionid",
                "value": TRADINGVIEW_SESSIONID,
                "domain": ".tradingview.com",
                "path": "/"
            }])
        else:
            print("[INFO] Menjalankan tanpa sessionid (indikator publik/template layout).")
            
        page = await context.new_page()
        
        # Buka layout chart pertama kali agar layout dan indikator siap
        first_sym = hunter_stocks[0]['symbol']
        print(f"📊 Menyiapkan Chart Layout TradingView ({first_sym})...")
        await page.goto(f"{CHART_LAYOUT_URL}?symbol=IDX%3A{first_sym}&interval=D", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(4)
        
        # 3. Looping pengecekan chart saham
        for idx, stock in enumerate(hunter_stocks, 1):
            sym = stock['symbol']
            print(f"\n[{idx}/{len(hunter_stocks)}] Memeriksa Saham: {sym} (Rp {stock['close']:.0f} | {stock['change']:+.2f}%)")
            
            tf_results = await scan_stock_rallygood(page, stock)
            
            # Cek apakah ada minimal satu timeframe dengan Dot Green
            any_green = any(tf_results.get(tf['code'], {}).get('status', False) for tf in TIMEFRAMES)
            
            hasil_deteksi.append({
                "stock": stock,
                "timeframes": tf_results,
                "has_green_dot": any_green
            })
            
        await browser.close()
        
    # 4. Susun Konten Laporan Teks Lengkap
    konten_laporan = []
    konten_laporan.append("=" * 75)
    konten_laporan.append(f"LAPORAN ANALISA SAHAM HUNTER - {tgl_analisa_id.upper()} (RALLY GOD IDX)")
    konten_laporan.append(f"Tanggal Analisa  : {tgl_analisa_id}")
    konten_laporan.append(f"Waktu Eksekusi   : {now_wib.strftime('%H:%M:%S WIB')}")
    konten_laporan.append(f"Kriteria Filter  : Harga Rp 10-1.000 | Vol > Avg 10D | Vol Pre-mkt > 500% (IDX)")
    konten_laporan.append(f"Rentang Analisis : {tgl_awal_id} s/d {tgl_analisa_id} (1 Bulan Terakhir / 30 Hari)")
    konten_laporan.append(f"Layout Chart     : {CHART_LAYOUT_URL}")
    konten_laporan.append("=" * 75 + "\n")
    
    # Hitung jumlah timeframe dengan Dot Green untuk setiap saham
    for item in hasil_deteksi:
        tf = item["timeframes"]
        item["count_green"] = sum(1 for tf_key in ['D', '60', '15'] if tf.get(tf_key, {}).get('status'))

    # Kelompokkan saham berdasarkan jumlah sinyal Dot Green
    saham_3_dot = [item for item in hasil_deteksi if item["count_green"] == 3]
    saham_2_dot = [item for item in hasil_deteksi if item["count_green"] == 2]
    saham_1_dot = [item for item in hasil_deteksi if item["count_green"] == 1]
    saham_0_dot = [item for item in hasil_deteksi if item["count_green"] == 0]

    # Urutkan berdasarkan volume transaksi tertinggi
    saham_3_dot.sort(key=lambda x: x['stock']['volume'], reverse=True)
    saham_2_dot.sort(key=lambda x: x['stock']['volume'], reverse=True)
    saham_1_dot.sort(key=lambda x: x['stock']['volume'], reverse=True)

    # 4. Susun Konten Laporan Teks Lengkap (Notepad)
    konten_laporan = []
    konten_laporan.append("=" * 75)
    konten_laporan.append(f"LAPORAN ANALISA SAHAM HUNTER - {tgl_analisa_id.upper()} (RALLY GOD IDX)")
    konten_laporan.append(f"Tanggal Analisa  : {tgl_analisa_id}")
    konten_laporan.append(f"Waktu Eksekusi   : {now_wib.strftime('%H:%M:%S WIB')}")
    konten_laporan.append(f"Kriteria Filter  : Harga Rp 10-1.000 | Vol > Avg 10D | Vol Pre-mkt > 500% (IDX)")
    konten_laporan.append(f"Rentang Analisis : {tgl_awal_id} s/d {tgl_analisa_id} (1 Bulan Terakhir / 30 Hari)")
    konten_laporan.append(f"Layout Chart     : {CHART_LAYOUT_URL}")
    konten_laporan.append("=" * 75 + "\n")
    
    konten_laporan.append("RINGKASAN HASIL PEMINDAIAN:")
    konten_laporan.append(f"• Total Saham Screener Hunter : {len(hasil_deteksi)} Saham")
    konten_laporan.append(f"• Saham 3 Timeframe (Prioritas) : {len(saham_3_dot)} Saham")
    konten_laporan.append(f"• Saham 2 Timeframe (Potensial) : {len(saham_2_dot)} Saham")
    konten_laporan.append(f"• Saham 1 Timeframe Saja        : {len(saham_1_dot)} Saham")
    konten_laporan.append(f"• Saham Netral (0 Timeframe)    : {len(saham_0_dot)} Saham")
    konten_laporan.append("*(Catatan: Notifikasi WhatsApp hanya menyaring saham dengan minimal 2 Timeframe)*\n")
    
    # Bagian 1: 3 Timeframe (Prioritas Utama)
    konten_laporan.append("=" * 75)
    konten_laporan.append(f"[BAGIAN 1] SAHAM PRIORITAS UTAMA (3 TIMEFRAME SEKALIGUS) - {len(saham_3_dot)} SAHAM:")
    konten_laporan.append("=" * 75)
    if saham_3_dot:
        for idx, item in enumerate(saham_3_dot, 1):
            st = item["stock"]
            tf = item["timeframes"]
            gain_str = format_gain_header(tf)
            smc_1d = tf.get('D', {}).get('smc')
            smc_1h = tf.get('60', {}).get('smc')
            konten_laporan.append(f"{idx}. {st['symbol']} | Harga: Rp {st['close']:.0f}{gain_str} | Vol: {st['volume']:,.0f}")
            konten_laporan.append("   🟢 ANALISA SAHAM INI !!! 🟢")
            g_1d = f" (Kenaikan: {tf['D']['gain_pct']:+.2f}%)" if tf.get('D', {}).get('gain_pct') is not None else ""
            g_1h = f" (Kenaikan: {tf['60']['gain_pct']:+.2f}%)" if tf.get('60', {}).get('gain_pct') is not None else ""
            konten_laporan.append(f"   - Daily (1D)  : [ADA DOT GREEN] (Muncul: {tf['D']['date']}{g_1d})")
            konten_laporan.append(f"   - 1 Jam (1H)  : [ADA DOT GREEN] (Muncul: {tf['60']['date']}{g_1h})")
            konten_laporan.append(f"   - 15 Menit    : [ADA DOT GREEN] (Muncul: {tf['15']['date']})")
            if smc_1d and smc_1d.get('supply') and smc_1d.get('demand'):
                sup_d = f"Rp {smc_1d['supply']:.0f} ({smc_1d['pct_to_supply']:+.2f}%)"
                dem_d = f"Rp {smc_1d['demand']:.0f} ({smc_1d['pct_to_demand']:+.2f}%)"
                konten_laporan.append(f"   - SMC Daily(1D): Supply: {sup_d} | Demand: {dem_d}")
            if smc_1h and smc_1h.get('supply') and smc_1h.get('demand'):
                sup_h = f"Rp {smc_1h['supply']:.0f} ({smc_1h['pct_to_supply']:+.2f}%)"
                dem_h = f"Rp {smc_1h['demand']:.0f} ({smc_1h['pct_to_demand']:+.2f}%)"
                konten_laporan.append(f"   - SMC 1 Jam(1H): Supply: {sup_h} | Demand: {dem_h}")
            if smc_1h and smc_1h.get('status_7d'):
                konten_laporan.append(f"   - Status 7D   : {smc_1h['status_7d']}\n")
            elif smc_1d and smc_1d.get('status_7d'):
                konten_laporan.append(f"   - Status 7D   : {smc_1d['status_7d']}\n")
            else:
                konten_laporan.append("")
    else:
        konten_laporan.append("Tidak ada saham dengan 3 Dot Green sekaligus malam ini.\n")
        
    # Bagian 2: 2 Timeframe (Potensial)
    konten_laporan.append("=" * 75)
    konten_laporan.append(f"[BAGIAN 2] SAHAM RADAR POTENSIAL (2 TIMEFRAME) - {len(saham_2_dot)} SAHAM:")
    konten_laporan.append("=" * 75)
    if saham_2_dot:
        for idx, item in enumerate(saham_2_dot, 1):
            st = item["stock"]
            tf = item["timeframes"]
            gain_str = format_gain_header(tf)
            smc_1d = tf.get('D', {}).get('smc')
            smc_1h = tf.get('60', {}).get('smc')
            konten_laporan.append(f"{idx}. {st['symbol']} | Harga: Rp {st['close']:.0f}{gain_str} | Vol: {st['volume']:,.0f}")
            if tf.get('D', {}).get('status'):
                g_1d = f" (Kenaikan: {tf['D']['gain_pct']:+.2f}%)" if tf.get('D', {}).get('gain_pct') is not None else ""
                konten_laporan.append(f"   - Daily (1D)  : [ADA DOT GREEN] (Muncul: {tf['D']['date']}{g_1d})")
            if tf.get('60', {}).get('status'):
                g_1h = f" (Kenaikan: {tf['60']['gain_pct']:+.2f}%)" if tf.get('60', {}).get('gain_pct') is not None else ""
                konten_laporan.append(f"   - 1 Jam (1H)  : [ADA DOT GREEN] (Muncul: {tf['60']['date']}{g_1h})")
            if tf.get('15', {}).get('status'):
                konten_laporan.append(f"   - 15 Menit    : [ADA DOT GREEN] (Muncul: {tf['15']['date']})")
            if smc_1d and smc_1d.get('supply') and smc_1d.get('demand'):
                sup_d = f"Rp {smc_1d['supply']:.0f} ({smc_1d['pct_to_supply']:+.2f}%)"
                dem_d = f"Rp {smc_1d['demand']:.0f} ({smc_1d['pct_to_demand']:+.2f}%)"
                konten_laporan.append(f"   - SMC Daily(1D): Supply: {sup_d} | Demand: {dem_d}")
            if smc_1h and smc_1h.get('supply') and smc_1h.get('demand'):
                sup_h = f"Rp {smc_1h['supply']:.0f} ({smc_1h['pct_to_supply']:+.2f}%)"
                dem_h = f"Rp {smc_1h['demand']:.0f} ({smc_1h['pct_to_demand']:+.2f}%)"
                konten_laporan.append(f"   - SMC 1 Jam(1H): Supply: {sup_h} | Demand: {dem_h}")
            if smc_1h and smc_1h.get('status_7d'):
                konten_laporan.append(f"   - Status 7D   : {smc_1h['status_7d']}")
            elif smc_1d and smc_1d.get('status_7d'):
                konten_laporan.append(f"   - Status 7D   : {smc_1d['status_7d']}")
            konten_laporan.append("")
    else:
        konten_laporan.append("Tidak ada saham dengan 2 Dot Green malam ini.\n")
        
    # Bagian 3: 1 Timeframe (Diabaikan dari WA)
    konten_laporan.append("=" * 75)
    konten_laporan.append(f"[BAGIAN 3] SAHAM DENGAN 1 TIMEFRAME SAJA - {len(saham_1_dot)} SAHAM (DIABAIKAN DARI WA):")
    konten_laporan.append("=" * 75)
    if saham_1_dot:
        for item in saham_1_dot:
            st = item["stock"]
            tf = item["timeframes"]
            active_tf = []
            if tf.get('D', {}).get('status'): active_tf.append(f"1D ({tf['D']['date']})")
            if tf.get('60', {}).get('status'): active_tf.append(f"1H ({tf['60']['date']})")
            if tf.get('15', {}).get('status'): active_tf.append(f"15M ({tf['15']['date']})")
            tf_str = ", ".join(active_tf)
            konten_laporan.append(f"• {st['symbol']:<6} | Rp {st['close']:<4.0f} ({st['change']:+6.2f}%) | Dot di: {tf_str}")
        konten_laporan.append("")
    else:
        konten_laporan.append("Tidak ada.\n")
        
    # Bagian 4: Rekapitulasi Seluruh Saham
    konten_laporan.append("=" * 75)
    konten_laporan.append(f"[BAGIAN 4] REKAPITULASI SELURUH {len(hasil_deteksi)} SAHAM HUNTER:")
    konten_laporan.append("=" * 75)
    for item in hasil_deteksi:
        st = item["stock"]
        k_dot = item.get("count_green", 0)
        status_text = f"🟢 {k_dot} TIMEFRAME" if k_dot > 0 else "⚪ Netral"
        konten_laporan.append(f"- {st['symbol']:<6} : Rp {st['close']:<4.0f} ({st['change']:+6.2f}%) -> {status_text}")
        
    isi_teks = "\n".join(konten_laporan)
    
    # Simpan ke folder reports/ lokal
    laporan_filename = REPORTS_DIR / f"laporan_hunter_{date_str}.txt"
    with open(laporan_filename, "w", encoding="utf-8") as f:
        f.write(isi_teks)
        
    # Simpan juga langsung ke folder Downloads komputer Anda
    downloads_dir = Path.home() / "Downloads"
    downloads_file = downloads_dir / f"laporan_hunter_{date_str}.txt"
    try:
        with open(downloads_file, "w", encoding="utf-8") as f:
            f.write(isi_teks)
        print(f"\n📂 File laporan Notepad berhasil dibuat di folder Downloads Anda:")
        print(f"👉 {downloads_file}")
        
        # Otomatis buka file di Notepad Windows
        if sys.platform == "win32":
            os.system(f'start notepad "{downloads_file}"')
    except Exception as e:
        print(f"[INFO] Gagal simpan ke Downloads: {e}")

    # 5. Susun Pesan Rangkuman WhatsApp (HANYA MINIMAL 2 TIMEFRAME)
    if send_wa:
        pesan_wa = (
            f"📊 *RADAR SAHAM HUNTER (RALLY GOD)*\n"
            f"📅 *{tgl_analisa_id}* • ⏰ *{now_wib.strftime('%H:%M WIB')}*\n"
            f"🎯 *Filter*: Rp 10–1.000 | Vol > 10D | Pre-mkt > 500%\n"
            f"⏱️ *Rentang Sinyal*: 30 Hari Terakhir\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
        )
        
        has_multi_tf = bool(saham_3_dot or saham_2_dot)
        
        if not has_multi_tf:
            pesan_wa += (
                f"\nℹ️ *TIDAK ADA SAHAM MINIMAL 2 TIMEFRAME*\n"
                f"Malam ini belum ada saham yang mengonfirmasi sinyal Dot Green di minimal 2 timeframe.\n"
            )
        else:
            # 1. KELOMPOK 3 TIMEFRAME (PRIORITAS UTAMA)
            if saham_3_dot:
                pesan_wa += (
                    f"\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔥 *DOT GREEN 3 TIMEFRAME*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🟢 *ANALISA SAHAM INI !!!* 🟢\n\n"
                )
                for idx, item in enumerate(saham_3_dot, 1):
                    st = item["stock"]
                    tf = item["timeframes"]
                    gain_str = format_gain_header(tf)
                    gain_line = f"{gain_str.strip()}\n" if gain_str else ""
                    smc_1d = tf.get('D', {}).get('smc')
                    smc_1h = tf.get('60', {}).get('smc')
                    smc_line = format_smc_wa(smc_1d, smc_1h)
                    pesan_wa += (
                        f"{idx}. *{st['symbol']}* — Rp {st['close']:.0f}\n"
                        f"{gain_line}"
                        f"📊 Volume: {st['volume']:,.0f} lembar\n"
                        f"• Daily (1D)  : {tf['D']['date']}\n"
                        f"• 1 Jam (1H)  : {tf['60']['date']}\n"
                        f"• 15 Mnt (15M): {tf['15']['date']}\n"
                        f"{smc_line}"
                    )
                    if idx < len(saham_3_dot):
                        pesan_wa += "───────────────────\n"
            else:
                pesan_wa += (
                    f"\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔥 *DOT GREEN 3 TIMEFRAME*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"_Tidak ada saham dengan 3 Dot Green malam ini._\n"
                )
                
            # 2. KELOMPOK 2 TIMEFRAME (RADAR POTENSIAL)
            if saham_2_dot:
                pesan_wa += (
                    f"\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"⚡ *DOT GREEN 2 TIMEFRAME*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🟡 *PANTAU SAHAM INI !!!* 🟡\n\n"
                )
                for idx, item in enumerate(saham_2_dot, 1):
                    st = item["stock"]
                    tf = item["timeframes"]
                    gain_str = format_gain_header(tf)
                    gain_line = f"{gain_str.strip()}\n" if gain_str else ""
                    smc_1d = tf.get('D', {}).get('smc')
                    smc_1h = tf.get('60', {}).get('smc')
                    smc_line = format_smc_wa(smc_1d, smc_1h)
                    pesan_wa += (
                        f"{idx}. *{st['symbol']}* — Rp {st['close']:.0f}\n"
                        f"{gain_line}"
                        f"📊 Volume: {st['volume']:,.0f} lembar\n"
                    )
                    if tf.get('D', {}).get('status'):
                        pesan_wa += f"• Daily (1D)  : {tf['D']['date']}\n"
                    if tf.get('60', {}).get('status'):
                        pesan_wa += f"• 1 Jam (1H)  : {tf['60']['date']}\n"
                    if tf.get('15', {}).get('status'):
                        pesan_wa += f"• 15 Mnt (15M): {tf['15']['date']}\n"
                    pesan_wa += f"{smc_line}"
                    if idx < len(saham_2_dot):
                        pesan_wa += "───────────────────\n"
            else:
                pesan_wa += (
                    f"\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"⚡ *DOT GREEN 2 TIMEFRAME*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"_Tidak ada saham dengan 2 Dot Green malam ini._\n"
                )

        pesan_wa += (
            f"\n━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 *REKAPITULASI PEMINDAIAN*:\n"
            f"• Total Saham Screener : {len(hasil_deteksi)} Saham\n"
            f"• 🔥 Lolos 3 Timeframe : {len(saham_3_dot)} Saham (Prioritas)\n"
            f"• ⚡ Lolos 2 Timeframe : {len(saham_2_dot)} Saham (Potensial)\n"
            f"• ⚪ 1 Timeframe Saja  : {len(saham_1_dot)} Saham (Diabaikan)\n"
            f"• ⚪ 0 Timeframe       : {len(saham_0_dot)} Saham (Netral)\n\n"
            f"💡 _Hanya saham dengan minimal 2 Timeframe yang dikirimkan ke WhatsApp agar ringkas dan fokus di HP._\n"
            f"📁 _Laporan lengkap seluruh {len(hasil_deteksi)} saham tersimpan di file Notepad Downloads & repository._\n"
            f"🌐 _Bot Agent Okto 24 Jam Otomatis_"
        )
        kirim_whatsapp(pesan_wa)
    else:
        print("ℹ️ Mode Uji Coba: Pengiriman WhatsApp dilewati (hanya mencatat ke file Notepad).")
        
    # Pastikan seluruh sisa screenshot dibersihkan
    bersihkan_screenshot()

# ============================================================================
# MAIN LOOP SCHEDULER: JALAN SETIAP MALAM PUKUL 19.00 WIB
# ============================================================================
def main():
    print("================================================================")
    print("🚀 BOT HUNTER + RALLY GOD 19.00 WIB (OKTOVAAAAA) DIAKTIFKAN")
    print(f"⏰ Jadwal Rutin: Setiap malam pukul {JAM_SCAN_WIB:02d}:{MENIT_SCAN_WIB:02d} WIB")
    print("================================================================")
    
    # Argumen --now untuk pengujian langsung
    if len(sys.argv) > 1 and "--now" in sys.argv:
        send_wa = "--wa" in sys.argv
        if send_wa:
            print("[TEST MODE] Menjalankan scan langsung saat ini & MENGIRIM NOTIFIKASI KE WHATSAPP...")
        else:
            print("[TEST MODE] Menjalankan scan langsung saat ini (tanpa kirim ke WhatsApp, tambahkan --wa untuk kirim ke WA)...")
        asyncio.run(run_daily_scan(send_wa=send_wa))
        return

    kirim_whatsapp("🤖 *BOT HUNTER RALLY GOD SIAP!*\nBot server standby dan akan otomatis melakukan scan setiap malam pukul 19:00 WIB.")
    
    scan_terakhir_tanggal = None
    
    while True:
        try:
            now_wib = datetime.datetime.now(WIB_TZ)
            hari_ini = now_wib.date()
            
            # Cek apakah jam sudah mencapai 19.00 WIB dan belum scan hari ini
            if (now_wib.hour == JAM_SCAN_WIB and 
                now_wib.minute >= MENIT_SCAN_WIB and 
                scan_terakhir_tanggal != hari_ini):
                
                print(f"⏰ Waktu menunjukkan {now_wib.strftime('%H:%M WIB')}. Memulai scan...")
                asyncio.run(run_daily_scan())
                scan_terakhir_tanggal = hari_ini
                
            # Istirahat 30 detik sebelum memeriksa jam berikutnya
            time.sleep(30)
            
        except KeyboardInterrupt:
            print("\nBot dihentikan oleh pengguna.")
            break
        except Exception as e:
            print(f"[MAIN LOOP ERROR] {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
