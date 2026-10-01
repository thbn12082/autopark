# Phiếu kiểm kê MN300 Tank300 1/12 RTR — mẫu để điền (soạn 24/09/2026)

**Kế hoạch đối chiếu:** [v3.1 bản `9d68257`](https://github.com/thbn12082/autopark/blob/9d68257/KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) mục 8 (giai đoạn 4: "Khi chưa có xe" → viết
phiếu kiểm kê; "Khi nhận xe" bước 1, 4, 5), mục 3 (đợt mua 4: "đúng gói pin/sạc/phụ kiện xác nhận với shop"), mục 17.2
("Bộ điện MN300 và giao tiếp servo/ESC — giai đoạn 4") và mục 18 (link mua). *(Cập nhật 30/09/2026: mọi "kế hoạch mục N
bước M" và câu trích kế hoạch trong tệp này theo bản trước đợt biên tập 26/09/2026; [bản hiện tại](../../KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md)
giữ số mục, mục 8 có đoạn "Khi chờ" và "Có xe".)*

**Trạng thái (24/09/2026): CHƯA NHẬN XE.** Mọi ô giá trị dưới đây để trống, hoặc ghi "CHƯA ĐO" / "CHƯA XÁC NHẬN". Phiếu
này chưa chứa thông tin nào về chiếc xe thật. Các bảng đo tốc độ, góc lái, bán kính quay và quãng dừng nằm ở
[GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md). Phần nguồn và dừng khẩn cấp nằm ở
[GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md).

## Cách điền

- **Chỉ ghi điều đã nhìn, đã đo hoặc đã đọc trên nhãn của chính chiếc xe này.** Không chép thông số của xe khác, của
  ảnh quảng cáo hay của một phiên bản khác cùng tên (kế hoạch mục 8 bước 4: "không lấy cấu hình của xe khác thay cho nó").
- Mỗi hàng có hai cột tách nhau: **"Theo shop / hộp / sách"** (lời người bán, chữ in trên hộp hoặc trong sách hướng dẫn) và
  **"Thực nhận / đo được"**. Cột thứ nhất chỉ để đối chiếu, không thay được cột thứ hai.
- Cách ghi: để trống = chưa kiểm; "CHƯA ĐO"; "CHƯA XÁC NHẬN" (đã hỏi nhưng chưa có câu trả lời); "không có" (đã kiểm và
  thật sự không có); "không đọc được" (nhãn mờ hoặc bị che). Ghi ngày, giờ, người kiểm và dụng cụ đo.
- **Ảnh:** chụp trước khi tháo, trong khi tháo và trước khi lắp lại. Tên tệp chỉ dùng ký tự ASCII (OpenCV trên Windows
  không đọc được đường dẫn có dấu) theo mẫu `mn300_<mục>_<yyyymmdd>_<nn>.jpg`, ví dụ `mn300_C1_esc_20261001_01.jpg`.
  Thư mục lưu ảnh: **CHƯA CHỐT**. Đề xuất: ảnh gốc để ở `runs/mn300/anh/` (thư mục `runs/` bị git-ignore), chỉ chép vài
  ảnh nhỏ cần cho khóa luận vào `docs/evidence/mn300/`. Việc có đưa ảnh vào git hay không do người dùng quyết định.
- **Không cắt, hàn hay đổi dây trước khi điền xong mục A–D và chạy thử ở mục F** (kế hoạch mục 8 bước 1: "chạy bằng điều
  khiển nguyên bản trong vùng thử trước khi can thiệp điện").

## 0. Thông tin phiếu

| Mục | Giá trị |
|---|---|
| Ngày nhận hàng | |
| Người kiểm kê | |
| Nơi kiểm, điều kiện (bàn, sàn) | |
| Link mua (kế hoạch mục 18) | https://shopee.vn/product/49222047/24674768117 — chỉ lưu để đối chiếu; biến thể thực giao phải ghi ở dòng dưới |
| Biến thể/phân loại ghi trên đơn hàng | |
| Mã đơn hàng (nếu cần đối chiếu với shop) | |
| Tên model, mã sản phẩm in trên hộp | |
| Số lô / số serial (nếu có) | |
| Ảnh hộp nguyên niêm (tên tệp) | |
| Hộp còn niêm phong khi nhận | có / không |
| Hư hỏng nhìn thấy khi nhận | |

## A. Nội dung gói hàng

Liệt kê theo mô tả của shop hoặc danh sách in trên hộp ở cột 2, rồi đánh dấu thứ thực có ở cột 3. Hàng trống ở cuối
dành cho thứ không có trong danh sách.

| # | Hạng mục | Theo shop / hộp / sách | Thực nhận (số lượng) | Tình trạng | Ảnh (tên tệp) |
|---:|---|---|---|---|---|
| A1 | Xe (khung + vỏ) | | | | |
| A2 | Bộ phát (tay điều khiển) | | | | |
| A3 | Pin cho xe | | | | |
| A4 | Bộ sạc / dây sạc | | | | |
| A5 | Pin cho bộ phát (loại, số lượng; có kèm không) | | | | |
| A6 | Sách hướng dẫn, sơ đồ, tờ cảnh báo | | | | |
| A7 | Dụng cụ kèm theo | | | | |
| A8 | Phụ tùng, linh kiện dự phòng | | | | |
| A9 | Phụ kiện trang trí/rời (gương, đèn…) có thể nhô ra ngoài thân | | | | |
| A10 | | | | | |
| A11 | | | | | |

**Thiếu so với mô tả của shop:** ……………… **Thừa/không rõ công dụng:** ………………

### A2b. Bộ phát: các núm/công tắc chỉnh

Ghi khi nhận, **trước khi vặn bất cứ núm nào**. Chụp ảnh mặt bộ phát, tên tệp `mn300_A2b_<yyyymmdd>_<nn>.jpg`.

| # | Núm/công tắc | Có không (theo bộ phát thật, không theo sách) | Vị trí khi nhận | Vị trí dùng khi đo (nếu khác) | Ảnh |
|---|---|---|---|---|---|
| A2b.1 | Trim lái | | | | |
| A2b.2 | Trim ga | | | | |
| A2b.3 | D/R lái (tỉ lệ hành trình lái) | | | | |
| A2b.4 | Giới hạn ga / chế độ tốc độ (trên bộ phát hoặc trên xe/ESC) | | | | |
| A2b.5 | Đảo kênh lái (REV) | | | | |
| A2b.6 | Đảo kênh ga (REV) | | | | |
| A2b.7 | End-point/EPA hoặc chỉnh khác (ABS, trộn kênh…) | | | | |
| A2b.8 | Khác | | | | |

Chưa kiểm bộ phát có những núm nào (chưa nhận xe, 24/09/2026); núm nào không có thì ghi "không có". Góc lái, lệch giữa và
độ rộng xung đo ở C2.5, F4 và ở [GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md) B2/B4/B7/B8 phụ thuộc các vị trí này.

## B. Pin và sạc

Đo điện áp pin bằng đồng hồ vạn năng ngay khi nhận, trước lần sạc đầu. Tài liệu dự án chưa ghi đã có đồng hồ vạn năng
hay chưa (kiểm lại 24/09/2026).

| # | Mục | Theo nhãn / sách | Đo được | Ghi chú | Ảnh |
|---:|---|---|---|---|---|
| B1 | Hóa học pin (ghi đúng chữ in trên nhãn) | | — | | |
| B2 | Điện áp danh định | | — | | |
| B3 | Dung lượng | | — | | |
| B4 | Số cell / cấu hình (nếu nhãn ghi) | | — | | |
| B5 | Điện áp lúc nhận (hở mạch) | — | CHƯA ĐO | ghi giờ đo | |
| B6 | Điện áp sau sạc đầy lần đầu | — | CHƯA ĐO | | |
| B7 | Đầu nối nguồn chính của pin (hình dạng, màu, nhãn) | | | chụp cận cả hai phía | |
| B8 | Dây cân bằng (có/không, số chân) | | | | |
| B9 | Dòng xả cho phép (nếu nhãn ghi) | | — | cần cho bảng định mức ở giai đoạn 6 | |
| B10 | Kích thước, khối lượng pin | | CHƯA ĐO | cần cho bố trí gá | |
| B11 | Bộ sạc: điện áp/dòng vào | | — | | |
| B12 | Bộ sạc: điện áp/dòng sạc ra, loại pin hỗ trợ | | — | | |
| B13 | Bộ sạc: có báo đầy, có cân bằng cell không | | | | |
| B14 | Thời gian sạc đầy lần đầu | | CHƯA ĐO | | |
| B15 | Cảnh báo an toàn trong sách (sạc, cất giữ, nhiệt) | | — | chép nguyên ý chính | |

## C. Bộ điện: ESC, bộ thu, servo, motor, đầu nối

Chụp ảnh **trước khi tháo** mỗi cụm, rồi chụp cận nhãn. Nếu phải mở vỏ để thấy nhãn, ghi rõ đã mở phần nào (kế hoạch mục
8 bước 4: "mở phần vỏ phù hợp để chụp motor, servo, ESC/bộ thu, pin, đầu nối và trục truyền động").

### C1. ESC (bộ điều tốc)

| # | Mục | Theo nhãn / sách | Quan sát / đo được | Ảnh |
|---:|---|---|---|---|
| C1.1 | Chữ in trên ESC (model, hãng, dòng định mức nếu có) | | | |
| C1.2 | ESC và bộ thu là **hai khối riêng** hay **một khối gộp** | | | |
| C1.3 | Số dây ra motor, màu dây | | | |
| C1.4 | Dây vào từ pin: đầu nối, tiết diện nhìn thấy | | | |
| C1.5 | Dây tín hiệu điều khiển ga: số chân, màu, đầu nối, cắm vào đâu | | | |
| C1.6 | Có cấp nguồn ra (BEC) trên dây tín hiệu không; điện áp đo được ở dây đỏ khi bật (không tải) | | CHƯA ĐO | |
| C1.7 | Công tắc nguồn: nằm ở đâu, cắt cái gì (pin → ESC, hay chỉ tín hiệu) | | | |
| C1.8 | Chế độ tiến/phanh/lùi theo sách (có phanh không, lùi có cần về trung tính trước không) | | CHƯA THỬ | |
| C1.9 | Cắt khi pin yếu (LVC): có không, ngưỡng, cách chỉnh | | | |
| C1.10 | Cách lập trình/hiệu chuẩn ESC (nút, jumper, thẻ) và trình tự hiệu chuẩn điểm giữa | | | |
| C1.11 | Đèn báo, tiếng bíp khi bật nguồn (ghi nguyên chuỗi) | | | |
| C1.12 | Hành vi khi bật nguồn mà tín hiệu ga không ở trung tính | | CHƯA THỬ | |
| C1.13 | Hành vi khi mất tín hiệu ga (tắt bộ phát khi đang chạy, xe kê cao bánh) | | CHƯA THỬ | |
| C1.14 | Tản nhiệt, quạt | | | |

Hai dòng C1.12 và C1.13 cần cho các giá trị CHƯA CHỐT của firmware: `boot_hold_ms` và hành vi ESC khi mất xung
([GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 0; [firmware README](../firmware/esp32_vehicle/README.md) mục "CHƯA CHỐT").
Làm khi xe **kê cao bánh**, không có người hay vật trước xe.

### C2. Bộ thu (receiver)

| # | Mục | Theo nhãn / sách | Quan sát / đo được | Ảnh |
|---:|---|---|---|---|
| C2.1 | Chữ in trên bộ thu | | | |
| C2.2 | Số kênh; kênh nào nối ga, kênh nào nối lái | | | |
| C2.3 | Đầu nối ra từng kênh (chuẩn 3 chân tách rời hay đầu riêng của hãng) | | | |
| C2.4 | Tín hiệu ra từng kênh là xung PWM tách rời hay dạng khác (cần máy hiện sóng/logic analyzer) | | CHƯA ĐO | |
| C2.5 | Chu kỳ và độ rộng xung ở trung tính, ga hết, lùi hết, lái trái hết, lái phải hết; ghi kèm vị trí A2b.1–A2b.7 lúc đo | | CHƯA ĐO | |
| C2.6 | Hành vi khi tắt bộ phát (fail-safe: giữ xung cuối, về trung tính, hay ngừng xung) | | CHƯA ĐO | |
| C2.7 | Cách ghép đôi (bind) với bộ phát | | | |

C2.4–C2.6 chỉ đo khi có máy hiện sóng hoặc logic analyzer. Tài liệu dự án chưa ghi đã có hay chưa
([TONG_HOP_DU_AN.md](../../TONG_HOP_DU_AN.md) mục 5.3). Chưa đo được thì ghi "CHƯA ĐO", không suy ra từ loại bộ thu.

### C3. Servo lái

| # | Mục | Theo nhãn / sách | Quan sát / đo được | Ảnh |
|---:|---|---|---|---|
| C3.1 | Chữ in trên servo | | | |
| C3.2 | Số dây, màu dây, đầu nối | | | |
| C3.3 | Nguồn servo lấy từ đâu (BEC của ESC, bộ thu, nguồn riêng) | | | |
| C3.4 | Kiểu nối cơ cấu lái (tay servo, bảo vệ servo, thanh giằng) | | | |
| C3.5 | Servo có quay được bánh khi xe đứng yên trên sàn không | | CHƯA THỬ | |
| C3.6 | Độ rơ nhìn thấy ở cơ cấu lái | | CHƯA ĐO | |

C3.5 cần cho `TrackerParams.preset_steer` (bộ bám đánh lái khi đứng yên ở đầu mỗi đoạn,
[control/tracker.py](../autopark/control/tracker.py)); xem bảng B3 ở [GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md).

### C4. Motor và truyền động

| # | Mục | Theo nhãn / sách | Quan sát / đo được | Ảnh |
|---:|---|---|---|---|
| C4.1 | Chữ in trên motor | | | |
| C4.2 | Loại motor theo số dây và nhãn (ghi điều nhìn thấy, không đoán) | | | |
| C4.3 | Số răng bánh răng motor / bánh răng chính (nếu đếm được) | | CHƯA ĐO | |
| C4.4 | Kiểu truyền động bốn bánh (trục, vi sai: ghi điều nhìn thấy) | | | |
| C4.5 | Chỗ có thể gắn encoder: trục motor, trục truyền, bánh (ảnh từng chỗ) | | | |
| C4.6 | Chỗ có thể gắn AS5600 + nam châm cho góc lái (ảnh từng chỗ) | | | |
| C4.7 | Đường kính bánh (đo ở mặt lốp, 4 bánh) | | CHƯA ĐO | |

C4.3, C4.5 và C4.7 cần để quy đổi số đếm encoder sang quãng đường (kế hoạch mục 9 bước 4). Kế hoạch mục 1.1 nhắc: "góc
đo ở trục cảm biến chưa tự đồng nghĩa góc bánh".

### C5. Đầu nối và dây (tổng hợp)

| # | Nối giữa | Loại đầu nối (theo hình dạng/nhãn) | Số chân, màu dây | Tiết diện dây nhìn thấy | Ảnh |
|---:|---|---|---|---|---|
| C5.1 | Pin → ESC (hoặc → công tắc) | | | | |
| C5.2 | ESC → motor | | | | |
| C5.3 | ESC → bộ thu (kênh ga) | | | | |
| C5.4 | Servo → bộ thu (kênh lái) | | | | |
| C5.5 | Công tắc nguồn | | | | |
| C5.6 | Đèn, phụ kiện điện khác (nếu có) | | | | |

Kế hoạch mục 18 có link dây XT60 kèm ghi chú "kiểm tra tương thích đầu nối hệ nguồn". Dòng C5.1 là chỗ đối chiếu;
chưa ghi đầu nối của xe thì chưa kết luận có tương thích hay không.

## D. Sơ đồ đấu dây nguyên bản

Vẽ tay hoặc chụp ảnh có chú thích, **trước khi đổi bất cứ dây nào**. Khung dưới là chỗ ghi lại; mũi tên chỉ là gợi ý thứ
tự cần lần theo, không phải sơ đồ của xe này (chưa nhận xe).

```text
[Pin] ──(C5.1)── [Công tắc?] ── [ESC] ──(C5.2)── [Motor]
                                  │
                                  └──(C5.3, BEC?)── [Bộ thu] ──(C5.4)── [Servo]
Điền: công tắc nằm trước hay sau ESC, BEC có hay không, servo lấy nguồn ở đâu, mass chung ở đâu.
```

| Điểm đo (khi bật nguồn, xe kê cao bánh, chưa đổi dây) | Điện áp đo được | Dụng cụ | Ngày |
|---|---|---|---|
| Hai cực pin | CHƯA ĐO | | |
| Dây đỏ – dây đen trên dây tín hiệu ga (BEC) | CHƯA ĐO | | |
| Dây đỏ – dây đen trên đầu nối servo | CHƯA ĐO | | |

## E. Cơ khí liên quan tới đo đạc và gá

Số đo kích thước (chiều dài cơ sở, vệt bánh, phần nhô, bề rộng) ghi ở bảng B1 của
[GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md). Ở đây chỉ ghi điều cần biết để gắn gá.

| # | Mục | Quan sát | Ảnh |
|---:|---|---|---|
| E1 | Cách giữ vỏ (cột, kẹp); vị trí và đường kính lỗ có sẵn trên khung | | |
| E2 | Mặt phẳng nào trên khung dùng làm mặt đỡ gá được mà không cần khoan | | |
| E3 | Hành trình hệ treo: chỗ nào trên xe đi lên xuống khi nén | | |
| E4 | Vùng quét của bánh trước khi đánh lái hết hai bên (không được đặt dây/gá vào đó) | | |
| E5 | Khối lượng xe nguyên bản có pin, không vỏ / có vỏ | CHƯA ĐO | |
| E6 | Khoảng sáng gầm | CHƯA ĐO | |

## F. Chạy thử bằng điều khiển nguyên bản (trước khi can thiệp điện)

Làm trong vùng thử kiểm soát, không có người trong đường xe, kê cao bánh trước rồi mới đặt xuống sàn. Chỉ ghi quan sát;
số đo định lượng làm theo [GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md) mục 3.

| # | Kiểm | Kết quả | Ngày, người |
|---:|---|---|---|
| F1 | Bật nguồn theo trình tự của sách; ghi đèn/bíp | CHƯA THỬ | |
| F2 | Kê cao bánh: ga tiến nhẹ, bánh quay đúng chiều | CHƯA THỬ | |
| F3 | Kê cao bánh: lùi (có phải về trung tính / nhấn hai lần không) | CHƯA THỬ | |
| F4 | Lái trái/phải hết cỡ; lái về giữa có thẳng không; ghi kèm vị trí A2b.1–A2b.7 lúc thử | CHƯA THỬ | |
| F5 | Tắt bộ phát khi bánh đang quay chậm (kê cao): bánh dừng hay chạy tiếp | CHƯA THỬ | |
| F6 | Trên sàn: chạy chậm tiến/lùi 1–2 m, có giật, có tiếng lạ | CHƯA THỬ | |
| F7 | Nhiệt ESC/motor sau 5 phút chạy nhẹ (sờ hoặc đo) | CHƯA ĐO | |

Dòng F5 là tình huống an toàn: làm khi bánh kê cao, tay sẵn ở công tắc nguồn.

## G. Câu hỏi cần xác nhận với shop

Hỏi trước khi đặt hàng nếu kịp; nếu đã đặt thì hỏi khi nhận. Ghi nguyên văn câu trả lời và ngày. Câu trả lời của shop
chỉ là "CHƯA XÁC NHẬN bằng đo" cho tới khi kiểm trên xe.

| # | Câu hỏi | Trả lời (nguyên văn) | Ngày | Đã kiểm trên xe? |
|---:|---|---|---|---|
| G1 | Gói giao gồm những gì: có pin xe, bộ sạc, pin cho bộ phát không? | | | |
| G2 | Pin xe loại gì, điện áp và dung lượng bao nhiêu, đầu nối loại nào? | | | |
| G3 | ESC và bộ thu là hai khối riêng hay một khối gộp? | | | |
| G4 | Bộ thu xuất xung PWM tách rời cho từng kênh (cắm servo/ESC chuẩn 3 chân) không? | | | |
| G5 | ESC có lùi không; có phanh không; có cần về trung tính trước khi lùi không? | | | |
| G6 | ESC có BEC không; servo lấy nguồn từ đâu? | | | |
| G7 | Motor loại gì; có bán riêng ESC, servo, motor thay thế không? | | | |
| G8 | Có sách hướng dẫn / sơ đồ điện không; xin bản điện tử nếu có | | | |
| G9 | Kích thước theo nhà sản xuất: chiều dài cơ sở, vệt bánh, dài, rộng (chỉ để đối chiếu với số đo, không dùng thay) | | | |
| G10 | Bảo hành còn không nếu đổi dây/gắn thêm mạch | | | |
| G11 | Biến thể nào khác với biến thể đã đặt (để chắc đúng hàng) | | | |

## H. Kết luận của phiếu (điền sau khi xong A–G)

| Câu hỏi kế hoạch mục 8 | Kết luận | Dựa trên (mục, ảnh, số đo) |
|---|---|---|
| Hiểu được hoạt động xe nguyên bản chưa? | | |
| ESC/bộ thu tách hay gộp; ESP32 có đưa lệnh vào được mà không thay cụm điện không? | | |
| Servo giao tiếp thế nào; có cần nguồn riêng không? | | |
| Thông tin còn thiếu (danh sách) | | |
| Có phải đổi cụm điện/cơ khí nào không (chỉ quyết định sau phép thử, kế hoạch mục 8) | | |

Kế hoạch mục 8 ghi: "Nếu chưa đủ dữ liệu thì giữ nguyên xe và hỏi/đo thêm", và "Chưa mua ESC thay thế chỉ từ tên xe".
