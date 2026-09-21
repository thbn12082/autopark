"""Reeds–Shepp ĐẦY ĐỦ (CSC, CCC, CCCC, CCSC, CCSCC) cho ứng viên "hai chiều".

File riêng của ứng viên `cand_bidirectional`; không đụng tới
`autopark/planning/reeds_shepp.py` (bản rút gọn chỉ có 16/48 biến thể).

Chuẩn hóa theo bán kính quay nhỏ nhất = 1: mọi tọa độ nhân với `maxc = 1/R_min`.
Đoạn 'L'/'R' là cung quay trái/phải, độ dài bằng góc quay; 'S' là đoạn thẳng.
Độ dài âm nghĩa là chạy lùi. Công thức 8.1–8.11 của Reeds & Shepp (1990), cách
tổ chức phép đối xứng (timeflip / reflect / backwards) theo OMPL.

Đường có tới 5 đoạn nên `RSPath.lengths` là tuple độ dài BẤT KỲ, khác bản rút gọn
luôn có đúng 3 đoạn. Mọi ứng viên đều được kiểm tra điểm cuối bằng tích phân
trước khi trả về: một công thức sai chỉ làm mất ứng viên, không tạo đường sai.
"""
from __future__ import annotations

import math
from typing import NamedTuple

from autopark.domain.types import Pose, wrap_angle

TWO_PI = 2.0 * math.pi
_ZERO = -1e-9          # dung sai cho các ràng buộc dấu
_END_TOL = 1e-6

_sin = math.sin
_cos = math.cos
_atan2 = math.atan2
_sqrt = math.sqrt
_hypot = math.hypot
_acos = math.acos
_asin = math.asin
_fmod = math.fmod
_PI = math.pi
_HALF_PI = 0.5 * math.pi


def mod2pi(x: float) -> float:
    """Đưa về (-pi, pi] giữ quy ước fmod của công thức gốc."""
    v = _fmod(x, TWO_PI)
    if v < -_PI:
        v += TWO_PI
    elif v > _PI:
        v -= TWO_PI
    return v


def _polar(x: float, y: float) -> tuple[float, float]:
    return _hypot(x, y), _atan2(y, x)


class RSPath(NamedTuple):
    """Dùng NamedTuple chứ không phải dataclass: mỗi lần gọi sinh ~20 ứng viên,
    trong vòng trong chi phí khởi tạo đối tượng đo được là đáng kể."""

    lengths: tuple[float, ...]     # chuẩn hóa, có dấu
    ctypes: tuple[str, ...]        # 'L', 'S', 'R'

    @property
    def length(self) -> float:
        return sum(abs(v) for v in self.lengths)

    @property
    def n_cusps(self) -> int:
        signs = [v for v in self.lengths if abs(v) > 1e-12]
        return sum(1 for a, b in zip(signs, signs[1:]) if a * b < 0)


# ------------------------------------------------------------------ công thức

def _lsl(x: float, y: float, phi: float):
    """Công thức 8.1: L+ S+ L+."""
    u, t = _polar(x - _sin(phi), y - 1.0 + _cos(phi))
    if t >= _ZERO:
        v = mod2pi(phi - t)
        if v >= _ZERO:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lsr(x: float, y: float, phi: float):
    """Công thức 8.2: L+ S+ R+."""
    u1, t1 = _polar(x + _sin(phi), y - 1.0 - _cos(phi))
    u1 = u1 * u1
    if u1 >= 4.0:
        u = _sqrt(u1 - 4.0)
        theta = _atan2(2.0, u)
        t = mod2pi(t1 + theta)
        v = mod2pi(t - phi)
        if t >= _ZERO and v >= _ZERO:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lrl(x: float, y: float, phi: float):
    """Công thức 8.6/8.7: L+ R- L+."""
    u1, t1 = _polar(x - _sin(phi), y - 1.0 + _cos(phi))
    if u1 <= 4.0:
        u = -2.0 * _asin(0.25 * u1)
        t = mod2pi(t1 + 0.5 * u + _PI)
        v = mod2pi(phi - t + u)
        if t >= _ZERO and u <= -_ZERO:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _tau_omega(u: float, v: float, xi: float, eta: float, phi: float) -> tuple[float, float]:
    delta = mod2pi(u - v)
    A = _sin(u) - _sin(delta)
    B = _cos(u) - _cos(delta) - 1.0
    t1 = _atan2(eta * A - xi * B, xi * A + eta * B)
    t2 = 2.0 * (_cos(delta) - _cos(v) - _cos(u)) + 3.0
    tau = mod2pi(t1 + _PI) if t2 < 0.0 else mod2pi(t1)
    omega = mod2pi(tau - u + v - phi)
    return tau, omega


def _lrlr_a(x: float, y: float, phi: float):
    """Công thức 8.7: L+ R+u L-u R-."""
    xi = x + _sin(phi)
    eta = y - 1.0 - _cos(phi)
    rho = 0.25 * (2.0 + _hypot(xi, eta))
    if rho <= 1.0:
        u = _acos(rho)
        t, v = _tau_omega(u, -u, xi, eta, phi)
        if t >= _ZERO and v <= -_ZERO:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lrlr_b(x: float, y: float, phi: float):
    """Công thức 8.8: L+ R-u L-u R+."""
    xi = x + _sin(phi)
    eta = y - 1.0 - _cos(phi)
    rho = (20.0 - xi * xi - eta * eta) / 16.0
    if 0.0 <= rho <= 1.0:
        u = -_acos(rho)
        if u >= -_HALF_PI:
            t, v = _tau_omega(u, u, xi, eta, phi)
            if t >= _ZERO and v >= _ZERO:
                return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lrsl(x: float, y: float, phi: float):
    """Công thức 8.9: L+ R- S- L-."""
    xi = x - _sin(phi)
    eta = y - 1.0 + _cos(phi)
    rho, theta = _polar(xi, eta)
    if rho >= 2.0:
        r = _sqrt(rho * rho - 4.0)
        u = 2.0 - r
        t = mod2pi(theta + _atan2(r, -2.0))
        v = mod2pi(phi - _HALF_PI - t)
        if t >= _ZERO and u <= -_ZERO and v <= -_ZERO:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lrsr(x: float, y: float, phi: float):
    """Công thức 8.10: L+ R- S- R-."""
    xi = x + _sin(phi)
    eta = y - 1.0 - _cos(phi)
    rho, theta = _polar(-eta, xi)
    if rho >= 2.0:
        t = theta
        u = 2.0 - rho
        v = mod2pi(t + _HALF_PI - phi)
        if t >= _ZERO and u <= -_ZERO and v <= -_ZERO:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lrslr(x: float, y: float, phi: float):
    """Công thức 8.11: L+ R- S- L- R+."""
    xi = x + _sin(phi)
    eta = y - 1.0 - _cos(phi)
    rho, _ = _polar(xi, eta)
    if rho >= 2.0:
        u = 4.0 - _sqrt(rho * rho - 4.0)
        if u <= -_ZERO:
            t = mod2pi(_atan2((4.0 - u) * xi - 2.0 * eta, -2.0 * xi + (u - 4.0) * eta))
            v = mod2pi(t - phi)
            if t >= _ZERO and v >= _ZERO:
                return True, t, u, v
    return False, 0.0, 0.0, 0.0


# ------------------------------------------------------ sinh toàn bộ ứng viên

_LSL = ("L", "S", "L")
_RSR = ("R", "S", "R")
_LSR = ("L", "S", "R")
_RSL = ("R", "S", "L")
_LRL = ("L", "R", "L")
_RLR = ("R", "L", "R")
_LRLR = ("L", "R", "L", "R")
_RLRL = ("R", "L", "R", "L")
_LRSL = ("L", "R", "S", "L")
_RLSR = ("R", "L", "S", "R")
_LRSR = ("L", "R", "S", "R")
_RLSL = ("R", "L", "S", "L")
_LSRL = ("L", "S", "R", "L")
_RSLR = ("R", "S", "L", "R")
_RSRL = ("R", "S", "R", "L")
_LSLR = ("L", "S", "L", "R")
_LRSLR = ("L", "R", "S", "L", "R")
_RLSRL = ("R", "L", "S", "R", "L")


def raw_candidates(x: float, y: float, phi: float) -> list[RSPath]:
    """Toàn bộ họ đường Reeds–Shepp (chuẩn hóa) từ gốc tới (x, y, phi)."""
    out: list[RSPath] = []
    ap = out.append

    # ---- CSC (8)
    ok, t, u, v = _lsl(x, y, phi)
    if ok:
        ap(RSPath((t, u, v), _LSL))
    ok, t, u, v = _lsl(-x, y, -phi)
    if ok:
        ap(RSPath((-t, -u, -v), _LSL))
    ok, t, u, v = _lsl(x, -y, -phi)
    if ok:
        ap(RSPath((t, u, v), _RSR))
    ok, t, u, v = _lsl(-x, -y, phi)
    if ok:
        ap(RSPath((-t, -u, -v), _RSR))
    ok, t, u, v = _lsr(x, y, phi)
    if ok:
        ap(RSPath((t, u, v), _LSR))
    ok, t, u, v = _lsr(-x, y, -phi)
    if ok:
        ap(RSPath((-t, -u, -v), _LSR))
    ok, t, u, v = _lsr(x, -y, -phi)
    if ok:
        ap(RSPath((t, u, v), _RSL))
    ok, t, u, v = _lsr(-x, -y, phi)
    if ok:
        ap(RSPath((-t, -u, -v), _RSL))

    cphi, sphi = _cos(phi), _sin(phi)
    xb = x * cphi + y * sphi
    yb = x * sphi - y * cphi

    # ---- CCC (8)
    ok, t, u, v = _lrl(x, y, phi)
    if ok:
        ap(RSPath((t, u, v), _LRL))
    ok, t, u, v = _lrl(-x, y, -phi)
    if ok:
        ap(RSPath((-t, -u, -v), _LRL))
    ok, t, u, v = _lrl(x, -y, -phi)
    if ok:
        ap(RSPath((t, u, v), _RLR))
    ok, t, u, v = _lrl(-x, -y, phi)
    if ok:
        ap(RSPath((-t, -u, -v), _RLR))
    ok, t, u, v = _lrl(xb, yb, phi)
    if ok:
        ap(RSPath((v, u, t), _LRL))
    ok, t, u, v = _lrl(-xb, yb, -phi)
    if ok:
        ap(RSPath((-v, -u, -t), _LRL))
    ok, t, u, v = _lrl(xb, -yb, -phi)
    if ok:
        ap(RSPath((v, u, t), _RLR))
    ok, t, u, v = _lrl(-xb, -yb, phi)
    if ok:
        ap(RSPath((-v, -u, -t), _RLR))

    # ---- CCCC (8)
    ok, t, u, v = _lrlr_a(x, y, phi)
    if ok:
        ap(RSPath((t, u, -u, v), _LRLR))
    ok, t, u, v = _lrlr_a(-x, y, -phi)
    if ok:
        ap(RSPath((-t, -u, u, -v), _LRLR))
    ok, t, u, v = _lrlr_a(x, -y, -phi)
    if ok:
        ap(RSPath((t, u, -u, v), _RLRL))
    ok, t, u, v = _lrlr_a(-x, -y, phi)
    if ok:
        ap(RSPath((-t, -u, u, -v), _RLRL))
    ok, t, u, v = _lrlr_b(x, y, phi)
    if ok:
        ap(RSPath((t, u, u, v), _LRLR))
    ok, t, u, v = _lrlr_b(-x, y, -phi)
    if ok:
        ap(RSPath((-t, -u, -u, -v), _LRLR))
    ok, t, u, v = _lrlr_b(x, -y, -phi)
    if ok:
        ap(RSPath((t, u, u, v), _RLRL))
    ok, t, u, v = _lrlr_b(-x, -y, phi)
    if ok:
        ap(RSPath((-t, -u, -u, -v), _RLRL))

    # ---- CCSC (16)
    ok, t, u, v = _lrsl(x, y, phi)
    if ok:
        ap(RSPath((t, -_HALF_PI, u, v), _LRSL))
    ok, t, u, v = _lrsl(-x, y, -phi)
    if ok:
        ap(RSPath((-t, _HALF_PI, -u, -v), _LRSL))
    ok, t, u, v = _lrsl(x, -y, -phi)
    if ok:
        ap(RSPath((t, -_HALF_PI, u, v), _RLSR))
    ok, t, u, v = _lrsl(-x, -y, phi)
    if ok:
        ap(RSPath((-t, _HALF_PI, -u, -v), _RLSR))

    ok, t, u, v = _lrsr(x, y, phi)
    if ok:
        ap(RSPath((t, -_HALF_PI, u, v), _LRSR))
    ok, t, u, v = _lrsr(-x, y, -phi)
    if ok:
        ap(RSPath((-t, _HALF_PI, -u, -v), _LRSR))
    ok, t, u, v = _lrsr(x, -y, -phi)
    if ok:
        ap(RSPath((t, -_HALF_PI, u, v), _RLSL))
    ok, t, u, v = _lrsr(-x, -y, phi)
    if ok:
        ap(RSPath((-t, _HALF_PI, -u, -v), _RLSL))

    ok, t, u, v = _lrsl(xb, yb, phi)
    if ok:
        ap(RSPath((v, u, -_HALF_PI, t), _LSRL))
    ok, t, u, v = _lrsl(-xb, yb, -phi)
    if ok:
        ap(RSPath((-v, -u, _HALF_PI, -t), _LSRL))
    ok, t, u, v = _lrsl(xb, -yb, -phi)
    if ok:
        ap(RSPath((v, u, -_HALF_PI, t), _RSLR))
    ok, t, u, v = _lrsl(-xb, -yb, phi)
    if ok:
        ap(RSPath((-v, -u, _HALF_PI, -t), _RSLR))

    ok, t, u, v = _lrsr(xb, yb, phi)
    if ok:
        ap(RSPath((v, u, -_HALF_PI, t), _RSRL))
    ok, t, u, v = _lrsr(-xb, yb, -phi)
    if ok:
        ap(RSPath((-v, -u, _HALF_PI, -t), _RSRL))
    ok, t, u, v = _lrsr(xb, -yb, -phi)
    if ok:
        ap(RSPath((v, u, -_HALF_PI, t), _LSLR))
    ok, t, u, v = _lrsr(-xb, -yb, phi)
    if ok:
        ap(RSPath((-v, -u, _HALF_PI, -t), _LSLR))

    # ---- CCSCC (4)
    ok, t, u, v = _lrslr(x, y, phi)
    if ok:
        ap(RSPath((t, -_HALF_PI, u, -_HALF_PI, v), _LRSLR))
    ok, t, u, v = _lrslr(-x, y, -phi)
    if ok:
        ap(RSPath((-t, _HALF_PI, -u, _HALF_PI, -v), _LRSLR))
    ok, t, u, v = _lrslr(x, -y, -phi)
    if ok:
        ap(RSPath((t, -_HALF_PI, u, -_HALF_PI, v), _RLSRL))
    ok, t, u, v = _lrslr(-x, -y, phi)
    if ok:
        ap(RSPath((-t, _HALF_PI, -u, _HALF_PI, -v), _RLSRL))

    return out


def min_normalized_length(x: float, y: float, phi: float) -> float:
    """Độ dài (chuẩn hóa) nhỏ nhất trong các họ, KHÔNG dựng đối tượng đường.

    Chỉ dùng làm heuristic nên không cần biết đường nào, chỉ cần con số; bỏ hẳn
    việc cấp phát ~20 `RSPath` mỗi lần gọi. Một ứng viên sai công thức chỉ có thể
    làm ước lượng NHỎ đi, tức là vẫn không vượt quá chi phí thật.
    """
    best = math.inf
    cphi, sphi = _cos(phi), _sin(phi)
    xb = x * cphi + y * sphi
    yb = x * sphi - y * cphi
    args4 = ((x, y, phi), (-x, y, -phi), (x, -y, -phi), (-x, -y, phi))
    argsb = ((xb, yb, phi), (-xb, yb, -phi), (xb, -yb, -phi), (-xb, -yb, phi))

    for fn in (_lsl, _lsr, _lrl):
        for a, b, c in args4:
            ok, t, u, v = fn(a, b, c)
            if ok:
                s = abs(t) + abs(u) + abs(v)
                if s < best:
                    best = s
    for a, b, c in argsb:                       # CCC chạy ngược
        ok, t, u, v = _lrl(a, b, c)
        if ok:
            s = abs(t) + abs(u) + abs(v)
            if s < best:
                best = s
    for fn in (_lrlr_a, _lrlr_b):               # CCCC: đoạn giữa đi hai lần
        for a, b, c in args4:
            ok, t, u, v = fn(a, b, c)
            if ok:
                s = abs(t) + 2.0 * abs(u) + abs(v)
                if s < best:
                    best = s
    for fn in (_lrsl, _lrsr):                   # CCSC: có một cung 90° cố định
        for a, b, c in args4:
            ok, t, u, v = fn(a, b, c)
            if ok:
                s = abs(t) + _HALF_PI + abs(u) + abs(v)
                if s < best:
                    best = s
        for a, b, c in argsb:
            ok, t, u, v = fn(a, b, c)
            if ok:
                s = abs(t) + _HALF_PI + abs(u) + abs(v)
                if s < best:
                    best = s
    for a, b, c in args4:                       # CCSCC: hai cung 90°
        ok, t, u, v = _lrslr(a, b, c)
        if ok:
            s = abs(t) + _PI + abs(u) + abs(v)
            if s < best:
                best = s
    return best


# ------------------------------------------------------------------ hình học

def interpolate(p: float, mode: str, maxc: float, ox: float, oy: float, oyaw: float):
    """Tư thế sau khi đi quãng có dấu `p` (chuẩn hóa) trên đoạn `mode`."""
    if mode == "S":
        d = p / maxc
        return ox + d * _cos(oyaw), oy + d * _sin(oyaw), oyaw
    ldx = _sin(p) / maxc
    if mode == "L":
        ldy = (1.0 - _cos(p)) / maxc
        yaw = oyaw + p
    else:
        ldy = -(1.0 - _cos(p)) / maxc
        yaw = oyaw - p
    c, s = _cos(oyaw), _sin(oyaw)
    return ox + c * ldx - s * ldy, oy + s * ldx + c * ldy, yaw


def normalized_goal(q0: Pose, q1: Pose, maxc: float) -> tuple[float, float, float]:
    dx, dy = q1.x - q0.x, q1.y - q0.y
    c, s = _cos(q0.yaw), _sin(q0.yaw)
    return (c * dx + s * dy) * maxc, (-s * dx + c * dy) * maxc, wrap_angle(q1.yaw - q0.yaw)


def path_end(q0: Pose, path: RSPath, maxc: float) -> Pose:
    x, y, yaw = q0.x, q0.y, q0.yaw
    for l, m in zip(path.lengths, path.ctypes):
        if abs(l) > 1e-12:
            x, y, yaw = interpolate(l, m, maxc, x, y, yaw)
    return Pose(x, y, wrap_angle(yaw))


def candidate_paths(q0: Pose, q1: Pose, maxc: float) -> list[RSPath]:
    """Các đường RS từ q0 tới q1 đã kiểm tra điểm cuối, xếp theo độ dài tăng dần."""
    x, y, phi = normalized_goal(q0, q1, maxc)
    valid: list[RSPath] = []
    for path in raw_candidates(x, y, phi):
        end = path_end(q0, path, maxc)
        if (_hypot(end.x - q1.x, end.y - q1.y) * maxc < _END_TOL
                and abs(wrap_angle(end.yaw - q1.yaw)) < _END_TOL):
            valid.append(path)
    valid.sort(key=lambda p: p.length)
    return valid


def shortest_length(q0: Pose, q1: Pose, maxc: float) -> float:
    """Độ dài (m) đường RS ngắn nhất đã kiểm tra; inf nếu không có."""
    paths = candidate_paths(q0, q1, maxc)
    return paths[0].length / maxc if paths else math.inf


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
            x, y, yaw = interpolate(l * k / n, m, maxc, ox, oy, oyaw)
            out.append((Pose(x, y, wrap_angle(yaw)), direction, m))
        ox, oy, oyaw = interpolate(l, m, maxc, ox, oy, oyaw)
    return out
