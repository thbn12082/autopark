"""Tắt EcoQoS cho một tiến trình (thêm 30/09/2026, `autopark/power_throttling.py`): dùng cho tiến trình pytest
(`tests/conftest.py`) và cho QEMU của bo ảo. Vì sao: docs/CHUYEN_MAY_BAN.md mục 8."""
import os
import subprocess
import sys

import pytest

from autopark import power_throttling
from autopark.power_throttling import disable_power_throttling, execution_speed_throttling

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="EcoQoS chỉ có trên Windows")


def test_off_windows_nothing_is_done(monkeypatch):
    monkeypatch.setattr(power_throttling.sys, "platform", "linux")
    assert disable_power_throttling() is False
    assert disable_power_throttling(1234) is False
    assert execution_speed_throttling() is None


def _require_state(state) -> None:
    """Không đọc được trạng thái: Windows trước bản 22000 thì bỏ qua (Microsoft ghi ProcessPowerThrottling cần bản
    22000); Windows 11 thì là lỗi của autopark/power_throttling.py, phải HỎNG chứ không bỏ qua."""
    if state is None and sys.getwindowsversion().build < 22000:
        pytest.skip("Windows trước bản 22000 có thể không đọc được trạng thái EcoQoS (GetProcessInformation)")
    assert state is not None, "Windows 11 phải đọc được trạng thái EcoQoS: autopark/power_throttling.py hỏng?"


@windows_only
def test_pytest_process_runs_without_ecoqos():
    """conftest.py tắt EcoQoS cho chính tiến trình pytest, trừ khi AUTOPARK_KEEP_ECOQOS=1."""
    state = execution_speed_throttling()
    _require_state(state)
    expected = "system" if os.environ.get("AUTOPARK_KEEP_ECOQOS") == "1" else "off"
    assert state == expected


@windows_only
def test_another_process_starts_with_windows_default_and_can_be_switched_off():
    """Đúng đường QemuBoard dùng cho QEMU: tắt theo pid. Tiến trình con KHÔNG thừa hưởng trạng thái của pytest."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        before = execution_speed_throttling(child.pid)
        _require_state(before)
        assert before == "system"
        assert disable_power_throttling(child.pid) is True
        assert execution_speed_throttling(child.pid) == "off"
    finally:
        child.kill()
        child.wait()


@windows_only
def test_process_that_cannot_be_opened_gives_false_and_none():
    """pid 0 (System Idle Process) không mở được: không ném lỗi, chỉ báo không làm được."""
    assert disable_power_throttling(0) is False
    assert execution_speed_throttling(0) is None
