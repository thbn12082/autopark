# Cài đặt và chạy AutoPark

[Cần biết tiến độ?](../TONG_HOP_DU_AN.md) · [Tài liệu kỹ thuật](docs/README.md) · [Sơ đồ hệ thống](docs/SO_DO_HE_THONG.md)

Biên tập 30/09/2026 theo mã tại `ff4a018` (mã giống `ebbec83`); cây làm việc lúc viết có thêm sửa chưa commit: sửa chữ (docstring, chú thích trong mã, một tooltip trong `ui/main_window.py`, mô tả gói trong `pyproject.toml`; không đổi hành vi) và cách đếm khung của `python -m autopark.transport.qemu_board kiem` (mục 9). Lệnh được đối chiếu với mã và script. Bản trước đợt này: [README tại `ff4a018`](https://github.com/thbn12082/autopark/blob/ff4a018/autopark/README.md); bản trước đợt 26/09/2026, còn các lệnh và nhật ký cũ: [README tại `9d68257`](https://github.com/thbn12082/autopark/blob/9d68257/autopark/README.md).

Cập nhật 02/10/2026 theo mã của đợt công cụ nghiệm thu (commit `d3e1555`): lệnh của các công cụ mới ở mục 3 (dấu đồng bộ video–log, giới hạn số lần đổi chiều), mục 4 (phát lại log lần chạy qua VehicleIO, chấm một lần chạy, diễn tập tiêm lỗi, đo EcoQoS của giao diện), mục 7, 8 (dấu đồng bộ của bàn thử, camera ngoài hub) và mục 9 (nút Xóa lỗi bo). Các công cụ nghiệm thu này mới kiểm bằng test: bo mô phỏng, cổng serial giả, camera giả, giao diện offscreen, bản ghi phát lại; chưa chạy với LiDAR, camera hay bo thật. Công cụ đo EcoQoS mở giao diện thật trên máy; kết quả đo ghi ở [biên bản chuyển máy](docs/CHUYEN_MAY_BAN.md).

Cập nhật lần hai cùng ngày theo mã đợt 2 (gộp trên `63017a5`, chưa commit lúc viết, nay là commit `470abb3`; người dùng giao quyết định 02/10/2026 ("làm hết"), theo đề xuất): ứng dụng và công cụ đo tự tắt EcoQoS (mục 4, 11); xe nghiệm thu `--vehicle-config` và tệp sa bàn nghiệm thu `scenarios/nghiem_thu` (mục 3, 4); bo ảo QEMU trong giao diện và nguồn tư thế (mục 9); ghi cảm biến trong phiên đỗ T3 (mục 4, 7); tham chiếu trên cao T4 (mục 4, 8); nguồn tư thế LiDAR và dựng bản đồ T2 (mục 8, 9); đo vòng điều khiển 50 Hz khi thu nhỏ cửa sổ (mục 4); cấu trúc mã và bảng gỡ rối (mục 10, 11). Phần mềm mới của đợt 2 chỉ kiểm bằng test, mô phỏng, bo ảo QEMU hay ảnh tổng hợp; với LiDAR, camera, camera trên cao hay bo thật: CHƯA THỬ, trừ các lượt chạy thiết bị ghi ở đoạn dưới.

Máy phát triển chính từ 29/09/2026 là máy bàn Dell Precision 3680 (i9-14900, RTX 4000 Ada 20 GB, Windows 11), repo ở `D:\xetulai\autopark` ([biên bản chuyển máy](docs/CHUYEN_MAY_BAN.md)); số đo mới trong tệp này làm trên máy đó. Trên máy này đã cài lại hai môi trường (29/09/2026) và chạy toàn bộ test (lượt mới nhất ở mục 4). Ngày 29/09/2026 lúc 15:08–15:19 (mã `b37e9ee`) đã chạy lại: `phase0` (mục 4); `verify_cache`, chấm val, dự đoán, train 1 epoch (mục 6); một bản ghi LiDAR 10 s; bàn thử bốn camera + LiDAR + AI có ghi rồi phát lại (mục 7); lệnh kiểm máy mới `rig.may_moi` ([tóm tắt](docs/evidence/chuyen_may_20260929/kiem_may_20260929.md)). Ngày 02/10/2026 trên máy bàn, không người ở cạnh: `video.camera_bench list` và `measure` (bốn camera 60 s), `fusion.demo` 30 s với LiDAR thật, `rig.bench` ghi thử 60 s và chạy dài 30 phút có ghi phiên (kịch bản LD-1, đủ 1800 s ở lần 3, sau khi sửa mã đọc C1); đo vòng điều khiển 50 Hz khi thu nhỏ cửa sổ; lần chạy ứng dụng với bo ảo QEMU bằng script ([biên bản chuyển máy](docs/CHUYEN_MAY_BAN.md) mục 12–14). Laptop trình diễn mới chạy mô phỏng giai đoạn 0 ([MAY_NOP_DO_AN.md](docs/MAY_NOP_DO_AN.md)).

Nghiên cứu nhận thức sử dụng **[Valeo WoodScape Dataset](https://github.com/valeoai/WoodScape)**. [Hồ sơ giấy phép](docs/GIAY_PHEP_DU_LIEU.md).

## 1. Chọn môi trường và thư mục

| Nhu cầu | Môi trường | Cần thêm | Hiện trạng 02/10/2026 |
|---|---|---|---|
| Mô phỏng tự đỗ | `.venv` | Không cần cảm biến/AI | Chạy trên máy tính; giai đoạn 0 đạt sáu điều kiện chuyển bước ở mức mô phỏng (20/09/2026, [báo cáo](../BAO_CAO_GIAI_DOAN_0.md)); từ 02/10/2026 có xe nghiệm thu 0,10 m/s và 9 tệp sa bàn nghiệm thu mức MP (mục 3) |
| LiDAR/camera không chạy AI | `.venv` | Thiết bị hoặc bản ghi theo lệnh | Đã đo với RPLIDAR C1 và bốn camera thật trên bàn thử, lần gần nhất 02/10/2026 trên máy bàn ([biên bản chuyển máy](docs/CHUYEN_MAY_BAN.md) mục 2, 12) |
| AI, huấn luyện, bàn thử có AI | `.venv-train` | Checkpoint, dữ liệu/camera, cấu hình GPU phù hợp | Mô hình tham chiếu đã huấn luyện và chấm trên WoodScape ([HUAN_LUYEN.md](../HUAN_LUYEN.md)); AI chạy trên bàn thử và bản ghi; trong phiên đỗ AI chưa tạo vật cản từ camera thật vì chưa camera nào được hiệu chuẩn ([AI camera](docs/AI_DIEU_KHIEN_XE.md)) |
| Firmware ESP32-S3 | C++ (g++, cmake), PlatformIO | Mục 9 dưới đây; [hướng dẫn firmware](firmware/esp32_vehicle/README.md) | Lõi C++ khớp bản tham chiếu Python trên máy tính; cả firmware đã biên dịch cho ESP32-S3 (29/09/2026); CHƯA nạp, CHƯA chạy trên bo (chưa có bo) |
| Bo ảo QEMU (firmware thật trong giả lập) | `.venv` + QEMU của Espressif + PlatformIO, đường dẫn ở `configs/thiet_bi.json` | Mục 9 dưới đây; [mô phỏng firmware](docs/MO_PHONG_FIRMWARE.md) mục 1, 1.1 | Firmware thật chạy trong QEMU, dùng từ dòng lệnh, pytest và giao diện (02/10/2026: thẻ Bo điều khiển, nút Khởi động bo ảo, cả phiên đỗ với tốc độ/góc lái/tư thế từ xe mô phỏng phía laptop); chỉ là giả lập (mức MP) |

Chưa có xe thật: MN300, ESP32-S3, IMU, ToF, encoder/AS5600, phần nguồn và nút dừng đều chưa nhận ([kiểm kê phần cứng](docs/hardware_inventory.md)), nên chưa lệnh nào trong tệp này điều khiển bo hay xe thật.

Python tối thiểu 3.11; môi trường tham chiếu Windows dùng Python 3.12.10. Thư viện cố định trong `requirements-phase0.lock` và `requirements-train.lock`.

**Chạy lệnh tại thư mục chứa README này, `pyproject.toml` và `run_app.py`** (trừ lệnh cmake và PlatformIO của firmware, chạy trong `firmware/esp32_vehicle`):

```text
autopark/                        ← gốc repository
├── README.md
└── autopark/                    ← chạy lệnh ở đây
    ├── pyproject.toml
    ├── run_app.py
    ├── autopark/                ← package Python
    └── firmware/esp32_vehicle/  ← lệnh cmake và PlatformIO (mục 9)
```

Các lệnh dưới dùng PowerShell, gọi trực tiếp Python của từng môi trường nên không cần activate.

**Chọn đường chạy phù hợp:**

```mermaid
flowchart TD
    A["Đứng tại thư mục có pyproject.toml"] --> B{"Muốn chạy gì?"}
    B -->|Mô phỏng tự đỗ| C["Cài .venv bằng cai_dat.cmd"]
    C --> D["Mở chay_app.cmd"]
    B -->|LiDAR hoặc camera, không AI| E["Cài .venv, chọn thiết bị hoặc bản ghi"]
    E --> F["Theo mục 7"]
    B -->|AI hoặc huấn luyện| G["Cài .venv-train bằng cai_dat_train.cmd"]
    G --> H{"Chạy mô hình có sẵn hay train?"}
    H -->|Có sẵn| I["Chép checkpoint, chuẩn bị ảnh, camera hoặc bản ghi"]
    H -->|Train| J["Chuẩn bị dataset và xác minh cache"]
    I --> K["Chạy mục 6 hoặc 7, kiểm hiệu chuẩn nếu tạo vật cản"]
    J --> L["Theo HUAN_LUYEN.md"]
    B -->|Firmware hoặc bo ảo| M["Cài g++, cmake và Ninja trên PATH, cài PlatformIO và QEMU rồi ghi đường dẫn hai công cụ này vào configs/thiet_bi.json"]
    M --> N["Theo mục 9: kiểm vector, test host, biên dịch, chạy bo ảo"]
    N -.->|chưa có bo| O["Nạp và chạy trên ESP32-S3 thật"]
    classDef daco fill:#dff0d8,stroke:#3c763d,color:#1b3a1b
    classDef giaLap fill:#fcf8e3,stroke:#8a6d3b,color:#4d3b12
    classDef chuaLam fill:#f2dede,stroke:#a94442,color:#4d1a1a,stroke-dasharray: 4 3
    class O chuaLam
```

Đỏ viền đứt: chưa làm hoặc chưa thử trên thiết bị. Các ô không tô màu là bước chọn đường chạy, không nói về trạng thái.

## 2. Cài và mở mô phỏng

Cách nhanh: chạy `cai_dat.cmd` rồi `chay_app.cmd`. `cai_dat.cmd` gọi `kiem_venv.cmd` chạy thử Python của `.venv` có sẵn; venv chép từ máy khác mà không chạy được thì được đổi tên thành `.venv.hong-tu-may-cu` rồi tạo mới (tên đó đã có thì script dừng và báo).

Hoặc chạy tuần tự:

```powershell
python --version
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-phase0.lock
./.venv/Scripts/python.exe -m pip install -e . --no-deps
./.venv/Scripts/python.exe -X utf8 run_app.py
```

Nếu `python --version` không chạy được, cài/sửa đường dẫn Python trước. Cài thư viện cần mạng. `requirements-phase0.lock` có cả `pyserial` để đọc LiDAR. Mô phỏng cơ bản không cần checkpoint AI.

Máy mới, hoặc thư mục chép từ máy khác: thứ tự đủ các bước (hai môi trường, cổng LiDAR, công cụ firmware, test, kiểm máy) ở sơ đồ "Chuẩn bị một máy mới" trong mục 5.

## 3. Thử một lượt đỗ

1. Đặt/xoay đích; đích đè vật cản hoặc làm thân xe vượt sa bàn bị từ chối.
2. **Tìm đường đỗ** → **Xem trước** → kết thúc xem trước → **Bắt đầu đỗ**.
3. Thử **Vật cản giả** hoặc **Mất dữ liệu** khi xe đang chạy.
4. Khi đã dừng, bấm **Chọn lại vị trí**, chọn lại vị trí/đích và lập đường mới.
5. **Lưu phiên…** trước khi đặt lại phiên (sau khi xe dừng: từ 02/10/2026 nút khóa khi xe đang chạy).

Mặc định xe chạy ở nhánh mô phỏng giai đoạn 0; các nhánh khác ở mục 9.

Dòng đường của cockpit cảnh báo khi đường có hơn 7 lần đổi chiều. `run_app.py <kịch bản> --max-cusps N` (hay `chay_app.cmd <kịch bản> --max-cusps N`) từ chối **Bắt đầu đỗ** khi đường có hơn N lần đổi chiều, trước mọi lệnh tới bo; `--warn-cusps N` đổi mức cảnh báo. Đây là công cụ T12 của [kịch bản nghiệm thu](docs/KICH_BAN_NGHIEM_THU.md) mục 7; giới hạn CHƯA CHỐT nên mặc định không chặn. Từ 02/10/2026 `run_app.py` báo lỗi (mã thoát 2) với tham số lạ.

Xe nghiệm thu (02/10/2026): `run_app.py <kịch bản> --vehicle-config configs/vehicle_nghiem_thu.json` (hay `chay_app.cmd <kịch bản> --vehicle-config configs\vehicle_nghiem_thu.json`) chạy với xe như `vehicle_default.json` nhưng tối đa 0,10 m/s (N-V1, ĐỀ XUẤT – CHỜ CHỐT; người dùng giao quyết định 02/10/2026). Planner vẫn đặt 0,15 m/s; quỹ đạo và bộ bám kẹp ở 0,10. Thẻ "Xe" (ngăn **Sa bàn +**) có ô **Cấu hình xe** để đổi xe khi đang chỉnh hoặc sẵn sàng. Xe đã chọn được giữ khi **Mở…** kịch bản khác, và bo mô phỏng tự chọn theo tệp xe (`configs/vehicle_io_sim_nghiem_thu.json` đi cùng xe nghiệm thu). Tệp xe thiếu hay hỏng thì thoát mã 2 trước khi mở cửa sổ. Đã chọn xe khác tệp xe của kịch bản thì **Lưu** ghi tệp xe đó vào kịch bản; muốn giữ nguyên tệp trong kho thì dùng **Lưu thành…**. Với bo ảo QEMU hay ESP32-S3, xe nghiệm thu bị từ chối ở VehicleIO (firmware biên dịch cứng 300 mm/s; suy ra từ mã, chưa chạy thử; mục 9).

```powershell
./.venv/Scripts/python.exe -X utf8 run_app.py scenarios/sa_ban_3x2_hai_hop.json --vehicle-config configs/vehicle_nghiem_thu.json
```

*(Cập nhật 02/10/2026)* Tệp sa bàn gắn kịch bản nghiệm thu (trường `acceptance`; bộ `scenarios/nghiem_thu/do1.json` … `do6.json`, mức MP) tự dùng giới hạn đổi chiều của kịch bản đó trong `configs/nguong_nghiem_thu.json` (N-D6 (b): ≤ 2 ở DO-1/2/3a/4a, ≤ 7 ở DO-3b/4b/5/6, DO-3c chỉ báo số; ĐỀ XUẤT – CHỜ CHỐT) và xe `configs/vehicle_nghiem_thu.json`. `--max-cusps N` chỉ siết thêm. Thẻ "Kịch bản" hiện giới hạn; "Lưu thành…" giữ thẻ. Ví dụ:

```powershell
./.venv/Scripts/python.exe -X utf8 run_app.py scenarios/nghiem_thu/do3b.json
```

Khi quay video để đối chiếu với log (R3, R7 của kịch bản nghiệm thu): bấm **F8** hoặc nút **Dấu đồng bộ · F8** trước **Bắt đầu đỗ** và sau khi xe dừng. Mỗi dấu nháy một ô trắng có số trên cửa sổ trong 0,5 s và ghi một dòng có `perf_counter` vào tệp `runs/sync_marks/<giờ>_ui_app.csv`; **Lưu phiên…** ghi thêm `<tên>_sync_marks.csv` cạnh tệp CSV ([kịch bản nghiệm thu](docs/KICH_BAN_NGHIEM_THU.md) mục 2.5). Nút khóa khi xe đang chạy. Dấu đồng bộ (T14, 02/10/2026) mới kiểm offscreen; với màn hình và camera thật CHƯA THỬ, độ trễ hiển thị CHƯA ĐO.

Mở kịch bản vùng chưa quan sát:

```powershell
./.venv/Scripts/python.exe -X utf8 run_app.py scenarios/giai_doan_0_unknown.json
```

Vùng chưa quan sát được chặn như vật cản. `configs/vehicle_default.json` chứa thông số giả định, chưa phải số đo MN300.

## 4. Test, bằng chứng và replay

Chạy toàn bộ bộ test (`offscreen`: Qt không mở cửa sổ):

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
./.venv/Scripts/python.exe -X utf8 -m pytest
Remove-Item Env:QT_QPA_PLATFORM
```

- Test cần torch được bỏ qua trong `.venv`; chạy cùng lệnh bằng `./.venv-train/Scripts/python.exe` để gồm cả chúng.
- Bộ test gồm cả firmware: 2 test host của lõi C++ (`tests/test_transport_firmware_host.py`, cần cmake và trình biên dịch C++ trên PATH) và `tests/test_firmware_qemu.py` của bo ảo (14 test, 7 trong đó chạy firmware thật trong QEMU, cần công cụ khai trong `configs/thiet_bi.json`; 02/10/2026 thêm phiên đỗ qua bo ảo). Máy thiếu công cụ thì các test cần nó tự bỏ qua: 2 test host, hoặc 7 test chạy QEMU (mục 9).
- EcoQoS: trên Windows 11, tiến trình pytest không có cửa sổ (ví dụ chạy nền) có thể chạy chậm tới ≈ 3 lần dù máy gần rảnh, đủ làm hỏng test có hạn giờ (dấu `planner_budget`; đo 30/09/2026). Vì vậy từ 30/09/2026 `tests/conftest.py` tắt EcoQoS cho tiến trình pytest; tiến trình con mà test mở thì không (riêng QEMU của bo ảo: `QemuBoard` tự tắt EcoQoS cho tiến trình QEMU). Từ 02/10/2026 các tiến trình sau cũng tự tắt EcoQoS cho chính mình lúc khởi động, cùng hàm `apply_ecoqos_policy` của `autopark/power_throttling.py` (cửa sổ thu nhỏ làm lập đường hết hạn, [biên bản](docs/CHUYEN_MAY_BAN.md) mục 10, 10.1; người dùng giao quyết định 02/10/2026):
  - ứng dụng: `run_app.py`, `ui.lidar_app`, `ui.rig_app`, `ui.calib_app`, `ui.roi_app`, `lidar.live_view`, `ui.overhead_app`; giao diện hiện nhãn "EcoQoS: tắt" ở góc phải thanh trạng thái;
  - công cụ mở thiết bị, chạy theo hạn giờ hay đo thời gian: `rig.bench`, `rig.may_moi`, `camera_bench`, `lidar.bench`, `video.overhead_record`, `evaluation.bench`, `sensitivity`, …; công cụ in hoặc ghi khóa `ecoqos` vào tệp kết quả. Đủ 27 điểm vào và 29 điểm vào không gọi (kèm lý do) ở `tests/test_ecoqos_policy.py`.

  Đặt `AUTOPARK_KEEP_ECOQOS=1` để giữ mặc định của Windows, ví dụ khi muốn đo đúng điều kiện đó; một biến cho pytest, ứng dụng và công cụ, chỉ đúng giá trị `1` (cmd: `set AUTOPARK_KEEP_ECOQOS=1`; PowerShell: `$env:AUTOPARK_KEEP_ECOQOS = "1"`). Trạng thái đọc lại được ghi vào tệp JUnit (thuộc tính `ecoqos` của testsuite: `off`, `system`, `on` hoặc `unknown`) và, khi chạy thêm `-v`, vào dòng đầu báo cáo.
- Vẫn chạy test có hạn giờ khi máy rảnh, tách khỏi các chiến dịch tải CPU và không kèm coverage (mô tả dấu `planner_budget` trong `pyproject.toml` chỉ ghi phần coverage: `run without coverage tracing`).
- Thư mục tạm: `pyproject.toml` đặt `tmp_path_retention_policy = "failed"`, nên pytest xóa `tmp_path` của test đạt ngay khi test xong; lượt có test hỏng chỉ còn thư mục của test hỏng và của fixture dùng chung (`tmp_path_factory`). Giữ hết thì mỗi lượt `.venv-train` để lại ≈ 2,1 GB trong `%TEMP%`. Cần giữ để xem lại thì thêm `-o tmp_path_retention_policy=all`.
- `chay_test.cmd` gọi `.venv\Scripts\python.exe -m pytest` nhưng không đặt `offscreen` và không có `-X utf8`; muốn giống các lượt ghi trong biên bản thì dùng lệnh trên.

Chi tiết và số đo: [biên bản chuyển máy](docs/CHUYEN_MAY_BAN.md) mục 8, 10.1; sơ đồ 3.7 (hạn giờ và EcoQoS) trong [Sơ đồ hệ thống](docs/SO_DO_HE_THONG.md).

**Ghi số test làm bằng chứng.** Commit mã trước; chạy toàn bộ test trên chính commit đó với cây làm việc sạch; lưu JUnit có mã commit vào `docs/evidence/<đợt>/`; cuối cùng ghi số vào tài liệu bằng một commit riêng. Thay `<đợt>` và `<mã commit>` trước khi chạy:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
./.venv/Scripts/python.exe -X utf8 -m pytest -p no:cacheprovider --junitxml docs/evidence/<đợt>/pytest_venv_<mã commit>.xml
./.venv-train/Scripts/python.exe -X utf8 -m pytest -p no:cacheprovider --junitxml docs/evidence/<đợt>/pytest_venv_train_<mã commit>.xml
Remove-Item Env:QT_QPA_PLATFORM
```

Ngày 30/09/2026 bước này chạy bằng script [chay_tren_commit.py](docs/evidence/mo_phong_20260930/chay_tren_commit.py): script chạy thêm `qemu_board kiem` và 10 lượt test bo ảo, rồi ghi thẳng vào `docs/evidence/mo_phong_20260930/`. Ngày 01/10/2026 dùng bản sửa của script đó, [docs/evidence/bien_tap_20261001/chay_tren_commit.py](docs/evidence/bien_tap_20261001/chay_tren_commit.py): ngày lấy lúc chạy, thư mục kết quả là tham số (`.venv\Scripts\python.exe -X utf8 docs\evidence\bien_tap_20261001\chay_tren_commit.py <commit> <thư mục kết quả>`). Sơ đồ 9.2 trong [Sơ đồ hệ thống](docs/SO_DO_HE_THONG.md).

Lần chạy toàn bộ gần nhất: 06/10/2026, máy bàn Dell Precision 3680 (i9-14900, RTX 4000 Ada 20 GB, Windows 11), bằng bản sửa của script ở trên (offscreen), commit `470abb3` của đợt 2, cây làm việc sạch: `.venv` 2105 đạt, 10 bỏ qua (cần torch), 0 hỏng, 640 s, nhưng tiến trình thoát mã 0xC0000005 sau khi đã ghi JUnit (có lẽ lúc tắt Python; chưa rõ nguyên nhân); `.venv-train` 2168 đạt, 1 hỏng, 683 s: `test_parking_session_through_qemu_board` bị từ chối START vì test trước để bo ảo còn dốc tham chiếu tốc độ về 0 (cổng START từ chối đúng; sửa test ở đợt sau); thêm 462 test so với lượt trên `d3e1555` (02/10/2026). Cả hai tệp JUnit ghi `ecoqos=off`. Số test đổi theo mã; tệp kết quả và các lượt trước ở [biên bản chuyển máy](docs/CHUYEN_MAY_BAN.md) mục 2, 3, 6, 8, 9, 11, 15.

*(Cập nhật 06/10/2026: lỗi thoát 0xC0000005 của `.venv` được điều tra ở [biên bản chuyển máy](docs/CHUYEN_MAY_BAN.md) mục 16; thủ phạm vẫn CHƯA RÕ. Lượt chạy lại trên commit sau dùng bản mới của script, [docs/evidence/su_co_thoat_20261006/chay_tren_commit.py](docs/evidence/su_co_thoat_20261006/chay_tren_commit.py), cùng hai tham số `<commit> <thư mục kết quả>`: đặt ErrorMode 0x8001 để crash có sự kiện WER và minidump (LocalDumps bật trên máy bàn; dump mới chép sang `runs/dump/`), chạy pytest với `-X faulthandler`, giữ đầu ra từng lượt, ghi mã thoát dạng hex, có hạn giờ, ghi HEAD và độ sạch của cây; `--chi-test tests/test_geometry.py` để kiểm script trong vài giây. Các bản cũ giữ nguyên.)*

Tạo phiên mẫu rồi phát lại:

```powershell
./.venv/Scripts/python.exe -X utf8 -m autopark.evaluation.phase0 --out runs/thu_nghiem_moi
./.venv/Scripts/python.exe -X utf8 -m autopark.evaluation.replay runs/thu_nghiem_moi/obstacle
```

Dùng thư mục đầu ra mới cho từng lượt. Phiên lưu cấu hình, quỹ đạo, sự kiện, telemetry, kết quả, snapshot source, ảnh/video. Replay dùng quỹ đạo đã lưu. Ngày 29/09/2026 trên máy bàn hiện tại (mã `b37e9ee`), `phase0` cho năm phiên trùng từng giá trị với đợt 20/09/2026, replay khớp cả năm ([tóm tắt](docs/evidence/chuyen_may_20260929/kiem_may_20260929.md) mục 2.1); kết quả vẫn chỉ là mô phỏng.

Kiểm mở rộng:

```powershell
./.venv/Scripts/python.exe -X utf8 -m autopark.evaluation.robustness --out runs/kiem_thu_moi
```

[Giải thích kết quả](../BAO_CAO_GIAI_DOAN_0.md). Replay trên tái mô phỏng các gói giai đoạn 0 (nhánh SIM). Gói của lần chạy qua VehicleIO dùng cùng lệnh nhưng là phát lại log (mục con dưới).

### Công cụ nghiệm thu (thêm 02/10/2026)

Ba công cụ đầu dưới đây làm theo bảng T1–T15 của [kịch bản nghiệm thu](docs/KICH_BAN_NGHIEM_THU.md) mục 7. Chúng mới kiểm bằng test: bo mô phỏng, cổng serial giả, camera giả, giao diện offscreen, bản ghi phát lại; chưa dùng với LiDAR, camera hay ESP32-S3 thật (bo ảo QEMU qua giao diện có từ đợt 2, mục 9). Đợt 2 (02/10/2026) thêm các đoạn tệp sa bàn nghiệm thu (T12 theo kịch bản), tham chiếu trên cao R1 (T4) và ghi cảm biến trong phiên đỗ (T3), cùng giới hạn đó (T4 mới kiểm trên ảnh tổng hợp). Hai công cụ cuối đo EcoQoS và vòng điều khiển 50 Hz của ứng dụng giao diện; *(cập nhật 02/10/2026: từ ngày đó ứng dụng tự tắt EcoQoS, xem gạch EcoQoS ở trên)*.

**Phát lại log lần chạy qua VehicleIO (T9).** Sau một lần chạy ở nhánh VehicleIO hoặc Quan sát với bo mô phỏng, **Lưu phiên…**/**Xuất log CSV…** ghi tệp CSV, thư mục `<tên>_vehicle_io/` (tám tệp: `commands.csv`, `telemetry.csv`, `events.csv`, `start_refusals.csv`, `board_actions.csv`, `poses.csv`, `clock.csv`, `link.json`) và gói `<tên>_<thời điểm>/` có thêm `vehicle_io/`. Phát lại gói bằng cùng lệnh replay:

```powershell
./.venv/Scripts/python.exe -X utf8 -m autopark.evaluation.replay <thư mục gói>
```

Lệnh chạy lại cùng phần mềm (`Session`, `VehicleLink`, bộ bám) trên đầu vào đã ghi rồi so lệnh, sự kiện (kể cả dòng `session_stop`) và kết quả với bản ghi; nó in báo cáo tiếng Việt và thoát mã 0 = KHỚP, 1 = KHÁC, 2 = không phát lại được (thiếu `vehicle_io/`, log ghi trước khi có băng phát lại, gói hỏng), 3 = lỗi bất ngờ khi phát lại. Đây là tái hiện quyết định của phần mềm, không tái hiện xe; mới kiểm với bo mô phỏng và cổng serial giả ([chế độ quan sát](docs/CHE_DO_QUAN_SAT.md) mục 5.1).

**Chấm một lần chạy (T5).** `autopark.evaluation.score_run` đọc thư mục `<tên>_vehicle_io` (RunLog `<tên>.csv` bên cạnh) hoặc gói của `export_run` (SIM hay VehicleIO), cùng một tham chiếu độc lập: tệp tư thế R1 (`--reference`, định dạng ở `evaluation/reference_pose.py`), hai điểm thước R2 (`--r2-points`), hay tư thế thật của mô phỏng (`--sim-truth`, chỉ mức MP và xe ảo của BT). Công cụ tính các ngưỡng N-… theo `configs/nguong_nghiem_thu.json` (ĐỀ XUẤT – CHỜ CHỐT), ghi một dòng biên bản vào tệp `--report` (bắt buộc, trừ khi `--dry-run`) và một tệp chi tiết JSON có SHA-256 của mọi tệp đã đọc. Nó chỉ tự đề xuất THÀNH CÔNG hay THẤT BẠI; `--result` của người chấm luôn thắng. Ví dụ chấm mức MP lần DO-1 đầu tiên, chạy ở nhánh VehicleIO với bo mô phỏng (`run_app.py scenarios/bai_do_xe.json`) rồi **Xuất log CSV…** vào `runs/nghiem_thu/mo_phong/do1_l01/lan_chay.csv`:

```powershell
./.venv/Scripts/python.exe -X utf8 -m autopark.evaluation.score_run --scenario DO-1 --attempt 1 --level MP --log runs/nghiem_thu/mo_phong/do1_l01/lan_chay_vehicle_io --sim-truth --layout scenarios/bai_do_xe.json --report runs/nghiem_thu/mo_phong/bien_ban_mo_phong.csv
```

`--layout` là tệp kịch bản (hay bố trí đo bằng thước) của lần chạy. Công cụ mới chấm dữ liệu tổng hợp và lần chạy mô phỏng; chưa chấm lần chạy thật nào (chưa có tham chiếu R1, công cụ T4) *(02/10/2026: công cụ T4 nay có, còn thiếu camera trên cao và TC-1)*. Ở tốc độ mặc định 0,15 m/s của planner, lần DO-1 mô phỏng không đạt N-V1 ([ngưỡng đề xuất](docs/NGUONG_NGHIEM_THU_DE_XUAT.md) N-V1). *(Cập nhật 02/10/2026: N-V1 kiểm thêm vế tốc độ mục tiêu từ lệnh đã gửi, nên lần chạy ở tốc độ mặc định luôn được đề xuất THẤT BẠI. Lần DO-1 mức MP cho nghiệm thu: mở `run_app.py scenarios/sa_ban_3x2_hai_hop.json --vehicle-config configs/vehicle_nghiem_thu.json` (hay tệp nghiệm thu `scenarios/nghiem_thu/do1.json`, tự dùng xe nghiệm thu và giới hạn đổi chiều của DO-1), chọn nhánh VehicleIO với bo mô phỏng, rồi chấm như lệnh trên với `--layout` là kịch bản đã chạy. Xe mô phỏng bị kẹp ở 0,10 m/s nên N-V1 ở MP không kiểm vọt lố; công cụ ghi chú điều này. `--sim-truth` nhận cả log bo ảo QEMU (tư thế xe mô phỏng phía laptop) nhưng chỉ ở mức MP.)* Tham số khác: `--help`.

**Diễn tập tiêm lỗi (T6), chỉ mức mô phỏng.** `autopark.evaluation.fault_drill` gây lỗi có kiểm soát rồi kiểm phản ứng: `pose` (nguồn tư thế ngừng cập nhật, CB-6) và `hang` (vòng điều khiển của laptop treo, có hoặc không Heartbeat; CB-5 (b), L7) chạy một phiên đỗ qua bo mô phỏng và kiểm phản ứng của phiên và của bo; `camera` (một camera đứng hình, CB-2) không chạy phiên đỗ, chỉ kiểm lớp camera: camera bị báo cũ, bị bỏ khỏi bộ ảnh rồi quay lại. Lệnh chạy trên bo mô phỏng, camera giả hay bản ghi phát lại, không mở cổng COM, LiDAR hay camera:

```powershell
./.venv/Scripts/python.exe -X utf8 -m autopark.evaluation.fault_drill pose --mode hold --repeat 10 --out runs/fault_drill/<ngày> --name cb6
./.venv/Scripts/python.exe -X utf8 -m autopark.evaluation.fault_drill hang --seconds 1 --phases 0 1 2 3 --out runs/fault_drill/<ngày> --name cb5b
./.venv/Scripts/python.exe -X utf8 -m autopark.evaluation.fault_drill camera --mode stall --repeat 10 --out runs/fault_drill/<ngày> --name cb2
```

Mỗi lần chạy một thư mục `<out>/<name>_<kk>/` (lần chạy `pose`, `hang`: tám tệp log của `VehicleLink`, `faults.csv`, `drill.json`; lần chạy `camera`: chỉ `faults.csv`, `drill.json`), tóm tắt ở `<out>/<name>.drill.json`; mã thoát 0 khi mọi lần ĐẠT, 1 khi có lần KHÔNG ĐẠT, 2 khi sai tham số hay `--name` đã dùng trong `--out`. ĐẠT/KHÔNG ĐẠT là kiểm của công cụ, không phải ngưỡng nghiệm thu. `hang --heartbeat` cho biến thể có Heartbeat; `camera --replay <bản ghi> --ports 1 2 3 4 --port 2` dùng bản ghi phát lại thay camera giả.

**Tệp sa bàn nghiệm thu (T12 theo kịch bản).** `autopark.evaluation.acceptance_scenarios` sinh 9 tệp gắn DO-1 … DO-6 từ `scenarios/sa_ban_3x2_hai_hop.json` và các ca khó của KICH_BAN mục 5.1, kích thước theo xe GIẢ ĐỊNH. Mặc định ghi vào `runs/sa_ban_nghiem_thu`; bộ trong kho ở `scenarios/nghiem_thu`. Khi có xe đo, sinh lại bằng lệnh dưới (`--dry-run` chỉ kiểm). Mọi thẻ được tra trong tệp ngưỡng trước khi ghi. Mã thoát 2 khi thẻ không tra được hay tệp đã có mà thiếu `--force`; khi đó không ghi tệp nào. Công cụ không chạy planner.

```powershell
./.venv/Scripts/python.exe -X utf8 -m autopark.evaluation.acceptance_scenarios --out scenarios/nghiem_thu --vehicle-config <tệp xe> --force
```

**Tham chiếu trên cao R1 (T4).** Camera trên cao + hai marker ArUco trên xe → tệp tư thế tham chiếu cho `score_run --reference` ([tham chiếu trên cao](docs/THAM_CHIEU_TREN_CAO.md)). Chuỗi lệnh (chỉ `overhead_record` và nút "Mở camera" của giao diện mở camera):

```powershell
./.venv/Scripts/python.exe -X utf8 -m autopark.perception.aruco_sheet --ids 0-47 --size-mm 100 --out calibration/bang_in/aruco
./.venv/Scripts/python.exe -X utf8 -m autopark.evaluation.overhead_ref survey-template --size 3.0x2.0 --step 0.5 --check 8 --out docs/evidence/moc_sa_ban_<ngày>.csv
./.venv/Scripts/python.exe -X utf8 -m autopark.video.overhead_record --index N --size 1280x720 --seconds 20 --out runs/tren_cao/<ngày> --name san_trong
./.venv/Scripts/python.exe -X utf8 -m autopark.evaluation.overhead_ref floor --intrinsics calibration/cam_tren_cao_1280x720.json --survey docs/evidence/moc_sa_ban_<ngày>.csv --video runs/tren_cao/<ngày>/san_trong.avi --out docs/evidence/nghiem_thu/mat_san_<ngày>.json
./.venv/Scripts/python.exe -X utf8 -m autopark.evaluation.overhead_ref tc1 --floor docs/evidence/nghiem_thu/mat_san_<ngày>.json --markers configs/tham_chieu/xe_gia_v1.json --poses docs/evidence/tc1_<ngày>.csv --kind full --out docs/evidence/nghiem_thu/tham_chieu_tren_cao_<ngày>.json
./.venv/Scripts/python.exe -X utf8 -m autopark.evaluation.overhead_ref track --video runs/tren_cao/<ngày>/do1_l01.avi --floor docs/evidence/nghiem_thu/mat_san_<ngày>.json --markers configs/tham_chieu/xe_gia_v1.json --tc1 docs/evidence/nghiem_thu/tham_chieu_tren_cao_<ngày>.json --out runs/nghiem_thu/<ngày>/do1_l01/tu_the_tham_chieu.csv
./.venv/Scripts/python.exe -X utf8 -m autopark.ui.overhead_app --index N --camera-name tren_cao --size 1280x720
```

- Tờ marker để in (PDF) đã có trong kho ở `calibration/bang_in/aruco/` (lệnh đầu chỉ cần khi tạo lại). `configs/tham_chieu/xe_gia_v1.json` là cấu hình marker trên xe giả ĐÃ ĐO, chưa có; mẫu GIẢ ĐỊNH `xe_gia_v0.json` (`measured: false`) bị `tc1` và `track` từ chối với dữ liệu thật (`track` nhận khi thêm `--cho-cau-hinh-chua-do`, độ chính xác khi đó để trống).
- `overhead_record`: tên đã có thì từ chối, trừ khi `--overwrite` (bản cũ đổi tên thành `<tên>.bak_<ngày_giờ>.*`); `--force` chỉ bỏ qua từ chối khi ổ còn < 5 GB; mã thoát 1 cả khi camera thôi trả khung tốt quá 5 s (trạng thái "lỗi").
- Mã thoát của `overhead_ref`: 0 xong; 1 xong nhưng chất lượng chưa đạt (khớp mặt sàn `ok` false; camera dịch, dưới 80 % khung hợp lệ hay không khung nào hợp lệ; TC-1 thiếu yêu cầu); 2 tham số sai hay bị từ chối, không ghi gì; 3 lỗi bất ngờ. Video AVI không do `overhead_record` ghi (chỉ có số khung/s danh định) bị từ chối trừ khi thêm `--allow-nominal-fps`; khi chấm, tham chiếu như vậy cần ít nhất 2 cặp đồng bộ.
- `overhead_ref check <tệp>` tóm tắt mọi tệp của T4; `overhead_ref synthetic --out runs/tren_cao/tong_hop` ghi một bộ thử TỔNG HỢP có README chuỗi lệnh.

Mới kiểm trên ảnh tổng hợp và camera giả; CHƯA THỬ với camera thật, chưa chọn camera trên cao, chưa làm TC-1; độ trễ chụp CHƯA ĐO (mặc định 0,15 s). Ngưỡng ĐỀ XUẤT – CHỜ CHỐT (người dùng giao quyết định 02/10/2026).

**Ghi cảm biến trong phiên đỗ (T3, thêm 02/10/2026).** Ngăn "Ghi cảm biến" của `ui.lidar_app` (mục 7). "Xuất log CSV…" ghi thêm `<tên>_sensor_recordings.json` trỏ tới bản ghi. Mới kiểm offscreen với nguồn giả.

**Đo EcoQoS của ứng dụng giao diện.** Công cụ mở giao diện thật, đặt cửa sổ thường, thu nhỏ hay bị một màn che kín bằng Win32 rồi lập đường như nút **Tìm đường đỗ**, kèm hai đối chứng (cùng giao diện tắt EcoQoS, tiến trình không cửa sổ). (Từ 02/10/2026 biến thể `gui_system` của công cụ là giao diện ở mặc định của Windows, tức ứng dụng trước ngày đó hay ứng dụng chạy với `AUTOPARK_KEEP_ECOQOS=1`; `gui_off` là ứng dụng hiện nay.) Lượt đầy đủ (mặc định ca `uturn_w46`, `--khoi 2 --lap 2`) mở cửa sổ thật khoảng 7–9 phút; máy phải rảnh và không ai dùng (bấm phím hay chuột trong lúc đo làm mất quyền đưa cửa sổ ra trước, các lượt sau bị loại); Esc hoặc bấm chuột đóng màn che. Kết quả lượt đo 02/10/2026: [biên bản chuyển máy](docs/CHUYEN_MAY_BAN.md) mục 10:

```powershell
./.venv/Scripts/python.exe -X utf8 -m autopark.evaluation.ecoqos_gui do --ra docs/evidence/ecoqos_giao_dien_<ngày>
./.venv/Scripts/python.exe -X utf8 -m autopark.evaluation.ecoqos_gui tom-tat --ra <thư mục đã đo>
```

`tom-tat` viết lại `tom_tat.txt` từ tệp kết quả. Lệnh thử nhanh `do --ra runs/thu_ecoqos --ca pillar_at_slot_mouth --khoi 1 --lap 1 --cho 2` (khoảng 35 s) chỉ kiểm công cụ chạy được: mỗi trạng thái chỉ có một lượt nên mọi phép so in "không đủ lượt hợp lệ để so"; muốn so cần ít nhất 2 lượt hợp lệ mỗi bên, như mặc định. Kết quả lượt đo thật ghi ở [biên bản chuyển máy](docs/CHUYEN_MAY_BAN.md).

**Đo vòng điều khiển 50 Hz khi chạy (thêm 02/10/2026).** Cùng công cụ, lệnh `do-chay`: mỗi lượt đặt cửa sổ thường, thu nhỏ hay bị che, bấm **Bắt đầu đỗ** và ghi nhịp giao diện, nhịp điều khiển, thời gian phiên so với đồng hồ thật của một lần chạy SIM hoặc VehicleIO với bo mô phỏng (không cổng COM, camera, LiDAR). Mặc định (kịch bản `bai_do_xe`, nhánh SIM và VEHICLE_IO, biến thể `gui_system` và `gui_off`, 2 khối) mở cửa sổ thật khoảng 15–30 phút (lượt ngày 02/10/2026 mất 14 phút 17 s); máy phải rảnh, không ai dùng, màn hình không tự tắt; không chạy cùng LD-1 hay lượt test:

```powershell
./.venv/Scripts/python.exe -X utf8 -m autopark.evaluation.ecoqos_gui do-chay --ra docs/evidence/ecoqos_chay_<ngày>
./.venv/Scripts/python.exe -X utf8 -m autopark.evaluation.ecoqos_gui do-chay --ra runs/thu_ecoqos_chay --nhanh SIM --bien-the gui_system --khoi 1 --lap 1 --cho 2
./.venv/Scripts/python.exe -X utf8 -m autopark.evaluation.ecoqos_gui do-chay --ra <thư mục mới> --bien-the gui_off,gui_off_dh
./.venv/Scripts/python.exe -X utf8 -m autopark.evaluation.ecoqos_gui tom-tat --ra <thư mục đã đo>
```

Lệnh thứ hai chỉ kiểm công cụ chạy được (mỗi trạng thái một lượt, mọi phép so in "không đủ lượt hợp lệ để so"). Lệnh thứ ba (biến thể `gui_off_dh`: tắt EcoQoS và luôn tôn trọng độ phân giải đồng hồ của tiến trình) chỉ cần khi `gui_off` vẫn thưa nhịp lúc thu nhỏ. `tom-tat` tự nhận thư mục của `do-chay` (`may.json` có `che_do: chay`). Một lần chạy không dừng được thì công cụ bỏ phần còn lại của khối đó, mã thoát vẫn 0; xem dòng CẢNH BÁO của `tom_tat.txt` và `khoi_bo_do` trong `may.json`.

Kết quả lượt đo 02/10/2026, 18:43–18:57, máy bàn, bằng lệnh thứ nhất ([tóm tắt](docs/evidence/ecoqos_chay_02102026/tom_tat.txt), [biên bản chuyển máy](docs/CHUYEN_MAY_BAN.md) mục 13): 32/32 lần chạy xong; thu nhỏ ở mặc định Windows (`gui_system`) làm thời gian tính mỗi bước 5 ms chậm rõ (hệ số 1,73 ở SIM, 1,76 ở VehicleIO), `gui_off` thì hết (1,00 / 0,96); bị che không thấy chậm; nhịp giao diện p95 không đổi (≈ 16,5 ms); khoảng lớn nhất giữa hai nhịp điều khiển 32 ms khi cửa sổ thường, 46–47 ms khi thu nhỏ, không khoảng nào quá 0,15 s; thời gian phiên chậm ≈ 2,5 % so với đồng hồ thật vì `QElapsedTimer` làm tròn ms. Hệ quả với bo theo đồng hồ tường (bo thật, bo ảo QEMU: hạn lệnh 0,15 s, watchdog 0,5 s) chỉ SUY RA, CHƯA ĐO; laptop và kế hoạch nguồn Balanced CHƯA ĐO.

## 5. Cài môi trường AI và lấy dữ liệu

Chạy `cai_dat_train.cmd`. Script tạo `.venv-train`, cài lock với torch CUDA 12.8 và kiểm GPU; `.venv-train` chép từ máy khác mà không chạy được thì được đổi tên thành `.venv-train.hong-tu-may-cu` rồi tạo mới, như mục 2. Môi trường này có Shapely để AI chạy cùng phiên đỗ. Môi trường tham chiếu dùng Python 3.12 và GPU NVIDIA.

[Chuyển môi trường/checkpoint sang laptop](docs/MAY_NOP_DO_AN.md). Chép cả dự án sang máy bàn khác: làm theo mục 5 của [biên bản chuyển máy](docs/CHUYEN_MAY_BAN.md), tóm trong sơ đồ dưới.

Bản clone không có:

| Tệp/dữ liệu | Cách có |
|---|---|
| `runs/ai_woodscape_rtx4000_v1/best.pt` | Chép từ máy bàn rồi so SHA-256 với [MAY_NOP_DO_AN.md](docs/MAY_NOP_DO_AN.md) mục 1, hoặc huấn luyện lại |
| `datasets/prepared/` | Chuẩn bị cache từ dataset |
| `runs/rig_recordings/` | Chép bản ghi hoặc ghi phiên mới |
| `calibration/cam_p<cổng>.json` | Hiệu chuẩn từng camera |
| `configs/rig/camera_rig_extrinsics_v1.json` | Đo ngoại tham |
| `configs/roi/rig_v1/` | Tạo ROI camera thật |

Cài thư viện không tự tạo các tệp này. Ngoại tham `v0` và ROI WoodScape không thay hiệu chuẩn camera dự án.

### Chuẩn bị một máy mới

Thứ tự làm khi chuyển sang một máy bàn khác hoặc cài laptop trình diễn, gom từ [biên bản chuyển máy](docs/CHUYEN_MAY_BAN.md) mục 5–8 và [MAY_NOP_DO_AN.md](docs/MAY_NOP_DO_AN.md) mục 2:

```mermaid
flowchart TD
    S["Máy mới: máy bàn thay thế hoặc laptop trình diễn"]
    Q{"Chép nguyên thư mục từ máy cũ?"}
    K1["Giữ runs/, datasets/, checkpoint đã chép"]
    K2["git clone thbn12082/autopark, chép best.pt qua USB"]
    H["So SHA-256 của best.pt với MAY_NOP_DO_AN mục 1"]
    P["Cài Python 3.12.10 và driver CP210x"]
    V1["cai_dat.cmd: kiem_venv.cmd, venv hỏng thì đổi tên, tạo .venv"]
    V2["cai_dat_train.cmd: .venv-train, torch cu128, in CUDA True"]
    C["Sửa lidar_port trong configs/thiet_bi.json"]
    F{"Cần firmware và bo ảo?"}
    FW["g++, cmake, Ninja, PlatformIO, QEMU 9.2.2, đường dẫn PlatformIO và QEMU vào thiet_bi.json"]
    SK["Không cài: test host firmware và test bo ảo tự bỏ qua"]
    PC["Traceback còn đường dẫn cũ: xóa __pycache__ ngoài venv"]
    T["Chạy toàn bộ test ở hai venv, offscreen, lưu JUnit"]
    MM["do_may_moi.cmd: 6 bước, so với tham_chieu_20260929.json"]
    R["Ghi kết quả vào CHUYEN_MAY_BAN.md hoặc MAY_NOP_DO_AN.md"]
    LB["Laptop: mang kết quả về máy bàn, may_moi --steps, CHƯA CHẠY"]
    RN["Chỉ đổi tên thư mục: pip install -e . --no-deps ở hai venv"]
    S --> Q
    Q -->|Có| K1 --> P
    Q -->|Không| K2 --> H --> P
    P --> V1 --> V2 --> C --> F
    F -->|Có| FW --> PC
    F -->|Không| SK --> PC
    PC --> T --> MM --> R
    MM -->|trên laptop| LB
    S -.->|cùng máy, chỉ đổi tên thư mục| RN
    classDef daco fill:#dff0d8,stroke:#3c763d,color:#1b3a1b
    classDef giaLap fill:#fcf8e3,stroke:#8a6d3b,color:#4d3b12
    classDef chuaLam fill:#f2dede,stroke:#a94442,color:#4d1a1a,stroke-dasharray: 4 3
    class LB chuaLam
```

Đỏ viền đứt: chưa làm hoặc chưa thử trên thiết bị. Các ô không tô màu là bước làm, không nói về trạng thái. Trên máy bàn hiện tại, nhánh chép nguyên thư mục đã làm ngày 29–30/09/2026 ([biên bản chuyển máy](docs/CHUYEN_MAY_BAN.md) mục 1–8). Trên laptop, `do_may_moi.cmd` chưa chạy lần nào. Cùng sơ đồ: 9.3 trong [Sơ đồ hệ thống](docs/SO_DO_HE_THONG.md).

## 6. Huấn luyện và suy luận

Sau khi có cache:

```powershell
./.venv-train/Scripts/python.exe -X utf8 -m autopark.perception.verify_cache
./.venv-train/Scripts/python.exe -X utf8 -m autopark.perception.train --config configs/train_woodscape_rtx4000_baseline.json --out runs/ai_luot_moi
```

Với checkpoint tham chiếu đã chép vào đúng chỗ:

```powershell
./.venv-train/Scripts/python.exe -X utf8 -m autopark.perception.evaluate --checkpoint runs/ai_woodscape_rtx4000_v1/best.pt --split val --out runs/cham_val_moi
./.venv-train/Scripts/python.exe -X utf8 -m autopark.perception.predict --checkpoint runs/ai_woodscape_rtx4000_v1/best.pt --input duong_dan_anh.jpg --out runs/du_doan_moi --threshold 0.15
```

Thay `duong_dan_anh.jpg` bằng ảnh thật. Ngưỡng 0,15 chưa được nghiệm thu trên sa bàn.

Ngày 29/09/2026 trên máy bàn hiện tại (mã `b37e9ee`), cả bốn lệnh đã chạy lại: `verify_cache` đạt; `evaluate --split val` với checkpoint tham chiếu ra mIoU 0,9700, bằng số ở [HUAN_LUYEN.md](../HUAN_LUYEN.md); `predict` chạy trên một ảnh ở ngưỡng 0,15; `train` chạy với thêm `--set epochs=1`, chỉ để kiểm pipeline và GPU ([tóm tắt](docs/evidence/chuyen_may_20260929/kiem_may_20260929.md) mục 2.3–2.6).

[Huấn luyện/kết quả](../HUAN_LUYEN.md), [tải dữ liệu](datasets/TAI_VA_KIEM_TRA.md), [nhãn sa bàn](docs/GAN_NHAN_SA_BAN.md).

## 7. LiDAR, camera và bàn thử

### Mở giao diện mà chưa kết nối cảm biến

Chọn một trong hai lệnh:

```powershell
./.venv/Scripts/python.exe -X utf8 -m autopark.ui.lidar_app --no-connect
./.venv-train/Scripts/python.exe -X utf8 -m autopark.ui.lidar_app --no-connect --camera-ai
```

Lệnh không tự mở LiDAR/camera. **Bật AI camera** mở camera; **Kết nối** mở LiDAR. **Nạp lại hiệu chuẩn** khi AI tắt chỉ kiểm tệp.

### Kết nối và ghi thiết bị thật

Cổng LiDAR đặt ở một chỗ: khóa `lidar_port` trong [configs/thiet_bi.json](configs/thiet_bi.json), hiện là `"COM3"` của máy bàn. Đổi máy thì sửa dòng này theo Device Manager (mục "Silicon Labs CP210x USB to UART Bridge (COMx)"), hoặc ghi `"auto"` để tự tìm bộ chuyển CP210x; `auto` lấy cổng CP210x đầu tiên, nên tránh khi cắm thêm bo khác cũng qua CP210x. Lệnh LiDAR không có `--port` lấy cổng từ tệp; `--port COMx` ghi đè cho một lần chạy. Tệp thiếu hoặc hỏng thì lệnh báo lỗi trước khi mở thiết bị (giao diện hiện lỗi ở ngăn LiDAR lúc kết nối).

Kiểm cổng, chỉ đọc thông tin và tình trạng C1:

```powershell
./.venv/Scripts/python.exe -X utf8 -m autopark.lidar.rplidar_c1 info
```

Mở giao diện và kết nối LiDAR ở cổng của tệp:

```powershell
./.venv/Scripts/python.exe -X utf8 -m autopark.ui.lidar_app
```

Ghi bốn camera + LiDAR + AI, cần checkpoint. `--lidar` không kèm giá trị lấy cổng của tệp; `--lidar COMx` ghi đè; bỏ `--lidar` thì không dùng LiDAR:

```powershell
./.venv-train/Scripts/python.exe -X utf8 -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 60 --name phien_moi --out runs/rig_bench/phien_moi --record runs/rig_recordings/phien_moi
```

Lệnh mở thiết bị thật. Mặc định 640×480; chất lượng bốn luồng phải đo chung trên đúng hub/máy. Sau khi đổi cách lấy cổng (29/09/2026), trên máy bàn đã chạy với thiết bị thật: `lidar.rplidar_c1 info` không `--port` mở đúng COM3 và đọc được C1 ([biên bản](docs/CHUYEN_MAY_BAN.md) mục 3); lúc 15:11–15:12 cùng ngày (mã `b37e9ee`), lệnh `rig.bench` như trên với `--lidar` không kèm cổng và `--seconds 30` chạy với bốn camera, LiDAR ở COM3 lấy từ tệp và AI, ghi phiên rồi phát lại được ([tóm tắt](docs/evidence/chuyen_may_20260929/kiem_may_20260929.md) mục 2.7–2.8; tệp gốc git-ignore ở `runs/kiem_may_20260929/rig_bench/` (số đo) và `runs/kiem_may_20260929/rig_recordings/r_kiem/` (bản ghi)). `ui.lidar_app` chưa chạy lại với thiết bị thật sau thay đổi này. *(Cập nhật 02/10/2026: trên máy bàn, không người ở cạnh, `rig.bench` như trên với `--seconds 1800 --record` (kịch bản LD-1) chạy đủ 30 phút ở lần 3: mỗi camera 23,85 fps, 0 khung hỏng, LiDAR 10,008 Hz, 0 lỗi, AI 23,75 bộ/s, ghi 4,44 MB/s; `fusion.demo` 30 s và `camera_bench measure` cũng chạy; `ui.lidar_app` với thiết bị thật vẫn chưa chạy ([biên bản](docs/CHUYEN_MAY_BAN.md) mục 12).)*

Mã đọc C1 (`lidar/rplidar_c1.py`, sửa 02/10/2026): trên cổng CP210x của máy bàn `reset_input_buffer()` không xóa byte nào, nên một tiến trình chết để C1 đang quét từng làm mọi lần mở sau trên cùng cổng hỏng ("bad response descriptor"). Mã nay đọc bỏ byte cũ (sau STOP, trước mỗi lệnh hỏi, trước SCAN, trong `flush()`), RESET một lần khi lệnh hỏi hỏng, bỏ vòng đầu sau `flush()`; `stats()` có thêm `discarded_bytes`, `skipped_after_flush`. Thử trên C1 thật: giết tiến trình đang quét rồi mở lại đạt 2/2 ([chẩn đoán](docs/evidence/thiet_bi_20261002/chan_doan_lidar.txt)).

Dấu đồng bộ cho video R3 (T14, thêm 02/10/2026): thêm `--sync-mark`, ví dụ:

```powershell
./.venv-train/Scripts/python.exe -X utf8 -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 60 --name cb1 --out runs/rig_bench/cb1 --sync-mark
```

Ô trắng có số nháy 0,5 s phủ cả màn hình chính (`--sync-screen N` chọn màn hình khác) ở đầu và cuối phần đo; nhấn Enter, Space hay m thêm một dấu, nhưng chỉ khi cửa sổ lệnh đang được chọn; phiên dài thêm `--sync-every 30` (một dấu mỗi 30 s). Lệnh ghi `<out>/<name>.sync.csv` (tệp đã có thì từ chối ngay, mã 2) và khóa `sync_marks` của `.rig.json`; không dùng với `--replay`. Tắt khóa màn hình khi chạy dài không người trông. `ui.rig_app` có nút "Dấu đồng bộ (F8)" tương tự. Chỉ kiểm offscreen; trên màn hình và với camera thật CHƯA THỬ; ảnh hưởng của cửa sổ nháy lên số đo CHƯA ĐO.

Từ 02/10/2026 (T10) `gap_max_ms` của từng camera trong `.rig.json` tính cả khoảng hở còn mở lúc chốt số (`gap_end_ms`, ví dụ camera ngừng hẳn trước khi hết phần đo), nghĩa cũ ở `gap_closed_max_ms`; `rig.bench` in "khoảng cách max … ms (hở cuối phiên … ms)". `.rig.json` ghi trước đó không có `gap_end_ms`. Mới kiểm bằng test với camera giả.

### Phát lại bản ghi

```powershell
./.venv-train/Scripts/python.exe -X utf8 -m autopark.rig.bench --replay runs/rig_recordings/phien_moi --name phat_lai --out runs/rig_bench/phat_lai
./.venv/Scripts/python.exe -X utf8 -m autopark.ui.rig_app --replay runs/rig_recordings/phien_moi --no-ai
```

Không mở thiết bị. Lệnh thứ hai chỉ xem, không chạy AI. [Ghi/phát lại](docs/GHI_PHAT_LAI_BAN_THU.md).

### AI tạo vật cản trong phiên đỗ

Cần checkpoint và nội tham/ngoại tham/ROI thật đạt kiểm tra; nếu thiếu, giao diện báo lý do chặn.

```powershell
./.venv-train/Scripts/python.exe -X utf8 -m autopark.ui.lidar_app --camera-ai --cam-ports 1 2 3 4
```

Lệnh mở LiDAR và camera thật. Nhánh kết hợp này CHƯA THỬ với camera thật đang mở (tính đến 30/09/2026; [AI camera](docs/AI_DIEU_KHIEN_XE.md) mục 8.3).

Phát lại bằng rig tổng hợp để thử luồng phần mềm:

```powershell
./.venv-train/Scripts/python.exe -X utf8 -m autopark.ui.lidar_app --no-connect --camera-ai --cam-replay runs/rig_recordings/phien_moi --camera-ai-test-rig
```

`--cam-replay` tự bật AI. Rig tổng hợp chỉ dùng với replay/nguồn giả; vị trí vật cản không phải số đo từ camera thật. [Chi tiết AI camera](docs/AI_DIEU_KHIEN_XE.md).

### Ghi cảm biến trong phiên đỗ (T3, thêm 02/10/2026)

Ngăn **Ghi cảm biến** của `ui.lidar_app` (thẻ cạnh ngăn LiDAR) ghi camera của ngăn AI camera và LiDAR của ngăn LiDAR vào `runs/session_recordings/<ngày_giờ>_<tên>/`, cùng đồng hồ `perf_counter` với log VehicleIO và dấu đồng bộ (mốc ở `session/clock.csv`). Không gửi gì tới bo, không dừng hay chặn xe. **Bắt đầu ghi** khóa khi xe đang chạy; **Dừng ghi** luôn dùng được. Đóng cửa sổ thì dừng ghi, dừng xe (enable=0 + DISARM, tắt bo ảo QEMU) rồi mới chờ bản ghi ghi nốt (tối đa 60 s).

```powershell
./.venv-train/Scripts/python.exe -X utf8 -m autopark.ui.lidar_app --camera-ai --cam-ports 1 2 3 4 --record-root runs/session_recordings --record-format jpg
./.venv-train/Scripts/python.exe -X utf8 -m autopark.ui.lidar_app --camera-ai --session-replay runs/session_recordings/<thư mục>
./.venv/Scripts/python.exe -X utf8 -m autopark.ui.lidar_app --recording runs/session_recordings/<thư mục>
```

- Lệnh 1 mở camera và LiDAR thật. Không bắt đầu ghi khi ổ còn < 5 GB (`--record-min-free-gb`), tự dừng dưới 2 GB (ĐỀ XUẤT – CHỜ CHỐT).
- Lệnh 2 phát lại camera và LiDAR của bản ghi trên một đồng hồ (T3b).
- Lệnh 3 chỉ phát lại LiDAR (mọi phần).

Chỉ kiểm offscreen với nguồn giả; CHƯA THỬ với thiết bị thật (MB/s của cảnh sa bàn, khung bị bỏ, vòng 50 Hz khi đang ghi: CHƯA ĐO). [Chi tiết](docs/GHI_PHAT_LAI_BAN_THU.md) mục 9.

## 8. Chuẩn bị camera và định vị

| Công việc | Tài liệu |
|---|---|
| In bảng, chụp, tính nội tham | [Hiệu chuẩn camera](docs/HIEU_CHUAN_CAMERA.md) |
| Đo vị trí/góc, vẽ ROI | [Ngoại tham và ROI](docs/NGOAI_THAM_VA_ROI.md) |
| Kiểm bản đồ nhìn từ trên xuống | [BEV](docs/BEV.md) |
| Gán nhãn ảnh | [Nhãn sa bàn](docs/GAN_NHAN_SA_BAN.md) |
| Ghi scan, đo khoảng cách, tạo map | [LiDAR](docs/GIAI_DOAN_1_LIDAR.md) |
| Định vị trên map có sẵn | [Định vị](docs/DINH_VI_LIDAR.md) |
| So sánh định vị/khớp scan | [SLAM](docs/SO_SANH_DINH_VI_SLAM.md) |
| Dựng bản đồ sa bàn từ nhiều chỗ đặt, nguồn tư thế LiDAR của phiên đỗ (T2) | [Nguồn tư thế LiDAR](docs/NGUON_TU_THE_LIDAR.md) |
| Camera trên cao: khớp mặt sàn, TC-1, tư thế R1 | [Tham chiếu trên cao](docs/THAM_CHIEU_TREN_CAO.md) |

Tham số từng công cụ: `python -m <tên_module> --help` bằng đúng môi trường.

Camera không qua hub 1–4, như camera trên cao của tham chiếu R1 (T11, thêm 02/10/2026): tra index OpenCV mỗi lần cắm hay khởi động lại, rồi hiệu chuẩn theo index và tên; tệp ra `calibration/cam_tren_cao_1280x720.json`, ảnh ở `runs/calib/<ngày giờ>_tren_cao/`:

```powershell
./.venv/Scripts/python.exe -X utf8 -m autopark.video.camera_bench list
./.venv/Scripts/python.exe -X utf8 -m autopark.ui.calib_app --index N --camera-name tren_cao --size 1280x720
```

BEV và AI camera không đọc tệp này; ngoại tham từ chối nó. Khi một số cổng có camera ở hai hub (ví dụ camera trên cao cắm thẳng cổng 2 của máy), `calib_app --port 2` báo lỗi thay vì chọn đại; khi đó cắm camera trên cao vào cổng có số khác hay rút nó ra lúc hiệu chuẩn camera xe. Chỉ kiểm offscreen với camera giả; camera trên cao thật CHƯA THỬ ([hiệu chuẩn camera](docs/HIEU_CHUAN_CAMERA.md)).

Sau nội tham: in marker, đo mốc, khớp mặt sàn, TC-1 và trích tư thế R1 bằng `autopark.evaluation.overhead_ref` hay giao diện `autopark.ui.overhead_app` (T4, thêm 02/10/2026; mới kiểm trên ảnh tổng hợp; lệnh ở mục 4, [tham chiếu trên cao](docs/THAM_CHIEU_TREN_CAO.md)).

Bản đồ LiDAR cho nguồn tư thế của phiên đỗ (T2, thêm 02/10/2026; người dùng giao quyết định 02/10/2026, theo đề xuất mục 7 của [so sánh SLAM](docs/SO_SANH_DINH_VI_SLAM.md)): ghi LiDAR đứng yên ở vài chỗ đặt, neo chỗ đặt 1 vào hệ sa bàn bằng tư thế đo bằng thước, rồi dựng bản đồ; định vị lại một bản ghi offline bằng cùng mã mà phiên dùng:

```powershell
./.venv/Scripts/python.exe -X utf8 -m autopark.lidar.map_builder --placement <chỗ_1>.npz --anchor X Y YAW_DEG --placement <chỗ_2>.npz --scenario scenarios/sa_ban_3x2_hai_hop.json --out runs/lidar_maps/<ngày>_<tên>
./.venv/Scripts/python.exe -X utf8 -m autopark.lidar.pose_estimator --map runs/lidar_maps/<ngày>_<tên> --recording <bản_ghi>.npz --out runs/lidar_pose/<ngày>_<tên> --initial X Y YAW_DEG
```

`map_builder`: tư thế là của TÂM QUAY LiDAR (m, m, độ) trong hệ sa bàn; bị từ chối (tỉ lệ ghép, độ tản, lệch so với thước, kiểm bỏ-ra-một vượt ngưỡng đề xuất) thì chỉ ghi `map_build.json` với `ok` false, mã thoát 1; dùng sai thì mã 2, không ghi gì; bản đồ không có mốc neo không dùng được cho phiên. `pose_estimator --recording` nhận cả thư mục bản ghi phiên (T3); `--same-scans-as <localization.csv>` xử lý đúng các vòng của một lần chạy đã ghi. Mới kiểm trên vòng quét tổng hợp và bản ghi C1 đứng yên; CHƯA dựng bản đồ sa bàn thật nào. Dùng trong phiên: mục 9.

## 9. Chế độ điều khiển, firmware và bo ảo

Nhánh chạy chọn ở ô "Nhánh chạy khi bấm Bắt đầu đỗ" của thẻ **Mô phỏng**; bo nhận lệnh (bo mô phỏng, bo ảo QEMU từ 02/10/2026, hay một cổng COM) và nguồn tư thế (từ 02/10/2026) chọn ở thẻ **Bo điều khiển**. Hai thẻ nằm trong ngăn "Thiết lập sa bàn", mở bằng nút **Sa bàn +**. Sơ đồ dưới là đường đi trong mã hôm nay (`ui/main_window.py`, `application/vehicle_link.py`):

```mermaid
flowchart TD
    A["Thẻ Mô phỏng: ô Nhánh chạy khi bấm Bắt đầu đỗ"] --> M{"Nhánh?"}
    B["Thẻ Bo điều khiển: Bo mô phỏng, Bo ảo QEMU hoặc một cổng COM, ô Nguồn tư thế"] --> P{"Bo đang chọn?"}
    M -->|SIM, mặc định| SIM["vehicle_link = None: SimWorld + SimFeedback của giai đoạn 0"]
    M -->|VEHICLE_IO hoặc OBSERVE| P
    P -->|Bo mô phỏng| VS["VehicleLink.simulated: mỗi START tạo SimVehicleIO + FirmwareModel mới tại xuất phát, bo theo tệp xe"]
    VS --> POSE["Nguồn Mô phỏng, mặc định: SimTruthPose, tư thế thật của xe mô phỏng, định vị lý tưởng"]
    VS --> LSIM["Nguồn LiDAR mô phỏng, chỉ với bo mô phỏng: định vị (a)+(b) trên vòng quét dựng từ sa bàn, tuổi tối đa 0,25 s, tư thế dời tới hiện tại"]
    VS --> VIO["VEHICLE_IO: COMMAND enable mỗi 20 ms, hạn 0,15 s"]
    VS --> OBS["OBSERVE: SimHumanDriver lái bằng phím mũi tên, phần mềm chỉ ghi commands.csv"]
    P -->|Bo ảo QEMU| QL["VehicleLink.qemu_board → QemuPlantVehicleIO + QemuPlantPose: xe mô phỏng phía laptop bám tham chiếu của firmware thật trong QEMU"]
    QR["Khởi động bo ảo: build esp32s3_qemu nếu cần, QEMU cổng TCP tự chọn (ui/qemu_runner.py)"] --> QL
    QL --> QS["Mỗi START: đặt xe mô phỏng, mở socket://, HELLO đúng boot_id, ARM. Hết lần chạy DISARM, đóng kết nối"]
    P -->|COMx| SER["VehicleLink.serial_port: SerialVehicleIO.deferred, cổng chưa mở"]
    SER -->|nguồn Mô phỏng| REF["START bị từ chối trước khi mở cổng: NoPoseSource, START_NO_POSE_SOURCE"]
    SER -->|nguồn LiDAR thật, chỉ ui.lidar_app| LREAL["LidarPoseSource: VEHICLE_IO bị từ chối trước I/O, START_POSE_UNVERIFIED. OBSERVE: mở cổng ở bước 0c, giữ mở giữa các lần chạy, START_CHECK từ chối vì T8"]
    LREAL -.->|gá LiDAR đo, p04, DV-2, DV-1, T8| REAL["Tự đỗ với ESP32-S3 thật"]
    B -->|tổ hợp bị cấm| BIND["Hộp thoại từ chối, các ô trở về liên kết đang dùng: bo ảo QEMU với nguồn LiDAR, LiDAR mô phỏng với bo COM, LiDAR thật với bo mô phỏng, cổng của LiDAR làm cổng bo"]
    B --> PROBE["Kiểm kết nối bo: HELLO, 5 khung telemetry, so giới hạn, đóng cổng, không ARM. Cổng mà liên kết giữ mở thì đóng trước khi kiểm"]
    PROBE -.->|CHƯA THỬ| REALP["Kiểm kết nối với ESP32-S3 thật"]
    SER --> CLR["Nút Xóa lỗi bo, khi chưa chạy: mở cổng nếu chưa mở, HELLO, gửi CLEAR_FAULT chỉ khi bo FAULT và ESTOP_INPUT = 0. Không ARM, không COMMAND, một dòng board_actions.csv"]
    CLR -.->|CHƯA THỬ| REALC["Xóa lỗi với ESP32-S3 thật"]
    classDef daco fill:#dff0d8,stroke:#3c763d,color:#1b3a1b
    classDef giaLap fill:#fcf8e3,stroke:#8a6d3b,color:#4d3b12
    classDef chuaLam fill:#f2dede,stroke:#a94442,color:#4d1a1a,stroke-dasharray: 4 3
    class A,B,SIM,REF,BIND daco
    class VS,POSE,LSIM,VIO,OBS,QL,QR,QS,PROBE,SER,LREAL,CLR giaLap
    class REAL,REALP,REALC chuaLam
```

Xanh: có mã và đã kiểm trên máy tính (test giao diện và phiên, offscreen) · Vàng: chỉ với bo mô phỏng, bo ảo QEMU (xe mô phỏng phía laptop) hoặc cổng serial giả · Đỏ viền đứt: chưa làm hoặc chưa thử trên thiết bị. Xanh và vàng ở đây hẹp hơn chú giải chuẩn: nhánh SIM tô xanh vì là đường mặc định đã kiểm, nhưng vẫn là mô phỏng; chưa lệnh nào đi tới bo hay xe thật.

| Chế độ | Hành vi |
|---|---|
| Mô phỏng giai đoạn 0 (SIM, mặc định) | Xe ảo chạy trong mô hình động học (`SimWorld` + `SimFeedback`), không qua VehicleIO |
| VehicleIO | Mỗi nhịp 20 ms gửi một COMMAND có hạn 0,15 s qua giao thức tới bo đã chọn; tốc độ và góc lái lấy từ telemetry, tư thế lấy từ nguồn tư thế đã chọn (mặc định mô phỏng, `SimTruthPose`). Chạy được với bo mô phỏng và bo ảo QEMU (xe mô phỏng phía laptop, 02/10/2026) |
| Quan sát | Tính lệnh và ghi `commands.csv` (cột `sent` = 0); không gửi COMMAND nào, kể cả enable=0; lúc START gửi DISARM và bo phải ở DISARMED suốt lần quan sát. Trong giao diện, người lái là `SimHumanDriver` (phím mũi tên) trên bo mô phỏng; với bo ảo QEMU, phím mũi tên lái xe mô phỏng phía laptop (`PlantHumanDriver`, 02/10/2026) |

Chọn một cổng COM thì **Bắt đầu đỗ** ở VehicleIO hay Quan sát bị từ chối trước khi mở cổng, vì chưa có nguồn tư thế thật (`NoPoseSource`). **Kiểm kết nối bo** gửi HELLO, đọc tới 5 khung telemetry, so giới hạn bo với cấu hình xe rồi đóng cổng; không ARM, không COMMAND. Nút này mới thử với bo mô phỏng và cổng serial giả, CHƯA THỬ với ESP32-S3. Danh sách bo chỉ có bo mô phỏng và cổng COM, nên giao diện chưa dùng được bo ảo QEMU. *(Cập nhật 02/10/2026: danh sách có thêm bo ảo QEMU; cổng COM với nguồn tư thế "LiDAR thật" có thể qua bước mở cổng lúc START, xem hai đoạn dưới.)*

**Bo ảo QEMU** (thêm 02/10/2026): chọn "Bo ảo QEMU (firmware xe trong giả lập)" ở thẻ Bo điều khiển rồi bấm **Khởi động bo ảo** (build env `esp32s3_qemu` khi ảnh thiếu hay cũ hơn mã nguồn, lần đầu vài phút; QEMU ở cổng TCP tự chọn trên 127.0.0.1, dùng ≈ 1 lõi CPU). Bắt đầu đỗ ở VehicleIO hay Quan sát đi qua firmware THẬT trong QEMU; tốc độ, góc lái, tư thế lấy từ xe mô phỏng phía laptop (firmware chưa đọc cảm biến, nên vòng PI, STALL, FEEDBACK_LOST của firmware không được thử). Mỗi Bắt đầu đỗ: đặt xe mô phỏng ở xuất phát, mở `socket://`, HELLO đúng boot_id, ARM; hết lần chạy DISARM rồi đóng kết nối. **Kiểm kết nối bo** và **Xóa lỗi bo** dùng được, không hỏi xác nhận. Chọn bo khác, **Tắt bo ảo** hay đóng cửa sổ thì QEMU tắt; log ở `runs/bo_ao_qemu/<ngày_giờ>/`; tham số GIẢ ĐỊNH của xe mô phỏng phía laptop ở `configs/bo_ao_qemu.json` (chu kỳ telemetry chỉ nhận 20..100 ms). Firmware biên dịch cứng `max_speed_mm_s` 300, nên với xe nghiệm thu (0,10 m/s) bo ảo từ chối Bắt đầu đỗ ở VehicleIO (LIMITS_MISMATCH, hướng an toàn; Quan sát chỉ cảnh báo; suy ra từ mã, chưa chạy thử với bo ảo); bản firmware 100 mm/s CHƯA LÀM. Một lần chạy ứng dụng bằng script (offscreen, không người bấm, 02/10/2026, xe `vehicle_default.json`): hai lần đỗ `bai_do_xe.json` đều xong, ≈ 21 s mỗi lần ([biên bản chuyển máy](docs/CHUYEN_MAY_BAN.md) mục 14, [bằng chứng](docs/evidence/bo_ao_ui_20261002/)); lái tay trên cửa sổ thật CHƯA THỬ; cửa sổ thu nhỏ với bo ảo (theo đồng hồ tường) CHƯA ĐO. KHÔNG phải bo thật, chỉ mức MP ([MO_PHONG_FIRMWARE.md](docs/MO_PHONG_FIRMWARE.md) mục 1.1).

**Nguồn tư thế** (thẻ Bo điều khiển, thêm 02/10/2026, T2): **Mô phỏng** (định vị lý tưởng, mặc định); **LiDAR mô phỏng** (chỉ với bo mô phỏng: LiDAR mô phỏng quét sa bàn từ tư thế thật của xe mô phỏng, định vị trên bản đồ dựng từ sa bàn, tư thế dời tới hiện tại bằng tốc độ, góc lái đo); **LiDAR thật** (chỉ trong `ui.lidar_app`, chỉ với bo COM, cần bản đồ của `lidar.map_builder`). Bo ảo QEMU chỉ đi với tư thế của xe mô phỏng phía laptop; cổng của LiDAR không được chọn làm cổng bo; tổ hợp bị cấm thì hộp thoại từ chối và các ô trở về liên kết đang dùng. Với "LiDAR thật", VehicleIO bị từ chối (START_POSE_UNVERIFIED) trước mọi I/O tới khi gá LiDAR được đo và đạt p04, DV-2, DV-1 (`configs/dinh_vi_lidar_v0.json`); ở Quan sát, lần Bắt đầu đỗ đầu mở cổng COM (bước 0c) và giữ mở giữa các lần chạy, **Kiểm kết nối bo** đóng cổng đó trước khi kiểm (hỏi xác nhận); vòng quét phát lại (bản ghi) không bao giờ cho chạy bo COM. Đường này CHƯA THỬ với bo thật. Lần chạy dừng khi định vị lạc (POSE_LOST), lệch kiểm chéo (POSE_DISAGREE), không kiểm chéo được (POSE_UNCHECKED) hay tư thế cũ quá 0,25 s (STALE_POSE). LiDAR mô phỏng chưa dùng được cho nghiệm thu MP: 4/9 tệp `scenarios/nghiem_thu` dừng POSE_LOST ([nguồn tư thế LiDAR](docs/NGUON_TU_THE_LIDAR.md)).

```powershell
./.venv/Scripts/python.exe -X utf8 -m autopark.ui.lidar_app --pose-source lidar_sim
./.venv/Scripts/python.exe -X utf8 -m autopark.ui.lidar_app --pose-source lidar_real --lidar-map runs/lidar_maps/<ngày>_<tên>
```

`--pose-source {sim_truth,lidar_sim,lidar_real}` chọn sẵn ô "Nguồn tư thế"; `--lidar-map` nạp bản đồ (phải ở hệ sa bàn); `--lidar-config` thay `configs/dinh_vi_lidar_v0.json`. "LiDAR thật" thiếu bản đồ, bản đồ hỏng hay cấu hình hỏng thì thoát mã 2 trước khi mở cửa sổ hay cổng nào. Mới kiểm offscreen với nguồn giả, LiDAR mô phỏng và bản ghi C1 đứng yên.

**Xóa lỗi bo (CLEAR_FAULT)** (thêm 02/10/2026, T15) dùng chính cổng đã chọn ở nhánh VehicleIO hoặc Quan sát, khi chưa chạy: giao diện hỏi xác nhận, mở cổng nếu chưa mở, gửi HELLO, đọc khung telemetry đầu tiên bo gửi sau lúc bấm; chỉ khi bo đang FAULT và telemetry báo nút dừng khẩn đã nhả (`ESTOP_INPUT` = 0) mới gửi đúng một CLEAR_FAULT, rồi đọc khung kế tiếp và đóng cổng. Không ARM, không COMMAND; bo về DISARMED và vẫn phải ARM qua **Bắt đầu đỗ**. Mỗi lần bấm một dòng `board_actions.csv`, xuất cùng log VehicleIO (mục 4); báo cáo hiện ngay trong thẻ. Nút bị khóa với bo mô phỏng của giao diện (mỗi lần Bắt đầu đỗ tạo bo mới ở DISARMED) và khi đang chạy. Mới thử với bo mô phỏng và cổng serial giả, CHƯA THỬ với ESP32-S3; mở cổng có thể làm bo khởi động lại qua DTR/RTS (CHƯA KIỂM). *(02/10/2026: cổng mà liên kết đang giữ mở từ lần Bắt đầu đỗ trước (bước 0c) thì nút dùng luôn và không đóng; với bo ảo QEMU nút không hỏi xác nhận.)*

[Giao thức](docs/GIAO_THUC_XE.md), [quan sát](docs/CHE_DO_QUAN_SAT.md), [firmware](firmware/esp32_vehicle/README.md), [bo ảo QEMU và các trình giả lập đã thử](docs/MO_PHONG_FIRMWARE.md). Sơ đồ 2.3 và 2.4 (một lần chạy qua VehicleLink) trong [Sơ đồ hệ thống](docs/SO_DO_HE_THONG.md).

### Firmware và bo ảo QEMU

Hiện trạng 30/09/2026: lõi C++ `src/core` khớp bản tham chiếu Python trên máy tính (703 check, 0 lệch, 29/09/2026); cả firmware đã biên dịch cho ESP32-S3, 0 lỗi, 0 cảnh báo (29/09/2026); firmware thật chạy trong bo ảo QEMU trên máy bàn, phần mềm phía laptop (`SerialVehicleIO`, cũng chạy trên máy bàn) nói chuyện với nó qua `socket://` (30/09/2026); laptop trình diễn chưa chạy bo ảo. CHƯA nạp, CHƯA chạy trên bo thật nào vì chưa có bo. Kết quả trong bo ảo là giả lập, không phải số đo phần cứng. *(Cập nhật 02/10/2026: giao diện chạy được bo ảo này và cả phiên đỗ qua nó, với xe mô phỏng phía laptop; xem đoạn "Bo ảo QEMU" ở trên. Firmware không đổi.)*

Công cụ trên máy bàn, đều ngoài repo ([biên bản chuyển máy](docs/CHUYEN_MAY_BAN.md) mục 6–8): PlatformIO và QEMU ở ổ D; g++, cmake và Ninja thuộc gói WinLibs cài bằng winget cho tài khoản người dùng, ở `%LOCALAPPDATA%\Microsoft\WinGet\Packages\` trên ổ C (đường dẫn gói ở cuối [bằng chứng test host](docs/evidence/chuyen_may_20260929/firmware_host_20260929.txt); cmake và Ninja cùng thư mục `mingw64\bin`, kiểm bằng `Get-Command` ngày 30/09/2026, không lưu log):

| Công cụ | Dùng cho | Trên máy bàn |
|---|---|---|
| g++ và cmake trên PATH | Test host của lõi C++ | g++ 16.1.0 MinGW-w64 UCRT, cmake 4.4.1, Ninja: cùng gói WinLibs, ổ C |
| PlatformIO Core | Biên dịch env `esp32s3` (bản nạp vào xe) và `esp32s3_qemu` (chỉ cho bo ảo) | 6.2.0 trong venv riêng `D:\xetulai\_platformio\penv`; nền tảng ở `D:\xetulai\_platformio\core` (biến `PLATFORMIO_CORE_DIR`) |
| QEMU của Espressif 9.2.2 | Bo ảo | `D:\xetulai\_platformio\qemu` |

Đường dẫn QEMU và PlatformIO khai trong [configs/thiet_bi.json](configs/thiet_bi.json) (khóa `qemu_xtensa`, `platformio_python`, `platformio_core_dir`); đổi máy chỉ sửa tệp này. Máy không có QEMU hay PlatformIO vẫn chạy được mọi phần khác; 7 test chạy firmware thật trong QEMU tự bỏ qua (6 tới 30/09/2026; 02/10/2026 thêm test phiên đỗ qua bo ảo), và giao diện báo "Máy này chưa cấu hình bo ảo" khi chọn bo ảo. Máy không có cmake hay trình biên dịch C++ trên PATH thì 2 test host tự bỏ qua.

Kiểm vector mẫu chung Python ↔ C++, trong thư mục có `pyproject.toml`:

```powershell
./.venv/Scripts/python.exe -X utf8 -m autopark.transport.vectors --check
```

Lệnh in `... vectors.json is up to date` (mã thoát 0), hoặc báo tệp cũ (mã thoát 1) khi `firmware/esp32_vehicle/test/vectors.json` khác bản sinh lại từ Python. `--write` ghi lại tệp đó; chỉ dùng khi đã quyết định đổi hành vi của bản tham chiếu Python.

Test host của lõi C++, trong `firmware/esp32_vehicle` (`--config` và `-C` dành cho Visual Studio; Ninja bỏ qua):

```powershell
cmake -S test/host -B build/host -DCMAKE_BUILD_TYPE=Release
cmake --build build/host --config Release
ctest --test-dir build/host -C Release --output-on-failure
```

Kết quả 29/09/2026 trên máy bàn: `703 checks, 0 failures` ([bằng chứng](docs/evidence/chuyen_may_20260929/firmware_host_20260929.txt)). Nếu báo lệch: bản tham chiếu Python là chuẩn, sửa C++ cho khớp ([README firmware](firmware/esp32_vehicle/README.md), mục "Cách kiểm trên máy tính").

Biên dịch cho ESP32-S3 (không nạp), trong `firmware/esp32_vehicle`, bằng python có gói platformio (máy bàn: đường dẫn ở khóa `platformio_python`):

```powershell
D:\xetulai\_platformio\penv\Scripts\python.exe -m platformio run -e esp32s3
```

Máy khác: cài PlatformIO (`pip install platformio`) trong một venv riêng, không cài vào `.venv` hay `.venv-train`; ổ hệ thống chật thì đặt `PLATFORMIO_CORE_DIR` sang ổ khác trước lần chạy đầu ([biên bản chuyển máy](docs/CHUYEN_MAY_BAN.md) mục 5, 7); rồi chạy lệnh trên bằng python của venv đó (hoặc `pio run -e esp32s3`). Lần đầu tải nền tảng `espressif32 @ 7.1.3` (≈ 2,5 GB). Kết quả 29/09/2026: 0 lỗi, 0 cảnh báo ([bằng chứng](docs/evidence/chuyen_may_20260929/firmware_esp32_20260929.txt)). Chưa chạy lệnh nạp (`-t upload`) nào: chưa có bo.

Bo ảo, trong thư mục có `pyproject.toml` (công cụ lấy từ `configs/thiet_bi.json`):

```powershell
# build env esp32s3_qemu, chạy bo ảo, HELLO + 2 s telemetry, in kết quả rồi tắt
./.venv/Scripts/python.exe -X utf8 -m autopark.transport.qemu_board kiem
# chạy bo ảo ở socket://127.0.0.1:5555 (monitor HMP ở cổng 5556) tới khi Ctrl+C
./.venv/Scripts/python.exe -X utf8 -m autopark.transport.qemu_board chay
# 14 test, 7 trong đó chạy firmware thật trong QEMU (từ 02/10/2026)
./.venv/Scripts/python.exe -X utf8 -m pytest tests/test_firmware_qemu.py
```

`--no-build` dùng ảnh đã build, không gọi PlatformIO; `chay` nhận thêm `--port`, `--monitor-port`, `--workdir`. `kiem` thoát 0 khi nhận ít nhất 30 khung trong cửa sổ 2 s, 1 khi ít hơn, 2 khi thiếu công cụ, build hỏng hoặc QEMU không khởi động. Lần build đầu của env mất vài phút. Khi `chay` đang chạy, từ Python: `SerialVehicleIO.open("socket://127.0.0.1:5555")`.

Kết quả trên máy bàn, 30/09/2026 (bo ảo, không phải bo thật):
- `kiem` với cách đếm đã sửa, hai lượt: 40 và 39 khung trong 2 s (≈ 20 Hz), cộng 16 khung nhận trước đó lúc chờ bo ra khỏi BOOT ([kiem_bo_ao_dem_rieng.txt](docs/evidence/mo_phong_20260930/bo_ao_30092026/kiem_bo_ao_dem_rieng.txt)). Hai lượt ghi trước đó (10:13 và 13:47) in "55 khung trong 2 s" vì bản cũ đếm gộp cả các khung nhận trước cửa sổ đo (16 + 39).
- Chạy lặp `tests/test_firmware_qemu.py` 10 lượt trên `ebbec83`: 10/10 lượt đạt cả 13 test (6 trong đó chạy firmware thật trong QEMU), mỗi lượt 9–10 s ([chay_lap_test_bo_ao_ebbec83.txt](docs/evidence/mo_phong_20260930/bo_ao_30092026/chay_lap_test_bo_ao_ebbec83.txt)).

Giới hạn: bản `esp32s3_qemu` khác bản nạp vào xe ở hai chỗ (Serial qua UART0, flash DIO); không nạp bản này vào xe. Bo ảo không có LEDC (xung ESC/servo), GPIO vào (E-stop), I2C, task watchdog kích hoạt hay USB-CDC thật; chạy được ở đây không chứng minh gì về bo thật ([MO_PHONG_FIRMWARE.md](docs/MO_PHONG_FIRMWARE.md) mục 1). Sơ đồ 6.6 (các tầng kiểm chứng firmware) và 6.7 (build và dựng bo ảo) trong [Sơ đồ hệ thống](docs/SO_DO_HE_THONG.md).

## 10. Cấu trúc mã

| Thư mục | Vai trò |
|---|---|
| `autopark/domain/` | Dữ liệu, cấu hình, hợp đồng cảm biến |
| `autopark/application/` | Phiên đỗ (`session.py`), nối phiên với VehicleIO (`vehicle_link.py`), phát lại log lần chạy qua VehicleIO (`vehicle_replay.py`), kiểm số lần đổi chiều trước khi chạy (`cusp_policy.py`, từ 02/10/2026 cả giới hạn theo kịch bản nghiệm thu); nguồn tư thế LiDAR của phiên (`lidar_pose_source.py`, T2) |
| `autopark/ui/` | Cửa sổ đỗ xe (`main_window`), bàn thử LiDAR + AI (`lidar_app`, `lidar_dock`, `camera_dock`), `rig_app`, `calib_app`, `roi_app`, `label_app`; ô nháy của dấu đồng bộ (`sync_flash`); bo ảo QEMU của thẻ Bo điều khiển (`qemu_runner`); ngăn ghi cảm biến trong phiên đỗ (`record_dock`, T3); tham chiếu trên cao R1 (`overhead_app`, T4); nhãn EcoQoS ở thanh trạng thái (`process_status`) |
| `autopark/planning/`, `autopark/control/` | Tìm đường, bám đường |
| `autopark/geometry/`, `autopark/simulation/` | Va chạm, động học, phản hồi giả |
| `autopark/perception/` | AI, hiệu chuẩn, ROI, BEV; tờ marker ArUco (`aruco_sheet`) |
| `autopark/lidar/`, `autopark/video/` | Nguồn scan/ảnh và công cụ đo; dựng bản đồ nhiều chỗ đặt (`map_builder`), bộ ghép định vị (a) + (b) (`pose_estimator`), cấu hình gá và ngưỡng (`pose_config`), LiDAR mô phỏng (`synthetic`) cho T2; ghi video camera trên cao với stamp perf_counter (`video/overhead_record.py`, T4) |
| `autopark/fusion/`, `autopark/rig/` | Hợp nhất, bàn thử; ghi cảm biến trong phiên đỗ (`rig/session_recording.py`, T3) |
| `autopark/transport/`, `firmware/` | Giao thức, VehicleIO (bo mô phỏng, cổng serial), bo ảo QEMU qua `socket://` (`qemu_board.py`, `socket_port.py`), bo ảo trong phiên đỗ với xe mô phỏng phía laptop (`qemu_plant.py`, 02/10/2026), firmware C++ |
| `autopark/safety/` | Thời hạn dữ liệu; tiêm lỗi có kiểm soát (`fault_injection.py`, T6: chỉ test và công cụ diễn tập dùng) |
| `autopark/storage/`, `autopark/evaluation/` | Lưu, replay, kiểm chứng; chấm một lần chạy (`score_run`, `reference_pose`), dấu đồng bộ video–log (`sync_marks`), diễn tập tiêm lỗi (`fault_drill`), đo EcoQoS và vòng 50 Hz của giao diện (`ecoqos_gui`, `ecoqos_chay`), sinh tệp sa bàn nghiệm thu (`acceptance_scenarios`), tham chiếu trên cao R1 (`overhead_ref`, `overhead_tc1`, `sync_video`, cảnh tổng hợp `overhead_synth`) |
| `autopark/estimation/` | Chỗ dành cho định vị và bản đồ quan sát của phiên đỗ; chưa có mã. Từ 02/10/2026 nguồn tư thế LiDAR của phiên nằm ở `application/lidar_pose_source.py` và `lidar/pose_estimator.py` (T2), dùng `lidar/localize.py`, `lidar/scan_odometry.py` |
| `autopark/image_io.py`, `autopark/power_throttling.py` | Đọc/ghi ảnh khi đường dẫn có dấu; tắt EcoQoS cho tiến trình: pytest, QEMU (theo pid) và, từ 02/10/2026, ứng dụng và công cụ đo qua `apply_ecoqos_policy` (nhãn trạng thái: `ui/process_status.py`) |
| `configs/`, `scenarios/`, `tests/` | Tham số, sa bàn, kiểm thử; `configs/nguong_nghiem_thu.json`: bản sao ngưỡng nghiệm thu ĐỀ XUẤT – CHỜ CHỐT cho công cụ chấm; `configs/vehicle_nghiem_thu.json` + `configs/vehicle_io_sim_nghiem_thu.json`: xe nghiệm thu 0,10 m/s và bo mô phỏng đi cùng (02/10/2026); `scenarios/nghiem_thu/`: 9 tệp sa bàn gắn kịch bản nghiệm thu DO-1 … DO-6 (mức MP); `configs/bo_ao_qemu.json`: tham số GIẢ ĐỊNH của xe mô phỏng phía laptop cho bo ảo; `configs/dinh_vi_lidar_v0.json`: gá LiDAR (GIẢ ĐỊNH – CHƯA ĐO), điều kiện tiên quyết và ngưỡng của nguồn tư thế LiDAR; `configs/tham_chieu/`: cấu hình marker trên xe (mẫu GIẢ ĐỊNH `xe_gia_v0.json`) |

Đơn vị: mét, giây, radian. Pose tại tâm trục sau; x hướng trước, y trái, yaw dương ngược chiều kim đồng hồ.

## 11. Khi không chạy được

| Biểu hiện | Kiểm tra |
|---|---|
| Không gọi được Python | Cài Python và sửa PATH |
| Thiếu package `autopark`/`run_app.py` | Đứng đúng thư mục có `pyproject.toml` |
| Thiếu torch | Cài và dùng `.venv-train` |
| Thiếu `best.pt` | Chép checkpoint hoặc train lại |
| AI bị chặn hiệu chuẩn | Làm nội tham → ngoại tham → ROI, đọc lý do trên UI |
| LiDAR không kết nối | Xem số COM trong Device Manager (không thấy cổng thì cài driver CP210x), sửa `lidar_port` trong `configs/thiet_bi.json` (mục 7); tránh nhầm cổng bo xe |
| Venv báo `No Python at ...` sau khi chép từ máy khác | Chạy lại `cai_dat.cmd` / `cai_dat_train.cmd` (mục 2, 5) |
| `import autopark` hỏng khi chạy ngoài thư mục repo, sau khi đổi tên hay dời thư mục | `pip install -e . --no-deps` ở `.venv` và `.venv-train` (mục 5) |
| Traceback hiện đường dẫn của máy cũ sau khi chép repo | Xóa các thư mục `__pycache__` ngoài venv |
| Ảnh không đọc/ghi được khi đường dẫn có dấu | Mã dự án đã xử lý qua `autopark/image_io.py` hoặc hàm tương đương; mã mới dùng `image_io` thay vì gọi thẳng `cv2.imread/imwrite`, vốn hỏng lặng lẽ với đường dẫn có dấu (ví dụ thư mục repo cũ `D:\gấp\...`, dùng tới chiều 29/09/2026; repo nay ở `D:\xetulai`, nhưng thư mục dữ liệu vẫn có thể có dấu) ([biên bản](docs/CHUYEN_MAY_BAN.md) mục 3) |
| AI không đủ bốn luồng | Kiểm khung hỏng, nhịp camera và USB |
| Test có hạn giờ (`planner_budget`) hỏng TIMEOUT hoặc TRACKING_FAILED | Kiểm tệp JUnit (khi chạy với `--junitxml`) có `ecoqos=off`, hoặc chạy thêm `-v` để thấy dòng `EcoQoS của tiến trình pytest: off`; không đặt `AUTOPARK_KEEP_ECOQOS=1`; chạy khi máy rảnh, tách khỏi coverage và chiến dịch tải CPU (mục 4) |
| Lập đường hết hạn (TIMEOUT, TRACKING_FAILED ở 8 s) khi cửa sổ ứng dụng bị thu nhỏ | Xem nhãn EcoQoS ở góc phải thanh trạng thái. "EcoQoS: tắt" là bình thường. Chữ vàng: đang đặt `AUTOPARK_KEEP_ECOQOS=1`, bỏ biến đó rồi mở lại. Chữ đỏ: Windows không nhận yêu cầu tắt, đừng thu nhỏ cửa sổ khi đang lập đường hay đang chạy ([biên bản](docs/CHUYEN_MAY_BAN.md) mục 10.1) |
| `qemu_board` thoát mã 2, báo không thấy QEMU hoặc thiếu `platformio_python` | Sửa đường dẫn trong `configs/thiet_bi.json` (mục 9); máy không dùng bo ảo thì bỏ qua, 7 test chạy QEMU tự bỏ qua |
| QEMU tự thoát lúc khởi động (espressif/qemu#175) | `QemuBoard` tự khởi động QEMU tối đa 5 lần (thử lại tới 4 lần); vẫn hỏng thì đọc `qemu.err` trong thư mục mà thông báo lỗi chỉ ra |
| Test bo ảo hỏng vì firmware chốt LOOP_OVERRUN | Máy bận làm QEMU trễ nhịp; chạy lại khi máy rảnh ([MO_PHONG_FIRMWARE.md](docs/MO_PHONG_FIRMWARE.md) mục 1) |
| Bắt đầu đỗ với bo ảo báo "bo ảo chưa chạy" | Bấm **Khởi động bo ảo** ở thẻ Bo điều khiển, chờ dòng "Bo ảo đang chạy" (lần build đầu vài phút) |
| "đang có một lần build env esp32s3_qemu khác …" | Một pytest, lệnh `qemu_board` hay cửa sổ khác đang build: chờ nó xong; khóa `.pio/autopark_esp32s3_qemu.lock` tự nhả khi tiến trình đó thoát |
| "HELLO_ACK có boot_id …, khác bo ảo đã khởi động" | Cổng không phải bo ảo này hoặc chip ảo đã khởi động lại: **Tắt bo ảo** rồi **Khởi động bo ảo** lại |
| Bắt đầu đỗ với bo ảo bị từ chối vì FAULT LOOP_OVERRUN | Máy bận làm QEMU trễ nhịp: giảm tải máy, bấm **Xóa lỗi bo**, thử lại |
| Bắt đầu đỗ ở VehicleIO với bo ảo bị từ chối vì LIMITS_MISMATCH | Đang dùng xe nghiệm thu (0,10 m/s) mà firmware biên dịch 300 mm/s (suy ra từ mã): dùng xe mặc định với bo ảo, hoặc Quan sát; bản firmware 100 mm/s CHƯA LÀM (mục 9) |
| "Máy này chưa cấu hình bo ảo" | Thiếu hay sai `qemu_xtensa` trong `configs/thiet_bi.json` (mục 9) |
| Thanh trạng thái báo "Không đọc được configs/bo_ao_qemu.json (telemetry_period_ms phải trong [20, 100] ms …)" | Sửa `telemetry_period_ms` về 20..100 (mặc định 20): io cần ngưỡng mất liên lạc 0,3 s ≥ 3 chu kỳ. Tới khi sửa, giao diện dùng tham số mặc định của xe mô phỏng |
| Bắt đầu đỗ với bo COM và "LiDAR thật" bị từ chối START_POSE_UNVERIFIED | Đúng thiết kế: gá LiDAR chưa đo, p04, DV-2, DV-1 chưa đạt (`configs/dinh_vi_lidar_v0.json`), hoặc vòng quét đang là bản ghi phát lại ([nguồn tư thế LiDAR](docs/NGUON_TU_THE_LIDAR.md)) |
| `run_app.py` thoát mã 2, báo tham số không nhận | Từ 02/10/2026 chỉ nhận đường dẫn kịch bản, `--max-cusps N`, `--warn-cusps N` và `--vehicle-config TỆP` (mục 3); tệp xe thiếu hay hỏng cũng thoát mã 2, kèm tên tệp và lý do |
| `run_app.py` (hay `ui.lidar_app --scenario`) thoát mã 2, báo "không có kịch bản … (tệp sa bàn gắn nghiệm thu)" hay lỗi tệp ngưỡng | Tệp sa bàn có trường `acceptance` mà `configs/nguong_nghiem_thu.json` không có khóa đó hay bị hỏng: sửa thẻ (mã dạng DO-1, biến thể ở `variant`) hoặc tệp ngưỡng. Trong cửa sổ, "Mở…" tệp như vậy hiện hộp "Không mở được kịch bản" và giữ kịch bản cũ |
| **Lưu phiên…**, **Xuất log CSV…**, **Dấu đồng bộ · F8** hay **Xóa lỗi bo** bị mờ | Ba nút đầu khóa khi xe đang chạy hoặc đang dừng (RUNNING, STOPPING): chờ xe dừng hẳn. **Xuất log CSV…** còn mờ (và **Lưu phiên…** bị ẩn) khi chưa có gì để ghi: chưa chạy hay lái tay lần nào, và liên kết đang chọn chưa có START bị từ chối hay lần Xóa lỗi bo. Xóa lỗi bo chỉ dùng ở nhánh VehicleIO hoặc Quan sát với bo chọn ở cổng COM (hay bo ảo QEMU đang chạy, từ 02/10/2026), khi phiên đang chỉnh hoặc sẵn sàng; tooltip nêu lý do khóa (mục 9) |

[Mục lục kỹ thuật](docs/README.md) · [Sơ đồ hệ thống](docs/SO_DO_HE_THONG.md).
