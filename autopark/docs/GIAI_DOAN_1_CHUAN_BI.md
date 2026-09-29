# Giai đoạn 1 — phần làm được khi chưa có đủ thiết bị (22/09/2026)

**Kế hoạch đối chiếu:** [v3.1, mục 5 "Khi đang chờ đồ"](../../KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) và mục 6–7 (BEV, hợp nhất).
**Mức bằng chứng:** phần mềm chạy trên dữ liệu lưu sẵn (WoodScape, DROW v2, ACDC, RoadObstacle21). Chưa có khung hình camera hay bản quét nào từ thiết bị của dự án đi qua các khối này. *Cập nhật 24/09/2026:* câu trên không còn đúng cho mọi khối. Bản quét thật của C1 đã đi qua `safety/freshness.py` và `ui/scan_view.py` trong `lidar/live_view.py` (chạy headless 8 s trên COM4 ngày 22/09, [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 4); `UsbCameraSource` chạy trên camera thật từ 23/09 (mục 1 và 4 bên dưới). Calibration, ROI và costmap vẫn chỉ chạy trên ảnh WoodScape.
**Thiết bị tại thời điểm viết:** RPLIDAR C1 đã cắm (cầu USB–UART CP2102N; sau khi cài driver CP210x cùng ngày thì thành COM4 — xem [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md)). Không có camera USB nào cắm vào. Chưa có ảnh sa bàn.

## 1. Đã làm gì

| Khối | Module | Trạng thái |
|---|---|---|
| Mô hình camera fisheye WoodScape (nội tại đa thức bậc 4, ngoại tại camera→xe) | `perception/calibration.py` | Kiểm chứng ba cách độc lập (mục 2) |
| Mặt nạ ROI theo camera (vùng thân xe mình / viền ống kính) | `perception/roi.py`, `configs/roi/woodscape_v1/` | Dựng từ 5.764 ảnh train |
| Chiếu mask FREE/BLOCKED xuống mặt sàn → `Costmap` (hợp đồng có sẵn ở `domain/sensors.py`) | `perception/costmap.py` | Có test hình học tổng hợp; đã chạy trên 4 ảnh WoodScape |
| Đánh giá ngoài miền: ACDC, RoadObstacle21 (kèm phân tích theo lớp gốc: người, xe, cây, nhà) | `perception/evaluate_external.py`, `configs/acdc_cityscapes_to_binary_v1.json` | Kết quả ở [HUAN_LUYEN.md](../../HUAN_LUYEN.md) mục 8–14 |
| Ngưỡng quyết định thiên về an toàn | `perception/engine.py::decide`, `evaluate.py --sweep/--threshold` | Chọn trên val, ghi log mọi lần chấm test |
| Xuất ONNX + đo độ trễ | `perception/export_onnx.py` | Khớp PyTorch 99,9999 % pixel |
| Nguồn camera phát lại (thư mục ảnh, file video) và khung `UsbCameraSource` | `video/sources.py` | Hai nguồn phát lại có test; USB thử thiết bị thật ngày 23/09 ([GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md)) |
| Nguồn LiDAR phát lại DROW v2 theo hợp đồng `LidarScan` | `lidar/drow.py` | Có test; đọc được 113 recording |
| Vẽ scan (OpenCV) và widget Qt + trình phát lại | `lidar/render.py`, `ui/scan_view.py`, `lidar/viewer.py` | Test offscreen |
| Giám sát dữ liệu cũ/mất/không hợp lệ cho mọi nguồn | `safety/freshness.py` | Có test; dùng trong trình phát lại |

Cùng ngày, nhánh LiDAR thật (driver RPLIDAR C1 trên COM4, ghi/phát lại phiên, bench, bản đồ lưới tĩnh) được làm ở [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) và dùng lại các khối ở đây. Chưa làm: hợp nhất nhiều camera, hợp nhất LiDAR–camera, SLAM/định vị, mọi thứ liên quan ESP32.

*Cập nhật 24/09/2026:* danh sách "chưa làm" ở trên là tình trạng ngày 22/09. Sau đó: lớp và quy tắc hợp nhất LiDAR/camera/ToF bằng phần mềm có từ cùng ngày 22/09 ở [GIAI_DOAN_3_CHUAN_BI.md](GIAI_DOAN_3_CHUAN_BI.md), nhưng lớp camera chưa có khung hình camera thật nào đi qua; bàn thử chỉ ghép bộ ảnh bốn camera theo thời gian ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md)), chưa chiếu kết quả AI xuống sàn, chưa ghép bốn camera hay hợp nhất với LiDAR trên dữ liệu thật; giao thức laptop–ESP32-S3, `VehicleIO` và firmware có từ 24/09 ở [GIAO_THUC_XE.md](GIAO_THUC_XE.md) (phần mềm và mô phỏng, mã C++ chưa biên dịch, chưa có bo); SLAM/định vị vẫn chưa làm.

*Cập nhật 25/09/2026* (mã dưới đây đã commit và push, `origin/main` = `54cb3e2`): nay đã có (1) mã BEV chiếu và gộp xác suất AI của nhiều camera xuống lưới mặt sàn hệ xe (`perception/bev.py`, commit `1d2b857`, [BEV.md](BEV.md)), mới kiểm trên rig bốn camera ảo và ảnh WoodScape, chưa chạy với hiệu chuẩn thật trên camera dự án (mới chạy thử bộ lọc khung hỏng trên hai bộ ảnh thật với nội tham danh định, kết quả BEV không có nghĩa; [BEV.md](BEV.md) mục 6) và chưa nối vào hợp nhất hay planner; (2) định vị một vòng quét trên bản đồ tĩnh (`lidar/localize.py`, commit `b100a5d`) và odometry khớp scan (`lidar/scan_odometry.py`, commit `a7cec5e`), chỉ chạy offline trên bản ghi, chưa có tham chiếu độc lập ([DINH_VI_LIDAR.md](DINH_VI_LIDAR.md), [SO_SANH_DINH_VI_SLAM.md](SO_SANH_DINH_VI_SLAM.md)); (3) `VehicleIO` nối vào phiên đỗ xe và chế độ quan sát (commit `c43e8d3`, [CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md)), vẫn chỉ với bo mô phỏng và cổng serial giả.

## 2. Calibration WoodScape — vì sao tin được

Quy ước lấy từ `readme.txt` nằm **bên trong** `datasets/woodscape_metadata/calibration.zip` (README ngoài chỉ dẫn link): `rho(θ) = k1θ + k2θ² + k3θ³ + k4θ⁴` (pixel, θ tính bằng radian từ trục quang); tâm ảnh `width/2 − 0,5 + cx_offset`, `height/2 − 0,5 + cy_offset`; `aspect_ratio` chỉ nhân thành phần dọc; quaternion thứ tự `(x, y, z, w)` quay **camera → xe**; hệ xe ISO 8855 (x trước, y trái, z lên, gốc trên mặt đất dưới tâm trục sau) — trùng quy ước của dự án. Hệ camera OpenCV (X phải, Y xuống, Z trục quang).

Ba kiểm chứng (`runs/perception_integration/calibration_convention_check.json`, `runs/perception_integration/ipm_check_*.jpg`; `runs/` ngoài Git, chép cả thư mục dự án thì mới có):

1. Trục quang bốn camera tính ra trong hệ xe: FV (0,92; 0; −0,40) — trước, chúc xuống 23°; RV (−0,66; 0; −0,75); MVL (−0,08; +0,23; −0,97) với vị trí y = +0,99 m (trái); MVR y = −0,96 m. Đọc theo chiều ngược lại (xe → camera) cho camera trước chĩa sang trái — vô lý.
2. Lưới mặt đất 1 m chiếu vào ảnh FV bám đúng mặt đường (vạch hội tụ về chân trời, vòng gần khớp mép nắp ca-pô).
3. `pixel_to_ground(ground_to_pixel(p)) = p` sai số 0 trên 180 điểm của 4 camera.

Phát hiện phụ (do agent đọc toàn bộ 8.234 file): **calibration khác nhau giữa các recording** (31–32 bộ riêng mỗi camera, hai cụm vị trí lắp), nên phải nạp theo từng ảnh; `aspect_ratio` lệch tối đa 6·10⁻⁴; **bốn file** `06418_MVR, 06419_RV, 06423_MVR, 06424_RV` mang ngoại tại của camera trước dù tên là hông/sau (lỗi dữ liệu gốc). `vehicle_info.zip` là telemetry CAN, không có kích thước xe.

## 3. ROI và costmap

**ROI** (`python -m autopark.perception.roi build`): rasterize polygon `ego_vehicle` đúng z-order như bộ sinh nhãn gốc (lần đầu vẽ polygon thô cho ra RV bị loại 99 % — sai; sau khi theo z-order còn 61 %), lấy tần suất trên tập train, loại pixel có tần suất ≥ 0,2 (bảo thủ) hoặc gần đen ≥ 95 % ảnh. Kết quả loại: FV 48,8 %, MVL 48,4 %, MVR 48,8 %, RV 61,4 % diện tích ảnh — phần lớn là thân xe và viền ngoài vòng ảnh của ống kính. Đây là ROI của rig WoodScape; với camera của dự án phải dựng lại từ vài mặt nạ vẽ tay, cùng định dạng file.

**Costmap** (`python -m autopark.perception.costmap`, ROI mặc định `configs/roi/woodscape_v1`; chạy `--no-roi` thì costmap bị đóng dấu không hợp lệ vì pixel thân xe mang nhãn vô nghĩa): mỗi tâm ô lưới được chiếu *vào ảnh* (chỉ dùng phép chiếu thuận, không nghịch đảo đa thức) và lấy nhãn pixel; IGNORE / ngoài ảnh / ngoài ROI → **UNKNOWN**; quét che khuất theo góc phương vị: sau ô OCCUPIED gần nhất, mọi ô xa hơn trong góc mà ô đó chiếm → UNKNOWN (vật cao chỉ đánh dấu chân, không "kéo vệt" ra xa; phần sàn bị che không bị ghi là FREE); ngoài `max_range` → UNKNOWN. Giả định mặt sàn phẳng z = 0. Bố cục: `cells[row][col]`, row theo y từ `origin.y` (trái +), col theo x từ `origin.x` (trước +), `origin = Pose(x_min, y_min, 0)`.

Trên ảnh `00007_FV` (lưới 25 × 20 m, 0,1 m, tầm 12 m): 14.511 ô FREE, 36 ô OCCUPIED (chân vật cản), 35.453 ô UNKNOWN. Hình `runs/perception_integration/costmap_00007_FV/costmap_textured.png` (ngoài Git) cho thấy mặt đường phía trước là FREE, chân xe đỗ/người đi bộ hai bên là OCCUPIED, phía sau chúng xám. **Chưa có cách đo sai số costmap bằng tham chiếu độc lập** — đó là việc của giai đoạn 2–3 với vật mẫu có tọa độ đo được.

## 4. Nguồn dữ liệu phát lại và giám sát dữ liệu cũ

- `video/sources.py`: `ImageSequenceSource` (thứ tự tự nhiên theo tên, thời gian = t0 + chỉ số/fps), `VideoFileSource` (một đồng hồ cho cả file: vị trí trong video nếu tăng nghiêm ngặt, không thì chỉ số/fps; stamp không bao giờ lặp hay lùi), `UsbCameraSource` (OpenCV, DirectShow trên Windows; mode đưa vào ngay lúc mở; stamp lấy ngay sau `read()` (đã gồm giải mã); yêu cầu hàng đợi driver 1 khung, DirectShow có nhận hay không ghi ở `buffer_size_applied`; khung trùng byte bị coi là lỗi đọc; `mode()` ghi kích thước thực còn fourcc/fps là yêu cầu — sửa 23/09 theo [GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md); từ chiều 23/09 khung MJPEG bị cắt cụt hoặc có dải xé cũng bị loại bằng `FrameReadError` và đếm riêng, xem [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 2) — cùng giao diện `read() -> Frame(meta: CameraFrame, image)`; nguồn phát lại trả `None` khi hết, nguồn trực tiếp ném `FrameReadError` khi một lần đọc hỏng. USB đã chạy trên camera thật ngày 23/09 (`camera_bench source`); `read()` treo vẫn chặn vòng lặp nên `check()` của bộ giám sát phải chạy từ timer riêng.
- `lidar/drow.py`: CSV 452 cột (seq, thời gian, 450 range), 224,5° bước 0,5°, chỉ số 0 = góc âm nhất (bên phải) theo loader v2 của tác giả — README gốc lại nói "giá trị đầu bên trái"; có tham số `mirror`, **phải đối chiếu với thiết bị thật trước khi tin chiều**. Range ≥ 29,9 m → NaN (tác giả ghi 29,96 là N/A; 29,98/29,99 cũng xuất hiện). Nhãn `.wp/.wc/.wa`: danh sách rỗng ≠ thiếu nhãn.
- Kiểm tra chiều góc trên dữ liệu thật: khung `seq 9891` của `run_2015-11-25-10-34-20-a` có nhãn người tại r = 0,63 m, φ = −1,89 rad; vòng tròn nhãn (dùng φ của tác giả) trùm đúng cụm điểm quét (dùng ánh xạ chỉ số → góc của module) — xem `runs/perception_integration/drow_scan_person.png` (ngoài Git). Vậy ánh xạ chỉ số theo loader v2 nhất quán với nhãn; chiều trái/phải so với thế giới thật vẫn phải kiểm tra bằng thiết bị.
- `safety/freshness.py`: mỗi nguồn có `max_age_s`, chu kỳ mong đợi; `observe(stamp, now)` từ chối mẫu không hợp lệ / lùi thời gian / ở tương lai (`CLOCK_SKEW`) / đã quá tuổi ngay lúc đến (`STALE_ON_ARRIVAL`); `check(now)` phát `SafetyEvent` `NO_DATA` / `STALE_DATA` / `CLOCK_SKEW` (action STOP). Một vòng review độc lập (4 agent, 22/09) đã chỉ ra và được sửa: stamp USB lấy sau khi giải mã, mẫu cũ lúc đến vẫn được nhận, sắp xếp tên file theo chuỗi, cờ `mirror` không áp cho nhãn, hợp đồng `LidarScan` nhận range âm. Trình phát lại `python -m autopark.lidar.viewer <csv> --labels wp`: nhấn Space tạm dừng → sau 0,3 s tiêu đề đổi màu và trạng thái báo `STALE_DATA` — cách thử logic "dữ liệu cũ thì không dùng" không cần cảm biến.

## 5. ONNX và độ trễ

`python -m autopark.perception.export_onnx`: đồ thị ONNX (opset 17, exporter TorchScript) nhận tensor chuẩn hóa (1, 3, 384, 512), trả logits. Đối chiếu 16 ảnh val bằng onnxruntime CPU: lệch logit tối đa 7·10⁻⁵, trùng argmax 99,9999 %. Độ trễ một ảnh **trên máy này**, GPU rảnh (p50, 200 lượt): onnxruntime CPU fp32 7,6 ms; torch CUDA fp32 4,4 ms; fp16 5,5 ms; đầu-cuối từ ảnh 1280×966 (letterbox → mạng → softmax về CPU) 7,8 ms — lúc GPU bận huấn luyện các số này cao gấp 2–3 lần. Chi tiết ở `runs/ai_woodscape_rtx4000_v1/export/export_report.json`. Script tự sinh ảnh nhiễu khi không có dataset, nên chạy được trên máy khác chỉ với `best.pt`. Chưa đo trên laptop i7-12700H + RTX 3050 Ti, máy mang đi nộp đồ án; chạy cùng lệnh trên đó. *Cập nhật 24/09/2026, người dùng xác nhận:* máy bàn i9-14900 + RTX 4000 Ada là máy phát triển chính; laptop i7-12700H + RTX 3050 Ti (4 GB VRAM) là máy mang đi nộp và trình diễn đồ án. Mọi số đo đến nay là trên máy bàn; số dùng cho khóa luận phải đo lại trên laptop. Máy bàn trong mục này là máy dùng tới 25/09/2026; từ 29/09/2026 máy bàn là Dell Precision 3680 cùng cấu hình ([chuyển máy](CHUYEN_MAY_BAN.md)).

## 6. Cách chạy

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

1. Cài driver CP210x (Silicon Labs) → cổng COM → viết driver RPLIDAR C1 (UART 460800, giao thức SLAMTEC) theo hợp đồng `LidarScan`, ghi phiên đo, so với DROW replay.
2. Khi có camera mẫu: `UsbCameraSource` + `mode()` để liệt kê mode thật; chụp ảnh sa bàn; chạy `predict.py` để đo độ lệch miền trước khi gán nhãn.
3. Hiệu chuẩn camera của dự án (OpenCV fisheye) và ghi calibration cùng định dạng JSON WoodScape để `costmap.py` dùng lại nguyên vẹn.
4. Định nghĩa `UNKNOWN` cho costmap hợp nhất (LiDAR + camera + ToF) và cách tham chiếu độc lập để đo sai số BEV (kế hoạch mục 6).

*Cập nhật 24/09/2026 — tình trạng bốn việc trên:* (1) driver RPLIDAR C1, ghi/phát lại phiên và phiên đo tĩnh đã làm ngày 22/09 ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md)); còn thiếu các lần đặt hộp để đo sai số khoảng cách. (2) Camera: liệt kê mode thật và đo trên máy bàn ngày 23/09 bằng `video/camera_bench.py` ([GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md)); chưa chụp ảnh sa bàn, chưa đo độ lệch miền trên ảnh sa bàn. (3) Mã đã có từ 24/09: `perception/calib_board.py` (bảng ô vuông để in: PDF, PNG và JSON mô tả bảng), `perception/fisheye_calib.py` (`cv2.fisheye.calibrate`, chuyển sang mô hình đa thức dạng WoodScape `FisheyeIntrinsics` có báo sai số khớp, ghi một tệp JSON cho mỗi camera, khóa theo cổng hub) và giao diện chụp `ui/calib_app.py`; mới kiểm bằng ảnh bảng tổng hợp và camera giả (`tests/test_fisheye_calib.py`, `tests/test_calib_app_ui.py`). Tệp hiệu chuẩn là JSON riêng của dự án (`autopark.fisheye_intrinsics/1`) có một khối nội tham dạng WoodScape, không phải tệp calibration WoodScape đầy đủ: chỉ có nội tham, chưa có ngoại tham camera→xe, nên `costmap.py` chưa dùng lại nguyên vẹn được. Chưa hiệu chuẩn camera nào: chưa in bảng, chưa chụp ảnh bảng; các ngưỡng chấp nhận trong mã mới là đề xuất, chưa kiểm trên camera thật. (4) Quy tắc hợp nhất trong `fusion/fuse.py` giữ ô không có lớp tươi nào là `UNKNOWN` ([GIAI_DOAN_3_CHUAN_BI.md](GIAI_DOAN_3_CHUAN_BI.md)); cách đo sai số BEV bằng tham chiếu độc lập thì chưa có.

*Cập nhật 25/09/2026:* (3) ngoại tham camera→xe nay có công cụ (`perception/extrinsics_calib.py`, commit `65b7127`, [NGOAI_THAM_VA_ROI.md](NGOAI_THAM_VA_ROI.md)). BEV ghép nội tham `cam_p<N>.json` với ngoại tham bằng `bev.load_rig()` và dùng cùng phép chiếu với `costmap.project_labels`, nên không cần tệp calibration WoodScape đầy đủ ([BEV.md](BEV.md)). Vẫn chưa có tệp nội tham, ngoại tham hay ROI nào của camera thật. (4) Cách đo sai số BEV bằng vật mẫu đặt ở vị trí đo bằng thước đã được viết thành đề xuất ([BEV.md](BEV.md) mục 8; [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 5.4, bản nháp), chưa làm.
