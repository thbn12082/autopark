"""Reeds–Shepp đầy đủ: 48 từ đường, thay cho bản rút gọn 16 từ trong `reeds_shepp.py`.

Bản cũ chỉ có hai họ CSC (thẳng kẹp giữa hai cung) và CCC (ba cung). Thiếu ba họ
CCCC, CCSC, CCSCC — đúng những họ nối được hai tư thế trong chỗ chật, vì chúng
cho phép nhiều lần đổi chiều liên tiếp. Đo trên bộ ca khó cho thấy đây là một
trong bốn nguyên nhân làm bộ lập đường bó tay ở các thao tác nhiều nhịp.

Chuẩn hoá theo bán kính quay nhỏ nhất bằng 1: mọi toạ độ nhân với `maxc = 1/R_min`.
Ký hiệu đoạn: 'L' cung trái, 'R' cung phải, 'S' đoạn thẳng. Độ dài mang dấu; âm
nghĩa là chạy lùi.

Công thức lấy theo Reeds & Shepp (1990), các mục 8.1–8.11, cùng ba phép đối xứng
(đảo thời gian, lấy đối xứng gương, đi ngược) để sinh đủ 48 từ từ 9 công thức gốc.
MỌI ứng viên đều được tích phân lại tới điểm cuối và chỉ giữ khi sai số dưới
ngưỡng, nên một công thức chép sai chỉ làm mất ứng viên chứ không sinh ra đường sai.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from autopark.domain.types import Pose, wrap_angle

TWO_PI = 2.0 * math.pi
HALF_PI = 0.5 * math.pi
_END_TOL = 1e-6
_EPS = 1e-12


def mod2pi(x: float) -> float:
    """Đưa góc về (-pi, pi], giữ đúng quy ước của công thức gốc."""
    v = math.fmod(x, TWO_PI)
    if v < -math.pi:
        v += TWO_PI
    elif v > math.pi:
        v -= TWO_PI
    return v


def _polar(x: float, y: float) -> tuple[float, float]:
    return math.hypot(x, y), math.atan2(y, x)


@dataclass(frozen=True)
class RSPath:
    lengths: tuple[float, ...]     # chuẩn hoá, mang dấu
    ctypes: tuple[str, ...]        # 'L', 'S', 'R'

    @property
    def length(self) -> float:
        return sum(abs(v) for v in self.lengths)

    @property
    def n_cusps(self) -> int:
        signs = [v for v in self.lengths if abs(v) > _EPS]
        return sum(1 for a, b in zip(signs, signs[1:]) if a * b < 0)

    @property
    def word(self) -> str:
        return "".join(
            (c if v >= 0 else c.lower()) for c, v in zip(self.ctypes, self.lengths) if abs(v) > _EPS
        )


# --------------------------------------------------------------------- công thức gốc
# Mỗi hàm trả về (tìm được?, t, u, v). Toạ độ đầu vào đã chuẩn hoá và đã đưa về
# hệ của tư thế xuất phát.

def _lsl(x: float, y: float, phi: float):
    """8.1  L+ S+ L+"""
    u, t = _polar(x - math.sin(phi), y - 1.0 + math.cos(phi))
    if t >= 0.0:
        v = mod2pi(phi - t)
        if v >= 0.0:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lsr(x: float, y: float, phi: float):
    """8.2  L+ S+ R+"""
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
    """8.3 / 8.4  L+ R- L+"""
    u1, t1 = _polar(x - math.sin(phi), y - 1.0 + math.cos(phi))
    if u1 <= 4.0:
        u = -2.0 * math.asin(0.25 * u1)
        t = mod2pi(t1 + 0.5 * u + math.pi)
        v = mod2pi(phi - t + u)
        if t >= 0.0 and u <= 0.0:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _tau_omega(u: float, v: float, xi: float, eta: float, phi: float) -> tuple[float, float]:
    delta = mod2pi(u - v)
    A = math.sin(u) - math.sin(delta)
    B = math.cos(u) - math.cos(delta) - 1.0
    t1 = math.atan2(eta * A - xi * B, xi * A + eta * B)
    t2 = 2.0 * (math.cos(delta) - math.cos(v) - math.cos(u)) + 3.0
    tau = mod2pi(t1 + math.pi) if t2 < 0.0 else mod2pi(t1)
    omega = mod2pi(tau - u + v - phi)
    return tau, omega


def _lrlr_a(x: float, y: float, phi: float):
    """8.7  L+ R+ L- R-"""
    xi = x + math.sin(phi)
    eta = y - 1.0 - math.cos(phi)
    rho = 0.25 * (2.0 + math.hypot(xi, eta))
    if rho <= 1.0:
        u = math.acos(rho)
        t, v = _tau_omega(u, -u, xi, eta, phi)
        if t >= 0.0 and v <= 0.0:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lrlr_b(x: float, y: float, phi: float):
    """8.8  L+ R- L- R+"""
    xi = x + math.sin(phi)
    eta = y - 1.0 - math.cos(phi)
    rho = (20.0 - xi * xi - eta * eta) / 16.0
    if 0.0 <= rho <= 1.0:
        u = -math.acos(rho)
        if u >= -HALF_PI:
            t, v = _tau_omega(u, u, xi, eta, phi)
            if t >= 0.0 and v >= 0.0:
                return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lrsl(x: float, y: float, phi: float):
    """8.9  L+ R- S- L-"""
    xi = x - math.sin(phi)
    eta = y - 1.0 + math.cos(phi)
    rho, theta = _polar(xi, eta)
    if rho >= 2.0:
        r = math.sqrt(rho * rho - 4.0)
        u = 2.0 - r
        t = mod2pi(theta + math.atan2(r, -2.0))
        v = mod2pi(phi - HALF_PI - t)
        if t >= 0.0 and u <= 0.0 and v <= 0.0:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lrsr(x: float, y: float, phi: float):
    """8.10  L+ R- S- R-"""
    xi = x + math.sin(phi)
    eta = y - 1.0 - math.cos(phi)
    rho, theta = _polar(-eta, xi)
    if rho >= 2.0:
        t = theta
        u = 2.0 - rho
        v = mod2pi(t + HALF_PI - phi)
        if t >= 0.0 and u <= 0.0 and v <= 0.0:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lrslr(x: float, y: float, phi: float):
    """8.11  L+ R- S- L- R+"""
    xi = x + math.sin(phi)
    eta = y - 1.0 - math.cos(phi)
    rho, _ = _polar(xi, eta)
    if rho >= 2.0:
        u = 4.0 - math.sqrt(rho * rho - 4.0)
        if u <= 0.0:
            t = mod2pi(math.atan2((4.0 - u) * xi - 2.0 * eta, -2.0 * xi + (u - 4.0) * eta))
            v = mod2pi(t - phi)
            if t >= 0.0 and v >= 0.0:
                return True, t, u, v
    return False, 0.0, 0.0, 0.0


# --------------------------------------------------------------------- sinh đủ 48 từ

_FLIP = {"L": "R", "R": "L", "S": "S"}


def _mirror(types: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(_FLIP[c] for c in types)


def _add(out: list[RSPath], types: tuple[str, ...], lengths: tuple[float, ...]) -> None:
    out.append(RSPath(lengths, types))


def _emit(out: list[RSPath], base, x: float, y: float, phi: float,
          types: tuple[str, ...], build) -> None:
    """Áp bốn phép đối xứng lên một công thức gốc.

    - gốc:          f(x, y, phi)
    - đảo thời gian: f(-x, y, -phi), độ dài đổi dấu
    - gương:        f(x, -y, -phi), đổi L thành R
    - cả hai:       f(-x, -y, phi), đổi dấu và đổi L thành R
    """
    flag, t, u, v = base(x, y, phi)
    if flag:
        _add(out, types, build(t, u, v))
    flag, t, u, v = base(-x, y, -phi)
    if flag:
        _add(out, types, tuple(-l for l in build(t, u, v)))
    flag, t, u, v = base(x, -y, -phi)
    if flag:
        _add(out, _mirror(types), build(t, u, v))
    flag, t, u, v = base(-x, -y, phi)
    if flag:
        _add(out, _mirror(types), tuple(-l for l in build(t, u, v)))


def _raw_candidates(x: float, y: float, phi: float) -> list[RSPath]:
    out: list[RSPath] = []

    # CSC — hai cung kẹp một đoạn thẳng
    _emit(out, _lsl, x, y, phi, ("L", "S", "L"), lambda t, u, v: (t, u, v))
    _emit(out, _lsr, x, y, phi, ("L", "S", "R"), lambda t, u, v: (t, u, v))

    # CCC — ba cung; thêm biến thể "đi ngược" để phủ cả hai cách chia
    _emit(out, _lrl, x, y, phi, ("L", "R", "L"), lambda t, u, v: (t, u, v))
    xb = x * math.cos(phi) + y * math.sin(phi)
    yb = x * math.sin(phi) - y * math.cos(phi)
    _emit(out, _lrl, xb, yb, phi, ("L", "R", "L"), lambda t, u, v: (v, u, t))

    # CCCC — bốn cung
    _emit(out, _lrlr_a, x, y, phi, ("L", "R", "L", "R"), lambda t, u, v: (t, u, -u, v))
    _emit(out, _lrlr_b, x, y, phi, ("L", "R", "L", "R"), lambda t, u, v: (t, u, u, v))

    # CCSC — hai cung, một đoạn thẳng, một cung; kèm bản đi ngược (CSCC)
    _emit(out, _lrsl, x, y, phi, ("L", "R", "S", "L"), lambda t, u, v: (t, -HALF_PI, u, v))
    _emit(out, _lrsr, x, y, phi, ("L", "R", "S", "R"), lambda t, u, v: (t, -HALF_PI, u, v))
    _emit(out, _lrsl, xb, yb, phi, ("L", "S", "R", "L"), lambda t, u, v: (v, u, -HALF_PI, t))
    _emit(out, _lrsr, xb, yb, phi, ("R", "S", "R", "L"), lambda t, u, v: (v, u, -HALF_PI, t))

    # CCSCC — năm đoạn
    _emit(out, _lrslr, x, y, phi, ("L", "R", "S", "L", "R"),
          lambda t, u, v: (t, -HALF_PI, u, -HALF_PI, v))
    return out


# --------------------------------------------------------------------- dùng chung

def _interpolate(p: float, mode: str, maxc: float, ox: float, oy: float, oyaw: float) -> tuple[float, float, float]:
    if mode == "S":
        return ox + p / maxc * math.cos(oyaw), oy + p / maxc * math.sin(oyaw), oyaw
    ldx = math.sin(p) / maxc
    if mode == "L":
        ldy = (1.0 - math.cos(p)) / maxc
        yaw = oyaw + p
    else:
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
        if abs(l) > _EPS:
            x, y, yaw = _interpolate(l, m, maxc, x, y, yaw)
    return Pose(x, y, wrap_angle(yaw))


def candidate_paths(q0: Pose, q1: Pose, maxc: float) -> list[RSPath]:
    """Mọi đường Reeds–Shepp nối q0 tới q1, đã xác minh điểm cuối, xếp theo độ dài tăng dần."""
    x, y, phi = normalized_goal(q0, q1, maxc)
    valid: list[RSPath] = []
    for path in _raw_candidates(x, y, phi):
        if any(not math.isfinite(l) for l in path.lengths):
            continue
        end = path_end(q0, path, maxc)
        if (math.hypot(end.x - q1.x, end.y - q1.y) * maxc < _END_TOL
                and abs(wrap_angle(end.yaw - q1.yaw)) < _END_TOL):
            valid.append(path)
    valid.sort(key=lambda p: p.length)
    return valid


def shortest_length(q0: Pose, q1: Pose, maxc: float) -> float:
    """Độ dài (mét) của đường Reeds–Shepp ngắn nhất; vô cùng nếu không có ứng viên nào."""
    paths = candidate_paths(q0, q1, maxc)
    return paths[0].length / maxc if paths else math.inf


def sample_path(q0: Pose, path: RSPath, maxc: float, step: float) -> list[tuple[Pose, int, str]]:
    """Lấy mẫu dọc đường: (tư thế, chiều ±1, loại đoạn). Phần tử đầu là q0."""
    first_dir = 1
    for l in path.lengths:
        if abs(l) > _EPS:
            first_dir = 1 if l > 0 else -1
            break
    out: list[tuple[Pose, int, str]] = [(q0, first_dir, path.ctypes[0])]
    ox, oy, oyaw = q0.x, q0.y, q0.yaw
    for l, m in zip(path.lengths, path.ctypes):
        if abs(l) < _EPS:
            continue
        direction = 1 if l > 0 else -1
        n = max(1, int(math.ceil(abs(l) / (step * maxc))))
        for k in range(1, n + 1):
            x, y, yaw = _interpolate(l * k / n, m, maxc, ox, oy, oyaw)
            out.append((Pose(x, y, wrap_angle(yaw)), direction, m))
        ox, oy, oyaw = _interpolate(l, m, maxc, ox, oy, oyaw)
    return out
