"""Build three deterministic 2D wiring sheets; no hardware is opened.

Run from any directory: python build_wiring.py
This checks the planned netlist, not physical wiring or electrical compatibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
from pathlib import Path

from components import draw_component, component_ports, PORT_SPECS

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
                           text(92, 181, "THIẾT KẾ ĐỀ XUẤT • Chưa kiểm chứng trên xe • GPIO đề xuất, firmware chưa đổi", 25, "#82500d", 600)]
        self.drawings, self.wires, self.overlays = [], [], []
        self.overlays.append(text(width - 70, height - 28, f"AutoPark · 08/11/2026 · Tờ {index}/3", 21, MUTED, anchor="end"))

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
    s = Sheet(2300, 1650, "01 · NGUỒN, MOTOR VÀ CỤM LÁI", "Pin và ESC rời thay phần công suất của XL1986RT; servo gốc vẫn là bộ phận đánh lái.", 1)
    s.background.append(box(70, 240, 2160, 1280, "#ffffff", "#d6e0e9", 20))
    s.node("BAT", "battery2s", 100, 300, 330, 220)
    s.node("ESC", "esc1060", 880, 300, 420, 280)
    s.node("MOTOR", "motor280", 1740, 325, 360, 216)
    s.node("ESP", "esp32", 240, 760, 350, 487.5)
    s.node("VS", "servo_supply", 920, 1090, 330, 224)
    s.node("SERVO", "servo", 1730, 1050, 360, 260)
    bp, bn = s.point("BAT.plus"), s.point("BAT.minus")
    ep, en = s.point("ESC.battery_plus"), s.point("ESC.battery_minus")
    s.wire("BAT.plus", "ESC.battery_plus", [(500, bp[1]), (500, ep[1])], RED, width=7)
    s.wire("BAT.minus", "ESC.battery_minus", [(540, bn[1]), (540, en[1])], GND, width=7)
    s.label(520, 310, "P1 · Giắc T/Deans đúng cặp", 25)
    s.label(520, 345, "Đối chiếu cực + / −", 22, MUTED)
    vp, vn = s.point("VS.vin_plus"), s.point("VS.vin_minus")
    s.line([(620, ep[1]), (620, vp[1]), vp], RED, True, 6)
    s.line([(675, en[1]), (675, vn[1]), vn], GND, True, 6)
    s.junction(620, ep[1], RED)
    s.junction(675, en[1], GND)
    s.label(690, 1040, ["P2 · Dây chia nguồn 2S (Y harness)", "Từ giắc T chính, không lấy từ giắc cân bằng"], 23, AMBER)
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
    s.cap("ESC.bec_plus", dy=55)
    s.label(1245, 637, "BEC +: bọc cách điện", 22, RED)
    s.note(810, 745, 720, ["Dây đỏ BEC không cấp ESP32 hoặc servo trong bản này.", "Nguồn servo ở dưới chỉ nối sau khi xác nhận V_SERVO.", "Không ghép song song BEC với nguồn servo riêng."], RED, "#fff3f2", 23)
    servo_v = s.point("SERVO.vplus")
    sv = s.point("VS.vout_plus")
    s.wire("VS.vout_plus", "SERVO.vplus", [(1570, sv[1]), (1570, servo_v[1])], RED, True, 7)
    s.label(1310, 1145, "V_SERVO: CHƯA CHỐT", 24, AMBER)
    sg = s.point("SERVO.gnd")
    vg = s.point("VS.vout_minus")
    s.wire("VS.vout_minus", "SERVO.gnd", [(1580, vg[1]), (1580, sg[1])], GND, True, 7)
    star = (1430, 1415)
    s.line([(1430, vg[1]), star], GND, False, 5)
    s.junction(1430, vg[1])
    s.junction(*star)
    eg = s.point("ESC.gnd")
    s.line([eg, (eg[0], 690), (1600, 690), (1600, star[1]), star], GND)
    pg = s.point("ESP.gnd")
    s.line([pg, (175, pg[1]), (175, 1495), (1430, 1495), star], GND)
    s.label(1500, 1460, ["GND chung: cùng mốc điện áp cho tín hiệu.", "Dòng servo về nguồn riêng, không qua ESP."], 22, MUTED)
    u = s.point("ESP.usb_native")
    s.line([u, (u[0], 1375)], USB, width=9)
    s.overlays.append(box(u[0] - 22, 1375, 44, 26, "#dceeff", USB, 6))
    s.label(520, 1380, ["U1 · USB native tới laptop ở Tờ 2", "Nguồn + dữ liệu; không cấp thêm 5V/BEC vào ESP"], 22, USB)
    s.label(100, 570, "Giắc cân bằng pin để rời khi chạy (sạc ở Tờ 3).", 22, MUTED)
    s.label(85, 1567, "Nét đứt: kết nối còn điều kiện xác minh. Giao cắt không chấm = không nối; chấm tròn = cùng nút.", 23, MUTED)
    s.label(85, 1600, "Theo lựa chọn hiện tại: chưa có nút dừng khẩn, phần tử ngắt động lực độc lập và cầu chì bổ sung.", 22, AMBER)
    return s.save("01-system.svg")


def signal_sheet():
    s = Sheet(2400, 2000, "02 · USB, CHÂN ĐIỀU KHIỂN VÀ PHẢN HỒI", "Các tên chân GPIO là map đề xuất cho DevKitC-1; không thay cho việc kiểm tra đúng phiên bản bo/module.", 2)
    s.background += [box(70, 240, 2260, 730, "white", "#d6e0e9", 20),
                     box(70, 1030, 2260, 865, "white", "#d6e0e9", 20)]
    s.node("PC", "laptop", 150, 265, 400, 288.89)
    s.node("HUB", "usb_hub", 900, 270, 330, 180)
    for i, (x, y) in enumerate([(1500, 275), (1950, 275), (1500, 565), (1950, 565)], 1):
        s.node(f"CAM{i}", "camera", x, y, 230, 172.5, label=f"CAMERA USB {i}")
    s.node("C1", "lidar", 140, 650, 300, 264)
    s.node("ADAPTER", "lidar_adapter", 880, 650, 300, 180)
    s.node("ESP", "esp32", 230, 1160, 420, 585)
    s.node("AS", "as5600", 1060, 1180, 350, 269.23)
    s.node("ENC", "mt6701", 1750, 1470, 350, 269.23)
    pc2, hup = s.point("PC.usb2"), s.point("HUB.upstream")
    s.wire("PC.usb2", "HUB.upstream", [(700, pc2[1]), (700, hup[1])], USB, width=8)
    s.label(580, 280, "U2 · Cáp USB upstream", 23, USB)
    camera_vias = {
        1: lambda a,b: [(1370,a[1]),(1370,b[1])],
        2: lambda a,b: [(1410,a[1]),(1410,235),(1890,235),(1890,b[1])],
        3: lambda a,b: [(1430,a[1]),(1430,b[1])],
        4: lambda a,b: [(1470,a[1]),(1470,790),(1890,790),(1890,b[1])],
    }
    for i in range(1,5):
        a, b = s.point(f"HUB.usb{i}"), s.point(f"CAM{i}.usb")
        s.wire(f"HUB.usb{i}", f"CAM{i}.usb", camera_vias[i](a,b), USB, width=7)
    s.note(730, 500, 670, ["U3–U6 · 4 camera USB đã có; chưa chốt hướng gá.", "Hub có nguồn phụ? Chỉ cấp nếu đúng model hỗ trợ.", "Không đưa nguồn tự chế vào cổng hub chưa xác minh."], AMBER, "#fff8ea", 21)
    pc3, au = s.point("PC.usb3"), s.point("ADAPTER.usb")
    s.wire("PC.usb3", "ADAPTER.usb", [(620,pc3[1]),(620,638),(1250,638),(1250,au[1])], USB, width=8)
    cp, al = s.point("C1.connector"), s.point("ADAPTER.lidar")
    s.wire("C1.connector", "ADAPTER.lidar", [(690,cp[1]),(690,al[1])], USB, width=8)
    s.label(500, 900, ["U7–U8 · C1 nối qua adapter USB và cáp gốc của bộ LiDAR.", "Giữ đúng giắc/cực nhà sản xuất; không suy ra pin từ màu dây."], 22, USB)
    pc1, eu = s.point("PC.usb1"), s.point("ESP.usb_native")
    s.wire("PC.usb1", "ESP.usb_native", [(45,pc1[1]),(45,1870),(eu[0],1870)], USB, width=9)
    s.label(80, 990, "U1 · Laptop ↔ USB native/CDC của ESP32: dữ liệu + nguồn. Cổng USB–UART không nối trong bản này.", 23, USB)
    s.label(1050, 1095, "PHẢN HỒI ĐO ĐƯỢC · module và gá chưa chốt", 28)
    p3, g = s.point("ESP.v3v3"), s.point("ESP.gnd")
    av, ev = s.point("AS.vcc"), s.point("ENC.vcc")
    s.line([p3,(180,p3[1]),(180,1135),(995,1135),(995,av[1]),av], LOGIC, True)
    s.line([(995,1135),(1610,1135),(1610,ev[1]),ev], LOGIC, True)
    s.junction(995,1135,LOGIC)
    s.label(1020, 1127, "L1 · 3V3 (chỉ module hỗ trợ 3,3 V)", 22, LOGIC)
    ag, eg = s.point("AS.gnd"), s.point("ENC.gnd")
    s.line([g,(185,g[1]),(185,1820),(700,1820),(700,ag[1]),ag], GND, True)
    s.line([(700,1820),(1640,1820),(1640,eg[1]),eg], GND, True)
    s.junction(700,1820,GND)
    for port, target, gutter, top_y, column, color in [
        ("sda","sda",150,1060,920,SIGNAL),
        ("scl","scl",115,1035,955,BLUE2),
    ]:
        a,b=s.point(f"ESP.{port}"),s.point(f"AS.{target}")
        s.wire(f"ESP.{port}",f"AS.{target}",[(gutter,a[1]),(gutter,top_y),(column,top_y),(column,b[1])],color,True)
    for port,target,gutter,base_y,column,color in [
        ("enc_a","a",150,1780,1675,SIGNAL),
        ("enc_b","b",115,1850,1710,BLUE2),
    ]:
        a,b=s.point(f"ESP.{port}"),s.point(f"ENC.{target}")
        s.wire(f"ESP.{port}",f"ENC.{target}",[(gutter,a[1]),(gutter,base_y),(column,base_y),(column,b[1])],color,True)
    s.note(740, 1490, 720, ["AS5600: GPIO6=SDA, GPIO7=SCL; pull-up chỉ về 3V3.", "VCC trên hình là cổng của module hỗ trợ 3,3 V.", "Thứ tự chân module/IC phải được đối chiếu riêng.", "MT6701: GPIO8=A, GPIO9=B; chốt MODE/ABZ và PPR.", "Nam châm gắn cơ khí lên trục; không phải dây điện."], MUTED, "#f3f7fb", 21)
    s.note(1700, 1190, 550, ["GPIO4: ESC_CTRL · GPIO5: SERVO_CTRL.", "GPIO6/7: I²C · GPIO8/9: A/B.", "Map đề xuất; firmware chưa đổi.", "Đối chiếu đúng chân trên module."], AMBER, "#fff8ea", 22)
    s.label(250, 1905, "L2 · GND cảm biến về ESP; GND ESP còn nối ESC/nguồn servo ở Tờ 1.", 23, GND)
    s.label(70, 1950, "ToF và IMU được hoãn. Bốn camera không tự thay thế phép đo tốc độ/góc lái hay kiểm chứng vùng mù.", 23, MUTED)
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
        "schema_version":1,
        "status":"proposed_not_hardware_verified",
        "date":"2026-11-08",
        "reference_board":"ESP32-S3-DevKitC-1 N16R8",
        "proposed_gpio":gpio,
        "firmware_pinmap_changed":False,
        "components":{
            "PC":"laptop","HUB":"usb_hub","CAM1":"camera","CAM2":"camera","CAM3":"camera","CAM4":"camera",
            "ESP":"esp32","C1":"lidar","ADAPTER":"lidar_adapter","BAT":"battery2s","ESC":"esc1060",
            "MOTOR":"motor280","SERVO":"servo","VS":"servo_supply","AS":"as5600","ENC":"mt6701","B3":"b3_charger",
        },
        "operating_nets":[
            {"id":"BAT_PLUS","endpoints":["BAT.plus","ESC.battery_plus","VS.vin_plus"],"voltage":"2S: nominal 7.4V, max 8.4V"},
            {"id":"BAT_MINUS","endpoints":["BAT.minus","ESC.battery_minus","VS.vin_minus"],"voltage":"battery return"},
            {"id":"GND","endpoints":["ESP.gnd","ESC.gnd","VS.vout_minus","SERVO.gnd","AS.gnd","ENC.gnd"],"voltage":"common signal reference; servo power return directly to its supply"},
            {"id":"MOTOR_A","endpoints":["ESC.motor_a","MOTOR.a"],"voltage":"switched motor output; NOT logic GND"},
            {"id":"MOTOR_B","endpoints":["ESC.motor_b","MOTOR.b"],"voltage":"switched motor output; NOT logic GND"},
            {"id":"ESC_CTRL","endpoints":["ESP.esc_pwm","ESC.signal"],"gpio":4,"condition":"confirm ESC accepts 3.3V signal and pulse range"},
            {"id":"SERVO_CTRL","endpoints":["ESP.servo_pwm","SERVO.signal"],"gpio":5,"condition":"confirm stock servo signal/pinout"},
            {"id":"V_SERVO","endpoints":["VS.vout_plus","SERVO.vplus"],"voltage":None,"condition":"choose and measure supply after confirming stock servo voltage/current; no ESC BEC connection"},
            {"id":"3V3","endpoints":["ESP.v3v3","AS.vcc","ENC.vcc"],"voltage":"3.3V","condition":"breakouts must support 3.3V; verify onboard regulator/pullups and total current"},
            {"id":"SDA","endpoints":["ESP.sda","AS.sda"],"gpio":6,"condition":"pullups only to3.3V"},
            {"id":"SCL","endpoints":["ESP.scl","AS.scl"],"gpio":7,"condition":"pullups only to3.3V"},
            {"id":"ENC_A","endpoints":["ESP.enc_a","ENC.a"],"gpio":8,"condition":"confirm MT6701 module MODE and PPR"},
            {"id":"ENC_B","endpoints":["ESP.enc_b","ENC.b"],"gpio":9,"condition":"confirm MT6701 module MODE and PPR"},
        ],
        "usb_links":[["PC.usb1","ESP.usb_native"],["PC.usb2","HUB.upstream"],["PC.usb3","ADAPTER.usb"],
                     ["ADAPTER.lidar","C1.connector"],*[ [f"HUB.usb{i}",f"CAM{i}.usb"] for i in range(1,5)]],
        "isolated_ports":["ESC.bec_plus"],
        "internal_links_to_verify":[
            {"endpoints":["ESC.battery_minus","ESC.gnd"],"condition":"ESC signal ground and battery return share the reference; verify actual ESC before wiring"},
            {"endpoints":["VS.vin_minus","VS.vout_minus"],"condition":"only if the selected servo regulator is non-isolated; do not assume all modules have this internal link","required_for_diagram":False},
        ],
        "charging_nets":[{"id":p,"endpoints":["B3."+p,"BAT."+p]} for p in ("balance_minus","balance_mid","balance_plus")],
        "charging_requirements":["battery disconnected from ESC and all vehicle loads","only one battery","B3 2S port only; 3S empty","main T contacts insulated"],
        "omitted_by_user":["emergency_stop","independent_motor_power_cutoff","additional_fuse"],
        "deferred":["ToF","IMU"],
        "unverified":["servo supply voltage/current and 3-wire pinout","actual ESC 3.3V input acceptance","sensor breakout pad order, mode and mounting","USB hub external power capability","adapter mating/polarity and motor stall current","firmware outputs and physical signal timing"],
    }


def validate_spec(data):
    """Catch internal drawing/netlist contradictions; this is not hardware validation."""
    assert len(set(data["proposed_gpio"].values()))==6
    assert not data["firmware_pinmap_changed"]
    for net in [*data["operating_nets"],*data["charging_nets"],*({"endpoints":x} for x in data["usb_links"])]:
        for endpoint in net["endpoints"]:
            name,port=endpoint.split(".")
            assert port in PORT_SPECS[data["components"][name]],endpoint
    endpoints=[p for n in data["operating_nets"] for p in n["endpoints"]]
    assert "ESC.bec_plus" not in endpoints
    assert "BAT.balance_mid" not in endpoints
    assert next(n for n in data["operating_nets"] if n["id"]=="V_SERVO")["voltage"] is None
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
