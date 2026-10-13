# 🤖 Agentic AI Trading Hunter - RallyGod Scanner (IDX)

Bot otomatis pemantau saham **Bursa Efek Indonesia (IDX)** berbasis **TradingView Screener HUNTER** dan indikator **(人•ᴗ•)RallyGood** (Dot Green Multi-Timeframe: Daily, 1 Jam, 15 Menit) dengan pengiriman 1 kali notifikasi rangkuman harian ke **WhatsApp via Fonnte**.

---

## 🚀 Fitur Utama
1. **Screener Hunter Otomatis**:
   - Memfilter saham Indonesia (IDX) dengan rentang harga Rp 10 – Rp 1.000.
   - Volume di atas rata-rata 10 hari (*Volume > Avg Vol 10D*).
2. **Pemeriksaan Multi-Timeframe (1 Bulan Terakhir)**:
   - Memeriksa **Daily (1D)**, **1 Jam (1H)**, dan **15 Menit (15M)**.
   - Mendeteksi apakah muncul titik hijau (*Dot Green*) khas `(人•ᴗ•)RallyGood` dalam 30 hari ke belakang.
3. **Pencatatan Laporan & Anti-Spam**:
   - Hasil disimpan ke file teks/Notepad di folder `reports/laporan_hunter_YYYYMMDD.txt`.
   - Mengirimkan **1 kali rangkuman rapi** ke WhatsApp pada pukul **19.00 WIB** setiap malam.
4. **Cloud-Ready (Laptop Bisa Dimatikan)**:
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

1. **Jalankan Uji Coba Langsung (Scan Sekarang Juga)**:
   ```bash
   python bot_hunter.py --now
   ```
2. **Jalankan Standby Rutin (Menunggu Jam 19.00 WIB Setiap Hari)**:
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
