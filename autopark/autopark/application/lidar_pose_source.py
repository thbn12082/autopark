"""Nguồn tư thế LiDAR cho `VehicleLink` (thêm 02/10/2026, T2): bộ ghép (a) + (b) của `lidar/pose_estimator.py` nối vào
phiên đỗ xe theo hợp đồng `PoseSource` của application/vehicle_link.py. Người dùng giao quyết định 02/10/2026 ("làm
hết"): làm theo ĐỀ XUẤT mục 7 của docs/KIEN_TRUC.md; mọi ngưỡng vẫn là ĐỀ XUẤT – CHỜ CHỐT.

- `LidarPoseSource`: RPLIDAR C1 thật hoặc bản ghi phát lại (ngăn LiDAR của `ui.lidar_app`). `simulated = False`. Nhận
  vòng quét từ luồng đọc (`on_scan`, không bao giờ chặn: hàng đợi `queue_size` vòng, vòng mới nhất thắng, đếm vòng bỏ).
  Luồng "dinh_vi_lidar" là luồng DUY NHẤT chạm bộ ghép; lệnh từ giao diện (gợi ý, bắt đầu/kết thúc lần chạy, ngắt nguồn)
  được gửi vào hàng lệnh. Sau mỗi vòng, luồng công bố một ảnh chụp dưới khóa ngắn; không bao giờ chạm Qt.
  `latest()` đổi dấu thời gian vòng quét (perf_counter lúc vòng về máy) sang đồng hồ io: t = io.now() − (perf() − t_vòng).
  KHÔNG kẹp, KHÔNG đóng dấu lại: mẫu cũ mang tuổi thật, nên VehicleLink dừng STALE_POSE khi luồng treo hay cáp rời.
- `SimLidarPoseSource`: LiDAR MÔ PHỎNG (lidar/synthetic.py) quét sa bàn từ tư thế THẬT của xe mô phỏng; xác định theo
  seed, không luồng. Bản đồ dựng lúc tạo từ vài chỗ đặt tổng hợp. Chỉ ghép với bo mô phỏng. `simulated = True`.
- `LidarSimPoseFactory`: VehicleLink mô phỏng gọi mỗi lần Bắt đầu đỗ (bo mô phỏng mới, nguồn mới).

Cổng START (`start_gate`): bo THẬT ở VEHICLE_IO bị từ chối khi `LidarPoseConfig.unmet()` còn mục nào (gá chưa đo, p04,
DV-2, DV-1): VehicleLink ghi START_POSE_UNVERIFIED và không mở cổng, không gửi gì. Quan sát, bo ảo đã gắn cờ và bo mô
phỏng chỉ ghi POSE_SOURCE_WARNING. Với bo thật mọi đường này CHƯA THỬ (chưa có ESP32-S3, chưa có xe; 02/10/2026).

Nguồn vòng quét (sửa 02/10/2026 sau review gộp đợt 2): ngăn LiDAR báo loại nguồn ĐANG gắn (`set_feed_kind`, mỗi lần gắn
hay ngắt nguồn). `evidence` chỉ là "device" khi vòng quét đến từ driver RPLIDAR C1 do chính ngăn mở; bản ghi phát lại
(`--recording`) là "recording_replay", phát lại phiên T3b (`--session-replay`) là "session_replay", nguồn khác (test) là
"other_source", ngăn đã ngắt là "no_feed". Khác "device" thì bo THẬT bị từ chối ở MỌI nhánh (START_POSE_UNVERIFIED,
kể cả khi đủ điều kiện tiên quyết và ở Quan sát); bo mô phỏng / bo ảo đã gắn cờ chỉ ghi POSE_SOURCE_WARNING. Chỉ kiểm
bằng test.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
import math
import threading
import time

import numpy as np

from autopark.application.vehicle_link import POSE_OK, PoseSample
from autopark.domain.types import Pose, Scenario, VehicleConfig
from autopark.lidar.localize import LocalizationMap
from autopark.lidar.pose_config import LidarPoseConfig
from autopark.lidar.pose_estimator import (HISTORY, INIT, LATCHED, POSE_DISAGREE, POSE_LOST, POSE_UNCHECKED, TRACKING,
                                           LidarPoseEstimator, Published, step_row)

__all__ = ["POSE_LOST", "POSE_DISAGREE", "POSE_UNCHECKED", "LidarPoseSource", "SimLidarPoseSource",
           "LidarSimPoseFactory", "PoseSourceStatus", "build_sim_map", "evidence_for_feed"]

NO_SCAN_S = 1.0                  # không có vòng quét mới quá lâu → nguồn không dùng được (START bị từ chối)
BEFORE_START_ROWS = 5            # số dòng before_start giữ lại cho localization.csv
MAX_RUN_ROWS = 20000             # chặn trên số dòng một lần chạy (≈ 33 phút ở 10 Hz)

# Nhãn `evidence` theo loại nguồn vòng quét mà ngăn LiDAR báo (`LidarDock.feed_kind`): CHỈ "live" (driver RPLIDAR C1 do
# chính ngăn mở) là "device"; None = ngăn đã ngắt nguồn.
FEED_EVIDENCE = {"live": "device", "recording_replay": "recording_replay", "session_replay": "session_replay",
                 "other": "other_source", None: "no_feed"}
FEED_TEXT = {"recording_replay": "bản ghi phát lại (--recording)",
             "session_replay": "phát lại một phiên ghi (--session-replay)",
             "other_source": "nguồn không phải driver RPLIDAR C1 của ngăn LiDAR (nguồn giả hay nơi khác gắn)",
             "no_feed": "không có nguồn nào (ngăn LiDAR đã ngắt)"}


def evidence_for_feed(kind: str | None) -> str:
    """Nhãn `evidence` của nguồn tư thế LiDAR cho loại nguồn vòng quét `kind`; loại lạ là "other_source", không bao giờ
    "device"."""
    return FEED_EVIDENCE.get(kind, "other_source")


def _vn(value: float, digits: int) -> str:
    """Số kiểu Việt Nam (dấu phẩy thập phân) cho chữ trên giao diện."""
    return f"{value:.{digits}f}".replace(".", ",")


@dataclass(frozen=True)
class PoseSourceStatus:
    """Ảnh chụp trạng thái nguồn cho giao diện (nhãn "Định vị LiDAR: …", làm mới 5 Hz)."""

    state: str
    available: bool
    text: str
    vehicle_pose: Pose | None
    age_s: float | None
    rate_hz: float
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    drops: int
    scans: int


def _gate(config: LidarPoseConfig, mode: str, hardware: bool) -> tuple[list[str], list[str]]:
    """(từ chối, cảnh báo): từ chối chỉ khi bo thật ở VEHICLE_IO; còn lại các mục chưa đạt thành cảnh báo."""
    unmet = config.unmet()
    if hardware and mode == "VEHICLE_IO":
        return unmet, []
    return [], [f"nguồn tư thế LiDAR chưa đủ điều kiện cho bo thật: {item}" for item in unmet]


def _rate(times: list[float], now: float) -> float:
    recent = sorted(t for t in times if now - 2.0 <= t <= now + 1e-9)
    return (len(recent) - 1) / (recent[-1] - recent[0]) if len(recent) >= 3 and recent[-1] > recent[0] else 0.0


def _status_text(state: str, pub: Published | None, age: float | None, rate: float, lat50, lat95, drops: int,
                 reason: str) -> str:
    if pub is not None and pub.status == POSE_OK and state in (TRACKING, "DEGRADED"):
        v = pub.vehicle_pose
        head = "OK" if state == TRACKING else "1 vòng không OK"
        text = (f"Định vị LiDAR: {head} · ({_vn(v.x, 3)}; {_vn(v.y, 3)}) m, {_vn(math.degrees(v.yaw), 1)}° · tuổi "
                f"{_vn(age, 2) if age is not None else '—'} s · {_vn(rate, 1)} vòng/s")
        if lat50 is not None:
            text += f" · xử lý trung vị {lat50:.0f} ms, p95 {lat95:.0f} ms"
        return text + f" · bỏ {drops} vòng"
    if state == LATCHED and pub is not None:
        return (f"Định vị LiDAR: LẠC ({pub.status}: {pub.reason_vi}): tự khởi tạo lại sau 1 s khi không chạy; đang "
                f"chạy thì giữ dừng")
    return f"Định vị LiDAR: {reason or 'đang khởi tạo (tìm quanh điểm xuất phát)…'}"


class LidarPoseSource:
    """C1 thật hoặc bản ghi phát lại; xem docstring mô-đun. `evidence`: nhãn ban đầu ("device" khi không ai báo nguồn,
    như các test dựng thẳng), rồi theo `set_feed_kind` của ngăn LiDAR: "device", "recording_replay", "session_replay",
    "other_source" hay "no_feed"."""

    simulated = False

    def __init__(self, estimator: LidarPoseEstimator, config: LidarPoseConfig, *, map_info: dict,
                 source_id: str = "lidar_c1_localize", threaded: bool = True, perf=time.perf_counter,
                 evidence: str = "device"):
        self.estimator = estimator
        self.config = config
        self.map_info = dict(map_info)
        self.source_id = source_id
        self.threaded = threaded
        self.perf = perf
        self.evidence = evidence
        self.feed_kind: str | None = None          # loại nguồn ngăn LiDAR báo lần gần nhất (None: chưa báo / đã ngắt)
        self._run_evidence: str | None = None      # `evidence` lúc mở lần chạy gần nhất (link.json ghi sau lần chạy)
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._queue: deque = deque()
        self._commands: deque = deque()
        self._io_now = None
        self._published: Published | None = None
        self._state = INIT
        self._history: deque = deque(maxlen=HISTORY)       # (t, quyết định, tư thế xe)
        self._last_processed_t: float | None = None
        self._received: deque = deque(maxlen=256)
        self._last_received: float | None = None
        self._latencies: deque = deque(maxlen=20)
        self._health: tuple[list[str], list[str]] = (["chưa xử lý vòng quét nào"], [])
        self._phase = "before_start"
        self._idle_rows: deque = deque(maxlen=BEFORE_START_ROWS)   # dòng ngoài lần chạy gần nhất
        self._pre_rows: list[dict] | None = None                    # chụp lúc mở lần chạy (None: chưa chạy lần nào)
        self._run_rows: list[dict] = []
        self.lidar_mirror: bool | None = None
        self.scans_received = 0
        self.scans_processed = 0
        self.drops = 0
        self.worker_error: str | None = None
        self.closed = False

    # ------------------------------------------------------------------------------------------ luồng đọc → hàng đợi
    def on_scan(self, scan, quality=None, t_first_perf: float | None = None, t_perf: float | None = None) -> None:
        """Người tiêu thụ của `ScanReader` (luồng bất kỳ, không bao giờ chặn lâu). `t_perf`: perf_counter lúc vòng về
        máy; thiếu thì lấy bây giờ."""
        t_perf = self.perf() if t_perf is None else float(t_perf)
        with self._lock:
            if self.closed:
                return
            self.scans_received += 1
            self._received.append(t_perf)
            self._last_received = t_perf
            dropped = 0
            while len(self._queue) >= self.config.localizer.queue_size:
                old = self._queue.popleft()
                dropped += old[4] + 1
                self.drops += 1
            self._queue.append((scan, quality, t_first_perf, t_perf, dropped))
        self._wake.set()

    def _post(self, *command) -> None:
        with self._lock:
            self._commands.append(command)
        self._wake.set()

    # ------------------------------------------------------------------------------------------------ luồng xử lý
    def start(self) -> None:
        if not self.threaded or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="dinh_vi_lidar", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(0.05)
            self._wake.clear()
            if self._stop.is_set():
                break
            try:
                self.pump()
            except Exception as exc:  # noqa: BLE001 - lỗi của luồng phải thành mã dừng, không lặng lẽ treo
                self._fail(exc)
                return

    def _fail(self, exc: BaseException) -> None:
        with self._lock:
            self.worker_error = repr(exc)
            pub = self._published
            pose = pub.vehicle_pose if pub is not None else Pose(math.nan, math.nan, math.nan)
            t = pub.t if pub is not None else (self._last_received or 0.0)
            self._published = Published(POSE_LOST, pose, t, f"luồng định vị LiDAR lỗi: {exc!r}")
            self._state = LATCHED

    def pump(self) -> int:
        """Xử lý lệnh đang chờ rồi vòng quét đang chờ (luồng "dinh_vi_lidar", hoặc test với threaded=False). Trả số
        vòng đã xử lý."""
        processed = 0
        while True:
            with self._lock:
                commands = list(self._commands)
                self._commands.clear()
                item = self._queue.popleft() if self._queue else None
            for command in commands:
                self._apply(command)
            if item is None:
                return processed
            self._process(item)
            processed += 1

    def _apply(self, command) -> None:
        est = self.estimator
        kind = command[0]
        if kind == "hint":
            est.set_hint(command[1])
        elif kind == "arm":
            est.arm()
            with self._lock:
                self._phase = "run"
                self._pre_rows = [dict(row, phase="before_start") for row in self._idle_rows]
                self._run_rows = []
        elif kind == "disarm":
            est.disarm()
            with self._lock:
                self._phase = "after_run"
        elif kind == "reset":
            est.reset_feed(command[1])
        self._snapshot(None)

    def _process(self, item) -> None:
        scan, _quality, t_first, t_perf, dropped = item
        step = self.estimator.process(np.asarray(scan.angles_rad, np.float64), np.asarray(scan.ranges_m, np.float64),
                                      t_perf, t_first=t_first)
        t_done = self.perf()
        step.t_done, step.dropped_before = t_done, dropped
        io_now = self._io_now
        if io_now is not None:
            try:
                step.t_io = io_now() - (self.perf() - t_perf)
            except Exception:  # noqa: BLE001 - đồng hồ io hỏng: bỏ cột, không làm hỏng luồng
                step.t_io = None
        self._snapshot(step)

    def _snapshot(self, step) -> None:
        est = self.estimator
        with self._lock:
            received = list(self._received)
        problems, warnings = est.health(self.perf(), received)
        with self._lock:
            self._published = est.published()
            self._state = est.state
            self._health = (problems, warnings)
            if step is None:
                return
            step.phase = self._phase
            row = step_row(step)
            if self._phase == "run":
                if len(self._run_rows) < MAX_RUN_ROWS:
                    self._run_rows.append(row)
            else:
                self._idle_rows.append(row)
            self._history.append((step.t, step.decision, step.vehicle))
            self._last_processed_t = step.t
            self._latencies.append(step.latency_s)
            self.scans_processed += 1

    # ------------------------------------------------------------------------------------- hợp đồng PoseSource
    def bind_clock(self, io_now) -> None:
        """Đồng hồ io (`VehicleIO.now`) để đổi dấu thời gian vòng quét; chưa gắn thì `latest()` trả None."""
        self._io_now = io_now

    def latest(self) -> PoseSample | None:
        io_now = self._io_now
        if io_now is None:
            return None
        with self._lock:
            pub = self._published
        if pub is None:
            return None
        t = io_now() - (self.perf() - pub.t)
        return PoseSample(pub.vehicle_pose, t, self.source_id, False, pub.status, pub.reason_vi)

    def _unavailable_reason(self) -> str:
        with self._lock:
            closed, error, last, pub, state = (self.closed, self.worker_error, self._last_received, self._published,
                                               self._state)
        if closed:
            return "nguồn tư thế LiDAR đã đóng"
        if error:
            return f"luồng định vị LiDAR lỗi: {error}"
        mirror = self._mirror_problem()
        if mirror:
            return mirror
        if last is None:
            return "Chưa có vòng quét: bấm Kết nối ở ngăn LiDAR"
        age = self.perf() - last
        if age > NO_SCAN_S:
            return f"Không có vòng quét mới trong {_vn(age, 1)} s (LiDAR ngắt hoặc treo)"
        if pub is None or state == INIT:
            return "đang khởi tạo định vị (tìm quanh điểm xuất phát)…"
        if pub.status != POSE_OK:
            return f"định vị LiDAR {pub.status}: {pub.reason_vi}"
        return ""

    @property
    def available(self) -> bool:
        return not self._unavailable_reason()

    @property
    def reason(self) -> str:
        return self._unavailable_reason()

    def _mirror_problem(self) -> str:
        want = self.map_info.get("mirror")
        if want is None or self.lidar_mirror is None or bool(want) == bool(self.lidar_mirror):
            return ""
        return (f"bản đồ ghi với chiều góc {'đảo' if want else 'không đảo'} nhưng LiDAR đang "
                f"{'đảo' if self.lidar_mirror else 'không đảo'} chiều góc")

    def set_lidar_mirror(self, mirror: bool | None) -> None:
        self.lidar_mirror = mirror

    def set_feed_kind(self, kind: str | None) -> None:
        """Ngăn LiDAR báo nguồn vòng quét đang gắn (mỗi lần gắn hay ngắt nguồn, và khi nhận nguồn này làm người tiêu
        thụ): "live", "recording_replay", "session_replay", "other" hay None (đã ngắt). `evidence` theo đó; chỉ "live"
        là "device" (sửa 02/10/2026 sau review gộp đợt 2)."""
        self.feed_kind = kind
        self.evidence = evidence_for_feed(kind)

    def feed_problem(self) -> str:
        """Lý do vòng quét không phải của LiDAR thật gá trên xe (`evidence` khác "device"); rỗng khi là thiết bị."""
        evidence = self.evidence
        if evidence == "device":
            return ""
        what = FEED_TEXT.get(evidence, f"nguồn {evidence!r}")
        return f"vòng quét LiDAR không phải của LiDAR thật gá trên xe: {what} (evidence {evidence})"

    def start_gate(self, mode: str, *, hardware: bool) -> tuple[list[str], list[str]]:
        """Như `_gate`, cộng nguồn vòng quét (sửa 02/10/2026 sau review gộp đợt 2): vòng quét không phải của LiDAR thật
        (bản ghi phát lại, phát lại phiên, nguồn khác, ngăn đã ngắt) → bo thật bị từ chối ở MỌI nhánh, kể cả Quan sát
        (log của bo thật không được mang tư thế lấy từ bản ghi); bo mô phỏng / bo ảo đã gắn cờ chỉ cảnh báo."""
        refusals, warnings = _gate(self.config, mode, hardware)
        problem = self.feed_problem()
        if problem and hardware:
            refusals = [problem, *refusals]
        elif problem:
            warnings = [problem, *warnings]
        return refusals, warnings

    def start_problems(self) -> tuple[list[str], list[str]]:
        """Điều kiện START tính ở luồng xử lý sau vòng gần nhất, cộng kiểm lúc gọi (vòng quét còn tới không, mirror)."""
        with self._lock:
            problems, warnings = list(self._health[0]), list(self._health[1])
            last = self._last_received
        if last is None or self.perf() - last > NO_SCAN_S:
            problems.append(self._unavailable_reason() or "không có vòng quét mới")
        mirror = self._mirror_problem()
        if mirror:
            problems.append(mirror)
        return problems, warnings

    def run_started(self) -> None:
        self._run_evidence = self.evidence     # nhãn của lần chạy: link.json ghi sau đó (ngăn đã ngắt…) vẫn đúng nguồn
        self._post("arm")

    def run_ended(self) -> None:
        self._post("disarm")

    def set_hint(self, vehicle_pose: Pose) -> None:
        self._post("hint", vehicle_pose)

    def feed_reset(self, reason: str = "") -> None:
        """Ngăn LiDAR ngắt nguồn hay đổi chiều góc: bỏ vòng đang chờ (của nguồn cũ) và báo bộ ghép."""
        with self._lock:
            self._queue.clear()
        self._post("reset", reason)

    def pose_for_stamp(self, t_perf: float) -> tuple[str, Pose | None]:
        """Như `LidarPoseEstimator.pose_for_time`, trên ảnh chụp (gọi được từ luồng giao diện)."""
        with self._lock:
            history, last = list(self._history), self._last_processed_t
        if last is None or t_perf > last + 1e-9:
            return "pending", None
        for t, decision, vehicle in reversed(history):
            if abs(t - t_perf) <= 1e-9:
                return ("ok", vehicle) if decision == "OK" and vehicle is not None else ("bad", None)
            if t < t_perf - 1e-9:
                break
        return "bad", None

    def status(self) -> PoseSourceStatus:
        now = self.perf()
        with self._lock:
            pub, state = self._published, self._state
            received = list(self._received)
            latencies = [v for v in self._latencies if v is not None]
            drops, scans = self.drops, self.scans_processed
        rate = _rate(received, now)
        age = None if pub is None else now - pub.t
        lat50 = float(np.percentile(latencies, 50)) * 1000 if latencies else None
        lat95 = float(np.percentile(latencies, 95)) * 1000 if latencies else None
        reason = self._unavailable_reason()
        text = _status_text(state, pub, age, rate, lat50, lat95, drops, reason)
        return PoseSourceStatus(state, not reason, text, pub.vehicle_pose if pub is not None else None, age, rate,
                                lat50, lat95, drops, scans)

    def log_rows(self) -> list[dict]:
        """Dòng localization.csv: 5 dòng cuối trước lúc mở lần chạy gần nhất (phase before_start) rồi các dòng của lần
        chạy đó; chưa chạy lần nào thì 5 dòng gần nhất."""
        with self._lock:
            if self._pre_rows is None:
                return list(self._idle_rows)
            return list(self._pre_rows) + list(self._run_rows)

    def describe(self) -> dict:
        with self._lock:
            latencies = [v for v in self._latencies if v is not None]
            counts = {"received": self.scans_received, "processed": self.scans_processed, "dropped": self.drops}
        cfg = self.config
        # "evidence": nguồn vòng quét lúc mở lần chạy gần nhất (log của lần chạy đó); chưa chạy thì nguồn hiện tại
        return {"source_id": self.source_id, "simulated": False, "evidence": self._run_evidence or self.evidence,
                "map": dict(self.map_info),
                "config": {"path": None if cfg.path is None else str(cfg.path), "sha256": cfg.sha256},
                "mount": cfg.mount.to_dict(), "mount_measured": cfg.mount.measured, "unmet": cfg.unmet(),
                "max_pose_age_s": cfg.max_pose_age_s, "thresholds": asdict(cfg.localizer), "counts": counts,
                "latency_s": None if not latencies else {"p50": float(np.percentile(latencies, 50)),
                                                         "p95": float(np.percentile(latencies, 95))},
                "worker_error": self.worker_error}

    def close(self) -> None:
        """Dừng luồng xử lý (chờ tối đa 1 s). Chủ của nguồn (cửa sổ bàn thử) gọi; VehicleLink không đóng nguồn này."""
        with self._lock:
            self.closed = True
            self._queue.clear()
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=1.0)


# ------------------------------------------------------------------------------------------------- LiDAR mô phỏng
def _free_spot(scenario: Scenario, x: float, y: float, clearance: float) -> bool:
    from shapely.geometry import Point, Polygon

    b = scenario.bounds
    if not (b.xmin + clearance <= x <= b.xmax - clearance and b.ymin + clearance <= y <= b.ymax - clearance):
        return False
    point = Point(x, y)
    return all(Polygon(o.corners()).distance(point) >= clearance for o in scenario.obstacles)


def build_sim_map(scenario: Scenario, config: LidarPoseConfig, rng: np.random.Generator,
                  start_sensor: Pose | None = None) -> tuple[LocalizationMap, dict]:
    """Bản đồ tĩnh của LiDAR mô phỏng: `map_placements` chỗ đặt tổng hợp (cảm biến ở điểm xuất phát rồi các điểm lưới
    3 × 3 trống trong sa bàn), mỗi chỗ `map_scans_per_placement` vòng có nhiễu, ray-cast qua `build_map_from_poses`.
    Gồm cả vật cản của sa bàn lúc dựng. Trả (bản đồ định vị, thông tin bản đồ cho describe())."""
    from autopark.lidar.map_builder import MapBuildConfig, auto_grid, build_map_from_poses
    from autopark.lidar.synthetic import raycast, scenario_segments
    from autopark.perception.costmap import GridSpec

    sim = config.sim
    b = scenario.bounds
    spots = []
    if start_sensor is not None and _free_spot(scenario, start_sensor.x, start_sensor.y, 0.05):
        spots.append((start_sensor.x, start_sensor.y, start_sensor.yaw))
    for fy in (0.5, 0.25, 0.75):
        for fx in (0.5, 0.25, 0.75):
            x, y = b.xmin + fx * b.width, b.ymin + fy * b.height
            if _free_spot(scenario, x, y, 0.15):
                spots.append((x, y, 0.3 * len(spots)))
    spots = spots[:sim.map_placements]
    segments = scenario_segments(scenario, walls_from_bounds=sim.walls_from_bounds, room_margin_m=sim.room_margin_m)
    scans = []
    for spot in spots:
        for _ in range(sim.map_scans_per_placement):
            angles, ranges = raycast(spot, segments, beams=sim.beams, fov_rad=math.radians(sim.fov_deg),
                                     max_range_m=sim.max_range_m, min_range_m=sim.min_range_m, noise_m=sim.noise_m,
                                     dropout=sim.dropout, rng=rng)
            scans.append(((angles, ranges), spot))
    build = MapBuildConfig(max_range=min(sim.max_range_m, config.localize.max_range_m),
                           min_range=config.localize.min_range_m)
    # Lưới lệch nửa ô: tường của sa bàn mô phỏng nằm ở tọa độ chẵn (biên, cạnh hộp) sẽ rơi đúng TÂM ô thay vì trên biên
    # hai ô. Tường trên biên ô cho dải OCCUPIED dày hai ô, trường khoảng cách phẳng (= 0) quanh điểm chạm, tinh chỉnh của
    # `localize` không có gradient và báo AMBIGUOUS "degenerate" (thấy 02/10/2026 trên sa bàn 3 × 2 m trống).
    hits = []
    for (a, r), s in scans:
        ok = np.isfinite(r) & (r <= build.max_range)
        hits.append(np.column_stack([s[0] + r[ok] * np.cos(a[ok] + s[2]), s[1] + r[ok] * np.sin(a[ok] + s[2])]))
    points = np.vstack([np.array([[s[0], s[1]] for s in spots])] + hits)
    grid0 = auto_grid(points, build.resolution, build.padding + build.resolution)
    half = build.resolution / 2
    grid = GridSpec(grid0.x_min - half, grid0.x_max - half, grid0.y_min - half, grid0.y_max - half, build.resolution)
    _, states, grid = build_map_from_poses(scans, grid, build)
    lmap = LocalizationMap(states, grid, config.localize, source="lidar_sim")
    info = {"path": None, "source": "LiDAR mô phỏng: bản đồ dựng từ sa bàn (tổng hợp)", "frame": "sa_ban",
            "session_ready": True, "mirror": None, "grid": grid.__dict__,
            "placements": [{"x_m": s[0], "y_m": s[1], "yaw_deg": math.degrees(s[2])} for s in spots],
            "scans_per_placement": sim.map_scans_per_placement}
    return lmap, info


class SimLidarPoseSource:
    """LiDAR MÔ PHỎNG + bộ ghép, đồng bộ trên đồng hồ của bo mô phỏng (xác định theo seed). `latest()`: khi tới hạn
    vòng quét (`period_s`), tạo MỘT vòng ở tư thế thật hiện tại, đóng dấu `clock()` (vòng quá hạn khác tính là bị bỏ) và
    xử lý; đang chạy thì kết quả có sau `latency_s`, ngoài lần chạy thì có ngay."""

    simulated = True

    def __init__(self, truth, clock, scenario: Scenario, cfg: VehicleConfig, config: LidarPoseConfig, *, seed: int = 0,
                 source_id: str = "lidar_sim_localize", truth_speed=None):
        from autopark.lidar.synthetic import SyntheticScanner

        self.truth, self.clock = truth, clock
        self.truth_speed = truth_speed            # tốc độ THẬT (m/s) khi có: đuôi đứng yên của tệp tham chiếu MP
        self._end_speed: float | None = None
        self.scenario, self.cfg, self.config = scenario, cfg, config
        self.source_id = source_id
        self.seed = seed
        rng = np.random.default_rng(seed)
        self.scanner = SyntheticScanner(scenario, config.sim, config.mount, rng=rng)
        start_sensor = config.mount.sensor_pose(scenario.start)
        lmap, self.map_info = build_sim_map(scenario, config, np.random.default_rng(seed + 1), start_sensor)
        self.estimator = LidarPoseEstimator(lmap, config.localizer, mount=config.mount, odometry=config.odometry,
                                            self_mask=cfg, hint=scenario.start)
        self.next_scan_t = clock()
        self._pending: deque = deque()
        self._published: Published | None = None
        self._running = False
        self._phase = "before_start"
        self._received: deque = deque(maxlen=256)
        self._last_scan_t: float | None = None
        self._idle_rows: deque = deque(maxlen=BEFORE_START_ROWS)
        self._pre_rows: list[dict] | None = None
        self._run_rows: list[dict] = []
        self._truth: list[tuple[float, Pose]] = []
        self.io_t0: float | None = None
        self.drops = 0
        self.scans_processed = 0

    # ------------------------------------------------------------------------------------------------- quét + xử lý
    def _service(self) -> None:
        now = self.clock()
        if self.scanner.silent or now + 1e-9 < self.next_scan_t:
            return
        period = self.config.sim.period_s
        due = int(math.floor((now - self.next_scan_t) / period + 1e-9)) + 1
        for k in range(due - 1):                 # vòng quá hạn: coi như đã tới nhưng bị bỏ (chỉ vòng mới nhất được làm)
            self._received.append(self.next_scan_t + k * period)
        self.drops += due - 1
        self.next_scan_t += due * period
        vehicle = self.truth()
        angles, ranges = self.scanner.scan(vehicle)
        step = self.estimator.process(angles, ranges, now, truth=vehicle)
        latency = self.config.sim.latency_s if self._running else 0.0
        step.t_io, step.t_done, step.dropped_before, step.phase = now, now + latency, due - 1, self._phase
        self._received.append(now)
        self._last_scan_t = now
        self.scans_processed += 1
        row = step_row(step, time_base="io")
        if self._phase == "run":
            if len(self._run_rows) < MAX_RUN_ROWS:
                self._run_rows.append(row)
            self._truth.append((now, vehicle))
        else:
            self._idle_rows.append(row)
        pub = self.estimator.published()
        if latency > 0:
            self._pending.append((now + latency, pub))
        else:
            self._published = pub

    def _release(self) -> None:
        now = self.clock()
        while self._pending and self._pending[0][0] <= now + 1e-12:
            self._published = self._pending.popleft()[1]

    def latest(self) -> PoseSample | None:
        self._service()
        self._release()
        pub = self._published
        if pub is None:
            return None
        return PoseSample(pub.vehicle_pose, pub.t, self.source_id, True, pub.status, pub.reason_vi)

    def warm_up(self, advance) -> None:
        """Trước START, xe mô phỏng còn đứng yên: tiến đồng hồ của bo mô phỏng từng `period_s` (`advance` =
        `SimVehicleIO.advance`) tới khi điều kiện START của nguồn đạt hoặc hết `warmup_max_s`."""
        sim = self.config.sim
        deadline = self.clock() + sim.warmup_max_s
        while True:
            self._service()
            self._release()
            problems, _ = self.start_problems()
            if not problems or self.clock() >= deadline - 1e-9:
                return
            advance(sim.period_s)

    # ------------------------------------------------------------------------------------- hợp đồng PoseSource
    def bind_clock(self, io_now) -> None:
        """Nguồn mô phỏng dùng sẵn đồng hồ của bo mô phỏng (`clock`); không cần gắn."""

    def _unavailable_reason(self) -> str:
        pub, state = self._published, self.estimator.state
        if self._last_scan_t is None:
            return "LiDAR mô phỏng chưa quét vòng nào"
        if self.clock() - self._last_scan_t > NO_SCAN_S:
            return f"Không có vòng quét mới trong {_vn(self.clock() - self._last_scan_t, 1)} s (LiDAR mô phỏng ngừng)"
        if pub is None or state == INIT:
            return "đang khởi tạo định vị (tìm quanh điểm xuất phát)…"
        if pub.status != POSE_OK:
            return f"định vị LiDAR {pub.status}: {pub.reason_vi}"
        return ""

    @property
    def available(self) -> bool:
        return not self._unavailable_reason()

    @property
    def reason(self) -> str:
        return self._unavailable_reason()

    def start_gate(self, mode: str, *, hardware: bool) -> tuple[list[str], list[str]]:
        return _gate(self.config, mode, hardware)

    def start_problems(self) -> tuple[list[str], list[str]]:
        problems, warnings = self.estimator.health(self.clock(), list(self._received))
        if self._last_scan_t is None or self.clock() - self._last_scan_t > NO_SCAN_S:
            problems.append(self._unavailable_reason() or "không có vòng quét mới")
        return problems, warnings

    def run_started(self) -> None:
        self._running = True
        self._phase = "run"
        self._pre_rows = [dict(row, phase="before_start") for row in self._idle_rows]
        self._run_rows = []
        self.io_t0 = self.clock()
        self._truth = [(self.io_t0, self.truth())]
        self.estimator.arm()

    def run_ended(self) -> None:
        self._running = False
        self._phase = "after_run"
        self.estimator.disarm()
        now = self.clock()
        if not self._truth or self._truth[-1][0] < now:
            self._truth.append((now, self.truth()))
        self._end_speed = self.truth_speed() if self.truth_speed is not None else None

    def set_hint(self, vehicle_pose: Pose) -> None:
        self.estimator.set_hint(vehicle_pose)

    def pose_for_stamp(self, t: float) -> tuple[str, Pose | None]:
        return self.estimator.pose_for_time(t)

    def status(self) -> PoseSourceStatus:
        now = self.clock()
        pub = self._published
        rate = _rate(list(self._received), now)
        age = None if pub is None else now - pub.t
        latency = self.config.sim.latency_s * 1000 if self._running else 0.0
        text = _status_text(self.estimator.state, pub, age, rate, latency, latency, self.drops,
                            self._unavailable_reason())
        return PoseSourceStatus(self.estimator.state, self.available, "MÔ PHỎNG · " + text,
                                pub.vehicle_pose if pub is not None else None, age, rate, latency, latency, self.drops,
                                self.scans_processed)

    def log_rows(self) -> list[dict]:
        if self._pre_rows is None:
            return list(self._idle_rows)
        return list(self._pre_rows) + list(self._run_rows)

    def truth_rows(self) -> list[tuple[float, Pose]]:
        """(t_io, tư thế THẬT của xe mô phỏng) ở mỗi vòng quét của lần chạy, cộng lúc mở và lúc kết thúc lần chạy."""
        return list(self._truth)

    def write_truth_reference(self, csv_path, t_io0: float):
        """Tệp tham chiếu MP (`evaluation/reference_pose.py`): tư thế THẬT của xe mô phỏng, đồng hồ t_session =
        t_io − t_io0, hệ sa bàn, tâm trục sau. Không phải phép đo độc lập. None khi chưa có mẫu nào."""
        from autopark.evaluation.reference_pose import (SIM_TRUTH_SOURCE, ReferenceAccuracy, ReferenceMeta,
                                                        ReferenceSample, write_reference)
        from autopark.perception.paths import utc_now

        samples, last = [], None
        for t_io, pose in self._truth:
            t = round(t_io - t_io0, 4)
            if t < 0 or (last is not None and t <= last):
                continue
            samples.append(ReferenceSample(t, pose))
            last = t
        if not samples:
            return None
        notes = ("Tư thế THẬT của xe mô phỏng ở mỗi vòng quét của LiDAR mô phỏng (10 Hz), lúc mở và lúc kết thúc lần "
                 "chạy; không phải phép đo độc lập: chỉ dùng ở mức MP.")
        if self._end_speed == 0.0 and samples:
            # Như `reference_from_sim_rows`: lần chạy dừng đúng lúc xe đứng yên, nên thêm 1 s đứng yên ở tư thế cuối
            # (bo mô phỏng không nhận lệnh nào sau DISARM) để bộ chấm có tư thế cuối.
            period = self.config.sim.period_s
            last = samples[-1]
            count = max(1, int(round(1.0 / period)))
            samples += [ReferenceSample(round(last.t + k * period, 4), last.pose) for k in range(1, count + 1)]
            notes += (f" Thêm {count} mẫu đứng yên (1 s) ở tư thế cuối sau khi lần chạy kết thúc, vì tốc độ thật lúc kết "
                      f"thúc bằng 0 và bo mô phỏng không nhận lệnh nào sau đó; phần này không phải dữ liệu ghi.")
        meta = ReferenceMeta("MP", "t_session", ReferenceAccuracy(0.0, 0.0, SIM_TRUTH_SOURCE), notes=notes,
                             source={"pose_source": self.source_id, "t_io0": t_io0}, tool="lidar_pose_source",
                             created_utc=utc_now())
        return write_reference(csv_path, samples, meta)

    def describe(self) -> dict:
        cfg = self.config
        return {"source_id": self.source_id, "simulated": True, "evidence": "simulation_only", "seed": self.seed,
                "map": dict(self.map_info),
                "config": {"path": None if cfg.path is None else str(cfg.path), "sha256": cfg.sha256},
                "mount": cfg.mount.to_dict(), "mount_measured": cfg.mount.measured, "unmet": cfg.unmet(),
                "max_pose_age_s": cfg.max_pose_age_s, "thresholds": asdict(cfg.localizer), "sim": asdict(cfg.sim),
                "counts": {"processed": self.scans_processed, "dropped": self.drops}}

    def close(self) -> None:
        """Không có luồng nào để dừng."""


class LidarSimPoseFactory:
    """Nhà máy nguồn LiDAR mô phỏng cho `VehicleLink.simulated(..., pose_factory=...)`: gọi với bo mô phỏng mới, sa bàn
    và xe của mỗi lần Bắt đầu đỗ. Dùng lại được với bất kỳ cặp (tư thế thật, đồng hồ) nào qua `for_truth`."""

    source_id = "lidar_sim_localize"
    simulated = True

    def __init__(self, config: LidarPoseConfig, *, seed: int = 0):
        self.config = config
        self.seed = seed

    def __call__(self, io, scenario: Scenario, cfg: VehicleConfig) -> SimLidarPoseSource:
        return self.for_truth(lambda: io.truth.pose, io.now, scenario, cfg, truth_speed=lambda: io.truth.speed)

    def for_truth(self, truth, clock, scenario: Scenario, cfg: VehicleConfig, *,
                  truth_speed=None) -> SimLidarPoseSource:
        return SimLidarPoseSource(truth, clock, scenario, cfg, self.config, seed=self.seed, source_id=self.source_id,
                                  truth_speed=truth_speed)
