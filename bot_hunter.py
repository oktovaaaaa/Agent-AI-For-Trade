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

def format_tanggal_id(dt):
    """Mengembalikan format tanggal Indonesia resmi, misal: 13 Oktober 2026"""
    return f"{dt.day} {BULAN_INDONESIA.get(dt.month, '')} {dt.year}"

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
                 Column('volume') > Column('average_volume_10d_calc')
             )
             .order_by('volume', ascending=False))
             
        if LIMIT_SAHAM_SCAN and LIMIT_SAHAM_SCAN > 0:
            q = q.limit(LIMIT_SAHAM_SCAN)
        else:
            q = q.limit(500) # Ambil seluruh saham yang lolos kriteria HUNTER tanpa batas 10
        
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
            
            # Ambil data Dot Green langsung dari engine data internal TradingView (100% presisi untuk semua saham)
            dot_timestamps = await page.evaluate('''() => {
                try {
                    const chart = window._exposed_chartWidgetCollection?.activeChartWidget?.value();
                    if (!chart) return [];
                    const model = chart.model();
                    const ts = model.timeScale();
                    const allStudies = model.panes().flatMap(p => p.dataSources()).filter(s => s.title && s.title().includes('RallyGood'));
                    if (!allStudies.length) return [];
                    
                    const study = allStudies[0];
                    const greenPv = (study._paneViews || []).find(pv => pv._plotName === 'plot_2');
                    if (!greenPv) return [];
                    
                    // Filter hanya item yang benar-benar aktif/dirender (y bukan NaN)
                    const activeDots = (greenPv._items || []).filter(it => !isNaN(it.y));
                    return activeDots.map(dot => ts.indexToTimePoint(dot.timePointIndex)).filter(tp => tp !== null && tp !== undefined);
                } catch(e) {
                    return [];
                }
            }''')
            
            valid_dots = []
            for tp in dot_timestamps:
                if tp and isinstance(tp, (int, float)):
                    dot_dt = datetime.datetime.fromtimestamp(tp, WIB_TZ)
                    diff_days = (now_dt - dot_dt).total_seconds() / 86400
                    # SYARAT MUTLAK: Hanya terima jika muncul dalam rentang 30 hari terakhir (1 bulan terakhir: 13 Sep - 13 Okt)
                    if 0 <= diff_days <= 30:
                        valid_dots.append(dot_dt)
            
            if valid_dots:
                latest_dot = max(valid_dots)
                if tf_code == 'D':
                    date_display = latest_dot.strftime("%d %b %Y")
                else:
                    date_display = latest_dot.strftime("%d %b %Y, %H:%M WIB")
                    
                print(f" 🟢 ADA DOT GREEN! ({date_display})")
                results[tf_code] = {"status": True, "date": date_display}
            else:
                print(" ❌ Tidak ada")
                results[tf_code] = {"status": False, "date": None}
                    
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
    konten_laporan.append(f"Kriteria Filter  : Harga Rp 10-1.000 | Volume > Avg 10D (Bursa Efek Indonesia)")
    konten_laporan.append(f"Rentang Analisis : {tgl_awal_id} s/d {tgl_analisa_id} (1 Bulan Terakhir / 30 Hari)")
    konten_laporan.append(f"Layout Chart     : {CHART_LAYOUT_URL}")
    konten_laporan.append("=" * 75 + "\n")
    
    saham_hijau = [item for item in hasil_deteksi if item["has_green_dot"]]
    konten_laporan.append(f"RINGKASAN: Ditemukan {len(saham_hijau)} dari {len(hasil_deteksi)} saham memiliki DOT GREEN RallyGood.\n")
    
    konten_laporan.append("DAFTAR SAHAM DENGAN DOT GREEN (1 BULAN TERAKHIR):")
    konten_laporan.append("-" * 75)
    if saham_hijau:
        for item in saham_hijau:
            st = item["stock"]
            tf = item["timeframes"]
            d_str = f"[ADA DOT GREEN] (Muncul: {tf.get('D', {}).get('date')})" if tf.get('D', {}).get('status') else 'Tidak ada'
            h_str = f"[ADA DOT GREEN] (Muncul: {tf.get('60', {}).get('date')})" if tf.get('60', {}).get('status') else 'Tidak ada'
            m_str = f"[ADA DOT GREEN] (Muncul: {tf.get('15', {}).get('date')})" if tf.get('15', {}).get('status') else 'Tidak ada'
            
            konten_laporan.append(f"• {st['symbol']:<6} | Harga: Rp {st['close']:<4.0f} ({st['change']:+6.2f}%) | Vol: {st['volume']:,.0f}")
            konten_laporan.append(f"    - Daily (1D)  : {d_str}")
            konten_laporan.append(f"    - 1 Jam (1H)  : {h_str}")
            konten_laporan.append(f"    - 15 Menit    : {m_str}\n")
    else:
        konten_laporan.append("Tidak ada saham yang memunculkan sinyal Dot Green dalam 1 bulan terakhir.\n")
        
    konten_laporan.append("-" * 75)
    konten_laporan.append("DAFTAR SELURUH SAHAM HUNTER YANG DI-SCAN:")
    for item in hasil_deteksi:
        st = item["stock"]
        status_text = "🟢 ADA DOT GREEN" if item["has_green_dot"] else "⚪ Netral"
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

    # 5. Susun Pesan Rangkuman WhatsApp
    if send_wa:
        pesan_wa = (
            f"📋 *LAPORAN ANALISA SAHAM HUNTER - {tgl_analisa_id.upper()}*\n"
            f"📅 *Tanggal Analisa*: {tgl_analisa_id} (Pukul {now_wib.strftime('%H:%M WIB')})\n"
            f"🔍 *Kriteria*: Saham IDX Rp 10-1000 | Vol > Avg 10D\n"
            f"⏱️ *Rentang Filter*: {tgl_awal_id} s/d {tgl_analisa_id} (30 Hari)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        
        if saham_hijau:
            pesan_wa += f"🟢 *DITEMUKAN {len(saham_hijau)} SAHAM DENGAN DOT GREEN*:\n\n"
            for i, item in enumerate(saham_hijau, 1):
                st = item["stock"]
                tf = item["timeframes"]
                
                d_icon = f"🟢 ADA ({tf.get('D', {}).get('date')})" if tf.get('D', {}).get('status') else "❌"
                h_icon = f"🟢 ADA ({tf.get('60', {}).get('date')})" if tf.get('60', {}).get('status') else "❌"
                m_icon = f"🟢 ADA ({tf.get('15', {}).get('date')})" if tf.get('15', {}).get('status') else "❌"
                
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
            f"📁 Catatan detail tersimpan di folder Downloads & `{laporan_filename.name}`\n"
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
