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

# Jadwal & Parameter Analisis (Default: Pukul 16.30 WIB / 04:30 Sore pasca tutup bursa)
JAM_SCAN_WIB = int(os.environ.get("JAM_SCAN_WIB", 16))
MENIT_SCAN_WIB = int(os.environ.get("MENIT_SCAN_WIB", 30))
LOOKBACK_DAYS = 30              # Cek sinyal 1 bulan terakhir (30 hari)
LIMIT_SAHAM_SCAN = int(os.environ.get("LIMIT_SAHAM_SCAN", 0))           # 0 = Ambil seluruh saham lolos screener tanpa batas (bisa diatur misal 20, 50, atau 0 untuk semua)

# Timeframe yang dicek sesuai permintaan (1D, 1H, 15M)
TIMEFRAMES = [
    {"code": "D", "name": "Daily (1D)", "interval": "D"},
    {"code": "60", "name": "1 Jam (1H)", "interval": "60"},
    {"code": "15", "name": "15 Menit (15M)", "interval": "15"}
]

# Folder Penyimpanan Laporan (Opsional)
REPORTS_DIR = Path("reports")
try:
    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "screenshots").mkdir(exist_ok=True)
except Exception:
    pass

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
        
        now_ts = datetime.datetime.now(WIB_TZ).timestamp()
        week_sec = 7 * 86400
        recent_bos = [b for b in bos_list if b.get('timestamp') and (now_ts - b['timestamp']) <= week_sec]
        
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
        
    if recent_bars:
        return calculate_smc_levels_fallback(recent_bars, cur_close)
    return None

def format_donalt_wa(tf_results):
    """
    Format sinyal Golden Cross & Death Cross (EMA + DonAlt Suite)
    untuk 3 timeframe (1D, 1H, 15M) di WhatsApp.
    Hanya menamai Golden atau Death (tanpa dot green agar tidak dobel).
    Menandai tanggal kemunculan dalam rentang 30 hari terakhir.
    """
    lines = []
    tf_order = [("D", "1D"), ("60", "1H"), ("15", "15M")]
    has_any = False
    sub_lines = []
    
    for code, label in tf_order:
        tf_data = tf_results.get(code, {})
        donalt = tf_data.get("donalt", {})
        g = donalt.get("golden")
        d = donalt.get("death")
        
        parts = []
        if g:
            has_any = True
            if g.get('gain_pct') is not None:
                rev_s = " s/d Death" if g.get('reversed') else ""
                gain_str = f" ({g['gain_pct']:+.2f}%{rev_s})"
            else:
                gain_str = ""
            parts.append(f"✨ Golden: {g['date']}{gain_str}")
        if d:
            has_any = True
            parts.append(f"⚠️ Death: {d['date']}")
            
        if parts:
            sub_lines.append(f"• {label:<4}: " + " | ".join(parts))
        else:
            sub_lines.append(f"• {label:<4}: -")
            
    lines.append("🏆 *EMA + DonAlt (30 Hari)*:")
    lines.extend(sub_lines)
    return "\n".join(lines) + "\n"

def format_donalt_notepad(tf_results):
    """Format sinyal Golden Cross & Death Cross untuk laporan Notepad."""
    lines = []
    tf_order = [("D", "Daily (1D)  "), ("60", "1 Jam (1H)  "), ("15", "15 Mnt (15M)")]
    for code, label in tf_order:
        tf_data = tf_results.get(code, {})
        donalt = tf_data.get("donalt", {})
        g = donalt.get("golden")
        d = donalt.get("death")
        
        parts = []
        if g:
            if g.get('gain_pct') is not None:
                rev_s = " s/d Death" if g.get('reversed') else ""
                gain_str = f" (Kenaikan: {g['gain_pct']:+.2f}%{rev_s})"
            else:
                gain_str = ""
            parts.append(f"✨ Golden: {g['date']} @ Rp {g['price']:.0f}{gain_str}")
        else:
            parts.append("✨ Golden: -")
            
        if d:
            parts.append(f"⚠️ Death: {d['date']} @ Rp {d['price']:.0f}")
        else:
            parts.append("⚠️ Death: -")
            
        lines.append(f"   - EMA Cross {label}: " + " | ".join(parts))
    return lines

def format_macd_wa(tf_results):
    """
    Format sinyal Bull & Bear (MACD Divergences)
    untuk 3 timeframe (1D, 1H, 15M) di WhatsApp (30 hari terakhir).
    """
    lines = []
    tf_order = [("D", "1D"), ("60", "1H"), ("15", "15M")]
    sub_lines = []
    
    for code, label in tf_order:
        tf_data = tf_results.get(code, {})
        macd = tf_data.get("macd", {})
        bull = macd.get("bull")
        bear = macd.get("bear")
        
        parts = []
        if bull:
            parts.append(f"🐂 {bull['type']}: {bull['date']}")
        if bear:
            parts.append(f"🐻 {bear['type']}: {bear['date']}")
            
        if parts:
            sub_lines.append(f"• {label:<4}: " + " | ".join(parts))
        else:
            sub_lines.append(f"• {label:<4}: -")
            
    lines.append("🌊 *MACD Divergences (30 Hari)*:")
    lines.extend(sub_lines)
    return "\n".join(lines) + "\n"

def format_macd_notepad(tf_results):
    """Format sinyal MACD Divergences (Bull & Bear) untuk laporan Notepad."""
    lines = []
    tf_order = [("D", "Daily (1D)  "), ("60", "1 Jam (1H)  "), ("15", "15 Mnt (15M)")]
    for code, label in tf_order:
        tf_data = tf_results.get(code, {})
        macd = tf_data.get("macd", {})
        bull = macd.get("bull")
        bear = macd.get("bear")
        
        parts = []
        if bull:
            parts.append(f"🐂 {bull['type']}: {bull['date']} @ Rp {bull['price']:.0f}")
        else:
            parts.append("🐂 Bull: -")
            
        if bear:
            parts.append(f"🐻 {bear['type']}: {bear['date']} @ Rp {bear['price']:.0f}")
        else:
            parts.append("🐻 Bear: -")
            
        lines.append(f"   - MACD Div  {label}: " + " | ".join(parts))
    return lines

def format_scalping_wa(tf_results):
    """
    Format sinyal BUY & SELL serta status Trend dari indikator
    ( ͡° ͜ʖ ͡°) Scalping vs Swing Trading untuk 3 timeframe (1D, 1H, 15M) di WhatsApp.
    """
    lines = []
    tf_order = [("D", "1D"), ("60", "1H"), ("15", "15M")]
    sub_lines = []
    
    for code, label in tf_order:
        tf_data = tf_results.get(code, {})
        sc = tf_data.get("scalping", {})
        buy = sc.get("buy")
        sell = sc.get("sell")
        trend = sc.get("trend")
        
        parts = []
        if buy:
            if buy.get('gain_pct') is not None:
                rev_s = " s/d SELL" if buy.get('reversed') else ""
                gain_s = f" ({buy['gain_pct']:+.2f}%{rev_s})"
            else:
                gain_s = ""
            parts.append(f"🟢 BUY: {buy['date']}{gain_s}")
        if sell:
            parts.append(f"🔴 SELL: {sell['date']}")
        if trend and trend != "-":
            parts.append(f"Trend: {trend}")
            
        if parts:
            sub_lines.append(f"• {label:<4}: " + " | ".join(parts))
        else:
            sub_lines.append(f"• {label:<4}: -")
            
    lines.append("⚔️ *Scalping vs Swing Trading (30 Hari)*:")
    lines.extend(sub_lines)
    return "\n".join(lines) + "\n"

def format_scalping_notepad(tf_results):
    """Format sinyal Scalping vs Swing Trading untuk laporan Notepad."""
    lines = []
    tf_order = [("D", "Daily (1D)  "), ("60", "1 Jam (1H)  "), ("15", "15 Mnt (15M)")]
    for code, label in tf_order:
        tf_data = tf_results.get(code, {})
        sc = tf_data.get("scalping", {})
        buy = sc.get("buy")
        sell = sc.get("sell")
        trend = sc.get("trend") or "-"
        
        parts = []
        if buy:
            if buy.get('gain_pct') is not None:
                rev_s = " s/d SELL" if buy.get('reversed') else ""
                gain_s = f" ({buy['gain_pct']:+.2f}%{rev_s})"
            else:
                gain_s = ""
            parts.append(f"🟢 BUY: {buy['date']} @ Rp {buy['price']:.0f}{gain_s}")
        else:
            parts.append("🟢 BUY: -")
            
        if sell:
            parts.append(f"🔴 SELL: {sell['date']} @ Rp {sell['price']:.0f}")
        else:
            parts.append("🔴 SELL: -")
            
        parts.append(f"Trend: {trend}")
        lines.append(f"   - Scalping  {label}: " + " | ".join(parts))
    return lines

def format_smc_wa(smc_1d, smc_1h=None):
    """Format tampilan SMC Supply, Demand & Status 7D untuk Timeframe 1D & 1H di WhatsApp."""
    if isinstance(smc_1d, dict) and smc_1h is None:
        smc_1h = smc_1d
        smc_1d = None
        
    lines = []
    if smc_1d and smc_1d.get('supply') and smc_1d.get('demand'):
        sup_d = f"Rp {smc_1d['supply']:.0f} ({smc_1d['pct_to_supply']:+.2f}%)"
        dem_d = f"Rp {smc_1d['demand']:.0f} ({smc_1d['pct_to_demand']:+.2f}%)"
        lines.append(f"• 1D  : Sup {sup_d} | Dem {dem_d}")
        
    if smc_1h and smc_1h.get('supply') and smc_1h.get('demand'):
        sup_h = f"Rp {smc_1h['supply']:.0f} ({smc_1h['pct_to_supply']:+.2f}%)"
        dem_h = f"Rp {smc_1h['demand']:.0f} ({smc_1h['pct_to_demand']:+.2f}%)"
        lines.append(f"• 1H  : Sup {sup_h} | Dem {dem_h}")
        
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
        return "🎯 *Supply & Demand (SMC Suite)*:\n" + "\n".join(lines) + "\n"
    return ""

def format_smc_notepad(tf_results):
    """Format sinyal SMC Supply, Demand & Status 7D untuk laporan Notepad."""
    lines = []
    smc_1d = tf_results.get('D', {}).get('smc')
    smc_1h = tf_results.get('60', {}).get('smc')
    
    if smc_1d and smc_1d.get('supply') and smc_1d.get('demand'):
        sup_d = f"Rp {smc_1d['supply']:.0f} ({smc_1d['pct_to_supply']:+.2f}%)"
        dem_d = f"Rp {smc_1d['demand']:.0f} ({smc_1d['pct_to_demand']:+.2f}%)"
        lines.append(f"   - SMC Daily (1D)       : Supply: {sup_d} | Demand: {dem_d}")
    if smc_1h and smc_1h.get('supply') and smc_1h.get('demand'):
        sup_h = f"Rp {smc_1h['supply']:.0f} ({smc_1h['pct_to_supply']:+.2f}%)"
        dem_h = f"Rp {smc_1h['demand']:.0f} ({smc_1h['pct_to_demand']:+.2f}%)"
        lines.append(f"   - SMC 1 Jam (1H)       : Supply: {sup_h} | Demand: {dem_h}")
    if smc_1h and smc_1h.get('status_7d'):
        lines.append(f"   - SMC Status 7D        : {smc_1h['status_7d']}")
    elif smc_1d and smc_1d.get('status_7d'):
        lines.append(f"   - SMC Status 7D        : {smc_1d['status_7d']}")
    return lines

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
        try:
            chart_url = f"{CHART_LAYOUT_URL}?symbol=IDX%3A{symbol}&interval=D"
            await page.goto(chart_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3.5)
        except Exception as e:
            print(f" ⚠️ Kendala navigasi chart {symbol}: {e}")
            return results
    
    # 2. Cek setiap timeframe (D, 60, 15)
    for tf in TIMEFRAMES:
        tf_code = tf['code']
        tf_name = tf['name']
        
        print(f"   ↳ Mengecek {symbol} [{tf_name}]...", end="", flush=True)
        
        try:
            # Ganti resolusi / timeframe secara instan tanpa reload penuh
            await page.evaluate('(r) => window._exposed_chartWidgetCollection?.activeChartWidget?.value()?.setResolution(r)', tf['interval'])
            await asyncio.sleep(1.8)
            
            # Ambil data Dot Green (RallyGood), Golden/Death (DonAlt), Supply/Demand (SMC),
            # BUY/SELL/Trend (Scalping vs Swing Trading), dan Bull/Bear (MACD Divergences)
            # dengan teknik Dynamic Swapping berurutan agar tidak pernah melebihi batas 2 indikator TradingView gratis.
            eval_data = await page.evaluate('''async () => {
                try {
                    const chart = window._exposed_chartWidgetCollection?.activeChartWidget?.value();
                    if (!chart) return { dots: [], donalt: { golden: [], death: [] }, smc: null, scalping: { buy: [], sell: [], trend: null }, macd: { bull: [], bear: [] }, currentClose: null, bars: [] };
                    const model = chart.model();
                    const ts = model.timeScale();
                    const ms = model.mainSeries();
                    const barsObj = ms && ms.bars ? ms.bars() : null;
                    const lastIdx = barsObj && barsObj.lastIndex ? barsObj.lastIndex() : (barsObj && barsObj.last ? barsObj.last().index : 0);
                    const lastBar = barsObj && barsObj.last ? barsObj.last() : null;
                    const currentClose = lastBar && lastBar.value ? lastBar.value[4] : null;

                    // Bar historis untuk fallback kalkulasi SMC jika diperlukan
                    const recentBars = [];
                    if (barsObj && barsObj.valueAt) {
                        for (let i = Math.max(0, lastIdx - 50); i <= lastIdx; i++) {
                            const b = barsObj.valueAt(i);
                            if (b) recentBars.push({ time: b[0], open: b[1], high: b[2], low: b[3], close: b[4], volume: b[5] });
                        }
                    }

                    const allStudies = model.panes().flatMap(p => p.dataSources());
                    const smcStudy = allStudies.find(s => s.title && s.title().includes('Ultimate SMC Suite'));
                    const donaltStudy = allStudies.find(s => s.title && s.title().includes('EMA + DonAlt Suite'));
                    const rallyStudy = allStudies.find(s => s.title && s.title().includes('RallyGood'));
                    const scStudy = allStudies.find(s => s.title && s.title().includes('Scalping vs Swing Trading'));
                    const macdStudy = allStudies.find(s => s.title && s.title().includes('MACD Divergences'));

                    // FASE 0: Keamanan awal - pastikan hanya EMA + DonAlt & RallyGood yang aktif (Maksimal 2 Indikator)
                    // Matikan dulu indikator sekunder sebelum menyalakan indikator utama agar TradingView tidak menolak batas 2 indikator
                    let needWait = false;
                    if (smcStudy?.properties?.().visible?.value()) { smcStudy.properties().visible.setValue(false); needWait = true; }
                    if (scStudy?.properties?.().visible?.value()) { scStudy.properties().visible.setValue(false); needWait = true; }
                    if (macdStudy?.properties?.().visible?.value()) { macdStudy.properties().visible.setValue(false); needWait = true; }
                    if (needWait) await new Promise(r => setTimeout(r, 400));

                    if (donaltStudy?.properties?.().visible && !donaltStudy.properties().visible.value()) {
                        donaltStudy.properties().visible.setValue(true);
                    }
                    if (rallyStudy?.properties?.().visible && !rallyStudy.properties().visible.value()) {
                        rallyStudy.properties().visible.setValue(true);
                    }
                    await new Promise(r => setTimeout(r, 600));

                    // FASE 1: Ekstraksi RallyGood (Dot Green) & EMA + DonAlt Suite (Golden/Death Cross)
                    // Tunggu hingga RallyGood paneViews terisi (polling hingga 1500ms)
                    if (rallyStudy) {
                        for (let r = 0; r < 15; r++) {
                            const greenPv = (rallyStudy._paneViews || []).find(pv => pv._plotName === 'plot_2');
                            if (greenPv && greenPv._items && greenPv._items.length > 0) break;
                            await new Promise(resolve => setTimeout(resolve, 100));
                        }
                    }

                    let dots = [];
                    if (rallyStudy) {
                        const greenPv = (rallyStudy._paneViews || []).find(pv => pv._plotName === 'plot_2');
                        if (greenPv) {
                            const activeDots = (greenPv._items || []).filter(it => !isNaN(it.y));
                            dots = activeDots.map(dot => {
                                const tp = ts.indexToTimePoint(dot.timePointIndex);
                                let dotClose = null;
                                if (barsObj && barsObj.valueAt) {
                                    const bar = barsObj.valueAt(dot.timePointIndex);
                                    if (bar && bar.length > 4) dotClose = bar[4];
                                }
                                return {
                                    timestamp: tp,
                                    dotClose: dotClose,
                                    currentClose: currentClose
                                };
                            }).filter(d => d.timestamp !== null && d.timestamp !== undefined);
                        }
                    }

                    let goldenList = [];
                    let deathList = [];
                    if (donaltStudy) {
                        const d = donaltStudy.data();
                        if (d) {
                            for (let i = d.firstIndex(); i <= d.lastIndex(); i++) {
                                const val = d.valueAt(i);
                                if (val && Array.isArray(val)) {
                                    const tp = ts.indexToTimePoint(i);
                                    const barVal = barsObj ? barsObj.valueAt(i) : null;
                                    const barTime = barVal ? barVal[0] : tp;
                                    const barClose = barVal ? barVal[4] : null;
                                    
                                    if (val[10] === 1 || val[16] === 1) {
                                        goldenList.push({ idx: i, timestamp: barTime, price: barClose });
                                    }
                                    if (val[11] === 1 || val[17] === 1) {
                                        deathList.push({ idx: i, timestamp: barTime, price: barClose });
                                    }
                                }
                            }
                        }
                    }

                    // FASE 2: GANTIAN! Matikan RallyGood, Nyalakan Ultimate SMC Suite (Cek Supply & Demand)
                    // Total indikator aktif: 2 (DonAlt + SMC)
                    if (rallyStudy?.properties?.().visible) rallyStudy.properties().visible.setValue(false);
                    await new Promise(r => setTimeout(r, 400));
                    if (smcStudy?.properties?.().visible) smcStudy.properties().visible.setValue(true);
                    await new Promise(r => setTimeout(r, 700));

                    let smcData = null;
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

                    // FASE 3: GANTIAN! Matikan Ultimate SMC Suite, Nyalakan ( ͡° ͜ʖ ͡°) Scalping vs Swing Trading
                    // Total indikator aktif: 2 (DonAlt + Scalping vs Swing Trading)
                    if (smcStudy?.properties?.().visible) smcStudy.properties().visible.setValue(false);
                    await new Promise(r => setTimeout(r, 400));
                    if (scStudy?.properties?.().visible) scStudy.properties().visible.setValue(true);
                    
                    // Beri waktu TradingView mengkalkulasi data Scalping vs Swing Trading (polling hingga 1200ms)
                    for (let r = 0; r < 12; r++) {
                        await new Promise(resolve => setTimeout(resolve, 100));
                        const scD = scStudy?.data?.();
                        if (scD && scD.lastIndex() > 0) {
                            const lastV = scD.valueAt(scD.lastIndex());
                            if (lastV && Array.isArray(lastV)) break;
                        }
                    }

                    let buyList = [];
                    let sellList = [];
                    let currentTrend = null;
                    if (scStudy) {
                        const scData = scStudy.data();
                        if (scData) {
                            for (let i = scData.lastIndex(); i >= Math.max(0, scData.firstIndex()); i--) {
                                const v = scData.valueAt(i);
                                if (v && Array.isArray(v) && (v[2] === 0 || v[2] === 1)) {
                                    currentTrend = (v[2] === 0) ? 'BUY (Green)' : 'SELL (Red)';
                                    break;
                                }
                            }
                            for (let i = Math.max(0, scData.firstIndex()); i <= scData.lastIndex(); i++) {
                                const val = scData.valueAt(i);
                                if (val && Array.isArray(val)) {
                                    const tp = ts.indexToTimePoint(i);
                                    const barVal = barsObj ? barsObj.valueAt(i) : null;
                                    const barTime = barVal ? barVal[0] : tp;
                                    const barClose = barVal ? barVal[4] : null;

                                    // plot_2 / val[3] adalah sinyal BUY shape
                                    if (val[3] !== null && val[3] !== undefined && !isNaN(val[3])) {
                                        buyList.push({ idx: i, timestamp: barTime, price: val[3] || barClose });
                                    }
                                    // plot_3 / val[4] adalah sinyal SELL shape
                                    if (val[4] !== null && val[4] !== undefined && !isNaN(val[4])) {
                                        sellList.push({ idx: i, timestamp: barTime, price: val[4] || barClose });
                                    }
                                }
                            }
                        }
                    }

                    // FASE 4: GANTIAN! Matikan Scalping vs Swing Trading, Nyalakan MACD Divergences
                    // Total indikator aktif: 2 (DonAlt + MACD)
                    if (scStudy?.properties?.().visible) scStudy.properties().visible.setValue(false);
                    await new Promise(r => setTimeout(r, 400));
                    if (macdStudy?.properties?.().visible) macdStudy.properties().visible.setValue(true);
                    
                    // Beri waktu TradingView mengkalkulasi data MACD (polling hingga 1200ms)
                    for (let r = 0; r < 12; r++) {
                        await new Promise(resolve => setTimeout(resolve, 100));
                        const mdD = macdStudy?.data?.();
                        if (mdD && mdD.lastIndex() > 0) {
                            const lastV = mdD.valueAt(mdD.lastIndex());
                            if (lastV && Array.isArray(lastV)) break;
                        }
                    }

                    let bullList = [];
                    let bearList = [];
                    if (macdStudy) {
                        const md = macdStudy.data();
                        if (md) {
                            for (let i = Math.max(0, md.firstIndex()); i <= md.lastIndex(); i++) {
                                const val = md.valueAt(i);
                                if (val && Array.isArray(val)) {
                                    const tp = ts.indexToTimePoint(i);
                                    const barVal = barsObj ? barsObj.valueAt(i) : null;
                                    const barTime = barVal ? barVal[0] : tp;
                                    const barClose = barVal ? barVal[4] : null;
                                    
                                    // plot_18: Regular Bull, plot_20: Hidden Bull
                                    if (val[19] === 1 || val[21] === 1) {
                                        bullList.push({ idx: i, timestamp: barTime, price: barClose, type: val[19] === 1 ? 'Bull' : 'H Bull' });
                                    }
                                    // plot_19: Regular Bear, plot_21: Hidden Bear
                                    if (val[20] === 1 || val[22] === 1) {
                                        bearList.push({ idx: i, timestamp: barTime, price: barClose, type: val[20] === 1 ? 'Bear' : 'H Bear' });
                                    }
                                }
                            }
                        }
                    }

                    // FASE 5: RESTORE! Matikan MACD Divergences, Nyalakan kembali RallyGood
                    // Kembali ke layout 2 indikator standar (DonAlt + RallyGood)
                    if (macdStudy?.properties?.().visible) macdStudy.properties().visible.setValue(false);
                    await new Promise(r => setTimeout(r, 400));
                    if (rallyStudy?.properties?.().visible) rallyStudy.properties().visible.setValue(true);
                    await new Promise(r => setTimeout(r, 600));

                    return {
                        dots: dots,
                        donalt: { golden: goldenList, death: deathList },
                        smc: smcData,
                        scalping: { buy: buyList, sell: sellList, trend: currentTrend },
                        macd: { bull: bullList, bear: bearList },
                        currentClose: currentClose,
                        bars: recentBars
                    };
                } catch(e) {
                    return { dots: [], donalt: { golden: [], death: [] }, smc: null, scalping: { buy: [], sell: [], trend: null }, macd: { bull: [], bear: [] }, currentClose: null, bars: [], error: String(e) };
                }
            }''')
            
            dot_data = eval_data.get('dots', [])
            cur_close = eval_data.get('currentClose') or stock_info.get('close')
            donalt_raw = eval_data.get('donalt', {})
            smc_raw = eval_data.get('smc')
            scalping_raw = eval_data.get('scalping', {})
            macd_raw = eval_data.get('macd', {})
            recent_bars = eval_data.get('bars', [])
            
            # 1. Olah RallyGood Dot Green (30 hari terakhir)
            valid_dots = []
            for d in dot_data:
                tp = d.get('timestamp')
                if tp and isinstance(tp, (int, float)):
                    dot_dt = datetime.datetime.fromtimestamp(tp, WIB_TZ)
                    diff_days = (now_dt - dot_dt).total_seconds() / 86400
                    if 0 <= diff_days <= LOOKBACK_DAYS:
                        valid_dots.append({
                            "dt": dot_dt,
                            "dot_close": d.get("dotClose"),
                            "current_close": d.get("currentClose")
                        })
            
            dot_status = False
            date_display = None
            dot_close = None
            gain_pct = None
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
                if dot_close and cur_close and dot_close > 0:
                    gain_pct = ((cur_close - dot_close) / dot_close) * 100
                dot_status = True

            # 2. Olah EMA + DonAlt Suite (Golden & Death Cross - 30 hari terakhir)
            now_ts = now_dt.timestamp()
            limit_ts = now_ts - (LOOKBACK_DAYS * 86400)
            
            recent_golden = [g for g in donalt_raw.get('golden', []) if g.get('timestamp') and g['timestamp'] >= limit_ts]
            recent_death = [d for d in donalt_raw.get('death', []) if d.get('timestamp') and d['timestamp'] >= limit_ts]
            
            golden_res = None
            if recent_golden:
                latest_g = max(recent_golden, key=lambda x: x['timestamp'])
                g_dt = datetime.datetime.fromtimestamp(latest_g['timestamp'], WIB_TZ)
                b_str = BULAN_PENDEK.get(g_dt.month, g_dt.strftime("%b"))
                g_date = f"{g_dt.day} {b_str} {g_dt.year}" if tf_code == 'D' else f"{g_dt.day} {b_str} {g_dt.year}, {g_dt.strftime('%H:%M')} WIB"
                g_price = latest_g.get('price')
                
                # Cek apakah trend berbalik arah ke Death Cross setelah sinyal Golden Cross ini
                all_deaths = donalt_raw.get('death', [])
                deaths_after_g = [d for d in all_deaths if d.get('timestamp') and d['timestamp'] > latest_g['timestamp']]
                g_reversed = False
                g_exit_price = cur_close
                if deaths_after_g:
                    first_d = min(deaths_after_g, key=lambda x: x['timestamp'])
                    if first_d.get('price'):
                        g_exit_price = first_d.get('price')
                        g_reversed = True
                        
                g_gain = ((g_exit_price - g_price) / g_price * 100) if (g_exit_price and g_price and g_price > 0) else None
                golden_res = {
                    "date": g_date,
                    "dt": g_dt,
                    "price": g_price,
                    "exit_price": g_exit_price,
                    "reversed": g_reversed,
                    "gain_pct": g_gain
                }
                
            death_res = None
            if recent_death:
                latest_d = max(recent_death, key=lambda x: x['timestamp'])
                d_dt = datetime.datetime.fromtimestamp(latest_d['timestamp'], WIB_TZ)
                b_str = BULAN_PENDEK.get(d_dt.month, d_dt.strftime("%b"))
                d_date = f"{d_dt.day} {b_str} {d_dt.year}" if tf_code == 'D' else f"{d_dt.day} {b_str} {d_dt.year}, {d_dt.strftime('%H:%M')} WIB"
                d_price = latest_d.get('price')
                death_res = {
                    "date": d_date,
                    "dt": d_dt,
                    "price": d_price
                }
                
            donalt_res = {
                "golden": golden_res,
                "death": death_res
            }
            
            # 3. Olah Scalping vs Swing Trading (BUY & SELL Signals + Trend - 30 hari terakhir)
            recent_sc_buys = [b for b in scalping_raw.get('buy', []) if b.get('timestamp') and b['timestamp'] >= limit_ts]
            recent_sc_sells = [s for s in scalping_raw.get('sell', []) if s.get('timestamp') and s['timestamp'] >= limit_ts]
            
            sc_buy_res = None
            if recent_sc_buys:
                latest_buy = max(recent_sc_buys, key=lambda x: x['timestamp'])
                b_dt = datetime.datetime.fromtimestamp(latest_buy['timestamp'], WIB_TZ)
                b_str = BULAN_PENDEK.get(b_dt.month, b_dt.strftime("%b"))
                b_date = f"{b_dt.day} {b_str} {b_dt.year}" if tf_code == 'D' else f"{b_dt.day} {b_str} {b_dt.year}, {b_dt.strftime('%H:%M')} WIB"
                b_price = latest_buy.get('price')
                
                # Cek apakah trend berbalik arah ke SELL setelah sinyal BUY ini
                all_sells = scalping_raw.get('sell', [])
                sells_after_buy = [s for s in all_sells if s.get('timestamp') and s['timestamp'] > latest_buy['timestamp']]
                b_reversed = False
                b_exit_price = cur_close
                if sells_after_buy:
                    first_sell = min(sells_after_buy, key=lambda x: x['timestamp'])
                    if first_sell.get('price'):
                        b_exit_price = first_sell.get('price')
                        b_reversed = True
                        
                b_gain = ((b_exit_price - b_price) / b_price * 100) if (b_exit_price and b_price and b_price > 0) else None
                sc_buy_res = {
                    "date": b_date,
                    "dt": b_dt,
                    "price": b_price,
                    "exit_price": b_exit_price,
                    "reversed": b_reversed,
                    "gain_pct": b_gain
                }
                
            sc_sell_res = None
            if recent_sc_sells:
                latest_sell = max(recent_sc_sells, key=lambda x: x['timestamp'])
                s_dt = datetime.datetime.fromtimestamp(latest_sell['timestamp'], WIB_TZ)
                s_str = BULAN_PENDEK.get(s_dt.month, s_dt.strftime("%b"))
                s_date = f"{s_dt.day} {s_str} {s_dt.year}" if tf_code == 'D' else f"{s_dt.day} {s_str} {s_dt.year}, {s_dt.strftime('%H:%M')} WIB"
                s_price = latest_sell.get('price')
                sc_sell_res = {
                    "date": s_date,
                    "dt": s_dt,
                    "price": s_price
                }
                
            scalping_res = {
                "buy": sc_buy_res,
                "sell": sc_sell_res,
                "trend": scalping_raw.get('trend')
            }
            
            # 4. Olah Ultimate SMC Suite (Supply & Demand, Status 7D) untuk Daily (1D) dan 1 Jam (1H)
            smc_res = None
            if tf_code in ['D', '60']:
                smc_res = parse_real_smc_levels(smc_raw, cur_close, recent_bars)

            # 5. Olah MACD Divergences (Bull & Bear Divergence - 30 hari terakhir)
            recent_bull = [b for b in macd_raw.get('bull', []) if b.get('timestamp') and b['timestamp'] >= limit_ts]
            recent_bear = [b for b in macd_raw.get('bear', []) if b.get('timestamp') and b['timestamp'] >= limit_ts]
            
            bull_res = None
            if recent_bull:
                latest_b = max(recent_bull, key=lambda x: x['timestamp'])
                b_dt = datetime.datetime.fromtimestamp(latest_b['timestamp'], WIB_TZ)
                b_str = BULAN_PENDEK.get(b_dt.month, b_dt.strftime("%b"))
                b_date = f"{b_dt.day} {b_str} {b_dt.year}" if tf_code == 'D' else f"{b_dt.day} {b_str} {b_dt.year}, {b_dt.strftime('%H:%M')} WIB"
                bull_res = {
                    "type": latest_b.get("type", "Bull"),
                    "date": b_date,
                    "dt": b_dt,
                    "price": latest_b.get("price")
                }
                
            bear_res = None
            if recent_bear:
                latest_br = max(recent_bear, key=lambda x: x['timestamp'])
                br_dt = datetime.datetime.fromtimestamp(latest_br['timestamp'], WIB_TZ)
                br_str = BULAN_PENDEK.get(br_dt.month, br_dt.strftime("%b"))
                br_date = f"{br_dt.day} {br_str} {br_dt.year}" if tf_code == 'D' else f"{br_dt.day} {br_str} {br_dt.year}, {br_dt.strftime('%H:%M')} WIB"
                bear_res = {
                    "type": latest_br.get("type", "Bear"),
                    "date": br_date,
                    "dt": br_dt,
                    "price": latest_br.get("price")
                }
                
            macd_res = {
                "bull": bull_res,
                "bear": bear_res
            }
            
            # Tampilan konsol informatif
            indicator_tags = []
            if golden_res:
                rev_s = " s/d Death" if golden_res.get('reversed') else ""
                g_tag = f"✨ Golden: {golden_res['date']}"
                if golden_res['gain_pct'] is not None:
                    g_tag += f" ({golden_res['gain_pct']:+.2f}%{rev_s})"
                indicator_tags.append(g_tag)
            if death_res:
                indicator_tags.append(f"⚠️ Death: {death_res['date']}")
            if sc_buy_res:
                rev_s = " s/d SELL" if sc_buy_res.get('reversed') else ""
                sc_tag = f"⚔️ Scalp BUY: {sc_buy_res['date']}"
                if sc_buy_res['gain_pct'] is not None:
                    sc_tag += f" ({sc_buy_res['gain_pct']:+.2f}%{rev_s})"
                indicator_tags.append(sc_tag)
            if sc_sell_res:
                indicator_tags.append(f"🔴 Scalp SELL: {sc_sell_res['date']}")
            if scalping_res.get('trend'):
                indicator_tags.append(f"Trend: {scalping_res['trend']}")
            if smc_res and smc_res.get('status_7d'):
                indicator_tags.append(f"🎯 SMC: {smc_res['status_7d']}")
            if bull_res:
                indicator_tags.append(f"🐂 {bull_res['type']}: {bull_res['date']}")
            if bear_res:
                indicator_tags.append(f"🐻 {bear_res['type']}: {bear_res['date']}")
                
            indicator_str = f" [{', '.join(indicator_tags)}]" if indicator_tags else ""

            if dot_status:
                gain_info = f" (Kenaikan: {gain_pct:+.2f}%)" if gain_pct is not None else ""
                print(f" 🟢 ADA DOT GREEN! ({date_display}){gain_info}{indicator_str}")
            else:
                print(f" ❌ Tidak ada dot green{indicator_str}")

            results[tf_code] = {
                "status": dot_status,
                "date": date_display,
                "dot_close": dot_close,
                "gain_pct": gain_pct,
                "donalt": donalt_res,
                "scalping": scalping_res,
                "smc": smc_res,
                "macd": macd_res
            }
                    
        except Exception as e:
            print(f" ⚠️ Error: {e}")
            results[tf_code] = {"status": False, "date": None, "error": str(e)}
            
    return results

# ============================================================================
# TAHAP 4: EKSEKUSI UTAMA (SCAN HARIAN JAM 16.30 WIB)
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
            "--disable-gpu",
            "--js-flags=--max-old-space-size=512",
            "--disable-extensions",
            "--disable-background-networking",
            "--mute-audio"
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
        
        # Tunggu sampai chart TradingView siap (polling hingga 20 detik)
        for _ in range(20):
            await asyncio.sleep(1)
            ready = await page.evaluate('''() => {
                const chart = window._exposed_chartWidgetCollection?.activeChartWidget?.value();
                return !!chart && chart.model().panes().flatMap(p => p.dataSources()).length >= 4;
            }''')
            if ready:
                break
        
        # Pastikan status default indikator di awal: DonAlt (ON), RallyGood (ON), lainnya (OFF)
        print("⚙️ Sinkronisasi Indikator TradingView: EMA + DonAlt (ON), RallyGood (ON), Lainnya (OFF)...")
        await page.evaluate('''async () => {
            try {
                const chart = window._exposed_chartWidgetCollection?.activeChartWidget?.value();
                if (!chart) return;
                const allStudies = chart.model().panes().flatMap(p => p.dataSources());
                const smc = allStudies.find(s => s.title && s.title().includes('Ultimate SMC Suite'));
                const donalt = allStudies.find(s => s.title && s.title().includes('EMA + DonAlt Suite'));
                const rally = allStudies.find(s => s.title && s.title().includes('RallyGood'));
                const sc = allStudies.find(s => s.title && s.title().includes('Scalping vs Swing Trading'));
                const macd = allStudies.find(s => s.title && s.title().includes('MACD Divergences'));
                
                // Matikan dulu indikator ekstra agar slot TradingView 2 indikator bersih
                if (smc?.properties?.().visible) smc.properties().visible.setValue(false);
                if (sc?.properties?.().visible) sc.properties().visible.setValue(false);
                if (macd?.properties?.().visible) macd.properties().visible.setValue(false);
                await new Promise(r => setTimeout(r, 600));

                if (donalt?.properties?.().visible) donalt.properties().visible.setValue(true);
                if (rally?.properties?.().visible) rally.properties().visible.setValue(true);
                await new Promise(r => setTimeout(r, 1000));
            } catch(e) {}
        }''')
        await asyncio.sleep(1)
        
        # 3. Looping pengecekan chart saham dengan proteksi Self-Healing & Auto-Skip
        for idx, stock in enumerate(hunter_stocks, 1):
            sym = stock['symbol']
            print(f"\n[{idx}/{len(hunter_stocks)}] Memeriksa Saham: {sym} (Rp {stock['close']:.0f} | {stock['change']:+.2f}%)")
            
            try:
                tf_results = await scan_stock_rallygood(page, stock)
                
                # Cek apakah ada minimal satu timeframe dengan Dot Green
                any_green = any(tf_results.get(tf['code'], {}).get('status', False) for tf in TIMEFRAMES)
                
                hasil_deteksi.append({
                    "stock": stock,
                    "timeframes": tf_results,
                    "has_green_dot": any_green
                })
            except Exception as err_saham:
                print(f"⚠️ [AUTO-SKIP] Saham {sym} mengalami error: {err_saham}. Otomatis lanjut ke saham berikutnya...")
                # Jika halaman tertutup atau browser terputus, pulihkan halaman secara otomatis
                try:
                    if page.is_closed():
                        print("🔄 [SELF-HEALING] Membuka kembali halaman browser...")
                        page = await context.new_page()
                        await page.goto(f"{CHART_LAYOUT_URL}?symbol=IDX%3A{sym}&interval=D", wait_until="domcontentloaded", timeout=45000)
                except Exception as rec_err:
                    print(f"⚠️ Gagal memulihkan halaman: {rec_err}")
                continue
            
        # Kembalikan status indikator ke default di TradingView sebelum menutup browser
        try:
            await page.evaluate('''async () => {
                const chart = window._exposed_chartWidgetCollection?.activeChartWidget?.value();
                if (!chart) return;
                const allStudies = chart.model().panes().flatMap(p => p.dataSources());
                const smc = allStudies.find(s => s.title && s.title().includes('Ultimate SMC Suite'));
                const donalt = allStudies.find(s => s.title && s.title().includes('EMA + DonAlt Suite'));
                const rally = allStudies.find(s => s.title && s.title().includes('RallyGood'));
                const sc = allStudies.find(s => s.title && s.title().includes('Scalping vs Swing Trading'));
                const macd = allStudies.find(s => s.title && s.title().includes('MACD Divergences'));

                if (smc?.properties?.().visible) smc.properties().visible.setValue(false);
                if (sc?.properties?.().visible) sc.properties().visible.setValue(false);
                if (macd?.properties?.().visible) macd.properties().visible.setValue(false);
                await new Promise(r => setTimeout(r, 400));
                if (donalt?.properties?.().visible) donalt.properties().visible.setValue(true);
                if (rally?.properties?.().visible) rally.properties().visible.setValue(true);
                await new Promise(r => setTimeout(r, 600));
            }''')
        except Exception:
            pass
            
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
            # Tambahkan sinyal Golden Cross & Death Cross (EMA + DonAlt Suite)
            notepad_donalt_lines = format_donalt_notepad(tf)
            konten_laporan.extend(notepad_donalt_lines)
            # Tambahkan sinyal Scalping vs Swing Trading (BUY & SELL + Trend)
            notepad_scalping_lines = format_scalping_notepad(tf)
            konten_laporan.extend(notepad_scalping_lines)
            # Tambahkan sinyal SMC Supply & Demand (Daily & 1 Jam)
            notepad_smc_lines = format_smc_notepad(tf)
            konten_laporan.extend(notepad_smc_lines)
            # Tambahkan sinyal MACD Divergences (Bull & Bear)
            notepad_macd_lines = format_macd_notepad(tf)
            konten_laporan.extend(notepad_macd_lines)
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
            konten_laporan.append(f"{idx}. {st['symbol']} | Harga: Rp {st['close']:.0f}{gain_str} | Vol: {st['volume']:,.0f}")
            if tf.get('D', {}).get('status'):
                g_1d = f" (Kenaikan: {tf['D']['gain_pct']:+.2f}%)" if tf.get('D', {}).get('gain_pct') is not None else ""
                konten_laporan.append(f"   - Daily (1D)  : [ADA DOT GREEN] (Muncul: {tf['D']['date']}{g_1d})")
            if tf.get('60', {}).get('status'):
                g_1h = f" (Kenaikan: {tf['60']['gain_pct']:+.2f}%)" if tf.get('60', {}).get('gain_pct') is not None else ""
                konten_laporan.append(f"   - 1 Jam (1H)  : [ADA DOT GREEN] (Muncul: {tf['60']['date']}{g_1h})")
            if tf.get('15', {}).get('status'):
                konten_laporan.append(f"   - 15 Menit    : [ADA DOT GREEN] (Muncul: {tf['15']['date']})")
            notepad_donalt_lines = format_donalt_notepad(tf)
            konten_laporan.extend(notepad_donalt_lines)
            notepad_scalping_lines = format_scalping_notepad(tf)
            konten_laporan.extend(notepad_scalping_lines)
            notepad_smc_lines = format_smc_notepad(tf)
            konten_laporan.extend(notepad_smc_lines)
            notepad_macd_lines = format_macd_notepad(tf)
            konten_laporan.extend(notepad_macd_lines)
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
            
            donalt_tags = []
            for code, lbl in [("D", "1D"), ("60", "1H"), ("15", "15M")]:
                g = tf.get(code, {}).get("donalt", {}).get("golden")
                if g:
                    rev_s = " s/d Death" if g.get('reversed') else ""
                    gain_s = f" ({g['gain_pct']:+.2f}%{rev_s})" if g.get('gain_pct') is not None else ""
                    donalt_tags.append(f"Golden {lbl}: {g['date']}{gain_s}")
            donalt_note = f" | EMA: {', '.join(donalt_tags)}" if donalt_tags else ""
            
            scalp_tags = []
            for code, lbl in [("D", "1D"), ("60", "1H"), ("15", "15M")]:
                sc = tf.get(code, {}).get("scalping", {})
                b = sc.get("buy")
                s = sc.get("sell")
                if b:
                    rev_s = " s/d SELL" if b.get('reversed') else ""
                    gain_s = f" ({b['gain_pct']:+.2f}%{rev_s})" if b.get('gain_pct') is not None else ""
                    scalp_tags.append(f"BUY {lbl}: {b['date']}{gain_s}")
                if s:
                    scalp_tags.append(f"SELL {lbl}: {s['date']}")
            scalp_note = f" | Scalp: {', '.join(scalp_tags)}" if scalp_tags else ""

            smc_1d = tf.get('D', {}).get('smc')
            smc_1h = tf.get('60', {}).get('smc')
            smc_notes = []
            if smc_1d and smc_1d.get('supply') and smc_1d.get('demand'):
                smc_notes.append(f"1D Sup:{smc_1d['supply']:.0f}/Dem:{smc_1d['demand']:.0f}")
            if smc_1h and smc_1h.get('supply') and smc_1h.get('demand'):
                smc_notes.append(f"1H Sup:{smc_1h['supply']:.0f}/Dem:{smc_1h['demand']:.0f}")
            smc_note = f" | SMC: {', '.join(smc_notes)}" if smc_notes else ""

            macd_tags = []
            for code, lbl in [("D", "1D"), ("60", "1H"), ("15", "15M")]:
                m = tf.get(code, {}).get("macd", {})
                b = m.get("bull")
                br = m.get("bear")
                if b:
                    macd_tags.append(f"Bull {lbl}: {b['date']}")
                if br:
                    macd_tags.append(f"Bear {lbl}: {br['date']}")
            macd_note = f" | MACD: {', '.join(macd_tags)}" if macd_tags else ""
            konten_laporan.append(f"• {st['symbol']:<6} | Rp {st['close']:<4.0f} ({st['change']:+6.2f}%) | Dot di: {tf_str}{donalt_note}{scalp_note}{smc_note}{macd_note}")
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
        g_tfs = []
        for code, lbl in [("D", "1D"), ("60", "1H"), ("15", "15M")]:
            if item["timeframes"].get(code, {}).get("donalt", {}).get("golden"):
                g_tfs.append(lbl)
        golden_str = f" [Golden Cross: {', '.join(g_tfs)}]" if g_tfs else ""
        
        sc_tfs = []
        for code, lbl in [("D", "1D"), ("60", "1H"), ("15", "15M")]:
            sc = item["timeframes"].get(code, {}).get("scalping", {})
            if sc.get("buy"):
                sc_tfs.append(f"BUY {lbl}")
            if sc.get("sell"):
                sc_tfs.append(f"SELL {lbl}")
        scalp_str = f" [Scalp: {', '.join(sc_tfs)}]" if sc_tfs else ""

        m_tfs = []
        for code, lbl in [("D", "1D"), ("60", "1H"), ("15", "15M")]:
            m = item["timeframes"].get(code, {}).get("macd", {})
            if m.get("bull"):
                m_tfs.append(f"Bull {lbl}")
            if m.get("bear"):
                m_tfs.append(f"Bear {lbl}")
        macd_str = f" [MACD: {', '.join(m_tfs)}]" if m_tfs else ""
        konten_laporan.append(f"- {st['symbol']:<6} : Rp {st['close']:<4.0f} ({st['change']:+6.2f}%) -> {status_text}{golden_str}{scalp_str}{macd_str}")
        
    # Fitur simpan file TXT ke folder Downloads/reports & buka Notepad telah dihapus (hasil langsung dikirim ke WhatsApp)

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
                    donalt_line = format_donalt_wa(tf)
                    scalp_line = format_scalping_wa(tf)
                    smc_1d = tf.get('D', {}).get('smc')
                    smc_1h = tf.get('60', {}).get('smc')
                    smc_line = format_smc_wa(smc_1d, smc_1h)
                    macd_line = format_macd_wa(tf)
                    pesan_wa += (
                        f"{idx}. *{st['symbol']}* — Rp {st['close']:.0f}\n"
                        f"{gain_line}"
                        f"📊 Volume: {st['volume']:,.0f} lembar\n"
                        f"• Daily (1D)  : {tf['D']['date']}\n"
                        f"• 1 Jam (1H)  : {tf['60']['date']}\n"
                        f"• 15 Mnt (15M): {tf['15']['date']}\n"
                        f"{donalt_line}"
                        f"{scalp_line}"
                        f"{smc_line}"
                        f"{macd_line}"
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
                    donalt_line = format_donalt_wa(tf)
                    scalp_line = format_scalping_wa(tf)
                    smc_1d = tf.get('D', {}).get('smc')
                    smc_1h = tf.get('60', {}).get('smc')
                    smc_line = format_smc_wa(smc_1d, smc_1h)
                    macd_line = format_macd_wa(tf)
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
                    pesan_wa += f"{donalt_line}"
                    pesan_wa += f"{scalp_line}"
                    pesan_wa += f"{smc_line}"
                    pesan_wa += f"{macd_line}"
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
            f"🌐 _Bot Agent Okto 24 Jam Otomatis_"
        )
        kirim_whatsapp(pesan_wa)
    else:
        print("ℹ️ Mode Uji Coba: Pengiriman WhatsApp dilewati (hanya mencatat ke file Notepad).")
        
    # Pastikan seluruh sisa screenshot dibersihkan
    bersihkan_screenshot()

# ============================================================================
# MAIN LOOP SCHEDULER: JALAN SETIAP HARI PUKUL 16.30 WIB
# ============================================================================
def main():
    print("================================================================")
    print("🚀 BOT HUNTER + RALLY GOD (OKTOVAAAAA) DIAKTIFKAN")
    print(f"⏰ Jadwal Rutin: Setiap hari pukul {JAM_SCAN_WIB:02d}:{MENIT_SCAN_WIB:02d} WIB")
    print("================================================================")
    
    # Argumen --limit untuk membatasi jumlah saham saat pengujian (contoh: --limit 5 atau --limit 10)
    global LIMIT_SAHAM_SCAN
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            try:
                LIMIT_SAHAM_SCAN = int(sys.argv[i + 1])
                print(f"🎯 Batas scan disetel ke {LIMIT_SAHAM_SCAN} saham (--limit {LIMIT_SAHAM_SCAN}).")
            except ValueError:
                pass

    # Argumen --now untuk pengujian langsung
    if len(sys.argv) > 1 and "--now" in sys.argv:
        send_wa = "--wa" in sys.argv
        if send_wa:
            print("[TEST MODE] Menjalankan scan langsung saat ini & MENGIRIM NOTIFIKASI KE WHATSAPP...")
        else:
            print("[TEST MODE] Menjalankan scan langsung saat ini (tanpa kirim ke WhatsApp, tambahkan --wa untuk kirim ke WA)...")
        asyncio.run(run_daily_scan(send_wa=send_wa))
        return

    kirim_whatsapp(f"🤖 *BOT HUNTER RALLY GOD SIAP!*\nBot server standby dan akan otomatis melakukan scan setiap hari pukul {JAM_SCAN_WIB:02d}:{MENIT_SCAN_WIB:02d} WIB.")
    
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
