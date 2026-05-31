import cv2
import os
import glob
import time
from ultralytics import YOLO
from gtts import gTTS
from playsound import playsound

# ==============================
# 1. Tạo file âm thanh cảnh báo nếu chưa có
# ==============================
if not os.path.exists("canhbao.mp3"):
    tts = gTTS("Cảnh báo! Phía trước có ổ gà, hãy giảm tốc độ!", lang="vi")
    tts.save("canhbao.mp3")
    print("✅ Đã tạo file canhbao.mp3")

# ==============================
# 2. Tìm file YOLO best.pt mới nhất
# ==============================
weight_paths = glob.glob("runs/detect/**/weights/best.pt", recursive=True)
if not weight_paths:
    raise FileNotFoundError("⚠️ Không tìm thấy file best.pt trong runs/detect/")

latest_weight = max(weight_paths, key=os.path.getmtime)
print(f"✅ Đang dùng mô hình: {latest_weight}")

# Load YOLO
model = YOLO(latest_weight)

# ==============================
# 3. Mở video và chạy detect
# ==============================
cap = cv2.VideoCapture("test1.mp4")   # đổi sang 0 nếu muốn dùng webcam

last_alert_time = 0   # để tránh cảnh báo liên tục

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Detect
    results = model(frame, verbose=False)

    detected = False
    for result in results:
        boxes = result.boxes.xyxy.cpu().numpy()
        confs = result.boxes.conf.cpu().numpy()
        names = result.boxes.cls.cpu().numpy()

        for box, conf, cls_id in zip(boxes, confs, names):
            if conf > 0.5:  # ngưỡng tự tin
                detected = True
                x1, y1, x2, y2 = map(int, box)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                cv2.putText(frame, "O GA!", (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

    # Nếu phát hiện ổ gà -> cảnh báo
    if detected and (time.time() - last_alert_time > 5):  # cách nhau ít nhất 5s
        print("⚠️ Cảnh báo: Phía trước có ổ gà!")
        playsound("canhbao.mp3", block=False)  # phát giọng nói song song
        last_alert_time = time.time()

    # Hiển thị video
    cv2.imshow("Pothole Detection", frame)

    # ==============================
    # 4. Làm chậm tốc độ video (sleep)
    # ==============================
    time.sleep(0.05)  # 0.05s ~ 20 FPS. Tăng lên (0.1s) để chậm hơn

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
