# Giai đoạn 1 — nhánh LiDAR: nhận RPLIDAR C1, driver, ghi phiên, bản đồ tĩnh (22/09/2026)

**Kế hoạch đối chiếu:** [v3.1, mục 5 "Khi nhận LiDAR"](../../KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md), bước 1–3 và 5.
**Mức bằng chứng:** thiết bị thật trên bàn làm việc, máy bàn i9-14900 (không phải laptop RTX 3050 Ti mang đi nộp đồ án), chưa làm nóng theo sổ tay, chưa đặt vật ở khoảng cách đo bằng thước. Mọi con số dưới đây là của một phiên cụ thể, không phải cam kết.
**Phần chuẩn bị khi chưa có đồ** (nguồn phát lại, ROI, costmap camera, giám sát dữ liệu cũ) nằm ở [GIAI_DOAN_1_CHUAN_BI.md](GIAI_DOAN_1_CHUAN_BI.md).

## 1. Tiếp nhận thiết bị

Máy nhận cầu USB–UART CP2102N (VID 10C4 / PID EA60) ở trạng thái Code 28; người dùng cài Silicon Labs CP210x Universal Windows Driver, thiết bị thành "Silicon Labs CP210x USB to UART Bridge (COM4)". Kiểm kê ở [hardware_inventory.md](hardware_inventory.md). Thăm dò giao thức trước khi viết driver (script tạm, không lưu trong repo) xác nhận: GET_INFO trả model 0x41 / firmware 1.2 / serial; GET_HEALTH OK; GET_LIDAR_CONF công bố hai chế độ Standard và DenseBoost, cùng 200 µs/mẫu; lệnh SCAN (0x20) trả mô tả `A5 5A 05 00 00 40 81` và luồng node 5 byte; RESET in `RP S2 LIDAR System.` sau ≈1 s.

## 2. Đã viết gì

| Khối | Module | Kiểm chứng |
|---|---|---|
| Giao thức: gói lệnh + checksum, mô tả phản hồi, node 5 byte, dò lại khi lệch byte, gom vòng theo cờ bắt đầu **và theo điểm góc quay về 0** | `lidar/rplidar_protocol.py` | test với byte chụp từ thiết bị và byte tính tay |
| Driver: pyserial 460800, info/health/scan-modes/reset, phiên đọc trả `LidarScan` theo quy ước yaw của dự án, ném `ScanReadError` khi hết thời gian chờ | `lidar/rplidar_c1.py` | test với cổng giả (kể cả health ERROR → reset); chạy thật trên COM4 |
| Ghi/phát lại phiên: `.npz` + `.json` meta (thiết bị, cổng, commit, thống kê driver, tóm tắt) | `lidar/recording.py` | test vòng tròn ghi → đọc → phát lại |
| Phiên đo tĩnh: ghi từng lần đặt vật, số đo, ngưỡng datasheet, hình, báo cáo | `lidar/bench.py` | test trên phòng tổng hợp có hộp; chạy thật một lần đặt |
| Bản đồ lưới tĩnh bằng ray casting, xuất `Costmap` cùng bố cục với costmap camera | `lidar/occupancy.py` | test phòng vuông (FREE/OCCUPIED/UNKNOWN, tư thế, tia NaN) |
| Odometry DROW `.odom2` để thử ghép nhiều vòng trên dữ liệu phát lại | `lidar/drow_odom.py` | test ghép theo dòng; chạy 300 vòng val |
| Màn hình scan trực tiếp + giám sát dữ liệu cũ + ghi phiên; phát lại `.npz` theo thời gian thật | `lidar/live_view.py` | test offscreen điều khiển tay; chạy headless 8 s với thiết bị |

22 test mới (`tests/test_lidar_*.py`), chạy cùng 14 test giai đoạn 1 có sẵn: 36/36 đạt trong `.venv`. Phụ thuộc mới: `pyserial>=3.5` (nhóm `lidar` trong pyproject).

Quy ước đã chốt trong mã: góc thiết bị tăng theo chiều kim đồng hồ (datasheet, và quan sát 99,8 % bước góc dương trong một vòng) nên driver **đổi dấu** để ra góc dương ngược chiều kim đồng hồ; cờ `--mirror` giữ dấu thiết bị nếu phép đo đặt hộp bên trái nói ngược. Khoảng cách 0 hoặc chất lượng 0 → NaN. Stamp = thời điểm gói byte chứa node cuối của vòng về tới máy, trên đồng hồ đơn điệu tính từ `start()` (mặc định `time.monotonic`, trên Python 3.12/Windows chỉ có bước 15,6 ms — xem ghi chú 24/09 ở mục 3).

## 3. Số đo trên bàn

Lệnh: `python -m autopark.lidar.bench record --port COM4 --out runs/lidar_bench/20260922 --name p07_nen_phong --seconds 20`.

| Đại lượng | Datasheet C1M1 | Đo được (p07, 181 vòng, 17,8 s) |
|---|---|---|
| Tần số quét | 8–12 Hz, 10 Hz thường | 10,09 Hz; chu kỳ trung vị 94 ms; khoảng trống lớn nhất 110 ms |
| Tia mỗi vòng | 5 kHz ÷ tần số ≈ 500 | trung vị 508 (396–536; các vòng đầu sau khởi động mô-tơ ít tia hơn) |
| Bước góc | 0,72° | 0,70° (trung vị trong một vòng, đo lúc thăm dò) |
| Tia không phản hồi | — | 34,6 % ở vị trí đặt (bàn làm việc, nhiều mặt xa/đen) |
| Khoảng cách | 0,05–12 m | 0,09–14,6 m; giá trị ngoài 0,05–12 m thiết bị vẫn xuất, datasheet ghi "chỉ tham khảo" |
| Lệch byte / dò lại | — | 0 trong 91.507 node |
| Khởi động mô-tơ | — | node đầu sau ≈2,2 s kể từ lệnh SCAN |

*Cập nhật 24/09/2026:* 10,09 Hz và khoảng 396–536 tia/vòng ở bảng trên tính cả lúc mô-tơ khởi động. 536 không phải số ổn định mà là đỉnh vượt khi khởi động, ở ≈ 1,3 s sau vòng đầu của bản ghi. Bỏ 3 s đầu thì p07 cho ≈ 10,0 Hz, 504–516 tia/vòng (mục 3b).

**Ghi chú 24/09/2026 về đồng hồ:** `bench` và `live_view` đóng dấu vòng bằng đồng hồ mặc định của driver là `time.monotonic`; trên Python 3.12/Windows đồng hồ này chỉ có bước 15,6 ms (cùng lỗi đã sửa ở bàn thử, [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 6). Trong p07, khoảng cách giữa hai vòng liên tiếp chỉ nhận các giá trị 78/79, 93/94, 109/110 ms (trung bình 99,1 ms). Vì vậy "chu kỳ trung vị 94 ms" và "khoảng trống lớn nhất 110 ms" là số bị lượng tử hóa, có thể lệch tới ≈ 15,6 ms, không phải chu kỳ thật. Tần số 10,09 Hz lấy số vòng chia cho cả 17,8 s nên sai số do đồng hồ dưới 0,01 Hz. Chu kỳ thật ≈ 100 ms: bàn thử dùng `perf_counter` đo một vòng dài trung vị 100,3 ms, 10,01 Hz, khoảng trống lớn nhất 103,9 ms (u01, 23/09).

Hình vòng quét cuối: [p07_nen_phong.png](evidence/lidar/p07_nen_phong.png). **Chưa có sai số khoảng cách so với thước**: cần các lần đặt hộp ở mục 6.

**Phát hiện khi ghi lần đầu:** trong 130 vòng có một "vòng" 1.016 tia với hai điểm góc quay về 0 — thiết bị bỏ sót cờ bắt đầu một lần. Driver được sửa để đóng vòng khi góc quay ngược quá 180° sau khi vòng đã có ≥ 100 tia (ngưỡng tránh tách nhầm ở node có cờ, vốn nằm ở ≈357° ngay trước điểm 0). Bản ghi p07 hiện tại là lần ghi lại sau khi sửa; thống kê driver ghi `wrap_splits` để theo dõi tần suất. *Cập nhật 24/09/2026:* cộng bộ đếm driver của 26 phiên ghi 22–24/09 (p07, live_headless, k01 và 23 phiên bàn thử giai đoạn 2) được 33.932 vòng: đóng vòng theo điểm góc (không có cờ bắt đầu) 5 lần, mỗi lần ở một phiên (t07, t08, u01, u04, w04), ≈ 1/6.800 vòng; 0 byte lệch, 0 vòng bị bỏ. Hai loại bộ đếm được cộng chung: 16 phiên bàn thử từ `20260923_v2` chỉ đếm sau lúc đặt lại bộ đếm (không gồm lúc làm nóng); 7 phiên bàn thử đầu tiên ngày 23/09 và ba phiên `bench`/`live_view` đếm từ lúc mở driver.

## 3b. Kiểm tra lại ngày 24/09/2026 (k01)

*Thêm 24/09/2026.* Ghi bằng `python -m autopark.lidar.bench record` trên máy bàn, mã ở commit `8293120`. Theo meta: COM4, `--warmup 3`, `--seconds 15`, không đặt vật, ghi chú "kiểm LiDAR có hỏng không, 24/09". LiDAR đã được dời chỗ sau 22/09; vị trí mới không được ghi lại. Bản ghi: `runs/lidar_bench/20260924_kiem/k01_kiem_suc_khoe.{npz,json,analysis.json,png}` (git-ignored; chưa chép bản nhỏ vào `docs/evidence/lidar/`).

- GET_INFO trả cùng thiết bị (serial `f57ffc8b…`, firmware 1.2, phần cứng 18); GET_HEALTH OK.
- 151 vòng được ghi trong 15,0 s (driver đếm 162 vòng, gồm 11 vòng lúc làm nóng); 0 lỗi đọc, 0 byte lệch, 0 vòng bị bỏ, 0 lần đóng vòng theo điểm góc.
- Tần số gộp 9,98 Hz (p07: 10,09 Hz); trung vị 512 tia/vòng (492–552). Chênh lệch là do đoạn khởi động mô-tơ nằm trong bản ghi, chưa thấy dấu hiệu thiết bị thay đổi. Ở p07 (ghi từ vòng đầu) mô-tơ lúc đầu quay nhanh (≈ 400 tia/vòng, vòng ≈ 78 ms theo đồng hồ thô), sau đó chậm lại (tới 536 tia/vòng ở ≈ 1,3 s), rồi mới ổn định quanh 510. Số tia/vòng tỉ lệ với chu kỳ vòng vì thiết bị lấy mẫu đều 5 kHz. `--warmup 3` tính từ ngay sau lệnh SCAN, mà node đầu tới sau ≈ 2,2 s (p07, live_headless), nên làm nóng chỉ bỏ 11 vòng đầu và k01 vẫn chứa pha chậm: 492 → 552 → 500 tia trong ≈ 1,4 s đầu bản ghi. Bỏ 3 s đầu của mỗi bản ghi thì cả hai ngày đều ≈ 10,0 Hz và 504–516 tia/vòng (trung bình ≈ 510; p07 còn 149 vòng, k01 còn 121 vòng). Stamp có bước 15,6 ms (ghi chú về đồng hồ ở mục 3), nên không ghi thêm chữ số thập phân.
- Độ lặp lại khoảng cách trên mặt tĩnh: ghép mỗi tia với tia gần góc nhất của vòng trước (lệch góc < 0,1–0,2°), chỉ lấy phản hồi 0,2–4 m, bỏ 3 s đầu. Trung vị |chênh| 1,0–1,25 mm ở p07 và 1,25–1,5 mm ở k01 tùy dung sai góc; p90 4–8 mm. Tính bằng script tạm ngày 24/09, không lưu trong repo. Đây là độ lặp lại giữa hai vòng, không phải sai số so với thước.
- Tia không phản hồi 21,1 % (p07: 34,6 %); phản hồi 0,14–12,85 m. Vùng không phản hồi thay đổi theo cảnh vì LiDAR đã dời chỗ, nên hai tỉ lệ này không so sánh được với nhau.

Kết luận: giao tiếp, tần số quét và số tia không có dấu hiệu hỏng. **Sai số khoảng cách so với thước vẫn chưa đo** (mục 6). Còn mở:
- Đỉnh khởi động 552 tia, cao hơn 536 (p07) và 540 (live_headless). Mới có ba lần khởi động được ghi (hai lần ngày 22/09, một lần ngày 24/09), chưa đủ để kết luận.
- k01 có 268 tia rất gần (0,135–0,173 m) với chất lượng ≤ 6 (trung vị chất lượng mọi phản hồi của k01 là 24), trong 130/151 vòng, quanh −56…−52° và −30…−28° theo quy ước dự án (tức 52–56° và 28–30° theo chiều kim đồng hồ ở quy ước thiết bị; dấu trái/phải chưa xác minh, mục 6b). p07 và live_headless (chỗ đặt cũ) cũng có tia gần chất lượng thấp ở hai vùng này, rộng hơn (p07: −70…−46° và −30…−22°), cùng các phản hồi gần khác của vật sát cảm biến ở chỗ đặt cũ. Chưa rõ là vật gì (nghi dây cáp; chưa kiểm).

## 4. Giám sát dữ liệu cũ trên thiết bị thật

`live_view` chạy headless 8 s với COM4: luồng đọc ở thread riêng, `FreshnessMonitor` với tuổi tối đa 0,3 s (≈3 chu kỳ) và chu kỳ mong đợi 0,094 s (lấy theo trung vị p07, là số bị lượng tử hóa — xem ghi chú 24/09 ở mục 3; mặc định của `live_view` và ngăn LiDAR là 0,1 s); trạng thái OK trong suốt phiên, bản ghi `live_headless.npz` được đóng đúng khi cửa sổ đóng. **Chưa thử rút cáp** để xem STALE_DATA phát trên thiết bị thật; cách thử: chạy `python -m autopark.lidar.live_view --port COM4`, rút cáp USB, tiêu đề phải đổi màu và dòng trạng thái báo `STALE_DATA` sau 0,3 s.

## 5. Bản đồ lưới tĩnh và thử odometry DROW

- Từ p07 (cảm biến cố định, lưới 8 × 8 m, ô 5 cm, tầm 8 m): 5.657 ô FREE, 230 ô OCCUPIED, còn lại UNKNOWN; [map_p07.png](evidence/lidar/map_p07.png); `costmap.json` cùng bố cục với costmap camera nên có thể hợp nhất sau. Chưa có tham chiếu độc lập để đo sai số bản đồ.
- DROW val `run_2015-11-25-10-34-20-a`, 300 vòng đầu, tư thế lấy từ `.odom2` ghép theo dòng: bản đồ theo quy ước loader v2 (không mirror) cho hành lang mỏng, rõ ([drow_odom_map.png](evidence/lidar/drow_odom_map.png), sharpness 0,30); đảo dấu góc cho vệt loang ([drow_odom_mirror_map.png](evidence/lidar/drow_odom_mirror_map.png), 0,18); giữ cảm biến cố định cho 0,13. Đây là bằng chứng gián tiếp rằng odometry DROW dùng cùng chiều với góc quét, chưa phải kiểm chứng SLAM. `.odom2` có seq không trùng seq của file scan (ghép theo dòng như loader gốc) và 23 dòng lặp.

## 6. Việc còn lại của bước 2–3 "Khi nhận LiDAR" — cần người đặt vật

Chuẩn bị: C1 dán cố định trên bàn phẳng, đánh dấu tâm quay; đo bằng thước từ tâm quay tới mặt hộp; hộp mặt trắng mờ rộng ≥ 30 cm; chạy quét ≥ 2 phút cho ấm máy (`--warmup 120` ở lần đầu). Hướng "phía trước" của C1 theo datasheet là trục x của hình 2-4; đặt hộp thẳng trước rồi xem góc quan sát được để chốt.

| Lần | Lệnh (trong `autopark`, `.venv`) |
|---|---|
| p01 | `python -m autopark.lidar.bench record --port COM4 --out runs/lidar_bench/<ngày> --name p01_truoc_0.5m --seconds 15 --warmup 120 --expected-distance 0.50 --expected-angle 0` |
| p02 | `... --name p02_truoc_1m --expected-distance 1.00 --expected-angle 0` |
| p03 | `... --name p03_truoc_2m --expected-distance 2.00 --expected-angle 0` |
| p04 | `... --name p04_trai_1m --expected-distance 1.00 --expected-angle 90` |
| p05 | `... --name p05_phai_1m --expected-distance 1.00 --expected-angle -90` |
| p06 | `... --name p06_sau_1m --expected-distance 1.00 --expected-angle 180` |
| p08 | `... --name p08_den_truoc_1m --expected-distance 1.00 --expected-angle 0 --note "hop den"` |

Sau đó `python -m autopark.lidar.bench report runs/lidar_bench/<ngày>` cho bảng; ngưỡng đạt: sai số ≤ 30 mm, hướng lệch ≤ 5°, 8–12 Hz, tia/vòng trong ±5 % của 5 kHz ÷ tần số, không trống quá 3 chu kỳ. Nếu p04 cho góc âm thì thêm `--mirror` và ghi lại lý do. Chép `*.analysis.json`, `*.png` và `report.md` vào `docs/evidence/lidar/`, cập nhật [gate_01.md](gate_01.md).

## 6b. Dấu góc trái/phải vẫn chưa được xác minh bằng vật thật

Driver đổi dấu góc thiết bị theo datasheet (góc tăng theo chiều kim đồng hồ). Kiểm toán 22/09 chỉ ra: nếu dấu sai, trái/phải sẽ lật ở CẢ hình quét lẫn sa bàn nên nhìn hai hình không phát hiện được; chỉ có lần đặt vật bên trái (p04, hoặc đơn giản là để một cuốn sách bên trái LiDAR và xem nó hiện ở phía trên xe trên sa bàn) mới chốt được. Nếu ngược, tích "Đảo chiều góc" trong ngăn LiDAR ([GIAI_DOAN_3_CHUAN_BI.md](GIAI_DOAN_3_CHUAN_BI.md) mục 5): ngăn xóa vật cản LiDAR trên sa bàn và dựng lại bản đồ từ vòng quét sau. *Sửa 24/09/2026:* câu cũ ghi "rồi quét nền lại", nhưng bản đã commit của ngăn LiDAR không có bước "quét nền" (đã bỏ hẳn, quy tắc 4 ở tài liệu đó). Khi phát lại bản ghi thì không đảo được (ngăn báo rõ); khi xe ảo đang chạy thì ô này bị khóa. Với phiên đo bằng `bench`, dùng `--mirror` như mục 6 và ghi lại lý do.

## 7. Giới hạn

- Chỉ dùng chế độ Standard; DenseBoost (định dạng gói khác) chưa cài đặt, chưa cần.
- Chưa đo trên laptop RTX 3050 Ti (máy nộp đồ án); chưa đo nhiệt/độ trễ dài hạn; chưa thử cáp dài hay hub.
- Bản đồ tĩnh không phải SLAM: không ước lượng tư thế, không nạp lại, không định vị.
- Phiên p07 chưa làm nóng và không có vật tham chiếu; số tia/tần số coi là ổn định, sai số khoảng cách thì chưa. *Cập nhật 24/09/2026:* ở trạng thái ổn định, số tia và tần số lặp lại ở k01 (mục 3b); sai số khoảng cách vẫn chưa đo.
- *Cập nhật 24/09/2026:* sau phiên p07, LiDAR đã chạy chung bốn camera + AI trên bàn thử ở máy bàn ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md)): ba phiên 10 phút s07, t09, u04 được 6006 / 6005 / 6006 vòng, 0 lỗi đọc, 0 vòng mất (t09 và u04 trung bình 10,01 Hz; s07 thuộc loạt đầu, đồng hồ thô, không lấy số thời gian), và năm phiên 60–120 s ngày 24/09 (w01–w05, 10,01–10,02 Hz, 0 lỗi đọc, 0 vòng mất). Độ lệch lúc về máy giữa vòng LiDAR và bộ ảnh ở mục 3.2 của tài liệu đó. LiDAR thật đứng yên làm nền để xe ảo lập đường và đỗ xong quanh đồ vật thật ở [GIAI_DOAN_3_CHUAN_BI.md](GIAI_DOAN_3_CHUAN_BI.md) mục 3; chưa thử đưa vật vào để xe ảo dừng. Vẫn chưa đo: nhiệt của LiDAR, độ trễ từ sự kiện thật tới lúc vòng quét về máy, cáp dài hay hub, và mọi số trên laptop RTX 3050 Ti (máy nộp đồ án).
