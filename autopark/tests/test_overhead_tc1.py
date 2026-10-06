"""TC-1 của tham chiếu trên cao (`autopark.evaluation.overhead_tc1`, thêm 02/10/2026) trên bộ thử TỔNG HỢP: so R1 với
R2 (hai đầu thước có nhiễu ≤ 2 mm), yêu cầu số tư thế / hướng / góc sa bàn, luật chép độ chính xác sang một lần chạy.
Sửa 02/10/2026 (đợt 2): run_tc1 từ chối khớp mặt sàn chưa đạt, cấu hình marker thật chưa đo và đoạn ghi TỔNG HỢP đi với
đầu vào thật. Không mở camera hay cổng nào."""
import copy
import csv
import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from autopark.evaluation import overhead_ref as R  # noqa: E402
from autopark.evaluation import overhead_tc1 as T  # noqa: E402
from autopark.evaluation.reference_pose import ACCURACY_KEYS  # noqa: E402
from autopark.lidar import recording as lidar_recording  # noqa: E402
from autopark.perception.paths import PROJECT  # noqa: E402
from tests.overhead_set import TC1_MIN_FRAMES, floor_fit_path, small_set, tc1_report_path  # noqa: E402


@pytest.fixture(autouse=True)
def no_git(monkeypatch):
    monkeypatch.setattr(lidar_recording, "git_commit", lambda: "test")


def pose_rows() -> list[dict]:
    info = small_set()
    with open(info["tc1_poses"], encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    base = Path(info["tc1_poses"]).parent
    return [dict(r, video=str((base / r["video"]).resolve())) for r in rows]      # đường dẫn tuyệt đối: CSV ở tmp_path


def write_poses(path: Path, rows: list[dict]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=T.POSE_FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return path


def fit_and_car():
    return R.load_floor_fit(floor_fit_path()), R.load_vehicle_markers(small_set()["markers"])


def test_full_tc1_on_synthetic_poses():
    report = T.load_tc1(tc1_report_path())
    acc = report.accuracy
    assert set(acc) == set(ACCURACY_KEYS)                               # chép nguyên được vào tệp tham chiếu
    assert acc["pos_max_m"] <= 0.006 and acc["yaw_max_deg"] <= 0.6 and acc["pos_median_m"] <= acc["pos_max_m"]
    summary = report.record["summary"]
    assert report.requirements["met"] and summary["n_poses"] == 10 and summary["headings"] >= 3
    assert summary["corners_covered"] == [True] * 4 and summary["spread_pos_p95_m"] < 0.002
    assert acc["source"].startswith("TC-1 đầy đủ") and "10 tư thế, cận trên" in acc["source"]
    assert report.synthetic and report.record["notes"][0] == R.SYNTHETIC_LABEL and set(T.NOTES) <= set(
        report.record["notes"])
    usable = {u["check"]: u for u in report.record["usable_for"]}
    assert usable["N-D1"]["ok"] is True and usable["N-D1"]["needs"] == pytest.approx(0.05 / 3)
    assert usable["N-L2"]["value"]["yaw_deg"] == acc["yaw_max_deg"]
    assert usable["N-L2"]["needs"]["yaw_deg"] == pytest.approx(2 / 3)
    assert usable["N-L2"]["ok"] is (acc["yaw_max_deg"] <= 2 / 3)
    assert usable["N-D3"]["ok"] is None and usable["N-D3"]["value"] > acc["pos_max_m"]
    assert report.record["floor"]["sha256"] == R.file_sha256(floor_fit_path())
    assert any("Dùng được cho" in line for line in T.summary_lines(report))
    assert R.main(["check", str(tc1_report_path())]) == 0


def test_requirements_report_missing_corners_headings_and_too_few_frames(tmp_path):
    fit, car = fit_and_car()
    poses = write_poses(tmp_path / "tc1.csv", [r for r in pose_rows() if r["tu_the"] in ("tu_the_05", "tu_the_06")])
    out = tmp_path / "bien_ban.json"
    argv = ["tc1", "--floor", str(floor_fit_path()), "--markers", small_set()["markers"], "--poses", str(poses),
            "--out", str(out)]
    assert R.main(argv) == 1                                            # ≥ 30 khung mỗi tư thế: đoạn 8 khung bị loại
    record = json.loads(out.read_text(encoding="utf-8"))
    missing = " | ".join(record["requirements"]["missing"])
    assert not record["requirements"]["met"] and record["summary"]["n_poses"] == 0
    assert "chỉ 8 khung hợp lệ (cần ≥ 30)" in missing and "cần ≥ 10 tư thế" in missing
    assert record["accuracy"]["pos_max_m"] is None
    report = T.run_tc1(T.read_tc1_poses(poses), fit, car, min_valid_frames=TC1_MIN_FRAMES)
    missing = " | ".join(report.requirements["missing"])
    assert report.record["summary"]["n_poses"] == 2 and "cần ≥ 3 hướng" in missing
    assert missing.count("thiếu tư thế cách góc") == 4
    day = T.run_tc1(T.read_tc1_poses(poses), fit, car, kind="day", min_valid_frames=TC1_MIN_FRAMES)
    assert day.requirements["missing"] == ["cần ≥ 3 tư thế dùng được, có 2"]


def test_ruler_length_mismatch_and_centre_cross_check_are_noted(tmp_path):
    fit, car = fit_and_car()
    rows = pose_rows()[4:7]
    rows[0]["x_truoc_m"] = f"{float(rows[0]['x_truoc_m']) + 0.03:.4f}"     # đọc sai 3 cm ở đầu trước
    truth = small_set()["tc1_truth"][5]
    rows[1]["x_tam_m"], rows[1]["y_tam_m"] = f"{truth.x + 0.002:.4f}", f"{truth.y:.4f}"
    report = T.run_tc1(T.read_tc1_poses(write_poses(tmp_path / "tc1.csv", rows)), fit, car, kind="day",
                       min_valid_frames=TC1_MIN_FRAMES)
    first, second = report.record["poses"][:2]
    assert first["r2"]["ruler_err_m"] > 0.02 and any("kiểm lại số đo thước" in n for n in first["notes"])
    assert second["r2"]["centre_check_m"] == pytest.approx(0.002, abs=0.0035)
    assert not any("kiểm lại số đo thước" in n for n in second["notes"]) and report.requirements["met"]


def test_compare_refinements_writes_alternatives(tmp_path):
    fit, car = fit_and_car()
    poses = T.read_tc1_poses(write_poses(tmp_path / "tc1.csv", pose_rows()[4:7]))
    report = T.run_tc1(poses, fit, car, kind="day", compare=("subpix",), min_valid_frames=TC1_MIN_FRAMES)
    alt = report.record["alternatives"]["subpix"]
    assert alt["n_poses"] == 3 and 0 < alt["pos_max_m"] < 0.01 and alt["yaw_max_deg"] is not None
    assert report.detector["refine"] == "contour"                      # biên bản vẫn theo bộ dò của khớp mặt sàn


def _relabelled(tmp_path: Path, *, floor: dict | None = None, markers: dict | None = None):
    """Bản sao khớp mặt sàn / cấu hình marker của bộ thử với vài khóa đổi (vd. cờ synthetic false như tệp thật)."""
    out = []
    for name, src, change in (("mat_san.json", floor_fit_path(), floor), ("xe.json", small_set()["markers"], markers)):
        record = json.loads(Path(src).read_text(encoding="utf-8"))
        record.update(change or {})
        path = tmp_path / name
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        out.append(path)
    return R.load_floor_fit(out[0]), R.load_vehicle_markers(out[1])


def test_tc1_refuses_failed_floor_unmeasured_markers_and_synthetic_clips_with_real_inputs(tmp_path, capsys):
    """run_tc1 (nên cả dòng lệnh lẫn thẻ TC-1 của giao diện) từ chối: khớp mặt sàn chưa đạt, cấu hình marker thật chưa
    đo, và đoạn ghi TỔNG HỢP (cờ trong JSON của bộ ghi) đi với khớp mặt sàn / cấu hình marker thật."""
    poses = T.read_tc1_poses(write_poses(tmp_path / "tc1.csv", pose_rows()[4:7]))
    fit, car = _relabelled(tmp_path, floor={"synthetic": False}, markers={"synthetic": False, "measured": True})
    with pytest.raises(R.OverheadError, match="không trộn dữ liệu TỔNG HỢP") as err:
        T.run_tc1(poses, fit, car, kind="day", min_valid_frames=TC1_MIN_FRAMES)
    assert "tu_the_05" in str(err.value) and "cờ synthetic True" in str(err.value)
    fit, car = _relabelled(tmp_path, floor={"ok": False, "reasons": ["thử: chưa đạt"]})
    with pytest.raises(R.OverheadError, match="chưa đạt.*khớp lại trước TC-1"):
        T.run_tc1(poses, fit, car, kind="day", min_valid_frames=TC1_MIN_FRAMES)
    fit, car = _relabelled(tmp_path, floor={"synthetic": False}, markers={"synthetic": False, "measured": False})
    with pytest.raises(R.OverheadError, match="measured: false"):
        T.run_tc1(poses, fit, car, kind="day", min_valid_frames=TC1_MIN_FRAMES)
    fit, car = _relabelled(tmp_path, markers={"measured": False})        # bộ thử tổng hợp chưa đo: vẫn nhận
    assert T.run_tc1(poses, fit, car, kind="day", min_valid_frames=TC1_MIN_FRAMES).requirements["met"]
    # dòng lệnh: cùng lời từ chối, không ghi biên bản
    _relabelled(tmp_path, floor={"ok": False, "reasons": ["thử: chưa đạt"]})
    out = tmp_path / "bien_ban.json"
    assert R.main(["tc1", "--floor", str(tmp_path / "mat_san.json"), "--markers", str(tmp_path / "xe.json"),
                   "--poses", str(tmp_path / "tc1.csv"), "--kind", "day", "--min-frames", str(TC1_MIN_FRAMES),
                   "--out", str(out)]) == 2
    assert "khớp lại trước TC-1" in capsys.readouterr().err and not out.exists()


def test_synthetic_report_refused_under_docs_evidence(tmp_path, capsys):
    report = T.load_tc1(tc1_report_path())
    target = PROJECT / "docs" / "evidence" / "nghiem_thu" / "tham_chieu_tren_cao_tong_hop_thu.json"
    with pytest.raises(R.OverheadError, match="không được ghi vào"):
        T.save_tc1(target, report)
    assert R.main(["tc1", "--floor", str(floor_fit_path()), "--markers", small_set()["markers"], "--poses",
                   small_set()["tc1_poses"], "--out", str(target)]) == 2
    assert "không được ghi vào" in capsys.readouterr().err and not target.exists()


def _variant(report: T.Tc1Report, **changes) -> T.Tc1Report:
    record = copy.deepcopy(report.record)
    for path, value in changes.items():
        node = record
        keys = path.split("__")
        for key in keys[:-1]:
            node = node[key]
        node[keys[-1]] = value
    return T.Tc1Report(record, report.path, report.sha256)


def test_accuracy_copy_rules():
    fit, car = fit_and_car()
    full = T.load_tc1(tc1_report_path())
    day = full.date
    acc, notes = T.accuracy_for_track(fit, car, day, full, None)
    assert acc.pos_max_m == full.accuracy["pos_max_m"] and acc.yaw_max_deg == full.accuracy["yaw_max_deg"]
    assert acc.source == full.accuracy["source"] and not notes
    acc, notes = T.accuracy_for_track(fit, car, day, None, None)
    assert acc.pos_max_m is None and acc.source == "chưa làm TC-1" and "không kiểm được" in notes[0]
    other_fit = copy.copy(fit)
    other_fit.sha256 = "0" * 64
    cases = [((other_fit, car, day, full, None), "khớp mặt sàn khác"),
             ((fit, car, day, _variant(full, detector__refine="subpix"), None), "bộ dò khác"),
             ((fit, car, day, _variant(full, synthetic=False), None), "cờ tổng hợp"),
             ((fit, car, day, _variant(full, requirements__met=False, requirements__missing=["thiếu góc"]), None),
              "chưa đủ yêu cầu"),
             ((fit, car, "2026-09-30", full, None), "cùng ngày"),
             ((fit, car, day, _variant(full, kind="day"), None), "kind full")]
    for args, words in cases:
        acc, notes = T.accuracy_for_track(*args)
        assert acc.pos_max_m is None and acc.yaw_max_deg is None and words in acc.source, words
        assert any(words in n for n in notes)
    acc, notes = T.accuracy_for_track(fit, car, day, _variant(full, requirements__met=False), None, allow=True)
    assert acc.pos_max_m == full.accuracy["pos_max_m"] and "--tc1-chua-du" in notes[0]
    other_car = copy.copy(car)
    other_car.sha256 = "1" * 64                                         # cấu hình marker sửa sau TC-1 đầy đủ
    acc, _ = T.accuracy_for_track(fit, other_car, day, full, None)
    assert acc.pos_max_m is None and "cấu hình marker khác" in acc.source
    worse_pos = full.accuracy["pos_max_m"] + 0.001
    same_day = _variant(full, kind="day", markers__sha256=other_car.sha256, accuracy__pos_max_m=worse_pos,
                        accuracy__yaw_max_deg=full.accuracy["yaw_max_deg"] / 2)
    acc, notes = T.accuracy_for_track(fit, other_car, day, full, same_day)
    assert acc.pos_max_m == pytest.approx(worse_pos) and acc.yaw_max_deg == full.accuracy["yaw_max_deg"]  # max từng trường
    assert any("TC-1 rút gọn trong ngày cùng cấu hình" in n for n in notes) and " + " in acc.source
    z_moved = _variant(same_day, markers__z_m=[0.107, 0.107])
    acc, _ = T.accuracy_for_track(fit, other_car, day, full, z_moved)
    assert acc.pos_max_m is None and "độ cao marker" in acc.source
    older = _variant(full, date="2026-09-30")
    acc, _ = T.accuracy_for_track(fit, car, day, older, None)
    assert acc.pos_max_m is None
    acc, _ = T.accuracy_for_track(fit, car, day, older, _variant(full, kind="day"))   # TC-1 rút gọn đầu ngày
    assert acc.pos_max_m == full.accuracy["pos_max_m"]
