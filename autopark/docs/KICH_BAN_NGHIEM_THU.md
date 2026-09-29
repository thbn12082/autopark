# Kịch bản nghiệm thu V1 trên sa bàn mô hình — bản nháp (24/09/2026)

> **Ghi công theo giấy phép dữ liệu:** các kịch bản nhận thức (nhóm NT) dùng mô hình AI huấn luyện trên **Valeo WoodScape
> Dataset** (<https://github.com/valeoai/WoodScape>; địa chỉ cũ `woodscape.valeo.com` / `woodscape.valeo.ai`, kiểm
> 25/09/2026 dẫn tới một trang không có nội dung WoodScape). Giới hạn sử dụng, gồm câu điều khoản về vận hành phương tiện
> và quyết định 25/09/2026 dùng mô hình trong vòng điều khiển xe (Valeo chưa xác nhận cách đọc):
> [GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md).
> *(Sửa 25/09/2026: link đổi từ `https://woodscape.valeo.com` sang repo GitHub theo đề xuất ở GIAY_PHEP_DU_LIEU.md mục
> "Ghi công: link tới trang bộ dữ liệu", CHỜ CHỐT. Bản trước viết "điều khoản cấm dùng mô hình đó để vận hành hoặc hỗ trợ
> vận hành phương tiện", mạnh hơn văn bản: điều khoản chỉ cho dùng phi thương mại và có vế không cho dùng mô hình trong vận
> hành phương tiện; dự án đọc vế đó là ví dụ của việc dùng thương mại.)*

**Kế hoạch đối chiếu:** [v3.1](../../KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) mục 16.3 (bộ kịch bản nghiệm thu, năm nhóm), 16.4
(điều kiện V1), 16.1 (mốc thử khởi đầu), 1.2 (phạm vi V1), 13 (giai đoạn 9: tự đỗ thật, luồng phản ứng với vật cản), 14
(giai đoạn 10: "Chuẩn bị bảng kịch bản, cách đo độc lập và định nghĩa thành công/thất bại trước khi thu kết quả cuối"), 15,
17.1 (tổ chức hồ sơ lần chạy). Ngưỡng dùng trong tệp này (mã `N-…`):
[NGUONG_NGHIEM_THU_DE_XUAT.md](NGUONG_NGHIEM_THU_DE_XUAT.md).

**Trạng thái: bản nháp. Mọi kịch bản CHƯA THỬ ở mức nghiệm thu.** Chưa nhận MN300, ESP32-S3, phần nguồn và dừng; chưa gá cảm
biến lên xe; định vị LiDAR mới chạy offline, chưa có tham chiếu độc lập; AI chưa nối vào costmap/planner (chờ quyết định
giấy phép WoodScape); chưa có camera trên cao hay công cụ tham chiếu độc lập nào. Mọi ngưỡng ở tệp kia là ĐỀ XUẤT – CHỜ
CHỐT. Tệp này không thêm số đo mới; mọi độ chính xác "kỳ vọng" của phương pháp đo là **ước tính hoặc phép tính**, ghi rõ ở
từng chỗ, và phải được đo lại ở phép kiểm tham chiếu TC-1 (mục 3.7) trước khi dùng.
*(Cập nhật 25/09/2026, `9d68257`: câu "AI chưa nối vào costmap/planner (chờ quyết định giấy phép WoodScape)" đã lỗi
thời. Ngày 25/09/2026 người làm khóa luận quyết định dùng mô hình WoodScape trong vòng điều khiển; Valeo chưa xác nhận cách
đọc điều khoản ([GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md)). Phần mềm đưa AI camera vào phiên đỗ xe làm nguồn vật cản
thứ hai đã có: ngăn "AI camera" của `ui.lidar_app --camera-ai` ([AI_DIEU_KHIEN_XE.md](AI_DIEU_KHIEN_XE.md)), chỉ kiểm bằng
nguồn giả, rig tổng hợp và phát lại. Chưa camera nào được hiệu chuẩn, nên trên bàn thật AI chưa tạo vật cản nào; điều
kiện hiệu chuẩn và tập chấm sa bàn của ĐK-AI (mục 1.3) vẫn còn.)*

Mọi lệnh viết trên **một dòng**, chạy trong thư mục `autopark` của repo (thư mục có pyproject.toml), dán được vào
cmd.exe. Thay `<ngay>`, `<ten>`… bằng giá trị thật trước khi chạy, và dùng tên **không dấu** (`cv2.imread`/`imwrite` gọi
thẳng trên Windows không đọc/ghi được đường dẫn có dấu; mã dự án đọc/ghi ảnh qua `autopark/image_io.py` nên repo chạy được
trong thư mục có dấu, [CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 3). Lệnh mở LiDAR (`lidar.bench record`; `ui.lidar_app`, `fusion.demo` không có
`--recording`; lệnh có `--lidar`) hay mở camera là lệnh chạm thiết bị: chỉ người thao tác chạy. Cổng LiDAR lấy từ
`configs/thiet_bi.json`, thêm `--port COMx` để ghi đè; ở `rig.bench`, `ui.rig_app`, `--lidar` không kèm giá trị dùng
cổng trong tệp đó ([chuyển máy](CHUYEN_MAY_BAN.md)).

## 0. Tóm tắt

- 37 kịch bản trong 9 nhóm (bảng ở mục 4): đỗ cơ sở (DO), đích không hợp lệ (DI), vật cản mới (VC), nhận thức (NT), mất
  cảm biến/liên lạc (CB), dừng và an toàn (AT), định vị (DV), chạy dài (LD), kiểm tham chiếu (TC). Năm nhóm của kế hoạch
  16.3 đều có mặt: "Đỗ cơ sở" → DO; "Nhận thức" → NT; "Vật cản mới" → VC; "Liên lạc/cảm biến" → CB; "Điều khiển/an toàn"
  → AT và DO-6 (đổi chiều). DI, DV, LD, TC là thêm để phủ điều kiện V1 ở 16.4.
- Bảy phương pháp đo độc lập R1–R7 (mục 2.1), trong đó quan trọng nhất là **camera trên cao** (R1). Quy trình dựng và kiểm
  nó ở mục 3.
- Làm được ngay, khi chưa có xe (mục 6): TC-1 nếu có camera trên cao, DV-1, DV-2, LD-1 trên máy bàn và laptop, phần bàn thử
  của VC-1, VC-2, VC-3, VC-6, CB-1, CB-3 (VC-2, VC-3 cần kịch bản có đoạn lùi/đoạn cong), và các bản mô phỏng của DO, DI.
- Đồng bộ video với log (R7) hiện CHƯA CÓ cách dùng được (mục 2.1, sửa tối 24/09/2026): các ngưỡng thời gian đo giữa video và
  log chưa chấm được cho tới khi có T7 hoặc T14 (mục 7).
- Còn thiếu công cụ để chạy nghiệm thu trên xe thật (mục 7, theo mã đã commit ở HEAD 9bcc30c): giao diện chưa chọn được
  cổng serial tới bo; định vị LiDAR chưa là nguồn tư thế của phiên; chưa ghi cảm biến đồng thời với phiên đỗ; chưa có công
  cụ tham chiếu trên cao; sự kiện dừng của phiên chưa vào log `VehicleIO` (T13); chưa có dấu đồng bộ video–log (T14) và nút
  CLEAR_FAULT (T15) (thêm tối 24/09/2026, đọc mã cây làm việc). Vài công cụ đang được thêm song song tối 24/09/2026, chưa commit (mục 7).
  *(Cập nhật 25/09/2026: các việc song song đó đã commit và push, `origin/main` = `54cb3e2` (đợt khuya: `65b7127` …
  `54cb3e2`). Giao diện nay chọn được cổng serial tới bo (thẻ "Bo điều khiển", `6db5087`), nhưng START với bo thật luôn bị
  từ chối vì chưa có nguồn tư thế thật (T2). Các dòng còn lại của gạch này vẫn đúng ở HEAD `54cb3e2`; chi tiết mục 7.)*

## 1. Phạm vi và quy ước

### 1.1. Vùng làm việc phải công bố (kế hoạch 16.3, cuối mục)

Kế hoạch 16.3: "Không cam kết phát hiện được mọi vật bất ngờ trong mọi điều kiện. Phải công bố vùng làm việc, loại/kích
thước vật thử, ánh sáng, tốc độ, khoảng phát hiện và các giới hạn còn lại." Đề xuất (CHƯA CHỐT):

| Mục | Đề xuất | Ghi chú |
|---|---|---|
| Sa bàn | Mặt sàn phẳng, cùng một loại ở mọi lần; ≥ 3 × 2 m như các kịch bản mẫu trong `scenarios/` ("kích thước là ví dụ"); biên bằng thanh xốp | Kích thước cuối chọn sau khi đo MN300: xe lớn hơn giả định 0,31 × 0,14 m thì vài bài có thể vô nghiệm trên sa bàn 3 × 2 m ([GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md) mục 5.2) |
| Bố trí tham chiếu | Mọi vạch ô, vật cản, tư thế xuất phát đo bằng thước theo hệ sa bàn (mục 3.3) và ghi thành tệp JSON cùng dạng `scenarios/*.json` | Tệp này là **bố trí tham chiếu** để chấm; bản đồ hệ thống dùng khi chạy là bản đồ LiDAR, không phải tệp này |
| Vật cản | Vật mềm, nhẹ; không dùng người đứng trong đường xe (kế hoạch mục 13) | |
| Vật thử (V1–V6) | V1: hộp carton sáng màu ≈ 20 × 20 × 20 cm. V2: như V1, bọc giấy đen mờ. V3: vật thấp hơn mặt phẳng quét LiDAR (ví dụ thanh xốp cao 5 cm). V4: chai nhựa trong. V5: dây cáp nằm trên sàn. V6: ống mảnh đứng Ø ≈ 2 cm, cao ≈ 30 cm | Kích thước là đề xuất; chiều cao mặt phẳng quét LiDAR trên xe CHƯA CHỐT (gá, [GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md) mục 6) |
| Ánh sáng | L1: đèn phòng bật đủ. L2: tắt một nửa đèn hoặc kéo rèm. L3: một nguồn sáng xiên tạo bóng đổ đậm | Tài liệu dự án không ghi có máy đo lux: ghi ảnh sa bàn (R1) và thông số khung/s, phơi sáng của từng camera ở mỗi mức |
| Tốc độ | ≤ N-V1 (0,10 m/s ở đợt đầu, đề xuất) | Kế hoạch 16.1: khảo sát 0,05–0,15 m/s |
| Khoảng phát hiện | Vật được đưa vào cách đầu/đuôi xe ≥ 30 cm theo hướng chạy và cách LiDAR ≥ 40 cm (N-P3) | [GIAI_DOAN_3_CHUAN_BI.md](GIAI_DOAN_3_CHUAN_BI.md) mục 3b |
| Ngoài phạm vi V1 | Vạch sơn, tự tìm ô, tự lái tới bãi, vật chuyển động liên tục (kế hoạch 1.2, 16.1) | |

### 1.2. Ba mức thử

Kế hoạch 1.3: mô phỏng, bàn thử và xe thật là ba mức bằng chứng khác nhau; kết quả ở mức dưới không thay được mức trên.

| Mức | Nghĩa | Dùng trong tệp này |
|---|---|---|
| MP | Mô phỏng: xe ảo, bo mô phỏng (`SimVehicleIO` + `FirmwareModel`), thông số giả định | Tiền nghiệm thu: kiểm bố trí và phần mềm trước khi thử thật; **không** tính là nghiệm thu |
| BT | Bàn thử: cảm biến thật (LiDAR C1, bốn camera) trên bàn hoặc giá, xe ảo hoặc xe đứng yên | Tiền nghiệm thu cho phần cảm biến; nghiệm thu thật cho DV-1, DV-2, LD-1, TC-1 |
| XT | Xe thật trên sa bàn | Mức nghiệm thu của mọi kịch bản DO, DI, VC, NT (động), CB, AT (trừ AT-4, chỉ làm ở mức bàn), DV-3 |

Với các kịch bản có chấp hành, dùng thêm bốn mức an toàn M0–M3 của
[GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md) mục 5.1 (M0: chỉ bo; M1: có xung, chưa nối ESC; M2: nối ESC, bánh kê cao;
M3: trên sàn, tốc độ thấp, người giám sát cầm nút dừng). Kịch bản trên sàn chỉ làm ở M3 sau khi M0–M2 của đúng tình huống đã
đạt.

### 1.3. Điều kiện trước dùng chung

| Mã | Nội dung |
|---|---|
| ĐK-XT | Điều kiện của mọi lần chạy có động lực trên sàn: giai đoạn 4 (có `vehicle_measured`, bảng B1–B8 của [GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md)); giai đoạn 5 (điều khiển có phản hồi, có mã đọc encoder và AS5600: thiếu tốc độ hoặc góc lái đo thì START bị từ chối, [CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) mục 8); **giai đoạn 6 đạt** (kế hoạch mục 10: "phải đạt trước giai đoạn chạy tự động trên sàn"); giai đoạn 7 (cảm biến gá trên xe, ngoại tham đo, footprint đo lại); giai đoạn 8 (hợp nhất trên xe chuyển động, định vị trong phiên); AT-5 (quan sát) đạt; TC-1 đạt; ngưỡng liên quan đã chốt; các công cụ T1–T3 ở mục 7 đã có |
| ĐK-AI | Thêm cho kịch bản dựa vào camera/AI: quyết định giấy phép WoodScape cho phép nối AI ([GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md)); hiệu chuẩn nội tham bốn camera, ngoại tham đo, mặt nạ ROI ([BEV.md](BEV.md) mục 8); tập chấm sa bàn có nhãn tô tay ([GAN_NHAN_SA_BAN.md](GAN_NHAN_SA_BAN.md)). *(Cập nhật 25/09/2026: phần giấy phép đạt từ 25/09/2026 theo quyết định của người làm khóa luận (cách đọc A), Valeo chưa xác nhận; hai điều kiện còn lại vẫn thiếu. Phần mềm nối AI vào phiên đã có (ngăn "AI camera", [AI_DIEU_KHIEN_XE.md](AI_DIEU_KHIEN_XE.md), mã ở `b01dea4`) nhưng chỉ tạo vật cản khi đã có nội tham đạt tiêu chí, ngoại tham đo và ROI như điều kiện ở trên.)* |
| ĐK-BT | Cho phần bàn thử: thiết bị đang có (LiDAR C1: COM3 trên máy bàn từ 29/09/2026, ghi ở `configs/thiet_bi.json`; COM4 trên máy bàn tới 25/09/2026, [chuyển máy](CHUYEN_MAY_BAN.md); bốn camera qua hub), người thao tác |

### 1.4. Kết quả một lần chạy và phân loại nguyên nhân

| Kết quả | Khi nào |
|---|---|
| THÀNH CÔNG | Chỉ cho lần đỗ (DO, phần cuối của VC-5): đủ mọi điều kiện ở [NGUONG_NGHIEM_THU_DE_XUAT.md](NGUONG_NGHIEM_THU_DE_XUAT.md) mục 1 |
| DỪNG ĐÚNG | Hệ thống dừng hoặc từ chối đúng như kịch bản yêu cầu, trong ngưỡng. Với VC, CB, AT, DI thì đây là kết quả "đạt" của kịch bản. Trong kịch bản DO, một lần dừng đúng là không hoàn thành nhiệm vụ đỗ (kế hoạch 14 bước 4) |
| THẤT BẠI | Vượt ngưỡng; chạm vật; không dừng khi phải dừng; dừng giả; tự chạy lại; có can thiệp của người |
| KHÔNG TÍNH | Lỗi của dụng cụ đo, không liên quan hệ thống (ví dụ video không ghi). Ghi lý do và chạy bù. Không được dùng loại này để bỏ một lần thất bại |

Mỗi lần THẤT BẠI ghi một nguyên nhân chính theo kế hoạch 14 bước 6: ảnh/AI, định vị, hình học, planner, điều khiển, cơ khí,
nguồn, liên lạc, đích không hợp lệ; thêm "dụng cụ đo" cho lần KHÔNG TÍNH. Mọi lần chạy được **đánh số trước** và ghi hết
(kế hoạch 14: "Không chỉ chọn các lần demo thành công").

## 2. Phương pháp đo độc lập và dữ liệu ghi

### 2.1. Phương pháp đo (R1–R7)

"Độc lập" nghĩa là không dùng đầu ra của chính hệ thống (định vị, telemetry, costmap) để tự xác nhận nó (kế hoạch mục 12
điều kiện cuối, mục 14). Độ chính xác dưới đây là **ước tính hoặc phép tính, CHƯA ĐO**; số tính lấy từ một script tạm ngày
24/09/2026 (không lưu trong repo) và ghi ở mục 3.10.

| Mã | Phương pháp | Đo được gì | Độ chính xác kỳ vọng | Giới hạn |
|---|---|---|---|---|
| R1 | Camera trên cao nhìn xuống sa bàn, hai marker ArUco trên xe, phép chiếu mặt sàn khớp từ các mốc đo bằng thước (mục 3) | Tư thế xe theo thời gian (quỹ đạo), tư thế cuối, khoảng hở, tốc độ | Vị trí ≈ 1 cm, hướng ≈ 1–1,6° (ước tính mục 3.10); **phải đo ở TC-1** | Thị sai do marker cao hơn sàn phải được bù; hướng là phần yếu nhất; chưa có công cụ (mục 7, T4) |
| R2 | Băng dính và vạch trên sàn, thước thép, thước kẹp | Tư thế xuất phát và tư thế cuối (hai điểm đánh dấu trên trục dọc xe), khoảng còn lại tới vật, vị trí vật thử | Mỗi điểm ± 3–5 mm (ước tính: đọc thước ± 1 mm cộng đặt dấu); hướng từ hai điểm cách 0,25 m: 1,0° nếu mỗi điểm ± 3 mm, 1,6° nếu ± 5 mm; cách 0,65 m: 0,37–0,62°; cách 1 m: 0,24–0,41° (TÍNH, √2·σ/d, mục 3.6) | Chỉ đo lúc đứng yên; không có quỹ đạo. Hướng muốn tốt hơn 0,67° (để kiểm N-L2) thì hai điểm phải cách ≥ 0,65 m (thước thẳng cứng gắn trên xe hay xe giả, mục 3.2) |
| R3 | Video (bên hông hoặc trên cao) có thước trong khung | Thời điểm vật xuất hiện, đứng yên, quãng dừng, tốc độ, số lần đổi chiều, chạm | Thời gian ± một khung: ≈ 42 ms với camera của dự án (23,85 khung/s, nhịp không đều ≈ 31 / 48 ms, [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 10); 17–33 ms với camera 60 / 30 khung/s. Số khung/s thật phải đọc từ tệp, không dùng số danh định ([GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md) B6) | Quãng đo theo thước trong khung, sai số tùy độ phân giải và thị sai |
| R4 | Ảnh chụp lúc xe dừng, từ trên xuống, có vạch ô và thước trong ảnh | Thân xe trong ô, khoảng còn lại; lưu hồ sơ | Như R2 | Bằng chứng lưu hồ sơ, đo số thì dùng R2 |
| R5 | Cờ giấy đứng cách mặt vật một khoảng định trước (ví dụ 2 cm), và viền băng dính quanh chân vật | Khoảng hở ≥ ngưỡng (cờ không đổ); chạm (vật xê dịch khỏi viền) | Đặt cờ ± 3 mm (ước tính) | Chỉ trả lời có/không |
| R6 | Log hệ thống: `commands.csv`, `telemetry.csv`, `events.csv`, `start_refusals.csv`, `link.json` ([CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) mục 5), `.rig.json`, track định vị | Lý do dừng, thời điểm phần mềm, lệnh đã gửi, trạng thái bo (mã và thời điểm của sự kiện dừng do **phiên** phát, như `MAP_CHANGED` hay `STALE_POSE`, chưa được ghi khi chạy qua `VehicleIO`: T13 ở mục 7; hiện chỉ có `result.reason` dạng văn bản trong `link.json` và dòng STOP đầu tiên trong `commands.csv`. Nhánh SIM, gồm xe ảo của bàn thử, thì "Xuất log CSV…" còn ghi gói `export_run` có `safety_events.json` với mã và thời điểm phiên) | Theo đồng hồ `perf_counter` của laptop | **Không độc lập**: chỉ đối chiếu, không dùng làm số nghiệm thu cho vị trí, hướng, khoảng hở, quãng dừng |
| R7 | Đồng bộ video với log: sự kiện nhìn thấy trong video và có dấu trong log, ở đầu và cuối lần chạy | Lệch và trôi giữa đồng hồ video và đồng hồ laptop | ± một khung video (ước tính) | Cách tốt nhất là LED do ESP32 bật khi nhận COMMAND/STOP: CHƯA LÀM ([GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md) B6; T7, chỉ có trên xe thật). Tạm dùng E-stop: KHÔNG dùng được với mã hiện tại (đọc mã và thử trên bo mô phỏng 24/09/2026). E-stop chốt FAULT; `VehicleLink` từ chối START khi FAULT; giao diện chưa có CLEAR_FAULT (T15). Telemetry chỉ được ghi khi lần chạy đang mở (`begin_run` xóa `telemetry_rows`, `refresh()`/`pump()` chỉ chạy trong lần chạy), nên nhấn sau khi xe đứng yên không vào `telemetry.csv`, và nhấn trước START thì dòng của nó bị xóa (chỉ vài khung cuối còn trong hàng đợi lúc START lọt vào với `t_session` âm: thử trên bo mô phỏng tối 24/09/2026, nhấn E-stop 0,5 s, nhả, CLEAR_FAULT rồi START thấy 3 khung như vậy, không khung nào có `estop_input` = 1; không dùng làm phương pháp). Ngoài ra, E-stop làm dấu đồng bộ thì không dùng được cho N-P5(a) (vòng tròn: lệch đồng bộ đã chứa sẵn trễ cần đo) và làm lệch mọi hiệu video–log khác thêm đúng trễ E-stop (≤ 60 ms nếu L10 đạt). Cách tạm khả thi, CHƯA CÓ công cụ: dấu đồng bộ trên màn hình laptop, vừa quay được trong video R3 vừa có dòng ghi `perf_counter` (T14). Chưa có T7 hoặc T14 thì R7: CHƯA CÓ |

Hệ quả của dòng R7 (tối 24/09/2026): mọi ô "R3 + R7" dưới đây chỉ đo được phần **hoàn toàn trong video** (quãng, đứng yên,
chạm, thứ tự sự kiện) cho tới khi có T7 hoặc T14. Hiệu giữa một mốc video và một mốc log (ví dụ `t_phát_hiện − t_vật`)
ghi "CHƯA ĐO ĐƯỢC (thiếu R7)", không ghi đạt. Sự kiện dùng làm dấu đồng bộ không được là chính sự kiện của ngưỡng đang
kiểm.

### 2.2. Gói dữ liệu mỗi lần chạy (GD1–GD6)

Kế hoạch 17.1: "Log phải ghi phiên bản code/model/map/calibration và phép thử; tránh đo hai cấu hình khác nhau rồi so sánh
như cùng điều kiện."

| Mã | Nội dung | Công cụ hiện có |
|---|---|---|
| GD1 | Manifest: mã commit, SHA-256 checkpoint AI, bản đồ LiDAR, tệp hiệu chuẩn và ngoại tham, `vehicle_measured`, phiên bản firmware, máy chạy, điện áp pin trước/sau, giờ, mức ánh sáng, người đo, người giám sát | Chưa có công cụ; ghi tay theo mẫu. Kế hoạch 14 bước 1: đóng phiên bản trước bộ thử cuối |
| GD2 | Log phiên qua `VehicleIO` (`VehicleLink.write_logs`: năm tệp ở R6) | Có, nút "Xuất log CSV…" của giao diện; mới dùng với bo mô phỏng |
| GD3 | Bản ghi cảm biến (bốn camera + LiDAR) cùng định dạng `rig.bench --record` ([GHI_PHAT_LAI_BAN_THU.md](GHI_PHAT_LAI_BAN_THU.md)) | Có cho bàn thử; ghi **trong** phiên đỗ xe: CHƯA CÓ (mục 7, T3). 4,98 MB/s ở cảnh tối (phiên o03); cảnh sa bàn CHƯA ĐO |
| GD4 | Track định vị (`track.csv`, `localize.json` của `lidar.localize`) | Có, chạy offline trên bản ghi LiDAR |
| GD5 | Tham chiếu độc lập: video R1/R3, ảnh R4, biên bản thước R2, tệp tư thế tham chiếu | Trích tư thế từ video R1: CHƯA CÓ (T4) |
| GD6 | Một dòng biên bản (mục 2.3) | Mẫu đề xuất; chưa có công cụ tự điền (T5) |

### 2.3. Biên bản lần chạy (mẫu đề xuất)

Mỗi lần chạy một dòng CSV, cột: `ma_kich_ban`, `bien_the`, `lan`, `ngay_gio`, `muc_thu` (MP/BT/XT, M0–M3), `ket_qua`
(THANH_CONG / DUNG_DUNG / THAT_BAI / KHONG_TINH), `nguyen_nhan`, `sai_so_vi_tri_cm`, `sai_so_huong_deg`, `trong_o`, `cham`,
`khoang_ho_min_cm`, `doi_chieu_lap`, `doi_chieu_thuc`, `thoi_gian_s`, `v_max_do_mps`, `t_phat_hien_s`, `quang_dung_cm`,
`khoang_con_lai_cm`, `can_thiep`, `phuong_phap_do` (R1…R7), `thu_muc_du_lieu`, `ghi_chu`. Ô không áp dụng để trống, không
ghi 0.

Nơi lưu (CHƯA CHỐT): dữ liệu gốc ở `runs\nghiem_thu\<ngay>\<ma>_l<lan>\` (thư mục `runs/` bị git-ignore); biên bản tổng hợp ở
`docs\evidence\bien_ban_nghiem_thu_<ngay>.csv`, đặt **thẳng** trong `docs\evidence\`. Lý do: `autopark/.gitignore` bỏ qua mọi
`*.csv` và chỉ có ngoại lệ `!docs/evidence/*.csv`; ngoại lệ này không áp dụng cho thư mục con. Kiểm ngày 24/09/2026 bằng
`git check-ignore -v --no-index`: `docs/evidence/nghiem_thu/bien_ban_20260925.csv` bị bỏ qua (dòng 9 `*.csv`), còn
`docs/evidence/bien_ban_nghiem_thu_20260925.csv` được giữ lại (dòng 13). Tệp JSON/PNG tham chiếu (mục 3.7 bước 4) vẫn để
được trong `docs\evidence\nghiem_thu\` vì git không bỏ qua các tệp này (cùng lần kiểm).

Kết quả mô phỏng của `autopark.evaluation.bench` (DO-3 … DO-6, DI-2) ghi vào `runs\nghiem_thu\mo_phong\`. Lệnh `bench` **không
tự tạo thư mục cha** và chỉ ghi tệp JSON sau khi chạy hết các ca, nên thiếu thư mục thì chạy xong mới báo
`FileNotFoundError`, thoát mã 1 và mất kết quả (thử ngày 24/09/2026 với một thư mục không tồn tại). Tạo thư mục một lần, chạy
từ thư mục `autopark` của repo, tức thư mục có pyproject.toml (lệnh không làm gì nếu thư mục đã có; đã thử trong cmd.exe 24/09/2026):
`if not exist runs\nghiem_thu\mo_phong mkdir runs\nghiem_thu\mo_phong`

*(Cập nhật 25/09/2026: đoạn trên là hành vi trước commit `10a4735`. Từ commit đó, `bench --json` tạo thư mục cha **trước**
khi chạy ca; không tạo được thì thoát mã 2 ngay, chưa chạy ca nào (`tests/test_evaluation_bench_cli.py`, 2 test). Lệnh
`mkdir` ở trên không còn bắt buộc, chạy thêm cũng không sao.)*

### 2.4. Trình tự một lần chạy trên xe thật

Theo kế hoạch 13 bước 1–4:

1. **Trước:** ghi GD1; đo điện áp pin; nhấn thử và nhả thử E-stop ở đầu buổi, rồi CLEAR_FAULT trước khi START (giao diện
   chưa có nút này: CHƯA CÓ, T15; nếu không, START bị từ chối vì bo FAULT, `test_start_fault_refused_by_link_check`); kiểm
   dữ liệu còn mới trên giao diện; kiểm hiệu chuẩn đúng phiên bản gá; đặt xe vào tư thế xuất phát theo vạch (R2); bật ghi
   R1, R3; tạo dấu đồng bộ đầu (R7) bằng T7 hoặc T14 (chưa có thì ghi `phuong_phap_do` không có R7 và chỉ chấm các ngưỡng
   đo hoàn toàn bằng video); lập đường; xem trước (không phát lệnh); bấm Bắt đầu đỗ. Phiên tự kiểm lại trạng thái thật
   trước START ([CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) mục 3).
2. **Trong:** người giám sát cầm nút dừng, không ai đứng trong sa bàn; người đưa vật (nhóm VC) đứng ngoài sa bàn và kéo vật
   bằng dây.
3. **Sau:** khi xe đứng yên: chụp R4, đo R2, kiểm cờ R5 và viền vật; tạo dấu đồng bộ cuối bằng T7/T14 (sau khi lần chạy kết
   thúc, telemetry không còn được ghi nên E-stop không dùng được, mục 2.1); xuất log (GD2); ghi dòng biên bản (GD6)
   **trước** khi chạy lần kế.

## 3. Dựng tham chiếu độc lập trên cao (R1) và kiểm nó (TC-1)

### 3.1. Mục đích

Kế hoạch mục 12 ("Có đánh giá định vị/BEV bằng tham chiếu độc lập, không dùng cùng một đầu ra tự xác nhận chính nó") và mục
14 ("Có tham chiếu độc lập cho sai số vị trí/hướng/khoảng cách"). Tư thế cuối đo bằng thước (R2) chỉ cho một điểm lúc xe
đứng yên. Camera trên cao cho cả quỹ đạo, khoảng hở trong lúc chạy, và dùng lại được cho định vị (DV-1, DV-3) và BEV (NT-2).

### 3.2. Dụng cụ

| Dụng cụ | Ghi chú |
|---|---|
| Thước thép ≥ 3 m (hoặc thước dây), thước kẹp | Tài liệu dự án chưa ghi đã có ([GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md) mục 2.2) |
| Băng dính màu, bút dạ | Dấu chữ thập cho mốc |
| Camera trên cao | CHƯA CHỐT: camera USB thứ năm, điện thoại, hoặc webcam khác. **Không** dùng một trong bốn camera của xe. Cần nhìn thấy toàn sa bàn cộng ≈ 10 cm lề |
| Giá treo cứng ở độ cao H ≈ 2 m (hoặc cao hơn), không rung | Camera dịch sau khi khớp thì phải khớp lại |
| Marker ArUco in giấy phẳng (ví dụ từ điển `DICT_4X4_50`, cạnh ≈ 8 cm), in đúng 100 %, đo cạnh bằng thước kẹp | `cv2.aruco` có trong `.venv` (OpenCV 5.0.0; kiểm bằng lệnh import ngày 24/09/2026). Công cụ dùng nó: CHƯA CÓ |
| Bảng hiệu chuẩn in sẵn (`calibration/bang_in/`) | Để hiệu chuẩn nội tham camera trên cao ([HIEU_CHUAN_CAMERA.md](HIEU_CHUAN_CAMERA.md)) |
| "Xe giả": tấm đế phẳng mang hai marker ở đúng độ cao dự kiến trên xe, có dấu tâm và một **thước thẳng cứng dài ≥ 0,65 m (nên 1 m)** gắn chặt, song song với trục hướng; hai đầu thước là hai điểm đo hướng bằng thước thép so với mốc sàn | Dùng ở TC-1 trước khi có xe; đặt thêm LiDAR C1 lên tấm này thì dùng luôn cho DV-1. Hướng từ hai đầu thước: 0,37–0,62° với 0,65 m, 0,24–0,41° với 1 m, nếu mỗi điểm ± 3–5 mm (TÍNH, mục 3.6). Vạch hướng ngắn 0,25 m cho 1,0–1,6°, không đủ kiểm N-L2 (mục 3.5 bước 4) |

### 3.3. Hệ tọa độ sa bàn

1. Gốc O ở một góc sa bàn; trục x dọc cạnh dài; trục y vuông góc, nằm bên trái khi nhìn theo chiều +x; góc dương ngược
   chiều kim đồng hồ (cùng quy ước với hệ xe của dự án, [autopark/README.md](../README.md) mục 10).
2. Kiểm vuông góc bằng tam giác 0,6 / 0,8 / 1,0 m. Đường chéo sai 1 mm ứng với góc lệch ≈ 0,12° (TÍNH: dc/dθ = a·b/c =
   0,48 m/rad).
3. Dán **mốc kiểm soát** mỗi 0,5 m trên cả sa bàn (sa bàn 3 × 2 m: 7 × 5 = 35 mốc), đo tọa độ từng mốc bằng thước từ hai cạnh
   đã kiểm vuông. Dán thêm **≥ 8 điểm kiểm tra** ở chỗ khác, **không** dùng để khớp. Ghi vào một tệp mốc (ví dụ
   `moc_sa_ban.csv`: tên, x, y, người đo, ngày).
4. Đo vạch ô, chân vật cản, tư thế xuất phát theo cùng hệ; ghi vào tệp bố trí tham chiếu (mục 1.1).

### 3.4. Camera trên cao

1. Gá cố định, nhìn gần thẳng xuống. Khóa phơi sáng và nét nếu camera cho phép. Camera của dự án ở phơi sáng tự động có thể
   đổi nhịp giữa 23,85 và 29,3 khung/s giữa các lần mở ([hardware_inventory.md](hardware_inventory.md), dòng "FPS thật đo được"), nên phải ghi thời điểm của **từng**
   khung.
2. Độ phân giải trên sàn (TÍNH, mô hình lỗ kim, bỏ qua méo): sa bàn rộng 3,2 m trên 640 / 1280 / 1920 pixel là 5,0 / 2,5 /
   1,7 mm/pixel. Ở H = 2,0 m, phủ 3,2 m cần góc nhìn ngang ≈ 77°; ở H = 2,5 m cần ≈ 65°.
3. Hiệu chuẩn nội tham trước khi khớp. Nếu là camera cùng loại với camera xe (130° theo nhà bán, chưa đo) thì dùng mô hình
   fisheye như [HIEU_CHUAN_CAMERA.md](HIEU_CHUAN_CAMERA.md). Công cụ hiện gọi camera theo cổng hub 1–4, nên camera trên cao
   cần cách mở khác: CHƯA CÓ (mục 7, T11).
4. Nếu laptop tự ghi camera trên cao (cùng đồng hồ `perf_counter`, khỏi phải đồng bộ R7), cắm nó vào **cổng gốc riêng**,
   không qua hub của bốn camera: hub đó đã có khung MJPEG bị cắt khi chạy chung ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md)
   mục 2). Kiểm lại số khung bị cắt của bốn camera khi có thêm camera này. Nếu ghi bằng máy khác hay điện thoại thì phải
   đồng bộ bằng R7.

### 3.5. Phép chiếu mặt sàn

1. Khử méo ảnh bằng nội tham.
2. Tìm tâm các mốc kiểm soát trong ảnh. Khớp phép chiếu mặt sàn (homography) từ mọi mốc, có loại ngoại lai; đồng thời ước
   lượng tư thế camera (`solvePnP`) để bù độ cao ở bước 3.6.
3. Báo sai số dư của các mốc dùng để khớp (RMS và lớn nhất), rồi sai số trên **điểm kiểm tra riêng**. Chỉ số trên điểm kiểm
   tra mới là độ chính xác của tham chiếu.
4. Ngưỡng chấp nhận tham chiếu (đề xuất, theo tỉ lệ 3:1 ở [NGUONG_NGHIEM_THU_DE_XUAT.md](NGUONG_NGHIEM_THU_DE_XUAT.md) mục
   0, áp lên giá trị lớn nhất của ngưỡng): sai số lớn nhất trên điểm kiểm tra ≤ 1,7 cm để kiểm N-D1 (5 cm), ≤ 1 cm để kiểm
   N-L1 (3 cm), ≤ 0,7 cm nếu muốn dùng R1 cho N-D5 (2 cm). Hướng (thêm tối 24/09/2026, TÍNH, CHƯA ĐO): sai số hướng lớn nhất
   (so với đường gốc dài ở TC-1) ≤ 1,7° để kiểm N-D2 (5°), ≤ 1,33° để kiểm N-L3 (4°), ≤ 1° để kiểm N-L5 (3°), ≤ 0,67° để
   kiểm N-L2 (2°).

### 3.6. Marker trên xe và bù độ cao

1. Hai marker trên mặt phẳng nằm ngang của xe, **cách nhau xa nhất có thể** (đầu và đuôi). Sau giai đoạn 7, đo bằng thước vị
   trí tâm mỗi marker so với tâm trục sau (x, y) và độ cao h so với sàn.
2. Marker cao h mà dùng thẳng phép chiếu mặt sàn thì bị lệch ≈ h·r / (H − h), với r là khoảng cách ngang từ điểm ngay dưới
   camera (TÍNH). Ví dụ H = 2,0 m: h = 0,10 m, r = 1,0 m lệch 5,3 cm; h = 0,15 m, r = 1,5 m lệch 12,2 cm. Vì vậy **phải**
   dùng phép chiếu của mặt phẳng z = h (từ tư thế camera ở 3.5 bước 2), không dùng thẳng phép chiếu mặt sàn.
3. Sai số của h cũng lan sang vị trí: sai 5 mm ở h cho ≈ 0,4 cm ở r = 1,5 m, H = 2,0 m (TÍNH, ≈ Δh·r/H).
4. Hướng xe lấy từ đường nối tâm hai marker. Sai số hướng ≈ √2·σ/d, với σ là sai số vị trí mỗi marker và d là khoảng cách
   hai marker (TÍNH): d = 0,25 m cho 0,65° nếu σ = 2 mm, 0,97° nếu σ = 3 mm, 1,62° nếu σ = 5 mm. Cùng công thức cho hai điểm
   đo bằng thước (R2): d = 0,65 m cho 0,37° / 0,62° (σ = 3 / 5 mm), d = 1 m cho 0,24° / 0,41°. Muốn ≤ 0,67° (kiểm N-L2)
   với σ = 5 mm thì d ≥ 0,61 m; muốn ≤ 0,33° (một phần ba trung vị 1° của N-L2) với σ = 3 mm thì d ≥ 0,73 m (TÍNH, script
   tạm tối 24/09/2026, không lưu trong repo).

### 3.7. TC-1 — kiểm tham chiếu bằng "xe giả" (làm được trước khi có xe)

1. Đặt "xe giả" (mục 3.2) ở ≥ 10 tư thế trải đều sa bàn, gồm các góc sa bàn (thị sai lớn nhất) và ≥ 3 hướng khác nhau. Đo
   mỗi tư thế bằng R2; hướng đo từ hai đầu thước thẳng ≥ 0,65 m trên xe giả (không dùng vạch 0,25 m), để TC-1 đo được sai
   số hướng của R1 dưới 1°.
2. Ghi 5–10 s video R1 ở mỗi tư thế, lấy tư thế trung vị.
3. Báo sai số R1 so với R2: vị trí (trung vị, lớn nhất), hướng (trung vị, lớn nhất), và độ tản giữa các khung (xe giả đứng
   yên nên độ tản là nhiễu của R1).
4. Kết luận theo 3.5 bước 4: R1 dùng được cho ngưỡng nào, không dùng được cho ngưỡng nào. Ghi biên bản (ví dụ
   `tham_chieu_tren_cao_<ngay>.json`: tham số camera, mốc, sai số từng điểm, kết luận) vào `docs\evidence\nghiem_thu\`.
5. Làm lại TC-1 mỗi khi camera trên cao bị dịch, khi đổi độ cao marker, và ở đầu mỗi ngày nghiệm thu (rút gọn: 3 tư thế).

Nếu đặt LiDAR C1 lên xe giả thì cùng buổi này có luôn tham chiếu độc lập cho định vị (DV-1). Lưu ý: sai số R2 của chính các
tư thế xe giả (± 3–5 mm mỗi điểm, ước tính) cộng vào kết quả TC-1, nên TC-1 cho **cận trên** của sai số R1.

### 3.8. Đầu ra của R1 cho mỗi lần chạy

Tệp tư thế tham chiếu, mỗi khung một dòng: thời điểm (theo đồng hồ đã đồng bộ), x, y, hướng của tâm trục sau, số marker thấy,
sai số dư. Từ đó tính tư thế cuối (trung vị của 1 s cuối khi xe đứng yên), quỹ đạo, tốc độ, và khoảng hở tới vật trong bố
trí tham chiếu (footprint xe đặt theo tư thế R1). Công cụ làm việc này: CHƯA CÓ (mục 7, T4, T5).

### 3.9. Khi không có camera trên cao

Dùng R2 + R4 cho tư thế cuối và khoảng còn lại; R5 cho khoảng hở; R3 (video bên hông) cho thời gian, quãng dừng, tốc độ.
Không có quỹ đạo, nên không kiểm được N-L5 và phần "trong lúc chạy" của N-D5.

### 3.10. Độ chính xác kỳ vọng của R1 (tổng hợp, CHƯA ĐO)

| Thành phần | Cỡ (TÍNH hoặc ước tính) |
|---|---|
| Độ phân giải trên sàn | 1,7–5,0 mm/pixel tùy độ phân giải camera (3.4) |
| Mốc kiểm soát đo bằng thước | ± 2–3 mm mỗi mốc (ước tính) |
| Thị sai do độ cao marker | Tới hàng chục cm nếu không bù; ≈ 0,4 cm với sai 5 mm ở h sau khi bù (3.6) |
| Hướng từ hai marker cách 0,25 m | 0,65–1,62° tùy sai số mỗi marker 2–5 mm (3.6) |
| Tổng, nếu bù độ cao và đo kỹ | Vị trí ≈ 1 cm, hướng ≈ 1–1,6°. **Không dùng con số này làm kết quả**: TC-1 quyết định |

Hướng là phần yếu nhất. Nếu TC-1 cho sai số hướng > 1,7°, R1 không kiểm được N-D2; khi đó dùng R2 với hai điểm cách nhau xa
hơn (dấu ở đầu và đuôi xe, hoặc vạch dọc hai bên hông xe). Với hai marker cách 0,25 m (0,65–1,62°), R1 không kiểm được N-L2
(cần ≤ 0,67°) và chỉ kiểm được N-L5 khi TC-1 cho ≤ 1° (thêm tối 24/09/2026, TÍNH).

## 4. Bảng tổng hợp kịch bản

"Số lần" là đề xuất, theo [NGUONG_NGHIEM_THU_DE_XUAT.md](NGUONG_NGHIEM_THU_DE_XUAT.md) mục 10. "Làm được ngay" là phần
tiền nghiệm thu (MP) hoặc bàn thử (BT) chạy được với phần mềm và thiết bị hiện có.

| Mã | Tên | Nhóm 16.3 | Điều kiện trước | Số lần | Làm được ngay | Trạng thái |
|---|---|---|---|---|---|---|
| DO-1 | Đỗ vuông góc lùi vào ô rộng, xuất phát chuẩn | Đỗ cơ sở | ĐK-XT | 10 | MP | CHƯA THỬ |
| DO-2 | Đỗ vuông góc từ năm tư thế xuất phát | Đỗ cơ sở | ĐK-XT | 15 | MP | CHƯA THỬ |
| DO-3 | Đỗ vuông góc, ô và lối đi hẹp dần (ba mức) | Đỗ cơ sở | ĐK-XT, DO-1 đạt | 5 × 3 | MP | CHƯA THỬ |
| DO-4 | Đỗ song song (ô 1,60 L và 1,35 L) | Đỗ cơ sở | ĐK-XT, DO-1 đạt | 10 + 5 | MP | CHƯA THỬ |
| DO-5 | Lùi thẳng dài trong hành lang hẹp | Đỗ cơ sở | ĐK-XT | 5 | MP | CHƯA THỬ |
| DO-6 | Quay đầu nhiều lần đổi chiều | Điều khiển/an toàn (đổi chiều) | ĐK-XT | 5 | MP | CHƯA THỬ |
| DI-1 | Đích lấn vật cản hoặc ra ngoài sa bàn | (V1: đặt đích, 16.4 ý 4) | Phần mềm; với xe thật: bo nối, đường dừng sẵn sàng | 3 × 3 | MP | CHƯA THỬ |
| DI-2 | Đích hợp lệ nhưng không có đường (hoặc chỉ có đường quá nhiều lần đổi chiều) | (16.4 ý 8; kế hoạch 13) | Như DI-1 | 3 × 2 | MP | CHƯA THỬ |
| DI-3 | Đích trong vùng chưa quan sát | (16.4 ý 8) | Như DI-1 | 3 | MP | CHƯA THỬ |
| DI-4 | Trạng thái thật không khớp lúc START | (16.4 ý 8) | Như DI-1 | 3 × 4 | MP (test) | CHƯA THỬ |
| VC-1 | Vật chắn phía trước khi đang tiến | Vật cản mới | ĐK-XT, chính sách sau vật cản đã chốt | 10 | BT (LiDAR thật, xe ảo) | CHƯA THỬ |
| VC-2 | Vật chắn phía sau khi đang lùi | Vật cản mới | Như VC-1 | 10 | BT (cần `--scenario` có đoạn lùi) | CHƯA THỬ |
| VC-3 | Vật bên hông vùng thân xe quét qua khi rẽ | Vật cản mới | Như VC-1 | 10 | BT (LiDAR thật, xe ảo, cần `--scenario` có đoạn cong); MP: CHƯA CÓ công cụ | CHƯA THỬ |
| VC-4 | Vật chiếm đích | Vật cản mới | Như VC-1 | 10 | MP (gần đúng, xem VC-4) | CHƯA THỬ |
| VC-5 | Vật chắn đường, đích còn trống: dừng, lập đường mới | Vật cản mới | Như VC-1 | 10 | MP | CHƯA THỬ |
| VC-6 | Vật mới ngoài hành lang: không dừng | Vật cản mới | Như VC-1 | 5 | BT | CHƯA THỬ |
| NT-1 | Ba mức ánh sáng | Nhận thức | ĐK-AI; bản động: ĐK-XT | 20 ảnh + 5 lần DO-1 mỗi mức | BT (một phần) | CHƯA THỬ |
| NT-2 | Vật ở mép ảnh và vùng chồng lấn hai camera | Nhận thức | ĐK-AI, giai đoạn 7 | 3 × 16 điểm | TH | CHƯA THỬ |
| NT-3 | Vật thấp hơn mặt phẳng quét LiDAR | Nhận thức | ĐK-AI; bản động: ĐK-XT | 10 tĩnh + 5 động | Không | CHƯA THỬ |
| NT-4 | Vật không có trong tập huấn luyện | Nhận thức | ĐK-AI | 10 mỗi vật | Không | CHƯA THỬ |
| NT-5 | Vùng che khuất, chưa quan sát, camera thiếu giữ UNKNOWN | Nhận thức | Giai đoạn 7; phần camera: ĐK-AI | 3 × 3 | TH (rig tổng hợp) | CHƯA THỬ |
| CB-1 | Mất một camera hoặc cả hub khi đang chạy | Liên lạc/cảm biến | ĐK-XT | 10 (5 + 5) | BT | CHƯA THỬ |
| CB-2 | Camera đứng hình, ảnh cũ | Liên lạc/cảm biến | ĐK-XT, công cụ tiêm lỗi (T6) | 10 | Test nguồn giả | CHƯA THỬ |
| CB-3 | Mất LiDAR (rút cáp) khi đang chạy | Liên lạc/cảm biến | ĐK-XT | 10 | BT | CHƯA THỬ |
| CB-4 | ToF không hợp lệ | Liên lạc/cảm biến | ĐK-XT, ToF + mã đọc (T8) | 10 | Không | CHƯA THỬ |
| CB-5 | Mất telemetry/lệnh; kết nối lại | Liên lạc/cảm biến; Điều khiển/an toàn (reconnect) | ĐK-XT; trước đó M0–M2 (GIAI_DOAN_6 L2, L3, L7) | 10 (4 + 3 + 3) | MP (test) | CHƯA THỬ |
| CB-6 | Mất định vị giữa lúc chạy | Liên lạc/cảm biến | ĐK-XT, T2, T6 | 10 | MP (test) | CHƯA THỬ |
| AT-1 | Nút STOP phần mềm khi đang chạy | Điều khiển/an toàn | ĐK-XT; trước đó M1–M2 (L15) | 10 | MP | CHƯA THỬ |
| AT-2 | E-stop khi đang chạy, rồi nhả | Điều khiển/an toàn | ĐK-XT; trước đó M1–M2 (L10–L12) | 10 (M3: CHƯA CHỐT) | MP (test) | CHƯA THỬ |
| AT-3 | Khởi động lại bo hoặc chương trình laptop khi đang chạy | Điều khiển/an toàn (reset) | ĐK-XT; trước đó M0–M1 (L9) | 10 | MP (test) | CHƯA THỬ |
| AT-4 | Nguồn yếu, sụt áp (chỉ ở mức bàn, có bảo vệ) | Điều khiển/an toàn | Mạch đo điện áp + ngưỡng (L13, L14) | 3 | Không | CHƯA THỬ |
| AT-5 | Chế độ quan sát: người lái, phần mềm không gửi lệnh | (kế hoạch 13; tiền nghiệm thu) | MN300 + bo + định vị; cách đấu dây đã chốt | 5 | MP | CHƯA THỬ |
| DV-1 | Định vị tĩnh tại điểm đo bằng thước | (16.4 ý 1) | ĐK-BT | ≥ 6 điểm × 2 loạt | **BT, làm được ngay** | CHƯA THỬ |
| DV-2 | Hướng gốc sau khởi động lại mô-tơ | (16.4 ý 1) | ĐK-BT | 5 cặp | **BT, làm được ngay** | CHƯA THỬ |
| DV-3 | Định vị khi xe chạy so với R1 | (16.4 ý 1) | Giai đoạn 7, TC-1; xe chạy tay (AT-5) hoặc tự lái | theo các lần AT-5, DO | Không | CHƯA THỬ |
| LD-1 | Chạy dài 30 phút bốn camera + LiDAR + AI | (16.1; 16.4 ý 2) | ĐK-BT; máy nghiệm thu | 1 mỗi máy | **BT, làm được ngay** | CHƯA THỬ |
| TC-1 | Kiểm tham chiếu trên cao bằng "xe giả" (mục 3.7) | (điều kiện của mọi kịch bản dùng R1) | Camera trên cao, giá, marker | ≥ 10 tư thế | **BT, khi có camera trên cao** | CHƯA THỬ |

`L`, `W` trong các kịch bản là chiều dài và bề rộng footprint của xe **đo ở B1 sau giai đoạn 7** (kể cả gá), chưa có.

## 5. Chi tiết từng kịch bản

### 5.1. Đỗ cơ sở (DO)

**DO-1 — Đỗ vuông góc lùi vào ô rộng, xuất phát chuẩn**

| | |
|---|---|
| Bố trí | Sa bàn theo mục 1.1. Một ô vuông góc ở cạnh dưới, rộng W + 0,20 m, sâu L + 0,19 m (cùng phần dư như ô 0,34 × 0,50 m của `scenarios/bai_do_xe.json` so với xe giả định 0,14 × 0,31 m). Hai bên ô là hai vật V1 hoặc hai xe mẫu, cao hơn mặt phẳng quét LiDAR. Xuất phát P1: tâm trục sau cách miệng ô ≥ 1 m theo phương vuông góc, xe song song cạnh dài; đánh dấu bằng băng dính dưới hai bánh. Đích: xe lùi vào, đầu hướng ra ngoài ô (như `scenarios/sa_ban_3x2_hai_hop.json`). Ánh sáng L1 |
| Hệ thống phải | Người dùng kéo/xoay đích vào ô trên giao diện; hệ thống kiểm footprint đích, lập đường tiến/lùi hợp giới hạn lái; xem trước không phát lệnh; bấm Bắt đầu đỗ; phiên kiểm lại trạng thái thật; xe chạy có phản hồi, giảm tốc gần đích, dừng, báo COMPLETED |
| Đo | Sai số vị trí và hướng cuối; thân xe trong ô; khoảng hở nhỏ nhất tới hai vật cạnh ô; số lần đổi chiều (lập / thực); thời gian; tốc độ đo lớn nhất; can thiệp; dừng giả |
| Đo độc lập, độ chính xác kỳ vọng | R1 cho quỹ đạo và tư thế cuối (≈ 1 cm / 1–1,6°, chờ TC-1); R2 + R4 cho tư thế cuối (± 3–5 mm mỗi điểm), làm song song với R1 ở 3 lần đầu để kiểm chéo; R5 cờ 2 cm trên mặt hai vật cạnh ô và viền chân vật; R3 cho tốc độ và đổi chiều (± một khung) |
| Số lần | 10 |
| Dữ liệu ghi | GD1–GD6 |
| Công cụ, lệnh | MP (tiền nghiệm thu, chạy được ngay): `.venv\Scripts\python.exe -X utf8 run_app.py scenarios\sa_ban_3x2_hai_hop.json`, rồi ở ngăn "Mô phỏng" chọn "VehicleIO: GỬI lệnh tới bo" trong ô "Nhánh chạy khi bấm Bắt đầu đỗ", thẻ "Bo điều khiển" để mặc định "Bo mô phỏng (mặc định)" (nhãn đổi khuya 24/09/2026; trước là "VehicleIO → bo mô phỏng"); xong bấm "Xuất log CSV…". Xe thật: CHƯA CÓ (mục 7, T1, T2) *(cập nhật 25/09/2026: T1 đã có từ `6db5087`; còn chặn là T2: START với cổng thật luôn bị từ chối `START_NO_POSE_SOURCE`)* |
| Điều kiện trước | ĐK-XT; AT-5 và DV-3 đạt |
| Ngưỡng | N-D1 … N-D9, N-V1, N-P4 |
| Trạng thái | CHƯA THỬ. Mô phỏng giai đoạn 0 và `VEHICLE_IO` mô phỏng có ca tương tự (CHE_DO_QUAN_SAT.md mục 7: 0,60 cm / +1,15°, định vị lý tưởng); không tính là nghiệm thu |

**DO-2 — Đỗ vuông góc từ năm tư thế xuất phát**

| | |
|---|---|
| Bố trí | Như DO-1. Năm tư thế xuất phát ghi trước, đánh dấu và đo bằng thước: P1 như DO-1; P2 dịch ngang 0,30 m về phía ô; P3 như P1 nhưng xoay +30°; P4 ngược hướng P1 (180°); P5 xa ô ≥ 2 m theo phương dọc. Mỗi tư thế phải có đường trong mô phỏng với cấu hình xe đo trước khi đưa vào nghiệm thu; tư thế nào không có đường thì thay và ghi lý do theo cách phân loại ở DO-3 (không ghi "vô nghiệm" chỉ vì planner hết giờ; kế hoạch 13: "Tự đỗ từ nhiều tư thế xuất phát trong phạm vi đã định") |
| Hệ thống phải | Như DO-1, từ mỗi tư thế |
| Đo | Như DO-1; thêm tư thế xuất phát đo được so với tư thế đã lập đường |
| Đo độc lập, độ chính xác kỳ vọng | Như DO-1 |
| Số lần | 5 tư thế × 3 = 15 |
| Dữ liệu ghi | GD1–GD6 |
| Công cụ, lệnh | MP: chép `scenarios\sa_ban_3x2_hai_hop.json` thành năm tệp mới với `start` khác nhau (không sửa tệp gốc), rồi chạy như DO-1 với từng tệp. Xe thật: CHƯA CÓ |
| Điều kiện trước | ĐK-XT; DO-1 đạt |
| Ngưỡng | N-D1 … N-D9, N-V1, N-P4 |
| Trạng thái | CHƯA THỬ |

**DO-3 — Đỗ vuông góc, ô và lối đi hẹp dần**

| | |
|---|---|
| Bố trí | Như `perpendicular_case` trong [evaluation/hard_cases.py](../autopark/evaluation/hard_cases.py): hàng xe mẫu đỗ vuông góc hai bên ô, ô sâu L + 0,09 m. Ba mức: (a) ô rộng W + 0,09 m, lối đi 1,70 L (`perp_aisle_170`); (b) W + 0,07 m, 1,35 L (`perp_aisle_135`); (c) W + 0,06 m, 1,15 L (`perp_aisle_115`). Chỉ sang mức sau khi mức trước đạt. Nhãn `feasible` của các ca này đặt cho xe giả định; với xe đo phải chạy lại mô phỏng trước. Mức nào planner không trả đường trong mô phỏng với cấu hình xe đo (TIMEOUT hoặc NO_PATH, chạy khi máy rảnh, ghi ngân sách thời gian) thì không đem chạy xe thật ở mức đó, và ghi đúng điều quan sát: "planner không tìm được đường (TIMEOUT/NO_PATH) trong N s". TIMEOUT/NO_PATH không chứng minh vô nghiệm (docstring [evaluation/hard_cases.py](../autopark/evaluation/hard_cases.py); [KIEM_THU_DO_BEN_GIAI_DOAN_0.md](KIEM_THU_DO_BEN_GIAI_DOAN_0.md) mục 4, 6; [GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md) mục 5.1). Phân loại nguyên nhân (sửa tối 24/09/2026): (1) "giới hạn hình học của sa bàn" chỉ khi có lập luận hình học cho thấy vô nghiệm với xe đo (GIAI_DOAN_4_CHUAN_BI.md mục 5.2); (2) "giới hạn planner / ngân sách thời gian" khi mức đó có đường chứng (witness) với xe đo, kiểm độc lập như `tests/test_hard_cases_labels.py`, mà planner vẫn không ra. Đường chứng trong `docs/evidence/hard_cases/witness_20260924.json` dựng cho xe giả định (`configs/vehicle_default.json`), nên với xe đo phải tìm và kiểm lại; (3) "chưa rõ nguyên nhân" khi chưa có cả hai |
| Hệ thống phải | Như DO-1; được phép nhiều lần đổi chiều |
| Đo | Như DO-1; trọng tâm là chạm (N-D4) và đổi chiều (N-D6) |
| Đo độc lập, độ chính xác kỳ vọng | Như DO-1; R5 viền chân mọi xe mẫu |
| Số lần | 5 mỗi mức |
| Dữ liệu ghi | GD1–GD6 |
| Công cụ, lệnh | MP. Từ commit `10a4735` (25/09/2026), `bench --json` tự tạo thư mục kết quả trước khi chạy ca; trước đó phải tạo tay, thiếu thì mất kết quả (mục 2.3). Lệnh tạo tay vẫn dùng được: `if not exist runs\nghiem_thu\mo_phong mkdir runs\nghiem_thu\mo_phong`. Chạy: `.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.bench --cases perp_aisle_170,perp_aisle_135,perp_aisle_115 --json runs\nghiem_thu\mo_phong\do3.json` (thêm `--config configs\vehicle_measured.json` khi có tệp này, [GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md) mục 4). Chạy khi máy rảnh: TIMEOUT phụ thuộc tải CPU ([KIEM_THU_DO_BEN_GIAI_DOAN_0.md](KIEM_THU_DO_BEN_GIAI_DOAN_0.md) mục 4). Xe thật: CHƯA CÓ |
| Điều kiện trước | ĐK-XT; DO-1 đạt |
| Ngưỡng | N-D1 … N-D4, N-D6 … N-D9, N-V1 (N-D5 không áp) |
| Trạng thái | CHƯA THỬ |

**DO-4 — Đỗ song song**

| | |
|---|---|
| Bố trí | Như `parallel_case` trong `evaluation/hard_cases.py`: hai xe mẫu đỗ sát lề, ô giữa hai xe; xe xuất phát ở làn đường, đã đi quá ô, phải lùi vào. (a) ô dài 1,60 L, làn rộng 0,52 m (`parallel_160`); (b) ô 1,35 L, làn 0,46 m (`parallel_135`). Bề rộng làn là số tuyệt đối đặt cho xe giả định: kiểm lại bằng mô phỏng với xe đo |
| Hệ thống phải | Đỗ song song có đổi chiều; kế hoạch 13: "Có kết quả đỗ vuông góc và song song; mọi thất bại đều được ghi" |
| Đo | Như DO-1 |
| Đo độc lập, độ chính xác kỳ vọng | Như DO-1; R5 ở mặt hai xe mẫu |
| Số lần | (a) 10; (b) 5 |
| Dữ liệu ghi | GD1–GD6 |
| Công cụ, lệnh | MP (từ commit `10a4735`, 25/09/2026, `bench --json` tự tạo thư mục kết quả; trước đó thư mục `runs\nghiem_thu\mo_phong` phải có trước, mục 2.3): `.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.bench --cases parallel_160,parallel_135 --json runs\nghiem_thu\mo_phong\do4.json`. Xe thật: CHƯA CÓ |
| Điều kiện trước | ĐK-XT; DO-1 đạt |
| Ngưỡng | (a): N-D1 … N-D9, N-V1; (b): như DO-3 |
| Trạng thái | CHƯA THỬ |

**DO-5 — Lùi thẳng dài trong hành lang hẹp**

| | |
|---|---|
| Bố trí | Như `reverse_along_corridor`: hành lang rộng ≈ 1,29 L (quá hẹp để quay đầu), hai tường bằng thanh xốp; đích ngay sau lưng xe, cách 1,0 m |
| Hệ thống phải | Lùi có phản hồi khoảng 1 m, giữ trong hành lang, không chạm tường, dừng đúng đích |
| Đo | Như DO-1; thêm lệch ngang lớn nhất khi lùi (chỉ báo số, chưa có ngưỡng); sai số bám tốc độ và góc lái trên đoạn lùi đều (đoạn thẳng dài nên hợp để đo) |
| Đo độc lập, độ chính xác kỳ vọng | R1 cho lệch ngang dọc đường và tốc độ; R3 cho tốc độ (quãng theo thước / thời gian thật giữa khung); R2 tư thế cuối; R5 viền tường. Tốc độ và góc lái đo trong `telemetry.csv` (R6) chỉ để đối chiếu |
| Số lần | 5 |
| Dữ liệu ghi | GD1–GD6 |
| Công cụ, lệnh | MP (từ commit `10a4735`, 25/09/2026, `bench --json` tự tạo thư mục kết quả; trước đó thư mục `runs\nghiem_thu\mo_phong` phải có trước, mục 2.3): `.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.bench --cases reverse_long_corridor --json runs\nghiem_thu\mo_phong\do5.json`. Xe thật: CHƯA CÓ |
| Điều kiện trước | ĐK-XT |
| Ngưỡng | N-D1, N-D2, N-D4, N-D7 … N-D9, N-V1; N-K1 … N-K4 khi đã có số (mục 9 của tệp ngưỡng: CHƯA ĐỀ XUẤT) |
| Trạng thái | CHƯA THỬ |

**DO-6 — Quay đầu nhiều lần đổi chiều**

| | |
|---|---|
| Bố trí | Như `corridor_uturn` `uturn_w70`: hành lang cụt rộng 0,70 m, dài 1,30 m cho xe giả định. Với xe đo, chọn bề rộng sao cho mô phỏng cần 3–7 lần đổi chiều. Xuất phát đầu hướng vào trong; đích quay ngược 180° |
| Hệ thống phải | Thực hiện đúng số lần đổi chiều của quỹ đạo; mỗi lần theo trình tự giảm tốc → xác nhận dừng → đổi chiều (kế hoạch 9 bước 6; 16.3 dòng "Điều khiển/an toàn: Đổi chiều") |
| Đo | Số lần đổi chiều thực; với từng lần: \|v đo\| lúc đổi và thời gian đứng ở 0; tư thế cuối; chạm |
| Đo độc lập, độ chính xác kỳ vọng | R3 đếm đổi chiều và kiểm không có chuyển động ngược chiều trước khi xe dừng hẳn (± một khung); R2 tư thế cuối. `telemetry.csv` (R6) để đối chiếu thời gian đứng ở 0 |
| Số lần | 5 |
| Dữ liệu ghi | GD1–GD6 |
| Công cụ, lệnh | MP (từ commit `10a4735`, 25/09/2026, `bench --json` tự tạo thư mục kết quả; trước đó thư mục `runs\nghiem_thu\mo_phong` phải có trước, mục 2.3): `.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.bench --cases uturn_w70 --json runs\nghiem_thu\mo_phong\do6.json`. Xe thật: CHƯA CÓ |
| Điều kiện trước | ĐK-XT; bảng B5 (đổi chiều, dòng D6) đã đo |
| Ngưỡng | N-D1, N-D2, N-D4, N-D6, N-K5 |
| Trạng thái | CHƯA THỬ |

### 5.2. Đích không hợp lệ và từ chối chạy (DI)

Kế hoạch 13: "Không có đường phù hợp thì giữ dừng, không ép planner phải trả một đường bất kỳ". Các kịch bản DI không có
chuyển động, nên chạy được với xe thật ngay khi có bo nối qua giao diện, với điều kiện đường dừng phần cứng vẫn sẵn sàng.
*(Cập nhật 25/09/2026, đọc mã ở HEAD `54cb3e2`: giao diện chọn được cổng bo thật từ `6db5087` (T1), nhưng chưa đủ. Với
cổng thật, START luôn bị từ chối ngay ở bước đầu (`START_NO_POSE_SOURCE`), trước khi mở cổng và trước mọi kiểm FAULT, xe
lăn, tư thế (`application/vehicle_link.py`). Đích sai hay không có đường thì bị chặn trên laptop trước START, không liên
lạc với bo, và tư thế xuất phát planner dùng vẫn là của tệp kịch bản. Vì vậy "không bắt đầu được" trên bo thật hôm nay
không chứng minh kiểm DI nào đã chạy; bản xe thật của DI còn chờ T2, mục 7.)*

**DI-1 — Đích lấn vật cản hoặc ra ngoài sa bàn**

| | |
|---|---|
| Bố trí | Sa bàn DO-1. Ba biến thể: (a) kéo đích để footprint đích chồng lên vật cạnh ô; (b) đích nằm một phần ngoài biên sa bàn; (c) vị trí đích đúng nhưng hướng làm thân xe lấn vật |
| Hệ thống phải | Báo đích không hợp lệ; không lập đường; không bắt đầu được; bo giữ DISARMED |
| Đo | Có lập đường không; bo có bị ARM không; có COMMAND chuyển động nào không |
| Đo độc lập, độ chính xác kỳ vọng | R3: xe không nhúc nhích. R6 để đối chiếu: `telemetry.csv` toàn DISARMED. Không có đại lượng hình học cần đo *(ghi chú 25/09/2026, đọc mã: đích bị chặn trước START thì không lần chạy nào được mở, mà telemetry chỉ được ghi khi lần chạy đang mở (R7, mục 2.1), nên `telemetry.csv` không có dòng nào của lần thử này; R6 ở đây CHƯA dùng được)* |
| Số lần | 3 mỗi biến thể |
| Dữ liệu ghi | GD1, GD2, ảnh chụp màn hình |
| Công cụ, lệnh | MP (chạy được ngay): `.venv\Scripts\python.exe -X utf8 run_app.py scenarios\sa_ban_3x2_hai_hop.json` rồi kéo đích vào hộp. Xe thật: CHƯA CÓ (T1) *(cập nhật 25/09/2026: T1 đã có từ `6db5087`; bản xe thật còn chờ T2, xem ghi chú đầu mục 5.2)* |
| Điều kiện trước | Phần mềm; với xe thật: bo nối, xe đứng trên sa bàn, đường dừng sẵn sàng |
| Ngưỡng | N-P11 |
| Trạng thái | CHƯA THỬ ở xe thật. Phần mô phỏng thuộc điều kiện giai đoạn 0 đã ĐẠT ngày 20/09 ("đích nằm trong vật cản bị từ chối", BAO_CAO_GIAI_DOAN_0.md mục 3) |

**DI-2 — Đích hợp lệ nhưng không có đường (hoặc chỉ có đường quá nhiều lần đổi chiều)**

| | |
|---|---|
| Bố trí | Hai biến thể. (a) Ô vuông góc bị vật chắn kín mọi phía, không còn lối vào: vô nghiệm hiển nhiên về hình học vì vùng đích tách rời vùng xuất phát. (b) Ô song song rất ngắn như `parallel_115` (ô 1,15 L, làn 0,40 m). Ở HEAD 9bcc30c ca này mang nhãn `infeasible` (kỳ vọng kiểm thử, chưa kiểm chứng độc lập). Bản sửa đang làm song song tối 24/09/2026 (chưa commit, tệp này không kiểm) của `evaluation/hard_cases.py` đổi nhãn thành `feasible`, với một đường dựng giải tích 279 lần đổi chiều: có nghiệm nhưng không thực dụng. *(Cập nhật 25/09/2026: bản sửa đó đã xong và đã commit, push (`10a4735`); ngoài đường 279 lần còn có đường chứng 13 lần đổi chiều, 1,32 m ([witness_ngan_song_song_20260924.json](evidence/hard_cases/witness_ngan_song_song_20260924.json)), nên "không thực dụng" là nhận xét về các đường dài, không phải tính chất của ca; planner hết giờ/NO_PATH ở ca này là giới hạn của planner. Đường 13 lần vẫn có nhịp 0,95–1,7 cm.)* Vì vậy (b) kiểm hành vi khi planner hết giờ, hoặc khi nó trả một đường có quá nhiều lần đổi chiều |
| Hệ thống phải | (a): không trả đường (NO_PATH hoặc hết giờ), không chạy, báo lý do. (b): không trả đường thì không chạy; trả đường mà số lần đổi chiều vượt giới hạn chấp nhận được thì không được đem chạy. Giới hạn đó CHƯA CHỐT (N-D6), và mã hiện chưa có kiểm này: `portfolio` chỉ ưu tiên đường ít đổi chiều hơn, giao diện hiện số lần đổi chiều ở bước lập đường (đọc mã 24/09/2026; mục 7, T12) |
| Đo | Kết quả lập đường, số lần đổi chiều nếu có đường, thời gian lập đường; bo không ARM |
| Đo độc lập, độ chính xác kỳ vọng | Như DI-1 |
| Số lần | 3 mỗi biến thể |
| Dữ liệu ghi | GD1, GD2 |
| Công cụ, lệnh | MP: (a) dựng trong giao diện mô phỏng (`run_app.py`), đặt vật cản kín quanh ô; (b) (từ commit `10a4735`, 25/09/2026, `bench --json` tự tạo thư mục kết quả; trước đó thư mục `runs\nghiem_thu\mo_phong` phải có trước, mục 2.3) `.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.bench --cases parallel_115 --json runs\nghiem_thu\mo_phong\di2.json`. Kiểm ngày 24/09/2026 trên máy bàn: `parallel_115` hết giờ (TIMEOUT) sau 20 s ([GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md) mục 1.1). Hết giờ không chứng minh vô nghiệm; tiêu chí nghiệm thu chỉ là "không chạy" |
| Điều kiện trước | Như DI-1 |
| Ngưỡng | N-P11 |
| Trạng thái | CHƯA THỬ |

**DI-3 — Đích trong vùng chưa quan sát**

| | |
|---|---|
| Bố trí | Đích đặt sau một vật cao che khuất khỏi LiDAR và camera (vùng UNKNOWN), hoặc ngoài tầm cảm biến |
| Hệ thống phải | UNKNOWN chặn như vật cản: đích không hợp lệ hoặc không có đường; không chạy |
| Đo | Như DI-1; thêm ảnh bản đồ hợp nhất có vùng UNKNOWN |
| Đo độc lập, độ chính xác kỳ vọng | Vùng che khuất dựng hình học từ vị trí vật (R2) và vị trí cảm biến; so với bản đồ |
| Số lần | 3 |
| Dữ liệu ghi | GD1, GD2, ảnh bản đồ |
| Công cụ, lệnh | MP: `.venv\Scripts\python.exe -X utf8 run_app.py scenarios\giai_doan_0_unknown.json` (vùng UNKNOWN có sẵn trong kịch bản, không phải kết quả AI). Xe thật: CHƯA CÓ |
| Điều kiện trước | Như DI-1; giai đoạn 7 (cảm biến trên xe) để vùng che khuất là thật |
| Ngưỡng | N-P11, N-G3 |
| Trạng thái | CHƯA THỬ |

**DI-4 — Trạng thái thật không khớp lúc START**

| | |
|---|---|
| Bố trí | Sa bàn DO-1. Bốn biến thể sau khi đã lập đường: (a) đẩy xe lệch 10 cm; (b) xoay xe 10°; (c) xe còn lăn; (d) bo đang FAULT (E-stop vừa nhả, chưa CLEAR_FAULT) |
| Hệ thống phải | START bị từ chối; bo không bị bỏ lại ở ARMED; `start_refusals.csv` có dòng `START_CHECK` "TỪ CHỐI"; log của lần chạy trước giữ nguyên ([CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) mục 3) |
| Đo | Có từ chối không, lý do; trạng thái bo |
| Đo độc lập, độ chính xác kỳ vọng | R2 đo độ lệch đã tạo (± 3–5 mm, ≈ 1–1,6°); R3 xe không nhúc nhích |
| Số lần | 3 mỗi biến thể |
| Dữ liệu ghi | GD1, GD2 |
| Công cụ, lệnh | MP (chạy được ngay, không chạm thiết bị): `.venv\Scripts\python.exe -X utf8 -m pytest tests\test_session_vehicle.py -k refused`. Xe thật: CHƯA CÓ |
| Điều kiện trước | Như DI-1; nguồn tư thế thật (T2) cho (a), (b) *(cập nhật 25/09/2026: từ `6db5087`, START với cổng thật bị từ chối ngay ở bước đầu (`START_NO_POSE_SOURCE`), trước khi mở cổng và trước các kiểm FAULT, xe lăn, tư thế; khi đó `start_refusals.csv` có dòng `START_NO_POSE_SOURCE`, không phải `START_CHECK` "TỪ CHỐI" (`tests/test_vehicle_board_ui.py`). Vì vậy cả (c), (d) trên bo thật cũng cần T2; chạy trước khi có T2 thì "bị từ chối" không chứng minh kiểm nào)* |
| Ngưỡng | N-P11 |
| Trạng thái | CHƯA THỬ ở xe thật (có test mô phỏng: `test_start_is_refused_when_the_real_state_disagrees`, `test_start_refused_heading_off`, `test_start_refused_vehicle_rolling`, `test_start_fault_refused_by_link_check`) |

### 5.3. Vật cản mới (VC)

Luồng hệ thống phải theo (kế hoạch 13): phát hiện thay đổi → kiểm vùng thân xe dự kiến đi qua → yêu cầu dừng và kiểm chứng
trạng thái dừng → cập nhật bản đồ, quan sát lại → đích còn hợp lệ? Không: chờ người dùng thay đích hoặc hủy. Có: tìm đường
mới; không có đường thì giữ dừng; có đường thì kiểm lại và tiếp tục theo **chính sách đã chốt** (tự tiếp tục hay chờ xác
nhận: CHƯA CHỐT, TONG_HOP_DU_AN.md mục 5.1; kế hoạch 13 khuyên ưu tiên người xác nhận khi thử ban đầu). Vật được kéo bằng
dây từ ngoài sa bàn; không ném vật sát xe (kế hoạch 13 bước 8).

**VC-1 — Vật chắn phía trước khi đang tiến**

| | |
|---|---|
| Bố trí | Đoạn tiến thẳng ≥ 1,5 m (sa bàn DO-1 hoặc DO-2). Vật V1 đặt sẵn ngoài hành lang, nối dây. Khi xe chạy ổn định ở ≤ N-V1, kéo vật vào hành lang thân xe, tới vị trí đã đánh dấu cách đầu xe ≥ 30 cm theo hướng chạy và cách LiDAR ≥ 40 cm |
| Hệ thống phải | Phát hiện vật mới trong hành lang, dừng, xác nhận đứng yên, hủy đường, cập nhật bản đồ, đánh giá lại theo luồng ở trên. Sau khi dừng, dời vật đi và chờ 10 s: xe không tự chạy lại |
| Đo | `t_vật`, `t_phát_hiện`, `t_lệnh_dừng`, `t_đứng_yên`; quãng từ `t_vật` tới đứng yên; khoảng còn lại tới vật; chạm; có chạy lại khi dời vật không; lý do dừng ghi trong log (qua `VehicleIO`: lý do lấy từ `link.json` `result.reason`, thời điểm xấp xỉ bằng dòng STOP đầu tiên của `commands.csv` tới khi có T13; ở bản BT nhánh SIM: `safety_events.json` của gói `export_run`) |
| Đo độc lập, độ chính xác kỳ vọng | R3 video bên hông, thước dọc đường, vật và xe cùng trong khung (± một khung, mục 2.1); R2 khoảng còn lại (± 3–5 mm); R7 để lấy `t_phát_hiện − t_vật` (R7 CHƯA CÓ, mục 2.1: tới khi có T7/T14, hiệu này ghi CHƯA ĐO ĐƯỢC) |
| Số lần | 10 |
| Dữ liệu ghi | GD1–GD6 |
| Công cụ, lệnh | BT (LiDAR thật, xe ảo; chạm thiết bị, người thao tác): `.venv\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app` (Kết nối → Tìm đường đỗ → Bắt đầu đỗ, rồi đưa hộp vào trước LiDAR cách ≥ 40 cm), hoặc `.venv\Scripts\python.exe -X utf8 -m autopark.fusion.demo --seconds 30`. Bản BT chỉ đo phần phát hiện của LiDAR thật; quãng dừng là của xe ảo. R7 ở bản BT: chỉ bằng T14 (không có bo, không E-stop); chưa có T14 thì hiệu mốc video − mốc log: CHƯA ĐO ĐƯỢC. Xe thật: CHƯA CÓ |
| Điều kiện trước | ĐK-XT; chính sách sau vật cản đã chốt |
| Ngưỡng | N-P1, N-P2, N-P3, N-P10, N-D4 |
| Trạng thái | CHƯA THỬ. Bản BT cũng chưa thử: đưa tay/hộp vào khi xe ảo chạy mới kiểm bằng nguồn quét kịch bản ([GIAI_DOAN_3_CHUAN_BI.md](GIAI_DOAN_3_CHUAN_BI.md) mục 3, 5) |

**VC-2 — Vật chắn phía sau khi đang lùi**

| | |
|---|---|
| Bố trí | Như VC-1 nhưng trong đoạn lùi (pha lùi vào ô của DO-1, hoặc DO-5); vật kéo vào sau đuôi xe, cách đuôi ≥ 30 cm |
| Hệ thống phải | Như VC-1. Phía sau phải được LiDAR hoặc camera sau quan sát; cung LiDAR bị gá che phía sau phải được ghi sau giai đoạn 7 và công bố |
| Đo | Như VC-1 |
| Đo độc lập, độ chính xác kỳ vọng | Như VC-1 |
| Số lần | 10 |
| Dữ liệu ghi | GD1–GD6 |
| Công cụ, lệnh | BT (LiDAR thật, xe ảo; chạm thiết bị, người thao tác): `.venv\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app --scenario scenarios\sa_ban_3x2_hai_hop.json`. Lập đường offline với kịch bản này (tối 24/09/2026, `.venv`, script tạm, xe `configs/vehicle_default.json`, chỉ hai hộp của kịch bản): 1 lần đổi chiều, tiến 0,37 m rồi lùi 2,43 m vào ô. Kết nối → Tìm đường đỗ; vật LiDAR thật được thêm vào sa bàn nên đường trên bàn thử có thể khác, phải xem đoạn lùi đã lập trên màn hình, rồi đánh dấu trên sàn một điểm trên đoạn lùi còn lại, cách LiDAR ≥ 40 cm. Mốc trên sa bàn: LiDAR đứng yên ở xuất phát (0,5; 1,5) hướng +x; đoạn lùi (offline) nằm PHÍA TRƯỚC–PHẢI của LiDAR (x theo LiDAR +0,24…+1,90 m, y −1,10…+0,16 m, cách LiDAR 0,25…2,20 m), không nằm phía sau nó. Bắt đầu đỗ; khi xe ảo đã qua điểm đổi chiều và đang lùi, kéo vật vào điểm đó, sau đuôi xe ảo ≥ 30 cm theo chiều lùi. KHÔNG đặt vật "phía sau LiDAR": với sa bàn mặc định của `lidar_app` (tiến thẳng 1,50 m, 0 lần đổi chiều, cùng lần lập đường) và cả với kịch bản trên, chỗ đó nằm ngoài hành lang nên xe ảo đúng ra không dừng (thành VC-6). `autopark.fusion.demo` không dùng được cho VC-2 vì đích cố định, đường tiến thẳng. R7 ở bản BT: như VC-1. Xe thật: CHƯA CÓ |
| Điều kiện trước | Như VC-1 |
| Ngưỡng | N-P1, N-P2, N-P3, N-P10, N-D4 |
| Trạng thái | CHƯA THỬ |

**VC-3 — Vật bên hông vùng thân xe quét qua khi rẽ**

| | |
|---|---|
| Bố trí | Trong đoạn cong của DO-1 hoặc DO-2, đặt vật V1 vào vùng mà góc trước phía ngoài sẽ quét qua, **không** nằm trên đường tâm quỹ đạo. Vị trí tính trước từ quỹ đạo đã lập (vùng quét của thân xe) và đánh dấu trên sàn |
| Hệ thống phải | Phát hiện vật chạm hành lang **thân xe** (không chỉ đường tâm) và dừng như VC-1 |
| Đo | Như VC-1; khoảng còn lại đo từ góc thân xe gần vật nhất |
| Đo độc lập, độ chính xác kỳ vọng | Như VC-1; R1 nếu có, vì góc thân xe khó thấy trong video bên hông |
| Số lần | 10 |
| Dữ liệu ghi | GD1–GD6 |
| Công cụ, lệnh | MP: CHƯA CÓ. Nút "Vật cản giả" không tạo được tình huống này: `_inject_test_obstacle` (`ui/main_window.py`) luôn đặt hộp 12 cm trên đường tâm xe, cách đầu hoặc đuôi 30 cm; `Session.inject_obstacle` dừng với mọi vật chèn vào, không kiểm hành lang (đọc mã 24/09/2026), nên xe dừng ở MP không chứng minh được gì về hành lang thân xe. Quy tắc hành lang (`fusion/bridge.py`, `ObstacleBridge`, `path_corridor`: hợp các hình thân xe nới `path_margin` 0,10 m dọc phần quỹ đạo còn lại) có test mô phỏng nguồn quét giả trên đường thẳng: `.venv\Scripts\python.exe -X utf8 -m pytest tests\test_fusion.py -k off_the_path` (vật cách 0,5 m bên hông không làm dừng, vật trên đường làm dừng; 1 test đạt, chạy lại tối 24/09/2026); ca góc thân xe quét qua ở đoạn cong: CHƯA CÓ TEST. BT (LiDAR thật, xe ảo; chạm thiết bị, người thao tác): `.venv\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app --scenario scenarios\sa_ban_3x2_hai_hop.json` (sa bàn mặc định của `lidar_app` là đường thẳng, không có đoạn cong). Kết nối → Tìm đường đỗ → Bắt đầu đỗ; đặt hộp cạnh quỹ đạo xe ảo, trong vùng thân xe quét qua ở đoạn cong, không nằm trên đường tâm, cách LiDAR ≥ 40 cm; CHƯA THỬ. R7 ở bản BT: như VC-1. Xe thật: CHƯA CÓ |
| Điều kiện trước | Như VC-1 |
| Ngưỡng | N-P1, N-P2, N-P3, N-P10, N-D4 |
| Trạng thái | CHƯA THỬ. Giới hạn cần công bố: tia LiDAR trong thân xe nới lề bị bỏ (trên xe thật đề xuất lề 3 cm, [GIAI_DOAN_3_CHUAN_BI.md](GIAI_DOAN_3_CHUAN_BI.md) mục 3b), nên vật sát thân xe hơn lề đó có thể không được thấy |

**VC-4 — Vật chiếm đích**

| | |
|---|---|
| Bố trí | Sa bàn DO-1. Khi xe đang chạy, trước pha lùi vào ô, kéo vật V1 vào giữa ô |
| Hệ thống phải | Dừng; nhận ra **đích** bị chiếm, khác với đường bị chắn (kế hoạch 7: "phân biệt đường bị chắn với chính đích bị chiếm"; kế hoạch 13: "tạo hành vi khác nhau đúng thiết kế"); chờ người dùng thay đích hoặc hủy; không lập đường tới đích bị chiếm, không chạy tiếp. Mã hiện tại (đọc 24/09/2026, `application/session.py`): mọi vật mới làm `MAP_CHANGED` → dừng → `WAIT_REPLAN`; đích bị chiếm chỉ được nhận ra khi lập lại đường (kiểm footprint đích), và việc lập lại đường do người dùng bấm. Chưa có sự kiện riêng "đích bị chiếm" lúc đang chạy |
| Đo | Như VC-1; lý do trên giao diện và trong log |
| Đo độc lập, độ chính xác kỳ vọng | Như VC-1 |
| Số lần | 10 |
| Dữ liệu ghi | GD1–GD6 |
| Công cụ, lệnh | MP (chỉ gần đúng): nút "Vật cản giả" luôn đặt hộp 12 cm trên đường tâm, 30 cm sau đuôi khi đang lùi (`_inject_test_obstacle`, `ui/main_window.py`); muốn hộp rơi vào ô phải bấm đúng lúc trong pha lùi; ngoài lúc đang chạy thì không sửa được vật cản (chỉ ở EDITING/READY). Xe dừng vì `MAP_CHANGED` như với mọi vật chèn vào, và đích bị chiếm chỉ được nhận ra khi người dùng lập lại đường, nên bản MP không kiểm được việc "phân biệt đường bị chắn với đích bị chiếm" lúc đang chạy. Có sẵn test giai đoạn 0 cho ca "đích bị chiếm sau khi dừng" ([KIEM_THU_DO_BEN_GIAI_DOAN_0.md](KIEM_THU_DO_BEN_GIAI_DOAN_0.md) mục 1). Xe thật: CHƯA CÓ |
| Điều kiện trước | Như VC-1 |
| Ngưỡng | N-P1, N-P2, N-P10, N-P11, N-D4 |
| Trạng thái | CHƯA THỬ |

**VC-5 — Vật chắn đường, đích còn trống: dừng, lập đường mới**

| | |
|---|---|
| Bố trí | Sa bàn DO-1. Vật V1 kéo vào đoạn quỹ đạo phía trước; bố trí sao cho còn đường vòng khác tới đích |
| Hệ thống phải | Dừng như VC-1; cập nhật bản đồ; lập đường mới từ chỗ dừng; tiếp tục theo chính sách đã chốt; đỗ xong. Nếu planner không tìm được đường mới thì giữ dừng (ghi DỪNG ĐÚNG) |
| Đo | Phần dừng như VC-1; có lập được đường mới không; phần đỗ như DO-1 |
| Đo độc lập, độ chính xác kỳ vọng | Như VC-1 và DO-1 |
| Số lần | 10 |
| Dữ liệu ghi | GD1–GD6 |
| Công cụ, lệnh | MP: giao diện mô phỏng ("Vật cản giả", rồi "Chọn lại vị trí" và lập đường từ vị trí vừa dừng, [autopark/README.md](../README.md) mục 3). Xe thật: CHƯA CÓ |
| Điều kiện trước | Như VC-1 |
| Ngưỡng | N-P1, N-P2, N-P10; phần đỗ: N-D1 … N-D9 |
| Trạng thái | CHƯA THỬ |

**VC-6 — Vật mới ngoài hành lang: không dừng**

| | |
|---|---|
| Bố trí | Khi xe đang chạy, kéo vật V1 tới vị trí cách hành lang thân xe ≥ 20 cm. Hành lang là thân xe nới `path_margin` 0,10 m dọc phần quỹ đạo còn lại ([GIAI_DOAN_3_CHUAN_BI.md](GIAI_DOAN_3_CHUAN_BI.md) mục 2 quy tắc 3) |
| Hệ thống phải | Không dừng; vật được ghi nhớ và đưa vào bản đồ ở lần cập nhật sau |
| Đo | Có dừng không; vật có trong bản đồ sau lần chạy không |
| Đo độc lập, độ chính xác kỳ vọng | R2 khoảng cách vật – hành lang (± 3–5 mm); R3 |
| Số lần | 5; ngoài ra đếm dừng giả ở mọi lần chạy nhóm DO |
| Dữ liệu ghi | GD1–GD6 |
| Công cụ, lệnh | BT: như VC-1, đặt vật ngoài đường của xe ảo. Xe thật: CHƯA CÓ |
| Điều kiện trước | Như VC-1 |
| Ngưỡng | N-P4 |
| Trạng thái | CHƯA THỬ. Bàn thử 22/09: 0 dừng giả trong 202 vòng với LiDAR đứng yên (GIAI_DOAN_3_CHUAN_BI.md mục 3) |

### 5.4. Nhận thức (NT)

Các kịch bản NT dựa vào camera và AI. Nếu hướng giấy phép WoodScape không cho nối AI vào costmap/planner thì chỉ còn phần
LiDAR; khi đó kết quả phải ghi đúng như vậy, và điều kiện V1 thứ ba cần hướng khác (xem
[NGUONG_NGHIEM_THU_DE_XUAT.md](NGUONG_NGHIEM_THU_DE_XUAT.md) mục 8). Phần tĩnh làm khi xe đứng yên, bo DISARMED, nên an toàn
hơn và làm được từ giai đoạn 7.
*(Cập nhật 25/09/2026: hướng giấy phép đã quyết ngày 25/09/2026 là cho nối AI (Valeo chưa xác nhận), nên câu điều kiện "nếu
… không cho nối AI" ở trên nay là **phương án dự phòng** (hướng 1 của GIAY_PHEP_DU_LIEU.md): nếu cách đọc bị phản bác thì
chạy `ui.lidar_app` không có `--camera-ai`, chỉ còn phần LiDAR và ghi kết quả đúng như vậy. Công cụ đưa AI vào phiên:
[AI_DIEU_KHIEN_XE.md](AI_DIEU_KHIEN_XE.md); chưa camera nào được hiệu chuẩn nên AI chưa tạo vật cản trên bàn thật.)*

**NT-1 — Ba mức ánh sáng**

| | |
|---|---|
| Bố trí | Sa bàn DO-1. Vật V1–V6 đặt ở vị trí đo bằng thước quanh xe đứng yên, cách thân xe 0,3–1,0 m. Ánh sáng L1, L2, L3 (mục 1.1) |
| Hệ thống phải | Bản đồ hợp nhất có vật ở đúng chỗ (OCCUPIED), sau vật là UNKNOWN, sàn trống là FREE hoặc UNKNOWN; sau đó đỗ được như DO-1 ở cả ba mức |
| Đo | Với từng vật và từng mức: có phát hiện không, vị trí trên BEV so với thước, báo động giả trên sàn; số khung/s và khung bị cắt của từng camera; tỉ lệ thành công DO-1 theo mức |
| Đo độc lập, độ chính xác kỳ vọng | R2 tọa độ chân vật (± 3–5 mm); ảnh có nhãn tô tay từ đầu (`--no-draft`, [GAN_NHAN_SA_BAN.md](GAN_NHAN_SA_BAN.md)) cho tỉ lệ pixel |
| Số lần | Tĩnh: 20 bộ ảnh mỗi mức; động: 5 lần DO-1 mỗi mức |
| Dữ liệu ghi | GD1, GD3, bộ ảnh chụp, GD4; phần động thêm GD2, GD5, GD6 |
| Công cụ, lệnh | BT (chạm thiết bị): `.venv-train\Scripts\python.exe -X utf8 -m autopark.ui.rig_app --lidar` (nút "Chụp bộ ảnh"); rồi `.venv\Scripts\python.exe -X utf8 -m autopark.perception.bev snapshot runs\rig_snapshots\<ngay_gio>` (hiện từ chối vì chưa có `calibration/cam_p*.json`, [BEV.md](BEV.md) mục 5). Ghi phiên để phát lại: `.venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 60 --name nt1_l1 --out runs\rig_bench\<ngay> --record runs\rig_recordings\nt1_l1`. Xe thật: CHƯA CÓ |
| Điều kiện trước | ĐK-AI; bản động: ĐK-XT |
| Ngưỡng | N-A1 … N-A3, N-G1, N-G3, N-C1; phần động: N-D8 |
| Trạng thái | CHƯA THỬ. Ghi chú: ở phơi sáng tự động, nhịp khung của một camera có thể khác giữa các lần mở (23,85 hay ≈ 29 khung/s, cơ chế chưa xác định, [hardware_inventory.md](hardware_inventory.md), dòng "FPS thật đo được"); cảnh sáng, nhiều chi tiết thì dễ có khung bị cắt ở 720p ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 2) |

**NT-2 — Vật ở mép ảnh và vùng chồng lấn hai camera**

| | |
|---|---|
| Bố trí | Xe đứng yên. Vật V1 đặt lần lượt ở 8 vị trí: bốn vùng chồng lấn giữa hai camera kề nhau (quanh bốn góc xe) và bốn điểm gần mép ảnh của từng camera; mỗi vị trí ở 0,3 m và 0,8 m từ thân xe. Tọa độ đo bằng thước |
| Hệ thống phải | Vật xuất hiện trên BEV tại vị trí đối chiếu được (kế hoạch 6: "không chỉ hiện một ô màu bất kỳ"); hai camera cho cùng một vị trí |
| Đo | Vị trí điểm chân vật trên BEV của từng camera và BEV hợp nhất; chênh lệch giữa hai camera |
| Đo độc lập, độ chính xác kỳ vọng | R2 (± 3–5 mm); R1 nếu đã có |
| Số lần | 3 lần mỗi điểm (8 vị trí × 2 khoảng cách = 16 điểm) |
| Dữ liệu ghi | GD1, bộ ảnh chụp, costmap BEV |
| Công cụ, lệnh | TH (chạy được ngay, không chạm thiết bị): `.venv\Scripts\python.exe -X utf8 -m autopark.perception.bev synthetic`. BT/XT: như NT-1 |
| Điều kiện trước | ĐK-AI; giai đoạn 7 |
| Ngưỡng | N-G1, N-G2, N-A2 |
| Trạng thái | CHƯA THỬ |

**NT-3 — Vật thấp hơn mặt phẳng quét LiDAR**

| | |
|---|---|
| Bố trí | Vật V3 trong vùng làm việc, trước và sau xe. Tĩnh: xe đứng yên. Động: như VC-1 với V3 |
| Hệ thống phải | LiDAR không thấy vật này. Nếu AI được nối: vật là OCCUPIED hoặc UNKNOWN, không bao giờ FREE; xe dừng như VC-1. Nếu AI không được nối: kết quả mong đợi là **không thấy**. Đó là giới hạn của V1 phải công bố, không tính là đạt |
| Đo | Như NT-1 (tĩnh), như VC-1 (động) |
| Đo độc lập, độ chính xác kỳ vọng | Như NT-1 và VC-1 |
| Số lần | 10 tĩnh, 5 động |
| Dữ liệu ghi | Như NT-1 và VC-1 |
| Công cụ, lệnh | Như NT-1. Xe thật: CHƯA CÓ |
| Điều kiện trước | ĐK-AI; bản động: ĐK-XT |
| Ngưỡng | N-A2, N-G3; phần động: N-P1 … N-P3, N-D4 |
| Trạng thái | CHƯA THỬ |

**NT-4 — Vật không có trong tập huấn luyện**

| | |
|---|---|
| Bố trí | Xe đứng yên; lần lượt V2 (đen mờ, LiDAR có thể phản hồi kém; lần đặt hộp p08 của [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 6 là hộp đen), V4, V5, V6, ở vị trí đo bằng thước |
| Hệ thống phải | Không cam kết phát hiện (kế hoạch 16.3). Ghi đúng điều thấy |
| Đo | Phát hiện theo N-A2; LiDAR có tia chạm vật không |
| Đo độc lập, độ chính xác kỳ vọng | R2 |
| Số lần | 10 mỗi vật |
| Dữ liệu ghi | Như NT-1 |
| Công cụ, lệnh | Như NT-1 |
| Điều kiện trước | ĐK-AI |
| Ngưỡng | N-A2 (báo số); kết quả không đạt được ghi thành giới hạn đã công bố, không bỏ ra khỏi báo cáo |
| Trạng thái | CHƯA THỬ. Trên dữ liệu công khai, vật lạ nhỏ là điểm yếu (RoadObstacle21, [HUAN_LUYEN.md](../../HUAN_LUYEN.md) mục 8, 10) |

**NT-5 — Vùng che khuất, chưa quan sát, camera thiếu giữ UNKNOWN**

| | |
|---|---|
| Bố trí | Ba biến thể: (a) vật cao ≈ 30 cm đặt 0,5 m trước xe: vùng sau vật; (b) rút một camera: vùng chỉ camera đó thấy; (c) vùng dưới thân xe |
| Hệ thống phải | Các vùng đó là UNKNOWN, không có ô FREE nào |
| Đo | Số ô FREE trong từng vùng (bản đồ hợp nhất và BEV lưu ra tệp) |
| Đo độc lập, độ chính xác kỳ vọng | Vùng che khuất dựng hình học từ vị trí vật đo bằng thước (R2) và vị trí cảm biến |
| Số lần | 3 mỗi biến thể |
| Dữ liệu ghi | GD1, costmap lưu ra tệp, ảnh |
| Công cụ, lệnh | TH (chạy được ngay): `.venv\Scripts\python.exe -X utf8 -m autopark.perception.bev synthetic --drop 2`; test: `.venv\Scripts\python.exe -X utf8 -m pytest tests\test_bev.py tests\test_fusion.py`. BT/XT: như NT-1 |
| Điều kiện trước | Giai đoạn 7; phần camera: ĐK-AI |
| Ngưỡng | N-G3, N-A4 |
| Trạng thái | CHƯA THỬ trên cảm biến dự án (quy tắc đã có test trên rig tổng hợp, [BEV.md](BEV.md) mục 7) |

### 5.5. Mất cảm biến và liên lạc (CB)

Mỗi kịch bản CB trên xe thật chỉ làm ở M3 sau khi tình huống tương ứng của
[GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md) mục 5 (L1–L16) đã đạt ở M0–M2.

**CB-1 — Mất một camera hoặc cả hub khi đang chạy**

| | |
|---|---|
| Bố trí | Sa bàn DO-1. Rút cáp một camera giữa đoạn lùi (5 lần, đổi camera mỗi lần); rút cả hub (5 lần) |
| Hệ thống phải | Camera bị báo thiếu; các camera khác không bị bỏ; phiên dừng hay tiếp tục theo chính sách đã chốt (CHƯA CHỐT); cắm lại không làm xe tự chạy lại |
| Đo | Thời điểm rút (R3 + R7), thời điểm báo thiếu (log), hành vi của phiên, bộ ảnh bỏ camera khỏe |
| Đo độc lập, độ chính xác kỳ vọng | R3 + R7 (± một khung) |
| Số lần | 10 (5 + 5) |
| Dữ liệu ghi | GD1–GD6 |
| Công cụ, lệnh | BT (chạm thiết bị): `.venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 60 --name cb1 --out runs\rig_bench\<ngay> --record runs\rig_recordings\cb1`, rút một camera giữa phiên (L5 ở GIAI_DOAN_6_CHUAN_BI.md). R7 ở bản BT: chỉ bằng T14 (không có bo, không E-stop); chưa có T14 thì hiệu mốc video − mốc log (lúc rút → lúc báo thiếu): CHƯA ĐO ĐƯỢC. Xe thật: CHƯA CÓ |
| Điều kiện trước | ĐK-XT |
| Ngưỡng | N-P9, N-P10 |
| Trạng thái | CHƯA THỬ, cả bản BT (L5: CHƯA THỬ) |

**CB-2 — Camera đứng hình, ảnh cũ**

| | |
|---|---|
| Bố trí | Sa bàn DO-1; một camera ngừng trả khung mới trong 1 s giữa lúc chạy |
| Hệ thống phải | Camera bị coi là treo/thiếu; lớp camera cũ quá 0,5 s bị bỏ; không vùng nào thành FREE vì thiếu dữ liệu |
| Đo | Thời điểm gây lỗi (log của công cụ tiêm lỗi), thời điểm hệ thống báo, hành vi |
| Đo độc lập, độ chính xác kỳ vọng | R3 + R7 |
| Số lần | 10 |
| Dữ liệu ghi | GD1–GD6 |
| Công cụ, lệnh | Chưa có cách gây lỗi an toàn trên phần cứng: khung cũ do driver trả lại đã bị bộ dò loại ([GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md)); camera treo mới có test với nguồn giả (`tests/test_multicam_rig.py`). Cần công cụ tiêm lỗi (mục 7, T6). Test hiện có (không chạm thiết bị, cần torch): `.venv-train\Scripts\python.exe -X utf8 -m pytest tests\test_multicam_rig.py` |
| Điều kiện trước | ĐK-XT; T6 |
| Ngưỡng | N-T4, N-G3, N-P10 |
| Trạng thái | CHƯA THỬ; công cụ CHƯA CÓ |

**CB-3 — Mất LiDAR (rút cáp) khi đang chạy**

| | |
|---|---|
| Bố trí | Sa bàn DO-1; rút cáp USB của C1 giữa đoạn tiến; cắm lại sau 10 s |
| Hệ thống phải | Dừng (LiDAR là lớp bắt buộc); không chạy tiếp khi cắm lại mà không có thao tác |
| Đo | Thời điểm rút, vòng quét cuối (bản ghi LiDAR), lệnh dừng, đứng yên; tên lỗi hiện trên giao diện |
| Đo độc lập, độ chính xác kỳ vọng | R3 + R7 cho thời điểm rút và quãng dừng |
| Số lần | 10 |
| Dữ liệu ghi | GD1–GD6 |
| Công cụ, lệnh | BT (chạm thiết bị): `.venv\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app` (xe ảo chạy, rút cáp; chép nguyên dòng lỗi: `LidarTransportError` hay `ScanReadError`, xem L4 ở GIAI_DOAN_6_CHUAN_BI.md); `.venv\Scripts\python.exe -X utf8 -m autopark.lidar.bench record --out runs\lidar_bench\<ngay> --name cb3_rut_cap --seconds 30` (kỳ vọng thoát mã 1, còn `.npz` và `.analysis.json`). Test (không chạm thiết bị): `.venv\Scripts\python.exe -X utf8 -m pytest tests\test_lidar_unplug.py`. R7 ở bản BT: chỉ bằng T14 (không có bo, không E-stop); chưa có T14 thì hiệu mốc video − mốc log: CHƯA ĐO ĐƯỢC. Xe thật: CHƯA CÓ |
| Điều kiện trước | ĐK-XT |
| Ngưỡng | N-P8, N-P10, N-T3 |
| Trạng thái | CHƯA THỬ với cáp thật (mới có test với cổng serial giả, L4 ở GIAI_DOAN_6_CHUAN_BI.md) |

**CB-4 — ToF không hợp lệ**

| | |
|---|---|
| Bố trí | Rút đầu nối một VL53L1X khi bo đang chạy: trước ở M0, sau ở M2 và M3 |
| Hệ thống phải | Cờ hợp lệ về 0 trong khung telemetry kế tiếp; không số đo nào bị báo thành "xa" hay an toàn ([GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 8); lớp ToF là lớp tùy chọn nên có dừng hay không: CHƯA CHỐT |
| Đo | Cờ trong `telemetry.csv`, hành vi của phiên |
| Đo độc lập, độ chính xác kỳ vọng | R3 + R7 cho thời điểm rút |
| Số lần | 10 |
| Dữ liệu ghi | GD1, GD2 |
| Công cụ, lệnh | CHƯA CÓ: chưa mua ToF (đợt 3), firmware chưa có mã đọc VL53L1X; ở HEAD 9bcc30c chưa có cầu nối `VehicleTelemetry` → `NearFieldReading` (TONG_HOP_DU_AN.md mục 5.4; đang thêm song song, chưa commit, mục 7). *(Cập nhật 25/09/2026: cầu nối đã commit trong `6db5087`: `tof_to_near_field`, `NearFieldLayer.add_telemetry`, vị trí gá GIẢ ĐỊNH ở `configs/tof_mounts_v0.json`; mới kiểm bằng khung telemetry giả và cổng serial GIẢ; ToF chưa vào `Session`/`VehicleLink` ([GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 12). Vẫn chưa có ToF và mã đọc VL53L1X)* |
| Điều kiện trước | ĐK-XT; T8 |
| Ngưỡng | N-T9; tuyệt đối: không số đo nào thành giá trị an toàn |
| Trạng thái | CHƯA THỬ |

**CB-5 — Mất telemetry/lệnh; kết nối lại**

| | |
|---|---|
| Bố trí | Sa bàn DO-1. Ba biến thể giữa lúc chạy: (a) rút USB laptop – ESP32-S3, cắm lại sau 10 s (4 lần); (b) treo chương trình laptop 1 s (3 lần); (c) đóng chương trình laptop rồi mở lại (3 lần) |
| Hệ thống phải | Chung cho mọi biến thể: bo về trung tính khi lệnh cuối hết hạn (`COMMAND_TIMEOUT` → ARMED), về DISARMED khi 0,5 s không có thông điệp (`LINK_TIMEOUT`), xe dừng; từ lúc gây lỗi, không COMMAND enable=1 nào tới bo cho tới `arm()` mới ([GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 5, 6). (a) Rút USB: laptop phát STOP với mã đầu là `LINK_ERROR` (lỗi cổng) hoặc `STALE_TELEMETRY` của phiên, kèm `TELEMETRY_STALE` của `VehicleIO` (Windows có báo lỗi cổng ngay khi rút hay không: CẦN KIỂM). Cắm lại: `reopen()` + `connect()` → DISARMED ([GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md) L3). (b) Treo 1 s: hết treo thì mã dừng đầu tiên của phiên phải là một trong `VEHICLE_STOPPED`/`VEHICLE_NOT_ARMED`/`STALE_TELEMETRY`, giống tập mã của `test_realtime_hang_without_heartbeat_never_resumes`. Trên mô phỏng (cổng serial giả, 24/09/2026), treo 1 s cho `VEHICLE_NOT_ARMED` (`LINK_TIMEOUT`) ở cả 4 pha, sau đó là `VEHICLE_STOPPED`; không có `LINK_ERROR`/`TELEMETRY_STALE`. Đây là đúng dự kiến, không phải lỗi ([CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) mục 8; GIAI_DOAN_6_CHUAN_BI.md L7). Lần chạy kết thúc STOPPED, không gửi lại enable. (c) Đóng chương trình: không đòi mã STOP phía laptop. Đóng cửa sổ bình thường thì `Session.close()` → `VehicleLink.close()` gửi enable=0 rồi DISARM, và bo phải DISARMED ngay (mô phỏng: `test_close_while_running_vehicle_io_stops_then_disarms`). Diệt tiến trình thì bo đi đường L2 (`COMMAND_TIMEOUT` → ARMED, 0,5 s → DISARMED `LINK_TIMEOUT`), kiểm trên bo/máy hiện sóng. Mở lại: `connect()` gửi HELLO mới → bo DISARMED (L9), không chuyển động cho tới `arm()` + COMMAND mới. Ghi rõ lần thử là đóng bình thường hay diệt tiến trình. Bo thật: CHƯA THỬ |
| Đo | Thời điểm gây lỗi; lúc laptop báo STOP và mã dừng đầu tiên ở (a), (b) (mã `STALE_TELEMETRY` của phiên chưa vào `events.csv`: T13; mã của `VehicleIO` và lớp nối thì có); ở (c): lúc đóng/diệt tiến trình, trạng thái bo sau 0,5 s và sau HELLO mới; lúc xung ESC về trung tính (M1), quãng dừng (M3), mọi COMMAND sau khi nối lại |
| Đo độc lập, độ chính xác kỳ vọng | M1: máy hiện sóng trên chân ESC (dụng cụ: tài liệu chưa ghi đã có); M3: R3 + R7 |
| Số lần | 10 (4 + 3 + 3) |
| Dữ liệu ghi | GD1–GD6 |
| Công cụ, lệnh | MP (chạy được ngay, không chạm thiết bị): `.venv\Scripts\python.exe -X utf8 -m pytest tests\test_session_vehicle.py -k "stale or hang or timeout"`. Script treo vòng điều khiển trên bo thật: CHƯA CÓ (L7 ở GIAI_DOAN_6_CHUAN_BI.md; mục 7, T6). Xe thật: CHƯA CÓ |
| Điều kiện trước | ĐK-XT; L2, L3, L7, L9 đạt ở M0–M2 |
| Ngưỡng | N-P7, N-P10, N-T1, N-T10 |
| Trạng thái | CHƯA THỬ trên bo (có test mô phỏng và cổng serial giả: `test_vehicle_io_stale_telemetry_stops_and_reconnect_never_resumes`, `test_realtime_hang_without_heartbeat_never_resumes`, CHE_DO_QUAN_SAT.md mục 7) |

**CB-6 — Mất định vị giữa lúc chạy**

| | |
|---|---|
| Bố trí | Sa bàn DO-1. Nguồn tư thế thôi trả tư thế mới giữa lúc chạy: dùng cờ tiêm lỗi của nguồn tư thế (CHƯA CÓ), hoặc úp một hộp lên LiDAR (cách này cũng có thể làm dừng vì lý do vật cản/bản đồ không hợp lệ; lần nào cũng phải ghi lý do dừng đầu tiên) |
| Hệ thống phải | Dừng `STALE_POSE` (hoặc một lý do dừng khác đúng thiết kế); không chạy lại khi định vị có lại mà không có thao tác |
| Đo | Lý do dừng đầu tiên, thời điểm, quãng dừng. Lý do lấy từ `link.json` `result.reason` (văn bản, không có mã), thời điểm xấp xỉ bằng dòng STOP đầu tiên của `commands.csv` tới khi có T13: `STALE_POSE` của phiên không vào `events.csv` (thử trên bo mô phỏng tối 24/09/2026, script tạm) |
| Đo độc lập, độ chính xác kỳ vọng | R3 + R7 (R7 CHƯA CÓ, mục 2.1) |
| Số lần | 10 |
| Dữ liệu ghi | GD1–GD6 |
| Công cụ, lệnh | MP (không chạm thiết bị): `.venv\Scripts\python.exe -X utf8 -m pytest tests\test_session_vehicle.py -k stale_pose`. Xe thật: CHƯA CÓ (T2, T6, T13) |
| Điều kiện trước | ĐK-XT; T2; T6; T13 |
| Ngưỡng | N-T2, N-P10 |
| Trạng thái | CHƯA THỬ (có test mô phỏng `test_stale_pose_source_stops_the_run`) |

### 5.6. Dừng và an toàn (AT)

**AT-1 — Nút STOP phần mềm khi đang chạy**

| | |
|---|---|
| Bố trí | Sa bàn DO-1; bấm STOP giữa đoạn tiến (5 lần) và giữa đoạn lùi (5 lần), ở tốc độ ổn định |
| Hệ thống phải | Gửi COMMAND enable=0 mỗi nhịp; bo dốc về trung tính; phiên xác nhận đứng yên bằng telemetry mới và kết thúc STOPPED; không tự chạy lại |
| Đo | Lúc bấm, lúc bo nhận (log), effort về 0, đứng yên; quãng dừng |
| Đo độc lập, độ chính xác kỳ vọng | R3 + R7 (± một khung) |
| Số lần | 10 |
| Dữ liệu ghi | GD1–GD6 |
| Công cụ, lệnh | MP (chạy được ngay): `.venv\Scripts\python.exe -X utf8 run_app.py scenarios\sa_ban_3x2_hai_hop.json`, nhánh "VehicleIO: GỬI lệnh tới bo" với thẻ "Bo điều khiển" để "Bo mô phỏng (mặc định)" (trước khuya 24/09/2026 nhãn là "VehicleIO → bo mô phỏng"), bấm dừng khi xe đang chạy. Xe thật: CHƯA CÓ |
| Điều kiện trước | ĐK-XT; L15 đạt ở M1–M2 |
| Ngưỡng | N-P6, N-P10 |
| Trạng thái | CHƯA THỬ |

**AT-2 — E-stop khi đang chạy, rồi nhả**

| | |
|---|---|
| Bố trí | Sa bàn DO-1; nhấn LA38 giữa đoạn tiến ở 0,05 m/s và 0,10 m/s; nhả sau 10 s; rồi làm từng bước CLEAR_FAULT, ARM, COMMAND, quay video bánh ở mỗi bước |
| Hệ thống phải | Phần cứng cắt động lực ESC (phần tử ngắt CHƯA CHỐT); firmware FAULT `ESTOP`, effort = 0 ngay; laptop `VEHICLE_FAULT` (STOP); sau khi nhả vẫn FAULT; không chuyển động cho tới đủ ba thao tác ([GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md) L10, L12) |
| Đo | Lúc nhấn, cờ `ESTOP_INPUT` trong telemetry, điện áp động lực ở ngõ vào ESC (M2), quãng và thời gian tới đứng yên (M3), chuyển động sau khi nhả |
| Đo độc lập, độ chính xác kỳ vọng | (a) của N-P5: kết quả L10 mức M1 (logic analyzer trên dây E-stop, chân ESC, chân GPIO gỡ lỗi), không đo bằng video: R3 + R7 cho ± một khung (≈ 42 ms) cộng ± một khung đồng bộ, vượt 20 ms của tỉ lệ 3:1, và R7 bằng chính nút E-stop là vòng tròn; (b): máy hiện sóng (M2); (c), (d): R3 với nút trong khung (± một khung) + R2 |
| Số lần | 10 ở M2; ở M3: CHƯA CHỐT (hao mòn) |
| Dữ liệu ghi | GD1–GD6 |
| Công cụ, lệnh | MP (không chạm thiết bị): `.venv\Scripts\python.exe -X utf8 -m pytest tests\test_session_vehicle.py -k fault`. Bước CLEAR_FAULT trên giao diện: CHƯA CÓ (T15). Xe thật: CHƯA CÓ |
| Điều kiện trước | ĐK-XT; L10–L12 đạt ở M1–M2 (số của N-P5(a) lấy từ L10 ở M1); phần tử ngắt đã chọn và lắp; T15 |
| Ngưỡng | N-P5, N-P10 |
| Trạng thái | CHƯA THỬ (test mô phỏng `test_vehicle_io_fault_stops_and_start_is_refused_until_cleared`) |

**AT-3 — Khởi động lại bo hoặc chương trình laptop khi đang chạy**

| | |
|---|---|
| Bố trí | Sa bàn DO-1, giữa đoạn tiến: (a) nhấn nút reset trên bo (4 lần); (b) `esp_restart()` qua bản build thử (3 lần); (c) đóng rồi mở lại chương trình laptop (3 lần) |
| Hệ thống phải | Bo BOOT → DISARMED; laptop thấy `TELEMETRY_STALE`, rồi `FIRMWARE_RESET` khi kết nối lại; chân ESC không phát xung khác trung tính trong lúc khởi động lại; không chuyển động cho tới `arm()` + COMMAND mới ([GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md) L9) |
| Đo | Xung ESC (M1), `reset_reason`, quãng dừng (M3), chuyển động sau khi bo lên lại |
| Đo độc lập, độ chính xác kỳ vọng | Máy hiện sóng (M1); R3 + R7 (M3) |
| Số lần | 10 (4 + 3 + 3) |
| Dữ liệu ghi | GD1–GD6 |
| Công cụ, lệnh | Xe thật và bo: CHƯA CÓ (firmware C++ chưa biên dịch; T1) *(cập nhật 25/09/2026: T1 đã có từ `6db5087`; còn chặn: firmware chưa biên dịch và nạp được, và T2, vì START với cổng thật luôn bị từ chối `START_NO_POSE_SOURCE` nên chưa mở được lần chạy nào trên bo thật)* |
| Điều kiện trước | ĐK-XT; L9 đạt ở M0–M1 |
| Ngưỡng | N-P7, N-P10 |
| Trạng thái | CHƯA THỬ (có test mô phỏng `SimVehicleIO.reset_firmware`, [GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 10) |

**AT-4 — Nguồn yếu, sụt áp (chỉ ở mức bàn, có bảo vệ)**

| | |
|---|---|
| Bố trí | M0: nguồn bàn chỉnh được đưa vào ngõ đo điện áp qua bộ chia, hạ dần điện áp. M1: hạ điện áp nguồn cấp cho bo, máy hiện sóng trên chân ESC. Không làm cạn pin thật để thử (L13, L14) |
| Hệ thống phải | `SUPPLY_LOW` chốt khi điện áp dưới ngưỡng, chỉ xóa khi đo lại ≥ ngưỡng; sụt áp làm bo khởi động lại thì chân ESC không phát xung khác trung tính và bo lên lại ở DISARMED |
| Đo | Điện áp lúc báo, trạng thái bo, xung ESC |
| Đo độc lập, độ chính xác kỳ vọng | Đồng hồ vạn năng, máy hiện sóng (dụng cụ: tài liệu chưa ghi đã có) |
| Số lần | 3 |
| Dữ liệu ghi | GD1, GD2, ảnh máy hiện sóng |
| Công cụ, lệnh | CHƯA CÓ: firmware chưa đo điện áp và `min_supply_mv` = 0 (tắt), nên hiện **không phát hiện pin yếu** ([GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md) L13) |
| Điều kiện trước | Mạch đo điện áp, ngưỡng theo loại pin (phiếu kiểm kê MN300 mục B) |
| Ngưỡng | Ngưỡng điện áp CHƯA CHỐT; tuyệt đối: không xung khác trung tính khi sụt áp |
| Trạng thái | CHƯA THỬ; chưa thử được |

**AT-5 — Chế độ quan sát: người lái, phần mềm không gửi lệnh**

| | |
|---|---|
| Bố trí | Sa bàn DO-1. Người lái bằng tay điều khiển RC theo lệnh gợi ý trên giao diện ("Quan sát: tính lệnh, KHÔNG gửi") |
| Hệ thống phải | Tính đường và lệnh nhưng không gửi COMMAND nào; bo DISARMED suốt lần chạy; nếu thấy bo ARMED thì gửi DISARM và kết thúc quan sát ([CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) mục 1, 4). Dùng để kiểm định vị và hợp nhất khi xe chạy **trước** khi cho phần mềm lái (kế hoạch 13, "Khi các khối thật chưa đồng thời sẵn sàng") |
| Đo | Số COMMAND bo nhận (phải 0); quỹ đạo người lái so với quỹ đạo lập; track định vị so với R1 (DV-3) |
| Đo độc lập, độ chính xác kỳ vọng | R1 (chờ TC-1) |
| Số lần | 5 |
| Dữ liệu ghi | GD1–GD5 |
| Công cụ, lệnh | MP (chạy được ngay): `.venv\Scripts\python.exe -X utf8 run_app.py scenarios\sa_ban_3x2_hai_hop.json`, chọn nhánh "Quan sát", lái xe mô phỏng bằng phím mũi tên. Test: `.venv\Scripts\python.exe -X utf8 -m pytest tests\test_session_vehicle.py -k observe`. Xe thật: CHƯA CÓ |
| Điều kiện trước | MN300 + bo + nguồn tư thế thật (T2); cách đấu dây ở chế độ quan sát (ESC nối máy thu RC hay nối ESP32-S3): CHƯA CHỐT |
| Ngưỡng | Tuyệt đối: 0 COMMAND; N-L5 (qua DV-3) |
| Trạng thái | CHƯA THỬ (test mô phỏng `test_observe_logs_commands_and_never_enables_the_board`) |

### 5.7. Định vị (DV)

**DV-1 — Định vị tĩnh tại điểm đo bằng thước**

| | |
|---|---|
| Bố trí | Theo [DINH_VI_LIDAR.md](DINH_VI_LIDAR.md) mục 7 bước 2. C1 dán trên "xe giả" (mục 3.2), có dấu tâm quay và một thước thẳng cứng dài ≥ 0,65 m (nên 1 m) gắn chặt trên xe giả, song song với trục hướng. Hai đầu thước là hai điểm đo hướng; tọa độ hai đầu đo bằng thước thép so với mốc sàn. Đặt trên sàn sa bàn. Ghi bản đồ ở gốc; dời tới ≥ 6 tư thế đo bằng thước, ví dụ (+0,20; 0), (0; +0,20), (+0,30; −0,20) m, hướng 0°, +10°, −20°. Cùng buổi làm bảy lần đặt hộp p01–p06, p08 ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 6) để có N-L0 và chốt dấu góc trái/phải |
| Hệ thống phải | Định vị OK ở mọi tư thế trong bản đồ, với sai số trong ngưỡng; tư thế ngoài cửa sổ hay ngoài bản đồ phải FAILED/AMBIGUOUS, không OK sai |
| Đo | `summary.ok_pose_median` trong `localize.json` so với số đo thước (hướng so theo hiệu đã quấn về ±180°); tỉ lệ vòng OK |
| Đo độc lập, độ chính xác kỳ vọng | R2 cho vị trí (± 3–5 mm mỗi điểm). Hướng lấy từ hai đầu thước dài d: √2·σ/d = 0,24–0,41° với d = 1 m, 0,37–0,62° với d = 0,65 m, σ = 3–5 mm (TÍNH, mục 3.6). Vạch 0,25 m (1,0–1,6°) và thước đo góc KHÔNG đủ cho N-L2 theo tỉ lệ 3:1 (cần ≤ 0,67°); nếu chỉ có những tham chiếu đó thì ghi N-L2 "không kiểm được". R1 chỉ dùng cho hướng khi TC-1 cho sai số hướng lớn nhất ≤ 0,67° |
| Số lần | ≥ 6 tư thế; lặp cả loạt 2 lần, mỗi lần dựng bản đồ mới |
| Dữ liệu ghi | Bản ghi `.npz` + `.analysis.json` mỗi tư thế, bản đồ `costmap.json`, `localize.json`, `track.csv`, biên bản thước |
| Công cụ, lệnh | BT, làm được ngay (chạm thiết bị, người thao tác). Ghi bản đồ: `.venv\Scripts\python.exe -X utf8 -m autopark.lidar.bench record --out runs\lidar_bench\<ngay> --name dv1_goc --seconds 20 --warmup 5`. Dựng bản đồ: `.venv\Scripts\python.exe -X utf8 -m autopark.lidar.occupancy --recording runs\lidar_bench\<ngay>\dv1_goc.npz --out runs\lidar_bench\<ngay>\map_dv1`. Mỗi tư thế: `.venv\Scripts\python.exe -X utf8 -m autopark.lidar.bench record --out runs\lidar_bench\<ngay> --name dv1_d01 --seconds 15 --warmup 5`. Định vị: `.venv\Scripts\python.exe -X utf8 -m autopark.lidar.localize --map runs\lidar_bench\<ngay>\map_dv1 --recording runs\lidar_bench\<ngay>\dv1_d01.npz --out runs\nghiem_thu\<ngay>\dv1_d01 --skip-seconds 3` |
| Điều kiện trước | ĐK-BT |
| Ngưỡng | N-L0, N-L1, N-L2, N-L3, N-T7 |
| Trạng thái | CHƯA THỬ (việc cần người, TONG_HOP_DU_AN.md mục 5.2) |

**DV-2 — Hướng gốc sau khởi động lại mô-tơ**

| | |
|---|---|
| Bố trí | Theo DINH_VI_LIDAR.md mục 7 bước 1: C1 dán cố định, không chạm vào. Ghi hai phiên 20 s; giữa hai phiên dừng mô-tơ (thoát chương trình) rồi chạy lại |
| Hệ thống phải | Định vị phiên hai trên bản đồ phiên một cho θ ≈ 0 trong độ lặp lại. Nếu không, gốc góc đổi theo lần khởi động (khả năng (b) ở DINH_VI_LIDAR.md mục 5, giải thích độ lệch +4,3° chưa rõ nguyên nhân), và phải có bước hiệu chuẩn hướng mỗi lần bật |
| Đo | θ trung vị của phiên hai; độ lệch x, y |
| Đo độc lập, độ chính xác kỳ vọng | Tham chiếu là "không chạm thiết bị" (dán cố định, dấu băng dính quanh đế, kiểm bằng ảnh trước/sau); độ lặp lại ≈ 0,1° (DINH_VI_LIDAR.md mục 7) |
| Số lần | 5 cặp phiên |
| Dữ liệu ghi | Hai `.npz` mỗi cặp, bản đồ, `localize.json`, ảnh đế trước/sau |
| Công cụ, lệnh | BT, làm được ngay (chạm thiết bị). Phiên một: `.venv\Scripts\python.exe -X utf8 -m autopark.lidar.bench record --out runs\lidar_bench\<ngay> --name dv2_c1_a --seconds 20 --warmup 5`. Phiên hai: cùng lệnh với `--name dv2_c1_b`. Bản đồ và định vị: như DV-1, dựng bản đồ từ `dv2_c1_a.npz`, định vị `dv2_c1_b.npz` |
| Điều kiện trước | ĐK-BT |
| Ngưỡng | N-L4 |
| Trạng thái | CHƯA THỬ |

**DV-3 — Định vị khi xe chạy, so với R1**

| | |
|---|---|
| Bố trí | Trong các lần AT-5 (người lái) và các lần DO (tự lái), ở ≤ N-V1 |
| Hệ thống phải | Tư thế OK đủ dày dọc quỹ đạo; không OK sai |
| Đo | Tỉ lệ vòng OK, số vòng liên tiếp không OK, sai số vị trí/hướng so với R1 theo thời gian |
| Đo độc lập, độ chính xác kỳ vọng | R1 (chờ TC-1), đồng bộ R7 |
| Số lần | Theo số lần AT-5 và DO |
| Dữ liệu ghi | GD3 (LiDAR), GD4, GD5 |
| Công cụ, lệnh | Offline trên bản ghi LiDAR của lần chạy (không chạm thiết bị): `.venv\Scripts\python.exe -X utf8 -m autopark.lidar.localize --map <thu_muc_ban_do> --recording <ban_ghi.npz> --out runs\nghiem_thu\<ngay>\dv3_<lan> --track`. Công cụ so track với R1: CHƯA CÓ (T5). Định vị trong phiên: CHƯA CÓ (T2) |
| Điều kiện trước | Giai đoạn 7; TC-1; AT-5 làm được |
| Ngưỡng | N-L3, N-L5, N-T2, N-T7 |
| Trạng thái | CHƯA THỬ (chưa có bản ghi nào của LiDAR đang di chuyển, DINH_VI_LIDAR.md mục 6) |

### 5.8. Chạy dài (LD)

**LD-1 — Chạy dài 30 phút bốn camera + LiDAR + AI**

| | |
|---|---|
| Bố trí | Kế hoạch 16.1: phiên khoảng 30 phút làm bước sàng lọc ban đầu. Bốn camera ở mode đã chốt (hiện 640×480), LiDAR, AI, trên **máy nghiệm thu**; camera nhìn sa bàn thật (không nhìn chỗ tối như các phiên 24/09). Xe đứng yên hoặc bàn thử. Trước phiên: khởi động lại máy 3 lần, mỗi lần chụp một bộ ảnh để kiểm từng camera đúng hướng theo cổng hub. Trong phiên (nếu có dụng cụ): một LED nháy đặt trong khung của cả bốn camera để đo trễ sự kiện → khung |
| Hệ thống phải | Chạy hết 30 phút không reset, không mất kết nối ngoài dự kiến; khung tốt/s, độ lệch bộ ảnh, tuổi AI trong ngưỡng; camera đúng hướng sau mỗi lần khởi động lại |
| Đo | Khung tốt/s mỗi camera theo cửa sổ 10 s, khung bị cắt/xé, khoảng dài nhất không có khung tốt, độ lệch bộ ảnh, thời gian lô AI, tuổi kết quả AI, lệch thời gian giữa vòng LiDAR và bộ ảnh, vòng LiDAR mất, lỗi đọc, CPU/GPU/nhiệt; trễ LED → khung (nếu có LED) |
| Đo độc lập, độ chính xác kỳ vọng | Đây là đo hiệu năng, không có đại lượng hình học. Số lấy từ `.rig.json` (đồng hồ `perf_counter`). Trễ sự kiện → khung cần LED do một nguồn độc lập điều khiển và ghi thời điểm bật: dụng cụ CHƯA CÓ |
| Số lần | 1 mỗi máy (máy bàn làm được ngay; laptop RTX 3050 Ti CHƯA ĐO) |
| Dữ liệu ghi | `.rig.json`; bản ghi phát lại nếu đủ đĩa. Cỡ cho 30 phút ở 640×480 JPEG q95: ≈ 9 GB ở 4,98 MB/s (ĐO ở phiên o03 trên máy bàn 24/09/2026, cảnh tối nên là mức THẤP) và ≈ 27 GB ở ≈ 15 MB/s (ƯỚC LƯỢNG cho cảnh nhiều chi tiết từ ảnh thảm hoa văn, CHƯA ĐO trong phiên thật; [GHI_PHAT_LAI_BAN_THU.md](GHI_PHAT_LAI_BAN_THU.md) mục 5 ý 6 và mục 7). Cảnh sa bàn CHƯA ĐO, tài liệu gốc dự đoán nằm giữa hay trên hai mức này. Trước khi thêm `--record`: ổ chứa cả `runs\rig_recordings` và `runs\rig_bench` phải còn trống ít nhất ≈ 30 GB, hoặc ghi thử 60 s nhìn sa bàn (lệnh ở dòng dưới) rồi lấy `mb_per_s` × 1800 cộng dư. Đĩa đầy giữa phiên thì bộ ghi chuyển "LỖI", bỏ mọi khung sau đó, `rig.bench` trả mã 1 (test với lỗi đĩa đầy giả lập, GHI_PHAT_LAI_BAN_THU.md mục 6), và `.rig.json` ghi cuối phiên trên cùng ổ cũng có thể không ghi được (suy ra, chưa thử). Chỗ trống: máy bàn từ 29/09/2026, ổ D ≈ 30,6 GB (đọc 29/09/2026, sát mức ≈ 30 GB ở trên; [chuyển máy](CHUYEN_MAY_BAN.md) mục 4); máy bàn tới 25/09/2026, ổ D ≈ 74 GB (đọc tối 24/09/2026; tài liệu gốc ghi 75 GB); laptop RTX 3050 Ti CHƯA ĐO |
| Công cụ, lệnh | BT, làm được ngay (chạm thiết bị): `.venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 1800 --name ld1 --out runs\rig_bench\<ngay>`. Thêm `--record runs\rig_recordings\ld1` chỉ khi ổ còn trống ≥ 30 GB (xem dòng trên). Ghi thử 60 s để đo MB/s ở cảnh sa bàn (chạm thiết bị): `.venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 60 --name ld1_thu_ghi --out runs\rig_bench\<ngay> --record runs\rig_recordings\ld1_thu_ghi` (MB/s in ở cuối và nằm trong `recording.mb_per_s` của `.rig.json`) |
| Điều kiện trước | ĐK-BT; máy nghiệm thu đã chọn |
| Ngưỡng | N-C1, N-C2, N-C3, N-C5, N-T3 … N-T6, N-T8 (chỉ báo số); N-C4 khi có LED |
| Trạng thái | CHƯA THỬ ở 30 phút. Phiên dài nhất đã có là 10 phút (u04, s07, t09; máy bàn, [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 3.5) |

## 6. Làm được ngay, khi chưa có xe

| Việc | Kịch bản | Cần gì |
|---|---|---|
| Kiểm tham chiếu trên cao bằng xe giả | TC-1 | Camera trên cao, giá, marker in, thước; công cụ T4 (hoặc làm tay với ảnh) |
| Định vị tĩnh so với thước, cùng buổi bảy lần đặt hộp | DV-1 | LiDAR C1, thước, người thao tác |
| Hướng gốc sau khởi động lại mô-tơ | DV-2 | LiDAR C1, người thao tác |
| Chạy dài 30 phút trên máy bàn, rồi trên laptop | LD-1 | Bốn camera, LiDAR; laptop cần mã và tham chiếu mới sau khi commit/push (TONG_HOP_DU_AN.md mục 5.1). *(Cập nhật 25/09/2026: đã commit và push, `origin/main` = `54cb3e2`; laptop lấy bằng `git pull`, tham chiếu máy bàn mới là [tham_chieu_20260924_toi.json](evidence/may_ban/tham_chieu_20260924_toi.json), commit `bfcbfc2`; [MAY_NOP_DO_AN.md](MAY_NOP_DO_AN.md). Laptop vẫn CHƯA chạy gì ngoài hồ sơ giai đoạn 0)* Tham chiếu hiện dùng là [tham_chieu_20260929.json](evidence/may_ban/tham_chieu_20260929.json): lượt `may_moi` trên máy bàn từ 29/09/2026, người dùng chọn ngày 29/09/2026; tệp 24/09 của máy bàn trước giữ để đối chiếu ([chuyển máy](CHUYEN_MAY_BAN.md) mục 2). |
| Rút cáp LiDAR, đưa vật vào khi xe ảo chạy, vật ngoài đường | CB-3, VC-1, VC-6 (phần BT) | LiDAR C1, người thao tác; sa bàn mặc định của `lidar_app` |
| Vật sau đuôi khi xe ảo đang lùi | VC-2 (phần BT) | LiDAR C1, người thao tác; `--scenario scenarios\sa_ban_3x2_hai_hop.json` (có đoạn lùi); đặt vật trên đoạn lùi đã lập, phía trước–phải LiDAR, không đặt "phía sau LiDAR" (xem VC-2) |
| Vật bên hông vùng thân xe quét qua ở đoạn cong | VC-3 (phần BT) | Như VC-2 (cùng kịch bản, vì sa bàn mặc định là đường thẳng) |
| Rút một camera, rút hub khi bàn thử chạy | CB-1 (phần BT) | Bốn camera, người thao tác |
| Bản mô phỏng của bài đỗ và từ chối | DO-1 … DO-6, DI-1 … DI-4, VC-4 (gần đúng, xem VC-4), VC-5, AT-1, AT-5 (phần MP) | Chỉ phần mềm. Từ commit `10a4735` (25/09/2026) `bench --json` tự tạo thư mục kết quả; trước đó phải tạo `runs\nghiem_thu\mo_phong` trước khi chạy `bench` (mục 2.3) |
| Chạy lại test liên quan (không chạm thiết bị) | DI-4, CB-3, CB-5, CB-6, AT-2, AT-5, NT-5; VC-3 (mô phỏng hành lang, đường thẳng: `tests\test_fusion.py -k off_the_path`) | `.venv\Scripts\python.exe -X utf8 -m pytest tests\test_session_vehicle.py tests\test_lidar_unplug.py tests\test_fusion.py tests\test_bev.py` |

Kết quả phần MP và BT ghi đúng mức của nó (kế hoạch 1.3); không chép sang cột nghiệm thu xe thật.

## 7. Công cụ còn thiếu

Bảng này ghi theo mã đã commit (HEAD 9bcc30c, 24/09/2026). Lúc viết (tối 24/09/2026), cây làm việc có các việc song song
**chưa commit**, tệp này không kiểm, có thể thay đổi vài dòng dưới:

- chọn cổng serial trong giao diện; START với bo thật bị từ chối khi chưa có nguồn tư thế thật (`START_NO_POSE_SOURCE`);
  so giới hạn bo với cấu hình xe (`tests/test_vehicle_board_ui.py`; CHE_DO_QUAN_SAT.md đang được bổ sung);
- cầu nối ToF → `NearFieldReading` với vị trí gá GIẢ ĐỊNH (`configs/tof_mounts_v0.json`, `tests/test_nearfield_tof.py`);
- công cụ ngoại tham và ROI cho camera dự án (`perception/extrinsics_calib.py`, `ui/roi_app.py`);
- odometry LiDAR thử nghiệm offline (`lidar/scan_odometry.py`); phép thử độ nhạy với sa bàn cố định
  (`evaluation/sensitivity.py`); nhãn mới cho bộ ca khó (`evaluation/hard_cases.py`).

Khi các việc đó được commit, cập nhật cột "Ghi chú" và phần "Công cụ, lệnh" của kịch bản liên quan.

*(Cập nhật 25/09/2026: bốn việc trên đã commit và push, `origin/main` = `54cb3e2`: chọn cổng serial, so giới hạn và
ToF → `NearFieldReading` ở `6db5087`; ngoại tham và ROI ở `65b7127`; odometry LiDAR ở `a7cec5e`; độ nhạy và nhãn ca khó
ở `10a4735`. Các dòng T1, T8, T10 dưới đây và CB-4 đã thêm ghi chú. Đọc lại mã ở HEAD `54cb3e2`: T2–T7, T9, T11–T15
vẫn đúng như bảng; T10 phần lớn đã có từ trước khi viết bảng (xem dòng T10); T11 vẫn đúng (`calib_app`, `fisheye_calib` nhận `--port` 1..4); T12–T15 vẫn chưa có trong mã.)*

| Mã | Công cụ | Cần cho | Ghi chú |
|---|---|---|---|
| T1 | Giao diện chọn cổng serial tới bo thật | Mọi kịch bản XT | [CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) mục 6 ở HEAD 9bcc30c: giao diện chưa có lựa chọn này (đang thêm song song, xem trên). *(Cập nhật 25/09/2026: đã có từ `6db5087`: thẻ "Bo điều khiển" chọn cổng COM, nút "Kiểm kết nối bo" chỉ HELLO + đọc telemetry, không ARM. START với cổng thật luôn bị từ chối (`START_NO_POSE_SOURCE`) tới khi có T2, và `begin_run` còn phải thêm bước mở cổng (`reopen()`), CHE_DO_QUAN_SAT.md mục 6, 8. Chỉ kiểm bằng cổng serial giả)* |
| T2 | Định vị LiDAR làm nguồn tư thế của phiên, cùng đồng hồ với `VehicleIO` | Mọi kịch bản XT, CB-6, DV-3 | Hiện phiên dùng `SimTruthPose` (định vị lý tưởng; CHE_DO_QUAN_SAT.md mục 2). Chọn N-T2 cùng lúc |
| T3 | Ghi cảm biến (bốn camera + LiDAR) trong phiên đỗ xe, cùng đồng hồ | GD3, DV-3, phân tích lỗi | Hiện bàn thử (`rig`) và phiên đỗ xe là hai chương trình; hai tiến trình khó mở chung một camera (suy luận, chưa thử) *(25/09/2026, mã ở `b01dea4`: lý do trên đã lỗi thời. `ui.lidar_app --camera-ai` dựng `Rig` bốn camera + AI ngay trong cửa sổ phiên đỗ xe, cùng tiến trình với ngăn LiDAR (`ui/camera_dock.py`; [AI_DIEU_KHIEN_XE.md](AI_DIEU_KHIEN_XE.md)); mới chạy với nguồn giả và bản ghi phát lại, với camera thật CHƯA THỬ. Ngăn AI camera và ngăn LiDAR đều chưa có chức năng ghi phiên, nên T3 vẫn còn)* |
| T4 | Công cụ tham chiếu trên cao (đề xuất có giao diện): hiệu chuẩn camera trên cao, khớp mặt sàn từ mốc, kiểm trên điểm kiểm tra, trích tư thế từ video marker, xuất tệp tư thế | R1, TC-1 | `cv2.aruco` có sẵn trong `.venv` (OpenCV 5.0.0, kiểm bằng import ngày 24/09/2026) |
| T5 | Công cụ chấm một lần chạy: đọc log + tệp tư thế tham chiếu + bố trí tham chiếu, tính các đại lượng N-D, N-P, ghi dòng biên bản | GD6, mọi kịch bản | Tránh chấm tay dễ sai |
| T6 | Tiêm lỗi có kiểm soát: camera đứng hình, nguồn tư thế ngừng, vòng điều khiển treo | CB-2, CB-5 (b), CB-6 | Script treo vòng điều khiển: L7 ở GIAI_DOAN_6_CHUAN_BI.md ghi "script chưa có" |
| T7 | LED do ESP32-S3 bật khi nhận COMMAND/STOP, thấy được trong video | R7 (cách tốt nhất; chỉ có trên xe thật) | [GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md) B6: CHƯA LÀM |
| T8 | Mã đọc encoder, AS5600, ToF, điện áp trong firmware; cầu nối `VehicleTelemetry` → `NearFieldReading` | ĐK-XT, CB-4, AT-4 | TONG_HOP_DU_AN.md mục 4.9, 5.4; cầu nối đang thêm song song (chưa commit). *(Cập nhật 25/09/2026: cầu nối đã commit trong `6db5087`, xem CB-4; mã đọc cảm biến trong firmware vẫn CHƯA CÓ)* |
| T9 | Phát lại lần chạy qua `VehicleIO` | Tái hiện (16.4 ý 10) | `replay_run` từ chối rõ bằng `ReplayNotSupported` (CHE_DO_QUAN_SAT.md mục 5); bằng chứng hiện là log GD2 |
| T10 | Trường "khoảng dài nhất không có khung tốt" của từng camera trong `.rig.json` | N-C2, LD-1 | *(Cập nhật 25/09/2026: phần lớn đã có, và đã có từ trước khi viết bảng này: `.rig.json` có `cameras[i].gap_max_ms`, khoảng dài nhất giữa hai khung tốt liên tiếp của từng camera; khung cắt, xé hay trùng không tính là khung tốt; đặt lại sau phần làm nóng (`reset_counters`); `rig.bench` in dòng "khoảng cách max". Có từ commit `7f93278` (`video/multicam.py`). Còn thiếu: khoảng hở chưa đóng ở cuối phiên (camera ngừng hẳn trước khi phiên kết thúc) không được tính; chưa có test riêng cho trường này. Số đọc lại trên máy bàn: N-C2 ở [NGUONG_NGHIEM_THU_DE_XUAT.md](NGUONG_NGHIEM_THU_DE_XUAT.md) mục 6)* |
| T11 | Mở camera trên cao không theo cổng hub 1–4 trong công cụ hiệu chuẩn | Mục 3.4 | `calib_app` và `fisheye_calib` nhận `--port` là cổng hub 1..4 |
| T12 | Kiểm số lần đổi chiều của đường trước khi cho chạy (từ chối hoặc cảnh báo) | DI-2, N-D6 | Mã hiện chưa có giới hạn (đọc 24/09/2026): `portfolio` chỉ ưu tiên đường ít đổi chiều hơn; giới hạn CHƯA CHỐT |
| T13 | Ghi sự kiện dừng của phiên (`Session.safety_events` và dừng qua `request_stop` của cầu nối hợp nhất: mã, `t_session`, nguồn, thông điệp) vào log `VehicleIO` (dòng mới trong `events.csv`, `handling` = `session_stop`, hoặc tệp `safety_events.csv` cạnh `link.json`) | N-P1, VC-1 … VC-6, CB-2, CB-5, CB-6, AT, mọi ô "lý do dừng ghi trong log" | Đọc mã cây làm việc tối 24/09/2026: `Session._safety_stop` chỉ thêm vào `Session.safety_events`; `VehicleLink.observe` trả STALE_TELEMETRY/NO_MEASURED_STATE/STALE_POSE mà không qua `_log_event`; `export_run` (nơi duy nhất ghi `safety_events.json`) từ chối lần chạy VehicleIO; `RunLog` không có cột sự kiện. Hiện chỉ có văn bản lý do dừng cuối ở `link.json` `result.reason` (không có mã, không có thời điểm phát). Thử trên bo mô phỏng cùng tối (script tạm, không lưu trong repo): chèn vật giả khi đang chạy cho `MAP_CHANGED` ở 0,750 s, dòng STOP đầu của `commands.csv` ở 0,760 s, `VEHICLE_STOPPED` của bo ở 0,78 s; `events.csv` chỉ có `START_CHECK` và `VEHICLE_STOPPED`. Nguồn tư thế ngừng giữa lúc chạy: tương tự, không có dòng `STALE_POSE` |
| T14 | Dấu đồng bộ video–log: nút/phím trên giao diện phiên đỗ xe và bàn thử (`lidar_app`, `rig.bench`), nháy một ô lớn trên màn hình laptop đặt trong khung video R3 và ghi dòng `SYNC_MARK` kèm `perf_counter` (vào `events.csv` hoặc một tệp riêng của công cụ). Dùng được trước START, sau khi dừng, và ở bản BT không có bo | R7, VC-1, VC-2, VC-3, CB-1, CB-3, mọi kịch bản dùng R7 | CHƯA CÓ. Độ trễ hiển thị màn hình CHƯA ĐO, nên sai số R7 lớn hơn ± một khung cho tới khi đo |
| T15 | Nút CLEAR_FAULT trên giao diện (gọi `VehicleIO.clear_fault()`, chỉ khi E-stop đã nhả) | Mục 2.4 bước 1, AT-2 (bước CLEAR_FAULT, ARM, COMMAND), DI-4 (d) | CHƯA CÓ: giao diện không có lời gọi CLEAR_FAULT nào (đọc `ui/` tối 24/09/2026) |

## 8. Còn mở

| Việc | Ai quyết | Ghi chú |
|---|---|---|
| Duyệt bộ kịch bản, số lần lặp, vật thử V1–V6, ba mức ánh sáng | Người dùng + GVHD | Chốt **trước** khi thu kết quả cuối (kế hoạch 14) |
| Chọn camera trên cao và máy ghi nó | Người dùng | Mục 3.2, 3.4 |
| Nơi lưu biên bản (`runs\nghiem_thu\`, `docs\evidence\bien_ban_nghiem_thu_<ngay>.csv`) | Người dùng | Mục 2.3: CSV đặt trong thư mục con của `docs\evidence\` bị git bỏ qua |
| Chính sách sau vật cản thông thường: tự tiếp tục hay chờ xác nhận | Người dùng | Kế hoạch 17.2; VC-5 |
| Mất camera hay ToF có làm xe dừng không | Người dùng | CB-1, CB-4 |
| Hướng giấy phép WoodScape | Người dùng | Nhóm NT; điều kiện V1 thứ ba. *(25/09/2026: đã quyết định dùng mô hình WoodScape trong vòng điều khiển, Valeo chưa xác nhận; vế nháp AI khi gán nhãn chưa quyết, [GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md))* |
| Cách đấu dây ở chế độ quan sát | Người dùng | AT-5; CHE_DO_QUAN_SAT.md mục 8 |
| Số lần E-stop ở M3 | Người dùng + GVHD | AT-2 |
| Máy chạy khi nghiệm thu | Người dùng | LD-1 và mọi ngưỡng thời gian |
