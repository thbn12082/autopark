"""AI tô các vùng quanh xe mà không camera nào thấy, CHỈ để xem (29/11/2026).

Bốn camera ≈ 98° gắn ở mép thân xe nên sát mỗi góc xe có một hình nêm không camera nào nhìn tới. Mô hình LaMa (big-lama,
bản ONNX của Carve, Apache-2.0: https://huggingface.co/Carve/LaMa-ONNX) vẽ tiếp mặt sàn từ hai bên vào vùng đó.

Ràng buộc an toàn:
- Phần AI vẽ KHÔNG phải hình thật: một vật cản nằm trong vùng mù sẽ bị vẽ thành sàn trống. Ảnh ghép luôn đánh dấu vùng này
  bằng sọc mảnh (`mark_ai_region`), và ảnh ghép quanh xe chỉ để người xem; không khối nào khác đọc nó để lập đường hay
  tìm vật cản.
- Suy luận chạy ở một luồng nền riêng; khung hình chỉ lấy kết quả mới nhất đã có, không bao giờ chờ mô hình. Chỉ dùng
  khi có GPU CUDA (≈ 0,25 s một lần trên RTX 3050 Ti); trên CPU LaMa mất ≈ 3,4 s và chiếm mọi nhân, có thể làm trễ vòng
  điều khiển xe 50 Hz, nên không bật.

Cài: `uv pip install --python .venv\\Scripts\\python.exe "onnxruntime-gpu[cuda,cudnn]>=1.20"`, rồi tải
`lama_fp32.onnx` (208 044 816 byte, SHA-256 `MODEL_SHA256`) vào `models/lama/`. Thiếu một trong hai thì ảnh ghép tự dùng
cách lấp màu loang cũ.
"""
from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .paths import PROJECT

MODEL_PATH = PROJECT / "models/lama/lama_fp32.onnx"
MODEL_URL = ("https://huggingface.co/Carve/LaMa-ONNX/resolve/c3c0c9e468934d62e79c329e35d82dd09ff8c444/"
             "lama_fp32.onnx")
MODEL_SIZE = 208_044_816
MODEL_SHA256 = "1faef5301d78db7dda502fe59966957ec4b79dd64e16f03ed96913c7a4eb68d6"
INPUT_SIZE = 512                       # bản ONNX cố định 512×512
MASK_DILATE_PX = 5                     # nới mặt nạ để mép vùng thiếu (nội suy dở dang) cũng được vẽ lại
REFRESH_S = 0.4                        # không chạy lại sớm hơn thế này dù cảnh đổi
CHANGE_LEVEL = 4.0                     # đổi trung bình > ngần này mức xám quanh vùng thiếu thì vẽ lại
MAX_AGE_S = 3.0                        # kết quả cũ hơn thế này thì chạy lại dù cảnh không đổi
STRIPE_PERIOD_PX, STRIPE_WIDTH_PX, STRIPE_ALPHA = 9, 1, 0.22
STRIPE_COLOR = np.array([235, 205, 150], np.float32)   # BGR, xanh nhạt


class InpaintUnavailable(RuntimeError):
    pass


def check_model(path: Path = MODEL_PATH, *, full_hash: bool = False) -> None:
    """Có tệp, đúng cỡ (và đúng SHA-256 khi `full_hash`); không thì `InpaintUnavailable`."""
    if not path.is_file():
        raise InpaintUnavailable(f"chưa có mô hình {path} (tải từ {MODEL_URL})")
    if path.stat().st_size != MODEL_SIZE:
        raise InpaintUnavailable(f"{path}: cỡ {path.stat().st_size} byte, cần {MODEL_SIZE}")
    if full_hash:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != MODEL_SHA256:
            raise InpaintUnavailable(f"{path}: SHA-256 {digest} khác {MODEL_SHA256}")


class LamaInpainter:
    """Phiên ONNX Runtime của LaMa trên GPU CUDA. `fill(ảnh BGR, mặt nạ bool)` → ảnh BGR cùng cỡ."""

    def __init__(self, path: Path = MODEL_PATH):
        check_model(path)
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise InpaintUnavailable("chưa cài onnxruntime-gpu") from exc
        if "CUDAExecutionProvider" not in ort.get_available_providers():
            raise InpaintUnavailable("onnxruntime không có CUDA (trên CPU LaMa quá chậm cho xem trực tiếp)")
        ort.set_default_logger_severity(3)
        try:
            ort.preload_dlls()
        except (AttributeError, OSError):
            pass
        options = ort.SessionOptions()
        options.log_severity_level = 3
        options.intra_op_num_threads = 1          # đo: ≈ 0,9 nhân CPU mỗi lần dù để mặc định; giữ CPU cho app
        # dò thuật toán cuDNN đầy đủ làm lần chạy đầu mất ≈ 9 s; "HEURISTIC" chọn ngay, tốc độ sau đó như nhau
        cuda = ("CUDAExecutionProvider", {"cudnn_conv_algo_search": "HEURISTIC"})
        self.session = ort.InferenceSession(str(path), options, providers=[cuda])
        if "CUDAExecutionProvider" not in self.session.get_providers():
            raise InpaintUnavailable("không mở được LaMa trên GPU CUDA")

    def fill(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        h, w = image.shape[:2]
        rgb = cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2RGB), (INPUT_SIZE, INPUT_SIZE),
                         interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        hole = cv2.resize(mask.astype(np.uint8), (INPUT_SIZE, INPUT_SIZE), interpolation=cv2.INTER_NEAREST)
        hole = cv2.dilate(hole, np.ones((MASK_DILATE_PX, MASK_DILATE_PX), np.uint8)).astype(np.float32)
        rgb *= 1.0 - hole[..., None]
        out = self.session.run(None, {"image": rgb.transpose(2, 0, 1)[None], "mask": hole[None, None]})[0]
        out = np.clip(out[0].transpose(1, 2, 0), 0, 255).astype(np.uint8)
        return cv2.resize(cv2.cvtColor(out, cv2.COLOR_RGB2BGR), (w, h), interpolation=cv2.INTER_CUBIC)


@dataclass(frozen=True)
class FillResult:
    image: np.ndarray                  # ảnh đã tô, cùng cỡ ảnh gửi vào
    made_at: float                     # time.monotonic() lúc có kết quả
    seconds: float                     # thời gian suy luận


class BackgroundFiller:
    """Một luồng nền: nhận ảnh mới nhất (`offer`), chỉ vẽ lại khi cảnh quanh vùng thiếu đổi đủ nhiều hoặc kết quả đã cũ;
    `latest()` trả kết quả gần nhất (hoặc None) ngay lập tức."""

    def __init__(self, fill_fn, mask: np.ndarray, *, clock=time.monotonic):
        self._fill = fill_fn
        self._mask = mask.astype(bool)
        ring = cv2.dilate(mask.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool) & ~self._mask
        self._ring = ring
        self._clock = clock
        self._lock = threading.Condition()
        self._pending: np.ndarray | None = None
        self._result: FillResult | None = None
        self._last_context: np.ndarray | None = None
        self._last_start = -float("inf")
        self.error: str | None = None
        self._stop = False
        self._thread = threading.Thread(target=self._run, name="autopark-bev-inpaint", daemon=True)
        self._thread.start()

    def _needs_refresh(self, image: np.ndarray, now: float) -> bool:
        if now - self._last_start < REFRESH_S:
            return False
        if self._result is None or self._last_context is None or now - self._result.made_at > MAX_AGE_S:
            return True
        context = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)[self._ring].astype(np.float32)
        return float(np.mean(np.abs(context - self._last_context))) > CHANGE_LEVEL

    def offer(self, image: np.ndarray) -> None:
        with self._lock:
            if self._stop or self.error is not None or self._pending is not None:
                return
            if self._needs_refresh(image, self._clock()):
                self._pending = image.copy()
                self._lock.notify()

    def latest(self) -> FillResult | None:
        with self._lock:
            return self._result

    def close(self) -> None:
        with self._lock:
            self._stop = True
            self._lock.notify()

    def _run(self) -> None:
        while True:
            with self._lock:
                while self._pending is None and not self._stop:
                    self._lock.wait()
                if self._stop:
                    return
                image = self._pending
                self._last_start = self._clock()
            try:
                started = time.perf_counter()
                filled = self._fill(image, self._mask)
                spent = time.perf_counter() - started
            except Exception as exc:  # noqa: BLE001 - lỗi mô hình: tắt AI, ảnh ghép quay về màu loang
                with self._lock:
                    self.error = " ".join(str(exc).split())[:200]
                    self._pending = None
                return
            with self._lock:
                self._result = FillResult(filled, self._clock(), spent)
                self._last_context = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)[self._ring].astype(np.float32)
                self._pending = None


_shared: LamaInpainter | None = None
_shared_error: str | None = None
_shared_lock = threading.Lock()


def shared_inpainter() -> LamaInpainter | None:
    """Một phiên LaMa dùng chung cho cả app (nạp ≈ 7 s một lần). None (kèm `shared_error()`) nếu không dùng được."""
    global _shared, _shared_error
    with _shared_lock:
        if _shared is None and _shared_error is None:
            try:
                _shared = LamaInpainter()
            except InpaintUnavailable as exc:
                _shared_error = str(exc)
            except Exception as exc:  # noqa: BLE001 - lỗi ONNX Runtime/driver: không có AI, không làm hỏng ảnh ghép
                _shared_error = f"không mở được LaMa: {' '.join(str(exc).split())[:160]}"
        return _shared


def shared_error() -> str | None:
    return _shared_error


def mark_ai_region(image: np.ndarray, region: np.ndarray) -> np.ndarray:
    """Sọc chéo mảnh, nhạt trên vùng AI vẽ để người xem biết đó không phải hình thật."""
    yy, xx = np.mgrid[: image.shape[0], : image.shape[1]]
    stripes = region & (((xx + yy) % STRIPE_PERIOD_PX) < STRIPE_WIDTH_PX)
    out = image.copy()
    out[stripes] = ((1 - STRIPE_ALPHA) * out[stripes] + STRIPE_ALPHA * STRIPE_COLOR).astype(np.uint8)
    return out


# ---- dòng lệnh: tải và kiểm mô hình --------------------------------------------------------------------------------
def download(path: Path = MODEL_PATH) -> Path:
    """Tải lama_fp32.onnx (bản đã ghim theo commit) vào `path`, kiểm cỡ và SHA-256 rồi mới đổi tên vào chỗ."""
    import urllib.request

    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(".part")
    digest = hashlib.sha256()
    with urllib.request.urlopen(MODEL_URL, timeout=60) as response, open(part, "wb") as out:
        while chunk := response.read(1 << 20):
            digest.update(chunk)
            out.write(chunk)
    if part.stat().st_size != MODEL_SIZE or digest.hexdigest() != MODEL_SHA256:
        part.unlink(missing_ok=True)
        raise InpaintUnavailable(f"tệp tải về sai cỡ hoặc SHA-256 ({digest.hexdigest()})")
    part.replace(path)
    return path


def main(argv=None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Mô hình LaMa tô vùng mù cho ảnh quanh xe")
    p.add_argument("cmd", choices=("download", "check"))
    args = p.parse_args(argv)
    try:
        if args.cmd == "download" and not MODEL_PATH.is_file():
            download()
        check_model(full_hash=True)
        inpainter = LamaInpainter()
        image = np.full((480, 480, 3), 120, np.uint8)
        mask = np.zeros((480, 480), bool)
        mask[200:280, 200:280] = True
        started = time.perf_counter()
        inpainter.fill(image, mask)
        print(f"LaMa sẵn sàng trên GPU: {MODEL_PATH} (lần đầu {time.perf_counter() - started:.1f} s)")
        return 0
    except InpaintUnavailable as exc:
        print(f"Không dùng được LaMa: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
