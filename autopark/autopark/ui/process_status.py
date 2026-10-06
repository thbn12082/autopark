"""Nhãn trạng thái EcoQoS của tiến trình ở thanh trạng thái các cửa sổ ứng dụng (thêm 02/10/2026).

`main()` của mỗi ứng dụng gọi `apply_ecoqos_policy(...)` (autopark/power_throttling.py) trước mọi việc khác, rồi gọi
`add_ecoqos_label(window, ecoqos)` ngay sau `window.show()`. Nhãn nằm cố định bên phải thanh trạng thái: "EcoQoS: tắt";
chữ vàng khi giữ mặc định của Windows (AUTOPARK_KEEP_ECOQOS=1), chữ đỏ khi Windows không nhận yêu cầu tắt, kèm một lời
báo 15 s. Chú thích (tooltip) nói vì sao và cách giữ mặc định. Không đổi tiêu đề cửa sổ (test so tiêu đề đúng từng chữ),
không mở hộp thoại. Nhãn chỉ nói trạng thái lúc khởi động: bật "Efficiency mode" trong Task Manager sau đó thì nhãn
không đổi (tệp kết quả vẫn ghi đúng vì đọc lại lúc ghi). Chỉ kiểm offscreen; cửa sổ thật CHƯA THỬ.
"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QMainWindow

from autopark.power_throttling import EcoQoSPolicy
from autopark.ui import theme

LABEL_NAME = "ecoqos_label"
WARNING_MS = 15000
_LEVEL_COLOR = {"warn": theme.WARN, "danger": theme.DANGER}


def add_ecoqos_label(window: QMainWindow, policy: EcoQoSPolicy) -> QLabel | None:
    """Thêm nhãn EcoQoS vào thanh trạng thái của `window`; None (không thêm gì) khi không phải Windows."""
    if not policy.windows:
        return None
    label = QLabel(policy.short_vi())
    label.setObjectName(LABEL_NAME)
    label.setToolTip(policy.explain_vi())
    window.statusBar().addPermanentWidget(label)
    color = _LEVEL_COLOR.get(policy.level)
    if color is not None:
        label.setStyleSheet(f"color: {color}; font-weight: 600;")
        window.statusBar().showMessage(f"Cảnh báo: {policy.short_vi()} — đừng thu nhỏ cửa sổ khi đang lập đường hay "
                                       "đang chạy.", WARNING_MS)
    return label
