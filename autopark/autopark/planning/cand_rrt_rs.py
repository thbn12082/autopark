"""Ứng viên: RRT-Connect hai chiều với hàm lái cục bộ là Reeds-Shepp đầy đủ.

Vì sao chọn cách này: Hybrid A* chết ở các ca chật KHÔNG phải vì chậm mà vì lưới
(5 cm x 10 độ) không biểu diễn nổi nhịp đẩy tới-lui — mỗi vòng đẩy chỉ dịch ngang
2-3 cm nên rơi vào đúng ô lưới cũ và bị tập đóng loại. RRT không có lưới, không có
tập đóng, nên không có giới hạn biểu diễn đó. Thêm nữa, MỘT cạnh Reeds-Shepp đã
chứa sẵn tới 4 lần đổi chiều, đúng thứ mà chỗ chật cần.

Kiến trúc
---------
1. Hai cây: cây A mọc từ xuất phát, cây B mọc từ đích. Mỗi cạnh là đoạn đầu (prefix)
   không va chạm của một đường Reeds-Shepp ĐẦY ĐỦ 48 họ (`cand_rrt_rs_full`).
2. Khoảng cách để tìm nút gần nhất là ĐỘ DÀI REEDS-SHEPP (không phải Euclid). Lọc
   thô bằng Euclid — vốn là cận dưới đúng của độ dài RS — rồi tính RS chính xác cho
   các ứng viên gần nhất, dừng sớm khi cận dưới đã vượt kỷ lục.
3. Va chạm trong vòng tìm kiếm: `FastCollisionChecker` giải tích, lấy mẫu 2 cm dọc
   cung. Đường cuối cùng vẫn phải qua `check_motion` của Shapely với thân xe THẬT.
4. Rút gọn ngẫu nhiên (shortcut): nối trực tiếp hai điểm xa nhau trên đường bằng RS,
   chấm bằng `độ dài + phạt đổi chiều + phạt nhịp ngắn`. Bắt buộc phải có: không có
   nó, đường RRT ngoằn ngoèo và có hàng chục lần đổi chiều thừa.
5. NGHIỆM THU BẰNG MÔ PHỎNG BÁM ĐƯỜNG. Bài học đo được: `TrajectoryTracker` dừng khi
   còn `stop_distance` = 1 cm tới cuối mỗi đoạn, nên một nhịp dài 1,5 cm gần như
   không được thực hiện; sai số dồn lại rồi xe đâm. Nhưng một ngưỡng "nhịp tối thiểu"
   cứng lại làm nhiều ca đỗ song song thành vô nghiệm (nhịp cuối vào ô 1,6× thân xe
   chỉ dài được 6 cm mà vẫn bám tốt). Nên thay vì đoán, ứng viên này chạy chính bộ
   bám + mô hình xe (`TrajectoryTracker` + `SimVehicle`, cùng dt và nhịp điều khiển
   với `simulation.rollout`) ngay trong lúc lập đường, và chỉ nhận đường nào xe thật
   sự bám tới đích trong dung sai mà không va chạm. Không tìm được đường như vậy thì
   quay lại mọc cây tiếp.

Hạt giống ngẫu nhiên cố định (`RRTParams.seed`, mặc định 20260907) nên kết quả lặp
lại được; đổi bằng biến môi trường `AUTOPARK_RRT_SEED` hoặc tham số.

Chỉ dùng, không sửa: hybrid_astar.PlanResult, trajectory.build_trajectory,
footprint.check_pose/check_motion, geometry.fast_collision.FastCollisionChecker,
control.tracker.TrajectoryTracker, simulation.vehicle.SimVehicle.
"""
from __future__ import annotations

import math
import os
import random
import time
from dataclasses import dataclass

from autopark.domain.computation import checkpoint
from autopark.planning.computation import controlled_plan
import numpy as np

from autopark.control.tracker import TrajectoryTracker
from autopark.domain.types import Bounds, Obstacle, Pose, VehicleConfig, VehicleState
from autopark.geometry.fast_collision import FastCollisionChecker
from autopark.geometry.footprint import check_motion, check_pose
from autopark.planning.cand_rrt_rs_full import TINY as _TINY
from autopark.planning.cand_rrt_rs_full import interp as _interp
from autopark.planning.cand_rrt_rs_full import min_length, sorted_words, wrap
from autopark.planning.hybrid_astar import PlanResult
from autopark.planning.trajectory import Trajectory, build_trajectory
from autopark.simulation.vehicle import SimVehicle

DEFAULT_SEED = 20260907
_ROOT = 9        # "chiều" đặc biệt cho gốc cây: phía trước chưa có nhịp nào


@dataclass
class RRTParams:
    seed: int = DEFAULT_SEED
    time_limit: float = 20.0

    # --- xe / an toàn (giữ đúng mức của hybrid_astar.py, không nới lỏng)
    steer_ratio: float = 0.85
    safety_margin: float = 0.03

    # --- lịch "epoch": (nhịp cùng chiều tối thiểu, phần thời gian). Xem plan().
    epochs: tuple = ((0.000, 0.06), (0.025, 0.09), (0.000, 0.35),
                     (0.025, 0.10), (0.000, 0.40))
    # --- và ngưỡng MỀM dùng khi chấm điểm lúc rút gọn / chọn từ RS
    soft_run: float = 0.16
    word_run_penalty: float = 1.80     # ưu tiên mềm cho từ RS có nhịp dài

    # --- lấy mẫu
    goal_bias: float = 0.10
    start_bias: float = 0.05
    node_bias: float = 0.20
    bias_sigma_xy: float = 0.22
    bias_sigma_yaw: float = 0.70
    sample_tries: int = 24

    # --- mở rộng cây
    max_extend: float = 0.55
    connect_extend: float = 1.30
    connect_iters: int = 6
    nn_k: int = 12
    steer_candidates: int = 4
    rs_step: float = 0.02

    # --- rút gọn
    cusp_weight: float = 0.35
    short_run_penalty: float = 2.50
    smooth_budget: float = 0.20        # s cho mỗi lượt rút gọn một ứng viên
    shortcut_min_span: float = 0.06
    pool_size: int = 6                 # số đường thô giữ lại để gọt dần
    grow_slice: float = 0.30           # s mọc cây mỗi vòng ngoài
    max_track_time: float = 225.0      # ước lượng thời gian bám; quá thì bỏ ứng viên

    # --- nghiệm thu bằng mô phỏng bám đường
    verify: bool = True
    verify_margin: float = 0.002       # thân xe nới 2 mm khi mô phỏng: thận trọng hơn bộ chấm
    verify_tol_xy: float = 0.047       # bộ chấm cho 5 cm; chừa một chút lề
    verify_tol_yaw: float = math.radians(4.7)
    verify_max_time: float = 200.0

    # --- quỹ đạo
    cruise_speed: float = 0.15
    approach_speed: float = 0.08
    approach_distance: float = 0.30


# --------------------------------------------------------------------------- cây

class _Tree:
    """Cây RRT.

    Mỗi nút giữ: tư thế, cha, dãy mẫu của cạnh cha->nút, chiều của cung cuối, độ dài
    "đuôi nhịp" (nhịp cùng chiều đang mở, có thể trải qua nhiều cạnh) và độ dài tối
    thiểu mà đuôi nhịp đó phải đạt khi bị đóng lại.
    """

    __slots__ = ("px", "py", "pyaw", "parent", "edge", "last_dir", "trail", "tmin",
                 "n", "cap", "ax", "ay", "root_min")

    def __init__(self, root: tuple[float, float, float], root_min: float):
        self.root_min = root_min
        self.cap = 4096
        self.ax = np.empty(self.cap)
        self.ay = np.empty(self.cap)
        self.px: list[float] = []
        self.py: list[float] = []
        self.pyaw: list[float] = []
        self.parent: list[int] = []
        self.edge: list[list | None] = []
        self.last_dir: list[int] = []
        self.trail: list[float] = []
        self.tmin: list[float] = []
        self.n = 0
        self._push(root, -1, None, _ROOT, 0.0, root_min)

    def _push(self, pose, parent, edge, last_dir, trail, tmin) -> int:
        if self.n >= self.cap:
            self.cap *= 2
            ax = np.empty(self.cap)
            ay = np.empty(self.cap)
            ax[: self.n] = self.ax[: self.n]
            ay[: self.n] = self.ay[: self.n]
            self.ax, self.ay = ax, ay
        i = self.n
        self.ax[i] = pose[0]
        self.ay[i] = pose[1]
        self.px.append(pose[0])
        self.py.append(pose[1])
        self.pyaw.append(pose[2])
        self.parent.append(parent)
        self.edge.append(edge)
        self.last_dir.append(last_dir)
        self.trail.append(trail)
        self.tmin.append(tmin)
        self.n = i + 1
        return i

    def add(self, samples, parent: int, trail: float, tmin: float) -> int:
        last = samples[-1]
        return self._push((last[0], last[1], last[2]), parent, samples, last[3], trail, tmin)

    def pose(self, i: int) -> tuple[float, float, float]:
        return (self.px[i], self.py[i], self.pyaw[i])

    def nearest(self, q, radius: float, k: int) -> int:
        """Nút có ĐỘ DÀI REEDS-SHEPP tới `q` nhỏ nhất (lọc thô bằng Euclid)."""
        n = self.n
        dx = self.ax[:n] - q[0]
        dy = self.ay[:n] - q[1]
        d2 = dx * dx + dy * dy
        if n <= k:
            order = np.argsort(d2)
        else:
            part = np.argpartition(d2, k)[:k]
            order = part[np.argsort(d2[part])]
        best_i = int(order[0])
        best = math.inf
        px, py, pyaw = self.px, self.py, self.pyaw
        for raw in order:
            i = int(raw)
            if math.sqrt(d2[i]) >= best:      # Euclid là cận dưới đúng của độ dài RS
                break
            length = min_length((px[i], py[i], pyaw[i]), q, radius)
            if length < best:
                best = length
                best_i = i
        return best_i

    def path_samples(self, node: int) -> list:
        chain = []
        i = node
        while self.parent[i] >= 0:
            chain.append(i)
            i = self.parent[i]
        chain.reverse()
        if not chain:
            return [(self.px[node], self.py[node], self.pyaw[node], 1, 0.0)]
        out = list(self.edge[chain[0]])
        for c in chain[1:]:
            out.extend(self.edge[c][1:])
        return out


def _reverse_samples(seq: list) -> list:
    """Đảo chiều đi: cùng hình học, chiều đổi dấu, góc lái giữ nguyên."""
    n = len(seq) - 1
    if n <= 0:
        x, y, yaw, d, st = seq[0]
        return [(x, y, yaw, -d, st)]
    out = [(seq[n][0], seq[n][1], seq[n][2], -seq[n][3], seq[n][4])]
    for j in range(1, n + 1):
        src = seq[n - j + 1]
        out.append((seq[n - j][0], seq[n - j][1], seq[n - j][2], -src[3], src[4]))
    return out


# ------------------------------------------------------------------ nhịp cùng chiều

def _run_bounds(samples: list) -> list[tuple[int, int]]:
    """Các nhịp cùng chiều theo chỉ số CUNG (1..n): [(đầu, cuối), ...]."""
    n = len(samples) - 1
    runs = []
    k = 1
    while k <= n:
        d = samples[k][3]
        j = k
        while j + 1 <= n and samples[j + 1][3] == d:
            j += 1
        runs.append((k, j))
        k = j + 1
    return runs


def _cumulative(seq: list) -> list[float]:
    cum = [0.0]
    for k in range(1, len(seq)):
        cum.append(cum[-1] + math.hypot(seq[k][0] - seq[k - 1][0], seq[k][1] - seq[k - 1][1]))
    return cum


def _run_stats(seq: list, soft_run: float):
    """(độ dài, số cusp, tổng độ hụt của các nhịp so với `soft_run`)."""
    n = len(seq) - 1
    if n < 1:
        return 0.0, 0, 0.0
    cum = _cumulative(seq)
    cusps = 0
    deficit = 0.0
    k = 1
    while k <= n:
        d = seq[k][3]
        j = k
        while j + 1 <= n and seq[j + 1][3] == d:
            j += 1
        if k > 1:
            cusps += 1
        run = cum[j] - cum[k - 1]
        if run < soft_run:
            deficit += (soft_run - run) / soft_run
        k = j + 1
    return cum[n], cusps, deficit


def _full_cost(seq: list, p: "RRTParams") -> float:
    length, cusps, deficit = _run_stats(seq, p.soft_run)
    return length + p.cusp_weight * cusps + p.short_run_penalty * deficit


# ------------------------------------------------------------------ lái cục bộ

def _word_deficit(lengths, radius: float, soft_run: float) -> float:
    """Tổng độ hụt (đã chuẩn hóa) của các nhịp trong một từ RS so với `soft_run`."""
    deficit = 0.0
    cur = 0.0
    sign = 0
    for l in lengths:
        if -1e-9 < l < 1e-9:
            continue
        sgn = 1 if l > 0.0 else -1
        if sign and sgn != sign:
            r = cur * radius
            if r < soft_run:
                deficit += (soft_run - r) / soft_run
            cur = 0.0
        sign = sgn
        cur += l if l > 0.0 else -l
    r = cur * radius
    if r < soft_run:
        deficit += (soft_run - r) / soft_run
    return deficit


class _Steerer:
    __slots__ = ("radius", "steer_mag", "checker", "step", "cands", "cusp_w",
                 "min_run", "soft_run", "run_pen", "rs_calls")

    def __init__(self, radius, steer_mag, checker, step, cands, cusp_w, min_run,
                 soft_run=0.0, run_pen=0.0):
        self.radius = radius
        self.steer_mag = steer_mag
        self.checker = checker
        self.step = step
        self.cands = cands
        self.cusp_w = cusp_w
        self.min_run = min_run
        self.soft_run = soft_run
        self.run_pen = run_pen
        self.rs_calls = 0

    def _words(self, a, b):
        words = sorted_words(a, b, self.radius, self.cusp_w, validate=False)
        if self.run_pen > 0.0 and self.soft_run > 0.0 and len(words) > 1:
            r, sr, cw, rp = self.radius, self.soft_run, self.cusp_w, self.run_pen
            words.sort(key=lambda w: w[2] + cw * w[3] + rp * _word_deficit(w[0], r, sr))
        return words

    def walk(self, a, lengths, ctypes, max_len: float):
        """Đi dọc một từ RS, kiểm va chạm NGAY từng mẫu, dừng ở va chạm/hết ngân sách.

        Sinh mẫu và kiểm tra xen kẽ (thay vì sinh hết rồi mới kiểm) là chỗ tiết kiệm
        lớn nhất trong chỗ chật, nơi phần lớn cung bị chặn ngay mấy centimet đầu.
        Trả về (samples, cum, stopped).
        """
        radius, step, sm = self.radius, self.step, self.steer_mag
        ok = self.checker.pose_ok
        ox, oy, oyaw = a
        samples = None
        cum = [0.0]
        acc = 0.0
        stopped = False
        for l, m in zip(lengths, ctypes):
            if -_TINY < l < _TINY:
                continue
            d = 1 if l > 0.0 else -1
            stq = sm if m == "L" else (-sm if m == "R" else 0.0)
            if samples is None:
                samples = [(ox, oy, oyaw, d, stq)]
            seg_len = (l if l > 0.0 else -l) * radius
            n = int(seg_len / step) + 1
            for k in range(1, n + 1):
                x, y, yaw = _interp(l * k / n, m, radius, ox, oy, oyaw)
                c = acc + seg_len * k / n
                if c > max_len or not ok(x, y, yaw):
                    stopped = True
                    break
                samples.append((x, y, wrap(yaw), d, stq))
                cum.append(c)
            if stopped:
                break
            acc += seg_len
            ox, oy, oyaw = _interp(l, m, radius, ox, oy, oyaw)
            oyaw = wrap(oyaw)
        if samples is None:
            return None, None, True
        return samples, cum, stopped

    def steer(self, a, b, max_len: float, prev_dir: int, trail: float, tmin: float,
              fresh_min: float):
        """Đoạn đầu dài nhất, không va chạm, của một đường RS từ a tới b.

        Trả về (samples, reached, trail_mới, tmin_mới) hoặc None nếu không tiến được.
        `fresh_min` là yêu cầu cho nhịp đầu khi nó KHÔNG nối tiếp đuôi nhịp cũ.
        """
        self.rs_calls += 1
        words = self._words(a, b)
        if not words:
            return None
        mr = self.min_run
        best = None
        best_len = 0.0
        for lengths, ctypes, _lm, _nc in words[: self.cands]:
            samples, cum, stopped = self.walk(a, lengths, ctypes, max_len)
            if samples is None or len(samples) < 2:
                continue
            merge0 = prev_dir != _ROOT and samples[1][3] == prev_dir
            if prev_dir != _ROOT and not merge0 and trail < tmin:
                continue                     # đóng đuôi nhịp cũ mà nó còn quá ngắn
            req0 = tmin if merge0 else fresh_min

            runs = _run_bounds(samples)
            m = len(samples) - 1
            reached = (not stopped) and _reached(samples[-1], b)
            for idx, (ks, ke) in enumerate(runs[:-1]):
                length = cum[ke] - cum[ks - 1] + (trail if (idx == 0 and merge0) else 0.0)
                if length < (req0 if idx == 0 else mr):
                    m = ks - 1
                    reached = False
                    break
            if m <= 0:
                continue

            ks, idx = runs[0][0], 0
            for t, (a0, b0) in enumerate(runs):
                if a0 <= m <= b0:
                    ks, idx = a0, t
                    break
            if idx == 0 and merge0:
                new_trail = trail + (cum[m] - cum[ks - 1])
                new_tmin = tmin
            else:
                new_trail = cum[m] - cum[ks - 1]
                new_tmin = req0 if idx == 0 else mr

            if reached:
                return samples, True, new_trail, new_tmin
            if cum[m] > best_len:
                best_len = cum[m]
                best = (samples[: m + 1], False, new_trail, new_tmin)
        if best is None or best_len < 1e-9:
            return None
        return best

    def connect_free(self, a, b, max_len: float = math.inf):
        """Đường RS trọn vẹn, không va chạm, từ a tới b (không xét ràng buộc nhịp)."""
        self.rs_calls += 1
        for lengths, ctypes, lm, _nc in self._words(a, b)[: self.cands]:
            if lm > max_len:
                continue
            samples, _cum, stopped = self.walk(a, lengths, ctypes, math.inf)
            if (not stopped) and samples is not None and len(samples) > 1 \
                    and _reached(samples[-1], b):
                return samples
        return None


def _reached(sample, target, xy_tol=2.0e-3, yaw_tol=4.0e-3) -> bool:
    return (abs(sample[0] - target[0]) < xy_tol and abs(sample[1] - target[1]) < xy_tol
            and abs(wrap(sample[2] - target[2])) < yaw_tol)


# ------------------------------------------------------------------ rút gọn

def _index_at(cum: list[float], s: float) -> int:
    lo, hi = 0, len(cum) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if cum[mid] < s:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _short_runs(seq: list, soft_run: float) -> list[tuple[int, int]]:
    n = len(seq) - 1
    cum = _cumulative(seq)
    out = []
    k = 1
    while k <= n:
        d = seq[k][3]
        j = k
        while j + 1 <= n and seq[j + 1][3] == d:
            j += 1
        if cum[j] - cum[k - 1] < soft_run:
            out.append((k, j))
        k = j + 1
    return out


def _shortcut(seq: list, steerer: _Steerer, rng: random.Random, p: RRTParams,
              deadline: float) -> list:
    """Rút gọn ngẫu nhiên: nối trực tiếp hai điểm xa nhau trên đường bằng RS."""
    cost = _full_cost(seq, p)
    tries = 0
    while time.perf_counter() < deadline:
        checkpoint()
        tries += 1
        n = len(seq)
        if n < 4:
            break
        cum = _cumulative(seq)
        total = cum[-1]
        if total < p.shortcut_min_span * 1.5:
            break
        mode = tries & 3
        if mode == 0:
            shorts = _short_runs(seq, p.soft_run)
            if shorts:
                ks, ke = shorts[rng.randrange(len(shorts))]
                span = rng.uniform(p.soft_run, 5.0 * p.soft_run)
                i = _index_at(cum, max(0.0, cum[ks - 1] - span))
                j = _index_at(cum, min(total, cum[ke] + span))
            else:
                i, j = 0, n - 1
        elif mode == 2:
            i, j = 0, n - 1
        else:
            s1 = rng.uniform(0.0, total)
            s2 = rng.uniform(0.0, total)
            if s1 > s2:
                s1, s2 = s2, s1
            if s2 - s1 < p.shortcut_min_span:
                continue
            i = _index_at(cum, s1)
            j = _index_at(cum, s2)
        if j - i < 2:
            continue
        a = (seq[i][0], seq[i][1], seq[i][2])
        b = (seq[j][0], seq[j][1], seq[j][2])
        new = steerer.connect_free(a, b, max_len=cum[j] - cum[i] + p.cusp_weight * 8.0)
        if new is None:
            continue
        new = list(new)
        new[0] = (new[0][0], new[0][1], new[0][2], seq[i][3], seq[i][4])
        cand = seq[:i] + new + seq[j + 1:]
        c = _full_cost(cand, p)
        if c < cost - 1e-6:
            seq = cand
            cost = c
    return seq


# ------------------------------------------------------------------ lấy mẫu

class _Sampler:
    def __init__(self, bounds: Bounds, start, goal, checker, rng: random.Random, p: RRTParams):
        self.b = bounds
        self.start = start
        self.goal = goal
        self.checker = checker
        self.rng = rng
        self.p = p

    def sample(self, trees):
        rng = self.rng
        p = self.p
        b = self.b
        ok = self.checker.pose_ok
        for _ in range(p.sample_tries):
            r = rng.random()
            if r < p.goal_bias:
                base = self.goal
            elif r < p.goal_bias + p.start_bias:
                base = self.start
            elif r < p.goal_bias + p.start_bias + p.node_bias:
                tree = trees[rng.randrange(len(trees))]
                i = rng.randrange(tree.n)
                base = (tree.px[i], tree.py[i], tree.pyaw[i])
            else:
                base = None
            if base is None:
                x = rng.uniform(b.xmin, b.xmax)
                y = rng.uniform(b.ymin, b.ymax)
                yaw = rng.uniform(-math.pi, math.pi)
            else:
                x = base[0] + rng.gauss(0.0, p.bias_sigma_xy)
                y = base[1] + rng.gauss(0.0, p.bias_sigma_xy)
                yaw = wrap(base[2] + rng.gauss(0.0, p.bias_sigma_yaw))
                if not (b.xmin <= x <= b.xmax and b.ymin <= y <= b.ymax):
                    continue
            if ok(x, y, yaw):
                return (x, y, yaw)
        return None


# ------------------------------------------- nghiệm thu: mô phỏng bám đường kín vòng

def _simulate(traj: Trajectory, cfg: VehicleConfig, checker: FastCollisionChecker,
              goal: Pose, p: RRTParams, dt: float = 0.005, control_every: int = 4):
    """Chạy đúng bộ bám + mô hình xe của dự án. Trả về (đạt, sai số xy, sai số yaw, lý do).

    Cùng dt và nhịp điều khiển với `simulation.rollout`; va chạm kiểm bằng bộ giải
    tích (bước 5 ms ở tốc độ <= 0,3 m/s cho dịch chuyển <= 1,5 mm nên đủ dày).
    """
    veh = SimVehicle(cfg, VehicleState(traj.points[0].pose, 0.0, 0.0, 0.0))
    tracker = TrajectoryTracker(traj, cfg)
    ok = checker.pose_ok
    speed = steer = 0.0
    step = 0
    max_steps = int(p.verify_max_time / dt)
    done = False
    while step < max_steps:
        if step % control_every == 0:
            checkpoint()
            out = tracker.update(veh.state)
            speed, steer = out.target_speed, out.target_steer
            if out.done and abs(veh.state.speed) < 1e-3:
                done = True
                break
        st = veh.step(dt, speed, steer)
        step += 1
        if not ok(st.pose.x, st.pose.y, st.pose.yaw):
            return False, math.inf, math.inf, "va chạm khi bám đường"
    pose = veh.state.pose
    ex = math.hypot(pose.x - goal.x, pose.y - goal.y)
    ey = abs(wrap(pose.yaw - goal.yaw))
    if not done:
        return False, ex, ey, "quá thời gian mô phỏng"
    if ex > p.verify_tol_xy or ey > p.verify_tol_yaw:
        return False, ex, ey, f"sai số cuối {ex * 100:.1f} cm / {math.degrees(ey):.1f}°"
    return True, ex, ey, ""


# ------------------------------------------------------------------ hàm chính

@controlled_plan(20.0)
def plan(start: Pose, goal: Pose, cfg: VehicleConfig, obstacles: list[Obstacle],
         bounds: Bounds, params=None) -> PlanResult:
    t0 = time.perf_counter()
    p = _resolve_params(params)

    goal_true = check_pose(cfg, goal, obstacles, bounds)
    if not goal_true.ok:
        return PlanResult("GOAL_INVALID", "Đích không hợp lệ: " + goal_true.describe(),
                          None, time.perf_counter() - t0, 0, 0)
    start_true = check_pose(cfg, start, obstacles, bounds)
    if not start_true.ok:
        return PlanResult("START_INVALID", "Xuất phát không hợp lệ: " + start_true.describe(),
                          None, time.perf_counter() - t0, 0, 0)

    # Lề an toàn: đúng công thức của hybrid_astar.py (không được nới lỏng hơn).
    margin = max(0.0, min(p.safety_margin, goal_true.min_clearance / 2, start_true.min_clearance / 2))

    checker = FastCollisionChecker(cfg, obstacles, bounds, margin)
    sim_checker = FastCollisionChecker(cfg, obstacles, bounds, p.verify_margin)
    steer_mag = cfg.max_steer * p.steer_ratio
    radius = cfg.wheelbase / math.tan(steer_mag)

    s = (start.x, start.y, start.yaw)
    g = (goal.x, goal.y, goal.yaw)
    deadline = t0 + p.time_limit

    def finish(seq):
        raw = [(Pose(x, y, yaw), d, st) for (x, y, yaw, d, st) in seq]
        return build_trajectory(raw, goal, cfg, p.cruise_speed, p.approach_speed,
                                p.approach_distance)

    def swept_ok(traj) -> bool:
        """Kiểm tra lại vùng quét với thân xe THẬT (Shapely, không nới lề)."""
        for a, b in zip(traj.points, traj.points[1:]):
            checkpoint()
            if not check_motion(cfg, a.pose, b.pose, obstacles, bounds).ok:
                return False
        return True

    def est_track_time(traj) -> float:
        """Ước lượng thô thời gian bộ bám cần: mỗi đoạn tốn thêm ~1,2 s dừng + chỉnh lái."""
        return traj.length / max(p.cruise_speed, 1e-3) + 1.2 * len(traj.segments)

    stats = {"iters": 0, "nodes": 0, "verify": 0, "cands": 0}
    fallback = [None, ""]      # quỹ đạo hợp lệ hình học nhưng chưa nghiệm thu được

    def run_epoch(min_run: float, ep_deadline: float, seed: int):
        """Một lượt RRT-Connect trọn vẹn với một mức `min_run`; trả về quỹ đạo đã nghiệm thu."""
        rng = random.Random(seed)
        st = _Steerer(radius, steer_mag, checker, p.rs_step, p.steer_candidates,
                      p.cusp_weight, min_run, p.soft_run, p.word_run_penalty)
        tree_a = _Tree(s, min_run)
        tree_b = _Tree(g, min_run)
        trees = (tree_a, tree_b)
        sampler = _Sampler(bounds, s, g, checker, rng, p)
        cur = {"ta": tree_a, "tb": tree_b}

        def grow(slice_deadline, max_joins: int = 3):
            found = []
            ta, tb = cur["ta"], cur["tb"]
            try:
                while time.perf_counter() < slice_deadline:
                    checkpoint()
                    stats["iters"] += 1
                    q = sampler.sample(trees)
                    if q is None:
                        continue
                    i_near = ta.nearest(q, radius, p.nn_k)
                    res = st.steer(ta.pose(i_near), q, p.max_extend, ta.last_dir[i_near],
                                   ta.trail[i_near], ta.tmin[i_near],
                                   ta.root_min if i_near == 0 else min_run)
                    if res is None:
                        ta, tb = tb, ta
                        continue
                    na = ta.add(res[0], i_near, res[2], res[3])
                    target = ta.pose(na)

                    nb = tb.nearest(target, radius, p.nn_k)
                    joined = False
                    for _ in range(p.connect_iters):
                        checkpoint()
                        res2 = st.steer(tb.pose(nb), target, p.connect_extend, tb.last_dir[nb],
                                        tb.trail[nb], tb.tmin[nb],
                                        tb.root_min if nb == 0 else min_run)
                        if res2 is None:
                            break
                        nb = tb.add(res2[0], nb, res2[2], res2[3])
                        if res2[1] or _reached(tb.pose(nb), target):
                            joined = True
                            break
                        if time.perf_counter() >= slice_deadline:
                            break
                    if joined:
                        if ta is tree_a:
                            n_start, n_goal = na, nb
                        else:
                            n_start, n_goal = nb, na
                        fwd = tree_a.path_samples(n_start)
                        bwd = _reverse_samples(tree_b.path_samples(n_goal))
                        found.append(fwd + bwd[1:])
                        if len(found) >= max_joins:
                            return found
                    ta, tb = tb, ta
                return found
            finally:
                cur["ta"], cur["tb"] = ta, tb

        pool: list[list] = []          # [dãy mẫu, giá, số lượt gọt, đã nghiệm thu hỏng]
        direct = st.connect_free(s, g)
        if direct is not None:
            seq0 = list(direct)
            pool.append([seq0, _full_cost(seq0, p), 0, False])

        # Giữ ít nhất một nửa thời gian cho việc MỌC CÂY: đa dạng đường thô quan
        # trọng hơn là gọt mãi một đường vốn không bám được.
        t_grow = t_proc = 0.0
        try:
            while time.perf_counter() < ep_deadline:
                checkpoint()
                g0 = time.perf_counter()
                want = p.grow_slice + max(0.0, t_proc - t_grow)
                for raw_sol in grow(min(g0 + want, ep_deadline)):
                    pool.append([raw_sol, _full_cost(raw_sol, p), 0, False])
                    stats["cands"] += 1
                while len(pool) > p.pool_size:
                    pool.remove(max(pool, key=lambda it: it[1] + 0.20 * it[2]))
                t_grow += time.perf_counter() - g0
                if not pool or time.perf_counter() >= ep_deadline:
                    continue

                p0 = time.perf_counter()
                try:
                    item = min(pool, key=lambda it: it[1] + 0.20 * it[2])
                    item[0] = _shortcut(item[0], st, rng, p,
                                        min(p0 + p.smooth_budget, ep_deadline))
                    new_cost = _full_cost(item[0], p)
                    improved = new_cost < item[1] - 1e-9
                    item[1] = new_cost
                    item[2] += 1
                    if item[3] and not improved:
                        continue           # đã hỏng và không khá hơn: khỏi thử lại
                    traj = finish(item[0])
                    if not p.verify:
                        if swept_ok(traj):
                            return traj
                        continue
                    if est_track_time(traj) > p.max_track_time:
                        item[3] = True
                        continue
                    stats["verify"] += 1
                    ok_sim, _ex, _ey, why = _simulate(traj, cfg, sim_checker, goal, p)
                    if ok_sim and swept_ok(traj):
                        return traj
                    item[3] = True
                    if fallback[0] is None and "va chạm" not in why and swept_ok(traj):
                        fallback[0] = traj
                        fallback[1] = f"CHƯA nghiệm thu được bằng mô phỏng bám ({why})"
                finally:
                    t_proc += time.perf_counter() - p0
            return None
        finally:
            stats["nodes"] += tree_a.n + tree_b.n

    # Lịch "epoch": xen kẽ vài mức `min_run`. Ngưỡng nhịp tối thiểu giúp các ca như
    # uturn_w46 (hành lang 46 cm) ra đường bám được, nhưng lại làm các ca đỗ song
    # song rất chật (parallel_122, pocket_exit_park) thành vô nghiệm — nên phải thử
    # cả hai chứ không chọn cứng một giá trị.
    total = max(0.05, p.time_limit)
    verified = None
    for k, (min_run, frac) in enumerate(p.epochs):
        checkpoint()
        if time.perf_counter() >= deadline:
            break
        ep_deadline = min(t0 + total * sum(f for _, f in p.epochs[:k + 1]), deadline)
        if ep_deadline <= time.perf_counter():
            continue
        verified = run_epoch(min_run, ep_deadline, p.seed + 1013 * k)
        if verified is not None:
            break

    elapsed = time.perf_counter() - t0
    traj = verified if verified is not None else fallback[0]
    if traj is None:
        return PlanResult("TIMEOUT",
                          f"RRT-Connect không nối được hai cây sau {stats['iters']} vòng, "
                          f"{stats['nodes']} nút, {stats['cands']} đường thô, "
                          f"{stats['verify']} lần nghiệm thu, {elapsed:.1f} s "
                          f"(hạt giống {p.seed})",
                          None, elapsed, stats["nodes"], stats["iters"])

    msg = (f"RRT-Connect+RS: dài {traj.length:.2f} m, {traj.n_cusps} lần đổi chiều, "
           f"{stats['iters']} vòng, {stats['nodes']} nút, {stats['cands']} đường thô, "
           f"{stats['verify']} lần nghiệm thu, hạt giống {p.seed}")
    if verified is None:
        msg += " | " + fallback[1]
    return PlanResult("OK", msg, traj, elapsed, stats["nodes"], stats["iters"])


def _resolve_params(params) -> RRTParams:
    p = RRTParams()
    env_seed = os.environ.get("AUTOPARK_RRT_SEED")
    if isinstance(params, RRTParams):
        p = params
    elif params is not None:
        for name in ("time_limit", "safety_margin", "steer_ratio",
                     "cruise_speed", "approach_speed", "approach_distance"):
            if hasattr(params, name):
                setattr(p, name, getattr(params, name))
        if hasattr(params, "seed"):
            p.seed = int(getattr(params, "seed"))
    if env_seed:
        try:
            p.seed = int(env_seed)
        except ValueError:
            pass
    return p
