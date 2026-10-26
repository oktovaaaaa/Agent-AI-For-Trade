@echo off
title Bot Hunter IDX Real-Time Intraday Engine (24/7 Standby)
echo ======================================================================
echo    BOT HUNTER RALLY GOD - REAL-TIME INTRADAY ENGINE (BURSA IDX)
echo ======================================================================
echo Mode pemantauan pasar tanpa henti:
echo - Sesi I   : 09:00 - 12:00 WIB (Jumat: 09:00 - 11:30 WIB)
echo - Istirahat: Bot tidur hemat CPU
echo - Sesi II  : 13:30 - 16:00 WIB (Jumat: 14:00 - 16:00 WIB)
echo - Scan Sore: 16:05 WIB (Pasca Tutup Pasar)
echo - Diluar jam bursa: Bot standby otomatis
echo.
python bot_hunter.py --realtime
pause
