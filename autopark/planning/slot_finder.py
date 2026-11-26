"""Tự tìm ô đỗ trên bản đồ lưới LiDAR (thêm 26/11/2026, việc 4: chưa dùng AI, chưa dùng camera).

Đầu vào là bản đồ trạng thái ô (UNKNOWN / FREE / OCCUPIED) cùng `GridSpec`, như `lidar/occupancy.py` hay
`lidar/map_builder.py` dựng ra. Kết quả là danh sách `SlotCandidate`. Mỗi ứng viên là một `ParkingSlot` kèm kiểu đỗ hợp lệ
và số đo khe. Không giới hạn khoảng cách từ xe tới ô.

Hai kiểu khe:

- **Vuông góc** (`perpendicular`): ô dài theo thân xe, có thành ở hai bên và ở đáy, miệng ô mở. Trước miệng phải còn một
  vùng trống dài `approach_m` để xe vào. Đỗ bằng `REVERSE_IN` hoặc `HEAD_IN`. Trục ô (`slot.yaw`) hướng từ miệng vào đáy.
- **Song song** (`parallel`): ô nằm dọc theo một thành (lề). Phía trước và phía sau ô có vật chặn. Phía ngoài ô phải còn
  một làn trống rộng `lane_m`. Đỗ bằng `PARALLEL`.

Cách tìm:

1. Ô bị chặn là mọi ô không FREE, nên UNKNOWN cũng chặn (hợp đồng `Costmap`). Ngoài lưới cũng tính là chặn.
2. Hướng ô thử: hướng chủ đạo của các cạnh vật cản (trung bình vòng của góc gradient, theo mod 90°) và ba hướng vuông
   góc với nó. `SlotParams.yaws_deg` ghi đè danh sách này.
3. Rải tâm ô trên lưới bước `lattice_m`. Lọc nhanh bằng trường khoảng cách tới ô bị chặn: đủ chỗ chứa ô, và gần vật
   cản (khe chứ không phải bãi trống).
4. Từ tâm thử, bắn tia ra bốn cạnh ô để đo khe hở tới thành. Dịch ô vào giữa hai thành bên rồi áp sát đáy (vuông góc),
   hoặc áp sát lề rồi vào giữa hai đầu (song song). Nhiều tâm thử của cùng một khe sẽ hội tụ về một ô.
5. Kiểm lại ô đã dịch bằng lấy mẫu dày (bước nửa ô lưới), kiểm vùng tiếp cận, rồi gộp các ô trùng.

Giới hạn đã biết: lấy mẫu ở bước nửa ô lưới có thể bỏ sót một ô bị chặn chỉ chồng lên ô đỗ dưới nửa ô lưới; lề
`margin_*` phải lớn hơn mức đó. Nên dùng lưới 1–2 cm (bản đồ định vị mặc định 5 cm quá thô cho xe rộng 16 cm). Ô đỗ chỉ
là đề xuất hình học. Xe có vào được hay không do `verify_with_planner` trả lời.

    .venv\\Scripts\\python.exe -X utf8 -m autopark.planning.slot_finder --scenario scenarios\\tim_khe_vuong_goc.json --out <thư mục>
    .venv\\Scripts\\python.exe -X utf8 -m autopark.planning.slot_finder --map <thư mục có costmap.json> --start X Y YAW_ĐỘ --out <thư mục>

Tùy chọn: [--vehicle configs\\vehicle_measured.json] [--resolution 0.02] [--verify] [--time-limit 8] [--max-verify 6].
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field, replace
import json
import math
from pathlib import Path
import time

import cv2
import numpy as np

from autopark.domain.types import (Bounds, ManeuverLimits, ParkingGoal, ParkingMode, ParkingSlot, Pose, Scenario,
                                   VehicleConfig, wrap_angle)
from autopark.perception.costmap import FREE, OCCUPIED, UNKNOWN, GridSpec

PERPENDICULAR = "perpendicular"
PARALLEL = "parallel"
KIND_MODES = {PERPENDICULAR: (ParkingMode.REVERSE_IN, ParkingMode.HEAD_IN), PARALLEL: (ParkingMode.PARALLEL,)}
KIND_LABEL = {PERPENDICULAR: "vuông góc", PARALLEL: "song song"}
# Xe đo thật (26/11/2026): kích thước đo, góc lái và tốc độ còn giả định. Không có tệp thì dùng xe giả định cũ.
_CONFIGS = Path(__file__).resolve().parents[2] / "configs"
DEFAULT_VEHICLE = (_CONFIGS / "vehicle_measured.json" if (_CONFIGS / "vehicle_measured.json").is_file()
                   else _CONFIGS / "vehicle_default.json")


@dataclass(frozen=True)
class SlotParams:
    """Ngưỡng hình học (m). ĐỀ XUẤT – CHỜ CHỐT trên sa bàn thật."""

    margin_side_m: float = 0.03        # lề mỗi bên thân xe trong ô
    margin_end_m: float = 0.03         # lề mỗi đầu xe trong ô
    contact_m: float = 0.08            # khe hở tối đa từ cạnh ô tới thành để coi cạnh đó "có thành"
    max_extra_width_m: float = 0.15    # khe vuông góc rộng hơn ô tối đa ngần này (rộng hơn = bãi trống)
    max_extra_length_m: float = 0.30   # khe song song dài hơn ô tối đa ngần này
    approach_m: float | None = None    # vùng trống trước miệng ô vuông góc; None = chiều dài xe
    lane_m: float | None = None        # làn trống bên ngoài ô song song; None = 1,5 × bề rộng xe
    probe_m: float = 0.6               # tầm bắn tia đo khe hở
    lattice_m: float = 0.02            # bước rải tâm thử
    side_hit_ratio: float = 0.6        # tỷ lệ tia phải chạm thành để một cạnh dài "có thành"
    end_hit_ratio: float = 0.4         # như trên cho cạnh ngắn (vật chặn đầu/cuối có thể hẹp hơn ô)
    rays_per_side: int = 5
    merge_m: float = 0.08              # hai ô cùng kiểu, cùng hướng, tâm gần hơn ngần này: gộp
    yaws_deg: tuple[float, ...] | None = None

    def approach(self, cfg: VehicleConfig) -> float:
        return self.approach_m if self.approach_m is not None else cfg.length

    def lane(self, cfg: VehicleConfig) -> float:
        return self.lane_m if self.lane_m is not None else 1.5 * cfg.width


@dataclass
class SlotCandidate:
    kind: str
    slot: ParkingSlot
    modes: tuple[ParkingMode, ...]
    slack_width_m: float               # khe rộng hơn ô (vuông góc) hoặc ...
    slack_length_m: float              # ... dài hơn ô (song song); phần kia = 0
    boundary_unknown: bool             # có thành chỉ là ô UNKNOWN (chưa thấy vật thật)
    kerb_side: str | None = None       # song song: "left"/"right" theo trục ô
    distance_m: float | None = None    # từ tâm trục sau của xe tới tư thế đích gần nhất, khi biết tư thế xe
    verify: dict = field(default_factory=dict)   # kiểu đỗ → kết quả lập quỹ đạo

    def goal_pose(self, cfg: VehicleConfig, mode: ParkingMode, reference_yaw: float | None = None) -> Pose:
        return self.slot.goal_pose(cfg, mode, reference_yaw)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "slot": self.slot.to_dict(), "modes": [m.value for m in self.modes],
                "slack_width_m": round(self.slack_width_m, 4), "slack_length_m": round(self.slack_length_m, 4),
                "boundary_unknown": self.boundary_unknown, "kerb_side": self.kerb_side,
                "distance_m": None if self.distance_m is None else round(self.distance_m, 4),
                "verify": self.verify}


# ------------------------------------------------------------------------------------------------ hình học trên lưới
class _Grid:
    def __init__(self, states: np.ndarray, grid: GridSpec):
        states = np.asarray(states)
        if states.shape != grid.shape:
            raise ValueError(f"lưới trạng thái {states.shape} không khớp GridSpec {grid.shape}")
        self.states, self.grid, self.res = states, grid, grid.resolution
        self.blocked = states != FREE
        free = np.where(self.blocked, 0, 255).astype(np.uint8)
        self.clear = cv2.distanceTransform(free, cv2.DIST_L2, cv2.DIST_MASK_PRECISE).astype(np.float64) * self.res

    def cells(self, x, y):
        g = self.grid
        r = np.floor((np.asarray(y) - g.y_min) / g.resolution).astype(np.int64)
        c = np.floor((np.asarray(x) - g.x_min) / g.resolution).astype(np.int64)
        rows, cols = g.shape
        inside = (r >= 0) & (r < rows) & (c >= 0) & (c < cols)
        return np.clip(r, 0, rows - 1), np.clip(c, 0, cols - 1), inside

    def is_blocked(self, x, y) -> np.ndarray:
        r, c, inside = self.cells(x, y)
        return ~inside | self.blocked[r, c]

    def state(self, x, y) -> np.ndarray:
        r, c, inside = self.cells(x, y)
        return np.where(inside, self.states[r, c], UNKNOWN)

    def clearance(self, x, y) -> np.ndarray:
        r, c, inside = self.cells(x, y)
        return np.where(inside, self.clear[r, c], 0.0)

    def rect_free(self, cx: float, cy: float, yaw: float, length: float, width: float) -> bool:
        """Lấy mẫu dày (bước nửa ô) cả cạnh lẫn lòng hình chữ nhật: không mẫu nào rơi vào ô bị chặn."""
        step = self.res / 2
        u = np.linspace(-length / 2, length / 2, max(2, int(math.ceil(length / step)) + 1))
        v = np.linspace(-width / 2, width / 2, max(2, int(math.ceil(width / step)) + 1))
        uu, vv = np.meshgrid(u, v)
        c, s = math.cos(yaw), math.sin(yaw)
        return not self.is_blocked(cx + c * uu - s * vv, cy + s * uu + c * vv).any()

    def coarse_free(self, cx: float, cy: float, yaw: float, length: float, width: float) -> bool:
        """Lọc nhanh (gần đúng, có thể lọt): lấy mẫu thưa bước một ô lưới trong lòng hình chữ nhật."""
        u = np.linspace(-length / 2, length / 2, max(2, int(math.ceil(length / self.res)) + 1))
        v = np.linspace(-width / 2, width / 2, max(2, int(math.ceil(width / self.res)) + 1))
        uu, vv = np.meshgrid(u, v)
        c, s = math.cos(yaw), math.sin(yaw)
        return not self.is_blocked(cx + c * uu - s * vv, cy + s * uu + c * vv).any()

    def side_gaps(self, cx, cy, yaw, length, width, probe, rays):
        """Khe hở từ mỗi cạnh ra tới ô bị chặn đầu tiên, theo pháp tuyến ngoài.

        Trả dict cạnh → (mảng khe hở từng tia, inf nếu không chạm trong `probe`; mảng: ô chạm là UNKNOWN). Cạnh theo
        trục ô: "front" (+x), "back" (−x), "left" (+y), "right" (−y)."""
        c, s = math.cos(yaw), math.sin(yaw)
        ex, ey = np.array([c, s]), np.array([-s, c])
        step = self.res / 2
        d = np.arange(0.0, probe + 1e-9, step)
        out = {}
        for name, n, t, half_n, half_t in (("front", ex, ey, length / 2, width / 2), ("back", -ex, ey, length / 2, width / 2),
                                           ("left", ey, ex, width / 2, length / 2), ("right", -ey, ex, width / 2, length / 2)):
            inset = min(self.res, half_t / 2)
            offs = np.linspace(-half_t + inset, half_t - inset, rays)
            base = np.array([cx, cy]) + half_n * n
            px = base[0] + offs[:, None] * t[0] + (d[None, :] + step / 2) * n[0]
            py = base[1] + offs[:, None] * t[1] + (d[None, :] + step / 2) * n[1]
            st = self.state(px, py)                       # ngoài lưới = UNKNOWN, nên "chặn" = không FREE
            hit = st != FREE
            any_hit = hit.any(axis=1)
            first = hit.argmax(axis=1)
            gaps = np.where(any_hit, d[first], np.inf)
            unknown = any_hit & (st[np.arange(rays), first] == UNKNOWN)
            out[name] = (gaps, unknown)
        return out


def dominant_yaw(states: np.ndarray, grid: GridSpec) -> float:
    """Hướng chủ đạo của cạnh vật cản (rad, trong [0, π/2)), theo hệ lưới: trung bình vòng của 4·góc gradient."""
    occ = (np.asarray(states) == OCCUPIED).astype(np.float32)
    gx = cv2.Sobel(occ, cv2.CV_32F, 1, 0, ksize=3)      # theo cột = trục x
    gy = cv2.Sobel(occ, cv2.CV_32F, 0, 1, ksize=3)      # theo hàng = trục y
    w = np.hypot(gx, gy)
    if not (w > 0).any():
        return 0.0
    a = np.arctan2(gy, gx)
    theta = math.atan2(float((w * np.sin(4 * a)).sum()), float((w * np.cos(4 * a)).sum())) / 4
    return theta % (math.pi / 2)


# ------------------------------------------------------------------------------------------------------- tìm ô đỗ
def _slack(gaps: np.ndarray) -> float:
    return float(np.min(gaps))


def _hits(gaps: np.ndarray, limit: float) -> float:
    return float(np.mean(gaps <= limit + 1e-9))


def find_slots(states: np.ndarray, grid: GridSpec, cfg: VehicleConfig, params: SlotParams | None = None, *,
               kinds: tuple[str, ...] = (PERPENDICULAR, PARALLEL), vehicle_pose: Pose | None = None) -> list[SlotCandidate]:
    """Mọi khe tìm được trên bản đồ. Có `vehicle_pose` thì xếp theo khoảng cách tới xe, không thì theo độ rộng rãi."""
    p = params or SlotParams()
    g = _Grid(states, grid)
    L = cfg.length + 2 * p.margin_end_m
    W = cfg.width + 2 * p.margin_side_m
    if p.yaws_deg is not None:
        yaws = [math.radians(a) for a in p.yaws_deg]
    else:
        base = dominant_yaw(states, grid)
        yaws = [wrap_angle(base + k * math.pi / 2) for k in range(4)]

    gx, gy = np.meshgrid(np.arange(grid.x_min + p.lattice_m / 2, grid.x_max, p.lattice_m),
                         np.arange(grid.y_min + p.lattice_m / 2, grid.y_max, p.lattice_m))
    gx, gy = gx.ravel(), gy.ravel()
    clear = g.clearance(gx, gy)
    # Tâm thử nằm trong ô đã khớp khe: vuông góc thì cách thành bên gần nhất ≤ (W + dư)/2; song song thì cách lề ≤ W.
    near_limit = max(W / 2 + p.max_extra_width_m, W) + p.contact_m + g.res
    keep = (clear >= W / 2 - g.res / 2) & (clear <= near_limit)
    seeds = list(zip(gx[keep], gy[keep]))

    found: list[SlotCandidate] = []
    seen: set = set()
    for yaw in yaws:
        c, s = math.cos(yaw), math.sin(yaw)
        ex, ey = np.array([c, s]), np.array([-s, c])
        for sx, sy in seeds:
            if not g.coarse_free(sx, sy, yaw, L, W):
                continue
            gaps = g.side_gaps(sx, sy, yaw, L, W, p.probe_m, p.rays_per_side)
            for kind in kinds:
                key0 = (kind, round(sx / g.res), round(sy / g.res), round(math.degrees(yaw)))
                if key0 in seen:
                    continue
                cand = (_perpendicular if kind == PERPENDICULAR else _parallel)(g, p, cfg, sx, sy, yaw, ex, ey, L, W, gaps)
                if cand is None:
                    continue
                key = (kind, round(cand.slot.cx / g.res), round(cand.slot.cy / g.res),
                       round(math.degrees(cand.slot.yaw if kind == PERPENDICULAR else cand.slot.yaw % math.pi)))
                if key in seen:
                    continue
                seen.add(key)
                found.append(cand)
    found = _merge(found, p.merge_m)
    if vehicle_pose is not None:
        for cand in found:
            cand.distance_m = min(vehicle_pose.distance_to(cand.goal_pose(cfg, m, vehicle_pose.yaw)) for m in cand.modes)
        found.sort(key=lambda k: (k.boundary_unknown, k.distance_m))
    else:
        found.sort(key=lambda k: (k.boundary_unknown, -(k.slack_width_m + k.slack_length_m)))
    return found


def _perpendicular(g: _Grid, p: SlotParams, cfg, sx, sy, yaw, ex, ey, L, W, gaps) -> SlotCandidate | None:
    gl, gr, gf = _slack(gaps["left"][0]), _slack(gaps["right"][0]), _slack(gaps["front"][0])
    if not (math.isfinite(gl) and math.isfinite(gr) and math.isfinite(gf)):
        return None
    if gl + gr > p.max_extra_width_m + 2 * g.res:
        return None
    shift = ((gl - gr) / 2) * ey + max(0.0, gf - g.res / 2) * ex      # vào giữa hai thành, áp sát đáy (+x)
    cx, cy = sx + shift[0], sy + shift[1]
    if not g.rect_free(cx, cy, yaw, L, W):
        return None
    gaps = g.side_gaps(cx, cy, yaw, L, W, p.probe_m, p.rays_per_side)
    gl, gr = _slack(gaps["left"][0]), _slack(gaps["right"][0])
    if not (math.isfinite(gl) and math.isfinite(gr)) or gl + gr > p.max_extra_width_m + 2 * g.res:
        return None
    half_extra = (gl + gr) / 2
    if _hits(gaps["left"][0], half_extra + p.contact_m) < p.side_hit_ratio:
        return None
    if _hits(gaps["right"][0], half_extra + p.contact_m) < p.side_hit_ratio:
        return None
    if _hits(gaps["front"][0], p.contact_m) < p.end_hit_ratio:
        return None
    # miệng ô (−x) mở: vùng tiếp cận trước miệng trống, và miệng không bị thành chắn
    a = p.approach(cfg)
    mouth = np.array([cx, cy]) - (L / 2 + a / 2) * ex
    if not g.rect_free(mouth[0], mouth[1], yaw, a, W):
        return None
    unknown = any(bool(gaps[k][1][gaps[k][0] <= half_extra + p.contact_m].any()) for k in ("left", "right", "front"))
    return SlotCandidate(PERPENDICULAR, ParkingSlot(cx, cy, wrap_angle(yaw), L, W), KIND_MODES[PERPENDICULAR],
                         slack_width_m=gl + gr, slack_length_m=0.0, boundary_unknown=unknown)


def _parallel(g: _Grid, p: SlotParams, cfg, sx, sy, yaw, ex, ey, L, W, gaps) -> SlotCandidate | None:
    gl, gr = _slack(gaps["left"][0]), _slack(gaps["right"][0])
    kerb = "left" if gl <= gr else "right"
    gk = min(gl, gr)
    if not math.isfinite(gk):
        return None
    normal = ey if kerb == "left" else -ey
    gf, gb = _slack(gaps["front"][0]), _slack(gaps["back"][0])
    if not (math.isfinite(gf) and math.isfinite(gb)) or gf + gb > p.max_extra_length_m + 2 * g.res:
        return None
    shift = max(0.0, gk - g.res / 2) * normal + ((gf - gb) / 2) * ex  # áp sát lề, vào giữa hai đầu
    cx, cy = sx + shift[0], sy + shift[1]
    if not g.rect_free(cx, cy, yaw, L, W):
        return None
    gaps = g.side_gaps(cx, cy, yaw, L, W, p.probe_m, p.rays_per_side)
    gf, gb = _slack(gaps["front"][0]), _slack(gaps["back"][0])
    if not (math.isfinite(gf) and math.isfinite(gb)) or gf + gb > p.max_extra_length_m + 2 * g.res:
        return None
    half_extra = (gf + gb) / 2
    if _hits(gaps[kerb][0], p.contact_m) < p.side_hit_ratio:
        return None
    if _hits(gaps["front"][0], half_extra + p.contact_m) < p.end_hit_ratio:
        return None
    if _hits(gaps["back"][0], half_extra + p.contact_m) < p.end_hit_ratio:
        return None
    lane = p.lane(cfg)
    centre = np.array([cx, cy]) - (W / 2 + lane / 2) * normal
    if not g.rect_free(centre[0], centre[1], yaw, L, lane):
        return None
    unknown = any(bool(gaps[k][1][gaps[k][0] <= half_extra + p.contact_m].any()) for k in (kerb, "front", "back"))
    return SlotCandidate(PARALLEL, ParkingSlot(cx, cy, wrap_angle(yaw), L, W), KIND_MODES[PARALLEL],
                         slack_width_m=0.0, slack_length_m=gf + gb, boundary_unknown=unknown, kerb_side=kerb)


def _merge(cands: list[SlotCandidate], radius: float) -> list[SlotCandidate]:
    out: list[SlotCandidate] = []
    for cand in sorted(cands, key=lambda k: -(k.slack_width_m + k.slack_length_m)):
        period = 2 * math.pi if cand.kind == PERPENDICULAR else math.pi
        dup = False
        for other in out:
            dyaw = abs((cand.slot.yaw - other.slot.yaw + period / 2) % period - period / 2)
            if other.kind == cand.kind and dyaw < math.radians(10) and \
                    math.hypot(cand.slot.cx - other.slot.cx, cand.slot.cy - other.slot.cy) < radius:
                dup = True
                break
        if not dup:
            out.append(cand)
    return out


# ---------------------------------------------------------------------------------------------- kiểm bằng planner
def clear_vehicle(states: np.ndarray, grid: GridSpec, cfg: VehicleConfig, pose: Pose, margin: float = 0.02) -> np.ndarray:
    """Bản sao bản đồ với chỗ xe đang đứng đặt FREE: LiDAR không thấy dưới thân xe, nên ô đó UNKNOWN và chặn xuất phát."""
    out = np.array(states, copy=True)
    gx, gy = grid.centers()
    c, s = math.cos(pose.yaw), math.sin(pose.yaw)
    dx, dy = gx - pose.x, gy - pose.y
    u, v = c * dx + s * dy, -s * dx + c * dy
    body = ((u >= -cfg.rear_overhang - margin) & (u <= cfg.wheelbase + cfg.front_overhang + margin)
            & (np.abs(v) <= cfg.width / 2 + margin))
    out[body & (out == UNKNOWN)] = FREE
    return out


def wide_limits(bounds: Bounds, max_cusps: int = 6) -> ManeuverLimits:
    """Giới hạn thao tác cho đích là ô đỗ tìm được: nới theo cỡ sa bàn, bỏ mức 0,7 m của thao tác gần."""
    diag = math.hypot(bounds.width, bounds.height)
    return ManeuverLimits(max_goal_distance_m=diag, area_half_extent_m=diag, max_path_length_m=3 * diag,
                          max_cusps=max_cusps)


def map_obstacles(states: np.ndarray, grid: GridSpec, cfg: VehicleConfig, start: Pose) -> list:
    """Vật cản cho bộ lập quỹ đạo từ bản đồ: ô OCCUPIED và UNKNOWN đều chặn, trừ chỗ xe đang đứng."""
    from autopark.domain.sensors import SourceStamp
    from autopark.fusion.obstacles import costmap_to_obstacles
    from autopark.perception.costmap import to_costmap

    cleared = clear_vehicle(states, grid, cfg, start)
    costmap = to_costmap(cleared, grid, SourceStamp("slot_finder", 0.0, True, "map"))
    return costmap_to_obstacles(costmap, include_unknown=True, prefix="ban_do")


def slot_scenario(cand: SlotCandidate, mode: ParkingMode, cfg: VehicleConfig, start: Pose, obstacles: list,
                  bounds: Bounds, *, name: str = "slot_finder", goal_template: ParkingGoal | None = None) -> Scenario:
    """Sa bàn một lần đỗ vào ô `cand`: đích theo kiểu đỗ, giới hạn thao tác nới theo cỡ sa bàn (không có mức 0,7 m)."""
    goal = cand.goal_pose(cfg, mode, start.yaw)
    template = goal_template or ParkingGoal(goal)
    return Scenario(name=name, bounds=bounds, start=start,
                    goal=ParkingGoal(goal, template.tolerance_xy, template.tolerance_yaw),
                    obstacles=list(obstacles), maneuver=wide_limits(bounds))


def plan_to_slot(cand: SlotCandidate, mode: ParkingMode, cfg: VehicleConfig, start: Pose, obstacles: list,
                 bounds: Bounds, *, time_limit: float = 8.0, goal_template: ParkingGoal | None = None):
    """Lập quỹ đạo từ `start` vào ô theo kiểu đỗ `mode`, trên vật cản `obstacles`. Trả (sa bàn đã dùng, PlanResult)."""
    from autopark.planning.maneuver_planner import plan_maneuver
    from autopark.planning.types import PlannerParams

    scenario = slot_scenario(cand, mode, cfg, start, obstacles, bounds, goal_template=goal_template)
    return scenario, plan_maneuver(scenario, cfg, PlannerParams(time_limit=time_limit))


def plan_entry(goal: Pose, result, elapsed: float) -> dict:
    entry = {"status": result.status, "message": result.message, "elapsed_s": round(elapsed, 2),
             "goal": {"x": round(goal.x, 4), "y": round(goal.y, 4), "yaw_deg": round(math.degrees(goal.yaw), 2)}}
    if result.ok and result.trajectory is not None:
        entry["path_length_m"] = round(float(result.trajectory.length), 3)
        entry["cusps"] = int(result.trajectory.n_cusps)
    return entry


def verify_with_planner(cands: list[SlotCandidate], states: np.ndarray, grid: GridSpec, cfg: VehicleConfig,
                        start: Pose, *, time_limit: float = 8.0, max_candidates: int = 6,
                        bounds: Bounds | None = None) -> list[SlotCandidate]:
    """Lập quỹ đạo từ `start` tới từng kiểu đỗ của `max_candidates` ứng viên đầu. Ghi kết quả vào `cand.verify`.

    Không giới hạn khoảng cách tới ô: giới hạn thao tác nới theo cỡ bản đồ thay cho mặc định 0,7 m của thao tác gần."""
    obstacles = map_obstacles(states, grid, cfg, start)
    bounds = bounds or Bounds(grid.x_min, grid.y_min, grid.x_max, grid.y_max)
    for cand in cands[:max_candidates]:
        for mode in cand.modes:
            t0 = time.perf_counter()
            scenario, result = plan_to_slot(cand, mode, cfg, start, obstacles, bounds, time_limit=time_limit)
            cand.verify[mode.value] = plan_entry(scenario.goal.pose, result, time.perf_counter() - t0)
    return cands


# ------------------------------------------------------------------------------------------------------ bản đồ, vẽ
def sim_map(scenario: Scenario, *, resolution: float = 0.02, seed: int = 0, config=None) -> tuple[np.ndarray, GridSpec]:
    """Bản đồ LiDAR MÔ PHỎNG của một sa bàn: LiDAR ảo đặt ở điểm xuất phát và các điểm lưới 3 × 3 còn trống."""
    from autopark.application.lidar_pose_source import _free_spot
    from autopark.lidar.occupancy import OccupancyCounts
    from autopark.lidar.pose_config import load_lidar_pose_config
    from autopark.lidar.synthetic import raycast, scenario_segments
    from autopark.domain.sensors import LidarScan, SourceStamp

    config = config or load_lidar_pose_config()
    sim = config.sim
    rng = np.random.default_rng(seed)
    b = scenario.bounds
    spots = []
    if _free_spot(scenario, scenario.start.x, scenario.start.y, 0.05):
        spots.append((scenario.start.x, scenario.start.y, scenario.start.yaw))
    for fy in (0.5, 0.25, 0.75):
        for fx in (0.5, 0.25, 0.75):
            x, y = b.xmin + fx * b.width, b.ymin + fy * b.height
            if _free_spot(scenario, x, y, 0.12):
                spots.append((x, y, 0.3 * len(spots)))
    segments = scenario_segments(scenario, walls_from_bounds=sim.walls_from_bounds, room_margin_m=sim.room_margin_m)
    pad = 2 * resolution
    grid = GridSpec(round(b.xmin - pad, 6), round(b.xmax + pad, 6), round(b.ymin - pad, 6), round(b.ymax + pad, 6),
                    resolution)
    counts = OccupancyCounts(grid)
    for spot in spots:
        for _ in range(sim.map_scans_per_placement):
            angles, ranges = raycast(spot, segments, beams=sim.beams, fov_rad=math.radians(sim.fov_deg),
                                     max_range_m=sim.max_range_m, min_range_m=sim.min_range_m, noise_m=sim.noise_m,
                                     dropout=sim.dropout, rng=rng)
            scan = LidarScan(SourceStamp("lidar_sim", 0.0, True, "sa_ban"), tuple(angles), tuple(ranges))
            counts.add_scan(scan, spot, max_range=sim.max_range_m, min_range=sim.min_range_m)
    return counts.states(), grid


def render_slots(states: np.ndarray, grid: GridSpec, cands: list[SlotCandidate], cfg: VehicleConfig,
                 start: Pose | None = None, scale: int = 4) -> np.ndarray:
    """Ảnh nhìn từ trên (x sang phải, y lên trên): bản đồ, ô đỗ đánh số, mũi tên hướng xe ở đích, xe xuất phát."""
    colors = {UNKNOWN: (110, 110, 110), FREE: (235, 235, 235), OCCUPIED: (40, 40, 40)}
    rows, cols = states.shape
    img = np.zeros((rows, cols, 3), np.uint8)
    for value, color in colors.items():
        img[states == value] = color
    img = cv2.resize(img[::-1], (cols * scale, rows * scale), interpolation=cv2.INTER_NEAREST)

    def px(x, y):
        return (int(round((x - grid.x_min) / grid.resolution * scale)),
                int(round((grid.y_max - y) / grid.resolution * scale)))

    def poly(points, color, thick=2):
        cv2.polylines(img, [np.array([px(*q) for q in points], np.int32)], True, color, thick, cv2.LINE_AA)

    def arrow(pose: Pose, color):
        tip = (pose.x + 0.08 * math.cos(pose.yaw), pose.y + 0.08 * math.sin(pose.yaw))
        cv2.arrowedLine(img, px(pose.x, pose.y), px(*tip), color, 2, cv2.LINE_AA, tipLength=0.35)

    for i, cand in enumerate(cands, 1):
        ok = any(v.get("status") == "OK" for v in cand.verify.values())
        tried = bool(cand.verify)
        color = (0, 160, 0) if ok else ((0, 0, 220) if tried else (220, 120, 0))
        poly(cand.slot.corners(), color)
        mode = cand.modes[0]
        arrow(cand.goal_pose(cfg, mode, start.yaw if start else None), color)
        cv2.putText(img, str(i), px(cand.slot.cx, cand.slot.cy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2, cv2.LINE_AA)
    if start is not None:
        from autopark.geometry.footprint import body_polygon
        poly(list(body_polygon(cfg, start).exterior.coords)[:-1], (200, 0, 200))
        arrow(start, (200, 0, 200))
    return img


# --------------------------------------------------------------------------------------------------------- dòng lệnh
def _load_map(path: Path) -> tuple[np.ndarray, GridSpec]:
    from autopark.lidar.localize import load_map
    lmap = load_map(path)
    return lmap.states, lmap.grid


def main(argv=None) -> int:
    from autopark.domain.types import VehicleConfig as VC
    from autopark.image_io import imwrite
    from autopark.perception.paths import atomic_write_json, utc_now
    from autopark.storage.scenario_store import load_scenario

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--scenario", type=Path, help="sa bàn JSON: dựng bản đồ bằng LiDAR MÔ PHỎNG")
    src.add_argument("--map", type=Path, help="costmap.json (lidar/occupancy.py, lidar/map_builder.py) hoặc thư mục chứa nó")
    ap.add_argument("--start", type=float, nargs=3, metavar=("X", "Y", "YAW_DEG"), help="tư thế xe (tâm trục sau)")
    ap.add_argument("--vehicle", type=Path, default=None, help="cấu hình xe; mặc định theo sa bàn hoặc configs/vehicle_measured.json")
    ap.add_argument("--resolution", type=float, default=0.02, help="ô lưới khi dựng bản đồ mô phỏng (m)")
    ap.add_argument("--verify", action="store_true", help="lập quỹ đạo tới từng ô để kiểm xe vào được")
    ap.add_argument("--time-limit", type=float, default=8.0)
    ap.add_argument("--max-verify", type=int, default=6)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)

    root = Path(__file__).resolve().parents[2]
    start = Pose(a.start[0], a.start[1], math.radians(a.start[2])) if a.start else None
    if a.scenario:
        scenario = load_scenario(a.scenario)
        cfg_path = a.vehicle or scenario.vehicle_config_path or DEFAULT_VEHICLE
        states, grid = sim_map(scenario, resolution=a.resolution)
        start = start or scenario.start
        source = f"LiDAR mô phỏng từ {a.scenario}"
    else:
        cfg_path = a.vehicle or DEFAULT_VEHICLE
        states, grid = _load_map(a.map)
        source = f"bản đồ {a.map}"
    cfg = VC.from_dict(json.loads(Path(cfg_path).read_text(encoding="utf-8")))

    t0 = time.perf_counter()
    cands = find_slots(states, grid, cfg, vehicle_pose=start)
    t_find = time.perf_counter() - t0
    if a.verify:
        if start is None:
            ap.error("--verify cần --start (hoặc --scenario)")
        verify_with_planner(cands, states, grid, cfg, start, time_limit=a.time_limit, max_candidates=a.max_verify)

    a.out.mkdir(parents=True, exist_ok=True)
    atomic_write_json(a.out / "o_do.json", {
        "created_utc": utc_now(), "source": source, "vehicle_config": str(cfg_path), "grid": asdict(grid),
        "start": None if start is None else start.to_dict(), "params": asdict(SlotParams()),
        "find_seconds": round(t_find, 2), "candidates": [c.to_dict() for c in cands]})
    imwrite(a.out / "o_do.png", render_slots(states, grid, cands, cfg, start))
    print(f"{len(cands)} ô đỗ ({t_find:.1f} s) · {source}")
    for i, cand in enumerate(cands, 1):
        sl = cand.slot
        extra = cand.slack_width_m if cand.kind == PERPENDICULAR else cand.slack_length_m
        line = (f"  {i}. {KIND_LABEL[cand.kind]:<9} tâm ({sl.cx:.3f}, {sl.cy:.3f}) hướng {math.degrees(sl.yaw):6.1f}° "
                f"dư {extra * 100:4.1f} cm")
        if cand.distance_m is not None:
            line += f" · cách xe {cand.distance_m:.2f} m"
        if cand.boundary_unknown:
            line += " · thành chưa thấy rõ"
        for mode, v in cand.verify.items():
            line += f" · {mode}: {v['status']}"
        print(line)
    print(f"Đã ghi {a.out / 'o_do.json'} và {a.out / 'o_do.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
