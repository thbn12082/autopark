"""Nạp/lưu cấu hình xe và kịch bản sa bàn dạng JSON.

Đường dẫn cấu hình xe trong kịch bản là tương đối so với file kịch bản, để cả
thư mục `scenarios/` và `configs/` quản lý được bằng Git.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from autopark.domain.types import Scenario, VehicleConfig


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
