# Giai đoạn 3 — phần làm được khi chưa có IMU, ToF hoặc ESP32 (22/09/2026)

**Kế hoạch đối chiếu:** [v3.1 bản `9d68257`, mục 7 "Khi chưa có IMU, ToF hoặc ESP32"](https://github.com/thbn12082/autopark/blob/9d68257/KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md). *(Cập nhật 30/09/2026: [bản hiện tại](../../KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) giữ mục 7, đoạn tương ứng là "Khi chờ".)*
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
| Thử trên bàn với LiDAR thật | `fusion/demo.py` (dòng lệnh) và `ui/lidar_dock.py` (giao diện): LiDAR đứng yên tại vị trí xuất phát → sa bàn 3 × 2 m → xe ảo lập đường quanh đồ vật thật rồi chạy; vật mới trên đường → dừng. Cổng LiDAR: COM4 trên máy bàn tới 25/09/2026; trên máy bàn từ 29/09/2026 lấy từ `configs/thiet_bi.json`, hiện COM3 ([chuyển máy](CHUYEN_MAY_BAN.md)) | `tests/test_fusion_demo.py`, `tests/test_lidar_dock_ui.py` với nguồn quét kịch bản; chạy thật: mục 3 (đỗ xong quanh đồ vật thật; **chưa thử** đưa tay hay rút cáp khi xe ảo đang chạy) |
| Bản đồ bám cảm biến theo thời gian thực | `bridge.sync_incremental`: giữ hộp còn bị chặn, bỏ hộp đã trống, thêm hộp mới sau mỗi vòng quét; bản đồ hợp nhất không hợp lệ thì KHÔNG đổi gì (không có bằng chứng ≠ trống) | test: vật đổi góc → hộp cũ bị xóa, hộp mới thêm, id không trùng; hết vật → sa bàn trống; sau khi lập đường thì `sync_incremental` ném lỗi |

14 test mới (`test_fusion.py` 11, `test_fusion_demo.py` 3). Bộ test toàn dự án sau khi thêm: 284 đạt, 4 bỏ qua trong 54 s (`.venv`, máy rảnh). *Cập nhật 24/09/2026: cả hai số trên đều không mô tả bản đã commit. So với commit cha `e845f60`, commit `6dba1a6` (22/09) thêm 22 test: `test_fusion.py` 14, `test_fusion_demo.py` 3, `tests/test_lidar_dock_ui.py` 5. Ngày 24/09 đã chạy lại toàn bộ test trên bản xuất ra từ đúng hai commit này (`git archive`, `.venv`, `QT_QPA_PLATFORM=offscreen`): `e845f60` cho 270 đạt, 4 bỏ qua; `6dba1a6` cho 292 đạt, 4 bỏ qua (4 mô-đun cần torch bị bỏ qua cả mô-đun). Vì 284 = 270 + 14, lượt chạy 284/4 có lẽ là trên cây làm việc trước khi thêm 3 test fusion và 5 test giao diện cuối; không còn nhật ký của lượt chạy đó nên không kiểm được.*

## 2. Năm quy tắc rút ra từ việc chạy với LiDAR thật

Mỗi quy tắc dưới đây được thêm sau một lần xe ảo dừng giả trên cảnh tĩnh của bàn làm việc; thứ tự là thứ tự phát hiện.

1. **Bền vững theo vòng quét.** Lớp `LiveLidar` chỉ coi ô là OCCUPIED khi bị chạm ở ≥ 2 trong 3 vòng gần nhất (đếm vòng, không đếm tia); ô bị chạm 1 lần là UNKNOWN, không bao giờ FREE. Trả giá: trễ thêm một vòng (≈ 0,1 s). Ô mới sát vật đã biết trong 1 ô không tính là thông tin mới.
2. **Mặt nạ thân xe và vùng mù.** Tia có điểm chạm trong thân xe nới 10 cm, hoặc dưới 0,05 m, bị bỏ (thành NaN). Trên bàn, bo adapter cách LiDAR 9 cm từng rơi vào thân xe ảo và làm "xuất phát không hợp lệ".
3. **Hành lang quỹ đạo.** Khi đang chạy chỉ vật mới chạm hành lang thân xe nới 10 cm dọc phần quỹ đạo còn lại mới làm dừng; vật mới ngoài hành lang được ghi nhớ (`bridge.seen`) và đưa vào sa bàn ở lần `sync` sau. Không có quy tắc này, vài ô lẻ tẻ cách đường 40 cm trở lên vẫn dừng xe trong vòng một giây.
4. **Không chụp bản đồ một lần.** Bản "quét nền" (gộp N vòng rồi giữ nguyên) làm người dùng xoay LiDAR mà sa bàn vẫn là cảnh cũ. Bỏ hẳn: khi đang chỉnh sa bàn, mỗi vòng quét đồng bộ lại các hộp (`sync_incremental`); khi đã lập đường thì bản đồ được chốt, vì planner và bộ bám đường cần một bản đồ đứng yên. Đổi cấu hình LiDAR hay ngắt kết nối trong lúc chạy → yêu cầu dừng, và các ô chỉnh bị khóa khi xe đang chạy.
5. **Cảm biến cố định thì tư thế cố định.** LiDAR trên bàn không chuyển động theo xe ảo; gán nó vào xe ảo đang chạy làm cả cảnh dịch theo xe và mọi mép vật thành "vật mới". Demo dùng LiDAR như cảm biến cố định tại vị trí xuất phát. Ngoài ra: bỏ 15 vòng đầu (mô-tơ C1 còn tăng tốc, mật độ tia đổi từng vòng), bản đồ nền là hợp của 10 vòng kế tiếp *(đúng với lần chạy thật 22/09/2026 ở mục 3; muộn tối 24/09/2026 demo dòng lệnh đổi sang bỏ ≥ 22 vòng, tùy chọn chờ thêm `--warmup` giây, xem ghi chú ngay dưới danh sách; CHƯA chạy với C1 thật)*, và xả bộ đệm LiDAR sau khi lập đường (dữ liệu tồn đọng sẽ mang stamp mới dù đã cũ).

*Cập nhật 24/09/2026: đo lại số tia/vòng trên ba bản ghi cùng driver (p07_nen_phong và live_headless ngày 22/09, k01_kiem_suc_khoe ngày 24/09; với k01 đã tính cả 11 vòng bỏ khi làm nóng). Trong chính 10 vòng dùng làm nền (vòng 16–25), số tia/vòng vẫn còn đổi từng vòng: đạt đỉnh 536–552 ở vòng 16–17 (≈ 3,7 s sau lệnh SCAN), rồi mới về khoảng ổn định 500–516 từ vòng 21–22 (≈ 4,2 s). Vậy bỏ 15 vòng chưa phủ hết giai đoạn khởi động của mô-tơ. Chưa đo ảnh hưởng của việc này lên bản đồ nền; nếu cần thì tăng `initial_skip` lên khoảng 22 hoặc chờ theo thời gian (≥ 4,5 s sau SCAN). Chi tiết ở [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 3b.*

*Cập nhật muộn tối 24/09/2026 (`fusion/demo.py`; chỉ kiểm bằng nguồn giả, CHƯA chạy với C1 thật).* Demo dòng lệnh nay bỏ vòng khởi động cho tới khi đủ CẢ HAI điều kiện:
- đã bỏ ≥ `--initial-skip` vòng (mặc định 22, trước là 15);
- stamp của vòng ≥ `--warmup` giây trên đồng hồ phiên của nguồn (mặc định 0 = chỉ đếm vòng; đề xuất 4,5). Với driver C1, đồng hồ này tính từ ngay trước lệnh SCAN.

Vòng đầu tiên thỏa cả hai là vòng nền đầu tiên. Tính lại trên ba bản ghi (vòng nền = 10 vòng ngay sau các vòng bỏ):

| Quy tắc | Vòng nền (đếm từ vòng đầu sau SCAN) | Tia/vòng của 10 vòng nền |
|---|---|---|
| bỏ 15 vòng (cũ) | 16–25 | 504–552 (còn đỉnh khởi động) |
| bỏ 22 vòng (mặc định mới) | 23–32 | 500–512 |
| bỏ 22 vòng và `--warmup 4.5` | 25–34 | 500–512 |

Số tia/vòng ổn định trong 500–516 từ vòng 21 (p07) hoặc vòng 22 (live_headless, k01), nên mặc định 22 vòng chỉ dư 1–2 vòng. Chờ theo thời gian là cách an toàn hơn: nó bám theo đại lượng vật lý (thời gian kể từ khi mô-tơ bắt đầu quay), không phụ thuộc tốc độ quay lúc đầu (ở p07 các vòng đầu chỉ dài ≈ 78 ms, vòng thứ 23 đã về lúc ≈ 4,4 s), và trên ba bản ghi cho thêm 2 vòng dự phòng. Nó đã được cài và có test, nhưng chưa làm mặc định: hai test `main()` trong `tests/test_lidar_unplug.py` (không thuộc phần việc này) dùng C1 giả có đồng hồ gần như đứng yên và giả định khởi động xong trước 40 vòng. Đặt `--warmup 4.5` làm mặc định: ĐỀ XUẤT – CHỜ CHỐT, cần sửa hai test đó. Với `--recording`, stamp tính từ vòng đầu của bản ghi chứ không phải từ SCAN, nên `--warmup` chờ lâu hơn cần thiết (thận trọng, không sai). Báo cáo JSON của demo có thêm `warmup`: số vòng bỏ, stamp vòng nền đầu, số tia ít/nhiều nhất của các vòng nền. Nhờ vậy lần chạy thật đầu tiên cho biết ngay vòng nền có nằm trong khoảng ổn định không. Giao diện `ui.lidar_app` không dùng quy tắc này (bản đồ thời gian thực từ 3 vòng gần nhất) và không đổi. Kiểm chứng: 4 test mới trong `tests/test_fusion_demo.py`; kiểm đột biến trên bản sao, 6/6 đột biến bị bắt: bỏ điều kiện thời gian, bỏ điều kiện số vòng, đổi "hoặc" thành "và", đưa mặc định dòng lệnh về 15, không truyền `--warmup`, đưa mặc định của `run_demo` về 15. Ảnh hưởng của vòng khởi động lên bản đồ nền: vẫn CHƯA ĐO.

*Sửa sau rà soát, muộn tối 24/09/2026 (chỉ thử bằng nguồn giả và C1 giả, không mở cổng thật).* Trước đó `--initial-skip -1` hay `--warmup -4.5` (gõ nhầm dấu) chỉ bị `run_demo` từ chối bằng traceback tiếng Anh, và với `--port` thì lúc đó cổng đã mở, lệnh SCAN đã gửi, mô-tơ C1 đã quay. Nay `main()` kiểm hai tùy chọn ngay sau khi đọc dòng lệnh, trước khi mở cổng hay bản ghi: `--initial-skip` âm, `--warmup` âm, NaN hoặc vô cực bị báo lỗi dòng lệnh bằng tiếng Việt, mã thoát 2, không traceback. Vô cực bị loại vì với `--port` nó làm demo bỏ vòng mãi mãi; NaN bị loại vì so sánh với NaN luôn sai nên điều kiện chờ bị bỏ qua. `run_demo` cũng từ chối NaN/vô cực (`ValueError`) trước lần đọc LiDAR đầu tiên. Thêm 3 hàm test (10 trường hợp) trong `tests/test_fusion_demo.py`: nguồn giả ném lỗi test nếu bị đọc, và `RplidarC1Source.open` giả ghi lại nếu bị gọi. Kiểm đột biến trên bản sao, không sửa repo: 6 đột biến mới đều bị bắt (bỏ kiểm ở `main()`; `main()` chỉ loại số âm; `main()` bỏ kiểm `--initial-skip`; bỏ kiểm ở `run_demo`; `run_demo` không loại NaN/vô cực; `run_demo` bỏ kiểm `initial_skip`), 6 đột biến cũ ở trên cũng vẫn bị bắt. `tests/test_lidar_unplug.py` (13 test, hành vi rút cáp) vẫn đạt.

## 3. Kết quả chạy thật trên bàn (22/09/2026, COM4)

| Cấu hình | Kết quả |
|---|---|
| Không quy tắc nào | dừng ngay vòng quét đầu sau xuất phát: 3 "vật mới" từ nhiễu |
| + bền vững 2/3, lề 1 ô | vẫn dừng ngay: 3 vật mới |
| + mặt nạ thân xe | lập đường được, dừng ở 6,8 s: 9 vật mới, có ô cách đường ≥ 40 cm |
| + hành lang quỹ đạo | dừng ở 6,8 s vì 2 ô trên đường (cáp cạnh LiDAR, mép vật); 3 vật ngoài đường bị bỏ qua đúng |
| + LiDAR cố định tại xuất phát, nền = hợp 10 vòng (bản dòng lệnh) | **COMPLETED**: 20 vật cản có sẵn, xe ảo lập đường quanh chúng và đỗ xong, 202 vòng quét, 0 lỗi đọc, 0 dừng giả, 2 vật mới ngoài đường được bỏ qua |

Chưa thử: đưa tay/hộp vào trước LiDAR trong lúc xe ảo chạy (cần người); rút cáp trong lúc chạy (kỳ vọng dừng với lý do "bản đồ hợp nhất không hợp lệ", đã có test với nguồn giả).

*Cập nhật tối 24/09/2026 (chỉ thử với cổng nối tiếp GIẢ trong `tests/test_lidar_unplug.py`; rút cáp C1 thật vẫn CHƯA THỬ). Trong `fusion/demo.py`, lỗi của cổng nối tiếp (rút cáp) nay không còn đi đường "bản đồ hợp nhất không hợp lệ". Driver ném `LidarTransportError`, lớp con của `ScanReadError`. Demo thôi đọc cổng và dừng xe ảo ngay với lý do "Mất kết nối LiDAR (lỗi cổng nối tiếp)". Demo kết thúc khi xe ảo đứng yên, đóng cổng chết không ném lỗi lần hai, thoát mã 1. Lý do "bản đồ hợp nhất không hợp lệ" vẫn đúng trong hai trường hợp. (1) Hết thời gian chờ vòng quét (`ScanReadError` thường, cổng còn sống): demo đếm lỗi, đọc tiếp, và lớp `LiveLidar` hết hạn sau `--max-age` (0,3 s). (2) Giao diện `ui.lidar_app`: luồng đọc chỉ hiện tên lỗi rồi thử lại, nên xe ảo dừng khi lớp `LiveLidar` hết hạn (suy ra từ mã).*

## 3b. Kiểm toán độc lập "vì sao số vật cản khác số vật" (22/09/2026, 45 agent, 21 phát hiện, 12 được xác nhận)

Câu hỏi của người dùng: LiDAR thấy nhiều hơn / số vật cản trên sa bàn nhiều hơn số đồ vật. Đo trên bản ghi p07 (cùng bàn): một vòng 352 phản hồi → 221 rơi trong sa bàn 3 × 2 m → 101 sau mặt nạ thân xe (120 điểm là bo adapter, dây cáp, mép bàn sát cảm biến) → gộp 10 vòng thành 67 ô 5 cm = 18 cụm vật nhưng 33 hình chữ nhật (11 hình chỉ một ô). Kết luận đã được phản biện xác nhận:

| Phát hiện | Xử lý |
|---|---|
| Số "vật cản" là số hình chữ nhật phủ chính xác, không phải số vật; phủ hình chữ nhật không phình (0 cặp gộp được), 33 là giá của bậc thang ở 5 cm | Giữ phủ chính xác (bao hộp theo cụm sẽ nuốt thêm 48 ô trống, bằng 3 thân xe). Thêm `count_objects` (cụm 8 lân cận) và nhãn "X vật thể, chia thành Y hộp"; điểm LiDAR thô vẽ thẳng lên sa bàn (vàng = dùng được, nâu = bị mặt nạ bỏ) |
| Hình quét vẽ phía trước lên trên, sa bàn vẽ phía trước sang phải: hai hình lệch nhau 90°, không có dấu hiệu hướng | `ScanView(front_up=False)` trong ngăn LiDAR (cùng hướng sa bàn), mũi tên "trước" trên hình quét, mũi tên hướng LiDAR tại điểm xuất phát trên sa bàn |
| Lề mặt nạ thân xe 10 cm làm vật cách thân xe dưới 10 cm thành "không có phản hồi" thay vì bị chặn; khoảng hở lúc xuất phát là do mặt nạ tạo ra | Lề thành tham số trên giao diện ("cm quanh xe bỏ", mặc định 10 vì bàn thử có adapter sát cảm biến; trên xe thật đặt 3 cm = lề an toàn của planner). Vật thử phải đặt cách LiDAR ≥ 40 cm |
| Bản đồ nền gộp 10 vòng với "thấy 1 lần là chặn": 29 % ô là nhiễu chớp tắt (6 ô chỉ thấy 1/10 vòng) | `ScanUnion` đếm theo VÒNG (không theo tia) với tham số "lần thấy mới tính", mặc định 2 |
| Ô "Đảo chiều góc" im lặng khi phát lại bản ghi và không làm mất hiệu lực bản đồ nền đã quét | Báo rõ khi phát lại; khi đổi chiều lúc đang chỉnh sa bàn thì xóa vật LiDAR và yêu cầu quét nền lại. *Cập nhật 24/09/2026: bản đã commit (`6dba1a6`) không có bước quét nền (quy tắc 4, mục 5). Đổi chiều lúc đang chỉnh sa bàn thì xóa vật LiDAR và bỏ các vòng quét cũ, hộp được dựng lại từ vòng quét sau (`_set_mirror` trong `ui/lidar_dock.py`). Khi xe ảo đang chạy thì ô "Đảo chiều góc" bị khóa; nếu chiều vẫn đổi trong lúc chạy thì xe dừng.* |
| Sa bàn có cạnh không chia hết cho 5 cm làm `GridSpec` ném lỗi trong timer 50 ms | `_bounds_grid` cắt xuống bội số 5 cm |
| Bộ đếm id vật cản tăng theo mọi ứng viên nên có thể trùng id ở lần chèn sau | Chỉ đánh số vật thực sự đưa vào sa bàn (`_numbered`), có test id không trùng |
| Chưa xác minh dấu góc (trái/phải) bằng vật thật; sai dấu sẽ lật trái/phải ở CẢ hai hình nên không tự phát hiện được | Vẫn cần lần đặt hộp bên trái (p04); ghi ở [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 6 và 6b |
| Chi phí `check_motion` với shapely tăng tuyến tính theo số hình chữ nhật (191 µs với 33 hình, mỗi bước 5 ms) | Chấp nhận ở quy mô bàn thử; khi quét cả phòng cần STRtree/union trong `footprint._evaluate` |

Sau khi sửa, chạy lại demo trên bàn: 28 vật cản nền, planner báo đích (2,0; 1,0) trúng vật thật ở khoảng 1,9–2,05 m trước cảm biến, đúng với đồ trên bàn; trong giao diện chỉ cần kéo đích sang chỗ trống.

## 4. Quy ước

- Hệ bản đồ = hệ sa bàn giai đoạn 0. Lưới `cells[row][col]`, row theo y, col theo x, cùng bố cục `perception/costmap.py`.
- Tư thế cảm biến trong hệ xe `(x, y, yaw)`, gốc xe tại tâm trục sau.
- `Obstacle.kind` chỉ nhận `box | car | wall | unknown`: vật cản từ bản đồ mang `kind="box"` (OCCUPIED) hoặc `"unknown"`; cầu nối nhận ra vật của mình qua tiền tố id (`lidar_00012`).
- Vật cản là phủ hình chữ nhật chính xác của ô bị chặn; tường xiên thành bậc thang nhiều hình nhỏ. Đúng nhưng chưa đo tốc độ planner với hàng trăm hình.

## 5. Cách chạy

Giao diện (khuyên dùng): cửa sổ đỗ xe giai đoạn 0 có thêm ngăn LiDAR bên phải (`ui/lidar_dock.py`, `ui/lidar_app.py`). **Bản đồ là thời gian thực, không có bước "quét nền"**: vừa kết nối là các hộp trên sa bàn đã bám theo LiDAR, xoay cảm biến hay dời đồ vật thì hộp đi theo trong vòng vài trăm mili giây. Trình tự: **Kết nối** → nhìn sa bàn khớp với thực tế (chỉnh "vòng gộp", "lần thấy mới tính", "cm quanh xe bỏ" nếu cần) → **Tìm đường đỗ** (bản đồ được CHỐT tại đây để lập đường) → **Bắt đầu đỗ** → đưa tay vào trước LiDAR cách ≥ 40 cm: kỳ vọng xe ảo dừng, ngăn LiDAR ghi "Vật mới trên đường". Rút cáp khi đang chạy: kỳ vọng xe dừng với lý do mất LiDAR. Hai hành vi này mới được kiểm bằng test chạy ẩn với nguồn quét kịch bản (`tests/test_lidar_dock_ui.py`, 5 test); **chưa thử với tay và cáp thật** (mục 3).

Lệnh `ui.lidar_app` và `fusion.demo` không kèm `--recording` mở LiDAR ở cổng ghi trong `configs/thiet_bi.json`; thêm `--port COMx` để ghi đè ([chuyển máy](CHUYEN_MAY_BAN.md)).

```powershell
# trong thư mục autopark, .venv
.\.venv\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app
.\.venv\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app --recording runs/lidar_bench/20260922/p07_nen_phong.npz
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_fusion.py tests/test_fusion_demo.py
.\.venv\Scripts\python.exe -X utf8 -m autopark.fusion.demo --seconds 30      # đưa tay vào trước LiDAR lúc xe chạy
.\.venv\Scripts\python.exe -X utf8 -m autopark.fusion.demo --recording runs/lidar_bench/20260922/p07_nen_phong.npz --seconds 10
.\.venv\Scripts\python.exe -X utf8 -m autopark.fusion.demo --seconds 30 --warmup 4.5
```

## 6. Chưa làm / giới hạn

- Chưa có ESP32, IMU, ToF: `NearFieldLayer` mới chạy với số đo giả; không ghi nhận "ToF thật đã hoạt động".
- *Cập nhật 24/09/2026:* khung telemetry thật đã được đặc tả ở [GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 3 và 8: `tof_valid_mask` + `tof_mm[4]`, số đo không hợp lệ gửi 0; phía laptop là `VehicleTelemetry.tof_m` (4 giá trị `float | None`, stamp là giờ laptop lúc nhận, giờ bo ở `device_time_ms`). Cấu trúc này khác `NearFieldReading` (không có `sensor_id`, `max_range_m`, stamp riêng từng số đo), nên câu "cùng cấu trúc dữ liệu thật" ở bảng mục 1 (viết 22/09, trước khi có giao thức) chỉ đúng về nội dung (nguồn, thời gian, giá trị, hợp lệ), không đúng về kiểu dữ liệu. Chưa có mã chuyển `VehicleTelemetry` → `NearFieldReading`, chưa có bảng gán chỉ số ToF 0–3 → vị trí gá; firmware C++ chưa biên dịch và chưa có mã đọc VL53L1X, nên chưa có số đo ToF thật. *Cập nhật 25/09/2026:* mã chuyển và bảng gán đã có từ commit `6db5087`: `fusion/layers.py::tof_to_near_field` đổi `VehicleTelemetry.tof_m` thành `NearFieldReading` theo `TofMountConfig` nạp `configs/tof_mounts_v0.json` (vị trí gá và tầm đo GIẢ ĐỊNH – CHƯA ĐO); `NearFieldLayer.add_telemetry` nạp cả khung; test ở `tests/test_nearfield_tof.py` (20 hàm, 54 trường hợp). Mới thử với khung telemetry của bo mô phỏng qua cổng serial giả; vẫn chưa có số đo ToF thật. *(Cập nhật 30/09/2026: vế "firmware C++ chưa biên dịch" ở trên đã cũ: firmware biên dịch cho ESP32-S3 từ 29/09/2026 và chạy trong bo ảo QEMU từ 30/09/2026 (chỉ là giả lập, [MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md)), chưa nạp bo; vẫn chưa có mã đọc VL53L1X nên vẫn chưa có số đo ToF thật.)*
- `CameraSemanticLayer` mới có phép đặt costmap camera vào bản đồ; chưa có khung hình camera thật đi qua. *(Cập nhật 25/09/2026: `perception/bev.py` (commit `1d2b857`) dựng được costmap hệ xe từ AI nhiều camera, nhưng chưa chỗ nào trong mã nạp nó vào `CameraSemanticLayer`; câu trên vẫn đúng.)* *(Cập nhật 30/09/2026: hai câu trên viết trước commit `b01dea4` (25/09/2026). Từ commit đó, `fusion/camera_ai.py` đặt BEV vào `CameraSemanticLayer` trong hệ bản đồ, lọc 2 trong 3 lô và đưa vật cản vào phiên đỗ qua ngăn AI camera ([AI_DIEU_KHIEN_XE.md](AI_DIEU_KHIEN_XE.md)). Khung thật của bản ghi `o03_20260924` đã đi qua đường này khi phát lại, nhưng với cấu hình thật mọi lô bị chặn (1163 lô, 0 vật cản) vì chưa có hiệu chuẩn; chưa chạy với camera thật đang mở.)*
- Chưa có định vị: tư thế xe lấy từ mô phỏng; LiDAR thật đứng yên. *(Cập nhật 25/09/2026: đã có định vị trên bản đồ tĩnh `lidar/localize.py` (commit `b100a5d`) và odometry khớp scan `lidar/scan_odometry.py` (commit `a7cec5e`), chỉ chạy offline trên bản ghi, chưa có tham chiếu độc lập, chưa nối vào hợp nhất hay phiên đỗ xe ([DINH_VI_LIDAR.md](DINH_VI_LIDAR.md), [SO_SANH_DINH_VI_SLAM.md](SO_SANH_DINH_VI_SLAM.md)). Với bo thật, phiên đỗ từ chối START khi chưa có nguồn tư thế thật ([CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) mục 3).)*
- Không có bộ nhớ thời gian trong hợp nhất (mỗi lần gọi là ảnh chụp); lớp LiDAR trực tiếp giữ 3 vòng gần nhất.
- Giao diện dùng bản đồ thời gian thực (3 vòng gần nhất, ô phải thấy ≥ 2 vòng); `fusion/demo.py` dòng lệnh vẫn dùng bản chụp 10 vòng đầu vì nó chạy không có người ngồi trước màn hình. *(Muộn tối 24/09/2026: đó là 10 vòng ngay sau các vòng khởi động bị bỏ, mục 2. Lệnh mẫu cuối ở mục 5 thêm `--warmup 4.5`, tức chờ tới 4,5 s sau SCAN; CHƯA chạy với C1 thật.)*
- Bản đồ chốt lúc lập đường: vật xuất hiện giữa lúc lập đường và lúc bấm chạy chỉ được phát hiện khi xe đã chạy.
- Hiệu năng planner với hàng trăm hình chữ nhật chưa đo; cần bộ kiểm tra va chạm theo lưới nếu chậm.
