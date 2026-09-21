"""Đường Reeds–Shepp rút gọn (họ CSC và CCC) cho Hybrid A*.

Chuẩn hóa theo bán kính quay nhỏ nhất = 1: mọi tọa độ nhân với `maxc = 1/R_min`.
Đoạn 'L'/'R' là cung quay trái/phải có độ dài bằng góc quay; 'S' là đoạn thẳng.
Độ dài âm nghĩa là chạy lùi. Công thức theo Reeds & Shepp (1990), cách tổ chức
các phép đối xứng theo PythonRobotics. Chỉ dùng hai họ (16 biến thể) nên không
bảo đảm là đường ngắn nhất; bù lại mọi ứng viên đều được kiểm tra điểm cuối bằng
tích phân trước khi trả về, nên một công thức sai chỉ làm mất ứng viên, không tạo
đường sai.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from autopark.domain.types import Pose, wrap_angle

TWO_PI = 2.0 * math.pi
_END_TOL = 1e-6


def mod2pi(x: float) -> float:
    """Đưa về (-pi, pi] giữ quy ước của công thức gốc."""
    v = math.fmod(x, TWO_PI)
    if v < -math.pi:
        v += TWO_PI
    elif v > math.pi:
        v -= TWO_PI
    return v


@dataclass(frozen=True)
class RSPath:
    lengths: tuple[float, float, float]   # chuẩn hóa, có dấu
    ctypes: tuple[str, str, str]          # 'L', 'S', 'R'

    @property
    def length(self) -> float:
        return abs(self.lengths[0]) + abs(self.lengths[1]) + abs(self.lengths[2])

    @property
    def n_cusps(self) -> int:
        signs = [l for l in self.lengths if abs(l) > 1e-12]
        return sum(1 for a, b in zip(signs, signs[1:]) if a * b < 0)


def _polar(x: float, y: float) -> tuple[float, float]:
    return math.hypot(x, y), math.atan2(y, x)


def _lsl(x: float, y: float, phi: float):
    u, t = _polar(x - math.sin(phi), y - 1.0 + math.cos(phi))
    if t >= 0.0:
        v = mod2pi(phi - t)
        if v >= 0.0:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lsr(x: float, y: float, phi: float):
    u1, t1 = _polar(x + math.sin(phi), y - 1.0 - math.cos(phi))
    u1 = u1 * u1
    if u1 >= 4.0:
        u = math.sqrt(u1 - 4.0)
        theta = math.atan2(2.0, u)
        t = mod2pi(t1 + theta)
        v = mod2pi(t - phi)
        if t >= 0.0 and v >= 0.0:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lrl(x: float, y: float, phi: float):
    u1, t1 = _polar(x - math.sin(phi), y - 1.0 + math.cos(phi))
    if u1 <= 4.0:
        u = -2.0 * math.asin(0.25 * u1)
        t = mod2pi(t1 + 0.5 * u + math.pi)
        v = mod2pi(phi - t + u)
        if t >= 0.0 and u <= 0.0:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _raw_candidates(x: float, y: float, phi: float) -> list[RSPath]:
    out: list[RSPath] = []

    def add(res, types, neg=False, reverse_order=False):
        flag, t, u, v = res
        if not flag:
            return
        lengths = (v, u, t) if reverse_order else (t, u, v)
        if neg:
            lengths = (-lengths[0], -lengths[1], -lengths[2])
        out.append(RSPath(lengths, types))

    lsl, lsr, lrl, rsr, rsl, rlr = ("L", "S", "L"), ("L", "S", "R"), ("L", "R", "L"), ("R", "S", "R"), ("R", "S", "L"), ("R", "L", "R")
    # CSC
    add(_lsl(x, y, phi), lsl)
    add(_lsl(-x, y, -phi), lsl, neg=True)
    add(_lsl(x, -y, -phi), rsr)
    add(_lsl(-x, -y, phi), rsr, neg=True)
    add(_lsr(x, y, phi), lsr)
    add(_lsr(-x, y, -phi), lsr, neg=True)
    add(_lsr(x, -y, -phi), rsl)
    add(_lsr(-x, -y, phi), rsl, neg=True)
    # CCC
    add(_lrl(x, y, phi), lrl)
    add(_lrl(-x, y, -phi), lrl, neg=True)
    add(_lrl(x, -y, -phi), rlr)
    add(_lrl(-x, -y, phi), rlr, neg=True)
    xb = x * math.cos(phi) + y * math.sin(phi)
    yb = x * math.sin(phi) - y * math.cos(phi)
    add(_lrl(xb, yb, phi), lrl, reverse_order=True)
    add(_lrl(-xb, yb, -phi), lrl, neg=True, reverse_order=True)
    add(_lrl(xb, -yb, -phi), rlr, reverse_order=True)
    add(_lrl(-xb, -yb, phi), rlr, neg=True, reverse_order=True)
    return out


def _interpolate(p: float, mode: str, maxc: float, ox: float, oy: float, oyaw: float) -> tuple[float, float, float]:
    """Tư thế sau khi đi tiến độ có dấu `p` (chuẩn hóa) trên đoạn `mode` từ (ox, oy, oyaw)."""
    if mode == "S":
        return ox + p / maxc * math.cos(oyaw), oy + p / maxc * math.sin(oyaw), oyaw
    ldx = math.sin(p) / maxc
    if mode == "L":
        ldy = (1.0 - math.cos(p)) / maxc
        yaw = oyaw + p
    else:  # "R"
        ldy = -(1.0 - math.cos(p)) / maxc
        yaw = oyaw - p
    c, s = math.cos(oyaw), math.sin(oyaw)
    return ox + c * ldx - s * ldy, oy + s * ldx + c * ldy, yaw


def normalized_goal(q0: Pose, q1: Pose, maxc: float) -> tuple[float, float, float]:
    dx, dy = q1.x - q0.x, q1.y - q0.y
    c, s = math.cos(q0.yaw), math.sin(q0.yaw)
    return (c * dx + s * dy) * maxc, (-s * dx + c * dy) * maxc, wrap_angle(q1.yaw - q0.yaw)


def path_end(q0: Pose, path: RSPath, maxc: float) -> Pose:
    x, y, yaw = q0.x, q0.y, q0.yaw
    for l, m in zip(path.lengths, path.ctypes):
        if abs(l) > 1e-12:
            x, y, yaw = _interpolate(l, m, maxc, x, y, yaw)
    return Pose(x, y, wrap_angle(yaw))


def candidate_paths(q0: Pose, q1: Pose, maxc: float) -> list[RSPath]:
    """Các đường RS từ q0 tới q1, đã kiểm tra điểm cuối, xếp theo độ dài tăng dần."""
    x, y, phi = normalized_goal(q0, q1, maxc)
    valid: list[RSPath] = []
    for path in _raw_candidates(x, y, phi):
        end = path_end(q0, path, maxc)
        if (math.hypot(end.x - q1.x, end.y - q1.y) * maxc < _END_TOL
                and abs(wrap_angle(end.yaw - q1.yaw)) < _END_TOL):
            valid.append(path)
    valid.sort(key=lambda p: p.length)
    return valid


def shortest_length(q0: Pose, q1: Pose, maxc: float) -> float:
    """Độ dài (m) đường RS ngắn nhất trong tập ứng viên; inf nếu không có."""
    paths = candidate_paths(q0, q1, maxc)
    if not paths:
        return math.inf
    return paths[0].length / maxc


def sample_path(q0: Pose, path: RSPath, maxc: float, step: float) -> list[tuple[Pose, int, str]]:
    """Lấy mẫu dọc đường: (tư thế, chiều ±1, loại đoạn). Điểm đầu là q0."""
    first_dir = 1
    for l in path.lengths:
        if abs(l) > 1e-12:
            first_dir = 1 if l > 0 else -1
            break
    out: list[tuple[Pose, int, str]] = [(q0, first_dir, path.ctypes[0])]
    ox, oy, oyaw = q0.x, q0.y, q0.yaw
    for l, m in zip(path.lengths, path.ctypes):
        if abs(l) < 1e-12:
            continue
        direction = 1 if l > 0 else -1
        n = max(1, int(math.ceil(abs(l) / (step * maxc))))
        for k in range(1, n + 1):
            x, y, yaw = _interpolate(l * k / n, m, maxc, ox, oy, oyaw)
            out.append((Pose(x, y, wrap_angle(yaw)), direction, m))
        ox, oy, oyaw = _interpolate(l, m, maxc, ox, oy, oyaw)
    return out
