"""Sinh SVG + PNG luồng tính đường mục tiêu, không đọc ảnh hoặc mã ứng dụng.

Chạy bằng Python có PySide6. --check so byte, không ghi tệp.
Mỗi lần chạy chỉ ghi luong-tinh-duong.svg và luong-tinh-duong.png cạnh mã này.
"""
from __future__ import annotations

import argparse
from html import escape
import math
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRectF
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

WIDTH, HEIGHT = 1800, 2240
INK = "#173247"
MUTED = "#526779"
BLUE = "#126ba3"
GREEN = "#087c65"
PURPLE = "#7652aa"
RED = "#a63040"
LINE = "#c4d3df"
BG = "#f4f8fb"
FONT = "Segoe UI"


class Drawing:
    def __init__(self):
        self.parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
            '<title>Luồng tính đường mục tiêu: Laptop – Raspberry Pi – ESP32</title>',
            '<desc>Thiết kế chưa triển khai phân tán, chưa kiểm chứng xe thật. Cảm biến tới Pi, Wi-Fi tới laptop AI và hợp nhất, chọn ô đỗ dự kiến, lập và kiểm quỹ đạo, người vận hành xác nhận, Pi kiểm và bám, ESP32 điều khiển và phản hồi. Vật cản hoặc dữ liệu cũ làm dừng; lập lại từ tư thế đo sau dừng và xác nhận lượt mới.</desc>',
            f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{BG}"/>',
            f'<g font-family="{FONT}" fill="{INK}">',
        ]

    def rect(self, x, y, w, h, fill="white", stroke=LINE, radius=16):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')

    def text(self, x, y, value, size=20, color=INK, bold=False, max_width=None, anchor="start"):
        # Catch line overflow before publishing an image. Text stays selectable in SVG.
        font = QFont(FONT)
        font.setPixelSize(size)
        font.setBold(bold)
        measured = QFontMetricsF(font).horizontalAdvance(value)
        if max_width is not None and measured > max_width:
            raise ValueError(f"Dòng vượt khung ({measured:.1f} > {max_width}): {value}")
        left = x - measured / 2 if anchor == "middle" else x
        if left < 0 or left + measured > WIDTH or y > HEIGHT:
            raise ValueError(f"Chữ vượt trang: {value}")
        self.parts.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{700 if bold else 400}" text-anchor="{anchor}">{escape(value)}</text>')

    def card(self, x, y, w, h, title, lines, color=BLUE, fill="white"):
        self.rect(x, y, w, h, fill, color)
        self.text(x + 20, y + 36, title, 23, color, True, w - 40)
        for n, value in enumerate(lines):
            baseline = y + 72 + n * 28
            if baseline > y + h - 16:
                raise ValueError(f"Thẻ quá thấp: {title}")
            self.text(x + 20, baseline, value, 20, max_width=w - 40)

    def arrow(self, points, color=BLUE, dashed=False):
        path = "M " + " L ".join(f"{x},{y}" for x, y in points)
        dash = ' stroke-dasharray="8 6"' if dashed else ""
        self.parts.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"{dash}/>')
        # Explicit triangle: supported identically by Qt SVG and browser renderers.
        (ax, ay), (bx, by) = points[-2:]
        angle = math.atan2(by - ay, bx - ax)
        ux, uy = math.cos(angle), math.sin(angle)
        pts = [(bx, by), (bx - 11 * ux + 5 * uy, by - 11 * uy - 5 * ux),
               (bx - 11 * ux - 5 * uy, by - 11 * uy + 5 * ux)]
        coords = " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
        self.parts.append(f'<polygon points="{coords}" fill="{color}"/>')

    def connector(self, x, y, letter, color=BLUE):
        self.parts.append(f'<circle cx="{x}" cy="{y}" r="18" fill="white" stroke="{color}" stroke-width="2"/>')
        self.text(x, y + 7, letter, 20, color, True, anchor="middle")

    def lane(self, x, y, w, h, title, color, fill):
        self.rect(x, y, w, h, fill, LINE, 20)
        self.text(x + 20, y + 39, title, 24, color, True, w - 40)

    def finish(self):
        return ("\n".join(self.parts + ["</g>", "</svg>", ""])).encode("utf-8")


def build_svg():
    d = Drawing()
    d.text(40, 55, "TỪ CẢM BIẾN ĐẾN QUỸ ĐẠO VÀ XE DỪNG", 36, INK, True)
    d.text(40, 94, "KIẾN TRÚC MỤC TIÊU · Chưa triển khai phân tán qua Pi · Chưa kiểm chứng chạy xe thật", 23, RED, True)
    d.text(40, 130, "Hiện có: mô phỏng / đích gần do người dùng chọn. Tự nhận diện và chọn ô đỗ là phần dự kiến.", 22, MUTED)

    # Band 1: three distinct responsibility lanes. The sensor card is wiring context.
    d.lane(40, 160, 540, 310, "NGUỒN DỮ LIỆU · TRÊN XE", MUTED, "#edf2f7")
    d.lane(620, 160, 540, 310, "RASPBERRY PI · THU VÀ ĐỊNH VỊ", GREEN, "#edf8f3")
    d.lane(1200, 160, 560, 310, "LAPTOP · AI VÀ HỢP NHẤT", BLUE, "#edf5fb")
    d.card(60, 226, 500, 224, "01  Camera, LiDAR, phản hồi", [
        "4 camera USB → hub USB → Pi",
        "LiDAR C1 → adapter USB → Pi",
        "Encoder + góc lái → ESP32",
        "ESP32 → USB ngắn → Pi",
        "Kết nối mục tiêu; cần hiệu chuẩn.",
    ], MUTED)
    d.card(640, 226, 500, 224, "02  Dấu thời gian + tư thế cục bộ", [
        "Mã cảm biến, số thứ tự, thời điểm đo",
        "Kiểm độ mới và đồng bộ các nguồn",
        "LiDAR + phản hồi → (x, y, hướng)",
        "Tốc độ, góc lái đo; chất lượng tư thế",
        "Giám sát vật cản cục bộ trên Pi",
    ], GREEN)
    d.card(1220, 226, 520, 224, "03  AI bốn camera + hợp nhất", [
        "Nhận ảnh, LiDAR, tư thế qua Wi-Fi",
        "AI → bằng chứng trong hệ bản đồ",
        "Hợp nhất camera + LiDAR + tư thế",
        "Vùng chưa rõ không được coi trống",
        "AI không trực tiếp điều khiển lái",
    ])
    d.arrow([(560, 336), (640, 336)], GREEN)
    d.text(600, 319, "USB", 18, GREEN, True, anchor="middle")
    d.arrow([(1140, 336), (1220, 336)])
    d.text(1180, 319, "Wi-Fi", 18, BLUE, True, anchor="middle")

    # Band 2: the laptop pipeline is a numbered serpentine with no crossing lines.
    d.lane(40, 490, 1720, 680, "LAPTOP · CHỌN ĐÍCH, LẬP VÀ KIỂM QUỸ ĐẠO", BLUE, "#edf5fb")
    d.card(1220, 565, 520, 225, "04  Chọn ô trống · DỰ KIẾN", [
        "Nhận diện và xếp hạng ứng viên",
        "Kích thước, độ tin cậy, lối tiếp cận",
        "Xét khoảng hở, quãng đường, tiến/lùi",
        "Không có ứng viên hợp lệ → R",
        "Chưa có bộ chọn ô tự động trong mã",
    ])
    d.card(640, 565, 500, 225, "05  Tư thế đích (x, y, hướng)", [
        "Cùng hệ tọa độ với tư thế đo",
        "Rõ mốc xe, đơn vị và dung sai",
        "Kiểm thân xe ở đích và lối vào",
        "Ghép với tư thế xuất phát mới nhất",
        "Đích không hợp lệ → R",
    ])
    d.card(60, 565, 500, 225, "06  Quỹ đạo tiến / lùi khả thi", [
        "Giới hạn lái, bán kính quay, tốc độ",
        "Gia tốc/phanh, đổi chiều, quãng đường",
        "Vùng quét toàn thân giữa các mẫu",
        "Khoảng hở + sai số + dự phòng dừng",
        "Không tìm được đường → R",
    ])
    d.arrow([(1480, 450), (1480, 565)])
    d.arrow([(1220, 676), (1140, 676)])
    d.arrow([(640, 676), (560, 676)])
    d.card(60, 840, 500, 210, "07  Mô phỏng và kiểm bám", [
        "Bám kín vòng với mô hình xe",
        "Kiểm va chạm, dung sai và dừng",
        "Không đạt → thử ứng viên khác",
        "Hết ngân sách / vẫn không đạt → R",
        "Đạt mô phỏng ≠ đã đạt trên xe thật",
    ])
    d.card(640, 840, 500, 210, "08  Người vận hành xác nhận", [
        "Xem đích, tiến/lùi và vùng quét",
        "Duyệt đúng phiên bản quỹ đạo",
        "Không xác nhận → giữ đứng yên",
        "Dữ liệu đổi → kiểm/lập và duyệt lại",
        "Chỉ lượt đã duyệt mới được gửi chạy",
    ])
    d.card(1220, 840, 520, 210, "09  Gửi QUỸ ĐẠO qua Wi-Fi LAN", [
        "Phiên / phiên bản, hệ tọa độ, mốc xe",
        "Thời điểm lập, hạn bắt đầu / thực hiện",
        "Tư thế đầu/đích, mẫu đường, giới hạn",
        "Pi nhận đường; tự tính từng nhịp lái",
        "Gói nhận được chưa có nghĩa được chạy",
    ])
    d.arrow([(310, 790), (310, 840)])
    d.arrow([(560, 945), (640, 945)])
    d.arrow([(1140, 945), (1220, 945)])
    d.rect(60, 1090, 1080, 60, "#fff1f3", "#d9aab2", 12)
    d.text(80, 1127, "R · TỪ CHỐI: giữ dừng, báo lý do; có thể tính ứng viên khác trước khi xin chạy.", 21, RED, True, 1040)
    d.arrow([(1480, 1050), (1480, 1105)])
    d.connector(1480, 1123, "A")
    d.text(1510, 1130, "→ cửa kiểm tra của Pi", 19, BLUE)

    # Band 3: two local controllers, with a distinct reverse feedback path.
    d.lane(40, 1200, 1120, 550, "RASPBERRY PI · KIỂM, BÁM VÀ QUYẾT ĐỊNH DỪNG", GREEN, "#edf8f3")
    d.lane(1200, 1200, 560, 550, "ESP32 · CƠ CẤU VÀ PHẢN HỒI", PURPLE, "#f4effa")
    d.connector(310, 1270, "A")
    d.arrow([(310, 1288), (310, 1310)], GREEN)
    d.card(60, 1310, 500, 220, "10  Pi kiểm trước khi bắt đầu", [
        "Đúng phiên, hệ tọa độ và hạn dùng",
        "Tư thế đo khớp đầu đường; xe đã dừng",
        "Dữ liệu mới, tin cậy; hành lang an toàn",
        "Đúng xác nhận của người vận hành",
        "Không đạt → từ chối, giữ dừng (R)",
    ], GREEN)
    d.card(640, 1310, 500, 220, "11  Bộ bám cục bộ trên Pi", [
        "Dùng tư thế, tốc độ, góc lái đo",
        "Tính mục tiêu tốc độ / góc lái",
        "Dừng có xác nhận trước đổi chiều",
        "Lệnh Pi → ESP32 luôn có thời hạn",
        "Giám sát vật cản / dữ liệu / liên kết",
    ], GREEN)
    d.card(1220, 1310, 520, 220, "12  ESP32 → ESC và servo", [
        "Kiểm phiên, thứ tự và hạn lệnh",
        "PWM ga ESC / PWM lái servo",
        "Đọc encoder và cảm biến góc lái",
        "Gửi số đo + trạng thái về Pi",
        "Watchdog: hết lệnh / mất USB → dừng",
    ], PURPLE)
    d.arrow([(560, 1410), (640, 1410)], GREEN)
    d.text(600, 1393, "Đạt", 18, GREEN, True, anchor="middle")
    d.arrow([(1140, 1410), (1220, 1410)], PURPLE)
    d.text(1180, 1393, "USB", 18, PURPLE, True, anchor="middle")
    d.arrow([(1480, 1530), (1480, 1578), (1030, 1578), (1030, 1530)], PURPLE, True)
    d.text(1230, 1607, "Phản hồi đo qua USB ngắn", 19, PURPLE, anchor="middle")
    d.arrow([(810, 1530), (810, 1625)], GREEN)
    d.card(60, 1625, 1080, 100, "13  Tiến độ / đạt đích → gửi trạng thái về laptop", [
        "Chỉ hoàn tất khi tư thế đo đạt dung sai + tốc độ đo xác nhận dừng; dữ liệu phải hợp lệ.",
    ], GREEN)
    d.card(1220, 1625, 520, 100, "Không có số đo ≠ xe đã dừng", [
        "Mất phản hồi: báo chưa xác nhận dừng.",
    ], PURPLE)

    # Band 4: independent stop/replan path avoids long crossing arrows in the main flow.
    d.lane(40, 1780, 1720, 370, "NHÁNH DỪNG · ÁP DỤNG TRONG SUỐT LƯỢT CHẠY", RED, "#fff2f3")
    d.card(60, 1850, 500, 224, "Phát hiện điều kiện không an toàn", [
        "Vật mới trong hành lang quét / dừng",
        "Dữ liệu cũ, mất hoặc không hợp lệ",
        "Tư thế không đủ tin cậy, bám sai",
        "Mất Wi-Fi / laptop quá hạn giám sát",
        "Pi / USB mất hoặc lệnh hết hạn",
    ], RED)
    d.card(640, 1850, 500, 224, "Pi dừng · ESP32 có watchdog", [
        "Pi dừng cục bộ, không đợi lập lại",
        "ESP32 dừng khi lệnh hết hạn",
        "Vô hiệu hóa đường của lượt cũ",
        "Đợi phản hồi xác nhận đứng yên",
        "Gửi tư thế đo mới + dữ liệu mới",
    ], RED)
    d.card(1220, 1850, 520, 224, "Laptop lập lại · lượt chạy mới", [
        "Chỉ lập từ tư thế đo SAU KHI DỪNG",
        "Cập nhật bản đồ / ô / đích ở 03–05",
        "Lập đường và kiểm bám lại ở 06–07",
        "Người vận hành xác nhận lại ở 08",
        "Gói mới qua 09 → Pi kiểm lại ở 10",
    ], RED)
    d.arrow([(560, 1960), (640, 1960)], RED)
    d.arrow([(1140, 1960), (1220, 1960)], RED)
    d.text(900, 2119, "KHÔNG TỰ KHỞI ĐỘNG LẠI khi vật cản biến mất hoặc mạng / dữ liệu phục hồi.", 24, RED, True, anchor="middle")
    d.text(40, 2188, "Mũi tên liền: luồng chính  ·  Nét đứt: phản hồi đo  ·  A: nối quỹ đạo  ·  R: từ chối / giữ dừng", 20, MUTED)
    d.text(40, 2221, "Wi-Fi LAN laptop–Pi; USB ngắn Pi–ESP32. 4G chỉ là tùy chọn từ xa về sau. Các ngưỡng phải được đo và kiểm trên xe.", 20, MUTED)
    return d.finish()


def render_png(svg):
    renderer = QSvgRenderer(QByteArray(svg))
    if not renderer.isValid():
        raise RuntimeError("SVG không hợp lệ")
    image = QImage(WIDTH, HEIGHT, QImage.Format.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        renderer.render(painter, QRectF(0, 0, WIDTH, HEIGHT))
    finally:
        painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError("Không mã hóa được PNG")
    buffer.close()
    return bytes(data)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="So byte ảnh sinh lại; không ghi tệp")
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for name in ("segoeui.ttf", "segoeuib.ttf"):
        path = fonts / name
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    if FONT not in QFontDatabase.families():
        raise RuntimeError(f"Cần phông {FONT} để giữ bố cục và kết quả xác định")
    svg = build_svg()
    png = render_png(svg)
    directory = Path(__file__).resolve().parent
    for extension, data in (("svg", svg), ("png", png)):
        output = directory / f"luong-tinh-duong.{extension}"
        if args.check:
            if not output.is_file() or output.read_bytes() != data:
                raise SystemExit(f"KHÁC hoặc thiếu: {output.name}")
            print(f"KHỚP: {output.name} ({len(data):,} byte)")
        else:
            output.write_bytes(data)
            print(f"Đã ghi: {output.name} ({len(data):,} byte)")
    app.quit()


if __name__ == "__main__":
    main()
