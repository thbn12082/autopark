"""Giao diện bàn thử: bốn camera có lớp tô AI, LiDAR, số đo trực tiếp.

    .\\.venv-train\\Scripts\\python.exe -X utf8 -m autopark.ui.rig_app --lidar COM4

- Bốn ô camera, gọi theo CỔNG HUB (index OpenCV đổi sau khởi động lại). Lớp tô: xanh = mô hình gọi là FREE, đỏ =
  BLOCKED, theo ngưỡng xác suất đang chọn. Khi bật AI, ảnh hiển thị là đúng bộ ảnh mà AI đã chấm (trễ hơn ảnh sống một
  lần suy luận) để lớp tô khớp từng pixel với ảnh; nếu AI không có kết quả mới quá 0,5 s (lỗi, đang nạp mô hình) thì
  ô quay về ảnh sống không tô và báo đỏ lý do.
- Chọn mô hình (mọi `runs/*/best.pt`, lượt nền WoodScape đứng đầu), kéo ngưỡng (0,50 là argmax, 0,15 là ngưỡng an toàn
  chọn trên val — HUAN_LUYEN.md mục 10), bật/tắt AI, bật/tắt lớp tô, đặt lại số đo.
- "Chụp bộ ảnh" lưu ảnh gốc cả bốn camera, xác suất, ảnh tô, vòng LiDAR và siêu dữ liệu (nguồn: bộ AI đồng bộ hay khung
  mới nhất không đồng bộ, tuổi từng khung lúc chụp, độ lệch) vào `runs/rig_snapshots/` — để thu ảnh sa bàn gán nhãn.
  Ảnh ghi qua `cv2.imencode` (imwrite của OpenCV không ghi được vào đường dẫn tiếng Việt trên Windows).
- Bảng số đo: số trực tiếp trên cửa sổ mẫu gần nhất (ghi rõ trên bảng). Số đo có hồ sơ thì dùng
  `python -m autopark.rig.bench` (không có giao diện tranh CPU).

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
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
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
        self.alert = False
        self.setMinimumSize(320, 180)

    def set_image(self, image: QImage | None, detail: str, alert: bool) -> None:
        if image is not None:
            self.pixmap = QPixmap.fromImage(image)
        self.detail, self.alert = detail, alert
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#101821"))
        if self.pixmap is not None:
            scaled = self.pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            x, y = (self.width() - scaled.width()) // 2, (self.height() - scaled.height()) // 2
            p.drawPixmap(x, y, scaled)
        font = QFont("Segoe UI")
        font.setPixelSize(13)
        font.setBold(True)
        p.setFont(font)
        band = QRectF(0, 0, self.width(), 22)
        p.fillRect(band, QColor(0, 0, 0, 150))
        p.setPen(QColor("#ff6b6b") if self.alert else QColor("#e8eef3"))
        p.drawText(band.adjusted(8, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   f"{self.caption}   {self.detail}")


class RigWindow(QMainWindow):
    def __init__(self, rig, checkpoints: list[Path] | None = None, snapshot_dir: Path = Path("runs/rig_snapshots"),
                 start: bool = True):
        super().__init__()
        self.rig, self.clock, self.snapshot_dir = rig, rig.clock, snapshot_dir
        self.setWindowTitle("Bàn thử — bốn camera, LiDAR, AI")
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

    def _force_redraw(self) -> None:
        self._last_shown.clear()

    # ---- vẽ -----------------------------------------------------------------------------------------------------
    def _current(self):
        """(khung theo cổng, xác suất theo cổng, kết quả AI hoặc None, ghi chú AI hoặc None)."""
        ai = self.rig.ai
        if ai is not None and ai.enabled.is_set():
            result = ai.result()
            age = None if result is None else self.clock() - result.t_done
            if result is not None and age <= AI_STALE_S:
                return result.frame_set.frames, result.probs, result, None
            if ai.segmenter is None or ai.requested != ai.checkpoint:
                note = "AI đang nạp mô hình"
            else:
                note = "AI chưa có kết quả" if result is None else f"AI ĐỨNG {age:.1f} s"
            if ai.load_error:
                note += f": {ai.load_error[:50]}"
            elif ai.errors and ai.last_error:
                note += f": {ai.last_error[:50]}"
            return self.rig.cams.latest_frames(), {}, None, note
        return self.rig.cams.latest_frames(), {}, None, None

    def tick(self) -> None:
        frames, probs, result, ai_note = self._current()
        now = self.clock()
        cam_stats = {c["port"]: c for c in self.rig.cams.camera_stats()}
        width = getattr(self.rig.cfg, "display_width", 640)
        for port, tile in self.tiles.items():
            c = cam_stats.get(port, {})
            frame = frames.get(port)
            if c.get("open_error"):
                tile.set_image(None, f"KHÔNG MỞ ĐƯỢC: {c['open_error']}", True)
                continue
            if frame is None:
                tile.set_image(None, "chưa có khung", True)
                continue
            prob = probs.get(port)
            blocked = f" · BLOCKED {float((prob >= self.threshold).mean()):.0%}" if prob is not None else ""
            detail = (f"{c.get('fps_last2s', 0):.1f} fps · cũ {c.get('duplicates', 0)} · cắt {c.get('truncated', 0) + c.get('torn', 0)} · "
                      f"tuổi {1000 * (now - frame.meta.stamp.t):.0f} ms{blocked}")
            if ai_note:
                detail += f" · {ai_note}"
            alert = bool(c.get("stale")) or ai_note is not None
            key = (frame.meta.stamp.t, None if result is None else result.t_done)   # id() có thể bị dùng lại
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
        self.metrics.setText(format_metrics(self.rig.snapshot(), self.threshold, self.message, self.last_snapshot))

    # ---- chụp ---------------------------------------------------------------------------------------------------
    def snapshot(self) -> Path | None:
        frames, probs, result, ai_note = self._current()
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
                "source": "ai_set" if result is not None else "latest_frames_unsynced",
                "stamp_skew_ms": round(1000 * (max(stamps) - min(stamps)), 2),
                "model": None if result is None else result.model,
                "checkpoint": None if result is None else result.checkpoint,
                "ai_note": ai_note, "camera_mode": self.rig.cams.mode, "cameras": {}, "failed_writes": []}
        if result is not None:
            meta["missing_ports"] = result.frame_set.missing
            meta["result_t_done_s"] = result.t_done
            meta["set_skew_ms"] = round(1000 * result.frame_set.skew_s, 2)
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
            f"đã chụp {folder.name}" + ("" if result is not None else " (không đồng bộ, AI tắt/đứng)")
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
    cams = snap["cameras"]
    lines.append("CAMERA")
    for c in cams["cameras"]:
        state = f"LỖI MỞ: {c['open_error']}" if c["open_error"] else (
            f"{f(c['fps_last2s'])} fps  cũ {c['duplicates']}  cắt {c['truncated']}  xé {c['torn']}  hỏng {c['read_failures']}  tuổi {f(c['age_ms'], 0)} ms"
            + ("  CŨ!" if c["stale"] else ""))
        lines.append(f"  cổng {c['port']} (idx {c['index']}): {state}")
    sk = cams["skew_ms"]
    lines.append(f"  bộ ảnh: dùng {cams['sets_built']}  bỏ vì lệch {cams['sets_rejected_skew']}  thiếu cam {cams['sets_partial']}"
                 f"  chặn (chưa đủ khung mới) {cams['sets_blocked_not_new']}")
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
        lines.append(f"  {f(a['sets_per_s_last3s'])} bộ/s  kết quả cách đây {f(a['last_result_age_ms'], 0)} ms  lô đầu {f(a['first_batch_ms'], 0)} ms")
        lines.append(f"  một lô ({a['window']}): trung vị {f(a['total_ms']['median'])}  p95 {f(a['total_ms']['p95'])} ms")
        lines.append(f"    tiền xử lý {f(a['pre_ms']['median'])}  mạng {f(a['model_ms']['median'])}  hậu {f(a['post_ms']['median'])} ms")
        lines.append(f"  tuổi kết quả (khung cũ nhất): {f(a['result_age_oldest_frame_ms']['median'])} ms  p95 {f(a['result_age_oldest_frame_ms']['p95'])}")
    r = snap.get("resources") or {}
    lines.append("TÀI NGUYÊN")
    lines.append(f"  CPU tiến trình {f(r.get('proc_cpu_cores'), 2)} lõi  CPU máy {f(r.get('sys_cpu_pct'))} %  RAM {f(r.get('proc_rss_mb'), 0)} MB")
    lines.append(f"  GPU {f(r.get('gpu_util_pct'), 0)} %  VRAM {f(r.get('gpu_mem_used_mb'), 0)} MB  {f(r.get('gpu_temp_c'), 0)} °C  {f(r.get('gpu_power_w'))} W")
    if message:
        lines.append("")
        lines.append(message)
    if last_snapshot is not None:
        lines.append(f"ảnh chụp: {last_snapshot}")
    return "\n".join(lines)


def main(argv=None) -> int:
    from autopark.rig.bench import add_rig_args, build_rig

    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    add_rig_args(p)
    p.add_argument("--snapshots", type=Path, default=Path("runs/rig_snapshots"))
    args = p.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv)
    rig = build_rig(args)
    checkpoints = []
    if not args.no_ai:
        from autopark.perception.live import list_checkpoints
        checkpoints = list_checkpoints(args.runs)
    window = RigWindow(rig, checkpoints, args.snapshots)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
