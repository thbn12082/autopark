"""Cổng LiDAR lấy từ MỘT chỗ, configs/thiet_bi.json (29/09/2026): đọc tệp, "auto", ghi đè bằng --port, và mọi lệnh
LiDAR dùng đúng giá trị đó. Không mở cổng thật: `RplidarC1Source.open` bị thay bằng hàm ghi lại cổng."""
import argparse
import json
import os
from types import SimpleNamespace

import pytest

from autopark.lidar import port as port_mod
from autopark.lidar.port import LidarPortError, configured_lidar_port, find_cp210x_port, lidar_port

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def write_config(tmp_path, value, key="lidar_port"):
    path = tmp_path / "thiet_bi.json"
    path.write_text(json.dumps({"_ghi_chu": "thử", key: value}), encoding="utf-8")
    return path


def fake_port(device, vid=None, pid=None):
    return SimpleNamespace(device=device, vid=vid, pid=pid)


CP210X = fake_port("COM12", 0x10C4, 0xEA60)
ESP32 = fake_port("COM10", 0x303A, 0x1001)


@pytest.fixture
def config(tmp_path, monkeypatch):
    """Trỏ tệp cấu hình của mô-đun sang tệp tạm; trả hàm ghi giá trị."""
    path = tmp_path / "thiet_bi.json"
    monkeypatch.setattr(port_mod, "CONFIG_PATH", path)

    def set_value(value):
        write_config(tmp_path, value)
        return path
    return set_value


@pytest.fixture
def opened(monkeypatch):
    """Thay RplidarC1Source.open: ghi lại cổng rồi ném OSError như cổng không có — không chạm thiết bị."""
    from autopark.lidar.rplidar_c1 import RplidarC1Source

    ports = []

    def fake_open(cls, port, **kwargs):
        ports.append(port)
        raise OSError(f"cổng giả {port}")
    monkeypatch.setattr(RplidarC1Source, "open", classmethod(fake_open))
    return ports


# ------------------------------------------------------------------------------------------------ đọc cấu hình

def test_repo_config_file_is_valid():
    value = configured_lidar_port()          # tệp thật trong repo: phải đọc được, không khẳng định số COM của máy nào
    assert value and value == value.strip()
    assert port_mod.CONFIG_PATH.parent.name == "configs" and port_mod.CONFIG_PATH.name == "thiet_bi.json"


def test_configured_value_is_read_and_stripped(tmp_path):
    assert configured_lidar_port(write_config(tmp_path, " COM7 ")) == "COM7"
    assert configured_lidar_port(write_config(tmp_path, "auto")) == "auto"


@pytest.mark.parametrize("content", ["", "{", "[]", json.dumps({"khac": "COM3"}), json.dumps({"lidar_port": 3}),
                                     json.dumps({"lidar_port": "  "}), json.dumps({"lidar_port": None})])
def test_broken_config_is_a_clear_error(tmp_path, content):
    path = tmp_path / "thiet_bi.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(LidarPortError) as info:
        configured_lidar_port(path)
    assert str(path) in str(info.value)


def test_config_saved_with_a_bom_is_read(tmp_path):
    path = tmp_path / "thiet_bi.json"          # Notepad / Set-Content -Encoding UTF8 của PowerShell 5.1
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"lidar_port": "COM8"}).encode("utf-8"))
    assert configured_lidar_port(path) == "COM8"


def test_unreadable_config_is_a_clear_error(tmp_path):
    folder = tmp_path / "thiet_bi.json"
    folder.mkdir()                              # một thư mục trùng tên: OSError khác FileNotFoundError
    with pytest.raises(LidarPortError) as info:
        configured_lidar_port(folder)
    assert "không đọc được" in str(info.value)


def test_missing_config_is_a_clear_error(tmp_path):
    with pytest.raises(LidarPortError) as info:
        configured_lidar_port(tmp_path / "khong_co.json")
    assert "khong_co.json" in str(info.value) and "--port" in str(info.value)


def test_lidar_port_error_is_a_value_error():
    assert issubclass(LidarPortError, ValueError)       # rig.bench giữ quy ước ValueError cho tham số sai


# ------------------------------------------------------------------------------------------------ chọn cổng

def test_explicit_port_wins_without_reading_the_file(config):
    assert lidar_port("COM5") == "COM5"                 # tệp cấu hình chưa có: không được đọc
    assert lidar_port(" COM5 ") == "COM5"


def test_no_explicit_port_uses_the_file(config):
    config("COM3")
    assert lidar_port() == "COM3" and lidar_port(None) == "COM3" and lidar_port("") == "COM3"
    assert lidar_port("   ") == "COM3"                   # ô cổng của ngăn LiDAR để trống


def test_auto_finds_the_cp210x_and_ignores_other_ports(config):
    config("auto")
    assert lidar_port(comports=[ESP32, CP210X]) == "COM12"
    assert lidar_port("AUTO", comports=[CP210X]) == "COM12"       # --port auto cũng tự tìm, không phân biệt hoa thường
    with pytest.raises(LidarPortError) as info:
        lidar_port(comports=[ESP32])
    assert "CP210x" in str(info.value)


def test_find_cp210x_port():
    assert find_cp210x_port([ESP32, CP210X, fake_port("COM13", 0x10C4, 0xEA60)]) == "COM12"   # cổng ĐẦU TIÊN
    assert find_cp210x_port([ESP32, fake_port("COM1")]) is None


def test_may_moi_uses_the_shared_detector():
    from autopark.rig import may_moi

    assert may_moi.find_lidar_port is find_cp210x_port
    assert (may_moi.CP210X_VID, may_moi.CP210X_PID) == (0x10C4, 0xEA60)


# ------------------------------------------------------------------------------------------------ các lệnh LiDAR

def test_fusion_demo_opens_the_configured_port(config, opened, capsys):
    from autopark.fusion import demo

    config("COM_CAU_HINH")
    assert demo.main(["--seconds", "1"]) == 1          # open ném OSError → báo, mã 1
    assert opened == ["COM_CAU_HINH"] and "COM_CAU_HINH" in capsys.readouterr().err
    assert demo.main(["--port", "COM5", "--seconds", "1"]) == 1
    assert opened[-1] == "COM5"


def test_fusion_demo_reports_a_broken_config_without_opening(config, opened, capsys):
    from autopark.fusion import demo

    assert demo.main(["--seconds", "1"]) == 1          # tệp cấu hình (tạm) chưa có
    assert opened == [] and "không xác định được cổng LiDAR" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        demo.main(["--port", "COM5", "--recording", "a.npz"])     # vẫn chỉ chọn một trong hai


def test_lidar_bench_record_takes_the_configured_port(config, monkeypatch):
    import autopark.lidar.bench as lidar_bench

    seen = []
    monkeypatch.setattr(lidar_bench, "record", lambda args: seen.append(args.port) or 0)
    config("COM_CAU_HINH")
    assert lidar_bench.main(["record", "--out", "x", "--name", "n"]) == 0
    assert lidar_bench.main(["record", "--port", "COM5", "--out", "x", "--name", "n"]) == 0
    assert seen == ["COM_CAU_HINH", "COM5"]            # bản ghi lưu cổng thật đã mở, không phải None


def test_lidar_bench_record_broken_config_exits_before_recording(config, monkeypatch, capsys):
    import autopark.lidar.bench as lidar_bench

    monkeypatch.setattr(lidar_bench, "record", lambda args: pytest.fail("không được ghi khi thiếu cổng"))
    with pytest.raises(SystemExit) as info:
        lidar_bench.main(["record", "--out", "x", "--name", "n"])
    assert info.value.code == 2 and "thiet_bi.json" in capsys.readouterr().err


def test_rplidar_c1_cli_takes_the_configured_port(config, opened):
    from autopark.lidar import rplidar_c1

    config("COM_CAU_HINH")
    with pytest.raises(OSError):
        rplidar_c1.main(["info"])
    with pytest.raises(OSError):
        rplidar_c1.main(["stream", "--port", "COM5", "--seconds", "0"])
    assert opened == ["COM_CAU_HINH", "COM5"]


def test_live_view_takes_the_configured_port(config, opened):
    pytest.importorskip("PySide6")
    from autopark.lidar import live_view

    config("COM_CAU_HINH")
    with pytest.raises(OSError):                        # mở cổng lỗi trước khi dựng cửa sổ
        live_view.main([])
    assert opened == ["COM_CAU_HINH"]


def test_live_view_broken_config_is_a_usage_error(config, opened):
    pytest.importorskip("PySide6")
    from autopark.lidar import live_view

    with pytest.raises(SystemExit) as info:
        live_view.main([])
    assert info.value.code == 2 and opened == []


# ------------------------------------------------------------------------------------------------ rig.bench / rig_app

def rig_args(*argv):
    from autopark.rig import bench

    p = argparse.ArgumentParser()
    bench.add_rig_args(p)
    return p.parse_args(["--index", "0", "--no-ai", *argv])


@pytest.fixture
def fake_rig(monkeypatch):
    """build_rig không dựng camera hay Rig thật."""
    from autopark.rig import bench

    monkeypatch.setattr(bench, "MultiCameraManager", lambda specs, **kwargs: SimpleNamespace(specs=specs))
    monkeypatch.setattr(bench, "Rig", lambda cams, cfg, **kwargs: SimpleNamespace(cams=cams, cfg=cfg, **kwargs))
    return bench


def test_rig_lidar_flag_without_value_uses_the_config(config, fake_rig):
    config("COM_CAU_HINH")
    assert rig_args("--lidar").lidar == ""
    rig = fake_rig.build_rig(rig_args("--lidar"))
    assert rig.cfg.lidar_port == "COM_CAU_HINH" and rig.open_lidar is not None
    rig = fake_rig.build_rig(rig_args("--lidar", "COM5"))
    assert rig.cfg.lidar_port == "COM5"
    rig = fake_rig.build_rig(rig_args())                 # không có --lidar: không LiDAR, không đọc tệp
    assert rig.cfg.lidar_port is None and rig.open_lidar is None


def test_rig_lidar_broken_config_fails_before_any_camera(config, monkeypatch):
    from autopark.rig import bench

    monkeypatch.setattr(bench, "MultiCameraManager", lambda *a, **k: pytest.fail("không được dựng camera"))
    monkeypatch.setattr(bench, "resolve_ports", lambda *a, **k: pytest.fail("không được tra cổng hub"))
    with pytest.raises(LidarPortError):
        bench.build_rig(rig_args("--lidar"))
    with pytest.raises(SystemExit) as info:
        bench.main(["--name", "t", "--index", "0", "--no-ai", "--lidar"])
    assert info.value.code == 2


def test_rig_replay_refuses_a_bare_lidar_flag(tmp_path):
    from autopark.rig import bench

    args = rig_args("--lidar")
    args.index = None
    args.replay = tmp_path / "ban_ghi"
    with pytest.raises(ValueError, match="--lidar"):       # "--lidar" trống vẫn là --lidar: bị từ chối khi phát lại
        bench.build_rig(args)


# ------------------------------------------------------------------------------------------------ ngăn LiDAR

@pytest.fixture
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_dock_prefills_and_connects_to_the_configured_port(qapp, config, opened):
    from autopark.ui.lidar_app import build_window

    config("COM_CAU_HINH")
    window, dock = build_window(None, port=None, recording=None)
    dock.timer.stop()
    window._timer.stop()
    assert dock.edit_port.text() == "COM_CAU_HINH" and "thiet_bi.json" in dock.edit_port.placeholderText()
    dock.edit_port.setText("")
    dock.connect_source()                               # ô trống → lấy lại từ tệp
    dock.edit_port.setText("COM5")
    dock.connect_source()
    assert opened == ["COM_CAU_HINH", "COM5"] and dock.source is None
    assert "Không kết nối được" in dock.lbl_device.text()
    window.close()


def test_dock_explicit_port_and_broken_config(qapp, config, opened):
    from autopark.ui.lidar_app import build_window

    window, dock = build_window(None, port="COM9", recording=None)     # --port ghi đè: không đọc tệp
    dock.timer.stop()
    window._timer.stop()
    assert dock.edit_port.text() == "COM9"
    window.close()
    window, dock = build_window(None, port=None, recording=None)      # tệp (tạm) chưa có: cửa sổ vẫn mở
    dock.timer.stop()
    window._timer.stop()
    assert dock.edit_port.text() == ""
    dock.connect_source()
    assert opened == [] and dock.source is None and "thiet_bi.json" in dock.lbl_device.text()
    window.close()
