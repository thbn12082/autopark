"""Nguồn giả cho bàn thử nhiều cảm biến: camera, LiDAR, bộ phân đoạn — chạy thật theo thời gian, không cần phần cứng."""
import math
import time

import numpy as np

from autopark.domain.sensors import LidarScan, SourceStamp
from autopark.video.multicam import RIG_CLOCK, CameraSpec
from autopark.video.sources import FrameReadError, _frame


class FakeCamera:
    """read() chặn `period` giây rồi trả một khung mới; mỗi `dup_every` lần thì ném lỗi khung cũ, mỗi `trunc_every` lần
    thì ném lỗi khung bị cắt, mỗi `torn_every` lần thì ném lỗi khung xé, như UsbCameraSource thật."""

    def __init__(self, spec: CameraSpec, period: float = 0.02, size=(64, 48), dup_every: int = 0, fail_every: int = 0,
                 phase: float = 0.0, clock=RIG_CLOCK, trunc_every: int = 0, torn_every: int = 0):
        self.spec, self.period, self.size, self.clock = spec, period, size, clock
        self.dup_every, self.fail_every, self.trunc_every, self.torn_every = dup_every, fail_every, trunc_every, torn_every
        self.n = 0
        self.closed = False
        time.sleep(phase)

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
        image = np.full((h, w, 3), (self.n * 7 + self.spec.port * 40) % 256, np.uint8)
        image[: h // 2] = 30                      # nửa trên tối, nửa dưới sáng: bộ phân đoạn giả chia đôi
        return _frame(self.spec.source_id, self.clock(), f"fake#{self.n}", image)

    def close(self):
        self.closed = True


class FakeRevolution:
    def __init__(self, t_first, t_last):
        self.t_first, self.t_last = t_first, t_last


class FakeLidar:
    """Như RplidarC1Source: stamp là giờ phiên (so với `t0`), read() chặn một vòng quét, có `last_revolution`."""

    def __init__(self, period: float = 0.1, beams: int = 90, fail_first: int = 0, clock=RIG_CLOCK):
        self.period, self.beams, self.fail_first, self.clock = period, beams, fail_first, clock
        self.t0 = clock()
        self.n = 0
        self.closed = False
        self.last_revolution = None

    def read(self) -> LidarScan:
        t_start = self.clock() - self.t0
        time.sleep(self.period)
        self.n += 1
        if self.n <= self.fail_first:
            raise RuntimeError("giả lập ScanReadError")
        t_last = self.clock() - self.t0
        self.last_revolution = FakeRevolution(t_start, t_last)
        angles = tuple(-math.pi + 2 * math.pi * k / self.beams for k in range(self.beams))
        ranges = tuple(1.5 if k % 10 else float("nan") for k in range(self.beams))
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


def fake_manager(ports=(1, 2, 3, 4), period=0.02, broken=(), periods=None, **kw):
    """`periods`: {cổng: chu kỳ riêng} cho camera chậm hơn (ví dụ {4: 0.06} khi các camera khác 0,02)."""
    from autopark.video.multicam import MultiCameraManager

    specs = [CameraSpec(port=p, index=k) for k, p in enumerate(ports)]

    def open_source(spec):
        if spec.port in broken:
            raise ValueError(f"Cannot open camera index {spec.index}")
        return FakeCamera(spec, period=(periods or {}).get(spec.port, period), **kw)

    return MultiCameraManager(specs, open_source=open_source, ring=3)
