# Sơ đồ USB — bốn camera qua hub UGREEN (23/09/2026)

Tài liệu này ghi sơ đồ USB của bốn camera và hub UGREEN: camera cắm vào đâu, Windows nhận chúng thế nào, và vì sao danh tính của một camera là cổng hub chứ không phải index OpenCV. Số liệu đo ngày 23/09/2026 trên máy bàn i9-14900, chưa phải laptop RTX 3050 Ti mang đi nộp đồ án. Số đo FPS, khung cũ và khung bị cắt ở [GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md).

Sơ đồ lấy bằng lệnh `python -m autopark.video.camera_bench list --out ...`. Lệnh dùng Get-PnpDevice cho camera và hub, và DirectShow DevicePath để ghép index OpenCV với InstanceId. Bản json: [evidence/camera/usb_topology_20260923.json](evidence/camera/usb_topology_20260923.json), với các khóa `pnp` (camera), `hubs`, `dshow_index_to_port`.

## Tóm tắt

- Bốn camera chia nhau một đường USB 2.0 qua hub. Hub chạy bus-powered trong mọi phiên ngày 23/09; phép thử nguồn ngoài chưa làm.
- Tính cả khung MJPEG bị cắt cụt, bốn camera qua hub này chỉ dùng được ở **640×480**.
- Camera không có serial, nên danh tính là cổng hub. Index OpenCV đổi sau khởi động lại máy, nên mã vận hành chọn camera theo InstanceId/cổng.
- Các bảng dưới là của máy bàn dùng tới 25/09/2026. Máy bàn từ 29/09/2026 có sơ đồ cổng gốc khác (mục Hub).
- Chưa thử: đổi cổng, nguồn ngoài cho hub, đo băng thông, laptop nộp đồ án.

## Hub

Bảng Hub và bảng Camera dưới đây là sơ đồ của máy bàn dùng tới 25/09/2026. Trên máy bàn từ 29/09/2026 thì khác:

- hub 05E3:0610 cắm cổng gốc 8 (LocationPath `PCIROOT(0)#PCI(1400)#USBROOT(0)#USB(8)`);
- nhánh USB 3 05E3:0626 ở cổng gốc 18;
- bốn camera 1BCF:0B09 ở Port_#0001–0004 của hub, InstanceId khác bảng Camera.

Nguồn: [usb_topology.json](evidence/chuyen_may_20260929/may_moi/usb_topology.json), [biên bản chuyển máy](CHUYEN_MAY_BAN.md).

Đây là một hub vật lý UGREEN 4 cổng, chip Genesys Logic. Windows thấy nó thành **hai** thiết bị, vì hub USB 3 luôn có hai nhánh:

| Thiết bị Windows (`hubs`) | VID:PID | Cắm vào (LocationInfo) | Ai đi qua |
|---|---|---|---|
| "Generic SuperSpeed USB Hub", bus báo "USB3.1 Hub" | 05E3:0626 | cổng gốc 24 của root hub 1 | thiết bị USB 3 (hiện không có) |
| "Generic USB Hub", bus báo "USB2.1 Hub" | 05E3:0610 | cổng gốc 5 của root hub 1 | **cả bốn camera** |

Camera UVC này là thiết bị USB 2.0. Vì vậy **bốn camera chia nhau một đường USB 2.0 (480 Mbit/s danh định)** về máy, dù hub có nhánh USB 3. UVC dùng endpoint đẳng thời, nên giới hạn thực tế là băng thông mỗi camera đặt trước theo alt-setting của mode. Băng thông này **chưa đo** ([GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) mục 4.2).

Theo người dùng, hub có cổng nguồn ngoài, nhưng hub **chạy bus-powered trong mọi phiên ngày 23/09**; phép thử nguồn ngoài chưa làm. Bốn camera từ 720p trở lên từng rớt khung ở cổng 4. Sau khi rút/cắm lại các camera thì 7 phiên liền có 0 khung cũ, nguyên nhân chưa rõ ([GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) mục 4.5).

### Khung MJPEG bị cắt khi chạy chung

"0 khung cũ" chỉ có nghĩa là driver không trả lại khung trước, không có nghĩa là ảnh nguyên vẹn. Các phiên sau rút/cắm chưa kiểm khung MJPEG bị cắt cụt. Chiều 23/09 đã đo lại, lần này có đếm khung bị cắt (phần đáy ảnh do bộ giải mã tô). Kết quả:

- **Bốn** camera chạy chung qua hub: phần lớn khung của hai đến ba camera bị cắt (720p r04, r08, r11 và 1080p r09).
- **Ba** camera ở 720p: chỉ **một** camera bị cắt phần lớn khung (r03: cổng 1 97 %, cổng 3 9 %; r05: cổng 4 67 %, cổng 3 1 %).
- Ba camera ở 1080p: chưa có phiên nào đếm khung bị cắt.
- Chạy một mình: không bị cắt.
- Ở 640×480: phần lớn thời gian ảnh nguyên vẹn, nhưng camera cổng 1 có những đợt 26–36 % khung hỏng, chưa rõ nguyên nhân.

Số liệu theo [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 2.3 (đối chiếu lại tối 24/09/2026).

Vì vậy bốn camera qua hub này chỉ dùng được ở **640×480**, là mặc định của `rig.bench` và giao diện từ 23/09, và vẫn phải bật bộ dò `truncated_rows`/`torn_bands`. Kết quả này hợp với giả thuyết thiếu băng thông USB 2.0 dùng chung nói ở trên, nhưng **chưa chứng minh**.

Mức cắt còn phụ thuộc cảnh. Ngày 24/09, khi camera nhìn vào chỗ tối, 720p × 4 không có khung nào bị cắt; đó **không** phải bằng chứng 720p đã dùng được. Xem [GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) mục 4.6 và [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 2 và 10.

## Camera

Bốn chiếc cùng loại: "HD Camera", VID 1BCF (Sunplus Innovation) PID 0B09, thiết bị composite, giao diện video MI_00. Camera **không có số serial**. InstanceId của Windows vì thế sinh từ *cổng hub* (`7&56B40FB&0&0000` …), nên danh tính của một camera là cổng nó cắm vào.

Bảng dưới lấy từ bản `list` lúc 10:36 ngày 23/09 (`usb_topology.json`, created_utc 03:36:17Z).

| Cổng hub | InstanceId (MI_00) | Index DirectShow / OpenCV |
|---:|---|---:|
| 1 | `USB\VID_1BCF&PID_0B09&MI_00\7&56B40FB&0&0000` | 0 |
| 2 | `USB\VID_1BCF&PID_0B09&MI_00\7&1824F1A0&0&0000` | 3 |
| 3 | `USB\VID_1BCF&PID_0B09&MI_00\7&2ADEA245&0&0000` | 1 |
| 4 | `USB\VID_1BCF&PID_0B09&MI_00\7&1FD88E3&0&0000` | 2 |

**Index OpenCV không theo thứ tự cổng** (0→1, 1→3, 2→4, 3→2). Độ ổn định của bảng index ↔ cổng ↔ InstanceId đã được kiểm như sau:

- **Mở/đóng nhiều lần trong cùng phiên máy.** Bản `list` đầu trong ngày (10:06, vòng 1) đã bị ghi đè cùng đường dẫn nên không còn tệp. Bản `list` thứ hai `usb_topology_2.json` (created_utc 04:06:08Z) chụp sau toàn bộ 23 phiên đo và 3 lần ghi video, tức sau hàng chục lần mở/đóng VideoCapture. Bản này cho **cùng** bảng với bản 10:36. Như vậy tính ổn định của index qua mở/đóng trong cùng phiên máy có hai tệp đối chiếu.
- **Rút/cắm lại cùng cổng: đã kiểm một lần.** Khoảng 11:55 người dùng rút/cắm các camera, sau đó camera cổng 3 treo; khoảng 12:01–12:04 họ rút/cắm lại camera cổng 3. Hai tệp `usb_topology_replug2.json` (created_utc 05:04:59Z) và `usb_topology_replug1.json` (05:05:17Z) cho cùng bảng với bản 10:36. Hai tệp chụp cách nhau 18 s, đều **sau** lần rút/cắm thứ hai; tên replug1/2 không theo thứ tự thời gian. Vì vậy chúng chỉ là **một** lần kiểm của trạng thái cuối (đính chính 24/09/2026).
- Bản `list` chụp lúc camera cổng 3 còn treo (≈ 11:58) đã bị ghi đè cùng đường dẫn. Bảng lúc đó chỉ còn trong nhật ký console ngoài repo (cũng cùng bảng), không tính là bằng chứng lưu trữ. Giờ rút/cắm lấy theo nhật ký phiên làm việc ([GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) mục 4.5).
- **Sau khởi động lại máy** lúc 12:35 ngày 23/09 (bản `list` lúc 13:07, `usb_topology_20260923_after_reboot.json`): InstanceId của từng cổng **giữ nguyên**, nhưng **index OpenCV đã đổi** thành 0→1, 1→3, **2→2, 3→4** (trước là 2→4, 3→2). Đây là bằng chứng trực tiếp rằng index không dùng được làm danh tính.
- **Đổi cổng: chưa thử** (giai đoạn 2, bước 3). Theo cơ chế Windows cấp InstanceId theo vị trí cho thiết bị không serial, đổi cổng sẽ đổi InstanceId; điều này cũng chưa thử.

Vì vậy mã vận hành phải chọn camera theo *InstanceId / cổng*, không hard-code index. Hàm `join_index_to_port` trong `camera_bench.py` dựng bảng này lúc chạy. Việc gán hướng trước/sau/trái/phải sẽ ghi theo cổng khi có gá.

## Điều chưa làm

- **Ưu tiên đầu (thêm 24/09/2026):** tách camera ra nhiều cổng gốc, tức hai camera qua hub, hai camera cắm thẳng vào cổng gốc khác của máy. Chạy lại bốn camera 720p và đọc cột khung bị cắt, với cảnh sáng, nhiều chi tiết, vì cảnh tối cho 0 khung bị cắt (xem trên). Đổi chỗ camera cổng 1 với cổng 2 để tách lỗi do "camera" hay do "cổng hub" ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 9, việc 1).
- Đổi cổng camera để kiểm InstanceId. Rút/cắm cùng cổng và khởi động lại máy đã kiểm trên máy bàn dùng tới 25/09/2026.
- Khởi động lại máy bàn từ 29/09/2026 rồi kiểm danh tính camera theo cổng hub ([biên bản chuyển máy](CHUYEN_MAY_BAN.md) mục 2).
- Thử trên laptop RTX 3050 Ti (máy nộp đồ án); thử cáp kéo dài.
- Phép thử nguồn ngoài cho hub, đọc thêm cột khung bị cắt; đo dòng tiêu thụ camera (không có đồng hồ đo USB).
- Đo băng thông đẳng thời mỗi camera đặt trước (USB Device Tree Viewer / USBPcap).
