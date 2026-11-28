"""Nhận một luồng quan sát camera và LiDAR từ Pi qua SSH."""
from __future__ import annotations

import base64
import io
import ipaddress
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, replace
from typing import BinaryIO, Literal
from zipfile import ZIP_DEFLATED, ZipFile

import cv2
import numpy as np

from autopark.domain.sensors import LidarScan, SourceStamp


_MAGIC = b"APW1\n"
_MAX_HEADER = 4096
_FOUR_CAMERAS = ("camera_1", "camera_2", "camera_3", "camera_4")
# Mode camera của luồng quan sát (fisheye_calib.LIVE_SIZE): 1280×720 dùng trọn chiều ngang cảm biến.
CAMERA_WIDTH, CAMERA_HEIGHT = 1280, 720
_PAYLOAD_LIMITS = {
    "start": 65536, "end": 65536, "lidar": 262144,
    **dict.fromkeys(("camera", *_FOUR_CAMERAS), 1048576),
}
_DRIVER_FILES = (
    "__init__.py",
    "power_throttling.py",
    "domain/__init__.py",
    "domain/sensors.py",
    "domain/types.py",
    "lidar/__init__.py",
    "lidar/rplidar_c1.py",
    "lidar/rplidar_protocol.py",
)
_DNS_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_USER = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}")

RemoteViewStatus = Literal["connecting", "live", "ended", "error", "stopped"]


@dataclass(frozen=True)
class RemoteCameraSample:
    frame: np.ndarray
    seq: int
    at: float


@dataclass(frozen=True)
class RemoteViewSnapshot:
    status: RemoteViewStatus = "stopped"
    detail: str = ""
    frame: np.ndarray | None = None
    frame_seq: int | None = None
    frame_at: float | None = None
    scan: LidarScan | None = None
    scan_seq: int | None = None
    scan_at: float | None = None
    cameras: tuple[RemoteCameraSample | None, ...] = (None,)
    # tư thế cảm biến LiDAR (x, y, góc) trong hệ odometry khớp scan (29/11/2026, cho ảnh nhớ mặt sàn); None khi chưa có
    # hoặc odometry mất dấu (vòng đó không khớp được)
    lidar_pose: tuple[float, float, float] | None = None
    lidar_pose_epoch: int = 0             # tăng mỗi lần odometry khởi động lại: ảnh nhớ cũ không còn cùng hệ


def _host_name(value: str) -> str:
    if not isinstance(value, str) or not value or "%" in value:
        raise ValueError("Địa chỉ hoặc tên máy SSH không hợp lệ")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        name = value.removesuffix(".")
        if len(name) > 253 or not all(_DNS_LABEL.fullmatch(label) for label in name.split(".")):
            raise ValueError("Địa chỉ hoặc tên máy SSH không hợp lệ") from None
    return value


def _camera_kinds(camera_count: int) -> tuple[str, ...]:
    if type(camera_count) is not int or camera_count not in (1, 4):
        raise ValueError("Số camera phải là 1 hoặc 4")
    return ("camera",) if camera_count == 1 else _FOUR_CAMERAS


def _sender_source(duration_s: float, camera_count: int = 1, check_esp32: bool = True) -> bytes:
    camera_count = len(_camera_kinds(camera_count))
    package = Path(__file__).resolve().parents[1]
    with io.BytesIO() as archive:
        with ZipFile(archive, "w", compression=ZIP_DEFLATED) as driver:
            for path in _DRIVER_FILES:
                driver.write(package / path, f"autopark/{path}")
        encoded = base64.b64encode(archive.getvalue()).decode("ascii")
    prefix = (
        f"LIDAR_PACKAGE = {encoded!r}\n"
        f"VIEW_DURATION = {duration_s!r}\n"
        f"VIEW_CAMERA_COUNT = {camera_count}\n"
        f"VIEW_CHECK_ESP32 = {bool(check_esp32)!r}\n"
    )
    return prefix.encode("ascii") + Path(__file__).with_name("remote_view_sender.py").read_bytes()


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Khóa JSON lặp: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"Hằng JSON không hợp lệ: {value}")


def _object(payload: bytes) -> dict:
    data = json.loads(
        payload.decode("utf-8"), object_pairs_hook=_unique_keys, parse_constant=_invalid_constant,
    )
    if not isinstance(data, dict):
        raise ValueError("Mẫu JSON phải là một đối tượng")
    return data


def _read_packet(stream: BinaryIO) -> tuple[str, dict, bytes]:
    line = stream.readline(_MAX_HEADER + 1)
    if not line:
        raise ValueError("Luồng SSH đóng trước gói kết thúc")
    if len(line) > _MAX_HEADER or not line.endswith(b"\n") or not line.isascii():
        raise ValueError("Dòng tiêu đề APW1 không hợp lệ")
    header = _object(line)
    kind, size = header.get("kind"), header.get("nbytes")
    if not isinstance(kind, str) or kind not in _PAYLOAD_LIMITS:
        raise ValueError("Loại gói APW1 không hợp lệ")
    if type(size) is not int or not 1 <= size <= _PAYLOAD_LIMITS[kind]:
        raise ValueError(f"Kích thước gói {kind} không hợp lệ")
    payload = stream.read(size)
    if len(payload) != size:
        raise ValueError(f"Gói {kind} bị cắt")
    return kind, header, payload


def _decode_frame(payload: bytes) -> np.ndarray:
    if not payload.startswith(b"\xff\xd8") or not payload.endswith(b"\xff\xd9"):
        raise ValueError("Gói camera không phải JPEG hoàn chỉnh")
    image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.shape != (CAMERA_HEIGHT, CAMERA_WIDTH, 3) or image.dtype != np.uint8:
        raise ValueError(f"Ảnh camera không giải mã được thành BGR {CAMERA_WIDTH}×{CAMERA_HEIGHT}")
    image.setflags(write=False)
    return image


def _decode_scan(payload: bytes, received_at: float) -> LidarScan:
    data = _object(payload)
    angles, ranges = data.get("angles_rad"), data.get("ranges_m")
    if not isinstance(angles, list) or not angles or not isinstance(ranges, list):
        raise ValueError("Gói LiDAR thiếu mảng góc hoặc cự ly")
    if any(type(angle) not in (int, float) for angle in angles):
        raise ValueError("Góc LiDAR không hợp lệ")
    if any(distance is not None and type(distance) not in (int, float) for distance in ranges):
        raise ValueError("Cự ly LiDAR không hợp lệ")
    stamp = SourceStamp("pi_lidar", received_at, frame_id="lidar")
    return LidarScan(stamp, tuple(angles), tuple(math.nan if r is None else r for r in ranges))


def _check_end(payload: bytes, counts: dict[str, int]) -> None:
    end = _object(payload)
    errors = end.get("errors")
    if not isinstance(errors, list) or any(not isinstance(error, str) for error in errors):
        raise ValueError("Gói kết thúc thiếu trạng thái lỗi của Pi")
    sent = end.get("sent")
    if not isinstance(sent, dict) or sent.keys() != counts.keys() or any(
        type(sent.get(kind)) is not int or sent[kind] != count for kind, count in counts.items()
    ):
        raise ValueError("Số mẫu Pi đã gửi và Windows nhận được không khớp")
    if end.get("ok") is not True or errors:
        raise ValueError(" · ".join(errors) or "Pi báo phiên quan sát thất bại")
    if not all(counts.values()):
        raise ValueError("Phiên kết thúc khi còn nguồn chưa có mẫu")


def _terminate(process: subprocess.Popen | None) -> None:
    if process is not None and process.poll() is None:
        try:
            process.terminate()
        except ProcessLookupError:
            pass


class RemoteSensorLink:
    """Một phiên quan sát, giữ mẫu mới nhất của từng camera và LiDAR."""

    def __init__(self, host: str, *, user: str = "xe", host_key_alias: str = "10.12.194.1",
                 duration_s: float = 180.0, camera_count: int = 1, check_esp32: bool = True):
        self.host = _host_name(host)
        self.host_key_alias = _host_name(host_key_alias)
        if not isinstance(user, str) or not _USER.fullmatch(user):
            raise ValueError("Tên đăng nhập SSH không hợp lệ")
        self.user = user
        if type(duration_s) not in (int, float) or not math.isfinite(duration_s) or duration_s <= 0:
            raise ValueError("Thời lượng quan sát phải là số giây dương")
        self.duration_s = float(duration_s)
        self.check_esp32 = bool(check_esp32)     # False: Pi không mở cổng ESP32 (app; tab Kết nối xe đang giữ cổng)
        self._camera_indices = {kind: index for index, kind in enumerate(_camera_kinds(camera_count))}
        self.camera_count = camera_count
        self._empty_cameras = (None,) * camera_count
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen | None = None
        self._snapshot = RemoteViewSnapshot(cameras=self._empty_cameras)
        self._recorder = None              # ScanRecorder khi đang ghi LiDAR (thêm 26/11/2026)
        self._camera_dir: Path | None = None   # thư mục ảnh khi ghi kèm camera (29/11/2026)
        self._camera_count_saved = 0
        self._odometry = None                  # ScanOdometry chạy trên luồng nhận, mỗi vòng ≈ 7 ms
        self._odometry_epoch = 0
        self._odometry_failures = 0

    # ---- ghi LiDAR: mọi vòng nhận được, kể cả vòng giao diện không kịp vẽ ---------------------------------------
    def start_lidar_recording(self, path, meta: dict | None = None, *, cameras: bool = False) -> Path:
        """Ghi mọi vòng C1 nhận từ lúc này vào `<path>.npz` theo định dạng `lidar/recording.py`, để `lidar/occupancy.py`,
        `lidar/map_builder.py` và `planning/slot_finder.py` đọc được. Dấu thời gian là đồng hồ Pi (giây), không phải
        lúc laptop nhận, nên không mang độ giật của Wi-Fi.

        `cameras=True` (29/11/2026, cho ảnh nhớ mặt sàn khi xe chạy): mọi khung JPEG nhận được ghi nguyên byte vào
        `<path>_cam/cam_p<N>/<t_ns đồng hồ Pi>.jpg`, cùng đồng hồ với các vòng quét."""
        from autopark.lidar.recording import ScanRecorder, default_meta

        with self._lock:
            if self._recorder is not None:
                raise RuntimeError("Đang ghi LiDAR")
            info = default_meta("pi_lidar", device="RPLIDAR C1", port=f"ssh://{self.user}@{self.host}",
                                mirror=False, clock="pi_monotonic_s", **(meta or {}))
            self._recorder = ScanRecorder(path, info)
            self._camera_count_saved = 0
            if cameras:
                self._camera_dir = Path(str(path) + "_cam")
                for index in range(1, len(self._camera_indices) + 1):
                    (self._camera_dir / f"cam_p{index}").mkdir(parents=True, exist_ok=True)
            return self._recorder.path

    def stop_lidar_recording(self) -> tuple[Path, int] | None:
        """Dừng ghi và ghi tệp. Trả (đường dẫn .npz, số vòng); không đang ghi thì trả None."""
        with self._lock:
            recorder, self._recorder = self._recorder, None
            self._camera_dir = None
        if recorder is None:
            return None
        return recorder.close(), len(recorder)

    def lidar_recording_count(self) -> int | None:
        with self._lock:
            return None if self._recorder is None else len(self._recorder)

    def _odometry_step(self, scan: LidarScan, pi_stamp_ns: int):
        """Odometry khớp scan cho ảnh nhớ mặt sàn. FAILED 5 vòng liền thì khởi động lại (hệ mới, `epoch` tăng)."""
        try:
            if self._odometry is None:
                from autopark.lidar.scan_odometry import ScanOdometry
                self._odometry = ScanOdometry()
                self._odometry_epoch += 1
                self._odometry_failures = 0
            step = self._odometry.update(np.asarray(scan.angles_rad, np.float64),
                                         np.asarray(scan.ranges_m, np.float64), pi_stamp_ns * 1e-9)
        except Exception:  # noqa: BLE001 - odometry chỉ phục vụ hiển thị, lỗi thì bỏ ảnh nhớ, không cắt luồng
            self._odometry = None
            return None, self._odometry_epoch
        if step.status == "FAILED":
            self._odometry_failures += 1
            if self._odometry_failures >= 5:
                self._odometry = None
            return None, self._odometry_epoch
        self._odometry_failures = 0
        return (float(step.x), float(step.y), float(step.theta)), self._odometry_epoch

    def camera_recording_count(self) -> int | None:
        with self._lock:
            return None if self._camera_dir is None else self._camera_count_saved

    def _record_camera(self, kind: str, payload: bytes, pi_stamp_ns: int) -> None:
        with self._lock:
            directory = self._camera_dir
        if directory is None:
            return
        index = self._camera_indices[kind] + 1
        try:
            (directory / f"cam_p{index}" / f"{pi_stamp_ns}.jpg").write_bytes(payload)
        except OSError:
            return
        with self._lock:
            self._camera_count_saved += 1

    def _record_scan(self, scan: LidarScan, pi_stamp_ns: int) -> None:
        with self._lock:
            if self._recorder is None:
                return
            t = pi_stamp_ns * 1e-9
            self._recorder.add(LidarScan(SourceStamp("pi_lidar", t, frame_id="lidar"), scan.angles_rad, scan.ranges_m))

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._cancel.clear()
            self._snapshot = RemoteViewSnapshot(
                "connecting", f"Đang kết nối {self.host}", cameras=self._empty_cameras,
            )
            self._thread = threading.Thread(target=self._run, name="autopark-pi-view", daemon=True)
            self._thread.start()

    def snapshot(self) -> RemoteViewSnapshot:
        with self._lock:
            return self._snapshot

    def close(self) -> None:
        with self._lock:
            self._cancel.set()
            self._snapshot = RemoteViewSnapshot(
                "stopped", "Đã ngắt quan sát", cameras=self._empty_cameras,
            )
            process, thread = self._process, self._thread
        _terminate(process)
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        self.stop_lidar_recording()            # còn đang ghi thì vẫn ghi tệp, không bỏ dữ liệu

    def _update(self, **fields) -> None:
        with self._lock:
            if not self._cancel.is_set():
                self._snapshot = replace(self._snapshot, **fields)

    def _update_camera(self, index: int, sample: RemoteCameraSample) -> None:
        with self._lock:
            if self._cancel.is_set():
                return
            cameras = list(self._snapshot.cameras)
            cameras[index] = sample
            legacy = {} if index else {"frame": sample.frame, "frame_seq": sample.seq, "frame_at": sample.at}
            self._snapshot = replace(self._snapshot, status="live", detail="Đang nhận dữ liệu từ Pi",
                                     cameras=tuple(cameras), **legacy)

    def _read(self, stream: BinaryIO) -> None:
        if stream.read(len(_MAGIC)) != _MAGIC:
            raise ValueError("Không nhận được lời chào APW1 từ Pi. Kiểm tra thông báo SSH trên terminal.")
        kind, _, payload = _read_packet(stream)
        if kind != "start":
            raise ValueError("Luồng APW1 chưa gửi gói bắt đầu")
        _object(payload)
        counts = dict.fromkeys((*self._camera_indices, "lidar"), 0)
        last_seq = dict.fromkeys(counts, 0)
        last_stamp = dict.fromkeys(counts, 0)
        while not self._cancel.is_set():
            kind, header, payload = _read_packet(stream)
            received_at = time.monotonic()
            if kind == "end":
                _check_end(payload, counts)
                return
            if kind == "start":
                raise ValueError("Luồng APW1 gửi lặp gói bắt đầu")
            if kind not in counts:
                raise ValueError(f"Nguồn {kind} không thuộc phiên quan sát này")
            seq, stamp, send = header.get("seq"), header.get("t_ns"), header.get("tx_ns")
            if type(seq) is not int or seq <= last_seq[kind]:
                raise ValueError(f"Số thứ tự {kind} lặp hoặc đi lùi")
            if type(stamp) is not int or type(send) is not int or not last_stamp[kind] <= stamp <= send:
                raise ValueError(f"Dấu thời gian từ Pi của {kind} không hợp lệ")
            last_seq[kind], last_stamp[kind] = seq, stamp
            counts[kind] += 1
            if kind == "lidar":
                scan = _decode_scan(payload, received_at)
                self._record_scan(scan, stamp)
                pose, epoch = self._odometry_step(scan, stamp)
                self._update(status="live", detail="Đang nhận dữ liệu từ Pi",
                             scan=scan, scan_seq=seq, scan_at=received_at, lidar_pose=pose, lidar_pose_epoch=epoch)
            else:
                self._record_camera(kind, payload, stamp)
                self._update_camera(self._camera_indices[kind],
                                    RemoteCameraSample(_decode_frame(payload), seq, received_at))

    def _run(self) -> None:
        command = [
            "ssh", "-T", "-o", f"HostKeyAlias={self.host_key_alias}",
            "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=8",
            "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=2",
            f"{self.user}@{self.host}", "python3", "-u", "-",
        ]
        process = None
        try:
            with tempfile.TemporaryFile() as sender:
                sender.write(_sender_source(self.duration_s, self.camera_count, self.check_esp32))
                sender.seek(0)
                with self._lock:
                    if self._cancel.is_set():
                        return
                    process = subprocess.Popen(command, stdin=sender, stdout=subprocess.PIPE)
                    self._process = process
                self._read(process.stdout)
                if self._cancel.is_set():
                    return
                if process.wait(timeout=5.0):
                    raise ValueError("Tiến trình SSH kết thúc với lỗi")
                if process.stdout.read(1):
                    raise ValueError("Có dữ liệu sau gói kết thúc")
                self._update(status="ended", detail="Pi đã kết thúc phiên quan sát")
        except (OSError, ValueError, OverflowError, RecursionError, subprocess.SubprocessError, cv2.error) as exc:
            self._update(status="error", detail=" ".join(str(exc).split())[:360])
        finally:
            if process is not None:
                _terminate(process)
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                finally:
                    process.stdout.close()
            with self._lock:
                self._process = None
