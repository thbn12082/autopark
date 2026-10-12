# Biên bản cổng chuyển bước giai đoạn 1 — kế hoạch v3.1, mục 5

Biên bản này chấm cổng chuyển bước của giai đoạn 1 (LiDAR và camera mẫu) theo kế hoạch v3.1 mục 5: ba kết quả LiDAR
tách riêng, năm điều kiện chuyển bước và các đầu ra phải có. Số đo chi tiết nằm ở
[GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md), [GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) và
[GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md).

Biên bản lập ngày 23/09/2026, bổ sung ngày 24, 25 và 29/09/2026. Lần bổ sung 25/09 đối chiếu với `origin/main` =
`54cb3e2`, nơi mọi việc tới khuya 24/09 đã commit và push.

## Trạng thái: CHƯA ĐẠT

Trạng thái không đổi từ khi lập biên bản. Chưa điều kiện chuyển bước nào được đánh dấu đạt.

- **Nhánh LiDAR:** đọc được scan và ghi/phát lại được. Sai số khoảng cách và định vị có tham chiếu độc lập thì chưa có.
- **Nhánh camera:** đã có bốn camera và hub, đo xong mode/FPS/bốn luồng trên máy bàn
  ([GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md)). Chưa gá, chưa hiệu chuẩn, chưa chấm AI trên ảnh thật. AI mới chạy
  trực tiếp trên bàn thử giai đoạn 2 để đo và quan sát.
- **Máy:** mọi số đo là trên máy bàn; laptop RTX 3050 Ti (máy nộp đồ án) chưa thử LiDAR hay camera.

## Ba kết quả LiDAR

Theo yêu cầu của kế hoạch, ba kết quả LiDAR được tách riêng:

| Kết quả | Trạng thái | Bằng chứng |
|---|---|---|
| Đọc scan được | **ĐẠT** trên máy bàn; sai số khoảng cách vẫn chưa đo (chi tiết dưới bảng) | [p07_nen_phong.analysis.json](evidence/lidar/p07_nen_phong.analysis.json), [hình](evidence/lidar/p07_nen_phong.png), [phân tích k01](evidence/lidar/k01_kiem_suc_khoe.analysis.json), [hình k01](evidence/lidar/k01_kiem_suc_khoe.png) |
| Tạo map được | **MỘT PHẦN**: bản đồ lưới tĩnh từ 181 vòng tại một vị trí cố định, lưu theo hợp đồng `Costmap` (không phải SLAM, không có tư thế ước lượng) | [map_p07.png](evidence/lidar/map_p07.png) |
| Định vị lại được | **CHƯA**: có công cụ, nhưng chưa đối chiếu với tham chiếu độc lập (chi tiết dưới bảng) | [DINH_VI_LIDAR.md](DINH_VI_LIDAR.md); [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 8; [ảnh live_headless](evidence/lidar/dinh_vi_live_headless_tren_p07.png), [ảnh k01](evidence/lidar/dinh_vi_k01_tren_p07.png), [tóm tắt](evidence/lidar/dinh_vi_tren_p07_20260924.json) |

**Đọc scan được — ĐẠT trên máy bàn.**

- p07 (22/09): COM4, chế độ Standard, 10,09 Hz, 508 tia/vòng, bản ghi 17,8 s không mất vòng, 0 byte lệch. Các số này tính
  cả lúc mô-tơ khởi động.
- k01 (24/09/2026), kiểm lại cùng thiết bị: cùng serial, health OK, ghi 15 s sau 3 s làm nóng. Kết quả 9,98 Hz, trung vị
  512 tia/vòng, 0 lỗi đọc, 0 vòng mất.
- Bỏ 3 s đầu mỗi bản ghi thì cả hai ngày đều ≈ 10,0 Hz và ≈ 510 tia/vòng ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md)
  mục 3b).
- 23 phiên bàn thử ngày 23–24/09 (có ba phiên 10 phút) cũng có 0 lỗi đọc, 0 vòng mất
  ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md)).
- Sai số khoảng cách vẫn chưa đo.
- Bản gốc của k01 là `runs/lidar_bench/20260924_kiem/k01_kiem_suc_khoe.*` (git-ignored). Bản sao phân tích và hình nằm
  trong git từ commit `a7cec5e` (25/09/2026).

**Định vị lại được — CHƯA.**

- Lúc lập biên bản: chưa có odometry, chưa có xe.
- Tối 24/09/2026 có công cụ định vị một vòng quét trên bản đồ tĩnh đã lưu (`lidar/localize.py`). Công cụ khớp tương quan
  nhánh-cận, tinh chỉnh, rồi báo OK / AMBIGUOUS / FAILED; nó không phải SLAM và không có odometry. Kết quả được báo riêng
  như kế hoạch yêu cầu: đọc scan / tạo map / định vị lại.
- Chạy offline trên bản ghi có sẵn: cùng chỗ thì nhất quán (live_headless 60/60 OK, lệch hướng +4,3° so với lúc dựng bản
  đồ, chưa rõ nguyên nhân); chỗ khác thì báo hỏng (k01 151/151 FAILED).
- **Chưa đối chiếu với tham chiếu độc lập**: chưa lần nào đặt LiDAR ở vị trí đo bằng thước, nên chưa có sai số thật. Các
  ngưỡng chưa chốt. Trạng thái vẫn CHƯA.
- Ngày 25/09/2026 có thêm odometry khớp scan và bản đồ tăng dần (`lidar/scan_odometry.py`, commit `a7cec5e`). Công cụ mới
  thử offline trên DROW v2 và sáu bản ghi C1 đứng yên; chưa có bản ghi C1 nào khi cảm biến di chuyển. So sánh phương án ở
  [SO_SANH_DINH_VI_SLAM.md](SO_SANH_DINH_VI_SLAM.md); lúc đó là đề xuất, chưa chốt. Ngày 02/10/2026 người dùng đồng ý làm
  theo đề xuất đó ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 7).
- Hai dòng "Tạo map được" và "Định vị lại được" giữ nguyên mức.

## Điều kiện chuyển bước

- [ ] **Laptop nhận LiDAR và camera ổn ở mode đã ghi rõ** — chưa. Trên máy bàn, LiDAR và một camera đạt, bốn camera chỉ
  dùng được ở 640×480; laptop RTX 3050 Ti (máy nộp đồ án) chưa thử cả LiDAR lẫn camera.
  - LiDAR: đạt trên máy bàn dùng tới 25/09/2026 (mode Standard, 460800 bps, COM4). Máy bàn từ 29/09/2026 đọc được LiDAR
    ở COM3 qua lệnh `may_moi`: 10,00 Hz, trung vị 508 tia/vòng ([chuyển máy](CHUYEN_MAY_BAN.md) mục 2).
  - Một camera: đạt trên máy bàn cho MJPG 720p (m01/n01): 23,9 fps trong ánh sáng phòng, 0 khung cũ trong 30 s, nhịp khung
    không đều, không đổi sau khi lột phim bảo vệ ống kính.
  - Bốn camera 720p đồng thời, hub bus-powered: ba chiếc không rớt khung; camera cổng 4 rớt thất thường (0 khung cũ/60 s ở
    n03, 4 ở m05; 18,6 / 22,3 / 3,9 fps ở ba phiên 10 s m12a–c). Sau khi rút/cắm lại các camera: 0 khung cũ ở cả
    720p × 4 và 1080p × 4 trong 7 phiên, nguyên nhân chưa rõ (GIAI_DOAN_1_CAMERA.md mục 4.5).
  - Chiều 23/09 phát hiện khung MJPEG bị cắt cụt, nên "không rớt" và "0 khung cũ" ở trên chỉ nói về khung cũ. Tính cả
    khung bị cắt cụt, bốn camera qua hub chỉ dùng được ở **640×480**: phiên u01 chạy cùng LiDAR và AI 120 s, 4 × 23,85
    khung tốt/s, 0 khung hỏng; phiên u04 10 phút có 6 khung hỏng ở cổng 4. Ở 480p camera cổng 1 vẫn có những đợt 26–36 %
    khung hỏng, chưa rõ nguyên nhân; bộ dò loại các khung đó. Ở 720p × 4, trong các phiên ngày 23/09, hai hoặc ba camera
    bị cắt phần lớn khung ([GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) mục 4.6,
    [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 2).
  - Ngày 24/09/2026, hai phiên w03/w04 (720p × 4, 60 s, camera nhìn vào chỗ tối) không có khung bị cắt/xé nào
    ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 10). Đây thêm một dấu hiệu khung bị cắt phụ thuộc cảnh (kích
    thước JPEG), **không** phải bằng chứng 720p đã dùng được; mặc định vẫn là 640×480.
- [ ] **Có dữ liệu và phép thử lưu/nạp bản đồ; phần định vị chưa đạt được báo riêng** — có phép thử lưu/nạp ở mức bản
  đồ lưới tĩnh; ô này vẫn để trống vì bản đồ chưa phải của phương án SLAM.
  - Lúc lập biên bản (23/09) mới có bản đồ tĩnh và file `costmap.json`, chưa có phép thử nạp lại hay định vị.
  - Từ 24/09/2026 có phép thử lưu/nạp: `tests/test_fusion.py::test_static_layer_round_trips_through_costmap_json` ghi bản
    đồ bằng `lidar/occupancy.py`, nạp bằng `fusion/layers.py::StaticMapLayer.load`, rồi ghi/nạp lại qua
    `write_costmap_json`/`read_costmap_json` và so bằng nhau.
  - Cùng ngày cũng nạp lại được `costmap.json` thật của p07 (`runs/lidar_bench/20260922/map_p07/`, git-ignored): lưới
    160 × 160 ô 5 cm, 5.657 FREE, 230 OCCUPIED, khớp số ở [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 5; ghi/nạp lại
    bằng nhau.
  - Ô này vẫn để trống vì bản đồ mới là bản đồ lưới tĩnh từ một vị trí ("Tạo map được: MỘT PHẦN" ở bảng trên), chưa phải
    bản đồ của phương án SLAM.
  - Định vị được báo riêng ở dòng "Định vị lại được". Từ tối 24/09/2026 phần này có công cụ và kết quả riêng
    ([DINH_VI_LIDAR.md](DINH_VI_LIDAR.md)), nhưng chưa đạt vì chưa có vị trí tham chiếu đo bằng thước.
- [ ] **Camera đủ nét trong vùng làm việc; hiệu chuẩn được và chạy AI trên ảnh thật** — chưa.
  - Camera chưa đặt ở độ cao/góc chúc dự kiến.
  - Hiệu chuẩn: chưa in bảng, chưa chụp ảnh hiệu chuẩn. Ngày 23/09 còn chưa có mã cho ống kính thật. Từ 24/09 đã có mã
    hiệu chuẩn fisheye cho ống kính thật và tệp bảng để in: `perception/calib_board.py` tạo bảng in,
    `perception/fisheye_calib.py` hiệu chuẩn Kannala–Brandt bằng `cv2.fisheye` (một tệp nội tham cho mỗi cổng hub),
    `ui/calib_app.py` chụp ảnh. Mã mới kiểm trên ảnh tổng hợp và camera giả. Chưa có tệp hiệu chuẩn của camera nào, và
    các ngưỡng chấp nhận trong mã là đề xuất, chưa kiểm trên camera thật. Vì vậy vẫn là "chưa hiệu chuẩn".
  - AI: từ chiều 23/09 mô hình đã chạy trực tiếp trên khung của bốn camera thật nằm trên bàn
    ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 3.3 và 7), nhưng chỉ đo thời gian suy luận và xem lớp tô. Chưa
    có ảnh sa bàn có nhãn, nên chưa đo và lưu lỗi như kế hoạch yêu cầu, nhất là vật cản bị gọi thành vùng trống.
  - Công cụ gán nhãn ảnh sa bàn có từ 24/09 ([GAN_NHAN_SA_BAN.md](GAN_NHAN_SA_BAN.md)). Mới thử nhập và export hai bộ ảnh
    thật chụp ngày 23/09 lúc camera nằm trên bàn (không ở độ cao/góc chúc của xe). Chưa gán nhãn ảnh thật nào.
- [ ] **Có số đo, không chỉ nhận xét video "mượt"** — có nhiều số đo trên máy bàn, nhưng còn thiếu các mục ở ý "Chưa
  đo" dưới đây.
  - LiDAR: có số đo tần số, tia/vòng, khoảng trống, tỉ lệ không phản hồi. **Sai số khoảng cách so với thước chưa đo**;
    cần phiên đặt hộp ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 6).
  - Camera: có FPS, khung cũ, khoảng cách khung, CPU ([GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) mục 4); có khung
    MJPEG bị cắt/xé.
  - Chạy chung bốn camera + LiDAR + AI trên máy bàn: có thời gian suy luận, độ trễ trong máy, độ lệch giữa camera và
    LiDAR, tải GPU, nhiệt GPU ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md)).
  - **Chưa đo:** độ trễ từ sự kiện thật tới lúc khung tới máy, nhiệt CPU, và mọi số trên laptop RTX 3050 Ti (máy nộp đồ
    án).
- [ ] **Chỉ quyết định mua thêm ba camera sau khi mẫu vượt kiểm tra đơn camera** — đã mua đủ bốn trước khi thử. Bài thử
  đơn camera làm ngày 23/09: đạt về mode và FPS, chưa đạt về vùng làm việc/hiệu chuẩn.

## Đầu ra phải có

| Tệp | Trạng thái |
|---|---|
| `hardware_inventory.md` | có, thiếu ảnh bộ thực giao và model trên nhãn ([hardware_inventory.md](hardware_inventory.md)) |
| `camera_modes.csv`, `camera_01_calibration.yaml` | `camera_modes.csv`: có ([docs/camera_modes.csv](camera_modes.csv)); calibration: chưa |
| Bản quét / bản đồ thử | có: `runs/lidar_bench/20260922/` và `runs/lidar_bench/20260924_kiem/` (kiểm lại 24/09), git-ignored; bản sao nhỏ ở `docs/evidence/lidar/` (dưới bảng) |
| Log nhận ảnh, video mẫu | có: `runs/camera_bench/20260923/` (git-ignored; dưới bảng), bản nhỏ ở [evidence/camera/](evidence/camera/) |
| `gate_01.md` | tệp này |

Bản sao nhỏ trong `docs/evidence/lidar/`:

- bản sao của phiên 22/09;
- từ tối 24/09/2026: ảnh overlay định vị p07, live_headless, k01 trên bản đồ p07 và tệp tóm tắt
  `dinh_vi_tren_p07_20260924.json`;
- từ commit `a7cec5e` (25/09/2026): bản sao k01 (`k01_kiem_suc_khoe.{png,json,analysis.json}`), độ lặp lại
  (`do_lap_lai_*`) và odometry khớp scan (`odometry_khop_scan_*`).

`runs/camera_bench/20260923/` gồm 17 file `*.measure.json` của 13 phiên m01–m13 còn phim bảo vệ ống kính, 6 file n01–n06
sau khi lột phim, 10 file q* sau khi rút/cắm lại camera; 3 video và 9 ảnh tĩnh.
