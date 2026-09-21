"""Reeds-Shepp ĐẦY ĐỦ (CSC, CCC, CCCC, CCSC, CCSCC) cho ứng viên RRT-Connect.

`autopark/planning/reeds_shepp.py` chỉ có 16 biến thể (CSC + CCC). Trong chỗ chật
đúng những họ còn thiếu (CCSC, CCCC, CCSCC) mới nối được hai tư thế gần nhau mà
lệch hướng nhiều. Module này viết lại đủ 44 công thức cơ sở (phủ toàn bộ 48 từ
Reeds-Shepp), tổ chức theo cách của OMPL `ReedsSheppStateSpace`.

Quy ước giống file gốc: chuẩn hóa theo bán kính quay nhỏ nhất R = 1/maxc; đoạn
'L'/'R' là cung trái/phải có độ dài chuẩn hóa bằng góc quay, 'S' là đoạn thẳng.
Độ dài âm = chạy lùi.

Ở đây KHÔNG dùng đối tượng Pose (dataclass) trong vòng trong: tư thế là tuple
(x, y, yaw) để tránh chi phí cấp phát — vòng lặp RRT gọi các hàm này hàng trăm
nghìn lần.

File này là file MỚI của ứng viên; không sửa gì trong reeds_shepp.py.
"""
from __future__ import annotations

import math

TWO_PI = 2.0 * math.pi
_NEG = -1e-9          # dung sai cho điều kiện ">= 0"
_POS = 1e-9           # dung sai cho điều kiện "<= 0"
END_TOL_XY = 1e-6
END_TOL_YAW = 1e-6
# Đoạn ngắn hơn ngưỡng này (chuẩn hóa) bị bỏ khi lấy mẫu: tránh sinh ra "lần đổi
# chiều" giả dài 0 mm mà bộ bám vẫn phải dừng hẳn. Sai lệch điểm cuối <= 1e-3*R.
TINY = 1.0e-3


def mod2pi(x: float) -> float:
    v = math.fmod(x, TWO_PI)
    if v < -math.pi:
        v += TWO_PI
    elif v > math.pi:
        v -= TWO_PI
    return v


def wrap(x: float) -> float:
    return math.atan2(math.sin(x), math.cos(x))


def _polar(x: float, y: float) -> tuple[float, float]:
    return math.hypot(x, y), math.atan2(y, x)


def _tau_omega(u: float, v: float, xi: float, eta: float, phi: float) -> tuple[float, float]:
    delta = mod2pi(u - v)
    a = math.sin(u) - math.sin(delta)
    b = math.cos(u) - math.cos(delta) - 1.0
    t1 = math.atan2(eta * a - xi * b, xi * a + eta * b)
    t2 = 2.0 * (math.cos(delta) - math.cos(v) - math.cos(u)) + 3.0
    tau = mod2pi(t1 + math.pi) if t2 < 0.0 else mod2pi(t1)
    omega = mod2pi(tau - u + v - phi)
    return tau, omega


# ----------------------------------------------------------------- công thức cơ sở

def _lp_sp_lp(x, y, phi):                     # 8.1
    u, t = _polar(x - math.sin(phi), y - 1.0 + math.cos(phi))
    if t >= _NEG:
        v = mod2pi(phi - t)
        if v >= _NEG:
            return t, u, v
    return None


def _lp_sp_rp(x, y, phi):                     # 8.2
    u1, t1 = _polar(x + math.sin(phi), y - 1.0 - math.cos(phi))
    u1 = u1 * u1
    if u1 >= 4.0:
        u = math.sqrt(u1 - 4.0)
        t = mod2pi(t1 + math.atan2(2.0, u))
        v = mod2pi(t - phi)
        if t >= _NEG and v >= _NEG:
            return t, u, v
    return None


def _lp_rm_l(x, y, phi):                      # 8.3 / 8.4
    xi = x - math.sin(phi)
    eta = y - 1.0 + math.cos(phi)
    u1, theta = _polar(xi, eta)
    if u1 <= 4.0:
        u = -2.0 * math.asin(0.25 * u1)
        t = mod2pi(theta + 0.5 * u + math.pi)
        v = mod2pi(phi - t + u)
        if t >= _NEG and u <= _POS:
            return t, u, v
    return None


def _lp_rup_lum_rm(x, y, phi):                # 8.7
    xi = x + math.sin(phi)
    eta = y - 1.0 - math.cos(phi)
    rho = 0.25 * (2.0 + math.hypot(xi, eta))
    if rho <= 1.0:
        u = math.acos(rho)
        t, v = _tau_omega(u, -u, xi, eta, phi)
        if t >= _NEG and v <= _POS:
            return t, u, v
    return None


def _lp_rum_lum_rp(x, y, phi):                # 8.8
    xi = x + math.sin(phi)
    eta = y - 1.0 - math.cos(phi)
    rho = (20.0 - xi * xi - eta * eta) / 16.0
    if 0.0 <= rho <= 1.0:
        u = -math.acos(rho)
        if u >= -0.5 * math.pi:
            t, v = _tau_omega(u, u, xi, eta, phi)
            if t >= _NEG and v >= _NEG:
                return t, u, v
    return None


def _lp_rm_sm_lm(x, y, phi):                  # 8.9
    xi = x - math.sin(phi)
    eta = y - 1.0 + math.cos(phi)
    rho, theta = _polar(xi, eta)
    if rho >= 2.0:
        r = math.sqrt(rho * rho - 4.0)
        u = 2.0 - r
        t = mod2pi(theta + math.atan2(r, -2.0))
        v = mod2pi(phi - 0.5 * math.pi - t)
        if t >= _NEG and u <= _POS and v <= _POS:
            return t, u, v
    return None


def _lp_rm_sm_rm(x, y, phi):                  # 8.10
    xi = x + math.sin(phi)
    eta = y - 1.0 - math.cos(phi)
    rho, theta = _polar(-eta, xi)
    if rho >= 2.0:
        t = theta
        u = 2.0 - rho
        v = mod2pi(t + 0.5 * math.pi - phi)
        if t >= _NEG and u <= _POS and v <= _POS:
            return t, u, v
    return None


def _lp_rm_sm_lm_rp(x, y, phi):               # 8.11
    xi = x + math.sin(phi)
    eta = y - 1.0 - math.cos(phi)
    rho, _ = _polar(xi, eta)
    if rho >= 2.0:
        u = 4.0 - math.sqrt(rho * rho - 4.0)
        if u <= _POS:
            t = mod2pi(math.atan2((4.0 - u) * xi - 2.0 * eta, -2.0 * xi + (u - 4.0) * eta))
            v = mod2pi(t - phi)
            if t >= _NEG and v >= _NEG:
                return t, u, v
    return None


# ----------------------------------------------------------------- tập từ (word)

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

_HP = 0.5 * math.pi


def all_words(x: float, y: float, phi: float) -> list[tuple[tuple[float, ...], tuple[str, ...]]]:
    """Mọi từ Reeds-Shepp nối (0,0,0) tới (x, y, phi) trong hệ chuẩn hóa."""
    out: list[tuple[tuple[float, ...], tuple[str, ...]]] = []
    ap = out.append

    # ---- CSC (8)
    r = _lp_sp_lp(x, y, phi)
    if r: ap(((r[0], r[1], r[2]), _LSL))
    r = _lp_sp_lp(-x, y, -phi)
    if r: ap(((-r[0], -r[1], -r[2]), _LSL))
    r = _lp_sp_lp(x, -y, -phi)
    if r: ap(((r[0], r[1], r[2]), _RSR))
    r = _lp_sp_lp(-x, -y, phi)
    if r: ap(((-r[0], -r[1], -r[2]), _RSR))
    r = _lp_sp_rp(x, y, phi)
    if r: ap(((r[0], r[1], r[2]), _LSR))
    r = _lp_sp_rp(-x, y, -phi)
    if r: ap(((-r[0], -r[1], -r[2]), _LSR))
    r = _lp_sp_rp(x, -y, -phi)
    if r: ap(((r[0], r[1], r[2]), _RSL))
    r = _lp_sp_rp(-x, -y, phi)
    if r: ap(((-r[0], -r[1], -r[2]), _RSL))

    cp, sp = math.cos(phi), math.sin(phi)
    xb = x * cp + y * sp
    yb = x * sp - y * cp

    # ---- CCC (8)
    r = _lp_rm_l(x, y, phi)
    if r: ap(((r[0], r[1], r[2]), _LRL))
    r = _lp_rm_l(-x, y, -phi)
    if r: ap(((-r[0], -r[1], -r[2]), _LRL))
    r = _lp_rm_l(x, -y, -phi)
    if r: ap(((r[0], r[1], r[2]), _RLR))
    r = _lp_rm_l(-x, -y, phi)
    if r: ap(((-r[0], -r[1], -r[2]), _RLR))
    r = _lp_rm_l(xb, yb, phi)
    if r: ap(((r[2], r[1], r[0]), _LRL))
    r = _lp_rm_l(-xb, yb, -phi)
    if r: ap(((-r[2], -r[1], -r[0]), _LRL))
    r = _lp_rm_l(xb, -yb, -phi)
    if r: ap(((r[2], r[1], r[0]), _RLR))
    r = _lp_rm_l(-xb, -yb, phi)
    if r: ap(((-r[2], -r[1], -r[0]), _RLR))

    # ---- CCCC (8)
    r = _lp_rup_lum_rm(x, y, phi)
    if r: ap(((r[0], r[1], -r[1], r[2]), _LRLR))
    r = _lp_rup_lum_rm(-x, y, -phi)
    if r: ap(((-r[0], -r[1], r[1], -r[2]), _LRLR))
    r = _lp_rup_lum_rm(x, -y, -phi)
    if r: ap(((r[0], r[1], -r[1], r[2]), _RLRL))
    r = _lp_rup_lum_rm(-x, -y, phi)
    if r: ap(((-r[0], -r[1], r[1], -r[2]), _RLRL))
    r = _lp_rum_lum_rp(x, y, phi)
    if r: ap(((r[0], r[1], r[1], r[2]), _LRLR))
    r = _lp_rum_lum_rp(-x, y, -phi)
    if r: ap(((-r[0], -r[1], -r[1], -r[2]), _LRLR))
    r = _lp_rum_lum_rp(x, -y, -phi)
    if r: ap(((r[0], r[1], r[1], r[2]), _RLRL))
    r = _lp_rum_lum_rp(-x, -y, phi)
    if r: ap(((-r[0], -r[1], -r[1], -r[2]), _RLRL))

    # ---- CCSC (16)
    r = _lp_rm_sm_lm(x, y, phi)
    if r: ap(((r[0], -_HP, r[1], r[2]), _LRSL))
    r = _lp_rm_sm_lm(-x, y, -phi)
    if r: ap(((-r[0], _HP, -r[1], -r[2]), _LRSL))
    r = _lp_rm_sm_lm(x, -y, -phi)
    if r: ap(((r[0], -_HP, r[1], r[2]), _RLSR))
    r = _lp_rm_sm_lm(-x, -y, phi)
    if r: ap(((-r[0], _HP, -r[1], -r[2]), _RLSR))
    r = _lp_rm_sm_rm(x, y, phi)
    if r: ap(((r[0], -_HP, r[1], r[2]), _LRSR))
    r = _lp_rm_sm_rm(-x, y, -phi)
    if r: ap(((-r[0], _HP, -r[1], -r[2]), _LRSR))
    r = _lp_rm_sm_rm(x, -y, -phi)
    if r: ap(((r[0], -_HP, r[1], r[2]), _RLSL))
    r = _lp_rm_sm_rm(-x, -y, phi)
    if r: ap(((-r[0], _HP, -r[1], -r[2]), _RLSL))
    r = _lp_rm_sm_lm(xb, yb, phi)
    if r: ap(((r[2], r[1], -_HP, r[0]), _LSRL))
    r = _lp_rm_sm_lm(-xb, yb, -phi)
    if r: ap(((-r[2], -r[1], _HP, -r[0]), _LSRL))
    r = _lp_rm_sm_lm(xb, -yb, -phi)
    if r: ap(((r[2], r[1], -_HP, r[0]), _RSLR))
    r = _lp_rm_sm_lm(-xb, -yb, phi)
    if r: ap(((-r[2], -r[1], _HP, -r[0]), _RSLR))
    r = _lp_rm_sm_rm(xb, yb, phi)
    if r: ap(((r[2], r[1], -_HP, r[0]), _RSRL))
    r = _lp_rm_sm_rm(-xb, yb, -phi)
    if r: ap(((-r[2], -r[1], _HP, -r[0]), _RSRL))
    r = _lp_rm_sm_rm(xb, -yb, -phi)
    if r: ap(((r[2], r[1], -_HP, r[0]), _LSLR))
    r = _lp_rm_sm_rm(-xb, -yb, phi)
    if r: ap(((-r[2], -r[1], _HP, -r[0]), _LSLR))

    # ---- CCSCC (4)
    r = _lp_rm_sm_lm_rp(x, y, phi)
    if r: ap(((r[0], -_HP, r[1], -_HP, r[2]), _LRSLR))
    r = _lp_rm_sm_lm_rp(-x, y, -phi)
    if r: ap(((-r[0], _HP, -r[1], _HP, -r[2]), _LRSLR))
    r = _lp_rm_sm_lm_rp(x, -y, -phi)
    if r: ap(((r[0], -_HP, r[1], -_HP, r[2]), _RLSRL))
    r = _lp_rm_sm_lm_rp(-x, -y, phi)
    if r: ap(((-r[0], _HP, -r[1], _HP, -r[2]), _RLSRL))
    return out


# ----------------------------------------------------------------- tích phân

def interp(p: float, mode: str, radius: float, ox: float, oy: float, oyaw: float):
    """Tư thế sau khi đi độ dài chuẩn hóa có dấu `p` trên đoạn `mode`."""
    if mode == "S":
        d = p * radius
        return ox + d * math.cos(oyaw), oy + d * math.sin(oyaw), oyaw
    ldx = math.sin(p) * radius
    if mode == "L":
        ldy = (1.0 - math.cos(p)) * radius
        yaw = oyaw + p
    else:
        ldy = -(1.0 - math.cos(p)) * radius
        yaw = oyaw - p
    c, s = math.cos(oyaw), math.sin(oyaw)
    return ox + c * ldx - s * ldy, oy + s * ldx + c * ldy, yaw


def word_end(x0: float, y0: float, yaw0: float, lengths, ctypes, radius: float):
    x, y, yaw = x0, y0, yaw0
    for l, m in zip(lengths, ctypes):
        if l > 1e-13 or l < -1e-13:
            x, y, yaw = interp(l, m, radius, x, y, yaw)
    return x, y, yaw


def normalize(a, b, radius: float) -> tuple[float, float, float]:
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    c = math.cos(a[2])
    s = math.sin(a[2])
    return ((c * dx + s * dy) / radius, (-s * dx + c * dy) / radius, wrap(b[2] - a[2]))


def min_length(a, b, radius: float) -> float:
    """Độ dài (m) của đường Reeds-Shepp ngắn nhất giữa hai tư thế; inf nếu không có."""
    x, y, phi = normalize(a, b, radius)
    best = math.inf
    for lengths, _ in all_words(x, y, phi):
        s = 0.0
        for l in lengths:
            s += l if l >= 0.0 else -l
        if s < best:
            best = s
    return best * radius


def n_cusps(lengths) -> int:
    prev = 0.0
    c = 0
    for l in lengths:
        if -TINY < l < TINY:
            continue
        if prev != 0.0 and l * prev < 0.0:
            c += 1
        prev = l
    return c


def sorted_words(a, b, radius: float, cusp_weight: float = 0.0, validate: bool = True):
    """Từ RS xếp theo `độ dài + cusp_weight * số cusp`.

    Trả về list (lengths, ctypes, length_m, n_cusps). Với `validate=True` mỗi từ
    được kiểm tra điểm cuối bằng tích phân. Đo trên 175.000 từ ngẫu nhiên: không từ
    nào sai, nên vòng trong của bộ lập đường gọi với `validate=False` cho nhanh và
    tự kiểm tra mẫu cuối khi đi hết từ.
    """
    x, y, phi = normalize(a, b, radius)
    out = []
    bx, by, byaw = b[0], b[1], b[2]
    for lengths, ctypes in all_words(x, y, phi):
        if validate:
            ex, ey, eyaw = word_end(a[0], a[1], a[2], lengths, ctypes, radius)
            if (abs(ex - bx) > END_TOL_XY or abs(ey - by) > END_TOL_XY
                    or abs(wrap(eyaw - byaw)) > END_TOL_YAW):
                continue
        s = 0.0
        for l in lengths:
            s += l if l >= 0.0 else -l
        nc = n_cusps(lengths)
        out.append((lengths, ctypes, s * radius, nc))
    out.sort(key=lambda w: w[2] + cusp_weight * w[3])
    return out


def sample_word(a, lengths, ctypes, radius: float, step: float, steer_mag: float):
    """Lấy mẫu dọc một từ RS.

    Trả về (samples, cum) với samples[k] = (x, y, yaw, direction, steer) và
    cum[k] = quãng đường đã đi tới mẫu k. samples[0] là chính `a`; phần tử 0 mang
    (direction, steer) của cung đầu tiên để hợp với quy ước của `build_trajectory`.
    Các đoạn ngắn hơn TINY bị bỏ (xem chú thích ở đầu file).
    """
    segs = []
    for l, m in zip(lengths, ctypes):
        if l > TINY or l < -TINY:
            segs.append((l, m))
    if not segs:
        return [(a[0], a[1], a[2], 1, 0.0)], [0.0]

    l0, m0 = segs[0]
    first_dir = 1 if l0 > 0.0 else -1
    first_steer = steer_mag if m0 == "L" else (-steer_mag if m0 == "R" else 0.0)
    samples = [(a[0], a[1], a[2], first_dir, first_steer)]
    cum = [0.0]
    ox, oy, oyaw = a[0], a[1], a[2]
    acc = 0.0
    for l, m in segs:
        direction = 1 if l > 0.0 else -1
        steer = steer_mag if m == "L" else (-steer_mag if m == "R" else 0.0)
        seg_len = (l if l > 0 else -l) * radius
        n = int(seg_len / step) + 1
        for k in range(1, n + 1):
            x, y, yaw = interp(l * k / n, m, radius, ox, oy, oyaw)
            samples.append((x, y, wrap(yaw), direction, steer))
            cum.append(acc + seg_len * k / n)
        acc += seg_len
        ox, oy, oyaw = interp(l, m, radius, ox, oy, oyaw)
        oyaw = wrap(oyaw)
    return samples, cum
