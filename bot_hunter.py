import time
import datetime
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from tradingview_screener import Query, Column

# ============================================================================
# KONFIGURASI BOT & TOKEN
# ============================================================================
# Ganti dengan Token Fonnte Anda (atau biarkan jika diset lewat Environment Variable FONNTE_TOKEN)
FONNTE_TOKEN = "MASUKKAN_TOKEN_FONNTE_DI_SINI"
NOMOR_WHATSAPP_TUJUAN = "6282111144710"  # Nomor WhatsApp penerima notifikasi

INTERVAL_SCAN_MENIT = 15  # Durasi jeda scan (setiap 15 menit)
SENT_SIGNALS_CACHE = {}   # Simpan riwayat sinyal agar tidak spam

# ============================================================================
# FUNSI KIRIM NOTIFIKASI WHATSAPP VIA FONNTE
# ============================================================================
def kirim_whatsapp(pesan):
    """Mengirim pesan notifikasi ke WhatsApp melalui API Fonnte."""
    if FONNTE_TOKEN == "MASUKKAN_TOKEN_FONNTE_DI_SINI":
        print("[WARNING] Token Fonnte belum diisi. Pesan berikut batal dikirim ke WA:\n", pesan)
        return False
        
    url = "https://api.fonnte.com/send"
    payload = {
        "target": NOMOR_WHATSAPP_TUJUAN,
        "message": pesan,
        "countryCode": "62"
    }
    headers = {
        "Authorization": FONNTE_TOKEN
    }
    try:
        response = requests.post(url, headers=headers, data=payload, timeout=10)
        res_json = response.json()
        if res_json.get("status"):
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ✅ Notifikasi WA berhasil dikirim!")
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
    """Mengambil daftar saham IDX dari TradingView Screener sesuai kriteria HUNTER."""
    print(f"\n[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔎 Memulai Screener HUNTER Saham Indonesia...")
    try:
        # Menggunakan TradingView Screener Query untuk pasar indonesia (idx)
        q = (Query()
             .set_markets('indonesia')
             .select('name', 'close', 'volume', 'volume|10d', 'change')
             .where(
                 Column('close').between(10, 1000),
                 Column('volume') > Column('volume|10d')
             )
             .order_by('volume', ascending=False)
             .limit(100))
        
        df_screener = q.get_scanner_data()[1]
        if df_screener.empty:
            print("ℹ️ Tidak ada saham yang memenuhi kriteria Screener HUNTER saat ini.")
            return []
            
        tickers = []
        for idx, row in df_screener.iterrows():
            ticker_name = row['ticker']  # contoh: IDX:DEFI
            symbol = ticker_name.split(':')[-1] if ':' in ticker_name else ticker_name
            tickers.append({
                'symbol': symbol,
                'yf_ticker': f"{symbol}.JK",
                'close': row['close'],
                'volume': row['volume'],
                'vol_10d': row['volume|10d'],
                'change': row['change']
            })
        print(f"✅ Ditemukan {len(tickers)} saham lolos filter Screener HUNTER.")
        return tickers
    except Exception as e:
        print(f"[ERROR] Screener TradingView gagal: {e}")
        return []

# ============================================================================
# TAHAP 2: HITUNG INDIKATOR EMA CROSS SUITE & DONALT TOOLKIT (OKTOVAAAAA)
# ============================================================================
def analyze_stock_indicators(stock_info):
    """Menghitung EMA 8,20,50,200 & DonAlt Pivot Levels pada data candle 1H/1D."""
    symbol = stock_info['symbol']
    yf_symbol = stock_info['yf_ticker']
    
    try:
        # Download data histori candle dari Yahoo Finance (1 jam / 1 hari)
        df = yf.download(yf_symbol, period="60d", interval="1h", progress=False)
        if df.empty or len(df) < 200:
            # Fallback ke daily jika hourly kurang
            df = yf.download(yf_symbol, period="1y", interval="1d", progress=False)
            
        if df.empty or len(df) < 50:
            return None

        # Format dataframe jika multi-index
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df['Close']
        high = df['High']
        low = df['Low']
        vol = df['Volume']

        # Hitung EMAs (8, 20, 50, 200)
        df['EMA8'] = close.ewm(span=8, adjust=False).mean()
        df['EMA20'] = close.ewm(span=20, adjust=False).mean()
        df['EMA50'] = close.ewm(span=50, adjust=False).mean()
        df['EMA200'] = close.ewm(span=200, adjust=False).mean()

        # Deteksi Crossover pada candle terbaru (bar[-1] vs bar[-2])
        c_curr = close.iloc[-1]
        c_prev = close.iloc[-2]
        
        ema8_curr = df['EMA8'].iloc[-1]
        ema8_prev = df['EMA8'].iloc[-2]
        
        ema20_curr = df['EMA20'].iloc[-1]
        ema20_prev = df['EMA20'].iloc[-2]
        
        ema50_curr = df['EMA50'].iloc[-1]
        ema50_prev = df['EMA50'].iloc[-2]
        
        ema200_curr = df['EMA200'].iloc[-1]
        ema200_prev = df['EMA200'].iloc[-2]

        signals = []

        # 1. Fast Cross (EMA 8 Cross Over EMA 20)
        if (ema8_prev <= ema20_prev) and (ema8_curr > ema20_curr):
            signals.append("⚡ FAST CROSS (EMA 8 > EMA 20)")

        # 2. Mid Cross (EMA 20 Cross Over EMA 50)
        if (ema20_prev <= ema50_prev) and (ema20_curr > ema50_curr):
            signals.append("🟡 MID CROSS (EMA 20 > EMA 50)")

        # 3. Golden Cross (EMA 50 Cross Over EMA 200)
        if (ema50_prev <= ema200_prev) and (ema50_curr > ema200_curr):
            signals.append("🚀 GOLDEN CROSS (EMA 50 > EMA 200)")

        # 4. DonAlt Pivot High (Patah Trend / Breakout Level)
        lookback = 20
        pivot_high = high.iloc[-lookback:-1].max()
        if c_prev <= pivot_high and c_curr > pivot_high:
            signals.append(f"📈 PATAH TREND / BREAKOUT LEVEL (Tembus Rp {pivot_high:.0f})")

        if signals:
            return {
                'symbol': symbol,
                'price': c_curr,
                'change': stock_info['change'],
                'volume': stock_info['volume'],
                'signals': signals
            }
    except Exception as e:
        # print(f"Error analisa {symbol}: {e}")
        pass
    return None

# ============================================================================
# MAIN LOOP MONITORING 24 JAM NONSTOP
# ============================================================================
def main():
    print("================================================================")
    print("🚀 BOT SAHAM HUNTER + EMA DONALT SUITE [OKTOVAAAAA] DIGERAKKAN")
    print("================================================================")
    
    # Kirim notifikasi tes saat bot pertama kali aktif
    kirim_whatsapp("🤖 *BOT SAHAM HUNTER AKTIF!*\nBot 24 jam nonstop siap memantau sinyal Golden Cross & Patah Trend Saham IDX untuk Anda.")
    
    while True:
        try:
            hunter_stocks = get_hunter_stocks()
            found_signals = []
            
            for stock in hunter_stocks:
                result = analyze_stock_indicators(stock)
                if result:
                    sym = result['symbol']
                    sig_key = f"{sym}_{result['signals'][0]}"
                    
                    # Cek cache anti-spam (supaya sinyal tidak terkirim terus menerus tiap 15 mnt)
                    now_ts = time.time()
                    if sig_key not in SENT_SIGNALS_CACHE or (now_ts - SENT_SIGNALS_CACHE[sig_key]) > 86400: # reset 24j
                        SENT_SIGNALS_CACHE[sig_key] = now_ts
                        found_signals.append(result)

            # Kirim notifikasi jika ada sinyal baru
            for item in found_signals:
                signals_str = "\n".join([f"• {s}" for s in item['signals']])
                pesan_wa = (
                    f"🚨 *SINYAL SAHAM HUNTER DETECTED!*\n\n"
                    f"📌 *Saham*: {item['symbol']}\n"
                    f"💰 *Harga*: Rp {item['price']:.0f} ({item['change']:.2f}%)\n"
                    f"📊 *Volume*: {item['volume']:,}\n\n"
                    f"⚡ *Sinyal Indikator*:\n{signals_str}\n\n"
                    f"⏰ *Waktu*: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M WIB')}\n"
                    f"🌐 _Di-scan otomatis oleh Bot Agent Okto 24 Jam_"
                )
                kirim_whatsapp(pesan_wa)

        except Exception as e:
            print(f"[MAIN ERROR] {e}")

        print(f"😴 Menunggu {INTERVAL_SCAN_MENIT} menit untuk scan berikutnya...")
        time.sleep(INTERVAL_SCAN_MENIT * 60)

if __name__ == "__main__":
    main()
