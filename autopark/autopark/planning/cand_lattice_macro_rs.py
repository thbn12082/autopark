"""Reeds-Shepp ĐẦY ĐỦ (48 họ) dùng riêng cho ứng viên `cand_lattice_macro`.

Bản trong `autopark/planning/reeds_shepp.py` chỉ có CSC và CCC (16/48 họ). Ở chỗ
chật, các họ nối được thường là CCCC, CCSC, CSCC và CCSCC — đúng những họ còn
thiếu. File này viết lại đủ 18 kiểu đường / 48 biến thể theo cách tổ chức của
Reeds & Shepp (1990) (cùng cách sắp xếp phép đối xứng như OMPL).

Quy ước giống `reeds_shepp.py` để dùng lẫn được:
- Chuẩn hóa theo bán kính quay nhỏ nhất = 1: nhân tọa độ với `maxc = 1/R_min`.
- Đoạn 'L' với độ dài có dấu p: Δyaw = +p, chiều chạy = dấu(p).
- Đoạn 'R' với độ dài có dấu p: Δyaw = -p, chiều chạy = dấu(p).
- Đoạn 'S' với độ dài có dấu p: đi thẳng p/maxc, chiều chạy = dấu(p).

Mọi ứng viên đều được kiểm tra điểm cuối bằng tích phân trước khi trả về
(`candidates`), nên một công thức sai chỉ làm mất ứng viên chứ không sinh đường
sai. Hàm `shortest_norm` dùng cho heuristic thì bỏ qua bước kiểm tra đó (ước
lượng thấp hơn thực tế vẫn an toàn cho A*).
"""
from __future__ import annotations

import math

TWO_PI = 2.0 * math.pi
PI = math.pi
HALF_PI = 0.5 * math.pi
ZERO = 1e-9
_END_TOL = 1e-6


def mod2pi(x: float) -> float:
    """Đưa góc về (-pi, pi] giữ quy ước của công thức gốc."""
    v = math.fmod(x, TWO_PI)
    if v < -PI:
        v += TWO_PI
    elif v > PI:
        v -= TWO_PI
    return v


def _polar(x: float, y: float) -> tuple[float, float]:
    return math.hypot(x, y), math.atan2(y, x)


def _tau_omega(u: float, v: float, xi: float, eta: float, phi: float) -> tuple[float, float]:
    delta = mod2pi(u - v)
    A = math.sin(u) - math.sin(delta)
    B = math.cos(u) - math.cos(delta) - 1.0
    t1 = math.atan2(eta * A - xi * B, xi * A + eta * B)
    t2 = 2.0 * (math.cos(delta) - math.cos(v) - math.cos(u)) + 3.0
    tau = mod2pi(t1 + PI) if t2 < 0 else mod2pi(t1)
    omega = mod2pi(tau - u + v - phi)
    return tau, omega


# --------------------------------------------------------------------- CSC

def _lp_sp_lp(x: float, y: float, phi: float):
    u, t = _polar(x - math.sin(phi), y - 1.0 + math.cos(phi))
    if t >= -ZERO:
        v = mod2pi(phi - t)
        if v >= -ZERO:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lp_sp_rp(x: float, y: float, phi: float):
    u1, t1 = _polar(x + math.sin(phi), y - 1.0 - math.cos(phi))
    u1 = u1 * u1
    if u1 >= 4.0:
        u = math.sqrt(u1 - 4.0)
        theta = math.atan2(2.0, u)
        t = mod2pi(t1 + theta)
        v = mod2pi(t - phi)
        if t >= -ZERO and v >= -ZERO:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


# --------------------------------------------------------------------- CCC

def _lp_rm_l(x: float, y: float, phi: float):
    xi = x - math.sin(phi)
    eta = y - 1.0 + math.cos(phi)
    u1, theta = _polar(xi, eta)
    if u1 <= 4.0:
        u = -2.0 * math.asin(0.25 * u1)
        t = mod2pi(theta + 0.5 * u + PI)
        v = mod2pi(phi - t + u)
        if t >= -ZERO and u <= ZERO:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


# --------------------------------------------------------------------- CCCC

def _lp_rup_lum_rm(x: float, y: float, phi: float):
    xi = x + math.sin(phi)
    eta = y - 1.0 - math.cos(phi)
    rho = 0.25 * (2.0 + math.hypot(xi, eta))
    if rho <= 1.0:
        u = math.acos(rho)
        t, v = _tau_omega(u, -u, xi, eta, phi)
        if t >= -ZERO and v <= ZERO:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lp_rum_lum_rp(x: float, y: float, phi: float):
    xi = x + math.sin(phi)
    eta = y - 1.0 - math.cos(phi)
    rho = (20.0 - xi * xi - eta * eta) / 16.0
    if 0.0 <= rho <= 1.0:
        u = -math.acos(rho)
        if u >= -HALF_PI:
            t, v = _tau_omega(u, u, xi, eta, phi)
            if t >= -ZERO and v >= -ZERO:
                return True, t, u, v
    return False, 0.0, 0.0, 0.0


# --------------------------------------------------------------------- CCSC

def _lp_rm_sm_lm(x: float, y: float, phi: float):
    xi = x - math.sin(phi)
    eta = y - 1.0 + math.cos(phi)
    rho, theta = _polar(xi, eta)
    if rho >= 2.0:
        r = math.sqrt(rho * rho - 4.0)
        u = 2.0 - r
        t = mod2pi(theta + math.atan2(r, -2.0))
        v = mod2pi(phi - HALF_PI - t)
        if t >= -ZERO and u <= ZERO and v <= ZERO:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


def _lp_rm_sm_rm(x: float, y: float, phi: float):
    xi = x + math.sin(phi)
    eta = y - 1.0 - math.cos(phi)
    rho, theta = _polar(-eta, xi)
    if rho >= 2.0:
        t = theta
        u = 2.0 - rho
        v = mod2pi(t + HALF_PI - phi)
        if t >= -ZERO and u <= ZERO and v <= ZERO:
            return True, t, u, v
    return False, 0.0, 0.0, 0.0


# --------------------------------------------------------------------- CCSCC

def _lp_rm_s_lm_rp(x: float, y: float, phi: float):
    xi = x + math.sin(phi)
    eta = y - 1.0 - math.cos(phi)
    rho, _theta = _polar(xi, eta)
    if rho >= 2.0:
        u = 4.0 - math.sqrt(rho * rho - 4.0)
        if u <= ZERO:
            t = mod2pi(math.atan2((4.0 - u) * xi - 2.0 * eta, -2.0 * xi + (u - 4.0) * eta))
            v = mod2pi(t - phi)
            if t >= -ZERO and v >= -ZERO:
                return True, t, u, v
    return False, 0.0, 0.0, 0.0


# ------------------------------------------------------------- gom ứng viên

def words(x: float, y: float, phi: float) -> list[tuple[str, tuple[float, ...]]]:
    """Tất cả (kiểu, độ dài có dấu) ứng viên trong hệ chuẩn hóa. Chưa lọc điểm cuối."""
    out: list[tuple[str, tuple[float, ...]]] = []
    app = out.append
    sin_phi, cos_phi = math.sin(phi), math.cos(phi)
    xb = x * cos_phi + y * sin_phi
    yb = x * sin_phi - y * cos_phi

    # ---- CSC (8)
    ok, t, u, v = _lp_sp_lp(x, y, phi)
    if ok:
        app(("LSL", (t, u, v)))
    ok, t, u, v = _lp_sp_lp(-x, y, -phi)
    if ok:
        app(("LSL", (-t, -u, -v)))
    ok, t, u, v = _lp_sp_lp(x, -y, -phi)
    if ok:
        app(("RSR", (t, u, v)))
    ok, t, u, v = _lp_sp_lp(-x, -y, phi)
    if ok:
        app(("RSR", (-t, -u, -v)))
    ok, t, u, v = _lp_sp_rp(x, y, phi)
    if ok:
        app(("LSR", (t, u, v)))
    ok, t, u, v = _lp_sp_rp(-x, y, -phi)
    if ok:
        app(("LSR", (-t, -u, -v)))
    ok, t, u, v = _lp_sp_rp(x, -y, -phi)
    if ok:
        app(("RSL", (t, u, v)))
    ok, t, u, v = _lp_sp_rp(-x, -y, phi)
    if ok:
        app(("RSL", (-t, -u, -v)))

    # ---- CCC (8)
    ok, t, u, v = _lp_rm_l(x, y, phi)
    if ok:
        app(("LRL", (t, u, v)))
    ok, t, u, v = _lp_rm_l(-x, y, -phi)
    if ok:
        app(("LRL", (-t, -u, -v)))
    ok, t, u, v = _lp_rm_l(x, -y, -phi)
    if ok:
        app(("RLR", (t, u, v)))
    ok, t, u, v = _lp_rm_l(-x, -y, phi)
    if ok:
        app(("RLR", (-t, -u, -v)))
    ok, t, u, v = _lp_rm_l(xb, yb, phi)
    if ok:
        app(("LRL", (v, u, t)))
    ok, t, u, v = _lp_rm_l(-xb, yb, -phi)
    if ok:
        app(("LRL", (-v, -u, -t)))
    ok, t, u, v = _lp_rm_l(xb, -yb, -phi)
    if ok:
        app(("RLR", (v, u, t)))
    ok, t, u, v = _lp_rm_l(-xb, -yb, phi)
    if ok:
        app(("RLR", (-v, -u, -t)))

    # ---- CCCC (8)
    ok, t, u, v = _lp_rup_lum_rm(x, y, phi)
    if ok:
        app(("LRLR", (t, u, -u, v)))
    ok, t, u, v = _lp_rup_lum_rm(-x, y, -phi)
    if ok:
        app(("LRLR", (-t, -u, u, -v)))
    ok, t, u, v = _lp_rup_lum_rm(x, -y, -phi)
    if ok:
        app(("RLRL", (t, u, -u, v)))
    ok, t, u, v = _lp_rup_lum_rm(-x, -y, phi)
    if ok:
        app(("RLRL", (-t, -u, u, -v)))
    ok, t, u, v = _lp_rum_lum_rp(x, y, phi)
    if ok:
        app(("LRLR", (t, u, u, v)))
    ok, t, u, v = _lp_rum_lum_rp(-x, y, -phi)
    if ok:
        app(("LRLR", (-t, -u, -u, -v)))
    ok, t, u, v = _lp_rum_lum_rp(x, -y, -phi)
    if ok:
        app(("RLRL", (t, u, u, v)))
    ok, t, u, v = _lp_rum_lum_rp(-x, -y, phi)
    if ok:
        app(("RLRL", (-t, -u, -u, -v)))

    # ---- CCSC (16)
    ok, t, u, v = _lp_rm_sm_lm(x, y, phi)
    if ok:
        app(("LRSL", (t, -HALF_PI, u, v)))
    ok, t, u, v = _lp_rm_sm_lm(-x, y, -phi)
    if ok:
        app(("LRSL", (-t, HALF_PI, -u, -v)))
    ok, t, u, v = _lp_rm_sm_lm(x, -y, -phi)
    if ok:
        app(("RLSR", (t, -HALF_PI, u, v)))
    ok, t, u, v = _lp_rm_sm_lm(-x, -y, phi)
    if ok:
        app(("RLSR", (-t, HALF_PI, -u, -v)))
    ok, t, u, v = _lp_rm_sm_rm(x, y, phi)
    if ok:
        app(("LRSR", (t, -HALF_PI, u, v)))
    ok, t, u, v = _lp_rm_sm_rm(-x, y, -phi)
    if ok:
        app(("LRSR", (-t, HALF_PI, -u, -v)))
    ok, t, u, v = _lp_rm_sm_rm(x, -y, -phi)
    if ok:
        app(("RLSL", (t, -HALF_PI, u, v)))
    ok, t, u, v = _lp_rm_sm_rm(-x, -y, phi)
    if ok:
        app(("RLSL", (-t, HALF_PI, -u, -v)))
    ok, t, u, v = _lp_rm_sm_lm(xb, yb, phi)
    if ok:
        app(("LSRL", (v, u, -HALF_PI, t)))
    ok, t, u, v = _lp_rm_sm_lm(-xb, yb, -phi)
    if ok:
        app(("LSRL", (-v, -u, HALF_PI, -t)))
    ok, t, u, v = _lp_rm_sm_lm(xb, -yb, -phi)
    if ok:
        app(("RSLR", (v, u, -HALF_PI, t)))
    ok, t, u, v = _lp_rm_sm_lm(-xb, -yb, phi)
    if ok:
        app(("RSLR", (-v, -u, HALF_PI, -t)))
    ok, t, u, v = _lp_rm_sm_rm(xb, yb, phi)
    if ok:
        app(("RSRL", (v, u, -HALF_PI, t)))
    ok, t, u, v = _lp_rm_sm_rm(-xb, yb, -phi)
    if ok:
        app(("RSRL", (-v, -u, HALF_PI, -t)))
    ok, t, u, v = _lp_rm_sm_rm(xb, -yb, -phi)
    if ok:
        app(("LSLR", (v, u, -HALF_PI, t)))
    ok, t, u, v = _lp_rm_sm_rm(-xb, -yb, phi)
    if ok:
        app(("LSLR", (-v, -u, HALF_PI, -t)))

    # ---- CCSCC (4)
    ok, t, u, v = _lp_rm_s_lm_rp(x, y, phi)
    if ok:
        app(("LRSLR", (t, -HALF_PI, u, -HALF_PI, v)))
    ok, t, u, v = _lp_rm_s_lm_rp(-x, y, -phi)
    if ok:
        app(("LRSLR", (-t, HALF_PI, -u, HALF_PI, -v)))
    ok, t, u, v = _lp_rm_s_lm_rp(x, -y, -phi)
    if ok:
        app(("RLSRL", (t, -HALF_PI, u, -HALF_PI, v)))
    ok, t, u, v = _lp_rm_s_lm_rp(-x, -y, phi)
    if ok:
        app(("RLSRL", (-t, HALF_PI, -u, HALF_PI, -v)))

    return out


def shortest_norm(x: float, y: float, phi: float) -> float:
    """Độ dài chuẩn hóa của đường RS ngắn nhất (không kiểm tra điểm cuối)."""
    best = math.inf
    for _types, lengths in words(x, y, phi):
        s = 0.0
        for l in lengths:
            s += l if l >= 0.0 else -l
        if s < best:
            best = s
    return best


def shortest_norm_fast(x: float, y: float, phi: float) -> float:
    """Chỉ CSC + CCC (16 họ). Dùng cho heuristic: rẻ hơn ~3 lần, chỉ hơi kém chặt.

    Đây đúng bằng tập họ mà `reeds_shepp.py` gốc có, nên heuristic không tệ hơn
    mốc chuẩn; các họ 4-5 đoạn chỉ dành cho khâu nối đích.
    """
    sin_phi, cos_phi = math.sin(phi), math.cos(phi)
    xb = x * cos_phi + y * sin_phi
    yb = x * sin_phi - y * cos_phi
    best = math.inf
    for fn, args in (
        (_lp_sp_lp, (x, y, phi)), (_lp_sp_lp, (-x, y, -phi)),
        (_lp_sp_lp, (x, -y, -phi)), (_lp_sp_lp, (-x, -y, phi)),
        (_lp_sp_rp, (x, y, phi)), (_lp_sp_rp, (-x, y, -phi)),
        (_lp_sp_rp, (x, -y, -phi)), (_lp_sp_rp, (-x, -y, phi)),
        (_lp_rm_l, (x, y, phi)), (_lp_rm_l, (-x, y, -phi)),
        (_lp_rm_l, (x, -y, -phi)), (_lp_rm_l, (-x, -y, phi)),
        (_lp_rm_l, (xb, yb, phi)), (_lp_rm_l, (-xb, yb, -phi)),
        (_lp_rm_l, (xb, -yb, -phi)), (_lp_rm_l, (-xb, -yb, phi)),
    ):
        ok, t, u, v = fn(*args)
        if ok:
            s = (t if t >= 0 else -t) + (u if u >= 0 else -u) + (v if v >= 0 else -v)
            if s < best:
                best = s
    return best


def normalize(x0: float, y0: float, yaw0: float, x1: float, y1: float, yaw1: float,
              maxc: float) -> tuple[float, float, float]:
    dx, dy = x1 - x0, y1 - y0
    c, s = math.cos(yaw0), math.sin(yaw0)
    return ((c * dx + s * dy) * maxc, (-s * dx + c * dy) * maxc,
            mod2pi(yaw1 - yaw0))


def step_pose(p: float, mode: str, maxc: float, ox: float, oy: float, oyaw: float):
    """Tư thế sau khi đi độ dài có dấu `p` (chuẩn hóa) trên đoạn `mode`."""
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


def path_end(x0: float, y0: float, yaw0: float, types: str, lengths, maxc: float):
    x, y, yaw = x0, y0, yaw0
    for l, m in zip(lengths, types):
        if l > 1e-12 or l < -1e-12:
            x, y, yaw = step_pose(l, m, maxc, x, y, yaw)
    return x, y, yaw


def ranked_words(x0: float, y0: float, yaw0: float, x1: float, y1: float, yaw1: float,
                 maxc: float, cusp_penalty: float = 0.0
                 ) -> list[tuple[float, str, tuple[float, ...], float, int]]:
    """Mọi ứng viên RS, xếp theo (độ dài m + phạt cusp). CHƯA kiểm tra điểm cuối.

    Kiểm tra điểm cuối là việc đắt, nên để hàm gọi làm lười (`verify`) chỉ với
    vài ứng viên thật sự định dùng.
    """
    nx, ny, nphi = normalize(x0, y0, yaw0, x1, y1, yaw1, maxc)
    out = []
    for types, lengths in words(nx, ny, nphi):
        total = 0.0
        prev = 0
        cusps = 0
        for l in lengths:
            if l > 1e-12:
                total += l
                sgn = 1
            elif l < -1e-12:
                total -= l
                sgn = -1
            else:
                continue
            if prev and sgn != prev:
                cusps += 1
            prev = sgn
        out.append((total / maxc + cusps * cusp_penalty, types, lengths, total / maxc, cusps))
    out.sort(key=lambda p: p[0])
    return out


def verify(x0: float, y0: float, yaw0: float, x1: float, y1: float, yaw1: float,
           types: str, lengths, maxc: float) -> bool:
    ex, ey, eyaw = path_end(x0, y0, yaw0, types, lengths, maxc)
    if math.hypot(ex - x1, ey - y1) * maxc > _END_TOL:
        return False
    return abs(mod2pi(eyaw - yaw1)) <= _END_TOL


def candidates(x0: float, y0: float, yaw0: float, x1: float, y1: float, yaw1: float,
               maxc: float) -> list[tuple[str, tuple[float, ...], float, int]]:
    """Các đường RS hợp lệ từ q0 tới q1: (kiểu, độ dài, tổng độ dài chuẩn hóa, số cusp)."""
    out = []
    for _rank, types, lengths, length_m, cusps in ranked_words(x0, y0, yaw0, x1, y1, yaw1, maxc):
        if verify(x0, y0, yaw0, x1, y1, yaw1, types, lengths, maxc):
            out.append((types, lengths, length_m * maxc, cusps))
    return out


def sample(x0: float, y0: float, yaw0: float, types: str, lengths, maxc: float,
           step: float, wheelbase: float) -> list[tuple[float, float, float, int, float]]:
    """Lấy mẫu dọc đường: (x, y, yaw, chiều, góc lái). KHÔNG có điểm đầu."""
    out: list[tuple[float, float, float, int, float]] = []
    steer_turn = math.atan(wheelbase * maxc)
    inv = 1.0 / maxc
    x, y, yaw = x0, y0, yaw0
    sin_, cos_, ceil_ = math.sin, math.cos, math.ceil
    for l, m in zip(lengths, types):
        if -1e-12 < l < 1e-12:
            continue
        direction = 1 if l > 0.0 else -1
        seg_len = (l if l > 0 else -l) * inv
        n = max(1, int(ceil_(seg_len / step)))
        c, s = cos_(yaw), sin_(yaw)
        if m == "S":
            dxs, dys = c * inv, s * inv
            for k in range(1, n + 1):
                p = l * k / n
                out.append((x + dxs * p, y + dys * p, yaw, direction, 0.0))
            x += dxs * l
            y += dys * l
        else:
            if m == "L":
                sgn, steer = 1.0, steer_turn
            else:
                sgn, steer = -1.0, -steer_turn
            for k in range(1, n + 1):
                p = l * k / n
                ldx = sin_(p) * inv
                ldy = sgn * (1.0 - cos_(p)) * inv
                out.append((x + c * ldx - s * ldy, y + s * ldx + c * ldy,
                            yaw + sgn * p, direction, steer))
            ldx = sin_(l) * inv
            ldy = sgn * (1.0 - cos_(l)) * inv
            x, y, yaw = x + c * ldx - s * ldy, y + s * ldx + c * ldy, yaw + sgn * l
    return out
