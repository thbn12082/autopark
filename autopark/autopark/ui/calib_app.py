"""Giao diện hiệu chuẩn nội tham một camera mắt cá, chọn theo cổng hub: xem trực tiếp, chụp bảng, hiệu chuẩn, lưu.

    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.ui.calib_app --port 1
    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.ui.calib_app --port 2 --size 1280x720 --square-mm 19.9
    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.ui.calib_app --index 4 --camera-name tren_cao --size 1280x720

Camera KHÔNG qua hub 1..4 (camera trên cao của mục 3.4 KICH_BAN_NGHIEM_THU; T11, thêm 02/10/2026): `--index N` mở theo
index OpenCV, không tra cổng hub (`index_camera_factory`); index đổi sau khởi động lại hay cắm lại, tra mỗi lần bằng
`python -m autopark.video.camera_bench list`. Tệp và thư mục ảnh khóa theo TÊN (`--camera-name`, mặc định tren_cao):
calibration/cam_<tên>[_WxH].json, runs/calib/<ngày giờ>_<tên>/; bản ghi có `camera.hub_port` null. Ô chọn cổng bị khóa.
Chỉ kiểm offscreen với camera giả; với camera trên cao thật CHƯA THỬ (bộ dò khung hỏng của `UsbCameraSource` và mô hình
mắt cá chọn cho camera Sunplus của xe; camera khác có thể cần mô hình ống kính khác). Camera trên cao cắm vào cổng gốc
của máy có SỐ trùng cổng hub của camera xe cần hiệu chuẩn (cổng gốc của laptop thường mang số 1–4) thì `--port N` báo
lỗi chứ không đoán, kể cả khi các camera xe khác đang cắm: một cổng không có cổng nào khác làm mốc hub (`resolve_ports`).
Khi đó cắm camera trên cao vào cổng có số khác N, hay rút nó ra lúc hiệu chuẩn camera xe.

- Camera gọi theo CỔNG HUB (`resolve_ports` đổi cổng → index OpenCV lúc mở; index đổi sau khởi động lại), mặc định
  640×480 MJPG — mode chạy chung bốn camera; 1280×720 chọn được nhưng là hiệu chuẩn RIÊNG cho mode đó (tệp có hậu tố).
  Hiệu chuẩn từng camera một, không mở cả bốn cùng lúc: một camera một mình trên hub chưa thấy khung hỏng ở 720p
  (docs/GIAI_DOAN_2_BAN_THU.md), nhưng khung hỏng vẫn bị loại và đếm nếu có.
- Một luồng riêng đọc camera và dò bảng trên từng khung (`fisheye_calib.assess_frame`, chế độ "live"); giao diện chỉ
  lấy khung mới nhất nên không bị `read()` chặn. Ảnh sống có vẽ góc bảng, lưới phủ (đỏ = chưa có góc nào của ảnh đã
  chụp, xanh đậm dần theo số góc) và các góc đã chụp (chấm vàng).
- Dòng trạng thái: thấy bảng chưa, nét không (độ rộng biên), tương phản, cách mép, khung hỏng, đứng yên, khác ảnh đã chụp.
- "Chụp" (hoặc phím cách, kể cả khi ô cỡ ô / ngưỡng mờ đang giữ focus) chỉ nhận khung đạt chất lượng. "Tự chụp": chụp
  khi bảng đạt, đứng yên đủ lâu và khác mọi ảnh đã chụp (`AutoCaptureGate`).
- "Hiệu chuẩn" chạy `calibrate_fisheye` trong luồng nền; hiện RMS, RMS từng ảnh (ảnh bị loại ghi lý do), trường nhìn,
  sai số chuyển sang mô hình dự án, tiêu chí ĐỀ XUẤT; ô bên phải hiện ảnh sống đã nắn (kéo "balance"). Trong lúc chạy,
  ô chọn cổng/mode bị khoá; nếu camera/mode vẫn bị đổi (gọi `reopen`), kết quả của lần chạy đó bị bỏ, không gán cho
  camera mới mở.
- "Lưu" ghi calibration/cam_p<cổng>.json (mode khác 640×480 thêm hậu tố kích thước) và ảnh đã chụp + captures.json +
  bản sao tệp hiệu chuẩn vào runs/calib/<ngày giờ>_p<cổng>/. Ảnh ghi qua cv2.imencode (đường dẫn tiếng Việt).

Camera lấy qua tham số `open_camera(cổng, rộng, cao)` nên test cắm được nguồn giả; `main()` (qua `build_window`) dùng
`resolve_ports` + `UsbCameraSource`, hay `index_camera_factory` với `--index`. Công cụ chưa từng chạy với camera thật khi
viết (chỉ test offscreen với nguồn giả).

Bước sau nội tham (thêm tối 24/09/2026): ngoại tham (bảng đặt trên sàn ở vị trí đo bằng thước) và mặt nạ ROI làm ở giao
diện riêng `autopark.ui.roi_app` (docs/NGOAI_THAM_VA_ROI.md). Giao diện đó dùng lại `LiveCamera`, `to_qimage`,
`parse_size` và `usb_camera_factory` của tệp này — đổi chữ ký các hàm đó thì kiểm cả tests/test_roi_tool.py.
"""
from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import sys
import threading
import time
from typing import Callable

import cv2
import numpy as np

from PySide6.QtCore import QEvent, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QListWidget,
                               QMainWindow, QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget)

from autopark.perception import fisheye_calib as fc
from autopark.perception.calib_board import BoardSpec
from autopark.power_throttling import apply_ecoqos_policy
from autopark.ui.process_status import add_ecoqos_label
from autopark.video.sources import FrameReadError

PORTS = (1, 2, 3, 4)
SIZES = ((640, 480), (1280, 720))
DEFAULT_CAMERA_NAME = "tren_cao"     # tên camera ngoài hub khi --index không kèm --camera-name (T11)
# (cổng hub, hay None với camera ngoài hub; rộng, cao) → nguồn có read() / close()
CameraFactory = Callable[[int | None, int, int], object]


def to_qimage(image_bgr: np.ndarray) -> QImage:
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


def _f(x, nd: int = 1) -> str:
    return "—" if x is None else f"{x:.{nd}f}".replace(".", ",")


@dataclass
class LiveFrame:
    seq: int
    t: float
    image: np.ndarray
    source_path: str
    detection: fc.Detection
    quality: fc.FrameQuality
    detect_ms: float


@dataclass
class CameraCounters:
    frames: int = 0
    truncated: int = 0              # khung bị cắt cụt nguồn đã loại (FrameReadError)
    torn: int = 0                   # khung có dải xé nguồn đã loại
    duplicates: int = 0
    read_failures: int = 0
    damaged_seen: int = 0           # khung hỏng lọt qua nguồn nhưng assess_frame bắt được
    detect_errors: int = 0
    open_error: str | None = None
    last_error: str | None = None


class LiveCamera(threading.Thread):
    """Một luồng: mở camera, đọc liên tục, dò bảng trên từng khung, giữ khung mới nhất (không hàng đợi)."""

    def __init__(self, open_camera: CameraFactory, port: int | None, size: tuple[int, int], spec: BoardSpec,
                 max_edge_width: float = fc.MAX_EDGE_WIDTH_PX, clock=time.perf_counter, *, name: str | None = None):
        # `name`: camera ngoài hub (T11), chỉ dùng cho tên luồng; `port` (None khi đó) vẫn được chuyển nguyên cho open_camera
        super().__init__(daemon=True, name=f"calib_cam_p{port}" if name is None else f"calib_cam_{name}")
        self.open_camera, self.port, self.size, self.spec, self.clock = open_camera, port, size, spec, clock
        self.max_edge_width = max_edge_width           # giao diện đổi được lúc chạy (gán float là nguyên tử)
        self.counters = CameraCounters()
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.source = None
        self._latest: LiveFrame | None = None
        self._seq = 0

    def run(self) -> None:
        try:
            self.source = self.open_camera(self.port, *self.size)
        except Exception as exc:  # noqa: BLE001 - lỗi mở phải hiện lên giao diện
            self.counters.open_error = f"{type(exc).__name__}: {exc}"
            return
        try:
            while not self.stop_event.is_set():
                try:
                    frame = self.source.read()
                except FrameReadError as exc:
                    self._count(str(exc))
                    continue
                except Exception as exc:  # noqa: BLE001
                    with self.lock:
                        self.counters.read_failures += 1
                        self.counters.last_error = f"{type(exc).__name__}: {exc}"
                    time.sleep(0.05)
                    continue
                if frame is None:                        # nguồn phát lại đã hết
                    self.counters.last_error = "nguồn hết khung"
                    break
                t0 = self.clock()
                try:
                    det, q = fc.assess_frame(frame.image, self.spec, mode="live", max_edge_width=self.max_edge_width)
                except Exception as exc:  # noqa: BLE001 - lỗi dò trên một khung không được làm chết luồng
                    with self.lock:
                        self.counters.detect_errors += 1
                        self.counters.last_error = f"dò bảng lỗi: {type(exc).__name__}: {exc}"
                    continue
                ms = 1000.0 * (self.clock() - t0)
                with self.lock:
                    self._seq += 1
                    self.counters.frames += 1
                    if q.damaged:
                        self.counters.damaged_seen += 1
                    self._latest = LiveFrame(self._seq, frame.meta.stamp.t, frame.image, frame.meta.image_path, det, q, ms)
        finally:
            try:
                self.source.close()
            except Exception:  # noqa: BLE001
                pass

    def _count(self, message: str) -> None:
        with self.lock:
            c = self.counters
            if "truncated frame" in message:
                c.truncated += 1
            elif "torn frame" in message:
                c.torn += 1
            elif "previous frame" in message:
                c.duplicates += 1
            else:
                c.read_failures += 1
                c.last_error = message

    def latest(self) -> LiveFrame | None:
        with self.lock:
            return self._latest

    def stop(self, timeout: float = 3.0) -> bool:
        """Dừng và chờ luồng; trả True nếu luồng CHƯA dừng (read() đang treo)."""
        self.stop_event.set()
        if self.is_alive():
            self.join(timeout)
        return self.is_alive()


@dataclass
class Capture:
    name: str
    image: np.ndarray
    corners: np.ndarray
    quality: dict
    descriptor: np.ndarray
    t: float
    auto: bool


class ImageView(QWidget):
    """Ảnh co giãn giữ tỉ lệ, có dải chữ ở trên."""

    def __init__(self, caption: str, parent=None):
        super().__init__(parent)
        self.caption = caption
        self.pixmap: QPixmap | None = None
        self.placeholder = ""
        self.setMinimumSize(400, 300)

    def set_image(self, image: QImage | None, placeholder: str = "") -> None:
        self.pixmap = None if image is None else QPixmap.fromImage(image)
        self.placeholder = placeholder
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#101821"))
        font = QFont("Segoe UI")
        font.setPixelSize(13)
        if self.pixmap is not None:
            scaled = self.pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap((self.width() - scaled.width()) // 2, (self.height() - scaled.height()) // 2, scaled)
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


class CalibWindow(QMainWindow):
    """`camera_name` (T11): camera KHÔNG qua hub 1..4 (camera trên cao), khóa theo tên thay cho cổng (`port` bỏ qua, thành
    None); `camera_index` = index OpenCV lúc mở, chỉ để hiện và ghi vào bản ghi. Tên sai → ValueError."""

    def __init__(self, open_camera: CameraFactory, *, port: int | None = 1, size: tuple[int, int] = fc.DEFAULT_SIZE,
                 spec: BoardSpec = BoardSpec(), out_dir: Path = Path("calibration"), runs_dir: Path = Path("runs/calib"),
                 gate: fc.AutoCaptureGate | None = None, min_images: int = fc.MIN_IMAGES, device: str | None = None,
                 camera_name: str | None = None, camera_index: int | None = None, start: bool = True):
        if camera_name is not None and (error := fc.camera_name_error(camera_name)):
            raise ValueError(error)
        super().__init__()
        self.camera_name, self.camera_index = camera_name, camera_index
        self.open_camera, self.size, self.spec = open_camera, tuple(size), spec
        self.port = None if camera_name is not None else int(port)
        self.out_dir, self.runs_dir, self.min_images, self.device = Path(out_dir), Path(runs_dir), min_images, device
        self.gate = gate or fc.AutoCaptureGate()
        self.captures: list[Capture] = []
        self._next_capture = 0
        self._captures_version = 0
        self._session = 0          # tăng mỗi lần reopen(): kết quả hiệu chuẩn của camera/mode trước phải bỏ
        self.calib: fc.FisheyeCalibration | None = None
        self.record: dict | None = None
        self._calib_version = -1
        self._calib_square: float | None = None
        self._calib_thread: threading.Thread | None = None
        self._calib_outcome: tuple | None = None
        self._maps_key = None
        self._maps = None
        self._last_seq = -1
        self._seen_t: deque = deque(maxlen=60)
        self._gate_note = ""
        self.message = ""
        self.last_saved: Path | None = None
        self.live_camera: LiveCamera | None = None

        self.live_view = ImageView("ảnh sống")
        self.undist_view = ImageView("ảnh nắn (xem trước)")
        self.undist_view.set_image(None, "chưa hiệu chuẩn")
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        bold = QFont("Segoe UI")
        bold.setPixelSize(13)
        bold.setBold(True)
        self.status.setFont(bold)
        self.cam_line = QLabel()
        self.cam_line.setTextFormat(Qt.TextFormat.PlainText)

        self.port_box = QComboBox()
        if self.camera_name is not None:                 # camera ngoài hub: một mục, luôn khóa (không đổi sang cổng hub)
            self.port_box.addItem(self.camera_label, None)
        else:
            for p in PORTS:
                self.port_box.addItem(f"cổng {p}", p)
            if self.port not in PORTS:
                self.port_box.addItem(f"cổng {self.port}", self.port)
            self.port_box.setCurrentIndex(self.port_box.findData(self.port))
        self.size_box = QComboBox()                      # dữ liệu là chuỗi "WxH": findData không so được tuple Python
        for w, h in SIZES + (() if self.size in SIZES else (self.size,)):
            self.size_box.addItem(f"{w}×{h}", f"{w}x{h}")
        self.size_box.setCurrentIndex(self.size_box.findData(f"{self.size[0]}x{self.size[1]}"))
        self.port_box.currentIndexChanged.connect(lambda _: self.reopen(self.port_box.currentData(), self.size))
        self.size_box.currentIndexChanged.connect(lambda _: self.reopen(self.port, parse_size(self.size_box.currentData())))

        self.square_spin = QDoubleSpinBox()
        self.square_spin.setRange(1.0, 200.0)
        self.square_spin.setDecimals(2)
        self.square_spin.setSingleStep(0.05)
        self.square_spin.setValue(spec.square_mm)
        self.square_spin.setSuffix(" mm")
        self.chk_measured = QCheckBox("Đã đo cỡ ô bằng thước")
        self.edge_spin = QDoubleSpinBox()
        self.edge_spin.setRange(0.5, 20.0)
        self.edge_spin.setDecimals(1)
        self.edge_spin.setSingleStep(0.5)
        self.edge_spin.setValue(fc.MAX_EDGE_WIDTH_PX)
        self.edge_spin.setSuffix(" px")
        self.edge_spin.valueChanged.connect(self._on_edge)
        self.chk_auto = QCheckBox("Tự chụp")
        self.chk_cov = QCheckBox("Lưới phủ")
        self.chk_cov.setChecked(True)
        self.btn_capture = QPushButton("Chụp (phím cách)")
        self.btn_capture.clicked.connect(lambda: self.capture())
        self.btn_delete = QPushButton("Xoá ảnh chọn")
        self.btn_delete.clicked.connect(self.delete_selected)
        self.btn_calib = QPushButton("Hiệu chuẩn")
        self.btn_calib.clicked.connect(self.start_calibration)
        self.btn_save = QPushButton("Lưu")
        self.btn_save.clicked.connect(self.save)
        for button in (self.btn_capture, self.btn_delete, self.btn_calib, self.btn_save):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)      # phím cách là "Chụp", không được bấm nhầm nút đang focus
        self.balance_slider = QSlider(Qt.Orientation.Horizontal)
        self.balance_slider.setRange(0, 100)
        self.balance_slider.setValue(30)
        self.balance_label = QLabel()
        self.balance_slider.valueChanged.connect(self._on_balance)
        self.capture_list = QListWidget()
        self.results = QLabel("chưa hiệu chuẩn")
        self.results.setTextFormat(Qt.TextFormat.PlainText)
        self.results.setWordWrap(True)
        self.results.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        mono = QFont("Consolas")
        mono.setPixelSize(12)
        self.results.setFont(mono)
        self.results.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._on_balance(self.balance_slider.value())

        views = QHBoxLayout()
        views.addWidget(self.live_view, 1)
        views.addWidget(self.undist_view, 1)
        left = QVBoxLayout()
        left.addLayout(views, 1)
        left.addWidget(self.status)
        left.addWidget(self.cam_line)
        left_box = QWidget()
        left_box.setLayout(left)

        side = QVBoxLayout()
        row = QHBoxLayout()
        row.addWidget(self.port_box)
        row.addWidget(self.size_box)
        side.addLayout(row)
        side.addWidget(QLabel(f"Bảng {spec.cols}×{spec.rows} góc trong · cỡ ô ĐO ĐƯỢC"))
        side.addWidget(self.square_spin)
        side.addWidget(self.chk_measured)
        row = QHBoxLayout()
        row.addWidget(QLabel("Ngưỡng mờ (đề xuất)"))
        row.addWidget(self.edge_spin)
        side.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(self.chk_auto)
        row.addWidget(self.chk_cov)
        side.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(self.btn_capture)
        row.addWidget(self.btn_delete)
        side.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(self.btn_calib)
        row.addWidget(self.btn_save)
        side.addLayout(row)
        side.addWidget(self.balance_label)
        side.addWidget(self.balance_slider)
        side.addWidget(QLabel("Ảnh đã chụp"))
        side.addWidget(self.capture_list, 2)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.results)
        side.addWidget(scroll, 3)
        side_box = QWidget()
        side_box.setLayout(side)
        side_box.setMaximumWidth(560)
        side_box.setMinimumWidth(420)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.addWidget(left_box, 3)
        layout.addWidget(side_box, 1)
        self.setCentralWidget(root)
        self.resize(1600, 820)
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=lambda: self.capture())
        for spin in (self.square_spin, self.edge_spin):     # ô số không dùng phím cách: phím cách luôn là "Chụp"
            spin.installEventFilter(self)

        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.tick)
        if start:
            self._start_camera()
        self.timer.start()
        self._update_title()
        self._update_buttons()

    # ---- camera -------------------------------------------------------------------------------------------------
    @property
    def camera_key(self) -> str:
        """Khóa camera trong tên thư mục ảnh: "p<cổng>" (camera xe) hay tên (camera ngoài hub)."""
        return f"p{self.port}" if self.camera_name is None else self.camera_name

    @property
    def camera_label(self) -> str:
        """Nhãn camera trên giao diện: "cổng N", hay "tên (index N)" với camera ngoài hub."""
        if self.camera_name is None:
            return f"cổng {self.port}"
        return self.camera_name if self.camera_index is None else f"{self.camera_name} (index {self.camera_index})"

    def _start_camera(self) -> None:
        self.live_camera = LiveCamera(self.open_camera, self.port, self.size, self.spec, self.edge_spin.value(),
                                      name=self.camera_name)
        self.live_camera.start()

    def _stop_camera(self) -> None:
        if self.live_camera is not None and self.live_camera.stop():
            print(f"CẢNH BÁO: luồng camera {self.camera_label} chưa dừng (read() treo)", file=sys.stderr)

    def reopen(self, port: int | None, size: tuple[int, int]) -> None:
        """Đổi camera hoặc mode: bỏ mọi ảnh đã chụp và kết quả (ảnh của camera/mode khác không dùng chung được).

        Một lần hiệu chuẩn còn đang chạy thì không dừng được giữa chừng, nhưng kết quả của nó mang số phiên cũ và bị
        `_poll_calibration` bỏ — kể cả khi quay lại đúng cổng/mode cũ (ảnh của lần mở trước đã bị bỏ). Camera ngoài hub
        (`port` None) chỉ đổi mode; không đổi được giữa camera ngoài hub và cổng hub."""
        if (port is None) != (self.camera_name is not None):
            raise ValueError("camera ngoài hub chỉ đổi mode (cổng None); camera xe cần cổng hub")
        port, size = (None if port is None else int(port)), tuple(size)
        if (port, size) == (self.port, self.size):
            return
        dropped = len(self.captures)
        busy = self._calib_thread is not None                  # đã khởi chạy mà chưa lấy kết quả
        self._stop_camera()
        self.port, self.size = port, size
        self._session += 1
        self.captures.clear()
        self._captures_version += 1
        self._drop_calibration()
        self.gate.reset()
        self._last_seq, self._seen_t = -1, deque(maxlen=60)
        self.capture_list.clear()
        self._start_camera()
        self._update_title()
        self._update_buttons()
        self.message = (f"đã mở {self.camera_label} ở {size[0]}×{size[1]}"
                        + (f"; bỏ {dropped} ảnh đã chụp" if dropped else "")
                        + ("; kết quả hiệu chuẩn đang chạy của camera/mode cũ sẽ bị bỏ" if busy else ""))

    def _update_title(self) -> None:
        self.setWindowTitle(f"Hiệu chuẩn camera — {self.camera_label}, {self.size[0]}×{self.size[1]}")

    def _on_edge(self, value: float) -> None:
        if self.live_camera is not None:
            self.live_camera.max_edge_width = float(value)

    def _on_balance(self, value: int) -> None:
        self.balance_label.setText(f"Ảnh nắn: balance {_f(value / 100.0, 2)} (0 = cắt viền, 1 = giữ cả trường nhìn)")
        self._maps_key = None

    # ---- vòng giao diện ------------------------------------------------------------------------------------------
    def tick(self) -> None:
        self._poll_calibration()
        cam = self.live_camera
        live = cam.latest() if cam is not None else None
        counters = cam.counters if cam is not None else CameraCounters()
        if live is not None and live.seq != self._last_seq:
            self._last_seq = live.seq
            self._seen_t.append(live.t)
            if self.chk_auto.isChecked():
                self._auto_step(live)
            self.live_view.set_image(to_qimage(self._draw_live(live)))
            self._draw_undistorted(live)
        text, alert = self.status_text(live, counters)
        self.status.setText(text)
        self.status.setStyleSheet("color: #ff6b6b;" if alert else "color: #8cf0d6;")
        self.cam_line.setText(self.camera_line(live, counters))

    def _draw_live(self, live: LiveFrame) -> np.ndarray:
        img = live.image.copy()
        if self.chk_cov.isChecked() and self._same_size(live):
            img = fc.draw_coverage(img, fc.coverage_counts([c.corners for c in self.captures], self.frame_size(live)))
        radius = max(1, img.shape[1] // 400)
        for c in self.captures:
            for x, y in c.corners:
                cv2.circle(img, (int(round(x)), int(round(y))), radius, (0, 220, 255), -1)
        if live.detection.found:
            cv2.drawChessboardCorners(img, self.spec.pattern_size, live.detection.corners.reshape(-1, 1, 2), True)
        return img

    def _draw_undistorted(self, live: LiveFrame) -> None:
        if self.calib is None:
            return
        size = self.frame_size(live)
        if size != self.calib.image_size:
            self.undist_view.set_image(None, f"khung {size[0]}×{size[1]} khác cỡ đã hiệu chuẩn {self.calib.image_size}")
            return
        key = (id(self.calib), self.balance_slider.value())
        if key != self._maps_key:
            self._maps = fc.undistort_maps(self.calib.K, self.calib.D, size, self.balance_slider.value() / 100.0)
            self._maps_key = key
        self.undist_view.set_image(to_qimage(fc.undistort_image(live.image, self.calib.K, self.calib.D, maps=self._maps)))

    @staticmethod
    def frame_size(live: LiveFrame) -> tuple[int, int]:
        return (int(live.image.shape[1]), int(live.image.shape[0]))

    def _same_size(self, live: LiveFrame) -> bool:
        return not self.captures or self.frame_size(live) == (self.captures[0].image.shape[1], self.captures[0].image.shape[0])

    def _auto_step(self, live: LiveFrame) -> None:
        q = live.quality
        corners = live.detection.corners if live.detection.found else None
        desc = fc.pose_descriptor(corners, self.spec, self.frame_size(live)) if corners is not None else None
        ok, note = self.gate.update(live.t, corners, q.ok, desc, [c.descriptor for c in self.captures])
        self._gate_note = note
        if ok and self.capture(live, auto=True):
            self.gate.captured(live.t)

    def status_text(self, live: LiveFrame | None, counters: CameraCounters) -> tuple[str, bool]:
        if counters.open_error:
            return f"KHÔNG MỞ ĐƯỢC CAMERA {self.camera_label}: {counters.open_error}", True
        if live is None:
            return "đang chờ khung đầu tiên…", True
        q = live.quality
        if q.damaged:
            return f"KHUNG HỎNG (không dùng): {q.damaged}", True
        if not q.found:
            return (f"Không thấy bảng {self.spec.cols}×{self.spec.rows}: đưa trọn bảng (cả viền trắng) vào khung, đủ sáng, "
                    "không lóa"), True
        parts = [f"Bảng: đủ {self.spec.n_corners} góc",
                 f"nét {_f(q.edge_width_px)} px" if q.edge_width_px is not None else "nét: không đo được",
                 f"tương phản {_f(q.contrast, 0)}", f"cách mép {_f(q.min_margin_px, 0)} px"]
        if self.captures and self._same_size(live):
            desc = fc.pose_descriptor(live.detection.corners, self.spec, self.frame_size(live))
            nearest = min(fc.pose_distance(desc, c.descriptor) for c in self.captures)
            parts.append(f"khác ảnh gần nhất {_f(nearest, 2)}" + (" (TRÙNG)" if nearest < self.gate.min_pose_distance else ""))
        if self.gate.motion_px is not None:
            parts.append(f"dịch {_f(self.gate.motion_px, 1)} px/khung")
        verdict = "ĐẠT" if q.ok else "CHƯA ĐẠT: " + "; ".join(q.reasons)
        text = " · ".join(parts) + f" → {verdict}"
        if self.chk_auto.isChecked() and self._gate_note:
            text += f"   [tự chụp: {self._gate_note}]"
        return text, not q.ok

    def camera_line(self, live: LiveFrame | None, counters: CameraCounters) -> str:
        t = list(self._seen_t)
        fps = (len(t) - 1) / (t[-1] - t[0]) if len(t) >= 2 and t[-1] > t[0] else 0.0
        line = (f"{self.camera_label} · {_f(fps)} khung dò/s · khung hỏng nguồn đã loại {counters.truncated + counters.torn} "
                f"(cắt {counters.truncated}, xé {counters.torn}) · hỏng lọt qua {counters.damaged_seen} · cũ {counters.duplicates} · "
                f"lỗi đọc {counters.read_failures}")
        if counters.detect_errors:
            line += f" · LỖI DÒ {counters.detect_errors}"
        if counters.last_error:
            line += f" · lỗi gần nhất: {counters.last_error[:80]}"
        if live is not None:
            line += f" · dò {_f(live.detect_ms, 0)} ms · khung {live.image.shape[1]}×{live.image.shape[0]}"
        line += f" · đã chụp {len(self.captures)}"
        if self.message:
            line += f"\n{self.message}"
        return line

    # ---- chụp ---------------------------------------------------------------------------------------------------
    def capture(self, live: LiveFrame | None = None, auto: bool = False) -> bool:
        live = live or (self.live_camera.latest() if self.live_camera is not None else None)
        if live is None:
            self.message = "chưa có khung để chụp"
            return False
        q = live.quality
        if not q.ok:
            self.message = "không chụp: " + "; ".join(q.reasons)
            return False
        if not self._same_size(live):
            self.message = f"không chụp: khung {self.frame_size(live)} khác cỡ các ảnh đã chụp"
            return False
        name = f"cap_{self._next_capture:03d}.png"
        self._next_capture += 1
        desc = fc.pose_descriptor(live.detection.corners, self.spec, self.frame_size(live))
        self.captures.append(Capture(name, live.image.copy(), live.detection.corners.copy(), q.to_dict(), desc, live.t, auto))
        self._captures_version += 1
        self.capture_list.addItem(self._item_text(self.captures[-1]))
        self.message = f"đã chụp {name}" + (" (tự chụp)" if auto else "") + f" — {len(self.captures)} ảnh"
        self._update_buttons()
        return True

    def delete_selected(self) -> None:
        rows = sorted({i.row() for i in self.capture_list.selectedIndexes()}, reverse=True)
        for r in rows:
            del self.captures[r]
            self.capture_list.takeItem(r)
        if rows:
            self._captures_version += 1
            self.message = f"đã xoá {len(rows)} ảnh"
            self._update_buttons()

    def _item_text(self, c: Capture) -> str:
        edge = c.quality.get("edge_width_px")
        text = f"{c.name}  nét {_f(edge, 1)} px" + ("  tự" if c.auto else "")
        if self.calib is not None and self._calib_version == self._captures_version:
            v = next((v for v in self.calib.views if v.name == c.name), None)
            if v is not None:
                text += f"  RMS {_f(v.rms_px, 2)} px" if v.used else f"  LOẠI ({_f(v.rms_px, 2)} px): {v.reason}"
        return text

    # ---- hiệu chuẩn ----------------------------------------------------------------------------------------------
    def calibrating(self) -> bool:
        return self._calib_thread is not None and self._calib_thread.is_alive()

    def start_calibration(self) -> bool:
        if self.calibrating():
            return False
        if len(self.captures) < self.min_images:
            self.message = f"cần ít nhất {self.min_images} ảnh, mới có {len(self.captures)}"
            return False
        spec = BoardSpec(self.spec.cols, self.spec.rows, float(self.square_spin.value()))
        views = [(c.name, c.corners) for c in self.captures]
        size = (self.captures[0].image.shape[1], self.captures[0].image.shape[0])
        version, session = self._captures_version, self._session
        self._calib_outcome = None

        def job():
            try:
                calib = fc.calibrate_fisheye(views, spec, size, min_images=self.min_images)
                self._calib_outcome = (session, version, spec, calib, None)
            except Exception as exc:  # noqa: BLE001 - hiện lỗi lên giao diện
                self._calib_outcome = (session, version, spec, None, f"{type(exc).__name__}: {exc}")

        self._calib_thread = threading.Thread(target=job, daemon=True, name="calibrate")
        self._calib_thread.start()
        self.message = f"đang hiệu chuẩn {len(views)} ảnh…"
        self._update_buttons()
        return True

    def _poll_calibration(self) -> None:
        if self._calib_thread is None or self._calib_thread.is_alive():
            return
        if self._calib_outcome is None:                  # luồng dừng mà không để lại kết quả (không lẽ xảy ra): mở khoá
            self._calib_thread = None
            self.message = "hiệu chuẩn dừng mà không có kết quả"
            self._update_buttons()
            return
        session, version, spec, calib, error = self._calib_outcome
        self._calib_thread, self._calib_outcome = None, None
        if session != self._session:
            # kết quả (hoặc lỗi) của camera/mode đã đóng: không gán cho camera đang mở, không hiện số, không nắn ảnh
            self.message = (f"đã đổi camera/mode trong lúc hiệu chuẩn: bỏ kết quả hiệu chuẩn của camera/mode trước "
                            f"(không áp cho {self.camera_label} {self.size[0]}×{self.size[1]}); ảnh của lần mở trước cũng "
                            "đã bị bỏ — chụp lại rồi hiệu chuẩn")
            self._update_buttons()
            return
        if error:
            self.message = f"hiệu chuẩn lỗi: {error}"
            self._update_buttons()
            return
        self.calib, self._calib_version, self._calib_square = calib, version, spec.square_mm
        self.record = self._build_record(spec, images_dir=None)
        self._maps_key = None
        self.results.setText(fc.summary_text(self.record))
        for i, c in enumerate(self.captures):
            self.capture_list.item(i).setText(self._item_text(c))
        stale = version != self._captures_version
        self.message = (f"xong: RMS {_f(calib.rms_px, 3)} px, dùng {calib.n_used}/{len(calib.views)} ảnh"
                        + (" — danh sách ảnh đã đổi trong lúc chạy, bấm Hiệu chuẩn lại" if stale else ""))
        self._update_buttons()

    def _drop_calibration(self) -> None:
        self.calib, self.record, self._calib_version, self._calib_square = None, None, -1, None
        self._maps_key, self._maps = None, None
        self.results.setText("chưa hiệu chuẩn")
        self.undist_view.set_image(None, "chưa hiệu chuẩn")

    def _build_record(self, spec: BoardSpec, images_dir: str | None, extra: dict | None = None) -> dict:
        reports = [{"name": c.name, **c.quality} for c in self.captures]
        measured = spec.square_mm if self.chk_measured.isChecked() else None
        base = {"capture": {"tool": "autopark.ui.calib_app", "size_requested": list(self.size),
                            "auto_captured": sum(c.auto for c in self.captures)}}
        if extra:
            base["capture"].update(extra)
        return fc.calibration_record(self.calib, spec, port=self.port, camera_name=self.camera_name,
                                     camera_index=self.camera_index, square_mm_measured=measured, images_dir=images_dir,
                                     frame_reports=reports, device=self.device, extra=base)

    def _update_buttons(self) -> None:
        # "đang bận" tính tới khi _poll_calibration lấy kết quả (không chỉ tới khi luồng dừng): trong khoảng đó mà đổi
        # camera thì kết quả vẫn bị bỏ theo số phiên, nhưng khoá ô chọn cho người dùng khỏi đổi nhầm lúc đang chạy
        busy = self._calib_thread is not None
        self.btn_calib.setEnabled(not busy and len(self.captures) >= self.min_images)
        self.btn_save.setEnabled(not busy and self.calib is not None and self._calib_version == self._captures_version)
        self.port_box.setEnabled(not busy and self.camera_name is None)     # camera ngoài hub: luôn khóa
        self.size_box.setEnabled(not busy)

    # ---- lưu ----------------------------------------------------------------------------------------------------
    def save(self) -> Path | None:
        if self.calib is None:
            self.message = "chưa hiệu chuẩn, chưa có gì để lưu"
            return None
        if self._calib_version != self._captures_version:
            self.message = "danh sách ảnh đã đổi sau khi hiệu chuẩn: bấm Hiệu chuẩn lại rồi mới lưu"
            return None
        if abs(float(self.square_spin.value()) - float(self._calib_square)) > 1e-9:
            self.message = "cỡ ô đã đổi sau khi hiệu chuẩn: bấm Hiệu chuẩn lại rồi mới lưu"
            return None
        spec = BoardSpec(self.spec.cols, self.spec.rows, float(self._calib_square))
        folder = self.runs_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self.camera_key}"
        suffix = 1
        while folder.exists():
            folder = self.runs_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self.camera_key}_{suffix}"
            suffix += 1
        folder.mkdir(parents=True)
        failed = [c.name for c in self.captures if not fc.write_image(folder / c.name, c.image)]
        record = self._build_record(spec, images_dir=str(folder), extra={"failed_writes": failed})
        path = fc.default_output_path(self.port, self.calib.image_size, self.out_dir, name=self.camera_name)
        existed = path.exists()
        fc.save_calibration(path, record)
        fc.save_calibration(folder / path.name, record)
        captures: dict = {"port": self.port}
        if self.camera_name is not None:                 # camera ngoài hub (T11): tên và index lúc chụp
            captures.update(camera_name=self.camera_name, opencv_index=self.camera_index)
        captures.update({"image_size": list(self.calib.image_size), "board": spec.to_dict(),
                         "captures": [{"name": c.name, "t_s": c.t, "auto": c.auto,
                                       "corners": np.round(c.corners, 4).tolist(), "quality": c.quality}
                                      for c in self.captures]})
        (folder / "captures.json").write_text(json.dumps(captures, ensure_ascii=False, indent=1), encoding="utf-8")
        self.record, self.last_saved = record, path
        self.message = (f"LỖI: {len(failed)} ảnh không ghi được vào {folder}" if failed else
                        f"đã lưu {path}" + (" (ghi đè bản cũ; bản cũ vẫn còn trong runs/calib nếu từng lưu bằng công cụ này)"
                                            if existed else "") + f"; ảnh ở {folder}")
        return path

    def eventFilter(self, obj, event):
        # Ô nhập số (QLineEdit bên trong) nhận ShortcutOverride cho mọi phím in được, nên QShortcut phím cách không chạy
        # khi ô cỡ ô hay ô ngưỡng mờ đang giữ focus — đúng lúc vừa gõ cỡ ô đo được. Hai ô này không dùng phím cách, nên
        # bỏ override: phím cách về "Chụp" (giá trị đang gõ dở vẫn được nhận vì ô số cập nhật theo từng phím).
        if (event.type() == QEvent.Type.ShortcutOverride and (obj is self.square_spin or obj is self.edge_spin)
                and event.key() == Qt.Key.Key_Space and event.modifiers() == Qt.KeyboardModifier.NoModifier):
            event.ignore()
            return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        self.timer.stop()
        try:
            self._stop_camera()
        finally:
            super().closeEvent(event)


def parse_size(text: str) -> tuple[int, int]:
    w, h = text.lower().replace("×", "x").split("x")
    return int(w), int(h)


def usb_camera_factory(port: int, width: int, height: int):
    """Camera thật theo cổng hub: hỏi Windows cổng → index ngay lúc mở (cần pygrabber), mở MJPG ở kích thước yêu cầu.
    Hỏi MỘT cổng, nên số cổng có camera ở hai hub luôn bị từ chối (ValueError của `resolve_ports`), không đoán."""
    from autopark.video.multicam import resolve_ports
    from autopark.video.sources import UsbCameraSource

    spec = resolve_ports([port])[0]
    source = UsbCameraSource(spec.index, width=width, height=height, fps=30, fourcc="MJPG", source_id=spec.source_id)
    if source.mode_mismatch:
        source.close()
        raise ValueError(f"camera cổng {port} không nhận {width}×{height}: {source.mode_mismatch}")
    return source


def index_camera_factory(index: int, *, source_id: str) -> CameraFactory:
    """Camera KHÔNG qua hub 1..4 (camera trên cao, T11): mở theo index OpenCV, KHÔNG tra cổng hub (`resolve_ports`), MJPG
    ở kích thước yêu cầu. Index đổi sau khởi động lại hay cắm lại: tra mỗi lần bằng
    `python -m autopark.video.camera_bench list`. Tệp hiệu chuẩn khóa theo tên camera nên index đổi không lẫn tệp."""
    def open_camera(_port, width: int, height: int):
        from autopark.video.sources import UsbCameraSource

        source = UsbCameraSource(index, width=width, height=height, fps=30, fourcc="MJPG", source_id=source_id)
        if source.mode_mismatch:
            source.close()
            raise ValueError(f"camera index {index} không nhận {width}×{height}: {source.mode_mismatch}")
        return source
    return open_camera


def build_window(argv=None, *, start: bool = True) -> CalibWindow:
    """Cửa sổ từ dòng lệnh (cần QApplication đã có). Tham số sai → mã 2 trước khi mở cửa sổ hay camera nào."""
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    which = p.add_mutually_exclusive_group()
    which.add_argument("--port", type=int, default=None, help="cổng hub của camera xe (1..4); mặc định 1")
    which.add_argument("--index", type=int, default=None, metavar="N",
                       help="camera KHÔNG qua hub 1..4 (camera trên cao): mở theo index OpenCV; tra bằng camera_bench list")
    p.add_argument("--camera-name", default=None, metavar="TÊN",
                   help=f"tên camera ngoài hub cho tệp và bản ghi (chỉ cùng --index; mặc định {DEFAULT_CAMERA_NAME})")
    p.add_argument("--size", type=parse_size, default=fc.DEFAULT_SIZE, help="640x480 (mặc định) hoặc 1280x720")
    p.add_argument("--cols", type=int, default=9)
    p.add_argument("--rows", type=int, default=6)
    p.add_argument("--square-mm", type=float, default=20.0, help="cỡ ô ĐO ĐƯỢC trên bản in (đổi được trong giao diện)")
    p.add_argument("--out-dir", type=Path, default=Path("calibration"))
    p.add_argument("--runs-dir", type=Path, default=Path("runs/calib"))
    p.add_argument("--device", default=None, help="mô tả thiết bị ghi vào tệp (tùy chọn)")
    args = p.parse_args(argv)
    if args.camera_name is not None and args.index is None:
        p.error("--camera-name chỉ dùng cùng --index (camera ngoài hub); camera xe chọn bằng --port")
    common = {"size": args.size, "spec": BoardSpec(args.cols, args.rows, args.square_mm), "out_dir": args.out_dir,
              "runs_dir": args.runs_dir, "device": args.device, "start": start}
    if args.index is None:
        return CalibWindow(usb_camera_factory, port=1 if args.port is None else args.port, **common)
    if args.index < 0:
        p.error(f"--index phải ≥ 0 (đang là {args.index})")
    name = DEFAULT_CAMERA_NAME if args.camera_name is None else args.camera_name
    if error := fc.camera_name_error(name):
        p.error(f"--camera-name: {error}")
    return CalibWindow(index_camera_factory(args.index, source_id=f"cam_{name}"), camera_name=name,
                       camera_index=args.index, **common)


def main(argv=None) -> int:
    ecoqos = apply_ecoqos_policy("ui.calib_app")       # trước mọi việc khác (power_throttling.py)
    app = QApplication.instance() or QApplication(sys.argv)
    window = build_window(argv)
    window.show()
    add_ecoqos_label(window, ecoqos)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
