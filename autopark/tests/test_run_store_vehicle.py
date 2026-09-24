"""Gói replay (`storage/run_store.py`) chỉ dành cho nhánh SIM: lần chạy qua VehicleIO bị từ chối rõ ràng.

Chạy trên chuỗi MÔ PHỎNG (SimVehicleIO + FirmwareModel), không mở cổng nào. Thêm tối 24/09/2026.
"""
import json
from dataclasses import replace

import pytest

from autopark.application.session import SessionState
from autopark.application.vehicle_link import DriveMode, VehicleLink
from autopark.storage import run_store
from autopark.storage.run_store import ReplayNotSupported, export_run, replay_run
from autopark.transport.vehicle_io import SIM_FIRMWARE_DEFAULT, SimIOConfig
from tests.test_session_vehicle import run_until_done, straight_session

SIM_CFG = SimIOConfig(firmware=replace(SIM_FIRMWARE_DEFAULT, boot_hold_ms=200))


@pytest.fixture(autouse=True)
def no_hardware_probe(monkeypatch):
    monkeypatch.setattr(run_store, "environment", lambda: {"test": True})   # không gọi PowerShell


@pytest.mark.parametrize("mode", [DriveMode.VEHICLE_IO, DriveMode.OBSERVE])
def test_export_refuses_a_vehicle_io_run_before_creating_anything(scenario, cfg, tmp_path, mode):
    session = straight_session(scenario, cfg)
    link = VehicleLink.simulated(mode, SIM_CFG)
    session.set_vehicle_link(link)
    session.start_run()
    if mode == DriveMode.OBSERVE:
        link.human.set(0.1, 0.0)
        session.advance(0.5)
        session.request_stop()
    run_until_done(session)
    assert session.state in (SessionState.COMPLETED, SessionState.STOPPED)
    assert session.run_snapshot["vehicle_link"]["mode"] == mode.value
    target = tmp_path / "goi"
    with pytest.raises(ReplayNotSupported, match="đi qua VehicleIO") as info:
        export_run(session, target)
    message = str(info.value)
    assert f"chế độ {mode.value}" in message and "simulation_only" in message
    assert "VehicleLink.write_logs" in message and "_vehicle_io" in message
    assert isinstance(info.value, ValueError)                    # nơi gọi cũ bắt ValueError vẫn bắt được
    assert not target.exists()                                   # không để lại gói dở
    # Log của lần chạy vẫn ghi được bằng đường đúng.
    written = link.write_logs(tmp_path / "log_vehicle_io")
    assert written["commands.csv"].exists() and written["link.json"].exists()


def test_export_refuses_when_the_run_link_is_set_even_without_the_snapshot_key(scenario, cfg, tmp_path):
    session = straight_session(scenario, cfg)
    session.set_vehicle_link(VehicleLink.simulated(DriveMode.VEHICLE_IO, SIM_CFG))
    session.start_run()
    run_until_done(session)
    del session.run_snapshot["vehicle_link"]                     # lớp phòng thủ thứ hai: dựa vào run_link
    with pytest.raises(ReplayNotSupported, match="VEHICLE_IO"):
        export_run(session, tmp_path / "goi")
    assert not (tmp_path / "goi").exists()


def test_replay_refuses_a_bundle_whose_snapshot_came_through_vehicle_io(scenario, cfg, tmp_path):
    session = straight_session(scenario, cfg)                    # nhánh SIM: đóng gói và phát lại được
    session.start_run()
    run_until_done(session)
    bundle = export_run(session, tmp_path / "sim")
    assert replay_run(bundle).state == session.state
    run_json = bundle / "config_snapshot" / "run.json"
    snapshot = json.loads(run_json.read_text(encoding="utf-8"))
    snapshot["vehicle_link"] = {"mode": "VEHICLE_IO", "evidence": "hardware_untested"}   # như gói do bản cũ ghi
    run_json.write_text(json.dumps(snapshot), encoding="utf-8")
    with pytest.raises(ReplayNotSupported, match="Không phát lại") as info:
        replay_run(bundle)
    assert "hardware_untested" in str(info.value) and "nhánh mô phỏng SIM" in str(info.value)
