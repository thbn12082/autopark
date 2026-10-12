# Dàn ý khóa luận đề xuất — xe mô hình tự đỗ

> **Ghi công bắt buộc theo giấy phép dữ liệu:** nghiên cứu nhận thức trong dự án này được thực hiện với **Valeo WoodScape
> Dataset** (<https://github.com/valeoai/WoodScape>). Giới hạn sử dụng: [GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md).
> Khóa luận nhắc tới nghiên cứu dùng bộ dữ liệu này thì phải hiển thị rõ dòng ghi công này.
>
> Link GitHub dùng từ 25/09/2026, theo đề xuất ở GIAY_PHEP_DU_LIEU.md mục "Ghi công: link tới trang bộ dữ liệu"; đề xuất
> này chưa chốt. Trước đó link chính là `https://woodscape.valeo.com`. Kiểm ngày 25/09/2026, hai địa chỉ cũ
> `woodscape.valeo.com` và `woodscape.valeo.ai` dẫn tới một trang không có nội dung WoodScape (mục 4).

Tệp này là dàn ý **đề xuất** cho khóa luận về hệ tự đỗ trên xe mô hình 1/12 của dự án AutoPark. Với từng chương và từng
mục, nó cho biết viết được gì, dựa trên tài liệu nào, ở mức bằng chứng nào, có hình/bảng nào và còn thiếu gì. Đây không
phải bản thảo khóa luận và không thêm số đo hay kết quả mới: mọi con số chép từ một biên bản hoặc tệp đo được nêu kèm;
chỗ chưa có bằng chứng ghi "chưa có", "chưa đo" hoặc "chưa chốt". Tài liệu dành cho người viết khóa luận, giáo viên hướng
dẫn (GVHD) và người duyệt; tiến độ chung của dự án ở [TONG_HOP_DU_AN.md](../../TONG_HOP_DU_AN.md).

## Tóm tắt

Trạng thái trong dàn ý tính tới 30/09/2026; vài mục có ghi thêm việc phần mềm ngày 02/10/2026. Những gì làm sau đó, kể cả
các lượt chạy thiết bị trên máy bàn ngày 02/10/2026, chưa được đưa vào dàn ý; trạng thái mới nhất của dự án (06/10/2026) ở
[TONG_HOP_DU_AN.md](../../TONG_HOP_DU_AN.md).

- **V1 chưa đạt điều kiện nào (0/10), chưa cổng nào từ 1 đến 10 đạt, chưa có kết quả trên xe thật.** V1 là bản đầu cần
  đạt, với 10 điều kiện ở kế hoạch mục 16.4. Chưa nhận MN300, ESP32-S3 và phần nguồn/dừng (mục 1).
- **Mô phỏng (MP):** tự đỗ trong mô phỏng giai đoạn 0 (20/09); `VehicleIO` nối vào phiên đỗ xe và chế độ quan sát với bo
  mô phỏng; lõi C++ firmware qua test host (29/09) và bản build firmware chạy trong bo ảo QEMU (30/09). Firmware chưa nạp
  vào bo thật.
- **Bàn thử trên máy bàn (BT):** LiDAR C1, bốn camera USB qua hub, bàn thử bốn camera + LiDAR + AI, ghi và phát lại một
  phiên thật. Qua hub này, bốn camera chỉ dùng được ở 640×480.
- **Dữ liệu công khai (DL):** AI phân đoạn FREE/BLOCKED đã chấm trên WoodScape, ACDC, RoadObstacle21 và RoadAnomaly21,
  nhưng chưa chấm trên ảnh sa bàn có nhãn.
- **Chỉ kiểm bằng ảnh tổng hợp hoặc thiết bị giả (TH):** hiệu chuẩn camera, ngoại tham và vùng quan tâm (ROI), bản đồ
  chiếm chỗ nhìn từ trên xuống (BEV), AI camera làm nguồn vật cản. Chưa camera nào được hiệu chuẩn.
- **Laptop trình diễn RTX 3050 Ti** mới chạy mô phỏng giai đoạn 0; mọi số hiệu năng thiết bị và AI là của máy bàn.
- **Giấy phép WoodScape:** ngày 25/09/2026 người làm khóa luận đã chọn cách đọc điều khoản (cách đọc A) để dùng mô hình
  trong vòng điều khiển; Valeo chưa xác nhận (mục 1, ý 4).
- **Còn chặn việc viết:** mẫu trình bày của trường; ngưỡng và kịch bản nghiệm thu (mới là đề xuất); hiệu chuẩn camera;
  ảnh sa bàn có nhãn; đo trên laptop; xe và phần cứng giai đoạn 4–9; sao lưu `autopark/runs/`. Thứ tự việc ở mục 7.

## Cách dùng dàn ý

**Khung chương.** Cấu trúc dưới đây theo khung thường gặp của khóa luận kỹ thuật ở Việt Nam: Mở đầu; Tổng quan; Cơ sở lý
thuyết; Thiết kế và xây dựng hệ thống; Thực nghiệm và đánh giá; Kết luận và hướng phát triển; Tài liệu tham khảo; Phụ lục.
Tên trường/khoa, số chương, thứ tự mục, định dạng trang, kiểu trích dẫn (IEEE, APA…) và số trang tối đa đều **chưa
biết**. Khi có mẫu của trường thì theo mẫu đó, rồi chuyển nội dung ở đây vào đúng chỗ.

**Các phần của tệp.** Phần 0 định nghĩa nhãn mức bằng chứng. Mục 1 gom những điều phải có trong khóa luận dù kết quả cuối
ra sao. Mục 2 là bố cục và mức sẵn sàng của từng chương. Mục 3 đi chi tiết từng chương. Mục 4 liệt kê hình và bảng có sẵn,
mục 5 là tài liệu tham khảo, mục 6 là những câu dễ viết sai, mục 7 là việc cần làm trước khi viết. Mục 8 là biên bản các
đợt việc phần mềm làm song song với dàn ý.

**Cách đọc mỗi mục ở phần 3:** *Viết được* (nội dung đã có cơ sở) · *Nguồn* (tài liệu, mục) · *Mức* (mức bằng chứng, phần
0) · *Hình/bảng* (có sẵn ở đâu) · *Còn thiếu* (trước khi viết được) · *Giới hạn phải nói* (câu bắt buộc có trong khóa luận).

**Nguồn.** Bản đầu (24/09/2026, repo ở commit `2bd37b6`) dựng từ [TONG_HOP_DU_AN.md](../../TONG_HOP_DU_AN.md) và mọi tài
liệu nó dẫn ở mục 6 (trừ README của Valeo, là tài liệu bên thứ ba), [kế hoạch v3.1](../../KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md),
[HUAN_LUYEN.md](../../HUAN_LUYEN.md), [BAO_CAO_GIAI_DOAN_0.md](../../BAO_CAO_GIAI_DOAN_0.md),
[MAY_NOP_DO_AN.md](MAY_NOP_DO_AN.md), các tệp trong [evidence/](evidence/), và docstring của vài mô-đun mã khi tài liệu
không nói tới (ghi rõ ở chỗ dùng). Bản đầu cũng đối chiếu với tệp gốc: `datasets/woodscape_metadata/LICENSE.pdf` và
`README.md`, `datasets/drow/README_source.md`, các JUnit trong `evidence/`, JSON thô trong `runs/rig_bench/` và
`runs/may_moi_20260924_may_ban/`, `metrics.json` của ba seed, `runs/robustness_final_2026-09-20/cases.jsonl`, và dựng lại
ba ảnh DROW. Các lần cập nhật sau đọc thêm biên bản của từng đợt việc (mục 8), [CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) và
[MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md).

**Ghi commit cạnh số.** Mọi việc nói trong dàn ý đã commit và push. Chữ "chưa commit" trong các biên bản là trạng thái lúc
viết đoạn đó. Khi đưa một con số vào khóa luận, ghi kèm commit chứa việc đó:

- Đợt tối 24/09 (bảy việc ở mục 8), commit lúc 20:22 ngày 24/09: `bfcbfc2` (bàn thử, tham chiếu 19:08), `1d2b857` (BEV),
  `b100a5d` (LiDAR, ảnh định vị), `c43e8d3` (xe, chế độ quan sát, bản sửa khoảng trống an toàn), `9bcc30c` (tài liệu).
- Đợt khuya 24/09 (mười một việc ở mục 8), commit lúc 00:54 ngày 25/09:
  - `65b7127`: ngoại tham và ROI, BEV tăng tốc, chặn dữ liệu tổng hợp;
  - `10a4735`: nhãn 16 ca khó và đường chứng, độ nhạy theo kích thước xe, `--vehicle-config`;
  - `a7cec5e`: odometry khớp scan, so sánh phương án định vị, độ lặp lại LiDAR, bản nhỏ k01, demo hợp nhất bỏ ≥ 22 vòng;
  - `6db5087`: thẻ "Bo điều khiển", so giới hạn bo, ToF → `NearFieldReading`;
  - `77eb51f`: RoadAnomaly21, `evaluate.py --train-overlap`, `labels import --exclude`, `may_moi` tóm tắt lại;
  - `54cb3e2`: kịch bản và ngưỡng nghiệm thu nháp, đồng bộ tài liệu.
- Rà tài liệu lúc 02:54 ngày 25/09: `89cd58f`.
- Đợt AI camera 25/09: `b01dea4` (mã), `99e9a9e` (giấy phép), `9d68257` (tài liệu).
- Viết lại tài liệu 26/09: `668bf5e`, `2ee2940`.
- Chuyển máy bàn 29/09: `76bee39`, `38f64bb`, `b37e9ee`. Bo ảo QEMU 30/09: `13b3871`, `cbb218a`, `ebbec83`, `ff4a018`. Hai
  đợt này ghi ở [CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md).
- Các việc ngày 02/10/2026 được nhắc trong dàn ý (công cụ nghiệm thu T4, T9, T13, T15; nguồn tư thế LiDAR): commit ghi ở
  [TONG_HOP_DU_AN.md](../../TONG_HOP_DU_AN.md).

---

## 0. Ký hiệu mức bằng chứng

Kế hoạch (mục 1.3) tách ba mức: mô phỏng, bàn thử, xe thật. Kết quả ở mức dưới không thay được mức trên. Dàn ý dùng thêm
ba nhãn (DL, TH, TK) để tách những thứ kế hoạch không gọi tên riêng. Bảng dưới tóm tắt; chi tiết những gì đã có ở từng mức
nằm ngay sau bảng.

| Nhãn | Nghĩa | Đã có (tới 30/09/2026) |
|---|---|---|
| **MP** | Mô phỏng phần mềm, thông số xe giả định | Mô phỏng giai đoạn 0; `VehicleIO` với bo mô phỏng; lõi C++ firmware qua test host; firmware trong bo ảo QEMU |
| **DL** | Chạy offline trên dữ liệu công khai lưu sẵn (WoodScape, ACDC, RoadObstacle21, AVM-SS, DROW v2) | Huấn luyện và chấm AI; BEV minh họa trên ảnh WoodScape; chấm RoadAnomaly21; odometry khớp scan trên DROW v2 |
| **BT** | Thiết bị thật nằm trên bàn, chưa gá, đo trên **máy bàn** i9-14900 + RTX 4000 Ada | LiDAR C1, bốn camera USB, bàn thử bốn camera + LiDAR + AI, ghi/phát lại một phiên thật; xử lý offline trên bản ghi |
| **TH** | Chỉ kiểm bằng ảnh tổng hợp hoặc thiết bị giả trong test | Hiệu chuẩn, ngoại tham và ROI, gán nhãn, BEV trên rig tổng hợp, AI camera làm nguồn vật cản, cầu nối ToF |
| **TK** | Chỉ có thiết kế/đặc tả hoặc mã chưa chạy | Lớp dán Arduino trên chip, ngõ vào E-stop, bản nháp giai đoạn 4 và 6, kịch bản và ngưỡng nghiệm thu đề xuất |
| **XT** | Xe thật | **Chưa có.** Chưa nhận MN300, ESP32-S3, phần nguồn/dừng |

**MP — mô phỏng.**
- Giai đoạn 0 đạt sáu điều kiện ở mức mô phỏng (20/09, laptop i7-12700H).
- `VehicleIO` mô phỏng (24/09). Tối 24/09, `VehicleIO` được nối vào phiên đỗ xe và chế độ quan sát, chỉ với bo mô phỏng
  hoặc cổng serial giả và tư thế lý tưởng ([CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md)). Khoảng trống an toàn khi có
  `Heartbeat` được tìm thấy và sửa cùng tối, cũng chỉ ở mức MP (3.12b).
- Khuya 24/09: phép thử độ nhạy theo kích thước xe với sa bàn cố định (hai lượt, dưới tải); kiểm lại nhãn 16 ca khó bằng
  đường chứng (`10a4735`); thẻ "Bo điều khiển" và so giới hạn bo, với bo mô phỏng và cổng serial giả (`6db5087`).
- 29–30/09: lõi C++ firmware qua test host (29/09); bản build thật chạy trong bo ảo QEMU với `SerialVehicleIO` (30/09;
  [MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md)).

**DL — dữ liệu công khai.**
- AI huấn luyện và chấm trên máy bàn (21–23/09).
- Tối 24/09: BEV minh họa trên ảnh WoodScape `00000_FV`, thêm một lần với ba ảnh khác thời điểm. Không có nhãn mặt sàn để
  chấm ([BEV.md](BEV.md) mục 6).
- Khuya 24/09: chấm RoadAnomaly21 (10 ảnh có nhãn, ba seed; `77eb51f`); odometry khớp scan trên DROW v2, so với `.odom2`,
  không phải ground truth (`a7cec5e`).
- Khuya 24/09: phần so manifest của `evaluate.py --train-overlap` chạy trên WoodScape val (0 trùng với 5.764 ảnh train) và
  AVM-SS val của `ai_ws_avm` (1.050/1.050 ảnh thuộc split chọn checkpoint; `77eb51f`). Nguồn:
  [HUAN_LUYEN.md](../../HUAN_LUYEN.md) cuối mục 8.

**BT — bàn thử.**
- LiDAR C1 (22–24/09), bốn camera USB (23–24/09), bàn thử bốn camera + LiDAR + AI (23–24/09).
- Tối 24/09: đo lại quy tắc ghép theo nhịp riêng và làm nóng AI (o01, o02, o07); ghi và phát lại một phiên thật
  (o03–o06). Định vị LiDAR chạy **offline** trên bản ghi BT có sẵn, chỉ cho độ nhất quán.
- Khuya 24/09 và 25/09 **không có phiên đo mới**. Chỉ chạy offline trên bản ghi BT có sẵn: độ lặp lại khoảng cách LiDAR
  (`lidar/repeatability.py`), odometry khớp scan trên sáu bản ghi C1 **đứng yên**, và phát lại bản ghi o03 qua ngăn AI
  camera với mô hình thật. Với rig thật, mọi lô AI bị chặn vì chưa hiệu chuẩn nên có 0 vật cản
  ([AI_DIEU_KHIEN_XE.md](AI_DIEU_KHIEN_XE.md) mục 8.2).
- 29/09: kiểm lại trên máy bàn hiện tại (cùng cấu hình) bằng `do_may_moi.cmd` và các lệnh README (mục 4;
  [CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 2).

**TH — ảnh tổng hợp hoặc thiết bị giả.**
- 24/09: công cụ hiệu chuẩn camera, công cụ gán nhãn.
- Tối 24/09: BEV trên rig bốn camera tổng hợp; định vị LiDAR trên phòng tổng hợp; ghi/phát lại với nguồn giả; nhánh "camera
  lỡ nhịp" của quy tắc ghép (đồng hồ giả).
- Khuya 24/09: công cụ ngoại tham và ROI (ảnh tổng hợp, camera giả); BEV tăng tốc (rig tổng hợp); cầu nối ToF →
  `NearFieldReading`; "Kiểm kết nối bo" (cổng serial giả); demo hợp nhất bỏ ≥ 22 vòng (nguồn giả); `may_moi` tóm tắt lại
  (bản sao kết quả máy bàn).
- Khuya 24/09: chốt chấm ảnh đã học và `labels import --exclude`, kiểm trên dữ liệu giả. Riêng phần so manifest của chốt
  chấm ảnh đã học đã chạy trên dữ liệu thật nên thuộc DL (xem trên).
- 25/09, đợt AI camera: AI camera làm nguồn vật cản trong phiên đỗ xe (camera giả, rig bốn camera tổng hợp, tệp hiệu chuẩn
  viết tay; 68 mục test).

**TK — thiết kế, đặc tả hoặc mã chưa chạy.**
- Lớp dán Arduino của firmware ESP32-S3 trên chip: LEDC, E-stop, watchdog kích hoạt, USB-CDC. Firmware biên dịch được từ
  29/09/2026 nhưng chưa nạp bo; lõi C++ và bản build trong bo ảo QEMU thuộc MP. Ngõ vào E-stop chưa lắp.
- Tối 24/09: bản nháp đo MN300 (giai đoạn 4), phiếu kiểm kê MN300, bảng tải, sơ đồ nguồn/dừng và 16 kịch bản thử lỗi
  (giai đoạn 6). Mọi số chưa đo, mọi phép thử chưa thử.
- Khuya 24/09: bộ kịch bản nghiệm thu và ngưỡng đề xuất; so sánh phương án định vị và đề xuất. Các ngưỡng vẫn chưa chốt;
  phương án định vị được người dùng đồng ý ngày 02/10/2026 (1.6).

Laptop RTX 3050 Ti là máy mang đi nộp và trình diễn (người dùng xác nhận 24/09). Trên laptop mới chỉ có số của giai đoạn 0
(MP, 20/09). Mọi số của mức BT và DL là số của máy bàn.

## 1. Tình trạng chung ảnh hưởng mọi chương

Những điều sau phải có mặt trong khóa luận, ở chương thực nghiệm và chương kết luận, dù kết quả cuối ra sao:

1. **Điều kiện hoàn thành V1: 0/10 đạt; chưa cổng nào từ 1 đến 10 đạt** (kế hoạch 16.4 và 17.4, cập nhật 24/09). Đợt rà
   soát kế hoạch ngày 24/09 đếm 275 việc: 56 xong, 92 một phần, 27 chưa bắt đầu, 100 chờ thiết bị chưa mua. Đó là số việc,
   không phải tỉ lệ hoàn thành. Nguồn:
   [kiem_toan_ke_hoach_20260924.json](evidence/ke_hoach/kiem_toan_ke_hoach_20260924.json).
2. **Chưa có kết quả trên xe thật.** Mọi kết luận về tự đỗ, dừng, E-stop, quãng dừng hiện chỉ ở mức MP.
3. **AI chưa từng được chấm trên ảnh sa bàn có nhãn.** Các số mIoU là của ảnh đường phố trong bộ dữ liệu công khai
   ([HUAN_LUYEN.md](../../HUAN_LUYEN.md)). Trên camera thật, lớp tô AI của bàn thử chỉ để nhìn và đo thời gian. Từ đợt AI
   camera ngày 25/09/2026 đã có phần mềm đưa AI vào phiên đỗ xe làm nguồn vật cản (3.11b). Nhưng chưa camera nào được hiệu
   chuẩn, nên trên bàn thật AI chưa tạo vật cản nào, và tỉ lệ báo giả của nguồn vật cản này trên sa bàn chưa đo.
4. **Giấy phép WoodScape.** Điều khoản WoodScape chỉ cho dùng phi thương mại (nghiên cứu, giảng dạy, benchmark, thử nghiệm
   cá nhân). Cùng câu cấm dùng thương mại có vế không cho dùng bộ dữ liệu hay mô hình huấn luyện trên nó trong vận hành
   phương tiện. Diễn biến và hiện trạng:
   - Ngày 22/09 người làm khóa luận chọn cách hiểu: xe 1/12 trên sa bàn thuộc "personal experimentation" và "academic
     research".
   - Ngày 25/09/2026 hướng xử lý cho việc nối AI đã chốt: người làm khóa luận dùng mô hình trong vòng điều khiển xe mô hình
     và đọc vế "in operation of a vehicle" là ví dụ của việc dùng thương mại (cách đọc A).
   - **Valeo chưa xác nhận cách đọc nào.** Cách đọc B (lệnh cấm riêng, bất kể thương mại) không loại trừ được, và hội đồng
     có thể nghiêng về B. Khóa luận phải nêu cả hai cách đọc và nói rõ chưa được xác nhận.
   - Đề xuất, chưa chốt: nên có kết quả dự phòng khi tắt AI camera (chỉ LiDAR). Đoạn đề xuất cho khóa luận và phương án dự
     phòng ở GIAY_PHEP_DU_LIEU.md mục "Khóa luận nên viết gì".
   - Quyết định không phủ checkpoint có AVM-SS và chưa nói về nhãn nháp AI khi gán nhãn sa bàn. Nên báo GVHD trước khi viết
     (mục 7, việc 2).

   Nguồn: [GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md); TONG_HOP mục 5.1.
5. **Khung MJPEG bị cắt** khi ba–bốn camera chạy chung qua hub UGREEN (nhánh USB 2.0) ở 720p/1080p. Với bốn camera, hai–ba
   camera mất phần lớn khung. Với ba camera ở 720p, một camera bị như vậy (r03, r05). Ba camera ở 1080p chưa có phiên nào
   đếm khung bị cắt. Ở 640×480 vẫn có đợt hỏng ở cổng 1 (23/09). Cấu hình dùng được hiện là 640×480 kèm bộ dò khung hỏng,
   và bộ dò có điểm mù đã biết ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 2.3–2.4). Các phiên 720p ngày 24/09
   (w03, w04, o01) không có khung bị cắt vì camera nhìn chỗ tối; đó **không** phải bằng chứng 720p dùng được.
6. **Mọi số hiệu năng thiết bị và AI là của máy bàn.** Số tới 25/09/2026 đo trên máy bàn trước. Số kiểm ngày 29/09/2026
   đo trên máy bàn hiện tại, cùng cấu hình ([CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 2). Laptop RTX 3050 Ti (4 GB VRAM,
   bộ điều khiển USB khác) chưa đo LiDAR, camera, AI. Quy trình đo đã sẵn ([MAY_NOP_DO_AN.md](MAY_NOP_DO_AN.md)) nhưng
   chưa chạy trên laptop. Tệp tham chiếu máy bàn để so đã đo lại hai lần: lúc 19:08 ngày 24/09 bằng mã mới, và ngày 29/09
   trên máy bàn hiện tại (4.10, mục 4).
7. **Ngưỡng nghiệm thu (kế hoạch 16.2) và bộ kịch bản (16.3) chưa chốt.** Vì vậy chương thực nghiệm chưa thể viết
   "đạt/không đạt" cho chỉ tiêu nào; chỉ báo được số đo kèm điều kiện đo. Từ khuya 24/09/2026 đã có bản đề xuất để duyệt:
   [NGUONG_NGHIEM_THU_DE_XUAT.md](NGUONG_NGHIEM_THU_DE_XUAT.md) (mã N-…) và [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md)
   (37 kịch bản, phương pháp đo độc lập R1–R7). Hai tệp này ở mức TK. Ngày 02/10/2026 người dùng đồng ý làm theo một số đề
   xuất, gồm phương án định vị (1.6) và giới hạn số lần đổi chiều theo từng kịch bản (N-D6 (b)). Các ngưỡng vẫn là đề
   xuất, chưa chốt cho tới khi người dùng và GVHD duyệt; không trích số N-… như ngưỡng đã chốt.
8. **Nhiều bằng chứng nằm trong `autopark/runs/` (git-ignore)**, chỉ có trên máy bàn, và chưa có bản sao lưu nào được ghi
   nhận (mục 7, việc 3; ý gốc ở TONG_HOP_DU_AN.md mục 5.1 bản `9d68257`). Hình và bảng lấy từ đó phải sao lưu trước khi
   viết.
9. **Số của giai đoạn 0 (20/09) đo trên bản mã cũ.** Từ đó mã đã thêm nhiều khối. Muốn dẫn số test, số ca, coverage trong
   khóa luận thì phải chạy lại trên bản mã cuối và ghi ngày, máy, commit. Các lượt chạy toàn bộ bộ test đã có:
   - 25/09, máy bàn trước, trên mã sau đó được commit thành `65b7127` … `54cb3e2`: `.venv` 1242 đạt, 7 bỏ qua;
     `.venv-train` 386 đạt. Số 386 là nhóm chọn của `.venv-train`, không phải toàn bộ (TONG_HOP_DU_AN.md mục 7).
   - 25/09 cuối đợt AI camera (máy bàn trước) và 29/09 ở `9d68257` (máy bàn hiện tại): cùng cho `.venv` 1.315 đạt, 7 bỏ
     qua; `.venv-train` 1.376 đạt.
   - Mới nhất trong dàn ý: 30/09 trên `ebbec83`, máy bàn Dell Precision 3680: `.venv` 1.380 đạt, 8 bỏ qua; `.venv-train`
     1.442 đạt; 0 hỏng ([CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 8). Các lượt sau đó ở TONG_HOP_DU_AN.md mục 7.

   Chiến dịch 2.880 ca và coverage chưa chạy lại; trước khi nộp phải chạy lại trên bản mã nộp.
10. **Công cụ AI trong quá trình làm.** Các biên bản ghi nhiều vòng rà soát "bằng agent". Ví dụ: HUAN_LUYEN mục 13 và đầu
    TONG_HOP ở bản `9d68257`; GIAI_DOAN_2_BAN_THU mục 8; đầu tệp [MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md) (khảo sát
    bằng 13 tác tử ngày 29/09/2026 và các lượt review bằng tác tử ngày 30/09/2026). Quy định của trường về khai báo dùng
    công cụ AI: **cần tra**. Lời cam đoan và phần phương pháp phải khớp quy định đó.
11. **Số lấy từ các đợt việc sau bản đầu phải ghi kèm commit.** Mọi đợt việc nói trong dàn ý đã commit và push; danh sách
    commit ở phần "Cách dùng dàn ý" đầu tệp. Bằng chứng nhỏ của các đợt này nằm trong `docs/evidence/`, tệp gốc vẫn ở
    `runs/` (git-ignore):
    - bản rút gọn số đo tối 24/09:
      [cho_nhip_rieng_ghi_phat_lai_20260924.json](evidence/rig/cho_nhip_rieng_ghi_phat_lai_20260924.json) (`bfcbfc2`);
    - kết quả định vị chạy lại offline bằng mã đã sửa màu overlay: bốn ảnh overlay và tệp tóm tắt
      [dinh_vi_tren_p07_20260924.json](evidence/lidar/dinh_vi_tren_p07_20260924.json), gồm lệnh, tham số, hash
      `localize.py` và kết quả từng lần chạy (`b100a5d`). Nguồn đúng là [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 8
      và [DINH_VI_LIDAR.md](DINH_VI_LIDAR.md) mục 5. `localize.json` và `track.csv` từng vòng không được chép, chỉ ở thư
      mục tạm;
    - tệp tham chiếu máy bàn [tham_chieu_20260924_toi.json](evidence/may_ban/tham_chieu_20260924_toi.json) (`bfcbfc2`);
    - `docs/evidence/hard_cases/` (`10a4735`); `docs/evidence/lidar/` gồm `do_lap_lai_*`, `k01_kiem_suc_khoe.*`,
      `odometry_khop_scan_*` (`a7cec5e`).

## 2. Bố cục đề xuất và mức sẵn sàng

| Phần | Nội dung chính | Mức sẵn sàng | Cái đang chặn |
|---|---|---|---|
| Phần đầu | Lời cam đoan, lời cảm ơn, tóm tắt (Việt/Anh), mục lục, danh mục hình, bảng, chữ viết tắt | Theo mẫu trường | Mẫu trường; quy định khai báo AI (mục 1, ý 10) |
| Mở đầu | Lý do, mục tiêu V1, phạm vi, phương pháp, đóng góp, bố cục | **Viết được phần lớn** | Tên đề tài chính thức; trích dẫn cho phần bối cảnh |
| Chương 1. Tổng quan | Bài toán tự đỗ, cảm biến, dữ liệu, lập đường, định vị, an toàn | **Một phần** (khảo sát dữ liệu có sẵn) | Tổng quan tài liệu gần như chưa có trong repo; tài liệu gốc cho định vị (dưới bảng) |
| Chương 2. Cơ sở lý thuyết | Hệ tọa độ, động học, Reeds–Shepp/Hybrid A*, bám quỹ đạo, fisheye, phân đoạn, lưới chiếm chỗ, hợp nhất, giao thức, PI | **Viết được phần lớn** từ mã và tài liệu | Trích dẫn nguồn gốc (mục 5 "cần tra"); lý thuyết định vị |
| Chương 3. Thiết kế và xây dựng | Kiến trúc, phần cứng, phần mềm từng khối, an toàn | **Phần mềm viết được; phần cứng xe chưa** | MN300, ESP32-S3, nguồn, gá (giai đoạn 4–7) |
| Chương 4. Thực nghiệm và đánh giá | MP, DL, BT; laptop; xe thật; đối chiếu V1 | **Một phần** (MP, DL, BT trên máy bàn) | Laptop, sa bàn có nhãn, sai số LiDAR, tham chiếu độc lập cho định vị, hiệu chuẩn camera, xe thật, ngưỡng 16.2 |
| Chương 5. Kết luận | Kết luận, hạn chế, hướng phát triển | **Chỉ có khung** | Phụ thuộc chương 4 |
| Tài liệu tham khảo | Dữ liệu, thuật toán, thiết bị, phần mềm | **Một phần** (mục 5) | Nhiều mục "cần tra" |
| Phụ lục | Hướng dẫn vận hành, giao thức, bảng số chi tiết, biên bản, giấy phép, BOM thực mua, video | **Có sẵn một phần** | Chọn lọc theo giới hạn trang; BOM thực mua; hướng dẫn lắp/dừng và video trên xe |

Ghi chú cho bảng:

- **Chương 1:** phương án SLAM chưa chọn. Định vị trên bản đồ tĩnh có công cụ từ tối 24/09 nhưng chưa có tài liệu gốc để
  trích. Từ khuya 24/09 có bản so sánh bốn phương án và đề xuất; ngày 02/10/2026 người dùng đồng ý làm theo đề xuất (1.6).
  Yêu cầu của các thư viện SLAM ngoài đều "cần tra".
- **Chương 3:** bản nháp đo xe và nguồn/dừng (tối 24/09) mới ở mức TK.
- **Chương 4:** tối 24/09 có thêm đo lại quy tắc ghép, ghi/phát lại, định vị offline, BEV tổng hợp. Hiệu chuẩn, ngoại tham
  và ROI là cái chặn BEV trên camera dự án; công cụ ngoại tham/ROI có từ khuya 24/09 nhưng chỉ ở mức TH. Ngưỡng 16.2 và
  kịch bản 16.3 có bản đề xuất, chưa duyệt.
- **Phụ lục:** đã có hướng dẫn cài đặt và chạy, giao thức, bảng số, biên bản, giấy phép. BOM thực mua chưa có giá/hóa
  đơn. Hướng dẫn lắp/dừng và video trên xe chờ giai đoạn 4–9.

---

## 3. Chi tiết từng phần

### Mở đầu

**M.1. Lý do chọn đề tài / đặt vấn đề**
- *Viết được:* hệ tự đỗ trên xe mô hình 1/12, laptop làm bộ xử lý chính, LiDAR 2D cho bản đồ/định vị, bốn camera USB cho
  nhận thức cục bộ, một ESP32-S3 điều khiển cấp thấp; hướng làm "phần mềm và nhận thức trước, tích hợp xe thật sau".
- *Nguồn:* kế hoạch mục 1.1, 2.1–2.2 và phần kết luận kế hoạch; [README gốc](../../README.md).
- *Còn thiếu:* dẫn chứng bối cảnh (hệ đỗ xe tự động trên ô tô, xe mô hình trong đào tạo/nghiên cứu). Repo không có tài
  liệu tổng quan nào: **cần tra**.

**M.2. Mục tiêu**
- *Viết được:* V1 theo kế hoạch mục 1.2: người dùng đặt đích trên giao diện; xe tìm và chạy quỹ đạo tiến/lùi hợp cơ cấu
  lái; LiDAR cho bản đồ và định vị; bốn camera cho nhận thức cục bộ; có vật cản hoặc dữ liệu cần thiết không còn hợp lệ
  thì dừng và đánh giá lại. Tiêu chí hoàn thành là 10 điều kiện ở mục 16.4.
- *Giới hạn phải nói:* mục tiêu là V1 của kế hoạch, không phải kết quả; nêu rõ mức đạt tới lúc nộp (hiện 0/10).

**M.3. Đối tượng và phạm vi**
- *Viết được:* cấu hình giữ nguyên (MN300 Tank300 1/12, laptop, RPLIDAR C1, bốn camera USB, ESP32-S3; kế hoạch 1.1); những
  thứ **không** bắt buộc trong V1 (nhận diện vạch đỗ, tự tìm ô, tự lái tới bãi, end-to-end, MPC nâng cao, dự đoán chuyển
  động người, tái dựng 3D); những cấu hình cũ không đưa trở lại (HSP, camera Wi-Fi, bốn ESP32-CAM, máy tính trên xe).
- *Còn thiếu:* GVHD duyệt phạm vi tối thiểu để bảo vệ (có bắt buộc chạy xe thật không).

**M.4. Phương pháp thực hiện**
- *Viết được:* 11 giai đoạn, 6 đợt mua. Mỗi giai đoạn có năm phần: đồ cần có, việc khi chưa có đồ, việc khi có đồ, đầu ra,
  điều kiện chuyển bước (kế hoạch 2.3). Ba mức bằng chứng (1.3); trạng thái `CHƯA LÀM / ĐANG LÀM / CHƯA ĐẠT / ĐẠT`; kiểm
  thử tự động, chiến dịch theo seed, replay, đo có hồ sơ; ghi đính chính có ngày thay vì viết lại lịch sử. Từ tối
  24/09/2026 có thêm ghi và phát lại phiên bàn thử để so thuật toán trên cùng dữ liệu thật (4.1).
- *Kiểm đột biến:* làm trên bản sao mã, có biên bản cho:
  - giao thức/firmware ([GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 11);
  - các khối mới tối 24/09: BEV, ghi/phát lại, định vị LiDAR, phiên `VehicleIO` (4.1, 3.14), quy tắc ghép theo nhịp riêng
    (GIAI_DOAN_2_BAN_THU mục 10.2);
  - các khối mới khuya 24/09 (3.14), trong đó có riêng phần `labels import --exclude` của công cụ gán nhãn (16 đột biến,
    [GAN_NHAN_SA_BAN.md](GAN_NHAN_SA_BAN.md) mục 10) và phần bỏ vòng khởi động của demo hợp nhất (6 + 6,
    [GIAI_DOAN_3_CHUAN_BI.md](GIAI_DOAN_3_CHUAN_BI.md) mục 2).

  Chưa có biên bản kiểm đột biến cho: mô phỏng giai đoạn 0, công cụ hiệu chuẩn nội tham, phần còn lại của công cụ gán nhãn
  và của hợp nhất bản đồ, bản sửa làm nóng AI (`AIWorker.warm_up`). Vì vậy không được viết là "kiểm đột biến mọi khối".
- *Hình:* sơ đồ luồng hệ thống và sơ đồ ba nhánh song song (kế hoạch 2.1, 2.2, hiện là khối chữ): **cần vẽ lại**.

**M.5. Đóng góp (chỉ ghi cái đã có bằng chứng, kèm mức)**
1. Phần mềm mô phỏng tự đỗ có đặt/xoay đích, lập đường tiến/lùi xét toàn thân xe, dừng khi bản đồ/phản hồi không hợp lệ,
   log và replay khớp — MP ([GIAI_DOAN_0.md](GIAI_DOAN_0.md)).
2. Baseline phân đoạn FREE/BLOCKED và đánh giá ngoài miền có tách lỗi nguy hiểm "vật cản → FREE", ngưỡng thiên về an toàn,
   kiểm ba seed — DL ([HUAN_LUYEN.md](../../HUAN_LUYEN.md)).
3. Driver và công cụ đo RPLIDAR C1, ghi/phát lại phiên, bản đồ lưới tĩnh — BT ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md)).
4. Bàn thử bốn camera + LiDAR + AI có đo đồng bộ; phát hiện, đo và lọc khung MJPEG bị cắt khi ba–bốn camera chạy chung
   qua hub — BT ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md)). Tối 24/09/2026 có thêm hai kết quả (GIAI_DOAN_2_BAN_THU
   mục 10.1–10.3):
   - quy tắc ghép bộ ảnh không chờ camera lỡ nhịp, xét theo nhịp riêng của từng camera. Đo lại trên phần cứng ở hai cấu
     hình mà quy tắc trước bỏ camera khỏe: 263/855 và 3/2861 bộ → 0/715 và 0/2862. Mức BT cho trường hợp bốn camera khỏe;
     nhánh camera lỡ nhịp chỉ TH;
   - lô AI đầu tiên của **mỗi** cỡ lô tốn 1,2–1,7 s trên GPU máy bàn, nên phải làm nóng mọi cỡ lô trước khi chạy — BT.
5. Hợp nhất nhiều lớp bản đồ có tuổi dữ liệu, cầu nối vật cản vào phiên, chạy với LiDAR thật đứng yên — MP + BT
   ([GIAI_DOAN_3_CHUAN_BI.md](GIAI_DOAN_3_CHUAN_BI.md)).
6. Giao thức laptop–ESP32-S3 có thời hạn lệnh, watchdog, chốt mất liên lạc; `VehicleIO` mô phỏng/serial đi qua cùng byte
   ([GIAO_THUC_XE.md](GIAO_THUC_XE.md)). Bản tham chiếu firmware — MP. Lõi C++ firmware (test host) và bản build trong bo
   ảo QEMU — MP (30/09/2026). Lớp dán Arduino trên chip — TK.
7. Công cụ hiệu chuẩn camera fisheye và công cụ gán nhãn ảnh sa bàn — TH ([HIEU_CHUAN_CAMERA.md](HIEU_CHUAN_CAMERA.md),
   [GAN_NHAN_SA_BAN.md](GAN_NHAN_SA_BAN.md)).

   Bốn việc sau làm tối 24/09/2026, có biên bản ở mục 8:
8. Ghi và phát lại phiên bàn thử bốn camera + LiDAR, chạy lại cả bàn thử từ bản ghi — test với nguồn giả (TH) và một phiên
   thật 60 s ở 480p, phát lại cho đúng số bộ và phân bố độ lệch (BT) ([GHI_PHAT_LAI_BAN_THU.md](GHI_PHAT_LAI_BAN_THU.md)).
9. Định vị lại một vòng quét LiDAR trên bản đồ tĩnh đã lưu bằng khớp scan, có kết luận OK / AMBIGUOUS / FAILED; không phải
   SLAM — TH (phòng tổng hợp) + chạy offline trên bản ghi BT. Mới có độ **nhất quán**, chưa có sai số so với tham chiếu độc
   lập ([DINH_VI_LIDAR.md](DINH_VI_LIDAR.md)).
10. BEV chiếm chỗ từ AI nhiều camera, giữ vùng không chắc, bị che, chưa thấy là UNKNOWN — TH (rig tổng hợp) + DL (ảnh
    WoodScape `00000_FV` và một lần ba ảnh khác thời điểm); **chưa chạy trên camera dự án** ([BEV.md](BEV.md)).
11. Nối `VehicleIO` vào phiên đỗ xe, có kiểm trạng thái thật trước START và chế độ quan sát (tính lệnh, không gửi) — MP, bo
    mô phỏng và cổng serial giả ([CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md)). Phải nói kèm khoảng trống an toàn khi có
    `Heartbeat`: tìm thấy và sửa ngày 24/09, bằng chứng vẫn là MP, chưa có bo thật (3.12b).

   Bốn việc sau làm khuya 24/09/2026 (mức ở từng dòng, bảng cuối mục 8); ý 12–13 trong `10a4735`, ý 14 trong `65b7127`,
   ý 15 trong `a7cec5e`:
12. Kiểm nhãn "có nghiệm / vô nghiệm" của bộ ca lập đường khó bằng **đường chứng** kiểm va chạm liên tục, độc lập với
    planner; hai nhãn cũ `infeasible` hóa ra sai — MP ([KIEM_THU_DO_BEN_GIAI_DOAN_0.md](KIEM_THU_DO_BEN_GIAI_DOAN_0.md) mục 6).
13. Phép thử độ nhạy của planner theo kích thước xe với sa bàn cố định — MP, quanh xe giả định
    ([DO_NHAY_KICH_THUOC_XE.md](DO_NHAY_KICH_THUOC_XE.md)).
14. Công cụ ngoại tham camera và mặt nạ ROI có giao diện, chặn ghi kết quả tổng hợp như số đo — TH
    ([NGOAI_THAM_VA_ROI.md](NGOAI_THAM_VA_ROI.md)); **chưa đo camera nào**.
15. Odometry khớp scan và so sánh phương án định vị — DL (DROW v2, so với `.odom2`, không phải ground truth) + BT offline
    (C1 **đứng yên**) ([SO_SANH_DINH_VI_SLAM.md](SO_SANH_DINH_VI_SLAM.md)). Đề xuất phương án là TK; người dùng đồng ý làm
    theo ngày 02/10/2026 (1.6).
- Bộ kịch bản và ngưỡng nghiệm thu nháp (khuya 24/09) là **kế hoạch đo** (TK), không phải đóng góp đã kiểm chứng.
- Bản nháp giai đoạn 4 và 6 (bảng đo MN300, phiếu kiểm kê, bảng tải, sơ đồ nguồn/dừng, kịch bản thử lỗi) cũng là **kế
  hoạch đo**, không phải đóng góp đã kiểm chứng; nếu nhắc thì ghi TK.
- *Giới hạn phải nói:* không ghi "xe tự đỗ được", "AI phát hiện vật cản quanh xe", "hệ thống an toàn đã kiểm chứng", "có
  định vị LiDAR" hay "có BEV quanh xe" mà không kèm mức bằng chứng (xem mục 6 của tệp này).

**M.6. Bố cục khóa luận** — viết sau cùng, theo mẫu trường.

### Chương 1. Tổng quan

**1.1. Bài toán đỗ xe tự động và hệ thống trên xe mô hình**
- *Viết được:* chỉ phần định nghĩa bài toán của dự án (V1, kế hoạch 1.2, 16.1).
- *Còn thiếu:* tổng quan tài liệu về hệ đỗ xe tự động, các mức tự động hóa, hệ tương tự trên xe mô hình. Repo không có
  nguồn nào: **cần tra**.

**1.2. Cảm biến cho nhận thức quanh xe: camera góc rộng/fisheye, LiDAR 2D, ToF, IMU**
- *Viết được:* vai trò từng cảm biến trong kiến trúc đã chọn (kế hoạch 1.1, 2.1). Kế hoạch 1.1 ghi quyết định: bốn camera
  USB đưa ảnh về laptop bằng dây qua hub; "camera truyền video qua Wi-Fi" và "bốn ESP32-CAM" là cấu hình cũ không được tự
  đưa trở lại.
- *Còn thiếu:* lý do bỏ camera Wi-Fi và chọn camera USB. Kế hoạch v3.1 chỉ ghi quyết định, không ghi lý do; bản v3.0 mà
  v3.1 dựa vào không có trong repo. Cần người dùng ghi lại lý do, kèm ngày, trước khi viết. So sánh có trích dẫn giữa các
  loại cảm biến: **cần tra**.

**1.3. Dữ liệu công khai cho nhận thức quanh xe và LiDAR 2D**
- *Viết được:* khảo sát 44 bộ/nhánh dữ liệu (20/09) chia 6 nhóm: camera quanh xe/fisheye, phân đoạn đường và vật lạ, ô
  đỗ, LiDAR 2D/định vị, camera–LiDAR 3D, nguồn tổng hợp; kết luận kiểm nhãn: AVM-SS hợp trực tiếp cho FREE/vật cản,
  WoodScape hợp sau khi chuyển nhãn và xử lý vùng void, các bộ ô đỗ (PS2.0, PSV, ParkScape, PIL-park) không có nhãn pixel
  vật cản. Sáu bộ đã tải và kiểm: AVM-SS, DROW v2, WoodScape, ACDC, RoadAnomaly21, RoadObstacle21 (TONG_HOP mục 4.2).
- *Nguồn:* [DANH_MUC_DATASET.md](../datasets/DANH_MUC_DATASET.md) mục 1–8; [TAI_VA_KIEM_TRA.md](../datasets/TAI_VA_KIEM_TRA.md);
  [GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md). *Mức:* DL (khảo sát tài liệu và kiểm nhãn trên mẫu thật).
- *Hình/bảng:* bảng thu gọn từ DANH_MUC mục 1–6; bảng giấy phép.
- *Giới hạn phải nói:* khảo sát không bao quát mọi bộ dữ liệu; cột giấy phép của khảo sát 20/09 có đính chính 24/09 ở
  đầu tệp; nhiều giấy phép "chưa xác minh".

**1.4. Phân đoạn ngữ nghĩa nhẹ cho thời gian thực và vấn đề vật lạ**
- *Viết được:* mô hình đã dùng là L-RASPP + MobileNetV3-Large. Gói bàn giao 20/09 ghi "ưu tiên" mô hình này nhưng không ghi
  lý do (`review_artifacts/ai_handoff_rtx4000_20260920/PROMPT_CLAUDE.md` mục 3; thư mục git-ignore, chỉ có trên máy bàn).
  Độ trễ đo **sau khi** đã huấn luyện: 7,8 ms đầu-cuối ngày 22/09 (HUAN_LUYEN mục 12), chỉ trên máy bàn i9-14900/RTX 4000
  Ada, chưa đo trên laptop RTX 3050 Ti. Số này chỉ cho thấy mô hình đã chọn đủ nhanh cho mốc 4 camera × 30 FPS trên máy bàn;
  không trình bày nó như lý do chọn ban đầu. Viết thêm được bài toán vật lạ (benchmark SegmentMeIfYouCan) và vì sao
  "UNKNOWN" không phải một lớp mô hình học được (kế hoạch 16.2).
- *Còn thiếu:* lý do chọn L-RASPP ban đầu chưa có biên bản; cần người dùng bổ sung, không dựng ngược từ số đo 22/09. Bài
  báo gốc của MobileNetV3/L-RASPP; so sánh với các họ mô hình khác. Câu "các phương pháp chuyên vật lạ trên bảng xếp hạng
  đạt AP 0,7–0,9" ở HUAN_LUYEN mục 8 **không ghi nguồn**: cần tra trước khi trích.

**1.5. Lập đường cho xe có ràng buộc lái**
- *Viết được:* các họ phương pháp mà mã dùng: đường Reeds–Shepp, Hybrid A*, RRT-Connect nối bằng Reeds–Shepp, lưới trạng
  thái có thao tác gộp; và lý do dự án dùng một **danh mục** bộ lập đường có nghiệm thu bằng mô phỏng bám đường.
- *Nguồn:* docstring của [planning/portfolio.py](../autopark/planning/portfolio.py),
  [cand_rrt_rs.py](../autopark/planning/cand_rrt_rs.py), [cand_lattice_macro.py](../autopark/planning/cand_lattice_macro.py),
  [cand_reference.py](../autopark/planning/cand_reference.py), [reeds_shepp_full.py](../autopark/planning/reeds_shepp_full.py);
  BAO_CAO_GIAI_DOAN_0 mục 2. *Mức:* MP.
- *Còn thiếu:* bài báo gốc của Hybrid A*, RRT-Connect, lưới trạng thái (**cần tra**). Các số đo làm cơ sở chọn thang lập
  đường **chỉ nằm trong docstring**, chưa có biên bản đo riêng. Ví dụ: "ca cột chắn cửa ô 0,04 s so với 4,59 s",
  "`parallel_135` giải trong 1,14 s". Phải chạy lại và lưu hồ sơ trước khi đưa vào khóa luận.

**1.6. Bản đồ và định vị 2D bằng LiDAR (SLAM, khớp scan)**
- *Hiện trạng:* dự án chưa chọn phương án **SLAM** (TONG_HOP mục 5.4). Kế hoạch mục 5 cảnh báo không coi chuỗi scan là đủ
  cho mọi thư viện và không gán odometry bằng 0 để báo đã có định vị. Những gì đã có về định vị:
  - Từ tối 24/09/2026: bộ định vị trên bản đồ tĩnh đã lưu. Nó không cập nhật bản đồ và không cộng dồn chuyển động.
  - Từ khuya 24/09/2026 (`a7cec5e`): [SO_SANH_DINH_VI_SLAM.md](SO_SANH_DINH_VI_SLAM.md) so sánh bốn phương án: (a) bản đồ
    tĩnh + định vị lại (đã có); (b) odometry khớp scan + bản đồ tăng dần (mới viết, chạy offline); (c) thư viện SLAM
    ngoài (Cartographer, slam_toolbox, Hector, GMapping, BreezySLAM, KISS-ICP…), không cài được trong đợt đó; (d) odometry
    bánh xe/IMU, chưa có phần cứng. Tài liệu **đề xuất** (a) + (b) cho sa bàn nhỏ, tĩnh, vì không cần đóng vòng hay bản đồ
    dựng dần.
  - Ngày 02/10/2026 người dùng đồng ý làm theo đề xuất (a) + (b). Nguồn tư thế này đã nối vào phiên ở mức MP (LiDAR mô
    phỏng) và chạy offline trên bản ghi C1 đứng yên (BT offline); các ngưỡng vẫn là đề xuất, chưa chốt
    ([NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md); 4.4).
- *Viết được:* phần tổng quan về **định vị trên bản đồ đã biết**: trường khả năng từ khoảng cách tới ô OCCUPIED gần nhất,
  khớp tương quan trên lưới rời rạc với nhánh-cận nhiều mức ("theo cách của Cartographer", chữ của
  [DINH_VI_LIDAR.md](DINH_VI_LIDAR.md) mục 2), tinh chỉnh Gauss-Newton. Viết được phần so sánh bốn phương án và lý do đề
  xuất (a) + (b), kèm điều kiện tiên quyết.
- *Còn thiếu:* chọn phương án SLAM nếu V1 cần bản đồ lớn hơn một góc nhìn, tra tài liệu và kiểm đầu vào bắt buộc của nó.
  Mọi yêu cầu về nền tảng, đầu vào, giấy phép của các thư viện SLAM ngoài là "cần tra". Tài liệu gốc cho khớp tương quan,
  nhánh-cận, trường khả năng: **cần tra** (mục 5, A21–A23).
- *Giới hạn phải nói:* tài liệu không ghi vì sao chọn cách định vị trên bản đồ tĩnh thay cho cách khác, và chưa có phép so
  sánh đo được; không viết "lý do chọn" khi chưa có biên bản. Không viết V1 "đã có SLAM".

**1.7. An toàn trong hệ thống điều khiển nhỏ**
- *Viết được:* nguyên tắc của kế hoạch (E-stop vật lý là đường dừng riêng, không phụ thuộc laptop; cờ STOP trên laptop
  không chứng minh xe dừng; reconnect không tự chạy tiếp; kế hoạch 2.1, 10, 13).
- *Còn thiếu:* nếu muốn dẫn tiêu chuẩn an toàn chức năng thì **cần tra**; repo không trích tiêu chuẩn nào.

**1.8. Kết luận chương** — nêu khoảng trống đề tài nhắm tới ở mức khiêm tốn: tích hợp và kiểm chứng có phân mức trên thiết
bị rẻ, không tuyên bố mới về thuật toán khi chưa có tổng quan để so.

### Chương 2. Cơ sở lý thuyết

Phần lớn chương này viết được từ mã và tài liệu. Chỗ nào mã tự thiết kế thì ghi là thiết kế của dự án; chỗ nào theo lý
thuyết có sẵn thì cần trích nguồn gốc (mục 5).

**2.1. Hệ tọa độ, đơn vị, thời gian**
- *Viết được:* mét, giây, radian; tư thế tại tâm trục sau, x trước, y trái, yaw dương ngược chiều kim đồng hồ, trùng hệ xe
  ISO 8855 của WoodScape; bố cục costmap `cells[row][col]`; góc LiDAR thiết bị tăng theo chiều kim đồng hồ và driver đổi
  dấu; một đồng hồ `perf_counter` cho mọi luồng của bàn thử; stamp camera là lúc `read()` trả khung, không phải lúc phơi
  sáng.
- *Nguồn:* [autopark/README.md](../README.md) mục 10; GIAI_DOAN_1_LIDAR mục 2; [GIAI_DOAN_1_CHUAN_BI.md](GIAI_DOAN_1_CHUAN_BI.md) mục 2; GIAI_DOAN_2_BAN_THU mục 1.
- *Giới hạn phải nói:* dấu góc trái/phải của LiDAR **chưa xác minh bằng vật thật** ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 6b).

**2.2. Mô hình động học xe đạp và giới hạn cơ cấu chấp hành**
- *Viết được:* phương trình ở kế hoạch mục 4; tích phân chính xác theo cung tròn với v, δ không đổi trong bước; bão hòa
  mục tiêu, tốc độ đổi lái, gia tốc/phanh, đổi chiều phải qua 0 ([simulation/vehicle.py](../autopark/simulation/vehicle.py)).
- *Giới hạn phải nói:* thông số trong [vehicle_default.json](../configs/vehicle_default.json) là **giả định**, chưa phải số
  đo MN300; mô hình không có trượt lốp, biến dạng, động lực học (BAO_CAO_GIAI_DOAN_0 mục 12).

**2.3. Đường Reeds–Shepp, Hybrid A*, RRT-Connect, lưới có thao tác gộp; kiểm tra va chạm toàn thân**
- *Viết được:* Reeds–Shepp đủ 48 từ đường từ 9 công thức gốc cùng ba phép đối xứng, mọi ứng viên tích phân lại tới điểm
  cuối; Hybrid A* trên lưới (x, y, yaw, chiều) với heuristic max(khoảng cách 2D có vật cản, độ dài Reeds–Shepp không
  vật cản khi gần đích) và thử nối thẳng tới đích bằng Reeds–Shepp;
  RRT-Connect hai cây với khoảng cách Reeds–Shepp; thao tác gộp dịch ngang Δy = 4R(1 − cos φ); kiểm tra va chạm bằng thân
  xe nới lề và vùng quét, bộ kiểm tra nhanh theo định lý trục tách (SAT), oracle độc lập bằng số phức + SAT tổng quát.
- *Nguồn:* docstring các tệp ở mục 1.5; [geometry/fast_collision.py](../autopark/geometry/fast_collision.py);
  [evaluation/collision_oracle.py](../autopark/evaluation/collision_oracle.py); KIEM_THU_DO_BEN_GIAI_DOAN_0 mục 4.
- *Giới hạn phải nói:* kiểm tra chuyển động là **lấy mẫu**, không phải chứng minh liên tục; TIMEOUT không đồng nghĩa vô
  nghiệm hình học.

**2.4. Bám quỹ đạo tiến/lùi**
- *Viết được:* luật lái δ = δ_ff + dir·k_θ·e_θ − atan(k_y·e_y / (|v| + v_ε)) với feedforward độ cong, dừng hẳn ở điểm đổi
  chiều ([control/tracker.py](../autopark/control/tracker.py)). Docstring của tracker.py chỉ nhắc Pure Pursuit thuần để
  giải thích vì sao cần δ_ff: "cắt cua trên cung bán kính nhỏ", một nhận định chưa đo. Dự án chưa có cài đặt Pure Pursuit
  hay phép so sánh đo được.
- *Còn thiếu:* mã không trích nguồn gốc của dạng luật này: **cần tra** trước khi gắn tên phương pháp. Muốn so sánh với Pure
  Pursuit thì phải cài đặt và chạy trên cùng bộ kịch bản mô phỏng; chưa làm.

**2.5. Mô hình camera fisheye, hiệu chuẩn, chiếu xuống mặt sàn**
- *Viết được:*
  - đa thức WoodScape ρ(θ) = k1θ + k2θ² + k3θ³ + k4θ⁴, tâm ảnh, quaternion camera → xe (theo `readme.txt` trong
    `calibration.zip`);
  - mô hình Kannala–Brandt 4 hệ số của `cv2.fisheye`, chỉ biểu diễn tia lệch trục dưới 90°; chuyển sang đa thức dự án bằng
    bình phương tối thiểu rồi lặp Lawson;
  - hiệu chuẩn bằng bảng ô vuông, luôn tinh chỉnh góc bằng `cornerSubPix`;
  - costmap từ ảnh: chiếu tâm ô vào ảnh bằng phép chiếu thuận; IGNORE/ngoài ảnh/ngoài ROI → UNKNOWN; ô sau ô OCCUPIED gần
    nhất trong cùng phương vị → UNKNOWN; giả định sàn phẳng z = 0;
  - BEV nhiều camera (từ tối 24/09/2026) dùng lại đúng phép chiếu này (`costmap.project_labels`, không sửa). Nó thêm hai
    ngưỡng xác suất (P ≤ 0,15 → FREE, P ≥ 0,50 → OCCUPIED, ở giữa → không chắc), lưới mịn 2 × 2 và một lượt chiếu ngược
    pixel → sàn chỉ để gỡ FREE ([BEV.md](BEV.md) mục 2–3). Phần thiết kế ở 3.8b.
- *Nguồn:* GIAI_DOAN_1_CHUAN_BI mục 2–3; [HIEU_CHUAN_CAMERA.md](HIEU_CHUAN_CAMERA.md) mục 1, 4.
- *Giới hạn phải nói:* kế hoạch mục 6 nhắc rằng chiếu mặt sàn chỉ đúng cho điểm thuộc mặt sàn, và không biến mask của vật
  cao thành footprint. Camera USB 130° là phối cảnh hay fisheye **chưa trả lời**, vì chưa hiệu chuẩn camera nào. Bảng độ
  phân giải mặt sàn theo khoảng cách ở BEV.md mục 3 là số **tính** trên ống kính danh định và tư thế giả định, chưa đo.

**2.6. Phân đoạn ngữ nghĩa hai lớp, chỉ số, ngưỡng quyết định**
- *Viết được:* L-RASPP + MobileNetV3-Large, thay cả hai đầu phân lớp về 2 lớp, khởi tạo từ trọng số torchvision
  `COCO_WITH_VOC_LABELS_V1`; cross-entropy bỏ qua 255; AdamW hai nhóm LR, warmup + poly, AMP fp16; mIoU, recall/precision
  vật cản, và hai loại lỗi "vật cản → FREE" (nguy hiểm) và "FREE → vật cản" (báo động giả); ngưỡng P(BLOCKED) chọn trên
  val theo F2.
- *Nguồn:* HUAN_LUYEN mục 2.3, 10; [perception/model.py](../autopark/perception/model.py).
- *Còn thiếu:* bài báo gốc (MobileNetV3, AdamW, định nghĩa F2): **cần tra**.

**2.7. LiDAR 2D và bản đồ lưới chiếm chỗ**
- *Viết được:* giao thức gói SLAMTEC (lệnh + checksum, node 5 byte, cờ bắt đầu vòng); bản đồ lưới bằng ray casting: ô "đi
  qua"/"chạm", tia không phản hồi không phải bằng chứng trống, OCCUPIED/FREE/UNKNOWN theo ngưỡng
  ([lidar/occupancy.py](../autopark/lidar/occupancy.py)).
- *Định vị trên bản đồ tĩnh (từ tối 24/09/2026):* bốn bước ([DINH_VI_LIDAR.md](DINH_VI_LIDAR.md) mục 2). *Mức:* TH + BT
  offline (4.4).
  - Trường khả năng exp(−d²/2σ²) và phạt điểm chạm trong ô FREE.
  - Khớp tương quan trên lưới (x, y, θ) với nhánh-cận nhiều mức. Ở mức k lấy max theo khối 2^k × 2^k, nên điểm của khối là
    cận trên đúng.
  - Tinh chỉnh Gauss-Newton có giảm chấn Levenberg–Marquardt và trọng số Cauchy; hiệp phương sai s²·(JᵀWJ)⁻¹.
  - Kiểm từng tia (khớp / mâu thuẫn ngắn / xuyên tường / không kiểm được); tỉ lệ khớp tính trên mọi tia hợp lệ.
- *Còn thiếu:* nguyên lý đo của C1 theo datasheet (**cần tra**, repo không lưu datasheet); lý thuyết SLAM (chưa chọn
  phương án); nguồn gốc của khớp tương quan, nhánh-cận, Gauss-Newton/Levenberg–Marquardt, trọng số Cauchy (**cần tra**,
  mục 5, A21–A23).

**2.8. Hợp nhất nhiều nguồn và giám sát dữ liệu cũ**
- *Viết được:* mỗi lớp có tuổi tối đa; ô OCCUPIED nếu lớp tươi nào OCCUPIED, FREE nếu có lớp tươi FREE, còn lại UNKNOWN;
  lớp bắt buộc cũ → bản đồ không hợp lệ, mọi ô bị chặn; `FreshnessMonitor` phát `NO_DATA`/`STALE_DATA`/`CLOCK_SKEW`.
- *Nguồn:* GIAI_DOAN_3_CHUAN_BI mục 1; GIAI_DOAN_1_CHUAN_BI mục 4. *Mức:* đây là thiết kế của dự án, không cần trích
  nguồn ngoài nếu không so với phương pháp khác.

**2.9. Truyền thông tin cậy laptop–vi điều khiển và máy trạng thái an toàn**
- *Viết được:* khung COBS + CRC-16/CCITT-FALSE, phiên và số thứ tự, thời hạn lệnh, watchdog hai phía, máy trạng thái
  BOOT/DISARMED/ARMED/RUNNING/FAULT, "reset và reconnect luôn về DISARMED".
- *Nguồn:* [GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 1–9. *Còn thiếu:* nguồn gốc COBS và tham số CRC (mục 5, cần tra chi tiết
  bài báo/danh mục).

**2.10. Điều khiển tốc độ PI có feedforward và bù vùng chết**
- *Viết được:* effort = sign(ref)·(bù vùng chết + ff·|ref|) + kp·(ref − v_đo) + I, kẹp theo trần effort, chống bão hòa
  tích phân, khóa đổi chiều (GIAO_THUC_XE mục 7).
- *Giới hạn phải nói:* hệ số chọn trên mô hình giả định, không có giá trị với xe thật.

### Chương 3. Thiết kế và xây dựng hệ thống

**3.1. Yêu cầu và kiến trúc tổng thể**
- *Viết được:* yêu cầu V1 và các nguyên tắc (kế hoạch 1.2–1.3, 2.1); laptop là bộ não, ESP32-S3 chỉ điều khiển cấp thấp;
  nhánh giám sát luôn chạy; sơ đồ thư mục mã ([autopark/README.md](../README.md) mục 10 "Cấu trúc mã").
- *Hình:* sơ đồ khối và luồng dữ liệu: **cần vẽ** (kế hoạch 2.1 mới là khối chữ).

**3.2. Phần cứng**
- *Viết được:* bảng thiết bị đã nhận: RPLIDAR C1 + CP2102N ngày 22/09; bốn camera "HD Camera" 1BCF:0B09 không serial và
  hub UGREEN Genesys Logic ngày 23/09. Bốn camera chung một nhánh USB 2.0, danh tính camera theo cổng hub. Hai máy tính và
  vai trò; danh sách chưa nhận.
- *Nguồn:* [hardware_inventory.md](hardware_inventory.md); [usb_topology.md](usb_topology.md); [camera_modes.csv](camera_modes.csv).
  *Mức:* BT.
- *Hình/bảng:* bảng kiểm kê; sơ đồ cổng USB (cần vẽ từ `usb_topology_*.json`).
- *Còn thiếu:* ảnh thiết bị thực giao (chưa chụp), model in trên nhãn LiDAR, mã model hub, chiều dài/loại dây camera, góc
  nhìn thật của camera; toàn bộ phần xe, gá, nguồn, dừng (giai đoạn 4–7). Từ tối 24/09/2026 có ba bản nháp mức TK:
  - mẫu phiếu kiểm kê MN300 để điền khi nhận xe ([mn300_inventory.md](mn300_inventory.md)), chưa có ô nào về chiếc xe thật;
  - bảng khái niệm gá điều chỉnh được ([GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md) mục 6), chưa quyết định gia công;
  - bảng tải P1–P14 ([GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md) mục 1): chỉ C1 có số datasheet, tổng theo nhánh
    chưa cộng được.
- *Giới hạn phải nói:* 130° là số nhà bán, chưa đo; hub chạy bus-powered trong mọi phiên, chưa thử nguồn ngoài.

**3.3. Kiến trúc phần mềm và hợp đồng dữ liệu**
- *Viết được:* các hợp đồng `VehicleState`, `GoalPose`, `CameraFrame`, `LidarScan`, `Telemetry`, `Costmap`, `Trajectory`,
  `SafetyEvent`; mỗi nguồn có nhận dạng, thời gian, trạng thái hợp lệ. Hai môi trường: `.venv` (mô phỏng, giao diện, không
  torch) và `.venv-train` (torch, bàn thử); khóa phiên bản ([requirements-phase0.lock](../requirements-phase0.lock),
  [requirements-train.lock](../requirements-train.lock)). Từ 25/09/2026 `.venv-train` có cả Shapely 2.1.2, nên phiên đỗ xe
  và AI camera chạy chung một tiến trình (3.11b); `.venv` vẫn không có torch.
- *Nguồn:* [domain/types.py](../autopark/domain/types.py), [domain/sensors.py](../autopark/domain/sensors.py);
  GIAI_DOAN_0 mục "Môi trường"; autopark/README.

**3.4. Mô phỏng, giao diện đặt đích, máy trạng thái phiên, log và replay**
- *Viết được:* đặt/kéo/xoay đích, từ chối đích trong vật cản; xem trước là rollout riêng không phát lệnh phần cứng; chuỗi
  `MAP_CHANGED → STOPPING → STOPPED → WAIT_REPLAN`; `COMPLETED` chỉ khi đạt dung sai; hết giờ → phanh rồi `FAULT`; mỗi
  phiên lưu cấu hình, quỹ đạo, sự kiện, kết quả, môi trường, `source.zip`; replay dùng quỹ đạo đã lưu.
- *Nguồn:* [BAO_CAO_GIAI_DOAN_0.md](../../BAO_CAO_GIAI_DOAN_0.md) mục 2–4, 7; [GIAI_DOAN_0.md](GIAI_DOAN_0.md). *Mức:* MP.
- *Hình:* [ui_running.png](evidence/ui_running.png), [ui_stopped.png](evidence/ui_stopped.png) (20/09); sơ đồ máy trạng
  thái: cần vẽ.
- *Nhánh chạy (từ tối 24/09/2026):* ngăn "Mô phỏng" có ô chọn nhánh chạy: mô phỏng giai đoạn 0 (mặc định), `VehicleIO` →
  bo mô phỏng, hoặc quan sát. Nhánh mặc định giữ nguyên hành vi, snapshot và replay của giai đoạn 0. Chi tiết ở 3.12b.
- *Replay của lần chạy qua `VehicleIO`:* lúc đầu chưa có. Từ 02/10/2026 (công cụ T9, mức MP), lần chạy này xuất gói và
  phát lại được bằng log: chạy lại cùng phần mềm trên đầu vào đã ghi và so quyết định với bản ghi, không tái mô phỏng xe
  ([CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) mục 5.1). Gói SIM vẫn tái mô phỏng như trước.

**3.5. Bộ lập đường danh mục và nghiệm thu bằng mô phỏng**
- *Viết được:* thang bốn nấc: lưới thô có thao tác gộp 1,0 s; cùng bộ đó thêm thời gian 1,5 s; RRT-Connect + Reeds–Shepp
  4,0 s; Hybrid A* lưới mịn có thao tác gộp 1,5 s. Mỗi ứng viên phải qua mô phỏng bám đường kín vòng; không nấc nào đạt
  dung sai thì trả `TRACKING_FAILED`.
- *Nguồn:* `default_ladder()` trong [planning/portfolio.py](../autopark/planning/portfolio.py). *Mức:* MP.
- *Còn thiếu:* biên bản đo riêng cho lựa chọn thang (mục 1.5 của tệp này).

**3.6. Nhánh LiDAR**
- *Viết được:* giao thức và driver C1: 460800 bps, dò lại khi lệch byte, gom vòng theo cờ bắt đầu **và** theo điểm góc quay
  về 0 (thêm sau lần thiết bị bỏ sót cờ). Ghi/phát lại `.npz` + `.json`; phiên đo tĩnh; bản đồ lưới tĩnh; màn hình trực
  tiếp có giám sát dữ liệu cũ 0,3 s.
- *Nguồn:* [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 1–5. *Mức:* BT.
- *Hình:* [p07_nen_phong.png](evidence/lidar/p07_nen_phong.png), [map_p07.png](evidence/lidar/map_p07.png).
- *Thêm từ tối 24/09/2026:* nạp lại bản đồ và định vị (3.6b). Vòng LiDAR cũng được ghi và phát lại cùng bốn camera trong
  bản ghi bàn thử (3.14; [GHI_PHAT_LAI_BAN_THU.md](GHI_PHAT_LAI_BAN_THU.md) mục 3). Mỗi `lidar/part_XXXX.npz` đọc được
  như bản ghi LiDAR thường nhưng stamp theo đồng hồ bàn thử.
- *Thêm từ khuya 24/09/2026 (`a7cec5e`):*
  - `lidar/repeatability.py`: độ lặp lại khoảng cách theo tia giữa hai vòng liên tiếp và theo ô góc 0,5° đã khử dốc
    ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 3c; TH 20 test + BT offline);
  - `lidar/scan_odometry.py`: odometry khớp scan với bản đồ tăng dần, `scan_to_map` / `scan_to_scan`, phát hiện suy biến
    hành lang ([SO_SANH_DINH_VI_SLAM.md](SO_SANH_DINH_VI_SLAM.md) mục 3; TH 32 test + DL + BT offline).
- *Bài học đáng viết (MP/DL):* phần lớn lần lạc trên DROW là do lỗi "khóa trục cứng" khi phép kiểm suy biến báo nhầm,
  **không** phải do thiếu odometry bánh xe như kết luận của bản đầu. Lỗi này được tìm thấy nhờ vòng kiểm tra độc lập.

**3.6b. Định vị LiDAR trên bản đồ tĩnh đã lưu** *(thêm tối 24/09/2026)*
- *Viết được:*
  - tách ba kết quả theo kế hoạch mục 5 bước 6: đọc scan được / tạo map được / định vị lại được;
  - bốn bước của thuật toán (2.7);
  - quy tắc kết luận với mười lý do: `too_few_beams`, `no_overlap`, `few_matched`, `low_match_fraction`,
    `conflicts_with_map`, `window_edge` → FAILED; `second_peak`, `degenerate`, `search_truncated`, `refine_unstable` →
    AMBIGUOUS. Chỉ tư thế OK được dùng tiếp; chế độ `--track` chỉ dời tâm cửa sổ theo vòng OK;
  - bài học thiết kế "tỉ lệ khớp phải tính trên mọi tia hợp lệ": bản đầu nhận nhầm một hội trường tròn trên bản đồ phòng.
- *Nguồn:* [DINH_VI_LIDAR.md](DINH_VI_LIDAR.md) mục 1–3, 6; [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 8.
  *Mức:* TH (29 test trên phòng tổng hợp) + chạy offline trên bản ghi BT (kết quả ở 4.4).
- *Hình (`b100a5d`):* [dinh_vi_p07_tren_p07.png](evidence/lidar/dinh_vi_p07_tren_p07.png) (không độc lập với bản đồ),
  [dinh_vi_live_headless_tren_p07.png](evidence/lidar/dinh_vi_live_headless_tren_p07.png),
  [dinh_vi_k01_tren_p07.png](evidence/lidar/dinh_vi_k01_tren_p07.png),
  [dinh_vi_k01_global_tren_p07.png](evidence/lidar/dinh_vi_k01_global_tren_p07.png) (`--global --every 5`); tóm tắt
  [dinh_vi_tren_p07_20260924.json](evidence/lidar/dinh_vi_tren_p07_20260924.json) (GIAI_DOAN_1_LIDAR mục 8). Bốn ảnh
  dựng bằng mã đã sửa màu overlay. Ảnh chỉ cho thấy độ **nhất quán**, không phải độ đúng.
- *Còn thiếu:* định vị khi cảm biến di chuyển trong cảnh thật (chưa có bản ghi nào như vậy). Việc nối vào phiên làm nguồn
  tư thế đòi `PoseSource` đóng dấu cùng đồng hồ với `VehicleIO.now()` ([CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) mục 2);
  từ 02/10/2026 đã nối ở mức MP với LiDAR mô phỏng (1.6; [NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md)).
- *Giới hạn phải nói:* không phải SLAM, không phải odometry. Các ngưỡng 0,6 / 0,25 / 0,9 / 5 cm / 2° là giá trị tạm, chưa
  chốt. Dấu trái/phải của driver không kiểm được bằng định vị, vì bản đồ và vòng quét cùng quy ước. `overlay.png` tạo
  trước bản sửa màu ngày 24/09 **không dán vào khóa luận**; bốn ảnh `dinh_vi_*.png` trong `evidence/lidar/` là bản tạo lại
  bằng mã đã sửa màu, không phải các tệp cũ đó.

**3.7. Nhánh camera và ghép bộ ảnh nhiều camera**
- *Viết được:*
  - ba bẫy OpenCV 5 + DirectShow có hồ sơ: mode phải đưa vào lúc mở; `grab()` không chờ khung mới; fourcc đọc lại tin
    được, fps thì không;
  - chọn camera theo cổng hub, vì index đổi sau khởi động lại;
  - `MultiCameraManager`: vòng đệm 3 khung, ghép theo mốc, bỏ bộ lệch > 60 ms;
  - bộ dò `truncated_rows`/`torn_bands` (≈ 0,2 ms/khung 720p);
  - quy tắc không chờ camera chậm. Bản trưa 24/09 chờ tối đa L = max(60 ms; 1,5 × chu kỳ camera nhanh nhất). Tối 24/09
    ngưỡng chung này bị thay, vì nó bỏ camera khỏe 24 khung/s khi có một camera chạy 29,3 khung/s (4.6; camera ≈ 29
    khung/s không cố định một cổng, 4.5).
- *Quy tắc theo nhịp riêng (từ tối 24/09/2026):* xét **mỗi camera theo nhịp của chính nó**, L = max(60 ms; 1,5 × chu kỳ đo
  được của nó). Camera đang chờ bị bỏ khỏi bộ khi:
  - khung mới cũ nhất đã chờ quá L;
  - khung "đúng lượt" (đoán theo các camera cùng nhịp) trễ quá nửa chu kỳ của nó;
  - khung đúng lượt tới mà hỏng;
  - hoặc camera treo (không lần tới nào trong 2,5 chu kỳ).

  Camera khỏe mà chậm hơn (phơi sáng dài) không bị bỏ: nó định nhịp cả chuỗi. Json ghi `policy.wait_rule = "own_cadence"`
  và `wait_periods_of_own`; khóa cũ `wait_periods_of_fastest` vẫn được ghi.
- *Nguồn:* [GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) mục 3, 5; [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 1,
  2.2, 10, 10.1–10.3; docstring đầu `autopark/video/multicam.py`. *Mức:* BT (bốn camera khỏe); TH (nhánh camera lỡ nhịp,
  đồng hồ giả).
- *Hình/bảng:* [khung_bi_cat_720p.jpg](evidence/rig/khung_bi_cat_720p.jpg), [day_khung_bi_cat.jpg](evidence/rig/day_khung_bi_cat.jpg),
  [day_khung_bi_cat_480p.jpg](evidence/rig/day_khung_bi_cat_480p.jpg), [khung_xe_480p.jpg](evidence/rig/khung_xe_480p.jpg);
  hồ sơ ba bẫy [traps_cam0.traps.json](evidence/camera/traps_cam0.traps.json) và lần chạy `UsbCameraSource`
  [source_cam0_720p.source.json](evidence/camera/source_cam0_720p.source.json) (23/09, BT).
- *Giới hạn phải nói:*
  - Bộ dò bỏ sót khi bộ giải mã tô màu phẳng, khi khung bị cắt giữa hàng khối cuối, hoặc khi dải xé cách mép phải dưới 64
    điểm. Chưa có phép kiểm độc lập bằng byte MJPEG thô.
  - Quy tắc ghép theo nhịp riêng: các hệ số 1,5, nửa chu kỳ, 2,5 và 15 % (ngưỡng "cùng nhịp") là lựa chọn thiết kế,
    **chưa đo** trên phần cứng. Một camera chậm cố định (ví dụ 8 khung/s ở chỗ tối) vẫn làm AI chậm theo như quy tắc cũ.
    Khi các camera khác nhịp thì độ lệch trong bộ lớn hơn.

**3.8. Nhánh AI: dữ liệu, huấn luyện, suy luận, ROI, costmap từ ảnh**
- *Viết được:*
  - ánh xạ nhãn WoodScape → FREE/BLOCKED/IGNORE;
  - chia tập theo timestamp + ảnh gần trùng: 5.764 / 1.235 / 1.235 ảnh, 1.261 nhóm;
  - `verify_cache`: khớp tới từng bit trên 256 ảnh dựng lại;
  - trainer có resume tất định và lớp chặn tập test (`--final-test`);
  - bài học `channels_last` làm train chậm ≈ 5,5 lần trên tổ hợp này;
  - suy luận theo lô trên bàn thử; ONNX; ROI WoodScape; costmap trên ảnh WoodScape;
  - làm nóng AI (từ tối 24/09/2026): `AIWorker.warm_up` (`rig/core.py`) chạy một lô ảnh đen cho mỗi cỡ lô n, n−1, …, 1
    ngay sau khi nạp mô hình, ở cả phiên thật lẫn phát lại. Lý do: lô đầu của **mỗi** cỡ lô tốn 1,2–1,7 s trên GPU máy
    bàn (số đo ở 4.6). Json ghi `ai.warm_up_ms`.

  BEV từ đầu ra AI ở 3.8b.
- *Nguồn:* [HUAN_LUYEN.md](../../HUAN_LUYEN.md) mục 2; GIAI_DOAN_1_CHUAN_BI mục 1–3, 5; GIAI_DOAN_2_BAN_THU mục 1. *Mức:* DL
  (huấn luyện, costmap), BT (suy luận trực tiếp).
- *Giới hạn phải nói:* ROI và costmap mới có cho rig WoodScape; giấy phép (mục 1, ý 4). Về việc nối đầu ra AI vào
  costmap/planner:
  - Bản đầu: đầu ra AI **chưa nối**; `CameraSemanticLayer` chưa được khởi tạo ở đâu.
  - Tối 24/09/2026: BEV đã tạo được `Costmap` và test đặt nó vào `CameraSemanticLayer`, nhưng bàn thử, hợp nhất và
    planner vẫn không dùng nó.
  - Từ đợt AI camera 25/09/2026: ngăn AI camera đưa BEV vào phiên đỗ xe làm nguồn vật cản (3.11b), mức TH cộng phát lại.
    Trên bàn thật chưa tạo vật cản nào vì chưa hiệu chuẩn. Lớp tô của `rig_app` vẫn chỉ để nhìn.

**3.8b. BEV chiếm chỗ từ AI nhiều camera** *(thêm tối 24/09/2026; kế hoạch giai đoạn 2 bước 7)*
- *Viết được:* đầu vào mỗi camera gồm bản đồ P(BLOCKED) cùng tỉ lệ khung với ảnh đã hiệu chuẩn, nội tham + ngoại tham trong
  hệ xe, ROI tùy chọn; một `GridSpec` chung. Tám quy tắc (BEV.md mục 2) gồm các ý:
  - hai ngưỡng: P ≤ `t_free` 0,15 → FREE, P ≥ `t_blocked` 0,50 → OCCUPIED, ở giữa → không chắc;
  - chiếu tâm ô vào ảnh; ô sau ô OCCUPIED đầu tiên theo từng phương vị là UNKNOWN (bị che);
  - lưới mịn 2 × 2 và lượt pixel → sàn chỉ để **gỡ** FREE, không đặt OCCUPIED;
  - hợp nhất ở lưới mịn, OCCUPIED thắng; "không chắc" không phủ quyết FREE chắc chắn của camera khác;
  - camera thiếu dữ liệu (không có xác suất, khung nghi hỏng, lệch thời gian) không góp gì, và vùng chỉ nó thấy giữ
    UNKNOWN, **không bao giờ mặc định FREE**;
  - dưới thân xe là UNKNOWN;
  - bitmask nguồn gốc từng ô.

  Sáu loại ô: free, occupied, uncertain, occluded, unseen, ego. Costmap bị đánh dấu không dùng được cho lập đường khi ngoại
  tham chưa đo, chưa có ROI, hoặc nội tham không đạt tiêu chí chấp nhận. Từ 25/09/2026 (`65b7127`) thêm trường hợp ngoại
  tham hay nội tham là dữ liệu tổng hợp (`"synthetic": true`), kể cả khi tệp ghi `"measured": true` ([BEV.md](BEV.md)
  mục 2).
- *Nguồn:* [BEV.md](BEV.md) mục 1–5; [autopark/perception/bev.py](../autopark/perception/bev.py);
  [camera_rig_extrinsics_v0.json](../configs/rig/camera_rig_extrinsics_v0.json). *Mức:* TH (rig bốn camera tổng hợp) + DL
  (ảnh WoodScape `00000_FV` và một lần ba ảnh khác thời điểm); số ở 4.9b.
- *Hình:* `bev.png` của lệnh `synthetic` (ô trái phân loại ô, ô phải số camera thấy) chưa được lưu trong repo hay trong
  `autopark/runs/`, và chưa có bản nào trong `docs/evidence/`. [BEV.md](BEV.md) mục 6 chỉ ghi thư mục ra của các lần chạy
  24/09 "nằm ngoài repo", không ghi đường dẫn; nhiều khả năng là thư mục tạm của phiên làm việc, có thể đã mất. Kiểm tối
  24/09, `autopark/runs/bev/` chưa tồn tại. Tạo lại bằng lệnh `synthetic` ở BEV.md mục 5 (mặc định ghi vào
  `runs/bev/<tên>/`, git-ignore), rồi chép bản nhỏ vào `docs/evidence/` và sao lưu (mục 7, việc 21).
- *Còn thiếu (theo thứ tự BEV.md mục 8):*
  - hiệu chuẩn nội tham bốn camera; không có thì lệnh `snapshot` từ chối;
  - gá, chốt gán cổng → hướng, đo ngoại tham. Công cụ ngoại tham và ROI đã có từ khuya 24/09, mức TH (3.9; `65b7127`);
  - ROI cho camera dự án;
  - đo sai số BEV bằng vật mẫu ở vị trí đo bằng thước (kế hoạch mục 6 bước 8);
  - phương pháp biên tiếp xúc của vật cao (chưa chọn);
  - đo thời gian trên laptop.

  Hai việc trong danh sách gốc đã làm ở mức phần mềm:
  - *Tăng tốc* (khuya 24/09, `65b7127`): phần hình học dựng một lần rồi nhớ, kết quả trùng từng bit với bản cũ, ≈ 7–12 ms
    cho 4 camera trên rig tổng hợp ([BEV.md](BEV.md) mục 6b; số ở 4.9b).
  - *Nối vào `CameraSemanticLayer`/bàn thử* (đợt AI camera 25/09, sau quyết định giấy phép; Valeo chưa xác nhận): ngăn AI
    camera dựng bảng lúc bật AI, đặt BEV vào lưới sa bàn, lọc 2/3 lô rồi đưa vào phiên (3.11b). Từ 25/09,
    `acceptance.all_pass` chỉ đạt khi là `true` của JSON (`bev.acceptance_flag`, [BEV.md](BEV.md) mục 2).
- *Giới hạn phải nói:*
  - Giả định sàn phẳng z = 0, **không phải footprint chính xác**: vật nhô, chân vật bị che, sàn nghiêng, vật mảnh ở xa.
  - Ngoại tham v0 là "GIẢ ĐỊNH — CHƯA ĐO", đặt cho xe 0,40 × 0,20 m, khác kích thước giả định 0,31 × 0,14 m của
    `vehicle_default.json`. Mọi BEV từ tệp rig v0 đều không dùng được cho lập đường.
  - Hai ngưỡng chưa kiểm trên ảnh sa bàn; mọi lỗi của mô hình đi thẳng vào BEV.
  - Ảnh WoodScape chỉ có một camera mỗi mã khung nên không có bộ bốn camera đồng bộ; phải ghi công WoodScape.

**3.9. Công cụ hiệu chuẩn camera**
- *Viết được:* bảng in A4/A3, dò góc, kiểm từng ảnh, loại ngoại lai, bản đồ phủ, chuyển sang đa thức dự án, giao diện chụp,
  tiêu chí chấp nhận **đề xuất**.
- *Nguồn:* [HIEU_CHUAN_CAMERA.md](HIEU_CHUAN_CAMERA.md); [calibration/README.md](../calibration/README.md). *Mức:* TH.
- *Còn thiếu:* hiệu chuẩn camera thật nào cũng chưa có; ngoại tham đo chưa có; ROI cho camera dự án chưa dựng.
  `CameraCalibration.from_dict` chưa nạp thẳng được `cam_p*.json`, nhưng BEV không cần nó (dưới đây).
- *Tệp ngoại tham v0 (từ tối 24/09/2026):* [camera_rig_extrinsics_v0.json](../configs/rig/camera_rig_extrinsics_v0.json).
  Mọi tư thế trong đó là "GIẢ ĐỊNH — CHƯA ĐO". `load_rig()` của BEV ghép nội tham `calibration/cam_p<cổng>.json` (qua
  `fisheye_calib.load_intrinsics`) với tệp này mà không đi qua `from_dict` ([BEV.md](BEV.md) mục 4; 3.8b). Thiếu tệp nội
  tham thì nó từ chối. Nó mới chạy với tệp nội tham tạm trong test (`tests/test_bev.py`); chưa có tệp `cam_p*.json` thật
  nào.
- *Công cụ ngoại tham và ROI (từ khuya 24/09/2026, `65b7127`;* [NGOAI_THAM_VA_ROI.md](NGOAI_THAM_VA_ROI.md)*):*
  - *Viết được:* bảng in đặt nằm trên sàn ở vị trí đo bằng thước trong hệ xe. Góc bảng đánh số theo màu ô, vì OpenCV trả
    thứ tự ngược ở mọi ảnh tổng hợp đã thử. `cv2.fisheye.solvePnP` + tinh chỉnh theo điểm ảnh; gộp nhiều lần đặt, loại
    lần đặt lệch; chín phép kiểm (ngưỡng đề xuất). Kết quả ghi vào `configs/rig/camera_rig_extrinsics_v1.json` và đọc lại
    bằng chính hàm của BEV. ROI bằng đa giác "Loại"/"Giữ", nới 2 px. Kết quả từ nội tham tổng hợp không bao giờ được ghi
    như số đo.
  - *Mức:* TH (ảnh dò tia qua camera Kannala–Brandt đã biết; 29 + 19 test; kiểm đột biến 39/39).
  - *Giới hạn phải nói:* chưa đo camera nào. Sai số thước và sai số vạch hệ xe là nguồn sai số lớn nhất, chưa đo; trên ảnh
    tổng hợp, ±2,5 mm mỗi điểm làm hướng camera lệch tới 0,93° (20 lần bốc thăm). Camera thấp nên bảng chỉ dò được ở rất
    gần (0,05–0,30 m, script tạm). Ảnh lật gương chỉ bị bắt khi nhiều lần đặt không khớp. Mọi ngưỡng chưa chốt.

**3.10. Công cụ gán nhãn ảnh sa bàn**
- *Viết được:* nháp từ AI, cọ/đa giác, duyệt; chỉ ảnh đã duyệt vào cache. Split đóng băng theo phiên chụp (≤ 60 s là cùng
  phiên); `export --disjoint-from` giữ tập chấm tách rời. Quy tắc gán nhãn "phân vân thì IGNORE, không đoán FREE". Tập
  chấm cho khóa luận phải tô tay từ đầu (`--no-draft`) để tránh thiên lệch neo.
- *Nguồn:* [GAN_NHAN_SA_BAN.md](GAN_NHAN_SA_BAN.md). *Mức:* TH, thêm 8 ảnh thật chụp 23/09 lúc camera nằm trên bàn, chỉ để
  thử nhập/export.
- *Hai chốt chống rò rỉ tập chấm (từ khuya 24/09/2026, `77eb51f`):*
  - `labels import --exclude`: không nhập khung trùng sha256, tên bộ ảnh hay giờ chụp với một dự án/cache khác;
  - `evaluate.py --train-overlap refuse`: mặc định từ chối chấm khi ảnh chấm trùng train của checkpoint hoặc không kiểm
    được.

  Cả hai kiểm bằng dữ liệu giả (TH); riêng phần so manifest của `evaluate.py` đã chạy trên dữ liệu thật (DL). Kết quả phần
  đó: WoodScape val sạch (0 trùng với 5.764 ảnh train); AVM-SS val của `ai_ws_avm` là split chọn checkpoint của chính nó
  (1.050/1.050 ảnh; xem 4.3). Ảnh gần trùng khác sha256, chụp ở hai phiên cách nhau > 60 s, vẫn lọt. Nguồn:
  [GAN_NHAN_SA_BAN.md](GAN_NHAN_SA_BAN.md) mục 2 bước 7; HUAN_LUYEN cuối mục 8.
- *Giới hạn phải nói:* chưa gán nhãn ảnh thật nào; tốc độ gán nhãn chưa đo. Nhãn sửa từ nháp của mô hình WoodScape có chịu
  điều khoản Valeo không thì **chưa đánh giá**: quyết định giấy phép ngày 25/09 chỉ nói về dùng mô hình trong vòng điều
  khiển, chưa nói về nhãn nháp. GIAY_PHEP_DU_LIEU.md đề xuất (chưa chốt) nhập ảnh huấn luyện bằng `--no-draft` ngay từ
  đầu, để phương án huấn luyện lại không dính WoodScape vẫn dùng được.

**3.11. Hợp nhất cảm biến và cầu nối vào phiên**
- *Viết được:* các lớp `StaticMap`, `LiveLidar`, `CameraSemantic`, `NearField`; quy tắc hợp nhất; ngăn LiDAR trong cửa sổ
  đỗ xe. Năm quy tắc rút ra khi chạy với LiDAR thật: bền vững 2/3 vòng, mặt nạ thân xe, hành lang quỹ đạo, bản đồ thời gian
  thực, cảm biến cố định thì tư thế cố định.
- *Thêm từ khuya 24/09/2026, chỉ với nguồn giả:*
  - demo dòng lệnh bỏ ≥ 22 vòng khởi động, có thêm `--warmup` giây ([GIAI_DOAN_3_CHUAN_BI.md](GIAI_DOAN_3_CHUAN_BI.md)
    mục 2; `a7cec5e`); chưa chạy với C1 thật;
  - cầu nối `VehicleTelemetry` → `NearFieldReading` với bảng gá ToF giả định `configs/tof_mounts_v0.json` (`6db5087`). Một
    ToF không dùng được chỉ mất cung của nó; lớp gần xe không bao giờ đánh dấu FREE. ToF chưa vào phiên
    ([GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 12).
- *Nguồn:* [GIAI_DOAN_3_CHUAN_BI.md](GIAI_DOAN_3_CHUAN_BI.md) mục 1–5. *Mức:* MP + BT (LiDAR đứng yên).
- *Giới hạn phải nói:*
  - ToF chỉ có số đo giả. Giao thức v1 không phân biệt "không có vật trong tầm" với "ToF hỏng".
  - Bỏ 15 vòng đầu chưa phủ hết pha khởi động mô-tơ (ghi chú 24/09); bản bỏ ≥ 22 vòng chưa chạy với C1 thật.
  - Lớp camera: từ đợt AI camera 25/09/2026, BEV đã vào hợp nhất ở mức phần mềm (3.11b). Khung thật mới đi qua ở dạng phát
    lại bản ghi o03, và mọi lô bị chặn.
  - Định vị: bản đầu ghi "chưa có định vị". Tối 24/09 đã có bộ định vị trên bản đồ tĩnh (3.6b) nhưng chưa nối vào hợp
    nhất. Từ 02/10/2026 nguồn tư thế LiDAR đã nối vào phiên ở mức MP (1.6).

**3.11b. AI camera làm nguồn vật cản trong phiên đỗ xe** *(thêm ở đợt AI camera 25/09/2026, `b01dea4`; kế hoạch giai
đoạn 3, 8, 9)*
- *Viết được — luồng dữ liệu:* luồng 4 camera (hay bản ghi phiên) → `Rig`/`AIWorker` của bàn thử → lô AI mới nhất → chặn
  nếu BEV không dùng được → BEV hệ xe → đặt vào lưới sa bàn theo tư thế → lọc ≥ 2 trong 3 lô → `CameraSemanticLayer` → hợp
  nhất → `ObstacleBridge` riêng (tiền tố `camera_ai`) → phiên đỗ xe. Khi đặt vào lưới sa bàn, mỗi ô lấy mẫu 3 × 3 điểm,
  nên không mất ô vật cản khi xoay; đổi lại vật phình tối đa một ô.
- *Viết được — quy tắc:*
  - **AI chỉ thêm vật cản**, không xóa vật của LiDAR hay người dùng; FREE của camera không mở đường.
  - Lúc chạy, hộp AI mới chạm hành lang quỹ đạo → MAP_CHANGED, xe dừng và chờ lập lại đường.
  - Điều kiện chặn: nội tham đạt, ngoại tham đo, có ROI, không tổng hợp, đúng cỡ khung. Lý do chặn báo theo trình tự nội
    tham → ngoại tham → ROI.
  - Mặt nạ thân xe trên BEV hệ xe và trong hệ bản đồ, ở tư thế của từng lô.
  - AI cũ lúc chạy: mặc định chỉ cảnh báo; tích "AI bắt buộc" thì dừng.
  - Hai cách đặt camera: cố định trên bàn, hoặc gắn trên xe.
  - Không có `--camera-ai` thì cửa sổ như trước (phương án dự phòng chỉ LiDAR).
- *Nguồn:* [AI_DIEU_KHIEN_XE.md](AI_DIEU_KHIEN_XE.md); [autopark/fusion/camera_ai.py](../autopark/fusion/camera_ai.py),
  [autopark/ui/camera_dock.py](../autopark/ui/camera_dock.py); quyết định giấy phép ở
  [GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md).
- *Mức:* **TH**: camera giả, rig bốn camera tổng hợp, tệp hiệu chuẩn viết tay; 68 mục test; đột biến 46/46 (AI_DIEU_KHIEN_XE
  mục 8.1). Cộng thêm phát lại một bản ghi **BT** với mô hình thật (o03, cảnh tối, không phải sa bàn): với rig thật, 1163
  lô bị chặn, 0 vật cản; với rig tổng hợp, tối đa 22 hộp ở vị trí vô nghĩa.
- *Hình:* chưa có hình nào trong repo hay `docs/evidence/`. Ảnh chụp màn hình ngăn khi phát lại có thể tạo lại bằng lệnh ở
  AI_DIEU_KHIEN_XE mục 7 (lệnh 2, 3; không mở thiết bị).
- *Còn thiếu:*
  - hiệu chuẩn nội tham, ngoại tham đo, ROI; không có thì AI không tạo vật cản nào;
  - chạy với camera thật đang mở;
  - chấm AI trên ảnh sa bàn có nhãn để chốt `t_blocked` 0,15, lọc 2/3, tuổi 0,5 s, lề 5 cm (mọi số là đề xuất, chưa chốt);
  - đo độ trễ từ lúc vật xuất hiện tới lúc xe dừng, sai số vị trí hộp AI, tỉ lệ báo giả/bỏ sót;
  - laptop; xe.
- *Giới hạn phải nói:*
  - Quyết định giấy phép theo cách đọc A, **Valeo chưa xác nhận** (mục 1, ý 4). Ô "Mô hình" nhận cả checkpoint có AVM-SS
    mà quyết định giấy phép không phủ.
  - AI chưa từng được chấm trên ảnh sa bàn. Ngưỡng 0,15 đổi lấy ít bỏ sót nhưng nhiều báo giả, nên có thể dừng giả.
  - BEV giả định sàn phẳng. AI không bù chỗ bỏ sót; chỉ LiDAR bảo vệ. Vật trong lề quanh xe vô hình với AI.
  - Ngăn chỉ xét lô mới nhất mỗi 50 ms. "Camera gắn trên xe" không nội suy tư thế về lúc chụp; sai số do đó chưa đo.
  - Phát lại bản ghi phiên chỉ cấp ảnh, nên LiDAR và AI không cùng cảnh.
- *Câu nên viết:* "Phần mềm đưa AI của bốn camera vào phiên đỗ xe như một nguồn vật cản phụ bên cạnh LiDAR; mới kiểm bằng
  nguồn giả, rig tổng hợp và phát lại một bản ghi; chưa camera nào được hiệu chuẩn nên trên bàn thật AI chưa tạo vật cản
  nào; việc dùng mô hình WoodScape trong vòng điều khiển dựa trên cách đọc điều khoản chưa được Valeo xác nhận."

**3.12. Giao thức xe, `VehicleIO`, firmware ESP32-S3**
- *Viết được:* bảy loại thông điệp, bố cục byte, phiên/số thứ tự. Thời hạn lệnh: laptop gửi 150 ms, bo kẹp ≤ 300 ms.
  Watchdog bo 500 ms → DISARMED; `TELEMETRY_STALE` của laptop 0,3 s có chốt; trần effort 250 ‰ (chưa chốt); lỗi STALL.
  Hai nhánh `VehicleIO` đi qua cùng byte; vector mẫu chung Python ↔ C++. Từ tối 24/09/2026 `SerialVehicleIO` có
  `poll(block=False)` và đồng hồ mặc định là `time.perf_counter`, vì trên Windows `time.monotonic` chỉ đổi mỗi 15,625 ms.
- *Nguồn:* [GIAO_THUC_XE.md](GIAO_THUC_XE.md); [firmware/esp32_vehicle/README.md](../firmware/esp32_vehicle/README.md).
  *Mức:* MP (Python; lõi C++ qua test host; bản build trong bo ảo QEMU từ 30/09/2026); TK (lớp dán trên chip: LEDC,
  E-stop, watchdog kích hoạt, USB-CDC).
- *Giới hạn phải nói:*
  - Firmware C++ **chưa nạp, chưa chạy trên bo**. Ngày 29/09/2026 nó biên dịch được cho ESP32-S3 bằng PlatformIO, 0 cảnh
    báo; lõi `src/core` khớp bản Python qua test host trên máy tính, 703 check. Từ 30/09/2026 bản build thật chạy trong bo
    ảo QEMU với phần mềm laptop ([MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md)). Bo ảo không có LEDC, GPIO vào, task
    watchdog kích hoạt, USB-CDC thật, nên không phải bằng chứng về bo.
  - Chân GPIO, xung ESC/servo, hành vi ESC khi mất xung và khi lùi đều chưa chốt.
  - `VehicleIO` đã nối vào phiên đỗ xe và bộ bám từ tối 24/09/2026, nhưng **chỉ với bo mô phỏng và cổng serial giả**
    (3.12b). GIAO_THUC_XE mục 12 ghi dòng cũ "chưa nối `VehicleIO` vào `session.py`, chưa ghi
    `commands.csv`/`telemetry.csv`" là lỗi thời ngay tại chỗ.
  - GIAO_THUC_XE mục 12 còn ghi hai điều phải nói. (a) Khoảng trống an toàn khi `Heartbeat` giữ liên lạc lúc vòng điều
    khiển treo: tìm thấy và sửa trên mô phỏng ngày 24/09, còn một khoảng hở suy ra từ mã; chi tiết ở 3.12b. (b)
    `export_run`/`replay_run` từng từ chối lần chạy qua `VehicleIO` (`ReplayNotSupported`,
    `tests/test_run_store_vehicle.py`); từ 02/10/2026 lời từ chối được thay bằng phát lại log (T9, MP).

**3.12b. Nối `VehicleIO` vào phiên đỗ xe; chế độ quan sát** *(thêm tối 24/09/2026; kế hoạch mục 9, giai đoạn 5 và 9)*
- *Viết được:*
  - Ba chế độ: `SIM` (mặc định, giữ nguyên hành vi giai đoạn 0); `VEHICLE_IO` (mỗi nhịp 50 Hz một COMMAND có thời hạn
    0,15 s); `OBSERVE` (người lái; phần mềm tính lệnh nhưng **không gửi COMMAND nào**, bo phải ở DISARMED). Thế giới gương
    chỉ kiểm va chạm hình học, không tích phân lệnh.
  - Kiểm trạng thái thật trước START: 3 khung telemetry mới nhận sau lúc bấm, xe đứng yên, tư thế mới ≤ 0,15 s, lệch điểm
    xuất phát ≤ 3 cm và ≤ 5°, không chạm vật cản. Sau đó ARM (hoặc DISARM ở chế độ quan sát), rồi kiểm lại tư thế.
  - Dừng an toàn mỗi nhịp (`STALE_TELEMETRY`, `NO_MEASURED_STATE`, `STALE_POSE`) và theo sự kiện của bo. Chưa xác nhận xe
    đứng yên sau 2,0 s thì FAULT `STOP_NOT_CONFIRMED`.
  - Bảy quy tắc an toàn, ví dụ: quan sát không bao giờ gửi COMMAND; đã dừng thì không chạy tiếp; chỉ START mới ARM; vòng
    điều khiển không đọc chặn và theo đồng hồ io; đóng phiên gửi enable=0 rồi DISARM.
  - Ô chọn nhánh chạy trong giao diện.
  - Tệp log: lúc đầu năm tệp. Từ 02/10/2026 (mức MP) là tám tệp: thêm `board_actions.csv` của nút "Xóa lỗi bo
    (CLEAR_FAULT)" (T15), `poses.csv` và `clock.csv` là băng phát lại log (T9). `events.csv` có dòng `session_stop` cho mọi
    quyết định dừng của phiên và cột `t_perf` (T13). Nguồn: [CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) mục 5, 6.
- *Nguồn:* [CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) mục 1–6, 8, 9; [GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 12;
  `application/vehicle_link.py`, `application/session.py`.
- *Mức:* MP. Chuỗi kiểm là `Session` → `VehicleLink` → `SimVehicleIO` → byte giao thức → `FirmwareModel` → `SimVehicle`;
  ba test đồng hồ dùng `SerialVehicleIO` với cổng serial giả. Số ở 4.8.
- *Còn thiếu:* ESP32-S3, MN300, mã đọc encoder và AS5600; nguồn tư thế thật, tức định vị LiDAR cùng đồng hồ với
  `VehicleIO.now()` (từ 02/10/2026 có ở mức MP với LiDAR mô phỏng, 1.6); cách đấu dây ở chế độ quan sát (ESC nối máy thu
  RC hay nối ESP32: chưa chốt); phép thử trên bo thật cho bản sửa khoảng trống an toàn (dưới). Hai việc trong danh sách
  gốc đã có:
  - lựa chọn cổng serial trong giao diện: có ở mức giao diện từ khuya 24/09 (thẻ "Bo điều khiển", cuối mục này);
  - replay cho lần chạy qua `VehicleIO`: tối 24/09 `export_run`/`replay_run` nhận ra khóa `vehicle_link` và từ chối rõ
    (`ReplayNotSupported`, `tests/test_run_store_vehicle.py`), bằng chứng của lần chạy là log `VehicleLink.write_logs`.
    Từ 02/10/2026 (T9, mức MP) lần chạy này xuất gói và phát lại được bằng log: chạy lại cùng phần mềm trên đầu vào đã
    ghi và so quyết định ([CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) mục 5.1).
- *Giới hạn phải nói:* tư thế là `SimTruthPose`, tức **định vị lý tưởng**, nên kết quả bám đường không nói gì về sai số
  định vị thật. Chế độ quan sát không chứng minh xe bám được lệnh (kế hoạch mục 13). Lớp nối không thay đường cắt động lực
  phần cứng. Mọi ngưỡng `LinkParams` chưa chốt.

*Khoảng trống an toàn khi có `Heartbeat` (mức MP).* Phần này kể theo thứ tự thời gian: lỗi tìm thấy tối 24/09/2026, sửa
muộn tối cùng ngày (`c43e8d3`), và còn một khoảng hở suy ra từ mã. Nguồn: [GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 12.

- *Lỗi tìm thấy trên mô phỏng, ở nhánh `VEHICLE_IO`:*
  - Khi có luồng `Heartbeat` chạy cạnh phiên (vẫn PING và đọc telemetry) mà vòng điều khiển treo lâu hơn hạn lệnh 0,15 s,
    bo về ARMED (`COMMAND_TIMEOUT`). Telemetry vẫn mới nên chốt `TELEMETRY_STALE` không bật.
  - Nếu bước 5 ms đầu tiên sau khi hết treo là nhịp điều khiển, phiên gửi **một** COMMAND enable=1 trước khi lấy sự kiện
    `VEHICLE_STOPPED`, vì lớp nối chỉ gom sự kiện trong `pump()`, chạy sau nhịp điều khiển. Bo ARMED → RUNNING thêm một
    lần; nhịp sau phiên mới dừng và gửi enable=0.
  - Lúc đó test `test_command_timeout_while_heartbeat_keeps_link_stops_and_never_resumes[0]` được đánh dấu
    `xfail(strict=True)` (pha 1–3 đạt).
  - Suy ra từ mã: `OBSERVE` không bao giờ gửi COMMAND nên không gặp lỗi này; chưa có test riêng cho `OBSERVE` + treo +
    `Heartbeat`.
  - Phiên hiện không dùng `Heartbeat`. Khi không có luồng nào đọc cổng lúc treo, 8 trường hợp (treo 0,3 s và 1 s × 4 pha,
    cổng serial giả) đều dừng và không có lệnh enable nào.
- *Effort trên mô hình bo trước bản sửa:* trên bo mô phỏng và cổng serial giả, enable=0 tới cùng mili giây với enable=1 nên
  effort vẫn 0. Nhưng điều đó chỉ đúng khi lệnh dừng tới **cùng mili giây**. Test mới cho bo chạy thêm 10 / 20 / 40 ms
  trước khi lệnh dừng tới, như thời gian tính và trễ USB trên máy thật: trước bản sửa, mô hình bo đưa effort lên 107 / 115
  / 130 ‰. Đây là số của mô hình bo (`FirmwareModel`, cổng serial giả, đầu vào đứng yên), không phải số đo.
- *Bản sửa muộn tối 24/09/2026 (`c43e8d3`; bo mô phỏng và cổng serial giả, chưa thử trên ESP32-S3 thật):* sửa hai lớp.
  1. `VehicleLink.refresh()` mới. `Session._step_closed_loop` gọi nó ở đầu mỗi bước khi đang RUNNING, trước nhịp điều
     khiển. Với bo thật nó gọi `poll(block=False)` (chỉ byte đã có); với bo mô phỏng nó gọi `VehicleIO.take_new()` mới
     (chỉ lấy telemetry đang chờ, không tiến I/O hay đồng hồ mô phỏng). Sau đó gom sự kiện.
  2. Trong `VehicleLink.command()`: còn sự kiện dừng chưa được phiên lấy thì không gửi gì, trả `HALTED`.
- *Test sau bản sửa:* `tests/test_session_vehicle.py` có 60 test, 60 đạt, 0 `xfail` (chạy lại riêng tệp tối 24/09, máy
  bàn, `.venv`).
  - Hai trường hợp `xfail` strict cũ nay đạt: pha 0 của
    `test_command_timeout_while_heartbeat_keeps_link_stops_and_never_resumes` và
    `test_vehicle_io_command_timeout_after_freeze_by_phase`.
  - Hai test từng ghi lại hành vi lỗi được viết lại và đổi tên: `test_resume_after_hang_sends_no_enable_to_the_sim_board`,
    `test_resume_after_hang_keeps_effort_zero_whatever_the_gap_before_the_stop[0/10/20/40]`. Sau khi hết treo không có
    enable=1 nào, effort 0 ở mọi khoảng trễ.
  - Test mới `test_command_refuses_enable_while_a_stop_event_is_pending`.
  - Đột biến: bỏ lời gọi `refresh()` thì 7 test hỏng; bỏ lớp chặn thứ hai thì test mới hỏng.
- *Khoảng hở còn lại (suy ra từ mã, chưa có test):* bản sửa chỉ chặn được khi khung telemetry báo bo rời RUNNING **đã tới
  laptop**, vì `refresh()` chỉ thấy khung đã tới. Nếu bo vừa về ARMED (`COMMAND_TIMEOUT`) mà khung báo điều đó chưa tới
  (bo gửi telemetry mỗi 50 ms, cộng trễ USB), laptop vẫn có thể gửi **một** COMMAND enable=1 và bo ARMED → RUNNING.
  Khoảng hở này và effort khi đó trên bo thật chưa đo ([GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 12, đoạn "Giới hạn còn
  lại"; [CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) mục 4 quy tắc 2 và mục 8). Cách đóng khoảng hở bằng chốt phía firmware
  sau `COMMAND_TIMEOUT` (bo không nhận enable=1 tới khi có ARM mới) đổi hành vi firmware, nên **chờ người dùng duyệt,
  chưa làm**; không viết như đã có.
- *Giới hạn phải nói:* sửa và kiểm **chỉ trên mô phỏng**. Khoảng trễ giữa telemetry báo dừng và lệnh kế tiếp trên bo thật
  chưa đo. Phiên hiện vẫn không dùng `Heartbeat`. Không viết quy tắc "đã dừng thì không chạy tiếp" như điều đã chứng minh
  vô điều kiện.
- *Câu nên viết:* "Trong test mô phỏng, sau bản sửa ngày 24/09, phiên không gửi lại lệnh chạy sau khi laptop đã nhận khung
  telemetry báo bo dừng, kể cả khi vòng điều khiển treo quá hạn lệnh trong lúc liên lạc vẫn được giữ; còn một khoảng hở
  suy ra từ mã, chưa có test: bo vừa về ARMED mà khung báo điều đó chưa tới laptop (chu kỳ telemetry 50 ms cộng trễ USB);
  chưa thử trên bo thật."

*Thẻ "Bo điều khiển" và so giới hạn bo (khuya 24/09/2026, `6db5087`).* Mức MP: bo mô phỏng, `FirmwareModel` sau cổng
serial giả, `comports` giả; chưa mở cổng thật nào. Nguồn: [CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) mục 3, 6–8;
[GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 7, 10, 12.

- *Viết được:*
  - Thẻ "Bo điều khiển" chọn bo mô phỏng hay cổng COM; liệt kê cổng mà không mở cổng.
  - Chọn cổng thật thì START luôn bị từ chối trước khi mở cổng (`START_NO_POSE_SOURCE`), vì chưa có nguồn tư thế thật và
    `SimTruthPose` không bao giờ được ghép với bo thật.
  - "Kiểm kết nối bo": HELLO, so giới hạn, đọc 5 khung telemetry, đóng cổng; không ARM, không COMMAND.
  - So sáu giới hạn trong HELLO_ACK với `VehicleConfig` theo bảng hướng nguy hiểm (với giảm tốc, nguy hiểm là bo **thấp**
    hơn); lệch nguy hiểm thì từ chối START ở `VEHICLE_IO`.
- *Số:* `tests/test_vehicle_board_ui.py` 30 test, `tests/test_nearfield_tof.py` 54 test, 15 test thêm vào
  `tests/test_transport_vehicle_io.py` (nay 64). Chạy chung 19 tệp liên quan: 505 đạt, 0 lỗi; kiểm đột biến 50/50.
- *Giới hạn phải nói:*
  - Chưa thử với ESP32-S3; mở cổng có làm bo khởi động lại qua DTR/RTS không thì cần tra.
  - Chọn nhầm cổng LiDAR thì HELLO tới C1; phản ứng của C1 chưa kiểm.
  - Chính sách so giới hạn là đề xuất, chưa chốt, và so với cấu hình chứ không với đường đã lập.
  - `begin_run` chưa có bước mở cổng.
  - Sự kiện dừng của phiên trong log (T13 ở [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 7): lúc đầu chưa có. Từ
    02/10/2026 mọi quyết định dừng của phiên vào `events.csv` thành dòng `session_stop` kèm `t_perf`. Bằng chứng mới ở mức
    mô phỏng (bo mô phỏng, cổng serial giả), chưa thử với bo ảo QEMU hay ESP32-S3 qua phiên. Cùng ngày có nút "Xóa lỗi bo
    (CLEAR_FAULT)" (T15), cũng chỉ ở mức MP.

**3.13. Nguồn và dừng an toàn**
- *Viết được:* các tình huống mất liên lạc, rút cáp, treo chương trình, bo khởi động lại đã viết trong đặc tả; cách đấu ngõ
  vào E-stop an toàn khi hở mạch (tiếp điểm NC nối GND, điện trở kéo lên) — đã chọn, chưa lắp.
- *Nguồn:* GIAO_THUC_XE mục 0, 5, 6, 12; kế hoạch mục 10. *Mức:* TK.
- *Bản nháp (từ tối 24/09/2026, TK):* các đầu ra kế hoạch gọi là bảng tải điện (`power_budget.md`), sơ đồ nguồn, sơ đồ
  dừng nay có bản nháp trong [GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md):
  - bảng tải P1–P14; chỉ C1 có số datasheet, tổng theo nhánh **chưa cộng được** (mục 1);
  - sơ đồ nguồn hai miền logic/USB và động lực (mục 2, mermaid);
  - sơ đồ dừng ba đường phần cứng / firmware / laptop và bảng các đường dừng (mục 3);
  - ba phương án phần tử mà LA38 cắt, chưa chốt (mục 3.2);
  - bảng thao tác cần làm để chạy lại sau từng sự kiện (mục 3.3); bảng định mức còn phải kiểm (mục 4);
  - 16 kịch bản thử lỗi (mục 5, xem 4.11).
- *Còn thiếu:* chọn UBEC/XL4015, cầu chì, phần tử ngắt và các quyết định N1–N7 (GIAI_DOAN_6_CHUAN_BI mục 2.1, 6); mọi phép
  đo và phép thử phần cứng.
- *Giới hạn phải nói:* ngõ vào E-stop của firmware **không thay** đường cắt động lực phần cứng. Sơ đồ nguồn/dừng hiện là
  bản nháp thiết kế, chưa có phần cứng nào; mô phỏng `VehicleIO` **giả định** E-stop cắt động lực
  (`actuator.estop_cuts_power: true`).

**3.14. Công cụ đo, kiểm thử và tái lập**
- *Viết được:* `lidar.bench`, `video.camera_bench`, `rig.bench`, `rig.may_moi`; pytest, chiến dịch theo seed, coverage,
  replay; kiểm thử đột biến (phạm vi đúng ở M.4); mọi số đo có tệp kèm ngày và máy.
- *Nguồn:* các tài liệu trên, mục "Cách chạy"; [MAY_NOP_DO_AN.md](MAY_NOP_DO_AN.md) mục 3.
- *Ghi và phát lại phiên bàn thử (từ tối 24/09/2026;* [GHI_PHAT_LAI_BAN_THU.md](GHI_PHAT_LAI_BAN_THU.md) *mục 1–4):*
  - Lệnh và giao diện: `rig.bench --record` / `--replay`, nút "Ghi phiên" và `--replay` của `rig_app`.
  - Bản ghi giữ mọi khung tốt (JPEG q95 hoặc PNG), sự kiện khung hỏng có stamp và nguyên văn, mọi vòng LiDAR, `meta.json`.
  - Phát lại đổi gốc stamp, giữ khoảng cách giữa khung và giữa nguồn, ném lại sự kiện khung hỏng đúng lúc. Nó chỉ bắt đầu
    sau khi AI nạp mô hình và làm nóng xong (hoặc nạp lỗi).
  - Công dụng: chạy **hai quy tắc trên cùng một dữ liệu**, điều không làm được trên phần cứng; phát triển BEV và định vị
    trên dữ liệu thật.
  - Lỗi ghi không bị bỏ qua im lặng: khung bị bỏ được đếm, đĩa đầy thành `LỖI`, bench trả mã 1.

  Phương pháp dùng ở 4.1, số ở 4.6b.
- *Công cụ khác từ tối 24/09/2026:* `python -m autopark.perception.bev` (`synthetic` / `snapshot` / `woodscape`),
  `python -m autopark.lidar.localize` (`--track`, `--global`). Kiểm đột biến có cho cả bốn việc mới: BEV 23 đột biến,
  ghi/phát lại 12 + 15, định vị 12 + 30, phiên `VehicleIO` 6 + 27 (con số và ngoại lệ ở từng tài liệu). Quy tắc ghép theo
  nhịp riêng cũng có kiểm đột biến (GIAI_DOAN_2_BAN_THU mục 10.2).
- *Công cụ khác từ khuya 24/09/2026:*
  - `evaluation.sensitivity` (`10a4735`): độ nhạy theo kích thước xe, chấm độc lập với planner; `scene_digest` bảo đảm sa
    bàn không đổi giữa các biến thể;
  - `evaluation.hard_cases --witness-out` (`10a4735`): sinh và kiểm đường chứng;
  - `perception.bev bench` (`65b7127`);
  - `rig.may_moi --steps` (`77eb51f`): tóm tắt lại thư mục kết quả, cảnh báo khi hai cột không cùng quy tắc ghép hay tham
    chiếu có trước làm nóng AI;
  - `--vehicle-config` cho `robustness`/`phase0`/`ui.lidar_app` (`10a4735`).

  Mọi việc của đợt khuya có biên bản kiểm đột biến (số ở từng tài liệu). Ví dụ: ngoại tham/ROI 39/39, BEV tăng tốc 20/20 và
  `max_range` 8/8, thẻ bo và ToF 50/50, độ lặp lại LiDAR 19/19, demo hợp nhất 6 + 6, nhãn ca khó 19. Odometry khớp scan
  34/36; hai đột biến sống sót được ghi rõ ở SO_SANH_DINH_VI_SLAM mục 3.7.
- *Còn thiếu:* khai báo công cụ AI (mục 1, ý 10).
- *Lưu ý khi viết lệnh:* ví dụ lệnh trong khóa luận nên viết trên **một dòng**. Người dùng gõ lệnh trong cmd.exe, nơi dấu
  nối dòng `\` của bash và `` ` `` của PowerShell đều không dùng được.

### Chương 4. Thực nghiệm và đánh giá

**4.1. Phương pháp đánh giá**
- *Viết được:* ba mức bằng chứng và nhãn ở phần 0; mỗi số là của một phiên cụ thể trên một máy cụ thể; stamp là lúc dữ
  liệu tới máy; tách hai loại lỗi AI; "dừng an toàn" khác "hoàn thành đỗ".
- *Ghi mọi lần thử và phân loại nguyên nhân lỗi (kế hoạch 14 ý 4, 6):* mỗi lần thử ghi một kết quả: COMPLETED, dừng bảo
  vệ, FAULT, lỗi liên lạc, hoặc can thiệp của người giám sát. Lần nào không COMPLETED thì gán đúng một trong 9 nhóm nguyên
  nhân: ảnh/AI, định vị, hình học, planner, control, cơ khí, nguồn, liên lạc, đích không hợp lệ. Báo cáo mọi lần thử, không
  chỉ lần thành công (kế hoạch 14 "Mục tiêu cần đạt": "Không chỉ chọn các lần demo thành công"). Đã có ở mức MP: 240 phiên
  kín vòng của chiến dịch 20/09 có trạng thái, sự kiện chèn và lý do dừng từng phiên
  (`runs/robustness_final_2026-09-20/cases.jsonl`, git-ignore), có thể phân loại lại theo 9 nhóm. Ở mức XT: chưa có.
- *Còn thiếu:* ngưỡng nghiệm thu (16.2), bộ kịch bản nghiệm thu (16.3), cách đo độc lập và định nghĩa thành công/thất bại.
  Các thứ này **phải chốt trước khi thu kết quả cuối** (kế hoạch mục 14, đoạn "Khi chưa đủ bộ xe" ở bản `9d68257`, nay là
  đoạn "Khi chờ"). Cần thêm mẫu biên bản lần thử có cột kết quả, can thiệp và nhóm nguyên nhân. Việc duyệt là việc 7 ở
  mục 7.
- *Bản đề xuất nghiệm thu (khuya 24/09/2026, `54cb3e2`; mức TK, chưa chốt):*
  - [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md): 37 kịch bản trong 9 nhóm; bảy phương pháp đo độc lập R1–R7 (camera
    trên cao là chính, kiểm nó bằng "xe giả" TC-1); gói dữ liệu GD1–GD6; mẫu biên bản có cột kết quả, can thiệp và nguyên
    nhân.
  - [NGUONG_NGHIEM_THU_DE_XUAT.md](NGUONG_NGHIEM_THU_DE_XUAT.md): mã ngưỡng N-… kèm căn cứ; quy tắc "tham chiếu chính xác
    hơn ngưỡng ≥ 3 lần" và "số thời gian đo trên đúng máy nghiệm thu".
  - Từ 02/10/2026 công cụ của tham chiếu R1 (T4) đã có, mới kiểm trên ảnh tổng hợp; chưa có số đo R1 hay TC-1 thật
    ([THAM_CHIEU_TREN_CAO.md](THAM_CHIEU_TREN_CAO.md)).

  Mục này viết được **phương pháp** từ hai tệp đó sau khi được duyệt; khi chưa duyệt, chỉ ghi là đề xuất.
- *Kế hoạch đo khác đã soạn nháp (tối 24/09/2026, TK):*
  - bảng đo MN300 B0–B8 và thứ tự đo khi nhận xe ([GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md) mục 3, 7);
  - phép thử độ nhạy planner với sa bàn cố định (mục 5.3); khuya 24/09 đã chạy hai lượt mô phỏng, xem 4.11;
  - 16 kịch bản thử lỗi nguồn/dừng L1–L16 theo năm mức thử R, M0–M3 ([GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md)
    mục 5).

  Chúng là **kế hoạch đo**, không phải ngưỡng 16.2 hay bộ kịch bản nghiệm thu 16.3. Tiêu chí trong GIAI_DOAN_6 mục 5 ghi
  là "đề xuất", tính từ tham số thiết kế. Ví dụ: xung ESC về trung tính trong T ≈ 0,43 s sau lệnh cuối ở 0,15 m/s; công
  thức này chỉ nói về xung, không nói về quãng dừng thật.
- *Phát lại làm phương pháp thử (từ tối 24/09/2026):* ghi một phiên bàn thử một lần rồi phát lại nhiều lần qua cùng mã, để
  so hai quy tắc hay hai phiên bản mã **trên cùng một dữ liệu** thật (3.14). Khi dẫn số của một phiên phát lại phải nói kèm
  năm giới hạn ([GHI_PHAT_LAI_BAN_THU.md](GHI_PHAT_LAI_BAN_THU.md) mục 5):
  1. stamp đã đổi gốc, nên chỉ so khoảng cách và độ lệch, không so giá trị tuyệt đối;
  2. JPEG mã hóa lại làm pixel đổi (sai khác trung bình 0,85–1,24 mức xám trên 8 ảnh 23/09), nên kết quả AI không trùng
     từng bit;
  3. bộ dò khung hỏng đã chạy lúc ghi; khung lọt bộ dò nằm trong bản ghi như khung tốt;
  4. phát lại không tái tạo tranh chấp USB, DirectShow, giải mã MJPEG của driver, nên CPU/GPU/thời gian AI của phiên phát
     lại không thay số đo trực tiếp;
  5. ở speed ≠ 1, kết quả ghép bộ không so được với phiên gốc.

  Phát lại vì vậy dùng để so **thuật toán**, không thay phép đo trên thiết bị.
- *Phát lại log lần chạy qua `VehicleIO` (từ 02/10/2026, T9, mức MP):* dùng để kiểm quyết định của phần mềm trên một lần
  chạy đã ghi. Công cụ chạy lại cùng mã trên đầu vào đã ghi (telemetry, sự kiện, tư thế, đồng hồ io của từng lần đọc) rồi so
  lệnh, sự kiện dừng, kết quả với bản ghi. Mã thoát: 0 = KHỚP, 1 = KHÁC, 2 = gói không phát lại được, 3 = lỗi bất ngờ. Câu
  viết được: "cùng đầu vào + mã này → cùng quyết định". Nó không tái hiện xe, bo hay cảm biến và không thay phép đo trên xe;
  mới kiểm với bo mô phỏng và cổng serial giả ([CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) mục 5.1).

**4.2. Mô phỏng giai đoạn 0 — MP, laptop i7-12700H, 20/09/2026**
- *Viết được:*
  - 220/220 test.
  - Chiến dịch 2.880 ca, 0 vi phạm bất biến: 2.000 ca tư thế/hình học, 600 chuyển động/vùng quét, 240 phiên kín vòng, 40
    lập đường + thực thi.
  - 240 phiên: 25 COMPLETED, 185 STOPPED, 30 FAULT (cố tình chèn vật quá gần). 40/40 bài planner có đường hợp lệ và chạy
    xong.
  - Coverage 93,93 % dòng / 84,25 % nhánh trên 10 mô-đun cốt lõi; toàn package 52,52 % / 38,11 %.
  - Năm phiên mẫu: parking COMPLETED sau 20,265 s, sai số vị trí cuối 8,92 mm; reverse 8,52 mm; noisy 4,78 mm; obstacle và
    data_loss STOPPED, không va chạm. Replay khớp.
  - Lượt test hồi quy đầu (trước sửa): 25 ca thất bại / 3 đạt.
- *Nguồn:* [BAO_CAO_GIAI_DOAN_0.md](../../BAO_CAO_GIAI_DOAN_0.md) mục 5–7; [KIEM_THU_DO_BEN_GIAI_DOAN_0.md](KIEM_THU_DO_BEN_GIAI_DOAN_0.md).
- *Hình/bảng:*
  - bảng mục 6.2, 7 của báo cáo; JUnit [robustness_pytest.xml](evidence/robustness_pytest.xml),
    [robustness_regressions_before.xml](evidence/robustness_regressions_before.xml);
  - [coverage_core.json](evidence/coverage_core.json) kèm JUnit của lượt đo coverage
    [robustness_coverage_pytest.xml](evidence/robustness_coverage_pytest.xml) (210 đạt, 10 bỏ chọn);
  - hai lượt thất bại [robustness_concurrent_load_pytest.xml](evidence/robustness_concurrent_load_pytest.xml) và
    [robustness_baseline_pytest.xml](evidence/robustness_baseline_pytest.xml). Cả hai là ca `uturn_w46` dùng hết ngân
    sách 8 s khi CPU bận: một TIMEOUT, một TRACKING_FAILED (đường tìm kịp trong ngân sách nhưng xe mô phỏng dừng ngoài
    dung sai). Đây không phải lỗi hồi quy, nhưng cũng không được trình bày là đạt;
  - video `runs/phase0_after_robustness/*/simulation.mp4` (git-ignore).
- *Còn thiếu:* chạy lại trên bản mã cuối và trên laptop, ghi commit (mục 1, ý 9); chạy lại với kích thước/giới hạn đo trên
  MN300 (giai đoạn 4).
- *Nhãn bộ ca khó (khuya 24/09/2026, `10a4735`; MP, máy bàn, dưới tải;*
  [KIEM_THU_DO_BEN_GIAI_DOAN_0.md](KIEM_THU_DO_BEN_GIAI_DOAN_0.md) *mục 6):*
  - Nhãn `expected` nay nói về sự tồn tại của đường trong mô hình planner. Nhãn `feasible` phải có đường chứng kiểm độc
    lập: tích phân lại từng cung, kiểm va chạm liên tục giữa các mẫu.
  - Cả 16/16 ca có đường chứng. `parallel_122` và `parallel_115` từng ghi `infeasible` (08/09), nay là `feasible`, với
    đường chứng ngắn 5 và 13 lần đổi chiều. TIMEOUT/NO_PATH của planner ở hai ca này và ở `zigzag_corridor` là giới hạn
    của planner (lề tìm kiếm, trần góc lái).
  - Hai trường hợp trong `tests/test_planner_hard_cases.py` từng khẳng định nhãn cũ nên hỏng. Ngày 25/09 chúng được sửa
    (trong `10a4735`): test đổi tên thành `test_ca_rat_chat_khong_bao_thanh_cong_gia`, nhãn `feasible`, planner được trả
    TIMEOUT/NO_PATH, nhưng báo OK thì đường phải qua kiểm độc lập. Lần chạy toàn bộ bộ test ngày 25/09 không còn test hỏng.
  - *Giới hạn phải nói:* "có nghiệm" khác "dùng được trên xe": đường planner cho `parallel_122` có 104–150 lần đổi chiều,
    nhiều nhịp dưới 2 cm. Mô hình cho phép đổi góc lái tức thời; kích thước xe giả định.
  - *Đối chứng âm:* nếu khóa luận dẫn "ca vô nghiệm" làm đối chứng âm thì phải đổi sang một ca có chứng minh (ví dụ ô bị đậy
    kín). Đối chứng âm hiện có trong bộ test là `tests/test_planning.py::test_walled_off_goal_reports_no_path`: có từ giai
    đoạn 0 (đã có trong JUnit 20/09 [pytest.xml](evidence/pytest.xml); trong git từ commit đầu `bef5695`, 21/09). Theo chú
    thích trong mã, tường chia đôi sa bàn; test chỉ đòi planner trả NO_PATH hoặc TIMEOUT. Đối chứng âm "có chứng minh"
    riêng chưa được thêm (TONG_HOP_DU_AN.md mục 5.4).
- *Giới hạn phải nói:*
  - Thông số xe giả định; miền tham số 0,7–1,4 lần kích thước chỉ là miền thử.
  - 25/240 COMPLETED **không phải tỉ lệ đỗ thành công**, vì chiến dịch cố tình chèn lỗi.
  - Tìm đường trong thời hạn phụ thuộc tải CPU và cách Windows xếp lịch tiến trình. Trên máy bàn hiện tại, `uturn_w46`
    hỏng cả khi máy gần rảnh nếu để Windows tự quyết EcoQoS (chế độ tiết kiệm của Windows 11 có thể hạ tốc tiến trình). Từ
    30/09/2026 `tests/conftest.py` tắt EcoQoS cho pytest; từ 02/10/2026 ứng dụng và công cụ đo cũng tự tắt. Nguồn:
    [KIEM_THU_DO_BEN_GIAI_DOAN_0.md](KIEM_THU_DO_BEN_GIAI_DOAN_0.md) mục 4; [CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 8,
    10.1.
  - Cờ dừng mô phỏng không chứng minh phanh hay E-stop.

**4.3. AI trên dữ liệu công khai — DL, máy bàn i9-14900 + RTX 4000 Ada, 21–23/09/2026**
- *Viết được:*
  - WoodScape test giữ riêng, chấm một lần (21/09): mIoU 0,9692; vật cản → FREE 1,75 %; theo camera (FV 1,21 %, RV 1,76 %,
    MVL/MVR 2,52 %); lỗi theo ảnh trung vị 1,27 %, p90 2,46 %, p99 6,56 %, tệ nhất 35,06 %.
  - Ba seed (22/09): test 0,9693 ± 0,0001, nên mọi khác biệt dưới 0,001 mIoU là nhiễu (ngưỡng này đo trên WoodScape test;
    trên ACDC độ lệch chuẩn theo seed là 0,005 mIoU, HUAN_LUYEN mục 16).
  - Ngoài miền (22/09), lượt nền **ba seed** (HUAN_LUYEN mục 16, 16.1, 17.1; dùng cho bảng chính): ACDC val thời tiết xấu
    mIoU 0,914 ± 0,005, vật cản → FREE 4,1 ± 0,4 % (đêm 8,4 ± 0,4 %); RoadObstacle21 (30 ảnh) recall 67,0 ± 2,3 %, ảnh
    thấy ≥ ½ vật 12 · 12 · 13 /30. Theo lớp gốc, bảng 16.1 (lớp đơn): car 10,8 ± 0,9 %, person 6,7 ± 0,1 %, bicycle
    25,0 ± 2,5 %, motorcycle 3,9 ± 0,4 %.
  - Riêng checkpoint **seed 20260920** (HUAN_LUYEN mục 8; chỉ để minh họa và đi kèm ảnh tốt/xấu nhất):
    - ACDC val_ref (trời quang) 0,966; chỉ seed này được chấm trên val_ref.
    - ACDC val 0,908, vật cản → FREE 4,42 % (đêm 8,38 %).
    - RO21 recall 68,3 %, vật cản → FREE 31,7 %, 11/30 ảnh không thấy vật.
    - Theo **nhóm** lớp của metrics.json (`per_source_class.groups`: vehicles / persons_and_riders / two_wheelers; khác
      các lớp đơn của bảng 16.1): xe 12,4 %, người 6,4 %, xe hai bánh 19 % bị gọi FREE.
    - Nếu cần số nhóm dạng ba seed: tính lại ngày 24/09 từ metrics.json ACDC của ba seed (tệp chấm 22/09) được 11,4 ± 1,2 /
      6,5 ± 0,05 / 18,9 ± 1,7 % (độ lệch chuẩn mẫu). Số này **chưa có trong HUAN_LUYEN**; dẫn thì ghi rõ "tính lại".
  - Ngưỡng 0,15 (chọn trên val theo F2):
    - ba seed (mục 17.1): vật cản → FREE trên ACDC 2,2 ± 0,2 % (báo động giả 7,6 ± 1,2 %), RO21 recall 79,9 ± 3,2 %;
    - chỉ seed 20260920 (mục 10): WoodScape test 0,69 % (hai seed kia chưa chấm test ở 0,15), ACDC 2,28 %, RO21 vật cản →
      FREE 18,2 %. Báo động giả trên WoodScape test tăng từ 1,37 % lên 3,09 %. Con số 3,97 % ghi trước 30/09/2026 là nhầm:
      đó là 1 − precision của lớp BLOCKED;
    - loss có trọng số lớp chỉ dịch điểm làm việc.
  - Thêm AVM-SS/ACDC (phần III): không lượt nào vượt lượt nền trên hai tập chưa chạm; trộn WoodScape + AVM làm vật cản →
    FREE trên ACDC tăng 4,1 ± 0,4 % → 13,5 ± 2,8 %; hai kết luận nháp đã rút lại.
  - Độ trễ một ảnh khi GPU rảnh: torch CUDA fp32 4,4 ms, onnxruntime CPU 7,6 ms (máy bàn).
  - Lỗi quan sát: ngược nắng/lóa gọi bó vỉa là FREE; vùng IGNORE cho đầu ra vô nghĩa (bắt buộc có ROI); nhãn gốc lỗi ở ảnh
    tệ nhất (thiếu polygon `ego_vehicle`).
- *Nguồn:* [HUAN_LUYEN.md](../../HUAN_LUYEN.md) phần I (mục 1, 2.8, 3), phần II (mục 8–12), phần III (mục 15–18).
- *Hình/bảng:* bảng mục 1, 2.8, 8, 9, 10, 16, 16.1, 17.1; ảnh tốt/trung bình/xấu nhất trong `runs/ai_woodscape_rtx4000_v1/eval_test/`,
  `eval_acdc_val/` (git-ignore; lưu ý giấy phép ảnh ở mục 4 của tệp này). Bảng AI chính của chương 4 dùng trung bình ±
  độ lệch chuẩn ba seed (mục 16, 16.1, 17.1). Số một seed (mục 8, 10) chỉ dùng minh họa và phải ghi "(seed 20260920)".
  Không đặt hai loại số cạnh nhau cho cùng một chỉ số mà không ghi nhãn.
- *RoadAnomaly21 (khuya 24/09/2026, `77eb51f`; DL, máy bàn;* [HUAN_LUYEN.md](../../HUAN_LUYEN.md) *cuối mục 8):* chấm trên
  10 ảnh `validation*` có nhãn, ba seed lượt nền. Vật bất thường → FREE 10,4 ± 1,2 % ở ngưỡng 0,50 và 5,5 ± 0,4 % ở 0,15;
  9/10 ảnh thấy ≥ ½ vật; gần hết lỗi nằm ở một ảnh (con hươu).
  - *Giới hạn phải nói:* chỉ pixel vật bất thường được chấm; nhãn 0 gồm cả nhà, cây, trời. Mô hình gọi BLOCKED ≈ 62 % pixel
    nền, nên recall cao không chứng minh nhận ra vật lạ. Không so được với bảng xếp hạng SMIYC; chỉ 10 ảnh; hồ sơ chưa nằm
    trong `runs/`.
- *AVM-SS val của lượt `ai_ws_avm`:* cũng từ đợt này, `evaluate.py` cho thấy số 0,913 / 8,7 % (HUAN_LUYEN mục 16) là **val
  dùng để chọn checkpoint của chính lượt đó** (1.050/1.050 ảnh), không phải tập chưa chạm. Nếu trích thì ghi rõ như vậy.
- *Còn thiếu:* **ảnh sa bàn có nhãn tô tay** và phép chấm ba checkpoint ở hai ngưỡng 0,50 và 0,15 (HUAN_LUYEN mục 18); đo
  trên laptop.
- *Giới hạn phải nói:*
  - Kết quả **trong phân phối**, trên split nội bộ. Split dựa trên timestamp + ảnh gần trùng, không có recording ID được xác
    nhận, nên **chưa loại trừ rò rỉ bối cảnh**.
  - Đây không phải split chính thức của tác giả nên không so được với số công bố. Thư mục `datasets/woodscape_metadata/` có
    các tệp `official_train/val/test.txt`, nhưng chưa tài liệu nào đối chiếu chúng; cần tra nếu muốn so.
  - 55 % pixel là IGNORE; RO21 chỉ 30 ảnh; huấn luyện không tái lập từng bit trên GPU; mô hình không phân biệt vỉa hè với
    đường; mọi số là của máy bàn.
- *Quan sát định tính được phép dẫn, kèm nhãn:* bộ ảnh camera thật đầu tiên (23/09, camera nằm trên bàn nhìn thảm hoa văn,
  **chưa có nhãn**). Lượt nền gọi BLOCKED 11 / 31 / 39 / 60 % pixel ở cổng 1–4 (ngưỡng 0,50). Nhìn bằng mắt, ở cổng 2–4 phần
  lớn là thảm, tức báo động giả. Đây không phải số đo so với nhãn.

**4.4. LiDAR RPLIDAR C1 trên bàn — BT, máy bàn, 22–24/09/2026**
- *Viết được:*
  - p07 (22/09, 17,8 s, không làm nóng): 10,09 Hz, trung vị 508 tia/vòng, 0 byte lệch trong 91.507 node. 34,6 % tia không
    phản hồi ở chỗ đặt đó; node đầu tới sau ≈ 2,2 s kể từ lệnh SCAN.
  - k01 (24/09, cùng serial, health OK): 151 vòng, 0 lỗi đọc, 9,98 Hz, trung vị 512 tia/vòng.
  - Bỏ 3 s đầu thì cả hai ngày ≈ 10,0 Hz, ≈ 510 tia/vòng.
  - Cộng 26 phiên 22–24/09: 33.932 vòng, 0 byte lệch, 0 vòng bị bỏ, 5 lần đóng vòng theo điểm góc.
  - Ba phiên 10 phút trên bàn thử: 6.006 / 6.005 / 6.006 vòng, 0 vòng mất.
  - Bản đồ lưới tĩnh 160 × 160 ô 5 cm: 5.657 FREE, 230 OCCUPIED; lưu/nạp lại bằng nhau.
  - Thử ghép 300 vòng DROW: sharpness 0,30 khi theo `.odom2`, 0,18 khi đảo dấu góc, 0,13 khi giữ cảm biến cố định. Đây là
    bằng chứng gián tiếp về chiều góc của odometry DROW, không phải kiểm chứng SLAM.
- *Nguồn:* [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 3, 3b, 5; [gate_01.md](gate_01.md); [hardware_inventory.md](hardware_inventory.md).
- *Hình/bảng:* bảng mục 3 (so với datasheet); [p07_nen_phong.png](evidence/lidar/p07_nen_phong.png) và
  [analysis.json](evidence/lidar/p07_nen_phong.analysis.json); [map_p07.png](evidence/lidar/map_p07.png). Ba ảnh DROW (DL):
  [drow_odom_map.png](evidence/lidar/drow_odom_map.png) (ghép theo `.odom2`, sharpness 0,30),
  [drow_odom_mirror_map.png](evidence/lidar/drow_odom_mirror_map.png) (đảo dấu góc, 0,18),
  [drow_fixed_map.png](evidence/lidar/drow_fixed_map.png) (giữ cảm biến cố định, 0,13).
  - GIAI_DOAN_1_LIDAR mục 5 link cả ba ảnh và ghi ba lệnh dựng lại, mỗi lệnh một dòng, kèm tham số (300 vòng đầu, lưới
    24 × 24 m ô 0,1 m, `--max-range 10`). Ngày 24/09 đã dựng lại cả ba ảnh bằng các lệnh đó, trùng từng byte với tệp trong
    `evidence/lidar/`. Khi trích lệnh thì dẫn mục đó, không dẫn dàn ý.
  - Sharpness là số ô OCCUPIED chia cho số ô quan sát được có ít nhất một lần trúng (`occupancy.py`, `summary`). Số này
    phụ thuộc lưới và tầm: với tham số mặc định (lưới 8 m, ô 0,05 m, tầm 12 m), biến thể cố định chỉ còn ≈ 0,08 (0,076,
    dựng lại 24/09). Vì vậy khi trích phải ghi kèm tham số.
- *Định vị trên bản đồ `map_p07` (tối 24/09/2026; chạy offline trên máy bàn, không chạy thiết bị;*
  [DINH_VI_LIDAR.md](DINH_VI_LIDAR.md) *mục 4–5;* [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) *mục 8):*
  - p07 (chính dữ liệu dựng bản đồ, **không độc lập**): 181/181 OK, trung vị (−1,3 mm; −3,3 mm; +0,008°), độ lệch chuẩn
    giữa các vòng 1,4 / 1,8 mm, 0,047°.
  - live_headless (22/09, 2,5 phút sau p07, dự kiến cùng chỗ): 60/60 OK, (−1,1 mm; −6,8 mm; **+4,33°**); `--track` và
    `--global` cho cùng kết quả. Kiểm không dùng bản đồ (dịch hồ sơ khoảng cách theo góc, script tạm không lưu trong repo)
    cũng cho −4,25…−4,5°. Nguyên nhân chưa phân biệt được: thiết bị bị xoay nhẹ giữa hai lần ghi, hay gốc góc của C1 đổi
    giữa hai lần khởi động mô-tơ.
  - k01 (24/09, LiDAR đã dời chỗ, vị trí mới không ghi lại): 151/151 FAILED; `--global --every 5`: 31/31 FAILED. Khi tìm
    toàn cục, cả 31 vòng cho **cùng một** đỉnh sai, nên tư thế ổn định qua các vòng không phải bằng chứng là tư thế đúng.
  - Dịch cứng có chủ đích trên vòng thật (±0,4 m, ±25°, 180 lần, script tạm): 180/180 OK, sai số trung vị 3,8 mm và
    0,038°, lớn nhất 17 mm và 0,24°. Đây là khả năng **tìm lại** trên cảnh thật, không phải độ đúng (che khuất không đổi).
  - Phòng tổng hợp (29 test): sai số 0,4–0,7 cm và 0,004–0,10° trên 6 tư thế, phần 0,5–0,6 cm có hệ thống do bản đồ lượng
    tử hóa tường về tâm ô.
  - Thời gian mỗi vòng, cửa sổ mặc định: trung vị 10,6–11,1 ms khi cảnh khớp, 84,6 ms khi không khớp (k01); `--global`
    534 ms (đo trước bản sửa kiểm xuyên tường; sau sửa thêm ≈ 2 ms trên live_headless, ≈ 6 ms trên k01).
  - *Hình/bảng (`b100a5d`):* [dinh_vi_p07_tren_p07.png](evidence/lidar/dinh_vi_p07_tren_p07.png) (không độc lập),
    [dinh_vi_live_headless_tren_p07.png](evidence/lidar/dinh_vi_live_headless_tren_p07.png),
    [dinh_vi_k01_tren_p07.png](evidence/lidar/dinh_vi_k01_tren_p07.png),
    [dinh_vi_k01_global_tren_p07.png](evidence/lidar/dinh_vi_k01_global_tren_p07.png) (`--global --every 5`); tóm tắt
    [dinh_vi_tren_p07_20260924.json](evidence/lidar/dinh_vi_tren_p07_20260924.json) gồm lệnh, tham số, hash mã, kết quả
    từng lần chạy (GIAI_DOAN_1_LIDAR mục 8). Ảnh dựng bằng mã đã sửa màu; trạng thái và tư thế trùng các số trên. Thời
    gian mỗi vòng trong tệp tóm tắt đo lúc máy bận việc khác, không trích. Ảnh chỉ cho thấy độ nhất quán, không phải độ
    đúng.
- *Độ lặp lại và odometry khớp scan (khuya 24/09/2026, `a7cec5e`; BT offline trên bản ghi có sẵn, máy bàn):*
  - **Độ lặp lại khoảng cách** ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 3c). Số ban đầu đến từ một script tạm ngày
    24/09, không lưu trong repo và đã mất. Phép tính được viết lại theo đúng mô tả thành `lidar/repeatability.py` và cho
    lại đúng số cũ: p07 1,0–1,25 mm, k01 1,25–1,5 mm tùy dung sai góc; p90 4,25–7,75 mm. Thêm live_headless 0,75–1,0 mm
    (28 vòng). Phép tính theo ô góc 0,5° đã khử dốc cho trung vị 0,89–1,56 mm. C1 gửi khoảng cách theo bậc 0,25 mm.
    "Tái lập" chỉ có nghĩa cùng mô tả cho cùng số, không chứng minh hai mã giống nhau.
    Hình/bảng: [do_lap_lai_20260924.json](evidence/lidar/do_lap_lai_20260924.json),
    [do_lap_lai_p07_nen_phong.png](evidence/lidar/do_lap_lai_p07_nen_phong.png),
    [do_lap_lai_k01_kiem_suc_khoe.png](evidence/lidar/do_lap_lai_k01_kiem_suc_khoe.png); bản nhỏ của k01 (hình vòng quét và
    `analysis.json`, GIAI_DOAN_1_LIDAR mục 3b): [k01_kiem_suc_khoe.png](evidence/lidar/k01_kiem_suc_khoe.png),
    [k01_kiem_suc_khoe.analysis.json](evidence/lidar/k01_kiem_suc_khoe.analysis.json).
  - **Odometry khớp scan** ([SO_SANH_DINH_VI_SLAM.md](SO_SANH_DINH_VI_SLAM.md) mục 3.4–3.5). Trên sáu bản ghi C1 **đứng
    yên**, `scan_to_map` không trôi (o03, 57 s: lệch lớn nhất 9 mm và 0,5°), còn `scan_to_scan` trôi 17,5 cm và 6,6°. Trên
    DROW v2 (DL, 35 chuỗi, so với `.odom2`, không phải ground truth): lệch trung vị 2,2 % trên đoạn 5 m, 2,8 % vòng FAILED.
    Hình: [odometry_khop_scan_drow_13-47-42_scan_to_map.png](evidence/lidar/odometry_khop_scan_drow_13-47-42_scan_to_map.png)
    và các tệp `odometry_khop_scan_*` cùng thư mục (hình dựng từ DROW: MIT, trích cả hai bài DROW, mục 4).
  - Phương án định vị cho V1: ngày 02/10/2026 người dùng đồng ý làm theo đề xuất (a) + (b). Nó đã nối vào phiên ở mức MP
    (LiDAR mô phỏng) và chạy offline trên bản ghi C1 đứng yên (BT offline); ngưỡng vẫn là đề xuất, chưa chốt (1.6;
    [NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md)).
- *Rút cáp LiDAR (muộn tối 24/09/2026, mức TH):* phần mềm xử lý rút cáp có test với cổng serial **giả**
  (`tests/test_lidar_unplug.py`, 13 test). Driver ném `LidarTransportError` (lớp con của `ScanReadError`); demo hợp nhất
  dừng xe ảo với lý do "Mất kết nối LiDAR"; `lidar.bench record` sau 3 lỗi đọc thì dừng, không ném lỗi lần hai khi đóng
  cổng đã chết, vẫn lưu và phân tích phần đã ghi, thoát mã 1. Rút cáp C1 thật chưa thử.
- *Còn thiếu:*
  - **sai số khoảng cách so với thước**: 7 lần đặt hộp p01–p06, p08, cần người;
  - dấu góc trái/phải;
  - thử rút cáp C1 thật xem `STALE_DATA`;
  - **tham chiếu độc lập cho định vị** ([DINH_VI_LIDAR.md](DINH_VI_LIDAR.md) mục 7): hai phiên liên tiếp không chạm C1,
    khởi động lại mô-tơ giữa hai phiên (để tìm nguyên nhân +4,3°); dời C1 tới 3–6 vị trí và hướng đo bằng thước, làm cùng
    buổi với 7 lần đặt hộp; chốt ngưỡng;
  - sao lưu `localize.json`/`track.csv` từng vòng nếu cần (bốn ảnh overlay và tệp tóm tắt đã chép, xem Hình/bảng ở trên);
  - đo trên laptop.
- *Giới hạn phải nói:*
  - "Độ lặp lại 1,0–1,5 mm giữa hai vòng liên tiếp" (p90 4–8 mm; tính cả live_headless thì 0,75–1,5 mm) không phải sai số
    so với thước. Số này ban đầu từ script tạm, nay `lidar/repeatability.py` cho lại đúng.
  - `bench`/`live_view` đóng dấu bằng `time.monotonic` bước 15,6 ms, nên chu kỳ trong các bản ghi đó bị lượng tử hóa.
  - Có tia rất gần chất lượng thấp ở hai vùng góc cố định, nghi do dây cáp, chưa kiểm.
  - Về định vị: số trên chỉ là độ **nhất quán** (cùng chỗ ra cùng tư thế, khác chỗ thì báo hỏng), không phải độ đúng. Độ
    lệch chuẩn Hessian (1–4 mm trên dữ liệu thật) quá lạc quan. Bản đồ p07 là một góc nhìn từ một chỗ trên bàn, nhiều
    UNKNOWN. Chưa có bản ghi C1 nào khi cảm biến di chuyển. Ngưỡng chưa chốt.
  - Số thời gian của đợt khuya đo khi máy bận.

**4.5. Camera USB — BT, máy bàn, 23–24/09/2026**
- *Viết được — mode và tốc độ khung:*
  - Mode công bố MJPG 640×480 / 1280×720 / 1920×1080 đều 30 fps.
  - Ở phơi sáng tự động, đo được thường ≈ 23,85 khung/s, nhịp xen kẽ ≈ 31 ms và ≈ 48 ms.
  - Ở phơi sáng tự động, đôi khi một camera chạy ≈ 29 khung/s, và camera đó **không cố định một cổng**:
    - cổng 3 ở s01–s07 và t01, t02 (23/09; GIAI_DOAN_2_BAN_THU mục 5, [hardware_inventory.md](hardware_inventory.md));
    - cổng 1 ở t05 (23/09, 640×480, `exposure: null`); số FPS này đếm cả khung có thể bị cắt, vì đo trước khi có bộ dò;
    - cổng 1 lúc 15:25 (m02 `may_moi`) và 17:56 (o01) ngày 24/09, 720p, cảnh tối. Với m02, `exposure: null` nằm trong
      `runs/may_moi_20260924_may_ban/m02_720p_chi_camera.rig.json`, và ghi chú của tệp tham chiếu ghi "phơi sáng tự động";
    - lần `may_moi` lúc 19:08 ngày 24/09 (720p chỉ camera, cùng chỗ đặt) thì không camera nào; cả bốn 23,83–23,87 khung/s.

    Khi viết, nói "một camera có thể chạy ≈ 29 khung/s, camera nào thì đổi giữa các lần mở"; không gắn với cổng 1.
  - r01/r02 (GIAI_DOAN_2 mục 2.3) cho 28,4 / 29,2 khung tốt/s, nhưng tệp raw không ghi chế độ phơi sáng. Ở phiên khác lại
    ≈ 23,5–23,9 (r07, u01).
  - Mọi phiên ép phơi sáng thủ công ≤ −5 cho 29,3 khung/s, ảnh gần đen (GIAI_DOAN_1_CAMERA mục 4.1, 4.4). Đó là phiên m02,
    m11, n02 ngày 23/09, một camera, `camera_bench`; không phải m02 `may_moi` ngày 24/09 (tên phiên trùng, TONG_HOP mục 7).
  - Cơ chế của các nhịp khác nhau chưa xác định.
- *Viết được — khung bị cắt:*
  - Chạy một mình thì không camera nào bị cắt khung.
  - Bốn camera ở 720p/1080p (cảnh sáng 23/09, camera nhìn thảm hoa văn): hai–ba camera bị cắt phần lớn khung (r04, r08,
    r11 ở 720p; r09 ở 1080p). Ví dụ u02, 720p, 60 s: cổng 1 và 4 có 1.431 và 1.430 khung bị cắt, 0,0 khung tốt/s.
  - Ba camera ở 720p: chỉ một camera bị cắt phần lớn khung (r03: cổng 1 97 %, cổng 3 9 %; r05: cổng 4 67 %, cổng 3 1 %).
  - Ba camera ở 1080p: chưa có phiên nào đếm khung bị cắt (m07, n05, q07, q08 đo trước khi có bộ dò, GIAI_DOAN_1_CAMERA
    mục 4.6).
  - 640×480, 18 phiên 23/09: cổng 1 hỏng 1.418 / 31.142 khung (4,6 %, gần hết trong hai đợt 26,3 % và 36,2 %); cổng 2 và
    3: 0; cổng 4: 6.
  - Index OpenCV đổi sau khởi động lại; InstanceId theo cổng giữ nguyên.
- *Nguồn:* [GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) mục 3, 4.1, 4.2, 4.6; [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md)
  mục 2.3–2.4, mục 5 (t05); [tham_chieu_20260924.json](evidence/may_ban/tham_chieu_20260924.json) (15:25);
  [tham_chieu_20260924_toi.json](evidence/may_ban/tham_chieu_20260924_toi.json) (19:08, `bfcbfc2`:
  `digest.cam720.good_fps` 23,83 / 23,87 / 23,87 / 23,87, `damaged` 0 ở cả bốn); [usb_topology.md](usb_topology.md).
- *Hình/bảng:* bảng mục 2.3, 2.4 của GIAI_DOAN_2_BAN_THU; các tệp `evidence/camera/*.measure.json`; ảnh mẫu
  [r01](evidence/camera/r01_cam0_720p_008s_small.jpg), [r03](evidence/camera/r03_cam0_720p_nofilm_005s_small.jpg); ảnh khung
  bị cắt ở mục 3.7.
- *Còn thiếu:* nguyên nhân khung bị cắt (giả thuyết băng thông USB 2.0 dùng chung qua hub, chưa chứng minh vì chưa đọc
  được byte MJPEG thô); tách camera ra nhiều cổng gốc; nguồn ngoài cho hub; góc nhìn thật; độ nét ở độ cao dự kiến; độ trễ
  từ sự kiện thật (LED nháy); nhiệt CPU; mọi số trên laptop.
- *Giới hạn phải nói:*
  - [report_20260923.md](evidence/camera/report_20260923.md) sinh **trước** khi có bộ dò khung bị cắt, nên chữ "sạch" và
    cột FPS ở đó chỉ nói về khung cũ (đính chính ở GIAI_DOAN_1_CAMERA mục 4.6).
  - Các phiên 720p × 4 ngày 24/09 không có khung bị cắt vì camera nhìn chỗ tối; đó **không** phải bằng chứng 720p dùng
    được. Gồm w03, w04; o01 (720p bốn camera, 30 s, cùng chỗ đặt; cổng 1 lại chạy 29,27 khung/s, cổng 2–4 ≈ 23,85; 4.6);
    và lần `may_moi` 19:08.

**4.6. Bàn thử bốn camera + LiDAR + AI — BT, máy bàn, 23–24/09/2026**
- *Viết được:*
  - u01 (120 s, 640×480): 4 × 23,8–23,9 khung tốt/s, 0 khung hỏng; AI 23,8 bộ/s; lô bốn ảnh trung vị 16,4 ms (mạng
    11,6 ms). Kết quả AI có mặt 34,8 ms (trung vị) sau khi khung cũ nhất của bộ tới máy. Độ lệch trong bộ trung vị 15,0 ms,
    p95 24,1 ms. Điểm giữa vòng LiDAR sớm hơn mốc bộ ảnh ≈ 80 ms. GPU trung bình 26 %, 41 → 46 °C.
  - u04 (600 s): 6 khung hỏng (cổng 4), AI 23,1 bộ/s, 15,6 ms/lô, LiDAR 6.006 vòng, 0 vòng mất; có bảng theo từng phút.
  - Quy tắc không chờ (24/09, w01–w05): ở ba phiên bật, 0 bộ thiếu camera khỏe trong 7.155 bộ, số bộ/s bằng lúc tắt. Tuổi
    kết quả AI ≈ 37–42 ms khi bật, ≈ 62 ms khi tắt; cơ chế chưa giải thích.
- *Nguồn:* [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 3–4, 10.
- *Hình/bảng:* bảng mục 3.1–3.5, 10; [giao_dien_480p_thr015.jpg](evidence/rig/giao_dien_480p_thr015.jpg),
  [giao_dien_720p_thr015.jpg](evidence/rig/giao_dien_720p_thr015.jpg) (lớp tô chỉ để nhìn).
- *Trường hợp quy tắc cũ bỏ camera khỏe (chưa được TONG_HOP nhắc):* tệp tham chiếu máy bàn cho lệnh đo laptop
  ([tham_chieu_20260924.json](evidence/may_ban/tham_chieu_20260924.json), 24/09 lúc 15:25, camera nhìn chỗ tối) ghi:
  - bước 720p chỉ camera (30 s): camera cổng 1 chạy 29,3 khung/s (phơi sáng tự động, `exposure: null`), ba camera kia
    ≈ 23,85. Quy tắc không chờ ghép 263/855 bộ thiếu camera (`lagging_per_port` = [0, 106, 137, 106]); ghi chú của tệp gọi
    đó là "bỏ camera khỏe";
  - bước 480p + LiDAR + AI 120 s: 3/2.861 bộ ghép thiếu camera (`lagging_per_port` = [0, 3, 0, 0]), 23,85 bộ AI/s.

  Đây là trường hợp quy tắc **bỏ camera khỏe**, khác kết luận "0 trong 7.155 bộ" của w01–w05; phải nêu cả hai khi viết về
  quy tắc này. Trường hợp này dẫn tới quy tắc theo nhịp riêng (3.7), đo lại ngay dưới đây.
- *Đo lại trên phần cứng sau khi đổi quy tắc (tối 24/09/2026, `bfcbfc2`).* Cùng máy bàn, hub, bốn camera ở cổng 1–4, LiDAR
  COM4, cùng chỗ đặt camera như lúc 15:25, camera nhìn chỗ tối. Nguồn: GIAI_DOAN_2_BAN_THU mục 10.3; bản rút gọn
  [cho_nhip_rieng_ghi_phat_lai_20260924.json](evidence/rig/cho_nhip_rieng_ghi_phat_lai_20260924.json); tệp gốc
  `runs/rig_bench/20260924_own/` (git-ignore).

  | Phiên | Cấu hình | Khung tốt/s cổng 1 / 2 / 3 / 4 | Bộ | Bộ bỏ camera khỏe | Độ lệch bộ trung vị / p95 / max (ms) |
  |---|---|---|---:|---:|---|
  | m02 (`may_moi` 24/09 lúc 15:25, quy tắc trước) | 720p chỉ camera, 30 s | 29,3 / 23,85 / 23,85 / 23,85 | 855 | 263 | 24,5 / 36,0 / 40,3 |
  | o01 (theo nhịp riêng) | 720p chỉ camera, 30 s | 29,27 / 23,87 / 23,87 / 23,83 | 715 | 0 | 28,5 / 36,4 / 52,8 |
  | m01 (`may_moi` 24/09 lúc 15:25, quy tắc trước) | 480p + LiDAR + AI, 120 s | 23,85 cả bốn | 2861 | 3 | 27,8 / 28,0 / 41,2 |
  | o02 (theo nhịp riêng) | 480p + LiDAR + AI, 120 s | 23,85 cả bốn | 2862 | 0 | 23,1 / 23,3 / 25,8 |

  Ở o01, camera 24 khung/s định nhịp; 164 khung dư của cổng 1 không vào bộ nào (23,8 bộ/s). Cái giá là độ lệch trong bộ
  lớn hơn ở 720p (trung vị 28,5 so với 24,5 ms, max 52,8 so với 40,3 ms), đúng như mô phỏng đã báo. Ở o02, AI chấm 23,85
  bộ/s, một lô trung vị 12,1 ms (p95 14,5, max 20,8 ms), LiDAR 10,008 Hz, 0 lỗi. Cả bốn phiên 0 khung bị cắt/xé. Không
  đặt 12,1 ms cạnh 16,4 ms của u01 như một cải thiện: hai phiên khác ngày, khác tải máy (u01 đo khi có dự án khác chạy
  cùng máy), và chưa tài liệu nào phân tích chênh lệch này.
- *Lô AI đầu tiên của mỗi cỡ lô (tối 24/09/2026).* Máy bàn, LiveSegmenter 640×480, cùng một tiến trình, lần lượt các lô 4,
  4, 3, 3, 2, 1, 4, 3 ảnh: 1665, 18, 1444, 15, 1431, 1265, 17, 15 ms. Lô đầu của **mỗi** cỡ phải trả phần khởi tạo, không
  chỉ lô đầu của phiên. Hiện tượng lộ ra khi phát lại phiên thật o03 (4.6b).
  - Sửa bằng `AIWorker.warm_up` (3.8): `ai.warm_up_ms` = [1682, 1444, 1468, 1283] ms. AI sẵn sàng chậm hơn ≈ 4,2 s so với
    trước. 4,2 s là phần chậm thêm, không phải thời gian làm nóng; tổng bốn lô làm nóng ≈ 5,9 s ở o06 và o07 (mục 6).
  - Phiên thật o07 sau sửa (480p + LiDAR + AI, 30 s): 715 bộ, 0 bỏ camera, 23,87 bộ/s, lô chậm nhất 18,3 ms.
  - Ở phiên thật trước đây chưa từng thấy AI đứng như thế (m01 `may_moi` 24/09: 3 lô thiếu camera trong cửa sổ đo, lô chậm
    nhất 20,2 ms). Giải thích "lô thiếu camera đầu tiên rơi vào 5 s làm nóng" là **chưa kiểm**.
  - Thời gian làm nóng trên laptop chưa đo.
- *Chạy lại `may_moi` lúc 19:08 bằng mã mới (muộn tối 24/09/2026, `bfcbfc2`).* Máy bàn, cùng hub và chỗ đặt, camera nhìn
  chỗ tối. Bản rút gọn [tham_chieu_20260924_toi.json](evidence/may_ban/tham_chieu_20260924_toi.json); tệp gốc
  `runs/may_moi_20260924_toi/` (git-ignore). Tên phiên m01/m02 trùng lần nữa, nên ghi kèm giờ.
  - m01 (480p + LiDAR + AI, 120 s): 23,85 khung/s mỗi camera, 0 khung hỏng, 2.861 bộ, 0 bộ thiếu camera khỏe (lúc 15:25
    là 3). AI 23,85 bộ/s, lô trung vị 13,2 ms, LiDAR 10,01 Hz. Độ lệch trong bộ trung vị / p95 / max 29,1 / 30,1 /
    33,9 ms, đọc từ `.rig.json` gốc vì tệp rút gọn không ghi độ lệch. `ai.warm_up_ms` = 1482 / 1448 / 1553 / 1410 ms, tổng
    ≈ 5,9 s.
  - m02 (720p chỉ camera, 30 s): lần này cả bốn camera ≈ 23,85 khung/s (4.5); 716 bộ, 0 bộ bỏ camera (lúc 15:25 là
    263/855); độ lệch trung vị / p95 / max 16,6 / 31,8 / 34,4 ms. Vì không có camera ≈ 29 khung/s, phiên này **không**
    thử lại tình huống hai nhịp; bằng chứng cho quy tắc mới trong tình huống đó vẫn chỉ là o01.
  - Bước `ai` riêng của `may_moi` (5 lô 4 ảnh khởi động, 60 lô đo; không dùng phần làm nóng của bàn thử): trung vị
    10,4 ms, p95 11,4 ms, VRAM đỉnh 78 MB.
- *Còn thiếu:* một phiên có camera chậm thật (bật và tắt quy tắc) để đo lợi ích chính, vốn chưa thấy trên phần cứng; độ trễ
  từ sự kiện thật; chạy lại `rig.bench` trên laptop. Cách làm đề xuất: ghi một phiên có camera bị cắt/xé khung thật (720p,
  cảnh sáng nhiều chi tiết) rồi phát lại với `--max-wait-ms 60` và `--max-wait-ms 0` trên cùng bản ghi
  (GHI_PHAT_LAI_BAN_THU mục 8).
- *Giới hạn phải nói:*
  - Mọi stamp là lúc dữ liệu tới máy, không phải lúc phơi sáng. Khi đo có một dự án khác chạy cùng máy (có ghi CPU cả
    máy).
  - Nhược điểm đã biết trong mô phỏng: với quy tắc trước, khi pha từng camera trôi, mỗi cổng khỏe vẫn bị bỏ 0,2–2,7 % số
    bộ. Với quy tắc theo nhịp riêng, cùng loại mô phỏng không bỏ "chậm" camera khỏe nào, nhưng còn 2,1–2,5 % số bộ bị để
    dành để gom lại pha (GIAI_DOAN_2_BAN_THU mục 10, 10.1).
  - Các phiên o01, o02, o07 không có khung hỏng nào, nên nhánh "bỏ camera lỡ nhịp" của quy tắc mới **chỉ** được kiểm bằng
    mô phỏng và test.
  - Khung hỏng mà lọt tới AI thì vùng vân xám bị gọi gần hết là FREE (đo trên hai khung 720p chụp trước khi có bộ lọc); lỗi
    theo hướng không an toàn.
  - 0 khung bị cắt ở 720p (o01) là do cảnh tối, không phải bằng chứng 720p dùng được.
  - Chưa chiếu kết quả AI xuống sàn trên dữ liệu thật: BEV đã có (3.8b) nhưng chưa chạy trên camera dự án vì chưa hiệu
    chuẩn.

**4.6b. Ghi và phát lại phiên bàn thử — BT (một phiên) + TH, máy bàn, tối 24/09/2026** *(thêm tối 24/09/2026)*
- *Viết được:*
  - Ghi o03: bốn camera 640×480 + LiDAR + AI, 60 s sau 5 s làm nóng, camera nhìn chỗ tối. Kết quả: 5.724 khung JPEG q95
    (1.431 mỗi camera), **0 khung bị bỏ**, 601 vòng LiDAR, trạng thái `xong`; 298,6 MB, tức 4,98 MB/s, ≈ 52 KB/khung.
    Trong lúc ghi: AI 23,85 bộ/s, lô trung vị 12,3 ms, 0 bộ bỏ camera, LiDAR 10,0 Hz, 0 lỗi.
  - Ước lượng trước đó (≈ 163 KB/khung, ≈ 15 MB/s) làm trên ảnh nhìn thảm hoa văn; cảnh sa bàn thật cho bao nhiêu thì chưa
    đo. CPU tiến trình trung bình 0,78 lõi, so với 0,68 lõi ở o02 không ghi; chênh ≈ 0,1 lõi gồm cả nhiễu giữa hai phiên,
    chưa tách.
  - Phát lại cùng bản ghi, cùng quy tắc, AI thật trên GPU:
    - o04 (chưa làm nóng): 1.364 bộ, 34/34/67/34 khung không vào bộ nào, lô AI chậm nhất 1.457 ms;
    - o05 (làm nóng lô 4 ảnh): 1.403 bộ, còn một lần đứng 1.272 ms;
    - **o06 (làm nóng mọi cỡ lô): 1.432 bộ như phiên thật**; độ lệch trong bộ trung vị / p95 / max 26,0 / 42,1 / 44,8 ms,
      trùng phiên thật tới 0,1 ms. Còn khác: một bộ thiếu cổng 3 ở giây đầu (chưa đo được nhịp camera); lô chậm nhất 19,7
      so với 18,4 ms; khung ra muộn so với lịch trung vị 0,3 ms.
  - Test: `tests/test_rig_replay.py` 27 hàm với nguồn giả: bản ghi đúng từng pixel ở PNG, stamp tương đối trùng tới 1 µs,
    sự kiện trùng loại/thứ tự/nguyên văn, lỗi ghi được báo. Kiểm đột biến 12 rồi 15; cả hai lượt đều bị bắt hết.
- *Nguồn:* [GHI_PHAT_LAI_BAN_THU.md](GHI_PHAT_LAI_BAN_THU.md) mục 5–7; [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md)
  mục 10.3; [cho_nhip_rieng_ghi_phat_lai_20260924.json](evidence/rig/cho_nhip_rieng_ghi_phat_lai_20260924.json). Bản ghi
  gốc `runs/rig_recordings/o03_20260924/` (≈ 300 MB, git-ignore, phải sao lưu).
- *Còn thiếu:* bản ghi có camera bị cắt/xé khung thật, để so hai quy tắc chờ trên cùng dữ liệu có camera lỡ nhịp; giao diện
  `--replay` với bản ghi thật (mới chạy với nguồn giả); phát lại ở speed ≠ 1 trên bản ghi thật; một phiên nhìn sa bàn thật
  để biết MB/s. Trên laptop, luồng ghi có theo kịp 4 × 24 khung/s không và đĩa có đủ chỗ không: chưa đo.
- *Giới hạn phải nói:* **một** phiên, cảnh tối, 480p, máy bàn. Kết quả AI khi phát lại không trùng từng bit vì JPEG mã hóa
  lại; các giới hạn chung của phát lại ở 4.1. Dòng CSV hỏng khi mất điện hay hệ điều hành sập mới chỉ được giả lập trong
  test, chưa thử trên máy thật.

**4.7. Hợp nhất với LiDAR thật đứng yên — BT + MP, máy bàn, 22/09/2026**
- *Viết được:* chuỗi thêm dần năm quy tắc từ "dừng ngay vòng quét đầu (3 vật mới từ nhiễu)" tới **COMPLETED**: LiDAR cố
  định tại điểm xuất phát, xe ảo lập đường quanh 20 vật cản thật và đỗ xong, 202 vòng quét, 0 lỗi đọc, 0 dừng giả; kiểm toán
  "vì sao số vật cản khác số vật" (18 cụm vật, 33 hình chữ nhật phủ chính xác ở lưới 5 cm).
- *Nguồn:* [GIAI_DOAN_3_CHUAN_BI.md](GIAI_DOAN_3_CHUAN_BI.md) mục 2, 3, 3b.
- *Còn thiếu:* đưa tay/hộp vào trước LiDAR (cách ≥ 40 cm) và rút cáp khi xe ảo đang chạy (mới kiểm bằng nguồn quét kịch bản;
  cần người); ảnh chụp màn hình phiên COMPLETED (không thấy trong `docs/evidence/`).
- *Giới hạn phải nói:* xe là xe ảo, LiDAR đứng yên; không nói gì về định vị hay quãng dừng.

**4.8. Giao thức, bản tham chiếu firmware, `VehicleIO` — MP, 24/09/2026**
- *Viết được:*
  - 184 test đạt, 0 lỗi: giao thức 52, bản tham chiếu firmware 73, `VehicleIO` 48, kiểm tĩnh C++ 11.
  - Ba đợt đột biến mã (21, 22, 22 đột biến). Sau khi thêm test, mọi đột biến đều bị bắt; 13 đột biến C++ đợt ba chỉ bị bắt
    bằng kiểm tĩnh mã nguồn.
  - Mô phỏng vòng tốc độ với số giả định: sai số trung bình < 1 mm/s nhưng vọt lố 26–57 %. Ngừng gửi lệnh lúc 0,15 m/s thì
    xe mô phỏng dừng sau 0,39 s, trôi 3,9 cm.
- *Nguồn:* [GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 10–11.
- *Giới hạn phải nói:* mọi số là của **mô hình giả định**, không phải quãng dừng hay đáp ứng của xe thật. C++ chưa chạy
  trên bo thật: lõi chạy qua test host trên máy tính (29/09/2026); cả firmware biên dịch cho ESP32-S3 (29/09/2026) và chạy
  trong bo ảo QEMU (30/09/2026, mức MP, [MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md)).
- *Số test giao thức từ khuya 24/09/2026 (`6db5087`):* bốn tệp `test_transport_*` có 200 test (52 + 73 + 64 + 11), thêm
  15 test so giới hạn và `deferred`. Số "48" của `test_transport_vehicle_io.py` ở trên là số lúc viết; ở `9bcc30c` tệp này
  có 49 test. Test thứ 49 là `test_take_new_returns_queued_telemetry_without_advancing_io`, thêm cùng `take_new()` trong
  `c43e8d3`; `e6c77c1` có 48 ([GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 11). Test của thẻ "Bo điều khiển" và cầu nối ToF
  (19 tệp chạy chung 505 đạt, đột biến 50/50) ở 3.12b. Mọi số vẫn là của bản tham chiếu Python, bo mô phỏng và cổng giả.
- *`VehicleIO` trong phiên đỗ xe và chế độ quan sát (tối 24/09/2026, MP;* [CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) *mục 7).*
  Số test của `tests/test_session_vehicle.py` đổi ba lần trong tối 24/09; mỗi số chỉ đúng với bản mã lúc đó:
  1. Lúc viết CHE_DO_QUAN_SAT mục 7: 34 test (tính cả tham số hóa), đạt 34/34. Chạy cùng các test giai đoạn 0, giao thức,
     hợp nhất, giao diện liên quan: 361 đạt, 0 lỗi. Kiểm đột biến 6 + 27, đều bị bắt.
  2. Sau đó tệp được thêm test: 50 test, 49 đạt + 1 `xfail(strict=True)` ghi khoảng trống an toàn ở 3.12b
     ([GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 11–12). Chưa thấy biên bản kiểm đột biến nào trên bản 50 test. Lúc 18:46 chạy
     lại danh sách tệp của CHE_DO_QUAN_SAT mục 7 (máy bàn, `.venv`, offscreen, chỉ nguồn giả): 375 đạt + 1 xfail, 0 lỗi;
     thêm `tests/test_run_store_vehicle.py`: 4 đạt. Lượt này bỏ riêng
     `test_lidar_dock_ui.py::test_dock_without_source_is_idle`, vì test đó thử mở cổng `COM9` qua driver serial thật và
     đợt này không đụng cổng COM. Số test của danh sách tăng từ 361 lên 377, đúng bằng 16 test mới của
     `test_session_vehicle.py`.
  3. Sau bản sửa khoảng trống an toàn (muộn tối): **60 test, 60 đạt, 0 `xfail`** (chạy lại riêng tệp, máy bàn, `.venv`).
     Danh sách tệp của CHE_DO_QUAN_SAT mục 7 chưa chạy lại riêng sau bản sửa; mọi tệp đó nằm trong lần chạy toàn bộ bộ test
     `.venv` cùng tối: 895 đạt, 6 bỏ qua, 0 lỗi. Chi tiết bản sửa ở 3.12b.
- *Số của mô phỏng phiên `VehicleIO`* (script tạm không lưu trong repo; sa bàn `bai_do_xe.json` 2,55 m, một lần đổi chiều;
  cấu hình bo `configs/vehicle_io_sim.json` toàn số giả định):
  - `VEHICLE_IO`: COMPLETED sau 20,95 s mô phỏng, sai số cuối 0,60 cm / +1,15°, lệch lớn nhất khỏi quỹ đạo 1,25 cm,
    1.049 COMMAND.
  - `OBSERVE`, người lái mô phỏng làm đúng lệnh gợi ý: COMPLETED sau 20,61 s, sai số 0,73 cm / +1,27°, **0 COMMAND**,
    effort luôn 0.
  - Rút cáp giả ở 0,10 m/s: phát hiện `STALE_TELEMETRY` sau 120 ms, xe mô phỏng dừng sau 0,43 s, trôi 4,1 cm, phiên kết
    thúc FAULT `STOP_NOT_CONFIRMED` sau 2,1 s. E-stop giả ở 0,10 m/s: laptop nhận `VEHICLE_FAULT` sau 15 ms, xe mô phỏng
    dừng sau 0,18 s, trôi 0,9 cm.
  - Đồng hồ qua `SerialVehicleIO` với cổng serial giả theo đồng hồ tường: trước bản sửa `SerialVehicleIO` (3.12), phiên chạy
    0,40 lần thời gian thực, 20 lệnh/s, 191 lần đọc chờ; sau sửa 1,00 lần, 50 lệnh/s, 0 lần đọc chờ.
- *Giới hạn phải nói (phiên `VehicleIO`):* tư thế lấy thẳng từ mô phỏng (định vị lý tưởng). Cảm biến tốc độ/góc lái là cảm
  biến giả có trễ và nhiễu giả định. Cổng serial giả trên máy tính **không phải** ESP32-S3. Mọi số trên không phải quãng
  dừng hay độ bám đường của MN300. Không viết "đã thử chế độ quan sát trên xe". Khoảng trống an toàn khi có `Heartbeat`
  (một COMMAND enable=1 sau khi bo đã về ARMED vì hết hạn lệnh) đã sửa ở mức MP; còn khoảng hở khi khung báo dừng chưa
  tới laptop, suy ra từ mã, chưa có test. Câu cần viết ở 3.12b.
- *Bài học từ khoảng trống an toàn (muộn tối 24/09/2026, MP):* một quy tắc an toàn đúng ở từng khối (bo về ARMED khi hết
  hạn lệnh; phiên dừng khi thấy `VEHICLE_STOPPED`) vẫn có kẽ hở do **thứ tự** trong một bước: sự kiện được gom sau nhịp
  điều khiển. Kẽ hở chỉ lộ ra khi ép pha của nhịp điều khiển lúc treo (pha 0) và có một luồng khác giữ liên lạc; test gốc
  tình cờ rơi vào pha 3 nên đạt. Lỗi được tìm thấy và sửa cùng tối, bằng test tham số hóa theo pha và theo khoảng trễ trước
  lệnh dừng. Nên viết như một kinh nghiệm về kiểm thử (duyệt pha, không dựa vào một lần chạy đạt), kèm mức MP.

**4.9. Hiệu chuẩn camera — TH, 24/09/2026**
- *Viết được:* trên ảnh tổng hợp dựng qua một camera Kannala–Brandt đã biết: fx tìm được 351,03 so với 351,0 thật; RMS chiếu
  lại 0,071 px; sai lệch mô hình trung vị 0,05 px, lớn nhất 0,49 px ở góc ảnh (vùng ngoại suy); bài học `findChessboardCornersSB`
  lệch có hệ thống khi không tinh chỉnh bằng `cornerSubPix` (fx 352,07); giao diện đã mở camera thật cổng 2 một lần (≈ 6 s,
  0 khung hỏng) nhưng không chụp ảnh nào.
- *Nguồn:* [HIEU_CHUAN_CAMERA.md](HIEU_CHUAN_CAMERA.md) mục 5.
- *Ngoại tham trên ảnh tổng hợp (khuya 24/09/2026, TH; 3.9):* với 3 lần đặt và số đo thước đúng, vị trí lệch 0,04 mm, hướng
  0,009°. Với nhiễu thước ±2,5 mm, hướng lệch tới 0,93° ([NGOAI_THAM_VA_ROI.md](NGOAI_THAM_VA_ROI.md) mục 7).
- *Còn thiếu:* toàn bộ hiệu chuẩn thật (in bảng 100 %, đo cỡ ô, 20–30 ảnh mỗi camera, so K bốn camera); ngoại tham thật,
  vốn cần nội tham, xe và gá trước.
- *Giới hạn phải nói:* ảnh tổng hợp dùng đúng mô hình 4 hệ số nên luôn khớp; không nói được gì về ống kính thật, MJPEG, rolling
  shutter.

**4.9b. BEV từ AI — TH + DL, máy bàn, 24/09/2026** *(thêm tối 24/09/2026)*
- *Viết được:*
  - Rig bốn camera tổng hợp (tư thế của tệp rig v0, ống kính danh định, lưới 120 × 120 ô 5 cm): free 4.113, occupied 18,
    uncertain 553, occluded 708, unseen 8.972, ego 36. Bỏ camera sau (`--drop 2`): free 2.939, vùng sau xe thành unseen.
    Hộp cao chỉ có cạnh chân hướng về camera là OCCUPIED, phía sau là nêm occluded. Chỉ 164 ô được hai camera cùng thấy.
  - Cột mảnh đặt giữa các tâm ô con, 75 vị trí mỗi cỡ. Trước bản sửa 24/09, số lần ô chứa cột vẫn FREE là 5/75 (cột 2 cm),
    14/75 (1,5 cm), 44/75 (1 cm). Sau khi thêm lượt gỡ FREE: 0/75 cả ba cỡ. Cái giá: FREE giảm 1,7 % trên rig tổng hợp.
  - Thời gian `build_bev`, bốn camera, lưới 6 × 6 m ô 5 cm, supersample 2 (mặc định):
    - bản đầu (24/09): trung vị 69,5 ms (tốt nhất 67,9 ms), lần đầu 318,5 ms vì dựng bảng pixel → ô con; **chậm hơn một chu
      kỳ khung** (≈ 42 ms ở 24 khung/s). Tải máy lúc đo không được kiểm;
    - bản tăng tốc (khuya 24/09, `65b7127`; [BEV.md](BEV.md) mục 6b) dựng phần hình học một lần rồi nhớ. Ở mặc định, khi
      bảng đã dựng: ≈ 7,4–8,8 ms (lần nhanh nhất), ≈ 9,5–12 ms (trung vị); bản cũ đo xen kẽ trong cùng tiến trình 87–104 ms
      (nhanh nhất). **Kết quả trùng từng bit** với bản cũ (test trên 45 cấu hình ngẫu nhiên, thêm 1.743 lần chiếu ngoài
      repo), với `max_range` `None` hoặc > 0. Đo trên rig tổng hợp khi 10–20 tiến trình Python khác chạy cùng máy. Khung
      đầu vẫn ≈ 0,3–0,5 s. Laptop chưa đo.
  - WoodScape `00000_FV` với checkpoint tham chiếu: nhìn bằng mắt, mặt đường phía trước là FREE; xe phía trước và vỉa hè
    cắt vùng FREE, phía sau chúng là occluded. Đây là **minh họa**, không phải phép đo sai số, vì không có nhãn mặt sàn.
  - WoodScape ba ảnh khác thời điểm (`00000_FV`, `00028_RV`, `00140_MVL`; mỗi mã khung chỉ có một camera): chạy được, nhưng
    costmap bị đánh dấu không dùng được vì các khung không đồng bộ; chỉ để thử luồng hợp nhất. Lần chạy này có một lỗi thấy
    được ở ảnh MVL, chưa sửa: đường cong mảnh OCCUPIED/occluded phía sau mặt phẳng ảnh của camera trái, θ gần 90–100°, do
    ROI `roi_MVL.png` không loại hết pixel sát thân xe.
  - Bộ ảnh thật 23/09: lệnh `snapshot` **từ chối** vì chưa có `calibration/cam_p*.json`, đúng thiết kế. Bộ lọc khung hỏng
    (chạy với nội tham danh định đặt ngoài repo; BEV ra từ đó vô nghĩa) bỏ p1 và p4 ở bộ ảnh 720p `20260923_145753_910`
    (352 và 328 dòng đáy bị tô), giữ cả bốn camera ở bộ ảnh 480p.
  - Test: `tests/test_bev.py` lúc đầu 32 test, kiểm đột biến 23, cả 23 bị bắt. Từ khuya 24/09 là 38 test (32 test cũ giữ
    nguyên); đột biến phần tăng tốc 20/20, phần chặn `max_range` 8/8.
- *Nguồn:* [BEV.md](BEV.md) mục 2, 6, 7.
- *Còn thiếu:* **đo sai số BEV** trên sa bàn bằng vật mẫu ở vị trí đo bằng thước (kế hoạch mục 6 bước 8), sau hiệu chuẩn,
  ngoại tham và ROI (3.8b); thời gian trên laptop.
- *Giới hạn phải nói:* không con số nào là sai số BEV. Rig tổng hợp dùng đúng mô hình ống kính và tư thế mà BEV giả định,
  nên chỉ kiểm quy tắc và tọa độ. Ngoại tham là "GIẢ ĐỊNH — CHƯA ĐO". Ảnh WoodScape phải kèm ghi công.

**4.10. Laptop trình diễn RTX 3050 Ti — chưa có số**
- *Hiện trạng:* laptop chưa chạy gì ngoài mô phỏng giai đoạn 0. Mọi mã nói trong dàn ý đã có trên `origin/main`, nên laptop
  chỉ cần `git pull`.
- *Viết được:* quy trình `do_may_moi.cmd` với sáu bước env/usb/lidar/ai/rig480/cam720 ([MAY_NOP_DO_AN.md](MAY_NOP_DO_AN.md)).
  Bản `may_moi` từ khuya 24/09 (`77eb51f`) in thêm làm nóng AI, quy tắc chờ, độ lệch bộ ảnh và cảnh báo khi hai cột không
  cùng điều kiện. Nó cũng tóm tắt lại được một thư mục kết quả mang từ laptop về ([MAY_NOP_DO_AN.md](MAY_NOP_DO_AN.md) mục
  4.1; kiểm offline trên bản sao kết quả máy bàn). BEV có lệnh `bench` riêng để đo trên laptop ([BEV.md](BEV.md) mục 5).
- *Tệp tham chiếu máy bàn để so:* `may_moi` lấy tệp đứng cuối theo tên; các tệp cũ giữ để đối chiếu.
  - [tham_chieu_20260924.json](evidence/may_ban/tham_chieu_20260924.json), 24/09 lúc 15:25: ghi **trước** quy tắc theo
    nhịp riêng và trước làm nóng mọi cỡ lô. Số `lagging_per_port` và thời gian AI sẵn sàng của nó không so thẳng được với
    một lần đo laptop bằng mã mới.
  - [tham_chieu_20260924_toi.json](evidence/may_ban/tham_chieu_20260924_toi.json), 24/09 lúc 19:08, mã mới (`bfcbfc2`; số
    ở 4.6).
  - [tham_chieu_20260929.json](evidence/may_ban/tham_chieu_20260929.json), 29/09 trên máy bàn hiện tại: tệp hiện dùng
    (mục 4).
- *Còn thiếu:* chạy trên laptop với cùng cảnh cho camera; mang kết quả về và ghi vào tài liệu. Đây là việc chặn **mọi** con
  số hiệu năng trong chương này. Các phần thêm từ tối 24/09 cũng chưa đo trên laptop: thời gian làm nóng AI mọi cỡ lô, quy
  tắc ghép theo nhịp riêng, ghi phiên (luồng ghi có theo kịp không, đĩa có đủ chỗ không), thời gian BEV, thời gian định vị
  mỗi vòng. Thời gian làm nóng của laptop đọc ở `ai.warm_up_ms` trong `m01_480p_lidar_ai.rig.json`
  ([MAY_NOP_DO_AN.md](MAY_NOP_DO_AN.md) mục 3).

**4.11. Tự đỗ trên xe thật và xử lý vật cản — chưa có**
- *Viết được:* chỉ phần kế hoạch thử (kế hoạch mục 13, 16.3): đỗ vuông góc rồi song song, nhiều tư thế xuất phát, vật cản
  chặn trước/sau/hông/chiếm đích, mất camera/scan/lệnh, E-stop, reset, reconnect.
- *Còn thiếu:* giai đoạn 4–9 (xe, đo đặc tính, ESP32-S3, nguồn/dừng, gá, hợp nhất trên xe chuyển động); ngưỡng 16.2; tham
  chiếu độc lập cho sai số vị trí/hướng; bảng phân loại nguyên nhân lỗi, can thiệp người giám sát và video từng phiên (kế
  hoạch 13 "Đầu ra phải có", 14; cách ghi ở 4.1).
- *Kế hoạch đo trước khi có xe (từ tối 24/09/2026; TK, mọi ô chưa đo, mọi phép chưa thử):*
  - **Đo MN300** ([GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md)): ánh xạ chín khóa của `vehicle_default.json` và các
    tham số khác sang bảng đo (mục 1). Bảng đo (mục 3): B0 thông tin phiên, B1 hình học và footprint, B2 góc lái thật và
    bán kính quay, B3 tốc độ đổi lái, B4 vùng ga không phản ứng và tốc độ ổn định thấp nhất, B5 đổi chiều và thả trôi, B6
    quãng dừng, B7 đường cong lệnh, B8 ánh xạ xung servo → góc lái. Thứ tự đo khi nhận xe ở mục 7; cách đưa số đo vào cấu
    hình và chạy lại mô phỏng ở mục 4. Phiếu kiểm kê trước khi can thiệp điện: [mn300_inventory.md](mn300_inventory.md).
  - **Kịch bản nghiệm thu nháp** (khuya 24/09): [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) và
    [NGUONG_NGHIEM_THU_DE_XUAT.md](NGUONG_NGHIEM_THU_DE_XUAT.md) (4.1); mọi kịch bản chưa thử. Bảng "làm được ngay" ở mục 6
    của tệp kịch bản (DV-1, DV-2, LD-1, phần bàn thử của VC/CB) là những phép có thể cho số trước khi có xe.
  - **Thử lỗi nguồn/dừng** ([GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md) mục 5): L1–L16 gồm mất nguồn bo, laptop
    tắt/treo, rút cáp USB bo/LiDAR/camera, mất cảm biến trên bo, treo firmware, khởi động lại, E-stop nhấn/đứt dây/nhả, pin
    yếu, sụt áp, lệnh STOP, mất động lực khi logic còn. Mỗi kịch bản gắn một hoặc vài mức R, M0–M3. Cả 16 chưa thử; vài kịch
    bản mới có test mô phỏng hoặc cổng giả.
- *Độ nhạy planner theo kích thước xe (MP):*
  - Chiến dịch 20/09 có đổi kích thước xe nhưng **chưa phải** phép thử độ nhạy: mỗi ca chỉ rút ngẫu nhiên một lần, và một
    nửa số ca phóng sa bàn theo xe. Bảng bán kính quay ở GIAI_DOAN_4_CHUAN_BI mục 5.2 là số **tính** từ giá trị giả định.
  - Phép thử với sa bàn cố định (đề xuất ở GIAI_DOAN_4_CHUAN_BI mục 5) đã chạy từ khuya 24/09 (`10a4735`), bằng công cụ
    `evaluation/sensitivity.py` ([DO_NHAY_KICH_THUOC_XE.md](DO_NHAY_KICH_THUOC_XE.md)). Hai lượt trên máy bàn, nhiều tiến
    trình song song dưới tải, ngân sách 8 s và 20 s: 20 sa bàn × 43 biến thể ±5/10/20 %; 0 vi phạm kiểm độc lập; 11 sa bàn
    giải được ở mọi biến thể. Mười cặp hỏng ở cả hai lượt đều là xe dài hơn 10–20 %; `uturn_w46` sát biên ngay với xe giả
    định.
  - *Giới hạn phải nói:* quanh xe giả định, một hạt giống RRT. Tải máy đổi được kết quả, nên ô "hết giờ" không phải vô
    nghiệm. Khoảng hở mô phỏng vài mm không nói gì về xe thật. Chưa chạy khi máy rảnh.

**4.12. Đối chiếu 10 điều kiện V1 (kế hoạch 16.4) — bảng nên có trong khóa luận**

Không điều kiện nào được đánh dấu đạt (kế hoạch 17.4, 24/09). Cột "Đã có" mô tả bằng chứng, không phải kết luận đạt. Bảng
giữ ô ngắn; chi tiết từng dòng ở danh sách ngay dưới bảng.

| # | Điều kiện | Đã có (mức) | Còn thiếu |
|---:|---|---|---|
| 1 | Bản đồ/định vị LiDAR hoạt động trong khu vực thử | Bản đồ lưới tĩnh (BT); định vị trên bản đồ tĩnh (TH + BT offline); odometry khớp scan (TH + DL + BT offline); nguồn tư thế LiDAR trong phiên (MP) | Tham chiếu độc lập cho định vị; định vị khi cảm biến di chuyển; chốt ngưỡng |
| 2 | Bốn camera cùng hoạt động, hiệu chuẩn đúng gá | Chạy chung ở 640×480 trên máy bàn (BT); quy tắc ghép theo nhịp riêng (BT); công cụ ngoại tham và ROI (TH) | Hiệu chuẩn, gá, ngoại tham; laptop |
| 3 | AI/CV cho thông tin cục bộ cho planner, có đo sai số/nhầm lẫn | Chấm trên dữ liệu công khai (DL); chạy trực tiếp để quan sát (BT); BEV (TH, DL); AI camera làm nguồn vật cản (TH) | Hiệu chuẩn, ngoại tham, ROI cho camera dự án; đo sai số BEV; chấm trên sa bàn |
| 4 | Chọn vị trí/hướng, xem trước, ra lệnh bắt đầu | Có trong giao diện mô phỏng (MP) | Trên xe thật |
| 5 | Quỹ đạo xét giới hạn lái và toàn thân xe | Có, với thông số giả định (MP); độ nhạy theo kích thước xe, đường chứng 16 ca khó (MP) | Thông số MN300 đo được |
| 6 | Xe thực thi có phản hồi tốc độ/góc | Vòng tốc độ và phiên đỗ xe qua `VehicleIO` mô phỏng (MP); firmware trong bo ảo QEMU (MP) | Encoder, AS5600, ESP32-S3, xe; nguồn tư thế thật |
| 7 | Hoàn thành các bài đỗ theo tiêu chí đã chốt | — (chỉ có bản đề xuất tiêu chí, TK) | Tiêu chí chưa chốt; xe |
| 8 | Vật cản/dữ liệu không hợp lệ làm dừng hoặc từ chối chạy | Dừng và từ chối START trong mô phỏng (MP); LiDAR thật đứng yên, 0 dừng giả (BT) | Thử với LiDAR thật khi xe ảo chạy; bo thật; xe |
| 9 | Nguồn, watchdog, E-stop đã kiểm chứng | Watchdog ở bản Python, test host C++, bo ảo QEMU (MP); ngõ vào E-stop và bản nháp nguồn/dừng (TK) | Toàn bộ phần cứng nguồn/dừng |
| 10 | Có dữ liệu, cấu hình, hướng dẫn tái hiện | Replay mô phỏng; hồ sơ đo bàn thử; hướng dẫn laptop; ghi/phát lại bàn thử (BT); phát lại log `VehicleIO` (MP) | Sao lưu `runs/`; chạy lại trên laptop và bản mã cuối |

Chi tiết theo dòng:

- **Dòng 1.** Bản đồ lưới tĩnh từ một vị trí (BT). Tối 24/09: định vị trên bản đồ tĩnh, nhất quán trên bản ghi đứng yên
  cùng chỗ và báo hỏng khi đã dời chỗ (TH + BT offline). Khuya 24/09 (`a7cec5e`): odometry khớp scan (TH + DL + BT offline,
  C1 đứng yên) và đề xuất phương án (TK). Ngày 02/10/2026 người dùng đồng ý phương án (a) + (b); nguồn tư thế đã nối vào
  phiên ở mức MP với LiDAR mô phỏng (1.6). Còn thiếu thêm: bản đồ của phương án SLAM nếu cần.
- **Dòng 2.** Tối 24/09: quy tắc ghép theo nhịp riêng được đo lại trên máy bàn (BT). Khuya 24/09 (`65b7127`): công cụ
  ngoại tham và ROI, chỉ kiểm trên ảnh tổng hợp (TH).
- **Dòng 3.** Tối 24/09: BEV trên rig tổng hợp và ảnh WoodScape (TH, DL). Khuya 24/09: BEV ≈ 7–12 ms trên rig tổng hợp
  (TH, `65b7127`); RoadAnomaly21 (DL, `77eb51f`). Đợt AI camera 25/09/2026: AI camera nối vào phiên đỗ xe làm nguồn vật
  cản (TH); phát lại bản ghi o03 thì mọi lô bị chặn vì chưa hiệu chuẩn (3.11b). Như vậy việc "nối vào costmap/planner" đã
  làm ở mức phần mềm, và quyết định giấy phép đã có (cách đọc A, Valeo chưa xác nhận).
- **Dòng 5.** Khuya 24/09 (`10a4735`): độ nhạy theo kích thước xe và đường chứng của 16 ca khó, kiểm độc lập với planner
  (MP). Tiêu chí số lần đổi chiều: ngày 02/10/2026 người dùng đồng ý giới hạn theo từng kịch bản nghiệm thu (N-D6 (b));
  ngưỡng vẫn là đề xuất.
- **Dòng 6.** Tối 24/09: `VehicleIO` nối vào phiên đỗ xe, đỗ xong với bo mô phỏng và tư thế lý tưởng; chế độ quan sát
  không gửi COMMAND nào (MP). Từ 30/09/2026 bản build firmware thật chạy trong bo ảo QEMU với `SerialVehicleIO`: dốc tốc
  độ mục tiêu, hết hạn lệnh, mất liên lạc, reset chip; mức MP/giả lập ([MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md)).
  Firmware chưa có mã đọc cảm biến nên chưa có phản hồi đo được; chưa nạp bo.
- **Dòng 7.** Khuya 24/09: bản đề xuất tiêu chí N-D… và kịch bản DO (TK), chưa duyệt.
- **Dòng 8.** Đã có:
  - Dừng khi có vật mới trên đường hoặc mất LiDAR: chỉ kiểm bằng mô phỏng và nguồn quét kịch bản (MP). LiDAR thật đứng yên
    (22/09) chỉ cho thấy đỗ xong với 0 dừng giả trên cảnh tĩnh (BT), không phải bằng chứng về hành vi dừng.
  - Tối 24/09: phiên đỗ xe qua `VehicleIO` mô phỏng dừng khi telemetry/tư thế cũ và từ chối START khi trạng thái thật
    không khớp (MP). Khoảng trống an toàn khi có `Heartbeat` tìm thấy và sửa cùng tối ở mức MP (3.12b).
  - Xử lý rút cáp LiDAR trong phần mềm có test với cổng giả (TH, 4.4).
  - Khuya 24/09 (`6db5087`): START bị từ chối khi giới hạn bo lệch nguy hiểm so với cấu hình, và khi chọn bo thật mà chưa
    có nguồn tư thế (MP, cổng giả, 3.12b); cầu nối ToF (TH).
  - Đợt AI camera 25/09/2026: hộp AI camera mới trên đường làm xe ảo dừng qua MAP_CHANGED. AI không dùng được lúc chạy thì
    cảnh báo, hoặc dừng khi tích "AI bắt buộc" (camera giả, MP; 3.11b).

  Còn thiếu: đưa tay/hộp và rút cáp với LiDAR thật khi xe ảo đang chạy (cần người); rút cáp thật; thử bản sửa khoảng trống
  trên bo thật; xe. Còn một khoảng hở suy ra từ mã, chưa có test: bo vừa về ARMED mà khung báo điều đó chưa tới laptop
  (≈ 50 ms + trễ USB) thì vẫn có thể có một enable=1 (GIAO_THUC_XE mục 12; 3.12b). Chốt firmware sau `COMMAND_TIMEOUT` để
  đóng khoảng hở này đang chờ người dùng duyệt, chưa làm.
- **Dòng 9.** Watchdog ở bản tham chiếu Python (MP); ngõ vào E-stop đã chọn (TK). Tối 24/09: bảng tải, sơ đồ nguồn/dừng,
  16 kịch bản thử lỗi soạn nháp (TK, chưa thử). Hết hạn lệnh, watchdog liên lạc và logic chốt E-stop của lõi C++ còn được
  kiểm qua test host (29/09/2026). Hết hạn lệnh và mất liên lạc còn chạy trong bo ảo QEMU (30/09/2026). Tất cả đều mức MP.
  Task watchdog kích hoạt thật, `output_guard`, móc panic và ngõ vào E-stop thật chưa kiểm ở đâu
  ([GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md)).
- **Dòng 10.** Tối 24/09: ghi/phát lại phiên bàn thử; một phiên thật phát lại đúng số bộ (BT). Từ 02/10/2026: phát lại
  log lần chạy qua `VehicleIO` (T9, MP). Điều kiện vẫn chưa đạt. Mọi việc đã commit và push, nhưng kết quả độ nhạy và RA21
  hiện chỉ ở `runs/` hoặc thư mục tạm.

### Chương 5. Kết luận và hướng phát triển

**5.1. Kết luận** — *viết được khung:* những gì đã xây dựng và đo, **ở mức nào** (bảng 4.12). Các phát hiện có số đo:
- Khung MJPEG bị cắt khi ba–bốn camera chạy chung qua hub, nên chọn 480p và bộ dò.
- AI chuyển miền tốt khi trời quang nhưng yếu về đêm, với vật lạ nhỏ, và không phân biệt vỉa hè. Thêm dữ liệu khác miền
  (AVM-SS) làm hỏng miền thứ ba. Ngưỡng 0,15 là đòn bẩy rẻ nhất để giảm lỗi nguy hiểm.
- Driver LiDAR phải đóng vòng theo điểm góc. Năm quy tắc hợp nhất rút ra từ LiDAR thật.
- Từ tối 24/09/2026:
  - Quy tắc ghép bộ ảnh phải xét mỗi camera theo nhịp riêng. Các camera cùng loại có thể chạy khác nhịp (29,3 và 23,85
    khung/s), và ngưỡng theo camera nhanh nhất bỏ camera khỏe (263/855 bộ → 0/715 sau khi đổi, đo trên máy bàn).
  - Camera nào chạy ≈ 29 khung/s thì đổi giữa các lần mở (cổng 3, cổng 1, hoặc không camera nào; 4.5), nên phần mềm không
    được gắn nhịp với cổng.
  - Lô AI đầu tiên của mỗi cỡ lô tốn 1,2–1,7 s, nên phải làm nóng mọi cỡ lô. Ghi/phát lại cho thấy giá trị ngay ở phiên
    thật đầu tiên, vì nó làm lộ ra lỗi làm nóng.
  - Với định vị, tư thế ổn định qua nhiều vòng không phải bằng chứng tư thế đúng (k01).
  - Một khoảng trống an toàn do thứ tự xử lý trong một bước điều khiển được tìm thấy và sửa trong mô phỏng (3.12b, 4.8;
    mức MP, chưa thử trên bo thật).
- Từ khuya 24/09/2026 (`10a4735`, `a7cec5e`):
  - Nhãn "vô nghiệm" của hai ca lập đường khó là sai, kiểm bằng đường chứng độc lập (MP, 4.2).
  - Trên bộ sa bàn đã có, phía nguy hiểm khi kích thước xe lệch giả định là xe **dài hơn** (MP, 4.11).
  - Lỗi lạc của odometry khớp scan trên DROW chủ yếu do khóa trục cứng, không phải do thiếu odometry bánh xe (DL, 4.4).

*Chưa viết được:* kết luận về tự đỗ thật.

**5.2. Hạn chế** — gom các "giới hạn phải nói" của chương 4 và mục 1 của tệp này.

**5.3. Hướng phát triển** — theo TONG_HOP mục 5.2–5.4 và kế hoạch giai đoạn 4–10:
- đo trên laptop; sai số LiDAR và dấu góc;
- BEV: mô-đun đã có, hướng tiếp là hiệu chuẩn → gá và ngoại tham → ROI → chạy và đo sai số BEV trên sa bàn;
- ảnh sa bàn có nhãn;
- định vị: bộ định vị trên bản đồ tĩnh đã có. Hướng tiếp là tham chiếu độc lập, định vị khi di chuyển, ghép định vị trên
  bản đồ tĩnh với odometry khớp scan thành nguồn tư thế thật cho phiên `VehicleIO`, rồi mới xét SLAM;
- ghi một phiên có camera lỡ nhịp thật để so hai quy tắc ghép trên cùng dữ liệu;
- mua và tích hợp đợt 3–6; đo xe và thử nguồn/dừng theo bản nháp giai đoạn 4 và 6;
- duyệt và chạy bộ kịch bản nghiệm thu;
- mặt nạ sức khỏe ToF và bộ đếm quãng đường trong giao thức (đổi phiên bản giao thức);
- tiêu chí "thực dụng" cho đường planner: số lần đổi chiều, nhịp ngắn nhất;
- mô hình không dính WoodScape nếu chọn hướng 2 của giấy phép.

### Tài liệu tham khảo

Xem mục 5 của tệp này. Trích theo kiểu mà mẫu trường yêu cầu; chỉ đưa vào danh mục những mục thực sự được trích trong bài.

### Phụ lục (đề xuất)

| Phụ lục | Nội dung | Nguồn có sẵn |
|---|---|---|
| A | Hướng dẫn vận hành: cài đặt, lắp, chạy và dừng | [autopark/README.md](../README.md); [MAY_NOP_DO_AN.md](MAY_NOP_DO_AN.md); [GHI_PHAT_LAI_BAN_THU.md](GHI_PHAT_LAI_BAN_THU.md) mục 1–2; [CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) mục 6. Phần lắp và dừng: chưa có |
| B | Đặc tả giao thức laptop–ESP32-S3 | [GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 1–9 |
| C | Bảng số liệu chi tiết: phiên camera, bàn thử, LiDAR, AI từng seed | GIAI_DOAN_1_CAMERA mục 4; GIAI_DOAN_2_BAN_THU mục 2–5 và 10.3; GHI_PHAT_LAI_BAN_THU mục 7; DINH_VI_LIDAR mục 5; HUAN_LUYEN mục 16 |
| D | Biên bản cổng và bảng tiến độ | [GIAI_DOAN_0.md](GIAI_DOAN_0.md); [gate_01.md](gate_01.md); kế hoạch 17.4; [kiem_toan_ke_hoach_20260924.json](evidence/ke_hoach/kiem_toan_ke_hoach_20260924.json) |
| E | Giấy phép dữ liệu và ghi công | [GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md) |
| F | Danh mục dữ liệu đã khảo sát | [DANH_MUC_DATASET.md](../datasets/DANH_MUC_DATASET.md) |
| G | Kiểm kê phần cứng, sơ đồ USB, mode camera | [hardware_inventory.md](hardware_inventory.md); [usb_topology.md](usb_topology.md); [camera_modes.csv](camera_modes.csv) |
| H | Danh sách đính chính có ngày (cho thấy quy trình sửa sai) | các đoạn "Đính chính"/"Cập nhật 24/09/2026" trong tài liệu |
| I | Khai báo công cụ AI (nếu trường yêu cầu) | cần theo quy định trường |
| J | BOM đã mua thực (kế hoạch 14 "Đầu ra phải có") | [hardware_inventory.md](hardware_inventory.md) (ngày nhận, không có giá); kế hoạch mục 18 (chỉ có link). Giá và hóa đơn: chưa có |
| K | Video | Mô phỏng `runs/phase0_after_robustness/{parking,reverse,noisy,obstacle,data_loss}/simulation.mp4` (MP, 20/09, git-ignore); bàn thử và xe thật: chưa có |
| L | Kế hoạch đo MN300, phiếu kiểm kê, bảng tải, sơ đồ nguồn/dừng, kịch bản thử lỗi (bản nháp TK) | [GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md); [mn300_inventory.md](mn300_inventory.md); [GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md) |

Ghi chú cho bảng phụ lục:

- **A:** hướng dẫn gồm hai môi trường, mô phỏng, bàn thử, đo laptop; từ tối 24/09 thêm ghi/phát lại và nhánh chạy trong
  giao diện. Phần lắp cảm biến lên xe và quy trình dừng/E-stop chưa có, chờ giai đoạn 4–7; sơ đồ dừng mới là bản nháp TK ở
  [GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md) mục 3.
- **J:** BOM cần ghi thiết bị, biến thể thực giao, số lượng, nơi mua, ngày đặt/nhận, giá theo hóa đơn.
  hardware_inventory.md ghi ngày nhận LiDAR 22/09, bốn camera + hub 23/09, không có giá; kế hoạch mục 18 chỉ có link, không
  xác minh giá. Repo chưa có giá hay hóa đơn. Không tự gán tổng tiền (kế hoạch 1.3, 18).
- **K:** video mô phỏng nằm trong `runs/` nên phải sao lưu.
- **L:** thêm tối 24/09; mọi ô chưa đo, mọi phép chưa thử. Khi có số đo thì thay bằng biên bản đo.

---

## 4. Hình và bảng có sẵn

Mục này liệt kê các hình, bảng và tệp bằng chứng có thể dùng, chia hai nhóm: có trong git và chỉ có trên máy bàn.

**Trong git** (`autopark/docs/evidence/`, có trên GitHub). Mọi tệp trong bảng đã commit; các dòng xếp theo ngày thêm vào
dàn ý. Commit chứa từng nhóm tệp ở phần "Cách dùng dàn ý" đầu tệp; ví dụ `hard_cases/` trong `10a4735`, còn
`lidar/do_lap_lai_*`, `k01_kiem_suc_khoe.*` và `odometry_khop_scan_*` trong `a7cec5e`.

| Tệp | Nội dung | Ngày, mức | Dùng cho |
|---|---|---|---|
| [ui_running.png](evidence/ui_running.png), [ui_stopped.png](evidence/ui_stopped.png) | Giao diện mô phỏng đang chạy / đã dừng | 20/09, MP | 3.4, 4.2 |
| [robustness_pytest.xml](evidence/robustness_pytest.xml), [robustness_regressions_before.xml](evidence/robustness_regressions_before.xml), [robustness_test_inventory.json](evidence/robustness_test_inventory.json), [coverage_core.json](evidence/coverage_core.json), [coverage_robustness.json](evidence/coverage_robustness.json), [environment.json](evidence/environment.json) | Test và coverage giai đoạn 0 | 20/09, MP | 4.2, phụ lục |
| [pytest.xml](evidence/pytest.xml), [robustness_coverage_pytest.xml](evidence/robustness_coverage_pytest.xml), [robustness_concurrent_load_pytest.xml](evidence/robustness_concurrent_load_pytest.xml), [robustness_baseline_pytest.xml](evidence/robustness_baseline_pytest.xml) | JUnit giai đoạn 0: 169/169 của đợt đầu; 210 đạt + 10 bỏ chọn khi đo coverage; hai lượt **thất bại** giữ làm bằng chứng tải CPU (ghi chú [a] dưới bảng) | 20/09, MP | 4.2 |
| [traps_cam0.traps.json](evidence/camera/traps_cam0.traps.json), [source_cam0_720p.source.json](evidence/camera/source_cam0_720p.source.json) | Hồ sơ ba bẫy OpenCV 5 + DirectShow (camera index 0, 3 s mỗi phép) và lần chạy `UsbCameraSource` 720p MJPG (120 khung, `buffer_size_applied = false`) | 23/09, BT | 3.7, 4.5 |
| [p07_nen_phong.png](evidence/lidar/p07_nen_phong.png) (+ [.json](evidence/lidar/p07_nen_phong.json), [.analysis.json](evidence/lidar/p07_nen_phong.analysis.json)) | Vòng quét C1 và phân tích | 22/09, BT | 3.6, 4.4 |
| [map_p07.png](evidence/lidar/map_p07.png) | Bản đồ lưới tĩnh | 22/09, BT | 3.6, 4.4 |
| [drow_odom_map.png](evidence/lidar/drow_odom_map.png), [drow_odom_mirror_map.png](evidence/lidar/drow_odom_mirror_map.png), [drow_fixed_map.png](evidence/lidar/drow_fixed_map.png) | Ghép 300 vòng DROW: theo `.odom2` (sharpness 0,30) / đảo dấu góc (0,18) / giữ cảm biến cố định (0,13); lưới 24 m ô 0,1 m, tầm 10 m | 22/09 (dựng lại trùng từng pixel 24/09), DL | 4.4 |
| `evidence/camera/*.measure.json`, [report_20260923.md](evidence/camera/report_20260923.md), `usb_topology_*.json` | Phiên đo camera m*, n*, q*; sơ đồ cổng | 23/09, BT (đọc cùng đính chính GIAI_DOAN_1_CAMERA 4.6) | 3.2, 4.5 |
| [r01](evidence/camera/r01_cam0_720p_008s_small.jpg), [r02](evidence/camera/r02_cam2_720p_005s_small.jpg), [r03](evidence/camera/r03_cam0_720p_nofilm_005s_small.jpg) | Ảnh mẫu một camera (r01, r02 còn phim bảo vệ) | 23/09, BT | 4.5 |
| [khung_bi_cat_720p.jpg](evidence/rig/khung_bi_cat_720p.jpg), [day_khung_bi_cat.jpg](evidence/rig/day_khung_bi_cat.jpg), [day_khung_bi_cat_480p.jpg](evidence/rig/day_khung_bi_cat_480p.jpg), [khung_xe_480p.jpg](evidence/rig/khung_xe_480p.jpg) | Khung MJPEG bị cắt/xé | 23/09, BT | 3.7, 4.5 |
| [giao_dien_480p_thr015.jpg](evidence/rig/giao_dien_480p_thr015.jpg), [giao_dien_720p_thr015.jpg](evidence/rig/giao_dien_720p_thr015.jpg) | Giao diện bàn thử có lớp tô AI | 23/09, BT | 4.6 |
| [tham_chieu_20260924.json](evidence/may_ban/tham_chieu_20260924.json) | Tham chiếu máy bàn của lệnh đo laptop lúc 15:25: quy tắc chờ cũ, chưa làm nóng AI; từ muộn tối 24/09 chỉ giữ để đối chiếu | 24/09, BT | 4.5, 4.6, 4.10 |
| [kiem_toan_ke_hoach_20260924.json](evidence/ke_hoach/kiem_toan_ke_hoach_20260924.json) | 275 việc của kế hoạch, trạng thái, bằng chứng | 24/09 | Mở đầu, phụ lục D |
| [cho_nhip_rieng_ghi_phat_lai_20260924.json](evidence/rig/cho_nhip_rieng_ghi_phat_lai_20260924.json) | Bản rút gọn m01, m02 (`may_moi` 15:25) và o01–o07; chuỗi thời gian lô AI đầu tiên theo cỡ lô (ghi chú [b]) | 24/09 tối, BT | 4.6, 4.6b |
| [dinh_vi_p07_tren_p07.png](evidence/lidar/dinh_vi_p07_tren_p07.png), [dinh_vi_live_headless_tren_p07.png](evidence/lidar/dinh_vi_live_headless_tren_p07.png), [dinh_vi_k01_tren_p07.png](evidence/lidar/dinh_vi_k01_tren_p07.png), [dinh_vi_k01_global_tren_p07.png](evidence/lidar/dinh_vi_k01_global_tren_p07.png) + [dinh_vi_tren_p07_20260924.json](evidence/lidar/dinh_vi_tren_p07_20260924.json) | Overlay định vị p07 / live_headless / k01 / k01 `--global --every 5` trên bản đồ p07, mã đã sửa màu; tệp tóm tắt (ghi chú [c]) | 24/09 tối, BT offline trên bản ghi 22/09 và 24/09 | 3.6b, 4.4 |
| Sơ đồ nguồn và sơ đồ dừng dạng mermaid trong [GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md) mục 2–3 | Bản nháp, nhiều ô chưa chốt; vẽ lại ngày 30/09 (ghi chú [d]) | 24/09 tối, TK | 3.13 (chỉ dùng làm hình nháp, ghi rõ chưa lắp) |
| [tham_chieu_20260924_toi.json](evidence/may_ban/tham_chieu_20260924_toi.json) | Tham chiếu máy bàn trước, dùng tới 25/09/2026: `may_moi` lúc 19:08 bằng mã mới (quy tắc chờ theo nhịp riêng, làm nóng AI, `ai_warm_up_ms`); không ghi độ lệch trong bộ | 24/09 tối, BT | 4.5, 4.6, 4.10 |
| [tham_chieu_20260929.json](evidence/may_ban/tham_chieu_20260929.json) | Tham chiếu hiện dùng của lệnh đo laptop: `may_moi` lúc 12:59 trên máy bàn hiện tại (ghi chú [e]) | 29/09, BT | 4.5, 4.6, 4.10 |
| [witness_20260924.json](evidence/hard_cases/witness_20260924.json), [witness_ngan_song_song_20260924.json](evidence/hard_cases/witness_ngan_song_song_20260924.json), ảnh [parallel_122_ngan_20260924.png](evidence/hard_cases/parallel_122_ngan_20260924.png), [parallel_115_ngan_20260924.png](evidence/hard_cases/parallel_115_ngan_20260924.png), [zigzag_corridor_20260924.png](evidence/hard_cases/zigzag_corridor_20260924.png) | Đường chứng cho nhãn 16 ca khó; đường chứng ngắn 5 / 13 lần đổi chiều của hai ca đỗ song song (ghi chú [f]) | 24/09 khuya, MP (xe giả định) | 4.2 |
| [do_lap_lai_20260924.json](evidence/lidar/do_lap_lai_20260924.json), [do_lap_lai_p07_nen_phong.png](evidence/lidar/do_lap_lai_p07_nen_phong.png), [do_lap_lai_k01_kiem_suc_khoe.png](evidence/lidar/do_lap_lai_k01_kiem_suc_khoe.png), [k01_kiem_suc_khoe.png](evidence/lidar/k01_kiem_suc_khoe.png) (+ [.json](evidence/lidar/k01_kiem_suc_khoe.json), [.analysis.json](evidence/lidar/k01_kiem_suc_khoe.analysis.json)) | Độ lặp lại khoảng cách của p07, live_headless, k01 (không phải sai số so với thước); vòng quét và phân tích của k01 | Bản ghi 22/09 và 24/09, tính khuya 24/09; BT offline | 4.4 |
| [odometry_khop_scan_20260924.json](evidence/lidar/odometry_khop_scan_20260924.json) và các ảnh `odometry_khop_scan_*.png` cùng thư mục; bản trước khi sửa khóa trục giữ ở `*_khoa_cung_truoc_sua.*` | Odometry khớp scan trên tổng hợp, DROW v2 (so với `.odom2`, không phải ground truth) và C1 đứng yên | 24/09 khuya; TH, DL, BT offline | 1.6, 3.6, 4.4 |
| JUnit trong [chuyen_may_20260929/](evidence/chuyen_may_20260929/): `pytest_venv*_9d68257.xml`, `*_sau_sua_20260929.xml`, `*_38f64bb.xml`, `*_firmware_host_20260929.xml` | Toàn bộ bộ test trên máy bàn hiện tại ngày 29/09, bốn lượt (ghi chú [g]) | 29/09, MP + TH (test tự động, không chạm thiết bị) | 4.2, mục 1 ý 9, phụ lục |
| [may_moi/tom_tat.md](evidence/chuyen_may_20260929/may_moi/tom_tat.md) và các tệp cùng thư mục | `do_may_moi.cmd` trên máy bàn hiện tại (LiDAR COM3, bốn camera, AI; 202 s), so với tham chiếu 24/09 19:08; cảnh camera không ghi lại | 29/09, BT | 4.5, 4.6, 4.10 |
| [kiem_may_20260929.md](evidence/chuyen_may_20260929/kiem_may_20260929.md) | Chạy lại các lệnh README trên máy bàn hiện tại, 29/09/2026 15:08–15:19, mã `b37e9ee` (ghi chú [h]) | 29/09; BT (LiDAR, bàn thử, `may_moi`), MP (phase0), DL (chấm val, train thử) | 4.2, 4.3, 4.4, 4.6, 4.6b, 4.10 |
| [firmware_host_20260929.txt](evidence/chuyen_may_20260929/firmware_host_20260929.txt), [firmware_esp32_20260929.txt](evidence/chuyen_may_20260929/firmware_esp32_20260929.txt) | Lõi C++ qua test host: 703 check, 0 lỗi, khớp bản Python. Biên dịch firmware cho ESP32-S3 bằng PlatformIO: SUCCESS, 0 cảnh báo; chưa nạp bo | 29/09, MP (test host), TK (biên dịch) | 3.12, 4.8 |
| [bo_ao_30092026/](evidence/mo_phong_20260930/bo_ao_30092026/), [nghien_cuu/](evidence/mo_phong_20260930/nghien_cuu/), `qemu_espressif_29092026/`, `so_sanh_29092026/` trong `evidence/mo_phong_20260930/` | Firmware thật trong bo ảo QEMU; khảo sát các trình giả lập ngày 29/09 (ghi chú [i]) | 29–30/09, MP (giả lập, không phải bo thật) | 3.12, 4.8 |
| [ecoqos_30092026/](evidence/mo_phong_20260930/ecoqos_30092026/), [pytest_venv_ebbec83.xml](evidence/mo_phong_20260930/pytest_venv_ebbec83.xml), [pytest_venv_train_ebbec83.xml](evidence/mo_phong_20260930/pytest_venv_train_ebbec83.xml) và các JUnit sáng 30/09 cùng thư mục | EcoQoS làm hỏng test có hạn giờ (`uturn_w46`) khi máy gần rảnh; toàn bộ bộ test trên `ebbec83` (ghi chú [j]) | 30/09, MP + TH (test tự động, không chạm thiết bị) | 4.2, mục 1 ý 9 |

Ghi chú cho bảng:

- **[a]** Lượt chạy song song chiến dịch: 216 test, 1 lỗi, `uturn_w46` TIMEOUT sau 8,004 s. Lượt baseline có coverage
  tracer: 169 test, 1 lỗi, `uturn_w46` TRACKING_FAILED sau 8,003 s. Lượt này dùng hết ngân sách; đường tìm được ở nấc
  "ngẫu nhiên" dài 1,91 m, 21 lần đổi chiều, và cho xe mô phỏng dừng lệch 3,5 cm / −7,2°, ngoài dung sai. Chạy riêng thì
  ca này ra đường trong khoảng 3,98 s (KIEM_THU_DO_BEN mục 4).
- **[b]** m01, m02 là `may_moi` 24/09 lúc 15:25 với quy tắc trước; khác phiên camera m01, m02 ngày 23/09. o01–o07 dùng quy
  tắc theo nhịp riêng: ghi o03, phát lại o04–o06, làm nóng o07.
- **[c]** Tóm tắt gồm lệnh, tham số, hash mã, kết quả từng lần chạy. Thời gian mỗi vòng trong tệp đo khi máy bận, không
  trích. Ảnh chỉ cho độ nhất quán, chưa có tham chiếu độc lập.
- **[d]** Ngày 30/09/2026 hai sơ đồ được vẽ lại theo mã ở `ff4a018`, có màu trạng thái. Bản 24/09 ghi task watchdog
  300 ms; bản nạp vào xe (Arduino-ESP32 2.0.17) là 1 s. Một phần logic dừng nay đã kiểm ở mức MP (bản Python, test host lõi
  C++, bo ảo QEMU); phần cứng nguồn và dừng vẫn chưa lắp.
- **[e]** Máy bàn hiện tại là Dell Precision 3680, cùng cấu hình; mã `9d68257`. `digest` có quy tắc chờ, làm nóng AI và độ
  lệch bộ ảnh. Cảnh camera không ghi lại. Người dùng chọn tệp này ngày 29/09/2026 ([CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md)
  mục 2).
- **[f]** Các lần chạy planner và tái bám ở các tệp JSON cùng thư mục; thời gian đo dưới tải, không phải số đo.
- **[g]** Bốn lượt: ở `9d68257` (`.venv` 1.315 đạt, 7 bỏ qua; `.venv-train` 1.376 đạt, trùng số máy bàn trước); sau sửa
  đổi chuyển máy; ở `38f64bb`; và khi thêm test host firmware ([CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 2, 3, 6).
- **[h]** Gồm: phase0 năm phiên; ghi LiDAR 10 s ở COM3; `rig.bench --lidar` 30 s bốn camera + LiDAR + AI có ghi phiên rồi
  phát lại; một lượt `may_moi` nữa; chấm val, train thử 1 epoch. Hồ sơ gốc git-ignore ở `runs/kiem_may_20260929/`.
- **[i]** Lệnh `qemu_board kiem`; 10 lượt chạy lặp `tests/test_firmware_qemu.py` gồm 13 test, 6 trong đó chạy firmware thật
  trong QEMU ([MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md)).
- **[j]** `.venv` 1.380 đạt, 8 bỏ qua; `.venv-train` 1.442 đạt; 0 hỏng ([CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 8).

**Không có trong git** (`autopark/runs/`, chỉ trên máy bàn, **phải sao lưu trước**):
- video mô phỏng `runs/phase0_after_robustness/*/simulation.mp4` và `summary.json`; chiến dịch
  `runs/robustness_final_2026-09-20/`;
- ảnh và chỉ số AI `runs/ai_woodscape_rtx4000_v1/eval_val/`, `eval_test/`, `eval_acdc_val/`,
  `eval_val_sweep/threshold_sweep.json`, `export/export_report.json`, `benchmark.json`;
- costmap và kiểm chiếu `runs/perception_integration/` (`costmap_*/costmap_textured.png`, `ipm_check_*`,
  `drow_scan_person.png`);
- bản ghi LiDAR `runs/lidar_bench/`; bàn thử `runs/rig_bench/`; bộ ảnh `runs/rig_snapshots/`;
- đo máy bàn `runs/may_moi_20260924_may_ban/` (15:25) và `runs/may_moi_20260924_toi/` (19:08);
- đo lại quy tắc ghép và phát lại `runs/rig_bench/20260924_own/`; bản ghi bàn thử `runs/rig_recordings/o03_20260924/`
  (≈ 300 MB);
- độ nhạy theo kích thước xe `runs/do_nhay_xe/` ([DO_NHAY_KICH_THUOC_XE.md](DO_NHAY_KICH_THUOC_XE.md)). Hồ sơ
  RoadAnomaly21 chưa có trong `runs/` (4.3).

**Chỉ ở thư mục tạm, có thể đã mất.** Đầu ra BEV (`bev.png`, `stats.json` của các lệnh `synthetic`/`woodscape`) và
`localize.json`/`track.csv` đầy đủ từng vòng của định vị trên bản ghi thật được ghi ra **thư mục tạm của phiên làm việc**,
không nằm trong `runs/` hay `docs/evidence/`. BEV.md mục 6 chỉ ghi "nằm ngoài repo", không ghi đường dẫn; thư mục
`runs/bev/` chưa tồn tại. Tạo lại bằng lệnh ở [BEV.md](BEV.md) mục 5 (mặc định ghi vào `runs/bev/<tên>/`) và
[DINH_VI_LIDAR.md](DINH_VI_LIDAR.md) mục 3 (dùng mã đã sửa màu overlay), rồi sao lưu. Với định vị, bốn ảnh overlay tạo lại
bằng mã đã sửa và tệp tóm tắt đã có trong `docs/evidence/lidar/` (`b100a5d`, bảng trên).

**Giấy phép của ảnh trong hình:**
- **Ảnh WoodScape** (costmap, kiểm chiếu, ảnh lỗi của tập test): phải kèm ghi công.
  - Điều khoản trích ở GIAY_PHEP_DU_LIEU cho phép dùng cho "academic or applied research publication". Toàn văn điều khoản
    (2 trang) có trong repo: `datasets/woodscape_metadata/LICENSE.pdf` (đọc 24/09). Bản này cho phép dùng cho nghiên
    cứu/công bố công khai không thu phí. Nó buộc mọi tài liệu công khai nhắc tới nghiên cứu dùng bộ dữ liệu phải hiển thị
    rõ ghi chú rằng nghiên cứu đã dùng Valeo WoodScape Dataset, kèm link tới trang bộ dữ liệu.
  - Bản này **không có điều khoản riêng** cho phép hay cấm in lại ảnh. Vì vậy việc in ảnh trong khóa luận là cách hiểu
    điều khoản, **cần GVHD chốt** (chưa chốt).
  - Link: LICENSE.pdf ghi bộ dữ liệu có tại `woodscape.valeo.ai`, còn README của repo WoodScape dùng `woodscape.valeo.com`.
    Kiểm trên web ngày 25/09: `woodscape.valeo.ai` chuyển 301 tới `woodscape.valeo.com`, còn `.com` là một trang Valeo không
    có nội dung WoodScape; không địa chỉ nào còn là trang bộ dữ liệu. Đề xuất, chưa chốt: link trong khóa luận là
    <https://github.com/valeoai/WoodScape>, ghi địa chỉ cũ dạng chữ để lưu vết. Valeo chưa xác nhận đây là "Dataset
    website". Dòng ghi công đầu tệp này đã đổi theo. Chi tiết: [GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md) mục "Kiểm trên
    web ngày 25/09/2026" và "Ghi công: link tới trang bộ dữ liệu".
- **Ảnh ACDC:** chỉ mục đích phi thương mại (License.pdf mục 1.1); ảnh đã ẩn danh (`_anon`).
- **Ảnh RoadObstacle21:** giấy phép **chưa xác minh**, nên không đưa ảnh vào khóa luận khi chưa tra.
- **Ảnh AVM-SS:** không có giấy phép (tác giả giữ toàn quyền), nên không in lại ảnh khi chưa hỏi tác giả.
- **Hình dựng từ DROW v2:** drow_odom_map.png, drow_odom_mirror_map.png, drow_fixed_map.png, và drow_scan_person.png trong
  `runs/perception_integration/`. Cả bốn dựng từ bản ghi val `run_2015-11-25-10-34-20-a` (GIAI_DOAN_1_LIDAR mục 5;
  GIAI_DOAN_1_CHUAN_BI mục 4), không thuộc phần `reha`; kiểm 24/09, bản tải về không có tệp nào tên chứa `reha`. Vì vậy
  chúng theo MIT, và phải ghi công bằng cách trích **cả hai** bài DROW (D6) theo README tác giả ("please cite **both**").
  Các ảnh `odometry_khop_scan_drow_*.png` trong `evidence/lidar/` (khuya 24/09) cũng dựng từ DROW v2, chuỗi `10-34-20-a`
  và `13-47-42` thuộc bản tải về không có phần `reha`, nên theo cùng quy tắc. GIAY_PHEP_DU_LIEU.md mục "DROW: ghi công khi
  dùng hình" đã liệt kê bốn hình `odometry_khop_scan_drow_*` (từ `89cd58f`). Nếu sau này có hình dựng từ phần `reha` thì
  theo CC BY-NC-SA 3.0.
- **Ảnh tự chụp trên bàn/sa bàn:** không vướng giấy phép dữ liệu.
- **BEV và overlay định vị (từ tối 24/09/2026):** BEV minh họa dựng từ ảnh WoodScape (lệnh `woodscape` của
  `perception.bev`) theo cùng quy tắc với ảnh WoodScape ở trên. `bev.png` của rig tổng hợp và `overlay.png` của bộ định vị
  (dựng từ bản ghi LiDAR tự ghi, gồm cả bốn ảnh `dinh_vi_*.png` trong `evidence/lidar/`) không vướng giấy phép dữ liệu.
  Mọi đầu ra AI dùng mô hình huấn luyện trên WoodScape vẫn chịu điều khoản ở mục 1, ý 4.

## 5. Tài liệu tham khảo đã dùng trong dự án

Cột "Điều đã biết" chỉ ghi những gì có trong repo (tài liệu, mã, README đi kèm dữ liệu). "Gợi ý để tra" là tên người viết
dàn ý nhớ, **chưa đối chiếu** với bản gốc; phải tra trước khi đưa vào danh mục.

### 5.1. Bộ dữ liệu

| Mã | Tài liệu | Dùng ở đâu | Điều đã biết (nguồn) | Trạng thái |
|---|---|---|---|---|
| D1 | **WoodScape** (Valeo) | Huấn luyện lượt nền; ROI; kiểm quy ước calibration; costmap trên ảnh | 8.234 cặp RGB–semantic; bài báo Yogamani và cs., arXiv:1905.01489, 2019; giấy phép Valeo riêng, bắt buộc ghi công (ghi chú D1) | Trích được (bản arXiv hoặc ICCV 2019 theo README); số trang/DOI kỷ yếu ICCV: **cần tra** |
| D2 | **ACDC** (ETH Zürich) | Chấm ngoài miền (val 406 ảnh, val_ref); cache huấn luyện phần III | 4.006 ảnh sương/đêm/mưa/tuyết, 19 lớp (DANH_MUC B06); phi thương mại (ghi chú D2) | Mục trích dẫn chính xác: **cần tra** |
| D3 | **RoadObstacle21** (benchmark SegmentMeIfYouCan) | Chấm vật lạ, 30 ảnh validation | Bài báo SegmentMeIfYouCan, NeurIPS 2021 Datasets and Benchmarks Track (ghi chú D3) | Trích bài báo được; **giấy phép dữ liệu chưa xác minh** |
| D4 | RoadAnomaly21 (cùng benchmark) | Chấm 10 ảnh `validation*` có nhãn từ khuya 24/09 (4.3; mã trong `77eb51f`) | Giấy phép theo từng ảnh (`LICENSE.txt`) | Đã dùng nên phải trích (bài báo SMIYC như D3); in ảnh thì theo giấy phép từng ảnh, chưa tra |
| D5 | **AVM-SS** (repo `Engro39/avm_dataset`) | Huấn luyện thử phần III | 6.763 cặp 320×160; split của tác giả rò rỉ khung liền kề (bỏ, chia lại); 7.071 pixel màu ngoài palette; không có tệp LICENSE, GitHub API `license: null` | Bài báo gốc: **cần tra**; không có giấy phép |
| D6 | **DROW v2** | Nguồn phát lại LiDAR, kiểm chiều góc, thử ghép odometry | 113 tệp scan, 464.023 dòng; MIT, riêng phần `reha` CC BY-NC-SA 3.0; README yêu cầu trích **cả hai** bài (ghi chú D6) | v2: đủ để trích; v1: tập/số/trang có trong README, **năm và tên chính xác: cần tra** |
| D7 | Lược đồ nhãn Cityscapes | Ánh xạ nhãn ACDC → FREE/BLOCKED ([acdc_cityscapes_to_binary_v1.json](../configs/acdc_cityscapes_to_binary_v1.json)) | ACDC dùng nhãn kiểu Cityscapes 34 lớp (HUAN_LUYEN mục 8) | Bài báo Cityscapes: **cần tra** |
| D8 | Các bộ/nhánh còn lại trong danh mục 44 mục | Khảo sát, không dùng | [DANH_MUC_DATASET.md](../datasets/DANH_MUC_DATASET.md) | Chỉ trích nếu viết về chúng ở chương 1 |
| D9 | COCO (qua trọng số tiền huấn luyện torchvision), dùng gián tiếp | Khởi tạo mọi lượt huấn luyện qua trọng số `COCO_WITH_VOC_LABELS_V1` (ghi chú D9) | Repo chỉ có tên trọng số và một câu trong HUAN_LUYEN mục 2.3 (ghi chú D9) | Bài báo COCO, Pascal VOC, điều khoản trọng số torchvision: **cần tra** (ghi chú D9) |

Ghi chú cho bảng 5.1:

- **D1.** Tên bài: Yogamani và cs., "WoodScape: A multi-task, multi-camera fisheye dataset for autonomous driving",
  arXiv:1905.01489, 2019. README ghi ICCV 2019 (Oral); BibTeX tác giả đề nghị trỏ arXiv:1905.01489 (`@article`,
  `datasets/woodscape_metadata/README.md`). Giấy phép Valeo riêng, toàn văn ở `datasets/woodscape_metadata/LICENSE.pdf`;
  MIT của mã không áp dụng cho ảnh. Bắt buộc ghi công. Điều khoản chỉ cho dùng phi thương mại và có câu không cho dùng mô
  hình trong vận hành phương tiện; dự án đọc câu đó là ví dụ của dùng thương mại (quyết định 25/09/2026), Valeo chưa xác
  nhận (GIAY_PHEP_DU_LIEU; mục 1, ý 4). Không viết gọn là "cấm dùng mô hình để vận hành phương tiện", vì mạnh hơn văn bản.
  Link trích: <https://github.com/valeoai/WoodScape> (đề xuất, chưa chốt).
- **D2.** License.pdf mục 1.1: phi thương mại, không có điều khoản phương tiện. README trong `datasets/training/acdc/gt/`
  nêu Christos Sakaridis, Haoran Wang, Dengxin Dai và yêu cầu trích theo trang citation của ACDC.
- **D3.** Bài báo: Chan, Lis, Uhlemeyer, Blum, Honari, Siegwart, Fua, Salzmann, Rottmann, "SegmentMeIfYouCan: A Benchmark
  for Anomaly Segmentation", NeurIPS 2021 Datasets and Benchmarks Track. BibTeX có trong README mã benchmark đã tải
  (`datasets/benchmark_tools/`).
- **D6.** Nguồn: `datasets/drow/README_source.md`. Hai bài cần trích:
  - (v1) Beyer, Hermans, Leibe, "DROW: Real-Time Deep Learning-Based Wheelchair Detection in 2-D Range Data", IEEE RA-L
    2(2), 585–592. README tự vênh: câu trích dạng văn bản ghi năm 2017, còn BibTeX (khóa `BeyerHermans2016RAL`) ghi
    `year = {2016}`, không có tập/trang, và viết tên hơi khác ("based … 2D"). Cần tra: 2016 bản trực tuyến hay 2017 số tạp
    chí?
  - (v2) Beyer, Hermans, Linder, Arras, Leibe, "Deep Person Detection in 2D Range Data", RA-L 3(3), 2018, 2726–2733.
- **D9.** Nơi dùng: `perception/model.py`; `initialization` mặc định trong `perception/train.py`. Kiểm 24/09, cả 12 thư mục
  `runs/ai_*` ghi `torchvision_official_pretrained_weights` trong `config_resolved.json`. Repo chỉ có tên trọng số và câu
  "trọng số pretrained chính thức của Torchvision (COCO)" (HUAN_LUYEN mục 2.3); không lưu bài báo, điều khoản của trọng số
  hay giấy phép ảnh COCO. Theo tên trọng số, nhãn theo lớp Pascal VOC: cần tra. Gợi ý để tra: COCO của Lin và cs., 2014;
  Pascal VOC của Everingham và cs., 2010.

### 5.2. Thuật toán, phương pháp

| Mã | Tài liệu | Dùng ở đâu | Điều đã biết (nguồn) | Trạng thái |
|---|---|---|---|---|
| A1 | **Reeds & Shepp (1990)**, đường tối ưu cho xe đi được cả tiến và lùi | `planning/reeds_shepp*.py`, các ứng viên `cand_*_rs.py` | Mã dẫn "Reeds & Shepp (1990), mục 8.1–8.11": 9 công thức gốc, ba phép đối xứng, 48 từ đường | Tên bài, tạp chí, trang: **cần tra** |
| A2 | **Hybrid A\*** | `planning/hybrid_astar.py`, `cand_reference.py` | Mã không trích nguồn | **Cần tra** (gợi ý để tra: Dolgov và cs.) |
| A3 | **RRT-Connect** | `planning/cand_rrt_rs.py` (nấc 3 của thang) | Mã không trích nguồn | **Cần tra** (gợi ý: Kuffner và LaValle) |
| A4 | Lưới trạng thái có thao tác gộp | `planning/cand_lattice_macro.py` (nấc 1–2) | Thiết kế của dự án; mã không trích nguồn lý thuyết lưới trạng thái | **Cần tra** nếu gọi tên "state lattice" |
| A5 | PythonRobotics; OMPL | Cách tổ chức phép đối xứng Reeds–Shepp (docstring `reeds_shepp.py`, `cand_rs_roadmap_rs.py`, `cand_lattice_macro_rs.py`) | Chỉ có tên | Đường dẫn, phiên bản: **cần tra** |
| A6 | Pure Pursuit | Chỉ được nhắc trong docstring `control/tracker.py` để giải thích vì sao cần δ_ff; chưa có cài đặt hay phép so sánh đo được | Luật bám của dự án có feedforward độ cong, khác Pure Pursuit thuần | **Cần tra** nếu trích |
| A7 | Định lý trục tách (SAT) | `geometry/fast_collision.py`, `evaluation/collision_oracle.py` | Chỉ có tên | Nguồn giáo trình: **cần tra** |
| A8 | Mô hình xe đạp động học | Kế hoạch mục 4; `simulation/vehicle.py` | Công thức có trong kế hoạch | Nguồn giáo trình: **cần tra** |
| A9 | **MobileNetV3 / L-RASPP** | `perception/model.py` | Triển khai torchvision `lraspp_mobilenet_v3_large`, trọng số `COCO_WITH_VOC_LABELS_V1` (dữ liệu tiền huấn luyện: D9) | Bài báo gốc: **cần tra** (gợi ý: Howard và cs., "Searching for MobileNetV3", 2019) |
| A10 | AdamW; lịch warmup + poly; huấn luyện độ chính xác hỗn hợp (AMP) | `perception/train.py` | Cấu hình ở HUAN_LUYEN mục 2.7 | **Cần tra** |
| A11 | mIoU; F-beta (F2) để chọn ngưỡng | `perception/metrics.py`, `evaluate.py --sweep` | Định nghĩa dùng trong HUAN_LUYEN mục 10 | Nguồn định nghĩa: **cần tra** nếu trường yêu cầu |
| A12 | **Mô hình fisheye Kannala–Brandt** (qua `cv2.fisheye`) | `perception/fisheye_calib.py` | 4 hệ số, chỉ biểu diễn tia lệch trục < 90° (HIEU_CHUAN_CAMERA mục 1) | Bài báo gốc: **cần tra** (gợi ý: Kannala và Brandt, 2006) |
| A13 | Mô hình đa thức fisheye của WoodScape | `perception/calibration.py` | Quy ước đọc từ `readme.txt` trong `calibration.zip` (GIAI_DOAN_1_CHUAN_BI mục 2) | Trích qua D1 |
| A14 | Lặp Lawson (xấp xỉ minimax) | Chuyển K, D sang đa thức dự án | Chỉ có tên trong mã | **Cần tra** |
| A15 | Băm tri giác pHash/dHash để dò ảnh gần trùng | `perception/data.py`, `prepare_extra.py`, `labels.py` | Mã tự viết bằng OpenCV | **Cần tra** nếu trích |
| A16 | Bản đồ lưới chiếm chỗ bằng ray casting | `lidar/occupancy.py` | Thiết kế của dự án (không cập nhật xác suất) | Nguồn lý thuyết: **cần tra** |
| A17 | **COBS** | `transport/protocol.py`, firmware | Mã dẫn "Cheshire & Baker 1999" | Tên bài, nơi đăng: **cần tra** |
| A18 | CRC-16/CCITT-FALSE | Giao thức xe | Đa thức 0x1021, khởi tạo 0xFFFF, không đảo bit, không XOR cuối, `CRC("123456789") = 0x29B1` (GIAO_THUC_XE mục 1) | Nguồn danh mục tham số CRC: **cần tra** |
| A19 | Kiểm thử đột biến | GIAO_THUC_XE mục 11 | Làm bằng script ngoài repo trên bản sao gói | **Cần tra** nếu trích phương pháp |
| A20 | Hệ tọa độ xe ISO 8855 | Quy ước tọa độ | Nhắc trong quy ước WoodScape (GIAI_DOAN_1_CHUAN_BI mục 2) | Tiêu chuẩn: **cần tra** |
| A21 | Khớp scan tương quan trên lưới, nhánh-cận nhiều mức (*thêm tối 24/09*) | `lidar/localize.py` | Tài liệu và docstring chỉ ghi "theo cách của Cartographer"/"kiểu Cartographer", không trích bài | **Cần tra** (gợi ý: Hess và cs., 2016, bài về đóng vòng thời gian thực trong SLAM LiDAR 2D của Cartographer; Olson, 2009, khớp scan tương quan) |
| A22 | Trường khả năng (likelihood field) cho mô hình đo khoảng cách (*thêm tối 24/09*) | `lidar/localize.py` | Dùng exp(−d²/2σ²) trên khoảng cách tới ô OCCUPIED gần nhất (DINH_VI_LIDAR mục 2); mã không trích nguồn | **Cần tra** (gợi ý: giáo trình Probabilistic Robotics của Thrun, Burgard, Fox) |
| A23 | Gauss-Newton, Levenberg–Marquardt, trọng số Cauchy (M-estimator) (*thêm tối 24/09*) | Tinh chỉnh tư thế trong `lidar/localize.py` | Chỉ có tên phương pháp | Nguồn giáo trình: **cần tra** |
| A24 | Chiếu nhãn ảnh xuống mặt sàn thành lưới chiếm chỗ nhìn từ trên (BEV) (*thêm tối 24/09*) | `perception/bev.py`, `perception/costmap.py` | Quy tắc là thiết kế của dự án (BEV.md mục 2); tài liệu không gọi tên phương pháp nào | **Cần tra** nếu gọi tên (ví dụ "inverse perspective mapping") hay so với phương pháp BEV khác |

### 5.3. Thiết bị và tài liệu nhà sản xuất

| Mã | Tài liệu | Điều đã biết (nguồn) | Trạng thái |
|---|---|---|---|
| H1 | **RPLIDAR C1 (C1M1), datasheet rev 1.1** và sổ tay C1 (SLAMTEC) | Các số datasheet đã dùng (ghi chú H1); thiết bị tự báo model 0x41, firmware 1.2, phần cứng 18 | **Repo không lưu bản PDF**: lưu bản sao, ghi đường dẫn và ngày tải; giao thức SLAMTEC: cần tra tài liệu gốc |
| H2 | Camera "HD Camera" VID 1BCF (Sunplus) PID 0B09 | Không có serial; mode đọc từ DirectShow ([camera_modes.csv](camera_modes.csv)); 130° là số nhà bán (kế hoạch 18, listing AdaChoi) | Không có datasheet; chỉ dẫn được số tự đo |
| H3 | Hub UGREEN 4 cổng, chip Genesys Logic 05E3:0610 / 05E3:0626 | [usb_topology.md](usb_topology.md); kế hoạch nêu UGREEN 50985 là ứng viên | Mã model thực giao chưa ghi |
| H4 | Silicon Labs CP2102N | Driver CP210x 11.6.0.420 trên máy bàn tới 25/09/2026 (nơi đo mọi số LiDAR tới ngày đó); 11.2.0.167 trên máy bàn từ 29/09/2026 ([chuyển máy](CHUYEN_MAY_BAN.md)); hardware_inventory | Đủ để ghi |
| H5 | ESP32-S3, Arduino-ESP32 (2.x/3.x), ESP-IDF | Firmware biên dịch được với Arduino-ESP32 2.0.17 và 3.3.12 (29/09/2026); `esp_task_wdt_init` đã đối chiếu IDF 4.4 (ghi chú H5) | **Cần tra** tài liệu LEDC, móc panic trước khi nạp |

Ghi chú cho bảng 5.3:

- **H1.** Số đã dùng (hardware_inventory, GIAI_DOAN_1_LIDAR): 8–12 Hz (10 Hz thường), 5 kHz mẫu, bước góc 0,72°, 0,05–12 m;
  UART 460800 bps 8N1 TTL 3,3 V; 5 V, khởi động 800 mA, làm việc 230 (max 260) mA; đầu nối XH2.54-5P; hướng trước là trục
  x hình 2-4; góc tăng theo chiều kim đồng hồ.
- **H5.** Lời gọi `esp_task_wdt_init` đã đối chiếu `esp_task_wdt.h` của IDF 4.4 (30/09/2026). API LEDC và móc panic **chưa
  đối chiếu tài liệu** (GIAO_THUC_XE mục 12).
| H6 | MN300 Tank300, BNO085, VL53L1X, AS5600, MT6701, LA38, UBEC/XL4015 | Chưa nhận; chỉ có link mua (kế hoạch 18) | Datasheet: **cần tra** khi dùng |

### 5.4. Phần mềm và thư viện

Python 3.12.10; PyTorch 2.11.0+cu128, torchvision 0.26.0+cu128; OpenCV (`opencv-python` 5.0.0.93); NumPy 2.5.2; Shapely
2.1.2; PySide6 6.11.2; pyserial 3.5; pygrabber 0.2; onnx 1.23.0, onnxruntime 1.30.0; psutil 7.2.2; nvidia-ml-py 13.610.43;
pytest 9.1.1; coverage 7.16.1 (các tệp khóa [requirements-phase0.lock](../requirements-phase0.lock),
[requirements-train.lock](../requirements-train.lock)). Trích phần mềm hay không, và trích thế nào: theo mẫu trường.

Shapely 2.1.2 lúc đầu chỉ có trong `.venv`. Ngày 25/09/2026 nó được cài thêm vào `.venv-train` với sự đồng ý của người
dùng, và `requirements-train.lock` có dòng `shapely==2.1.2`, để phiên đỗ xe và AI camera chạy chung một tiến trình.

### 5.5. Tài liệu nội bộ

Kế hoạch v3.1 và các biên bản trong repo là **hồ sơ của chính đề tài**, không phải tài liệu tham khảo. Nên đặt ở phụ lục
hoặc dẫn như hồ sơ thí nghiệm (kèm commit), theo mẫu trường.

## 6. Câu dễ viết sai và câu đúng theo bằng chứng

Mỗi ý dưới đây gồm câu không nên viết (in đậm), lý do, và câu nên viết thay. Các ý gom theo chủ đề.

**Tự đỗ, mô phỏng, lập đường**

- **"Hệ thống tự đỗ được xe MN300"**. Vì sao: chưa có xe. Viết: "Tự đỗ mới kiểm chứng trong mô phỏng với thông số xe giả
  định (20/09/2026)".
- **"Tỉ lệ đỗ thành công 25/240"**. Vì sao: 240 phiên là chiến dịch cố tình chèn lỗi. Viết: "240 phiên kín vòng có lỗi
  giả: 25 COMPLETED, 185 STOPPED đúng logic, 30 FAULT do chèn vật quá gần".
- **"Ca `parallel_115` vô nghiệm"** hay **"planner giải mọi ca khó"**. Vì sao: nhãn cũ sai, ca này có đường chứng 13 lần
  đổi chiều; planner vẫn TIMEOUT/NO_PATH ở ca này. Viết: "Cả 16 ca khó có đường chứng kiểm độc lập trong mô hình planner;
  planner hiện chưa tìm được đường cho vài ca trong ngân sách (giới hạn của planner, mô phỏng)".
- **"Planner chịu được xe lệch ±20 % kích thước"**. Vì sao: chỉ 11/20 sa bàn giải được ở mọi biến thể; xe dài hơn làm hỏng
  vài sa bàn; mô phỏng, dưới tải, xe giả định. Viết: "Trong mô phỏng, quanh xe giả định, 11/20 sa bàn giải được ở mọi biến
  thể ±5/10/20 %; các cặp hỏng lặp lại đều là xe dài hơn 10–20 %".
- **"Xe dừng trong 0,39 s / 3,9 cm"** (hay 0,43 s / 4,1 cm, 0,18 s / 0,9 cm của phiên `VehicleIO` mô phỏng, tối 24/09).
  Vì sao: số của mô hình giả định. Viết: "Trong mô phỏng với số giả định…; quãng dừng thật chưa đo".

**AI và giấy phép**

- **"Mô hình đạt mIoU 0,969"** (không kèm điều kiện). Vì sao: trong phân phối, split nội bộ, không phải split chính thức,
  không phải sa bàn. Viết: "mIoU 0,9692 trên tập test giữ riêng của split nội bộ WoodScape; chưa chấm trên ảnh sa bàn".
- **"AI phát hiện vật cản quanh xe"**. Vì sao: từ 25/09/2026 phần mềm đã nối AI camera vào phiên đỗ xe, nhưng chưa camera
  nào được hiệu chuẩn, AI chưa tạo vật cản nào trên bàn thật và chưa được chấm trên ảnh sa bàn; lớp tô của bàn thử chỉ để
  nhìn. Viết: "Phần mềm đưa AI camera vào phiên đỗ xe làm nguồn vật cản phụ đã có, mới kiểm bằng nguồn giả, rig tổng hợp
  và phát lại; chưa chạy với camera đã hiệu chuẩn, chưa đo phát hiện hay báo giả trên sa bàn" (3.11b).
- **"Giấy phép WoodScape cho phép dùng mô hình trên xe"** hay **"giấy phép cấm dùng mô hình trên xe"**. Vì sao: văn bản
  không tự phân định hai cách đọc; Valeo chưa xác nhận. Viết: "Điều khoản chỉ cho dùng phi thương mại và có vế không cho
  dùng mô hình trong vận hành phương tiện; khóa luận đọc vế đó là ví dụ của dùng thương mại; cách đọc này chưa được Valeo
  xác nhận" (mục 1, ý 4; GIAY_PHEP_DU_LIEU.md mục "Khóa luận nên viết gì").
- **"Suy luận 16,4 ms"** (không kèm máy). Vì sao: đó là máy bàn RTX 4000 Ada. Viết: "…trên máy bàn; laptop RTX 3050 Ti
  chưa đo".
- **"Thêm AVM-SS cải thiện ban đêm"**. Vì sao: kết luận này đã rút lại sau ba seed. Viết: "Trộn AVM-SS làm lỗi nguy hiểm
  trên ACDC tăng 4,1 → 13,5 %".
- **"Mô hình nhận ra 89,6 % vật bất thường"**. Vì sao: mô hình cũng gọi BLOCKED ≈ 62 % pixel nền; chỉ 10 ảnh; không so được
  với SMIYC. Viết: "Trên 10 ảnh có nhãn của RoadAnomaly21, 10,4 ± 1,2 % pixel vật bất thường bị gọi FREE ở ngưỡng 0,50 (ba
  seed); mô hình gọi BLOCKED phần lớn nền không phải mặt đường, nên con số này không đo khả năng nhận ra vật lạ".

**Camera, bàn thử, BEV**

- **"Camera 130°, 30 fps"**. Vì sao: 130° là số nhà bán; 30 fps là mode công bố; số FPS thật khác nhau giữa camera và
  giữa phiên. Camera nhanh không cố định một cổng: cổng 3 ở s01–s07, t01, t02 ngày 23/09; cổng 1 ở t05 (23/09) và lúc
  15:25, 17:56 ngày 24/09; không camera nào lúc 19:08. Viết: "Góc nhìn chưa đo; ở phơi sáng tự động thường ≈ 23,85
  khung/s; ở một số lần mở, một camera chạy ≈ 29 khung/s, camera nào thì thay đổi giữa các lần mở; chưa đạt 30 fps đều ở
  chế độ nào; cơ chế chưa xác định".
- **"Bốn camera chạy được ở 720p"**. Vì sao: 23/09 cảnh sáng, hai–ba camera bị cắt phần lớn khung; w03/w04 và o01 (tối
  24/09) chỉ là cảnh tối. Viết: "Qua hub này, bốn camera dùng được ở 640×480 kèm bộ dò khung hỏng".
- **"Quy tắc không chờ giảm độ trễ AI"**. Vì sao: cơ chế chưa giải thích; không phiên nào có camera chậm; có trường hợp
  bỏ camera khỏe (263/855 bộ, tham chiếu 24/09). Viết: nêu cả số đo w01–w05 và trường hợp tham chiếu, kèm "lợi ích chính
  chưa thấy trên phần cứng"; nêu thêm quy tắc theo nhịp riêng và số đo lại o01/o02 (ý dưới).
- **"Quy tắc ghép mới không bao giờ bỏ camera khỏe"**. Vì sao: hai phiên đo lại có camera nhìn chỗ tối, không khung hỏng
  nào; nhánh camera lỡ nhịp chỉ kiểm bằng mô phỏng; trong mô phỏng vẫn còn 2,1–2,5 % số bộ bị để dành. Viết: "Trong hai
  phiên đo lại tối 24/09 trên máy bàn, quy tắc theo nhịp riêng không bỏ camera khỏe nào (0/715 ở 720p, 0/2.862 ở 480p);
  ở 720p độ lệch trong bộ lớn hơn (max 52,8 so với 40,3 ms); nhánh camera lỡ nhịp mới kiểm bằng mô phỏng".
- **"Làm nóng AI mất 4,2 s"** hay **"lô AI đầu 1,4 s"** (không kèm máy). Vì sao: đó là số của GPU máy bàn, và hai con số
  bị hiểu sai.
  - 4,2 s không phải thời gian làm nóng mà là phần AI sẵn sàng **chậm thêm so với trước** (GIAI_DOAN_2_BAN_THU mục 10.3).
  - Bốn lô làm nóng (4, 3, 2, 1 ảnh) mất 1682,9 / 1444,2 / 1467,5 / 1282,9 ms ở o06, tổng ≈ 5,9 s (o06 5.877 ms, o07
    5.869 ms; `ai.warm_up_ms` trong
    [cho_nhip_rieng_ghi_phat_lai_20260924.json](evidence/rig/cho_nhip_rieng_ghi_phat_lai_20260924.json)). Lần `may_moi`
    19:08 cho 1482 / 1448 / 1553 / 1410 ms, tổng cũng ≈ 5,9 s.
  - 1,4 s chỉ là lô 3 ảnh đầu tiên; lô đầu mỗi cỡ lô 1,2–1,7 s.

  Viết: "Trên máy bàn RTX 4000 Ada, làm nóng mọi cỡ lô (4, 3, 2, 1 ảnh) mất ≈ 5,9 s (tổng `ai.warm_up_ms`, o06/o07); AI
  sẵn sàng chậm hơn ≈ 4,2 s so với trước; lô AI đầu tiên của mỗi cỡ lô tốn 1,2–1,7 s; laptop RTX 3050 Ti chưa đo".
- **"Khung hỏng không tới AI"**. Vì sao: bộ dò có điểm mù. Viết: "Bộ dò loại các khung hỏng dạng đã biết; còn điểm mù
  (…)".
- **"BEV chạy thời gian thực, ≈ 8 ms"**. Vì sao: số đo trên rig tổng hợp, máy bàn, khi nhiều tiến trình khác chạy; khung đầu
  0,3–0,5 s; chưa có camera dự án; laptop chưa đo. Viết: "Trên rig bốn camera tổng hợp, máy bàn, BEV mất ≈ 7–12 ms mỗi
  khung sau khi dựng bảng, kết quả trùng từng bit với bản trước khi tăng tốc; chưa chạy trên camera dự án, laptop chưa đo".
- **"Ngoại tham camera sai số < 1°"**. Vì sao: chỉ ảnh tổng hợp; chưa camera nào được đo; sai số thước chưa đo. Viết: "Trên
  ảnh tổng hợp, với nhiễu thước ±2,5 mm mỗi điểm, hướng camera lệch tới 0,93°; chưa đo camera thật nào".
- **"Hệ thống có BEV quanh xe"**. Vì sao: chưa hiệu chuẩn camera nào; ngoại tham giả định; mới chạy trên rig tổng hợp và
  ảnh WoodScape (không có bộ bốn camera đồng bộ). Viết: "Mô-đun BEV đã kiểm trên rig bốn camera tổng hợp; chưa chạy trên
  camera của dự án; sai số BEV chưa đo".
- **"Phát lại tái hiện đúng phiên thật"**. Vì sao: một phiên; AI không trùng từng bit; không tái tạo USB/CPU. Viết: "Phát
  lại một phiên 60 s cho đúng số bộ và phân bố độ lệch trong bộ của phiên thật; kết quả AI không trùng từng bit vì JPEG mã
  hóa lại".
- **"Hiệu chuẩn camera đạt RMS 0,071 px"**. Vì sao: đó là ảnh tổng hợp. Viết: "Trên ảnh tổng hợp; chưa hiệu chuẩn camera
  thật nào".

**LiDAR và định vị**

- **"LiDAR sai số ± 1,5 mm"**. Vì sao: 1,0–1,5 mm là độ lặp lại giữa hai vòng liên tiếp (ban đầu từ script tạm, nay
  `lidar/repeatability.py` cho lại đúng số). Viết: "Sai số khoảng cách so với thước chưa đo".
- **"Có bản đồ và định vị bằng LiDAR"**. Vì sao: bản đồ lưới tĩnh từ một vị trí; định vị mới có độ nhất quán, chưa có tham
  chiếu độc lập. Viết: "Bản đồ lưới tĩnh từ LiDAR đứng yên; định vị lại trên bản đồ đó nhất quán ở cùng chỗ và báo hỏng
  khi LiDAR đã dời chỗ (bản ghi 22/09, 24/09, chạy offline); sai số so với tham chiếu độc lập chưa đo; không phải SLAM".
- **"Định vị LiDAR chính xác tới vài mm"**. Vì sao: số mm là độ lệch giữa các vòng ở cùng chỗ, hoặc sai số tìm lại sau
  phép dịch cứng; độ lệch chuẩn Hessian quá lạc quan. Viết: "Độ lệch chuẩn tư thế giữa các vòng ở cùng chỗ 1,4–2,7 mm
  (p07, live_headless); sai số so với vị trí đo bằng thước chưa đo".
- **"Hệ thống có SLAM"** hay **"odometry LiDAR định vị được xe"**. Vì sao:
  - (b) chỉ chạy offline; mọi bản ghi C1 đều đứng yên; trên DROW chỉ so với `.odom2`, không phải ground truth;
  - từ 02/10/2026, (a) + (b) đã nối vào phiên đỗ xe ở mức MP (LiDAR mô phỏng) và chạy offline trên bản ghi C1 đứng yên;
  - với LiDAR mô phỏng trên 9 kịch bản đỗ nghiệm thu (xe 0,10 m/s, sau khi thêm dự đoán tư thế): 5/9 hoàn thành, 4/9 dừng
    POSE_LOST. Vì vậy LiDAR mô phỏng chưa dùng được cho nghiệm thu MP ([NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md)).

  Viết: "Odometry khớp scan chạy offline không trôi trên bản ghi C1 đứng yên và lệch trung vị 2,2 %/5 m so với odometry
  đi kèm DROW v2; chưa thử khi cảm biến di chuyển". Về phương án: "Có nguồn tư thế LiDAR (định vị trên bản đồ tĩnh + kiểm
  chéo bằng odometry khớp scan) chạy trong phiên mô phỏng; không phải SLAM". Phương án làm theo đề xuất từ 02/10/2026;
  các ngưỡng vẫn chưa chốt.

**Giao thức, firmware, an toàn**

- **"Đã thử chế độ quan sát / chạy xe qua VehicleIO"**. Vì sao: chỉ bo mô phỏng và cổng serial giả, tư thế lý tưởng. Viết:
  "Nối `VehicleIO` vào phiên đỗ xe mới kiểm trong mô phỏng, tư thế lấy từ mô phỏng; chưa có bo hay xe".
- **"Phiên đã dừng thì không bao giờ chạy tiếp"**. Vì sao: trên mô phỏng đã tìm thấy một trường hợp vòng điều khiển treo
  quá hạn lệnh trong khi luồng `Heartbeat` giữ liên lạc, dẫn tới một COMMAND enable=1 sau khi bo đã về ARMED. Trường hợp
  này đã sửa ở mức MP ngày 24/09 (3.12b), nhưng còn một khoảng hở suy ra từ mã, chưa có test: khung báo bo về ARMED chưa
  tới laptop (GIAO_THUC_XE mục 12, CHE_DO_QUAN_SAT mục 8). Chưa thử trên bo thật. Viết: dùng câu nên viết ở 3.12b.
- **"Watchdog và E-stop đã kiểm chứng"**. Vì sao: chỉ có bản tham chiếu Python (lõi C++ khớp nó qua test host trên máy
  tính từ 29/09/2026); firmware biên dịch được nhưng chưa chạy trên bo; không phần cứng. Viết: "Logic watchdog kiểm trên
  bản tham chiếu Python; chưa thử trên bo".
- **"Firmware đã chạy/đã kiểm thử trên ESP32-S3"**. Vì sao: firmware chỉ chạy trong bo ảo QEMU (Serial qua UART0, flash
  DIO; không LEDC, GPIO vào, task watchdog kích hoạt, USB-CDC); chưa nạp bo. Viết: "Bản build firmware chạy trong bo ảo
  QEMU và nói chuyện đúng giao thức với phần mềm laptop (30/09/2026); chưa nạp, chưa chạy trên bo ESP32-S3".
- **"Laptop kiểm được giới hạn của bo ESP32-S3"**. Vì sao: chỉ `FirmwareModel` sau cổng serial giả; chưa có bo. Viết:
  "Phần mềm so giới hạn trong HELLO_ACK với cấu hình xe và từ chối START khi lệch nguy hiểm; mới kiểm với bo mô phỏng và
  cổng serial giả".

## 7. Việc cần làm trước khi viết, theo thứ tự đề xuất

| # | Việc | Cần | Mở khóa |
|---:|---|---|---|
| 1 | Hỏi GVHD/khoa: mẫu trình bày, kiểu trích dẫn, giới hạn trang, quy định khai báo công cụ AI, phạm vi tối thiểu để bảo vệ | Người | Mọi phần |
| 2 | Báo GVHD về quyết định giấy phép WoodScape và hai cách đọc trước khi viết; hỏi GVHD về in ảnh WoodScape (mục 4); quyết định có dùng nháp AI khi gán nhãn sa bàn không | Người dùng | 3.8, 3.11b, 4.3, 5 |
| 3 | Sao lưu `autopark/runs/`, checkpoint và bản giải nén dataset ra ngoài ổ D | Người | Mọi hình/bảng lấy từ `runs/` |
| 4 | Lập BOM thực mua mỗi khi hàng về. Bắt đầu với LiDAR C1, bốn camera và hub đã nhận: ghi nơi mua, ngày nhận, giá theo hóa đơn/đơn hàng | Người | 3.2, Phụ lục J |
| 5 | Ghi lại lý do các lựa chọn chưa có biên bản (bỏ camera Wi-Fi, chọn L-RASPP), kèm ngày | Người dùng | 1.2, 1.4 |
| 6 | Chạy `do_may_moi.cmd` trên laptop, cùng cảnh cho camera | Laptop + thiết bị | Mọi số hiệu năng ở chương 4 |
| 7 | Chốt ngưỡng 16.2, bảng kịch bản 16.3, cách đo độc lập **trước** khi thu kết quả cuối; bản đề xuất đã có (ghi chú) | Người dùng + GVHD | 4.1, 4.11 |
| 8 | Chốt mẫu biên bản lần thử, gồm kết quả, can thiệp và 9 nhóm nguyên nhân lỗi, trước khi thu kết quả cuối (có thể gộp vào việc 7) | Người dùng + GVHD | 4.1, 4.11 |
| 9 | 7 lần đặt hộp LiDAR; phần phần mềm của việc này đã xong (ghi chú) | Người (đặt hộp); phần mềm | 4.4 |
| 10 | In bảng, hiệu chuẩn bốn camera; gá ở độ cao dự kiến; chốt gán cổng → hướng, đo ngoại tham, dựng ROI, rồi đo sai số BEV bằng vật mẫu ở vị trí đo bằng thước | Người | 3.8b, 3.9, 4.5, 4.9, 4.9b |
| 11 | Chụp ảnh sa bàn; tập chấm tô tay `--no-draft`; chấm ba checkpoint ở 0,50 và 0,15 | Người + máy có GPU | 4.3 (phần quan trọng nhất của AI) |
| 12 | Định vị: tham chiếu độc lập, bản ghi C1 di chuyển đầu tiên, chốt ngưỡng; SLAM chỉ khi cần bản đồ lớn hơn (ghi chú) | Người dùng + người (đặt C1) + phần mềm | 1.6, 2.7, 3.6b, 4.4, bảng 4.12 dòng 1 |
| 13 | Lưu thành biên bản các số đo chọn thang lập đường đang chỉ nằm trong docstring | Phần mềm | 1.5, 3.5 |
| 14 | Chạy lại toàn bộ test, chiến dịch 2.880 ca và coverage trên bản mã nộp; ghi commit, máy, ngày (ghi chú) | Phần mềm | 4.2, phụ lục |
| 15 | Nhận và tích hợp phần cứng đợt 3–6, giai đoạn 4–9; khi nhận xe, làm theo bản nháp giai đoạn 4/6 (ghi chú) | Mua + người | 3.2, 3.13, 4.11 |
| 16 | Viết hướng dẫn lắp/chạy/dừng; quay video các phiên thử trên xe | Người | Phụ lục A, K và 4.11 |
| 17 | Tra đủ các mục "cần tra" ở mục 5; lưu bản PDF datasheet C1 | Người | Tài liệu tham khảo |
| 18 | Vẽ sơ đồ khối, sơ đồ máy trạng thái, sơ đồ cổng USB, chụp ảnh thiết bị | Người | Chương 3 |
| 19 | Commit việc tối 24/09: **đã xong**; còn ghi mã commit cạnh mọi số lấy từ phần này (ghi chú) | Người dùng | 3.6b, 3.8b, 3.12b, 4.4, 4.6, 4.6b, 4.8, 4.9b |
| 20 | Ghi một phiên có camera bị cắt/xé khung thật (720p, cảnh sáng), phát lại với `--max-wait-ms 60` và `--max-wait-ms 0` trên cùng bản ghi | Người + thiết bị | 3.7, 4.6, 4.6b |
| 21 | Tạo lại `bev.png` tổng hợp và chép bản nhỏ vào `docs/evidence/`; sao lưu `runs/rig_recordings/`. Phần định vị đã xong (ghi chú) | Phần mềm + người (sao lưu) | 3.8b, 4.6b, 4.9b (bản đầu kèm 3.6b, 4.4) |
| 22 | Đo trên laptop các phần mới: làm nóng AI, quy tắc ghép theo nhịp riêng, ghi phiên, thời gian BEV (`bev bench`) và định vị (ghi chú) | Laptop + thiết bị | 4.10 |
| 23 | Commit đợt khuya: **đã xong**; còn ghi mã commit cạnh số khi viết (ghi chú) | Người dùng + phần mềm | Mọi mục có ghi "khuya 24/09" |
| 24 | Quyết định: chốt firmware sau `COMMAND_TIMEOUT`; chính sách so giới hạn bo; mặt nạ sức khỏe ToF và bộ đếm quãng đường (đổi giao thức) (ghi chú) | Người dùng | 1.6, 3.11, 3.12b, 4.2, 4.12 |
| 25 | Làm các phép "làm được ngay" của bộ kịch bản: DV-1, DV-2 cùng buổi đặt hộp, LD-1 chạy dài 30 phút; chạy lại độ nhạy khi máy rảnh (`--workers 1`) để có số thời gian dùng được | Người + thiết bị; phần mềm | 4.4, 4.6, 4.11 |
| 26 | Chạy ngăn AI camera với camera thật sau hiệu chuẩn; chốt tham số và chính sách "AI bắt buộc"; chọn checkpoint cho vòng điều khiển (ghi chú) | Người dùng + người + thiết bị | 3.11b, 4.12 dòng 3, 8 |

Ghi chú cho bảng (việc 19–26 được thêm từ tối 24/09/2026 trở đi):

- **Việc 2.** Ngày 25/09/2026 vế nối AI vào vòng điều khiển đã quyết: cách đọc A, Valeo chưa xác nhận
  ([GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md); TONG_HOP 5.1). Hỏi Valeo hay không là việc người dùng tự quyết và tự gửi.
- **Việc 7.** Bản đề xuất để duyệt: [NGUONG_NGHIEM_THU_DE_XUAT.md](NGUONG_NGHIEM_THU_DE_XUAT.md) mục 12,
  [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 8. Còn việc duyệt từng mã N-…, số lần lặp, tỉ lệ 3:1, máy chạy
  nghiệm thu, camera trên cao.
- **Việc 9.** Hai việc phần mềm (lưu script độ lặp lại vào repo, chép bản nhỏ k01 vào `docs/evidence/lidar/`) đã làm khuya
  24/09 (`a7cec5e`); còn 7 lần đặt hộp.
- **Việc 12.** Định vị trên bản đồ tĩnh có công cụ từ tối 24/09. So sánh phương án và đề xuất có từ khuya 24/09
  ([SO_SANH_DINH_VI_SLAM.md](SO_SANH_DINH_VI_SLAM.md) mục 7); ngày 02/10/2026 người dùng đồng ý làm theo đề xuất. Còn: hai
  phiên liên tiếp không chạm C1 (tìm nguyên nhân +4,3°), dời C1 tới 3–6 vị trí đo bằng thước, chốt ngưỡng
  ([DINH_VI_LIDAR.md](DINH_VI_LIDAR.md) mục 7). Thêm phép đẩy C1 trên tấm ván theo đường dán băng có mốc (SO_SANH_DINH_VI_SLAM
  mục 8.4) để có bản ghi C1 di chuyển đầu tiên.
- **Việc 14.** Các lượt chạy toàn bộ bộ test đã có ở mục 1, ý 9; mới nhất trong dàn ý là 30/09 trên `ebbec83` (`.venv`
  1.380 đạt, 8 bỏ qua; `.venv-train` 1.442 đạt; 0 hỏng). Chiến dịch 2.880 ca và coverage chưa chạy lại. Trước khi nộp vẫn
  phải chạy lại trên bản mã nộp.
- **Việc 15.** Khi nhận xe: điền phiếu kiểm kê trước khi can thiệp điện, đo theo B0–B8, thử lỗi theo L1–L16.
- **Việc 19.** Năm commit lúc 20:22 ngày 24/09, `bfcbfc2` … `9bcc30c`, đã push. Chúng gồm các tệp bằng chứng
  `docs/evidence/lidar/dinh_vi_*` (bốn ảnh + tệp tóm tắt), `docs/evidence/rig/cho_nhip_rieng_ghi_phat_lai_20260924.json`,
  `docs/evidence/may_ban/tham_chieu_20260924_toi.json` và các bản sửa sau 19:08 (khoảng trống an toàn,
  `lidar.bench record`). Lệnh năm tệp ở cuối mục 8 chưa chạy lại trên chính `9bcc30c`; lần chạy lại ngày 25/09 là trên
  `54cb3e2`.
- **Việc 21.** Phần định vị đã xong: `evidence/lidar/dinh_vi_*` (`b100a5d`; mục 4).
- **Việc 22.** Tệp tham chiếu máy bàn đo bằng mã mới đã có (`tham_chieu_20260924_toi.json`, 19:08, `bfcbfc2`; từ 29/09 có
  `tham_chieu_20260929.json`). Mã tối và khuya 24/09 đã có trên `origin/main`, kể cả dòng mới của `tom_tat.md` (`77eb51f`),
  nên laptop chỉ cần `git pull`. Phần đo trên laptop còn nguyên.
- **Việc 23.** Ngày 25/09, trước commit: sửa `tests/test_planner_hard_cases.py` theo nhãn mới (hai trường hợp từng hỏng),
  đổi tên test thành `test_ca_rat_chat_khong_bao_thanh_cong_gia`; chạy toàn bộ bộ test: `.venv` 1242 đạt, 7 bỏ qua;
  `.venv-train` 386 đạt (nhóm chọn, không phải toàn bộ; TONG_HOP_DU_AN.md mục 7). Commit lúc 00:54 ngày 25/09, `65b7127` …
  `54cb3e2`, đã push.
- **Việc 24.** Hai quyết định trong danh sách gốc đã có ngày 02/10/2026, theo đề xuất: phương án định vị (việc 12), và
  tiêu chí số lần đổi chiều là giới hạn theo từng kịch bản nghiệm thu (N-D6 (b)); ngưỡng vẫn là đề xuất. Chốt firmware sau
  `COMMAND_TIMEOUT` đổi hành vi firmware, nên chờ duyệt, chưa làm. Các quyết định còn lại chưa đổi.
- **Việc 26.** Phần commit, push và chạy lại toàn bộ test của đợt AI camera đã xong: `b01dea4`, `99e9a9e`, `9d68257`. Toàn
  bộ test ngày 25/09 trên máy bàn trước và ngày 29/09 ở `9d68257` trên máy bàn hiện tại cùng cho `.venv` 1.315 đạt, 7 bỏ
  qua; `.venv-train` 1.376 đạt; số mới nhất ở `ebbec83` như việc 14. Còn lại:
  - sau hiệu chuẩn (việc 10), chạy ngăn AI camera với camera thật và đặt vật mẫu ở vị trí đo bằng thước;
  - chốt tham số và chính sách "AI bắt buộc" sau khi chấm AI trên sa bàn (việc 11);
  - chọn checkpoint cho vòng điều khiển; đề xuất (chưa chốt) là chỉ dùng lượt chỉ WoodScape.

## 8. Việc phần mềm làm song song (yêu cầu của người dùng ngày 24/09/2026)

Ngày 24/09/2026 người dùng yêu cầu phần mềm làm song song một số việc trong lúc soạn dàn ý. Mục này ghi ba đợt: bảy việc
tối 24/09, mười một việc khuya 24/09 và hai việc đợt AI camera 25/09. Mỗi việc có biên bản riêng. Bảng của từng đợt ghi
mức bằng chứng thật, các mục của dàn ý đã sửa theo, và điều cần lưu ý khi viết. Mọi việc đã commit; commit của từng đợt ở
phần "Cách dùng dàn ý" đầu tệp. Cuối mỗi đợt là các lần chạy test kiểm lại khi cập nhật dàn ý.

### Đợt tối 24/09/2026: bảy việc

Commit lúc 20:22 ngày 24/09, `bfcbfc2` … `9bcc30c`. Bản đầu của dàn ý (chiều 24/09) chưa dẫn kết quả nào của các việc
này, vì lúc đó chúng chưa có biên bản.

| Việc | Biên bản | Mức bằng chứng thật (tối 24/09) | Đã cập nhật ở | Lưu ý khi viết |
|---|---|---|---|---|
| Quy tắc chờ camera chậm xét theo nhịp của từng camera | [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 10.1–10.3; [cho_nhip_rieng_ghi_phat_lai_20260924.json](evidence/rig/cho_nhip_rieng_ghi_phat_lai_20260924.json) | **BT** cho bốn camera khỏe (o01, o02); **TH** cho nhánh camera lỡ nhịp/hỏng/treo (ghi chú 1) | 3.7, 4.6, M.5, 5.1, bảng 4.12 dòng 2, mục 6 | Nêu cả trường hợp 263/855 bộ và cái giá ở 720p (ghi chú 1) |
| *(phát hiện kèm theo)* Lô AI đầu tiên của mỗi cỡ lô tốn 1,2–1,7 s; làm nóng mọi cỡ lô | [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 10.3; [GHI_PHAT_LAI_BAN_THU.md](GHI_PHAT_LAI_BAN_THU.md) mục 7 | **BT**, máy bàn: đo thứ tự lô, `ai.warm_up_ms` [1682, 1444, 1468, 1283] ms, o07 sau sửa 715 bộ, 0 bỏ camera | 3.8, 4.6, 5.1, mục 6 | AI sẵn sàng chậm hơn ≈ 4,2 s; chưa từng thấy AI đứng giữa phiên thật; laptop chưa đo |
| BEV từ AI: chiếu kết quả xuống sàn, giữ vùng chưa thấy/không chắc là UNKNOWN | [BEV.md](BEV.md); [camera_rig_extrinsics_v0.json](../configs/rig/camera_rig_extrinsics_v0.json) | **TH** (rig bốn camera tổng hợp, 32 test, 23 đột biến) + **DL** (ảnh WoodScape, chỉ minh họa); chưa chạy trên camera dự án (ghi chú 2) | 2.5, 3.8, 3.8b, 4.9b, M.5, 5.3, bảng 4.12 dòng 3, mục 5 (A24), mục 6 | Ảnh WoodScape là mức DL; không có con số sai số BEV nào (ghi chú 2) |
| Ghi và phát lại phiên bốn camera + LiDAR | [GHI_PHAT_LAI_BAN_THU.md](GHI_PHAT_LAI_BAN_THU.md) | **TH** (27 hàm test với nguồn giả; đột biến 12 + 15) + **BT** một phiên thật o03 (ghi chú 3) | 3.6, 3.14, 4.1, 4.6b, M.5, bảng 4.12 dòng 10, mục 6 | Phát lại giúp kiểm thử lặp lại, không thay phép đo trên thiết bị (ghi chú 3) |
| Định vị LiDAR trên bản ghi có sẵn (khớp scan với bản đồ tĩnh) | [DINH_VI_LIDAR.md](DINH_VI_LIDAR.md); [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 8 | **TH** (29 test trên phòng tổng hợp) + chạy **offline** trên ba bản ghi BT (22/09, 24/09): chỉ độ nhất quán; không có tham chiếu độc lập | 1.6, 2.7, 3.6b, 4.4, M.5, bảng 4.12 dòng 1, mục 5 (A21–A23), mục 6, mục 7 việc 12 | Bản ghi hiện có là LiDAR **đứng yên**; độ lệch +4,3° chưa rõ nguyên nhân (ghi chú 4) |
| Chế độ quan sát: tính đường và lệnh lái nhưng không gửi ra xe; nối `VehicleIO` vào phiên đỗ xe | [CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) | **MP**: bo mô phỏng (`SimVehicleIO` + `FirmwareModel`), ba test đồng hồ với cổng serial giả; tư thế lý tưởng (`SimTruthPose`); chưa từng nối ESP32-S3 hay MN300 (ghi chú 5) | 3.12, 3.12b, 4.8, M.5, bảng 4.12 dòng 6 và 8, mục 6 | Không chứng minh xe bám được lệnh; không viết "đã dừng thì không chạy tiếp" vô điều kiện (ghi chú 5) |
| Bản nháp tài liệu giai đoạn 4 và 6 (phiếu kiểm kê và bảng đo MN300, bảng công suất, sơ đồ nguồn và dừng khẩn cấp, kịch bản thử lỗi) | [GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md); [mn300_inventory.md](mn300_inventory.md); [GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md) | **TK**: mọi số chưa đo, mọi kịch bản chưa thử; số điện duy nhất là datasheet C1 | 3.2, 3.13, 4.1, 4.11, bảng 4.12 dòng 9, phụ lục L, mục 7 việc 15 | Là bản nháp thiết kế (TK), mọi số chưa đo. Không phải ngưỡng 16.2 hay bộ kịch bản 16.3 |

Ghi chú cho bảng:

1. *Quy tắc chờ.* Đo lại trên máy bàn: 720p chỉ camera 30 s (o01, 0/715 bộ bỏ camera khỏe; quy tắc trước 263/855) và
   480p + LiDAR + AI 120 s (o02, 0/2.862; quy tắc trước 3/2.861). Nhánh camera lỡ nhịp/hỏng/treo chỉ kiểm bằng đồng hồ giả
   với khoảng cách khung thật ngày 23/09. Khi viết, đối chiếu với trường hợp 263/855 bộ ở tham chiếu máy bàn và với nhược
   điểm trong mô phỏng: quy tắc trước bỏ 0,2–2,7 %; quy tắc mới bỏ "chậm" 0 % nhưng để dành 2,1–2,5 %. Nói cái giá: độ lệch
   trong bộ ở 720p lớn hơn. Camera nhìn chỗ tối, không phiên nào có khung hỏng.
2. *BEV.* Phần DL là ảnh WoodScape `00000_FV` và một lần ba ảnh khác thời điểm. Chưa chạy trên camera dự án vì chưa có
   `calibration/cam_p*.json`, ngoại tham là "GIẢ ĐỊNH — CHƯA ĐO", chưa có ROI. Kế hoạch mục 6 yêu cầu vật mẫu có vị trí
   đối chiếu được trên BEV, không chỉ ô màu.
3. *Ghi/phát lại.* o03: 60 s, 480p + LiDAR + AI, 5.724 khung, 0 bỏ, 4,98 MB/s. Phát lại o06 cho 1.432 bộ như phiên thật,
   độ lệch trong bộ trùng. Chưa có bản ghi có camera lỡ nhịp thật; giao diện `--replay` chưa chạy với bản ghi thật.
4. *Định vị.* Kế hoạch mục 5 đòi định vị tại các vị trí có tham chiếu độc lập, và cấm gán odometry bằng 0 để báo đã có
   định vị. Độ lệch +4,3° là của live_headless. Bốn ảnh overlay và tệp tóm tắt đã chép vào `docs/evidence/lidar/` (mục 4).
5. *Chế độ quan sát.* Đây là việc của kế hoạch mục 13 "khi các khối thật chưa đồng thời sẵn sàng".
   - Số test của `tests/test_session_vehicle.py`: 34 lúc viết CHE_DO_QUAN_SAT mục 7 (đột biến 6 + 27 trên bản này); 50
     (49 đạt + 1 `xfail(strict=True)` ghi khoảng trống an toàn) sau khi thêm test; 60 đạt, 0 `xfail` sau bản sửa khoảng
     trống muộn tối 24/09. Đột biến của bản sửa: bỏ `refresh()` → 7 test hỏng, bỏ lớp chặn → test mới hỏng (4.8).
   - Khoảng trống an toàn khi có `Heartbeat` (một COMMAND enable=1 đưa bo ARMED → RUNNING thêm một lần) tìm thấy trên mô
     phỏng và đã sửa ở mức MP. Còn khoảng hở khi khung báo bo đã dừng chưa tới laptop, suy ra từ mã, chưa có test. Câu nên
     viết ở 3.12b và mục 6 (GIAO_THUC_XE mục 12).
   - Lần chạy qua `VehicleIO` lúc đầu không phát lại được (`ReplayNotSupported`). Từ 02/10/2026, mức MP, nó phát lại được
     bằng log (T9), chỉ kiểm quyết định của phần mềm, không tái hiện xe. Cùng ngày có dòng `session_stop` cho mọi quyết
     định dừng của phiên (T13) và nút "Xóa lỗi bo (CLEAR_FAULT)" (T15) (CHE_DO_QUAN_SAT mục 5, 5.1, 6).

**Kiểm lại bằng test của bảy việc.** Đây chỉ là kiểm lại test, không phải phép đo mới. Mọi lần chạy dưới đây dùng máy
bàn, `.venv`, offscreen, chỉ nguồn giả, không đụng phần cứng. Lệnh chạy trong thư mục `autopark`; trong cmd.exe đặt
trước `set QT_QPA_PLATFORM=offscreen`:

```
.venv\Scripts\python.exe -X utf8 -m pytest tests/test_bev.py tests/test_lidar_localize.py tests/test_session_vehicle.py tests/test_rig_replay.py tests/test_multicam_rig.py
```

Các lần chạy, theo thời gian (mỗi số chỉ đúng với bản mã lúc đó):

1. *Tối 24/09, trên cây làm việc chưa commit lúc đó:* 237 đạt, 0 lỗi, 0 bỏ qua (93,9 s), 1 cảnh báo `SyntaxWarning` ở
   docstring `autopark/lidar/localize.py` dòng 7.
2. *18:42–18:44 ngày 24/09:* docstring đã sửa lúc 18:17 (lệnh mẫu nay dùng `\\`), biên dịch với `-W error::SyntaxWarning`
   không còn cảnh báo. Chạy lại đúng lệnh trên, thêm `-rxX -W error::SyntaxWarning`: 253 test, **252 đạt, 1 xfail có chủ
   đích**, 0 lỗi, 0 cảnh báo (98,1 s). Test xfail là
   `test_session_vehicle.py::test_command_timeout_while_heartbeat_keeps_link_stops_and_never_resumes[0]` (`strict=True`).
   Nó ghi lại khoảng trống an toàn tìm thấy trên mô phỏng (3.12b), không phải test mới hỏng; lúc đó
   `tests/test_session_vehicle.py` có 50 test (49 đạt + 1 xfail). Nếu khoảng trống được sửa thì xfail strict sẽ thành XPASS
   và báo lỗi. Lần chạy rộng hơn cho nhánh `VehicleIO` (danh sách tệp của CHE_DO_QUAN_SAT mục 7) ở 4.8.
3. *Muộn tối 24/09, sau bản sửa khoảng trống an toàn:* đúng như dự báo, trường hợp `xfail` strict đạt, nên test được đổi
   thành test thường.
   - `tests/test_session_vehicle.py`: 60 test, **60 đạt, 0 `xfail`** (chạy lại riêng tệp). `test_bev.py` +
     `test_lidar_localize.py`: 61 đạt (32 + 29, chạy lại riêng hai tệp).
   - Lệnh năm tệp ở trên thu **263 test** (đếm bằng `--collect-only`; 253 − 50 + 60). Lệnh này không chạy lại thành một
     lượt riêng; cả năm tệp nằm trong lần chạy toàn bộ bộ test cùng tối. Nó cũng chưa chạy lại trên chính `9bcc30c`.
   - Toàn bộ bộ test cùng tối: `.venv` 895 đạt, 6 bỏ qua (các mô-đun chỉ chạy được với torch), 215 s; `.venv-train` 248
     đạt (sáu mô-đun cần torch cùng `test_labels`, `test_rig_replay`, `test_multicam_rig`, `test_rig_app_ui`,
     `test_may_moi`). Không còn test nào đánh dấu `xfail` trong `tests/`.
4. *25/09, HEAD `54cb3e2`, mã và test trùng HEAD, không kiểm máy có rảnh không:* lệnh năm tệp thu **269 test**
   (`test_bev.py` 38 sau đợt khuya, `test_lidar_localize.py` 29, `test_session_vehicle.py` 60, `test_rig_replay.py` 27,
   `test_multicam_rig.py` 115; tức 263 + 6). Chạy lại đúng lệnh đó, thêm
   `-rxX -W error::SyntaxWarning -p no:cacheprovider`: **269 đạt**, 0 lỗi, 0 `xfail`, 0 cảnh báo, 103,2 s. Toàn bộ bộ test
   ngày 25/09 (trước commit đợt khuya, máy rảnh): `.venv` 1242 đạt, 7 bỏ qua, 0 hỏng; `.venv-train` 386 đạt (nhóm chọn,
   không phải toàn bộ; TONG_HOP_DU_AN.md mục 7).

Khi dẫn các số này, ghi kèm mã commit (mục 7, việc 19 và 23).

### Đợt khuya 24/09/2026: mười một việc

Commit lúc 00:54 ngày 25/09, `65b7127` … `54cb3e2`; commit của từng việc ở phần "Cách dùng dàn ý" đầu tệp. Mỗi việc có
biên bản. **Không việc nào có phiên đo mới trên thiết bị**; không mở camera, LiDAR hay cổng COM. Số thời gian của đợt này
đo trên máy bàn khi nhiều tác tử khác chạy song song, chỉ dùng để so tương đối. Chưa việc nào chạy trên laptop RTX 3050
Ti. Số test là số đếm bằng `--collect-only`, đếm lại ở `54cb3e2` không đổi; số đạt, kiểm đột biến và điều kiện chạy ở tài
liệu của từng việc.

| Việc | Biên bản | Mức bằng chứng thật (khuya 24/09) | Đã cập nhật ở | Lưu ý khi viết |
|---|---|---|---|---|
| Công cụ ngoại tham camera và mặt nạ ROI, giao diện `ui/roi_app.py` | [NGOAI_THAM_VA_ROI.md](NGOAI_THAM_VA_ROI.md); [HIEU_CHUAN_CAMERA.md](HIEU_CHUAN_CAMERA.md) mục 7 | **TH**: ảnh dò tia qua camera Kannala–Brandt đã biết, camera sống là nguồn giả; 29 + 19 test; đột biến 39/39. Chưa camera nào có nội tham, chưa gá | 3.8b, 3.9, 4.9, bảng 4.12 dòng 2, mục 6 | Không có số ngoại tham thật nào. Sai số thước và vạch hệ xe là nguồn sai số lớn nhất, chưa đo. Mọi ngưỡng chưa chốt |
| BEV tăng tốc, chặn `max_range` sai | [BEV.md](BEV.md) mục 6b, 7 | **TH**: rig tổng hợp và hiệu chuẩn WoodScape với bản đồ ngẫu nhiên, máy bàn dưới tải; kết quả trùng từng bit với bản cũ; 38 test | 3.8b, 4.9b, bảng 4.12 dòng 3, mục 6 | Số ms là của máy bàn khi bận; khung đầu 0,3–0,5 s; laptop chưa đo; vẫn chưa chạy trên camera dự án |
| Kịch bản nghiệm thu và ngưỡng đề xuất | [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md); [NGUONG_NGHIEM_THU_DE_XUAT.md](NGUONG_NGHIEM_THU_DE_XUAT.md) | **TK**: mọi ngưỡng là đề xuất, chưa chốt; mọi kịch bản chưa thử; độ chính xác kỳ vọng của phương pháp đo là ước tính | mục 1 ý 7, 4.1, 4.11, bảng 4.12 dòng 7, mục 7 việc 7, 25 | Chỉ viết như phương pháp **đề xuất** cho tới khi duyệt; không trích mã N-… như ngưỡng đã chốt |
| Độ nhạy planner theo kích thước xe; `--vehicle-config` | [DO_NHAY_KICH_THUOC_XE.md](DO_NHAY_KICH_THUOC_XE.md); [GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md) mục 5.3, 8 | **MP**: hai lượt × 860 lần chạy, xe giả định, nhiều tiến trình dưới tải; 56 test | M.5, 4.1, 4.11, bảng 4.12 dòng 5, 5.1, mục 6 | Tải máy đổi được kết quả; "hết giờ" không phải vô nghiệm; `robustness --vehicle-config` chỉ giữ tỉ lệ footprint |
| Nhãn 16 ca khó và đường chứng | [KIEM_THU_DO_BEN_GIAI_DOAN_0.md](KIEM_THU_DO_BEN_GIAI_DOAN_0.md) mục 6 | **MP** + kiểm va chạm độc lập với planner; 44 test; thời gian planner đo dưới tải, chỉ định tính | M.5, 4.2, bảng 4.12 dòng 5, 5.1, mục 4, 6 | "Có nghiệm" khác "dùng được trên xe"; hai trường hợp từng hỏng ở `tests/test_planner_hard_cases.py` đã sửa ngày 25/09 (`10a4735`) |
| Odometry khớp scan, so sánh phương án định vị | [SO_SANH_DINH_VI_SLAM.md](SO_SANH_DINH_VI_SLAM.md) | **TH** (32 test) + **DL** (DROW v2, so với `.odom2`) + **BT offline** (C1 đứng yên); đề xuất phương án: **TK**. Ngày 02/10/2026 người dùng đồng ý; có nguồn tư thế ở mức MP và BT offline ([NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md)); ngưỡng chưa chốt | 1.6, 3.6, 4.4, M.5, bảng 4.12 dòng 1, 5.1, mục 4, 6, 7 việc 12 | Chưa có bản ghi C1 di chuyển, chưa có tham chiếu độc lập; không viết "đã có SLAM"; bản đầu kết luận sai về odometry bánh xe, đã sửa |
| Độ lặp lại khoảng cách LiDAR; bản nhỏ k01 | [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 3b, 3c | **BT offline** trên p07, live_headless, k01; 20 test | 3.6, 4.4, mục 4, mục 7 việc 9 | Không phải sai số so với thước; mã gốc đã mất nên "tái lập" chỉ là cùng mô tả cho cùng số |
| Thẻ "Bo điều khiển", "Kiểm kết nối bo", so giới hạn bo; cầu nối ToF → `NearFieldReading` | [CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) mục 3, 6–8; [GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 7, 10, 12 | **MP/TH**: `FirmwareModel` sau cổng serial giả, `comports` giả; 30 + 54 test, thêm 15 test giao thức; 19 tệp chạy chung 505 đạt; đột biến 50/50; gá ToF giả định | 3.11, 3.12b, 4.8, bảng 4.12 dòng 8, mục 6, mục 7 việc 24 | Chưa mở cổng thật nào; START với bo thật luôn bị từ chối (chưa có nguồn tư thế); chốt firmware sau `COMMAND_TIMEOUT` chờ duyệt, chưa làm |
| RoadAnomaly21; `evaluate.py --train-overlap`; `labels import --exclude` | [HUAN_LUYEN.md](../../HUAN_LUYEN.md) cuối mục 8; [GAN_NHAN_SA_BAN.md](GAN_NHAN_SA_BAN.md) mục 2 bước 7 | RA21: **DL** (10 ảnh có nhãn, ba seed, máy bàn); hai chốt: **TH** (dữ liệu giả; phần so manifest thử trên dữ liệu thật) | 3.10, 4.3, bảng 4.12 dòng 3, mục 6 | Recall RA21 không chứng minh nhận ra vật lạ; số AVM-SS val của `ai_ws_avm` là val chọn checkpoint của chính nó |
| Demo hợp nhất bỏ ≥ 22 vòng khởi động, `--warmup` | [GIAI_DOAN_3_CHUAN_BI.md](GIAI_DOAN_3_CHUAN_BI.md) mục 2 | **TH**: nguồn giả, C1 giả; số tia/vòng của vòng nền tính lại trên ba bản ghi có sẵn (BT offline) | 3.11 | Chưa chạy với C1 thật; ảnh hưởng lên bản đồ nền chưa đo |
| `may_moi`: dòng mới của `tom_tat.md`, tóm tắt lại thư mục đã có | [MAY_NOP_DO_AN.md](MAY_NOP_DO_AN.md) mục 2, 4, 4.1 | **TH**: bản sao hai lần chạy máy bàn (15:25, 19:08); 21 test | 4.10, mục 7 việc 22 | Laptop chưa chạy; mã đã có trên `origin/main` (`77eb51f`), laptop `git pull` là có |

### Đợt AI camera 25/09/2026: hai việc

Làm sau `89cd58f`; commit ngày 25/09, `b01dea4` (mã), `99e9a9e` (giấy phép), `9d68257` (tài liệu). **Không có phiên đo mới
trên thiết bị**; không mở camera, LiDAR hay cổng COM. Chưa việc nào chạy trên laptop RTX 3050 Ti. Số test đếm bằng
`--collect-only`; các lần chạy lại ở dưới bảng.

| Việc | Biên bản | Mức bằng chứng thật (25/09) | Đã cập nhật ở | Lưu ý khi viết |
|---|---|---|---|---|
| Quyết định giấy phép: dùng mô hình huấn luyện trên WoodScape trong vòng điều khiển xe mô hình (cách đọc A) | [GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md) mục "WoodScape trong vòng điều khiển: quyết định 25/09/2026" | Quyết định của người làm khóa luận, không phải số đo; kiểm trên web 25/09 (địa chỉ trang bộ dữ liệu, issue #14); **Valeo chưa xác nhận** | mục 1 ý 4, 3.8, 3.8b, 3.10, 3.11b, bảng 4.12 dòng 3, mục 4, 5.1 (D1), mục 6, mục 7 việc 2 | Nêu cả hai cách đọc và phương án dự phòng chỉ LiDAR; không viết "được phép" hay "bị cấm" như điều đã chắc; quyết định không phủ checkpoint có AVM-SS và nhãn nháp AI |
| AI camera làm nguồn vật cản thứ hai trong phiên đỗ xe (`fusion/camera_ai.py`, ngăn "AI camera", `ui.lidar_app --camera-ai`); `bev.acceptance_flag`; shapely trong `.venv-train` | [AI_DIEU_KHIEN_XE.md](AI_DIEU_KHIEN_XE.md); [BEV.md](BEV.md) mục 2, mục 8 việc 7 | **TH**: camera giả, rig bốn camera tổng hợp, tệp hiệu chuẩn viết tay; cộng phát lại bản ghi **BT** o03 với mô hình thật (ghi chú dưới bảng) | phần 0, mục 1 ý 3, 3.8, 3.8b, 3.11, 3.11b, bảng 4.12 dòng 3 và 8, 5.4, mục 6, mục 7 việc 26 | Chưa camera nào được hiệu chuẩn nên AI chưa tạo vật cản nào trên bàn thật; chưa chạy với camera thật đang mở, chưa trên xe; mọi tham số là đề xuất, chưa chốt; AI chưa chấm trên ảnh sa bàn |

Ghi chú cho dòng AI camera:
- Test: `tests/test_camera_ai_layer.py` 21 hàm / 45 mục, `tests/test_camera_dock_ui.py` 20 hàm / 23 mục; đột biến 46/46
  (AI_DIEU_KHIEN_XE mục 8.1).
- Phát lại bản ghi o03 với mô hình thật (máy bàn, tải không kiểm soát): với rig thật, 1163/1163 lô bị chặn, 0 vật cản;
  với rig tổng hợp, 969 lô dùng được, vị trí hộp vô nghĩa. Số phát lại đo trước các bản sửa cùng ngày, chưa chạy lại.

**Kiểm lại bằng test** (máy bàn, offscreen, chỉ nguồn giả, không đụng phần cứng; không kiểm máy có rảnh không):
1. *25/09, cây làm việc chưa commit trên `89cd58f`:* hai tệp test mới **68 đạt** ở cả `.venv` lẫn `.venv-train`. Bộ 15 tệp
   liên quan **343 đạt** ở `.venv-train` (129 s) và **343 đạt** ở `.venv` (127 s). 15 tệp đó là hai tệp mới cùng
   `test_lidar_dock_ui`, `test_bev`, `test_fusion`, `test_fusion_demo`, `test_session`, `test_session_run`,
   `test_session_vehicle`, `test_phase0`, `test_ui_smoke`, `test_rig_replay`, `test_extrinsics_calib`, `test_roi_tool`,
   `test_fisheye_calib`.
2. *Toàn bộ bộ test sau đợt này:* ngày 25/09 trên máy bàn trước và ngày 29/09 ở `9d68257` trên máy bàn hiện tại cùng cho
   `.venv` 1.315 đạt, 7 bỏ qua; `.venv-train` 1.376 đạt. Mới nhất trong dàn ý: `ebbec83`, `.venv` 1.380 đạt, 8 bỏ qua;
   `.venv-train` 1.442 đạt; 0 hỏng. Nguồn: TONG_HOP_DU_AN.md mục 7; [CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 2, 8.

## Ghi chú về các bản cũ

Bản dàn ý trước lần viết lại này giữ nguyên các ghi chú cập nhật theo từng đợt (24/09–02/10/2026), kể cả danh sách mục đã
sửa ở mỗi đợt: [`56d7c61`](https://github.com/thbn12082/autopark/blob/56d7c61/autopark/docs/DAN_Y_KHOA_LUAN.md).
