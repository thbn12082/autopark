# Giai đoạn 1 — nhánh LiDAR: nhận RPLIDAR C1, driver, ghi phiên, bản đồ tĩnh (22/09/2026)

**Kế hoạch đối chiếu:** [v3.1, mục 5 "Khi nhận LiDAR"](../../KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md), bước 1–3 và 5. *Thêm 24/09/2026:* bước 6 (nạp lại bản đồ, định vị) có công cụ và kết quả trên bản ghi sẵn, chưa có tham chiếu độc lập — mục 8 và [DINH_VI_LIDAR.md](DINH_VI_LIDAR.md).
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
| *(thêm muộn tối 24/09/2026)* Độ lặp lại khoảng cách trên cảnh tĩnh: ghép tia hai vòng liên tiếp theo góc, độ lệch chuẩn theo ô góc đã khử dốc, bỏ tia không phản hồi, bỏ giây đầu; JSON + PNG | `lidar/repeatability.py` | 13 test (`tests/test_lidar_repeatability.py`: dữ liệu tổng hợp có nhiễu biết trước, hai test tái lập số trên p07/k01 thật); chạy offline trên p07, live_headless, k01 (mục 3c). *Sau rà soát, muộn tối 24/09/2026: 20 test, xem cuối mục 3c.* |
| *(thêm 24/09/2026)* Định vị một vòng quét trên bản đồ đã lưu: trường khoảng cách, khớp tương quan nhánh-cận, tinh chỉnh Gauss-Newton, báo OK / AMBIGUOUS / FAILED | `lidar/localize.py` | 29 test trên phòng tổng hợp (`tests/test_lidar_localize.py`; 17 lúc viết, thêm 12 sau đợt rà soát cùng ngày); chạy offline trên p07, live_headless, k01 (mục 8) |

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

*Thêm 24/09/2026.* Ghi bằng `python -m autopark.lidar.bench record` trên máy bàn, mã ở commit `8293120`. Theo meta: COM4, `--warmup 3`, `--seconds 15`, không đặt vật, ghi chú "kiểm LiDAR có hỏng không, 24/09". LiDAR đã được dời chỗ sau 22/09; vị trí mới không được ghi lại. Bản ghi: `runs/lidar_bench/20260924_kiem/k01_kiem_suc_khoe.{npz,json,analysis.json,png}` (git-ignored; chưa chép bản nhỏ vào `docs/evidence/lidar/`). *(Tối 24/09/2026: trong `docs/evidence/lidar/` chỉ có ảnh định vị k01 trên bản đồ p07, mục 8; hình vòng quét và phân tích của k01 vẫn chưa chép.)* *(Muộn tối 24/09/2026: đã chép hình vòng quét cuối [k01_kiem_suc_khoe.png](evidence/lidar/k01_kiem_suc_khoe.png), phân tích [k01_kiem_suc_khoe.analysis.json](evidence/lidar/k01_kiem_suc_khoe.analysis.json) và meta [k01_kiem_suc_khoe.json](evidence/lidar/k01_kiem_suc_khoe.json); ba tệp trùng từng byte với tệp trong `runs/`. Bản ghi `.npz` (418 KB) không chép.)*

- GET_INFO trả cùng thiết bị (serial `f57ffc8b…`, firmware 1.2, phần cứng 18); GET_HEALTH OK.
- 151 vòng được ghi trong 15,0 s (driver đếm 162 vòng, gồm 11 vòng lúc làm nóng); 0 lỗi đọc, 0 byte lệch, 0 vòng bị bỏ, 0 lần đóng vòng theo điểm góc.
- Tần số gộp 9,98 Hz (p07: 10,09 Hz); trung vị 512 tia/vòng (492–552). Chênh lệch là do đoạn khởi động mô-tơ nằm trong bản ghi, chưa thấy dấu hiệu thiết bị thay đổi. Ở p07 (ghi từ vòng đầu) mô-tơ lúc đầu quay nhanh (≈ 400 tia/vòng, vòng ≈ 78 ms theo đồng hồ thô), sau đó chậm lại (tới 536 tia/vòng ở ≈ 1,3 s), rồi mới ổn định quanh 510. Số tia/vòng tỉ lệ với chu kỳ vòng vì thiết bị lấy mẫu đều 5 kHz. `--warmup 3` tính từ ngay sau lệnh SCAN, mà node đầu tới sau ≈ 2,2 s (p07, live_headless), nên làm nóng chỉ bỏ 11 vòng đầu và k01 vẫn chứa pha chậm: 492 → 552 → 500 tia trong ≈ 1,4 s đầu bản ghi. Bỏ 3 s đầu của mỗi bản ghi thì cả hai ngày đều ≈ 10,0 Hz và 504–516 tia/vòng (trung bình ≈ 510; p07 còn 149 vòng, k01 còn 121 vòng). Stamp có bước 15,6 ms (ghi chú về đồng hồ ở mục 3), nên không ghi thêm chữ số thập phân.
- Độ lặp lại khoảng cách trên mặt tĩnh: ghép mỗi tia với tia gần góc nhất của vòng trước (lệch góc < 0,1–0,2°), chỉ lấy phản hồi 0,2–4 m, bỏ 3 s đầu. Trung vị |chênh| 1,0–1,25 mm ở p07 và 1,25–1,5 mm ở k01 tùy dung sai góc; p90 4–8 mm. Tính bằng script tạm ngày 24/09, không lưu trong repo. Đây là độ lặp lại giữa hai vòng, không phải sai số so với thước. *(Muộn tối 24/09/2026: script tạm đã mất. Phép tính được viết lại theo đúng mô tả này thành `lidar/repeatability.py` và cho lại đúng các số trên; xem mục 3c.)*
- Tia không phản hồi 21,1 % (p07: 34,6 %); phản hồi 0,14–12,85 m. Vùng không phản hồi thay đổi theo cảnh vì LiDAR đã dời chỗ, nên hai tỉ lệ này không so sánh được với nhau.

Kết luận: giao tiếp, tần số quét và số tia không có dấu hiệu hỏng. **Sai số khoảng cách so với thước vẫn chưa đo** (mục 6). Còn mở:
- Đỉnh khởi động 552 tia, cao hơn 536 (p07) và 540 (live_headless). Mới có ba lần khởi động được ghi (hai lần ngày 22/09, một lần ngày 24/09), chưa đủ để kết luận.
- k01 có 268 tia rất gần (0,135–0,173 m) với chất lượng ≤ 6 (trung vị chất lượng mọi phản hồi của k01 là 24), trong 130/151 vòng, quanh −56…−52° và −30…−28° theo quy ước dự án (tức 52–56° và 28–30° theo chiều kim đồng hồ ở quy ước thiết bị; dấu trái/phải chưa xác minh, mục 6b). p07 và live_headless (chỗ đặt cũ) cũng có tia gần chất lượng thấp ở hai vùng này, rộng hơn (p07: −70…−46° và −30…−22°), cùng các phản hồi gần khác của vật sát cảm biến ở chỗ đặt cũ. Chưa rõ là vật gì (nghi dây cáp; chưa kiểm).

## 3c. Độ lặp lại khoảng cách: công cụ trong repo và kết quả chạy lại (thêm muộn tối 24/09/2026)

Script tạm tính độ lặp lại ở mục 3b không được lưu. Muộn tối 24/09/2026, phép tính được viết lại theo đúng mô tả ở mục 3b thành `lidar/repeatability.py`. Công cụ chạy offline trên máy bàn, không mở thiết bị. Mã gốc đã mất, nên "tái lập" ở đây chỉ có nghĩa: cùng mô tả phương pháp cho cùng các số. Không chứng minh được hai mã giống hệt nhau.

Lệnh (trong `autopark`, một dòng, dán được vào cmd.exe):

```
.venv\Scripts\python.exe -X utf8 -m autopark.lidar.repeatability runs/lidar_bench/20260922/p07_nen_phong.npz runs/lidar_bench/20260922/live_headless.npz runs/lidar_bench/20260924_kiem/k01_kiem_suc_khoe.npz --out runs/lidar_bench/do_lap_lai
```

Mỗi bản ghi cho `<tên>.repeatability.json` và `<tên>.repeatability.png`; thêm một tệp gộp `repeatability_summary.json`. *(Sau rà soát, muộn tối 24/09/2026: nếu hai bản ghi khác thư mục trùng tên tệp, ví dụ `lidar/part_0000.npz` của hai phiên bàn thử, thì tên tệp ra được thêm dần tên thư mục cha, ví dụ `o03_20260924__lidar__part_0000.repeatability.json`; trước đó tệp ra của bản ghi sau ghi đè bản ghi trước mà không báo. Mỗi mục trong tệp gộp ghi đường dẫn bản ghi như đã gõ (`path`) và tên hai tệp ra (`outputs`). Nêu cùng một bản ghi hai lần thì bị từ chối như lỗi dòng lệnh. Ba bản ghi ở lệnh trên không trùng tên, nên tên tệp ra không đổi.)* Bộ lọc mặc định giống mục 3b: bỏ tia không phản hồi (NaN, không tính là 0), chỉ lấy phản hồi 0,2–4 m, bỏ 3 s đầu tính từ vòng đầu của bản ghi. Có hai phép tính:
- **Theo tia, giữa hai vòng liên tiếp** (phép tính của mục 3b): mỗi tia ghép với tia gần góc nhất của vòng trước, có xét vòng qua ±180°; chỉ nhận cặp lệch góc < 0,1° (hoặc < 0,2°); thống kê |Δr|.
- **Theo ô góc 0,5°** (mới): gom mọi tia của các vòng đã chọn theo ô góc. Góc tia xê dịch giữa các vòng, nên trên mặt nghiêng khoảng cách đổi theo góc ngay trong một ô. Trong mỗi ô, khử độ dốc đó bằng hồi quy tuyến tính khoảng cách theo góc, rồi lấy độ lệch chuẩn phần dư. Tóm tắt bằng trung vị và p90 qua các ô. Một ô chỉ được tính khi có ≥ 10 mẫu và ≥ 50 % số tia rơi vào ô qua bộ lọc.

| Bản ghi (số vòng dùng) | \|Δr\|, lệch góc < 0,1°: trung vị / p90 (số cặp) | \|Δr\|, lệch góc < 0,2°: trung vị / p90 (số cặp) | Độ lệch chuẩn theo ô 0,5°, đã khử dốc: trung vị / p90 (số ô) |
|---|---|---|---|
| p07, 22/09 (149) | 1,00 / 4,25 mm (8.922) | 1,25 / 6,00 mm (16.924) | 1,56 / 44,8 mm (286) |
| live_headless, 22/09 (28) | 0,75 / 4,25 mm (1.892) | 1,00 / 5,50 mm (3.174) | 0,89 / 6,41 mm (282) |
| k01, 24/09 (121) | 1,25 / 5,50 mm (9.295) | 1,50 / 7,75 mm (19.173) | 1,39 / 3,43 mm (429) |

Đối chiếu với số đã ghi ở mục 3b và TONG_HOP_DU_AN.md mục 4.3:
- p07 cho 1,0–1,25 mm và k01 cho 1,25–1,5 mm tùy dung sai góc: **trùng** số đã ghi. p90 là 4,25–7,75 mm, nằm trong khoảng "4–8 mm" đã ghi.
- live_headless không có trong số đã ghi. Sau khi bỏ 3 s, bản ghi này chỉ còn 28 vòng. Trung vị của nó là 0,75–1,0 mm, thấp hơn khoảng "1,0–1,5 mm" ở TONG_HOP. Tính cả live_headless thì khoảng trung vị là 0,75–1,5 mm. Chưa rõ vì sao thấp hơn; bản ghi ngắn, ghi 2,5 phút sau p07 ở cùng chỗ đặt.
- Trung vị luôn là bội của 0,25 mm, vì C1 gửi khoảng cách theo bước 1/4 mm (JSON ghi `range_step_mm: 0.25`, nghĩa là mọi khoảng cách hữu hạn của bản ghi là bội của 0,25 mm; đã kiểm trên cả ba bản ghi). "1,0 so với 1,25 mm" chỉ cách nhau một bậc lượng tử.
- Hai phép tính cho cùng cỡ: trung vị |Δr| là 0,75–1,5 mm (ba bản ghi, hai dung sai góc), trung vị độ lệch chuẩn theo ô 0,5° (đã khử dốc) là 0,89–1,56 mm. Nếu nhiễu của mỗi vòng là Gauss độc lập với độ lệch chuẩn σ thì trung vị |Δr| ≈ 0,95σ, tức σ suy từ |Δr| ≈ 0,79–1,57 mm; đây là giả định, CHƯA KIỂM. *(Sửa sau rà soát, muộn tối 24/09/2026: câu cũ ghi "trung vị ≈ 0,9–1,6 mm" cho cả hai phép tính, không khớp trung vị |Δr| 0,75 mm của live_headless ở bảng trên.)*
- p90 theo ô của p07 lớn (44,8 mm): 66/286 ô có độ lệch chuẩn > 10 mm. Các ô này gom ở vài vùng góc (quanh −95…−90°, −13…+20°, 121…155°). Ở 74 % số ô đó, 1,4826 × MAD nhỏ hơn nửa độ lệch chuẩn, tức là vài giá trị nhảy xa chứ không phải nhiễu đều. Điều này hợp với mép vật hoặc phản hồi chập chờn, nhưng chưa kiểm bằng mắt từng vùng. k01 chỉ có 11/429 ô như vậy.

Bằng chứng (máy bàn, muộn tối 24/09/2026, chỉ chép phần nhỏ). Lần chạy đầu ra một thư mục tạm của phiên làm việc. *Sau rà soát cùng tối, chạy lại bằng mã đã sửa với đúng lệnh trên, ra `runs/lidar_bench/do_lap_lai` (git-ignored): mọi số trong bảng không đổi, chỉ hash mã, mốc giờ, lệnh và các trường mới `path`/`outputs` khác. Tệp tóm tắt dưới là của lần chạy lại.*
- tóm tắt đủ ba bản ghi, kèm lệnh, tham số và hash mã `repeatability.py` lúc chạy (sha256 sau khi đổi CRLF→LF, kiểm lại bằng `git show <commit>:autopark/autopark/lidar/repeatability.py` rồi sha256; mã chưa commit lúc viết; *cập nhật 25/09/2026:* mã đã commit ở `a7cec5e`, và sha256 ghi trong tệp trùng sha256 của `repeatability.py` ở `a7cec5e` và ở `54cb3e2`): [do_lap_lai_20260924.json](evidence/lidar/do_lap_lai_20260924.json);
- hình, bên trái là độ lệch chuẩn theo góc, bên phải là tần suất |Δr| với dung sai 0,1°: [do_lap_lai_p07_nen_phong.png](evidence/lidar/do_lap_lai_p07_nen_phong.png), [do_lap_lai_k01_kiem_suc_khoe.png](evidence/lidar/do_lap_lai_k01_kiem_suc_khoe.png).

Giới hạn:
- Đây là độ lặp lại giữa các vòng trên cảnh tĩnh, **không phải sai số so với thước**. Sai số so với thước vẫn chưa đo (mục 6).
- p07 và live_headless ghi không làm nóng. Mốc bỏ 3 s tính từ vòng đầu của bản ghi, không phải từ lệnh SCAN.
- Chưa tách kết quả theo khoảng cách hay theo loại bề mặt.

Kiểm chứng: `tests/test_lidar_repeatability.py`, 13 test. Các test dùng dữ liệu tổng hợp có nhiễu biết trước; hai test chạy trên p07/k01 thật nếu có trong `runs/` (thiếu thì bỏ qua). Kiểm đột biến trên bản sao, không sửa repo: 9/9 đột biến bị ít nhất một test bắt. Chín đột biến là: bỏ khử dốc, giữ tia NaN, bỏ phần bỏ giây đầu, bỏ xử lý vòng qua ±180°, bỏ dung sai góc, bỏ lọc khoảng cách, bỏ lọc chất lượng, bỏ hệ số 1,4826, ghép hai vòng không liền nhau.

*Sau rà soát, muộn tối 24/09/2026:* 20 test (thêm 7). Rà soát chỉ ra hai quy tắc nhận ô (≥ 10 mẫu, ≥ 50 % số tia trong ô có phản hồi) và phép kiểm bậc 0,25 mm không có test nào giữ: bỏ quy tắc 50 % thì p07 đổi từ 1,56 / 44,8 mm (286 ô) thành 2,70 / 129,5 mm (433 ô; tính lại offline trên máy bàn bằng `min_bin_return_fraction=0`) mà 13 test cũ vẫn đạt. Test mới:
- ô có nhiều tia không phản hồi (cung 20–50° chỉ ≈ 30 % tia có phản hồi) không được tính;
- ô cần đủ 10 mẫu (9 vòng: 0 ô, 10 vòng: 512 ô);
- `range_step_mm` là `None` khi khoảng cách không theo bậc 0,25 mm;
- hai test trên bản ghi thật giữ thêm số theo ô của bảng trên (286 ô, 1,56 / 44,8 mm cho p07; 429 ô, 1,39 / 3,43 mm cho k01);
- hai bản ghi trùng tên tệp giữ đủ hai bộ tệp ra; tên tệp ra chỉ dài thêm khi trùng; cùng một bản ghi nêu hai lần bị từ chối (mã thoát 2);
- hash mã như nhau với tệp LF và CRLF.

Kiểm đột biến lại trên bản sao, không sửa repo: 9 đột biến cũ và 10 đột biến mới của `repeatability.py`, cả 19 đều bị ít nhất một test bắt. Mười đột biến mới: đặt tên tệp ra chỉ theo tên bản ghi, nhận cùng một bản ghi hai lần, thêm thư mục cha cho mọi tên, bỏ trường `path`, hash byte thô, bỏ quy tắc 50 %, hạ 50 % xuống 25 %, hạ 10 mẫu xuống 3, đổi `>=` thành `>` ở số mẫu, luôn báo bậc 0,25 mm.

## 4. Giám sát dữ liệu cũ trên thiết bị thật

`live_view` chạy headless 8 s với COM4: luồng đọc ở thread riêng, `FreshnessMonitor` với tuổi tối đa 0,3 s (≈3 chu kỳ) và chu kỳ mong đợi 0,094 s (lấy theo trung vị p07, là số bị lượng tử hóa — xem ghi chú 24/09 ở mục 3; mặc định của `live_view` và ngăn LiDAR là 0,1 s); trạng thái OK trong suốt phiên, bản ghi `live_headless.npz` được đóng đúng khi cửa sổ đóng. **Chưa thử rút cáp** để xem STALE_DATA phát trên thiết bị thật; cách thử: chạy `python -m autopark.lidar.live_view --port COM4`, rút cáp USB, tiêu đề phải đổi màu và dòng trạng thái báo `STALE_DATA` sau 0,3 s.

## 5. Bản đồ lưới tĩnh và thử odometry DROW

- Từ p07 (cảm biến cố định, lưới 8 × 8 m, ô 5 cm, tầm 8 m): 5.657 ô FREE, 230 ô OCCUPIED, còn lại UNKNOWN; [map_p07.png](evidence/lidar/map_p07.png); `costmap.json` cùng bố cục với costmap camera nên có thể hợp nhất sau. Chưa có tham chiếu độc lập để đo sai số bản đồ.
- DROW val `run_2015-11-25-10-34-20-a`, 300 vòng đầu, tư thế lấy từ `.odom2` ghép theo dòng: bản đồ theo quy ước loader v2 (không mirror) cho hành lang mỏng, rõ ([drow_odom_map.png](evidence/lidar/drow_odom_map.png), sharpness 0,30); đảo dấu góc cho vệt loang ([drow_odom_mirror_map.png](evidence/lidar/drow_odom_mirror_map.png), 0,18); giữ cảm biến cố định cho 0,13 ([drow_fixed_map.png](evidence/lidar/drow_fixed_map.png); *link thêm tối 24/09/2026*, ảnh đã có trong `evidence/` từ 22/09 nhưng trước đây mục này chưa link). Đây là bằng chứng gián tiếp rằng odometry DROW dùng cùng chiều với góc quét, chưa phải kiểm chứng SLAM. `.odom2` có seq không trùng seq của file scan (ghép theo dòng như loader gốc) và 23 dòng lặp.
- *Thêm tối 24/09/2026, cách dựng lại ba ảnh DROW* (trong `autopark`, `.venv`, dữ liệu `datasets/drow/` bị git-ignore; mỗi lệnh một dòng, dán được vào cmd.exe và PowerShell):

  ```
  .\.venv\Scripts\python.exe -X utf8 -m autopark.lidar.occupancy --drow datasets/drow/DROWv2-data/val/run_2015-11-25-10-34-20-a.bag.csv --scans 300 --grid -12 12 -12 12 0.1 --max-range 10 --out <thư mục>
  .\.venv\Scripts\python.exe -X utf8 -m autopark.lidar.occupancy --drow datasets/drow/DROWv2-data/val/run_2015-11-25-10-34-20-a.bag.csv --scans 300 --grid -12 12 -12 12 0.1 --max-range 10 --odom --out <thư mục>
  .\.venv\Scripts\python.exe -X utf8 -m autopark.lidar.occupancy --drow datasets/drow/DROWv2-data/val/run_2015-11-25-10-34-20-a.bag.csv --scans 300 --grid -12 12 -12 12 0.1 --max-range 10 --odom --mirror --out <thư mục>
  ```

  Lần lượt cho ảnh cố định, theo `.odom2`, đảo dấu góc. Tham số: 300 vòng đầu (`--start` mặc định 0), lưới 24 × 24 m ô 0,1 m, tầm 10 m; `--min-passes 3`, `--min-hits 2`, `--occupied-ratio 0.2` để mặc định. `costmap.json` không ghi tầm quét, nên tham số tầm được xác nhận bằng cách dựng lại: tối 24/09/2026 chạy ba lệnh trên vào thư mục tạm, `map.png` trùng từng byte với ba tệp trong `evidence/lidar/`, lưới `costmap.json` của ảnh cố định trùng từng ô với `runs/lidar_bench/20260922/drow_fixed/`; bỏ `--max-range 10` (tầm mặc định 12 m) thì ảnh cố định khác (739 ô OCCUPIED thay vì 660). Sharpness phụ thuộc lưới và tầm, nên trích số 0,30 / 0,18 / 0,13 phải kèm tham số này. Hình dựng từ DROW phải ghi công theo [GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md) (trích cả hai bài DROW).

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
- Bản đồ tĩnh không phải SLAM: không ước lượng tư thế, không nạp lại, không định vị. *Cập nhật 24/09/2026:* đã có nạp lại bản đồ và định vị từng vòng quét trên bản đồ cố định (mục 8). Vẫn không phải SLAM: bản đồ không được cập nhật, không có odometry. *Cập nhật 25/09/2026:* có thêm odometry khớp scan và bản đồ tăng dần (`lidar/scan_odometry.py`, commit `a7cec5e`), mới thử offline trên DROW v2 và sáu bản ghi C1 đứng yên; so sánh các phương án và đề xuất cho V1 (ĐỀ XUẤT – CHỜ CHỐT) ở [SO_SANH_DINH_VI_SLAM.md](SO_SANH_DINH_VI_SLAM.md). Trên C1 thật chưa có bản đồ nào dựng khi cảm biến di chuyển.
- Phiên p07 chưa làm nóng và không có vật tham chiếu; số tia/tần số coi là ổn định, sai số khoảng cách thì chưa. *Cập nhật 24/09/2026:* ở trạng thái ổn định, số tia và tần số lặp lại ở k01 (mục 3b); sai số khoảng cách vẫn chưa đo.
- *Cập nhật 24/09/2026:* sau phiên p07, LiDAR đã chạy chung bốn camera + AI trên bàn thử ở máy bàn ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md)): ba phiên 10 phút s07, t09, u04 được 6006 / 6005 / 6006 vòng, 0 lỗi đọc, 0 vòng mất (t09 và u04 trung bình 10,01 Hz; s07 thuộc loạt đầu, đồng hồ thô, không lấy số thời gian), và năm phiên 60–120 s ngày 24/09 (w01–w05, 10,01–10,02 Hz, 0 lỗi đọc, 0 vòng mất). Độ lệch lúc về máy giữa vòng LiDAR và bộ ảnh ở mục 3.2 của tài liệu đó. LiDAR thật đứng yên làm nền để xe ảo lập đường và đỗ xong quanh đồ vật thật ở [GIAI_DOAN_3_CHUAN_BI.md](GIAI_DOAN_3_CHUAN_BI.md) mục 3; chưa thử đưa vật vào để xe ảo dừng. Vẫn chưa đo: nhiệt của LiDAR, độ trễ từ sự kiện thật tới lúc vòng quét về máy, cáp dài hay hub, và mọi số trên laptop RTX 3050 Ti (máy nộp đồ án).

## 8. Định vị lại trên bản đồ tĩnh (thêm 24/09/2026)

Bước 6 của kế hoạch: *"Nạp lại bản đồ, thử định vị tại các vị trí có tham chiếu độc lập."* Công cụ là
`python -m autopark.lidar.localize`. Phương pháp, tham số, test và giới hạn nằm ở [DINH_VI_LIDAR.md](DINH_VI_LIDAR.md).
Ngày 24/09 chỉ chạy offline trên các bản ghi có sẵn, không chạy thiết bị. Bản đồ dùng là `map_p07` (mục 5). Dựng lại bản
đồ này bằng mã hiện tại cho lưới giống hệt từng ô.

| Bản ghi | Kết quả (cửa sổ ±0,5 m / ±30° quanh gốc) |
|---|---|
| p07 (chính dữ liệu dựng bản đồ, không độc lập) | 181/181 OK. Tư thế (−1,3 mm; −3,3 mm; +0,01°); độ lệch chuẩn giữa các vòng 1,4 / 1,8 mm, 0,05° |
| live_headless (22/09, 2,5 phút sau p07) | 60/60 OK. Tư thế (−1,1 mm; −6,8 mm; **+4,33°**); độ lệch chuẩn 2,6 / 2,7 mm, 0,07°. Tìm trên cả bản đồ (`--global`) cho cùng kết quả |
| k01 (24/09, LiDAR đã dời chỗ) | 151/151 FAILED (tỉ lệ khớp trung vị 0,24, mâu thuẫn với bản đồ). Tìm trên cả bản đồ (31 vòng): 31/31 FAILED |

*Thêm tối 24/09/2026 — bằng chứng trong git.* Chạy lại offline trên máy bàn các lệnh ở [DINH_VI_LIDAR.md](DINH_VI_LIDAR.md) mục 3 (bản đồ `runs/lidar_bench/20260922/map_p07`, không chạy thiết bị), ra thư mục tạm, rồi chỉ chép ảnh overlay và một tệp tóm tắt:
[dinh_vi_p07_tren_p07.png](evidence/lidar/dinh_vi_p07_tren_p07.png),
[dinh_vi_live_headless_tren_p07.png](evidence/lidar/dinh_vi_live_headless_tren_p07.png),
[dinh_vi_k01_tren_p07.png](evidence/lidar/dinh_vi_k01_tren_p07.png),
[dinh_vi_k01_global_tren_p07.png](evidence/lidar/dinh_vi_k01_global_tren_p07.png) (`--global --every 5`),
tóm tắt [dinh_vi_tren_p07_20260924.json](evidence/lidar/dinh_vi_tren_p07_20260924.json) (lệnh, tham số, hash mã `localize.py` lúc đó chưa commit; *cập nhật 25/09/2026:* hash này trùng sha256 của `localize.py` trong commit `b100a5d` và ở `54cb3e2`, kết quả từng lần chạy, kể cả `--track` và `--global` của live_headless). Trạng thái và tư thế trùng bảng trên: p07 181/181 OK, trung vị (−1,3 mm; −3,3 mm; +0,008°); live_headless 60/60 OK, (−1,1 mm; −6,8 mm; +4,33°), `--track` và `--global` cũng 60/60 OK cùng tư thế; k01 151/151 FAILED; k01 `--global --every 5` 31/31 FAILED. Thời gian mỗi vòng trong tệp tóm tắt đo lúc máy đang chạy việc khác song song, không thay số ở DINH_VI_LIDAR.md mục 5. Ảnh overlay chỉ cho thấy độ **nhất quán**, không phải độ đúng; chưa có tham chiếu độc lập. Trước khi chạy, bản đồ `map_p07` cũng được dựng lại từ p07 bằng `autopark.lidar.occupancy`: lưới trùng từng ô, `map.png` trùng từng byte với [map_p07.png](evidence/lidar/map_p07.png).

Kết luận:
- **Đọc scan được:** có, trên máy bàn (mục 3).
- **Tạo map được:** một phần, cùng mức **MỘT PHẦN** ở [gate_01.md](gate_01.md). Có bản đồ lưới tĩnh `map_p07` từ 181 vòng
  p07 ở một vị trí cố định (mục 5), lưu và nạp lại được. Chưa phải bản đồ SLAM: không có tư thế ước lượng, chưa ghép nhiều
  vị trí, chưa đo sai số bản đồ vì chưa có tham chiếu độc lập. *(Sửa tối 24/09/2026: bản trước của dòng này ghi "có
  (mục 5)", khác mức gate_01 chấm; dòng "Đọc scan được" chỉ thêm "trên máy bàn".)*
- **Định vị lại được:** có công cụ. Công cụ nhất quán ở cùng chỗ và không nhận bừa ở chỗ khác. **Chưa đạt** theo kế hoạch
  vì chưa có vị trí tham chiếu độc lập nào, nên chưa có sai số thật.

Phát hiện mới: live_headless lệch hướng +4,3° so với p07 trong khi vị trí gần như không đổi. So hồ sơ khoảng cách theo góc
của hai bản ghi, một cách không dùng bản đồ, cũng cho độ dịch −4,25…−4,5°. Có hai khả năng, chưa phân biệt được:
(a) thiết bị bị xoay nhẹ trên bàn giữa hai lần ghi;
(b) gốc góc của C1 đổi giữa hai lần khởi động mô-tơ.
Khả năng (b) ảnh hưởng tới hướng của LiDAR so với xe ở mỗi lần bật.

*Ghi chú 24/09/2026, sau đợt rà soát bộ định vị* (chi tiết ở [DINH_VI_LIDAR.md](DINH_VI_LIDAR.md) mục 2–5). Đã sửa
sáu lỗi:
- tóm tắt hướng tính trên vòng tròn (trước đó hướng ≈ 180° cho trung vị ≈ 0°);
- kiểm tia xuyên tường nối hai ô chéo nhau (trước đó tường chéo có khe);
- lý do mới `no_overlap` khi không tia nào kiểm được (trước đó báo nhầm là mâu thuẫn với bản đồ);
- từ chối cửa sổ tìm âm hoặc không hữu hạn;
- màu `overlay.png`: FAILED trước đó trùng màu tường, OK gần trùng chấm gốc bản đồ. Mọi `overlay.png` cũ không dán vào
  khóa luận;
- lệnh mẫu dán được vào cmd.exe và PowerShell.

Chạy lại trên ba bản ghi: không vòng nào đổi kết luận, tư thế giữ nguyên. Kiểm xuyên tường tốn thêm vài ms mỗi vòng.
Test tăng từ 17 lên 29. Kiểm đột biến ([DINH_VI_LIDAR.md](DINH_VI_LIDAR.md) mục 4): gỡ bất kỳ bản sửa nào trong mã,
hay bất kỳ kiểm OK/AMBIGUOUS/FAILED nào, đều làm ít nhất một test hỏng. Hai ngoại lệ không có test: màu nền dải chữ
trên overlay (chỉ là thẩm mỹ), và bản sửa lệnh mẫu (nằm trong tài liệu). Các ý kết luận ở trên không đổi.

Việc còn lại, cần người và thiết bị, làm cùng buổi với mục 6 ([DINH_VI_LIDAR.md](DINH_VI_LIDAR.md) mục 7):
1. Ghi hai phiên liên tiếp mà không chạm vào C1, khởi động lại mô-tơ giữa hai phiên, để kiểm khả năng (b).
2. Dời C1 tới 3–6 vị trí và hướng đo bằng thước / thước đo góc, định vị trên bản đồ ghi ở gốc, rồi so với số đo thước.
3. Chốt các ngưỡng tạm của bộ định vị.
