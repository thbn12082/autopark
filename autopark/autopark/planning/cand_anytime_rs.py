"""Reeds–Shepp đầy đủ (44 từ đường) cho ứng viên `cand_anytime`.

File này TỰ CHỨA: không phụ thuộc `autopark.planning.reeds_shepp` (chỉ 16 từ,
thiếu CCCC/CCSC/CCSCC) cũng không phụ thuộc bất kỳ file nào của ứng viên khác.

Chuẩn hoá theo bán kính quay nhỏ nhất bằng 1: mọi toạ độ nhân `maxc = 1/R_min`.
Đoạn 'L'/'R' là cung trái/phải, độ dài bằng góc quay; 'S' là đoạn thẳng. Độ dài
âm nghĩa là chạy lùi.

Công thức theo Reeds & Shepp (1990) mục 8.1–8.11 cùng ba phép đối xứng (đảo thời
gian, gương, đi ngược). Mỗi ứng viên dùng để NỐI ĐƯỜNG đều được tích phân lại và
chỉ giữ khi điểm cuối khớp, nên công thức chép sai chỉ làm mất ứng viên chứ không
sinh đường sai. Riêng hàm heuristic `shortest_length_fast` bỏ qua bước xác minh:
ở đó một công thức sai chỉ làm heuristic NHỎ đi (vẫn là cận dưới hợp lệ), không
làm hỏng tính đúng đắn.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from autopark.domain.types import Pose, wrap_angle

TWO_PI = 2.0 * math.pi
HALF_PI = 0.5 * math.pi
_END_TOL = 1e-6
_EPS = 1e-12

_sin = math.sin
_cos = math.cos
_atan2 = math.atan2
_hypot = math.hypot
_sqrt = math.sqrt
_acos = math.acos
_asin = math.asin
_fmod = math.fmod


def mod2pi(x: float) -> float:
    """Đưa góc về (-pi, pi], giữ đúng quy ước của công thức gốc."""
    v = _fmod(x, TWO_PI)
    if v < -math.pi:
        v += TWO_PI
    elif v > math.pi:
        v -= TWO_PI
    return v


@dataclass(frozen=True)
class RSPath:
    lengths: tuple[float, ...]
    ctypes: tuple[str, ...]

    @property
    def length(self) -> float:
        return sum(abs(v) for v in self.lengths)

    @property
    def n_cusps(self) -> int:
        signs = [v for v in self.lengths if abs(v) > _EPS]
        return sum(1 for a, b in zip(signs, signs[1:]) if a * b < 0)


# ------------------------------------------------------------------ công thức gốc

def _lsl(x, y, phi):
    """8.1  L+ S+ L+"""
    dx = x - _sin(phi)
    dy = y - 1.0 + _cos(phi)
    u = _hypot(dx, dy)
    t = _atan2(dy, dx)
    if t >= 0.0:
        v = mod2pi(phi - t)
        if v >= 0.0:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lsr(x, y, phi):
    """8.2  L+ S+ R+"""
    dx = x + _sin(phi)
    dy = y - 1.0 - _cos(phi)
    u1 = dx * dx + dy * dy
    if u1 >= 4.0:
        t1 = _atan2(dy, dx)
        u = _sqrt(u1 - 4.0)
        t = mod2pi(t1 + _atan2(2.0, u))
        v = mod2pi(t - phi)
        if t >= 0.0 and v >= 0.0:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lrl(x, y, phi):
    """8.3 / 8.4  L+ R- L+"""
    dx = x - _sin(phi)
    dy = y - 1.0 + _cos(phi)
    u1 = _hypot(dx, dy)
    if u1 <= 4.0:
        t1 = _atan2(dy, dx)
        u = -2.0 * _asin(0.25 * u1)
        t = mod2pi(t1 + 0.5 * u + math.pi)
        v = mod2pi(phi - t + u)
        if t >= 0.0 and u <= 0.0:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _tau_omega(u, v, xi, eta, phi):
    delta = mod2pi(u - v)
    A = _sin(u) - _sin(delta)
    B = _cos(u) - _cos(delta) - 1.0
    t1 = _atan2(eta * A - xi * B, xi * A + eta * B)
    t2 = 2.0 * (_cos(delta) - _cos(v) - _cos(u)) + 3.0
    tau = mod2pi(t1 + math.pi) if t2 < 0.0 else mod2pi(t1)
    return tau, mod2pi(tau - u + v - phi)


def _lrlr_a(x, y, phi):
    """8.7  L+ R+ L- R-"""
    xi = x + _sin(phi)
    eta = y - 1.0 - _cos(phi)
    rho = 0.25 * (2.0 + _hypot(xi, eta))
    if rho <= 1.0:
        u = _acos(rho)
        t, v = _tau_omega(u, -u, xi, eta, phi)
        if t >= 0.0 and v <= 0.0:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lrlr_b(x, y, phi):
    """8.8  L+ R- L- R+"""
    xi = x + _sin(phi)
    eta = y - 1.0 - _cos(phi)
    rho = (20.0 - xi * xi - eta * eta) / 16.0
    if 0.0 <= rho <= 1.0:
        u = -_acos(rho)
        if u >= -HALF_PI:
            t, v = _tau_omega(u, u, xi, eta, phi)
            if t >= 0.0 and v >= 0.0:
                return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lrsl(x, y, phi):
    """8.9  L+ R-(90°) S- L-"""
    xi = x - _sin(phi)
    eta = y - 1.0 + _cos(phi)
    rho = _hypot(xi, eta)
    if rho >= 2.0:
        theta = _atan2(eta, xi)
        r = _sqrt(rho * rho - 4.0)
        u = 2.0 - r
        t = mod2pi(theta + _atan2(r, -2.0))
        v = mod2pi(phi - HALF_PI - t)
        if t >= 0.0 and u <= 0.0 and v <= 0.0:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lrsr(x, y, phi):
    """8.10  L+ R-(90°) S- R-"""
    xi = x + _sin(phi)
    eta = y - 1.0 - _cos(phi)
    rho = _hypot(-eta, xi)
    if rho >= 2.0:
        t = _atan2(xi, -eta)
        u = 2.0 - rho
        v = mod2pi(t + HALF_PI - phi)
        if t >= 0.0 and u <= 0.0 and v <= 0.0:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lrslr(x, y, phi):
    """8.11  L+ R-(90°) S- L-(90°) R+"""
    xi = x + _sin(phi)
    eta = y - 1.0 - _cos(phi)
    rho = _hypot(xi, eta)
    if rho >= 2.0:
        u = 4.0 - _sqrt(rho * rho - 4.0)
        if u <= 0.0:
            t = mod2pi(_atan2((4.0 - u) * xi - 2.0 * eta, -2.0 * xi + (u - 4.0) * eta))
            v = mod2pi(t - phi)
            if t >= 0.0 and v >= 0.0:
                return True, t, u, v
    return False, 0.0, 0.0, 0.0


# ------------------------------------------------------------------ sinh đủ từ đường

_FLIP = {"L": "R", "R": "L", "S": "S"}
_LSL = ("L", "S", "L")
_LSR = ("L", "S", "R")
_LRL = ("L", "R", "L")
_LRLR = ("L", "R", "L", "R")
_LRSL = ("L", "R", "S", "L")
_LRSR = ("L", "R", "S", "R")
_LSRL = ("L", "S", "R", "L")
_RSRL = ("R", "S", "R", "L")
_LRSLR = ("L", "R", "S", "L", "R")


def _mirror(types):
    return tuple(_FLIP[c] for c in types)


_M = {t: _mirror(t) for t in (_LSL, _LSR, _LRL, _LRLR, _LRSL, _LRSR, _LSRL, _RSRL, _LRSLR)}


def _emit(out, base, x, y, phi, types, build):
    """Bốn phép đối xứng của một công thức gốc: gốc, đảo thời gian, gương, cả hai."""
    mtypes = _M[types]
    flag, t, u, v = base(x, y, phi)
    if flag:
        out.append((build(t, u, v), types))
    flag, t, u, v = base(-x, y, -phi)
    if flag:
        out.append((build(-t, -u, -v) if build is _b3 else tuple(-l for l in build(t, u, v)), types))
    flag, t, u, v = base(x, -y, -phi)
    if flag:
        out.append((build(t, u, v), mtypes))
    flag, t, u, v = base(-x, -y, phi)
    if flag:
        out.append((build(-t, -u, -v) if build is _b3 else tuple(-l for l in build(t, u, v)), mtypes))


def _b3(t, u, v):
    return (t, u, v)


def _b3r(t, u, v):
    return (v, u, t)


def _b4a(t, u, v):
    return (t, u, -u, v)


def _b4b(t, u, v):
    return (t, u, u, v)


def _b4c(t, u, v):
    return (t, -HALF_PI, u, v)


def _b4d(t, u, v):
    return (v, u, -HALF_PI, t)


def _b5(t, u, v):
    return (t, -HALF_PI, u, -HALF_PI, v)


def raw_candidates(x: float, y: float, phi: float) -> list[tuple[tuple[float, ...], tuple[str, ...]]]:
    out: list[tuple[tuple[float, ...], tuple[str, ...]]] = []
    cp, sp = _cos(phi), _sin(phi)
    xb = x * cp + y * sp
    yb = x * sp - y * cp

    _emit(out, _lsl, x, y, phi, _LSL, _b3)          # CSC
    _emit(out, _lsr, x, y, phi, _LSR, _b3)
    _emit(out, _lrl, x, y, phi, _LRL, _b3)          # CCC
    _emit(out, _lrl, xb, yb, phi, _LRL, _b3r)
    _emit(out, _lrlr_a, x, y, phi, _LRLR, _b4a)     # CCCC
    _emit(out, _lrlr_b, x, y, phi, _LRLR, _b4b)
    _emit(out, _lrsl, x, y, phi, _LRSL, _b4c)       # CCSC
    _emit(out, _lrsr, x, y, phi, _LRSR, _b4c)
    _emit(out, _lrsl, xb, yb, phi, _LSRL, _b4d)     # CSCC (đi ngược)
    _emit(out, _lrsr, xb, yb, phi, _RSRL, _b4d)
    _emit(out, _lrslr, x, y, phi, _LRSLR, _b5)      # CCSCC
    return out


# ------------------------------------------------------------------ dùng chung

def _interpolate(p, mode, maxc, ox, oy, oyaw):
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
        if abs(l) > _EPS:
            x, y, yaw = _interpolate(l, m, maxc, x, y, yaw)
    return Pose(x, y, wrap_angle(yaw))


def candidate_paths(q0: Pose, q1: Pose, maxc: float) -> list[RSPath]:
    """Mọi đường RS nối q0 tới q1, ĐÃ xác minh điểm cuối, xếp theo độ dài tăng dần."""
    x, y, phi = normalized_goal(q0, q1, maxc)
    raw = raw_candidates(x, y, phi)
    raw.sort(key=lambda item: sum(abs(v) for v in item[0]))
    valid: list[RSPath] = []
    for lengths, types in raw:
        ok = True
        for l in lengths:
            if not (l == l and -1e12 < l < 1e12):   # loại NaN/inf
                ok = False
                break
        if not ok:
            continue
        path = RSPath(lengths, types)
        end = path_end(q0, path, maxc)
        if (_hypot(end.x - q1.x, end.y - q1.y) * maxc < _END_TOL
                and abs(wrap_angle(end.yaw - q1.yaw)) < _END_TOL):
            valid.append(path)
    return valid


def shortest_length_fast(x: float, y: float, phi: float) -> float:
    """Độ dài (chuẩn hoá) ngắn nhất, KHÔNG dựng tuple và KHÔNG xác minh điểm cuối.

    Đây là hàm heuristic, chạy hàng chục nghìn lần, nên viết phẳng: mỗi công thức
    gốc được gọi bốn lần (bốn phép đối xứng) và chỉ cộng trị tuyệt đối.
    Nếu một công thức sai thì con số chỉ NHỎ đi — heuristic vẫn là cận dưới hợp
    lệ, không phá tính đúng của tìm kiếm.
    """
    best = math.inf
    cp, sp = _cos(phi), _sin(phi)
    xb = x * cp + y * sp
    yb = x * sp - y * cp

    # 3 đoạn: CSC và CCC
    for f, ax, ay, ap in ((_lsl, x, y, phi), (_lsr, x, y, phi),
                          (_lrl, x, y, phi), (_lrl, xb, yb, phi)):
        for sx, sy, sph in ((ax, ay, ap), (-ax, ay, -ap), (ax, -ay, -ap), (-ax, -ay, ap)):
            ok, t, u, v = f(sx, sy, sph)
            if ok:
                s = (t if t >= 0 else -t) + (u if u >= 0 else -u) + (v if v >= 0 else -v)
                if s < best:
                    best = s
    # 4 cung: CCCC (đoạn giữa nhân đôi)
    for f in (_lrlr_a, _lrlr_b):
        for sx, sy, sph in ((x, y, phi), (-x, y, -phi), (x, -y, -phi), (-x, -y, phi)):
            ok, t, u, v = f(sx, sy, sph)
            if ok:
                s = (t if t >= 0 else -t) + 2.0 * (u if u >= 0 else -u) + (v if v >= 0 else -v)
                if s < best:
                    best = s
    # CCSC: thêm một cung 90° cố định
    for f, ax, ay in ((_lrsl, x, y), (_lrsr, x, y), (_lrsl, xb, yb), (_lrsr, xb, yb)):
        for sx, sy, sph in ((ax, ay, phi), (-ax, ay, -phi), (ax, -ay, -phi), (-ax, -ay, phi)):
            ok, t, u, v = f(sx, sy, sph)
            if ok:
                s = HALF_PI + (t if t >= 0 else -t) + (u if u >= 0 else -u) + (v if v >= 0 else -v)
                if s < best:
                    best = s
    # CCSCC: hai cung 90° cố định
    for sx, sy, sph in ((x, y, phi), (-x, y, -phi), (x, -y, -phi), (-x, -y, phi)):
        ok, t, u, v = _lrslr(sx, sy, sph)
        if ok:
            s = math.pi + (t if t >= 0 else -t) + (u if u >= 0 else -u) + (v if v >= 0 else -v)
            if s < best:
                best = s
    return best


def shortest_length(q0: Pose, q1: Pose, maxc: float) -> float:
    """Độ dài (mét) đường RS ngắn nhất đã xác minh; inf nếu không có ứng viên."""
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
