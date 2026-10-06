"""Nạp/lưu cấu hình xe và kịch bản sa bàn dạng JSON.

Đường dẫn cấu hình xe trong kịch bản là tương đối so với file kịch bản, để cả
thư mục `scenarios/` và `configs/` quản lý được bằng Git.

Tệp xe có kiểm tra (02/10/2026, chuyển từ evaluation/sensitivity.py, nơi đó vẫn xuất lại cùng tên):
`load_vehicle_config_file` trả `VehicleConfigFile` (đường dẫn tuyệt đối, cấu hình, sha256), `vehicle_config_arg` là kiểu
của cờ `--vehicle-config`. `list_vehicle_configs` liệt kê configs/vehicle_*.json (trừ tệp bo mô phỏng vehicle_io_sim*)
cho ô "Cấu hình xe" của giao diện. Xe nghiệm thu `ACCEPTANCE_VEHICLE_CONFIG` = configs/vehicle_nghiem_thu.json: như
vehicle_default.json nhưng max_speed_mps = 0,10 m/s (N-V1, ĐỀ XUẤT – CHỜ CHỐT; người dùng giao quyết định 02/10/2026
('làm hết'): cấu hình xe riêng, không đổi tệp mặc định).
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from autopark.domain.types import Scenario, VehicleConfig

CONFIGS_DIR = Path(__file__).resolve().parents[2] / "configs"
DEFAULT_VEHICLE_CONFIG = CONFIGS_DIR / "vehicle_default.json"
ACCEPTANCE_VEHICLE_CONFIG = CONFIGS_DIR / "vehicle_nghiem_thu.json"     # 0,10 m/s; bo: vehicle_io_sim_nghiem_thu.json
VEHICLE_CONFIG_GLOB = "vehicle_*.json"
SIM_IO_CONFIG_PREFIX = "vehicle_io_sim"          # configs/vehicle_io_sim*.json là cấu hình bo mô phỏng, không phải xe

REQUIRED_VEHICLE_KEYS = ("name", "wheelbase_m", "width_m", "front_overhang_m", "rear_overhang_m", "max_steer_deg",
                         "max_speed_mps", "max_accel_mps2", "max_decel_mps2", "max_steer_rate_deg_s")


def load_vehicle_config(path: str | Path) -> VehicleConfig:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return VehicleConfig.from_dict(data)


def save_vehicle_config(cfg: VehicleConfig, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cfg.to_dict(), f, ensure_ascii=False, indent=2)
    return path


# ---------------------------------------------------------------- nạp cấu hình xe có kiểm tra (dùng chung cho CLI)

class VehicleConfigError(ValueError):
    """Tệp cấu hình xe không dùng được; thông điệp nói rõ tệp nào và vì sao."""


@dataclass(frozen=True)
class VehicleConfigFile:
    """Cấu hình xe đã nạp, kèm đường dẫn tuyệt đối và sha256 của tệp để ghi vào bằng chứng."""

    path: Path
    cfg: VehicleConfig
    sha256: str

    def describe(self) -> dict[str, Any]:
        return {"path": str(self.path), "sha256": self.sha256, "config": self.cfg.to_dict()}


def load_vehicle_config_file(path: str | Path) -> VehicleConfigFile:
    """Nạp và kiểm một tệp cấu hình xe JSON; mọi lỗi thành `VehicleConfigError` có tên tệp và lý do."""
    p = Path(path)
    if not p.exists():
        raise VehicleConfigError(f"không thấy tệp cấu hình xe '{p}' (thư mục đang chạy: {Path.cwd()})")
    if not p.is_file():
        raise VehicleConfigError(f"'{p}' không phải một tệp cấu hình xe (là thư mục?)")
    raw = p.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VehicleConfigError(f"'{p}' không phải JSON UTF-8 hợp lệ: {exc}") from exc
    if not isinstance(data, dict):
        raise VehicleConfigError(f"'{p}' phải chứa một đối tượng JSON {{...}}, đang là {type(data).__name__}")
    missing = [key for key in REQUIRED_VEHICLE_KEYS if key not in data]
    if missing:
        raise VehicleConfigError(f"'{p}' thiếu khóa: {', '.join(missing)} (xem configs/vehicle_default.json)")
    try:
        cfg = VehicleConfig.from_dict(data)
    except (TypeError, ValueError) as exc:
        raise VehicleConfigError(f"'{p}': {exc}") from exc
    return VehicleConfigFile(p.resolve(), cfg, hashlib.sha256(raw).hexdigest())


def vehicle_config_arg(text: str) -> VehicleConfigFile:
    """Kiểu cho argparse: tệp hỏng thành thông báo rõ ràng và mã thoát 2, trước khi công cụ làm việc gì khác."""
    try:
        return load_vehicle_config_file(text)
    except VehicleConfigError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def path_key(path: str | Path) -> str:
    """Khóa so hai đường dẫn tệp: tuyệt đối, chuẩn hóa hoa/thường và dấu gạch theo hệ điều hành (Windows không phân
    biệt hoa/thường)."""
    return os.path.normcase(str(Path(path).resolve()))


def list_vehicle_configs(configs_dir: str | Path = CONFIGS_DIR) -> tuple[list[VehicleConfigFile], list[str]]:
    """Các tệp xe `vehicle_*.json` trong `configs_dir` (bỏ tệp bo mô phỏng vehicle_io_sim*.json), nạp có kiểm tra.

    Trả (tệp dùng được, lỗi): tệp hỏng không làm hỏng cả danh sách mà thành một dòng '<tên>: <lý do>'. Thứ tự:
    vehicle_default.json, vehicle_nghiem_thu.json, rồi theo tên. Thư mục không có thì cả hai danh sách rỗng."""
    folder = Path(configs_dir)
    first = (DEFAULT_VEHICLE_CONFIG.name, ACCEPTANCE_VEHICLE_CONFIG.name)
    paths = sorted((p for p in folder.glob(VEHICLE_CONFIG_GLOB) if not p.name.startswith(SIM_IO_CONFIG_PREFIX)),
                   key=lambda p: (first.index(p.name) if p.name in first else len(first), p.name))
    found: list[VehicleConfigFile] = []
    problems: list[str] = []
    for path in paths:
        try:
            found.append(load_vehicle_config_file(path))
        except (VehicleConfigError, OSError) as exc:
            problems.append(f"{path.name}: {exc}")
    return found, problems


def load_scenario(path: str | Path) -> Scenario:
    path = Path(path).resolve()
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    scenario = Scenario.from_dict(data)
    scenario.vehicle_config_path = (path.parent / scenario.vehicle_config).resolve()
    return scenario


def save_scenario(scenario: Scenario, path: str | Path) -> Path:
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if scenario.vehicle_config_path is not None:
        try:
            rel = os.path.relpath(scenario.vehicle_config_path, path.parent)
        except ValueError:
            # Windows: kịch bản và cấu hình xe nằm trên hai ổ đĩa khác nhau, không có đường dẫn tương đối
            rel = str(Path(scenario.vehicle_config_path).resolve())
        scenario.vehicle_config = Path(rel).as_posix()
    with path.open("w", encoding="utf-8") as f:
        json.dump(scenario.to_dict(), f, ensure_ascii=False, indent=2)
    return path
