"""Tiêm lỗi có kiểm soát (T6, docs/KICH_BAN_NGHIEM_THU.md mục 7; thêm 02/10/2026): camera đứng hình, nguồn tư thế ngừng
cập nhật, vòng điều khiển treo. CHỈ dùng trong test và diễn tập trên MÔ PHỎNG (`autopark.evaluation.fault_drill`): bo mô
phỏng `SimVehicleIO`, cổng serial GIẢ, camera giả, bản ghi phát lại. Mã sản phẩm KHÔNG import module này, giao diện
không có nút tiêm lỗi, và không hàm nào ở đây mở cổng COM, LiDAR hay camera.

Mỗi lần gây lỗi và hết lỗi ghi một `FaultRecord` vào `FaultLog` (faults.csv). Cột = cột events.csv của `VehicleLink`
(`EVENT_FIELDS`, có `t_perf` của T13 và `call` của T9) thêm `t_rig` sau `t_io`, nên faults.csv nối được với events.csv
và ghép theo `t_io`. `t_rig`: giá trị THÔ của đồng hồ bàn thử `RIG_CLOCK` (perf_counter, cùng gốc với `t_perf`), KHÔNG
phải `t_rig_s` tương đối của dấu đồng bộ T14 (= t_perf − Rig.t_start). `t_perf`: perf_counter() lúc tạo dòng, có ở mọi
dòng (cả tư thế và treo), nên mọi lần gây lỗi đặt được lên trục t_perf/dấu đồng bộ T14. `call` luôn trống: dòng không do
một lần đọc io trả. (Cập nhật 02/10/2026 sau khi gộp T13, T9.)

- Camera (CB-2): `FreezeSwitch` là công tắc của một camera; `freezable_open_source` bọc `open_source` của
  `MultiCameraManager` (cài TRƯỚC khi dựng `Rig`, để `CameraTap` ghi đúng cái hệ thống thấy).
  STALL: `read()` không trả khung nào tới khi hết đóng băng (driver/USB treo, không có lần tới nào). Khung lẽ ra ra
  trong lúc đó bị mất như ở camera thật: nguồn phát lại (không mất mục nào khi không ai đọc) không được trả dồn chúng
  với stamp cũ sau khi hết đóng băng — lớp bọc bỏ và đếm chúng (`FreezeSwitch.skipped_after_stall`).
  REPEAT: driver trả lại bộ đệm trước. Với `UsbCameraSource`, `RepeatingCapture` trả lại đúng mảng ảnh cũ nên chính bộ
  dò khung cũ của nguồn bắt; với nguồn khác, lớp bọc ném `FrameReadError` chứa "previous frame", chữ mà
  `CameraWorker._count_error` đếm là khung cũ (`REPEAT_MESSAGE`; đổi chữ ở một chỗ thì phải đổi chỗ kia, có test ghim).
- Nguồn tư thế (CB-6): `FreezablePoseSource`. HOLD: giữ mẫu lấy lúc dừng với stamp CŨ; SILENT: `latest()` trả None.
  Không bao giờ đóng dấu lại dữ liệu cũ. `VehicleLink` bóc lớp bọc (`fault_inner`) để luật SimTruthPose vẫn áp dụng.
- Vòng điều khiển treo (CB-5 (b), L7 ở GIAI_DOAN_6_CHUAN_BI.md): `hang_control_loop`. `Session.advance` không được gọi
  và laptop không gửi gì, bo vẫn chạy; có hoặc không Heartbeat.

Phản ứng dự kiến (đo trên mô phỏng 01–02/10/2026; các giới hạn là kiểm của công cụ suy từ tham số hiện tại, KHÔNG phải
ngưỡng nghiệm thu đã chốt — N-T2, N-T4, N-P7 vẫn ĐỀ XUẤT – CHỜ CHỐT):

- Camera STALL hoặc REPEAT (`MultiCameraManager` với `RigConfig` mặc định): bộ ảnh bỏ camera đó (`FrameSet.lagging`)
  sau khoảng L_p (60–63 ms); `camera_stats` báo "stale" và camera vào `FrameSet.missing` sau 0,5 s (STALE_AFTER_S) cộng
  tuổi khung tốt cuối; các camera khác giữ nhịp; REPEAT được đếm là khung cũ (`duplicates`). Lớp AI camera
  (SourcePolicy 0,5 s) thành cũ: cảnh báo một lần mỗi lần chạy, hoặc dừng khi bật "AI bắt buộc"; vùng chỉ camera đó
  thấy thành UNKNOWN, không bao giờ FREE. Không có STALE_DATA: `FreshnessMonitor` mới nối cho LiDAR.
- Tư thế HOLD hoặc SILENT: STALE_POSE trong ≤ 0,175 s (HOLD) hoặc ≤ 0,025 s (SILENT); STOPPING, enable=0 mỗi 20 ms;
  kết thúc STOPPED + DISARM + WAIT_REPLAN. Không enable nào sau đó; tư thế có lại không đổi gì.
- Treo không Heartbeat (ứng dụng hiện nay): bo COMMAND_TIMEOUT → ARMED sau 0,15 s, LINK_TIMEOUT → DISARMED sau 0,5 s
  im lặng. Laptop không thấy gì trong lúc treo nên không có TELEMETRY_STALE. Tỉnh dậy: VEHICLE_STOPPED nếu treo dưới
  0,5 s, VEHICLE_NOT_ARMED nếu trên 0,5 s (gần 0,5 s thì tùy pha). Không enable nào sau đó.
- Treo có Heartbeat: bo chỉ COMMAND_TIMEOUT, telemetry vẫn mới; VEHICLE_STOPPED khi tỉnh dậy.
- TELEMETRY_STALE / STALE_TELEMETRY thuộc về mất telemetry trong lúc laptop vẫn chạy (CB-5 (a)): đã có
  `SimVehicleIO.set_link` và test của nó; module này không thêm cách tiêm lỗi nào cho trường hợp đó.

Ngoài phạm vi (ghi nhận, chưa có phản ứng an toàn): dữ liệu đứng yên mà stamp vẫn mới (định vị kẹt lặp tư thế với stamp
mới, ảnh đứng mà không trùng từng byte) — không có chế độ tiêm lỗi cho nó.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from enum import Enum
import math
from pathlib import Path
import threading
import time
from typing import TYPE_CHECKING, Callable, Mapping

from autopark.transport.loopback import FirmwareSerialLoopback
from autopark.transport.vehicle_io import Heartbeat, SerialVehicleIO, SimVehicleIO, VehicleIO
from autopark.video.multicam import RIG_CLOCK, CameraSpec
from autopark.video.sources import FrameReadError, UsbCameraSource

if TYPE_CHECKING:                                   # chỉ cho chú thích kiểu: Session nạp muộn trong hang_control_loop
    from autopark.application.session import Session
    from autopark.application.vehicle_link import PoseSample

# ---------------------------------------------------------------------------------------------------- log tiêm lỗi
# = vehicle_link.EVENT_FIELDS chèn "t_rig" sau "t_io" (viết thẳng ra để phần camera không phải nạp vehicle_link; test
# ghim hai danh sách khớp nhau). 02/10/2026: thêm t_perf (T13) và call (T9) như EVENT_FIELDS.
FAULT_FIELDS = ["t_session", "t_io", "t_rig", "t_perf", "source", "code", "action", "handling", "message", "call"]
FAULT_SOURCE = "fault_injection"
INJECTED = "fault_injected"
CLEARED = "fault_cleared"
FAULT_CAMERA_STALL = "FAULT_CAMERA_STALL"
FAULT_CAMERA_REPEAT = "FAULT_CAMERA_REPEAT"
FAULT_POSE_HOLD = "FAULT_POSE_HOLD"
FAULT_POSE_SILENT = "FAULT_POSE_SILENT"
FAULT_HANG = "FAULT_HANG"
FAULT_END = "FAULT_END"


def _blank(value):
    return "" if value is None else value


@dataclass(frozen=True)
class FaultRecord:
    """Một lần gây lỗi (`handling` "fault_injected") hoặc hết lỗi ("fault_cleared"). `t_io`: đồng hồ VehicleIO;
    `t_session` = t_io − t0 (`VehicleLink.session_time_now()`), như dòng VehicleIO và lớp nối của events.csv —
    commands.csv và (gần như mọi) dòng session_stop của events.csv (T13) mang thời gian thế giới của `Session`, sau một
    lần treo mô phỏng chậm hơn đúng thời lượng treo, nên ghép các tệp theo `t_io`; `t_rig`: đồng hồ bàn thử (camera);
    thời điểm không áp dụng thì None. `t_perf`: time.perf_counter() thô lúc tạo bản ghi (như cột t_perf của events.csv,
    T13)."""

    code: str
    handling: str
    message: str
    t_io: float | None = None
    t_session: float | None = None
    t_rig: float | None = None
    t_perf: float | None = field(default_factory=time.perf_counter)
    source: str = FAULT_SOURCE
    action: str = "LOG"

    def row(self) -> dict:
        """Dòng faults.csv (khóa đúng bằng FAULT_FIELDS): None thành chuỗi rỗng, t_session làm tròn 4 chữ số (như
        `VehicleLink._log_event`); `call` luôn trống (dòng không do một lần đọc io trả)."""
        return {"t_session": _blank(None if self.t_session is None else round(self.t_session, 4)),
                "t_io": _blank(self.t_io), "t_rig": _blank(self.t_rig), "t_perf": _blank(self.t_perf),
                "source": self.source, "code": self.code, "action": self.action, "handling": self.handling,
                "message": self.message, "call": ""}


class FaultLog:
    """Các `FaultRecord` theo thứ tự ghi; ghi được từ nhiều luồng (luồng camera, luồng phiên)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._records: list[FaultRecord] = []

    def add(self, record: FaultRecord) -> FaultRecord:
        with self._lock:
            self._records.append(record)
        return record

    @property
    def records(self) -> list[FaultRecord]:
        """Bản sao danh sách."""
        with self._lock:
            return list(self._records)

    def write_csv(self, path: str | Path) -> Path:
        """Ghi faults.csv (utf-8); luôn có dòng tiêu đề, kể cả khi chưa có lần tiêm lỗi nào."""
        path = Path(path)
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FAULT_FIELDS)
            writer.writeheader()
            writer.writerows(r.row() for r in self.records)
        return path


def _note(message: str, note: str) -> str:
    return f"{message}; {note}" if note else message


def _record(log: FaultLog | None, code: str, handling: str, message: str, *, t_io: float | None = None,
            t_session: float | None = None, t_rig: float | None = None) -> FaultRecord:
    record = FaultRecord(code, handling, message, t_io=t_io, t_session=t_session, t_rig=t_rig)
    if log is not None:
        log.add(record)
    return record


# ---------------------------------------------------------------------------------------------- camera đứng hình
REPEAT_MESSAGE = "driver returned the previous frame again (tiêm lỗi REPEAT)"
STALL_SLICE_S = 0.02        # bước chờ tối đa khi STALL: luồng camera bị yêu cầu dừng thì trả về trong ≤ 20 ms


class FreezeMode(str, Enum):
    STALL = "stall"         # read() không trả gì tới khi hết đóng băng (driver/USB treo, không có lần tới nào)
    REPEAT = "repeat"       # driver trả lại bộ đệm trước


class FreezeSwitch:
    """Công tắc đóng băng một camera (`target`, ví dụ "cam_p2"); dùng chung giữa luồng điều khiển và luồng camera.

    `max_stall_s` là giới hạn an toàn của CÔNG CỤ: một đợt STALL quá hạn đó tự hết (ghi FAULT_END "tự hết"), để quên
    `thaw()` không chặn luồng camera mãi. Luôn gọi `release()` trong `finally` TRƯỚC khi dừng luồng camera.

    `clock` phải cùng đồng hồ với stamp khung của nguồn (RIG_CLOCK): `drop_if_backlog` so stamp với lúc đóng băng và
    lúc hết."""

    def __init__(self, target: str, *, clock: Callable[[], float] = RIG_CLOCK, log: FaultLog | None = None,
                 max_stall_s: float = 10.0):
        if not math.isfinite(max_stall_s) or max_stall_s <= 0:
            raise ValueError("max_stall_s phải hữu hạn và > 0")
        self.target, self.clock, self.log, self.max_stall_s = target, clock, log, max_stall_s
        self._lock = threading.Lock()
        self._mode: FreezeMode | None = None
        self._released = False
        self._flowing = threading.Event()           # đặt khi KHÔNG ở STALL: read() đi tiếp
        self._flowing.set()
        self._stall_deadline: float | None = None   # time.perf_counter() hết hạn an toàn của đợt STALL hiện tại
        self._stall_start: float | None = None      # clock() lúc bắt đầu đợt STALL hiện tại (t_rig của dòng gây lỗi)
        self._stall_window: tuple[float, float] | None = None   # [bắt đầu; hết) của đợt STALL gần nhất đã hết
        self._skipped = 0                           # mục nguồn trả dồn sau STALL đã bị bỏ (`drop_if_backlog`)

    @property
    def mode(self) -> FreezeMode | None:
        with self._lock:
            return self._mode

    @property
    def released(self) -> bool:
        with self._lock:
            return self._released

    @property
    def skipped_after_stall(self) -> int:
        """Số mục (khung hay FrameReadError) lẽ ra ra trong một đợt STALL mà nguồn trả dồn sau khi hết đóng băng, đã bị
        bỏ (`drop_if_backlog`); cộng dồn suốt đời công tắc. Camera giả, camera USB: 0; bản ghi phát lại: ≈ thời lượng
        đóng băng / chu kỳ khung."""
        with self._lock:
            return self._skipped

    def freeze(self, mode: FreezeMode | str = FreezeMode.STALL, *, note: str = "") -> FaultRecord:
        mode = FreezeMode(mode)
        with self._lock:
            if self._released:
                raise RuntimeError(f"{self.target}: công tắc đã nhả, không đóng băng lại")
            if self._mode is not None:
                raise RuntimeError(f"{self.target}: đang đóng băng {self._mode.name}; gọi thaw() trước")
            t_rig = self.clock()
            self._mode = mode
            if mode is FreezeMode.STALL:
                self._stall_deadline = time.perf_counter() + self.max_stall_s
                self._stall_start = t_rig
                self._flowing.clear()
            what = "ngừng trả khung (STALL)" if mode is FreezeMode.STALL else "trả lại khung cũ (REPEAT)"
            return _record(self.log, f"FAULT_CAMERA_{mode.name}", INJECTED, _note(f"{self.target}: {what}", note),
                           t_rig=t_rig)

    def thaw(self, *, note: str = "") -> FaultRecord | None:
        """Hết đóng băng; không đang đóng băng thì không làm gì (trả None)."""
        with self._lock:
            return self._end(note)

    def release(self) -> None:
        """Hết đóng băng (nếu đang) và từ chối mọi lần đóng băng sau. Gọi trong `finally` trước khi dừng camera."""
        with self._lock:
            self._released = True
            self._end("nhả công tắc")

    def _end(self, note: str, message: str | None = None) -> FaultRecord | None:
        """Gọi trong `self._lock`. Hết STALL: nhớ đợt [lúc đóng băng; lúc hết) cho `drop_if_backlog`; lúc hết = t_rig
        của dòng FAULT_END, đọc TRƯỚC khi thả luồng camera."""
        mode = self._mode
        if mode is None:
            return None
        t_rig = self.clock()
        if mode is FreezeMode.STALL and self._stall_start is not None:
            self._stall_window = (self._stall_start, t_rig)
        self._mode = None
        self._stall_deadline = self._stall_start = None
        self._flowing.set()
        text = message or f"{self.target}: hết đóng băng {mode.name}"
        return _record(self.log, FAULT_END, CLEARED, _note(text, note), t_rig=t_rig)

    def drop_if_backlog(self, t: float | None) -> bool:
        """True (và đếm vào `skipped_after_stall`) khi mục có thời điểm `t` nằm trong đợt STALL gần nhất đã hết, tức
        lẽ ra ra trong lúc đứng hình. `FreezableFrameSource` gọi cho mọi mục nguồn bên trong (không phải USB) trả: nguồn
        phát lại (`ReplayCameraSource`: stamp = lịch của mục, không chờ khi lịch đã qua) không mất mục nào khi không ai
        đọc, nên ngay sau khi hết đóng băng nó trả dồn các mục đó với stamp cũ; camera thật đứng hình thì mất hẳn chúng.
        Chỉ bỏ mục TRONG đợt: đồng hồ của nguồn khác `clock` thì không bỏ gì (không vòng bỏ mãi). `t` None: không bỏ."""
        with self._lock:
            window = self._stall_window
            if t is None or window is None or not window[0] <= t < window[1]:
                return False
            self._skipped += 1
            return True

    def wait_while_stalled(self) -> None:
        """Gọi từ luồng camera trước mỗi lần đọc: chặn trong lúc STALL. Trả về khi hết đóng băng, khi nhả công tắc, khi
        luồng camera bị yêu cầu dừng (`stop_event` của `CameraWorker`, như `ReplaySession.should_stop`), hoặc khi đợt
        STALL quá `max_stall_s` — lúc đó tự hết và ghi FAULT_END."""
        worker_stop = getattr(threading.current_thread(), "stop_event", None)
        while True:
            with self._lock:
                if self._mode is not FreezeMode.STALL:
                    return
                remaining = self._stall_deadline - time.perf_counter()
                if remaining <= 0:
                    self._end("", f"{self.target}: hết đóng băng STALL, tự hết sau {self.max_stall_s:g} s (giới hạn "
                                  f"an toàn của công cụ)")
                    return
            if worker_stop is not None and worker_stop.is_set():
                return
            self._flowing.wait(min(remaining, STALL_SLICE_S))


class RepeatingCapture:
    """Bọc `cv2.VideoCapture` bên trong một `UsbCameraSource` (REPEAT ở mức driver).

    `read()` LUÔN đọc driver trước (giữ nhịp thật, bộ đệm driver không dồn). Đang REPEAT và đã có ảnh giữ thì trả
    (True, ảnh giữ) — đúng mảng cũ, nên chính `UsbCameraSource` ném "driver returned the previous frame again" và đếm
    `duplicates`. Không thì giữ ảnh mới và trả nó. Đóng băng trước khung đầu: khung đầu đi qua rồi mới bị lặp. Lỗi đọc
    thật của driver (False/None) không bị che. Mọi thuộc tính khác đi thẳng tới capture."""

    def __init__(self, capture, switch: FreezeSwitch):
        self.capture, self.switch = capture, switch
        self._held = None

    def read(self, *args, **kwargs):
        ok, image = self.capture.read(*args, **kwargs)
        if not ok or image is None:
            return ok, image
        if self.switch.mode is FreezeMode.REPEAT and self._held is not None:
            return True, self._held
        self._held = image
        return ok, image

    def __getattr__(self, name):
        capture = self.__dict__.get("capture")
        if capture is None:
            raise AttributeError(name)
        return getattr(capture, name)


class FreezableFrameSource:
    """Nguồn khung (hợp đồng `FrameSource`) có công tắc đóng băng.

    - `UsbCameraSource`: cài `RepeatingCapture` vào `inner.capture` (một lần); REPEAT do chính nguồn bắt.
    - Nguồn khác (camera giả, phát lại): REPEAT = vẫn đọc nguồn bên trong (giữ nhịp) rồi ném `FrameReadError` với
      `REPEAT_MESSAGE` và thời điểm của khung vừa đọc; khung đầu tiên đi qua như `RepeatingCapture`.
    - STALL: chặn ở `FreezeSwitch.wait_while_stalled()` trước khi đọc nguồn bên trong. Nguồn khác USB: sau khi hết
      đóng băng, mục (khung, `FrameReadError`) có thời điểm trong đợt STALL bị bỏ và đếm
      (`FreezeSwitch.drop_if_backlog`) thay vì trả dồn với stamp cũ — như camera thật, mất các khung lẽ ra chụp trong
      lúc đứng hình. Ngoại lệ khác (không có thời điểm) đi thẳng ra.
    `source_id` lấy của nguồn bên trong, không có thì là tên công tắc (FakeCamera của test không có `source_id`)."""

    def __init__(self, inner, switch: FreezeSwitch):
        self.inner, self.switch = inner, switch
        self.source_id = getattr(inner, "source_id", None) or switch.target
        self._delivered = False
        if isinstance(inner, UsbCameraSource) and not isinstance(inner.capture, RepeatingCapture):
            inner.capture = RepeatingCapture(inner.capture, switch)

    def read(self):
        if isinstance(self.inner, UsbCameraSource):
            self.switch.wait_while_stalled()
            return self.inner.read()
        while True:
            self.switch.wait_while_stalled()
            try:
                frame = self.inner.read()
            except FrameReadError as exc:
                if self.switch.drop_if_backlog(exc.t):
                    continue
                raise
            if frame is None:
                return None
            if not self.switch.drop_if_backlog(frame.meta.stamp.t):
                break
        if self.switch.mode is FreezeMode.REPEAT and self._delivered:
            raise FrameReadError(f"{self.source_id}: {REPEAT_MESSAGE}", frame.meta.stamp.t)
        self._delivered = True
        return frame

    def close(self):
        return self.inner.close()

    def __getattr__(self, name):
        inner = self.__dict__.get("inner")
        if inner is None:
            raise AttributeError(name)
        return getattr(inner, name)


def freezable_open_source(open_source: Callable[[CameraSpec], object],
                          switches: Mapping[int, FreezeSwitch]) -> Callable[[CameraSpec], object]:
    """Bọc `open_source` của `MultiCameraManager`: chỉ cổng có công tắc trong `switches` mới được bọc. Cài TRƯỚC khi
    dựng `Rig` (Rig bọc tiếp bằng `CameraTap`, nên bản ghi phiên chứa đúng cái hệ thống thấy)."""

    def open_freezable(spec: CameraSpec):
        source = open_source(spec)
        switch = switches.get(spec.port)
        return source if switch is None else FreezableFrameSource(source, switch)

    return open_freezable


# ----------------------------------------------------------------------------------------- nguồn tư thế ngừng
class PoseFault(str, Enum):
    HOLD = "hold"           # giữ mẫu lấy lúc dừng với stamp CŨ
    SILENT = "silent"       # latest() trả None


class FreezablePoseSource:
    """Bọc một `PoseSource` (hợp đồng của `application/vehicle_link.py`) với lỗi "nguồn ngừng cập nhật".

    `source_id` = id nguồn bên trong + "+fault", nên link.json và cột `pose_source` của commands.csv cho thấy có lớp
    tiêm lỗi. `available`/`reason` đi thẳng tới nguồn bên trong (bọc `NoPoseSource` vẫn bị từ chối START). Không bao
    giờ đóng dấu lại dữ liệu cũ: lỗi "đứng mà stamp vẫn mới" chưa có phản ứng an toàn nào nên không có chế độ cho nó.
    `clock` phải là đồng hồ của VehicleIO (`io.now`)."""

    def __init__(self, inner, *, clock: Callable[[], float], log: FaultLog | None = None):
        self.fault_inner = inner                    # VehicleLink bóc lớp này khi kiểm luật SimTruthPose
        self.source_id = f"{inner.source_id}+fault"
        self.simulated = inner.simulated
        self.clock, self.log = clock, log
        self._lock = threading.Lock()
        self._fault: PoseFault | None = None
        self._held: PoseSample | None = None

    @property
    def available(self) -> bool:
        return getattr(self.fault_inner, "available", True)

    @property
    def reason(self) -> str:
        # nguồn bên trong không có `reason`: AttributeError, nên getattr(…, mặc định) của VehicleLink vẫn đúng
        return self.fault_inner.reason

    @property
    def fault(self) -> PoseFault | None:
        with self._lock:
            return self._fault

    def latest(self) -> PoseSample | None:
        with self._lock:
            fault, held = self._fault, self._held
        if fault is None:
            return self.fault_inner.latest()
        return None if fault is PoseFault.SILENT else held

    def stop(self, mode: PoseFault | str = PoseFault.HOLD, *, t_session: float | None = None) -> FaultRecord:
        """Nguồn ngừng cập nhật từ bây giờ. HOLD: lấy `inner.latest()` lúc này và trả mãi mẫu đó (stamp cũ)."""
        mode = PoseFault(mode)
        t_io = self.clock()
        inner_id = self.fault_inner.source_id
        with self._lock:
            if self._fault is not None:
                raise RuntimeError(f"{self.source_id}: nguồn tư thế đang ngừng ({self._fault.name}); gọi resume() "
                                   f"trước")
            held = self.fault_inner.latest() if mode is PoseFault.HOLD else None
            self._fault, self._held = mode, held
        if mode is PoseFault.SILENT:
            message = f"nguồn tư thế {inner_id} ngừng trả mẫu (SILENT): latest() trả None"
        elif held is None:
            message = f"nguồn tư thế {inner_id} ngừng cập nhật (HOLD) khi chưa có mẫu nào: latest() trả None"
        else:
            message = (f"nguồn tư thế {inner_id} ngừng cập nhật (HOLD): giữ mẫu stamp t_io {held.t:.3f} s, không đóng "
                       f"dấu lại")
        return _record(self.log, f"FAULT_POSE_{mode.name}", INJECTED, message, t_io=t_io, t_session=t_session)

    def resume(self, *, t_session: float | None = None) -> FaultRecord | None:
        """Trả lại nguồn bên trong; không đang lỗi thì không làm gì (trả None)."""
        with self._lock:
            fault = self._fault
            if fault is None:
                return None
            self._fault, self._held = None, None
        return _record(self.log, FAULT_END, CLEARED,
                       f"nguồn tư thế {self.fault_inner.source_id}: hết {fault.name}, trả lại mẫu của nguồn",
                       t_io=self.clock(), t_session=t_session)


# ------------------------------------------------------------------------------------------ vòng điều khiển treo
@dataclass(frozen=True)
class HangResult:
    seconds: float                          # thời lượng xin treo
    heartbeat: bool
    phase: int                              # step_count % CONTROL_EVERY lúc bắt đầu treo
    t_io_start: float
    t_io_end: float
    t_session: float                        # io.now() − t0 lúc bắt đầu treo
    pings: int
    io_kind: str                            # "sim" | "loopback" | "wall_clock"
    board_state_at_end: str | None          # FirmwareModel (sim/loopback); None với đồng hồ tường (không đọc được bo)
    board_stop_reason_at_end: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def io_kind(io: VehicleIO) -> str:
    """"sim" (`SimVehicleIO`), "loopback" (`SerialVehicleIO` sau `FirmwareSerialLoopback` với `ManualClock`), còn lại
    "wall_clock" (bo ảo QEMU, cổng thật, cổng giả theo đồng hồ tường)."""
    if isinstance(io, SimVehicleIO):
        return "sim"
    if isinstance(io, SerialVehicleIO) and isinstance(io.transport, FirmwareSerialLoopback):
        return "loopback"
    return "wall_clock"


def _firmware(io: VehicleIO, kind: str):
    if kind == "sim":
        return io.firmware
    if kind == "loopback":
        return io.transport.firmware
    return None


def _align_phase(session: Session, io: VehicleIO, kind: str, phase: int) -> None:
    """Tiến phiên từng bước 5 ms tới khi `step_count % CONTROL_EVERY == phase` (như các test treo của
    tests/test_session_vehicle.py): bo mô phỏng `advance(PHYSICS_DT)`; cổng giả `loop.advance(5)` rồi `advance(0)`."""
    from autopark.application.session import SessionState

    for _ in range(4 * session.CONTROL_EVERY):
        if session.world.step_count % session.CONTROL_EVERY == phase:
            return
        if kind == "sim":
            session.advance(session.PHYSICS_DT)
        else:
            io.transport.advance(5)
            session.advance(0.0)
        if session.state != SessionState.RUNNING:
            raise RuntimeError(f"Lần chạy đã dừng ({session.state.value}: {session.stop_reason}) trong lúc căn pha")
    raise RuntimeError(f"Không căn được pha {phase} của nhịp điều khiển")


def _ping_if_silent(io: VehicleIO, period_s: float) -> int:
    if io.connected and io.now() - io.last_tx_time >= period_s:
        io.ping(wait=False)
        return 1
    return 0


def _hang_sim(io: SimVehicleIO, seconds: float, heartbeat: bool, ping_period_s: float) -> int:
    end = io.now() + seconds
    pings = 0
    if heartbeat:                           # như luồng Heartbeat: service() + PING, không lấy hàng đợi của poll()
        while io.now() < end - 1e-9:
            io.service()
            pings += _ping_if_silent(io, ping_period_s)
        return pings
    io.pause_host()                         # không ai đọc cổng: byte nằm trong bộ đệm, không kiểm TELEMETRY_STALE
    try:
        while io.now() < end - 1e-9:
            io.service()
    finally:
        io.resume_host()
    return pings


def _hang_loopback(io: SerialVehicleIO, seconds: float, heartbeat: bool, ping_period_s: float) -> int:
    loop: FirmwareSerialLoopback = io.transport
    remaining = max(1, round(seconds * 1000))
    if not heartbeat:
        loop.advance(remaining)             # bo chạy tiếp; laptop không đọc, không gửi gì
        return 0
    pings = 0
    while remaining > 0:
        step = min(10, remaining)
        loop.advance(step)
        remaining -= step
        io.service(block=False)
        pings += _ping_if_silent(io, ping_period_s)
    return pings


def _hang_wall_clock(io: VehicleIO, seconds: float, heartbeat: bool, ping_period_s: float) -> int:
    beat = Heartbeat(io, ping_period_s) if heartbeat else None
    if beat is not None:
        beat.start()
    try:
        time.sleep(seconds)                 # luồng gọi Session.advance ngủ thật
    finally:
        if beat is not None:
            beat.stop()
    return beat.pings if beat is not None else 0


def hang_control_loop(session: Session, seconds: float, *, heartbeat: bool = False, phase: int | None = None,
                      ping_period_s: float = 0.1, log: FaultLog | None = None) -> HangResult:
    """Treo vòng điều khiển `seconds` giây giữa lần chạy qua VehicleIO: `Session.advance` không được gọi, laptop không
    gửi lệnh nào, bo vẫn chạy. Xong thì người gọi tiếp tục gọi `session.advance(...)` như thường.

    - Bo mô phỏng (`SimVehicleIO`): có Heartbeat = vòng `service()` + PING khi im ≥ `ping_period_s` (như
      `heartbeat_only` của tests/test_session_vehicle.py); không Heartbeat = `pause_host()`, chạy bo bằng `service()`,
      rồi `resume_host()` đọc dồn byte, đóng dấu lúc đọc.
    - Cổng giả `FirmwareSerialLoopback` + `ManualClock`: có Heartbeat = từng 10 ms `loop.advance` +
      `service(block=False)` + PING; không Heartbeat = `loop.advance(ms)`, không ai đọc.
    - Còn lại (bo ảo QEMU, cổng thật, cổng giả theo đồng hồ tường): `Heartbeat` thật (tùy chọn) rồi `time.sleep`. PHẢI
      gọi từ chính luồng chạy `session.advance`. Không ép pha được (thời gian phiên bám `io.now()`).

    `phase` (0..CONTROL_EVERY−1, chỉ bo mô phỏng và cổng giả): tiến phiên từng bước 5 ms tới pha đó trước khi treo; pha
    0 = bước đầu tiên sau khi hết treo là nhịp điều khiển. Ghi FAULT_HANG và FAULT_END vào `log`.

    ValueError: `seconds` không hữu hạn hay ≤ 0, phiên không RUNNING qua VehicleIO, `phase` sai hoặc dùng với đồng hồ
    tường. RuntimeError: lần chạy dừng trong lúc căn pha."""
    from autopark.application.session import SessionState

    if (isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds)
            or seconds <= 0):
        raise ValueError("seconds phải hữu hạn và > 0")
    if not math.isfinite(ping_period_s) or ping_period_s <= 0:
        raise ValueError("ping_period_s phải hữu hạn và > 0")
    link = session.run_link
    if session.state != SessionState.RUNNING or link is None or link.io is None or session.world is None:
        raise ValueError("Chỉ treo vòng điều khiển khi phiên đang chạy qua VehicleIO")
    io = link.io
    kind = io_kind(io)
    every = session.CONTROL_EVERY
    if phase is not None:
        if kind == "wall_clock":
            raise ValueError("Không ép pha được với VehicleIO theo đồng hồ tường: thời gian phiên bám io.now()")
        if isinstance(phase, bool) or not isinstance(phase, int) or not 0 <= phase < every:
            raise ValueError(f"phase phải là số nguyên trong 0..{every - 1}")
        _align_phase(session, io, kind, phase)
    phase_now = session.world.step_count % every
    t_start, t_session = io.now(), link.session_time_now()
    _record(log, FAULT_HANG, INJECTED, f"treo vòng điều khiển {seconds:.3f} s, {'có' if heartbeat else 'không'} "
                                       f"Heartbeat, pha {phase_now}", t_io=t_start, t_session=t_session)
    if kind == "sim":
        pings = _hang_sim(io, seconds, heartbeat, ping_period_s)
    elif kind == "loopback":
        pings = _hang_loopback(io, seconds, heartbeat, ping_period_s)
    else:
        pings = _hang_wall_clock(io, seconds, heartbeat, ping_period_s)
    t_end = io.now()
    _record(log, FAULT_END, CLEARED, f"hết treo vòng điều khiển sau {t_end - t_start:.3f} s ({pings} PING)",
            t_io=t_end, t_session=link.session_time_now())
    firmware = _firmware(io, kind)
    return HangResult(seconds=float(seconds), heartbeat=bool(heartbeat), phase=phase_now, t_io_start=t_start,
                      t_io_end=t_end, t_session=t_session, pings=pings, io_kind=kind,
                      board_state_at_end=firmware.state.name if firmware is not None else None,
                      board_stop_reason_at_end=firmware.stop_reason.name if firmware is not None else None)


__all__ = ["FAULT_FIELDS", "FaultRecord", "FaultLog", "FreezeMode", "FreezeSwitch", "RepeatingCapture",
           "FreezableFrameSource", "freezable_open_source", "REPEAT_MESSAGE", "PoseFault", "FreezablePoseSource",
           "HangResult", "hang_control_loop", "io_kind"]
