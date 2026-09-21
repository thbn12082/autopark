"""Reeds-Shepp ĐẦY ĐỦ (48 từ đường) cho ứng viên `cand_hybrid_fast`.

Bản rút gọn `autopark/planning/reeds_shepp.py` chỉ có hai họ CSC và CCC (16 từ).
Ở đây có đủ chín công thức gốc của Reeds & Shepp (1990), mục 8.1-8.11:

    CSC     LpSpLp, LpSpRp
    CCC     LpRmL                       (thêm biến thể "đi ngược")
    CCCC    LpRupLumRm, LpRumLumRp
    CCSC    LpRmSmLm, LpRmSmRm          (thêm biến thể "đi ngược")
    CCSCC   LpRmSLmRp

Ba phép đối xứng (đảo thời gian, đối xứng gương, đi ngược) nhân chín công thức
này lên thành 44 phép thử phủ kín 48 từ đường.

MỌI ứng viên trả cho bộ lập đường đều được tích phân lại tới điểm cuối và chỉ
giữ khi sai số dưới ngưỡng, đúng như `reeds_shepp.py` đang làm: một công thức
chép sai chỉ làm mất ứng viên chứ không sinh ra đường sai.

Ngoài phiên bản vô hướng, file có thêm `length_grid()`: cùng công thức nhưng
viết theo mảng numpy, dùng để dựng sẵn BẢNG TRA heuristic phi holonomic không
vật cản cho toàn sa bàn (thay cho việc gọi lại Reeds-Shepp ở từng nút).

Chuẩn hoá: bán kính quay nhỏ nhất = 1, mọi toạ độ nhân `maxc = 1/R_min`.
Độ dài đoạn mang dấu; âm nghĩa là chạy lùi.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from autopark.domain.types import Pose, wrap_angle

TWO_PI = 2.0 * math.pi
PI = math.pi
HALF_PI = 0.5 * math.pi
_ZERO = -1e-9          # dung sai cho các bất đẳng thức của công thức gốc
_END_TOL = 2e-5        # sai số điểm cuối (đơn vị chuẩn hoá) chấp nhận được


def mod2pi(x: float) -> float:
    """Đưa góc về (-pi, pi] theo đúng quy ước công thức gốc."""
    v = math.fmod(x, TWO_PI)
    if v < -PI:
        v += TWO_PI
    elif v > PI:
        v -= TWO_PI
    return v


def _polar(x: float, y: float) -> tuple[float, float]:
    return math.hypot(x, y), math.atan2(y, x)


# --------------------------------------------------------------------------- kiểu

_WORDS: dict[int, str] = {
    0: "LRL", 1: "RLR",
    2: "LRLR", 3: "RLRL",
    4: "LRSL", 5: "RLSR",
    6: "LSRL", 7: "RSLR",
    8: "LRSR", 9: "RLSL",
    10: "RSRL", 11: "LSLR",
    12: "LSR", 13: "RSL",
    14: "LSL", 15: "RSR",
    16: "LRSLR", 17: "RLSRL",
}


@dataclass(frozen=True)
class RSPath:
    lengths: tuple[float, ...]     # chuẩn hoá, mang dấu
    ctypes: tuple[str, ...]        # 'L', 'S', 'R'

    @property
    def length(self) -> float:
        return sum(abs(v) for v in self.lengths)

    @property
    def n_cusps(self) -> int:
        signs = [v for v in self.lengths if abs(v) > 1e-12]
        return sum(1 for a, b in zip(signs, signs[1:]) if a * b < 0)

    @property
    def word(self) -> str:
        return "".join(f"{m}{'+' if v > 0 else '-'}" for v, m in zip(self.lengths, self.ctypes)
                       if abs(v) > 1e-12)


# --------------------------------------------------------------------------- công thức gốc (vô hướng)

def _tau_omega(u: float, v: float, xi: float, eta: float, phi: float) -> tuple[float, float]:
    delta = mod2pi(u - v)
    A = math.sin(u) - math.sin(delta)
    B = math.cos(u) - math.cos(delta) - 1.0
    t1 = math.atan2(eta * A - xi * B, xi * A + eta * B)
    t2 = 2.0 * (math.cos(delta) - math.cos(v) - math.cos(u)) + 3.0
    tau = mod2pi(t1 + PI) if t2 < 0 else mod2pi(t1)
    omega = mod2pi(tau - u + v - phi)
    return tau, omega


def _lp_sp_lp(x: float, y: float, phi: float):
    """8.1  L+ S+ L+"""
    u, t = _polar(x - math.sin(phi), y - 1.0 + math.cos(phi))
    if t >= _ZERO:
        v = mod2pi(phi - t)
        if v >= _ZERO:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lp_sp_rp(x: float, y: float, phi: float):
    """8.2  L+ S+ R+"""
    u1, t1 = _polar(x + math.sin(phi), y - 1.0 - math.cos(phi))
    u1 = u1 * u1
    if u1 >= 4.0:
        u = math.sqrt(u1 - 4.0)
        theta = math.atan2(2.0, u)
        t = mod2pi(t1 + theta)
        v = mod2pi(t - phi)
        if t >= _ZERO and v >= _ZERO:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lp_rm_l(x: float, y: float, phi: float):
    """8.3/8.4  L+ R- L"""
    xi = x - math.sin(phi)
    eta = y - 1.0 + math.cos(phi)
    u1, theta = _polar(xi, eta)
    if u1 <= 4.0:
        u = -2.0 * math.asin(min(1.0, max(-1.0, 0.25 * u1)))
        t = mod2pi(theta + 0.5 * u + PI)
        v = mod2pi(phi - t + u)
        if t >= _ZERO and u <= -_ZERO:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lp_rup_lum_rm(x: float, y: float, phi: float):
    """8.7  L+ R+ L- R-"""
    xi = x + math.sin(phi)
    eta = y - 1.0 - math.cos(phi)
    rho = 0.25 * (2.0 + math.hypot(xi, eta))
    if rho <= 1.0:
        u = math.acos(rho)
        t, v = _tau_omega(u, -u, xi, eta, phi)
        if t >= _ZERO and v <= -_ZERO:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lp_rum_lum_rp(x: float, y: float, phi: float):
    """8.8  L+ R- L- R+"""
    xi = x + math.sin(phi)
    eta = y - 1.0 - math.cos(phi)
    rho = (20.0 - xi * xi - eta * eta) / 16.0
    if 0.0 <= rho <= 1.0:
        u = -math.acos(rho)
        if u >= -HALF_PI:
            t, v = _tau_omega(u, u, xi, eta, phi)
            if t >= _ZERO and v >= _ZERO:
                return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lp_rm_sm_lm(x: float, y: float, phi: float):
    """8.9  L+ R- S- L-"""
    xi = x - math.sin(phi)
    eta = y - 1.0 + math.cos(phi)
    rho, theta = _polar(xi, eta)
    if rho >= 2.0:
        r = math.sqrt(rho * rho - 4.0)
        u = 2.0 - r
        t = mod2pi(theta + math.atan2(r, -2.0))
        v = mod2pi(phi - HALF_PI - t)
        if t >= _ZERO and u <= -_ZERO and v <= -_ZERO:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lp_rm_sm_rm(x: float, y: float, phi: float):
    """8.10  L+ R- S- R-"""
    xi = x + math.sin(phi)
    eta = y - 1.0 - math.cos(phi)
    rho, theta = _polar(-eta, xi)
    if rho >= 2.0:
        t = theta
        u = 2.0 - rho
        v = mod2pi(t + HALF_PI - phi)
        if t >= _ZERO and u <= -_ZERO and v <= -_ZERO:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lp_rm_s_lm_rp(x: float, y: float, phi: float):
    """8.11  L+ R- S- L- R+"""
    xi = x + math.sin(phi)
    eta = y - 1.0 - math.cos(phi)
    rho, _ = _polar(xi, eta)
    if rho >= 2.0:
        u = 4.0 - math.sqrt(rho * rho - 4.0)
        if u <= -_ZERO:
            t = mod2pi(math.atan2((4.0 - u) * xi - 2.0 * eta, -2.0 * xi + (u - 4.0) * eta))
            v = mod2pi(t - phi)
            if t >= _ZERO and v >= _ZERO:
                return True, t, u, v
    return False, 0.0, 0.0, 0.0


# --------------------------------------------------------------------------- sinh ứng viên

def raw_candidates(x: float, y: float, phi: float) -> list[RSPath]:
    """44 phép thử (phủ 48 từ đường) cho tư thế đích đã chuẩn hoá."""
    out: list[RSPath] = []

    def add(res, tid: int, make):
        flag, t, u, v = res
        if flag:
            out.append(RSPath(tuple(make(t, u, v)), tuple(_WORDS[tid])))

    xb = x * math.cos(phi) + y * math.sin(phi)
    yb = x * math.sin(phi) - y * math.cos(phi)

    # ---- CSC (8.1, 8.2)
    f = _lp_sp_lp
    add(f(x, y, phi), 14, lambda t, u, v: (t, u, v))
    add(f(-x, y, -phi), 14, lambda t, u, v: (-t, -u, -v))
    add(f(x, -y, -phi), 15, lambda t, u, v: (t, u, v))
    add(f(-x, -y, phi), 15, lambda t, u, v: (-t, -u, -v))
    f = _lp_sp_rp
    add(f(x, y, phi), 12, lambda t, u, v: (t, u, v))
    add(f(-x, y, -phi), 12, lambda t, u, v: (-t, -u, -v))
    add(f(x, -y, -phi), 13, lambda t, u, v: (t, u, v))
    add(f(-x, -y, phi), 13, lambda t, u, v: (-t, -u, -v))

    # ---- CCC (8.3, 8.4) và biến thể đi ngược
    f = _lp_rm_l
    add(f(x, y, phi), 0, lambda t, u, v: (t, u, v))
    add(f(-x, y, -phi), 0, lambda t, u, v: (-t, -u, -v))
    add(f(x, -y, -phi), 1, lambda t, u, v: (t, u, v))
    add(f(-x, -y, phi), 1, lambda t, u, v: (-t, -u, -v))
    add(f(xb, yb, phi), 0, lambda t, u, v: (v, u, t))
    add(f(-xb, yb, -phi), 0, lambda t, u, v: (-v, -u, -t))
    add(f(xb, -yb, -phi), 1, lambda t, u, v: (v, u, t))
    add(f(-xb, -yb, phi), 1, lambda t, u, v: (-v, -u, -t))

    # ---- CCCC (8.7, 8.8)
    f = _lp_rup_lum_rm
    add(f(x, y, phi), 2, lambda t, u, v: (t, u, -u, v))
    add(f(-x, y, -phi), 2, lambda t, u, v: (-t, -u, u, -v))
    add(f(x, -y, -phi), 3, lambda t, u, v: (t, u, -u, v))
    add(f(-x, -y, phi), 3, lambda t, u, v: (-t, -u, u, -v))
    f = _lp_rum_lum_rp
    add(f(x, y, phi), 2, lambda t, u, v: (t, u, u, v))
    add(f(-x, y, -phi), 2, lambda t, u, v: (-t, -u, -u, -v))
    add(f(x, -y, -phi), 3, lambda t, u, v: (t, u, u, v))
    add(f(-x, -y, phi), 3, lambda t, u, v: (-t, -u, -u, -v))

    # ---- CCSC (8.9, 8.10) và biến thể đi ngược
    f = _lp_rm_sm_lm
    add(f(x, y, phi), 4, lambda t, u, v: (t, -HALF_PI, u, v))
    add(f(-x, y, -phi), 4, lambda t, u, v: (-t, HALF_PI, -u, -v))
    add(f(x, -y, -phi), 5, lambda t, u, v: (t, -HALF_PI, u, v))
    add(f(-x, -y, phi), 5, lambda t, u, v: (-t, HALF_PI, -u, -v))
    f = _lp_rm_sm_rm
    add(f(x, y, phi), 8, lambda t, u, v: (t, -HALF_PI, u, v))
    add(f(-x, y, -phi), 8, lambda t, u, v: (-t, HALF_PI, -u, -v))
    add(f(x, -y, -phi), 9, lambda t, u, v: (t, -HALF_PI, u, v))
    add(f(-x, -y, phi), 9, lambda t, u, v: (-t, HALF_PI, -u, -v))
    f = _lp_rm_sm_lm
    add(f(xb, yb, phi), 6, lambda t, u, v: (v, u, -HALF_PI, t))
    add(f(-xb, yb, -phi), 6, lambda t, u, v: (-v, -u, HALF_PI, -t))
    add(f(xb, -yb, -phi), 7, lambda t, u, v: (v, u, -HALF_PI, t))
    add(f(-xb, -yb, phi), 7, lambda t, u, v: (-v, -u, HALF_PI, -t))
    f = _lp_rm_sm_rm
    add(f(xb, yb, phi), 10, lambda t, u, v: (v, u, -HALF_PI, t))
    add(f(-xb, yb, -phi), 10, lambda t, u, v: (-v, -u, HALF_PI, -t))
    add(f(xb, -yb, -phi), 11, lambda t, u, v: (v, u, -HALF_PI, t))
    add(f(-xb, -yb, phi), 11, lambda t, u, v: (-v, -u, HALF_PI, -t))

    # ---- CCSCC (8.11)
    f = _lp_rm_s_lm_rp
    add(f(x, y, phi), 16, lambda t, u, v: (t, -HALF_PI, u, -HALF_PI, v))
    add(f(-x, y, -phi), 16, lambda t, u, v: (-t, HALF_PI, -u, HALF_PI, -v))
    add(f(x, -y, -phi), 17, lambda t, u, v: (t, -HALF_PI, u, -HALF_PI, v))
    add(f(-x, -y, phi), 17, lambda t, u, v: (-t, HALF_PI, -u, HALF_PI, -v))

    return out


# --------------------------------------------------------------------------- hình học

def _interpolate(p: float, mode: str, maxc: float, ox: float, oy: float, oyaw: float):
    if mode == "S":
        d = p / maxc
        return ox + d * math.cos(oyaw), oy + d * math.sin(oyaw), oyaw
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
        if abs(l) > 1e-12:
            x, y, yaw = _interpolate(l, m, maxc, x, y, yaw)
    return Pose(x, y, wrap_angle(yaw))


def verify(q0: Pose, q1: Pose, path: RSPath, maxc: float) -> bool:
    """Tích phân lại tới điểm cuối: chỉ giữ ứng viên thật sự nối được q0 -> q1."""
    end = path_end(q0, path, maxc)
    return (math.hypot(end.x - q1.x, end.y - q1.y) * maxc < _END_TOL
            and abs(wrap_angle(end.yaw - q1.yaw)) < _END_TOL)


def candidate_paths(q0: Pose, q1: Pose, maxc: float, verified: bool = True) -> list[RSPath]:
    """Các đường RS từ q0 tới q1, xếp theo độ dài tăng dần (đã kiểm tra điểm cuối)."""
    x, y, phi = normalized_goal(q0, q1, maxc)
    cands = raw_candidates(x, y, phi)
    if verified:
        cands = [p for p in cands if verify(q0, q1, p, maxc)]
    cands.sort(key=lambda p: p.length)
    return cands


def shortest_length(q0: Pose, q1: Pose, maxc: float) -> float:
    """Độ dài (m) đường RS ngắn nhất; inf nếu không tìm được ứng viên hợp lệ."""
    paths = candidate_paths(q0, q1, maxc)
    if not paths:
        return math.inf
    return paths[0].length / maxc


def sample_path(q0: Pose, path: RSPath, maxc: float, step: float) -> list[tuple[Pose, int, str]]:
    """Lấy mẫu dọc đường: (tư thế, chiều +-1, loại đoạn). Điểm đầu là q0."""
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


# --------------------------------------------------------------------------- bản numpy (chỉ độ dài)
#
# Dùng để dựng BẢNG TRA heuristic. Chỉ cần ĐỘ DÀI nên bỏ được phần dựng đường,
# và ba phép đối xứng không đổi độ dài nên chỉ việc lấy min. Vài rút gọn đại số
# so với bản vô hướng (đã kiểm chứng bằng cách so lại với bản vô hướng):
#   - mod2pi bằng rint thay cho fmod + 2 lần where;
#   - sin/cos của phi tính một lần rồi truyền vào (các phép đối xứng chỉ đổi dấu sin);
#   - trong 8.7 thì delta = 2u và t2 = (2cos u - 1)^2 >= 0, trong 8.8 thì delta = 0
#     và t2 = 5 - 4cos u > 0, nên nhánh "t2 < 0" của tau_omega không bao giờ xảy ra
#     và biểu thức rút gọn còn một arccos + một arctan2.

_INV_TWO_PI = 1.0 / TWO_PI


def _m2p(x):
    return x - TWO_PI * np.rint(x * _INV_TWO_PI)


def _f_lsl(x, y, sp, cp, phi):
    a = x - sp
    b = y - 1.0 + cp
    u = np.sqrt(a * a + b * b)
    t = np.arctan2(b, a)
    v = _m2p(phi - t)
    return np.where((t >= _ZERO) & (v >= _ZERO), np.abs(t) + u + np.abs(v), np.inf)


def _f_lsr(x, y, sp, cp, phi):
    a = x + sp
    b = y - 1.0 - cp
    u1 = a * a + b * b
    t1 = np.arctan2(b, a)
    u = np.sqrt(np.maximum(u1 - 4.0, 0.0))
    t = _m2p(t1 + np.arctan2(2.0, u))
    v = _m2p(t - phi)
    return np.where((u1 >= 4.0) & (t >= _ZERO) & (v >= _ZERO), np.abs(t) + u + np.abs(v), np.inf)


def _f_lrl(x, y, sp, cp, phi):
    xi = x - sp
    eta = y - 1.0 + cp
    u1 = np.sqrt(xi * xi + eta * eta)
    theta = np.arctan2(eta, xi)
    u = -2.0 * np.arcsin(np.minimum(0.25 * u1, 1.0))
    t = _m2p(theta + 0.5 * u + PI)
    v = _m2p(phi - t + u)
    return np.where((u1 <= 4.0) & (t >= _ZERO) & (u <= -_ZERO),
                    np.abs(t) + np.abs(u) + np.abs(v), np.inf)


def _f_cccc_a(x, y, sp, cp, phi):
    """8.7  L+ R+ L- R-  (delta = 2u, t2 = (2cos u - 1)^2 >= 0)."""
    xi = x + sp
    eta = y - 1.0 - cp
    rho = 0.25 * (2.0 + np.sqrt(xi * xi + eta * eta))
    c = np.minimum(rho, 1.0)
    u = np.arccos(c)
    s = np.sqrt(np.maximum(1.0 - c * c, 0.0))
    # A = s(1-2c), B = c(1-2c); 1-2c <= 0 vì c = rho >= 0.5 nên đổi dấu cả hai tử/mẫu
    t = _m2p(np.arctan2(xi * c - eta * s, -xi * s - eta * c))
    v = _m2p(t - 2.0 * u - phi)
    return np.where((rho <= 1.0) & (t >= _ZERO) & (v <= -_ZERO),
                    np.abs(t) + 2.0 * u + np.abs(v), np.inf)


def _f_cccc_b(x, y, sp, cp, phi):
    """8.8  L+ R- L- R+  (delta = 0, t2 = 5 - 4cos u > 0)."""
    xi = x + sp
    eta = y - 1.0 - cp
    rho = (20.0 - xi * xi - eta * eta) / 16.0
    c = np.clip(rho, 0.0, 1.0)
    u = -np.arccos(c)
    s0 = np.sqrt(np.maximum(1.0 - c * c, 0.0))     # = -sin(u)
    B = c - 2.0
    t = _m2p(np.arctan2(-eta * s0 - xi * B, -xi * s0 + eta * B))
    v = _m2p(t - phi)
    return np.where((rho >= 0.0) & (rho <= 1.0) & (u >= -HALF_PI) & (t >= _ZERO) & (v >= _ZERO),
                    np.abs(t) + 2.0 * np.abs(u) + np.abs(v), np.inf)


def _f_ccsc_a(x, y, sp, cp, phi):
    """8.9  L+ R- S- L-"""
    xi = x - sp
    eta = y - 1.0 + cp
    rho2 = xi * xi + eta * eta
    theta = np.arctan2(eta, xi)
    r = np.sqrt(np.maximum(rho2 - 4.0, 0.0))
    u = 2.0 - r
    t = _m2p(theta + np.arctan2(r, -2.0))
    v = _m2p(phi - HALF_PI - t)
    return np.where((rho2 >= 4.0) & (t >= _ZERO) & (u <= -_ZERO) & (v <= -_ZERO),
                    np.abs(t) + HALF_PI + np.abs(u) + np.abs(v), np.inf)


def _f_ccsc_b(x, y, sp, cp, phi):
    """8.10  L+ R- S- R-"""
    xi = x + sp
    eta = y - 1.0 - cp
    rho = np.sqrt(xi * xi + eta * eta)
    t = np.arctan2(xi, -eta)
    u = 2.0 - rho
    v = _m2p(t + HALF_PI - phi)
    return np.where((rho >= 2.0) & (t >= _ZERO) & (u <= -_ZERO) & (v <= -_ZERO),
                    np.abs(t) + HALF_PI + np.abs(u) + np.abs(v), np.inf)


def _f_ccscc(x, y, sp, cp, phi):
    """8.11  L+ R- S- L- R+"""
    xi = x + sp
    eta = y - 1.0 - cp
    rho2 = xi * xi + eta * eta
    u = 4.0 - np.sqrt(np.maximum(rho2 - 4.0, 0.0))
    t = _m2p(np.arctan2((4.0 - u) * xi - 2.0 * eta, -2.0 * xi + (u - 4.0) * eta))
    v = _m2p(t - phi)
    return np.where((rho2 >= 4.0) & (u <= -_ZERO) & (t >= _ZERO) & (v >= _ZERO),
                    np.abs(t) + PI + np.abs(u) + np.abs(v), np.inf)


_NP_ALL = (_f_lsl, _f_lsr, _f_lrl, _f_cccc_a, _f_cccc_b, _f_ccsc_a, _f_ccsc_b, _f_ccscc)
_NP_BACK = (_f_lrl, _f_ccsc_a, _f_ccsc_b)


def length_grid(x, y, phi):
    """Độ dài RS ngắn nhất (đơn vị chuẩn hoá) cho từng phần tử của mảng (x, y, phi).

    Cùng 44 phép thử như bản vô hướng. Trả `inf` ở chỗ không có ứng viên nào
    (trên thực tế không xảy ra: Reeds-Shepp luôn nối được hai tư thế bất kỳ).
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    phi = np.asarray(phi, dtype=np.float64)
    sp = np.sin(phi)
    cp = np.cos(phi)
    nx, ny, nphi, nsp = -x, -y, -phi, -sp
    best = np.full(np.broadcast(x, y, phi).shape, np.inf)
    with np.errstate(invalid="ignore", divide="ignore"):
        for f in _NP_ALL:
            best = np.minimum(best, f(x, y, sp, cp, phi))          # gốc
            best = np.minimum(best, f(nx, y, nsp, cp, nphi))       # đảo thời gian
            best = np.minimum(best, f(x, ny, nsp, cp, nphi))       # đối xứng gương
            best = np.minimum(best, f(nx, ny, sp, cp, phi))        # cả hai
        xb = x * cp + y * sp
        yb = x * sp - y * cp
        nxb, nyb = -xb, -yb
        for f in _NP_BACK:                                          # đi ngược
            best = np.minimum(best, f(xb, yb, sp, cp, phi))
            best = np.minimum(best, f(nxb, yb, nsp, cp, nphi))
            best = np.minimum(best, f(xb, nyb, nsp, cp, nphi))
            best = np.minimum(best, f(nxb, nyb, sp, cp, phi))
    return best
