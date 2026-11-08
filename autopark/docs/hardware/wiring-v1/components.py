"""Reusable, deterministic SVG component drawings for the AutoPark wiring sheets.

Coordinates describe diagram terminals, not unverified physical PCB header positions.
Each component's title, body and terminals fit its native box. All positions scale
with the supplied width/height, so external wires can use component_ports().
"""
from __future__ import annotations

from html import escape

COLORS = {
    "ink": "#13283f", "muted": "#5b6f82", "pcb": "#14685c", "board": "#202c38",
    "red": "#d83737", "ground": "#334155", "signal": "#0c8b9a", "logic": "#8b5cf6",
    "usb": "#2875c7", "amber": "#c57912", "metal": "#cbd5df", "white": "#f8fafc",
}

NATIVE_SIZES = {
    "esp32": (280, 390), "esc1060": (360, 240), "motor280": (300, 180),
    "servo": (290, 210), "battery2s": (300, 200), "b3_charger": (280, 240),
    "as5600": (260, 200), "mt6701": (260, 200), "laptop": (360, 260),
    "usb_hub": (330, 180), "lidar": (250, 220), "lidar_adapter": (250, 150),
    "camera": (200, 150), "servo_supply": (280, 190), "stock_board": (250, 250),
}


def _p(x, y, side, label, color, provisional=False):
    return {"x": x, "y": y, "side": side, "label": label, "color": COLORS[color],
            "provisional": provisional}


PORT_SPECS = {
    "esp32": {
        "usb_uart": _p(92, 390, "bottom", "USB–UART", "usb"),
        "usb_native": _p(185, 390, "bottom", "USB native", "usb"),
        "v3v3": _p(68, 48, "left", "3V3", "logic"),
        "gnd": _p(68, 335.7, "left", "GND", "ground"),
        "esc_pwm": _p(68, 89.1, "left", "GPIO4", "signal"),
        "servo_pwm": _p(68, 102.8, "left", "GPIO5", "signal"),
        "sda": _p(68, 116.5, "left", "GPIO6", "signal"),
        "scl": _p(68, 130.2, "left", "GPIO7", "signal"),
        "enc_a": _p(68, 198.7, "left", "GPIO8", "signal"),
        "enc_b": _p(68, 239.8, "left", "GPIO9", "signal"),
    },
    "esc1060": {
        "battery_plus": _p(0, 70, "left", "BAT +", "red"),
        "battery_minus": _p(0, 106, "left", "BAT −", "ground"),
        "motor_a": _p(360, 70, "right", "Motor A", "usb"),
        "motor_b": _p(360, 110, "right", "Motor B", "amber"),
        "signal": _p(238, 240, "bottom", "S", "signal"),
        "bec_plus": _p(274, 240, "bottom", "BEC +", "red"),
        "gnd": _p(310, 240, "bottom", "GND", "ground"),
    },
    "motor280": {
        "a": _p(0, 67, "left", "A", "usb"),
        "b": _p(0, 115, "left", "B", "amber"),
    },
    "servo": {
        "signal": _p(0, 80, "left", "S", "signal", True),
        "vplus": _p(0, 114, "left", "+V servo", "red", True),
        "gnd": _p(0, 148, "left", "GND", "ground", True),
    },
    "battery2s": {
        "plus": _p(300, 70, "right", "+", "red"),
        "minus": _p(300, 106, "right", "−", "ground"),
        "balance_minus": _p(81, 200, "bottom", "B−", "ground"),
        "balance_mid": _p(112, 200, "bottom", "BM", "logic"),
        "balance_plus": _p(143, 200, "bottom", "B+", "red"),
    },
    "b3_charger": {
        "ac": _p(0, 92, "left", "AC", "usb"),
        "balance_minus": _p(169, 240, "bottom", "B−", "ground"),
        "balance_mid": _p(200, 240, "bottom", "BM", "logic"),
        "balance_plus": _p(231, 240, "bottom", "B+", "red"),
    },
    "as5600": {
        "vcc": _p(0, 70, "left", "VCC 3V3*", "logic", True),
        "gnd": _p(0, 103, "left", "GND", "ground", True),
        "sda": _p(0, 136, "left", "SDA", "signal", True),
        "scl": _p(0, 169, "left", "SCL", "signal", True),
    },
    "mt6701": {
        "vcc": _p(0, 70, "left", "VCC 3V3*", "logic", True),
        "gnd": _p(0, 103, "left", "GND", "ground", True),
        "a": _p(0, 136, "left", "A (ABZ)*", "signal", True),
        "b": _p(0, 169, "left", "B (ABZ)*", "signal", True),
    },
    "laptop": {
        "usb1": _p(0, 112, "left", "USB 1", "usb"),
        "usb2": _p(360, 112, "right", "USB 2", "usb"),
        "usb3": _p(360, 157, "right", "USB 3", "usb"),
        "ac": _p(0, 157, "left", "Nguồn PC", "usb"),
    },
    "usb_hub": {
        "upstream": _p(0, 80, "left", "USB host", "usb"),
        "usb1": _p(330, 52, "right", "1", "usb"),
        "usb2": _p(330, 85, "right", "2", "usb"),
        "usb3": _p(330, 118, "right", "3", "usb"),
        "usb4": _p(330, 151, "right", "4", "usb"),
        "dc_in": _p(94, 180, "bottom", "Nguồn phụ?", "amber", True),
    },
    "lidar": {"connector": _p(250, 159, "right", "Cáp C1", "usb")},
    "lidar_adapter": {
        "lidar": _p(0, 80, "left", "Cáp C1", "usb"),
        "usb": _p(250, 80, "right", "USB", "usb"),
    },
    "camera": {"usb": _p(0, 103, "left", "USB", "usb")},
    "servo_supply": {
        "vin_plus": _p(0, 76, "left", "IN +", "red", True),
        "vin_minus": _p(0, 132, "left", "IN −", "ground", True),
        "vout_plus": _p(280, 76, "right", "OUT +", "red", True),
        "vout_minus": _p(280, 132, "right", "OUT −", "ground", True),
    },
    "stock_board": {},
}

TITLES = {
    "esp32": "ESP32-S3 DevKitC-1", "esc1060": "ESC 1060 BRUSHED",
    "motor280": "MOTOR GỐC 280–60T", "servo": "CỤM LÁI GỐC · 3 DÂY",
    "battery2s": "PIN LiPo 2S · DỰ KIẾN", "b3_charger": "B3 PRO · SẠC CÂN BẰNG",
    "as5600": "CẢM BIẾN GÓC AS5600", "mt6701": "ENCODER MT6701 · ỨNG VIÊN",
    "laptop": "MÁY TÍNH CHẠY AUTOPARK", "usb_hub": "HUB USB HIỆN CÓ",
    "lidar": "RPLIDAR C1", "lidar_adapter": "ADAPTER USB CỦA C1",
    "camera": "CAMERA USB", "servo_supply": "NGUỒN SERVO · CHƯA CHỌN",
    "stock_board": "XL1986RT · BO GỐC",
}

ALIASES = {"regulated_servo_supply": "servo_supply", "esc": "esc1060", "battery": "battery2s",
           "encoder": "mt6701", "charger": "b3_charger", "motor": "motor280"}


def _n(value):
    return f"{float(value):.3f}".rstrip("0").rstrip(".") or "0"


def _tag(name, **attrs):
    return "<" + name + " " + " ".join(f'{key.replace("_", "-")}="{escape(str(value), quote=True)}"'
                                       for key, value in attrs.items()) + "/>"


def rect(x, y, w, h, fill, stroke="none", rx=0, sw=1, **extra):
    return _tag("rect", x=_n(x), y=_n(y), width=_n(w), height=_n(h), fill=fill, stroke=stroke,
                rx=_n(rx), stroke_width=_n(sw), **extra)


def circle(x, y, radius, fill, stroke="none", sw=1, **extra):
    return _tag("circle", cx=_n(x), cy=_n(y), r=_n(radius), fill=fill, stroke=stroke,
                stroke_width=_n(sw), **extra)


def line(x1, y1, x2, y2, color, width=2, **extra):
    return _tag("line", x1=_n(x1), y1=_n(y1), x2=_n(x2), y2=_n(y2), stroke=color,
                stroke_width=_n(width), stroke_linecap="round", **extra)


def path(d, fill="none", stroke="none", sw=1, **extra):
    return _tag("path", d=d, fill=fill, stroke=stroke, stroke_width=_n(sw),
                stroke_linecap="round", stroke_linejoin="round", **extra)


def text(x, y, value, size=12, fill=None, anchor="start", weight=400, **extra):
    attrs = {"x": _n(x), "y": _n(y), "font-size": _n(size), "fill": fill or COLORS["ink"],
             "text-anchor": anchor, "font-weight": weight,
             "font-family": "Arial, DejaVu Sans, sans-serif", **extra}
    return "<text " + " ".join(f'{k}="{escape(str(v), quote=True)}"' for k, v in attrs.items()) + ">" + escape(str(value)) + "</text>"


def _wire(points, color, width=4, dashed=False):
    return _tag("polyline", points=" ".join(f"{_n(x)},{_n(y)}" for x, y in points), fill="none",
                stroke=color, stroke_width=width, stroke_linecap="round", stroke_linejoin="round",
                **({"stroke-dasharray": "5 4"} if dashed else {}))


def _chip(x, y, w, h, label="", pins=4):
    out = []
    for i in range(pins):
        py = y + 5 + i * (h - 10) / max(1, pins - 1)
        out += [rect(x - 6, py - 2, 8, 4, "#b9c8d4"), rect(x + w - 2, py - 2, 8, 4, "#b9c8d4")]
    out += [rect(x, y, w, h, "#1e293b", "#0b1421", 3), circle(x + 5, y + 5, 1.5, "#dbe5ec")]
    if label:
        out.append(text(x + w / 2, y + h / 2 + 3, label, min(11, w / max(4, len(label)) * 1.45), "#d8e4ec", "middle"))
    return "".join(out)


def _screw(x, y, radius=5):
    return circle(x, y, radius, "#101c28", "#8293a1", 1.2) + line(x - radius / 2, y, x + radius / 2, y, "#9fafbc", 1)


def _ports(kind, labels=None):
    out = []
    for key, spec in PORT_SPECS[kind].items():
        x, y = spec["x"], spec["y"]
        out.append(circle(x, y, 4.5, "white", spec["color"], 2,
                          **({"stroke-dasharray": "3 2"} if spec["provisional"] else {})))
        caption = (labels or {}).get(key, spec["label"])
        if kind == "esp32" and spec["side"] == "left":
            out.append(text(x - 9, y + 3, caption, 9.5, spec["color"], "end", 700))
        elif spec["side"] == "left":
            out.append(text(x + 9, y - 7, caption, 10.5, spec["color"], weight=700))
        elif spec["side"] == "right":
            out.append(text(x - 9, y - 7, caption, 10.5, spec["color"], "end", 700))
        elif spec["side"] == "bottom":
            out.append(text(x, y - 9, caption, 9.5, spec["color"], "middle", 700))
    return "".join(out)


_DRAWERS = {}


def component_ports(kind, x=0, y=0, w=None, h=None):
    """Absolute wiring-anchor coordinates for this component's requested rectangle."""
    kind = ALIASES.get(kind, kind)
    nw, nh = NATIVE_SIZES[kind]
    sx, sy = (nw if w is None else w) / nw, (nh if h is None else h) / nh
    return {name: (x + spec["x"] * sx, y + spec["y"] * sy)
            for name, spec in PORT_SPECS[kind].items()}


def draw_component(kind, x=0, y=0, w=None, h=None, *, label=None, subtitle=None,
                   port_labels=None, show_ports=True):
    """Return a self-contained SVG group; it contains no external images or fonts.

    Terminals are functional diagram anchors. They never assert the physical pin
    sequence of unconfirmed ESP32/sensor modules. port_labels may replace captions
    after the actual hardware has been verified; keys stay stable for routing.
    """
    kind = ALIASES.get(kind, kind)
    nw, nh = NATIVE_SIZES[kind]
    sx, sy = (nw if w is None else w) / nw, (nh if h is None else h) / nh
    body = _DRAWERS.get(kind, lambda: "")()
    header = text(nw / 2, 16, label or TITLES[kind], 13, anchor="middle", weight=700)
    foot = text(nw / 2, nh - 5, subtitle, 10, COLORS["muted"], "middle") if subtitle else ""
    return (f'<g transform="translate({_n(x)} {_n(y)}) scale({_n(sx)} {_n(sy)})" data-component="{kind}">'
            + header + body + (_ports(kind, port_labels) if show_ports else "") + foot + "</g>")


def _esp32():
    # Reference orientation: antenna up, two USB connectors down, J1 at left.
    left = ["3V3", "3V3", "RST", "4", "5", "6", "7", "15", "16", "17", "18", "8",
            "3", "46", "9", "10", "11", "12", "13", "14", "5V", "G"]
    right = ["G", "TX", "RX", "1", "2", "42", "41", "40", "39", "38", "37", "36",
             "35", "0", "45", "48", "47", "21", "20", "19", "G", "G"]
    out = [rect(60, 29, 160, 337, COLORS["board"], "#07121e", 8, 2),
           rect(62, 39, 13, 308, "#0a1521", rx=3), rect(205, 39, 13, 308, "#0a1521", rx=3)]
    for index, (a, b) in enumerate(zip(left, right)):
        yy = 48 + index * 13.7
        out += [rect(64, yy - 4, 8, 8, "#d5b15d", "#f6de9f", 1),
                rect(208, yy - 4, 8, 8, "#d5b15d", "#f6de9f", 1),
                text(79, yy + 2.8, a, 7.7, "#e1e8ef"),
                text(201, yy + 2.8, b, 7.7, "#e1e8ef", "end")]
    out += [rect(91, 42, 98, 136, "#557665", rx=2),
            path("M98 66 V48 H109 V60 H120 V48 H131 V60 H142 V48 H153 V60 H164 V48 H180", stroke="#c8af5c", sw=3),
            rect(95, 73, 90, 101, "#c5ccd0", "#9da8ad", 4, 1.5),
            rect(99, 77, 82, 93, "#d9dde0", "#e8ecee", 2),
            text(140, 100, "ESPRESSIF", 9, "#5d6871", "middle", 700),
            text(140, 121, "ESP32-S3", 13, "#485562", "middle", 700),
            text(140, 138, "WROOM-1", 9.5, "#65717b", "middle"),
            text(140, 158, "N16R8*", 9, "#65717b", "middle"),
            _chip(115, 190, 49, 42, "USB", 5),
            rect(108, 247, 14, 23, "#9ba9b5", rx=2), rect(135, 248, 35, 15, "#364d5b", rx=2),
            circle(156, 287, 4.5, "#7fe2c5", "#e7faf7", 1),
            text(140, 319, "DevKitC-1", 10, "#e2eaf0", "middle"),
            text(89, 35, "J1", 7.5, "#f4d68b"), text(192, 35, "J3", 7.5, "#f4d68b"),
            rect(82, 338, 30, 12, "#5b6c7a", "#94a3b8", 2), rect(168, 338, 30, 12, "#5b6c7a", "#94a3b8", 2),
            text(97, 334, "RST", 7, "#dce8f0", "middle"), text(183, 334, "BOOT", 7, "#dce8f0", "middle"),
            rect(77, 355, 32, 20, "#c6d1dc", "#778995", 4, 1.5),
            rect(80, 363, 26, 8, "#1a2938", rx=2),
            rect(169, 355, 32, 20, "#c6d1dc", "#778995", 4, 1.5),
            rect(172, 363, 26, 8, "#1a2938", rx=2),
            line(92, 375, 92, 390, COLORS["usb"], 4), line(185, 375, 185, 390, COLORS["usb"], 4)]
    return "".join(out)


def _esc1060():
    out = [_wire([(0, 70), (53, 70), (88, 88)], COLORS["red"], 6),
           _wire([(0, 106), (53, 106), (88, 114)], COLORS["ground"], 6),
           rect(18, 53, 24, 71, "#9c2830", "#60242a", 4, 2),
           rect(20, 65, 14, 5, "#f2d180", rx=1), rect(28, 91, 5, 16, "#f2d180", rx=1),
           text(30, 140, "T-plug", 10, COLORS["muted"], "middle"),
           _wire([(220, 79), (303, 70), (360, 70)], "#2778bd", 6),
           _wire([(220, 105), (307, 110), (360, 110)], "#e7b323", 6),
           rect(313, 63, 27, 14, "#d6d4bb", "#a59659", 6, 1.5),
           rect(313, 103, 27, 14, "#d6d4bb", "#a59659", 6, 1.5),
           text(329, 138, "bullet", 10, COLORS["muted"], "middle"),
           rect(86, 57, 144, 128, "#1f2c39", "#071827", 13, 2),
           rect(98, 68, 117, 92, "#d83c39", "#922724", 6, 1.5)]
    for xx in range(104, 213, 12):
        out += [rect(xx, 74, 5, 80, "#ed7972", rx=1), line(xx + 5, 75, xx + 5, 153, "#852422", 1)]
    out += [rect(112, 95, 87, 45, "#202d38", "#7e2a27", 3),
            text(155, 111, "QUICRUN", 10, "white", "middle", 700),
            text(155, 130, "1060", 16, "white", "middle", 700),
            circle(230, 47, 16, "#182433", "#697b8e", 2), circle(230, 47, 10, "#c7cfd5", "#8e9ca8", 1),
            line(222, 47, 238, 47, "#768798", 1), line(230, 39, 230, 55, "#768798", 1),
            _wire([(205, 160), (238, 177), (238, 240)], "#dbdedb", 3),
            _wire([(211, 164), (274, 181), (274, 240)], COLORS["red"], 3),
            _wire([(217, 168), (310, 185), (310, 240)], COLORS["ground"], 3),
            rect(225, 193, 99, 27, "#162536", "#07111d", 3)]
    for xx in (238, 274, 310):
        out.append(rect(xx - 4, 205, 8, 10, "#dabd72", rx=1))
    out += [_wire([(103, 171), (86, 196), (62, 196)], COLORS["red"], 2),
            _wire([(110, 176), (88, 207), (62, 207)], COLORS["ground"], 2),
            rect(24, 183, 44, 33, "#263442", "#121d2b", 5, 1.5),
            rect(37, 190, 17, 18, "#e24d3c", "#722020", 2),
            text(46, 231, "Công tắc ESC", 9, COLORS["muted"], "middle")]
    return "".join(out)


def _motor280():
    out = [_wire([(0, 67), (60, 67), (78, 78)], COLORS["red"], 5),
           _wire([(0, 115), (60, 115), (78, 112)], COLORS["ground"], 5),
           rect(54, 80, 28, 29, "#eee8d7", "#b6b2a8", 2),
           rect(83, 47, 149, 103, "#53616c", "#1a2834", 18, 2),
           rect(87, 55, 140, 16, "#a9b1b8", rx=8), rect(88, 128, 139, 12, "#263641", rx=5),
           _tag("ellipse", cx=88, cy=99, rx=12, ry=49, fill="#c0c9cc", stroke="#576875", stroke_width=2),
           _tag("ellipse", cx=228, cy=99, rx=14, ry=49, fill="#bcc6cb", stroke="#576875", stroke_width=2),
           _tag("ellipse", cx=235, cy=99, rx=8, ry=30, fill="#d6dde0", stroke="#9aaab4", stroke_width=1),
           rect(235, 92, 52, 14, "#b8c4ce", "#617588", 3, 1.5),
           line(241, 95, 282, 95, "#f0f4f5", 2),
           text(157, 95, "280 Motor", 17, "#e0e6e9", "middle", 700),
           text(157, 118, "60T", 21, "#e0e6e9", "middle", 700),
           text(153, 171, "Motor kéo hiện có · theo ảnh xe", 11, COLORS["muted"], "middle")]
    return "".join(out)


def _servo():
    out = [_wire([(0, 80), (63, 80), (92, 105)], "#d5a42a", 3),
           _wire([(0, 114), (61, 114), (92, 118)], COLORS["red"], 3),
           _wire([(0, 148), (62, 148), (92, 131)], "#7c4d32", 3),
           rect(91, 70, 139, 103, "#202a35", "#0a1623", 8, 2),
           rect(99, 77, 123, 26, "#3e4a55", rx=5),
           rect(84, 86, 12, 55, "#263340", rx=2), rect(230, 86, 14, 55, "#263340", rx=2),
           _screw(90, 101, 3.5), _screw(238, 101, 3.5),
           circle(192, 73, 18, "#2d3944", "#70808d", 1.5),
           rect(186, 38, 12, 77, "#d2d9de", "#8494a1", 6, 1.5),
           circle(192, 73, 7, "#768795", "#cbd7df", 1),
           _screw(192, 73, 3), circle(192, 45, 2.2, "#495b69"), circle(192, 103, 2.2, "#495b69"),
           text(159, 130, "SERVO LÁI", 14, "#dbe6ed", "middle", 700),
           text(159, 149, "giữ cụm gốc", 11, "#b1c3cf", "middle"),
           text(145, 194, "Điện áp / thứ tự dây: cần xác minh", 10.5, COLORS["amber"], "middle", 700)]
    return "".join(out)


def _battery2s():
    out = [rect(22, 39, 198, 112, "#2d3c4a", "#142432", 9, 2),
           path("M23 47 L42 36 H202 L219 47", fill="#adb8c3", stroke="#748591"),
           rect(34, 50, 171, 87, "#eabf38", "#f7db77", 3),
           text(119, 77, "LiPo 2S", 23, "#1d2d3d", "middle", 700),
           text(119, 99, "7,4 V · 1500 mAh", 15, "#253648", "middle", 700),
           text(119, 121, "30C · thông số đang chọn", 10, "#485569", "middle"),
           _wire([(218, 65), (260, 70), (300, 70)], COLORS["red"], 6),
           _wire([(219, 117), (262, 106), (300, 106)], COLORS["ground"], 6),
           rect(263, 54, 23, 68, "#a52d36", "#72252a", 4, 2),
           rect(268, 66, 14, 5, "#dec47c", rx=1), rect(274, 92, 5, 16, "#dec47c", rx=1),
           text(273, 139, "T-plug", 10, COLORS["muted"], "middle"),
           _wire([(60, 150), (81, 171), (81, 200)], COLORS["ground"], 2.5),
           _wire([(72, 150), (112, 171), (112, 200)], "#7a8491", 2.5),
           _wire([(84, 150), (143, 171), (143, 200)], COLORS["red"], 2.5),
           rect(66, 164, 93, 21, "#f5f1e6", "#aeb7c0", 2, 1.5),
           text(214, 180, "JST-XH 2S", 10, COLORS["muted"], "middle")]
    for xx in (81, 112, 143):
        out.append(rect(xx - 3.5, 169, 7, 10, "#a5aeb5", rx=1))
    return "".join(out)


def _b3_charger():
    out = [_wire([(0, 92), (40, 92)], COLORS["ground"], 7),
           rect(36, 35, 218, 168, "#1d2a37", "#06101d", 16, 2.5),
           rect(48, 46, 195, 144, "#27394b", "#506575", 11, 1),
           rect(57, 57, 176, 83, "#15293d", rx=6),
           text(145, 88, "B3 Pro", 29, "#eff6fc", "middle", 700),
           text(145, 112, "LiPo BALANCE CHARGER", 10.5, "#b4cadb", "middle", 700),
            text(145, 130, "AC 110–240 V", 10.5, "#a0b7c8", "middle"),
            text(145, 144, "Đọc nhãn 2S, không dựa vị trí hình", 8.5, "#eec67c", "middle")]
    for i, xx in enumerate((89, 144, 199), 1):
        out += [circle(xx, 158, 6, "#4ec8a1", "#97efd3", 1),
                text(xx, 177, f"CELL {i}", 8.5, "#bfd0dc", "middle")]
    out += [rect(60, 192, 64, 20, "#dddcd4", "#8a959b", 2),
            rect(175, 192, 50, 20, "#dddcd4", "#8a959b", 2),
            text(92, 226, "3S · không dùng", 9.5, COLORS["muted"], "middle"),
            text(200, 187, "2S", 10, "#e7eff5", "middle", 700)]
    for xx in (70, 85, 100, 115):
        out.append(rect(xx - 2, 197, 4, 10, "#596a78", rx=1))
    for physical_x, terminal_x, color in ((184, 169, "ground"), (200, 200, "logic"), (216, 231, "red")):
        out += [rect(physical_x - 3, 197, 6, 10, "#596a78", rx=1),
                _wire([(physical_x, 212), (terminal_x, 224), (terminal_x, 240)], COLORS[color], 2.5)]
    return "".join(out)


def _angle_module(kind):
    is_steer = kind == "as5600"
    chipname = "AS5600" if is_steer else "MT6701"
    out = [rect(94, 55, 126, 121, "#16725e" if is_steer else "#236b87", "#0c433a", 8, 2),
           circle(107, 68, 4, "#f1e9ca", "#9f955e", 1), circle(207, 163, 4, "#f1e9ca", "#9f955e", 1),
           _chip(142, 99, 43, 35, chipname, 4),
           rect(144, 151, 19, 8, "#b6c7bd", rx=1), rect(172, 151, 16, 8, "#b6c7bd", rx=1),
           circle(165, 65, 24, "#d9dee3", "#84939f", 1.5),
           path("M165 41 A24 24 0 0 0 165 89 Z", fill="#be4545", stroke="none"),
           path("M165 41 A24 24 0 0 1 165 89 Z", fill="#456fa8", stroke="none"),
           text(154, 69, "N", 11, "white", "middle", 700), text(176, 69, "S", 11, "white", "middle", 700),
           path("M190 53 Q202 64 191 76", stroke=COLORS["amber"], sw=2),
           path("M190 76 l0 -7 l6 3 Z", fill=COLORS["amber"]),
           text(165, 34, "Nam châm gá trên trục", 9.7, COLORS["muted"], "middle"),
           text(130, 194, "* Module / thứ tự chân cần đối chiếu", 10, COLORS["amber"], "middle", 700)]
    for key, spec in PORT_SPECS[kind].items():
        yy = spec["y"]
        out += [_wire([(0, yy), (82, yy), (94, yy)], spec["color"], 2.5, True),
                circle(103, yy, 3.2, "#d6bd6d", "#f8e5a2", 1)]
    return "".join(out)


def _servo_supply():
    out = [rect(58, 47, 164, 113, "#256f65", "#104e47", 7, 2),
           rect(55, 64, 23, 80, "#4a81b3", "#1b537c", 3),
           rect(202, 64, 23, 80, "#4a81b3", "#1b537c", 3),
           _screw(66, 77, 5), _screw(66, 131, 5), _screw(213, 77, 5), _screw(213, 131, 5),
           circle(119, 82, 21, "#394249", "#90a5af", 2),
           circle(119, 82, 12, "#a48852", "#c5b17e", 3),
           _chip(156, 73, 26, 37, "REG", 3),
           rect(144, 126, 33, 23, "#3174aa", "#123d63", 2),
           circle(160, 137, 6, "#cbd6df", "#a5b5c0", 1), line(156, 137, 164, 137, "#41586a", 1),
           circle(94, 133, 11, "#1e293b", "#8b9ca8", 1.5),
           text(140, 181, "V_SERVO: đo / xác nhận trước", 10.5, COLORS["amber"], "middle", 700)]
    for key, spec in PORT_SPECS["servo_supply"].items():
        end = 58 if spec["side"] == "left" else 222
        out.append(line(spec["x"], spec["y"], end, spec["y"], spec["color"], 3, stroke_dasharray="5 3"))
    return "".join(out)


def _laptop():
    out = [rect(45, 35, 270, 157, "#263545", "#101c29", 11, 2),
           rect(58, 48, 244, 129, "#132a40", "#476881", 3),
           text(180, 83, "AutoPark", 24, "#dff5ff", "middle", 700),
           text(180, 106, "Lập đường · giao diện · bản ghi", 12, "#acc5d9", "middle"),
           path("M78 148 L122 148 Q143 148 153 134 L178 121 Q190 112 207 129 L232 151 L281 151", stroke="#58d3b5", sw=3),
           rect(196, 136, 20, 10, "#efc358", rx=3),
           path("M45 192 L315 192 L347 234 Q347 241 335 243 H25 Q13 241 13 234 Z", "#9daeba", "#415468", 2),
           path("M65 198 H296 L312 223 H49 Z", "#536779", "#6d7d8c", 1),
           rect(145, 224, 70, 13, "#b8c5ce", "#788c9e", 2),
           line(0, 112, 45, 112, COLORS["usb"], 5),
           line(0, 157, 45, 157, COLORS["ground"], 4),
           line(315, 112, 360, 112, COLORS["usb"], 5),
           line(315, 157, 360, 157, COLORS["usb"], 5)]
    for yy in (203, 210, 217):
        for xx in range(65, 291, 15):
            out.append(rect(xx, yy, 10, 3.5, "#c2ced8", rx=.7))
    return "".join(out)


def _usb_hub():
    out = [rect(58, 35, 208, 125, "#232e3b", "#0b1724", 13, 2),
           rect(70, 47, 162, 100, "#334557", "#526475", 7),
           text(150, 82, "USB HUB", 21, "#e2edf5", "middle", 700),
           text(150, 106, "4 camera", 13, "#c6d5df", "middle"),
           text(150, 127, "model cần đối chiếu", 10, "#b4c8d8", "middle"),
           _wire([(0, 80), (38, 80), (58, 82)], COLORS["usb"], 5),
           rect(26, 68, 26, 23, "#b9c5ce", "#748796", 3),
           line(94, 160, 94, 180, COLORS["amber"], 3, stroke_dasharray="4 3")]
    for key in ("usb1", "usb2", "usb3", "usb4"):
        yy = PORT_SPECS["usb_hub"][key]["y"]
        out += [rect(245, yy - 9, 22, 18, "#91a1b1", "#617586", 2),
                rect(249, yy - 5, 15, 10, "#132c48", rx=1),
                line(267, yy, 330, yy, COLORS["usb"], 4)]
    return "".join(out)


def _lidar():
    out = [rect(43, 54, 150, 139, "#273543", "#0f1b27", 18, 2),
           _screw(56, 68, 4), _screw(178, 68, 4), _screw(56, 180, 4), _screw(178, 180, 4),
           circle(118, 116, 63, "#152332", "#455669", 2),
           circle(118, 116, 52, "#253446", "#6c7f91", 1.5),
           path("M67 108 Q117 80 169 108 L168 128 Q116 105 68 128 Z", "#091523", "#3b556a", 1),
           text(118, 88, "RPLIDAR", 11.5, "#e2e9ed", "middle", 700),
           text(118, 145, "C1", 24, "#d1dde5", "middle", 700),
           path("M51 52 Q104 18 176 49", stroke=COLORS["signal"], sw=2, stroke_dasharray="5 4"),
           path("M176 49 l-9 -1 l4 -7 Z", fill=COLORS["signal"]),
           _wire([(187, 154), (217, 159), (250, 159)], COLORS["ground"], 5),
           rect(218, 148, 23, 22, "#f2efe1", "#a8b3ba", 2),
           text(119, 214, "Cáp nguyên bộ tới adapter", 11, COLORS["muted"], "middle")]
    return "".join(out)


def _lidar_adapter():
    out = [rect(62, 42, 133, 73, "#256c54", "#104434", 4, 1.5),
           rect(53, 61, 27, 39, "#f1eddc", "#9faaa8", 2),
           _chip(111, 58, 39, 37, "USB", 4),
           rect(173, 64, 31, 30, "#b9c5ce", "#657b8a", 3),
           rect(186, 72, 19, 14, "#243c4e", rx=2),
           circle(91, 55, 3, "#5cdc86", "#cef3d8", 1),
           line(0, 80, 53, 80, COLORS["usb"], 5), line(204, 80, 250, 80, COLORS["usb"], 5),
           text(125, 139, "Nguồn + dữ liệu qua USB", 11, COLORS["muted"], "middle")]
    for yy in range(67, 99, 7):
        out.append(rect(58, yy, 13, 3, "#acb7bd", rx=.5))
    return "".join(out)


def _camera():
    out = [rect(55, 47, 116, 79, "#1b604e", "#0b3b31", 5, 2),
           _screw(64, 56, 3.5), _screw(161, 56, 3.5), _screw(64, 116, 3.5), _screw(161, 116, 3.5),
           rect(93, 43, 48, 85, "#26323e", "#13202d", 6),
           circle(117, 85, 31, "#233442", "#6d8497", 2),
           circle(117, 85, 23, "#080f18", "#4d6377", 2),
           circle(117, 85, 16, "#163c58", "#70a0b6", 1),
           circle(112, 80, 6, "#72a9c3"), circle(121, 90, 3, "#0a1625"),
           _wire([(0, 103), (35, 103), (55, 100)], COLORS["usb"], 4),
           text(111, 145, "Dạng module minh họa", 10.5, COLORS["muted"], "middle")]
    return "".join(out)


def _stock_board():
    out = [rect(44, 39, 163, 177, "#c7b494", "#776b58", 3, 2),
           _screw(55, 50, 4), _screw(196, 50, 4), _screw(55, 205, 4), _screw(196, 205, 4),
           text(125, 88, "XL1986RT", 17, "#f7f2e3", "middle", 700),
           rect(79, 100, 92, 38, "none", "#f3ebd9", 1, 1.5),
           text(125, 126, "2.4G", 26, "#f7f2e3", "middle"),
           text(125, 154, "E0-19", 12, "#f7f2e3", "middle"),
           circle(66, 160, 13, "#1e2b38", "#cdd7dd", 3),
           circle(183, 70, 13, "#1e2b38", "#cdd7dd", 3),
           _chip(161, 161, 31, 29, "SA8336", 4),
           rect(73, 175, 61, 23, "#f0e8d6", "#9b9587", 2),
           rect(69, 47, 48, 23, "#1c2937", "#0f1822", 2),
           path("M207 96 Q241 74 226 37", stroke="#525f68", sw=4),
           text(125, 237, "Hình theo ảnh · không nối trong bản mới", 10, COLORS["muted"], "middle")]
    return "".join(out)


_DRAWERS.update({
    "esp32": _esp32, "esc1060": _esc1060, "motor280": _motor280, "servo": _servo,
    "battery2s": _battery2s, "b3_charger": _b3_charger,
    "as5600": lambda: _angle_module("as5600"), "mt6701": lambda: _angle_module("mt6701"),
    "servo_supply": _servo_supply, "laptop": _laptop, "usb_hub": _usb_hub,
    "lidar": _lidar, "lidar_adapter": _lidar_adapter, "camera": _camera, "stock_board": _stock_board,
})


def component_catalog_svg():
    """Standalone component sheet, including provenance/pin-order caveats."""
    width, height = 1800, 1730
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           rect(0, 0, width, height, "#edf3f7"),
           text(55, 65, "AUTOPARK / THƯ VIỆN LINH KIỆN 2D", 34, weight=700),
           text(55, 101, "Hình dáng tham chiếu • điểm nối có tên • không theo tỉ lệ kích thước thật", 19, COLORS["muted"]),
           text(55, 133, "Chân ESP32 theo DevKitC-1; module cảm biến và nguồn chưa chốt thứ tự chân vật lý.", 17, COLORS["amber"], weight=700)]
    kinds = ["esp32", "esc1060", "motor280", "servo", "battery2s", "b3_charger", "servo_supply", "as5600",
             "mt6701", "laptop", "usb_hub", "lidar", "lidar_adapter", "camera", "stock_board"]
    for index, kind in enumerate(kinds):
        col, row = index % 4, index // 4
        x, y = 45 + col * 435, 170 + row * 365
        out.append(rect(x, y, 410, 345, "white", "#ccd9e2", 14, 1.5))
        out.append(text(x + 18, y + 27, f"{index + 1:02d}", 14, COLORS["muted"], weight=700))
        nw, nh = NATIVE_SIZES[kind]
        scale = min(365 / nw, 275 / nh)
        dw, dh = nw * scale, nh * scale
        out.append(draw_component(kind, x + (410 - dw) / 2, y + 40 + (280 - dh) / 2, dw, dh))
    out += [text(55, 1670, "Vòng nét đứt: chân/chức năng cần đối chiếu trên module thực. Không suy ra thứ tự chân chỉ từ màu dây.",
                 17, COLORS["amber"], weight=700),
            text(55, 1703, "Ảnh xe chỉ làm tham chiếu hình dạng; đồ mua mới được vẽ theo loại/model đã chọn, chưa thay cho kiểm tra phần cứng.",
                 16, COLORS["muted"]), "</svg>"]
    return "".join(out)
