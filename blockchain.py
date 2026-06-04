"""
Blockchain module - Gửi hash detection lên smart contract Sepolia
"""

import os                                                                       # Đọc environment variables
import json                                                                     # Xử lý JSON files
import threading                                                                # Chạy transaction trong background
import hashlib                                                                  # Tính SHA-256 hash


def compute_detection_hash(image_bytes, timestamp_display, location):
    """Tạo SHA-256 từ ảnh + thời gian + vị trí."""
    # Ghép ảnh + thời gian + vị trí thành một payload duy nhất để băm.
    # Nếu bất kỳ thành phần nào thay đổi (ảnh/thời gian/vị trí) thì hash sẽ khác.
    payload = (
        image_bytes                                                           # Thêm dữ liệu ảnh (bytes)
        + b"|"                                                                # Thêm ký tự phân tách |
        + timestamp_display.encode("utf-8")                                  # Chuyển timestamp thành UTF-8 bytes
        + b"|"                                                                # Thêm ký tự phân tách |
        + f"{location['lat']},{location['lon']}".encode("utf-8")            # Chuyển tọa độ GPS thành UTF-8 bytes
    )
    # Tính SHA-256 hash của payload và chuyển thành hex string (64 ký tự hexa)
    return hashlib.sha256(payload).hexdigest()


CONTRACT_ABI = [
    # ===== FUNCTION 1: storeHash() =====
    # Hàm ghi hash detection lên blockchain (write function)
    {
        "inputs": [
            # Tham số 1: dataHash (32 bytes - kích thước cố định của SHA-256)
            {"internalType": "bytes32", "name": "dataHash", "type": "bytes32"},
            # Tham số 2: imageFile (chuỗi text - tên file ảnh detection)
            {"internalType": "string", "name": "imageFile", "type": "string"},
        ],
        "name": "storeHash",                              # Tên function trên smart contract
        "outputs": [],                                    # Không trả về giá trị (void)
        "stateMutability": "nonpayable",                  # Không cần gửi ETH, chỉ gas fee
        "type": "function",                               # Đây là một function bình thường
    },
    
    # ===== FUNCTION 2: hasHash() =====
    # Hàm kiểm tra hash có tồn tại trên blockchain không (read function)
    {
        "inputs": [
            # Tham số: dataHash cần kiểm tra
            {"internalType": "bytes32", "name": "dataHash", "type": "bytes32"}
        ],
        "name": "hasHash",                                # Tên function trên smart contract
        "outputs": [
            # Trả về kết quả boolean (true nếu hash tồn tại, false nếu không)
            {"internalType": "bool", "name": "", "type": "bool"}
        ],
        "stateMutability": "view",                        # Chỉ đọc dữ liệu, không thay đổi state
        "type": "function",                               # Đây là một function bình thường
    },
]

DEFAULT_SEPOLIA_CONTRACT_ADDRESS = "0x97A093BB0563AC74080291b7eAFE0582638c35Ad"  # Địa chỉ smart contract trên Sepolia testnet


class BlockchainClient:
    """Gửi hash lên smart contract trên Sepolia."""

    def __init__(self):
        self.enabled = False                              # Flag: blockchain có hoạt động không (mặc định tắt)
        self.pending_threads = []                         # Danh sách các thread đang gửi transaction
        self.nonce_lock = threading.Lock()                # Lock để tránh race condition khi tăng nonce
        self.next_nonce = None                            # Nonce của transaction tiếp theo (ban đầu None)
        self._init_client()                               # Gọi hàm khởi tạo client

    def _init_client(self):
        # Lấy các biến môi trường từ hệ thống (.env file)
        self.rpc_url = os.getenv("SEPOLIA_RPC_URL")                           # URL endpoint RPC của Sepolia testnet
        self.private_key = os.getenv("SEPOLIA_PRIVATE_KEY")                   # Private key của ví Ethereum
        self.contract_address = os.getenv("SEPOLIA_CONTRACT_ADDRESS", DEFAULT_SEPOLIA_CONTRACT_ADDRESS)  # Address smart contract

        # Kiểm tra: nếu thiếu RPC URL hoặc Private Key, tắt blockchain
        if not self.rpc_url or not self.private_key:
            # Thiếu cấu hình thì tắt blockchain, phần còn lại vẫn chạy bình thường.
            print("ℹ️ Blockchain tắt (thiếu SEPOLIA_RPC_URL/SEPOLIA_PRIVATE_KEY)")
            return

        # === BƯỚC 1: VALIDATE PRIVATE KEY ===
        # Xóa tiền tố "0x" nếu có và loại bỏ khoảng trắng
        private_key_clean = self.private_key.replace("0x", "").strip()
        # Private key phải có đúng 64 ký tự hex (256 bits = 64 hex chars)
        if len(private_key_clean) != 64:
            print(f"❌ SEPOLIA_PRIVATE_KEY format error: expected 64 hex chars, got {len(private_key_clean)}")
            print("   Private key must be 64 hexadecimal characters (0-9, a-f)")
            print("   You may have set it to your wallet address instead of private key")
            return
        
        # Kiểm tra: các ký tự trong private key có phải hexa không (0-9, a-f)
        try:
            int(private_key_clean, 16)  # Validate it's valid hex - thử convert thành số hexa
        except ValueError:
            print(f"❌ SEPOLIA_PRIVATE_KEY contains non-hexadecimal characters")
            print("   Valid hex: 0-9, a-f only")
            return

        # === BƯỚC 2: IMPORT WEB3 LIBRARY ===
        # Thư viện web3.py là cầu nối Python với Ethereum blockchain
        try:
            from web3 import Web3
        except Exception:
            print("⚠️ Thiếu thư viện web3. Cài: pip install web3")
            return

        # === BƯỚC 3: KẾT NỐI TỚI RPC ENDPOINT ===
        # Tạo đối tượng Web3 kết nối với RPC endpoint của Sepolia
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        # Kiểm tra: kết nối thành công không?
        if not self.w3.is_connected():
            # RPC không kết nối được (URL sai, mạng sai, bị chặn...).
            print(f"⚠️ Không kết nối được RPC Sepolia: {self.rpc_url}")
            return

        # === BƯỚC 4: LOAD TÀI KHOẢN TỪ PRIVATE KEY ===
        # Tạo đối tượng account từ private key (chứa địa chỉ ví + signing methods)
        self.account = self.w3.eth.account.from_key(self.private_key)
        # === BƯỚC 5: KẾT NỐI SMART CONTRACT ===
        # Tạo đối tượng contract để gọi các function trên blockchain
        # Cần: địa chỉ contract + ABI (mô tả các function)
        self.contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(self.contract_address),      # Convert address thành checksum format
            abi=CONTRACT_ABI,                                                 # Danh sách các function có sẵn
        )
        # === KẾT QUẢ: BLOCKCHAIN READY ===
        self.enabled = True                                                   # Bật flag blockchain ready
        print("✅ Blockchain client sẵn sàng")

    def submit_hash_async(self, data_hash, image_file, json_path):
        """Gửi hash lên blockchain trong background thread (không chặn video)"""
        # Tạo thread mới để gửi transaction
        thread = threading.Thread(
            target=self._submit_hash,                                         # Hàm sẽ chạy trong thread
            args=(data_hash, image_file, json_path),                          # Tham số truyền vào hàm
            daemon=False,                                                      # daemon=False: chờ thread hoàn tất trước khi exit
        )
        # Thêm thread vào danh sách để theo dõi
        self.pending_threads.append(thread)
        # Bắt đầu chạy thread
        thread.start()

    def wait_for_pending(self, timeout=10):
        """Chờ tất cả transaction đang pending hoàn tất trước khi thoát"""
        # Nếu không có thread nào đang chạy, return luôn
        if not self.pending_threads:
            return
        # Duyệt qua từng thread trong danh sách
        for thread in list(self.pending_threads):
            # Chờ thread hoàn tất trong timeout giây (mặc định 10 giây)
            thread.join(timeout=timeout)
        # Sau khi chờ, lọc lại danh sách: chỉ giữ những thread vẫn còn chạy
        self.pending_threads = [t for t in self.pending_threads if t.is_alive()]

    def _get_next_nonce(self):
        """Lấy nonce tiếp theo (theo dõi số thứ tự transaction)"""
        # Lock: chỉ một thread được phép truy cập nonce cùng lúc
        with self.nonce_lock:
            # Lần đầu tiên: lấy nonce hiện tại từ blockchain
            if self.next_nonce is None:
                # get_transaction_count: đếm số transaction đã gửi từ địa chỉ này
                # = nonce của transaction tiếp theo
                self.next_nonce = self.w3.eth.get_transaction_count(self.account.address)
            # Lấy nonce hiện tại
            nonce = self.next_nonce
            # Tăng nonce cho transaction tiếp theo
            self.next_nonce += 1
            # Trả về nonce của transaction hiện tại
            return nonce

    def _submit_hash(self, data_hash, image_file, json_path):
        """Gửi hash lên smart contract (function chạy trong background thread)"""
        try:
            # === BƯỚC 1: LẤY NONCE ===
            # Nonce: số thứ tự transaction, mỗi transaction cần nonce khác nhau
            nonce = self._get_next_nonce()
            
            # === BƯỚC 2: XÂY DỰNG TRANSACTION ===
            # Gọi function storeHash() trên smart contract
            tx = self.contract.functions.storeHash(
                bytes.fromhex(data_hash),                                     # Chuyển hex string thành bytes32
                image_file,                                                   # Tên file ảnh (string)
            ).build_transaction({
                # Người gửi transaction (ví của chúng ta)
                "from": self.account.address,
                # Nonce: số thứ tự transaction
                "nonce": nonce,
                # Gas limit: mức gas tối đa cho transaction này
                "gas": 150000,
                # maxFeePerGas: mức phí tối đa (150 gwei)
                "maxFeePerGas": self.w3.to_wei("20", "gwei"),
                # maxPriorityFeePerGas: ưu tiên cho miner (1 gwei)
                "maxPriorityFeePerGas": self.w3.to_wei("1", "gwei"),
            })
            
            # === BƯỚC 3: KÝ TRANSACTION ===
            # Sử dụng private key để ký transaction (chứng minh quyền sở hữu ví)
            signed = self.account.sign_transaction(tx)
            # Lấy raw transaction (dạng byte được ký)
            raw_tx = signed.rawTransaction if hasattr(signed, "rawTransaction") else signed.raw_transaction
            
            # === BƯỚC 4: GỬI TRANSACTION LÊN BLOCKCHAIN ===
            # send_raw_transaction: gửi transaction đã ký tới Sepolia testnet
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            # Chuyển transaction hash thành hex string
            tx_hex = self.w3.to_hex(tx_hash)
            
            # === BƯỚC 5: LƯU TX_HASH VÀO JSON FILE ===
            # Lưu transaction hash để có thể tra cứu sau này
            self._update_json_tx(json_path, tx_hex)
            # In thông báo thành công
            print(f"🔗 Đã gửi hash lên blockchain: {tx_hex}")
        except Exception as e:
            # Nếu lỗi, in thông báo lỗi và tiếp tục (không làm crash chương trình)
            print(f"⚠️ Gửi blockchain thất bại: {type(e).__name__}: {e}")

    def _update_json_tx(self, json_path, tx_hash):
        """Cập nhật file JSON detection với transaction hash từ blockchain"""
        try:
            # === BƯỚC 1: ĐỌC FILE JSON ===
            # Mở file JSON (chứa thông tin detection)
            with open(json_path, "r", encoding="utf-8") as f:
                # Đọc và parse JSON thành dictionary Python
                data = json.load(f)
            
            # === BƯỚC 2: CẬP NHẬT TRANSACTION HASH ===
            # Thêm/cập nhật trường tx_hash vào dictionary
            data["tx_hash"] = tx_hash
            
            # === BƯỚC 3: GHI LẠI FILE JSON ===
            # Mở file ở chế độ ghi (overwrite)
            with open(json_path, "w", encoding="utf-8") as f:
                # Ghi dictionary thành JSON (pretty print với indent=2)
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            # Nếu lỗi (file không tìm thấy, lỗi JSON...), in thông báo
            print(f"⚠️ Không thể cập nhật tx_hash: {e}")
