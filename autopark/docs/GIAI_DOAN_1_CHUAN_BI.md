# Giai đoạn 1 — phần làm được khi chưa có đủ thiết bị (22/09/2026)

Tài liệu này ghi lại phần việc của giai đoạn 1 (GĐ 1) làm trong ngày 22/09/2026, khi mới có LiDAR và chưa cắm camera nào. Phần việc gồm mô hình camera fisheye WoodScape, mặt nạ ROI, costmap từ ảnh, nguồn dữ liệu phát lại, bộ giám sát dữ liệu cũ và xuất mô hình AI sang ONNX. Nội dung chính là trạng thái ngày 22/09. Những gì thay đổi sau đó được ghi kèm ngày, chủ yếu ở cuối mục 1 và mục 7.

Kế hoạch đối chiếu là [kế hoạch v3.1 bản `9d68257`](https://github.com/thbn12082/autopark/blob/9d68257/KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md), mục 5 "Khi đang chờ đồ" và mục 6–7 (BEV, hợp nhất). Trong [bản kế hoạch hiện tại](../../KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md), phần này là đoạn "Khi chờ đồ" của mục 5.

## Tóm tắt

- **Mức bằng chứng ngày 22/09:** phần mềm chạy trên dữ liệu lưu sẵn (WoodScape, DROW v2, ACDC, RoadObstacle21). Chưa có khung hình camera hay bản quét nào từ thiết bị của dự án đi qua các khối này.
- **Thay đổi đến 24/09:** bản quét thật của RPLIDAR C1 đã đi qua `safety/freshness.py` và `ui/scan_view.py` trong `lidar/live_view.py`. Lần chạy đó là headless, 8 s, trên COM4 ngày 22/09 ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 4). `UsbCameraSource` chạy trên camera thật từ 23/09 (mục 1 và 4 bên dưới).
- **Vẫn chỉ chạy trên ảnh WoodScape:** calibration, ROI và costmap. Theo lần cập nhật ngày 25/09/2026, chưa có tệp nội tham, ngoại tham hay ROI nào của camera thật (mục 7).
- **Thiết bị lúc viết (22/09):** RPLIDAR C1 đã cắm qua cầu USB–UART CP2102N; sau khi cài driver CP210x cùng ngày thì thành COM4 ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md)). Chưa cắm camera USB nào. Chưa có ảnh sa bàn.

## 1. Đã làm gì

Bảng dưới liệt kê các khối viết trong ngày 22/09 và trạng thái kiểm của từng khối.

| Khối | Module | Trạng thái |
|---|---|---|
| Mô hình camera fisheye WoodScape: nội tham đa thức bậc 4, ngoại tham camera→xe | `perception/calibration.py` | Kiểm chứng ba cách độc lập (mục 2) |
| Mặt nạ ROI theo camera: vùng thân xe mình, viền ống kính | `perception/roi.py`, `configs/roi/woodscape_v1/` | Dựng từ 5.764 ảnh train |
| Chiếu mask FREE/BLOCKED xuống mặt sàn thành `Costmap` (hợp đồng có sẵn ở `domain/sensors.py`) | `perception/costmap.py` | Có test hình học tổng hợp; đã chạy trên 4 ảnh WoodScape |
| Đánh giá ngoài miền ACDC, RoadObstacle21, kèm phân tích theo lớp gốc (người, xe, cây, nhà) | `perception/evaluate_external.py`, `configs/acdc_cityscapes_to_binary_v1.json` | Kết quả ở [HUAN_LUYEN.md](../../HUAN_LUYEN.md) mục 8–14 |
| Ngưỡng quyết định thiên về an toàn | `perception/engine.py::decide`, `evaluate.py --sweep/--threshold` | Chọn trên val, ghi log mọi lần chấm test |
| Xuất ONNX và đo độ trễ | `perception/export_onnx.py` | Khớp PyTorch 99,9999 % pixel |
| Nguồn camera phát lại (thư mục ảnh, file video) và khung `UsbCameraSource` | `video/sources.py` | Hai nguồn phát lại có test; USB thử trên thiết bị thật ngày 23/09 ([GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md)) |
| Nguồn LiDAR phát lại DROW v2 theo hợp đồng `LidarScan` | `lidar/drow.py` | Có test; đọc được 113 recording |
| Vẽ scan (OpenCV), widget Qt và trình phát lại | `lidar/render.py`, `ui/scan_view.py`, `lidar/viewer.py` | Test offscreen |
| Giám sát dữ liệu cũ, mất hoặc không hợp lệ cho mọi nguồn | `safety/freshness.py` | Có test; dùng trong trình phát lại |

Cùng ngày, nhánh LiDAR thật được làm ở [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) và dùng lại các khối ở đây. Nhánh đó gồm driver RPLIDAR C1 trên COM4, ghi và phát lại phiên, bench, bản đồ lưới tĩnh.

Ngày 22/09 chưa làm: hợp nhất nhiều camera, hợp nhất LiDAR–camera, SLAM/định vị và mọi thứ liên quan ESP32. Các việc này tiến triển sau đó như sau.

**Đến 24/09/2026:**

- Lớp và quy tắc hợp nhất LiDAR/camera/ToF bằng phần mềm đã có từ chính ngày 22/09, ở [GIAI_DOAN_3_CHUAN_BI.md](GIAI_DOAN_3_CHUAN_BI.md). Tuy vậy lớp camera chưa có khung hình camera thật nào đi qua.
- Bàn thử mới chỉ ghép bộ ảnh bốn camera theo thời gian ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md)). Chưa chiếu kết quả AI xuống sàn, chưa ghép bốn camera, chưa hợp nhất với LiDAR trên dữ liệu thật.
- Giao thức laptop–ESP32-S3, `VehicleIO` và firmware có từ 24/09 ở [GIAO_THUC_XE.md](GIAO_THUC_XE.md). Lúc đó chỉ có phần mềm và mô phỏng, mã C++ chưa biên dịch, chưa có bo.
- SLAM/định vị vẫn chưa làm.

**Ngày 25/09/2026** (mã đã commit và push, `origin/main` = `54cb3e2`):

1. Có mã BEV chiếu và gộp xác suất AI của nhiều camera xuống lưới mặt sàn hệ xe: `perception/bev.py`, commit `1d2b857`, xem [BEV.md](BEV.md). Mã mới được kiểm trên rig bốn camera ảo và ảnh WoodScape, chưa chạy với hiệu chuẩn thật trên camera dự án. Trên hai bộ ảnh thật mới chỉ chạy thử bộ lọc khung hỏng với nội tham danh định, nên kết quả BEV ở đó không có nghĩa ([BEV.md](BEV.md) mục 6).
2. Có định vị một vòng quét trên bản đồ tĩnh (`lidar/localize.py`, commit `b100a5d`) và odometry khớp scan (`lidar/scan_odometry.py`, commit `a7cec5e`). Cả hai chỉ chạy offline trên bản ghi, chưa có tham chiếu độc lập ([DINH_VI_LIDAR.md](DINH_VI_LIDAR.md), [SO_SANH_DINH_VI_SLAM.md](SO_SANH_DINH_VI_SLAM.md)).
3. `VehicleIO` được nối vào phiên đỗ xe và chế độ quan sát (commit `c43e8d3`, [CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md)). Phần này vẫn chỉ chạy với bo mô phỏng (`SimVehicleIO` + `FirmwareModel`) và cổng serial giả.

Cũng từ commit `b01dea4` ngày 25/09/2026, BEV được nối vào phiên đỗ qua `fusion/camera_ai.py`, làm nguồn vật cản thứ hai. Nguồn này chỉ tạo vật cản khi hiệu chuẩn đạt. Vì chưa có hiệu chuẩn thật nên mọi lô đều bị chặn ([AI_DIEU_KHIEN_XE.md](AI_DIEU_KHIEN_XE.md)).

**Đến 30/09/2026:** mã C++ của firmware biên dịch được từ 29/09/2026 (test host 703 check, 0 lệch; PlatformIO cho ESP32-S3). Từ 30/09/2026 firmware chạy trong bo ảo QEMU, tức firmware thật chạy trong trình giả lập, chỉ là giả lập ([MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md)). Vẫn chưa có bo thật, chưa nạp firmware.

## 2. Calibration WoodScape — vì sao tin được

Mục này nói `perception/calibration.py` đọc tệp hiệu chuẩn WoodScape theo quy ước nào, và ba phép kiểm cho thấy cách đọc đó đúng.

Quy ước lấy từ `readme.txt` nằm **bên trong** `datasets/woodscape_metadata/calibration.zip`; README ở ngoài chỉ dẫn link. Cụ thể:

- Nội tham: `rho(θ) = k1θ + k2θ² + k3θ³ + k4θ⁴`, rho tính bằng pixel, θ là góc từ trục quang tính bằng radian.
- Tâm ảnh: `width/2 − 0,5 + cx_offset`, `height/2 − 0,5 + cy_offset`.
- `aspect_ratio` chỉ nhân thành phần dọc.
- Quaternion theo thứ tự `(x, y, z, w)`, quay **camera → xe**.
- Hệ xe theo ISO 8855: x hướng trước, y sang trái, z lên, gốc trên mặt đất dưới tâm trục sau. Quy ước này trùng với quy ước của dự án.
- Hệ camera theo OpenCV: X sang phải, Y xuống, Z là trục quang.

Ba phép kiểm chứng dưới đây có kết quả ở `runs/perception_integration/calibration_convention_check.json` và `runs/perception_integration/ipm_check_*.jpg`. Thư mục `runs/` nằm ngoài Git, chỉ có khi chép cả thư mục dự án.

1. Trục quang bốn camera tính ra trong hệ xe: FV (0,92; 0; −0,40), tức nhìn trước, chúc xuống 23°; RV (−0,66; 0; −0,75); MVL (−0,08; +0,23; −0,97) với vị trí y = +0,99 m (bên trái); MVR y = −0,96 m. Nếu đọc theo chiều ngược lại (xe → camera) thì camera trước chĩa sang trái, điều này vô lý.
2. Lưới mặt đất 1 m chiếu vào ảnh FV bám đúng mặt đường: các vạch hội tụ về chân trời, vòng gần khớp mép nắp ca-pô.
3. `pixel_to_ground(ground_to_pixel(p)) = p` với sai số 0 trên 180 điểm của 4 camera.

Một agent đọc toàn bộ 8.234 tệp và có thêm các phát hiện phụ:

- **Calibration khác nhau giữa các recording**: mỗi camera có 31–32 bộ riêng, thuộc hai cụm vị trí lắp. Vì vậy phải nạp hiệu chuẩn theo từng ảnh.
- `aspect_ratio` lệch tối đa 6·10⁻⁴.
- **Bốn tệp** `06418_MVR, 06419_RV, 06423_MVR, 06424_RV` mang ngoại tham của camera trước dù tên là camera hông/sau. Đây là lỗi của dữ liệu gốc.
- `vehicle_info.zip` là telemetry CAN, không có kích thước xe.

## 3. ROI và costmap

Mục này mô tả cách dựng mặt nạ ROI cho rig WoodScape và cách costmap chiếu nhãn AI xuống mặt sàn.

**ROI** (`python -m autopark.perception.roi build`) được dựng như sau:

- Rasterize polygon `ego_vehicle` đúng z-order như bộ sinh nhãn gốc. Lần đầu vẽ polygon thô thì RV bị loại 99 %, kết quả này sai; sau khi theo z-order còn 61 %.
- Lấy tần suất trên tập train. Pixel bị loại nếu tần suất ≥ 0,2 (bảo thủ) hoặc gần đen ở ≥ 95 % ảnh.

Kết quả loại FV 48,8 %, MVL 48,4 %, MVR 48,8 %, RV 61,4 % diện tích ảnh. Phần lớn vùng bị loại là thân xe và viền ngoài vòng ảnh của ống kính. Đây là ROI của rig WoodScape; với camera của dự án phải dựng lại từ vài mặt nạ vẽ tay, cùng định dạng tệp.

**Costmap** (`python -m autopark.perception.costmap`) mặc định dùng ROI `configs/roi/woodscape_v1`. Nếu chạy `--no-roi` thì costmap bị đóng dấu không hợp lệ, vì pixel thân xe mang nhãn vô nghĩa. Cách tính:

- Mỗi tâm ô lưới được chiếu *vào ảnh* rồi lấy nhãn pixel. Mã chỉ dùng phép chiếu thuận, không nghịch đảo đa thức.
- Pixel IGNORE, ô ngoài ảnh hoặc ngoài ROI thành **UNKNOWN**.
- Quét che khuất theo góc phương vị: sau ô OCCUPIED gần nhất, mọi ô xa hơn trong góc mà ô đó chiếm thành UNKNOWN. Nhờ vậy vật cao chỉ đánh dấu chân, không "kéo vệt" ra xa, và phần sàn bị che không bị ghi là FREE.
- Ô ngoài `max_range` thành UNKNOWN.
- Giả định mặt sàn phẳng z = 0.
- Bố cục: `cells[row][col]`, row theo y tính từ `origin.y` (trái +), col theo x tính từ `origin.x` (trước +), `origin = Pose(x_min, y_min, 0)`.

Trên ảnh `00007_FV` với lưới 25 × 20 m, ô 0,1 m, tầm 12 m, costmap có 14.511 ô FREE, 36 ô OCCUPIED (chân vật cản) và 35.453 ô UNKNOWN. Hình `runs/perception_integration/costmap_00007_FV/costmap_textured.png` (ngoài Git) cho thấy mặt đường phía trước là FREE, chân xe đỗ và người đi bộ hai bên là OCCUPIED, phía sau chúng màu xám.

**Chưa có cách đo sai số costmap bằng tham chiếu độc lập.** Đó là việc của giai đoạn 2–3, với vật mẫu có tọa độ đo được.

## 4. Nguồn dữ liệu phát lại và giám sát dữ liệu cũ

Mục này mô tả các nguồn camera và LiDAR phát lại, nguồn camera USB và bộ giám sát dữ liệu cũ.

**`video/sources.py`.** Mọi nguồn có cùng giao diện `read() -> Frame(meta: CameraFrame, image)`. Nguồn phát lại trả `None` khi hết; nguồn trực tiếp ném `FrameReadError` khi một lần đọc hỏng.

- `ImageSequenceSource`: thứ tự tự nhiên theo tên, thời gian = t0 + chỉ số/fps.
- `VideoFileSource`: một đồng hồ cho cả file. Mã dùng vị trí trong video nếu nó tăng nghiêm ngặt, không thì dùng chỉ số/fps. Stamp không bao giờ lặp hay lùi.
- `UsbCameraSource`: OpenCV, DirectShow trên Windows. Mode được đưa vào ngay lúc mở. Stamp lấy ngay sau `read()`, tức đã gồm thời gian giải mã. Nguồn yêu cầu hàng đợi driver 1 khung; DirectShow có nhận hay không được ghi ở `buffer_size_applied`. Khung trùng byte bị coi là lỗi đọc.
- `mode()` của `UsbCameraSource` ghi kích thước thực, còn fourcc/fps là giá trị yêu cầu. Điểm này được sửa ngày 23/09 theo [GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md).
- Từ chiều 23/09, khung MJPEG bị cắt cụt hoặc có dải xé cũng bị loại bằng `FrameReadError` và được đếm riêng ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 2).

Nguồn USB đã chạy trên camera thật ngày 23/09 (`camera_bench source`). Một lần `read()` bị treo vẫn chặn vòng lặp, nên `check()` của bộ giám sát phải chạy từ timer riêng.

**`lidar/drow.py`.** Đọc CSV 452 cột: seq, thời gian, 450 range. Góc quét 224,5°, bước 0,5°.

- Chỉ số 0 là góc âm nhất (bên phải), theo loader v2 của tác giả. README gốc lại nói "giá trị đầu bên trái". Module có tham số `mirror`, và **phải đối chiếu với thiết bị thật trước khi tin chiều**.
- Range ≥ 29,9 m thành NaN. Tác giả ghi 29,96 là N/A; trong dữ liệu cũng xuất hiện 29,98 và 29,99.
- Nhãn `.wp/.wc/.wa`: danh sách rỗng khác với thiếu nhãn.

Chiều góc đã được kiểm trên dữ liệu thật. Khung `seq 9891` của `run_2015-11-25-10-34-20-a` có nhãn người tại r = 0,63 m, φ = −1,89 rad. Vòng tròn nhãn (vẽ bằng φ của tác giả) trùm đúng cụm điểm quét (vẽ bằng ánh xạ chỉ số → góc của module). Hình ở `runs/perception_integration/drow_scan_person.png` (ngoài Git). Vậy ánh xạ chỉ số theo loader v2 nhất quán với nhãn; còn chiều trái/phải so với thế giới thật vẫn phải kiểm bằng thiết bị.

**`safety/freshness.py`.** Mỗi nguồn có `max_age_s` và chu kỳ mong đợi.

- `observe(stamp, now)` từ chối mẫu không hợp lệ, mẫu lùi thời gian, mẫu ở tương lai (`CLOCK_SKEW`) và mẫu đã quá tuổi ngay lúc đến (`STALE_ON_ARRIVAL`).
- `check(now)` phát `SafetyEvent` `NO_DATA` / `STALE_DATA` / `CLOCK_SKEW`, với action STOP.

Ngày 22/09 một vòng review độc lập gồm 4 agent đã chỉ ra các lỗi sau, và tất cả đã được sửa: stamp USB lấy sau khi giải mã, mẫu cũ lúc đến vẫn được nhận, sắp xếp tên file theo chuỗi, cờ `mirror` không áp cho nhãn, hợp đồng `LidarScan` nhận range âm.

Có thể thử logic "dữ liệu cũ thì không dùng" mà không cần cảm biến, bằng trình phát lại `python -m autopark.lidar.viewer <csv> --labels wp`. Nhấn Space để tạm dừng; sau 0,3 s tiêu đề đổi màu và trạng thái báo `STALE_DATA`.

## 5. ONNX và độ trễ

`python -m autopark.perception.export_onnx` xuất đồ thị ONNX (opset 17, exporter TorchScript). Đồ thị nhận tensor chuẩn hóa (1, 3, 384, 512) và trả logits.

Đối chiếu trên 16 ảnh val bằng onnxruntime CPU: lệch logit tối đa 7·10⁻⁵, trùng argmax 99,9999 %.

Độ trễ một ảnh **trên máy bàn**, khi GPU rảnh (p50, 200 lượt):

| Cách chạy | p50 |
|---|---|
| onnxruntime CPU fp32 | 7,6 ms |
| torch CUDA fp32 | 4,4 ms |
| torch CUDA fp16 | 5,5 ms |
| Đầu-cuối từ ảnh 1280×966 (letterbox → mạng → softmax về CPU) | 7,8 ms |

Lúc GPU bận huấn luyện, các số này cao gấp 2–3 lần. Chi tiết ở `runs/ai_woodscape_rtx4000_v1/export/export_report.json`. Script tự sinh ảnh nhiễu khi không có dataset, nên chạy được trên máy khác chỉ với `best.pt`.

Ngày 24/09/2026 người dùng xác nhận vai trò hai máy. Máy bàn i9-14900 + RTX 4000 Ada là máy phát triển chính. Laptop i7-12700H + RTX 3050 Ti (4 GB VRAM) là máy mang đi nộp và trình diễn đồ án. Tính đến ngày đó, mọi số đo là trên máy bàn, chưa đo trên laptop. Số dùng cho khóa luận phải đo lại trên laptop bằng cùng lệnh.

Máy bàn trong mục này là máy dùng tới 25/09/2026. Từ 29/09/2026 máy bàn là Dell Precision 3680 cùng cấu hình ([chuyển máy](CHUYEN_MAY_BAN.md)).

## 6. Cách chạy

Các lệnh dưới chạy trong thư mục `autopark`. Nhóm đầu cần `.venv-train` (có torch); nhóm sau dùng `.venv` (mô phỏng, PySide6), không cần torch.

```powershell
# trong thư mục autopark, .venv-train (torch)
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.roi build
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.costmap --checkpoint runs/ai_woodscape_rtx4000_v1/best.pt --image datasets/training/woodscape/rgb_images/00007_FV.png --roi configs/roi/woodscape_v1 --out runs/perception_integration/costmap_00007_FV
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.evaluate_external --checkpoint runs/ai_woodscape_rtx4000_v1/best.pt --dataset acdc --split val --out <dir>
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.evaluate --checkpoint runs/ai_woodscape_rtx4000_v1/best.pt --split val --sweep --out <dir>
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.export_onnx --checkpoint runs/ai_woodscape_rtx4000_v1/best.pt --out runs/ai_woodscape_rtx4000_v1/export
# .venv (mô phỏng, PySide6) — không cần torch
.\.venv\Scripts\python.exe -X utf8 -m autopark.lidar.viewer datasets/drow/DROWv2-data/val/run_2015-11-25-10-34-20-a.bag.csv --labels wp
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_perception_calibration.py tests/test_phase1_sources.py tests/test_scan_view_ui.py
```

## 7. Việc kế tiếp theo kế hoạch

Ngày 22/09 bốn việc kế tiếp là:

1. Cài driver CP210x (Silicon Labs) để có cổng COM, rồi viết driver RPLIDAR C1 (UART 460800, giao thức SLAMTEC) theo hợp đồng `LidarScan`, ghi phiên đo, so với DROW replay.
2. Khi có camera mẫu: dùng `UsbCameraSource` + `mode()` để liệt kê mode thật, chụp ảnh sa bàn, chạy `predict.py` để đo độ lệch miền trước khi gán nhãn.
3. Hiệu chuẩn camera của dự án bằng OpenCV fisheye và ghi calibration cùng định dạng JSON WoodScape để `costmap.py` dùng lại nguyên vẹn.
4. Định nghĩa `UNKNOWN` cho costmap hợp nhất (LiDAR + camera + ToF) và cách tham chiếu độc lập để đo sai số BEV (kế hoạch mục 6).

Tình trạng từng việc theo các lần cập nhật ngày 24/09 và 25/09/2026:

**Việc 1 — LiDAR.** Driver RPLIDAR C1, ghi/phát lại phiên và phiên đo tĩnh đã làm ngày 22/09 ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md)). Đến 24/09 còn thiếu các lần đặt hộp để đo sai số khoảng cách.

**Việc 2 — Camera.** Ngày 23/09 đã liệt kê mode thật và đo trên máy bàn bằng `video/camera_bench.py` ([GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md)). Đến 24/09 chưa chụp ảnh sa bàn, chưa đo độ lệch miền trên ảnh sa bàn.

**Việc 3 — Hiệu chuẩn.** Từ 24/09 đã có mã:

- `perception/calib_board.py`: bảng ô vuông để in, gồm PDF, PNG và JSON mô tả bảng.
- `perception/fisheye_calib.py`: gọi `cv2.fisheye.calibrate`, chuyển sang mô hình đa thức dạng WoodScape `FisheyeIntrinsics` có báo sai số khớp, ghi một tệp JSON cho mỗi camera, khóa theo cổng hub.
- Giao diện chụp `ui/calib_app.py`.

Mã mới được kiểm bằng ảnh bảng tổng hợp và camera giả (`tests/test_fisheye_calib.py`, `tests/test_calib_app_ui.py`). Tệp hiệu chuẩn là JSON riêng của dự án (`autopark.fisheye_intrinsics/1`), có một khối nội tham dạng WoodScape. Đây không phải tệp calibration WoodScape đầy đủ: tệp chỉ có nội tham, chưa có ngoại tham camera→xe, nên `costmap.py` chưa dùng lại nguyên vẹn được. Đến 24/09 chưa hiệu chuẩn camera nào: chưa in bảng, chưa chụp ảnh bảng. Các ngưỡng chấp nhận trong mã mới là đề xuất, chưa kiểm trên camera thật.

Ngày 25/09 ngoại tham camera→xe có công cụ riêng: `perception/extrinsics_calib.py`, commit `65b7127`, xem [NGOAI_THAM_VA_ROI.md](NGOAI_THAM_VA_ROI.md). BEV ghép nội tham `cam_p<N>.json` với ngoại tham bằng `bev.load_rig()` và dùng cùng phép chiếu với `costmap.project_labels`, nên không cần tệp calibration WoodScape đầy đủ ([BEV.md](BEV.md)). Vẫn chưa có tệp nội tham, ngoại tham hay ROI nào của camera thật.

**Việc 4 — UNKNOWN và sai số BEV.** Quy tắc hợp nhất trong `fusion/fuse.py` giữ ô không có lớp tươi nào là `UNKNOWN` ([GIAI_DOAN_3_CHUAN_BI.md](GIAI_DOAN_3_CHUAN_BI.md)). Đến 24/09 chưa có cách đo sai số BEV bằng tham chiếu độc lập. Ngày 25/09 cách đo bằng vật mẫu đặt ở vị trí đo bằng thước đã được viết thành đề xuất ([BEV.md](BEV.md) mục 8; [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 5.4, bản nháp), chưa làm.
