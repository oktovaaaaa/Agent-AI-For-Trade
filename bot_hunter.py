import os
import sys
import time
import datetime
import requests
import json
import asyncio
import gc
from pathlib import Path
import pandas as pd
import numpy as np
from PIL import Image
import pytz
from tradingview_screener import Query, Column
from playwright.async_api import async_playwright
try:
    import psutil
except ImportError:
    psutil = None

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
NOMOR_WHATSAPP_TUJUAN = os.environ.get("NOMOR_WHATSAPP_TUJUAN", "082111144710")

# Session Cookie TradingView (Mendukung multi-akun dipisah tanda koma)
# Default: 5 Akun TradingView (Akun 1 + Akun 2 + Akun 3 + Akun 4 + Akun 5)
TRADINGVIEW_SESSIONIDS_RAW = os.environ.get(
    "TRADINGVIEW_SESSIONID", 
    "999m9aq36s5hhqv7yw2vfubqvqhxbmj9,7ev2mzm8hgnx5zmu898kaa8g2nuzfc2i,yx4cryfynruplr29eryqu7qooc05mlex,kp2dfxh2grqbjsbjal140l3b9sgj9zl2,yblqlk1na0odzz71mu3y8il6igu229u1"
)
TRADINGVIEW_SESSIONIDS = [s.strip() for s in TRADINGVIEW_SESSIONIDS_RAW.split(",") if s.strip()]

# URL Layout Chart TradingView Anda tempat indikator (人•ᴗ•)RallyGood terpasang
CHART_LAYOUT_URL = "https://www.tradingview.com/chart/6B2fiCnc/"

# Jadwal & Parameter Analisis (Default: Pukul 16.21 WIB / 04:21 Sore pasca tutup bursa)
JAM_SCAN_WIB = int(os.environ.get("JAM_SCAN_WIB", 16))
MENIT_SCAN_WIB = int(os.environ.get("MENIT_SCAN_WIB", 21))
LOOKBACK_DAYS = 30              # Cek sinyal 1 bulan terakhir (30 hari)
LIMIT_SAHAM_SCAN = int(os.environ.get("LIMIT_SAHAM_SCAN", 0))           # 0 = Ambil seluruh saham lolos screener tanpa batas (bisa diatur misal 20, 50, atau 0 untuk semua)
DEFAULT_WORKERS = 5 if os.environ.get("GITHUB_ACTIONS") else 25
NUM_WORKERS = int(os.environ.get("NUM_WORKERS", DEFAULT_WORKERS))                    # Jumlah worker tab paralel (default 25 worker: 5 worker per akun)

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

class HardwareMonitor:
    """Pemantau konsumsi RAM dan Core CPU secara real-time saat scan berjalan."""
    def __init__(self):
        self.running = False
        self.peak_ram_bytes = 0
        self.cpu_samples = []
        if psutil:
            self.total_cores = psutil.cpu_count(logical=True) or 1
            self.physical_cores = psutil.cpu_count(logical=False) or self.total_cores
            self.total_ram_gb = psutil.virtual_memory().total / (1024**3)
            self.main_proc = psutil.Process(os.getpid())
        else:
            self.total_cores = os.cpu_count() or 1
            self.physical_cores = self.total_cores
            self.total_ram_gb = 0
            self.main_proc = None

    async def run(self):
        if not psutil:
            return
        self.running = True
        while self.running:
            try:
                # Kumpulkan RAM dari Python + SEMUA child process Chromium browser
                procs = [self.main_proc] + self.main_proc.children(recursive=True)
                total_mem = 0
                for p in procs:
                    try:
                        total_mem += p.memory_info().rss
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                if total_mem > self.peak_ram_bytes:
                    self.peak_ram_bytes = total_mem
                self.cpu_samples.append(psutil.cpu_percent(interval=None))
            except Exception:
                pass
            await asyncio.sleep(0.5)

    def stop(self):
        self.running = False
        if not psutil:
            return None
        peak_mb = self.peak_ram_bytes / (1024 * 1024)
        peak_gb = self.peak_ram_bytes / (1024 ** 3)
        avg_cpu = sum(self.cpu_samples) / len(self.cpu_samples) if self.cpu_samples else 0.0
        peak_cpu = max(self.cpu_samples) if self.cpu_samples else 0.0
        tot_ram = psutil.virtual_memory().total
        pct_of_ram = (self.peak_ram_bytes / tot_ram) * 100 if tot_ram else 0.0
        return {
            "peak_mb": peak_mb,
            "peak_gb": peak_gb,
            "pct_ram": pct_of_ram,
            "avg_cpu": avg_cpu,
            "peak_cpu": peak_cpu,
            "total_cores": self.total_cores,
            "physical_cores": self.physical_cores,
            "total_ram_gb": self.total_ram_gb
        }

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
    
    # Jaminan selalu ada level harga Resisten (Supply) dan Support (Demand) dari candle bar
    if not nearest_supply and bars:
        highs = [b['high'] for b in bars if b.get('high') and b['high'] > cur_close]
        nearest_supply = min(highs) if highs else max(b['high'] for b in bars if b.get('high'))
    if not nearest_demand and bars:
        lows = [b['low'] for b in bars if b.get('low') and b['low'] < cur_close]
        nearest_demand = max(lows) if lows else min(b['low'] for b in bars if b.get('low'))
        
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
            
        # Jika salah satu supply atau demand kosong dari TV, lengkapi dari candlestick bar
        if (not nearest_supply or not nearest_demand) and recent_bars:
            fb = calculate_smc_levels_fallback(recent_bars, cur_close)
            if fb:
                if not nearest_supply and fb.get('supply'):
                    nearest_supply = fb['supply']
                if not nearest_demand and fb.get('demand'):
                    nearest_demand = fb['demand']
            
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
# SISTEM ANTI-SPAM & ALERT INSTAN INTRADAY
# ============================================================================
ALERTED_SIGNALS_FILE = Path("docs/data/alerted_signals.json")

# Cache status pasar bursa hari ini berdasarkan detak jantung BBCA
_CACHED_BBCA_MARKET_STATUS = {}

def check_bbca_market_status(now_wib=None):
    """
    Memeriksa status operasional bursa IDX hari ini melalui saham patokan BBCA di TradingView:
    - Akhir pekan (Sabtu & Minggu): Otomatis TUTUP (WEEKEND).
    - Hari kerja (Senin - Jumat): Cek tanggal candle terakhir BBCA via TradingView Screener API.
      * Jika tanggal candle == hari ini: BUKA (TRADING_DAY).
      * Jika tanggal candle < hari ini: TUTUP (HOLIDAY / LIBUR NASIONAL).
    """
    global _CACHED_BBCA_MARKET_STATUS
    if now_wib is None:
        now_wib = datetime.datetime.now(WIB_TZ)
        
    today_dt = now_wib.date()
    cache_key = today_dt.strftime("%Y-%m-%d")
    
    # Gunakan cache jika sudah dicek hari ini
    if cache_key in _CACHED_BBCA_MARKET_STATUS and _CACHED_BBCA_MARKET_STATUS[cache_key].get("session") == "TRADING_DAY":
        return _CACHED_BBCA_MARKET_STATUS[cache_key]

    # 1. Akhir pekan (Sabtu & Minggu)
    if now_wib.weekday() in [5, 6]:
        res = {
            "is_open": False,
            "session": "WEEKEND",
            "reason": "Bursa Tutup (Akhir Pekan / Weekend)",
            "trading_date": today_dt - datetime.timedelta(days=1 if now_wib.weekday() == 5 else 2)
        }
        _CACHED_BBCA_MARKET_STATUS[cache_key] = res
        return res

    # 2. Hari kerja sebelum jam 09:00 WIB
    if now_wib.time() < datetime.time(8, 59):
        prev_trading = today_dt - datetime.timedelta(days=3 if now_wib.weekday() == 0 else 1)
        return {
            "is_open": False,
            "session": "PRE_MARKET",
            "reason": "Sebelum Jam Pembukaan Bursa (< 09:00 WIB)",
            "trading_date": prev_trading
        }

    # 3. Jam bursa aktif: Periksa candle terbaru BBCA
    try:
        q = Query().set_markets('indonesia').select('name', 'close', 'volume', 'time').where(Column('name') == 'BBCA')
        df = q.get_scanner_data()[1]
        if not df.empty:
            row = df.iloc[0]
            ts = row.get('time')
            if ts and not pd.isna(ts):
                candle_dt = datetime.datetime.fromtimestamp(int(ts), WIB_TZ).date()
                
                # Toleransi pembukaan tepat jam 09:00: Jika candle masih kemarin dan waktu < 09:02, tunggu sebentar untuk feed
                if candle_dt < today_dt and now_wib.time() < datetime.time(9, 2):
                    print("⏳ [09:00 WIB] Menunggu 20 detik untuk sinkronisasi feed pembukaan BBCA...")
                    time.sleep(20)
                    now_wib = datetime.datetime.now(WIB_TZ)
                    q = Query().set_markets('indonesia').select('name', 'close', 'volume', 'time').where(Column('name') == 'BBCA')
                    df = q.get_scanner_data()[1]
                    if not df.empty:
                        row = df.iloc[0]
                        ts = row.get('time')
                        if ts and not pd.isna(ts):
                            candle_dt = datetime.datetime.fromtimestamp(int(ts), WIB_TZ).date()

                if candle_dt == today_dt:
                    res = {
                        "is_open": True,
                        "session": "TRADING_DAY",
                        "reason": f"Bursa Buka (Candle BBCA aktif hari ini: {candle_dt})",
                        "trading_date": candle_dt
                    }
                    _CACHED_BBCA_MARKET_STATUS[cache_key] = res
                    return res
                else:
                    res = {
                        "is_open": False,
                        "session": "HOLIDAY",
                        "reason": f"Bursa Libur / Tidak Ada Perdagangan Hari Ini (Candle BBCA terakhir tertanggal {candle_dt})",
                        "trading_date": candle_dt
                    }
                    _CACHED_BBCA_MARKET_STATUS[cache_key] = res
                    return res
    except Exception as e:
        print(f"⚠️ [WARNING] Gagal memeriksa status BBCA via screener: {e}")

    # Fallback jika terjadi error koneksi ke scanner
    return {
        "is_open": True,
        "session": "TRADING_DAY",
        "reason": "Fallback (Gagal koneksi screener BBCA)",
        "trading_date": today_dt
    }

def get_latest_trading_date(now_wib):
    """
    Mengembalikan tanggal sesi bursa IDX terbaru:
    - Menggunakan tanggal candle bursa terbaru dari saham patokan BBCA.
    - Menghindari pembuatan tanggal baru pada hari libur nasional atau akhir pekan.
    """
    bbca_info = check_bbca_market_status(now_wib)
    if bbca_info and bbca_info.get("trading_date"):
        return bbca_info["trading_date"]

    dt = now_wib.date()
    if now_wib.weekday() == 5:
        return dt - datetime.timedelta(days=1)
    elif now_wib.weekday() == 6:
        return dt - datetime.timedelta(days=2)
    elif now_wib.time() < datetime.time(9, 0):
        if now_wib.weekday() == 0:
            return dt - datetime.timedelta(days=3)
        else:
            return dt - datetime.timedelta(days=1)
    else:
        return dt

def load_alerted_keys(now_wib):
    """Memuat daftar kunci sinyal yang sudah pernah dikirimkan hari ini untuk mencegah spam."""
    trading_date = get_latest_trading_date(now_wib)
    today_str = trading_date.strftime("%Y-%m-%d")
    target_file = ALERTED_SIGNALS_FILE
    if not target_file.exists():
        fallback = REPORTS_DIR / "alerted_signals_today.json"
        if fallback.exists():
            target_file = fallback

    if target_file.exists():
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("date") == today_str:
                    return set(data.get("alerted_keys", []))
                else:
                    print(f"🔄 Sesi bursa baru ({today_str}). Mengosongkan riwayat alert anti-spam.")
                    return set()
        except Exception as e:
            print(f"⚠️ Gagal membaca riwayat alert anti-spam {target_file}: {e}")
            return set()
    return set()

def save_alerted_keys(alerted_keys, now_wib):
    """Menyimpan daftar sinyal yang telah dikirim hari ini ke disk."""
    trading_date = get_latest_trading_date(now_wib)
    today_str = trading_date.strftime("%Y-%m-%d")
    data = {
        "date": today_str,
        "updated_at": now_wib.strftime("%Y-%m-%d %H:%M:%S WIB"),
        "total_alerts": len(alerted_keys),
        "alerted_keys": sorted(list(alerted_keys))
    }
    for p in [ALERTED_SIGNALS_FILE, REPORTS_DIR / "alerted_signals_today.json"]:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"⚠️ Gagal menyimpan riwayat alert ke {p}: {e}")

def check_and_send_instant_alert(stock, tf_results, alerted_keys, now_wib, save_to_disk=True):
    """
    Mengecek apakah saham ini memiliki sinyal BARU HARI INI:
    - Dot Green (15M, 1H, 1D)
    - Scalp BUY (15M, 1H, 1D)
    - Golden Cross EMA (15M, 1H, 1D)
    - MACD Bullish Divergence (15M, 1H, 1D)
    
    Jika ada sinyal hari ini yang belum pernah dikirim (belum ada di alerted_keys),
    seketika kirim pesan WhatsApp khusus emiten ini dan catat ke alerted_keys.
    """
    sym = stock.get("symbol")
    today_date = get_latest_trading_date(now_wib)
    
    new_signals_text = []
    new_keys = []
    
    # 1. Cek Dot Green
    for tf_code, tf_label in [("15", "15M"), ("60", "1H"), ("D", "Daily")]:
        tf_data = tf_results.get(tf_code, {})
        if tf_data.get("status"):
            dt = tf_data.get("dt")
            if dt and dt.date() == today_date:
                t_str = dt.strftime("%H:%M") if tf_code != "D" else "Hari Ini"
                key = f"{sym}|DOT_GREEN|{tf_code}|{dt.strftime('%Y-%m-%d %H:%M') if tf_code != 'D' else dt.strftime('%Y-%m-%d')}"
                if key not in alerted_keys:
                    new_signals_text.append(f"• 🟢 *Dot Green {tf_label}* (Pukul {t_str} WIB)")
                    new_keys.append(key)
                    
    # 2. Cek Scalp BUY (Hanya jika belum dibalas oleh sinyal SELL setelahnya)
    for tf_code, tf_label in [("15", "15M"), ("60", "1H"), ("D", "Daily")]:
        sc = tf_results.get(tf_code, {}).get("scalping", {})
        buy = sc.get("buy")
        if buy and not buy.get("reversed"):
            b_dt = buy.get("dt")
            if b_dt and b_dt.date() == today_date:
                t_str = b_dt.strftime("%H:%M") if tf_code != "D" else "Hari Ini"
                key = f"{sym}|SCALP_BUY|{tf_code}|{b_dt.strftime('%Y-%m-%d %H:%M') if tf_code != 'D' else b_dt.strftime('%Y-%m-%d')}"
                if key not in alerted_keys:
                    new_signals_text.append(f"• ⚔️ *Scalp BUY {tf_label}* (Pukul {t_str} WIB)")
                    new_keys.append(key)

    # 3. Cek Golden Cross (Hanya jika belum dibalas oleh Death Cross setelahnya)
    for tf_code, tf_label in [("15", "15M"), ("60", "1H"), ("D", "Daily")]:
        donalt = tf_results.get(tf_code, {}).get("donalt", {})
        g = donalt.get("golden")
        if g and not g.get("reversed"):
            g_dt = g.get("dt")
            if g_dt and g_dt.date() == today_date:
                t_str = g_dt.strftime("%H:%M") if tf_code != "D" else "Hari Ini"
                key = f"{sym}|GOLDEN_CROSS|{tf_code}|{g_dt.strftime('%Y-%m-%d %H:%M') if tf_code != 'D' else g_dt.strftime('%Y-%m-%d')}"
                if key not in alerted_keys:
                    new_signals_text.append(f"• ✨ *Golden Cross {tf_label}* (Pukul {t_str} WIB)")
                    new_keys.append(key)

    # 4. Cek MACD Bull (Hanya jika belum dibalas oleh Bearish Divergence setelahnya)
    for tf_code, tf_label in [("15", "15M"), ("60", "1H"), ("D", "Daily")]:
        m = tf_results.get(tf_code, {}).get("macd", {})
        bull = m.get("bull")
        if bull and not bull.get("reversed"):
            m_dt = bull.get("dt")
            if m_dt and m_dt.date() == today_date:
                t_str = m_dt.strftime("%H:%M") if tf_code != "D" else "Hari Ini"
                key = f"{sym}|MACD_BULL|{tf_code}|{m_dt.strftime('%Y-%m-%d %H:%M') if tf_code != 'D' else m_dt.strftime('%Y-%m-%d')}"
                if key not in alerted_keys:
                    new_signals_text.append(f"• 🐂 *MACD Bullish Div {tf_label}* (Pukul {t_str} WIB)")
                    new_keys.append(key)

    if not new_signals_text:
        return False
        
    # Ambil info Support & Resisten SMC (cari dari 1H, 15M, atau 1D yang punya nilai)
    smc = tf_results.get("60", {}).get("smc") or tf_results.get("15", {}).get("smc") or tf_results.get("D", {}).get("smc") or {}
    sup_val = smc.get("demand")
    res_val = smc.get("supply")
    status_7d = smc.get("status_7d") or "⚪ Di Antara Demand & Supply"
    
    sup_str = f"Rp {sup_val:.0f}" if sup_val else "-"
    res_str = f"Rp {res_val:.0f}" if res_val else "-"
    
    cur_price = stock.get("close", 0)
    chg_pct = stock.get("change", 0.0)
    
    pesan_alert = (
        f"🟢 *SINYAL ENTRY / BULLISH (INTRADAY)*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Emiten   : *{sym}*\n"
        f"Harga    : Rp {cur_price:.0f} ({chg_pct:+.2f}%)\n"
        f"Sinyal   :\n"
        + "\n".join(new_signals_text) + "\n"
        f"SMC Area :\n"
        f"• Support (Demand)  : {sup_str}\n"
        f"• Resisten (Supply) : {res_str}\n"
        f"• Status            : {status_7d}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"> _Sent via Aranter_"
    )
    
    print(f"\n🟢 [BULLISH ALERT] Sinyal baru (Entry/Bullish) terdeteksi untuk {sym} ({len(new_keys)} sinyal). Mengirim WhatsApp...")
    sent = kirim_whatsapp(pesan_alert)
    if sent:
        for k in new_keys:
            alerted_keys.add(k)
        if save_to_disk:
            save_alerted_keys(alerted_keys, now_wib)
    return sent

def check_and_send_bearish_alert(stock, tf_results, alerted_keys, now_wib, save_to_disk=True):
    """
    Mengecek apakah saham ini memiliki sinyal BEARISH / EXIT BARU HARI INI:
    - Dot Red RallyGood (15M, 1H, 1D)
    - Death Cross EMA + DonAlt Suite (15M, 1H, 1D)
    
    Jika ada sinyal hari ini yang belum pernah dikirim (belum ada di alerted_keys),
    seketika kirim pesan WhatsApp khusus emiten ini dan catat ke alerted_keys.
    """
    sym = stock.get("symbol")
    today_date = get_latest_trading_date(now_wib)
    
    new_signals_text = []
    new_keys = []
    
    # 1. Cek Dot Red (RallyGood)
    for tf_code, tf_label in [("15", "15M"), ("60", "1H"), ("D", "Daily")]:
        tf_data = tf_results.get(tf_code, {})
        red_info = tf_data.get("red_dot", {})
        if red_info.get("status") and red_info.get("active"):
            dt = red_info.get("dt")
            if dt and dt.date() == today_date:
                t_str = dt.strftime("%H:%M") if tf_code != "D" else "Hari Ini"
                key = f"{sym}|DOT_RED|{tf_code}|{dt.strftime('%Y-%m-%d %H:%M') if tf_code != 'D' else dt.strftime('%Y-%m-%d')}"
                if key not in alerted_keys:
                    new_signals_text.append(f"• 🔴 *Dot Red {tf_label}* (Pukul {t_str} WIB)")
                    new_keys.append(key)
                    
    # 2. Cek Death Cross (EMA + DonAlt Suite - Hanya jika belum dibalas Golden Cross setelahnya)
    for tf_code, tf_label in [("15", "15M"), ("60", "1H"), ("D", "Daily")]:
        donalt = tf_results.get(tf_code, {}).get("donalt", {})
        death = donalt.get("death")
        if death and not death.get("reversed"):
            d_dt = death.get("dt")
            if d_dt and d_dt.date() == today_date:
                t_str = d_dt.strftime("%H:%M") if tf_code != "D" else "Hari Ini"
                key = f"{sym}|DEATH_CROSS|{tf_code}|{d_dt.strftime('%Y-%m-%d %H:%M') if tf_code != 'D' else d_dt.strftime('%Y-%m-%d')}"
                if key not in alerted_keys:
                    new_signals_text.append(f"• 💀 *Death Cross {tf_label}* (Pukul {t_str} WIB)")
                    new_keys.append(key)

    # 3. Cek Scalp SELL (Scalping vs Swing Trading - Hanya jika belum dibalas BUY setelahnya)
    for tf_code, tf_label in [("15", "15M"), ("60", "1H"), ("D", "Daily")]:
        sc = tf_results.get(tf_code, {}).get("scalping", {})
        sell = sc.get("sell")
        if sell and not sell.get("reversed"):
            s_dt = sell.get("dt")
            if s_dt and s_dt.date() == today_date:
                t_str = s_dt.strftime("%H:%M") if tf_code != "D" else "Hari Ini"
                key = f"{sym}|SCALP_SELL|{tf_code}|{s_dt.strftime('%Y-%m-%d %H:%M') if tf_code != 'D' else s_dt.strftime('%Y-%m-%d')}"
                if key not in alerted_keys:
                    new_signals_text.append(f"• 🔴 *Scalp SELL {tf_label}* (Pukul {t_str} WIB)")
                    new_keys.append(key)

    # 4. Cek MACD Bearish Divergence (Hanya jika belum dibalas Bullish Divergence setelahnya)
    for tf_code, tf_label in [("15", "15M"), ("60", "1H"), ("D", "Daily")]:
        m = tf_results.get(tf_code, {}).get("macd", {})
        bear = m.get("bear")
        if bear and not bear.get("reversed"):
            br_dt = bear.get("dt")
            if br_dt and br_dt.date() == today_date:
                t_str = br_dt.strftime("%H:%M") if tf_code != "D" else "Hari Ini"
                key = f"{sym}|MACD_BEAR|{tf_code}|{br_dt.strftime('%Y-%m-%d %H:%M') if tf_code != 'D' else br_dt.strftime('%Y-%m-%d')}"
                if key not in alerted_keys:
                    new_signals_text.append(f"• 🐻 *MACD Bearish Div {tf_label}* (Pukul {t_str} WIB)")
                    new_keys.append(key)

    if not new_signals_text:
        return False
        
    # Ambil info Support & Resisten SMC (cari dari 1H, 15M, atau 1D yang punya nilai)
    smc = tf_results.get("60", {}).get("smc") or tf_results.get("15", {}).get("smc") or tf_results.get("D", {}).get("smc") or {}
    sup_val = smc.get("demand")
    res_val = smc.get("supply")
    status_7d = smc.get("status_7d") or "⚪ Di Antara Demand & Supply"
    
    sup_str = f"Rp {sup_val:.0f}" if sup_val else "-"
    res_str = f"Rp {res_val:.0f}" if res_val else "-"
    
    cur_price = stock.get("close", 0)
    chg_pct = stock.get("change", 0.0)
    
    pesan_alert = (
        f"⚠️ *PERINGATAN EXIT / BEARISH (INTRADAY)*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Emiten   : *{sym}*\n"
        f"Harga    : Rp {cur_price:.0f} ({chg_pct:+.2f}%)\n"
        f"Sinyal   :\n"
        + "\n".join(new_signals_text) + "\n"
        f"SMC Area :\n"
        f"• Support (Demand)  : {sup_str}\n"
        f"• Resisten (Supply) : {res_str}\n"
        f"• Status            : {status_7d}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"> _Sent via Aranter_"
    )
    
    print(f"\n⚠️ [BEARISH ALERT] Sinyal exit/bearish terdeteksi untuk {sym} ({len(new_keys)} sinyal). Mengirim WhatsApp...")
    sent = kirim_whatsapp(pesan_alert)
    if sent:
        for k in new_keys:
            alerted_keys.add(k)
        if save_to_disk:
            save_alerted_keys(alerted_keys, now_wib)
    return sent

def kirim_pesan_summary_wa(hasil_deteksi, now_wib, sesi_label=None):
    """Mengirim pesan rangkuman WhatsApp (Daftar saham 3-Dot & 2-Dot Green + link web resmi)."""
    tgl_analisa_id = format_tanggal_id(now_wib)

    for item in hasil_deteksi:
        tf = item.get("timeframes", {})
        item["count_green"] = sum(1 for tf_key in ['D', '60', '15'] if tf.get(tf_key, {}).get('status'))

    saham_3_dot = [item for item in hasil_deteksi if item.get("count_green", 0) == 3]
    saham_2_dot = [item for item in hasil_deteksi if item.get("count_green", 0) == 2]

    saham_3_dot.sort(key=lambda x: x.get('stock', {}).get('volume', 0), reverse=True)
    saham_2_dot.sort(key=lambda x: x.get('stock', {}).get('volume', 0), reverse=True)

    header_sesi = f" ({sesi_label})" if sesi_label else ""
    pesan_wa = (
        f"📊 *Aranter — Hunter Screener*{header_sesi}\n"
        f"📅 *{tgl_analisa_id}* • ⏰ *{now_wib.strftime('%H:%M WIB')}*\n"
        f"🎯 *Filter*: Rp 10–1.000 | Vol > 10D | Pre-mkt > 500%\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    # Bagian 1: 3-Dot Green (VVIP)
    pesan_wa += "🔥 *DOT GREEN 3 TIMEFRAME (VVIP)*:\n"
    if saham_3_dot:
        for idx, item in enumerate(saham_3_dot, 1):
            pesan_wa += f"{idx}. {item['stock']['symbol']}\n"
    else:
        pesan_wa += "- (Tidak ada saham 3-Dot)\n"

    # Bagian 2: 2-Dot Green (Potensial)
    pesan_wa += "\n⚡ *DOT GREEN 2 TIMEFRAME (POTENSIAL)*:\n"
    if saham_2_dot:
        for idx, item in enumerate(saham_2_dot, 1):
            pesan_wa += f"{idx}. {item['stock']['symbol']}\n"
    else:
        pesan_wa += "- (Tidak ada saham 2-Dot)\n"

    # Penutup Rekomendasi Website & Tips
    pesan_wa += (
        f"\n━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 *REKOMENDASI ANALISIS LENGKAP:*\n"
        f"Untuk keputusan entry yang lebih akurat, sangat direkomendasikan melihat detail teknikal setiap saham langsung di website resmi:\n"
        f"👉 https://aranter.web.id/\n\n"
        f"Di website Anda dapat memeriksa:\n"
        f"• Waktu kemunculan Dot Green (Daily, 1H, 15M) & persen kenaikannya\n"
        f"• Zona Demand & Supply SMC (area pantul & batas risiko entry)\n"
        f"• Sinyal Scalping BUY/SELL, Golden Cross EMA & MACD Divergence\n"
        f"• Pantauan riwayat 30 hari bursa saham 3-Dot Green\n\n"
        f"💡 *Tips Hunter:* Utamakan saham dengan volume spike di atas rata-rata 10 hari & selalu perhatikan area demand SMC sebelum entry.\n\n"
        f"🤖 _Dashboard Aranter for Trade by Oktovaaaaa_"
    )
    return kirim_whatsapp(pesan_wa)

def get_current_idx_session(now_wib):
    """
    Menentukan status dan sesi bursa IDX saat ini:
    Senin - Kamis:
      Sesi 1   : 09:00 - 12:00 WIB
      Istirahat: 12:00 - 13:30 WIB
      Sesi 2   : 13:30 - 15:50 WIB
    Jumat:
      Sesi 1   : 09:00 - 11:30 WIB
      Istirahat: 11:30 - 14:00 WIB
      Sesi 2   : 14:00 - 15:50 WIB
    Sabtu & Minggu: Tutup
    """
    weekday = now_wib.weekday()  # 0=Senin, ..., 4=Jumat, 5=Sabtu, 6=Minggu
    cur_time = now_wib.time()
    
    # Akhir pekan (Sabtu & Minggu)
    if weekday in [5, 6]:
        return {
            "status": "CLOSED",
            "session": "WEEKEND",
            "name": "Bursa Tutup (Akhir Pekan / Weekend)"
        }

    # Cek apakah hari kerja ini merupakan Hari Libur Nasional / Cuti Bersama via detak jantung BBCA
    if cur_time >= datetime.time(9, 0):
        bbca_info = check_bbca_market_status(now_wib)
        if not bbca_info.get("is_open") and bbca_info.get("session") == "HOLIDAY":
            return {
                "status": "CLOSED",
                "session": "HOLIDAY",
                "name": bbca_info.get("reason", "Bursa Tutup (Hari Libur Nasional)")
            }
        
    t_0900 = datetime.time(9, 0)
    t_1550 = datetime.time(15, 50)
    
    # Hari Jumat
    if weekday == 4:
        t_1130 = datetime.time(11, 30)
        t_1400 = datetime.time(14, 0)
        
        if t_0900 <= cur_time < t_1130:
            return {
                "status": "OPEN",
                "session": "SESI_1",
                "name": "Sesi I Jumat (09:00 - 11:30 WIB)",
                "end_time": t_1130
            }
        elif t_1130 <= cur_time < t_1400:
            return {
                "status": "BREAK",
                "session": "ISTIRAHAT",
                "name": "Istirahat Sholat Jumat (11:30 - 14:00 WIB)",
                "resume_time": t_1400
            }
        elif t_1400 <= cur_time < t_1550:
            return {
                "status": "OPEN",
                "session": "SESI_2",
                "name": "Sesi II Jumat (14:00 - 15:50 WIB)",
                "end_time": t_1550
            }
        else:
            return {
                "status": "CLOSED",
                "session": "AFTER_HOURS",
                "name": "Di Luar Jam Bursa Jumat"
            }
            
    # Senin - Kamis
    else:
        t_1200 = datetime.time(12, 0)
        t_1330 = datetime.time(13, 30)
        
        if t_0900 <= cur_time < t_1200:
            return {
                "status": "OPEN",
                "session": "SESI_1",
                "name": "Sesi I (09:00 - 12:00 WIB)",
                "end_time": t_1200
            }
        elif t_1200 <= cur_time < t_1330:
            return {
                "status": "BREAK",
                "session": "ISTIRAHAT",
                "name": "Istirahat Siang (12:00 - 13:30 WIB)",
                "resume_time": t_1330
            }
        elif t_1330 <= cur_time < t_1550:
            return {
                "status": "OPEN",
                "session": "SESI_2",
                "name": "Sesi II (13:30 - 15:50 WIB)",
                "end_time": t_1550
            }
        else:
            return {
                "status": "CLOSED",
                "session": "AFTER_HOURS",
                "name": "Di Luar Jam Bursa (Senin - Kamis)"
            }

# ============================================================================
# TAHAP 1: SCREENER HUNTER (SAHAM ID Rp 10-1000 & VOLUME > AVG 10D)
# ============================================================================
def get_hunter_stocks():
    """Mengambil saham IDX dari TradingView Screener sesuai kriteria HUNTER."""
    print(f"\n[{datetime.datetime.now(WIB_TZ).strftime('%Y-%m-%d %H:%M:%S WIB')}] 🔎 Memulai Screener HUNTER Saham IDX...")
    try:
        q = (Query()
             .set_markets('indonesia')
             .select('name', 'close', 'high', 'low', 'volume', 'average_volume_10d_calc', 'change')
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
            c_val = float(row['close'])
            h_raw = float(row.get('high', c_val))
            l_raw = float(row.get('low', c_val))
            tickers.append({
                'symbol': symbol,
                'tv_symbol': f"IDX:{symbol}",
                'close': c_val,
                'high': max(h_raw, c_val),
                'low': min(l_raw, c_val),
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
                'high': 83.0,
                'low': 78.0,
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
async def scan_stock_rallygood(page, stock_info, worker_id=None):
    """
    Membuka chart TradingView untuk saham tertentu secara instan (setSymbol & setResolution),
    mendeteksi Dot Green, dan mengekstrak tanggal & jam persis kemunculannya langsung dari TradingView.
    """
    symbol = stock_info['symbol']
    results = {}
    now_dt = datetime.datetime.now(WIB_TZ)
    w_tag = f"[Worker {worker_id}] " if worker_id is not None else ""
    
    # 1. Ganti simbol saham secara instan di chart TradingView
    try:
        await page.evaluate('(s) => window._exposed_chartWidgetCollection?.activeChartWidget?.value()?.setSymbol(s)', f"IDX:{symbol}")
        await asyncio.sleep(0.8)
    except Exception:
        try:
            chart_url = f"{CHART_LAYOUT_URL}?symbol=IDX%3A{symbol}&interval=D"
            await page.goto(chart_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2.5)
        except Exception as e:
            print(f" {w_tag}⚠️ Kendala navigasi chart {symbol}: {e}")
            return results
    
    # 2. Cek setiap timeframe (D, 60, 15)
    for tf in TIMEFRAMES:
        tf_code = tf['code']
        tf_name = tf['name']
        
        try:
            # Ganti resolusi / timeframe secara instan tanpa reload penuh
            await page.evaluate('(r) => window._exposed_chartWidgetCollection?.activeChartWidget?.value()?.setResolution(r)', tf['interval'])
            await asyncio.sleep(0.7)
            
            # Pastikan model chart dan indikator RallyGood siap sebelum ekstraksi
            for _ in range(15):
                ready_check = await page.evaluate('''() => {
                    try {
                        const chart = window._exposed_chartWidgetCollection?.activeChartWidget?.value();
                        if (!chart || !chart.model) return false;
                        const allStudies = chart.model().panes().flatMap(p => p.dataSources());
                        return allStudies.some(s => s.title && s.title().includes('RallyGood'));
                    } catch(e) { return false; }
                }''')
                if ready_check:
                    break
                await asyncio.sleep(0.3)
            
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
                    if (needWait) await new Promise(r => setTimeout(r, 150));

                    if (donaltStudy?.properties?.().visible && !donaltStudy.properties().visible.value()) {
                        donaltStudy.properties().visible.setValue(true);
                    }
                    if (rallyStudy?.properties?.().visible && !rallyStudy.properties().visible.value()) {
                        rallyStudy.properties().visible.setValue(true);
                    }
                    await new Promise(r => setTimeout(r, 200));

                    // FASE 1: Ekstraksi RallyGood (Dot Green & Dot Red) & EMA + DonAlt Suite (Golden/Death Cross)
                    // Tunggu hingga RallyGood paneViews terisi (polling hingga 1250ms untuk kestabilan di runner headless)
                    if (rallyStudy) {
                        for (let r = 0; r < 25; r++) {
                            const greenPv = (rallyStudy._paneViews || []).find(pv => pv._plotName === 'plot_2');
                            const redPv = (rallyStudy._paneViews || []).find(pv => pv._plotName === 'plot_1');
                            if ((greenPv && greenPv._items && greenPv._items.length > 0) || (redPv && redPv._items && redPv._items.length > 0)) break;
                            await new Promise(resolve => setTimeout(resolve, 50));
                        }
                    }

                    const parseBarOrTpTime = (idx, rawTp) => {
                        let barTime = null;
                        if (barsObj && barsObj.valueAt) {
                            const bar = barsObj.valueAt(idx);
                            if (bar && bar.length > 0 && typeof bar[0] === 'number') {
                                barTime = bar[0];
                            }
                        }
                        if (barTime !== null) return barTime;
                        if (typeof rawTp === 'number') return rawTp;
                        if (rawTp && typeof rawTp === 'object') {
                            if (typeof rawTp.time === 'number') return rawTp.time;
                            if (rawTp.year && rawTp.month && rawTp.day) {
                                return Math.floor(Date.UTC(rawTp.year, rawTp.month - 1, rawTp.day, 0, 0, 0) / 1000);
                            }
                        }
                        return null;
                    };

                    let dots = [];
                    let redDots = [];
                    if (rallyStudy) {
                        const greenPv = (rallyStudy._paneViews || []).find(pv => pv._plotName === 'plot_2');
                        if (greenPv) {
                            const activeDots = (greenPv._items || []).filter(it => !isNaN(it.y));
                            dots = activeDots.map(dot => {
                                const tp = ts.indexToTimePoint(dot.timePointIndex);
                                const itemTime = parseBarOrTpTime(dot.timePointIndex, tp);
                                let dotClose = null;
                                if (barsObj && barsObj.valueAt) {
                                    const bar = barsObj.valueAt(dot.timePointIndex);
                                    if (bar && bar.length > 4) dotClose = bar[4];
                                }
                                return {
                                    timestamp: itemTime,
                                    dotClose: dotClose,
                                    currentClose: currentClose
                                };
                            }).filter(d => d.timestamp !== null && d.timestamp !== undefined);
                        }

                        const redPv = (rallyStudy._paneViews || []).find(pv => pv._plotName === 'plot_1');
                        if (redPv) {
                            const activeReds = (redPv._items || []).filter(it => !isNaN(it.y));
                            redDots = activeReds.map(dot => {
                                const tp = ts.indexToTimePoint(dot.timePointIndex);
                                const itemTime = parseBarOrTpTime(dot.timePointIndex, tp);
                                let dotClose = null;
                                if (barsObj && barsObj.valueAt) {
                                    const bar = barsObj.valueAt(dot.timePointIndex);
                                    if (bar && bar.length > 4) dotClose = bar[4];
                                }
                                return {
                                    timestamp: itemTime,
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
                    await new Promise(r => setTimeout(r, 150));
                    if (smcStudy?.properties?.().visible) smcStudy.properties().visible.setValue(true);
                    for (let r = 0; r < 12; r++) {
                        const prims = smcStudy?._graphics?._primitivesCollection;
                        const boxesInner = prims?.dwgboxes?.get('boxes');
                        if (boxesInner && boxesInner.get(false)?._primitivesDataById) break;
                        await new Promise(resolve => setTimeout(resolve, 50));
                    }

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
                    await new Promise(r => setTimeout(r, 150));
                    if (scStudy?.properties?.().visible) scStudy.properties().visible.setValue(true);
                    
                    // Beri waktu TradingView mengkalkulasi data Scalping vs Swing Trading (polling hingga 600ms)
                    for (let r = 0; r < 12; r++) {
                        await new Promise(resolve => setTimeout(resolve, 50));
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
                    await new Promise(r => setTimeout(r, 150));
                    if (macdStudy?.properties?.().visible) macdStudy.properties().visible.setValue(true);
                    
                    // Beri waktu TradingView mengkalkulasi data MACD (polling hingga 600ms)
                    for (let r = 0; r < 12; r++) {
                        await new Promise(resolve => setTimeout(resolve, 50));
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
                    await new Promise(r => setTimeout(r, 150));
                    if (rallyStudy?.properties?.().visible) rallyStudy.properties().visible.setValue(true);
                    await new Promise(r => setTimeout(r, 200));

                    return {
                        dots: dots,
                        redDots: redDots,
                        donalt: { golden: goldenList, death: deathList },
                        smc: smcData,
                        scalping: { buy: buyList, sell: sellList, trend: currentTrend },
                        macd: { bull: bullList, bear: bearList },
                        currentClose: currentClose,
                        bars: recentBars
                    };
                } catch(e) {
                    return { dots: [], redDots: [], donalt: { golden: [], death: [] }, smc: null, scalping: { buy: [], sell: [], trend: null }, macd: { bull: [], bear: [] }, currentClose: null, bars: [], error: String(e) };
                }
            }''')
            
            dot_data = eval_data.get('dots', [])
            red_data = eval_data.get('redDots', [])
            cur_close = eval_data.get('currentClose') or stock_info.get('close')
            donalt_raw = eval_data.get('donalt', {})
            smc_raw = eval_data.get('smc')
            scalping_raw = eval_data.get('scalping', {})
            macd_raw = eval_data.get('macd', {})
            recent_bars = eval_data.get('bars', [])
            
            def _parse_tp_dt(tp_val):
                if tp_val is None:
                    return None
                if isinstance(tp_val, (int, float)):
                    return datetime.datetime.fromtimestamp(tp_val, WIB_TZ)
                elif isinstance(tp_val, dict):
                    if "time" in tp_val and isinstance(tp_val["time"], (int, float)):
                        return datetime.datetime.fromtimestamp(tp_val["time"], WIB_TZ)
                    y = tp_val.get("year")
                    m = tp_val.get("month")
                    d_day = tp_val.get("day")
                    if y and m and d_day:
                        return datetime.datetime(int(y), int(m), int(d_day), 9, 0, 0, tzinfo=WIB_TZ)
                return None

            # 1. Olah RallyGood Dot Green & Dot Red (30 hari terakhir)
            valid_dots = []
            for d in dot_data:
                dot_dt = _parse_tp_dt(d.get('timestamp'))
                if dot_dt:
                    diff_days = (now_dt - dot_dt).total_seconds() / 86400
                    if -1 <= diff_days <= LOOKBACK_DAYS:
                        valid_dots.append({
                            "dt": dot_dt,
                            "dot_close": d.get("dotClose"),
                            "current_close": d.get("currentClose")
                        })

            valid_red_dots = []
            for d in red_data:
                rd_dt = _parse_tp_dt(d.get('timestamp'))
                if rd_dt:
                    diff_days = (now_dt - rd_dt).total_seconds() / 86400
                    if -1 <= diff_days <= LOOKBACK_DAYS:
                        valid_red_dots.append({
                            "dt": rd_dt,
                            "dot_close": d.get("dotClose"),
                            "current_close": d.get("currentClose")
                        })
            
            raw_green_status = False
            latest_dot = None
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
                raw_green_status = True

            red_status = False
            latest_red = None
            red_date_display = None
            red_close = None
            red_drop_pct = None
            if valid_red_dots:
                latest_r = max(valid_red_dots, key=lambda x: x["dt"])
                latest_red = latest_r["dt"]
                b_str = BULAN_PENDEK.get(latest_red.month, latest_red.strftime("%b"))
                if tf_code == 'D':
                    red_date_display = f"{latest_red.day} {b_str} {latest_red.year}"
                else:
                    red_date_display = f"{latest_red.day} {b_str} {latest_red.year}, {latest_red.strftime('%H:%M')} WIB"
                red_close = latest_r.get("dot_close")
                cur_close = latest_r.get("current_close") or stock_info["close"]
                if red_close and cur_close and red_close > 0:
                    red_drop_pct = ((cur_close - red_close) / red_close) * 100
                red_status = True

            # Evaluasi pertentangan Dot Red vs Dot Green:
            # Di SEMUA timeframe (Daily, 1H, 15M):
            # Sinyal yang paling akhir muncul (terbaru) adalah sinyal aktif yang menang / valid.
            # Jika Red Dot muncul SETELAH Green Dot (latest_red > latest_dot):
            #   Green Dot gugur/dibatalkan (active_green = False), dan Red Dot aktif (active_red = True).
            # Jika Green Dot muncul SETELAH Red Dot (latest_dot > latest_red):
            #   Green Dot aktif (active_green = True), dan Red Dot terpatahkan (active_red = False).
            active_green = False
            active_red = False

            if raw_green_status and red_status:
                if latest_red > latest_dot:
                    active_green = False
                    active_red = True
                else:
                    active_green = True
                    active_red = False
            elif raw_green_status:
                active_green = True
                active_red = False
            elif red_status:
                active_green = False
                active_red = True

            dot_status = active_green  # Status resmi yang digunakan untuk perhitungan count_green

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
                
                # Cek apakah trend berbalik arah ke Golden Cross setelah sinyal Death Cross ini
                all_goldens = donalt_raw.get('golden', [])
                goldens_after_d = [g for g in all_goldens if g.get('timestamp') and g['timestamp'] > latest_d['timestamp']]
                d_reversed = bool(goldens_after_d)

                death_res = {
                    "date": d_date,
                    "dt": d_dt,
                    "price": d_price,
                    "reversed": d_reversed
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
                
                # Cek apakah trend berbalik arah ke BUY setelah sinyal SELL ini
                all_buys = scalping_raw.get('buy', [])
                buys_after_sell = [b for b in all_buys if b.get('timestamp') and b['timestamp'] > latest_sell['timestamp']]
                s_reversed = bool(buys_after_sell)

                sc_sell_res = {
                    "date": s_date,
                    "dt": s_dt,
                    "price": s_price,
                    "reversed": s_reversed
                }
                
            scalping_res = {
                "buy": sc_buy_res,
                "sell": sc_sell_res,
                "trend": scalping_raw.get('trend')
            }
            
            # 4. Olah Ultimate SMC Suite (Supply & Demand, Status 7D) untuk Daily (1D), 1 Jam (1H), dan 15 Menit (15M)
            smc_res = None
            if tf_code in ['D', '60', '15']:
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
                
                # Cek apakah ada Bearish Divergence setelah Bullish Divergence ini
                all_bears = macd_raw.get('bear', [])
                bears_after_b = [br for br in all_bears if br.get('timestamp') and br['timestamp'] > latest_b['timestamp']]
                b_reversed = bool(bears_after_b)

                bull_res = {
                    "type": latest_b.get("type", "Bull"),
                    "date": b_date,
                    "dt": b_dt,
                    "price": latest_b.get("price"),
                    "reversed": b_reversed
                }
                
            bear_res = None
            if recent_bear:
                latest_br = max(recent_bear, key=lambda x: x['timestamp'])
                br_dt = datetime.datetime.fromtimestamp(latest_br['timestamp'], WIB_TZ)
                br_str = BULAN_PENDEK.get(br_dt.month, br_dt.strftime("%b"))
                br_date = f"{br_dt.day} {br_str} {br_dt.year}" if tf_code == 'D' else f"{br_dt.day} {br_str} {br_dt.year}, {br_dt.strftime('%H:%M')} WIB"
                
                # Cek apakah ada Bullish Divergence setelah Bearish Divergence ini
                all_bulls = macd_raw.get('bull', [])
                bulls_after_br = [b for b in all_bulls if b.get('timestamp') and b['timestamp'] > latest_br['timestamp']]
                br_reversed = bool(bulls_after_br)

                bear_res = {
                    "type": latest_br.get("type", "Bear"),
                    "date": br_date,
                    "dt": br_dt,
                    "price": latest_br.get("price"),
                    "reversed": br_reversed
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
                
            if red_status and active_red:
                indicator_tags.append(f"🔴 Red Dot: {red_date_display}")
                
            indicator_str = f" [{', '.join(indicator_tags)}]" if indicator_tags else ""

            if dot_status:
                gain_info = f" (Kenaikan: {gain_pct:+.2f}%)" if gain_pct is not None else ""
                print(f" {w_tag}↳ {symbol} [{tf_name}]: 🟢 ADA DOT GREEN! ({date_display}){gain_info}{indicator_str}")
            elif raw_green_status and not active_green:
                print(f" {w_tag}↳ {symbol} [{tf_name}]: 🔴 DOT GREEN DIBATALKAN OLEH RED DOT! (Red: {red_date_display} > Green: {date_display}){indicator_str}")
            elif active_red:
                print(f" {w_tag}↳ {symbol} [{tf_name}]: 🔴 ADA RED DOT AKTIF ({red_date_display}){indicator_str}")
            else:
                print(f" {w_tag}↳ {symbol} [{tf_name}]: ❌ Tidak ada dot green{indicator_str}")

            results[tf_code] = {
                "status": dot_status,
                "raw_green_status": raw_green_status,
                "date": date_display if dot_status else None,
                "dt": latest_dot if dot_status else None,
                "dot_close": dot_close,
                "gain_pct": gain_pct if dot_status else None,
                "red_dot": {
                    "status": red_status,
                    "active": active_red,
                    "date": red_date_display,
                    "dt": latest_red,
                    "dot_close": red_close,
                    "drop_pct": red_drop_pct
                },
                "donalt": donalt_res,
                "scalping": scalping_res,
                "smc": smc_res,
                "macd": macd_res
            }
                    
        except Exception as e:
            print(f" {w_tag}⚠️ Error {symbol} [{tf_name}]: {e}")
            results[tf_code] = {"status": False, "date": None, "error": str(e)}
            
    return results
            
# ============================================================================
# TAHAP 3.5: SIMPAN DATA UNTUK WEB STATIS (RETENSI 30 HARI / 1 BULAN BERGULIR)
# ============================================================================
def simpan_database_json(hasil_deteksi, now_wib):
    """
    Menyimpan hasil analisa ke database JSON untuk Web Statis Dashboard:
    - Retensi 30 hari (1 bulan bergulir) untuk semua data scan harian.
    - Data > 30 hari otomatis terhapus saat data hari baru dibuat.
    """
    try:
        data_dir = Path("docs") / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        history_file = data_dir / "history.json"
        
        # Inisialisasi struktur history
        history = {
            "last_updated": now_wib.strftime("%Y-%m-%d %H:%M:%S WIB"),
            "daily_scans": {},
            "vip_3dot_history": []
        }
        if history_file.exists():
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                pass
                
        trading_dt = get_latest_trading_date(now_wib)
        date_key = trading_dt.strftime("%Y-%m-%d")
        tgl_id = format_tanggal_id(trading_dt)
        
        # 1. Cek emiten yang mengalami Red Dot aktif di 1D DAN 1H
        # Emiten ini terhapus total dari database website hari ini (daily_scans) & vip_3dot_history
        purged_symbols = set()
        for item in hasil_deteksi:
            sym = item.get('stock', {}).get('symbol')
            tf = item.get('timeframes', {})
            red_d = tf.get('D', {}).get('red_dot', {}).get('active', False)
            red_60 = tf.get('60', {}).get('red_dot', {}).get('active', False)
            if red_d and red_60:
                purged_symbols.add(sym)
                print(f"🚫 [PURGE 1D+1H RED DOT] {sym}: Memiliki Red Dot aktif di Daily DAN 1 Jam! Terhapus dari website hari ini & menu VIP.")

        clean_stocks = []
        for item in hasil_deteksi:
            st = item.get('stock', {})
            sym = st.get('symbol')
            if sym in purged_symbols:
                continue

            tf = item.get('timeframes', {})
            clean_tf = {}
            for tf_k in ['D', '60', '15']:
                tf_v = tf.get(tf_k, {})
                clean_tf[tf_k] = {
                    "status": bool(tf_v.get("status", False)),
                    "date": tf_v.get("date"),
                    "dot_close": tf_v.get("dot_close"),
                    "gain_pct": tf_v.get("gain_pct"),
                    "red_dot": tf_v.get("red_dot"),
                    "donalt": tf_v.get("donalt"),
                    "scalping": tf_v.get("scalping"),
                    "smc": tf_v.get("smc"),
                    "macd": tf_v.get("macd")
                }
            
            c_val = float(st.get("close", 0))
            cg = sum(1 for tf_k in ['D', '60', '15'] if clean_tf[tf_k]["status"])
            clean_stocks.append({
                "symbol": sym,
                "name": st.get("name", sym),
                "close": c_val,
                "high": float(st.get("high", c_val)),
                "low": float(st.get("low", c_val)),
                "change": st.get("change"),
                "volume": st.get("volume"),
                "count_green": cg,
                "has_green_dot": cg > 0,
                "is_vip_audit": bool(st.get("is_vip_audit", False)),
                "timeframes": clean_tf
            })
            
        # Urutkan berdasarkan count_green desc, lalu volume desc
        clean_stocks.sort(key=lambda x: (x.get("count_green", 0), x.get("volume", 0)), reverse=True)
        
        saham_3_dot = [s for s in clean_stocks if s["count_green"] == 3 and not s.get("is_vip_audit", False)]
        saham_2_dot = [s for s in clean_stocks if s["count_green"] == 2 and not s.get("is_vip_audit", False)]
        saham_1_dot = [s for s in clean_stocks if s["count_green"] == 1 and not s.get("is_vip_audit", False)]
        saham_0_dot = [s for s in clean_stocks if s["count_green"] == 0 and not s.get("is_vip_audit", False)]
        
        # Khusus Website Screener Hari Ini: Hanya simpan saham yang memang lolos screener (bukan audit vip sepi)
        saham_web = [s for s in clean_stocks if s.get("count_green", 0) >= 2 and not s.get("is_vip_audit", False)]
        
        # Deteksi Sesi Bursa saat Penyimpanan Database (Midday / Istirahat vs Penutupan Sore)
        cur_t = now_wib.time()
        t_0900 = datetime.time(9, 0)
        t_1430 = datetime.time(14, 30)
        is_midday = (t_0900 <= cur_t < t_1430) and (now_wib.weekday() < 5)
        cur_session_tag = "SESI_SIANG" if is_midday else "SESI_SORE"
        cur_session_label = "Sesi Siang (Istirahat)" if is_midday else "Penutupan Sore"

        # Cek apakah data penutupan hari ini 100% sama persis dengan yang sudah tersimpan untuk date_key ini
        if date_key in history.get("daily_scans", {}):
            old_day_data = history["daily_scans"][date_key]
            old_stocks = old_day_data.get("stocks", [])
            if old_stocks and len(old_stocks) == len(saham_web):
                old_map = {s["symbol"]: (s.get("close"), s.get("volume"), s.get("count_green")) for s in old_stocks if s.get("symbol")}
                new_map = {s["symbol"]: (s.get("close"), s.get("volume"), s.get("count_green")) for s in saham_web if s.get("symbol")}
                if old_map == new_map and old_day_data.get("session") == cur_session_tag:
                    print(f"ℹ️ [DATABASE WEB] Data scan untuk {date_key} ({cur_session_label}) 100% identik dengan database sebelumnya. Melewati penulisan file agar git diff tetap bersih.")
                    return

        # Simpan scan hari ini
        history["last_updated"] = now_wib.strftime("%Y-%m-%d %H:%M:%S WIB")
        if "daily_scans" not in history or not isinstance(history["daily_scans"], dict):
            history["daily_scans"] = {}

        # Simpan info harga & sesi entry awal jika saham sudah terdeteksi di Sesi Siang
        existing_today_stocks = {}
        if date_key in history.get("daily_scans", {}):
            for st_old in history["daily_scans"][date_key].get("stocks", []):
                if st_old.get("symbol"):
                    existing_today_stocks[st_old["symbol"]] = st_old

        for s in saham_web:
            sym_w = s.get("symbol")
            old_w = existing_today_stocks.get(sym_w)
            if is_midday:
                s["entry_session"] = "SESI_SIANG"
                s["midday_price"] = float(s.get("close", 0))
            elif old_w and old_w.get("midday_price"):
                s["entry_session"] = "SESI_SIANG"
                s["midday_price"] = old_w["midday_price"]
            else:
                s["entry_session"] = "SESI_SORE"
                s["midday_price"] = None

        history["daily_scans"][date_key] = {
            "date": date_key,
            "date_display": tgl_id,
            "time_display": now_wib.strftime("%H:%M WIB"),
            "session": cur_session_tag,
            "session_label": cur_session_label,
            "summary": {
                "total_screener": len(saham_web),
                "count_3_dot": len(saham_3_dot),
                "count_2_dot": len(saham_2_dot),
                "count_1_dot": len(saham_1_dot),
                "count_0_dot": len(saham_0_dot)
            },
            "stocks": saham_web
        }
        
        # PANGKAS DATABASE: MAKSIMAL 30 CANDLE / HARI BUKA BURSA TERAKHIR (1 BULAN BERGULIR)
        # Jika masuk tanggal baru ke-31, tanggal terlama (ke-1) otomatis terhapus bergulir.
        sorted_daily_keys = sorted(history["daily_scans"].keys())
        if len(sorted_daily_keys) > 30:
            keys_to_remove = sorted_daily_keys[:-30]
            for d_key in keys_to_remove:
                del history["daily_scans"][d_key]
                print(f"🗑️ [RETENSI 30 CANDLE] Menghapus data harian bursa lama tanggal {d_key} (> 30 candle).")
        
        # Batas tanggal bursa terlama yang masih aktif tersimpan
        oldest_retained_date = min(history["daily_scans"].keys()) if history["daily_scans"] else date_key
                
        # 2. SIMPAN & PERBARUI RIWAYAT KHUSUS SAHAM 3 DOT GREEN & REKOMENDASI (1 BULAN / 30 CANDLE)
        if "vip_3dot_history" not in history or not isinstance(history["vip_3dot_history"], list):
            history["vip_3dot_history"] = []

        # Penanganan Status Saham VIP 3-Dot (Track Record Testimoni vs Rekomendasi Aktif):
        # Saham TIDAK DIHAPUS dari vip_3dot_history agar tetap bertahan 30 hari bursa sebagai etalase testimoni keuntungan!
        # Namun diberi status "COMPLETED" (Selesai / Take Profit) jika terkena Red Dot 1H atau Red Dot 1D + 1H:
        symbols_scanned_today = {s["symbol"]: s for s in clean_stocks}
        demoted_vip_symbols = {sym for sym, s in symbols_scanned_today.items() if s.get("count_green", 0) < 3}
        completed_vip_symbols = purged_symbols.union(demoted_vip_symbols)

        for h in history["vip_3dot_history"]:
            sym = h.get("symbol")
            if sym in completed_vip_symbols:
                if h.get("status") != "COMPLETED":
                    h["status"] = "COMPLETED"
                    h["is_active"] = False
                    h["exit_reason"] = "RED_DOT_1D_1H" if sym in purged_symbols else "RED_DOT_1H"
                    h["exit_date"] = date_key
                    h["exit_date_display"] = tgl_id
                    h["exit_label"] = "🏁 Selesai / Take Profit"
                    print(f"🏁 [TRACK RECORD TESTIMONI] {sym}: Terdeteksi Red Dot. Ditandai 'Selesai / Take Profit' (tetap disimpan 30 hari sebagai testimoni, dinonaktifkan dari menu VIP).")

        stock_lookup = {s["symbol"]: s for s in clean_stocks}
        saham_3_dot_lookup = {s["symbol"]: s for s in saham_3_dot}
        tgl_id_short = now_wib.strftime("%d %b %Y")

        # Cek apakah ada saham yang sedang dipantau di vip_3dot_history tapi sepi/tidak masuk screener hunter hari ini
        missing_tracked = [
            h.get("symbol") for h in history["vip_3dot_history"]
            if h.get("symbol") and h.get("symbol") not in stock_lookup
        ]
        if missing_tracked:
            try:
                q_missing = (Query().set_markets('indonesia')
                             .select('name', 'close', 'high', 'low', 'change', 'volume')
                             .where(Column('name').isin(missing_tracked)))
                df_miss = q_missing.get_scanner_data()[1]
                if not df_miss.empty:
                    for _, row in df_miss.iterrows():
                        tk = str(row['ticker']).split(':')[-1]
                        c_val = float(row['close'])
                        h_raw = float(row.get('high', c_val))
                        l_raw = float(row.get('low', c_val))
                        stock_lookup[tk] = {
                            "symbol": tk,
                            "name": tk,
                            "close": c_val,
                            "high": max(h_raw, c_val),
                            "low": min(l_raw, c_val),
                            "change": float(row['change']),
                            "volume": float(row['volume']),
                            "count_green": 0,
                            "has_green_dot": False,
                            "timeframes": {}
                        }
            except Exception as e_miss:
                print(f"⚠️ [INFO] Info harga saham sepi tidak dapat di-fetch: {e_miss}")

        # a. Perbarui saham-saham yang SUDAH ADA di tracking vip_3dot_history
        scanned_symbols = {s["symbol"] for s in clean_stocks}
        for h in history["vip_3dot_history"]:
            sym = h.get("symbol")
            if "performance_history" not in h or not isinstance(h["performance_history"], list):
                h["performance_history"] = []

            # Konfirmasi Ulang Sinyal (Re-Trigger 3-Dot Green):
            # Jika saham ter-trigger 3-Dot Green lagi di tanggal baru, perbarui data indikator & tanggal sinyal terakhir
            # Catatan: TIDAK me-reset performance_history agar seluruh riwayat hari bursa sebelumnya tetap tersimpan utuh!
            if sym in saham_3_dot_lookup:
                s3 = saham_3_dot_lookup[sym]
                h["data"] = s3
                h["status"] = "ACTIVE"
                h["is_active"] = True
                h["exit_reason"] = None
                h["exit_label"] = "🟢 Aktif Dipantau"
                h["last_trigger_date"] = date_key
                h["last_trigger_date_display"] = tgl_id
                if not h.get("base_price"):
                    h["base_price"] = float(s3.get("close", 0))
                if not h.get("entry_session"):
                    h["entry_session"] = "SESI_SIANG" if is_midday else "SESI_SORE"
                    h["entry_session_label"] = "Sesi Siang (Istirahat)" if is_midday else "Penutupan Sore"

            # Update data harian berjalan (Tracking harian 30 hari bursa)
            if sym in stock_lookup:
                cur_s = stock_lookup[sym]
                c_val = float(cur_s.get("close", 0))
                h_val = max(float(cur_s.get("high", c_val)), c_val)
                l_val = min(float(cur_s.get("low", c_val)), c_val)
                chg_val = round(float(cur_s.get("change", 0.0)), 2)
                base_p = float(h.get("base_price") or c_val)
                if not h.get("base_price"):
                    h["base_price"] = base_p
                
                cum_gain = round(((c_val - base_p) / base_p) * 100, 2) if base_p > 0 else 0.0
                peak_gain_today = round(((h_val - base_p) / base_p) * 100, 2) if base_p > 0 else 0.0

                if sym in scanned_symbols:
                    h["data"] = cur_s
                    cg_status = cur_s.get("count_green", 0)
                else:
                    # Saham sepi/tidak masuk screener hari ini: update harga close, high, low, change, volume
                    # Data indikator sinyal 3-Dot (RallyGood, SMC, EMA) tetap utuh terjaga!
                    if "data" in h and isinstance(h["data"], dict):
                        h["data"]["close"] = c_val
                        h["data"]["high"] = h_val
                        h["data"]["low"] = l_val
                        h["data"]["change"] = chg_val
                        h["data"]["volume"] = float(cur_s.get("volume", 0))
                    else:
                        h["data"] = cur_s
                    cg_status = h.get("data", {}).get("count_green", 3)

                # Update jika tanggal hari ini sudah ada, atau tambahkan jika hari baru
                existing_entry = next((item for item in h["performance_history"] if item.get("date") == date_key), None)
                if existing_entry:
                    existing_entry["close"] = c_val
                    existing_entry["high"] = h_val
                    existing_entry["low"] = l_val
                    existing_entry["daily_change_pct"] = chg_val
                    existing_entry["cumulative_gain_pct"] = cum_gain
                    existing_entry["peak_gain_pct"] = peak_gain_today
                    existing_entry["count_green"] = cg_status
                else:
                    h["performance_history"].append({
                        "date": date_key,
                        "date_display": tgl_id_short,
                        "close": c_val,
                        "high": h_val,
                        "low": l_val,
                        "daily_change_pct": chg_val,
                        "cumulative_gain_pct": cum_gain,
                        "peak_gain_pct": peak_gain_today,
                        "count_green": cg_status
                    })

        # b. Tambahkan saham 3-Dot Green BARU yang belum pernah masuk vip_3dot_history
        existing_symbols = {h.get("symbol") for h in history["vip_3dot_history"]}
        for s3 in saham_3_dot:
            sym = s3["symbol"]
            if sym not in existing_symbols:
                c_val = float(s3.get("close", 0))
                h_val = max(float(s3.get("high", c_val)), c_val)
                l_val = min(float(s3.get("low", c_val)), c_val)
                chg_val = round(float(s3.get("change", 0.0)), 2)

                ent_session = "SESI_SIANG" if is_midday else "SESI_SORE"
                ent_session_label = "Sesi Siang (Istirahat)" if is_midday else "Penutupan Sore"

                record_item = {
                    "symbol": sym,
                    "scan_date": date_key,
                    "scan_date_display": tgl_id,
                    "base_price": c_val,
                    "entry_session": ent_session,
                    "entry_session_label": ent_session_label,
                    "entry_time": now_wib.strftime("%H:%M WIB"),
                    "status": "ACTIVE",
                    "is_active": True,
                    "exit_reason": None,
                    "exit_label": "🟢 Aktif Dipantau",
                    "data": s3,
                    "performance_history": [{
                        "date": date_key,
                        "date_display": tgl_id_short,
                        "close": c_val,
                        "high": h_val,
                        "low": l_val,
                        "daily_change_pct": 0.0,
                        "cumulative_gain_pct": 0.0,
                        "peak_gain_pct": 0.0,
                        "entry_session": ent_session,
                        "count_green": 3
                    }]
                }
                history["vip_3dot_history"].append(record_item)
                existing_symbols.add(sym)

        # c. Pangkas saham yang masa pantau 30 hari bursa-nya sudah kedaluwarsa (tanpa re-trigger baru)
        history["vip_3dot_history"] = [
            h for h in history["vip_3dot_history"]
            if max(h.get("last_trigger_date", ""), h.get("scan_date", "")) >= oldest_retained_date
        ]

        # Urutkan vip_3dot_history berdasarkan tanggal sinyal terbaru
        history["vip_3dot_history"].sort(key=lambda x: (max(x.get("last_trigger_date", ""), x.get("scan_date", "")), x.get("data", {}).get("volume", 0)), reverse=True)
        
        # Tulis ke file JSON history.json
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2, default=str)
            
        print(f"💾 [DATABASE WEB] Berhasil menyimpan data scan & riwayat 1 bulan (30 hari rolling) di {history_file}")
    except Exception as e:
        print(f"⚠️ [DATABASE WEB ERROR] Gagal menyimpan data JSON: {e}")

# ============================================================================
# TAHAP 3.8: PENGAMBILAN SAHAM VIP 3-DOT UNTUK AUDIT PENUTUPAN
# ============================================================================
def get_missing_vip_stocks(current_stocks):
    """
    Mengambil saham yang sedang dipantau di vip_3dot_history namun
    tidak masuk dalam daftar screener hunter hari ini (karena volume sepi)
    agar grafik & indikatornya dapat diaudit saat penutupan pasar / akhir realtime.
    """
    history_file = Path("docs/data/history.json")
    if not history_file.exists():
        return []
    try:
        with open(history_file, "r", encoding="utf-8") as f:
            hist = json.load(f)
        current_symbols = set()
        for s in current_stocks:
            if isinstance(s, dict):
                sym = s.get("symbol") or s.get("stock", {}).get("symbol")
                if sym:
                    current_symbols.add(sym)
        vip_list = hist.get("vip_3dot_history", [])
        # HANYA audit saham VIP yang MASIH AKTIF (yang belum COMPLETED) agar efisien
        missing = [
            v.get("symbol") for v in vip_list
            if v.get("symbol") and v.get("symbol") not in current_symbols and v.get("status") != "COMPLETED"
        ]
        if not missing:
            return []
        
        q_missing = (Query().set_markets('indonesia')
                     .select('name', 'close', 'high', 'low', 'change', 'volume')
                     .where(Column('name').isin(missing)))
        df_miss = q_missing.get_scanner_data()[1]
        missing_stocks = []
        if not df_miss.empty:
            for _, row in df_miss.iterrows():
                tk = str(row['ticker']).split(':')[-1]
                c_val = float(row['close'])
                h_raw = float(row.get('high', c_val))
                l_raw = float(row.get('low', c_val))
                missing_stocks.append({
                    "symbol": tk,
                    "name": tk,
                    "close": c_val,
                    "high": max(h_raw, c_val),
                    "low": min(l_raw, c_val),
                    "change": float(row['change']),
                    "volume": float(row['volume']),
                    "is_vip_audit": True
                })
        return missing_stocks
    except Exception as e:
        print(f"⚠️ [VIP AUDIT FETCH ERROR] Gagal mengambil info saham VIP: {e}")
        return []

# ============================================================================
# TAHAP 4: EKSEKUSI UTAMA (SCAN HARIAN JAM 16.21 WIB)
# ============================================================================
async def run_daily_scan(send_wa=True, realtime_mode=False, alerted_keys=None, audit_vip=False, custom_stocks=None):
    now_wib = datetime.datetime.now(WIB_TZ)
    date_str = now_wib.strftime("%Y%m%d")
    tgl_analisa_id = format_tanggal_id(now_wib)
    tgl_awal_id = format_tanggal_id(now_wib - datetime.timedelta(days=LOOKBACK_DAYS))
    
    mode_tag = "REAL-TIME INTRADAY" if realtime_mode else ("AUDIT VIP" if custom_stocks is not None else "SCAN HARIAN")
    print("\n" + "="*70)
    print(f"🚀 MEMULAI {mode_tag} HUNTER - RALLY GOD [{tgl_analisa_id} {now_wib.strftime('%H:%M WIB')}]")
    print("="*70)
    
    # Bersihkan file screenshot lama agar disk tetap bersih
    bersihkan_screenshot()
    
    if custom_stocks is not None:
        stocks_to_scan = list(custom_stocks)
        hunter_stocks = [s for s in stocks_to_scan if not s.get("is_vip_audit")]
        if not stocks_to_scan:
            print("ℹ️ Daftar saham kustom kosong.")
            return []
    else:
        # 1. Ambil saham lolos kriteria Screener HUNTER
        hunter_stocks = get_hunter_stocks()
        if not hunter_stocks:
            if send_wa and not realtime_mode:
                kirim_whatsapp(f"ℹ️ *SCAN HUNTER {tgl_analisa_id}*\nTidak ada saham IDX Rp 10-1000 yang lolos kriteria volume hari ini.")
            return []

        stocks_to_scan = list(hunter_stocks)
        # Perbaikan & Audit Saham VIP yang sepi HANYA dijalankan di akhir saat penutupan bursa / realtime selesai:
        if audit_vip or not realtime_mode:
            vip_audit_stocks = get_missing_vip_stocks(hunter_stocks)
            if vip_audit_stocks:
                print(f"🔍 [AUDIT PENUTUPAN VIP 3-DOT] Menambahkan {len(vip_audit_stocks)} saham VIP (tidak lolos screener volume hari ini) untuk diperiksa grafik & Red Dot-nya...")
                stocks_to_scan.extend(vip_audit_stocks)
        
    # Kirim notifikasi awal ke WhatsApp saat pemindaian harian dimulai (dilewati pada mode real-time loop agar tidak spam)
    if send_wa and not realtime_mode and custom_stocks is None:
        pesan_mulai = (
            f"🚀 *Memulai Analisa Screener Aranter*\n"
            f"📅 *{tgl_analisa_id}* • ⏰ *{now_wib.strftime('%H:%M WIB')}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 *Jumlah Saham Terdeteksi di Screener*: *{len(hunter_stocks)} Saham*\n"
            f"⚡ *Multi-Worker Parallel*: *{min(NUM_WORKERS, len(hunter_stocks))} Worker Aktif*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏳ Bot sedang menganalisis chart multi-timeframe (Daily, 1H, 15M) di TradingView...\n\n"
            f"Laporan lengkap akan dikirimkan otomatis setelah pemindaian selesai."
        )
        kirim_whatsapp(pesan_mulai)
        
    hasil_deteksi = []
    t_start_total = time.time()
    async with async_playwright() as pw:
        browser_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--js-flags=--max-old-space-size=256",
            "--disable-extensions",
            "--disable-background-networking",
            "--mute-audio"
        ]
        browser = None
        for launch_opt in [{}, {"channel": "chrome"}, {"channel": "msedge"}]:
            try:
                browser = await pw.chromium.launch(headless=True, args=browser_args, **launch_opt)
                break
            except Exception:
                continue
                
        if not browser:
            print("[ERROR] Tidak dapat membuka browser (Chromium/Chrome/Edge). Pastikan browser terpasang.")
            return
        
        # Inisialisasi Browser Contexts terisolasi untuk tiap akun TradingView
        contexts = []
        if TRADINGVIEW_SESSIONIDS:
            for acc_idx, sid in enumerate(TRADINGVIEW_SESSIONIDS, 1):
                ctx = await browser.new_context(
                    viewport={"width": 1600, "height": 900},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                await ctx.add_cookies([{
                    "name": "sessionid",
                    "value": sid,
                    "domain": ".tradingview.com",
                    "path": "/"
                }])
                contexts.append(ctx)
                print(f"🔑 [Akun {acc_idx}] Session Cookie TradingView ({sid[:6]}...{sid[-4:]}) berhasil dimuat.")
        else:
            ctx = await browser.new_context(
                viewport={"width": 1600, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            contexts.append(ctx)
            print("[INFO] Menjalankan tanpa sessionid (indikator publik/template layout).")
            
        async def buat_halaman_chart(sym_target, worker_id=1):
            ctx = contexts[(worker_id - 1) % len(contexts)]
            chart_page = await ctx.new_page()
            try:
                await chart_page.route(
                    "**/*",
                    lambda route: route.abort() if route.request.resource_type in ["media"] or any(
                        x in route.request.url for x in ["google-analytics", "doubleclick", "hotjar", "datadoghq"]
                    ) else route.continue_()
                )
            except Exception:
                pass
            await chart_page.goto(f"{CHART_LAYOUT_URL}?symbol=IDX%3A{sym_target}&interval=D", wait_until="domcontentloaded", timeout=45000)
            for _ in range(40):
                await asyncio.sleep(0.5)
                ready = await chart_page.evaluate('''() => {
                    try {
                        const chart = window._exposed_chartWidgetCollection?.activeChartWidget?.value();
                        if (!chart || !chart.model) return false;
                        const model = chart.model();
                        if (!model || !model.panes) return false;
                        const allStudies = model.panes().flatMap(p => p.dataSources());
                        const hasRally = allStudies.some(s => s.title && s.title().includes('RallyGood'));
                        return allStudies.length >= 4 && hasRally;
                    } catch(e) {
                        return false;
                    }
                }''')
                if ready:
                    break
            # Sinkronisasi status default indikator di awal
            await chart_page.evaluate('''async () => {
                try {
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
                    await new Promise(r => setTimeout(r, 200));

                    if (donalt?.properties?.().visible) donalt.properties().visible.setValue(true);
                    if (rally?.properties?.().visible) rally.properties().visible.setValue(true);
                    await new Promise(r => setTimeout(r, 300));
                } catch(e) {}
            }''')
            await asyncio.sleep(0.5)
            return chart_page

        # Inisialisasi antrean saham terpusat (asyncio.Queue) agar TIDAK BENTROK antar worker
        queue = asyncio.Queue()
        for idx, stock in enumerate(stocks_to_scan, 1):
            await queue.put((idx, stock))
            
        hasil_deteksi = []
        lock = asyncio.Lock()
        total_stocks = len(stocks_to_scan)
        actual_workers = max(1, min(NUM_WORKERS, total_stocks))
        
        print(f"\n⚡ [PARALLEL ENGINE] Menjalankan {actual_workers} worker browser paralel ({len(contexts)} akun TradingView) untuk {total_stocks} saham (Screener + Audit VIP)...\n")

        async def worker_loop(worker_id: int):
            account_num = ((worker_id - 1) % len(contexts)) + 1
            first_sym = stocks_to_scan[0]['symbol']
            print(f"🚀 [Worker {worker_id} | Akun {account_num}] Menyiapkan tab browser TradingView ({first_sym})...")
            page = await buat_halaman_chart(first_sym, worker_id=worker_id)
            print(f"⚙️ [Worker {worker_id} | Akun {account_num}] Tab siap & indikator tersinkronisasi.")
            
            processed_count = 0
            MAX_RETRIES = 2
            
            try:
                while not queue.empty():
                    try:
                        idx, stock = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                    sym = stock['symbol']
                    processed_count += 1

                    # FITUR AUTO-PURGE RAM: Setiap 5 saham per worker, refresh tab agar RAM tetap ringan (<200 MB)
                    if processed_count > 1 and (processed_count - 1) % 5 == 0:
                        print(f"\n🧹 [Worker {worker_id} | Akun {account_num} - RAM AUTO-PURGE] Mengosongkan cache grafik & me-refresh tab untuk {sym}...")
                        try:
                            await page.close()
                        except Exception:
                            pass
                        gc.collect()
                        page = await buat_halaman_chart(sym, worker_id=worker_id)
                        print(f"✨ [Worker {worker_id} | Akun {account_num}] Tab segar kembali. Melanjutkan analisis {sym}...")

                    print(f"\n[{idx}/{total_stocks}] [Worker {worker_id} | Akun {account_num}] Memeriksa Saham: {sym} (Rp {stock['close']:.0f} | {stock['change']:+.2f}%)")

                    t_start_saham = time.time()
                    for attempt in range(1, MAX_RETRIES + 1):
                        try:
                            tf_results = await scan_stock_rallygood(page, stock, worker_id=worker_id)
                            if not tf_results:
                                tf_results = {}

                            count_green = sum(1 for tf in TIMEFRAMES if tf_results.get(tf['code'], {}).get('status', False))
                            any_green = count_green > 0
                            dur_saham = time.time() - t_start_saham

                            async with lock:
                                hasil_deteksi.append({
                                    "stock": stock,
                                    "timeframes": tf_results,
                                    "count_green": count_green,
                                    "has_green_dot": any_green,
                                    "order_idx": idx,
                                    "dur_sec": dur_saham
                                })
                                if realtime_mode and alerted_keys is not None:
                                    await asyncio.to_thread(check_and_send_instant_alert, stock, tf_results, alerted_keys, now_wib)
                                    await asyncio.to_thread(check_and_send_bearish_alert, stock, tf_results, alerted_keys, now_wib)
                            print(f"⏱️ [{idx}/{total_stocks}] [Worker {worker_id} | Akun {account_num}] Selesai {sym} dalam {dur_saham:.1f} detik.")
                            break
                        except Exception as err_saham:
                            if attempt < MAX_RETRIES:
                                print(f"⚠️ [Worker {worker_id} | Akun {account_num} - RETRY {attempt}/{MAX_RETRIES}] Saham {sym} terkendala: {err_saham}. Merefresh tab...")
                                try:
                                    if page.is_closed():
                                        page = await buat_halaman_chart(sym, worker_id=worker_id)
                                    else:
                                        await page.goto(f"{CHART_LAYOUT_URL}?symbol=IDX%3A{sym}&interval=D", wait_until="domcontentloaded", timeout=45000)
                                    await asyncio.sleep(2.0)
                                except Exception as rec_err:
                                    print(f"⚠️ [Worker {worker_id} | Akun {account_num}] Gagal memulihkan tab: {rec_err}")
                            else:
                                print(f"❌ [Worker {worker_id} | Akun {account_num} - SKIP] Saham {sym} sudah dicoba {MAX_RETRIES}x namun tetap gagal: {err_saham}. Melanjutkan antrean...")
                                async with lock:
                                    hasil_deteksi.append({
                                        "stock": stock,
                                        "timeframes": {},
                                        "has_green_dot": False,
                                        "order_idx": idx,
                                        "dur_sec": time.time() - t_start_saham
                                    })
            finally:
                try:
                    if not page.is_closed():
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
                            await new Promise(r => setTimeout(r, 200));
                            if (donalt?.properties?.().visible) donalt.properties().visible.setValue(true);
                            if (rally?.properties?.().visible) rally.properties().visible.setValue(true);
                        }''')
                        await page.close()
                except Exception:
                    pass

        # Aktifkan pelacak penggunaan RAM & CPU secara real-time
        hw_mon = HardwareMonitor()
        hw_task = asyncio.create_task(hw_mon.run())

        # Jalankan worker secara bertahap (staggered start 2 detik agar tidak rebutan inisialisasi)
        tasks = []
        for w_id in range(1, actual_workers + 1):
            tasks.append(asyncio.create_task(worker_loop(w_id)))
            if w_id < actual_workers:
                await asyncio.sleep(2.0)

        await asyncio.gather(*tasks)
        hw_stats = hw_mon.stop()
        hw_task.cancel()
        await browser.close()

    t_end_total = time.time()
    total_dur_sec = t_end_total - t_start_total
    menit = int(total_dur_sec // 60)
    detik = total_dur_sec % 60
    dur_str = f"{menit}m {detik:.1f}s" if menit > 0 else f"{total_dur_sec:.1f} detik"
    avg_per_saham = total_dur_sec / total_stocks if total_stocks > 0 else 0

    print("\n" + "═" * 70)
    print(f"⚡ BENCHMARK KECEPATAN & KONSUMSI HARDWARE ({actual_workers} WORKER PARALEL)")
    print(f"⏱️ Total Waktu Pemindaian : {dur_str} ({total_dur_sec:.1f} detik)")
    print(f"📊 Saham Berhasil Discan  : {total_stocks} Saham")
    print(f"🤖 Worker Aktif           : {actual_workers} Worker Tab Browser ({len(contexts)} Akun)")
    print(f"⚡ Kecepatan Rata-Rata    : {avg_per_saham:.1f} detik / saham")
    if hw_stats:
        print(f"💻 Spesifikasi CPU        : {hw_stats['total_cores']} Cores/Threads ({hw_stats['physical_cores']} Core Fisik)")
        print(f"🖥️ Pemakaian CPU          : Rata-rata {hw_stats['avg_cpu']:.1f}% | Puncak {hw_stats['peak_cpu']:.1f}%")
        print(f"🧠 Pemakaian RAM Total    : Puncak {hw_stats['peak_mb']:.1f} MB ({hw_stats['peak_gb']:.2f} GB) / {hw_stats['pct_ram']:.1f}% dari {hw_stats['total_ram_gb']:.1f} GB")
    print(f"🚀 Peningkatan Performa   : ~{actual_workers}x lebih cepat dibanding scan sekuensial!")
    print("═" * 70 + "\n")

    # Urutkan kembali hasil analisa sesuai urutan awal screener
    hasil_deteksi.sort(key=lambda x: x.get('order_idx', 0))
        
    # 4. Susun Konten Laporan Teks Lengkap
    konten_laporan = []
    konten_laporan.append("=" * 75)
    konten_laporan.append(f"LAPORAN ANALISA SAHAM HUNTER - {tgl_analisa_id.upper()} (RALLY GOD IDX)")
    konten_laporan.append(f"Tanggal Analisa  : {tgl_analisa_id}")
    konten_laporan.append(f"Waktu Eksekusi   : {now_wib.strftime('%H:%M:%S WIB')} (Durasi: {dur_str})")
    konten_laporan.append(f"Kriteria Filter  : Harga Rp 10-1.000 | Vol > Avg 10D | Vol Pre-mkt > 500% (IDX)")
    konten_laporan.append(f"Rentang Analisis : {tgl_awal_id} s/d {tgl_analisa_id} (1 Bulan Terakhir / 30 Hari)")
    konten_laporan.append(f"Layout Chart     : {CHART_LAYOUT_URL}")
    konten_laporan.append("=" * 75 + "\n")
    
    # Hitung jumlah timeframe dengan Dot Green untuk setiap saham
    for item in hasil_deteksi:
        tf = item["timeframes"]
        item["count_green"] = sum(1 for tf_key in ['D', '60', '15'] if tf.get(tf_key, {}).get('status'))

    # Pisahkan saham screener hunter murni vs saham audit VIP untuk laporan teks & WhatsApp
    saham_hunter_only = [item for item in hasil_deteksi if not item.get("stock", {}).get("is_vip_audit", False)]
    saham_audit_vip = [item for item in hasil_deteksi if item.get("stock", {}).get("is_vip_audit", False)]

    # Kelompokkan saham berdasarkan jumlah sinyal Dot Green (khusus saham screener hunter)
    saham_3_dot = [item for item in saham_hunter_only if item["count_green"] == 3]
    saham_2_dot = [item for item in saham_hunter_only if item["count_green"] == 2]
    saham_1_dot = [item for item in saham_hunter_only if item["count_green"] == 1]
    saham_0_dot = [item for item in saham_hunter_only if item["count_green"] == 0]

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
    konten_laporan.append(f"• Total Saham Screener Hunter : {len(saham_hunter_only)} Saham")
    if saham_audit_vip:
        konten_laporan.append(f"• Total Saham Audit VIP 3-Dot : {len(saham_audit_vip)} Saham")
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
        
    # 5. Susun Pesan Rangkuman WhatsApp (Hanya pada mode scan harian biasa, bukan real-time loop atau audit parsial)
    if send_wa and not realtime_mode and custom_stocks is None:
        kirim_pesan_summary_wa(saham_hunter_only, now_wib)
    elif not send_wa:
        print("ℹ️ Mode Uji Coba: Pengiriman WhatsApp dilewati.")
        
    # 6. Simpan Data ke Database JSON (Hanya pada scan lengkap seluruh saham, bukan uji coba --limit atau audit parsial)
    if LIMIT_SAHAM_SCAN == 0 and custom_stocks is None:
        simpan_database_json(hasil_deteksi, now_wib)
    elif custom_stocks is not None:
        pass  # Penyimpanan database dikelola oleh fungsi pemanggil (misal transisi sesi)
    else:
        print(f"ℹ️ [MODE UJI COBA --limit {LIMIT_SAHAM_SCAN}] Penyimpanan ke database web (history.json) dilewati agar data web resmi tetap utuh.")

    # Pastikan seluruh sisa screenshot dibersihkan
    bersihkan_screenshot()
    return hasil_deteksi

# ============================================================================
# MESIN REAL-TIME INTRADAY BURSA IDX
# ============================================================================
async def run_realtime_market_session(single_session=False, test_mode=False):
    """
    Mesin pemantauan real-time intraday jam bursa IDX.
    - Melakukan loop scan setiap ~3 menit selama sesi aktif (Sesi 1 atau Sesi 2).
    - Begitu ada saham yang memunculkan sinyal baru HARI INI (Dot Green, Scalp BUY, Golden Cross, MACD Bull),
      langsung kirim alert instan ke WhatsApp per emiten tersebut!
    - Anti-spam: Mencegah pengiriman berulang untuk sinyal yang sama di hari yang sama.
    - Pada akhir Sesi 1 (12:00 WIB / 11:30 WIB Jumat): Jalankan audit saham VIP yang sepi, simpan snapshot mid-day ke history.json & kirim rangkuman Sesi I ke WA.
    - Pada akhir Sesi 2 (15:50 WIB): Jalankan audit saham VIP yang sepi, perbarui history.json & kirim rangkuman penutupan harian WhatsApp.
    - Jika single_session=True (misal di GitHub Actions runner): Selesai saat sesi berakhir.
    """
    now_wib = datetime.datetime.now(WIB_TZ)
    alerted_keys = load_alerted_keys(now_wib)
    
    print("\n" + "═" * 70)
    print("🚀 MEMULAI ENGINE PEMANTAUAN REAL-TIME INTRADAY BURSA IDX")
    print(f"📅 Waktu Saat Ini : {now_wib.strftime('%A, %d %B %Y %H:%M:%S WIB')}")
    print(f"🛡️ Riwayat Anti-Spam Hari Ini: {len(alerted_keys)} sinyal tersimpan")
    print("═" * 70)

    # Mode Uji Coba: Langsung jalankan 1 siklus pemantauan
    if test_mode:
        print("🧪 [TEST MODE] Menjalankan 1 siklus scan intraday & memeriksa sinyal baru...")
        hasil = await run_daily_scan(send_wa=True, realtime_mode=True, alerted_keys=alerted_keys)
        print(f"✅ [TEST MODE] Selesai 1 siklus ({len(hasil)} saham).")
        return

    while True:
        now_wib = datetime.datetime.now(WIB_TZ)
        session_info = get_current_idx_session(now_wib)
        status = session_info["status"]
        session_name = session_info["name"]

        if status == "CLOSED":
            print(f"🛑 [{now_wib.strftime('%H:%M:%S WIB')}] {session_name}.")
            if single_session:
                if session_info.get("session") in ["WEEKEND", "HOLIDAY"]:
                    print(f"🛑 [BURSA LIBUR] Hari ini tidak ada sesi perdagangan aktif bursa IDX ({session_name}).")
                    print("🏁 Runner selesai dengan aman tanpa mengubah database web.")
                    break
                print("🌙 [DI LUAR JAM BURSA] Menjalankan 1x scan harian penuh & memperbarui database web...")
                await run_daily_scan(send_wa=True, realtime_mode=False)
                print("🏁 Selesai scan di luar jam bursa. Keluar dari runner.")
                break
            else:
                print("💤 Menunggu 60 detik sebelum memeriksa jam bursa kembali...")
                await asyncio.sleep(60)
                continue

        elif status == "BREAK":
            print(f"⏸️ [{now_wib.strftime('%H:%M:%S WIB')}] {session_name}.")
            if single_session:
                print("🍽️ [JAM ISTIRAHAT BURSA] Menjalankan 1x scan snapshot Sesi Siang & memperbarui database web...")
                await run_daily_scan(send_wa=True, realtime_mode=False)
                print("🏁 Selesai scan snapshot istirahat siang. Keluar dari runner.")
                break
            else:
                resume_time = session_info.get("resume_time")
                if resume_time:
                    target_dt = now_wib.replace(hour=resume_time.hour, minute=resume_time.minute, second=0, microsecond=0)
                    wait_sec = max(10, int((target_dt - now_wib).total_seconds()))
                    print(f"⏳ Istirahat bursa: Bot tidur selama {wait_sec // 60} menit hingga Sesi II dibuka ({resume_time.strftime('%H:%M')} WIB)...")
                    await asyncio.sleep(min(wait_sec, 300))
                else:
                    await asyncio.sleep(60)
                continue

        elif status == "OPEN":
            cur_session_type = session_info.get("session")
            end_time = session_info.get("end_time")
            print(f"\n🟢 [{now_wib.strftime('%H:%M:%S WIB')}] {session_name} SEDANG BERJALAN.")
            
            t_pass_start = time.time()
            hasil = await run_daily_scan(send_wa=True, realtime_mode=True, alerted_keys=alerted_keys)
            pass_dur = time.time() - t_pass_start
            
            # Periksa kembali waktu setelah scan selesai
            now_after = datetime.datetime.now(WIB_TZ)
            new_session = get_current_idx_session(now_after)
            
            # Transisi akhir Sesi 1 (Jam Istirahat Siang / Sholat Jumat)
            if cur_session_type == "SESI_1" and (new_session["session"] != "SESI_1" or now_after.time() >= end_time):
                print(f"\n🔔 [{now_after.strftime('%H:%M:%S WIB')}] SESI I TELAH BERAKHIR (JAM ISTIRAHAT).")
                
                # Audit Saham VIP yang sepi saat istirahat siang
                vip_audit_stocks = get_missing_vip_stocks(hasil)
                hasil_midday = list(hasil)
                if vip_audit_stocks:
                    print(f"🔍 [AUDIT ISTIRAHAT SIANG] Menemukan {len(vip_audit_stocks)} saham VIP sepi. Memeriksa grafik di TradingView untuk konfirmasi Red Dot / 3-Dot...")
                    hasil_audit_vip = await run_daily_scan(send_wa=False, realtime_mode=False, alerted_keys=alerted_keys, custom_stocks=vip_audit_stocks)
                    if hasil_audit_vip:
                        hasil_midday.extend(hasil_audit_vip)
                        print(f"✅ [AUDIT ISTIRAHAT SIANG] Selesai memeriksa {len(hasil_audit_vip)} saham VIP.")
                
                print("💾 Memperbarui data database web (snapshot mid-day & audit VIP)...")
                simpan_database_json(hasil_midday, now_after)
                print("📱 Mengirim Rangkuman Siang (Sesi I) ke WhatsApp...")
                saham_hunter_midday = [item for item in hasil if not item.get("stock", {}).get("is_vip_audit", False)]
                kirim_pesan_summary_wa(saham_hunter_midday, now_after, sesi_label="Istirahat Siang")
                if single_session:
                    print("🏁 Runner Sesi I selesai.")
                    break

            # Transisi akhir Sesi 2 (Penutupan Perdagangan / Closing)
            elif cur_session_type == "SESI_2" and (new_session["session"] != "SESI_2" or now_after.time() >= end_time):
                print(f"\n🔔 [{now_after.strftime('%H:%M:%S WIB')}] SESI II TELAH BERAKHIR (PENUTUPAN PASAR).")
                print("🔍 Menjalankan Audit & Perbaikan Saham VIP 3-Dot di penutupan pasar...")
                hasil_closing = await run_daily_scan(send_wa=False, realtime_mode=False, alerted_keys=alerted_keys, audit_vip=True)
                print("💾 Memperbarui database web penutupan & mengirim Rangkuman Penutupan WhatsApp...")
                simpan_database_json(hasil_closing, now_after)
                saham_hunter_closing = [item for item in hasil_closing if not item.get("stock", {}).get("is_vip_audit", False)]
                kirim_pesan_summary_wa(saham_hunter_closing, now_after, sesi_label="Penutupan Pasar")
                if single_session:
                    print("🏁 Runner Sesi II selesai.")
                    break

            # Sesi masih aktif: jeda interval sebelum putaran berikutnya
            else:
                INTERVAL_SECONDS = 180  # Loop setiap 3 menit
                sisa_jeda = max(10, int(INTERVAL_SECONDS - pass_dur))
                print(f"\n⏳ Selesai 1 siklus dalam {pass_dur:.1f} detik. Stand by {sisa_jeda} detik sebelum pemindaian berikutnya...")
                await asyncio.sleep(sisa_jeda)

def test_send_sample_alert():
    """Menguji format pengiriman alert instan (Bullish & Bearish) ke WhatsApp tujuan dengan simulasi jam bursa."""
    now_wib = datetime.datetime.now(WIB_TZ)
    trading_date = get_latest_trading_date(now_wib)
    # Gunakan timestamp jam bursa aktif pada sesi bursa aktif (trading_date)
    sample_candle_bull = datetime.datetime.combine(trading_date, datetime.time(10, 30), tzinfo=WIB_TZ)
    sample_candle_bear = datetime.datetime.combine(trading_date, datetime.time(14, 15), tzinfo=WIB_TZ)

    sample_stock = {"symbol": "SIMULASI-TES", "close": 1500, "change": 5.25}
    sample_tf = {
        "15": {
            "status": True,
            "dt": sample_candle_bull,
            "date": sample_candle_bull.strftime("%d %b %Y, %H:%M WIB"),
            "donalt": {
                "golden": {
                    "dt": sample_candle_bull,
                    "date": sample_candle_bull.strftime("%d %b %Y, %H:%M WIB"),
                    "price": 1450,
                    "gain_pct": 3.45
                }
            },
            "scalping": {
                "buy": {
                    "dt": sample_candle_bull,
                    "date": sample_candle_bull.strftime("%d %b %Y, %H:%M WIB"),
                    "gain_pct": 9.09
                }
            },
            "macd": {
                "bull": {
                    "dt": sample_candle_bull,
                    "date": sample_candle_bull.strftime("%d %b %Y, %H:%M WIB"),
                    "price": 1450
                }
            },
            "smc": {
                "demand": 1420,
                "supply": 1680,
                "status_7d": "⚪ Di Antara Demand & Supply"
            }
        }
    }
    dummy_keys = set()
    print("🧪 Mengirim contoh alert instan (Bullish) ke WhatsApp...")
    res1 = check_and_send_instant_alert(sample_stock, sample_tf, dummy_keys, now_wib, save_to_disk=False)
    print(f"Hasil pengiriman Bullish: {'Berhasil ✅' if res1 else 'Gagal ❌'}")

    sample_bearish_tf = {
        "60": {
            "status": False,
            "red_dot": {
                "status": True,
                "active": True,
                "dt": sample_candle_bear,
                "date": sample_candle_bear.strftime("%d %b %Y, %H:%M WIB")
            },
            "donalt": {
                "death": {
                    "dt": sample_candle_bear,
                    "date": sample_candle_bear.strftime("%d %b %Y, %H:%M WIB"),
                    "price": 1530
                }
            },
            "scalping": {
                "sell": {
                    "dt": sample_candle_bear,
                    "date": sample_candle_bear.strftime("%d %b %Y, %H:%M WIB"),
                    "price": 1530
                }
            },
            "macd": {
                "bear": {
                    "dt": sample_candle_bear,
                    "date": sample_candle_bear.strftime("%d %b %Y, %H:%M WIB"),
                    "price": 1530
                }
            },
            "smc": {
                "demand": 1420,
                "supply": 1680,
                "status_7d": "🔴 Breakdown Demand Area"
            }
        }
    }
    dummy_bearish_keys = set()
    print("🧪 Mengirim contoh alert instan (Bearish / Exit) ke WhatsApp...")
    res2 = check_and_send_bearish_alert(sample_stock, sample_bearish_tf, dummy_bearish_keys, now_wib, save_to_disk=False)
    print(f"Hasil pengiriman Bearish: {'Berhasil ✅' if res2 else 'Gagal ❌'}")

# ============================================================================
# MAIN LOOP SCHEDULER: JALAN SETIAP HARI PUKUL 16.21 WIB
# ============================================================================
def main():
    import signal
    def handle_exit_signal(sig, frame):
        print(f"\n[TERMINATION] Sinyal pembatalan diterima ({sig}). Menghentikan bot seketika...")
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, handle_exit_signal)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, handle_exit_signal)
    except Exception as e:
        print(f"[SIGNAL WARNING] Tidak dapat memasang signal handler: {e}")

    print("================================================================")
    print("🚀 BOT HUNTER + RALLY GOD (OKTOVAAAAA) DIAKTIFKAN")
    print(f"⏰ Jadwal Standar: Setiap hari pukul {JAM_SCAN_WIB:02d}:{MENIT_SCAN_WIB:02d} WIB")
    print("================================================================")
    
    # Argumen --limit untuk membatasi jumlah saham saat pengujian (contoh: --limit 5)
    global LIMIT_SAHAM_SCAN
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            try:
                LIMIT_SAHAM_SCAN = int(sys.argv[i + 1])
                print(f"🎯 Batas scan disetel ke {LIMIT_SAHAM_SCAN} saham (--limit {LIMIT_SAHAM_SCAN}).")
            except ValueError:
                pass

    # Argumen --test-alert untuk mengetes format WhatsApp
    if "--test-alert" in sys.argv:
        test_send_sample_alert()
        return

    # Argumen --realtime atau environment variable MODE=realtime untuk pemantauan intraday jam bursa
    if "--realtime" in sys.argv or os.environ.get("MODE") == "realtime":
        single_sess = ("--session" in sys.argv) or bool(os.environ.get("GITHUB_ACTIONS"))
        test_mode = ("--now" in sys.argv)
        asyncio.run(run_realtime_market_session(single_session=single_sess, test_mode=test_mode))
        return

    # Argumen --now untuk pengujian scan harian langsung 1x
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
            
            # Cek jadwal: Sabtu pukul 19:08 WIB, Senin-Jumat pukul 16:21 WIB
            is_saturday = (now_wib.weekday() == 5)
            target_jam = 19 if is_saturday else JAM_SCAN_WIB
            target_menit = 8 if is_saturday else MENIT_SCAN_WIB
            if (now_wib.hour == target_jam and 
                now_wib.minute >= target_menit and 
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
