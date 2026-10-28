"""Giao diện tham chiếu trên cao R1 (T4, docs/KIEM_THU_VA_LO_TRINH.md): lớp mỏng trên `evaluation/overhead_ref.py`,
`overhead_tc1.py` và `video/overhead_record.py`. Thêm 02/10/2026.

    .venv\\Scripts\\python.exe -X utf8 -m autopark.ui.overhead_app
    .venv\\Scripts\\python.exe -X utf8 -m autopark.ui.overhead_app --index N --camera-name tren_cao --size 1280x720 --intrinsics calibration\\cam_tren_cao_1280x720.json --survey docs\\evidence\\moc_sa_ban_<ngay>.csv

Bốn thẻ:

1. **Mặt sàn**: nạp nội tham camera trên cao (T11), tệp mốc sa bàn, ảnh/video sàn trống (hoặc chụp 15 khung từ camera đang
   mở), chọn từ điển ArUco và cách tinh chỉnh góc, "Dò mốc" (bảng: tên, vai trò, mã, nguồn ArUco/chấm tay, u, v, sai số),
   chấm tay điểm không có mã (chuột trái đặt, chuột phải xóa, Esc thôi), "Khớp mặt sàn" (tóm tắt: độ cao/nghiêng
   camera, mốc dùng/bị loại, sai số mốc kiểm soát và điểm kiểm tra, mốc thiếu, cảnh báo, "Dùng được cho (chỉ phần mặt
   sàn)"), "Lưu kết quả khớp…" (JSON + ảnh xem). Đổi bất kỳ đầu vào nào thì kết quả khớp cũ mất hiệu lực.
2. **Trích tư thế**: video, kết quả khớp, cấu hình marker xe, biên bản TC-1 (đầy đủ / rút gọn trong ngày), số marker tối
   thiểu, khoảng thời gian, sai số đồng bộ, cặp đồng bộ, vùng ô nháy T14 (kéo chuột trên ảnh) và tệp dấu đồng bộ; "Bắt
   đầu trích"/"Dừng" chạy nền với tiến độ, xem trước (≤ 5 Hz: marker, thân xe, điểm R1), đồ thị x, y, hướng theo t, và
   độ chính xác sẽ ghi (từ TC-1, hay CHƯA CÓ kèm lý do). "Lưu tệp tư thế…" (mặc định
   runs\\nghiem_thu\\<yyyymmdd>\\<tên video>\\tu_the_tham_chieu.csv). Ô "Nhận video chỉ có số khung/s danh định" như
   `--allow-nominal-fps` (thêm 02/10/2026: AVI không kèm tệp của bộ ghi bị từ chối nếu không đánh dấu).
3. **TC-1**: bảng tư thế sửa được (tư thế, video, cửa sổ, hai đầu thước, tâm kiểm chéo, người đo, ngày) và cột kết quả
   (sai số vị trí, hướng, độ tản); nạp/lưu bảng; loại đầy đủ (≥ 10) / rút gọn trong ngày (≥ 3); so các cách tinh chỉnh
   góc; "Tính TC-1" chạy nền; "Lưu biên bản TC-1…" (bộ thử tổng hợp bị từ chối dưới docs\\evidence).
4. **Ghi video**: chỉ khi chạy với `--index N` (tra bằng `python -m autopark.video.camera_bench list`). Camera KHÔNG BAO
   GIỜ mở lúc khởi động: chỉ nút "Mở camera". Xem trực tiếp kèm độ lệch camera so với lúc khớp; "Bắt đầu ghi"/"Dừng
   ghi" ghi như `video.overhead_record` (stamp perf_counter từng khung).

Trích, TC-1 và đọc camera chạy trong luồng riêng; một QTimer 100 ms đọc kết quả. Đóng cửa sổ thì báo dừng các luồng và chờ
tối đa 3 s. Như `video.overhead_record`, `main()` tự tắt EcoQoS của tiến trình (`power_throttling`); tệp ghi mang chính
sách lúc khởi động (`ecoqos_policy`) và trạng thái đọc lại lúc ghi (`ecoqos`). "Tính TC-1" từ chối như lệnh `tc1` (khớp
mặt sàn chưa đạt, cấu hình marker thật chưa đo). Các phương thức công khai nhận đường dẫn tường minh, không mở hộp thoại
(test gọi thẳng). Mọi ngưỡng ĐỀ XUẤT – CHỜ CHỐT (người dùng giao quyết định 02/10/2026). Chỉ kiểm offscreen với bộ thử
TỔNG HỢP và camera giả (tests/test_overhead_app_ui.py); CHƯA THỬ với camera thật.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import traceback

import cv2
import numpy as np

from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
                               QTabWidget, QVBoxLayout, QWidget)

from autopark.evaluation import overhead_ref as R
from autopark.evaluation import overhead_tc1 as T
from autopark.perception.aruco_sheet import DICTIONARIES
from autopark.perception.paths import PROJECT
from autopark.ui.calib_app import index_camera_factory, parse_size
from autopark.ui.roi_app import ImageCanvas, _mono
from autopark.video import overhead_record as rec

TITLE = "Tham chiếu trên cao (R1, T4)"
POLL_MS = 100
PREVIEW_EVERY_S = 0.2
LIVE_EVERY_S = 0.1
SHIFT_EVERY_S = 0.5
CAPTURE_FRAMES = 15
CLOSE_WAIT_S = 3.0
FLOOR_COLUMNS = ["Tên", "Vai trò", "Mã", "Nguồn", "u", "v", "Sai số (mm)", "Ghi chú"]
TC1_INPUTS = [("Tư thế", "tu_the"), ("Video", "video"), ("Từ (s)", "t_tu_s"), ("Đến (s)", "t_den_s"),
              ("x sau", "x_sau_m"), ("y sau", "y_sau_m"), ("x trước", "x_truoc_m"), ("y trước", "y_truoc_m"),
              ("x tâm", "x_tam_m"), ("y tâm", "y_tam_m"), ("Người đo", "nguoi_do"), ("Ngày", "ngay")]
TC1_RESULTS = ["Sai số vị trí (mm)", "Sai số hướng (°)", "Độ tản p95 (mm)"]
REFINE_ITEMS = (("contour", "đường viền – mặc định"), ("subpix", "điểm ảnh con"), ("apriltag", "AprilTag"),
                ("none", "không"))
LEGEND = "xanh lá: mốc kiểm soát · xanh lam: điểm kiểm tra · đỏ: bị loại · xám: không thấy · mũi tên: sai số ×100"
SOURCE_LABELS = {"aruco": "ArUco", "click": "chấm tay"}
NOMINAL_FPS_LABEL = "Nhận video chỉ có số khung/s danh định (thời điểm khung không phải stamp thật; có ghi chú)"


def _f(x, nd: int = 1) -> str:
    return "—" if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{x:.{nd}f}".replace(".", ",")


def _button(text: str, slot) -> QPushButton:
    b = QPushButton(text)
    b.clicked.connect(slot)
    return b


def _row(*widgets, stretch_last: bool = False) -> QHBoxLayout:
    lay = QHBoxLayout()
    for k, w in enumerate(widgets):
        lay.addWidget(QLabel(w) if isinstance(w, str) else w, 1 if stretch_last and k == len(widgets) - 1 else 0)
    if not stretch_last:
        lay.addStretch(1)
    return lay


class DragCanvas(ImageCanvas):
    """ImageCanvas báo cả lúc nhả chuột (kéo một hình chữ nhật: vùng ô nháy T14)."""
    released = Signal(float, float, int)

    def mouseReleaseEvent(self, event):
        pos = self.widget_to_image(event.position())
        if pos is not None:
            self.released.emit(pos[0], pos[1], int(event.button().value))
        super().mouseReleaseEvent(event)


class TrackPlot(QWidget):
    """x, y (m) và hướng (°) theo t (s) của các khung hợp lệ, ba dải chồng nhau."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.t: list[float] = []
        self.series: list[list[float]] = [[], [], []]
        self.setMinimumHeight(170)

    def set_data(self, t, x, y, yaw_deg) -> None:
        self.t, self.series = list(t), [list(x), list(y), list(yaw_deg)]
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#101821"))
        font = QFont("Segoe UI")
        font.setPixelSize(11)
        p.setFont(font)
        names = ("x (m)", "y (m)", "hướng (°)")
        colors = ("#5fb3ff", "#7ee08a", "#ffb35f")
        min_span = (0.02, 0.02, 2.0)          # nhiễu dưới mm / phần mười độ không bị phóng to như chuyển động
        h = self.height() / 3.0
        for k, (name, color, values) in enumerate(zip(names, colors, self.series)):
            top = k * h
            p.setPen(QColor("#9cafbe"))
            p.drawText(6, int(top + 14), name)
            if len(values) < 2:
                continue
            t0, t1 = self.t[0], self.t[-1]
            v0, v1 = min(values), max(values)
            if v1 - v0 < min_span[k]:
                mid = (v0 + v1) / 2
                v0, v1 = mid - min_span[k] / 2, mid + min_span[k] / 2
            span_t, span_v = max(t1 - t0, 1e-9), max(v1 - v0, 1e-9)
            p.drawText(self.width() - 140, int(top + 14), f"{_f(v0, 3)} … {_f(v1, 3)}")
            p.setPen(QPen(QColor(color), 1.5))
            pts = [QPointF(60 + (t - t0) / span_t * (self.width() - 70), top + h - 6 - (v - v0) / span_v * (h - 22))
                   for t, v in zip(self.t, values)]
            for a, b in zip(pts, pts[1:]):
                p.drawLine(a, b)


class Worker(threading.Thread):
    """Chạy `fn(stop_event)` trong luồng nền; giữ kết quả hoặc lỗi cho timer của cửa sổ đọc."""

    def __init__(self, fn, name: str):
        super().__init__(daemon=True, name=name)
        self.fn, self.stop_event = fn, threading.Event()
        self.result = None
        self.error: str | None = None

    def run(self):
        try:
            self.result = self.fn(self.stop_event)
        except R.OverheadError as exc:
            self.error = str(exc)
        except Exception as exc:                       # noqa: BLE001 - báo lên giao diện, không làm sập cửa sổ
            self.error = f"lỗi bất ngờ: {exc}\n{traceback.format_exc()}"


class OverheadWindow(QMainWindow):
    def __init__(self, open_camera=None, *, camera_index: int | None = None, camera_name: str = "tren_cao",
                 size: tuple[int, int] = rec.DEFAULT_SIZE, runs_dir=R.DEFAULT_RUNS,
                 track_dir=PROJECT / "runs" / "nghiem_thu"):
        super().__init__()
        self.open_camera_factory, self.camera_index, self.camera_name = open_camera, camera_index, camera_name
        self.size_requested = tuple(size)
        self.runs_dir, self.track_dir = Path(runs_dir), Path(track_dir)
        # thẻ 1
        self.intr: R.OverheadIntrinsics | None = None
        self.survey: R.Survey | None = None
        self.floor_frames: list[np.ndarray] = []
        self.floor_infos: list[dict] = []
        self.floor_source = ""
        self.detected: dict[str, dict] = {}
        self.clicks: dict[str, tuple[float, float]] = {}
        self.fit: R.FloorFit | None = None
        self.click_mode = False
        self._capture: dict | None = None
        # thẻ 2
        self.video: R.OverheadVideo | None = None
        self._video_path: Path | None = None   # video chọn gần nhất (kể cả bị từ chối): nạp lại khi đổi ô danh định
        self.track_fit: R.FloorFit | None = None
        self.track_car: R.VehicleMarkers | None = None
        self.track_tc1: T.Tc1Report | None = None
        self.track_tc1_day: T.Tc1Report | None = None
        self.flash_roi: tuple[int, int, int, int] | None = None
        self.sync_marks: list[dict] | None = None
        self.sync_marks_path: Path | None = None
        self.extraction: Worker | None = None
        self.track_output = None              # (samples, meta, detail, warnings)
        self._progress: dict = {}
        self._latest_image = None
        self._last_preview = 0.0
        self._drag_start: tuple[float, float] | None = None
        self.picking_roi = False
        # thẻ 3
        self.tc1_floor: R.FloorFit | None = None
        self.tc1_car: R.VehicleMarkers | None = None
        self.tc1_worker: Worker | None = None
        self.tc1_report: T.Tc1Report | None = None
        # thẻ 4
        self.camera: rec.RecordingThread | None = None
        self.recorder: rec.OverheadRecorder | None = None
        self.last_recording: dict | None = None
        self._last_live = 0.0
        self._last_shift = 0.0
        self.shift_text = ""
        # chính sách EcoQoS áp lúc khởi động (main): ghi vào khóa ecoqos_policy của tệp ghi; khóa ecoqos thì bộ ghi đọc
        # lại ecoqos_state() lúc ghi (sửa 02/10/2026: trước đây chép trạng thái lúc mở ứng dụng)
        self.ecoqos_policy: dict = {}
        self.message = ""

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_floor_tab(), "1. Mặt sàn")
        self.tabs.addTab(self._build_track_tab(), "2. Trích tư thế")
        self.tabs.addTab(self._build_tc1_tab(), "3. TC-1")
        self.tabs.addTab(self._build_camera_tab(), "4. Ghi video")
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.setTextFormat(Qt.TextFormat.PlainText)
        root = QWidget()
        lay = QVBoxLayout(root)
        lay.addWidget(self.tabs, 1)
        lay.addWidget(self.message_label)
        self.setCentralWidget(root)
        self.setWindowTitle(TITLE)
        self.resize(1500, 920)
        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.refresh()

    # ================================================================== dựng thẻ
    def _build_floor_tab(self) -> QWidget:
        self.floor_canvas = ImageCanvas("sàn trống: mốc dò được / kết quả khớp")
        self.floor_canvas.clicked.connect(self._floor_clicked)
        self.floor_canvas.key.connect(self._floor_key)
        self.dict_box = QComboBox()
        for name in DICTIONARIES:
            self.dict_box.addItem(name, name)
        self.dict_box.currentIndexChanged.connect(lambda _: self._invalidate_fit("đổi từ điển ArUco"))
        self.refine_box = QComboBox()
        for key, label in REFINE_ITEMS:
            self.refine_box.addItem(label, key)
        self.refine_box.currentIndexChanged.connect(lambda _: self._invalidate_fit("đổi cách tinh chỉnh góc"))
        self.floor_table = QTableWidget(0, len(FLOOR_COLUMNS))
        self.floor_table.setHorizontalHeaderLabels(FLOOR_COLUMNS)
        self.floor_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.floor_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.floor_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.floor_inputs = _mono(QLabel(), 11)
        self.floor_summary = _mono(QLabel("chưa khớp"), 11)
        self.btn_detect = _button("Dò mốc", self.detect_floor)
        self.btn_click = _button("Chấm tay điểm đang chọn", self._toggle_click_mode)
        self.btn_fit = _button("Khớp mặt sàn", self.fit_floor)
        self.btn_save_floor = _button("Lưu kết quả khớp…", self._ask_save_floor)
        self.btn_capture = _button(f"Chụp từ camera ({CAPTURE_FRAMES} khung)", self.capture_floor_frames)
        side = QVBoxLayout()
        side.addLayout(_row(_button("Nội tham camera trên cao…", self._ask_intrinsics),
                            _button("Tệp mốc sa bàn…", self._ask_survey)))
        side.addLayout(_row(_button("Ảnh sàn trống…", self._ask_floor_images),
                            _button("Video sàn trống…", self._ask_floor_video), self.btn_capture))
        side.addWidget(self.floor_inputs)
        side.addLayout(_row("Từ điển ArUco", self.dict_box, "Tinh chỉnh góc", self.refine_box, self.btn_detect))
        side.addWidget(self.floor_table, 1)
        side.addLayout(_row(self.btn_click, self.btn_fit, self.btn_save_floor))
        side.addWidget(self.floor_summary)
        legend = QLabel(LEGEND)
        legend.setWordWrap(True)
        side.addWidget(legend)
        return self._split(self.floor_canvas, side)

    def _build_track_tab(self) -> QWidget:
        self.track_canvas = DragCanvas("video: marker xe, thân xe, điểm R1 (kéo chuột để chọn vùng ô nháy T14)")
        self.track_canvas.clicked.connect(self._track_pressed)
        self.track_canvas.released.connect(self._track_released)
        self.track_inputs = _mono(QLabel(), 11)
        self.min_markers_box = QComboBox()
        self.min_markers_box.addItem("2 (mặc định, KICH_BAN 3.6)", 2)
        self.min_markers_box.addItem("1 (khung một marker, có ghi chú)", 1)
        self.window_edit = QLineEdit()
        self.window_edit.setPlaceholderText("A,B giây từ khung đầu (trống = cả video)")
        self.sync_error_edit = QLineEdit()
        self.sync_error_edit.setPlaceholderText(f"trống = tự tính (perf_counter: {R.CAPTURE_LATENCY_S:g} s)")
        self.sync_pairs_edit = QLineEdit()
        self.sync_pairs_edit.setPlaceholderText("18.0=mark:1; 32.0=mark:2")
        self.roi_edit = QLineEdit()
        self.roi_edit.setPlaceholderText("x,y,rộng,cao (px)")
        self.roi_edit.editingFinished.connect(self._roi_typed)
        self.chk_failed_floor = QCheckBox("Cho dùng kết quả khớp chưa đạt (độ chính xác thành null)")
        self.chk_unmeasured = QCheckBox("Cho dùng cấu hình marker chưa đo (độ chính xác thành null)")
        self.chk_tc1_partial = QCheckBox("Nhận TC-1 thiếu yêu cầu (có ghi chú)")
        # như --allow-nominal-fps (thêm 02/10/2026): AVI không kèm tệp của bộ ghi chỉ có số khung/s danh định
        self.chk_nominal_fps = QCheckBox(NOMINAL_FPS_LABEL)
        self.chk_nominal_fps.toggled.connect(self._nominal_fps_toggled)
        self.btn_start = _button("Bắt đầu trích", self.start_extraction)
        self.btn_stop = _button("Dừng", self.stop_extraction)
        self.btn_save_track = _button("Lưu tệp tư thế…", self._ask_save_track)
        self.progress_label = QLabel("chưa trích")
        self.accuracy_label = QLabel()
        self.accuracy_label.setWordWrap(True)
        self.plot = TrackPlot()
        side = QVBoxLayout()
        side.addLayout(_row(_button("Video…", self._ask_video), _button("Kết quả khớp mặt sàn…", self._ask_track_floor),
                            _button("Marker trên xe…", self._ask_track_markers)))
        side.addLayout(_row(_button("Biên bản TC-1…", lambda: self._ask_tc1_report(False)),
                            _button("TC-1 rút gọn trong ngày…", lambda: self._ask_tc1_report(True))))
        side.addWidget(self.track_inputs)
        side.addLayout(_row("Số marker tối thiểu", self.min_markers_box))
        side.addLayout(_row("Khoảng thời gian (s)", self.window_edit, stretch_last=True))
        side.addLayout(_row("Sai số đồng bộ (s)", self.sync_error_edit, stretch_last=True))
        side.addLayout(_row("Cặp đồng bộ", self.sync_pairs_edit, stretch_last=True))
        side.addLayout(_row("Vùng dấu đồng bộ T14", self.roi_edit, _button("Chọn trên ảnh", self._pick_roi),
                            _button("Tệp dấu đồng bộ…", self._ask_sync_marks)))
        for chk in (self.chk_failed_floor, self.chk_unmeasured, self.chk_tc1_partial, self.chk_nominal_fps):
            side.addWidget(chk)
        side.addLayout(_row(self.btn_start, self.btn_stop, self.btn_save_track))
        side.addWidget(self.progress_label)
        side.addWidget(self.accuracy_label)
        side.addWidget(self.plot, 1)
        return self._split(self.track_canvas, side)

    def _build_tc1_tab(self) -> QWidget:
        self.tc1_inputs = _mono(QLabel(), 11)
        self.tc1_table = QTableWidget(0, len(TC1_INPUTS) + len(TC1_RESULTS))
        self.tc1_table.setHorizontalHeaderLabels([label for label, _ in TC1_INPUTS] + TC1_RESULTS)
        self.kind_box = QComboBox()
        self.kind_box.addItem("đầy đủ (≥ 10 tư thế)", "full")
        self.kind_box.addItem("rút gọn trong ngày (≥ 3)", "day")
        self.chk_compare = QCheckBox("So các cách tinh chỉnh góc (đường viền, điểm ảnh con)")
        self.min_frames_spin = QSpinBox()
        self.min_frames_spin.setRange(1, 1000)
        self.min_frames_spin.setValue(T.MIN_VALID_FRAMES)
        self.btn_tc1 = _button("Tính TC-1", self.compute_tc1)
        self.btn_save_tc1 = _button("Lưu biên bản TC-1…", self._ask_save_tc1)
        self.tc1_summary = _mono(QLabel("chưa tính"), 11)
        lay = QVBoxLayout()
        lay.addLayout(_row(_button("Marker xe giả…", self._ask_tc1_markers),
                           _button("Kết quả khớp mặt sàn…", self._ask_tc1_floor)))
        lay.addWidget(self.tc1_inputs)
        lay.addWidget(self.tc1_table, 1)
        lay.addLayout(_row(_button("Thêm dòng", self.add_tc1_row), _button("Xóa dòng", self.remove_tc1_row),
                           _button("Nạp bảng tư thế…", self._ask_tc1_poses),
                           _button("Lưu bảng tư thế…", self._ask_save_tc1_poses)))
        lay.addLayout(_row("Loại", self.kind_box, self.chk_compare, "Khung hợp lệ tối thiểu", self.min_frames_spin,
                           self.btn_tc1, self.btn_save_tc1))
        lay.addWidget(self.tc1_summary)
        page = QWidget()
        page.setLayout(lay)
        return page

    def _build_camera_tab(self) -> QWidget:
        self.live_canvas = ImageCanvas("camera trên cao")
        self.camera_info = QLabel()
        self.camera_info.setWordWrap(True)
        self.btn_open_cam = _button("Mở camera", self.open_camera)
        self.btn_close_cam = _button("Đóng camera", self.close_camera)
        self.rec_dir_edit = QLineEdit(str(self.runs_dir / datetime.now().strftime("%Y%m%d")))
        self.rec_name_edit = QLineEdit("san_trong")
        self.btn_rec = _button("Bắt đầu ghi", self.start_recording)
        self.btn_rec_stop = _button("Dừng ghi", self.stop_recording)
        self.rec_status = QLabel()
        self.rec_status.setWordWrap(True)
        side = QVBoxLayout()
        side.addWidget(self.camera_info)
        side.addLayout(_row(self.btn_open_cam, self.btn_close_cam))
        side.addLayout(_row("Thư mục ghi", self.rec_dir_edit, stretch_last=True))
        side.addLayout(_row("Tên lần ghi", self.rec_name_edit, stretch_last=True))
        side.addLayout(_row(self.btn_rec, self.btn_rec_stop))
        side.addWidget(self.rec_status)
        side.addStretch(1)
        return self._split(self.live_canvas, side)

    @staticmethod
    def _split(canvas: QWidget, side: QVBoxLayout) -> QWidget:
        page = QWidget()
        lay = QHBoxLayout(page)
        lay.addWidget(canvas, 3)
        holder = QWidget()
        holder.setLayout(side)
        holder.setMinimumWidth(560)
        lay.addWidget(holder, 2)
        return page

    # ================================================================== tiện ích
    def _say(self, text: str) -> None:
        self.message = text
        self.message_label.setText(text)

    def _fail(self, exc) -> bool:
        self._say(f"LỖI: {exc}")
        return False

    @property
    def detector(self) -> R.DetectorParams:
        return R.DetectorParams(self.dict_box.currentData(), self.refine_box.currentData())

    def _invalidate_fit(self, why: str = "") -> None:
        if self.fit is not None:
            self._say(f"kết quả khớp cũ mất hiệu lực ({why}): bấm 'Khớp mặt sàn' lại")
        self.fit = None
        self.refresh()

    # ================================================================== thẻ 1: mặt sàn
    def load_intrinsics(self, path) -> bool:
        try:
            self.intr = R.load_overhead_intrinsics(path)
        except R.OverheadError as exc:
            return self._fail(exc)
        self._invalidate_fit("nạp nội tham")
        self._say(f"đã nạp nội tham {path}" + (f" ({R.SYNTHETIC_LABEL})" if self.intr.synthetic else ""))
        return True

    def load_survey(self, path) -> bool:
        try:
            self.survey = R.read_survey(path, self.dict_box.currentData())
        except R.OverheadError as exc:
            return self._fail(exc)
        self.detected, self.clicks = {}, {}
        self._invalidate_fit("đổi tệp mốc")
        self._say(f"đã nạp {len(self.survey.points)} mốc từ {path}")
        return True

    def load_floor_images(self, paths) -> bool:
        try:
            frames, infos = R.floor_inputs(images=[Path(p) for p in paths])
        except R.OverheadError as exc:
            return self._fail(exc)
        return self._set_floor_frames(frames, infos, f"{len(frames)} ảnh")

    def load_floor_video(self, path, frames: int = R.FLOOR_FRAMES) -> bool:
        try:
            images, infos = R.floor_inputs(video=Path(path), frames=frames)
        except R.OverheadError as exc:
            return self._fail(exc)
        return self._set_floor_frames(images, infos, f"{len(images)} khung đầu của {Path(path).name}")

    def _set_floor_frames(self, frames, infos, label: str) -> bool:
        if not frames:
            return self._fail("không có khung sàn trống nào")
        self.floor_frames, self.floor_infos, self.floor_source = list(frames), list(infos), label
        self.detected = {}
        self._invalidate_fit("đổi ảnh sàn trống")
        self.floor_canvas.set_image(self.floor_frames[0])
        return True

    def detect_floor(self) -> int:
        """Dò marker trên mọi khung sàn trống; điền bảng (chưa khớp). Trả số mốc của tệp mốc thấy được."""
        if self.intr is None or self.survey is None or not self.floor_frames:
            self._fail("cần nội tham, tệp mốc và ảnh sàn trống")
            return 0
        params = self.detector
        detector = params.build()
        by_id = self.survey.by_id()
        seen: dict[str, list] = {}
        for img in self.floor_frames:
            for mid, corners in R.detect_markers(img, params, detector=detector).items():
                if mid in by_id:
                    seen.setdefault(by_id[mid].name, []).append(R.marker_centre_px(corners, self.intr))
        need = R.MIN_SEEN_FRACTION * len(self.floor_frames)
        self.detected = {name: {"uv": np.median(np.array(uvs), axis=0), "n": len(uvs)} for name, uvs in seen.items()
                         if len(uvs) >= need}
        self._invalidate_fit("dò lại")
        self._say(f"thấy {len(self.detected)}/{len(self.survey.points)} mốc trên {len(self.floor_frames)} khung")
        self.refresh()
        return len(self.detected)

    def selected_point(self) -> str | None:
        row = self.floor_table.currentRow()
        if row < 0 or self.survey is None or row >= len(self.survey.points):
            return None
        return self.survey.points[row].name

    def set_manual_point(self, name: str, u: float, v: float) -> bool:
        if self.survey is None or name not in self.survey.by_name():
            return self._fail(f"không có mốc {name!r} trong tệp mốc")
        self.clicks[name] = (float(u), float(v))
        self._invalidate_fit(f"chấm tay {name}")
        return True

    def clear_manual_point(self, name: str) -> None:
        if self.clicks.pop(name, None) is not None:
            self._invalidate_fit(f"bỏ điểm chấm tay {name}")

    def fit_floor(self) -> bool:
        if self.intr is None or self.survey is None or not (self.floor_frames or self.clicks):
            return self._fail("cần nội tham, tệp mốc và ảnh sàn trống")
        try:
            self.fit = R.fit_floor(self.floor_frames, self.intr, self.survey, params=self.detector, clicks=self.clicks,
                                   image_infos=self.floor_infos)
        except R.OverheadError as exc:
            self.fit = None
            self.refresh()
            return self._fail(exc)
        self.click_mode = False
        self.refresh()
        self._say("khớp xong: " + ("ĐẠT" if self.fit.ok else "CHƯA ĐẠT") + " — xem tóm tắt; 'Lưu kết quả khớp…'")
        return True

    def save_floor(self, path, overwrite: bool = False) -> Path | None:
        if self.fit is None:
            self._fail("chưa có kết quả khớp hợp lệ (bấm 'Khớp mặt sàn')")
            return None
        try:
            out, jpg = R.save_floor_fit(path, self.fit, overwrite=overwrite,
                                        image=self.floor_frames[0] if self.floor_frames else None)
        except (R.OverheadError, OSError) as exc:
            self._fail(exc)
            return None
        self.track_fit = self.tc1_floor = self.fit                   # dùng ngay cho thẻ 2 và 3
        self._say(f"đã ghi {out}" + (f" và {jpg.name}" if jpg else ""))
        self.refresh()
        return out

    def capture_floor_frames(self, n: int = CAPTURE_FRAMES) -> bool:
        if self.camera is None or not self.camera.is_alive():
            return self._fail("mở camera ở thẻ 4 trước")
        folder = self.runs_dir / datetime.now().strftime("%Y%m%d") / f"san_trong_{datetime.now():%H%M%S}"
        self._capture = {"n": n, "frames": [], "last": None, "folder": folder}
        self._say(f"đang chụp {n} khung sàn trống…")
        return True

    def _capture_tick(self) -> None:
        cap = self._capture
        frame = self.camera.latest() if self.camera is not None else None
        if cap is None or frame is None or frame is cap["last"]:
            return
        cap["last"] = frame
        cap["frames"].append(frame.image.copy())
        if len(cap["frames"]) < cap["n"]:
            return
        self._capture = None
        cap["folder"].mkdir(parents=True, exist_ok=True)
        infos = []
        for k, img in enumerate(cap["frames"]):
            path = cap["folder"] / f"khung_{k:02d}.png"
            ok, buf = cv2.imencode(".png", img)
            if ok:
                path.write_bytes(buf.tobytes())
                infos.append({"path": str(path), "sha256": R.file_sha256(path), "frames": 1})
        self._set_floor_frames(cap["frames"], infos, f"{len(cap['frames'])} khung chụp vào {cap['folder']}")

    def _toggle_click_mode(self) -> None:
        if self.selected_point() is None:
            self._fail("chọn một mốc trong bảng trước")
            return
        self.click_mode = not self.click_mode
        self._say(f"chấm tay {self.selected_point()}: chuột trái đặt, chuột phải xóa, Esc thôi" if self.click_mode
                  else "thôi chấm tay")

    def _floor_clicked(self, x: float, y: float, button: int) -> None:
        name = self.selected_point()
        if not self.click_mode or name is None:
            return
        if button == Qt.MouseButton.LeftButton.value:
            self.set_manual_point(name, x, y)
        elif button == Qt.MouseButton.RightButton.value:
            self.clear_manual_point(name)
        self.refresh()

    def _floor_key(self, key: int) -> None:
        if key == Qt.Key.Key_Escape.value and self.click_mode:
            self.click_mode = False
            self._say("thôi chấm tay")

    def _floor_table_rows(self) -> list[list[str]]:
        rows = []
        if self.survey is None:
            return rows
        errors = {}
        if self.fit is not None:
            errors = {r["ten"]: r for r in self.fit.residuals}
            errors.update({r["ten"]: r for r in self.fit.check.get("points", [])})
        dropped = {d["ten"]: d["reason"] for d in self.fit.dropped} if self.fit is not None else {}
        missing = {m["ten"]: m["reason"] for m in self.fit.missing} if self.fit is not None else {}
        for p in self.survey.points:
            if p.name in self.clicks:
                source, uv = "chấm tay", self.clicks[p.name]
            elif p.name in self.detected:
                source, uv = "ArUco", self.detected[p.name]["uv"]
            else:
                source, uv = "—", None
            err = errors.get(p.name)
            note = dropped.get(p.name) or missing.get(p.name) or ("chưa đo" if not p.measured else "")
            rows.append([p.name, p.role, "" if p.marker_id is None else str(p.marker_id), source,
                         _f(uv[0] if uv is not None else None), _f(uv[1] if uv is not None else None),
                         _f(err["err_m"] * 1000, 2) if err else "", note])
        return rows

    def _refresh_floor(self) -> None:
        self.floor_inputs.setText(
            f"nội tham: {self.intr.path if self.intr else '—'}"
            + (f" ({R.SYNTHETIC_LABEL})" if self.intr is not None and self.intr.synthetic else "")
            + f"\ntệp mốc: {self.survey.path if self.survey else '—'}\nsàn trống: {self.floor_source or '—'}")
        rows = self._floor_table_rows()
        current = self.floor_table.currentRow()
        self.floor_table.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, value in enumerate(values):
                self.floor_table.setItem(r, c, QTableWidgetItem(value))
        if 0 <= current < len(rows):
            self.floor_table.selectRow(current)
        self.btn_save_floor.setEnabled(self.fit is not None)
        self.btn_capture.setEnabled(self.camera is not None)
        self.floor_summary.setText("\n".join(R.floor_summary_lines(self.fit)) if self.fit is not None else "chưa khớp")
        if not self.floor_frames:
            self.floor_canvas.set_image(None, "nạp ảnh hay video sàn trống (không có xe)")
            return
        if self.fit is not None:
            self.floor_canvas.set_image(R.draw_floor_overlay(self.floor_frames[0], self.fit))
            return
        img = self.floor_frames[0].copy()
        for name, det in self.detected.items():
            cv2.circle(img, tuple(int(round(v)) for v in det["uv"]), 6, (0, 200, 0), 2, cv2.LINE_AA)
        for name, uv in self.clicks.items():
            cv2.drawMarker(img, tuple(int(round(v)) for v in uv), (0, 200, 255), cv2.MARKER_CROSS, 14, 2)
        self.floor_canvas.set_image(img)

    # ================================================================== thẻ 2: trích tư thế
    def load_track_video(self, path) -> bool:
        self._video_path = Path(path)
        try:
            self.video = R.OverheadVideo(path, allow_nominal_fps=self.chk_nominal_fps.isChecked())
        except R.OverheadError as exc:
            self.video = None                       # không giữ video cũ khi video mới bị từ chối
            self.track_output = None
            self.refresh()
            hint = (f" (giao diện: đánh dấu '{NOMINAL_FPS_LABEL}')" if "--allow-nominal-fps" in str(exc) else "")
            return self._fail(f"{exc}{hint}")
        cap = cv2.VideoCapture(str(path))
        ok, image = cap.read()
        cap.release()
        if ok:
            self.track_canvas.set_image(image)
            self._latest_image = image
        self.track_output = None
        self.refresh()
        return True

    def _nominal_fps_toggled(self, _checked: bool) -> None:
        """Đổi ô 'số khung/s danh định': nạp lại video đang chọn theo luật mới (nhận, hay từ chối như dòng lệnh). Video
        của bộ ghi (đồng hồ perf_counter) không phụ thuộc ô này: giữ nguyên, kể cả kết quả trích chưa lưu."""
        if self._video_path is None or (self.extraction is not None and self.extraction.is_alive()):
            return
        if self.video is not None and self.video.clock == "perf_counter":
            return
        self.load_track_video(self._video_path)

    def load_track_floor(self, path) -> bool:
        try:
            self.track_fit = R.load_floor_fit(path)
        except R.OverheadError as exc:
            return self._fail(exc)
        self.track_output = None
        self.refresh()
        return True

    def load_track_markers(self, path) -> bool:
        try:
            self.track_car = R.load_vehicle_markers(path)
        except R.OverheadError as exc:
            return self._fail(exc)
        self.track_output = None
        self.refresh()
        return True

    def load_track_tc1(self, path, day: bool = False) -> bool:
        try:
            report = T.load_tc1(path)
        except R.OverheadError as exc:
            return self._fail(exc)
        if day:
            self.track_tc1_day = report
        else:
            self.track_tc1 = report
        self.track_output = None
        self.refresh()
        return True

    def load_sync_marks(self, path) -> bool:
        from autopark.evaluation.sync_marks import read_sync_marks

        try:
            self.sync_marks = [m for m in read_sync_marks(path) if m.get("kind") == "SYNC_MARK"]
        except (OSError, ValueError, KeyError) as exc:
            return self._fail(f"không đọc được tệp dấu đồng bộ {path}: {exc}")
        self.sync_marks_path = Path(path)
        self.refresh()
        return True

    def set_flash_roi(self, roi) -> None:
        self.flash_roi = None if roi is None else tuple(int(round(v)) for v in roi)
        self.roi_edit.setText("" if roi is None else ",".join(str(v) for v in self.flash_roi))
        self.refresh()

    def _roi_typed(self) -> None:
        text = self.roi_edit.text().strip()
        if not text:
            self.set_flash_roi(None)
            return
        try:
            values = [int(float(v)) for v in text.replace(";", ",").split(",")]
            if len(values) != 4 or values[2] <= 0 or values[3] <= 0:
                raise ValueError
        except ValueError:
            self._fail("vùng ô nháy cần x,y,rộng,cao (px)")
            return
        self.set_flash_roi(values)

    def _pick_roi(self) -> None:
        self.picking_roi = True
        self._say("kéo chuột trên ảnh video quanh phần TRONG của ô nháy T14")

    def _track_pressed(self, x: float, y: float, button: int) -> None:
        if self.picking_roi and button == Qt.MouseButton.LeftButton.value:
            self._drag_start = (x, y)

    def _track_released(self, x: float, y: float, button: int) -> None:
        if not self.picking_roi or self._drag_start is None:
            return
        (x0, y0), self._drag_start, self.picking_roi = self._drag_start, None, False
        w, h = abs(x - x0), abs(y - y0)
        if w < 3 or h < 3:
            self._fail("vùng quá nhỏ: kéo một hình chữ nhật")
            return
        self.set_flash_roi((min(x, x0), min(y, y0), w, h))

    def _track_options(self) -> R.TrackOptions:
        window = None
        text = self.window_edit.text().strip()
        if text:
            try:
                a, b = (float(v) for v in text.replace(";", ",").split(","))
            except ValueError:
                raise R.OverheadError("khoảng thời gian cần A,B (giây từ khung đầu)") from None
            if not a < b:
                raise R.OverheadError("khoảng thời gian cần A < B")
            window = (a, b)
        return R.TrackOptions(int(self.min_markers_box.currentData()), window, self.flash_roi)

    def _sync_inputs(self) -> tuple[list, float | None]:
        pairs = []
        for part in self.sync_pairs_edit.text().replace(",", ";").split(";"):
            if part.strip():
                try:
                    pairs.append(R._sync_arg(part.strip()))
                except argparse.ArgumentTypeError as exc:
                    raise R.OverheadError(f"cặp đồng bộ {part.strip()!r}: {exc}") from None
        text = self.sync_error_edit.text().strip().replace(",", ".")
        try:
            error = float(text) if text else None
        except ValueError:
            raise R.OverheadError("sai số đồng bộ phải là số giây") from None
        return pairs, R.check_seconds("sai số đồng bộ", error)       # hữu hạn ≥ 0, như --sync-error

    def start_extraction(self) -> bool:
        if self.extraction is not None and self.extraction.is_alive():
            return self._fail("đang trích")
        if self.video is None or self.track_fit is None or self.track_car is None:
            return self._fail("cần video, kết quả khớp mặt sàn và cấu hình marker xe")
        try:
            options = self._track_options()
            pairs, sync_error = self._sync_inputs()
            R.check_track_inputs(self.track_fit, self.track_car, self.video,
                                 allow_failed_floor=self.chk_failed_floor.isChecked(),
                                 allow_unmeasured=self.chk_unmeasured.isChecked())
            if self.flash_roi is not None:
                x, y, w, h = self.flash_roi
                if x < 0 or y < 0 or x + w > self.video.size[0] or y + h > self.video.size[1]:
                    raise R.OverheadError("vùng ô nháy nằm ngoài ảnh")
            video = R.OverheadVideo(self.video.path, allow_nominal_fps=self.chk_nominal_fps.isChecked())
        except R.OverheadError as exc:
            return self._fail(exc)
        fit, car = self.track_fit, self.track_car
        tc1, tc1_day, marks = self.track_tc1, self.track_tc1_day, self.sync_marks
        allow = {name for name, chk in (("tc1_chua_du", self.chk_tc1_partial), ("cau_hinh_chua_do", self.chk_unmeasured),
                                        ("mat_san_chua_dat", self.chk_failed_floor),
                                        ("nominal_fps", self.chk_nominal_fps)) if chk.isChecked()}
        total = len(video)
        self._progress = {"total": total, "frames": 0, "valid": 0, "two": 0, "shift": None, "points": []}
        self.track_output = None

        def frames():
            for frame in video:
                self._latest_image = frame.image
                yield frame

        def progress(fp, counts):
            self._progress.update(frames=counts["frames"], valid=counts["valid"], two=counts["two_marker"],
                                  shift=fp.floor_shift_px, last=fp)
            if fp.valid:
                self._progress["points"].append((fp.t, fp.pose.x, fp.pose.y, math.degrees(fp.pose.yaw)))

        def work(stop):
            result = R.extract_track(frames(), fit, car, options, progress=progress, stop=stop, clock=video.clock,
                                     source_info=video.source_info())
            if stop.is_set():
                return None
            return R.build_reference(result, fit, car, video, tc1=tc1, tc1_day=tc1_day, sync=pairs,
                                     sync_error_s=sync_error, allow_flags=allow, marks=marks)

        self.extraction = Worker(work, "overhead_extract")
        self.extraction.start()
        self._say("đang trích tư thế…")
        self.refresh()
        return True

    def stop_extraction(self) -> None:
        if self.extraction is not None and self.extraction.is_alive():
            self.extraction.stop_event.set()
            self._say("đã yêu cầu dừng trích")

    def default_track_path(self) -> Path:
        stem = self.video.path.stem if self.video is not None else "video"
        return self.track_dir / datetime.now().strftime("%Y%m%d") / stem / "tu_the_tham_chieu.csv"

    def save_track(self, path=None, overwrite: bool = False):
        if self.track_output is None:
            self._fail("chưa có kết quả trích")
            return None
        samples, meta, detail, _ = self.track_output
        try:
            paths = R.write_track(path or self.default_track_path(), samples, meta, detail, overwrite)
        except (R.OverheadError, OSError, ValueError) as exc:
            self._fail(exc)
            return None
        if paths[0] is None:
            self._fail(f"không khung nào hợp lệ: chỉ ghi {paths[2]}")
        else:
            self._say(f"đã ghi {paths[0]}, {paths[1].name}, {paths[2].name}")
        return paths

    def _poll_extraction(self) -> None:
        w = self.extraction
        if w is None:
            return
        if w.is_alive():
            self._preview_tick()
            return
        self.extraction = None
        if w.error:
            self._fail(w.error)
        elif w.result is None:
            self._say("đã dừng trích (không có kết quả để lưu)")
        else:
            self.track_output = w.result
            samples, meta, _, warnings = w.result
            valid = sum(s.valid for s in samples)
            self._say(f"trích xong: {len(samples)} khung, {valid} hợp lệ" + "".join(f"\nCẢNH BÁO: {x}"
                                                                                for x in warnings))
        self._preview_tick(force=True)
        self.refresh()

    def _preview_tick(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_preview < PREVIEW_EVERY_S:
            return
        self._last_preview = now
        p = self._progress
        if p:
            total = p.get("total") or 0
            frames = max(1, p.get("frames", 0))
            self.progress_label.setText(
                f"Khung {p.get('frames', 0)}/{total} · hợp lệ {100 * p.get('valid', 0) / frames:.0f} % · hai marker "
                f"{100 * p.get('two', 0) / frames:.0f} % · camera lệch {_f(p.get('shift'))} px")
            pts = p.get("points") or []
            if pts:
                t0 = pts[0][0]
                self.plot.set_data([q[0] - t0 for q in pts], [q[1] for q in pts], [q[2] for q in pts],
                                   [q[3] for q in pts])
        image = self._latest_image
        if image is not None:
            self.track_canvas.set_image(self._draw_preview(image, p.get("last") if p else None))

    def _draw_preview(self, image: np.ndarray, fp) -> np.ndarray:
        out = image.copy()
        fit = self.track_fit
        if self.flash_roi is not None:
            x, y, w, h = self.flash_roi
            cv2.rectangle(out, (x, y), (x + w, y + h), (0, 220, 255), 2)
        if fp is None or fit is None:
            return out
        for role, mp in fp.markers.items():
            z = next((m.z for m in self.track_car.markers if m.role == role), 0.0) if self.track_car else 0.0
            uv = fit.camera.project(np.column_stack([mp.corners_xy, np.full(4, z)]))
            if np.all(np.isfinite(uv)):
                cv2.polylines(out, [np.round(uv).astype(np.int32)], True, (0, 220, 0), 2, cv2.LINE_AA)
        if fp.pose is not None:
            from autopark.geometry.footprint import body_corners

            cfg = self._vehicle_cfg()
            if cfg is not None:
                corners = body_corners(cfg, fp.pose)
                body = np.array(corners + corners[:1])
                uv = fit.camera.project(np.column_stack([body, np.zeros(len(body))]))
                if np.all(np.isfinite(uv)):
                    cv2.polylines(out, [np.round(uv).astype(np.int32)], False, (255, 160, 0), 2, cv2.LINE_AA)
            c = fit.camera.project([[fp.pose.x, fp.pose.y, 0.0]])[0]
            if np.all(np.isfinite(c)):
                cv2.drawMarker(out, (int(round(c[0])), int(round(c[1]))), (0, 0, 255), cv2.MARKER_CROSS, 16, 2)
        elif fp.reason:
            cv2.putText(out, "khong hop le", (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
        return out

    def _vehicle_cfg(self):
        """Cấu hình xe (configs/vehicle_default.json) để vẽ thân xe ở ảnh xem trước; đọc một lần."""
        if not hasattr(self, "_cfg_cache"):
            from autopark.storage.scenario_store import load_vehicle_config

            try:
                self._cfg_cache = load_vehicle_config(T.DEFAULT_VEHICLE)
            except (OSError, ValueError, KeyError):
                self._cfg_cache = None
        return self._cfg_cache

    def accuracy_text(self) -> str:
        """Dòng 'Độ chính xác: …' sẽ ghi vào tệp mô tả (theo luật chép của TC-1)."""
        if self.track_fit is None or self.track_car is None:
            return "Độ chính xác: — (chưa đủ đầu vào)"
        if self.track_output is not None:
            acc = self.track_output[1].accuracy
        else:
            date = self.video.date if self.video is not None else datetime.now().date().isoformat()
            acc, _ = T.accuracy_for_track(self.track_fit, self.track_car, date, self.track_tc1, self.track_tc1_day,
                                          self.chk_tc1_partial.isChecked())
            forced = (not self.track_car.measured) or (not self.track_fit.ok)
            if forced and acc.pos_max_m is not None:
                return "Độ chính xác: CHƯA CÓ (T5 sẽ ghi không kiểm được) vì cấu hình marker chưa đo hay khớp chưa đạt"
        if acc.pos_max_m is None:
            return f"Độ chính xác: CHƯA CÓ (T5 sẽ ghi không kiểm được) vì {acc.source}"
        return (f"Độ chính xác: từ TC-1 — vị trí ≤ {_f(acc.pos_max_m * 1000, 1)} mm, hướng ≤ {_f(acc.yaw_max_deg, 2)}° "
                f"({acc.source})")

    def _refresh_track(self) -> None:
        clock = "—"
        if self.video is not None:
            clock = (f"perf_counter (máy {self.video.host or '?'})" if self.video.clock == "perf_counter" else "video")
        self.track_inputs.setText(
            f"video: {self.video.path if self.video else '—'}\nĐồng hồ: {clock}\n"
            f"khớp mặt sàn: {self.track_fit.path if self.track_fit else '—'}"
            + ("" if self.track_fit is None or self.track_fit.ok else " (CHƯA ĐẠT)")
            + f"\nmarker xe: {self.track_car.path if self.track_car else '—'}"
            + (" (GIẢ ĐỊNH, chưa đo)" if self.track_car is not None and not self.track_car.measured else "")
            + f"\nTC-1: {self.track_tc1.path if self.track_tc1 else '—'} · trong ngày: "
            f"{self.track_tc1_day.path if self.track_tc1_day else '—'}\n"
            f"dấu đồng bộ: {self.sync_marks_path or '—'}")
        busy = self.extraction is not None and self.extraction.is_alive()
        self.btn_start.setEnabled(not busy)
        self.btn_stop.setEnabled(busy)
        self.btn_save_track.setEnabled(self.track_output is not None and not busy)
        self.accuracy_label.setText(self.accuracy_text())

    # ================================================================== thẻ 3: TC-1
    def load_tc1_markers(self, path) -> bool:
        try:
            self.tc1_car = R.load_vehicle_markers(path)
        except R.OverheadError as exc:
            return self._fail(exc)
        self.refresh()
        return True

    def load_tc1_floor(self, path) -> bool:
        try:
            self.tc1_floor = R.load_floor_fit(path)
        except R.OverheadError as exc:
            return self._fail(exc)
        self.refresh()
        return True

    def load_tc1_poses(self, path) -> bool:
        try:
            poses = T.read_tc1_poses(path)
        except R.OverheadError as exc:
            return self._fail(exc)
        self.tc1_table.setRowCount(0)
        for p in poses:
            values = {"tu_the": p.name, "video": str(p.video),
                      "t_tu_s": "" if p.window is None else f"{p.window[0]:g}",
                      "t_den_s": "" if p.window is None else f"{p.window[1]:g}",
                      "x_sau_m": f"{p.rear[0]:.4f}", "y_sau_m": f"{p.rear[1]:.4f}", "x_truoc_m": f"{p.front[0]:.4f}",
                      "y_truoc_m": f"{p.front[1]:.4f}", "x_tam_m": "" if p.centre is None else f"{p.centre[0]:.4f}",
                      "y_tam_m": "" if p.centre is None else f"{p.centre[1]:.4f}", "nguoi_do": p.measured_by,
                      "ngay": p.date}
            self.add_tc1_row(values)
        self._say(f"đã nạp {len(poses)} tư thế từ {path}")
        return True

    def add_tc1_row(self, values: dict | None = None) -> None:
        r = self.tc1_table.rowCount()
        self.tc1_table.insertRow(r)
        values = values or {"tu_the": f"tu_the_{r + 1:02d}", "ngay": datetime.now().strftime("%d/%m/%Y")}
        for c, (_, key) in enumerate(TC1_INPUTS):
            self.tc1_table.setItem(r, c, QTableWidgetItem(str(values.get(key, ""))))
        for c in range(len(TC1_INPUTS), self.tc1_table.columnCount()):
            item = QTableWidgetItem("")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tc1_table.setItem(r, c, item)

    def remove_tc1_row(self) -> None:
        r = self.tc1_table.currentRow()
        if r >= 0:
            self.tc1_table.removeRow(r)

    def tc1_rows(self) -> list[dict]:
        rows = []
        for r in range(self.tc1_table.rowCount()):
            row = {}
            for c, (_, key) in enumerate(TC1_INPUTS):
                item = self.tc1_table.item(r, c)
                row[key] = item.text().strip() if item is not None else ""
            if any(row.values()):
                rows.append(row)
        return rows

    def save_tc1_poses(self, path) -> Path | None:
        path = Path(path)
        rows = []
        for row in self.tc1_rows():
            video = Path(row["video"])
            try:
                row = dict(row, video=os.path.relpath(video, path.parent) if video.is_absolute() else row["video"])
            except ValueError:                                # ổ đĩa khác: giữ đường dẫn tuyệt đối
                pass
            rows.append(row)
        try:
            R.check_output_path(path, False, True)
            path.parent.mkdir(parents=True, exist_ok=True)
            R.backup_existing(path)
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=T.POSE_FIELDS, extrasaction="ignore", lineterminator="\n")
                w.writeheader()
                w.writerows({**dict.fromkeys(T.POSE_FIELDS, ""), **r} for r in rows)
        except (R.OverheadError, OSError) as exc:
            self._fail(exc)
            return None
        self._say(f"đã ghi bảng tư thế {path}")
        return path

    def _poses_from_table(self) -> list[T.Tc1Pose]:
        folder = Path(tempfile.mkdtemp(prefix="tc1_bang_"))
        try:
            path = folder / "tu_the.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=T.POSE_FIELDS, extrasaction="ignore", lineterminator="\n")
                w.writeheader()
                for r in self.tc1_rows():
                    w.writerow({**dict.fromkeys(T.POSE_FIELDS, ""), **r, "video": str(Path(r["video"]).resolve())})
            return T.read_tc1_poses(path)
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def compute_tc1(self, kind: str | None = None, compare: bool | None = None) -> bool:
        if self.tc1_worker is not None and self.tc1_worker.is_alive():
            return self._fail("đang tính TC-1")
        fit = self.tc1_floor or self.fit or self.track_fit
        car = self.tc1_car
        if fit is None or car is None:
            return self._fail("cần kết quả khớp mặt sàn (đã lưu) và cấu hình marker xe giả")
        if kind is not None:
            self.kind_box.setCurrentIndex(self.kind_box.findData(kind))
        if compare is not None:
            self.chk_compare.setChecked(compare)
        try:
            if fit.path is None:
                raise R.OverheadError("lưu kết quả khớp mặt sàn trước (biên bản TC-1 ghi SHA-256 của tệp đó)")
            T.check_tc1_inputs(fit, car)          # như lệnh `overhead_ref tc1`: khớp chưa đạt, cấu hình chưa đo
            poses = self._poses_from_table()
        except R.OverheadError as exc:
            return self._fail(exc)
        kind = self.kind_box.currentData()
        methods = [m for m in ("contour", "subpix") if m != fit.detector.refine] if self.chk_compare.isChecked() else []
        min_frames = self.min_frames_spin.value()
        self.tc1_report = None

        def work(stop):
            return T.run_tc1(poses, fit, car, kind=kind, compare=methods, stop=stop, min_valid_frames=min_frames)

        self.tc1_worker = Worker(work, "overhead_tc1")
        self.tc1_worker.start()
        self._say(f"đang tính TC-1 ({len(poses)} tư thế)…")
        self.refresh()
        return True

    def save_tc1(self, path, overwrite: bool = False) -> Path | None:
        if self.tc1_report is None:
            self._fail("chưa có kết quả TC-1")
            return None
        try:
            out = T.save_tc1(path, self.tc1_report, overwrite)
        except (R.OverheadError, OSError) as exc:
            self._fail(exc)
            return None
        self.track_tc1 = self.tc1_report if self.tc1_report.kind == "full" else self.track_tc1
        self._say(f"đã ghi biên bản TC-1 {out}")
        self.refresh()
        return out

    def _poll_tc1(self) -> None:
        w = self.tc1_worker
        if w is None or w.is_alive():
            return
        self.tc1_worker = None
        if w.error:
            self._fail(w.error)
        elif w.result is not None:
            self.tc1_report = w.result
            by_name = {e["tu_the"]: e for e in w.result.record["poses"]}
            for r in range(self.tc1_table.rowCount()):
                item = self.tc1_table.item(r, 0)
                e = by_name.get(item.text().strip() if item else "")
                cells = ["", "", ""] if e is None else (
                    ["LOẠI", e["excluded"], ""] if "excluded" in e else
                    [_f(e["err_pos_m"] * 1000, 1), _f(e["err_yaw_deg"], 2), _f(e["spread"]["pos_p95_m"] * 1000, 1)])
                for k, text in enumerate(cells):
                    self.tc1_table.item(r, len(TC1_INPUTS) + k).setText(text)
            self._say("TC-1 xong: " + w.result.requirements["status"])
        self.refresh()

    def _refresh_tc1(self) -> None:
        fit = self.tc1_floor or self.fit or self.track_fit
        self.tc1_inputs.setText(f"marker xe giả: {self.tc1_car.path if self.tc1_car else '—'}\n"
                                f"khớp mặt sàn: {fit.path if fit is not None and fit.path else '— (lưu trước)'}")
        busy = self.tc1_worker is not None and self.tc1_worker.is_alive()
        self.btn_tc1.setEnabled(not busy)
        self.btn_save_tc1.setEnabled(self.tc1_report is not None and not busy)
        if self.tc1_report is not None:
            lines = T.summary_lines(self.tc1_report)
            self.tc1_summary.setText("\n".join(lines[:4]))
        elif busy:
            self.tc1_summary.setText("đang tính…")

    # ================================================================== thẻ 4: camera
    def open_camera(self) -> bool:
        if self.open_camera_factory is None:
            return self._fail("chạy giao diện với --index N để mở camera trên cao (tra bằng camera_bench list)")
        if self.camera is not None and self.camera.is_alive():
            return True
        w, h = self.size_requested
        factory = self.open_camera_factory
        self.camera = rec.RecordingThread(lambda: factory(None, w, h))
        self.camera.start()
        self._say("đang mở camera…")
        self.refresh()
        return True

    def close_camera(self) -> None:
        if self.camera is None:
            return
        if self.camera.recording is not None:
            self.stop_recording()
        self.camera.stop(CLOSE_WAIT_S)
        self.camera = None
        self._capture = None
        self.live_canvas.set_image(None, "camera đã đóng")
        self.refresh()

    def start_recording(self, out_dir=None, name: str | None = None) -> bool:
        if self.camera is None or not self.camera.is_alive() or self.camera.latest() is None:
            return self._fail("mở camera và chờ có hình trước khi ghi")
        out_dir = Path(out_dir or self.rec_dir_edit.text().strip())
        name = name or self.rec_name_edit.text().strip()
        try:
            free = rec.disk_free_gb(out_dir)
            if free < rec.MIN_FREE_GB:
                raise rec.RecorderError(f"ổ đĩa chỉ còn {free:.1f} GB (< {rec.MIN_FREE_GB:g} GB)")
            recorder = rec.OverheadRecorder(out_dir, name)          # tên đã có: từ chối (giao diện không ghi đè)
            info = {"index": self.camera_index, "name": self.camera_name,
                    "requested": {"width": self.size_requested[0], "height": self.size_requested[1]}}
            self.camera.start_recording(recorder, info, ecoqos_policy=self.ecoqos_policy or None)
        except (rec.RecorderError, OSError, ValueError) as exc:
            return self._fail(exc)
        self.recorder = recorder
        self._rec_t0 = time.monotonic()
        self._say(f"đang ghi {recorder.paths['video']}" + (f" (CẢNH BÁO: ổ còn {free:.0f} GB)"
                                                            if free < rec.WARN_FREE_GB else ""))
        self.refresh()
        return True

    def stop_recording(self) -> dict | None:
        if self.camera is None or self.recorder is None:
            return None
        meta = self.camera.stop_recording()
        paths = self.recorder.paths
        self.recorder, self.last_recording = None, meta
        if meta is not None:
            self._say(f"đã ghi {paths['video']}: {meta['frames']} khung, {meta.get('fps_real')} khung/s")
        self.refresh()
        return meta

    def _camera_tick(self) -> None:
        cam = self.camera
        if cam is None:
            return
        if cam.error:
            self._fail(cam.error)
            self.camera = None
            self.refresh()
            return
        now = time.monotonic()
        frame = cam.latest()
        if frame is not None and now - self._last_live >= LIVE_EVERY_S:
            self._last_live = now
            fit = self.fit or self.track_fit
            if fit is not None and now - self._last_shift >= SHIFT_EVERY_S:
                self._last_shift = now
                monitor = R.FloorShiftMonitor(fit)
                shift, seen, _ = monitor.update(0, R.detect_markers(frame.image, fit.detector))
                self.shift_text = (f"Camera lệch so với lúc khớp: {_f(shift, 1)} px" if shift is not None else
                                   f"Camera lệch: không đo được (thấy {seen} mốc sàn)")
                self._refresh_camera()
            self.live_canvas.set_image(frame.image)
        if self._capture is not None:
            self._capture_tick()
        rec_now = self.recorder
        if rec_now is not None:
            elapsed = now - getattr(self, "_rec_t0", now)
            size_mb = rec_now.paths["video"].stat().st_size / 1e6 if rec_now.paths["video"].exists() else 0.0
            fps = (rec_now.frames - 1) / (rec_now.t_last - rec_now.t_first) if rec_now.frames > 1 else 0.0
            broken = sum(rec_now.counts.values())
            self.rec_status.setText(
                f"Đang ghi {int(elapsed) // 60:02d}:{int(elapsed) % 60:02d} · {_f(fps)} khung/s · khung hỏng {broken} · "
                f"{size_mb:.0f} MB · ổ còn {rec.disk_free_gb(rec_now.out_dir):.0f} GB")
        if cam.record_error:
            self._fail(cam.record_error)
            cam.record_error = None
            if self.recorder is not None:               # bộ ghi đã đóng tệp (trạng thái "lỗi"): hiện như lần ghi cuối
                self.last_recording = dict(self.recorder.meta)
            self.recorder = None
            self.refresh()

    def _refresh_camera(self) -> None:
        has_factory = self.open_camera_factory is not None
        live = self.camera is not None
        if not has_factory:
            self.camera_info.setText("Chưa chọn camera: chạy `python -m autopark.ui.overhead_app --index N "
                                     "[--camera-name tren_cao] [--size 1280x720]`, với N tra bằng `python -m "
                                     "autopark.video.camera_bench list`. Camera trên cao cắm vào cổng gốc riêng, không "
                                     "qua hub của bốn camera xe (KICH_BAN 3.4).")
        else:
            self.camera_info.setText(f"Camera index {self.camera_index} (tra bằng camera_bench list), tên "
                                     f"{self.camera_name}, {self.size_requested[0]}×{self.size_requested[1]}. "
                                     + (self.shift_text or "") + ("" if live else " Camera đang đóng."))
        recording = self.recorder is not None
        self.btn_open_cam.setEnabled(has_factory and not live)
        self.btn_close_cam.setEnabled(live)
        self.btn_rec.setEnabled(live and not recording)
        self.btn_rec_stop.setEnabled(recording)
        if not recording and self.last_recording is not None:
            m = self.last_recording
            self.rec_status.setText(f"lần ghi cuối: {m.get('status')}, {m.get('frames')} khung, {m.get('fps_real')} "
                                    f"khung/s, khoảng cách khung {m.get('gap_ms')} ms")

    # ================================================================== vòng lặp và đóng cửa sổ
    def refresh(self) -> None:
        self._refresh_floor()
        self._refresh_track()
        self._refresh_tc1()
        self._refresh_camera()

    def tick(self) -> None:
        self._poll_extraction()
        self._poll_tc1()
        self._camera_tick()

    def shutdown(self) -> None:
        """Dừng mọi luồng (trích, TC-1, camera), chờ tối đa 3 s."""
        self.timer.stop()
        for w in (self.extraction, self.tc1_worker):
            if w is not None and w.is_alive():
                w.stop_event.set()
        deadline = time.monotonic() + CLOSE_WAIT_S
        for w in (self.extraction, self.tc1_worker):
            if w is not None:
                w.join(max(0.0, deadline - time.monotonic()))
        if self.camera is not None:
            if self.recorder is not None:
                self.camera.stop_recording("dừng (đóng cửa sổ)")
                self.recorder = None
            self.camera.stop(max(0.1, deadline - time.monotonic()))
            self.camera = None

    def closeEvent(self, event):
        try:
            self.shutdown()
        finally:
            super().closeEvent(event)

    # ================================================================== hộp thoại (chỉ khi người bấm)
    def _open_name(self, caption: str, pattern: str) -> str:
        return QFileDialog.getOpenFileName(self, caption, str(PROJECT), pattern)[0]

    def _save_name(self, caption: str, default: Path, pattern: str) -> str:
        return QFileDialog.getSaveFileName(self, caption, str(default), pattern)[0]

    def _ask_intrinsics(self):
        if path := self._open_name("Nội tham camera trên cao", "JSON (*.json)"):
            self.load_intrinsics(path)

    def _ask_survey(self):
        if path := self._open_name("Tệp mốc sa bàn", "CSV (*.csv)"):
            self.load_survey(path)

    def _ask_floor_images(self):
        paths = QFileDialog.getOpenFileNames(self, "Ảnh sàn trống", str(PROJECT), "Ảnh (*.png *.jpg *.jpeg *.bmp)")[0]
        if paths:
            self.load_floor_images(paths)

    def _ask_floor_video(self):
        if path := self._open_name("Video sàn trống", "Video (*.avi *.mp4 *.mkv)"):
            self.load_floor_video(path)

    def _ask_save_floor(self):
        default = self.runs_dir / datetime.now().strftime("%Y%m%d") / f"mat_san_{datetime.now():%Y%m%d_%H%M}.json"
        if path := self._save_name("Lưu kết quả khớp mặt sàn", default, "JSON (*.json)"):
            self.save_floor(path, overwrite=Path(path).exists())

    def _ask_video(self):
        if path := self._open_name("Video trên cao", "Video (*.avi *.mp4 *.mkv)"):
            self.load_track_video(path)

    def _ask_track_floor(self):
        if path := self._open_name("Kết quả khớp mặt sàn", "JSON (*.json)"):
            self.load_track_floor(path)

    def _ask_track_markers(self):
        if path := self._open_name("Cấu hình marker trên xe", "JSON (*.json)"):
            self.load_track_markers(path)

    def _ask_tc1_report(self, day: bool):
        if path := self._open_name("Biên bản TC-1" + (" rút gọn trong ngày" if day else ""), "JSON (*.json)"):
            self.load_track_tc1(path, day)

    def _ask_sync_marks(self):
        if path := self._open_name("Tệp dấu đồng bộ T14", "CSV (*.csv)"):
            self.load_sync_marks(path)

    def _ask_save_track(self):
        if path := self._save_name("Lưu tệp tư thế tham chiếu", self.default_track_path(), "CSV (*.csv)"):
            self.save_track(path, overwrite=Path(path).exists())

    def _ask_tc1_markers(self):
        if path := self._open_name("Cấu hình marker xe giả", "JSON (*.json)"):
            self.load_tc1_markers(path)

    def _ask_tc1_floor(self):
        if path := self._open_name("Kết quả khớp mặt sàn", "JSON (*.json)"):
            self.load_tc1_floor(path)

    def _ask_tc1_poses(self):
        if path := self._open_name("Bảng tư thế TC-1", "CSV (*.csv)"):
            self.load_tc1_poses(path)

    def _ask_save_tc1_poses(self):
        # mặc định dưới runs/; bảng chính thức thì người dùng chọn docs\evidence\tc1_<ngày>.csv (git chỉ giữ CSV ở đó)
        default = self.runs_dir / datetime.now().strftime("%Y%m%d") / f"tc1_{datetime.now():%Y%m%d}.csv"
        if path := self._save_name("Lưu bảng tư thế TC-1", default, "CSV (*.csv)"):
            self.save_tc1_poses(path)

    def _ask_save_tc1(self):
        default = self.runs_dir / datetime.now().strftime("%Y%m%d") / f"tc1_{datetime.now():%Y%m%d_%H%M}.json"
        if path := self._save_name("Lưu biên bản TC-1", default, "JSON (*.json)"):
            self.save_tc1(path, overwrite=Path(path).exists())


def build_window(argv=None) -> OverheadWindow:
    """Cửa sổ từ dòng lệnh (cần QApplication). Tham số sai → mã 2 trước khi mở cửa sổ; camera chỉ mở khi bấm."""
    from autopark.perception import fisheye_calib as fc

    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--index", type=int, default=None, metavar="N", help="camera trên cao theo index OpenCV")
    p.add_argument("--camera-name", default="tren_cao")
    p.add_argument("--size", type=parse_size, default=rec.DEFAULT_SIZE, help="mặc định 1280x720")
    for name in ("intrinsics", "survey", "floor", "markers", "video"):
        p.add_argument(f"--{name}", type=Path, default=None)
    args = p.parse_args(argv)
    if args.index is not None and args.index < 0:
        p.error("--index phải ≥ 0")
    if error := fc.camera_name_error(args.camera_name):
        p.error(f"--camera-name: {error}")
    factory = None if args.index is None else index_camera_factory(args.index, source_id=f"cam_{args.camera_name}")
    window = OverheadWindow(factory, camera_index=args.index, camera_name=args.camera_name, size=args.size)
    if args.intrinsics:
        window.load_intrinsics(args.intrinsics)
    if args.survey:
        window.load_survey(args.survey)
    if args.floor:
        window.load_track_floor(args.floor)
        window.load_tc1_floor(args.floor)
    if args.markers:
        window.load_track_markers(args.markers)
        window.load_tc1_markers(args.markers)
    if args.video:
        window.load_track_video(args.video)
    return window


def main(argv=None) -> int:
    from autopark.power_throttling import apply_ecoqos_policy
    from autopark.ui.process_status import add_ecoqos_label

    policy = apply_ecoqos_policy("ui.overhead_app")           # trước mọi việc khác (power_throttling.py)
    app = QApplication.instance() or QApplication(sys.argv)
    window = build_window(argv)
    # công cụ đo (ghi video R1): như video.overhead_record, chính sách lúc khởi động vào khóa ecoqos_policy của tệp ghi;
    # khóa ecoqos thì bộ ghi đọc lại ecoqos_state() lúc ghi
    window.ecoqos_policy = {"request": policy.request, "set_ok": policy.set_ok, "after": policy.state}
    window.show()
    add_ecoqos_label(window, policy)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
