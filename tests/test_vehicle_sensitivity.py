"""Kiểm cấu hình xe cho cửa sổ LiDAR không kết nối phần cứng."""
import json
import os
import pytest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from autopark.storage.scenario_store import load_vehicle_config
from tests.conftest import PROJECT_ROOT
DEFAULT_CFG_PATH = PROJECT_ROOT / "configs" / "vehicle_default.json"

def write_cfg(path, **changes):
    data = json.loads(DEFAULT_CFG_PATH.read_text(encoding="utf-8"))
    data.update({"name": "xe_thu_tam", "wheelbase_m": 0.30, "width_m": 0.10, "front_overhang_m": 0.05,
                 "rear_overhang_m": 0.07, "max_steer_deg": 28.0})
    data.update(changes)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    pytest.importorskip("numpy")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _close(window, dock):
    dock.timer.stop()
    window._timer.stop()
    dock.shutdown()
    window.close()


def test_lidar_app_nhan_cau_hinh_xe(qapp, tmp_path):
    from autopark.ui import lidar_app

    cfg_path = write_cfg(tmp_path / "xe.json")
    window, dock = lidar_app.build_window(None, port="COM9", recording=None, vehicle_config=cfg_path)
    try:
        assert window.session.cfg.name == "xe_thu_tam"
        assert window.session.scenario.vehicle_config_path == cfg_path.resolve()
        assert dock.source is None                                     # không mở cổng nào
    finally:
        _close(window, dock)

    scenario_path = PROJECT_ROOT / "scenarios" / "thao_tac_cua_hep.json"
    window, dock = lidar_app.build_window(scenario_path, port="COM9", recording=None, vehicle_config=cfg_path)
    try:
        assert window.session.cfg.name == "xe_thu_tam"
    finally:
        _close(window, dock)

    window, dock = lidar_app.build_window(None, port="COM9", recording=None)   # mặc định không đổi
    try:
        assert window.session.cfg == load_vehicle_config(DEFAULT_CFG_PATH)
    finally:
        _close(window, dock)


def _fake_open_dialog(monkeypatch, path):
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(path), "JSON (*.json)")))


def _no_error_box(monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    def fail(*args, **kwargs):
        raise AssertionError(f"không được hiện hộp lỗi: {args[1:]}")

    monkeypatch.setattr(QMessageBox, "critical", staticmethod(fail))


def test_lidar_app_mo_kich_ban_trong_cua_so_van_giu_xe_da_chon(qapp, tmp_path, monkeypatch):
    """Nút "Mở kịch bản" không được lặng lẽ đổi sang tệp xe của kịch bản khi đã chạy với --vehicle-config."""
    from autopark.ui import lidar_app

    opened = PROJECT_ROOT / "scenarios" / "thao_tac_cua_hep.json"
    _fake_open_dialog(monkeypatch, opened)
    _no_error_box(monkeypatch)
    cfg_path = write_cfg(tmp_path / "xe.json")
    window, dock = lidar_app.build_window(None, port="COM9", recording=None, vehicle_config=cfg_path)
    try:
        window._open_scenario()
        assert window.session.scenario.name != "ban_thu_lidar"                  # kịch bản mới đã được mở
        assert window.scenario_path == opened
        assert window.session.cfg.name == "xe_thu_tam"
        assert window.session.scenario.vehicle_config_path == cfg_path.resolve()
        assert "xe.json" in window.statusBar().currentMessage()
        assert dock.source is None
    finally:
        _close(window, dock)

    # Không có --vehicle-config: như MainWindow, dùng tệp xe mà kịch bản trỏ tới.
    window, dock = lidar_app.build_window(None, port="COM9", recording=None)
    try:
        window._open_scenario()
        assert window.scenario_path == opened
        assert window.session.cfg == load_vehicle_config(PROJECT_ROOT / "configs" / "vehicle_nghiem_thu.json")
    finally:
        _close(window, dock)


def test_lidar_app_mo_kich_ban_tep_xe_cua_kich_ban_hong_van_dung_xe_da_chon(qapp, tmp_path, monkeypatch):
    """Kịch bản trỏ tới tệp xe không có: với --vehicle-config vẫn mở được, không hiện hộp lỗi."""
    from autopark.ui import lidar_app

    data = json.loads((PROJECT_ROOT / "scenarios" / "thao_tac_cua_hep.json").read_text(encoding="utf-8"))
    data["vehicle_config"] = "khong_co_xe_nay.json"
    broken = tmp_path / "kich_ban_tro_xe_hong.json"
    broken.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    _fake_open_dialog(monkeypatch, broken)
    _no_error_box(monkeypatch)
    cfg_path = write_cfg(tmp_path / "xe.json")
    window, dock = lidar_app.build_window(None, port="COM9", recording=None, vehicle_config=cfg_path)
    try:
        window._open_scenario()
        assert window.scenario_path == broken and window.session.cfg.name == "xe_thu_tam"
    finally:
        _close(window, dock)


def test_lidar_app_tep_hong_thoat_truoc_khi_mo_cua_so(qapp, tmp_path, capsys, monkeypatch):
    from autopark.ui import lidar_app

    def must_not_open(*args, **kwargs):
        raise AssertionError("không được mở cửa sổ/cổng khi tệp xe hỏng")

    monkeypatch.setattr(lidar_app, "build_window", must_not_open)
    bad = write_cfg(tmp_path / "hong.json", max_steer_deg=0)
    with pytest.raises(SystemExit) as info:
        lidar_app.main(["--no-connect", "--vehicle-config", str(bad)])
    assert info.value.code == 2 and "max_steer" in capsys.readouterr().err
