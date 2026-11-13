# Kết nối điện AutoPark — mục tiêu Laptop, Pi trên xe và ESP32

Ngày cập nhật thiết kế: 13/11/2026. Cấu hình tham chiếu: ESP32-S3-DevKitC-1 N16R8 và Hobbywing QuicRun 1060 Brushed giắc T. Bổ sung Raspberry Pi trên xe, nguồn ổn áp riêng cho Pi và nguồn hub phù hợp; model/công suất/đầu nối của các phần bổ sung còn chờ chọn và đo kiểm.

**Đây là thiết kế kết nối và bản đồ chân đề xuất, chưa phải kết quả lắp chạy trên xe.** Hình dáng motor, cụm lái và bo gốc được đối chiếu với ảnh người dùng. Các linh kiện dự định mua được vẽ theo hình dáng tham chiếu; vị trí chân trên module cảm biến, đầu nối servo và điện áp servo vẫn cần đối chiếu với hàng thực nhận. Màu cam/nét đứt chỉ phần chờ xác minh, không phải dây đã được phép cấp điện.

**Kiến trúc mục tiêu:** laptop chạy AI trên bốn luồng camera, fusion, chọn ô đỗ và lập quỹ đạo. Pi thu LiDAR/camera, định vị cục bộ từ số đo, bám quỹ đạo và dừng vật cản ngay trên xe. ESP32 thực hiện ga/lái, đọc encoder và góc lái thực, dừng khi lệnh từ Pi hết hạn. Laptop ↔ Pi qua Wi-Fi LAN; Pi ↔ ESP32 qua USB ngắn trên xe. Pi nhận quỹ đạo, không nhận từng nhịp góc lái từ laptop; AI không trực tiếp điều khiển chấp hành. 4G chỉ là tùy chọn điều khiển từ xa về sau.

**Mã hiện có chưa triển khai đầy đủ kiến trúc này:** ứng dụng đang phục vụ mô phỏng và thao tác đích gần do người dùng đặt; Pi phân tán và tự chọn ô đỗ chưa được triển khai trên xe. Firmware còn tắt PWM và chưa hoàn thiện đọc phản hồi vật lý. Các hình dưới đây đều là thiết kế mục tiêu, không phải sơ đồ một hệ đã lắp chạy.

## Bảng linh kiện và ba bản vẽ

Trước khi xem dây nối, mở [bảng nhận diện linh kiện và các chân — SVG](hardware/wiring-v1/00-components.svg) hoặc [PNG](hardware/wiring-v1/00-components.png?v=6e63bbce0540).

1. [Kết nối tổng thể — SVG](hardware/wiring-v1/01-system.svg) · [PNG](hardware/wiring-v1/01-system.png?v=acfaa2ca6cb8).
2. [Chi tiết tín hiệu và cảm biến — SVG](hardware/wiring-v1/02-signal-feedback.svg) · [PNG](hardware/wiring-v1/02-signal-feedback.png?v=511cc0a13238).
3. [Sạc pin tách khỏi xe — SVG](hardware/wiring-v1/03-charging.svg) · [PNG](hardware/wiring-v1/03-charging.png?v=26d85a84984b).

![Kết nối tổng thể](hardware/wiring-v1/01-system.png?v=acfaa2ca6cb8)

![Chi tiết tín hiệu và cảm biến](hardware/wiring-v1/02-signal-feedback.png?v=511cc0a13238)

![Sạc pin tách khỏi xe](hardware/wiring-v1/03-charging.png?v=26d85a84984b)

## Những bộ phận được giữ và thay

| Bộ phận | Vai trò trong bản thiết kế |
|---|---|
| Laptop chạy AutoPark | Mục tiêu: AI bốn camera, fusion, chọn ô và lập quỹ đạo; trao đổi dữ liệu với Pi qua Wi-Fi LAN |
| Raspberry Pi trên xe — chờ chọn model | Mục tiêu: thu cảm biến, định vị cục bộ, bám quỹ đạo, kiểm hành lang và dừng vật cản; làm USB host cho ESP32, C1 và hub camera |
| ESP32-S3-DevKitC-1 N16R8 | Mục tiêu: nhận lệnh ngắn hạn từ Pi, phát ga/lái, đọc tốc độ/góc lái thực, watchdog dừng khi lệnh hết hạn |
| Nguồn ổn áp cho Pi — chờ chọn | Nhánh riêng từ pin 2S; nguồn đúng yêu cầu Pi và tải USB C1/ESP32, qua cổng nguồn đúng model; không dùng BEC 6 V |
| Nguồn hub — chờ chọn | Nhánh riêng từ pin 2S; chỉ cấp DC-in được hãng hub hỗ trợ, đúng điện áp/cực/dòng cho bốn camera; kiểm không cấp ngược USB về Pi |
| QuicRun 1060 Brushed bản T | Điều khiển công suất cho motor kéo |
| Motor 280–60T trên xe | Giữ motor và truyền động hiện có |
| Cụm lái gốc nối ba dây | Dự kiến giữ; cần xác minh model, nguồn và tín hiệu trước khi nối |
| Encoder tốc độ | Ứng viên MT6701 ở chế độ A/B, kèm nam châm và gá; chưa chốt module thực nhận |
| Cảm biến góc lái | Ứng viên AS5600 qua I²C, kèm nam châm và gá; chưa chốt module thực nhận |
| LiDAR C1, adapter USB, bốn camera và hub | C1 → adapter USB → Pi; bốn camera USB → hub → Pi. Hub cũ chưa xác minh DC-in, cần chọn hub có nguồn phù hợp nếu không đạt; phải hiệu chuẩn và đo vị trí gá |
| Pin LiPo 2S 7,4 V, 1.500 mAh, giắc T | Pin dự định dùng; tối đa 8,4 V khi đầy, kích thước phải vừa xe |
| Sạc B3 Pro | Sạc riêng qua giắc cân bằng 2S; không nối trong lúc chạy xe |
| XL1986RT | Tháo khỏi đường điều khiển trong phương án này và cất riêng; không nối song song đầu motor với ESC mới |

Theo lựa chọn của người dùng, sơ đồ không bố trí nút dừng khẩn, phần tử ngắt động lực độc lập hoặc cầu chì bổ sung. ToF và IMU được để ngoài cấu hình bản đầu. Do đó bản này không có đường ngắt động lực độc lập khi bộ điều khiển lỗi. Tay điều khiển nguyên bản không còn điều khiển ga/lái theo sơ đồ này.

## Nguồn điện và các nhánh trên xe

**Nhánh pin và nguồn motor:** pin 2S qua đầu T chung tới bộ dây chia đúng cực: một nhánh ESC, một nhánh nguồn Pi, một nhánh nguồn hub. Trên Tờ 1, nhãn `P3+`/`P3−` ở hai vùng hình là sự tiếp tục của cùng nhánh pin; không phải một pin khác hoặc pinout giắc mới. Hai đầu ra motor của ESC nối vào motor 280 qua dây chuyển đúng loại. Không cho dòng motor đi qua chân ESP32, dây tín hiệu hoặc breadboard. Hai dây motor không phải dây nguồn cố định +/−: ESC đảo cực để đổi chiều quay. Công tắc trên ESC không ngắt nguồn hai nhánh Pi/hub.

Dòng khởi động/kẹt trục của motor, dòng servo và định mức dây/giắc thực nhận chưa được đo hoặc xác nhận. Các số dòng công bố của ESC hay pin không thay cho bước đối chiếu tải và đầu nối thực tế.

**Nguồn Pi:** chọn bộ DC–DC riêng có đầu vào chịu toàn dải pin 2S, đầu ra ổn áp theo đúng model Pi, cổng nguồn/cáp phù hợp và đủ dòng cho Pi cùng C1/ESP32 qua USB. Ký hiệu `+5 V`/GND trong hình tách hai lõi của cáp nguồn để đọc đường điện, không chỉ định cấp qua header GPIO. Phải kiểm sụt áp lúc khởi động/tải đồng thời, nhiễu motor, nhiệt và cách nhận nguồn USB-C nếu model yêu cầu. BEC 6 V của ESC không nối Pi. Chưa chốt model nên sơ đồ không gán một dòng định mức chung cho mọi Pi. Yêu cầu nguồn và giới hạn tải USB tùy model được nêu trong [tài liệu nguồn Raspberry Pi](https://www.raspberrypi.com/documentation/computers/getting-started.html#power-supply).

**Nguồn hub và bốn camera:** nguồn DC–DC thứ hai cấp đúng điện áp/cực/dòng vào DC-in mà nhà sản xuất hub hỗ trợ, đủ tải cả bốn camera. Không mặc định hub hiện có nhận nguồn phụ hoặc nhận 5 V. Chọn hub có nguồn phù hợp nếu hub cũ không đáp ứng; không tự đấu nguồn vào dây USB. Kiểm đường upstream không cấp ngược VBUS về Pi, không ghép song song đầu ra dương nguồn hub với nguồn Pi. Băng thông USB/Wi-Fi, FPS, độ trễ và đồng bộ thời gian của bốn camera phải đo trên cấu hình cuối.

**Nguồn ESP32:** nguồn và dữ liệu đi qua USB ngắn từ Pi tới cổng USB native của DevKitC-1. Cổng này phải được đối chiếu bằng chữ in trên bo và cấu hình USB CDC; không dựa vào vị trí trái/phải của hình minh họa. Không đồng thời cấp thêm nguồn vào chân 5V hoặc 3V3 của ESP32 theo sơ đồ này. Các chân 3V3 chỉ cấp cho module cảm biến 3,3 V đã xác minh và trong giới hạn nguồn của bo.

**Nguồn servo — bản sửa dùng BEC của ESC:** dây BEC dương của QuicRun 1060 cấp tới chân nguồn dương của servo; dây GND servo về GND của ESC/BEC. Mẫu 1060 tham chiếu có BEC 6 V/3 A. **Chỉ nối nhánh nguồn này sau khi xác nhận servo hỗ trợ 6 V, điện áp BEC thực đúng và khả năng cấp dòng đáp ứng tải lái.** Servo gốc hiện vẫn chưa xác minh model/điện áp; chọn phương án này không đồng nghĩa đã xác nhận tương thích.

Bản này không dùng bộ ổn áp servo rời. Servo nhận nguồn BEC có điều kiện; hai bộ DC–DC mới chỉ dành cho Pi và hub. Nhánh chia pin mới không cấp trực tiếp servo, không lấy từ giắc cân bằng và không nối đầu ra BEC với đầu ra các DC–DC.

**Giắc điều khiển ESC cần được tách đúng chức năng:** Signal của ESC nhận ga từ GPIO4; BEC dương và GND cấp nguồn servo; Signal của servo nhận lái riêng từ GPIO5. Không cắm nguyên giắc ba chân ESC vào giắc servo hoặc dùng dây Y ba lõi nối chung hai Signal. Có thể dùng bộ dây chuyển làm sẵn đúng sơ đồ. **BEC dương không nối vào chân 3V3, 5V hoặc GPIO của ESP32**, và không ghép song song với nguồn servo khác.

Các GND của ESP32, ESC, module cảm biến và servo phải có cùng tham chiếu. Dòng hồi servo đi về ESC/BEC bằng dây nguồn phù hợp; nhánh GND tới ESP32 chỉ làm tham chiếu tín hiệu, không dẫn dòng tải servo xuyên qua bo ESP32. Chọn DC–DC không cách ly cho phương án này và kiểm IN−/OUT− cùng tham chiếu; Pi/ESP/hub còn liên hệ GND qua cáp USB. Dòng tải motor/servo vẫn phải hồi trên dây nguồn riêng, không qua cáp USB. Kiểm liên hệ GND tín hiệu với cực âm nguồn ESC trên hàng thực nhận.

## Bản đồ chân ESP32 đề xuất

Các số J1 dưới đây đối chiếu header DevKitC-1 chính thức. Hình bo nhìn từ phía linh kiện, nhưng khi lắp vẫn phải đọc chữ in trên bo thực. Chỉ áp dụng bảng khi bo đúng DevKitC-1 và các chân đó còn trống.

| Chức năng | Chân ESP32 đề xuất | Vị trí header tham chiếu | Đầu bên kia | Trạng thái |
|---|---|---|---|---|
| `ESC_CTRL` | GPIO4 | J1-4 | Signal của giắc điều khiển ESC | Chờ xác minh ESC nhận mức 3,3 V |
| `SERVO_CTRL` | GPIO5 | J1-5 | Signal của servo | Chờ xác minh giao tiếp và mức tín hiệu servo |
| `AS_SDA` | GPIO6 | J1-6 | SDA của AS5600 | Module phải có I²C mức 3,3 V |
| `AS_SCL` | GPIO7 | J1-7 | SCL của AS5600 | Điện trở kéo lên chỉ tới 3,3 V |
| `ENC_A` | GPIO8 | J1-12 | A của module MT6701 cấu hình A/B | Chờ module, chế độ và gá thực |
| `ENC_B` | GPIO9 | J1-15 | B của module MT6701 cấu hình A/B | Chờ module, chế độ và gá thực |
| Nguồn cảm biến | 3V3 | J1-1 hoặc J1-2 | Nguồn 3,3 V của module đã xác minh | Không phải đầu vào nguồn 6 V |
| Tham chiếu logic | GND | J1-22 | GND chung | Đối chiếu thông mạch khi chưa cấp nguồn |

Đây là lựa chọn chân của bản thiết kế, không phải chức năng tự có của GPIO4…9. Firmware phải cấu hình chúng tương ứng. Không dùng GPIO19/20 cho các tín hiệu trên vì dành cho USB native; không dùng chân strapping hoặc chân bộ nhớ của biến thể N16R8 trong bảng này.

## Các giắc dễ nhầm

| Đầu nối | Cách dùng trong sơ đồ |
|---|---|
| T/Deans hai cực | Pin → bộ dây chia ESC / nguồn Pi / nguồn hub; đúng cặp đầu nối và cực. Rút tại đầu pin chung sẽ tách mọi tải khi sạc |
| Giắc cân bằng LiPo 2S ba chân | Chỉ tới cổng 2S của B3 khi pin đã tách khỏi xe; là các điểm cell, không phải Signal/nguồn/GND của servo |
| Ba dây nhỏ của ESC | Signal → GPIO4; GND → servo/GND chung; BEC dương → nguồn servo, chỉ khi xác minh dùng được 6 V |
| Ba dây của servo | Signal → GPIO5 riêng biệt với Signal của ESC; nguồn → BEC dương; GND → ESC/BEC và GND chung. Đối chiếu chân thực trước khi nối |
| Bullet ở đầu motor ESC | Nối sang giắc motor hai chân bằng dây chuyển được xác nhận; chiều tiến/lùi được kiểm và hiệu chuẩn sau |
| USB C1 | C1 giữ adapter USB đang có; adapter nối Pi trên xe. Không nối UART của C1 sang chân ESP trong phương án này |
| USB camera | Bốn camera nối hub rồi tới Pi. CAM1…CAM4 là số minh họa, chưa xác nhận tương ứng trước/sau/trái/phải |
| USB Pi–ESP32 | Cáp ngắn trên xe: nguồn + dữ liệu qua USB native/CDC của ESP32 |
| Wi-Fi LAN laptop–Pi | Dữ liệu hai chiều; laptop gửi quỹ đạo/xác nhận, Pi gửi ảnh/scan/pose/trạng thái. Không phải dây điện, không cấp nguồn xe |

Nếu ESC hoặc servo không nhận mức tín hiệu 3,3 V, cần chọn mạch đệm/chuyển mức đúng loại rồi cập nhật đường Signal. Sơ đồ không tự giả định 5 V hoặc 6 V là mức tín hiệu hợp lệ cho ESP32.

## Lắp cơ khí và phản hồi

Encoder tốc độ đo góc/số vòng ở trục hoặc bánh được chọn, rồi quy đổi ra tốc độ và quãng đường bằng tỷ số truyền, đường kính bánh và chiều quay đã đo. Với MT6701, phải chốt đúng module và chế độ A/B; các chân A/B có thể dùng chung chức năng với giao tiếp khác tùy chế độ. Không lấy thứ tự pad trên hình minh họa làm pinout của mọi module MT6701.

Tên MT6701 chưa đủ để xác nhận độ phân giải: một số biến thể mặc định chỉ có 1 xung/vòng ở đầu ra A/B. Cần chọn hoặc cấu hình đúng số xung/vòng (PPR) rồi kiểm lại ở tốc độ thấp trên vị trí gá thực. Ưu tiên module đã được cấu hình và kiểm PPR; không tự nâng nguồn 3V3 của ESP32 để lập trình EEPROM cho cảm biến.

AS5600 đo góc nam châm gắn với cơ cấu lái. Gá phải giữ khoảng cách/hướng nam châm đúng yêu cầu cảm biến và hiệu chuẩn ra góc bánh xe. Đường nét đứt giữa nam châm và trục/cảm biến biểu diễn liên hệ cơ khí/từ trường, không phải dây điện.

Hub hiện có chưa được xác nhận model và khả năng nhận nguồn phụ. Chỉ dùng cổng nguồn phụ nếu đúng thiết kế của hub, đúng điện áp và cách cấp nguồn; không tự ghép nguồn vào dây USB. Gá LiDAR/camera chắc chắn rồi đo vị trí, hướng, vùng che và hiệu chuẩn trước khi dùng làm tư thế/vật cản cho xe thật.

## Dừng và lập lại quỹ đạo — yêu cầu mục tiêu

Pi phải dừng và giữ dừng khi vật cản làm hành lang quỹ đạo không an toàn, dữ liệu cảm biến/tư thế/quỹ đạo quá cũ hoặc mất liên kết laptop. ESP32 phải dừng khi lệnh từ Pi hết hạn hay mất USB; Wi-Fi không được nằm trong vòng xuất từng nhịp chấp hành. Gói tin cần dấu thời gian, thời hạn hiệu lực và phiên/lượt chạy để loại lệnh cũ. Các ngưỡng phải được thiết kế và kiểm trên xe; bản vẽ chưa xác nhận triển khai này.

Không tự chạy lại khi vật cản biến mất hoặc liên kết trở lại. Khi đã dừng, lấy **tư thế mới đo được**, gửi về laptop để fusion/chọn ô nếu cần và lập quỹ đạo mới; kiểm lại dữ liệu, đường đi rồi xác nhận lượt chạy mới. Không tiếp tục mù quỹ đạo cũ hoặc coi tư thế mô phỏng là tư thế xe thật.

## Trình tự lắp và kiểm tra

1. Ghi lại bo, ESC, servo, module cảm biến và tất cả đầu giắc thực nhận. Đối chiếu chữ in chân và dấu cực; tách pin khỏi xe trong lúc đi dây.
2. Bố trí cơ khí motor/servo giữ nguyên, gá các cảm biến. Xác định tuyến dây để tránh trục quay, bánh và hệ treo.
3. Chuẩn bị bộ dây chia T cho ESC / DC–DC Pi / DC–DC hub và dây chuyển motor. Chọn đầu vào DC–DC chịu toàn dải 2S, dây/giắc đủ tải; giữ pin tách mọi tải trong lúc đi dây. Nhánh BEC → servo cũng để rời tới khi đã xác minh servo hỗ trợ 6 V và kiểm nguồn.
4. Đấu dây chuyển tách Signal ga và Signal lái theo bảng chân; đo thông mạch khi chưa cấp điện. BEC dương chỉ có đích tới nguồn servo, không tới nguồn/GPIO ESP32; hai Signal không nối chung.
5. Khi động lực chưa nối, kiểm riêng điện áp/cực/tải của nguồn Pi và nguồn hub trước khi cắm thiết bị. Xác nhận hub không cấp ngược Pi qua upstream, rồi kiểm C1 và bốn camera đồng thời về Pi. Cấp ESP32 bằng USB từ Pi, hoàn thiện và kiểm firmware: đọc cảm biến đúng chiều/dấu/đơn vị, đo xung ga/lái và điện áp tín hiệu.
6. Với motor và servo còn tách, kiểm điện áp BEC theo hướng dẫn của ESC. Khi nguồn, định mức servo, tín hiệu và firmware đã được xác minh, kết nối từng bộ chấp hành rồi thử với bánh kê khỏi mặt bàn. Hiệu chuẩn trung tính ga, chiều quay, hành trình servo và giới hạn cơ khí.
7. Sau đó mới đo tốc độ thấp, phanh, tư thế thực và phản hồi khi mất Wi-Fi, mất USB, lệnh/dữ liệu hết hạn hoặc xuất hiện vật cản trong hành lang. Kiểm xe giữ dừng khi liên kết trở lại; chỉ chạy lượt mới sau khi laptop lập lại từ tư thế mới và có xác nhận. Sơ đồ này không chứng minh xe đã đạt các phép đo đó.

### Trạng thái firmware tại lúc vẽ

Mã hiện tại vẫn đặt `kPinEsc`, `kPinServo`, `kPinEstop` bằng `-1` và `AP_ENABLE_PWM_OUTPUTS=0`. Khi bật PWM, mã còn kiểm tĩnh yêu cầu cấu hình chân E-stop. Vì bản thiết kế này theo lựa chọn bỏ E-stop, **không thể chỉ đổi cờ PWM thành 1 rồi coi là chạy được**; cần thiết kế và kiểm nhánh cấu hình firmware phù hợp. Không gán một chân giả chỉ để vượt kiểm tra đó.

Phần đọc cảm biến thật trong `read_inputs()` chưa hoàn thiện. Phần mềm hiện tại còn yêu cầu số đo tốc độ/góc lái và nguồn tư thế thật hợp lệ trước START. Giới hạn tốc độ mô phỏng 0,10 m/s cũng chưa tự thay các hằng số giới hạn trong firmware bo. Phân vai laptop–Pi trong tài liệu là mục tiêu cần triển khai, không có nghĩa vòng bám hiện đã chuyển sang Pi. Đợt cập nhật bản vẽ không sửa hoặc bật firmware điều khiển xe.

## Sạc pin: sơ đồ riêng, không chạy xe đồng thời

1. Ngắt đầu T chung của pin khỏi ESC và cả hai nhánh nguồn Pi/hub; không chỉ tắt công tắc ESC. Tắt Pi đúng quy trình trước khi ngắt nguồn khi có thể.
2. Kết nối nguồn AC của B3 theo hướng dẫn bộ sạc; AC không đi tới ESP32 hay ESC.
3. Nối giắc cân bằng ba chân của pin LiPo 2S vào đúng cổng 2S. Cổng 3S để trống. Giắc T của pin không dùng trong sơ đồ sạc B3 và được giữ tránh chạm chập.
4. Chỉ nối một pack mỗi lần; pin phải cho phép dòng sạc của chiếc B3 thực nhận. Theo dõi quá trình sạc và ngắt khi hoàn tất theo chỉ báo của bộ sạc.

Không coi giắc cân bằng ba chân là SM3P nguồn chỉ vì có cùng số chân. Không dùng sơ đồ này để sạc khối Li-ion 18650 nguyên bản: bản vẽ sạc dành riêng cho pack LiPo 2S đang chọn.

## Nguồn tham khảo và phạm vi xác nhận

- [Espressif — ESP32-S3-DevKitC-1 v1.1](https://documentation.espressif.com/api/resource/path/docs/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html): header và các lựa chọn nguồn. Hình bo là tham chiếu; đối chiếu lại PCB thực.
- [Hobbywing — QuicRun 1060 Brushed](https://www.hobbywingdirect.com/products/quicrun-10-brushed-esc): giắc T, motor chổi than, nguồn 2S/3S và BEC 6 V/3 A của model được công bố.
- [Hobbywing — hướng dẫn 1625/1060/860](https://www.hobbywing.com/en/uploads/file/20240315/e8525a6a27f4e1dcbe3af554c06deac0.pdf): dây motor/nguồn, chế độ F/R và thao tác hiệu chuẩn. Chưa tìm thấy ngưỡng đầu vào chứng minh 3,3 V cho chiếc ESC thực nhận.
- [B3 Pro — hướng dẫn của imaxRC, bản lưu tại RC Factory](https://www.rc-factory.cz/assets/docs/da21c8a03bc75ae73c4b5362c3acef7c/1321-1/b3-pro-manual.pdf): hai cổng cân bằng 2S/3S và dòng công bố. Tên trên gian hàng không tự xác nhận chất lượng chiếc sạc.
- [MagnTek — MT6701](https://www.magntek.com.cn/136/108) và [datasheet Rev1.8](https://www.magntek.com.cn/upload/pdf/202407/MT6701_Rev.1.8.pdf): cảm biến góc từ, các kiểu đầu ra và PPR theo biến thể; module, nam châm, chế độ và gá của dự án chưa chốt.
- [ams OSRAM — AS5600, tài liệu evaluation board](https://look.ams-osram.com/m/4f8342513a447495/original/AS5600_UG000254_2-00.pdf): tham chiếu giao tiếp I²C và chế độ 3,3 V. Không thay pinout của module người dùng mua.
- [SLAMTEC — RPLIDAR C1](https://www.slamtec.com/en/c1/spec): giao tiếp của cảm biến; hệ thống này dùng adapter USB hiện có.
- Ảnh xe người dùng tại thư mục `ảnh mạch/`: xác nhận nhãn 280–60T, bo XL1986RT và vị trí cụm lái. Ảnh gốc không được nhúng vào bản vẽ hay tự đưa lên GitHub.

## Tệp nguồn và kiểm tra

Bản vẽ được dựng bằng SVG từ mã Python, sau đó xuất PNG để đọc trên GitHub. Các pad có tọa độ xác định giúp đối chiếu nét dây và đầu nối; đây không phải mô phỏng điện hoặc mô phỏng mạch đã chạy.

- Thư viện hình linh kiện: [components.py](hardware/wiring-v1/components.py).
- Ghép sơ đồ: [build_wiring.py](hardware/wiring-v1/build_wiring.py).
- Danh sách mạng dây: [wiring_spec.json](hardware/wiring-v1/wiring_spec.json).
- Ghi chú linh kiện: [component_notes.md](hardware/wiring-v1/component_notes.md).
- Ghi chú tự kiểm của tác giả, chờ nhóm kiểm độc lập: [REVIEW.md](hardware/wiring-v1/REVIEW.md).

Kết quả kiểm tra hình và cách dựng lại được ghi trong thư mục nguồn cùng bản vẽ.
