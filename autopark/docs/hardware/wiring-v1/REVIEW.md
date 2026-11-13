# Kiểm tra bộ bản vẽ điện 2D AutoPark

Ngày cập nhật: **13/11/2026**. Revision: **`laptop_pi_esp32_target_v3`**.

Đây là ghi chú tự kiểm của tác giả bản cập nhật. Báo cáo PASS độc lập ngày 08/11/2026 của revision `esc_bec_servo_v2` đã được thay thế; kết quả cũ không áp dụng cho kiến trúc mới. Bản này ghi rõ các kiểm tra tài liệu đã làm và các hạng mục phần cứng còn mở, không xác nhận xe đã lắp/chạy.

## Nội dung thay đổi và phạm vi

- Laptop chạy AI bốn camera, fusion, chọn ô và lập quỹ đạo; trao đổi với Pi bằng Wi-Fi LAN. Pi nhận quỹ đạo và xác nhận lượt chạy, không nhận từng nhịp lái qua Wi-Fi. 4G chỉ là tùy chọn về sau.
- Pi trên xe thu C1/camera, định vị cục bộ, bám quỹ đạo và dừng vật cản. ESP32 nhận lệnh ngắn hạn qua USB, phát ga/lái, đọc encoder/góc lái và watchdog lệnh hết hạn. Đây là vai trò mục tiêu, chưa phải triển khai đã chạy.
- Pin 2S chia ba nhánh: ESC, DC–DC Pi và DC–DC hub. Hai nhãn `P3+`/`P3−` trên Tờ 1 nối tiếp cùng nhánh pin giữa hai vùng hình, không phải nguồn mới. Hai đường đầu ra dương DC–DC độc lập, không nối BEC.
- Nguồn Pi theo đúng model và tải C1/ESP qua USB; nguồn hub theo đúng DC-in/cực/dòng của hub được chọn, đủ bốn camera và không cấp ngược VBUS về Pi. Pi, DC–DC và hub có nguồn đều chưa chốt model/đo kiểm.
- BEC 6 V chỉ cấp servo khi xác minh tương thích điện áp và đủ dòng. Hai Signal ga/lái tách riêng, GND servo hồi trực tiếp ESC/BEC. Không thêm E-stop, ToF hoặc IMU vào cấu hình.
- Sạc B3 giữ nguyên mạch: pin tách toàn bộ xe, chỉ cáp cân bằng 2S, cổng 3S bỏ trống và giắc T che tiếp điểm. Tắt công tắc ESC không ngắt hai nhánh nguồn Pi/hub.

Chỉ sửa `docs/hardware/wiring-v1/**` và `docs/LAP_RAP_DIEN_2D.md`. Không đọc lại, sửa, nhúng hoặc đưa ảnh nguồn từ thư mục người dùng vào bộ xuất. Hình kế thừa phong cách vector có sẵn, Pi và bộ nguồn được dựng bằng hình học trong mã, không dùng ImageGen.

## Đối chiếu mã hiện có

Đã đọc `firmware/esp32_vehicle/src/main.cpp`, `src/core/vehicle_core.cpp` và các đoạn ứng dụng trong `autopark/ui/main_window.py`. Ứng dụng còn thao tác đích gần do người dùng đặt và mô phỏng; không có căn cứ xem bản vẽ như bằng chứng đã triển khai Pi phân tán hoặc tự chọn ô đỗ.

Firmware còn `kPinEsc = kPinServo = kPinEstop = -1`, mặc định `AP_ENABLE_PWM_OUTPUTS=0`; `read_inputs()` chưa hoàn thiện phản hồi vật lý. Khi bật PWM, kiểm tĩnh còn yêu cầu cấu hình chân E-stop. Cần thiết kế/kiểm cấu hình firmware phù hợp lựa chọn hiện tại; không gán chân giả để vượt kiểm tra. Đợt tài liệu không sửa hoặc bật firmware.

Yêu cầu dừng mục tiêu được ghi trên ảnh và hướng dẫn: vật cản làm hành lang không an toàn, dữ liệu/pose/quỹ đạo cũ hoặc mất liên kết → dừng và giữ dừng. ESP32 dừng khi lệnh Pi hết hạn/mất USB. Không tự khởi động lại; laptop lập lại từ tư thế mới đo lúc xe đã dừng, rồi cần xác nhận lượt chạy mới.

## Kiểm tra bản dựng

| Hạng mục | Kết quả trong phạm vi tài liệu |
|---|---|
| Catalogue | 17 loại hình, bao gồm Pi và hai bộ DC–DC; một hình camera được dùng bốn lần. Số lượng, ngày và chiều cao catalogue sinh từ mã |
| Net nguồn/tín hiệu | 17 net hoạt động; mọi mốc cổng tồn tại, không có cổng thuộc hai net khác nhau; BEC chỉ tới servo, hai đầu motor không ghép GND |
| Liên kết dữ liệu | 7 cáp USB: Pi–ESP, Pi–hub, Pi–adapter C1 và 4 hub–camera; 1 cáp gốc adapter–C1 khai báo riêng; 1 Wi-Fi laptop–Pi không phải dây điện |
| GND | Hồi tải servo trực tiếp ESC; liên hệ BAT−/GND ESC, IN−/OUT− các DC–DC không cách ly và GND qua USB khai báo riêng để xác minh trên hàng thật |
| Sạc | 3 net cân bằng ghép cùng tên, không chứa tải xe; yêu cầu tách ESC và cả hai nguồn Pi/hub |
| SVG/PNG | Render đủ bốn ảnh bằng `autopark/.venv/Scripts/python.exe` + PySide6 QtSvg; SVG parse được, không nhúng media, PNG mở lại đúng kích thước và không rỗng |
| Bố cục | Tự xem đủ bốn PNG; sửa nhãn P3 khỏi thân ESC/công tắc, tách rõ hai dây nguồn Pi. Nhóm tích hợp đã xem catalogue/sạc/tín hiệu và yêu cầu sửa hai nhãn P3 |
| Hash và liên kết | Hash nguồn và 8 tệp SVG/PNG nằm trong `export_manifest.json`; renderer tự cập nhật `?v=` trong hướng dẫn lắp, không sửa README gốc |
| Tính xác định | Dựng lại bằng cùng Python/Qt/font: cả 8 SVG/PNG, spec và manifest giống từng byte; kiểm lại hash nguồn, hash ảnh và mọi `?v=` trong hướng dẫn đều khớp |

Kích thước PNG mặc định 2×: `00-components.png` **3600×4190**, `01-system.png` **4600×5700**, `02-signal-feedback.png` **5600×4880**, `03-charging.png` **4400×2700**. Ngày trên cả ba tờ và catalogue lấy từ `DESIGN_DATE`; manifest/spec dùng cùng ngày. Hash chi tiết tham chiếu manifest thay vì chép một bản dễ lỗi thời vào báo cáo này.

## Các điều kiện chưa được kiểm trên thiết bị

Chưa kiểm model Pi, nguồn/cáp/USB-C và tải động; hub DC-in, định mức và cấp ngược USB; dòng motor/servo, giắc/dây chia pin và nhiễu/sụt áp/nhiệt; servo 6 V, điện áp BEC thực, mức logic ga/lái; chân/mode/PPR encoder và module góc lái; gá/hiệu chuẩn LiDAR/camera; băng thông USB/Wi-Fi và thời gian dữ liệu; driver, ngưỡng dừng và quy trình xác nhận lại. Nét đứt và cổng có dấu * là điều kiện chờ xác minh, không phải dây được nghiệm thu.

Nguồn tham chiếu mới: [Raspberry Pi — yêu cầu nguồn theo model](https://www.raspberrypi.com/documentation/computers/getting-started.html#power-supply). BEC tham chiếu đối chiếu lại [Hobbywing — manual QuicRun 1625/1060/860](https://www.hobbywing.com/en/uploads/file/20240315/e8525a6a27f4e1dcbe3af554c06deac0.pdf). Các tài liệu pinout/cảm biến/sạc kế thừa được dẫn trong [hướng dẫn lắp](../../LAP_RAP_DIEN_2D.md) và [ghi chú linh kiện](component_notes.md); chúng không thay cho kiểm tra thiết bị thực nhận.
