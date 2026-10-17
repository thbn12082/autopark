# AutoPark — bắt đầu từ đây

AutoPark là dự án làm **xe mô hình tự đỗ vào chỗ người dùng chọn**. Ví dụ: trên một sa bàn có vài xe đang đỗ, bạn chọn ô trống, phần mềm tìm đường tiến/lùi rồi điều khiển xe đi vào ô đó.

Bạn có thể tham gia phần mềm ngay bằng máy tính Windows. Bản mô phỏng chạy được mà chưa cần xe, LiDAR, camera hay GPU NVIDIA.

## Nếu đây là lần đầu bạn mở dự án

Làm theo ba bước này:

1. **Cài và chạy một lượt đỗ:** mở [Hướng dẫn chạy](autopark/README.md), làm mục 1–3. Bạn sẽ thấy xe di chuyển trên sa bàn.
2. **Hiểu đoạn mã vừa chạy:** đọc mục 1–3 của [Sơ đồ hệ thống](autopark/docs/SO_DO_HE_THONG.md). Tài liệu chỉ ra tệp nào xử lý giao diện, tìm đường và điều khiển xe.
3. **Làm thay đổi đầu tiên:** theo [Hướng dẫn tham gia](CONTRIBUTING.md). Có bài tập sửa một sa bàn, cách kiểm kết quả và quy trình gửi thay đổi.

Gặp từ lạ như *tư thế xe*, *BEV*, *VehicleIO* hay *checkpoint*, tra [Thuật ngữ](autopark/docs/THUAT_NGU.md). Bạn có thể đọc tài liệu từng mảng khi bắt đầu làm mảng đó.

## Hiện tại làm được gì?

Hồ sơ thiết bị và kết quả thử gần nhất được ghi tới **06/10/2026**. Bộ hướng dẫn này được biên tập ngày **17/10/2026**, dựa trên mã tại `8be69fb`.

| Mảng | Bạn có thể làm gì? | Mức đã kiểm chứng |
|---|---|---|
| Mô phỏng đỗ xe | Mở sa bàn, chọn chỗ đỗ, tìm đường, xem trước, cho xe chạy và thử dừng | Đã chạy trọn phiên trên máy tính |
| LiDAR và bốn camera USB | Đọc, xem, ghi và phát lại dữ liệu cảm biến | Đã thử thiết bị thật trên bàn; cần có thiết bị hoặc bản ghi để làm lại |
| AI camera | Phân ảnh thành vùng trống và vật cản | Đã chạy trên ảnh và bàn thử; chưa hiệu chuẩn camera để dùng trong phiên đỗ thật |
| Firmware ESP32-S3 | Kiểm logic điều khiển trên máy tính; chạy firmware trong QEMU | Đã kiểm bằng mô phỏng/giả lập; chưa nạp vào bo thật |
| Xe tự đỗ ngoài đời | Mục tiêu của dự án | Chưa có lượt chạy trên xe thật; V1 chưa đạt điều kiện nghiệm thu |

Xe MN300, bo ESP32-S3 và một số linh kiện còn thiếu theo hồ sơ trên. Xem [Tổng quan và công việc tiếp theo](TONG_HOP_DU_AN.md) để biết phần nào cần người, dữ liệu hoặc thiết bị.

## Một lần đỗ diễn ra như thế nào?

```mermaid
flowchart LR
    A["Chọn ô đỗ"] --> B["Xác định vị trí xe và vật cản"]
    B --> C["Tìm đường tiến/lùi"]
    C --> D["Kiểm tra và xem trước"]
    D --> E["Điều chỉnh tốc độ, góc lái"]
    E --> F["Đến đích hoặc dừng khi có lỗi"]
```

Trong mô phỏng, chương trình biết vị trí xe từ xe ảo. Khi dùng xe thật, hệ thống phải đo vị trí đó bằng cảm biến. Đây là một phần việc còn đang phát triển.

Laptop xử lý ảnh, dữ liệu LiDAR và tìm đường. Bo ESP32-S3 dự kiến nhận lệnh từ laptop để điều khiển động cơ và bộ lái. **AI chỉ giúp nhận biết môi trường**; phần tìm đường và bám đường nằm ở các mô-đun khác.

## Mở đúng thư mục

Tên `autopark` xuất hiện ở nhiều cấp thư mục. Nhìn các tệp dưới đây để biết bạn đang ở đâu:

```text
<gốc kho mã>/                   ← có .git và README bạn đang đọc
├── README.md
├── CONTRIBUTING.md             ← cách tham gia và làm thay đổi đầu tiên
├── TONG_HOP_DU_AN.md            ← tiến độ, phần còn thiếu, việc tiếp theo
├── KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md
├── HUAN_LUYEN.md                ← nhánh AI
└── autopark/                   ← chạy lệnh Python tại đây
    ├── pyproject.toml          ← danh sách thư viện cần cài
    ├── run_app.py              ← mở ứng dụng
    ├── autopark/               ← mã Python
    ├── tests/                  ← kiểm thử tự động
    ├── scenarios/              ← sa bàn mẫu
    ├── configs/                ← cấu hình xe, cảm biến và AI
    ├── firmware/               ← mã cho bo ESP32-S3
    └── docs/                   ← tài liệu chuyên đề và bằng chứng
```

Sau khi cài xong theo hướng dẫn, mở PowerShell ở thư mục có `pyproject.toml` và chạy:

```powershell
.\.venv\Scripts\python.exe run_app.py scenarios\bai_do_xe.json
```

Giữ cấu hình mô phỏng, bấm **Tìm đường đỗ**, rồi **Bắt đầu đỗ**. Nếu dùng **Xem trước** để quan sát lộ trình, hãy bấm **Kết thúc xem trước** trước khi bắt đầu đỗ. Cách thao tác và xử lý lỗi ở mục 3 của [Hướng dẫn chạy](autopark/README.md).

## Chọn phần bạn muốn làm

| Bạn muốn làm gì? | Đọc tiếp | Vị trí mã chính |
|---|---|---|
| Giao diện, tương tác với sa bàn | [Bài tập đầu tiên](CONTRIBUTING.md) | `autopark/autopark/ui/` |
| Tìm đường và điều khiển xe mô phỏng | [Sơ đồ hệ thống, mục 2–3](autopark/docs/SO_DO_HE_THONG.md) | `planning/`, `control/`, `simulation/` trong gói Python |
| LiDAR, bản đồ, định vị | [Nhóm tài liệu LiDAR](autopark/docs/README.md#lidar-va-vi-tri-xe) | `autopark/autopark/lidar/` |
| Camera và AI | [Huấn luyện AI](HUAN_LUYEN.md), [nhóm tài liệu camera](autopark/docs/README.md#camera-va-ai) | `video/`, `perception/`, `fusion/` trong gói Python |
| Giao tiếp với bo và firmware | [Sơ đồ hệ thống, mục 6](autopark/docs/SO_DO_HE_THONG.md) | `autopark/autopark/transport/`, `autopark/firmware/` |
| Kiểm thử và đánh giá kết quả | [Hướng dẫn tham gia](CONTRIBUTING.md), [nghiệm thu](autopark/docs/KICH_BAN_NGHIEM_THU.md) | `autopark/tests/`, `autopark/autopark/evaluation/` |

## Những điều cần biết trước khi làm tiếp

- **Thông số xe mẫu là giả định.** Chúng giúp kiểm phần mềm; cần đo xe thật trước khi đưa lên xe.
- **Dữ liệu lớn nằm ngoài Git.** Dataset, trọng số AI, môi trường Python và phần lớn bản ghi trong `runs/` cần lấy riêng. Clone mã là đủ để bắt đầu mô phỏng.
- **Cấu hình thiết bị phụ thuộc máy.** `autopark/configs/thiet_bi.json` đang ghi COM3 và đường dẫn QEMU/PlatformIO ở `D:/xetulai/_platformio/...`. Khi làm phần cứng hoặc bo ảo, chỉnh theo máy của bạn; chạy mô phỏng cơ bản chưa cần các đường dẫn này.
- **Kết quả phải ghi rõ cách thử.** Test phần mềm đạt, giả lập chạy được và xe thật đỗ được là ba kết quả khác nhau. Khi báo tiến độ, ghi lệnh chạy và loại dữ liệu/thiết bị đã dùng.

Danh sách đầy đủ nằm trong [Mục lục tài liệu](autopark/docs/README.md). [Kế hoạch triển khai](KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) giải thích các giai đoạn và điều kiện hoàn thành V1; [báo cáo giai đoạn 0](BAO_CAO_GIAI_DOAN_0.md) lưu kết quả mô phỏng ban đầu.

## Dữ liệu và ghi công

Nhánh AI sử dụng **[Valeo WoodScape Dataset](https://github.com/valeoai/WoodScape)**. Phạm vi sử dụng, điều khoản và các quyết định của dự án được lưu trong [Hồ sơ giấy phép dữ liệu](autopark/docs/GIAY_PHEP_DU_LIEU.md). Kiểm tra hồ sơ này trước khi dùng thêm dữ liệu hoặc chia sẻ mô hình.
