"""Mở camera và bản quét C1 từ Pi để quan sát khi xe đứng yên."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import time

import cv2
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QPushButton, QSizePolicy, QTabWidget, QVBoxLayout, QWidget,
)

from autopark.perception import fisheye_calib
from autopark.perception.calib_board import BoardSpec
from autopark.rig.remote_view_link import RemoteSensorLink
from autopark.ui import theme
from autopark.ui.rig_app import CameraTile, to_qimage, write_image
from autopark.ui.scan_view import ScanView
from autopark.ui.surround_3d_panel import Surround3DPanel
from autopark.ui.surround_view_panel import SurroundViewPanel


DISPLAY_STALE_S = 0.75
ACTIVE = {"connecting", "live"}
# Vị trí đã đối chiếu trên xe theo thứ tự cổng USB của bộ bốn camera.
FOUR_CAMERA_LABELS = ("Camera 1 · Trước", "Camera 2 · Sau", "Camera 3 · Trái", "Camera 4 · Phải")

class RemoteSensorWindow(QMainWindow):
    def __init__(self, host="", *, camera_count=1, duration_s=180.0, log_path=None,
                 calibration_dir=None, calibration_floor=False, link_factory=RemoteSensorLink, clock=time.monotonic,
                 lidar_dir=None, connection=None, check_esp32=True, saved_host=None):
        super().__init__()
        # Trong app (27/11/2026): `connection` là CarConnection của tab Kết nối xe. IP Pi lấy từ đó (hoặc IP đã lưu ở tab
        # đó), và mở tab này khi xe đã kết nối thì tự bắt đầu xem. `check_esp32=False`: Pi không mở cổng ESP32 mà tab
        # Kết nối xe đang giữ.
        self.connection = connection
        self.check_esp32 = check_esp32
        self.saved_host = saved_host or (lambda: "")
        self._auto_started_for = None
        if camera_count not in (1, 4):
            raise ValueError("Chọn chế độ một hoặc bốn camera")
        self.setWindowTitle("AutoPark — Kiểm hướng cảm biến")
        self.resize(*((1450, 850) if camera_count == 4 else (1200, 720)))
        self.setMinimumSize(*((1060, 600) if camera_count == 4 else (860, 530)))
        self.camera_count = camera_count
        self.duration_s = duration_s
        self.log_path = log_path
        self.calibration_dir = Path(calibration_dir) if calibration_dir is not None else None
        self.calibration_floor = calibration_floor
        self.lidar_dir = Path(lidar_dir) if lidar_dir is not None else Path("runs") / "lidar_pi"
        self.link_factory = link_factory
        self.clock = clock
        self.link = None
        self.shown_frames = [None] * camera_count
        self.shown_scan = None
        self.last_event = None
        self.tabs = None
        self.bird_eye = None
        self.surround_3d = None
        self._lidar_mount = None
        self._bev_sequences = None
        self._bev_logged = False

        self.host = QLineEdit(host)
        self.host.setPlaceholderText("Địa chỉ IP của Pi")
        self.host.setMaximumWidth(184)
        self.host.setAccessibleName("Địa chỉ IP của Pi")
        self.connect_button = QPushButton("Kết nối")
        self.connect_button.setObjectName("connect")
        self.stop_button = QPushButton("Dừng")
        self.stop_button.setEnabled(False)
        self.connect_button.clicked.connect(self.connect_link)
        self.host.returnPressed.connect(self.connect_link)
        self.stop_button.clicked.connect(self.stop_link)

        title = QLabel("Kiểm hướng cảm biến")
        title.setObjectName("title")
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        toolbar.addWidget(title, 1)
        toolbar.addWidget(QLabel("IP của Pi"))
        toolbar.addWidget(self.host)
        toolbar.addWidget(self.connect_button)
        toolbar.addWidget(self.stop_button)

        guide = QLabel("Giữ xe đứng yên. Camera 1–4 theo thứ tự cổng USB trên hub."
                       if camera_count == 4 else
                       "Giữ xe đứng yên. Đặt hộp trước xe rồi dịch sang trái và sang phải.")
        guide.setObjectName("guide")

        camera_labels = FOUR_CAMERA_LABELS if camera_count == 4 else ("Camera 1",)
        self.camera_tiles = [CameraTile(i + 1) for i in range(camera_count)]
        self.camera_status = [QLabel("Chờ ảnh") for _ in self.camera_tiles]
        camera_grid = QGridLayout()
        camera_grid.setContentsMargins(0, 0, 0, 0)
        camera_grid.setSpacing(12)
        for index, (tile, status) in enumerate(zip(self.camera_tiles, self.camera_status)):
            tile.caption = ""
            tile.set_image(None, "Chờ ảnh", False)
            name = camera_labels[index] if camera_count == 4 else "Camera USB"
            camera_grid.addWidget(self._panel(name, status, tile), index // 2, index % 2)
        camera_area = QWidget()
        camera_area.setLayout(camera_grid)

        self.scan_view = ScanView(max_range=2.0, front_up=True)
        self.scan_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.scan_status = QLabel("Chờ bản quét")

        scan_panel = self._panel("LiDAR C1 · bán kính 2 m", self.scan_status, self.scan_view)
        directions = QHBoxLayout()
        for text, alignment in (("Trái", Qt.AlignmentFlag.AlignLeft),
                                ("↑ Trước xe", Qt.AlignmentFlag.AlignHCenter),
                                ("Phải", Qt.AlignmentFlag.AlignRight)):
            label = QLabel(text)
            label.setObjectName("axis")
            label.setAlignment(alignment)
            directions.addWidget(label, 1)
        scan_panel.layout().insertLayout(1, directions)
        # Ghi LiDAR (26/11/2026): mỗi lần bấm là một chỗ đặt xe đứng yên, dùng cho lidar/map_builder.py và
        # planning/slot_finder.py.
        self.lidar_record_button = QPushButton("Ghi LiDAR")
        self.lidar_record_button.setCheckable(True)
        self.lidar_record_button.setEnabled(False)
        self.lidar_record_button.setAccessibleName("Ghi bản quét LiDAR")
        self.lidar_record_button.toggled.connect(self._toggle_lidar_recording)
        self.lidar_record_status = QLabel(f"Lưu vào {self.lidar_dir}")
        self.lidar_record_status.setTextFormat(Qt.TextFormat.PlainText)
        self.lidar_record_status.setWordWrap(True)
        self.lidar_record_status.setObjectName("guide")
        record_row = QHBoxLayout()
        record_row.addWidget(self.lidar_record_button)
        record_row.addWidget(self.lidar_record_status, 1)
        scan_panel.layout().addLayout(record_row)

        panels = QHBoxLayout()
        panels.setSpacing(14)
        panels.addWidget(camera_area, 9 if camera_count == 4 else 6)
        panels.addWidget(scan_panel, 5)

        self.link_status = QLabel("Nhập địa chỉ Pi rồi chọn Kết nối.")
        self.link_status.setTextFormat(Qt.TextFormat.PlainText)
        self.link_status.setWordWrap(True)
        self.link_status.setObjectName("guide")

        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        layout.addLayout(toolbar)

        camera_page = QWidget()
        sensor_layout = QVBoxLayout(camera_page)
        sensor_layout.setContentsMargins(0, 8, 0, 0)
        sensor_layout.setSpacing(10)
        sensor_layout.addWidget(guide)
        if self.calibration_dir is not None:
            self._calibration_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="autopark-board")
            self._auto_gate = fisheye_calib.AutoCaptureGate()
            self._auto_poses = [[] for _ in camera_labels]
            self._auto_job = None
            self._auto_seq = None
            self.calibration_camera = QComboBox()
            self.calibration_camera.setObjectName("calibrationCamera")
            self.calibration_camera.setAccessibleName("Camera lưu ảnh bảng chuẩn")
            self.calibration_camera.addItems(list(camera_labels))
            self.calibration_button = QPushButton("Lưu ảnh bảng trên sàn" if calibration_floor else "Lưu ảnh bảng chuẩn")
            self.calibration_button.clicked.connect(self.capture_calibration)
            self.calibration_auto = QPushButton("Tự lưu ảnh")
            self.calibration_auto.setCheckable(True)
            self.calibration_auto.toggled.connect(self._toggle_calibration_auto)
            self.calibration_auto.setVisible(not calibration_floor)
            self.calibration_status = QLabel("Đặt bảng nằm ngửa ở mốc đã đo rồi lưu ảnh để kiểm tra."
                                             if calibration_floor else "Đặt bảng 9×6 góc trong vào ảnh camera đã chọn.")
            self.calibration_status.setObjectName("calibrationStatus")
            self.calibration_status.setTextFormat(Qt.TextFormat.PlainText)
            self.calibration_status.setWordWrap(True)
            calibration_controls = QHBoxLayout()
            calibration_controls.addWidget(self.calibration_camera)
            calibration_controls.addWidget(self.calibration_auto)
            calibration_controls.addWidget(self.calibration_button)
            calibration_controls.addWidget(self.calibration_status, 1)
            sensor_layout.addLayout(calibration_controls)
        sensor_layout.addLayout(panels, 1)
        if camera_count == 4:
            self.bird_eye = SurroundViewPanel()
            self.bird_eye.rendered.connect(self._record_bev_frame)
            self.tabs = QTabWidget()
            self.tabs.addTab(camera_page, "Camera và C1")
            self.tabs.addTab(self.bird_eye, "Nhìn từ trên (BEV)")
            self.surround_3d = Surround3DPanel()
            self.tabs.addTab(self.surround_3d, "3D quanh xe")
            self.tabs.currentChanged.connect(self._change_tab)
            layout.addWidget(self.tabs, 1)
        else:
            layout.addWidget(camera_page, 1)
        layout.addWidget(self.link_status)
        self.setCentralWidget(page)
        theme.apply_dark(self)          # nền tối chung của AutoPark (26/11/2026)

        self.timer = QTimer(self)
        self.timer.setInterval(60)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        if connection is not None:
            self.host.setReadOnly(True)
            self.host.setToolTip("IP lấy từ tab Kết nối xe")
            self.link_status.setText("Kết nối xe ở tab Kết nối xe; khi xe đã kết nối, tab này tự bắt đầu xem.")
            self._sync_connection()

    # ---- nối với tab Kết nối xe ------------------------------------------------------------------------------------
    def connection_host(self) -> str:
        """IP Pi của tab Kết nối xe: IP đang kết nối, nếu chưa thì IP đã lưu ở tab đó."""
        c = self.connection
        if c is None:
            return self.host.text().strip()
        if c.mode == "pi" and c.target:
            return c.target
        return self.saved_host() or self.host.text().strip()

    def _sync_connection(self) -> None:
        c = self.connection
        if c is None:
            return
        active = self.link is not None and self.link.snapshot().status in ACTIVE
        host = self.connection_host()
        if not active and host and self.host.text() != host:
            self.host.setText(host)
        # Xe vừa kết nối (qua Pi) và tab đang hiện: tự xem, mỗi lần kết nối xe một lần (bấm Dừng thì không tự mở lại).
        session = c.io
        if (session is not None and c.mode == "pi" and session is not self._auto_started_for and not active
                and self.isVisible()):
            self._auto_started_for = session
            self.connect_link()

    def _tick(self) -> None:
        self._sync_connection()
        self.refresh()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_connection()

    @staticmethod
    def _panel(title, status, canvas):
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        label = QLabel(title)
        label.setObjectName("caption")
        status.setTextFormat(Qt.TextFormat.PlainText)
        header = QHBoxLayout()
        header.addWidget(label, 1)
        header.addWidget(status)
        layout.addLayout(header)
        layout.addWidget(canvas, 1)
        return panel

    def _show_event(self, message, *, deduplicate=True):
        if deduplicate:
            if message == self.last_event:
                return
            self.last_event = message
        if self.log_path is not None:
            stamp = time.strftime("%H:%M:%S")
            try:
                with self.log_path.open("a", encoding="utf-8") as log:
                    log.write(f"{stamp} {message}\n")
            except OSError as exc:
                print(f"Lỗi ghi log giao diện: {exc}", file=sys.stderr)

    def capture_calibration(self):
        if self.calibration_dir is None:
            return
        index = self.calibration_camera.currentIndex()
        view = self.link.snapshot() if self.link is not None else None
        sample = view.cameras[index] if view is not None and 0 <= index < len(view.cameras) else None
        if sample is None or view.status != "live" or not 0 <= self.clock() - sample.at <= DISPLAY_STALE_S:
            self.calibration_status.setText("Chưa có ảnh trực tiếp đủ mới từ camera đã chọn.")
            return
        frame = sample.frame
        if frame.shape != (480, 640, 3) or frame.dtype.name != "uint8":
            self.calibration_status.setText("Ảnh camera phải là ảnh màu gốc 640×480.")
            return
        try:
            damaged = fisheye_calib.damage_reason(frame)
            if damaged:
                self.calibration_status.setText(f"Ảnh lỗi: {damaged}")
                return
            # Lượt ngoại tham giữ ảnh gốc để có thể dò bảng sau, kể cả khi nhìn rất xiên.
            if not self.calibration_floor and not fisheye_calib.detect_corners(frame, BoardSpec()).found:
                self.calibration_status.setText("Chưa thấy đủ 9×6 góc trong của bảng chuẩn.")
                return
        except (ValueError, cv2.error) as exc:
            self.calibration_status.setText(f"Lỗi kiểm tra ảnh bảng chuẩn: {exc}")
            return
        self._save_calibration_frame(index, frame)

    def _save_calibration_frame(self, index, frame):
        directory = self.calibration_dir / f"cam_p{index + 1}"
        path = None
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=directory, prefix="cap_", suffix=".png", delete=False) as capture:
                path = Path(capture.name)
            if not write_image(path, frame):
                raise OSError("không ghi được tệp PNG")
        except (OSError, ValueError, cv2.error) as exc:
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            self.calibration_status.setText(f"Lỗi lưu ảnh bảng chuẩn: {exc}")
            return False
        count = sum(image.is_file() for image in directory.glob("cap_*.png"))
        camera = self.calibration_camera.itemText(index)
        self.calibration_status.setText(f"Đã lưu {count} ảnh · {camera} · {path.name}")
        self._show_event(f"CALIB_CAPTURE camera={index + 1}", deduplicate=False)
        return True

    def _toggle_calibration_auto(self, active):
        self.calibration_auto.setText("Dừng tự lưu" if active else "Tự lưu ảnh")
        self.calibration_camera.setEnabled(not active)
        self.calibration_button.setEnabled(not active)
        self._auto_gate.reset()
        self._auto_seq = None
        self.calibration_status.setText("Đưa cả bàn cờ vào ảnh và giữ yên." if active else "Đã dừng tự lưu.")

    def _refresh_auto_calibration(self, view, now):
        index = self.calibration_camera.currentIndex()
        sample = view.cameras[index] if view.status == "live" else None
        if (sample is None or not 0 <= now - sample.at <= DISPLAY_STALE_S
                or (self.tabs is not None and self.tabs.currentWidget() is self.bird_eye)):
            self._auto_gate.reset()
            self._auto_seq = None
            self.calibration_status.setText("Chờ ảnh trực tiếp trong tab Camera và C1.")
            return

        if self._auto_job is not None:
            pending, future = self._auto_job
            if not future.done():
                return
            self._auto_job = None
            if self._auto_seq == pending.seq and 0 <= now - pending.at <= DISPLAY_STALE_S:
                self._use_auto_calibration_result(index, pending, future)

        if sample.seq != self._auto_seq:
            self._auto_seq = sample.seq
            future = self._calibration_executor.submit(fisheye_calib.assess_frame, sample.frame, BoardSpec())
            self._auto_job = (sample, future)

    def _use_auto_calibration_result(self, index, sample, future):
        try:
            detection, quality = future.result()
        except (ValueError, cv2.error) as exc:
            self._auto_gate.reset()
            self.calibration_status.setText(f"Lỗi kiểm tra ảnh bảng chuẩn: {exc}")
            return

        corners = detection.corners if detection.found else None
        descriptor = (fisheye_calib.pose_descriptor(corners, BoardSpec(), sample.frame.shape[:2][::-1])
                      if corners is not None else None)
        poses = self._auto_poses[index]
        ready, note = self._auto_gate.update(sample.at, corners, quality.ok, descriptor, poses)
        if ready:
            if not self._save_calibration_frame(index, sample.frame):
                return
            poses.append(descriptor)
            self._auto_gate.captured(sample.at)
            note = "Đổi vị trí hoặc nghiêng bảng"
        elif note.startswith("trùng tư thế"):
            note = "Đổi vị trí hoặc nghiêng bảng"
        elif not quality.ok and quality.found:
            note = quality.reasons[0]
        self.calibration_status.setText(f"Đã tự lưu {len(poses)} ảnh · {note}.")

    @staticmethod
    def _set_sensor_status(label, text, fresh):
        style = f"color: {theme.OK}; font-weight: 700" if fresh else f"color: {theme.WARN}"
        if label.text() != text:
            label.setText(text)
        if label.styleSheet() != style:
            label.setStyleSheet(style)

    def _can_record_lidar(self):
        return self.link is not None and hasattr(self.link, "start_lidar_recording")

    def _toggle_lidar_recording(self, active):
        if active:
            if not self._can_record_lidar():
                self.lidar_record_button.setChecked(False)
                return
            name = time.strftime("c1_%Y%m%d_%H%M%S")
            try:
                path = self.link.start_lidar_recording(self.lidar_dir / name)
            except (OSError, RuntimeError, ValueError) as exc:
                self.lidar_record_status.setText(f"Lỗi bắt đầu ghi: {exc}")
                self.lidar_record_button.blockSignals(True)
                self.lidar_record_button.setChecked(False)
                self.lidar_record_button.blockSignals(False)
                return
            self.lidar_record_button.setText("Dừng ghi")
            self.lidar_record_status.setText(f"Đang ghi · 0 vòng · {path.name}. Giữ xe đứng yên.")
            self._show_event(f"LIDAR_RECORD_START {path.name}", deduplicate=False)
        else:
            self._finish_lidar_recording()

    def _finish_lidar_recording(self):
        self.lidar_record_button.blockSignals(True)
        self.lidar_record_button.setChecked(False)
        self.lidar_record_button.blockSignals(False)
        self.lidar_record_button.setText("Ghi LiDAR")
        if not self._can_record_lidar():
            return
        try:
            result = self.link.stop_lidar_recording()
        except (OSError, ValueError) as exc:
            self.lidar_record_status.setText(f"Lỗi ghi tệp LiDAR: {exc}")
            return
        if result is not None:
            path, scans = result
            self.lidar_record_status.setText(f"Đã ghi {scans} vòng · {path}")
            self._show_event(f"LIDAR_RECORD_STOP {path.name} scans={scans}", deduplicate=False)

    def connect_link(self):
        if self.link is not None and self.link.snapshot().status in ACTIVE:
            return
        self.stop_link()
        try:
            extra = {} if self.check_esp32 else {"check_esp32": False}
            self.link = self.link_factory(self.host.text().strip(), duration_s=self.duration_s,
                                          camera_count=self.camera_count, **extra)
            self.link.start()
        except (OSError, RuntimeError, ValueError) as exc:
            self.link = None
            self.link_status.setText(f"Lỗi kết nối: {exc}")
            self._show_event(f"ERROR {exc}")
            return
        self.refresh()

    def stop_link(self):
        if self.link is not None:
            if self.lidar_record_button.isChecked():
                self._finish_lidar_recording()
            self.link.close()
            self.link = None
            self._show_event("STOPPED")
        self.shown_frames = [None] * self.camera_count
        self.shown_scan = None
        if self.calibration_dir is not None:
            self._auto_gate.reset()
            self._auto_seq = None
        self._bev_sequences = None
        self._bev_logged = False
        if self.bird_eye is not None:
            self.bird_eye.clear()
        for tile, status in zip(self.camera_tiles, self.camera_status):
            tile.pixmap = None
            tile.set_image(None, "Chờ ảnh", False)
            self._set_sensor_status(status, "Chờ ảnh", False)
        self.scan_view.set_scan(None, stale=True)
        self._set_sensor_status(self.scan_status, "Chờ bản quét", False)
        self.lidar_record_button.setEnabled(False)
        self.link_status.setText("Chọn Kết nối để mở phiên quan sát.")
        self.host.setEnabled(True)
        self.connect_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def _refresh_camera(self, index, sample, now, active):
        tile, status = self.camera_tiles[index], self.camera_status[index]
        fresh = active and sample is not None and 0 <= now - sample.at <= DISPLAY_STALE_S
        if fresh:
            self._set_sensor_status(status, "Trực tiếp", True)
            if sample.seq != self.shown_frames[index]:
                tile.set_image(to_qimage(sample.frame), f"Ảnh {sample.seq}", False)
                self.shown_frames[index] = sample.seq
        else:
            text = "Dữ liệu cũ" if sample is not None else "Chờ ảnh"
            self._set_sensor_status(status, text, False)
            if self.shown_frames[index] is not None or tile.detail != text:
                tile.pixmap = None
                tile.set_image(None, text, True)
                self.shown_frames[index] = None
        return fresh

    def _change_tab(self, _index):
        self._bev_sequences = None
        if self.tabs.currentWidget() is self.bird_eye:
            self.refresh()
        else:
            self.bird_eye.clear()

    def _refresh_bev(self, samples, camera_fresh):
        if self.tabs is None or self.tabs.currentWidget() is not self.bird_eye:
            return
        sequences = tuple(sample.seq if fresh else None for sample, fresh in zip(samples, camera_fresh))
        previous = self._bev_sequences
        if sequences == previous:
            return
        self._bev_sequences = sequences
        if previous is not None and any(old is not None and new is None for old, new in zip(previous, sequences)):
            self.bird_eye.clear()
        frames = {index: sample.frame for index, (sample, fresh) in enumerate(zip(samples, camera_fresh), 1)
                  if fresh}
        if frames:
            self.bird_eye.submit(frames)

    def _refresh_3d(self, view, camera_fresh, scan_fresh):
        """Thẻ 3D quanh xe: ảnh camera còn mới và điểm LiDAR (gá theo configs/dinh_vi_lidar_v0.json)."""
        if self.tabs is None or self.surround_3d is None or self.tabs.currentWidget() is not self.surround_3d:
            return
        from autopark.perception import surround_3d as s3
        frames = {index: sample.frame for index, (sample, fresh) in enumerate(zip(view.cameras, camera_fresh), 1)
                  if fresh}
        lidar = None
        if scan_fresh:
            if self._lidar_mount is None:
                from autopark.lidar.pose_config import load_lidar_pose_config
                self._lidar_mount = load_lidar_pose_config().mount
            lidar = s3.scan_to_vehicle(view.scan, self._lidar_mount)
        height = self._lidar_mount.z_m if self._lidar_mount is not None and self._lidar_mount.z_m else s3.LIDAR_HEIGHT_M
        self.surround_3d.submit(frames, s3.Overlays(lidar_xy=lidar, lidar_z=height))

    def _record_bev_frame(self, camera_count, is_preview):
        if camera_count == self.camera_count and not self._bev_logged:
            self._bev_logged = True
            mode = "preview" if is_preview else "calibrated"
            self._show_event(f"BEV_RENDERED cameras={camera_count} mode={mode}", deduplicate=False)

    def refresh(self):
        if self.link is None:
            return
        view = self.link.snapshot()
        now = self.clock()
        is_active = view.status in ACTIVE
        self.host.setEnabled(not is_active)
        self.connect_button.setEnabled(not is_active)
        self.stop_button.setEnabled(is_active)

        camera_fresh = [self._refresh_camera(i, sample, now, is_active)
                        for i, sample in enumerate(view.cameras)]
        if self.calibration_dir is not None and self.calibration_auto.isChecked():
            self._refresh_auto_calibration(view, now)
        self._refresh_bev(view.cameras, camera_fresh)
        scan_fresh = (is_active and view.scan is not None and view.scan_at is not None
                      and 0 <= now - view.scan_at <= DISPLAY_STALE_S)
        self._refresh_3d(view, camera_fresh, scan_fresh)

        recording = self.lidar_record_button.isChecked()
        self.lidar_record_button.setEnabled(recording or (scan_fresh and self._can_record_lidar()))
        if recording:
            if not is_active:
                self._finish_lidar_recording()
            else:
                count = self.link.lidar_recording_count()
                if count is not None:
                    text = f"Đang ghi · {count} vòng. Giữ xe đứng yên."
                    if self.lidar_record_status.text() != text:
                        self.lidar_record_status.setText(text)

        if scan_fresh:
            self._set_sensor_status(self.scan_status, "Trực tiếp", True)
            if view.scan_seq != self.shown_scan:
                self.scan_view.set_scan(view.scan, stale=False)
                self.shown_scan = view.scan_seq
        else:
            text = "Dữ liệu cũ" if view.scan_at is not None else "Chờ bản quét"
            self._set_sensor_status(self.scan_status, text, False)
            if self.shown_scan is not None or not self.scan_view.stale:
                self.scan_view.set_scan(None, stale=True)
                self.shown_scan = None

        status_text = {
            "connecting": "Đang kết nối. Nhập mật khẩu Pi ở cửa sổ SSH nếu được hỏi.",
            "live": f"Wi-Fi · {sum(camera_fresh)}/{self.camera_count} camera trực tiếp"
                    f" · C1 {'đang cập nhật' if scan_fresh else 'đang chờ mẫu mới'}.",
            "ended": "Phiên quan sát đã kết thúc. Chọn Kết nối để mở lại.",
            "error": "Kết nối có lỗi. Kiểm tra cửa sổ SSH rồi thử lại.",
            "stopped": "Phiên quan sát đã dừng.",
        }.get(view.status, view.status)
        if view.status == "error" and view.detail:
            status_text += f" {view.detail}"
        if len(camera_fresh) == self.camera_count and all(camera_fresh) and scan_fresh:
            self._show_event(f"LIVE cameras={self.camera_count} lidar=1")
        elif view.status in {"error", "ended", "stopped"}:
            self._show_event(f"{view.status.upper()} {view.detail}".rstrip())
        elif (any(sample is not None and not fresh for sample, fresh in zip(view.cameras, camera_fresh))
              or (view.scan_at is not None and not scan_fresh)):
            self._show_event("STALE")
        else:
            self._show_event("CONNECTING")
        if self.link_status.text() != status_text:
            self.link_status.setText(status_text)

    def closeEvent(self, event):
        self.timer.stop()
        self.stop_link()
        if self.calibration_dir is not None:
            self._calibration_executor.shutdown(wait=False, cancel_futures=True)
        if self.bird_eye is not None:
            self.bird_eye.shutdown()
        if self.surround_3d is not None:
            self.surround_3d.shutdown()
        super().closeEvent(event)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="", help="Địa chỉ IP của Raspberry Pi")
    parser.add_argument("--cameras", type=int, choices=(1, 4), default=4,
                        help="Số camera USB trong cửa sổ quan sát")
    parser.add_argument("--seconds", type=float, default=180.0, help="Thời lượng mỗi phiên quan sát")
    parser.add_argument("--log", type=Path, default=None, help="Tệp log sự kiện giao diện")
    parser.add_argument("--calibration-dir", type=Path, default=None,
                        help="Bật lưu ảnh bảng chuẩn vào thư mục chỉ định")
    parser.add_argument("--calibration-floor", action="store_true",
                        help="Lưu ảnh nguyên gốc của lần đặt bảng trên sàn để giải ngoại tham")
    parser.add_argument("--bird-eye", action="store_true", help="Mở tab nhìn từ trên khi khởi động")
    parser.add_argument("--lidar-dir", type=Path, default=None,
                        help="Thư mục lưu bản ghi LiDAR của nút Ghi LiDAR (mặc định runs/lidar_pi)")
    args = parser.parse_args(argv)
    if args.bird_eye and args.cameras != 4:
        parser.error("--bird-eye dùng với chế độ bốn camera")
    if args.calibration_floor and args.calibration_dir is None:
        parser.error("--calibration-floor cần --calibration-dir")

    app = QApplication([])
    app.setFont(QFont("Segoe UI", 10))
    window = RemoteSensorWindow(args.host, camera_count=args.cameras,
                                duration_s=args.seconds, log_path=args.log, calibration_dir=args.calibration_dir,
                                calibration_floor=args.calibration_floor, lidar_dir=args.lidar_dir)
    if args.bird_eye:
        window.tabs.setCurrentWidget(window.bird_eye)
    window.show()
    if args.host:
        QTimer.singleShot(0, window.connect_link)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
