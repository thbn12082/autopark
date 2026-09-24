"""Khung MJPEG hỏng trên đường USB, thấy ngày 23/09/2026 khi chạy bốn camera qua hub: đáy ảnh bị bộ giải mã tô bằng một
khối 8×8 xám lặp lại (khung bị cắt cụt), có khi kèm dải xé giữa ảnh (mất dữ liệu giữa khung). Bộ dò, nguồn USB loại khung,
camera_bench và rig đếm — không cần phần cứng."""
import time

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from autopark.rig.core import Rig, RigConfig  # noqa: E402
from autopark.video import camera_bench as cb  # noqa: E402
from autopark.video.sources import (FrameReadError, UsbCameraSource, bottom_repeat_share, torn_bands,  # noqa: E402
                                    truncated_rows)
from tests.rig_fakes import fake_manager  # noqa: E402


def scene(h=720, w=1280, seed=0):
    """Giống ảnh camera: độ sáng đổi mượt + nhiễu cảm biến (dịch 8 điểm ảnh gần như không trùng)."""
    rng = np.random.default_rng(seed)
    base = np.linspace(40, 200, h)[:, None, None] + np.linspace(0, 30, w)[None, :, None]
    return np.clip(base + rng.normal(0, 3, (h, w, 3)), 0, 255).astype(np.uint8)


def fill_pattern(h, w, flat_last_row=False, seed=1):
    """Vân bộ giải mã tô: một khối 8×8 xám (R = B) có kết cấu bên trong, lặp lại khắp ảnh."""
    rng = np.random.default_rng(seed)
    g = rng.integers(100, 160, (8, 8)).astype(np.uint8)
    if flat_last_row:                                   # ảnh hỏng thật ở cổng 4: dòng cuối của vân gần phẳng
        g[7] = 128
    tile = np.stack([g, g + 3, g], axis=2)
    return np.tile(tile, (h // 8 + 1, w // 8 + 1, 1))[:h, :w]


def truncate(image, first_bad_row, flat_last_row=False):
    """Tô từ `first_bad_row` xuống đáy, như khung bị cắt cụt thật."""
    out = image.copy()
    out[first_bad_row:] = fill_pattern(*image.shape[:2], flat_last_row=flat_last_row)[first_bad_row:]
    return out


def tear(image, block_row, from_col):
    """Dải xé: một hàng khối 8 dòng bị tô từ cột `from_col` tới mép phải, phần còn lại của ảnh nguyên (như hit_cam_p1_000027)."""
    out = image.copy()
    r = slice(8 * block_row, 8 * block_row + 8)
    out[r, from_col:] = fill_pattern(*image.shape[:2])[r, from_col:]
    return out


def test_detector_finds_the_filled_band_and_measures_it():
    clean = scene()
    assert truncated_rows(clean) == 0
    # cùng số với hai ảnh hỏng thật (cổng 1 hỏng từ dòng 368, cổng 4 từ dòng 392), lấy mẫu mỗi 4 dòng
    assert truncated_rows(truncate(clean, 368)) == 352
    assert truncated_rows(truncate(clean, 392, flat_last_row=True)) == 328
    assert truncated_rows(truncate(clean, 0)) == 720
    for h, w in ((480, 640), (1080, 1920)):
        other = scene(h, w, seed=2)
        assert truncated_rows(other) == 0 and truncated_rows(truncate(other, h - 64)) == 64


def test_detector_ignores_flat_saturated_noisy_and_tiny_images():
    # Các ca dưới đây đều lặp y hệt khi dịch 8 điểm ảnh (qua được phép thử đầu): chỉ phép thử "vân có kết cấu bên trong
    # chu kỳ" chặn chúng. Bỏ phép thử đó thì mọi khung của cảnh như vậy bị loại.
    assert truncated_rows(np.zeros((720, 1280, 3), np.uint8)) == 0              # nắp ống kính / tối
    assert truncated_rows(np.full((720, 1280, 3), 128, np.uint8)) == 0          # xám phẳng
    white8 = np.full((720, 1280, 3), 255, np.uint8)
    white8[-8:, ::8] = 20                                                       # cháy sáng, cứ 8 cột một điểm tối
    assert truncated_rows(white8) == 0
    split = scene()
    split[-40:, :640] = 0
    split[-40:, 640:] = 255                                                     # vật đen cạnh vùng cháy sáng
    assert truncated_rows(split) == 0
    # sàn trắng cháy sáng kiểu camera này (RGB 251/255/251, không phải 255/255/255) phủ 92 % bề ngang, mép mềm, qua JPEG
    blown = scene()
    mask = np.zeros(blown.shape[:2], np.float32)
    mask[-120:, : int(0.92 * 1280)] = 1.0
    mask = cv2.GaussianBlur(mask, (0, 0), 3)[..., None]
    blown = (blown * (1 - mask) + np.array([251, 255, 251], np.float32) * mask).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", blown, [cv2.IMWRITE_JPEG_QUALITY, 85])
    blown = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    assert truncated_rows(blown) == 0 and torn_bands(blown) == 0
    assert truncated_rows(np.random.default_rng(3).integers(0, 256, (720, 1280, 3), dtype=np.uint8)) == 0
    assert truncated_rows(np.zeros((4, 6, 3), np.uint8)) == 0
    assert truncated_rows(scene()[:, :, 0]) == 0                                # ảnh xám một kênh
    assert truncated_rows(truncate(scene(), 600)[:, :, 0]) == 120


def test_torn_band_mid_image_is_found_even_when_the_bottom_is_intact():
    clean = scene()
    assert torn_bands(clean) == 0
    torn = tear(clean, block_row=21, from_col=208)                   # dòng 168–175 từ cột 208, như khung thật cổng 1
    assert truncated_rows(torn) == 0 and torn_bands(torn) == 1
    assert torn_bands(tear(tear(clean, 5, 632), 60, 96)) == 2
    assert torn_bands(tear(clean, 30, 1280 - 40)) == 0              # dải ngắn hơn 64 điểm: giới hạn đã ghi
    edge = scene()
    edge[:, -200:] = (251, 255, 251)                                 # vùng cháy sáng chạm mép phải: phẳng, không phải xé
    assert torn_bands(edge) == 0
    both = tear(truncate(clean, 600), 10, 300)
    rows = truncated_rows(both)
    assert rows == 120 and torn_bands(both, exclude_bottom_rows=rows) == 1


def test_detectors_are_cheap_on_clean_frames():
    clean = scene()
    truncated_rows(clean), torn_bands(clean)
    t = time.perf_counter()
    for _ in range(50):
        truncated_rows(clean)
        torn_bands(clean)
    assert (time.perf_counter() - t) / 50 < 0.005      # chạy trên mọi khung của bốn camera: phải rẻ


def test_bottom_repeat_share_is_a_raw_number():
    assert bottom_repeat_share(scene()) < 0.2 and bottom_repeat_share(truncate(scene(), 600)) > 0.9


class ImageCapture:
    """cv2.VideoCapture giả trả lần lượt các ảnh cho sẵn (hết thì ảnh cuối, mỗi lần khác một điểm ảnh), mỗi lần đọc tốn `dt` giây."""

    def __init__(self, images, dt=0.01):
        self.images, self.dt, self.now, self.i = list(images), dt, 0.0, 0
        h, w = self.images[0].shape[:2]
        self.props = {cv2.CAP_PROP_FRAME_WIDTH: w, cv2.CAP_PROP_FRAME_HEIGHT: h}

    def clock(self):
        return self.now

    def isOpened(self):
        return True

    def get(self, prop):
        return self.props.get(prop, 0.0)

    def set(self, prop, value):
        return True

    def read(self):
        self.now += self.dt
        k = self.i
        self.i += 1
        if k < len(self.images):
            return True, self.images[k]
        image = self.images[-1].copy()
        image[0, 0, 0] = k % 256                    # khác khung trước để không bị tính là khung cũ
        return True, image

    def release(self):
        pass


def open_with(monkeypatch, images):
    monkeypatch.setattr(cv2, "VideoCapture", lambda *args: ImageCapture(images))
    return UsbCameraSource(0, width=1280, height=720, clock=lambda: 1.0)


def test_usb_source_rejects_truncated_frames_and_keeps_the_good_frame_as_reference(monkeypatch):
    a, b = scene(seed=10), scene(seed=11)
    bad = truncate(scene(seed=12), 400)
    source = open_with(monkeypatch, [a, bad, a, b])
    assert source.read() is not None
    with pytest.raises(FrameReadError, match="truncated frame"):
        source.read()
    with pytest.raises(FrameReadError, match="previous frame"):     # khung hỏng không thay khung tốt làm mốc: a vẫn là cũ
        source.read()
    assert source.read() is not None                                 # b: khung mới thật
    assert source.truncated == 1 and source.duplicates == 1 and source.failures == 2


def test_usb_source_counts_a_redelivered_truncated_buffer_as_duplicate(monkeypatch):
    # driver trả lại đúng bộ đệm hỏng vừa đọc: đó là khung cũ, không phải thêm một khung bị cắt (như camera_bench)
    good, good2 = scene(seed=20), scene(seed=21)
    bad = truncate(scene(seed=22), 360)
    source = open_with(monkeypatch, [good, bad, bad, bad, good2])
    source.read()
    for _ in range(3):
        with pytest.raises(FrameReadError):
            source.read()
    assert source.read() is not None
    assert source.truncated == 1 and source.duplicates == 2
    cap = ImageCapture([good] * 5 + [good, bad, bad, bad, good2], dt=0.01)
    stats = cb.measure_stream(cap, seconds=0.05, index=0, clock=cap.clock, warmup_frames=5)
    assert stats.truncated_frames == 1 and stats.duplicate_reads == 3        # bench: good lặp lại 1 lần + bad 2 lần


def test_usb_source_rejects_torn_frames(monkeypatch):
    a, b = scene(seed=30), scene(seed=31)
    torn = tear(scene(seed=32), 21, 208)
    source = open_with(monkeypatch, [a, torn, b])
    source.read()
    with pytest.raises(FrameReadError, match="torn frame"):
        source.read()
    assert source.read() is not None and source.torn == 1 and source.truncated == 0 and source.failures == 1
    unchecked = open_with(monkeypatch, [truncate(scene(seed=33), 400)])
    unchecked.check_truncation = False                      # tắt được khi cần ghi nguyên khung hỏng để xem
    assert unchecked.read() is not None and unchecked.truncated == 0


def test_measure_stream_counts_truncated_and_torn_frames_inside_new_frames():
    clean = [scene(96, 128, seed=s) for s in range(20)]
    def frame(k):
        if k % 4 == 0:
            return truncate(scene(96, 128, seed=100 + k), 48)
        if k % 4 == 1:
            return tear(scene(96, 128, seed=200 + k), 3, 32)
        return clean[5 + k % 15]
    cap = ImageCapture(clean[:5] + [frame(k) for k in range(40)], dt=0.01)
    stats = cb.measure_stream(cap, seconds=0.3, index=0, clock=cap.clock, warmup_frames=5)
    assert stats.new_frames == 30 and stats.truncated_frames == 8 and stats.torn_frames == 8   # k ≡ 0 / ≡ 1 (mod 4), k < 30
    request = {"fourcc": "MJPG", "width": 128, "height": 96, "fps": 30}
    row = cb.report_markdown([{"name": "x", "created_utc": "t", "process_cpu_cores": 0.1, "requested": request,
                               "streams": [cb.asdict(stats)]}])
    assert "| 8 / 8 |" in row
    old = {k: v for k, v in cb.asdict(stats).items() if k not in ("truncated_frames", "torn_frames")}   # json giai đoạn 1
    assert "chưa đo" in cb.report_markdown([{"name": "cu", "created_utc": "t", "process_cpu_cores": 0.1,
                                             "requested": request, "streams": [old]}])


def test_manager_and_rig_count_truncated_and_torn_frames_per_camera():
    cams = fake_manager(ports=(1, 2), period=0.01, trunc_every=4, torn_every=7)
    rig = Rig(cams, RigConfig(ai=False))
    rig.start()
    try:
        time.sleep(1.3)
        stats = cams.stats()
        rig.reset_counters()
        after_reset = cams.camera_stats()
        time.sleep(1.2)
        series = list(rig.series)
    finally:
        rig.stop()
    for c in stats["cameras"]:
        assert c["truncated"] > 3 and c["torn"] > 1 and c["duplicates"] == 0 and c["read_failures"] == 0
        assert c["frames"] >= 2 * c["truncated"]
    assert all(c["truncated"] <= 2 and c["torn"] <= 2 for c in after_reset)
    assert series and all(v >= 0 for row in series for key in ("cam_truncated_1s", "cam_torn_1s") for v in row[key].values())
    assert sum(row["cam_truncated_1s"][1] for row in series) > 0
