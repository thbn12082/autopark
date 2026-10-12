# Giai đoạn 1 — nhánh LiDAR: nhận RPLIDAR C1, driver, ghi phiên, bản đồ tĩnh (22/09/2026)

Tài liệu này ghi lại việc nhận và thử RPLIDAR C1 trên bàn: driver, ghi và phát lại phiên, số đo, độ lặp lại khoảng
cách, bản đồ lưới tĩnh và định vị lại trên bản đồ đó. Nó đối chiếu với kế hoạch v3.1
[bản `9d68257`](https://github.com/thbn12082/autopark/blob/9d68257/KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md), mục 5 "Khi
nhận LiDAR", bước 1–3, 5 và 6. Phần chuẩn bị khi chưa có đồ (nguồn phát lại, ROI, costmap camera, giám sát dữ liệu cũ)
nằm ở [GIAI_DOAN_1_CHUAN_BI.md](GIAI_DOAN_1_CHUAN_BI.md); kết quả cổng chuyển bước ở [gate_01.md](gate_01.md).

Tên đoạn và số bước ở trên theo bản kế hoạch trước ngày 26/09/2026.
[Bản hiện tại](../../KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) vẫn giữ mục 5, nhưng đoạn tương ứng tên là "Có đồ".

**Mức bằng chứng:** thiết bị thật trên bàn làm việc.

- Số đo ngày 22–24/09/2026 làm trên máy bàn trước (i9-14900, dùng tới 25/09/2026, LiDAR ở COM4). Đó không phải laptop
  RTX 3050 Ti mang đi nộp đồ án.
- Máy bàn hiện tại (Dell Precision 3680, LiDAR ở COM3) có các lượt kiểm ngày 29/09/2026
  ([CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 2;
  [kiem_may_20260929.md](evidence/chuyen_may_20260929/kiem_may_20260929.md)) và lượt thử driver đã sửa ngày 02/10/2026
  (cuối mục 2).
- Chưa làm nóng theo sổ tay, chưa đặt vật ở khoảng cách đo bằng thước.
- Mỗi con số dưới đây là của một phiên cụ thể, không phải cam kết.

## Tóm tắt

Trạng thái theo các mục bên dưới; phần mới nhất là bản sửa driver ngày 02/10/2026 (mục 2).

- **Đọc scan:** driver C1 chạy ổn trên máy bàn. Hai phiên p07 (22/09) và k01 (24/09) không lệch byte nào; khi đã qua
  lúc mô-tơ khởi động, C1 cho ≈ 10,0 Hz và 504–516 tia/vòng (mục 3, 3b). Ngày 02/10/2026 driver được sửa để đọc bỏ byte
  cũ ở cổng; phép chạy dài 30 phút sau đó có 0 lỗi LiDAR (mục 2).
- **Độ lặp lại khoảng cách** giữa hai vòng liên tiếp trên cảnh tĩnh: trung vị 0,75–1,5 mm, p90 4,25–7,75 mm (mục 3c).
  Đây không phải sai số so với thước.
- **Bản đồ:** có bản đồ lưới tĩnh `map_p07` từ một vị trí cố định, lưu và nạp lại được (mục 5). Chưa phải SLAM.
- **Định vị lại:** có công cụ. Nó nhất quán ở cùng chỗ và từ chối ở chỗ khác, nhưng chưa có vị trí tham chiếu độc lập
  nên chưa có sai số thật (mục 8).
- **Còn thiếu, cần người đặt vật:** sai số khoảng cách so với thước, dấu góc trái/phải (p04), thử rút cáp với thiết bị
  thật (mục 4, 6, 6b). Chưa đo gì trên laptop RTX 3050 Ti (mục 7).

## 1. Tiếp nhận thiết bị

Lúc nhận, máy thấy cầu USB–UART CP2102N (VID 10C4 / PID EA60) ở trạng thái Code 28. Người dùng cài Silicon Labs CP210x
Universal Windows Driver, sau đó thiết bị hiện là "Silicon Labs CP210x USB to UART Bridge (COM4)". Kiểm kê chi tiết ở
[hardware_inventory.md](hardware_inventory.md).

Trước khi viết driver, một script tạm (không lưu trong repo) thăm dò giao thức và xác nhận:

- GET_INFO trả model 0x41, firmware 1.2 và serial;
- GET_HEALTH trả OK;
- GET_LIDAR_CONF công bố hai chế độ Standard và DenseBoost, cùng 200 µs/mẫu;
- lệnh SCAN (0x20) trả mô tả `A5 5A 05 00 00 40 81`, sau đó là luồng node 5 byte;
- RESET in `RP S2 LIDAR System.` sau ≈1 s.

## 2. Đã viết gì

| Khối | Module | Kiểm chứng |
|---|---|---|
| Giao thức: gói lệnh + checksum, mô tả phản hồi, node 5 byte, dò lại khi lệch byte, gom vòng theo cờ bắt đầu **và theo điểm góc quay về 0** | `lidar/rplidar_protocol.py` | test với byte chụp từ thiết bị và byte tính tay |
| Driver: pyserial 460800; info/health/scan-modes/reset; phiên đọc trả `LidarScan` theo quy ước yaw của dự án; ném `ScanReadError` khi hết thời gian chờ | `lidar/rplidar_c1.py` | test với cổng giả, kể cả health ERROR → reset; chạy thật trên COM4; bản sửa 02/10/2026 đo trên C1 thật (cuối mục này) |
| Ghi/phát lại phiên: `.npz` + meta `.json` (thiết bị, cổng, commit, thống kê driver, tóm tắt) | `lidar/recording.py` | test vòng tròn ghi → đọc → phát lại |
| Phiên đo tĩnh: ghi từng lần đặt vật, số đo, ngưỡng datasheet, hình, báo cáo | `lidar/bench.py` | test trên phòng tổng hợp có hộp; chạy thật một lần đặt |
| Bản đồ lưới tĩnh bằng ray casting, xuất `Costmap` cùng bố cục với costmap camera | `lidar/occupancy.py` | test phòng vuông (FREE/OCCUPIED/UNKNOWN, tư thế, tia NaN) |
| Odometry DROW `.odom2` để thử ghép nhiều vòng trên dữ liệu phát lại | `lidar/drow_odom.py` | test ghép theo dòng; chạy 300 vòng val |
| Màn hình scan trực tiếp, giám sát dữ liệu cũ, ghi phiên; phát lại `.npz` theo thời gian thật | `lidar/live_view.py` | test offscreen điều khiển tay; chạy headless 8 s với thiết bị |
| Độ lặp lại khoảng cách trên cảnh tĩnh (thêm muộn tối 24/09/2026); xuất JSON + PNG | `lidar/repeatability.py` | 20 test (`tests/test_lidar_repeatability.py`); chạy offline trên p07, live_headless, k01 (mục 3c) |
| Định vị một vòng quét trên bản đồ đã lưu (thêm 24/09/2026): trường khoảng cách, khớp tương quan nhánh-cận, tinh chỉnh Gauss-Newton, báo OK / AMBIGUOUS / FAILED | `lidar/localize.py` | 29 test trên phòng tổng hợp (`tests/test_lidar_localize.py`); chạy offline trên p07, live_headless, k01 (mục 8) |

Công cụ độ lặp lại ghép tia của hai vòng liên tiếp theo góc và tính độ lệch chuẩn theo ô góc đã khử dốc, sau khi bỏ tia
không phản hồi và bỏ giây đầu. Lúc viết nó có 13 test (dữ liệu tổng hợp có nhiễu biết trước, hai test tái lập số trên
p07/k01 thật); rà soát cùng tối nâng lên 20 test (mục 3c). Bộ định vị có 17 test lúc viết, thêm 12 sau đợt rà soát cùng
ngày (mục 8).

Ngày 22/09/2026 có 22 test mới (`tests/test_lidar_*.py`). Chạy cùng 14 test giai đoạn 1 có sẵn: 36/36 đạt trong `.venv`.
Phụ thuộc mới: `pyserial>=3.5` (nhóm `lidar` trong pyproject).

**Quy ước đã chốt trong mã:**

- Góc của thiết bị tăng theo chiều kim đồng hồ. Datasheet nói vậy, và trong một vòng quan sát thấy 99,8 % bước góc
  dương. Vì thế driver **đổi dấu** để góc dương là ngược chiều kim đồng hồ. Cờ `--mirror` giữ dấu thiết bị, dùng khi phép
  đo đặt hộp bên trái cho kết quả ngược (mục 6b).
- Khoảng cách 0 hoặc chất lượng 0 → NaN.
- Stamp là thời điểm gói byte chứa node cuối của vòng về tới máy, trên đồng hồ đơn điệu tính từ `start()`. Mặc định là
  `time.monotonic`; trên Python 3.12/Windows đồng hồ này chỉ có bước 15,6 ms (xem ghi chú về đồng hồ ở mục 3).

**Sửa driver ngày 02/10/2026: byte cũ ở cổng LiDAR.** Phần này đo trên thiết bị thật: C1 trên COM3 của máy bàn hiện tại
(cầu CP210x, VID:PID 10C4:EA60), không người ở cạnh.

- **Phát hiện:** trên cổng này `reset_input_buffer()` (PurgeComm) không xóa byte nào. Có 81 byte trước và sau khi gọi;
  khi đang quét là 23 303 byte trước và sau.
- **Hệ quả 1:** nếu một tiến trình chết bỏ lại C1 đang quét mà không gửi STOP, mọi lần `start()` sau trên cùng cổng đều
  hỏng mãi. Mỗi lần driver chỉ đọc được 7 byte của mô tả trả lời, còn phần ứ tăng thêm 20 byte. Chuyện này đã xảy ra ở
  phép chạy dài LD-1 (kịch bản nghiệm thu: 30 phút, bốn camera 480p + LiDAR + AI). Lần 1 của LD-1 chết ở t ≈ 1050 s,
  không gửi STOP; vì vậy lần 2 (30 phút) có 8151 lỗi "bad response descriptor" và 0 vòng LiDAR. Làm lại được lỗi bằng
  cách giết một tiến trình đang quét rồi mở lại cổng.
- **Hệ quả 2:** `flush()` của driver (`fusion.demo` gọi sau khi lập đường để bỏ phần ứ) trước nay không xả được gì trên
  máy này, nên vòng cũ mang stamp mới.
- **Sửa** trong `lidar/rplidar_c1.py`:
  - `_discard_input` đọc bỏ byte cũ. Sau STOP, nó đọc tới khi cổng im 0,05 s, tối đa 1,5 s. Trước mỗi lệnh hỏi, trước
    SCAN và trong `flush()`, nó đọc phần đang chờ lúc gọi.
  - Lệnh hỏi info/health hỏng thì RESET một lần rồi hỏi lại.
  - Bỏ vòng đầu tiên sau `flush()`, vì trên C1 thật lần cắt giữa một nút cho ra một "vòng" giả 4 tia.
  - `stats()` có thêm `discarded_bytes` và `skipped_after_flush`.
  - Test: `tests/test_lidar_protocol.py`, với cổng giả mà PurgeComm không xóa gì.
- **Thử trên C1 thật với driver đã sửa:**
  - giết tiến trình đang quét rồi mở lại: đạt 2/2, đọc bỏ 58–60 byte, không cần RESET;
  - `flush()` bỏ 12,7 KB và 25,5 KB trong 0,1–0,2 ms, vòng kế đủ 452 và 516 tia;
  - LD-1 lần 3 (30 phút): 18 015 vòng, 10,008 Hz, 0 lỗi LiDAR.
- **Chưa thử:** cổng USB CDC của bo ESP32-S3 (`SerialVehicleIO` không gọi `reset_input_buffer`).
- **Vì sao LD-1 lần 1 chết (exit 127):** ngày 06/10/2026 đã rõ, kiểm trên máy tính. Một phiên tác tử Claude khác trên
  cùng máy, làm dự án khác, đã dừng tiến trình bằng `Stop-Process -Force`; không liên quan LiDAR.

Nguồn: [chan_doan_lidar.txt](evidence/thiet_bi_20261002/chan_doan_lidar.txt); cùng thư mục có các script thử
`thu_purge.py`, `thu_lidar_ket.py`, `thu_flush.py`. Chi tiết các lượt chạy ở [CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md)
mục 12, nguyên nhân exit 127 ở mục 16 của cùng biên bản.

## 3. Số đo trên bàn

Phiên p07 ngày 22/09/2026 ghi nền phòng, không đặt vật, chưa làm nóng. Lệnh:

```
python -m autopark.lidar.bench record --port COM4 --out runs/lidar_bench/20260922 --name p07_nen_phong --seconds 20
```

| Đại lượng | Datasheet C1M1 | Đo được (p07, 181 vòng, 17,8 s) |
|---|---|---|
| Tần số quét | 8–12 Hz, 10 Hz thường | 10,09 Hz; chu kỳ trung vị 94 ms; khoảng trống lớn nhất 110 ms |
| Tia mỗi vòng | 5 kHz ÷ tần số ≈ 500 | trung vị 508 (396–536; các vòng đầu sau khởi động mô-tơ ít tia hơn) |
| Bước góc | 0,72° | 0,70° (trung vị trong một vòng, đo lúc thăm dò) |
| Tia không phản hồi | — | 34,6 % ở vị trí đặt (bàn làm việc, nhiều mặt xa/đen) |
| Khoảng cách | 0,05–12 m | 0,09–14,6 m; giá trị ngoài 0,05–12 m thiết bị vẫn xuất, datasheet ghi "chỉ tham khảo" |
| Lệch byte / dò lại | — | 0 trong 91.507 node |
| Khởi động mô-tơ | — | node đầu sau ≈2,2 s kể từ lệnh SCAN |

Hai số 10,09 Hz và 396–536 tia/vòng ở bảng trên tính cả lúc mô-tơ khởi động. 536 không phải số ổn định mà là đỉnh vượt
khi khởi động, ở ≈ 1,3 s sau vòng đầu của bản ghi. Bỏ 3 s đầu thì p07 cho ≈ 10,0 Hz và 504–516 tia/vòng (mục 3b).

**Ghi chú về đồng hồ (24/09/2026).** `bench` và `live_view` đóng dấu vòng bằng đồng hồ mặc định của driver là
`time.monotonic`. Trên Python 3.12/Windows đồng hồ này chỉ có bước 15,6 ms; đây cũng là lỗi đã sửa ở bàn thử
([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 6). Trong p07, khoảng cách giữa hai vòng liên tiếp chỉ nhận các giá
trị 78/79, 93/94, 109/110 ms (trung bình 99,1 ms). Vì vậy "chu kỳ trung vị 94 ms" và "khoảng trống lớn nhất 110 ms" là số
bị lượng tử hóa, có thể lệch tới ≈ 15,6 ms, không phải chu kỳ thật. Tần số 10,09 Hz lấy số vòng chia cho cả 17,8 s, nên
sai số do đồng hồ dưới 0,01 Hz. Chu kỳ thật ≈ 100 ms: bàn thử dùng `perf_counter` đo được một vòng dài trung vị 100,3 ms,
10,01 Hz, khoảng trống lớn nhất 103,9 ms (u01, 23/09).

Hình vòng quét cuối: [p07_nen_phong.png](evidence/lidar/p07_nen_phong.png). **Chưa có sai số khoảng cách so với
thước**; cần các lần đặt hộp ở mục 6.

**Phát hiện khi ghi lần đầu: thiết bị đôi khi bỏ sót cờ bắt đầu vòng.** Trong 130 vòng của lần ghi đầu có một "vòng"
1.016 tia với hai điểm góc quay về 0. Driver được sửa để đóng vòng khi góc quay ngược quá 180° sau khi vòng đã có
≥ 100 tia. Ngưỡng 100 tia tránh tách nhầm ở node có cờ, vốn nằm ở ≈357° ngay trước điểm 0. Bản ghi p07 hiện tại là lần
ghi lại sau khi sửa. Thống kê driver ghi `wrap_splits` để theo dõi tần suất.

Đến 24/09/2026, cộng bộ đếm driver của 26 phiên ghi ngày 22–24/09 (p07, live_headless, k01 và 23 phiên bàn thử giai
đoạn 2) được 33.932 vòng. Trong đó đóng vòng theo điểm góc (không có cờ bắt đầu) 5 lần, mỗi lần ở một phiên (t07, t08,
u01, u04, w04), tức ≈ 1/6.800 vòng; 0 byte lệch, 0 vòng bị bỏ. Hai loại bộ đếm được cộng chung:

- 16 phiên bàn thử từ `20260923_v2` chỉ đếm sau lúc đặt lại bộ đếm, không gồm lúc làm nóng;
- 7 phiên bàn thử đầu tiên ngày 23/09 và ba phiên `bench`/`live_view` đếm từ lúc mở driver.

## 3b. Kiểm tra lại ngày 24/09/2026 (k01)

Phiên k01 kiểm xem LiDAR có hỏng gì không. Ghi bằng `python -m autopark.lidar.bench record` trên máy bàn, mã
ở commit `8293120`. Theo meta: COM4, `--warmup 3`, `--seconds 15`, không đặt vật, ghi chú "kiểm LiDAR có hỏng không,
24/09". LiDAR đã được dời chỗ sau 22/09; vị trí mới không được ghi lại.

Bản ghi gốc là `runs/lidar_bench/20260924_kiem/k01_kiem_suc_khoe.{npz,json,analysis.json,png}` (git-ignored). Muộn tối
24/09/2026 đã chép vào git hình vòng quét cuối [k01_kiem_suc_khoe.png](evidence/lidar/k01_kiem_suc_khoe.png), phân tích
[k01_kiem_suc_khoe.analysis.json](evidence/lidar/k01_kiem_suc_khoe.analysis.json) và meta
[k01_kiem_suc_khoe.json](evidence/lidar/k01_kiem_suc_khoe.json). Ba tệp này trùng từng byte với tệp trong `runs/`. Bản
ghi `.npz` (418 KB) không chép.

Kết quả:

- GET_INFO trả cùng thiết bị (serial `f57ffc8b…`, firmware 1.2, phần cứng 18); GET_HEALTH OK.
- 151 vòng được ghi trong 15,0 s; driver đếm 162 vòng, gồm 11 vòng lúc làm nóng. 0 lỗi đọc, 0 byte lệch, 0 vòng bị bỏ,
  0 lần đóng vòng theo điểm góc.
- Tần số gộp 9,98 Hz (p07: 10,09 Hz); trung vị 512 tia/vòng (492–552). Chênh lệch là do đoạn khởi động mô-tơ nằm trong
  bản ghi; chưa thấy dấu hiệu thiết bị thay đổi (giải thích ngay dưới danh sách).
- Độ lặp lại khoảng cách trên mặt tĩnh: ghép mỗi tia với tia gần góc nhất của vòng trước (lệch góc < 0,1–0,2°), chỉ lấy
  phản hồi 0,2–4 m, bỏ 3 s đầu. Trung vị |chênh| là 1,0–1,25 mm ở p07 và 1,25–1,5 mm ở k01, tùy dung sai góc; p90 4–8 mm.
  Đây là độ lặp lại giữa hai vòng, không phải sai số so với thước. Lúc đầu phép tính chạy bằng một script tạm không lưu
  trong repo, và script đó đã mất. Muộn tối 24/09/2026 phép tính được viết lại theo đúng mô tả này thành
  `lidar/repeatability.py` và cho lại đúng các số trên (mục 3c).
- Tia không phản hồi 21,1 % (p07: 34,6 %); phản hồi 0,14–12,85 m. Vùng không phản hồi thay đổi theo cảnh vì LiDAR đã dời
  chỗ, nên hai tỉ lệ này không so sánh được với nhau.

**Vì sao k01 và p07 khác tần số và số tia.** Ở p07 (ghi từ vòng đầu), mô-tơ lúc đầu quay nhanh: ≈ 400 tia/vòng, vòng
≈ 78 ms theo đồng hồ thô. Sau đó nó chậm lại, tới 536 tia/vòng ở ≈ 1,3 s, rồi mới ổn định quanh 510. Số tia/vòng tỉ lệ
với chu kỳ vòng, vì thiết bị lấy mẫu đều 5 kHz. `--warmup 3` tính từ ngay sau lệnh SCAN, mà node đầu tới sau ≈ 2,2 s
(p07, live_headless). Vì vậy làm nóng chỉ bỏ 11 vòng đầu, và k01 vẫn chứa pha chậm: 492 → 552 → 500 tia trong ≈ 1,4 s
đầu bản ghi. Bỏ 3 s đầu của mỗi bản ghi thì cả hai ngày đều ≈ 10,0 Hz và 504–516 tia/vòng (trung bình ≈ 510; p07 còn
149 vòng, k01 còn 121 vòng). Stamp có bước 15,6 ms (ghi chú về đồng hồ ở mục 3), nên không ghi thêm chữ số thập phân.

**Kết luận:** giao tiếp, tần số quét và số tia không có dấu hiệu hỏng. **Sai số khoảng cách so với thước vẫn chưa đo**
(mục 6).

Còn mở:

- Đỉnh khởi động của k01 là 552 tia, cao hơn 536 (p07) và 540 (live_headless). Mới có ba lần khởi động được ghi (hai lần
  ngày 22/09, một lần ngày 24/09), chưa đủ để kết luận.
- k01 có 268 tia rất gần (0,135–0,173 m) với chất lượng ≤ 6, trong 130/151 vòng; trung vị chất lượng mọi phản hồi của k01
  là 24. Các tia này nằm quanh −56…−52° và −30…−28° theo quy ước dự án, tức 52–56° và 28–30° theo chiều kim đồng hồ ở quy
  ước thiết bị (dấu trái/phải chưa xác minh, mục 6b). p07 và live_headless (chỗ đặt cũ) cũng có tia gần chất lượng thấp ở
  hai vùng này, rộng hơn (p07: −70…−46° và −30…−22°), cùng các phản hồi gần khác của vật sát cảm biến ở chỗ đặt cũ. Chưa
  rõ là vật gì; nghi dây cáp, chưa kiểm.

## 3c. Độ lặp lại khoảng cách: công cụ trong repo và kết quả chạy lại (thêm muộn tối 24/09/2026)

Script tạm tính độ lặp lại ở mục 3b không được lưu. Vì vậy muộn tối 24/09/2026 phép tính được viết lại theo đúng mô tả
ở mục 3b thành `lidar/repeatability.py`. Công cụ chạy offline trên máy bàn, không mở thiết bị. Mã gốc đã mất, nên "tái
lập" ở đây chỉ có nghĩa là cùng mô tả phương pháp cho cùng các số; không chứng minh được hai mã giống hệt nhau.

Lệnh (trong `autopark`, một dòng, dán được vào cmd.exe):

```
.venv\Scripts\python.exe -X utf8 -m autopark.lidar.repeatability runs/lidar_bench/20260922/p07_nen_phong.npz runs/lidar_bench/20260922/live_headless.npz runs/lidar_bench/20260924_kiem/k01_kiem_suc_khoe.npz --out runs/lidar_bench/do_lap_lai
```

**Tệp ra.** Mỗi bản ghi cho `<tên>.repeatability.json` và `<tên>.repeatability.png`, cộng một tệp gộp
`repeatability_summary.json`. Mỗi mục trong tệp gộp ghi đường dẫn bản ghi như đã gõ (`path`) và tên hai tệp ra
(`outputs`). Nếu hai bản ghi khác thư mục trùng tên tệp, ví dụ `lidar/part_0000.npz` của hai phiên bàn thử, tên tệp ra
được thêm dần tên thư mục cha, ví dụ `o03_20260924__lidar__part_0000.repeatability.json`. Bản đầu chưa làm vậy, nên tệp
ra của bản ghi sau ghi đè bản ghi trước mà không báo; lỗi này được sửa sau rà soát cùng tối. Nêu cùng một bản ghi hai
lần thì bị từ chối như lỗi dòng lệnh. Ba bản ghi ở lệnh trên không trùng tên, nên tên tệp ra không đổi.

**Bộ lọc mặc định** giống mục 3b: bỏ tia không phản hồi (NaN, không tính là 0), chỉ lấy phản hồi 0,2–4 m, bỏ 3 s đầu
tính từ vòng đầu của bản ghi.

**Hai phép tính:**

- **Theo tia, giữa hai vòng liên tiếp** (phép tính của mục 3b): mỗi tia ghép với tia gần góc nhất của vòng trước, có xét
  vòng qua ±180°. Chỉ nhận cặp lệch góc < 0,1° (hoặc < 0,2°), rồi thống kê |Δr|.
- **Theo ô góc 0,5°** (mới): gom mọi tia của các vòng đã chọn theo ô góc. Góc tia xê dịch giữa các vòng, nên trên mặt
  nghiêng khoảng cách đổi theo góc ngay trong một ô. Trong mỗi ô, khử độ dốc đó bằng hồi quy tuyến tính khoảng cách theo
  góc, rồi lấy độ lệch chuẩn phần dư. Tóm tắt bằng trung vị và p90 qua các ô. Một ô chỉ được tính khi có ≥ 10 mẫu và
  ≥ 50 % số tia rơi vào ô qua bộ lọc.

| Bản ghi (số vòng dùng) | \|Δr\|, lệch góc < 0,1°: trung vị / p90 (số cặp) | \|Δr\|, lệch góc < 0,2°: trung vị / p90 (số cặp) | Độ lệch chuẩn theo ô 0,5°, đã khử dốc: trung vị / p90 (số ô) |
|---|---|---|---|
| p07, 22/09 (149) | 1,00 / 4,25 mm (8.922) | 1,25 / 6,00 mm (16.924) | 1,56 / 44,8 mm (286) |
| live_headless, 22/09 (28) | 0,75 / 4,25 mm (1.892) | 1,00 / 5,50 mm (3.174) | 0,89 / 6,41 mm (282) |
| k01, 24/09 (121) | 1,25 / 5,50 mm (9.295) | 1,50 / 7,75 mm (19.173) | 1,39 / 3,43 mm (429) |

**Đối chiếu với số đã ghi trước đó.** Mục 3b và TONG_HOP_DU_AN.md mục 4.3
([bản `9d68257`](https://github.com/thbn12082/autopark/blob/9d68257/TONG_HOP_DU_AN.md)) ghi trung vị "1,0–1,5 mm", p90
"4–8 mm". Mục 4.3 của tổng hợp hiện nay ghi theo bảng trên: trung vị 0,75–1,5 mm, p90 4,25–7,75 mm.

- p07 cho 1,0–1,25 mm và k01 cho 1,25–1,5 mm tùy dung sai góc: **trùng** số đã ghi. p90 là 4,25–7,75 mm, nằm trong
  khoảng "4–8 mm" đã ghi.
- live_headless không có trong số đã ghi. Sau khi bỏ 3 s, bản ghi này chỉ còn 28 vòng. Trung vị của nó là 0,75–1,0 mm,
  thấp hơn khoảng "1,0–1,5 mm" của bản tổng hợp cũ. Tính cả live_headless thì khoảng trung vị là 0,75–1,5 mm. Chưa rõ vì
  sao thấp hơn; bản ghi này ngắn, ghi 2,5 phút sau p07 ở cùng chỗ đặt.
- Trung vị luôn là bội của 0,25 mm, vì C1 gửi khoảng cách theo bước 1/4 mm. JSON ghi `range_step_mm: 0.25`, nghĩa là mọi
  khoảng cách hữu hạn của bản ghi là bội của 0,25 mm; đã kiểm trên cả ba bản ghi. Vì vậy "1,0 so với 1,25 mm" chỉ cách
  nhau một bậc lượng tử.
- Hai phép tính cho cùng cỡ. Trung vị |Δr| là 0,75–1,5 mm (ba bản ghi, hai dung sai góc); trung vị độ lệch chuẩn theo ô
  0,5° (đã khử dốc) là 0,89–1,56 mm. Nếu nhiễu của mỗi vòng là Gauss độc lập với độ lệch chuẩn σ thì trung
  vị |Δr| ≈ 0,95σ, tức σ suy từ |Δr| ≈ 0,79–1,57 mm. Đây là giả định, chưa kiểm.
- p90 theo ô của p07 lớn (44,8 mm): 66/286 ô có độ lệch chuẩn > 10 mm. Các ô này gom ở vài vùng góc (quanh −95…−90°,
  −13…+20°, 121…155°). Ở 74 % số ô đó, 1,4826 × MAD nhỏ hơn nửa độ lệch chuẩn, tức là vài giá trị nhảy xa chứ không phải
  nhiễu đều. Điều này hợp với mép vật hoặc phản hồi chập chờn, nhưng chưa kiểm bằng mắt từng vùng. k01 chỉ có 11/429 ô
  như vậy.

**Bằng chứng** (máy bàn, muộn tối 24/09/2026, chỉ chép phần nhỏ vào git). Lần chạy đầu ra một thư mục tạm của phiên làm
việc. Sau rà soát cùng tối, công cụ chạy lại bằng mã đã sửa với đúng lệnh trên, ra `runs/lidar_bench/do_lap_lai`
(git-ignored). Mọi số trong bảng không đổi; chỉ hash mã, mốc giờ, lệnh và các trường mới `path`/`outputs` khác. Tệp tóm
tắt dưới đây là của lần chạy lại.

- Tóm tắt đủ ba bản ghi, kèm lệnh, tham số và hash mã `repeatability.py` lúc chạy:
  [do_lap_lai_20260924.json](evidence/lidar/do_lap_lai_20260924.json). Hash là sha256 sau khi đổi CRLF→LF; kiểm lại bằng
  `git show <commit>:autopark/autopark/lidar/repeatability.py` rồi tính sha256. Lúc chạy mã chưa commit. Ngày 25/09/2026
  mã đã commit ở `a7cec5e`, và sha256 ghi trong tệp trùng sha256 của `repeatability.py` ở `a7cec5e` và ở `54cb3e2`.
- Hình, bên trái là độ lệch chuẩn theo góc, bên phải là tần suất |Δr| với dung sai 0,1°:
  [do_lap_lai_p07_nen_phong.png](evidence/lidar/do_lap_lai_p07_nen_phong.png),
  [do_lap_lai_k01_kiem_suc_khoe.png](evidence/lidar/do_lap_lai_k01_kiem_suc_khoe.png).

**Giới hạn:**

- Đây là độ lặp lại giữa các vòng trên cảnh tĩnh, **không phải sai số so với thước**. Sai số so với thước vẫn chưa đo
  (mục 6).
- p07 và live_headless ghi không làm nóng. Mốc bỏ 3 s tính từ vòng đầu của bản ghi, không phải từ lệnh SCAN.
- Chưa tách kết quả theo khoảng cách hay theo loại bề mặt.

**Kiểm chứng.** Lúc viết, `tests/test_lidar_repeatability.py` có 13 test. Các test dùng dữ liệu tổng hợp có nhiễu biết
trước; hai test chạy trên p07/k01 thật nếu có trong `runs/` (thiếu thì bỏ qua). Kiểm đột biến trên bản sao, không sửa
repo: 9/9 đột biến bị ít nhất một test bắt. Chín đột biến là: bỏ khử dốc, giữ tia NaN, bỏ phần bỏ giây đầu, bỏ xử lý vòng
qua ±180°, bỏ dung sai góc, bỏ lọc khoảng cách, bỏ lọc chất lượng, bỏ hệ số 1,4826, ghép hai vòng không liền nhau.

Rà soát muộn tối 24/09/2026 chỉ ra hai quy tắc nhận ô (≥ 10 mẫu, ≥ 50 % số tia trong ô có phản hồi) và phép kiểm bậc
0,25 mm không có test nào giữ. Ví dụ, bỏ quy tắc 50 % thì p07 đổi từ 1,56 / 44,8 mm (286 ô) thành 2,70 / 129,5 mm (433 ô;
tính lại offline trên máy bàn bằng `min_bin_return_fraction=0`), mà 13 test cũ vẫn đạt. Vì vậy có thêm 7 test, tổng 20:

- ô có nhiều tia không phản hồi (cung 20–50° chỉ ≈ 30 % tia có phản hồi) không được tính;
- ô cần đủ 10 mẫu (9 vòng: 0 ô, 10 vòng: 512 ô);
- `range_step_mm` là `None` khi khoảng cách không theo bậc 0,25 mm;
- hai test trên bản ghi thật giữ thêm số theo ô của bảng trên (286 ô, 1,56 / 44,8 mm cho p07; 429 ô, 1,39 / 3,43 mm cho
  k01);
- hai bản ghi trùng tên tệp giữ đủ hai bộ tệp ra; tên tệp ra chỉ dài thêm khi trùng; cùng một bản ghi nêu hai lần bị từ
  chối (mã thoát 2);
- hash mã như nhau với tệp LF và CRLF.

Kiểm đột biến lại trên bản sao, không sửa repo: 9 đột biến cũ và 10 đột biến mới của `repeatability.py`, cả 19 đều bị ít
nhất một test bắt. Mười đột biến mới là: đặt tên tệp ra chỉ theo tên bản ghi, nhận cùng một bản ghi hai lần, thêm thư mục
cha cho mọi tên, bỏ trường `path`, hash byte thô, bỏ quy tắc 50 %, hạ 50 % xuống 25 %, hạ 10 mẫu xuống 3, đổi `>=` thành
`>` ở số mẫu, luôn báo bậc 0,25 mm.

## 4. Giám sát dữ liệu cũ trên thiết bị thật

`live_view` đã chạy headless 8 s với LiDAR ở COM4, trạng thái OK trong suốt phiên. Luồng đọc chạy ở thread riêng.
`FreshnessMonitor` dùng tuổi tối đa 0,3 s (≈3 chu kỳ) và chu kỳ mong đợi 0,094 s. Số 0,094 s lấy theo trung vị p07, là số
bị lượng tử hóa (ghi chú về đồng hồ ở mục 3); mặc định của `live_view` và ngăn LiDAR là 0,1 s. Bản ghi `live_headless.npz`
được đóng đúng khi cửa sổ đóng.

**Chưa thử rút cáp** để xem STALE_DATA phát trên thiết bị thật. Cách thử:

1. chạy lệnh dưới;
2. rút cáp USB;
3. sau 0,3 s, tiêu đề phải đổi màu và dòng trạng thái báo `STALE_DATA`.

```
python -m autopark.lidar.live_view
```

Cổng LiDAR lấy từ `configs/thiet_bi.json`; thêm `--port COMx` để ghi đè ([chuyển máy](CHUYEN_MAY_BAN.md)).

## 5. Bản đồ lưới tĩnh và thử odometry DROW

- **Bản đồ từ p07.** Cảm biến cố định, lưới 8 × 8 m, ô 5 cm, tầm 8 m: 5.657 ô FREE, 230 ô OCCUPIED, còn lại UNKNOWN
  ([map_p07.png](evidence/lidar/map_p07.png)). `costmap.json` cùng bố cục với costmap camera nên có thể hợp nhất sau.
  Chưa có tham chiếu độc lập để đo sai số bản đồ.
- **Thử odometry DROW.** Dữ liệu DROW val `run_2015-11-25-10-34-20-a`, 300 vòng đầu, tư thế lấy từ `.odom2` ghép theo
  dòng. Ba cách dựng cho ba ảnh:
  - theo quy ước loader v2 (không mirror): hành lang mỏng, rõ ([drow_odom_map.png](evidence/lidar/drow_odom_map.png),
    sharpness 0,30);
  - đảo dấu góc: vệt loang ([drow_odom_mirror_map.png](evidence/lidar/drow_odom_mirror_map.png), 0,18);
  - giữ cảm biến cố định: 0,13 ([drow_fixed_map.png](evidence/lidar/drow_fixed_map.png)).

  Đây là bằng chứng gián tiếp rằng odometry DROW dùng cùng chiều với góc quét, chưa phải kiểm chứng SLAM. `.odom2` có seq
  không trùng seq của file scan (nên ghép theo dòng như loader gốc) và có 23 dòng lặp.
- **Cách dựng lại ba ảnh DROW** (trong `autopark`, `.venv`; dữ liệu `datasets/drow/` bị git-ignore; mỗi lệnh một dòng,
  dán được vào cmd.exe và PowerShell):

  ```
  .\.venv\Scripts\python.exe -X utf8 -m autopark.lidar.occupancy --drow datasets/drow/DROWv2-data/val/run_2015-11-25-10-34-20-a.bag.csv --scans 300 --grid -12 12 -12 12 0.1 --max-range 10 --out <thư mục>
  .\.venv\Scripts\python.exe -X utf8 -m autopark.lidar.occupancy --drow datasets/drow/DROWv2-data/val/run_2015-11-25-10-34-20-a.bag.csv --scans 300 --grid -12 12 -12 12 0.1 --max-range 10 --odom --out <thư mục>
  .\.venv\Scripts\python.exe -X utf8 -m autopark.lidar.occupancy --drow datasets/drow/DROWv2-data/val/run_2015-11-25-10-34-20-a.bag.csv --scans 300 --grid -12 12 -12 12 0.1 --max-range 10 --odom --mirror --out <thư mục>
  ```

  Ba lệnh lần lượt cho ảnh cố định, ảnh theo `.odom2` và ảnh đảo dấu góc. Tham số: 300 vòng đầu (`--start` mặc định 0),
  lưới 24 × 24 m ô 0,1 m, tầm 10 m; `--min-passes 3`, `--min-hits 2`, `--occupied-ratio 0.2` để mặc định.

  `costmap.json` không ghi tầm quét, nên tham số tầm được xác nhận bằng cách dựng lại. Tối 24/09/2026, ba lệnh trên chạy
  vào thư mục tạm: `map.png` trùng từng byte với ba tệp trong `evidence/lidar/`, và lưới `costmap.json` của ảnh cố định
  trùng từng ô với `runs/lidar_bench/20260922/drow_fixed/`. Bỏ `--max-range 10` (tầm mặc định 12 m) thì ảnh cố định khác:
  739 ô OCCUPIED thay vì 660. Sharpness phụ thuộc lưới và tầm, nên khi trích số 0,30 / 0,18 / 0,13 phải kèm các tham số
  này. Hình dựng từ DROW phải ghi công theo [GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md) (trích cả hai bài DROW).

## 6. Việc còn lại của bước 2–3 "Khi nhận LiDAR" — cần người đặt vật

Phần này cần người đặt hộp ở khoảng cách đo bằng thước, để đo sai số khoảng cách và chốt dấu góc.

**Chuẩn bị:**

- C1 dán cố định trên bàn phẳng, đánh dấu tâm quay;
- đo bằng thước từ tâm quay tới mặt hộp;
- hộp mặt trắng mờ, rộng ≥ 30 cm;
- chạy quét ≥ 2 phút cho ấm máy (`--warmup 120` ở lần đầu);
- hướng "phía trước" của C1 theo datasheet là trục x của hình 2-4; đặt hộp thẳng trước rồi xem góc quan sát được để chốt.

| Lần | Lệnh (trong `autopark`, `.venv`) |
|---|---|
| p01 | `python -m autopark.lidar.bench record --out runs/lidar_bench/<ngày> --name p01_truoc_0.5m --seconds 15 --warmup 120 --expected-distance 0.50 --expected-angle 0` |
| p02 | `... --name p02_truoc_1m --expected-distance 1.00 --expected-angle 0` |
| p03 | `... --name p03_truoc_2m --expected-distance 2.00 --expected-angle 0` |
| p04 | `... --name p04_trai_1m --expected-distance 1.00 --expected-angle 90` |
| p05 | `... --name p05_phai_1m --expected-distance 1.00 --expected-angle -90` |
| p06 | `... --name p06_sau_1m --expected-distance 1.00 --expected-angle 180` |
| p08 | `... --name p08_den_truoc_1m --expected-distance 1.00 --expected-angle 0 --note "hop den"` |

**Sau các lần đặt:**

1. Chạy `python -m autopark.lidar.bench report runs/lidar_bench/<ngày>` để ra bảng.
2. So với ngưỡng đạt: sai số ≤ 30 mm, hướng lệch ≤ 5°, 8–12 Hz, tia/vòng trong ±5 % của 5 kHz ÷ tần số, không trống quá
   3 chu kỳ.
3. Nếu p04 cho góc âm thì thêm `--mirror` và ghi lại lý do.
4. Chép `*.analysis.json`, `*.png` và `report.md` vào `docs/evidence/lidar/`, cập nhật [gate_01.md](gate_01.md).

## 6b. Dấu góc trái/phải vẫn chưa được xác minh bằng vật thật

Driver đổi dấu góc thiết bị theo datasheet (góc tăng theo chiều kim đồng hồ), nhưng dấu này chưa được kiểm bằng vật
thật. Kiểm toán ngày 22/09 chỉ ra: nếu dấu sai, trái/phải sẽ lật ở cả hình quét lẫn sa bàn, nên nhìn hai hình không phát
hiện được. Chỉ lần đặt vật bên trái mới chốt được: p04, hoặc đơn giản là để một cuốn sách bên trái LiDAR và xem nó hiện
ở phía trên xe trên sa bàn.

Nếu dấu ngược:

- Trong ngăn LiDAR, tích "Đảo chiều góc" ([GIAI_DOAN_3_CHUAN_BI.md](GIAI_DOAN_3_CHUAN_BI.md) mục 3b và 5). Ngăn xóa vật cản
  LiDAR trên sa bàn và dựng lại bản đồ từ vòng quét sau. Bản đã commit của ngăn LiDAR không có bước "quét nền"; bước đó
  đã bỏ hẳn (quy tắc 4 ở mục 2 của tài liệu trên). Khi phát lại bản ghi thì không đảo được, và ngăn báo rõ điều đó; khi
  xe ảo đang chạy thì ô này bị khóa.
- Với phiên đo bằng `bench`, dùng `--mirror` như mục 6 và ghi lại lý do.

## 7. Giới hạn

- Chỉ dùng chế độ Standard. DenseBoost (định dạng gói khác) chưa cài đặt, chưa cần.
- Bản đồ tĩnh ở mục 5 không phải SLAM: lúc đầu nó không ước lượng tư thế, không nạp lại, không định vị. Các bước sau:
  - Từ 24/09/2026 có nạp lại bản đồ và định vị từng vòng quét trên bản đồ cố định (mục 8). Bản đồ không được cập nhật
    và chưa có odometry.
  - Từ 25/09/2026 có thêm odometry khớp scan và bản đồ tăng dần (`lidar/scan_odometry.py`, commit `a7cec5e`). Công cụ mới
    thử offline trên DROW v2 và sáu bản ghi C1 đứng yên. So sánh các phương án và đề xuất cho V1 (bản đầu cần đạt) nằm ở
    [SO_SANH_DINH_VI_SLAM.md](SO_SANH_DINH_VI_SLAM.md).
  - Ngày 02/10/2026 người dùng đồng ý làm theo đề xuất đó. Nguồn tư thế LiDAR (a) + (b) và công cụ dựng bản đồ nhiều chỗ
    đặt đã nối vào phiên đỗ xe, mới kiểm ở mức mô phỏng (MP) và trên bản ghi C1 đứng yên
    ([NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md)).

  Trên C1 thật chưa có bản đồ nào dựng khi cảm biến di chuyển. Vẫn không phải SLAM.
- Phiên p07 chưa làm nóng và không có vật tham chiếu. Ở trạng thái ổn định, số tia và tần số lặp lại ở k01 (mục 3b);
  sai số khoảng cách thì chưa đo.
- Sau phiên p07, LiDAR đã chạy chung với bốn camera + AI trên bàn thử ở máy bàn
  ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md)):
  - ba phiên 10 phút s07, t09, u04 được 6006 / 6005 / 6006 vòng, 0 lỗi đọc, 0 vòng mất. t09 và u04 trung bình 10,01 Hz;
    s07 thuộc loạt đầu dùng đồng hồ thô, nên không lấy số thời gian;
  - năm phiên 60–120 s ngày 24/09 (w01–w05): 10,01–10,02 Hz, 0 lỗi đọc, 0 vòng mất.

  Độ lệch lúc về máy giữa vòng LiDAR và bộ ảnh nằm ở mục 3.2 của tài liệu đó.
- LiDAR thật đứng yên đã làm nền để xe ảo lập đường và đỗ xong quanh đồ vật thật
  ([GIAI_DOAN_3_CHUAN_BI.md](GIAI_DOAN_3_CHUAN_BI.md) mục 3). Chưa thử đưa vật vào để xe ảo dừng.
- Vẫn chưa đo: nhiệt của LiDAR và độ trễ dài hạn; độ trễ từ sự kiện thật tới lúc vòng quét về máy; cáp dài hay hub; mọi
  số trên laptop RTX 3050 Ti (máy nộp đồ án).

## 8. Định vị lại trên bản đồ tĩnh (thêm 24/09/2026)

Bước 6 của kế hoạch là *"Nạp lại bản đồ, thử định vị tại các vị trí có tham chiếu độc lập."* Công cụ là
`python -m autopark.lidar.localize`; phương pháp, tham số, test và giới hạn nằm ở [DINH_VI_LIDAR.md](DINH_VI_LIDAR.md).
Ngày 24/09 chỉ chạy offline trên các bản ghi có sẵn, không chạy thiết bị. Bản đồ dùng là `map_p07` (mục 5).

| Bản ghi | Kết quả (cửa sổ ±0,5 m / ±30° quanh gốc) |
|---|---|
| p07 (chính dữ liệu dựng bản đồ, không độc lập) | 181/181 OK. Tư thế (−1,3 mm; −3,3 mm; +0,01°); độ lệch chuẩn giữa các vòng 1,4 / 1,8 mm, 0,05° |
| live_headless (22/09, 2,5 phút sau p07) | 60/60 OK. Tư thế (−1,1 mm; −6,8 mm; **+4,33°**); độ lệch chuẩn 2,6 / 2,7 mm, 0,07°. Tìm trên cả bản đồ (`--global`) cho cùng kết quả |
| k01 (24/09, LiDAR đã dời chỗ) | 151/151 FAILED (tỉ lệ khớp trung vị 0,24, mâu thuẫn với bản đồ). Tìm trên cả bản đồ (31 vòng): 31/31 FAILED |

**Bằng chứng trong git.** Tối 24/09/2026, các lệnh ở [DINH_VI_LIDAR.md](DINH_VI_LIDAR.md) mục 3 được chạy lại offline
trên máy bàn (bản đồ `runs/lidar_bench/20260922/map_p07`, không chạy thiết bị), ra thư mục tạm. Chỉ ảnh overlay và một
tệp tóm tắt được chép vào git:

- ảnh overlay: [dinh_vi_p07_tren_p07.png](evidence/lidar/dinh_vi_p07_tren_p07.png),
  [dinh_vi_live_headless_tren_p07.png](evidence/lidar/dinh_vi_live_headless_tren_p07.png),
  [dinh_vi_k01_tren_p07.png](evidence/lidar/dinh_vi_k01_tren_p07.png),
  [dinh_vi_k01_global_tren_p07.png](evidence/lidar/dinh_vi_k01_global_tren_p07.png) (`--global --every 5`);
- tóm tắt [dinh_vi_tren_p07_20260924.json](evidence/lidar/dinh_vi_tren_p07_20260924.json): lệnh, tham số, hash mã
  `localize.py` và kết quả từng lần chạy, kể cả `--track` và `--global` của live_headless. Lúc chạy `localize.py` chưa
  commit; ngày 25/09/2026 đối chiếu thấy hash này trùng sha256 của `localize.py` trong commit `b100a5d` và ở `54cb3e2`.

Trạng thái và tư thế trùng bảng trên:

- p07 181/181 OK, trung vị (−1,3 mm; −3,3 mm; +0,008°);
- live_headless 60/60 OK, (−1,1 mm; −6,8 mm; +4,33°); `--track` và `--global` cũng 60/60 OK cùng tư thế;
- k01 151/151 FAILED; k01 `--global --every 5` 31/31 FAILED.

Thời gian mỗi vòng trong tệp tóm tắt đo lúc máy đang chạy việc khác song song, nên không thay số ở DINH_VI_LIDAR.md
mục 5. Ảnh overlay chỉ cho thấy độ **nhất quán**, không phải độ đúng, vì chưa có tham chiếu độc lập. Trước khi chạy, bản
đồ `map_p07` cũng được dựng lại từ p07 bằng `autopark.lidar.occupancy` với mã hiện tại: lưới trùng từng ô, `map.png`
trùng từng byte với [map_p07.png](evidence/lidar/map_p07.png).

**Kết luận:**

- **Đọc scan được:** có, trên máy bàn (mục 3).
- **Tạo map được:** một phần, cùng mức **MỘT PHẦN** ở [gate_01.md](gate_01.md). Có bản đồ lưới tĩnh `map_p07` từ 181 vòng
  p07 ở một vị trí cố định (mục 5), lưu và nạp lại được. Chưa phải bản đồ SLAM: không có tư thế ước lượng, chưa ghép
  nhiều vị trí, chưa đo sai số bản đồ vì chưa có tham chiếu độc lập.
- **Định vị lại được:** có công cụ. Công cụ nhất quán ở cùng chỗ và không nhận bừa ở chỗ khác. **Chưa đạt** theo kế
  hoạch, vì chưa có vị trí tham chiếu độc lập nào nên chưa có sai số thật.

**Phát hiện mới: live_headless lệch hướng +4,3° so với p07**, trong khi vị trí gần như không đổi. So hồ sơ khoảng cách
theo góc của hai bản ghi, một cách không dùng bản đồ, cũng cho độ dịch −4,25…−4,5°. Có hai khả năng, chưa phân biệt
được:

- (a) thiết bị bị xoay nhẹ trên bàn giữa hai lần ghi;
- (b) gốc góc của C1 đổi giữa hai lần khởi động mô-tơ.

Khả năng (b) ảnh hưởng tới hướng của LiDAR so với xe ở mỗi lần bật.

**Rà soát bộ định vị (24/09/2026).** Chi tiết ở [DINH_VI_LIDAR.md](DINH_VI_LIDAR.md) mục 2–5. Đã sửa sáu lỗi:

- tóm tắt hướng tính trên vòng tròn (trước đó hướng ≈ 180° cho trung vị ≈ 0°);
- kiểm tia xuyên tường nối hai ô chéo nhau (trước đó tường chéo có khe);
- lý do mới `no_overlap` khi không tia nào kiểm được (trước đó báo nhầm là mâu thuẫn với bản đồ);
- từ chối cửa sổ tìm âm hoặc không hữu hạn;
- màu `overlay.png`: FAILED trước đó trùng màu tường, OK gần trùng chấm gốc bản đồ. Mọi `overlay.png` cũ không dán vào
  khóa luận;
- lệnh mẫu dán được vào cmd.exe và PowerShell.

Chạy lại trên ba bản ghi: không vòng nào đổi kết luận, tư thế giữ nguyên. Kiểm xuyên tường tốn thêm vài ms mỗi vòng. Test
tăng từ 17 lên 29. Kiểm đột biến ([DINH_VI_LIDAR.md](DINH_VI_LIDAR.md) mục 4): gỡ bất kỳ bản sửa nào trong mã, hay bất kỳ
kiểm OK/AMBIGUOUS/FAILED nào, đều làm ít nhất một test hỏng. Hai ngoại lệ không có test: màu nền dải chữ trên overlay
(chỉ là thẩm mỹ) và bản sửa lệnh mẫu (nằm trong tài liệu). Các ý kết luận ở trên không đổi.

**Việc còn lại**, cần người và thiết bị, làm cùng buổi với mục 6 ([DINH_VI_LIDAR.md](DINH_VI_LIDAR.md) mục 7):

1. Ghi hai phiên liên tiếp mà không chạm vào C1, khởi động lại mô-tơ giữa hai phiên, để kiểm khả năng (b).
2. Dời C1 tới 3–6 vị trí và hướng đo bằng thước / thước đo góc, định vị trên bản đồ ghi ở gốc, rồi so với số đo thước.
3. Chốt các ngưỡng tạm của bộ định vị.
