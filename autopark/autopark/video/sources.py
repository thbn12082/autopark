"""Nguồn ảnh camera theo hợp đồng `CameraFrame`: thư mục ảnh, file video lưu sẵn và camera USB.

Cùng một giao diện `FrameSource` cho cả ba, để phần nhận thức và giám sát dữ liệu cũ chạy y hệt trên dữ liệu
phát lại và trên camera thật (giai đoạn 1). Quy ước `read()`: trả `Frame`; trả `None` CHỈ khi nguồn phát lại
đã hết; nguồn trực tiếp không bao giờ trả `None` mà ném `FrameReadError` khi một lần đọc hỏng, để vòng lặp
tiêu thụ không nhầm sự cố USB với hết dữ liệu. Thời gian của nguồn phát lại lấy từ file (một đồng hồ duy nhất
cho cả file) cộng `t0`; camera thật lấy đồng hồ phiên ngay sau khi `read()` trả về (đã gồm chờ khung kế và giải
mã, nên tuổi khung tính được nhỏ hơn tuổi thật một khoảng giải mã/copy, không lớn hơn). Có yêu cầu hàng đợi driver
1 khung (`CAP_PROP_BUFFERSIZE`); DirectShow có nhận hay không ghi ở `buffer_size_applied`. `mode()` trả về kích
thước thực đọc từ driver, còn fourcc/fps chỉ là yêu cầu; `mode_mismatch` ghi khác biệt kích thước. Một `read()` bị treo vẫn chặn vòng lặp: người dùng cần gọi `FreshnessMonitor.check()`
từ một timer riêng (hoặc chạy nguồn trong luồng riêng) để STALE_DATA vẫn được phát khi driver treo.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import re
import sys
import time
from typing import Iterator, Protocol

import cv2
import numpy as np

from autopark.domain.sensors import CameraFrame, SourceStamp

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


class FrameReadError(RuntimeError):
    """A live source failed to deliver a frame; the stream is not over."""


@dataclass(frozen=True)
class Frame:
    meta: CameraFrame
    image: np.ndarray      # BGR uint8 (H, W, 3)


class FrameSource(Protocol):
    source_id: str

    def read(self) -> Frame | None: ...

    def close(self) -> None: ...


def natural_key(path: Path) -> list:
    """frame_2 < frame_10: digits compare numerically, the rest as text."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]


def _frame(source_id: str, t: float, path: str, image: np.ndarray) -> Frame:
    if image is None or image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
        raise ValueError(f"{source_id}: expected a BGR uint8 image")
    stamp = SourceStamp(source_id, t, True, source_id)
    return Frame(CameraFrame(stamp, path, int(image.shape[1]), int(image.shape[0]), "BGR8"), image)


class ImageSequenceSource:
    """Ảnh trong một thư mục, thứ tự tự nhiên theo tên (frame_2 trước frame_10); thời gian = t0 + chỉ số / fps."""

    def __init__(self, directory, *, fps: float = 30.0, source_id: str = "camera_replay", t0: float = 0.0):
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError("fps must be finite and > 0")
        self.directory = Path(directory)
        if not self.directory.is_dir():
            raise ValueError(f"Not a directory: {self.directory}")
        self.files = sorted((p for p in self.directory.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS), key=natural_key)
        if not self.files:
            raise ValueError(f"No images in {self.directory}")
        self.fps, self.source_id, self.t0, self.index = fps, source_id, t0, 0

    def __len__(self) -> int:
        return len(self.files)

    def read(self) -> Frame | None:
        if self.index >= len(self.files):
            return None
        path = self.files[self.index]
        image = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Cannot decode {path}")
        frame = _frame(self.source_id, self.t0 + self.index / self.fps, str(path), image)
        self.index += 1
        return frame

    def __iter__(self) -> Iterator[Frame]:
        while (frame := self.read()) is not None:
            yield frame

    def close(self) -> None:
        pass


class VideoFileSource:
    """Khung hình từ file video. Một đồng hồ cho cả file: vị trí trong video (POS_MSEC) khi nó tăng nghiêm ngặt,
    nếu không thì chỉ số / fps; stamp không bao giờ giảm hay lặp."""

    def __init__(self, path, *, source_id: str = "camera_replay", t0: float = 0.0):
        self.path = Path(path)
        self.capture = cv2.VideoCapture(str(self.path))
        if not self.capture.isOpened():
            raise ValueError(f"Cannot open video {self.path}")
        fps = float(self.capture.get(cv2.CAP_PROP_FPS))
        self.fps = fps if math.isfinite(fps) and fps > 0 else 30.0
        self.frame_count = int(self.capture.get(cv2.CAP_PROP_FRAME_COUNT))
        self.source_id, self.t0, self.index = source_id, t0, 0
        self.clock_source = "position"        # switches to "index" permanently if the position clock misbehaves
        self._last_t: float | None = None

    def _stamp(self) -> float:
        if self.clock_source == "position":
            position = self.capture.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            if math.isfinite(position) and (self._last_t is None or position > self._last_t):
                return position
            self.clock_source = "index"       # stale, zero or decreasing position: fall back for the rest of the file
        t = self.index / self.fps
        if self._last_t is not None and t <= self._last_t:
            t = self._last_t + 1.0 / self.fps
        return t

    def read(self) -> Frame | None:
        ok, image = self.capture.read()
        if not ok or image is None:
            return None
        t = self._stamp()
        self._last_t = t
        frame = _frame(self.source_id, self.t0 + t, f"{self.path}#frame={self.index}", image)
        self.index += 1
        return frame

    def __iter__(self) -> Iterator[Frame]:
        while (frame := self.read()) is not None:
            yield frame

    def close(self) -> None:
        self.capture.release()


def _repeat_share(rows: np.ndarray, shift: int) -> np.ndarray:
    """Với mỗi dòng (trục 0): tỉ lệ điểm ảnh trùng từng giá trị (mọi kênh) với điểm cách nó `shift` cột về bên phải."""
    same = rows[:, :-shift] == rows[:, shift:]
    if same.ndim == 3:
        same = same.all(axis=2)
    return same.mean(axis=1)


def truncated_rows(image: np.ndarray, period: int = 8, threshold: float = 0.9, block: int = 8, max_flat: float = 0.5,
                   step: int = 4) -> int:
    """Số dòng ở đáy ảnh do bộ giải mã tô vào khi khung MJPEG bị cắt cụt trên đường USB (0 = khung nguyên vẹn).

    Thấy ngày 23/09/2026 trên bốn camera qua hub UGREEN không cắm nguồn riêng: phần thiếu của khung bị cắt được tô bằng
    một vân khối 8×8 lặp lại (xám, R = B), nên mọi dòng ở vùng đó trùng từng giá trị với chính nó dịch 8 điểm ảnh ở
    > 90 % số điểm, còn ảnh thật (nhiễu cảm biến) chỉ trùng ≤ 13 % (627 khung sạch, docs/GIAI_DOAN_2_BAN_THU.md). Khung bị
    cắt thì hàng khối cuối luôn hỏng, nên chỉ xét `block` dòng cuối (khung sạch tốn vài chục µs). Hỏng khi:
    (1) MỌI dòng trong đó trùng với chính nó dịch `period` điểm ảnh ở > `threshold` số điểm, và
    (2) vân có kết cấu BÊN TRONG chu kỳ: tỉ lệ điểm trùng điểm kề bên (dịch 1) < `max_flat`. Đuôi tô thật: ≤ 0,05; vùng
    phẳng thì gần 1 — ảnh đen, nắp ống kính, sàn trắng cháy sáng (camera này cháy thành RGB 251/255/251 chứ không phải
    255/255/255) lặp y hệt khi dịch 8 mà không phải hỏng.
    Nếu bộ giải mã tô bằng màu phẳng, hoặc khung bị cắt giữa hàng khối cuối, hàm này KHÔNG bắt được; dải xé giữa ảnh
    (mất gói giữa khung, đáy vẫn nguyên) là việc của `torn_bands`. Khi hàng khối cuối hỏng mới lấy mẫu mỗi `step` dòng
    từ đáy lên để ước lượng phần bị tô (chỉ để ghi nhận, sai lệch vài dòng)."""
    if image.ndim < 2 or image.shape[1] <= period or image.shape[0] < block:
        return 0
    h = image.shape[0]
    tail_rows = image[h - block:]
    if _repeat_share(tail_rows, period).min() <= threshold:
        return 0
    if float(_repeat_share(tail_rows, 1).mean()) >= max_flat:
        return 0
    eq = _repeat_share(image[h - 1::-step], period)
    k = len(eq) if (eq > threshold).all() else int(np.argmin(eq > threshold))
    return max(block, min(h, k * step))


def torn_bands(image: np.ndarray, period: int = 8, min_run: int = 64, max_flat: float = 0.5, block: int = 8,
               exclude_bottom_rows: int = 0) -> int:
    """Số hàng khối có dải xé: bộ giải mã tô từ một cột tới mép phải (mất dữ liệu giữa khung rồi bắt lại ở dấu khởi động
    lại; phần dưới ảnh vẫn đúng chỗ nên đáy có thể nguyên vẹn — ví dụ khung cổng 1 hit_cam_p1_000027, dòng 168–175).

    Mỗi hàng khối `block` dòng xét một dòng giữa: dải xé là một đoạn trùng với chính nó dịch `period` điểm ảnh, chạy liền
    tới mép phải, dài ≥ `min_run` điểm, và có kết cấu bên trong chu kỳ (tỉ lệ trùng điểm kề bên < `max_flat`; vùng phẳng
    hay cháy sáng chạm mép phải thì không tính). Lọc sơ bộ bằng điểm ở mép phải (phải trùng điểm cách `period` cột) nên
    khung sạch tốn rất ít. `exclude_bottom_rows` bỏ phần đáy đã bị tô (xem `truncated_rows`) để chỉ đếm dải phía trên.
    Đo 23/09/2026: 0 dải trên 638 khung sạch; dải bắt đầu gần mép phải hơn `min_run` điểm thì không bắt được."""
    if image.ndim < 2 or image.shape[1] <= period + min_run:
        return 0
    w = image.shape[1]
    n_blocks = (image.shape[0] - exclude_bottom_rows) // block
    if n_blocks <= 0:
        return 0
    rows = image[block // 2 - 1:n_blocks * block:block]           # một dòng giữa mỗi hàng khối
    edge = rows[:, -1] == rows[:, -1 - period]
    if edge.ndim == 2:
        edge = edge.all(axis=1)
    candidates = rows[edge]
    if not len(candidates):
        return 0
    same = candidates[:, :-period] == candidates[:, period:]
    if same.ndim == 3:
        same = same.all(axis=2)
    miss = ~same[:, ::-1]
    run = np.where(miss.any(axis=1), np.argmax(miss, axis=1), same.shape[1])      # số điểm trùng liền ở cuối dòng
    bands = 0
    for k in np.flatnonzero(run >= min_run):
        segment = candidates[k, w - int(run[k]) - period:]
        if float(_repeat_share(segment[None], 1)[0]) < max_flat:
            bands += 1
    return bands


def bottom_repeat_share(image: np.ndarray, period: int = 8, rows: int = 16) -> float:
    """Tỉ lệ điểm ở `rows` dòng đáy trùng với điểm cách `period` cột — con số thô, KHÔNG phải phán quyết: khung sạch
    ≤ 0,13, đáy bị tô ≈ 1. Ghi vào siêu dữ liệu ảnh chụp để lọc lại khi gán nhãn bằng một ngưỡng khác bộ dò."""
    if image.ndim < 2 or image.shape[1] <= period or image.shape[0] < 1:
        return 0.0
    return round(float(_repeat_share(image[-rows:], period).mean()), 4)


class UsbCameraSource:
    """Camera UVC qua OpenCV (DirectShow trên Windows).

    Ba điều dưới đây đo bằng `autopark.video.camera_bench` trên bốn camera "HD Camera" (Sunplus 1BCF:0B09) ngày
    23/09/2026, OpenCV 5.0 (hồ sơ: runs/camera_bench/20260923, docs/GIAI_DOAN_1_CAMERA.md mục 3); lớp này viết
    theo đó và được chạy trên camera thật bằng `camera_bench source` (hồ sơ cùng thư mục):
    (1) kích thước và MJPG phải đưa vào NGAY LÚC MỞ (`params` của `cv2.VideoCapture`) — đặt sau khi mở thì backend
    rơi về YUY2, 720p/1080p chỉ còn 10/5 fps; (2) `grab()` không chờ khung mới nên nguồn dùng `read()`, hàm này chặn
    tới khung kế tiếp; (3) `CAP_PROP_FPS` đọc lại là −1 hoặc tiếng vọng của yêu cầu nên FPS thật phải đo bằng
    `autopark.video.camera_bench`; `CAP_PROP_FOURCC` đọc lại phản ánh định dạng đã thương lượng (`fourcc_reported`). Khung trùng byte với khung trước là
    driver trả lại khung cũ: tính là lỗi đọc để tuổi khung không bị che. Stamp lấy ngay sau `read()` (đã gồm giải mã),
    bằng `time.perf_counter` (monotonic của Python 3.12 trên Windows chỉ có bước 15,6 ms).
    """

    def __init__(self, index: int, *, width: int | None = None, height: int | None = None, fps: float | None = None,
                 fourcc: str | None = "MJPG", exposure: float | None = None, source_id: str = "camera_usb",
                 clock=time.perf_counter):          # monotonic trên Python 3.12/Windows chỉ có bước 15,6 ms
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        params: list = []
        if fourcc:
            params += [cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc)]
        if width:
            params += [cv2.CAP_PROP_FRAME_WIDTH, int(width)]
        if height:
            params += [cv2.CAP_PROP_FRAME_HEIGHT, int(height)]
        if fps:
            params += [cv2.CAP_PROP_FPS, int(round(fps))]     # params chỉ nhận int
        self.capture = cv2.VideoCapture(index, backend, params) if params else cv2.VideoCapture(index, backend)
        if not self.capture.isOpened():
            raise ValueError(f"Cannot open camera index {index}")
        self.requested = {"width": width, "height": height, "fps": fps, "fourcc": fourcc, "exposure": exposure}
        self.buffer_size_applied = bool(self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1))
        if exposure is None:
            self.exposure_applied = bool(self.capture.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75))
        else:
            self.exposure_applied = bool(self.capture.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)) and \
                bool(self.capture.set(cv2.CAP_PROP_EXPOSURE, float(exposure)))
        self.source_id, self.clock, self.index, self.failures = source_id, clock, 0, 0
        self.duplicates = 0        # driver trả lại đúng khung trước (tính cả vào failures)
        self.read_failures = 0     # read() trả False/None (tính cả vào failures)
        self.truncated = 0         # khung MJPEG bị cắt cụt, đáy do bộ giải mã tô (tính cả vào failures), xem truncated_rows
        self.torn = 0              # đáy nguyên nhưng có dải xé giữa ảnh (tính cả vào failures), xem torn_bands
        self.check_truncation = True      # loại cả khung bị cắt lẫn khung có dải xé
        self._last_image: np.ndarray | None = None      # khung tốt cuối cùng đã trả ra
        self._last_read: np.ndarray | None = None       # ảnh của lần đọc thành công gần nhất (có thể là khung bị cắt)
        actual = self.mode()
        self.mode_mismatch = {key: (value, actual[key]) for key, value in self.requested.items()
                              if key in ("width", "height") and value is not None and actual[key] != value}

    def mode(self) -> dict:
        """Kích thước là thật; `fourcc_reported` là định dạng đã thương lượng (YUY2 nếu rơi về, tin được);
        `fps` là yêu cầu, `fps_reported` của DirectShow là −1 hoặc tiếng vọng nên FPS thật phải đo."""
        code = int(self.capture.get(cv2.CAP_PROP_FOURCC))
        return {"width": int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": self.requested["fps"], "fourcc": self.requested["fourcc"],
                "fourcc_reported": "".join(chr((code >> (8 * i)) & 0xFF) for i in range(4)),   # định dạng đã thương lượng
                "fps_reported": float(self.capture.get(cv2.CAP_PROP_FPS)),
                "exposure_reported": float(self.capture.get(cv2.CAP_PROP_EXPOSURE))}

    def read(self) -> Frame:
        ok, image = self.capture.read()
        t = self.clock()
        if not ok or image is None:
            self.failures += 1
            self.read_failures += 1
            raise FrameReadError(f"{self.source_id}: read failed ({self.failures} failures so far)")
        # Khung cũ xét TRƯỚC khung bị cắt, so với cả lần đọc trước (kể cả khi đó là khung bị cắt: driver trả lại đúng bộ
        # đệm đó thì là khung cũ, không phải thêm một khung bị cắt — như camera_bench.measure_stream) lẫn khung tốt cuối.
        same = lambda ref: ref is not None and image.shape == ref.shape and np.array_equal(image, ref)
        if same(self._last_read) or (self._last_image is not self._last_read and same(self._last_image)):
            self.failures += 1
            self.duplicates += 1
            raise FrameReadError(f"{self.source_id}: driver returned the previous frame again")
        self._last_read = image
        if self.check_truncation:
            rows = truncated_rows(image)
            if rows:
                self.failures += 1
                self.truncated += 1
                raise FrameReadError(f"{self.source_id}: truncated frame ({rows} of {image.shape[0]} rows filled by the decoder)")
            bands = torn_bands(image)
            if bands:
                self.failures += 1
                self.torn += 1
                raise FrameReadError(f"{self.source_id}: torn frame ({bands} block rows filled mid-image by the decoder)")
        self._last_image = image
        frame = _frame(self.source_id, t, f"usb#frame={self.index}", image)
        self.index += 1
        return frame

    def close(self) -> None:
        self.capture.release()


def open_source(spec: str, **kwargs) -> FrameSource:
    """'usb:0' -> camera, a directory -> image sequence, otherwise a video file."""
    if spec.startswith("usb:"):
        return UsbCameraSource(int(spec[4:]), **kwargs)
    path = Path(spec)
    if path.is_dir():
        return ImageSequenceSource(path, **kwargs)
    return VideoFileSource(path, **kwargs)
