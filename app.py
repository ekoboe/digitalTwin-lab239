"""
server.py — Flask Backend Ruang Rapat IoT
==========================================
Menghubungkan dashboard 3D (Three.js) dengan ESP32.

Endpoint:
  GET  /                    → Serve index.html (halaman utama)
  POST /api/sensor          → Terima data suhu & kelembapan dari ESP32
  GET  /api/sensor/latest   → Kirim data sensor terbaru ke dashboard
  POST /api/control         → Terima perintah kontrol dari dashboard
  GET  /api/control/state   → Kirim state perangkat terkini ke ESP32 / dashboard
"""

from flask import Flask, request, jsonify, send_from_directory
import math
import os
import threading
import time

# -----------------------------------------------------------------------
# INISIALISASI
# -----------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=BASE_DIR, static_url_path="")

# -----------------------------------------------------------------------
# STATE BERSAMA (thread-safe dengan lock)
# -----------------------------------------------------------------------
lock = threading.Lock()

sensor_data = {
    "temperature": 28.0,
    "humidity":    65.0,
    "alarm":       False,
    "alarm_reason": "",
    "timestamp":   time.time(),
}

device_state = {
    "lampu1": True,
    "lampu2": True,
    "lampu3": True,
    "acBos":  True,
    "acRapat": True,
    "layar":  True,
}

ALARM_TEMP     = 39.0
ALARM_HUMIDITY = 80.0

# -----------------------------------------------------------------------
# HELPER
# -----------------------------------------------------------------------
def cek_alarm(suhu, kelembapan):
    reasons = []
    if suhu >= ALARM_TEMP:
        reasons.append("Suhu dalam ruangan tinggi")
    if kelembapan >= ALARM_HUMIDITY:
        reasons.append("Kelembapan dalam ruangan terlalu tinggi")
    alarm = len(reasons) > 0
    reason = " & ".join(reasons) if reasons else ""
    return alarm, reason


def baca_body_json():
    """Ambil objek JSON; tolak body kosong, JSON rusak, atau tipe non-objek."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, (jsonify({"error": "Body harus berupa objek JSON yang valid"}), 400)
    return data, None


def angka_sensor(data, nama):
    """Validasi angka sensor dan cegah NaN/Infinity masuk ke state aplikasi."""
    value = data.get(nama)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"'{nama}' harus berupa angka")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"'{nama}' harus berupa angka finite")
    return value

# -----------------------------------------------------------------------
# ROUTES — Static Files
# -----------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(BASE_DIR, filename)

# -----------------------------------------------------------------------
# ROUTES — Sensor (dari ESP32)
# -----------------------------------------------------------------------
@app.route("/api/sensor", methods=["POST"])
def terima_sensor():
    """
    ESP32 POST data sensor ke sini setiap ~3 detik.
    Body JSON: { "temperature": float, "humidity": float, "alarm": bool }
    Response : state perangkat aktif (untuk relay ESP32)
    """
    data, error = baca_body_json()
    if error:
        return error

    try:
        suhu = angka_sensor(data, "temperature")
        kelembapan = angka_sensor(data, "humidity")
    except (TypeError, ValueError, OverflowError) as exc:
        return jsonify({"error": str(exc)}), 400

    alarm, reason = cek_alarm(suhu, kelembapan)

    with lock:
        sensor_data["temperature"] = suhu
        sensor_data["humidity"]    = kelembapan
        sensor_data["alarm"]       = alarm
        sensor_data["alarm_reason"] = reason
        sensor_data["timestamp"]   = time.time()
        # Salin state perangkat untuk dikirim balik ke ESP32
        state_copy = dict(device_state)

    print(f"[Sensor] {suhu:.1f}°C  {kelembapan:.0f}%"
          + (f"  ⚠ ALARM: {reason}" if alarm else ""))

    return jsonify(state_copy)

@app.route("/api/sensor/latest", methods=["GET"])
def sensor_terbaru():
    """
    Dashboard JS polling ke sini setiap ~2 detik untuk update UI.
    Response: data sensor + state alarm
    """
    with lock:
        data = dict(sensor_data)
    return jsonify(data)

# -----------------------------------------------------------------------
# ROUTES — Control (dari Dashboard JS)
# -----------------------------------------------------------------------
@app.route("/api/control", methods=["POST"])
def kontrol_perangkat():
    """
    Dashboard JS POST perintah toggle perangkat.
    Body JSON: { "device": "lampu1", "state": true }
    Response : state lengkap semua perangkat
    """
    data, error = baca_body_json()
    if error:
        return error

    device = data.get("device")
    state = data.get("state")

    valid_devices = {"lampu1", "lampu2", "lampu3", "acBos", "acRapat", "layar"}
    if not isinstance(device, str) or device not in valid_devices:
        return jsonify({"error": f"Device '{device}' tidak dikenal"}), 400
    if not isinstance(state, bool):
        return jsonify({"error": "'state' harus berupa boolean true atau false"}), 400

    with lock:
        device_state[device] = state
        state_copy = dict(device_state)

    print(f"[Control] {device} → {'ON' if state else 'OFF'}")
    return jsonify(state_copy)

@app.route("/api/control/state", methods=["GET"])
def state_perangkat():
    """
    Kirim state semua perangkat (bisa dipakai dashboard atau ESP32 polling).
    """
    with lock:
        state_copy = dict(device_state)
    return jsonify(state_copy)

# -----------------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------------
if __name__ == "__main__":
    host = "0.0.0.0"
    port = 5000
    print("=" * 50)
    print(" Flask Server — Ruang Rapat IoT")
    print(f" Berjalan di  : http://{host}:{port}")
    print(f" Buka browser : http://localhost:{port}")
    print("=" * 50)
    app.run(host=host, port=port, debug=False, threaded=True)
