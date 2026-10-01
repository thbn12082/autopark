# Báo cáo giai đoạn 0 — mô phỏng tự đỗ

**Kết luận:** giai đoạn 0 đạt sáu điều kiện chuyển bước trong phạm vi mô phỏng đã kiểm ngày **20/09/2026**. Đây là báo cáo của đợt đó; tiến độ sau này nằm ở [tổng quan hiện tại](TONG_HOP_DU_AN.md).

Biên tập 30/09/2026 theo mã tại `ff4a018` (mã giống `ebbec83`); lần biên tập 26/09/2026 dựng từ hồ sơ tại `9d68257`. Cả hai lần biên tập không thay số liệu của đợt 20/09; lượt chạy lại ngày 29/09/2026 ghi riêng ở khối dưới.

## Trạng thái 30/09/2026

Các mục 1–12 là kết quả đợt 20/09/2026 trên laptop. Sau đợt đó:

- **Mã lập đường và mô phỏng không đổi.** `planning`, `control`, `simulation`, `geometry` và `domain/computation.py` giữ nguyên từ commit đầu `bef5695` (21/09/2026) tới `ff4a018`, chỉ khác chú thích (docstring). Phần thêm sau đợt: nhánh VehicleIO trong `application/session.py` (24/09/2026); tùy chọn `--vehicle-config`, nhãn ca khó và phép đo độ nhạy kích thước xe trong `evaluation` (25/09/2026).
- **Năm phiên mẫu chạy lại trên máy mới.** Từ 29/09/2026 máy phát triển chính là máy bàn Dell Precision 3680 (i9-14900, RTX 4000 Ada) ([biên bản chuyển máy](autopark/docs/CHUYEN_MAY_BAN.md)). Ngày 29/09/2026 trên máy này, `phase0` với mã `b37e9ee` cho năm phiên trùng từng giá trị với đợt 20/09 (`runs/phase0_after_robustness/summary.json`, số ở mục 7): trạng thái, replay khớp, sai số vị trí và hướng, thời gian, số khung video, sự kiện an toàn ([tóm tắt kiểm lại](autopark/docs/evidence/chuyen_may_20260929/kiem_may_20260929.md) mục 2.1). Trong `runs/` của máy bàn không có lượt chạy lại chiến dịch 2.880 ca (mục 6.2).
- **Bộ test hiện tại.** Lượt đầy đủ gần nhất: commit `ebbec83`, cây làm việc sạch, máy bàn, 30/09/2026, offscreen. `.venv`: 1380 đạt, 8 bỏ qua (cần torch), 0 hỏng, 365 s. `.venv-train`: 1442 đạt, 0 hỏng, 400 s. Bộ này gồm test của mọi phần thêm sau 20/09, nên không so số lượng với 220 test ở mục 6.1 ([biên bản chuyển máy](autopark/docs/CHUYEN_MAY_BAN.md) mục 8).
- **EcoQoS.** Test có hạn giờ đo cả cách Windows xếp lịch tiến trình. Từ 30/09/2026 `tests/conftest.py` tắt EcoQoS cho tiến trình pytest (mục 6.1).

## 1. Kết quả tổng quan

- 220/220 test pytest đạt.
- 2.880 trường hợp theo seed không ghi nhận vi phạm các điều kiện đã đặt.
- 40/40 bài planner trong chiến dịch có đường hợp lệ và thực thi hoàn thành.
- Năm phiên mẫu có video, log, cấu hình và replay khớp.

Các con số chỉ áp dụng cho tập phép thử này, không chứng minh mọi bài đỗ đều giải được hoặc xe thật đã hoạt động.

## 2. Phần mềm đã có

| Khối | Chức năng |
|---|---|
| Sa bàn và giao diện | Đặt/kéo/xoay đích, vật cản và vùng chưa quan sát |
| Tìm đường | Hybrid A*/Reeds–Shepp và các bộ tìm đường bổ sung; kiểm quỹ đạo bằng mô phỏng |
| Hình học | Toàn thân xe, phần nhô đầu/đuôi và vùng thân xe quét khi quay |
| Điều khiển | Bám đường tiến/lùi, dừng trước khi đổi chiều |
| Phản hồi giả | Trễ, nhiễu, mất mẫu theo seed; kiểm dữ liệu cũ/hỏng |
| Quản lý phiên | Xem trước, chạy, phanh, dừng, hoàn thành và lỗi |
| Lưu/phát lại | Bản đồ, quỹ đạo, cấu hình, sự kiện, môi trường và snapshot source |

Thông số xe trong [vehicle_default.json](autopark/configs/vehicle_default.json) là giả định mô phỏng, chưa phải số đo MN300.

## 3. Sáu điều kiện chuyển bước

| Điều kiện | Kết luận của đợt 20/09 |
|---|---|
| Kéo/xoay đích; từ chối đích đè vật cản | Đạt trong mô phỏng |
| Tiến/lùi và tuân thủ giới hạn lái | Đạt trong mô phỏng |
| Kiểm va chạm toàn thân xe | Đạt trong phạm vi thử |
| Vật mới vô hiệu đường; dừng trước khi lập đường mới | Đạt trong mô phỏng |
| Xem trước không phát lệnh phần cứng | Đạt |
| Cấu hình/log đủ để tái hiện | Đạt với các phiên đã ghi |

Sơ đồ ở mục 7 nối từng điều kiện với nguồn bằng chứng: pytest, chiến dịch theo seed (mục 6) và năm phiên mẫu. Bằng chứng từng điều kiện: [biên bản giai đoạn 0](autopark/docs/GIAI_DOAN_0.md).

Nhánh VehicleIO được thêm sau đợt này; kết quả 220 test không bao gồm nghiệm thu nhánh đó. Xem [chế độ quan sát](autopark/docs/CHE_DO_QUAN_SAT.md).

## 4. Luồng vận hành

```mermaid
flowchart TD
    E["Chỉnh sa bàn và đặt đích"] --> P["Kiểm đích, tìm và kiểm đường"]
    P --> G{"Có quỹ đạo hợp lệ?"}
    G -->|Không| E
    G -->|Có| R["Sẵn sàng"]
    R --> V["Xem trước riêng trong mô phỏng"]
    V --> R
    R -->|Người dùng bấm Bắt đầu| X["Chạy và nhận phản hồi"]
    X --> C{"Trạng thái phiên?"}
    C -->|Đạt dung sai đỗ| OK["COMPLETED: đỗ xong"]
    C -->|Vật cản hoặc dữ liệu hỏng| S["Hủy đường, phanh về 0"]
    C -->|Va chạm| F["FAULT: ghi lỗi"]
    C -->|Chưa xong, không lỗi| X
    S --> W["STOPPED: chờ đánh giá lại"]
    W -->|Người dùng chọn lại, lấy vị trí vừa dừng| E
```

Sơ đồ rút gọn các nhánh thường gặp trong mô phỏng. Xem trước là tùy chọn trên giao diện; hoàn tất xem trước không tự cho xe chạy. Nhánh hết thời gian chạy được mô tả ngay dưới đây.

Sau sự kiện dừng, hệ thống không tự chạy tiếp. Đường mới lấy xuất phát tại vị trí vừa dừng. `COMPLETED` đòi đạt dung sai; đi hết danh sách điểm chưa đủ. Hết thời gian chạy phải phanh trước khi kết thúc FAULT.

## 5. Các nhóm lỗi đã sửa

| Nhóm lỗi | Hành vi sau sửa |
|---|---|
| Phiên đóng vẫn nhận lệnh | Chặn chạy/lái tay và ngừng mô phỏng sau close |
| Hết thời gian khi đang chạy hoặc phanh | Hoàn tất phanh, giữ kết quả/sự kiện đúng |
| Báo dừng hoặc đổi chiều khi còn tốc độ | Chờ tốc độ về 0 |
| NaN/Infinity trong dữ liệu/lệnh | Từ chối hoặc dừng trước khi đưa vào controller |
| Vật cản/lỗi thứ hai lúc đang phanh | Tiếp tục nhận cập nhật và lưu sự kiện |
| Xuất phát đã va chạm | Giữ cờ collision từ khởi tạo |
| Preview báo hoàn thành ngoài dung sai | Phân biệt hết đường với đỗ đúng |
| Mục tiêu tốc độ vượt cấu hình | Kẹp quỹ đạo và controller, kể cả tốc độ bò |

Lượt hồi quy ban đầu có 25 trường hợp thất bại; nhiều trường hợp cùng thuộc một nhóm lỗi, không phải 25 lỗi độc lập. [Trước sửa](autopark/docs/evidence/robustness_regressions_before.xml), [sau sửa](autopark/docs/evidence/robustness_pytest.xml).

## 6. Kết quả kiểm thử

### 6.1. Pytest

Lượt đầy đủ: **220 đạt**, khoảng 60,23 giây tại lần đo đã lưu. Lượt coverage: 210 đạt, 10 không chọn vì có ngân sách thời gian; mười test này đã chạy trong lượt đầy đủ không gắn tracer.

Ca quay đầu chật `uturn_w46` từng TIMEOUT ở hạn 8 s khi pytest chạy đồng thời với chiến dịch robustness, lúc máy chịu tải CPU (đợt 20/09, laptop; [JUnit lượt có tải](autopark/docs/evidence/robustness_concurrent_load_pytest.xml)). Kết quả tìm đường theo thời hạn phụ thuộc tải CPU và cách Windows xếp lịch tiến trình. Đo ngày 30/09/2026 trên máy bàn, tải CPU 0–12%, tiến trình không có cửa sổ ([do_uturn_w46.txt](autopark/docs/evidence/mo_phong_20260930/ecoqos_30092026/do_uturn_w46.txt)): khi để Windows tự quyết, lần gọi đầu trong mỗi tiến trình đạt (3/3, 4,55–4,57 s), còn 5/5 lần gọi sau hỏng TRACKING_FAILED ở 8,00 s; khi tiến trình tự tắt EcoQoS thì đạt 8/8, 3,61–3,64 s. Cơ chế cụ thể của Windows (dồn sang lõi E hay hạ xung) CHƯA rõ.

Từ 30/09/2026 `tests/conftest.py` tắt EcoQoS cho tiến trình pytest; tệp JUnit ghi `ecoqos=off`, đặt `AUTOPARK_KEEP_ECOQOS=1` để giữ mặc định của Windows. Ứng dụng giao diện và các lệnh đánh giá (`phase0`, `robustness`...) không tự tắt EcoQoS; ảnh hưởng lên chúng CHƯA ĐO. Chi tiết: [biên bản chuyển máy](autopark/docs/CHUYEN_MAY_BAN.md) mục 8, sơ đồ 3.7 trong [Sơ đồ hệ thống](autopark/docs/SO_DO_HE_THONG.md).

### 6.2. Chiến dịch theo seed

| Nhóm | Số trường hợp |
|---|---:|
| Tư thế/hình học | 2.000 |
| Chuyển động/vùng quét | 600 |
| Phiên kín vòng và lỗi giả | 240 |
| Lập đường và thực thi | 40 |
| **Tổng** | **2.880** |

Trong **240 phiên kín vòng**: 25 COMPLETED, 185 STOPPED đúng logic, 30 FAULT do cố tình chèn vật quá gần để phanh. STOPPED và FAULT không phải đỗ thành công. Nhóm **40 ca planner** được thống kê riêng: 40 hoàn thành.

Miền thử giả định: kích thước 0,7–1,4 lần cấu hình; góc lái 22–38°; tốc độ 0,06–0,30 m/s; gia tốc 0,15–0,45 m/s²; giảm tốc 0,25–0,90 m/s²; đổi lái 35–140°/s; bước vật lý 2,5/5/10 ms.

### 6.3. Coverage

| Phạm vi ở thời điểm đo | Dòng | Nhánh |
|---|---:|---:|
| 10 module cốt lõi | 93,93% | 84,25% |
| Toàn package lúc đó | 52,52% | 38,11% |

Không dùng số của lõi để đại diện toàn repo. Coverage cao không chứng minh đã thử đủ đầu vào.

[Báo cáo chi tiết](autopark/docs/KIEM_THU_DO_BEN_GIAI_DOAN_0.md), [JUnit](autopark/docs/evidence/robustness_pytest.xml), [coverage toàn bộ](autopark/docs/evidence/coverage_robustness.json), [coverage lõi](autopark/docs/evidence/coverage_core.json).

## 7. Năm phiên mẫu và replay

**Sáu điều kiện, nguồn bằng chứng và vòng replay.** Sơ đồ nối từng điều kiện ở mục 3 với nguồn bằng chứng của đợt 20/09; nhánh `phase0` là năm phiên của mục này. Mỗi phiên được xuất gói (`export_run`), phát lại ngay (`replay_run`) và chỉ được vẽ video khi phát lại khớp.

```mermaid
flowchart TD
    G["Sáu điều kiện chuyển bước giai đoạn 0, kế hoạch mục 4"]
    G --> C1["1. Kéo, xoay đích, từ chối đích đè vật cản"]
    G --> C2["2. Tiến, lùi, giữ giới hạn lái và đổi chiều"]
    G --> C3["3. Kiểm va chạm toàn thân và vùng quét"]
    G --> C4["4. Vật mới hủy đường, dừng trước khi lập lại"]
    G --> C5["5. Xem trước không phát lệnh phần cứng"]
    G --> C6["6. Cấu hình và log đủ để chạy lại"]
    C1 --> PT["pytest 220 trên 220 đạt"]
    C2 --> PT
    C3 --> PT
    C4 --> PT
    C5 --> PT
    C6 --> PT
    C3 --> ROB["robustness 2.880 ca theo seed, 0 vi phạm bất biến"]
    C4 --> ROB
    C2 --> P0["phase0: 5 phiên parking, reverse, noisy, obstacle, data_loss"]
    C4 --> P0
    C6 --> P0
    P0 --> EX["export_run: cấu hình và quỹ đạo, telemetry, sự kiện, kết quả, môi trường, source.zip"]
    EX --> RP["replay_run: chạy lại quỹ đạo đã lưu, bơm lại sự kiện đúng bước vật lý, không gọi planner"]
    RP --> EQ{"Trạng thái phiên, tư thế và vận tốc cuối, va chạm, quãng đường, telemetry khớp?"}
    EQ -->|Có| VID["Video mp4 có dòng SIMULATION ONLY và ảnh khung cuối"]
    EQ -->|Không| ERR["Báo lỗi, kiểm lại phiên bản mã và môi trường, không nhận làm bằng chứng"]
    PT --> KQ["ĐẠT ở mức mô phỏng, laptop i7-12700H, 20/09/2026"]
    ROB --> KQ
    VID --> KQ
    KQ -.-> NO["Chưa chứng minh: số đo MN300, phản hồi thật, quãng phanh, E-stop, tự đỗ thật"]
    classDef daco fill:#dff0d8,stroke:#3c763d,color:#1b3a1b
    classDef giaLap fill:#fcf8e3,stroke:#8a6d3b,color:#4d3b12
    classDef chuaLam fill:#f2dede,stroke:#a94442,color:#4d1a1a,stroke-dasharray: 4 3
    class PT,ROB,P0,KQ,VID giaLap
    class NO chuaLam
```

Xanh: đã có và đã kiểm/đo · Vàng: chỉ trong mô phỏng/giả lập · Đỏ viền đứt: chưa làm hoặc chưa thử trên thiết bị.

Replay không gọi planner tìm một đường mới. Luồng này dành cho phiên mô phỏng giai đoạn 0; không áp dụng cho phiên VehicleIO (`replay_run` từ chối phát lại lần chạy qua VehicleIO). Mã: [phase0.py](autopark/autopark/evaluation/phase0.py), [run_store.py](autopark/autopark/storage/run_store.py). Xem thêm sơ đồ 3.6 trong [Sơ đồ hệ thống](autopark/docs/SO_DO_HE_THONG.md).

| Phiên | Kết quả | Thời gian mô phỏng | Sai số vị trí cuối | Replay |
|---|---|---:|---:|---|
| parking | COMPLETED | 20,265 s | 8,92 mm | Khớp |
| reverse | COMPLETED | 12,145 s | 8,52 mm | Khớp |
| noisy | COMPLETED | 12,265 s | 4,78 mm | Khớp |
| obstacle | STOPPED, không va chạm | 1,345 s | Không chấm tới đích | Khớp |
| data_loss | STOPPED, không va chạm | 1,490 s | Không chấm tới đích | Khớp |

Phiên noisy: trễ 40 ms, nhiễu vị trí 2 mm và yaw 0,2°, mất mẫu 2%, seed 42.

Dữ liệu đầy đủ ở `autopark/runs/phase0_after_robustness/`, không nằm trong Git; ngày 30/09/2026 thư mục này có trên máy bàn. Replay dùng quỹ đạo lưu sẵn để tránh phụ thuộc ngân sách tìm đường mới.

[Ảnh đang chạy](autopark/docs/evidence/ui_running.png), [ảnh đã dừng](autopark/docs/evidence/ui_stopped.png).

## 8. Dữ liệu công khai

Giai đoạn này đã chuẩn bị danh mục, công cụ tải/kiểm và dữ liệu cho bước AI tiếp theo. Đó không phải bằng chứng AI đã hoạt động trong mô phỏng.

[Danh mục dataset](autopark/datasets/DANH_MUC_DATASET.md), [trạng thái và cách kiểm](autopark/datasets/TAI_VA_KIEM_TRA.md).

## 9. AI nằm ngoài kết quả nghiệm thu giai đoạn 0

Ngày 20/09 chưa có lượt huấn luyện hoàn chỉnh. Baseline được huấn luyện từ 21/09; báo cáo riêng ở [HUAN_LUYEN.md](HUAN_LUYEN.md).

Nghiên cứu AI sử dụng **[Valeo WoodScape Dataset](https://github.com/valeoai/WoodScape)**. [Hồ sơ giấy phép](autopark/docs/GIAY_PHEP_DU_LIEU.md).

## 10. Môi trường và mã nguồn

Máy đợt mô phỏng: Windows 11, Python 3.12.10, i7-12700H, RTX 3050 Ti Laptop 4 GB. [Môi trường ghi lúc đo](autopark/docs/evidence/environment.json). Laptop này nay là máy trình diễn, nộp đồ án ([MAY_NOP_DO_AN.md](autopark/docs/MAY_NOP_DO_AN.md)); máy phát triển từ 29/09/2026 là máy bàn (khối "Trạng thái 30/09/2026").

Mã chính: [session](autopark/autopark/application/session.py), [simulation](autopark/autopark/simulation/), [planning](autopark/autopark/planning/), [tracker](autopark/autopark/control/tracker.py), [oracle va chạm](autopark/autopark/evaluation/collision_oracle.py).

Đơn vị mét/giây/radian; pose ở tâm trục sau, x trước, y trái, yaw dương ngược chiều kim đồng hồ.

## 11. Cách tự kiểm chứng

Cài môi trường theo [hướng dẫn chạy](autopark/README.md). Chạy từ thư mục `autopark` của repo, thư mục có `pyproject.toml` (trên máy bàn: `D:\xetulai\autopark\autopark`):

```powershell
./.venv/Scripts/python.exe -X utf8 -m pytest
./.venv/Scripts/python.exe -X utf8 -m autopark.evaluation.phase0 --out runs/phase0_kiem_lai
./.venv/Scripts/python.exe -X utf8 -m autopark.evaluation.replay runs/phase0_kiem_lai/obstacle
./.venv/Scripts/python.exe -X utf8 -m autopark.evaluation.robustness --out runs/robustness_kiem_lai
```

Chạy tuần tự, chọn thư mục mới. Bộ test hiện tại đã lớn hơn 220 (lượt gần nhất: khối "Trạng thái 30/09/2026"); chạy lại trên mã hiện tại là một lượt kiểm mới, không tái tạo nguyên số lượng test ngày 20/09. Lệnh `phase0` đã chạy lại ngày 29/09/2026 trên máy bàn và cho đúng năm kết quả của mục 7.

## 12. Giới hạn và bước tiếp theo

Chưa chứng minh: thông số MN300, phản hồi/định vị thật, quãng phanh, E-stop, tự đỗ thật, AI sa bàn. Vật xuất hiện quá gần có thể gây FAULT. Preview dùng rollout lý tưởng, chưa thể hiện đủ lỗi phần cứng.

Giữ các test làm hồi quy; khi đo được MN300 thì thay cấu hình và chạy lại (`phase0` và `robustness` nhận `--vehicle-config` từ 25/09/2026). Tiếp tục kiểm cảm biến theo [kế hoạch](KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md).

[Báo cáo trước đợt biên tập 26/09](https://github.com/thbn12082/autopark/blob/9d68257/BAO_CAO_GIAI_DOAN_0.md) lưu đầy đủ hồ sơ lịch sử. Số mục 1–12 giữ như bản đó; chi tiết mà tài liệu khác dẫn theo số mục nhưng đã lược khi biên tập (ví dụ giới hạn của mô hình xe ở mục 12) tra ở bản đó. Bản ngay trước đợt biên tập 30/09: [ff4a018](https://github.com/thbn12082/autopark/blob/ff4a018/BAO_CAO_GIAI_DOAN_0.md).
