# Kiểm kê phần cứng — giai đoạn 1

Tài liệu này liệt kê phần cứng đã nhận cho giai đoạn 1 (RPLIDAR C1, bốn camera USB, hub UGREEN), những gì máy đọc được
từ chúng và các số đo chính. Chỉ ghi những gì đã cầm trên tay hoặc máy đọc được; ô ghi "chưa ghi" là chưa kiểm, không
phải giả định. Số đo chi tiết nằm ở [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md),
[GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) và [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md).

## Hiện trạng

Tính đến 30/09/2026, theo các lần kiểm kê: 22/09 (LiDAR), 23/09 (camera và hub), 24–25/09 (kiểm lại LiDAR, khung bị cắt
ở 720p, mã hiệu chuẩn camera, vai trò hai máy, danh sách chưa nhận), 29/09 (máy bàn mới) và 30/09 (firmware chạy trong bo
ảo QEMU).

- **RPLIDAR C1:** nhận 22/09/2026, máy đọc được thông tin và sức khỏe; trên máy bàn hiện tại ở COM3. Đo trên bàn ≈ 10 Hz,
  ≈ 510 tia/vòng sau khi mô-tơ ổn định. Sai số khoảng cách so với thước chưa đo.
- **Bốn camera + hub:** nhận 23/09/2026. Camera không có serial nên danh tính là cổng hub. Bốn camera qua hub chỉ dùng
  được ở 640×480, và ở đó cổng 1 vẫn có đợt khung hỏng; ở 720p/1080p nhiều khung bị cắt khi chạy chung.
- **Chưa nhận:** ESP32-S3, IMU, ToF, encoder, AS5600, xe MN300, phần nguồn và E-stop (mục cuối).
- **Còn thiếu trong kiểm kê:** ảnh bộ thực giao, model in trên nhãn, cổng USB của LiDAR, dây camera, dòng điện thật, góc
  nhìn thực của camera.

## Máy tính

- **Máy bàn** i9-14900 + RTX 4000 Ada 20 GB là máy phát triển chính. Từ 29/09/2026 máy bàn là Dell Precision 3680 cùng
  cấu hình ([chuyển máy](CHUYEN_MAY_BAN.md)). Mọi số đo trong tệp này là trên máy bàn trước, dùng tới 25/09/2026, trừ chỗ
  ghi ngày 29/09/2026.
- **Laptop** i7-12700H + RTX 3050 Ti (4 GB VRAM) là máy mang đi nộp và trình diễn đồ án (người dùng xác nhận
  24/09/2026). Laptop đã chạy giai đoạn 0; LiDAR và camera chưa thử trên laptop.

Nguồn: [GIAI_DOAN_0.md](GIAI_DOAN_0.md), [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md).

## RPLIDAR C1 (đợt mua 1)

| Mục | Giá trị | Nguồn |
|---|---|---|
| Thiết bị tự báo | model 0x41 (C1), firmware 1.2, phần cứng 18 | lệnh GET_INFO qua `python -m autopark.lidar.rplidar_c1 info --port COM4` |
| Serial | `f57ffc8bc6e598d1b59598f976dd5762` | GET_INFO |
| Sức khỏe | OK (0), mã lỗi 0 (22/09; kiểm lại 24/09/2026, k01: vẫn OK, cùng serial) | GET_HEALTH |
| Chế độ quét thiết bị công bố | 0 "Standard": 200 µs/mẫu, xa nhất 16 m, kiểu trả lời 0x81 — **đang dùng**; 1 "DenseBoost": 200 µs/mẫu, 40 m, 0x85 — thiết bị gọi là typical, **chưa dùng** | GET_LIDAR_CONF |
| Adapter USB | CP2102N USB to UART Bridge, VID 10C4 / PID EA60 | Device Manager |
| Driver Windows, máy bàn tới 25/09/2026 | Silicon Labs CP210x Universal Windows Driver 11.6.0.420 (Silicon Laboratories, ngày driver 14/08/2026), cổng **COM4** | Device Manager; người dùng cài ngày 22/09/2026 |
| Driver Windows, máy bàn từ 29/09/2026 | CP210x 11.2.0.167 (Windows Update), cổng **COM3**, cùng C1 và cùng serial ([chuyển máy](CHUYEN_MAY_BAN.md)) | Device Manager; cài ngày 29/09/2026 |
| UART | 460800 bps, 8N1, TTL 3,3 V | datasheet C1M1 rev 1.1; giao tiếp thực tế ở 460800 |
| Nguồn | 5 V qua USB máy tính; datasheet: khởi động 800 mA, làm việc 230 (max 260) mA ở 10 Hz. Dòng thật **chưa đo** | datasheet C1M1 rev 1.1 |
| Đầu nối | XH2.54-5P (VCC, TX, RX, GND, MOTOCTL) từ LiDAR tới adapter; adapter tới máy bằng cáp USB | datasheet, sổ tay C1 |
| Model in trên nhãn / hộp | chưa ghi (datasheet mô tả model C1M1) | |
| Ảnh bộ thực giao | chưa chụp | |
| Cổng USB của máy đang dùng | chưa ghi (nên cắm thẳng cổng USB 3, không qua hub không nguồn) | |
| Máy tính | xem mục "Máy tính" ở trên | |

Bảng tải nháp của cả hệ, thêm tối 24/09/2026, có dòng P1 là LiDAR: [GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md)
mục 1.

**Số đo trên bàn** (chi tiết ở [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 3, 3b):

- **22/09/2026, phiên p07:** chế độ Standard, chưa làm nóng, không đặt vật
  ([bản ghi](evidence/lidar/p07_nen_phong.json), [phân tích](evidence/lidar/p07_nen_phong.analysis.json)). Kết quả:
  10,09 Hz; trung vị 508 tia/vòng (396–536); ≈5,1 kHz mẫu; 0 byte lệch trong 91.507 node; 34,6 % tia không phản hồi ở
  vị trí đặt; phản hồi xa nhất 14,6 m, vượt 12 m của datasheet (datasheet ghi "chỉ để tham khảo"); mô-tơ mất ≈2,2 s từ
  lệnh SCAN tới node đầu.
- **24/09/2026, phiên k01 kiểm lại:** làm nóng 3 s, ghi 15 s, không đặt vật, LiDAR đã dời chỗ
  (`runs/lidar_bench/20260924_kiem/k01_kiem_suc_khoe.json`, git-ignored; bản sao trong git:
  [k01_kiem_suc_khoe.json](evidence/lidar/k01_kiem_suc_khoe.json)). GET_INFO trả cùng model 0x41, firmware 1.2, phần
  cứng 18 và cùng serial; GET_HEALTH vẫn OK. Có 0 lỗi đọc, 0 byte lệch, 0 vòng bị bỏ.
- **Khi mô-tơ đã ổn định:** bỏ 3 s đầu mỗi bản ghi thì cả hai ngày đều ≈ 10,0 Hz và trung bình ≈ 510 tia/vòng
  (504–516). Con số 10,09 Hz và khoảng 396–536 của p07 có lẫn phần khởi động; đỉnh 552 của k01 cũng rơi vào lúc mô-tơ
  mới chạy. Mới có ba lần khởi động được ghi.
- **Sai số khoảng cách so với thước: chưa đo.** Cần phiên đặt hộp ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 6).

## Bốn camera USB 130° (theo nhà bán, chưa đo) và hub UGREEN (nhận 23/09/2026)

| Mục | Giá trị | Nguồn |
|---|---|---|
| Camera | 4 × "HD Camera", VID 1BCF (Sunplus Innovation) PID 0B09, UVC composite, **không có serial** → danh tính = cổng hub | Device Manager, DirectShow |
| Mode công bố | MJPG 640×480 / 1280×720 / 1920×1080 đều 30 fps; YUY2 640×480 30, 1280×720 10, 1920×1080 5 fps ([camera_modes.csv](camera_modes.csv)) | `python -m autopark.video.camera_bench modes` |
| FPS thật đo được | ≈ 24 fps với phơi sáng tự động trong phòng; 29,3 fps khi ép phơi sáng. Một số phiên có camera ≈ 29 khung/s ở phơi sáng tự động, không cố định một cổng (chi tiết dưới bảng) | xem chi tiết dưới bảng |
| Bốn luồng đồng thời | 640×480: 4 × 23,9 fps, 0 khung cũ; 720p và 1080p: camera cổng 4 (và cổng 3 ở 1080p) rớt khung. Chưa kiểm khung bị cắt (chi tiết dưới bảng) | [GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) mục 4.2 |
| Khung MJPEG bị cắt khi chạy chung | có, khi ba–bốn camera chạy chung qua hub ở 720p/1080p; ở 640×480 phần lớn thời gian nguyên vẹn. Mặc định vẫn 640×480 (chi tiết dưới bảng) | [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 2, mục 10, [GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) mục 4.6 |
| Hub | UGREEN 4 cổng, chip Genesys Logic: 05E3:0626 "USB3.1 Hub" và 05E3:0610 "USB2.1 Hub"; cả bốn camera ở nhánh USB 2.0, cổng hub 1–4 | `camera_bench list` → `usb_topology.json` khóa `hubs` |
| Cổng gốc của hub | máy bàn tới 25/09/2026: 24 (0626) và 5 (0610) ([usb_topology.md](usb_topology.md)); máy bàn từ 29/09/2026: 18 (0626) và 8, HS08 (0610) ([usb_topology.json](evidence/chuyen_may_20260929/may_moi/usb_topology.json)) | `camera_bench list` → `usb_topology.json` khóa `hubs` |
| Nguồn hub | hub có cổng nguồn ngoài (theo người dùng); **bus-powered trong mọi phiên ngày 23/09**, chưa thử adapter; dòng camera **chưa đo** | |
| Rút/cắm lại camera | hai lần ngày 23/09; index và InstanceId giữ nguyên (chi tiết dưới bảng) | `usb_topology_replug1/2.json`, [GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) mục 4.5 |
| Khởi động lại máy | 12:35 ngày 23/09: InstanceId theo cổng giữ nguyên, index OpenCV đổi (cổng 2 ↔ cổng 4) → chọn camera theo cổng, không theo index | `usb_topology_20260923_after_reboot.json` |
| Góc nhìn thực, nhãn/hộp, độ nét trong vùng làm việc | **chưa đo** (camera mới nằm trên bàn) | |
| Lớp phim bảo vệ ống kính | các phiên m01–m13 đo khi còn phim; lột lúc ≈ 11:15 ngày 23/09; phiên n01–n06 sau khi lột: nhịp khung/FPS không đổi, ảnh sáng hơn ≈ 5 lần ở cùng phơi sáng thủ công | [GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) mục 4.4 |
| `camera_01_calibration.yaml` | chưa có (chưa in bảng hiệu chuẩn, chưa chụp). Mã đã có từ 24/09: tệp ra sẽ là `calibration/cam_p<cổng>.json`, mới kiểm trên ảnh tổng hợp | [HIEU_CHUAN_CAMERA.md](HIEU_CHUAN_CAMERA.md) |
| Dây camera (chiều dài, loại) | **chưa ghi** — kế hoạch yêu cầu thử dây ngắn trước rồi mới cáp kéo dài | |
| Laptop nộp đồ án (RTX 3050 Ti) | chưa thử camera trên laptop; xem mục "Máy tính" | |

Bảng tải nháp của cả hệ (thêm tối 24/09/2026) có dòng P3, P4 cho hub và camera, đều chưa đo / cần tra:
[GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md) mục 1.

### FPS thật đo được

- **Một camera, phơi sáng tự động trong phòng:** ≈ 24 fps. Đo ở 720p và 1080p một camera (m01, m03, m08, m13); 640×480
  chỉ đo trong phiên bốn camera m04. Nhịp khung không đều: trung bình 41,9 ms, trung vị 47 ms.
- **Ép phơi sáng −5…−8:** 29,3 fps, ảnh tối (m02/m11).
- **Camera ≈ 29 khung/s ở phơi sáng tự động** (ghi tối 24/09/2026). Json của các phiên này ghi `exposure: null`, tức
  chương trình không đặt phơi sáng. Camera nhanh **không cố định một cổng**:
  - **Cổng 3:** cả bảy phiên s01–s07 (23/09, xong ≈ 13:59–14:16) đạt 29,0–29,3 khung/s ở cả 480p, 720p và 1080p; s05
    640×480 cùng LiDAR + AI đạt 29,3. t01, t02 (xong ≈ 14:36–14:38, 720p) đạt 28,9 / 29,0. Từ t03 (xong ≈ 14:40) cổng 3
    về 23,85.
  - **Cổng 1:** t05 (xong ≈ 14:42, 640×480, cùng LiDAR + AI, 29,3); m02 của lệnh đo máy mới trên bàn thử
    (`runs/may_moi_20260924_may_ban/`, 24/09 15:25, 720p, chỉ camera, 29,3 khung tốt/s); o01 (tối 24/09, 720p, chỉ
    camera, 29,27 khung tốt/s). Ở ba phiên này ba camera kia ≈ 23,8–23,9.
  - Ở s04 cả cổng 1 lẫn cổng 3 nhanh: cổng 1 trung bình 27,6, 51/60 giây ≥ 27 khung/s. Ở s07 cổng 4 có 91/598 giây ≥ 27
    (trung bình 25,2).
  - Ở loạt s và t01, t02, cổng 2 ≈ 23,85; cổng 1 và 4 thấp hơn và dao động.
  - r01/r02 (23/09, 720p) cho cổng 1 28,4 / 29,2 khung tốt/s, nhưng tệp không ghi chế độ phơi sáng. Ở một số phiên khác
    cổng 1 lại ≈ 23,5–23,9 khung tốt/s (r07, u01, m01, o02).
  - Vì sao: **chưa rõ**; m02 và o01 chạy lúc camera nhìn chỗ tối. Không mặc định cổng nào là camera nhanh.

Cách đọc các số trên:

- Số của loạt s và t đếm cả khung có thể bị cắt, vì đo trước khi có bộ dò. Ở 720p cổng 3 từng bị cắt 0–70 % khung khi
  bốn camera chạy chung, ở 1080p 100 % ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 2.3).
- FPS trung bình của loạt s là số khung / thời lượng, nên không dính lỗi đồng hồ 15,6 ms ở mục 6 của tài liệu đó; số
  giây ≥ 27 đọc từ chuỗi theo giây trong cùng tệp.
- Tối 24/09/2026 đã quét 37 tệp `*.rig.json` dưới `runs/`: chỉ các phiên nêu trên có camera trung bình ≥ 26 khung/s;
  loạt r không có tệp dạng này. Ngày 25/09/2026 quét lại được 39 tệp; ngoài các phiên nêu trên vẫn không tệp nào có
  camera trung bình ≥ 26 khung/s, kể cả hai tệp của lệnh `may_moi` tối 24/09 (`runs/may_moi_20260924_toi/`, bốn camera
  23,83–23,87 khung/s ở 480p và 720p).
- Phiên m02 của lệnh đo máy mới khác phiên m02 phơi sáng thủ công −6 ở ý thứ hai (cùng tên, khác thư mục).

Nguồn: [GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) mục 4.1; [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 2.3
(r01, r02, r07), mục 5 (t01, t02, t05), mục 10.1 và 10.3 (m02, o01); `runs/rig_bench/20260923/s01…s07*.rig.json`
(git-ignore; GIAI_DOAN_2_BAN_THU.md mục 6 không có bảng FPS của loạt s);
[cho_nhip_rieng_ghi_phat_lai_20260924.json](evidence/rig/cho_nhip_rieng_ghi_phat_lai_20260924.json).

### Bốn luồng đồng thời

- 640×480 (m04, 30 s): 4 × 23,9 fps, 0 khung cũ.
- 720p (m05, 60 s): 4 × 23,8 fps, camera cổng 4 rớt 4 khung. Ba phiên 10 s (m12a–c): camera cổng 4 còn 18,6 / 22,3 /
  3,9 fps, ba chiếc kia không rớt.
- 1080p (m06, m09, m10): camera cổng 4 còn 22,5 / 13,1 / 18,7 fps, cổng 3 còn 22,3–22,7. Ba camera 1080p (m07): cổng 3
  còn 20,0 fps.

Các số này chưa kiểm khung bị cắt. Nguồn: [GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) mục 4.2.

### Khung MJPEG bị cắt khi chạy chung

Khung bị cắt thiếu dữ liệu ở đáy, và bộ giải mã tô phần đó bằng vân xám. Chạy một mình thì không bị. Các phiên dưới đây
chạy chiều 23/09, chỉ đọc camera, mỗi phiên 15 s, camera nhìn xuống thảm hoa văn dày:

- **Bốn camera ở 720p:** **hai–ba** camera bị cắt phần lớn khung. r04: cổng 1, 4 ≈ 99–100 %, cổng 3 28 %; r08: cổng 1,
  3, 4 = 100 / 70 / 81 %; r11: cổng 1, 4 = 100 %.
- **Bốn camera ở 1080p** (r09): ba camera bị cắt phần lớn khung.
- **Ba camera ở 720p:** chỉ **một** camera bị cắt phần lớn khung. r03 (cổng 1 + 2 + 3): cổng 1 97 %, cổng 3 9 %; r05
  (cổng 2 + 3 + 4): cổng 4 67 %, cổng 3 1 %.
- **Hai camera ở 720p** (r02): cổng 1 1 %.
- Cổng 2 chưa lần nào bị cắt ở 720p. Ba camera ở 1080p chưa có phiên nào đếm khung bị cắt.

Ở 640×480, phần lớn thời gian cả bốn nguyên vẹn (u01: 4 × 23,85 khung tốt/s, 120 s, cùng LiDAR + AI). Nhưng camera cổng
1 có những đợt 26–36 % khung hỏng, chưa rõ nguyên nhân.

Ngày 24/09/2026 có hai phiên bốn camera 720p cùng LiDAR + AI (w03, w04, mỗi phiên 60 s), lúc camera nhìn vào chỗ tối.
Hai phiên này không có khung bị cắt/xé nào, thêm một dấu hiệu khung bị cắt phụ thuộc cảnh (nghi do kích thước JPEG, chưa
đo). Đây **không** phải bằng chứng 720p đã dùng được; mặc định vẫn 640×480.

Nguồn: [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 2 (số theo mục 2.3) và mục 10;
[GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) mục 4.6.

### Rút/cắm lại camera

Hai lần ngày 23/09: ≈ 11:55 các camera, rồi ≈ 12:00–12:04 riêng camera cổng 3 sau khi nó bị treo không mở được. Danh tính
được kiểm sau cả hai lần (hai bản `list` lúc ≈ 12:05): index và InstanceId giữ nguyên. Sau đó có 0 khung cũ trong 7
phiên, nguyên nhân chưa rõ. Các phiên này chưa kiểm khung bị cắt (GIAI_DOAN_1_CAMERA.md mục 4.6).

## ESP32-S3, IMU BNO085, ToF VL53L1X, encoder/MT6701, AS5600 + nam châm, xe MN300, nguồn/cầu chì/E-stop (LA38)/phần tử ngắt động lực

Chưa nhận, chưa kiểm kê. Kế hoạch mục 1.1 có các mục này từ trước; danh sách ngày 22/09 bỏ sót AS5600 và phần nguồn/E-stop,
được bổ sung ngày 24/09/2026. Loại nguồn (UBEC hay XL4015), định mức cầu chì và phần tử ngắt chưa chốt (kế hoạch mục 1.1
và mục 3, đợt 5–6).

Đã có mẫu để điền khi nhận đồ (thêm tối 24/09/2026), **chưa điền ô nào** vì chưa nhận:

- MN300: phiếu kiểm kê [mn300_inventory.md](mn300_inventory.md) (gói hàng, pin/sạc, ESC, bộ thu, servo, motor, đầu nối,
  ảnh, câu hỏi cho shop). Khi nhận xe thì điền phiếu đó; mục này chỉ giữ dòng tóm tắt và link.
- Bảng đo đặc tính xe (tốc độ, góc lái, bán kính quay, quãng dừng): [GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md),
  mọi ô chưa đo.
- Nguồn, cầu chì, E-stop LA38, phần tử ngắt động lực, bảng tải nháp và kịch bản lỗi:
  [GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md); các ô ở đó còn chưa đo, chưa chốt hoặc chưa thử.
- ESP32-S3 và giao thức laptop–xe: [GIAO_THUC_XE.md](GIAO_THUC_XE.md). Firmware C++ **biên dịch cho ESP32-S3 từ 29/09/2026
  và chạy trong bo ảo QEMU từ 30/09/2026** (chỉ là giả lập, [MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md)). Firmware chưa
  nạp vào bo, chưa nối với bo thật nào.
