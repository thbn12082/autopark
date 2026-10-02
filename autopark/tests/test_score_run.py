"""Công cụ chấm một lần chạy (T5, `autopark.evaluation.score_run`).

Dữ liệu là tổng hợp (tham chiếu R1 có nhiễu, log VehicleIO viết tay theo hai định dạng: cũ và T13 có `session_stop`,
`t_perf`, `clock`; tệp dấu đồng bộ theo cột của T14) hoặc lần chạy MÔ PHỎNG thật (Session → VehicleLink →
SimVehicleIO → FirmwareModel; nhánh SIM + export_run). Không mở cổng, không camera, không gọi PowerShell hay git.
Mọi tệp ghi trong tmp_path. Thêm 02/10/2026.
"""
import csv
import json
import math
import random
import re
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from autopark.application.session import Session, SessionState
from autopark.application.vehicle_link import COMMAND_FIELDS, TELEMETRY_FIELDS, DriveMode, VehicleLink
from autopark.domain.types import Obstacle, Pose
from autopark.evaluation.reference_pose import ReferenceAccuracy, ReferenceMeta, ReferenceSample, write_reference
from autopark.evaluation.score_run import BIEN_BAN_FIELDS, load_thresholds, main
from autopark.lidar import recording as lidar_recording
from autopark.storage import run_store
from autopark.storage.run_store import export_run
from autopark.storage.scenario_store import load_scenario, load_vehicle_config
from autopark.transport.vehicle_io import SIM_FIRMWARE_DEFAULT, SimIOConfig
from tests.conftest import PROJECT_ROOT
from tests.test_session_vehicle import SIM_CFG, FixedPose, run_until_done, sim_io, straight_session

BAI_DO_XE = PROJECT_ROOT / "scenarios" / "bai_do_xe.json"              # đích (2.2, 0.255, 90°), ô x 2.03–2.37
VEHICLE = PROJECT_ROOT / "configs" / "vehicle_default.json"
OLD_EVENT_FIELDS = ["t_session", "t_io", "source", "code", "action", "handling", "message"]
T13_EVENT_FIELDS = ["t_session", "t_io", "t_perf", "source", "code", "action", "handling", "message"]
SYNC_FIELDS = ["n", "kind", "t_perf", "t_wall", "source", "trigger", "state", "t_session", "t_io", "io_clock",
               "t_rig_s", "flash_ms", "paint_ms", "note"]                  # cột T14 trừ cột cuối time_scale (tệp cũ)
RUNLOG_FIELDS = ["t", "x", "y", "yaw_deg", "speed", "steer_deg", "target_speed", "target_steer_deg", "collided",
                 "min_clearance", "distance"]
T0_IO, T0_PERF = 50.0, 1000.0                                             # đồng hồ io/perf lúc START của log giả


@pytest.fixture(autouse=True)
def no_subprocess(monkeypatch):
    monkeypatch.setattr(lidar_recording, "git_commit", lambda: "test")     # không gọi git
    monkeypatch.setattr(run_store, "environment", lambda: {"test": True})  # không gọi PowerShell


# ---------------------------------------------------------------------------------------------- dữ liệu tổng hợp
def write_csv(path: Path, fields, rows) -> Path:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def cmd(t, kind="TRACK", sent=1, segment=0, done=0):
    return {"t_session": round(t, 4), "t_io": round(T0_IO + t, 4), "kind": kind, "sent": sent,
            "segment": segment if kind == "TRACK" else "", "done": done if kind == "TRACK" else ""}


def tel(t, v=0.0, v_ref=0.0):
    return {"t_session": round(t, 4), "t_io": round(T0_IO + t, 4), "state": "RUNNING", "speed_mps": v,
            "speed_ref_mps": v_ref}


def event(t, code, handling="session_stop", action="STOP", source="sim_safety"):
    return {"t_session": round(t, 4), "t_io": round(T0_IO + t, 4), "t_perf": round(T0_PERF + t, 6),
            "source": source, "code": code, "action": action, "handling": handling, "message": f"{code} giả"}


def vio_log(root: Path, *, name="lan_vehicle_io", t_end=8.5, outcome="COMPLETED", reason="Đỗ xong",
            mode="VEHICLE_IO", evidence="hardware_untested", port="COM5", pose_source="lidar_pose",
            io_simulated=False, commands=None, telemetry=None, events=(), t13=True, result=True,
            runlog=None) -> Path:
    """Thư mục log giống `VehicleLink.write_logs`; t13=True thêm cột t_perf và khóa clock như thiết kế T13."""
    d = root / name
    d.mkdir(parents=True)
    if commands is None:
        commands = [cmd(i * 0.1) for i in range(int(round(t_end / 0.1)))]
        commands[-1]["done"] = 1
    telemetry = telemetry if telemetry is not None else [tel(i * 0.05) for i in range(int(round(t_end / 0.05)))]
    write_csv(d / "commands.csv", COMMAND_FIELDS, [dict(c, mode=mode) for c in commands])
    write_csv(d / "telemetry.csv", TELEMETRY_FIELDS, telemetry)
    fields = T13_EVENT_FIELDS if t13 else OLD_EVENT_FIELDS
    write_csv(d / "events.csv", fields, events)
    write_csv(d / "start_refusals.csv", fields, [])
    info = {"mode": mode, "io": "SerialVehicleIO", "io_simulated": io_simulated, "pose_source": pose_source,
            "pose_simulated": False, "port": port, "params": {}, "sim_config": None, "limits_check": None,
            "evidence": evidence, "runs": 1, "refused_starts": 0, "stats": None,
            "result": {"t_session": t_end, "outcome": outcome, "reason": reason, "board_state": "DISARMED",
                       "commands_sent": sum(1 for c in commands if c["sent"] == 1),
                       "telemetry_received": len(telemetry)} if result else None}
    if t13:
        info["clock"] = {"t_io_at_start": T0_IO, "t_perf_at_start": T0_PERF}
    (d / "link.json").write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    if runlog is not None:
        write_csv(d.with_name(name[:-len("_vehicle_io")] + ".csv"), RUNLOG_FIELDS, runlog)
    return d


def stop_log(root: Path, *, t_detect=5.15, t_stop=5.16, t_end=5.6, t13=True, events=None, enable_after=(),
             **kwargs) -> Path:
    """Lần chạy dừng vì vật cản: TRACK tới t_stop, rồi STOP; sự kiện dừng của phiên ở t_detect."""
    commands = [cmd(i * 0.02) if i * 0.02 < t_stop - 1e-9 else cmd(i * 0.02, "STOP")
                for i in range(int(round(t_end / 0.02)) + 1)]
    commands += [cmd(t) for t in enable_after]                    # lệnh chạy SAU lệnh dừng (theo thứ tự dòng)
    if events is None:
        events = [event(t_detect, "MAP_CHANGED")]
    kwargs.setdefault("outcome", "STOPPED")
    kwargs.setdefault("reason", "Vật cản mới: dừng, cập nhật và chờ lập lại đường")
    return vio_log(root, t_end=t_end, commands=commands, events=events, t13=t13, **kwargs)


def write_track(path: Path, motion, t_end: float, *, fps=30.0, sigma=0.002, yaw_sigma_deg=0.3, seed=0,
                accuracy=(0.008, 0.9), clock="t_session", method="R1", t_offset=0.0) -> Path:
    """Tệp tham chiếu R1 tổng hợp: tư thế theo `motion(t)` → (x, y, hướng độ) cộng nhiễu Gauss."""
    rng = random.Random(seed)
    samples = []
    for i in range(int(round(t_end * fps)) + 1):
        t = i / fps
        x, y, yaw = motion(t)
        pose = Pose(x + rng.gauss(0, sigma), y + rng.gauss(0, sigma), math.radians(yaw + rng.gauss(0, yaw_sigma_deg)))
        samples.append(ReferenceSample(round(t + t_offset, 4), pose, i, 2, 0.001))
    acc = ReferenceAccuracy(*accuracy, "TC-1 tổng hợp") if accuracy else ReferenceAccuracy(None, None)
    write_reference(path, samples, ReferenceMeta(method, clock, acc, tool="test"))
    return path


def parking_motion(x_end=2.23, y_end=0.255, yaw=92.0, v=0.08, t_stop=6.25):
    """Lùi thẳng xuống ô của bai_do_xe rồi đứng yên từ t_stop."""
    return lambda t: (x_end, y_end + v * max(0.0, t_stop - t), yaw)


def braking_motion(t):
    """0,1 m/s theo +x từ x = 0,5; phanh 0,5 m/s² từ 5,2 s; đứng yên ở x = 1,03 từ 5,4 s."""
    if t <= 5.2:
        x = 0.5 + 0.1 * t
    elif t <= 5.4:
        x = 1.02 + 0.1 * (t - 5.2) - 0.25 * (t - 5.2) ** 2
    else:
        x = 1.03
    return x, 1.0, 0.0


def straight_layout(root: Path, obstacles=()) -> Path:
    data = {"schema_version": 1, "name": "thang", "vehicle_config": str(VEHICLE),
            "bounds": {"xmin": 0.0, "ymin": 0.0, "xmax": 3.0, "ymax": 2.0},
            "start": {"x": 0.5, "y": 1.0, "yaw_deg": 0.0}, "goal": {"x": 2.0, "y": 1.0, "yaw_deg": 0.0},
            "obstacles": [o.to_dict() for o in obstacles]}
    path = root / "bo_tri_thang.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class Scored:
    """Kết quả một lần chấm: dòng biên bản cuối cùng, tệp chi tiết và các kiểm theo mã."""

    def __init__(self, report: Path, detail: Path):
        with report.open(encoding="utf-8-sig", newline="") as f:
            self.rows = list(csv.DictReader(f))
        self.row = self.rows[-1]
        self.detail = json.loads(detail.read_text(encoding="utf-8"))
        self.checks = {c["code"]: c for c in self.detail["checks"]}

    def verdict(self, code):
        return self.checks[code]["verdict"]


def score(tmp_path, *extra, scenario="DO-1", level="XT", attempt=1, expect=0, report="bien_ban.csv",
          detail="chi_tiet.json"):
    argv = ["--scenario", scenario, "--attempt", str(attempt), "--level", level, *map(str, extra),
            "--report", str(tmp_path / report), "--detail", str(tmp_path / detail)]
    assert main(argv) == expect
    return Scored(tmp_path / report, tmp_path / detail) if expect == 0 else None


# ---------------------------------------------------------------------------------------------- tư thế cuối, quy tắc 3
def test_final_pose_is_median_of_last_second_and_meets_nd1_nd2(tmp_path):
    ref = write_track(tmp_path / "r1.csv", parking_motion(), 8.5)
    log = vio_log(tmp_path)
    s = score(tmp_path, "--log", log, "--reference", ref, "--layout", BAI_DO_XE, "--touch", "khong",
              "--intervention", "khong", "--methods", "R5")
    assert float(s.row["sai_so_vi_tri_cm"]) == pytest.approx(3.0, abs=0.2)
    assert float(s.row["sai_so_huong_deg"]) == pytest.approx(2.0, abs=0.2)
    assert s.verdict("N-D1") == s.verdict("N-D2") == "dat"
    assert s.row["trong_o"] == "co" and s.row["cham"] == "khong" and s.row["can_thiep"] == "khong"
    assert s.row["phuong_phap_do"] == "R1+R6+R5" and s.row["doi_chieu_thuc"] == "0" == s.row["doi_chieu_lap"]
    # Khoảng hở 2 cm cần tham chiếu ≤ 0,67 cm ở góc thân xe: 0,8 cm + 0,26 m × sin 0,9° vượt → không kiểm được.
    assert s.verdict("N-D5") == "khong_kiem_duoc" and "quy tắc 3" in s.checks["N-D5"]["note"]
    assert s.row["ket_qua"] == "" and "N-D5" in s.row["ghi_chu"]
    assert s.row["ghi_chu"].endswith("ngưỡng ĐỀ XUẤT – CHỜ CHỐT")


def test_coarse_reference_gives_khong_kiem_duoc_not_dat(tmp_path):
    ref = write_track(tmp_path / "r1.csv", parking_motion(), 8.5, accuracy=(0.02, 0.9))
    s = score(tmp_path, "--log", vio_log(tmp_path), "--reference", ref, "--layout", BAI_DO_XE, "--touch", "khong",
              "--intervention", "khong")
    assert s.verdict("N-D1") == "khong_kiem_duoc"
    assert float(s.row["sai_so_vi_tri_cm"]) == pytest.approx(3.0, abs=0.2)      # số vẫn được ghi
    assert s.row["ket_qua"] != "THANH_CONG" and "quy tắc 3" in s.row["ghi_chu"]


def test_missing_tc1_accuracy_blocks_reference_verdicts(tmp_path):
    ref = write_track(tmp_path / "r1.csv", parking_motion(), 8.5, accuracy=None)
    s = score(tmp_path, "--log", vio_log(tmp_path), "--reference", ref, "--layout", BAI_DO_XE, "--touch", "khong",
              "--intervention", "khong")
    for code in ("N-D1", "N-D2", "N-D3", "N-D5", "N-V1"):
        assert s.verdict(code) == "khong_kiem_duoc", code
        assert "TC-1" in s.checks[code]["note"], code
    assert s.row["ket_qua"] == "" and s.row["trong_o"] == ""


def test_car_still_moving_at_file_end_leaves_final_pose_empty(tmp_path):
    ref = write_track(tmp_path / "r1.csv", parking_motion(t_stop=9.0), 8.5)
    s = score(tmp_path, "--log", vio_log(tmp_path), "--reference", ref, "--layout", BAI_DO_XE)
    assert s.row["sai_so_vi_tri_cm"] == s.row["sai_so_huong_deg"] == s.row["trong_o"] == ""
    assert "chưa đứng yên" in s.row["ghi_chu"] and s.verdict("N-D1") == "khong_kiem_duoc"


def test_r2_points_give_the_final_pose_and_the_detail_keeps_r1_minus_r2(tmp_path):
    ref = write_track(tmp_path / "r1.csv", parking_motion(), 8.5)
    pose = Pose(2.22, 0.255, math.radians(91.0))                    # đo bằng thước: hai dấu trên trục xe
    rear, front = pose.to_world(-0.06, 0.0), pose.to_world(0.25, 0.0)
    s = score(tmp_path, "--log", vio_log(tmp_path), "--reference", ref, "--layout", BAI_DO_XE,
              "--r2-points", f"{rear[0]},{rear[1]},{front[0]},{front[1]}", "--r2-error-cm", "0.3")
    assert float(s.row["sai_so_vi_tri_cm"]) == pytest.approx(2.0, abs=0.05)
    assert float(s.row["sai_so_huong_deg"]) == pytest.approx(1.0, abs=0.01)
    assert s.row["phuong_phap_do"] == "R1+R2+R6"
    r1_r2 = s.detail["reference"]["R1-R2"]
    assert r1_r2["dist_m"] == pytest.approx(0.01, abs=0.002) and r1_r2["dyaw_deg"] == pytest.approx(1.0, abs=0.2)
    assert s.checks["N-D1"]["detail"]["source"] == "R2"


def test_min_clearance_matches_analytic_gap(tmp_path):
    box = Obstacle("hop", 1.2, 1.22, 0.2, 0.2)                     # đáy hộp y = 1,12; hông xe y = 1,07 → hở 5 cm
    ref = write_track(tmp_path / "mp.csv", lambda t: (0.5 + 0.1 * min(t, 15.0), 1.0, 0.0), 17.0, fps=50.0,
                      sigma=0.0, yaw_sigma_deg=0.0, accuracy=(0.0, 0.0), method="MP")
    log = vio_log(tmp_path, evidence="simulation_only", port=None, t_end=17.0)
    s = score(tmp_path, "--log", log, "--reference", ref, "--layout", straight_layout(tmp_path, [box]),
              level="MP")
    assert float(s.row["khoang_ho_min_cm"]) == pytest.approx(5.0, abs=0.05)
    assert s.verdict("N-D5") == "dat" and s.checks["N-D5"]["detail"]["obstacle"] == "hop"
    assert s.verdict("N-D3") == "khong_ap_dung" and s.row["phuong_phap_do"] == "MP+R6"


@pytest.mark.parametrize("dx, expected, verdict", [(0.0, "co", "dat"), (0.13, "khong", "khong_dat"),
                                                   (0.097, "", "khong_kiem_duoc")])
def test_in_slot_inside_outside_and_borderline(tmp_path, dx, expected, verdict):
    # Ô của bai_do_xe: x 2,03–2,37; ở đích thân xe x 2,13–2,27. Sai số góc thân xe 0,5 cm + 0,26 m × sin 0,5° ≈ 0,73 cm.
    ref = write_track(tmp_path / "r1.csv", lambda t: (2.2 + dx, 0.255, 90.0), 2.0, sigma=0.0, yaw_sigma_deg=0.0,
                      accuracy=(0.005, 0.5))
    s = score(tmp_path, "--log", vio_log(tmp_path), "--reference", ref, "--layout", BAI_DO_XE)
    assert s.row["trong_o"] == expected and s.verdict("N-D3") == verdict
    assert s.checks["N-D3"]["detail"]["footprint_error_m"] == pytest.approx(0.00727, abs=2e-5)


def test_v_max_over_0_2_m_window_flags_nv1_and_proposes_that_bai(tmp_path):
    motion = lambda t: (1.0 + 0.14 * min(max(t - 1.0, 0.0), 1.0 / 0.14), 1.0, 0.0)    # 1 m ở 0,14 m/s tới đích
    ref = write_track(tmp_path / "r1.csv", motion, 10.5, accuracy=(0.005, 0.5))
    s = score(tmp_path, "--log", vio_log(tmp_path, t_end=10.5), "--reference", ref, "--layout",
              straight_layout(tmp_path), "--touch", "khong", "--intervention", "khong")
    assert float(s.row["v_max_do_mps"]) == pytest.approx(0.140, abs=0.003)
    assert s.verdict("N-V1") == "khong_dat"
    assert s.row["ket_qua"] == "THAT_BAI" and "nguyên nhân chính" in s.row["ghi_chu"]


def test_thanh_cong_needs_every_success_condition_and_touch_or_intervention_always_fails(tmp_path):
    """NGUONG mục 1: THÀNH CÔNG cần N-D1, N-D2, N-D3 (khi có ô), N-D4, N-D7, N-D9, N-V1 dù danh sách của kịch bản
    (DO-6: N-D1, N-D2, N-D4, N-D6) không có; các kiểm thêm đó chỉ để đề xuất ket_qua, ô của chúng để trống. N-D4 và
    N-D9 tuyệt đối ở mọi kịch bản: chạm hay can thiệp ghi tay luôn là THAT_BAI."""
    ref = write_track(tmp_path / "r1.csv", parking_motion(), 8.5)
    base = ["--log", vio_log(tmp_path), "--reference", ref, "--layout", BAI_DO_XE, "--touch", "khong"]
    s = score(tmp_path, *base, "--intervention", "khong", scenario="DO-6", attempt=1)
    assert s.row["ket_qua"] == "THANH_CONG"
    decision = {c["code"]: c["verdict"] for c in s.detail["decision_checks"]}
    assert decision == {"N-D3": "dat", "N-D7": "dat", "N-D9": "dat", "N-V1": "dat"}
    assert s.row["trong_o"] == s.row["thoi_gian_s"] == s.row["v_max_do_mps"] == ""      # ô ngoài danh sách DO-6
    s = score(tmp_path, *base, scenario="DO-6", attempt=2)                      # thiếu --intervention
    assert s.row["ket_qua"] == "" and "N-D9 (điều kiện THÀNH CÔNG, NGUONG mục 1)" in s.row["ghi_chu"]
    s = score(tmp_path, *base, "--intervention", "co", scenario="DO-6", attempt=3)
    assert s.row["ket_qua"] == "THAT_BAI" and s.row["can_thiep"] == "co"          # trước đây THANH_CONG
    assert "N-D9 can thiệp của người: co → không đạt" in s.row["ghi_chu"]
    s = score(tmp_path, *base, "--intervention", "khong", "--v-max-mps", "0.3", scenario="DO-6", attempt=4)
    assert s.row["ket_qua"] == "THAT_BAI" and s.row["v_max_do_mps"] == "" and "N-V1" in s.row["ghi_chu"]
    # AT-1 không có N-D4 trong danh sách: chạm ghi tay vẫn là THAT_BAI, không phải 'không có kiểm nào không đạt'
    s = score(tmp_path, "--log", stop_log(tmp_path, name="b_vehicle_io"), "--touch", "co", scenario="AT-1")
    assert s.row["ket_qua"] == "THAT_BAI" and s.row["cham"] == "co" and "tuyệt đối ở mọi kịch bản" in s.row["ghi_chu"]


# --------------------------------------------------------------------------------------------- mốc, đồng hồ, quãng dừng
def test_stop_distance_from_event_on_reference_clock(tmp_path):
    ref = write_track(tmp_path / "r1.csv", braking_motion, 8.0, sigma=0.001, yaw_sigma_deg=0.2,
                      accuracy=(0.003, 0.5))
    s = score(tmp_path, "--log", stop_log(tmp_path), "--reference", ref, "--event", "ref:5.0", "--touch", "khong",
              scenario="VC-1")
    assert float(s.row["quang_dung_cm"]) == pytest.approx(3.0, abs=0.2)                 # 0,1 × 0,2 + 0,1²/(2 × 0,5)
    assert s.verdict("N-P2") == "dat" and s.checks["N-P2"]["error"] == pytest.approx(0.6 + 0.1 * 100 / 30, abs=0.05)
    assert float(s.row["t_phat_hien_s"]) == pytest.approx(0.150, abs=1e-6) and s.verdict("N-P1") == "dat"
    assert s.verdict("N-P10") == "dat" and s.row["ket_qua"] == ""


def test_np1_needs_r7_or_shared_clock(tmp_path):
    ref = write_track(tmp_path / "r1.csv", braking_motion, 8.0, sigma=0.001, clock="video", t_offset=7.3)
    log = stop_log(tmp_path, t_detect=5.25, t_stop=5.26)
    base = ["--log", log, "--reference", ref, "--event", "ref:12.3", "--touch", "khong"]
    s = score(tmp_path, *base, scenario="VC-1", attempt=1)
    assert s.row["t_phat_hien_s"] == "" and "thiếu R7" in s.row["ghi_chu"]
    s = score(tmp_path, *base, "--sync", "12.3=5.0", scenario="VC-1", attempt=2)
    assert s.row["t_phat_hien_s"] == "0.250" and s.verdict("N-P1") == "khong_kiem_duoc"
    assert "R7" in s.row["phuong_phap_do"]
    s = score(tmp_path, *base, "--sync", "12.3=5.0", "--time-error", "0.05", scenario="VC-1", attempt=3)
    assert s.row["t_phat_hien_s"] == "0.250" and s.verdict("N-P1") == "dat"
    assert s.checks["N-P1"]["error"] == pytest.approx(0.05 + 1 / 30, abs=1e-4)


def test_two_sync_pairs_fit_offset_and_drift(tmp_path):
    ref = write_track(tmp_path / "r1.csv", braking_motion, 8.0, clock="video", t_offset=7.3)
    pairs = [(t, t * (1 + 1e-4) - 7.3) for t in (10.0, 40.0)]
    s = score(tmp_path, "--log", stop_log(tmp_path), "--reference", ref, "--event", "ref:12.3",
              *[a for t, u in pairs for a in ("--sync", f"{t}={u:.6f}")], scenario="VC-1")
    cmap = s.detail["clock_map"]
    assert cmap["drift"] == pytest.approx(1e-4, abs=1e-6) and cmap["offset"] == pytest.approx(-7.3, abs=1e-6)
    assert s.detail["event"]["t_session"] == pytest.approx(12.3 * (1 + 1e-4) - 7.3, abs=1e-6)


def test_event_stop_makes_np1_not_checkable(tmp_path):
    ref = write_track(tmp_path / "r1.csv", braking_motion, 8.0, sigma=0.001)
    s = score(tmp_path, "--log", stop_log(tmp_path), "--reference", ref, "--event", "stop", scenario="VC-1")
    assert s.verdict("N-P1") == "khong_kiem_duoc" and "chính lệnh dừng" in s.checks["N-P1"]["note"]
    assert s.row["t_phat_hien_s"] == "" and s.detail["event"]["t_session"] == pytest.approx(5.16)


def test_code_event_that_is_the_stop_decision_itself_is_circular(tmp_path):
    """NGUONG quy tắc 3: sự kiện của ngưỡng đang kiểm không làm mốc. code:<MÃ> trùng quyết định dừng của phiên (hay
    dòng "stop" cùng mã lúc lớp nối nhận sự kiện bo, T13) → N-P1 không kiểm được, không phải 'đạt 0,000 s'."""
    s = score(tmp_path, "--log", stop_log(tmp_path), "--event", "code:MAP_CHANGED", scenario="VC-1")
    assert s.verdict("N-P1") == "khong_kiem_duoc" and "vòng tròn" in s.checks["N-P1"]["note"]
    assert s.row["t_phat_hien_s"] == "" and s.detail["event"]["circular"]
    twin = [event(8.090, "VEHICLE_FAULT", "stop", source="sim_vehicle_io"),
            event(8.095, "VEHICLE_FAULT", source="sim_vehicle_io")]
    log = stop_log(tmp_path, name="b_vehicle_io", t_stop=8.1, t_end=8.6, events=twin)
    s = score(tmp_path, "--log", log, "--event", "code:VEHICLE_FAULT", scenario="VC-1", attempt=2)
    assert s.verdict("N-P1") == "khong_kiem_duoc" and "vòng tròn" in s.checks["N-P1"]["note"]
    # Mã không phải sự kiện dừng (dòng log của công cụ khác) vẫn là mốc dùng được
    marked = [event(8.0, "FAULT_MARK", "log", "LOG", "fault_injection"), event(8.095, "MAP_CHANGED")]
    log = stop_log(tmp_path, name="c_vehicle_io", t_stop=8.1, t_end=8.6, events=marked)
    s = score(tmp_path, "--log", log, "--event", "code:FAULT_MARK", scenario="VC-1", attempt=3)
    assert s.row["t_phat_hien_s"] == "0.095" and s.verdict("N-P1") == "dat"


def test_self_restart_after_standstill_fails_np10(tmp_path):
    def motion(t):                                                  # đứng yên 3 s rồi tự chạy thêm 5 cm
        x, y, yaw = braking_motion(min(t, 8.4))
        return x + 0.05 * min(max(t - 8.4, 0.0), 1.0), y, yaw

    ref = write_track(tmp_path / "r1.csv", motion, 10.5, sigma=0.001, accuracy=(0.003, 0.5))
    s = score(tmp_path, "--log", stop_log(tmp_path), "--reference", ref, "--event", "ref:5.0", scenario="VC-1")
    assert s.verdict("N-P10") == "khong_dat" and s.checks["N-P10"]["detail"]["moved_after_standstill_m"] > 0.045
    assert s.row["ket_qua"] == "THAT_BAI" and "tự chạy lại" in s.row["ghi_chu"]
    assert float(s.row["quang_dung_cm"]) == pytest.approx(3.0, abs=0.2)          # quãng tới lần đứng yên ĐẦU


def test_enable_command_after_stop_fails_np10_from_log(tmp_path):
    log = stop_log(tmp_path, t_detect=2.99, t_stop=3.0, t_end=4.0, enable_after=(3.5,),
                   events=[event(2.99, "USER_STOP", source="user")])
    s = score(tmp_path, "--log", log, scenario="AT-1")
    assert s.verdict("N-P10") == "khong_dat" and "1 lệnh chạy sau lệnh dừng" in s.checks["N-P10"]["note"]
    assert s.verdict("N-P6") == "khong_kiem_duoc" and s.row["ket_qua"] == "THAT_BAI"


@pytest.mark.parametrize("variant, expected, approximated", [
    ("t13_session_stop", 0.095, False),
    ("t13_vehicle_row_earlier", 0.095, False),      # T13: dòng "stop" lúc nhận không phải quyết định của phiên
    ("old_stop_row", 0.095, False),                 # log cũ: dòng "stop" của VehicleIO có mã và thời điểm
    ("old_without_rows", 0.100, True),              # log cũ, phiên dừng vì sự kiện không được ghi: dòng STOP ±20 ms
])
def test_detection_time_prefers_logged_stop_events_over_first_stop_row(tmp_path, variant, expected, approximated):
    events = {"t13_session_stop": [event(8.095, "MAP_CHANGED")],
              "t13_vehicle_row_earlier": [event(8.090, "VEHICLE_FAULT", "stop", source="sim_vehicle_io"),
                                          event(8.095, "VEHICLE_FAULT", source="sim_vehicle_io")],
              "old_stop_row": [event(8.095, "VEHICLE_FAULT", "stop", source="sim_vehicle_io")],
              "old_without_rows": [event(8.2, "VEHICLE_STOPPED", "log", "LOG", "sim_vehicle_io")]}[variant]
    log = stop_log(tmp_path, t_stop=8.1, t_end=8.6, t13=variant.startswith("t13"), events=events)
    s = score(tmp_path, "--log", log, "--event", "session:8.0", scenario="VC-1")
    assert float(s.row["t_phat_hien_s"]) == pytest.approx(expected, abs=1e-6)
    detection = s.detail["log"]["detection"]
    assert detection["exact"] is not approximated
    assert ("±20 ms" in s.row["ghi_chu"]) is approximated
    if approximated:
        assert s.checks["N-P1"]["error"] == pytest.approx(0.02)


def test_realtime_board_detection_is_the_decision_time_not_the_step_time(tmp_path):
    """Bo thời gian thực (io_simulated false): giao diện khựng 0,3 s, phiên chạy dồn bước tới io.now(). Dòng
    session_stop ghi thời gian bước 5,15 s nhưng t_io (lúc phiên quyết định) ứng với 5,45 s; các dòng STOP sau đó cũng
    vậy."""
    lagging = event(5.15, "MAP_CHANGED")
    lagging.update(t_io=round(T0_IO + 5.45, 4), t_perf=round(T0_PERF + 5.45, 6))
    commands = [cmd(i * 0.02) if i * 0.02 < 5.16 - 1e-9 else cmd(i * 0.02, "STOP") for i in range(281)]
    for row in commands:
        if row["kind"] == "STOP":
            row["t_io"] = round(row["t_io"] + 0.3, 4)
    common = dict(t_end=5.6, commands=commands, outcome="STOPPED")
    log = vio_log(tmp_path, name="a_vehicle_io", events=[lagging], **common)
    s = score(tmp_path, "--log", log, "--event", f"perf:{T0_PERF + 5.0}", scenario="VC-1", attempt=1)
    assert s.row["t_phat_hien_s"] == "0.450" and s.verdict("N-P1") == "khong_dat"   # trước đây 0,150 'đạt' ±0
    detection = s.detail["log"]["detection"]
    assert detection["exact"] and detection["t_step"] == pytest.approx(5.15)
    assert "muộn hơn thời gian bước" in s.checks["N-P1"]["note"]
    # Log cũ (chưa T13) của bo thời gian thực: dòng STOP đầu, theo t_io của nó (±20 ms)
    old = vio_log(tmp_path, name="b_vehicle_io", t13=False, **common)
    s = score(tmp_path, "--log", old, "--event", f"io:{T0_IO + 5.0}", scenario="VC-1", attempt=2)
    assert s.row["t_phat_hien_s"] == "0.460" and s.checks["N-P1"]["error"] == pytest.approx(0.02)
    # Bo mô phỏng: thời gian phiên là thời gian mô phỏng, giữ t_session của dòng
    sim = vio_log(tmp_path, name="c_vehicle_io", events=[lagging], evidence="simulation_only", port=None,
                  pose_source="sim_truth_pose", io_simulated=True, **common)
    s = score(tmp_path, "--log", sim, "--event", "session:5.0", scenario="VC-1", level="MP", attempt=3)
    assert s.row["t_phat_hien_s"] == "0.150"


def test_user_stop_is_neither_a_detection_nor_a_false_stop(tmp_path):
    user = dict(source="user")
    early = stop_log(tmp_path, name="a_vehicle_io", t_detect=5.2, t_stop=5.22,
                     events=[event(5.2, "USER_STOP", **user)])
    late = stop_log(tmp_path, name="b_vehicle_io", t_detect=6.5, t_stop=6.52, t_end=7.0,
                    events=[event(6.5, "USER_STOP", **user)])
    s = score(tmp_path, "--log", early, "--event", "session:5.0", scenario="VC-1", attempt=1)
    assert s.row["t_phat_hien_s"] == "0.200" and s.verdict("N-P1") == "khong_kiem_duoc"   # người dừng trước ngưỡng
    assert "do người" in s.checks["N-P1"]["note"]
    s = score(tmp_path, "--log", late, "--event", "session:5.0", scenario="VC-1", attempt=2)
    assert s.verdict("N-P1") == "khong_dat"                       # hệ thống chưa dừng sau 0,4 s: người phải dừng
    s = score(tmp_path, "--log", early, scenario="VC-6", attempt=3)
    assert s.verdict("N-P4") == "khong_kiem_duoc" and s.row["ket_qua"] == ""
    old = stop_log(tmp_path, name="c_vehicle_io", t13=False, events=[], reason="Người dùng yêu cầu dừng")
    s = score(tmp_path, "--log", old, scenario="VC-6", attempt=4)                # log cũ: nhận ra qua lý do dừng
    assert s.verdict("N-P4") == "khong_kiem_duoc" and s.detail["log"]["detection"]["by_user"] is True


def test_nd6c_speed_at_direction_flip(tmp_path):
    def log_with(v_at_flip, evidence, name):
        telemetry = [tel(t / 20, *((0.05, 0.05) if t < 40 else (0.0, 0.0) if t < 50 else (-0.05, -0.05)))
                     for t in range(100)]
        telemetry[50]["speed_mps"] = v_at_flip                        # mẫu đầu sau khi v tham chiếu đổi dấu
        commands = [cmd(t / 10, segment=0 if t < 25 else 1) for t in range(50)]
        commands[-1]["done"] = 1
        return vio_log(tmp_path, name=name, t_end=5.0, telemetry=telemetry, commands=commands, evidence=evidence,
                       port=None if evidence == "simulation_only" else "COM5")

    cases = [(0.05, "hardware_untested", "XT", "khong_dat"), (0.004, "hardware_untested", "XT", "dat"),
             (0.05, "simulation_only", "MP", "chi_bao_so")]
    for i, (v, evidence, level, part) in enumerate(cases):
        s = score(tmp_path, "--log", log_with(v, evidence, f"l{i}_vehicle_io"), "--layout", BAI_DO_XE,
                  scenario="DO-6", level=level, attempt=i + 1)
        detail = s.checks["N-D6"]["detail"]
        assert detail["parts"]["c"] == part and detail["speed_at_flips_mps"] == [v]
        assert s.row["doi_chieu_lap"] == s.row["doi_chieu_thuc"] == "1"
        assert s.verdict("N-D6") == ("khong_dat" if part == "khong_dat" else "dat")


def test_planned_cusps_known_only_when_path_finished_or_plan_saved(tmp_path):
    def commands(done):
        rows = [cmd(t / 10, segment=min(t // 10, 2)) for t in range(30)]
        rows[-1]["done"] = int(done)
        return rows

    finished = vio_log(tmp_path, name="a_vehicle_io", commands=commands(True))
    unfinished = vio_log(tmp_path, name="b_vehicle_io", commands=commands(False), outcome="STOPPED",
                         reason="Người dùng yêu cầu dừng")
    saved = vio_log(tmp_path, name="c_vehicle_io", commands=commands(True))
    (saved / "run.json").write_text(json.dumps({"trajectory": {"segments": [[0, 5], [6, 9], [10, 14], [15, 20]]},
                                                "max_run_time": 180.0}), encoding="utf-8")
    rows = {}
    for i, log in enumerate((finished, unfinished, saved), start=1):
        rows[log.name] = score(tmp_path, "--log", log, "--layout", BAI_DO_XE, scenario="DO-6", attempt=i).row
    assert rows["a_vehicle_io"]["doi_chieu_lap"] == "2"
    assert rows["b_vehicle_io"]["doi_chieu_lap"] == "" and "chưa biết số lần đổi chiều" in rows["b_vehicle_io"][
        "ghi_chu"]
    assert rows["c_vehicle_io"]["doi_chieu_lap"] == "3"                          # run.json được ưu tiên


@pytest.mark.parametrize("outcome, flips, part", [
    ("COMPLETED", 0, "khong_dat"),       # lần đỗ xong mà thiếu lần đổi chiều: không đúng quỹ đạo
    ("STOPPED", 0, "khong_ap_dung"),     # dừng trước lần đổi chiều đã lập: đường chưa đi hết, không xét (a)
    ("STOPPED", 1, "dat"),
    ("STOPPED", 2, "khong_dat"),         # (a) cấm đổi chiều THÊM, kể cả khi lần chạy bị dừng
])
def test_nd6a_on_a_stopped_run_only_forbids_extra_reversals(tmp_path, outcome, flips, part):
    per = 100 // (flips + 1)
    telemetry = []
    for i in range(100):
        k = min(i // per, flips)
        v_ref = 0.05 if k % 2 == 0 else -0.05
        telemetry.append(tel(i / 20, 0.0 if k and i % per == 0 else v_ref, v_ref))   # đứng yên lúc đổi chiều
    log = vio_log(tmp_path, t_end=5.0, telemetry=telemetry, outcome=outcome)
    (log / "run.json").write_text(json.dumps({"trajectory": {"segments": [[0, 5], [6, 9]]}}), encoding="utf-8")
    s = score(tmp_path, "--log", log, "--layout", BAI_DO_XE, "--touch", "khong", scenario="DO-6")
    nd6 = s.checks["N-D6"]
    assert (s.row["doi_chieu_lap"], s.row["doi_chieu_thuc"]) == ("1", str(flips))
    assert nd6["detail"]["parts"]["a"] == part and (nd6["verdict"] == "khong_dat") is (part == "khong_dat")
    if part == "khong_ap_dung":
        assert "đường chưa đi hết" in nd6["note"]
        assert s.row["ket_qua"] == "" and "DUNG_DUNG" in s.row["ghi_chu"]


def test_log_exported_before_the_run_ended_is_not_a_missed_stop(scenario, cfg, tmp_path):
    """'Xuất log CSV…' được bấm giữa lần chạy: chưa có sự kiện dừng không có nghĩa là hệ thống không dừng."""
    s = score(tmp_path, "--log", vio_log(tmp_path, result=False), "--event", "session:4.0", scenario="VC-1")
    assert s.verdict("N-P1") == "khong_kiem_duoc" and "chưa kết thúc" in s.checks["N-P1"]["note"]
    assert s.row["t_phat_hien_s"] == "" and s.row["ket_qua"] == ""             # trước đây 'không đạt', THAT_BAI
    session = straight_session(scenario, cfg)                                    # gói SIM xuất khi đang RUNNING
    session.start_run()
    while session.world.time < 1.0:
        session.advance(0.05)
    bundle = export_run(session, tmp_path / "giua_20261002_101500_000000")
    assert json.loads((bundle / "result.json").read_text(encoding="utf-8"))["state"] == "RUNNING"
    s = score(tmp_path, "--log", bundle, "--event", "session:0.5", scenario="VC-1", level="MP", attempt=2)
    assert s.verdict("N-P1") == "khong_kiem_duoc" and s.row["ket_qua"] == ""
    s = score(tmp_path, "--log", bundle, scenario="VC-6", level="MP", attempt=3)
    assert s.verdict("N-P4") == "khong_kiem_duoc" and s.row["ket_qua"] == ""
    s = score(tmp_path, "--log", bundle, "--layout", straight_layout(tmp_path), scenario="DO-5", level="MP",
              attempt=4)
    assert s.verdict("N-D7") == "khong_kiem_duoc" and s.row["ket_qua"] == ""
    assert "chưa kết thúc" in s.row["ghi_chu"] and s.detail["log"]["ended"] is False


def test_unfinished_export_and_run_timeout(tmp_path):
    s = score(tmp_path, "--log", vio_log(tmp_path, name="a_vehicle_io", result=False), "--layout", BAI_DO_XE,
              scenario="DO-5", attempt=1)
    assert "chưa kết thúc" in s.row["ghi_chu"] and s.verdict("N-D7") == "khong_kiem_duoc"
    assert s.verdict("N-D1") == "khong_ap_dung"                       # không COMPLETED: chỉ ghi số (nếu có)
    log = stop_log(tmp_path, name="b_vehicle_io", t_detect=12.0, t_stop=12.02, t_end=12.5, outcome="FAULT",
                   events=[event(12.0, "RUN_TIMEOUT")])
    s = score(tmp_path, "--log", log, "--layout", BAI_DO_XE, scenario="DO-5", attempt=2)
    assert s.verdict("N-D7") == "khong_dat" and s.row["thoi_gian_s"] == "12.50"
    assert s.row["ket_qua"] == "THAT_BAI"


def test_vc6_false_stop_and_observe_zero_command(tmp_path):
    s = score(tmp_path, "--log", vio_log(tmp_path, name="a_vehicle_io"), scenario="VC-6", attempt=1)
    assert s.verdict("N-P4") == "dat"
    s = score(tmp_path, "--log", stop_log(tmp_path, name="b_vehicle_io"), scenario="VC-6", attempt=2)
    assert s.verdict("N-P4") == "khong_dat" and s.row["ket_qua"] == "THAT_BAI"
    observe = [cmd(t / 10, sent=0) for t in range(20)]
    s = score(tmp_path, "--log", vio_log(tmp_path, name="c_vehicle_io", mode="OBSERVE", commands=observe),
              scenario="AT-5", attempt=3)
    assert s.verdict("0-COMMAND") == "dat"
    assert score(tmp_path, "--log", vio_log(tmp_path, name="d_vehicle_io"), scenario="AT-5", attempt=4,
                 expect=2) is None                                                # log VEHICLE_IO: từ chối


# ---------------------------------------------------------------------------------------------- T13 / T14: perf_counter
def test_perf_counter_reference_maps_through_t13_link_clock(tmp_path):
    ref = write_track(tmp_path / "r1.csv", braking_motion, 8.0, sigma=0.001, clock="perf_counter",
                      t_offset=T0_PERF, accuracy=(0.003, 0.5))
    log = stop_log(tmp_path, t_detect=5.2, t_stop=5.22)
    s = score(tmp_path, "--log", log, "--reference", ref, "--event", f"ref:{T0_PERF + 5.0}", scenario="VC-1",
              attempt=1)
    assert s.row["t_phat_hien_s"] == "0.200" and s.verdict("N-P1") == "dat"
    assert "link.json clock" in s.detail["clock_map"]["source"] and s.row["phuong_phap_do"] == "R1+R6"
    assert float(s.row["quang_dung_cm"]) == pytest.approx(3.0, abs=0.2)
    s = score(tmp_path, "--log", log, "--reference", ref, "--event", f"perf:{T0_PERF + 5.0}", scenario="VC-1",
              attempt=2)
    assert s.row["t_phat_hien_s"] == "0.200" and s.checks["N-P1"]["error"] == pytest.approx(0.0)


def sync_mark(n, t_perf, state="READY", note=""):
    return {"n": n, "kind": "SYNC_MARK", "t_perf": t_perf, "t_wall": "2026-10-02T10:00:00.000", "source": "ui.app",
            "trigger": "key_f8", "state": state, "flash_ms": 500, "paint_ms": 1.5, "note": note}


def clock_row(t_perf, state, t_session, note, time_scale=""):
    return {"n": "", "kind": "CLOCK", "t_perf": t_perf, "source": "ui.app", "trigger": "state_change",
            "state": state, "t_session": t_session, "io_clock": "sim", "note": note, "time_scale": time_scale}


def test_t14_marks_pair_a_video_reference_on_a_realtime_board(tmp_path):
    # Video R1: v = t_session + 20. Dấu #1 trước START (t_session −2), dấu #2 sau khi dừng (t_session 12).
    ref = write_track(tmp_path / "r1.csv", braking_motion, 8.0, sigma=0.001, clock="video", t_offset=20.0,
                      accuracy=(0.003, 0.5))
    log = stop_log(tmp_path, t_detect=5.2, t_stop=5.22)
    write_csv(tmp_path / "lan_sync_marks.csv", SYNC_FIELDS,                      # tên T14 ghi cạnh <tên>.csv
              [sync_mark(1, T0_PERF - 2.0), sync_mark(2, T0_PERF + 12.0, "STOPPED")])
    s = score(tmp_path, "--log", log, "--reference", ref, "--sync", "18.0=mark:1", "--sync", "32.0=mark:2",
              "--time-error", "0.04", "--event", "ref:25.0", scenario="VC-1")
    assert s.detail["clock_map"]["offset"] == pytest.approx(-20.0, abs=1e-9)
    assert s.row["t_phat_hien_s"] == "0.200" and s.verdict("N-P1") == "dat"
    assert s.row["phuong_phap_do"] == "R1+R6+R7" and s.detail["sync_marks"].endswith("lan_sync_marks.csv")
    assert float(s.row["quang_dung_cm"]) == pytest.approx(3.0, abs=0.2)


def test_t14_clock_rows_of_the_matching_run_anchor_simulated_time(tmp_path):
    # Bo mô phỏng, log cũ (không t_perf): đổi perf_counter → t_session chỉ nhờ dòng CLOCK của T14. Tệp có hai lần
    # chạy; chỉ lần có dòng kết thúc trùng t_end của log (5,6 s) được dùng.
    runlog = [{"t": round(i * 0.02, 4), "x": braking_motion(i * 0.02)[0], "y": 1.0, "yaw_deg": 0.0,
               "speed": 0.0 if i == 280 else 0.1, "collided": 0} for i in range(281)]
    log = stop_log(tmp_path, t13=False, t_end=5.6, events=[], evidence="simulation_only", port=None,
                   pose_source="sim_truth_pose", io_simulated=True, runlog=runlog)
    write_csv(tmp_path / "lan_sync_marks.csv", SYNC_FIELDS, [
        clock_row(900.0, "RUNNING", 0.016, "READY→RUNNING"), clock_row(904.2, "STOPPED", 4.0, "RUNNING→STOPPED"),
        sync_mark(1, 990.0),
        clock_row(992.016, "RUNNING", 0.016, "READY→RUNNING"), clock_row(997.4, "STOPPING", 5.15, "RUNNING→STOPPING"),
        clock_row(997.87, "STOPPED", 5.6, "STOPPING→STOPPED")])
    s = score(tmp_path, "--log", log, "--sim-truth", "--event", "mark:1+7.0", "--time-error", "0.04",
              scenario="VC-1", level="BT")
    anchors = [a[0] for a in s.detail["perf_map"]["anchors"]]
    assert anchors == [992.016, 997.4, 997.87]                                     # không lấy lần chạy trước
    # Tệp không có cột time_scale (tốc độ chạy): giả định 1×, ghi giả định vào tệp chi tiết; các mốc khớp 1× ± trôi
    assert s.detail["perf_map"]["scale"] == 1.0 and "giả định 1×" in s.detail["perf_map"]["scale_source"]
    assert s.detail["perf_map"]["fitted_scale"] == pytest.approx(0.954, abs=0.002)
    assert s.detail["event"]["t_session"] == pytest.approx(5.15 - 0.4, abs=1e-9)
    assert s.detail["event"]["error_session_s"] == pytest.approx(0.04 + 0.1 + 0.05 * 0.4, abs=1e-9)
    # 0,16 s + 20 ms của dòng STOP (log cũ) > 0,4/3: phần thời gian không kiểm được, số vẫn ghi
    assert s.row["t_phat_hien_s"] == "0.410" and s.verdict("N-P1") == "khong_kiem_duoc"
    assert "R7" in s.row["phuong_phap_do"] and s.row["cham"] == "khong" and "xe ảo" in s.row["ghi_chu"]


def test_t14_time_scale_maps_simulated_time_and_blocks_reaction_thresholds(tmp_path, capsys):
    """Giao diện đặt tốc độ chạy 2×: 1 s perf_counter = 2 s phiên. Cột time_scale của T14 cho hệ số; tệp cũ không có
    cột đó mà các mốc cho 2× thì giả định 1× bị bác, không đổi perf_counter sang t_session."""
    runlog = [{"t": round(i * 0.02, 4), "x": braking_motion(i * 0.02)[0], "y": 1.0, "yaw_deg": 0.0,
               "speed": 0.0 if i == 280 else 0.1, "collided": 0} for i in range(281)]
    log = stop_log(tmp_path, t13=False, t_end=5.6, events=[], evidence="simulation_only", port=None,
                   pose_source="sim_truth_pose", io_simulated=True, runlog=runlog)
    rows = [clock_row(1000.008, "RUNNING", 0.016, "READY→RUNNING", 2.0),
            clock_row(1002.575, "STOPPING", 5.15, "RUNNING→STOPPING", 2.0),
            clock_row(1002.8, "STOPPED", 5.6, "STOPPING→STOPPED", 2.0), sync_mark(1, 990.0)]
    write_csv(tmp_path / "lan_sync_marks.csv", SYNC_FIELDS + ["time_scale"], rows)
    args = ["--log", log, "--sim-truth", "--event", "mark:1+12.375", "--time-error", "0.04"]
    s = score(tmp_path, *args, scenario="VC-1", level="BT", attempt=1)
    perf_map = s.detail["perf_map"]
    assert perf_map["scale"] == 2.0 and "time_scale" in perf_map["scale_source"]
    # perf 1002,375 = 0,2 s thật trước mốc STOPPING (5,15 s phiên) → 4,75 s phiên (1× cho 4,95 s)
    assert s.detail["event"]["t_session"] == pytest.approx(4.75, abs=1e-9)
    assert s.detail["event"]["error_session_s"] == pytest.approx(2 * (0.1 + 0.05 * 0.2) + 2 * 0.04, abs=1e-9)
    assert s.row["t_phat_hien_s"] == "0.410" and s.verdict("N-P1") == "khong_kiem_duoc"
    # Quãng dừng của xe ảo đo đúng theo thời gian phiên, nhưng xe ảo đi 2× nhanh hơn vật và LiDAR thật: không chấm
    assert s.row["quang_dung_cm"] != "" and s.verdict("N-P2") == "khong_kiem_duoc"
    assert "2×" in s.checks["N-P2"]["note"] and "2×" in s.checks["N-P1"]["note"]
    write_csv(tmp_path / "lan_sync_marks.csv", SYNC_FIELDS, rows)                # tệp cũ: không có cột time_scale
    assert score(tmp_path, *args, scenario="VC-1", level="BT", attempt=2, expect=2) is None
    err = capsys.readouterr().err
    assert "2.000 s phiên mỗi giây thật" in err and "giả định 1×" in err


# ---------------------------------------------------------------------------------------------- lần chạy mô phỏng thật
@pytest.mark.parametrize("speed_cap", [None, 0.10])
def test_mp_vehicle_io_parking_run_scores_every_check(tmp_path, speed_cap):
    """bai_do_xe qua VehicleLink.simulated(VEHICLE_IO). Ở tốc độ mặc định (0,15 m/s của planner) tốc độ THẬT của xe
    mô phỏng trên đoạn 0,2 m vượt 0,12 m/s nên N-V1 không đạt; đặt trần 0,10 m/s (mục tiêu đợt đầu của N-V1) thì
    THANH_CONG (thử 02/10/2026)."""
    scenario = load_scenario(BAI_DO_XE)
    cfg = load_vehicle_config(scenario.vehicle_config_path)
    firmware = replace(SIM_FIRMWARE_DEFAULT, boot_hold_ms=200)
    if speed_cap is not None:
        cfg = replace(cfg, max_speed=speed_cap)
        firmware = replace(firmware, max_speed_mm_s=round(speed_cap * 1000))
    session = Session(scenario, cfg)
    assert session.plan_sync().ok and session.trajectory.n_cusps == 1
    link = VehicleLink.simulated(DriveMode.VEHICLE_IO, SimIOConfig(firmware=firmware))
    session.set_vehicle_link(link)
    session.start_run()
    run_until_done(session)
    assert session.state == SessionState.COMPLETED
    session.log.to_csv(tmp_path / "lan.csv")
    log = link.write_logs(tmp_path / "lan_vehicle_io")["link.json"].parent
    s = score(tmp_path, "--log", log, "--sim-truth", "--layout", BAI_DO_XE, level="MP")
    row = s.row
    assert float(row["sai_so_vi_tri_cm"]) == pytest.approx(session.report.position_error * 100, abs=0.1)
    assert row["trong_o"] == "co" and row["cham"] == "khong" and row["can_thiep"] == "khong"
    assert row["doi_chieu_lap"] == row["doi_chieu_thuc"] == "1"
    assert float(row["thoi_gian_s"]) == pytest.approx(link.result["t_session"], abs=0.005)
    assert row["phuong_phap_do"] == "MP+R6" and row["thu_muc_du_lieu"].endswith("lan_vehicle_io")
    failed = [code for code, c in s.checks.items() if c["verdict"] == "khong_dat"]
    too_fast = float(row["v_max_do_mps"]) > 0.12
    assert failed == (["N-V1"] if too_fast else [])                  # mọi kiểm khác đạt
    assert row["ket_qua"] == ("THAT_BAI" if too_fast else "THANH_CONG")
    if speed_cap is not None:
        assert not too_fast and row["ket_qua"] == "THANH_CONG"
    hashes = {Path(f["path"]).name: f["sha256"] for f in s.detail["inputs"]["files"]}
    assert {"link.json", "commands.csv", "telemetry.csv", "events.csv", "lan.csv", "bai_do_xe.json"} <= set(hashes)
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes.values())
    assert s.detail["git_commit"] == "test" and s.detail["thresholds"]["status"] == "DE_XUAT_CHO_CHOT"


def test_mp_sim_bundle_obstacle_run_scores_stop_distance_and_np1(scenario, cfg, tmp_path):
    session = straight_session(scenario, cfg)
    session.start_run()
    while session.world.time < 1.0:
        session.advance(0.05)
    start = session.world.state.pose
    session.inject_obstacle(Obstacle("vat_1", start.x + 0.45, start.y, 0.1, 0.1, 0.0))
    run_until_done(session)
    assert session.state == SessionState.STOPPED
    bundle = export_run(session, tmp_path / "vc1_20261002_101500_000000")
    s = score(tmp_path, "--log", bundle, "--sim-truth", "--event", "code:obstacle", scenario="VC-1", level="MP",
              detail="unused.json")
    expected_cm = (session.world.state.pose.x - start.x) * 100              # đường thẳng: quãng = hiệu x
    assert s.row["t_phat_hien_s"] == "0.000" and s.verdict("N-P1") == "dat"
    assert float(s.row["quang_dung_cm"]) == pytest.approx(expected_cm, abs=0.2)
    assert s.verdict("N-P10") == "dat" and s.verdict("N-P3") == "dat" and float(s.row["khoang_con_lai_cm"]) > 10
    assert s.row["ket_qua"] == "" and not any(c["verdict"] == "khong_dat" for c in s.checks.values())
    assert "DUNG_DUNG" in s.row["ghi_chu"]


def test_stopped_sim_parking_run_leaves_ket_qua_to_the_person(tmp_path):
    """Lần đỗ bai_do_xe (1 lần đổi chiều đã lập) ở nhánh SIM dừng vì vật chèn lúc 1 s, trước lần đổi chiều: N-D6(a)
    không xét (đường chưa đi hết), ket_qua để trống cho người chấm chọn DUNG_DUNG hay THAT_BAI."""
    layout = load_scenario(BAI_DO_XE)
    session = Session(layout, load_vehicle_config(layout.vehicle_config_path))
    assert session.plan_sync().ok and session.trajectory.n_cusps == 1
    session.start_run()
    while session.world.time < 1.0:
        session.advance(0.05)
    pose = session.world.state.pose
    session.inject_obstacle(Obstacle("vat_xa", pose.x + 0.6, pose.y + 0.6, 0.1, 0.1, 0.0))
    run_until_done(session)
    assert session.state == SessionState.STOPPED
    bundle = export_run(session, tmp_path / "do1_20261002_101500_000000")
    s = score(tmp_path, "--log", bundle, "--sim-truth", "--layout", BAI_DO_XE, level="MP")
    nd6 = s.checks["N-D6"]
    assert (s.row["doi_chieu_lap"], s.row["doi_chieu_thuc"]) == ("1", "0")
    assert nd6["detail"]["parts"]["a"] == "khong_ap_dung" and nd6["verdict"] != "khong_dat"
    assert s.row["ket_qua"] == "" and "DUNG_DUNG" in s.row["ghi_chu"]           # trước đây THAT_BAI


def stopped_vehicle_io_run(scenario, cfg, tmp_path):
    """Đường thẳng qua bo mô phỏng (VehicleLink.simulated), dừng vì vật chèn lúc 1 s; xuất như 'Xuất log CSV…' sau T9:
    `lan.csv`, `lan_vehicle_io/` và gói `lan_<giờ>/` có `vehicle_io/`. Trả (phiên, gói)."""
    session = straight_session(scenario, cfg)
    link = VehicleLink.simulated(DriveMode.VEHICLE_IO, SIM_CFG)
    session.set_vehicle_link(link)
    session.start_run()
    while session.simulating and session.world.time < 1.0:
        session.advance(0.05)
    start = session.world.state.pose
    session.inject_obstacle(Obstacle("vat_1", start.x + 0.45, start.y, 0.1, 0.1, 0.0))
    run_until_done(session)
    assert session.state == SessionState.STOPPED
    session.log.to_csv(tmp_path / "lan.csv")
    link.write_logs(tmp_path / "lan_vehicle_io")
    return session, export_run(session, tmp_path / "lan_20261002_101500_000000")


def test_vehicle_io_package_is_scored_from_its_vehicle_io_log_not_as_a_sim_bundle(scenario, cfg, tmp_path):
    """Gói T9 của lần chạy qua VehicleIO (manifest replay_kind vehicle_io_log): RunLog của gói là thế giới gương, nên
    gói được chấm như log VehicleIO từ vehicle_io/ (mức, --sim-truth, N-D6(c) theo link.json), không như gói SIM."""
    _, bundle = stopped_vehicle_io_run(scenario, cfg, tmp_path)
    assert json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))["replay_kind"] == "vehicle_io_log"
    write_csv(tmp_path / "lan_sync_marks.csv", SYNC_FIELDS, [sync_mark(1, 990.0)])     # T14 ghi cạnh lan.csv
    layout = straight_layout(tmp_path)
    s = score(tmp_path, "--log", bundle, "--sim-truth", "--layout", layout, level="MP")
    log = s.detail["log"]
    assert (log["kind"], log["mode"], log["evidence"]) == ("vehicle_io", "VEHICLE_IO", "simulation_only")
    assert Path(log["package"]) == bundle and Path(log["directory"]) == bundle / "vehicle_io"
    assert Path(log["runlog"]) == bundle / "telemetry.csv"
    assert log["detection"]["code"] == "MAP_CHANGED" and log["detection"]["origin"] == "events.csv"
    assert log["plan_source"] == "config_snapshot/run.json của gói" and s.row["doi_chieu_lap"] == "0"
    assert s.checks["N-D6"]["detail"]["parts"]["c"] == "chi_bao_so"            # bo mô phỏng: nhiễu encoder
    assert s.row["thu_muc_du_lieu"].endswith(bundle.name) and s.detail["sync_marks"].endswith("lan_sync_marks.csv")
    # Chấm thẳng <gói>/vehicle_io vẫn dùng run.json và RunLog của gói; thư mục lan_vehicle_io thì không có run.json
    s = score(tmp_path, "--log", bundle / "vehicle_io", "--sim-truth", "--layout", layout, level="MP", attempt=2)
    assert Path(s.detail["log"]["runlog"]) == bundle / "telemetry.csv" and s.row["doi_chieu_lap"] == "0"
    assert s.detail["sync_marks"].endswith("lan_sync_marks.csv")
    s = score(tmp_path, "--log", tmp_path / "lan_vehicle_io", "--sim-truth", "--layout", layout, level="MP",
              attempt=3)
    assert s.row["doi_chieu_lap"] == "" and Path(s.detail["log"]["runlog"]) == tmp_path / "lan.csv"
    assert main(["--scenario", "DO-1", "--attempt", "4", "--level", "MP", "--log", str(bundle), "--sim-truth",
                 "--layout", str(layout), "--report", str(tmp_path / "bb.csv")]) == 0
    assert (tmp_path / f"{bundle.name}.cham_DO-1_l4.json").exists()            # tệp chi tiết cạnh gói, không trong gói


def test_observe_package_is_scored_as_observe_for_zero_command(scenario, cfg, tmp_path):
    """Gói T9 của lần quan sát (OBSERVE): chế độ lấy từ link.json, nên AT-5 (0 COMMAND) chấm được; trước đây gói bị
    đọc thành gói SIM và AT-5 từ chối 'log này là SIM'."""
    session = straight_session(scenario, cfg)
    link = VehicleLink.simulated(DriveMode.OBSERVE, SIM_CFG)
    session.set_vehicle_link(link)
    session.start_run()
    link.human.set(0.1, 0.0)                                       # người lái mô phỏng chạy 0,5 s rồi bấm Dừng
    session.advance(0.5)
    session.request_stop()
    run_until_done(session)
    bundle = export_run(session, tmp_path / "quan_sat_20261002_101500_000000")
    s = score(tmp_path, "--log", bundle, scenario="AT-5", level="MP")
    assert s.detail["log"]["mode"] == "OBSERVE" and s.verdict("0-COMMAND") == "dat"


def test_sim_truth_refused_for_a_package_whose_pose_is_not_the_simulation_truth(scenario, cfg, tmp_path, capsys):
    """Gói T9 của lần chạy qua bo mô phỏng nhưng nguồn tư thế không phải SimTruthPose: RunLog của gói là ước lượng
    của hệ thống, --sim-truth bị từ chối (NGUONG quy tắc 2). Gói thiếu vehicle_io/ cũng không đọc thành gói SIM."""
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, session.scenario.start)
    session.set_vehicle_link(VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=FixedPose(io, session.scenario.start)))
    session.start_run()
    session.advance(0.5)
    session.request_stop()
    run_until_done(session)
    bundle = export_run(session, tmp_path / "lan_20261002_101500_000000")
    assert json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))["evidence"] == "simulation_only"
    layout = straight_layout(tmp_path)
    assert score(tmp_path, "--log", bundle, "--sim-truth", "--layout", layout, level="MP", expect=2) is None
    err = capsys.readouterr().err
    assert "quy tắc 2" in err and "fixed_pose" in err
    shutil.rmtree(bundle / "vehicle_io")
    assert score(tmp_path, "--log", bundle, "--sim-truth", "--layout", layout, level="MP", expect=2) is None
    assert "thiếu vehicle_io/link.json" in capsys.readouterr().err
    assert not (tmp_path / "bien_ban.csv").exists() and not (tmp_path / "chi_tiet.json").exists()


def test_default_detail_path_is_beside_the_log_folder(tmp_path):
    log = stop_log(tmp_path)
    assert main(["--scenario", "VC-1", "--attempt", "2", "--level", "XT", "--log", str(log), "--report",
                 str(tmp_path / "bb.csv")]) == 0
    detail = tmp_path / "lan_vehicle_io.cham_VC-1_l2.json"
    assert json.loads(detail.read_text(encoding="utf-8"))["identity"]["lan"] == 2


# ---------------------------------------------------------------------------------------------- từ chối, biên bản
@pytest.mark.parametrize("evidence, pose_source", [("hardware_untested", "lidar_pose"),
                                                   ("simulation_only", "no_pose_source")])
def test_sim_truth_refused_for_non_simulated_log(tmp_path, capsys, evidence, pose_source):
    log = vio_log(tmp_path, evidence=evidence, pose_source=pose_source, port=None)
    assert score(tmp_path, "--log", log, "--sim-truth", "--layout", BAI_DO_XE, level="BT", expect=2) is None
    assert "quy tắc 2" in capsys.readouterr().err
    assert not (tmp_path / "bien_ban.csv").exists() and not (tmp_path / "chi_tiet.json").exists()


def test_level_rules_mp_xt(tmp_path, capsys):
    sim = vio_log(tmp_path, name="a_vehicle_io", evidence="simulation_only", port=None,
                  pose_source="sim_truth_pose", io_simulated=True)
    real = vio_log(tmp_path, name="b_vehicle_io")
    qemu = vio_log(tmp_path, name="c_vehicle_io", port="socket://127.0.0.1:5555")
    for log, level, extra in ((sim, "XT", ()), (real, "MP", ()), (qemu, "XT/M3", ()), (sim, "XT", ("--sim-truth",)),
                              (real, "XT/M5", ())):
        assert score(tmp_path, "--log", log, "--layout", BAI_DO_XE, *extra, level=level, expect=2) is None
    err = capsys.readouterr().err
    assert err.count("LỖI:") == 5 and "mức XT cần log của bo thật" in err and "mức MP cần log mô phỏng" in err
    assert not (tmp_path / "bien_ban.csv").exists()


def manual_row(tmp_path, attempt, *extra, expect=0):
    argv = ["--scenario", "LD-1", "--attempt", str(attempt), "--level", "BT", "--when", "2026-10-02 09:30",
            "--report", str(tmp_path / "bb.csv"), *extra]
    assert main(argv) == expect


def test_report_header_bom_and_append(tmp_path):
    manual_row(tmp_path, 1, "--result", "DUNG_DUNG")
    manual_row(tmp_path, 2, "--result", "DUNG_DUNG", "--note", "laptop")
    raw = (tmp_path / "bb.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    with (tmp_path / "bb.csv").open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert reader.fieldnames == BIEN_BAN_FIELDS
    assert [r["lan"] for r in rows] == ["1", "2"] and rows[1]["ghi_chu"].startswith("laptop")


def test_duplicate_attempt_refused_then_replaced(tmp_path, capsys):
    manual_row(tmp_path, 1, "--result", "DUNG_DUNG")
    manual_row(tmp_path, 1, "--result", "DUNG_DUNG", "--note", "lần hai", expect=2)
    assert "--replace" in capsys.readouterr().err
    manual_row(tmp_path, 1, "--result", "DUNG_DUNG", "--note", "lần hai", "--replace")
    with (tmp_path / "bb.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1 and rows[0]["ghi_chu"].startswith("lần hai")
    assert not (tmp_path / "bb.csv.tmp").exists()


def test_unknown_scenario_lists_known_keys(tmp_path, capsys):
    assert main(["--scenario", "DO1", "--attempt", "1", "--level", "MP", "--dry-run"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("LỖI:") and "DO-1" in err and "DO-3a" in err
    assert main(["--scenario", "VC-5", "--attempt", "1", "--level", "MP", "--dry-run"]) == 2
    assert "VC-5do, VC-5dung" in capsys.readouterr().err
    assert main(["--scenario", "DO-3a", "--attempt", "1", "--level", "MP", "--dry-run"]) == 2   # biến thể ở --variant
    assert "--variant" in capsys.readouterr().err


def test_that_bai_or_khong_tinh_needs_cause_and_manual_group_needs_no_log(tmp_path, capsys):
    manual_row(tmp_path, 1, "--result", "KHONG_TINH", expect=2)
    assert "--cause" in capsys.readouterr().err and not (tmp_path / "bb.csv").exists()
    manual_row(tmp_path, 1, "--result", "KHONG_TINH", "--cause", "dụng cụ đo", "--methods", "R3")
    with (tmp_path / "bb.csv").open(encoding="utf-8-sig", newline="") as f:
        row = next(csv.DictReader(f))
    filled = {k for k, v in row.items() if v}
    assert filled == {"ma_kich_ban", "lan", "ngay_gio", "muc_thu", "ket_qua", "nguyen_nhan", "phuong_phap_do",
                      "ghi_chu"}
    assert row["ket_qua"] == "KHONG_TINH" and row["ngay_gio"] == "2026-10-02 09:30" and row["phuong_phap_do"] == "R3"
    assert main(["--scenario", "DO-1", "--attempt", "1", "--level", "MP", "--dry-run"]) == 2      # có kiểm, thiếu log
    assert "cần --log" in capsys.readouterr().err


def test_dry_run_writes_nothing(tmp_path, capsys):
    log = stop_log(tmp_path)
    assert main(["--scenario", "VC-1", "--attempt", "1", "--level", "XT", "--log", str(log), "--event", "session:5.0",
                 "--report", str(tmp_path / "bb.csv"), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "N-P1 t_phát_hiện − t_vật: 0.150 s ≤ 0.4 s → đạt" in out and "không ghi tệp nào" in out
    assert sorted(p.name for p in tmp_path.iterdir()) == ["lan_vehicle_io"]


def test_malformed_inputs_are_refused(tmp_path, capsys):
    log = stop_log(tmp_path)
    ref = write_track(tmp_path / "r1.csv", braking_motion, 8.0)
    for extra in (("--r2-points", "1,2,3"), ("--time-error", "nan"), ("--event", "frame:9999", "--reference", ref),
                  ("--sync", "12.3", "--reference", ref), ("--when", "02/10/2026")):
        assert score(tmp_path, "--log", log, *extra, scenario="VC-1", expect=2) is None
    assert capsys.readouterr().err.count("LỖI:") == 5
    assert not (tmp_path / "bien_ban.csv").exists()


def test_thresholds_file_matches_nguong_doc_and_rejects_unknown_keys(tmp_path):
    t = load_thresholds()
    assert t.status == "DE_XUAT_CHO_CHOT" and t.reference_ratio == 3.0
    assert (t.limit("N-D1", "max_cm"), t.limit("N-D2", "max_deg"), t.limit("N-V1", "max_mps"),
            t.limit("N-P1", "max_s")) == (5.0, 5.0, 0.12, 0.4)
    nguong = (PROJECT_ROOT / "docs" / "NGUONG_NGHIEM_THU_DE_XUAT.md").read_text(encoding="utf-8")
    rows = {line.split("|")[1].strip(): line for line in nguong.splitlines() if line.startswith("| N-")}
    assert "≤ 5 cm" in rows["N-D1"] and "≤ 5°" in rows["N-D2"] and "≤ 0,4 s" in rows["N-P1"]
    assert "1,2 × 0,10 m/s" in rows["N-V1"] and "≥ 2 cm" in rows["N-D5"] and "≥ 10 cm" in rows["N-P3"]
    kich_ban = (PROJECT_ROOT / "docs" / "KICH_BAN_NGHIEM_THU.md").read_text(encoding="utf-8")
    section = kich_ban.split("## 4. Bảng tổng hợp kịch bản")[1].split("## 5.")[0]
    codes = re.findall(r"^\| ([A-Z]{2}-\d) \|", section, flags=re.M)
    assert len(codes) == 37
    for code in codes:
        assert any(k == code or (k.startswith(code) and not k[len(code)].isdigit()) for k in t.scenarios), code
    assert {"VC-5dung", "VC-5do"} <= set(t.scenarios)
    data = json.loads((PROJECT_ROOT / "configs" / "nguong_nghiem_thu.json").read_text(encoding="utf-8"))
    for mutate in (lambda d: d.update(extra=1), lambda d: d["limits"]["N-D1"].update(min_cm=1.0),
                   lambda d: d["scenarios"]["DO-1"]["checks"].append("N-X9"),
                   lambda d: d["analysis"].update(smooth_s=float("nan"))):
        broken = json.loads(json.dumps(data))
        mutate(broken)
        path = tmp_path / "nguong.json"
        path.write_text(json.dumps(broken), encoding="utf-8")
        with pytest.raises(ValueError):
            load_thresholds(path)
