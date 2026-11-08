"""Giới hạn đổi chiều của thao tác gần; tùy chọn người dùng chỉ được siết thêm."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from autopark.planning.trajectory import Trajectory

CUSP_WARN_DEFAULT = 7
SOURCE_CLI = "dong_lenh"
SOURCE_MANEUVER = "thao_tac_gan"


def _check_limit(name: str, value) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} phải là None hoặc số nguyên ≥ 0 (đang là {value!r})")


@dataclass(frozen=True)
class CuspPolicy:
    """Giới hạn bổ sung và mức cảnh báo; None giữ giới hạn của thao tác."""

    max_cusps: int | None = None
    warn_cusps: int | None = CUSP_WARN_DEFAULT

    def __post_init__(self) -> None:
        _check_limit("max_cusps", self.max_cusps)
        _check_limit("warn_cusps", self.warn_cusps)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CuspCheck:
    """Kết quả kiểm tra số lần đổi chiều của một quỹ đạo."""

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
        if self.refused:
            origin = f" {self.origin}" if self.origin else ""
            return (f"Đường có {self.n_cusps} lần đổi chiều, vượt giới hạn {self.max_cusps}{origin}: "
                    "không đem chạy; đổi tư thế đích rồi tính thao tác lại")
        if self.warned:
            return (f"Đường có {self.n_cusps} lần đổi chiều, nhiều hơn mức cảnh báo {self.warn_cusps}; "
                    "vẫn nằm trong giới hạn cho phép")
        return f"Đường có {self.n_cusps} lần đổi chiều"

    def to_dict(self) -> dict:
        return {"planned": self.n_cusps, "max_cusps": self.max_cusps, "warn_cusps": self.warn_cusps,
                "refused": self.refused, "warned": self.warned}


def check_cusps(trajectory: Trajectory, policy: CuspPolicy, origin: str = "") -> CuspCheck:
    return CuspCheck(trajectory.n_cusps, policy.max_cusps, policy.warn_cusps, origin)


@dataclass(frozen=True)
class CuspLimit:
    """Giới hạn hiệu lực sau khi gộp kịch bản với tùy chọn người dùng."""

    policy: CuspPolicy
    source: str
    cli_max_cusps: int | None = None

    @property
    def cli_ignored(self) -> bool:
        return (self.source == SOURCE_MANEUVER and self.cli_max_cusps is not None
                and self.cli_max_cusps > self.policy.max_cusps)

    @property
    def origin(self) -> str:
        return "theo --max-cusps" if self.source == SOURCE_CLI else "của thao tác gần"

    def short(self) -> str:
        source = "--max-cusps" if self.source == SOURCE_CLI else "thao tác gần"
        return f"tối đa {self.policy.max_cusps} ({source})"

    def summary(self) -> str:
        text = f"Đổi chiều tối đa {self.policy.max_cusps} {self.origin}"
        if self.cli_ignored:
            text += f"; --max-cusps {self.cli_max_cusps} lớn hơn nên không dùng"
        return text

    def to_dict(self) -> dict:
        return {"source": self.source, "max_cusps": self.policy.max_cusps, "warn_cusps": self.policy.warn_cusps,
                "cli_max_cusps": self.cli_max_cusps}


def resolve_cusp_limit(base: CuspPolicy, maneuver_max_cusps: int) -> CuspLimit:
    """Giới hạn của kịch bản luôn có hiệu lực, kể cả khi cờ dòng lệnh lớn hơn."""
    if type(maneuver_max_cusps) is not int or maneuver_max_cusps < 0:
        raise ValueError("maneuver.max_cusps phải là số nguyên ≥ 0")
    if base.max_cusps is not None and base.max_cusps < maneuver_max_cusps:
        return CuspLimit(base, SOURCE_CLI, base.max_cusps)
    return CuspLimit(CuspPolicy(maneuver_max_cusps, base.warn_cusps), SOURCE_MANEUVER, base.max_cusps)


def add_cusp_args(parser: argparse.ArgumentParser) -> None:
    """`--max-cusps N` và `--warn-cusps N`; đọc ra chính sách bằng `cusp_policy_from_args`."""
    parser.add_argument("--max-cusps", type=int, default=None, metavar="N",
                        help="từ chối chạy khi đường có hơn N lần đổi chiều; chỉ siết thêm giới hạn thao tác gần")
    parser.add_argument("--warn-cusps", type=int, default=None, metavar="N",
                        help=f"cảnh báo khi đường có hơn N lần đổi chiều (mặc định {CUSP_WARN_DEFAULT})")


def cusp_policy_from_args(parser: argparse.ArgumentParser, args) -> CuspPolicy:
    """Chính sách từ dòng lệnh; số âm → `parser.error` (mã 2), trước khi mở cửa sổ hay thiết bị nào."""
    for flag, value in (("--max-cusps", args.max_cusps), ("--warn-cusps", args.warn_cusps)):
        if value is not None and value < 0:
            parser.error(f"{flag} phải ≥ 0 (đang là {value})")
    return CuspPolicy(args.max_cusps, CUSP_WARN_DEFAULT if args.warn_cusps is None else args.warn_cusps)
