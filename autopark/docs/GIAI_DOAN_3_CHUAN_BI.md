# Giai đoạn 3 — phần làm được khi chưa có IMU, ToF hoặc ESP32 (22/09/2026)

**Kế hoạch đối chiếu:** [v3.1, mục 7 "Khi chưa có IMU, ToF hoặc ESP32"](../../KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md).
**Mức bằng chứng:** phần mềm + test tổng hợp; một đầu vào thật duy nhất là RPLIDAR C1 đứng yên trên bàn (qua `fusion/demo.py`). Chưa có IMU, ToF, ESP32, rig hay xe; **không có số đo ToF/IMU thật nào** được đọc.

## 1. Đã làm gì

| Mục trong kế hoạch | Cài đặt | Kiểm chứng |
|---|---|---|
| Các lớp `StaticMap`, `LiveLidar`, `CameraSemantic`, `NearField` với trạng thái hợp lệ/cũ | `fusion/layers.py`: mỗi lớp giữ một `Costmap` trong hệ bản đồ + `SourcePolicy` tuổi tối đa; lớp tĩnh không hết hạn | `tests/test_fusion.py` |
| Telemetry giả cùng cấu trúc dữ liệu thật | `NearFieldReading(stamp, sensor_id, range_m, max_range_m, valid)`; số đo không hợp lệ → không có ô nào, lớp không tươi | test: đọc hợp lệ đánh dấu một cung nhỏ; đọc không hợp lệ làm bản đồ hợp nhất không hợp lệ; không bao giờ sinh FREE |
| Phép biến đổi rig–map, thử bằng vị trí biết trước | `sensor_pose_in_map(vehicle_pose, mount)`; `resample(costmap, grid, pose)` đưa costmap hệ xe (camera) vào hệ bản đồ | test với xe ở (1; 0,5) quay 90°, cảm biến lệch 0,1 m: vật 0,98 m trước cảm biến rơi đúng ô (1; 1,58) |
| Hợp nhất | `fusion/fuse.py`: OCCUPIED nếu bất kỳ lớp tươi nào OCCUPIED, FREE nếu có lớp tươi FREE, còn lại UNKNOWN; lớp bắt buộc không tươi → `stamp.valid = False`, mọi ô bị chặn, có lý do | test quy tắc từng ô, lớp cũ, lớp tùy chọn, lưới khác nhau |
| Đường đang hợp lệ → thêm vật cản → hủy hợp lệ → dừng → lập lại hoặc chờ | `fusion/obstacles.py` (ô bị chặn → hình chữ nhật phủ chính xác; chỉ thông tin mới) + `fusion/bridge.py` (`sync` khi chỉnh sa bàn, `inject` khi chạy, dừng khi bản đồ không hợp lệ) nối vào `Session` giai đoạn 0 | test: vật 0,6 m trước xe đang chạy → STOPPING → STOPPED, không va chạm, `MAP_CHANGED`, `WAIT_REPLAN`, lập lại đường được; mất LiDAR → dừng với lý do; vật ngoài hành lang → ghi nhớ, không dừng |
| Lưu/nạp bản đồ | `read_costmap_json` / `write_costmap_json`; lớp tĩnh nạp `costmap.json` của `lidar/occupancy.py` | test vòng tròn ghi → nạp bằng nhau |
| Thử trên bàn với LiDAR thật | `fusion/demo.py` (dòng lệnh) và `ui/lidar_dock.py` (giao diện): LiDAR ở COM4 đứng yên tại vị trí xuất phát → sa bàn 3 × 2 m → xe ảo lập đường quanh đồ vật thật rồi chạy; đưa tay vào trước LiDAR → dừng | `tests/test_fusion_demo.py`, `tests/test_lidar_dock_ui.py` với nguồn quét kịch bản; chạy thật: mục 3 |
| Bản đồ bám cảm biến theo thời gian thực | `bridge.sync_incremental`: giữ hộp còn bị chặn, bỏ hộp đã trống, thêm hộp mới sau mỗi vòng quét; bản đồ hợp nhất không hợp lệ thì KHÔNG đổi gì (không có bằng chứng ≠ trống) | test: vật đổi góc → hộp cũ bị xóa, hộp mới thêm, id không trùng; hết vật → sa bàn trống; sau khi lập đường thì `sync_incremental` ném lỗi |

14 test mới (`test_fusion.py` 11, `test_fusion_demo.py` 3). Bộ test toàn dự án sau khi thêm: 284 đạt, 4 bỏ qua trong 54 s (`.venv`, máy rảnh).

## 2. Năm quy tắc rút ra từ việc chạy với LiDAR thật

Mỗi quy tắc dưới đây được thêm sau một lần xe ảo dừng giả trên cảnh tĩnh của bàn làm việc; thứ tự là thứ tự phát hiện.

1. **Bền vững theo vòng quét.** Lớp `LiveLidar` chỉ coi ô là OCCUPIED khi bị chạm ở ≥ 2 trong 3 vòng gần nhất (đếm vòng, không đếm tia); ô bị chạm 1 lần là UNKNOWN, không bao giờ FREE. Trả giá: trễ thêm một vòng (≈ 0,1 s). Ô mới sát vật đã biết trong 1 ô không tính là thông tin mới.
2. **Mặt nạ thân xe và vùng mù.** Tia có điểm chạm trong thân xe nới 10 cm, hoặc dưới 0,05 m, bị bỏ (thành NaN). Trên bàn, bo adapter cách LiDAR 9 cm từng rơi vào thân xe ảo và làm "xuất phát không hợp lệ".
3. **Hành lang quỹ đạo.** Khi đang chạy chỉ vật mới chạm hành lang thân xe nới 10 cm dọc phần quỹ đạo còn lại mới làm dừng; vật mới ngoài hành lang được ghi nhớ (`bridge.seen`) và đưa vào sa bàn ở lần `sync` sau. Không có quy tắc này, vài ô lẻ tẻ cách đường 40 cm trở lên vẫn dừng xe trong vòng một giây.
4. **Không chụp bản đồ một lần.** Bản "quét nền" (gộp N vòng rồi giữ nguyên) làm người dùng xoay LiDAR mà sa bàn vẫn là cảnh cũ. Bỏ hẳn: khi đang chỉnh sa bàn, mỗi vòng quét đồng bộ lại các hộp (`sync_incremental`); khi đã lập đường thì bản đồ được chốt, vì planner và bộ bám đường cần một bản đồ đứng yên. Đổi cấu hình LiDAR hay ngắt kết nối trong lúc chạy → yêu cầu dừng, và các ô chỉnh bị khóa khi xe đang chạy.
5. **Cảm biến cố định thì tư thế cố định.** LiDAR trên bàn không chuyển động theo xe ảo; gán nó vào xe ảo đang chạy làm cả cảnh dịch theo xe và mọi mép vật thành "vật mới". Demo dùng LiDAR như cảm biến cố định tại vị trí xuất phát. Ngoài ra: bỏ 15 vòng đầu (mô-tơ C1 còn tăng tốc, mật độ tia đổi từng vòng), bản đồ nền là hợp của 10 vòng kế tiếp, và xả bộ đệm LiDAR sau khi lập đường (dữ liệu tồn đọng sẽ mang stamp mới dù đã cũ).

## 3. Kết quả chạy thật trên bàn (22/09/2026, COM4)

| Cấu hình | Kết quả |
|---|---|
| Không quy tắc nào | dừng ngay vòng quét đầu sau xuất phát: 3 "vật mới" từ nhiễu |
| + bền vững 2/3, lề 1 ô | vẫn dừng ngay: 3 vật mới |
| + mặt nạ thân xe | lập đường được, dừng ở 6,8 s: 9 vật mới, có ô cách đường ≥ 40 cm |
| + hành lang quỹ đạo | dừng ở 6,8 s vì 2 ô trên đường (cáp cạnh LiDAR, mép vật); 3 vật ngoài đường bị bỏ qua đúng |
| + LiDAR cố định tại xuất phát, nền = hợp 10 vòng (bản dòng lệnh) | **COMPLETED**: 20 vật cản có sẵn, xe ảo lập đường quanh chúng và đỗ xong, 202 vòng quét, 0 lỗi đọc, 0 dừng giả, 2 vật mới ngoài đường được bỏ qua |

Chưa thử: đưa tay/hộp vào trước LiDAR trong lúc xe ảo chạy (cần người); rút cáp trong lúc chạy (kỳ vọng dừng với lý do "bản đồ hợp nhất không hợp lệ", đã có test với nguồn giả).

## 3b. Kiểm toán độc lập "vì sao số vật cản khác số vật" (22/09/2026, 45 agent, 21 phát hiện, 12 được xác nhận)

Câu hỏi của người dùng: LiDAR thấy nhiều hơn / số vật cản trên sa bàn nhiều hơn số đồ vật. Đo trên bản ghi p07 (cùng bàn): một vòng 352 phản hồi → 221 rơi trong sa bàn 3 × 2 m → 101 sau mặt nạ thân xe (120 điểm là bo adapter, dây cáp, mép bàn sát cảm biến) → gộp 10 vòng thành 67 ô 5 cm = 18 cụm vật nhưng 33 hình chữ nhật (11 hình chỉ một ô). Kết luận đã được phản biện xác nhận:

| Phát hiện | Xử lý |
|---|---|
| Số "vật cản" là số hình chữ nhật phủ chính xác, không phải số vật; phủ hình chữ nhật không phình (0 cặp gộp được), 33 là giá của bậc thang ở 5 cm | Giữ phủ chính xác (bao hộp theo cụm sẽ nuốt thêm 48 ô trống, bằng 3 thân xe). Thêm `count_objects` (cụm 8 lân cận) và nhãn "X vật thể, chia thành Y hộp"; điểm LiDAR thô vẽ thẳng lên sa bàn (vàng = dùng được, nâu = bị mặt nạ bỏ) |
| Hình quét vẽ phía trước lên trên, sa bàn vẽ phía trước sang phải: hai hình lệch nhau 90°, không có dấu hiệu hướng | `ScanView(front_up=False)` trong ngăn LiDAR (cùng hướng sa bàn), mũi tên "trước" trên hình quét, mũi tên hướng LiDAR tại điểm xuất phát trên sa bàn |
| Lề mặt nạ thân xe 10 cm làm vật cách thân xe dưới 10 cm thành "không có phản hồi" thay vì bị chặn; khoảng hở lúc xuất phát là do mặt nạ tạo ra | Lề thành tham số trên giao diện ("cm quanh xe bỏ", mặc định 10 vì bàn thử có adapter sát cảm biến; trên xe thật đặt 3 cm = lề an toàn của planner). Vật thử phải đặt cách LiDAR ≥ 40 cm |
| Bản đồ nền gộp 10 vòng với "thấy 1 lần là chặn": 29 % ô là nhiễu chớp tắt (6 ô chỉ thấy 1/10 vòng) | `ScanUnion` đếm theo VÒNG (không theo tia) với tham số "lần thấy mới tính", mặc định 2 |
| Ô "Đảo chiều góc" im lặng khi phát lại bản ghi và không làm mất hiệu lực bản đồ nền đã quét | Báo rõ khi phát lại; khi đổi chiều lúc đang chỉnh sa bàn thì xóa vật LiDAR và yêu cầu quét nền lại |
| Sa bàn có cạnh không chia hết cho 5 cm làm `GridSpec` ném lỗi trong timer 50 ms | `_bounds_grid` cắt xuống bội số 5 cm |
| Bộ đếm id vật cản tăng theo mọi ứng viên nên có thể trùng id ở lần chèn sau | Chỉ đánh số vật thực sự đưa vào sa bàn (`_numbered`), có test id không trùng |
| Chưa xác minh dấu góc (trái/phải) bằng vật thật; sai dấu sẽ lật trái/phải ở CẢ hai hình nên không tự phát hiện được | Vẫn cần lần đặt hộp bên trái (p04); ghi ở GIAI_DOAN_1_LIDAR.md |
| Chi phí `check_motion` với shapely tăng tuyến tính theo số hình chữ nhật (191 µs với 33 hình, mỗi bước 5 ms) | Chấp nhận ở quy mô bàn thử; khi quét cả phòng cần STRtree/union trong `footprint._evaluate` |

Sau khi sửa, chạy lại demo trên bàn: 28 vật cản nền, planner báo đích (2,0; 1,0) trúng vật thật ở khoảng 1,9–2,05 m trước cảm biến, đúng với đồ trên bàn; trong giao diện chỉ cần kéo đích sang chỗ trống.

## 4. Quy ước

- Hệ bản đồ = hệ sa bàn giai đoạn 0. Lưới `cells[row][col]`, row theo y, col theo x, cùng bố cục `perception/costmap.py`.
- Tư thế cảm biến trong hệ xe `(x, y, yaw)`, gốc xe tại tâm trục sau.
- `Obstacle.kind` chỉ nhận `box | car | wall | unknown`: vật cản từ bản đồ mang `kind="box"` (OCCUPIED) hoặc `"unknown"`; cầu nối nhận ra vật của mình qua tiền tố id (`lidar_00012`).
- Vật cản là phủ hình chữ nhật chính xác của ô bị chặn; tường xiên thành bậc thang nhiều hình nhỏ. Đúng nhưng chưa đo tốc độ planner với hàng trăm hình.

## 5. Cách chạy

Giao diện (khuyên dùng): cửa sổ đỗ xe giai đoạn 0 có thêm ngăn LiDAR bên phải (`ui/lidar_dock.py`, `ui/lidar_app.py`). **Bản đồ là thời gian thực, không có bước "quét nền"**: vừa kết nối là các hộp trên sa bàn đã bám theo LiDAR, xoay cảm biến hay dời đồ vật thì hộp đi theo trong vòng vài trăm mili giây. Trình tự: **Kết nối** → nhìn sa bàn khớp với thực tế (chỉnh "vòng gộp", "lần thấy mới tính", "cm quanh xe bỏ" nếu cần) → **Tìm đường đỗ** (bản đồ được CHỐT tại đây để lập đường) → **Bắt đầu đỗ** → đưa tay vào trước LiDAR cách ≥ 40 cm: xe ảo dừng, ngăn LiDAR ghi "Vật mới trên đường". Rút cáp khi đang chạy: xe dừng với lý do mất LiDAR. Test chạy ẩn: `tests/test_lidar_dock_ui.py` (5 test).

```powershell
# trong thư mục autopark, .venv
.\.venv\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app --port COM4
.\.venv\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app --recording runs/lidar_bench/20260922/p07_nen_phong.npz
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_fusion.py tests/test_fusion_demo.py
.\.venv\Scripts\python.exe -X utf8 -m autopark.fusion.demo --port COM4 --seconds 30      # đưa tay vào trước LiDAR lúc xe chạy
.\.venv\Scripts\python.exe -X utf8 -m autopark.fusion.demo --recording runs/lidar_bench/20260922/p07_nen_phong.npz --seconds 10
```

## 6. Chưa làm / giới hạn

- Chưa có ESP32, IMU, ToF: `NearFieldLayer` mới chạy với số đo giả; không ghi nhận "ToF thật đã hoạt động".
- `CameraSemanticLayer` mới có phép đặt costmap camera vào bản đồ; chưa có khung hình camera thật đi qua.
- Chưa có định vị: tư thế xe lấy từ mô phỏng; LiDAR thật đứng yên.
- Không có bộ nhớ thời gian trong hợp nhất (mỗi lần gọi là ảnh chụp); lớp LiDAR trực tiếp giữ 3 vòng gần nhất.
- Giao diện dùng bản đồ thời gian thực (3 vòng gần nhất, ô phải thấy ≥ 2 vòng); `fusion/demo.py` dòng lệnh vẫn dùng bản chụp 10 vòng đầu vì nó chạy không có người ngồi trước màn hình.
- Bản đồ chốt lúc lập đường: vật xuất hiện giữa lúc lập đường và lúc bấm chạy chỉ được phát hiện khi xe đã chạy.
- Hiệu năng planner với hàng trăm hình chữ nhật chưa đo; cần bộ kiểm tra va chạm theo lưới nếu chậm.
