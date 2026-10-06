"""Độ nhạy của bộ lập đường theo kích thước xe, với SA BÀN CỐ ĐỊNH. Chỉ là mô phỏng.

Vì sao cần công cụ này: `bench`, `compare`, `render` dựng bộ ca khó bằng `build_cases(cfg)` với CHÍNH cấu hình dùng để
lập đường, nên đổi cỡ xe thì ô đỗ, lối đi và xe đỗ bên cạnh phóng theo xe (GIAI_DOAN_4_CHUAN_BI.md mục 5.1). Ở đây sa
bàn được dựng MỘT LẦN từ cấu hình tham chiếu (mặc định `configs/vehicle_default.json`; mọi số trong tệp đó là GIẢ ĐỊNH
– CHƯA ĐO), rồi lập đường và kiểm va chạm bằng cấu hình đã đổi.

Quy ước (đọc kỹ trước khi dùng kết quả):
- Sa bàn = vùng, vật cản, xe đỗ bên cạnh, ô đỗ, tư thế xuất phát (tâm trục sau). Giữ nguyên cho mọi biến thể xe.
- Kịch bản có ô đỗ: đích được tính lại cho xe đang thử để thân xe nằm giữa CÙNG ô đó (`Scenario.sync_goal`, như ứng
  dụng làm). Kịch bản không có ô đỗ: đích (tâm trục sau) giữ nguyên.
- Lập đường qua `plan_parking` (đường của ứng dụng: thang portfolio có kiểm chứng bám đường). Ngân sách thời gian mặc
  định bằng `PlannerParams().time_limit` của ứng dụng; `--time-limit` đổi được. Hạt giống RRT cố định (`--rrt-seed`,
  mặc định `cand_rrt_rs.DEFAULT_SEED`), đặt qua biến môi trường `AUTOPARK_RRT_SEED` trong lúc chạy.
- Chấm một lần chạy là "giải được" khi: trạng thái OK; kiểm vùng quét độc lập (`check_motion`) không chạm; kiểm lấy
  mẫu độc lập (`collision_oracle`, cả điểm giữa hai mẫu) không chạm; góc lái không vượt `max_steer` của xe đang thử;
  xe mô phỏng bám tới đích của sa bàn (không phải đích planner tự ghi trong quỹ đạo) trong dung sai (`rollout`, cùng
  cấu hình xe đang thử).
- "Lật" = ca giải được với xe tham chiếu nhưng không giải được với biến thể (hoặc ngược lại).
- TIMEOUT phụ thuộc tải CPU, KHÔNG có nghĩa là vô nghiệm hình học. `--recheck-time-limit` chạy lại các ca lật với ngân
  sách dài hơn để tách hai loại này. Chạy nhiều tiến trình (`--workers`) làm các lần chạy tranh CPU với nhau; số giây
  ghi trong kết quả phải đọc kèm số tiến trình và tải máy lúc chạy.

Không có số nào ở đây là số đo trên xe thật hay trên MN300.

Dùng (chạy trong thư mục `autopark` của repo, thư mục có pyproject.toml; mỗi lệnh là MỘT dòng, dán thẳng vào cmd.exe):
    .venv\\Scripts\\python.exe -X utf8 -m autopark.evaluation.sensitivity --list
    .venv\\Scripts\\python.exe -X utf8 -m autopark.evaluation.sensitivity --scenes parallel_160,uturn_w55 --params width --levels 10 --combos none --out runs\\do_nhay_xe\\thu_nhanh
    .venv\\Scripts\\python.exe -X utf8 -m autopark.evaluation.sensitivity --workers 4 --recheck-time-limit 20
    .venv\\Scripts\\python.exe -X utf8 -m autopark.evaluation.sensitivity --params none --combos none --plan-config configs\\vehicle_measured.json

Đầu ra (mặc định `runs/do_nhay_xe/<ngày_giờ>/`): `ket_qua.json` (mọi lần chạy, cấu hình, môi trường) và
`bang_do_nhay.md` (bảng tóm tắt). Mã thoát 1 khi có vi phạm an toàn: bộ lập đường báo OK nhưng kiểm độc lập thấy chạm
hoặc góc lái vượt giới hạn.
"""
from __future__ import annotations

import argparse
from collections import Counter
import contextlib
import copy
import hashlib
import importlib
import inspect
import json
import math
import os
import statistics
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterator

from autopark.application.session import Session
from autopark.domain.computation import ComputationCancelled, ComputationControl, ComputationTimedOut
from autopark.domain.types import Pose, Scenario, VehicleConfig
from autopark.evaluation import collision_oracle as oracle
from autopark.evaluation.hard_cases import build_cases
from autopark.geometry.footprint import check_motion, check_pose
from autopark.planning.cand_rrt_rs import DEFAULT_SEED as RRT_DEFAULT_SEED
from autopark.planning.hybrid_astar import PlannerParams, PlanResult
from autopark.planning.parking import plan_parking
from autopark.power_throttling import apply_ecoqos_policy, ecoqos_state
from autopark.simulation.rollout import rollout
from autopark.storage.scenario_store import load_scenario
# Nạp tệp xe có kiểm tra: chuyển sang storage/scenario_store.py (02/10/2026); xuất lại cùng tên cho phase0, robustness,
# ui.lidar_app và test.
from autopark.storage.scenario_store import (REQUIRED_VEHICLE_KEYS, VehicleConfigError,  # noqa: F401
                                            VehicleConfigFile, load_vehicle_config_file, vehicle_config_arg)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REFERENCE = PROJECT_ROOT / "configs" / "vehicle_default.json"
DEFAULT_SCENARIO_DIR = PROJECT_ROOT / "scenarios"
DEFAULT_OUT_ROOT = PROJECT_ROOT / "runs" / "do_nhay_xe"
APP_PLANNER = "app"                  # plan_parking, đúng đường ứng dụng gọi
APP_MAX_RUN_TIME = Session.MAX_RUN_TIME   # s mô phỏng khi planner kiểm chứng bám đường, như Session.plan_sync
ROLLOUT_MAX_TIME = 240.0             # s mô phỏng cho lần bám kín vòng độc lập, như bench.run_case
RRT_SEED_ENV = "AUTOPARK_RRT_SEED"

# ---------------------------------------------------------------- sa bàn cố định

@dataclass(frozen=True)
class Scene:
    """Một sa bàn dựng từ cấu hình tham chiếu. `scenario` không bao giờ bị sửa; mỗi lần chạy dùng bản sao."""

    name: str
    source: str
    difficulty: str
    expected: str
    scenario: Scenario


def scene_geometry(sc: Scenario) -> dict[str, Any]:
    """Phần cố định của sa bàn: vùng, vật cản, xuất phát, ô đỗ/kiểu đỗ; đích chỉ tính khi không có ô đỗ."""
    geometry: dict[str, Any] = {"bounds": sc.bounds.to_dict(), "start": sc.start.to_dict(),
                                "obstacles": [o.to_dict() for o in sc.obstacles]}
    if sc.slot is not None:
        geometry["slot"] = sc.slot.to_dict()
        geometry["mode"] = sc.mode.value
    else:
        geometry["goal"] = sc.goal.to_dict()
    return geometry


def scene_digest(sc: Scenario) -> str:
    """sha256 (16 ký tự đầu) của phần cố định; hai lần chạy cùng sa bàn phải có cùng giá trị."""
    text = json.dumps(scene_geometry(sc), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(text.encode("ascii")).hexdigest()[:16]


def build_scenes(reference: VehicleConfig, scenario_dir: Path | None = DEFAULT_SCENARIO_DIR,
                 include_hard_cases: bool = True) -> dict[str, Scene]:
    """Dựng mọi sa bàn MỘT LẦN từ `reference`: 16 ca khó và các tệp `scenarios/*.json` (tên `kb_<tệp>`)."""
    scenes: dict[str, Scene] = {}
    if include_hard_cases:
        for name, case in build_cases(reference).items():
            scenes[name] = Scene(name, "evaluation/hard_cases.py", case.difficulty, case.expected,
                                 copy.deepcopy(case.scenario))
    if scenario_dir is not None:
        for path in sorted(Path(scenario_dir).glob("*.json")):
            sc = load_scenario(path)
            sc.sync_goal(reference)
            name = "kb_" + path.stem
            scenes[name] = Scene(name, f"scenarios/{path.name}", "kich_ban", "unknown", sc)
    return scenes


# ---------------------------------------------------------------- biến thể xe

LENGTH_ATTRS = ("rear_overhang", "wheelbase", "front_overhang")
FOOTPRINT_ATTRS = LENGTH_ATTRS + ("width",)
PARAM_ATTRS: dict[str, tuple[str, ...]] = {
    "length": LENGTH_ATTRS,                         # cả xe dài ra: nhô sau, chiều dài cơ sở, nhô trước cùng hệ số
    "width": ("width",),
    "overhangs": ("front_overhang", "rear_overhang"),
    "wheelbase": ("wheelbase",),
    "max_steer": ("max_steer",),
    "front_overhang": ("front_overhang",),
    "rear_overhang": ("rear_overhang",),
}
PARAM_LABELS = {
    "length": "chiều dài thân (nhô sau + L + nhô trước cùng hệ số)",
    "width": "bề rộng",
    "overhangs": "hai phần nhô (trước và sau)",
    "wheelbase": "chiều dài cơ sở L",
    "max_steer": "góc lái lớn nhất",
    "front_overhang": "nhô trước",
    "rear_overhang": "nhô sau",
}
DEFAULT_PARAMS = ("length", "width", "overhangs", "wheelbase", "max_steer")
# Tổ hợp: (hệ số dấu cho footprint, hệ số dấu cho góc lái, chạy cả hai chiều ±)
COMBOS: dict[str, tuple[int, int, bool]] = {
    "kich_thuoc": (+1, 0, True),     # phóng đều footprint (dài và rộng), giữ góc lái
    "lon_lai_kem": (+1, -1, False),  # xe to hơn p % VÀ góc lái nhỏ hơn p %: phía bất lợi
    "nho_lai_gat": (-1, +1, False),  # xe nhỏ hơn p % VÀ góc lái lớn hơn p %: phía thuận lợi
}
COMBO_LABELS = {
    "kich_thuoc": "phóng đều footprint (dài và rộng), giữ góc lái",
    "lon_lai_kem": "footprint +p %, góc lái −p %",
    "nho_lai_gat": "footprint −p %, góc lái +p %",
}
DEFAULT_COMBOS = ("kich_thuoc", "lon_lai_kem", "nho_lai_gat")
DEFAULT_LEVELS = (5.0, 10.0, 20.0)
BASELINE = "goc"


@dataclass(frozen=True)
class Variant:
    name: str
    group: str                                  # "goc", tên tham số, tên tổ hợp, hoặc "tep"
    level_pct: float                            # có dấu; 0 cho xe gốc và cấu hình từ tệp
    factors: tuple[tuple[str, float], ...]      # (thuộc tính VehicleConfig, hệ số nhân)
    cfg: VehicleConfig
    source: str = ""


def scaled_config(base: VehicleConfig, factors: dict[str, float], name: str) -> VehicleConfig:
    """Nhân các thuộc tính của `base` với hệ số; biến thể không hợp lệ (ví dụ góc ≥ 89°) thành ValueError."""
    unknown = [a for a in factors if not hasattr(base, a)]
    if unknown:
        raise ValueError(f"không có thuộc tính xe: {', '.join(unknown)}")
    changes = {attr: getattr(base, attr) * factor for attr, factor in factors.items()}
    note = ", ".join(f"{attr} × {factor:.3f}" for attr, factor in factors.items())
    cfg = replace(base, name=name, notes=f"BIẾN THỂ MÔ PHỎNG của '{base.name}' ({note}); không phải số đo.", **changes)
    problems = cfg.validate()
    if problems:
        raise ValueError(f"biến thể {name} không hợp lệ: {'; '.join(problems)}")
    return cfg


def _level_name(level: float) -> str:
    return f"{level:g}"


def build_variants(base: VehicleConfig, params: tuple[str, ...] = DEFAULT_PARAMS,
                   levels: tuple[float, ...] = DEFAULT_LEVELS, combos: tuple[str, ...] = DEFAULT_COMBOS,
                   plan_configs: tuple[VehicleConfigFile, ...] = ()) -> list[Variant]:
    """Xe gốc, rồi từng tham số ±mức, rồi các tổ hợp, rồi các cấu hình lấy từ tệp (ví dụ xe đã đo)."""
    variants = [Variant(BASELINE, BASELINE, 0.0, (), base)]
    for param in params:
        if param not in PARAM_ATTRS:
            raise ValueError(f"không có tham số '{param}'; có: {', '.join(PARAM_ATTRS)}")
        for level in levels:
            for sign in (-1, +1):
                factor = 1 + sign * level / 100
                name = f"{param}{'+' if sign > 0 else '-'}{_level_name(level)}"
                factors = {attr: factor for attr in PARAM_ATTRS[param]}
                variants.append(Variant(name, param, sign * level, tuple(factors.items()),
                                        scaled_config(base, factors, name)))
    for combo in combos:
        if combo not in COMBOS:
            raise ValueError(f"không có tổ hợp '{combo}'; có: {', '.join(COMBOS)}")
        size_sign, steer_sign, both = COMBOS[combo]
        for level in levels:
            for sign in ((-1, +1) if both else (+1,)):
                factors = {attr: 1 + sign * size_sign * level / 100 for attr in FOOTPRINT_ATTRS}
                if steer_sign:
                    factors["max_steer"] = 1 + sign * steer_sign * level / 100
                name = f"{combo}{'+' if sign > 0 else '-'}{_level_name(level)}"
                variants.append(Variant(name, combo, sign * level, tuple(factors.items()),
                                        scaled_config(base, factors, name)))
    for item in plan_configs:
        variants.append(Variant(f"tep:{item.path.stem}", "tep", 0.0, (), item.cfg, str(item.path)))
    names = [v.name for v in variants]
    duplicated = sorted({n for n in names if names.count(n) > 1})
    if duplicated:
        raise ValueError(f"trùng tên biến thể: {', '.join(duplicated)}")
    return variants


# ---------------------------------------------------------------- một lần chạy

PlannerFn = Callable[..., PlanResult]


def _plan_app(sc: Scenario, cfg: VehicleConfig, time_limit: float) -> PlanResult:
    """Giống `Session._calculate_plan`: plan_parking với cùng ngân sách, lỗi thuật toán thành ERROR.

    Ngân sách sai (nan, vô cùng, âm) từ lời gọi trực tiếp `evaluate`/`run_sweep` cũng thành một dòng ERROR thay vì
    làm đổ cả lượt quét."""
    try:
        control = ComputationControl().with_timeout(time_limit)
        return plan_parking(copy.deepcopy(sc), cfg, PlannerParams(time_limit=time_limit),
                            max_run_time=APP_MAX_RUN_TIME, control=control)
    except ComputationCancelled:
        return PlanResult("CANCELLED", "Đã hủy tính đường")
    except ComputationTimedOut:
        return PlanResult("TIMEOUT", "Đã hết thời gian tính đường")
    except Exception as exc:  # noqa: BLE001 - lỗi thuật toán phải khác với không tìm được đường
        return PlanResult("ERROR", f"Lỗi lập đường: {exc!r}")


def _plan_custom(func: PlannerFn, sc: Scenario, goal: Pose, cfg: VehicleConfig, time_limit: float) -> PlanResult:
    """Bộ lập đường theo giao diện của bench: plan(start, goal, cfg, obstacles, bounds, ...)."""
    kwargs: dict[str, Any] = {}
    try:
        sig = inspect.signature(func)
        if "time_limit" in sig.parameters:
            kwargs["time_limit"] = time_limit
        elif "params" in sig.parameters:
            kwargs["params"] = PlannerParams(time_limit=time_limit)
    except (TypeError, ValueError):
        kwargs["time_limit"] = time_limit
    try:
        return func(sc.start, goal, cfg, list(sc.obstacles), sc.bounds, **kwargs)
    except Exception as exc:  # noqa: BLE001
        return PlanResult("ERROR", f"Lỗi lập đường: {exc!r}")


def _round(value: float | None, digits: int) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(float(value), digits)


def _interpolated(a: Pose, b: Pose) -> Iterator[Pose]:
    dyaw = math.atan2(math.sin(b.yaw - a.yaw), math.cos(b.yaw - a.yaw))
    for fraction in (0.25, 0.5, 0.75):
        yield Pose(a.x + fraction * (b.x - a.x), a.y + fraction * (b.y - a.y), a.yaw + fraction * dyaw)


def evaluate(scene: Scene, variant: Variant, time_limit: float, planner: PlannerFn | None = None) -> dict[str, Any]:
    """Lập đường cho `variant.cfg` trên sa bàn cố định `scene` và chấm độc lập. Không sửa `scene`."""
    cfg = variant.cfg
    sc = copy.deepcopy(scene.scenario)
    goal = sc.sync_goal(cfg)                                    # chỉ đổi khi có ô đỗ; vật cản/vùng/xuất phát giữ nguyên
    start_check = check_pose(cfg, sc.start, sc.obstacles, sc.bounds)
    goal_check = check_pose(cfg, goal, sc.obstacles, sc.bounds)
    row: dict[str, Any] = {
        "scene": scene.name, "variant": variant.name, "group": variant.group, "level_pct": variant.level_pct,
        "time_limit_s": time_limit, "scene_digest": scene_digest(sc), "goal": goal.to_dict(),
        "start_clear": start_check.ok, "goal_clear": goal_check.ok,
        "slot_fits": sc.slot.fits_vehicle(cfg) if sc.slot is not None else None,
        "status": "", "solved": False, "verdict": "", "plan_s": None, "wall_s": None,
        "length_m": None, "cusps": None, "min_clearance_m": None, "run_min_clearance_m": None,
        "path_ok": None, "oracle_ok": None, "steer_ok": None, "tracked": None,
        "pos_err_m": None, "yaw_err_deg": None, "violations": [], "message": "",
    }
    t0 = time.perf_counter()
    result = _plan_app(sc, cfg, time_limit) if planner is None else _plan_custom(planner, sc, goal, cfg, time_limit)
    wall = time.perf_counter() - t0
    row["status"] = result.status
    row["plan_s"] = _round(result.elapsed or wall, 4)
    row["message"] = result.message
    traj = result.trajectory
    if result.status != "OK" or traj is None or not traj.points:
        row["verdict"] = result.status or "?"
        row["wall_s"] = _round(time.perf_counter() - t0, 4)
        return row

    points = traj.points
    row["length_m"] = _round(traj.length, 4)
    row["cusps"] = traj.n_cusps
    row["path_ok"] = all(check_motion(cfg, a.pose, b.pose, sc.obstacles, sc.bounds).ok
                         for a, b in zip(points, points[1:]))
    row["oracle_ok"] = (all(oracle.pose_ok(cfg, p.pose, sc.obstacles, sc.bounds) for p in points)
                        and all(oracle.pose_ok(cfg, q, sc.obstacles, sc.bounds)
                                for a, b in zip(points, points[1:]) for q in _interpolated(a.pose, b.pose)))
    row["steer_ok"] = all(abs(p.steer) <= cfg.max_steer + 1e-9 for p in points)
    row["min_clearance_m"] = _round(min(check_pose(cfg, p.pose, sc.obstacles, sc.bounds).min_clearance
                                        for p in points), 5)
    if not row["path_ok"]:
        row["violations"].append("planner_ok_but_swept_check_collides")
    if not row["oracle_ok"]:
        row["violations"].append("planner_ok_but_sampled_oracle_collides")
    if not row["steer_ok"]:
        row["violations"].append("planner_ok_but_steer_above_vehicle_limit")

    # Sai số cuối tính tới đích CỦA SA BÀN, không tới `traj.goal` do planner tự khai: planner dừng trước đích rồi khai
    # đích là điểm dừng thì vẫn bị bắt. Bộ bám không đọc `goal`, nên với planner của ứng dụng (dựng quỹ đạo bằng
    # đúng đích được yêu cầu) việc này không đổi kết quả.
    run = rollout(sc, cfg, replace(traj, goal=goal), max_time=ROLLOUT_MAX_TIME)
    rep = run.report
    row["pos_err_m"] = _round(rep.position_error, 5)
    row["yaw_err_deg"] = _round(math.degrees(rep.heading_error), 3)
    row["tracked"] = bool(rep.completed and not rep.collided and rep.position_error <= sc.goal.tolerance_xy
                          and abs(rep.heading_error) <= sc.goal.tolerance_yaw)
    if run.states:
        row["run_min_clearance_m"] = _round(min(check_pose(cfg, s.pose, sc.obstacles, sc.bounds).min_clearance
                                                for s in run.states), 5)
    if not row["tracked"]:
        row["message"] = "Bám đường không đạt: " + rep.describe()
    row["solved"] = bool(row["path_ok"] and row["oracle_ok"] and row["steer_ok"] and row["tracked"])
    if row["solved"]:
        row["verdict"] = "GIAI_DUOC"
    elif row["violations"]:
        row["verdict"] = "VI_PHAM"
    else:
        row["verdict"] = "BAM_HONG"
    row["wall_s"] = _round(time.perf_counter() - t0, 4)
    return row


# ---------------------------------------------------------------- chạy cả lượt

def load_planner_spec(spec: str) -> PlannerFn | None:
    if spec == APP_PLANNER:
        return None
    module_name, _, func_name = spec.partition(":")
    if not module_name or not func_name:
        raise ValueError(f"--planner phải là '{APP_PLANNER}' hoặc có dạng module:ham, nhận {spec!r}")
    return getattr(importlib.import_module(module_name), func_name)


def _run_task(task: tuple[Scene, Variant, float, str]) -> dict[str, Any]:
    """Hàm cấp mô-đun để tiến trình con gọi được (Windows dùng spawn)."""
    scene, variant, time_limit, planner_spec = task
    row = evaluate(scene, variant, time_limit, load_planner_spec(planner_spec))
    row["ecoqos"] = ecoqos_state()        # của tiến trình đã chạy ca này (tiến trình con khi --workers > 1)
    return row


@contextlib.contextmanager
def rrt_seed_env(seed: int) -> Iterator[None]:
    """Đặt hạt giống RRT cho lượt chạy (cả tiến trình con), trả lại giá trị cũ khi xong."""
    old = os.environ.get(RRT_SEED_ENV)
    os.environ[RRT_SEED_ENV] = str(int(seed))
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(RRT_SEED_ENV, None)
        else:
            os.environ[RRT_SEED_ENV] = old


def _execute(tasks: list[tuple[Scene, Variant, float, str]], workers: int, seed: int,
             progress: Callable[[int, int, dict[str, Any]], None] | None) -> list[dict[str, Any]]:
    results: list[dict[str, Any] | None] = [None] * len(tasks)
    with rrt_seed_env(seed):
        if workers <= 1:
            for i, task in enumerate(tasks):
                results[i] = _run_task(task)
                if progress:
                    progress(i + 1, len(tasks), results[i])
        else:
            # Tham chiếu hàm qua tên mô-đun thật, để tiến trình con nạp được cả khi chạy bằng `python -m`.
            fn = importlib.import_module("autopark.evaluation.sensitivity")._run_task
            # Tiến trình con không thừa hưởng EcoQoS của tiến trình mẹ: mỗi tiến trình con tự tắt (02/10/2026).
            with ProcessPoolExecutor(max_workers=workers, initializer=apply_ecoqos_policy,
                                     initargs=("evaluation.sensitivity:worker",)) as pool:
                futures = {pool.submit(fn, task): i for i, task in enumerate(tasks)}
                for done, future in enumerate(as_completed(futures), 1):
                    i = futures[future]
                    results[i] = future.result()
                    if progress:
                        progress(done, len(tasks), results[i])
    return [r for r in results if r is not None]


def run_sweep(scenes: dict[str, Scene], variants: list[Variant], time_limit: float, *,
              recheck_time_limit: float = 0.0, workers: int = 1, rrt_seed: int = RRT_DEFAULT_SEED,
              planner_spec: str = APP_PLANNER,
              progress: Callable[[int, int, dict[str, Any]], None] | None = None) -> list[dict[str, Any]]:
    """Mọi cặp (sa bàn, biến thể), theo thứ tự cố định; kết quả không phụ thuộc thứ tự tiến trình con xong."""
    tasks = [(scene, variant, time_limit, planner_spec) for scene in scenes.values() for variant in variants]
    rows = _execute(tasks, workers, rrt_seed, progress)
    if recheck_time_limit > time_limit:
        base = {r["scene"]: r for r in rows if r["variant"] == BASELINE}
        by_name = {v.name: v for v in variants}
        again = [i for i, r in enumerate(rows)
                 if r["scene"] in base and base[r["scene"]]["solved"] and not r["solved"]
                 and r["status"] not in ("START_INVALID", "GOAL_INVALID")]
        if again:
            retasks = [(scenes[rows[i]["scene"]], by_name[rows[i]["variant"]], recheck_time_limit, planner_spec)
                       for i in again]
            for i, rerun in zip(again, _execute(retasks, workers, rrt_seed, progress)):
                rows[i]["recheck"] = {key: rerun[key] for key in (
                    "time_limit_s", "status", "solved", "verdict", "plan_s", "length_m", "cusps",
                    "min_clearance_m", "tracked", "violations", "message")}
    return rows


# ---------------------------------------------------------------- tóm tắt

def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def summarize(rows: list[dict[str, Any]], variants: list[Variant]) -> dict[str, Any]:
    base = {r["scene"]: r for r in rows if r["variant"] == BASELINE}
    per_variant = []
    for v in variants:
        vr = [r for r in rows if r["variant"] == v.name]
        solved = [r for r in vr if r["solved"]]
        per_variant.append({
            "variant": v.name, "group": v.group, "level_pct": v.level_pct,
            "factors": dict(v.factors), "config": v.cfg.to_dict(), "source": v.source,
            "solved": len(solved), "total": len(vr),
            "flips_ok_to_fail": [r["scene"] for r in vr if base.get(r["scene"], {}).get("solved") and not r["solved"]],
            "flips_fail_to_ok": [r["scene"] for r in vr
                                 if r["scene"] in base and not base[r["scene"]]["solved"] and r["solved"]],
            "flips_solved_on_recheck": [r["scene"] for r in vr if (r.get("recheck") or {}).get("solved")],
            "median_plan_s_solved": _median([r["plan_s"] for r in solved if r["plan_s"] is not None]),
            "max_plan_s_solved": max((r["plan_s"] for r in solved if r["plan_s"] is not None), default=None),
            "median_min_clearance_m": _median([r["min_clearance_m"] for r in solved
                                               if r["min_clearance_m"] is not None]),
            "min_min_clearance_m": min((r["min_clearance_m"] for r in solved if r["min_clearance_m"] is not None),
                                       default=None),
            "median_cusps": _median([r["cusps"] for r in solved if r["cusps"] is not None]),
            "violations": sorted({f"{r['scene']}:{x}" for r in vr for x in r["violations"]}),
        })
    thresholds: dict[str, dict[str, dict[str, Any]]] = {}
    groups = [g for g in dict.fromkeys(v.group for v in variants) if g not in (BASELINE, "tep")]
    for scene, b in base.items():
        if not b["solved"]:
            continue
        thresholds[scene] = {}
        for group in groups:
            entry: dict[str, Any] = {}
            for side, sign in (("tang", +1), ("giam", -1)):
                levels = sorted((abs(r["level_pct"]), r["solved"]) for r in rows
                                if r["scene"] == scene and r["group"] == group and r["level_pct"] * sign > 0)
                first = next((lv for lv, ok in levels if not ok), None)
                entry[side] = None if first is None else sign * first
                entry[side + "_khong_don_dieu"] = first is not None and any(
                    ok for lv, ok in levels if lv > first)
                entry[side + "_co_du_lieu"] = bool(levels)
            thresholds[scene][group] = entry
    return {"per_variant": per_variant, "thresholds": thresholds,
            "violations": sorted({f"{r['scene']}/{r['variant']}:{x}" for r in rows for x in r["violations"]})}


# ---------------------------------------------------------------- bảng markdown

SYMBOL_SOLVED, SYMBOL_TIMEOUT, SYMBOL_FAIL = "✓", "T", "✗"


def _symbol(row: dict[str, Any] | None) -> str:
    if row is None:
        return "·"
    if row["solved"]:
        return SYMBOL_SOLVED
    return SYMBOL_TIMEOUT if row["status"] == "TIMEOUT" else SYMBOL_FAIL


def _fmt(value: float | None, digits: int = 2, scale: float = 1.0) -> str:
    return "—" if value is None else f"{value * scale:.{digits}f}"


def _threshold_text(entry: dict[str, Any]) -> str:
    parts = []
    for side in ("tang", "giam"):
        if not entry.get(side + "_co_du_lieu"):
            continue
        level = entry[side]
        if level is None:
            continue
        parts.append(f"{level:+g} %" + ("*" if entry[side + "_khong_don_dieu"] else ""))
    return ", ".join(parts) if parts else "—"


def _ecoqos_text(manifest: dict[str, Any]) -> str:
    """'off (từng ca: off ×52)': EcoQoS của tiến trình chính và của các tiến trình đã chạy từng ca; ket_qua.json ghi
    trước 02/10/2026 không có → '—'."""
    per_row = ", ".join(f"{state} ×{count}" for state, count in (manifest.get("ecoqos_rows") or {}).items())
    return (manifest.get("ecoqos") or "—") + (f" (từng ca: {per_row})" if per_row else "")


def markdown_report(data: dict[str, Any]) -> str:
    """Bảng tóm tắt; mọi dòng ghi rõ đây là mô phỏng và cấu hình tham chiếu là giả định."""
    manifest, rows, summary = data["manifest"], data["rows"], data["summary"]
    variants = manifest["variants"]
    scenes = manifest["scenes"]
    ref = manifest["reference_config"]["config"]
    lines = [
        "# Độ nhạy của bộ lập đường theo kích thước xe — sa bàn cố định (CHỈ MÔ PHỎNG)",
        "",
        f"- Chạy lúc {manifest['started_at']} → {manifest['finished_at']}, máy: {manifest['machine']}; "
        f"{manifest['workers']} tiến trình song song; EcoQoS {_ecoqos_text(manifest)}; ngân sách lập đường "
        f"{manifest['time_limit_s']:g} s/ca"
        + (f", chạy lại ca lật với {manifest['recheck_time_limit_s']:g} s" if manifest["recheck_time_limit_s"] else "")
        + f"; hạt giống RRT {manifest['rrt_seed']}; bộ lập đường `{manifest['planner']}`.",
        f"- Mã nguồn: git `{manifest['git'].get('head', '?')}`"
        + (" (cây làm việc có thay đổi chưa commit)" if manifest["git"].get("dirty") else "") + ".",
        f"- Sa bàn dựng một lần từ `{manifest['reference_config']['path']}` (`{ref['name']}`): dài "
        f"{(ref['rear_overhang_m'] + ref['wheelbase_m'] + ref['front_overhang_m']) * 100:.0f} cm, rộng "
        f"{ref['width_m'] * 100:.0f} cm, L {ref['wheelbase_m'] * 100:.0f} cm, nhô trước/sau "
        f"{ref['front_overhang_m'] * 100:.0f}/{ref['rear_overhang_m'] * 100:.0f} cm, lái {ref['max_steer_deg']:g}°. "
        "Các giá trị này là GIẢ ĐỊNH – CHƯA ĐO, không phải MN300.",
        "- Mọi kết quả là mô phỏng: planner + bộ bám + xe động học lý tưởng. TIMEOUT phụ thuộc tải CPU, không có nghĩa là "
        "vô nghiệm hình học." + (f" Ghi chú lúc chạy: {manifest['note_user']}" if manifest.get("note_user") else ""),
        "",
        "## 1. Xe tham chiếu trên từng sa bàn",
        "",
        "| Sa bàn | Nguồn | Mức | Kỳ vọng | Kết quả | Lập đường (s) | Dài (m) | Đổi chiều | Hở nhỏ nhất (cm) |",
        "|---|---|---|---|---|---:|---:|---:|---:|",
    ]
    by_key = {(r["scene"], r["variant"]): r for r in rows}
    for s in scenes:
        r = by_key.get((s["name"], BASELINE))
        if r is None:
            continue
        lines.append(f"| `{s['name']}` | {s['source']} | {s['difficulty']} | {s['expected']} | {r['verdict']} | "
                     f"{_fmt(r['plan_s'])} | {_fmt(r['length_m'])} | {r['cusps'] if r['cusps'] is not None else '—'} | "
                     f"{_fmt(r['min_clearance_m'], 1, 100)} |")
    lines += [
        "",
        "## 2. Ma trận kết quả",
        "",
        f"{SYMBOL_SOLVED} giải được (đường qua kiểm độc lập và xe mô phỏng bám tới đích), {SYMBOL_TIMEOUT} hết giờ, "
        f"{SYMBOL_FAIL} thất bại khác (NO_PATH, xuất phát/đích chạm, ô nhỏ hơn xe, bám hỏng...). Trong mỗi ô, các mức "
        "xếp từ giảm nhiều nhất tới tăng nhiều nhất, phía giảm và phía tăng cách nhau bằng `/`: với mức 5, 10, 20 % "
        "là `−20 −10 −5 / +5 +10 +20`.",
        "",
    ]
    groups = [g for g in dict.fromkeys(v["group"] for v in variants) if g not in (BASELINE,)]
    header = "| Sa bàn | gốc | " + " | ".join(g if g != "tep" else "tệp" for g in groups) + " |"
    lines += [header, "|---|---|" + "---|" * len(groups)]
    for s in scenes:
        cells = [_symbol(by_key.get((s["name"], BASELINE)))]
        for g in groups:
            members = [v for v in variants if v["group"] == g]
            neg = sorted((v for v in members if v["level_pct"] < 0), key=lambda v: v["level_pct"])
            pos = sorted((v for v in members if v["level_pct"] > 0), key=lambda v: v["level_pct"])
            zero = [v for v in members if v["level_pct"] == 0]
            text = "".join(_symbol(by_key.get((s["name"], v["name"]))) for v in neg)
            text += ("/" if neg and pos else "") + "".join(_symbol(by_key.get((s["name"], v["name"]))) for v in pos)
            text += "".join(_symbol(by_key.get((s["name"], v["name"]))) for v in zero)
            cells.append(f"`{text}`")
        lines.append(f"| `{s['name']}` | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## 3. Theo biến thể",
        "",
        "| Biến thể | Thay đổi | Giải được | Lật OK → hỏng | Trong đó giải được khi chạy lại | Lật hỏng → OK "
        "| Lập đường trung vị / chậm nhất (s, ca giải được) | Hở nhỏ nhất trung vị / nhỏ nhất (cm) | Đổi chiều trung vị |",
        "|---|---|---:|---|---|---|---:|---:|---:|",
    ]
    for pv in summary["per_variant"]:
        change = ", ".join(f"{k} ×{f:.2f}" for k, f in pv["factors"].items()) or (
            "xe tham chiếu" if pv["group"] == BASELINE else f"tệp {pv['source']}")
        lines.append(
            f"| `{pv['variant']}` | {change} | {pv['solved']}/{pv['total']} | "
            f"{', '.join(pv['flips_ok_to_fail']) or '—'} | {', '.join(pv['flips_solved_on_recheck']) or '—'} | "
            f"{', '.join(pv['flips_fail_to_ok']) or '—'} | "
            f"{_fmt(pv['median_plan_s_solved'])} / {_fmt(pv['max_plan_s_solved'])} | "
            f"{_fmt(pv['median_min_clearance_m'], 1, 100)} / {_fmt(pv['min_min_clearance_m'], 1, 100)} | "
            f"{_fmt(pv['median_cusps'], 1)} |")
    th_groups = [g for g in groups if g != "tep"]
    if summary["thresholds"] and th_groups:
        lines += [
            "",
            "## 4. Mức lật đầu tiên (chỉ các sa bàn xe tham chiếu giải được)",
            "",
            "Mỗi ô: mức nhỏ nhất (theo độ lớn) mà từ đó ca không còn giải được, phía tăng và/hoặc phía giảm. `—` = không "
            "lật trong các mức đã chạy. `*` = không đơn điệu: một mức lớn hơn lại giải được (thường do hết giờ).",
            "",
            "| Sa bàn | " + " | ".join(th_groups) + " |",
            "|---|" + "---|" * len(th_groups),
        ]
        for scene, per_group in summary["thresholds"].items():
            lines.append(f"| `{scene}` | " + " | ".join(_threshold_text(per_group.get(g, {})) for g in th_groups) + " |")
    flips = [r for r in rows if r["variant"] != BASELINE and by_key.get((r["scene"], BASELINE), {}).get("solved")
             and not r["solved"]]
    if flips:
        lines += [
            "",
            "## 5. Chi tiết các ca lật OK → hỏng",
            "",
            "| Sa bàn | Biến thể | Kết quả | Xuất phát / đích còn trống | Lý do (rút gọn) | Chạy lại với ngân sách dài hơn |",
            "|---|---|---|---|---|---|",
        ]
        for r in flips:
            recheck = r.get("recheck")
            again = "—" if recheck is None else f"{recheck['time_limit_s']:g} s: {recheck['verdict']}"
            clear = f"{'có' if r['start_clear'] else 'KHÔNG'} / {'có' if r['goal_clear'] else 'KHÔNG'}"
            reason = r["message"].replace("|", "/").replace("\n", " ")[:110]
            lines.append(f"| `{r['scene']}` | `{r['variant']}` | {r['verdict']} | {clear} | {reason} | {again} |")
    if summary["violations"]:
        lines += ["", "## Vi phạm an toàn (planner báo OK nhưng kiểm độc lập không đạt)", ""]
        lines += [f"- `{v}`" for v in summary["violations"]]
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- CLI

def _git_state() -> dict[str, Any]:
    info: dict[str, Any] = {}
    try:
        info["head"] = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT,
                                               timeout=10, stderr=subprocess.DEVNULL).decode().strip()
        status = subprocess.check_output(["git", "status", "--porcelain"], cwd=PROJECT_ROOT, timeout=20,
                                         stderr=subprocess.DEVNULL).decode("utf-8", errors="replace")
        info["dirty"] = bool(status.strip())
    except (OSError, subprocess.SubprocessError) as exc:
        info["error"] = str(exc)
    return info


def _machine() -> str:
    try:
        from autopark.storage.run_store import environment
        env = environment()
        cpu = env.get("hardware", {}).get("cpu") or env.get("cpu")
        cpu = cpu[0] if isinstance(cpu, list) and cpu else cpu
        return f"{cpu} ({env.get('os')})"
    except Exception as exc:  # noqa: BLE001 - chỉ để ghi chú
        return f"không đọc được ({exc!r})"


def _csv(text: str) -> tuple[str, ...]:
    if text.strip().lower() in ("", "none", "khong"):
        return ()
    return tuple(dict.fromkeys(item.strip() for item in text.split(",") if item.strip()))


def _positive_float(text: str) -> float:
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"cần một số, nhận '{text}'") from exc
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError(f"cần số dương hữu hạn, nhận '{text}'")
    return value


def _nonneg_finite_float(text: str) -> float:
    """0 (tắt) hoặc số dương hữu hạn; từ chối nan/inf/số âm trước khi chạy quét (nan lọt qua mọi phép so sánh)."""
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"cần một số, nhận '{text}'") from exc
    if not math.isfinite(value) or value < 0:
        raise argparse.ArgumentTypeError(f"cần 0 (không chạy lại) hoặc số dương hữu hạn, nhận '{text}'")
    return value


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m autopark.evaluation.sensitivity",
        description="Độ nhạy bộ lập đường theo kích thước xe, sa bàn cố định dựng từ cấu hình tham chiếu (mô phỏng).")
    ap.add_argument("--reference-config", type=vehicle_config_arg, default=str(DEFAULT_REFERENCE),
                    help="cấu hình xe dùng để DỰNG sa bàn và làm xe gốc (mặc định configs/vehicle_default.json, GIẢ ĐỊNH)")
    ap.add_argument("--plan-config", type=vehicle_config_arg, action="append", default=[],
                    help="thêm một cấu hình xe từ tệp làm biến thể (ví dụ xe đã đo); lặp lại được")
    ap.add_argument("--params", default=",".join(DEFAULT_PARAMS),
                    help=f"tham số đổi từng cái một, phân cách dấu phẩy; 'none' để bỏ. Có: {', '.join(PARAM_ATTRS)}")
    ap.add_argument("--levels", default=",".join(_level_name(x) for x in DEFAULT_LEVELS),
                    help="các mức %%, mỗi mức chạy cả tăng và giảm (mặc định 5,10,20)")
    ap.add_argument("--combos", default=",".join(DEFAULT_COMBOS),
                    help=f"tổ hợp; 'none' để bỏ. Có: {', '.join(COMBOS)}")
    ap.add_argument("--scenes", default="", help="chỉ chạy các sa bàn này (tên, phân cách dấu phẩy); xem --list")
    ap.add_argument("--no-scenarios", action="store_true", help="bỏ các tệp scenarios/*.json, chỉ chạy bộ ca khó")
    ap.add_argument("--scenario-dir", type=Path, default=DEFAULT_SCENARIO_DIR)
    ap.add_argument("--time-limit", type=_positive_float, default=PlannerParams().time_limit,
                    help="ngân sách lập đường mỗi ca, giây (mặc định bằng PlannerParams().time_limit của ứng dụng)")
    ap.add_argument("--recheck-time-limit", type=_nonneg_finite_float, default=0.0,
                    help="chạy lại các ca lật OK → hỏng với ngân sách này (phải lớn hơn --time-limit; 0 = không)")
    ap.add_argument("--workers", type=int, default=1, help="số tiến trình song song (tranh CPU; ảnh hưởng TIMEOUT)")
    ap.add_argument("--rrt-seed", type=int, default=RRT_DEFAULT_SEED, help="hạt giống RRT (mặc định của planner)")
    ap.add_argument("--planner", default=APP_PLANNER,
                    help="'app' = plan_parking của ứng dụng; hoặc module:ham theo giao diện của bench")
    ap.add_argument("--out", type=Path, default=None, help="thư mục kết quả (mặc định runs/do_nhay_xe/<ngày_giờ>)")
    ap.add_argument("--note", default="", help="ghi chú về điều kiện chạy (tải máy...), chép vào kết quả")
    ap.add_argument("--list", action="store_true", help="in danh sách sa bàn và biến thể rồi thoát")
    return ap


def main(argv: list[str] | None = None) -> int:
    apply_ecoqos_policy("evaluation.sensitivity")      # trước mọi việc khác; tiến trình con: initializer của _execute
    ap = build_parser()
    args = ap.parse_args(argv)
    reference: VehicleConfigFile = args.reference_config
    try:
        levels = tuple(float(x) for x in _csv(args.levels))
    except ValueError:
        ap.error(f"--levels phải là các số phân cách dấu phẩy, nhận '{args.levels}'")
    if any(not math.isfinite(x) or x <= 0 or x >= 100 for x in levels):
        ap.error("--levels: mỗi mức phải trong (0, 100) %")
    params, combos = _csv(args.params), _csv(args.combos)
    try:
        variants = build_variants(reference.cfg, params, levels, combos, tuple(args.plan_config))
    except ValueError as exc:
        ap.error(str(exc))
    if (params or combos) and not levels:
        ap.error("--levels trống nhưng vẫn yêu cầu --params/--combos")
    if args.workers < 1:
        ap.error("--workers phải ≥ 1")
    if args.recheck_time_limit and args.recheck_time_limit <= args.time_limit:
        ap.error("--recheck-time-limit phải lớn hơn --time-limit (hoặc 0 để tắt)")
    try:
        load_planner_spec(args.planner)
    except (ValueError, ImportError, AttributeError) as exc:
        ap.error(f"--planner: {exc}")
    scenario_dir = None if args.no_scenarios else args.scenario_dir
    if scenario_dir is not None and not Path(scenario_dir).is_dir():
        ap.error(f"--scenario-dir: không thấy thư mục '{scenario_dir}'")
    scenes = build_scenes(reference.cfg, scenario_dir)
    wanted = _csv(args.scenes)
    unknown = [n for n in wanted if n not in scenes]
    if unknown:
        ap.error(f"không có sa bàn: {', '.join(unknown)}. Có: {', '.join(scenes)}")
    if wanted:
        scenes = {n: scenes[n] for n in wanted}

    if args.list:
        print("Sa bàn (dựng từ " + str(reference.path) + "):")
        for s in scenes.values():
            print(f"  {s.name:<26} {s.difficulty:<9} {s.expected:<11} {s.source}")
        print(f"Biến thể ({len(variants)}):")
        for v in variants:
            change = ", ".join(f"{a}×{f:.2f}" for a, f in v.factors) or (v.source or "xe tham chiếu")
            print(f"  {v.name:<22} {change}")
        return 0

    out = args.out or DEFAULT_OUT_ROOT / time.strftime("%Y%m%d_%H%M%S")
    if out.exists() and any(out.iterdir()):
        ap.error(f"--out: thư mục '{out}' đã có dữ liệu; chọn thư mục mới để không ghi đè bằng chứng cũ")
    out.mkdir(parents=True, exist_ok=True)

    started = time.strftime("%Y-%m-%d %H:%M:%S")
    total = len(scenes) * len(variants)
    print(f"Sa bàn cố định từ {reference.path.name}: {len(scenes)} sa bàn × {len(variants)} biến thể = {total} lần chạy; "
          f"{args.time_limit:g} s/ca; {args.workers} tiến trình. CHỈ MÔ PHỎNG.", flush=True)

    def progress(done: int, count: int, row: dict[str, Any]) -> None:
        print(f"  [{done:>4}/{count}] {row['scene']:<24} {row['variant']:<18} {row['verdict']:<14} "
              f"{row['plan_s'] or 0:6.2f}s  {row['message'][:60]}", flush=True)

    t0 = time.perf_counter()
    rows = run_sweep(scenes, variants, args.time_limit, recheck_time_limit=args.recheck_time_limit,
                     workers=args.workers, rrt_seed=args.rrt_seed, planner_spec=args.planner, progress=progress)
    manifest = {
        "tool": "autopark.evaluation.sensitivity", "evidence": "simulation_only",
        "note": ("Sa bàn dựng một lần từ cấu hình tham chiếu; chỉ cấu hình lập đường/kiểm va chạm thay đổi. "
                 "Cấu hình tham chiếu mặc định là GIẢ ĐỊNH – CHƯA ĐO. TIMEOUT không có nghĩa là vô nghiệm."),
        "started_at": started, "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_s": round(time.perf_counter() - t0, 2), "machine": _machine(), "git": _git_state(),
        "ecoqos": ecoqos_state(), "ecoqos_rows": dict(Counter(r.get("ecoqos") for r in rows)),
        "argv": list(sys.argv if argv is None else argv), "workers": args.workers,
        "time_limit_s": args.time_limit, "recheck_time_limit_s": args.recheck_time_limit,
        "rrt_seed": args.rrt_seed, "planner": args.planner, "levels_pct": list(levels), "note_user": args.note,
        "reference_config": reference.describe(),
        "scenes": [{"name": s.name, "source": s.source, "difficulty": s.difficulty, "expected": s.expected,
                    "digest": scene_digest(s.scenario), "geometry": scene_geometry(s.scenario)}
                   for s in scenes.values()],
        "variants": [{"name": v.name, "group": v.group, "level_pct": v.level_pct, "factors": dict(v.factors),
                      "source": v.source, "config": v.cfg.to_dict()} for v in variants],
        "source_sha256": {p.relative_to(PROJECT_ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted((PROJECT_ROOT / "autopark").rglob("*.py"))},
    }
    data = {"manifest": manifest, "rows": rows, "summary": summarize(rows, variants)}
    (out / "ket_qua.json").write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False),
                                      encoding="utf-8")
    report = markdown_report(data)
    (out / "bang_do_nhay.md").write_text(report, encoding="utf-8")
    print()
    for pv in data["summary"]["per_variant"]:
        print(f"  {pv['variant']:<22} {pv['solved']:>3}/{pv['total']:<3} lật OK→hỏng: "
              f"{', '.join(pv['flips_ok_to_fail']) or '—'}")
    print(f"\nĐã ghi {out / 'ket_qua.json'} và {out / 'bang_do_nhay.md'}")
    if data["summary"]["violations"]:
        print("VI PHẠM: planner báo OK nhưng kiểm độc lập không đạt:", *data["summary"]["violations"], sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
