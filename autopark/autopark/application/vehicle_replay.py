"""Phát lại log của lần chạy qua VehicleIO (T9, thêm 02/10/2026; chỉ kiểm với bo mô phỏng và cổng serial GIẢ, CHƯA
THỬ với bo thật).

Gói SIM được TÁI MÔ PHỎNG (`storage/run_store.py` `replay_run`). Lần chạy qua `VehicleIO` (VEHICLE_IO hoặc quan sát
OBSERVE) thì không tái mô phỏng được: trạng thái của nó lấy từ telemetry và nguồn tư thế; tay người lái (OBSERVE) và
lỗi gây ra phía xe không được ghi. "Phát lại log" ở đây là chạy lại CÙNG phần mềm (Session → VehicleLink →
TrajectoryTracker → MirroredWorld, mã không đổi), vòng hở, trên ĐẦU VÀO đã ghi, đúng thứ tự, qua một VehicleIO "băng"
(`ReplayVehicleIO`) và một nguồn tư thế "băng" (`ReplayPoseSource`). Lệnh tính ra không đi đâu cả. Đầu vào đã ghi là
băng của `VehicleLink.write_logs` (log_format 2):

- mỗi lần đọc io của lớp nối (`refresh` đầu bước khi đang chạy, `pump` cuối bước): đúng các khung telemetry và sự kiện
  VehicleIO mà lần đọc đó trả (cột `call` của telemetry.csv, events.csv), và đồng hồ io sau lần đọc (clock.csv);
- mỗi lần `pose_source.latest()` trong lần chạy: mẫu đã ghi và đồng hồ io đọc liền sau mẫu (poses.csv);
- mỗi lần `send()`/`stop()`: số thứ tự hoặc lời lỗi đã ghi, và đồng hồ đọc liền sau (commands.csv);
- vật cản chèn vào và yêu cầu dừng khi đang chạy (events.jsonl của gói), chèn lại đúng bước như nhánh SIM.

So với bản ghi: lệnh (commands.csv), dòng telemetry và sự kiện của lớp nối và của phiên (telemetry.csv, events.csv), sự
kiện an toàn của phiên (safety_events.json), kết quả cuối (result.json, kết quả trong link.json), RunLog của thế giới
gương (telemetry.csv của gói) và sự thẳng hàng của đầu vào (poses.csv, clock.csv). Không tái hiện: bước kiểm START
(kết nối, HELLO, so giới hạn, ARM/DISARM, kiểm lại tư thế; phát lại mở lần chạy ở `run_start` đã ghi), thống kê io,
trạng thái bo sau DISARM cuối, và bản thân xe, bo, cảm biến, định vị. Điều khẳng định được: "cùng đầu vào + mã này →
cùng quyết định"; KHÔNG cho thấy xe sẽ lặp lại lần chạy.

Giới hạn đã biết: khung bị lấy khỏi hàng đợi của VehicleIO ngoài lớp nối (hiện chỉ test làm, `io.advance()` lúc treo)
không có trên băng, nên lần chạy đó phát lại KHÁC (đúng như thiết kế). Với đồng hồ tường (bo thật), đồng hồ lúc quan sát
lấy từ lần đọc trước, sớm vài µs: cột đồng hồ so với sai số `clock_abs_s`; số giây in trong lời (tuổi telemetry của
STALE_TELEMETRY, in tới ms) cũng vậy (sau review 02/10/2026). Log ghi trước T9 (không có log_format 2) bị từ chối; tệp
CSV của băng không đọc được (không phải UTF-8...) cũng vậy, tệp có BOM (Excel "CSV UTF-8") thì đọc được.
"""
from __future__ import annotations

import bisect
import csv
import json
import math
import re
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from autopark.application.vehicle_link import (CLOCK_FIELDS, LOG_FORMAT, POSE_FIELDS, SEND_FAILED_NOTE, SESSION_STOP,
                                               DriveMode, LinkParams, MirroredWorld, PoseSample, VehicleLink,
                                               VehicleLinkError)
from autopark.domain.sensors import SafetyEvent, SourceStamp
from autopark.domain.types import Pose, Scenario, VehicleConfig, VehicleState
from autopark.transport.protocol import N_TOF, Fault, State, StopReason, TelemetryFlag
from autopark.transport.vehicle_io import LinkStats, VehicleIOError, VehicleTelemetry

if TYPE_CHECKING:
    from autopark.application.session import Session


class VehicleTapeError(ValueError):
    """Băng phát lại không dùng được: thư mục log VehicleLink thiếu tệp, khóa hay cột, log ghi trước khi có băng
    (log_format < 2), dòng không đọc được. Lúc phát lại: đồng hồ io bị kéo lùi (bản phát lại đã lệch bản ghi)."""


@dataclass(frozen=True)
class ReplayTolerance:
    """Sai số cho phép khi so bản ghi với bản phát lại. Cả hai số là ĐỀ XUẤT, chưa đo trên bo thật (02/10/2026).

    value_abs: mọi số thực khác (máy khác có thể lệch bit cuối của libm hay shapely; quyết định rời rạc bị lật vẫn hiện
    là chỗ khác, không bị giấu). clock_abs_s: cột đồng hồ io (t_io của commands.csv và events.csv, telemetry_age_s) và
    số giây in trong lời (message, reason) = một bước 5 ms: với đồng hồ tường, đồng hồ lúc ghi dòng lệnh muộn hơn đồng
    hồ trên băng vài µs."""

    value_abs: float = 1e-9
    clock_abs_s: float = 0.005


# Tệp phải có trong thư mục log VehicleLink để phát lại (start_refusals.csv, board_actions.csv thì không: chúng ở ngoài
# lần chạy).
TAPE_FILES = ("link.json", "commands.csv", "telemetry.csv", "events.csv", "poses.csv", "clock.csv")
# Cột mà việc dựng lại băng cần, theo tệp.
_REQUIRED_COLUMNS = {
    "commands.csv": ("t_session", "t_io", "mode", "sent", "seq", "note"),
    "telemetry.csv": ("t_io", "device_time_ms", "sequence", "state", "fault", "stop_reason", "flags", "speed_mps",
                      "steer_rad", "speed_ref_mps", "steer_ref_rad", "effort", "last_cmd_seq", "cmd_age_s", "supply_v",
                      "rx_errors", "rejects", "call"),
    "events.csv": ("t_session", "t_io", "source", "code", "action", "handling", "message", "call"),
    "poses.csv": ("use", "t_session", "t_io", "available", "sample_t_io", "x", "y", "yaw_rad", "source_id",
                  "simulated"),
    "clock.csv": ("call", "kind", "t_session", "t_io"),
}
# Mã sự kiện không so: DISARM_FAILED, END_RUN_SEND_FAILED chỉ có khi bo không trả lời (phát lại không gửi gì tới bo);
# SYNC_MARK là dấu đồng bộ video–log do người dùng bấm (T14), không phải quyết định của phần mềm.
REPLAY_IGNORED_CODES = frozenset({"DISARM_FAILED", "END_RUN_SEND_FAILED", "SYNC_MARK"})
# Cột không so ở mọi tệp: t_perf = perf_counter() của laptop lúc ghi dòng (T13).
REPLAY_IGNORED_COLUMNS = frozenset({"t_perf"})
# Dòng không so cột t_io: quyết định dừng của phiên (T13) ghi io.now() lúc quyết định; yêu cầu dừng từ giao diện tới
# giữa hai lần đọc io, nên đồng hồ đó không có trên băng.
REPLAY_CLOCK_FREE_HANDLINGS = frozenset({SESSION_STOP})
# Phần không so (in nguyên văn trong báo cáo).
NOT_COMPARED = (
    "bước kiểm START (kết nối, HELLO, so giới hạn, ARM/DISARM, kiểm lại tư thế): phát lại mở lần chạy ở run_start "
    "đã ghi",
    "dòng before_start của events.csv, start_refusals.csv và board_actions.csv (ngoài lần chạy)",
    "thống kê io (stats của link.json, commands_sent và telemetry_received của kết quả)",
    "trạng thái bo sau lệnh DISARM cuối (board_state của kết quả)",
    "cột t_perf, cột t_io của dòng session_stop, dòng DISARM_FAILED, END_RUN_SEND_FAILED và SYNC_MARK",
    "bản thân xe, bo, cảm biến và định vị",
)
MAX_REPORTED_MISMATCHES = 20
# `ReplayVehicleIO.telemetry_fresh()` khi không được truyền max_age_s (VehicleLink luôn truyền): như mặc định
# telemetry_timeout_s của VehicleIO.
DEFAULT_TELEMETRY_TIMEOUT_S = 0.3


# ---------------------------------------------------------------------------------------------------------- đọc băng
def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Tiêu đề và các dòng của một tệp CSV của băng. "utf-8-sig": tệp lưu lại bằng Excel ("CSV UTF-8") có BOM, không có
    nó thì cột đầu thành "\\ufefft_session" và băng bị từ chối nhầm vì "thiếu cột" (sửa sau review 02/10/2026)."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def _opt_float(text: str) -> float | None:
    return None if text == "" else float(text)


def telemetry_from_row(row: dict[str, str], source_id: str) -> VehicleTelemetry:
    """Dựng lại khung telemetry từ một dòng telemetry.csv. Dấu thời gian là t_io (lúc laptop nhận); trạng thái, lỗi
    và lý do dừng tra theo tên; ô trống là None. IMU và ToF không có trong log (vòng điều khiển không dùng): None."""
    return VehicleTelemetry(
        stamp=SourceStamp(source_id, float(row["t_io"]), True, "vehicle"),
        device_time_ms=int(row["device_time_ms"]), sequence=int(row["sequence"]), state=State[row["state"]],
        fault=Fault[row["fault"]], stop_reason=StopReason[row["stop_reason"]], flags=TelemetryFlag(int(row["flags"])),
        speed_mps=_opt_float(row["speed_mps"]), steer_rad=_opt_float(row["steer_rad"]),
        speed_ref_mps=float(row["speed_ref_mps"]), steer_ref_rad=float(row["steer_ref_rad"]),
        effort=float(row["effort"]), last_cmd_seq=int(row["last_cmd_seq"]), cmd_age_s=_opt_float(row["cmd_age_s"]),
        imu=None, tof_m=(None,) * N_TOF, supply_v=_opt_float(row["supply_v"]), rx_errors=int(row["rx_errors"]),
        rejects=int(row["rejects"]))


@dataclass
class VehicleRunTape:
    """Băng phát lại của một lần chạy, đọc từ thư mục log VehicleLink (`read_vehicle_tape`)."""

    directory: Path
    info: dict                                          # link.json
    mode: DriveMode
    params: LinkParams
    io_source_id: str
    run_start: dict                                     # t_io0, x, y, yaw_rad, steer_rad, state_source
    frames: list[tuple[int, VehicleTelemetry]]          # (số lần đọc, khung), đúng thứ tự ghi
    io_events: list[tuple[int, SafetyEvent]]            # (số lần đọc, sự kiện VehicleIO)
    calls: list[float]                                  # io.now() sau mỗi lần đọc (clock.csv)
    poses: list[tuple[float, PoseSample | None]]        # (io.now() liền sau mẫu, mẫu hoặc None)
    sends: list[tuple[float, int | str]]                # (io.now() liền sau send/stop, seq hoặc lời lỗi)
    rows: dict[str, list[dict[str, str]]]               # dòng thô của từng tệp CSV, để so


def _parse_rows(name: str, rows: list[dict[str, str]], parse: Callable[[int, dict[str, str]], object]) -> list:
    """`parse(i, dòng)` cho từng dòng (i đếm từ 0); bỏ kết quả None. Dòng hỏng → `VehicleTapeError` nêu tệp và số dòng
    dữ liệu (đếm từ 1 sau dòng tiêu đề)."""
    out = []
    for i, row in enumerate(rows):
        try:
            value = parse(i, row)
        except (KeyError, TypeError, ValueError) as exc:
            raise VehicleTapeError(f"{name} dòng {i + 1}: {type(exc).__name__}: {exc}") from exc
        if value is not None:
            out.append(value)
    return out


def _pose_from_row(_i: int, row: dict[str, str]) -> tuple[float, PoseSample | None]:
    t_io = float(row["t_io"])
    if row["available"] == "0":
        return t_io, None
    if row["available"] != "1":
        raise ValueError(f"available phải là 0 hoặc 1, có {row['available']!r}")
    pose = Pose(float(row["x"]), float(row["y"]), float(row["yaw_rad"]))
    return t_io, PoseSample(pose, float(row["sample_t_io"]), row["source_id"], row["simulated"] == "1")


def _io_event_from_row(_i: int, row: dict[str, str]) -> tuple[int, SafetyEvent] | None:
    """Chỉ dòng có số lần đọc (sự kiện VehicleIO mà một lần đọc io trả); dòng của lớp nối và của phiên: None."""
    if row["call"] == "":
        return None
    stamp = SourceStamp(row["source"], max(0.0, float(row["t_io"])))
    return int(row["call"]), SafetyEvent(stamp, row["code"], row["message"], row["action"])


def _call_time(i: int, row: dict[str, str]) -> float:
    if int(row["call"]) != i:
        raise ValueError(f"số lần đọc {row['call']}, cần {i}")
    return float(row["t_io"])


def _send_outcome(_i: int, row: dict[str, str]) -> tuple[float, int | str] | None:
    if row["sent"] == "1":
        return float(row["t_io"]), int(row["seq"])
    if row["note"].startswith(SEND_FAILED_NOTE):
        return float(row["t_io"]), row["note"][len(SEND_FAILED_NOTE):]
    return None                           # không gửi gì: đã dừng nên không gửi enable


def read_vehicle_tape(directory: str | Path) -> VehicleRunTape:
    """Đọc băng phát lại từ thư mục log của `VehicleLink.write_logs`. Thiếu tệp, link.json không có log_format ≥ 2 hay
    run_start, chế độ không phải VEHICLE_IO/OBSERVE, thiếu cột (cột call), tệp CSV không đọc được (không phải UTF-8...),
    dòng không đọc được → `VehicleTapeError` nói rõ chỗ hỏng (tệp, số dòng dữ liệu tính từ 1 sau dòng tiêu đề)."""
    path = Path(directory)
    missing = [name for name in TAPE_FILES if not (path / name).is_file()]
    if missing:
        raise VehicleTapeError(f"thiếu tệp {', '.join(missing)}")
    try:
        info = json.loads((path / "link.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise VehicleTapeError(f"link.json không đọc được: {exc}") from exc
    if not isinstance(info, dict):
        raise VehicleTapeError("link.json không phải một đối tượng JSON")
    log_format = info.get("log_format")
    if not isinstance(log_format, int) or isinstance(log_format, bool) or log_format < LOG_FORMAT:
        raise VehicleTapeError(f"link.json không có log_format ≥ {LOG_FORMAT} (có {log_format!r})")
    start = info.get("run_start")
    if not isinstance(start, dict):
        raise VehicleTapeError("link.json không có run_start (liên kết chưa mở lần chạy nào)")
    try:
        run_start = {key: float(start[key]) for key in ("t_io0", "x", "y", "yaw_rad", "steer_rad")}
        run_start["state_source"] = str(start["state_source"])
    except (KeyError, TypeError, ValueError) as exc:
        raise VehicleTapeError(f"run_start của link.json hỏng: {type(exc).__name__}: {exc}") from exc
    try:
        mode = DriveMode(info.get("mode"))
    except ValueError as exc:
        raise VehicleTapeError(f"chế độ {info.get('mode')!r} của link.json không hợp lệ") from exc
    if mode not in (DriveMode.VEHICLE_IO, DriveMode.OBSERVE):
        raise VehicleTapeError(f"chế độ {mode.value} không đi qua VehicleIO")
    try:
        params = LinkParams(**info["params"])
    except (KeyError, TypeError, ValueError) as exc:
        raise VehicleTapeError(f"params của link.json hỏng: {type(exc).__name__}: {exc}") from exc
    io_source_id = info.get("io_source_id")
    if not isinstance(io_source_id, str) or not io_source_id:
        raise VehicleTapeError("link.json không có io_source_id")
    if info.get("result") is not None and not isinstance(info["result"], dict):
        raise VehicleTapeError("result của link.json không phải một đối tượng JSON")
    rows: dict[str, list[dict[str, str]]] = {}
    for name, required in _REQUIRED_COLUMNS.items():
        try:
            header, data = _read_csv(path / name)
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            # Tệp không phải UTF-8 (mở rồi lưu bằng Excel theo bảng mã ANSI), ô quá dài, không đọc được: băng hỏng,
            # không phải lần phát lại KHÁC bản ghi (sửa sau review 02/10/2026: trước đó lỗi thoát ra ngoài
            # ReplayNotSupported).
            raise VehicleTapeError(f"{name} không đọc được: {type(exc).__name__}: {exc}") from exc
        absent = [column for column in required if column not in header]
        if absent:
            raise VehicleTapeError(f"{name} thiếu cột {', '.join(absent)}")
        rows[name] = data
    frames = _parse_rows("telemetry.csv", rows["telemetry.csv"],
                         lambda _i, row: (int(row["call"]), telemetry_from_row(row, io_source_id)))
    io_events = _parse_rows("events.csv", rows["events.csv"], _io_event_from_row)
    calls = _parse_rows("clock.csv", rows["clock.csv"], _call_time)
    poses = _parse_rows("poses.csv", rows["poses.csv"], _pose_from_row)
    # Quan sát không gửi COMMAND nào: không có lệnh để trả.
    sends = (_parse_rows("commands.csv", rows["commands.csv"], _send_outcome) if mode == DriveMode.VEHICLE_IO
             else [])
    return VehicleRunTape(path, info, mode, params, io_source_id, run_start, frames, io_events, calls, poses, sends,
                          rows)


# ------------------------------------------------------------------------------------------------- io và tư thế băng
class ReplayVehicleIO:
    """VehicleIO "băng" (duck typing, KHÔNG phải SimVehicleIO, nên lớp nối đi nhánh `poll(block=False)`): mỗi lần
    `poll()` là lần đọc thứ k của băng — đặt đồng hồ bằng io.now() đã ghi sau lần đọc đó và trả đúng các khung của nó;
    `events()` trả các sự kiện của lần đọc vừa rồi. `latest()` là khung mới nhất trong MỌI khung đã ghi có t_io ≤ đồng
    hồ (khung nhận trong lúc chờ DISARM bên trong một lần đọc được giao ở lần đọc sau nhưng đã là `latest()` của bo).
    `send()`/`stop()` trả số thứ tự hoặc ném lỗi đã ghi, và đồng hồ không lùi về trước lúc ghi dòng lệnh. Không gửi
    gì đi đâu cả; `disarm()`, `close()` không làm gì."""

    port = None

    def __init__(self, tape: VehicleRunTape):
        self.source_id = tape.io_source_id
        self.connected = True
        self.stats = LinkStats()
        self.clock = tape.run_start["t_io0"]
        frames = [tel for _, tel in tape.frames]
        order = sorted(range(len(frames)), key=lambda i: frames[i].stamp.t)    # sắp xếp ổn định theo t_io
        self._sorted = [frames[i] for i in order]
        self._times = [tel.stamp.t for tel in self._sorted]
        self._by_call: dict[int, list[VehicleTelemetry]] = {}
        for call, tel in tape.frames:
            self._by_call.setdefault(call, []).append(tel)
        self._events_by_call: dict[int, list[SafetyEvent]] = {}
        for call, event in tape.io_events:
            self._events_by_call.setdefault(call, []).append(event)
        self._calls = list(tape.calls)
        self._next_call = 0
        self._current: int | None = None
        self._sends = deque(tape.sends)
        self.extra_reads = 0              # lần đọc vượt quá băng (bản so báo chỗ khác)
        self.send_calls = 0               # số lần send()/stop() trong lúc phát lại, kể cả lệnh dừng của end_run/close
        self.extra_sends = 0              # send()/stop() khi băng đã hết lệnh: lệnh dừng của end_run/close, hoặc lệch

    def now(self) -> float:
        return self.clock

    def set_clock(self, t: float) -> None:
        if t < self.clock:
            raise VehicleTapeError(f"đồng hồ io phát lại bị kéo lùi ({t!r} < {self.clock!r}): bản phát lại đã lệch "
                                   f"thứ tự đọc của bản ghi")
        self.clock = t

    def poll(self, block: bool = True) -> list[VehicleTelemetry]:
        k = self._next_call
        self._next_call += 1
        if k >= len(self._calls):
            self.extra_reads += 1
            self._current = None
            return []
        self._current = k
        self.set_clock(self._calls[k])
        return list(self._by_call.get(k, ()))

    def events(self) -> list[SafetyEvent]:
        if self._current is None:
            return []
        return self._events_by_call.pop(self._current, [])

    def latest(self) -> VehicleTelemetry | None:
        i = bisect.bisect_right(self._times, self.clock)
        return self._sorted[i - 1] if i else None

    def telemetry_fresh(self, now: float | None = None, max_age_s: float | None = None) -> bool:
        now = self.clock if now is None else now
        limit = DEFAULT_TELEMETRY_TIMEOUT_S if max_age_s is None else max_age_s
        tel = self.latest()
        return tel is not None and 0 <= now - tel.stamp.t <= limit

    def send(self, speed_mps: float, steer_rad: float, *, enable: bool = True, validity_s: float | None = None) -> int:
        self.send_calls += 1
        if not self._sends:
            self.extra_sends += 1
            return 0x10000 + self.extra_sends         # ngoài dải 16 bit: không trùng số thứ tự thật nào
        t_io, outcome = self._sends.popleft()
        self.set_clock(max(self.clock, t_io))
        if isinstance(outcome, str):
            raise VehicleIOError(outcome)
        return outcome

    def stop(self, validity_s: float | None = None) -> int:
        return self.send(0.0, 0.0, enable=False, validity_s=validity_s)

    def disarm(self, timeout_s: float | None = None) -> None:
        pass

    def close(self) -> None:
        pass


class ReplayPoseSource:
    """Nguồn tư thế "băng": mỗi `latest()` lấy mẫu kế tiếp của poses.csv (có thể là None, như lúc ghi) và đặt đồng hồ
    io bằng io.now() đã ghi liền sau mẫu đó. Hết băng: None."""

    def __init__(self, io: ReplayVehicleIO, tape: VehicleRunTape):
        self.io = io
        self.source_id = tape.info.get("pose_source")
        self.simulated = bool(tape.info.get("pose_simulated"))
        self._samples = deque(tape.poses)
        self.extra_reads = 0

    def latest(self) -> PoseSample | None:
        if not self._samples:
            self.extra_reads += 1
            return None
        t_io, sample = self._samples.popleft()
        self.io.set_clock(t_io)
        return sample


class ReplayVehicleLink(VehicleLink):
    """`VehicleLink` chạy trên băng: CÙNG mã quyết định của lớp nối (observe, command, _guard, _collect_events...),
    với `ReplayVehicleIO` và `ReplayPoseSource`. Không theo thời gian thực (`realtime` = False: `Session.advance` bước
    theo PHYSICS_DT, đồng hồ io lấy từ băng). `begin_run` không kết nối, không ARM: mở lần chạy ở `run_start` đã ghi."""

    def __init__(self, tape: VehicleRunTape):
        io = ReplayVehicleIO(tape)
        super().__init__(tape.mode, io, pose_source=ReplayPoseSource(io, tape), params=tape.params)
        self.tape = tape

    @property
    def realtime(self) -> bool:
        return False

    @property
    def clear_fault_blocker(self) -> str | None:
        return "liên kết phát lại log không có bo"

    def describe(self) -> dict:
        """Các khóa của `VehicleLink.describe()` lấy theo link.json đã ghi, thêm {"replay": True}."""
        info = self.tape.info
        out = {key: info.get(key) for key in VehicleLink.describe(self)}
        out["replay"] = True
        return out

    def begin_run(self, scenario: Scenario, cfg: VehicleConfig, dt: float) -> MirroredWorld:
        if self._closed:
            raise VehicleLinkError("Liên kết VehicleIO đã đóng")
        start = self.tape.run_start
        self.io.set_clock(start["t_io0"])
        initial = VehicleState(Pose(start["x"], start["y"], start["yaw_rad"]), 0.0, start["steer_rad"], 0.0,
                               source_id=start["state_source"])
        world = MirroredWorld(scenario, cfg, dt, self, initial)
        self._commit_run([], world)
        return world


# ------------------------------------------------------------------------------------------------------------- so khớp
@dataclass(frozen=True)
class ReplayMismatch:
    """Một chỗ bản phát lại khác bản ghi. row: số dòng dữ liệu của tệp ghi (1 = dòng đầu sau tiêu đề) hoặc số phần tử
    (tệp JSON), None khi không theo dòng. t_session: thời gian phiên của dòng, None khi không có (xếp cuối)."""

    file: str
    row: int | None
    column: str
    recorded: str
    replayed: str
    t_session: float | None

    def describe(self) -> str:
        where = self.file + (f" dòng {self.row}" if self.row is not None else "")
        when = f" (t_session {self.t_session:.4f} s)" if self.t_session is not None else ""
        column = f", cột {self.column}" if self.column else ""
        return f"{where}{when}{column}: ghi {self.recorded!r}, phát lại {self.replayed!r}"


def _cell(value) -> str:
    """Ô của dòng phát lại như csv.DictWriter sẽ ghi: None → "", còn lại str()."""
    return "" if value is None else str(value)


def _as_float(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


# Số giây in trong lời ("0.152 s"): tuổi telemetry của STALE_TELEMETRY ("Telemetry cũ (0.152 s, ngưỡng 0.15 s)") tính
# từ một lần đọc io.now() không có trên băng (phát lại dùng đồng hồ của lần đọc io trước, sớm vài µs với đồng hồ tường),
# nên chữ số ms cuối có thể khác. Lời đó đi vào safety_events.json, lý do dừng (result.json, kết quả của link.json) và
# message của dòng session_stop (events.csv).
_SECONDS_IN_TEXT = re.compile(r"(-?\d+\.\d+) s\b")


def _same_text(recorded: str, replayed: str, tol: ReplayTolerance) -> bool:
    """Hai lời giống nhau, coi số giây in trong lời như cột đồng hồ: phần chữ phải bằng hẳn, từng cặp số giây lệch
    ≤ clock_abs_s (sửa sau review 02/10/2026: trước đó so bằng hẳn, nên bo thật với đồng hồ tường cho KHÁC giả khoảng
    một lần trên trăm lần dừng vì STALE_TELEMETRY)."""
    if recorded == replayed:
        return True
    a, b = _SECONDS_IN_TEXT.split(recorded), _SECONDS_IN_TEXT.split(replayed)
    # split với một nhóm bắt: phần chữ ở chỉ số chẵn, số giây ở chỉ số lẻ
    if len(a) != len(b) or a[0::2] != b[0::2]:
        return False
    return all(abs(float(x) - float(y)) <= tol.clock_abs_s for x, y in zip(a[1::2], b[1::2]))


def _row_time(row: dict) -> float | None:
    for key in ("t_session", "t"):
        if key in row:
            return _as_float(_cell(row[key]))
    return None


def compare_rows(name: str, recorded: list[dict[str, str]], replayed: list[dict], tol: ReplayTolerance, *,
                 clock_columns: frozenset[str] = frozenset(), skip: Callable[[dict], bool] | None = None,
                 skip_columns: frozenset[str] = frozenset()) -> tuple[int, list[ReplayMismatch], float]:
    """So dòng của một tệp CSV đã ghi với dòng phát lại (trong bộ nhớ), theo cột của tệp ghi. Ô phát lại là "" với None,
    str(v) với giá trị khác; hai chuỗi bằng nhau là khớp; hai số thì lệch ≤ clock_abs_s (cột đồng hồ) hay ≤ value_abs
    (cột khác); hai lời chỉ khác số giây in trong lời thì như cột đồng hồ (`_same_text`). Số dòng khác nhau: một chỗ
    khác ở dòng thừa đầu tiên. `skip`: bỏ dòng (cả hai phía). Trả (số cặp dòng đã so, các chỗ khác, lệch lớn nhất ở cột
    đồng hồ)."""
    rec = [(number, row) for number, row in enumerate(recorded, 1) if skip is None or not skip(row)]
    rep = [row for row in replayed if skip is None or not skip(row)]
    mismatches: list[ReplayMismatch] = []
    max_clock = 0.0
    for (number, want_row), got_row in zip(rec, rep):
        when = _row_time(want_row)
        for column, text in want_row.items():
            if column is None or column in skip_columns:          # None: ô thừa cuối dòng (csv.DictReader)
                continue
            want = "" if text is None else text
            got = _cell(got_row.get(column))
            if want == got:
                continue
            a, b = _as_float(want), _as_float(got)
            if a is not None and b is not None:
                diff = abs(a - b)
                if column in clock_columns:
                    if math.isfinite(diff):
                        max_clock = max(max_clock, diff)
                    if diff <= tol.clock_abs_s:
                        continue
                elif diff <= tol.value_abs:
                    continue
            elif _same_text(want, got, tol):
                continue
            mismatches.append(ReplayMismatch(name, number, column, want, got, when))
    if len(rec) != len(rep):
        k = min(len(rec), len(rep))
        if len(rec) > k:
            number, extra = rec[k]
        else:
            number, extra = (rec[-1][0] + 1 if rec else 1), rep[k]
        mismatches.append(ReplayMismatch(name, number, "(số dòng)", f"{len(rec)} dòng", f"{len(rep)} dòng",
                                         _row_time(extra)))
    return min(len(rec), len(rep)), mismatches, max_clock


_MISSING = object()


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _json_text(value) -> str:
    if value is _MISSING:
        return "(không có)"
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def compare_values(file: str, recorded, replayed, tol: ReplayTolerance, *, column: str = "", row: int | None = None,
                   t_session: float | None = None) -> list[ReplayMismatch]:
    """So đệ quy hai giá trị kiểu JSON (dict, list, số, chuỗi, bool, None): số thực lệch ≤ value_abs là khớp; bool,
    None phải bằng hẳn (cùng kiểu); chuỗi bằng hẳn, trừ số giây in trong lời: so như cột đồng hồ (`_same_text`)."""
    if isinstance(recorded, dict) and isinstance(replayed, dict):
        out = []
        for key in [*recorded, *(k for k in replayed if k not in recorded)]:
            out += compare_values(file, recorded.get(key, _MISSING), replayed.get(key, _MISSING), tol,
                                  column=f"{column}.{key}" if column else str(key), row=row, t_session=t_session)
        return out
    if isinstance(recorded, list) and isinstance(replayed, list):
        out = []
        for i, (a, b) in enumerate(zip(recorded, replayed)):
            out += compare_values(file, a, b, tol, column=f"{column}[{i}]", row=row, t_session=t_session)
        if len(recorded) != len(replayed):
            out.append(ReplayMismatch(file, row, f"{column} (số phần tử)", str(len(recorded)), str(len(replayed)),
                                      t_session))
        return out
    if _is_number(recorded) and _is_number(replayed):
        if abs(recorded - replayed) <= tol.value_abs:
            return []
    elif recorded is not _MISSING and type(recorded) is type(replayed) and recorded == replayed:
        return []
    elif isinstance(recorded, str) and isinstance(replayed, str) and _same_text(recorded, replayed, tol):
        return []
    return [ReplayMismatch(file, row, column, _json_text(recorded), _json_text(replayed), t_session)]


def _plain(value):
    """Giá trị Python → đúng dạng sau khi ghi JSON rồi đọc lại (tuple thành list...), để so với tệp JSON đã ghi."""
    return json.loads(json.dumps(value, ensure_ascii=False))


def _skip_event(row: dict) -> bool:
    return row.get("handling") == "before_start" or row.get("code") in REPLAY_IGNORED_CODES


def _clock_free(rows: list[dict]) -> list[dict]:
    return [dict(row, t_io="") if row.get("handling") in REPLAY_CLOCK_FREE_HANDLINGS else row for row in rows]


def compare_link_logs(tape: VehicleRunTape, link: VehicleLink,
                      tol: ReplayTolerance) -> tuple[dict[str, int], list[ReplayMismatch], float]:
    """So log của liên kết phát lại với băng: commands.csv (cột đồng hồ t_io, telemetry_age_s), telemetry.csv,
    events.csv (bỏ dòng before_start và mã trong REPLAY_IGNORED_CODES; t_io là cột đồng hồ, trừ dòng session_stop),
    poses.csv và clock.csv (thẳng hàng: use/kind và t_session). Cột t_perf không so."""
    checks = (
        ("commands.csv", link.command_rows, {"clock_columns": frozenset({"t_io", "telemetry_age_s"})}),
        ("telemetry.csv", link.telemetry_rows, {}),
        ("events.csv", _clock_free(link.event_rows), {"skip": _skip_event, "clock_columns": frozenset({"t_io"})}),
        ("poses.csv", link.pose_rows, {"skip_columns": frozenset(POSE_FIELDS) - {"use", "t_session"}}),
        ("clock.csv", link.clock_rows, {"skip_columns": frozenset(CLOCK_FIELDS) - {"kind", "t_session"}}),
    )
    compared: dict[str, int] = {}
    mismatches: list[ReplayMismatch] = []
    max_clock = 0.0
    for name, replayed, options in checks:
        recorded = tape.rows[name]
        if name == "events.csv":
            recorded = _clock_free(recorded)
        options = dict(options, skip_columns=options.get("skip_columns", frozenset()) | REPLAY_IGNORED_COLUMNS)
        n, found, clock = compare_rows(name, recorded, replayed, tol, **options)
        compared[name] = n
        mismatches += found
        max_clock = max(max_clock, clock)
    return compared, mismatches, max_clock


@dataclass
class VehicleReplayReport:
    """Kết quả phát lại log một lần chạy qua VehicleIO. `mismatches` xếp theo t_session (None cuối): chỗ đầu là chỗ lệch
    sớm nhất. `compared`: số dòng (hay phần tử) đã so theo tệp; "RunLog" là telemetry.csv của gói."""

    ok: bool
    mode: str
    evidence: str
    state: str
    steps: int
    compared: dict[str, int]
    mismatches: list[ReplayMismatch]
    max_clock_diff_s: float
    tolerance: ReplayTolerance
    not_compared: list[str] = field(default_factory=lambda: list(NOT_COMPARED))

    def lines(self) -> list[str]:
        """Báo cáo tiếng Việt, mỗi phần tử một dòng (CLI in nguyên văn)."""
        tol = self.tolerance
        verdict = "KHỚP" if self.ok else f"KHÁC ({len(self.mismatches)} chỗ)"
        out = [f"Phát lại log lần chạy qua VehicleIO (chế độ {self.mode}, bằng chứng {self.evidence}): {verdict}",
               f"Kết thúc khi phát lại: {self.state}, {self.steps} bước.",
               "Đã so: " + ", ".join(f"{name} {n}" for name, n in self.compared.items())
               + " (RunLog = telemetry.csv của gói).",
               f"Lệch đồng hồ lớn nhất {self.max_clock_diff_s * 1000:.3f} ms (cho phép {tol.clock_abs_s * 1000:g} ms ở "
               f"cột đồng hồ; số thực khác lệch tối đa {tol.value_abs:g})."]
        if self.mismatches:
            shown = self.mismatches[:MAX_REPORTED_MISMATCHES]
            out.append(f"Chỗ khác, xếp theo t_session (chỗ đầu là chỗ lệch sớm nhất; in {len(shown)}):")
            out += ["  " + m.describe() for m in shown]
            if len(self.mismatches) > len(shown):
                out.append(f"  … và {len(self.mismatches) - len(shown)} chỗ khác nữa.")
        out.append("Không so: " + "; ".join(self.not_compared) + ".")
        out.append("Đây là chạy lại PHẦN MỀM trên đầu vào đã ghi (cùng đầu vào + mã này → cùng quyết định); KHÔNG chạy "
                   "lại xe, bo hay định vị.")
        return out

    def to_dict(self) -> dict:
        return asdict(self)


def compare_vehicle_run(tape: VehicleRunTape, link: VehicleLink, session: Session, *, evidence: str, result: dict,
                        safety_events: list, runlog: list[dict[str, str]], tolerance: ReplayTolerance | None = None,
                        failure: BaseException | None = None) -> VehicleReplayReport:
    """So một lần phát lại với gói đã ghi: log của liên kết (`compare_link_logs`), RunLog (telemetry.csv của gói),
    safety_events.json (số thực theo value_abs), result.json (state, reason, steps, collided bằng hẳn; final_state,
    distance theo value_abs) và kết quả trong link.json (outcome, reason, t_session). `failure`: ngoại lệ trong lúc phát
    lại, thành một chỗ khác."""
    tol = tolerance or ReplayTolerance()
    compared, mismatches, max_clock = compare_link_logs(tape, link, tol)
    world = session.world
    n, found, _ = compare_rows("RunLog", runlog, session.log.rows, tol)
    compared["RunLog"] = n
    mismatches += found
    replayed_events = _plain([asdict(e) for e in session.safety_events])
    for number, (a, b) in enumerate(zip(safety_events, replayed_events), 1):
        mismatches += compare_values("safety_events.json", a, b, tol, row=number, t_session=_event_time(a))
    if len(safety_events) != len(replayed_events):
        k = min(len(safety_events), len(replayed_events))
        extra = safety_events[k] if len(safety_events) > k else replayed_events[k]
        mismatches.append(ReplayMismatch("safety_events.json", k + 1, "(số phần tử)", str(len(safety_events)),
                                         str(len(replayed_events)), _event_time(extra)))
    compared["safety_events.json"] = min(len(safety_events), len(replayed_events))
    actual = {"state": session.state.value, "reason": session.stop_reason,
              "steps": world.step_count if world is not None else None,
              "final_state": _plain(asdict(world.state)) if world is not None else None,
              "collided": world.collided if world is not None else None,
              "distance": world.distance if world is not None else None}
    for key, value in actual.items():
        mismatches += compare_values("result.json", result.get(key, _MISSING), value, tol, column=key)
    compared["result.json"] = 1
    recorded_result, replayed_result = tape.info.get("result"), link.result
    if recorded_result is None or replayed_result is None:
        mismatches += compare_values("link.json", recorded_result, replayed_result, tol, column="result")
    else:
        for key in ("outcome", "reason", "t_session"):
            mismatches += compare_values("link.json", recorded_result.get(key, _MISSING),
                                         replayed_result.get(key, _MISSING), tol, column=f"result.{key}")
    compared["link.json"] = 1
    if failure is not None:
        mismatches.append(ReplayMismatch("(chạy phát lại)", None, "", f"{result.get('steps')} bước như bản ghi",
                                         f"{type(failure).__name__}: {failure}",
                                         world.time if world is not None else None))
    mismatches.sort(key=lambda m: (m.t_session is None, m.t_session or 0.0))
    return VehicleReplayReport(not mismatches, tape.mode.value, evidence, session.state.value,
                               world.step_count if world is not None else 0, compared, mismatches, max_clock, tol)


def _event_time(event) -> float | None:
    try:
        return float(event["stamp"]["t"])
    except (KeyError, TypeError, ValueError):
        return None
