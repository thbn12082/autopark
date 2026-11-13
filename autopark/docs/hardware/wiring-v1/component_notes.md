# Tham chiếu hình dạng và hợp đồng thư viện 2D

`components.py` tự vẽ SVG bằng hình học vector; không nhúng hoặc phát hành lại ảnh bên thứ ba. Hình dùng để nhận dạng linh kiện và ghép đường điện trên sơ đồ, không phải bản vẽ cơ khí theo tỉ lệ.

## API cho người ghép hình

```python
draw_component(kind, x, y, w=None, h=None, *, label=None, subtitle=None,
               port_labels=None, show_ports=True) -> str
component_ports(kind, x=0, y=0, w=None, h=None) -> dict[str, tuple[float, float]]
component_catalog_svg() -> str
```

- `NATIVE_SIZES[kind]` chứa kích thước thiết kế SVG.
- `PORT_SPECS[kind][port]` chứa `x`, `y`, `side`, `label`, `color`, `provisional` trong tọa độ gốc.
- `component_ports()` trả tọa độ tuyệt đối sau phép tịnh tiến/co giãn; dùng các giá trị này để nối dây.
- Vẽ dây ra khỏi các pad ESP32 sau khi vẽ thân bo để thấy đoạn dây ở sát pad.
- Mỗi linh kiện có các mốc chức năng ở mép hoặc ở đầu dây ngắn. Riêng các chân ESP32 được đặt tại pad J1 của hình tham chiếu.
- `port_labels` thay chữ chú thích, không đổi tên khóa hoặc vị trí. `subtitle` tùy chọn nằm dưới cùng hộp hình; người ghép cần kiểm xem có đụng nhãn đầu cắm đáy hay không.
- Có thể dùng nhiều lần một `kind`: SVG không sinh ID trùng nhau, không cần stylesheet/gradient từ ngoài.

## Phân biệt dữ liệu đã thấy và dữ liệu tham chiếu

| Linh kiện | Cơ sở hình dạng | Điều chưa được hình xác nhận |
|---|---|---|
| Motor 280–60T | Ảnh xe thật, file kết thúc `e21cdef01d0662a6967b24660e555dde.jpg` | Giắc trắng hai chân phía motor chưa xác định tên/chuẩn chính xác; A/B là tên hai đường motor, không phải bảo đảm chiều tiến |
| Cụm lái ba dây | Ảnh toàn xe, file kết thúc `8b01c57c48141e46baf637dc70e85de5.jpg` | Hình servo minh họa vị trí vỏ/horn/cáp; điện áp, model, thứ tự chân và tầm xung thực chưa được xác minh |
| XL1986RT | Ảnh trực tiếp mặt linh kiện của bo gốc | Chỉ để nhận dạng bo được thay chức năng, không nối nó song song với ESC mới |
| ESP32-S3 DevKitC-1 | Bố cục bo và bảng J1/J3 trong tài liệu Espressif v1.0 | Mã N16R8 được người dùng xác nhận qua câu trả lời; chưa có ảnh rõ revision và silk của bo thực. GPIO sử dụng là đề xuất thiết kế, firmware hiện chưa cấu hình các chân này |
| ESC 1060 Brushed | Hình dạng ESC 1060: tản nhiệt có cánh, tụ, công tắc, dây RC và hai đầu motor | SKU/hàng shop vẫn cần đối chiếu; không suy ra mức BEC hoặc mức logic chỉ từ hình dáng. Trong bản sửa BEC, nguồn BEC chỉ tới servo sau khi xác minh servo hỗ trợ 6 V và BEC đủ dòng; không tới ESP32 |
| Pin LiPo 2S | Pack chữ nhật với dây nguồn T và nhánh cân bằng ba dây | Chưa mua/chưa có ảnh pin thực; kích thước chỉ minh họa, không khẳng định vừa khay xe |
| B3 Pro | Vỏ hộp, ba LED, ổ AC và cổng 2S/3S theo hướng dẫn B3 Pro | Vị trí cổng có thể khác theo phiên bản; luôn đọc nhãn 2S trên sạc. B−/BM/B+ trên hình là thứ tự điện chức năng, không xác nhận hướng nhìn vào giắc của hàng mua |
| AS5600 / MT6701 | PCB nhỏ, IC cảm biến và nam châm đồng trục minh họa | PCB module thương mại chưa chốt. Các pad nguồn/tín hiệu là mốc chức năng; không phải pinout vật lý của một module cụ thể. VCC 3V3 chỉ áp dụng nếu module mua cho phép. MT6701 cần đúng cấu hình/chân xuất ABZ |
| LiDAR C1 | Đầu quét tròn trên đế vuông có góc bo tròn | Dùng nguyên cáp C1 và adapter USB tương ứng; hình không diễn giải từng chân riêng của cáp |
| Hub / camera / máy tính | Hình tham chiếu chung, giữ phong cách vector cũ | Laptop chỉ nối Wi-Fi với Pi; bốn camera qua hub tới Pi. Hub cũ chưa xác minh DC-in; chọn hub có nguồn phù hợp và kiểm không cấp ngược VBUS về Pi |
| Raspberry Pi | PCB xanh, SoC, hàng chân và cổng USB để nhận dạng loại máy tính đơn bo | Model chưa chọn. Mốc USB/nguồn là chức năng, không khẳng định vị trí cổng của Pi cụ thể; cấp nguồn qua cổng đúng model, không suy ra cấp qua header GPIO |
| DC–DC Pi / DC–DC hub | Giữ phong cách module vector của thư viện, hai khối nguồn riêng | Chưa chọn hay đo phần cứng. Đầu vào chịu toàn dải 2S; Pi cần 5 V ổn áp đúng yêu cầu model/tải, hub cần điện áp/cực/dòng đúng DC-in được hãng hỗ trợ; hai đầu ra dương không ghép song song, không dùng BEC 6 V |

## Chân ESP32 tham chiếu

Mặt trước bo, anten phía trên và USB phía dưới; dãy J1 nằm bên trái. Bảng dưới dùng số hàng J1 từ tài liệu hãng, không phải số GPIO thay thế cho số chân:

| Chức năng đề xuất | GPIO/tên chân | Hàng J1 |
|---|---|---:|
| Nguồn logic cảm biến | 3V3 | 1 |
| ESC_CTRL | GPIO4 | 4 |
| SERVO_CTRL | GPIO5 | 5 |
| AS_SDA | GPIO6 | 6 |
| AS_SCL | GPIO7 | 7 |
| ENC_A | GPIO8 | 12 |
| ENC_B | GPIO9 | 15 |
| GND chung | GND | 22 |

Hai đầu USB phải nhận dạng theo silk/chức năng trên bo thật. Cổng native USB đi tới USB của ESP32-S3, còn USB–UART đi qua chip cầu USB/UART. Không hoán đổi tên chỉ dựa vào kiểu đầu micro-USB/USB-C hoặc vị trí trên một bo sao chép.

Nguồn tham chiếu sơ đồ chân: [Espressif ESP32-S3-DevKitC-1 v1.0](https://documentation.espressif.com/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.0.html). Tài liệu ghi các GPIO35–37 của biến thể có bộ nhớ Octal không dùng làm I/O ngoài; thiết kế này không sử dụng chúng.

Các nguồn hình dạng/chức năng khác: [Hobbywing QuicRun 1060](https://www.hobbywingdirect.com/products/quicrun-10-brushed-esc), [hướng dẫn B3 Pro](https://www.rc-factory.cz/assets/docs/da21c8a03bc75ae73c4b5362c3acef7c/1321-1/b3-pro-manual.pdf), [SLAMTEC RPLIDAR C1](https://www.slamtec.com/en/c1/spec), [MT6701 của MagnTek](https://www.magntek.com.cn/136/108). Ảnh xe người dùng chỉ được đọc làm tham chiếu; thư viện không chép ảnh đó vào SVG.

Không vẽ thêm nút dừng khẩn, phần tử ngắt động lực, cầu chì, IMU hay ToF: người dùng đã yêu cầu bỏ/hoãn các mục đó. Hình thể hiện lựa chọn của người dùng, không phải xác nhận hệ thống có đường ngắt động lực độc lập.

Bản catalogue ngày 13/11/2026 có **17 loại hình linh kiện** (một hình camera dùng bốn lần trong sơ đồ). Danh sách `CATALOG_KINDS` và ngày `DESIGN_DATE` trong mã là nguồn chung cho catalogue, footer, spec và manifest; số hàng/kích thước catalogue được tính tự động. Bo XL1986RT chỉ để nhận dạng phần cất riêng, không thuộc mạng hoạt động. Nguồn servo lấy từ BEC có điều kiện tương thích 6 V; hai bộ nguồn mới dành riêng Pi và hub, không phải nguồn servo rời.

Tham chiếu yêu cầu nguồn: [Raspberry Pi — Power supply](https://www.raspberrypi.com/documentation/computers/getting-started.html#power-supply). Model Pi, cáp/cổng nguồn, tải C1/ESP qua USB, hub và bốn camera còn phải chọn/đo; hình không xác nhận một định mức nguồn chung cho mọi Pi. Hình không chứa ảnh chụp gốc và không dùng ImageGen.
