"""Ngăn "Ghi cảm biến" của cửa sổ đỗ xe `ui.lidar_app` (T3, 02/10/2026): bật tắt bản ghi bốn camera + LiDAR trong phiên
đỗ (`rig.session_recording.SessionSensorRecorder`) và báo trạng thái của nó. Tài liệu: docs/VAN_HANH.md.

Ghi mọi khung tốt của camera ở ngăn AI camera và mọi vòng quét của ngăn LiDAR vào một thư mục, cùng đồng hồ perf_counter
với log VehicleIO và dấu đồng bộ. Không gửi gì tới bo, không dừng hay chặn xe, không mở thiết bị nào.

- "Bắt đầu ghi" bị khóa khi xe đang chạy (RUNNING/STOPPING: luồng giao diện là vòng điều khiển 50 Hz, mà bắt đầu ghi
  phải ghi meta.json trên luồng này), khi chưa có nguồn nào và khi bản ghi trước còn ghi nốt. "Dừng ghi" luôn bấm được
  và không chặn: luồng ghi ghi nốt hàng đợi rồi báo XONG.
- Timer 1 s: mốc đồng hồ định kỳ, ngưỡng đĩa, lỗi ghi, nguồn rời/nối lại (`SessionSensorRecorder.poll`); mọi lỗi ở lại
  trong nhật ký của ngăn.
- Huy hiệu "● ĐANG GHI" ở thanh trên của cửa sổ, cạnh nút dấu đồng bộ, chỉ hiện khi đang ghi.

Chỉ kiểm bằng test offscreen với nguồn giả (tests/test_record_dock_ui.py); CHƯA THỬ với camera và LiDAR thật.
"""
from __future__ import annotations

from dataclasses import replace
from html import escape
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDockWidget, QFileDialog, QFrame, QLabel, QLineEdit, QListWidget,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from autopark.rig.session_recording import (DEFAULT_ROOT, DRIVING_STATES, RecordStartError, SessionSensorRecorder,
                                            fmt_dec, fmt_int, outside_ignored_runs)
from autopark.ui import theme
from autopark.ui.theme import Card, WrapLabel

HINT = ("Ghi mọi khung tốt của camera ở ngăn AI camera và mọi vòng LiDAR của ngăn LiDAR vào một thư mục, cùng đồng hồ "
        "perf_counter với log VehicleIO và dấu đồng bộ. Không gửi gì tới bo, không dừng hay chặn xe.")
LOCKED_WHILE_DRIVING = ("Bắt đầu ghi trước Bắt đầu đỗ: lúc xe chạy, luồng giao diện là vòng điều khiển 50 Hz, không ghi "
                        "đĩa lâu")
NO_SOURCE = "Bật AI camera hoặc kết nối LiDAR trước"
NOT_IGNORED = "Thư mục không bị git bỏ qua: ảnh camera có thể lọt vào git"
LOG_MAX = 200


def _clock(seconds: float | None) -> str:
    s = int(seconds or 0)
    return f"{s // 60:02d}:{s % 60:02d}"


def _duration(seconds: float | None) -> str:
    s = int(round(seconds or 0))
    return f"{s // 60} phút {s % 60:02d} s" if s >= 60 else f"{s} s"


def _line(text: str, tone: str | None = None, bold: bool = False) -> str:
    style = (f"color: {tone};" if tone else "") + ("font-weight: 600;" if bold else "")
    return f'<span style="{style}">{escape(text)}</span>' if style else escape(text)


def status_lines(st: dict, plan: str = "") -> list[tuple[str, str | None]]:
    """Các dòng của thẻ "Trạng thái" từ `SessionSensorRecorder.status()`: (chữ, màu hay None). `plan`: "camera 1 2 ·
    LiDAR COM3" — nguồn sẽ ghi khi bấm "Bắt đầu ghi" (dòng lúc chưa ghi)."""
    state = st.get("state")
    free = st.get("free_gb")
    drive = str(st.get("drive") or "ổ đĩa")
    drive = drive[:1].upper() + drive[1:]                   # "Ổ D" (capitalize() sẽ hạ chữ D)
    disk = f"{drive}: còn {fmt_dec(free)} GB." if free is not None else f"{drive}: không đọc được dung lượng trống."
    lines: list[tuple[str, str | None]] = []
    if state == "idle":
        lines.append((f"Chưa ghi. Sẽ ghi: {plan}. {disk}" if plan else f"Chưa ghi. {NO_SOURCE}. {disk}", None))
    elif state == "recording":
        parts = [f"ĐANG GHI {_clock(st.get('elapsed_s'))}"]
        if st.get("cameras"):
            cams = f"camera {len(st.get('ports') or [])} cổng, {fmt_int(st.get('frames_total') or 0)} khung " \
                   f"(bỏ {fmt_int(st.get('dropped_total') or 0)})"
            parts.append(cams if st.get("cam_attached") else cams + ", camera đã rời")
        if st.get("lidar"):
            lidar = f"LiDAR {fmt_int(st.get('lidar_scans') or 0)} vòng"
            parts.append(lidar if st.get("lidar_attached") else lidar + ", LiDAR đã rời")
        rate = st.get("mb_per_s")
        parts.append(f"{fmt_dec(st.get('mb_written') or 0, 0)} MB" + (f", {fmt_dec(rate)} MB/s" if rate else ""))
        if st.get("pending_frames"):
            parts.append(f"chờ ghi {fmt_int(st['pending_frames'])} khung")
        if free is not None:
            minutes = st.get("minutes_left")
            parts.append(f"ổ còn {fmt_dec(free)} GB" + (f" ≈ {minutes:.0f} phút" if minutes is not None else ""))
        lines.append((" · ".join(parts), theme.ACCENT))
    elif state == "draining":
        lines.append((f"ĐANG GHI NỐT: còn {fmt_int(st.get('pending_frames') or 0)} khung chờ ghi", theme.ACCENT))
    elif state == "done":
        lines.append((f"XONG: {st.get('folder')} · {_duration(st.get('elapsed_s'))} · "
                      f"{fmt_int(st.get('frames_total') or 0)} khung · {fmt_int(st.get('lidar_scans') or 0)} vòng LiDAR · "
                      f"{fmt_dec(st.get('mb_written') or 0, 0)} MB", theme.OK))
    elif state == "error":
        dropped = st.get("dropped_total")
        lines.append((f"LỖI GHI: {st.get('error')}" + (f" · {fmt_int(dropped)} khung bị bỏ" if dropped else ""),
                      theme.DANGER))
    # Bộ ghi đếm chung khung bỏ vì hàng đợi đầy và khung bỏ sau lỗi ghi: có lỗi ghi thì không đổ cho hàng đợi (sửa
    # 02/10/2026 sau review gộp đợt 2; như ui.rig_app), số khung bị bỏ nằm ở dòng LỖI GHI.
    if state != "idle" and st.get("dropped_total") and not st.get("error"):
        lines.append((f"GHI THIẾU: hàng đợi ghi đầy (đĩa chậm?), {fmt_int(st['dropped_total'])} khung bị bỏ", theme.WARN))
    if state not in ("idle", "error") and st.get("stopped_by") not in (None, "user", "window_closed"):
        lines.append((f"Đã tự dừng: {st['stopped_by']}", theme.WARN))
    if st.get("replay"):
        lines.append(("GHI LẠI TỪ BẢN GHI PHÁT LẠI", theme.WARN))
    if st.get("synthetic"):
        lines.append(("RIG TỔNG HỢP", theme.WARN))
    if st.get("outside_runs"):
        lines.append((NOT_IGNORED, theme.WARN))
    if st.get("hook_errors"):
        lines.append((f"{st['hook_errors']} lỗi của móc ghi (xem nhật ký): xe, AI và LiDAR vẫn chạy", theme.WARN))
    return lines


def open_in_explorer(path: Path) -> bool:
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class SensorRecordDock(QDockWidget):
    def __init__(self, window, recorder: SessionSensorRecorder, parent=None):
        super().__init__("Ghi cảm biến", parent or window)
        self.window = window
        self.recorder = recorder
        self.setObjectName("sensorRecordDock")
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.open_folder = open_in_explorer          # test thay bằng hàm giả: không mở Explorer
        options = recorder.options

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        card = Card("Bản ghi cảm biến (T3)")
        hint = WrapLabel(HINT)
        hint.setObjectName("hint")
        self.edit_root = QLineEdit(str(options.root))
        self.edit_root.setToolTip("Mặc định runs/session_recordings (git bỏ qua). Mỗi lần ghi một thư mục "
                                  "<ngày_giờ>_<tên> bên trong")
        self.edit_root.textChanged.connect(lambda _text: self.refresh())
        self.btn_root = QPushButton("Chọn…")
        self.btn_root.clicked.connect(self._choose_root)
        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("ví dụ do1_l3 (tùy chọn)")
        self.edit_name.setToolTip("Mã lần chạy (KICH_BAN_NGHIEM_THU mục 2.4): thành phần cuối của tên thư mục")
        self.combo_format = QComboBox()
        quality = options.jpeg_quality
        self.combo_format.addItem(f"JPEG chất lượng {quality}" + (" (mặc định)" if quality == 95 else ""), "jpg")
        self.combo_format.addItem("PNG không mất mát (chỉ đoạn ngắn)", "png")
        self.combo_format.setCurrentIndex(max(0, self.combo_format.findData(options.image_format)))
        self.combo_format.setToolTip("PNG lớn hơn JPEG ≈ 4,5 lần và tốn ≈ một lõi CPU: chỉ cho đoạn ngắn")
        self.chk_cameras = QCheckBox("Camera của ngăn AI camera")
        self.chk_cameras.setChecked(True)
        self.chk_lidar = QCheckBox("LiDAR của ngăn LiDAR")
        self.chk_lidar.setChecked(True)
        self.chk_ai = QCheckBox("Kết quả AI theo lô")
        self.chk_ai.setChecked(bool(options.ai_rows))
        self.chk_ai.setToolTip("Mỗi lô AI mà ngăn AI camera xét: khung đã dùng, dùng được hay bị chặn, số hộp AI "
                               "(session/ai_batches.csv). Không ghi bản đồ xác suất")
        for chk in (self.chk_cameras, self.chk_lidar):
            chk.toggled.connect(lambda _on: self.refresh())
        self.btn_record = QPushButton("Bắt đầu ghi")
        self.btn_record.clicked.connect(self.toggle)
        self.btn_open = QPushButton("Mở thư mục")
        self.btn_open.setToolTip("Mở thư mục bản ghi gần nhất (hay thư mục gốc) trong Explorer")
        self.btn_open.clicked.connect(self.open_last_folder)
        self.lbl_root_warning = WrapLabel("")
        self.lbl_root_warning.setStyleSheet(f"color: {theme.WARN};")
        card.add(hint)
        card.add_layout(theme.row(QLabel("Thư mục gốc"), self.edit_root, self.btn_root))
        card.add(self.lbl_root_warning)
        card.add_layout(theme.row(QLabel("Tên"), self.edit_name))
        card.add_layout(theme.row(QLabel("Ảnh"), self.combo_format))
        card.add(self.chk_cameras, self.chk_lidar, self.chk_ai)
        card.add_layout(theme.row(self.btn_record, self.btn_open))
        layout.addWidget(card)

        card = Card("Trạng thái")
        self.lbl_status = WrapLabel("Chưa ghi.")
        self.lbl_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card.add(self.lbl_status)
        layout.addWidget(card)

        self.log = QListWidget()
        self.log.setMaximumHeight(150)
        layout.addWidget(self.log)
        layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        self.setWidget(scroll)

        self.badge = QLabel("● ĐANG GHI")
        self.badge.setObjectName("recordBadge")
        self.badge.setToolTip("Bản ghi cảm biến đang ghi (ngăn Ghi cảm biến)")
        self.badge.setStyleSheet(f"color: {theme.DANGER}; font-weight: 700; padding: 0 6px;")
        self.badge.setVisible(False)
        self._install_badge()

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.poll_once)
        self.timer.start()
        self.refresh()

    # ---------------------------------------------------------------- helpers
    def say(self, text: str) -> None:
        self.log.addItem(text)
        if self.log.count() > LOG_MAX:
            self.log.takeItem(0)
        self.log.scrollToBottom()

    def _install_badge(self) -> None:
        """Huy hiệu vào thanh trên của cửa sổ, ngay trước nút "Dấu đồng bộ · F8"."""
        header = getattr(self.window, "header", None)
        row = header.layout() if header is not None else None
        if row is None:
            return
        index = row.indexOf(getattr(self.window, "sync_action", None))
        row.insertWidget(index if index >= 0 else row.count(), self.badge)

    def _driving(self) -> bool:
        return self.window.session.state.value in DRIVING_STATES

    def _choose_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Thư mục gốc của bản ghi cảm biến", self.edit_root.text())
        if path:
            self.edit_root.setText(path)

    def _plan(self, avail) -> str:
        parts = []
        if avail.cameras and self.chk_cameras.isChecked():
            parts.append("camera " + " ".join(str(p) for p in avail.camera_ports))
        if avail.lidar and self.chk_lidar.isChecked():
            parts.append("LiDAR " + (avail.lidar_label or ""))
        return " · ".join(parts)

    # ---------------------------------------------------------------- làm mới
    def refresh(self) -> None:
        rec = self.recorder
        active, draining = rec.active, rec.draining
        avail = rec.availability()
        for chk, key in ((self.chk_cameras, "cameras"), (self.chk_lidar, "lidar")):
            ok = bool(getattr(avail, key))
            chk.setEnabled(ok and not active)
            chk.setToolTip("" if ok else avail.reasons.get(key, ""))
        self.chk_ai.setEnabled(avail.cameras and self.chk_cameras.isChecked() and not active)
        for widget in (self.edit_root, self.btn_root, self.edit_name, self.combo_format):
            widget.setEnabled(not active)                   # cài đặt khóa khi đang ghi
        if active:
            self.btn_record.setText("Dừng ghi")
            self.btn_record.setEnabled(True)               # luôn dừng được, không chặn
            self.btn_record.setToolTip("Dừng nhận ngay; bản ghi ghi nốt hàng đợi rồi báo XONG")
        else:
            self.btn_record.setText("Bắt đầu ghi")
            selected = (avail.cameras and self.chk_cameras.isChecked()) or (avail.lidar and self.chk_lidar.isChecked())
            if self._driving():
                why = LOCKED_WHILE_DRIVING
            elif draining:
                why = "Bản ghi trước còn đang ghi nốt: chờ XONG"
            elif not avail.any:
                why = NO_SOURCE
            elif not selected:
                why = "Chọn ít nhất một nguồn có sẵn"
            else:
                why = ""
            self.btn_record.setEnabled(not why)
            self.btn_record.setToolTip(why)
        self.badge.setVisible(active)
        root_text = self.edit_root.text().strip()
        self.lbl_root_warning.setText(NOT_IGNORED if root_text and outside_ignored_runs(Path(root_text)) else "")
        status = rec.status()
        status["outside_runs"] = False                     # cảnh báo thư mục gốc đã ở dòng riêng dưới ô
        lines = status_lines(status, self._plan(avail))
        self.lbl_status.setText("<br>".join(_line(text, tone, bold=tone is not None) for text, tone in lines))

    # ---------------------------------------------------------------- bật / tắt
    def toggle(self) -> None:
        if self.recorder.active:
            self.stop_recording("user")
        else:
            self.start_recording()

    def start_recording(self) -> bool:
        """Bắt đầu ghi với các ô của ngăn; lý do từ chối hiện ở nhật ký và thanh trạng thái. Trả True khi đã ghi."""
        try:
            options = replace(self.recorder.options, root=Path(self.edit_root.text().strip() or DEFAULT_ROOT),
                              image_format=self.combo_format.currentData()).check()
        except ValueError as exc:
            self._report(f"Không bắt đầu ghi: {exc}")
            return False
        self.recorder.options = options
        try:
            rec = self.recorder.start(self.edit_name.text(), cameras=self.chk_cameras.isChecked(),
                                      lidar=self.chk_lidar.isChecked(), ai_rows=self.chk_ai.isChecked())
        except RecordStartError as exc:
            self._report(str(exc))
            return False
        self.say(f"Bắt đầu ghi: {rec.folder}")
        self.refresh()
        return True

    def stop_recording(self, reason: str = "user") -> None:
        """Không chặn: ngừng nhận ngay, luồng ghi ghi nốt (dòng trạng thái "ĐANG GHI NỐT")."""
        status = self.recorder.stop(reason)
        if status is not None:
            self.say(f"Dừng ghi ({reason}): còn {status['pending_frames']} khung chờ ghi")
        self.refresh()

    def open_last_folder(self) -> None:
        rec = self.recorder.rec
        path = rec.folder if rec is not None and rec.folder.exists() else Path(self.edit_root.text().strip() or DEFAULT_ROOT)
        if not path.exists():
            self.say(f"Chưa có thư mục {path}")
            return
        self.open_folder(path)

    def _report(self, text: str) -> None:
        self.say(text)
        self.window.statusBar().showMessage(text, 10000)
        self.refresh()

    # ---------------------------------------------------------------- nhịp 1 s
    def poll_once(self) -> None:
        try:
            messages = self.recorder.poll()
        except Exception as exc:  # noqa: BLE001 - poll() không ném; đây là chốt chặn cuối của timer
            messages = [f"Lỗi kiểm bản ghi cảm biến: {type(exc).__name__}: {exc}"]
        for text in messages:
            self.say(text)
        if messages:
            self.window.statusBar().showMessage("Ghi cảm biến: " + messages[-1], 8000)
        try:
            self.refresh()
        except Exception as exc:  # noqa: BLE001
            self.say(f"Lỗi làm mới ngăn Ghi cảm biến: {type(exc).__name__}: {exc}")

    def shutdown(self) -> None:
        """Đóng cửa sổ: dừng timer, dừng ghi (không chờ; cửa sổ chờ luồng ghi sau khi dừng xe và đóng các ngăn khác)."""
        self.timer.stop()
        if self.recorder.active:
            self.recorder.stop("window_closed")
        self.badge.setVisible(False)
