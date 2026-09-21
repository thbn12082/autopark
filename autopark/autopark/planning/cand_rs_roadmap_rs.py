"""Reeds–Shepp ĐẦY ĐỦ 48 họ, dùng riêng cho ứng viên "Bản đồ đường Reeds–Shepp".

`autopark/planning/reeds_shepp.py` chỉ có CSC và CCC (16 biến thể). Trong chỗ chật,
các họ nối được lại chính là CCCC, CCSC, CSCC và CCSCC — nên module này dựng lại
toàn bộ 48 từ theo Reeds & Shepp (1990), cách tổ chức phép đối xứng theo OMPL.

Quy ước giống module gốc: chuẩn hóa theo bán kính quay nhỏ nhất = 1 (nhân tọa độ
với `maxc = 1/R_min`); đoạn 'L'/'R' là cung trái/phải có độ dài bằng góc quay,
'S' là đoạn thẳng; độ dài âm nghĩa là chạy lùi.

Bốn phép đối xứng dùng ở đây, viết lại từ định nghĩa để khỏi phụ thuộc bảng chỉ số:
  timeflip   f(-x,  y, -phi) -> cùng từ, đảo dấu mọi độ dài
  reflect    f( x, -y, -phi) -> đổi L<->R trong từ, giữ nguyên độ dài
  cả hai     f(-x, -y,  phi) -> đổi L<->R, đảo dấu độ dài
  backwards  giải bài toán ngược rồi đảo đường: đảo thứ tự các đoạn.
Với `xb = x cos(phi) + y sin(phi)`, `yb = x sin(phi) - y cos(phi)`:
  f( xb,  yb,  phi) -> đảo thứ tự từ,               đảo thứ tự độ dài
  f(-xb,  yb, -phi) -> đảo thứ tự từ,               đảo thứ tự rồi đổi dấu
  f( xb, -yb, -phi) -> đảo thứ tự của từ đã đổi L<->R, đảo thứ tự độ dài
  f(-xb, -yb,  phi) -> đảo thứ tự của từ đã đổi L<->R, đảo thứ tự rồi đổi dấu

Mọi ứng viên vẫn phải được kiểm tra điểm cuối bằng tích phân trước khi dùng
(`endpoint_error`), nên một công thức sai chỉ làm mất ứng viên chứ không sinh
đường sai.
"""
from __future__ import annotations

import math

TWO_PI = 2.0 * math.pi
_PI_2 = 0.5 * math.pi
_ZERO = 1e-9

_cos = math.cos
_sin = math.sin
_atan2 = math.atan2
_hypot = math.hypot
_sqrt = math.sqrt
_fabs = math.fabs

_SWAP = {"L": "R", "R": "L", "S": "S"}


def mod2pi(x: float) -> float:
    v = math.fmod(x, TWO_PI)
    if v < -math.pi:
        v += TWO_PI
    elif v > math.pi:
        v -= TWO_PI
    return v


def _polar(x: float, y: float) -> tuple[float, float]:
    return _hypot(x, y), _atan2(y, x)


def _tau_omega(u: float, v: float, xi: float, eta: float, phi: float) -> tuple[float, float]:
    delta = mod2pi(u - v)
    A = _sin(u) - _sin(delta)
    B = _cos(u) - _cos(delta) - 1.0
    t1 = _atan2(eta * A - xi * B, xi * A + eta * B)
    t2 = 2.0 * (_cos(delta) - _cos(v) - _cos(u)) + 3.0
    tau = mod2pi(t1 + math.pi) if t2 < 0 else mod2pi(t1)
    omega = mod2pi(tau - u + v - phi)
    return tau, omega


# --------------------------------------------------------------- công thức gốc

def _lp_sp_lp(x, y, phi):
    """L+ S+ L+ (công thức 8.1)."""
    u, t = _polar(x - _sin(phi), y - 1.0 + _cos(phi))
    if t >= -_ZERO:
        v = mod2pi(phi - t)
        if v >= -_ZERO:
            return t, u, v
    return None


def _lp_sp_rp(x, y, phi):
    """L+ S+ R+ (công thức 8.2)."""
    u1, t1 = _polar(x + _sin(phi), y - 1.0 - _cos(phi))
    u1 = u1 * u1
    if u1 >= 4.0:
        u = _sqrt(u1 - 4.0)
        theta = _atan2(2.0, u)
        t = mod2pi(t1 + theta)
        v = mod2pi(t - phi)
        if t >= -_ZERO and v >= -_ZERO:
            return t, u, v
    return None


def _lp_rm_l(x, y, phi):
    """L+ R- L (công thức 8.3/8.4)."""
    xi = x - _sin(phi)
    eta = y - 1.0 + _cos(phi)
    u1, theta = _polar(xi, eta)
    if u1 <= 4.0:
        u = -2.0 * math.asin(0.25 * u1)
        t = mod2pi(theta + 0.5 * u + math.pi)
        v = mod2pi(phi - t + u)
        if t >= -_ZERO and u <= _ZERO:
            return t, u, v
    return None


def _lp_rup_lum_rm(x, y, phi):
    """L+ R+ L- R- (công thức 8.7)."""
    xi = x + _sin(phi)
    eta = y - 1.0 - _cos(phi)
    rho = 0.25 * (2.0 + _hypot(xi, eta))
    if rho <= 1.0:
        u = math.acos(rho)
        t, v = _tau_omega(u, -u, xi, eta, phi)
        if t >= -_ZERO and v <= _ZERO:
            return t, u, v
    return None


def _lp_rum_lum_rp(x, y, phi):
    """L+ R- L- R+ (công thức 8.8)."""
    xi = x + _sin(phi)
    eta = y - 1.0 - _cos(phi)
    rho = (20.0 - xi * xi - eta * eta) / 16.0
    if 0.0 <= rho <= 1.0:
        u = -math.acos(rho)
        if u >= -_PI_2:
            t, v = _tau_omega(u, u, xi, eta, phi)
            if t >= -_ZERO and v >= -_ZERO:
                return t, u, v
    return None


def _lp_rm_sm_lm(x, y, phi):
    """L+ R-(90°) S- L- (công thức 8.9)."""
    xi = x - _sin(phi)
    eta = y - 1.0 + _cos(phi)
    rho, theta = _polar(xi, eta)
    if rho >= 2.0:
        r = _sqrt(rho * rho - 4.0)
        u = 2.0 - r
        t = mod2pi(theta + _atan2(r, -2.0))
        v = mod2pi(phi - _PI_2 - t)
        if t >= -_ZERO and u <= _ZERO and v <= _ZERO:
            return t, u, v
    return None


def _lp_rm_sm_rm(x, y, phi):
    """L+ R-(90°) S- R- (công thức 8.10)."""
    xi = x + _sin(phi)
    eta = y - 1.0 - _cos(phi)
    rho, theta = _polar(-eta, xi)
    if rho >= 2.0:
        t = theta
        u = 2.0 - rho
        v = mod2pi(t + _PI_2 - phi)
        if t >= -_ZERO and u <= _ZERO and v <= _ZERO:
            return t, u, v
    return None


def _lp_rm_s_lm_rp(x, y, phi):
    """L+ R-(90°) S- L-(90°) R+ (công thức 8.11)."""
    xi = x + _sin(phi)
    eta = y - 1.0 - _cos(phi)
    rho, _ = _polar(xi, eta)
    if rho >= 2.0:
        u = 4.0 - _sqrt(rho * rho - 4.0)
        if u <= _ZERO:
            t = mod2pi(_atan2((4.0 - u) * xi - 2.0 * eta, -2.0 * xi + (u - 4.0) * eta))
            v = mod2pi(t - phi)
            if t >= -_ZERO and v >= -_ZERO:
                return t, u, v
    return None


# ------------------------------------------------------- sinh toàn bộ ứng viên

_W_LSL = ("L", "S", "L")
_W_LSR = ("L", "S", "R")
_W_LRL = ("L", "R", "L")
_W_LRLR = ("L", "R", "L", "R")
_W_LRSL = ("L", "R", "S", "L")
_W_LRSR = ("L", "R", "S", "R")
_W_LRSLR = ("L", "R", "S", "L", "R")


def _swap(word: tuple) -> tuple:
    return tuple(_SWAP[c] for c in word)


def _rev(seq: tuple) -> tuple:
    return tuple(reversed(seq))


def _neg(seq: tuple) -> tuple:
    return tuple(-v for v in seq)


# Từ đã tính sẵn 4 biến thể (gốc, đổi L<->R, đảo, đảo của bản đổi L<->R)
_WORDS = {}
for _w in (_W_LSL, _W_LSR, _W_LRL, _W_LRLR, _W_LRSL, _W_LRSR, _W_LRSLR):
    _WORDS[_w] = (_w, _swap(_w), _rev(_w), _rev(_swap(_w)))


def _emit4(out, func, word, mk, x, y, phi):
    """Bốn biến thể thuận: gốc, timeflip, reflect, timeflip+reflect."""
    w, ws, _, _ = _WORDS[word]
    r = func(x, y, phi)
    if r is not None:
        out.append((w, mk(r)))
    r = func(-x, y, -phi)
    if r is not None:
        out.append((w, _neg(mk(r))))
    r = func(x, -y, -phi)
    if r is not None:
        out.append((ws, mk(r)))
    r = func(-x, -y, phi)
    if r is not None:
        out.append((ws, _neg(mk(r))))


def _emit4_back(out, func, word, mk, xb, yb, phi):
    """Bốn biến thể ngược (giải bài toán ngược rồi đảo đường)."""
    _, _, wr, wsr = _WORDS[word]
    r = func(xb, yb, phi)
    if r is not None:
        out.append((wr, _rev(mk(r))))
    r = func(-xb, yb, -phi)
    if r is not None:
        out.append((wr, _neg(_rev(mk(r)))))
    r = func(xb, -yb, -phi)
    if r is not None:
        out.append((wsr, _rev(mk(r))))
    r = func(-xb, -yb, phi)
    if r is not None:
        out.append((wsr, _neg(_rev(mk(r)))))


def _mk3(r):
    return (r[0], r[1], r[2])


def _mk_ccccm(r):          # L+ R+ L- R-  : (t, u, -u, v)
    return (r[0], r[1], -r[1], r[2])


def _mk_ccccp(r):          # L+ R- L- R+  : (t, u, u, v)
    return (r[0], r[1], r[1], r[2])


def _mk_ccsc(r):           # L+ R-(90°) S- L-
    return (r[0], -_PI_2, r[1], r[2])


def _mk_ccscc(r):          # L+ R-(90°) S- L-(90°) R+
    return (r[0], -_PI_2, r[1], -_PI_2, r[2])


def all_candidates(x: float, y: float, phi: float) -> list[tuple[tuple, tuple]]:
    """Mọi từ Reeds–Shepp nối (0,0,0) tới (x, y, phi) trong hệ đã chuẩn hóa.

    Trả về danh sách (từ, độ dài có dấu). Chưa lọc trùng, chưa xếp thứ tự.
    """
    out: list[tuple[tuple, tuple]] = []
    xb = x * _cos(phi) + y * _sin(phi)
    yb = x * _sin(phi) - y * _cos(phi)

    # CSC (8 từ)
    _emit4(out, _lp_sp_lp, _W_LSL, _mk3, x, y, phi)
    _emit4(out, _lp_sp_rp, _W_LSR, _mk3, x, y, phi)
    # CCC (8 từ)
    _emit4(out, _lp_rm_l, _W_LRL, _mk3, x, y, phi)
    _emit4_back(out, _lp_rm_l, _W_LRL, _mk3, xb, yb, phi)
    # CCCC (8 từ)
    _emit4(out, _lp_rup_lum_rm, _W_LRLR, _mk_ccccm, x, y, phi)
    _emit4(out, _lp_rum_lum_rp, _W_LRLR, _mk_ccccp, x, y, phi)
    # CCSC + CSCC (16 từ)
    _emit4(out, _lp_rm_sm_lm, _W_LRSL, _mk_ccsc, x, y, phi)
    _emit4_back(out, _lp_rm_sm_lm, _W_LRSL, _mk_ccsc, xb, yb, phi)
    _emit4(out, _lp_rm_sm_rm, _W_LRSR, _mk_ccsc, x, y, phi)
    _emit4_back(out, _lp_rm_sm_rm, _W_LRSR, _mk_ccsc, xb, yb, phi)
    # CCSCC (8 từ; các biến thể ngược trùng với biến thể reflect nên không sinh)
    _emit4(out, _lp_rm_s_lm_rp, _W_LRSLR, _mk_ccscc, x, y, phi)
    return out


# ------------------------------------------------------------- hình học đường

def interpolate(p: float, mode: str, maxc: float, ox: float, oy: float, oyaw: float):
    """Tư thế sau khi đi tiến độ có dấu `p` (chuẩn hóa) trên đoạn `mode`."""
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


def path_end(word: tuple, lengths: tuple, maxc: float, ox: float, oy: float, oyaw: float):
    x, y, yaw = ox, oy, oyaw
    for l, m in zip(lengths, word):
        if _fabs(l) > 1e-12:
            x, y, yaw = interpolate(l, m, maxc, x, y, yaw)
    return x, y, yaw


def endpoint_error(word: tuple, lengths: tuple, x: float, y: float, phi: float) -> float:
    """Sai lệch điểm cuối trong hệ chuẩn hóa (maxc = 1) so với (x, y, phi)."""
    ex, ey, eyaw = path_end(word, lengths, 1.0, 0.0, 0.0, 0.0)
    dyaw = _atan2(_sin(eyaw - phi), _cos(eyaw - phi))
    return _hypot(ex - x, ey - y) + _fabs(dyaw)


def path_length(lengths: tuple) -> float:
    return sum(_fabs(l) for l in lengths)


def n_cusps(lengths: tuple) -> int:
    sgn = [1 if l > 0 else -1 for l in lengths if _fabs(l) > 1e-9]
    return sum(1 for a, b in zip(sgn, sgn[1:]) if a != b)


def reverse_length(lengths: tuple) -> float:
    return sum(-l for l in lengths if l < 0)


def path_free(checker, ox: float, oy: float, oyaw: float, word: tuple, lengths: tuple,
              maxc: float, step: float, check_start: bool = False) -> bool:
    """Lấy mẫu dọc đường và hỏi `checker.pose_ok` từng tư thế."""
    x, y, yaw = ox, oy, oyaw
    if check_start and not checker.pose_ok(x, y, yaw):
        return False
    inv = 1.0 / (step * maxc)
    for l, m in zip(lengths, word):
        al = _fabs(l)
        if al < 1e-12:
            continue
        n = int(al * inv) + 1
        dl = l / n
        for k in range(1, n + 1):
            nx, ny, nyaw = interpolate(dl * k, m, maxc, x, y, yaw)
            if not checker.pose_ok(nx, ny, nyaw):
                return False
        x, y, yaw = interpolate(l, m, maxc, x, y, yaw)
    return True


def path_samples(ox: float, oy: float, oyaw: float, word: tuple, lengths: tuple,
                 maxc: float, step: float, steer_mag: float):
    """Dãy (x, y, yaw, chiều ±1, góc lái) dọc đường; phần tử đầu là tư thế xuất phát."""
    first_dir = 1
    for l in lengths:
        if _fabs(l) > 1e-12:
            first_dir = 1 if l > 0 else -1
            break
    first_steer = 0.0
    for l, m in zip(lengths, word):
        if _fabs(l) > 1e-12:
            first_steer = steer_mag if m == "L" else (-steer_mag if m == "R" else 0.0)
            break
    out = [(ox, oy, oyaw, first_dir, first_steer)]
    x, y, yaw = ox, oy, oyaw
    inv = 1.0 / (step * maxc)
    for l, m in zip(lengths, word):
        al = _fabs(l)
        if al < 1e-12:
            continue
        direction = 1 if l > 0 else -1
        steer = steer_mag if m == "L" else (-steer_mag if m == "R" else 0.0)
        n = int(al * inv) + 1
        dl = l / n
        for k in range(1, n + 1):
            nx, ny, nyaw = interpolate(dl * k, m, maxc, x, y, yaw)
            out.append((nx, ny, nyaw, direction, steer))
        x, y, yaw = interpolate(l, m, maxc, x, y, yaw)
    return out
