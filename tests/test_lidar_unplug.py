"""Rút cáp LiDAR giữa chừng: driver RPLIDAR C1 và demo bàn thử phải kết thúc gọn, có thông báo rõ, không traceback.

Cổng nối tiếp ở đây là GIẢ: sau khi "rút cáp", mọi truy cập cổng ném `serial.SerialException` (lớp con của `OSError`)
như pyserial trên Windows. Không mở cổng thật nào, không cần LiDAR. Hành vi với cáp C1 thật: CHƯA THỬ (24/09/2026).
"""
import json

import pytest

np = pytest.importorskip("numpy")
serial = pytest.importorskip("serial")

from autopark.fusion import demo  # noqa: E402
from autopark.fusion.demo import run_demo  # noqa: E402
from autopark.lidar import rplidar_protocol as proto  # noqa: E402
from autopark.lidar.rplidar_c1 import LidarTransportError, RplidarC1Source, ScanReadError  # noqa: E402
from tests.test_lidar_protocol import (CAPTURED_HEALTH_OK, CAPTURED_INFO, FakeClock, FakeTransport,  # noqa: E402
                                       revolution_bytes, scripted_transport)

# Thông điệp kiểu pyserial trên Windows khi rút cáp USB (ClearCommError trong `in_waiting`).
UNPLUGGED = "ClearCommError failed (PermissionError(13, 'The device does not recognize the command.', None, 22))"
EMPTY_REVOLUTION = revolution_bytes(8, distance_mm=0.0, quality=0)      # không tia nào có phản hồi: không vật cản


class EndlessC1(FakeTransport):
    """C1 giả trả lời INFO/HEALTH/SCAN như bản ghi thật; sau SCAN mỗi lần đọc trên bộ đệm rỗng sinh thêm một vòng quét
    (kể cả sau `reset_input_buffer`). Sau `unplug()` — hoặc tự động khi lần đọc luồng thứ `reads_before_unplug + 1`
    tới — MỌI truy cập cổng (`in_waiting`, `read`, `write`, `reset_input_buffer`) ném `SerialException`; `close()`
    vẫn đóng được."""

    def __init__(self, reads_before_unplug: int | None = None):
        super().__init__({proto.request(proto.CMD_GET_INFO): [CAPTURED_INFO],
                          proto.request(proto.CMD_GET_HEALTH): [CAPTURED_HEALTH_OK]})
        self.reads_before_unplug = reads_before_unplug
        self.streaming = False
        self.stream_reads = 0
        self.unplugged = False
        self.failures = 0

    def unplug(self) -> None:
        self.unplugged = True

    def _check(self) -> None:
        if self.unplugged:
            self.failures += 1
            raise serial.SerialException(UNPLUGGED)

    @property
    def in_waiting(self) -> int:
        self._check()
        return len(self.buffer) or (len(EMPTY_REVOLUTION) if self.streaming else 0)

    def write(self, data: bytes) -> None:
        self._check()
        super().write(data)
        if bytes(data) == proto.request(proto.CMD_SCAN):
            self.streaming = True
        elif bytes(data) == proto.request(proto.CMD_STOP):
            self.streaming = False

    def read(self, n: int) -> bytes:
        self._check()
        if not self.buffer and self.streaming:
            self.stream_reads += 1
            if self.reads_before_unplug is not None and self.stream_reads > self.reads_before_unplug:
                self.unplug()
                self._check()
            self.buffer += EMPTY_REVOLUTION
        return super().read(n)

    def reset_input_buffer(self) -> None:
        self._check()
        super().reset_input_buffer()


class FakeWall:
    """Đồng hồ tường giả cho vòng lặp demo: mỗi lần gọi tiến `step` giây (test xác định, không chờ thật)."""

    def __init__(self, step: float = 0.02):
        self.t, self.step = 0.0, step

    def __call__(self) -> float:
        self.t += self.step
        return self.t


# ---- driver --------------------------------------------------------------------------------------------------------
def test_port_failure_in_read_becomes_lidar_transport_error():
    transport = EndlessC1()
    source = RplidarC1Source(transport, clock=FakeClock(), source_id="c1")
    scans = [source.read() for _ in range(3)]
    assert all(np.isnan(np.asarray(s.ranges_m)).all() for s in scans)
    transport.unplug()
    with pytest.raises(LidarTransportError) as info:
        source.read()
    error = info.value
    assert isinstance(error, ScanReadError)                      # nơi gọi chỉ bắt ScanReadError vẫn bắt được
    assert isinstance(error.__cause__, serial.SerialException) and isinstance(error.__cause__, OSError)
    assert "c1: serial port failed" in str(error) and "ClearCommError" in str(error)
    assert source.revolutions == 3
    # close() vẫn ném OSError khi không gửi được STOP qua cổng đã chết (có ghi trong docstring driver), nhưng cổng
    # vẫn được đóng; demo bắt lỗi này (test bên dưới).
    with pytest.raises(OSError):
        source.close()
    assert transport.closed


def test_port_failure_while_starting_inside_read_is_a_transport_error():
    transport = EndlessC1()
    transport.unplug()                                           # cáp đã rút trước khi bắt đầu
    source = RplidarC1Source(transport, clock=FakeClock())
    with pytest.raises(LidarTransportError) as info:
        source.read()                                            # read() tự gọi start()
    assert isinstance(info.value.__cause__, serial.SerialException)


def test_timeout_stays_a_plain_scan_read_error():
    source = RplidarC1Source(scripted_transport(revolutions=1), clock=FakeClock(), revolution_timeout_s=0.5)
    source.read()
    with pytest.raises(ScanReadError) as info:
        source.read()                                            # không còn vòng nào: hết thời gian chờ
    assert not isinstance(info.value, LidarTransportError) and info.value.__cause__ is None


# ---- demo bàn thử --------------------------------------------------------------------------------------------------
def test_demo_stops_the_virtual_car_and_ends_cleanly_when_the_cable_is_pulled(cfg):
    transport = EndlessC1(reads_before_unplug=60)
    source = RplidarC1Source(transport, clock=FakeClock())
    logs = []
    report = run_demo(source, seconds=20.0, cfg=cfg, initial_skip=2, initial_scans=5, clock=FakeWall(0.02),
                      sleep=lambda _s: None, log=logs.append)
    assert report["status"] == "STOPPED" and report["collided"] is False
    assert report["error"] is None
    assert report["transport_error"].startswith("LidarTransportError") and "ClearCommError" in report["transport_error"]
    assert "Mất kết nối LiDAR" in report["stop_reason"]
    assert report["read_errors"] == 1                            # đọc lỗi một lần rồi thôi, không đọc lại cổng chết
    assert transport.stream_reads == 61 and transport.failures == 1
    assert report["scans"] >= 50                                 # xe ảo đã chạy một lúc trước khi rút cáp
    assert any(line.startswith("mất kết nối LiDAR") for line in logs)
    assert any("kết thúc: STOPPED" in line and "mất kết nối LiDAR" in line for line in logs)
    assert demo._close_quietly(source).startswith("đóng LiDAR không trọn vẹn")   # STOP không gửi được, không ném
    assert transport.closed


class ScriptedPortFailure:
    """Nguồn giả không có vật nào; `read()` thứ `fail_at` (hoặc `flush()`) ném `SerialException` trực tiếp."""

    def __init__(self, fail_at: int | None = None, flush_fails: bool = False):
        self.reads, self.t = 0, 0.0
        self.fail_at, self.flush_fails = fail_at, flush_fails

    def now(self) -> float:
        return self.t

    def read(self):
        from tests.test_fusion import scan_with_object

        self.reads += 1
        self.t += 0.1
        if self.fail_at is not None and self.reads >= self.fail_at:
            raise serial.SerialException(UNPLUGGED)
        return scan_with_object(self.t, None)

    def flush(self) -> None:
        if self.flush_fails:
            raise serial.SerialException(UNPLUGGED)

    def close(self) -> None:
        pass


def test_demo_port_failure_before_the_run_returns_a_report(cfg):
    logs = []
    report = run_demo(ScriptedPortFailure(fail_at=3), seconds=5.0, cfg=cfg, initial_skip=2, initial_scans=5,
                      log=logs.append)
    assert report["status"] == "LỖI LIDAR TRƯỚC KHI CHẠY" and "trong lúc khởi động" in report["error"]
    assert report["transport_error"].startswith("SerialException") and report["read_errors"] == 1
    assert logs[-1].startswith("LỖI LIDAR TRƯỚC KHI CHẠY: mất kết nối LiDAR")

    report = run_demo(ScriptedPortFailure(flush_fails=True), seconds=5.0, cfg=cfg, initial_skip=0, initial_scans=3,
                      log=lambda _line: None)
    assert report["status"] == "LỖI LIDAR TRƯỚC KHI CHẠY" and "xả bộ đệm" in report["error"]


def test_demo_raw_oserror_during_the_run_is_handled_like_a_transport_error(cfg):
    report = run_demo(ScriptedPortFailure(fail_at=20), seconds=20.0, cfg=cfg, initial_skip=0, initial_scans=5,
                      clock=FakeWall(0.02), sleep=lambda _s: None, log=lambda _line: None)
    assert report["status"] == "STOPPED" and report["transport_error"].startswith("SerialException")
    assert report["read_errors"] == 1


def test_demo_main_exits_with_code_1_and_json_when_the_cable_is_pulled(monkeypatch, capsys):
    transports = []

    def fake_open(cls, port, **kwargs):                          # KHÔNG mở cổng thật
        transport = EndlessC1(reads_before_unplug=40)
        transports.append(transport)
        return cls(transport, clock=FakeClock(), **kwargs)

    monkeypatch.setattr(RplidarC1Source, "open", classmethod(fake_open))
    code = demo.main(["--port", "CONG_GIA", "--seconds", "10"])
    captured = capsys.readouterr()
    assert code == 1
    report = json.loads(captured.out.strip().splitlines()[-1])
    assert report["transport_error"].startswith("LidarTransportError")
    assert report["status"] == "STOPPED" and "Mất kết nối LiDAR" in report["stop_reason"]
    assert report["close_error"].startswith("đóng LiDAR không trọn vẹn")
    assert "đóng LiDAR không trọn vẹn" in captured.err and "Traceback" not in captured.err
    assert transports[0].closed


def test_demo_main_reports_a_port_that_cannot_be_opened(monkeypatch, capsys):
    def refuse(cls, port, **kwargs):
        raise serial.SerialException(f"could not open port '{port}': FileNotFoundError(2, 'The system cannot find "
                                     f"the file specified.', None, 2)")

    monkeypatch.setattr(RplidarC1Source, "open", classmethod(refuse))
    code = demo.main(["--port", "CONG_GIA", "--seconds", "1"])
    captured = capsys.readouterr()
    assert code == 1 and "không mở được LiDAR trên CONG_GIA" in captured.err and captured.out == ""


# ---- demo: bản ghi --recording hết giữa chừng (thêm tối 24/09/2026) ------------------------------------------------
class EndingRecording:
    """Nguồn giả kiểu `PacedReplay`: `total` vòng quét trống, lần đọc sau đó ném `ScanStreamEnded` (bản ghi hết)."""

    def __init__(self, total: int):
        self.live_view = pytest.importorskip("autopark.lidar.live_view")      # mô-đun định nghĩa lỗi, kéo theo PySide6
        self.total, self.reads, self.t = total, 0, 0.0

    def now(self) -> float:
        return self.t

    def read(self):
        from tests.test_fusion import scan_with_object

        self.reads += 1
        if self.reads > self.total:
            raise self.live_view.ScanStreamEnded("hết bản ghi")
        self.t += 0.1
        return scan_with_object(self.t, None)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


def test_demo_recording_that_ends_during_start_up_returns_a_report(cfg):
    logs = []
    report = run_demo(EndingRecording(total=4), seconds=5.0, cfg=cfg, initial_skip=2, initial_scans=5,
                      log=logs.append)
    assert report["status"] == "LỖI LIDAR TRƯỚC KHI CHẠY" and report["stream_ended"] is True
    assert report["error"].startswith("bản ghi LiDAR hết trong lúc khởi động") and "4 vòng" in report["error"]
    assert report["transport_error"] is None and report["read_errors"] == 0
    assert logs[-1].startswith("LỖI LIDAR TRƯỚC KHI CHẠY: bản ghi LiDAR hết")


def test_demo_recording_that_ends_during_the_run_stops_the_virtual_car_cleanly(cfg):
    source = EndingRecording(total=40)
    logs = []
    report = run_demo(source, seconds=20.0, cfg=cfg, initial_skip=0, initial_scans=5, clock=FakeWall(0.02),
                      sleep=lambda _s: None, log=logs.append)
    assert report["status"] == "STOPPED" and report["collided"] is False
    assert report["stream_ended"] is True and report["stop_reason"] == "Hết bản ghi LiDAR"
    assert report["error"] is None and report["transport_error"] is None and report["read_errors"] == 0
    assert report["scans"] == 40 and source.reads == 41                     # hết bản ghi thì thôi đọc
    assert any(line.startswith("hết bản ghi LiDAR") for line in logs)
    assert any("kết thúc: STOPPED" in line and "hết bản ghi LiDAR" in line for line in logs)


def test_demo_main_recording_end_exits_with_code_0_and_json(monkeypatch, capsys):
    live_view = pytest.importorskip("autopark.lidar.live_view")
    monkeypatch.setattr(live_view, "PacedReplay", lambda path: EndingRecording(total=40))   # không đọc tệp nào
    code = demo.main(["--recording", "khong_co_tep.npz", "--seconds", "10"])
    captured = capsys.readouterr()
    report = json.loads(captured.out.strip().splitlines()[-1])
    assert code == 0 and report["stream_ended"] is True and report["status"] == "STOPPED"
    assert report["error"] is None and report["close_error"] is None and "Traceback" not in captured.err


def test_demo_other_source_errors_still_propagate(cfg):
    """Chỉ lỗi cổng, hết thời gian chờ và hết bản ghi được bắt; lỗi khác của nguồn vẫn thoát ra (như docstring)."""
    class Broken(EndingRecording):
        def read(self):
            raise RuntimeError("nguồn hỏng kiểu khác")

    with pytest.raises(RuntimeError, match="nguồn hỏng kiểu khác"):
        run_demo(Broken(total=0), seconds=1.0, cfg=cfg, initial_skip=0, initial_scans=3, log=lambda _line: None)


# ---- lệnh ghi của bàn đo LiDAR ---------------------------------------------------------------------------------------
def test_bench_record_keeps_and_analyses_the_scans_when_the_cable_is_pulled(tmp_path, monkeypatch, capsys):
    """`lidar.bench record`: rút cáp giữa phiên → 3 lỗi đọc → dừng, LƯU và PHÂN TÍCH phần đã ghi, thoát mã 1, không
    traceback dù `close()` không gửi được STOP (sửa tối 24/09/2026)."""
    from autopark.lidar import bench

    transport = EndlessC1(reads_before_unplug=40)
    transport.baudrate = 460800

    def fake_open(port, **kwargs):
        source = RplidarC1Source(transport, clock=FakeClock(), source_id="c1")
        source.scan_modes = lambda: {}                           # C1 giả chỉ trả lời INFO/HEALTH
        return source

    monkeypatch.setattr(RplidarC1Source, "open", staticmethod(fake_open))
    code = bench.main(["record", "--port", "COM_GIA", "--out", str(tmp_path), "--name", "rut_cap", "--seconds", "30"])
    out = capsys.readouterr().out
    assert code == 1 and "phiên dừng sớm sau 3 lỗi đọc" in out and "đóng LiDAR không trọn vẹn" in out
    assert (tmp_path / "rut_cap.npz").exists() and (tmp_path / "rut_cap.analysis.json").exists()
    meta = json.loads((tmp_path / "rut_cap.json").read_text(encoding="utf-8"))
    assert meta["read_errors"] == 3 and transport.closed
