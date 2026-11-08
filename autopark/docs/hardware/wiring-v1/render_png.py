r"""Rebuild and export the reviewed wiring drawings as high-resolution PNGs.

From the Python project directory:
    .venv\Scripts\python.exe docs/hardware/wiring-v1/render_png.py

No hardware, network, browser or source photographs are used. All image pixels
come from the deterministic SVG sources and the installed Segoe UI font.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import xml.etree.ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, qVersion
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

OUT = Path(__file__).resolve().parent
SHEETS = ("00-components", "01-system", "02-signal-feedback", "03-charging")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def svg_dimensions(path: Path) -> tuple[int, int]:
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    if root.tag != "{http://www.w3.org/2000/svg}svg":
        raise ValueError(f"Not an SVG document: {path.name}")
    viewbox = root.get("viewBox", "").split()
    if len(viewbox) != 4:
        raise ValueError(f"Missing four-value viewBox: {path.name}")
    values = [float(v) for v in viewbox]
    if values[:2] != [0.0, 0.0] or any(not math.isfinite(v) for v in values):
        raise ValueError(f"Unsupported viewBox: {path.name}")
    width, height = values[2:]
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid dimensions: {path.name}")
    for node in root.iter():
        if node.tag.endswith("foreignObject"):
            raise ValueError(f"foreignObject is not portable to QtSvg: {path.name}")
        for key, value in node.attrib.items():
            if key.endswith("href") and not value.startswith("#"):
                raise ValueError(f"External/embedded media is not allowed: {path.name}")
    return round(width), round(height)


def render_one(stem: str, scale: float) -> dict:
    source = OUT / f"{stem}.svg"
    target = OUT / f"{stem}.png"
    width, height = svg_dimensions(source)
    renderer = QSvgRenderer(str(source))
    if not renderer.isValid():
        raise ValueError(f"QtSvg rejected {source.name}")
    pixel_width, pixel_height = round(width * scale), round(height * scale)
    canvas = QImage(pixel_width, pixel_height, QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(QColor("white"))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    renderer.render(painter, QRectF(0, 0, pixel_width, pixel_height))
    painter.end()
    if not canvas.save(str(target), "PNG"):
        raise OSError(f"Cannot write {target.name}")
    loaded = QImage(str(target))
    if loaded.isNull() or (loaded.width(), loaded.height()) != (pixel_width, pixel_height):
        raise ValueError(f"PNG could not be reopened at the expected size: {target.name}")
    sample = loaded.scaled(96, 96)
    dark_pixels = sum(
        max(sample.pixelColor(x, y).red(), sample.pixelColor(x, y).green(), sample.pixelColor(x, y).blue()) < 200
        for y in range(sample.height()) for x in range(sample.width())
    )
    if dark_pixels < 60:
        raise ValueError(f"PNG appears blank or missing content: {target.name}")
    return {
        "svg": source.name, "png": target.name,
        "svg_size": [width, height], "png_size": [pixel_width, pixel_height],
        "svg_sha256": digest(source), "png_sha256": digest(target),
        "png_bytes": target.stat().st_size, "nonblank_check": True,
    }


def write_index() -> None:
    content = """# Bản vẽ 2D kết nối AutoPark

Các bản vẽ thể hiện phương án ESP32-S3 + ESC rời, có các nhánh chưa xác minh được đánh dấu. Đây là tài liệu thiết kế, chưa nghiệm thu điện hoặc chạy xe thật.

| Tờ | PNG để xem | SVG để phóng to |
|---|---|---|
| Linh kiện và điểm nối | [00-components.png](00-components.png) | [00-components.svg](00-components.svg) |
| Nguồn và chấp hành | [01-system.png](01-system.png) | [01-system.svg](01-system.svg) |
| Tín hiệu, phản hồi và USB | [02-signal-feedback.png](02-signal-feedback.png) | [02-signal-feedback.svg](02-signal-feedback.svg) |
| Sạc pin tách khỏi xe | [03-charging.png](03-charging.png) | [03-charging.svg](03-charging.svg) |

[Hướng dẫn lắp và các điều kiện cần xác minh](../../LAP_RAP_DIEN_2D.md) · [Review độc lập](REVIEW.md) · [Nguồn hình linh kiện](component_notes.md)

## Dựng lại

Từ thư mục dự án Python `autopark/`:

```powershell
.\\.venv\\Scripts\\python.exe docs/hardware/wiring-v1/render_png.py
```

Script dựng lại SVG, xuất PNG ở tỷ lệ 2×, kiểm XML/QtSvg, kích thước và ảnh không rỗng, rồi ghi `export_manifest.json` với hash. Dùng `--no-rebuild` nếu chỉ muốn xuất các SVG đang có; dùng `--scale 1.5` để đổi độ phân giải. Không mở thiết bị hoặc gọi mạng.

`components.py` chứa hình linh kiện và tọa độ pad; `build_wiring.py` ghép các dây và ghi `wiring_spec.json`. Netlist và hình là kiểm tra nhất quán của thiết kế, không phải mô phỏng điện hay bằng chứng phần cứng tương thích. Ảnh gốc người dùng không được nhúng hoặc xuất bản trong bộ tệp này.
"""
    (OUT / "README.md").write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale", type=float, default=2.0)
    parser.add_argument("--no-rebuild", action="store_true")
    args = parser.parse_args()
    if not math.isfinite(args.scale) or not 0.5 <= args.scale <= 3.0:
        parser.error("--scale must be between 0.5 and 3")
    app = QApplication.instance() or QApplication([])
    font_directory = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
        path = font_directory / name
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    families = set(QFontDatabase.families())
    if "Segoe UI" not in families:
        raise RuntimeError("Segoe UI is required for the reviewed Vietnamese text layout")
    app.setFont(QFont("Segoe UI", 10))
    from components import component_catalog_svg
    (OUT / "00-components.svg").write_text(component_catalog_svg(), encoding="utf-8")
    if not args.no_rebuild:
        from build_wiring import main as build
        build()
    exported = [render_one(stem, args.scale) for stem in SHEETS]
    manifest = {
        "schema_version": 1, "scope": "proposed_design_not_hardware_verified",
        "renderer": "QtSvg", "qt_version": qVersion(), "font": "Segoe UI",
        "scale": args.scale, "external_media": False,
        "sources": {name: digest(OUT / name) for name in ("components.py", "build_wiring.py", "render_png.py", "wiring_spec.json")},
        "artifacts": exported,
        "checks": ["SVG XML and viewBox parsed", "No external or embedded media", "QtSvg accepted all sheets", "PNGs reopened at expected dimensions", "Nonblank raster samples"],
    }
    (OUT / "export_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_index()
    print(json.dumps({"exported": [entry["png"] for entry in exported], "validated": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
