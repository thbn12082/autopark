"""Kiểm số lần đổi chiều của đường trước khi cho chạy (T12, thêm 02/10/2026; DI-2 và N-D6 của docs/KICH_BAN_NGHIEM_THU.md).

Mỗi lần đổi chiều (tiến ↔ lùi) xe phải dừng hẳn rồi đi ngược: tốn thời gian và là chỗ sai số bám đường dồn lại.
`planning/portfolio.py` chỉ ƯU TIÊN đường ít đổi chiều hơn, không có giới hạn cứng. Mô-đun này so đường ĐÃ lập
(`Trajectory.n_cusps`) với một chính sách:

- `max_cusps` (mặc định None = không chặn): đường có HƠN chừng ấy lần đổi chiều thì `Session.start_run` từ chối Bắt đầu
  đỗ, trước mọi I/O với bo; đi qua `VehicleLink` thì có thêm một dòng START_TOO_MANY_CUSPS trong start_refusals.csv (GD2).
  Trạng thái giữ READY, đường giữ nguyên (xem trước vẫn được).
- `warn_cusps` (mặc định 7 = cận "kịch bản hẹp" N-D6 (b) đề xuất): hơn chừng ấy thì giao diện cảnh báo, vẫn chạy được.

Giới hạn CHƯA CHỐT (N-D6 (b) đề xuất ≤ 2 ở kịch bản rộng DO-1/2/3a/4a, ≤ 7 ở kịch bản hẹp DO-3b/4b/5/6), nên mặc định
không chặn gì. Người thử đặt cho từng lần chạy bằng `--max-cusps N` / `--warn-cusps N` (run_app.py, `ui.lidar_app`) hay
`Session(cusp_policy=...)`; trường giới hạn theo từng kịch bản trong tệp kịch bản: CHƯA CÓ.

Vì sao kiểm ở `Session.start_run`, không ở bộ lập đường: (1) planner và portfolio không đổi, nên kết quả và thời gian lập
đường (bench, ca khó, phép đo EcoQoS của giao diện) giữ nguyên; (2) DI-2 tách "không có đường" (NO_PATH/TIMEOUT) khỏi "có
đường mà không được đem chạy"; (3) `start_run` là cửa chung của mọi nhánh chạy (SIM, VEHICLE_IO, OBSERVE, "Đỗ lại").
Kết quả so (`CuspCheck.to_dict`) nằm trong `Session.run_snapshot["cusps"]` (số lần đổi chiều đã lập, cho T5). Không Qt.
Chỉ kiểm bằng test (mô phỏng, bo mô phỏng, giao diện offscreen).
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass

from autopark.planning.trajectory import Trajectory

CUSP_WARN_DEFAULT = 7      # mức cảnh báo mặc định = cận "kịch bản hẹp" N-D6 (b) đề xuất (CHƯA CHỐT)


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
    """Một đường so với một chính sách. Từ chối thì không tính là cảnh báo."""

    n_cusps: int
    max_cusps: int | None
    warn_cusps: int | None

    @property
    def refused(self) -> bool:
        return self.max_cusps is not None and self.n_cusps > self.max_cusps

    @property
    def warned(self) -> bool:
        return not self.refused and self.warn_cusps is not None and self.n_cusps > self.warn_cusps

    def describe(self) -> str:
        n = self.n_cusps
        if self.refused:
            return (f"Đường có {n} lần đổi chiều, vượt giới hạn {self.max_cusps} (N-D6, CHƯA CHỐT): không đem chạy; "
                    "đổi vị trí xuất phát/ô đỗ rồi tìm đường lại")
        if self.warned:
            return (f"Đường có {n} lần đổi chiều, nhiều hơn mức cảnh báo {self.warn_cusps} (N-D6 đề xuất ≤ 2 ở kịch bản "
                    "rộng, ≤ 7 ở kịch bản hẹp; CHƯA CHỐT); vẫn chạy được")
        return f"Đường có {n} lần đổi chiều"

    def to_dict(self) -> dict:
        return {"planned": self.n_cusps, "max_cusps": self.max_cusps, "warn_cusps": self.warn_cusps,
                "refused": self.refused, "warned": self.warned}


def check_cusps(trajectory: Trajectory, policy: CuspPolicy) -> CuspCheck:
    return CuspCheck(trajectory.n_cusps, policy.max_cusps, policy.warn_cusps)


def add_cusp_args(parser: argparse.ArgumentParser) -> None:
    """`--max-cusps N` và `--warn-cusps N`; đọc ra chính sách bằng `cusp_policy_from_args`."""
    parser.add_argument("--max-cusps", type=int, default=None, metavar="N",
                        help="từ chối Bắt đầu đỗ khi đường có hơn N lần đổi chiều (T12; giới hạn CHƯA CHỐT; mặc định "
                             "không chặn)")
    parser.add_argument("--warn-cusps", type=int, default=None, metavar="N",
                        help=f"cảnh báo khi đường có hơn N lần đổi chiều (mặc định {CUSP_WARN_DEFAULT})")


def cusp_policy_from_args(parser: argparse.ArgumentParser, args) -> CuspPolicy:
    """Chính sách từ dòng lệnh; số âm → `parser.error` (mã 2), trước khi mở cửa sổ hay thiết bị nào."""
    for flag, value in (("--max-cusps", args.max_cusps), ("--warn-cusps", args.warn_cusps)):
        if value is not None and value < 0:
            parser.error(f"{flag} phải ≥ 0 (đang là {value})")
    return CuspPolicy(args.max_cusps, CUSP_WARN_DEFAULT if args.warn_cusps is None else args.warn_cusps)
