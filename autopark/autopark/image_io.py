"""Đọc/ghi ảnh qua OpenCV mà chịu được đường dẫn có dấu tiếng Việt trên Windows (thêm 29/09/2026).

`cv2.imread`/`cv2.imwrite` mở tệp theo bảng mã ANSI của Windows (máy bàn: 1252), nên đường dẫn như `D:\\gấp\\...` làm
imread trả None và imwrite trả False mà không báo lỗi (đo 29/09/2026, OpenCV 5.0.0). `VideoWriter`/`VideoCapture` qua
FFmpeg thì không bị. Hai hàm dưới giữ hợp đồng của cv2 nhưng đọc/ghi byte bằng Python: imread trả None khi hỏng; imwrite
trả False khi không mã hóa hay không ghi được, và NÉM cv2.error ở đúng những chỗ cv2.imwrite ném (ảnh rỗng, không có
đuôi hay đuôi lạ).
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def imread(path, flags: int = cv2.IMREAD_COLOR) -> np.ndarray | None:
    """Như `cv2.imread`: None khi không có tệp hay không giải mã được."""
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, flags)


def imwrite(path, image: np.ndarray, params=None) -> bool:
    """Như `cv2.imwrite`: định dạng theo đuôi tệp; False khi không mã hóa hay không ghi được."""
    path = Path(path)
    ok, buffer = cv2.imencode(path.suffix, image, [] if params is None else list(params))
    if not ok:
        return False
    try:
        path.write_bytes(buffer.tobytes())
    except OSError:
        return False
    return True
