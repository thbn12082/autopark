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
"""
from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Protocol

from autopark.control.tracker import TrackerOutput
from autopark.domain.sensors import SafetyEvent, SourceStamp
from autopark.domain.types import Pose, Scenario, VehicleConfig, VehicleState, clamp, wrap_angle
from autopark.geometry.footprint import check_motion, check_pose
from autopark.simulation.world import SimWorld, StepResult
from autopark.transport.protocol import Fault, State, TelemetryFlag
from autopark.transport.vehicle_io import SimIOConfig, SimVehicleIO, VehicleIO, VehicleIOError, VehicleTelemetry


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
TELEMETRY_FIELDS = ["t_session", "t_io", "device_time_ms", "sequence", "state", "fault", "stop_reason", "flags",
                    "link_ok", "estop_input", "cmd_active", "speed_mps", "steer_rad", "speed_ref_mps",
                    "steer_ref_rad", "effort", "last_cmd_seq", "cmd_age_s", "supply_v", "rx_errors", "rejects"]
EVENT_FIELDS = ["t_session", "t_io", "source", "code", "action", "handling", "message"]

# Sự kiện VehicleIO mang action "LOG" nhưng trong lúc TỰ ĐỖ qua VehicleIO nghĩa là bo không còn chạy theo lệnh
# của laptop: coi là dừng. (Ở chế độ quan sát không có lệnh nào nên không nâng mức.)
_VEHICLE_IO_STOP_CODES = {"COMMAND_REJECTED", "VEHICLE_STOPPED"}


def _blank(value):
    return "" if value is None else value


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
        # Dòng sự kiện (EVENT_FIELDS) của các lần START bị từ chối, cộng dồn suốt đời liên kết; không đè log của lần
        # chạy trước.
        self.start_refusals: list[dict] = []
        self.refused_starts = 0           # số lần START bị từ chối
        self.runs = 0
        self.result: dict | None = None
        self.suggestion: TrackerOutput | None = None
        self._reset_run_state()

    @classmethod
    def simulated(cls, mode: DriveMode | str, sim_config: SimIOConfig | None = None, *,
                  params: LinkParams | None = None) -> "VehicleLink":
        return cls(mode, params=params, sim_config=sim_config or SimIOConfig(), _simulated=True)

    def _reset_run_state(self) -> None:
        self._io_t0 = 0.0
        self._pending: list[SafetyEvent] = []
        self._run_cmd_seqs: set[int] = set()
        self._stop_started: float | None = None
        self._halted = False              # đã có lệnh dừng/sự kiện dừng: lần chạy này không gửi enable nữa
        self._guard_reported = False
        self._running = False

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
            "io_simulated": self._simulated or isinstance(self.io, SimVehicleIO),
            "pose_source": source.source_id if source is not None else (
                SimTruthPose.source_id if self._simulated else None),
            "pose_simulated": self.pose_simulated,
            "params": asdict(self.params),
            "sim_config": self.sim_config.to_dict() if self.sim_config is not None else None,
            "evidence": ("simulation_only" if (self._simulated or isinstance(self.io, SimVehicleIO))
                         else "hardware_untested"),
        }

    # ------------------------------------------------------------------ bắt đầu lần chạy
    def _t_session(self, t_io: float) -> float:
        return t_io - self._io_t0

    def _link_event(self, t: float, code: str, message: str, action: str = "STOP") -> SafetyEvent:
        return SafetyEvent(SourceStamp("vehicle_link", max(0.0, t)), code, message, action)

    def _log_event(self, t_io: float | None, t_session: float | None, source: str, code: str, action: str,
                   handling: str, message: str) -> None:
        self.event_rows.append({"t_session": _blank(None if t_session is None else round(t_session, 4)),
                                "t_io": _blank(t_io), "source": source, "code": code, "action": action,
                                "handling": handling, "message": message})

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
            problems.append(f"Bo đang FAULT ({tel.fault.name}): xử lý nguyên nhân rồi CLEAR_FAULT")
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
        self._reset_run_state()
        self.command_rows.clear()
        self.telemetry_rows.clear()
        self.event_rows = staged
        self.result = None
        self.suggestion = None
        self._io_t0 = self.io.now()
        self._running = True
        self.runs += 1
        return world

    def _open_run(self, scenario: Scenario, cfg: VehicleConfig, dt: float) -> MirroredWorld:
        io = self.io
        p = self.params
        try:
            if not io.connected:
                io.connect(timeout_s=p.connect_timeout_s)
            io.wait_ready(timeout_s=p.ready_timeout_s)
            samples = self._new_telemetry(io.now(), p.start_samples)
        except VehicleIOError as exc:
            self._log_event(io.now(), None, "vehicle_link", "START_NO_LINK", "LOG", "before_start", str(exc))
            raise VehicleLinkError(f"Không có liên lạc với bo: {exc}") from exc
        for ev in io.events():            # sự kiện cũ: ghi lại, không làm dừng lần chạy mới
            self._log_event(ev.stamp.t, None, ev.stamp.source_id, ev.code, ev.action, "before_start", ev.message)
        problems, summary = self._start_problems(samples, scenario, cfg)
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
        phiên chậm hơn `io.now()`)."""
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

    def refresh(self) -> None:
        """Lấy telemetry và sự kiện ĐÃ tới, không tiến thời gian: bo thật `poll(block=False)` (chỉ byte có sẵn); bo mô
        phỏng chỉ lấy hàng đợi hiện có (`take_new()`), không chạy thêm nhịp nào. `Session` gọi hàm này đầu mỗi bước khi
        đang chạy, TRƯỚC nhịp điều khiển.

        Sửa tối 24/09/2026 (khoảng trống an toàn, tìm thấy trên mô phỏng): trước đó sự kiện chỉ được gom trong `pump()`,
        chạy SAU nhịp điều khiển. Vòng điều khiển treo lâu hơn hạn lệnh trong khi Heartbeat vẫn giữ liên lạc thì bo về
        ARMED (COMMAND_TIMEOUT) mà telemetry vẫn mới; bước đầu tiên sau khi hết treo rơi đúng nhịp điều khiển thì gửi MỘT
        COMMAND enable=1 (bo ARMED → RUNNING) trước khi thấy VEHICLE_STOPPED. Mô hình bo với lệnh dừng tới sau 10–40 ms
        cho effort 107–130 ‰."""
        io = self.io
        if io is None:
            return
        if isinstance(io, SimVehicleIO):
            self._on_telemetry(io.take_new())
        else:
            self._on_telemetry(io.poll(block=False))
        self._collect_events()

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
                "rx_errors": tel.rx_errors, "rejects": tel.rejects})
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
            self._log_event(ev.stamp.t, t, ev.stamp.source_id, ev.code, ev.action, handling, ev.message)
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

    def estimate(self, t: float, prev: VehicleState) -> VehicleState:
        """Trạng thái cho thế giới gương: tư thế từ nguồn định vị, tốc độ/góc lái đo; thiếu thì giữ giá trị trước."""
        pose = prev.pose
        source = prev.source_id
        sample = self.pose_source.latest() if self.pose_source is not None else None
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
        sample = self.pose_source.latest()
        # Đọc đồng hồ SAU khi lấy mẫu: với đồng hồ mịn (bo thật), mẫu đóng dấu io.now() bên trong latest() luôn muộn
        # hơn một `now` đọc trước đó vài µs và sẽ bị coi nhầm là mẫu "ở tương lai" (tuổi âm) → STALE_POSE giả.
        now = io.now()
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
                                                       out, observed, f"gửi lỗi: {exc}"))
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
            note = f"gửi lỗi: {exc}"
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

    # ------------------------------------------------------------------ log
    def write_logs(self, directory: str | Path) -> dict[str, Path]:
        """Ghi commands.csv, telemetry.csv, events.csv (của lần chạy gần nhất đã mở), start_refusals.csv (mọi lần
        START bị từ chối của liên kết này; luôn tạo, có thể chỉ có dòng tiêu đề) và link.json vào thư mục."""
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        written = {}
        for name, fields, rows in (("commands.csv", COMMAND_FIELDS, self.command_rows),
                                   ("telemetry.csv", TELEMETRY_FIELDS, self.telemetry_rows),
                                   ("events.csv", EVENT_FIELDS, self.event_rows),
                                   ("start_refusals.csv", EVENT_FIELDS, self.start_refusals)):
            target = path / name
            with target.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            written[name] = target
        info = dict(self.describe(), result=self.result, runs=self.runs, refused_starts=self.refused_starts,
                    stats=asdict(self.io.stats) if self.io is not None else None)
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
