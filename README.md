# AutoPark — đỗ xe và xoay trở cho xe mô hình

AutoPark hướng tới xe mô hình tự tìm ô đỗ phù hợp, tính đường tiến/lùi và thực hiện ở tốc độ thấp. **Kiến trúc mục tiêu gồm laptop chạy AI và lập đường, Raspberry Pi trên xe thu cảm biến và bám đường, ESP32 điều khiển cơ cấu thật.** Người dùng xem phương án và xác nhận trước mỗi lượt chạy.

**Hiện trạng ngày 26/11/2026.**

- **Quan sát:** cửa sổ quan sát trên laptop nhận bốn camera USB và LiDAR C1 từ Pi qua Wi-Fi khi xe đứng yên. Nút "Ghi LiDAR" lưu bản quét để dựng bản đồ sa bàn.
- **Điều khiển:** firmware ESP32 đã điều khiển được ESC và servo trên bàn thử.
- **Phần mềm đỗ xe:** đã tự tìm được ô đỗ trên bản đồ LiDAR. Bấm ô trong giao diện để đặt đích, rồi tính đường và chạy thử kín vòng trong mô phỏng với kích thước xe đo thật.
- **Đang chờ:** in bốn tờ ChArUco để hiệu chuẩn ngoại tham Bird’s Eye View (BEV), và lắp MT6701 để có phản hồi góc lái và tốc độ.

Đọc [bàn giao cho phiên tiếp theo](BAN_GIAO_CODEX.md) để tiếp tục.

## Phần cứng

| Thành phần | Cấu hình / nhiệm vụ |
|---|---|
| Máy tính trên xe | **Raspberry Pi 4 Model B, RAM 8 GB**, chạy Raspberry Pi OS 64-bit trong lượt thử |
| Lưu trữ trên Pi | **microSD 64 GB** cho hệ điều hành, chương trình, cấu hình và log; video ưu tiên lưu ở laptop |
| Cảm biến góc lái | **MT6701 #1**, đọc góc tuyệt đối qua I²C vào ESP32; gá tại cơ cấu lái. Đã có module, **chưa lắp** |
| Cảm biến chuyển động | **MT6701 #2**, dự kiến đếm xung A/B qua ESP32 để tính tốc độ và quãng đường; gá trên bánh hoặc trục truyền động. **Chưa lắp** |
| IMU hỗ trợ định vị | **BNO085**, dự kiến đọc qua ESP32; gắn cố định lên khung để đo góc quay thân xe và đối chiếu với LiDAR C1. **Chưa lắp** |
| Điều khiển cơ cấu | ESP32-S3 với flash 16 MB và PSRAM 8 MB, cắm USB vào Pi. ESC QuicRun 1060 (GPIO4) và servo (GPIO5) đã chạy bằng firmware AutoPark trên bàn thử |
| Quan sát | Đã nhận đồng thời **bốn camera USB qua hub có nguồn riêng** và LiDAR C1. Laptop hiển thị ảnh, bản quét và tab BEV |

**Phương án cảm biến gồm hai MT6701 và một BNO085.** Tốc độ và góc lái đo được là hai phản hồi cần có để thử tự chạy, nên không đo tay góc lái hay tốc độ trước khi lắp MT6701. BNO085 là nguồn dữ liệu bổ sung cho định vị. Mỗi MT6701 có một nam châm và một vị trí gá. Đường xung A/B của MT6701 #2 dự kiến nối riêng vào ESP32, còn MT6701 #1 dùng bus I²C. Thứ tự thử khi lắp:

1. **Thử BNO085 trước.** Ngắt pin ESC, đọc góc trên bàn rồi xoay bo khoảng 90° để kiểm hướng và độ lớn góc đo. Sau đó gá lên khung để đối chiếu hướng quay với C1 khi di chuyển xe bằng tay.
2. **Thử MT6701 #1.** Dùng bo 5 chân đang có để kiểm đọc góc qua I²C trên bàn. Sau khi tìm được vị trí gá tại cơ cấu lái, hiệu chuẩn chiều trái/phải, điểm giữa và quan hệ giữa góc cảm biến với góc bánh trước.
3. **Thử MT6701 #2.** Xác minh chế độ A/B trên module định dùng trước khi gá. Sau khi lắp, quay bánh bằng tay để kiểm chiều đếm và đo số xung trên một vòng bánh trước khi quy đổi tốc độ, quãng đường.

Hệ điều hành của Pi nằm trên thẻ microSD. Thiết kế nguồn dùng USB-C ổn áp 5,1 V/3 A cho Pi, với giới hạn tổng tải USB trực tiếp là 1,2 A. Hub bốn camera cần nguồn riêng phù hợp. Cần đo độ trễ, tải USB và CPU với đủ thiết bị trước khi chốt FPS. Xem [hướng dẫn lắp và nguồn tham khảo](autopark/docs/LAP_RAP_DIEN_2D.md).

### Module MT6701 5 chân và cách gá nam châm

Module thực tế có các chân `VDD`, `GND`, `Analog/PWM`, `SCL` và `SDA`. Đây là ứng viên để thử đọc góc lái qua I²C. Cần xác minh cấu hình `MODE` và tín hiệu A/B trên breakout trước khi dùng cho encoder bánh.

<table>
  <tr>
    <td align="center"><img src="autopark/docs/images/mt6701-mat-truoc.jpg" alt="Mặt trước module MT6701 5 chân" width="280"><br>Mặt trước</td>
    <td align="center"><img src="autopark/docs/images/mt6701-mat-sau.jpg" alt="Mặt sau module MT6701 5 chân" width="280"><br>Mặt sau</td>
  </tr>
</table>

Cố định bo và gắn nam châm lên chi tiết quay. Canh trục nam châm qua tâm hình học của vỏ IC đen tại vị trí `U1`, với mặt nam châm song song mặt trên IC. MagnTek khuyến nghị nam châm trụ hai cực từ hóa theo đường kính **Ø6 × 2,5 mm**. Khe hở từ mặt nam châm đến mặt IC là **0,5–2 mm**, danh định **1 mm**, với lệch tâm tối đa **0,3 mm**. [Datasheet MagnTek, mục 6](https://www.magntek.com.cn/upload/pdf/202407/MT6701_Rev.1.8.pdf#page=9)

![Sơ đồ gá nam châm đồng trục với IC U1 trên module MT6701](autopark/docs/images/ga-nam-cham-mt6701.png)

Bắt đầu bằng lượt ướm trên bàn với pin ESC đã ngắt. Dán nam châm vào đầu trục và bắt bo lên giá đỡ riêng cố định với khung. Đặt miếng căn nhựa không từ tính dày khoảng **1 mm** giữa mặt nam châm và mặt trên `U1` để giữ khe trong lúc cố định gá. Khi gá đã chắc, rút miếng căn rồi xoay trục bằng tay để kiểm khe hở suốt hành trình.

![Cách dùng miếng căn nhựa tạm để chỉnh khe hở nam châm MT6701](autopark/docs/images/can-khe-ho-mt6701.png)

### IMU BNO085 để thử đo hướng thân xe

![Bo IMU BNO085 GY-BNO08X và hàng chân cắm](autopark/docs/images/gy-bno08x-imu.jpg)

Bo `GY-BNO08X` của xe dùng chip **BNO085** theo xác nhận của người lắp. Phần đọc dữ liệu trong AutoPark và chân nối BNO085 đang chờ lượt thử trên bàn. [Datasheet Ceva BNO08X, mục 2.2](https://www.ceva-ip.com/wp-content/uploads/BNO080_085-Datasheet.pdf#page=31)

### Kích thước MN300 đo thực

| Kích thước | Số đo | Mốc đo |
|---|---:|---|
| Chiều dài cơ sở | 210 mm | Tâm trục trước đến tâm trục sau |
| Bề rộng lớn nhất | 160 mm | Hai mép ngoài cùng của xe |
| Phần nhô trước | 37 mm | Tâm trục trước đến mũi xe |
| Phần nhô sau | 47 mm | Tâm trục sau đến đuôi xe |

Phần mềm dùng các số này qua [`autopark/configs/vehicle_measured.json`](autopark/configs/vehicle_measured.json). Góc lái tối đa 30° và giới hạn tốc độ trong tệp đó vẫn là giả định, chờ đo bằng MT6701.

![Sơ đồ kích thước MN300 đo thực](autopark/docs/images/kich-thuoc-mn300-do-thuc.png)

### Vị trí gá LiDAR C1 đo thực

Gốc tọa độ nằm trên mặt sàn, ngay dưới tâm trục sau.

| Trục | Số đo | Mốc đo |
|---|---:|---|
| `x` | 180 mm | Từ tâm trục sau về phía trước, đến tâm quay C1 |
| `y` | +30 mm | Từ đường tâm dọc của xe sang trái, đến tâm quay C1 |
| `z` | 160 mm | Từ mặt sàn lên mặt phẳng quét LiDAR |

Góc hướng của C1 cần được đo khi hiệu chuẩn. Tệp định vị `autopark/configs/dinh_vi_lidar_v0.json` vẫn ghi vị trí gá giả định, chưa cập nhật theo số đo này.

![Sơ đồ vị trí gá LiDAR C1 đo thực trên MN300](autopark/docs/images/vi-tri-ga-lidar-c1-do-thuc.png)

### Hướng gá bốn camera

<img src="autopark/docs/images/bo-camera-usb.jpg" alt="Bo camera USB thực tế với ống kính và giắc trắng" width="300">

Thử đặt bo camera theo chiều dọc như sơ đồ, với đầu có ống kính ở trên, giắc trắng và dây hướng xuống sàn. Hướng mặt ống kính ra ngoài theo vị trí trong bảng.

Mở từng ô trong ứng dụng quan sát ở khung ảnh ngang **640×480**. Cầm giấy ghi **↑ TRÊN** trước ống kính, rồi xoay cả bo quanh trục ống kính từng 90° nếu cần, đến khi mũi tên trên màn hình chỉ lên. Đánh dấu cạnh trên của bo và cố định theo chiều vừa kiểm tra.

Chúc nhẹ thân camera xuống để nhìn được phần sàn sát xe. Hướng trái và phải tính theo chiều tiến của xe.

| Ô camera trong ứng dụng | Hướng đã xác nhận |
|---:|---|
| 1 | Trước |
| 2 | Sau |
| 3 | Trái |
| 4 | Phải |

Giữ từng camera ở cổng hub đã đối chiếu với ô hiển thị trong ứng dụng.

![Sơ đồ hướng gá bốn camera trên MN300](autopark/docs/images/huong-ga-bon-camera.png)

## Hiệu chuẩn Bird’s Eye View trên xe thật

![Ảnh ghép Bird’s Eye View từ bốn camera MN300 trước khi hiệu chuẩn](autopark/docs/images/bev-chua-hieu-chuan.jpg)

Mỗi camera dùng mô hình ống kính đo riêng (nội tham). Ảnh trên là mốc trước hiệu chuẩn. Tab BEV vẫn hiển thị hình chiếu ước lượng cho tới khi có ngoại tham. Khi có tệp rig `v1`, tab chiếu ảnh bốn camera về cùng mặt sàn để kiểm các đường nối. [Quy trình hiệu chuẩn camera](autopark/docs/PHAN_CUNG_VA_HIEU_CHUAN.md#hiệu-chuẩn-camera)

| Camera | Ảnh dùng khi tính nội tham | RMS chiếu lại (px) | Tệp 640×480 |
|---|---:|---:|---|
| 1 · Trước | 30/32 | 0,136 | [cam_p1.json](autopark/calibration/cam_p1.json) |
| 2 · Sau | 25/25 | 0,191 | [cam_p2.json](autopark/calibration/cam_p2.json) |
| 3 · Trái | 21/22 | 0,143 | [cam_p3.json](autopark/calibration/cam_p3.json) |
| 4 · Phải | 25/26 | 0,130 | [cam_p4.json](autopark/calibration/cam_p4.json) |

**Ngoại tham dùng bốn tờ A4 in mẫu ChArUco, không đo thước.** Cách cũ dùng bàn cờ trên tablet cộng thước đã bỏ, vì tọa độ nhập tay lệch tới 4–5 cm. Theo cách mới:

1. In [bốn tờ ChArUco](autopark/calibration/bang_in/to_ngoai_tham/to_ngoai_tham_A4_4trang.pdf) (trước, sau, trái, phải).
2. Đặt mỗi tờ sao cho mép tờ chạm lốp. Không cần nhập số đo nào.
3. Chụp mỗi camera một ảnh.
4. Chạy `autopark/perception/sheet_extrinsics.py solve` để giải tư thế bốn camera, kiểm chéo và ghi tệp rig.

Bộ giải đã đạt trên ảnh tổng hợp. **Đang chờ in tờ để chụp trên xe thật.** [Chi tiết](BAN_GIAO_CODEX.md#cập-nhật-tối-24112026-ngoại-tham-bằng-tờ-in-bỏ-đo-thước)

## Kết quả bàn thử trên xe thật

Các lượt ngày 22/11/2026 thực hiện khi xe đứng yên và pin ESC đã ngắt, với firmware AutoPark build cho flash 16 MB, PWM tắt. Các lượt motor và servo ngày 24–25/11 chạy với bánh nhấc khỏi sàn.

| Hạng mục | Kết quả quan sát |
|---|---|
| Laptop và Pi | Đã đăng nhập SSH qua USB Gadget để cấu hình Pi, rồi kiểm tra lại SSH qua Wi-Fi khi Pi dùng sạc dự phòng. |
| USB Pi–ESP32 | Bản firmware AutoPark trả `HELLO_ACK` và telemetry `DISARMED`, `fault=NONE`. Cả 10 lượt mở lại phiên kiểm USB đều đạt. |
| Nguồn và thu dữ liệu tại Pi | Nguồn từ cổng USB laptop báo thiếu áp (`0x50005`). Khi dùng sạc dự phòng, camera và C1 chạy đồng thời hơn 5 phút với ESP32 vẫn nối USB. Camera giải mã 8.784 khung MJPG 640×480 ở trung bình 29,28 fps. C1 đọc 2.984 vòng ở trung bình 10,02 Hz. Cả 199 lần lấy mẫu nguồn đều báo `throttled=0x0`. |
| Truyền qua Wi-Fi | Trong 45 giây, laptop nhận đủ 450/450 khung camera ở 10,00 fps và 452/452 vòng C1 ở 10,04 Hz. Số thứ tự hai luồng liên tục. Trung bình toàn phiên SSH là 3,06 Mb/s. Khoảng cách lớn nhất giữa hai mẫu nhận liên tiếp là 156 ms cho camera và 154 ms cho C1. |
| Kiểm hướng quan sát | Trong cửa sổ quan sát thử nghiệm trên laptop, người thử di chuyển hộp lần lượt ra trước, sang trái và sang phải xe. Ảnh camera và cụm điểm C1 đều thay đổi đúng phía theo quan sát. |
| Motor và servo (sketch `MN300_Bench_Test`) | Người dùng xác nhận ngày 24/11/2026: motor quay qua ESC (GPIO4) và servo đánh lái (GPIO5), servo lấy nguồn BEC 6 V của ESC và chạy ổn. Không có nhật ký số liệu. |
| Firmware AutoPark có PWM (env `esp32s3_16mb_pwm`) | Ngày 25/11/2026, bánh nhấc khỏi sàn, nạp từ Pi bằng `nap.sh`. Người dùng xác nhận đạt cả năm bước của `tools/thu_ban_pwm.py`: kết nối, servo trái/giữa/phải, tiến, lùi, và tự dừng khi ngừng gửi lệnh. Giới hạn thử bàn: ga 1375–1625 µs, servo 1200–1800 µs, lệnh hết hạn sau 200 ms. Không dùng E-stop theo thiết kế. Không lưu nhật ký số liệu. |

Trước lượt tự chạy trên sàn, cần:

- phản hồi góc lái và tốc độ từ hai MT6701;
- bản đồ LiDAR của sa bàn;
- xác nhận tư thế xe bằng định vị LiDAR;
- kiểm mất luồng;
- đo quãng dừng. Xem [Kiểm thử và lộ trình](autopark/docs/KIEM_THU_VA_LO_TRINH.md) và [Phần cứng và hiệu chuẩn](autopark/docs/PHAN_CUNG_VA_HIEU_CHUAN.md).

## Hiện có và cần phát triển

| Hạng mục | Hiện có trong repository | Phần cần phát triển theo thiết kế mục tiêu |
|---|---|---|
| Tìm ô đỗ | Tìm khe vuông góc và song song trên bản đồ LiDAR, không giới hạn khoảng cách tới xe (`planning/slot_finder.py`). Nút "Tìm ô đỗ" trong giao diện vẽ các ô lên sa bàn để bấm chọn (`ui/slot_picker.py`). Mới thử trên LiDAR mô phỏng | Chạy trên bản đồ C1 ghi từ sa bàn thật |
| Thao tác và đích đến | Lập và bám đường trong ứng dụng; mô phỏng cua hẹp, lách vật cản, vào khe. Chạy kín mô phỏng từ quét LiDAR đến đỗ xong, lập đường chỉ trên bản đồ, chấm trong sa bàn thật (`simulation/slot_run.py`) | Thử trên xe thật sau khi có phản hồi MT6701 |
| Cảm nhận | Các khối camera/AI, LiDAR, hợp nhất vật cản và ước lượng tư thế. Cửa sổ quan sát nhận bốn camera và C1, lưu ảnh hiệu chuẩn và ghi bản quét C1 | Ngoại tham BEV bằng tờ in; đo tuổi dữ liệu bốn luồng và kiểm mất luồng trong ứng dụng |
| Thực hiện quỹ đạo | Bộ bám và xử lý dừng chạy trong ứng dụng hiện tại | Pi nhận quỹ đạo, định vị và bám đường cục bộ; giám sát vật cản và liên kết |
| Bo điều khiển | Giao thức và logic firmware có xử lý hết hạn lệnh; PWM ESC/servo đã chạy trên bàn thử (25/11/2026, bánh nhấc); đọc encoder/góc lái thật chưa hoàn thiện | Đo điểm chặn servo và ánh xạ xung–góc/tốc độ, phản hồi thật và kiểm watchdog trên xe |

Kết quả mô phỏng đã ghi nhận nằm trong [Kiểm thử và lộ trình](autopark/docs/KIEM_THU_VA_LO_TRINH.md). Kết quả đó chỉ áp dụng cho mô hình và bộ tình huống đã thử.

## Phân công trong kiến trúc mục tiêu

| Thiết bị | Công việc chính | Dữ liệu trao đổi |
|---|---|---|
| **Laptop** | Chạy AI trên ảnh từ bốn camera; hợp nhất dữ liệu cảm biến; nhận biết và chọn ô đỗ; lập và kiểm tra quỹ đạo | Nhận ảnh, dữ liệu LiDAR, tư thế và trạng thái từ Pi; gửi quỹ đạo cùng điều kiện thực hiện xuống Pi |
| **Pi 4 Model B · 8 GB trên xe** | Thu cảm biến; ước lượng vị trí và hướng xe; bám quỹ đạo theo phản hồi; chủ động yêu cầu dừng khi vùng chuyển động không an toàn hoặc dữ liệu/liên kết quá hạn | Nhận quỹ đạo qua Wi-Fi; gửi lệnh tốc độ/góc lái có hạn hiệu lực tới ESP32 qua USB ngắn; nhận phản hồi thật |
| **ESP32 trên xe** | Phát tín hiệu tới ESC và servo; đọc MT6701 #2 qua A/B và MT6701 #1 qua I²C; giám sát hạn lệnh và đưa cơ cấu về trạng thái dừng khi hết hạn | Nhận lệnh từ Pi; trả số đo và trạng thái lỗi về Pi |

**AI không phát lệnh lái trực tiếp.** Laptop gửi quỹ đạo để Pi thực hiện; Pi tự tính các nhịp điều khiển tại xe. Wi-Fi không phải đường truyền từng nhịp đánh lái từ laptop.

Laptop và Pi kết nối **Wi-Fi trong cùng mạng LAN**, có thể qua router hoặc điểm phát tại chỗ. **Không cần Internet hay 4G để vận hành cấu hình này.** 4G chỉ là lựa chọn truy cập từ xa về sau, chưa nằm trong cấu hình vận hành hiện tại.

Trên xe, LiDAR C1 dùng adapter USB nối Pi; bốn camera USB nối qua hub tới Pi; Pi nối ESP32 bằng cáp USB ngắn. Pi chuyển dữ liệu cần thiết lên laptop để xử lý AI và lập đường. Băng thông camera, độ trễ, khả năng cấp nguồn của hub và tải xử lý trên Pi còn cần đo khi tích hợp.

## Hai luồng cần đọc trước

### Nhận biết vật cản và dừng

Pi thu LiDAR, ảnh camera và phản hồi chuyển động. Laptop chạy AI và hợp nhất bằng chứng vật cản; Pi duy trì định vị và giám sát cục bộ vùng mà toàn thân xe sắp đi qua. Khi vật cản làm vùng này không an toàn, dữ liệu cần thiết quá hạn hoặc liên kết mất quá ngưỡng giám sát, xe phải dừng. ESP32 có thêm watchdog để xử lý lệnh từ Pi hết hạn.

![Thiết kế mục tiêu: luồng nhận biết vật cản và dừng trên Laptop–Pi–ESP32](autopark/docs/images/luong-vat-can.png?v=3c4768033b92)

Đọc [Luồng vật cản](autopark/docs/LUONG_VAT_CAN.md) để theo dõi nguồn dữ liệu, nơi xử lý và trách nhiệm dừng của từng thiết bị.

### Chọn ô đỗ, tính đường và thực hiện

Laptop dùng bản đồ vật cản và tư thế đo được để đánh giá ô đỗ, tính đường tiến/lùi và kiểm khoảng trống cho toàn thân xe. Sau khi người dùng xác nhận, laptop gửi quỹ đạo xuống Pi. Pi kiểm điều kiện thực hiện, bám đường bằng phản hồi tại xe và gửi lệnh ngắn hạn tới ESP32.

![Thiết kế mục tiêu: chọn ô đỗ, tính quỹ đạo trên laptop và bám đường trên Pi](autopark/docs/images/luong-tinh-duong.png?v=f065af9e9ba1)

**Xe không tự chạy lại khi vật cản biến mất hoặc mạng/dữ liệu phục hồi.** Sau khi xác nhận xe đứng yên, Pi cung cấp tư thế mới đo được; laptop tính lại đường từ tư thế đó. Người dùng phải xác nhận lượt chạy mới. Nếu chưa có tư thế hoặc dữ liệu hợp lệ, xe tiếp tục đứng yên.

Đọc [Luồng tính đường](autopark/docs/LUONG_TINH_DUONG.md) để phân biệt chọn ô, lập quỹ đạo, bám đường và tính lại sau khi dừng. Ứng dụng đã tự tìm ô đỗ và cho bấm chọn ô, hoặc kéo đích bằng tay. Bám quỹ đạo trên Pi là bước triển khai tiếp theo.

## Phần cứng và nguồn điện

Chi tiết linh kiện, chân GPIO đề xuất, đầu nối, điều kiện tương thích, cách gá phản hồi và trình tự kiểm tra được giữ tại [Lắp ráp điện 2D](autopark/docs/LAP_RAP_DIEN_2D.md). Đây là tài liệu cần đối chiếu trước khi đi dây.

Ba nhánh nguồn cần phân biệt:

- **Motor:** pin LiPo 2S cấp ESC QuicRun 1060; ESC cấp motor kéo.
- **Servo:** lấy nguồn từ BEC 6 V của ESC; đã chạy ổn trên bàn thử ngày 24/11/2026.
- **Pi và thiết bị USB:** Pi cần nguồn ổn áp riêng phù hợp model và tổng tải. **Không cấp Pi bằng BEC 6 V của ESC.** ESP32 dùng USB từ Pi theo thiết kế; nguồn cho hub/camera và khả năng cấp dòng của từng cổng phải được kiểm tra.

Bộ hình SVG và PNG mô tả bố trí mục tiêu cho bốn camera và hai MT6701. Sơ đồ chân BNO085 sẽ được bổ sung sau lượt thử trên bàn.

![Thiết kế mục tiêu: linh kiện và các đầu nối](autopark/docs/hardware/wiring-v1/00-components.png?v=9ac413ffc93c)

*Nhận diện linh kiện và đầu nối; module, điện áp và cách gá chưa chốt phải được đối chiếu với thiết bị thực nhận.*

![Thiết kế mục tiêu: nguồn và kết nối các khối trên xe](autopark/docs/hardware/wiring-v1/01-system.png?v=b04a45841440)

*Nguồn Pi tách biệt với nhánh BEC cấp servo.*

![Thiết kế mục tiêu: USB, tín hiệu điều khiển và phản hồi](autopark/docs/hardware/wiring-v1/02-signal-feedback.png?v=8a5bdf9db514)

*C1 và hub bốn camera nối Pi; Pi nối ESP32 bằng USB ngắn. MT6701 #1 (I²C, góc lái) và MT6701 #2 (A/B, chuyển động) trả phản hồi về ESP32.*

![Thiết kế sạc riêng cho pin LiPo 2S](autopark/docs/hardware/wiring-v1/03-charging.png?v=6f5b5dda4a87)

*Sạc B3 dùng giắc cân bằng 2S khi pin đã tách khỏi ESC và mọi tải trên xe. Không chạy xe đồng thời với sạc.*

## Chạy mô phỏng hiện có

Từ thư mục gốc repository, dùng Python 3.11 trở lên trong PowerShell:

```powershell
cd autopark
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe run_app.py scenarios/thao_tac_cua_hep.json
```

Có thể thay kịch bản bằng `scenarios/thao_tac_lui_vao_khe.json`. Trong giao diện, kéo đích tới vị trí và hướng mong muốn, tính thao tác, xem trước rồi xác nhận thực hiện trong mô phỏng. Cách chạy này chưa triển khai dịch vụ trên Pi hoặc điều khiển xe thật.

Để thử tự tìm ô đỗ, mở `scenarios/tim_khe_vuong_goc.json` hoặc `scenarios/tim_khe_song_song.json` và bấm **Tìm ô đỗ**. Bấm một ô để đặt đích; bấm lại để đổi lùi vào ↔ tiến vào. Chạy cả chuỗi từ quét LiDAR đến đỗ xong không cần giao diện:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.simulation.slot_run --scenario scenarios/tim_khe_vuong_goc.json --out runs/slot_run
```

![Giao diện mô phỏng cảnh cua hẹp](autopark/docs/images/giao-dien-cua-hep.png)

*Ảnh mô phỏng đường tiến/lùi và vùng thân xe quét qua. Giới hạn của các cảnh mẫu thuộc cấu hình mô phỏng, chưa phải thông số đã đo trên xe.*

## Đọc tiếp theo công việc

| Bạn muốn tìm hiểu | Tài liệu |
|---|---|
| Cách dữ liệu trở thành vật cản và yêu cầu dừng | [Luồng vật cản](autopark/docs/LUONG_VAT_CAN.md) |
| Cách chọn ô, tính đường và chạy một lượt | [Luồng tính đường](autopark/docs/LUONG_TINH_DUONG.md) |
| Cấu trúc các khối phần mềm | [Kiến trúc](autopark/docs/KIEN_TRUC.md) |
| Cách dùng, lưu và phát lại mô phỏng | [Vận hành](autopark/docs/VAN_HANH.md) |
| Đi dây, cấp nguồn và đối chiếu chân | [Lắp ráp điện 2D](autopark/docs/LAP_RAP_DIEN_2D.md) |
| Đo xe, gá và hiệu chuẩn cảm biến | [Phần cứng và hiệu chuẩn](autopark/docs/PHAN_CUNG_VA_HIEU_CHUAN.md) |
| Việc đang làm và cách tiếp tục | [Bàn giao AutoPark](BAN_GIAO_CODEX.md) |
| Bằng chứng hiện có và các bước còn thiếu | [Kiểm thử và lộ trình](autopark/docs/KIEM_THU_VA_LO_TRINH.md) |
| Nguồn dữ liệu và điều kiện sử dụng | [Dữ liệu và giấy phép](autopark/docs/DU_LIEU_VA_GIAY_PHEP.md) |
