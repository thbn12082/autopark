"""Build three deterministic 2D wiring sheets; no hardware is opened.

Run from any directory: python build_wiring.py
This checks the planned netlist, not physical wiring or electrical compatibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
from pathlib import Path

from components import draw_component, component_ports, PORT_SPECS, DESIGN_DATE, CATALOG_KINDS

OUT = Path(__file__).resolve().parent
INK = "#153047"
MUTED = "#536b7b"
BG = "#f4f7fa"
RED = "#cf343f"
GND = "#334155"
USB = "#237cc2"
LOGIC = "#7651c9"
SIGNAL = "#138d86"
AMBER = "#bf7414"
BLUE2 = "#35a9c4"


def number(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def text(x, y, lines, size=24, color=INK, weight=400, anchor="start", leading=1.35):
    if isinstance(lines, str):
        lines = lines.split("\n")
    # QtSvg does not consistently honor nested tspan x/dy. Independent text
    # elements retain the same line positions in browsers and the PNG renderer.
    return "".join(
        f'<text x="{number(x)}" y="{number(y + i * size * leading)}" '
        f'font-family="Segoe UI, Arial, sans-serif" font-size="{size}" fill="{color}" '
        f'font-weight="{weight}" text-anchor="{anchor}">{escape(str(line))}</text>'
        for i, line in enumerate(lines))


def box(x, y, w, h, fill="white", stroke="#cad7e2", radius=16, width=2):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>')


@dataclass
class Node:
    kind: str
    x: float
    y: float
    w: float
    h: float
    label: str | None = None
    subtitle: str | None = None

    def ports(self):
        return component_ports(self.kind, self.x, self.y, self.w, self.h)


class Sheet:
    def __init__(self, width, height, title, subtitle, index):
        self.width, self.height = width, height
        self.nodes = {}
        self.background = [box(0, 0, width, height, BG, BG, 0), text(70, 73, title, 44, weight=700),
                           text(70, 114, subtitle, 23, MUTED),
                           box(70, 142, width - 140, 65, "#fff4df", "#e8bf75", 12),
                           text(92, 181, "THIẾT KẾ MỤC TIÊU • Chưa kiểm chứng trên xe • Pi phân tán / tự chọn ô chưa triển khai", 25, "#82500d", 600)]
        self.drawings, self.wires, self.overlays = [], [], []
        self.overlays.append(text(width - 70, height - 28, f"AutoPark · {DESIGN_DATE} · Tờ {index}/3", 21, MUTED, anchor="end"))

    def node(self, name, kind, x, y, w, h, label=None, subtitle=None):
        n = Node(kind, x, y, w, h, label, subtitle)
        self.nodes[name] = n
        self.drawings.append(draw_component(kind, x, y, w, h, label=label, subtitle=subtitle))
        return n

    def point(self, endpoint):
        name, port = endpoint.split(".")
        return self.nodes[name].ports()[port]

    def line(self, points, color=SIGNAL, dashed=False, width=5):
        pts = " ".join(f"{number(x)},{number(y)}" for x, y in points)
        self.wires.append(f'<polyline points="{pts}" fill="none" stroke="white" stroke-width="{width + 7}" stroke-linecap="round" stroke-linejoin="round"/>')
        dash = ' stroke-dasharray="13 9"' if dashed else ""
        self.wires.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"{dash}/>')

    def wire(self, a, b, vias=(), color=SIGNAL, dashed=False, width=5):
        self.line([self.point(a), *vias, self.point(b)], color, dashed, width)

    def junction(self, x, y, color=GND):
        self.overlays.append(f'<circle cx="{number(x)}" cy="{number(y)}" r="7" fill="{color}" stroke="white" stroke-width="2"/>')

    def label(self, x, y, lines, size=23, color=INK, weight=600, anchor="start"):
        self.overlays.append(text(x, y, lines, size, color, weight, anchor))

    def note(self, x, y, w, lines, color=AMBER, fill="#fff8ea", size=23):
        if isinstance(lines, str):
            lines = lines.split("\n")
        height = 35 + len(lines) * size * 1.35
        self.overlays += [box(x, y, w, height, fill, color, 12), text(x + 20, y + 34, lines, size, color)]

    def cap(self, endpoint, dx=0, dy=55, label=None, color=RED):
        x, y = self.point(endpoint)
        end = (x + dx, y + dy)
        self.line([(x, y), end], color, False, 6)
        self.overlays.append(box(end[0] - 12, end[1] - 9, 24, 18, GND, GND, 4))
        if label:
            self.label(end[0] + 27, end[1] + 8, label, 22, color)

    def save(self, filename):
        body = "\n".join([*self.background, *self.drawings, *self.wires, *self.overlays])
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
               f'viewBox="0 0 {self.width} {self.height}">\n{body}\n</svg>\n')
        path = OUT / filename
        path.write_text(svg, encoding="utf-8")
        return path


def system_sheet():
    s = Sheet(2300, 2850, "01 · NGUỒN TRÊN XE: ĐỘNG LỰC, PI VÀ HUB", "Pin 2S chia nhánh: ESC + nguồn Pi + nguồn hub. BEC 6 V chỉ cấp servo sau khi xác minh tương thích.", 1)
    s.background.append(box(70, 240, 2160, 1280, "#ffffff", "#d6e0e9", 20))
    s.node("BAT", "battery2s", 100, 300, 330, 220)
    s.node("ESC", "esc1060", 880, 300, 420, 280)
    s.node("MOTOR", "motor280", 1740, 325, 360, 216)
    s.node("ESP", "esp32", 240, 760, 350, 487.5)
    s.node("SERVO", "servo", 1730, 1050, 360, 260)
    bp, bn = s.point("BAT.plus"), s.point("BAT.minus")
    ep, en = s.point("ESC.battery_plus"), s.point("ESC.battery_minus")
    s.wire("BAT.plus", "ESC.battery_plus", [(500, bp[1]), (500, ep[1])], RED, width=7)
    s.wire("BAT.minus", "ESC.battery_minus", [(540, bn[1]), (540, en[1])], GND, width=7)
    s.label(520, 310, "P1 · Giắc T/Deans đúng cặp", 25)
    s.label(520, 345, "Đối chiếu cực + / −", 22, MUTED)
    # Named continuation pair, not another battery or a physical connector pinout.
    s.line([(650, ep[1]), (650, 485), (800, 485)], RED, True, 7)
    s.line([(700, en[1]), (700, 545), (800, 545)], GND, True, 7)
    s.junction(650, ep[1], RED)
    s.junction(700, en[1], GND)
    s.label(720, 475, "P3+ ↓", 21, RED)
    s.label(720, 535, "P3− ↓", 21, GND)
    s.label(370, 635, "P3 → nguồn Pi / hub (phần dưới)", 21, MUTED)
    ma, mb = s.point("MOTOR.a"), s.point("MOTOR.b")
    ea, eb = s.point("ESC.motor_a"), s.point("ESC.motor_b")
    s.wire("ESC.motor_a", "MOTOR.a", [(1485, ea[1]), (1485, ma[1])], USB, width=7)
    s.wire("ESC.motor_b", "MOTOR.b", [(1540, eb[1]), (1540, mb[1])], AMBER, width=7)
    s.label(1390, 315, "M1 · Dây chuyển motor", 25)
    s.note(1660, 610, 510, ["Bullet ESC → giắc 2 chân motor gốc.", "A/B là hai đầu ra đảo cực.", "Không nối A/B xuống GND.", "Đối chiếu giắc và dây motor thực tế."], MUTED, "#f3f7fb", 21)
    esc_sig = s.point("ESC.signal")
    esp_esc = s.point("ESP.esc_pwm")
    s.wire("ESP.esc_pwm", "ESC.signal", [(180, esp_esc[1]), (180, 680), (esc_sig[0], 680)], SIGNAL, True)
    s.label(700, 610, "S1 · GPIO4 → ESC S · kiểm tra mức 3V3", 23, SIGNAL)
    servo_sig, esp_servo = s.point("SERVO.signal"), s.point("ESP.servo_pwm")
    s.wire("ESP.servo_pwm", "SERVO.signal", [(120, esp_servo[1]), (120, 730), (1640, 730), (1640, servo_sig[1])], SIGNAL, True)
    s.label(700, 715, "S2 · GPIO5 → servo S · kiểm tra mức 3V3", 23, SIGNAL)
    s.note(680, 795, 770, ["CHỈ NỐI nếu servo được xác nhận dùng nguồn 6 V",
                         "và BEC đủ dòng cho tải lái thực tế.",
                         "1060 tham chiếu: BEC 6 V / 3 A; đo lại ESC thực nhận.",
                         "BEC + không nối vào 3V3, 5V hoặc GPIO của ESP32."], RED, "#fff3f2", 23)
    servo_v = s.point("SERVO.vplus")
    bec = s.point("ESC.bec_plus")
    s.wire("ESC.bec_plus", "SERVO.vplus", [(bec[0], 650), (1530, 650), (1530, servo_v[1])], RED, True, 7)
    s.label(700, 1020, ["P2 · BEC + của ESC → nguồn + của servo",
                        "6 V là điện áp BEC tham chiếu; servo còn chờ xác minh."], 22, RED)
    sg = s.point("SERVO.gnd")
    star = (1600, sg[1])
    eg = s.point("ESC.gnd")
    s.wire("ESC.gnd", "SERVO.gnd", [(eg[0], 690), (1600, 690), star], GND, True, 7)
    s.junction(*star)
    pg = s.point("ESP.gnd")
    s.line([pg, (175, pg[1]), (175, 1495), (1600, 1495), star], GND)
    s.label(1650, 1420, ["GND servo về ESC/BEC bằng dây nguồn.", "Nhánh tới ESP chỉ làm mốc tín hiệu."], 22, MUTED)
    s.note(680, 1100, 770, ["TÁCH CHỨC NĂNG GIẮC ĐIỀU KHIỂN ESC:",
                          "S của ESC nhận ga từ GPIO4.",
                          "BEC + và GND cấp nguồn cho servo.",
                          "S của servo nhận lái riêng từ GPIO5.",
                          "Không dùng dây Y ba lõi nối chung hai chân S."], MUTED, "#f3f7fb", 22)
    u = s.point("ESP.usb_native")
    s.line([u, (u[0], 1375)], USB, width=9)
    s.overlays.append(box(u[0] - 22, 1375, 44, 26, "#dceeff", USB, 6))
    s.label(520, 1380, ["U1 · USB native tới Pi trên xe ở Tờ 2", "Nguồn + dữ liệu; không cấp thêm 5V/BEC vào ESP"], 22, USB)
    s.label(100, 570, "Giắc cân bằng pin để rời khi chạy (sạc ở Tờ 3).", 22, MUTED)
    s.label(85, 1567, "Nét đứt: kết nối còn điều kiện xác minh. Giao cắt không chấm = không nối; chấm tròn = cùng nút.", 23, MUTED)
    s.label(85, 1600, "Theo lựa chọn hiện tại: chưa có nút dừng khẩn, phần tử ngắt động lực độc lập và cầu chì bổ sung.", 22, AMBER)
    s.background.append(box(70, 1670, 2160, 1110, "white", "#d6e0e9", 20))
    s.label(95, 1720, "P3 · HAI BỘ NGUỒN ỔN ÁP RIÊNG — PHƯƠNG ÁN CHỜ CHỌN / ĐO KIỂM", 28)
    s.label(95, 1760, "P3+/P3− tiếp tục đúng hai nhánh có tên ở trên; không lấy từ BEC hoặc giắc cân bằng.", 23, MUTED)
    s.node("PSPI", "pi_supply", 470, 1830, 400, 271.43)
    s.node("PSHUB", "hub_supply", 470, 2250, 400, 271.43)
    s.node("PI", "raspberry_pi", 1270, 1800, 480, 333.33)
    s.node("HUB", "usb_hub", 1270, 2250, 420, 229.09, label="HUB CÓ NGUỒN · CHỜ CHỌN")
    for port, x, start_y, col, name in [("vin_plus", 200, 1840, RED, "P3+"),
                                      ("vin_minus", 260, 1900, GND, "P3−")]:
        p, h = s.point(f"PSPI.{port}"), s.point(f"PSHUB.{port}")
        s.line([(110,start_y),(x,start_y),(x,h[1]),h],col,True,7)
        s.line([(x,p[1]),p],col,True,7)
        s.junction(x,p[1],col)
        s.label(100,start_y-20,name,24,col)
    for out_port, target, gutter, col in [("vout_plus", "power_5v", 1060, RED),
                                         ("vout_minus", "power_gnd", 1120, GND)]:
        a,b=s.point(f"PSPI.{out_port}"),s.point(f"PI.{target}")
        s.wire(f"PSPI.{out_port}",f"PI.{target}",[(gutter,a[1]),(gutter,b[1])],col,True,7)
    s.label(915, 1825, "P4 · 5 V ổn áp*", 24, RED)
    s.label(915, 2150, "Cả + và GND qua cổng nguồn đúng model Pi; hình tách hai lõi để đọc đường điện.", 21, MUTED)
    for out_port, target, gutter, bottom, col in [("vout_plus","dc_plus",1040,2570,RED),
                                                ("vout_minus","dc_minus",1100,2615,GND)]:
        a,b=s.point(f"PSHUB.{out_port}"),s.point(f"HUB.{target}")
        s.wire(f"PSHUB.{out_port}",f"HUB.{target}",[(gutter,a[1]),(gutter,bottom),(b[0],bottom)],col,True,7)
    s.label(915, 2225, "P5 · DC đúng định mức hub*", 24, RED)
    s.note(1780, 1830, 410, ["PI 4: RAM 4 GB / SD 64 GB", "Đầu vào chịu toàn dải pin 2S.", "Nguồn USB-C 5,1 V / 3 A;", "đủ tải Pi + C1 + ESP qua USB.", "Kiểm sụt áp, nhiễu, nhiệt", "nguồn và cáp vẫn chờ chọn.", "Không dùng BEC 6 V."], AMBER, "#fff8ea", 21)
    s.note(1760, 2250, 440, ["HUB / NGUỒN: CHỜ CHỌN", "Chỉ cấp qua DC-in hãng hỗ trợ.", "Điện áp / cực / dòng đúng hub.", "Đủ tải đồng thời 4 camera.", "Kiểm không cấp ngược VBUS", "từ hub về cổng USB của Pi.", "Hub cũ: chưa xác nhận DC-in."], AMBER, "#fff8ea", 21)
    s.label(95, 2685, ["USB Pi ↔ ESP/C1/hub: xem Tờ 2; GND theo cáp USB. Nguồn Pi và hub không ghép song song đầu ra dương.",
                       "Chọn DC–DC không cách ly, kiểm IN−/OUT− cùng tham chiếu; dòng motor/servo hồi theo dây nguồn riêng.",
                       "Ngắt pin tại đầu T chung sẽ tách cả ESC, nguồn Pi và nguồn hub trước khi sạc. Công tắc ESC không ngắt hai nhánh mới."], 22, MUTED)
    return s.save("01-system.svg")


def signal_sheet():
    s = Sheet(2800, 2440, "02 · LAPTOP ↔ WI-FI ↔ PI TRÊN XE ↔ USB ↔ ESP32", "Pi thu cảm biến, định vị và bám quỹ đạo tại xe. Laptop gửi quỹ đạo, không gửi từng nhịp lái qua Wi-Fi.", 2)
    s.background += [box(70, 240, 2660, 730, "white", "#d6e0e9", 20),
                     box(70, 1030, 2660, 865, "white", "#d6e0e9", 20)]
    s.node("PC", "laptop", 120, 285, 360, 260)
    s.node("PI", "raspberry_pi", 850, 285, 400, 277.78)
    s.node("HUB", "usb_hub", 1500, 280, 330, 180, label="HUB CÓ NGUỒN · CHỜ CHỌN")
    for i, (x, y) in enumerate([(2000, 280), (2450, 280), (2000, 650), (2450, 650)], 1):
        s.node(f"CAM{i}", "camera", x, y, 230, 172.5, label=f"CAMERA USB {i}")
    s.node("C1", "lidar", 800, 670, 300, 264)
    s.node("ADAPTER", "lidar_adapter", 1250, 700, 300, 180)
    s.node("ESP", "esp32", 230, 1160, 420, 585)
    s.node("STEER", "mt6701_steer", 1060, 1180, 350, 269.23)
    s.node("ENC", "mt6701", 1750, 1470, 350, 269.23)
    pc, pi = s.point("PC.wifi"), s.point("PI.wifi")
    s.wire("PC.wifi", "PI.wifi", [(700,pc[1]),(700,pi[1])], USB, True, 6)
    s.label(515, 285, ["N1 · Wi-Fi LAN", "Hai chiều · không phải dây"], 22, USB)
    s.label(505, 445, ["→ quỹ đạo / xác nhận chạy", "← ảnh, scan, pose, trạng thái"], 21, USB)
    pu, hu = s.point("PI.usb2"), s.point("HUB.upstream")
    s.wire("PI.usb2", "HUB.upstream", [(1370,pu[1]),(1370,hu[1])], USB, width=8)
    s.label(1430, 255, "U2 · USB upstream tới Pi", 22, USB)
    camera_vias = {
        1: lambda a,b: [(1940,a[1]),(1940,b[1])],
        2: lambda a,b: [(1870,a[1]),(1870,245),(2400,245),(2400,b[1])],
        3: lambda a,b: [(1900,a[1]),(1900,b[1])],
        4: lambda a,b: [(1860,a[1]),(1860,920),(2400,920),(2400,b[1])],
    }
    for i in range(1,5):
        a,b=s.point(f"HUB.usb{i}"),s.point(f"CAM{i}.usb")
        s.wire(f"HUB.usb{i}",f"CAM{i}.usb",camera_vias[i](a,b),USB,width=7)
    s.note(1930, 510, 760, ["U3–U6 · Bốn camera USB → hub → Pi.", "Chưa chốt hướng gá / FPS / băng thông thực tế."], AMBER, "#fff8ea", 22)
    s.label(1460, 495, ["Nguồn hub riêng: P5 ở Tờ 1.", "DC-in chưa xác minh; không cấp ngược Pi."], 20, AMBER)
    s.label(780, 600, "Nguồn Pi riêng: P4 ở Tờ 1; BEC 6 V không nối Pi.", 21, AMBER)
    pu, au=s.point("PI.usb3"),s.point("ADAPTER.usb")
    s.wire("PI.usb3","ADAPTER.usb",[(1410,pu[1]),(1410,590),(1610,590),(1610,au[1])],USB,width=8)
    cp,al=s.point("C1.connector"),s.point("ADAPTER.lidar")
    s.wire("C1.connector","ADAPTER.lidar",[(1180,cp[1]),(1180,al[1])],USB,width=8)
    s.label(1140, 900, ["U7 · C1 + adapter USB → Pi.", "U8 · Cáp C1 gốc; không chuyển sang GPIO ESP."], 21, USB)
    pu,eu=s.point("PI.usb1"),s.point("ESP.usb_native")
    s.wire("PI.usb1","ESP.usb_native",[(1300,pu[1]),(1300,625),(45,625),(45,1870),(eu[0],1870)],USB,width=9)
    s.note(100, 690, 610, ["LAPTOP: AI trên 4 luồng camera,", "fusion + chọn ô đỗ + lập quỹ đạo.", "PI: thu C1/camera, định vị cục bộ,", "bám quỹ đạo và dừng vật cản tại xe.", "AI không trực tiếp xuất ga / góc lái.", "4G: tùy chọn điều khiển từ xa về sau."], MUTED, "#f3f7fb", 22)
    s.label(80, 990, "U1 · USB NGẮN TRÊN XE: Pi ↔ USB native/CDC của ESP32; dữ liệu + nguồn. Không kéo USB từ laptop ra xe.", 23, USB)
    s.label(1050, 1095, "HAI MT6701 RIÊNG · module và gá cần đối chiếu", 28)
    p3, g = s.point("ESP.v3v3"), s.point("ESP.gnd")
    av, ev = s.point("STEER.vcc"), s.point("ENC.vcc")
    s.line([p3,(180,p3[1]),(180,1135),(995,1135),(995,av[1]),av], LOGIC, True)
    s.line([(995,1135),(1610,1135),(1610,ev[1]),ev], LOGIC, True)
    s.junction(995,1135,LOGIC)
    s.label(1020, 1127, "L1 · 3V3 (chỉ module hỗ trợ 3,3 V)", 22, LOGIC)
    ag, eg = s.point("STEER.gnd"), s.point("ENC.gnd")
    s.line([g,(185,g[1]),(185,1820),(700,1820),(700,ag[1]),ag], GND, True)
    s.line([(700,1820),(1640,1820),(1640,eg[1]),eg], GND, True)
    s.junction(700,1820,GND)
    # Named rail continuations: same ESP32 3V3/GND as L1/L2, conditional on module pinout.
    sm, sz = s.point("STEER.mode"), s.point("STEER.z")
    s.line([sm, (1480, sm[1]), (1480, 1240), (1610, 1240)], LOGIC, True)
    s.line([sz, (1530, sz[1]), (1530, 1240)], LOGIC, True)
    s.junction(1530, 1240, LOGIC)
    s.junction(1610, 1240, LOGIC)
    s.label(1490, 1225, "3V3 · L1", 20, LOGIC)
    em, ez = s.point("ENC.mode"), s.point("ENC.z")
    s.line([em, (2310, em[1])], GND, True)
    s.label(2200, em[1] - 16, "GND · L2", 20, GND)
    s.line([ez, (2200, ez[1])], SIGNAL, True)
    s.label(2210, ez[1] + 8, "Z: để trống", 19, MUTED)
    for port, target, gutter, top_y, column, color in [
        ("sda","sda",150,1060,920,SIGNAL),
        ("scl","scl",115,1035,955,BLUE2),
    ]:
        a,b=s.point(f"ESP.{port}"),s.point(f"STEER.{target}")
        s.wire(f"ESP.{port}",f"STEER.{target}",[(gutter,a[1]),(gutter,top_y),(column,top_y),(column,b[1])],color,True)
    for port,target,gutter,base_y,column,color in [
        ("enc_a","a",150,1780,1675,SIGNAL),
        ("enc_b","b",115,1850,1710,BLUE2),
    ]:
        a,b=s.point(f"ESP.{port}"),s.point(f"ENC.{target}")
        s.wire(f"ESP.{port}",f"ENC.{target}",[(gutter,a[1]),(gutter,base_y),(column,base_y),(column,b[1])],color,True)
    s.note(740, 1490, 720, ["#1 góc lái: GPIO6=SDA, GPIO7=SCL; I²C 3V3.", "#1: MODE và Z/CSN ở mức 3V3 để dùng I²C.", "#2 bánh/trục: GPIO8=A, GPIO9=B; MODE về GND.", "#2: Z để trống; kiểm ABZ và PPR thực nhận.", "Hai module + hai nam châm; không chung trục đo.", "Các mốc 3V3/GND bên phải cùng nguồn ESP.", "Module có jumper: kiểm trước khi đấu bổ sung."], MUTED, "#f3f7fb", 21)
    s.note(1700, 1190, 550, ["GPIO4: ESC_CTRL · GPIO5: SERVO_CTRL.", "GPIO6/7: I²C · GPIO8/9: A/B.", "Map đề xuất; firmware chưa đổi.", "Đối chiếu đúng chân trên module."], AMBER, "#fff8ea", 22)
    s.label(250, 1905, "L2 · GND cảm biến về ESP; GND ESP còn nối ESC/BEC và servo ở Tờ 1.", 23, GND)
    s.label(70, 1950, "ToF và IMU được hoãn. Bốn camera không tự thay thế phép đo tốc độ/góc lái hay kiểm chứng vùng mù.", 23, MUTED)
    s.note(2350, 1170, 350, ["ESP32 — MỤC TIÊU", "Xuất ga / lái thật.", "Đọc encoder tốc độ", "và góc lái đo được.", "Watchdog lệnh hết hạn", "ép dừng khi Pi im lặng.", "Pinmap: chưa áp dụng."], AMBER, "#fff8ea", 21)
    s.note(80, 2030, 1290, ["DỪNG VÀ GIỮ DỪNG — YÊU CẦU KIẾN TRÚC", "Pi dừng nếu vật cản khiến hành lang quỹ đạo không an toàn,", "hoặc dữ liệu / pose / quỹ đạo hết hạn, hoặc mất liên kết laptop.", "ESP32 dừng khi lệnh từ Pi hết hạn / mất USB. Không tự chạy lại.", "Laptop lập lại từ pose mới đo khi xe đã dừng; xác nhận lượt chạy mới."], RED, "#fff3f2", 25)
    s.note(1430, 2030, 1270, ["PHÂN BIỆT HIỆN TẠI VỚI MỤC TIÊU", "Mã hiện có: mô phỏng, thao tác đích gần do người dùng đặt.", "Chưa triển khai hệ Pi phân tán hoặc tự chọn ô đỗ trên xe.", "Firmware hiện tắt PWM; driver phản hồi thật chưa hoàn thiện.", "Hình không xác nhận phần cứng đã lắp / thử hay đạt an toàn."], MUTED, "#f3f7fb", 25)
    return s.save("02-signal-feedback.svg")


def charge_sheet():
    s=Sheet(2200,1350,"03 · SẠC PIN — TÁCH HẲN KHỎI XE","Chế độ sạc riêng: không nối pin vào ESC hoặc tải trên xe trong khi sạc.",3)
    s.background.append(box(70,245,2060,1020,"white","#d6e0e9",20))
    s.node("B3","b3_charger",650,330,400,342.86)
    s.node("BAT","battery2s",1360,330,430,286.67)
    # A wall socket illustration is intentionally not an electrical mains wiring diagram.
    s.drawings += [box(160,390,190,165,"#e8edf3",GND,18),
                   '<circle cx="225" cy="470" r="15" fill="#334155"/>',
                   '<circle cx="285" cy="470" r="15" fill="#334155"/>',
                   text(255,590,"Ổ điện AC 220 V",25,INK,600,"middle")]
    ac=s.point("B3.ac")
    s.line([(350,470),(500,470),(500,ac[1]),ac],GND,width=10)
    s.label(405,400,"C1 · Dây nguồn của sạc",23)
    for port,y,col in [("balance_minus",830,GND),("balance_mid",885,LOGIC),("balance_plus",940,RED)]:
        a,b=s.point("B3."+port),s.point("BAT."+port)
        s.wire("B3."+port,"BAT."+port,[(a[0],y),(b[0],y)],col,width=6)
    s.label(1210,735,["C2 · Cáp cân bằng 2S / 3 dây", "B− • BM • B+", "Đối chiếu cực và khóa giắc"],23,INK,anchor="middle")
    s.cap("BAT.plus",dx=80,dy=0,color=RED)
    s.cap("BAT.minus",dx=80,dy=0,color=GND)
    s.label(1830,560,["Giắc T để rời", "Che kín tiếp điểm", "KHÔNG nối ESC"],23,RED)
    s.note(1260,1010,780,["Chỉ dùng một pack LiPo 2S ở cổng 2S.", "Cổng 3S để trống; không sạc đồng thời 2 pack.", "Pin phải có giắc cân bằng phù hợp.", "Dòng sạc B3 phải nằm trong mức pin cho phép."],AMBER,"#fff8ea",23)
    s.node("OLD","stock_board",130,950,210,210)
    s.label(380,1050,["XL1986RT: cất riêng sau khi thay chức năng.", "Không nối vào mạng mới trên ba tờ này.", "B3 chỉ sạc pin, không cấp nguồn vận hành xe."],23,MUTED)
    s.label(95,1292,"Các ký hiệu B−/BM/B+ mô tả chức năng; không suy ra thứ tự lỗ cắm từ góc nhìn minh họa.",23,MUTED)
    return s.save("03-charging.svg")


def spec():
    gpio={"ESC_CTRL":4,"SERVO_CTRL":5,"SDA":6,"SCL":7,"ENC_A":8,"ENC_B":9}
    return {
        "schema_version":2,
        "revision":"pi4_dual_mt6701_target_v4",
        "status":"proposed_not_hardware_verified",
        "date":"-".join(reversed(DESIGN_DATE.split("/"))),
        "catalog_component_kinds":list(CATALOG_KINDS),
        "catalog_component_count":len(CATALOG_KINDS),
        "architecture":{
            "status":"target_not_distributed_implementation",
            "laptop":["AI on four camera streams","fusion","parking slot selection","trajectory planning"],
            "pi":["onboard sensor acquisition","local measured localization","local trajectory tracking","local obstacle stop"],
            "esp32":["real actuator outputs (target)","encoder and measured steering feedback","expired-command watchdog"],
            "link":"Wi-Fi LAN; 4G optional remote access later",
            "laptop_to_pi":"trajectory and explicit run confirmation, not per-tick steering",
            "pi_to_laptop":"four camera streams, scans, new measured pose, telemetry/status",
            "ai_direct_actuator_control":False,
            "stop_conditions":["unsafe obstacle corridor","stale sensor/pose/trajectory","lost laptop link","expired Pi command or lost USB to ESP32"],
            "automatic_restart":False,
            "restart":"stop; measure new pose; laptop replans; explicit new run confirmation",
            "current_code":"simulation/manual nearby goal; distributed Pi and automatic slot selection not implemented; PWM disabled; physical feedback drivers unfinished",
        },
        "reference_board":"ESP32-S3-DevKitC-1 N16R8",
        "onboard_computer":{"model":"Raspberry Pi 4 Model B","ram_gb":4,"microSD_gb":64,"hardware_tested":False},
        "feedback_sensors":{
            "STEER":{"chip":"MT6701","quantity":1,"role":"absolute steering angle","interface":"I2C","mode":"HIGH at 3.3V","z_csn":"HIGH at 3.3V","module_pinout_verified":False},
            "ENC":{"chip":"MT6701","quantity":1,"role":"wheel/drivetrain speed and distance","interface":"quadrature A/B","mode":"LOW at GND; ABZ configuration verified before use","z":"unconnected output","ppr":"must select and measure; not inferred from 14-bit angle","module_pinout_verified":False},
        },
        "proposed_gpio":gpio,
        "firmware_pinmap_changed":False,
        "components":{
            "PC":"laptop","HUB":"usb_hub","CAM1":"camera","CAM2":"camera","CAM3":"camera","CAM4":"camera",
            "ESP":"esp32","C1":"lidar","ADAPTER":"lidar_adapter","BAT":"battery2s","ESC":"esc1060",
            "MOTOR":"motor280","SERVO":"servo","STEER":"mt6701_steer","ENC":"mt6701","B3":"b3_charger",
            "PI":"raspberry_pi","PSPI":"pi_supply","PSHUB":"hub_supply",
        },
        "operating_nets":[
            {"id":"BAT_PLUS","endpoints":["BAT.plus","ESC.battery_plus","PSPI.vin_plus","PSHUB.vin_plus"],"voltage":"2S: nominal 7.4V, max 8.4V","continuation":"P3+; separate power branches; input range/load/wiring not verified"},
            {"id":"BAT_MINUS","endpoints":["BAT.minus","ESC.battery_minus","PSPI.vin_minus","PSHUB.vin_minus"],"voltage":"battery return","continuation":"P3-; power currents return on rated power harness, not ESP32"},
            {"id":"PI_5V","endpoints":["PSPI.vout_plus","PI.power_5v"],"voltage":"5.1V regulated USB-C supply for Pi 4; recommended 3A","condition":"select converter rated for full 2S range and Pi+C1+ESP USB loads; correct power connector/cable and USB-C negotiation if required; not BEC 6V"},
            {"id":"PI_RETURN","endpoints":["PSPI.vout_minus","PI.power_gnd"],"voltage":"return in Pi power cable"},
            {"id":"HUB_DC","endpoints":["PSHUB.vout_plus","HUB.dc_plus"],"voltage":"as specified by selected powered hub, not assumed","condition":"hub must support dedicated DC input; confirm polarity/current for four cameras and no upstream VBUS backfeed to Pi"},
            {"id":"HUB_RETURN","endpoints":["PSHUB.vout_minus","HUB.dc_minus"],"voltage":"return in hub DC power cable"},
            {"id":"GND","endpoints":["ESP.gnd","ESC.gnd","SERVO.gnd","STEER.gnd","ENC.gnd","ENC.mode"],"voltage":"common signal reference; servo power return directly to ESC/BEC, not through ESP32"},
            {"id":"MOTOR_A","endpoints":["ESC.motor_a","MOTOR.a"],"voltage":"switched motor output; NOT logic GND"},
            {"id":"MOTOR_B","endpoints":["ESC.motor_b","MOTOR.b"],"voltage":"switched motor output; NOT logic GND"},
            {"id":"ESC_CTRL","endpoints":["ESP.esc_pwm","ESC.signal"],"gpio":4,"condition":"confirm ESC accepts 3.3V signal and pulse range"},
            {"id":"SERVO_CTRL","endpoints":["ESP.servo_pwm","SERVO.signal"],"gpio":5,"condition":"confirm stock servo signal/pinout"},
            {"id":"V_SERVO","endpoints":["ESC.bec_plus","SERVO.vplus"],"voltage":6.0,"reference_current_a":3.0,"condition":"connect ONLY after confirming the stock servo supports 6V, actual ESC BEC voltage and load current fit; no parallel supply; never to ESP32 rails or GPIO"},
            {"id":"3V3","endpoints":["ESP.v3v3","STEER.vcc","ENC.vcc","STEER.mode","STEER.z"],"voltage":"3.3V","condition":"breakouts must support 3.3V; verify onboard regulator/pullups and total current"},
            {"id":"SDA","endpoints":["ESP.sda","STEER.sda"],"gpio":6,"condition":"pullups only to3.3V"},
            {"id":"SCL","endpoints":["ESP.scl","STEER.scl"],"gpio":7,"condition":"pullups only to3.3V"},
            {"id":"ENC_A","endpoints":["ESP.enc_a","ENC.a"],"gpio":8,"condition":"confirm MT6701 module MODE and PPR"},
            {"id":"ENC_B","endpoints":["ESP.enc_b","ENC.b"],"gpio":9,"condition":"confirm MT6701 module MODE and PPR"},
        ],
        "usb_links":[["PI.usb1","ESP.usb_native"],["PI.usb2","HUB.upstream"],["PI.usb3","ADAPTER.usb"],
                     *[[f"HUB.usb{i}",f"CAM{i}.usb"] for i in range(1,5)]],
        "sensor_cable_links":[["ADAPTER.lidar","C1.connector"]],
        "wireless_links":[{"endpoints":["PC.wifi","PI.wifi"],"medium":"Wi-Fi LAN","electrical_wire":False}],
        "isolated_ports":["ENC.z"],
        "internal_links_to_verify":[
            {"endpoints":["ESC.battery_minus","ESC.gnd"],"condition":"ESC signal ground and battery return share the reference; verify actual ESC before wiring"},
            {"endpoints":["PSPI.vin_minus","PSPI.vout_minus"],"condition":"select non-isolated converter; verify common return"},
            {"endpoints":["PSHUB.vin_minus","PSHUB.vout_minus"],"condition":"select non-isolated converter; verify common return"},
            {"endpoints":["PI.power_gnd","ESP.gnd","HUB.dc_minus"],"condition":"common reference via USB grounds; never use signal cable for motor/servo load return; verify hub does not backfeed Pi VBUS"},
        ],
        "charging_nets":[{"id":p,"endpoints":["B3."+p,"BAT."+p]} for p in ("balance_minus","balance_mid","balance_plus")],
        "charging_requirements":["battery disconnected from ESC and all vehicle loads","only one battery","B3 2S port only; 3S empty","main T contacts insulated"],
        "omitted_by_user":["emergency_stop","independent_motor_power_cutoff","additional_fuse"],
        "deferred":["ToF","IMU"],
        "unverified":["Pi 4 USB-C supply, cable, voltage drop and USB total load (1.2A limit)","hub model, DC input rating and upstream VBUS backfeed prevention","2S branch harness, converter input range/load transients, voltage drop and heat","four-camera USB/Wi-Fi bandwidth and timestamps","stock servo 6V compatibility, load current and 3-wire pinout","actual ESC BEC voltage/current and 3.3V input acceptance","sensor breakout pad order, mode and mounting","adapter mating/polarity and motor stall current","firmware outputs and physical signal timing"],
    }


def validate_spec(data):
    """Catch internal drawing/netlist contradictions; this is not hardware validation."""
    assert len(set(data["proposed_gpio"].values()))==6
    assert not data["firmware_pinmap_changed"]
    for net in [*data["operating_nets"],*data["charging_nets"],*data["wireless_links"],
                *data["internal_links_to_verify"],
                *({"endpoints":x} for x in data["usb_links"]+data["sensor_cable_links"])]:
        for endpoint in net["endpoints"]:
            name,port=endpoint.split(".")
            assert port in PORT_SPECS[data["components"][name]],endpoint
    endpoints=[p for n in data["operating_nets"] for p in n["endpoints"]]
    assert "VS" not in data["components"]
    assert data["catalog_component_count"] == len(set(data["catalog_component_kinds"])) == len(CATALOG_KINDS)
    assert all(not p.startswith("PC.") for link in data["usb_links"] for p in link)
    assert ["PI.usb1","ESP.usb_native"] in data["usb_links"]
    assert ["PI.usb2","HUB.upstream"] in data["usb_links"]
    assert ["PI.usb3","ADAPTER.usb"] in data["usb_links"]
    assert len(data["usb_links"]) == 7
    assert data["sensor_cable_links"] == [["ADAPTER.lidar","C1.connector"]]
    assert data["wireless_links"][0]["endpoints"] == ["PC.wifi","PI.wifi"]
    assert not data["architecture"]["automatic_restart"]
    assert data["components"]["STEER"] == "mt6701_steer"
    assert data["components"]["ENC"] == "mt6701"
    assert data["onboard_computer"]["ram_gb"] == 4
    assert data["onboard_computer"]["microSD_gb"] == 64
    rails = {net["id"]: set(net["endpoints"]) for net in data["operating_nets"]}
    assert {"STEER.mode", "STEER.z"} <= rails["3V3"]
    assert "ENC.mode" in rails["GND"]
    assert "ENC.z" not in endpoints and data["isolated_ports"] == ["ENC.z"]
    assert len(endpoints) == len(set(endpoints)), "A port must not bridge different operating nets"
    assert "BAT.balance_mid" not in endpoints
    servo_power = next(n for n in data["operating_nets"] if n["id"]=="V_SERVO")
    assert servo_power["voltage"] == 6.0
    assert set(servo_power["endpoints"]) == {"ESC.bec_plus", "SERVO.vplus"}
    assert "ONLY" in servo_power["condition"]
    assert set(next(n for n in data["operating_nets"] if n["id"]=="ESC_CTRL")["endpoints"]) == {"ESP.esc_pwm", "ESC.signal"}
    assert set(next(n for n in data["operating_nets"] if n["id"]=="SERVO_CTRL")["endpoints"]) == {"ESP.servo_pwm", "SERVO.signal"}
    assert set(next(n for n in data["operating_nets"] if n["id"]=="MOTOR_A")["endpoints"])=={"ESC.motor_a","MOTOR.a"}
    assert all(not p.startswith("ESP.") for n in data["charging_nets"] for p in n["endpoints"])


def main():
    data=spec()
    validate_spec(data)
    (OUT/"wiring_spec.json").write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    paths=[system_sheet(),signal_sheet(),charge_sheet()]
    print(json.dumps({"generated":[p.name for p in paths],"netlist_internal_checks":"passed","hardware_verified":False},ensure_ascii=False))


if __name__=="__main__":
    main()
