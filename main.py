#!/usr/bin/env python3
"""
🛣️ Hệ thống Phát Hiện Ổ Gà Trên Đường Bằng Deep Learning
Hỗ trợ nhận diện từ webcam, file video, hoặc DroidCam
"""

import cv2
import os
import glob
import time
import argparse
import urllib.request
import numpy as np
import json
import threading
import random
import hashlib
from ultralytics import YOLO
from gtts import gTTS
from datetime import datetime

# Load environment variables từ .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv không cài, sẽ sử dụng biến môi trường hệ thống

DEFAULT_SEPOLIA_CONTRACT_ADDRESS = "0x97A093BB0563AC74080291b7eAFE0582638c35Ad"

try:
    from playsound import playsound
    HAS_PLAYSOUND = True
except ImportError:
    HAS_PLAYSOUND = False

try:
    import telegram
    from telegram import Bot, InputFile
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False

try:
    import asyncio
    HAS_ASYNCIO = True
except ImportError:
    HAS_ASYNCIO = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class TelegramNotifier:
    """Gửi thông báo phát hiện ổ gà lên Telegram"""
    
    def __init__(self):
        """Khởi tạo Telegram notifier"""
        self.enabled = False
        self.token = None
        self.chat_id = None
        self.pending_threads = []
        
        if not HAS_TELEGRAM:
            print("ℹ️  Telegram tắt (thiếu thư viện python-telegram-bot)")
            print("   Cài đặt: pip install python-telegram-bot")
            return
        
        # Lấy token và chat_id từ environment variables
        self.token = os.getenv("TELEGRAM_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if not self.token or not self.chat_id:
            print("ℹ️  Telegram tắt (thiếu TELEGRAM_TOKEN hoặc TELEGRAM_CHAT_ID)")
            print("   Vui lòng cấu hình environment variables")
            return
        
        try:
            self.enabled = True
            print("✅ Telegram notifier sẵn sàng")
        except Exception as e:
            print(f"⚠️ Lỗi khởi tạo Telegram: {type(e).__name__}: {e}")
            self.enabled = False
    
    def send_detection_async(self, image_path, detection_info):
        """Gửi thông báo detection lên Telegram (async)"""
        if not self.enabled:
            return
        
        thread = threading.Thread(
            target=self._send_detection,
            args=(image_path, detection_info),
            daemon=False,
        )
        self.pending_threads.append(thread)
        thread.start()
    
    def wait_for_pending(self, timeout=10):
        """Chờ tất cả tin nhắn pending gửi xong"""
        if not self.pending_threads:
            return
        for thread in list(self.pending_threads):
            thread.join(timeout=timeout)
        self.pending_threads = [t for t in self.pending_threads if t.is_alive()]
    
    def _send_detection(self, image_path, detection_info):
        """Gửi thông báo detection lên Telegram"""
        try:
            if not os.path.exists(image_path):
                print(f"⚠️ Tệp ảnh không tồn tại: {image_path}")
                return
            
            # Tạo caption với thông tin detection
            caption = self._build_caption(detection_info)
            
            # Sử dụng requests API trực tiếp (không async)
            if HAS_REQUESTS:
                self._send_via_requests(image_path, caption)
            else:
                print("⚠️ Cần cài: pip install requests")
        except Exception as e:
            print(f"⚠️ Lỗi gửi Telegram: {type(e).__name__}: {e}")
    
    def _send_via_requests(self, image_path, caption):
        """Gửi ảnh qua Telegram API bằng requests library"""
        url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
        
        with open(image_path, 'rb') as photo:
            files = {'photo': photo}
            data = {
                'chat_id': self.chat_id,
                'caption': caption,
                'parse_mode': 'HTML'
            }
            
            try:
                response = requests.post(url, files=files, data=data, timeout=10)
                result = response.json()
                
                if result.get('ok'):
                    pass  # Detection sent to Telegram
                else:
                    print(f"⚠️ Lỗi Telegram API: {result.get('description', 'Unknown error')}")
            except Exception as e:
                print(f"⚠️ Lỗi gửi qua requests: {type(e).__name__}: {e}")
    
    def _build_caption(self, detection_info):
        """Xây dựng caption cho tin nhắn Telegram"""
        timestamp = detection_info.get('timestamp', 'N/A')
        count = detection_info.get('detection_count', 0)
        location = detection_info.get('location', {})
        lat = location.get('lat', 'N/A')
        lon = location.get('lon', 'N/A')
        
        caption = (
            f"🚨 <b>PHÁT HIỆN Ổ GÀ</b>\n\n"
            f"📍 <b>Vị trí:</b> {lat}, {lon}\n"
            f"⏰ <b>Thời gian:</b> {timestamp}\n"
            f"🔍 <b>Số lượng:</b> {count} ổ gà"
        )
        return caption


class DetectionLogger:
    """Lưu thông tin phát hiện ổ gà để hiển thị trên web"""
    
    def __init__(self, output_dir="detections", telegram_notifier=None):
        """
        Khởi tạo logger
        
        Args:
            output_dir: Thư mục lưu ản⚠️ Lỗi Telegram API: Bad Request: chat not foundh detection
            telegram_notifier: Đối tượng TelegramNotifier (tùy chọn)
        """
        self.output_dir = output_dir
        self.last_notification_time = 0
        self.notification_interval = 5  # Lưu tối đa 1 detection mỗi 5 giây
        self.total_detections = 0
        self._sim_lat = 10.7758
        self._sim_lon = 106.7004
        self.blockchain = BlockchainClient()
        self.telegram_notifier = telegram_notifier
        
        # Tạo thư mục nếu chưa có
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
    
    def save_detection(self, frame, detection_count, frame_number):
        """
        Lưu detection info và ảnh
        
        Args:
            frame: Frame hiện tại
            detection_count: Số lượng ổ gà phát hiện
            frame_number: Số thứ tự frame
        
        Returns:
            True nếu lưu thành công, False nếu không
        """
        # Kiểm tra khoảng cách thời gian giữa các lưu
        current_time = time.time()
        if current_time - self.last_notification_time < self.notification_interval:
            return False
        
        try:
            # Tạo timestamp
            now = datetime.now()
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            timestamp_display = now.strftime("%d/%m/%Y %H:%M:%S")
            timestamp_iso = now.isoformat()

            # Encode ảnh thành JPEG bytes để lưu + hash
            ok, buffer = cv2.imencode(".jpg", frame)
            if not ok:
                print("⚠️ Không thể encode ảnh để lưu detection")
                return False
            image_bytes = buffer.tobytes()
            
            # Lưu ảnh
            image_path = os.path.join(self.output_dir, f"detection_{timestamp}.jpg")
            with open(image_path, "wb") as img_file:
                img_file.write(image_bytes)

            location = self._simulate_location()
            data_hash = compute_detection_hash(image_bytes, timestamp_display, location)
            
            # Lưu thông tin vào JSON
            info = {
                "timestamp": timestamp_display,
                "timestamp_iso": timestamp_iso,
                "frame_number": frame_number,
                "detection_count": detection_count,
                "image_file": f"detection_{timestamp}.jpg",
                "location": location,
                "data_hash": data_hash,
                "tx_hash": None
            }
            
            json_path = os.path.join(self.output_dir, f"detection_{timestamp}.json")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(info, f, ensure_ascii=False, indent=2)

            if self.blockchain.enabled:
                self.blockchain.submit_hash_async(data_hash, info["image_file"], json_path)
            
            # Gửi thông báo lên Telegram
            if self.telegram_notifier and self.telegram_notifier.enabled:
                self.telegram_notifier.send_detection_async(image_path, info)
            
            self.total_detections += detection_count
            self.last_notification_time = current_time
            # Detection saved
            
            return True
        except Exception as e:
            print(f"⚠️ Lỗi lưu detection: {e}")
            return False

    def _simulate_location(self):
        """Giả lập GPS bằng random walk nhẹ."""
        self._sim_lat += random.uniform(-0.00005, 0.00005)
        self._sim_lon += random.uniform(-0.00005, 0.00005)
        return {
            "lat": round(self._sim_lat, 6),
            "lon": round(self._sim_lon, 6)
        }


def compute_detection_hash(image_bytes, timestamp_display, location):
    """Tạo SHA-256 từ ảnh + thời gian + vị trí."""
    # Ghép ảnh + thời gian + vị trí thành một payload duy nhất để băm.
    # Nếu bất kỳ thành phần nào thay đổi (ảnh/thời gian/vị trí) thì hash sẽ khác.
    payload = (
        image_bytes
        + b"|"
        + timestamp_display.encode("utf-8")
        + b"|"
        + f"{location['lat']},{location['lon']}".encode("utf-8")
    )
    return hashlib.sha256(payload).hexdigest()


class BlockchainClient:
    """Gửi hash lên smart contract trên Sepolia."""

    def __init__(self):
        self.enabled = False
        self.pending_threads = []
        self.nonce_lock = threading.Lock()
        self.next_nonce = None
        self._init_client()

    def _init_client(self):
        self.rpc_url = os.getenv("SEPOLIA_RPC_URL")
        self.private_key = os.getenv("SEPOLIA_PRIVATE_KEY")
        self.contract_address = os.getenv("SEPOLIA_CONTRACT_ADDRESS", DEFAULT_SEPOLIA_CONTRACT_ADDRESS)

        if not self.rpc_url or not self.private_key:
            # Thiếu cấu hình thì tắt blockchain, phần còn lại vẫn chạy bình thường.
            print("ℹ️ Blockchain tắt (thiếu SEPOLIA_RPC_URL/SEPOLIA_PRIVATE_KEY)")
            return

        # Validate private key format
        private_key_clean = self.private_key.replace("0x", "").strip()
        if len(private_key_clean) != 64:
            print(f"❌ SEPOLIA_PRIVATE_KEY format error: expected 64 hex chars, got {len(private_key_clean)}")
            print("   Private key must be 64 hexadecimal characters (0-9, a-f)")
            print("   You may have set it to your wallet address instead of private key")
            return
        
        try:
            int(private_key_clean, 16)  # Validate it's valid hex
        except ValueError:
            print(f"❌ SEPOLIA_PRIVATE_KEY contains non-hexadecimal characters")
            print("   Valid hex: 0-9, a-f only")
            return

        try:
            from web3 import Web3
        except Exception:
            print("⚠️ Thiếu thư viện web3. Cài: pip install web3")
            return

        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        if not self.w3.is_connected():
            # RPC không kết nối được (URL sai, mạng sai, bị chặn...).
            print(f"⚠️ Không kết nối được RPC Sepolia: {self.rpc_url}")
            return

        self.account = self.w3.eth.account.from_key(self.private_key)
        # Kết nối contract bằng ABI + address để gọi hàm on-chain.
        self.contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(self.contract_address),
            abi=CONTRACT_ABI,
        )
        self.enabled = True
        print("✅ Blockchain client sẵn sàng")

    def submit_hash_async(self, data_hash, image_file, json_path):
        # Gửi giao dịch trên background thread để không làm chậm xử lý video.
        thread = threading.Thread(
            target=self._submit_hash,
            args=(data_hash, image_file, json_path),
            daemon=False,
        )
        self.pending_threads.append(thread)
        thread.start()

    def wait_for_pending(self, timeout=10):
        # Chờ các giao dịch đang gửi hoàn tất trước khi thoát chương trình.
        if not self.pending_threads:
            return
        for thread in list(self.pending_threads):
            thread.join(timeout=timeout)
        self.pending_threads = [t for t in self.pending_threads if t.is_alive()]

    def _get_next_nonce(self):
        # Dùng nonce tăng dần để tránh trùng nonce khi gửi nhiều tx liên tiếp.
        with self.nonce_lock:
            if self.next_nonce is None:
                self.next_nonce = self.w3.eth.get_transaction_count(self.account.address)
            nonce = self.next_nonce
            self.next_nonce += 1
            return nonce

    def _submit_hash(self, data_hash, image_file, json_path):
        try:
            nonce = self._get_next_nonce()
            tx = self.contract.functions.storeHash(
                bytes.fromhex(data_hash),
                image_file,
            ).build_transaction({
                "from": self.account.address,
                "nonce": nonce,
                "gas": 150000,
                "maxFeePerGas": self.w3.to_wei("20", "gwei"),
                "maxPriorityFeePerGas": self.w3.to_wei("1", "gwei"),
            })
            # Ký giao dịch bằng private key của ví Sepolia.
            signed = self.account.sign_transaction(tx)
            raw_tx = signed.rawTransaction if hasattr(signed, "rawTransaction") else signed.raw_transaction
            # Gửi raw transaction lên mạng Sepolia.
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            tx_hex = self.w3.to_hex(tx_hash)
            # Lưu tx_hash vào JSON để truy vết giao dịch sau này.
            self._update_json_tx(json_path, tx_hex)
            print(f"🔗 Đã gửi hash lên blockchain: {tx_hex}")
        except Exception as e:
            print(f"⚠️ Gửi blockchain thất bại: {type(e).__name__}: {e}")

    def _update_json_tx(self, json_path, tx_hash):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["tx_hash"] = tx_hash
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ Không thể cập nhật tx_hash: {e}")


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


class MJPEGStreamReader:
    """Đọc MJPEG stream từ URL (ví dụ: DroidCam)"""
    
    def __init__(self, url):
        self.url = url
        self.stream = None
        self.frame_buffer = b''
        self.is_open = False
        self._connect()
    
    def _connect(self):
        """Kết nối tới MJPEG stream"""
        try:
            print(f"🔗 Kết nối tới: {self.url}")
            req = urllib.request.Request(self.url, headers={'User-Agent': 'Mozilla/5.0'})
            self.stream = urllib.request.urlopen(req, timeout=10)
            
            # Kiểm tra content-type
            content_type = self.stream.headers.get('Content-Type', '')
            print(f"📺 Content-Type: {content_type}")
            
            self.is_open = True
            print("✅ Kết nối MJPEG stream thành công!")
        except urllib.error.URLError as e:
            print(f"⚠️ Lỗi kết nối URL: {e.reason}")
            self.is_open = False
        except Exception as e:
            print(f"⚠️ Lỗi kết nối MJPEG: {type(e).__name__}: {e}")
            self.is_open = False
    
    def read(self):
        """Đọc frame từ stream"""
        if not self.is_open:
            return False, None
        
        try:
            # Tìm boundary của frame MJPEG
            while True:
                chunk = self.stream.read(4096)
                if not chunk:
                    print("❌ Stream kết thúc")
                    self.is_open = False
                    return False, None
                
                self.frame_buffer += chunk
                
                # Tìm JPEG frame (bắt đầu bằng FFD8 và kết thúc bằng FFD9)
                a = self.frame_buffer.find(b'\xff\xd8')
                b = self.frame_buffer.find(b'\xff\xd9')
                
                if a != -1 and b != -1:
                    jpg = self.frame_buffer[a:b+2]
                    self.frame_buffer = self.frame_buffer[b+2:]
                    
                    # Decode JPEG thành frame
                    frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if frame is not None:
                        return True, frame
                    else:
                        print("⚠️ Decode JPEG thất bại")
                        continue
        except Exception as e:
            print(f"⚠️ Lỗi đọc frame: {type(e).__name__}: {e}")
            self.is_open = False
            return False, None
    
    def isOpened(self):
        """Kiểm tra stream có mở không"""
        return self.is_open
    
    def release(self):
        """Đóng stream"""
        if self.stream:
            try:
                self.stream.close()
            except:
                pass
        self.is_open = False
    
    def get(self, prop):
        """Mock OpenCV API"""
        if prop == cv2.CAP_PROP_FPS:
            return 30  # Giả sử 30 FPS
        elif prop == cv2.CAP_PROP_FRAME_WIDTH:
            return 1280
        elif prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return 720
        return 0


class PotholeDetector:
    """Lớp xử lý phát hiện ổ gà"""
    
    def __init__(self, weight_path=None, confidence_threshold=0.5, detection_logger=None):
        """
        Khởi tạo detector
        
        Args:
            weight_path: Đường dẫn tới file best.pt (nếu None, sẽ tìm tự động)
            confidence_threshold: Ngưỡng tin cậy (0-1)
            detection_logger: Đối tượng DetectionLogger (tùy chọn)
        """
        self.confidence_threshold = confidence_threshold
        self.last_alert_time = 0
        self.alert_interval = 5  # Khoảng cách giữa các cảnh báo (giây)
        self.detection_logger = detection_logger
        
        # Tạo file âm thanh cảnh báo nếu chưa có
        self._prepare_alert_audio()
        
        # Load model YOLO
        self.model = self._load_model(weight_path)
    
    def _prepare_alert_audio(self):
        """Tạo file âm thanh cảnh báo"""
        if not os.path.exists("canhbao.mp3"):
            print("📢 Tạo file âm thanh cảnh báo...")
            try:
                tts = gTTS("Cảnh báo! Phía trước có ổ gà, hãy giảm tốc độ!", lang="vi")
                tts.save("canhbao.mp3")
                print("✅ Đã tạo file canhbao.mp3")
            except Exception as e:
                print(f"⚠️ Lỗi tạo âm thanh: {e}")
    
    def _load_model(self, weight_path=None):
        """Tải mô hình YOLO"""
        if weight_path and os.path.exists(weight_path):
            model_path = weight_path
        else:
            # Tìm file best.pt mới nhất từ script directory
            script_dir = os.path.dirname(os.path.abspath(__file__))
            search_pattern = os.path.join(script_dir, "runs/detect/**/weights/best.pt")
            
            weight_paths = glob.glob(search_pattern, recursive=True)
            
            if not weight_paths:
                # Cố gắng tìm từ thư mục hiện tại
                alt_search_pattern = "runs/detect/**/weights/best.pt"
                weight_paths = glob.glob(alt_search_pattern, recursive=True)
            
            if not weight_paths:
                raise FileNotFoundError(
                    f"⚠️ Không tìm thấy file best.pt trong:\n"
                    f"  - {search_pattern}\n"
                    f"Vui lòng kiểm tra thư mục runs/detect/ hoặc dùng --weights"
                )
            
            model_path = max(weight_paths, key=os.path.getmtime)
        
        print(f"✅ Đang tải mô hình: {model_path}")
        return YOLO(model_path)
    
    def detect_and_draw(self, frame, frame_number=0):
        """
        Phát hiện ổ gà và vẽ lên frame
        
        Args:
            frame: Frame input
            frame_number: Số thứ tự frame
        
        Returns:
            Tuple: (frame_with_detections, detected_count)
        """
        results = self.model(frame, verbose=False)
        detected_count = 0
        
        for result in results:
            boxes = result.boxes.xyxy.cpu().numpy()
            confs = result.boxes.conf.cpu().numpy()
            
            for box, conf in zip(boxes, confs):
                if conf > self.confidence_threshold:
                    detected_count += 1
                    x1, y1, x2, y2 = map(int, box)
                    
                    # Vẽ hình chữ nhật
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                    
                    # Vẽ text "O GA!" và độ tin cậy
                    label = f"O GA! {conf:.2f}"
                    cv2.putText(frame, label, (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        
        # Lưu detection nếu có phát hiện
        if detected_count > 0 and self.detection_logger:
            self.detection_logger.save_detection(frame, detected_count, frame_number)
        
        return frame, detected_count
    
    def trigger_alert(self):
        """Phát cảnh báo"""
        current_time = time.time()
        if current_time - self.last_alert_time > self.alert_interval:
            print("⚠️ CẢNH BÁO: Phía trước có ổ gà! Hãy giảm tốc độ!")
            if HAS_PLAYSOUND and os.path.exists("canhbao.mp3"):
                try:
                    playsound("canhbao.mp3", block=False)
                except Exception as e:
                    print(f"⚠️ Lỗi phát âm thanh: {e}")
            self.last_alert_time = current_time


def parse_arguments():
    """Phân tích tham số dòng lệnh"""
    parser = argparse.ArgumentParser(
        description="🛣️ Hệ thống phát hiện ổ gà trên đường",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ví dụ cách sử dụng:
  python main.py --source 0                    # Sử dụng webcam mặc định
  python main.py --source 1                    # Sử dụng webcam thứ 2
  python main.py --source test1.mp4            # Sử dụng file video
  python main.py --source video.mp4 --conf 0.6 # File video với ngưỡng 60%
  
  # DroidCam (3 cách)
  python main.py --droidcam 192.168.1.5 4747  # Cách 1: --droidcam IP PORT
  python main.py --source http://192.168.1.5:4747/video  # Cách 2: URL trực tiếp
  python main.py --source droidcam:192.168.1.5:4747       # Cách 3: Format shortcut
        """
    )
    
    parser.add_argument(
        "--source",
        type=str,
        default="0",
        help="Nguồn input: số (webcam), file video, hoặc URL (default: 0)"
    )
    
    parser.add_argument(
        "--conf",
        type=float,
        default=0.5,
        help="Ngưỡng tin cậy từ 0 đến 1 (default: 0.5)"
    )
    
    parser.add_argument(
        "--weights",
        type=str,
        default=None,
        help="Đường dẫn tới file best.pt (nếu không, sẽ tìm tự động)"
    )
    
    parser.add_argument(
        "--skip-audio",
        action="store_true",
        help="Không phát âm thanh cảnh báo"
    )
    
    parser.add_argument(
        "--droidcam",
        nargs=2,
        metavar=("IP", "PORT"),
        help="Sử dụng DroidCam với IP và PORT (ví dụ: --droidcam 192.168.1.5 4747)"
    )

    parser.add_argument(
        "--no-web",
        action="store_true",
        help="Không khởi chạy giao diện web"
    )
    
    return parser.parse_args()


def start_web_server():
    """Khởi chạy web server trong background"""
    try:
        from web_server import app
    except Exception as e:
        print(f"⚠️ Không thể khởi chạy web server: {type(e).__name__}: {e}")
        return

    def _run():
        try:
            app.run(debug=False, host="0.0.0.0", port=5000, use_reloader=False)
        except OSError as e:
            print(f"⚠️ Web server không thể chạy: {e}")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


def check_url_reachable(url, timeout=3):
    """
    Kiểm tra URL có thể truy cập được không
    Cho MJPEG stream: thử kết nối trực tiếp tới endpoint
    """
    try:
        # Nếu là stream MJPEG, extract IP:port và thử kết nối
        if "/video" in url or "/mjpeg" in url or ":4747" in url:
            import socket
            # Extract IP và port từ URL (format: http://192.168.1.5:4747/video)
            try:
                netloc = url.split("://")[1].split("/")[0]  # "192.168.1.5:4747"
                if ":" in netloc:
                    ip, port = netloc.split(":")
                    port = int(port)
                else:
                    ip = netloc
                    port = 80
                
                print(f"🔍 Kiểm tra kết nối tới {ip}:{port}...")
                socket.create_connection((ip, port), timeout=timeout)
                return True
            except Exception as e:
                print(f"  ⚠️ Lỗi kết nối socket: {type(e).__name__}: {e}")
                return False
        
        # Nếu là URL bình thường, thử urlopen với HEAD request
        print(f"🔍 Kiểm tra URL: {url[:50]}...")
        req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'Mozilla/5.0'})
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except Exception as e:
        print(f"  ⚠️ Kiểm tra thất bại: {type(e).__name__}")
        return False


def parse_droidcam_source(source_arg):
    """
    Phân tích định dạng DroidCam shortcut: droidcam:192.168.1.5:4747
    
    Returns:
        URL nếu hợp lệ, None nếu không
    """
    if source_arg.startswith("droidcam:"):
        parts = source_arg.replace("droidcam:", "").split(":")
        if len(parts) >= 2:
            ip = parts[0]
            port = parts[1]
            return f"http://{ip}:{port}/video"
    return None


def get_video_source(source_arg, droidcam_args=None):
    """
    Xác định loại nguồn và trả về giá trị phù hợp
    
    Args:
        source_arg: Nguồn từ --source
        droidcam_args: Tuple (IP, PORT) từ --droidcam
    
    Returns:
        Tuple: (source_value, source_type_name)
    """
    # Ưu tiên 1: --droidcam IP PORT
    if droidcam_args:
        ip, port = droidcam_args
        url = f"http://{ip}:{port}/video"
        print(f"🔗 Kiểm tra kết nối DroidCam tại {url}...")
        if check_url_reachable(url):
            return url, f"DroidCam ({ip}:{port})"
        else:
            raise ConnectionError(f"❌ Không thể kết nối DroidCam tại {url}")
    
    # Ưu tiên 2: Định dạng shortcut droidcam:IP:PORT
    droidcam_url = parse_droidcam_source(source_arg)
    if droidcam_url:
        print(f"🔗 Kiểm tra kết nối DroidCam...")
        if check_url_reachable(droidcam_url):
            return droidcam_url, f"DroidCam ({source_arg.replace('droidcam:', '')})"
        else:
            raise ConnectionError(f"❌ Không thể kết nối DroidCam tại {droidcam_url}")
    
    # Ưu tiên 3: URL trực tiếp (http://... hoặc rtsp://...)
    if source_arg.startswith("http://") or source_arg.startswith("https://") or source_arg.startswith("rtsp://"):
        print(f"🔗 Kiểm tra kết nối URL stream...")
        if check_url_reachable(source_arg, timeout=5):
            return source_arg, f"Stream ({source_arg})"
        else:
            raise ConnectionError(f"❌ Không thể kết nối URL: {source_arg}")
    
    # Ưu tiên 4: Webcam (số)
    try:
        camera_index = int(source_arg)
        return camera_index, f"Webcam (ID: {camera_index})"
    except ValueError:
        pass
    
    # Ưu tiên 5: File video (tuyệt đối hoặc tương đối)
    # Kiểm tra đường dẫn tuyệt đối
    if os.path.exists(source_arg):
        abs_path = os.path.abspath(source_arg)
        return abs_path, f"File video: {abs_path}"
    
    # Kiểm tra đường dẫn tương đối từ script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    relative_path = os.path.join(script_dir, source_arg)
    if os.path.exists(relative_path):
        return relative_path, f"File video: {relative_path}"
    
    raise FileNotFoundError(f"❌ Không tìm thấy source: {source_arg}")


def setup_video_capture(source):
    """
    Khởi tạo VideoCapture
    
    Args:
        source: Webcam index, file path, hoặc URL
    
    Returns:
        cv2.VideoCapture object hoặc MJPEGStreamReader
    """
    # Nếu là MJPEG stream (DroidCam), dùng MJPEG reader
    if isinstance(source, str) and "http" in source and "4747" in source:
        print("🔗 Đang kết nối MJPEG stream (DroidCam)...")
        mjpeg_reader = MJPEGStreamReader(source)
        if mjpeg_reader.isOpened():
            return mjpeg_reader
        else:
            raise RuntimeError(f"❌ Không thể kết nối MJPEG stream: {source}")
    
    # Nếu là URL stream khác (RTSP, HTTP video), dùng cv2.VideoCapture
    if isinstance(source, str) and ("http" in source or "rtsp" in source):
        print("🔗 Đang kết nối video stream...")
        cap = cv2.VideoCapture(source)
        
        # Thử retry nếu lần đầu tiên thất bại
        if not cap.isOpened():
            print("⏳ Thử lại lần 1...")
            time.sleep(2)
            cap = cv2.VideoCapture(source)
        
        if not cap.isOpened():
            print("⏳ Thử lại lần 2...")
            time.sleep(2)
            cap = cv2.VideoCapture(source)
        
        # Tối ưu cho stream
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
        
        if not cap.isOpened():
            raise RuntimeError(f"❌ Không thể mở video stream: {source}")
        return cap
    
    # Nếu là webcam hoặc file video, dùng cv2.VideoCapture thường
    cap = cv2.VideoCapture(source)
    
    if not cap.isOpened():
        raise RuntimeError(f"❌ Không thể mở nguồn video: {source}")
    
    return cap


def get_frame_info(cap):
    """Lấy thông tin về video/camera"""
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    return fps, width, height


def main():
    """Hàm chính"""
    # Parse tham số
    args = parse_arguments()
    web_server_module = None
    
    print("\n" + "="*60)
    print("🛣️  HỆ THỐNG PHÁT HIỆN Ổ GÀ TRÊN ĐƯỜNG")
    print("="*60 + "\n")
    
    try:
        # Xóa dữ liệu phát hiện cũ khi bắt đầu
        script_dir = os.path.dirname(os.path.abspath(__file__))
        detections_dir = os.path.join(script_dir, "detections")
        if os.path.exists(detections_dir):
            import shutil
            print("🗑️  Xóa dữ liệu phát hiện cũ...")
            shutil.rmtree(detections_dir)
            print("✅ Đã reset dữ liệu\n")
        
        # Khởi tạo Telegram Notifier
        print("📱 Khởi tạo Telegram Notifier...")
        telegram_notifier = TelegramNotifier()
        print()
        
        # Khởi tạo Detection Logger
        print("📱 Khởi tạo Detection Logger...")
        script_dir = os.path.dirname(os.path.abspath(__file__))
        detections_dir = os.path.join(script_dir, "detections")
        detection_logger = DetectionLogger(output_dir=detections_dir, telegram_notifier=telegram_notifier)
        print()

        # Khởi chạy web server (nếu không bị tắt)
        if not args.no_web:
            print("🌐 Khởi chạy giao diện web tại http://localhost:5000 ...")
            import web_server as web_server_module
            start_web_server()
            print()
        
        # Xác định nguồn input
        print("📹 Đang kiểm tra nguồn input...")
        source_value, source_type = get_video_source(args.source, droidcam_args=args.droidcam)
        print(f"✅ Sử dụng: {source_type}\n")
        
        # Khởi tạo detector
        print("🤖 Đang tải mô hình AI...")
        detector = PotholeDetector(
            weight_path=args.weights,
            confidence_threshold=args.conf,
            detection_logger=detection_logger
        )
        
        # Nếu có tùy chọn skip audio
        if args.skip_audio:
            global HAS_PLAYSOUND
            HAS_PLAYSOUND = False
            print("🔇 Âm thanh cảnh báo bị tắt\n")
        
        # Mở video
        print("⏳ Đang khởi tạo video capture...")
        cap = setup_video_capture(source_value)
        fps, width, height = get_frame_info(cap)
        
        print(f"✅ Nguồn mở thành công!")
        print(f"   - Độ phân giải: {width}x{height}")
        if fps > 0:
            print(f"   - FPS: {fps:.1f}")
        print("\n" + "="*60)
        print("💡 Nhấn 'Q' để thoát | 'P' để tạm dừng")
        print("="*60 + "\n")
        
        frame_count = 0
        total_detections = 0
        paused = False
        stream_stride = 2
        
        # Vòng lặp xử lý frame
        while True:
            if not paused:
                ret, frame = cap.read()
                if not ret:
                    print("\n✅ Đã xử lý xong video! Nhấn 'Q' để thoát.")
                    paused = True
                    continue
                
                # Phát hiện ổ gà
                frame_with_detections, detected_count = detector.detect_and_draw(frame, frame_number=frame_count)
                total_detections += detected_count
                
                # Cảnh báo nếu có phát hiện
                if detected_count > 0:
                    detector.trigger_alert()
                
                # Hiển thị thông tin
                info_text = f"Frame: {frame_count} | Detections: {detected_count}"
                cv2.putText(frame_with_detections, info_text, (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                # Cập nhật frame cho web stream
                if web_server_module and frame_count % stream_stride == 0:
                    web_server_module.update_latest_frame(frame_with_detections)
                
                # Hiển thị frame
                cv2.imshow("🛣️ Phát Hiện Ổ Gà - Press Q to Exit", frame_with_detections)
                
                frame_count += 1
            else:
                # Khi tạm dừng, vẫn hiển thị frame nhưng không xử lý
                cv2.imshow("🛣️ Phát Hiện Ổ Gà - Press Q to Exit", frame_with_detections)
            
            # Xử lý phím
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == ord('Q'):
                print("\n👋 Thoát chương trình...")
                break
            elif key == ord('p') or key == ord('P'):
                paused = not paused
                status = "TẠMM DỪNG" if paused else "TIẾP TỤC"
                print(f"⏸️  {status}")
        
        # Giải phóng tài nguyên
        if detection_logger and detection_logger.blockchain.enabled:
            print("⏳ Chờ gửi hash blockchain...")
            detection_logger.blockchain.wait_for_pending(timeout=15)
        if detection_logger and detection_logger.telegram_notifier and detection_logger.telegram_notifier.enabled:
            print("⏳ Chờ gửi tin Telegram...")
            detection_logger.telegram_notifier.wait_for_pending(timeout=15)
        cap.release()
        cv2.destroyAllWindows()
        
        print(f"\n✅ Tổng số frame xử lý: {frame_count}")
        print(f"✅ Tổng ổ gà phát hiện: {total_detections}")
        print(f"📁 Các ảnh phát hiện được lưu trong: detections/")
        print(f"🌐 Truy cập: http://localhost:5000 để xem giao diện web")
        print("="*60 + "\n")
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Người dùng dừng chương trình!")
        if 'detection_logger' in locals() and detection_logger.blockchain.enabled:
            print("⏳ Chờ gửi hash blockchain...")
            detection_logger.blockchain.wait_for_pending(timeout=15)
        if 'detection_logger' in locals() and detection_logger.telegram_notifier and detection_logger.telegram_notifier.enabled:
            print("⏳ Chờ gửi tin Telegram...")
            detection_logger.telegram_notifier.wait_for_pending(timeout=15)
        if 'cap' in locals():
            cap.release()
            cv2.destroyAllWindows()
    except Exception as e:
        print(f"\n❌ LỖI: {e}")
        import traceback
        traceback.print_exc()
        if 'detection_logger' in locals() and detection_logger.blockchain.enabled:
            print("⏳ Chờ gửi hash blockchain...")
            detection_logger.blockchain.wait_for_pending(timeout=15)
        if 'detection_logger' in locals() and detection_logger.telegram_notifier and detection_logger.telegram_notifier.enabled:
            print("⏳ Chờ gửi tin Telegram...")
            detection_logger.telegram_notifier.wait_for_pending(timeout=15)
        if 'cap' in locals():
            cap.release()
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
