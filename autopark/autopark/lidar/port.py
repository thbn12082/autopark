"""Cổng COM của RPLIDAR C1 lấy từ MỘT chỗ: `configs/thiet_bi.json`, khóa `lidar_port` (thêm 29/09/2026).

Số COM do Windows cấp theo từng máy (máy bàn tới 25/09/2026: COM4; máy bàn từ 29/09/2026: COM3), nên đổi máy thì chỉ
sửa tệp đó, không sửa mã. Giá trị `"COMx"` dùng thẳng; `"auto"` tìm bộ chuyển CP210x của C1 theo mã thiết bị (VID 10C4,
PID EA60) — lấy cổng CP210x ĐẦU TIÊN, nên đừng dùng `"auto"` khi máy cắm thêm một bo khác cũng qua CP210x.

`--port COMx` (hay `--port auto`) của từng lệnh vẫn ghi đè cho một lần chạy. `rig.may_moi` luôn tự tìm (máy mới chưa biết
số COM). Tệp được tìm theo vị trí mã nguồn, không theo thư mục đang đứng.
"""
from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "thiet_bi.json"
CP210X_VID, CP210X_PID = 0x10C4, 0xEA60
AUTO = "auto"


class LidarPortError(ValueError):
    """Không xác định được cổng LiDAR: tệp cấu hình thiếu/hỏng, hoặc `auto` mà không thấy bộ chuyển CP210x."""


def find_cp210x_port(comports=None) -> str | None:
    """Cổng COM của bộ chuyển CP210x (RPLIDAR C1) đầu tiên; None nếu không có. `comports`: danh sách giả cho test."""
    if comports is None:
        from serial.tools import list_ports
        comports = list_ports.comports()
    for port in comports:
        if getattr(port, "vid", None) == CP210X_VID and getattr(port, "pid", None) == CP210X_PID:
            return port.device
    return None


def configured_lidar_port(path: Path | str | None = None) -> str:
    """Giá trị `lidar_port` đúng như ghi trong tệp (`"COM3"` hay `"auto"`), chưa tự tìm."""
    path = CONFIG_PATH if path is None else Path(path)
    try:
        # utf-8-sig: Notepad và `Set-Content -Encoding UTF8` của PowerShell 5.1 ghi BOM ở đầu tệp
        value = json.loads(path.read_text(encoding="utf-8-sig"))["lidar_port"]
    except FileNotFoundError:
        raise LidarPortError(f"không thấy {path}: tạo tệp với {{\"lidar_port\": \"COMx\"}} hoặc truyền --port") from None
    except OSError as exc:                  # bị khóa, không có quyền, là thư mục...
        raise LidarPortError(f"không đọc được {path} ({type(exc).__name__}: {exc})") from None
    except (json.JSONDecodeError, KeyError, TypeError, UnicodeDecodeError) as exc:
        raise LidarPortError(f"{path} hỏng hoặc thiếu khóa \"lidar_port\" ({type(exc).__name__}: {exc})") from None
    if not isinstance(value, str) or not value.strip():
        raise LidarPortError(f"{path}: \"lidar_port\" phải là chuỗi như \"COM3\" hoặc \"auto\" (đang là {value!r})")
    return value.strip()


def lidar_port(port: str | None = None, *, path: Path | str | None = None, comports=None) -> str:
    """Cổng sẽ mở: `port` nếu người dùng truyền, không thì theo tệp cấu hình; `"auto"` (ở đâu cũng vậy) → tự tìm CP210x."""
    value = (port or "").strip() or configured_lidar_port(path)
    if value.lower() != AUTO:
        return value
    found = find_cp210x_port(comports)
    if found is None:
        raise LidarPortError("lidar_port = \"auto\" nhưng không thấy bộ chuyển CP210x (VID 10C4, PID EA60): cắm LiDAR, "
                             "cài driver CP210x, hoặc ghi số COM vào configs/thiet_bi.json")
    return found
