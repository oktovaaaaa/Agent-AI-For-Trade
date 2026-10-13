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
LIMIT_SAHAM_SCAN = 30           # Jumlah saham top volume dari Screener HUNTER

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

# ============================================================================
# FUNSI KIRIM NOTIFIKASI WHATSAPP VIA FONNTE (1X PENGIRIMAN)
# ============================================================================
def kirim_whatsapp(pesan):
    """Mengirim pesan rangkuman ke WhatsApp via API Fonnte."""
    if not FONNTE_TOKEN or FONNTE_TOKEN == "MASUKKAN_TOKEN_FONNTE_DI_SINI":
        print("[WARNING] Token Fonnte belum diisi. Pesan tidak terkirim.")
        return False
        
    url = "https://api.fonnte.com/send"
    payload = {
        "target": NOMOR_WHATSAPP_TUJUAN,
        "message": pesan,
        "countryCode": "62"
    }
    headers = {"Authorization": FONNTE_TOKEN}
    try:
        response = requests.post(url, headers=headers, data=payload, timeout=15)
        res_json = response.json()
        if res_json.get("status"):
            print(f"[{datetime.datetime.now(WIB_TZ).strftime('%H:%M:%S WIB')}] ✅ Rangkuman berhasil dikirim ke WhatsApp!")
            return True
        else:
            print(f"[ERROR] Gagal kirim WA Fonnte: {res_json}")
            return False
    except Exception as e:
        print(f"[EXCEPT] Error koneksi Fonnte: {e}")
        return False

# ============================================================================
# TAHAP 1: SCREENER HUNTER (SAHAM ID Rp 10-1000 & VOLUME > AVG 10D)
# ============================================================================
def get_hunter_stocks():
    """Mengambil saham IDX dari TradingView Screener sesuai kriteria HUNTER."""
    print(f"\n[{datetime.datetime.now(WIB_TZ).strftime('%Y-%m-%d %H:%M:%S WIB')}] 🔎 Memulai Screener HUNTER Saham IDX...")
    try:
        q = (Query()
             .set_markets('indonesia')
             .select('name', 'close', 'volume', 'volume|10d', 'change')
             .where(
                 Column('close').between(10, 1000),
                 Column('volume') > Column('volume|10d')
             )
             .order_by('volume', ascending=False)
             .limit(LIMIT_SAHAM_SCAN))
        
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
                'vol_10d': float(row['volume|10d']),
                'change': float(row['change'])
            })
        print(f"✅ Ditemukan {len(tickers)} saham Hunter potensial untuk dianalisis.")
        return tickers
    except Exception as e:
        print(f"[ERROR] Screener TradingView gagal: {e}")
        return []

# ============================================================================
# TAHAP 2: DETEKSI VISUAL/PIXEL DOT GREEN PADA INDIKATOR (人•ᴗ•)RallyGood
# ============================================================================
def detect_green_dot_in_image(image_path):
    """
    Menganalisis screenshot sub-pane RallyGood untuk mendeteksi keberadaan
    lingkaran hijau (Dot Green) khas RallyGood di candle 1 bulan terakhir.
    """
    try:
        img = Image.open(image_path).convert("RGB")
        width, height = img.size
        
        # Fokuskan area sub-pane bawah (di mana RallyGood berada: 55% - 95% tinggi chart)
        crop_top = int(height * 0.55)
        crop_bottom = int(height * 0.95)
        
        # Fokuskan 70% area horizontal kanan (merepresentasikan 1 bulan terakhir)
        crop_left = int(width * 0.20)
        crop_right = int(width * 0.95)
        
        cropped = img.crop((crop_left, crop_top, crop_right, crop_bottom))
        pixels = np.array(cropped)
        
        # Karakteristik warna hijau terang (Dot Green) TradingView:
        # Green tinggi (180-255), Red rendah (<100), Blue sedang/rendah (<160)
        r = pixels[:, :, 0]
        g = pixels[:, :, 1]
        b = pixels[:, :, 2]
        
        green_mask = (g > 180) & (r < 110) & (b < 170) & (g > r + 80)
        green_pixel_count = np.sum(green_mask)
        
        # Sebuah lingkaran dot green biasanya memiliki minimal 15-20 piksel hijau terang
        if green_pixel_count >= 15:
            return True, int(green_pixel_count)
        return False, 0
    except Exception as e:
        print(f"Error analisa pixel {image_path}: {e}")
        return False, 0

# ============================================================================
# TAHAP 3: BROWSER OTOMATIS MEMERIKSA CHART 15M, 1H, 1D
# ============================================================================
async def scan_stock_rallygood(page, stock_info):
    """
    Membuka chart TradingView untuk saham tertentu dan memeriksa
    keberadaan Dot Green RallyGood pada timeframe 1D, 1H, dan 15M.
    """
    symbol = stock_info['symbol']
    results = {}
    
    for tf in TIMEFRAMES:
        tf_code = tf['code']
        tf_name = tf['name']
        
        chart_url = f"{CHART_LAYOUT_URL}?symbol=IDX%3A{symbol}&interval={tf['interval']}"
        print(f"   ↳ Mengecek {symbol} [{tf_name}]...", end="", flush=True)
        
        try:
            await page.goto(chart_url, wait_until="domcontentloaded", timeout=30000)
            # Tunggu 4 detik agar canvas indikator RallyGood selesai me-render candle
            await asyncio.sleep(4.5)
            
            # Simpan screenshot chart untuk verifikasi
            ss_path = REPORTS_DIR / "screenshots" / f"{symbol}_{tf_code}.png"
            await page.screenshot(path=str(ss_path))
            
            # Deteksi Dot Green pada screenshot
            has_green_dot, pixel_count = detect_green_dot_in_image(ss_path)
            
            if has_green_dot:
                print(f" 🟢 ADA DOT GREEN! ({pixel_count} px)")
                results[tf_code] = {"status": True, "pixels": pixel_count}
            else:
                print(" ❌ Tidak ada")
                results[tf_code] = {"status": False, "pixels": 0}
                # Hapus screenshot jika tidak ada dot green agar hemat penyimpanan
                if ss_path.exists():
                    ss_path.unlink()
                    
        except Exception as e:
            print(f" ⚠️ Error: {e}")
            results[tf_code] = {"status": False, "pixels": 0, "error": str(e)}
            
    return results

# ============================================================================
# TAHAP 4: EKSEKUSI UTAMA (SCAN HARIAN JAM 19.00 WIB)
# ============================================================================
async def run_daily_scan():
    now_wib = datetime.datetime.now(WIB_TZ)
    date_str = now_wib.strftime("%Y%m%d")
    date_display = now_wib.strftime("%d/%m/%Y")
    
    print("\n" + "="*70)
    print(f"🚀 MEMULAI SCAN HARIAN HUNTER - RALLY GOD [{date_display} {now_wib.strftime('%H:%M WIB')}]")
    print("="*70)
    
    # 1. Ambil saham lolos kriteria Screener HUNTER
    hunter_stocks = get_hunter_stocks()
    if not hunter_stocks:
        kirim_whatsapp(f"ℹ️ *SCAN HUNTER {date_display}*\nTidak ada saham IDX Rp 10-1000 yang lolos kriteria volume hari ini.")
        return
        
    hasil_deteksi = []
    
    # 2. Jalankan Headless Chromium dengan Playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ]
        )
        
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
        
    # 4. Tulis hasil lengkap ke File Laporan (Format Notepad / Teks)
    laporan_filename = REPORTS_DIR / f"laporan_hunter_{date_str}.txt"
    with open(laporan_filename, "w", encoding="utf-8") as f:
        f.write("="*75 + "\n")
        f.write(f"LAPORAN SCAN MALAM SAHAM HUNTER - INDIKATOR RALLY GOD (IDX)\n")
        f.write(f"Waktu Scan       : {now_wib.strftime('%d-%m-%Y %H:%M:%S WIB')}\n")
        f.write(f"Kriteria Filter  : Harga Rp 10-1.000 | Volume > Avg 10D (Bursa Efek Indonesia)\n")
        f.write(f"Rentang Analisis : 1 Bulan Terakhir (30 Hari)\n")
        f.write(f"Layout Chart     : {CHART_LAYOUT_URL}\n")
        f.write("="*75 + "\n\n")
        
        saham_hijau = [item for item in hasil_deteksi if item["has_green_dot"]]
        f.write(f"RINGKASAN: Ditemukan {len(saham_hijau)} dari {len(hasil_deteksi)} saham memiliki DOT GREEN RallyGood.\n\n")
        
        f.write("DAFTAR SAHAM DENGAN DOT GREEN (1 BULAN TERAKHIR):\n")
        f.write("-" * 75 + "\n")
        if saham_hijau:
            for item in saham_hijau:
                st = item["stock"]
                tf = item["timeframes"]
                f.write(f"• {st['symbol']:<6} | Harga: Rp {st['close']:<4.0f} ({st['change']:+6.2f}%) | Vol: {st['volume']:,.0f}\n")
                f.write(f"    - Daily (1D)  : {'[ADA DOT GREEN]' if tf.get('D', {}).get('status') else 'Tidak ada'}\n")
                f.write(f"    - 1 Jam (1H)  : {'[ADA DOT GREEN]' if tf.get('60', {}).get('status') else 'Tidak ada'}\n")
                f.write(f"    - 15 Menit    : {'[ADA DOT GREEN]' if tf.get('15', {}).get('status') else 'Tidak ada'}\n\n")
        else:
            f.write("Tidak ada saham yang memunculkan sinyal Dot Green dalam 1 bulan terakhir.\n\n")
            
        f.write("-" * 75 + "\n")
        f.write("DAFTAR SELURUH SAHAM HUNTER YANG DI-SCAN HARI INI:\n")
        for item in hasil_deteksi:
            st = item["stock"]
            status_text = "🟢 ADA DOT GREEN" if item["has_green_dot"] else "⚪ Netral"
            f.write(f"- {st['symbol']:<6} : Rp {st['close']:<4.0f} ({st['change']:+6.2f}%) -> {status_text}\n")
            
    print(f"\n📄 Laporan lengkap berhasil disimpan ke file: {laporan_filename}")
    
    # 5. Susun Pesan Rangkuman WhatsApp (CUKUP 1 KALI PENGIRIMAN)
    saham_hijau = [item for item in hasil_deteksi if item["has_green_dot"]]
    
    pesan_wa = (
        f"📋 *RANGKUMAN SCAN MALAM - HUNTER RALLY GOD*\n"
        f"📅 *Tanggal*: {date_display} (Pukul {now_wib.strftime('%H:%M WIB')})\n"
        f"🔍 *Kriteria*: Saham IDX Rp 10-1000 | Vol > Avg 10D\n"
        f"⏱️ *Rentang*: Riwayat 1 Bulan Terakhir\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    
    if saham_hijau:
        pesan_wa += f"🟢 *DITEMUKAN {len(saham_hijau)} SAHAM DENGAN DOT GREEN*:\n\n"
        for i, item in enumerate(saham_hijau, 1):
            st = item["stock"]
            tf = item["timeframes"]
            
            d_icon = "🟢 ADA" if tf.get('D', {}).get('status') else "❌"
            h_icon = "🟢 ADA" if tf.get('60', {}).get('status') else "❌"
            m_icon = "🟢 ADA" if tf.get('15', {}).get('status') else "❌"
            
            pesan_wa += (
                f"{i}. *{st['symbol']}* | Rp {st['close']:.0f} ({st['change']:+.2f}%)\n"
                f"   • Daily (1D) : {d_icon}\n"
                f"   • 1 Jam (1H) : {h_icon}\n"
                f"   • 15 Menit   : {m_icon}\n"
                f"   • Volume     : {st['volume']:,.0f}\n\n"
            )
    else:
        pesan_wa += "ℹ️ Tidak ditemukan saham dengan sinyal Dot Green RallyGood malam ini.\n\n"
        
    pesan_wa += (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 *Total Di-scan*: {len(hasil_deteksi)} Saham\n"
        f"📁 Catatan detail tersimpan di: `{laporan_filename.name}`\n"
        f"🌐 _Bot Agent Okto 24 Jam Otomatis_"
    )
    
    # Kirim 1x WhatsApp
    kirim_whatsapp(pesan_wa)

# ============================================================================
# MAIN LOOP SCHEDULER: JALAN SETIAP MALAM PUKUL 19.00 WIB
# ============================================================================
def main():
    print("================================================================")
    print("🚀 BOT HUNTER + RALLY GOD 19.00 WIB (OKTOVAAAAA) DIAKTIFKAN")
    print(f"⏰ Jadwal Rutin: Setiap malam pukul {JAM_SCAN_WIB:02d}:{MENIT_SCAN_WIB:02d} WIB")
    print("================================================================")
    
    # Argumen --now untuk pengujian langsung tanpa menunggu jam 19.00
    if len(sys.argv) > 1 and sys.argv[1] == "--now":
        print("[TEST MODE] Menjalankan scan langsung saat ini...")
        asyncio.run(run_daily_scan())
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
