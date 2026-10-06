"""Chấm một lần chạy nghiệm thu (T5): đọc log + tham chiếu độc lập + bố trí tham chiếu, tính các đại lượng N-D, N-V1,
N-P của docs/NGUONG_NGHIEM_THU_DE_XUAT.md và ghi một dòng biên bản (docs/KICH_BAN_NGHIEM_THU.md mục 2.3).
Thêm 02/10/2026.

Dùng (mỗi lệnh một dòng, chạy trong thư mục autopark):

    python -m autopark.evaluation.score_run --scenario DO-1 --attempt 1 --level MP --log runs/nghiem_thu/mo_phong/do1_l01/lan_chay_vehicle_io --sim-truth --layout scenarios/bai_do_xe.json --report runs/nghiem_thu/mo_phong/bien_ban_mo_phong.csv
    python -m autopark.evaluation.score_run --scenario DO-1 --attempt 3 --level XT/M3 --log <thư mục _vehicle_io> --reference <run>/tu_the_tham_chieu.csv --layout docs/evidence/nghiem_thu/bo_tri_do1.json --touch khong --intervention khong --methods R5 --report docs/evidence/bien_ban_nghiem_thu_<ngay>.csv

Nguyên tắc (NGUONG mục 0, quy tắc đề xuất):

- Quy tắc 2: log của hệ thống (R6) không bao giờ là số nghiệm thu cho vị trí, hướng, khoảng hở hay quãng dừng. Các số
  đó lấy từ tham chiếu độc lập: tệp tư thế R1 (`evaluation/reference_pose.py`), hai điểm thước R2 (`--r2-points`),
  hoặc, chỉ ở mức MP và cho xe ảo của BT, tư thế thật của mô phỏng (`--sim-truth`). Log cho thời điểm, lý do dừng,
  lệnh đã gửi, số lần đổi chiều đã lập.
- Quy tắc 3: sai số tham chiếu > 1/3 ngưỡng thì kết luận "không kiểm được", không ghi "đạt"; giá trị vẫn được ghi. Với
  kiểm thân xe (N-D3, N-D5) sai số gồm cả sai số hướng nhân cánh tay đòn tới góc thân xe xa nhất (≈ 0,26 m với xe giả
  định), chặt hơn KICH_BAN mục 3.5 bước 4: chỉ có thể biến "đạt" thành "không kiểm được".
- Công cụ chỉ tự đề xuất THANH_CONG (lần đỗ: nhóm DO hay VC-5do, COMPLETED, mọi kiểm của kịch bản đạt và mọi điều
  kiện THÀNH CÔNG của NGUONG mục 1 đạt, kể cả điều kiện danh sách của kịch bản không có) và THAT_BAI (có kiểm không đạt;
  chạm hay can thiệp ghi tay luôn là THAT_BAI vì N-D4, N-D9 tuyệt đối). Mọi trường hợp khác để trống cho người chấm;
  không bao giờ tự ghi DUNG_DUNG hay KHONG_TINH. `--result` của người luôn thắng, khác đề xuất thì ghi vào ghi_chu.
- N-V1 (cập nhật 02/10/2026; người dùng giao quyết định 02/10/2026 ('làm hết'), ngưỡng vẫn ĐỀ XUẤT – CHỜ CHỐT): ngoài
  tốc độ đo, khi tệp ngưỡng có `target_mps` thì kiểm cả vế "tốc độ mục tiêu ≤ 0,10 m/s ở đợt đầu" bằng lệnh đã gửi
  (target_speed_mps của commands.csv, target_speed của RunLog gói SIM); vượt thì N-V1 không đạt (chạy với
  configs/vehicle_nghiem_thu.json). Ô v_max_do_mps vẫn chỉ ghi tốc độ đo. Xe mô phỏng bị kẹp ở max_speed_mps của cấu
  hình xe nên ở MP tốc độ đo không vượt mức đó (ghi chú tự thêm). Ghi chú thêm (không đổi kết luận) khi kịch bản không
  phải lần đỗ chạy nhanh hơn vế mục tiêu (ngưỡng phản ứng NGUONG mục 3 giả định tốc độ ≤ N-V1), và khi xe của lần chạy
  (run.json) khác kích thước xe dùng để chấm.

Log đọc được: thư mục `<tên>_vehicle_io/` của `VehicleLink.write_logs` (RunLog `<tên>.csv` ở bên cạnh), gói
`<tên>_<giờ>/` của `export_run` cho lần chạy qua VehicleIO (T9: chấm từ `vehicle_io/` của gói như log VehicleIO, RunLog
là telemetry.csv của gói; không bao giờ như gói SIM), và gói SIM của `export_run`. Đọc được cả định dạng T13 (dòng
`handling` = `session_stop` và cột `t_perf` trong events.csv, khóa `clock` của link.json) lẫn log cũ không có các phần
đó: khi đó t_phát_hiện lấy gần đúng bằng dòng STOP đầu của commands.csv (±20 ms). Với bo thời gian thực, t_phát_hiện là
t_io − t0 của dòng (lúc phiên quyết định), không phải thời gian bước. Dấu đồng bộ T14 (`<tên>_sync_marks.csv`, cột
SYNC_FIELDS của evaluation/sync_marks.py) dùng cho R7: cặp `--sync <t_ref>=mark:<n>`, mốc `--event mark:<n>+<dt>`;
cột `time_scale` (tốc độ chạy của giao diện) cho hệ số perf_counter → t_session khi phiên chạy thời gian mô phỏng (tệp
cũ: giả định 1×, ghi ở tệp chi tiết). Cập nhật 02/10/2026 sau rà soát (gói T9, N-D6(a), đề xuất ket_qua, mốc vòng tròn
code:, log xuất giữa lần chạy, đồng hồ bo thời gian thực, tốc độ chạy).

Ngưỡng và bảng kiểm theo kịch bản: configs/nguong_nghiem_thu.json, bản sao các số ĐỀ XUẤT – CHỜ CHỐT của NGUONG; chốt
thì sửa cả tệp đó lẫn hai tài liệu. Mới kiểm trên dữ liệu tổng hợp và lần chạy mô phỏng (tests/test_score_run.py,
02/10/2026); CHƯA chấm lần chạy thật nào (chưa có R1/T4, chưa có xe).
"""
from __future__ import annotations

import argparse
import bisect
import csv
from dataclasses import asdict, dataclass, field, fields, is_dataclass, replace
from datetime import datetime
import hashlib
from itertools import accumulate
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys

from shapely.geometry import Point, Polygon

from autopark.application.vehicle_link import QemuPlantPose, SimTruthPose
from autopark.domain.types import Obstacle, ParkingSlot, Pose, Scenario, VehicleConfig, wrap_angle
from autopark.evaluation.reference_pose import (ReferenceAccuracy, ReferenceTrack, SyncPair, read_reference,
                                                reference_from_sim_rows, static_reference)
from autopark.geometry.footprint import body_corners, body_polygon, bounds_polygon, obstacle_polygon
from autopark.lidar import recording as lidar_recording
from autopark.perception.paths import PROJECT, atomic_write_json, utc_now
from autopark.storage.run_store import is_vehicle_io_package
from autopark.storage.scenario_store import load_scenario, load_vehicle_config
from autopark.transport.qemu_plant import QEMU_EVIDENCE

TOOL = "autopark.evaluation.score_run"
DETAIL_SCHEMA_VERSION = 1
DEFAULT_THRESHOLDS = PROJECT / "configs" / "nguong_nghiem_thu.json"

# Cột biên bản đúng thứ tự KICH_BAN mục 2.3; khóa một dòng là (mã, biến thể, lần, mức)
BIEN_BAN_FIELDS = ["ma_kich_ban", "bien_the", "lan", "ngay_gio", "muc_thu", "ket_qua", "nguyen_nhan",
                   "sai_so_vi_tri_cm", "sai_so_huong_deg", "trong_o", "cham", "khoang_ho_min_cm", "doi_chieu_lap",
                   "doi_chieu_thuc", "thoi_gian_s", "v_max_do_mps", "t_phat_hien_s", "quang_dung_cm",
                   "khoang_con_lai_cm", "can_thiep", "phuong_phap_do", "thu_muc_du_lieu", "ghi_chu"]
ROW_KEY = ("ma_kich_ban", "bien_the", "lan", "muc_thu")
RESULTS = ("THANH_CONG", "DUNG_DUNG", "THAT_BAI", "KHONG_TINH")
LEVEL_RE = re.compile(r"^(MP|BT|XT)(/M[0-3])?$")
CODE_RE = re.compile(r"[A-Z]{2}-\d+")                     # mã kịch bản của KICH_BAN mục 4
WHEN_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")

DAT, KHONG_DAT, KHONG_KIEM_DUOC, KHONG_AP_DUNG, CHI_BAO_SO = (
    "dat", "khong_dat", "khong_kiem_duoc", "khong_ap_dung", "chi_bao_so")
VERDICT_LABELS = {DAT: "đạt", KHONG_DAT: "KHÔNG ĐẠT", KHONG_KIEM_DUOC: "không kiểm được",
                  KHONG_AP_DUNG: "không áp dụng", CHI_BAO_SO: "chỉ báo số"}

CHECK_IDS = ("N-D1", "N-D2", "N-D3", "N-D4", "N-D5", "N-D6", "N-D7", "N-D9", "N-V1", "N-P1", "N-P2", "N-P3",
             "N-P4", "N-P5c", "N-P6", "N-P7", "N-P8", "N-P10", "0-COMMAND")
LIMIT_PARAMS = {"N-D1": ("max_cm",), "N-D2": ("max_deg",), "N-D5": ("min_cm",), "N-D6": ("standstill_mps",),
                "N-D7": ("max_run_s",), "N-V1": ("max_mps",), "N-P1": ("max_s",), "N-P2": ("max_cm",),
                "N-P3": ("min_cm",), "N-P5c": ("max_cm", "max_s"), "N-P6": ("max_cm",), "N-P7": ("max_cm",),
                "N-P8": ("max_cm",)}
# Khóa tùy chọn (02/10/2026): N-V1.target_mps = vế "tốc độ mục tiêu ≤ 0,10 m/s" (lệnh đã gửi); tệp không có thì bỏ vế đó
LIMIT_OPTIONAL = {"N-V1": ("target_mps",)}
VEHICLE_GEOMETRY_KEYS = ("wheelbase_m", "width_m", "front_overhang_m", "rear_overhang_m", "max_steer_deg")
STOP_DISTANCE_CHECKS = ("N-P2", "N-P5c", "N-P6", "N-P7", "N-P8")
GEOMETRY_CHECKS = ("N-D1", "N-D2", "N-D3", "N-D5")
PARKING_RESULT_KEYS = ("VC-5do",)          # phần đỗ của VC-5 cũng là một lần đỗ (KICH_BAN mục 1.4)
THRESHOLD_STATUSES = ("DE_XUAT_CHO_CHOT", "CHOT")
# Kiểm chạy cả khi danh sách của kịch bản không có, CHỈ để đề xuất ket_qua (ô của chúng để trống): với lần đỗ là mọi
# điều kiện THÀNH CÔNG của NGUONG mục 1 (N-D3 tự "không áp dụng" khi bố trí không có ô); với kịch bản khác là N-D4 và
# N-D9, tuyệt đối ở mọi kịch bản (N-D4 "0 lần trong mọi lần chạy", N-D9 "mọi can thiệp ghi thành THẤT BẠI").
SUCCESS_CHECKS = ("N-D1", "N-D2", "N-D3", "N-D4", "N-D7", "N-D9", "N-V1")
ABSOLUTE_CHECKS = ("N-D4", "N-D9")

SESSION_STOP = "session_stop"              # handling của dòng dừng do PHIÊN quyết định (T13, vehicle_link.SESSION_STOP)
USER_STOP_CODES = ("USER_STOP", "USER_RESET")   # mã T13 của dừng/đặt lại do người
USER_STOP_REASON = "Người dùng yêu cầu dừng"    # lý do mặc định của Session.request_stop (log cũ, gói SIM)
SIM_TRUTH_POSE = SimTruthPose.source_id
EMULATED_PORT_PREFIXES = ("socket://", "loop://")
# Bo ảo QEMU với xe mô phỏng phía laptop (02/10/2026; người dùng giao quyết định 02/10/2026, ĐỀ XUẤT): log là mô phỏng
# (mức MP, XT từ chối), và tư thế qemu_plant_pose là tư thế thật của xe mô phỏng nên --sim-truth dùng được, chỉ ở MP.
QEMU_PLANT_POSE = QemuPlantPose.source_id
EMULATED_EVIDENCE = frozenset({"simulation_only", QEMU_EVIDENCE})
SIM_TRUTH_SOURCES = frozenset({("simulation_only", SIM_TRUTH_POSE), (QEMU_EVIDENCE, QEMU_PLANT_POSE)})
VEHICLE_IO_SUFFIX = "_vehicle_io"
SIM_BUNDLE_SUFFIX_RE = re.compile(r"_\d{8}_\d{6}_\d{6}$")   # <tên>_<YYYYmmdd_HHMMSS_micro> của "Xuất log CSV…"
PACKAGE_LOG_DIR = "vehicle_io"             # thư mục log VehicleLink trong gói export_run của lần chạy VehicleIO (T9)
VEHICLE_IO_REPLAY_KIND = "vehicle_io_log"  # replay_kind trong manifest.json của gói đó (gói SIM không có khóa này)
NOT_ENDED_STATES = ("RUNNING", "STOPPING")  # result.json state của gói SIM xuất khi lần chạy chưa kết thúc
STOP_ROW_ERROR_S = 0.02                    # nhịp điều khiển 50 Hz: sự kiện ở [t_STOP − 20 ms, t_STOP] (NGUONG mục 3)
SPEED_HALF_WINDOW_S = 0.1                  # tốc độ tham chiếu tại một mốc: quãng trên ±0,1 s

# Dấu đồng bộ T14 (cột SYNC_FIELDS của evaluation/sync_marks.py)
SYNC_MARK, CLOCK_ROW = "SYNC_MARK", "CLOCK"
RUN_STATES = ("RUNNING", "STOPPING", "STOPPED", "COMPLETED", "FAULT")
END_STATES = ("STOPPED", "COMPLETED", "FAULT")
SYNC_MARKS_SUFFIX = "_sync_marks.csv"


class ScoreError(ValueError):
    """Đầu vào không chấm được. CLI in 'LỖI: …' ra stderr, thoát mã 2 và không ghi gì."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _cell(value) -> float | None:
    """Ô số của log hay CSV: rỗng → None; không phải số → ValueError (nơi gọi đổi thành ScoreError)."""
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    number = float(text)
    return number if math.isfinite(number) else None


def _read_csv(path: Path, files: dict[str, str]) -> tuple[list[str], list[dict]]:
    if not path.exists():
        raise ScoreError(f"thiếu tệp {path}")
    try:
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            header = list(reader.fieldnames or [])
    except (OSError, csv.Error, UnicodeDecodeError) as exc:
        raise ScoreError(f"không đọc được {path}: {exc}") from exc
    files[str(path)] = _sha256(path)
    return header, rows


def _read_json(path: Path, files: dict[str, str]):
    if not path.exists():
        raise ScoreError(f"thiếu tệp {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ScoreError(f"không đọc được {path}: {exc}") from exc
    files[str(path)] = _sha256(path)
    return value


# ====================================================================== ngưỡng và bảng kịch bản
@dataclass(frozen=True)
class AnalysisParams:
    """Tham số phân tích tham chiếu (ĐỀ XUẤT, chỉnh trên nhiễu tổng hợp 2–3 mm; chưa có R1 thật)."""

    final_window_s: float = 1.0           # tư thế cuối: trung vị của 1 s cuối khi xe đứng yên (KICH_BAN mục 3.8)
    standstill_radius_m: float = 0.01     # đứng yên: mọi vị trí đã làm trơn trong cửa sổ cách trung vị ≤ 1 cm
    standstill_min_s: float = 0.5         # cửa sổ đứng yên tối thiểu sau một mốc (quãng dừng, tự chạy lại)
    settle_m: float = 0.003               # t_đứng_yên: mẫu đầu cách vị trí dừng ≤ 3 mm
    smooth_s: float = 0.2                 # trung bình trượt có tâm (tắt với MP)
    path_step_m: float = 0.01             # tỉa quãng: giữ điểm cách điểm giữ trước ≥ 1 cm (nhiễu không cộng dồn)
    max_gap_s: float = 0.5                # khoảng trống dữ liệu dài hơn mà xe đã dịch → không kiểm khoảng hở/tốc độ
    restart_m: float = 0.02               # dịch quá 2 cm sau khi đã đứng yên → tự chạy lại (N-P10)
    reversal_hysteresis_m: float = 0.02   # đếm đổi chiều sau ≥ 2 cm đi theo chiều ngược
    speed_window_m: float = 0.2           # N-V1: tốc độ trung bình trên đoạn 0,2 m
    clock_anchor_error_s: float = 0.1     # ghép perf_counter–t_session ở một dòng mốc khi phiên chạy thời gian mô phỏng
    clock_drift: float = 0.05             # độ trôi lớn nhất giả định giữa thời gian mô phỏng và thời gian thực


@dataclass(frozen=True)
class ScenarioRule:
    key: str
    checks: tuple[str, ...]
    max_cusps: int | None = None

    @property
    def group(self) -> str:
        return self.key.split("-", 1)[0]

    @property
    def parking(self) -> bool:
        """Lần đỗ: kết quả THÀNH CÔNG có nghĩa (KICH_BAN mục 1.4)."""
        return self.group == "DO" or self.key in PARKING_RESULT_KEYS


@dataclass(frozen=True)
class Thresholds:
    path: Path
    sha256: str
    status: str
    notes: str
    reference_ratio: float
    analysis: AnalysisParams
    limits: dict
    scenarios: dict

    def limit(self, check: str, name: str) -> float:
        return float(self.limits[check][name])

    def limit_or_none(self, check: str, name: str) -> float | None:
        """Giới hạn tùy chọn (LIMIT_OPTIONAL): None khi tệp ngưỡng không có khóa đó."""
        value = self.limits.get(check, {}).get(name)
        return float(value) if value is not None else None

    def rule(self, scenario: str, variant: str = "") -> ScenarioRule:
        """Khóa là mã + biến thể khi có khóa đó (DO-3a, VC-5dung), không thì mã. Mã phải đúng dạng của KICH_BAN mục 4
        (DO-1, VC-5): biến thể đưa vào --variant, để khóa dòng biên bản (mã, biến thể, lần, mức) nhất quán."""
        if CODE_RE.fullmatch(scenario):
            for key in ([scenario + variant] if variant else []) + [scenario]:
                if key in self.scenarios:
                    return self.scenarios[key]
        letters = re.match(r"[A-Za-z]*", scenario).group(0).upper()
        near = sorted(k for k in self.scenarios if k.startswith(scenario)) if scenario else []
        near = near or sorted(k for k in self.scenarios if k.startswith(letters + "-"))
        raise ScoreError(f"không có kịch bản {scenario + variant!r} trong {self.path.name} (mã dạng DO-1, biến thể ở "
                         f"--variant); các khóa {letters or scenario}: {', '.join(near) or '(không có)'}")


def _positive(value, name: str, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{where}: {name} phải là số hữu hạn > 0 (nhận {value!r})")
    return float(value)


def load_thresholds(path=DEFAULT_THRESHOLDS) -> Thresholds:
    """Đọc chặt configs/nguong_nghiem_thu.json: khóa lạ, mã kiểm lạ, số không hữu hạn hay ≤ 0 đều ném ValueError."""
    path = Path(path)
    where = f"Tệp ngưỡng {path}"
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"{where}: phải là object JSON")
    allowed = {"schema_version", "status", "notes", "reference_ratio", "analysis", "limits", "scenarios"}
    unknown = sorted(set(data) - allowed)
    missing = sorted(allowed - set(data) - {"notes"})
    if unknown or missing:
        raise ValueError(f"{where}: khóa lạ {unknown} / thiếu {missing}")
    if data["schema_version"] != 1:
        raise ValueError(f"{where}: schema_version {data['schema_version']!r} không hỗ trợ (cần 1)")
    if data["status"] not in THRESHOLD_STATUSES:
        raise ValueError(f"{where}: status phải là một trong {THRESHOLD_STATUSES}")
    analysis = data["analysis"]
    if not isinstance(analysis, dict):
        raise ValueError(f"{where}: analysis phải là object")
    unknown = sorted(set(analysis) - {f.name for f in fields(AnalysisParams)})
    if unknown:
        raise ValueError(f"{where}: analysis có khóa lạ {unknown}")
    params = AnalysisParams(**{k: _positive(v, f"analysis.{k}", where) for k, v in analysis.items()})
    if not isinstance(data["limits"], dict) or not isinstance(data["scenarios"], dict):
        raise ValueError(f"{where}: limits và scenarios phải là object")
    limits = {}
    for check, values in data["limits"].items():
        if check not in LIMIT_PARAMS:
            raise ValueError(f"{where}: limits có mã kiểm lạ {check!r}")
        required, optional = set(LIMIT_PARAMS[check]), set(LIMIT_OPTIONAL.get(check, ()))
        if not isinstance(values, dict) or not required <= set(values) <= required | optional:
            raise ValueError(f"{where}: limits.{check} phải có đúng các khóa {LIMIT_PARAMS[check]}"
                             + (f" (tùy chọn {LIMIT_OPTIONAL[check]})" if check in LIMIT_OPTIONAL else ""))
        limits[check] = {k: _positive(v, f"limits.{check}.{k}", where) for k, v in values.items()}
    scenarios = {}
    for key, entry in data["scenarios"].items():
        if not isinstance(entry, dict) or set(entry) - {"checks", "max_cusps", "notes"} or "checks" not in entry:
            raise ValueError(f"{where}: scenarios.{key} phải có 'checks' (và tùy chọn max_cusps, notes)")
        checks = entry["checks"]
        if not isinstance(checks, list) or any(c not in CHECK_IDS for c in checks):
            raise ValueError(f"{where}: scenarios.{key} có mã kiểm lạ {[c for c in checks if c not in CHECK_IDS]}")
        lacking = [c for c in checks if c in LIMIT_PARAMS and c not in limits]
        if lacking:
            raise ValueError(f"{where}: scenarios.{key} dùng {lacking} mà limits không có")
        cusps = entry.get("max_cusps")
        if cusps is not None and (isinstance(cusps, bool) or not isinstance(cusps, int) or cusps < 0):
            raise ValueError(f"{where}: scenarios.{key}.max_cusps phải là số nguyên ≥ 0 hoặc null")
        scenarios[key] = ScenarioRule(key, tuple(checks), cusps)
    return Thresholds(path, hashlib.sha256(raw).hexdigest(), data["status"], str(data.get("notes", "")),
                      _positive(data["reference_ratio"], "reference_ratio", where), params, limits, scenarios)


# ====================================================================== đọc log
@dataclass(frozen=True)
class LogEvent:
    t_session: float | None
    code: str
    source: str
    message: str
    detection: bool                # sự kiện dừng do phiên quyết định (ứng viên t_phát_hiện)
    origin: str                    # tệp chứa nó
    action: str = ""
    handling: str = ""
    t_io: float | None = None
    t_perf: float | None = None    # perf_counter lúc ghi dòng (T13); None ở log cũ
    derived: bool = False          # t_session suy từ t_io − t0 (dòng trước START không có t_session)


@dataclass(frozen=True)
class Detection:
    """t_phát_hiện: lúc phiên quyết định dừng lần đầu (NGUONG mục 3). `by_user`: lần dừng đầu do người (nút Dừng,
    Đặt lại), không phải do hệ thống phát hiện. `t_step`: t_session ghi ở dòng (thời gian bước của phiên); với bo thời
    gian thực `t_session` ở đây là t_io − t0 của dòng, lúc phiên thật sự quyết định (xem `_decision_time`)."""

    t_session: float
    code: str
    source: str
    exact: bool
    error_s: float
    origin: str
    note: str = ""
    by_user: bool = False
    t_step: float | None = None


@dataclass
class RunLogData:
    directory: Path
    kind: str                      # vehicle_io | sim_bundle
    mode: str
    evidence: str
    emulated: bool
    outcome: str | None
    reason: str
    t_end: float | None
    events: list[LogEvent]
    detection: Detection | None
    speed_series: list[tuple[float, float | None, float]]   # (t_session, v đo, v tham chiếu)
    planned_cusps: int | None
    plan_source: str
    runlog_path: Path | None
    runlog_rows: list[dict] | None
    files: dict[str, str]
    notes: list[str] = field(default_factory=list)           # ghi chú đưa vào ghi_chu của mọi dòng
    plan_note: str = ""                                       # vì sao chưa biết số lần đổi chiều đã lập (N-D6)
    runlog_note: str = ""                                     # vì sao không có RunLog (cần cho --sim-truth)
    io_simulated: bool | None = None
    pose_source: str | None = None
    port: str | None = None
    t_first_stop_cmd: float | None = None
    enable_after_stop: int | None = None
    commands_sent: int | None = None
    link_commands_sent: int | None = None
    t0_io: float | None = None
    t0_source: str = ""
    clock: dict | None = None
    t13: bool = False
    max_run_time: float | None = None
    injected_obstacles: list[Obstacle] = field(default_factory=list)
    package: Path | None = None    # gói export_run (T9) chứa thư mục log VehicleLink này (`<gói>/vehicle_io`)
    # N-V1 vế mục tiêu (02/10/2026): |tốc độ mục tiêu| lớn nhất của lệnh (lệnh đã gửi, NGUONG quy tắc 2) và nguồn; xe
    # của lần chạy (tên, max_speed_mps, nguồn, kích thước khi có run.json)
    max_target_mps: float | None = None
    target_source: str = ""
    run_vehicle: dict | None = None

    @property
    def sim_truth(self) -> bool:
        """Tư thế trong RunLog là tư thế THẬT của mô phỏng: gói SIM (evidence simulation_only), hoặc VehicleIO mô phỏng
        với SimTruthPose. Gói của lần chạy qua VehicleIO luôn được đọc thành kind vehicle_io (RunLog của nó là thế giới
        gương, tư thế lấy từ nguồn định vị), nên chỉ qua nhánh thứ hai. Thêm 02/10/2026: bo ảo QEMU với qemu_plant_pose
        (tư thế thật của xe mô phỏng phía laptop; `_check_log` chỉ nhận ở mức MP)."""
        if self.kind == "sim_bundle":
            return self.evidence == "simulation_only"
        return (self.evidence, self.pose_source) in SIM_TRUTH_SOURCES

    @property
    def ended(self) -> bool:
        """Log có kết quả cuối của lần chạy: False khi xuất lúc lần chạy chưa kết thúc (link.json result null, gói SIM
        state RUNNING/STOPPING)."""
        return self.outcome is not None and self.outcome not in NOT_ENDED_STATES

    @property
    def data_dir(self) -> Path:
        """Thư mục dữ liệu của lần chạy: gói T9 khi log VehicleLink nằm trong gói, không thì thư mục log."""
        return self.package if self.package is not None else self.directory

    @property
    def t0_real(self) -> float | None:
        """t0 của io khi bo chạy thời gian thực (thời điểm của dòng log lấy theo t_io, `_decision_time`); None khác."""
        return self.t0_io if self.kind == "vehicle_io" and self.io_simulated is False else None

    def summary(self) -> dict:
        return {"directory": str(self.directory), "package": str(self.package) if self.package else None,
                "kind": self.kind, "mode": self.mode, "evidence": self.evidence,
                "emulated": self.emulated, "io_simulated": self.io_simulated, "pose_source": self.pose_source,
                "port": self.port, "outcome": self.outcome, "ended": self.ended, "reason": self.reason,
                "t_end": self.t_end,
                "t13_format": self.t13, "t0_io": self.t0_io, "t0_source": self.t0_source, "clock": self.clock,
                "detection": asdict(self.detection) if self.detection else None,
                "t_first_stop_cmd": self.t_first_stop_cmd, "enable_after_stop": self.enable_after_stop,
                "commands_sent": self.commands_sent, "link_commands_sent": self.link_commands_sent,
                "planned_cusps": self.planned_cusps, "plan_source": self.plan_source,
                "plan_note": self.plan_note, "max_run_time": self.max_run_time,
                "runlog": str(self.runlog_path) if self.runlog_path else None, "runlog_note": self.runlog_note,
                "events": [asdict(e) for e in self.events],
                "injected_obstacles": [o.to_dict() for o in self.injected_obstacles], "notes": list(self.notes),
                "max_target_mps": self.max_target_mps, "target_source": self.target_source,
                "run_vehicle": self.run_vehicle}


def load_run_log(directory, runlog=None) -> RunLogData:
    """Đọc một lần chạy. Loại chọn theo nội dung:

    - có link.json → thư mục log VehicleLink: `<tên>_vehicle_io` của 'Xuất log CSV…', hoặc `<gói>/vehicle_io`;
    - gói export_run của lần chạy qua VehicleIO (T9: có vehicle_io/, manifest.json replay_kind vehicle_io_log, hay
      snapshot có khóa vehicle_link) → chấm như log VehicleIO từ vehicle_io/ của gói, RunLog là telemetry.csv của gói.
      Không bao giờ chấm như gói SIM: RunLog của gói đó là thế giới gương (tư thế từ nguồn định vị của lần chạy, không
      phải tư thế thật), nên --sim-truth, mức MP/XT và N-D6(c) phải xét theo link.json (NGUONG quy tắc 2);
    - có result.json và config_snapshot/run.json → gói SIM của export_run."""
    path = Path(directory)
    if not path.is_dir():
        raise ScoreError(f"--log {path}: không phải thư mục")
    try:
        if (path / "link.json").exists():
            return _load_vehicle_io(path, runlog, _package_of(path))
        why = _vehicle_io_package(path)
        if why:
            if not (path / PACKAGE_LOG_DIR / "link.json").exists():
                raise ScoreError(f"--log {path}: gói của lần chạy qua VehicleIO ({why}) nhưng thiếu "
                                 f"{PACKAGE_LOG_DIR}/link.json (log VehicleLink). Không chấm như gói SIM: RunLog của "
                                 f"gói là thế giới gương, không phải tư thế thật (NGUONG quy tắc 2)")
            return _load_vehicle_io(path / PACKAGE_LOG_DIR, runlog, path)
        if (path / "result.json").exists() and (path / "config_snapshot" / "run.json").exists():
            return _load_sim_bundle(path, runlog)
    except ScoreError:
        raise
    except (KeyError, ValueError, TypeError) as exc:
        raise ScoreError(f"log {path} hỏng hoặc khác định dạng: {exc!r}") from exc
    raise ScoreError(f"--log {path}: không nhận ra loại log. Cần thư mục <tên>_vehicle_io của 'Xuất log CSV…' "
                     f"(link.json, commands.csv, telemetry.csv, events.csv), gói export_run của lần chạy qua "
                     f"VehicleIO (vehicle_io/link.json) hoặc gói SIM (result.json, config_snapshot/run.json, "
                     f"telemetry.csv)")


def _vehicle_io_package(path: Path) -> str:
    """Vì sao `path` là gói export_run của lần chạy qua VehicleIO (T9, `storage/run_store.py`), hoặc '' (gói SIM, thư
    mục khác). Đủ một trong ba dấu hiệu, để gói thiếu một phần cũng không bị đọc thành gói SIM."""
    if (path / PACKAGE_LOG_DIR / "link.json").exists():
        return f"có {PACKAGE_LOG_DIR}/link.json"
    try:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        manifest = None
    if isinstance(manifest, dict) and manifest.get("replay_kind") == VEHICLE_IO_REPLAY_KIND:
        return f"manifest.json replay_kind {VEHICLE_IO_REPLAY_KIND}"
    if is_vehicle_io_package(path):
        return "config_snapshot/run.json có khóa vehicle_link"
    return ""


def _package_of(directory: Path) -> Path | None:
    """Gói T9 chứa thư mục log VehicleLink `directory` (`<gói>/vehicle_io`, gói có config_snapshot/run.json), hoặc
    None với thư mục `<tên>_vehicle_io` của 'Xuất log CSV…'."""
    parent = directory.parent
    if directory.name == PACKAGE_LOG_DIR and (parent / "config_snapshot" / "run.json").exists():
        return parent
    return None


def _decision_time(t_session: float | None, t_io: float | None, t0_real: float | None) -> float | None:
    """Thời điểm phiên quyết định, trên trục t_session. Bo thời gian thực (`t0_real` = t0 của io): t_io − t0 của
    dòng. Ở đó Session.advance chạy dồn mọi bước tới io.now() trong một lần gọi, nên dòng ghi thời gian BƯỚC
    (t_session) sớm hơn lúc quyết định thật (t_io = io.now() lúc ghi) tới một nhịp, cả quãng giao diện khựng.
    Bo mô phỏng, gói SIM (`t0_real` None): t_session của dòng."""
    if t0_real is not None and t_io is not None:
        return t_io - t0_real
    return t_session


def _first_detection(events: list[LogEvent], stop_step: float | None, stop_time: float | None, t13: bool,
                     reason: str, t0_real: float | None = None) -> Detection | None:
    """Sự kiện dừng sớm nhất. Chỉ coi là chính xác khi không muộn hơn dòng STOP đầu của commands.csv (so thời gian
    bước: `stop_step`); ngược lại (log cũ, phiên dừng vì sự kiện không được ghi) lấy dòng STOP đó, sai số ±20 ms.
    Thời điểm báo ra là lúc phiên quyết định (`_decision_time`): bo thời gian thực lấy t_io − t0 của dòng, dòng STOP
    thì `stop_time` (đã đổi như vậy)."""
    candidates = [e for e in events if e.detection and e.t_session is not None]
    first = min(candidates, key=lambda e: e.t_session) if candidates else None
    if first is not None and (stop_step is None or first.t_session <= stop_step + 1e-6):
        return Detection(_decision_time(first.t_session, first.t_io, t0_real), first.code, first.source, True, 0.0,
                         first.origin, by_user=first.code in USER_STOP_CODES or first.source == "user",
                         t_step=first.t_session)
    if stop_time is None:
        return None
    note = ("t_phát_hiện xấp xỉ bằng dòng STOP đầu của commands.csv (±20 ms), chưa có T13" if not t13 else
            "không có dòng session_stop trước dòng STOP đầu: t_phát_hiện xấp xỉ bằng dòng STOP (±20 ms)")
    if reason:
        note += f"; lý do dừng cuối (link.json): {reason}"
    return Detection(stop_time, "", "commands.csv", False, STOP_ROW_ERROR_S, "commands.csv", note,
                     by_user=reason == USER_STOP_REASON, t_step=stop_step)


def _snapshot_cusps(directory: Path, files: dict[str, str],
                    package: Path | None = None) -> tuple[int | None, float | None, str]:
    """run.json của lần chạy: trong thư mục log (gói SIM có sẵn), rồi config_snapshot/run.json của gói T9 chứa thư mục
    log VehicleLink (`<gói>/vehicle_io`). Thư mục `<tên>_vehicle_io` của 'Xuất log CSV…' không có run.json."""
    candidates = [(directory / "run.json", "run.json"),
                  (directory / "config_snapshot" / "run.json", "config_snapshot/run.json")]
    if package is not None:
        candidates.append((package / "config_snapshot" / "run.json", "config_snapshot/run.json của gói"))
    for candidate, label in candidates:
        if candidate.exists():
            snap = _read_json(candidate, files)
            segments = snap["trajectory"]["segments"]
            max_run = snap.get("max_run_time")
            return max(0, len(segments) - 1), (float(max_run) if max_run is not None else None), label
    return None, None, ""


def _number(value) -> float | None:
    """Số hữu hạn của JSON (không nhận bool hay chuỗi), không thì None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _max_abs(rows: list[dict], column: str, kind: str | None = None) -> float | None:
    """|giá trị| lớn nhất của một cột số (ô trống bỏ qua); `kind`: chỉ các dòng có cột kind bằng giá trị đó."""
    best = None
    for row in rows:
        if kind is not None and row.get("kind") != kind:
            continue
        value = _cell(row.get(column))
        if value is not None and (best is None or abs(value) > best):
            best = abs(value)
    return best


def _run_vehicle(directory: Path, files: dict[str, str], package: Path | None = None,
                 limits_check=None) -> dict | None:
    """Xe của lần chạy (N-V1, ghi chú kích thước; 02/10/2026): khóa "vehicle" của run.json (gói SIM, gói T9; có kích
    thước), không thì tên xe và max_speed phía planner trong limits_check của link.json (thư mục _vehicle_io của
    'Xuất log CSV…', không có kích thước). None khi không có cả hai."""
    candidates = [(directory / "run.json", "run.json"),
                  (directory / "config_snapshot" / "run.json", "config_snapshot/run.json")]
    if package is not None:
        candidates.append((package / "config_snapshot" / "run.json", "config_snapshot/run.json của gói"))
    for candidate, label in candidates:
        if candidate.exists():
            snap = _read_json(candidate, files)
            vehicle = snap.get("vehicle") if isinstance(snap, dict) else None
            if isinstance(vehicle, dict):
                out = {"name": str(vehicle.get("name", "?")), "max_speed_mps": _number(vehicle.get("max_speed_mps")),
                       "source": label}
                out.update({k: _number(vehicle[k]) for k in VEHICLE_GEOMETRY_KEYS
                            if _number(vehicle.get(k)) is not None})
                return out
            break
    if isinstance(limits_check, dict):
        speed = next((_number(row[2]) for row in limits_check.get("compared") or []
                      if isinstance(row, (list, tuple)) and len(row) == 3 and row[0] == "max_speed_mps"), None)
        return {"name": str(limits_check.get("vehicle_name") or "?"), "max_speed_mps": speed,
                "source": "link.json limits_check"}
    return None


def _load_vehicle_io(directory: Path, runlog, package: Path | None = None) -> RunLogData:
    files: dict[str, str] = {}
    info = _read_json(directory / "link.json", files)
    if not isinstance(info, dict):
        raise ScoreError(f"{directory / 'link.json'}: không phải object JSON")
    notes: list[str] = []
    result = info.get("result") if isinstance(info.get("result"), dict) else None
    if result is None:
        notes.append("log xuất khi lần chạy chưa kết thúc (link.json result rỗng)")
    clock = info.get("clock") if isinstance(info.get("clock"), dict) else None
    _, tel_rows = _read_csv(directory / "telemetry.csv", files)
    ev_header, ev_rows = _read_csv(directory / "events.csv", files)
    _, cmd_rows = _read_csv(directory / "commands.csv", files)
    t0_io, t0_source = None, ""
    if clock is not None and clock.get("t_io_at_start") is not None:
        t0_io, t0_source = float(clock["t_io_at_start"]), "link.json clock (T13)"
    else:
        diffs = [_cell(r["t_io"]) - _cell(r["t_session"]) for r in tel_rows
                 if _cell(r.get("t_io")) is not None and _cell(r.get("t_session")) is not None]
        if diffs:
            t0_io, t0_source = statistics.median(diffs), "trung vị t_io − t_session của telemetry.csv"
    io_simulated = info.get("io_simulated") if isinstance(info.get("io_simulated"), bool) else None
    t0_real = t0_io if io_simulated is False else None      # bo thời gian thực: lúc quyết định theo t_io
    t13 = "t_perf" in ev_header or clock is not None
    events = []
    for row in ev_rows:
        t_io, t_session, derived = _cell(row.get("t_io")), _cell(row.get("t_session")), False
        if t_session is None and t_io is not None and t0_io is not None:
            t_session, derived = t_io - t0_io, True
        handling, action = (row.get("handling") or "").strip(), (row.get("action") or "").strip()
        # T13: chỉ dòng session_stop + STOP là quyết định dừng của phiên (sự kiện bo/lớp nối có cả dòng "stop" lúc
        # nhận). Log cũ: dòng "stop" là các sự kiện dừng duy nhất có mã.
        detection = (handling == SESSION_STOP and action == "STOP") if t13 else handling == "stop"
        events.append(LogEvent(t_session, row.get("code") or "", row.get("source") or "", row.get("message") or "",
                               detection, "events.csv", action, handling, t_io, _cell(row.get("t_perf")), derived))
    stop_index = next((i for i, r in enumerate(cmd_rows) if r.get("kind") == "STOP"), None)
    t_stop_step = _cell(cmd_rows[stop_index]["t_session"]) if stop_index is not None else None
    t_first_stop = None if stop_index is None else _decision_time(
        t_stop_step, _cell(cmd_rows[stop_index].get("t_io")), t0_real)
    enable_after = None if stop_index is None else sum(
        1 for r in cmd_rows[stop_index + 1:] if r.get("kind") == "TRACK" and r.get("sent") == "1")
    speed_series = []
    for row in tel_rows:
        t = _cell(row.get("t_session"))
        if t is not None and t >= 0:
            speed_series.append((t, _cell(row.get("speed_mps")), _cell(row.get("speed_ref_mps")) or 0.0))
    planned, max_run, plan_source = _snapshot_cusps(directory, files, package)
    plan_note = ""
    if planned is None:
        done = [r for r in cmd_rows if r.get("kind") == "TRACK" and r.get("done") == "1"]
        segments = [int(r["segment"]) for r in cmd_rows if r.get("kind") == "TRACK" and (r.get("segment") or "")]
        if done and segments:
            planned, plan_source = max(segments), "commands.csv (đoạn cuối khi done = 1)"
        else:
            plan_note = ("chưa biết số lần đổi chiều đã lập: đường chưa đi hết (không có done = 1) và thư mục log "
                         "không có run.json")
    port = info.get("port")
    evidence = str(info.get("evidence", "?"))
    reason = str(result.get("reason", "")) if result else ""
    runlog_path = None
    if runlog:
        runlog_path = Path(runlog)
        if not runlog_path.exists():
            raise ScoreError(f"--runlog {runlog_path}: không có tệp")
    elif package is not None:
        runlog_path = package / "telemetry.csv"                # RunLog của gói T9
    elif directory.name.endswith(VEHICLE_IO_SUFFIX):
        runlog_path = directory.with_name(directory.name[:-len(VEHICLE_IO_SUFFIX)] + ".csv")
    runlog_rows, runlog_note = None, ""
    if runlog_path is not None and runlog_path.exists():
        _, runlog_rows = _read_csv(runlog_path, files)
    else:
        name = runlog_path.name if runlog_path is not None else "<tên>.csv (tên thư mục không có hậu tố _vehicle_io)"
        runlog_note = f"không thấy RunLog {name} cạnh thư mục log: dùng --runlog"
        runlog_path = None
    max_target = _max_abs(cmd_rows, "target_speed_mps", "TRACK")          # N-V1 vế mục tiêu: lệnh bám đường
    return RunLogData(
        directory=directory, kind="vehicle_io", mode=str(info.get("mode", "?")), evidence=evidence,
        emulated=evidence in EMULATED_EVIDENCE or (isinstance(port, str) and port.startswith(EMULATED_PORT_PREFIXES)),
        outcome=str(result["outcome"]) if result else None, reason=reason,
        t_end=float(result["t_session"]) if result else None, events=events,
        detection=_first_detection(events, t_stop_step, t_first_stop, t13, reason, t0_real), speed_series=speed_series,
        planned_cusps=planned, plan_source=plan_source, runlog_path=runlog_path, runlog_rows=runlog_rows,
        files=files, notes=notes, plan_note=plan_note, runlog_note=runlog_note, io_simulated=io_simulated,
        pose_source=info.get("pose_source"), port=port if isinstance(port, str) else None,
        t_first_stop_cmd=t_first_stop, enable_after_stop=enable_after,
        commands_sent=sum(1 for r in cmd_rows if r.get("sent") == "1"),
        link_commands_sent=int(result["commands_sent"]) if result and result.get("commands_sent") is not None
        else None,
        t0_io=t0_io, t0_source=t0_source, clock=clock, t13=t13, max_run_time=max_run, package=package,
        max_target_mps=max_target, target_source="commands.csv (kind TRACK)" if max_target is not None else "",
        run_vehicle=_run_vehicle(directory, files, package, info.get("limits_check")))


def _load_sim_bundle(directory: Path, runlog) -> RunLogData:
    """Gói SIM của export_run (snapshot không có vehicle_link: `load_run_log` đã tách gói của lần chạy qua VehicleIO).
    Bằng chứng lấy từ manifest.json; `sim_truth` chỉ đúng khi bằng chứng là simulation_only."""
    files: dict[str, str] = {}
    notes: list[str] = []
    result = _read_json(directory / "result.json", files)
    snap = _read_json(directory / "config_snapshot" / "run.json", files)
    if (directory / "manifest.json").exists():
        evidence = str(_read_json(directory / "manifest.json", files).get("evidence", "?"))
    else:
        evidence = "simulation_only"            # nhánh SIM chỉ có mô phỏng (snapshot không có vehicle_link)
        notes.append("gói SIM thiếu manifest.json")
    if str(result["state"]) in NOT_ENDED_STATES:
        notes.append(f"log xuất khi lần chạy chưa kết thúc (result.json state {result['state']})")
    events: list[LogEvent] = []
    if (directory / "safety_events.json").exists():
        for item in _read_json(directory / "safety_events.json", files):
            stamp = item["stamp"]
            action = str(item.get("action", "STOP"))
            events.append(LogEvent(float(stamp["t"]), str(item["code"]), str(stamp["source_id"]),
                                   str(item.get("message", "")), action == "STOP", "safety_events.json", action))
    injected: list[Obstacle] = []
    jsonl = directory / "events.jsonl"
    if jsonl.exists():
        files[str(jsonl)] = _sha256(jsonl)
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            kind = str(item["kind"])
            message = str(item.get("reason") or (item.get("obstacle") or {}).get("id", ""))
            events.append(LogEvent(float(item["t"]), kind, "run_events", message, kind == "stop", "events.jsonl"))
            if kind == "obstacle":
                injected.append(Obstacle.from_dict(item["obstacle"]))
    detection = None
    stops = [e for e in events if e.detection]
    if stops:
        first = min(stops, key=lambda e: e.t_session)
        detection = Detection(first.t_session, first.code, first.source, True, 0.0, first.origin,
                              by_user=first.code == "stop" and first.message == USER_STOP_REASON)
    runlog_path = Path(runlog) if runlog else directory / "telemetry.csv"
    _, rows = _read_csv(runlog_path, files)
    speed_series = [(float(r["t"]), _cell(r.get("speed")), _cell(r.get("target_speed")) or 0.0) for r in rows]
    enable_after = None
    if detection is not None:
        enable_after = sum(1 for r in rows if float(r["t"]) > detection.t_session + STOP_ROW_ERROR_S
                           and abs(float(r["target_speed"])) > 1e-9)
    planned, max_run, plan_source = _snapshot_cusps(directory, files)
    max_target = _max_abs(rows, "target_speed")                           # N-V1 vế mục tiêu: cột của RunLog
    return RunLogData(                          # nhánh SIM không có bo: luôn là giả lập (không bao giờ đủ cho mức XT)
        directory=directory, kind="sim_bundle", mode="SIM", evidence=evidence, emulated=True,
        outcome=str(result["state"]), reason=str(result.get("reason") or ""),
        t_end=int(result["steps"]) * float(snap["physics_dt"]), events=events, detection=detection,
        speed_series=speed_series, planned_cusps=planned, plan_source=plan_source, runlog_path=runlog_path,
        runlog_rows=rows, files=files, notes=notes, enable_after_stop=enable_after, max_run_time=max_run,
        injected_obstacles=injected, max_target_mps=max_target,
        target_source=f"{runlog_path.name} (target_speed)" if max_target is not None else "",
        run_vehicle=_run_vehicle(directory, files))


# ====================================================================== dấu đồng bộ T14 và đồng hồ perf_counter
@dataclass(frozen=True)
class SyncMarkRow:
    kind: str
    n: int | None
    t_perf: float
    state: str
    t_session: float | None
    t_io: float | None
    io_clock: str
    note: str
    time_scale: float | None = None     # giây phiên mỗi giây thật ("tốc độ chạy" của giao diện); None: tệp cũ, ô trống


@dataclass
class SyncMarks:
    path: Path
    rows: list[SyncMarkRow]
    sha256: str

    def mark(self, n: int) -> SyncMarkRow:
        for row in self.rows:
            if row.kind == SYNC_MARK and row.n == n:
                return row
        known = [row.n for row in self.rows if row.kind == SYNC_MARK]
        raise ScoreError(f"tệp dấu đồng bộ {self.path} không có dấu #{n} (có: {known or 'không dấu nào'})")


def read_sync_marks_csv(path) -> SyncMarks:
    """Đọc tệp dấu đồng bộ T14 theo tên cột (chỉ cần kind, n, t_perf, state, t_session, t_io, io_clock, note), không
    phụ thuộc mã của T14. Cột `time_scale` (giây phiên mỗi giây thật, tốc độ chạy của giao diện) là tùy chọn: tệp cũ
    không có thì `build_perf_map` giả định 1× và ghi lại giả định đó."""
    path = Path(path)
    files: dict[str, str] = {}
    header, rows = _read_csv(path, files)
    missing = [c for c in ("kind", "n", "t_perf", "state", "t_session", "t_io", "io_clock") if c not in header]
    if missing:
        raise ScoreError(f"tệp dấu đồng bộ {path}: thiếu cột {', '.join(missing)}")
    out = []
    try:
        for row in rows:
            kind = (row.get("kind") or "").strip()
            t_perf = _cell(row.get("t_perf"))
            if kind not in (SYNC_MARK, CLOCK_ROW) or t_perf is None:
                continue
            n = (row.get("n") or "").strip()
            scale = _cell(row.get("time_scale"))
            if scale is not None and scale <= 0:
                raise ValueError(f"time_scale phải > 0 (nhận {scale:g})")
            out.append(SyncMarkRow(kind, int(n) if n else None, t_perf, (row.get("state") or "").strip(),
                                   _cell(row.get("t_session")), _cell(row.get("t_io")),
                                   (row.get("io_clock") or "").strip(), row.get("note") or "", scale))
    except ValueError as exc:
        raise ScoreError(f"tệp dấu đồng bộ {path}: {exc}") from exc
    return SyncMarks(path, out, files[str(path)])


def find_sync_marks(log_dir: Path) -> Path | None:
    """Tệp `<tên>_sync_marks.csv` mà 'Xuất log CSV…' của T14 ghi cạnh `<tên>.csv`, đoán từ tên thư mục log:
    `<tên>_vehicle_io`, gói `<tên>_<YYYYmmdd_HHMMSS_micro>` (SIM hay T9), hoặc `<gói>/vehicle_io` (tên lấy từ gói)."""
    if _package_of(log_dir) is not None:
        log_dir = log_dir.parent
    name = log_dir.name
    if name.endswith(VEHICLE_IO_SUFFIX):
        stem = name[:-len(VEHICLE_IO_SUFFIX)]
    else:
        stem = SIM_BUNDLE_SUFFIX_RE.sub("", name)
    candidate = log_dir.with_name(stem + SYNC_MARKS_SUFFIX)
    return candidate if candidate.exists() else None


def _clock_rows_of_run(marks: SyncMarks, t_end: float | None) -> tuple[list[SyncMarkRow], str]:
    """Các dòng CLOCK của đúng lần chạy đang chấm. Một tệp T14 có thể chứa nhiều lần chạy: tách ở mỗi dòng RUNNING
    (bắt đầu lần chạy) và chọn lần có dòng kết thúc trùng t_end của log."""
    runs: list[list[SyncMarkRow]] = []
    previous = ""
    for row in marks.rows:
        if row.kind != CLOCK_ROW or row.state not in RUN_STATES:
            continue
        if row.state == "RUNNING" or not runs or previous in END_STATES:
            runs.append([])
        runs[-1].append(row)
        previous = row.state
    if t_end is None:
        return [], "log không có t_end: không chọn được lần chạy trong tệp dấu đồng bộ"
    matching = [run for run in runs if any(r.state in END_STATES and r.t_session is not None
                                           and abs(r.t_session - t_end) <= 0.05 for r in run)]
    if not matching:
        return [], f"tệp dấu đồng bộ không có dòng CLOCK kết thúc ở t_session ≈ {t_end:.2f} s"
    return matching[-1], ""


@dataclass(frozen=True)
class PerfMap:
    """Đổi perf_counter thô của laptop sang t_session của lần chạy.

    - Chính xác (`offset`): bo chạy thời gian thực có khóa `clock` của link.json (T13): t_session = t_perf −
      t_perf_at_start, vì t_io = perf_counter − hằng số (SerialVehicleIO). Thời gian phiên bám io.now(), không theo
      tốc độ chạy của giao diện, nên hệ số luôn là 1.
    - Theo mốc (`anchors`): khi thời gian phiên là thời gian mô phỏng (gói SIM, bo mô phỏng), lấy dòng mốc gần nhất
      (dòng events.csv có cả t_perf và t_session của T13; dòng CLOCK của T14):
      t_session ≈ mốc.t_session + k·(t_perf − mốc.t_perf), k = `scale` = giây phiên mỗi giây thật (cột time_scale
      của T14, tức tốc độ chạy 0,1–8× của giao diện; tệp cũ: giả định 1). Sai số = k·(clock_anchor_error_s +
      clock_drift·|khoảng tới mốc|): một nhịp giao diện và độ trôi đều tính theo giây thật."""

    source: str
    offset: float | None = None
    anchors: tuple[tuple[float, float, str], ...] = ()
    anchor_error_s: float = 0.0
    drift: float = 0.0
    scale: float = 1.0
    scale_source: str = ""
    fitted_scale: float | None = None      # hệ số khớp từ chính các mốc (chỉ để kiểm `scale`)

    @property
    def exact(self) -> bool:
        return self.offset is not None

    def to_session(self, t_perf: float) -> tuple[float, float]:
        """→ (t_session, sai số s)."""
        if self.offset is not None:
            return t_perf - self.offset, 0.0
        anchor = min(self.anchors, key=lambda a: abs(a[0] - t_perf))
        gap = t_perf - anchor[0]
        return anchor[1] + self.scale * gap, self.scale * (self.anchor_error_s + self.drift * abs(gap))

    def summary(self) -> dict:
        return {"source": self.source, "offset": self.offset, "anchors": [list(a) for a in self.anchors],
                "anchor_error_s": self.anchor_error_s, "drift": self.drift, "scale": self.scale,
                "scale_source": self.scale_source, "fitted_scale": self.fitted_scale}


def _anchor_slope(anchors: list[tuple[float, float, str]]) -> tuple[float, float] | None:
    """Hệ số Δt_session/Δt_perf khớp bình phương nhỏ nhất qua các mốc, kèm khoảng perf_counter mà chúng trải;
    None khi chưa đủ hai mốc ở hai thời điểm perf_counter khác nhau."""
    xs, ys = [a[0] for a in anchors], [a[1] for a in anchors]
    span = max(xs) - min(xs) if xs else 0.0
    if len(xs) < 2 or span < 1e-6:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx, span


def build_perf_map(log: RunLogData | None, marks: SyncMarks | None,
                   params: AnalysisParams) -> tuple[PerfMap | None, list[str]]:
    """Ánh xạ perf_counter → t_session của lần chạy, hoặc (None, lý do). Theo mốc: hệ số là time_scale của các dòng
    CLOCK của lần chạy (T14); không có thì giả định 1× và ghi giả định vào `scale_source` (tệp chi tiết). Hệ số khớp
    từ chính các mốc phải khớp hệ số đó trong clock_drift + 2·clock_anchor_error_s/khoảng mốc; lệch hơn (tốc độ chạy
    khác mà tệp không ghi, đổi giữa lần chạy, giao diện khựng lâu) thì từ chối, không đổi bằng một hệ số sai."""
    notes: list[str] = []
    if log is None:
        return None, notes
    if log.kind == "vehicle_io" and log.io_simulated is False and log.clock \
            and log.clock.get("t_perf_at_start") is not None:
        return PerfMap("link.json clock (T13): t_session = t_perf − t_perf_at_start, bo chạy thời gian thực",
                       offset=float(log.clock["t_perf_at_start"]),
                       scale_source="bo thời gian thực: thời gian phiên bám io.now(), không theo tốc độ chạy"), notes
    anchors = [(e.t_perf, e.t_session, f"events.csv {e.code}") for e in log.events
               if e.t_perf is not None and e.t_session is not None and not e.derived
               and e.handling in ("stop", "log", SESSION_STOP)]
    rows: list[SyncMarkRow] = []
    if marks is not None:
        rows, note = _clock_rows_of_run(marks, log.t_end)
        if note:
            notes.append(note)
        anchors += [(r.t_perf, r.t_session, f"CLOCK {r.note}".strip()) for r in rows if r.t_session is not None]
    if not anchors:
        return None, notes
    scales = sorted({r.time_scale for r in rows if r.time_scale is not None})
    if len(scales) > 1:
        notes.append(f"tốc độ chạy đổi trong lần chạy: time_scale {', '.join(f'{s:g}' for s in scales)} ở các dòng "
                     f"CLOCK")
        return None, notes
    if scales:
        scale, scale_source = scales[0], "time_scale của dòng CLOCK của lần chạy, tức tốc độ chạy của giao diện"
    else:
        scale = 1.0
        scale_source = ("giả định 1×: dòng CLOCK của lần chạy không có time_scale, tệp dấu đồng bộ cũ" if rows else
                        "giả định 1×: không có dòng CLOCK của lần chạy ghi time_scale")
    anchors.sort()
    fit = _anchor_slope(anchors)
    if fit is not None:
        slope, span = fit
        tolerance = params.clock_drift + 2 * params.clock_anchor_error_s / span
        if abs(slope / scale - 1.0) > tolerance:
            notes.append(f"các mốc perf_counter–t_session của lần chạy cho {slope:.3f} s phiên mỗi giây thật, lệch hệ "
                         f"số {scale:g}× ({scale_source}) quá {tolerance:.1%}: tốc độ chạy khác hay giao diện khựng "
                         f"lâu")
            return None, notes
    return PerfMap("mốc perf_counter–t_session gần nhất (dòng events.csv của T13, dòng CLOCK của T14)",
                   anchors=tuple(anchors), anchor_error_s=params.clock_anchor_error_s, drift=params.clock_drift,
                   scale=scale, scale_source=scale_source,
                   fitted_scale=fit[0] if fit is not None else None), notes


# ====================================================================== phân tích tham chiếu
@dataclass
class TrackAnalysis:
    method: str
    t: list[float]
    raw: list[tuple[float, float, float]]        # (x, y, hướng rad) của mẫu hợp lệ trong cửa sổ
    smooth: list[tuple[float, float, float]]     # đã làm trơn (MP: bằng raw)
    kept: list[int]                              # chỉ số trong smooth của các điểm quãng đã tỉa
    kept_s: list[float]                          # quãng tích lũy tại các điểm đó
    final_pose: Pose | None
    final_spread_m: float | None
    frame_period_s: float | None
    moving_gap: tuple[float, float, float] | None
    two_marker_fraction: float | None
    max_residual_m: float | None
    notes: list[str] = field(default_factory=list)

    @property
    def length_m(self) -> float:
        return self.kept_s[-1] if self.kept_s else 0.0


def _smooth(t: list[float], raw: list[tuple[float, float, float]], half: float) -> list[tuple[float, float, float]]:
    """Trung bình trượt có tâm ±half giây; hướng được mở cuộn trước khi lấy trung bình."""
    n = len(t)
    yaws = [raw[0][2]]
    for i in range(1, n):
        yaws.append(yaws[-1] + wrap_angle(raw[i][2] - raw[i - 1][2]))
    cx = list(accumulate((p[0] for p in raw), initial=0.0))
    cy = list(accumulate((p[1] for p in raw), initial=0.0))
    cw = list(accumulate(yaws, initial=0.0))
    out, lo, hi = [], 0, 0
    for i in range(n):
        while t[lo] < t[i] - half - 1e-9:
            lo += 1
        hi = max(hi, i)
        while hi + 1 < n and t[hi + 1] <= t[i] + half + 1e-9:
            hi += 1
        k = hi - lo + 1
        out.append(((cx[hi + 1] - cx[lo]) / k, (cy[hi + 1] - cy[lo]) / k, wrap_angle((cw[hi + 1] - cw[lo]) / k)))
    return out


def _decimate(smooth: list[tuple[float, float, float]], step: float) -> tuple[list[int], list[float]]:
    """Giữ một điểm khi nó cách điểm giữ trước ≥ step: nhiễu lúc đứng yên không cộng dồn vào quãng."""
    kept, s = [0], [0.0]
    for i in range(1, len(smooth)):
        x0, y0, _ = smooth[kept[-1]]
        d = math.hypot(smooth[i][0] - x0, smooth[i][1] - y0)
        if d >= step:
            kept.append(i)
            s.append(s[-1] + d)
    return kept, s


def _final_pose(t, raw, smooth, params: AnalysisParams) -> tuple[Pose | None, float | None, str]:
    """Trung vị từng trục của mẫu THÔ trong final_window_s cuối; chỉ nhận khi mọi vị trí đã làm trơn trong cửa sổ cách
    nó ≤ standstill_radius_m."""
    first = bisect.bisect_left(t, t[-1] - params.final_window_s - 1e-9)
    idx = range(first, len(t))
    if t[-1] - t[first] < 0.9 * params.final_window_s:
        return None, None, (f"tham chiếu có ít hơn {params.final_window_s:g} s dữ liệu ở cuối: chưa có tư thế cuối")
    yaw_last = raw[-1][2]
    pose = Pose(statistics.median(raw[i][0] for i in idx), statistics.median(raw[i][1] for i in idx),
                wrap_angle(yaw_last + statistics.median(wrap_angle(raw[i][2] - yaw_last) for i in idx)))
    spread = max(math.hypot(raw[i][0] - pose.x, raw[i][1] - pose.y) for i in idx)
    moving = max(math.hypot(smooth[i][0] - pose.x, smooth[i][1] - pose.y) for i in idx)
    if moving > params.standstill_radius_m:
        return None, spread, (f"xe chưa đứng yên trong {params.final_window_s:g} s cuối của tham chiếu "
                              f"(dịch {moving * 100:.1f} cm): chưa có tư thế cuối")
    return pose, spread, ""


def analyse_reference(track: ReferenceTrack, params: AnalysisParams,
                      window: tuple[float, float] | None = None) -> TrackAnalysis:
    samples = [s for s in track.valid_samples if window is None or window[0] <= s.t <= window[1]]
    if not samples:
        raise ScoreError("không còn mẫu tham chiếu hợp lệ nào (kiểm --ref-window)")
    t = [s.t for s in samples]
    raw = [(s.pose.x, s.pose.y, s.pose.yaw) for s in samples]
    method = track.meta.method
    smooth = raw if method == "MP" or len(t) < 3 else _smooth(t, raw, params.smooth_s / 2)
    kept, kept_s = _decimate(smooth, params.path_step_m)
    notes = []
    if method == "R2":
        final, spread, note = Pose(*raw[-1]), 0.0, ""
    else:
        final, spread, note = _final_pose(t, raw, smooth, params)
    if note:
        notes.append(note)
    gap = None
    for i in range(1, len(t)):
        moved = math.hypot(raw[i][0] - raw[i - 1][0], raw[i][1] - raw[i - 1][1])
        if t[i] - t[i - 1] > params.max_gap_s and moved >= params.standstill_radius_m:
            gap = (t[i - 1], t[i], moved)
            notes.append(f"tham chiếu mất {t[i] - t[i - 1]:.2f} s dữ liệu ({t[i - 1]:.2f}–{t[i]:.2f} s) khi xe dịch "
                         f"{moved * 100:.1f} cm")
            break
    markers = [s.n_markers for s in samples if s.n_markers is not None]
    residuals = [s.residual_m for s in samples if s.residual_m is not None]
    return TrackAnalysis(
        method, t, raw, smooth, kept, kept_s, final, spread,
        statistics.median(b - a for a, b in zip(t, t[1:])) if len(t) >= 2 else None, gap,
        sum(1 for m in markers if m == 2) / len(markers) if markers else None,
        max(residuals) if residuals else None, notes)


def _position_at(an: TrackAnalysis, t: float) -> tuple[float, float]:
    """Vị trí đã làm trơn tại t (nội suy tuyến tính, kẹp ở hai đầu)."""
    ts = an.t
    if t <= ts[0]:
        return an.smooth[0][0], an.smooth[0][1]
    if t >= ts[-1]:
        return an.smooth[-1][0], an.smooth[-1][1]
    j = bisect.bisect_right(ts, t)
    a, b = an.smooth[j - 1], an.smooth[j]
    u = (t - ts[j - 1]) / (ts[j] - ts[j - 1])
    return a[0] + u * (b[0] - a[0]), a[1] + u * (b[1] - a[1])


def _s_at(an: TrackAnalysis, t: float) -> float:
    """s(t) = s(điểm giữ cuối ≤ t) + dây cung tới vị trí đã làm trơn tại t."""
    kept_t = [an.t[k] for k in an.kept]
    j = max(0, bisect.bisect_right(kept_t, t) - 1)
    x, y = _position_at(an, t)
    kx, ky, _ = an.smooth[an.kept[j]]
    return an.kept_s[j] + math.hypot(x - kx, y - ky)


def distance_along(an: TrackAnalysis, t_a: float, t_b: float) -> float:
    """Quãng đi được theo tham chiếu giữa hai thời điểm (đồng hồ tham chiếu)."""
    return _s_at(an, t_b) - _s_at(an, t_a)


def speed_at(an: TrackAnalysis, t: float, half: float = SPEED_HALF_WINDOW_S) -> float:
    a, b = max(an.t[0], t - half), min(an.t[-1], t + half)
    return distance_along(an, a, b) / (b - a) if b > a else 0.0


def max_speed(an: TrackAnalysis, window_m: float) -> tuple[float, float, float] | None:
    """Tốc độ trung bình lớn nhất trên một đoạn ≥ window_m: với mỗi điểm giữ, lấy điểm giữ đầu tiên phía sau có
    Δs ≥ window_m. Trả (v, Δt, t đầu đoạn) hoặc None khi cả quãng ngắn hơn window_m."""
    ts = [an.t[k] for k in an.kept]
    ss = an.kept_s
    best, j = None, 0
    for i in range(len(ts)):
        j = max(j, i + 1)
        while j < len(ts) and ss[j] - ss[i] < window_m:
            j += 1
        if j >= len(ts):
            break
        dt = ts[j] - ts[i]
        if dt > 0 and (best is None or (ss[j] - ss[i]) / dt > best[0]):
            best = ((ss[j] - ss[i]) / dt, dt, ts[i])
    return best


def first_standstill(an: TrackAnalysis, t_from: float,
                     params: AnalysisParams) -> tuple[float, float, tuple[float, float]] | None:
    """Lần đứng yên đầu tiên từ t_from: cửa sổ [t_k, t_k + standstill_min_s] nằm trọn trong dữ liệu và mọi vị trí đã
    làm trơn trong đó cách trung vị P ≤ standstill_radius_m. Trả (t_đứng_yên, t_k + standstill_min_s, P) với
    t_đứng_yên = mẫu đầu từ t_from cách P ≤ settle_m; None khi tham chiếu hết trước đó."""
    ts, sm = an.t, an.smooth
    start = bisect.bisect_left(ts, t_from - 1e-9)
    for k in range(start, len(ts)):
        t_end = ts[k] + params.standstill_min_s
        if t_end > ts[-1] + 1e-9:
            return None
        hi = bisect.bisect_right(ts, t_end + 1e-9)
        px = statistics.median(sm[i][0] for i in range(k, hi))
        py = statistics.median(sm[i][1] for i in range(k, hi))
        if all(math.hypot(sm[i][0] - px, sm[i][1] - py) <= params.standstill_radius_m for i in range(k, hi)):
            settle = next((i for i in range(start, hi)
                           if math.hypot(sm[i][0] - px, sm[i][1] - py) <= params.settle_m), k)
            return ts[settle], t_end, (px, py)
    return None


def moved_after(an: TrackAnalysis, t_end: float, point: tuple[float, float]) -> float:
    """Khoảng cách lớn nhất từ point tới mọi vị trí đã làm trơn sau t_end."""
    start = bisect.bisect_right(an.t, t_end)
    return max((math.hypot(x - point[0], y - point[1]) for x, y, _ in an.smooth[start:]), default=0.0)


def reversals_on_reference(an: TrackAnalysis, hysteresis: float) -> int:
    """Đếm đổi chiều: chiếu dây cung giữa hai điểm giữ liên tiếp lên hướng xe; chỉ tính một lần đổi khi đã đi ≥
    hysteresis theo chiều ngược."""
    count, direction, pending, opposite = 0, 0, 0.0, 0.0
    for a, b in zip(an.kept, an.kept[1:]):
        xa, ya, yaw_a = an.smooth[a]
        xb, yb, yaw_b = an.smooth[b]
        yaw = yaw_a + wrap_angle(yaw_b - yaw_a) / 2
        v = (xb - xa) * math.cos(yaw) + (yb - ya) * math.sin(yaw)
        if direction == 0:
            pending += v
            if abs(pending) >= hysteresis:
                direction = 1 if pending > 0 else -1
            continue
        if v * direction >= 0:
            opposite = 0.0
            continue
        opposite += abs(v)
        if opposite >= hysteresis:
            count += 1
            direction, opposite = -direction, 0.0
    return count


def min_clearance(an: TrackAnalysis, cfg: VehicleConfig,
                  obstacles: list[Obstacle]) -> tuple[float, str | None, float | None]:
    """Khoảng hở nhỏ nhất thân xe – vật trên mọi mẫu đã làm trơn (MP: mẫu thô): (m, id vật, t)."""
    best = (math.inf, None, None)
    polygons = [(o.id, obstacle_polygon(o)) for o in obstacles]
    for t, (x, y, yaw) in zip(an.t, an.smooth):
        body = body_polygon(cfg, Pose(x, y, yaw))
        for oid, poly in polygons:
            d = body.distance(poly)
            if d < best[0]:
                best = (d, oid, t)
    return best


def border_clearance(an: TrackAnalysis, cfg: VehicleConfig, layout: Scenario) -> float:
    """Khoảng hở nhỏ nhất tới mép sa bàn (chỉ ghi vào tệp chi tiết, N-D5 không tính mép)."""
    area = bounds_polygon(layout.bounds)
    best = math.inf
    for x, y, yaw in an.smooth:
        body = body_polygon(cfg, Pose(x, y, yaw))
        best = min(best, body.distance(area.exterior) if area.contains(body) else 0.0)
    return best


def slot_margin(cfg: VehicleConfig, pose: Pose, slot: ParkingSlot) -> float:
    """Lề nhỏ nhất từ góc thân xe tới vạch ô khi cả bốn góc trong ô; ngược lại là −(góc ra ngoài xa nhất)."""
    poly = Polygon(slot.corners())
    corners = [Point(c) for c in body_corners(cfg, pose)]
    outside = [poly.distance(p) for p in corners if not poly.covers(p)]
    if outside:
        return -max(outside)
    return min(poly.exterior.distance(p) for p in corners)


def footprint_reach(cfg: VehicleConfig) -> float:
    """Khoảng cách lớn nhất từ tâm trục sau tới một góc thân xe (cánh tay đòn của sai số hướng)."""
    return max(math.hypot(x, y) for x, y in body_corners(cfg, Pose(0.0, 0.0, 0.0)))


def footprint_error(cfg: VehicleConfig, pos_e: float | None, yaw_e_rad: float | None) -> float | None:
    """Sai số vị trí của góc thân xe: pos_e + tầm·sin(yaw_e) (None khi chưa biết độ chính xác)."""
    if pos_e is None or yaw_e_rad is None:
        return None
    return pos_e + footprint_reach(cfg) * math.sin(yaw_e_rad)


# ====================================================================== đồng hồ và mốc sự kiện
@dataclass(frozen=True)
class ClockMap:
    """t_session = scale·t_ref + offset. `time_scale`: giây phiên mỗi giây thật của phép đổi perf_counter → t_session
    mà các cặp đồng bộ đã đi qua (None khi không cặp nào qua perf_counter)."""

    scale: float
    offset: float
    source: str
    residual_s: float = 0.0
    identity: bool = False
    time_scale: float | None = None

    def to_session(self, t_ref: float) -> float:
        return self.scale * t_ref + self.offset

    def to_ref(self, t_session: float) -> float:
        return (t_session - self.offset) / self.scale

    def summary(self) -> dict:
        return {"scale": self.scale, "offset": self.offset, "drift": self.scale - 1.0, "source": self.source,
                "residual_s": self.residual_s, "identity": self.identity, "time_scale": self.time_scale}


@dataclass(frozen=True)
class ResolvedPair:
    t_ref: float
    t_session: float
    spec: str
    side: str                      # session | io | perf | mark
    error_s: float                 # sai số phía log (đổi perf_counter → t_session)


def parse_sync_side(text: str) -> tuple[float, str]:
    """Phía log của một cặp --sync: `<s>` hoặc `session:<s>`, `io:<t_io>`, `perf:<t_perf>`, `mark:<n>`."""
    kind, sep, value = text.strip().partition(":")
    if not sep:
        kind, value = "session", text
    if kind not in ("session", "io", "perf", "mark"):
        raise ValueError(f"phía log {text!r}: cần <s>, session:<s>, io:<s>, perf:<s> hoặc mark:<n>")
    if kind == "mark":
        n = int(value)
        if n < 1:
            raise ValueError("mark:<n> cần n ≥ 1")
        return float(n), kind
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{text!r} không hữu hạn")
    return number, kind


def _no_perf_map(what: str, perf_why: str) -> ScoreError:
    """Lỗi khi cần đổi perf_counter sang t_session mà không có ánh xạ; `perf_why` là lý do `build_perf_map` từ chối."""
    return ScoreError(f"{what}: không đổi được perf_counter sang t_session ("
                      + (perf_why or "cần link.json clock của T13 với bo thời gian thực, hoặc mốc CLOCK của T14 cho "
                                     "đúng lần chạy") + ")")


def _resolve_pair(pair: SyncPair, log: RunLogData | None, perf: PerfMap | None,
                  marks: SyncMarks | None, perf_why: str = "") -> ResolvedPair:
    spec = f"{pair.t_ref:g}={pair.side}:{pair.value:g}"
    if pair.side == "session":
        return ResolvedPair(pair.t_ref, pair.value, spec, pair.side, 0.0)
    if pair.side == "io":
        if log is None or log.t0_io is None:
            raise ScoreError(f"cặp đồng bộ {spec}: cần --log có telemetry.csv hoặc link.json clock để biết t0 của io")
        return ResolvedPair(pair.t_ref, pair.value - log.t0_io, spec, pair.side, 0.0)
    if pair.side == "mark":
        if marks is None:
            raise ScoreError(f"cặp đồng bộ {spec}: cần tệp dấu đồng bộ T14 (--sync-marks)")
        t_perf = marks.mark(int(pair.value)).t_perf
    else:
        t_perf = pair.value
    if perf is None:
        raise _no_perf_map(f"cặp đồng bộ {spec}", perf_why)
    t_session, error = perf.to_session(t_perf)
    return ResolvedPair(pair.t_ref, t_session, spec, pair.side, error)


NOMINAL_VIDEO_NOTE = "đồng hồ video theo số khung/s danh định"     # = overhead_ref.NOMINAL_NOTE (không nhập vòng)


def _nominal_video_clock(meta) -> bool:
    """Tham chiếu theo đồng hồ video mà thời điểm khung chỉ là số khung/s danh định (T4 `track --allow-nominal-fps`:
    ghi chú NOMINAL_VIDEO_NOTE, source.allow có 'nominal_fps')."""
    if meta.clock != "video":
        return False
    allow = (meta.source or {}).get("allow") or ()
    return NOMINAL_VIDEO_NOTE in (meta.notes or "") or "nominal_fps" in allow


def _fit_pairs(pairs: list[ResolvedPair], source: str, expected: float = 1.0) -> ClockMap:
    """Khớp t_session = scale·t_ref + offset. `expected`: hệ số phải có (giây phiên mỗi giây của đồng hồ tham chiếu;
    k của PerfMap khi cặp đi qua perf_counter, đồng hồ video coi là giây thật); một cặp thì dùng đúng hệ số đó."""
    if len(pairs) == 1:
        p = pairs[0]
        return ClockMap(expected, p.t_session - expected * p.t_ref,
                        f"{source}: 1 cặp (chỉ lệch" + (f", hệ số {expected:g}" if expected != 1.0 else "") + ")")
    xs, ys = [p.t_ref for p in pairs], [p.t_session for p in pairs]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 1e-12:
        raise ScoreError("cặp đồng bộ trùng t_ref: không khớp được")
    scale = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    if abs(scale / expected - 1.0) > 0.01:
        raise ScoreError(f"cặp đồng bộ không nhất quán: hệ số đồng hồ {scale:.5f} lệch {expected:g} quá 1 %")
    offset = my - scale * mx
    residual = max(abs(y - (scale * x + offset)) for x, y in zip(xs, ys))
    return ClockMap(scale, offset, f"{source}: {len(pairs)} cặp, bình phương nhỏ nhất", residual)


def clock_map(track: ReferenceTrack, cli_pairs: list[SyncPair], *, log: RunLogData | None, perf: PerfMap | None,
              marks: SyncMarks | None, time_error: float | None, perf_why: str = ""
              ) -> tuple[ClockMap | None, float | None, list[ResolvedPair], list[str]]:
    """Đồng hồ tham chiếu → t_session. Trả (ánh xạ hoặc None, sai số đồng bộ s hoặc None = chưa biết, cặp, ghi chú).
    Sai số đồng bộ = --time-error (không có thì sync_error_s của tệp mô tả) + sai số đổi perf_counter của cặp +
    phần dư của phép khớp."""
    meta, notes = track.meta, []
    if meta.clock in ("t_session", "t_io"):
        if cli_pairs:
            raise ScoreError(f"đồng hồ tham chiếu là {meta.clock}: không dùng --sync")
        if meta.sync:
            notes.append(f"bỏ qua sync của tệp mô tả: đồng hồ là {meta.clock}")
        if meta.clock == "t_session":
            return ClockMap(1.0, 0.0, "t_session (cùng đồng hồ phiên)", identity=True), 0.0, [], notes
        if log is None or log.t0_io is None:
            raise ScoreError("tham chiếu theo đồng hồ t_io cần --log có telemetry.csv hoặc link.json clock để biết t0")
        return ClockMap(1.0, -log.t0_io, f"t_io − t0, t0 = {log.t0_io:.4f} s ({log.t0_source})"), 0.0, [], notes
    pairs = list(cli_pairs) or list(meta.sync)
    if pairs and len(pairs) < 2 and _nominal_video_clock(meta):
        # một cặp chỉ cho độ lệch, lấy hệ số 1: sai tốc độ của số khung/s danh định (vd. 30 khung/s ghi cho camera
        # chạy 25,5) sẽ đổi im lặng sang t_session; hai cặp trở lên thì _fit_pairs kiểm lệch hệ số 1 % (02/10/2026)
        raise ScoreError(f"{NOMINAL_VIDEO_NOTE} (--allow-nominal-fps): cần ≥ 2 cặp đồng bộ (--sync hay dấu nháy T14) "
                         f"để kiểm tốc độ đồng hồ, đang có 1")
    if pairs:
        resolved = [_resolve_pair(p, log, perf, marks, perf_why) for p in pairs]
        via_perf = perf is not None and any(p.side in ("perf", "mark") for p in resolved)
        cmap = _fit_pairs(resolved, "--sync" if cli_pairs else "sync của tệp mô tả",
                          perf.scale if via_perf else 1.0)
        if via_perf:
            cmap = replace(cmap, time_scale=perf.scale)
        base = time_error if time_error is not None else meta.sync_error_s
        if base is None:
            notes.append("chưa biết sai số đồng bộ R7 (--time-error hoặc sync_error_s của tệp mô tả): các mốc đổi qua "
                         "R7 không chấm được")
            return cmap, None, resolved, notes
        return cmap, base + max(p.error_s for p in resolved) + cmap.residual_s, resolved, notes
    if meta.clock == "perf_counter" and perf is not None and perf.exact:
        # T4 (02/10/2026): stamp perf_counter của camera trễ hơn lúc chụp; sai số = --time-error, không thì
        # sync_error_s của tệp mô tả, tệp không ghi thì 0 như trước
        base = time_error if time_error is not None else meta.sync_error_s
        return ClockMap(1.0, -perf.offset, perf.source, time_scale=1.0), base or 0.0, [], notes
    notes.append(f"đồng hồ tham chiếu {meta.clock}: chưa có cặp đồng bộ R7 (--sync), không đổi được sang t_session")
    return None, None, [], notes


@dataclass(frozen=True)
class EventTime:
    """Mốc của ngưỡng (ví dụ t_vật) trên hai đồng hồ, kèm sai số (None = chưa biết).

    `circular`: vì sao mốc không dùng được cho N-P1 (chính lệnh dừng, hay chính sự kiện dừng của phiên: NGUONG quy
    tắc 3 cấm lấy sự kiện của ngưỡng đang kiểm làm mốc). `time_scale`: giây phiên mỗi giây thật của phép đổi
    perf_counter → t_session mà mốc đã đi qua; None khi mốc không qua perf_counter."""

    spec: str
    t_ref: float | None
    t_session: float | None
    error_ref_s: float | None
    error_session_s: float | None
    from_stop: bool = False
    code: str = ""
    note: str = ""
    circular: str = ""
    time_scale: float | None = None


def _to_ref_error(error: float | None, cmap: ClockMap, sync_error: float | None) -> float | None:
    if error is None:
        return None
    if cmap.identity:
        return error
    return None if sync_error is None else error / cmap.scale + sync_error


def resolve_event(spec: str, *, log: RunLogData | None, track: ReferenceTrack | None,
                  analysis: TrackAnalysis | None, cmap: ClockMap | None, sync_error: float | None,
                  perf: PerfMap | None, marks: SyncMarks | None, time_error: float | None,
                  perf_why: str = "") -> EventTime:
    """Văn phạm: ref:<s> | frame:<n> | session:<s> | io:<s> | perf:<s> | mark:<n>[+dt|-dt] | stop | code:<MÃ>.
    `stop` và `code:<MÃ>` trùng sự kiện dừng của phiên là mốc vòng tròn (`circular`): N-P1 không kiểm được."""
    spec = spec.strip()

    def on_session(t_session: float, error: float | None, **extra) -> EventTime:
        if cmap is None:
            return EventTime(spec, None, t_session, None, error, **extra)
        return EventTime(spec, cmap.to_ref(t_session), t_session, _to_ref_error(error, cmap, sync_error), error,
                         **extra)

    def need_log() -> RunLogData:
        if log is None:
            raise ScoreError(f"--event {spec}: cần --log")
        return log

    if spec == "stop":
        data = need_log()
        t = data.t_first_stop_cmd if data.kind == "vehicle_io" else (
            data.detection.t_session if data.detection else None)
        if t is None:
            raise ScoreError(f"--event stop: log không có lệnh dừng nào ({data.directory})")
        return on_session(t, 0.0, from_stop=True, code="STOP", circular="mốc là chính lệnh dừng (vòng tròn)")
    kind, sep, value = spec.partition(":")
    if not sep or not value:
        raise ScoreError(f"--event {spec!r}: cần ref:<s>, frame:<n>, session:<s>, io:<s>, perf:<s>, mark:<n>[+dt], "
                         f"stop hoặc code:<MÃ>")
    try:
        if kind in ("ref", "frame"):
            if track is None or track.meta.method == "R2":
                raise ScoreError(f"--event {spec}: cần tệp tham chiếu R1 hoặc --sim-truth")
            frame_error = 0.0 if track.meta.method == "MP" else (analysis.frame_period_s if analysis else None)
            if kind == "ref":
                t_ref = float(value)
            else:
                n = int(value)
                sample = next((s for s in track.samples if s.frame == n), None)
                if sample is None:
                    raise ScoreError(f"--event frame:{n}: tệp tham chiếu không có khung {n}")
                t_ref = sample.t
            if cmap is None:
                return EventTime(spec, t_ref, None, frame_error, None, note="CHƯA ĐO ĐƯỢC (thiếu R7)")
            if frame_error is None:
                error = None
            elif cmap.identity:
                error = frame_error
            else:
                error = None if sync_error is None else frame_error * cmap.scale + sync_error
            return EventTime(spec, t_ref, cmap.to_session(t_ref), frame_error, error, time_scale=cmap.time_scale)
        if kind == "session":
            return on_session(float(value), 0.0)
        if kind == "io":
            data = need_log()
            if data.t0_io is None:
                raise ScoreError(f"--event {spec}: log không cho biết t0 của io")
            return on_session(float(value) - data.t0_io, 0.0)
        if kind in ("perf", "mark"):
            need_log()
            dt = 0.0
            if kind == "mark":
                match = re.fullmatch(r"(\d+)([+-]\d+(?:\.\d*)?)?", value)
                if match is None:
                    raise ScoreError(f"--event {spec}: cần mark:<n> hoặc mark:<n>+<giây> (giây đọc trên video)")
                if marks is None:
                    raise ScoreError(f"--event {spec}: cần tệp dấu đồng bộ T14 (--sync-marks)")
                t_perf = marks.mark(int(match.group(1))).t_perf
                dt = float(match.group(2) or 0.0)
                t_perf += dt
            else:
                t_perf = float(value)
            if perf is None:
                raise _no_perf_map(f"--event {spec}", perf_why)
            t_session, error = perf.to_session(t_perf)
            note = ""
            if dt != 0.0:
                note = "khoảng từ dấu đồng bộ tới mốc đọc trên video"
                # dt và sai số đọc video là giây thật: sang giây phiên nhân hệ số của phép đổi
                error = None if time_error is None else error + perf.scale * time_error
                if time_error is None:
                    note += ": chưa biết sai số đọc video (--time-error)"
            return on_session(t_session, error, note=note, time_scale=perf.scale)
        if kind == "code":
            data = need_log()
            hits = [e for e in data.events if e.code == value and e.t_session is not None]
            if not hits:
                raise ScoreError(f"--event {spec}: log không có sự kiện mã {value}")
            first = min(hits, key=lambda e: e.t_session)
            # Chính quyết định dừng của phiên, hay dòng cùng mã với nó (dòng "stop" lúc lớp nối nhận sự kiện bo, T13):
            # mốc vòng tròn. Mã chỉ có ở gói SIM như obstacle, data_loss không phải phát hiện: vẫn dùng được.
            det = data.detection
            circular = ""
            if first.detection or (det is not None and det.code and det.code == value):
                circular = f"mốc {spec} là chính sự kiện dừng của phiên (vòng tròn, NGUONG quy tắc 3)"
            return on_session(_decision_time(first.t_session, first.t_io, data.t0_real), 0.0, code=value,
                              circular=circular)
    except ValueError as exc:
        if isinstance(exc, ScoreError):
            raise
        raise ScoreError(f"--event {spec!r}: {exc}") from exc
    raise ScoreError(f"--event {spec!r}: loại mốc {kind!r} không hỗ trợ")


# ====================================================================== kiểm từng ngưỡng
@dataclass
class CheckResult:
    code: str
    label: str
    verdict: str
    value: float | str | None = None
    unit: str = ""
    limit: float | None = None
    op: str = ""
    error: float | None = None     # cùng đơn vị với value
    note: str = ""
    cells: dict[str, str] = field(default_factory=dict)
    detail: dict = field(default_factory=dict)

    def value_text(self) -> str:
        """Giá trị như ghi ở ô biên bản (một ô), không thì số 3 chữ số; '' khi chưa có."""
        cell = next(iter(self.cells.values()), "") if len(self.cells) == 1 else ""
        if cell:
            return cell
        if isinstance(self.value, float):
            return f"{self.value:.3f}"
        return "" if self.value is None else str(self.value)

    def line(self) -> str:
        """Một dòng in ra màn hình, ví dụ 'N-D1 sai số vị trí cuối: 0.6 cm ≤ 5 cm → đạt (tham chiếu ±0 cm)'."""
        value = self.value_text()
        unit = f" {self.unit}" if self.unit else ""
        text = f"{self.code} {self.label}: " + (f"{value}{unit}" if value else "—")
        if self.limit is not None and self.op:
            text += f" {self.op} {self.limit:g}{unit}"
        text += f" → {VERDICT_LABELS[self.verdict]}"
        if self.error is not None:
            text += f" (tham chiếu ±{self.error:.3g}{unit})"
        if self.note:
            text += f"; {self.note}"
        return text


def judge(value: float, limit: float, error: float | None, ratio: float, kind: str, unit: str = "") -> tuple[str, str]:
    """Quy tắc 3: sai số chưa biết hay > limit/ratio thì không kiểm được; còn lại so ngưỡng (kind 'max': ≤, 'min': ≥).
    Giá trị vẫn được ghi ở mọi trường hợp."""
    if error is None:
        return KHONG_KIEM_DUOC, "chưa có độ chính xác tham chiếu (TC-1)"
    if error > limit / ratio + 1e-12:
        unit = f" {unit}" if unit else ""
        return KHONG_KIEM_DUOC, f"tham chiếu ±{error:.3g}{unit} > {limit:g}{unit}/{ratio:g}, quy tắc 3"
    ok = value <= limit + 1e-12 if kind == "max" else value >= limit - 1e-12
    return (DAT if ok else KHONG_DAT), ""


@dataclass
class FinalPose:
    pose: Pose
    pos_e: float | None            # m
    yaw_e: float | None            # rad
    source: str


@dataclass
class _Context:
    rule: ScenarioRule
    thresholds: Thresholds
    level: str
    log: RunLogData | None
    layout: Scenario | None
    cfg: VehicleConfig | None
    goal: Pose | None
    track: ReferenceTrack | None
    analysis: TrackAnalysis | None
    final: FinalPose | None
    final_note: str
    cmap: ClockMap | None
    sync_error: float | None
    event: EventTime | None
    sim_truth: bool
    touch: str | None
    intervention: str | None
    remaining_cm: float | None
    stop_distance_cm: float | None
    v_max_mps: float | None
    clearance: tuple[float, str | None, float | None] | None = None

    @property
    def ratio(self) -> float:
        return self.thresholds.reference_ratio

    @property
    def params(self) -> AnalysisParams:
        return self.thresholds.analysis

    @property
    def completed(self) -> bool:
        return self.log is not None and self.log.outcome == "COMPLETED"

    @property
    def trajectory(self) -> bool:
        return self.track is not None and self.track.has_trajectory and self.analysis is not None

    def track_fp_error(self) -> float | None:
        acc = self.track.meta.accuracy if self.track is not None else None
        if acc is None or self.cfg is None:
            return None
        yaw = math.radians(acc.yaw_max_deg) if acc.yaw_max_deg is not None else None
        return footprint_error(self.cfg, acc.pos_max_m, yaw)


def _not_completed(ctx: _Context, result: CheckResult) -> CheckResult:
    """Lần chạy không COMPLETED: N-D1…N-D3 không áp dụng nhưng vẫn ghi số."""
    if ctx.log is not None and not ctx.completed:
        result.verdict = KHONG_AP_DUNG
        ended = f"lần chạy kết thúc {ctx.log.outcome}" if ctx.log.ended else "log xuất khi lần chạy chưa kết thúc"
        result.note = f"{ended}: chỉ ghi số" + (f"; {result.note}" if result.note else "")
    return result


def check_nd1(ctx: _Context) -> CheckResult:
    limit = ctx.thresholds.limit("N-D1", "max_cm")
    out = CheckResult("N-D1", "sai số vị trí cuối", KHONG_KIEM_DUOC, unit="cm", limit=limit, op="≤")
    if ctx.final is None:
        out.note = ctx.final_note
        return _not_completed(ctx, out)
    fin, goal = ctx.final, ctx.goal
    value = math.hypot(fin.pose.x - goal.x, fin.pose.y - goal.y) * 100
    out.value, out.error = value, (fin.pos_e * 100 if fin.pos_e is not None else None)
    out.verdict, out.note = judge(value, limit, out.error, ctx.ratio, "max", "cm")
    out.cells = {"sai_so_vi_tri_cm": f"{value:.1f}"}
    out.detail = {"final_pose": fin.pose.to_dict(), "goal": goal.to_dict(), "source": fin.source}
    return _not_completed(ctx, out)


def check_nd2(ctx: _Context) -> CheckResult:
    limit = ctx.thresholds.limit("N-D2", "max_deg")
    out = CheckResult("N-D2", "sai số hướng cuối (|·|)", KHONG_KIEM_DUOC, unit="°", limit=limit, op="≤")
    if ctx.final is None:
        out.note = ctx.final_note
        return _not_completed(ctx, out)
    value = math.degrees(wrap_angle(ctx.final.pose.yaw - ctx.goal.yaw))
    out.value = value
    out.error = math.degrees(ctx.final.yaw_e) if ctx.final.yaw_e is not None else None
    out.verdict, out.note = judge(abs(value), limit, out.error, ctx.ratio, "max", "°")
    out.cells = {"sai_so_huong_deg": f"{value:+.2f}"}
    return _not_completed(ctx, out)


def check_nd3(ctx: _Context) -> CheckResult:
    out = CheckResult("N-D3", "thân xe trong ô", KHONG_KIEM_DUOC)
    if ctx.layout is None or ctx.layout.slot is None:
        out.verdict, out.note = KHONG_AP_DUNG, "bố trí không có ô đỗ"
        return out
    if ctx.final is None:
        out.note = ctx.final_note
        return _not_completed(ctx, out)
    margin = slot_margin(ctx.cfg, ctx.final.pose, ctx.layout.slot)
    fp_e = footprint_error(ctx.cfg, ctx.final.pos_e, ctx.final.yaw_e)
    out.detail = {"margin_m": margin, "footprint_error_m": fp_e}
    out.label += f" (lề góc thân xe {margin * 100:+.1f} cm" + (
        f", sai số ±{fp_e * 100:.2g} cm)" if fp_e is not None else ")")
    if fp_e is None:
        out.value, out.note = "", "chưa có độ chính xác tham chiếu (TC-1)"
    elif margin >= fp_e:
        out.value, out.verdict = "co", DAT
    elif margin <= -fp_e:
        out.value, out.verdict = "khong", KHONG_DAT
    else:
        out.value = ""
        out.note = (f"lề {margin * 100:+.1f} cm nằm trong sai số góc thân xe ±{fp_e * 100:.1f} cm (vị trí + tầm × "
                    f"sin hướng, quy tắc 3): kiểm R4")
    out.cells = {"trong_o": out.value}
    return _not_completed(ctx, out)


def check_nd4(ctx: _Context) -> CheckResult:
    out = CheckResult("N-D4", "chạm", KHONG_KIEM_DUOC)
    notes = []
    if ctx.touch is not None:                   # quan sát của người (R5/R3), ghi ở phuong_phap_do qua --methods
        out.value = ctx.touch
        out.verdict = KHONG_DAT if ctx.touch == "co" else DAT
    elif ctx.sim_truth and ctx.log is not None and ctx.log.runlog_rows is not None:
        hit = any((r.get("collided") or "0").strip() == "1" for r in ctx.log.runlog_rows)
        out.value = "co" if hit else "khong"
        out.verdict = KHONG_DAT if hit else DAT
        notes.append("va chạm hình học của mô phỏng (gồm mép sa bàn)" + (", xe ảo" if ctx.level.startswith("BT")
                                                                          else ""))
    else:
        notes.append("chưa có quan sát chạm: --touch co|khong (R5, R3)")
    fp_e = ctx.track_fp_error()
    if ctx.clearance is not None and ctx.track is not None and ctx.track.meta.method == "R1" and fp_e is not None \
            and ctx.clearance[0] <= fp_e:
        notes.append(f"R1 không loại trừ chạm {ctx.clearance[1]}: kiểm R5")
    out.note = "; ".join(notes)
    out.cells = {"cham": out.value} if out.value else {}
    return out


def check_nd5(ctx: _Context) -> CheckResult:
    limit = ctx.thresholds.limit("N-D5", "min_cm")
    out = CheckResult("N-D5", "khoảng hở nhỏ nhất thân xe – vật", KHONG_KIEM_DUOC, unit="cm", limit=limit, op="≥")
    if not ctx.trajectory:
        out.note = "chưa có quỹ đạo tham chiếu (R1/MP): dùng R5 (cờ cách vật 2 cm)"
        return out
    if not ctx.layout.obstacles:
        out.verdict, out.note = KHONG_AP_DUNG, "bố trí không có vật"
        return out
    d, oid, t = ctx.clearance
    fp_e = ctx.track_fp_error()
    out.value, out.error = d * 100, (fp_e * 100 if fp_e is not None else None)
    out.verdict, out.note = judge(out.value, limit, out.error, ctx.ratio, "min", "cm")
    out.cells = {"khoang_ho_min_cm": f"{out.value:.1f}"}
    out.detail = {"obstacle": oid, "t_ref": t, "border_clearance_m": border_clearance(ctx.analysis, ctx.cfg,
                                                                                      ctx.layout)}
    if ctx.analysis.moving_gap is not None:
        out.verdict = KHONG_KIEM_DUOC
        out.note = "tham chiếu có khoảng trống dữ liệu khi xe chạy: số này chỉ là cận trên"
    return out


def _flips(series: list[tuple[float, float | None, float]]) -> list[tuple[float, float | None]]:
    """Các lần v tham chiếu của log đổi dấu (bỏ qua giá trị 0): (t, |v đo| ở mẫu đầu sau khi đổi)."""
    out, sign = [], 0
    for t, v_meas, v_ref in series:
        if abs(v_ref) <= 1e-9:
            continue
        new = 1 if v_ref > 0 else -1
        if sign and new != sign:
            out.append((t, abs(v_meas) if v_meas is not None else None))
        sign = new
    return out


def check_nd6(ctx: _Context) -> CheckResult:
    standstill = ctx.thresholds.limit("N-D6", "standstill_mps")
    log = ctx.log
    out = CheckResult("N-D6", "đổi chiều", KHONG_KIEM_DUOC)
    flips = _flips(log.speed_series)
    lap = log.planned_cusps
    if ctx.trajectory:
        thuc, source = reversals_on_reference(ctx.analysis, ctx.params.reversal_hysteresis_m), "tham chiếu"
    else:
        thuc, source = len(flips), "v tham chiếu của log (R6)"
    notes = []
    if source == "tham chiếu" and thuc != len(flips):
        notes.append(f"tham chiếu đếm {thuc} lần, v tham chiếu của log đổi dấu {len(flips)} lần")
    parts = {}
    if lap is None:
        parts["a"] = parts["b"] = KHONG_KIEM_DUOC
        notes.append(log.plan_note or "chưa biết số lần đổi chiều đã lập")
    else:
        if thuc == lap:
            parts["a"] = DAT
        elif thuc < lap and not ctx.completed:
            # (a) cấm đổi chiều THÊM; lần chạy dừng giữa đường chưa tới các lần đổi chiều còn lại (lập lấy từ cả quỹ
            # đạo trong run.json): không xét, để người chấm chọn DUNG_DUNG hay THAT_BAI như mọi lần đỗ bị dừng.
            parts["a"] = KHONG_AP_DUNG
            ended = f"lần chạy kết thúc {log.outcome}" if log.ended else "log xuất khi lần chạy chưa kết thúc"
            notes.append(f"(a) thực {thuc} < lập {lap}: {ended}, đường chưa đi hết")
        else:
            parts["a"] = KHONG_DAT
        if ctx.rule.max_cusps is None:
            parts["b"] = CHI_BAO_SO
        else:
            parts["b"] = DAT if lap <= ctx.rule.max_cusps else KHONG_DAT
        if parts["a"] == KHONG_DAT:
            notes.append(f"(a) thực {thuc} ≠ lập {lap}")
        if parts["b"] == KHONG_DAT:
            notes.append(f"(b) lập {lap} > {ctx.rule.max_cusps}")
    speeds = [v for _, v in flips]
    worst = max((v for v in speeds if v is not None), default=None)
    if any(v is None for v in speeds):
        parts["c"] = KHONG_KIEM_DUOC
        notes.append("(c) thiếu tốc độ đo lúc đổi chiều")
    elif log.kind == "vehicle_io" and log.evidence == "simulation_only":
        parts["c"] = CHI_BAO_SO
        notes.append(f"(c) chỉ báo số ở bo mô phỏng: nhiễu encoder giả định 0,01 m/s bằng ngưỡng"
                     + (f"; |v đo| lớn nhất lúc đổi {worst:.3f} m/s" if worst is not None else ""))
    else:
        parts["c"] = DAT if worst is None or worst <= standstill + 1e-12 else KHONG_DAT
        if parts["c"] == KHONG_DAT:
            notes.append(f"(c) |v đo| lúc đổi chiều {worst:.3f} m/s > {standstill:g} m/s")
    verdicts = parts.values()
    out.verdict = KHONG_DAT if KHONG_DAT in verdicts else (KHONG_KIEM_DUOC if KHONG_KIEM_DUOC in verdicts else DAT)
    out.value = f"lập {lap if lap is not None else '?'}, thực {thuc} ({source})"
    out.note = "; ".join(notes)
    out.cells = {"doi_chieu_lap": "" if lap is None else str(lap), "doi_chieu_thuc": str(thuc)}
    out.detail = {"parts": parts, "plan_source": log.plan_source, "log_flips": len(flips),
                  "speed_at_flips_mps": speeds, "max_cusps": ctx.rule.max_cusps}
    return out


def check_nd7(ctx: _Context) -> CheckResult:
    limit = ctx.thresholds.limit("N-D7", "max_run_s")
    log = ctx.log
    out = CheckResult("N-D7", "thời gian (START tới hết lần chạy, R6)", KHONG_KIEM_DUOC, unit="s", limit=limit,
                      op="<")
    timeout_event = any(e.code == "RUN_TIMEOUT" for e in log.events)
    if log.t_end is None or (not log.ended and not timeout_event):
        out.note = ("log chưa có kết quả lần chạy" if log.t_end is None else
                    f"log xuất khi lần chạy chưa kết thúc ({log.outcome}): {log.t_end:.2f} s chưa phải thời gian cả "
                    f"lần chạy")
        return out
    timeout = timeout_event or log.t_end >= limit - 0.01
    out.value, out.verdict = log.t_end, (KHONG_DAT if timeout else DAT)
    notes = ["RUN_TIMEOUT"] if timeout else []
    if log.max_run_time is not None and abs(log.max_run_time - limit) > 1e-6:
        notes.append(f"MAX_RUN_TIME của lần chạy {log.max_run_time:g} s khác ngưỡng {limit:g} s")
    out.note = "; ".join(notes)
    out.cells = {"thoi_gian_s": f"{log.t_end:.2f}"}
    return out


def check_nd9(ctx: _Context) -> CheckResult:
    out = CheckResult("N-D9", "can thiệp của người", KHONG_KIEM_DUOC)
    if ctx.intervention is not None:
        out.value, out.verdict = ctx.intervention, (KHONG_DAT if ctx.intervention == "co" else DAT)
    elif ctx.sim_truth:
        out.value, out.verdict, out.note = "khong", DAT, "mô phỏng: không có người can thiệp"
    else:
        out.note = "chưa ghi can thiệp: --intervention co|khong"
    out.cells = {"can_thiep": out.value} if out.value else {}
    return out


def check_nv1(ctx: _Context) -> CheckResult:
    """N-V1 (NGUONG mục 2): tốc độ đo trung bình trên đoạn `speed_window_m` ≤ max_mps (tham chiếu R1/MP, hay R3 qua
    --v-max-mps) và, khi tệp ngưỡng có target_mps (02/10/2026), vế mục tiêu (`_nv1_target`). Vế nào không đạt thì N-V1
    không đạt; ô v_max_do_mps chỉ ghi tốc độ đo."""
    limit = ctx.thresholds.limit("N-V1", "max_mps")
    window = ctx.params.speed_window_m
    out = CheckResult("N-V1", f"tốc độ đo lớn nhất (đoạn {window:g} m)", KHONG_KIEM_DUOC, unit="m/s", limit=limit,
                      op="≤")
    if ctx.v_max_mps is not None:
        out.value = ctx.v_max_mps
        out.verdict = DAT if ctx.v_max_mps <= limit + 1e-12 else KHONG_DAT
        out.note = "R3 (người đo, không kiểm quy tắc 3)"
    elif ctx.trajectory:
        best = max_speed(ctx.analysis, window)
        if best is None:
            out.note = f"quãng chạy theo tham chiếu ngắn hơn {window:g} m"
        else:
            v, dt, t0 = best
            pos_e = ctx.track.meta.accuracy.pos_max_m
            out.value, out.error = v, (math.sqrt(2) * pos_e / dt if pos_e is not None else None)
            out.verdict, out.note = judge(v, limit, out.error, ctx.ratio, "max", "m/s")
            out.detail = {"t_start_ref": t0, "dt_s": dt}
            if ctx.analysis.moving_gap is not None:
                out.verdict, out.note = KHONG_KIEM_DUOC, "tham chiếu có khoảng trống dữ liệu khi xe chạy"
    else:
        out.note = "chưa có quỹ đạo tham chiếu: đo R3 rồi dùng --v-max-mps"
    if out.value is not None:
        out.cells = {"v_max_do_mps": f"{out.value:.3f}"}
    _nv1_target(ctx, out)
    return out


def _vehicle_text(vehicle: dict | None) -> str:
    if not vehicle:
        return "xe của lần chạy không rõ"
    cap = vehicle.get("max_speed_mps")
    return f"xe của lần chạy {vehicle.get('name', '?')}" + (f", tối đa {cap:g} m/s" if cap is not None else "")


def _nv1_target(ctx: _Context, out: CheckResult) -> None:
    """Vế mục tiêu của N-V1 (thêm 02/10/2026; người dùng giao quyết định 02/10/2026 ('làm hết'), ngưỡng ĐỀ XUẤT – CHỜ
    CHỐT): |tốc độ mục tiêu| lớn nhất của lệnh bám đường trong log ≤ target_mps ('tốc độ mục tiêu ≤ 0,10 m/s ở đợt
    đầu'; lệnh đã gửi lấy từ log được, NGUONG quy tắc 2). Log không có tốc độ mục tiêu hay tệp ngưỡng không có
    target_mps: 'không áp dụng', chỉ ghi ở tệp chi tiết. Không đạt thì N-V1 không đạt. Xe mô phỏng bị kẹp ở
    max_speed_mps của cấu hình xe: khi mức đó ≤ max_mps, ghi chú rằng N-V1 không kiểm vọt lố (không đổi kết luận)."""
    log = ctx.log
    limit = ctx.thresholds.limit_or_none("N-V1", "target_mps")
    target = log.max_target_mps if log is not None else None
    vehicle = log.run_vehicle if log is not None else None
    cap = vehicle.get("max_speed_mps") if vehicle else None
    notes = [out.note] if out.note else []
    if limit is None or target is None:
        verdict = KHONG_AP_DUNG
    elif target > limit + 1e-9:
        verdict = out.verdict = KHONG_DAT
        notes.append(f"tốc độ mục tiêu lớn nhất {target:.3f} m/s > {limit:g} m/s (vế mục tiêu của N-V1, đợt đầu; "
                     f"{_vehicle_text(vehicle)}): chạy với configs/vehicle_nghiem_thu.json")
    else:
        verdict = DAT
    simulated = log is not None and (log.kind == "sim_bundle" or log.io_simulated is True)
    if simulated and cap is not None and cap <= ctx.thresholds.limit("N-V1", "max_mps") + 1e-12:
        notes.append(f"xe mô phỏng bị kẹp ở max_speed_mps của cấu hình xe ({cap:g} m/s) nên tốc độ đo không vượt mức "
                     f"đó: N-V1 ở mức này không kiểm vọt lố của vòng tốc độ")
    out.note = "; ".join(notes)
    out.detail["target"] = {"limit_mps": limit, "max_target_mps": target, "verdict": verdict,
                            "source": log.target_source if log is not None else "", "vehicle": vehicle}


def check_np1(ctx: _Context) -> CheckResult:
    limit = ctx.thresholds.limit("N-P1", "max_s")
    out = CheckResult("N-P1", "t_phát_hiện − t_vật", KHONG_KIEM_DUOC, unit="s", limit=limit, op="≤")
    det, ev = ctx.log.detection, ctx.event
    if ev is None:
        out.note = "thiếu --event (mốc t_vật)"
        return out
    if det is None:
        if not ctx.log.ended:              # chưa có sự kiện dừng nào TỚI lúc xuất: không biết hệ thống có dừng không
            out.note = "log xuất khi lần chạy chưa kết thúc: chưa biết hệ thống có dừng không"
        else:
            out.verdict, out.note = KHONG_DAT, "log không có sự kiện dừng nào: hệ thống không dừng"
        return out
    out.detail = {"detection": asdict(det), "event": asdict(ev)}
    if ev.circular:
        out.note = ev.circular
        return out
    if ev.t_session is None:
        out.note = "CHƯA ĐO ĐƯỢC (thiếu R7)"
        return out
    value = det.t_session - ev.t_session
    error = None if ev.error_session_s is None else ev.error_session_s + (0.0 if det.exact else det.error_s)
    out.value, out.error = value, error
    out.cells = {"t_phat_hien_s": f"{value:.3f}"}
    if error is None:
        out.note = "chưa biết sai số đồng bộ R7 của mốc (--time-error)" + (f"; {ev.note}" if ev.note else "")
        return out
    out.verdict, note = judge(value, limit, error, ctx.ratio, "max", "s")
    notes = [note] if note else []
    scale_note = _time_scale_note(ev, ctx.params)
    if scale_note:
        out.verdict = KHONG_KIEM_DUOC
        notes.append(scale_note)
    elif value < -error - 1e-9:
        out.verdict = KHONG_KIEM_DUOC
        notes.append("phiên dừng TRƯỚC mốc vật: kiểm lại mốc, đồng bộ hay lý do dừng")
    elif det.by_user and out.verdict == DAT:
        # Người dừng trước khi hết ngưỡng: không biết hệ thống có tự phát hiện kịp không. Người dừng sau ngưỡng
        # (KHÔNG ĐẠT ở trên) thì hệ thống chắc chắn chưa dừng trong ngưỡng.
        out.verdict = KHONG_KIEM_DUOC
        notes.append("lần dừng đầu do người, trước khi hết ngưỡng: không biết hệ thống có tự phát hiện kịp không")
    notes.append(f"dừng đầu: {det.code or '?'} ({det.source}{', người dừng' if det.by_user else ''})")
    if det.t_step is not None and det.t_session - det.t_step > 0.0005:
        notes.append(f"bo thời gian thực: t_phát_hiện lấy t_io lúc phiên quyết định, muộn hơn thời gian bước ghi ở "
                     f"dòng {det.t_session - det.t_step:.3f} s")
    if not det.exact:
        notes.append(det.note)
    if ev.note:
        notes.append(ev.note)
    out.note = "; ".join(notes)
    return out


def _time_scale_note(ev: EventTime | None, params: AnalysisParams) -> str:
    """Mốc đổi từ perf_counter khi phiên chạy khác 1× (tốc độ chạy của giao diện, cột time_scale của T14): khoảng thời
    gian phiên bằng time_scale × khoảng thời gian thật, xe ảo đi theo thời gian phiên còn vật, LiDAR, video theo thời
    gian thật. Ngưỡng phản ứng (N-P1, quãng dừng) đặt cho thời gian thật nên không chấm được; giá trị vẫn ghi."""
    if ev is None or ev.time_scale is None or abs(ev.time_scale - 1.0) <= params.clock_drift:
        return ""
    return (f"phiên chạy {ev.time_scale:g}× (tốc độ chạy, time_scale của T14): thời gian phiên khác thời gian thật, "
            f"ngưỡng phản ứng chỉ chấm ở 1×")


def check_stop_distance(ctx: _Context, code: str) -> CheckResult:
    limit = ctx.thresholds.limit(code, "max_cm")
    out = CheckResult(code, "quãng từ mốc tới đứng yên", KHONG_KIEM_DUOC, unit="cm", limit=limit, op="≤")
    ev = ctx.event
    if ctx.stop_distance_cm is not None:
        out.value = ctx.stop_distance_cm
        out.verdict = DAT if out.value <= limit + 1e-12 else KHONG_DAT
        out.note = "R3 (người đo, không kiểm quy tắc 3)"
        if code == "N-P5c":
            out.verdict = KHONG_DAT if out.verdict == KHONG_DAT else KHONG_KIEM_DUOC
            out.note += "; phần thời gian tới đứng yên chưa có số"
        out.cells = {"quang_dung_cm": f"{out.value:.1f}"}
        return out
    if not ctx.trajectory:
        out.note = "chưa có quỹ đạo tham chiếu: đo R3 rồi dùng --stop-distance-cm"
        return out
    if ev is None:
        out.note = "thiếu --event (mốc bắt đầu quãng)"
        return out
    if ev.t_ref is None:
        out.note = "CHƯA ĐO ĐƯỢC (thiếu R7: mốc không đổi được sang đồng hồ tham chiếu)"
        return out
    still = first_standstill(ctx.analysis, ev.t_ref, ctx.params)
    if still is None:
        out.note = "tham chiếu kết thúc trước khi xe đứng yên"
        return out
    t_still, t_end, _ = still
    value = distance_along(ctx.analysis, ev.t_ref, t_end) * 100
    pos_e = ctx.track.meta.accuracy.pos_max_m
    v_event = speed_at(ctx.analysis, ev.t_ref)
    error = None if pos_e is None or ev.error_ref_s is None else (2 * pos_e + v_event * ev.error_ref_s) * 100
    out.value, out.error = value, error
    out.verdict, note = judge(value, limit, error, ctx.ratio, "max", "cm")
    if pos_e is not None and ev.error_ref_s is None:
        note = "chưa biết sai số đồng bộ R7 của mốc (--time-error)"
    notes = [note] if note else []
    out.detail = {"t_event_ref": ev.t_ref, "t_still_ref": t_still, "t_standstill_window_end_ref": t_end,
                  "speed_at_event_mps": v_event, "time_to_still_s": t_still - ev.t_ref}
    if code == "N-P5c":
        max_s = ctx.thresholds.limit(code, "max_s")
        frame = ctx.analysis.frame_period_s or 0.0
        t_error = None if ev.error_ref_s is None else ev.error_ref_s + frame
        t_verdict, t_note = judge(t_still - ev.t_ref, max_s, t_error, ctx.ratio, "max", "s")
        out.detail["time_verdict"] = t_verdict
        notes.append(f"tới đứng yên sau {t_still - ev.t_ref:.2f} s (≤ {max_s:g} s: {VERDICT_LABELS[t_verdict]}"
                     + (f", {t_note}" if t_note else "") + ")")
        if KHONG_DAT in (out.verdict, t_verdict):
            out.verdict = KHONG_DAT
        elif KHONG_KIEM_DUOC in (out.verdict, t_verdict):
            out.verdict = KHONG_KIEM_DUOC
    scale_note = _time_scale_note(ev, ctx.params)
    if scale_note:                           # xe ảo đi theo thời gian phiên trong lúc LiDAR/vật theo thời gian thật
        out.verdict = KHONG_KIEM_DUOC
        notes.append(scale_note)
    out.note = "; ".join(notes)
    out.cells = {"quang_dung_cm": f"{value:.1f}"}
    return out


def check_np3(ctx: _Context) -> CheckResult:
    limit = ctx.thresholds.limit("N-P3", "min_cm")
    out = CheckResult("N-P3", "khoảng còn lại thân xe – vật sau khi dừng", KHONG_KIEM_DUOC, unit="cm", limit=limit,
                      op="≥")
    log = ctx.log
    if ctx.remaining_cm is not None:
        out.value = ctx.remaining_cm
        out.verdict = DAT if out.value >= limit - 1e-12 else KHONG_DAT
        out.note = "R2 (người đo, không kiểm quy tắc 3)"
    elif ctx.sim_truth and ctx.level.startswith("MP") and log.kind != "sim_bundle":
        out.note = ("log VehicleIO: công cụ chỉ đọc hình vật chèn từ events.jsonl của gói SIM, không từ log VehicleIO: "
                    "dùng --remaining-cm")
        return out
    elif ctx.sim_truth and ctx.level.startswith("MP"):
        if not log.injected_obstacles:
            out.note = "lần chạy không có vật chèn vào"
            return out
        if ctx.final is None or ctx.cfg is None:
            out.note = ctx.final_note or "thiếu cấu hình xe"
            return out
        body = body_polygon(ctx.cfg, ctx.final.pose)
        dist, oid = min((body.distance(obstacle_polygon(o)), o.id) for o in log.injected_obstacles)
        out.value, out.error = dist * 100, 0.0
        out.verdict, _ = judge(out.value, limit, 0.0, ctx.ratio, "min", "cm")
        out.note = f"tới vật chèn {oid} (mô phỏng)"
    elif ctx.sim_truth:
        out.note = ("vật chèn ở mức BT là ước lượng của LiDAR, quy tắc 2 không cho dùng: đo R2 rồi dùng "
                    "--remaining-cm")
        return out
    else:
        out.note = "đo R2 sau khi dừng rồi dùng --remaining-cm"
        return out
    out.cells = {"khoang_con_lai_cm": f"{out.value:.1f}"}
    return out


def check_np4(ctx: _Context) -> CheckResult:
    log = ctx.log
    out = CheckResult("N-P4", "không dừng giả", KHONG_KIEM_DUOC)
    if log.outcome is None:
        out.note = "log chưa có kết quả lần chạy"
    elif not log.ended:
        out.note = f"log xuất khi lần chạy chưa kết thúc ({log.outcome})"
    elif log.outcome == "COMPLETED" and log.detection is None:
        out.verdict, out.value = DAT, "không dừng"
    elif log.outcome == "RESET" or (log.detection is not None and log.detection.by_user):
        out.note = "người dừng hay đặt lại lần chạy: không xét được dừng giả"
    else:
        out.verdict = KHONG_DAT
        out.value = "dừng"
        det = log.detection
        out.note = (f"phiên dừng ({log.reason or log.outcome})" if det is None else
                    f"phiên dừng ở {det.t_session:.3f} s ({det.code or log.reason or '?'})")
    return out


def check_np10(ctx: _Context) -> CheckResult:
    log, ev = ctx.log, ctx.event
    out = CheckResult("N-P10", "không tự chạy lại", KHONG_KIEM_DUOC)
    if log.detection is None:
        out.verdict, out.note = KHONG_AP_DUNG, "lần chạy không có lần dừng"
        return out
    notes = []
    log_fail = bool(log.enable_after_stop)
    if log_fail:
        notes.append(f"log: {log.enable_after_stop} lệnh chạy sau lệnh dừng")
    anchor = ev.t_ref if ev is not None and ev.t_ref is not None else (
        ctx.cmap.to_ref(log.detection.t_session) if ctx.cmap is not None else None)
    ref_fail, ref_known = False, False
    if ctx.trajectory and anchor is not None:
        still = first_standstill(ctx.analysis, anchor, ctx.params)
        if still is not None:
            moved = moved_after(ctx.analysis, still[1], still[2])
            ref_known, ref_fail = True, moved > ctx.params.restart_m
            out.detail = {"moved_after_standstill_m": moved, "standstill_end_ref": still[1]}
            if ref_fail:
                notes.append(f"tham chiếu: xe dịch {moved * 100:.1f} cm sau khi đã đứng yên")
        else:
            notes.append("tham chiếu kết thúc trước khi xe đứng yên")
    if log_fail or ref_fail:
        out.verdict, out.value = KHONG_DAT, "tự chạy lại"
        notes.insert(0, "tự chạy lại")
    else:
        out.verdict, out.value = DAT, "không"
        if not ref_known:
            notes.append("chỉ xét log (R6): chưa có quỹ đạo tham chiếu sau lần dừng")
    out.note = "; ".join(notes)
    return out


def check_zero_command(ctx: _Context) -> CheckResult:
    log = ctx.log
    out = CheckResult("0-COMMAND", "không COMMAND nào ở chế độ quan sát", KHONG_KIEM_DUOC)
    counts = [c for c in (log.commands_sent, log.link_commands_sent) if c is not None]
    out.value = max(counts) if counts else None
    out.verdict = DAT if counts and max(counts) == 0 else (KHONG_DAT if counts else KHONG_KIEM_DUOC)
    out.note = f"commands.csv gửi {log.commands_sent}, link.json commands_sent {log.link_commands_sent}"
    return out


CHECK_FUNCTIONS = {"N-D1": check_nd1, "N-D2": check_nd2, "N-D3": check_nd3, "N-D4": check_nd4, "N-D5": check_nd5,
                   "N-D6": check_nd6, "N-D7": check_nd7, "N-D9": check_nd9, "N-V1": check_nv1, "N-P1": check_np1,
                   "N-P3": check_np3, "N-P4": check_np4, "N-P10": check_np10, "0-COMMAND": check_zero_command}


def run_check(ctx: _Context, code: str) -> CheckResult:
    if code in STOP_DISTANCE_CHECKS:
        return check_stop_distance(ctx, code)
    return CHECK_FUNCTIONS[code](ctx)


# ====================================================================== kết quả, dòng biên bản, tệp chi tiết
def decision_checks(rule: ScenarioRule) -> tuple[str, ...]:
    """Mã kiểm chạy thêm CHỈ để đề xuất ket_qua (ô của chúng vẫn để trống như bảng kịch bản): với lần đỗ là các điều
    kiện THÀNH CÔNG của NGUONG mục 1 mà danh sách của kịch bản thiếu (ví dụ DO-6 thiếu N-D7, N-D9, N-V1); với kịch bản
    khác là N-D4 và N-D9, tuyệt đối ở mọi kịch bản."""
    wanted = SUCCESS_CHECKS if rule.parking else ABSOLUTE_CHECKS
    return tuple(code for code in wanted if code not in rule.checks)


def propose_result(rule: ScenarioRule, checks: list[CheckResult], log: RunLogData | None, manual: str | None,
                   cause: str | None, decision: list[CheckResult] | None = None) -> tuple[str, list[str]]:
    """THAT_BAI khi có kiểm không đạt, kể cả kiểm chỉ để đề xuất (`decision`, xem `decision_checks`): chạm hay can
    thiệp ghi tay (--touch co, --intervention co) luôn là THAT_BAI. THANH_CONG chỉ cho lần đỗ COMPLETED mà mọi kiểm
    của kịch bản và mọi điều kiện THÀNH CÔNG của NGUONG mục 1 đạt/chỉ báo số/không áp dụng; còn lại để trống kèm lý
    do. Không bao giờ tự ghi DUNG_DUNG hay KHONG_TINH."""
    notes = []
    failed = [c.code for c in checks if c.verdict == KHONG_DAT]
    blocked = [c.code for c in checks if c.verdict == KHONG_KIEM_DUOC]
    why = "điều kiện THÀNH CÔNG, NGUONG mục 1" if rule.parking else "tuyệt đối ở mọi kịch bản"
    decision = decision or []
    extra_failed = [c for c in decision if c.verdict == KHONG_DAT]
    extra_blocked = [c.code for c in decision if c.verdict == KHONG_KIEM_DUOC] if rule.parking else []
    for c in extra_failed:
        notes.append(f"{c.code} {c.label}: {c.value_text()}{f' {c.unit}' if c.unit else ''} → không đạt ({why}, "
                     f"ngoài danh sách kiểm của {rule.key})")
    computed = ""
    if failed or extra_failed:
        computed = "THAT_BAI"
    elif rule.parking and log is not None and log.outcome == "COMPLETED" and not blocked and not extra_blocked:
        computed = "THANH_CONG"
    elif rule.parking and log is not None and not log.ended:
        notes.append("log xuất khi lần chạy chưa kết thúc: chưa đề xuất ket_qua (chấm log xuất sau khi lần chạy kết "
                     "thúc)")
    elif rule.parking and log is not None and log.outcome != "COMPLETED":
        notes.append(f"phiên dừng ({log.reason or log.outcome}): người chấm chọn DUNG_DUNG hay THAT_BAI, xét N-P4")
    elif blocked or extra_blocked:
        notes.append("chưa đề xuất ket_qua: " + ", ".join(blocked + [f"{c} ({why})" for c in extra_blocked])
                     + " không kiểm được")
    elif checks:
        notes.append("không có kiểm nào không đạt: người chấm chọn DUNG_DUNG hay THAT_BAI")
    result = computed
    if manual:
        if computed and manual != computed:
            notes.append(f"người chấm ghi {manual}, công cụ đề xuất {computed}")
        result = manual
    if result == "THAT_BAI" and not cause:
        notes.append("cần ghi nguyên nhân chính (mục 1.4)")
    return result, notes


def _relative(path: Path) -> str:
    try:
        return Path(os.path.relpath(Path(path).resolve(), Path.cwd())).as_posix()
    except ValueError:                    # khác ổ đĩa trên Windows
        return Path(path).resolve().as_posix()


def _check_report(report: Path, row: dict, replace_row: bool) -> list[dict]:
    """Đọc biên bản hiện có (nếu có), kiểm tiêu đề và khóa trùng; trả các dòng sau khi thêm/thay dòng mới."""
    rows: list[dict] = []
    if report.exists():
        try:
            with report.open(encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                header = list(reader.fieldnames or [])
        except PermissionError as exc:
            raise ScoreError(f"không đọc được {report} ({exc}): đóng tệp trong Excel rồi chạy lại") from exc
        except (OSError, csv.Error, UnicodeDecodeError) as exc:
            raise ScoreError(f"không đọc được biên bản {report}: {exc}") from exc
        if header != BIEN_BAN_FIELDS:
            raise ScoreError(f"biên bản {report} có tiêu đề khác mẫu KICH_BAN mục 2.3: {header}")
    key = tuple(row[k] for k in ROW_KEY)
    hits = [i for i, r in enumerate(rows) if tuple((r.get(k) or "") for k in ROW_KEY) == key]
    if hits and not replace_row:
        raise ScoreError(f"biên bản {report} đã có dòng {key[0]} biến thể {key[1]!r} lần {key[2]} mức {key[3]}: "
                         f"dùng --replace để thay")
    if hits:
        rows[hits[0]] = row
        rows = [r for i, r in enumerate(rows) if i not in hits[1:]]
    else:
        rows.append(row)
    return rows


def write_row(report, row: dict, replace_row: bool = False) -> Path:
    """Ghi dòng biên bản: UTF-8 có BOM (Excel đọc được), tiêu đề đúng BIEN_BAN_FIELDS, khóa (mã, biến thể, lần, mức)
    không trùng trừ khi replace_row. Ghi ra <tệp>.tmp rồi os.replace, nên không bao giờ để lại tệp ghi dở."""
    report = Path(report)
    rows = _check_report(report, row, replace_row)
    temporary = report.with_name(report.name + ".tmp")
    try:
        report.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=BIEN_BAN_FIELDS)
            writer.writeheader()
            writer.writerows({k: r.get(k, "") for k in BIEN_BAN_FIELDS} for r in rows)
        os.replace(temporary, report)
    except PermissionError as exc:
        temporary.unlink(missing_ok=True)
        raise ScoreError(f"không ghi được {report} ({exc}): đóng tệp trong Excel rồi chạy lại") from exc
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise ScoreError(f"không ghi được {report}: {exc}") from exc
    return report


def _jsonable(value):
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


# ====================================================================== dòng lệnh
class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, f"LỖI: {message}\n")


def _finite(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} không phải số") from None
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError(f"{text!r} không hữu hạn")
    return value


def _non_negative(text: str) -> float:
    value = _finite(text)
    if value < 0:
        raise argparse.ArgumentTypeError(f"{text!r} phải ≥ 0")
    return value


def _numbers(count: int):
    def parse(text: str) -> tuple[float, ...]:
        parts = [p for p in text.split(",")]
        if len(parts) != count:
            raise argparse.ArgumentTypeError(f"{text!r}: cần {count} số cách nhau bằng dấu phẩy")
        return tuple(_finite(p.strip()) for p in parts)
    return parse


def _sync_arg(text: str) -> SyncPair:
    ref, sep, side = text.partition("=")
    if not sep:
        raise argparse.ArgumentTypeError(f"--sync {text!r}: cần REF=PHIÊN, ví dụ 12.30=5.00 hoặc 12.30=mark:1")
    try:
        value, kind = parse_sync_side(side)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--sync {text!r}: {exc}") from None
    return SyncPair(_finite(ref.strip()), value, kind)


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="python -m autopark.evaluation.score_run",
                description="Chấm một lần chạy nghiệm thu (T5) và ghi một dòng biên bản (KICH_BAN_NGHIEM_THU.md mục "
                            "2.3). Ngưỡng ĐỀ XUẤT – CHỜ CHỐT ở configs/nguong_nghiem_thu.json.")
    g = p.add_argument_group("lần chạy")
    g.add_argument("--scenario", required=True, help="mã kịch bản, ví dụ DO-1, VC-1, AT-5")
    g.add_argument("--variant", default="", help="biến thể (a, b, c, dung, do…); khóa ngưỡng là mã + biến thể khi "
                                                 "có khóa đó")
    g.add_argument("--attempt", required=True, type=int, help="số thứ tự lần chạy, ≥ 1, đánh trước khi chạy")
    g.add_argument("--level", required=True, help="mức thử MP, BT hoặc XT, có thể kèm /M0…/M3 (ví dụ XT/M3)")
    g = p.add_argument_group("dữ liệu")
    g.add_argument("--log", help="thư mục log: <tên>_vehicle_io của 'Xuất log CSV…', gói <tên>_<giờ> của export_run "
                                 "(SIM, hay lần chạy qua VehicleIO có vehicle_io/), hoặc <gói>/vehicle_io")
    g.add_argument("--runlog", help="RunLog <tên>.csv khi không nằm cạnh thư mục _vehicle_io")
    g.add_argument("--layout", help="bố trí tham chiếu đo bằng thước (JSON cùng dạng scenarios/*.json)")
    g.add_argument("--vehicle", help="cấu hình xe; mặc định theo vehicle_config của bố trí (bố trí nghiệm thu trong "
                                     "docs/evidence/nghiem_thu/ trỏ ../../../configs/vehicle_nghiem_thu.json)")
    g = p.add_argument_group("tham chiếu độc lập (R1, R2 hoặc tư thế thật của mô phỏng)")
    g.add_argument("--reference", help="tệp tư thế tham chiếu <tên>.csv (+ <tên>.json), evaluation/reference_pose.py")
    g.add_argument("--sim-truth", action="store_true",
                   help="dùng tư thế THẬT trong RunLog của log mô phỏng (chỉ mức MP và xe ảo của BT)")
    g.add_argument("--r2-points", type=_numbers(4), metavar="X1,Y1,X2,Y2",
                   help="R2: hai dấu trên trục dọc xe đo bằng thước, hệ sa bàn (m): điểm 1 dấu sau, điểm 2 dấu trước")
    g.add_argument("--r2-marks", type=_numbers(2), metavar="D1,D2",
                   help="tọa độ x trong hệ xe của hai dấu (m); mặc định −rear_overhang và wheelbase + front_overhang")
    g.add_argument("--r2-error-cm", type=_non_negative, default=0.5,
                   help="sai số lớn nhất của mỗi điểm R2 (cm), mặc định 0.5")
    g.add_argument("--ref-window", type=_numbers(2), metavar="A,B", help="chỉ dùng tham chiếu trong [A, B] (giây)")
    g = p.add_argument_group("đồng hồ và mốc")
    g.add_argument("--sync", type=_sync_arg, action="append", default=[], metavar="REF=PHIÊN",
                   help="cặp đồng bộ R7, lặp được: phía log là <t_session>, io:<t_io>, perf:<perf_counter> hoặc "
                        "mark:<n> (dấu SYNC_MARK thứ n của tệp T14)")
    g.add_argument("--sync-marks", help="tệp dấu đồng bộ T14; mặc định <tên>_sync_marks.csv cạnh thư mục log")
    g.add_argument("--time-error", type=_non_negative,
                   help="sai số đồng bộ phía tham chiếu/video (s): đọc khung, độ trễ màn hình…")
    g.add_argument("--event", help="mốc của ngưỡng phản ứng: ref:<s>, frame:<n>, session:<s>, io:<s>, perf:<s>, "
                                   "mark:<n>[+<s>], stop, code:<MÃ>")
    g = p.add_argument_group("quan sát của người")
    g.add_argument("--touch", choices=("co", "khong"), help="chạm vật (R5/R3)")
    g.add_argument("--intervention", choices=("co", "khong"), help="có can thiệp của người")
    g.add_argument("--remaining-cm", type=_finite, help="khoảng còn lại tới vật sau khi dừng, đo R2 (cm)")
    g.add_argument("--stop-distance-cm", type=_finite, help="quãng dừng đo R3 (cm), thay số của tham chiếu")
    g.add_argument("--v-max-mps", type=_finite, help="tốc độ lớn nhất đo R3 (m/s), thay số của tham chiếu")
    g.add_argument("--methods", default="", help="phương pháp đo thêm, ví dụ R3,R5")
    g.add_argument("--result", choices=RESULTS, help="kết quả do người chấm chọn (thắng đề xuất của công cụ)")
    g.add_argument("--cause", help="nguyên nhân chính (KICH_BAN mục 1.4), bắt buộc với THAT_BAI và KHONG_TINH")
    g.add_argument("--note", default="", help="ghi chú thêm")
    g.add_argument("--when", help="ngày giờ lần chạy 'YYYY-MM-DD HH:MM'; mặc định giờ sửa link.json/result.json")
    g = p.add_argument_group("đầu ra")
    g.add_argument("--thresholds", default=str(DEFAULT_THRESHOLDS), help="tệp ngưỡng")
    g.add_argument("--report", help="tệp biên bản CSV (bắt buộc trừ khi --dry-run)")
    g.add_argument("--detail", help="tệp chi tiết JSON; mặc định <thư mục log>.cham_<mã><biến thể>_l<lần>.json cạnh "
                                    "thư mục log (cạnh gói khi log nằm trong gói T9)")
    g.add_argument("--replace", action="store_true", help="thay dòng đã có cùng (mã, biến thể, lần, mức)")
    g.add_argument("--dry-run", action="store_true", help="chỉ in, không ghi tệp nào")
    return p


@dataclass
class Report:
    rule: ScenarioRule
    checks: list[CheckResult]
    row: dict[str, str]
    detail: dict
    lines: list[str]
    report_path: Path | None
    detail_path: Path | None


def _check_arguments(args, thresholds: Thresholds) -> tuple[ScenarioRule, str]:
    """Lỗi đầu vào biết được trước khi đọc log. Trả (quy tắc của kịch bản, mức MP/BT/XT)."""
    if not LEVEL_RE.match(args.level):
        raise ScoreError(f"--level {args.level!r}: cần MP, BT hoặc XT, có thể kèm /M0…/M3")
    if args.attempt < 1:
        raise ScoreError("--attempt phải ≥ 1")
    if args.when is not None and not WHEN_RE.match(args.when):
        raise ScoreError(f"--when {args.when!r}: cần dạng 'YYYY-MM-DD HH:MM'")
    if args.result in ("THAT_BAI", "KHONG_TINH") and not args.cause:
        raise ScoreError(f"--result {args.result} cần --cause (nguyên nhân chính, KICH_BAN mục 1.4)")
    if not args.dry_run and not args.report:
        raise ScoreError("cần --report (hoặc --dry-run)")
    if args.ref_window is not None and args.ref_window[0] >= args.ref_window[1]:
        raise ScoreError("--ref-window A,B cần A < B")
    rule = thresholds.rule(args.scenario, args.variant)
    level = args.level.split("/", 1)[0]
    if args.sim_truth and (args.reference or args.r2_points or args.sync):
        raise ScoreError("--sim-truth không dùng chung với --reference, --r2-points hay --sync")
    if args.sync and not args.reference:
        raise ScoreError("--sync cần --reference (cặp đồng bộ là của đồng hồ tệp tham chiếu)")
    if args.sim_truth and level == "XT":
        raise ScoreError("mức XT không dùng --sim-truth: tư thế mô phỏng không phải tham chiếu của xe thật")
    if rule.checks and not args.log:
        raise ScoreError(f"kịch bản {rule.key} có kiểm {', '.join(rule.checks)}: cần --log")
    return rule, level


def _check_log(args, rule: ScenarioRule, level: str, log: RunLogData) -> None:
    """Từ chối log không hợp mức thử (XT cần bo thật, MP cần mô phỏng), --sim-truth với log không phải tư thế thật của
    mô phỏng (NGUONG quy tắc 2) và 0-COMMAND với log không phải chế độ quan sát."""
    if level == "XT" and log.emulated:
        raise ScoreError(f"mức XT cần log của bo thật; log này là mô phỏng/giả lập (evidence {log.evidence}, "
                         f"cổng {log.port})")
    if level == "MP" and not log.emulated:
        raise ScoreError(f"mức MP cần log mô phỏng; log này có evidence {log.evidence}, cổng {log.port}")
    if args.sim_truth and not log.sim_truth:
        raise ScoreError(f"--sim-truth chỉ dùng với log mô phỏng có tư thế thật (gói SIM, hoặc log VehicleIO: thư mục "
                         f"_vehicle_io hay gói T9, có evidence simulation_only và pose_source {SIM_TRUTH_POSE}, hoặc bo "
                         f"ảo QEMU với evidence {QEMU_EVIDENCE} và pose_source {QEMU_PLANT_POSE}, chỉ ở mức MP); log "
                         f"này có evidence {log.evidence}, pose_source {log.pose_source}. Log của hệ thống không tự "
                         f"xác nhận nó (NGUONG quy tắc 2)")
    if args.sim_truth and log.evidence == QEMU_EVIDENCE and level != "MP":
        raise ScoreError(f"--sim-truth với log bo ảo QEMU (evidence {QEMU_EVIDENCE}) chỉ dùng ở mức MP: xe mô phỏng phía "
                         f"laptop không phải tham chiếu của mức {level} (NGUONG quy tắc 2, ĐỀ XUẤT 02/10/2026)")
    if "0-COMMAND" in rule.checks and log.mode != "OBSERVE":
        raise ScoreError(f"{rule.key} (0-COMMAND) cần log chế độ quan sát OBSERVE; log này là {log.mode}")


def _layout_and_vehicle(args, rule: ScenarioRule, log: RunLogData | None,
                        files: dict[str, str]) -> tuple[Scenario | None, VehicleConfig | None, Pose | None]:
    """Bố trí tham chiếu và cấu hình xe: --vehicle, không có thì vehicle_config của bố trí, rồi vehicle.json của gói
    (SIM hay T9). Trả (bố trí, xe, đích)."""
    layout = cfg = None
    if args.layout:
        try:
            layout = load_scenario(args.layout)
        except (OSError, ValueError, KeyError) as exc:
            raise ScoreError(f"--layout {args.layout}: {exc}") from exc
        files[str(Path(args.layout))] = _sha256(Path(args.layout))
    vehicle_path = Path(args.vehicle) if args.vehicle else (layout.vehicle_config_path if layout else None)
    if vehicle_path is None and log is not None and (log.kind == "sim_bundle" or log.package is not None):
        vehicle_path = log.data_dir / "config_snapshot" / "vehicle.json"
    if vehicle_path is not None:
        try:
            cfg = load_vehicle_config(vehicle_path)
        except (OSError, ValueError, KeyError) as exc:
            raise ScoreError(f"cấu hình xe {vehicle_path}: {exc}") from exc
        files[str(vehicle_path)] = _sha256(Path(vehicle_path))
    needs = [c for c in rule.checks if c in GEOMETRY_CHECKS]
    if needs and (layout is None or cfg is None):
        raise ScoreError(f"{', '.join(needs)} cần --layout (bố trí tham chiếu đo bằng thước, KICH_BAN mục 1.1) và "
                         f"cấu hình xe")
    goal = layout.sync_goal(cfg) if layout is not None and cfg is not None else None
    return layout, cfg, goal


def _run_notes(rule: ScenarioRule, thresholds: Thresholds, log: RunLogData | None,
               cfg: VehicleConfig | None) -> list[str]:
    """Ghi chú về tốc độ và xe của lần chạy (thêm 02/10/2026), không đổi kết luận nào: kịch bản không phải lần đỗ mà tốc
    độ mục tiêu vượt vế mục tiêu của N-V1 (các ngưỡng phản ứng của NGUONG mục 3 giả định tốc độ ≤ N-V1); xe của lần chạy
    (run.json) khác kích thước xe dùng để chấm (--vehicle, vehicle_config của bố trí)."""
    notes: list[str] = []
    if log is None:
        return notes
    limit = thresholds.limit_or_none("N-V1", "target_mps")
    target = log.max_target_mps
    if not rule.parking and limit is not None and target is not None and target > limit + 1e-9:
        notes.append(f"tốc độ mục tiêu lớn nhất {target:.3f} m/s > {limit:g} m/s: các ngưỡng phản ứng (NGUONG mục 3) "
                     f"giả định tốc độ ≤ N-V1")
    run = log.run_vehicle or {}
    if cfg is not None:
        scored = {"wheelbase_m": cfg.wheelbase, "width_m": cfg.width, "front_overhang_m": cfg.front_overhang,
                  "rear_overhang_m": cfg.rear_overhang, "max_steer_deg": math.degrees(cfg.max_steer)}
        differ = [f"{k} {run[k]:g} ≠ {scored[k]:g}" for k in VEHICLE_GEOMETRY_KEYS
                  if run.get(k) is not None and abs(run[k] - scored[k]) > 1e-6]
        if differ:
            notes.append(f"xe của lần chạy {run.get('name', '?')} khác kích thước xe dùng để chấm {cfg.name} "
                         f"({', '.join(differ)}): kiểm --vehicle/--layout")
    return notes


def _r2_track(args, cfg: VehicleConfig | None) -> tuple[ReferenceTrack, list[str]]:
    """R2: hai dấu trên trục dọc xe đo bằng thước → tư thế tâm trục sau. Sai số hướng √2·e/d, sai số vị trí e + |D1|·
    sai số hướng (dấu sau gần trục sau)."""
    x1, y1, x2, y2 = args.r2_points
    if args.r2_marks is not None:
        d1, d2 = args.r2_marks
    elif cfg is not None:
        d1, d2 = -cfg.rear_overhang, cfg.wheelbase + cfg.front_overhang
    else:
        raise ScoreError("--r2-points cần --r2-marks hoặc cấu hình xe (--layout/--vehicle)")
    if d2 <= d1:
        raise ScoreError("--r2-marks: dấu trước phải ở phía trước dấu sau (D2 > D1)")
    yaw = math.atan2(y2 - y1, x2 - x1)
    pose = Pose(x1 - d1 * math.cos(yaw), y1 - d1 * math.sin(yaw), wrap_angle(yaw))
    error = args.r2_error_cm / 100
    yaw_error = math.sqrt(2) * error / (d2 - d1)
    accuracy = ReferenceAccuracy(error + abs(d1) * yaw_error, math.degrees(yaw_error),
                                 f"R2 --r2-points, mỗi điểm ±{args.r2_error_cm:g} cm")
    notes = []
    measured = math.hypot(x2 - x1, y2 - y1)
    if abs(measured - (d2 - d1)) > 2 * error + 0.005:
        notes.append(f"hai điểm R2 cách {measured:.3f} m, khác khoảng cách hai dấu {d2 - d1:.3f} m: kiểm lại "
                     f"vị trí dấu")
    return static_reference(pose, accuracy, "R2", "; ".join(notes)), notes


@dataclass
class _References:
    """Tham chiếu của lần chấm: quỹ đạo (R1 hoặc MP), R2, phân tích và tư thế cuối đã chọn."""

    track: ReferenceTrack | None = None
    r2: ReferenceTrack | None = None
    analysis: TrackAnalysis | None = None
    final: FinalPose | None = None
    final_note: str = ""
    r1_minus_r2: dict | None = None

    def summary(self) -> dict | None:
        if self.track is None and self.r2 is None:
            return None
        out: dict = {}
        track, an = self.track, self.analysis
        if track is not None:
            out.update({"path": str(track.path) if track.path else None, "method": track.meta.method,
                        "clock": track.meta.clock, "accuracy": track.meta.accuracy.to_dict(),
                        "samples": len(track.samples), "valid_samples": len(track.valid_samples),
                        "meta_notes": track.meta.notes})
        if an is not None:
            out.update({"analysed_samples": len(an.t), "t_first": an.t[0], "t_last": an.t[-1],
                        "frame_period_s": an.frame_period_s,
                        "final_pose": an.final_pose.to_dict() if an.final_pose else None,
                        "final_spread_m": an.final_spread_m, "path_length_m": an.length_m,
                        "moving_gap": an.moving_gap, "two_marker_fraction": an.two_marker_fraction,
                        "max_residual_m": an.max_residual_m, "notes": an.notes})
        if self.r2 is not None:
            out["r2"] = {"pose": self.r2.samples[0].pose.to_dict(), "accuracy": self.r2.meta.accuracy.to_dict(),
                         "notes": self.r2.meta.notes}
        if self.r1_minus_r2 is not None:
            out["R1-R2"] = self.r1_minus_r2
        return out


def _references(args, log: RunLogData | None, cfg: VehicleConfig | None, level: str, params: AnalysisParams,
                files: dict[str, str], notes: list[str]) -> _References:
    """Đọc tham chiếu (--sim-truth, --reference, --r2-points), phân tích quỹ đạo và chọn tư thế cuối: R2 trước, rồi
    tệp tham chiếu."""
    refs = _References()
    if args.sim_truth:
        if log is None or log.runlog_rows is None:
            raise ScoreError("--sim-truth cần RunLog của lần chạy (<tên>.csv cạnh thư mục _vehicle_io, hoặc --runlog)"
                             + (f": {log.runlog_note}" if log is not None and log.runlog_note else ""))
        try:
            refs.track = reference_from_sim_rows(log.runlog_rows)
        except (KeyError, ValueError) as exc:
            raise ScoreError(f"RunLog {log.runlog_path}: {exc}") from exc
    elif args.reference:
        try:
            refs.track = read_reference(args.reference)
        except ValueError as exc:
            raise ScoreError(str(exc)) from exc
        for path in (Path(args.reference), Path(args.reference).with_suffix(".json")):
            files[str(path)] = _sha256(path)
        if refs.track.meta.method == "MP" and level == "XT":
            raise ScoreError("mức XT không dùng tệp tham chiếu phương pháp MP (tư thế mô phỏng)")
        if refs.track.meta.source.get("synthetic") is True and level in ("BT", "XT"):
            raise ScoreError("tham chiếu TỔNG HỢP chỉ dùng ở mức MP")      # T4: bộ thử overhead_synth
    if args.r2_points is not None:
        refs.r2, r2_notes = _r2_track(args, cfg)
        notes += r2_notes
    track = refs.track
    if track is not None:
        refs.analysis = analyse_reference(track, params, args.ref_window)
        notes += refs.analysis.notes
        if track.meta.accuracy.pos_max_m is None or track.meta.accuracy.yaw_max_deg is None:
            notes.append("tham chiếu chưa có độ chính xác TC-1: kết luận dựa vào nó là 'không kiểm được' (quy tắc 3)")
    an = refs.analysis
    if refs.r2 is not None:
        acc = refs.r2.meta.accuracy
        refs.final = FinalPose(refs.r2.samples[0].pose, acc.pos_max_m, math.radians(acc.yaw_max_deg), "R2")
        if an is not None and an.final_pose is not None:
            a, b = an.final_pose, refs.r2.samples[0].pose
            refs.r1_minus_r2 = {"dx_m": a.x - b.x, "dy_m": a.y - b.y, "dist_m": a.distance_to(b),
                                "dyaw_deg": math.degrees(wrap_angle(a.yaw - b.yaw))}
    elif an is not None and an.final_pose is not None:
        acc = track.meta.accuracy
        refs.final = FinalPose(an.final_pose, acc.pos_max_m,
                               math.radians(acc.yaw_max_deg) if acc.yaw_max_deg is not None else None,
                               track.meta.method)
    elif an is not None:
        refs.final_note = next((n for n in an.notes if "tư thế cuối" in n), "chưa có tư thế cuối")
    else:
        refs.final_note = "chưa có tham chiếu cho tư thế cuối (--reference, --r2-points hoặc --sim-truth)"
    return refs


def _sync_marks(args, log: RunLogData | None, files: dict[str, str], notes: list[str]) -> SyncMarks | None:
    """--sync-marks, không có thì `<tên>_sync_marks.csv` cạnh thư mục log. Tệp tự tìm thấy mà hỏng chỉ thành ghi chú,
    không chặn việc chấm."""
    marks = None
    if args.sync_marks:
        marks = read_sync_marks_csv(args.sync_marks)
    elif log is not None and find_sync_marks(log.data_dir) is not None:
        try:
            marks = read_sync_marks_csv(find_sync_marks(log.data_dir))
        except ScoreError as exc:
            notes.append(f"bỏ qua tệp dấu đồng bộ tự tìm thấy: {exc}")
    if marks is not None:
        files[str(marks.path)] = marks.sha256
    return marks


def _methods(args, log: RunLogData | None, track: ReferenceTrack | None, r2: bool, synced: bool) -> str:
    """phuong_phap_do: MP, R1, R2 khi dùng; R6 khi đọc log; R7 khi có đồng bộ video–log; rồi --methods."""
    methods = []
    if args.sim_truth or (track is not None and track.meta.method == "MP"):
        methods.append("MP")
    if track is not None and track.meta.method == "R1":
        methods.append("R1")
    if r2 or (track is not None and track.meta.method == "R2"):
        methods.append("R2")
    if log is not None:
        methods.append("R6")
    if synced:
        methods.append("R7")
    methods += [m.strip() for m in args.methods.split(",") if m.strip()]
    return "+".join(dict.fromkeys(methods))


def _row(args, checks: list[CheckResult], result: str, result_notes: list[str], log: RunLogData | None,
         refs: _References, synced: bool, notes: list[str], status: str) -> dict[str, str]:
    """Dòng biên bản: chỉ các cột của kiểm trong quy tắc, cộng cham/can_thiep khi người ghi tay. ghi_chu = --note, ghi
    chú của lần chấm, của từng kiểm, của đề xuất kết quả, rồi trạng thái ngưỡng."""
    row = dict.fromkeys(BIEN_BAN_FIELDS, "")
    notes = list(notes)
    if args.when:
        when = args.when
    elif log is not None:
        stamp = log.directory / ("link.json" if log.kind == "vehicle_io" else "result.json")
        when = datetime.fromtimestamp(stamp.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    else:
        when = datetime.now().strftime("%Y-%m-%d %H:%M")
        notes.append("ngay_gio là lúc chấm (không có log)")
    row.update(ma_kich_ban=args.scenario, bien_the=args.variant, lan=str(args.attempt), ngay_gio=when,
               muc_thu=args.level, ket_qua=result, nguyen_nhan=args.cause or "")
    for check in checks:
        row.update(check.cells)
    if args.touch is not None:
        row["cham"] = args.touch
    if args.intervention is not None:
        row["can_thiep"] = args.intervention
    row["phuong_phap_do"] = _methods(args, log, refs.track, refs.r2 is not None, synced)
    data_dir = log.data_dir if log is not None else (Path(args.reference).parent if args.reference else None)
    row["thu_muc_du_lieu"] = _relative(data_dir) if data_dir is not None else ""
    by_note: dict[str, list[str]] = {}                 # cùng một ghi chú cho nhiều kiểm: ghi một lần
    for check in checks:
        if check.note and check.note not in notes:
            by_note.setdefault(check.note, []).append(check.code)
    auto = notes + [f"{', '.join(codes)}: {note}" for note, codes in by_note.items()] + result_notes
    if status != "CHOT":
        auto.append("ngưỡng ĐỀ XUẤT – CHỜ CHỐT")
    ghi_chu = [args.note.strip()] if args.note.strip() else []
    ghi_chu += [n.replace("\n", " ").strip() for n in dict.fromkeys(auto) if n and n.strip()]
    row["ghi_chu"] = "; ".join(ghi_chu)
    return row


def score(args) -> Report:
    """Chấm theo các tham số dòng lệnh đã đọc. Mọi lỗi đầu vào → ScoreError trước khi ghi bất kỳ tệp nào."""
    try:
        thresholds = load_thresholds(args.thresholds)
    except (OSError, ValueError) as exc:
        raise ScoreError(f"tệp ngưỡng {args.thresholds}: {exc}") from exc
    rule, level = _check_arguments(args, thresholds)
    notes: list[str] = []
    log = load_run_log(args.log, args.runlog) if args.log else None
    files: dict[str, str] = dict(log.files) if log is not None else {}
    if log is not None:
        _check_log(args, rule, level, log)
        notes += log.notes
    layout, cfg, goal = _layout_and_vehicle(args, rule, log, files)
    notes += _run_notes(rule, thresholds, log, cfg)            # tốc độ mục tiêu, xe của lần chạy (02/10/2026)
    refs = _references(args, log, cfg, level, thresholds.analysis, files, notes)
    marks = _sync_marks(args, log, files, notes)
    perf, perf_notes = build_perf_map(log, marks, thresholds.analysis)
    perf_why = "; ".join(perf_notes) if perf is None else ""      # vì sao không đổi được perf_counter (nếu cần tới)
    cmap, sync_error, pairs = None, None, []
    if refs.track is not None:
        cmap, sync_error, pairs, clock_notes = clock_map(refs.track, args.sync, log=log, perf=perf, marks=marks,
                                                         time_error=args.time_error, perf_why=perf_why)
        notes += clock_notes
    event = None
    if args.event:
        event = resolve_event(args.event, log=log, track=refs.track, analysis=refs.analysis, cmap=cmap,
                              sync_error=sync_error, perf=perf, marks=marks, time_error=args.time_error,
                              perf_why=perf_why)
    if (event is not None and event.spec.startswith(("perf:", "mark:"))) or any(p.side in ("perf", "mark")
                                                                                for p in pairs):
        notes += perf_notes                # báo về mốc perf_counter chỉ khi thật sự dùng tới
    # R7 = đồng bộ video với log: có cặp đồng bộ, hoặc mốc đọc trên video tính từ một dấu đồng bộ T14
    synced = bool(pairs) or (event is not None and event.spec.startswith("mark:"))
    ctx = _Context(rule, thresholds, args.level, log, layout, cfg, goal, refs.track, refs.analysis, refs.final,
                   refs.final_note, cmap, sync_error, event, args.sim_truth, args.touch, args.intervention,
                   args.remaining_cm, args.stop_distance_cm, args.v_max_mps)
    if ctx.trajectory and layout is not None and cfg is not None:
        ctx.clearance = min_clearance(refs.analysis, cfg, layout.obstacles)
    checks = [run_check(ctx, code) for code in rule.checks]
    # Kiểm chỉ để đề xuất ket_qua (không ghi ô). Kiểm hình học cần bố trí và xe (lần đỗ trong configs luôn có N-D1, N-D2
    # nên đã đòi --layout); N-D7 cần log. N-D4, N-D9 chạy được cả khi không có log (kịch bản chỉ ghi tay).
    decision = [run_check(ctx, code) for code in decision_checks(rule)
                if code in ABSOLUTE_CHECKS or (log is not None and (code not in GEOMETRY_CHECKS or goal is not None))]
    result, result_notes = propose_result(rule, checks, log, args.result, args.cause, decision)
    row = _row(args, checks, result, result_notes, log, refs, synced, notes, thresholds.status)
    detail_path = Path(args.detail) if args.detail else None
    if detail_path is None and log is not None:
        base = log.data_dir                                       # gói T9: cạnh gói, không nằm trong gói
        detail_path = base.with_name(f"{base.name}.cham_{args.scenario}{args.variant}_l{args.attempt}.json")
    manual = {name: getattr(args, name) for name in ("touch", "intervention", "remaining_cm", "stop_distance_cm",
                                                     "v_max_mps", "methods", "result", "cause", "note", "when")}
    detail = {
        "schema_version": DETAIL_SCHEMA_VERSION, "tool": TOOL, "git_commit": lidar_recording.git_commit(),
        "created_utc": utc_now(),
        "identity": {"ma_kich_ban": args.scenario, "bien_the": args.variant, "lan": args.attempt,
                     "muc_thu": args.level, "rule": rule.key, "checks": list(rule.checks),
                     "decision_checks": [c.code for c in decision], "max_cusps": rule.max_cusps},
        "inputs": {"files": [{"path": p, "sha256": h} for p, h in files.items()], "manual": manual,
                   "event": args.event, "sync": [asdict(p) for p in args.sync], "time_error_s": args.time_error,
                   "ref_window": args.ref_window, "sim_truth": args.sim_truth, "r2_points": args.r2_points,
                   "r2_marks": args.r2_marks, "r2_error_cm": args.r2_error_cm},
        "thresholds": {"path": str(thresholds.path), "sha256": thresholds.sha256, "status": thresholds.status,
                       "reference_ratio": thresholds.reference_ratio, "analysis": asdict(thresholds.analysis)},
        "log": log.summary() if log is not None else None, "reference": refs.summary(),
        "clock_map": cmap.summary() if cmap is not None else None, "sync_error_s": sync_error,
        "sync_pairs": [asdict(p) for p in pairs], "perf_map": perf.summary() if perf is not None else None,
        "perf_map_notes": perf_notes, "sync_marks": str(marks.path) if marks is not None else None,
        "event": asdict(event) if event is not None else None,
        "clearance": dict(zip(("min_m", "obstacle", "t_ref"), ctx.clearance)) if ctx.clearance else None,
        "checks": [asdict(c) for c in checks], "decision_checks": [asdict(c) for c in decision],
        "result": {"ket_qua": result, "manual": args.result, "notes": result_notes},
        "row": row, "notes": notes,
    }
    lines = [c.line() for c in checks]
    lines += [f"(chỉ để đề xuất ket_qua, không ghi ô) {c.line()}" for c in decision
              if rule.parking or c.verdict == KHONG_DAT]
    lines.append(f"ket_qua đề xuất: {result or '(để trống: người chấm chọn)'}")
    return Report(rule, checks, row, _jsonable(detail), lines, Path(args.report) if args.report else None,
                  detail_path)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:              # --help (0) hoặc lỗi tham số (2, đã in 'LỖI: …')
        return int(exc.code or 0)
    try:
        report = score(args)
        if not args.dry_run:
            _check_report(report.report_path, report.row, args.replace)
    except ScoreError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2
    for line in report.lines:
        print(line)
    if args.dry_run:
        print("--dry-run: không ghi tệp nào")
        return 0
    try:
        write_row(report.report_path, report.row, args.replace)
    except ScoreError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2
    print(f"đã ghi dòng biên bản vào {report.report_path}")
    if report.detail_path is not None:
        try:
            report.detail_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(report.detail_path, report.detail)
        except (OSError, ValueError) as exc:
            print(f"LỖI: đã ghi dòng biên bản nhưng không ghi được tệp chi tiết {report.detail_path}: {exc}",
                  file=sys.stderr)
            return 1
        print(f"đã ghi tệp chi tiết {report.detail_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
