"""Giao diện bàn thử: bốn camera có lớp tô AI, LiDAR, số đo trực tiếp.

    .\\.venv-train\\Scripts\\python.exe -X utf8 -m autopark.ui.rig_app --lidar

`--lidar` không kèm giá trị: cổng lấy từ `lidar_port` của configs/thiet_bi.json (29/09/2026); `--lidar COMx` ghi đè.

- Bốn ô camera, gọi theo CỔNG HUB (index OpenCV đổi sau khởi động lại). Lớp tô: xanh = mô hình gọi là FREE, đỏ =
  BLOCKED, theo ngưỡng xác suất đang chọn. Khi bật AI, ảnh hiển thị là đúng bộ ảnh mà AI đã chấm (trễ hơn ảnh sống một
  lần suy luận) để lớp tô khớp từng pixel với ảnh; nếu AI không có kết quả mới quá 0,5 s (lỗi, đang nạp mô hình) thì
  ô quay về ảnh sống không tô và báo đỏ lý do.
- Camera chậm (lỡ nhịp của chính nó nên bị bỏ khỏi bộ AI vừa chấm sau khi chờ — ngưỡng riêng = max(`--max-wait-ms`,
  1,5 × chu kỳ khung của CHÍNH camera đó), xem `video.multicam`): ô vẫn hiện khung và lớp tô của lô GẦN NHẤT có
  camera đó (cùng mô hình), báo đỏ "chậm" kèm số lô và tuổi kết quả; kết quả đó cũ hơn 0,5 s hoặc chưa có thì hiện
  ảnh sống không tô và nói rõ.
  Camera được để dành cho bộ sau vì lệch pha (không chậm) cũng hiện lớp tô của lô gần nhất, ghi "lệch pha", không báo
  đỏ. Ghi chú này đứng ĐẦU dải chữ của ô; dải quá dài thì phần số đo phía sau bị rút gọn bằng "…". Đo ngày 24/09 bằng
  cửa sổ ẩn và QFontMetrics (Segoe UI 13 px đậm), chưa nhìn trên màn hình thật: ở cửa sổ mặc định 1600×900 ô rộng 557 px
  (541 px cho chữ), còn dải chữ kiểu cũ (ghi chú ở cuối) dài 613 px, nên phần cuối — tuổi kết quả — bị cắt mất im lặng.
- Chọn mô hình (mọi `runs/*/best.pt`, lượt nền WoodScape đứng đầu), kéo ngưỡng (0,50 là argmax, 0,15 là ngưỡng an toàn
  chọn trên val — HUAN_LUYEN.md mục 10), bật/tắt AI, bật/tắt lớp tô, đặt lại số đo.
- "Chụp bộ ảnh" lưu ảnh gốc cả bốn camera, xác suất, ảnh tô, vòng LiDAR và siêu dữ liệu (nguồn: bộ AI đồng bộ hay khung
  mới nhất không đồng bộ, tuổi từng khung lúc chụp, độ lệch) vào `runs/rig_snapshots/` — để thu ảnh sa bàn gán nhãn.
  `source: "ai_set"` chỉ nói lần chụp theo kết quả AI hiện hành; nguồn của TỪNG ảnh ở `cameras[<cổng>].frame_from`:
  "this_set" (khung của bộ AI này), "earlier_batch" (camera ngoài bộ: khung đã chấm ở lô trước, cũ hơn) hay
  "live_unsynced" (khung sống, không thuộc bộ AI nào, cũ hơn hay MỚI hơn bộ; các cổng này ở `unsynced_ports`).
  Ảnh ghi qua `cv2.imencode` (imwrite của OpenCV không ghi được vào đường dẫn tiếng Việt trên Windows).
- Bảng số đo: số trực tiếp trên cửa sổ mẫu gần nhất (ghi rõ trên bảng). Số đo có hồ sơ thì dùng
  `python -m autopark.rig.bench` (không có giao diện tranh CPU).
- "Ghi phiên" (từ 24/09): bật/tắt việc ghi mọi khung tốt, sự kiện khung hỏng và vòng LiDAR vào
  `--record-root`/<giờ>/ (docs/GHI_PHAT_LAI_BAN_THU.md). Tắt thì ngừng nhận ngay, phần còn trong hàng đợi được ghi nốt
  ở nền; bảng số đo ghi trạng thái, số khung bị bỏ và LỖI GHI (đĩa đầy…) bằng chữ, không âm thầm. Trong lúc ghi nốt
  nút bị làm mờ (một bản ghi chưa xong tại một thời điểm); đóng cửa sổ thì chờ ghi nốt xong.
- `--replay <thư mục>`: chạy cả giao diện từ một phiên đã ghi, không mở thiết bị nào; tiêu đề và bảng số đo ghi "PHÁT LẠI",
  hết bản ghi thì mọi ô ghi "HẾT BẢN GHI" (báo đỏ) và camera thành "cũ" sau 0,5 s. Ảnh là JPEG mã hóa lại của khung
  tốt lúc ghi: chụp bộ ảnh từ phát lại ghi `replay` trong meta để không lẫn với ảnh camera thật.

Mô hình chưa từng được chấm trên ảnh sa bàn: lớp tô là để NHÌN mô hình làm gì, không phải bằng chứng.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

import cv2
import numpy as np

try:                                   # torch trước Qt: tránh xung đột DLL trên Windows
    import torch  # noqa: F401
except Exception:  # noqa: BLE001
    pass

from PySide6.QtCore import QRectF, QSignalBlocker, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
                               QPushButton, QSlider, QVBoxLayout, QWidget)

from autopark.ui.scan_view import ScanView
from autopark.video.multicam import clock_info, fit_width
from autopark.video.sources import bottom_repeat_share

FREE_BGR = (60, 190, 60)
BLOCKED_BGR = (50, 50, 230)
PALETTE = np.array([FREE_BGR, BLOCKED_BGR], np.uint8)
LIDAR_STALE_S = 0.3
AI_STALE_S = 0.5


def overlay(image_bgr: np.ndarray, prob: np.ndarray | None, threshold: float, alpha: float) -> np.ndarray:
    """Tô FREE xanh / BLOCKED đỏ lên ảnh (cùng kích thước với `prob`)."""
    if prob is None or alpha <= 0:
        return image_bgr
    if prob.shape[:2] != image_bgr.shape[:2]:
        prob = cv2.resize(prob, (image_bgr.shape[1], image_bgr.shape[0]), interpolation=cv2.INTER_LINEAR)
    colors = PALETTE[(prob >= threshold).astype(np.uint8)]
    return cv2.addWeighted(image_bgr, 1.0 - alpha, colors, alpha, 0.0)


def to_qimage(image_bgr: np.ndarray) -> QImage:
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


def write_image(path: Path, image) -> bool:
    """Ghi ảnh chịu được đường dẫn Unicode (cv2.imwrite trả False trên đường dẫn tiếng Việt ở Windows)."""
    ok, buf = cv2.imencode(path.suffix, image)
    if not ok:
        return False
    try:
        path.write_bytes(buf.tobytes())
    except OSError:
        return False
    return True


class CameraTile(QWidget):
    def __init__(self, port: int, parent=None):
        super().__init__(parent)
        self.port = port
        self.pixmap: QPixmap | None = None
        self.caption = f"cổng {port}"
        self.detail = "đang mở…"
        self.shown_text = ""
        self.alert = False
        self.setMinimumSize(320, 180)

    def set_image(self, image: QImage | None, detail: str, alert: bool) -> None:
        if image is not None:
            self.pixmap = QPixmap.fromImage(image)
        self.detail, self.alert = detail, alert
        self.update()

    @staticmethod
    def band_font() -> QFont:
        font = QFont("Segoe UI")
        font.setPixelSize(13)
        font.setBold(True)
        return font

    def band_text(self, metrics: QFontMetrics, width: int) -> str:
        """Chữ trên dải đầu ô, rút gọn bằng "…" ở CUỐI khi quá rộng (ghi chú quan trọng — chậm, lệch pha, AI đứng — đặt ở
        đầu `detail` nên không bị mất; drawText tự cắt thì cắt im lặng, không ai biết thiếu chữ)."""
        return metrics.elidedText(f"{self.caption}   {self.detail}", Qt.TextElideMode.ElideRight, max(0, int(width)))

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#101821"))
        if self.pixmap is not None:
            scaled = self.pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            x, y = (self.width() - scaled.width()) // 2, (self.height() - scaled.height()) // 2
            p.drawPixmap(x, y, scaled)
        p.setFont(self.band_font())
        band = QRectF(0, 0, self.width(), 22)
        p.fillRect(band, QColor(0, 0, 0, 150))
        p.setPen(QColor("#ff6b6b") if self.alert else QColor("#e8eef3"))
        rect = band.adjusted(8, 0, -8, 0)
        self.shown_text = self.band_text(p.fontMetrics(), rect.width())     # giữ lại để test biết đã vẽ chữ gì
        p.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.shown_text)


class RigWindow(QMainWindow):
    def __init__(self, rig, checkpoints: list[Path] | None = None, snapshot_dir: Path = Path("runs/rig_snapshots"),
                 start: bool = True, record_root: Path = Path("runs/rig_recordings"), record_options: dict | None = None):
        super().__init__()
        self.rig, self.clock, self.snapshot_dir = rig, rig.clock, snapshot_dir
        self.record_root, self.record_options = Path(record_root), dict(record_options or {})
        replay = getattr(rig, "replay", None)
        self.setWindowTitle("Bàn thử — bốn camera, LiDAR, AI" if replay is None else
                            f"Bàn thử — PHÁT LẠI {replay.folder.name} ×{replay.speed:g} (không mở thiết bị)")
        self.threshold = 0.5
        self.alpha = 0.45
        self.show_overlay = True
        self._last_shown: dict[int, tuple] = {}
        self._last_scan_key = None
        self.last_snapshot: Path | None = None
        self.message = ""

        ports = [s.port for s in rig.cams.specs]
        self.tiles = {port: CameraTile(port) for port in ports}
        grid = QGridLayout()
        for k, port in enumerate(ports):
            grid.addWidget(self.tiles[port], k // 2, k % 2)
        cams_box = QWidget()
        cams_box.setLayout(grid)

        self.scan_view = ScanView(max_range=4.0)
        self.metrics = QLabel()
        self.metrics.setTextFormat(Qt.TextFormat.PlainText)
        mono = QFont("Consolas")
        mono.setPixelSize(12)
        self.metrics.setFont(mono)
        self.metrics.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.metrics.setMinimumWidth(420)

        self.model_box = QComboBox()
        for path in list(checkpoints or []):
            self.model_box.addItem(path.parent.name, str(path))
        if rig.ai is not None and rig.ai.requested:
            idx = self.model_box.findData(str(rig.ai.requested))
            if idx < 0:
                self.model_box.addItem(Path(rig.ai.requested).parent.name, str(rig.ai.requested))
                idx = self.model_box.count() - 1
            self.model_box.setCurrentIndex(idx)
        self.model_box.currentIndexChanged.connect(self.on_model)
        self.model_box.setEnabled(rig.ai is not None)

        self.thr_slider = QSlider(Qt.Orientation.Horizontal)
        self.thr_slider.setRange(1, 19)          # × 0,05
        self.thr_slider.setValue(10)
        self.thr_slider.valueChanged.connect(self.on_threshold)
        self.thr_label = QLabel()
        self.btn_safe = QPushButton("0,15 (an toàn)")
        self.btn_safe.clicked.connect(lambda: self.thr_slider.setValue(3))
        self.btn_argmax = QPushButton("0,50")
        self.btn_argmax.clicked.connect(lambda: self.thr_slider.setValue(10))
        self.alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.alpha_slider.setRange(0, 90)
        self.alpha_slider.setValue(int(self.alpha * 100))
        self.alpha_slider.valueChanged.connect(lambda v: setattr(self, "alpha", v / 100.0) or self._force_redraw())
        self.chk_ai = QCheckBox("Bật AI")
        self.chk_ai.setChecked(rig.ai is not None)
        self.chk_ai.setEnabled(rig.ai is not None)
        self.chk_ai.toggled.connect(self.on_ai)
        self.chk_overlay = QCheckBox("Tô màu")
        self.chk_overlay.setChecked(True)
        self.chk_overlay.toggled.connect(lambda v: setattr(self, "show_overlay", v) or self._force_redraw())
        self.btn_snap = QPushButton("Chụp bộ ảnh")
        self.btn_snap.clicked.connect(self.snapshot)
        self.btn_reset = QPushButton("Đặt lại số đo")
        self.btn_reset.clicked.connect(self.on_reset)
        self.btn_record = QPushButton("Ghi phiên")
        self.btn_record.setCheckable(True)
        self.btn_record.setEnabled(hasattr(rig, "start_recording"))
        self.btn_record.toggled.connect(self.on_record)
        self.on_threshold(self.thr_slider.value())

        controls = QVBoxLayout()
        controls.addWidget(QLabel("Mô hình"))
        controls.addWidget(self.model_box)
        row = QHBoxLayout()
        row.addWidget(self.thr_label)
        row.addWidget(self.btn_safe)
        row.addWidget(self.btn_argmax)
        controls.addLayout(row)
        controls.addWidget(self.thr_slider)
        controls.addWidget(QLabel("Độ đậm lớp tô"))
        controls.addWidget(self.alpha_slider)
        row2 = QHBoxLayout()
        row2.addWidget(self.chk_ai)
        row2.addWidget(self.chk_overlay)
        row2.addWidget(self.btn_snap)
        row2.addWidget(self.btn_reset)
        row2.addWidget(self.btn_record)
        controls.addLayout(row2)
        side = QVBoxLayout()
        side.addWidget(self.scan_view, 3)
        side.addLayout(controls)
        side.addWidget(self.metrics, 4)
        side_box = QWidget()
        side_box.setLayout(side)
        side_box.setMaximumWidth(540)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.addWidget(cams_box, 3)
        layout.addWidget(side_box, 1)
        self.setCentralWidget(root)
        self.resize(1600, 900)

        self.frame_timer = QTimer(self)
        self.frame_timer.setInterval(40)
        self.frame_timer.timeout.connect(self.tick)
        self.metrics_timer = QTimer(self)
        self.metrics_timer.setInterval(500)
        self.metrics_timer.timeout.connect(self.update_metrics)
        if start:
            self.rig.start()
        self.frame_timer.start()
        self.metrics_timer.start()

    # ---- điều khiển --------------------------------------------------------------------------------------------
    def on_threshold(self, value: int) -> None:
        self.threshold = round(value * 0.05, 2)
        self.thr_label.setText(f"Ngưỡng BLOCKED: {self.threshold:.2f}".replace(".", ","))
        self._force_redraw()

    def on_model(self, index: int) -> None:
        path = self.model_box.itemData(index)
        if self.rig.ai is not None and path:
            self.rig.ai.request_model(path)
            self.message = f"đang nạp {Path(path).parent.name}…"

    def on_ai(self, on: bool) -> None:
        if self.rig.ai is None:
            return
        if on:
            self.rig.ai.enabled.set()
        else:
            self.rig.ai.enabled.clear()
        self._force_redraw()

    def on_reset(self) -> None:
        self.rig.reset_counters()
        self.message = "đã đặt lại số đo"

    def on_record(self, on: bool) -> None:
        """Bật: ghi vào record_root/<giờ>. Tắt: ngừng nhận ngay, ghi nốt ở nền (không đứng hình giao diện)."""
        if on:
            folder = self.record_root / datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            try:
                self.rig.start_recording(folder, notes={"from": "ui.rig_app"}, **self.record_options)
            except Exception as exc:  # noqa: BLE001 - thư mục có sẵn dữ liệu, không tạo được thư mục, …: nói rõ
                self.message = f"LỖI: không bắt đầu ghi được: {type(exc).__name__}: {exc}"
                with QSignalBlocker(self.btn_record):
                    self.btn_record.setChecked(False)
                return
            self.btn_record.setText("Dừng ghi")
            self.message = f"đang ghi phiên vào {folder}"
        else:
            status = self.rig.stop_recording(wait=False)
            self.btn_record.setText("Ghi phiên")
            if status is not None:
                self.message = (f"dừng ghi {Path(status['folder']).name}: {status['frames_total']} khung đã ghi, "
                                f"{status['pending_frames']} khung đang ghi nốt")
        self.update_metrics()

    def _force_redraw(self) -> None:
        self._last_shown.clear()

    # ---- vẽ -----------------------------------------------------------------------------------------------------
    def _current(self):
        """(khung theo cổng, xác suất theo cổng, kết quả AI hoặc None, ghi chú AI hoặc None, camera ngoài bộ).

        "camera ngoài bộ": cổng không có trong bộ AI vừa chấm — chậm (`frame_set.lagging`) hoặc để dành cho bộ sau vì
        lệch pha (`frame_set.deferred`) → `CameraAI` của lô trước mà khung/xác suất đang hiện lấy từ đó, hoặc None nếu đang
        hiện ảnh sống không tô (chưa có kết quả, hoặc kết quả cũ hơn AI_STALE_S)."""
        ai = self.rig.ai
        if ai is not None and ai.enabled.is_set():
            result = ai.result()
            now = self.clock()
            age = None if result is None else now - result.t_done
            if result is not None and age <= AI_STALE_S:
                frames, probs, lagging = dict(result.frame_set.frames), dict(result.probs), {}
                live = None
                for port in (*result.frame_set.lagging, *result.frame_set.deferred):
                    held = result.carried.get(port)
                    if held is not None and now - held.t_done <= AI_STALE_S:
                        frames[port], probs[port], lagging[port] = held.frame, held.prob, held
                        continue
                    live = self.rig.cams.latest_frames() if live is None else live
                    if port in live:
                        frames[port], lagging[port] = live[port], None
                return frames, probs, result, None, lagging
            if ai.segmenter is None or ai.requested != ai.checkpoint:
                note = "AI đang nạp mô hình"
            else:
                note = "AI chưa có kết quả" if result is None else f"AI ĐỨNG {age:.1f} s"
            if ai.load_error:
                note += f": {ai.load_error[:50]}"
            elif ai.errors and ai.last_error:
                note += f": {ai.last_error[:50]}"
            return self.rig.cams.latest_frames(), {}, None, note, {}
        return self.rig.cams.latest_frames(), {}, None, None, {}

    def tick(self) -> None:
        frames, probs, result, ai_note, lagging = self._current()
        now = self.clock()
        cam_stats = {c["port"]: c for c in self.rig.cams.camera_stats()}
        width = getattr(self.rig.cfg, "display_width", 640)
        replay = getattr(self.rig, "replay", None)
        ended = replay is not None and replay.finished
        for port, tile in self.tiles.items():
            c = cam_stats.get(port, {})
            frame = frames.get(port)
            if c.get("open_error"):
                tile.set_image(None, f"KHÔNG MỞ ĐƯỢC: {c['open_error']}", True)
                continue
            if frame is None:
                waiting = replay is not None and not replay.begun
                tile.set_image(None, "phát lại chưa bắt đầu (chờ AI nạp mô hình)" if waiting else
                               ("HẾT BẢN GHI phát lại, camera này không có khung" if ended else "chưa có khung"), True)
                continue
            prob = probs.get(port)
            blocked = f" · BLOCKED {float((prob >= self.threshold).mean()):.0%}" if prob is not None else ""
            detail = (f"{c.get('fps_last2s', 0):.1f} fps · cũ {c.get('duplicates', 0)} · cắt {c.get('truncated', 0) + c.get('torn', 0)} · "
                      f"tuổi {1000 * (now - frame.meta.stamp.t):.0f} ms{blocked}")
            # ghi chú quan trọng đứng ĐẦU dải chữ (ô 557 px ở cửa sổ mặc định; phần số đo phía sau có thể bị rút gọn)
            if ai_note:
                detail = f"{ai_note} · {detail}"
            done_t = None if result is None else result.t_done
            slow = False
            if port in lagging:
                held = lagging[port]
                slow = port in result.frame_set.lagging              # deferred: lệch pha, camera không chậm
                head = "chậm" if slow else "lệch pha, chấm ở bộ sau"
                if held is None:
                    note = f"{head}: chưa có kết quả AI mới, ảnh sống không tô"
                else:
                    note = f"{head}: lớp tô của lô #{held.batch_id}, cách đây {1000 * (now - held.t_done):.0f} ms"
                    done_t = held.t_done
                detail = f"{note} · {detail}"
            if ended:                                                    # đứng đầu hết: ảnh đứng yên là vì bản ghi đã hết
                detail = f"HẾT BẢN GHI phát lại · {detail}"
            alert = bool(c.get("stale")) or ai_note is not None or slow or ended
            key = (frame.meta.stamp.t, done_t)   # id() có thể bị dùng lại
            if self._last_shown.get(port) == key:
                tile.set_image(None, detail, alert)
                continue
            self._last_shown[port] = key
            size = (prob.shape[1], prob.shape[0]) if prob is not None else \
                fit_width(frame.image.shape[1], frame.image.shape[0], width)
            small = cv2.resize(frame.image, size, interpolation=cv2.INTER_AREA)
            shown = overlay(small, prob, self.threshold, self.alpha) if self.show_overlay else small
            tile.set_image(to_qimage(shown), detail, alert)
        if self.rig.lidar is not None:
            latest, _ = self.rig.lidar.snapshot()
            if latest is not None:
                scan, t_abs = latest[0], latest[1]
                stale = (now - t_abs) > LIDAR_STALE_S
                key = (t_abs, stale)
                if key != self._last_scan_key:                 # vẽ lại chỉ khi có vòng mới (10 Hz) hoặc đổi trạng thái
                    self._last_scan_key = key
                    self.scan_view.set_scan(scan, stale=stale)

    def update_metrics(self) -> None:
        ai = self.rig.ai
        if ai is not None:
            with QSignalBlocker(self.model_box):
                if ai.load_error or ai.requested == ai.checkpoint:
                    idx = self.model_box.findData(str(ai.checkpoint)) if ai.checkpoint else -1
                    if idx >= 0 and idx != self.model_box.currentIndex():
                        self.model_box.setCurrentIndex(idx)
            if self.message.startswith("đang nạp") and ai.requested == ai.checkpoint and ai.segmenter is not None:
                self.message = f"đã nạp {Path(ai.checkpoint).parent.name}"
            if ai.load_error and self.message.startswith("đang nạp"):
                self.message = f"nạp lỗi, vẫn chạy {Path(str(ai.checkpoint)).parent.name if ai.checkpoint else '—'}"
        snap = self.rig.snapshot()
        rec = snap.get("recording")
        # bản ghi trước còn ghi nốt: Rig.start_recording sẽ từ chối, nên làm mờ nút tới khi nó xong
        last = getattr(self.rig, "last_recorder", None)
        draining = getattr(self.rig, "recorder", None) is None and last is not None and not last.finished.is_set()
        self.btn_record.setEnabled(hasattr(self.rig, "start_recording") and not draining)
        if rec is not None and self.message.startswith("dừng ghi") and rec["state"] in ("xong", "LỖI"):
            self.message = f"đã ghi xong {rec['folder']}: {rec['frames_total']} khung, bỏ {rec['dropped_total']}" \
                if rec["state"] == "xong" else f"GHI LỖI {rec['folder']}: {rec['error']}"
        self.metrics.setText(format_metrics(snap, self.threshold, self.message, self.last_snapshot))

    # ---- chụp ---------------------------------------------------------------------------------------------------
    def snapshot(self) -> Path | None:
        frames, probs, result, ai_note, lagging = self._current()
        # vòng LiDAR lấy cùng lúc với khung, TRƯỚC khi ghi ảnh (ghi PNG mất ~80 ms: lấy sau thì vòng mới hơn ảnh, tuổi âm)
        lidar_latest = self.rig.lidar.snapshot()[0] if self.rig.lidar is not None else None
        t_cap = self.clock()
        if not frames:
            self.message = "chưa có khung để chụp"
            return None
        folder = self.snapshot_dir / datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        folder.mkdir(parents=True, exist_ok=True)
        stamps = [f.meta.stamp.t for f in frames.values()]
        meta = {"created_local": datetime.now().isoformat(timespec="milliseconds"), "clock": clock_info(),
                "t_capture_s": t_cap, "threshold": self.threshold,
                # "ai_set": mỗi ảnh lấy theo kết quả AI hiện hành; nguồn của TỪNG ảnh ở cameras[<cổng>].frame_from
                "source": "ai_set" if result is not None else "latest_frames_unsynced",
                # trên MỌI ảnh được ghi, gồm cả cổng ngoài bộ (frame_from: khung của lô trước — cũ hơn — hoặc khung sống,
                # cũ hơn HAY MỚI hơn bộ); độ lệch của riêng bộ AI là set_skew_ms
                "stamp_skew_ms": round(1000 * (max(stamps) - min(stamps)), 2),
                "model": None if result is None else result.model,
                "checkpoint": None if result is None else result.checkpoint,
                "ai_note": ai_note, "camera_mode": self.rig.cams.mode, "cameras": {}, "failed_writes": []}
        replay = getattr(self.rig, "replay", None)
        if replay is not None:
            # ảnh là JPEG mã hóa lại của khung tốt lúc ghi, stamp theo đồng hồ phát lại: đừng lẫn với ảnh camera thật
            meta["replay"] = replay.describe()
        if result is not None:
            meta["missing_ports"] = result.frame_set.missing
            meta["lagging_ports"] = result.frame_set.lagging      # bị bỏ khỏi bộ này vì chậm (khác missing: vẫn có khung tươi)
            meta["deferred_ports"] = result.frame_set.deferred    # để dành cho bộ sau vì lệch pha (camera không chậm)
            meta["result_batch_id"] = result.batch_id
            meta["result_t_done_s"] = result.t_done
            meta["set_skew_ms"] = round(1000 * result.frame_set.skew_s, 2)
            # cổng ngoài bộ mà ảnh ghi là khung SỐNG, không thuộc bộ AI nào (kết quả mang sang cũ hơn AI_STALE_S hoặc chưa có)
            meta["unsynced_ports"] = sorted(p for p, h in lagging.items() if h is None)
        cam_stats = {c["port"]: c for c in self.rig.cams.camera_stats()}
        source_checks = {port: getattr(w.source, "check_truncation", None) for port, w in self.rig.cams.workers.items()}
        for port, frame in frames.items():
            age = t_cap - frame.meta.stamp.t
            entry = {"stamp_s": frame.meta.stamp.t, "age_ms": round(1000 * age, 1), "stale": age > self.rig.cams.stale_after_s,
                     "width": frame.meta.width, "height": frame.meta.height,
                     "index": next((s.index for s in self.rig.cams.specs if s.port == port), None),
                     # nguồn đã loại khung bị cắt/xé khi source_rejects_damaged; con số thô dưới đây KHÔNG phải phán
                     # quyết, để lọc lại ảnh gán nhãn bằng ngưỡng khác bộ dò (khung sạch ≤ 0,13, đáy bị tô ≈ 1)
                     "bottom_repeat_share": bottom_repeat_share(frame.image),
                     "source_rejects_damaged": source_checks.get(port),
                     "truncated_frames_so_far": cam_stats.get(port, {}).get("truncated"),
                     "torn_frames_so_far": cam_stats.get(port, {}).get("torn")}
            if not write_image(folder / f"cam_p{port}.png", frame.image):
                meta["failed_writes"].append(f"cam_p{port}.png")
            prob = probs.get(port)
            # xác suất của ô này lấy từ lô nào: đúng bộ AI này, một lô trước (camera chậm), hay không có
            if result is not None:
                held = lagging.get(port)
                entry["lagging"] = port in result.frame_set.lagging
                entry["deferred"] = port in result.frame_set.deferred
                # ảnh này lấy từ đâu: đúng khung của bộ AI này / khung đã chấm ở một lô trước / khung sống không đồng bộ
                entry["frame_from"] = ("this_set" if port not in lagging else
                                       "earlier_batch" if held is not None else "live_unsynced")
                entry["ai_prob_from"] = None if prob is None else ("earlier_batch" if held is not None else "this_set")
                if prob is not None:
                    src_id, src_t = (held.batch_id, held.t_done) if held is not None else (result.batch_id, result.t_done)
                    entry.update({"prob_batch_id": src_id, "prob_t_done_s": src_t,
                                  "prob_age_ms": round(1000 * (t_cap - src_t), 1)})
            else:
                entry["frame_from"] = "live_unsynced"
            if prob is not None:
                small = cv2.resize(frame.image, (prob.shape[1], prob.shape[0]), interpolation=cv2.INTER_AREA)
                for name, img in ((f"prob_blocked_p{port}.png", np.round(prob * 255).astype(np.uint8)),
                                  (f"overlay_p{port}.jpg", overlay(small, prob, self.threshold, 0.45))):
                    if not write_image(folder / name, img):
                        meta["failed_writes"].append(name)
                entry["prob_size"] = [int(prob.shape[1]), int(prob.shape[0])]
                entry["blocked_fraction_at_threshold"] = float((prob >= self.threshold).mean())
            meta["cameras"][str(port)] = entry
        if lidar_latest is not None:
            scan, t_abs = lidar_latest[0], lidar_latest[1]
            meta["lidar"] = {"stamp_s": t_abs, "age_ms": round(1000 * (t_cap - t_abs), 1),
                             "angles_rad": list(scan.angles_rad),
                             "ranges_m": [None if not np.isfinite(r) else r for r in scan.ranges_m]}
        (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        self.last_snapshot = folder
        failed = meta["failed_writes"]
        self.message = f"LỖI: {len(failed)} ảnh không ghi được vào {folder.name}" if failed else \
            f"đã chụp {folder.name}" + ("" if result is not None else " (không đồng bộ, AI tắt/đứng)") + \
            (f" (cổng {sorted(lagging)} không có trong bộ AI này; nguồn ảnh ghi trong meta)" if lagging else "")
        return folder

    def closeEvent(self, event):
        self.frame_timer.stop()
        self.metrics_timer.stop()
        try:
            alive = self.rig.stop()
            if alive:
                print(f"CẢNH BÁO: luồng chưa dừng sạch: {alive} (LiDAR: rút nguồn C1 hoặc mở lại để gửi STOP)",
                      file=sys.stderr)
        finally:
            super().closeEvent(event)


def format_metrics(snap: dict, threshold: float, message: str = "", last_snapshot: Path | None = None) -> str:
    f = lambda x, nd=1: "—" if x is None else f"{x:.{nd}f}".replace(".", ",")
    lines = [f"t = {f(snap['t_s'])} s   (phân vị trên cửa sổ mẫu gần nhất)"]
    rp = snap.get("replay")
    if rp is not None:
        state = "HẾT BẢN GHI" if rp["finished"] else ("chờ AI nạp mô hình" if not rp["begun"] else "đang phát")
        lines.append(f"PHÁT LẠI ×{f(rp['speed'], 2)}  {state}  {f(rp['position_s'])} / {f(rp['duration_s'])} s")
        lines.append(f"  {rp['folder']}")
    cams = snap["cameras"]
    lagging = cams.get("lagging_per_port", {})
    lines.append("CAMERA")
    for c in cams["cameras"]:
        state = f"LỖI MỞ: {c['open_error']}" if c["open_error"] else (
            f"{f(c['fps_last2s'])} fps  cũ {c['duplicates']}  cắt {c['truncated']}  xé {c['torn']}  hỏng {c['read_failures']}"
            f"  chậm {lagging.get(c['port'], 0)}  nhịp {f(c.get('period_ms'))} ms  tuổi {f(c['age_ms'], 0)} ms"
            + ("  CŨ!" if c["stale"] else ""))
        lines.append(f"  cổng {c['port']} (idx {c['index']}): {state}")
    sk = cams["skew_ms"]
    pol = snap.get("policy") or {}
    wait_ms, periods = pol.get("max_wait_ms"), pol.get("wait_periods_of_own")
    limit = (cams.get("wait_limit_ms") or {}).get("median")
    lines.append(f"  bộ ảnh: dùng {cams['sets_built']}  bỏ vì lệch {cams['sets_rejected_skew']}  thiếu cam {cams['sets_partial']}"
                 f"  chặn (chưa đủ khung mới) {cams['sets_blocked_not_new']}")
    wait_txt = "TẮT" if wait_ms is None else (f"tối đa max({f(wait_ms, 0)} ms; {f(periods)} × nhịp riêng từng cam), "
                                              f"lớn nhất trong bộ {f(limit, 0)} ms")
    lines.append(f"  chờ camera chậm {wait_txt}:  bộ thiếu cam chậm {cams.get('sets_partial_wait', 0)}"
                 f"  để dành lệch pha {cams.get('sets_regrouped', 0)}")
    lines.append(f"  độ lệch ({cams['skew_window']}): trung vị {f(sk['median'])}  p95 {f(sk['p95'])}  max {f(sk['max'])} ms")
    l = snap.get("lidar")
    lines.append("LIDAR")
    if l is None:
        lines.append("  tắt")
    elif l["open_error"]:
        lines.append(f"  LỖI MỞ: {l['open_error']}")
    else:
        lines.append(f"  {f(l['hz_last3s'])} Hz  vòng {l['scans']}  lỗi {l['errors']}  tuổi {f(l['age_ms'], 0)} ms  tia hợp lệ {l['beams_valid_last']}")
        vs = l.get("vs_set", {}).get("last_minus_anchor_ms", {})
        lines.append(f"  cuối vòng − mốc bộ ảnh: trung vị {f(vs.get('median'))}  [{f(vs.get('min'))}; {f(vs.get('max'))}] ms")
        if l["last_error"]:
            lines.append(f"  lỗi gần nhất: {l['last_error'][:60]}")
    a = snap.get("ai")
    lines.append("AI")
    if a is None:
        lines.append("  tắt (chạy lại không có --no-ai)")
    else:
        lines.append(f"  {a['model']}  {a['device']}  amp={a['amp']}  {'BẬT' if a['enabled'] else 'TẮT (bộ ảnh do luồng nền ghép)'}"
                     f"  ngưỡng {f(threshold, 2)}")
        if a["load_error"]:
            lines.append(f"  LỖI NẠP: {a['load_error'][:70]}")
        if a["errors"]:
            lines.append(f"  LỖI SUY LUẬN ×{a['errors']}: {(a['last_error'] or '')[:70]}")
        lines.append(f"  {f(a['sets_per_s_last3s'])} bộ/s  kết quả cách đây {f(a['last_result_age_ms'], 0)} ms  lô đầu {f(a['first_batch_ms'], 0)} ms"
                     f"  lô thiếu cam chậm {a.get('batches_partial_wait', 0)}")
        lines.append(f"  một lô ({a['window']}): trung vị {f(a['total_ms']['median'])}  p95 {f(a['total_ms']['p95'])} ms")
        lines.append(f"    tiền xử lý {f(a['pre_ms']['median'])}  mạng {f(a['model_ms']['median'])}  hậu {f(a['post_ms']['median'])} ms")
        lines.append(f"  tuổi kết quả (khung cũ nhất): {f(a['result_age_oldest_frame_ms']['median'])} ms  p95 {f(a['result_age_oldest_frame_ms']['p95'])}")
    r = snap.get("resources") or {}
    lines.append("TÀI NGUYÊN")
    lines.append(f"  CPU tiến trình {f(r.get('proc_cpu_cores'), 2)} lõi  CPU máy {f(r.get('sys_cpu_pct'))} %  RAM {f(r.get('proc_rss_mb'), 0)} MB")
    lines.append(f"  GPU {f(r.get('gpu_util_pct'), 0)} %  VRAM {f(r.get('gpu_mem_used_mb'), 0)} MB  {f(r.get('gpu_temp_c'), 0)} °C  {f(r.get('gpu_power_w'))} W")
    rec = snap.get("recording")
    if rec is not None:
        lines.append("GHI PHIÊN")
        lines.append(f"  {rec['state']}  {rec['frames_total']} khung {rec['image_format']}  bỏ {rec['dropped_total']}"
                     f"  LiDAR {'—' if rec['lidar_scans'] is None else rec['lidar_scans']} vòng  {f(rec['mb_written'], 0)} MB"
                     f" ({f(rec['mb_per_s'])} MB/s)  chờ ghi {rec['pending_frames']} khung")
        lines.append(f"  → {rec['folder']}")
        if rec["error"]:
            lines.append(f"  LỖI GHI: {rec['error'][:90]}")
        elif rec["dropped_total"]:
            lines.append("  GHI THIẾU: hàng đợi ghi đầy (đĩa chậm?), bản ghi không đủ mọi khung")
    if message:
        lines.append("")
        lines.append(message)
    if last_snapshot is not None:
        lines.append(f"ảnh chụp: {last_snapshot}")
    return "\n".join(lines)


def checkpoint_choices(runs) -> list[Path]:
    from autopark.perception.live import list_checkpoints
    return list_checkpoints(runs)


def build_window(argv=None, start: bool = True) -> RigWindow:
    """Dựng Rig (thiết bị thật, hay bản ghi với --replay) và cửa sổ từ dòng lệnh; cần QApplication đã có."""
    from autopark.rig.bench import add_rig_args, build_rig, check_record_args, recording_options

    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    add_rig_args(p)
    p.add_argument("--snapshots", type=Path, default=Path("runs/rig_snapshots"))
    p.add_argument("--record-root", type=Path, default=Path("runs/rig_recordings"),
                   help="nút 'Ghi phiên' ghi vào <thư mục này>/<giờ>/")
    args = p.parse_args(argv)
    check_record_args(p, args)          # --jpeg-quality sai báo ngay, không đợi tới lúc bấm "Ghi phiên"
    from autopark.lidar.port import LidarPortError

    try:
        rig = build_rig(args)
    except LidarPortError as exc:
        p.error(str(exc))
    checkpoints = [] if args.no_ai else checkpoint_choices(args.runs)
    return RigWindow(rig, checkpoints, args.snapshots, start=start, record_root=args.record_root,
                     record_options=recording_options(args))


def main(argv=None) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = build_window(argv)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
