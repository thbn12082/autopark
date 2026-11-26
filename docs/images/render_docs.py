r"""Rebuild the documentation visuals from the current app, scenes and vehicle.

From autopark/: .venv\Scripts\python.exe docs/images/render_docs.py
No device is opened. SVG previews go to an external temporary directory.
The raw evidence photograph is deliberately neither rewritten nor generated.
"""
from __future__ import annotations

import argparse
from html import escape
import json
import math
import os
from pathlib import Path
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))
OUT = Path(__file__).resolve().parent

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QFontDatabase, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from autopark.application.session import SessionState
from autopark.geometry.footprint import body_corners, swept_polygon
from autopark.ui.app import build_window

INK = "#173247"
MUTED = "#536d80"
BLUE = "#126ba3"
GREEN = "#087c65"
AMBER = "#ad6711"
RED = "#b13f4d"
PURPLE = "#7652aa"
LINE = "#a4b7c5"
BG = "#f4f8fb"


def capture(app):
    scenes = {}
    for slug in ("cua_hep", "lui_vao_khe"):
        w = build_window(PROJECT / "scenarios" / f"thao_tac_{slug}.json")
        w._timer.stop()
        w._pose_timer.stop()
        assert w.session.vehicle_link is None, "Documentation capture must use SIM only"
        w.resize(1440, 960)
        w.show()
        app.processEvents()
        result = w.plan(sync=True)
        assert result is not None and result.ok, result
        assert w.session.state == SessionState.READY
        app.processEvents()
        if slug == "cua_hep":
            assert w.grab().save(str(OUT / "giao-dien-cua-hep.png"))
        w.run()
        assert w.session.state == SessionState.RUNNING
        for _ in range(1500):
            if not w.session.simulating:
                break
            w.advance_by(0.1)
        w._poll_state_change()
        assert w.session.state == SessionState.COMPLETED, w.session.stop_reason
        assert w.session.world.state.speed == 0
        app.processEvents()
        if slug == "lui_vao_khe":
            assert w.grab().save(str(OUT / "giao-dien-lui-vao-khe.png"))
        scenes[slug] = (w.session.scenario, w.session.cfg, w.session.trajectory)
        traj = w.session.trajectory
        final = w.session.world.state.pose
        goal = w.session.scenario.goal.pose
        print(json.dumps({"scene": slug, "plan": result.status,
                          "terminal": w.session.state.value,
                          "path_m": round(traj.length, 5), "cusps": traj.n_cusps,
                          "directions": [traj.points[a].direction for a, _ in traj.segments],
                          "position_error_cm": round(final.distance_to(goal) * 100, 4),
                          "heading_error_deg": round(math.degrees(final.heading_error_to(goal)), 4),
                          "speed_mps": w.session.world.state.speed}, ensure_ascii=False), flush=True)
        w.close()
    return scenes


class SVG:
    def __init__(self, width, height, title, subtitle):
        self.width, self.height = width, height
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
                      f'<title>{escape(title)}</title><desc>{escape(subtitle)}</desc>',
                      '<defs>']
        for key, color in (("blue", BLUE), ("green", GREEN), ("red", RED), ("muted", MUTED), ("amber", AMBER), ("purple", PURPLE)):
            self.parts.append(f'<marker id="{key}" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L9,4.5 L0,9 Z" fill="{color}"/></marker>')
        self.parts += ['</defs>', f'<rect width="{width}" height="{height}" fill="{BG}"/>',
                       '<g font-family="Segoe UI">']
        self.text(44, 56, title, 32, INK, bold=True)
        self.text(44, 91, subtitle, 19, MUTED)

    def text(self, x, y, value, size=20, color=INK, bold=False, anchor="start"):
        self.parts.append(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" fill="{color}" font-weight="{600 if bold else 400}" text-anchor="{anchor}">{escape(str(value))}</text>')

    def rect(self, x, y, w, h, fill="white", stroke=LINE, radius=15, dash=None):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="1.8"{f" stroke-dasharray={chr(34)}{dash}{chr(34)}" if dash else ""}/>')

    def box(self, x, y, w, h, title, lines=(), color=BLUE, fill="white"):
        self.rect(x, y, w, h, fill, color)
        self.text(x + 20, y + 34, title, 22, color, True)
        for n, line in enumerate(lines):
            self.text(x + 20, y + 65 + n * 28, line, 19)

    def path(self, points, color=BLUE, width=2.4, arrow=False, dash=None, opacity=1):
        points = list(points)
        d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in points)
        key = {BLUE:"blue", GREEN:"green", RED:"red", MUTED:"muted", AMBER:"amber", PURPLE:"purple"}.get(color,"muted")
        self.parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round" opacity="{opacity}"{f" marker-end={chr(34)}url(#{key}){chr(34)}" if arrow else ""}{f" stroke-dasharray={chr(34)}{dash}{chr(34)}" if dash else ""}/>')

    def polygon(self, points, fill, stroke=LINE, width=1.5, opacity=1):
        ps = " ".join(f"{x:.2f},{y:.2f}" for x,y in points)
        self.parts.append(f'<polygon points="{ps}" fill="{fill}" stroke="{stroke}" stroke-width="{width}" opacity="{opacity}"/>')

    def circle(self,x,y,r,fill,stroke="none"):
        self.parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')

    def write(self, name):
        (OUT / name).write_text("\n".join(self.parts + ["</g></svg>"]), encoding="utf-8")


def user_flow():
    s = SVG(1440, 1100, "Một đích gần · một lượt thao tác", "Người lái chọn tư thế đích; phần mềm tìm đường, kiểm bám, thực hiện rồi dừng.")
    # Three columns: human/editor, accepted route, runtime and stopping.
    s.text(44, 142, "01   CHỌN & TÍNH", 18, MUTED, True)
    s.text(519, 142, "02   SẴN SÀNG", 18, MUTED, True)
    s.text(994, 142, "03   THỰC HIỆN & DỪNG", 18, MUTED, True)
    s.box(44, 166, 400, 116, "Chọn vị trí + hướng đích", ["Xe đã ở chỗ khó; lấy tư thế hiện tại.", "Sửa đích/vật cản → cần đường mới."])
    s.path([(244,282),(244,320)], arrow=True)
    s.box(44, 320, 400, 144, "Tính thao tác", ["Kiểm đầu bài và vùng thao tác.", "Tìm đường tiến/lùi; kiểm vùng quét.", "Chạy thử bộ bám trong mô phỏng."])
    s.path([(444,392),(519,392)], arrow=True)
    s.text(481,378,"Đạt",17,GREEN,anchor="middle")
    s.box(519, 320, 400, 116, "Sẵn sàng · đường được nhận", ["Đường còn khớp cảnh và tư thế.", "Chưa có lệnh chạy xe."], GREEN, "#edf8f3")
    s.path([(244,464),(244,510)], color=RED, arrow=True)
    s.text(258,491,"Không đạt",17,RED)
    s.box(44, 510, 400, 116, "Giữ xe đứng yên", ["Báo lý do; sửa đích/đầu bài", "rồi người dùng bấm tính lại."], RED, "#fff3f3")
    s.path([(44,568),(26,568),(26,224),(44,224)],color=RED,arrow=True)
    s.path([(719,436),(719,510)],color=GREEN,arrow=True)
    s.text(733,476,"Tùy chọn",17,MUTED)
    s.box(519, 510, 400, 116, "Xem trước", ["Phát mô phỏng đường đã nhận.", "Đóng xem trước → trở lại sẵn sàng."], GREEN)
    s.path([(919,568),(944,568),(944,378),(919,378)],color=GREEN,arrow=True)
    s.path([(919,350),(966,350),(966,224),(994,224)],color=BLUE,arrow=True)
    s.text(962,303,"Bấm",17,BLUE,anchor="middle")
    s.box(994,166,400,116,"Thực hiện",["Kiểm lại đường trước khi cho xe chạy.","Kiểm tư thế, đứng yên và kết nối."])
    s.path([(1194,282),(1194,320)],arrow=True)
    s.box(994,320,400,144,"Đang thực hiện tiến/lùi",["Đánh lái theo phản hồi.","Đổi chiều chỉ sau khi đứng yên.","Giám sát dữ liệu, vật cản, giới hạn."])
    s.path([(1194,464),(1194,510)],color=RED,arrow=True)
    s.text(1208,490,"Yêu cầu dừng / lỗi",17,RED)
    s.box(994,510,400,116,"Đang dừng",["Yêu cầu dừng; tốc độ mục tiêu về 0.","Chờ bằng chứng dừng; còn quãng phanh."],RED,"#fff3f3")
    s.path([(1394,392),(1416,392),(1416,720),(1194,720),(1194,758)],color=GREEN,arrow=True)
    s.text(1178,703,"Tới đích trong dung sai + đứng yên",17,GREEN,anchor="middle")
    s.path([(1194,626),(1194,670),(966,670),(966,812),(994,812)],color=RED,arrow=True)
    s.text(978,746,"Đã đứng yên",17,RED)
    s.box(994,758,400,116,"Lượt kết thúc · đã đứng yên",["Hoàn thành: tới đích đạt dung sai.","Hoặc dừng theo yêu cầu."],GREEN,"#edf8f3")
    s.path([(994,816),(919,816)],color=GREEN,arrow=True)
    s.box(519,758,400,116,"Chọn đích tiếp",["Người lái đánh giá, giữ tư thế vừa dừng.","Đặt đích mới và tính một lượt mới."],GREEN)
    s.path([(519,816),(244,816),(244,684),(10,684),(10,224),(44,224)],color=GREEN,arrow=True)
    s.box(44,936,1350,112,"Các nhánh từ chối không tự chạy lại",["Chưa đủ điều kiện chạy → chờ. Không xác nhận dừng hoặc có sự cố → báo lỗi; xử lý và kiểm lại điều kiện.","Dữ liệu phục hồi, kết nối lại hoặc xem trước xong đều không tự kích hoạt Thực hiện."],AMBER,"#fff8ec")
    s.write("luong-do-xe.svg")


def architecture():
    s = SVG(1440,1050,"Từ bằng chứng cảm biến tới lệnh chuyển động","Sơ đồ chức năng của phần mềm. AI bổ sung vật cản; bộ bám đường mới tạo tốc độ và góc lái.")
    s.rect(32,126,1376,580,"#ffffff","#c5d7e3",20)
    s.text(52,158,"TRÊN MÁY TÍNH",17,MUTED,True)
    s.box(52,185,290,116,"Nguồn cảm biến",["LiDAR, ảnh và phản hồi.", "Có thời gian và độ hợp lệ."])
    s.box(52,346,290,116,"Thời gian và tư thế",["Neo hệ; kiểm tuổi dữ liệu.","Bản đồ + đo chuyển động."])
    s.path([(197,301),(197,346)],arrow=True)
    s.box(52,507,290,144,"Camera và AI",["Chiếu từ ảnh xuống sàn.","Trống / vật / chưa rõ.","Không phát lệnh lái."],PURPLE,"#f5f0fa")
    s.path([(52,244),(42,244),(42,580),(52,580)],color=MUTED,arrow=True)
    s.box(414,346,290,116,"Bản đồ / hợp nhất",["Vật LiDAR + AI + người dùng.","Giữ vật LiDAR / người dùng."])
    s.path([(342,404),(414,404)],arrow=True)
    s.path([(342,579),(376,579),(376,435),(414,435)],arrow=True)
    s.box(414,185,290,116,"Người lái chọn đích gần",["Vị trí + hướng; cấu hình xe.","Giới hạn cho một lượt."])
    s.box(776,185,290,144,"Tìm đường và thử bám",["Đường tiến/lùi + vùng quét.","Kiểm giới hạn; thử bám.","Đạt → sẵn sàng, chờ chạy."])
    s.path([(704,243),(776,243)],arrow=True)
    s.path([(704,404),(741,404),(741,285),(776,285)],arrow=True)
    s.box(776,383,290,116,"Bộ bám đường",["Tốc độ + góc lái mục tiêu.","Dừng trước khi đổi chiều."])
    s.path([(921,329),(921,383)],arrow=True)
    s.text(934,360,"Khi được phép chạy",17,MUTED)
    s.path([(342,372),(364,372),(364,480),(757,480),(757,443),(776,443)],color=GREEN,arrow=True)
    s.text(420,502,"Phản hồi tư thế / chuyển động",17,GREEN)
    s.box(1124,185,264,314,"Quản lý và giám sát",["Kiểm điều kiện chạy.","Tuổi / lỗi dữ liệu.","Va chạm, phạm vi.","Dự phòng quãng phanh", "và góc thân xe quét.","Yêu cầu dừng ngay.","Ghi lại diễn biến."],RED,"#fff3f3")
    s.path([(1066,422),(1124,422)],color=RED,arrow=True,dash="7 5")
    s.box(776,558,612,116,"Đầu ra có kiểm soát",["Mô phỏng nhận mục tiêu; thiết bị nhận lệnh có hạn.","Phản hồi quay lại bộ bám; sự cố chuyển sang nhánh dừng."],GREEN,"#edf8f3")
    s.path([(921,499),(921,558)],color=GREEN,arrow=True)
    s.path([(1256,499),(1256,558)],color=RED,arrow=True)
    s.path([(776,616),(728,616),(728,686),(20,686),(20,404),(52,404)],color=GREEN,arrow=True,dash="7 5")
    s.text(360,673,"Phản hồi / đo mô phỏng hoặc thiết bị",17,GREEN)
    s.path([(980,674),(980,736),(264,736),(264,770)],color=GREEN,arrow=True)
    s.path([(1082,674),(1082,745),(719,745),(719,770)],color=GREEN,arrow=True)
    s.path([(1190,674),(1190,770)],color=AMBER,arrow=True,dash="7 5")
    s.box(44,770,420,162,"Mô phỏng",["Mô hình động học + phản hồi giả.","Ảnh minh họa dùng nhánh này.","Không mở cổng thiết bị."],GREEN,"#edf8f3")
    s.box(509,770,420,162,"Bo điều khiển ảo",["Kiểm giao thức và máy trạng thái.","Xe trên máy tính vẫn là mô phỏng.","Không phải phép đo cơ cấu thật."],BLUE)
    s.box(974,770,420,162,"Bo + xe thật · còn bị chặn",["Chưa có nguồn tư thế sống được nhận.","Còn thiếu phản hồi, đo xe, hiệu chuẩn.","Chưa chạy thao tác trên xe thật."],AMBER,"#fff8ec")
    s.text(44,990,"Mũi tên xanh: dữ liệu / điều khiển / phản hồi. Đỏ: giám sát dừng. Nét đứt: vòng phản hồi hoặc nhánh chưa đủ điều kiện.",18,MUTED)
    s.write("toan-canh.svg")


def stopping():
    s=SVG(1440,920,"Yêu cầu dừng ≠ đã đứng yên","Dừng là một quá trình có phản hồi; dữ liệu trở lại không tự nối tiếp lượt đang chạy.")
    s.box(44,145,408,172,"Phát hiện khi đang chạy",["Người dùng bấm Dừng; vật cản mới.","Tư thế lỗi, thiếu hoặc quá cũ.","Mất phản hồi hoặc dữ liệu bắt buộc.","Sắp vượt đường / vùng có xét phanh."],RED,"#fff3f3")
    s.box(516,145,408,172,"Chốt yêu cầu → đang dừng",["Gửi yêu cầu dừng ngay khi tác động.","Mục tiêu tốc độ về 0; còn quãng phanh.","Không chờ nhịp điều khiển 20 ms.","Lưu nguyên nhân và nguồn sự kiện."],RED,"#fff3f3")
    s.path([(452,231),(516,231)],color=RED,arrow=True)
    s.box(988,145,408,172,"Lỗi giao tiếp hoặc ghi nhận",["Giữ trạng thái đang dừng; tiếp tục thử.","Thử lại thao tác còn cần thực hiện.","Không coi thất bại ghi/gửi là", "bằng chứng xe đã dừng."],AMBER,"#fff8ec")
    s.path([(924,206),(988,206)],color=AMBER,arrow=True)
    s.path([(988,279),(952,279),(952,344),(720,344),(720,317)],color=AMBER,arrow=True)
    s.box(516,404,408,144,"Theo dõi phản hồi",["Mô phỏng: tốc độ về 0.","Thiết bị: phản hồi dừng hợp lệ", "và dữ liệu phản hồi còn mới."])
    s.path([(720,317),(720,404)],color=RED,arrow=True)
    s.box(44,404,408,144,"Chưa xác nhận / quá hạn",["Tiếp tục kiểm khi còn chờ dừng.","Quá hạn / sự cố không khép được →", "báo lỗi; cần người xử lý và kiểm lại."],RED)
    s.path([(516,476),(452,476)],color=RED,arrow=True)
    s.path([(720,548),(720,606)],color=GREEN,arrow=True)
    s.text(737,583,"Đủ bằng chứng",18,GREEN)
    s.box(516,606,408,116,"Đã dừng",["Giữ tư thế dừng để đánh giá lại.","Người lái chọn đích tiếp / tính lại."],GREEN,"#edf8f3")
    s.box(988,404,408,144,"Nguồn tư thế lỗi",["Giữ tư thế hữu hạn cuối cho trạng thái.","Chốt lỗi và yêu cầu dừng.","Mẫu tốt trở lại không tự bỏ chốt."],PURPLE,"#f5f0fa")
    s.rect(44,777,1352,95,"#eaf2f8","#c6d8e4")
    s.text(64,813,"Dự phòng dừng của phần mềm",22,BLUE,True)
    s.text(64,846,"Tính thêm bước có thể tăng tốc kế tiếp + quãng phanh + chuyển động góc thân xe. Các tham số phải đo lại trên xe thật.",19)
    s.write("dung-va-phan-hoi.svg")


def vehicle_geometry(cfg):
    s=SVG(1440,790,"Thân xe và hệ tọa độ dùng trong mô hình","Kích thước và giới hạn lấy từ cấu hình mô phỏng; còn giả định, chưa đo trên xe thật.")
    # True relative dimensions, +x to the right and +y upwards.
    scale=2100
    rear_x, cy = 280,390
    x0=rear_x-cfg.rear_overhang*scale
    x1=rear_x+(cfg.wheelbase+cfg.front_overhang)*scale
    front_x=rear_x+cfg.wheelbase*scale
    y0=cy-cfg.width/2*scale
    y1=cy+cfg.width/2*scale
    s.rect(x0,y0,x1-x0,y1-y0,"#dcebf4",BLUE,24)
    for axle in (rear_x,front_x):
        s.path([(axle,y0+16),(axle,y1-16)],color=MUTED,width=3)
        for wy in (y0,y1):
            s.rect(axle-35,wy-10,70,20,INK,INK,5)
    s.circle(rear_x,cy,7,BLUE)
    s.path([(rear_x,cy),(875,cy)],color=BLUE,width=3,arrow=True)
    s.text(867,375,"+x · trước",20,BLUE,True,anchor="end")
    s.path([(rear_x,cy),(rear_x,182)],color=GREEN,width=3,arrow=True)
    s.text(rear_x+15,196,"+y · trái",20,GREEN,True)
    s.text(rear_x-18,cy+36,"O",24,BLUE,True,anchor="end")
    s.path([(rear_x+54,cy),(rear_x+51,cy-20),(rear_x+38,cy-38),(rear_x+18,cy-51)],color=GREEN,arrow=True)
    s.text(rear_x+65,cy-45,"Góc +",19,GREEN)
    def dim(xa,xb,y,text):
        s.path([(xa,y),(xb,y)],color=MUTED,width=1.6)
        for xx in (xa,xb):s.path([(xx,y-9),(xx,y+9)],color=MUTED,width=1.6)
        s.text((xa+xb)/2,y-14,text,19,MUTED,anchor="middle")
    dim(x0,rear_x,595,f"Nhô sau {cfg.rear_overhang*100:g} cm")
    dim(rear_x,front_x,595,f"Cơ sở {cfg.wheelbase*100:g} cm")
    dim(front_x,x1,595,f"Nhô trước {cfg.front_overhang*100:g} cm")
    dim(x0,x1,659,f"Dài toàn thân {cfg.length*100:g} cm")
    s.path([(110,y0),(110,y1)],color=MUTED,width=1.6)
    s.path([(101,y0),(119,y0)],color=MUTED)
    s.path([(101,y1),(119,y1)],color=MUTED)
    s.text(91,cy-8,"Rộng",18,MUTED,anchor="end")
    s.text(91,cy+21,f"{cfg.width*100:g} cm",18,MUTED,anchor="end")
    s.box(965,190,429,172,"Vị trí và hướng xe",["O ở tâm trục sau; +z hướng lên.","Góc hướng dương: quay sang trái.","Đích gồm cả vị trí và hướng.","Vùng quét xét toàn thân và phần nhô."])
    s.box(965,410,429,172,"Giới hạn mẫu có thể chỉnh",[f"Góc lái tương đương: ±{math.degrees(cfg.max_steer):g}°.",f"Tốc độ tối đa: {cfg.max_speed:.2f} m/s.","Đo lại hình học, lái, trễ và phanh", "trước khi dùng cấu hình cho xe thật."],AMBER,"#fff8ec")
    s.text(44,742,"Thân xe vẽ đúng tỉ lệ từ cấu hình; bánh và cung góc hướng chỉ là ký hiệu. Không phải bản vẽ cơ khí hoặc vị trí gá cảm biến.",19,MUTED)
    s.write("he-truc-va-kich-thuoc.svg")


def swept_geometry(scene,cfg,traj):
    s=SVG(1440,1010,"Cua hẹp: đường tâm chưa mô tả hết chỗ xe chiếm","Vùng quét dựng từ đường đã tính trong cảnh cua 90 độ; chưa phải vệt đo xe thật.")
    # Exact map coordinates with an enlarged view of the corner.
    left,top,size=64,150,740
    xmin,ymin,xmax,ymax=.05,.25,1.20,1.40
    scale=size/(xmax-xmin)
    def xy(p): return left+(p[0]-xmin)*scale, top+(ymax-p[1])*scale
    s.rect(left,top,size,size,"white","#c1d2dd",0)
    for i in range(2,12,2):
        x=i/10
        if xmin<x<xmax:s.path([xy((x,ymin)),xy((x,ymax))],color="#e5edf3",width=1)
        if ymin<x<ymax:s.path([xy((xmin,x)),xy((xmax,x))],color="#e5edf3",width=1)
    # Clip numerically: the Qt SVG preview renderer does not implement clipPath.
    viewbox=box(xmin,ymin,xmax,ymax)
    for o in scene.obstacles:
        poly=Polygon(o.corners()).intersection(viewbox)
        if not poly.is_empty:s.polygon([xy(p) for p in poly.exterior.coords],"#d0d9df","#7c919f",1.8)
    sweep=unary_union([swept_polygon(cfg,a.pose,b.pose) for a,b in zip(traj.points,traj.points[1:])])
    for poly in getattr(sweep,"geoms",[sweep]):s.polygon([xy(p) for p in poly.exterior.coords],"#b8ddd9",GREEN,1,0.62)
    # Draw actual paths followed by all four corners, not invented clearance envelopes.
    for corner,color in ((0,PURPLE),(1,PURPLE),(2,AMBER),(3,AMBER)):
        s.path([xy(body_corners(cfg,p.pose)[corner]) for p in traj.points],color=color,width=1.8,opacity=.72)
    indices=[0,len(traj.points)//2,len(traj.points)-1]
    for n,index in enumerate(indices):
        p=traj.points[index].pose
        s.polygon([xy(q) for q in body_corners(cfg,p)],"#eaf4fa",BLUE,2,.48)
        px,py=xy((p.x,p.y))
        s.circle(px,py,5,BLUE)
        s.path([(px,py),xy(p.to_world(.15,0))],color=BLUE,width=2.5,arrow=True)
    for a,b in traj.segments:
        seg=traj.points[a:b+1]
        color=BLUE if seg[0].direction==1 else RED
        s.path([xy((p.pose.x,p.pose.y)) for p in seg],color=color,width=4.2,dash="7 5" if seg[0].direction==-1 else None)
        if len(seg)>5:
            n=len(seg)//2
            s.path([xy((seg[n-2].pose.x,seg[n-2].pose.y)),xy((seg[n+2].pose.x,seg[n+2].pose.y))],color=color,width=3,arrow=True)
    # Snapshot labels go last so the trajectory cannot obscure their digits.
    for n,index in enumerate(indices):
        p=traj.points[index].pose
        px,py=xy((p.x,p.y))
        s.circle(px-23,py+28,16,BLUE)
        s.text(px-23,py+34,str(n+1),18,"white",True,anchor="middle")
    s.text(200,205,"Góc tường trong",19,MUTED,True)
    s.text(721,303,"Tường",18,MUTED,True,anchor="middle")
    s.text(721,330,"ngoài",18,MUTED,True,anchor="middle")
    s.text(290,875,"Tường dưới",18,MUTED,True)
    bx=left+60
    s.path([(bx,916),(bx+.20*scale,916)],color=INK,width=4)
    s.text(bx+.10*scale,904,"20 cm",18,MUTED,anchor="middle")
    s.box(856,150,538,144,"1 → 2 → 3 · các tư thế trên đường",["Chấm xanh: tâm trục sau (x, y).", "Mũi tên trên thân: hướng đầu xe.","Vùng quét gồm cả đầu, đuôi và hai sườn."],BLUE)
    s.rect(856,325,538,255,"white",LINE)
    s.text(876,360,"Chú giải hình học",22,INK,True)
    s.path([(878,394),(936,394)],color=BLUE,width=4)
    s.text(953,400,"Đường tâm trục sau · tiến",19)
    s.path([(878,429),(936,429)],color=RED,width=4,dash="7 5")
    s.text(953,435,"Đường tâm trục sau · lùi",19)
    s.rect(878,453,57,21,"#b8ddd9",GREEN,0)
    s.text(953,470,"Vùng thân xe quét giữa mẫu",19)
    s.path([(878,505),(936,505)],color=AMBER,width=2.5)
    s.text(953,511,"Hai góc đầu xe",19)
    s.path([(878,544),(936,544)],color=PURPLE,width=2.5)
    s.text(953,550,"Hai góc đuôi xe",19)
    s.box(856,591,538,144,"Khoảng hở phải xét toàn thân",["Các góc đầu và đuôi đi theo cung khác", "đường tâm; kiểm cả chuyển động giữa mẫu.","Dải màu là vùng quét hình học của đường."],GREEN,"#edf8f3")
    s.box(856,769,538,121,"Chưa phải biên an toàn của xe thật",["Dự phòng dừng được kiểm riêng khi chạy.","Hình này không cộng sai số cảm biến/phanh."],AMBER,"#fff8ec")
    s.text(64,936,f"Xe giả định: dài {cfg.length*100:g} cm · rộng {cfg.width*100:g} cm · cơ sở {cfg.wheelbase*100:g} cm · lái ±{math.degrees(cfg.max_steer):g}°.",20,INK,True)
    s.text(64,972,f"Đường được nhận: {traj.length:.3f} m · {traj.n_cusps} lần đổi chiều. Hình trích vùng cua; không biểu diễn toàn biên thao tác.",19,MUTED)
    s.write("vung-quet-cua-hep.svg")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-dir",type=Path,default=Path(tempfile.gettempdir()) / "autopark-doc-previews")
    args=parser.parse_args()
    app=QApplication.instance() or QApplication([])
    for name in ("segoeui.ttf","segoeuib.ttf","segoeuil.ttf","consola.ttf"):
        font=Path(os.environ.get("WINDIR","C:/Windows"))/"Fonts"/name
        if font.exists():QFontDatabase.addApplicationFont(str(font))
    scenes=capture(app)
    user_flow()
    architecture()
    stopping()
    scene,cfg,traj=scenes["cua_hep"]
    vehicle_geometry(cfg)
    swept_geometry(scene,cfg,traj)
    args.preview_dir.mkdir(parents=True,exist_ok=True)
    for source in OUT.glob("*.svg"):
        renderer=QSvgRenderer(str(source))
        assert renderer.isValid(),source
        size=renderer.defaultSize()
        image=QImage(size,QImage.Format.Format_ARGB32)
        image.fill(QColor("white"))
        painter=QPainter(image)
        renderer.render(painter,QRectF(0,0,size.width(),size.height()))
        painter.end()
        dest=args.preview_dir / f"{source.stem}.png"
        assert image.save(str(dest))
        print(dest,flush=True)


if __name__ == "__main__":
    main()
