import os
import cv2
import torch

# ==============================
# 🔍 Tự động tìm dataset_dir
# ==============================
def find_dataset_dir():
    for root, dirs, files in os.walk("."):
        if "train" in dirs and "valid" in dirs:
            return os.path.abspath(root)
    raise FileNotFoundError("❌ Không tìm thấy dataset_dir!")
    
dataset_dir = find_dataset_dir()
img_path = os.path.join(dataset_dir, "train/images")
label_path = os.path.join(dataset_dir, "train/labels")
out_path = os.path.join(dataset_dir, "vis")
os.makedirs(out_path, exist_ok=True)

# Class names (sửa theo dataset)
class_names = ["pothole"]

# ==============================
# ⚡ Chọn device: GPU / CPU
# ==============================
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print("✅ Using device:", device)

# ==============================
# 🚀 Loop qua ảnh trong dataset
# ==============================
for img_file in os.listdir(img_path):
    if not (img_file.endswith(".jpg") or img_file.endswith(".png")):
        continue

    # Đọc ảnh bằng OpenCV → Tensor
    img = cv2.imread(os.path.join(img_path, img_file))
    h, w, _ = img.shape
    img_tensor = torch.from_numpy(img).to(device)

    # Load nhãn
    label_file = os.path.join(label_path, img_file.rsplit(".", 1)[0] + ".txt")
    if not os.path.exists(label_file):
        continue

    with open(label_file, "r") as f:
        labels = [list(map(float, line.split())) for line in f.readlines()]

    if len(labels) == 0:
        continue

    labels = torch.tensor(labels, device=device)  # (N, 5) tensor [cls, x, y, bw, bh]

    # Chuyển từ YOLO format (cx, cy, w, h) → (x1, y1, x2, y2)
    cx, cy, bw, bh = labels[:, 1], labels[:, 2], labels[:, 3], labels[:, 4]
    x1 = ((cx - bw/2) * w).long()
    y1 = ((cy - bh/2) * h).long()
    x2 = ((cx + bw/2) * w).long()
    y2 = ((cy + bh/2) * h).long()
    cls_ids = labels[:, 0].long()

    # Convert về CPU để vẽ (OpenCV không chạy GPU)
    img_np = img_tensor.cpu().numpy()

    # Vẽ bounding box
    for i in range(len(cls_ids)):
        cv2.rectangle(img_np, (x1[i].item(), y1[i].item()), (x2[i].item(), y2[i].item()), (0, 255, 0), 2)
        cv2.putText(img_np, class_names[cls_ids[i].item()], (x1[i].item(), y1[i].item() - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    # Lưu kết quả
    cv2.imwrite(os.path.join(out_path, img_file), img_np)

print("🎉 Done! Check folder:", out_path)
