"""Vẽ cảnh 3D quanh xe bằng GPU (OpenGL 3.3 qua Qt, thêm 26/11/2026).

```
CPU (một lần)                      GPU (mỗi lần vẽ, ~60 khung/giây)
├── lưới tam giác mặt bát ───────► vị trí từng điểm trên bát
├── thông số 4 camera ───────────► shader chiếu fisheye + trộn 4 ảnh cho TỪNG PIXEL
└── ảnh camera mới (khi có) ─────► 4 texture
Xoay / phóng to: chỉ đổi một ma trận, không tính lại gì trên CPU.
```

Công thức chiếu và trộn giống hệt bản CPU (`perception/surround_3d.py`): đa thức fisheye ρ(θ), bỏ điểm sau lưng camera
khi đang xem thử gá giả định, trọng số ưu tiên tâm ống kính và camera gần hơn.
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
GL_LINES = 0x0001
GL_POINTS = 0x0000
GL_DEPTH_TEST = 0x0B71
GL_PROGRAM_POINT_SIZE = 0x8642
GL_COLOR_BUFFER_BIT = 0x4000
GL_DEPTH_BUFFER_BIT = 0x0100
GL_BLEND = 0x0BE2
GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA = 0x0302, 0x0303

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
uniform vec4 camK[4];       // đa thức rho(theta) = theta*(k1 + theta*(k2 + theta*(k3 + theta*k4)))
uniform vec4 camC[4];       // cx, cy, tỷ lệ điểm ảnh, theta_max
uniform vec2 camSize[4];
uniform int camLive[4];     // 1 = có ảnh trong texture
uniform int preview;        // gá giả định: không nhìn ra sau lưng camera
uniform vec4 body;          // x_min, x_max, y_min, y_max của thân xe

vec4 sampleCam(int i, sampler2D tex) {
    if (camLive[i] == 0) return vec4(0.0);
    vec3 d = vPos - camT[i];
    vec3 pc = vec3(dot(camR0[i], d), dot(camR1[i], d), dot(camR2[i], d));
    if (preview == 1 && pc.z <= 0.0) return vec4(0.0);
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
    float e = clamp(edge / 64.0, 0.04, 1.0);
    vec2 dh = vPos.xy - camT[i].xy;
    float w = e * e / (1.0 + dot(dh, dh) / 0.16);
    vec3 c = texture(tex, vec2((u + 0.5) / sz.x, (v + 0.5) / sz.y)).rgb;
    return vec4(c * w, w);
}

void main() {
    bool floorPt = vPos.z < 0.002;
    if (vPos.z < 0.02 && vPos.x > body.x - 0.01 && vPos.x < body.y + 0.01
            && vPos.y > body.z - 0.01 && vPos.y < body.w + 0.01) {
        color = vec4(0.06, 0.07, 0.08, 1.0);              // bóng dưới gầm xe
        return;
    }
    vec4 acc = sampleCam(0, tex0) + sampleCam(1, tex1) + sampleCam(2, tex2) + sampleCam(3, tex3);
    if (acc.w > 0.0) {
        color = vec4(acc.rgb / acc.w, 1.0);
        return;
    }
    vec3 base = floorPt ? vec3(0.09, 0.10, 0.12) : vec3(0.11, 0.13, 0.15);
    if (floorPt) {                                         // lưới 10 cm để thấy tỷ lệ khi chưa có ảnh
        vec2 g = abs(fract(vPos.xy / 0.1 + 0.5) - 0.5) / fwidth(vPos.xy / 0.1);
        float line = 1.0 - min(min(g.x, g.y), 1.0);
        base = mix(base, vec3(0.20, 0.23, 0.26), line * 0.7);
    }
    color = vec4(base, 1.0);
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
void main() { color = vColor; }
"""


def bowl_mesh(bowl: s3.Bowl, rings_floor: int = 36, rings_wall: int = 48, segments: int = 180) -> np.ndarray:
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


def _rgba(bgr, alpha: float = 1.0) -> tuple:
    b, g, r = bgr
    return (r / 255.0, g / 255.0, b / 255.0, alpha)


def body_geometry(body, height: float = s3.BODY_HEIGHT_M):
    """(tam giác, đường viền) của hộp thân xe, mỗi đỉnh 7 số: x y z r g b a."""
    corners = [(body.x_min, body.y_min), (body.x_max, body.y_min), (body.x_max, body.y_max), (body.x_min, body.y_max)]
    lo = [(x, y, 0.0) for x, y in corners]
    hi = [(x, y, height) for x, y in corners]
    faces = [(hi, (212, 196, 176)),                                        # nóc
             ([lo[0], lo[1], hi[1], hi[0]], (150, 132, 112)), ([lo[1], lo[2], hi[2], hi[1]], (176, 158, 136)),
             ([lo[2], lo[3], hi[3], hi[2]], (150, 132, 112)), ([lo[3], lo[0], hi[0], hi[3]], (120, 104, 88))]
    tris = []
    for quad, color in faces:
        rgba = _rgba(color)
        for idx in ((0, 1, 2), (0, 2, 3)):
            tris += [(*quad[i], *rgba) for i in idx]
    edge = _rgba((235, 228, 214))
    lines = []
    for ring in (lo, hi):
        for i in range(4):
            lines += [(*ring[i], *edge), (*ring[(i + 1) % 4], *edge)]
    for i in range(4):
        lines += [(*lo[i], *edge), (*hi[i], *edge)]
    z = height + 0.002                                                    # mũi tên chỉ đầu xe trên nóc
    tail, tip = (body.x_min + 0.06, 0.0, z), (body.x_max - 0.03, 0.0, z)
    dark = _rgba((36, 30, 26))
    head = 0.04
    lines += [(*tail, *dark), (*tip, *dark),
              (*tip, *dark), (tip[0] - head, 0.025, z, *dark), (*tip, *dark), (tip[0] - head, -0.025, z, *dark)]
    return np.array(tris, np.float32), np.array(lines, np.float32)


def overlay_geometry(overlays: s3.Overlays | None):
    """(đường trên sàn, điểm LiDAR), mỗi đỉnh 7 số."""
    lines, points = [], []
    if overlays is None:
        return np.zeros((0, 7), np.float32), np.zeros((0, 7), np.float32)
    slot_color, path_color = _rgba((214, 240, 140)), _rgba((107, 183, 239))
    for corners in overlays.slots:
        c = list(corners)
        for a, b in zip(c, c[1:] + c[:1]):
            lines += [(a[0], a[1], 0.003, *slot_color), (b[0], b[1], 0.003, *slot_color)]
    if overlays.path_xy is not None:
        p = np.asarray(overlays.path_xy, np.float64).reshape(-1, 2)
        for a, b in zip(p, p[1:]):
            lines += [(a[0], a[1], 0.003, *path_color), (b[0], b[1], 0.003, *path_color)]
    if overlays.lidar_xy is not None:
        dot = _rgba((102, 209, 255))
        points = [(x, y, overlays.lidar_z, *dot) for x, y in np.asarray(overlays.lidar_xy).reshape(-1, 2)]
    return np.array(lines, np.float32).reshape(-1, 7), np.array(points, np.float32).reshape(-1, 7)


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
        self._overlays: s3.Overlays | None = None
        self._overlays_dirty = True
        self._drag: tuple[QPointF, s3.View] | None = None
        self._ready = False
        self.frames_drawn = 0

    # ------------------------------------------------------------------ đầu vào
    def set_frames(self, frames: dict[int, np.ndarray]) -> None:
        for port, frame in frames.items():
            if port in self.cameras and frame is not None and frame.ndim == 3 and frame.dtype == np.uint8:
                self._frames[port] = np.ascontiguousarray(frame)
                self._dirty_frames.add(port)
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
        stride = data.shape[1] * 4 if data.ndim == 2 and len(data) else sum(n for _, n in layout) * 4
        offset = 0
        for location, size in layout:
            self.gl.glEnableVertexAttribArray(location)
            self._attr_program.setAttributeBuffer(location, GL_FLOAT, offset, size, stride)
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
        self.gl = self.context().functions()
        self.bowl_program = self._program(BOWL_VS, BOWL_FS)
        self.flat_program = self._program(FLAT_VS, FLAT_FS)
        self._attr_program = self.bowl_program
        self.bowl_program.bind()
        self._bowl = self._buffer(bowl_mesh(self.bowl), [(0, 3)])
        self._attr_program = self.flat_program
        self.flat_program.bind()
        tris, lines = body_geometry(self.body)
        self._body_tris = self._buffer(tris, [(0, 3), (1, 4)])
        self._body_lines = self._buffer(lines, [(0, 3), (1, 4)])
        empty = np.zeros((1, 7), np.float32)
        self._overlay_lines = self._buffer(empty, [(0, 3), (1, 4)])
        self._overlay_points = self._buffer(empty, [(0, 3), (1, 4)])
        self._overlay_lines[2] = self._overlay_points[2] = 0
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
            lines, points = overlay_geometry(self._overlays)
            self._refill(self._overlay_lines, lines)
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
        target = position + forward
        look.lookAt(QVector3D(*position), QVector3D(*target), QVector3D(*(-down)))
        return proj * look

    def paintGL(self):
        gl = self.gl
        self._upload()
        gl.glClearColor(0.055, 0.075, 0.105, 1.0)
        gl.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        gl.glEnable(GL_DEPTH_TEST)
        mvp = self.mvp()

        p = self.bowl_program
        p.bind()
        p.setUniformValue("mvp", mvp)
        p.setUniformValue(p.uniformLocation("preview"), 1 if self.is_preview else 0)
        b = self.body
        p.setUniformValue(p.uniformLocation("body"), QVector4D(b.x_min, b.x_max, b.y_min, b.y_max))
        for i in range(4):
            p.setUniformValue(p.uniformLocation(f"tex{i}"), i)
            p.setUniformValue(p.uniformLocation(f"camLive[{i}]"), 0)
        for i, (port, camera) in enumerate(list(self.cameras.items())[:4]):
            calib = camera.calibration
            rot = calib.extrinsics.rotation                          # camera → xe; hàng của R^T = cột của R
            intr = calib.intrinsics
            loc = p.uniformLocation
            p.setUniformValue(loc(f"camR0[{i}]"), QVector3D(*rot[:, 0]))
            p.setUniformValue(loc(f"camR1[{i}]"), QVector3D(*rot[:, 1]))
            p.setUniformValue(loc(f"camR2[{i}]"), QVector3D(*rot[:, 2]))
            p.setUniformValue(loc(f"camT[{i}]"), QVector3D(*calib.extrinsics.translation))
            p.setUniformValue(loc(f"camK[{i}]"), QVector4D(*intr.k))
            p.setUniformValue(loc(f"camC[{i}]"), QVector4D(intr.cx, intr.cy, intr.aspect_ratio, intr.theta_max))
            p.setUniformValue(loc(f"camSize[{i}]"), QVector2D(intr.width, intr.height))
            p.setUniformValue(loc(f"camLive[{i}]"), 1 if port in self._frames else 0)
            self.textures[port].bind(i)
        vao, _, count = self._bowl
        vao.bind()
        gl.glDrawArrays(GL_TRIANGLES, 0, count)
        vao.release()

        f = self.flat_program
        f.bind()
        f.setUniformValue("mvp", mvp)
        f.setUniformValue1f("pointSize", 4.0)
        gl.glEnable(GL_PROGRAM_POINT_SIZE)
        for item, mode in ((self._body_tris, GL_TRIANGLES), (self._body_lines, GL_LINES),
                           (self._overlay_lines, GL_LINES), (self._overlay_points, GL_POINTS)):
            vao, _, count = item
            if count == 0:
                continue
            vao.bind()
            gl.glDrawArrays(mode, 0, count)
            vao.release()
        self.frames_drawn += 1
