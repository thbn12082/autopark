"""Kiểm số lần đổi chiều của đường trước khi cho chạy (T12, thêm 02/10/2026; DI-2 và N-D6 của docs/KIEM_THU_VA_LO_TRINH.md).

Mỗi lần đổi chiều (tiến ↔ lùi) xe phải dừng hẳn rồi đi ngược: tốn thời gian và là chỗ sai số bám đường dồn lại.
`planning/portfolio.py` chỉ ƯU TIÊN đường ít đổi chiều hơn, không có giới hạn cứng. Mô-đun này so đường ĐÃ lập
(`Trajectory.n_cusps`) với một chính sách:

- `max_cusps` (mặc định None = không chặn): đường có HƠN chừng ấy lần đổi chiều thì `Session.start_run` từ chối Bắt đầu
  đỗ, trước mọi I/O với bo; đi qua `VehicleLink` thì có thêm một dòng START_TOO_MANY_CUSPS trong start_refusals.csv (GD2).
  Trạng thái giữ READY, đường giữ nguyên (xem trước vẫn được).
- `warn_cusps` (mặc định 7 = cận "kịch bản hẹp" N-D6 (b) đề xuất): hơn chừng ấy thì giao diện cảnh báo, vẫn chạy được.

Giới hạn theo kịch bản nghiệm thu (thêm 02/10/2026; người dùng giao quyết định 02/10/2026 ('làm hết') theo đề xuất
N-D6 (b), các số vẫn ĐỀ XUẤT – CHỜ CHỐT): tệp sa bàn có trường `acceptance` (`AcceptanceTag` của domain/types.py, ví dụ
{"code": "DO-3", "variant": "b"}) thì giới hạn là `scenarios.<khóa>.max_cusps` của configs/nguong_nghiem_thu.json, đúng
số mà công cụ chấm (evaluation/score_run.py) dùng cho N-D6 (b): ≤ 2 ở kịch bản rộng DO-1/2/3a/4a, ≤ 7 ở kịch bản hẹp
DO-3b/4b/5/6; null (DO-3c, các nhóm khác) = chỉ báo số. Khóa tìm như `Thresholds.rule` của score_run: mã + biến thể nếu
có khóa đó, không thì mã. `read_acceptance_rule` đọc tệp ngưỡng (nhẹ, không nhập score_run); `resolve_cusp_limit` gộp
với cờ: `--max-cusps N` chỉ SIẾT thêm (giới hạn = min(N, số của kịch bản); N lớn hơn thì không dùng và giao diện báo),
`--warn-cusps` vẫn là mức cảnh báo. Tệp không gắn, và mọi công cụ không đưa tệp ngưỡng cho `Session` (phát lại, T6
fault_drill, phase0, robustness, fusion.demo), giữ đúng như trước: mặc định không chặn. Chỉ `run_app.py` và
`ui.lidar_app` đưa tệp ngưỡng; tệp chỉ được đọc lúc mở kịch bản có gắn, không đọc lúc lập đường hay trong vòng 50 Hz.
Sửa tệp ngưỡng khi giao diện đang mở thì phải mở lại kịch bản.

Vì sao kiểm ở `Session.start_run`, không ở bộ lập đường: (1) planner và portfolio không đổi, nên kết quả và thời gian lập
đường (bench, ca khó, phép đo EcoQoS của giao diện) giữ nguyên; (2) DI-2 tách "không có đường" (NO_PATH/TIMEOUT) khỏi "có
đường mà không được đem chạy"; (3) `start_run` là cửa chung của mọi nhánh chạy (SIM, VEHICLE_IO, OBSERVE, "Đỗ lại").
Kết quả so (`CuspCheck.to_dict`) nằm trong `Session.run_snapshot["cusps"]` (số lần đổi chiều đã lập, cho T5); lần chạy
của tệp gắn nghiệm thu có thêm `run_snapshot["cusp_rule"]` (`CuspLimit.to_dict`: nguồn giới hạn, khóa, đường dẫn và
sha256 của tệp ngưỡng). Không Qt. Chỉ kiểm bằng test (mô phỏng, bo mô phỏng, giao diện offscreen).
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

from autopark.domain.types import AcceptanceTag
from autopark.planning.trajectory import Trajectory

CUSP_WARN_DEFAULT = 7      # mức cảnh báo mặc định = cận "kịch bản hẹp" N-D6 (b) đề xuất (CHƯA CHỐT)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ACCEPTANCE_THRESHOLDS = PROJECT_ROOT / "configs" / "nguong_nghiem_thu.json"    # = score_run.DEFAULT_THRESHOLDS
THRESHOLD_STATUSES = ("DE_XUAT_CHO_CHOT", "CHOT")                            # = score_run.THRESHOLD_STATUSES
# Giới hạn có hiệu lực lấy từ đâu (`CuspLimit.source`): mặc định (không chặn), cờ --max-cusps, kịch bản nghiệm thu
SOURCE_DEFAULT, SOURCE_CLI, SOURCE_ACCEPTANCE = "mac_dinh", "dong_lenh", "nghiem_thu"
SOURCE_MANEUVER = "thao_tac_gan"


def _check_limit(name: str, value) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} phải là None hoặc số nguyên ≥ 0 (đang là {value!r})")


@dataclass(frozen=True)
class CuspPolicy:
    """`max_cusps`: từ chối Bắt đầu đỗ khi đường có HƠN chừng ấy lần đổi chiều (None = không chặn, mặc định).
    `warn_cusps`: cảnh báo khi HƠN chừng ấy (None = không cảnh báo)."""

    max_cusps: int | None = None
    warn_cusps: int | None = CUSP_WARN_DEFAULT

    def __post_init__(self) -> None:
        _check_limit("max_cusps", self.max_cusps)
        _check_limit("warn_cusps", self.warn_cusps)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CuspCheck:
    """Một đường so với một chính sách. Từ chối thì không tính là cảnh báo. `origin`: giới hạn từ đâu, chèn vào câu từ
    chối (`CuspLimit.origin`); rỗng = câu như trước 02/10/2026."""

    n_cusps: int
    max_cusps: int | None
    warn_cusps: int | None
    origin: str = ""

    @property
    def refused(self) -> bool:
        return self.max_cusps is not None and self.n_cusps > self.max_cusps

    @property
    def warned(self) -> bool:
        return not self.refused and self.warn_cusps is not None and self.n_cusps > self.warn_cusps

    def describe(self) -> str:
        n = self.n_cusps
        if self.refused:
            return (f"Đường có {n} lần đổi chiều, vượt giới hạn {self.max_cusps} {self.origin or '(N-D6, CHƯA CHỐT)'}: "
                    "không đem chạy; đổi vị trí xuất phát/ô đỗ rồi tìm đường lại")
        if self.warned:
            return (f"Đường có {n} lần đổi chiều, nhiều hơn mức cảnh báo {self.warn_cusps} (N-D6 đề xuất ≤ 2 ở kịch bản "
                    "rộng, ≤ 7 ở kịch bản hẹp; CHƯA CHỐT); vẫn chạy được")
        return f"Đường có {n} lần đổi chiều"

    def to_dict(self) -> dict:
        return {"planned": self.n_cusps, "max_cusps": self.max_cusps, "warn_cusps": self.warn_cusps,
                "refused": self.refused, "warned": self.warned}


def check_cusps(trajectory: Trajectory, policy: CuspPolicy, origin: str = "") -> CuspCheck:
    return CuspCheck(trajectory.n_cusps, policy.max_cusps, policy.warn_cusps, origin)


# ---------------------------------------------------------------- giới hạn theo kịch bản nghiệm thu

class AcceptanceTagError(ValueError):
    """Tệp sa bàn gắn kịch bản nghiệm thu mà tệp ngưỡng không cho được giới hạn (thiếu, hỏng, không có khóa); thông điệp
    nêu tệp ngưỡng, thẻ và các khóa gần đó."""


@dataclass(frozen=True)
class AcceptanceCuspRule:
    """Giới hạn đổi chiều của một kịch bản nghiệm thu, đọc từ tệp ngưỡng. `key`: khóa đã dùng (DO-3b; DO-2 cho thẻ
    DO-2 + p3); `max_cusps` None = chỉ báo số; `path`: tệp ngưỡng, tương đối so với thư mục dự án (posix) khi nằm trong
    dự án, không thì tuyệt đối; `sha256` của các byte đã đọc."""

    tag: AcceptanceTag
    key: str
    max_cusps: int | None
    status: str
    path: str
    sha256: str

    @property
    def basis(self) -> str:
        return "N-D6 (b), đã chốt" if self.status == "CHOT" else "N-D6 (b) đề xuất, CHƯA CHỐT"

    def to_dict(self) -> dict:
        return {"acceptance": self.tag.to_dict(), "key": self.key, "max_cusps": self.max_cusps,
                "thresholds": {"path": self.path, "sha256": self.sha256, "status": self.status}}


def _thresholds_label(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def read_acceptance_rule(tag: AcceptanceTag, path: str | Path = ACCEPTANCE_THRESHOLDS) -> AcceptanceCuspRule:
    """Giới hạn đổi chiều của kịch bản `tag` trong tệp ngưỡng `path` (mặc định configs/nguong_nghiem_thu.json).

    Đọc nhẹ mà chặt, không nhập evaluation/score_run.py (kéo theo shapely, bản ghi LiDAR…): UTF-8 (BOM được),
    schema_version 1, status thuộc THRESHOLD_STATUSES, scenarios là object; khóa tìm như `Thresholds.rule` (mã +
    biến thể nếu có khóa đó, không thì mã); mục là object; max_cusps thiếu hay null = chỉ báo số, có thì là số nguyên
    ≥ 0 (không nhận bool). Mọi lỗi thành `AcceptanceTagError`. Các phần khác của tệp (limits, analysis…) do score_run
    kiểm."""
    path = Path(path)
    where = f"Tệp ngưỡng {_thresholds_label(path)}"
    need = f"tệp sa bàn gắn nghiệm thu {tag.label} cần tệp này"
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AcceptanceTagError(f"{where}: không đọc được ({exc}); {need}") from exc
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except ValueError as exc:                   # gồm UnicodeDecodeError, json.JSONDecodeError
        raise AcceptanceTagError(f"{where}: không phải JSON UTF-8 hợp lệ ({exc}); {need}") from exc
    if not isinstance(data, dict):
        raise AcceptanceTagError(f"{where}: phải là object JSON; {need}")
    if data.get("schema_version") != 1:
        raise AcceptanceTagError(f"{where}: schema_version {data.get('schema_version')!r} không hỗ trợ (cần 1); {need}")
    if data.get("status") not in THRESHOLD_STATUSES:
        raise AcceptanceTagError(f"{where}: status {data.get('status')!r} phải là một trong {THRESHOLD_STATUSES}; "
                                 f"{need}")
    scenarios = data.get("scenarios")
    if not isinstance(scenarios, dict):
        raise AcceptanceTagError(f"{where}: scenarios phải là object; {need}")
    candidates = ([tag.label] if tag.variant else []) + [tag.code]
    key = next((k for k in candidates if k in scenarios), None)
    if key is None:
        group = tag.code.split("-", 1)[0]
        same_code = sorted(k for k in scenarios if k.startswith(tag.code))
        near = same_code or sorted(k for k in scenarios if k.startswith(group + "-"))
        hint = " (biến thể ghi ở acceptance.variant)" if same_code else ""
        raise AcceptanceTagError(f"{where}: không có kịch bản {tag.label!r} (tệp sa bàn gắn nghiệm thu); các khóa "
                                 f"{tag.code if same_code else group}: {', '.join(near) or '(không có)'}{hint}")
    entry = scenarios[key]
    if not isinstance(entry, dict):
        raise AcceptanceTagError(f"{where}: scenarios.{key} phải là object (tệp sa bàn gắn nghiệm thu {tag.label})")
    value = entry.get("max_cusps")
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
        raise AcceptanceTagError(f"{where}: scenarios.{key}.max_cusps phải là số nguyên ≥ 0 hoặc null (đang là "
                                 f"{value!r}; tệp sa bàn gắn nghiệm thu {tag.label})")
    return AcceptanceCuspRule(tag, key, value, data["status"], _thresholds_label(path), hashlib.sha256(raw).hexdigest())


@dataclass(frozen=True)
class CuspLimit:
    """Giới hạn có hiệu lực lúc Bắt đầu đỗ (`resolve_cusp_limit`). `policy`: chính sách đem so; `source`: max_cusps từ
    đâu (SOURCE_DEFAULT, SOURCE_CLI, SOURCE_ACCEPTANCE); `rule`: giới hạn của kịch bản nghiệm thu mà tệp sa bàn gắn
    (None = không gắn); `cli_max_cusps`: số của --max-cusps (None = không có cờ)."""

    policy: CuspPolicy
    source: str
    rule: AcceptanceCuspRule | None = None
    cli_max_cusps: int | None = None

    @property
    def cli_ignored(self) -> bool:
        """--max-cusps lớn hơn giới hạn của kịch bản: cờ không nới được, nên không dùng."""
        if self.source == SOURCE_MANEUVER:
            return self.cli_max_cusps is not None and self.cli_max_cusps > self.policy.max_cusps
        return (self.rule is not None and self.rule.max_cusps is not None and self.cli_max_cusps is not None
                and self.cli_max_cusps > self.rule.max_cusps)

    @property
    def origin(self) -> str:
        """Giới hạn từ đâu, cho câu từ chối (`CuspCheck.describe`); rỗng khi không gắn nghiệm thu (câu như trước)."""
        if self.source == SOURCE_MANEUVER:
            return "của thao tác gần"
        rule = self.rule
        if rule is None:
            return ""
        if self.source == SOURCE_ACCEPTANCE:
            return f"của {rule.key} ({rule.basis})"
        allowed = ": chỉ báo số" if rule.max_cusps is None else f" cho phép {rule.max_cusps}"
        return f"theo --max-cusps (kịch bản {rule.key}{allowed})"

    def short(self) -> str:
        """Đuôi ngắn cho dòng đường của giao diện; rỗng khi không gắn nghiệm thu (dòng như trước)."""
        if self.source == SOURCE_MANEUVER:
            return f"tối đa {self.policy.max_cusps} (thao tác gần)"
        rule = self.rule
        if rule is None:
            return ""
        if self.source == SOURCE_CLI:
            return f"tối đa {self.policy.max_cusps} (--max-cusps; {rule.key})"
        if self.policy.max_cusps is None:
            return f"{rule.key}: chỉ báo số"
        return f"tối đa {self.policy.max_cusps} ({rule.key})"

    def summary(self) -> str:
        """Một câu cho nhãn của thẻ Kịch bản và thanh trạng thái."""
        if self.source == SOURCE_MANEUVER:
            return f"Thao tác gần: đổi chiều tối đa {self.policy.max_cusps}"
        warn = "không cảnh báo" if self.policy.warn_cusps is None else f"cảnh báo khi hơn {self.policy.warn_cusps}"
        rule, top = self.rule, self.policy.max_cusps
        if rule is None:
            if self.source == SOURCE_CLI:
                return f"Đổi chiều tối đa {top} theo --max-cusps; {warn}"
            return f"Đổi chiều: không chặn (T12, giới hạn CHƯA CHỐT); {warn}"
        head = f"Nghiệm thu {rule.key}: đổi chiều"
        if self.source == SOURCE_CLI:
            allowed = "chỉ báo số" if rule.max_cusps is None else f"cho phép {rule.max_cusps}"
            return f"{head} tối đa {top} theo --max-cusps (kịch bản {allowed})"
        if top is None:
            return f"{head} chỉ báo số, không chặn ({rule.basis}); {warn}"
        text = f"{head} tối đa {top} ({rule.basis})"
        if self.cli_ignored:
            text += f"; --max-cusps {self.cli_max_cusps} lớn hơn nên không dùng"
        return text

    def to_dict(self) -> dict:
        """Cho `Session.run_snapshot["cusp_rule"]` (chỉ lần chạy của tệp gắn nghiệm thu)."""
        data = {"source": self.source, "max_cusps": self.policy.max_cusps, "warn_cusps": self.policy.warn_cusps,
                "cli_max_cusps": self.cli_max_cusps}
        rule = self.rule
        if rule is not None:
            data.update(acceptance=rule.tag.to_dict(), key=rule.key, rule_max_cusps=rule.max_cusps,
                        thresholds={"path": rule.path, "sha256": rule.sha256, "status": rule.status})
        return data


def resolve_cusp_limit(base: CuspPolicy, rule: AcceptanceCuspRule | None) -> CuspLimit:
    """Gộp chính sách của cờ hay hàm dựng (`base`; base.max_cusps khác None = có --max-cusps) với giới hạn của kịch bản
    nghiệm thu (`rule`, None = tệp không gắn). Cờ chỉ siết thêm: giới hạn = min(cờ, số của kịch bản); kịch bản chỉ báo
    số (null) thì cờ áp như khi không gắn. Mức cảnh báo luôn lấy từ `base`."""
    cli = base.max_cusps
    if rule is None:
        return CuspLimit(base, SOURCE_DEFAULT if cli is None else SOURCE_CLI, None, cli)
    if cli is not None and (rule.max_cusps is None or cli < rule.max_cusps):
        return CuspLimit(base, SOURCE_CLI, rule, cli)
    return CuspLimit(CuspPolicy(rule.max_cusps, base.warn_cusps), SOURCE_ACCEPTANCE, rule, cli)


def add_cusp_args(parser: argparse.ArgumentParser) -> None:
    """`--max-cusps N` và `--warn-cusps N`; đọc ra chính sách bằng `cusp_policy_from_args`."""
    parser.add_argument("--max-cusps", type=int, default=None, metavar="N",
                        help="từ chối chạy khi đường có hơn N lần đổi chiều; chỉ siết thêm giới hạn thao tác gần "
                             "và giới hạn acceptance (nếu có trong configs/nguong_nghiem_thu.json)")
    parser.add_argument("--warn-cusps", type=int, default=None, metavar="N",
                        help=f"cảnh báo khi đường có hơn N lần đổi chiều (mặc định {CUSP_WARN_DEFAULT})")


def cusp_policy_from_args(parser: argparse.ArgumentParser, args) -> CuspPolicy:
    """Chính sách từ dòng lệnh; số âm → `parser.error` (mã 2), trước khi mở cửa sổ hay thiết bị nào."""
    for flag, value in (("--max-cusps", args.max_cusps), ("--warn-cusps", args.warn_cusps)):
        if value is not None and value < 0:
            parser.error(f"{flag} phải ≥ 0 (đang là {value})")
    return CuspPolicy(args.max_cusps, CUSP_WARN_DEFAULT if args.warn_cusps is None else args.warn_cusps)
