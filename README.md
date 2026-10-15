# 🤖 Agentic AI Trading Hunter - RallyGod Scanner (IDX)

Bot otomatis pemantau saham **Bursa Efek Indonesia (IDX)** berbasis **TradingView Screener HUNTER** dan indikator **(人•ᴗ•)RallyGood** (Dot Green Multi-Timeframe: Daily, 1 Jam, 15 Menit) dengan pengiriman 1 kali notifikasi rangkuman harian ke **WhatsApp via Fonnte**.

---

## 🚀 Fitur Utama
1. **Screener Hunter Otomatis (Persis Sesuai TradingView)**:
   - Memfilter saham Indonesia (IDX) dengan rentang harga Rp 10 – Rp 1.000.
   - Volume di atas rata-rata 10 hari (*Volume > Avg Vol 10D*).
   - Volume di atas Pre-market Volume minimal 500% (*Vol above Pre-mkt vol by 500% or more*).
   - Menghasilkan tepat **153 saham Hunter**.
2. **Pemeriksaan Multi-Timeframe (1 Bulan Terakhir)**:
   - Memeriksa **Daily (1D)**, **1 Jam (1H)**, dan **15 Menit (15M)** langsung dari engine data internal TradingView.
   - Mendeteksi apakah muncul titik hijau (*Dot Green*) khas `(人•ᴗ•)RallyGood` dalam rentang 30 hari ke belakang.
3. **Peringatan & Kategori Khusus (Anti-Spam Layar HP)**:
   - 🔥 **3 Timeframe**: Ditandai 1 kali di atas kategori dengan `🟢 ANALISA SAHAM INI !!! 🟢`.
   - ⚡ **2 Timeframe**: Ditandai 1 kali di atas kategori dengan `🟡 PANTAU SAHAM INI !!! 🟡`.
   - Tidak ada pengulangan tulisan peringatan di setiap saham, sehingga tampilan sangat bersih dan tidak membingungkan di layar HP.
4. **Perhitungan Kenaikan Riil Sejak Dot Green Muncul**:
   - Persentase di samping harga bukan lagi kenaikan 1 hari hari ini, melainkan **kenaikan riil sejak sinyal Dot Green pertama kali muncul**:
     - Untuk 3 Timeframe: Menghitung kenaikan dari Dot 1D dan Dot 1H (misal: `(1D: +12.50% | 1H: +5.20%)`).
     - Untuk 2 Timeframe: Menghitung kenaikan dari Dot 1D dan/atau Dot 1H yang aktif (misal: `(1H: +18.89%)`).
   - Memberikan sinyal instan apakah saham tersebut baru saja *breakout* (masih fresh) atau sudah reli tinggi.
5. **Analisa SMC Supply & Demand Ganda (1D & 1H) + Breakout/Breakdown 7 Hari**:
   - Mendeteksi level **Supply Terdekat** (Resisten) dan **Demand Terdekat** (Support) langsung dari indikator *Ultimate SMC Suite* asli untuk **kedua timeframe sekaligus: Daily (1D) & 1 Jam (1H)**.
   - Menghitung jarak persentase eksak: berapa % lagi menuju Supply dan berapa % harga berada di atas Demand di masing-masing timeframe.
   - Mendeteksi status **Breakout Supply**, **Breakdown Demand**, atau riwayat struktur **BOS (Break of Structure) & CHoCH (Change of Character)** dalam rentang waktu **1 minggu (7 hari) terakhir**.
6. **Pembersihan Otomatis Screenshot**:
   - Tidak membebani storage disk, semua temporary screenshot langsung dibersihkan otomatis.
7. **Pencatatan Laporan & Notifikasi WhatsApp**:
   - File teks rekapitulasi seluruh 153 saham tersimpan di `reports/laporan_hunter_YYYYMMDD.txt` dan folder `Downloads`.
   - Mengirimkan rangkuman rapi ke WhatsApp via Fonnte setiap pukul **19.00 WIB** setiap malam.
8. **Cloud-Ready (Laptop Bisa Dimatikan)**:
   - Mendukung deployment di Cloud Server / VPS Linux menggunakan Docker.

---

## 🛠️ Cara Menjalankan

### Pilihan 1: Di Server / VPS (Rekomendasi Utama - Laptop Bisa Mati)
Di server VPS Anda, cukup jalankan perintah satu baris:
```bash
docker compose up -d --build
```
- Bot akan berjalan 24 jam nonstop di background.
- Setiap pukul **19.00 WIB**, bot akan otomatis bangun, scan semua saham, mencatat file laporan, dan mengirim WhatsApp.

Untuk melihat log aktivitas bot di server:
```bash
docker compose logs -f
```

Untuk menghentikan bot:
```bash
docker compose down
```

---

### Pilihan 2: Dijalankan Langsung di Laptop (Windows)
Jika Anda ingin menjalankannya di laptop:

1. **Jalankan Scan Sekarang & Langsung Kirim ke WhatsApp**:
   ```bash
   python bot_hunter.py --now --wa
   ```
2. **Jalankan Scan Sekarang (Hanya Simpan ke Notepad)**:
   ```bash
   python bot_hunter.py --now
   ```
3. **Jalankan Standby Rutin (Otomatis Setiap Malam Jam 19.00 WIB)**:
   ```bash
   python bot_hunter.py
   ```

---

## 📁 Struktur File
- `bot_hunter.py` : Script utama pemindai screener, browser otomatis, dan pengirim WhatsApp.
- `docker-compose.yml` : Konfigurasi container Docker server (1-klik run).
- `Dockerfile` : Blueprint image Playwright Chromium server.
- `requirements.txt` : Daftar dependensi Python.
- `reports/` : Folder tempat file laporan scan dan tangkapan layar chart disimpan.
