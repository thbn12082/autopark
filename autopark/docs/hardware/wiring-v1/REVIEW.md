# Kiểm tra độc lập sơ đồ điện 2D AutoPark

Ngày kiểm tra: 08/11/2026. Vai trò: agent `review_wiring`, độc lập với agent vẽ linh kiện và agent ghép dây.

Revision được duyệt: **`esc_bec_servo_v2` — servo lấy nguồn từ BEC của ESC có điều kiện**. Báo cáo này thay thế kết quả duyệt phương án nguồn servo rời trước đó.

**Trạng thái: PASS trong phạm vi tài liệu thiết kế — hình, netlist và hướng dẫn nhất quán sau các lần sửa. Chưa kiểm chứng phần cứng.**

PASS có nghĩa không còn lỗi chặn xuất bản được phát hiện trong bộ hình và tài liệu được liệt kê dưới đây. Không dùng trạng thái này để kết luận hàng thực nhận tương thích, dây đã lắp đúng hoặc xe đã đủ điều kiện cấp động lực. Các mục chờ đo/xác minh phần cứng vẫn có hiệu lực.

## Phạm vi đã kiểm

- Đã đọc `LAP_RAP_DIEN_2D.md` và các điểm liên quan trong `firmware/esp32_vehicle/platformio.ini`, `src/main.cpp`, `autopark/application/vehicle_link.py`.
- Đã xem ảnh toàn cảnh xe người dùng: nhãn motor 280–60T, bo XL1986RT và vị trí cụm lái có bó ba dây. Ảnh chưa xác nhận model, điện áp hoặc ngưỡng tín hiệu của cụm lái.
- Đã đối chiếu tài liệu Espressif, Hobbywing, imaxRC/B3, ams OSRAM và MagnTek. Hình module cảm biến phải được hiểu là tham chiếu chức năng, chưa phải pinout của hàng thực nhận.
- Đã xem đủ bốn PNG hoàn chỉnh: danh mục linh kiện và ba tờ nguồn/chấp hành, tín hiệu/phản hồi, sạc riêng. Đã kiểm mã dựng, netlist JSON, các đầu mút dây và các điểm giao cắt trong hình.

## Kết quả kiểm văn bản và lựa chọn chân

| Mục | Kết quả tại lần kiểm này |
|---|---|
| ESP32 lấy nguồn qua USB | Phù hợp phạm vi thử trên bàn; hướng dẫn loại trừ cấp đồng thời thêm 5V/3V3 từ nguồn khác |
| Dây BEC đỏ của ESC | Chỉ tới nguồn dương servo qua nhánh có điều kiện; không đưa BEC vào ESP32 hoặc ghép song song nguồn khác |
| Nguồn servo | BEC của 1060 tham chiếu là 6 V/3 A; chỉ nối sau khi xác nhận servo hỗ trợ 6 V, điện áp BEC thực và dòng tải phù hợp. Đã bỏ bộ ổn áp rời và nhánh chia nguồn pin |
| GND và dòng động lực | Servo hồi trực tiếp về ESC/BEC; nhánh tới ESP32 chỉ là tham chiếu tín hiệu. Dòng motor không đi qua ESP32 hoặc breadboard |
| Tách giắc điều khiển ESC | GPIO4 tới Signal ESC, GPIO5 tới Signal servo; BEC+/GND cấp servo. Hướng dẫn loại trừ dây Y ba lõi nối chung hai Signal |
| Tín hiệu ESC/servo | Có điều kiện xác minh mức 3,3V; chưa được công bố là cắm trực tiếp chắc chắn dùng được |
| GPIO4/5/6/7 | Khớp vị trí J1-4/5/6/7 của DevKitC-1 tham chiếu |
| GPIO8/9 | Khớp J1-12/J1-15; không nhầm số GPIO với số thứ tự chân header |
| Nguồn/đất tham chiếu | 3V3 tại J1-1/J1-2; GND J1-22. 5V J1-21 không dùng làm đầu vào bổ sung trong bản này |
| USB native | Dành GPIO19/20 cho USB; không phân bổ chúng cho harness cảm biến/ga/lái |
| AS5600 | I²C ở mức 3,3V; cần đối chiếu cách cấp nguồn của module và điện trở kéo lên |
| MT6701 | Chế độ A/B và PPR phải được kiểm; tên chip không đủ để xác nhận độ phân giải |
| LiDAR/camera | Kết nối qua laptop/USB; không tự gán CAM1…4 thành hướng trước/sau/trái/phải đã đo |
| Sạc B3 | Pin tách khỏi toàn bộ xe; chỉ giắc cân bằng ba chân tới cổng 2S, cổng 3S để trống |
| Thành phần người dùng loại bỏ | Không tự thêm E-stop, phần tử ngắt động lực, cầu chì, ToF hoặc IMU; đã nêu giới hạn không có ngắt động lực độc lập |

Pinmap GPIO4…9 là **lựa chọn của bản thiết kế** cho DevKitC-1 tham chiếu, chưa được áp dụng hoặc kiểm trên bo vật lý. Phải đối chiếu chữ in và phiên bản PCB thực trước khi đi dây. Vị trí trái/phải của hai cổng USB không được dùng thay cho nhãn chức năng trên bo.

## Điểm đã gửi cho nhóm thiết kế

1. Firmware vẫn có `kPinEsc = kPinServo = kPinEstop = -1` và `AP_ENABLE_PWM_OUTPUTS=0`. Kiểm tĩnh khi bật PWM còn đòi hỏi chân E-stop. Hướng dẫn đã ghi không chỉ đổi cờ thành 1 hoặc gán chân giả để vượt điều kiện.
2. Phần mềm laptop yêu cầu phản hồi tốc độ, góc lái và tư thế thật hợp lệ. Một sơ đồ kết nối không thay việc viết driver, hiệu chuẩn và kiểm điều kiện START.
3. AS5600 có cấu hình nguồn ở cấp IC khác với nhãn VCC trên từng breakout. Hình bốn chân chức năng không được xem là thứ tự chân vật lý của mọi module.
4. MT6701 có biến thể mặc định A/B chỉ 1 PPR; cần module/chế độ/PPR thích hợp. Không nâng rail 3V3 của ESP32 để lập trình EEPROM cảm biến.
5. Hub hiện có chưa được xác nhận khả năng cấp nguồn phụ; không vẽ một đường nguồn ghép vào USB như kết nối đã được xác minh.
6. Đã sửa hình B3: cổng 2S có ba tiếp điểm, cổng 3S có bốn tiếp điểm và tỷ lệ hình dạng hợp lý. Nhãn B−/BM/B+ chỉ là các nút điện của pack; chưa thay việc kiểm cực và chiều giắc thực.
7. Dòng khởi động/kẹt motor, dòng tải servo và định mức dây/giắc còn phải xác định. Không coi danh định của riêng ESC là định mức toàn bộ đường nguồn.

## Kiểm tra bản dựng cuối

| Hạng mục | Kết quả |
|---|---|
| Danh mục 14 linh kiện | PASS: có hình nhận dạng và điểm nối; không có bộ ổn áp servo rời. Ký hiệu tùy chọn còn trong thư viện không phải linh kiện của cấu hình này |
| Các net hoạt động | PASS trong thiết kế: 13 net; nguồn pin 2S chỉ tới ESC, BEC tới servo có điều kiện, rail 3V3 và tín hiệu riêng biệt; không có cổng thuộc hai net khác nhau |
| BEC | PASS có điều kiện: `V_SERVO` có đúng hai đầu `ESC.bec_plus` và `SERVO.vplus`; không có đầu ESP32. Nhánh được vẽ nét đứt kèm yêu cầu xác minh 6 V và dòng tải |
| Hai tín hiệu điều khiển | PASS: `ESC_CTRL` và `SERVO_CTRL` độc lập; không có nối tắt Signal ESC với Signal servo |
| Hồi nguồn servo | PASS về đường vẽ: GND servo tới ESC/BEC trực tiếp; nhánh ESP32 lấy cùng tham chiếu, không nằm nối tiếp trên đường hồi tải servo |
| Hai đầu motor | PASS: mỗi đầu chỉ nối đầu ra ESC tương ứng; không ghép vào GND hoặc 3V3 |
| Các mốc dây/cap | PASS: 18 mốc ở tờ 1, 30 mốc ở tờ 2, 9 mốc ở tờ 3 khớp với đầu mút đường vẽ, tổng 57 mốc |
| Điểm nối trong thiết bị | PASS về cách khai báo: netlist ghi riêng liên hệ BAT−/GND qua ESC cần đo xác nhận; đã bỏ liên hệ nội bộ của nguồn servo rời |
| GPIO và giao tiếp | PASS: GPIO4–9 không trùng nhau; các net cảm biến đúng nhãn, USB native giữ riêng |
| Sạc | PASS: ba điểm balance ghép cùng tên; không có ESP/ESC/tải xe trong net sạc, giắc T để rời và cách điện |
| Bố cục | PASS sau sửa: chú thích nhiều dòng đọc được, dây không xuyên thân ESP32, các hộp chú thích không che mất đường nguồn/GND/USB |
| Cảnh báo/điều kiện ngay trên ảnh | PASS: có nhánh servo và tín hiệu chờ xác minh, GPIO đề xuất, firmware chưa đổi và trạng thái thiết kế chưa thử xe |
| Tính nhất quán của tệp xuất | PASS: 4 SVG parse được; 8 hash SVG/PNG và các hash nguồn khớp `export_manifest.json`; không nhúng ảnh ngoài/ảnh người dùng |

Các lỗi của bản nháp đã được sửa trước khi duyệt: renderer nối các `tspan` thành một dòng; route tín hiệu servo đi ngang thân bo; một số chú thích che dây; tiêu đề tờ phản hồi cắt qua hai đường I²C. Trong revision BEC này, chú thích hồi nguồn servo đã được dịch ra ngoài đường GND dọc. Đã xem lại đủ bốn PNG xuất cuối; các giao cắt không có chấm được phân biệt bằng khoảng trắng, nút GND có chấm nối và không có dây che chữ còn được phát hiện.

Kích thước PNG đã kiểm: `00-components.png` 3600×3460, `01-system.png` 4600×3300, `02-signal-feedback.png` 4800×4000, `03-charging.png` 4400×2700.

Phiên bản nguồn được duyệt:

- `build_wiring.py` SHA-256: `f79e83134b04b8545477e0d2bddbaaa2ffb8e11ebc59e36d6e4c2d0190377f72`.
- `components.py` SHA-256: `02cc2fc8a161e3447bd6109816894359379a6fc69079429102acde6d9483f455`.
- `wiring_spec.json` SHA-256: `913e3becdaa7b82e5cfdab1a6195238a56e4fe0e02ec8d4b133d3bb612f25a76`.
- Hash chi tiết của hình và renderer: xem `export_manifest.json`.

## Điều kiện phần cứng còn mở

Servo gốc chưa được xác nhận hỗ trợ 6 V; điện áp BEC thực, dòng tải servo và khả năng cấp dòng của ESC thực nhận vẫn phải được kiểm trước khi nối nhánh nguồn này. Thứ tự dây thực, ngưỡng tín hiệu ESC/servo, cấu hình nguồn/pull-up của các module, MODE/PPR encoder, dòng motor và định mức dây/giắc, cách cấp nguồn hub và toàn bộ firmware/hiệu chuẩn vẫn cần xác minh trên thiết bị. Các chân/nút chức năng minh họa không thay pinout của hàng thực nhận. Không có ngắt động lực độc lập hoặc cầu chì bổ sung trong lựa chọn này.

## Nguồn đối chiếu

- [Espressif — DevKitC-1 v1.1](https://documentation.espressif.com/api/resource/path/docs/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html) và [bảng header DevKitC-1 trong ESP-IDF](https://docs.espressif.com/projects/esp-idf/en/v4.4.3/esp32s3/hw-reference/esp32s3/user-guide-devkitc-1.html).
- [Hobbywing — manual QuicRun 1625/1060/860](https://www.hobbywing.com/en/uploads/file/20240315/e8525a6a27f4e1dcbe3af554c06deac0.pdf).
- [imaxRC — manual B3 Pro, bản lưu tại RC Factory](https://www.rc-factory.cz/assets/docs/da21c8a03bc75ae73c4b5362c3acef7c/1321-1/b3-pro-manual.pdf).
- [ams OSRAM — AS5600 evaluation-board operation manual](https://look.ams-osram.com/m/4f8342513a447495/original/AS5600_UG000254_2-00.pdf).
- [MagnTek — MT6701 Rev1.8](https://www.magntek.com.cn/upload/pdf/202407/MT6701_Rev.1.8.pdf), các phần pin configuration, part number, output mode và EEPROM.

Đây là kiểm tra thiết kế bằng tài liệu và hình, không phải nghiệm thu điện, phép đo dòng/điện áp, thử servo/ESC hoặc chạy xe thật.
