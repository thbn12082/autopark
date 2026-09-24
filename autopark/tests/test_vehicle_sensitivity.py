"""Độ nhạy planner theo kích thước xe với sa bàn cố định (`evaluation/sensitivity.py`) và tùy chọn `--vehicle-config`
của `robustness`, `phase0`, `ui/lidar_app`. Chỉ mô phỏng; không mở cổng COM hay camera nào."""
import copy
import json
import math
import os
import random
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from autopark.domain.types import Bounds, Obstacle, ParkingGoal, Pose, Scenario  # noqa: E402
from autopark.evaluation import phase0, robustness  # noqa: E402
from autopark.evaluation import sensitivity as sens  # noqa: E402
from autopark.evaluation.hard_cases import build_cases  # noqa: E402
from autopark.planning import cand_rrt_rs  # noqa: E402
from autopark.planning.hybrid_astar import PlanResult  # noqa: E402
from autopark.planning.trajectory import build_trajectory  # noqa: E402
from autopark.storage.scenario_store import load_vehicle_config  # noqa: E402
from tests.conftest import PROJECT_ROOT  # noqa: E402

DEFAULT_CFG_PATH = PROJECT_ROOT / "configs" / "vehicle_default.json"


@pytest.fixture(scope="module")
def ref_cfg():
    return load_vehicle_config(DEFAULT_CFG_PATH)


@pytest.fixture(scope="module")
def scenes(ref_cfg):
    return sens.build_scenes(ref_cfg, sens.DEFAULT_SCENARIO_DIR)


def big_variant(ref_cfg, scale=1.3):
    factors = {attr: scale for attr in sens.FOOTPRINT_ATTRS}
    name = f"to_hon_{scale:g}"
    return sens.Variant(name, "thu", (scale - 1) * 100, tuple(factors.items()), sens.scaled_config(ref_cfg, factors, name))


def baseline(ref_cfg):
    return sens.Variant(sens.BASELINE, sens.BASELINE, 0.0, (), ref_cfg)


def write_cfg(path, **changes):
    data = json.loads(DEFAULT_CFG_PATH.read_text(encoding="utf-8"))
    data.update({"name": "xe_thu_tam", "wheelbase_m": 0.30, "width_m": 0.10, "front_overhang_m": 0.05,
                 "rear_overhang_m": 0.07, "max_steer_deg": 28.0})
    data.update(changes)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


# Bộ lập đường giả ở cấp mô-đun: tiến trình con (spawn) và `--planner module:ham` nạp được chúng.
MODULE = "tests.test_vehicle_sensitivity"
PROBE = f"{MODULE}:budget_probe"


def open_scene(obstacles=()):
    """Sa bàn 3 × 2 m trống (hoặc có vật cản cho trước), xuất phát (0,5; 1,0), đích (2,0; 1,0), cùng hướng +x."""
    sc = Scenario("thu_trong", Bounds(0.0, 0.0, 3.0, 2.0), Pose(0.5, 1.0, 0.0), ParkingGoal(Pose(2.0, 1.0, 0.0)),
                  obstacles=list(obstacles))
    return sens.Scene("thu_trong", "test", "easy", "unknown", sc)


def straight(x0, x1, steer=0.0, step=0.01):
    n = round((x1 - x0) / step)
    return [(Pose(x0 + step * i, 1.0, 0.0), 1, steer) for i in range(n + 1)]


def budget_probe(start, goal, cfg, obstacles, bounds, time_limit):
    """Ghi vào message ngân sách và hạt giống RRT mà bộ lập đường THẬT SỰ nhận. Biến thể (không phải xe gốc) báo
    TIMEOUT khi ngân sách < 10 s, nên chỉ lượt chạy lại (ngân sách dài hơn) mới giải được."""
    seen = json.dumps({"time_limit": time_limit, "seed": os.environ.get(sens.RRT_SEED_ENV)})
    if "BIẾN THỂ MÔ PHỎNG" in (cfg.notes or "") and time_limit < 10.0:
        return PlanResult("TIMEOUT", seen)
    raw = [(Pose(start.x + (goal.x - start.x) * i / 150, start.y, start.yaw), 1, 0.0) for i in range(151)]
    return PlanResult("OK", seen, build_trajectory(raw, goal, cfg, 0.15, 0.08), 0.01)


def steer_over_limit(start, goal, cfg, obstacles, bounds, time_limit=None):
    """Đi thẳng 20 cm theo hướng xuất phát nhưng ghi góc lái 1,5 × max_steer: kiểm độc lập phải bắt."""
    raw = [(Pose(start.x + 0.01 * i * math.cos(start.yaw), start.y + 0.01 * i * math.sin(start.yaw), start.yaw), 1,
            1.5 * cfg.max_steer) for i in range(21)]
    return PlanResult("OK", "góc lái quá giới hạn", build_trajectory(raw, raw[-1][0], cfg, 0.15, 0.08), 0.01)


# ---------------------------------------------------------------- sa bàn cố định


class Spy:
    """Bộ lập đường giả: ghi lại đúng những gì planner nhận được, không lập đường."""

    def __init__(self):
        self.calls = []

    def __call__(self, start, goal, cfg, obstacles, bounds, time_limit=None):
        self.calls.append({"start": start, "goal": goal, "cfg": cfg, "obstacles": list(obstacles), "bounds": bounds})
        return PlanResult("NO_PATH", "spy")


def test_sa_ban_giu_nguyen_khi_doi_cau_hinh_lap_duong(ref_cfg, scenes):
    """Vật cản, vùng và xuất phát mà planner nhận phải là của xe tham chiếu, không phóng theo xe đang thử."""
    big = big_variant(ref_cfg)
    scaled_cases = build_cases(big.cfg)
    ref_cases = build_cases(ref_cfg)
    differs_when_scaled = 0
    for name, scene in scenes.items():
        before = sens.scene_digest(scene.scenario)
        spy_ref, spy_big = Spy(), Spy()
        row_ref = sens.evaluate(scene, baseline(ref_cfg), 1.0, planner=spy_ref)
        row_big = sens.evaluate(scene, big, 1.0, planner=spy_big)
        got_ref, got_big = spy_ref.calls[0], spy_big.calls[0]
        assert got_big["cfg"] is big.cfg
        assert got_big["obstacles"] == got_ref["obstacles"] == scene.scenario.obstacles, name
        assert got_big["bounds"] == got_ref["bounds"] == scene.scenario.bounds, name
        assert got_big["start"] == got_ref["start"] == scene.scenario.start, name
        assert row_ref["scene_digest"] == row_big["scene_digest"] == before, name
        assert sens.scene_digest(scene.scenario) == before, f"{name}: evaluate đã sửa sa bàn gốc"
        if name in ref_cases:
            assert got_ref["obstacles"] == ref_cases[name].scenario.obstacles
            scaled = scaled_cases[name].scenario
            if (scaled.obstacles, scaled.bounds, scaled.slot) != (got_big["obstacles"], got_big["bounds"],
                                                                  scene.scenario.slot):
                differs_when_scaled += 1
        # Có ô đỗ: đích tính lại cho xe đang thử trong CÙNG ô; không có ô: đích tâm trục sau giữ nguyên.
        sc = scene.scenario
        if sc.slot is not None:
            assert got_big["goal"] == sc.slot.goal_pose(big.cfg, sc.mode, reference_yaw=sc.start.yaw), name
        else:
            assert got_big["goal"] == got_ref["goal"] == sc.goal.pose, name
    # Phép thử chỉ có ý nghĩa nếu dựng lại theo xe to hơn thì sa bàn khác đi ở một số ca.
    assert differs_when_scaled >= 5


@pytest.mark.planner_budget
def test_run_sweep_moi_bien_the_cung_mot_sa_ban(ref_cfg, scenes):
    chosen = {n: scenes[n] for n in ("parallel_160", "perp_aisle_135")}
    big = big_variant(ref_cfg)
    rows = sens.run_sweep(chosen, [baseline(ref_cfg), big], 8.0)
    assert [(r["scene"], r["variant"]) for r in rows] == [
        ("parallel_160", "goc"), ("parallel_160", big.name), ("perp_aisle_135", "goc"), ("perp_aisle_135", big.name)]
    for name in chosen:
        digests = {r["scene_digest"] for r in rows if r["scene"] == name}
        assert digests == {sens.scene_digest(build_cases(ref_cfg)[name].scenario)}
        assert sens.scene_digest(build_cases(big.cfg)[name].scenario) not in digests


@pytest.mark.planner_budget
def test_xe_to_hon_nhieu_hong_ca_chat_ma_xe_mac_dinh_qua(ref_cfg, scenes):
    """perp_aisle_135 (tight): xe tham chiếu đỗ được; xe to hơn 30 % không vừa ô CỐ ĐỊNH, dù sa bàn phóng theo xe
    (cách của bench/compare) thì vẫn đỗ được. Đây đúng là điều bench không thấy."""
    scene = scenes["perp_aisle_135"]
    big = big_variant(ref_cfg, 1.3)
    ok = sens.evaluate(scene, baseline(ref_cfg), 8.0)
    assert ok["solved"], ok["message"]
    assert ok["path_ok"] and ok["oracle_ok"] and ok["steer_ok"] and ok["tracked"]
    assert ok["min_clearance_m"] is not None and ok["min_clearance_m"] > 0
    assert ok["cusps"] is not None and ok["plan_s"] < 8.0 + 0.5

    fail = sens.evaluate(scene, big, 8.0)
    assert not fail["solved"]
    assert fail["status"] == "GOAL_INVALID" and fail["slot_fits"] is False

    scaled = sens.Scene(scene.name, "", "", "", build_cases(big.cfg)["perp_aisle_135"].scenario)
    assert sens.evaluate(scaled, big, 8.0)["solved"]

    summary = sens.summarize([ok, fail], [baseline(ref_cfg), big])
    per = {p["variant"]: p for p in summary["per_variant"]}
    assert per[big.name]["flips_ok_to_fail"] == ["perp_aisle_135"]
    assert per["goc"]["flips_ok_to_fail"] == []


def test_duong_bao_ok_ma_cham_vat_thi_bi_bat(ref_cfg):
    """Planner báo OK với một đường đâm qua hộp: kiểm độc lập phải bắt, không được tính là giải được."""
    sc = Scenario("thu_cham", Bounds(0.0, 0.0, 3.0, 2.0), Pose(0.5, 1.0, 0.0), ParkingGoal(Pose(2.0, 1.0, 0.0)),
                  obstacles=[Obstacle("hop", 1.3, 1.0, 0.2, 0.2)])
    scene = sens.Scene("thu_cham", "test", "easy", "unknown", sc)
    raw = [(Pose(0.5 + 0.01 * i, 1.0, 0.0), 1, 0.0) for i in range(151)]

    def reckless(start, goal, cfg, obstacles, bounds, time_limit=None):
        return PlanResult("OK", "đường thẳng qua hộp", build_trajectory(raw, goal, cfg, 0.15, 0.08), 0.01)

    row = sens.evaluate(scene, baseline(ref_cfg), 1.0, planner=reckless)
    assert row["status"] == "OK" and not row["solved"] and row["verdict"] == "VI_PHAM"
    assert row["path_ok"] is False and row["oracle_ok"] is False
    assert "planner_ok_but_swept_check_collides" in row["violations"]
    assert row["min_clearance_m"] == 0.0


def _fixed_plan(trajectory_fn):
    def plan(start, goal, cfg, obstacles, bounds, time_limit=None):
        return PlanResult("OK", "đường cho sẵn", trajectory_fn(goal, cfg), 0.01)
    return plan


def test_goc_lai_vuot_gioi_han_la_vi_pham(ref_cfg):
    """Đường thẳng, không chạm gì, nhưng góc lái ghi trong quỹ đạo vượt max_steer của xe đang thử."""
    plan = _fixed_plan(lambda goal, cfg: build_trajectory(straight(0.5, 2.0, 1.2 * cfg.max_steer), goal, cfg,
                                                          0.15, 0.08))
    row = sens.evaluate(open_scene(), baseline(ref_cfg), 1.0, planner=plan)
    assert row["path_ok"] is True and row["oracle_ok"] is True and row["steer_ok"] is False
    assert row["violations"] == ["planner_ok_but_steer_above_vehicle_limit"]
    assert row["verdict"] == "VI_PHAM" and not row["solved"]


def test_dung_truoc_dich_10_cm_la_bam_hong(ref_cfg):
    """Đường sạch nhưng kết thúc 10 cm trước đích (dung sai 5 cm): không được tính là giải được."""
    plan = _fixed_plan(lambda goal, cfg: build_trajectory(straight(0.5, 1.9), goal, cfg, 0.15, 0.08))
    row = sens.evaluate(open_scene(), baseline(ref_cfg), 1.0, planner=plan)
    assert row["path_ok"] is True and row["oracle_ok"] is True and row["steer_ok"] is True
    assert row["violations"] == []
    assert row["pos_err_m"] == pytest.approx(0.10, abs=0.02)
    assert row["tracked"] is False and row["verdict"] == "BAM_HONG" and not row["solved"]


def test_dich_do_planner_tu_khai_khong_duoc_tinh(ref_cfg):
    """Planner dừng 10 cm trước đích rồi ghi đích của quỹ đạo là chỗ dừng: sai số vẫn tính tới đích của sa bàn."""
    plan = _fixed_plan(lambda goal, cfg: build_trajectory(straight(0.5, 1.9), Pose(1.9, 1.0, 0.0), cfg, 0.15, 0.08))
    row = sens.evaluate(open_scene(), baseline(ref_cfg), 1.0, planner=plan)
    assert row["goal"] == Pose(2.0, 1.0, 0.0).to_dict()
    assert row["pos_err_m"] == pytest.approx(0.10, abs=0.02)
    assert row["tracked"] is False and row["verdict"] == "BAM_HONG" and not row["solved"]


def test_duong_thua_diem_giua_cham_vach_mong_bi_bat(ref_cfg):
    """Hai điểm đường đều trống, đoạn thẳng giữa chúng xuyên vách mỏng: mẫu giữa hai điểm của oracle phải bắt."""
    wall = Obstacle("vach", 1.0, 1.0, 0.02, 0.30)
    scene = open_scene([wall])
    a, b = Pose(0.3, 1.0, 0.0), Pose(1.5, 1.0, 0.0)
    from autopark.evaluation import collision_oracle as oracle
    assert oracle.pose_ok(ref_cfg, a, [wall], scene.scenario.bounds)
    assert oracle.pose_ok(ref_cfg, b, [wall], scene.scenario.bounds)
    plan = _fixed_plan(lambda goal, cfg: build_trajectory([(a, 1, 0.0), (b, 1, 0.0)], b, cfg, 0.15, 0.08))
    row = sens.evaluate(scene, baseline(ref_cfg), 1.0, planner=plan)
    assert row["oracle_ok"] is False
    assert "planner_ok_but_sampled_oracle_collides" in row["violations"]
    assert row["verdict"] == "VI_PHAM" and not row["solved"]


def test_cli_vi_pham_thoat_ma_1_va_ghi_vao_bang(tmp_path, capsys):
    out = tmp_path / "ra"
    code = sens.main(["--scenes", "lateral_shift", "--no-scenarios", "--params", "none", "--combos", "none",
                      "--planner", f"{MODULE}:steer_over_limit", "--out", str(out)])
    assert code == 1
    data = json.loads((out / "ket_qua.json").read_text(encoding="utf-8"))
    assert "lateral_shift/goc:planner_ok_but_steer_above_vehicle_limit" in data["summary"]["violations"]
    table = (out / "bang_do_nhay.md").read_text(encoding="utf-8")
    assert "## Vi phạm an toàn" in table and "planner_ok_but_steer_above_vehicle_limit" in table
    assert "VI PHẠM" in capsys.readouterr().out


# ---------------------------------------------------------------- biến thể và tóm tắt


def test_bien_the_nhan_dung_thuoc_tinh(ref_cfg):
    variants = sens.build_variants(ref_cfg)
    by = {v.name: v.cfg for v in variants}
    assert len(variants) == 1 + 5 * 6 + 6 + 3 + 3
    assert len(by) == len(variants)
    assert by["goc"] is ref_cfg
    assert by["width+10"].width == pytest.approx(ref_cfg.width * 1.10)
    assert by["width+10"].wheelbase == ref_cfg.wheelbase and by["width+10"].max_steer == ref_cfg.max_steer
    assert by["length-20"].length == pytest.approx(ref_cfg.length * 0.80)
    assert by["length-20"].wheelbase == pytest.approx(ref_cfg.wheelbase * 0.80)
    assert by["overhangs+20"].wheelbase == ref_cfg.wheelbase
    assert by["overhangs+20"].front_overhang == pytest.approx(ref_cfg.front_overhang * 1.2)
    assert by["overhangs+20"].rear_overhang == pytest.approx(ref_cfg.rear_overhang * 1.2)
    assert math.degrees(by["max_steer-20"].max_steer) == pytest.approx(24.0)
    assert math.degrees(by["max_steer+20"].max_steer) == pytest.approx(36.0)
    worse = by["lon_lai_kem+10"]
    assert worse.width == pytest.approx(ref_cfg.width * 1.1) and worse.length == pytest.approx(ref_cfg.length * 1.1)
    assert worse.max_steer == pytest.approx(ref_cfg.max_steer * 0.9)
    better = by["nho_lai_gat+20"]
    assert better.width == pytest.approx(ref_cfg.width * 0.8) and better.max_steer == pytest.approx(ref_cfg.max_steer * 1.2)
    assert by["kich_thuoc-5"].max_steer == ref_cfg.max_steer
    assert "BIẾN THỂ MÔ PHỎNG" in by["width+10"].notes
    with pytest.raises(ValueError, match="max_steer"):
        sens.build_variants(ref_cfg, ("max_steer",), (200.0,), ())
    with pytest.raises(ValueError, match="không có tham số"):
        sens.build_variants(ref_cfg, ("mui_xe",), (5.0,), ())


def test_muc_lat_dau_tien_va_khong_don_dieu(ref_cfg):
    variants = sens.build_variants(ref_cfg, ("width",), (5.0, 10.0, 20.0), ())
    solved = {"goc": True, "width-5": True, "width-10": True, "width-20": False,
              "width+5": True, "width+10": False, "width+20": True}
    rows = [{"scene": "s", "variant": v.name, "group": v.group, "level_pct": v.level_pct, "solved": solved[v.name],
             "status": "OK" if solved[v.name] else "TIMEOUT", "plan_s": 1.0, "min_clearance_m": 0.02, "cusps": 1,
             "violations": []} for v in variants]
    summary = sens.summarize(rows, variants)
    entry = summary["thresholds"]["s"]["width"]
    assert entry["tang"] == 10 and entry["tang_khong_don_dieu"] is True
    assert entry["giam"] == -20 and entry["giam_khong_don_dieu"] is False
    per = {p["variant"]: p for p in summary["per_variant"]}
    assert per["width+10"]["flips_ok_to_fail"] == ["s"] and per["width+20"]["flips_ok_to_fail"] == []
    assert sens._threshold_text(entry) == "+10 %*, -20 %"


def test_hat_giong_rrt_dat_trong_luot_chay_roi_tra_lai(monkeypatch):
    monkeypatch.delenv(sens.RRT_SEED_ENV, raising=False)
    with sens.rrt_seed_env(1234):
        assert cand_rrt_rs._resolve_params(None).seed == 1234
    assert sens.RRT_SEED_ENV not in os.environ
    monkeypatch.setenv(sens.RRT_SEED_ENV, "77")
    with sens.rrt_seed_env(5):
        assert os.environ[sens.RRT_SEED_ENV] == "5"
    assert os.environ[sens.RRT_SEED_ENV] == "77"


@pytest.mark.planner_budget
def test_nhieu_tien_trinh_cho_cung_thu_tu_va_ket_qua(ref_cfg, scenes):
    chosen = {n: scenes[n] for n in ("reverse_long_corridor", "lateral_shift")}
    variants = sens.build_variants(ref_cfg, ("width",), (10.0,), ())
    one = sens.run_sweep(chosen, variants, 8.0, workers=1)
    two = sens.run_sweep(chosen, variants, 8.0, workers=2)
    key = [(r["scene"], r["variant"], r["verdict"], r["cusps"], r["length_m"]) for r in one]
    assert key == [(r["scene"], r["variant"], r["verdict"], r["cusps"], r["length_m"]) for r in two]
    assert all(r["solved"] for r in one)


def test_run_sweep_ngan_sach_chay_lai_va_hat_giong_toi_bo_lap_duong(ref_cfg, monkeypatch):
    monkeypatch.delenv(sens.RRT_SEED_ENV, raising=False)
    variants = sens.build_variants(ref_cfg, ("width",), (10.0,), ())
    scene = {"thu_trong": open_scene()}
    rows = sens.run_sweep(scene, variants, 4.0, recheck_time_limit=12.0, rrt_seed=4242, planner_spec=PROBE)
    assert [r["variant"] for r in rows] == ["goc", "width-10", "width+10"]
    assert [json.loads(r["message"]) for r in rows] == [{"time_limit": 4.0, "seed": "4242"}] * 3
    assert rows[0]["solved"] and "recheck" not in rows[0]
    for r in rows[1:]:
        assert r["status"] == "TIMEOUT" and not r["solved"]
        assert r["recheck"]["time_limit_s"] == 12.0 and r["recheck"]["solved"], r
        assert json.loads(r["recheck"]["message"]) == {"time_limit": 12.0, "seed": "4242"}
    per = {p["variant"]: p for p in sens.summarize(rows, variants)["per_variant"]}
    assert per["width+10"]["flips_ok_to_fail"] == ["thu_trong"]
    assert per["width+10"]["flips_solved_on_recheck"] == ["thu_trong"]
    assert sens.RRT_SEED_ENV not in os.environ
    # Không có --recheck-time-limit thì không chạy lại.
    assert all("recheck" not in r for r in sens.run_sweep(scene, variants, 4.0, planner_spec=PROBE))


def test_nhieu_tien_trinh_giu_thu_tu_va_hat_giong_khi_xong_nguoc(ref_cfg, monkeypatch):
    """as_completed trả future theo thứ tự nộp ĐẢO NGƯỢC: hàng vẫn theo thứ tự nộp; hạt giống tới được tiến trình
    con."""
    monkeypatch.setattr(sens, "as_completed", lambda fs: reversed(list(fs)))
    variants = sens.build_variants(ref_cfg, ("width",), (10.0,), ())
    rows = sens.run_sweep({"thu_trong": open_scene()}, variants, 4.0, workers=2, rrt_seed=99, planner_spec=PROBE)
    assert [r["variant"] for r in rows] == ["goc", "width-10", "width+10"]
    assert {json.loads(r["message"])["seed"] for r in rows} == {"99"}


def test_cli_time_limit_va_rrt_seed_toi_plan_parking(tmp_path, capsys, monkeypatch):
    """Đường ứng dụng (`plan_parking`) nhận đúng --time-limit ở cả PlannerParams lẫn hạn chót, và đúng --rrt-seed."""
    seen = []

    def fake_plan_parking(sc, cfg, params, max_run_time=None, control=None):
        seen.append((params.time_limit, control.deadline - time.perf_counter(), os.environ.get(sens.RRT_SEED_ENV)))
        return PlanResult("NO_PATH", "giả")

    monkeypatch.setattr(sens, "plan_parking", fake_plan_parking)
    monkeypatch.delenv(sens.RRT_SEED_ENV, raising=False)
    out = tmp_path / "ra"
    assert sens.main(["--scenes", "lateral_shift", "--no-scenarios", "--params", "width", "--levels", "10",
                      "--combos", "none", "--time-limit", "3", "--rrt-seed", "555", "--out", str(out)]) == 0
    assert len(seen) == 3
    assert all(lim == 3.0 and 2.0 < rem <= 3.0 and seed == "555" for lim, rem, seed in seen), seen
    assert json.loads((out / "ket_qua.json").read_text(encoding="utf-8"))["manifest"]["rrt_seed"] == 555


def test_ngan_sach_sai_goi_truc_tiep_thanh_dong_error(ref_cfg):
    """Gọi thẳng `evaluate` với ngân sách nan/vô cùng: một dòng ERROR, không làm đổ cả lượt."""
    scene = open_scene()
    for bad in (math.nan, math.inf, -1.0):
        row = sens.evaluate(scene, baseline(ref_cfg), bad)
        assert row["status"] == "ERROR" and not row["solved"], (bad, row["message"])


# ---------------------------------------------------------------- nạp cấu hình xe có kiểm tra


@pytest.mark.parametrize("content, message", [
    (None, "không thấy tệp cấu hình xe"),
    ("{không phải json", "không phải JSON"),
    ("[1, 2]", "đối tượng JSON"),
    ('{"name": "x"}', "thiếu khóa"),
])
def test_tep_cau_hinh_hong_bao_ro_ly_do(tmp_path, content, message):
    path = tmp_path / "xe.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    with pytest.raises(sens.VehicleConfigError, match=message) as info:
        sens.load_vehicle_config_file(path)
    assert "xe.json" in str(info.value)


def test_tep_cau_hinh_so_am_hoac_goc_qua_lon_bi_tu_choi(tmp_path):
    with pytest.raises(sens.VehicleConfigError, match="width phải hữu hạn và > 0"):
        sens.load_vehicle_config_file(write_cfg(tmp_path / "am.json", width_m=-0.1))
    with pytest.raises(sens.VehicleConfigError, match="max_steer"):
        sens.load_vehicle_config_file(write_cfg(tmp_path / "goc.json", max_steer_deg=95.0))
    with pytest.raises(sens.VehicleConfigError, match="không phải một tệp"):
        sens.load_vehicle_config_file(tmp_path)
    ok = sens.load_vehicle_config_file(write_cfg(tmp_path / "tot.json"))
    assert ok.cfg.name == "xe_thu_tam" and ok.path == (tmp_path / "tot.json").resolve() and len(ok.sha256) == 64


# ---------------------------------------------------------------- CLI của sensitivity


@pytest.mark.planner_budget
def test_cli_sensitivity_ghi_json_va_bang(tmp_path, capsys):
    out = tmp_path / "ra"
    code = sens.main(["--scenes", "reverse_long_corridor", "--no-scenarios", "--params", "width", "--levels", "10",
                      "--combos", "none", "--time-limit", "4", "--plan-config", str(write_cfg(tmp_path / "do.json")),
                      "--out", str(out), "--note", "thu tu dong"])
    assert code == 0
    data = json.loads((out / "ket_qua.json").read_text(encoding="utf-8"))
    manifest = data["manifest"]
    assert manifest["evidence"] == "simulation_only" and manifest["time_limit_s"] == 4.0
    assert manifest["reference_config"]["path"] == str(DEFAULT_CFG_PATH.resolve())
    assert manifest["rrt_seed"] == cand_rrt_rs.DEFAULT_SEED and manifest["note_user"] == "thu tu dong"
    assert [v["name"] for v in manifest["variants"]] == ["goc", "width-10", "width+10", "tep:do"]
    assert [r["variant"] for r in data["rows"]] == ["goc", "width-10", "width+10", "tep:do"]
    assert len({r["scene_digest"] for r in data["rows"]}) == 1
    assert data["rows"][0]["solved"]
    table = (out / "bang_do_nhay.md").read_text(encoding="utf-8")
    assert "CHỈ MÔ PHỎNG" in table and "GIẢ ĐỊNH – CHƯA ĐO" in table
    assert "| `reverse_long_corridor` |" in table and "`tep:do`" in table


def test_cli_sensitivity_dung_cau_hinh_tham_chieu_de_dung_sa_ban(tmp_path, capsys, ref_cfg):
    small = write_cfg(tmp_path / "nho.json", wheelbase_m=0.15, width_m=0.10, front_overhang_m=0.04, rear_overhang_m=0.04)
    assert sens.main(["--reference-config", str(small), "--list", "--no-scenarios"]) == 0
    text = capsys.readouterr().out
    assert "nho.json" in text and "parallel_160" in text
    scenes_small = sens.build_scenes(sens.load_vehicle_config_file(small).cfg, None)
    scenes_ref = sens.build_scenes(ref_cfg, None)
    assert sens.scene_digest(scenes_small["parallel_160"].scenario) != sens.scene_digest(
        scenes_ref["parallel_160"].scenario)


@pytest.mark.parametrize("argv, message", [
    (["--reference-config", "khong_co_tep.json"], "không thấy tệp cấu hình xe"),
    (["--plan-config", "khong_co_tep.json"], "không thấy tệp cấu hình xe"),
    (["--levels", "150"], "(0, 100)"),
    (["--levels", "abc"], "--levels"),
    (["--params", "mui_xe"], "không có tham số"),
    (["--combos", "la"], "không có tổ hợp"),
    (["--scenes", "khong_co_ca"], "không có sa bàn"),
    (["--time-limit", "0"], "số dương"),
    (["--time-limit", "8", "--recheck-time-limit", "5"], "--recheck-time-limit"),
    # Tham số giới hạn quét: nếu kiểm tra hỏng, test hỏng nhanh thay vì chạy cả 860 lần.
    (["--scenes", "parallel_160", "--no-scenarios", "--params", "none", "--combos", "none",
      "--recheck-time-limit", "nan"], "--recheck-time-limit"),
    (["--scenes", "parallel_160", "--no-scenarios", "--params", "none", "--combos", "none",
      "--recheck-time-limit", "inf"], "--recheck-time-limit"),
    (["--workers", "0"], "--workers"),
    (["--planner", "khong_dung_dang"], "--planner"),
])
def test_cli_sensitivity_tu_choi_tham_so_sai(argv, message, capsys, tmp_path):
    out = tmp_path / "khong_duoc_tao"
    with pytest.raises(SystemExit) as info:
        sens.main(argv + ["--out", str(out)])
    assert info.value.code == 2
    assert message in capsys.readouterr().err
    assert not out.exists()


@pytest.mark.parametrize("value", ["nan", "inf", "NaN", "Infinity", "-1", "abc"])
def test_recheck_time_limit_tu_choi_nan_inf_am(value, capsys):
    with pytest.raises(SystemExit) as info:
        sens.build_parser().parse_args(["--recheck-time-limit", value])
    assert info.value.code == 2 and "--recheck-time-limit" in capsys.readouterr().err


def test_recheck_time_limit_0_la_tat_va_nan_bi_chan_truoc_khi_quet(capsys, monkeypatch):
    assert sens.build_parser().parse_args(["--recheck-time-limit", "0"]).recheck_time_limit == 0.0
    assert sens.build_parser().parse_args(["--recheck-time-limit", "12.5"]).recheck_time_limit == 12.5

    def must_not_run(*args, **kwargs):
        raise AssertionError("không được bắt đầu quét khi tham số sai")

    monkeypatch.setattr(sens, "run_sweep", must_not_run)
    with pytest.raises(SystemExit) as info:
        sens.main(["--list", "--no-scenarios", "--recheck-time-limit", "nan"])
    assert info.value.code == 2


def test_cli_sensitivity_khong_ghi_de_thu_muc_da_co(tmp_path, capsys):
    out = tmp_path / "cu"
    out.mkdir()
    (out / "ket_qua.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit) as info:
        sens.main(["--scenes", "lateral_shift", "--params", "none", "--combos", "none", "--out", str(out)])
    assert info.value.code == 2 and "đã có dữ liệu" in capsys.readouterr().err
    assert (out / "ket_qua.json").read_text(encoding="utf-8") == "{}"


# ---------------------------------------------------------------- --vehicle-config của robustness, phase0, lidar_app


def test_robustness_dung_cau_hinh_xe_duoc_chon(tmp_path):
    cfg_path = write_cfg(tmp_path / "xe.json")
    out = tmp_path / "ra"
    robustness.main(["--out", str(out), "--vehicle-config", str(cfg_path),
                     "--poses", "3", "--motions", "0", "--runs", "0", "--plans", "0"])
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["base_vehicle"]["name"] == "xe_thu_tam"
    assert manifest["vehicle_config"]["path"] == str(cfg_path.resolve())
    assert manifest["arguments"]["vehicle_config"] == str(cfg_path.resolve())
    cases = [json.loads(line) for line in (out / "cases.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(cases) == 3
    for case in cases:   # varied_config nhân mọi kích thước với cùng hệ số: tỉ lệ L/rộng phải là của tệp đã chọn
        v = case["input"]["vehicle"]
        assert v["wheelbase_m"] / v["width_m"] == pytest.approx(0.30 / 0.10)


def test_robustness_varied_config_chi_giu_ti_le_footprint_cua_tep(tmp_path):
    """Ghim hành vi đã ghi trong docstring robustness.py và DO_NHAY_KICH_THUOC_XE.md mục 3: ca pose/swept/runtime giữ
    tỉ lệ footprint của tệp nhưng rút góc lái 22–38° và tốc độ 0,06–0,30 m/s từ khoảng cố định, KHÔNG theo tệp.
    Đổi hành vi này thì phải sửa cả hai tài liệu."""
    base = sens.load_vehicle_config_file(write_cfg(tmp_path / "xe.json", max_steer_deg=20.0, max_speed_mps=0.5)).cfg
    for seed in range(50):
        v = robustness.varied_config(base, random.Random(seed))
        assert v.wheelbase / v.width == pytest.approx(base.wheelbase / base.width)
        assert v.front_overhang / v.wheelbase == pytest.approx(base.front_overhang / base.wheelbase)
        assert v.rear_overhang / v.wheelbase == pytest.approx(base.rear_overhang / base.wheelbase)
        assert 0.7 - 1e-9 <= v.wheelbase / base.wheelbase <= 1.4 + 1e-9
        assert math.radians(22) - 1e-9 <= v.max_steer <= math.radians(38) + 1e-9     # tệp ghi 20°
        assert 0.06 - 1e-9 <= v.max_speed <= 0.30 + 1e-9                               # tệp ghi 0,5 m/s


def test_robustness_mac_dinh_van_la_vehicle_default(tmp_path):
    out = tmp_path / "ra"
    robustness.main(["--out", str(out), "--poses", "1", "--motions", "0", "--runs", "0", "--plans", "0"])
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["vehicle_config"]["path"] == str(DEFAULT_CFG_PATH.resolve())
    assert manifest["base_vehicle"] == load_vehicle_config(DEFAULT_CFG_PATH).to_dict()


def test_robustness_tep_hong_thoat_truoc_khi_tao_thu_muc(tmp_path, capsys):
    out = tmp_path / "ra"
    with pytest.raises(SystemExit) as info:
        robustness.main(["--out", str(out), "--vehicle-config", str(write_cfg(tmp_path / "hong.json", width_m=0))])
    assert info.value.code == 2 and "width phải hữu hạn và > 0" in capsys.readouterr().err
    assert not out.exists()


class _Stop(Exception):
    pass


def _spy_session(captured):
    class SpySession:
        def __init__(self, scenario, cfg, *args, **kwargs):
            captured.append(cfg)
            raise _Stop

    return SpySession


def test_phase0_dung_cau_hinh_xe_duoc_chon(tmp_path, monkeypatch):
    captured = []
    monkeypatch.setattr(phase0, "Session", _spy_session(captured))
    cfg_path = write_cfg(tmp_path / "xe.json")
    with pytest.raises(_Stop):
        phase0.main(["--out", str(tmp_path / "ra"), "--vehicle-config", str(cfg_path)])
    assert captured[0].name == "xe_thu_tam" and captured[0].wheelbase == pytest.approx(0.30)
    used = json.loads((tmp_path / "ra" / "vehicle_config_used.json").read_text(encoding="utf-8"))
    assert used["path"] == str(cfg_path.resolve()) and used["config"]["name"] == "xe_thu_tam"

    captured.clear()
    with pytest.raises(_Stop):
        phase0.main(["--out", str(tmp_path / "ra2")])
    assert captured[0] == load_vehicle_config(DEFAULT_CFG_PATH)


def test_phase0_tep_hong_thoat_ma_2(tmp_path, capsys):
    with pytest.raises(SystemExit) as info:
        phase0.main(["--out", str(tmp_path / "ra"), "--vehicle-config", str(tmp_path / "khong_co.json")])
    assert info.value.code == 2 and "không thấy tệp cấu hình xe" in capsys.readouterr().err
    assert not (tmp_path / "ra").exists()


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

    scenario_path = PROJECT_ROOT / "scenarios" / "sa_ban_3x2_hai_hop.json"
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

    opened = PROJECT_ROOT / "scenarios" / "sa_ban_3x2_hai_hop.json"
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
        assert window.session.cfg == load_vehicle_config(DEFAULT_CFG_PATH)
    finally:
        _close(window, dock)


def test_lidar_app_mo_kich_ban_tep_xe_cua_kich_ban_hong_van_dung_xe_da_chon(qapp, tmp_path, monkeypatch):
    """Kịch bản trỏ tới tệp xe không có: với --vehicle-config vẫn mở được, không hiện hộp lỗi."""
    from autopark.ui import lidar_app

    data = json.loads((PROJECT_ROOT / "scenarios" / "sa_ban_3x2_hai_hop.json").read_text(encoding="utf-8"))
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


def test_so_sanh_voi_ban_sao_khong_doi_scene(scenes):
    """Bản sao sâu của một sa bàn cho cùng digest; digest đổi khi đổi vật cản (digest thật sự nhìn vào hình học)."""
    sc = copy.deepcopy(scenes["pillar_at_slot_mouth"].scenario)
    assert sens.scene_digest(sc) == sens.scene_digest(scenes["pillar_at_slot_mouth"].scenario)
    sc.obstacles[0] = Obstacle(sc.obstacles[0].id, sc.obstacles[0].cx + 0.01, sc.obstacles[0].cy,
                               sc.obstacles[0].width, sc.obstacles[0].height)
    assert sens.scene_digest(sc) != sens.scene_digest(scenes["pillar_at_slot_mouth"].scenario)
