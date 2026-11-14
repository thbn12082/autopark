"""Build only luong-vat-can.svg and .png, without opening devices or source photos.

Run from the inner autopark directory:
    .venv\\Scripts\\python.exe docs/images/build_obstacle_flow.py

The drawing describes the agreed target architecture, not an executed experiment.
All geometry and wording are local to this file. No shared renderer is imported.
SVG bytes are deterministic; PNG bytes are deterministic with the same Qt/fonts.
"""
from __future__ import annotations

from html import escape
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication


OUT = Path(__file__).resolve().parent
WIDTH, HEIGHT = 1840, 2530
INK = "#183448"
MUTED = "#536c7c"
BLUE = "#236bb0"
TEAL = "#087f78"
RED = "#ba3e46"
AMBER = "#93601a"
PURPLE = "#7358a7"
BG = "#f5f8fb"
FONT = "Segoe UI"


class Drawing:
    def __init__(self):
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">',
            '<title id="title">Gặp vật cản — Kiến trúc mục tiêu 14/11/2026</title>',
            '<desc id="desc">Bốn làn: cảm biến, Raspberry Pi trên xe, laptop và ESP32. Camera qua hub USB tới Pi để nén, qua Wi-Fi tới AI và fusion trên laptop. LiDAR C1 tới Pi qua USB. Pi định vị, bám quỹ đạo và dừng cục bộ khi hành lang không an toàn hoặc dữ liệu, liên kết quá hạn, không chờ AI. ESP32 chấp hành, đọc phản hồi và xử lý lệnh hết hạn. Sau tốc độ đo về không, Pi gửi tư thế dừng mới để laptop lập lại; người dùng xác nhận lượt mới. Đây là thiết kế, chưa kiểm chứng trên xe thật.</desc>',
            f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{BG}"/>',
            f'<g font-family="{FONT}" font-size="20">',
        ]
        self.checks = 0

    def rect(self, x, y, w, h, fill="white", stroke="none", radius=16, dash=False):
        dashed = ' stroke-dasharray="7 5"' if dash else ""
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"{dashed}/>')

    def text(self, x, y, value, size=20, color=INK, bold=False, anchor="start", max_width=None):
        font = QFont(FONT)
        font.setPixelSize(size)
        font.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
        width = QFontMetricsF(font).horizontalAdvance(value)
        if max_width is not None and width > max_width:
            raise ValueError(f"Text too wide ({width:.1f} > {max_width}): {value}")
        left = x if anchor == "start" else x - width if anchor == "end" else x - width / 2
        if left < 0 or left + width > WIDTH or y < 0 or y > HEIGHT:
            raise ValueError(f"Text outside canvas: {value}")
        self.checks += 1
        self.parts.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{600 if bold else 400}" text-anchor="{anchor}">{escape(value)}</text>')

    def box(self, x, y, w, h, title, lines, color=BLUE, fill="white", size=19, dash=False):
        self.rect(x, y, w, h, fill, color, dash=dash)
        self.rect(x + 1, y + 20, 4, h - 40, color, radius=2)
        self.text(x + 20, y + 35, title, 22, color, True, max_width=w - 40)
        for i, line in enumerate(lines):
            baseline = y + 68 + i * 27
            if baseline > y + h - 15:
                raise ValueError(f"Text too tall: {title}")
            self.text(x + 20, baseline, line, size, max_width=w - 40)

    def arrow(self, points, color=BLUE, dashed=False, width=3):
        """Explicit arrow triangles render consistently in Qt and web browsers."""
        path = "M " + " L ".join(f"{x},{y}" for x, y in points)
        dash = ' stroke-dasharray="8 6"' if dashed else ""
        self.parts.append(f'<path d="{path}" fill="none" stroke="{BG}" stroke-width="{width + 5}" stroke-linejoin="round"/>')
        self.parts.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"{dash}/>')
        x, y = points[-1]
        px, py = points[-2]
        length = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
        dx, dy = (x - px) / length, (y - py) / length
        tip = [(x, y), (x - dx * 11 + dy * 5, y - dy * 11 - dx * 5), (x - dx * 11 - dy * 5, y - dy * 11 + dx * 5)]
        self.parts.append(f'<polygon points="{" ".join(f"{a:.2f},{b:.2f}" for a, b in tip)}" fill="{color}"/>')

    def label(self, x, y, value, color=BLUE, size=17):
        font = QFont(FONT)
        font.setPixelSize(size)
        w = QFontMetricsF(font).horizontalAdvance(value) + 18
        self.rect(x - w / 2, y - size, w, size + 9, BG, radius=5)
        self.text(x, y, value, size, color, anchor="middle")

    def section(self, y, number, title):
        self.rect(40, y - 29, 1760, 41, "#e8eff5", radius=8)
        self.text(56, y, number, 23, BLUE, True)
        self.text(105, y, title, 22, INK, True)

    def write(self):
        target = OUT / "luong-vat-can.svg"
        target.write_bytes(("\n".join(self.parts + ["</g></svg>"]) + "\n").encode("utf-8"))
        return target


def build():
    d = Drawing()
    d.text(40, 65, "Gặp vật cản: ai thấy, ai dừng, ai lập lại?", 40, INK, True)
    d.text(40, 105, "KIẾN TRÚC MỤC TIÊU · 14/11/2026", 23, BLUE, True)
    d.rect(40, 129, 1760, 58, "#19394d", radius=12)
    d.text(60, 166, "Thiết kế cần triển khai và kiểm chứng trên xe thật. Code hiện tại: mô phỏng / người dùng chọn đích gần.", 22, "white", True)
    for x, color, label, dashed in ((45, BLUE, "Dữ liệu / quỹ đạo", False), (420, TEAL, "Điều khiển cục bộ", False), (815, RED, "Dừng / lỗi", False), (1155, PURPLE, "Phản hồi đo", True)):
        d.arrow([(x, 221), (x + 49, 221)], color, dashed)
        d.text(x + 65, 228, label, 19, color)
    d.text(1788, 228, "Giao cắt ≠ nối", 18, MUTED, anchor="end")

    lanes = ((40, 340, "CẢM BIẾN", "Thu nhận trên xe", "#edf3f8", MUTED),
             (420, 440, "PI 4 · 4 GB · SD 64 GB", "Định vị · bám đường · dừng cục bộ", "#eaf6f3", TEAL),
             (900, 440, "LAPTOP", "AI · hợp nhất · chọn ô · lập đường", "#edf2fb", BLUE),
             (1380, 420, "ESP32", "Chấp hành · phản hồi · watchdog", "#f2eef8", PURPLE))
    for x, w, title, sub, tint, color in lanes:
        d.rect(x, 252, w, 2100, tint, radius=18)
        d.rect(x, 252, w, 83, color, radius=14)
        d.text(x + 20, 286, title, 23, "white", True)
        d.text(x + 20, 315, sub, 18, "white", max_width=w - 40)

    d.box(56, 406, 308, 126, "4 camera USB", ["Qua hub USB trên xe", "Ảnh + thời điểm chụp"], MUTED)
    d.box(436, 406, 408, 126, "Thu ảnh + nén trên Pi", ["Giữ dấu thời gian từng camera", "Truyền ảnh qua Wi-Fi LAN"], TEAL)
    d.box(916, 406, 408, 126, "AI trên laptop", ["Xử lý ảnh từ cả 4 camera", "Bổ sung bằng chứng vật cản"], BLUE)
    d.box(1396, 406, 388, 126, "Vai trò riêng của ESP32", ["Không chạy AI / chọn ô", "Nhận lệnh ga và lái từ Pi"], PURPLE, dash=True)
    d.arrow([(364, 469), (436, 469)])
    d.label(400, 453, "USB")
    d.arrow([(844, 469), (916, 469)])
    d.label(880, 453, "Wi-Fi")

    d.box(56, 578, 308, 154, "LiDAR C1", ["Qua adapter USB tới Pi", "Đo trong mặt quét", "Vùng khuất vẫn chưa rõ"], MUTED)
    d.box(436, 578, 408, 154, "LiDAR + định vị cục bộ", ["Đọc C1 và phản hồi từ ESP32", "Ước lượng x, y, hướng trên xe", "Gửi quét + pose + tuổi dữ liệu"], TEAL)
    d.box(916, 578, 408, 154, "Hợp nhất (fusion)", ["AI + LiDAR + pose cùng mốc", "Vùng chưa rõ ≠ vùng an toàn", "Giữ bằng chứng vật đã biết"], BLUE)
    d.box(1396, 578, 388, 154, "Đọc phản hồi thực", ["MT6701 #2: tốc độ qua A/B", "MT6701 #1: góc lái qua I²C", "Gửi số đo và trạng thái về Pi"], PURPLE)
    d.arrow([(364, 655), (436, 655)])
    d.label(400, 639, "USB")
    d.arrow([(844, 655), (916, 655)])
    d.label(880, 639, "Wi-Fi")
    d.arrow([(1120, 532), (1120, 578)])
    d.arrow([(1120, 732), (1120, 854)])
    d.arrow([(1590, 732), (1590, 773), (760, 773), (760, 732)], PURPLE, True)
    d.label(1200, 761, "USB ngắn · số đo + trạng thái", PURPLE)
    d.arrow([(640, 732), (640, 854)], TEAL)

    d.box(56, 854, 308, 140, "Không phải vật nào", ["cũng làm xe đánh lái.", "Ngoài vùng xe sẽ quét:", "cập nhật bản đồ, theo dõi."], TEAL, "#f8fcfa", size=18)
    d.box(436, 854, 408, 140, "Pi bám quỹ đạo cục bộ", ["Dùng tư thế và phản hồi đo", "Tính tốc độ / góc lái mỗi nhịp", "Laptop gửi quỹ đạo, không tick"], TEAL)
    d.box(916, 854, 408, 140, "Chọn ô / lập quỹ đạo", ["Xét toàn thân xe, tiến và lùi", "Quỹ đạo + giới hạn + thời hạn", "Gửi khi người dùng xác nhận"], BLUE)
    d.box(1396, 854, 388, 140, "Điều khiển chấp hành", ["ESP32 → ESC + servo thật", "Đọc lại encoder và góc lái", "Kiểm thời hạn từng lệnh"], PURPLE)
    d.arrow([(916, 924), (844, 924)])
    d.label(880, 908, "LAN")
    d.arrow([(740, 994), (740, 1030), (1590, 1030), (1590, 994)], TEAL)
    d.label(1150, 1018, "USB ngắn · lệnh tốc độ / góc lái có hạn", TEAL)
    d.arrow([(640, 994), (640, 1124)], TEAL)

    d.box(436, 1124, 408, 176, "Giám sát hành lang trên Pi", ["Vùng quét thân xe + quãng dừng", "Vật / vùng chưa rõ đe dọa → dừng", "Dữ liệu / Wi-Fi cũ, thiếu → dừng", "Đủ điều kiện an toàn → bám tiếp"], TEAL, size=18)
    d.box(916, 1124, 408, 176, "Nếu chỉ camera thấy nguy cơ", ["AI → fusion → yêu cầu STOP", "Vật đe dọa hành lang: gửi về Pi", "Chịu trễ ảnh + nén + mạng + AI", "Không thay đường dừng LiDAR"], BLUE, size=18)
    d.box(1396, 1124, 388, 176, "Nếu Pi / USB mất lệnh", ["Watchdog hết hạn trên ESP32", "Tự đưa về dừng theo thiết kế", "Không chờ laptop / Wi-Fi", "Chặn tự chạy lại sau sự cố"], RED, "#fff7f7", size=18)
    d.arrow([(1324, 684), (1356, 684), (1356, 1107), (1120, 1107), (1120, 1124)])
    d.arrow([(436, 1210), (400, 1210), (400, 924), (436, 924)], TEAL, True)
    d.label(293, 1052, "An toàn: tiếp tục bám", TEAL, 16)

    # Small top view: swept body corridor, object inside, object outside.
    d.rect(56, 1124, 308, 360, "white", "#a6bbc9")
    d.text(76, 1158, "Xét cả vùng thân xe quét", 20, INK, True, max_width=268)
    d.rect(156, 1196, 103, 184, "#fde7e8", RED, radius=24, dash=True)
    d.rect(174, 1301, 67, 99, "#e2eef7", BLUE, radius=12)
    d.rect(184, 1313, 47, 26, "#9dbbd4", radius=5)
    d.text(207, 1374, "XE", 18, BLUE, True, anchor="middle")
    d.arrow([(207, 1290), (207, 1249)], RED)
    d.rect(189, 1206, 36, 29, "#d85760", radius=5)
    d.rect(92, 1220, 35, 29, "#53a99b", radius=5)
    d.text(77, 1430, "Đỏ: xâm nhập hành lang → dừng", 17, RED, max_width=266)
    d.text(77, 1456, "Xanh: ngoài vùng → theo dõi", 17, TEAL, max_width=266)

    d.box(436, 1350, 408, 126, "DỪNG CỤC BỘ · chốt dừng", ["Ngắt quyền bám quỹ đạo cũ", "Không đợi AI / mạng trả lời"], RED, "#fff3f3")
    d.box(1396, 1350, 388, 126, "Giảm tốc / điều khiển dừng", ["Thực hiện qua ESC + servo", "Quãng dừng phải được đo thật"], RED, "#fff3f3", size=18)
    d.arrow([(640, 1300), (640, 1350)], RED)
    d.label(733, 1332, "Nguy cơ / lỗi", RED, 16)
    d.arrow([(1120, 1300), (1120, 1378), (844, 1378)], RED)
    d.label(1120, 1363, "Wi-Fi · STOP", RED)
    d.arrow([(844, 1444), (1396, 1444)], RED)
    d.label(1120, 1428, "USB ngắn · ưu tiên STOP", RED)
    d.arrow([(1590, 1300), (1590, 1350)], RED)

    d.box(56, 1520, 308, 154, "Vùng mù ≠ vùng trống", ["LiDAR có thể sót vật thấp.", "Ảnh có thể khuất hoặc trễ.", "Chưa rõ an toàn: giữ dừng."], AMBER, "#fffaf0", size=17)
    d.box(436, 1548, 408, 126, "Pi xác nhận trạng thái dừng", ["Tốc độ đo ≈ 0 đủ thời gian", "Chốt pose dừng mới: x, y, hướng"], PURPLE, size=18)
    d.box(1396, 1548, 388, 126, "Xác nhận tốc độ về 0", ["Encoder còn mới và hợp lệ", "Không suy ra từ lệnh v = 0"], PURPLE)
    d.arrow([(1590, 1476), (1590, 1548)], RED)
    d.arrow([(1396, 1611), (844, 1611)], PURPLE, True)
    d.label(1120, 1595, "USB ngắn · phản hồi đo", PURPLE)

    d.box(436, 1790, 408, 142, "Giữ dừng, khóa lượt cũ", ["Dữ liệu về lại ≠ tự chạy lại", "Chưa xác nhận dừng: giữ lỗi", "Chờ đường mới và xác nhận mới"], RED, "#fff7f7", size=18)
    d.box(916, 1790, 408, 142, "Lập lại từ tư thế đã đo", ["Nhận pose dừng + bản đồ mới", "Chọn lại ô / tính đường nếu cần", "Không dùng điểm dừng dự đoán"], BLUE, size=18)
    d.box(1396, 1790, 388, 142, "Nếu mất phản hồi đo?", ["Không kết luận xe đã đứng yên", "Giữ dừng / lỗi, chờ kiểm tra", "Không mở lượt chạy mới"], AMBER, "#fffaf0", size=18, dash=True)
    d.arrow([(640, 1674), (640, 1790)], RED)
    d.arrow([(844, 1640), (878, 1640), (878, 1770), (1120, 1770), (1120, 1790)])
    d.label(1120, 1755, "Wi-Fi · pose dừng + dữ liệu mới", BLUE)
    d.box(916, 1978, 408, 118, "Người dùng xác nhận lượt mới", ["Xem đường và điều kiện hiện tại", "Không có đường an toàn: giữ dừng"], BLUE, size=18)
    d.arrow([(1120, 1932), (1120, 1978)])

    d.rect(56, 1790, 308, 306, "#19394d")
    d.text(76, 1825, "VÍ DỤ: ĐANG LÙI VÀO Ô", 20, "white", True, max_width=268)
    for i, line in enumerate(("Thùng giấy vào vùng đuôi quét.", "1. Pi thấy nguy cơ → dừng.", "2. ESP32 giảm tốc, trả số đo.", "3. Pi chốt pose dừng đo được.", "4. Laptop tính đường mới.", "5. Người dùng xác nhận lại.")):
        d.text(76, 1862 + i * 29, line, 17, "#edf5fa", max_width=268)
    d.text(76, 2054, "Vật còn chắn / dữ liệu cũ?", 18, "#ffdb9c", True, max_width=268)
    d.text(76, 2080, "Giữ dừng, không tự lách qua.", 17, "#ffdb9c", max_width=268)

    d.box(436, 2140, 408, 148, "Pi kiểm lại trước khi chạy", ["Pose + cảm biến + link còn mới", "Quỹ đạo mới hợp lệ, đúng phiên", "Đạt mọi điều kiện: mới bám lại"], TEAL, "#f6fcf9", size=18)
    d.box(1396, 2140, 388, 148, "ESP32 nhận lượt chạy mới", ["Chỉ chấp hành lệnh còn hạn", "Tốc độ / góc lái do Pi phát", "Hết hạn: quay về dừng"], PURPLE, size=18)
    d.arrow([(1120, 2096), (1120, 2214), (844, 2214)])
    d.label(1120, 2197, "Wi-Fi · quỹ đạo mới + xác nhận", BLUE)
    d.arrow([(640, 2288), (640, 2320), (1590, 2320), (1590, 2288)], TEAL)
    d.label(1120, 2306, "USB ngắn · lệnh cho lượt chạy mới", TEAL)
    d.text(76, 2185, "Không đủ điều kiện ở bất kỳ", 18, MUTED, max_width=270)
    d.text(76, 2212, "bước nào: tiếp tục giữ dừng.", 18, MUTED, max_width=270)
    d.text(76, 2258, "4G: tùy chọn từ xa về sau;", 17, MUTED, max_width=270)
    d.text(76, 2284, "không thuộc đường dừng tại xe.", 17, MUTED, max_width=270)

    # Paint section strips after connectors: every vertical has a clean gap
    # across a heading, including the safe-return loop and the stop/hold link.
    d.section(375, "01", "Thu nhận tại xe, nhận biết và hợp nhất trên laptop")
    d.section(821, "02", "Khi được phép chạy: Pi bám quỹ đạo, ESP32 điều khiển cơ cấu")
    d.section(1087, "03", "Có nguy cơ hoặc mất dữ liệu: dừng trước, đo lại sau")
    d.section(1722, "04", "Đứng yên đã được xác nhận → lập đường mới → người dùng xác nhận")
    d.rect(40, 2380, 1760, 99, "#19394d", radius=14)
    d.text(63, 2417, "Pi dừng cục bộ. AI không trực tiếp bẻ lái. Dữ liệu hoặc liên kết phục hồi không tự làm xe chạy lại.", 23, "white", True)
    d.text(63, 2453, "Luôn cần: dừng đo được → tư thế mới → lập lại trên laptop → xác nhận lượt mới → kiểm điều kiện trên Pi.", 22, "#d9e8f1")
    d.text(40, 2510, "Sơ đồ chức năng mục tiêu • Chưa triển khai đầy đủ Pi phân tán / tự chọn ô • Chưa chứng minh phanh hoặc tránh vật trên xe thật", 18, MUTED)
    return d.write(), d.checks


def main():
    app = QApplication.instance() or QApplication([])
    # Qt's offscreen platform does not enumerate Windows fonts automatically.
    for name in ("segoeui.ttf", "seguisb.ttf"):
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if font_path.is_file():
            QFontDatabase.addApplicationFont(str(font_path))
    if FONT not in QFontDatabase.families():
        raise RuntimeError(f"Install {FONT} to keep the documented layout and raster output reproducible")
    svg_path, checks = build()
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        raise RuntimeError("Generated SVG is not valid")
    output = QImage(WIDTH, HEIGHT, QImage.Format.Format_ARGB32_Premultiplied)
    output.fill(QColor(BG))
    painter = QPainter(output)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    renderer.render(painter, QRectF(0, 0, WIDTH, HEIGHT))
    painter.end()
    png_path = svg_path.with_suffix(".png")
    if not output.save(str(png_path), "PNG"):
        raise RuntimeError("Could not save PNG")
    print(f"Built {svg_path.name} and {png_path.name}: {WIDTH}x{HEIGHT}; checked {checks} text lines")
    app.quit()


if __name__ == "__main__":
    main()
