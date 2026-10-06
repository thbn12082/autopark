"""Vẽ một ca đo và đường lập được ra ảnh PNG, để đối chiếu bằng mắt và đưa vào báo cáo.

Dùng:
    python -m autopark.evaluation.render --out thu_muc_ra
    python -m autopark.evaluation.render --planner autopark.planning.cand_x:plan --cases parallel_135 --out ra

Vẽ trực tiếp bằng QPainter lên QImage, không mở cửa sổ nào.
"""
from __future__ import annotations

import argparse
import math
import os
from pathlib import Path

# Plugin "windows" cho font thật (có dấu tiếng Việt); không mở cửa sổ nào vì chỉ vẽ lên QImage.
os.environ.setdefault("QT_QPA_PLATFORM", "windows")

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QBrush, QColor, QFont, QGuiApplication, QImage, QPainter, QPainterPath, QPen, QPolygonF  # noqa: E402

from autopark.domain.types import Pose, Scenario, VehicleConfig  # noqa: E402
from autopark.evaluation.hard_cases import HardCase, build_cases  # noqa: E402
from autopark.geometry.footprint import body_polygon  # noqa: E402
from autopark.planning.trajectory import Trajectory  # noqa: E402
from autopark.power_throttling import apply_ecoqos_policy  # noqa: E402
from autopark.storage.scenario_store import load_vehicle_config  # noqa: E402
from autopark.ui.items import (  # noqa: E402
    COLOR_EGO_BODY,
    COLOR_EGO_OUTLINE,
    COLOR_EGO_WINDOW,
    COLOR_PARKED_BODY,
    COLOR_PARKED_WINDOW,
    paint_car,
)

BG = QColor("#17191d")
FLOOR = QColor("#2b2e35")
GRID = QColor("#363a43")
FRAME = QColor("#9aa0aa")
FORWARD = QColor("#4cd964")
REVERSE = QColor("#ff9f0a")
SLOT = QColor("#4cd964")
BOX = QColor("#8a6d3b")
WALL = QColor("#5a5f6a")
TEXT = QColor("#e6e8eb")
MUTED = QColor("#9aa0aa")

_app = None


def _ensure_app() -> None:
    global _app
    if QGuiApplication.instance() is None:
        _app = QGuiApplication([])


def _pen(color: QColor, width: float = 2.0, style=Qt.PenStyle.SolidLine) -> QPen:
    p = QPen(color, width, style)
    p.setCosmetic(True)
    return p


def render_case(case: HardCase, cfg: VehicleConfig, trajectory: Trajectory | None = None,
                width_px: int = 1200, caption: str = "") -> QImage:
    _ensure_app()
    sc: Scenario = case.scenario
    b = sc.bounds
    pad = 0.10
    world_w, world_h = b.width + 2 * pad, b.height + 2 * pad
    header = 74
    scale = width_px / world_w
    height_px = int(world_h * scale) + header

    img = QImage(width_px, height_px, QImage.Format.Format_RGB32)
    img.fill(BG)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # Tiêu đề vẽ theo pixel, trước khi đổi hệ toạ độ
    painter.setPen(_pen(TEXT, 1.0))
    painter.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
    painter.drawText(QRectF(14, 8, width_px - 28, 26), Qt.AlignmentFlag.AlignLeft,
                     f"{case.name}   [{case.difficulty} / {case.expected}]")
    painter.setPen(_pen(MUTED, 1.0))
    painter.setFont(QFont("Segoe UI", 10))
    painter.drawText(QRectF(14, 34, width_px - 28, 34), Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
                     caption or case.note)

    # Hệ toạ độ bản đồ: mét, y hướng lên
    painter.save()
    painter.translate(0, height_px)
    painter.scale(scale, -scale)
    painter.translate(pad - b.xmin, pad - b.ymin)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(FLOOR)
    painter.drawRect(QRectF(b.xmin, b.ymin, b.width, b.height))
    painter.setPen(_pen(GRID, 1.0))
    x = b.xmin
    while x <= b.xmax + 1e-9:
        painter.drawLine(QPointF(x, b.ymin), QPointF(x, b.ymax))
        x += 0.10
    y = b.ymin
    while y <= b.ymax + 1e-9:
        painter.drawLine(QPointF(b.xmin, y), QPointF(b.xmax, y))
        y += 0.10
    painter.setPen(_pen(FRAME, 2.0))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(QRectF(b.xmin, b.ymin, b.width, b.height))

    # Vùng thân xe quét
    if trajectory is not None and trajectory.points:
        from shapely.ops import unary_union
        polys, last_s = [], -1.0
        for p in trajectory.points:
            if p.s - last_s >= 0.03 or p is trajectory.points[-1]:
                polys.append(body_polygon(cfg, p.pose))
                last_s = p.s
        union = unary_union(polys)
        path = QPainterPath()
        for geom in getattr(union, "geoms", [union]):
            path.addPolygon(QPolygonF([QPointF(px, py) for px, py in geom.exterior.coords]))
            for interior in geom.interiors:
                path.addPolygon(QPolygonF([QPointF(px, py) for px, py in interior.coords]))
        painter.setPen(_pen(QColor(76, 217, 100, 90), 1.0))
        painter.setBrush(QBrush(QColor(76, 217, 100, 34)))
        painter.drawPath(path)

    # Ô đỗ
    if sc.slot is not None:
        painter.save()
        painter.translate(sc.slot.cx, sc.slot.cy)
        painter.rotate(math.degrees(sc.slot.yaw))
        hl, hw = sc.slot.length / 2, sc.slot.width / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(76, 217, 100, 30)))
        painter.drawRect(QRectF(-hl, -hw, sc.slot.length, sc.slot.width))
        painter.setPen(_pen(SLOT, 2.5))
        painter.drawLine(QPointF(-hl, -hw), QPointF(hl, -hw))
        painter.drawLine(QPointF(-hl, hw), QPointF(hl, hw))
        painter.drawLine(QPointF(hl, -hw), QPointF(hl, hw))
        painter.setPen(_pen(SLOT, 1.5, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(-hl, -hw), QPointF(-hl, hw))
        painter.restore()

    # Vật cản
    for o in sc.obstacles:
        painter.save()
        painter.translate(o.cx, o.cy)
        painter.rotate(math.degrees(o.yaw))
        if o.kind == "car":
            rear_len, front_len = o.width * 0.22, o.width * 0.18
            wb = o.width - rear_len - front_len
            painter.translate(-o.width / 2 + rear_len, 0.0)
            paint_car(painter, -rear_len, wb, wb + front_len, o.height / 2,
                      COLOR_PARKED_BODY, COLOR_PARKED_WINDOW, COLOR_PARKED_BODY.lighter(130))
        else:
            color = WALL if o.kind == "wall" else BOX
            painter.setPen(_pen(color.lighter(140), 1.5))
            painter.setBrush(QBrush(color, Qt.BrushStyle.BDiagPattern if o.kind == "wall" else Qt.BrushStyle.SolidPattern))
            painter.drawRect(QRectF(-o.width / 2, -o.height / 2, o.width, o.height))
        painter.restore()

    # Đường đi: xanh khi tiến, cam khi lùi
    if trajectory is not None and trajectory.points:
        for si, (a, bb) in enumerate(trajectory.segments):
            pts = trajectory.points[a:bb + 1]
            path = QPainterPath()
            path.moveTo(pts[0].pose.x, pts[0].pose.y)
            for p in pts[1:]:
                path.lineTo(p.pose.x, p.pose.y)
            painter.setPen(_pen(FORWARD if pts[0].direction > 0 else REVERSE, 3.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
            if si > 0:
                painter.setPen(_pen(QColor("#ffffff"), 1.5))
                painter.setBrush(QBrush(REVERSE))
                painter.drawEllipse(QPointF(pts[0].pose.x, pts[0].pose.y), 0.014, 0.014)

    # Xe đích (nét đứt) và xe xuất phát
    for pose, body, window, outline, dashed in (
        (sc.goal.pose, QColor(76, 217, 100, 60), QColor(40, 90, 60, 90), SLOT, True),
        (sc.start, QColor(143, 180, 255, 90), QColor(40, 60, 90, 120), QColor("#8fb4ff"), False),
    ):
        painter.save()
        painter.translate(pose.x, pose.y)
        painter.rotate(math.degrees(pose.yaw))
        paint_car(painter, -cfg.rear_overhang, cfg.wheelbase, cfg.wheelbase + cfg.front_overhang,
                  cfg.width / 2, body, window, outline, 0.0, dashed)
        painter.restore()

    painter.restore()
    painter.end()
    return img


def main(argv: list[str] | None = None) -> int:
    ecoqos = apply_ecoqos_policy("evaluation.render")  # trước mọi việc khác: --planner chạy theo hạn giờ đồng hồ thật
    ap = argparse.ArgumentParser(description="Vẽ ca đo ra PNG")
    ap.add_argument("--planner", default="", help="module:ham; bỏ trống thì chỉ vẽ ca, không lập đường")
    ap.add_argument("--config", default="configs/vehicle_default.json")
    ap.add_argument("--cases", default="")
    ap.add_argument("--time-limit", type=float, default=20.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    print(ecoqos.cli_line())

    cfg = load_vehicle_config(args.config)
    cases = build_cases(cfg)
    names = [n.strip() for n in args.cases.split(",") if n.strip()] or list(cases)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    func = None
    if args.planner:
        from autopark.evaluation.bench import load_planner
        func = load_planner(args.planner)

    for name in names:
        case = cases[name]
        traj, caption = None, case.note
        if func is not None:
            from autopark.evaluation.bench import _call_planner
            result = _call_planner(func, case, cfg, args.time_limit)
            traj = result.trajectory
            caption = f"{result.status} — {result.message} ({result.elapsed:.2f} s)"
        img = render_case(case, cfg, traj, caption=caption)
        path = out_dir / f"{name}.png"
        img.save(str(path))
        print(f"đã vẽ {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
