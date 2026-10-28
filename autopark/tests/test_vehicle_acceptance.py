"""Xe nghiệm thu 0,10 m/s và bo mô phỏng đi cùng (thêm 02/10/2026; người dùng giao quyết định 02/10/2026 ('làm hết'):
cấu hình xe riêng configs/vehicle_nghiem_thu.json, tệp mặc định không đổi; N-V1 vẫn ĐỀ XUẤT – CHỜ CHỐT).

Không Qt, không cổng, không camera: nhánh SIM giai đoạn 0 và bo mô phỏng (SimVehicleIO + FirmwareModel). Mọi tệp tạm
ghi trong tmp_path. Đây là kiểm phần mềm trên mô phỏng, không phải số đo xe.
"""
import copy
from dataclasses import replace
import json
import os
import shutil

import pytest

from autopark.application.session import Session, SessionError, SessionState
from autopark.application.vehicle_link import DriveMode, VehicleLink
from autopark.planning.hybrid_astar import PlannerParams
from autopark.storage.scenario_store import (ACCEPTANCE_VEHICLE_CONFIG, CONFIGS_DIR, DEFAULT_VEHICLE_CONFIG,
                                            list_vehicle_configs, load_scenario, load_vehicle_config,
                                            load_vehicle_config_file)
from autopark.transport.vehicle_io import (DEFAULT_SIM_IO_NAME, SimIOConfig, SimVehicleIO, choose_sim_io_config,
                                           load_sim_io_config)
from tests.conftest import PROJECT_ROOT
from tests.test_session_vehicle import run_until_done, straight_session

ACCEPTANCE_SIM_IO = CONFIGS_DIR / "vehicle_io_sim_nghiem_thu.json"
DEFAULT_SIM_IO = CONFIGS_DIR / DEFAULT_SIM_IO_NAME
BAI_DO_XE = PROJECT_ROOT / "scenarios" / "thao_tac_cua_hep.json"


def flatten(data: dict, prefix: str = "") -> dict:
    out = {}
    for key, value in data.items():
        if isinstance(value, dict):
            out.update(flatten(value, f"{prefix}{key}."))
        else:
            out[prefix + key] = value
    return out


# ---------------------------------------------------------------------------------------------- tệp cấu hình
def test_acceptance_vehicle_equals_default_except_speed():
    acc = load_vehicle_config_file(ACCEPTANCE_VEHICLE_CONFIG).cfg
    default = load_vehicle_config(DEFAULT_VEHICLE_CONFIG)
    assert acc.max_speed == pytest.approx(0.10) and default.max_speed == pytest.approx(0.3)   # mặc định không đổi
    assert acc.name == "xe_nghiem_thu_gia_dinh" and "người dùng giao quyết định 02/10/2026" in acc.notes
    assert replace(acc, name=default.name, notes=default.notes, max_speed=default.max_speed) == default
    keys = lambda path: list(json.loads(path.read_text(encoding="utf-8")))                   # noqa: E731
    assert keys(ACCEPTANCE_VEHICLE_CONFIG) == keys(DEFAULT_VEHICLE_CONFIG)


def test_planner_default_cruise_unchanged():
    """Xe nghiệm thu chỉ kẹp tốc độ (quỹ đạo, bộ bám); tốc độ hành trình của planner giữ nguyên."""
    params = PlannerParams()
    assert params.cruise_speed == pytest.approx(0.15) and params.approach_speed == pytest.approx(0.08)


def test_acceptance_sim_board_differs_only_in_vehicle_and_speed():
    base = flatten(json.loads(DEFAULT_SIM_IO.read_text(encoding="utf-8")))
    acc = flatten(json.loads(ACCEPTANCE_SIM_IO.read_text(encoding="utf-8")))
    assert set(base) == set(acc)
    changed = {key: acc[key] for key in base if base[key] != acc[key]}
    assert set(changed) == {"notes", "vehicle_config", "firmware.max_speed_mm_s"}
    assert changed["vehicle_config"] == "vehicle_nghiem_thu.json" and changed["firmware.max_speed_mm_s"] == 100
    sim_cfg, vehicle = load_sim_io_config(ACCEPTANCE_SIM_IO)
    assert vehicle == load_vehicle_config_file(ACCEPTANCE_VEHICLE_CONFIG).cfg
    assert sim_cfg.firmware == replace(load_sim_io_config(DEFAULT_SIM_IO)[0].firmware, max_speed_mm_s=100)


def test_acceptance_board_limits_match_vehicle():
    sim_cfg, vehicle = load_sim_io_config(ACCEPTANCE_SIM_IO)
    io = SimVehicleIO(vehicle, sim_cfg)
    try:
        io.connect()
        check = io.check_limits(vehicle, emit_event=False)
        assert check.ok and check.vehicle_name == "xe_nghiem_thu_gia_dinh"
        assert io.hello.limits.max_speed_mps == pytest.approx(0.10)
    finally:
        io.close()


# ---------------------------------------------------------------------------------------------- chọn bo theo tệp xe
def test_choose_sim_io_config_pairs_real_files(monkeypatch):
    default = choose_sim_io_config(DEFAULT_VEHICLE_CONFIG, CONFIGS_DIR)
    assert default.path == DEFAULT_SIM_IO and default.matched and default.note == ""
    assert default.config == load_sim_io_config(DEFAULT_SIM_IO)[0]
    acc = choose_sim_io_config(ACCEPTANCE_VEHICLE_CONFIG, CONFIGS_DIR)
    assert acc.path == ACCEPTANCE_SIM_IO and acc.matched and acc.note == ""
    assert acc.config.firmware.max_speed_mm_s == 100
    nothing = choose_sim_io_config(None, CONFIGS_DIR)
    assert nothing.path == DEFAULT_SIM_IO and not nothing.matched and "không có tệp" in nothing.note
    monkeypatch.chdir(PROJECT_ROOT)                                # đường dẫn tương đối, chữ hoa/thường khác
    assert choose_sim_io_config("configs/vehicle_nghiem_thu.json", CONFIGS_DIR).path == ACCEPTANCE_SIM_IO
    if os.name == "nt":
        upper = str(ACCEPTANCE_VEHICLE_CONFIG).upper()
        assert choose_sim_io_config(upper, CONFIGS_DIR).path == ACCEPTANCE_SIM_IO


def test_choose_sim_io_config_fallbacks(tmp_path):
    folder = tmp_path / "configs"
    folder.mkdir()
    shutil.copy(DEFAULT_SIM_IO, folder / DEFAULT_SIM_IO_NAME)
    shutil.copy(DEFAULT_VEHICLE_CONFIG, folder / "vehicle_default.json")
    for name in ("xe_x.json", "xe_y.json"):
        shutil.copy(ACCEPTANCE_VEHICLE_CONFIG, folder / name)
    board = json.loads(DEFAULT_SIM_IO.read_text(encoding="utf-8"))

    def write_board(name: str, **changes) -> None:
        (folder / name).write_text(json.dumps(dict(board, **changes), ensure_ascii=False), encoding="utf-8")

    # Tệp xe không có bo nào trỏ tới: bo mặc định, không khớp
    unknown = choose_sim_io_config(folder / "xe_x.json", folder)
    assert unknown.path == folder / DEFAULT_SIM_IO_NAME and not unknown.matched
    assert "không có tệp vehicle_io_sim*.json nào có vehicle_config trỏ xe_x.json" in unknown.note
    # Tệp khớp nhưng có khóa lạ: không dùng, rơi về bo mặc định và ghi tên tệp hỏng
    write_board("vehicle_io_sim_x.json", vehicle_config="xe_x.json", khoa_la=1)
    broken = choose_sim_io_config(folder / "xe_x.json", folder)
    assert broken.path == folder / DEFAULT_SIM_IO_NAME and not broken.matched
    assert "vehicle_io_sim_x.json trỏ xe_x.json nhưng không nạp được" in broken.note
    # Hai tệp khớp: tệp đầu theo tên, tệp kia ghi ở chú thích; tệp JSON hỏng chỉ thành chú thích
    write_board("vehicle_io_sim_b.json", vehicle_config="xe_y.json")
    write_board("vehicle_io_sim_a.json", vehicle_config="xe_y.json", seed=7)
    (folder / "vehicle_io_sim_hong.json").write_text("{", encoding="utf-8")
    two = choose_sim_io_config(folder / "xe_y.json", folder)
    assert two.path == folder / "vehicle_io_sim_a.json" and two.matched and two.config.seed == 7
    assert "vehicle_io_sim_b.json" in two.note and "vehicle_io_sim_hong.json hỏng" in two.note
    # Không có cả bo mặc định: cấu hình mặc định trong mã
    empty = tmp_path / "rong"
    empty.mkdir()
    fallback = choose_sim_io_config(folder / "xe_x.json", empty)
    assert fallback.path is None and fallback.config == SimIOConfig() and not fallback.matched
    assert "vehicle_io_sim.json không nạp được" in fallback.note


def test_list_vehicle_configs(tmp_path):
    files, problems = list_vehicle_configs()
    names = [f.path.name for f in files]
    assert names[:2] == ["vehicle_default.json", "vehicle_nghiem_thu.json"] and problems == []
    assert not any(name.startswith("vehicle_io_sim") for name in names)
    shutil.copy(ACCEPTANCE_VEHICLE_CONFIG, tmp_path / "vehicle_b.json")
    shutil.copy(DEFAULT_VEHICLE_CONFIG, tmp_path / "vehicle_default.json")
    shutil.copy(DEFAULT_SIM_IO, tmp_path / DEFAULT_SIM_IO_NAME)
    (tmp_path / "vehicle_a_hong.json").write_text("{", encoding="utf-8")
    files, problems = list_vehicle_configs(tmp_path)
    assert [f.path.name for f in files] == ["vehicle_default.json", "vehicle_b.json"]
    assert len(problems) == 1 and problems[0].startswith("vehicle_a_hong.json: ")
    assert list_vehicle_configs(tmp_path / "khong_co") == ([], [])


# ---------------------------------------------------------------------------------------------- phiên
def test_session_set_vehicle(scenario, cfg):
    session = straight_session(scenario, cfg)
    link = VehicleLink.simulated(DriveMode.VEHICLE_IO)
    session.set_vehicle_link(link)
    session.start_manual()                                      # log của lần lái tay: đổi xe xóa log
    session.advance(0.2)
    session.stop_manual()
    assert session.state == SessionState.READY and len(session.log) > 0
    acc = load_vehicle_config_file(ACCEPTANCE_VEHICLE_CONFIG)
    with pytest.raises(SessionError, match="không hợp lệ"):
        session.set_vehicle(replace(acc.cfg, max_speed=0.0), acc.path)
    assert session.state == SessionState.READY and session.cfg is cfg      # cấu hình hỏng: không đổi gì
    session.set_vehicle(acc.cfg, acc.path)
    assert session.state == SessionState.EDITING and session.trajectory is None and len(session.log) == 0
    assert session.cfg.max_speed == pytest.approx(0.10)
    assert session.scenario.vehicle_config_path == ACCEPTANCE_VEHICLE_CONFIG
    assert session.vehicle_link is link                            # không đụng liên kết
    assert session.plan_sync().ok
    session.set_vehicle_link(None)
    session.start_run()
    assert session.state == SessionState.RUNNING
    with pytest.raises(SessionError, match="Chỉ chỉnh sa bàn khi đang chỉnh hoặc sẵn sàng"):
        session.set_vehicle(load_vehicle_config(DEFAULT_VEHICLE_CONFIG), DEFAULT_VEHICLE_CONFIG)
    assert session.cfg.max_speed == pytest.approx(0.10)
    session.request_stop()
    run_until_done(session)


def test_acceptance_targets_capped_sim():
    """bai_do_xe với xe nghiệm thu, nhánh SIM: planner giữ 0,15 m/s nhưng quỹ đạo và bộ bám kẹp mục tiêu ở 0,10 m/s;
    xe mô phỏng cũng bị kẹp ở max_speed (nên tốc độ đo ở MP không bao giờ vượt 0,10)."""
    scenario = load_scenario(BAI_DO_XE)
    acc = load_vehicle_config_file(ACCEPTANCE_VEHICLE_CONFIG)
    scenario.vehicle_config_path = acc.path
    session = Session(scenario, acc.cfg)
    assert session.plan_sync().ok
    assert max(p.v for p in session.trajectory.points) <= 0.10 + 1e-9
    session.start_run()
    run_until_done(session)
    assert session.state == SessionState.COMPLETED
    assert max(abs(row["target_speed"]) for row in session.log.rows) <= 0.10 + 1e-9
    assert max(abs(row["speed"]) for row in session.log.rows) <= 0.10 + 1e-9


def test_board_vehicle_mismatch_directions(scenario, cfg):
    """Xe nghiệm thu với bo mặc định (300 mm/s > 100): bo cho chạy nhanh hơn xe, START bị từ chối, không COMMAND nào.
    Xe mặc định với bo nghiệm thu (100 < 300 mm/s): bo chặt hơn, chạy và chỉ ghi cảnh báo."""
    acc = load_vehicle_config_file(ACCEPTANCE_VEHICLE_CONFIG).cfg
    session = straight_session(copy.deepcopy(scenario), acc)
    link = VehicleLink.simulated(DriveMode.VEHICLE_IO, load_sim_io_config(DEFAULT_SIM_IO)[0])
    session.set_vehicle_link(link)
    with pytest.raises(SessionError) as info:
        session.start_run()
    assert "Giới hạn của bo" in str(info.value) and "tốc độ lớn nhất" in str(info.value)
    assert session.state == SessionState.READY and link.runs == 0 and link.command_rows == []
    assert ("LIMITS_MISMATCH", "STOP") in [(r["code"], r["action"]) for r in link.start_refusals]
    assert link.limits_check is not None and link.limits_check.risky

    session = straight_session(copy.deepcopy(scenario), load_vehicle_config(DEFAULT_VEHICLE_CONFIG))
    link = VehicleLink.simulated(DriveMode.VEHICLE_IO, load_sim_io_config(ACCEPTANCE_SIM_IO)[0])
    session.set_vehicle_link(link)
    session.start_run()
    assert session.state == SessionState.RUNNING and link.start_refusals == []
    rows = [r for r in link.event_rows if r["code"] == "LIMITS_MISMATCH"]
    assert len(rows) == 1 and rows[0]["action"] == "LOG" and "chỉ cảnh báo (bo chặt hơn)" in rows[0]["message"]
    session.request_stop()
    run_until_done(session)
    assert session.state == SessionState.STOPPED
