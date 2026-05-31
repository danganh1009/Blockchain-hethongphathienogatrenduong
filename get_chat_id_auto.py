#!/usr/bin/env python3
import requests
import json

TOKEN = "8678043145:AAFtwQ3xBDROot-ciTwHsc3w1MosLLDGkcw"

print("🔍 Đang lấy Chat ID từ @Ovit_bot...")
try:
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    response = requests.get(url)
    data = response.json()
    
    if data['ok'] and data['result']:
        for update in data['result']:
            if 'message' in update:
                chat_id = update['message']['chat']['id']
                print(f"✅ Chat ID: {chat_id}")
                
                # Cập nhật .env
                with open('.env', 'r') as f:
                    content = f.read()
                
                new_content = content.replace(
                    f"TELEGRAM_CHAT_ID=",
                    f"TELEGRAM_CHAT_ID={chat_id}"
                )
                
                with open('.env', 'w') as f:
                    f.write(new_content)
                
                print(f"✅ File .env đã cập nhật!")
                break
    else:
        print("❌ Không tìm thấy tin nhắn. Hãy gửi /start cho @Ovit_bot trước!")
        
except Exception as e:
    print(f"❌ Lỗi: {e}")
