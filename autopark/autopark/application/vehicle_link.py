"""Nối phiên đỗ xe (`Session`) với `VehicleIO`: ba chế độ chạy (kế hoạch mục 9 — giai đoạn 5 và giai đoạn 9).

- ``SIM`` (mặc định): KHÔNG dùng lớp này. `Session` chạy `SimWorld` + `SimFeedback` y như giai đoạn 0.
- ``VEHICLE_IO``: vòng kín đi qua `VehicleIO`. Mỗi nhịp điều khiển (50 Hz), bộ bám quỹ đạo tính (tốc độ, góc lái)
  theo đúng đơn vị của API `VehicleIO` (m/s có dấu, rad) và lớp này gửi một COMMAND có thời hạn. Mọi sự kiện dừng
  của `VehicleIO` (TELEMETRY_STALE, SESSION_LOST, VEHICLE_FAULT, FIRMWARE_RESET, LINK_ERROR...) làm `Session` dừng
  an toàn. Sau khi đã dừng, lần chạy này KHÔNG BAO GIỜ gửi lại lệnh enable: telemetry có lại hay kết nối lại cũng
  không chạy tiếp; muốn chạy phải lập lại đường rồi bấm Bắt đầu đỗ, lúc đó `begin_run()` mới `arm()` lại.
- ``OBSERVE`` (chế độ quan sát, kế hoạch giai đoạn 9): người lái cầm lái. Phần mềm vẫn lập đường, tính lệnh bám
  quỹ đạo mỗi nhịp và GHI LOG (commands.csv, telemetry.csv) nhưng KHÔNG gửi COMMAND nào — kể cả COMMAND enable=0.
  Bo phải ở DISARMED trong suốt lần quan sát; thấy bo ARMED/RUNNING thì gửi DISARM và kết thúc quan sát.

Cái gì ĐO, cái gì MÔ PHỎNG (ghi 24/09/2026 — chưa có ESP32-S3, chưa có MN300):

- tốc độ, góc lái: telemetry `VehicleIO`. Trên bo thật là encoder/AS5600 — CHƯA CÓ MÃ ĐỌC; ở nhánh mô phỏng là
  cảm biến giả có trễ và nhiễu trong `SimVehicleIO` (số giả định).
- tư thế x, y, hướng: `PoseSource` được tiêm vào. Hiện CHỈ có `SimTruthPose` = tư thế THẬT của xe trong
  `SimVehicleIO` (định vị lý tưởng, MÔ PHỎNG). Chưa có định vị LiDAR nào.
- va chạm: kiểm hình học tư thế ước lượng với vật cản đã biết của sa bàn; không phải cảm biến va chạm.

Đồng hồ: `PoseSource` phải đóng dấu bằng CÙNG đồng hồ với `VehicleIO.now()`. Thời gian phiên t (của `Session`)
ứng với `io.now() = t0 + t`, t0 lấy lúc `begin_run()` xong. Với `SimVehicleIO`, lớp này tiến đồng hồ mô phỏng của
bo theo thời gian phiên (xác định hoàn toàn, dùng trong test). Với VehicleIO chạy theo thời gian thực (`realtime`,
ví dụ `SerialVehicleIO`), `Session.advance()` không cộng thời gian giao diện và không tua nhanh: nó lấy t theo
`session_time_now()` = `io.now() - t0`, và mỗi bước chỉ đọc byte đã có sẵn (`poll(block=False)`), không chờ timeout
đọc của cổng. Nhờ vậy nhịp điều khiển 50 Hz, hạn xác nhận dừng, MAX_RUN_TIME và cột t_session của mọi log cùng bám
`io.now()` (sai khác ≤ một bước 5 ms). Điều này mới kiểm với cổng serial GIẢ (FirmwareModel sau cổng giả, đồng hồ
tường), CHƯA kiểm với bo thật (24/09/2026).

Trước START (`begin_run`) lớp này kiểm lại trạng thái THẬT: có phiên và telemetry mới, bo không FAULT, không nhấn
E-stop, có tốc độ và góc lái đo được, xe đứng yên, có tư thế mới, tư thế gần điểm xuất phát đã lập đường và không
chạm vật cản. Sai một điều là từ chối START. Sau ARM/DISARM tư thế được đọc và kiểm lại; lỗi ở bất kỳ bước nào sau
khi đã gửi ARM thì gửi DISARM trước khi báo lỗi. Lần START bị từ chối không xóa log của lần chạy trước: các dòng của
nó được nối vào `start_refusals`.

Hành vi trên bo thật CHƯA KIỂM: mọi test hiện nay chạy qua `SimVehicleIO` + `FirmwareModel` (bản tham chiếu Python).

Thêm 24/09/2026 (chỉ kiểm với bo mô phỏng và cổng serial GIẢ `FirmwareSerialLoopback`, CHƯA THỬ với ESP32-S3):

- Giới hạn: trước START lớp nối so giới hạn bo báo trong HELLO_ACK với `VehicleConfig` của planner
  (`VehicleIO.check_limits`). Lệch thì ghi dòng `LIMITS_MISMATCH`. Ở VEHICLE_IO, lệch theo hướng nguy hiểm (bo cho
  phép nhanh hơn/lái gắt hơn/đổi lái hay tăng tốc nhanh hơn, phanh yếu hơn, hoặc góc lái nhỏ hơn đường đã lập cần)
  thì từ chối START; bo chỉ chặt hơn thì cảnh báo và vẫn chạy. Ở OBSERVE chỉ ghi, vì không gửi lệnh nào.
- Bo thật: `VehicleLink.serial_port(mode, "COMx")` tạo `SerialVehicleIO.deferred` (chưa mở cổng) với `NoPoseSource`.
  Khi chưa có nguồn tư thế thật, START bị từ chối ngay đầu `begin_run`, trước khi mở cổng hay gửi byte nào.
  `SimTruthPose` chỉ nhận `SimVehicleIO` của chính liên kết: ghép nó với bo thật (kể cả `SimTruthPose` dựng quanh
  chính bo serial) bị từ chối ngay khi tạo liên kết.
- `probe_board()`: "Kiểm kết nối bo" của giao diện. HELLO, đọc vài khung telemetry, so giới hạn, đóng cổng. Không
  bao giờ ARM, không gửi COMMAND.

Thêm 02/10/2026 (T13, sự kiện dừng của phiên trong log; chỉ kiểm với bo mô phỏng và cổng serial GIẢ, CHƯA THỬ với bo
ảo QEMU hay ESP32-S3 qua `Session`):

- events.csv ghi cả quyết định dừng của PHIÊN: mỗi quyết định là một dòng `handling` = ``session_stop``
  (`log_session_event`, do `Session` gọi). Các dòng session_stop là đúng `Session.safety_events` (cùng thứ tự, mã,
  nguồn, t_session, action), cộng mọi yêu cầu dừng khi đang chạy (USER_STOP, FUSED_MAP_INVALID, mã của ngăn LiDAR và
  ngăn AI camera), USER_RESET và COLLISION. Sự kiện của bo hay của lớp nối vì vậy có HAI dòng: `stop` lúc lớp nối
  nhận, `session_stop` lúc phiên quyết định; người đọc lọc theo `handling`. Lý do dừng đầu tiên của lần chạy là dòng
  session_stop đầu tiên có action STOP.
- Mọi dòng events.csv và start_refusals.csv có cột `t_perf` = `time.perf_counter()` THÔ của laptop lúc ghi dòng (QPC
  trên Windows, cùng gốc với `RIG_CLOCK` của bản ghi rig, so được giữa các tiến trình). Với dòng sự kiện của VehicleIO
  đó là lúc lớp nối gom sự kiện, không phải lúc bo phát.
- link.json có khóa ``clock`` = {"t_io_at_start", "t_perf_at_start"}: io.now() và perf_counter() đọc liền nhau lúc mở
  lần chạy (cả hai null khi chưa mở lần nào). Bo thật với đồng hồ mặc định của `SerialVehicleIO` (perf_counter() − t0
  của io): t_perf = t_io + (t_perf_at_start − t_io_at_start), áp cho cả commands.csv và telemetry.csv. Bo mô phỏng:
  t_io là đồng hồ mô phỏng (nhịp 10 ms, chạy trước thời gian phiên tới 5 ms), phép đổi không áp dụng.

Thêm 02/10/2026 (T15, nút "Xóa lỗi bo (CLEAR_FAULT)"; chỉ thử với bo mô phỏng và cổng serial GIẢ, CHƯA THỬ với
ESP32-S3):

- `clear_fault()`: xóa lỗi bo trên VehicleIO của CHÍNH liên kết, chỉ khi không có lần chạy nào đang mở. Quyết định
  theo khung telemetry đầu tiên bo gửi sau lúc bấm: bo không FAULT, hoặc cờ ESTOP_INPUT = 1, thì không gửi CLEAR_FAULT;
  còn lại gửi đúng một REQUEST CLEAR_FAULT (firmware tự kiểm lại). Không bao giờ ARM, không COMMAND nào. Cổng serial
  chưa mở (`SerialVehicleIO.deferred`) thì mở rồi đóng lại khi xong. *(Sửa sau review 02/10/2026: dùng lại phiên đang
  có thì trước khi đọc trạng thái gửi một PING và chờ ACK, làm rào "khung mới"; trước đó khung cũ tồn đọng trong cổng
  có thể thành căn cứ quyết định.)*
- Mỗi lần bấm là một dòng board_actions.csv (`board_actions`, cộng dồn suốt đời liên kết như `start_refusals`), kể cả
  lần không gửi gì. Ba mốc của dòng (t_io, t_perf, wall_time) đọc liền nhau lúc quyết định gửi hay không gửi.
  *(Sau review 02/10/2026: cột message ghi đủ sự kiện VehicleIO gom được (mã, action, t_io, lời); bốn cột hello_* nối
  cuối giữ HELLO_ACK của lần bấm.)*

Thêm 02/10/2026 (T9, băng để phát lại log; chỉ kiểm với bo mô phỏng và cổng serial GIẢ, CHƯA THỬ với bo thật):

- Lớp nối ghi thêm ĐẦU VÀO của lần chạy, đủ để chạy lại cùng phần mềm trên đúng các đầu vào đó
  (`application/vehicle_replay.py`, `storage/run_store.py` `replay_vehicle_run`). Mỗi lần đọc io trong lần chạy
  (`refresh` đầu bước khi đang chạy, `pump` cuối bước) là một dòng clock.csv: số lần đọc `call`, loại, t_session và
  io.now() SAU lần đọc. Khung telemetry và sự kiện VehicleIO mà lần đọc đó trả mang cùng số ở cột `call`. Mỗi lần đọc
  nguồn tư thế trong lần chạy (`estimate`, `observe`) là một dòng poses.csv: mẫu (hoặc không có mẫu) và io.now() đọc
  liền sau mẫu. link.json có thêm `run_start` (t_io0 và trạng thái đầu của thế giới gương), `log_format` (= 2) và, qua
  `describe()`, `io_source_id`.
- Chỉ ghi: không quyết định nào của lớp nối đổi, không gửi gì thêm tới bo. Tư thế đọc trong `_open_run` (kiểm START)
  không ghi, vì phát lại không chạy lại bước START.
"""
from __future__ import annotations

import csv
import inspect
import json
import math
import time
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Protocol

from autopark.control.tracker import TrackerOutput
from autopark.domain.sensors import SafetyEvent, SourceStamp
from autopark.domain.types import Pose, Scenario, VehicleConfig, VehicleState, clamp, wrap_angle
from autopark.geometry.footprint import check_motion, check_pose
from autopark.simulation.world import SimWorld, StepResult
from autopark.transport.protocol import Fault, ResetReason, Result, State, TelemetryFlag
from autopark.transport.vehicle_io import (HelloInfo, LimitsCheck, SerialVehicleIO, SimIOConfig, SimVehicleIO,
                                           VehicleIO, VehicleIOError, VehicleTelemetry)


class DriveMode(str, Enum):
    SIM = "SIM"
    VEHICLE_IO = "VEHICLE_IO"
    OBSERVE = "OBSERVE"

    @property
    def label(self) -> str:
        return {
            "SIM": "Mô phỏng giai đoạn 0 (mặc định)",
            "VEHICLE_IO": "VehicleIO: gửi lệnh tới bo",
            "OBSERVE": "Quan sát: tính lệnh, KHÔNG gửi ra xe",
        }[self.value]


class VehicleLinkError(RuntimeError):
    """Không bắt đầu được lần chạy qua VehicleIO (trạng thái thật không đạt điều kiện START)."""


@dataclass(frozen=True)
class PoseSample:
    pose: Pose
    t: float              # đồng hồ của VehicleIO (io.now())
    source_id: str
    simulated: bool       # True: tư thế lấy từ mô phỏng, không phải từ cảm biến/định vị


class PoseSource(Protocol):
    source_id: str
    simulated: bool

    def latest(self) -> PoseSample | None:
        """Tư thế mới nhất (đồng hồ của VehicleIO), hoặc None khi chưa có."""


class SimTruthPose:
    """MÔ PHỎNG: tư thế THẬT của xe trong `SimVehicleIO` — định vị lý tưởng, không nhiễu, không trễ.

    Chỉ để thử chuỗi Session → VehicleIO → FirmwareModel khi chưa có định vị LiDAR. Kết quả bám đường dùng nguồn
    này KHÔNG nói gì về độ chính xác định vị thật."""

    source_id = "sim_truth_pose"
    simulated = True

    def __init__(self, io: SimVehicleIO):
        self.io = io

    def latest(self) -> PoseSample | None:
        return PoseSample(self.io.truth.pose, self.io.now(), self.source_id, True)


MAX_POSE_WRAPPERS = 8          # số lớp bọc tiêm lỗi (`fault_inner`) tối đa quanh một nguồn tư thế


def unwrap_pose_source(source):
    """Nguồn tư thế trong cùng, dưới các lớp bọc tiêm lỗi (`fault_inner`, safety/fault_injection.py, 02/10/2026).

    Chỉ đọc thuộc tính THẬT của đối tượng hay của lớp (kể cả property) qua `inspect.getattr_static`, không qua
    `__getattr__`: Mock hay proxy chuyển tiếp thuộc tính "có" mọi tên và mỗi lần trả một đối tượng mới, nên vòng bóc
    bằng getattr trước đây chạy mãi trong `VehicleLink.__init__` (sửa sau review 02/10/2026). Quá `MAX_POSE_WRAPPERS`
    lớp, hay lớp bọc trỏ vòng về chính nó → ValueError (không kiểm được luật SimTruthPose thì không tạo liên kết)."""
    base = source
    for _ in range(MAX_POSE_WRAPPERS):
        if inspect.getattr_static(base, "fault_inner", None) is None:
            return base
        inner = getattr(base, "fault_inner", None)     # thuộc tính có thật (giá trị, hay property được gọi)
        if inner is None:
            return base
        base = inner
    raise ValueError(f"Nguồn tư thế bọc quá {MAX_POSE_WRAPPERS} lớp fault_inner (hoặc lớp bọc trỏ vòng): không kiểm "
                     f"được luật SimTruthPose")


NO_POSE_SOURCE_REASON = ("Chưa có nguồn tư thế thật: định vị LiDAR chưa nối vào phiên và chưa kiểm yêu cầu cùng "
                         "đồng hồ với VehicleIO; tư thế mô phỏng (SimTruthPose) không được dùng với bo thật")


class NoPoseSource:
    """Chỗ giữ nguồn tư thế khi chạy với bo THẬT mà chưa có định vị (thêm 24/09/2026).

    `available = False`: `VehicleLink.begin_run` từ chối START ngay đầu, trước khi mở cổng hay gửi gì tới bo. Không
    thay bằng `SimTruthPose`: tư thế của xe mô phỏng không nói gì về xe thật."""

    source_id = "no_pose_source"
    simulated = False
    available = False

    def __init__(self, reason: str = NO_POSE_SOURCE_REASON):
        self.reason = reason

    def latest(self) -> PoseSample | None:
        return None


class SimHumanDriver:
    """MÔ PHỎNG người lái ở chế độ quan sát: tay điều khiển RC lái ESC/servo, KHÔNG qua ESP32-S3.

    Lớp này thay đầu vào của xe trong `SimVehicleIO`: xe theo (tốc độ, góc lái) của người lái; đầu ra effort/góc
    của `FirmwareModel` vẫn được tính nhưng bị bỏ qua (và phải bằng 0 vì bo DISARMED — test kiểm điều này). Giới hạn
    gia tốc và tốc độ đổi lái vẫn theo `VehicleConfig`; E-stop cắt động lực nếu `estop_cuts_power`. Cách đấu dây
    thật ở chế độ quan sát (ESC nối máy thu RC hay nối ESP32) CHƯA CHỐT."""

    def __init__(self, io: SimVehicleIO):
        self.io = io
        self.speed = 0.0
        self.steer = 0.0
        vehicle = io.vehicle
        base_step = vehicle.step

        def human_step(dt: float, _board_speed: float, _board_steer: float) -> VehicleState:
            actuator = io.config.actuator
            speed = 0.0 if (io.estop and actuator.estop_cuts_power) else self.speed
            return base_step(dt, speed, self.steer)

        vehicle.step = human_step          # thay theo từng đối tượng; SimVehicleIO._pump gọi self.vehicle.step

    def set(self, speed: float, steer: float) -> None:
        if not all(math.isfinite(v) for v in (speed, steer)):
            raise ValueError("Lệnh người lái phải hữu hạn")
        cfg = self.io.vehicle_cfg
        self.speed = clamp(speed, -cfg.max_speed, cfg.max_speed)
        self.steer = clamp(steer, -cfg.max_steer, cfg.max_steer)


@dataclass(frozen=True)
class LinkParams:
    """Ngưỡng của lớp nối. Đều là giá trị khởi đầu để thử phần mềm, CHƯA CHỐT theo xe thật."""

    max_state_age_s: float = 0.15            # telemetry/tư thế cũ hơn → dừng (bằng stale_after_s của giai đoạn 0)
    standstill_mps: float = 0.01             # |tốc độ đo| ≤ ngưỡng này và bo không còn tham chiếu → coi là đứng yên
    start_position_tolerance_m: float = 0.03
    start_yaw_tolerance_rad: float = math.radians(5.0)
    start_speed_tolerance_mps: float = 0.02  # |trung bình tốc độ đo| của `start_samples` khung nhận sau START
    start_samples: int = 3
    stop_confirm_timeout_s: float = 2.0      # kể từ lệnh dừng: quá hạn mà chưa xác nhận đứng yên → FAULT
    command_validity_s: float | None = None  # None = mặc định của VehicleIO (0,15 s)
    connect_timeout_s: float = 1.0
    ready_timeout_s: float = 3.0
    fresh_timeout_s: float = 1.0
    disarm_timeout_s: float = 0.2

    def __post_init__(self):
        for name in ("max_state_age_s", "standstill_mps", "start_position_tolerance_m", "start_yaw_tolerance_rad",
                     "start_speed_tolerance_mps", "stop_confirm_timeout_s", "connect_timeout_s", "ready_timeout_s",
                     "fresh_timeout_s", "disarm_timeout_s"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} phải hữu hạn và > 0")
        if not isinstance(self.start_samples, int) or isinstance(self.start_samples, bool) or self.start_samples < 1:
            raise ValueError("start_samples phải là số nguyên >= 1")


COMMAND_FIELDS = ["t_session", "t_io", "mode", "kind", "sent", "seq", "target_speed_mps", "target_steer_rad",
                  "target_steer_deg", "phase", "segment", "index", "distance_to_end_m", "lateral_error_m",
                  "heading_error_deg", "done", "obs_x", "obs_y", "obs_yaw_deg", "obs_speed_mps", "obs_steer_deg",
                  "telemetry_age_s", "pose_source", "pose_simulated", "note"]
# call (thêm 02/10/2026, T9): số của lần đọc io (dòng clock.csv) đã trả khung này.
TELEMETRY_FIELDS = ["t_session", "t_io", "device_time_ms", "sequence", "state", "fault", "stop_reason", "flags",
                    "link_ok", "estop_input", "cmd_active", "speed_mps", "steer_rad", "speed_ref_mps",
                    "steer_ref_rad", "effort", "last_cmd_seq", "cmd_age_s", "supply_v", "rx_errors", "rejects", "call"]
# Cột của events.csv và start_refusals.csv. t_perf (thêm 02/10/2026, T13): time.perf_counter() thô lúc ghi dòng. Dòng
# nào cũng phải dựng bằng `_event_row` (qua `_log_event`, `log_session_event` hay `record_refused_start`):
# csv.DictWriter ném ValueError khi gặp khóa lạ, và lặng lẽ để trống cột thiếu.
# `handling`: before_start (trước START), stop (sự kiện buộc dừng, lúc lớp nối nhận), log (chỉ ghi), after_run (tới
# sau khi lần chạy đã kết thúc), session_stop (quyết định dừng của PHIÊN, `SESSION_STOP`). call (thêm 02/10/2026, T9):
# số của lần đọc io đã trả sự kiện VehicleIO này; trống với dòng do lớp nối hay phiên tạo và ở start_refusals.csv.
EVENT_FIELDS = ["t_session", "t_io", "t_perf", "source", "code", "action", "handling", "message", "call"]
SESSION_STOP = "session_stop"
# Băng phát lại log (thêm 02/10/2026, T9; `application/vehicle_replay.py`). poses.csv: một dòng mỗi lần đọc nguồn tư thế
# trong lần chạy (use = "estimate" hoặc "observe"); t_io = io.now() đọc liền SAU mẫu; available = 0 khi nguồn không có
# mẫu (các cột của mẫu để trống). clock.csv: một dòng mỗi lần đọc io trong lần chạy (kind = "refresh" hoặc "pump");
# t_io = io.now() sau lần đọc.
POSE_FIELDS = ["n", "use", "t_session", "t_io", "available", "sample_t_io", "x", "y", "yaw_rad", "source_id",
               "simulated"]
CLOCK_FIELDS = ["call", "kind", "t_session", "t_io"]
# Định dạng log của `write_logs` (khóa log_format của link.json). 2 = có băng phát lại (T9); log trước đó không có khóa.
LOG_FORMAT = 2
# Đầu cột note của commands.csv khi send()/stop() ném lỗi; phần sau là lời lỗi (phát lại log dựng lại lỗi từ đây).
SEND_FAILED_NOTE = "gửi lỗi: "
# Cột của board_actions.csv (thêm 02/10/2026, T15): một dòng mỗi lần bấm "Xóa lỗi bo (CLEAR_FAULT)", kể cả lần không gửi
# gì. t_io (đồng hồ io, so được với t_io của các tệp khác của cùng liên kết), t_perf (perf_counter() thô, như T13) và
# wall_time (giờ máy ISO 8601 có múi giờ) đọc liền nhau lúc quyết định gửi hay không gửi CLEAR_FAULT; chưa tới bước đó
# (không mở được cổng, không có HELLO_ACK hay telemetry) thì lúc bấm. Dòng nào cũng đi qua `BoardFaultClear.to_row()`.
# Bốn cột hello_* (nối cuối sau review 02/10/2026, thứ tự cột cũ giữ nguyên): HELLO_ACK của lần bấm, trống khi dùng lại
# phiên; boot_id ghi "0x" + 8 chữ số hex để bảng tính không đọc thành số.
BOARD_ACTION_FIELDS = ["t_io", "t_perf", "wall_time", "target", "request", "outcome", "ack_result", "state_before",
                       "fault_before", "estop_before", "state_after", "fault_after", "requests_sent", "commands_sent",
                       "message", "hello_firmware", "hello_boot_id", "hello_reset_reason", "hello_state"]

# Sự kiện VehicleIO mang action "LOG" nhưng trong lúc TỰ ĐỖ qua VehicleIO nghĩa là bo không còn chạy theo lệnh
# của laptop: coi là dừng. (Ở chế độ quan sát không có lệnh nào nên không nâng mức.)
_VEHICLE_IO_STOP_CODES = {"COMMAND_REJECTED", "VEHICLE_STOPPED"}


def _blank(value):
    return "" if value is None else value


def _event_row(t_io: float | None, t_session: float | None, source: str, code: str, action: str, handling: str,
               message: str, call: int | None = None) -> dict:
    """Một dòng events.csv hay start_refusals.csv: khóa đúng bằng EVENT_FIELDS, đúng thứ tự cột; None thành ô trống,
    t_session làm tròn 0,1 ms, t_perf = perf_counter() thô lúc dựng dòng. Chỗ DUY NHẤT biết khóa của hai tệp đó
    (sửa sau review 02/10/2026: trước đó `record_refused_start` tự dựng dòng và đã thiếu t_perf, call một lần)."""
    return {"t_session": _blank(None if t_session is None else round(t_session, 4)), "t_io": _blank(t_io),
            "t_perf": time.perf_counter(), "source": source, "code": code, "action": action, "handling": handling,
            "message": message, "call": _blank(call)}


class MirroredWorld(SimWorld):
    """Thế giới "gương" của lần chạy qua VehicleIO: KHÔNG tích phân lệnh. Mỗi bước lấy trạng thái ước lượng từ
    `VehicleLink` (tư thế từ nguồn định vị, tốc độ/góc lái đo từ telemetry) và kiểm va chạm hình học với vật cản
    đã biết. Va chạm không làm xe dừng tức thời như `SimWorld` (xe thật không dừng tức thời): `Session` kết thúc
    FAULT và lớp nối gửi lệnh dừng + DISARM."""

    def __init__(self, scenario: Scenario, cfg: VehicleConfig, dt: float, link: "VehicleLink",
                 initial: VehicleState):
        super().__init__(scenario, cfg, dt)
        self._link = link
        self.vehicle.state = replace(initial, t=0.0)
        self.last_collision = check_pose(cfg, initial.pose, scenario.obstacles, scenario.bounds)
        self.collided = not self.last_collision.ok

    def reset(self) -> None:
        raise RuntimeError("Không đặt lại được xe qua VehicleIO; đặt xe bằng tay rồi lập lại đường")

    def step(self, target_speed: float, target_steer: float) -> StepResult:
        # target_*: lệnh đã đi qua VehicleLink.command() (hoặc không đi đâu ở chế độ quan sát)
        prev = self.state
        t = prev.t + self.dt
        self._link.pump(t)
        new = self._link.estimate(t, prev)
        self.vehicle.state = new
        self.step_count += 1
        self.distance += math.hypot(new.pose.x - prev.pose.x, new.pose.y - prev.pose.y)
        collision = check_motion(self.cfg, prev.pose, new.pose, self.scenario.obstacles, self.scenario.bounds)
        self.last_collision = collision
        if not collision.ok:
            self.collided = True
            return StepResult(new, collision, True)
        return StepResult(new, collision, False)


class VehicleLink:
    """Bộ chuyển giữa `Session` và một `VehicleIO` (chế độ VEHICLE_IO hoặc OBSERVE; SIM không dùng lớp này).

    Dùng `VehicleLink.simulated(mode)` cho chuỗi mô phỏng của giao diện: mỗi lần START tạo một `SimVehicleIO` mới
    đặt tại điểm xuất phát (mô phỏng người đặt xe vào vị trí), nguồn tư thế là `SimTruthPose`, và ở chế độ quan
    sát có `SimHumanDriver`. Truyền `io` + `pose_source` để dùng một VehicleIO có sẵn (test, hoặc bo thật khi đã có
    nguồn định vị)."""

    def __init__(self, mode: DriveMode | str, io: VehicleIO | None = None, *, pose_source: PoseSource | None = None,
                 params: LinkParams | None = None, sim_config: SimIOConfig | None = None, _simulated: bool = False):
        mode = DriveMode(mode)
        if mode == DriveMode.SIM:
            raise ValueError("Chế độ SIM không đi qua VehicleLink (Session.set_vehicle_link(None))")
        if not _simulated and (io is None or pose_source is None):
            raise ValueError("Cần VehicleIO và nguồn tư thế (hoặc dùng VehicleLink.simulated)")
        # Lớp bọc tiêm lỗi (`fault_inner`, safety/fault_injection.py, 02/10/2026) không được che luật SimTruthPose.
        base = unwrap_pose_source(pose_source)
        if isinstance(base, SimTruthPose) and (base.io is not io or not isinstance(io, SimVehicleIO)):
            # Tư thế thật của một xe mô phỏng KHÁC, ghép với bo thật, hoặc SimTruthPose dựng quanh chính bo serial
            # (sửa muộn tối 24/09/2026: trước đó lọt qua rồi START hỏng với AttributeError thay vì từ chối rõ ràng):
            # không phải tư thế của xe mà io điều khiển.
            raise ValueError("SimTruthPose chỉ dùng với chính SimVehicleIO của liên kết (bo mô phỏng); không ghép với "
                             "bo thật hay bo mô phỏng khác")
        self.mode = mode
        self.io = io
        self.pose_source = pose_source
        self.params = params or LinkParams()
        self.sim_config = sim_config
        self._simulated = _simulated
        self.human: SimHumanDriver | None = None
        self._closed = False
        self.command_rows: list[dict] = []
        self.telemetry_rows: list[dict] = []
        self.event_rows: list[dict] = []
        # Băng phát lại (T9) của lần chạy gần nhất đã mở: dòng poses.csv (POSE_FIELDS), dòng clock.csv (CLOCK_FIELDS)
        # và trạng thái lúc mở lần chạy (khóa run_start của link.json; None khi chưa mở lần nào).
        self.pose_rows: list[dict] = []
        self.clock_rows: list[dict] = []
        self.run_start: dict | None = None
        # Dòng sự kiện (EVENT_FIELDS) của các lần START bị từ chối, cộng dồn suốt đời liên kết; không đè log của lần
        # chạy trước.
        self.start_refusals: list[dict] = []
        # Dòng board_actions.csv (BOARD_ACTION_FIELDS): mỗi lần `clear_fault()` (T15), cộng dồn suốt đời liên kết như
        # start_refusals; begin_run không xóa.
        self.board_actions: list[dict] = []
        self.refused_starts = 0           # số lần START bị từ chối
        self.runs = 0
        self.result: dict | None = None
        self.suggestion: TrackerOutput | None = None
        self.limits_check: LimitsCheck | None = None    # lần so giới hạn gần nhất lúc START (kể cả lần bị từ chối)
        self._reset_run_state()

    @classmethod
    def simulated(cls, mode: DriveMode | str, sim_config: SimIOConfig | None = None, *,
                  params: LinkParams | None = None) -> "VehicleLink":
        return cls(mode, params=params, sim_config=sim_config or SimIOConfig(), _simulated=True)

    @classmethod
    def serial_port(cls, mode: DriveMode | str, port: str, *, pose_source: PoseSource | None = None,
                    params: LinkParams | None = None, **io_kwargs) -> "VehicleLink":
        """Liên kết tới bo THẬT qua cổng `port` (thêm 24/09/2026). Cổng KHÔNG được mở ở đây
        (`SerialVehicleIO.deferred`). Không truyền nguồn tư thế thì dùng `NoPoseSource`, và START luôn bị từ chối
        trước khi mở cổng."""
        io = SerialVehicleIO.deferred(port, **io_kwargs)
        return cls(mode, io, pose_source=pose_source if pose_source is not None else NoPoseSource(), params=params)

    def _reset_run_state(self) -> None:
        self._io_t0 = 0.0
        self._perf_t0: float | None = None    # perf_counter() đọc liền sau _io_t0 lúc mở lần chạy (link.json "clock")
        self._pending: list[SafetyEvent] = []
        self._run_cmd_seqs: set[int] = set()
        self._stop_started: float | None = None
        self._halted = False              # đã có lệnh dừng/sự kiện dừng: lần chạy này không gửi enable nữa
        self._guard_reported = False
        self._running = False
        self._call = 0                    # số của lần đọc io kế tiếp trong lần chạy (cột call, clock.csv; T9)
        self._last_t = 0.0                # t của lần pump gần nhất = world.time lúc đầu bước (dòng refresh ghi t này)

    # ------------------------------------------------------------------ thuộc tính
    @property
    def observe_only(self) -> bool:
        return self.mode == DriveMode.OBSERVE

    @property
    def realtime(self) -> bool:
        """True khi VehicleIO chạy theo thời gian thực (bo thật): Session không được tua nhanh."""
        if self._simulated:
            return False
        return not isinstance(self.io, SimVehicleIO)

    @property
    def pose_simulated(self) -> bool:
        return self._simulated or bool(self.pose_source is not None and self.pose_source.simulated)

    def describe(self) -> dict:
        source = self.pose_source
        return {
            "mode": self.mode.value,
            "io": type(self.io).__name__ if self.io is not None else ("SimVehicleIO" if self._simulated else None),
            # T9: nguồn đóng dấu khung telemetry; phát lại log dựng lại khung và nguồn trạng thái với đúng tên này
            "io_source_id": getattr(self.io, "source_id", None),
            "io_simulated": self._simulated or isinstance(self.io, SimVehicleIO),
            "pose_source": source.source_id if source is not None else (
                SimTruthPose.source_id if self._simulated else None),
            "pose_simulated": self.pose_simulated,
            "port": getattr(self.io, "port", None),
            "params": asdict(self.params),
            "sim_config": self.sim_config.to_dict() if self.sim_config is not None else None,
            "limits_check": self.limits_check.to_dict() if self.limits_check is not None else None,
            "evidence": ("simulation_only" if (self._simulated or isinstance(self.io, SimVehicleIO))
                         else "hardware_untested"),
        }

    # ------------------------------------------------------------------ bắt đầu lần chạy
    def _t_session(self, t_io: float) -> float:
        return t_io - self._io_t0

    def _link_event(self, t: float, code: str, message: str, action: str = "STOP") -> SafetyEvent:
        return SafetyEvent(SourceStamp("vehicle_link", max(0.0, t)), code, message, action)

    def _log_event(self, t_io: float | None, t_session: float | None, source: str, code: str, action: str,
                   handling: str, message: str, *, call: int | None = None) -> None:
        """Cửa ghi duy nhất của `event_rows` (dòng dựng bằng `_event_row`). t_perf: perf_counter() thô lúc ghi. `call`
        (T9): chỉ `_collect_events` truyền, cho sự kiện VehicleIO mà một lần đọc io trả; dòng khác để trống."""
        self.event_rows.append(_event_row(t_io, t_session, source, code, action, handling, message, call))

    def log_session_event(self, t_session: float, source: str, code: str, message: str, *, action: str = "STOP",
                          handling: str = SESSION_STOP) -> None:
        """T13 (02/10/2026): ghi một sự kiện do PHIÊN phát vào events.csv của lần chạy đang mở (`Session` gọi trước
        `end_run`). Ba mốc của dòng: t_session = thời gian phiên của sự kiện; t_io = io.now() lúc phiên quyết định
        (cùng quy ước với commands.csv); t_perf = perf_counter() lúc ghi. Chỉ ghi log: không gửi gì tới bo; chưa có io
        thì t_io để trống.

        KHÔNG BAO GIỜ ném lỗi (bảo đảm ở đây từ sau review 02/10/2026; trước đó chỉ là lời hứa): `Session` gọi hàm này
        ngay TRƯỚC bước an toàn (sang STOPPING, vô hiệu đường, `end_run` gửi enable=0 + DISARM), nên lỗi ở đây sẽ bỏ
        qua chính bước đó. Đọc io.now() hỏng thì t_io để trống và lời lỗi nối vào message; lỗi khác khi ghi thì mất
        dòng này, phiên vẫn dừng."""
        try:
            io, t_io = self.io, None
            if io is not None:
                try:
                    t_io = io.now()
                except Exception as exc:  # noqa: BLE001 - đồng hồ hỏng không được chặn bước dừng
                    message = f"{message} (không đọc được io.now(): {exc!r})"
            self._log_event(t_io, t_session, source, code, action, handling, message)
        except Exception:  # noqa: BLE001 - như trên: thà mất một dòng log còn hơn bỏ qua bước dừng
            pass

    def _new_telemetry(self, after: float, count: int) -> list[VehicleTelemetry]:
        """Chờ `count` khung telemetry khác nhau NHẬN SAU thời điểm `after` (đồng hồ io). Trạng thái dùng để quyết
        định START phải phản ánh bo từ lúc bấm START trở đi, không phải khung cũ có trước một thao tác vừa làm."""
        io = self.io
        deadline = io.now() + self.params.fresh_timeout_s
        samples: list[VehicleTelemetry] = []
        while True:
            tel = io.latest()
            if tel is not None and tel.stamp.t > after and (not samples or tel.sequence != samples[-1].sequence):
                samples.append(tel)
                if len(samples) >= count:
                    return samples
            if io.now() >= deadline:
                raise VehicleIOError(f"Không nhận đủ {count} khung telemetry mới trong "
                                     f"{self.params.fresh_timeout_s:.1f} s")
            io.service()

    def _measured_speed(self, tel: VehicleTelemetry) -> float | None:
        if tel.speed_mps is None:
            return None
        if abs(tel.speed_mps) <= self.params.standstill_mps and tel.speed_ref_mps == 0.0:
            return 0.0                    # đứng yên: bo không còn tham chiếu và số đo nằm trong ngưỡng nhiễu
        return tel.speed_mps

    def _start_problems(self, samples: list[VehicleTelemetry], scenario: Scenario,
                        cfg: VehicleConfig) -> tuple[list[str], str]:
        p = self.params
        tel = samples[-1]
        problems = []
        if tel.state == State.FAULT or tel.fault != Fault.NONE:
            problems.append(f"Bo đang FAULT ({tel.fault.name}): xử lý nguyên nhân (nhả nút dừng khẩn…) rồi bấm "
                            f"'Xóa lỗi bo (CLEAR_FAULT)' ở thẻ Bo điều khiển")
        if tel.estop_input:
            problems.append("Nút dừng khẩn đang nhấn")
        if tel.state == State.BOOT:
            problems.append("Bo chưa khởi động xong (BOOT)")
        if self.mode == DriveMode.VEHICLE_IO and tel.state == State.RUNNING:
            problems.append("Bo đang RUNNING theo lệnh từ nơi khác: không bắt đầu")
        speeds = [s.speed_mps for s in samples]
        mean_speed = math.nan
        if any(v is None for v in speeds) or tel.steer_rad is None:
            problems.append("Telemetry không có tốc độ hoặc góc lái đo được (chưa có encoder/AS5600?)")
        else:
            mean_speed = sum(speeds) / len(speeds)
            if abs(mean_speed) > p.start_speed_tolerance_mps or tel.speed_ref_mps != 0.0:
                problems.append(f"Xe đang chuyển động (trung bình {mean_speed:+.3f} m/s trên {len(speeds)} khung, "
                                f"tham chiếu của bo {tel.speed_ref_mps:+.3f} m/s): chỉ bắt đầu khi xe đứng yên")
        sample = self.pose_source.latest()
        summary = f"bo {tel.state.name}, tốc độ đo trung bình {mean_speed:+.3f} m/s"
        if self._pose_fresh(sample):
            start = scenario.start
            dist = sample.pose.distance_to(start)
            dyaw = wrap_angle(sample.pose.yaw - start.yaw)
            summary += (f", tư thế ({sample.pose.x:.3f}, {sample.pose.y:.3f}) m lệch {dist * 100:.1f} cm / "
                        f"{math.degrees(dyaw):+.1f}° so với xuất phát ({sample.source_id}"
                        f"{', MÔ PHỎNG' if sample.simulated else ''})")
        problems += self._pose_problems(sample, scenario, cfg)
        return problems, summary

    def _pose_fresh(self, sample: PoseSample | None) -> bool:
        return sample is not None and 0 <= self.io.now() - sample.t <= self.params.max_state_age_s

    def _pose_problems(self, sample: PoseSample | None, scenario: Scenario, cfg: VehicleConfig) -> list[str]:
        """Kiểm tư thế lúc START (dùng cả trước ARM và sau ARM/DISARM): mới, gần điểm xuất phát, không chạm vật cản."""
        p = self.params
        if not self._pose_fresh(sample):
            return ["Chưa có tư thế mới từ nguồn định vị"]
        out = []
        start = scenario.start
        dist = sample.pose.distance_to(start)
        dyaw = wrap_angle(sample.pose.yaw - start.yaw)
        if dist > p.start_position_tolerance_m or abs(dyaw) > p.start_yaw_tolerance_rad:
            out.append(f"Xe đang ở ({sample.pose.x:.3f}, {sample.pose.y:.3f}) m, hướng "
                       f"{math.degrees(sample.pose.yaw):+.1f}°: lệch {dist * 100:.1f} cm / "
                       f"{math.degrees(dyaw):+.1f}° so với điểm xuất phát đã lập đường (cho phép "
                       f"{p.start_position_tolerance_m * 100:.0f} cm / "
                       f"{math.degrees(p.start_yaw_tolerance_rad):.0f}°)")
        if not check_pose(cfg, sample.pose, scenario.obstacles, scenario.bounds).ok:
            out.append("Tư thế đo được chạm vật cản hoặc ra ngoài sa bàn")
        return out

    def record_refused_start(self, code: str, message: str, source: str = "session") -> None:
        """START bị PHIÊN từ chối trước khi tới `begin_run` (T12, 02/10/2026: đường đổi chiều quá giới hạn): một dòng
        vào `start_refusals` (start_refusals.csv, bằng chứng GD2) và đếm vào `refused_starts`. Không I/O nào với bo,
        nên dùng được cả khi liên kết mô phỏng chưa START lần nào (`io` None); log và kết quả lần chạy trước giữ nguyên.
        Dòng dựng bằng `_event_row` như mọi dòng events.csv (t_session trống, t_io = io.now() khi đã có io, t_perf lúc
        ghi, call trống)."""
        io = self.io
        self.start_refusals.append(_event_row(io.now() if io is not None else None, None, source, code, "LOG",
                                              "before_start", message))
        self.refused_starts += 1

    def begin_run(self, scenario: Scenario, cfg: VehicleConfig, dt: float) -> MirroredWorld:
        """Kiểm lại trạng thái thật rồi mở lần chạy. VEHICLE_IO: `arm()` (thao tác cho phép mới — gỡ cả chốt
        TELEMETRY_STALE). OBSERVE: gửi DISARM (không phải lệnh chuyển động) rồi chờ telemetry mới báo DISARMED; không
        gửi COMMAND nào.

        Lỗi ở bất kỳ bước nào → `VehicleLinkError` (không ngoại lệ loại khác): đã gửi ARM thì gửi DISARM trước khi báo
        lỗi, nên bo không bị bỏ lại ở ARMED. Log, kết quả và (nhánh mô phỏng) bo giả của lần chạy TRƯỚC giữ nguyên
        cho tới khi lần mới đã thật sự mở; các dòng trước START của lần bị từ chối được nối vào `start_refusals`."""
        if self._closed:
            raise VehicleLinkError("Liên kết VehicleIO đã đóng")
        previous = (self.io, self.pose_source, self.human, self.event_rows)
        if self._simulated:
            new_io = SimVehicleIO(cfg, self.sim_config, start=VehicleState(scenario.start, 0.0, 0.0, 0.0))
            self.io, self.pose_source = new_io, SimTruthPose(new_io)
            self.human = SimHumanDriver(new_io) if self.observe_only else None
        self.event_rows = []              # dòng trước START của lần thử này (_log_event ghi vào đây)
        try:
            world = self._open_run(scenario, cfg, dt)
        except Exception as exc:
            if not isinstance(exc, VehicleLinkError):     # lỗi trước khi gửi ARM/DISARM (ví dụ nguồn tư thế ném)
                self._log_event(self.io.now(), None, "vehicle_link", "START_ABORTED", "LOG", "before_start",
                                repr(exc))
            attempt = self.event_rows
            if self._simulated:
                self.io.close()           # bo mô phỏng MỚI của lần bị từ chối; bo của lần trước giữ nguyên
            self.io, self.pose_source, self.human, self.event_rows = previous
            self.start_refusals.extend(attempt)
            self.refused_starts += 1
            if isinstance(exc, VehicleLinkError):
                raise
            raise VehicleLinkError(f"Lỗi khi mở lần chạy: {exc!r}") from exc
        # Lần mới đã mở: tới đây mới thay log/kết quả của lần chạy trước.
        staged = self.event_rows
        if self._simulated and previous[0] is not None:
            previous[0].close()
        self._commit_run(staged, world)
        return world

    def _commit_run(self, staged_events: list[dict], world: MirroredWorld) -> None:
        """Mở lần chạy mới (`begin_run` đã qua mọi kiểm tra, hoặc phát lại log ở `ReplayVehicleLink`): thay log, kết quả
        và băng phát lại của lần chạy trước; t0 = io.now(). T9: `run_start` = t0 cùng trạng thái đầu của thế giới gương
        (tư thế, góc lái, nguồn), đủ để phát lại log dựng lại thế giới gương mà không chạy lại bước START."""
        self._reset_run_state()
        self.command_rows.clear()
        self.telemetry_rows.clear()
        self.event_rows = staged_events
        self.pose_rows.clear()
        self.clock_rows.clear()
        self.result = None
        self.suggestion = None
        self._io_t0 = self.io.now()
        self._perf_t0 = time.perf_counter()    # liền sau _io_t0: cặp đổi t_io → perf của link.json "clock"
        self._running = True
        self.runs += 1
        state = world.state
        self.run_start = {"t_io0": self._io_t0, "x": state.pose.x, "y": state.pose.y, "yaw_rad": state.pose.yaw,
                          "steer_rad": state.steer, "state_source": state.source_id}

    def _open_run(self, scenario: Scenario, cfg: VehicleConfig, dt: float) -> MirroredWorld:
        io = self.io
        p = self.params
        if not getattr(self.pose_source, "available", True):
            # Bo thật mà chưa có nguồn tư thế thật (24/09/2026): từ chối TRƯỚC mọi I/O (không mở cổng, không HELLO).
            port = getattr(io, "port", None)
            message = (f"Không bắt đầu được với bo thật{f' ({port})' if port else ''}: "
                       f"{getattr(self.pose_source, 'reason', NO_POSE_SOURCE_REASON)}. Cổng chưa được mở, không gửi gì "
                       f"tới bo; dùng 'Kiểm kết nối bo' để kiểm liên lạc")
            self._log_event(io.now(), None, "vehicle_link", "START_NO_POSE_SOURCE", "LOG", "before_start", message)
            raise VehicleLinkError(message)
        try:
            if not io.connected:
                io.connect(timeout_s=p.connect_timeout_s)
            io.wait_ready(timeout_s=p.ready_timeout_s)
            samples = self._new_telemetry(io.now(), p.start_samples)
            limits = io.check_limits(cfg, emit_event=False)
        except VehicleIOError as exc:
            self._log_event(io.now(), None, "vehicle_link", "START_NO_LINK", "LOG", "before_start", str(exc))
            raise VehicleLinkError(f"Không có liên lạc với bo: {exc}") from exc
        self.limits_check = limits
        for ev in io.events():            # sự kiện cũ: ghi lại, không làm dừng lần chạy mới
            self._log_event(ev.stamp.t, None, ev.stamp.source_id, ev.code, ev.action, "before_start", ev.message)
        refuse_limits = self.mode == DriveMode.VEHICLE_IO and bool(limits.risky)
        if not limits.ok:
            # VEHICLE_IO + lệch nguy hiểm → dòng STOP và START bị từ chối (qua START_CHECK); còn lại chỉ cảnh báo.
            handling = ("TỪ CHỐI START" if refuse_limits else
                        "chỉ cảnh báo (quan sát: không gửi lệnh)" if self.observe_only else
                        "chỉ cảnh báo (bo chặt hơn)")
            self._log_event(io.now(), None, "vehicle_link", "LIMITS_MISMATCH", "STOP" if refuse_limits else "LOG",
                            "before_start", f"{limits.describe()} → {handling}")
        problems, summary = self._start_problems(samples, scenario, cfg)
        if refuse_limits:
            problems.append("Giới hạn của bo lệch cấu hình xe mà planner dùng theo hướng nguy hiểm: "
                            + "; ".join(m.describe() for m in limits.risky)
                            + ". Sửa cấu hình xe hoặc firmware cho khớp rồi lập lại đường")
        summary += ", giới hạn: " + ("khớp" if limits.ok else
                                     f"lệch {len(limits.mismatches)} ({len(limits.risky)} nguy hiểm)")
        self._log_event(io.now(), None, "vehicle_link", "START_CHECK", "LOG", "before_start",
                        ("TỪ CHỐI: " + "; ".join(problems) + " | " if problems else "Đạt: ") + summary)
        if problems:
            raise VehicleLinkError("; ".join(problems))
        tel = samples[-1]
        arm_sent = False
        try:
            try:
                if self.mode == DriveMode.VEHICLE_IO:
                    arm_sent = True       # hết giờ chờ ACK không có nghĩa bo chưa ARM: lỗi về sau vẫn gửi DISARM
                    io.arm()
                else:
                    io.disarm()
                    if tel.state in (State.ARMED, State.RUNNING):
                        self._log_event(io.now(), None, "vehicle_link", "OBSERVE_DISARM", "LOG", "before_start",
                                        f"Bo đang {tel.state.name} lúc bắt đầu quan sát: đã gửi DISARM")
                    tel = self._new_telemetry(io.now(), 1)[-1]
                    if tel.state != State.DISARMED:
                        raise VehicleLinkError(f"Bo ở {tel.state.name} sau DISARM: không quan sát")
                    if tel.steer_rad is None:
                        raise VehicleLinkError("Khung telemetry sau DISARM không có góc lái đo được: không quan sát")
            except VehicleIOError as exc:
                raise VehicleLinkError(f"Bo từ chối: {exc}") from exc
            # ARM/DISARM có thể mất tới vài trăm ms trên bo thật: đọc và kiểm lại tư thế thay vì dùng mẫu lúc kiểm.
            sample = self.pose_source.latest()
            pose_problems = self._pose_problems(sample, scenario, cfg)
            if pose_problems:
                raise VehicleLinkError("Sau khi mở lần chạy: " + "; ".join(pose_problems))
            initial = VehicleState(sample.pose, 0.0, tel.steer_rad, 0.0, source_id=self._state_source(sample))
            return MirroredWorld(scenario, cfg, dt, self, initial)
        except Exception as exc:
            if arm_sent:                  # bo có thể đã ARM: tháo ra trước khi báo lỗi
                try:
                    io.disarm(timeout_s=p.disarm_timeout_s)
                except VehicleIOError as dexc:
                    self._log_event(io.now(), None, "vehicle_link", "DISARM_FAILED", "LOG", "before_start", str(dexc))
            self._log_event(io.now(), None, "vehicle_link", "START_ABORTED", "LOG", "before_start", str(exc))
            if isinstance(exc, VehicleLinkError):
                raise
            raise VehicleLinkError(f"Lỗi khi mở lần chạy: {exc!r}") from exc

    def _state_source(self, sample: PoseSample) -> str:
        return f"{self.io.source_id}+{sample.source_id}"

    # ------------------------------------------------------------------ mỗi bước
    def session_time_now(self) -> float:
        """Thời gian phiên theo đồng hồ của VehicleIO: `io.now() - t0`. `Session.advance()` dùng nó khi `realtime`."""
        return self.io.now() - self._io_t0

    def pump(self, t: float) -> None:
        """Tiến I/O tới thời gian phiên t. Mô phỏng: chạy bo giả tới io.now() ≥ t0 + t. Bo thật: `poll(block=False)`
        — chỉ đọc byte đã có sẵn, KHÔNG chờ timeout đọc của cổng (chờ ở đây sẽ chặn luồng giao diện và làm thời gian
        phiên chậm hơn `io.now()`). T9: một lần gọi là một lần đọc io của băng phát lại (dòng clock.csv "pump")."""
        io = self.io
        if io is None:
            return
        if isinstance(io, SimVehicleIO):
            tick = io.config.tick_ms / 1000.0
            target = self._io_t0 + t
            while io.now() + 1e-9 < target:
                self._on_telemetry(io.advance(tick))
        else:
            self._on_telemetry(io.poll(block=False))
        self._collect_events()
        self._end_call("pump", t)
        self._last_t = t

    def refresh(self) -> None:
        """Lấy telemetry và sự kiện ĐÃ tới, không tiến thời gian: bo thật `poll(block=False)` (chỉ byte có sẵn); bo mô
        phỏng chỉ lấy hàng đợi hiện có (`take_new()`), không chạy thêm nhịp nào. `Session` gọi hàm này đầu mỗi bước khi
        đang chạy, TRƯỚC nhịp điều khiển.

        Sửa tối 24/09/2026 (khoảng trống an toàn, tìm thấy trên mô phỏng): trước đó sự kiện chỉ được gom trong `pump()`,
        chạy SAU nhịp điều khiển. Vòng điều khiển treo lâu hơn hạn lệnh trong khi Heartbeat vẫn giữ liên lạc thì bo về
        ARMED (COMMAND_TIMEOUT) mà telemetry vẫn mới; bước đầu tiên sau khi hết treo rơi đúng nhịp điều khiển thì gửi MỘT
        COMMAND enable=1 (bo ARMED → RUNNING) trước khi thấy VEHICLE_STOPPED. Mô hình bo với lệnh dừng tới sau 10–40 ms
        cho effort 107–130 ‰.

        T9: một lần gọi là một lần đọc io của băng phát lại (dòng clock.csv "refresh"); t_session của dòng là t của lần
        pump trước, tức world.time lúc đầu bước (0 ở bước đầu), nên `Session` không phải truyền gì."""
        io = self.io
        if io is None:
            return
        if isinstance(io, SimVehicleIO):
            self._on_telemetry(io.take_new())
        else:
            self._on_telemetry(io.poll(block=False))
        self._collect_events()
        self._end_call("refresh", self._last_t)

    def _end_call(self, kind: str, t: float) -> None:
        """T9: kết thúc một lần đọc io của lần chạy: dòng clock.csv (số lần đọc, loại, t_session, io.now() SAU lần đọc),
        rồi tăng số lần đọc. Khung telemetry và sự kiện VehicleIO mà lần đọc này trả mang cùng số ở cột call."""
        self.clock_rows.append({"call": self._call, "kind": kind, "t_session": round(t, 4), "t_io": self.io.now()})
        self._call += 1

    def _on_telemetry(self, frames: list[VehicleTelemetry]) -> None:
        for tel in frames:
            self.telemetry_rows.append({
                "t_session": round(self._t_session(tel.stamp.t), 4), "t_io": tel.stamp.t,
                "device_time_ms": tel.device_time_ms, "sequence": tel.sequence, "state": tel.state.name,
                "fault": tel.fault.name, "stop_reason": tel.stop_reason.name, "flags": int(tel.flags),
                "link_ok": int(tel.link_ok), "estop_input": int(tel.estop_input),
                "cmd_active": int(bool(tel.flags & TelemetryFlag.CMD_ACTIVE)),
                "speed_mps": _blank(tel.speed_mps), "steer_rad": _blank(tel.steer_rad),
                "speed_ref_mps": tel.speed_ref_mps, "steer_ref_rad": tel.steer_ref_rad, "effort": tel.effort,
                "last_cmd_seq": tel.last_cmd_seq, "cmd_age_s": _blank(tel.cmd_age_s), "supply_v": _blank(tel.supply_v),
                "rx_errors": tel.rx_errors, "rejects": tel.rejects, "call": self._call})
            # Khung nhận trước START (còn trong hàng đợi của VehicleIO) chỉ ghi log, không đưa vào kiểm tra.
            if self._running and not self._guard_reported and tel.stamp.t >= self._io_t0:
                self._guard(tel)

    def _guard(self, tel: VehicleTelemetry) -> None:
        t = self._t_session(tel.stamp.t)
        if self.observe_only:
            if tel.state in (State.ARMED, State.RUNNING) or tel.flags & TelemetryFlag.CMD_ACTIVE:
                self._guard_reported = True
                message = (f"Chế độ quan sát nhưng bo đang {tel.state.name}: gửi DISARM và kết thúc quan sát")
                self._pending.append(self._link_event(t, "OBSERVE_NOT_DISARMED", message))
                self._log_event(tel.stamp.t, t, "vehicle_link", "OBSERVE_NOT_DISARMED", "STOP", "stop", message)
                try:
                    self.io.disarm(timeout_s=self.params.disarm_timeout_s)
                except VehicleIOError as exc:
                    self._log_event(self.io.now(), None, "vehicle_link", "DISARM_FAILED", "LOG", "log", str(exc))
        elif tel.last_cmd_seq in self._run_cmd_seqs and tel.state not in (State.ARMED, State.RUNNING):
            self._guard_reported = True
            message = f"Bo đã rời chế độ nhận lệnh ({tel.state.name}, lý do {tel.stop_reason.name}): dừng"
            self._pending.append(self._link_event(t, "VEHICLE_NOT_ARMED", message))
            self._log_event(tel.stamp.t, t, "vehicle_link", "VEHICLE_NOT_ARMED", "STOP", "stop", message)

    def _collect_events(self) -> None:
        for ev in self.io.events():
            t = self._t_session(ev.stamp.t)
            # Bo rời RUNNING vì chính laptop đã gửi lệnh dừng (enable=0) thì không phải sự cố.
            promoted = (self.mode == DriveMode.VEHICLE_IO and ev.code in _VEHICLE_IO_STOP_CODES
                        and self._stop_started is None)
            stop = ev.action == "STOP" or promoted
            if not self._running:
                handling = "after_run"
            else:
                handling = "stop" if stop else "log"
            self._log_event(ev.stamp.t, t, ev.stamp.source_id, ev.code, ev.action, handling, ev.message,
                            call=self._call)
            if stop and self._running:
                self._pending.append(SafetyEvent(SourceStamp(ev.stamp.source_id, max(0.0, t)), ev.code,
                                                 ev.message, "STOP"))

    def take_events(self) -> list[SafetyEvent]:
        """Sự kiện buộc dừng từ lần `pump()` trước (VehicleIO và các kiểm tra của lớp này), stamp theo thời gian
        phiên."""
        out, self._pending = self._pending, []
        if out:
            self._halted = True
        return out

    def telemetry_fresh(self) -> bool:
        return self.io is not None and self.io.telemetry_fresh(max_age_s=self.params.max_state_age_s)

    def _pose(self, use: str, t: float) -> tuple[PoseSample | None, float | None]:
        """Đọc nguồn tư thế rồi đọc io.now() NGAY SAU mẫu (thứ tự `observe` vẫn dùng), và (T9) ghi một dòng poses.csv:
        mẫu, hoặc available = 0 khi nguồn không có mẫu, cùng đồng hồ io lúc đọc. `use`: "estimate" (thế giới gương)
        hoặc "observe" (trạng thái đo cho bộ bám). Trả (mẫu, io.now())."""
        sample = self.pose_source.latest() if self.pose_source is not None else None
        now = self.io.now() if self.io is not None else None
        row = {"n": len(self.pose_rows), "use": use, "t_session": round(t, 4), "t_io": _blank(now),
               "available": int(sample is not None)}
        if sample is None:
            row.update(sample_t_io="", x="", y="", yaw_rad="", source_id="", simulated="")
        else:
            row.update(sample_t_io=sample.t, x=sample.pose.x, y=sample.pose.y, yaw_rad=sample.pose.yaw,
                       source_id=sample.source_id, simulated=int(sample.simulated))
        self.pose_rows.append(row)
        return sample, now

    def estimate(self, t: float, prev: VehicleState) -> VehicleState:
        """Trạng thái cho thế giới gương: tư thế từ nguồn định vị, tốc độ/góc lái đo; thiếu thì giữ giá trị trước."""
        pose = prev.pose
        source = prev.source_id
        sample, _ = self._pose("estimate", t)
        if sample is not None:
            pose = sample.pose
            source = self._state_source(sample)
        speed, steer = prev.speed, prev.steer
        tel = self.io.latest() if self.io is not None else None
        if tel is not None:
            measured = self._measured_speed(tel)
            if measured is not None:
                speed = measured
            if tel.steer_rad is not None:
                steer = tel.steer_rad
        return VehicleState(pose, speed, steer, t, source_id=source)

    def observe(self, t: float) -> tuple[VehicleState | None, SafetyEvent | None]:
        """Trạng thái đo cho bộ bám quỹ đạo, hoặc (None, sự kiện dừng) khi telemetry/tư thế cũ hoặc thiếu."""
        p = self.params
        io = self.io
        tel = io.latest()
        now = io.now()
        if tel is None or not 0 <= now - tel.stamp.t <= p.max_state_age_s:
            age = "không có" if tel is None else f"{now - tel.stamp.t:.3f} s"
            message = f"Telemetry cũ ({age}, ngưỡng {p.max_state_age_s:.2f} s): dừng và chờ đánh giá lại"
            return None, self._link_event(t, "STALE_TELEMETRY", message)
        speed = self._measured_speed(tel)
        if speed is None or tel.steer_rad is None:
            return None, self._link_event(t, "NO_MEASURED_STATE", "Telemetry không có tốc độ/góc lái đo được: dừng")
        # Đọc đồng hồ SAU khi lấy mẫu (trong `_pose`): với đồng hồ mịn (bo thật), mẫu đóng dấu io.now() bên trong
        # latest() luôn muộn hơn một `now` đọc trước đó vài µs và sẽ bị coi nhầm là mẫu "ở tương lai" (tuổi âm) →
        # STALE_POSE giả.
        sample, now = self._pose("observe", t)
        if sample is None or not 0 <= now - sample.t <= p.max_state_age_s:
            return None, self._link_event(t, "STALE_POSE", "Tư thế từ nguồn định vị cũ hoặc thiếu: dừng và chờ "
                                                           "đánh giá lại")
        return VehicleState(sample.pose, speed, tel.steer_rad, t, source_id=self._state_source(sample)), None

    def _command_row(self, t: float, kind: str, sent: bool, seq, speed: float, steer: float,
                     out: TrackerOutput | None, observed: VehicleState | None, note: str = "") -> dict:
        io = self.io
        tel = io.latest() if io is not None else None
        sample_id = self.pose_source.source_id if self.pose_source is not None else ""
        return {
            "t_session": round(t, 4), "t_io": io.now() if io is not None else "", "mode": self.mode.value,
            "kind": kind, "sent": int(sent), "seq": _blank(seq), "target_speed_mps": speed,
            "target_steer_rad": steer, "target_steer_deg": math.degrees(steer),
            "phase": out.phase if out else "", "segment": out.segment if out else "",
            "index": out.index if out else "", "distance_to_end_m": out.distance_to_end if out else "",
            "lateral_error_m": out.lateral_error if out else "",
            "heading_error_deg": math.degrees(out.heading_error) if out else "",
            "done": int(out.done) if out else "",
            "obs_x": observed.pose.x if observed else "", "obs_y": observed.pose.y if observed else "",
            "obs_yaw_deg": math.degrees(observed.pose.yaw) if observed else "",
            "obs_speed_mps": observed.speed if observed else "",
            "obs_steer_deg": math.degrees(observed.steer) if observed else "",
            "telemetry_age_s": (io.now() - tel.stamp.t) if tel is not None else "",
            "pose_source": sample_id, "pose_simulated": int(self.pose_simulated), "note": note,
        }

    def command(self, t: float, out: TrackerOutput, observed: VehicleState) -> SafetyEvent | None:
        """Một nhịp điều khiển. VEHICLE_IO: gửi COMMAND enable có thời hạn. OBSERVE: chỉ ghi log, KHÔNG gửi."""
        self.suggestion = out
        if self.observe_only:
            self.command_rows.append(self._command_row(t, "TRACK", False, None, out.target_speed, out.target_steer,
                                                       out, observed, "quan sát: không gửi"))
            return None
        if self._halted or self._pending:
            # Không bao giờ xảy ra khi Session đúng luật (đã sang STOPPING, và `refresh()` + `take_events()` chạy trước
            # nhịp điều khiển); chặn thêm một lớp: còn sự kiện dừng chưa được Session lấy thì cũng không gửi enable.
            self.command_rows.append(self._command_row(t, "TRACK", False, None, out.target_speed, out.target_steer,
                                                       out, observed, "đã dừng: không gửi enable"))
            self._halted = True
            return self._link_event(t, "HALTED",
                                    "Lần chạy đã dừng hoặc có sự kiện dừng chưa xử lý: không gửi lệnh chạy")
        try:
            seq = self.io.send(out.target_speed, out.target_steer, validity_s=self.params.command_validity_s)
        except (VehicleIOError, ValueError) as exc:
            self.command_rows.append(self._command_row(t, "TRACK", False, None, out.target_speed, out.target_steer,
                                                       out, observed, f"{SEND_FAILED_NOTE}{exc}"))
            self._halted = True
            return self._link_event(t, "SEND_FAILED", f"Không gửi được lệnh: {exc}")
        self._run_cmd_seqs.add(seq)
        self.command_rows.append(self._command_row(t, "TRACK", True, seq, out.target_speed, out.target_steer,
                                                   out, observed))
        return None

    def command_stop(self, t: float) -> None:
        """Nhịp điều khiển trong lúc dừng. VEHICLE_IO: COMMAND enable=0 (bo dốc về trung tính). OBSERVE: không gửi."""
        self._halted = True
        if self._stop_started is None:
            self._stop_started = t
        self.suggestion = None
        if self.observe_only:
            self.command_rows.append(self._command_row(t, "STOP", False, None, 0.0, 0.0, None, None,
                                                       "quan sát: không gửi"))
            return
        seq, note = None, ""
        try:
            seq = self.io.stop(validity_s=self.params.command_validity_s)
        except (VehicleIOError, ValueError) as exc:
            note = f"{SEND_FAILED_NOTE}{exc}"
        self.command_rows.append(self._command_row(t, "STOP", seq is not None, seq, 0.0, 0.0, None, None, note))

    def stop_timed_out(self, t: float) -> bool:
        return self._stop_started is not None and t - self._stop_started >= self.params.stop_confirm_timeout_s

    def end_run(self, t: float, outcome: str, reason: str) -> None:
        """Kết thúc lần chạy. VEHICLE_IO: COMMAND enable=0 rồi DISARM (lần sau phải ARM lại lúc START).
        OBSERVE: không gửi gì."""
        if not self._running:
            return
        self._running = False
        self._halted = True
        self.suggestion = None
        io = self.io
        if self.mode == DriveMode.VEHICLE_IO and io is not None and io.connected:
            for action in (lambda: io.stop(validity_s=self.params.command_validity_s),
                           lambda: io.disarm(timeout_s=self.params.disarm_timeout_s)):
                try:
                    action()
                except (VehicleIOError, ValueError) as exc:
                    self._log_event(io.now(), None, "vehicle_link", "END_RUN_SEND_FAILED", "LOG", "log", str(exc))
        tel = io.latest() if io is not None else None
        self.result = {"t_session": t, "outcome": outcome, "reason": reason,
                       "board_state": tel.state.name if tel is not None else None,
                       "commands_sent": io.stats.commands_sent if io is not None else 0,
                       "telemetry_received": io.stats.telemetry_received if io is not None else 0}

    # ------------------------------------------------------------------ xóa lỗi bo (T15, thêm 02/10/2026)
    @property
    def clear_fault_blocker(self) -> str | None:
        """Lý do `clear_fault()` bị chặn; None = được phép. Kiểm theo thứ tự: liên kết đã đóng, đang có lần chạy
        (`_running` phủ cả RUNNING lẫn STOPPING), bo mô phỏng của giao diện, chưa có io."""
        if self._closed:
            return "liên kết VehicleIO đã đóng"
        if self._running:
            return "đang có lần chạy: chỉ xóa lỗi khi lần chạy đã kết thúc"
        if self._simulated:
            return ("bo mô phỏng của giao diện được tạo mới (DISARMED) mỗi lần Bắt đầu đỗ, không có lỗi để xóa; nút "
                    "dùng với bo chọn ở cổng COM")
        if self.io is None:
            return "liên kết chưa có VehicleIO"
        return None

    def clear_fault(self, *, request_timeout_s: float | None = None) -> BoardFaultClear:
        """"Xóa lỗi bo (CLEAR_FAULT)" trên VehicleIO của CHÍNH liên kết này, ngoài lần chạy (T15).

        Dùng io của liên kết chứ không dùng io tạm như "Kiểm kết nối bo": khi cổng được giữ mở giữa các lần chạy (T2),
        mở cổng lần hai sẽ hỏng trên Windows; t_io của dòng log cùng đồng hồ với log của liên kết. Bị chặn
        (`clear_fault_blocker`) thì ném `VehicleLinkError` và không ghi gì.

        Cổng serial chưa mở (`SerialVehicleIO.deferred` của giao diện) thì `reopen()` rồi đóng lại khi xong: chọn cổng
        vẫn không mở cổng, "Kiểm kết nối bo" vẫn mở được cổng. io đã mở sẵn (tiêm vào, hoặc T2 sau này) thì không đóng.
        Đã có phiên thì dùng lại, không HELLO, nhưng gửi một PING và chờ ACK trước khi đọc trạng thái (rào "khung mới",
        xem `_clear_fault_on`); chưa có phiên, hoặc laptop đã chốt mất liên lạc (`rearm_required`), thì HELLO mở phiên
        mới (bo giữ FAULT; khung của phiên cũ bị bỏ). Quyết định theo khung telemetry ĐẦU TIÊN bo gửi sau lúc bấm: bo
        không FAULT → không gửi CLEAR_FAULT; cờ ESTOP_INPUT = 1 → không gửi CLEAR_FAULT; còn lại gửi đúng một REQUEST
        CLEAR_FAULT (firmware tự kiểm lại: ESTOP_ACTIVE, FAULT_ACTIVE) rồi đọc khung kế tiếp để xác nhận. KHÔNG BAO GIỜ
        ARM, không COMMAND nào (kể cả enable=0, kể cả ở OBSERVE); REQUEST khác có thể ra là PING rào ở trên (không đổi
        trạng thái bo) và DISARM mà VehicleIO tự gửi khi mất liên lạc (TELEMETRY_STALE), như "Kiểm kết nối bo".

        Không ném `VehicleIOError`: lỗi liên lạc nằm trong báo cáo. Mỗi lần gọi không bị chặn thêm đúng một dòng vào
        `board_actions`. Sự kiện VehicleIO gom được trong lúc này vào báo cáo và cột message của dòng đó, không thành
        dòng before_start của lần START sau. Chỉ thử với bo mô phỏng và cổng serial GIẢ; CHƯA THỬ với ESP32-S3."""
        blocker = self.clear_fault_blocker
        if blocker is not None:
            raise VehicleLinkError(f"Không xóa lỗi bo: {blocker}")
        io = self.io
        opened_here = isinstance(io, SerialVehicleIO) and io.transport is None
        if opened_here:
            try:
                io.reopen()
            except Exception as exc:          # SerialException (OSError), VehicleIOError, ValueError, ImportError...
                target = io.port or "cổng serial"
                report = BoardFaultClear(target, False, error=f"Không mở được {target}: {exc}")
                report.stamp(io)
                self.board_actions.append(report.to_row())
                return report
        close_error: OSError | None = None
        try:
            report = self._clear_fault_on(io, request_timeout_s)
        finally:
            if opened_here:
                try:
                    io.close()                # cổng trở lại "chưa mở", như lúc mới chọn
                except OSError as exc:
                    io.transport = None       # bỏ đối tượng cổng lỗi: lần bấm sau mở lại từ đầu
                    close_error = exc
        if close_error is not None:
            report.error = report.error or f"Lỗi khi đóng cổng: {close_error}"
        self.board_actions.append(report.to_row())
        return report

    def _clear_fault_on(self, io: VehicleIO, request_timeout_s: float | None) -> BoardFaultClear:
        """Một lần xóa lỗi trên io đã mở (xem `clear_fault`). Lỗi liên lạc trước bước quyết định: giữ NO_LINK.

        Rào "khung mới" trước khi đọc khung quyết định (`_await_frame` tự nó không bảo đảm khung là khung mới): phiên
        mới thì chính HELLO_ACK là rào (khung của phiên cũ bị bỏ); dùng lại phiên thì PING rồi chờ ACK. Bo gửi ACK và
        telemetry trên CÙNG một luồng byte, đúng thứ tự, nên khi ACK tới thì mọi khung cũ đứng trước nó đã được đọc (cả
        phần tồn đọng dài hơn một lần đọc `PUMP_MAX_BYTES`, cả phần còn trong bộ đệm của cổng hay của bo), và khung đọc
        ở các lần đọc SAU là bo gửi sau khi xử lý PING, tức sau lúc bấm. Sửa sau review 02/10/2026: trước đó chỉ có một
        lần đọc không chờ, nên với cổng giữ mở giữa các lần chạy (T2) khung DISARMED cũ tới muộn có thể thành căn cứ
        quyết định và báo NOT_NEEDED khi bo đang FAULT. Bo không ACK PING (hết giờ, bo không còn phiên này): NO_LINK,
        bấm lại."""
        p = self.params
        simulated = isinstance(io, SimVehicleIO)
        report = BoardFaultClear(getattr(io, "port", None) or ("bo mô phỏng" if simulated else type(io).__name__),
                                 simulated)
        report.stamp(io)                      # lúc bấm; thay bằng lúc quyết định nếu tới được bước đó
        commands0, requests0 = io.stats.commands_sent, io.stats.requests_sent
        try:
            if io.connected and not io.rearm_required:
                report.session_reused = True
                io.ping(wait=True)            # rào "khung mới": xem docstring; PING không đổi trạng thái bo
            else:
                # Chưa có phiên, hoặc laptop đã chốt mất liên lạc (TELEMETRY_STALE): mở phiên mới. Bo vừa khởi động lại
                # chỉ trả NO_SESSION cho REQUEST và không gửi telemetry, nên chờ khung trên phiên cũ là vô ích.
                frames0, hello_before = io.stats.frames_sent, io.hello
                try:
                    report.hello = io.connect(timeout_s=p.connect_timeout_s)   # HELLO giữ FAULT: bo không tự xóa lỗi
                except VehicleIOError:
                    if io.hello is not None and io.hello is not hello_before:
                        report.hello = io.hello   # có HELLO_ACK nhưng phiên bị từ chối: vẫn báo firmware/boot_id
                    raise
                finally:
                    report.hello_sent = io.stats.frames_sent > frames0
            report.before = before = _await_frame(io, p.fresh_timeout_s)
            report.stamp(io)
            if before.state != State.FAULT and before.fault == Fault.NONE:
                report.outcome = "NOT_NEEDED"
            elif before.estop_input:
                report.outcome = "ESTOP_PRESSED"
            else:
                self._send_clear_fault(io, report, request_timeout_s)
        except VehicleIOError as exc:
            report.error = str(exc)
        finally:
            report.events = io.events()       # như probe_board: vào báo cáo, không thành dòng before_start lần sau
            report.commands_sent = io.stats.commands_sent - commands0
            report.requests_sent = io.stats.requests_sent - requests0
        return report

    def _send_clear_fault(self, io: VehicleIO, report: BoardFaultClear, request_timeout_s: float | None) -> None:
        """Gửi REQUEST CLEAR_FAULT, chờ ACK, rồi đọc khung kế tiếp. Chỉ CLEARED khi ACK OK VÀ khung sau báo hết lỗi."""
        requests0 = io.stats.requests_sent
        try:
            io.clear_fault(timeout_s=request_timeout_s)
            report.ack_result = "OK"
        except VehicleIOError as exc:
            if exc.result is None:            # hết giờ chờ ACK, hoặc lỗi cổng
                report.outcome, report.error = "NO_ACK", str(exc)
            else:
                report.outcome = "REFUSED"
                report.ack_result = exc.result.name if isinstance(exc.result, Result) else f"RESULT_{exc.result}"
        report.sent = io.stats.requests_sent > requests0
        if not report.sent:                   # không ghi được khung ra cổng, hoặc phiên vừa mất
            report.outcome = "NO_LINK"
            return
        try:
            report.after = _await_frame(io, self.params.fresh_timeout_s)
        except VehicleIOError as exc:
            report.error = report.error or str(exc)
        if report.ack_result == "OK":
            after = report.after
            report.outcome = ("CLEARED" if after is not None and after.state != State.FAULT
                              and after.fault == Fault.NONE else "NOT_CONFIRMED")

    # ------------------------------------------------------------------ log
    def write_logs(self, directory: str | Path) -> dict[str, Path]:
        """Ghi tám tệp vào thư mục: commands.csv, telemetry.csv, events.csv, poses.csv, clock.csv (của lần chạy gần
        nhất đã mở), start_refusals.csv (mọi lần START bị từ chối của liên kết này), board_actions.csv (mọi lần "Xóa lỗi
        bo" của liên kết này, T15) và link.json. Hai tệp cộng dồn luôn được tạo, có thể chỉ có dòng tiêu đề.

        T13 (02/10/2026): events.csv có cả dòng `session_stop` (quyết định dừng của phiên) và cột t_perf (cả
        start_refusals.csv); link.json có thêm khóa "clock" (cặp t_io/perf_counter lúc mở lần chạy, xem docstring của
        mô-đun). Khóa này không nằm trong `describe()`, nên snapshot của lần chạy không đổi.

        T9 (02/10/2026): băng phát lại log: poses.csv, clock.csv, cột call của telemetry.csv và events.csv; link.json có
        thêm "run_start" (None khi chưa mở lần chạy nào), "log_format" (`LOG_FORMAT`) và, qua `describe()`,
        "io_source_id"."""
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        written = {}
        for name, fields, rows in (("commands.csv", COMMAND_FIELDS, self.command_rows),
                                   ("telemetry.csv", TELEMETRY_FIELDS, self.telemetry_rows),
                                   ("events.csv", EVENT_FIELDS, self.event_rows),
                                   ("start_refusals.csv", EVENT_FIELDS, self.start_refusals),
                                   ("board_actions.csv", BOARD_ACTION_FIELDS, self.board_actions),
                                   ("poses.csv", POSE_FIELDS, self.pose_rows),
                                   ("clock.csv", CLOCK_FIELDS, self.clock_rows)):
            target = path / name
            with target.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            written[name] = target
        info = dict(self.describe(), result=self.result, runs=self.runs, refused_starts=self.refused_starts,
                    stats=asdict(self.io.stats) if self.io is not None else None,
                    clock={"t_io_at_start": None if self._perf_t0 is None else self._io_t0,
                           "t_perf_at_start": self._perf_t0},
                    run_start=self.run_start, log_format=LOG_FORMAT)
        target = path / "link.json"
        target.write_text(json.dumps(info, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        written["link.json"] = target
        return written

    def close(self) -> None:
        """Đóng liên kết. VEHICLE_IO còn phiên: COMMAND enable=0 và DISARM trước khi đóng cổng."""
        if self._closed:
            return
        self._closed = True
        io = self.io
        if io is None:
            return
        if self.mode == DriveMode.VEHICLE_IO and io.connected:
            for action in (lambda: io.stop(), lambda: io.disarm(timeout_s=self.params.disarm_timeout_s)):
                try:
                    action()
                except (VehicleIOError, ValueError):
                    pass
        try:
            io.close()
        except OSError:
            pass


# ---------------------------------------------------------------------- "Kiểm kết nối bo" (thêm 24/09/2026)
@dataclass
class BoardProbe:
    """Kết quả một lần "Kiểm kết nối bo": HELLO_ACK, vài khung telemetry, so giới hạn, sự kiện, số khung đã gửi."""

    target: str                                   # "COM5" hoặc "bo mô phỏng"
    simulated: bool
    hello: HelloInfo | None = None
    frames: list[VehicleTelemetry] = field(default_factory=list)
    limits: LimitsCheck | None = None
    events: list[SafetyEvent] = field(default_factory=list)
    error: str | None = None
    commands_sent: int = 0                        # phải luôn 0: kiểm kết nối không gửi COMMAND nào
    requests_sent: int = 0                        # REQUEST (chỉ có thể là DISARM do VehicleIO tự gửi khi mất liên lạc)
    frames_wanted: int = 0

    @property
    def ok(self) -> bool:
        return self.error is None and self.hello is not None and len(self.frames) >= self.frames_wanted

    def lines(self) -> list[str]:
        """Báo cáo tiếng Việt, mỗi phần tử một dòng (giao diện hiển thị nguyên văn)."""
        kind = "bo MÔ PHỎNG (SimVehicleIO + FirmwareModel)" if self.simulated else "bo thật qua cổng serial"
        out = [f"Kiểm kết nối: {self.target} — {kind}. Chỉ HELLO, không ARM, không gửi lệnh chuyển động."]
        h = self.hello
        if h is None:
            out.append("Không nhận được HELLO_ACK.")
        else:
            lim = h.limits
            out.append(f"HELLO_ACK: firmware {h.firmware_version}, boot_id {h.boot_id:08x}, lý do reset "
                       f"{h.reset_reason}, trạng thái {h.state.name}, chu kỳ telemetry "
                       f"{h.telemetry_period_s * 1000:.0f} ms.")
            out.append(f"Giới hạn bo: {lim.max_speed_mps * 1000:.0f} mm/s, "
                       f"lái ±{math.degrees(lim.max_steer_rad):.1f}°, "
                       f"đổi lái {math.degrees(lim.max_steer_rate_rad_s):.0f}°/s, tăng tốc "
                       f"{lim.max_accel_mps2 * 1000:.0f} mm/s², giảm tốc {lim.max_decel_mps2 * 1000:.0f} / dừng "
                       f"{lim.stop_decel_mps2 * 1000:.0f} mm/s², hạn lệnh ≤ {lim.max_validity_s * 1000:.0f} ms, "
                       f"watchdog liên lạc {lim.link_timeout_s * 1000:.0f} ms.")
        if self.limits is not None:
            if self.limits.ok:
                out.append(self.limits.describe() + ".")
            else:
                verdict = ("START ở VEHICLE_IO sẽ bị TỪ CHỐI" if self.limits.risky
                           else "chỉ cảnh báo, START không bị chặn vì giới hạn")
                out.append(f"LIMITS_MISMATCH ({verdict}): {self.limits.describe()}.")
        out.append(f"Telemetry: {len(self.frames)}/{self.frames_wanted} khung.")
        for tel in self.frames:
            speed = "—" if tel.speed_mps is None else f"{tel.speed_mps:+.3f} m/s"
            steer = "—" if tel.steer_rad is None else f"{math.degrees(tel.steer_rad):+.1f}°"
            supply = "—" if tel.supply_v is None else f"{tel.supply_v:.2f} V"
            tof = " ".join("—" if v is None else f"{v:.3f}" for v in tel.tof_m)
            out.append(f"  #{tel.sequence} t_bo {tel.device_time_ms} ms: {tel.state.name}, lỗi {tel.fault.name}, "
                       f"tốc độ {speed}, lái {steer}, E-stop {'NHẤN' if tel.estop_input else 'không'}, "
                       f"nguồn {supply}, ToF [m] {tof}")
        for ev in self.events:
            out.append(f"Sự kiện {ev.code} ({ev.action}): {ev.message}")
        out.append(f"Đã gửi: {self.commands_sent} COMMAND, {self.requests_sent} REQUEST (HELLO không tính). "
                   f"Đã đóng kết nối.")
        if self.error:
            out.append(f"LỖI: {self.error}")
        return out


def probe_board(io: VehicleIO, cfg: VehicleConfig, *, target: str = "", frames: int = 5,
                connect_timeout_s: float = 1.0, frames_timeout_s: float = 1.0) -> BoardProbe:
    """"Kiểm kết nối bo": `connect()` (HELLO; bo về DISARMED hoặc giữ BOOT/FAULT), đọc tới `frames` khung telemetry
    trong `frames_timeout_s` (đồng hồ io), so giới hạn với `cfg` (`check_limits`, có sự kiện `LIMITS_MISMATCH`), rồi
    ĐÓNG io. KHÔNG BAO GIỜ gọi `arm()`, `send()` hay `stop()`: không COMMAND nào, kể cả enable=0. REQUEST duy nhất có
    thể lọt ra là DISARM mà `VehicleIO` tự gửi khi mất liên lạc (TELEMETRY_STALE). Lỗi liên lạc (hết giờ, lỗi cổng)
    không ném ra mà ghi vào `error`; io luôn được đóng. Bo đã trả HELLO_ACK nhưng `connect()` không nhận phiên (chu kỳ
    telemetry quá dài): báo cáo vẫn có HELLO_ACK và kết quả so giới hạn, `error` nói phiên bị từ chối. Mới thử với bo
    mô phỏng và cổng serial GIẢ; CHƯA THỬ với ESP32-S3 (24/09/2026)."""
    if not isinstance(frames, int) or isinstance(frames, bool) or frames < 1:
        raise ValueError("frames phải là số nguyên >= 1")
    simulated = isinstance(io, SimVehicleIO)
    report = BoardProbe(target or getattr(io, "port", None) or ("bo mô phỏng" if simulated else type(io).__name__),
                        simulated, frames_wanted=frames)
    commands0, requests0 = io.stats.commands_sent, io.stats.requests_sent
    hello_before = io.hello              # HELLO_ACK của phiên cũ (nếu có) không được báo như của lần kiểm này
    try:
        report.hello = io.connect(timeout_s=connect_timeout_s)
        report.limits = io.check_limits(cfg)
        deadline = io.now() + frames_timeout_s
        while len(report.frames) < frames and io.now() < deadline and io.connected:
            report.frames.extend(io.poll())
        report.frames = report.frames[:frames]
        if len(report.frames) < frames:
            report.error = (f"Chỉ nhận {len(report.frames)}/{frames} khung telemetry trong {frames_timeout_s:.1f} s"
                            + ("" if io.connected else " (mất phiên hoặc lỗi cổng)"))
    except VehicleIOError as exc:
        report.error = str(exc)
        if report.hello is None and io.hello is not None and io.hello is not hello_before:
            # connect() đã nhận HELLO_ACK của lần kiểm này rồi mới từ chối phiên (vd. bo chọn chu kỳ telemetry quá dài
            # so với telemetry_timeout_s): vẫn báo firmware/boot_id/giới hạn để chẩn đoán (sửa muộn tối 24/09/2026).
            # check_limits chỉ đọc hello, không gửi gì tới bo; `ok` vẫn False vì có lỗi.
            report.hello = io.hello
            report.limits = io.check_limits(cfg)
            report.error = f"HELLO_ACK nhận được nhưng phiên bị từ chối: {exc}"
    finally:
        report.events = io.events()
        report.commands_sent = io.stats.commands_sent - commands0
        report.requests_sent = io.stats.requests_sent - requests0
        try:
            io.close()
        except OSError as exc:
            report.error = report.error or f"Lỗi khi đóng cổng: {exc}"
    return report


# ---------------------------------------------------------------------- "Xóa lỗi bo (CLEAR_FAULT)" (02/10/2026, T15)
CLEAR_FAULT_OUTCOMES = ("CLEARED", "NOT_NEEDED", "ESTOP_PRESSED", "REFUSED", "NOT_CONFIRMED", "NO_ACK", "NO_LINK")
# Lỗi nào firmware cũng xóa khi hết nguyên nhân (SUPPLY_LOW: khi điện áp đo lại đủ ngưỡng); báo cáo nêu cần kiểm gì.
_FAULT_NOTE = {
    Fault.ESTOP: "nút dừng khẩn",
    Fault.LOOP_OVERRUN: "vòng điều khiển của bo bị trễ",
    Fault.SUPPLY_LOW: "điện áp dưới ngưỡng",
    Fault.FEEDBACK_LOST: "mất phản hồi tốc độ khi đang chạy",
    Fault.STALL: "effort cao mà xe không đi theo: kiểm kẹt bánh, encoder đảo dấu trước khi chạy lại",
}
# Mã ACK khi bo từ chối CLEAR_FAULT → việc người dùng cần làm.
_REFUSAL_NOTE = {
    "ESTOP_ACTIVE": "bo thấy nút dừng khẩn đang nhấn: nhả nút rồi bấm lại",
    "FAULT_ACTIVE": "nguyên nhân lỗi còn; SUPPLY_LOW chỉ xóa được khi điện áp đo lại đủ ngưỡng",
    "NO_SESSION": "bo không còn phiên này, có thể vừa khởi động lại: bấm lại để mở phiên mới",
    "WRONG_SESSION": "bo đang ở phiên khác: bấm lại để mở phiên mới",
}


def _wall_time() -> str:
    """Giờ máy lúc gọi: ISO 8601 có độ lệch múi giờ, tới ms (để đối chiếu với biên bản và video)."""
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _reset_reason_text(value: int) -> str:
    """Lý do reset trong HELLO_ACK: tên `ResetReason` khi biết (POWER_ON, WATCHDOG...), không thì số thô."""
    return ResetReason(value).name if value in ResetReason._value2member_map_ else str(value)


def _frame_text(tel: VehicleTelemetry | None) -> str:
    """Một khung telemetry trong báo cáo xóa lỗi: số thứ tự, đồng hồ bo, trạng thái, lỗi (kèm ghi chú), E-stop."""
    if tel is None:
        return "không có khung telemetry mới"
    note = _FAULT_NOTE.get(tel.fault)
    return (f"#{tel.sequence} t_bo {tel.device_time_ms} ms: {tel.state.name}, lỗi {tel.fault.name}"
            f"{f' ({note})' if note else ''}, E-stop {'NHẤN' if tel.estop_input else 'không nhấn'}")


def _await_frame(io: VehicleIO, timeout_s: float) -> VehicleTelemetry:
    """Khung telemetry đầu tiên ĐỌC ĐƯỢC SAU lúc gọi (dấu thời gian là lúc laptop đọc cổng, đồng hồ io); quá `timeout_s`
    thì `VehicleIOError`.

    Hàm này KHÔNG tự bảo đảm khung là do bo gửi sau lúc gọi (sửa lời sau review 02/10/2026): lần đọc không chờ đầu hàm
    chỉ bỏ được phần đọc được trong lần đó (tối đa `PUMP_MAX_BYTES` trong `PUMP_MAX_S`); phần tồn đọng dài hơn, hay byte
    còn trong bộ đệm của bo, tới ở lần đọc sau và mang dấu thời gian muộn dù bo đã gửi từ trước. Người gọi phải đặt rào
    trước: một thông điệp bo trả lời trên cùng luồng byte (HELLO_ACK của phiên mới, ACK của PING hay của CLEAR_FAULT),
    xem `VehicleLink._clear_fault_on`. Dừng sớm khi `io.connected` thành False (lỗi cổng, bo không còn phiên): sau
    `_link_failed`, `service()` không đọc gì nữa, nên chờ tiếp thì với `ManualClock` là treo mãi, với đồng hồ thật là
    chờ bận vô ích. Vì vậy không dùng `VehicleLink._new_telemetry` (hàm đó giữ nguyên)."""
    io.service(block=False)
    after = io.now()
    deadline = after + timeout_s
    while io.connected:
        tel = io.latest()
        if tel is not None and tel.stamp.t > after:
            return tel
        if io.now() >= deadline:
            raise VehicleIOError(f"Không nhận được khung telemetry mới trong {timeout_s:.1f} s")
        io.service()
    raise VehicleIOError("Mất phiên với bo trong lúc chờ telemetry (lỗi cổng hoặc bo không còn phiên)")


@dataclass
class BoardFaultClear:
    """Kết quả một lần "Xóa lỗi bo (CLEAR_FAULT)" (`VehicleLink.clear_fault`): khung trước và sau, ACK, sự kiện, số
    khung đã gửi. `to_row()` là dòng board_actions.csv của lần bấm đó."""

    target: str                                   # "COM7", "bo mô phỏng", hoặc tên lớp io
    simulated: bool
    wall_time: str = ""                           # giờ máy (ISO 8601) đọc cùng lúc với t_io
    t_io: float | None = None                     # io.now() lúc quyết định gửi / không gửi (chưa tới bước đó: lúc bấm)
    t_perf: float | None = None                   # perf_counter() thô đọc liền sau t_io
    hello_sent: bool = False                      # đã gửi HELLO (io chưa có phiên, hoặc đã chốt mất liên lạc)
    session_reused: bool = False                  # dùng phiên đang có, không gửi HELLO
    hello: HelloInfo | None = None                # HELLO_ACK của lần bấm này (None khi dùng phiên đang có)
    before: VehicleTelemetry | None = None        # khung đầu tiên nhận sau lúc bấm: căn cứ quyết định
    sent: bool = False                            # REQUEST CLEAR_FAULT đã thật sự ghi ra (stats.requests_sent tăng)
    ack_result: str = ""                          # "OK", tên Result, hoặc "" (chưa gửi / không có ACK)
    after: VehicleTelemetry | None = None         # khung đầu tiên nhận sau ACK, lời từ chối hoặc hết giờ
    outcome: str = "NO_LINK"                      # một trong CLEAR_FAULT_OUTCOMES
    events: list[SafetyEvent] = field(default_factory=list)
    error: str | None = None
    # CLEAR_FAULT, PING rào khi dùng lại phiên, và DISARM do VehicleIO tự gửi khi mất liên lạc
    requests_sent: int = 0
    commands_sent: int = 0                        # phải luôn 0: xóa lỗi không gửi COMMAND nào

    @property
    def ok(self) -> bool:
        return self.outcome in ("CLEARED", "NOT_NEEDED")

    def stamp(self, io: VehicleIO) -> None:
        """Đặt ba mốc thời gian của dòng log, đọc liền nhau: io.now(), perf_counter() thô, giờ máy."""
        self.t_io = io.now()
        self.t_perf = time.perf_counter()
        self.wall_time = _wall_time()

    def summary(self) -> str:
        """Một câu tiếng Việt theo `outcome` (giao diện, thanh trạng thái và cột message của board_actions.csv)."""
        before, after, outcome = self.before, self.after, self.outcome
        if outcome == "CLEARED":
            boot = ("; bo còn trong thời gian giữ khởi động, sẽ tự sang DISARMED"
                    if after is not None and after.state == State.BOOT else "")
            return (f"Đã xóa lỗi: bo {after.state.name if after is not None else '?'}{boot}. Vẫn phải ARM (Bắt đầu đỗ) "
                    f"và có lệnh mới thì xe mới chạy; bánh xe không được quay sau thao tác này.")
        if outcome == "NOT_NEEDED":
            # "không gửi CLEAR_FAULT", không phải "không gửi gì": dùng lại phiên thì đã có PING rào (review 02/10/2026)
            return (f"Bo không ở FAULT ({before.state.name if before is not None else '?'}): không cần và không gửi "
                    f"CLEAR_FAULT.")
        if outcome == "ESTOP_PRESSED":
            return ("Nút dừng khẩn còn NHẤN (cờ ESTOP_INPUT; dây E-stop hở cũng đọc là nhấn): nhả nút rồi bấm lại. "
                    "Không gửi CLEAR_FAULT.")
        if outcome == "REFUSED":
            note = _REFUSAL_NOTE.get(self.ack_result)
            return f"Bo từ chối CLEAR_FAULT: {self.ack_result}{f' ({note})' if note else ''}."
        if outcome == "NOT_CONFIRMED":
            seen = "không tới" if after is None else f"vẫn báo {after.state.name}, lỗi {after.fault.name}"
            return f"Bo trả ACK OK nhưng khung telemetry sau đó {seen}: kiểm nút dừng khẩn rồi bấm lại."
        if outcome == "NO_ACK":
            seen = "" if after is None else f"; khung sau đó báo {after.state.name}, lỗi {after.fault.name}"
            return f"Không nhận được ACK của CLEAR_FAULT{seen}: trạng thái bo chưa chắc, bấm lại để kiểm."
        return "Không có liên lạc với bo: không gửi CLEAR_FAULT."

    def lines(self) -> list[str]:
        """Báo cáo tiếng Việt, mỗi phần tử một dòng (giao diện hiển thị nguyên văn, chọn và chép được)."""
        kind = "bo MÔ PHỎNG (SimVehicleIO + FirmwareModel)" if self.simulated else "bo qua cổng serial"
        out = [f"Xóa lỗi bo (CLEAR_FAULT): {self.target} — {kind}. Chỉ gửi CLEAR_FAULT khi bo đang FAULT và nút dừng "
               f"khẩn đã nhả; không ARM, không gửi lệnh chuyển động."]
        h = self.hello
        if h is not None:
            out.append(f"HELLO_ACK: firmware {h.firmware_version}, boot_id {h.boot_id:08x}, lý do reset "
                       f"{h.reset_reason}, trạng thái {h.state.name}.")
        elif self.session_reused:
            out.append("Dùng phiên đang có với bo (không gửi HELLO); gửi PING và chờ ACK trước khi đọc trạng thái, để "
                       "khung cũ còn trong cổng không thành căn cứ quyết định.")
        elif self.hello_sent:
            out.append("Đã gửi HELLO, không nhận được HELLO_ACK.")
        out.append(f"Trước: {_frame_text(self.before)}.")
        if self.sent:
            ack = ("không nhận được ACK" if not self.ack_result else
                   "ACK OK" if self.ack_result == "OK" else f"ACK {self.ack_result}")
            out.append(f"Đã gửi CLEAR_FAULT lúc t_io {self.t_io:.3f} s: {ack}.")
            out.append(f"Sau: {_frame_text(self.after)}.")
        for ev in self.events:
            out.append(f"Sự kiện {ev.code} ({ev.action}): {ev.message}")
        out.append(f"Đã gửi: {self.commands_sent} COMMAND, {self.requests_sent} REQUEST (HELLO không tính).")
        out.append(f"KẾT QUẢ: {self.summary()}")
        if self.error:
            out.append(f"LỖI: {self.error}")
        return out

    def to_row(self) -> dict:
        """Dòng board_actions.csv (khóa đúng bằng BOARD_ACTION_FIELDS).

        Sửa sau review 02/10/2026: sự kiện VehicleIO gom được trong lần bấm vào message ĐỦ (mã, action, t_io của sự
        kiện, lời), không chỉ mã: chúng không vào log nào khác, và t_io cho thấy sự kiện nào có từ trước lúc bấm. Bốn
        cột hello_* (nối cuối) giữ HELLO_ACK của lần bấm (trống khi dùng lại phiên hay không có HELLO_ACK): đổi boot_id
        giữa các dòng, hay lý do reset, phân biệt "bo khởi động lại khi mở cổng" với "đã xóa bằng CLEAR_FAULT"."""
        before, after, hello = self.before, self.after, self.hello
        message = self.summary()
        if self.error:
            message += f" | LỖI: {self.error}"
        if self.events:
            message += " | sự kiện: " + "; ".join(f"{ev.code} ({ev.action}, t_io {ev.stamp.t:.3f}): {ev.message}"
                                                  for ev in self.events)
        return {"t_io": _blank(self.t_io), "t_perf": _blank(self.t_perf), "wall_time": self.wall_time,
                "target": self.target, "request": "CLEAR_FAULT", "outcome": self.outcome,
                "ack_result": self.ack_result,
                "state_before": before.state.name if before is not None else "",
                "fault_before": before.fault.name if before is not None else "",
                "estop_before": int(before.estop_input) if before is not None else "",
                "state_after": after.state.name if after is not None else "",
                "fault_after": after.fault.name if after is not None else "",
                "requests_sent": self.requests_sent, "commands_sent": self.commands_sent, "message": message,
                "hello_firmware": hello.firmware_version if hello is not None else "",
                "hello_boot_id": f"0x{hello.boot_id:08x}" if hello is not None else "",
                "hello_reset_reason": _reset_reason_text(hello.reset_reason) if hello is not None else "",
                "hello_state": hello.state.name if hello is not None else ""}
