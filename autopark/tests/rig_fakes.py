"""Nguồn giả cho bàn thử nhiều cảm biến: camera, LiDAR, bộ phân đoạn — chạy thật theo thời gian, không cần phần cứng."""
import math
import time

import numpy as np

from autopark.domain.sensors import LidarScan, SourceStamp
from autopark.video.multicam import RIG_CLOCK, CameraSpec
from autopark.video.sources import FrameReadError, _frame


class FakeCamera:
    """read() chặn `period` giây rồi trả một khung mới; mỗi `dup_every` lần thì ném lỗi khung cũ, mỗi `trunc_every` lần
    thì ném lỗi khung bị cắt, mỗi `torn_every` lần thì ném lỗi khung xé, như UsbCameraSource thật.

    `textured`: ảnh có vân (dốc màu + nhiễu cố định theo cổng và số khung, ô 8×8 góc trái trên = số khung % 256) thay vì
    hai mảng phẳng — để phép so JPEG/PNG khi ghi–phát lại có nghĩa. `keep`: giữ (stamp, ảnh) mọi khung tốt đã trả ở `kept`."""

    def __init__(self, spec: CameraSpec, period: float = 0.02, size=(64, 48), dup_every: int = 0, fail_every: int = 0,
                 phase: float = 0.0, clock=RIG_CLOCK, trunc_every: int = 0, torn_every: int = 0, textured: bool = False,
                 keep: bool = False):
        self.spec, self.period, self.size, self.clock = spec, period, size, clock
        self.dup_every, self.fail_every, self.trunc_every, self.torn_every = dup_every, fail_every, trunc_every, torn_every
        self.textured = textured
        self.kept: list | None = [] if keep else None
        self.n = 0
        self.closed = False
        time.sleep(phase)

    def _textured(self, w: int, h: int) -> np.ndarray:
        yy, xx = np.mgrid[0:h, 0:w]
        base = (xx * 3 + yy * 2 + self.n * 5 + self.spec.port * 60) % 200 + 20
        noise = np.random.default_rng(self.spec.port * 1_000_003 + self.n).integers(-6, 7, (h, w, 3))
        image = np.clip(base[..., None] + noise, 0, 255).astype(np.uint8)
        image[:8, :8] = self.n % 256
        return image

    def read(self):
        time.sleep(self.period)
        self.n += 1
        if self.dup_every and self.n % self.dup_every == 0:
            raise FrameReadError(f"{self.spec.source_id}: driver returned the previous frame again")
        if self.fail_every and self.n % self.fail_every == 0:
            raise FrameReadError(f"{self.spec.source_id}: read failed")
        if self.trunc_every and self.n % self.trunc_every == 0:
            raise FrameReadError(f"{self.spec.source_id}: truncated frame (24 of 48 rows filled by the decoder)")
        if self.torn_every and self.n % self.torn_every == 0:
            raise FrameReadError(f"{self.spec.source_id}: torn frame (1 block rows filled mid-image by the decoder)")
        w, h = self.size
        if self.textured:
            image = self._textured(w, h)
        else:
            image = np.full((h, w, 3), (self.n * 7 + self.spec.port * 40) % 256, np.uint8)
            image[: h // 2] = 30                      # nửa trên tối, nửa dưới sáng: bộ phân đoạn giả chia đôi
        frame = _frame(self.spec.source_id, self.clock(), f"fake#{self.n}", image)
        if self.kept is not None:
            self.kept.append((frame.meta.stamp.t, image.copy()))
        return frame

    def close(self):
        self.closed = True


class FakeRevolution:
    def __init__(self, t_first, t_last):
        self.t_first, self.t_last = t_first, t_last


class FakeLidar:
    """Như RplidarC1Source: stamp là giờ phiên (so với `t0`), read() chặn một vòng quét, có `last_revolution` và
    `last_quality` (chất lượng từng tia: 0 ở tia không phản hồi). Khoảng cách đổi theo số vòng để phép so ghi–phát lại
    phân biệt được từng vòng."""

    def __init__(self, period: float = 0.1, beams: int = 90, fail_first: int = 0, clock=RIG_CLOCK):
        self.period, self.beams, self.fail_first, self.clock = period, beams, fail_first, clock
        self.t0 = clock()
        self.n = 0
        self.closed = False
        self.last_revolution = None
        self.last_quality = None

    def read(self) -> LidarScan:
        t_start = self.clock() - self.t0
        time.sleep(self.period)
        self.n += 1
        if self.n <= self.fail_first:
            raise RuntimeError("giả lập ScanReadError")
        t_last = self.clock() - self.t0
        self.last_revolution = FakeRevolution(t_start, t_last)
        angles = tuple(-math.pi + 2 * math.pi * k / self.beams for k in range(self.beams))
        ranges = tuple(1.5 + 0.001 * (self.n % 100) if k % 10 else float("nan") for k in range(self.beams))
        self.last_quality = np.array([0 if k % 10 == 0 else 40 + self.n % 7 for k in range(self.beams)], np.uint8)
        return LidarScan(SourceStamp("fake_lidar", t_last, True, "lidar"), angles, ranges)

    def stats(self):
        return {"revolutions_returned": self.n}

    def close(self):
        self.closed = True


class FakeTiming:
    def __init__(self, batch):
        self.batch, self.pre_ms, self.model_ms, self.post_ms, self.total_ms = batch, 1.0, 2.0, 0.5, 3.5


class FakeSegmenter:
    """Xác suất BLOCKED = 0,9 ở nửa trên ảnh, 0,1 ở nửa dưới."""

    def __init__(self, path: str, delay: float = 0.005, fail: bool = False):
        self.name, self.delay, self.device, self.amp, self.fail = f"fake:{path}", delay, "cpu", False, fail
        self.batch_sizes: list[int] = []            # cỡ từng lô đã nhận, để test biết AI chấm bao nhiêu camera

    def infer(self, images, out_size=None):
        self.batch_sizes.append(len(images))
        time.sleep(self.delay)
        if self.fail:
            raise RuntimeError("giả lập CUDA hết bộ nhớ")
        out = []
        for k, image in enumerate(images):
            size = (image.shape[1], image.shape[0]) if out_size is None else \
                (out_size[k] if isinstance(out_size, list) else out_size)
            w, h = size
            prob = np.full((h, w), 0.1, np.float32)
            prob[: h // 2] = 0.9
            out.append(prob)
        return out, FakeTiming(len(images))


def fake_manager(ports=(1, 2, 3, 4), period=0.02, broken=(), periods=None, port_kw=None, **kw):
    """`periods`: {cổng: chu kỳ riêng} cho camera chậm hơn (ví dụ {4: 0.06} khi các camera khác 0,02). `port_kw`: {cổng:
    tham số FakeCamera riêng}, ví dụ {4: {"trunc_every": 2}} cho một camera lỡ nhịp vì khung hỏng."""
    from autopark.video.multicam import MultiCameraManager

    specs = [CameraSpec(port=p, index=k) for k, p in enumerate(ports)]

    def open_source(spec):
        if spec.port in broken:
            raise ValueError(f"Cannot open camera index {spec.index}")
        return FakeCamera(spec, period=(periods or {}).get(spec.port, period), **{**kw, **(port_kw or {}).get(spec.port, {})})

    return MultiCameraManager(specs, open_source=open_source, ring=3)
