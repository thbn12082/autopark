"""Nguồn ảnh camera theo hợp đồng `CameraFrame`: thư mục ảnh, file video lưu sẵn và camera USB.

Cùng một giao diện `FrameSource` cho cả ba, để phần nhận thức và giám sát dữ liệu cũ chạy y hệt trên dữ liệu
phát lại và trên camera thật (giai đoạn 1). Quy ước `read()`: trả `Frame`; trả `None` CHỈ khi nguồn phát lại
đã hết; nguồn trực tiếp không bao giờ trả `None` mà ném `FrameReadError` khi một lần đọc hỏng, để vòng lặp
tiêu thụ không nhầm sự cố USB với hết dữ liệu. Thời gian của nguồn phát lại lấy từ file (một đồng hồ duy nhất
cho cả file) cộng `t0`; camera thật lấy đồng hồ phiên tại thời điểm `grab()` (trước khi giải mã) và giữ hàng
đợi driver ở 1 khung để tuổi khung phản ánh đúng độ trễ. `UsbCameraSource` mới chỉ được viết theo API OpenCV,
chưa chạy với thiết bị nào trên máy này; `mode()` trả về mode thực đọc từ driver và `mode_mismatch` ghi khác
biệt so với yêu cầu. Một `read()` bị treo vẫn chặn vòng lặp: người dùng cần gọi `FreshnessMonitor.check()`
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


class UsbCameraSource:
    """Camera UVC qua OpenCV. CHƯA KIỂM CHỨNG với thiết bị thật.

    Stamp lấy ngay sau `grab()` (trước khi giải mã), hàng đợi driver đặt về 1 khung (nếu driver cho phép) và
    khung trùng byte với khung trước bị coi là lỗi đọc, để tuổi khung không bị che bởi bộ đệm của driver.
    """

    def __init__(self, index: int, *, width: int | None = None, height: int | None = None, fps: float | None = None,
                 fourcc: str | None = "MJPG", source_id: str = "camera_usb", clock=time.monotonic):
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        self.capture = cv2.VideoCapture(index, backend)
        if not self.capture.isOpened():
            raise ValueError(f"Cannot open camera index {index}")
        self.requested = {"width": width, "height": height, "fps": fps, "fourcc": fourcc}
        # DirectShow tends to reset the pixel format when the frame size changes: size first, then format.
        if width:
            self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        if height:
            self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if fourcc:
            self.capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
        if fps:
            self.capture.set(cv2.CAP_PROP_FPS, fps)
        self.buffer_size_applied = bool(self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1))
        self.source_id, self.clock, self.index, self.failures = source_id, clock, 0, 0
        self._last_image: np.ndarray | None = None
        actual = self.mode()
        self.mode_mismatch = {key: (value, actual[key]) for key, value in self.requested.items()
                              if value is not None and actual[key] != value and not (key == "fps" and actual[key] == 0)}

    def mode(self) -> dict:
        code = int(self.capture.get(cv2.CAP_PROP_FOURCC))
        return {"width": int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": float(self.capture.get(cv2.CAP_PROP_FPS)),
                "fourcc": "".join(chr((code >> (8 * i)) & 0xFF) for i in range(4))}

    def read(self) -> Frame:
        if not self.capture.grab():
            self.failures += 1
            raise FrameReadError(f"{self.source_id}: grab failed ({self.failures} failures so far)")
        t = self.clock()
        ok, image = self.capture.retrieve()
        if not ok or image is None:
            self.failures += 1
            raise FrameReadError(f"{self.source_id}: retrieve failed ({self.failures} failures so far)")
        if self._last_image is not None and image.shape == self._last_image.shape and np.array_equal(image, self._last_image):
            self.failures += 1
            raise FrameReadError(f"{self.source_id}: driver returned the previous frame again")
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
