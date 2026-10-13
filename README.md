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
3. **Peringatan Khusus 3 Timeframe (Golden Signal)**:
   - Jika suatu saham memiliki sinyal Dot Green lengkap di ketiga timeframe sekaligus (15M + 1H + 1D), bot otomatis menandainya dengan:
     `🟢 ANALISA SAHAM INI !!! 🟢`
     dan menempatkannya di urutan prioritas teratas.
4. **Pembersihan Otomatis Screenshot**:
   - Tidak membebani storage disk, semua temporary screenshot langsung dibersihkan otomatis.
5. **Pencatatan Laporan & Notifikasi WhatsApp**:
   - File teks tersimpan di `reports/laporan_hunter_YYYYMMDD.txt` dan folder `Downloads`.
   - Mengirimkan rangkuman rapi ke WhatsApp via Fonnte setiap pukul **19.00 WIB** setiap malam.
6. **Cloud-Ready (Laptop Bisa Dimatikan)**:
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
