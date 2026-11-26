"""Kiểm tra cặp mẫu AVM và ánh xạ nhãn; không huấn luyện hoặc giả lập kết quả AI."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def avm_to_project(rgb: np.ndarray) -> np.ndarray:
    """FREE=0, OBSTACLE=1, UNKNOWN=255. Vùng xe mình/màu lạ không là FREE."""
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("Mask phải là ảnh RGB uint8")
    result = np.full(rgb.shape[:2], 255, dtype=np.uint8)
    for color, label in (((0, 0, 255), 0), ((255, 255, 255), 0),
                         ((255, 0, 0), 1), ((0, 255, 0), 1)):
        result[np.all(rgb == color, axis=2)] = label
    return result


def main():
    import cv2
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=Path, default=Path("datasets/samples/avm"))
    args = parser.parse_args()
    sample = args.sample
    image = cv2.imdecode(np.frombuffer((sample / "image.jpg").read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    mask = cv2.imdecode(np.frombuffer((sample / "gt.png").read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    if image is None or mask is None or image.shape != mask.shape:
        raise ValueError("Ảnh/mask không đọc được hoặc khác kích thước")
    rgb = cv2.cvtColor(mask, cv2.COLOR_BGR2RGB)
    colors, counts = np.unique(rgb.reshape(-1, 3), axis=0, return_counts=True)
    mapped = avm_to_project(rgb)
    ok, encoded = cv2.imencode(".png", mapped)
    if not ok:
        raise ValueError("Không mã hóa được nhãn")
    (sample / "project_labels.png").write_bytes(encoded.tobytes())
    report = {"source": "https://github.com/Engro39/avm_dataset", "sample_only": True,
              "image_shape": list(image.shape), "mask_colors_rgb": [
                  {"rgb": c.tolist(), "pixels": int(n)} for c, n in zip(colors, counts)],
              "project_pixels": {str(v): int((mapped == v).sum()) for v in (0, 1, 255)},
              "mapping": {"0": "FREE (free space + marker)", "1": "OBSTACLE (vehicle + other)",
                          "255": "UNKNOWN/IGNORE (ego + unrecognized colors)"},
              "sha256": {name: hashlib.sha256((sample / name).read_bytes()).hexdigest()
                         for name in ("image.jpg", "gt.png")},
              "caveat": "Đây là chuyển nhãn mẫu do tác giả công bố; không phải dự đoán, không phải nghiệm thu toàn dataset."}
    (sample / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
