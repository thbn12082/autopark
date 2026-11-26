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

Thêm 02/10/2026 (bo ảo QEMU trong phiên đỗ; người dùng giao quyết định 02/10/2026; chỉ thử với bo ảo GIẢ trong test và
một lần với QEMU thật, CHƯA THỬ với ESP32-S3):

- `VehicleLink.qemu_board(mode, source)`: firmware THẬT trong QEMU qua `QemuPlantVehicleIO` (`transport/qemu_plant.py`).
  Firmware chưa đọc cảm biến, nên tốc độ, góc lái và tư thế (`QemuPlantPose`) lấy từ XE MÔ PHỎNG phía laptop bám tham
  chiếu firmware báo; luật START không nới. Mỗi START: lấy bo đang chạy từ `source` (chưa chạy → START_NO_QEMU_BOARD,
  trước mọi I/O), đặt xe mô phỏng ở điểm xuất phát, mở socket (bước 0c của `_open_run`, chung với cổng COM), HELLO
  (boot_id phải đúng bo ảo đã khởi động), kiểm START, ARM; hết lần chạy thì DISARM rồi đóng socket
  (`_close_after_run`, chỉ bo ảo: QEMU chỉ phục vụ một client; cổng COM giữ mở giữa các lần chạy). Liên kết bo ảo
  có `virtual_board` = True: không tính là phần cứng chấp hành.
- Luật ghép: `QemuPlantPose` chỉ với chính `QemuPlantVehicleIO` của liên kết, và io bo ảo chỉ với `QemuPlantPose`
  (không bao giờ với SimTruthPose, NoPoseSource hay tư thế LiDAR). Bằng chứng `qemu_firmware_simulated_vehicle` (mức MP);
  link.json có thêm khóa "board" và "plant" (None với liên kết khác).

Thêm 02/10/2026 (T2, nguồn tư thế LiDAR, `application/lidar_pose_source.py`; người dùng giao quyết định 02/10/2026,
ngưỡng ĐỀ XUẤT – CHỜ CHỐT; chỉ kiểm với bo mô phỏng + LiDAR mô phỏng và cổng serial GIẢ, mọi đường với bo thật CHƯA
THỬ):

- `PoseSample` có thêm `status` ("OK" hoặc POSE_LOST / POSE_DISAGREE / POSE_UNCHECKED) và `reason`. Mẫu không OK không
  bao giờ dùng cho điều khiển hay thế giới gương: `observe` dừng với mã = status (nguồn = source_id của mẫu), `estimate`
  giữ tư thế trước. poses.csv nối thêm hai cột status, reason (băng cũ không có hai cột vẫn phát lại được).
- `LinkParams.max_pose_age_s` (None = như max_state_age_s): tuổi tư thế tối đa riêng cho nguồn LiDAR (0,25 s, N-T2 phương
  án "chỉ LiDAR 10 Hz"); telemetry vẫn theo max_state_age_s.
- `_open_run`: bước 0a (nguồn không `available` → START_NO_POSE_SOURCE, như cũ); bước 0b: `start_gate` của nguồn — bo
  THẬT (`hardware_actuators`) ở VEHICLE_IO với điều kiện tiên quyết chưa đạt → START_POSE_UNVERIFIED, KHÔNG I/O nào;
  còn lại → dòng POSE_SOURCE_WARNING; bước 0c (mới): cổng serial chưa mở (`SerialVehicleIO.deferred`) thì `reopen()`;
  lỗi → START_NO_LINK. Cổng giữ mở giữa các lần chạy, `close()` mới đóng. Điều kiện START của nguồn (`start_problems`)
  vào START_CHECK.
- Móc nguồn tư thế (`bind_clock`, `warm_up`, `run_started`, `run_ended`, `start_gate`, `start_problems`, `describe`,
  `log_rows`, `write_truth_reference`) gọi qua getattr trên nguồn đã bóc lớp tiêm lỗi; lỗi của móc thành dòng
  POSE_SOURCE_HOOK_FAILED, không bao giờ chặn bước dừng. `write_logs` ghi thêm localization.csv và (nguồn mô phỏng)
  tu_the_that_mo_phong.csv + .json (tham chiếu MP).
- `virtual_board=True`: bo ảo (QEMU) được gắn cờ, không tính là phần cứng chấp hành ở bước 0b. Bo không gắn cờ coi là
  bo thật.

Sửa sau review 02/10/2026 (chỉ kiểm với bo mô phỏng + LiDAR mô phỏng, bo ảo GIẢ và cổng serial GIẢ; bo thật CHƯA THỬ):

- Dự đoán tư thế (`LinkParams.predict_pose`, bật bởi `LinkParams.for_lidar` cho mọi liên kết với nguồn LiDAR của giao
  diện): tư thế của mẫu OK được dời từ dấu thời gian của mẫu tới io.now() bằng tốc độ, góc lái ĐO (mô hình xe đạp động
  học) trước khi vào bộ bám (`observe`) và thế giới gương (`estimate`); poses.csv ghi thêm các cột pred_*. Kiểm tuổi tư
  thế (STALE_POSE, kiểm START) vẫn trên tuổi THÔ. Lý do: ở MP, mẫu LiDAR cũ 0,04–0,13 s làm xe lệch tư thế thật quá khe
  hở của đường (DO-4a va chạm khi mọi vòng định vị đều OK). Mặc định tắt: SimTruthPose, bo ảo QEMU và băng cũ như trước.
- Bước 0a nói đúng trạng thái cổng (chưa mở / liên kết đang giữ mở từ bước 0c của lần START trước), như bước 0b.
- `release_port()`: đóng cổng serial liên kết giữ giữa các lần chạy; "Kiểm kết nối bo" gọi trước khi mở cùng cổng.
- io bo ảo truyền thẳng (`QemuPlantVehicleIO`, ví dụ với lớp bọc tiêm lỗi) cũng là liên kết bo ảo (`is_qemu`): đóng
  socket sau lần chạy, `virtual_board`, bằng chứng `qemu_firmware_simulated_vehicle`, khóa board/plant.
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
from typing import Callable, Protocol

from autopark.control.tracker import TrackerOutput
from autopark.domain.sensors import SafetyEvent, SourceStamp
from autopark.domain.types import Pose, Scenario, VehicleConfig, VehicleState, clamp, wrap_angle
from autopark.geometry.footprint import check_motion, check_pose
from autopark.power_throttling import ecoqos_state
from autopark.simulation.vehicle import integrate_bicycle
from autopark.simulation.world import SimWorld, StepResult
from autopark.transport.protocol import Fault, ResetReason, Result, State, TelemetryFlag
from autopark.transport.qemu_plant import (QEMU_EVIDENCE, QEMU_KIND, PlantConfig, QemuBoardHandle,
                                           QemuPlantVehicleIO)
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


POSE_OK = "OK"


@dataclass(frozen=True)
class PoseSample:
    pose: Pose
    t: float              # đồng hồ của VehicleIO (io.now())
    source_id: str
    simulated: bool       # True: tư thế lấy từ mô phỏng, không phải từ cảm biến/định vị
    # T2 (02/10/2026): "OK" hoặc mã dừng của nguồn (POSE_LOST, POSE_DISAGREE, POSE_UNCHECKED) kèm lý do tiếng Việt.
    status: str = POSE_OK
    reason: str = ""


def _pose_sample_problem(sample) -> str | None:
    """Validate a source boundary before geometry or the controller sees a sample."""
    if sample is None:
        return None
    if not isinstance(sample, PoseSample) or not isinstance(sample.pose, Pose):
        return "Nguồn định vị trả mẫu không đúng kiểu PoseSample/Pose"
    try:
        finite = all(math.isfinite(v) for v in (sample.pose.x, sample.pose.y, sample.pose.yaw, sample.t))
    except (TypeError, ValueError, OverflowError):
        finite = False
    if not finite:
        return "Tư thế hoặc thời gian từ nguồn định vị không phải số hữu hạn"
    if (not isinstance(sample.source_id, str) or not sample.source_id
            or not isinstance(sample.status, str) or not sample.status
            or not isinstance(sample.reason, str) or not isinstance(sample.simulated, bool)):
        return "Thông tin nguồn/trạng thái của mẫu định vị không hợp lệ"
    return None


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


# ---------------------------------------------------------------------- bo ảo QEMU (thêm 02/10/2026)
QEMU_OVERRUN_HINT = (" (bo ảo QEMU: máy bận làm QEMU trễ nhịp > 100 ms; giảm tải máy, bấm 'Xóa lỗi bo (CLEAR_FAULT)' "
                     "rồi thử lại)")


class QemuPlantPose:
    """MÔ PHỎNG: tư thế của xe mô phỏng phía laptop trong `QemuPlantVehicleIO` (bo ảo QEMU, thêm 02/10/2026).

    Mẫu mang t của khung telemetry cuối (xe mô phỏng chỉ tiến khi có khung, không ngoại suy), nên tuổi tư thế bằng tuổi
    telemetry. Như `SimTruthPose`: định vị lý tưởng, KHÔNG nói gì về định vị thật; chỉ ghép với chính io đó (luật ghép
    trong `VehicleLink.__init__`). Đây là nguồn "trạng thái đo" của bo ảo: io cho tốc độ, góc lái; nguồn này cho tư thế."""

    source_id = "qemu_plant_pose"
    simulated = True

    def __init__(self, io: QemuPlantVehicleIO):
        self.io = io

    def latest(self) -> PoseSample | None:
        sample = self.io.plant_sample()
        if sample is None:
            return None
        pose, t = sample
        return PoseSample(pose, t, self.source_id, True)


class PlantHumanDriver:
    """MÔ PHỎNG người lái ở chế độ quan sát qua bo ảo QEMU (thêm 02/10/2026): cùng giao diện với `SimHumanDriver`
    (`speed`, `steer`, `set()`), lái xe mô phỏng phía laptop của `QemuPlantVehicleIO` thay cho tham chiếu firmware.
    Firmware giữ DISARMED và không nhận COMMAND nào."""

    def __init__(self, io: QemuPlantVehicleIO, cfg: VehicleConfig):
        self.io = io
        self.cfg = cfg
        self.speed = 0.0
        self.steer = 0.0
        io.set_human_targets(0.0, 0.0)

    def set(self, speed: float, steer: float) -> None:
        if not all(math.isfinite(v) for v in (speed, steer)):
            raise ValueError("Lệnh người lái phải hữu hạn")
        self.speed = clamp(speed, -self.cfg.max_speed, self.cfg.max_speed)
        self.steer = clamp(steer, -self.cfg.max_steer, self.cfg.max_steer)
        self.io.set_human_targets(self.speed, self.steer)


class QemuBoardSource(Protocol):
    """Nơi liên kết bo ảo lấy bo đang chạy lúc START và lúc "Xóa lỗi bo": `ui/qemu_runner.QemuBoardRunner`, bo giả."""

    def current_board(self) -> tuple[QemuBoardHandle | None, str]:
        """(bo đang chạy, "") hoặc (None, lý do bằng tiếng Việt)."""


@dataclass(frozen=True)
class QemuLinkSpec:
    """Liên kết bo ảo QEMU: nguồn bo và tham số xe mô phỏng phía laptop (configs/bo_ao_qemu.json)."""

    source: QemuBoardSource
    plant: PlantConfig


def _perf_clock() -> Callable[[], float]:
    """perf_counter() − t0 (như đồng hồ mặc định của `SerialVehicleIO`)."""
    t0 = time.perf_counter()
    return lambda: time.perf_counter() - t0


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
    # T2 (02/10/2026): tuổi tư thế tối đa riêng cho nguồn tư thế; None = max_state_age_s. Nguồn LiDAR dùng 0,25 s (N-T2
    # phương án "chỉ LiDAR 10 Hz", ĐỀ XUẤT; người dùng giao quyết định 02/10/2026). Telemetry vẫn theo max_state_age_s.
    max_pose_age_s: float | None = None
    # Sửa sau review 02/10/2026 (T2): dời tư thế của mẫu OK từ dấu thời gian của mẫu tới io.now() bằng tốc độ và góc lái
    # ĐO (mô hình xe đạp động học) trước khi giao cho bộ bám và thế giới gương (`VehicleLink._predicted_pose`). Mặc định
    # tắt: bo mô phỏng với SimTruthPose (tuổi 0), bo ảo QEMU (tư thế xe mô phỏng mang t của khung telemetry cuối) và
    # băng phát lại ghi trước khi có khóa này chạy như trước. Liên kết với nguồn LiDAR bật (`for_lidar`). Kiểm tuổi tư
    # thế vẫn trên tuổi THÔ của mẫu.
    predict_pose: bool = False

    def __post_init__(self):
        for name in ("max_state_age_s", "standstill_mps", "start_position_tolerance_m", "start_yaw_tolerance_rad",
                     "start_speed_tolerance_mps", "stop_confirm_timeout_s", "connect_timeout_s", "ready_timeout_s",
                     "fresh_timeout_s", "disarm_timeout_s"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} phải hữu hạn và > 0")
        if not isinstance(self.start_samples, int) or isinstance(self.start_samples, bool) or self.start_samples < 1:
            raise ValueError("start_samples phải là số nguyên >= 1")
        if self.max_pose_age_s is not None and (not math.isfinite(self.max_pose_age_s) or self.max_pose_age_s <= 0):
            raise ValueError("max_pose_age_s phải hữu hạn và > 0 (hoặc None)")
        if not isinstance(self.predict_pose, bool):
            raise ValueError("predict_pose phải là True hoặc False")

    @property
    def pose_age_limit_s(self) -> float:
        """Tuổi tư thế tối đa: `max_pose_age_s`, không đặt thì `max_state_age_s`."""
        return self.max_state_age_s if self.max_pose_age_s is None else self.max_pose_age_s

    @classmethod
    def for_lidar(cls, max_pose_age_s: float, **kwargs) -> "LinkParams":
        """Ngưỡng của liên kết với nguồn tư thế LiDAR (T2): tuổi tư thế tối đa riêng (`max_pose_age_s`, N-T2 phương án
        "chỉ LiDAR 10 Hz", ĐỀ XUẤT) và dự đoán tư thế tới io.now() (`predict_pose`, sửa sau review 02/10/2026). Giao
        diện dựng liên kết "LiDAR mô phỏng" và "LiDAR thật" bằng hàm này."""
        return cls(max_pose_age_s=max_pose_age_s, predict_pose=True, **kwargs)


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
# status, reason (nối cuối 02/10/2026, T2): trạng thái của mẫu (OK hoặc mã dừng của nguồn tư thế LiDAR) và lý do.
# pred_* (nối cuối sau review 02/10/2026, T2): dự đoán tư thế tới io.now() (`LinkParams.predict_pose`): khoảng đã dời
# (= tuổi THÔ của mẫu, s), tốc độ và góc lái ĐO đã dùng, tư thế giao cho bộ bám (use = observe) hay thế giới gương
# (use = estimate). Trống khi không dời. x, y, yaw_rad vẫn là mẫu THÔ của nguồn: phát lại log đọc mẫu thô rồi dự đoán
# lại bằng cùng mã, nên phát lại không so các cột pred_*.
POSE_FIELDS = ["n", "use", "t_session", "t_io", "available", "sample_t_io", "x", "y", "yaw_rad", "source_id",
               "simulated", "status", "reason", "pred_dt_s", "pred_speed_mps", "pred_steer_rad", "pred_x", "pred_y",
               "pred_yaw_rad"]
_PRED_BLANK = {name: "" for name in POSE_FIELDS if name.startswith("pred_")}
# Tệp ghi thêm của nguồn tư thế LiDAR (T2): định vị từng vòng, và tham chiếu MP của nguồn mô phỏng.
LOCALIZATION_FILE = "localization.csv"
SIM_TRUTH_FILE = "tu_the_that_mo_phong.csv"
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


def _close_io(io) -> None:
    """Đóng io (socket của bo ảo QEMU); lỗi khi đóng thì bỏ đối tượng cổng, lần sau mở lại từ đầu."""
    if io is None:
        return
    try:
        io.close()
    except OSError:
        if isinstance(io, SerialVehicleIO):
            io.transport = None
            io.connected = False


def _port_closed(io) -> bool:
    return isinstance(io, SerialVehicleIO) and io.transport is None


def _port_open(io) -> bool:
    return isinstance(io, SerialVehicleIO) and io.transport is not None


def _port_state_text(io) -> str:
    """Câu về cổng trong lời từ chối START trước mọi I/O của lần này (bước 0a, 0b), theo trạng thái THẬT của cổng: chưa
    mở; đang mở (bước 0c của một lần START trước đã mở, liên kết giữ cổng giữa các lần chạy); không phải cổng serial."""
    if _port_closed(io):
        return "Cổng chưa được mở, không gửi gì tới bo"
    if _port_open(io):
        return "Cổng đang mở (liên kết giữ cổng giữa các lần chạy), lần này không gửi gì tới bo"
    return "Không gửi gì tới bo"


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
    nguồn định vị). `VehicleLink.qemu_board(mode, source)` (02/10/2026): bo ảo QEMU với xe mô phỏng phía laptop."""

    def __init__(self, mode: DriveMode | str, io: VehicleIO | None = None, *, pose_source: PoseSource | None = None,
                 params: LinkParams | None = None, sim_config: SimIOConfig | None = None, _simulated: bool = False,
                 _qemu: QemuLinkSpec | None = None, clock: Callable[[], float] | None = None,
                 pose_factory=None, virtual_board: bool = False):
        mode = DriveMode(mode)
        if mode == DriveMode.SIM:
            raise ValueError("Chế độ SIM không đi qua VehicleLink (Session.set_vehicle_link(None))")
        if not _simulated and _qemu is None and (io is None or pose_source is None):
            raise ValueError("Cần VehicleIO và nguồn tư thế (hoặc dùng VehicleLink.simulated)")
        # Lớp bọc tiêm lỗi (`fault_inner`, safety/fault_injection.py, 02/10/2026) không được che luật SimTruthPose.
        base = unwrap_pose_source(pose_source)
        if isinstance(base, SimTruthPose) and (base.io is not io or not isinstance(io, SimVehicleIO)):
            # Tư thế thật của một xe mô phỏng KHÁC, ghép với bo thật, hoặc SimTruthPose dựng quanh chính bo serial
            # (sửa muộn tối 24/09/2026: trước đó lọt qua rồi START hỏng với AttributeError thay vì từ chối rõ ràng):
            # không phải tư thế của xe mà io điều khiển.
            raise ValueError("SimTruthPose chỉ dùng với chính SimVehicleIO của liên kết (bo mô phỏng); không ghép với "
                             "bo thật hay bo mô phỏng khác")
        # Bo ảo QEMU (02/10/2026): tư thế của xe mô phỏng phía laptop chỉ đi với chính io đó, và io đó chỉ đi với nó.
        if isinstance(base, QemuPlantPose) and (base.io is not io or not isinstance(io, QemuPlantVehicleIO)):
            raise ValueError("QemuPlantPose chỉ dùng với chính QemuPlantVehicleIO của liên kết (bo ảo QEMU)")
        if isinstance(io, QemuPlantVehicleIO) and not isinstance(base, QemuPlantPose):
            raise ValueError("Bo ảo QEMU chỉ đi với tư thế của chính xe mô phỏng phía laptop (QemuPlantPose)")
        self.mode = mode
        self.io = io
        self.pose_source = pose_source
        self.params = params or LinkParams()
        self.sim_config = sim_config
        self._simulated = _simulated
        # Bo ảo QEMU (02/10/2026): nguồn bo + xe mô phỏng; một đồng hồ cho mọi io của liên kết (t_io so được giữa các lần
        # chạy và với board_actions.csv). Socket mở ở bước 0c của `_open_run` như cổng COM; chỉ bo ảo đóng nó sau mỗi lần
        # chạy (QEMU chỉ phục vụ một client), cổng COM giữ mở giữa các lần chạy (T2).
        self._qemu = _qemu
        self._clock = clock or _perf_clock()
        # Sửa sau review 02/10/2026: io bo ảo truyền thẳng (`QemuPlantVehicleIO`, ví dụ với lớp bọc tiêm lỗi quanh
        # `QemuPlantPose`, luật ghép ở trên cho phép) cũng là liên kết bo ảo: đóng socket sau lần chạy, không phải phần
        # cứng chấp hành, bằng chứng và khóa board/plant của bo ảo (`is_qemu`). Trước đó chỉ `qemu_board()` có các nhãn
        # này.
        qemu_io = isinstance(io, QemuPlantVehicleIO)
        self._close_after_run = _qemu is not None or qemu_io
        # T2: nhà máy nguồn tư thế cho liên kết mô phỏng (gọi mỗi lần START với bo mô phỏng mới); None = SimTruthPose
        self.pose_factory = pose_factory
        # bo ảo (QEMU, hay bo khác đã gắn cờ): không phải phần cứng chấp hành (T2, bước 0b)
        self.virtual_board = bool(virtual_board) or _qemu is not None or qemu_io
        self.human: SimHumanDriver | PlantHumanDriver | None = None
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
        if self.io is not None:
            self._pose_hook("bind_clock", self.io.now)

    @classmethod
    def simulated(cls, mode: DriveMode | str, sim_config: SimIOConfig | None = None, *,
                  params: LinkParams | None = None, pose_factory=None, virtual_board: bool = False) -> "VehicleLink":
        return cls(mode, params=params, sim_config=sim_config or SimIOConfig(), _simulated=True,
                   pose_factory=pose_factory, virtual_board=virtual_board)

    @classmethod
    def serial_port(cls, mode: DriveMode | str, port: str, *, pose_source: PoseSource | None = None,
                    params: LinkParams | None = None, pose_factory=None, virtual_board: bool = False,
                    **io_kwargs) -> "VehicleLink":
        """Liên kết tới bo THẬT qua cổng `port` (thêm 24/09/2026). Cổng KHÔNG được mở ở đây
        (`SerialVehicleIO.deferred`). Không truyền nguồn tư thế thì dùng `NoPoseSource`, và START luôn bị từ chối
        trước khi mở cổng. Có nguồn tư thế (T2): cổng mở ở START (bước 0c của `_open_run`), sau các bước kiểm nguồn."""
        io = SerialVehicleIO.deferred(port, **io_kwargs)
        return cls(mode, io, pose_source=pose_source if pose_source is not None else NoPoseSource(), params=params,
                   pose_factory=pose_factory, virtual_board=virtual_board)

    @classmethod
    def qemu_board(cls, mode: DriveMode | str, source: QemuBoardSource, *, plant_config: PlantConfig | None = None,
                   params: LinkParams | None = None, clock: Callable[[], float] | None = None) -> "VehicleLink":
        """Liên kết tới bo ảo QEMU (firmware THẬT trong giả lập) với xe mô phỏng phía laptop (thêm 02/10/2026). Chưa mở
        gì ở đây; mỗi START lấy bo đang chạy từ `source`, io và `QemuPlantPose` dựng lúc đó. `clock`: đồng hồ io của liên
        kết (mặc định perf_counter() − t0; bo giả trong test có đồng hồ riêng)."""
        return cls(mode, params=params, _qemu=QemuLinkSpec(source, plant_config or PlantConfig()), clock=clock)

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
        self._wheelbase: float | None = None   # chiều dài cơ sở của xe lần chạy (dự đoán tư thế); None: chưa mở
        self._pose_fault: PoseSample | None = None
        self._last_valid_pose = Pose(0.0, 0.0, 0.0)

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
    def is_qemu(self) -> bool:
        """Liên kết tới bo ảo QEMU: `qemu_board` (02/10/2026), hoặc io bo ảo (`QemuPlantVehicleIO`) truyền thẳng (sửa
        sau review 02/10/2026)."""
        return self._qemu is not None or isinstance(self.io, QemuPlantVehicleIO)

    @property
    def pose_simulated(self) -> bool:
        return (self._simulated or self.is_qemu
                or bool(self.pose_source is not None and self.pose_source.simulated))

    @property
    def hardware_actuators(self) -> bool:
        """True khi lệnh của liên kết tới phần cứng chấp hành thật: không phải bo mô phỏng, không phải bo ảo đã gắn cờ
        `virtual_board`. Bo không gắn cờ coi là bo thật (T2)."""
        return not (self._simulated or isinstance(self.io, SimVehicleIO) or self.virtual_board)

    # ------------------------------------------------------------------ móc của nguồn tư thế (T2)
    def _pose_base(self):
        try:
            return unwrap_pose_source(self.pose_source)
        except ValueError:
            return self.pose_source

    def _pose_attr(self, name: str):
        """Móc `name` của nguồn tư thế đã bóc lớp tiêm lỗi, chỉ khi nó có THẬT (qua `inspect.getattr_static`, như
        `unwrap_pose_source`: proxy có `__getattr__` không bị hỏi); None khi không có."""
        base = self._pose_base()
        if base is None or inspect.getattr_static(base, name, None) is None:
            return None
        return getattr(base, name, None)

    def _pose_hook(self, name: str, *args, **kwargs):
        """Gọi móc `name` của nguồn tư thế (đã bóc lớp tiêm lỗi) nếu có. Lỗi KHÔNG BAO GIỜ thoát ra (có thể đang ở bước
        dừng): thành một dòng POSE_SOURCE_HOOK_FAILED; trả None."""
        hook = self._pose_attr(name)
        if hook is None:
            return None
        try:
            return hook(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - móc của nguồn không được chặn bước dừng
            try:
                t_io = self.io.now() if self.io is not None else None
            except Exception:  # noqa: BLE001
                t_io = None
            self._log_event(t_io, None, "vehicle_link", "POSE_SOURCE_HOOK_FAILED", "LOG", "log",
                            f"{name}() của nguồn tư thế lỗi: {exc!r}")
            return None

    def describe(self) -> dict:
        source = self.pose_source
        qemu = self.is_qemu
        factory = self.pose_factory
        info = self._pose_hook("describe") if source is not None else None
        return {
            "mode": self.mode.value,
            "io": type(self.io).__name__ if self.io is not None else ("SimVehicleIO" if self._simulated else
                                                                   "QemuPlantVehicleIO" if qemu else None),
            # T9: nguồn đóng dấu khung telemetry; phát lại log dựng lại khung và nguồn trạng thái với đúng tên này
            "io_source_id": getattr(self.io, "source_id", None),
            # Đồng hồ io mô phỏng hay không (score_run, khóa "clock" của link.json): bo ảo QEMU chạy theo perf_counter.
            "io_simulated": self._simulated or isinstance(self.io, SimVehicleIO),
            "pose_source": source.source_id if source is not None else (
                getattr(factory, "source_id", None) if factory is not None else
                SimTruthPose.source_id if self._simulated else QemuPlantPose.source_id if qemu else None),
            "pose_simulated": self.pose_simulated,
            "port": getattr(self.io, "port", None),
            "params": asdict(self.params),
            "sim_config": self.sim_config.to_dict() if self.sim_config is not None else None,
            "limits_check": self.limits_check.to_dict() if self.limits_check is not None else None,
            "evidence": ("simulation_only" if (self._simulated or isinstance(self.io, SimVehicleIO))
                         else QEMU_EVIDENCE if qemu else "hardware_untested"),
            # Bo ảo QEMU (02/10/2026): hai khóa luôn có (None với liên kết khác) để ReplayVehicleLink chép lại.
            "board": self._board_info(),
            "plant": self._plant_info(),
            "pose_source_info": info if isinstance(info, dict) else None,      # T2: bản đồ, cấu hình, ngưỡng
            "virtual_board": self.virtual_board,
        }

    def _board_info(self) -> dict | None:
        """Khóa "board": bo ảo của io hiện tại ({"kind": "qemu", ...`describe()` của bo}, cả khi io bo ảo được truyền
        thẳng); {"kind": "qemu"} trước lần chạy đầu của `qemu_board()`; None với liên kết không phải bo ảo."""
        io = self.io
        if isinstance(io, QemuPlantVehicleIO):
            return {"kind": "qemu", **io.board.describe()}
        return {"kind": "qemu"} if self._qemu is not None else None

    def _plant_info(self) -> dict | None:
        """Khóa "plant": tham số xe mô phỏng phía laptop của liên kết bo ảo (của `qemu_board()`, hay của io bo ảo truyền
        thẳng); None với liên kết khác."""
        if self._qemu is not None:
            return self._qemu.plant.to_dict()
        io = self.io
        return io.plant_config.to_dict() if isinstance(io, QemuPlantVehicleIO) else None

    def _now_or_none(self) -> float | None:
        """io.now(); chưa có io thì đồng hồ của liên kết bo ảo, còn lại None (dòng log không có t_io)."""
        if self.io is not None:
            return self.io.now()
        return self._clock() if self._qemu is not None else None

    # ------------------------------------------------------------------ bắt đầu lần chạy
    def _t_session(self, t_io: float) -> float:
        return t_io - self._io_t0

    def _link_event(self, t: float, code: str, message: str, action: str = "STOP",
                    source: str = "vehicle_link") -> SafetyEvent:
        return SafetyEvent(SourceStamp(source, max(0.0, t)), code, message, action)

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
            if self.is_qemu and tel.fault == Fault.LOOP_OVERRUN:
                problems[-1] += QEMU_OVERRUN_HINT
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
        source_check = self._pose_hook("start_problems")      # T2: định vị LiDAR đã bắt, đủ nhịp, đủ nhanh
        if source_check is not None:
            source_problems, source_warnings = source_check
            problems += [f"nguồn tư thế: {text}" for text in source_problems]
            if source_warnings:
                summary += ", cảnh báo nguồn tư thế: " + "; ".join(source_warnings)
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
        return (sample is not None and _pose_sample_problem(sample) is None and sample.status == POSE_OK
                and 0 <= self.io.now() - sample.t <= self.params.pose_age_limit_s)

    def _pose_problems(self, sample: PoseSample | None, scenario: Scenario, cfg: VehicleConfig) -> list[str]:
        """Kiểm tư thế lúc START (dùng cả trước ARM và sau ARM/DISARM): mới, gần điểm xuất phát, không chạm vật cản."""
        p = self.params
        problem = _pose_sample_problem(sample)
        if problem is not None:
            return [problem]
        if sample is not None and sample.status != POSE_OK:
            return [f"Định vị LiDAR báo {sample.status}: {sample.reason}"]
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
        self.start_refusals.append(_event_row(self._now_or_none(), None, source, code, "LOG", "before_start", message))
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
            source = self.pose_factory(new_io, scenario, cfg) if self.pose_factory is not None else SimTruthPose(new_io)
            self.io, self.pose_source = new_io, source
            self.human = SimHumanDriver(new_io) if self.observe_only else None
        self.event_rows = []              # dòng trước START của lần thử này (_log_event ghi vào đây)
        try:
            if self._qemu is not None:
                self._stage_qemu(scenario, cfg)     # bo ảo QEMU: trong try để dòng từ chối vào start_refusals
            if self._simulated and self.pose_factory is not None:
                self._pose_hook("bind_clock", self.io.now)
                self._pose_hook("warm_up", self.io.advance)      # T2: xe mô phỏng còn đứng yên trước START
            world = self._open_run(scenario, cfg, dt)
        except Exception as exc:
            if not isinstance(exc, VehicleLinkError):     # lỗi trước khi gửi ARM/DISARM (ví dụ nguồn tư thế ném)
                self._log_event(self._now_or_none(), None, "vehicle_link", "START_ABORTED", "LOG", "before_start",
                                repr(exc))
            attempt = self.event_rows
            if self._simulated:
                self.io.close()           # bo mô phỏng MỚI của lần bị từ chối; bo của lần trước giữ nguyên
            elif self._close_after_run:
                _close_io(self.io)        # bo ảo: đóng socket của io mới hay io dùng lại; không để kết nối nào mở
            self.io, self.pose_source, self.human, self.event_rows = previous
            self.start_refusals.extend(attempt)
            self.refused_starts += 1
            if isinstance(exc, VehicleLinkError):
                raise
            raise VehicleLinkError(f"Lỗi khi mở lần chạy: {exc!r}") from exc
        # Lần mới đã mở: tới đây mới thay log/kết quả của lần chạy trước.
        staged = self.event_rows
        if (self._simulated or self._qemu is not None) and previous[0] is not None and previous[0] is not self.io:
            previous[0].close()
        self._commit_run(staged, world)
        return world

    def _stage_qemu(self, scenario: Scenario, cfg: VehicleConfig) -> None:
        """Bo ảo QEMU (02/10/2026), đầu START: lấy bo đang chạy; chưa chạy → START_NO_QEMU_BOARD trước mọi I/O. io của
        liên kết không nối tới bo này (lần đầu, hoặc bo đã khởi động lại) → io và `QemuPlantPose` mới (lần bị từ chối thì
        `begin_run` trả io cũ). Rồi người đặt xe mô phỏng vào điểm xuất phát; quan sát: người lái mô phỏng."""
        spec = self._qemu
        board, reason = spec.source.current_board()
        if board is None:
            message = (f"Không bắt đầu được với bo ảo QEMU: {reason}. Chưa mở kết nối, không gửi gì; bấm 'Khởi động bo "
                       f"ảo' ở thẻ Bo điều khiển")
            self._log_event(self._clock(), None, "vehicle_link", "START_NO_QEMU_BOARD", "LOG", "before_start", message)
            raise VehicleLinkError(message)
        io = self.io
        if not (isinstance(io, QemuPlantVehicleIO) and io.board is board and io.port == board.url):
            io = QemuPlantVehicleIO(board, plant_config=spec.plant, clock=self._clock)
            self.io, self.pose_source = io, QemuPlantPose(io)
        io.place_vehicle(cfg, scenario.start)
        self.human = PlantHumanDriver(io, cfg) if self.observe_only else None

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
        self._wheelbase = world.cfg.wheelbase  # dự đoán tư thế (`_predicted_pose`), cả khi phát lại log
        self._running = True
        self.runs += 1
        state = world.state
        self._last_valid_pose = state.pose
        self.run_start = {"t_io0": self._io_t0, "x": state.pose.x, "y": state.pose.y, "yaw_rad": state.pose.yaw,
                          "steer_rad": state.steer, "state_source": state.source_id}
        self._pose_hook("run_started")        # T2: nguồn LiDAR: không tìm toàn cục, giữ chốt dừng tới run_ended

    def _open_run(self, scenario: Scenario, cfg: VehicleConfig, dt: float) -> MirroredWorld:
        io = self.io
        p = self.params
        if not getattr(self.pose_source, "available", True):
            # Bo thật mà chưa có nguồn tư thế thật (24/09/2026): từ chối TRƯỚC mọi I/O (không mở cổng, không HELLO).
            # Sửa sau review 02/10/2026: câu về cổng theo trạng thái THẬT (như bước 0b). Bước 0c của lần START trước có
            # thể đã mở cổng và liên kết giữ nó; trước đó lời luôn nói "Cổng chưa được mở".
            port = getattr(io, "port", None)
            hint = ("; dùng 'Kiểm kết nối bo' để kiểm liên lạc" if _port_closed(io) else
                    "; 'Kiểm kết nối bo' đóng cổng này của liên kết trước khi kiểm (lần Bắt đầu đỗ sau mở lại)"
                    if _port_open(io) else "")
            message = (f"Không bắt đầu được với bo thật{f' ({port})' if port else ''}: "
                       f"{getattr(self.pose_source, 'reason', NO_POSE_SOURCE_REASON)}. {_port_state_text(io)}{hint}")
            if not self.hardware_actuators:   # T2: bo mô phỏng / bo ảo với nguồn LiDAR chưa dùng được
                message = (f"Không bắt đầu được: nguồn tư thế {getattr(self.pose_source, 'source_id', '?')} chưa dùng "
                           f"được: {getattr(self.pose_source, 'reason', NO_POSE_SOURCE_REASON)}. Không gửi gì tới bo")
            self._log_event(io.now(), None, "vehicle_link", "START_NO_POSE_SOURCE", "LOG", "before_start", message)
            raise VehicleLinkError(message)
        self._check_pose_gate(io)
        if isinstance(io, SerialVehicleIO) and io.transport is None:
            # Bước 0c (T2): cổng của `serial_port` chưa mở → mở ở đây, sau mọi bước kiểm không I/O. Cổng giữ mở giữa
            # các lần chạy; `close()` đóng. Mở cổng có thể làm ESP32-S3 khởi động lại (DTR/RTS): wait_ready lo BOOT.
            # Bo ảo QEMU (02/10/2026): socket mở ở đây mỗi lần START, đóng sau lần chạy (`_close_after_run`).
            port = getattr(io, "port", None) or "cổng serial"
            try:
                io.reopen()
            except Exception as exc:          # SerialException/ConnectionRefusedError (OSError), VehicleIOError...
                message = (f"Không mở được kết nối tới bo ảo {io.port}: {exc}" if self.is_qemu
                           else f"Không mở được {port}: {exc}")
                self._log_event(io.now(), None, "vehicle_link", "START_NO_LINK", "LOG", "before_start", message)
                raise VehicleLinkError(message) from exc
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

    def _check_pose_gate(self, io) -> None:
        """Bước 0b (T2): `start_gate` của nguồn tư thế. Từ chối (bo thật ở VEHICLE_IO, điều kiện tiên quyết của định vị
        LiDAR chưa đạt) → START_POSE_UNVERIFIED và `VehicleLinkError`, KHÔNG I/O nào; cảnh báo → dòng
        POSE_SOURCE_WARNING. Móc lỗi khi phần cứng chấp hành thật → coi như từ chối (an toàn)."""
        gate = self._pose_attr("start_gate")
        if gate is None:
            return
        try:
            refusals, warnings = gate(self.mode.value, hardware=self.hardware_actuators)
        except Exception as exc:  # noqa: BLE001 - không kiểm được thì không chạy với bo thật
            refusals, warnings = ([f"kiểm điều kiện của nguồn tư thế lỗi: {exc!r}"] if self.hardware_actuators
                                  else []), [f"kiểm điều kiện của nguồn tư thế lỗi: {exc!r}"]
        for text in warnings:
            self._log_event(io.now(), None, "vehicle_link", "POSE_SOURCE_WARNING", "LOG", "before_start", text)
        if refusals:
            port = getattr(io, "port", None)
            message = (f"Không bắt đầu được với bo thật{f' ({port})' if port else ''} ở {self.mode.value}: "
                       + "; ".join(refusals) + f". {_port_state_text(io)}")
            self._log_event(io.now(), None, "vehicle_link", "START_POSE_UNVERIFIED", "LOG", "before_start", message)
            raise VehicleLinkError(message)

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

    def _pose(self, use: str, t: float) -> tuple[PoseSample | None, float | None, dict]:
        """Đọc nguồn tư thế rồi đọc io.now() NGAY SAU mẫu (thứ tự `observe` vẫn dùng), và (T9) ghi một dòng poses.csv:
        mẫu, hoặc available = 0 khi nguồn không có mẫu, cùng đồng hồ io lúc đọc. `use`: "estimate" (thế giới gương)
        hoặc "observe" (trạng thái đo cho bộ bám). Trả (mẫu, io.now(), dòng poses.csv); các cột pred_* để trống, chỉ
        `_predicted_pose` điền."""
        sample, failure = self._pose_fault, None
        if sample is None:
            try:
                sample = self.pose_source.latest() if self.pose_source is not None else None
            except Exception as exc:  # nguồn lỗi không được làm gián đoạn bước phanh
                failure = ("POSE_SOURCE_ERROR", f"Nguồn định vị lỗi: {type(exc).__name__}: {exc}")
            else:
                problem = _pose_sample_problem(sample)
                if problem is not None:
                    failure = ("INVALID_POSE", problem)
        now = self.io.now() if self.io is not None else None
        if failure is not None:
            # Chốt cả lỗi thoáng qua ở nhịp estimate: mẫu tốt trở lại trước nhịp observe không được nối tiếp lượt.
            # Mẫu lỗi hữu hạn giữ trong poses.csv để phát lại đúng quyết định; status khác OK không vào thế giới gương.
            self._pose_fault = sample = PoseSample(self._last_valid_pose, now if now is not None else t,
                                                   "vehicle_link", self.pose_simulated, *failure)
        if sample is not None and sample.status == POSE_OK:
            self._last_valid_pose = sample.pose
        row = {"n": len(self.pose_rows), "use": use, "t_session": round(t, 4), "t_io": _blank(now),
               "available": int(sample is not None)}
        if sample is None:
            row.update(sample_t_io="", x="", y="", yaw_rad="", source_id="", simulated="", status="", reason="")
        else:
            row.update(sample_t_io=sample.t, x=sample.pose.x, y=sample.pose.y, yaw_rad=sample.pose.yaw,
                       source_id=sample.source_id, simulated=int(sample.simulated), status=sample.status,
                       reason=sample.reason)
        row.update(_PRED_BLANK)
        self.pose_rows.append(row)
        return sample, now, row

    def _predicted_pose(self, sample: PoseSample, now: float | None, tel: VehicleTelemetry | None,
                        row: dict) -> Pose:
        """Tư thế giao cho bộ bám (`observe`) và thế giới gương (`estimate`) từ một mẫu OK (sửa sau review 02/10/2026).

        Khi `params.predict_pose`: dời tư thế của mẫu từ dấu thời gian của mẫu tới `now` (io.now() đọc liền sau mẫu)
        bằng tốc độ ĐO (`_measured_speed`, như trạng thái giao cho bộ bám) và góc lái ĐO của khung telemetry `tel`, giữ
        không đổi trong khoảng đó: mô hình xe đạp động học (`integrate_bicycle`, chiều dài cơ sở của cấu hình xe lần
        chạy). Chỉ dời khi tuổi THÔ của mẫu trong (0, pose_age_limit_s], khung telemetry mới (0 ≤ tuổi ≤
        max_state_age_s, cùng `now`) và có cả tốc độ lẫn góc lái đo; còn lại trả nguyên tư thế của mẫu (SimTruthPose có
        tuổi 0 nên không đổi). Ghi khoảng đã dời, tốc độ, góc lái và tư thế dời vào các cột pred_* của dòng poses.csv
        `row`. Không đổi mẫu và dấu thời gian của nó: mọi kiểm tuổi vẫn trên tuổi thô.

        Lý do (review 02/10/2026, MP với LiDAR mô phỏng ở tốc độ nghiệm thu 0,10 m/s): mẫu LiDAR tới bộ bám đã cũ
        0,04–0,13 s (trễ xử lý 0,04 s cộng chu kỳ quét 0,1 s); xe trễ 0,4–1,3 cm sau tư thế thật, cộng sai số định vị,
        vượt khe hở của đường lập (DO-4a: va chạm xe_sau khi mọi vòng định vị đều OK), và thế giới gương báo va chạm
        trễ."""
        p = self.params
        if not p.predict_pose or sample.status != POSE_OK or now is None or tel is None or self._wheelbase is None:
            return sample.pose
        age = now - sample.t
        speed, steer = self._measured_speed(tel), tel.steer_rad
        if (speed is None or steer is None or not 0 < age <= p.pose_age_limit_s
                or not 0 <= now - tel.stamp.t <= p.max_state_age_s):
            return sample.pose
        pose = integrate_bicycle(sample.pose, speed, steer, age, self._wheelbase)
        row.update(pred_dt_s=age, pred_speed_mps=speed, pred_steer_rad=steer, pred_x=pose.x, pred_y=pose.y,
                   pred_yaw_rad=pose.yaw)
        return pose

    def estimate(self, t: float, prev: VehicleState) -> VehicleState:
        """Trạng thái cho thế giới gương: tư thế từ nguồn định vị (dời tới io.now() khi `params.predict_pose`, xem
        `_predicted_pose`), tốc độ/góc lái đo; thiếu thì giữ giá trị trước."""
        pose = prev.pose
        source = prev.source_id
        sample, now, row = self._pose("estimate", t)
        speed, steer = prev.speed, prev.steer
        tel = self.io.latest() if self.io is not None else None
        if tel is not None:
            measured = self._measured_speed(tel)
            if measured is not None:
                speed = measured
            if tel.steer_rad is not None:
                steer = tel.steer_rad
        if sample is not None and sample.status == POSE_OK:      # T2: mẫu không OK không vào thế giới gương
            pose = self._predicted_pose(sample, now, tel, row)
            source = self._state_source(sample)
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
        sample, now, row = self._pose("observe", t)
        if sample is not None and sample.status != POSE_OK:
            # T2: nguồn LiDAR báo POSE_LOST / POSE_DISAGREE / POSE_UNCHECKED: dừng với đúng mã đó, nguồn = id của nguồn
            return None, self._link_event(t, sample.status, f"Định vị LiDAR: {sample.reason}: dừng và chờ đánh giá "
                                                            f"lại", source=sample.source_id)
        # Tuổi THÔ của mẫu (trước mọi dự đoán): dự đoán không bao giờ làm một mẫu cũ thành "mới".
        if sample is None or not 0 <= now - sample.t <= p.pose_age_limit_s:
            return None, self._link_event(t, "STALE_POSE", "Tư thế từ nguồn định vị cũ hoặc thiếu: dừng và chờ "
                                                           "đánh giá lại")
        pose = self._predicted_pose(sample, now, tel, row)       # sửa sau review 02/10/2026: bù tuổi của mẫu
        return VehicleState(pose, speed, tel.steer_rad, t, source_id=self._state_source(sample)), None

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
        self._pose_hook("run_ended")          # T2: sau lệnh dừng + DISARM; lỗi chỉ thành dòng log
        tel = io.latest() if io is not None else None
        self.result = {"t_session": t, "outcome": outcome, "reason": reason,
                       "board_state": tel.state.name if tel is not None else None,
                       "commands_sent": io.stats.commands_sent if io is not None else 0,
                       "telemetry_received": io.stats.telemetry_received if io is not None else 0}
        if self._close_after_run and io is not None:
            # Bo ảo QEMU (02/10/2026): TCP của QEMU chỉ phục vụ một client; nhả cho "Kiểm kết nối bo", "Xóa lỗi bo".
            _close_io(io)

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
        if self._qemu is not None:
            board, reason = self._qemu.source.current_board()
            return None if board is not None else f"bo ảo QEMU chưa chạy ({reason})"
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
        io = self.io if self._qemu is None else self._qemu_fault_io()
        opened_here = isinstance(io, SerialVehicleIO) and io.transport is None
        if opened_here:
            try:
                io.reopen()
            except Exception as exc:          # SerialException (OSError), VehicleIOError, ValueError, ImportError...
                target = self._qemu_target(io) or io.port or "cổng serial"
                report = BoardFaultClear(target, False, error=f"Không mở được {target}: {exc}",
                                         kind=QEMU_KIND if self.is_qemu else "")
                report.stamp(io)
                self.board_actions.append(report.to_row())
                return report
        close_error: OSError | None = None
        try:
            report = self._clear_fault_on(io, request_timeout_s)
            if self.is_qemu:
                report.target, report.kind = self._qemu_target(io), QEMU_KIND
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

    def _qemu_fault_io(self) -> QemuPlantVehicleIO:
        """io cho "Xóa lỗi bo" của liên kết bo ảo (02/10/2026): io của liên kết nếu nó nối tới bo đang chạy; không thì
        một io tạm tới bo đó (không giữ lại), cùng đồng hồ liên kết. Mở và đóng như cổng COM chưa mở."""
        board, reason = self._qemu.source.current_board()
        if board is None:
            raise VehicleLinkError(f"Không xóa lỗi bo: bo ảo QEMU chưa chạy ({reason})")
        io = self.io
        if isinstance(io, QemuPlantVehicleIO) and io.board is board and io.port == board.url:
            return io
        return QemuPlantVehicleIO(board, plant_config=self._qemu.plant, clock=self._clock)

    def _qemu_target(self, io) -> str | None:
        """Cột target của board_actions.csv với bo ảo: "bo ảo QEMU socket://…"; None với liên kết khác."""
        return f"bo ảo QEMU {io.port}" if self.is_qemu else None

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
        bo" của liên kết này, T15) và link.json. Hai tệp cộng dồn luôn được tạo, có thể chỉ có dòng tiêu đề. Nguồn tư
        thế LiDAR thêm tệp của nó (T2, dưới).

        T13 (02/10/2026): events.csv có cả dòng `session_stop` (quyết định dừng của phiên) và cột t_perf (cả
        start_refusals.csv); link.json có thêm khóa "clock" (cặp t_io/perf_counter lúc mở lần chạy, xem docstring của
        mô-đun). Khóa này không nằm trong `describe()`, nên snapshot của lần chạy không đổi.

        T9 (02/10/2026): băng phát lại log: poses.csv, clock.csv, cột call của telemetry.csv và events.csv; link.json có
        thêm "run_start" (None khi chưa mở lần chạy nào), "log_format" (`LOG_FORMAT`) và, qua `describe()`,
        "io_source_id".

        T2 (02/10/2026): nguồn tư thế có `log_rows()` → thêm localization.csv (định vị từng vòng: 5 vòng trước START và
        các vòng của lần chạy); nguồn mô phỏng có `write_truth_reference` → thêm tu_the_that_mo_phong.csv + .json (tham
        chiếu MP của evaluation/reference_pose.py, đồng hồ t_session = t_io − t_io0)."""
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
                    run_start=self.run_start, log_format=LOG_FORMAT,
                    ecoqos=ecoqos_state())     # 02/10/2026: ngoài describe(), phát lại log và snapshot không đổi
        target = path / "link.json"
        target.write_text(json.dumps(info, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        written["link.json"] = target
        written.update(self._write_pose_source_logs(path))
        return written

    def _write_pose_source_logs(self, path: Path) -> dict[str, Path]:
        """Tệp của nguồn tư thế LiDAR (T2). Lỗi của nguồn chỉ làm thiếu tệp đó (dòng POSE_SOURCE_HOOK_FAILED trong
        bộ nhớ), không làm hỏng các tệp khác."""
        written: dict[str, Path] = {}
        rows = self._pose_hook("log_rows")
        if rows is not None:
            from autopark.lidar.pose_estimator import write_localization_csv

            written[LOCALIZATION_FILE] = write_localization_csv(path / LOCALIZATION_FILE, rows)
        if self.run_start is not None:
            reference = self._pose_hook("write_truth_reference", path / SIM_TRUTH_FILE, self._io_t0)
            if reference is not None:
                written[SIM_TRUTH_FILE] = reference[0]
                written[reference[1].name] = reference[1]
        return written

    def release_port(self) -> str | None:
        """Đóng cổng serial mà liên kết đang giữ mở giữa các lần chạy (bước 0c, T2), khi không có lần chạy nào đang mở
        (sửa sau review 02/10/2026). Cổng trở lại "chưa mở"; bước 0c mở lại (và HELLO lại) ở lần Bắt đầu đỗ sau. Giao
        diện gọi hàm này trước "Kiểm kết nối bo" trên cùng cổng: trên Windows một cổng COM chỉ mở được một lần, nên mở
        lần hai để kiểm hỏng ("Access is denied") khi liên kết còn giữ cổng. Không gửi gì tới bo: ngoài lần chạy bo đã
        ở DISARMED (`end_run`, hay DISARM khi START bị từ chối sau ARM; quan sát không ARM). Trả tên cổng đã đóng; None
        khi không có gì để đóng (không phải cổng serial, cổng chưa mở, đang có lần chạy, liên kết đã đóng)."""
        io = self.io
        if self._closed or self._running or not _port_open(io):
            return None
        _close_io(io)
        return getattr(io, "port", None) or "cổng serial"

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
    kind: str = ""                                # loại bo trong dòng đầu báo cáo; "" = theo `simulated` (02/10/2026)

    @property
    def ok(self) -> bool:
        return self.error is None and self.hello is not None and len(self.frames) >= self.frames_wanted

    def lines(self) -> list[str]:
        """Báo cáo tiếng Việt, mỗi phần tử một dòng (giao diện hiển thị nguyên văn)."""
        kind = self.kind or ("bo MÔ PHỎNG (SimVehicleIO + FirmwareModel)" if self.simulated
                             else "bo thật qua cổng serial")
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
                connect_timeout_s: float = 1.0, frames_timeout_s: float = 1.0, kind: str = "") -> BoardProbe:
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
                        simulated, frames_wanted=frames, kind=kind)
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
    kind: str = ""                                # loại bo trong dòng đầu báo cáo; "" = theo `simulated` (02/10/2026)

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
        kind = self.kind or ("bo MÔ PHỎNG (SimVehicleIO + FirmwareModel)" if self.simulated
                             else "bo qua cổng serial")
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
