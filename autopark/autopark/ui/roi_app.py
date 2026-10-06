"""Giao diện ngoại tham + ROI cho camera của dự án (hai thẻ), chọn camera theo cổng hub.

    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.ui.roi_app --port 1
    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.ui.roi_app --port 1 --snapshot runs/rig_snapshots/<ngày_giờ>
    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.ui.roi_app --port 1 --live
    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.ui.roi_app --port 1 --image runs/extrinsics/tong_hop/dat_01.png --intrinsics runs/extrinsics/tong_hop/calibration/cam_p1.json

Mỗi lệnh viết trên MỘT dòng (dán được vào cmd.exe). Cách làm từng bước: docs/NGOAI_THAM_VA_ROI.md.

**Nguồn ảnh (dùng chung hai thẻ):** "Mở ảnh…" (một tệp ảnh), "Mở bộ ảnh…" (thư mục `runs/rig_snapshots/<ngày_giờ>`: lấy
`cam_p<cổng>.png`, đổi cổng thì đổi ảnh theo), hoặc "Camera sống" (mở camera theo cổng hub như `calib_app`; "Chụp khung"
giữ lại khung hiện tại làm ảnh tĩnh). Chỉ MỘT camera được mở, và chỉ khi bấm "Camera sống" hoặc chạy với `--live`.

**Thẻ Ngoại tham** (`perception/extrinsics_calib.py`): nạp nội tham `calibration/cam_p<cổng>.json` (thiếu thì từ chối —
hiệu chuẩn nội tham trước); ảnh hiện góc bảng đã đánh số O, A, B, C (O = góc trong sát ô đen góc trên-trái tờ in) để người
đo biết phải đo góc nào. Nhập tọa độ (m, hệ xe: x trước, y trái, gốc dưới tâm trục sau) của O, A (và B để kiểm), bấm "Thêm
lần đặt" — mỗi lần đặt được dò và giải ngay (RMS, độ cao camera suy ra). Đặt bảng chỗ khác, lặp lại. "Tính ngoại tham":
giải chung, loại lần đặt lệch, các phép kiểm; ảnh hiện lưới mặt sàn của hệ xe chiếu qua tư thế vừa đo (lưới phải nằm đúng
lên vạch băng dính). "Ghi tệp rig": lưu phiên (ảnh + danh sách lần đặt + báo cáo) vào `runs/extrinsics/<ngày_giờ>_p<cổng>/`
rồi ghi tệp rig (mặc định configs/rig/camera_rig_extrinsics_v1.json); tệp đã có thì phải tích "cho phép ghi đè". Đổi số
góc / cỡ ô / ô "Đã đo cỡ ô" hay nạp lại nội tham SAU khi tính thì kết quả cũ mất hiệu lực (nút "Ghi tệp rig" tắt), các lần
đặt được phân tích lại theo thông số mới: phải bấm "Tính ngoại tham" lại. Nội tham TỔNG HỢP (camera ảo của lệnh
`extrinsics_calib synthetic`): ô "Ghi vào" mặc định chuyển sang `<bộ thử>/camera_rig_tong_hop.json`, tệp ghi ra mang nhãn
"synthetic": true và không bao giờ được ghi vào configs/ hay calibration/.

**Thẻ ROI** (`perception/roi_tool.py`): bấm chuột trái để thêm đỉnh, chuột phải hoặc Enter để đóng đa giác, Backspace bỏ đỉnh
cuối, Esc huỷ đa giác đang vẽ. Đa giác "Loại" (thân xe, dây, viền ống kính) hay "Giữ". Vùng loại tô đỏ ngay trên ảnh (đã
nới `margin_px`). "Lưu ROI" ghi `<thư mục>/roi_p<cổng>.png` ở cỡ gốc của ảnh + `.json` (đa giác) + `_xem.jpg`; thư mục mặc
định configs/roi/rig_v1 — đưa vào BEV bằng `--roi-dir configs/roi/rig_v1`.

Camera lấy qua tham số `open_camera(cổng, rộng, cao)` nên test cắm được nguồn giả. Công cụ CHƯA từng chạy với camera thật
(24/09/2026: chỉ test offscreen với ảnh tổng hợp).
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow, QPushButton, QRadioButton,
                               QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from autopark.perception import extrinsics_calib as ec
from autopark.perception import fisheye_calib as fc
from autopark.perception import roi_tool as rt
from autopark.perception.calib_board import BoardSpec
from autopark.perception.paths import PROJECT
from autopark.power_throttling import apply_ecoqos_policy
from autopark.ui.calib_app import LiveCamera, to_qimage
from autopark.ui.process_status import add_ecoqos_label

PORTS = (1, 2, 3, 4)
ORIENT_EVERY_S = 0.3            # camera sống: đánh số góc (cần PnP) tối đa ~3 lần/s


def _mono(label: QLabel, size: int = 12) -> QLabel:
    font = QFont("Consolas")
    font.setPixelSize(size)
    label.setFont(font)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


class ImageCanvas(QWidget):
    """Ảnh co giãn giữ tỉ lệ; đổi toạ độ widget ↔ điểm ảnh (tâm pixel ở số nguyên) cho thao tác chuột."""
    clicked = Signal(float, float, int)          # x, y (điểm ảnh), nút chuột (Qt.MouseButton dạng int)
    key = Signal(int)

    def __init__(self, caption: str, parent=None):
        super().__init__(parent)
        self.caption = caption
        self.pixmap: QPixmap | None = None
        self.image_size: tuple[int, int] | None = None
        self.placeholder = ""
        self.setMinimumSize(480, 360)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    def set_image(self, image_bgr: np.ndarray | None, placeholder: str = "") -> None:
        if image_bgr is None:
            self.pixmap, self.image_size = None, None
        else:
            self.pixmap = QPixmap.fromImage(to_qimage(image_bgr))
            self.image_size = (int(image_bgr.shape[1]), int(image_bgr.shape[0]))
        self.placeholder = placeholder
        self.update()

    def _geometry(self) -> tuple[float, float, float] | None:
        if self.image_size is None:
            return None
        w, h = self.image_size
        s = min(self.width() / w, self.height() / h)
        return s, (self.width() - w * s) / 2.0, (self.height() - h * s) / 2.0

    def image_to_widget(self, x: float, y: float) -> QPointF:
        s, ox, oy = self._geometry()
        return QPointF(ox + (x + 0.5) * s, oy + (y + 0.5) * s)

    def widget_to_image(self, pos: QPointF) -> tuple[float, float] | None:
        g = self._geometry()
        if g is None:
            return None
        s, ox, oy = g
        x, y = (pos.x() - ox) / s - 0.5, (pos.y() - oy) / s - 0.5
        w, h = self.image_size
        if not (-0.5 <= x <= w - 0.5 and -0.5 <= y <= h - 0.5):
            return None
        return x, y

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#101821"))
        font = QFont("Segoe UI")
        font.setPixelSize(13)
        g = self._geometry()
        if self.pixmap is not None and g is not None:
            s, ox, oy = g
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            p.drawPixmap(QRectF(ox, oy, self.image_size[0] * s, self.image_size[1] * s), self.pixmap,
                         QRectF(0, 0, self.pixmap.width(), self.pixmap.height()))
        elif self.placeholder:
            p.setFont(font)
            p.setPen(QColor("#9cafbe"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.placeholder)
        font.setBold(True)
        p.setFont(font)
        band = QRectF(0, 0, self.width(), 22)
        p.fillRect(band, QColor(0, 0, 0, 150))
        p.setPen(QColor("#e8eef3"))
        p.drawText(band.adjusted(8, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.caption)

    def mousePressEvent(self, event):
        pos = self.widget_to_image(event.position())
        if pos is not None:
            self.clicked.emit(pos[0], pos[1], int(event.button().value))
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        self.key.emit(int(event.key()))
        super().keyPressEvent(event)


def _spin(lo: float, hi: float, decimals: int, value: float, step: float, suffix: str = "") -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(decimals)
    s.setSingleStep(step)
    s.setValue(value)
    if suffix:
        s.setSuffix(suffix)
    return s


class ExtrinsicsRoiWindow(QMainWindow):
    def __init__(self, open_camera=None, *, port: int = 1, spec: BoardSpec = BoardSpec(9, 6, 30.0),
                 calibration_dir=PROJECT / "calibration", intrinsics_path=None, rig_out=ec.DEFAULT_OUT,
                 rig_base=ec.DEFAULT_BASE, roi_dir=rt.DEFAULT_ROI_DIR, runs_dir=ec.DEFAULT_RUNS,
                 roi_runs_dir=PROJECT / "runs/roi", live_size: tuple[int, int] = fc.DEFAULT_SIZE):
        super().__init__()
        self.open_camera, self.port, self.live_size = open_camera, int(port), tuple(live_size)
        self.calibration_dir, self.runs_dir, self.roi_runs_dir = Path(calibration_dir), Path(runs_dir), Path(roi_runs_dir)
        self.image: np.ndarray | None = None
        self.image_source: str | None = None
        self.snapshot_dir: Path | None = None
        self.live_camera: LiveCamera | None = None
        self._live_seq = -1
        self._live_valid_seq = 0                       # khung sống từ số thứ tự này mới dò theo cỡ bảng hiện tại
        self._orient_cache: tuple | None = None        # ((thông số bảng, khoá ảnh), góc đã đánh số, góc thô, ghi chú)
        self._ego_cache: tuple | None = None           # (đường dẫn, mtime, hộp thân xe) của tệp "Chép từ"
        self._last_orient_t = 0.0
        self.intr: ec.CameraIntrinsics | None = None
        self.intr_error = ""
        self.inputs: list[ec.PlacementInput] = []
        self.analyses: list[ec.PlacementResult] = []
        self.result: ec.ExtrinsicsResult | None = None
        self._inputs_version = 0
        self._result_version = -1
        self.last_session: Path | None = None
        self.last_rig: Path | None = None
        self.polygons: list[rt.RoiPolygon] = []
        self.current_pts: list[tuple[float, float]] = []
        self.last_roi: dict | None = None
        self.message = ""

        # ---- thanh nguồn ảnh ----
        self.port_box = QComboBox()
        for p in PORTS:
            self.port_box.addItem(f"cổng {p}", p)
        if self.port not in PORTS:
            self.port_box.addItem(f"cổng {self.port}", self.port)
        self.port_box.setCurrentIndex(self.port_box.findData(self.port))
        self.port_box.currentIndexChanged.connect(lambda _: self.set_port(self.port_box.currentData()))
        self.btn_open = QPushButton("Mở ảnh…")
        self.btn_open.clicked.connect(self._ask_image)
        self.btn_snapshot = QPushButton("Mở bộ ảnh…")
        self.btn_snapshot.clicked.connect(self._ask_snapshot)
        self.chk_live = QCheckBox("Camera sống")
        self.chk_live.setEnabled(open_camera is not None)
        self.chk_live.toggled.connect(self.set_live)
        self.btn_grab = QPushButton("Chụp khung")
        self.btn_grab.clicked.connect(self.grab_live)
        self.source_label = QLabel()
        self.source_label.setTextFormat(Qt.TextFormat.PlainText)
        self.message_label = QLabel()
        self.message_label.setTextFormat(Qt.TextFormat.PlainText)
        self.message_label.setWordWrap(True)
        top = QHBoxLayout()
        for w in (self.port_box, self.btn_open, self.btn_snapshot, self.chk_live, self.btn_grab):
            top.addWidget(w)
        top.addWidget(self.source_label, 1)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_extrinsics_tab(spec, rig_out, rig_base), "Ngoại tham")
        self.tabs.addTab(self._build_roi_tab(roi_dir), "ROI")
        self.tabs.currentChanged.connect(lambda _: self.refresh())

        root = QWidget()
        lay = QVBoxLayout(root)
        lay.addLayout(top)
        lay.addWidget(self.tabs, 1)
        lay.addWidget(self.message_label)
        self.setCentralWidget(root)
        self.resize(1500, 900)

        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        # nối sau khi mọi widget đã có: đổi thông số bảng làm kết quả/góc đã dò theo thông số cũ mất hiệu lực
        for s in (self.cols_spin, self.rows_spin):
            s.valueChanged.connect(lambda _: self._board_changed(pattern=True))
        self.square_spin.valueChanged.connect(lambda _: self._board_changed())
        self.chk_square.toggled.connect(lambda _: self._board_changed(reanalyse=False))
        self.load_intrinsics(intrinsics_path)
        self._update_title()
        self.refresh()

    # ---- dựng thẻ ---------------------------------------------------------------------------------------------------
    def _build_extrinsics_tab(self, spec: BoardSpec, rig_out, rig_base) -> QWidget:
        self.ext_canvas = ImageCanvas("ảnh: góc bảng O, A, B, C / lưới hệ xe sau khi tính")
        self.intr_edit = QLineEdit()
        self.btn_intr = QPushButton("Nạp nội tham")
        self.btn_intr.clicked.connect(lambda: self.load_intrinsics(self.intr_edit.text().strip() or None, user=True))
        self.intr_label = _mono(QLabel(), 11)
        self.cols_spin, self.rows_spin = QSpinBox(), QSpinBox()
        for s, v in ((self.cols_spin, spec.cols), (self.rows_spin, spec.rows)):
            s.setRange(3, 30)
            s.setValue(v)
        self.square_spin = _spin(1.0, 200.0, 2, spec.square_mm, 0.05, " mm")
        self.chk_square = QCheckBox("Đã đo cỡ ô bằng thước")
        self.board_z_spin = _spin(0.0, 0.05, 4, 0.0, 0.001, " m")
        self.board_z_spin.setToolTip("độ cao mặt in trên sàn (độ dày tấm dán bảng); lưu theo TỪNG lần đặt lúc bấm 'Thêm "
                                     "lần đặt' — đổi ở đây chỉ áp dụng cho các lần đặt thêm sau")
        self.point_spins = {}
        grid = QGridLayout()
        grid.addWidget(QLabel("góc"), 0, 0)
        grid.addWidget(QLabel("x (m, trước)"), 0, 1)
        grid.addWidget(QLabel("y (m, trái)"), 0, 2)
        for row, name in enumerate(("O", "A", "B", "C"), start=1):
            grid.addWidget(QLabel(name), row, 0)
            sx, sy = _spin(-5.0, 5.0, 4, 0.0, 0.001, " m"), _spin(-5.0, 5.0, 4, 0.0, 0.001, " m")
            grid.addWidget(sx, row, 1)
            grid.addWidget(sy, row, 2)
            self.point_spins[name] = (sx, sy)
        self.chk_use_b = QCheckBox("Dùng B")
        self.chk_use_c = QCheckBox("Dùng C (đo cả bốn góc: hướng bảng chính xác hơn)")
        self.btn_add = QPushButton("Thêm lần đặt (ảnh hiện tại)")
        self.btn_add.clicked.connect(self.add_placement)
        self.btn_del = QPushButton("Xoá lần đặt chọn")
        self.btn_del.clicked.connect(self.remove_selected)
        self.placement_list = QListWidget()
        self.placement_list.currentRowChanged.connect(lambda _: self.refresh())
        self.btn_solve = QPushButton("Tính ngoại tham")
        self.btn_solve.clicked.connect(self.solve)
        self.min_spin = QSpinBox()
        self.min_spin.setRange(1, 20)
        self.min_spin.setValue(ec.MIN_PLACEMENTS)
        self.results = _mono(QLabel("chưa tính"))
        self.out_edit = QLineEdit(str(rig_out))
        self.base_edit = QLineEdit(str(rig_base))
        self.chk_overwrite = QCheckBox("Cho phép ghi đè tệp rig đã có (bản cũ được sao lưu)")
        self.btn_write = QPushButton("Ghi tệp rig")
        self.btn_write.clicked.connect(self.write_rig)

        side = QVBoxLayout()
        row = QHBoxLayout()
        row.addWidget(QLabel("Nội tham"))
        row.addWidget(self.intr_edit, 1)
        row.addWidget(self.btn_intr)
        side.addLayout(row)
        side.addWidget(self.intr_label)
        row = QHBoxLayout()
        row.addWidget(QLabel("Bảng"))
        row.addWidget(self.cols_spin)
        row.addWidget(QLabel("×"))
        row.addWidget(self.rows_spin)
        row.addWidget(QLabel("góc trong, ô"))
        row.addWidget(self.square_spin)
        side.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(self.chk_square)
        row.addWidget(QLabel("mặt in cao"))
        row.addWidget(self.board_z_spin)
        side.addLayout(row)
        side.addWidget(QLabel("Tọa độ đo bằng thước trong hệ xe (gốc trên sàn dưới tâm trục sau):"))
        side.addLayout(grid)
        row = QHBoxLayout()
        row.addWidget(self.chk_use_b)
        row.addWidget(self.chk_use_c)
        side.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(self.btn_add)
        row.addWidget(self.btn_del)
        side.addLayout(row)
        side.addWidget(self.placement_list, 1)
        row = QHBoxLayout()
        row.addWidget(self.btn_solve)
        row.addWidget(QLabel("tối thiểu"))
        row.addWidget(self.min_spin)
        row.addWidget(QLabel("lần đặt"))
        side.addLayout(row)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.results)
        side.addWidget(scroll, 2)
        grid2 = QGridLayout()
        grid2.addWidget(QLabel("Ghi vào"), 0, 0)
        grid2.addWidget(self.out_edit, 0, 1)
        grid2.addWidget(QLabel("Chép từ"), 1, 0)
        grid2.addWidget(self.base_edit, 1, 1)
        side.addLayout(grid2)
        side.addWidget(self.chk_overwrite)
        side.addWidget(self.btn_write)
        side_box = QWidget()
        side_box.setLayout(side)
        side_box.setMinimumWidth(460)
        side_box.setMaximumWidth(600)
        tab = QWidget()
        lay = QHBoxLayout(tab)
        lay.addWidget(self.ext_canvas, 3)
        lay.addWidget(side_box, 1)
        return tab

    def _build_roi_tab(self, roi_dir) -> QWidget:
        self.roi_canvas = ImageCanvas("ROI: chuột trái thêm đỉnh · chuột phải/Enter đóng · Backspace bỏ đỉnh · Esc huỷ")
        self.roi_canvas.clicked.connect(self.canvas_clicked)
        self.roi_canvas.key.connect(self.canvas_key)
        self.rb_exclude = QRadioButton("Loại (thân xe, dây, viền)")
        self.rb_include = QRadioButton("Giữ")
        self.rb_exclude.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.rb_exclude)
        group.addButton(self.rb_include)
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("nhãn đa giác (ví dụ: thân xe)")
        self.margin_spin = QSpinBox()
        self.margin_spin.setRange(0, 50)
        self.margin_spin.setValue(rt.DEFAULT_MARGIN_PX)
        self.margin_spin.setSuffix(" px")
        self.margin_spin.valueChanged.connect(lambda _: self.refresh())
        self.btn_close_poly = QPushButton("Đóng đa giác")
        self.btn_close_poly.clicked.connect(self.close_polygon)
        self.btn_undo = QPushButton("Bỏ đỉnh cuối")
        self.btn_undo.clicked.connect(self.undo_vertex)
        self.btn_del_poly = QPushButton("Xoá đa giác chọn")
        self.btn_del_poly.clicked.connect(self.delete_selected_polygon)
        self.poly_list = QListWidget()
        self.roi_dir_edit = QLineEdit(str(roi_dir))
        self.chk_roi_overwrite = QCheckBox("Cho phép ghi đè ROI đã có (bản cũ giữ với hậu tố .bak)")
        self.btn_roi_load = QPushButton("Mở ROI đã có")
        self.btn_roi_load.clicked.connect(lambda: self.load_roi())
        self.btn_roi_save = QPushButton("Lưu ROI")
        self.btn_roi_save.clicked.connect(self.save_roi)
        self.roi_report = _mono(QLabel("chưa có đa giác"))
        side = QVBoxLayout()
        side.addWidget(self.rb_exclude)
        side.addWidget(self.rb_include)
        side.addWidget(self.label_edit)
        row = QHBoxLayout()
        row.addWidget(QLabel("Nới vùng loại (ĐỀ XUẤT)"))
        row.addWidget(self.margin_spin)
        side.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(self.btn_close_poly)
        row.addWidget(self.btn_undo)
        side.addLayout(row)
        side.addWidget(self.poly_list, 1)
        side.addWidget(self.btn_del_poly)
        side.addWidget(QLabel("Thư mục ROI (đưa vào BEV bằng --roi-dir)"))
        side.addWidget(self.roi_dir_edit)
        side.addWidget(self.chk_roi_overwrite)
        row = QHBoxLayout()
        row.addWidget(self.btn_roi_load)
        row.addWidget(self.btn_roi_save)
        side.addLayout(row)
        side.addWidget(self.roi_report, 1)
        side_box = QWidget()
        side_box.setLayout(side)
        side_box.setMinimumWidth(380)
        side_box.setMaximumWidth(520)
        tab = QWidget()
        lay = QHBoxLayout(tab)
        lay.addWidget(self.roi_canvas, 3)
        lay.addWidget(side_box, 1)
        return tab

    # ---- nguồn ảnh --------------------------------------------------------------------------------------------------
    def _update_title(self) -> None:
        self.setWindowTitle(f"Ngoại tham và ROI — cổng {self.port}")

    def _ask_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Mở ảnh camera", str(PROJECT / "runs"), "Ảnh (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self.load_image_file(path)

    def _ask_snapshot(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Mở bộ ảnh bàn thử", str(PROJECT / "runs/rig_snapshots"))
        if path:
            self.load_snapshot(path)

    def load_image_file(self, path) -> bool:
        image = fc.read_image(Path(path))
        if image is None:
            self.message = f"LỖI: không đọc được ảnh {path}"
            self.refresh()
            return False
        self.snapshot_dir = None
        self._set_still(image, str(path))
        return True

    def load_snapshot(self, folder) -> bool:
        folder = Path(folder)
        path = folder / f"cam_p{self.port}.png"
        if not path.exists():
            self.message = f"LỖI: bộ ảnh {folder} không có cam_p{self.port}.png"
            self.refresh()
            return False
        if not (folder / "meta.json").exists():
            self.message = f"CẢNH BÁO: {folder} không có meta.json (lần chụp dở dang?)"
        image = fc.read_image(path)
        if image is None:
            self.message = f"LỖI: không đọc được {path}"
            self.refresh()
            return False
        self.snapshot_dir = folder
        self._set_still(image, str(path))
        return True

    def _set_still(self, image: np.ndarray, source: str) -> None:
        size_changed = self.image is None or self.image.shape[:2] != image.shape[:2]
        self.image, self.image_source = image, source
        self._orient_cache = None
        self.placement_list.setCurrentRow(-1)          # hiện ảnh mới, không phải ảnh của lần đặt đang chọn
        damaged = fc.damage_reason(image)
        if damaged:
            self.message = f"CẢNH BÁO: khung nghi hỏng ({damaged}) — không dùng được cho ngoại tham; chụp lại"
        if size_changed and self.intr is not None and tuple(self.intr.size) != (image.shape[1], image.shape[0]):
            self.load_intrinsics(None)
        self.refresh()

    def set_port(self, port: int) -> None:
        """Đổi camera: bỏ lần đặt, kết quả, đa giác và ảnh của camera trước (không dùng ảnh cổng này cho cổng kia)."""
        port = int(port)
        if port == self.port:
            return
        dropped, dropped_polys = len(self.inputs), len(self.polygons) + bool(self.current_pts)
        self.port = port
        self.inputs, self.analyses, self.result = [], [], None
        self._inputs_version += 1
        self.placement_list.clear()
        self.results.setText("chưa tính")
        self.polygons, self.current_pts = [], []
        self._refresh_poly_list()
        self._orient_cache = None
        notes = [f"đã chuyển sang cổng {port}"]
        if self.live_camera is not None:
            self._stop_live()
            self._start_live()
        snapshot = self.snapshot_dir
        self.image, self.image_source, self.snapshot_dir = None, None, None
        if snapshot is not None:
            if self.load_snapshot(snapshot):
                notes.append(f"ảnh cam_p{port}.png của cùng bộ ảnh")
            else:
                notes.append(f"bộ ảnh {snapshot.name} không có cam_p{port}.png: chưa có ảnh")
        elif self.live_camera is None:
            notes.append("ảnh của cổng trước đã bỏ: mở ảnh của camera này")
        self.load_intrinsics(None)
        self._update_title()
        if dropped:
            notes.append(f"bỏ {dropped} lần đặt của cổng trước")
        if dropped_polys:
            notes.append("bỏ đa giác ROI của cổng trước")
        self.message = "; ".join(notes)
        self.refresh()

    # ---- thông số bảng -----------------------------------------------------------------------------------------------
    def _spec(self) -> BoardSpec:
        return BoardSpec(int(self.cols_spin.value()), int(self.rows_spin.value()), float(self.square_spin.value()))

    def _board_changed(self, pattern: bool = False, reanalyse: bool = True) -> None:
        """Đổi số góc / cỡ ô / ô 'Đã đo cỡ ô': kết quả đã tính theo thông số cũ mất hiệu lực (phải Tính lại mới ghi được);
        góc đã dò theo số góc cũ bỏ đi; các lần đặt được phân tích lại theo bảng mới."""
        was_fresh = self.result is not None and self._result_version == self._inputs_version
        self._inputs_version += 1
        self._orient_cache = None
        spec = self._spec()
        if pattern and self.live_camera is not None:
            # LiveCamera.run đọc self.spec ở mỗi khung (gán là nguyên tử, không mở lại camera USB). Khung đang dò dở lúc
            # gán có thể vẫn theo bảng cũ: chỉ tin phần dò của khung từ số thứ tự (khung mới nhất + 2) trở đi.
            self.live_camera.spec = spec
            last = self.live_camera.latest()
            self._live_valid_seq = (0 if last is None else last.seq) + 2
        notes = []
        if pattern:
            try:
                ec.check_spec(spec)
            except ec.ExtrinsicsError as exc:
                notes.append(f"LỖI: {exc}")
        if reanalyse and self.intr is not None and self.inputs:
            self.analyses = [ec.analyse_placement(inp, spec, self.intr) for inp in self.inputs]
            for k, a in enumerate(self.analyses):
                self.placement_list.item(k).setText(self._placement_text(a))
            bad = sum(not a.used for a in self.analyses)
            notes.append(f"đã phân tích lại {len(self.analyses)} lần đặt theo bảng {spec.cols}×{spec.rows} ô "
                         f"{spec.square_mm:g} mm" + (f" ({bad} lần không dùng được)" if bad else ""))
        if was_fresh:
            notes.append("đã đổi thông số bảng sau khi tính: bấm Tính ngoại tham lại trước khi ghi tệp rig")
        if notes:
            self.message = "; ".join(notes)
        self.refresh()

    # ---- camera sống ------------------------------------------------------------------------------------------------
    def _start_live(self) -> None:
        self.live_camera = LiveCamera(self.open_camera, self.port, self.live_size, self._spec())
        self.live_camera.start()
        self._live_seq = -1
        self._live_valid_seq = 0                        # luồng mới dò theo cỡ bảng hiện tại ngay từ khung đầu

    def _stop_live(self) -> None:
        cam, self.live_camera = self.live_camera, None
        if cam is not None and cam.stop():
            print(f"CẢNH BÁO: luồng camera cổng {self.port} chưa dừng (read() treo)", file=sys.stderr)

    def set_live(self, on: bool) -> None:
        if on and self.open_camera is None:
            self.message = "không có hàm mở camera"
            return
        if on and self.live_camera is None:
            self._start_live()
            self._orient_cache = None
            self.placement_list.setCurrentRow(-1)
            self.message = f"đang mở camera cổng {self.port} ({self.live_size[0]}×{self.live_size[1]})"
        elif not on and self.live_camera is not None:
            self._stop_live()
            self.message = "đã tắt camera sống"
        self.refresh()

    def grab_live(self) -> bool:
        live = self.live_camera.latest() if self.live_camera is not None else None
        if live is None:
            self.message = "chưa có khung sống để chụp (bật 'Camera sống' trước)"
            self.refresh()
            return False
        self.snapshot_dir = None
        self._set_still(live.image.copy(), f"khung sống cổng {self.port} lúc {datetime.now().strftime('%H:%M:%S')}")
        self.chk_live.setChecked(False)
        return True

    def current_image(self) -> tuple[np.ndarray | None, str | None]:
        if self.live_camera is not None:
            live = self.live_camera.latest()
            if live is not None:
                return live.image, f"khung sống cổng {self.port}"
            return None, None
        return self.image, self.image_source

    def tick(self) -> None:
        cam = self.live_camera
        if cam is None:
            return
        live = cam.latest()
        if cam.counters.open_error:
            self.message = f"KHÔNG MỞ ĐƯỢC CAMERA cổng {self.port}: {cam.counters.open_error}"
            self._stop_live()
            self.chk_live.setChecked(False)
            self.refresh()
            return
        if live is not None and live.seq != self._live_seq:
            self._live_seq = live.seq
            self.refresh()

    # ---- nội tham ---------------------------------------------------------------------------------------------------
    def load_intrinsics(self, path=None, user: bool = False) -> bool:
        image, _ = self.current_image()
        size = fc.DEFAULT_SIZE if image is None else (image.shape[1], image.shape[0])
        path = Path(path) if path else ec.default_intrinsics_path(self.port, size, self.calibration_dir)
        self.intr_edit.setText(str(path))
        self._orient_cache = None
        self._inputs_version += 1           # kết quả đã tính với nội tham trước: phải Tính lại mới ghi được
        notes = []
        try:
            self.intr = ec.load_camera_intrinsics(path, self.port)
            self.intr_error = ""
            acc = self.intr.acceptance_all_pass
            if self.intr.synthetic:
                self.intr_label.setText(f"nội tham {self.intr.size[0]}×{self.intr.size[1]}: {ec.SYNTHETIC_MARK} (camera "
                                        f"ảo, không phải hiệu chuẩn thật) — kết quả chỉ để thử, KHÔNG PHẢI SỐ ĐO")
                if Path(self.out_edit.text().strip()) == Path(ec.DEFAULT_OUT):
                    self.out_edit.setText(str(path.parent.parent / ec.SYNTHETIC_RIG_NAME))
                    notes.append(f"nội tham {ec.SYNTHETIC_MARK}: 'Ghi vào' đổi sang {self.out_edit.text()} (không ghi "
                                 f"kết quả tổng hợp vào configs/)")
            else:
                self.intr_label.setText(f"nội tham {self.intr.size[0]}×{self.intr.size[1]}, tiêu chí đề xuất: "
                                        + ("đạt" if acc else "CHƯA ĐẠT" if acc is False else "không ghi"))
            ok = True
        except ec.ExtrinsicsError as exc:
            self.intr, self.intr_error = None, str(exc)
            self.intr_label.setText(f"CHƯA CÓ NỘI THAM: {exc}")
            ok = False
        if ok and self.inputs:                  # các lần đặt đã thêm: phân tích lại với nội tham này
            spec = self._spec()
            self.analyses = [ec.analyse_placement(inp, spec, self.intr) for inp in self.inputs]
            for k, a in enumerate(self.analyses):
                self.placement_list.item(k).setText(self._placement_text(a))
        if user:
            notes.insert(0, ("đã nạp nội tham " + str(path)) if ok else f"LỖI: {self.intr_error}")
        if notes:
            self.message = "; ".join(notes)
        self.refresh()
        return ok

    # ---- ngoại tham -------------------------------------------------------------------------------------------------
    def _placement(self) -> ec.BoardPlacement:
        names = ("O", "A") + (("B",) if self.chk_use_b.isChecked() else ()) + (("C",) if self.chk_use_c.isChecked() else ())
        pts = {n: (float(self.point_spins[n][0].value()), float(self.point_spins[n][1].value())) for n in names}
        return ec.BoardPlacement.from_points(pts, board_z_m=float(self.board_z_spin.value()))

    def set_points(self, points: dict, use_b: bool | None = None, use_c: bool | None = None) -> None:
        """Điền ô số đo (tên → (x, y) m) — cho test và cho việc nạp lại."""
        for name, (x, y) in points.items():
            self.point_spins[name][0].setValue(float(x))
            self.point_spins[name][1].setValue(float(y))
        if use_b is not None:
            self.chk_use_b.setChecked(bool(use_b))
        if use_c is not None:
            self.chk_use_c.setChecked(bool(use_c))

    def add_placement(self) -> bool:
        image, source = self.current_image()
        if image is None:
            self.message = "chưa có ảnh: mở ảnh, bộ ảnh, hoặc bật camera sống"
            self.refresh()
            return False
        if self.intr is None:
            self.message = f"chưa có nội tham: {self.intr_error}"
            self.refresh()
            return False
        if self.inputs and self.inputs[0].image.shape != image.shape:
            self.message = "ảnh khác cỡ các lần đặt trước"
            self.refresh()
            return False
        name = f"dat_{len(self.inputs) + 1:02d}"
        while any(i.name == name for i in self.inputs):
            name += "b"
        inp = ec.PlacementInput(name, image.copy(), self._placement(),
                                None if source is None or source.startswith("khung sống") else source)
        analysis = ec.analyse_placement(inp, self._spec(), self.intr)
        self.inputs.append(inp)
        self.analyses.append(analysis)
        self._inputs_version += 1
        self.placement_list.addItem(self._placement_text(analysis))
        self.placement_list.setCurrentRow(-1)
        detail = (f"RMS {analysis.rms_px:.3f} px, camera cao {analysis.t_cv[2]:.3f} m theo riêng lần này"
                  if analysis.used else f"KHÔNG DÙNG ĐƯỢC — {analysis.reason}")
        self.message = f"đã thêm {name}: {detail}"
        self.refresh()
        return analysis.used

    def _placement_text(self, a: ec.PlacementResult) -> str:
        if not a.used:
            return f"{a.name}: LOẠI — {a.reason}"
        text = f"{a.name}: RMS {a.rms_px:.3f} px · cao {a.t_cv[2]:.3f} m · bảng cách {a.board_distance_m:.2f} m"
        if a.deviation_m is not None:
            text += f" · lệch {100 * a.deviation_m:.2f} cm / {a.deviation_deg:.2f}°"
        return text

    def remove_selected(self) -> None:
        row = self.placement_list.currentRow()
        if row < 0 or row >= len(self.inputs):
            return
        del self.inputs[row]
        del self.analyses[row]
        self.placement_list.takeItem(row)
        self._inputs_version += 1
        self.message = "đã xoá một lần đặt; bấm Tính ngoại tham lại"
        self.refresh()

    def solve(self) -> ec.ExtrinsicsResult | None:
        if self.intr is None:
            self.message = f"chưa có nội tham: {self.intr_error}"
            self.refresh()
            return None
        if not self.inputs:
            self.message = "chưa có lần đặt nào"
            self.refresh()
            return None
        try:
            result = ec.solve_extrinsics(self.inputs, self._spec(), self.intr, min_placements=int(self.min_spin.value()),
                                         square_mm_measured=self.chk_square.isChecked())
        except ec.ExtrinsicsError as exc:          # ví dụ bảng có cols + rows chẵn: báo trên giao diện, không thoát slot
            self.message = f"LỖI: {exc}"
            self.refresh()
            return None
        self.result = result
        self._result_version = self._inputs_version
        self.analyses = list(self.result.placements)
        for k, a in enumerate(self.analyses):
            self.placement_list.item(k).setText(self._placement_text(a))
        self.results.setText(ec.summary_text(self.result))
        if not self.result.ok:
            self.message = "TỪ CHỐI: " + " | ".join(self.result.refusals)
        elif self.result.synthetic:
            self.message = (f"ĐẠT trên ảnh {ec.SYNTHETIC_MARK} — chỉ để thử, KHÔNG PHẢI SỐ ĐO (ghi được ra ngoài configs/, "
                            f"tệp mang nhãn \"synthetic\": true)")
        else:
            self.message = "ĐẠT — có thể ghi tệp rig"
        if self.result.R_cv is not None:                # hiện lưới hệ xe trên lần đặt đầu tiên dùng được
            first = next((k for k, p in enumerate(self.result.placements) if p.used), -1)
            self.placement_list.setCurrentRow(first)
        self.refresh()
        return self.result

    def save_session(self) -> Path | None:
        """Ảnh + danh sách lần đặt + báo cáo vào runs/extrinsics/<ngày_giờ>_p<cổng>/ (để chạy lại bằng dòng lệnh)."""
        if not self.inputs:
            return None
        folder = self.runs_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_p{self.port}"
        k = 1
        while folder.exists():
            folder = self.runs_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_p{self.port}_{k}"
            k += 1
        folder.mkdir(parents=True)
        entries = []
        for inp in self.inputs:
            path = folder / f"{inp.name}.png"
            if not fc.write_image(path, inp.image):
                raise ec.ExtrinsicsError(f"không ghi được {path}")
            entries.append({"name": inp.name, "image": path.name, "source": inp.image_path,
                            **inp.placement.to_dict()})
        # kết quả còn mới: ghi đúng thông số bảng / nội tham ĐÃ DÙNG để tính (phiên chạy lại cho cùng tư thế), không phải
        # giá trị ô nhập lúc này
        fresh = self.result is not None and self._result_version == self._inputs_version
        spec = self.result.spec if fresh else self._spec()
        measured = self.result.square_mm_measured if fresh else self.chk_square.isChecked()
        intr_path = (self.result.intrinsics.path if fresh and self.result.intrinsics is not None
                     else None if self.intr is None else self.intr.path)
        # board_z_m lưu theo từng lần đặt (to_dict); khối board ghi giá trị chung khi mọi lần đặt giống nhau
        heights = {inp.placement.board_z_m for inp in self.inputs}
        board_z = heights.pop() if len(heights) == 1 else float(self.board_z_spin.value())
        record = ec.placements_record(self.port, spec, entries, square_mm_measured=measured, board_z_m=board_z,
                                      intrinsics=intr_path)
        (folder / f"dat_bang_p{self.port}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1),
                                                             encoding="utf-8")
        if fresh:
            for pr in self.result.placements:
                pr.image_path = str(folder / f"{pr.name}.png")
            ec.write_report(folder, self.result, self.inputs, ego=self._ego())
        self.last_session = folder
        return folder

    def write_rig(self) -> Path | None:
        if self.result is None or self._result_version != self._inputs_version:
            self.message = ("chưa tính (hoặc lần đặt / thông số bảng / nội tham đã đổi sau khi tính): bấm Tính ngoại "
                            "tham")
            self.refresh()
            return None
        if self.result.spec != self._spec() or self.result.square_mm_measured != self.chk_square.isChecked():
            self.message = "thông số bảng đã đổi sau khi tính: bấm Tính ngoại tham lại"     # chốt chặn thứ hai
            self.refresh()
            return None
        if not self.result.ok:
            self.message = "kết quả không đạt, không ghi: " + " | ".join(self.result.refusals)
            self.refresh()
            return None
        out = Path(self.out_edit.text().strip())
        base = Path(self.base_edit.text().strip())
        if out.exists() and not self.chk_overwrite.isChecked():
            self.message = (f"{out} đã có: không ghi đè im lặng — tích 'cho phép ghi đè' (bản cũ được sao lưu), và muốn giữ "
                            f"các camera đã đo trong tệp đó thì đặt 'Chép từ' = chính tệp đó")
            self.refresh()
            return None
        existed = out.exists()
        try:
            session = self.save_session()
            path = ec.write_rig_file(out, [self.result], base_path=base, overwrite=self.chk_overwrite.isChecked(),
                                     allow_synthetic=self.result.synthetic)   # vẫn cấm configs/, calibration/
        except (ec.ExtrinsicsError, OSError) as exc:
            self.message = f"LỖI: {exc}"
            self.refresh()
            return None
        self.last_rig = path
        backup = ec.last_backup(path) if existed else None
        self.message = (f"đã ghi {path} (đọc lại bằng bev.load_rig_extrinsics: khớp); phiên lưu ở {session}"
                        + (f"; bản cũ: {backup.name}" if backup else ""))
        self.refresh()
        return path

    # ---- ROI --------------------------------------------------------------------------------------------------------
    def canvas_clicked(self, x: float, y: float, button: int) -> None:
        image, _ = self.current_image()
        if image is None:
            return
        if button == Qt.MouseButton.LeftButton.value:
            h, w = image.shape[:2]
            self.current_pts.append((float(np.clip(x, 0, w - 1)), float(np.clip(y, 0, h - 1))))
        elif button == Qt.MouseButton.RightButton.value:
            self.close_polygon()
            return
        self.refresh()

    def canvas_key(self, key: int) -> None:
        if key in (Qt.Key.Key_Return.value, Qt.Key.Key_Enter.value):
            self.close_polygon()
        elif key == Qt.Key.Key_Backspace.value:
            self.undo_vertex()
        elif key == Qt.Key.Key_Escape.value:
            self.current_pts = []
            self.refresh()

    def close_polygon(self) -> bool:
        if len(self.current_pts) < 3:
            self.message = f"đa giác cần ít nhất 3 đỉnh (đang có {len(self.current_pts)})"
            self.refresh()
            return False
        mode = "include" if self.rb_include.isChecked() else "exclude"
        poly = rt.RoiPolygon(list(self.current_pts), mode, self.label_edit.text().strip())
        self.polygons.append(poly)
        self.current_pts = []
        self._refresh_poly_list()
        self.message = f"đã đóng đa giác {'giữ' if mode == 'include' else 'loại'} {len(poly.points)} đỉnh"
        self.refresh()
        return True

    def undo_vertex(self) -> None:
        if self.current_pts:
            self.current_pts.pop()
            self.refresh()

    def delete_selected_polygon(self) -> None:
        row = self.poly_list.currentRow()
        if 0 <= row < len(self.polygons):
            del self.polygons[row]
            self._refresh_poly_list()
            self.refresh()

    def _refresh_poly_list(self) -> None:
        self.poly_list.clear()
        for k, p in enumerate(self.polygons):
            self.poly_list.addItem(f"{k + 1}. {'GIỮ' if p.mode == 'include' else 'LOẠI'} · {len(p.points)} đỉnh"
                                   + (f" · {p.label}" if p.label else ""))

    def roi_spec(self) -> rt.RoiSpec | None:
        image, source = self.current_image()
        if image is None:
            return None
        return rt.RoiSpec(self.port, int(image.shape[1]), int(image.shape[0]), list(self.polygons),
                          int(self.margin_spin.value()), source)

    def roi_mask(self) -> np.ndarray | None:
        spec = self.roi_spec()
        return None if spec is None else rt.rasterize(spec)

    def save_roi(self) -> dict | None:
        image, source = self.current_image()
        spec = self.roi_spec()
        if spec is None:
            self.message = "chưa có ảnh để dựng ROI"
            self.refresh()
            return None
        if self.current_pts:
            self.message = "còn một đa giác đang vẽ dở: đóng (Enter) hoặc huỷ (Esc) trước khi lưu"
            self.refresh()
            return None
        if self.intr is not None and tuple(self.intr.size) != (spec.width, spec.height):
            self.message = (f"ảnh {spec.width}×{spec.height} khác cỡ nội tham {self.intr.size}: BEV sẽ từ chối ROI này — "
                            f"dùng ảnh đúng mode camera")
            self.refresh()
            return None
        try:
            if source is None or source.startswith("khung sống"):
                keep = self.roi_runs_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_p{self.port}.png"
                keep.parent.mkdir(parents=True, exist_ok=True)
                fc.write_image(keep, image)
                spec.source_image = str(keep)
            result = rt.save_roi(spec, Path(self.roi_dir_edit.text().strip()), image=image,
                                 overwrite=self.chk_roi_overwrite.isChecked())
        except (rt.RoiError, OSError) as exc:
            self.message = f"LỖI: {exc}"
            self.refresh()
            return None
        self.last_roi = result
        self.message = (f"đã lưu {result['png']} (dùng được {100 * result['usable_fraction']:.1f} %)"
                        + (f"; bản cũ: {', '.join(Path(b).name for b in result['backups'])}" if result["backups"] else ""))
        self.refresh()
        return result

    def load_roi(self, folder=None) -> bool:
        folder = Path(folder or self.roi_dir_edit.text().strip())
        path = rt.roi_paths(folder, self.port)["json"]
        try:
            spec = rt.load_spec(path)
        except rt.RoiError as exc:
            self.message = f"LỖI: {exc}"
            self.refresh()
            return False
        image, _ = self.current_image()
        if image is not None and (image.shape[1], image.shape[0]) != (spec.width, spec.height):
            self.message = f"ROI {path} cỡ {spec.width}×{spec.height} khác ảnh đang mở"
            self.refresh()
            return False
        self.polygons = list(spec.polygons)
        self.margin_spin.setValue(spec.margin_px)
        self.current_pts = []
        self._refresh_poly_list()
        self.message = f"đã mở {path}: {len(self.polygons)} đa giác"
        self.refresh()
        return True

    # ---- vẽ ---------------------------------------------------------------------------------------------------------
    def _ego(self):
        """Hộp thân xe GIẢ ĐỊNH của tệp 'Chép từ' (vẽ trắng trên ảnh kiểm); nhớ theo (đường dẫn, mtime)."""
        path = Path(self.base_edit.text().strip() or ec.DEFAULT_BASE)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return None
        if self._ego_cache is None or self._ego_cache[:2] != (str(path), mtime):
            self._ego_cache = (str(path), mtime, ec.rig_ego(path))
        return self._ego_cache[2]

    def _oriented(self, image: np.ndarray, key, detection=None, stale_detection: bool = False):
        """(góc đã đánh số hoặc None, góc thô hoặc None, ghi chú); nhớ theo (thông số bảng, `key`) để không giải lại mỗi
        lần vẽ. `stale_detection`: khung sống còn dò theo cỡ bảng cũ — chưa dùng góc của nó."""
        spec = self._spec()
        key = (spec, key)
        if self._orient_cache is not None and self._orient_cache[0] == key:
            return self._orient_cache[1:]
        raw = None
        if detection is None:
            det = fc.detect_corners(image, spec)
            raw = det.corners if det.found else None
        elif not stale_detection:
            raw = detection.corners if detection.found else None
        if raw is not None and len(raw) != spec.n_corners:      # khung dò theo bảng cũ (khác số góc)
            raw = None
        oriented, note = None, ""
        if stale_detection:
            note = f"đang dò lại theo bảng {spec.cols}×{spec.rows} mới"
        elif raw is None:
            note = f"không thấy đủ {spec.cols}×{spec.rows} góc trong"
        elif self.intr is None:
            note = "chưa nạp nội tham: chưa biết góc nào là O"
        elif tuple(self.intr.size) != (image.shape[1], image.shape[0]):
            note = "ảnh khác cỡ nội tham"
        else:
            try:
                oriented = ec.orient_board(image, raw, spec, self.intr.K, self.intr.D).corners
            except ec.ExtrinsicsError as exc:
                note = str(exc)
        self._orient_cache = (key, oriented, raw, note)
        return oriented, raw, note

    def _draw_extrinsics(self) -> None:
        row = self.placement_list.currentRow()
        if 0 <= row < len(self.inputs):                  # một lần đặt đang chọn: hiện ảnh của chính lần đó
            fresh = (self.result is not None and self._result_version == self._inputs_version
                     and self.result.R_cv is not None)
            a = self.analyses[row]
            current = self._spec()
            if fresh:                                    # vẽ theo đúng thông số bảng của kết quả
                img = ec.draw_result(self.inputs[row].image, self.result.placements[row], self.result, self.result.spec,
                                     ego=self._ego())
            elif a.corners is not None and a.spec == current and len(a.corners) == current.n_corners:
                img = ec.draw_board_labels(self.inputs[row].image, a.corners, current)
            else:                                        # góc đánh số theo bảng khác bảng đang nhập: không vẽ nhãn sai
                img = self.inputs[row].image
            self.ext_canvas.set_image(img)
            self.ext_note = f"{a.name}: " + ("dùng được" if a.used else f"LOẠI — {a.reason}")
            if not fresh and a.spec is not None and a.spec != current:
                self.ext_note += (f" (phân tích theo bảng {a.spec.cols}×{a.spec.rows} ô {a.spec.square_mm:g} mm, chưa "
                                  f"phân tích lại theo bảng đang nhập: cần nội tham)")
            return
        image, _ = self.current_image()
        if image is None:
            self.ext_canvas.set_image(None, "mở ảnh / bộ ảnh, hoặc bật camera sống")
            return
        live = self.live_camera.latest() if self.live_camera is not None else None
        if live is not None:
            image = live.image                           # vẽ đúng khung đã dò (latest() có thể đã sang khung mới)
            now = time.monotonic()
            cached_live = self._orient_cache is not None and self._orient_cache[0][1][0] == "live"
            if not cached_live or now - self._last_orient_t >= ORIENT_EVERY_S:
                self._last_orient_t = now
                self._orient_cache = None
                oriented, raw, note = self._oriented(live.image, ("live", live.seq), live.detection,
                                                     stale_detection=live.seq < self._live_valid_seq)
            else:
                _, oriented, raw, note = self._orient_cache
        else:
            oriented, raw, note = self._oriented(image, ("still", id(image)))
        spec = self._spec()
        if oriented is not None and len(oriented) == spec.n_corners:
            img = ec.draw_board_labels(image, oriented, spec)
        else:
            img = image.copy()
            if raw is not None and len(raw) == spec.n_corners:
                cv2.drawChessboardCorners(img, spec.pattern_size, np.asarray(raw, np.float32).reshape(-1, 1, 2), True)
        self.ext_canvas.set_image(img)
        self.ext_note = note

    def _draw_roi(self) -> None:
        image, _ = self.current_image()
        if image is None:
            self.roi_canvas.set_image(None, "mở ảnh / bộ ảnh, hoặc bật camera sống rồi 'Chụp khung'")
            self.roi_report.setText("chưa có ảnh")
            return
        try:
            mask = self.roi_mask()
        except rt.RoiError as exc:
            self.roi_report.setText(f"LỖI: {exc}")
            return
        out = rt.overlay(image, mask, polygons=self.polygons)
        pts = [(int(round(x)), int(round(y))) for x, y in self.current_pts]
        for a, b in zip(pts[:-1], pts[1:]):
            cv2.line(out, a, b, (0, 255, 255), 1, cv2.LINE_AA)
        for p in pts:
            cv2.circle(out, p, 3, (0, 255, 255), -1, cv2.LINE_AA)
        self.roi_canvas.set_image(out)
        expected = None if self.intr is None else tuple(self.intr.size)
        report = rt.check_mask(mask, expected)
        lines = [f"cổng {self.port} · ảnh {mask.shape[1]}×{mask.shape[0]} · {len(self.polygons)} đa giác"
                 + (f" · đang vẽ {len(self.current_pts)} đỉnh" if self.current_pts else ""),
                 f"dùng được {100 * report['usable_fraction']:.1f} % · loại {100 * report['excluded_fraction']:.1f} % · "
                 f"{report['usable_components']} mảnh"]
        lines += [f"LỖI: {e}" for e in report["errors"]] + [f"CẢNH BÁO: {w}" for w in report["warnings"]]
        if expected is None:
            lines.append("chưa nạp nội tham: chưa kiểm cỡ ROI với cỡ đã hiệu chuẩn")
        self.roi_report.setText("\n".join(lines))

    def refresh(self) -> None:
        image, source = self.current_image()
        size = "" if image is None else f" · {image.shape[1]}×{image.shape[0]}"
        self.source_label.setText(f"ảnh: {source or '—'}{size}")
        self.ext_note = ""
        if self.tabs.currentIndex() == 0:
            self._draw_extrinsics()
        else:
            self._draw_roi()
        busy_result = (self.result is not None and self._result_version == self._inputs_version
                       and self.result.spec == self._spec())
        self.btn_write.setEnabled(bool(busy_result and self.result.ok))
        self.btn_grab.setEnabled(self.live_camera is not None)
        text = self.message
        if self.ext_note and self.tabs.currentIndex() == 0:
            text = (text + "\n" if text else "") + f"bảng trên ảnh: {self.ext_note}"
        self.message_label.setText(text)
        alert = text.startswith(("LỖI", "TỪ CHỐI", "KHÔNG", "CẢNH BÁO"))
        self.message_label.setStyleSheet("color: #d9534f;" if alert else "")

    def closeEvent(self, event):
        self.timer.stop()
        try:
            self._stop_live()
        finally:
            super().closeEvent(event)


def main(argv=None) -> int:
    ecoqos = apply_ecoqos_policy("ui.roi_app")         # trước mọi việc khác (power_throttling.py)
    p = argparse.ArgumentParser(description="Ngoại tham và ROI cho camera dự án (docs/NGOAI_THAM_VA_ROI.md)")
    p.add_argument("--port", type=int, default=1, help="cổng hub của camera (1..4)")
    p.add_argument("--image", type=Path, help="mở sẵn một ảnh")
    p.add_argument("--snapshot", type=Path, help="mở sẵn một bộ ảnh runs/rig_snapshots/<ngày_giờ>")
    p.add_argument("--live", action="store_true", help="mở camera thật theo cổng hub ngay khi chạy")
    p.add_argument("--size", default="640x480", help="cỡ khung camera sống (mặc định 640x480, mode chạy bốn camera)")
    p.add_argument("--intrinsics", type=Path, help="tệp nội tham (mặc định calibration/cam_p<cổng>.json)")
    p.add_argument("--square-mm", type=float, default=30.0, help="cỡ ô ĐO ĐƯỢC của bảng (đổi được trong giao diện)")
    p.add_argument("--rig-out", type=Path, default=ec.DEFAULT_OUT)
    p.add_argument("--rig-base", type=Path, default=ec.DEFAULT_BASE)
    p.add_argument("--roi-dir", type=Path, default=rt.DEFAULT_ROI_DIR)
    args = p.parse_args(argv)
    from autopark.ui.calib_app import parse_size, usb_camera_factory

    app = QApplication.instance() or QApplication(sys.argv)
    window = ExtrinsicsRoiWindow(usb_camera_factory, port=args.port, spec=BoardSpec(9, 6, args.square_mm),
                                 intrinsics_path=args.intrinsics, rig_out=args.rig_out, rig_base=args.rig_base,
                                 roi_dir=args.roi_dir, live_size=parse_size(args.size))
    if args.snapshot:
        window.load_snapshot(args.snapshot)
    elif args.image:
        window.load_image_file(args.image)
    if args.intrinsics:
        window.load_intrinsics(args.intrinsics, user=True)
    if args.live:
        window.chk_live.setChecked(True)
    window.show()
    add_ecoqos_label(window, ecoqos)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
