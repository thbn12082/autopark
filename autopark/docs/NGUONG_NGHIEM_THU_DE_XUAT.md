# Ngưỡng nghiệm thu V1 — bản đề xuất cho kế hoạch mục 16.2 (24/09/2026)

> **Ghi công theo giấy phép dữ liệu:** các số AI trích ở mục 8 là của mô hình huấn luyện trên **Valeo WoodScape Dataset**
> (<https://woodscape.valeo.com>). Giới hạn sử dụng: [GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md).

**Kế hoạch đối chiếu:** [v3.1](../../KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) mục 16.2 (bảy nhóm ngưỡng "cần chốt"), 16.1 (mốc
thử khởi đầu), 16.4 (điều kiện hoàn thành V1), 13 (giai đoạn 9), 14 (định nghĩa cách đo và thành công/thất bại trước khi
thu kết quả cuối). Bộ kịch bản dùng các ngưỡng này: [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md).

**Trạng thái: mọi ngưỡng trong tệp này là ĐỀ XUẤT – CHỜ CHỐT.** Chưa ngưỡng nào được người dùng hay GVHD duyệt. Tệp này
**không thêm số đo mới**: mỗi ngưỡng ghi căn cứ (tệp, mục, con số) và mức của căn cứ đó; chỗ nào không có số đo thì ghi
"chưa có số đo làm căn cứ". Kế hoạch mục 16.2 viết: "Không có đủ thông số xe/sa bàn/thực nghiệm để tự ghi một bộ ngưỡng
cuối". Tệp này chỉ là bản nháp để chốt, không phải bộ ngưỡng cuối.

Tình trạng làm nền (24/09/2026, theo [TONG_HOP_DU_AN.md](../../TONG_HOP_DU_AN.md)): chưa nhận MN300, ESP32-S3, phần nguồn và
dừng; firmware C++ chưa biên dịch; AI chưa nối vào costmap/planner (chờ quyết định giấy phép WoodScape); định vị LiDAR
mới chạy offline, chưa có tham chiếu độc lập. Mọi số đo phần cứng hiện có là trên **máy bàn** i9-14900 + RTX 4000 Ada
(22–24/09/2026). Trên laptop RTX 3050 Ti (máy nộp đồ án) chỉ có hồ sơ mô phỏng giai đoạn 0 (20/09/2026).

## 0. Cách đọc

**Mức căn cứ** (cột "Mức" trong các bảng):

| Nhãn | Nghĩa |
|---|---|
| ĐO-MB | số đo trên thiết bị thật, máy bàn, có phiên và tệp đo |
| MP | số của mô phỏng, với thông số xe giả định (`configs/vehicle_default.json`, `configs/vehicle_io_sim.json`) |
| TH | dữ liệu tổng hợp trong test |
| TK | giá trị thiết kế đang có trong mã hoặc cấu hình, chưa kiểm trên thiết bị thật |
| KH | lấy từ kế hoạch v3.1 |
| DL | số trên bộ dữ liệu công khai, không phải ảnh sa bàn |
| TÍNH | tính từ các số trên (phép tính ghi kèm), không phải số đo |
| — | chưa có số đo làm căn cứ |

**Hai loại ngưỡng.** *Tuyệt đối* là 0 lần vi phạm (chạm vật, tự chạy lại, ô FREE do thiếu dữ liệu…): một lần vi phạm là
không đạt, bất kể các lần khác. *Định lượng* là giới hạn số, kiểm trên từng lần chạy hoặc trên thống kê của cả loạt.

Mỗi ngưỡng có mã `N-…`. Mã kịch bản (`DO-1`, `VC-1`…) ở [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md). Mã phương pháp đo
độc lập (`R1`…`R7`) định nghĩa ở mục 2 của tệp đó.

**Quy tắc chung (đề xuất, CHỜ CHỐT):**

1. **Chốt trước khi thu kết quả cuối** (kế hoạch mục 14: "Chuẩn bị bảng kịch bản, cách đo độc lập và định nghĩa thành
   công/thất bại trước khi thu kết quả cuối"). Không nới ngưỡng sau khi xem kết quả. Muốn đổi thì ghi lý do và ngày, rồi
   chạy lại toàn bộ kịch bản dùng ngưỡng đó.
2. **Đo bằng tham chiếu độc lập** (kế hoạch mục 12: "không dùng cùng một đầu ra tự xác nhận chính nó"; mục 14: "Có tham
   chiếu độc lập cho sai số vị trí/hướng/khoảng cách"). Log của hệ thống chỉ dùng để đối chiếu, không dùng làm số nghiệm thu
   cho vị trí, hướng, khoảng hở hay quãng dừng.
3. **Tham chiếu phải chính xác hơn ngưỡng ít nhất 3 lần** (sai số của tham chiếu ≤ 1/3 ngưỡng cần kiểm). Tỉ lệ 3:1 là quy
   ước đề xuất, cần GVHD duyệt. Tham chiếu không đạt tỉ lệ này thì ngưỡng đó ghi "không kiểm được", không ghi "đạt". Tỉ lệ
   áp lên giá trị **lớn nhất** của ngưỡng (như N-L1: 3 cm → tham chiếu ≤ 1 cm); phần "trung vị" của ngưỡng báo kèm sai số
   tham chiếu, và chỉ ghi "đạt" khi tham chiếu cũng ≤ 1/3 trung vị. Sự kiện dùng làm dấu đồng bộ R7 không được là chính sự
   kiện của ngưỡng đang kiểm (thêm tối 24/09/2026, xem N-P5).
4. **Số thời gian và hiệu năng phải đo trên đúng máy chạy khi nghiệm thu.** Máy đó CHƯA CHỐT: laptop RTX 3050 Ti là máy nộp
   đồ án (người dùng xác nhận 24/09), còn laptop có đặt trên xe hay không là câu N1 ở
   [GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md) mục 2.1. Mọi số thời gian trích dưới đây là của máy bàn; vài phiên đo
   khi một dự án khác chạy cùng máy ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 3).
5. Các ngưỡng về phản ứng (mục 3) giả định tốc độ ≤ N-V1. Đổi tốc độ vận hành thì phải xét lại cả mục 3.

## 1. Tự đỗ (dòng "Tự đỗ" của bảng 16.2)

**Định nghĩa một lần đỗ THÀNH CÔNG (đề xuất):** hệ thống báo COMPLETED; **và** sai số vị trí, hướng cuối đo bằng tham chiếu
độc lập nằm trong N-D1, N-D2; **và** thân xe nằm trong ô (N-D3, khi kịch bản có ô); **và** không chạm vật (N-D4); **và**
không có can thiệp của người (N-D9); **và** không RUN_TIMEOUT (N-D7); **và** tốc độ đo không vượt N-V1. Một lần dừng an toàn
đúng thiết kế là **DỪNG ĐÚNG**: đúng chức năng, nhưng không phải hoàn thành nhiệm vụ đỗ (kế hoạch mục 14 bước 4). Các loại
kết quả khác và cách phân loại nguyên nhân: [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 1.4.

| Mã | Đại lượng | Ngưỡng đề xuất | Căn cứ | Mức | Đo bằng |
|---|---|---|---|---|---|
| N-D1 | Sai số vị trí cuối: tâm trục sau so với đích | ≤ 5 cm ở mọi lần tính thành công; báo trung vị và lớn nhất của cả loạt | `ParkingGoal.tolerance_xy` mặc định 0,05 m trong [domain/types.py](../autopark/domain/types.py), docstring ghi "Dung sai là mục tiêu thiết kế, chưa phải kết quả"; [sa_ban_3x2_hai_hop.json](../scenarios/sa_ban_3x2_hai_hop.json) ghi `tolerance_cm` 5,0. Mô phỏng: phiên parking / reverse / noisy sai 8,92 / 8,52 / 4,78 mm ([BAO_CAO_GIAI_DOAN_0.md](../../BAO_CAO_GIAI_DOAN_0.md) mục 7, laptop, 20/09); qua `VEHICLE_IO` và bo mô phỏng 0,60 cm, chế độ quan sát 0,73 cm, cả hai với định vị lý tưởng ([CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) mục 7). Xe thật: CHƯA ĐO | TK, MP | R1 hoặc R2; sai số tham chiếu phải ≤ 1,7 cm |
| N-D2 | Sai số hướng cuối | ≤ 5° | `ParkingGoal.tolerance_yaw` mặc định 5°. Mô phỏng: +1,15° (`VEHICLE_IO`), +1,27° (quan sát) (CHE_DO_QUAN_SAT.md mục 7). Định vị LiDAR có độ lệch hướng +4,33° giữa bản ghi p07 và live_headless, chưa rõ nguyên nhân ([DINH_VI_LIDAR.md](DINH_VI_LIDAR.md) mục 5). Nếu nguyên nhân là gốc góc đổi theo mỗi lần khởi động mô-tơ thì riêng lỗi này gần hết ngưỡng; phải xử lý trước (N-L4) | TK, MP, ĐO-MB | R1 (hai marker) hoặc R2; sai số tham chiếu phải ≤ 1,7° |
| N-D3 | Thân xe nằm trong ô | Tuyệt đối trong lần tính thành công: toàn bộ footprint (kể cả gá cảm biến sau giai đoạn 7) nằm trong vạch ô | Phần mềm có kiểm tương tự `Session.footprint_inside_slot` (dung sai 1 cm, [application/session.py](../autopark/application/session.py)); đó là kiểm của chính hệ thống, không phải tham chiếu | TK | R4 (ảnh từ trên, có vạch) + R2 |
| N-D4 | Chạm vật | Tuyệt đối: 0 lần trong mọi lần chạy của mọi kịch bản | Kế hoạch mục 13: kiểm sai số cuối vị trí, hướng **và** khoảng hở. Mô phỏng: 0 vi phạm bất biến (gồm va chạm theo oracle) trong 2.880 ca ([KIEM_THU_DO_BEN_GIAI_DOAN_0.md](KIEM_THU_DO_BEN_GIAI_DOAN_0.md) mục 2) | KH, MP | R3 (video) + R5 (viền băng dính quanh chân vật: vật bị xê dịch là đã chạm) |
| N-D5 | Khoảng hở nhỏ nhất thân xe – vật trong cả lần chạy | ≥ 2 cm ở kịch bản rộng (DO-1, DO-2, DO-4a); kịch bản hẹp chỉ áp N-D4 | Lề của planner ở nấc đầu là 3 cm (`_STAGES` `tho`/`min`, `RRTParams`); nấc hẹp chỉ còn 1,5 / 0,8 cm, nấc `lưới mịn` sàn 4 mm, và lề còn bị chặn ở nửa khoảng hở tại xuất phát/đích nên có thể về 0 ([GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md) mục 1.2). Lệch lớn nhất khỏi các điểm quỹ đạo của lần chạy `VEHICLE_IO` mô phỏng: 1,25 cm (CHE_DO_QUAN_SAT.md mục 7). 3 − 1,25 ≈ 1,75 cm, làm tròn 2 cm. Lệch bám của xe thật: CHƯA ĐO | TK, MP, TÍNH | R5 (cờ giấy đứng cách mặt vật 2 cm; đặt cờ ± 3 mm, ước tính). R1 chỉ dùng được cho ngưỡng này nếu kiểm tham chiếu (TC-1) cho sai số ≤ 0,7 cm |
| N-D6 | Đổi chiều | (a) số lần đổi chiều thực hiện bằng số lần của quỹ đạo đã lập, không thêm; (b) quỹ đạo đã lập có ≤ 2 lần đổi chiều ở kịch bản rộng (DO-1, DO-2, DO-3a, DO-4a), ≤ 7 lần ở kịch bản hẹp (DO-3b, DO-4b, DO-5, DO-6); DO-3c (loại `xtight`) chỉ báo số; (c) tuyệt đối: chỉ đổi chiều khi \|v đo\| ≤ 0,01 m/s | (b): phân nhóm ca mô phỏng trong [evaluation/hard_cases.py](../autopark/evaluation/hard_cases.py): `easy` 1–2 lần đổi chiều, `tight` 3–7, `xtight` "rất nhiều lần đẩy tới đẩy lui"; sa bàn `bai_do_xe.json` có 1 lần (CHE_DO_QUAN_SAT.md mục 7). (c): firmware đứng ở 0 ít nhất `direction_change_hold_ms` 300 ms (CHƯA CHỐT) và cần \|v đo\| ≤ `standstill_mm_s` 10 mm/s ([GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 7). Mã hiện không chặn đường có quá nhiều lần đổi chiều trước khi chạy: `portfolio` chỉ ưu tiên đường ít đổi chiều hơn (đọc mã 24/09/2026; công cụ T12 ở tệp kịch bản) | MP, TK | R6 (`commands.csv` cột `segment`, `telemetry.csv`) đối chiếu với R3 |
| N-D7 | Thời gian một lần đỗ | Không RUN_TIMEOUT (180 s); báo trung vị và lớn nhất; chưa đặt ngưỡng chặt hơn | `Session.MAX_RUN_TIME` = 180 s ([application/session.py](../autopark/application/session.py)). Sa bàn `bai_do_xe.json` qua `VEHICLE_IO` mô phỏng mất 20,95 s với `max_speed_mps` giả định 0,3 m/s (CHE_DO_QUAN_SAT.md mục 7); ở N-V1 thời gian sẽ khác. Chưa có số đo làm căn cứ cho ngưỡng chặt hơn | TK, MP | R3 |
| N-D8 | Tỉ lệ thành công qua N lần | Mục 10 | Mục 10 | TÍNH | Biên bản các lần chạy |
| N-D9 | Can thiệp của người | Tuyệt đối trong lần tính thành công: 0 lần (nhấn dừng, chạm tay vào xe, sửa sa bàn giữa chừng). Mọi can thiệp ghi thành THẤT BẠI kèm lý do | Kế hoạch mục 14 bước 4: "Ghi cả lần dừng bảo vệ, lỗi liên lạc và can thiệp của người giám sát" | KH | Biên bản + video R3 |

## 2. Tốc độ vận hành khi nghiệm thu

| Mã | Đại lượng | Ngưỡng đề xuất | Căn cứ | Mức | Đo bằng |
|---|---|---|---|---|---|
| N-V1 | Tốc độ lớn nhất khi nghiệm thu | Tốc độ mục tiêu ≤ 0,10 m/s ở đợt đầu; tốc độ đo (trung bình trên đoạn 0,2 m) ≤ 1,2 × 0,10 m/s. Chỉ nâng lên ≤ 0,15 m/s khi đã có B4 (chạy đều), B6 (quãng dừng) ở 0,15 m/s và N-P2 đo đạt ở 0,15 m/s | Kế hoạch mục 16.1: khảo sát 0,05–0,15 m/s và "chỉ chọn tốc độ vận hành trong phần miền đã đo phù hợp với khoảng dừng và khoảng hở". `max_speed_mps` = 0,3 m/s trong cấu hình là giả định ([GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md) mục 1.1). Kẹp tốc độ của firmware chỉ áp lên mục tiêu, không giới hạn tốc độ thật khi chạy mạch hở (GIAO_THUC_XE.md mục 7). Vòng tốc độ mô phỏng vọt lố 26–57 % (GIAO_THUC_XE.md mục 10), nên hệ số 1,2 là đề xuất, chưa có số đo. 0,10 m/s ở giữa miền của kế hoạch; với thời gian phát hiện xấu nhất theo thiết kế 0,3 s (N-P1) xe đi 3 cm ở 0,10 m/s, 4,5 cm ở 0,15 m/s (TÍNH). Chưa có số đo xe làm căn cứ | KH, TK, MP, TÍNH | R3 (video bên hông có thước; tốc độ = quãng / khoảng thời gian **thật** giữa hai khung), hoặc R1 |

## 3. Phản ứng với vật cản và lỗi (dòng "Phản ứng lỗi")

**Bốn mốc thời gian dùng chung:** `t_vật` là lúc vật vào hành lang thân xe (đọc từ video R3); `t_phát_hiện` là lúc phiên
phát sự kiện dừng đầu tiên (`Session.safety_events[0]`: `MAP_CHANGED`, `STALE_POSE`, `STALE_TELEMETRY`…); `t_lệnh_dừng` là
dòng STOP đầu tiên trong `commands.csv`; `t_đứng_yên` là khung video đầu tiên xe không còn dịch chuyển (R3), đối chiếu với
telemetry.

Ở mã hiện tại (đọc tối 24/09/2026) sự kiện dừng của phiên **không** được ghi ra tệp nào khi chạy qua `VehicleIO`:
`events.csv` chỉ có sự kiện của `VehicleIO` và lớp nối (`START_CHECK`, `VEHICLE_STOPPED`, `TELEMETRY_STALE`…); công cụ T13
ở [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 7. Tới khi có T13, lấy xấp xỉ `t_phát_hiện` ≈ dòng STOP đầu tiên của
`commands.csv`: nhịp điều khiển 20 ms, nên sự kiện nằm trong [t_STOP − 20 ms, t_STOP] (thử trên bo mô phỏng tối 24/09/2026,
script tạm: `MAP_CHANGED` 0,750 s, STOP đầu 0,760 s). Không dùng dòng `VEHICLE_STOPPED` của `events.csv`: đó là bo báo đã
rời RUNNING sau lệnh dừng của laptop (0,78 s trong cùng lần thử), muộn hơn `t_lệnh_dừng`. Ở nhánh SIM (xe ảo của bàn thử), `safety_events.json`
của gói `export_run` có mã và thời điểm phiên.

Hiệu giữa một mốc video và một mốc log chỉ tính được khi video và log đã đồng bộ (R7). R7 hiện CHƯA CÓ (tối 24/09/2026):
cách tạm bằng E-stop không dùng được với mã hiện tại ([KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 2.1). Tới khi
có T7 hoặc T14, phần thời gian đo giữa video và log của N-P1, N-P7, N-P8, N-P9 chưa chấm được. Chưa đồng bộ được thì chỉ
kiểm các ngưỡng đo hoàn toàn bằng video: N-P2, N-P3, và phần quãng của N-P5–N-P8.

| Mã | Đại lượng | Ngưỡng đề xuất (ở tốc độ ≤ N-V1) | Căn cứ | Mức | Đo bằng |
|---|---|---|---|---|---|
| N-P1 | `t_phát_hiện − t_vật` khi vật chắn hành lang | ≤ 0,4 s | LiDAR 10 Hz đo được: vòng trung vị 100,3 ms, khoảng trống lớn nhất 103,9 ms (u01, [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 3, ghi chú đồng hồ). Lớp `LiveLidar` chỉ coi ô là OCCUPIED khi bị chạm ở ≥ 2 trong 3 vòng ([GIAI_DOAN_3_CHUAN_BI.md](GIAI_DOAN_3_CHUAN_BI.md) mục 2, quy tắc 1). Từ lúc vật xuất hiện tới lúc vòng quét thứ hai chạm nó về máy: 0,1–0,3 s (TÍNH: chờ tia quét tới góc của vật ≤ 0,1 s, chờ vòng đó kết thúc ≤ 0,1 s, thêm một vòng 0,1 s). Cộng 0,1 s cho hợp nhất, cầu nối và nhịp điều khiển 20 ms: phần này CHƯA ĐO. Trên bàn chưa thử đưa tay vào khi xe ảo chạy (GIAI_DOAN_3_CHUAN_BI.md mục 3) | ĐO-MB (chu kỳ quét), TÍNH | R3 + R7 (R7 CHƯA CÓ: cần T7/T14), đối chiếu R6 (`commands.csv`, xấp xỉ ±20 ms tới khi có T13) |
| N-P2 | Quãng xe đi từ `t_vật` tới `t_đứng_yên` | ≤ 10 cm | 0,3 s × 0,10 m/s = 3 cm (TÍNH). Quãng hãm v²/2a: 0,83 cm với giảm tốc giả định 0,6 m/s², 1,67 cm với 0,3 m/s² (TÍNH). Mô phỏng rút cáp ở 0,10 m/s: xe trôi 4,1 cm, gồm 120 ms phát hiện (CHE_DO_QUAN_SAT.md mục 7). Trễ USB, trễ ESC, thả trôi/phanh của xe thật: CHƯA ĐO (bảng B5, B6 ở GIAI_DOAN_4_CHUAN_BI.md). 10 cm ≈ hai lần tổng tính được | TÍNH, MP | R3 (thước dọc đường trong khung; sai số ± một khung) |
| N-P3 | Khoảng còn lại từ thân xe tới vật sau khi dừng | ≥ 10 cm, khi vật được đưa vào cách đầu (hoặc đuôi) xe ≥ 30 cm theo hướng chạy và cách LiDAR ≥ 40 cm; kèm N-D4 | Kế hoạch mục 13 bước 8: đưa vật nhẹ từ khoảng cách an toàn, không ném vật sát xe. Vật thử phải cách LiDAR ≥ 40 cm (GIAI_DOAN_3_CHUAN_BI.md mục 3b, vì lề mặt nạ thân xe). 30 cm − 10 cm (N-P2) = 20 cm; lấy 10 cm để chừa sai số đặt vật (TÍNH) | KH, TÍNH | R2 (thước sau khi dừng) + R4 |
| N-P4 | Dừng giả | Tuyệt đối: 0 lần dừng do vật ngoài hành lang (VC-6) hay do nhiễu, trong mọi lần chạy nhóm DO | Bàn thử 22/09: LiDAR cố định trên bàn, xe ảo lập đường quanh 20 vật thật và đỗ xong, 202 vòng quét, 0 dừng giả sau năm quy tắc (GIAI_DOAN_3_CHUAN_BI.md mục 3). LiDAR gắn trên xe đang chạy: CHƯA THỬ | ĐO-MB (LiDAR đứng yên) | R6 + R3 |
| N-P5 | E-stop khi đang chạy | (a) telemetry báo FAULT và `ESTOP_INPUT` ≤ 60 ms sau lúc nhấn; (b) điện áp động lực ở ngõ vào ESC về ≈ 0 trong thời gian CẦN CHỐT theo phần tử ngắt đã chọn; (c) từ lúc nhấn tới đứng yên ≤ 5 cm và ≤ 1,0 s; (d) tuyệt đối: không chuyển động sau khi nhả nút cho tới CLEAR_FAULT + ARM + COMMAND mới | (a), (b), (d): tiêu chí đề xuất của L10, L12 ở [GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md) mục 5.3 ("≤ 50 ms + 10 ms"). (c): mô phỏng E-stop ở 0,10 m/s trôi 0,9 cm, đứng yên sau 0,18 s (CHE_DO_QUAN_SAT.md mục 7), nhưng mô phỏng giả định E-stop cắt động lực tức thì (`estop_cuts_power: true`, GIAI_DOAN_6_CHUAN_BI.md mục 3.1). Xe thật thả trôi thế nào: CHƯA ĐO (B5 dòng D1). Kế hoạch mục 10: "không coi cắt nguồn là đứng yên tức thì". Vì sao (a) không đo bằng video (tối 24/09/2026, Monte Carlo trong script tạm, không lưu trong repo; mô hình: pha khung video ngẫu nhiên, cờ hiện ở khung telemetry kế tiếp trong 50 ms, trễ bo cố định): nếu R7 đồng bộ bằng chính nút E-stop thì trễ thật của bo bị triệt tiêu trong phép trừ, và một bo trễ 183 ms (gấp ≈ 3 ngưỡng) vẫn "đạt ≤ 60 ms" ở 99,0 % số lần với 23,85 khung/s, 100 % với 240 khung/s. Đây là mô phỏng phép đo, không phải số đo | TK, MP, TÍNH | (a) mức M1 (L10 ở [GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md)): logic analyzer, kênh 1 trên dây tín hiệu E-stop (chân `kPinEstop`), kênh 2 trên chân ESC (`kPinEsc`, xung về trung tính = effort 0), kênh 3 trên một chân GPIO gỡ lỗi mà firmware lật khi xếp khung FAULT hoặc khung telemetry đầu tiên có `ESTOP_INPUT` = 1 (bản build thử; CHƯA CÓ trong firmware). Cách này đo phía bo; phần truyền USB tới laptop không nằm trong phép đo, ghi riêng (CHƯA ĐO). `FAULT.time_ms` và `sample_time_ms` (cột `device_time_ms` của `telemetry.csv`, R6) chỉ để đối chiếu, vì đó là đồng hồ của chính bo. R3 + R7 KHÔNG kiểm được (a): ± một khung (≈ 42 ms) cộng ± một khung đồng bộ, vượt 20 ms của quy tắc 3; R7 bằng chính nút E-stop là vòng tròn, vì lệch đồng bộ đã chứa sẵn trễ cần đo. (b) máy hiện sóng mức M2. (c), (d) R3 (nút trong khung) + R2 |
| N-P6 | Nút STOP phần mềm | Effort = 0 sau \|v_ref\| / stop_decel + 10 ms kể từ lúc bo nhận lệnh (≈ 0,18 s ở 0,10 m/s); từ lệnh tới đứng yên ≤ 5 cm; kết thúc STOPPED, không FAULT `STOP_NOT_CONFIRMED` | L15 ở GIAI_DOAN_6_CHUAN_BI.md mục 5.3. Dốc dừng 600 mm/s² của firmware (TK, CHƯA CHỐT) cho 0,83 cm nếu xe bám đúng mục tiêu (TÍNH). Hạn xác nhận dừng 2,0 s (`stop_confirm_timeout_s`, CHE_DO_QUAN_SAT.md mục 9) | TK, TÍNH | R3, R6 |
| N-P7 | Mất liên lạc laptop – bo (rút USB; chương trình laptop treo) | Laptop báo STOP ≤ 0,35 s sau khi rút (chỉ áp cho rút USB: khi laptop treo hay bị đóng thì không đòi mã STOP phía laptop trong lúc lỗi, xem CB-5); xung ESC về trung tính trong T = t_hạn + \|v\| / stop_decel + 30 ms (0,35 s ở 0,10 m/s với t_hạn = 0,15 s); từ lúc rút tới đứng yên ≤ 10 cm; tuyệt đối: cắm lại hay hết treo thì không chạy cho tới `arm()` + COMMAND mới | L3, L7 và công thức T ở GIAI_DOAN_6_CHUAN_BI.md mục 5.1 và 5.3 (≤ 0,3 s + 50 ms). Mô phỏng rút cáp ở 0,10 m/s: phát hiện sau 120 ms, trôi 4,1 cm (CHE_DO_QUAN_SAT.md mục 7). `TELEMETRY_STALE` 0,3 s (GIAO_THUC_XE.md mục 5) | TK, MP | R3 + R7 cho thời điểm rút so với log (R7 CHƯA CÓ: cần T7/T14; chưa có thì phần "≤ 0,35 s sau khi rút" chưa chấm được), R6; mức M1: máy hiện sóng trên chân ESC |
| N-P8 | Mất LiDAR (rút cáp) khi đang chạy | Yêu cầu dừng ≤ 0,4 s sau vòng quét cuối; từ lúc rút tới đứng yên ≤ 10 cm; tuyệt đối: cắm lại thì không chạy tiếp khi không có thao tác | L4 ở GIAI_DOAN_6_CHUAN_BI.md (≤ 0,3 s + 0,1 s). Lớp `LiveLidar` là lớp bắt buộc, tuổi tối đa 0,3 s (GIAI_DOAN_3_CHUAN_BI.md mục 1). Mới kiểm với cổng serial giả (`tests/test_lidar_unplug.py`); rút cáp C1 thật: CHƯA THỬ | TK | R6 (vòng cuối trong bản ghi LiDAR) + R3 + R7 cho thời điểm rút và quãng dừng (R7 CHƯA CÓ: cần T7/T14) |
| N-P9 | Mất một camera | Camera bị báo thiếu ≤ 0,54 s (0,5 s + một chu kỳ khung); tuyệt đối: 0 camera khỏe bị bỏ nhầm; xe có phải dừng hay không: CHƯA CHỐT (lớp camera đang là lớp tùy chọn) | L5 ở GIAI_DOAN_6_CHUAN_BI.md; `STALE_AFTER_S` = 0,5 s ([video/multicam.py](../autopark/video/multicam.py)). Máy bàn: 0 / 715 bộ (o01) và 0 / 2.862 bộ (o02) bỏ camera khỏe ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 10.3) | TK, ĐO-MB | R6 (`.rig.json`, log) + R3 + R7 cho lúc rút so với lúc báo thiếu (R7 CHƯA CÓ: cần T14 ở bàn thử) |
| N-P10 | Không tự chạy lại | Tuyệt đối: 0 lần xe chuyển động mà không có thao tác cho phép mới, sau khi: vật được dời đi, telemetry có lại, kết nối lại, nhả E-stop, bo khởi động lại, chương trình laptop khởi động lại | Kế hoạch mục 10 bước 6, mục 13. `tests/test_session_vehicle.py`: 60/60 đạt, chỉ trên bo mô phỏng và cổng serial giả (CHE_DO_QUAN_SAT.md mục 7) | KH, MP | R3 + R6 (không có COMMAND enable=1 nào trước lần `arm()` mới) |
| N-P11 | Đích không hợp lệ, không có đường, xe lệch điểm xuất phát | Tuyệt đối: bo không bị ARM lần nào, không COMMAND chuyển động nào; giao diện báo lý do | Đích lấn vật cản bị từ chối (`GOAL_INVALID`, BAO_CAO_GIAI_DOAN_0.md mục 3). START bị từ chối khi tư thế lệch điểm xuất phát > 3 cm hoặc > 5°, khi xe còn lăn, khi bo FAULT (`LinkParams`, CHE_DO_QUAN_SAT.md mục 3, 9). Không có đường thì giữ dừng (kế hoạch mục 13: "Không có đường phù hợp thì giữ dừng, không ép planner phải trả một đường bất kỳ"). Trong mã, mọi kết quả lập đường khác OK (NO_PATH, TIMEOUT, CANCELLED, ERROR) đều làm `trajectory = None` và đưa phiên về EDITING (`Session._apply_plan`); `Session.start_run` từ chối "Chưa có đường để chạy" trước `link.begin_run`, nên bo không bị ARM ([application/session.py](../autopark/application/session.py)). Kiểm ngoài repo (tối 24/09/2026, máy bàn, `.venv`, script tạm, bo mô phỏng) bằng planner giả trả lần lượt bốn trạng thái: cả bốn bị từ chối START, `link.runs` = 0, bo không ARMED. Pytest hiện có mới kiểm nhánh chưa có đường sau khi sửa sa bàn hoặc reset (`tests/test_session_run.py`, `tests/test_phase0.py`); chưa có ca riêng cho NO_PATH/TIMEOUT. Lưu ý: TIMEOUT không chứng minh vô nghiệm hình học ([KIEM_THU_DO_BEN_GIAI_DOAN_0.md](KIEM_THU_DO_BEN_GIAI_DOAN_0.md) mục 4); ở đây chỉ cần là không chạy | KH, TK, MP | R6 (`start_refusals.csv`; `telemetry.csv` toàn DISARMED) + quan sát |

## 4. Dữ liệu còn mới và độ trễ (dòng "Camera" và "Phản ứng lỗi"; kế hoạch mục 12)

**Nguyên tắc tuyệt đối** (TK, đã có test tổng hợp và mô phỏng, chưa kiểm trên xe): lớp bắt buộc bị cũ thì bản đồ hợp nhất
không hợp lệ và mọi ô bị chặn (GIAI_DOAN_3_CHUAN_BI.md mục 1); không có dữ liệu thì không bao giờ là FREE
([BEV.md](BEV.md) mục 2; GIAI_DOAN_3_CHUAN_BI.md mục 2 quy tắc 1). Kế hoạch mục 12: "Dữ liệu cần thiết bị cũ/mất thì không
cho tiếp tục mù".

| Mã | Nguồn dữ liệu | Giới hạn đề xuất | Giá trị trong mã (TK) | Số đo làm căn cứ | Ghi chú |
|---|---|---|---|---|---|
| N-T1 | Telemetry xe trong phiên đỗ | 0,15 s | `LinkParams.max_state_age_s` = 0,15 s, bằng 3 chu kỳ telemetry 50 ms (CHE_DO_QUAN_SAT.md mục 9) | Chu kỳ telemetry thật: CHƯA ĐO (chưa có bo) | |
| N-T2 | Tư thế xe | CHƯA CHỐT, hai phương án: 0,15 s nếu nguồn tư thế nội suy giữa hai vòng quét (encoder, IMU); 0,25 s nếu tư thế chỉ lấy từ định vị LiDAR 10 Hz | Dùng chung `max_state_age_s` = 0,15 s | LiDAR 100,3 ms/vòng (u01); định vị một vòng trên cảnh khớp: trung vị 10,6–11,1 ms, đo trước bản sửa kiểm xuyên tường; sau bản sửa ≈ 13,3 ms trung vị (live_headless, đo khi có tác vụ khác chạy song song) ([DINH_VI_LIDAR.md](DINH_VI_LIDAR.md) mục 5, bảng thứ hai) | TÍNH: nếu tư thế chỉ đổi mỗi vòng quét thì tuổi lúc nhịp điều khiển dao động 0–0,1 s cộng thời gian định vị. Một vòng không OK là tuổi vượt 0,2 s, phiên dừng `STALE_POSE`. Nếu đóng dấu tư thế theo giữa vòng quét (sớm hơn lúc vòng về máy ≈ 50 ms) thì tuổi có thể vượt 0,15 s ngay cả khi không mất vòng nào. Ở 0,10 m/s, tư thế 0,25 s tuổi ứng ≈ 2,5 cm. Nguồn tư thế thật: CHƯA CÓ (CHE_DO_QUAN_SAT.md mục 2, 8) |
| N-T3 | LiDAR (lớp bắt buộc) | 0,3 s | `LiveLidarLayer` `max_age_s` = 0,3 s ([fusion/layers.py](../autopark/fusion/layers.py)); `fusion.demo --max-age` mặc định 0,3 | 26 phiên 22–24/09: 33.932 vòng, 0 vòng bị bỏ; ba phiên 10 phút: 6.006 / 6.005 / 6.006 vòng, 0 vòng mất (GIAI_DOAN_1_LIDAR.md mục 3, 7) | 0,3 s = 3 vòng: mất một vòng không làm dừng, mất hai vòng liên tiếp thì có thể |
| N-T4 | Lớp camera/AI (lớp tùy chọn) | 0,5 s | `CameraSemanticLayer` `max_age_s` = 0,5 s | Tuổi kết quả AI so với khung cũ nhất, trung vị / p95: 34,8 / 74,9 ms (u01), 65,5 / 84,9 ms (u04) (GIAI_DOAN_2_BAN_THU.md mục 3.3); 36,6–42,3 / 39,9–45,1 ms ở ba phiên bật quy tắc chờ w01, w03, w05 (mục 10) | Nếu nối BEV thì cộng thời gian `build_bev` (4 camera 640×480, lưới 6 × 6 m ô 5 cm, supersample 2): ≈ 11,8–12,0 ms trung vị sau khi tăng tốc (tối 24/09/2026, máy bàn, rig tổng hợp, đo khi các tác tử khác đang chạy song song; [BEV.md](BEV.md) mục 6b). Bản trước khi tăng tốc: 69,5 ms (mục 6). → tuổi trung vị ≈ 0,05–0,08 s, p95 ≈ 0,05–0,1 s (TÍNH, cộng trung vị BEV vào số đo tuổi ở cột trước; laptop CHƯA ĐO), vẫn dưới 0,5 s |
| N-T5 | Tuổi kết quả AI, p95 | ≤ 0,15 s trên máy nghiệm thu, tính cả BEV nếu đã nối | — | Xem N-T4 (máy bàn) | Đề xuất; laptop CHƯA ĐO |
| N-T6 | Thời gian một lô AI bốn ảnh | p95 ≤ 42 ms (một chu kỳ khung ở 23,85 khung/s); mọi cỡ lô phải làm nóng xong trước START | — | o02: trung vị 12,1 ms, p95 14,5 ms, lớn nhất 20,8 ms (GIAI_DOAN_2_BAN_THU.md mục 10.3); u01: p95 36,7 ms, lớn nhất 64,7 ms (mục 3.3). Lô đầu của mỗi cỡ lô 1,2–1,7 s (mục 10.3) | Laptop CHƯA ĐO |
| N-T7 | Định vị một vòng quét | p95 ≤ 50 ms (nửa vòng quét) | — | Trước bản sửa kiểm xuyên tường (máy bàn, không tải nặng khác): cảnh khớp trung vị 10,6–11,1 ms, p95 12,4–13,1 ms; cảnh không khớp (k01) 84,6 / 103,7 ms. Sau bản sửa (máy bàn, đo khi có tác vụ khác chạy song song, chỉ có trung vị): live_headless ≈ 13,3 ms, k01 ≈ 93,7 ms; p95 sau bản sửa CHƯA ĐO (DINH_VI_LIDAR.md mục 5, bảng thứ hai) | Cảnh không khớp cho FAILED nên tư thế đằng nào cũng không được dùng. Laptop CHƯA ĐO |
| N-T8 | Lệch thời gian giữa vòng LiDAR và bộ ảnh | Phải được bù khi xe chạy; chưa đặt ngưỡng (mã bù: CHƯA CÓ) | — | Giữa vòng quét sớm hơn mốc bộ ảnh ≈ 80 ms, trung vị (u01; GIAI_DOAN_2_BAN_THU.md mục 3.2, 4) | Ở 0,10 m/s là ≈ 0,8 cm (TÍNH) |
| N-T9 | ToF (lớp tùy chọn) | 0,3 s | `NearFieldLayer` `max_age_s` = 0,3 s | Chưa có ToF | |
| N-T10 | Lệnh chuyển động | Thời hạn mỗi COMMAND 0,15 s (bo kẹp ≤ 0,3 s); watchdog liên lạc của bo 0,5 s; `TELEMETRY_STALE` của laptop 0,3 s | GIAO_THUC_XE.md mục 5 | Chưa có bo | Kiểm qua N-P7 |

## 5. Định vị (dòng "Định vị")

| Mã | Đại lượng | Ngưỡng đề xuất | Căn cứ | Mức | Đo bằng |
|---|---|---|---|---|---|
| N-L0 | Khoảng cách LiDAR so với thước (điều kiện trước của định vị) | Sai số ≤ 30 mm; hướng lệch ≤ 5°; 8–12 Hz; tia/vòng trong ±5 % của 5 kHz ÷ tần số; không trống quá 3 chu kỳ | Ngưỡng "đạt" đã đề xuất cho bảy lần đặt hộp p01–p06, p08 ở [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 6 (chưa làm) | TK | `lidar.bench record --expected-distance --expected-angle` rồi `lidar.bench report` |
| N-L1 | Sai số vị trí định vị so với tham chiếu, cảm biến đứng yên | Trung vị ≤ 2 cm, lớn nhất ≤ 3 cm trên mọi điểm tham chiếu | START từ chối khi tư thế lệch điểm xuất phát > 3 cm (`LinkParams`), nên định vị phải tốt hơn 3 cm thì kiểm này mới có nghĩa. Dung sai đích 5 cm (N-D1): định vị không nên chiếm quá một nửa. Dữ liệu tổng hợp: sai số 0,4–0,7 cm, trong đó 0,5–0,6 cm có hệ thống do bản đồ ô 5 cm (DINH_VI_LIDAR.md mục 4, 6). Bản ghi thật: chỉ có độ **nhất quán**, độ lệch chuẩn 2,6 / 2,7 mm (live_headless), không phải sai số | TK, TH, ĐO-MB (nhất quán) | DV-1: R1 hoặc R2 (DINH_VI_LIDAR.md mục 7 bước 2) |
| N-L2 | Sai số hướng định vị | Trung vị ≤ 1°, lớn nhất ≤ 2° | Ngưỡng `degenerate` của công cụ là 2° (DINH_VI_LIDAR.md mục 2). Tổng hợp: 0,004–0,10°. Nhất quán: 0,068°, nhưng hai bản ghi dự kiến cùng chỗ lệch +4,33°, chưa rõ nguyên nhân (DINH_VI_LIDAR.md mục 5) | TK, TH, ĐO-MB | DV-1 với tham chiếu hướng ≤ 0,67° (thước thẳng ≥ 0,65 m trên xe giả: 0,37–0,62° khi mỗi đầu ± 3–5 mm, TÍNH); R2 vạch 0,25 m (1,0–1,6°) hay thước đo góc thì không kiểm được. Trung vị 1° cần tham chiếu ≤ 0,33° (thước 1 m, mỗi đầu ± 3 mm: 0,24°); không đạt thì trung vị chỉ báo số (quy tắc 3) |
| N-L3 | "OK sai" | Tuyệt đối: 0 vòng quét được báo OK mà sai số > 2 × N-L1 lớn nhất (6 cm) hoặc > 2 × N-L2 lớn nhất (4°) | k01 tìm trên cả bản đồ: 31 vòng cho **cùng một** đỉnh sai (DINH_VI_LIDAR.md mục 5). Tư thế ổn định qua các vòng không phải bằng chứng tư thế đúng; chỉ các phép kiểm trên từng vòng mới là căn cứ | ĐO-MB | DV-1, DV-3 |
| N-L4 | Hướng gốc sau khi khởi động lại mô-tơ | \|Δθ\| ≤ 0,2° giữa hai phiên liên tiếp không chạm thiết bị. Vượt thì phải có bước hiệu chuẩn hướng mỗi lần bật, và kiểm lại N-L2 sau bước đó | DINH_VI_LIDAR.md mục 7 bước 1 ("vượt độ lặp lại ~0,1°"); 0,2° = hai lần độ lặp lại (đề xuất) | ĐO-MB (độ lặp lại) | DV-2 |
| N-L5 | Định vị khi xe chạy ở ≤ N-V1 | ≥ 95 % vòng quét OK dọc quỹ đạo; không quá 1 vòng liên tiếp không OK (xem N-T2); sai số so với R1 theo N-L1, N-L2 cộng thêm 1 cm và 1° | Chưa có số đo làm căn cứ: chưa thử khi cảm biến di chuyển (DINH_VI_LIDAR.md mục 6) | — | DV-3: R1 cả quỹ đạo; tham chiếu R1 phải có sai số hướng ≤ 1° ở TC-1 (hai marker cách 0,25 m cho 0,65–1,62°, TÍNH), không thì phần hướng ghi không kiểm được |

## 6. Camera (dòng "Camera")

| Mã | Đại lượng | Ngưỡng đề xuất | Căn cứ | Mức | Đo bằng |
|---|---|---|---|---|---|
| N-C1 | Khung tốt/s mỗi camera, ở mode đã chốt, chạy cùng LiDAR + AI | ≥ 20 khung/s trong mọi cửa sổ 10 s của phiên 30 phút | 640×480 + LiDAR + AI: 23,8–23,9 khung/s (u01 120 s, u04 600 s), 23,85 (o02 120 s). Trong đợt khung hỏng, cổng 1 còn 17,6 khung tốt/s (u03) (GIAI_DOAN_2_BAN_THU.md mục 3.1): ngưỡng này bắt được đợt như vậy. Phiên 30 phút: kế hoạch mục 16.1 | ĐO-MB, KH | LD-1 (`rig.bench`, `.rig.json`) |
| N-C2 | Khoảng dài nhất không có khung tốt, mỗi camera | ≤ 0,5 s, trừ lúc cố ý gây lỗi | `STALE_AFTER_S` = 0,5 s. Các phiên đã đo chưa báo riêng đại lượng này *(cập nhật 25/09/2026: câu này sai ngay từ lúc viết. `.rig.json` có `cameras[i].gap_max_ms` từ commit `7f93278` (24/09, `video/multicam.py`): khoảng dài nhất giữa hai khung tốt liên tiếp, khung cắt/xé/trùng không tính là khung tốt, đặt lại sau phần làm nóng. Đọc lại tệp trên máy bàn 25/09/2026 (thư mục `runs/` không commit), 640×480, bốn camera: u01 54–66 ms, u04 (600 s) 54–96 ms, o02 50–64 ms, m01 tối 24/09 52 ms; u03 cổng 1 có 357 khung cắt và 20 khung xé: 102 ms (các phiên u chạy 23/09 trên mã chưa commit lúc đó). Mọi số này là ĐO-MB và dưới 0,5 s nhiều lần)* | TK | LD-1; cần thêm trường vào `.rig.json` hoặc tính từ bản ghi (CHƯA CÓ) *(cập nhật 25/09/2026: trường đã có, đọc `cameras[i].gap_max_ms` của `.rig.json`; chưa tính khoảng hở chưa đóng ở cuối phiên, tức camera ngừng hẳn trước khi phiên kết thúc)* |
| N-C3 | Độ lệch thời gian trong bộ ảnh | p95 ≤ 42 ms (một chu kỳ khung); bộ lệch > 60 ms bị bỏ (`--max-skew-ms` mặc định) | p95: 24,1 ms (u01), 34,2 ms (u04), 23,3 ms (o02), 36,4 ms (o01, 720p, hai nhịp khác nhau); 56,4 ms ở u03 khi cổng 1 có đợt khung hỏng (GIAI_DOAN_2_BAN_THU.md mục 3.2, 10.3). Cùng tài liệu: khi không camera nào mất khung thì độ lệch gần như luôn dưới một chu kỳ khung | ĐO-MB | LD-1 |
| N-C4 | Trễ từ sự kiện thật tới lúc khung tới máy | p95 ≤ 0,2 s | Chưa có số đo làm căn cứ: cần LED nháy (GIAI_DOAN_2_BAN_THU.md mục 4). 0,2 s đặt để nhánh camera cộng tuổi AI (N-T5) không chậm hơn nhánh LiDAR xấu nhất 0,3 s quá nhiều (TÍNH) | — | LED nháy trong khung của cả bốn camera |
| N-C5 | Nhận đúng camera theo hướng sau khởi động lại hay rút/cắm | Tuyệt đối: 4/4 đúng ở mỗi lần, ít nhất 3 lần | InstanceId theo cổng giữ nguyên sau khởi động lại ngày 23/09 ([usb_topology.md](usb_topology.md)); kế hoạch mục 6: "Đọc đúng camera theo đúng hướng sau khi khởi động lại" | ĐO-MB | Ảnh chụp từng camera sau mỗi lần khởi động |

## 7. Hình học và BEV (dòng "Hình học")

| Mã | Đại lượng | Ngưỡng đề xuất | Căn cứ | Mức | Đo bằng |
|---|---|---|---|---|---|
| N-G1 | Sai số vị trí điểm chân vật trên BEV so với thước | ≤ 5 cm trong vùng ≤ 1 m quanh thân xe; xa hơn 1 m chỉ báo số, chưa đặt ngưỡng | Chưa có số đo làm căn cứ: BEV chưa chạy trên camera dự án ([BEV.md](BEV.md) mục 8). 5 cm bằng một ô costmap. Độ phân giải mặt sàn **tính** trên rig giả định ≈ 9,5 cm/pixel ở 2 m với camera trước (TONG_HOP_DU_AN.md mục 4.12), nên xa hơn 1 m khó đạt | — | NT-2 với R2 |
| N-G2 | Chênh lệch vị trí cùng một vật giữa hai camera ở vùng chồng lấn | ≤ 5 cm | Chưa có số đo làm căn cứ | — | NT-2 |
| N-G3 | Vùng chưa quan sát, bị che, dưới thân xe, hoặc của camera thiếu dữ liệu | Tuyệt đối: 0 ô FREE | Quy tắc BEV ([BEV.md](BEV.md) mục 2): 32 test và 23 đột biến bị bắt trên rig tổng hợp *(cập nhật 25/09/2026: nay `tests/test_bev.py` có 38 test, đếm bằng `--collect-only` ở HEAD `54cb3e2`; 32 test cũ giữ nguyên, thêm các lượt đột biến cho phần tăng tốc, [BEV.md](BEV.md) mục 7; vẫn chỉ rig tổng hợp)*. Kế hoạch mục 6: vùng chưa quan sát giữ UNKNOWN | TK, TH | NT-5 |

**Định nghĩa `UNKNOWN` đề xuất** (kế hoạch 16.2 yêu cầu định nghĩa): một ô là UNKNOWN khi (1) chưa cảm biến nào quan sát
được nó; (2) số đo của nó không hợp lệ hoặc đã cũ quá giới hạn ở mục 4; (3) nó bị che khuất sau một vật; (4) dự đoán AI
thiếu tin cậy (0,15 < p(BLOCKED) < 0,50, hai ngưỡng hiện có của [BEV.md](BEV.md) mục 2); (5) LiDAR mới chạm nó ở 1 trong 3
vòng gần nhất (GIAI_DOAN_3_CHUAN_BI.md mục 2 quy tắc 1). UNKNOWN chặn lập đường như vật cản. Đây không phải một lớp của mô
hình AI (kế hoạch 16.2: thêm tên lớp không bảo đảm nhận ra mọi vật lạ).

## 8. AI (dòng "AI")

**Điều kiện áp dụng:** mục này chỉ có nghĩa khi hướng giấy phép WoodScape cho phép nối AI vào costmap/planner
([GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md); TONG_HOP_DU_AN.md mục 5.1, việc người dùng quyết định). Nếu không nối AI, điều
kiện V1 thứ ba ("AI/CV cung cấp thông tin cục bộ cho planner, có đo sai số/nhầm lẫn", kế hoạch 16.4) không đạt được với mô
hình hiện tại; người dùng cần chọn hướng khác (huấn luyện lại không dùng WoodScape, v.v.). Mọi số dưới đây là trên **bộ dữ
liệu công khai**; chưa có ảnh sa bàn nào có nhãn (TONG_HOP_DU_AN.md mục 4.2, 4.7).

| Mã | Đại lượng | Ngưỡng đề xuất | Căn cứ | Mức | Đo bằng |
|---|---|---|---|---|---|
| N-A1 | Tỉ lệ pixel vật cản bị gọi FREE, ngưỡng 0,15, trong ROI, trên tập chấm sa bàn tô tay từ đầu (`--no-draft`, [GAN_NHAN_SA_BAN.md](GAN_NHAN_SA_BAN.md)) | ≤ 2 % | Ở ngưỡng 0,15: WoodScape test 0,69 %, ACDC (thời tiết xấu) 2,28 %, RoadObstacle21 (vật lạ nhỏ) 18,2 % ([HUAN_LUYEN.md](../../HUAN_LUYEN.md) mục 10). Trên sa bàn: CHƯA ĐO | DL | Tập chấm sa bàn |
| N-A2 | Theo từng vật thử đã khai báo trong vùng làm việc: vật có ≥ 50 % pixel BLOCKED | Ở ≥ 95 % số khung có vật trong vùng làm việc | RoadObstacle21 ở ngưỡng 0,15: 19 / 30 ảnh thấy ≥ ½ vật (HUAN_LUYEN.md mục 10), tức vật lạ nhỏ là điểm yếu. Vì vậy phải khai báo loại và cỡ vật thử (kế hoạch 16.3 cuối mục) | DL | NT-1 … NT-4 |
| N-A3 | Báo động giả (FREE → BLOCKED) trên sàn trống | ≤ 5 % pixel | Ở ngưỡng 0,15: WoodScape test 3,97 %, ACDC 7,70 % (HUAN_LUYEN.md mục 10). Ảnh camera thật đầu tiên (23/09, chưa có nhãn, ngưỡng 0,50): 11 / 31 / 39 / 60 % pixel BLOCKED ở cổng 1–4; ở cổng 2–4, nhìn bằng mắt, phần lớn vùng đó là thảm hoa văn, tức báo động giả (TONG_HOP_DU_AN.md mục 4.2). Vì vậy vật liệu mặt sàn sa bàn có thể quyết định nhiều (chưa kiểm) | DL, quan sát | Tập chấm sa bàn |
| N-A4 | Vùng không chắc (0,15 < p < 0,50) | Tuyệt đối: là UNKNOWN, không bao giờ FREE | [BEV.md](BEV.md) mục 2 | TK | Test + NT-5 |

## 9. Điều khiển (dòng "Điều khiển") — chưa đề xuất số

Kế hoạch 16.2 ghi nhóm này "Cần chốt trên xe thật", và điều kiện chuyển bước giai đoạn 5 đòi "số đo sai số bám tốc độ/góc
ở miền thử nghiệm". Chưa có xe, encoder hay AS5600, nên tệp này **không đề xuất số**; chỉ liệt kê đại lượng và thời điểm
chốt.

| Mã | Đại lượng | Ngưỡng | Chốt sau | Số của mô phỏng để tham khảo (không phải căn cứ) |
|---|---|---|---|---|
| N-K1 | Sai số bám tốc độ (trung bình, lớn nhất) | CHƯA ĐỀ XUẤT | Bảng B4, B7 ([GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md) mục 3) và giai đoạn 5 | Sai số trung bình < 1 mm/s ở 0,05–0,15 m/s ([GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 10, MP) |
| N-K2 | Vọt lố tốc độ khi đổi mục tiêu | CHƯA ĐỀ XUẤT; liên quan hệ số 1,2 của N-V1 | B7, giai đoạn 5 | 26–57 % khi feedforward lệch như giả định; 21–24 % khi feedforward khớp mô hình (GIAO_THUC_XE.md mục 10, MP) |
| N-K3 | Sai số góc lái đo so với lệnh | CHƯA ĐỀ XUẤT | B2, B8, `steering_calibration.yaml` (giai đoạn 5) | — |
| N-K4 | Trễ đáp ứng lệnh → chuyển động | CHƯA ĐỀ XUẤT | Giai đoạn 5 (`stats.cmd_echo_s`, LED) | Trễ cơ cấu chấp hành mô phỏng 30 ms là giả định (GIAO_THUC_XE.md mục 10) |
| N-K5 | Trình tự đổi chiều | Tuyệt đối: giảm tốc → xác nhận dừng → đổi chiều (trùng N-D6 ý c) | B5 và giai đoạn 5 | Firmware giữ 0 ít nhất 300 ms (CHƯA CHỐT) |

## 10. Số lần lặp và tỉ lệ thành công (N-D8)

Số dưới đây là **phép tính thống kê**, không phải số đo: cận dưới một phía 95 % của tỉ lệ thành công thật theo
Clopper–Pearson, khi quan sát k lần đạt trong n lần (tính bằng script tạm ngày 24/09/2026, không lưu trong repo).

| n lần | k đạt | Cận dưới 95 % |
|---:|---:|---:|
| 5 | 5 | 0,549 |
| 10 | 10 | 0,741 |
| 10 | 9 | 0,606 |
| 15 | 15 | 0,819 |
| 20 | 20 | 0,861 |
| 20 | 19 | 0,784 |
| 20 | 18 | 0,717 |
| 30 | 30 | 0,905 |
| 30 | 29 | 0,851 |
| 59 | 59 | 0,950 |

Muốn khẳng định tỉ lệ thành công ≥ 90 % (cận dưới 95 %) cần 29 lần đạt liên tiếp không lần hỏng; ≥ 95 % cần 59 lần. Với
thời gian của một đồ án, V1 **không chứng minh được độ tin cậy cao**; nó chỉ chứng minh hệ thống làm được lặp lại trong
điều kiện đã khai báo. Khóa luận phải viết đúng như vậy.

Đề xuất (CHỜ CHỐT):

- **Kịch bản đỗ (nhóm DO):** mỗi biến thể ≥ 10 lần (DO-2: 5 tư thế × 3 lần; DO-3, DO-4b, DO-5, DO-6: 5 lần mỗi biến thể,
  vì khó hơn và tốn thời gian hơn). Biến thể 10 lần đạt khi ≥ 9 / 10 thành công; biến thể 5 lần đạt khi 5 / 5. Tuyệt đối:
  0 lần chạm (N-D4). Báo thêm tỉ lệ gộp của cả nhóm kèm cận dưới ở bảng trên.
- **Kịch bản an toàn** (VC-1 … VC-5, nhóm CB, AT-1 … AT-3): ≥ 10 lần mỗi kịch bản; kịch bản có nhiều biến thể thì chia
  cho các biến thể, mỗi biến thể ≥ 3 lần. Đạt khi mọi lần đều đạt (10 / 10). Một lần không dừng, dừng quá ngưỡng hay tự
  chạy lại là không đạt: sửa rồi làm lại **cả loạt**. Với E-stop ở mức trên sàn (M3), số lần có thể ít hơn vì hao mòn cơ
  khí: CHƯA CHỐT.
- **Kịch bản từ chối** (nhóm DI): ≥ 3 lần mỗi biến thể; đạt khi 3 / 3.
- **Mọi lần chạy được đánh số trước và ghi hết**, kể cả thất bại và lần hủy (kế hoạch mục 14: "Không chỉ chọn các lần demo
  thành công"). Lần hủy vì lỗi dụng cụ đo (ví dụ video không ghi) được ghi KHÔNG TÍNH kèm lý do, và phải chạy bù.

## 11. Ánh xạ về kế hoạch

### 11.1. Bảng 16.2

| Nhóm trong 16.2 | Mã ở tệp này | Còn thiếu để chốt |
|---|---|---|
| Camera | N-C1 … N-C5, N-T4 … N-T6 | Số trên máy nghiệm thu; LED đo trễ; mode camera đã chốt (hiện 640×480) |
| Hình học | N-G1 … N-G3 | Hiệu chuẩn nội tham bốn camera, ngoại tham đo, ROI ([BEV.md](BEV.md) mục 8) |
| AI | N-A1 … N-A4 | Quyết định giấy phép WoodScape; tập chấm sa bàn có nhãn |
| Định vị | N-L0 … N-L5, N-T2, N-T7 | Bảy lần đặt hộp; tham chiếu độc lập (DV-1, DV-2); nguồn tư thế trong phiên |
| Điều khiển | N-K1 … N-K5, N-V1 | MN300, encoder, AS5600, ESP32-S3; bảng B2–B8 |
| Tự đỗ | N-D1 … N-D9, N-V1 | Tất cả ở trên, cộng tham chiếu trên cao đã kiểm (TC-1) |
| Phản ứng lỗi | N-P1 … N-P11, N-T1, N-T3, N-T9, N-T10 | Giai đoạn 6 (nguồn và dừng) phải đạt trước khi thử trên sàn; chính sách sau vật cản thông thường |

### 11.2. Điều kiện V1 (16.4)

| Điều kiện V1 | Ngưỡng liên quan | Kịch bản ([KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md)) |
|---|---|---|
| 1. Bản đồ/định vị LiDAR hoạt động trong khu vực thử | N-L0 … N-L5, N-T2, N-T3, N-T7 | DV-1, DV-2, DV-3 |
| 2. Bốn camera cùng hoạt động, hiệu chuẩn đúng gá | N-C1 … N-C5, N-G1, N-G2 | LD-1, NT-2 |
| 3. AI/CV cung cấp thông tin cục bộ cho planner, có đo sai số/nhầm lẫn | N-A1 … N-A4, N-G3, N-T4 … N-T6 | NT-1 … NT-5 |
| 4. Chọn vị trí/hướng, xem trước, ra lệnh bắt đầu | N-P11 | DO-1, DI-1 … DI-4 |
| 5. Quỹ đạo xét giới hạn lái và toàn thân xe | N-D4, N-D5, N-D6 | DO-1 … DO-6, VC-3 |
| 6. Thực thi có phản hồi tốc độ/góc | N-K1 … N-K5, N-V1 | DO-5, DO-6, AT-5 |
| 7. Hoàn thành các bài đỗ theo tiêu chí đã chốt | N-D1 … N-D9 | DO-1 … DO-6 |
| 8. Vật cản/dữ liệu không hợp lệ làm dừng hoặc từ chối đúng thiết kế | N-P1 … N-P4, N-P8 … N-P11, mục 4 | VC-1 … VC-6, CB-1 … CB-6, DI-1 … DI-4 |
| 9. Nguồn, watchdog, E-stop đã kiểm chứng | N-P5 … N-P7, N-P10 | AT-1 … AT-4, CB-5 |
| 10. Dữ liệu, cấu hình, hướng dẫn để tái hiện | (không phải ngưỡng số) | Gói dữ liệu GD1 … GD6 ở KICH_BAN_NGHIEM_THU.md mục 2.2 |

## 12. Việc cần làm để chốt

| Việc | Ai | Ghi chú |
|---|---|---|
| Duyệt từng mã N-…: giữ, sửa số, hay bỏ | Người dùng + GVHD | Ghi ngày chốt cạnh từng mã; sau đó điền bảng 16.2 của kế hoạch (tệp kế hoạch không thuộc phạm vi tệp này) |
| Chọn máy chạy khi nghiệm thu; đo lại N-T4 … N-T7, N-C1 … N-C3 trên máy đó | Người dùng | Quy tắc chung 4 |
| Chọn một trong hai phương án N-T2 (tuổi tư thế) | Người dùng, khi nối định vị LiDAR vào phiên | Ảnh hưởng tới việc có cần encoder/IMU nội suy |
| Mất camera có làm xe dừng không (N-P9) | Người dùng | Lớp camera và lớp ToF đang là lớp tùy chọn (GIAI_DOAN_6_CHUAN_BI.md mục 6) |
| Sau vật cản thông thường: xe tự tiếp tục hay chờ xác nhận | Người dùng | Kế hoạch 17.2; ảnh hưởng VC-5 |
| Hướng giấy phép WoodScape | Người dùng | Quyết định mục 8 có áp dụng không |
| Tỉ lệ độ chính xác 3:1 và số lần lặp ở mục 10 | Người dùng + GVHD | Tỉ lệ áp lên giá trị lớn nhất (quy tắc 3). Nếu không dựng được tham chiếu hướng ≤ 0,67° (thước thẳng ≥ 0,65 m) thì phương án khác là nới N-L2 thành trung vị ≤ 1,5°, lớn nhất ≤ 3° (tham chiếu ≤ 1°) và sửa theo N-L3 (6°), N-L5 (lớn nhất 4°); cách này kiểm độ lệch +4,33° (N-L4, N-D2) kém hơn nên không ưu tiên |
| Công cụ còn thiếu cho phép đo: ghi sự kiện dừng của phiên (T13), dấu đồng bộ video–log (T14), nút CLEAR_FAULT (T15), GPIO gỡ lỗi khi xếp khung FAULT trong firmware (N-P5(a)) | Người phát triển | [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 7; chưa có T13/T14 thì N-P1, N-P7 … N-P9 chưa chấm được phần thời gian video–log |
| Đo các số còn thiếu trước khi chốt: B1–B8 (GIAI_DOAN_4_CHUAN_BI.md), N-L0 (đặt hộp), DV-1, DV-2, TC-1 (kiểm tham chiếu trên cao), LED đo trễ camera | Người dùng (cần người thao tác) | DV-1, DV-2 và TC-1 làm được ngay với LiDAR và camera đang có |
