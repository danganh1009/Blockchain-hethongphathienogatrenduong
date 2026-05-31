#!/usr/bin/env python3
"""
🌐 Web Server để hiển thị kết quả phát hiện ổ gà
Truy cập: http://localhost:5000
"""

from flask import Flask, render_template, jsonify, send_file, Response, request
import cv2
import os
import json
import glob
import threading
import time
import hashlib
from pathlib import Path

DEFAULT_SEPOLIA_CONTRACT_ADDRESS = "0x97A093BB0563AC74080291b7eAFE0582638c35Ad"

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
DETECTIONS_DIR = BASE_DIR / "detections"

app = Flask(
    __name__,
    template_folder=str(TEMPLATES_DIR),
    static_folder=str(STATIC_DIR),
    static_url_path="/static",
)

latest_frame = None
latest_frame_lock = threading.Lock()
STREAM_FPS = 10
STREAM_QUALITY = 70
STREAM_MAX_WIDTH = 960


def update_latest_frame(frame):
    """Cập nhật frame mới nhất để stream lên web."""
    global latest_frame
    if frame is None:
        return
    with latest_frame_lock:
        latest_frame = frame.copy()


def get_detections():
    """Lấy danh sách tất cả detections"""
    detections = []
    
    if not DETECTIONS_DIR.exists():
        return detections
    
    # Tìm tất cả file JSON
    json_files = glob.glob(str(DETECTIONS_DIR / "detection_*.json"))
    
    for json_file in sorted(json_files, reverse=True):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                detections.append(data)
        except Exception as e:
            print(f"⚠️ Lỗi đọc {json_file}: {e}")
    
    return detections


def compute_detection_hash(image_bytes, timestamp_display, location):
    """Tạo SHA-256 từ ảnh + thời gian + vị trí."""
    payload = (
        image_bytes
        + b"|"
        + timestamp_display.encode("utf-8")
        + b"|"
        + f"{location['lat']},{location['lon']}".encode("utf-8")
    )
    return hashlib.sha256(payload).hexdigest()


def get_blockchain_client():
    rpc_url = os.getenv("SEPOLIA_RPC_URL")
    contract_address = os.getenv("SEPOLIA_CONTRACT_ADDRESS", DEFAULT_SEPOLIA_CONTRACT_ADDRESS)

    if not rpc_url:
        return None

    try:
        from web3 import Web3
    except Exception:
        return None

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        return None

    contract = w3.eth.contract(
        address=w3.to_checksum_address(contract_address),
        abi=CONTRACT_ABI,
    )
    return w3, contract


def get_stats():
    """Lấy thống kê"""
    detections = get_detections()
    
    total_detections = sum(d.get('detection_count', 0) for d in detections)
    total_images = len(detections)
    latest_detection = detections[0] if detections else None

    return {
        'total_images': total_images,
        'total_detections': total_detections,
        'latest_detection': latest_detection.get('timestamp') if latest_detection else None,
        'latest_detection_iso': latest_detection.get('timestamp_iso') if latest_detection else None
    }


@app.route('/')
def index():
    """Trang chính"""
    stats = get_stats()
    return render_template('index.html', **stats)


@app.route('/blockchain')
def blockchain_page():
    """Trang blockchain"""
    return render_template('blockchain.html')


@app.route('/api/detections')
def api_detections():
    """API trả về danh sách detections"""
    detections = get_detections()
    return jsonify(detections)


@app.route('/api/stats')
def api_stats():
    """API trả về thống kê"""
    stats = get_stats()
    return jsonify(stats)


@app.route('/image/<filename>')
def serve_image(filename):
    """Phục vụ ảnh"""
    file_path = DETECTIONS_DIR / filename

    if file_path.exists():
        return send_file(str(file_path), mimetype="image/jpeg")
    return "File not found", 404


def _generate_mjpeg_stream():
    """Tạo stream MJPEG từ frame hiện tại."""
    min_interval = 1.0 / STREAM_FPS
    last_sent = 0.0
    while True:
        with latest_frame_lock:
            frame = latest_frame.copy() if latest_frame is not None else None

        if frame is None:
            time.sleep(0.05)
            continue

        now = time.time()
        if now - last_sent < min_interval:
            time.sleep(0.005)
            continue

        if STREAM_MAX_WIDTH and frame.shape[1] > STREAM_MAX_WIDTH:
            scale = STREAM_MAX_WIDTH / frame.shape[1]
            new_size = (STREAM_MAX_WIDTH, int(frame.shape[0] * scale))
            frame = cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)

        ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), STREAM_QUALITY])
        if not ok:
            continue

        jpg = buffer.tobytes()
        last_sent = now
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
        )


@app.route('/video_feed')
def video_feed():
    """Stream video realtime."""
    return Response(_generate_mjpeg_stream(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/health")
def health_check():
    """Simple health check endpoint."""
    return jsonify({"status": "ok"})


@app.route("/api/verify")
def api_verify():
    """Xác thực hash trên blockchain"""
    image_file = request.args.get("image_file")
    if not image_file:
        return jsonify({"ok": False, "error": "missing image_file"}), 400

    json_path = DETECTIONS_DIR / image_file.replace(".jpg", ".json")
    if not json_path.exists():
        return jsonify({"ok": False, "error": "detection not found"}), 404

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        image_path = DETECTIONS_DIR / data["image_file"]
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        location = data.get("location")
        timestamp_display = data.get("timestamp")
        if not location or not timestamp_display:
            return jsonify({"ok": False, "error": "missing data"}), 400

        local_hash = compute_detection_hash(image_bytes, timestamp_display, location)
        chain = get_blockchain_client()
        if not chain:
            return jsonify({"ok": False, "error": "blockchain not configured"}), 500

        w3, contract = chain
        on_chain = contract.functions.hasHash(bytes.fromhex(local_hash)).call()

        return jsonify({
            "ok": True,
            "local_hash": local_hash,
            "on_chain": bool(on_chain),
            "tx_hash": data.get("tx_hash")
        })
    except Exception as e:
        return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}"}), 500


CONTRACT_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "dataHash", "type": "bytes32"},
            {"internalType": "string", "name": "imageFile", "type": "string"},
        ],
        "name": "storeHash",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "dataHash", "type": "bytes32"}
        ],
        "name": "hasHash",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
]


if __name__ == '__main__':
    print("\n" + "="*60)
    print("🌐 WEB SERVER - PHÁT HIỆN Ổ GÀ")
    print("="*60)
    print("\n📱 Truy cập: http://localhost:5000")
    print("⏹️  Nhấn Ctrl+C để dừng server\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
