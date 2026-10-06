"""Dựng bản đồ tĩnh nhiều chỗ đặt trong hệ sa bàn (lidar/map_builder.py, T2, thêm 02/10/2026) trên bản ghi TỔNG HỢP
(tests/lidar_fakes.py) và trên bản ghi C1 đứng yên khi máy có (bỏ qua khi thiếu). Không thiết bị.

Mọi tư thế ở đây là tư thế TÂM QUAY LiDAR (m, m, rad) trong hệ sa bàn. Cận rộng hơn số đo lúc viết test (02/10/2026)
khoảng 2–5 lần; số đo ghi cạnh từng cận."""
import json
import math
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from autopark.lidar.localize import load_map, localize  # noqa: E402
from autopark.lidar.map_builder import (SA_BAN_FRAME, SENSOR_FRAME, MapBuildConfig, PlacementSpec,  # noqa: E402
                                        build_static_map, main, parse_placement, read_map_build, write_map)
from autopark.lidar.synthetic import drive  # noqa: E402
from autopark.perception.costmap import UNKNOWN  # noqa: E402
from tests.lidar_fakes import (OTHER_ROOM, default_config, scan_at, scene, static_slice,  # noqa: E402
                               write_recording)

PROJECT = Path(__file__).resolve().parents[1]
RUNS = PROJECT / "runs"
NO_SKIP = MapBuildConfig(skip_seconds=0.0)
A = (0.6, 1.0, math.radians(20.0))
B = (1.83, 1.42, math.radians(-35.0))
C = (2.37, 0.97, math.radians(160.0))


def gap(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1]), abs(math.degrees(math.atan2(math.sin(a[2] - b[2]),
                                                                              math.cos(a[2] - b[2]))))


@pytest.fixture(scope="module")
def recordings(tmp_path_factory):
    """Ba bản ghi đứng yên (2 s mỗi bản) ở A, B, C; thư mục tên tiếng Việt."""
    folder = tmp_path_factory.mktemp("ban_ghi") / "bản ghi tổng hợp"
    rng = np.random.default_rng(21)
    return {name: write_recording(folder / f"chỗ {name}", static_slice(pose, 2.0, rng))
            for name, pose in (("A", A), ("B", B), ("C", C))}


def test_single_placement_map_is_in_the_sa_ban_frame(recordings, tmp_path):
    """Đo 02/10/2026: định vị lại vòng quét mới tại mốc neo lệch 4,0 mm / 0,03°."""
    result = build_static_map([PlacementSpec(recordings["A"])], anchor=A, config=NO_SKIP)
    assert result.ok and result.frame == SA_BAN_FRAME and result.session_ready
    assert result.placements[0].pose_source == "anchor" and result.placements[0].pose == pytest.approx(A)
    out = tmp_path / "bản đồ A"
    write_map(result, out)
    for name in ("costmap.json", "map.png", "counts.npz", "placements.csv", "map_build.json"):
        assert (out / name).is_file(), name
    block = read_map_build(out)
    assert block["frame"] == "sa_ban" and block["session_ready"] is True and block["mirror"] is False
    assert block["anchor"]["yaw_deg"] == pytest.approx(20.0) and len(block["inputs_sha256"]) == 1
    lmap = load_map(out, default_config().localize)
    found = localize(lmap, *scan_at(A, np.random.default_rng(22)), A, window=(0.3, 0.3, math.radians(20)))
    assert found.ok
    dm, ddeg = gap((found.x, found.y, found.theta), A)
    assert dm < 0.01 and ddeg < 0.3


def test_three_synthetic_placements_register_without_tape_poses(recordings, tmp_path):
    """Chỗ đặt 2 ghép bằng tìm toàn cục (không gợi ý), chỗ đặt 3 bằng gợi ý lệch 0,3 m / 20°. Đo 02/10/2026: lệch so với
    tư thế thật 2,5 mm / 0,10° và 3,2 mm / 0,08°; bỏ-ra-một lệch ≤ 7,0 mm / 0,08°; ô UNKNOWN trong sa bàn 163 so với 355
    khi chỉ có chỗ đặt 1."""
    hint = (C[0] - 0.3, C[1] + 0.1, C[2] - math.radians(20))
    specs = [PlacementSpec(recordings["A"]), PlacementSpec(recordings["B"]),
             PlacementSpec(recordings["C"], hint_pose=hint)]
    result = build_static_map(specs, anchor=A, config=NO_SKIP)
    assert result.ok, result.reasons_vi
    p = result.placements
    assert [x.guess for x in p] == ["", "global", "hint"] and [x.pose_source for x in p] == ["anchor"] + ["registered"] * 2
    for res, truth in zip(p[1:], (B, C)):
        dm, ddeg = gap(res.pose, truth)
        assert dm < 0.01 and ddeg < 0.3, (res.index, dm, ddeg)
        assert res.registration.ok == res.registration.tried
    assert all(x.loo["checked"] and x.loo["ok"] for x in p), [x.loo for x in p]
    single = build_static_map(specs[:1], anchor=A, config=NO_SKIP)

    def unknown_on_board(r):
        gx, gy = r.grid.centers()
        board = (gx >= 0) & (gx <= 3.0) & (gy >= 0) & (gy <= 2.0)
        return int(((r.states == UNKNOWN) & board).sum())

    assert unknown_on_board(result) < 0.8 * unknown_on_board(single)


def test_tape_pose_disagreeing_with_registration_is_refused_unless_trusted(recordings, tmp_path):
    out = tmp_path / "thước lệch"
    tape = (B[0] + 0.10, B[1], B[2])
    args = ["--placement", str(recordings["A"]), "--anchor", str(A[0]), str(A[1]), "20",
            "--placement", str(recordings["B"]), "--pose", "2", str(tape[0]), str(tape[1]), str(math.degrees(tape[2])),
            "--skip-seconds", "0"]
    assert main(args + ["--out", str(out)]) == 1
    assert sorted(f.name for f in out.iterdir()) == ["map_build.json"]
    report = json.loads((out / "map_build.json").read_text(encoding="utf-8"))
    assert report["ok"] is False and "thước" in report["reasons"][0] and "--trust-tape" in report["reasons"][0]
    assert report["placements"][1]["tape_gap_m"] == pytest.approx(0.10, abs=0.01)
    trusted = tmp_path / "tin thước"
    assert main(args + ["--out", str(trusted), "--trust-tape"]) == 0
    block = read_map_build(trusted)
    assert block["placements"][1]["pose_source"] == "tape" and block["placements"][1]["tape_gap_m"] > 0.08
    assert block["placements"][1]["pose"]["x_m"] == pytest.approx(tape[0]) and block["trust_tape"] is True
    assert any("--trust-tape" in w for w in block["warnings"])


def test_unregistrable_placement_is_refused(recordings, tmp_path):
    other = write_recording(tmp_path / "phòng khác", static_slice((0.4, 0.2, 0.3), 2.0, np.random.default_rng(23),
                                                               segments=scene(OTHER_ROOM, [])))
    out = tmp_path / "không ghép được"
    args = ["--placement", str(recordings["A"]), "--anchor", str(A[0]), str(A[1]), "20", "--placement", str(other),
            "--hint", "2", "0.5", "1.0", "0", "--skip-seconds", "0", "--out", str(out)]
    assert main(args) == 1
    assert not (out / "costmap.json").exists() and (out / "map_build.json").is_file()
    report = json.loads((out / "map_build.json").read_text(encoding="utf-8"))
    assert report["ok"] is False and report["reasons"][0].startswith("Không ghép được chỗ đặt 2")


def test_odometry_hint_between_slices_of_one_recording(tmp_path):
    """Một bản ghi: đứng 3 s ở A, bê 1 m và quay 45° ở 0,2 m/s, đứng 3 s ở chỗ mới. Chỗ đặt 2 ghép từ odometry khớp scan
    qua đoạn bê, không tìm toàn cục. Đo 02/10/2026: điểm đoán từ odometry lệch 2,6 mm / 0,36°, sau khi ghép 2,2 mm /
    0,12°."""
    rng = np.random.default_rng(24)
    path = drive(A, [(0.0, 0.0, 30), (0.2, math.radians(9.0), 50), (0.0, 0.0, 30)])
    scans = [(*scan_at(tuple(p), rng), 0.1 * k) for k, p in enumerate(path)]
    rec = write_recording(tmp_path / "bê LiDAR", scans)
    specs = [parse_placement(f"{rec}@0:2.95"), parse_placement(f"{rec}@8.05:")]
    assert specs[0].t1_s == pytest.approx(2.95) and specs[1].t0_s == pytest.approx(8.05) and specs[1].t1_s is None
    result = build_static_map(specs, anchor=A, config=NO_SKIP)
    assert result.ok, result.reasons_vi
    second = result.placements[1]
    assert second.guess == "odometry_hint" and second.pose_source == "registered"
    dm, ddeg = gap(second.pose, tuple(path[-1]))
    assert dm < 0.01 and ddeg < 0.3
    assert gap(second.guess_pose, tuple(path[-1]))[0] < 0.1               # odometry đã đưa gần tới chỗ mới


def test_usage_errors_exit_2_before_writing(recordings, tmp_path, capsys):
    base = tmp_path / "dùng sai"
    mirrored = write_recording(tmp_path / "đảo chiều", static_slice(A, 1.0, np.random.default_rng(25)),
                               meta={"mirror": True})
    cases = [
        ["--placement", str(recordings["A"]), "--anchor", "0.6", "1.0", "20", "--placement", str(mirrored)],
        ["--placement", str(recordings["A"]), "--anchor", "0.6", "1.0", "20", "--placement", str(recordings["B"]),
         "--pose", "1", "0.6", "1.0", "20"],
        ["--placement", str(recordings["A"]), "--anchor-vehicle", "0.5", "1.0", "20"],
        ["--placement", str(tmp_path / "không có.npz"), "--anchor", "0", "0", "0"],
        ["--placement", str(recordings["A"]), "--anchor", "0.6", "1.0", "20", "--self-mask", "--lidar-config",
         str(PROJECT / "configs" / "dinh_vi_lidar_v0.json")],
    ]
    for k, args in enumerate(cases):
        with pytest.raises(SystemExit) as info:
            main(args + ["--skip-seconds", "0", "--out", str(base / str(k))])
        assert info.value.code == 2, args
        assert not (base / str(k)).exists()
    err = capsys.readouterr().err
    assert "mirror" in err and "mốc neo" in err and "--lidar-config" in err
    taken = tmp_path / "đã có"
    taken.mkdir()
    (taken / "ghi chú.txt").write_text("giữ", encoding="utf-8")
    with pytest.raises(SystemExit) as info:
        main(["--placement", str(recordings["A"]), "--anchor", "0.6", "1.0", "20", "--skip-seconds", "0",
              "--out", str(taken)])
    assert info.value.code == 2 and sorted(f.name for f in taken.iterdir()) == ["ghi chú.txt"]
    assert main(["--placement", str(recordings["A"]), "--anchor-vehicle", "0.505", "1.0", "20", "--lidar-config",
                 str(PROJECT / "configs" / "dinh_vi_lidar_v0.json"), "--self-mask", "--vehicle-config",
                 str(PROJECT / "configs" / "vehicle_default.json"), "--skip-seconds", "0", "--out",
                 str(taken), "--overwrite"]) == 0
    block = read_map_build(taken)
    mount = default_config().mount
    assert block["anchor"]["x_m"] == pytest.approx(0.505 + mount.x_m * math.cos(math.radians(20)))
    assert block["mount"]["x_m"] == mount.x_m and (taken / "ghi chú.txt").exists()     # --overwrite chỉ thay tệp kết quả


def test_map_without_anchor_is_not_session_ready_and_is_refused_by_the_pose_source(recordings, tmp_path):
    result = build_static_map([PlacementSpec(recordings["A"])], config=NO_SKIP)
    assert result.ok and result.frame == SENSOR_FRAME and not result.session_ready and result.anchor is None
    out = tmp_path / "chưa neo"
    write_map(result, out)
    assert read_map_build(out)["session_ready"] is False
    pytest.importorskip("PySide6")
    from autopark.ui.lidar_app import lidar_map_info

    with pytest.raises(ValueError, match="không phải hệ sa bàn"):
        lidar_map_info(out)


# ---- dữ liệu thật (bỏ qua nếu máy không có) ------------------------------------------------------------------------
def test_real_c1_live_headless_registers_to_p07_with_its_known_rotation(tmp_path):
    """p07 (mốc neo 0, 0, 0) + live_headless (lần bật khác) với gợi ý (0, 0, 0): ghép ra đúng phép quay đã biết của
    DINH_VI_LIDAR mục 5 (−1,1 mm; −6,8 mm; +4,33°). Đo 02/10/2026: (−1,3 mm; −4,7 mm; +4,31°), bỏ-ra-một đạt."""
    p07 = RUNS / "lidar_bench" / "20260922" / "p07_nen_phong.npz"
    live = RUNS / "lidar_bench" / "20260922" / "live_headless.npz"
    if not (p07.exists() and live.exists()):
        pytest.skip("không có bản ghi C1 runs/lidar_bench/20260922")
    specs = [PlacementSpec(p07, None, 10.0), PlacementSpec(live, hint_pose=(0.0, 0.0, 0.0))]
    result = build_static_map(specs, anchor=(0.0, 0.0, 0.0))
    assert result.ok, result.reasons_vi
    pose = result.placements[1].pose
    assert math.hypot(pose[0] + 0.0011, pose[1] + 0.0068) < 0.01
    assert math.degrees(pose[2]) == pytest.approx(4.33, abs=0.3)


def test_real_c1_k01_does_not_register_to_p07(tmp_path):
    """k01: C1 đã dời đi chỗ khác. Chỉ gợi ý (0, 0, 0), không tìm toàn cục (giữ CPU thấp): từ chối, mã thoát 1."""
    p07 = RUNS / "lidar_bench" / "20260922" / "p07_nen_phong.npz"
    k01 = RUNS / "lidar_bench" / "20260924_kiem" / "k01_kiem_suc_khoe.npz"
    if not (p07.exists() and k01.exists()):
        pytest.skip("không có bản ghi C1 p07 / k01")
    out = tmp_path / "k01"
    assert main(["--placement", f"{p07}@:10", "--anchor", "0", "0", "0", "--placement", str(k01),
                 "--hint", "2", "0", "0", "0", "--out", str(out)]) == 1
    assert not (out / "costmap.json").exists()
