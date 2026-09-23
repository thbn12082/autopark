# Sơ đồ USB — bốn camera qua hub UGREEN (23/09/2026)

Đo trên máy bàn i9-14900 (chưa phải laptop của xe) bằng `python -m autopark.video.camera_bench list --out ...`
(Get-PnpDevice cho camera và hub, DirectShow DevicePath để ghép index OpenCV với InstanceId). Bản json:
[evidence/camera/usb_topology_20260923.json](evidence/camera/usb_topology_20260923.json) — khóa `pnp` (camera),
`hubs`, `dshow_index_to_port`.

## Hub

Một hub vật lý UGREEN 4 cổng, chip Genesys Logic; Windows thấy thành **hai** thiết bị vì hub USB 3 luôn có hai nhánh:

| Thiết bị Windows (`hubs`) | VID:PID | Cắm vào (LocationInfo) | Ai đi qua |
|---|---|---|---|
| "Generic SuperSpeed USB Hub", bus báo "USB3.1 Hub" | 05E3:0626 | cổng gốc 24 của root hub 1 | thiết bị USB 3 (hiện không có) |
| "Generic USB Hub", bus báo "USB2.1 Hub" | 05E3:0610 | cổng gốc 5 của root hub 1 | **cả bốn camera** |

Camera UVC này là thiết bị USB 2.0, nên **bốn camera chia nhau một đường USB 2.0 (480 Mbit/s danh định)** về máy, bất
kể hub có nhánh USB 3. UVC dùng endpoint đẳng thời, giới hạn thực tế là băng thông mỗi camera đặt trước theo
alt-setting của mode — **chưa đo** (xem [GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) mục 4.2). Hub **có cổng nguồn ngoài**; chạy bus-powered tới ≈ 11:45 ngày 23/09, sau đó cắm adapter (điện áp/dòng chưa đo). Với bus-powered, bốn camera
từ 720p trở lên rớt khung ở cổng 4; với nguồn ngoài, 0 khung cũ trong 7 phiên A/B — xem [GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) mục 4.5.

## Camera

Bốn chiếc cùng loại: "HD Camera", VID 1BCF (Sunplus Innovation) PID 0B09, thiết bị composite, giao diện video MI_00.
**Không có số serial**: InstanceId của Windows sinh từ *cổng hub* (`7&56B40FB&0&0000` …), nên danh tính của một camera
là cổng nó cắm vào.

| Cổng hub | InstanceId (MI_00) | Index DirectShow / OpenCV (bản `list` 10:36 ngày 23/09, `usb_topology.json` created_utc 03:36:17Z) |
|---:|---|---:|
| 1 | `USB\VID_1BCF&PID_0B09&MI_00\7&56B40FB&0&0000` | 0 |
| 2 | `USB\VID_1BCF&PID_0B09&MI_00\7&1824F1A0&0&0000` | 3 |
| 3 | `USB\VID_1BCF&PID_0B09&MI_00\7&2ADEA245&0&0000` | 1 |
| 4 | `USB\VID_1BCF&PID_0B09&MI_00\7&1FD88E3&0&0000` | 2 |

**Index OpenCV không theo thứ tự cổng** (0→1, 1→3, 2→4, 3→2). Bản `list` đầu trong ngày (10:06, vòng 1) đã bị ghi đè cùng đường dẫn nên không còn file. Bản `list` thứ hai `usb_topology_2.json` (created_utc 04:06:08Z, sau toàn bộ 23 phiên đo và 3 lần ghi video, tức sau hàng chục lần mở/đóng VideoCapture) cho **cùng** bảng index ↔ cổng ↔ InstanceId với bản 10:36 — tính ổn định của index qua mở/đóng trong cùng phiên máy đã có hai file đối chiếu. **Rút/cắm lại cùng cổng đã kiểm một lần** (camera cổng 3, ≈ 12:00 ngày 23/09; `usb_topology_replug.json` cho cùng bảng index ↔ cổng ↔ InstanceId). **Chưa thử đổi cổng, chưa thử khởi động lại máy** (giai đoạn 2, bước 3). Theo cơ chế Windows cấp InstanceId theo vị trí cho thiết bị không serial, đổi cổng sẽ đổi InstanceId — cũng chưa thử. Vì vậy mã vận
hành phải chọn camera theo *InstanceId / cổng* (hàm `join_index_to_port` trong `camera_bench.py` cho bảng này lúc
chạy), không hard-code index; việc gán hướng trước/sau/trái/phải sẽ ghi theo cổng khi có gá.

## Điều chưa làm

- Đổi cổng camera và khởi động lại máy để kiểm InstanceId/index (rút/cắm cùng cổng đã kiểm).
- Thử trên laptop của xe; thử cáp kéo dài.
- Đo điện áp/dòng adapter của hub và dòng tiêu thụ camera (không có đồng hồ đo USB); phép thử đảo nguồn.
- Đo băng thông đẳng thời mỗi camera đặt trước (USB Device Tree Viewer / USBPcap).
