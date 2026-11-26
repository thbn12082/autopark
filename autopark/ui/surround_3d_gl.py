"""Vẽ cảnh 3D quanh xe bằng GPU (OpenGL 3.3 qua Qt, thêm 26/11/2026; làm lại giao diện cùng ngày).

```
CPU (một lần)                      GPU (mỗi lần vẽ, theo nhịp màn hình)
├── lưới tam giác mặt bát ───────► vị trí từng điểm trên bát
├── thông số 4 camera ───────────► shader chiếu fisheye + trộn mềm 4 ảnh cho TỪNG PIXEL
├── mô hình xe (kích thước đo) ──► thân, cabin kính, bánh, đèn; có ánh sáng
└── ảnh camera mới (khi có) ─────► 4 texture + màu sàn trung bình (tô điểm mù)
Xoay / phóng to: chỉ đổi một ma trận.
```

Công thức chiếu giống bản CPU (`perception/surround_3d.py`). Khác ở phần trình bày: vết nối giữa camera được trộn mềm,
điểm mù tô màu sàn trung bình thay vì đen, sàn chìm dần vào nền ở xa, bóng mềm dưới xe.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMatrix4x4, QSurfaceFormat, QVector2D, QVector3D, QVector4D
from PySide6.QtOpenGL import (QOpenGLBuffer, QOpenGLPixelTransferOptions, QOpenGLShader, QOpenGLShaderProgram,
                              QOpenGLTexture, QOpenGLVertexArrayObject)
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from autopark.perception import surround_3d as s3

GL_FLOAT = 0x1406
GL_TRIANGLES = 0x0004
GL_POINTS = 0x0000
GL_DEPTH_TEST = 0x0B71
GL_PROGRAM_POINT_SIZE = 0x8642
GL_COLOR_BUFFER_BIT = 0x4000
GL_DEPTH_BUFFER_BIT = 0x0100
GL_BLEND = 0x0BE2
GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA = 0x0302, 0x0303

BG_TOP = (0.075, 0.105, 0.145)
BG_BOTTOM = (0.030, 0.042, 0.058)
TIRE_RADIUS_M = 0.037            # lốp Ø 74 mm (đo 24/11/2026)
WHEELBASE_M = 0.21

_available: bool | None = None


def gl_available() -> bool:
    """Máy có tạo được context OpenGL 3.3 core không (một lần, nhớ kết quả)."""
    global _available
    if _available is None:
        try:
            from PySide6.QtGui import QGuiApplication, QOffscreenSurface, QOpenGLContext
            if QGuiApplication.platformName() in ("offscreen", "minimal"):
                _available = False
            else:
                ctx = QOpenGLContext()
                ctx.setFormat(_format())
                surface = QOffscreenSurface()
                surface.setFormat(_format())
                surface.create()
                _available = bool(ctx.create() and ctx.format().majorVersion() >= 3 and ctx.makeCurrent(surface))
                if _available:
                    ctx.doneCurrent()
        except Exception:  # noqa: BLE001 - không có OpenGL thì dùng bản CPU
            _available = False
    return _available


def _format() -> QSurfaceFormat:
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    fmt.setDepthBufferSize(24)
    fmt.setSamples(4)
    return fmt


# ------------------------------------------------------------------------------------------------------------ shader
BG_VS = """#version 330 core
layout(location = 0) in vec2 pos;
out float vY;
void main() { vY = pos.y * 0.5 + 0.5; gl_Position = vec4(pos, 0.999, 1.0); }
"""

BG_FS = """#version 330 core
in float vY;
out vec4 color;
uniform vec3 top;
uniform vec3 bottom;
void main() { color = vec4(mix(bottom, top, smoothstep(0.0, 1.0, vY)), 1.0); }
"""

BOWL_VS = """#version 330 core
layout(location = 0) in vec3 pos;
uniform mat4 mvp;
out vec3 vPos;
void main() { vPos = pos; gl_Position = mvp * vec4(pos, 1.0); }
"""

BOWL_FS = """#version 330 core
in vec3 vPos;
out vec4 color;
uniform sampler2D tex0;
uniform sampler2D tex1;
uniform sampler2D tex2;
uniform sampler2D tex3;
uniform vec3 camR0[4];      // ba hàng của phép quay xe -> camera
uniform vec3 camR1[4];
uniform vec3 camR2[4];
uniform vec3 camT[4];       // vị trí camera trong hệ xe
uniform vec4 camK[4];       // rho(theta) = theta*(k1 + theta*(k2 + theta*(k3 + theta*k4)))
uniform vec4 camC[4];       // cx, cy, tỷ lệ điểm ảnh, theta_max
uniform vec2 camSize[4];
uniform int camLive[4];
uniform int anyLive;
uniform int preview;        // gá giả định: không nhìn ra sau lưng camera
uniform vec4 body;          // x_min, x_max, y_min, y_max của thân xe
uniform vec2 center;
uniform vec3 fillColor;     // màu sàn trung bình (tô điểm mù)
uniform vec3 fogColor;
uniform vec2 fog;           // bán kính bắt đầu / hết chìm vào nền

vec4 sampleCam(int i, sampler2D tex) {
    if (camLive[i] == 0) return vec4(0.0);
    vec3 d = vPos - camT[i];
    vec3 pc = vec3(dot(camR0[i], d), dot(camR1[i], d), dot(camR2[i], d));
    float facing = pc.z / max(length(pc), 1e-6);
    if (preview == 1 && facing <= 0.0) return vec4(0.0);
    float chi = length(pc.xy);
    float th = atan(chi, pc.z);
    if (th > camC[i].w) return vec4(0.0);
    vec4 k = camK[i];
    float rho = th * (k.x + th * (k.y + th * (k.z + th * k.w)));
    float s = chi > 1e-9 ? rho / chi : 0.0;
    float u = camC[i].x + s * pc.x;
    float v = camC[i].y + s * pc.y * camC[i].z;
    vec2 sz = camSize[i];
    if (u < 0.0 || v < 0.0 || u > sz.x - 1.0 || v > sz.y - 1.0) return vec4(0.0);
    float edge = min(min(u, v), min(sz.x - 1.0 - u, sz.y - 1.0 - v));
    float e = smoothstep(0.0, 48.0, edge);                       // mép ảnh mờ dần: vết nối mềm
    vec2 dh = vPos.xy - camT[i].xy;
    float w = e * e / (1.0 + dot(dh, dh) / 0.16);
    w *= smoothstep(camC[i].w, camC[i].w - 0.12, th);            // rìa ống kính mờ dần
    if (preview == 1) w *= smoothstep(0.0, 0.25, facing);
    vec3 c = texture(tex, vec2((u + 0.5) / sz.x, (v + 0.5) / sz.y)).rgb;
    return vec4(c * w, w);
}

float boxDistance(vec2 p) {                                      // khoảng cách tới hình chữ nhật thân xe
    vec2 c = vec2(body.x + body.y, body.z + body.w) * 0.5;
    vec2 h = vec2(body.y - body.x, body.w - body.z) * 0.5;
    vec2 q = abs(p - c) - h;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0);
}

void main() {
    bool floorPt = vPos.z < 0.002;
    vec4 acc = sampleCam(0, tex0) + sampleCam(1, tex1) + sampleCam(2, tex2) + sampleCam(3, tex3);
    vec3 base;
    if (anyLive == 1) {
        float cover = smoothstep(0.0, 0.02, acc.w);              // điểm mù: trộn dần sang màu sàn trung bình
        vec3 cam = acc.w > 0.0 ? acc.rgb / acc.w : fillColor;
        base = mix(fillColor, cam, cover);
    } else {
        base = floorPt ? vec3(0.10, 0.115, 0.13) : vec3(0.12, 0.14, 0.16);
        if (floorPt) {
            vec2 g = abs(fract(vPos.xy / 0.1 + 0.5) - 0.5) / fwidth(vPos.xy / 0.1);
            base = mix(base, vec3(0.19, 0.22, 0.25), (1.0 - min(min(g.x, g.y), 1.0)) * 0.6);
        }
    }
    if (floorPt) {                                               // bóng mềm dưới xe
        float d = boxDistance(vPos.xy);
        base *= mix(0.25, 1.0, smoothstep(-0.01, 0.07, d));
    }
    float r = length(vPos.xy - center);
    base = mix(base, fogColor, smoothstep(fog.x, fog.y, r));      // xa thì chìm vào nền
    color = vec4(base, 1.0);
}
"""

LIT_VS = """#version 330 core
layout(location = 0) in vec3 pos;
layout(location = 1) in vec3 normal;
layout(location = 2) in vec4 rgba;
uniform mat4 mvp;
out vec3 vNormal;
out vec4 vColor;
out vec3 vPos;
void main() { vNormal = normal; vColor = rgba; vPos = pos; gl_Position = mvp * vec4(pos, 1.0); }
"""

LIT_FS = """#version 330 core
in vec3 vNormal;
in vec4 vColor;
in vec3 vPos;
out vec4 color;
uniform vec3 eye;
void main() {
    vec3 n = normalize(vNormal);
    if (dot(n, eye - vPos) < 0.0) n = -n;                         // chiếu sáng hai mặt
    vec3 light = normalize(vec3(-0.35, 0.45, 0.82));
    float diffuse = max(dot(n, light), 0.0);
    float sky = 0.5 + 0.5 * n.z;                                  // trời sáng hơn mặt đất
    vec3 view = normalize(eye - vPos);
    float glossy = vColor.a < 0.99 ? 1.0 : 0.35;                  // alpha < 1: kính / sơn bóng
    float spec = pow(max(dot(reflect(-light, n), view), 0.0), 40.0) * glossy;
    float rim = pow(1.0 - max(dot(n, view), 0.0), 3.0) * 0.25;
    vec3 c = vColor.rgb * (0.30 + 0.25 * sky + 0.55 * diffuse) + vec3(spec + rim);
    color = vec4(c, 1.0);
}
"""

FLAT_VS = """#version 330 core
layout(location = 0) in vec3 pos;
layout(location = 1) in vec4 rgba;
uniform mat4 mvp;
uniform float pointSize;
out vec4 vColor;
void main() { vColor = rgba; gl_PointSize = pointSize; gl_Position = mvp * vec4(pos, 1.0); }
"""

FLAT_FS = """#version 330 core
in vec4 vColor;
out vec4 color;
uniform int roundDots;
void main() {
    float a = vColor.a;
    if (roundDots == 1) {                                             // chấm tròn phát sáng
        float d = length(gl_PointCoord - 0.5) * 2.0;
        if (d > 1.0) discard;
        a *= smoothstep(1.0, 0.35, d);
    }
    color = vec4(vColor.rgb, a);
}
"""


# ---------------------------------------------------------------------------------------------------------- hình học
def bowl_mesh(bowl: s3.Bowl, rings_floor: int = 40, rings_wall: int = 48, segments: int = 200) -> np.ndarray:
    """Tam giác (N, 3) phủ mặt bát quanh tâm, mịn hơn ở sát xe."""
    radii = np.concatenate([np.linspace(0.0, bowl.floor_radius_m, rings_floor + 1),
                            bowl.floor_radius_m + (bowl.rim_radius_m - bowl.floor_radius_m)
                            * np.linspace(0.0, 1.0, rings_wall + 1)[1:] ** 1.3])
    angles = np.linspace(0.0, 2 * math.pi, segments + 1)
    rr, aa = np.meshgrid(radii, angles, indexing="ij")
    cx, cy = bowl.center_xy
    grid = np.stack([cx + rr * np.cos(aa), cy + rr * np.sin(aa), bowl.height(rr)], axis=-1).astype(np.float32)
    a, b, c, d = grid[:-1, :-1], grid[1:, :-1], grid[1:, 1:], grid[:-1, 1:]
    return np.concatenate([np.stack([a, b, c], 2), np.stack([a, c, d], 2)], axis=2).reshape(-1, 3)


def _rgb(hex_color: str, alpha: float = 1.0) -> tuple:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0, alpha)


def _tri(out: list, a, b, c, color) -> None:
    a, b, c = (np.asarray(p, np.float64) for p in (a, b, c))
    n = np.cross(b - a, c - a)
    norm = np.linalg.norm(n)
    if norm < 1e-12:
        return
    n /= norm
    for p in (a, b, c):
        out.append((*p, *n, *color))


def _extrude(out: list, profile_xz, y0: float, y1: float, color, side_color=None) -> None:
    """Đa giác lồi (x, z) đẩy theo y từ y0 tới y1: hai mặt bên + các mặt viền, pháp tuyến phẳng."""
    side_color = side_color or color
    pts = [np.array(p, np.float64) for p in profile_xz]
    e1, e2 = pts[1] - pts[0], pts[2] - pts[0]
    if e1[0] * e2[1] - e1[1] * e2[0] < 0:                   # đưa về ngược chiều kim đồng hồ trong mặt (x, z)
        pts = pts[::-1]
    left = [(p[0], y1, p[1]) for p in pts]                  # mặt +y
    right = [(p[0], y0, p[1]) for p in pts]                 # mặt −y
    for i in range(1, len(pts) - 1):
        _tri(out, left[0], left[i + 1], left[i], side_color)
        _tri(out, right[0], right[i], right[i + 1], side_color)
    for i in range(len(pts)):
        j = (i + 1) % len(pts)
        _tri(out, right[i], left[i], left[j], color)
        _tri(out, right[i], left[j], right[j], color)


def _wheel(out: list, x: float, y: float, z: float, radius: float, width: float, segments: int = 24) -> None:
    tire, hub = _rgb("#1b1e22"), _rgb("#8b949e")
    angles = np.linspace(0.0, 2 * math.pi, segments + 1)
    y0, y1 = y - width / 2, y + width / 2
    ring = [(x + radius * math.cos(a), z + radius * math.sin(a)) for a in angles]
    for (xa, za), (xb, zb) in zip(ring, ring[1:]):
        _tri(out, (xa, y0, za), (xb, y0, zb), (xb, y1, zb), tire)
        _tri(out, (xa, y0, za), (xb, y1, zb), (xa, y1, za), tire)
    outer = y1 if y > 0 else y0
    inner_r = radius * 0.55
    for (xa, za), (xb, zb) in zip(ring, ring[1:]):        # mặt lốp + mâm
        c = (x, outer, z)
        pa, pb = (xa, outer, za), (xb, outer, zb)
        ma = (x + (xa - x) * 0.55, outer, z + (za - z) * 0.55)
        mb = (x + (xb - x) * 0.55, outer, z + (zb - z) * 0.55)
        order = (lambda p, q, r: (p, q, r)) if y > 0 else (lambda p, q, r: (p, r, q))
        _tri(out, *order(ma, pa, pb), tire)
        _tri(out, *order(ma, pb, mb), tire)
        _tri(out, *order(c, ma, mb), hub)
    del inner_r


def car_mesh(body, *, paint: str = "#dfe6ee") -> np.ndarray:
    """Mô hình xe theo kích thước đo (thân xe `body`, hệ xe): thân vát, cabin kính, nóc, bánh, đèn.

    Mỗi đỉnh 10 số: x y z, pháp tuyến, r g b a (a < 1 = mặt bóng)."""
    out: list = []
    x0, x1, y0, y1 = body.x_min, body.x_max, body.y_min, body.y_max
    length = x1 - x0
    paint_c, paint_side = _rgb(paint, 0.9), _rgb(paint, 0.9)
    glass = _rgb("#1a2633", 0.6)
    trim = _rgb("#2a3138")
    clearance, shoulder, roof = 0.022, 0.072, 0.118
    # thân dưới: vát mũi và đuôi
    _extrude(out, [(x0 + 0.006, clearance), (x1 - 0.006, clearance), (x1, clearance + 0.012), (x1, shoulder - 0.012),
                   (x1 - 0.022, shoulder), (x0 + 0.014, shoulder), (x0, shoulder - 0.010), (x0, clearance + 0.010)],
             y0 + 0.004, y1 - 0.004, paint_c, paint_side)
    # cabin kính, hẹp hơn thân
    cab0, cab1 = x0 + 0.20 * length, x1 - 0.30 * length
    inset = 0.016
    _extrude(out, [(cab0, shoulder), (cab1, shoulder), (cab1 - 0.040, roof - 0.004), (cab0 + 0.026, roof - 0.004)],
             y0 + inset, y1 - inset, glass, glass)
    # nóc sơn
    _extrude(out, [(cab0 + 0.024, roof - 0.005), (cab1 - 0.042, roof - 0.005), (cab1 - 0.046, roof),
                   (cab0 + 0.028, roof)], y0 + inset + 0.002, y1 - inset - 0.002, paint_c, paint_c)
    # cản trước / sau màu tối
    _extrude(out, [(x1 - 0.004, clearance + 0.004), (x1 + 0.004, clearance + 0.004), (x1 + 0.004, clearance + 0.018),
                   (x1 - 0.004, clearance + 0.018)], y0 + 0.010, y1 - 0.010, trim)
    _extrude(out, [(x0 - 0.004, clearance + 0.004), (x0 + 0.004, clearance + 0.004), (x0 + 0.004, clearance + 0.018),
                   (x0 - 0.004, clearance + 0.018)], y0 + 0.010, y1 - 0.010, trim)
    # đèn
    head, tail = _rgb("#f4f1d8", 0.5), _rgb("#d43a3a", 0.5)
    for y in (y0 + 0.022, y1 - 0.022):
        _extrude(out, [(x1 - 0.002, shoulder - 0.022), (x1 + 0.0015, shoulder - 0.022),
                       (x1 + 0.0015, shoulder - 0.013), (x1 - 0.002, shoulder - 0.013)], y - 0.014, y + 0.014, head)
        _extrude(out, [(x0 - 0.0015, shoulder - 0.020), (x0 + 0.002, shoulder - 0.020),
                       (x0 + 0.002, shoulder - 0.012), (x0 - 0.0015, shoulder - 0.012)], y - 0.014, y + 0.014, tail)
    # bánh xe: trục sau x = 0, trục trước x = chiều dài cơ sở
    for x in (0.0, WHEELBASE_M):
        for y in (y0 + 0.012, y1 - 0.012):
            _wheel(out, x, y, TIRE_RADIUS_M, TIRE_RADIUS_M, 0.024)
    return np.array(out, np.float32)


def overlay_geometry(overlays: s3.Overlays | None, width: float = 0.012):
    """(dải trên sàn dạng tam giác, điểm LiDAR), mỗi đỉnh 7 số: x y z r g b a."""
    if overlays is None:
        return np.zeros((0, 7), np.float32), np.zeros((0, 7), np.float32)
    tris: list = []

    def ribbon(points, color, closed):
        p = np.asarray(points, np.float64).reshape(-1, 2)
        if closed:
            p = np.vstack([p, p[:1]])
        for a, b in zip(p, p[1:]):
            d = b - a
            n = np.linalg.norm(d)
            if n < 1e-9:
                continue
            off = np.array([-d[1], d[0]]) / n * width / 2
            q = [a + off, b + off, b - off, a - off]
            for i in (0, 1, 2, 0, 2, 3):
                tris.append((q[i][0], q[i][1], 0.004, *color))

    for corners in overlays.slots:
        ribbon(corners, _rgb("#8cf0d6", 0.95), True)
    if overlays.path_xy is not None:
        ribbon(overlays.path_xy, _rgb("#efb76b", 0.95), False)
    points = []
    if overlays.lidar_xy is not None:
        dot = _rgb("#ffd166", 0.95)
        points = [(x, y, overlays.lidar_z, *dot) for x, y in np.asarray(overlays.lidar_xy).reshape(-1, 2)]
    return np.array(tris, np.float32).reshape(-1, 7), np.array(points, np.float32).reshape(-1, 7)


# ------------------------------------------------------------------------------------------------------------ widget
class Surround3DGLWidget(QOpenGLWidget):
    """Cảnh 3D vẽ bằng GPU. Kéo chuột để xoay, lăn để phóng to; ảnh mới qua `set_frames`."""

    def __init__(self, cameras: dict, *, is_preview: bool, body=None, bowl: s3.Bowl | None = None, parent=None):
        super().__init__(parent)
        from autopark.perception.surround_view import BODY
        self.setFormat(_format())
        self.setMinimumSize(420, 280)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.cameras = dict(sorted(cameras.items())[:4])
        self.is_preview = is_preview
        self.body = body or BODY
        center = ((self.body.x_min + self.body.x_max) / 2, (self.body.y_min + self.body.y_max) / 2)
        self.bowl = bowl or s3.Bowl(center_xy=center)
        self.view = s3.PRESETS["sau_phai"][1]
        self._frames: dict[int, np.ndarray] = {}
        self._dirty_frames: set[int] = set()
        self._fill = np.array([0.30, 0.31, 0.32])
        self._overlays: s3.Overlays | None = None
        self._overlays_dirty = True
        self._drag: tuple[QPointF, s3.View] | None = None
        self.on_manual_view = None          # gọi khi người dùng kéo tay (bỏ chọn góc nhìn đặt sẵn)
        self._ready = False
        self.error: Exception | None = None
        self.frames_drawn = 0

    # ------------------------------------------------------------------ đầu vào
    def set_frames(self, frames: dict[int, np.ndarray]) -> None:
        for port, frame in frames.items():
            if port in self.cameras and frame is not None and frame.ndim == 3 and frame.dtype == np.uint8:
                self._frames[port] = np.ascontiguousarray(frame)
                self._dirty_frames.add(port)
        if self._frames:                                    # màu sàn trung bình: nửa dưới của các ảnh
            samples = [f[f.shape[0] // 2::8, ::8].reshape(-1, 3) for f in self._frames.values()]
            bgr = np.median(np.vstack(samples), axis=0) / 255.0
            self._fill = bgr[::-1]
        self.update()

    def clear_frames(self) -> None:
        self._frames.clear()
        self._dirty_frames.clear()
        self.update()

    def set_overlays(self, overlays: s3.Overlays | None) -> None:
        self._overlays = overlays
        self._overlays_dirty = True
        self.update()

    def set_view(self, view: s3.View) -> None:
        self.view = view.clamped()
        self.update()

    # ------------------------------------------------------------------ chuột
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = (event.position(), self.view)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            if self.on_manual_view is not None:
                self.on_manual_view()

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            start, base = self._drag
            delta = event.position() - start
            self.set_view(s3.replace(base, azimuth_deg=base.azimuth_deg - 0.4 * delta.x(),
                                     elevation_deg=base.elevation_deg + 0.3 * delta.y()))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def wheelEvent(self, event):
        steps = -event.angleDelta().y() / 120.0
        self.set_view(s3.replace(self.view, distance_m=self.view.distance_m * (1.1 ** steps)))

    # ------------------------------------------------------------------ OpenGL
    def _program(self, vs: str, fs: str) -> QOpenGLShaderProgram:
        program = QOpenGLShaderProgram(self)
        if not (program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, vs)
                and program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, fs) and program.link()):
            raise RuntimeError("Lỗi shader cảnh 3D: " + program.log())
        return program

    def _buffer(self, data: np.ndarray, layout) -> list:
        vao = QOpenGLVertexArrayObject(self)
        vao.create()
        vao.bind()
        vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        vbo.create()
        vbo.bind()
        vbo.allocate(data.tobytes(), data.nbytes)
        stride = sum(n for _, n in layout) * 4
        offset = 0
        for location, size in layout:
            self.gl.glEnableVertexAttribArray(location)
            self.bowl_program.setAttributeBuffer(location, GL_FLOAT, offset, size, stride)
            offset += size * 4
        vao.release()
        return [vao, vbo, len(data)]

    @staticmethod
    def _refill(item: list, data: np.ndarray) -> None:
        """Nạp lại dữ liệu vào bộ đệm có sẵn (không tạo bộ đệm mới mỗi lần đổi lớp vẽ chồng)."""
        item[1].bind()
        payload = data.tobytes() if len(data) else np.zeros(7, np.float32).tobytes()
        item[1].allocate(payload, len(payload))
        item[2] = len(data)

    def initializeGL(self):
        try:
            self._initialize()
        except Exception as exc:  # noqa: BLE001 - Qt nuốt lỗi trong initializeGL: in ra và đánh dấu
            import traceback
            traceback.print_exc()
            self.error = exc

    def _initialize(self):
        self.error = None
        self.gl = self.context().functions()
        self.bg_program = self._program(BG_VS, BG_FS)
        self.bowl_program = self._program(BOWL_VS, BOWL_FS)
        self.lit_program = self._program(LIT_VS, LIT_FS)
        self.flat_program = self._program(FLAT_VS, FLAT_FS)
        self._bg = self._buffer(np.array([[-1, -1], [3, -1], [-1, 3]], np.float32), [(0, 2)])
        self._bowl = self._buffer(bowl_mesh(self.bowl), [(0, 3)])
        self._car = self._buffer(car_mesh(self.body), [(0, 3), (1, 3), (2, 4)])
        empty = np.zeros((1, 7), np.float32)
        self._overlay_tris = self._buffer(empty, [(0, 3), (1, 4)])
        self._overlay_points = self._buffer(empty, [(0, 3), (1, 4)])
        self._overlay_tris[2] = self._overlay_points[2] = 0
        self.textures: dict[int, QOpenGLTexture] = {}
        self._transfer = QOpenGLPixelTransferOptions()
        self._transfer.setAlignment(1)
        for port, camera in self.cameras.items():
            intr = camera.calibration.intrinsics
            tex = QOpenGLTexture(QOpenGLTexture.Target.Target2D)
            tex.setSize(intr.width, intr.height)
            tex.setFormat(QOpenGLTexture.TextureFormat.RGB8_UNorm)
            tex.allocateStorage()
            tex.setMinificationFilter(QOpenGLTexture.Filter.Linear)
            tex.setMagnificationFilter(QOpenGLTexture.Filter.Linear)
            tex.setWrapMode(QOpenGLTexture.WrapMode.ClampToEdge)
            self.textures[port] = tex
        self._dirty_frames = set(self._frames)
        self._overlays_dirty = True
        self._ready = True

    def _upload(self):
        for port in list(self._dirty_frames):
            frame, tex = self._frames.get(port), self.textures.get(port)
            if frame is not None and tex is not None and frame.shape[1] == tex.width() and frame.shape[0] == tex.height():
                tex.setData(QOpenGLTexture.PixelFormat.BGR, QOpenGLTexture.PixelType.UInt8, frame.tobytes(),
                            self._transfer)
        self._dirty_frames.clear()
        if self._overlays_dirty:
            tris, points = overlay_geometry(self._overlays)
            self._refill(self._overlay_tris, tris)
            self._refill(self._overlay_points, points)
            self._overlays_dirty = False

    def mvp(self) -> QMatrix4x4:
        view = self.view
        position, right, down, forward = view.basis()
        aspect = max(self.width(), 1) / max(self.height(), 1)
        vfov = math.degrees(2 * math.atan(math.tan(math.radians(view.fov_deg) / 2) / max(aspect, 1e-3)))
        proj = QMatrix4x4()
        proj.perspective(max(vfov, 20.0), aspect, 0.02, 20.0)
        look = QMatrix4x4()
        look.lookAt(QVector3D(*position), QVector3D(*(position + forward)), QVector3D(*(-down)))
        return proj * look

    def _draw(self, item, mode):
        vao, _, count = item
        if count:
            vao.bind()
            self.gl.glDrawArrays(mode, 0, count)
            vao.release()

    def paintGL(self):
        if not self._ready:
            return
        gl = self.gl
        self._upload()
        gl.glClearColor(*BG_BOTTOM, 1.0)
        gl.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        mvp = self.mvp()
        position = self.view.basis()[0]

        # nền chuyển màu (không ghi chiều sâu)
        gl.glDisable(GL_DEPTH_TEST)
        bg = self.bg_program
        bg.bind()
        bg.setUniformValue(bg.uniformLocation("top"), QVector3D(*BG_TOP))
        bg.setUniformValue(bg.uniformLocation("bottom"), QVector3D(*BG_BOTTOM))
        self._draw(self._bg, GL_TRIANGLES)
        gl.glEnable(GL_DEPTH_TEST)

        # mặt bát có ảnh camera
        p = self.bowl_program
        p.bind()
        loc = p.uniformLocation
        p.setUniformValue("mvp", mvp)
        p.setUniformValue(loc("preview"), 1 if self.is_preview else 0)
        p.setUniformValue(loc("anyLive"), 1 if self._frames else 0)
        b = self.body
        p.setUniformValue(loc("body"), QVector4D(b.x_min, b.x_max, b.y_min, b.y_max))
        p.setUniformValue(loc("center"), QVector2D(*self.bowl.center_xy))
        p.setUniformValue(loc("fillColor"), QVector3D(*self._fill))
        p.setUniformValue(loc("fogColor"), QVector3D(*[(t + u) / 2 for t, u in zip(BG_TOP, BG_BOTTOM)]))
        p.setUniformValue(loc("fog"), QVector2D(self.bowl.floor_radius_m * 1.05, self.bowl.rim_radius_m * 0.8))
        for i in range(4):
            p.setUniformValue(loc(f"tex{i}"), i)
            p.setUniformValue(loc(f"camLive[{i}]"), 0)
        for i, (port, camera) in enumerate(list(self.cameras.items())[:4]):
            calib, intr = camera.calibration, camera.calibration.intrinsics
            rot = calib.extrinsics.rotation                          # camera → xe; hàng của R^T = cột của R
            p.setUniformValue(loc(f"camR0[{i}]"), QVector3D(*rot[:, 0]))
            p.setUniformValue(loc(f"camR1[{i}]"), QVector3D(*rot[:, 1]))
            p.setUniformValue(loc(f"camR2[{i}]"), QVector3D(*rot[:, 2]))
            p.setUniformValue(loc(f"camT[{i}]"), QVector3D(*calib.extrinsics.translation))
            p.setUniformValue(loc(f"camK[{i}]"), QVector4D(*intr.k))
            p.setUniformValue(loc(f"camC[{i}]"), QVector4D(intr.cx, intr.cy, intr.aspect_ratio, intr.theta_max))
            p.setUniformValue(loc(f"camSize[{i}]"), QVector2D(intr.width, intr.height))
            p.setUniformValue(loc(f"camLive[{i}]"), 1 if port in self._frames else 0)
            self.textures[port].bind(i)
        self._draw(self._bowl, GL_TRIANGLES)

        # lớp vẽ chồng trên sàn (trong suốt nhẹ)
        gl.glEnable(GL_BLEND)
        gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        f = self.flat_program
        f.bind()
        f.setUniformValue("mvp", mvp)
        f.setUniformValue(f.uniformLocation("roundDots"), 0)
        self._draw(self._overlay_tris, GL_TRIANGLES)

        # xe có ánh sáng
        gl.glDisable(GL_BLEND)
        lit = self.lit_program
        lit.bind()
        lit.setUniformValue("mvp", mvp)
        lit.setUniformValue(lit.uniformLocation("eye"), QVector3D(*position))
        self._draw(self._car, GL_TRIANGLES)

        # điểm LiDAR tròn phát sáng
        gl.glEnable(GL_BLEND)
        gl.glEnable(GL_PROGRAM_POINT_SIZE)
        f.bind()
        f.setUniformValue("mvp", mvp)
        f.setUniformValue(f.uniformLocation("roundDots"), 1)
        f.setUniformValue1f("pointSize", 7.0 * self.devicePixelRatio())
        self._draw(self._overlay_points, GL_POINTS)
        gl.glDisable(GL_BLEND)
        self.frames_drawn += 1
