"""Tệp tư thế tham chiếu độc lập (R1, R2, MP): hợp đồng giữa công cụ trích tư thế từ video (T4) và công cụ chấm
một lần chạy (T5, `evaluation/score_run.py`). Thêm 02/10/2026 (docs/KICH_BAN_NGHIEM_THU.md mục 3.8, mục 7).

Một tệp tham chiếu gồm `<tên>.csv` (mỗi khung video một dòng) và tệp mô tả `<tên>.json` cùng gốc tên
(`sidecar_path`). Gợi ý nơi lưu: `runs/nghiem_thu/<ngay>/<ma>_l<lan>/tu_the_tham_chieu.csv` (thư mục `runs/` bị git
bỏ qua).

CSV: UTF-8 không BOM, dấu phẩy, dấu chấm thập phân, có dòng tiêu đề, các dòng theo thứ tự thời gian.

- `t_s`: giây, thời điểm chụp THẬT của khung theo đồng hồ ghi trong tệp mô tả (không dùng số khung/s danh định);
  tăng ngặt.
- `frame`: số thứ tự khung trong video gốc (tùy chọn).
- `x_m`, `y_m`: mét, hệ sa bàn (KICH_BAN mục 3.3). `yaw_deg`: độ, dương ngược chiều kim đồng hồ từ trục +x; số hữu hạn
  bất kỳ, khi đọc được đưa về (−180, 180].
- `n_markers`: 0..2, số marker thấy (tùy chọn, chỉ để báo). `residual_m`: sai số dư của phép khớp, ≥ 0 (tùy chọn).
- `valid`: 1 hoặc 0. 0 = công cụ trích không tin khung này; khi đó x, y, hướng để trống được.

Điểm đo là tâm trục sau, đã bù độ cao marker (mục 3.6). Cột bắt buộc: t_s, x_m, y_m, yaw_deg, valid; cột lạ bị bỏ
qua. Bộ ghi làm tròn t 4 chữ số, x/y 5, hướng 3.

Đồng hồ (`clock` của tệp mô tả):

- `t_session`: thời gian phiên của log, dùng thẳng.
- `t_io`: đồng hồ VehicleIO của lần chạy; t_session = t_io − t0 (t0 lấy từ khóa `clock` của link.json, hoặc trung
  vị t_io − t_session của telemetry.csv với log cũ).
- `perf_counter` (perf_counter thô của chính laptop chạy phiên) và `video` (giây tính từ khung đầu) cần cặp đồng bộ
  R7 (`sync`, hoặc `--sync` của công cụ chấm), ví dụ dấu đồng bộ T14. Riêng `perf_counter` với bo chạy thời gian thực
  thì đổi được bằng khóa `clock` của link.json (T13).

Mỗi cặp trong `sync` ghi `t_ref_s` và đúng một trong `t_session_s`, `t_io_s`, `t_perf_s` (perf_counter của laptop)
hoặc `mark` (số thứ tự dấu SYNC_MARK trong tệp dấu đồng bộ T14).

`accuracy` lấy từ biên bản TC-1 (mục 3.7). `pos_max_m`/`yaw_max_deg` null nghĩa là chưa làm TC-1: mọi kết luận dựa
vào R1 thành "không kiểm được" (NGUONG quy tắc 3). Phương pháp `MP` là tư thế thật của mô phỏng
(`reference_from_sim_rows`), không phải phép đo; chỉ dùng ở mức MP và xe ảo của BT.

Mới kiểm bằng dữ liệu tổng hợp và lần chạy mô phỏng (tests/test_reference_pose.py); chưa có tệp nào từ video thật.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import statistics

from autopark.domain.types import Pose, wrap_angle
from autopark.perception.paths import atomic_write_json

SCHEMA_VERSION = 1
KIND = "tu_the_tham_chieu"
METHODS = ("R1", "R2", "MP")
CLOCKS = ("t_session", "t_io", "perf_counter", "video")
COORDINATE_FRAME = "sa_ban"
POINT = "tam_truc_sau"
CSV_FIELDS = ["t_s", "frame", "x_m", "y_m", "yaw_deg", "n_markers", "residual_m", "valid"]
REQUIRED_COLUMNS = ("t_s", "x_m", "y_m", "yaw_deg", "valid")
META_KEYS = ("schema_version", "kind", "method", "clock", "coordinate_frame", "point", "accuracy", "sync",
             "sync_error_s", "notes", "source", "tool", "created_utc")
REQUIRED_META_KEYS = ("schema_version", "kind", "method", "clock", "coordinate_frame", "point", "accuracy")
ACCURACY_KEYS = ("pos_max_m", "yaw_max_deg", "pos_median_m", "yaw_median_deg", "source")
# Khóa phía "phiên" của một cặp đồng bộ trong tệp mô tả → loại của cặp
SYNC_SIDE_KEYS = {"t_session_s": "session", "t_io_s": "io", "t_perf_s": "perf", "mark": "mark"}
SIM_TRUTH_SOURCE = "tư thế thật của mô phỏng"


def _fail(where, problem: str):
    raise ValueError(f"Tệp tham chiếu {where}: {problem}")


@dataclass(frozen=True)
class ReferenceSample:
    """Một khung: thời điểm theo đồng hồ của tệp và tư thế tâm trục sau (None khi khung không hợp lệ)."""

    t: float
    pose: Pose | None
    frame: int | None = None
    n_markers: int | None = None
    residual_m: float | None = None

    @property
    def valid(self) -> bool:
        return self.pose is not None


@dataclass(frozen=True)
class ReferenceAccuracy:
    """Sai số của tham chiếu, đo ở TC-1 (lớn nhất là số dùng cho quy tắc 3). None = chưa đo."""

    pos_max_m: float | None
    yaw_max_deg: float | None
    source: str = ""
    pos_median_m: float | None = None
    yaw_median_deg: float | None = None

    def to_dict(self) -> dict:
        return {"pos_max_m": self.pos_max_m, "yaw_max_deg": self.yaw_max_deg, "pos_median_m": self.pos_median_m,
                "yaw_median_deg": self.yaw_median_deg, "source": self.source}


@dataclass(frozen=True)
class SyncPair:
    """Cặp đồng bộ: `t_ref` trên đồng hồ của tệp tham chiếu ứng với `value` ở phía log.

    `side`: `session` (t_session), `io` (đồng hồ VehicleIO), `perf` (perf_counter của laptop) hoặc `mark` (số thứ tự
    dấu SYNC_MARK của tệp dấu đồng bộ T14; `value` là số nguyên)."""

    t_ref: float
    value: float
    side: str = "session"
    note: str = ""

    def to_dict(self) -> dict:
        key = {side: key for key, side in SYNC_SIDE_KEYS.items()}[self.side]
        return {"t_ref_s": self.t_ref, key: int(self.value) if self.side == "mark" else self.value,
                "note": self.note}


def _number(value, name: str, where, *, minimum: float | None = None, allow_none: bool = False) -> float | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(where, f"{name} phải là số (nhận {value!r})")
    number = float(value)
    if not math.isfinite(number) or (minimum is not None and number < minimum):
        _fail(where, f"{name} phải là số hữu hạn" + (f" ≥ {minimum:g}" if minimum is not None else "")
              + f" (nhận {value!r})")
    return number


def _sync_pair(entry, where) -> SyncPair:
    if not isinstance(entry, dict):
        _fail(where, f"mỗi cặp trong sync phải là object (nhận {entry!r})")
    unknown = sorted(set(entry) - {"t_ref_s", "note", *SYNC_SIDE_KEYS})
    if unknown:
        _fail(where, f"cặp sync có khóa lạ {', '.join(unknown)}")
    sides = [key for key in SYNC_SIDE_KEYS if key in entry]
    if "t_ref_s" not in entry or len(sides) != 1:
        _fail(where, "mỗi cặp sync cần t_ref_s và đúng một trong " + ", ".join(SYNC_SIDE_KEYS))
    key = sides[0]
    if key == "mark":
        mark = entry[key]
        if isinstance(mark, bool) or not isinstance(mark, int) or mark < 1:
            _fail(where, f"mark của cặp sync phải là số nguyên ≥ 1 (nhận {mark!r})")
        value = float(mark)
    else:
        value = _number(entry[key], key, where)
    note = entry.get("note", "")
    if not isinstance(note, str):
        _fail(where, "note của cặp sync phải là chuỗi")
    return SyncPair(_number(entry["t_ref_s"], "t_ref_s", where), value, SYNC_SIDE_KEYS[key], note)


@dataclass(frozen=True)
class ReferenceMeta:
    """Nội dung tệp mô tả `<tên>.json` (khóa tiếng Anh như configs/*.json)."""

    method: str
    clock: str
    accuracy: ReferenceAccuracy
    sync: tuple[SyncPair, ...] = ()
    sync_error_s: float | None = None
    notes: str = ""
    source: dict = field(default_factory=dict)
    tool: str = ""
    created_utc: str = ""

    def to_dict(self) -> dict:
        return {"schema_version": SCHEMA_VERSION, "kind": KIND, "method": self.method, "clock": self.clock,
                "coordinate_frame": COORDINATE_FRAME, "point": POINT, "accuracy": self.accuracy.to_dict(),
                "sync": [pair.to_dict() for pair in self.sync], "sync_error_s": self.sync_error_s,
                "notes": self.notes, "source": dict(self.source), "tool": self.tool, "created_utc": self.created_utc}

    @classmethod
    def from_dict(cls, d, where="") -> "ReferenceMeta":
        """Đọc chặt: khóa lạ, thiếu khóa bắt buộc hay giá trị ngoài miền đều ném ValueError có tên tệp."""
        if not isinstance(d, dict):
            _fail(where, "tệp mô tả phải là một object JSON")
        unknown = sorted(set(d) - set(META_KEYS))
        if unknown:
            _fail(where, f"tệp mô tả có khóa lạ {', '.join(unknown)}")
        missing = [key for key in REQUIRED_META_KEYS if key not in d]
        if missing:
            _fail(where, f"tệp mô tả thiếu khóa {', '.join(missing)}")
        if d["schema_version"] != SCHEMA_VERSION:
            _fail(where, f"schema_version {d['schema_version']!r} không hỗ trợ (cần {SCHEMA_VERSION})")
        if d["kind"] != KIND:
            _fail(where, f"kind phải là {KIND!r} (nhận {d['kind']!r})")
        if d["method"] not in METHODS:
            _fail(where, f"method {d['method']!r} không hỗ trợ (cần một trong {', '.join(METHODS)})")
        if d["clock"] not in CLOCKS:
            _fail(where, f"clock {d['clock']!r} không hỗ trợ (cần một trong {', '.join(CLOCKS)})")
        if d["coordinate_frame"] != COORDINATE_FRAME or d["point"] != POINT:
            _fail(where, f"chỉ nhận coordinate_frame {COORDINATE_FRAME!r} và point {POINT!r}")
        acc = d["accuracy"]
        if not isinstance(acc, dict):
            _fail(where, "accuracy phải là object")
        unknown = sorted(set(acc) - set(ACCURACY_KEYS))
        if unknown:
            _fail(where, f"accuracy có khóa lạ {', '.join(unknown)}")
        if "pos_max_m" not in acc or "yaw_max_deg" not in acc:
            _fail(where, "accuracy cần pos_max_m và yaw_max_deg (null khi chưa làm TC-1)")
        source = acc.get("source", "")
        if not isinstance(source, str):
            _fail(where, "accuracy.source phải là chuỗi")
        accuracy = ReferenceAccuracy(
            _number(acc["pos_max_m"], "accuracy.pos_max_m", where, minimum=0.0, allow_none=True),
            _number(acc["yaw_max_deg"], "accuracy.yaw_max_deg", where, minimum=0.0, allow_none=True),
            source,
            _number(acc.get("pos_median_m"), "accuracy.pos_median_m", where, minimum=0.0, allow_none=True),
            _number(acc.get("yaw_median_deg"), "accuracy.yaw_median_deg", where, minimum=0.0, allow_none=True))
        pairs = d.get("sync", [])
        if not isinstance(pairs, list):
            _fail(where, "sync phải là danh sách")
        for key in ("notes", "tool", "created_utc"):
            if not isinstance(d.get(key, ""), str):
                _fail(where, f"{key} phải là chuỗi")
        source = d.get("source", {})
        if not isinstance(source, dict):
            _fail(where, "source phải là object")
        return cls(d["method"], d["clock"], accuracy, tuple(_sync_pair(p, where) for p in pairs),
                   _number(d.get("sync_error_s"), "sync_error_s", where, minimum=0.0, allow_none=True),
                   d.get("notes", ""), dict(source), d.get("tool", ""), d.get("created_utc", ""))


@dataclass
class ReferenceTrack:
    samples: list[ReferenceSample]
    meta: ReferenceMeta
    path: Path | None = None

    @property
    def valid_samples(self) -> list[ReferenceSample]:
        return [s for s in self.samples if s.pose is not None]

    @property
    def has_trajectory(self) -> bool:
        """R2 chỉ có tư thế đứng yên; quỹ đạo cần R1 hoặc MP với ít nhất hai mẫu hợp lệ."""
        return self.meta.method != "R2" and len(self.valid_samples) >= 2


def sidecar_path(csv_path) -> Path:
    return Path(csv_path).with_suffix(".json")


def _check_times(samples: list[ReferenceSample], where) -> None:
    previous = None
    for sample in samples:
        t = round(sample.t, 4)
        if not math.isfinite(sample.t) or (previous is not None and t <= previous):
            _fail(where, f"t_s phải hữu hạn và tăng ngặt sau khi làm tròn 4 chữ số (t = {sample.t!r})")
        previous = t


def write_reference(csv_path, samples: list[ReferenceSample], meta: ReferenceMeta) -> tuple[Path, Path]:
    """Ghi `<tên>.csv` và tệp mô tả `<tên>.json`; trả (csv, json)."""
    path = Path(csv_path)
    if not any(s.valid for s in samples):
        _fail(path, "không có mẫu hợp lệ nào để ghi")
    _check_times(samples, path)
    ReferenceMeta.from_dict(meta.to_dict(), path)          # cùng luật như khi đọc
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_FIELDS)
        for s in samples:
            pose = s.pose
            writer.writerow([f"{s.t:.4f}", "" if s.frame is None else int(s.frame),
                             "" if pose is None else f"{pose.x:.5f}", "" if pose is None else f"{pose.y:.5f}",
                             "" if pose is None else f"{math.degrees(pose.yaw):.3f}",
                             "" if s.n_markers is None else int(s.n_markers),
                             "" if s.residual_m is None else f"{s.residual_m:.5f}", 1 if pose is not None else 0])
    side = sidecar_path(path)
    atomic_write_json(side, meta.to_dict())
    return path, side


def _cell_float(text: str, name: str, where, line: int, *, minimum: float | None = None) -> float | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        _fail(where, f"dòng {line}: {name} không phải số ({text!r})")
    if not math.isfinite(number) or (minimum is not None and number < minimum):
        _fail(where, f"dòng {line}: {name} phải hữu hạn" + (f" và ≥ {minimum:g}" if minimum is not None else "")
              + f" ({text!r})")
    return number


def _cell_int(text: str, name: str, where, line: int, *, low: int | None = None,
              high: int | None = None) -> int | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        number = int(text)
    except ValueError:
        _fail(where, f"dòng {line}: {name} phải là số nguyên ({text!r})")
    if (low is not None and number < low) or (high is not None and number > high):
        _fail(where, f"dòng {line}: {name} ngoài miền {low}..{high} ({number})")
    return number


def read_reference(csv_path) -> ReferenceTrack:
    """Đọc tệp tham chiếu và tệp mô tả. Mọi vấn đề ném ValueError('Tệp tham chiếu <đường dẫn>: <vấn đề>')."""
    path = Path(csv_path)
    side = sidecar_path(path)
    if not path.exists():
        _fail(path, "không có tệp")
    if not side.exists():
        _fail(path, f"thiếu tệp mô tả {side.name} (cùng tên, đuôi .json)")
    try:
        data = json.loads(side.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        _fail(path, f"tệp mô tả {side.name} không đọc được: {exc}")
    meta = ReferenceMeta.from_dict(data, path)
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        rows = list(reader)
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        _fail(path, f"thiếu cột {', '.join(missing)}")
    samples: list[ReferenceSample] = []
    for line, row in enumerate(rows, start=2):
        t = _cell_float(row["t_s"], "t_s", path, line)
        if t is None:
            _fail(path, f"dòng {line}: thiếu t_s")
        if samples and t <= samples[-1].t:
            _fail(path, f"dòng {line}: t_s không tăng ngặt ({t:g} sau {samples[-1].t:g})")
        valid = (row["valid"] or "").strip()
        if valid not in ("0", "1"):
            _fail(path, f"dòng {line}: valid phải là 0 hoặc 1 ({valid!r})")
        pose = None
        if valid == "1":
            values = []
            for name in ("x_m", "y_m", "yaw_deg"):
                value = _cell_float(row[name], name, path, line) if (row[name] or "").strip().lower() != "nan" \
                    else None
                if value is None:
                    _fail(path, f"dòng {line}: dòng hợp lệ (valid = 1) thiếu hoặc NaN ở {name}")
                values.append(value)
            pose = Pose(values[0], values[1], wrap_angle(math.radians(values[2])))
        samples.append(ReferenceSample(
            t, pose, _cell_int(row.get("frame"), "frame", path, line),
            _cell_int(row.get("n_markers"), "n_markers", path, line, low=0, high=2),
            _cell_float(row.get("residual_m"), "residual_m", path, line, minimum=0.0)))
    if not any(s.valid for s in samples):
        _fail(path, "không có dòng hợp lệ (valid = 1)")
    return ReferenceTrack(samples, meta, path)


def static_reference(pose: Pose, accuracy: ReferenceAccuracy, method: str = "R2", notes: str = "") -> ReferenceTrack:
    """Tham chiếu một mẫu lúc đứng yên (R2: hai điểm đo bằng thước), đặt ở t = 0; không có quỹ đạo."""
    if method not in METHODS:
        raise ValueError(f"method {method!r} không hỗ trợ")
    return ReferenceTrack([ReferenceSample(0.0, pose)], ReferenceMeta(method, "t_session", accuracy, notes=notes))


def reference_from_sim_rows(rows: list[dict], tail_s: float = 1.0) -> ReferenceTrack:
    """Track MP từ các dòng RunLog (cột t, x, y, yaw_deg, speed): tư thế THẬT của xe mô phỏng, đồng hồ t_session,
    độ chính xác 0. Không phải phép đo độc lập: chỉ dùng ở mức MP và cho xe ảo của BT.

    RunLog dừng đúng lúc lần chạy kết thúc nên không có 1 s đứng yên cho tư thế cuối. Chỉ khi dòng cuối có tốc độ
    bằng 0, hàm thêm các mẫu đứng yên ở tư thế cuối trong `tail_s` giây, cách nhau bằng trung vị bước thời gian (xe mô
    phỏng không nhận lệnh nào sau lần chạy); điều này được ghi trong `meta.notes`."""
    samples: list[ReferenceSample] = []
    for row in rows:
        t = float(row["t"])
        pose = Pose(float(row["x"]), float(row["y"]), wrap_angle(math.radians(float(row["yaw_deg"]))))
        if not all(math.isfinite(v) for v in (t, pose.x, pose.y, pose.yaw)):
            raise ValueError(f"RunLog có giá trị không hữu hạn ở t = {row['t']!r}")
        if samples and t <= samples[-1].t:
            raise ValueError(f"RunLog: t không tăng ngặt ({t:g} sau {samples[-1].t:g})")
        samples.append(ReferenceSample(t, pose))
    if not samples:
        raise ValueError("RunLog rỗng: không dựng được track MP")
    notes = "Tư thế THẬT của xe mô phỏng (RunLog), không phải phép đo độc lập; chỉ dùng ở mức MP và xe ảo của BT."
    if float(rows[-1]["speed"]) == 0.0 and len(samples) >= 2 and tail_s > 0:
        dt = statistics.median(b.t - a.t for a, b in zip(samples, samples[1:]))
        count = max(1, int(round(tail_s / dt)))
        last = samples[-1]
        samples += [ReferenceSample(round(last.t + k * dt, 6), last.pose) for k in range(1, count + 1)]
        notes += (f" Thêm {count} mẫu đứng yên ({tail_s:g} s) ở tư thế cuối sau khi lần chạy kết thúc, vì xe mô phỏng "
                  f"không nhận lệnh nào sau đó; phần này không phải dữ liệu ghi.")
    meta = ReferenceMeta("MP", "t_session", ReferenceAccuracy(0.0, 0.0, SIM_TRUTH_SOURCE), notes=notes)
    return ReferenceTrack(samples, meta)
