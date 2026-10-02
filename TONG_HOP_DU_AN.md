# Tổng quan và tiến độ AutoPark

Tài liệu này giải thích dự án đang ở đâu và cần làm gì tiếp theo. [Cách cài/chạy](autopark/README.md), [mục lục kỹ thuật](autopark/docs/README.md) và [sơ đồ hệ thống](autopark/docs/SO_DO_HE_THONG.md) nằm riêng để dễ tra.

Biên tập 30/09/2026 theo mã tại `ff4a018` (mã giống `ebbec83`); cây làm việc lúc viết có thêm sửa chưa commit: sửa chữ (docstring, chú thích trong mã, một tooltip trong `ui/main_window.py`, mô tả gói trong `pyproject.toml`; không đổi hành vi) và cách đếm khung của `python -m autopark.transport.qemu_board kiem`. Ngày biên tập không phải ngày đo: mô phỏng giai đoạn 0 (20/09/2026) chạy trên laptop; số cảm biến, AI và bàn thử tới 25/09/2026 đo trên máy bàn trước; số từ 29/09/2026 đo trên máy bàn hiện tại ([biên bản chuyển máy](autopark/docs/CHUYEN_MAY_BAN.md)). Bản trước đợt này: [`ff4a018`](https://github.com/thbn12082/autopark/blob/ff4a018/TONG_HOP_DU_AN.md); bản trước đợt 26/09/2026, giữ nhật ký và số liệu chi tiết tới 25/09: [`9d68257`](https://github.com/thbn12082/autopark/blob/9d68257/TONG_HOP_DU_AN.md).

Cập nhật 02/10/2026 theo mã của đợt công cụ nghiệm thu (commit `d3e1555`): mục 3 (dòng GĐ 10), 4.1, 4.5, 4.6, 4.9, 4.10, 4.15, 5.1, 5.4 và 6 (dòng Sơ đồ hệ thống). Các công cụ nghiệm thu mới chỉ được kiểm bằng test (bo mô phỏng, cổng serial giả, camera giả, giao diện offscreen, bản ghi phát lại); số test toàn bộ của đợt này ghi sau lượt chạy trên commit.

Nghiên cứu nhận thức sử dụng **[Valeo WoodScape Dataset](https://github.com/valeoai/WoodScape)**. [Phạm vi sử dụng](autopark/docs/GIAY_PHEP_DU_LIEU.md).

## 1. Mục tiêu V1, phạm vi và mức bằng chứng

V1 cho phép chọn vị trí/hướng đỗ, tìm đường tiến/lùi phù hợp cơ cấu lái, bám đường có phản hồi, dừng và đánh giá lại khi gặp vật cản hoặc mất dữ liệu.

V1 không bắt buộc tự tìm ô đỗ, nhận diện vạch, tự lái đến bãi từ nơi khác, điều khiển từ ảnh tới lệnh bằng mạng neural, hoặc dựng cảnh 3D.

| Mức kết quả | Ý nghĩa | Đã có (30/09/2026) |
|---|---|---|
| Mô phỏng/nguồn giả | Kiểm logic và thuật toán bằng dữ liệu tạo ra | Đỗ xe, lỗi cảm biến, giao thức với bo mô phỏng, lõi firmware C++ khớp bản Python (test host), vật cản AI |
| Giả lập firmware | Firmware thật đã biên dịch chạy trong bo ảo QEMU, nói chuyện với phần mềm laptop | Giao thức, máy trạng thái, dốc tốc độ, hết hạn lệnh, mất liên lạc, reset chip (30/09); không kiểm được xung ESC/servo, E-stop, task watchdog kích hoạt |
| Bàn thử/bản ghi | Đo cảm biến thật hoặc xử lý dữ liệu đã ghi | LiDAR, bốn camera, AI trực tiếp, ghi/phát lại; định vị offline |
| Xe thật | Cảm biến và điều khiển trên xe chuyển động | Chưa có kết quả: chưa có xe, chưa nạp bo |

Cổng giai đoạn 0 đã đạt ở mức mô phỏng. Chưa cổng nào từ 1 đến 10 đạt; V1 đạt 0/10 điều kiện hoàn thành ([kế hoạch](KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) mục 16.4, 17.4). Kết quả mô phỏng hay giả lập không được dùng để đánh dấu đạt cổng (kế hoạch mục 15). Mức bằng chứng của từng điều kiện V1: sơ đồ 8.3 trong [Sơ đồ hệ thống](autopark/docs/SO_DO_HE_THONG.md).

## 2. Thiết bị

Tình trạng theo kiểm kê 22–25/09/2026; LiDAR và bốn camera qua hub chạy lại trên máy bàn hiện tại ngày 29/09/2026, các mục khác chưa kiểm kê lại. Hồ sơ tới 30/09/2026 không ghi nhận thêm thiết bị nào:

| Thành phần | Tình trạng |
|---|---|
| RPLIDAR C1 + CP2102N | Đã nhận 22/09 (serial `f57ffc8bc6e598d1b59598f976dd5762`). Máy bàn hiện tại: COM3, driver CP210x 11.2.0.167, đọc được ngày 29/09. Máy bàn trước: COM4, driver 11.6.0.420 |
| Bốn camera USB “HD Camera” | Đã nhận 23/09; không có serial nên danh tính là cổng hub; 130° là số nhà bán, góc nhìn thật chưa đo |
| Hub UGREEN bốn cổng | Đã nhận 23/09; camera chung nhánh USB 2.0, các phiên đã ghi dùng nguồn từ USB |
| MN300, ESP32-S3, BNO085, VL53L1X, AS5600, encoder | Chưa nhận |
| Nguồn, cầu chì, E-stop, phần tử ngắt | Chưa có bộ nào để kiểm chứng |

| Máy | Cấu hình | Vai trò |
|---|---|---|
| Máy bàn hiện tại (từ 29/09/2026) | Dell Precision 3680, i9-14900, RTX 4000 Ada 20 GB, RAM 63,7 GB, Windows 11 Enterprise, driver NVIDIA 596.71; repo ở `D:\xetulai\autopark` (tới chiều 29/09/2026 tên là `D:\gấp\autopark`) | Máy phát triển chính: huấn luyện, đo cảm biến, test host và biên dịch firmware, bo ảo QEMU |
| Máy bàn trước (tới 25/09/2026) | i9-14900, RTX 4000 Ada 20 GB, RAM 64 GB, driver NVIDIA 596.72; repo ở `D:\ap` | Nơi đo mọi số cảm biến, AI và bàn thử tới 25/09 |
| Laptop | i7-12700H, RTX 3050 Ti 4 GB | Máy trình diễn và nộp đồ án; mới chạy mô phỏng giai đoạn 0 (20/09), chưa đo cảm biến, AI hay bàn thử |

Cổng LiDAR đặt ở một chỗ: [`autopark/configs/thiet_bi.json`](autopark/configs/thiet_bi.json), khóa `lidar_port` (hiện `"COM3"`; `"auto"` tự tìm bộ chuyển CP210x, lấy cổng đầu tiên). Các lệnh LiDAR lấy cổng từ tệp này khi không có `--port`; `--port COMx` ghi đè cho một lần chạy. `rig.bench`/`ui.rig_app` lấy cổng này khi `--lidar` không kèm giá trị; lệnh kiểm máy mới (`do_may_moi.cmd`) luôn tự tìm CP210x. Từ 30/09/2026 cùng tệp giữ đường dẫn QEMU và PlatformIO cho bo ảo (khóa `qemu_xtensa`, `platformio_python`, `platformio_core_dir`; máy không có QEMU thì test bo ảo tự bỏ qua). Đổi máy thì sửa `lidar_port` và làm theo [biên bản chuyển máy](autopark/docs/CHUYEN_MAY_BAN.md) mục 5.

Công cụ firmware trên máy bàn, đặt ngoài repo: g++ 16.1.0 và cmake 4.4.1 cho test host; PlatformIO Core 6.2.0 ở `D:\xetulai\_platformio\penv`; QEMU của Espressif 9.2.2 ở `D:\xetulai\_platformio\qemu` ([biên bản chuyển máy](autopark/docs/CHUYEN_MAY_BAN.md) mục 6–8).

[Kiểm kê](autopark/docs/hardware_inventory.md), [phiếu nhận MN300](autopark/docs/mn300_inventory.md), [chuyển sang máy trình diễn](autopark/docs/MAY_NOP_DO_AN.md), [chuyển máy bàn](autopark/docs/CHUYEN_MAY_BAN.md).

## 3. Tiến độ theo 11 giai đoạn

Sơ đồ dưới cho thấy mỗi giai đoạn đang ở mức bằng chứng nào, và ba nhánh phần mềm, cảm biến trên bàn, xe/điều khiển/nguồn gặp nhau ở tích hợp. Phụ thuộc lấy theo [kế hoạch](KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) mục 2.2.

```mermaid
flowchart TD
    subgraph SG_PM["Nhánh phần mềm"]
        G0["GĐ 0 Mô phỏng: ĐẠT ở mức mô phỏng, 20/09"]
    end
    subgraph SG_CB["Nhánh cảm biến trên bàn"]
        G1["GĐ 1 LiDAR, camera mẫu: có số đo, cổng chưa đạt"]
        G2["GĐ 2 Bốn camera, BEV: bàn thử 640×480, chưa hiệu chuẩn"]
        G3["GĐ 3 Hợp nhất trên bàn: phần mềm, chưa IMU/ToF/ESP32"]
    end
    subgraph SG_XE["Nhánh xe, điều khiển, nguồn"]
        G4["GĐ 4 Đo MN300: chỉ bảng đo nháp, chưa có xe"]
        P["Chuẩn bị nguồn, dừng cho thử chấp hành: bản nháp"]
        G5["GĐ 5 ESP32: firmware biên dịch, chạy trong QEMU, chưa nạp bo"]
        G6["GĐ 6 Nguồn và dừng: bản nháp, 16 kịch bản CHƯA THỬ"]
    end
    subgraph SG_TH["Tích hợp và nghiệm thu"]
        G7["GĐ 7 Gá cảm biến lên xe: chưa làm"]
        G8["GĐ 8 Hợp nhất khi xe chạy: chỉ phần mềm"]
        G9["GĐ 9 Tự đỗ thật: chưa chạy"]
        G10["GĐ 10 Nghiệm thu, khóa luận: bản nháp, V1 0/10"]
    end
    G1 --> G2 --> G3 --> G7
    G4 --> G5
    G4 --> G7
    P --> G5
    P --> G6
    G0 --> G8
    G5 --> G8
    G7 --> G8 --> G9 --> G10
    G6 --> G9
    subgraph SG_CG["Chú giải"]
        K1["Có số đo trên thiết bị thật"]
        K2["Chỉ phần mềm, mô phỏng hoặc giả lập"]
        K3["Chưa làm, mới có bản nháp hoặc chưa thử trên thiết bị"]
    end
    classDef daco fill:#dff0d8,stroke:#3c763d,color:#1b3a1b
    classDef giaLap fill:#fcf8e3,stroke:#8a6d3b,color:#4d3b12
    classDef chuaLam fill:#f2dede,stroke:#a94442,color:#4d1a1a,stroke-dasharray: 4 3
    class G1,G2,K1 daco
    class G0,G3,G5,G8,K2 giaLap
    class G4,P,G6,G7,G9,G10,K3 chuaLam
```

Xanh: đã có và đã kiểm/đo · Vàng: chỉ trong mô phỏng/giả lập · Đỏ viền đứt: chưa làm hoặc chưa thử trên thiết bị. Ở sơ đồ này, xanh chỉ có nghĩa là đã có số đo trên thiết bị thật (cổng giai đoạn 1 và 2 vẫn chưa đạt); vàng gồm cả phần mềm mới chạy với nguồn giả hoặc bo mô phỏng; đỏ viền đứt gồm cả việc mới có bản nháp. Mũi tên là phụ thuộc theo kế hoạch, không có nghĩa bước đó đã xong. Như kế hoạch mục 2.2, phần chuẩn bị nguồn và dừng phải có trước khi thử chấp hành ở GĐ 5; GĐ 6 xác nhận nguồn và dừng toàn hệ thống, chỉ cần trước GĐ 9.

| GĐ | Công việc | Trạng thái 30/09/2026 và điểm đang chặn |
|---|---|---|
| 0 | Mô phỏng | Đạt 6 điều kiện chuyển bước ở mức mô phỏng (20/09/2026, laptop); thông số xe giả định |
| 1 | LiDAR và camera mẫu | Đang làm. Có số đo LiDAR và camera trên bàn; thiếu sai số khoảng cách LiDAR, định vị có tham chiếu độc lập, hiệu chuẩn và gá camera, chấm AI trên ảnh thật có nhãn; [cổng 1 chưa đạt](autopark/docs/gate_01.md) |
| 2 | Bốn camera, BEV | Đang làm. Bàn thử bốn camera + LiDAR + AI chạy ở 640×480; thiếu hiệu chuẩn và gá; 720p còn khung bị cắt tùy cảnh |
| 3 | Hợp nhất trên bàn | Có lớp bản đồ, phép hợp nhất và đường đưa vật cản LiDAR, AI camera vào phiên (phần mềm); chưa có IMU/ToF/ESP32 thật |
| 4 | Đo MN300 | Có bảng đo nháp và thử độ nhạy mô phỏng; chưa nhận xe |
| 5 | ESP32, điều khiển phản hồi | Có giao thức, bo mô phỏng, `VehicleIO`. Lõi C++ qua test host (703 check, 0 lệch, 29/09/2026); cả firmware biên dịch cho ESP32-S3 bằng PlatformIO (29/09/2026); chạy trong bo ảo QEMU (30/09/2026, [mô phỏng firmware](autopark/docs/MO_PHONG_FIRMWARE.md)). CHƯA nạp bo vì chưa có bo |
| 6 | Nguồn và dừng | Bản nháp: bảng tải, sơ đồ nguồn/dừng, 16 kịch bản lỗi CHƯA THỬ; chưa có phần cứng |
| 7 | Gá cảm biến lên xe | Chưa làm |
| 8 | Hợp nhất khi xe chạy | Có phần mềm chuẩn bị (`VehicleLink`, chế độ quan sát); chưa có nguồn tư thế thật nên START với bo thật bị từ chối; chưa kiểm đồng bộ thời gian |
| 9 | Tự đỗ thật | Chưa thực hiện |
| 10 | Nghiệm thu, khóa luận | Có dàn ý khóa luận, 37 kịch bản và ngưỡng nháp; chưa nghiệm thu V1 (0/10 điều kiện). Từ 02/10/2026 có thêm phần lớn công cụ phần mềm cho nghiệm thu (mục 4.15), mới kiểm bằng test và mô phỏng |

[Bản kiểm toán 275 việc ngày 24/09](autopark/docs/evidence/ke_hoach/kiem_toan_ke_hoach_20260924.json) ghi 56 việc xong, 92 một phần, 27 chưa bắt đầu, 100 chờ thiết bị. Bảng có trước các bổ sung sau đó; không dùng để tính phần trăm hoàn thành hiện tại. Sơ đồ đợt mua và thiết bị đã nhận: sơ đồ 8.2 trong [Sơ đồ hệ thống](autopark/docs/SO_DO_HE_THONG.md).

## 4. Nội dung theo mảng

### 4.1. Mô phỏng và lập đường

Có chỉnh sa bàn, đặt đích, xem trước, tiến/lùi, lái tay và xuất log. Mọi phần này chạy trên máy tính với xe và phản hồi mô phỏng; cấu hình xe `configs/vehicle_default.json` là giả định.

Điểm vào `planning/parking.py::plan_parking` tính đích từ ô đỗ (ô nhỏ hơn thân xe thì trả GOAL_INVALID ngay) rồi gọi thang `portfolio`: bốn nấc chạy lần lượt (không song song), mỗi đường ứng viên được xe mô phỏng bám thử trước khi nhận. Có hai ngưỡng khác nhau: đạt 4 cm/4° thì dừng leo thang, đạt 5 cm/5° (dung sai đích) thì được nhận:

```mermaid
flowchart TD
    S["portfolio.plan với ngân sách T: ứng dụng 8 s, bench 20 s"] --> L["default_ladder, ngân sách mỗi nấc nhân T chia 8 s"]
    subgraph THANG["Bốn nấc mặc định, tổng danh nghĩa 8 s"]
        N1["1. gộp-nhanh: cand_lattice_macro, 1,0 s"]
        N2["2. gộp-kỹ: cùng bộ lưới gộp, 1,5 s"]
        N3["3. ngẫu nhiên: cand_rrt_rs, RRT-Connect nối Reeds–Shepp, 4,0 s"]
        N4["4. lưới mịn: cand_reference, Hybrid A* lưới 2,5 cm và 5 độ, 1,5 s"]
        N1 --> N2 --> N3 --> N4
    end
    L -->|danh sách nấc| N1
    L --> NEXT{"Còn nấc và còn hơn 0,05 s?"}
    NEXT -->|Có| RUN["Chạy nấc kế tiếp với ngân sách nhỏ hơn giữa phần của nấc và thời gian còn lại"]
    RUN --> ST{"Nấc trả về gì?"}
    ST -->|GOAL_INVALID hoặc START_INVALID| BAD["Trả ngay, sai đầu bài thì leo thang vô ích"]
    ST -->|CANCELLED| CAN["Trả CANCELLED"]
    ST -->|NO_PATH hoặc TIMEOUT| MISS["Ghi nhật ký nấc, nhớ lỗi cuối"]
    MISS --> NEXT
    ST -->|OK| VER["rollout kiểm chứng, dung sai đích 5 cm và 5 độ"]
    VER -->|Hết hạn giữa chừng| TO["Ghi TIMEOUT, dừng leo thang"]
    VER --> Q1{"Tới đích, không va chạm, sai số không quá 4 cm và 4 độ?"}
    Q1 -->|Có| CMP{"Đã giữ một đường đạt 5 cm và 5 độ mà ít đổi chiều hơn, hoặc bằng số lần mà ngắn hơn?"}
    CMP -->|Không| OK1["Trả OK với đường này"]
    CMP -->|Có| FB
    Q1 -->|Không| Q2{"Đi hết đường và không va chạm?"}
    Q2 -->|Không| NEXT
    Q2 -->|Có| KEEP["Giữ làm dự phòng nếu tốt hơn: đạt 5 cm và 5 độ trước, rồi ít đổi chiều, ngắn, lệch hướng nhỏ"]
    KEEP --> NEXT
    NEXT -->|Không| FB{"Có đường dự phòng?"}
    TO --> FB
    FB -->|Có, trong dung sai| OK2["Trả OK với đường dự phòng"]
    FB -->|Có, ngoài dung sai| TF["Trả TRACKING_FAILED, đường chỉ để chẩn đoán"]
    FB -->|Không| LF["Trả lỗi cuối, NO_PATH hoặc TIMEOUT"]
    classDef daco fill:#dff0d8,stroke:#3c763d,color:#1b3a1b
    classDef giaLap fill:#fcf8e3,stroke:#8a6d3b,color:#4d3b12
    classDef chuaLam fill:#f2dede,stroke:#a94442,color:#4d1a1a,stroke-dasharray: 4 3
    class VER giaLap
```

Vàng: chỉ trong mô phỏng (xe mô phỏng bám thử đường). Các ô không tô là logic lập đường trong `planning/`, có test trên máy tính; chưa bước nào chạy trên xe thật. TRACKING_FAILED nghĩa là có đường nhưng xe mô phỏng không bám tới đích trong dung sai, khác NO_PATH. Hết thời gian hoặc chưa tìm ra đường không chứng minh bài toán vô nghiệm. Luồng từ nút bấm tới quỹ đạo, nhịp chạy kín vòng và phản ứng an toàn khi chạy: sơ đồ 3.1–3.4 trong [Sơ đồ hệ thống](autopark/docs/SO_DO_HE_THONG.md).

Hạn thời gian là đồng hồ thật (ứng dụng: 8 s cho cả tìm lẫn kiểm chứng), nên kết quả phụ thuộc tải máy và cách Windows xếp lịch tiến trình. Ngày 30/09/2026, khi để Windows tự quyết EcoQoS, cả 2/2 lượt nhóm 15 test ngân sách thời gian có test hỏng (1–3 test); khi tiến trình tự tắt EcoQoS, 2/2 lượt đạt 15/15. Từ đó `tests/conftest.py` tắt EcoQoS cho tiến trình pytest ([biên bản chuyển máy](autopark/docs/CHUYEN_MAY_BAN.md) mục 8). Ứng dụng chưa tắt. Đo ngày 02/10/2026 bằng `python -m autopark.evaluation.ecoqos_gui` (mở giao diện thật, đổi trạng thái cửa sổ trước mỗi lần lập đường; lệnh ở [hướng dẫn chạy](autopark/README.md) mục 4): cửa sổ thu nhỏ thì Windows hạ tốc tiến trình giao diện và lập đường `uturn_w46` hết hạn 8 s ở 4/4 lượt; tiến trình tự tắt EcoQoS thì đạt 4/4; bị che thì không chậm ([biên bản chuyển máy](autopark/docs/CHUYEN_MAY_BAN.md) mục 10; một máy, kế hoạch nguồn High performance, 4 lượt mỗi trạng thái).

Hồ sơ 20/09 (laptop) ghi 220 test đạt và 2.880 trường hợp theo seed không vi phạm các điều kiện đã đặt. Trong 240 phiên có lỗi giả: 25 hoàn thành, 185 dừng đúng logic, 30 FAULT do chèn vật quá gần. Không cộng ba nhóm thành số lần đỗ thành công. Mã lập đường, bám đường, mô phỏng và hình học không đổi từ commit đầu `bef5695` (21/09) tới `ff4a018`, trừ chữ trong docstring và chú thích. Ngày 29/09/2026 trên máy bàn hiện tại (mã `b37e9ee`), chạy lại năm phiên mẫu `evaluation.phase0` cho kết quả trùng từng giá trị với đợt 20/09 ([tóm tắt](autopark/docs/evidence/chuyen_may_20260929/kiem_may_20260929.md) mục 2.1); chiến dịch 2.880 ca chưa chạy lại sau 20/09.

Cả 16 ca khó có đường chứng trong mô hình hình học. Điều đó không có nghĩa planner tìm được trong thời hạn hoặc đường đủ thực dụng cho xe; `parallel_115` vẫn chưa được planner giải trong các lượt báo cáo. Từ 02/10/2026 có thể đặt giới hạn số lần đổi chiều khi chạy (`run_app.py <kịch bản> --max-cusps N`, công cụ T12): `Session.start_run` từ chối đường vượt giới hạn trước mọi lệnh tới bo, planner không đổi; mặc định không chặn, giao diện chỉ cảnh báo khi đường có hơn 7 lần đổi chiều. Tiêu chí "đường thực dụng" vẫn CHƯA CHỐT.

[Báo cáo mô phỏng](BAO_CAO_GIAI_DOAN_0.md), [kiểm thử độ bền](autopark/docs/KIEM_THU_DO_BEN_GIAI_DOAN_0.md), [độ nhạy kích thước](autopark/docs/DO_NHAY_KICH_THUOC_XE.md).

### 4.2. AI nhận thức, dữ liệu và giấy phép

L-RASPP/MobileNetV3 phân ảnh thành FREE và BLOCKED. Checkpoint tham chiếu: `runs/ai_woodscape_rtx4000_v1/best.pt`, không nằm trong Git; trên máy bàn hiện tại SHA-256 trùng hồ sơ ([biên bản chuyển máy](autopark/docs/CHUYEN_MAY_BAN.md) mục 1).

WoodScape test nội bộ ở ngưỡng 0,50 đạt mIoU 0,9692; 1,75% pixel vật cản bị gọi FREE. Ở ngưỡng an toàn 0,15 (ngưỡng mà ngăn AI camera dùng) bỏ sót còn 0,69%, còn 3,09% pixel FREE bị gọi vật cản (1,37% ở 0,50). Đây không phải test chính thức, chưa chứng minh độ chính xác sa bàn. Các lượt thêm AVM-SS/ACDC chưa thay thế được lượt nền trên cả hai tập đánh giá chưa dùng để học/chọn mô hình.

Số huấn luyện, chấm, ONNX và độ trễ trong [huấn luyện](HUAN_LUYEN.md) đo 21–24/09 trên máy bàn trước. Ngày 29/09/2026 trên máy bàn hiện tại (mã `b37e9ee`): chấm lại val được mIoU 0,9700, bỏ sót 1,70%, trùng số ngày 21/09; train thử 1 epoch chạy được ([tóm tắt lượt kiểm lại](autopark/docs/evidence/chuyen_may_20260929/kiem_may_20260929.md); tệp gốc ở `autopark/runs/kiem_may_20260929/`, không có trong Git). Trên laptop trình diễn chưa đo gì của AI.

Ngày 25/09 người làm khóa luận quyết định dùng checkpoint WoodScape trong vòng điều khiển theo cách diễn giải của dự án; Valeo chưa xác nhận. Quyết định không bao gồm nhãn nháp AI hoặc checkpoint chứa AVM-SS.

[Huấn luyện](HUAN_LUYEN.md), [giấy phép](autopark/docs/GIAY_PHEP_DU_LIEU.md). Sơ đồ huấn luyện, giấy phép dữ liệu và ngưỡng quyết định: sơ đồ 5.1, 5.2, 5.7 trong [Sơ đồ hệ thống](autopark/docs/SO_DO_HE_THONG.md).

### 4.3. LiDAR RPLIDAR C1

Đã đọc scan, ghi/phát lại, tạo bản đồ tĩnh. Sau bỏ khởi động, các bản ghi ngày 22 và 24/09 (máy bàn trước) đạt khoảng 10 vòng/s và 510 tia/vòng. Ngày 29/09 trên máy bàn hiện tại (COM3), lệnh kiểm máy mới đo 10,00 Hz, trung vị 508 tia/vòng, tương đương lượt cùng lệnh trên máy bàn trước ngày 24/09 ([biên bản chuyển máy](autopark/docs/CHUYEN_MAY_BAN.md) mục 2); cùng ngày, bàn thử 30 s lấy cổng từ `thiet_bi.json` nhận 301 vòng, 10,03 Hz (mục 4.11).

Độ lặp lại khoảng cách giữa hai vòng liên tiếp, tính offline trên ba bản ghi C1 đứng yên (22 và 24/09, phản hồi 0,2–4 m): trung vị |Δr| 0,75–1,5 mm, p90 4,25–7,75 mm ([thử LiDAR](autopark/docs/GIAI_DOAN_1_LIDAR.md) mục 3c). Đây không phải sai số so với thước; sai số khoảng cách so với thước chưa đo.

Có công cụ định vị trên bản đồ và odometry khớp scan. Kết quả C1 hiện dùng bản ghi đứng yên; chưa có tham chiếu độc lập hoặc kiểm khi di chuyển. Khớp lại cùng chỗ chưa chứng minh sai số định vị thực. Các công cụ này chạy offline, chưa là nguồn tư thế của phiên đỗ; phương án định vị cho V1 là đề xuất chờ chốt ([so sánh SLAM](autopark/docs/SO_SANH_DINH_VI_SLAM.md) mục 7).

[Thử LiDAR](autopark/docs/GIAI_DOAN_1_LIDAR.md), [định vị](autopark/docs/DINH_VI_LIDAR.md), [so sánh SLAM](autopark/docs/SO_SANH_DINH_VI_SLAM.md).

### 4.4. Camera USB và lỗi khung hình

Mặc định bàn thử **640×480** vì nhiều phiên 720p có khung MJPEG bị cắt khi bốn camera chạy chung hub. Một số phiên 720p nhìn cảnh tối không lỗi chưa đủ kết luận ổn định.

480p cũng từng có đợt lỗi; bộ đọc loại khung hỏng. Nguyên nhân chưa xác định dứt điểm. Camera được nhận diện theo cổng hub vì không có serial riêng; trên máy bàn hiện tại bốn camera vẫn cắm cổng hub 1–4, nhưng chưa khởi động lại máy để kiểm danh tính theo cổng.

[Thử camera](autopark/docs/GIAI_DOAN_1_CAMERA.md), [sơ đồ USB](autopark/docs/usb_topology.md).

### 4.5. Bàn thử bốn camera + LiDAR + AI

Có giao diện xem đồng thời, đo suy luận, độ lệch thời gian và khung lỗi. Quy tắc chờ dựa trên nhịp riêng từng camera; AI làm nóng với các cỡ lô cần dùng. Độ lệch và độ trễ tính theo lúc dữ liệu tới máy; độ trễ từ sự kiện thật tới lúc dữ liệu về máy chưa đo.

Số đo trong hướng dẫn bàn thử là của máy bàn trước. Ngày 29/09/2026, lệnh kiểm máy mới (`do_may_moi.cmd`, mã `9d68257`, LiDAR và bốn camera thật) trên máy bàn hiện tại cho: AI lô 4 ảnh 480p trung vị 10,8 ms (máy bàn trước 10,4 ms); bàn thử 480p + LiDAR + AI 120 s được 2.861 bộ ảnh, 0 khung hỏng, 23,85 bộ AI/s, như máy bàn trước; 720p chỉ camera được 715 bộ, 0 khung hỏng. Cảnh camera lúc đo không ghi lại, nên số khung hỏng chưa so được với các phiên cũ. Lượt này là tham chiếu `may_moi` hiện dùng ([`tham_chieu_20260929.json`](autopark/docs/evidence/may_ban/tham_chieu_20260929.json), người dùng chọn ngày 29/09/2026); lệnh đo trên laptop so với nó. Trong lượt chạy lại các lệnh README cùng ngày (15:08–15:19, mã `b37e9ee`), lệnh kiểm máy mới (`rig.may_moi`) chạy lần hai cho bàn thử 23,87 bộ AI/s, bước AI trung vị 12,7 ms (p95 21,8 ms); ba lần lặp riêng bước AI cho 11,0 / 10,8 / 10,8 ms ([tóm tắt](autopark/docs/evidence/chuyen_may_20260929/kiem_may_20260929.md)). Số máy bàn chưa thay được phép đo trên laptop trình diễn. [Hướng dẫn bàn thử](autopark/docs/GIAI_DOAN_2_BAN_THU.md), [kết quả kiểm máy mới](autopark/docs/CHUYEN_MAY_BAN.md) mục 2.

Từ 02/10/2026, `gap_max_ms` của từng camera trong `.rig.json` tính cả khoảng hở còn mở lúc chốt số (`gap_end_ms`: camera ngừng hẳn trước khi hết phần đo; công cụ T10), nghĩa cũ ở `gap_closed_max_ms`; `.rig.json` ghi trước đó không có khóa mới. `rig.bench --sync-mark` (T14) nháy dấu đồng bộ video–log trên màn hình và ghi `<name>.sync.csv` theo `perf_counter`, cùng đồng hồ với stamp của bàn thử. Cả hai mới kiểm bằng test với camera giả và giao diện offscreen; chưa chạy lại trên bàn thử thật, độ trễ hiển thị của dấu đồng bộ CHƯA ĐO ([hướng dẫn chạy](autopark/README.md) mục 7).

### 4.6. Hiệu chuẩn camera

Có bảng in, công cụ chụp/tính nội tham fisheye, đo ngoại tham và vẽ ROI. Công cụ mới được kiểm chủ yếu bằng ảnh tổng hợp; chưa camera dự án nào có hiệu chuẩn thật. Kiểm 30/09/2026: `calibration/` chưa có tệp nội tham `cam_p*.json` nào, `configs/rig/` chỉ có ngoại tham `v0` giả định, chưa có ROI `configs/roi/rig_v1/`. Từ 02/10/2026 công cụ nội tham mở được camera không qua hub 1–4 (camera trên cao của tham chiếu R1) theo index và tên (`ui.calib_app --index N --camera-name TÊN`, công cụ T11), lưu `calibration/cam_<tên>.json` (mode khác 640×480 thêm hậu tố kích thước, ví dụ `cam_tren_cao_1280x720.json`) mà BEV và AI camera không đọc; khi một số cổng có camera ở hai hub, chọn camera theo cổng chỉ nhận khi các cổng khác chỉ ra hub của camera xe, không thì báo lỗi thay vì chọn đại. Phần này mới kiểm offscreen với camera giả.

Thứ tự: **nội tham → ngoại tham theo gá → ROI → kiểm sai số bằng vật có vị trí đo được**.

```mermaid
flowchart TD
    A["Chốt camera, mode ảnh và vị trí gá"] --> B["Chụp bảng ô vuông để tính nội tham"]
    B --> C{"Nội tham đạt tiêu chí?"}
    C -->|Chưa| B
    C -->|Đạt| D["Đo vị trí và góc camera: ngoại tham"]
    D --> E["Vẽ ROI: loại thân xe và vùng không dùng"]
    E --> F["Chiếu BEV, đặt vật ở vị trí đã đo"]
    F --> G{"Sai số trong ngưỡng đã chốt?"}
    G -->|Chưa| H["Xác định lỗi ở gá, phép đo, nội tham hoặc ROI"]
    H --> A
    G -->|Đạt| I["Có bằng chứng hình học để xét dùng trên xe"]
    classDef daco fill:#dff0d8,stroke:#3c763d,color:#1b3a1b
    classDef giaLap fill:#fcf8e3,stroke:#8a6d3b,color:#4d3b12
    classDef chuaLam fill:#f2dede,stroke:#a94442,color:#4d1a1a,stroke-dasharray: 4 3
    class A,B,D,E,F,H,I chuaLam
```

Xanh: đã có và đã kiểm/đo · Vàng: chỉ trong mô phỏng/giả lập · Đỏ viền đứt: chưa làm hoặc chưa thử trên thiết bị. Ở đây mọi bước đều chưa làm với camera của dự án; công cụ cho từng bước đã có, mới kiểm trên ảnh tổng hợp. Nhánh cuối là mục tiêu kiểm chứng. Hiệu chuẩn đi tới chặn AI camera thế nào: sơ đồ 4.6 trong [Sơ đồ hệ thống](autopark/docs/SO_DO_HE_THONG.md).

[Nội tham](autopark/docs/HIEU_CHUAN_CAMERA.md), [ngoại tham và ROI](autopark/docs/NGOAI_THAM_VA_ROI.md).

### 4.7. Gán nhãn ảnh sa bàn

Có nhập ảnh, sửa/duyệt nhãn, xuất cache; chưa có tập sa bàn được gán nhãn để chấm mô hình. Tập đánh giá cần tô tay từ đầu và tách theo phiên chụp. Nhãn sửa từ dự đoán có thể thiên lệch về mô hình tạo nháp.

[Quy trình gán nhãn](autopark/docs/GAN_NHAN_SA_BAN.md).

### 4.8. Hợp nhất cảm biến

Có lớp bản đồ tĩnh, LiDAR, camera và cận trường; kiểm thời hạn dữ liệu; chuyển vật cản vào phiên mô phỏng. Ngày 22/09/2026 (máy bàn trước, COM4), xe ảo đã tìm đường quanh vật do LiDAR thật đứng yên quét. Sau khi đổi cách lấy cổng LiDAR (29/09/2026), `ui.lidar_app` và `fusion.demo` chưa chạy lại với LiDAR thật.

ToF mới dùng gá giả định và dữ liệu mô phỏng; lớp cận trường chưa được phiên đỗ dùng. Phiên chưa có nguồn tư thế thật: định vị LiDAR chỉ chạy offline (mục 4.3). Chưa kiểm trên xe chuyển động. [Chuẩn bị hợp nhất](autopark/docs/GIAI_DOAN_3_CHUAN_BI.md).

### 4.9. Giao thức xe, VehicleIO và firmware ESP32-S3

Laptop nói với bo bằng giao thức v1: khung COBS + CRC-16, phiên, số thứ tự, lệnh có hạn (laptop gửi hạn 150 ms, bo kẹp tối đa 300 ms); bo tự về DISARMED sau 500 ms không nhận thông điệp hợp lệ nào. Bản tham chiếu Python (`transport/protocol.py`, `transport/firmware_model.py`) là chuẩn. `VehicleIO` nói cùng byte giao thức với bo mô phỏng, cổng COM hoặc `socket://`. Chế độ quan sát tính lệnh và ghi log nhưng không gửi lệnh chạy.

Firmware C++ được kiểm theo từng tầng; chưa tầng nào chạm bo thật:

```mermaid
flowchart TD
    PY["Bản tham chiếu Python: protocol.py, firmware_model.py"]
    TP["pytest: protocol 52, firmware_model 73, vehicle_io 71 test"]
    VJ["vectors.py sinh test/vectors.json: 5 CRC, 11 COBS, 13 thông điệp, 11 luồng byte, 10 kịch bản 616 bước"]
    HT["test/host (g++ 16.1, cmake): src/core khớp từng byte, 703 check, 0 lệch"]
    HP["test_transport_firmware_host: build cmake, chạy vector, vector sai phải hỏng (2 test)"]
    SC["test_transport_firmware_source: kiểm tĩnh main.cpp và platformio.ini (11 test)"]
    PB["pio run -e esp32s3: cả firmware biên dịch, 0 cảnh báo (Arduino-ESP32 2.0.17, thử thêm 3.3.12)"]
    QB["Bo ảo QEMU, env esp32s3_qemu: 13 test, 6 trong đó chạy firmware thật trong QEMU, 10/10 lượt đạt"]
    M0["M0: nạp bo, chỉ cắm USB, PWM tắt: HELLO_ACK, telemetry 20 Hz, ARM, hết hạn, rút cáp"]
    M1["M1: máy hiện sóng hoặc logic analyzer trên chân ESC, servo: guard, watchdog, panic, E-stop"]
    M2["M2 và M3: nối ESC, servo, xe kê cao bánh rồi chạy trên sàn"]
    PY --> TP
    PY --> VJ --> HT --> HP
    SC --> PB
    HT --> PB --> QB --> M0 --> M1 --> M2
    classDef daco fill:#dff0d8,stroke:#3c763d,color:#1b3a1b
    classDef giaLap fill:#fcf8e3,stroke:#8a6d3b,color:#4d3b12
    classDef chuaLam fill:#f2dede,stroke:#a94442,color:#4d1a1a,stroke-dasharray: 4 3
    class PY,TP,VJ,HT,HP,SC,PB daco
    class QB giaLap
    class M0,M1,M2 chuaLam
```

Xanh: đã có và đã kiểm/đo · Vàng: chỉ trong mô phỏng/giả lập · Đỏ viền đứt: chưa làm hoặc chưa thử trên thiết bị. Xanh ở đây là đã kiểm trên máy tính (test host và biên dịch ngày 29/09/2026); số test theo lượt trên `ebbec83` (30/09/2026). Bo ảo không có LEDC, GPIO vào (E-stop) hay USB-CDC thật, và task watchdog không bao giờ kích hoạt; chạy được trong bo ảo không chứng minh gì về bo thật ([mô phỏng firmware](autopark/docs/MO_PHONG_FIRMWARE.md) mục 1). M0–M3 là các mức thử trên bo ở [chuẩn bị nguồn và dừng](autopark/docs/GIAI_DOAN_6_CHUAN_BI.md) mục 5.1, dựng theo trình tự thử trên bo của [README firmware](autopark/firmware/esp32_vehicle/README.md). Kiến trúc liên kết laptop–bo, trình tự chạy và lỗi, máy trạng thái firmware: sơ đồ 6.1–6.7 trong [Sơ đồ hệ thống](autopark/docs/SO_DO_HE_THONG.md).

Phía giao diện: thẻ "Bo điều khiển" cho chọn cổng và "Kiểm kết nối bo" (HELLO, đọc vài khung telemetry, không ARM, không gửi lệnh). Danh sách chỉ có bo mô phỏng và cổng COM, nên chưa chọn được bo ảo (`socket://` mới dùng từ Python và trong test); bo ảo cũng chưa nối vào phiên đỗ, mới kiểm ở mức `VehicleIO` (13 test, 6 trong đó chạy firmware thật trong QEMU). Chọn cổng COM thì Bắt đầu đỗ bị từ chối trước khi mở cổng vì chưa có nguồn tư thế thật; kể cả khi có, `begin_run` còn thiếu bước mở cổng (`reopen()`). Từ 02/10/2026 thẻ có nút "Xóa lỗi bo (CLEAR_FAULT)" (T15) cho bo chọn ở cổng COM: chỉ gửi CLEAR_FAULT khi bo đang FAULT và telemetry báo nút dừng khẩn đã nhả, không ARM, không gửi lệnh chuyển động, mỗi lần bấm một dòng `board_actions.csv`. Cùng ngày, mỗi quyết định dừng của phiên chạy qua `VehicleIO` được ghi vào `events.csv` (dòng `session_stop`, T13), và lần chạy qua `VehicleIO` có gói phát lại bằng log (T9): chạy lại cùng phần mềm trên đầu vào đã ghi và so quyết định, không tái hiện xe. Cả ba mới thử với bo mô phỏng và cổng serial giả; với ESP32-S3: CHƯA THỬ ([chế độ quan sát](autopark/docs/CHE_DO_QUAN_SAT.md)).

Firmware chưa có mã đọc cảm biến (encoder, AS5600, BNO085, VL53L1X, điện áp nguồn): telemetry báo không có số đo. Loại bo (`esp32-s3-devkitc-1`) và các chân ESC, servo, E-stop CHƯA CHỐT. Khoảng hở còn lại (suy ra từ mã, chưa có test; [giao thức](autopark/docs/GIAO_THUC_XE.md) mục 12): nếu bo vừa về ARMED vì hết hạn lệnh (`COMMAND_TIMEOUT`) mà khung telemetry báo điều đó chưa tới laptop, laptop vẫn có thể gửi enable=1 và bo chạy lại (ARMED → RUNNING); khoảng hở và effort khi đó trên bo thật: CHƯA ĐO. Đề xuất chốt phía firmware (sau `COMMAND_TIMEOUT` không nhận enable=1 tới khi có ARM mới): CHƯA LÀM.

[Giao thức và điểm còn mở](autopark/docs/GIAO_THUC_XE.md), [quan sát](autopark/docs/CHE_DO_QUAN_SAT.md), [firmware](autopark/firmware/esp32_vehicle/README.md), [bo ảo QEMU và các trình giả lập đã thử](autopark/docs/MO_PHONG_FIRMWARE.md).

### 4.10. Nguồn và an toàn

Có bản nháp bảng tải, sơ đồ nguồn/dừng, 16 kịch bản lỗi L1–L16 (đều CHƯA THỬ); chưa có phần cứng nguồn hay dừng nào, chưa đo điện áp hay dòng. Theo thiết kế có ba lớp dừng: nút LA38 cắt động lực bằng phần cứng, firmware, laptop; phần tử ngắt có ba phương án, CHƯA CHỐT. Ngõ E-stop của ESP32 không thay đường ngắt động lực.

Tác dụng của `output_guard`, móc panic, ngõ E-stop thật và watchdog phần cứng của chip chưa được kiểm ở đâu: firmware mới biên dịch và chạy trong bo ảo, mà bo ảo không có LEDC, GPIO vào và watchdog phần cứng không kích hoạt. Watchdog liên lạc 500 ms (`LINK_TIMEOUT`) và logic chốt E-stop (với ngõ vào giả) đã kiểm bằng bản Python và test host; watchdog liên lạc kiểm thêm trong bo ảo. Chuỗi dừng ba lớp và sơ đồ nguồn dự kiến: sơ đồ 7.1, 7.2 trong [Sơ đồ hệ thống](autopark/docs/SO_DO_HE_THONG.md). Từ 02/10/2026 kịch bản L7 (vòng điều khiển của laptop treo) có script diễn tập ở mức mô phỏng (`python -m autopark.evaluation.fault_drill hang`, công cụ T6, có hoặc không Heartbeat); trên bo vẫn CHƯA THỬ.

[Chuẩn bị nguồn và dừng](autopark/docs/GIAI_DOAN_6_CHUAN_BI.md).

### 4.11. Ghi và phát lại phiên bàn thử

Có ghi camera + LiDAR và phát lại không cần thiết bị. Phiên thật 60 giây `o03` (máy bàn trước, 24/09, camera nhìn chỗ tối) đã được đối chiếu số bộ ảnh và độ lệch thời gian khi phát lại. Ngày 29/09/2026 trên máy bàn hiện tại (mã `b37e9ee`), một phiên 30 s bốn camera + LiDAR + AI ghi bằng `rig.bench --record`; phát lại đủ 3.026 khung và 301 vòng LiDAR, ra 717 bộ ảnh như lúc ghi ([tóm tắt](autopark/docs/evidence/chuyen_may_20260929/kiem_may_20260929.md)). Bản ghi đầy đủ không có trong Git. Chưa có bản ghi nhìn sa bàn thật.

[Quy trình ghi/phát lại](autopark/docs/GHI_PHAT_LAI_BAN_THU.md).

### 4.12. BEV từ nhiều camera

BEV là bản đồ nhìn từ trên xuống suy ra từ ảnh và hình học camera, gồm ô FREE/OCCUPIED/UNKNOWN. Phần chiếu đã tăng tốc và kiểm kết quả bằng dữ liệu tổng hợp. Từ 25/09/2026 (`b01dea4`) BEV đi vào phiên đỗ qua ngăn AI camera (mục 4.16); lệnh `bev` mặc định gọi vật cản khi P(BLOCKED) ≥ 0,50, còn ngăn AI camera dùng 0,15.

Chỉ dùng khi hiệu chuẩn, ngoại tham, ROI và thời gian dữ liệu đạt kiểm tra. Giả định sàn phẳng và biên chân vật giới hạn kết quả. Ngoại tham `v0` trong Git là giả định.

[Chi tiết BEV](autopark/docs/BEV.md).

### 4.13. Đo MN300

Có phiếu kiểm kê và bảng đo kích thước, lái, tốc độ, điện, gá. Chưa nhận xe nên chưa có số đo xe. Không dùng `vehicle_default.json` làm thông số MN300 thật.

[Chuẩn bị đo xe](autopark/docs/GIAI_DOAN_4_CHUAN_BI.md).

### 4.14. Khóa luận

Có dàn ý và hình/bảng tham khảo; dàn ý không phải bản thảo khóa luận. Chưa biết mẫu trường, kiểu trích dẫn, giới hạn trang và quy định khai báo AI. Kết quả mô phỏng, giả lập firmware, dữ liệu công khai, bàn thử, xe thật phải trình bày riêng.

[Dàn ý](autopark/docs/DAN_Y_KHOA_LUAN.md).

### 4.15. Nghiệm thu V1

Có nháp 37 kịch bản trong chín nhóm, cách đo độc lập và ngưỡng đề xuất. Chưa nghiệm thu các kịch bản; ngưỡng còn chờ chốt.

Công cụ nghiệm thu (bảng T1–T15 của kịch bản mục 7, đối chiếu mã ngày 02/10/2026): đã có T1 (thẻ "Bo điều khiển"), T5 (chấm một lần chạy, `evaluation/score_run.py`), T6 (tiêm lỗi có kiểm soát, chỉ ở mức mô phỏng), T9 (phát lại log lần chạy qua `VehicleIO`), T10 (khoảng hở cuối phiên của camera), T11 (camera ngoài hub trong công cụ hiệu chuẩn), T12 (giới hạn số lần đổi chiều, mặc định tắt), T13 (sự kiện dừng của phiên trong log), T14 (dấu đồng bộ video–log) và T15 (nút CLEAR_FAULT); T8 có một phần; còn thiếu T2 (nguồn tư thế thật), T3 (ghi cảm biến trong phiên đỗ), T4 (trích tư thế tham chiếu từ video; định dạng tệp tư thế đã có) và T7 (LED trên bo). Các công cụ thêm ngày 02/10/2026 mới kiểm bằng test: bo mô phỏng, cổng serial giả, camera giả, giao diện offscreen, bản ghi phát lại; chưa dùng với LiDAR, camera thật, bo ảo qua giao diện hay ESP32-S3. Lệnh của từng công cụ: [hướng dẫn chạy](autopark/README.md) mục 3, 4, 7, 8, 9.

Công cụ chấm T5 đọc log VehicleIO hoặc gói của `export_run` cùng tham chiếu độc lập, tính các ngưỡng N-… theo `autopark/configs/nguong_nghiem_thu.json` (bản sao các ngưỡng ĐỀ XUẤT – CHỜ CHỐT) và ghi một dòng biên bản cùng tệp chi tiết; nó chỉ tự đề xuất THÀNH CÔNG hay THẤT BẠI. Mới chấm dữ liệu tổng hợp và lần chạy mô phỏng; chưa chấm lần chạy thật vì chưa có tham chiếu R1 (T4). Chấm thử mức MP cho DO-1 (02/10/2026, trên log tạm, không lưu trong repo): ở tốc độ mặc định 0,15 m/s của planner, tốc độ thật lớn nhất trên đoạn 0,2 m là 0,150 m/s ở nhánh SIM và ≈ 0,18 m/s qua bo mô phỏng (số lẻ đổi theo cấu hình bo), vượt N-V1 (0,12 m/s), nên công cụ đề xuất THẤT BẠI; đặt `max_speed_mps` 0,10 cho xe (và bo mô phỏng) thì mọi kiểm đạt, phần này có test (`tests/test_score_run.py`, `bai_do_xe.json` qua bo mô phỏng) ([ngưỡng đề xuất](autopark/docs/NGUONG_NGHIEM_THU_DE_XUAT.md) N-V1).

[Kịch bản](autopark/docs/KICH_BAN_NGHIEM_THU.md), [ngưỡng đề xuất](autopark/docs/NGUONG_NGHIEM_THU_DE_XUAT.md).

### 4.16. AI camera trong vòng điều khiển

**Từ lô AI tới vật cản** trong phần mềm hiện có: mỗi lô phải qua chuỗi chặn theo đúng thứ tự trong `CameraObstacleMapper.update` (`fusion/camera_ai.py`):

```mermaid
flowchart TD
    RES["Lô AI mới nhất, đọc mỗi nhịp 50 ms của ngăn AI camera"] --> ST{"Rig nạp đủ nội tham, ngoại tham, ROI và không phải rig TỔNG HỢP với camera thật?"}
    ST -->|Không| BLK["Chặn lô: 0 ô OCCUPIED, lớp không hợp lệ, xóa cửa sổ lọc, hiện lý do"]
    ST -->|Có| SZ{"Cỡ khung trùng cỡ ảnh đã hiệu chuẩn?"}
    SZ -->|Không| BLK
    SZ -->|Có| BEV["bev.build_bev: t_blocked 0,15, t_free 0,05, che hộp thân xe nới 5 cm"]
    BEV --> GT{"BEV dùng được? Rig thật: ngoại tham measured, có ROI, all_pass đúng true, không dữ liệu TỔNG HỢP"}
    GT -->|Không| BLK
    GT -->|Có| GAP{"Lô cách lô trước quá 0,5 s?"}
    GAP -->|Có| CLR["Xóa cửa sổ lọc"]
    GAP -->|Không| MAPF
    CLR --> MAPF["vehicle_states_to_map: đặt vào lưới sa bàn theo tư thế xe hoặc chỗ đặt camera, lấy mẫu 3×3"]
    MAPF --> EGO["ego_cells: che thân xe lần hai trong hệ bản đồ, ở tư thế của lô"]
    EGO --> FLT["Lọc thời gian: OCCUPIED khi thấy ở ít nhất 2 trong 3 lô đã xét"]
    FLT --> LAY["CameraSemanticLayer, tuổi tối đa 0,5 s"]
    LAY --> FUS["fuse: Costmap hợp nhất riêng của ngăn"]
    FUS --> BRG["ObstacleBridge tiền tố camera_ai: chỉ thêm hoặc bớt hộp của AI"]
    BRG --> SES["Session: planner chỉ dùng hộp vật cản, FREE của camera không mở đường"]
    REAL["Camera thật đã hiệu chuẩn: chưa có, phát lại o03 cho 1.163 trên 1.163 lô bị chặn"] -.-> ST
    classDef daco fill:#dff0d8,stroke:#3c763d,color:#1b3a1b
    classDef giaLap fill:#fcf8e3,stroke:#8a6d3b,color:#4d3b12
    classDef chuaLam fill:#f2dede,stroke:#a94442,color:#4d1a1a,stroke-dasharray: 4 3
    class RES,ST,BLK daco
    class SZ,BEV,GT,GAP,CLR,MAPF,EGO,FLT,LAY,FUS,BRG,SES giaLap
    class REAL chuaLam
```

Xanh: đã có và đã kiểm/đo · Vàng: chỉ trong mô phỏng/giả lập · Đỏ viền đứt: chưa làm hoặc chưa thử trên thiết bị. Ở sơ đồ này, xanh là đã chạy khi phát lại bản ghi thật o03 với mô hình thật và rig thật: cả 1.163 lô bị chặn ngay ở ô chặn tĩnh vì chưa có tệp nội tham, ngoại tham đã đo và ROI. Vàng là bước kiểm cỡ khung, cổng "BEV dùng được" và nhánh tạo vật cản: mới chạy với test, nguồn giả và rig tổng hợp (kể cả phát lại o03 với rig tổng hợp, vị trí vật cản vô nghĩa); nhánh chặn của hai bước kiểm này mới kiểm bằng test. Rig tổng hợp chỉ được dùng khi thử bằng bản ghi hoặc nguồn giả, không bao giờ với camera live.

Ngăn **AI camera** của `ui.lidar_app --camera-ai` chuyển ô vật cản BEV vào phiên đỗ bên cạnh LiDAR. Nó chỉ thêm vật cản: không xóa vật cản LiDAR hoặc vật do người dùng đặt, và FREE của camera không mở đường. Hộp AI vào phiên theo trạng thái phiên (sơ đồ 5.5 trong [Sơ đồ hệ thống](autopark/docs/SO_DO_HE_THONG.md)):
- đang chỉnh sa bàn (EDITING): sau mỗi lô dùng được, hộp AI được thêm hoặc bớt (chỉ hộp của AI);
- sẵn sàng (READY): bản đồ giữ cố định để lập đường và xem trước;
- đang chạy (RUNNING): hộp AI mới chạm hành lang quỹ đạo còn lại (nới 10 cm) gây MAP_CHANGED, xe dừng và chờ lập lại đường; hộp mới ngoài hành lang chỉ được ghi nhớ, không thêm vào sa bàn;
- AI không dùng được khi xe chạy (bị chặn, chưa có kết quả, quá 0,5 s hoặc lỗi): mặc định cảnh báo và giữ vật cản đã biết; bật **AI bắt buộc** thì dừng xe.

Đã kiểm bằng nguồn giả, rig tổng hợp và phát lại o03 với mô hình thật (25/09/2026, máy bàn trước). Với cấu hình thật chưa hiệu chuẩn: **1.163 lô bị chặn, 0 vật cản được tạo**. Chưa thử nhánh này với camera live, qua `VehicleIO` hoặc trên xe thật.

Mặc định thử nghiệm: BLOCKED 0,15; xuất hiện ít nhất hai trong ba lô; tuổi lớp AI tối đa 0,5 giây; lề thân xe 5 cm. Chưa phải ngưỡng nghiệm thu. Tư thế đặt lô chưa nội suy về lúc chụp.

[Điều kiện bật và giới hạn](autopark/docs/AI_DIEU_KHIEN_XE.md).

## 5. Việc tiếp theo

### 5.1. Những lựa chọn còn cần chốt

- Phương án định vị và nguồn tư thế thật cho phiên đỗ.
- Tốc độ, ngưỡng và bộ kịch bản nghiệm thu; máy chạy khi nghiệm thu, camera trên cao, nơi lưu biên bản ([kịch bản nghiệm thu](autopark/docs/KICH_BAN_NGHIEM_THU.md) mục 8). Tốc độ mặc định 0,15 m/s của planner vượt N-V1 khi chấm mức MP (mục 4.15): cần chọn giữa một cấu hình xe riêng cho nghiệm thu và đổi mặc định.
- Nguồn, E-stop, phần tử ngắt, encoder, gá; loại bo ESP32-S3 và chân ESC, servo, E-stop.
- Chốt phía firmware sau `COMMAND_TIMEOUT`; báo sức khỏe ToF (đổi bố cục byte, phải tăng phiên bản giao thức).
- Xe tự tiếp tục hay chờ xác nhận sau vật cản thông thường.
- Chính sách AI bắt buộc và tham số của ngăn AI camera; ngăn chỉ nhận checkpoint học trên WoodScape (không AVM-SS) hay không.
- Có dùng nhãn nháp AI khi gán nhãn ảnh sa bàn không.
- Tiêu chí "đường thực dụng": trần số lần đổi chiều, nhịp ngắn nhất (công cụ giới hạn số lần đổi chiều T12 đã có, mặc định tắt).
- Sao lưu `autopark/runs/` (checkpoint tham chiếu, bản ghi đo) và dataset ra ngoài ổ D: hồ sơ chưa ghi nhận bản sao lưu nào.

Bản viết lại không thay đổi quyết định kỹ thuật hoặc tự duyệt đề xuất.

### 5.2. Việc làm được với cảm biến hiện có

1. Hiệu chuẩn camera, đo ngoại tham, tạo ROI. Đây cũng là điều kiện để AI camera bắt đầu tạo vật cản trên bàn thật (mục 4.16).
2. Dùng vật đo bằng thước để chấm LiDAR và BEV.
3. Thu ảnh sa bàn, lập tập chấm tô tay riêng; kết quả chấm cũng là căn cứ chốt ngưỡng 0,15 và lọc 2/3 của ngăn AI camera.
4. Đo bốn camera + LiDAR + AI trên laptop trình diễn ([máy nộp đồ án](autopark/docs/MAY_NOP_DO_AN.md), rồi `do_may_moi.cmd`).
5. Ghi LiDAR khi di chuyển, đối chiếu bằng tham chiếu độc lập.
6. Trên máy bàn hiện tại: khởi động lại rồi kiểm danh tính bốn camera theo cổng hub (N-C5 trong [ngưỡng đề xuất](autopark/docs/NGUONG_NGHIEM_THU_DE_XUAT.md)); chạy lại `ui.lidar_app`, `fusion.demo` và lệnh camera riêng (`video.camera_bench measure`/`record`, chưa có hồ sơ chạy sau 23/09/2026; sau đó chỉ bước `camera_bench list` chạy bên trong `may_moi`, ngày 24/09/2026 trên máy bàn trước và 29/09/2026 trên máy bàn hiện tại) với thiết bị thật. Sau sửa đổi cổng LiDAR đã chạy với thiết bị thật: `lidar.rplidar_c1 info` ([biên bản chuyển máy](autopark/docs/CHUYEN_MAY_BAN.md) mục 3), rồi lượt 29/09/2026 15:08–15:19 (mã `b37e9ee`) ghi LiDAR 10 s ở COM3 và chạy `rig.bench --lidar` 30 s với bốn camera, LiDAR và AI, có ghi phiên và phát lại ([tóm tắt](autopark/docs/evidence/chuyen_may_20260929/kiem_may_20260929.md); tệp gốc `autopark/runs/kiem_may_20260929/`, không có trong Git).
7. Mỗi lượt đo camera ghi lại cảnh camera nhìn; khung hỏng phụ thuộc cảnh nên thiếu thông tin này thì không so được giữa các lượt hay giữa các máy.
8. Các kịch bản nghiệm thu làm được khi chưa có xe: DV-1 (định vị tĩnh so với thước), DV-2 (hướng gốc sau khởi động lại mô-tơ), LD-1 (chạy dài 30 phút trên máy bàn, rồi trên laptop), TC-1 khi chọn được camera trên cao ([kịch bản nghiệm thu](autopark/docs/KICH_BAN_NGHIEM_THU.md) mục 6). LD-1 có ghi phiên (`--record`) cần ổ còn trống ≥ 30 GB; ổ D máy bàn còn ≈ 28 GB sau khi cài PlatformIO chiều 29/09/2026, rồi ≈ 62,6 GB khi đọc lại chiều 30/09/2026 (không lưu log; [biên bản chuyển máy](autopark/docs/CHUYEN_MAY_BAN.md) mục 7). Số này đổi theo thời gian, nên đọc lại ngay trước khi chạy.

### 5.3. Việc cần thiết bị mới

Nhận/đo MN300; nhận ESP32-S3, nạp firmware (đã biên dịch 29/09/2026) theo các mức M0–M3 ([chuẩn bị nguồn và dừng](autopark/docs/GIAI_DOAN_6_CHUAN_BI.md) mục 5.1; trình tự thử trên bo ở [README firmware](autopark/firmware/esp32_vehicle/README.md)); viết mã đọc phản hồi rồi đọc encoder, góc lái, IMU, ToF; lắp nguồn/dừng; kiểm từng phần trước khi gá lên xe. [Sáu đợt mua](KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) (kế hoạch mục 3).

Ngoài sáu đợt mua, tài liệu chưa ghi đã có máy hiện sóng hoặc logic analyzer (đo xung ESC/servo trước khi nối), đồng hồ vạn năng, nguồn bàn hay adapter nguồn cho hub; dự án chưa có đồng hồ đo dòng USB ([chuẩn bị nguồn và dừng](autopark/docs/GIAI_DOAN_6_CHUAN_BI.md) mục 1). Nghiệm thu còn cần camera trên cao, giá treo, marker in và thước thẳng dài ≥ 0,65 m ([kịch bản nghiệm thu](autopark/docs/KICH_BAN_NGHIEM_THU.md) mục 3.2).

### 5.4. Phần mềm có thể chuẩn bị

Còn lại: cho giao diện chọn được bo ảo QEMU (`socket://`, hiện chỉ dùng từ Python) và nối bo ảo vào phiên đỗ; làm nguồn tư thế thật và bước mở cổng (`reopen()`) trong `begin_run`; các công cụ còn thiếu trong [kịch bản nghiệm thu](autopark/docs/KICH_BAN_NGHIEM_THU.md) mục 7: T2, T3, T4 (khớp mặt sàn từ mốc, kiểm trên điểm kiểm tra, trích tư thế từ video; đã có định dạng tệp đầu ra và công cụ nội tham cho camera trên cao, T11) và mã firmware của T7, T8; đo độ trễ hiển thị của dấu đồng bộ (T14) và thử nó với màn hình, camera thật; chọn cấu hình xe hay tốc độ cho nghiệm thu (mục 4.15). Thay đổi giao thức cần được thiết kế/kiểm riêng.

Đã làm ngày 02/10/2026, mới kiểm bằng test (bo mô phỏng, cổng serial giả, camera giả, giao diện offscreen, bản ghi phát lại), chưa thử trên thiết bị: nút CLEAR_FAULT (T15); ghi sự kiện dừng của phiên vào log `VehicleIO` (T13) và dấu đồng bộ video–log (T14); phát lại lần chạy qua `VehicleIO` bằng log (T9); công cụ chấm một lần chạy (T5), tiêm lỗi có kiểm soát ở mức mô phỏng (T6), khoảng hở cuối phiên của camera (T10), camera ngoài hub trong công cụ hiệu chuẩn (T11), giới hạn số lần đổi chiều (T12).

Ứng dụng tự tắt EcoQoS hay cảnh báo khi cửa sổ bị thu nhỏ: CHƯA LÀM, chờ quyết định. Đo ngày 02/10/2026 (`python -m autopark.evaluation.ecoqos_gui`): cửa sổ thu nhỏ thì lập đường hết hạn 8 s ở 4/4 lượt ([biên bản chuyển máy](autopark/docs/CHUYEN_MAY_BAN.md) mục 10); vòng điều khiển 50 Hz khi cửa sổ thu nhỏ và kế hoạch nguồn Balanced: CHƯA ĐO.

## 6. Bản đồ tài liệu

- [Cài/chạy](autopark/README.md): thao tác phần mềm, chạy test, firmware và bo ảo.
- [Kế hoạch](KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md): thứ tự, phụ thuộc, điều kiện hoàn thành.
- [Sơ đồ hệ thống](autopark/docs/SO_DO_HE_THONG.md): các sơ đồ kiến trúc, luồng dữ liệu, an toàn, tiến độ và quy trình, tô màu theo trạng thái (30/09/2026, cập nhật 02/10/2026 cho các công cụ nghiệm thu).
- [Huấn luyện](HUAN_LUYEN.md): dữ liệu, kết quả, tái hiện AI.
- [Báo cáo giai đoạn 0](BAO_CAO_GIAI_DOAN_0.md): bằng chứng mô phỏng 20/09.
- [Mục lục kỹ thuật](autopark/docs/README.md): hướng dẫn/biên bản theo công việc.
- [Mô phỏng firmware](autopark/docs/MO_PHONG_FIRMWARE.md): bo ảo QEMU, các trình giả lập đã thử và giới hạn (29–30/09/2026).
- [Firmware ESP32-S3](autopark/firmware/esp32_vehicle/README.md): kiểm trên máy tính, biên dịch, bo ảo, trình tự thử trên bo.
- [Chuyển máy bàn](autopark/docs/CHUYEN_MAY_BAN.md): máy bàn hiện tại, cổng LiDAR, cài lại môi trường, đổi tên thư mục sang `D:\xetulai`, PlatformIO, số kiểm 29/09–02/10/2026 (test host và biên dịch firmware, bo ảo QEMU, EcoQoS, số test trên `ebbec83`, `c03ff94` và `d3e1555`, đo EcoQoS của giao diện; mục 2, 3, 6–11), các bước lần sau đổi máy.
- [Máy nộp đồ án](autopark/docs/MAY_NOP_DO_AN.md): cài và đo lại trên laptop trình diễn.

## 7. Cách đọc bằng chứng

“Đạt” gắn với phép thử, thời điểm và môi trường cụ thể. Test giả không thay số đo thiết bị. Chạy được trong bo ảo QEMU không thay chạy trên bo thật. FPS không thay độ trễ từ sự kiện thật tới ảnh. Độ lặp lại không phải sai số so với thước. Test có hạn giờ đo cả cách Windows xếp lịch tiến trình: từ trưa 30/09/2026 pytest tắt EcoQoS và JUnit ghi trạng thái đó (`ecoqos`).

| Đợt đã ghi | Kết quả | Phạm vi |
|---|---|---|
| 20/09 | 220 đạt | Bộ giai đoạn 0 lúc đó, laptop |
| 25/09, trước AI camera | `.venv`: 1.242 đạt, 7 bỏ qua; nhóm `.venv-train`: 386 đạt | Máy bàn trước. `.venv` chạy toàn bộ test; `.venv-train` chỉ chạy nhóm chọn (các mô-đun cần torch cùng test gán nhãn, bàn thử, `may_moi`, hiệu chuẩn, ngoại tham, ROI), không phải toàn bộ |
| 25/09, AI camera | 343 đạt ở mỗi môi trường | 15 tệp liên quan, máy bàn trước |
| 25/09, cuối đợt AI camera | `.venv`: 1.315 đạt, 7 bỏ qua (cần torch); `.venv-train`: 1.376 đạt | Toàn bộ test, máy bàn trước |
| 29/09, mã `9d68257` | `.venv`: 1.315 đạt, 7 bỏ qua; `.venv-train`: 1.376 đạt | Toàn bộ test, máy bàn hiện tại; trùng số máy bàn trước |
| 29/09, sau sửa đổi chuyển máy | `.venv`: 1.353 đạt, 8 bỏ qua (cần torch); `.venv-train`: 1.415 đạt; 0 hỏng | Toàn bộ test, máy bàn hiện tại, mã `9d68257` cộng sửa đổi cổng LiDAR, đọc/ghi ảnh, cài đặt |
| 29/09, commit `38f64bb` | `.venv`: 1.354 đạt, 8 bỏ qua (cần torch); `.venv-train`: 1.416 đạt; 0 hỏng | Toàn bộ test, máy bàn hiện tại, commit của đợt chuyển máy; thêm một test tệp tham chiếu `may_moi` 29/09 |
| 29/09 chiều, test host firmware | `.venv`: 1.356 đạt, 8 bỏ qua (cần torch); `.venv-train`: 1.418 đạt; 0 hỏng | `b37e9ee` cộng hai test build và chạy test host của firmware |
| 30/09 sáng, bo ảo QEMU | `.venv`: 1.376 đạt, 8 bỏ qua (cần torch), 0 hỏng; `.venv-train`: 1.437 đạt, 1 hỏng (`uturn_w46`, ngân sách thời gian) ở cả hai lượt | Mã chưa commit tính tới 10:21, trước khi `tests/conftest.py` tắt EcoQoS: `b37e9ee` cộng bo ảo QEMU (13 test, 6 trong đó chạy firmware thật trong QEMU) và sửa `SerialVehicleIO` (7 test). `uturn_w46` đạt khi tiến trình pytest tự tắt EcoQoS của Windows |
| 30/09, commit `ebbec83` | `.venv`: 1.380 đạt, 8 bỏ qua (cần torch); `.venv-train`: 1.442 đạt; 0 hỏng | Mã giống `ff4a018`. Toàn bộ test trên commit của đợt bo ảo, cây làm việc sạch, 365 s và 400 s; thêm 4 test EcoQoS; `tests/conftest.py` tắt EcoQoS cho tiến trình pytest (JUnit ghi `ecoqos=off`) |
| 01/10, commit `c03ff94` | `.venv`: 1.380 đạt, 8 bỏ qua (cần torch); `.venv-train`: 1.442 đạt; 0 hỏng | Toàn bộ test trên commit của đợt biên tập tài liệu (mã chỉ khác `ebbec83` ở chữ và cách đếm khung của `qemu_board kiem`; không thêm test), cây làm việc sạch, 349 s và 370 s, JUnit ghi `ecoqos=off` |
| 02/10, commit `d3e1555` | `.venv`: 1.645 đạt, 8 bỏ qua (cần torch); `.venv-train`: 1.707 đạt; 0 hỏng | Lượt mới nhất. Toàn bộ test trên commit của đợt công cụ nghiệm thu (T5, T6, T9–T15, đo EcoQoS của giao diện; thêm 265 test), cây làm việc sạch, 469 s và 483 s, JUnit ghi `ecoqos=off` |

Không cộng các lượt thành tổng test. Lượt 20/09 ghi ở [báo cáo giai đoạn 0](BAO_CAO_GIAI_DOAN_0.md) mục 6; các lượt 25/09 ở [bản tổng hợp `9d68257`](https://github.com/thbn12082/autopark/blob/9d68257/TONG_HOP_DU_AN.md). Các lượt ngày 29/09–02/10 chạy offscreen; tệp kết quả và giới hạn ở [biên bản chuyển máy](autopark/docs/CHUYEN_MAY_BAN.md) mục 2, 3, 6, 8, 9, 11.

`runs/`, dataset đầy đủ, cache, checkpoint và môi trường Python không có trong Git. Bằng chứng nhỏ nằm ở `autopark/docs/evidence/`. Lượt chạy lại các lệnh README trên máy bàn hiện tại ngày 29/09/2026 có tệp gốc ở `autopark/runs/kiem_may_20260929/` (git-ignore) và bản tóm tắt trong Git: [kiem_may_20260929.md](autopark/docs/evidence/chuyen_may_20260929/kiem_may_20260929.md).

Mọi việc tới `ff4a018` đã commit và push; ghi chú “chưa commit” trong các biên bản là trạng thái lúc viết đoạn đó. [Bản tổng hợp `9d68257`](https://github.com/thbn12082/autopark/blob/9d68257/TONG_HOP_DU_AN.md) giữ nhật ký và toàn bộ số liệu bổ sung tới 25/09. Số mục 1–7, 4.1–4.16 và 5.1–5.4 giữ như các bản trước; chi tiết mà các biên bản viết trước 26/09/2026 dẫn theo số mục nhưng không còn ở bản này thì tra ở bản `9d68257`. Tên đoạn và số bước của kế hoạch ("Khi nhận LiDAR", "bước N") trong các biên bản theo [bản kế hoạch `9d68257`](https://github.com/thbn12082/autopark/blob/9d68257/KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md).
