"""Live feed: memancarkan kejadian bot ke kantor 3D Aranter secara realtime.

Bot  --POST {LIVE_PUSH_URL} (header X-Live-Token)-->  server/analyst_bridge.py (repo Agent-AI-Office)
                                                     <--GET /api/live--  kantor 3D

Aman untuk produksi:
- Tidak aktif sama sekali kalau env LIVE_PUSH_URL / LIVE_TOKEN kosong.
- Pengiriman di thread latar (batch tiap ~1 detik, timeout 4 detik). Gagal kirim = dibuang diam-diam,
  bot tidak pernah melambat atau error karena kantor 3D offline.
"""
import json
import os
import queue
import threading
import time
import urllib.request

LIVE_PUSH_URL = os.environ.get("LIVE_PUSH_URL", "").strip()
LIVE_TOKEN = os.environ.get("LIVE_TOKEN", "").strip()
ENABLED = bool(LIVE_PUSH_URL and LIVE_TOKEN)

_q = queue.Queue(maxsize=5000)
_started = False
_pending = [0]  # kejadian yang belum selesai dikirim
_lock = threading.Lock()


def _sender():
    while True:
        batch = [_q.get()]
        t_end = time.time() + 1.0
        while len(batch) < 200 and time.time() < t_end:
            try:
                batch.append(_q.get(timeout=max(0.01, t_end - time.time())))
            except queue.Empty:
                break
        try:
            req = urllib.request.Request(
                LIVE_PUSH_URL, method="POST",
                data=json.dumps({"events": batch}, ensure_ascii=False, default=str).encode("utf-8"),
                headers={"Content-Type": "application/json", "X-Live-Token": LIVE_TOKEN,
                         "User-Agent": "AranterBot-LiveFeed/1.0"},
            )
            urllib.request.urlopen(req, timeout=4).read()
        except Exception:  # noqa: BLE001 — kantor 3D offline tidak boleh mengganggu bot
            pass
        finally:
            with _lock:
                _pending[0] -= len(batch)


def emit(event_type, **data):
    """Kirim 1 kejadian, mis. emit("stock", worker=2, stock={...}). Tidak pernah melempar error."""
    global _started
    if not ENABLED:
        return
    try:
        if not _started:
            with _lock:
                if not _started:
                    threading.Thread(target=_sender, daemon=True, name="live-feed").start()
                    _started = True
        with _lock:
            _pending[0] += 1
        try:
            _q.put_nowait({"t": event_type, "ts": time.time(), **data})
        except queue.Full:
            with _lock:
                _pending[0] -= 1
    except Exception:  # noqa: BLE001
        pass


def flush(timeout=5.0):
    """Tunggu antrean terkirim (dipanggil sebelum runner selesai)."""
    if not ENABLED:
        return
    t_end = time.time() + timeout
    while _pending[0] > 0 and time.time() < t_end:
        time.sleep(0.1)


def stock_entry(stock, tf_results):
    """Format sama dengan entri saham di docs/data/history.json (lihat simpan_database_json)."""
    tf = tf_results or {}
    clean_tf = {}
    for k in ("D", "60", "45"):
        v = tf.get(k, {}) or {}
        clean_tf[k] = {key: v.get(key) for key in ("date", "dot_close", "gain_pct", "red_dot", "donalt", "scalping", "smc", "macd")}
        clean_tf[k]["status"] = bool(v.get("status", False))
    close = float(stock.get("close", 0) or 0)
    cg = sum(1 for k in ("D", "60", "45") if clean_tf[k]["status"])
    return {
        "symbol": stock.get("symbol"), "name": stock.get("name", stock.get("symbol")),
        "close": close, "high": float(stock.get("high", close) or close), "low": float(stock.get("low", close) or close),
        "change": stock.get("change"), "volume": stock.get("volume"),
        "count_green": cg, "has_green_dot": cg > 0, "is_vip_audit": bool(stock.get("is_vip_audit", False)),
        "timeframes": clean_tf,
    }
