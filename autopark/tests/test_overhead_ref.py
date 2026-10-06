"""Tham chiếu trên cao R1 (T4, `autopark.evaluation.overhead_ref`, thêm 02/10/2026) trên bộ thử TỔNG HỢP: tệp mốc,
cấu hình marker xe, nội tham, khớp mặt sàn, tư thế từng khung (bù độ cao), camera dịch, lệnh `track` ghi đúng hợp đồng
`reference_pose` và T5 đọc được. Không mở camera hay cổng COM nào; mọi tệp ghi trong tmp_path hay thư mục tạm của bộ thử.
Sửa 02/10/2026 (đợt 2): AVI không kèm tệp của bộ ghi chỉ có số khung/s danh định (từ chối trừ khi --allow-nominal-fps),
video của bộ ghi chép thiếu .json / .frames.csv bị từ chối, --sync-error / --capture-latency-s kiểm trước khi mở video.
"""
import csv
from dataclasses import replace
import json
import math
from pathlib import Path
import shutil

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from autopark.domain.types import Pose  # noqa: E402
from autopark.evaluation import overhead_ref as R  # noqa: E402
from autopark.evaluation import overhead_synth as S  # noqa: E402
from autopark.evaluation.reference_pose import read_reference  # noqa: E402
from autopark.evaluation.score_run import analyse_reference, load_thresholds  # noqa: E402
from autopark.lidar import recording as lidar_recording  # noqa: E402
from autopark.video.overhead_record import OverheadRecorder  # noqa: E402
from tests.conftest import PROJECT_ROOT  # noqa: E402
from tests.overhead_set import copy_run, floor_fit_path, small_set  # noqa: E402

SURVEY_HEADER = "ten,vai_tro,x_m,y_m,z_m,ma_aruco,nguoi_do,ngay,ghi_chu\n"


@pytest.fixture(autouse=True)
def no_git(monkeypatch):
    monkeypatch.setattr(lidar_recording, "git_commit", lambda: "test")     # không gọi git mỗi lần ghi


def survey_rows() -> list[dict]:
    with open(small_set()["survey"], encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_survey(path: Path, rows: list[dict]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return path


def empty_floor() -> np.ndarray:
    return cv2.imread(small_set()["floor_image"])


def intrinsics():
    return R.load_overhead_intrinsics(small_set()["intrinsics"])


def track(tmp_path: Path, *extra, video=None, out="tu_the_tham_chieu.csv", markers=None, floor=None) -> int:
    info = small_set()
    return R.main(["track", "--video", str(video or info["run"]), "--floor", str(floor or floor_fit_path()),
                   "--markers", str(markers or info["markers"]), "--out", str(tmp_path / out), *map(str, extra)])


# ---------------------------------------------------------------------------------------------- tệp mốc, marker, nội tham
def test_survey_csv_rules(tmp_path):
    path = tmp_path / "moc.csv"
    path.write_text(SURVEY_HEADER + "K1,kiem_soat,0.5,1.0,,3,An,02/10/2026,\nK2,kiem_soat,,,,4,,,chưa đo\n",
                    encoding="utf-8-sig")                                              # BOM của Excel: nhận
    survey = R.read_survey(path)
    assert [p.name for p in survey.points] == ["K1", "K2"] and [p.name for p in survey.unmeasured] == ["K2"]
    assert survey.points[0].z == 0.0 and survey.sha256
    bad = {"K1,kiem_soat,0.5,1.0,,3,An,02/10/2026,\nK1,kiem_tra,1,1,,5,An,02/10/2026,\n": ("dòng 3", "trùng"),
           "K1,kiem_soat,0.5,1.0,,3,An,02/10/2026,\nK3,kiem_tra,1,1,,3,An,02/10/2026,\n": ("dòng 3", "trùng với mốc K1"),
           "K1,kiemsoat,0.5,1.0,,3,An,02/10/2026,\n": ("dòng 2", "vai_tro"),
           "K1,kiem_soat,0,5,1.0,,3,An,02/10/2026,\n": ("dòng 2", "dấu CHẤM"),
           'K1,kiem_soat,"0,5",1.0,,3,An,02/10/2026,\n': ("dòng 2", "dấu CHẤM"),
           "K1,kiem_soat,0.5,1.0,,3,,02/10/2026,\n": ("dòng 2", "nguoi_do"),
           "K1,kiem_soat,0.5,1.0,,3,An,2026-10-02,\n": ("dòng 2", "dd/mm/yyyy"),
           "K1,kiem_soat,0.5,1.0,,48,An,02/10/2026,\n": ("dòng 2", "marker xe"),
           "K1,kiem_soat,0.5,,,3,An,02/10/2026,\n": ("dòng 2", "cùng có hoặc cùng trống")}
    for body, (line, words) in bad.items():
        path.write_text(SURVEY_HEADER + body, encoding="utf-8")
        with pytest.raises(R.OverheadError) as err:
            R.read_survey(path)
        assert line in str(err.value) and words in str(err.value), body
    # dòng chưa đo được liệt kê nhưng không bao giờ dùng để khớp
    rows = survey_rows()
    rows[7]["x_m"] = rows[7]["y_m"] = ""
    fit = R.fit_floor([empty_floor()], intrinsics(), R.read_survey(write_survey(tmp_path / "chua_do.csv", rows)))
    assert rows[7]["ten"] not in fit.used
    assert next(m for m in fit.missing if m["ten"] == rows[7]["ten"])["reason"].startswith("chưa đo")


def test_survey_template_names_ids_and_refuses_too_many_for_dict50(tmp_path, capsys):
    out = tmp_path / "moc_sa_ban.csv"
    info = R.write_survey_template(out, (3.0, 2.0), 0.5, 8)
    assert info["control"] == 35 and info["check"] == 8 and info["ids"] == list(range(43))
    survey = R.read_survey(out)
    names = [p.name for p in survey.points]
    assert names[:3] == ["K_x000_y000", "K_x050_y000", "K_x100_y000"] and "K_x300_y200" in names
    assert names[35:] == [f"T{k:02d}" for k in range(1, 9)] and len(survey.unmeasured) == 43
    with out.open(encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert header[-2:] == ["x_danh_dinh_m", "y_danh_dinh_m"]
    with pytest.raises(R.OverheadError, match="đã có"):
        R.write_survey_template(out, (3.0, 2.0), 0.5, 8)
    with pytest.raises(R.OverheadError, match="DICT_4X4_100"):
        R.write_survey_template(tmp_path / "lon.csv", (4.0, 3.0), 0.5, 8)
    big = R.write_survey_template(tmp_path / "lon.csv", (4.0, 3.0), 0.5, 8, "DICT_4X4_100")
    assert 48 not in big["ids"] and 49 not in big["ids"] and max(big["ids"]) == 72
    assert R.main(["survey-template", "--size", "2.0x1.0", "--out", str(tmp_path / "nho.csv")]) == 0
    assert "autopark.perception.aruco_sheet --ids 0-22" in capsys.readouterr().out


def test_vehicle_markers_config_needs_exactly_two_markers_measured_flag_and_sane_geometry():
    base = S.vehicle_markers_record()
    car = R.parse_vehicle_markers(base)
    assert car.distance_m == pytest.approx(0.30) and car.ids == (48, 49) and not car.warnings

    def broken(change):
        data = json.loads(json.dumps(base))
        change(data)
        return data

    cases = [(lambda d: d["markers"].append(dict(d["markers"][0], id=47)), "ĐÚNG hai marker"),
             (lambda d: d["markers"][1].update(id=48), "khác mã"),
             (lambda d: d["markers"][1].update(x_m=0.10), "< 0.15"),
             (lambda d: d["markers"][0].update(z_m=0.6), "z_m"),
             (lambda d: d["markers"][0].update(side_m=80), "đơn vị mét"),
             (lambda d: d.pop("measured"), "measured"),
             (lambda d: d.update(extra=1), "khóa lạ"),
             (lambda d: d["markers"][1].update(role="sau"), "cùng role"),
             (lambda d: d["r2_points_m"].pop("truoc"), "r2_points_m"),
             (lambda d: d.update(format="x"), "format")]
    for change, words in cases:
        with pytest.raises(R.OverheadError, match=words):
            R.parse_vehicle_markers(broken(change))
    near = R.parse_vehicle_markers(broken(lambda d: d["markers"][1].update(x_m=0.20)))
    assert near.warnings and "√2·σ/d" in near.warnings[0]
    template = R.load_vehicle_markers(PROJECT_ROOT / "configs" / "tham_chieu" / "xe_gia_v0.json")
    assert template.measured is False and not template.synthetic and template.r2_points["truoc"] == (0.55, 0.05)


def test_intrinsics_of_a_hub_camera_or_another_size_are_refused(tmp_path, capsys):
    record = json.loads(Path(small_set()["intrinsics"]).read_text(encoding="utf-8"))
    hub = tmp_path / "cam_p1.json"
    hub.write_text(json.dumps(dict(record, camera=dict(record["camera"], hub_port=1))), encoding="utf-8")
    with pytest.raises(R.OverheadError, match="camera riêng"):
        R.load_overhead_intrinsics(hub)
    with pytest.raises(R.OverheadError, match="chưa có tệp nội tham"):
        R.load_overhead_intrinsics(tmp_path / "khong_co.json")
    small = tmp_path / "cam_tren_cao_640x480.json"
    small.write_text(json.dumps(dict(record, image_size=[640, 480])), encoding="utf-8")
    out = tmp_path / "mat_san.json"
    assert R.main(["floor", "--intrinsics", str(small), "--survey", small_set()["survey"], "--image",
                   small_set()["floor_image"], "--out", str(out)]) == 2
    assert "nội tham là 640×480" in capsys.readouterr().err and not out.exists()
    intr = intrinsics()
    assert intr.synthetic and intr.acceptance_all_pass is True and intr.camera["hub_port"] is None


# ---------------------------------------------------------------------------------------------- khớp mặt sàn
def test_floor_fit_recovers_camera_and_meets_check_points():
    path = floor_fit_path()
    fit = R.load_floor_fit(path)
    truth = small_set()["camera"]
    assert np.linalg.norm(fit.camera.centre - truth.centre) < 0.010
    assert fit.ok and fit.synthetic and len(fit.used) == 24 and fit.check["n"] == 8
    assert fit.check["max_m"] <= 0.003 and fit.record["fit"]["rms_px"] < 0.5
    assert fit.record["thresholds"]["status"].startswith("ĐỀ XUẤT – CHỜ CHỐT")
    assert fit.sha256 == R.file_sha256(path) and fit.record["detector"]["refine"] == "contour"
    assert path.with_name("mat_san_xem.jpg").stat().st_size > 10_000
    for key in ("homography_check", "radial_trend", "extrapolated", "gsd_mm_per_px", "coverage", "acceptance"):
        assert key in fit.diagnostics
    assert fit.diagnostics["homography_check"]["max_diff_m"] < 0.003
    assert fit.diagnostics["radial_trend"]["flagged"] is False
    assert [u["ok"] for u in fit.diagnostics["acceptance"]["usable_floor_for"]] == [True, True, True]
    again = R.floor_fit_from_record(json.loads(path.read_text(encoding="utf-8")))
    assert np.allclose(again.camera.R, fit.camera.R) and again.used == fit.used
    assert any("ĐẠT" in line for line in R.floor_summary_lines(fit))


def test_floor_from_video_warns_when_the_car_is_in_view_and_reports_layout_coverage(tmp_path):
    info = small_set()
    out = tmp_path / "mat_san.json"
    code = R.main(["floor", "--intrinsics", info["intrinsics"], "--survey", info["survey"], "--video", info["run"],
                   "--frames", "4", "--layout", str(PROJECT_ROOT / "scenarios" / "bai_do_xe.json"), "--out", str(out)])
    assert code in (0, 1)
    fit = R.load_floor_fit(out)
    assert any("xe/xe giả đang nằm trong ảnh sàn trống" in w for w in fit.warnings)
    assert fit.record["images"][0]["frames"] == 4 and fit.record["images"][0]["sha256"] == R.file_sha256(info["run"])
    assert 0.0 < fit.diagnostics["coverage"]["fraction_visible"] <= 1.0
    assert out.with_name("mat_san_xem.jpg").exists()


def test_check_summarises_t4_files(tracked, tmp_path, capsys):
    info = small_set()
    for path in (floor_fit_path(), info["markers"], Path(info["out"]) / "chay_01.json", tracked,
                 tracked.with_suffix(".json"), info["survey"], info["tc1_poses"],
                 PROJECT_ROOT / "configs" / "tham_chieu" / "xe_gia_v0.json"):
        assert R.main(["check", str(path)]) == 0, path
    out = capsys.readouterr().out
    for words in ("khớp mặt sàn mat_san.json", "cấu hình marker xe_gia_tong_hop: ĐÃ ĐO", "bản ghi chay_01.json: xong",
                  "tham chiếu R1 tu_the_tham_chieu.csv: 40 dòng", "tệp mốc moc_sa_ban.csv: 32 mốc",
                  "bảng tư thế TC-1 tc1_tong_hop.csv: 10 tư thế", "GIẢ ĐỊNH (chưa đo)"):
        assert words in out, words
    (tmp_path / "la.json").write_text("{}", encoding="utf-8")
    assert R.main(["check", str(tmp_path / "la.json")]) == 2


def test_synthetic_command_writes_a_small_labelled_set(tmp_path, capsys):
    out = tmp_path / "tong_hop"
    assert R.main(["synthetic", "--out", str(out), "--size", "640x360", "--frames", "6", "--tc1-poses", "2",
                   "--tc1-frames", "3"]) == 0
    readme = (out / "README.txt").read_text(encoding="utf-8")
    assert readme.startswith(R.SYNTHETIC_LABEL) and " floor --intrinsics " in readme and " track --video " in readme
    assert (out / "calibration" / "cam_tren_cao_tong_hop_640x360.json").exists() and (out / "tc1" / "tu_the_02.avi").exists()
    assert R.main(["synthetic", "--out", str(PROJECT_ROOT / "calibration" / "tong_hop_thu")]) == 2
    assert "không được ghi vào" in capsys.readouterr().err
    assert not (PROJECT_ROOT / "calibration" / "tong_hop_thu").exists()


def test_a_mismeasured_control_point_is_dropped_by_name(tmp_path):
    rows = survey_rows()
    victim = next(r for r in rows if r["ten"] == "K_x100_y050")
    victim["x_m"] = f"{float(victim['x_m']) + 0.03:.4f}"                                # thước đọc sai 3 cm
    fit = R.fit_floor([empty_floor()], intrinsics(), R.read_survey(write_survey(tmp_path / "moc.csv", rows)))
    assert [d["ten"] for d in fit.dropped] == ["K_x100_y050"] and "lệch" in fit.dropped[0]["reason"]
    assert fit.dropped[0]["err_m"] > 0.02 and fit.check["max_m"] <= 0.003 and fit.ok


def test_mirrored_survey_and_cm_units_are_refused_with_hints(tmp_path, capsys):
    rows = survey_rows()
    mirrored = [dict(r, y_m=f"{1.5 - float(r['y_m']):.4f}") for r in rows]            # y sang PHẢI
    with pytest.raises(R.OverheadError, match="TRÁI"):
        R.fit_floor([empty_floor()], intrinsics(), R.read_survey(write_survey(tmp_path / "guong.csv", mirrored)))
    cm = [dict(r, x_m=f"{float(r['x_m']) * 100:.2f}", y_m=f"{float(r['y_m']) * 100:.2f}") for r in rows]
    path = write_survey(tmp_path / "cm.csv", cm)
    with pytest.raises(R.OverheadError, match="cm"):
        R.fit_floor([empty_floor()], intrinsics(), R.read_survey(path))
    assert R.main(["floor", "--intrinsics", small_set()["intrinsics"], "--survey", str(path), "--image",
                   small_set()["floor_image"], "--out", str(tmp_path / "x.json")]) == 2
    assert "MÉT" in capsys.readouterr().err and not (tmp_path / "x.json").exists()


def test_missing_markers_report_outside_frame_and_too_small_modules(tmp_path):
    info = small_set()
    floor = list(info["floor_markers"]) + [S.FloorMarker("NHO", 40, -0.15, 0.75, 0.040)]   # marker 40 mm
    image = S.OverheadRenderer(info["camera"], "DICT_4X4_50", floor).frame(rng=np.random.default_rng(5))
    rows = survey_rows() + [
        {"ten": "NHO", "vai_tro": "kiem_tra", "x_m": "-0.15", "y_m": "0.75", "z_m": "0", "ma_aruco": "40",
         "nguoi_do": "T", "ngay": "02/10/2026", "ghi_chu": ""},
        {"ten": "XA", "vai_tro": "kiem_tra", "x_m": "4.0", "y_m": "0.75", "z_m": "0", "ma_aruco": "41",
         "nguoi_do": "T", "ngay": "02/10/2026", "ghi_chu": "ngoài sa bàn"}]
    fit = R.fit_floor([image], intrinsics(), R.read_survey(write_survey(tmp_path / "moc.csv", rows)),
                      floor_marker_mm=40.0)
    missing = {m["ten"]: m for m in fit.missing}
    assert set(missing) == {"NHO", "XA"}
    assert missing["NHO"]["reason"].startswith("quá nhỏ") and missing["NHO"]["module_px"] < 4.5
    assert missing["XA"]["reason"] == "ngoài khung hình"
    assert any("không dùng được" in w for w in fit.warnings)


def test_manual_click_points_are_used_with_source_click(tmp_path):
    rows = survey_rows()
    rows[6]["ma_aruco"] = ""                                       # mốc chỉ có dấu băng dính: phải chấm tay
    name = rows[6]["ten"]
    path = write_survey(tmp_path / "moc.csv", rows)
    fit = R.fit_floor([empty_floor()], intrinsics(), R.read_survey(path))
    assert name not in fit.used and next(m for m in fit.missing if m["ten"] == name)["reason"].startswith("chưa chấm")
    cam = small_set()["camera"]
    uv = cam.project([[float(rows[6]["x_m"]), float(rows[6]["y_m"]), 0.0]])[0]
    clicks = tmp_path / "cham.json"
    clicks.write_text(json.dumps({"points": [{"ten": name, "u": float(uv[0]), "v": float(uv[1])}]}), encoding="utf-8")
    out = tmp_path / "mat_san.json"
    assert R.main(["floor", "--intrinsics", small_set()["intrinsics"], "--survey", str(path), "--image",
                   small_set()["floor_image"], "--clicks", str(clicks), "--out", str(out)]) == 0
    fit = R.load_floor_fit(out)
    det = next(d for d in fit.detections if d["ten"] == name)
    assert det["source"] == "click" and name in fit.used and fit.ok


# ---------------------------------------------------------------------------------------------- tư thế từng khung
def car():
    return R.load_vehicle_markers(small_set()["markers"])


def test_car_pose_with_height_compensation():
    info = small_set()
    fit = R.load_floor_fit(floor_fit_path())
    rng = np.random.default_rng(11)
    poses = S.tc1_pose_set((2.5, 1.5), 4) + [Pose(1.0, 0.8, math.radians(100.0)), Pose(1.5, 0.5, math.radians(-35))]
    assert len({round(math.degrees(p.yaw)) for p in poses}) >= 3
    for pose in poses:
        image = info["renderer"].frame(pose, info["plate"], rng=rng)
        fp = R.solve_frame(R.detect_markers(image, fit.detector), fit, car())
        assert fp.valid and fp.n_markers == 2, fp.reason
        assert math.hypot(fp.pose.x - pose.x, fp.pose.y - pose.y) <= 0.003
        assert abs(math.degrees(fp.pose.yaw - pose.yaw + math.pi) % 360 - 180) <= 0.3
        assert abs(fp.pair_err_m) < 0.003 and all(abs(e) < 0.08 for e in fp.side_err.values())


def test_wrong_marker_height_is_caught_by_pair_distance():
    info = small_set()
    fit = R.load_floor_fit(floor_fit_path())
    flat = R.parse_vehicle_markers(S.vehicle_markers_record(z=0.0))           # cấu hình ghi z_m = 0, thật 0,10 m
    pose = S.tc1_pose_set((2.5, 1.5), 1)[0]                                    # gần góc sa bàn: thị sai lớn
    image = info["renderer"].frame(pose, info["plate"], rng=np.random.default_rng(3))
    found = R.detect_markers(image, fit.detector)
    fp = R.solve_frame(found, fit, flat)
    assert not fp.valid and "khoảng cách hai marker lệch" in fp.reason and fp.pair_err_m > 0.005
    centres = [R.marker_on_plane(found[m.marker_id], fit.camera, 0.0).centre for m in flat.markers]
    forced = (centres[0] + centres[1]) / 2 - np.array([math.cos(pose.yaw), math.sin(pose.yaw)]) * 0.15
    assert math.hypot(forced[0] - pose.x, forced[1] - pose.y) > 0.030        # không có phép kiểm thì lệch > 3 cm


def test_single_marker_frames_invalid_by_default_flagged_when_allowed():
    info = small_set()
    fit = R.load_floor_fit(floor_fit_path())
    pose = Pose(1.0, 0.6, math.radians(20.0))
    front = (pose.x + 0.30 * math.cos(pose.yaw), pose.y + 0.30 * math.sin(pose.yaw))
    hand = S.Occluder(front[0] - 0.09, front[0] + 0.09, front[1] - 0.09, front[1] + 0.09, 0.30)
    image = info["renderer"].frame(pose, info["plate"], rng=np.random.default_rng(4), occluders=[hand])
    found = R.detect_markers(image, fit.detector)
    assert 48 in found and 49 not in found
    fp = R.solve_frame(found, fit, car())
    assert not fp.valid and fp.reason == "chỉ thấy marker sau" and fp.n_markers == 1
    fp = R.solve_frame(found, fit, car(), min_markers=1)
    assert fp.valid and fp.n_markers == 1 and any("một marker" in f for f in fp.flags)
    assert abs(math.degrees(fp.pose.yaw - pose.yaw)) <= 2.0 and math.hypot(fp.pose.x - pose.x, fp.pose.y - pose.y) < 0.01


# ---------------------------------------------------------------------------------------------- lệnh track → T5
@pytest.fixture(scope="module")
def tracked(tmp_path_factory):
    out = tmp_path_factory.mktemp("track")
    assert track(out) == 0
    return out / "tu_the_tham_chieu.csv"


def test_track_cli_writes_a_reference_that_read_reference_accepts(tracked):
    ref = read_reference(tracked)
    with open(Path(small_set()["out"]) / "chay_01.frames.csv", encoding="utf-8") as f:
        frames = list(csv.DictReader(f))
    assert len(ref.samples) == len(frames) == 40 and len(ref.valid_samples) == 40
    assert [s.frame for s in ref.samples] == list(range(40))
    assert [s.t for s in ref.samples] == [round(float(r["t_perf"]), 4) for r in frames]
    meta = ref.meta
    assert meta.method == "R1" and meta.clock == "perf_counter" and meta.sync_error_s == pytest.approx(0.15)
    assert "CHƯA ĐO" in meta.notes and meta.notes.startswith("TỔNG HỢP — KHÔNG PHẢI SỐ ĐO")
    assert meta.accuracy.pos_max_m is None and meta.accuracy.source == "chưa làm TC-1"
    assert meta.source["synthetic"] is True and meta.source["counts"]["valid"] == 40
    assert meta.source["floor_sha256"] == R.file_sha256(floor_fit_path()) and meta.tool.endswith("track")
    detail = tracked.with_name("tu_the_tham_chieu.chi_tiet.csv")
    with detail.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert reader.fieldnames == R.DETAIL_FIELDS and len(rows) == 40 and rows[0]["floor_seen"] not in ("", "0")


def test_t4_reference_feeds_t5_analysis(tracked):
    an = analyse_reference(read_reference(tracked), load_thresholds().analysis)
    truth = small_set()["truth_poses"][-1]
    assert an.final_pose is not None, an.notes
    assert math.hypot(an.final_pose.x - truth.x, an.final_pose.y - truth.y) <= 0.003
    assert abs(math.degrees(an.final_pose.yaw - truth.yaw)) <= 0.3
    assert read_reference(tracked).has_trajectory and an.two_marker_fraction >= 0.9 and an.moving_gap is None


def test_camera_bump_is_detected(tmp_path):
    info = small_set()
    stamps = S.camera_stamps(40, 30000.0)
    rec = OverheadRecorder(tmp_path, "va_lech", synthetic=True)
    rec.start(960, 540, {"name": "tren_cao_tong_hop"})
    rng = np.random.default_rng(9)
    pose = Pose(1.2, 0.7, 0.5)
    for k, t in enumerate(stamps):
        rec.add(info["renderer"].frame(pose, info["plate"], rng=rng, camera_offset=(0.3, 0, 0) if k >= 20 else None),
                t)
    rec.stop()
    assert track(tmp_path, video=tmp_path / "va_lech.avi") == 1
    ref = read_reference(tmp_path / "tu_the_tham_chieu.csv")
    assert ref.meta.source["camera_shift"]["moved_at"] == 20
    assert [s.valid for s in ref.samples] == [True] * 20 + [False] * 20
    with open(tmp_path / "tu_the_tham_chieu.chi_tiet.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert all("camera trên cao đã dịch" in r["reason"] for r in rows[20:])
    assert float(rows[30]["floor_shift_px"]) > 2.0 and float(rows[5]["floor_shift_px"]) < 0.3


def test_frames_csv_count_mismatch_and_nominal_fps_video_are_refused(tmp_path, capsys):
    video = copy_run(tmp_path / "thieu")
    frames = video.with_name("chay_01.frames.csv")
    frames.write_text("".join(frames.read_text(encoding="utf-8").splitlines(keepends=True)[:-1]), encoding="utf-8")
    assert track(tmp_path, video=video) == 2
    assert "không khớp" in capsys.readouterr().err and not (tmp_path / "tu_the_tham_chieu.csv").exists()
    # AVI thật không kèm tệp của bộ ghi (sửa 02/10/2026: trước đây test thay nguồn bằng đồng hồ 'index' giả, còn AVI
    # thật thì được nhận làm đồng hồ 'video' với thời điểm = chỉ số / 30)
    bare = tmp_path / "tran" / "quay_tay.avi"
    bare.parent.mkdir()
    shutil.copy2(small_set()["run"], bare)
    assert R.nominal_fps_container(bare) and not R.nominal_fps_container(small_set()["survey"])
    assert track(tmp_path, "--window", "0,0.5", video=bare) == 2
    err = capsys.readouterr().err
    assert "--allow-nominal-fps" in err and "AVI" in err and not (tmp_path / "tu_the_tham_chieu.csv").exists()
    assert track(tmp_path, "--window", "0,0.5", "--allow-nominal-fps", video=bare) == 0
    ref = read_reference(tmp_path / "tu_the_tham_chieu.csv")
    assert ref.meta.clock == "video" and "danh định" in ref.meta.notes and len(ref.samples) >= 10
    assert "không kiểm được video có phải TỔNG HỢP" in ref.meta.notes and "nominal_fps" in ref.meta.source["allow"]
    assert [s.t for s in ref.samples[:4]] == pytest.approx([0.0, 1 / 30, 2 / 30, 3 / 30], abs=1e-4)   # danh định


def test_recorder_video_with_a_missing_companion_file_is_refused(tmp_path, capsys):
    """Video của bộ ghi chép thiếu .json (hay thiếu .frames.csv): từ chối thay vì lặng lẽ bỏ stamp perf_counter thật của
    frames.csv (kể cả khi chỉ ra --frames-csv) và mất cờ TỔNG HỢP của JSON."""
    no_json = copy_run(tmp_path / "thieu_json")
    no_json.with_suffix(".json").unlink()
    frames = no_json.with_name("chay_01.frames.csv")
    for extra in ((), ("--frames-csv", frames), ("--allow-nominal-fps",)):
        assert track(tmp_path, *extra, video=no_json) == 2, extra
        err = capsys.readouterr().err
        assert "thiếu chay_01.json" in err and "chép đủ các tệp của lần ghi" in err, extra
    no_csv = copy_run(tmp_path / "thieu_csv")
    no_csv.with_name("chay_01.frames.csv").unlink()
    assert track(tmp_path, "--allow-nominal-fps", video=no_csv) == 2
    assert "thiếu chay_01.frames.csv" in capsys.readouterr().err
    assert not list(tmp_path.glob("tu_the_tham_chieu*"))
    with pytest.raises(R.OverheadError, match="thiếu chay_01.json"):
        R.OverheadVideo(no_json, frames)
    images, infos = R.floor_inputs(video=no_json, frames=3)                   # khớp mặt sàn chỉ cần ảnh: nhận
    assert len(images) == 3 and infos[0]["frames"] == 3


def test_non_avi_video_whose_position_clock_fails_needs_allow_nominal_fps(tmp_path, monkeypatch, capsys):
    """Tệp không phải AVI (MKV) có thời điểm từng khung; khi vị trí khung thôi tăng ngặt (`VideoFileSource` rơi về chỉ
    số / số khung/s) thì vẫn từ chối trừ khi --allow-nominal-fps."""
    mkv = tmp_path / "may_khac.mkv"
    cap = cv2.VideoCapture(small_set()["run"])
    writer = cv2.VideoWriter(str(mkv), cv2.VideoWriter_fourcc(*"MJPG"), 30.0, (960, 540))
    writer.set(cv2.VIDEOWRITER_PROP_QUALITY, 95.0)
    for _ in range(20):
        ok, image = cap.read()
        writer.write(image)
    writer.release()
    cap.release()
    assert not R.nominal_fps_container(mkv) and R.OverheadVideo(mkv).clock == "video"
    real_open = R._open_video_source

    class NominalClock:
        def __init__(self, path):
            self.inner = real_open(path)
            self.clock_source = "index"                                       # tệp chỉ cho số khung/s danh định

        def read(self):
            return self.inner.read()

        def close(self):
            self.inner.close()

    monkeypatch.setattr(R, "_open_video_source", NominalClock)
    assert track(tmp_path, "--window", "0,0.3", video=mkv) == 2
    assert "--allow-nominal-fps" in capsys.readouterr().err and not (tmp_path / "tu_the_tham_chieu.csv").exists()
    assert track(tmp_path, "--window", "0,0.3", "--allow-nominal-fps", video=mkv) == 0
    ref = read_reference(tmp_path / "tu_the_tham_chieu.csv")
    assert ref.meta.clock == "video" and "danh định từ khung 0" in ref.meta.notes


def test_outputs_are_never_overwritten_silently(tmp_path, capsys):
    assert track(tmp_path, "--window", "0,0.3") == 0
    first = (tmp_path / "tu_the_tham_chieu.csv").read_bytes()
    assert track(tmp_path, "--window", "0,0.6") == 2
    assert "--overwrite" in capsys.readouterr().err
    assert (tmp_path / "tu_the_tham_chieu.csv").read_bytes() == first
    assert track(tmp_path, "--window", "0,0.6", "--overwrite") == 0
    backups = sorted(p.name for p in tmp_path.glob("*.bak_*"))
    assert len(backups) == 3 and (tmp_path / "tu_the_tham_chieu.csv").read_bytes() != first
    fit = R.load_floor_fit(floor_fit_path())
    with pytest.raises(R.OverheadError, match="đã có"):
        R.save_floor_fit(floor_fit_path(), fit)


def test_bad_sync_error_or_capture_latency_refused_before_the_video_and_nothing_half_written(tmp_path, monkeypatch,
                                                                                             capsys):
    """--capture-latency-s / --sync-error âm hay nan: mã 2 trước khi mở video, không ghi gì (trước đây: xử lý hết video,
    ghi tệp chi tiết rồi mới hỏng ở write_reference, mã 3). write_track kiểm tệp mô tả trước khi chạm tệp chi tiết."""
    opened = []
    real_video = R.OverheadVideo
    monkeypatch.setattr(R, "OverheadVideo", lambda *a, **k: opened.append(a) or real_video(*a, **k))
    for extra in (("--capture-latency-s", "-0.1"), ("--capture-latency-s", "nan"), ("--sync-error", "nan"),
                  ("--sync-error", "-1"), ("--sync-error", "inf")):
        assert track(tmp_path, *extra, out="a.csv") == 2, extra
        assert "phải là số giây hữu hạn ≥ 0" in capsys.readouterr().err, extra
    assert track(tmp_path, "--sync", "nan=mark:1", out="a.csv") == 2
    assert "t_ref phải hữu hạn" in capsys.readouterr().err
    assert opened == [] and not list(tmp_path.iterdir())                    # không mở video, không ghi gì
    monkeypatch.setattr(R, "OverheadVideo", real_video)
    assert track(tmp_path, "--window", "0,0.6", out="b.csv") == 0
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    ref = read_reference(tmp_path / "b.csv")
    with open(tmp_path / "b.chi_tiet.csv", encoding="utf-8") as f:
        detail = list(csv.DictReader(f))
    for bad in (replace(ref.meta, sync_error_s=-0.5), replace(ref.meta, sync_error_s=float("nan"))):
        with pytest.raises(ValueError, match="sync_error_s"):
            R.write_track(tmp_path / "b.csv", ref.samples, bad, detail[:3], overwrite=True)
        # chi tiết cũ giữ nguyên, không tệp sao lưu, không tệp tạm
        assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
    with pytest.raises(R.OverheadError, match="hữu hạn ≥ 0"):
        R.build_reference(R.TrackResult([], None, {}, "perf_counter", {}), R.load_floor_fit(floor_fit_path()), car(),
                          capture_latency_s=-0.1)


def test_unmeasured_markers_or_failed_floor_fit_refused_unless_flag_then_accuracy_null(tmp_path, capsys):
    unmeasured = tmp_path / "xe_gia_v0.json"
    unmeasured.write_text(json.dumps(S.vehicle_markers_record(measured=False, synthetic=False)), encoding="utf-8")
    assert track(tmp_path, "--window", "0,0.3", markers=unmeasured) == 2
    assert "measured: false" in capsys.readouterr().err
    assert track(tmp_path, "--window", "0,0.3", "--cho-cau-hinh-chua-do", markers=unmeasured) == 2
    assert "không trộn dữ liệu TỔNG HỢP" in capsys.readouterr().err               # thật + tổng hợp: từ chối
    synthetic_v0 = tmp_path / "xe_gia_tong_hop_v0.json"
    synthetic_v0.write_text(json.dumps(S.vehicle_markers_record(measured=False)), encoding="utf-8")
    assert track(tmp_path, "--window", "0,0.3", markers=synthetic_v0, out="a.csv") == 0     # tổng hợp: nhận
    meta = read_reference(tmp_path / "a.csv").meta
    assert meta.accuracy.pos_max_m is None and "cấu hình marker chưa đo" in meta.notes
    record = json.loads(floor_fit_path().read_text(encoding="utf-8"))
    record.update(ok=False, reasons=["thử: chưa đạt"])
    failed = tmp_path / "mat_san_chua_dat.json"
    failed.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    assert track(tmp_path, "--window", "0,0.3", floor=failed, out="b.csv") == 2
    assert "chưa đạt" in capsys.readouterr().err and not (tmp_path / "b.csv").exists()
    assert track(tmp_path, "--window", "0,0.3", "--cho-mat-san-chua-dat", floor=failed, out="b.csv") == 0
    meta = read_reference(tmp_path / "b.csv").meta
    assert meta.accuracy.pos_max_m is None and "khớp mặt sàn chưa đạt" in meta.notes
    clash = S.vehicle_markers_record()
    clash["markers"][0]["id"] = 3                                         # mã 3 đang là một mốc sàn
    (tmp_path / "xe_trung_ma.json").write_text(json.dumps(clash), encoding="utf-8")
    assert track(tmp_path, "--window", "0,0.3", markers=tmp_path / "xe_trung_ma.json", out="c.csv") == 2
    assert "trùng mã mốc sàn" in capsys.readouterr().err
