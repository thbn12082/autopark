# Kế hoạch triển khai AutoPark — v3.1

**Mục tiêu:** hoàn thành xe mô hình tự đỗ có phản hồi, có kiểm chứng bằng số đo. Triển khai phần mềm và bàn thử trước, rồi tích hợp xe thật.

Bản biên tập 26/09/2026 giữ cấu hình, 11 giai đoạn, sáu đợt mua và các điều kiện chuyển bước của kế hoạch gốc. Tiến độ đối chiếu đến `9d68257`; không có phép đo mới trong lần viết lại.

[Tiến độ và kết quả hiện có](TONG_HOP_DU_AN.md) · [Cách chạy](autopark/README.md) · [Mục lục kỹ thuật](autopark/docs/README.md)

Nghiên cứu nhận thức sử dụng **[Valeo WoodScape Dataset](https://github.com/valeoai/WoodScape)**. [Quyết định và giới hạn sử dụng](autopark/docs/GIAY_PHEP_DU_LIEU.md).

## 1. Cấu hình và phạm vi

### 1.1. Các thành phần đã chọn

| Thành phần | Vai trò |
|---|---|
| MN300 Tank300 1/12 4WD RTR | Xe nền; bộ điện thực giao cần kiểm |
| Laptop | AI, bản đồ/định vị, hợp nhất, tìm/bám đường, giao diện, log |
| RPLIDAR C1/C1M1 | Scan cho bản đồ, định vị, hình học vật cản |
| Bốn camera USB UVC | Quan sát trước/sau/trái/phải, nhận thức cục bộ |
| Hub và dây USB | Truyền bốn luồng; phải đo tải/nguồn thực |
| Một ESP32-S3 chính | Cảm biến, telemetry, ESC/servo, giám sát mất lệnh |
| AS5600 + nam châm | Phản hồi cơ cấu lái sau khi gá/hiệu chuẩn |
| MT6701 hoặc encoder phù hợp | Tốc độ/quãng đường sau khi xác định tỷ số truyền |
| BNO085 | Hỗ trợ ước lượng hướng/chuyển động |
| Khoảng bốn VL53L1X | Khoảng cách gần; thử hai trước |
| Nguồn, cầu chì, E-stop, phần tử ngắt | Cấp điện và dừng theo thiết kế đã đo |

Chưa tự thay xe bằng HSP, camera bằng ESP32-CAM/Wi-Fi, bỏ LiDAR hoặc thay laptop. USB laptop–ESP32 là phương án thử trên bàn; đường điều khiển khi tích hợp xe chưa chốt.

Theo hồ sơ đã nhận LiDAR, bốn camera và hub; các phần xe/bo/nguồn còn thiếu. [Kiểm kê](autopark/docs/hardware_inventory.md).

### 1.2. V1 phải làm gì?

Người dùng đặt vị trí/hướng đỗ. Xe tìm và chạy đường tiến/lùi phù hợp cơ cấu lái, dùng LiDAR và camera để nhận biết môi trường, dừng và đánh giá lại khi có vật cản hoặc dữ liệu không hợp lệ.

Không bắt buộc tự tìm ô, nhận diện vạch, tự lái đến bãi, điều khiển neural end-to-end, MPC nâng cao, dự đoán người hoặc tái dựng 3D.

### 1.3. Nguyên tắc giữ nguyên

Kết quả mô phỏng, bàn thử và xe thật ghi riêng. Ngưỡng chưa đo/chưa duyệt phải để “cần chốt”. Có thể làm phần mềm khi thiếu thiết bị, nhưng chưa được đánh dấu đạt phép thử thật.

Nguồn/dừng phải chuẩn bị trước khi thử chấp hành; giai đoạn 6 xác nhận toàn hệ thống trước chạy tự động trên sàn. Có thể mua sớm chính ESP32-S3 duy nhất ở đợt 3 để đọc cảm biến.

## 2. Luồng hệ thống và cách triển khai

### 2.1. Luồng khi hoàn chỉnh

```text
LiDAR → Bản đồ/định vị ───────────────┐
Camera → AI + BEV cục bộ ────────────┼→ Trạng thái/bản đồ hợp nhất
ESP32 → Phản hồi chuyển động/ToF ────┘             ↓
Đích → Kiểm tra → Tìm đường → Xem trước → Bám đường → ESP32 → Xe
                                                    ↑         │
                                                    └ Phản hồi┘
```

Giám sát lỗi chạy cùng vòng điều khiển. E-stop vật lý là đường dừng riêng với giao diện laptop.

### 2.2. Những việc có thể làm đồng thời

Mô phỏng/AI từ dữ liệu sẵn có; kiểm cảm biến/bàn thử; đo xe/điều khiển/nguồn. Ba nhánh gặp nhau ở tích hợp và nghiệm thu. Đợt mua không tương đương giai đoạn phần mềm.

### 2.3. Cách ghi tiến độ

Mỗi giai đoạn ghi việc đã làm, đầu ra, kết quả đo và thứ còn chặn. “Đang làm” không có nghĩa cổng chuyển bước đã đạt. Dùng log và biên bản để xác nhận; không tự tính phần trăm hoàn thành từ số lượng tệp.

## 3. Sáu đợt mua

| Đợt | Chuẩn bị | Điều kiện trước khi mở rộng |
|---|---|---|
| 1 | LiDAR + bộ nối, một camera mẫu, dây ngắn, nguồn bàn thử | Camera dùng được ở vùng gần xe |
| 2 | Thêm ba camera, hub/nguồn/gá | Thử cả bốn đồng thời, rồi mới thêm dây dài |
| 3 | BNO085, hai ToF, dây; đề xuất mua sớm ESP32-S3 chính | Đối chiếu nguồn/giao tiếp, đọc ổn từng cảm biến |
| 4 | MN300 đúng gói pin/sạc/phụ kiện | Đo xe để chọn phản hồi/gá và cách điều khiển |
| 5 | AS5600, encoder, gá; thêm ToF nếu cần | Có nguồn/dừng phù hợp trước thử chấp hành; không mua trùng ESP32 |
| 6 | Nguồn theo tải, E-stop + phần ngắt, cầu chì/dây/gá cuối | Mất lệnh, dừng, reset, tải đồng thời đạt trước tự đỗ |

Thực tế đã mua đủ bốn camera trước khi hoàn tất phép thử mẫu. Đây là khác biệt so với trình tự dự kiến, không phải bằng chứng camera mẫu đã đạt.

## 4. Giai đoạn 0 — mô phỏng

**Hiện tại:** đạt ở mức mô phỏng ngày 20/09.

**Làm:** sa bàn, đích, động học, tìm/bám đường, toàn thân/vùng quét, lỗi giả, log/replay. Khi có thiết bị có thể thử từng cảm biến độc lập.

**Đầu ra:** cấu hình giả định ghi rõ, test, log, video và replay. [Báo cáo](BAO_CAO_GIAI_DOAN_0.md).

### Mục tiêu cần đạt / điều kiện chuyển bước

- [x] Kéo và xoay đích được; đích nằm trong vật cản bị từ chối.
- [x] Xe ảo chạy tiến/lùi; đường tuân thủ giới hạn lái đặt trong cấu hình.
- [x] Kiểm tra va chạm xét toàn thân xe.
- [x] Vật cản mới làm đường cũ mất hiệu lực; xe ảo dừng trước khi thử đường mới.
- [x] Xem trước không phát lệnh đến phần cứng.
- [x] Ghi lại đủ cấu hình và log để chạy lại cùng kịch bản.

**Cập nhật 20/09/2026:** sáu điều kiện trên đã kiểm chứng ở mức mô phỏng trong `autopark`; xem [biên bản và giới hạn](autopark/docs/GIAI_DOAN_0.md), [dataset và kiểm tra nhãn](autopark/datasets/DANH_MUC_DATASET.md). Không diễn giải thành kết quả xe thật.

**Nếu chưa đạt:** sửa dữ liệu/hình học/logic tại mô phỏng. Không cần mua thêm cảm biến để xử lý một lỗi thuần phần mềm.

## 5. Giai đoạn 1 — LiDAR và camera mẫu

**Hiện tại:** đang làm, [cổng 1 chưa đạt](autopark/docs/gate_01.md).

**Khi chờ đồ:** nguồn phát lại, hợp đồng dữ liệu, khảo sát đầu vào của phương án mapping/định vị.

**Có đồ:** kiểm kê; đo mode/FPS/lỗi; đo khoảng cách LiDAR bằng vật biết vị trí; lưu/nạp map; định vị với tham chiếu độc lập; kiểm camera ở độ cao/góc dự kiến và hiệu chuẩn.

Tách ba kết quả LiDAR: đọc scan, tạo map, định vị lại. Scan tốt chưa chứng minh định vị tốt.

**Đầu ra:** kiểm kê, mode camera, hiệu chuẩn, bản ghi/map, log/video, biên bản cổng. Mã hiện dùng nội tham `calibration/cam_p<cổng>.json`; tên YAML trong kế hoạch cũ là tên dự kiến.

### Mục tiêu cần đạt / điều kiện chuyển bước

- [ ] Laptop nhận LiDAR và camera ổn ở mode đã ghi rõ.
- [ ] Có dữ liệu và phép thử lưu/nạp bản đồ; phần định vị chưa đạt được báo riêng.
- [ ] Camera đủ nét trong vùng làm việc; hiệu chuẩn được và chạy AI trên ảnh thật.
- [ ] Có số đo, không chỉ nhận xét video “mượt”.
- [ ] **Chỉ quyết định mua thêm ba camera sau khi mẫu vượt kiểm tra đơn camera.**

**Nếu camera chưa đạt:** thử cấu hình hoặc model khác trước khi nhân số lượng. **Nếu LiDAR đến trước:** làm scan/map và tiếp tục AI với dữ liệu lưu sẵn; không chờ camera.

## 6. Giai đoạn 2 — bốn camera và BEV

**Hiện tại:** có bàn thử/phần mềm; thiếu hiệu chuẩn và gá thật.

**Khi chờ:** nguồn phát lại bốn hướng, hàng đợi giới hạn, đo từng khối và kiểm sai lệch thời gian.

**Có đồ:** thử cả bốn với LiDAR + AI; ghi USB/nguồn/cách gán hướng; đo nội/ngoại tham; dựng ROI; đặt vật có tọa độ biết trước để chấm BEV và vùng che khuất. Thử A/B dây ngắn–dài.

720p30 MJPEG là mục tiêu khảo sát ban đầu; mặc định triển khai hiện là **640×480** vì các phiên 720p có khung cắt. Cùng FPS không chứng minh ảnh chụp đồng thời.

**Đầu ra:** gá, bộ hiệu chuẩn, USB topology, log, vùng quan sát, sai số BEV. Không chiếu toàn bộ vật cao xuống sàn rồi coi đó là footprint đúng.

### Mục tiêu cần đạt / điều kiện chuyển bước

- [ ] Bốn camera chạy đồng thời ở mode đã thống nhất; có báo cáo tải và mất hình.
- [ ] Đọc đúng camera theo đúng hướng sau khi khởi động lại.
- [ ] Có bộ hiệu chuẩn đa camera gắn với gá thực.
- [ ] Vật mẫu xuất hiện tại vị trí có thể đối chiếu trên BEV, không chỉ hiện một ô màu bất kỳ.
- [ ] Vùng chưa quan sát/thiếu tin cậy được giữ là `UNKNOWN`, không mặc định `FREE`.
- [ ] Có thử riêng dây kéo dài trước khi đưa vào vận hành xe.

**Nếu chưa đạt:** quay về bài thử cổng/nguồn/mode từng bước. Không mặc định đổi hub đắt hơn sẽ giải quyết mọi vấn đề; ghi nguyên nhân và bằng chứng trước khi mua lại.

## 7. Giai đoạn 3 — hợp nhất trên bàn

**Hiện tại:** có lớp bản đồ/nguồn giả; thiếu IMU/ToF/bo thật.

**Khi chờ:** telemetry giả, thời hạn dữ liệu, đổi hệ tọa độ và logic vật mới → dừng → đánh giá lại.

**Có đồ:** đọc từng cảm biến qua ESP32; đo dấu/trục IMU; thử ToF với vật liệu/khoảng cách/timeout; chuyển về hệ rig; đối chiếu vật biết vị trí. Chưa nối chấp hành ở bước kiểm đọc cảm biến.

**Đầu ra:** firmware cảm biến, dây, telemetry có timestamp/cờ hợp lệ, log đồng bộ, map/BEV và bài thử vật cản.

### Mục tiêu cần đạt / điều kiện chuyển bước

- [ ] IMU/ToF thật được đọc qua một đường giao tiếp đã xác định.
- [ ] Mỗi số đo có thời gian và trạng thái; lỗi sensor không bị biến thành giá trị khoảng cách “an toàn”.
- [ ] Global map và local BEV đặt được vào cùng phép mô tả tọa độ.
- [ ] Vật mới làm đường mất hiệu lực; phần mềm phát dừng và phân biệt đường bị chắn với chính đích bị chiếm.
- [ ] Có log cho `STOP → quan sát lại → cập nhật → replan/chờ`.

**Giới hạn bằng chứng:** giai đoạn này chứng minh nhận thức và logic; chưa chứng minh quãng đường dừng hoặc độ chính xác đỗ thật.

## 8. Giai đoạn 4 — nhận và đo MN300

**Hiện tại:** có bảng đo nháp, chưa nhận/đo xe.

**Khi chờ:** chuẩn bị phiếu B0–B8 và kiểm độ nhạy planner với kích thước giả định.

**Có xe:** kiểm gói thực giao, cơ khí/bộ điện; đo thân xe, chiều dài cơ sở, góc lái, bán kính quay, tốc độ thấp, đặc tính phanh/lùi và vị trí gá. Xác định quan hệ góc cảm biến với góc bánh.

**Đầu ra:** ảnh kiểm kê, số đo và cấu hình xe có nguồn gốc. [Hướng dẫn đo](autopark/docs/GIAI_DOAN_4_CHUAN_BI.md).

### Mục tiêu cần đạt / điều kiện chuyển bước

- [ ] Hiểu được hoạt động xe nguyên bản và có dữ liệu chạy chậm, không chỉ biết tốc độ quảng cáo.
- [ ] Có kích thước thực dùng cho planner.
- [ ] Có phương án can thiệp ESC/servo được xác minh hoặc danh sách thông tin còn thiếu rõ ràng.
- [ ] Xác định được phương án gá encoder/góc lái đủ cơ sở để đặt linh kiện.
- [ ] Nếu phải đổi một cụm điện/cơ khí, quyết định dựa trên phép thử, không mua thay đồng loạt.

**Nếu chưa đạt:** tiếp tục hoàn thiện phần mềm trên rig; không đẩy lỗi xe chạy giật sang việc đổi thuật toán AI.

## 9. Giai đoạn 5 — ESP32 và điều khiển có phản hồi

**Hiện tại:** bo mô phỏng/giao thức có test; C++ chưa biên dịch trong hồ sơ.

**Khi chờ:** đặc tả giao thức, bo giả, test vector, kiểm trạng thái kết nối và lệnh hết hạn. Biên dịch/test host khi có toolchain.

**Có đồ:** đo tín hiệu/giới hạn ESC–servo; đọc encoder/góc lái; kiểm hướng và điều khiển phản hồi; thử mất lệnh/reset. Chỉ thử chấp hành khi phần nguồn/dừng của bước thử đã sẵn sàng.

**Đầu ra:** firmware đã biên dịch/nạp, hiệu chuẩn, log đáp ứng và giao thức khớp laptop. START trên xe cần nguồn tư thế thật; quan sát không gửi lệnh chạy.

### Mục tiêu cần đạt / điều kiện chuyển bước

- [ ] Nhận lệnh đúng đơn vị và chỉ chạy khi được cho phép.
- [ ] Đo được tốc độ/góc lái; đã kiểm tra dấu và hệ số quy đổi.
- [ ] Có số đo sai số bám tốc độ/góc ở miền thử nghiệm.
- [ ] Đổi tiến/lùi theo trình tự đã kiểm chứng trên bộ điện thực.
- [ ] Mất lệnh/reset làm hệ thống về trạng thái đã thiết kế; reconnect không tự chạy tiếp.

**Nếu chưa đạt:** phân biệt lỗi đo, cơ khí, nguồn và bộ điều khiển; không tăng gain tùy tiện để bù một encoder lắp sai hoặc tín hiệu không hợp lệ.

## 10. Giai đoạn 6 — nguồn và dừng

**Hiện tại:** bản nháp, chưa đo hoặc thử trên bộ xe.

**Khi chờ:** bảng tải, sơ đồ cấp điện/đường dừng, định mức cần kiểm, kịch bản lỗi.

**Có đồ:** đo từng nhánh và tải chung; kiểm sụt áp/reset/nhiệt; dừng phần mềm, mất lệnh, E-stop và reconnect. Xác định phần tử ngắt động lực; nút E-stop và cờ FAULT không tự chứng minh xe đã dừng.

**Đầu ra:** bảng đo, sơ đồ hoàn công, kịch bản lỗi có log. [Hướng dẫn nguồn/dừng](autopark/docs/GIAI_DOAN_6_CHUAN_BI.md).

### Mục tiêu cần đạt / điều kiện chuyển bước

- [ ] Có sơ đồ cấp điện và ngắt động lực khớp thiết bị thực.
- [ ] Không reset/disconnect ngoài dự kiến trong bộ thử tải đã định.
- [ ] Các đường dừng đã thử, không chỉ tồn tại trên sơ đồ.
- [ ] Đo được khoảng dừng trong điều kiện thử; không coi cắt nguồn là đứng yên tức thì.
- [ ] Phần nguồn/dừng được xác nhận trước tự đỗ thật.

## 11. Giai đoạn 7 — gá cảm biến lên xe

**Hiện tại:** chưa làm.

**Khi chờ:** thiết kế sơ bộ và quy ước tọa độ từ số đo xe.

**Có đồ:** gá cứng, giữ vùng nhìn, quản lý dây, đo lại ngoại tham/ROI và các vùng mù, kiểm khi rung/chuyển động.

**Đầu ra:** bản vẽ/ảnh gá, hệ tọa độ, bộ hiệu chuẩn trên xe và log kiểm.

### Mục tiêu cần đạt / điều kiện chuyển bước

- [ ] Sensor và dây không cản chuyển động.
- [ ] Vùng bị che đã được ghi lại; không tự khẳng định bốn camera phủ kín mọi điểm quanh xe.
- [ ] Bộ hiệu chuẩn đúng phiên bản gá và mode ảnh.
- [ ] Sai lệch khi xe chuyển động nằm trong giới hạn đã chọn cho bước tích hợp.

## 12. Giai đoạn 8 — hợp nhất khi xe chuyển động

**Hiện tại:** phần mềm chuẩn bị, chưa kiểm xe thật.

**Khi chờ:** phát lại có trễ/mất dữ liệu, kiểm đổi hệ tọa độ và phản ứng khi các lớp mâu thuẫn.

**Có xe:** đồng bộ thời gian, ước lượng tư thế, chuyển dữ liệu về đúng thời điểm/hệ tọa độ, đo sai số bằng tham chiếu độc lập, kiểm khi tiến/lùi/quay.

**Đầu ra:** pose/map/BEV/log trên xe chuyển động, sai số và giới hạn công bố.

### Mục tiêu cần đạt / điều kiện chuyển bước

- [ ] Vật mẫu có vị trí hợp lý trên map khi xe đổi tư thế.
- [ ] Phát hiện được mâu thuẫn giữa cảm biến hoặc mất độ tin cậy.
- [ ] Dữ liệu cần thiết bị cũ/mất thì không cho tiếp tục mù.
- [ ] Planner nhận môi trường hiện hành và kết quả cũ bị loại đúng.
- [ ] Có đánh giá định vị/BEV bằng tham chiếu độc lập, không dùng cùng một đầu ra tự xác nhận chính nó.

## 13. Giai đoạn 9 — tự đỗ và vật cản

**Hiện tại:** chưa chạy thật.

**Khi chờ:** dùng cấu hình xe đo được trong mô phỏng; chuẩn bị chế độ quan sát và bài thử.

**Có đủ điều kiện:** quan sát trước; kiểm trạng thái đầu, xem trước; thử đỗ ở phạm vi/tốc độ đã xác nhận, rồi thử vật cản trước/sau/hông/chiếm đích.

Luồng phản ứng: **phát hiện → vô hiệu đường → dừng → quan sát/cập nhật → lập lại đường hoặc giữ dừng**. V1 không cần tự lách liên tục qua vật đang chuyển động.

**Đầu ra:** video đồng bộ log, sai số cuối, khoảng hở, số đổi chiều, lý do thất bại.

### Mục tiêu cần đạt / điều kiện chuyển bước

- [ ] Tự đỗ từ nhiều tư thế xuất phát trong phạm vi đã định, không chỉ phát chuỗi lệnh theo thời gian.
- [ ] Có kết quả đỗ vuông góc và song song; mọi thất bại đều được ghi.
- [ ] Kiểm tra cả sai số cuối vị trí, hướng và khoảng hở.
- [ ] Vật cản chắn đường hoặc chiếm đích tạo hành vi khác nhau đúng thiết kế.
- [ ] Không có đường phù hợp thì giữ dừng, không ép planner phải trả một đường bất kỳ.

## 14. Giai đoạn 10 — đánh giá và khóa luận

**Hiện tại:** có dàn ý, kết quả từng khối và kịch bản nháp.

**Khi chờ:** chốt cách chấm, tập ảnh sa bàn độc lập, mẫu báo cáo và cách ghi thất bại.

**Khi tích hợp xong:** thực hiện bộ bài đã chốt, so cấu hình, lưu cả lỗi, viết rõ vùng làm việc và giới hạn.

**Đầu ra:** báo cáo, dữ liệu/cấu hình tái hiện, video, hướng dẫn bàn giao.

### Mục tiêu cần đạt

- [ ] Có chỉ số định lượng và định nghĩa cách đo.
- [ ] Có tham chiếu độc lập cho sai số vị trí/hướng/khoảng cách.
- [ ] Không chỉ chọn các lần demo thành công.
- [ ] Phân biệt bài toán đã giải quyết với phần chưa đạt hoặc ngoài phạm vi.
- [ ] Người khác đọc hướng dẫn có thể tái lập một phiên thử trong điều kiện đã nêu.

## 15. Khi thiếu linh kiện

| Thiếu | Vẫn làm được |
|---|---|
| Camera | AI trên dữ liệu lưu sẵn, nguồn phát lại, LiDAR |
| LiDAR | Camera, hiệu chuẩn, nhãn, mô phỏng |
| IMU/ToF/ESP32 | Hợp đồng telemetry, nguồn giả, test logic |
| MN300 | Bàn thử, bảng đo, độ nhạy cấu hình |
| Nguồn/gá cuối | Thiết kế, test host, mô phỏng; chưa nghiệm thu chấp hành/xe |

Không thay phép thử phần cứng bằng kết quả mô phỏng để đánh dấu đạt cổng.

## 16. Đo lường và hoàn thành V1

### 16.1. Mốc khảo sát ban đầu

720p30 MJPEG là mode dự kiến khảo sát; hiện bốn camera mặc định 480p. Phiên khoảng 30 phút là bước sàng lọc dài hạn được đề xuất. Miền tốc độ 0,05–0,15 m/s là miền cần khảo sát, không phải tốc độ đã nghiệm thu.

### 16.2. Ngưỡng cần chốt

| Nhóm | Đại lượng |
|---|---|
| Camera | FPS, độ trễ p50/p95, khoảng đứng hình, lệch thời gian |
| Hình học | Sai số BEV, lệch giữa camera, vùng dùng được |
| AI | mIoU/precision/recall, vật cản bị gọi FREE, UNKNOWN |
| Định vị | Sai số vị trí/hướng, ổn định, định vị lại |
| Điều khiển | Sai số tốc độ/góc, đổi chiều, trễ, quãng dừng |
| Tự đỗ | Sai số cuối, khoảng hở, tỷ lệ hoàn thành, thời gian, số đổi chiều |
| Lỗi | Thời điểm phát hiện/phát lệnh/dừng thực, reconnect |

[Bảng ngưỡng đề xuất](autopark/docs/NGUONG_NGHIEM_THU_DE_XUAT.md) chưa phải ngưỡng đã được duyệt. UNKNOWN gồm vùng chưa quan sát/không hợp lệ/che khuất/thiếu tin cậy; thêm tên lớp không tự bảo đảm nhận ra vật lạ.

### 16.3. Bộ kịch bản

[Bản nháp nghiệm thu](autopark/docs/KICH_BAN_NGHIEM_THU.md) có 37 kịch bản trong chín nhóm, gồm đỗ cơ sở, nhận thức, vật cản mới, lỗi cảm biến/liên lạc và nguồn/dừng. Chưa thử ở mức nghiệm thu.

Cần ghi vùng làm việc, ánh sáng, vật thử, tốc độ và khoảng phát hiện; không cam kết phát hiện mọi vật trong mọi điều kiện.

### 16.4. Mười điều kiện hoàn thành

- [ ] Bản đồ/định vị LiDAR hoạt động trong khu vực thử đã định.
- [ ] Bốn camera USB cùng hoạt động và có hiệu chuẩn đúng gá.
- [ ] AI/CV cung cấp thông tin cục bộ cho planner, có đo sai số/nhầm lẫn.
- [ ] Người dùng chọn vị trí/hướng, xem trước và ra lệnh bắt đầu được.
- [ ] Quỹ đạo xét giới hạn lái và toàn thân xe.
- [ ] Xe thực thi có phản hồi tốc độ/góc, không chỉ chạy theo thời gian.
- [ ] Hoàn thành các bài đỗ theo tiêu chí đã chốt.
- [ ] Vật cản/dữ liệu không hợp lệ làm dừng hoặc từ chối chạy đúng thiết kế.
- [ ] Nguồn, watchdog và E-stop đã kiểm chứng.
- [ ] Có dữ liệu, cấu hình và hướng dẫn để tái hiện kết quả.

## 17. Bàn giao và bước tiếp theo

### 17.1. Hồ sơ cần giữ

Mã/commit, môi trường, cấu hình xe, hiệu chuẩn, nguồn dữ liệu/giấy phép, log/video đồng bộ, phép đo độc lập, kết quả cả đạt lẫn thất bại. Dataset, checkpoint và `runs/` cần bàn giao riêng vì không trong Git.

### 17.2. Các lựa chọn còn mở

Nguồn tư thế thật; gá/encoder/nguồn/E-stop; đường điều khiển laptop–bo; ngưỡng nghiệm thu; chốt firmware sau `COMMAND_TIMEOUT`; sức khỏe ToF; chính sách AI bắt buộc và nhãn nháp AI. Đọc [tổng quan](TONG_HOP_DU_AN.md) và tài liệu chuyên đề trước khi thay.

### 17.3. Năm việc làm tiếp

1. Hiệu chuẩn camera, ngoại tham và ROI.
2. Đo sai số LiDAR/BEV bằng vị trí tham chiếu.
3. Thu và gán nhãn tập sa bàn độc lập.
4. Đo bàn thử trên laptop trình diễn.
5. Chuẩn bị firmware/toolchain và nhận/đo xe để mở các bước tích hợp.

### 17.4. Trạng thái chuyển bước

Giai đoạn 0 đạt ở mô phỏng. Giai đoạn 1 chưa đạt theo biên bản; giai đoạn 2–10 chưa có cổng đạt. V1 chưa đạt 10 điều kiện trên.

[Bảng tiến độ từng giai đoạn](TONG_HOP_DU_AN.md) là nơi đọc trạng thái hiện tại. Không lặp nhật ký commit trong từng dòng kế hoạch.

## 18. Nguồn mua đã được cung cấp

Các liên kết dưới giữ từ kế hoạch gốc để đối chiếu. Lần biên tập này không kiểm giá, tồn kho, biến thể hoặc tính tương thích; không chốt lại ngân sách.

| Hạng mục | Link đã cung cấp | Ghi chú dùng trong kế hoạch |
|---|---|---|
| MN300 Tank300 | https://shopee.vn/product/49222047/24674768117 | Xe nền hiện hành; xác nhận gói pin/sạc thực giao. |
| RPLIDAR C1M1 | https://shopee.vn/product/1419756587/45651899727 | Hỏi rõ bộ nối laptop. |
| Camera USB AdaChoi | https://shopee.vn/product/1264216444/55807744269 | Mẫu theo BOM: 130°; mua một trước. |
| UGREEN 50985 | https://shopee.vn/product/1283561216/28453158757 | Hub ứng viên; không mặc định đủ tải bốn camera. |
| Cáp UGREEN 90722 | https://shopee.vn/product/60169370/22378467940 | Thử sau cấu hình dây ngắn; không bắt buộc mua đợt 1. |
| ESP32-S3 chính | https://shopee.vn/product/107147748/40425371167 | Một bo duy nhất; có thể mua sớm để đọc IMU/ToF trên bench. |
| AS5600 | https://shopee.vn/product/578443443/11880418419 | Xác minh bộ nam châm, giao tiếp và gá. |
| MT6701 | https://shopee.vn/product/1257696740/40455544497 | Xác minh chân/mode và gá trước chốt. |
| GY-BNO085 | https://shopee.vn/product/81431289/27362128544 | Đúng phân loại BNO085 theo danh sách người dùng. |
| VL53L1X | https://shopee.vn/product/237617462/26162878906 | Mẫu hàn sẵn chân; thử hai trước. |
| UBEC ứng viên | https://shopee.vn/product/75359161/7525834451 | Chỉ chọn theo điện áp/tải thực; không khẳng định mọi phân loại tương đương. |
| XL4015 ứng viên cũ | https://shopee.vn/product/27117857/349326027 | Chưa bắt buộc mua; chọn nguồn sau bảng tải. |
| Nút LA38 | https://shopee.vn/product/1097845497/25309631912 | Phải phối hợp với đường dừng/phần tử ngắt phù hợp. |
| Cầu chì/đế | https://shopee.vn/product/265439065/18077814935 | Không chốt 15 A chỉ từ link. |
| XT60 dây sẵn | https://shopee.vn/product/27693865/40306450328 | Kiểm tra tương thích đầu nối hệ nguồn. |

[Bản kế hoạch trước biên tập](https://github.com/thbn12082/autopark/blob/9d68257/KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) giữ toàn bộ danh sách thao tác, tên đầu ra dự kiến và nhật ký tiến độ cũ.
