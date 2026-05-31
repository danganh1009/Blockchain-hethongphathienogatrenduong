#!/usr/bin/env python3
"""
🤖 Helper script để lấy Telegram Chat ID và test kết nối
Chạy: python get_telegram_info.py
"""

import os
import sys
import requests
from dotenv import load_dotenv

# Load environment variables từ .env
load_dotenv()

def get_chat_id_from_api():
    """Lấy Chat ID từ Telegram API"""
    token = input("📌 Nhập TELEGRAM_TOKEN của bạn: ").strip()
    
    if not token:
        print("❌ Token không được để trống!")
        return None
    
    try:
        # Gọi getMe để kiểm tra token
        url = f"https://api.telegram.org/bot{token}/getMe"
        response = requests.get(url, timeout=5)
        result = response.json()
        
        if not result.get("ok"):
            print(f"❌ Token không hợp lệ: {result.get('description', 'Unknown error')}")
            return None
        
        print(f"✅ Bot name: {result['result']['first_name']} (@{result['result']['username']})")
        print("\n📱 Các bước lấy Chat ID:")
        print("1. Tìm bot vừa tạo trên Telegram")
        print("2. Gửi bất kỳ tin nhắn nào")
        print("3. Truy cập URL dưới đây:")
        print(f"   https://api.telegram.org/bot{token}/getUpdates")
        print("4. Tìm dòng: \"chat\":{\"id\": <YOUR_CHAT_ID>}")
        print("5. Copy giá trị <YOUR_CHAT_ID>\n")
        
        # Cố gắng lấy chat ID từ recent updates
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        response = requests.get(url, timeout=5)
        result = response.json()
        
        if result.get("ok") and result['result']:
            for update in result['result']:
                if 'message' in update:
                    chat_id = update['message']['chat']['id']
                    print(f"✅ Found Chat ID: {chat_id}")
                    return token, chat_id
        
        print("ℹ️  Không tìm thấy tin nhắn gần đây. Hãy gửi tin nhắn cho bot rồi chạy lại script này.")
        chat_id = input("Hoặc nhập Chat ID thủ công (nếu có): ").strip()
        if chat_id:
            return token, int(chat_id)
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Lỗi kết nối: {e}")
    except Exception as e:
        print(f"❌ Lỗi: {e}")
    
    return None


def test_telegram_connection(token, chat_id):
    """Test kết nối Telegram"""
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": "🎉 Test thành công! Hệ thống phát hiện ổ gà của bạn đã sẵn sàng gửi ảnh lên Telegram."
        }
        
        response = requests.post(url, json=data, timeout=5)
        result = response.json()
        
        if result.get("ok"):
            print("✅ Test thành công! Bạn sẽ nhận được tin nhắn trên Telegram.")
            return True
        else:
            print(f"❌ Test thất bại: {result.get('description', 'Unknown error')}")
            return False
    except Exception as e:
        print(f"❌ Lỗi test: {e}")
        return False


def main():
    """Hàm chính"""
    print("\n" + "="*60)
    print("🤖 TELEGRAM SETUP HELPER")
    print("="*60 + "\n")
    
    # Kiểm tra requests library
    try:
        import requests
    except ImportError:
        print("⚠️  Cần cài đặt thư viện requests")
        print("Chạy: pip install requests python-dotenv")
        return
    
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if token and chat_id:
        print("✅ Đã tìm thấy cấu hình Telegram trong .env")
        print(f"Token: {token[:10]}... (ẩn)")
        print(f"Chat ID: {chat_id}\n")
        
        choice = input("Bạn muốn test kết nối? (y/n): ").lower()
        if choice == 'y':
            test_telegram_connection(token, chat_id)
        else:
            print("✅ Cấu hình sẵn sàng!")
    else:
        print("📌 Cần cấu hình Telegram\n")
        result = get_chat_id_from_api()
        
        if result:
            token, chat_id = result
            print("\n" + "="*60)
            print("📝 Thêm dòng sau vào .env hoặc environment variables:")
            print("="*60)
            print(f"TELEGRAM_TOKEN={token}")
            print(f"TELEGRAM_CHAT_ID={chat_id}")
            print("="*60 + "\n")
            
            choice = input("Bạn muốn test kết nối? (y/n): ").lower()
            if choice == 'y':
                test_telegram_connection(token, chat_id)


if __name__ == "__main__":
    main()
