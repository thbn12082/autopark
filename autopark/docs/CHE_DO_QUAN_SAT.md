# Nối `VehicleIO` vào phiên đỗ xe và chế độ quan sát

Tài liệu này mô tả cách phiên đỗ xe (`Session`) chạy qua `VehicleIO`, tức lớp giao tiếp với bo điều khiển trên xe, và
chế độ quan sát, trong đó người lái cầm lái còn phần mềm chỉ tính và ghi lệnh. Nó dành cho người cần chạy, đọc log hay
sửa ba nhánh chạy của phiên. Giao thức, firmware và bản thân `VehicleIO` xem ở [GIAO_THUC_XE.md](GIAO_THUC_XE.md); bo ảo
QEMU ở [MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md); nguồn tư thế LiDAR ở
[NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md). Nội dung gốc viết ngày 24/09/2026; các phần thêm sau đó ghi rõ ngày.

Tài liệu bám [kế hoạch v3.1](../../KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) mục 9. Giai đoạn (GĐ) 5 yêu cầu `VehicleIO` có
nhánh mô phỏng và nhánh phần cứng. GĐ 9 yêu cầu chế độ quan sát ("người lái, phần mềm tính đường/lệnh nhưng không gửi
chấp hành") và "trước START kiểm tra lại trạng thái thực". Mục 10 của kế hoạch quy định mất liên lạc hay kết nối lại
không được tự chạy tiếp.

## Tóm tắt

Hiện trạng tính đến 02/10/2026, ngày của các phần mới nhất trong tài liệu:

- **Ba nhánh chạy**, chọn ở ô "Nhánh chạy khi bấm Bắt đầu đỗ": SIM (mặc định, giữ nguyên mô phỏng GĐ 0), VEHICLE_IO
  (phần mềm lái, lệnh đi qua `VehicleIO` tới bo) và OBSERVE (người lái cầm lái, phần mềm không gửi COMMAND nào). Xem
  mục 1.
- **Mọi kết quả ở đây là mô phỏng hoặc giả lập.** Chưa có ESP32-S3, MN300, encoder hay AS5600. Không lần chạy nào trong
  tài liệu này dùng bo hay xe thật.
- **Đã có và đã kiểm bằng test:** kiểm trạng thái thật trước START (mục 3); các quy tắc an toàn như "đã dừng thì không
  chạy tiếp" (mục 4); log tám tệp của mỗi liên kết (mục 5); phát lại log lần chạy (T9, mục 5.1); thẻ "Bo điều khiển" với
  "Kiểm kết nối bo" và nút "Xóa lỗi bo (CLEAR_FAULT)" (T15, mục 6); tiêm lỗi có kiểm soát (T6, mục 7.1).
- **Bo ảo QEMU chạy được cả phiên đỗ** với xe mô phỏng phía laptop: bằng bo ảo giả trong test, và bằng QEMU thật trong
  một test và một lần chạy ứng dụng ngày 02/10/2026, khi các nút được gọi bằng mã (mục 7).
- **Nguồn tư thế LiDAR (T2)** có ở mức MP với LiDAR mô phỏng, và đã kiểm trên bản ghi C1 đứng yên. LiDAR mô phỏng chưa
  dùng được cho nghiệm thu MP, vì một số kịch bản dừng `POSE_LOST`, hay đi sát hoặc chạm vật (mục 8).
- **Bắt đầu đỗ với bo thật vẫn bị từ chối:** nguồn "Mô phỏng" bị chặn ở bước 0a; "LiDAR thật" ở VEHICLE_IO bị chặn ở
  bước 0b; Quan sát bị chặn ở `START_CHECK` vì firmware chưa đọc tốc độ và góc lái (mục 3).
- **Còn thiếu** (mục 8): chạy với ESP32-S3 và MN300, mã đọc encoder và AS5600, đưa ToF vào phiên, chốt cách đấu dây ở
  chế độ quan sát, bản firmware 100 mm/s cho xe nghiệm thu. Mọi ngưỡng ở mục 9 chưa chốt.

Ngày 02/10/2026 người dùng đồng ý làm theo các đề xuất cho bo ảo QEMU trong phiên, nguồn tư thế LiDAR (T2), xe nghiệm
thu và giới hạn đổi chiều theo kịch bản. Các ngưỡng đi kèm vẫn là đề xuất, chưa chốt.

## Từ viết tắt và tên gọi

- **SIM / VEHICLE_IO / OBSERVE**: ba nhánh chạy của phiên (mục 1). Giao diện gọi hai nhánh sau là "VehicleIO" và "Quan
  sát".
- **Lớp nối**: `VehicleLink`, nối `Session` với `VehicleIO` và nguồn tư thế.
- **Bo mô phỏng**: `SimVehicleIO` + `FirmwareModel` (bản tham chiếu Python của firmware), chạy trong ứng dụng.
- **Bo ảo (QEMU)**: firmware C++ thật chạy trong trình giả lập QEMU trên máy tính, nói chuyện với laptop qua
  `socket://`.
- **Bo COM, bo thật**: bo nối qua cổng serial thật, tức ESP32-S3 trên xe. Hiện chưa có bo này.
- **Cổng serial giả**: cổng giả dùng trong test (`FirmwareSerialLoopback` với `ManualClock`, hay một cổng giả theo đồng
  hồ tường); đầu kia là `FirmwareModel`.
- **Offscreen**: giao diện Qt chạy mà không hiện cửa sổ, dùng trong test.
- **T1–T15**: các công cụ nghiệm thu ở [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 7, ví dụ T2 nguồn tư thế
  thật, T9 phát lại log, T13 sự kiện dừng trong log, T15 nút CLEAR_FAULT.
- **MP, XT**: mức thử mô phỏng và xe thật (kịch bản nghiệm thu mục 1.2). DO-, DI-, AT-, DV- là mã kịch bản nghiệm thu;
  N-… là mã ngưỡng ở [NGUONG_NGHIEM_THU_DE_XUAT.md](NGUONG_NGHIEM_THU_DE_XUAT.md).
- **Đợt 1, đợt 2 (02/10/2026)**: hai đợt thay đổi trong cùng ngày. Đợt 1 là các công cụ nghiệm thu T6, T9, T12–T15. Đợt
  2, gộp sau, thêm bo ảo QEMU trong phiên, nguồn tư thế LiDAR (T2), xe nghiệm thu và ghi cảm biến trong phiên (T3).
- **EcoQoS**: chế độ tiết kiệm của Windows 11, có thể hạ tốc một tiến trình.

## Mức bằng chứng

Mặc định, mọi lần chạy trong tài liệu này đi qua chuỗi `Session` → `VehicleLink` → `SimVehicleIO` → byte giao thức →
`FirmwareModel` → cơ cấu chấp hành giả định → `SimVehicle`. Tư thế xe lấy thẳng từ mô phỏng. Không số nào dưới đây là số
đo trên xe hay trên bo.

Các đường khác cũng chỉ là mô phỏng hoặc giả lập:

- Phép thử đồng hồ ở mục 7 và một số phép thử vòng điều khiển treo dùng `SerialVehicleIO` với cổng serial giả; đầu kia
  vẫn là `FirmwareModel`.
- Bo ảo QEMU (từ 02/10/2026): firmware thật chạy trong QEMU, còn tốc độ, góc lái và tư thế lấy từ một xe mô phỏng phía
  laptop (mục 2, 3, 6; [MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md) mục 1.1). Phiên chạy qua bo ảo bằng bo ảo giả trong
  test, và bằng QEMU thật trong một test và một lần chạy ứng dụng mà các nút được gọi bằng mã (mục 7).
- Nguồn tư thế LiDAR (T2, từ 02/10/2026): LiDAR mô phỏng đi với bo mô phỏng; C1 thật hay bản ghi đi với bo COM, mới kiểm
  trên bản ghi C1 đứng yên.

Các công cụ nghiệm thu thêm ngày 02/10/2026 — sự kiện dừng của phiên trong log (T13), nút "Xóa lỗi bo" (T15), phát lại
log (T9), dấu đồng bộ video–log (T14), giới hạn số lần đổi chiều (T12), tiêm lỗi có kiểm soát (T6) — được kiểm với bo mô
phỏng, cổng serial giả và giao diện offscreen. Đợt 2 kiểm thêm một phần với bo ảo giả: dừng giữa lần chạy, "Xóa lỗi bo",
xuất gói và phát lại (mục 7). Với QEMU thật chỉ có các lần chạy COMPLETED. Chưa công cụ nào chạy qua phiên với ESP32-S3,
LiDAR thật hay camera thật.

## Mã và test

Phần nền (24/09/2026):

- **Lớp nối, ba chế độ, thế giới gương, log:**
  [`autopark/application/vehicle_link.py`](../autopark/application/vehicle_link.py).
- **Móc vào phiên** (chọn nhánh, vòng điều khiển, dừng):
  [`autopark/application/session.py`](../autopark/application/session.py).
- **Ô chọn nhánh chạy trong giao diện:** [`autopark/ui/main_window.py`](../autopark/ui/main_window.py), ngăn "Mô phỏng".
- **Test:** [`tests/test_session_vehicle.py`](../tests/test_session_vehicle.py).
- **Cấu hình bo mô phỏng mà giao diện dùng:** [`configs/vehicle_io_sim.json`](../configs/vehicle_io_sim.json), toàn số
  giả định. Từ 02/10/2026 giao diện chọn tệp `configs/vehicle_io_sim*.json` có `vehicle_config` trỏ đúng tệp xe đang
  dùng (`transport/vehicle_io.choose_sim_io_config`); không có thì dùng `vehicle_io_sim.json`. Xe nghiệm thu
  `vehicle_nghiem_thu.json` đi cùng `vehicle_io_sim_nghiem_thu.json`.

Phần thêm sau:

- **So giới hạn bo, bo thật chưa có tư thế, "Kiểm kết nối bo", thẻ "Bo điều khiển"** (tối 24/09/2026).
  - Mã: `vehicle_link.py`, `transport/vehicle_io.py`, `ui/main_window.py`.
  - Test: [`tests/test_vehicle_board_ui.py`](../tests/test_vehicle_board_ui.py).
- **Sự kiện dừng của phiên trong log** (T13, 02/10/2026): dòng `session_stop` của `events.csv`, cột `t_perf`, khóa
  `clock` của `link.json`.
  - Mã: `vehicle_link.py` (`EVENT_FIELDS`, `SESSION_STOP`, `log_session_event`, `write_logs`), `session.py`
    (`_log_session_event`, `_add_safety_event`, `request_stop(code=, source=)`), `fusion/bridge.py`, `ui/lidar_dock.py`,
    `ui/camera_dock.py`.
  - Test: [`tests/test_session_stop_log.py`](../tests/test_session_stop_log.py), `tests/test_lidar_dock_ui.py`,
    `tests/test_camera_dock_ui.py`.
- **Nút "Xóa lỗi bo (CLEAR_FAULT)", tệp `board_actions.csv`** (T15, 02/10/2026).
  - Mã: `vehicle_link.py` (`VehicleLink.clear_fault`, `BoardFaultClear`), `ui/main_window.py` (`_clear_board_fault`).
  - Test: `tests/test_vehicle_board_ui.py -k clear_fault`,
    `tests/test_session_vehicle.py::test_fault_refused_start_then_link_clear_fault_then_start`.
- **Xuất gói và phát lại log của lần chạy qua `VehicleIO`** (T9, 02/10/2026).
  - Mã: [`autopark/application/vehicle_replay.py`](../autopark/application/vehicle_replay.py), `vehicle_link.py` (băng
    `poses.csv`, `clock.csv`), `storage/run_store.py` (`export_run`, `replay_vehicle_run`, `replay_run`),
    `evaluation/replay.py`, `ui/main_window.py` (`_export_log`).
  - Test: [`tests/test_run_store_vehicle.py`](../tests/test_run_store_vehicle.py).
- **Giới hạn số lần đổi chiều trước START** (T12, 02/10/2026).
  - Mã: [`autopark/application/cusp_policy.py`](../autopark/application/cusp_policy.py), `session.py` (`start_run`,
    `cusp_limit`, `replace_scenario`), `ui/main_window.py`. Giới hạn theo kịch bản (cũng từ 02/10/2026):
    `domain/types.py` (`AcceptanceTag`), `evaluation/acceptance_scenarios.py`, `scenarios/nghiem_thu/`.
  - Test: `tests/test_cusp_policy.py`, `tests/test_cusp_acceptance.py`.
- **Dấu đồng bộ video–log ở cockpit** (T14, 02/10/2026).
  - Mã: [`autopark/evaluation/sync_marks.py`](../autopark/evaluation/sync_marks.py), `ui/sync_flash.py`,
    `ui/main_window.py`.
  - Test: `tests/test_sync_marks.py`, `tests/test_export_log_ui.py`.
- **Tiêm lỗi có kiểm soát** (T6, 02/10/2026; chỉ dùng trong test và diễn tập).
  - Mã: [`autopark/safety/fault_injection.py`](../autopark/safety/fault_injection.py), `evaluation/fault_drill.py`,
    `SimVehicleIO.pause_host()`.
  - Test: `tests/test_fault_injection.py` (mục 7.1).
- **Bo ảo QEMU trong phiên đỗ**: xe mô phỏng phía laptop, nút "Khởi động bo ảo" (02/10/2026).
  - Mã: [`autopark/transport/qemu_plant.py`](../autopark/transport/qemu_plant.py), `vehicle_link.py`
    (`VehicleLink.qemu_board`, `QemuPlantPose`, `PlantHumanDriver`),
    [`autopark/ui/qemu_runner.py`](../autopark/ui/qemu_runner.py), `ui/main_window.py`, `configs/bo_ao_qemu.json`.
  - Test: `tests/test_qemu_plant.py`, `test_qemu_plant_timing.py`, `test_qemu_runner.py`, `test_qemu_board_ui.py`,
    `test_firmware_qemu.py::test_parking_session_through_qemu_board`.
- **Nguồn tư thế LiDAR, bước 0a/0b/0c của START, dự đoán tư thế** (T2, 02/10/2026).
  - Mã: [`autopark/application/lidar_pose_source.py`](../autopark/application/lidar_pose_source.py), `vehicle_link.py`
    (`PoseSample.status`, `LinkParams.max_pose_age_s`, `predict_pose`, `for_lidar`, `_check_pose_gate`, `release_port`),
    `ui/main_window.py` (ô "Nguồn tư thế"), `ui/lidar_app.py`.
  - Test: `tests/test_session_lidar_pose.py`, `test_lidar_pose_source.py`, `test_pose_source_ui.py`,
    `test_pose_prediction.py`, `test_bench_window_feed_and_close.py`.
- **Xe nghiệm thu, bo mô phỏng theo tệp xe, ô "Cấu hình xe"** (02/10/2026).
  - Mã: `transport/vehicle_io.py` (`choose_sim_io_config`), `storage/scenario_store.py`, `session.py` (`set_vehicle`),
    `ui/main_window.py`; cấu hình `configs/vehicle_nghiem_thu.json`, `configs/vehicle_io_sim_nghiem_thu.json`.
  - Test: `tests/test_vehicle_acceptance.py`, `tests/test_vehicle_choice_ui.py`.
- **Ghi cảm biến trong phiên** (T3, 02/10/2026; chỉ có ở `ui.lidar_app`).
  - Mã: `rig/session_recording.py`, `ui/record_dock.py`, `ui/lidar_app.py`.
  - Test: `tests/test_session_recording.py`, `test_record_dock_ui.py`, `test_session_replay_ui.py`. Chi tiết ở
    [GHI_PHAT_LAI_BAN_THU.md](GHI_PHAT_LAI_BAN_THU.md).

## 1. Ba chế độ

Phiên đỗ có ba nhánh chạy. Chúng khác nhau ở ba điểm: lệnh có tới xe không, trạng thái cho bộ bám quỹ đạo lấy từ đâu, và
ai lái.

| Chế độ | Lệnh ra xe | Trạng thái đưa vào bộ bám quỹ đạo | Ai lái |
|---|---|---|---|
| `SIM` (mặc định) | không có xe; `SimWorld` chạy thẳng theo lệnh | `SimFeedback` (phản hồi giả của GĐ 0) | phần mềm, trong mô phỏng |
| `VEHICLE_IO` | mỗi nhịp điều khiển (50 Hz) một COMMAND enable có thời hạn (mặc định 0,15 s) qua `VehicleIO` | tốc độ và góc lái lấy từ telemetry; tư thế lấy từ nguồn tư thế | phần mềm, qua bo |
| `OBSERVE` (quan sát) | **không gửi COMMAND nào**, kể cả COMMAND enable=0; bo phải ở DISARMED | như `VEHICLE_IO` | người lái |

- **SIM giữ nguyên hành vi GĐ 0.** Không chọn gì thì `Session.vehicle_link` là `None`. Khi đó `world` là `SimWorld`, còn
  phản hồi giả, snapshot và replay như cũ. Test GĐ 0 chạy lại đều đạt (mục 7).
- **Lớp nối không đổi đơn vị.** Bộ bám `TrajectoryTracker` ra lệnh bằng m/s (có dấu) và rad, cũng là đơn vị của API
  `VehicleIO`. Việc đổi sang mm/s và mrad trên dây do `speed_to_wire` / `steer_to_wire` làm. Test so từng lệnh bo nhận
  với số của bộ bám.
- **Thế giới gương.** Ở `VEHICLE_IO` và `OBSERVE`, `Session.world` là `MirroredWorld`. Nó không tích phân lệnh. Mỗi bước
  5 ms nó lấy trạng thái từ lớp nối rồi kiểm va chạm hình học với các vật cản đã biết trên sa bàn.
- Xem trước (preview) và lái tay luôn là mô phỏng GĐ 0, không đi qua `VehicleIO`.

## 2. Cái gì đo, cái gì mô phỏng

Bảng dưới cho biết mỗi đại lượng phiên dùng lấy từ đâu trong mã, trên xe thật sẽ lấy từ đâu, và hiện nay thực chất là
gì.

| Đại lượng | Nguồn trong mã | Trên xe thật (khi có) | Hiện nay |
|---|---|---|---|
| Tốc độ, góc lái | telemetry `VehicleIO` (`speed_mps`, `steer_rad`) | encoder, AS5600 qua ESP32-S3: **chưa có mã đọc** | cảm biến giả trong `SimVehicleIO`: trễ 20/10 ms, nhiễu σ 0,01 m/s / 0,3° (giả định) |
| Tư thế x, y, hướng | `PoseSource` tiêm vào lớp nối | định vị LiDAR `lidar_c1_localize` (T2); mới kiểm trên bản ghi C1 đứng yên | mặc định `SimTruthPose`: tư thế **thật** của xe mô phỏng, tức định vị lý tưởng; tùy chọn LiDAR mô phỏng |
| Bo ảo QEMU *(thêm 02/10/2026)* | `QemuPlantVehicleIO` thay `speed_mps`, `steer_rad` của telemetry; tư thế từ `QemuPlantPose` | — | xe mô phỏng phía laptop bám tham chiếu của firmware thật trong QEMU; định vị lý tưởng, mức MP |
| "Xe đứng yên" | \|tốc độ đo\| ≤ 0,01 m/s **và** tham chiếu tốc độ của bo = 0, trên telemetry còn mới | như bên trái | ngưỡng chưa chốt (bằng `standstill_mm_s` của firmware) |
| Va chạm | hình học: tư thế ước lượng so với vật cản đã biết | không phải cảm biến va chạm | như bên trái |
| Người lái (chỉ `OBSERVE`) | tay điều khiển RC lái ESC/servo, không qua ESP32 | cách đấu dây ở chế độ quan sát **chưa chốt** | `SimHumanDriver`: xe mô phỏng theo lệnh của người lái; đầu ra của bo bị bỏ qua (và bằng 0) |

**Nguồn tư thế.** Ngày 25/09/2026 dự án có định vị LiDAR chạy offline trên bản ghi (`lidar/localize.py`, commit
`b100a5d`), nhưng chưa phải nguồn tư thế của phiên (mục 8). Từ 02/10/2026 (T2) phiên có thêm hai nguồn LiDAR
([NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md)):

- `lidar_sim_localize`: LiDAR mô phỏng cộng định vị (a)+(b). Chỉ đi với bo mô phỏng, gắn cờ `simulated`.
- `lidar_c1_localize`: C1 thật hoặc bản ghi phát lại, cộng định vị trên bản đồ tĩnh. Chỉ có trong `ui.lidar_app`, không
  gắn cờ `simulated`.

**Xe mô phỏng của bo ảo QEMU.** Xe mô phỏng phía laptop (`LaptopPlant`, `SimVehicle` với giới hạn của cấu hình xe) bám
`speed_ref`, `steer_ref` của firmware thật trong QEMU, tới thời điểm của từng khung. Với các khung đứng trước khung cuối
của một lần đọc cổng, thời điểm được lùi theo đồng hồ bo (sửa ngày 02/10/2026 theo review). Số được làm tròn 1 mm/s, 1
mrad, nhiễu 0 (`configs/bo_ao_qemu.json`). Cờ SPEED_VALID, STEER_VALID của firmware vẫn bằng 0.

**Cùng đồng hồ.** `PoseSource` phải đóng dấu thời gian theo cùng đồng hồ với `VehicleIO.now()`; định vị LiDAR phải đáp
ứng điều này trước khi thay `SimTruthPose`. Từ 02/10/2026, `LidarPoseSource` đổi dấu vòng quét (perf_counter lúc vòng về
máy) sang đồng hồ io theo công thức t = io.now() − (perf_counter() − t_vòng). Nó không kẹp và không đóng dấu lại, nên
mẫu cũ mang đúng tuổi thật.

Mọi kết quả bám đường trong tài liệu này dùng định vị lý tưởng, trừ các lần chạy với LiDAR mô phỏng (T2), vẫn ở mức MP.
Chúng không nói gì về sai số định vị thật. Kết quả và giới hạn của LiDAR mô phỏng ở
[NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md) và mục 8.

## 3. Một lần chạy

Mục này đi theo một lần bấm Bắt đầu đỗ ở `VEHICLE_IO` hay `OBSERVE`: các bước kiểm trước START, việc làm ở mỗi nhịp điều
khiển, khi nào phiên buộc dừng và cách kết thúc. Nguyên tắc chung: chỉ cần một kiểm sai là START bị từ chối
(`SessionError`), phiên giữ READY và bo **không** bị bỏ lại ở ARMED.

**Thứ tự kiểm trước START.**

- Số lần đổi chiều của đường (T12): trong `Session.start_run`, trước khi gọi `begin_run`.
- Bước 0 (0a, 0b, 0c): nguồn tư thế và cổng, trong `VehicleLink.begin_run` / `_open_run`.
- Bước 1–5: kết nối, đọc khung telemetry mới, kiểm trạng thái thật, ARM hay DISARM, kiểm lại tư thế. So giới hạn của bo
  nằm giữa bước 2 và 3.

**Số lần đổi chiều (T12, thêm 02/10/2026).** `Session.start_run` so số lần đổi chiều của đường đã lập với giới hạn.
Đường vượt giới hạn thì START bị từ chối trước khi gọi `begin_run`, nên không có I/O nào với bo; bo mô phỏng của giao
diện còn chưa được dựng. Phiên giữ READY và giữ đường.

- Giới hạn đặt bằng cờ `--max-cusps N` của `run_app.py` và `ui.lidar_app`. Mặc định không chặn; con số chưa chốt.
- Tệp sa bàn có trường `acceptance` (mở bằng `run_app.py` hay `ui.lidar_app`) lấy giới hạn của kịch bản trong
  `configs/nguong_nghiem_thu.json`, theo ngưỡng N-D6 (b), là đề xuất, chưa chốt: ≤ 2 ở DO-1, DO-2, DO-3a, DO-4a; ≤ 7 ở
  DO-3b, DO-4b, DO-5, DO-6; DO-3c chỉ báo số. Bộ tệp gồm chín tệp `scenarios/nghiem_thu/*.json`. Khi đó `--max-cusps`
  chỉ siết thêm, và kiểm vẫn nằm trước `begin_run`, trước mọi I/O với bo.
- Câu từ chối nêu khóa, ví dụ "vượt giới hạn 2 của DO-1 (N-D6 (b) đề xuất, CHƯA CHỐT)".
- Qua `VehicleLink`, `start_refusals` có dòng `START_TOO_MANY_CUSPS`: nguồn `session`, `before_start`, `t_session`
  trống. `t_io` là `io.now()` khi liên kết đã có io, trống khi chưa. Nhánh SIM chỉ báo lỗi, không ghi log.
- Snapshot của lần chạy có khóa `cusps`: số lần đổi chiều đã lập và chính sách lúc bắt đầu. Tệp gắn nghiệm thu có thêm
  `cusp_rule` (nguồn, khóa, đường dẫn và SHA-256 tệp ngưỡng) và `scenario.acceptance`. Tệp không gắn giữ đúng các khóa
  cũ.
- Bằng chứng: chỉ có test (mô phỏng, bo mô phỏng, giao diện offscreen) và một lần chạy offscreen với planner thật trên
  `do1.json` (lập đường OK 0,70 s, 1 lần đổi chiều). Chưa thử với LiDAR, bo thật hay laptop.

**Bước 0: nguồn tư thế và cổng.** Bản tối 24/09/2026 chỉ có một kiểm ở đây: bo thật chưa có nguồn tư thế thì từ chối
ngay. Từ 02/10/2026 (T2 và bo ảo QEMU), bước 0 gồm các bước dưới, chạy theo thứ tự, trước bước 1
(`VehicleLink.begin_run`, `_open_run`). Chúng chỉ được kiểm với bo mô phỏng, LiDAR mô phỏng, bo ảo giả, cổng serial giả,
và QEMU thật qua một test và một lần chạy ứng dụng bằng mã. Mọi đường với bo thật chưa thử.

- **Chuẩn bị ở đầu START.** Với bo ảo QEMU, liên kết lấy bo đang chạy từ nút "Khởi động bo ảo". Bo chưa chạy thì START
  bị từ chối với `START_NO_QEMU_BOARD`, chưa có gì được mở (đoạn bo ảo cuối mục này). Với LiDAR mô phỏng, một nguồn mới
  được dựng cho bo mô phỏng mới và chạy trước START tới khi đạt điều kiện của nó (tối đa 2 s mô phỏng, xe đứng yên).
- **0a. Nguồn tư thế phải dùng được.** Nguồn không `available` thì START bị từ chối với dòng `START_NO_POSE_SOURCE`
  trong `start_refusals`.
  - Trường hợp hay gặp là chọn cổng COM với nguồn "Mô phỏng": liên kết khi đó dùng `NoPoseSource` (mục 6). START bị từ
    chối ngay: không mở cổng, không HELLO, không gửi byte nào. Lời báo nêu tên cổng và lý do: chưa có định vị thật, tư
    thế mô phỏng không được dùng với bo thật.
  - Với bo mô phỏng hay bo ảo, lời báo là "nguồn tư thế … chưa dùng được".
  - Lời từ chối nói đúng trạng thái cổng. Cổng chưa mở: "Cổng chưa được mở, không gửi gì tới bo; dùng 'Kiểm kết nối bo'
    để kiểm liên lạc". Cổng đang mở vì bước 0c của một lần START trước đã mở và liên kết còn giữ: "Cổng đang mở (liên
    kết giữ cổng giữa các lần chạy), lần này không gửi gì tới bo; 'Kiểm kết nối bo' đóng cổng này của liên kết trước khi
    kiểm (lần Bắt đầu đỗ sau mở lại)". Trước bản sửa sau review ngày 02/10/2026, lời này luôn nói "Cổng chưa được mở".
- **0b. Điều kiện tiên quyết của nguồn LiDAR** (`start_gate`).
  - Bo thật (không phải bo mô phỏng, không gắn cờ `virtual_board`) ở `VEHICLE_IO` mà điều kiện tiên quyết chưa đạt thì
    từ chối `START_POSE_UNVERIFIED`, không I/O nào. Điều kiện tiên quyết gồm đo gá LiDAR, p04, DV-2, DV-1 trong
    `configs/dinh_vi_lidar_v0.json`. Các trường hợp khác chỉ ghi mỗi mục chưa đạt thành một dòng `POSE_SOURCE_WARNING`
    (`before_start`).
  - Vòng quét của nguồn LiDAR không phải của LiDAR thật, tức evidence khác `device` (`--recording`, `--session-replay`,
    nguồn khác, ngăn LiDAR đã ngắt). Khi đó bo thật bị từ chối ở mọi nhánh, kể cả Quan sát (`START_POSE_UNVERIFIED`,
    không I/O nào). Bo mô phỏng hay bo ảo gắn cờ chỉ nhận một dòng `POSE_SOURCE_WARNING`. Luật này sửa ngày 02/10/2026
    sau review gộp đợt 2, chỉ kiểm bằng test.
  - Lời từ chối ở bước này dùng cùng câu về trạng thái cổng như bước 0a, không kèm gợi ý.
- **0c. Mở cổng.** Cổng `SerialVehicleIO.deferred` chưa mở thì gọi `reopen()`. Lỗi thì từ chối `START_NO_LINK` với lời
  "Không mở được COMx: …" hay "Không mở được kết nối tới bo ảo …". Cổng COM giữ mở giữa các lần chạy.
  `VehicleLink.close()` đóng cổng khi đổi bo, nhánh chạy, nguồn tư thế hay đóng cửa sổ; "Kiểm kết nối bo" đóng cổng
  trước khi kiểm (`VehicleLink.release_port`, mục 6). Chỉ bo ảo đóng socket sau mỗi lần chạy và sau lần START bị từ
  chối, vì QEMU chỉ phục vụ một client.
- **Điều kiện START của nguồn LiDAR** được đưa vào dòng `START_CHECK`: đã bắt, 5 vòng OK gần nhất, ≥ 8 vòng/s trong 2 s,
  trễ xử lý p95 ≤ 0,10 s, có mốc kiểm chéo. p95 > 0,05 s chỉ cảnh báo. Lỗi của móc nguồn tư thế thành dòng
  `POSE_SOURCE_HOOK_FAILED` và không bao giờ chặn bước dừng. Các ngưỡng là đề xuất, chưa chốt
  ([NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md)).

Ngoài các bước trên, `SimTruthPose` ghép với một `VehicleIO` khác `SimVehicleIO` của chính nó (bo thật hoặc bo mô phỏng
khác) bị từ chối ngay khi tạo `VehicleLink` (ValueError).

Hệ quả với bo COM:

- Nguồn "Mô phỏng" (`NoPoseSource`) bị từ chối ở 0a và không bao giờ mở cổng.
- "LiDAR thật" ở `VEHICLE_IO` bị từ chối ở 0b.
- Ở `OBSERVE` (nguồn dùng được, vòng quét của LiDAR thật), cổng được mở ở 0c, rồi HELLO và đọc 3 khung. Sau đó
  `START_CHECK` từ chối vì telemetry không có tốc độ, góc lái đo: firmware chưa có mã cảm biến (T8). Cổng vẫn giữ mở sau
  lần từ chối đó.

**Bước 1–5** (`VehicleLink.begin_run`, gọi từ `Session.start_run`):

1. Chưa có phiên thì `connect()`. Chờ bo ra khỏi BOOT.
2. Chờ **3 khung telemetry mới, nhận sau lúc bấm START**. Khung cũ có trước một thao tác vừa làm (ARM, CLEAR_FAULT...)
   không được dùng để quyết định.
3. Kiểm trạng thái thật:
   - bo không FAULT, không nhấn E-stop, không BOOT; ở `VEHICLE_IO`, bo không được đang RUNNING theo lệnh từ nơi khác;
   - có tốc độ và góc lái đo được; trung bình tốc độ đo của 3 khung ≤ 0,02 m/s và tham chiếu tốc độ của bo = 0;
   - có tư thế mới, tuổi từ 0 tới 0,15 s; mẫu "ở tương lai" cũng bị từ chối;
   - tư thế cách điểm xuất phát đã lập đường ≤ 3 cm và ≤ 5°, và không chạm vật cản.

   Kết quả kiểm được ghi thành dòng `START_CHECK`: đạt là "Đạt: ...", từ chối là "TỪ CHỐI: ...".
4. `VEHICLE_IO`: gọi `arm()`. Đây là thao tác cho phép mới, và nó gỡ chốt `TELEMETRY_STALE` của `VehicleIO`. `OBSERVE`:
   gửi DISARM (không phải lệnh chuyển động), rồi chờ một khung telemetry mới báo DISARMED và có góc lái đo được.
5. Sau ARM hay DISARM (trên bo thật có thể mất vài trăm ms), lớp nối **đọc và kiểm lại tư thế**: mới, gần điểm xuất
   phát, không chạm vật cản.

Lỗi ở bước 4–5, kể cả ngoại lệ bất kỳ từ nguồn tư thế, đều thành `SessionError`. Nếu đã gửi ARM, kể cả khi ACK hết giờ,
lớp nối gửi DISARM trước khi báo lỗi, rồi ghi `START_ABORTED`; DISARM không được xác nhận thì ghi thêm `DISARM_FAILED`.

**So giới hạn của bo, giữa bước 2 và 3** (thêm tối 24/09/2026; mới kiểm với bo mô phỏng và cổng serial giả, chưa thử với
ESP32-S3). Giới hạn trong HELLO_ACK được so với `VehicleConfig` mà planner dùng (`VehicleIO.check_limits`), với sai số
một đơn vị trên dây. Bảng hướng nguy hiểm ở [GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 7. Khớp thì chỉ thêm ", giới hạn:
khớp" vào `START_CHECK`. Lệch thì có dòng `LIMITS_MISMATCH` trước `START_CHECK`:

- `VEHICLE_IO` và lệch nguy hiểm: dòng có action STOP, START bị từ chối ("Giới hạn của bo lệch cấu hình xe..."), bo
  không bị ARM. Lệch nguy hiểm là khi bo cho phép nhanh hơn, lái gắt hơn, đổi lái hay tăng tốc nhanh hơn, phanh yếu hơn,
  hoặc góc lái nhỏ hơn đường đã lập cần.
- `VEHICLE_IO` và bo chỉ chặt hơn: dòng LOG "chỉ cảnh báo", START vẫn chạy, thanh trạng thái của giao diện hiện cảnh
  báo.
- `OBSERVE`: luôn chỉ ghi dòng LOG, vì không gửi lệnh nào.

Kết quả so ghi ở `link.json`, khóa `limits_check`. Quy tắc này là đề xuất, chưa chốt.

**Lần START bị từ chối không xóa bằng chứng của lần chạy trước.** `commands.csv`, `telemetry.csv`, `events.csv`, kết quả
và (ở nhánh mô phỏng của giao diện) bo mô phỏng của lần chạy trước giữ nguyên cho tới khi lần mới đã thật sự mở: sau ARM
ở `VEHICLE_IO`, sau khi nhận DISARMED ở `OBSERVE`, và sau bước 5. Các dòng trước START của lần bị từ chối được nối vào
`start_refusals.csv`, ví dụ `START_CHECK` "TỪ CHỐI...", `START_NO_LINK`, `START_ABORTED`, sự kiện cũ đã rút khỏi
`VehicleIO`. Vì vậy `Session.log` và `run_link` luôn trỏ cùng một lần chạy, và `START_CHECK` của lần đạt nằm trong
`events.csv` của chính lần đó. Lần bấm "Xóa lỗi bo" (T15, từ 02/10/2026) cũng không đụng tới log của lần chạy trước. Nó
thêm một dòng vào `board_actions.csv`; sự kiện `VehicleIO` gom được trong lúc bấm nằm ở cột `message` của dòng đó, không
thành dòng `before_start` của lần START sau.

**Mỗi nhịp điều khiển (20 ms).** Lớp nối lấy trạng thái đo (`observe`). Phiên dừng an toàn nếu:

- telemetry cũ hơn 0,15 s (`STALE_TELEMETRY`);
- thiếu tốc độ hoặc góc lái đo (`NO_MEASURED_STATE`);
- tư thế cũ hoặc thiếu (`STALE_POSE`). Mẫu cũ hơn `pose_age_limit_s` là cũ: 0,25 s với nguồn LiDAR, 0,15 s với nguồn
  khác;
- mẫu tư thế có `status` khác OK (T2, từ 02/10/2026): dừng với mã `POSE_LOST`, `POSE_DISAGREE` hay `POSE_UNCHECKED`,
  nguồn là id của nguồn tư thế (`lidar_sim_localize`, `lidar_c1_localize`).

Thế giới gương (`estimate`) chỉ nhận mẫu OK.

**Dự đoán tư thế** (sửa sau review 02/10/2026). Liên kết với nguồn LiDAR của giao diện (`LinkParams.for_lidar`) bật
`predict_pose`. Khi đó tư thế của mẫu OK được dời từ dấu thời gian của mẫu tới `io.now()` bằng tốc độ và góc lái đo (mô
hình xe đạp động học), trước khi vào bộ bám và thế giới gương. Việc dời chỉ xảy ra khi tuổi thô nằm trong (0;
`pose_age_limit_s`], khung telemetry còn mới và có cả tốc độ lẫn góc lái đo. Kiểm tuổi (`STALE_POSE`, kiểm START) vẫn
dùng tuổi thô. Mặc định tắt, nên `SimTruthPose`, bo ảo QEMU và băng ghi trước khi có khóa này chạy như trước. Lý do
thêm: ở MP, mẫu LiDAR tới bộ bám đã cũ 0,04–0,13 s và xe lệch tư thế thật quá khe hở của đường; DO-4a va chạm dù mọi
vòng định vị đều OK. Chỉ kiểm ở MP.

Nếu không có lỗi nào ở trên, bộ bám tính lệnh:

- `VEHICLE_IO`: gửi COMMAND. Gửi lỗi thì dừng với mã `SEND_FAILED`.
- `OBSERVE`: chỉ ghi một dòng vào `commands.csv`.

**Sự kiện buộc dừng.** Khi phiên đang chạy, `Session` gọi `VehicleLink.refresh()` ở đầu mỗi bước 5 ms. Hàm này lấy
telemetry và sự kiện đã tới laptop (bo thật: `poll(block=False)`; bo mô phỏng: `take_new()`, không tiến bo mô phỏng).
Sau đó `Session` lấy sự kiện dừng, trước nhịp điều khiển. Các sự kiện buộc dừng:

- mọi sự kiện `STOP` của `VehicleIO`: `TELEMETRY_STALE`, `SESSION_LOST`, `VEHICLE_FAULT`, `FIRMWARE_RESET`,
  `LINK_ERROR`;
- ở `VEHICLE_IO`, thêm `COMMAND_REJECTED` và `VEHICLE_STOPPED` khi laptop chưa ra lệnh dừng;
- `VEHICLE_NOT_ARMED`: telemetry báo bo đã rời ARMED/RUNNING sau khi nhận lệnh của lần chạy này;
- `OBSERVE_NOT_DISARMED`: ở chế độ quan sát mà bo ARMED/RUNNING. Lớp nối gửi DISARM ngay.

Ghi chú ngày 01/10/2026 về `FIRMWARE_RESET`: sự kiện này chỉ sinh trong `connect()` của lần chạy sau và chỉ được ghi log
trước START, nên không làm dừng lần chạy nào. Chip khởi động lại giữa lần chạy làm phiên dừng vì telemetry cũ, hoặc vì
`SESSION_LOST` (`transport/vehicle_io.py` `connect()`, `application/vehicle_link.py` `_open_run`). Telemetry cũ được bắt
bởi `STALE_TELEMETRY` của lớp nối sau 0,15 s, tới trước `TELEMETRY_STALE` sau 0,3 s.

Việc lấy sự kiện trước nhịp điều khiển chỉ có từ bản sửa tối 24/09/2026. Trước đó lớp nối chỉ gom sự kiện của
`VehicleIO` trong `pump()`, mà `pump()` chạy sau nhịp điều khiển của cùng bước. Nếu telemetry đã tới trong lúc vòng điều
khiển treo (có luồng khác đọc cổng) và bước đầu tiên khi hết treo rơi vào nhịp điều khiển, lệnh enable của nhịp đó được
gửi trước khi sự kiện được xử lý. Đó là khoảng trống mô tả ở mục 8.

**Dừng.** Ở `STOPPING`, phiên gửi COMMAND enable=0 mỗi nhịp và bo dốc về trung tính.

- Lần chạy kết thúc STOPPED khi có telemetry **mới** báo xe đứng yên.
- Sau 2,0 s kể từ lệnh dừng mà vẫn chưa xác nhận được xe đứng yên (mất telemetry, hoặc xe vẫn chạy), phiên kết thúc
  **FAULT** với mã `STOP_NOT_CONFIRMED`. Lý do: không có số đo thì phần mềm không được coi là xe đã dừng.
- Ở `OBSERVE`, phần mềm không điều khiển xe nên kết thúc quan sát ngay, không chờ người lái dừng.

**Ghi quyết định dừng vào log** (T13, thêm 02/10/2026; chỉ kiểm với bo mô phỏng và cổng serial giả). Mỗi quyết định dừng
của phiên được ghi thành một dòng có `handling` = `session_stop` trong `events.csv` (mục 5). Các quyết định đó gồm:

- mọi phần tử của `Session.safety_events`, kể cả sự kiện tới khi đã STOPPING, `STOP_NOT_CONFIRMED` và `WAIT_REPLAN`;
- mọi yêu cầu dừng khi đang chạy: nút Dừng hay phím Esc (`USER_STOP`), cầu nối hợp nhất (`FUSED_MAP_INVALID`), ngăn
  LiDAR, ngăn AI camera;
- đặt lại khi đang chạy (`USER_RESET`) và va chạm hình học (`COLLISION`).

Dòng được ghi trước `end_run`, nên thuộc lần chạy đang mở. Ghi log không gửi gì tới bo. Yêu cầu dừng lặp lại khi đã
STOPPING không thêm dòng.

**Kết thúc lần chạy** (COMPLETED, STOPPED, FAULT, hoặc đặt lại khi đang chạy): `VEHICLE_IO` gửi enable=0 rồi DISARM.
`OBSERVE` không gửi gì.

**Bo ảo QEMU** (thêm 02/10/2026, chỉ mô phỏng). Một lần chạy qua bo ảo đi như sau:

- Trước mọi I/O, liên kết bo ảo lấy bo đang chạy từ runner của nút "Khởi động bo ảo". Bo chưa chạy thì từ chối
  `START_NO_QEMU_BOARD` (dòng `start_refusals`, `t_io` theo đồng hồ liên kết) với lời "Không bắt đầu được với bo ảo
  QEMU: <lý do>. Chưa mở kết nối, không gửi gì; bấm 'Khởi động bo ảo' ở thẻ Bo điều khiển".
- Có bo thì liên kết đặt xe mô phỏng ở điểm xuất phát, thay việc người đặt xe. Sau đó nó mở `socket://127.0.0.1:<cổng>`
  ở bước 0c (không mở được thì `START_NO_LINK`) và gửi HELLO xin chu kỳ 20 ms. HELLO_ACK phải mang đúng boot_id mà bo ảo
  báo lúc khởi động; khác thì `START_NO_LINK` và không nhận phiên.
- Các kiểm START còn lại như với bo thật, kể cả so giới hạn. Firmware biên dịch cứng `max_speed_mm_s` = 300, nên xe
  nghiệm thu 0,10 m/s bị từ chối ở `VEHICLE_IO` (`LIMITS_MISMATCH`). Điều này suy ra từ mã
  ([MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md) mục 1.1).
- Bo FAULT LOOP_OVERRUN thì lời từ chối thêm "(bo ảo QEMU: máy bận làm QEMU trễ nhịp > 100 ms; giảm tải máy, bấm 'Xóa
  lỗi bo (CLEAR_FAULT)' rồi thử lại)".
- Hết lần chạy, `VEHICLE_IO` gửi enable=0 rồi DISARM. Ở cả hai nhánh, kết nối được đóng, vì QEMU chỉ phục vụ một client.

## 4. Quy tắc an toàn

Lớp nối giữ bảy quy tắc dưới đây. Tài liệu khác dẫn theo số quy tắc (ví dụ "mục 4 quy tắc 4"), nên thứ tự được giữ
nguyên.

1. **Quan sát không bao giờ gửi COMMAND.** Ở chế độ này lớp nối không gọi `send()` hay `stop()`. Ra khỏi lớp nối chỉ có
   HELLO, DISARM và REQUEST do `VehicleIO` tự gửi. Nếu thấy bo ARMED/RUNNING hoặc cờ `CMD_ACTIVE`, lớp nối gửi DISARM và
   kết thúc quan sát. Ngoài lần chạy, nút "Xóa lỗi bo" (T15, từ 02/10/2026) còn có thể gửi qua liên kết quan sát một
   PING và nhiều nhất một CLEAR_FAULT (mục 6); vẫn không có COMMAND nào.
2. **Đã dừng thì không chạy tiếp.** Sau sự kiện dừng đầu tiên **đã tới laptop**, lần chạy chỉ gửi enable=0. Đầu mỗi
   bước, trước nhịp điều khiển, lớp nối lấy mọi telemetry và sự kiện đã tới (`refresh()`), rồi `Session` chuyển sang
   dừng. Lớp nối có thêm một chốt chặn lệnh enable kể cả khi `Session` gọi sai: `command()` không gửi enable (trả
   `HALTED`) khi `_halted` đã đặt, hoặc khi còn sự kiện dừng lớp nối đã gom mà `Session` chưa lấy. Telemetry có lại
   không làm chạy tiếp; `connect()` lại cũng không, vì bo về DISARMED. Sự kiện mà khung telemetry báo nó chưa tới laptop
   thì không chặn được (mục 8). Trước bản sửa tối 24/09/2026, quy tắc này có một ngoại lệ ở pha 0 (mục 8).
3. **Chỉ START mới ARM.** Sau dừng an toàn, đường bị hủy (`path_invalidated`). Người dùng phải đặt lại, lập lại đường từ
   chỗ xe đứng rồi bấm Bắt đầu đỗ. Lúc đó `begin_run` kiểm lại trạng thái thật rồi mới `arm()`. Bo đang FAULT (ví dụ
   E-stop) thì START bị từ chối tới khi có người gọi `clear_fault()`; lớp nối không tự gọi hàm này. Từ 02/10/2026 (T15),
   người dùng gọi được nó từ giao diện bằng nút "Xóa lỗi bo (CLEAR_FAULT)" (mục 6), và lời từ chối START vì FAULT chỉ
   tới nút đó.
4. **Bo thật chạy theo thời gian thực, và vòng điều khiển không đọc chặn.** Với `VehicleIO` không phải mô phỏng
   (`realtime`), `Session.advance()` không cộng thời gian giao diện và không tua nhanh: thời gian phiên lấy theo
   `io.now() - t0` (`VehicleLink.session_time_now()`). Mỗi bước 5 ms chỉ đọc byte đã có sẵn (`poll(block=False)`), không
   chờ timeout đọc của cổng. Nhờ vậy nhịp điều khiển 50 Hz, hạn xác nhận dừng 2 s, `MAX_RUN_TIME` và cột `t_session` của
   mọi tệp log cùng bám `io.now()`. Đồng hồ mặc định của `SerialVehicleIO` là `time.perf_counter()`, vì trên Windows
   `time.monotonic()` chỉ đổi mỗi 15,625 ms (đo bằng `time.get_clock_info` trên máy bàn, Python 3.12, 24/09/2026). Liên
   kết bo ảo QEMU (từ 02/10/2026) cũng chạy theo đồng hồ tường, tức `perf_counter` của liên kết, và đi đúng đường này.
   Bằng chứng: cổng serial giả, và QEMU thật trong một test và một lần chạy ứng dụng mà các nút được gọi bằng mã (mục
   7). Chưa kiểm với bo thật (mục 8).
5. **Đóng phiên hoặc cửa sổ giữa lúc chạy `VEHICLE_IO`** gửi COMMAND enable=0 rồi DISARM trước khi đóng cổng
   (`Session.close()` → `VehicleLink.close()`). Đã kiểm trên `SimVehicleIO` + `FirmwareModel`: bo nhận enable=0 và về
   DISARMED trong 50 ms, trước khi hết hạn lệnh (0,15 s) hay watchdog liên lạc (0,5 s). Chưa kiểm trên bo thật. Thứ tự
   khi đóng cửa sổ, từ 02/10/2026:
   - Với bo ảo QEMU: đóng phiên (enable=0 + DISARM) trước, rồi mới tắt QEMU.
   - Ở `ui.lidar_app`: bước đóng phiên chạy ngay sau khi dừng ghi cảm biến, trước mọi việc có thể phải chờ. Các việc đó
     là tắt ngăn AI camera, nguồn tư thế LiDAR (≤ 1 s), ngăn LiDAR, rồi chờ bản ghi cảm biến ghi nốt (tối đa 60 s).
     Trước bản sửa sau review gộp đợt 2, enable=0 + DISARM đi sau lần chờ ghi nốt, trong lúc vòng 50 Hz đứng. Chỉ kiểm
     bằng test offscreen.
6. **Lái tay sau một lần chạy qua `VehicleIO`** bỏ liên kết của lần chạy đó khỏi phiên (`run_link = None`). Nút "Xuất
   log CSV…"/"Lưu phiên…" khi ấy chỉ ghi log lái tay, không kèm thư mục `_vehicle_io` của lần chạy trước. Giao diện còn
   kiểm thêm một lớp: chỉ ghi `_vehicle_io` khi snapshot của log hiện tại có khóa `vehicle_link`.
   - Ngoại lệ (từ 02/10/2026): log hiện tại không thuộc lần chạy qua `VehicleIO` nào, còn liên kết đang chọn chưa chạy
     lần nào nhưng đã có START bị từ chối hay lần bấm "Xóa lỗi bo". Khi đó "Xuất log CSV…" bật ngay và ghi
     `<tên>_vehicle_io/` của liên kết đó, với `commands.csv`, `telemetry.csv`, `events.csv` rỗng và `runs` = 0 trong
     `link.json`.
   - Liên kết đã chạy thì không có ngoại lệ này: log lái tay vẫn không kèm log `VehicleIO` của lần chạy cũ.
   - Sau một lần chạy qua `VehicleIO`, hai nút còn xuất gói phát lại (mục 5 và 5.1).
7. **Lớp nối không thay được đường cắt động lực phần cứng.** Cờ STOP trên laptop không chứng minh xe thật dừng được
   ([GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 0, 12).

**Bo ảo QEMU** (thêm 02/10/2026). Bo ảo có luật ghép và các lớp chặn riêng:

- `QemuPlantVehicleIO` chỉ dựng từ bo do ứng dụng mở, và chỉ nối `socket://127.0.0.1:<1..65535>`. Giao diện không có ô
  nhập URL.
- `QemuPlantPose` chỉ ghép với chính io đó, và io đó chỉ ghép với `QemuPlantPose`: không bao giờ với `SimTruthPose`,
  `NoPoseSource` hay tư thế LiDAR. Lớp bọc tiêm lỗi (`fault_inner`) được bóc ra trước khi áp luật này.
- Ba lớp chặn cầu TCP tới một ESP32 thật chiếm cổng: bo phải đang chạy, HELLO_ACK phải đúng boot_id, URL chỉ là
  loopback.
- Số của xe mô phỏng không bao giờ tới firmware.
- Liên kết bo ảo có `virtual_board` = True và không tính là phần cứng chấp hành (`hardware_actuators` = False).

Với cổng COM, nguồn "Mô phỏng" vẫn bị từ chối START (`START_NO_POSE_SOURCE`) trước khi mở cổng. Với nguồn LiDAR thật
(T2, gộp cùng ngày), bước 0c mở cổng COM ở lần Bắt đầu đỗ đầu tiên qua được bước 0a, 0b, rồi giữ cổng mở giữa các lần
chạy. Chỉ bo ảo đóng kết nối sau mỗi lần chạy (mục 3).

**Tổ hợp bo và nguồn tư thế** (T2, thêm 02/10/2026). Giao diện (`MainWindow._build_link`, ở nhánh VehicleIO và Quan sát)
chỉ cho các tổ hợp sau:

- bo ảo QEMU chỉ đi với nguồn "Mô phỏng", tức tư thế của xe mô phỏng phía laptop;
- LiDAR mô phỏng chỉ đi với bo mô phỏng;
- LiDAR thật chỉ đi với bo COM;
- trong `ui.lidar_app`, cổng đang ghi ở ô cổng của ngăn LiDAR không được nhận làm cổng bo.

Tổ hợp bị cấm thì hộp thoại "Không đổi được nhánh chạy" hiện ra, và ba ô (nhánh chạy, bo, nguồn tư thế) trở về liên kết
đang dùng. Chỉ kiểm bằng test offscreen.

## 5. Log

Mỗi liên kết ghi log riêng bằng `VehicleLink.write_logs(thư_mục)`: tám tệp, cộng vài tệp của nguồn tư thế LiDAR. Trong
giao diện, nút "Xuất log CSV…" ghi các tệp này vào thư mục `<tên>_vehicle_io/` cạnh tệp CSV, chỉ khi log hiện tại là của
một lần chạy qua `VehicleIO`; ngoại lệ ở mục 4, quy tắc 6. Sau một lần chạy qua `VehicleIO`, giao diện còn xuất một gói
phát lại được (dưới đây và mục 5.1).

Diễn biến:

- Bản 24/09/2026 ghi năm tệp: `commands.csv`, `telemetry.csv`, `events.csv`, `start_refusals.csv`, `link.json`.
- Tối 24/09/2026, `storage/run_store.export_run` được sửa để từ chối rõ ràng lần chạy qua `VehicleIO` (`VEHICLE_IO` và
  `OBSERVE`) bằng `ReplayNotSupported`, trước khi tạo thư mục nào. Cách này giữ tới khi có T9. `ReplayNotSupported` là
  lớp con của `ValueError`, lời báo tiếng Việt khi đó chỉ sang `VehicleLink.write_logs`. `replay_run` cũng từ chối gói
  có khóa `vehicle_link` trong snapshot. Test lúc đó:
  [`tests/test_run_store_vehicle.py`](../tests/test_run_store_vehicle.py), 4 test, bo mô phỏng.
- Ngày 02/10/2026, T15 thêm `board_actions.csv`; T9 thêm `poses.csv`, `clock.csv` (băng phát lại) và cho xuất gói; T13
  thêm dòng `session_stop` và cột `t_perf`. Các phần này chỉ kiểm với bo mô phỏng và cổng serial giả.

| Tệp | Nội dung |
|---|---|
| `commands.csv` | Mỗi nhịp điều khiển một dòng: lệnh bộ bám tính ra, có gửi hay không, trạng thái đo đã dùng |
| `telemetry.csv` | Mọi khung telemetry nhận được |
| `events.csv` | Sự kiện của `VehicleIO`, của lớp nối và quyết định dừng của phiên, trong lần chạy gần nhất đã mở |
| `start_refusals.csv` | Dòng trước START của **mọi** lần START bị từ chối của liên kết này |
| `board_actions.csv` | *(Thêm 02/10/2026, T15.)* Mỗi lần bấm "Xóa lỗi bo (CLEAR_FAULT)" một dòng |
| `poses.csv` | *(Thêm 02/10/2026, T9.)* Mỗi lần đọc nguồn tư thế trong lần chạy một dòng |
| `clock.csv` | *(Thêm 02/10/2026, T9.)* Mỗi lần đọc io trong lần chạy một dòng |
| `link.json` | Mô tả liên kết, tham số, kết quả, số lần chạy và số lần bị từ chối |

Chi tiết từng tệp:

- **`commands.csv`**: `t_session`, `t_io`, `mode`, `kind` (TRACK/STOP), `sent` (1 = đã gửi tới bo, 0 = không gửi),
  `seq`; mục tiêu tốc độ/góc lái; trạng thái bộ bám (`phase`, `segment`, `index`, `distance_to_end_m`,
  `lateral_error_m`, `heading_error_deg`, `done`); trạng thái đo đã dùng (`obs_*`); tuổi telemetry; nguồn tư thế;
  `pose_simulated`; `note`.
- **`telemetry.csv`**: thời gian (`t_session` âm = nhận trước START), trạng thái, lỗi, lý do dừng, cờ, tốc độ/góc đo
  (rỗng = không hợp lệ), tham chiếu, effort, `last_cmd_seq`, tuổi lệnh, điện áp, bộ đếm lỗi. T9 thêm cột cuối `call`: số
  của lần đọc io đã trả khung này, xem `clock.csv`.
- **`events.csv`**: cột theo thứ tự `t_session, t_io, t_perf, source, code, action, handling, message, call`. Ví dụ dòng
  của lớp nối: `START_CHECK` "Đạt...", `OBSERVE_DISARM`. Cột `handling` là cách xử lý: `stop`, `log`, `before_start`,
  `after_run`, và từ T13 thêm `session_stop` = quyết định dừng của phiên (xem dưới). Cột `call` (T9) chỉ có ở dòng sự
  kiện `VehicleIO`, trống ở dòng của lớp nối và của phiên.
- **`start_refusals.csv`**: cùng cột với `events.csv`, có `t_perf`, còn `call` luôn trống. Gồm `START_CHECK` "TỪ
  CHỐI...", `START_NO_LINK`, `START_ABORTED`, `DISARM_FAILED`, sự kiện cũ rút khỏi `VehicleIO`, và từ T12 mã
  `START_TOO_MANY_CUSPS` (nguồn `session`, khi đường đổi chiều quá giới hạn, mục 3). Tệp luôn được tạo, có thể chỉ có
  dòng tiêu đề.
- **`board_actions.csv`** (T15):
  - Mỗi lần bấm một dòng, kể cả lần không gửi CLEAR_FAULT. Tệp cộng dồn suốt đời liên kết như `start_refusals.csv`, luôn
    được tạo, có thể chỉ có dòng tiêu đề.
  - Ba mốc thời gian, đọc liền nhau lúc quyết định gửi hay không gửi; chưa tới bước đó thì là lúc bấm. `t_io` là đồng hồ
    io của liên kết, so được với `t_io` của các tệp khác cùng liên kết. `t_perf` là `perf_counter()` thô. `wall_time` là
    giờ máy ISO 8601 có múi giờ.
  - `target`, `request` (= CLEAR_FAULT), `outcome` (CLEARED, NOT_NEEDED, ESTOP_PRESSED, REFUSED, NOT_CONFIRMED, NO_ACK,
    NO_LINK), `ack_result`.
  - `state_before`/`fault_before`/`estop_before` lấy từ khung đầu tiên bo gửi sau lúc bấm; `state_after`/`fault_after`
    từ khung đầu tiên sau ACK.
  - `requests_sent` (gồm cả PING) và `commands_sent` (luôn 0).
  - `message`: câu kết quả, lỗi, và đủ từng sự kiện `VehicleIO` gom được, dạng "MÃ (ACTION, t_io X.XXX): lời", nối bằng
    "; ".
  - Bốn cột cuối, nối sau review 02/10/2026 (15 cột cũ giữ thứ tự): `hello_firmware`, `hello_boot_id` ("0x" + 8 chữ số
    hex), `hello_reset_reason` (tên `ResetReason`: POWER_ON, WATCHDOG…), `hello_state`. Đây là HELLO_ACK của lần bấm;
    trống khi dùng lại phiên hay không có HELLO_ACK. `boot_id` đổi giữa các dòng, hay lý do reset, giúp phân biệt "bo
    khởi động lại khi mở cổng" với "đã xóa bằng CLEAR_FAULT".
- **`poses.csv`** (T9): `n`, `use` (`estimate` = thế giới gương cuối bước, `observe` = trạng thái đo cho bộ bám),
  `t_session`, `t_io` (`io.now()` đọc liền SAU mẫu), `available` (0 = nguồn không có mẫu, các cột của mẫu để trống),
  `sample_t_io`, `x`, `y`, `yaw_rad`, `source_id`, `simulated`. Tư thế đọc lúc kiểm START không được ghi.
  - T2 nối thêm hai cột `status` (OK hoặc mã dừng của nguồn LiDAR) và `reason`.
  - Sau review 02/10/2026 nối thêm sáu cột cuối `pred_dt_s`, `pred_speed_mps`, `pred_steer_rad`, `pred_x`, `pred_y`,
    `pred_yaw_rad`: dự đoán tư thế tới `io.now()` (`LinkParams.predict_pose`, nguồn LiDAR). Các cột này trống khi không
    dời. `x`, `y`, `yaw_rad` vẫn là mẫu thô. Phát lại không so các cột `pred_*`.
- **`clock.csv`** (T9): `call` (0, 1, 2…), `kind` (`refresh` đầu bước khi đang chạy, `pump` cuối bước), `t_session`,
  `t_io` (`io.now()` sau lần đọc). Cột `call` của `telemetry.csv` và `events.csv` trỏ về số này.
- **`link.json`**: chế độ, loại `VehicleIO`, nguồn tư thế, cờ mô phỏng, tham số, cấu hình bo mô phỏng, kết quả, số lần
  chạy đã mở (`runs`), số lần START bị từ chối (`refused_starts`), `LinkStats`, và kết quả so giới hạn `limits_check`
  (mục 3). Các khóa thêm ngày 02/10/2026:
  - `clock` = {`t_io_at_start`, `t_perf_at_start`} (T13, xem dưới).
  - `run_start` = `t_io0`, `x`, `y`, `yaw_rad`, `steer_rad`, `state_source` của thế giới gương lúc mở lần chạy, null khi
    chưa mở lần nào (T9, mục 5.1).
  - `log_format` (= 2) và `io_source_id` (T9). `io_source_id` cũng nằm trong `describe()`, tức snapshot `vehicle_link`.
  - Trong `describe()` (T2 và bo ảo QEMU): `pose_source_info` (bản đồ, cấu hình, ngưỡng, `evidence` của nguồn LiDAR;
    None với nguồn khác), `virtual_board`, `board` và `plant` (đoạn "Log qua bo ảo QEMU" dưới đây; None với liên kết
    khác). `params` có thêm `max_pose_age_s` và `predict_pose`.
  - `ecoqos`: trạng thái EcoQoS của tiến trình lúc ghi log, một trong off / system / on / unknown. Khóa này nằm ngoài
    `describe()`, nên phát lại log và snapshot không đổi.

**Tệp thêm theo nguồn tư thế** (T2, 02/10/2026). Nguồn tư thế LiDAR thêm `localization.csv`: định vị từng vòng, gồm 5
vòng trước START và các vòng của lần chạy. LiDAR mô phỏng thêm `tu_the_that_mo_phong.csv` và `.json`, là tham chiếu ở
mức MP.

**Gói phát lại** (`export_run`, T9, 02/10/2026):

- `export_run` xuất gói cho lần chạy qua `VehicleIO`. Gói có cùng các tệp của gói SIM (`config_snapshot/`,
  `telemetry.csv` = RunLog của thế giới gương, `events.jsonl`, `safety_events.json`, `result.json`, `source.zip`,
  `manifest.json`) cộng thư mục `vehicle_io/` chứa tám tệp trên.
- Manifest ghi `evidence` theo snapshot, `model` = `vehicle_io_mirror`, `replay_kind` = `vehicle_io_log`. Gói SIM không
  có khóa `replay_kind` và không đổi.
- `export_run` vẫn từ chối bằng `ReplayNotSupported`, trước khi tạo thư mục, khi log không chắc thuộc đúng lần chạy:
  snapshot có `vehicle_link` mà phiên không còn `run_link`; phiên có `run_link` mà snapshot thiếu khóa; chế độ trong
  snapshot khác chế độ của liên kết; liên kết chưa mở lần chạy nào.
- Phát lại gói: mục 5.1.

**Log qua bo ảo QEMU** (thêm 02/10/2026):

- `link.json`: `evidence` = `qemu_firmware_simulated_vehicle`, `io` = `QemuPlantVehicleIO`, `io_source_id` =
  `qemu_board`, `port` = `socket://127.0.0.1:<cổng>`, `pose_source` = `qemu_plant_pose`, `pose_simulated` = true (cột
  `pose_simulated` của `commands.csv` = 1), `virtual_board` = true.
- `io_simulated` = false, vì liên kết chạy theo đồng hồ perf_counter; khóa `clock` đổi `t_io` sang perf_counter như với
  bo thật.
- Hai khóa luôn có: `board` ({`kind` "qemu", `url`, `image_sha256`, `hello`, `workdir`, `pid`, …}) và `plant` (nội dung
  `configs/bo_ao_qemu.json`). Cả hai là None với liên kết khác.
- `telemetry.csv`: cột `flags` là cờ của firmware (SPEED_VALID = STEER_VALID = 0), nhưng `speed_mps`, `steer_rad` mang
  số của xe mô phỏng.
- `events.csv`: nguồn sự kiện VehicleIO là `qemu_board`. Mã mới: `START_NO_QEMU_BOARD`.
- `board_actions.csv`: target là "bo ảo QEMU socket://…".
- Phát lại log (mục 5.1) dùng được, không phải đổi gì. Nhật ký của bo ảo nằm ở `runs/bo_ao_qemu/<giờ>/bo_ao.json`
  ([MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md) mục 1.1).

**Dòng `session_stop`, cột `t_perf`, khóa `clock`** (thêm 02/10/2026, T13). Mức bằng chứng: bo mô phỏng và cổng serial
giả; bo ảo QEMU và ESP32-S3 chưa thử qua phiên lúc thêm, trạng thái sau đợt 2 ở mục 8.

- **Nội dung.** Các dòng `session_stop` là đúng `Session.safety_events`: cùng thứ tự, `code`, `source` (nguồn của sự
  kiện), `t_session` (thời điểm phiên của sự kiện), `action` (STOP hay WAIT), và `message` bằng message của sự kiện.
  Riêng `MAP_CHANGED` có thêm "(vật <id> tại (x, y) m, R×C cm)", chỉ ở dòng log. Cộng thêm mọi yêu cầu dừng khi đang
  chạy, `USER_RESET` và `COLLISION`; ba loại này không vào `safety_events`. Sau khi lần chạy kết thúc, phiên không ghi
  thêm dòng nào.
- **Ba mốc của dòng `session_stop`.** `t_session`: với yêu cầu dừng là thời gian phiên lúc yêu cầu. `t_io`: `io.now()`
  lúc phiên quyết định, cùng quy ước với `commands.csv`. `t_perf`: `time.perf_counter()` thô (giây) lúc ghi dòng.
- **Cột `t_perf`** có ở mọi dòng `events.csv` và `start_refusals.csv`. Đó là QPC trên Windows, chung cho mọi tiến trình
  của một máy, cùng gốc với stamp bàn thử (`RIG_CLOCK`) và cột `t_perf` của dấu đồng bộ T14. Với dòng sự kiện của
  `VehicleIO` (`stop`, `log`, `after_run`), `t_perf` là lúc lớp nối gom sự kiện, không phải lúc bo phát.
- **Một sự kiện, một hay hai dòng.** Sự kiện của `VehicleIO` (ví dụ `VEHICLE_FAULT`, `TELEMETRY_STALE`) và hai kiểm
  khung telemetry của lớp nối (`VEHICLE_NOT_ARMED`, `OBSERVE_NOT_DISARMED`) có HAI dòng: `stop` lúc lớp nối nhận,
  `session_stop` lúc phiên quyết định. Các kiểm ở nhịp điều khiển của lớp nối (`STALE_TELEMETRY`, `NO_MEASURED_STATE`,
  `STALE_POSE`, `HALTED`, `SEND_FAILED`) trả sự kiện thẳng cho `Session`, nên chỉ có dòng `session_stop`, không có dòng
  `stop`. Lọc theo `handling`.
- **Lý do dừng đầu tiên** và `t_phát_hiện` là dòng đầu tiên có `handling` = `session_stop` và `action` = STOP. Với
  `USER_STOP`, lúc bấm thật đọc ở `t_perf` (và `t_io` với bo thật); `t_session` có thể sớm hơn tới một nhịp giao diện.
- **Thứ tự dòng ở bo mô phỏng.** `t_session` của dòng `session_stop` có thể sớm hơn tới 5 ms so với dòng `stop` cùng mã.
  Dòng `stop` mang thời điểm của khung trên đồng hồ bo mô phỏng (nhịp 10 ms, đi trước thời gian phiên tới 5 ms), còn
  dòng `session_stop` mang thời gian phiên. Kiểm lại ngày 02/10/2026 bằng script tạm, không lưu trong repo, trên đường
  thẳng như `tests/test_session_stop_log.py`: E-stop giả ở `t_session` 0,795 s cho dòng `stop` VEHICLE_FAULT 0,82 s,
  dòng `session_stop` 0,815 s, cùng `t_io` 1,21 s; dòng STOP đầu của `commands.csv` ở 0,82 s. Vì vậy hãy xếp thứ tự theo
  `t_io` hay theo thứ tự dòng, không theo `t_session`.
- **Khóa `clock` của `link.json`**: `io.now()` và `perf_counter()` đọc liền nhau lúc mở lần chạy; cả hai null khi chưa
  mở lần nào. Với bo chạy thời gian thực trên đồng hồ mặc định của `SerialVehicleIO` (`io_simulated` false), công thức
  `t_perf = t_io + (t_perf_at_start − t_io_at_start)` áp cho cột `t_io` của `commands.csv`, `telemetry.csv`,
  `events.csv`. Công thức này được test với cổng serial giả, đồng hồ io dựng từ `perf_counter`. Với bo mô phỏng, `t_io`
  là đồng hồ mô phỏng, không đổi được.
- **`Session.run_events`.** Qua `VehicleIO`, mục "stop" của `Session.run_events` mang thêm `code`/`source` khi khác mặc
  định, để phát lại log (mục 5.1) dựng lại đúng dòng. Nhánh SIM và dừng của người dùng giữ {t, kind, reason}.
- **Ghi log không chặn dừng** (sau review 02/10/2026). `log_session_event` không bao giờ ném lỗi. Đọc `io.now()` hỏng
  thì `t_io` để trống và lời lỗi được nối vào `message`; lỗi khác khi ghi thì mất dòng đó, phiên vẫn dừng. Mọi dòng
  `events.csv` và `start_refusals.csv` được dựng bằng một hàm (`_event_row`), kể cả dòng `START_TOO_MANY_CUSPS` của T12.

Mã mới ngày 02/10/2026 (mã cũ giữ nguồn cũ):

| `code` | `source` | Từ đâu |
|---|---|---|
| `USER_STOP` | `user` | nút Dừng, phím Esc hay Space khi đang chạy (`MainWindow.stop()`); mặc định của `request_stop` |
| `USER_RESET` | `user` | đặt lại khi đang chạy (`Session.reset()`) |
| `COLLISION` | `sim_safety` | va chạm hình học của thế giới gương |
| `FUSED_MAP_INVALID` | `lidar_bridge`, `camera_ai_bridge` | bản đồ hợp nhất không hợp lệ khi đang chạy |
| `LIDAR_CONFIG_CHANGED`, `LIDAR_MIRROR_CHANGED`, `LIDAR_DISCONNECTED` | `lidar_dock` | ngăn LiDAR |
| `CAMERA_AI_CONFIG_CHANGED`, `CAMERA_AI_DISABLED`, `CAMERA_AI_ERROR`, `CAMERA_AI_BLOCKED`, `CAMERA_AI_NO_RESULT`, `CAMERA_AI_STALE`, `CAMERA_AI_UNUSABLE` | `camera_dock` | ngăn AI camera |

Ghi chú cho bảng:

- `USER_STOP`: ở Quan sát với bo mô phỏng, phím Space chỉ phanh xe của người lái mô phỏng.
- Ngăn AI camera: mọi mã trừ `CAMERA_AI_CONFIG_CHANGED` chỉ có khi tích "AI bắt buộc". `CAMERA_AI_UNUSABLE` dùng cho
  loại "không dùng được" chưa có mã riêng; mã này thêm sau review 02/10/2026.

Mã cũ:

- `MAP_CHANGED`, `RUN_TIMEOUT`, `WAIT_REPLAN`: nguồn `sim_safety`. Đây là tên cũ của lớp an toàn trong `Session`, dùng
  cả khi chạy qua `VehicleIO`; nó **không** có nghĩa là sự kiện mô phỏng.
- `STALE_TELEMETRY`, `NO_MEASURED_STATE`, `STALE_POSE`, `HALTED`, `SEND_FAILED`, `STOP_NOT_CONFIRMED`,
  `VEHICLE_NOT_ARMED`, `OBSERVE_NOT_DISARMED`: nguồn `vehicle_link`.
- Mã của `VehicleIO`: nguồn `sim_vehicle_io` hoặc `esp32_vehicle`.

Mã thêm trong đợt 2 (02/10/2026):

- Nguồn tư thế LiDAR (T2): `POSE_LOST`, `POSE_DISAGREE`, `POSE_UNCHECKED` là mã dừng, nguồn là id của nguồn tư thế
  (`lidar_sim_localize` hay `lidar_c1_localize`). Trước START: `START_POSE_UNVERIFIED` (từ chối) và
  `POSE_SOURCE_WARNING` (chỉ ghi). `POSE_SOURCE_HOOK_FAILED`: móc của nguồn lỗi, chỉ ghi.
- Bo ảo QEMU: `START_NO_QEMU_BOARD` (nguồn `vehicle_link`). Sự kiện VehicleIO của bo ảo mang nguồn `qemu_board`.

**Tệp dấu đồng bộ video–log** (thêm 02/10/2026, T14; do giao diện ghi, không phải `write_logs`; chỉ kiểm offscreen).

- "Xuất log CSV…" ghi thêm `<tên>_sync_marks.csv` cạnh tệp CSV, không nằm trong `<tên>_vehicle_io/`, chỉ khi đã có ít
  nhất một dấu. Tệp có ở mọi nhánh, kể cả SIM.
- Tệp gồm hai loại dòng. Dòng `SYNC_MARK` sinh khi bấm nút hay phím F8 (mục 6); `t_perf` đọc ngay sau khi vẽ ô. Dòng
  `CLOCK` do giao diện tự ghi mỗi khi phiên vào RUNNING, STOPPING, STOPPED, COMPLETED hay FAULT, ghép `perf_counter` với
  thời gian phiên trong cùng nhịp giao diện.
- Cột: `n`, `kind`, `t_perf`, `t_wall`, `source`, `trigger`, `state`, `t_session`, `t_io`, `io_clock`, `t_rig_s`,
  `flash_ms`, `paint_ms`, `note`, `time_scale`. Cột `time_scale` (thêm sau review) là "tốc độ chạy" của cockpit, bằng 1
  khi lần chạy đi qua `VehicleIO` thời gian thực.
- Tệp sống `runs/sync_marks/<ngày giờ>_ui_app.csv` (hay `_ui_lidar_app.csv`) có cùng nội dung. Nó được tạo ở dấu đầu
  tiên rồi ghi từng dòng ngay khi có. Ghi lỗi (ví dụ tệp đang mở trong Excel) thì dòng vẫn giữ trong bộ nhớ, thanh trạng
  thái báo, và lần ghi được sau đó ghi lại cả tệp.
- Cách đổi đồng hồ video và log sang `perf_counter`: docstring của
  [`autopark/evaluation/sync_marks.py`](../autopark/evaluation/sync_marks.py) và
  [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 7 (T14).

**Tệp trỏ tới bản ghi cảm biến** (thêm 02/10/2026, T3; chỉ `ui.lidar_app`; chỉ kiểm offscreen). Khi cửa sổ đã ghi ít
nhất một bản ghi cảm biến (ngăn "Ghi cảm biến"), "Xuất log CSV…"/"Lưu phiên…" ghi thêm `<tên>_sensor_recordings.json`
cạnh tệp CSV. Nếu có gói `<tên>_<thời điểm>/`, gói cũng có `sensor_recordings.json`. Mỗi bản ghi là một mục: `folder`,
`status`, `t_start_s`, `t_stop_s`, `overlap_s`, `covers_run` (so với lần chạy gần nhất), số khung, số vòng LiDAR,
`meta_sha256` (khi đã xong). Bản ghi không bao giờ được chép vào gói; phát lại T9 (mục 5.1) vẫn chỉ phát lại quyết định
từ log `VehicleIO`. Chi tiết: [GHI_PHAT_LAI_BAN_THU.md](GHI_PHAT_LAI_BAN_THU.md) mục 9.

**Chấm một lần chạy** (thêm 02/10/2026, T5). Thư mục `<tên>_vehicle_io/` cùng tệp `<tên>.csv` bên cạnh, hay gói
`<tên>_<ngày giờ>/` có `vehicle_io/` (T9), là đầu vào của công cụ chấm
`python -m autopark.evaluation.score_run --log …`.

- Gói được chấm như log `VehicleIO`, không như gói SIM. Tệp `<tên>_sync_marks.csv` được tìm theo tên log hay tên gói.
- Mã và thời điểm quyết định dừng lấy từ dòng `session_stop`. Với log ghi trước T13, công cụ lấy gần đúng bằng dòng STOP
  đầu của `commands.csv` (±20 ms).
- Log qua bo ảo QEMU là log mô phỏng: `score_run` không chấm cấp XT, và `--sim-truth` (tư thế `qemu_plant_pose` của xe
  mô phỏng) chỉ dùng ở cấp MP.

### 5.1. Phát lại lần chạy qua VehicleIO (T9, thêm 02/10/2026)

Phát lại log chạy lại đúng phần mềm của phiên trên đầu vào đã ghi của một lần chạy, rồi so quyết định với bản ghi. Nó
cho biết "cùng đầu vào + mã này → cùng quyết định", nhưng không tái hiện xe hay bo.

*Mức bằng chứng:* chỉ bo mô phỏng, cổng serial giả và (từ đợt 2) bo ảo giả. Bo thật chưa thử, vì START với bo thật còn
bị từ chối (mục 3: bước 0 hoặc `START_CHECK`).

**Vì sao cần cách phát lại riêng.** Gói SIM được tái mô phỏng như trước. Lần chạy qua `VehicleIO` (`VEHICLE_IO`,
`OBSERVE`) thì không tái mô phỏng được: trạng thái lấy từ telemetry và nguồn tư thế, còn tay người lái (`OBSERVE`) và
lỗi gây ra phía xe không được ghi. Vì vậy "phát lại log" chạy lại CÙNG phần mềm (`Session` → `VehicleLink` → bộ bám →
thế giới gương, mã không đổi), vòng hở, trên đầu vào đã ghi, đúng thứ tự, qua `ReplayVehicleIO` và `ReplayPoseSource`
([`autopark/application/vehicle_replay.py`](../autopark/application/vehicle_replay.py)). Lệnh tính ra không đi đâu.

**Đầu vào đã ghi** (băng của `write_logs`, `log_format` 2):

- mỗi lần đọc io của lớp nối (`refresh` đầu bước khi đang chạy, `pump` cuối bước), với đúng các khung telemetry và sự
  kiện `VehicleIO` mà lần đọc đó trả (cột `call`) và `io.now()` sau lần đọc (`clock.csv`);
- mỗi lần đọc nguồn tư thế: mẫu và `io.now()` liền sau mẫu (`poses.csv`);
- mỗi `send()`/`stop()`: số thứ tự hay lời lỗi, và `io.now()` liền sau (`commands.csv`);
- vật cản chèn vào và yêu cầu dừng (`events.jsonl` của gói), được chèn lại đúng bước như nhánh SIM. Mục "stop" mang
  `code`/`source` của T13 được chuyển nguyên.

**So với bản ghi:**

- `commands.csv`, kể cả cột đồng hồ `t_io` và `telemetry_age_s`;
- `telemetry.csv`;
- `events.csv`, kể cả dòng `session_stop`. Bỏ qua dòng `before_start` và mã `DISARM_FAILED`, `END_RUN_SEND_FAILED`;
  không so cột `t_io` của dòng `session_stop`;
- `poses.csv` và `clock.csv`, phải thẳng hàng theo `use`/`kind` và `t_session`;
- `safety_events.json`;
- `result.json`: `state`, `reason`, `steps`, `collided` phải bằng; `final_state`, `distance` so theo sai số;
- RunLog (`telemetry.csv` của gói) và `result` trong `link.json` (`outcome`, `reason`, `t_session`).

Cột `t_perf` không được so ở tệp nào. Sai số cho số thực là 1e-9. Sai số cho cột đồng hồ, và cho số giây in trong lời
(ví dụ tuổi telemetry trong lời của `STALE_TELEMETRY`, sửa sau review), là 5 ms, tức một bước. Cả hai sai số là đề xuất,
chưa đo trên bo thật.

**Không so:**

- bước kiểm START: kết nối, HELLO, so giới hạn, ARM/DISARM, kiểm lại tư thế. Phát lại mở lần chạy ở `run_start` đã ghi;
- thống kê io, trạng thái bo sau DISARM cuối, `start_refusals.csv`, `board_actions.csv`;
- bản thân xe, bo, cảm biến, định vị;
- `localization.csv` (T2). Tệp này tái hiện bằng
  `python -m autopark.lidar.pose_estimator --map <thư mục bản đồ> --recording <thư mục bản ghi phiên T3> --same-scans-as localization.csv --out <thư mục>`;
- các cột `pred_*` của `poses.csv`: chúng tính lại từ mẫu thô bằng cùng mã, còn lệnh và RunLog dùng tư thế đã dời thì
  vẫn được so.

Điều khẳng định được là "cùng đầu vào + mã này → cùng quyết định". Phát lại KHÔNG cho thấy xe sẽ lặp lại lần chạy, và
không thay phép đo trên xe.

Băng ghi trước T2 không có cột `status`, `reason`; khi phát lại, mẫu được coi là OK. Lần chạy qua bo ảo QEMU xuất gói và
phát lại như lần chạy qua bo mô phỏng (test với bo ảo giả).

**Lệnh**, chạy trong thư mục `autopark` với `.venv`:

```
.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.replay <thư mục gói>
```

Gói SIM in "Replay OK: …" như trước. Gói `VehicleIO` in báo cáo tiếng Việt: KHỚP hay KHÁC, số dòng đã so theo tệp, lệch
đồng hồ lớn nhất, tối đa 20 chỗ khác xếp theo `t_session` (chỗ đầu là chỗ lệch sớm nhất), và phần không so.

Mã thoát:

- 0 = KHỚP;
- 1 = KHÁC;
- 2 = không phát lại được (`ReplayNotSupported`): thiếu `vehicle_io/`; log ghi trước T9, không có `log_format` 2; chế độ
  không khớp; tệp hỏng như CSV không phải UTF-8 hay lỗi CSV, JSON sai kiểu, snapshot không dựng lại được phiên;
- 3 = lỗi bất ngờ khi phát lại: in tên lỗi, traceback ra stderr; không phải KHÁC (thêm sau review).

Gói thiếu hay hỏng `config_snapshot/run.json` khiến `run_store.is_vehicle_io_package` trả False. Dù vậy dòng lệnh vẫn
nhận đó là gói `VehicleIO` nhờ `vehicle_io/link.json`, nên cũng thoát mã 2, không rơi xuống nhánh gói SIM. Tệp CSV có
BOM (Excel "CSV UTF-8") vẫn đọc được.

Trong Python: `run_store.replay_vehicle_run(gói)` trả (phiên, báo cáo) và không đóng phiên. `replay_run(gói)` ném
`ValueError` "Phát lại khác bản ghi (n chỗ); đầu tiên: …" khi khác.

**Giới hạn của phát lại log:**

- Không chạy lại bước START.
- Khung bị lấy khỏi hàng đợi của `VehicleIO` ngoài lớp nối không có trên băng, nên phát lại báo KHÁC. Điều này đúng
  thiết kế, và quyết định dừng vẫn khớp. Hiện chỉ test làm việc này (`io.advance()` lúc treo).
- Nếu có luồng `Heartbeat` đọc cổng song song (phiên hiện không dùng), `latest()` lúc phát lại có thể khác.
- Với đồng hồ tường (bo thật), đồng hồ lúc quan sát lấy từ lần đọc io trước nên sớm vài µs. Trên cổng serial giả theo
  đồng hồ tường, lệch lớn nhất là 3,6 µs (script tạm của lượt viết mã T9). Vì thế một quyết định sát ngưỡng, ví dụ
  telemetry cũ đúng 0,15 s, có thể lật và hiện thành chỗ khác.
- Máy khác có thể lệch bit cuối (libm, shapely): sai số 1e-9 lo phần này; quyết định rời rạc bị lật vẫn hiện là chỗ
  khác.

**Kích thước và chi phí.** Kiểm lại ngày 02/10/2026 bằng script tạm, không lưu trong repo; máy bàn, `.venv`; bo mô phỏng
theo `configs/vehicle_io_sim.json`; sa bàn `bai_do_xe` ở `VEHICLE_IO`, COMPLETED sau 20,945 s, 4.189 bước, 1.049
COMMAND.

- `clock.csv` 195 KB (8.378 dòng), `poses.csv` 541 KB (5.237 dòng), cả thư mục `vehicle_io/` 1.062 KB.
- Trong bộ nhớ: 2,25 MB + 3,15 MB (`sys.getsizeof` đệ quy).
- Phát lại 0,67 s, KHỚP, lệch đồng hồ 0.
- Suy ra cho lần chạy dài nhất 180 s (`MAX_RUN_TIME`): ≈ 6,3 MB trên đĩa cho hai băng, ≈ 46 MB bộ nhớ.
- Theo lượt viết mã T9, vòng điều khiển chậm thêm ≈ 0–16 µs mỗi bước 5 ms, cùng cỡ nhiễu đo.

## 6. Giao diện

Mục này mô tả các ô và nút của cockpit liên quan tới ba nhánh chạy: ô chọn nhánh, thẻ "Bo điều khiển", các nút xuất log,
dấu đồng bộ, số lần đổi chiều, thẻ "Xe", ô "Nguồn tư thế", bo ảo QEMU và ngăn "Ghi cảm biến". Mức bằng chứng ghi ở từng
phần; phần lớn chỉ được kiểm bằng test offscreen.

**Ô "Nhánh chạy khi bấm Bắt đầu đỗ"** nằm ở ngăn "Mô phỏng". Mặc định là "Mô phỏng giai đoạn 0". Ô này chỉ đổi được khi
đang chỉnh hoặc sẵn sàng; từ lúc chạy tới lúc đặt lại thì bị khóa. Dưới ô có dòng giải thích cho từng nhánh.

- **VehicleIO: GỬI lệnh tới bo.** Trước muộn tối 24/09/2026 nhãn là "VehicleIO → bo mô phỏng: GỬI lệnh".
  - Khi thẻ "Bo điều khiển" để "Bo mô phỏng (mặc định)", mỗi lần START giao diện tạo một `SimVehicleIO` mới đặt ở điểm
    xuất phát. Chỗ này mô phỏng việc người đặt xe vào vị trí. Bo mô phỏng dựng theo tệp `configs/vehicle_io_sim*.json`
    có `vehicle_config` trỏ đúng tệp xe đang dùng; không có thì theo `configs/vehicle_io_sim.json` (bản 24/09/2026 luôn
    dùng tệp này).
  - Chọn cổng COM với nguồn "Mô phỏng" thì START bị từ chối, vì chưa có nguồn tư thế thật. Cổng COM với nguồn "LiDAR
    thật" (T2) cũng chưa chạy được: VehicleIO bị từ chối ở bước 0b, Quan sát bị từ chối ở `START_CHECK` (mục 3).
  - Chọn "Bo ảo QEMU" thì phiên chạy qua bo ảo với xe mô phỏng phía laptop (cuối mục này).
- **Quan sát: tính lệnh, KHÔNG gửi.** Khi đang quan sát, phím ↑ ↓ ← → lái xe mô phỏng thay người lái, Space phanh, 0 trả
  lái, Esc kết thúc. Nhãn tiến độ hiện lệnh gợi ý kèm "(không gửi)". Thẻ trạng thái đổi thành "Quan sát".

**Thẻ "Bo điều khiển"** (thêm muộn tối 24/09/2026, ngay dưới ngăn "Mô phỏng"). Trước đó giao diện chưa có lựa chọn cổng
serial. Thẻ chỉ được kiểm bằng test offscreen với `comports` giả và cổng serial giả; chưa mở cổng thật nào, và chưa có
ESP32-S3.

- **Ô chọn bo.** Danh sách luôn có "Bo mô phỏng (mặc định)", "Bo ảo QEMU (firmware xe trong giả lập)", rồi các cổng COM.
  Chọn bo mô phỏng thì hành vi y như trước.
  - Cổng COM lấy từ `serial.tools.list_ports.comports()`. Cổng chỉ được liệt kê khi mở danh sách hoặc bấm "Quét cổng",
    không liệt kê lúc dựng cửa sổ. Việc liệt kê không mở cổng.
  - Cổng có VID 303A được ghi thêm "Espressif". Đây chỉ là gợi ý, không dùng để lọc.
  - Cổng đã chọn mà không còn thấy (rút cáp) vẫn được giữ, ghi "(không thấy — đã rút?)". Giao diện không tự đổi sang bo
    khác.
  - Tới 30/09/2026 danh sách chỉ có bo mô phỏng và cổng COM, nên bo ảo QEMU (`socket://…`,
    [MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md)) chỉ dùng được từ Python. Mục "Bo ảo QEMU" có từ 02/10/2026.
- **Chọn một cổng thật** ở `VEHICLE_IO` hay `OBSERVE` tạo `VehicleLink.serial_port(mode, cổng)`, gồm
  `SerialVehicleIO.deferred` (cổng CHƯA mở) và `NoPoseSource`.
  - Với nguồn "Mô phỏng", bấm Bắt đầu đỗ thì hiện hộp thoại "Không bắt đầu được": chưa có nguồn tư thế thật, cổng chưa
    được mở, không gửi gì tới bo (mục 3, bước 0a).
  - Với "LiDAR thật" (chỉ có trong `ui.lidar_app`, từ 02/10/2026, T2), liên kết là
    `VehicleLink.serial_port(mode, cổng, pose_source=nguồn LiDAR)`, và Bắt đầu đỗ đi qua bước 0a, 0b, 0c ở mục 3.
  - Tư thế mô phỏng (`SimTruthPose`) không bao giờ được dùng với bo thật. `VehicleLink` báo ValueError khi
    `SimTruthPose` bọc một xe mô phỏng khác, hoặc khi io không phải `SimVehicleIO`, kể cả `SimTruthPose` dựng quanh
    chính bo serial. Ca cuối từng lọt qua trước bản sửa muộn tối 24/09/2026, rồi START hỏng với `AttributeError`.
- **Nút "Kiểm kết nối bo"** (`probe_board`). Nút này **không bao giờ ARM hay gửi lệnh chuyển động**.
  - Với cổng thật, giao diện hỏi xác nhận trước khi mở: "chỉ tiếp tục nếu cổng là bo ESP32-S3 của xe, không phải LiDAR".
    Sau đó nút mở cổng, gửi HELLO, so giới hạn với cấu hình xe, đọc tới 5 khung telemetry, rồi đóng cổng. HELLO đưa bo
    đang ARMED/RUNNING về DISARMED.
  - Kết quả hiện ngay trong thẻ: phiên bản firmware, `boot_id`, lý do reset, trạng thái, chu kỳ telemetry, các giới hạn,
    kết quả so giới hạn (`LIMITS_MISMATCH` và START có bị từ chối không), từng khung telemetry (trạng thái, lỗi, tốc độ,
    lái, E-stop, nguồn, ToF), sự kiện, số COMMAND/REQUEST đã gửi (luôn 0 COMMAND).
  - Với "Bo mô phỏng", nút chạy cùng hàm trên một `SimVehicleIO` mới, không hỏi xác nhận. Với bo ảo QEMU, nút cũng không
    hỏi xác nhận (cuối mục này).
  - Bo trả HELLO_ACK nhưng `connect()` không nhận phiên, vì bo chọn chu kỳ telemetry dài hơn `telemetry_timeout_s / 3`
    (ví dụ 200 hay 400 ms): báo cáo vẫn có firmware, `boot_id`, lý do reset, giới hạn và kết quả so giới hạn. Dòng lỗi
    là "HELLO_ACK nhận được nhưng phiên bị từ chối: Bo chọn chu kỳ telemetry ... ms ...". Trước bản sửa muộn tối
    24/09/2026 theo rà soát, báo cáo nói "Không nhận được HELLO_ACK." rồi lại báo lỗi chu kỳ của chính HELLO_ACK đó.
  - HELLO_ACK của một phiên cũ (cổng đã đóng) không bao giờ được báo như của lần kiểm mới.
  - Bo trả HELLO_ACK mà không gửi telemetry: vòng đọc dừng sau `frames_timeout_s` (1 s, đồng hồ io), báo lỗi "Chỉ nhận
    0/5 khung". Có `TELEMETRY_STALE` và đúng một REQUEST DISARM do `VehicleIO` tự gửi, 0 COMMAND.
  - Nhánh chạy đang giữ chính cổng đó mở (bước 0c, kể cả sau một lần Bắt đầu đỗ bị từ chối ở `START_CHECK`): sau khi
    người dùng xác nhận, nút đóng cổng của liên kết (`VehicleLink.release_port`) rồi mới mở để kiểm. Thanh trạng thái và
    dòng cuối báo cáo nói "đã đóng COMx mà nhánh chạy giữ mở từ lần Bắt đầu đỗ trước; lần Bắt đầu đỗ sau mở lại". Trả
    lời "Không" thì không đóng gì. Trước bản sửa sau review 02/10/2026, trên Windows nút báo "Không mở được COMx: …
    Access is denied".
- **Nút "Xóa lỗi bo (CLEAR_FAULT)"** (`VehicleLink.clear_fault`; thêm 02/10/2026, T15). Nút nằm ở hàng riêng dưới "Quét
  cổng | Kiểm kết nối bo". Chỉ thử với bo mô phỏng và cổng serial giả, chưa thử với ESP32-S3. Nút **không bao giờ ARM**
  và không gửi COMMAND nào.
  - **Khi nào bật.** Nút chỉ bật khi phiên đang chỉnh hoặc sẵn sàng (EDITING/READY), ở nhánh VehicleIO hoặc Quan sát,
    với bo chọn ở cổng COM. Với bo mô phỏng của giao diện thì nút khóa, vì mỗi lần Bắt đầu đỗ tạo bo mới ở DISARMED;
    tooltip nêu lý do khóa. Từ đợt 2, nút cũng bật với bo ảo QEMU khi bo đang chạy, không hỏi xác nhận. Với cổng thật,
    giao diện hỏi xác nhận trước khi mở (chỉ tiếp tục nếu cổng là bo ESP32-S3 của xe, không phải LiDAR).
  - **Phiên với bo.** Nút dùng `VehicleIO` của chính liên kết đang chọn. Cổng chưa mở thì nút mở rồi đóng lại khi xong.
    Chưa có phiên, hoặc laptop đã chốt `TELEMETRY_STALE`, thì nút gửi HELLO mở phiên mới (bo giữ FAULT). Đã có phiên thì
    nút dùng lại phiên đó: gửi một REQUEST PING và chờ ACK trước khi đọc trạng thái. Đây là rào "khung mới": luồng byte
    của bo đúng thứ tự, nên khung đọc sau ACK là khung bo gửi sau lúc bấm. Rào này thêm sau review 02/10/2026; trước đó
    khung cũ tồn đọng trong cổng có thể thành căn cứ.
  - **Khi nào dùng lại phiên.** Lúc viết mã T15, với cổng COM của giao diện, cổng luôn chưa mở lúc bấm, nên mỗi lần bấm
    là một phiên mới (HELLO); nhánh PING chỉ chạy khi `VehicleIO` đã mở sẵn, tức trong test. Từ khi có T2 (cùng ngày),
    sau một lần Bắt đầu đỗ mà bước 0c đã mở cổng COM (nguồn "LiDAR thật" ở Quan sát), liên kết giữ cổng và phiên, nên
    lần bấm sau dùng lại phiên đó (PING). Với bo thật: chưa thử.
  - **Quyết định** theo khung telemetry đầu tiên bo gửi sau lúc bấm. Bo không ở FAULT thì không cần và không gửi
    CLEAR_FAULT (NOT_NEEDED). `ESTOP_INPUT` = 1 thì cũng không gửi (ESTOP_PRESSED). Còn lại nút gửi đúng một REQUEST
    CLEAR_FAULT, rồi đọc khung kế tiếp. Firmware tự kiểm lại trước khi xóa (`ESTOP_ACTIVE`, `FAULT_ACTIVE`).
  - **Báo cáo trong thẻ**: HELLO_ACK, hay "Dùng phiên đang có với bo (không gửi HELLO); gửi PING và chờ ACK…"; khung
    trước và sau (trạng thái, lỗi kèm ghi chú nguyên nhân, E-stop); ACK; sự kiện; số COMMAND/REQUEST; KẾT QUẢ; LỖI. PING
    được tính vào số REQUEST, nên CLEARED trên phiên dùng lại là 2 REQUEST. Chữ xanh khi CLEARED hay NOT_NEEDED, vàng
    khi khác.
  - **Sau khi xóa.** Lỗi khác E-stop (STALL, LOOP_OVERRUN, FEEDBACK_LOST, SUPPLY_LOW) được xóa theo luật firmware;
    SUPPLY_LOW chỉ xóa khi điện áp đủ lại. Bo về DISARMED và vẫn phải ARM qua Bắt đầu đỗ. Mỗi lần bấm ghi một dòng
    `board_actions.csv` (mục 5).
- **Khóa khi chạy.** Ô chọn cổng, "Quét cổng", "Kiểm kết nối bo" và "Xóa lỗi bo" bị khóa từ lúc chạy tới lúc đặt lại.
  "Xóa lỗi bo" còn khóa ở nhánh Mô phỏng giai đoạn 0, với bo mô phỏng của giao diện, và khi liên kết đã đóng
  (`VehicleLink.clear_fault_blocker`). Gọi thẳng `_clear_board_fault` khi bị khóa chỉ báo lý do ở thanh trạng thái.
- **Giao diện bị chặn trong lúc kiểm.** "Kiểm kết nối bo" chạy trên luồng giao diện (con trỏ chờ), tối đa khoảng 1 s chờ
  HELLO_ACK cộng 1 s chờ telemetry. "Xóa lỗi bo" cũng chạy trên luồng giao diện, chờ tối đa ≈ 3,5 s: HELLO 1 s (hay PING
  0,5 s), khung 1 s, ACK của CLEAR_FAULT 0,5 s, khung 1 s, chưa kể lúc mở cổng. Trên bo thật cả hai chưa đo.

**"Xuất log CSV…" và "Lưu phiên…"** (hai nút gọi cùng một hàm; T9, thêm 02/10/2026 và sửa sau review; chỉ kiểm
offscreen):

- Sau một lần chạy qua `VehicleIO`, ngoài tệp CSV và thư mục `<tên>_vehicle_io/`, hai nút còn xuất gói
  `<tên>_<ngày>_<giờ>_<micro giây>/`, phát lại được bằng log (mục 5.1). Thanh trạng thái báo "Đã ghi N dòng vào <tệp> (+
  thư mục _vehicle_io, gói phát lại <tên gói>)", hoặc "(+ thư mục _vehicle_io; KHÔNG xuất gói phát lại: <lý do>)". Không
  có hộp thoại hay nút mới.
- Liên kết đang chọn chưa chạy lần nào mà có START bị từ chối hay lần bấm "Xóa lỗi bo": hai nút bật và ghi thêm
  `<tên>_vehicle_io/` của liên kết đó (mục 4, quy tắc 6). Đổi nhánh chạy hay cổng thì liên kết cũ bị thay, và các dòng
  này mất nếu chưa xuất.
- Hai nút và ô "tốc độ chạy" bị khóa khi xe đang chạy (RUNNING/STOPPING). Lý do: luồng giao diện cũng là luồng của vòng
  điều khiển 50 Hz, mà xuất gói chạy PowerShell và nén mã nguồn mất ≈ 1,4 s (lượt review 02/10/2026 đo 1,46 s,
  offscreen, bo mô phỏng của giao diện, không lưu log). Gói chỉ xuất sau khi xe dừng. Lời gọi thẳng giữa lần chạy chỉ
  ghi tệp CSV, `_vehicle_io` và tệp dấu đồng bộ.

**Nút "Dấu đồng bộ · F8"** (thêm 02/10/2026, T14; chỉ kiểm offscreen, `tests/test_sync_marks.py`). Nút nằm ở hàng đầu
cockpit, cạnh thẻ trạng thái; phím F8 tương đương, kể cả khi lái tay.

- Mỗi dấu nháy một ô trắng có số phủ cả cửa sổ trong 0,5 s và ghi một dòng `SYNC_MARK` (mục 5).
- Dùng được ở mọi trạng thái trừ RUNNING/STOPPING: khi đó nút mờ, còn F8 bị từ chối kèm lời báo ở thanh trạng thái. Hai
  dấu cách nhau ít nhất 1 s. Bắt đầu đỗ bị từ chối khi ô còn sáng.
- Ở VEHICLE_IO/OBSERVE, dòng có `t_io`/`io_clock` của liên kết: của lần chạy vừa xong, hoặc của lần Bắt đầu đỗ tới. Với
  bo mô phỏng của giao diện, trước lần Bắt đầu đỗ đầu tiên chưa có bo nên hai ô này trống. Với cổng thật chưa mở, giao
  diện vẫn đọc được đồng hồ mà không mở cổng; test kiểm điều này bằng cách thay `serial.Serial`/`serial_for_url` bằng
  hàm từ chối.
- Màn hình thật: chưa thử. Độ trễ hiển thị của màn hình: chưa đo.

**Số lần đổi chiều** (thêm 02/10/2026, T12; chỉ kiểm offscreen, `tests/test_cusp_policy.py`).

- Dòng đường của cockpit ("… m · N lần đổi chiều") thêm "nhiều đổi chiều (> M)" màu cam khi đường có hơn
  `--warn-cusps M` lần đổi chiều (mặc định 7). Khi có `--max-cusps N` và đường vượt, dòng này thêm "vượt giới hạn N:
  không chạy" màu đỏ. Thanh trạng thái báo câu đầy đủ sau khi lập đường.
- Nút Bắt đầu đỗ vẫn bấm được; bấm thì hiện hộp "Không bắt đầu được" như các lý do từ chối khác (mục 3).
- Cờ: `python run_app.py [kịch bản] --max-cusps N --warn-cusps M`, hay
  `python -m autopark.ui.lidar_app --max-cusps N --warn-cusps M`. Số âm bị từ chối (mã 2) trước khi mở cửa sổ.
- Từ khi có giới hạn theo kịch bản (cùng ngày), thẻ "Kịch bản" có dòng giới hạn, ví dụ "Nghiệm thu DO-3b: đổi chiều tối
  đa 7 (N-D6 (b) đề xuất, CHƯA CHỐT)" hay "Đổi chiều: không chặn (T12, giới hạn CHƯA CHỐT); cảnh báo khi hơn 7".
  - Dòng này màu cam khi `--max-cusps` lớn hơn số của kịch bản ("--max-cusps 9 lớn hơn nên không dùng") hay siết hơn.
    Chú thích nêu tệp ngưỡng, trạng thái, 12 ký tự đầu SHA-256 và "sửa tệp ngưỡng thì mở lại kịch bản".
  - Dòng đường thêm "tối đa 7 (DO-3b)"; từ chối thì "vượt giới hạn 7 của DO-3b: không chạy". Thanh trạng thái báo giới
    hạn lúc mở tệp gắn.
  - Thẻ chỉ đọc; "Lưu" và "Lưu thành…" giữ thẻ. Tệp ngưỡng không cho được giới hạn thì "Mở…" hiện hộp "Không mở được
    kịch bản" và giữ kịch bản cũ.

**Thẻ "Xe", ô "Cấu hình xe"** (thêm 02/10/2026; chỉ kiểm bằng test offscreen với bo mô phỏng,
`tests/test_vehicle_choice_ui.py`).

- Ô liệt kê `configs/vehicle_*.json` (trừ `vehicle_io_sim*`), mỗi mục ghi tên tệp và tốc độ tối đa. Tệp xe nằm ngoài
  `configs/` (ví dụ chọn bằng `--vehicle-config`) hiện thêm "(ngoài configs/)". Nhãn của thẻ ghi tên tệp xe và tốc độ
  tối đa; cung tốc độ của đồng hồ lái đầy ở tốc độ tối đa của xe.
- Ô chỉ đổi được khi đang chỉnh hoặc sẵn sàng. Đổi xe hủy đường đã lập (về "Đang chỉnh sa bàn") và xóa log; phiên còn
  log thì giao diện hỏi trước, mặc định Không.
- Xe chọn ở ô này, hay bằng `run_app.py --vehicle-config` / `ui.lidar_app --vehicle-config`, được giữ khi "Mở…" kịch bản
  khác: tệp xe của kịch bản không được đọc, thanh trạng thái báo điều đó.
- "Lưu" ghi tệp xe đang dùng vào kịch bản; thanh trạng thái ghi "(xe: <tệp>)". Dùng "Lưu thành…" để tạo bản sao nghiệm
  thu, không ghi đè `scenarios/*.json`.
- Bo mô phỏng được chọn theo tệp xe lúc dựng thẻ, ngay trước mỗi Bắt đầu đỗ, sau khi đổi xe và sau khi mở kịch bản. Liên
  kết bo mô phỏng đang chọn nhận cấu hình mới mà vẫn giữ `start_refusals`/`board_actions`. Liên kết cổng COM hay bo ảo
  không bị đụng.
- Gợi ý của thẻ "Bo điều khiển" ghi tệp bo đã chọn kèm "(khớp tệp xe …)". Không có tệp khớp thì gợi ý nói vì sao, và
  rằng Bắt đầu đỗ ở VehicleIO sẽ bị TỪ CHỐI (`LIMITS_MISMATCH`) khi bo lệch theo hướng nguy hiểm.
- Bo ảo QEMU không đổi theo tệp xe: firmware biên dịch cứng 300 mm/s, nên xe nghiệm thu bị từ chối ở `VEHICLE_IO` qua bo
  ảo (mục 3).

**Ô "Nguồn tư thế"** (thêm 02/10/2026, T2; chỉ kiểm offscreen với LiDAR mô phỏng, bản ghi và nguồn giả). Chi tiết ở
[NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md) mục 7.

- Thẻ "Bo điều khiển" có ô "Nguồn tư thế" với ba lựa chọn: "Mô phỏng: định vị lý tưởng (mặc định)", "LiDAR mô phỏng:
  định vị trên vòng quét dựng từ sa bàn", "LiDAR thật: định vị trên bản đồ tĩnh". Lựa chọn cuối chỉ có trong
  `ui.lidar_app`, cần ngăn LiDAR và bản đồ.
- Nút "Chọn bản đồ LiDAR…" chọn thư mục của `autopark.lidar.map_builder`.
- Nút "Đặt xuất phát theo LiDAR" lấy tư thế OK hiện tại làm điểm xuất phát. Khi đó kiểm START với điểm xuất phát không
  còn là kiểm độc lập.
- Nhãn trạng thái định vị làm mới 5 Hz.
- `ui.lidar_app` nhận thêm `--pose-source`, `--lidar-map`, `--lidar-config`.
- Liên kết với "LiDAR mô phỏng" hay "LiDAR thật" dùng `LinkParams.for_lidar`: tuổi tư thế tối đa 0,25 s và dự đoán tư
  thế (mục 3, mục 9).
- Tổ hợp bị cấm (mục 4): bo mô phỏng + LiDAR thật, bo COM + LiDAR mô phỏng, bo ảo QEMU + nguồn LiDAR, cổng bo trùng cổng
  của ngăn LiDAR.

**Bo ảo QEMU** (thêm 02/10/2026; chỉ mô phỏng).

- **Chọn và chạy.** Chọn mục "Bo ảo QEMU (firmware xe trong giả lập)" thì hiện nút "Khởi động bo ảo" / "Tắt bo ảo" và
  một dòng trạng thái. Chọn mục không chạy gì. Rời mục khi bo đang chạy thì bo bị tắt ("Đã tắt bo ảo QEMU (đã chọn bo
  khác)"). Đóng cửa sổ thì đóng phiên (enable=0 + DISARM) rồi mới tắt QEMU. Nút khóa khi đang chạy.
- **Dòng trạng thái** lần lượt có thể là: "Bo ảo: chưa chạy.", "Đang build firmware env esp32s3_qemu… n s", "Đang khởi
  động QEMU… n s (tự thử lại tối đa 5 lần, espressif/qemu#175)", "Bo ảo đang chạy: <url> · firmware … · QEMU khởi động k
  lần · log <thư mục>", "Đang tắt bo ảo…", "LỖI bo ảo: …". Máy chưa cấu hình bo ảo thì dòng là "Máy này chưa cấu hình bo
  ảo: …" và nút khóa.
- **"Kiểm kết nối bo"** cần bo ảo đang chạy và không hỏi xác nhận. Nó báo thêm "Tốc độ, góc lái '—': firmware chưa đọc
  cảm biến; trong phiên đỗ số đo lấy từ xe mô phỏng phía laptop.". **"Xóa lỗi bo"** với bo ảo không hỏi xác nhận
  ESP32/DTR.
- **Nhãn cảnh báo.** Gợi ý của thẻ nói rõ đây KHÔNG phải bo thật. Cockpit có nhãn "BO ẢO QEMU · XE MÔ PHỎNG" màu cảnh
  báo, thấy được trong video T14, khi chọn bo ảo và nhánh không phải SIM. Thanh trạng thái lúc START báo "Nhánh chạy:
  VehicleIO qua BO ẢO QEMU (<url>) — tốc độ, góc lái, tư thế từ XE MÔ PHỎNG phía laptop; không phải bo hay xe thật". Ghi
  chú của dấu đồng bộ là "<chế độ>, bo ảo QEMU <url>".
- **Quan sát qua bo ảo:** phím mũi tên lái xe mô phỏng phía laptop (`PlantHumanDriver`), 0 COMMAND.
- Lần chạy ứng dụng với QEMU thật ngày 02/10/2026 gọi các nút bằng mã, không ai bấm tay (mục 7).

**Ngăn "Ghi cảm biến"** (thêm 02/10/2026, T3; chỉ có ở `ui.lidar_app`, không có ở `ui.app`; chỉ kiểm offscreen). Ngăn
này bật tắt bản ghi bốn camera + LiDAR trong phiên đỗ. "Bắt đầu ghi" khóa khi RUNNING/STOPPING; "Dừng ghi" luôn dùng
được và không chặn. Ngăn không gửi gì tới bo, không yêu cầu dừng, không chặn START. Mốc đồng hồ nằm ở
`session/clock.csv`, không ghi vào tệp dấu đồng bộ của cửa sổ ([GHI_PHAT_LAI_BAN_THU.md](GHI_PHAT_LAI_BAN_THU.md) mục
9).

## 7. Đã kiểm (mô phỏng, cổng serial giả và bo ảo; máy bàn, `.venv`)

Mục này liệt kê test và các lần chạy đã làm, theo thứ tự thời gian: phần nền ngày 24/09/2026, phần thêm tối 24/09 và
ngày 25/09, rồi hai đợt ngày 02/10/2026. Mọi phép thử chạy trên máy bàn với `.venv`. Bo là bo mô phỏng hay cổng serial
giả; từ 02/10/2026 có thêm bo ảo giả, LiDAR mô phỏng, và QEMU thật trong một test và một lần chạy ứng dụng. Không test
nào mở cổng thật. Đột biến và mọi số ở đây chỉ nói về phần mềm trên máy tính, không nói gì về bo thật.

Số test theo tệp (tính cả tham số hóa):

| Tệp test | Số test | Ghi chú |
|---|---|---|
| `tests/test_session_vehicle.py` | 34 → 60 → 61 | 24/09, tối 24/09, 02/10/2026 |
| `tests/test_vehicle_board_ui.py` | 26 → 30 → 45 | tối 24/09, sau rà soát, 02/10 (đợt 1); đợt 2 thêm 1 test |
| `tests/test_transport_vehicle_io.py` | thêm 15 | tối 24/09/2026 |
| `tests/test_nearfield_tof.py` | 33 → 54 | tối 24/09, sau rà soát |
| `tests/test_run_store_vehicle.py` | 4 → 33 | trước T9, sau T9 |
| `tests/test_session_stop_log.py` | 19 | T13 |
| `tests/test_cusp_policy.py`, `tests/test_cusp_acceptance.py` | 10, 44 | T12 |
| `tests/test_sync_marks.py`, `tests/test_export_log_ui.py` | 26, 4 | T14 và nút xuất log |
| `tests/test_fault_injection.py` | 31 | T6, mục 7.1 |
| `tests/test_qemu_plant.py`, `test_qemu_plant_timing.py`, `test_qemu_runner.py`, `test_qemu_board_ui.py` | 24, 5, 15, 10 | bo ảo QEMU, đợt 2 |
| `tests/test_session_lidar_pose.py`, `test_pose_prediction.py`, `test_bench_window_feed_and_close.py`, `test_lidar_pose_source.py`, `test_pose_source_ui.py` | 11, 9, 14, 9, 6 | T2, đợt 2 |
| `tests/test_vehicle_acceptance.py`, `tests/test_vehicle_choice_ui.py` | 10, 5 | xe nghiệm thu, đợt 2 |

**`tests/test_session_vehicle.py`.** Ngày 24/09/2026 tệp có 34 test, đạt 34/34. Mọi test chạy trên `SimVehicleIO` +
`FirmwareModel`, trừ ba test đồng hồ dùng `SerialVehicleIO` với cổng serial giả (`FirmwareSerialLoopback` với
`ManualClock`, hoặc một cổng giả theo đồng hồ tường ngay trong tệp test).

Muộn hơn tối 24/09/2026 tệp có **60 test, 60 đạt, 0 `xfail`**; chạy lại riêng tệp này khi sửa tài liệu cũng cho 60
passed. Phần thêm là 26 trường hợp từ 9 hàm test (danh sách thứ hai dưới đây). Một phần được thêm trước bản sửa: mất số
đo giữa lần chạy, thiếu góc lái lúc START và treo vòng điều khiển, trong đó có hai `xfail` ở pha 0. Phần còn lại đi cùng
bản sửa khoảng trống ở mục 8. Ngoài ba test đồng hồ, 12 trường hợp mới cũng dùng `SerialVehicleIO` với cổng serial giả
(`FirmwareSerialLoopback` + `ManualClock`): `test_realtime_hang_without_heartbeat_never_resumes` (8) và
`test_resume_after_hang_keeps_effort_zero_whatever_the_gap_before_the_stop` (4). Ngày 02/10/2026 tệp có 61 test, thêm
một test của T15 (dưới).

34 test ngày 24/09/2026, xếp theo nhóm:

- *Nhánh SIM và ô chọn nhánh*
  - `test_sim_is_default_and_keeps_phase0_world`: mặc định là SIM, `world` là `SimWorld`, snapshot không có khóa
    `vehicle_link`. Chọn SIM tường minh cho log giống hệt từng dòng.
  - `test_sim_link_mode_is_rejected`: `VehicleLink` không nhận chế độ SIM.
  - `test_drive_mode_cannot_change_while_running`: không đổi được nhánh khi đang chạy.
- *Đỗ qua bo mô phỏng*
  - `test_vehicle_io_follows_planned_path_through_the_firmware_model`: sa bàn `bai_do_xe.json` (có đổi chiều). Kết thúc
    COMPLETED, sai số < 3 cm / 3°, lệch khỏi quỹ đạo < 5 cm. Bo ARMED lúc START, DISARMED khi xong. Từng lệnh enable bo
    nhận (mm/s, mrad) bằng `speed_to_wire`/`steer_to_wire` của đúng lệnh bộ bám.
- *Dừng khi đang chạy, và không chạy tiếp*
  - `test_vehicle_io_stale_telemetry_stops_and_reconnect_never_resumes`: rút cáp giả khi xe đang chạy. Dừng đầu tiên là
    `STALE_TELEMETRY` (≤ 0,18 s), có ghi thêm `TELEMETRY_STALE`. Kết thúc FAULT `STOP_NOT_CONFIRMED`; xe trong bo giả tự
    dừng. Cắm lại rồi `connect()` lại: bo DISARMED, xe không nhúc nhích, không thêm lệnh enable nào. Chỉ sau khi lập lại
    đường và START mới chạy tiếp, và kết thúc COMPLETED.
  - `test_vehicle_io_fault_stops_and_start_is_refused_until_cleared`: E-stop giả gây `VEHICLE_FAULT`, kết thúc STOPPED.
    Từ lúc laptop nhận báo lỗi, không lệnh enable nào tới bo. Thả E-stop thì bo vẫn FAULT, và START bị từ chối ("FAULT")
    tới khi `clear_fault()`. Hai lần bị từ chối không đổi `commands.csv`/`telemetry.csv`/`events.csv`/kết quả của lần
    chạy E-stop; `Session.log` và `run_link` giữ nguyên. `start_refusals` có đúng một dòng `START_CHECK` "TỪ CHỐI" mỗi
    lần; `write_logs` ghi `start_refusals.csv` và `link.json` có `refused_starts`. Sau `clear_fault()`, START mở lần
    mới, và chỉ lúc đó log cũ mới được thay.
  - `test_stale_pose_source_stops_the_run`: nguồn tư thế ngừng trả dữ liệu: `STALE_POSE`, kết thúc STOPPED, bo DISARMED.
  - `test_vehicle_io_board_disarmed_elsewhere_stops_with_vehicle_not_armed`: DISARM từ nơi khác giữa lần chạy: dừng đầu
    tiên là `VEHICLE_NOT_ARMED`, không lệnh enable nào sau khi laptop biết.
  - `test_vehicle_io_command_timeout_after_freeze_never_resumes`: laptop "treo" 0,25 s (> hạn lệnh 0,15 s, < watchdog
    0,5 s): dừng `VEHICLE_STOPPED` (`COMMAND_TIMEOUT`), không lệnh enable nào sau khi hết treo. Tối 24/09/2026 mới thấy
    test này đạt chỉ vì lúc treo tình cờ rơi vào pha 3. Ép pha 0 thì trước bản sửa có một enable=1 tới bo; xem
    `test_vehicle_io_command_timeout_after_freeze_by_phase` ở danh sách thứ hai và mục 8.
  - `test_vehicle_io_command_rejected_stops_the_run`: bo từ chối mọi COMMAND: dừng `COMMAND_REJECTED`.
  - `test_close_while_running_vehicle_io_stops_then_disarms`: `Session.close()` giữa lúc chạy: lệnh cuối bo nhận là
    enable=0, bo DISARMED sau 50 ms.
  - `test_manual_after_vehicle_io_run_drops_old_link`: lái tay sau lần chạy `VEHICLE_IO`: `run_link` là None; liên kết
    đang chọn không bị đóng, START sau đó vẫn chạy.
- *Kiểm trước START*
  - `test_refused_start_keeps_the_previous_simulated_board_and_logs`: nhánh mô phỏng của giao diện. START bị từ chối
    (`START_NO_LINK`) giữ nguyên bo mô phỏng, bộ đếm lệnh, log và kết quả COMPLETED của lần trước. START đạt sau đó mới
    đóng và thay bo mô phỏng cũ.
  - `test_start_is_refused_when_the_real_state_disagrees`: xe lệch 10 cm so với xuất phát: từ chối, bo không bị ARM.
    E-stop đang nhấn: từ chối.
  - `test_start_refused_heading_off`: lệch hướng 10° (vị trí đúng): từ chối, bo DISARMED, `runs == 0`.
  - `test_start_refused_vehicle_rolling`: xe còn lăn 0,1 m/s, tư thế báo về vẫn ở điểm xuất phát: từ chối "chuyển động".
  - `test_observe_start_refused_while_board_still_references_speed`: quan sát, xe đứng yên nhưng bo còn tham chiếu tốc
    độ ≠ 0: từ chối.
  - `test_start_refused_board_already_running`: `VEHICLE_IO`, bo đang RUNNING theo lệnh từ nơi khác (tham chiếu 0): từ
    chối "RUNNING".
  - `test_start_refused_pose_not_fresh[0.5]`, `[-0.5]`: tư thế cũ 0,5 s, và tư thế "ở tương lai" 0,5 s (đồng hồ lệch):
    từ chối.
  - `test_start_refused_measured_pose_in_obstacle`: tư thế đo chạm vật cản: `begin_run` từ chối "chạm vật cản", bo không
    bị ARM.
  - `test_start_refused_without_measured_speed`: bo không có encoder (`speed_available=False`): từ chối.
  - `test_start_fault_refused_by_link_check`: bo FAULT (E-stop đã thả): lớp nối tự từ chối, không dựa vào việc firmware
    từ chối ARM.
  - `test_pose_lost_after_arm_disarms_and_refuses_start`: nguồn tư thế có mẫu lúc kiểm, mất mẫu ngay sau ARM. Kết quả là
    `SessionError` (không phải `AttributeError`), phiên READY, lớp nối không chạy. Bo nhận DISARM sau ARM
    (`HOST_DISARM`) và DISARMED sau 0,1 s, không nhờ watchdog 0,5 s. `start_refusals` = `START_CHECK`, `START_ABORTED`.
  - `test_observe_refuses_when_frame_after_disarm_has_no_steer`: quan sát, khung telemetry sau DISARM không có góc lái:
    từ chối, không gửi COMMAND.
- *Đồng hồ thời gian thực (cổng serial giả)*
  - `test_realtime_link_session_clock_follows_io_clock_without_blocking_reads`: `SerialVehicleIO` + cổng giả
    `ManualClock`. Mỗi 100 ms của bo, `advance(0,016)` đưa thời gian phiên tới `io.now() - t0` (sai ≤ 5 ms; `real_dt` và
    hệ số tua 4 không có tác dụng). Không lần đọc cổng rỗng nào; 45–55 lệnh trong 1 s đồng hồ io.
  - `test_realtime_serial_link_does_not_block_the_ui_tick`: cổng giả theo đồng hồ tường (đọc rỗng chờ 10 ms như
    pyserial), vòng giao diện 16 ms trong 1 s. Thời gian phiên luôn nằm giữa đồng hồ io đầu và cuối `advance()` (trừ ≤ 5
    ms). Không lần đọc chờ nào, `advance()` trung bình < 12 ms, 45–55 lệnh/s.
  - `test_serial_default_clock_is_fine_grained`: đồng hồ mặc định của `SerialVehicleIO` cho > 50 giá trị khác nhau trong
    50 ms, không phải bước 15,625 ms.
- *Quan sát*
  - `test_observe_logs_commands_and_never_enables_the_board`: người lái mô phỏng làm theo lệnh gợi ý và đỗ xong
    (COMPLETED). Sau mỗi bước 20 ms bo vẫn DISARMED, effort 0, không có lệnh đang hiệu lực. Bo **không nhận một COMMAND
    nào**, `commands_sent == 0`. Hơn 200 dòng `commands.csv` có `sent=0` và tốc độ mục tiêu > 0,1 m/s. `telemetry.csv`
    từ START trở đi toàn DISARMED, effort 0. `start_refusals.csv` có, rỗng.
  - `test_observe_disarms_a_board_found_armed`: bo đang ARMED lúc START: lớp nối DISARM trước khi quan sát. Giữa lúc
    quan sát có chương trình khác ARM và gửi lệnh: phát hiện `OBSERVE_NOT_DISARMED`. REQUEST duy nhất bo nhận sau đó là
    DISARM của lớp nối, và ngay lúc kết thúc bo đã DISARMED với lý do `HOST_DISARM`, không phải watchdog 0,5 s.
  - `test_observe_stop_ends_without_waiting_for_the_driver`: dừng quan sát thì kết thúc ngay dù người lái vẫn chạy. Test
    căn cho bước STOPPING đầu tiên rơi vào nhịp điều khiển, nên đi qua nhịp dừng (`command_stop`): có dòng STOP
    `sent=0`, bo không nhận COMMAND nào kể cả enable=0.
- *Giao diện offscreen*
  - `test_window_drive_mode_selector`: có 3 lựa chọn, mặc định SIM. Quan sát: ô bị khóa khi chạy, phím ↑ chạy xe mô
    phỏng, bo DISARMED, không gửi lệnh, nhãn "không gửi", xuất log có `commands.csv` và `start_refusals.csv`. VehicleIO:
    đỗ xong. Đổi về SIM được.
  - `test_window_manual_export_after_vehicle_io_run_has_no_old_link_logs`: lái tay sau lần chạy `VEHICLE_IO` rồi "Xuất
    log CSV…": có `m.csv`, không có `m_vehicle_io/`. Gán lại liên kết cũ vào phiên rồi xuất lần nữa vẫn không có
    `_vehicle_io`, nhờ lớp kiểm snapshot của giao diện.
  - `test_window_close_while_running_vehicle_io_disarms`: đóng cửa sổ giữa lúc tự đỗ `VEHICLE_IO`: lệnh cuối bo nhận là
    enable=0, bo DISARMED sau 50 ms.

26 trường hợp thêm tối 24/09/2026 (vẫn chỉ bo mô phỏng hoặc cổng serial giả):

- `test_measured_speed_lost_mid_run_stops_and_standstill_is_not_assumed`: bo mô phỏng thôi báo tốc độ giữa lúc chạy.
  Dừng đầu tiên là `NO_MEASURED_STATE`. Không có tốc độ đo thì không xác nhận được đã đứng yên, nên kết thúc FAULT
  `STOP_NOT_CONFIRMED`; đường bị hủy. Sau lệnh dừng đầu tiên (+15 ms) không lệnh enable nào tới bo; xe mô phỏng đứng
  yên, bo DISARMED.
- `test_measured_steer_lost_mid_run_stops`: bo thôi báo góc lái giữa lúc chạy: dừng `NO_MEASURED_STATE`, kết thúc
  STOPPED (tốc độ vẫn đo được), không enable nào sau lệnh dừng, bo DISARMED.
- `test_start_refused_without_measured_steer[VEHICLE_IO]`, `[OBSERVE]`: bo không có góc lái đo (AS5600). START bị từ
  chối "góc lái" trước khi ARM, và trước DISARM của quan sát; 0 COMMAND; `start_refusals` có đúng một `START_CHECK` nhắc
  AS5600.
- `test_command_timeout_while_heartbeat_keeps_link_stops_and_never_resumes[0]`…`[3]`: vòng điều khiển treo 1 s trong khi
  một vòng giống `Heartbeat` vẫn đọc telemetry và PING (≥ 8 PING). Bo về ARMED (`COMMAND_TIMEOUT`), không bị watchdog
  DISARM; telemetry vẫn mới, không `TELEMETRY_STALE`. Ở cả bốn pha: dừng đầu tiên `VEHICLE_STOPPED` (`COMMAND_TIMEOUT`),
  kết thúc STOPPED, không ARM lại, **không COMMAND enable=1 nào tới bo sau khi hết treo**. Pha 0 là `xfail(strict=True)`
  trước bản sửa (mục 8).
- `test_realtime_hang_without_heartbeat_never_resumes[300/1000 ms × pha 0–3]`: cổng serial giả, `ManualClock`, KHÔNG có
  luồng nào đọc cổng hay PING lúc treo, như phiên hiện nay. Treo 0,3 s thì bo về ARMED, treo 1 s thì DISARMED. Hết treo,
  cả 8 trường hợp: dừng đầu tiên là `STALE_TELEMETRY`, `VEHICLE_STOPPED` hoặc `VEHICLE_NOT_ARMED`; kết thúc STOPPED;
  không enable nào tới bo; bo DISARMED. Test chỉ kiểm tập ba mã. Chạy lại tối 24/09/2026 trên mã lúc đó bằng script tạm,
  máy bàn, thực tế ra `VEHICLE_STOPPED` khi treo 0,3 s và `VEHICLE_NOT_ARMED` khi treo 1 s, ở cả bốn pha.
- `test_vehicle_io_command_timeout_after_freeze_by_phase[0]`…`[3]`: như
  `test_vehicle_io_command_timeout_after_freeze_never_resumes` (treo 0,25 s bằng `SimVehicleIO.advance`, laptop vẫn đọc
  telemetry lúc treo) nhưng ép pha nhịp điều khiển. Dừng `VEHICLE_STOPPED` (`COMMAND_TIMEOUT`), không enable=1 nào sau
  khi hết treo. Pha 0 là `xfail(strict=True)` trước bản sửa.
- `test_resume_after_hang_sends_no_enable_to_the_sim_board`: bo mô phỏng, pha 0, treo 1 s với vòng giống `Heartbeat`;
  đồng hồ io đi trước thời gian phiên 0,9–1,1 s. Sau khi hết treo, lệnh đầu tiên bo nhận là enable=0, không có enable=1,
  effort của bo luôn 0. Test này thay test ghi hành vi lỗi `test_resume_burst_commands_share_sim_clock_ms`.
- `test_resume_after_hang_keeps_effort_zero_whatever_the_gap_before_the_stop[0/10/20/40]`: cổng serial giả,
  `ManualClock`, pha 0, treo 1 s trong khi một vòng đọc telemetry và PING. Bo chạy thêm 0/10/20/40 ms trước lệnh dừng
  đầu tiên, thay cho thời gian tính và trễ USB trên máy thật. Kết quả: không enable=1 nào tới bo, effort 0 ở mọi khoảng.
  Trước bản sửa, một enable=1 tới trước và effort lên 0/107/115/130 ‰; đây là số của mô hình bo với đầu vào đứng yên,
  không phải số đo. Test này thay `test_resume_burst_effort_grows_with_gap_between_commands`.
- `test_command_refuses_enable_while_a_stop_event_is_pending`: lớp chặn thứ hai. Đặt một sự kiện dừng vào hàng chờ của
  lớp nối rồi gọi thẳng `command()`: trả `HALTED`, không COMMAND nào được gửi, dòng `commands.csv` có `sent=0`.

**`tests/test_vehicle_board_ui.py`: so giới hạn, bo thật chưa có tư thế, "Kiểm kết nối bo", thẻ "Bo điều khiển"** (thêm
muộn tối 24/09/2026). Lúc thêm tệp có **26 test, 26 đạt**. Sau đợt sửa theo rà soát muộn hơn cùng tối, tệp có **30 test,
30 đạt**; bốn test mới và phần thêm của `test_sim_truth_pose_is_never_paired_with_another_board` được ghi "thêm muộn"
trong danh sách dưới. Ngày 02/10/2026 (đợt 1) tệp có 45 test: thêm 14 test của nút "Xóa lỗi bo" (T15) và
`test_pose_wrapper_unwrapping_stops_for_proxies_and_cycles` (sửa sau review). Đợt 2 thêm
`test_window_probe_releases_the_port_the_link_holds_open` (danh sách T2 cuối mục).

Bo là `SimVehicleIO` hoặc `FirmwareModel` sau cổng serial giả (`FirmwareSerialLoopback` + `ManualClock`).
`serial.Serial` bị thay bằng hàm ghi lại mọi lần mở và từ chối; `serial.tools.list_ports.comports` bị thay bằng danh
sách giả. Không test nào mở hay liệt kê cổng thật. 30 test sau rà soát:

- *So giới hạn lúc START*
  - `test_vehicle_io_start_refused_when_board_limits_are_risky[3 trường hợp]`: firmware 400 mm/s, góc lái 400 mrad (nhỏ
    hơn 30°), giảm tốc 400 mm/s². START bị từ chối "Giới hạn của bo", không ARM, 0 COMMAND, bo DISARMED;
    `start_refusals` = `LIMITS_MISMATCH` (STOP) rồi `START_CHECK` "TỪ CHỐI".
  - `test_vehicle_io_board_stricter_only_warns_and_runs`: firmware 250 mm/s < 300. Có dòng `LIMITS_MISMATCH` LOG "chỉ
    cảnh báo", `START_CHECK` "Đạt ... lệch 1 (0 nguy hiểm)"; START vẫn chạy và gửi lệnh; `link.json` có `limits_check`.
  - `test_observe_logs_risky_limits_but_does_not_refuse`: quan sát với firmware 400 mm/s: START đạt, dòng LOG, 0
    COMMAND.
  - `test_matching_limits_add_no_row_and_are_reported_in_start_check`: giới hạn khớp: không có dòng `LIMITS_MISMATCH`,
    `START_CHECK` ghi "giới hạn: khớp".
- *Bo thật chưa có tư thế*
  - `test_real_port_start_is_refused_before_the_port_is_opened[VEHICLE_IO/OBSERVE]`: `VehicleLink.serial_port`. START bị
    từ chối hai lần "nguồn tư thế thật ... COMx ... Cổng chưa được mở"; không lần mở cổng nào, 0 khung gửi;
    `START_NO_POSE_SOURCE`.
  - `test_sim_truth_pose_is_never_paired_with_another_board`: `SimTruthPose` ghép với bo serial, bo mô phỏng khác, hay
    `serial_port`: ValueError. Phần thêm muộn tối 24/09/2026: `SimTruthPose` dựng quanh chính bo serial, ở `VEHICLE_IO`
    và `OBSERVE`: ValueError, 0 khung gửi, bo chưa kết nối.
- *Hàm `probe_board`*
  - `test_probe_board_says_hello_reads_telemetry_and_closes`: cổng giả. Đúng một HELLO được ghi ra, 5 khung DISARMED,
    giới hạn khớp, 0 COMMAND/REQUEST, cổng đóng; báo cáo có firmware 1.0, `boot_id`.
  - `test_probe_board_disarms_an_armed_board_and_never_arms`: bo đang ARMED (chương trình khác). Sau khi kiểm, bo
    DISARMED (`NEW_SESSION`), không COMMAND/REQUEST nào.
  - `test_probe_board_reports_risky_limits`: firmware 400 mm/s: sự kiện `LIMITS_MISMATCH` STOP, báo cáo "START ở
    VEHICLE_IO sẽ bị TỪ CHỐI".
  - `test_probe_board_silent_board_times_out_and_still_closes`: bo im lặng: lỗi "HELLO_ACK", cổng vẫn đóng, báo cáo có
    "Không nhận được HELLO_ACK.".
  - `test_probe_board_hello_but_no_telemetry_times_out_disarms_once_and_closes` (thêm muộn): bo trả HELLO_ACK nhưng
    không gửi telemetry. Lỗi "0/5 khung" sau 1 s (đồng hồ io, không đọc quá 1,1 s), `TELEMETRY_STALE`, trên dây đúng
    HELLO + một REQUEST DISARM, 0 COMMAND, cổng đóng. Bo giả tự báo lỗi nếu vòng đọc chạy quá 10 s, nên bỏ hạn chờ thì
    test hỏng thay vì treo.
  - `test_probe_board_keeps_hello_when_session_refused_for_long_telemetry_period` (thêm muộn): bo chọn chu kỳ 400 ms,
    giới hạn 400 mm/s. Phiên bị từ chối nhưng báo cáo vẫn có HELLO_ACK (`boot_id`, chu kỳ 400 ms), so giới hạn (nguy
    hiểm, `LIMITS_MISMATCH` STOP, "sẽ bị TỪ CHỐI"), lỗi "bị từ chối ... 400 ms", không có "Không nhận được HELLO_ACK".
    Chỉ HELLO trên dây, cổng đóng.
  - `test_probe_board_keeps_hello_when_connect_refuses_the_board_period` (thêm muộn): như trên với chu kỳ 200 ms, giới
    hạn khớp. Báo cáo có firmware 1.0, `boot_id`, "Giới hạn bo", "khớp", và dòng "LỖI: HELLO_ACK nhận được nhưng phiên
    bị từ chối: Bo chọn chu kỳ telemetry 200 ms".
  - `test_probe_board_does_not_report_an_old_hello_when_the_port_is_closed` (thêm muộn): phiên cũ có HELLO_ACK, cổng đã
    đóng: lỗi "Cổng chưa mở", báo cáo không mang HELLO_ACK cũ.
  - `test_probe_board_unplug_after_hello_reports_link_error`: rút cáp giả sau HELLO: `LINK_ERROR`, lỗi "mất phiên hoặc
    lỗi cổng".
  - `test_probe_board_on_the_simulated_board`: kiểm trên `SimVehicleIO`: đạt, báo "MÔ PHỎNG".
  - `test_list_serial_ports_*` (2): sắp theo số cổng (COM3, COM4, COM10), đánh dấu Espressif; liệt kê lỗi thì trả rỗng.
- *Giao diện*
  - `test_window_port_choice_defaults_to_sim_and_lists_ports_on_demand`: dựng cửa sổ không liệt kê cổng; mở danh sách
    thì quét. Chọn COM10 ở `VEHICLE_IO` → `SerialVehicleIO` chưa mở + `NoPoseSource`. Rút cáp: cổng vẫn giữ "(không
    thấy)". Về bo mô phỏng và SIM được.
  - `test_window_real_port_start_is_refused_with_clear_message[VEHICLE_IO/OBSERVE]`: Bắt đầu đỗ với COM4: hộp thoại
    "Không bắt đầu được" nêu "nguồn tư thế thật" và COM4; phiên READY; không mở cổng.
  - `test_window_probe_real_port_sends_only_hello`: nút "Kiểm kết nối bo" hỏi xác nhận có tên cổng, báo cáo
    firmware/giới hạn/5 khung, chỉ HELLO trên dây, cổng đóng.
  - `test_window_probe_shows_risky_limits`: firmware góc lái 700 mrad: thẻ hiện `LIMITS_MISMATCH` và "TỪ CHỐI".
  - `test_window_probe_cancelled_or_failing_open_sends_nothing`: bấm "No" thì không mở cổng. Mở cổng lỗi thì thẻ hiện
    "Không mở được COM4".
  - `test_window_probe_simulated_board_asks_nothing`: bo mô phỏng: không hỏi, báo "MÔ PHỎNG".
  - `test_window_start_shows_limits_warning_or_refusal`: bo mô phỏng của giao diện với firmware 250 mm/s: chạy, thanh
    trạng thái "LIMITS_MISMATCH (cảnh báo)". Với 400 mm/s: hộp thoại từ chối nêu "tốc độ lớn nhất".
  - `test_window_board_controls_locked_while_running`: khi chạy, ô cổng và nút kiểm bị khóa; gọi thẳng `_probe_board()`
    cũng không làm gì.

**Giao thức và ToF** (tối 24/09/2026). `tests/test_transport_vehicle_io.py` thêm 15 test: `compare_limits` từng trường
và từng hướng, sai số làm tròn, sự kiện `check_limits`, `SerialVehicleIO.deferred` không mở cổng. ToF có
`tests/test_nearfield_tof.py`, lúc đầu 33 test ([GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 12). Sau đợt sửa theo rà soát
muộn hơn cùng tối, tệp ToF có 54 test, 54 đạt:

- Test cũ `test_invalid_reading_makes_the_layer_stale_and_marks_nothing` khẳng định đúng hành vi lỗi "một ToF mặt nạ 0
  làm cả lớp không hợp lệ". Nó được thay bằng `test_unusable_tof_drops_only_its_own_arc`.
- Hai ca "tối đa" của `test_unusable_values_...` chuyển sang
  `test_values_at_or_beyond_max_range_are_valid_but_mark_nothing`.
- Thêm test mức `fuse()`: camera nói FREE, chỉ ToF trước thấy vật; ba khung trộn; không gian trống với lớp bắt buộc.
  Thêm test stamp khung không hợp lệ, `required_sensors`, đường nguồn chung, và các ca bảng gá `null`/chuỗi/bool/danh
  sách.

**Đột biến cho so giới hạn, thẻ "Bo điều khiển" và ToF** (muộn tối 24/09/2026, máy bàn, `.venv`). Cách làm: sửa mã trên
**bản sao** trong thư mục tạm, không đụng repo; mỗi lần một đột biến; chạy các tệp test liên quan.

Lần đầu chạy trên ba tệp `test_vehicle_board_ui.py`, `test_transport_vehicle_io.py`, `test_nearfield_tof.py`; bản gốc
trên bản sao đạt 123 test. **31 đột biến, cả 31 bị bắt**:

- Phần so giới hạn: đảo hướng nguy hiểm; bỏ sai số làm tròn; coi góc lái nhỏ hơn là không nguy hiểm; bỏ so `stop_decel`;
  đảo action của sự kiện; `connect()` không xóa kết quả cũ.
- `deferred` mở cổng ngay.
- `VehicleLink`: không từ chối START khi lệch nguy hiểm; từ chối cả ở quan sát; không so giới hạn lúc START; bỏ chặn
  `NoPoseSource`; bỏ chặn `SimTruthPose` ghép sai.
- `probe_board`: gửi enable=0; ARM bo; không đóng cổng.
- Giao diện: liệt kê cổng lúc dựng; bỏ qua cổng đã chọn; bỏ cổng đã rút; không hỏi trước khi mở cổng; không khóa khi
  chạy; mở danh sách không quét; không cảnh báo giới hạn lúc START.
- ToF: nhận số đo đúng tầm tối đa; bỏ kiểm hữu hạn; bỏ tầm tối thiểu; bỏ stamp của khung; đảo chỉ số; yaw không đổi sang
  radian; không kiểm khóa lạ; `add_readings` cập nhật dở; None thành hợp lệ.

Đo lại muộn hơn cùng tối, sau đợt sửa theo rà soát, cùng cách làm, trên bốn tệp `test_vehicle_board_ui.py`,
`test_transport_vehicle_io.py`, `test_nearfield_tof.py`, `test_fusion.py`; bản gốc trên bản sao đạt 162 test. Danh sách
và số ở trên là trước bản sửa. Lần đo lại: **50 đột biến, cả 50 bị bắt**.

- 30 đột biến cũ chạy lại (neo lại chuỗi ở chỗ mã đã đổi), cả 30 bị bắt. Đột biến "ToF: nhận số đo đúng tầm tối đa" bị
  bỏ, vì nay số đo ≥ tầm tối đa có bit hợp lệ là hợp lệ và không đánh dấu ô nào. Đây là thay đổi có chủ ý, xem
  GIAO_THUC_XE.md mục 12.
- 20 đột biến mới cho bản sửa, cả 20 bị bắt:
  - ToF, khung telemetry: quay lại luật "mọi ToF hợp lệ"; bỏ qua stamp khung; `add_telemetry` không truyền stamp khung.
  - ToF, nguồn chung: `all` thay `any`; luôn hợp lệ.
  - `required_sensors`: bỏ; cảm biến bắt buộc chưa có số đo không tính; tên lạ không bị từ chối.
  - Tầm tối đa: số đo ≥ tầm tối đa lại thành không hợp lệ; vẫn đánh dấu cung; bỏ ghi chú "ngoài tầm".
  - `status()` thiếu `invalid_sensors`.
  - Bảng gá: nhận `null`/chuỗi qua `float()`; bỏ kiểm `sensor_id` khi đọc JSON; bỏ kiểm `sensor_id` trong
    `__post_init__`.
  - `VehicleLink`: chặn `SimTruthPose` chỉ so io (bản cũ).
  - `probe_board`: bỏ giữ HELLO_ACK khi phiên bị từ chối; báo cả HELLO_ACK cũ; giữ HELLO mà không so giới hạn; bỏ hạn
    chờ telemetry.

Đột biến "ép lại `str(sensor_id)`" là đột biến tương đương, vì sensor_id vừa được kiểm là chuỗi ngay trước đó, nên không
tính. Đây vẫn là đột biến trên bản tham chiếu Python, bo mô phỏng và cổng serial giả, không nói gì về bo thật.

**Đột biến để kiểm test của phiên qua `VehicleIO`.** Đợt đầu vá tạm trong tiến trình bằng monkeypatch, không sửa tệp
nào. Sáu đột biến đều bị ít nhất một test bắt:

1. Quan sát mà vẫn gửi lệnh.
2. Bỏ qua sự kiện dừng.
3. Bỏ kiểm tuổi telemetry và tư thế.
4. Bỏ kiểm trước START.
5. Không DISARM khi kết thúc.
6. Lúc dừng vẫn gửi lệnh chạy.

Đợt hai, 24/09/2026, sau khi sửa theo rà soát: sửa mã trên **bản sao** trong thư mục tạm (không đụng repo), mỗi lần một
đột biến, chạy lại cả tệp. 27 đột biến đều bị ít nhất một test bắt (bản gốc: 34/34 đạt):

7. Vòng điều khiển đọc cổng có chờ (`poll()` thay vì `poll(block=False)`).
8. Thời gian phiên cộng `real_dt` của giao diện thay vì theo đồng hồ io.
9. `SerialVehicleIO` bỏ qua `block=False`.
10. Đồng hồ mặc định của `SerialVehicleIO` về lại `time.monotonic()`.
11. `observe()` đọc đồng hồ trước khi lấy mẫu tư thế, nên mẫu vừa đóng dấu bị coi là "ở tương lai" (STALE_POSE giả).
12. Không DISARM khi lỗi sau ARM.
13. Bỏ kiểm lại tư thế sau ARM.
14. Quan sát không kiểm góc lái của khung sau DISARM.
15. Lái tay giữ liên kết của lần chạy trước.
16. Xóa log của lần trước trước khi kiểm START.
17. Không trả lại bo mô phỏng của lần trước khi START bị từ chối.
18. Không ghi dòng vào `start_refusals`.
19. Quan sát gửi enable=0 lúc dừng.
20. Bỏ kiểm "xe đang chuyển động" (cả hai phần); riêng phần tham chiếu tốc độ của bo.
21. Bỏ kiểm bo đang RUNNING.
22. Bỏ kiểm lệch hướng; bỏ kiểm tuổi tư thế; bỏ kiểm tư thế chạm vật cản; bỏ kiểm có tốc độ/góc lái đo; bỏ kiểm bo
    FAULT.
23. Thấy bo ARMED/RUNNING giữa lúc quan sát mà không gửi DISARM.
24. Bỏ nâng mức `COMMAND_REJECTED`/`VEHICLE_STOPPED` thành dừng.
25. Bỏ kiểm `VEHICLE_NOT_ARMED`.
26. `Session.close()` không đóng liên kết; `VehicleLink.close()` không gửi enable=0 và DISARM.
27. Giao diện bỏ kiểm snapshot khi xuất log.

27 đột biến của đợt hai được chạy với 34 test lúc đó, chưa chạy lại với 60 test sau này. Muộn hơn tối 24/09/2026, bản
sửa khoảng trống ở mục 8 có thêm hai đột biến. Cách làm: vá trong tiến trình bằng một plugin pytest đặt ngoài repo,
không sửa tệp nào; chạy khi viết tài liệu này, máy bàn, `.venv`.

28. Bỏ lời gọi `VehicleLink.refresh()`, giữ lớp chặn thứ hai: 7 test hỏng, 53 đạt. Bảy test đó là pha 0 của
    `test_command_timeout_while_heartbeat_keeps_link_stops_and_never_resumes` và
    `test_vehicle_io_command_timeout_after_freeze_by_phase`, `test_resume_after_hang_sends_no_enable_to_the_sim_board`,
    và bốn trường hợp của `test_resume_after_hang_keeps_effort_zero_whatever_the_gap_before_the_stop`.
29. Bỏ lớp chặn "còn sự kiện dừng chưa lấy" trong `command()`: chỉ
    `test_command_refuses_enable_while_a_stop_event_is_pending` hỏng, 59 đạt. Lớp này chỉ chặn sự kiện lớp nối ĐÃ gom;
    việc chặn khoảng trống ở pha 0 là nhờ `refresh()`.

**Các lượt chạy nhiều tệp cùng lúc.** Thời gian của các lượt này đo lúc các agent khác hay việc khác có thể đang chạy
song song trên cùng máy, nên không dùng làm số đo tốc độ.

- **24/09/2026, sau đợt sửa theo rà soát:** chạy lại các test có sẵn (`test_phase0`, `test_session`, `test_session_run`,
  `test_runtime_safety`, `test_ui_smoke`, bốn tệp `test_transport_*`, `test_background_work`, `test_fusion`,
  `test_fusion_demo`, `test_lidar_dock_ui`, `test_vehicle_editing_ui`, `test_scenario_store`) cùng tệp mới: 361 đạt, 0
  lỗi. Số 361 là từ trước khi thêm các test tối 24/09 và bản sửa khoảng trống; khi đó `tests/test_session_vehicle.py` có
  34 test. Tổng cho đúng nhóm tệp này sau đó chưa đếm lại.
- **Cuối tối 24/09/2026, bộ test đầy đủ:** 895 đạt, 6 bỏ qua (mô-đun cần torch), 215 s.
- **Muộn tối 24/09/2026, sau phần so giới hạn / "Bo điều khiển" / ToF, 17 tệp:** `test_vehicle_board_ui` 26,
  `test_nearfield_tof` 33, `test_session_vehicle` 60, bốn tệp `test_transport_*` 52 + 73 + 64 + 11, `test_ui_smoke` 9,
  `test_phase0` 13, `test_session` 11, `test_session_run` 11, `test_runtime_safety` 40, `test_fusion` 14,
  `test_fusion_demo` 7, `test_run_store_vehicle` 4, `test_vehicle_editing_ui` 4, `test_lidar_dock_ui` 5. Kết quả **437
  đạt, 0 lỗi**, 127 s. Bộ test đầy đủ không chạy lại.
- **Muộn hơn tối 24/09/2026, sau đợt sửa theo rà soát, 19 tệp:** `test_vehicle_board_ui` 30, `test_nearfield_tof` 54,
  `test_session_vehicle` 60, bốn tệp `test_transport_*` 52 + 73 + 64 + 11, `test_ui_smoke` 9, `test_phase0` 13,
  `test_session` 11, `test_session_run` 11, `test_runtime_safety` 40, `test_fusion` 14, `test_fusion_demo` 17 (tệp do
  việc khác sửa cùng tối), `test_run_store_vehicle` 4, `test_vehicle_editing_ui` 4, `test_lidar_dock_ui` 5,
  `test_background_work` 8, `test_scenario_store` 25. Kết quả **505 đạt, 0 lỗi**, 107 s. Bộ test đầy đủ không chạy lại.
- **25/09/2026:** mã và test của tài liệu này đã commit và push: `c43e8d3` (nối `VehicleIO` vào phiên, quan sát, bản sửa
  khoảng trống ở mục 8) và `6db5087` (thẻ "Bo điều khiển", so giới hạn, ToF); `origin/main` = `54cb3e2`. Đếm lại ở HEAD
  bằng `--collect-only`: số test của cả 19 tệp trên không đổi (tổng 505). Bộ test đầy đủ chạy lại trên mã trùng
  `54cb3e2` (cây làm việc chỉ khác ở tài liệu): **1242 đạt, 7 bỏ qua** (mô-đun cần torch), 0 lỗi, 313 s. Vẫn chỉ bo mô
  phỏng và cổng serial giả.

**Đồng hồ khi chạy qua `SerialVehicleIO`.** Script tạm ngày 24/09/2026, không lưu trong repo; cổng serial giả theo đồng
hồ tường, bo là `FirmwareModel`, xe đứng yên; vòng giao diện 16 ms trong 3 s; máy bàn.

| Mã | Thời gian phiên / đồng hồ io | Lệnh/s | `advance()` trung bình | Lần đọc chờ |
|---|---|---|---|---|
| Trước khi sửa (dựng lại trên bản sao) | 0,40 | 20 | ≈ 212 ms (mỗi bước chờ 10 ms) | 191 |
| Sau khi sửa | 1,00 | 50 | ≈ 1,1 ms | 0 |

Đây là cổng giả trên laptop, không phải ESP32-S3. Nó chỉ chứng minh vòng điều khiển không chờ cổng và bám đồng hồ io.

**Số của mô phỏng.** Script tạm ngày 24/09/2026, không lưu trong repo; xác định theo seed; bo mô phỏng lấy cấu hình từ
`configs/vehicle_io_sim.json`; sa bàn `bai_do_xe.json`, 2,55 m, 1 lần đổi chiều.

| Lần chạy | Kết thúc | Sai số / quãng dừng | Ghi chú |
|---|---|---|---|
| `VEHICLE_IO` | COMPLETED sau 20,95 s mô phỏng | sai số cuối 0,60 cm / +1,15°; lệch lớn nhất khỏi các điểm quỹ đạo 1,25 cm | 1.049 COMMAND; \|effort\| lớn nhất 454 ‰ (mô phỏng dùng trần 1000 ‰) |
| `OBSERVE`, người lái mô phỏng làm đúng lệnh gợi ý | COMPLETED sau 20,61 s | sai số 0,73 cm / +1,27° | 0 COMMAND; effort luôn 0 |
| Rút cáp giả ở 0,10 m/s (đường thẳng 1,5 m) | FAULT `STOP_NOT_CONFIRMED` sau 2,1 s | xe mô phỏng dừng sau 0,43 s, trôi 4,1 cm | phát hiện `STALE_TELEMETRY` sau 120 ms |
| E-stop giả ở 0,10 m/s | STOPPED sau 0,25 s | xe mô phỏng dừng sau 0,18 s, trôi 0,9 cm | laptop nhận `VEHICLE_FAULT` sau 15 ms |

Các số trên là của mô hình giả định (trễ, vùng chết, nhiễu, E-stop cắt động lực ngay), **không phải** quãng dừng hay độ
bám đường của MN300. Thời điểm phát hiện mất telemetry phụ thuộc pha của chu kỳ telemetry 50 ms. Với cấu hình bo nhanh
dùng trong test (`boot_hold_ms` 200), cùng phép thử cho 160 ms.

**Test thêm ngày 02/10/2026, đợt 1** (công cụ nghiệm thu T6, T9, T12–T15). Máy bàn, `.venv`, giao diện offscreen; bo mô
phỏng hoặc cổng serial giả. Ở test giao diện, `serial.Serial` và `comports` bị thay bằng bản giả; không test nào mở
cổng, camera hay LiDAR thật. Số test đếm bằng `pytest --collect-only` ngày 02/10/2026, sau lượt sửa theo review. Kết quả
chạy trên bản commit ghi ở biên bản của lượt chạy toàn bộ, không ghi ở đây.

*T13* — [`tests/test_session_stop_log.py`](../tests/test_session_stop_log.py), 19 test (16 lúc viết mã, 3 thêm sau
review). Thêm 3 test trong `tests/test_lidar_dock_ui.py` (đếm sau đợt 1: 8 test) và 6 trong
`tests/test_camera_dock_ui.py`: 5 mục của `test_ai_stop_in_vehicle_io_is_logged_with_its_code`, cộng
`test_every_unusable_kind_used_by_the_dock_has_its_own_stop_code`. Tệp camera đếm sau đợt 1 có 30 mục, kể cả test T6 ở
mục 7.1. Hai test dùng `SerialVehicleIO` với cổng serial giả.

- `test_session_stop_rows_mirror_safety_events[estop/map_changed/no_measured_state/stale_pose/stale_telemetry]`: dòng
  `session_stop` khớp từng phần tử `safety_events` (mã, nguồn, `t_session`, action, message). Dòng đầu đúng mã và nguồn.
  `t_io` không giảm và không muộn hơn STOP đầu của `commands.csv`. Mô tả vật chỉ ở dòng log.
- `test_user_stop_is_logged_but_not_added_to_safety_events`: một dòng `USER_STOP` dù gọi hai lần; `safety_events` rỗng;
  `run_events` giữ {t, kind, reason}.
- `test_fused_map_invalid_stop_from_bridge_is_logged`: một dòng (`FUSED_MAP_INVALID`, `lidar_bridge`); lần hai lúc
  STOPPING không thêm; `run_events` mang mã và nguồn.
- `test_reset_while_running_logs_user_reset`: đặt lại ngay sau START: một dòng `USER_RESET`, kết quả RESET.
- `test_collision_in_mirrored_world_is_logged`: va chạm hình học: FAULT, đúng một dòng `COLLISION`.
- `test_observe_mode_logs_session_stops_without_sending`: quan sát: dòng `USER_STOP`, 0 COMMAND.
- `test_realtime_session_stop_row_uses_the_io_clock`: cổng serial giả, `ManualClock`. `t_io` = `io.now()` lúc yêu cầu,
  lệch 30–35 ms so với thời gian phiên khi io đi trước 30 ms.
- `test_write_logs_has_t_perf_and_clock`, `test_link_json_clock_is_null_before_any_run`: tiêu đề hai tệp =
  `EVENT_FIELDS`; mọi dòng, kể cả `START_NO_LINK`, có `t_perf`; `clock` đúng, null khi chưa mở lần chạy nào.
- `test_link_json_clock_converts_io_time_to_perf_counter_on_a_wall_clock_board` (sau review): cổng serial giả, đồng hồ
  io = `perf_counter` dời 500 s. `t_io` cộng độ lệch của `clock` khớp `t_perf` của dòng `USER_STOP`, lệch < 0,05 s; test
  chỉ kiểm dòng này.
- `test_nothing_is_logged_after_the_run_has_ended` (sau review): sau STOPPED, bấm Dừng, cầu nối báo bản đồ hỏng, chèn
  vật, đặt lại: không thêm dòng.
- `test_a_failing_io_clock_never_blocks_the_stop` (sau review): đồng hồ io ném lỗi lúc yêu cầu dừng. Phiên vẫn STOPPING
  rồi STOPPED; dòng `USER_STOP` có `t_io` trống và lời lỗi.
- `test_sim_branch_safety_events_unchanged`, `test_sim_branch_stop_request_keeps_the_old_run_events`: nhánh SIM không
  đổi.
- `test_window_stop_in_vehicle_io_logs_user_stop_and_exports`: giao diện, nút Dừng rồi "Xuất log CSV…".
- `test_lidar_disconnect_in_vehicle_io_is_logged`,
  `test_lidar_setting_change_in_vehicle_io_is_logged_with_its_code[mirror/mask]`: ngăn LiDAR, mã và nguồn `lidar_dock`.
- `test_ai_stop_in_vehicle_io_is_logged_with_its_code[stale/disabled/error/config/unknown_kind]`,
  `test_every_unusable_kind_used_by_the_dock_has_its_own_stop_code`: ngăn AI camera, mã và nguồn `camera_dock`. Loại
  chưa có mã riêng dừng với `CAMERA_AI_UNUSABLE`. Trước bản sửa sau review, loại này gây `KeyError` trong timer và xe
  không dừng.

*T15* — 14 test `-k clear_fault` trong `tests/test_vehicle_board_ui.py` (tệp sau đợt 1 có 45 test), và
`tests/test_session_vehicle.py::test_fault_refused_start_then_link_clear_fault_then_start` (tệp nay 61).

- `test_clear_fault_after_release_goes_to_disarmed_without_arm_or_command[VEHICLE_IO/OBSERVE]`: bo mô phỏng FAULT ESTOP,
  nút đã nhả, chưa có phiên. Trên dây: HELLO (bo giữ FAULT), đúng một REQUEST CLEAR_FAULT (không ARM, không DISARM), 0
  COMMAND. Khung sau là DISARMED, lỗi NONE; 1 s sau xe đứng yên, effort 0, bo vẫn DISARMED. Có một dòng
  `board_actions.csv` đủ cột, `message` có đủ sự kiện, bốn cột `hello_*` đúng HELLO_ACK. Không đụng `event_rows`,
  `start_refusals`.
- `test_clear_fault_sends_nothing_while_estop_pressed_or_board_not_in_fault`: nút còn nhấn: ESTOP_PRESSED, không REQUEST
  nào. Nhả rồi bấm lại: CLEARED trên phiên đang có, không HELLO, trên dây PING rồi CLEAR_FAULT (2 REQUEST). Bo không
  FAULT: NOT_NEEDED. Phiên đã chốt `TELEMETRY_STALE`: mở phiên mới.
- `test_clear_fault_estop_pressed_after_the_telemetry_is_refused_by_the_board`: E-stop nhấn lại đúng lúc REQUEST tới bo:
  `ESTOP_ACTIVE`, REFUSED, `COMMAND_REJECTED`.
- `test_clear_fault_ack_ok_but_fault_again_is_not_confirmed`: ACK OK nhưng khung sau còn FAULT: NOT_CONFIRMED.
- `test_clear_fault_supply_low_refused_until_voltage_is_back_on_fake_serial`: cổng serial giả, SUPPLY_LOW:
  `FAULT_ACTIVE`; điện áp đủ: CLEARED. Trên dây HELLO, CLEAR_FAULT, PING, CLEAR_FAULT, không COMMAND.
- `test_clear_fault_on_a_reused_session_decides_on_a_frame_sent_after_the_press[released/pressed]` (sau review): cổng
  serial giả không ai đọc 120 s (hơn hai lần đọc 64 KiB khung DISARMED tồn đọng), rồi E-stop. Nút quyết định theo khung
  bo gửi sau lúc bấm, không báo NOT_NEEDED khi bo đang FAULT.
- `test_clear_fault_on_a_real_port_link_opens_the_port_then_closes_it`: cổng chưa mở được mở rồi đóng ở mỗi lần bấm.
  START sau đó vẫn `START_NO_POSE_SOURCE`, không mở thêm cổng.
- `test_clear_fault_open_failure_and_unplug_are_reported_not_raised`: không mở được cổng: NO_LINK. Rút cáp sau
  CLEAR_FAULT: NO_ACK, `LINK_ERROR`, không treo, không báo đã xóa.
- `test_clear_fault_blocked_for_ui_sim_board_open_run_and_closed_link`: bo mô phỏng của giao diện, RUNNING/STOPPING,
  liên kết đã đóng: `VehicleLinkError`, không ghi dòng, không CLEAR_FAULT nào tới bo.
- `test_window_clear_fault_button_follows_mode_board_and_run_state`,
  `test_window_clear_fault_on_a_real_port[released/pressed]`: nút bật/khóa theo nhánh, bo, trạng thái. Với cổng COM giả:
  hộp thoại xác nhận, nhãn xanh/vàng; trả lời No thì không mở cổng.
- `test_fault_refused_start_then_link_clear_fault_then_start`: E-stop → STOPPED → START bị từ chối vì FAULT →
  `clear_fault()` → START ARM lại (AT-2, DI-4 (d) ở mức mô phỏng).

*T9* — [`tests/test_run_store_vehicle.py`](../tests/test_run_store_vehicle.py), nay 33 test: 29 lúc viết mã, kể cả 4
test có từ trước T9, và 4 thêm sau review.

- Xuất gói và phát lại KHỚP ở `VEHICLE_IO` và `OBSERVE`. Từ chối khi phiên không còn log `VehicleLink`, khi chế độ lệch,
  khi liên kết chưa mở lần chạy nào. Băng ghi đủ mọi lần đọc io và mọi lần đọc tư thế; chưa chạy thì không có
  `run_start`.
- `test_replay_reproduces_the_stop[…]`: phát lại 10 kiểu dừng, dòng `session_stop` dựng lại đúng, lệch đồng hồ 0. Mười
  kiểu là: `STALE_POSE`; E-stop `VEHICLE_FAULT`; rút cáp → `STALE_TELEMETRY`, `TELEMETRY_STALE`, `STOP_NOT_CONFIRMED`;
  `MAP_CHANGED`; `COLLISION`; dừng tay; `FUSED_MAP_INVALID` của cầu nối; `COMMAND_REJECTED`; mất góc lái
  `NO_MEASURED_STATE`; `OBSERVE_NOT_DISARMED` có chờ DISARM trong lần đọc.
- Cổng serial giả, `ManualClock`, vòng điều khiển treo 300 ms: phát lại theo đồng hồ io đã ghi. Tư thế sửa tay 2 cm bị
  báo ở đúng dòng `commands.csv`. Khung lấy ngoài lớp nối bị báo KHÁC.
- Log thiếu `poses.csv`, `clock.csv` hay `log_format`, dòng hỏng, thiếu cột `call`: bị từ chối.
- Sau review: tám kiểu gói hỏng bị `replay_vehicle_run` từ chối (`ReplayNotSupported`) thay vì để lỗi lọt ra. Qua dòng
  lệnh, test kiểm mã 2 với ba kiểu: CSV ANSI, thiếu `config_snapshot/run.json`, `run.json` không phải JSON (mục 5.1).
  Gói có BOM vẫn KHỚP. Số giây trong lời được so như cột đồng hồ: lệch 1 ms KHỚP, 10 ms KHÁC. Lỗi bất ngờ cho mã 3, và
  báo cáo in được cả khi stdout là cp1252.
- START bị từ chối không làm hỏng băng của lần trước, kể cả khi có dòng `board_actions.csv` của T15. Mã thoát CLI và
  dòng "Replay OK" của gói SIM. Giao diện offscreen: gói của một lần quan sát phát lại được.

*Gói SIM không đổi.* Đo lại ngày 02/10/2026 bằng script tạm của lượt sửa theo review, không lưu trong repo. Script so
gói ghi bằng `3148014` với gói ghi bằng cây làm việc có T5, T6, T9–T15, trên 4 lần chạy (đường thẳng COMPLETED, chèn
vật, dừng tay, `bai_do_xe`): 32 tệp, trừ `source.zip` và hai trường `created_utc`, `source_sha256` của manifest. Kết
quả: 28 tệp trùng từng byte; khác duy nhất là khóa `cusps` (T12) nối cuối `config_snapshot/run.json` của cả 4 gói. Mọi
khóa khác và thứ tự khóa giữ nguyên; cả 8 gói phát lại (`replay_run`) đúng trạng thái. Đợt 2 đổi
`config_snapshot/run.json` như sau; điều này đọc từ mã `Session.start_run`, chưa so lại gói:

- mọi lần chạy thêm `start_source` ("manual" hay "lidar_localize", T2) ngay sau `cusps`;
- lần chạy của tệp gắn nghiệm thu thêm `acceptance` (khóa cuối của `scenario`) và `cusp_rule` (ngay trước
  `vehicle_link`);
- phát lại bỏ qua thẻ (`test_replay_session_ignores_acceptance_tags`).

*T12* — `tests/test_cusp_policy.py`, 10 test, gồm:

- `test_refusal_through_a_vehicle_link_is_logged_before_any_board_io`: `VehicleLink.simulated(VEHICLE_IO)`, giới hạn 1,
  đường 2 lần đổi chiều. START bị từ chối, `link.io` vẫn None (chưa dựng bo), 0 lần chạy. `start_refusals.csv` có đúng
  một dòng `START_TOO_MANY_CUSPS` (nguồn `session`, `before_start`, có `t_perf`, `call` trống); `events.csv` chỉ có tiêu
  đề. Nâng giới hạn thì chạy được và dòng từ chối vẫn còn. Lần từ chối khi liên kết đã có io thì `t_io` = `io.now()`.
- `test_window_warns_about_many_reversals_and_refuses_above_the_limit`: giao diện offscreen. Cảnh báo ở dòng đường và
  thanh trạng thái, hộp "Không bắt đầu được", phiên giữ READY.

*T12 theo kịch bản* — `tests/test_cusp_acceptance.py`, 44 test (thêm 02/10/2026). Test kiểm:

- giới hạn N-D6 (b) đọc từ tệp ngưỡng khớp `score_run` ở mọi khóa, và khớp câu N-D6 (b) của NGUONG; tệp ngưỡng hỏng hay
  khóa lạ bị từ chối;
- thứ tự ưu tiên cờ/kịch bản; từ chối trước I/O với bo (dòng `START_TOO_MANY_CUSPS` nêu DO-1) và `cusp_rule` trong
  snapshot;
- `replace_scenario` giữ phiên khi lỗi; đổi xe không đọc lại tệp ngưỡng; phát lại bỏ qua thẻ;
- giao diện offscreen (`run_app`, `ui.lidar_app` với COM9 không kết nối); mã thoát 2;
- planner, mô phỏng và bộ bám không đọc thẻ; bộ sinh và bộ tệp `scenarios/nghiem_thu` khớp nguồn.

`tests/test_scenario_store.py` thêm 9 test cho trường `acceptance`.

*T14 và các nút xuất log* — `tests/test_sync_marks.py`, 26 test (tệp mới; gồm cả phần `rig.bench`, `ui.rig_app`), và
`tests/test_export_log_ui.py`, 4 test (tệp mới, sau review). Phần của cockpit:

- `test_main_window_marks_before_start_and_after_stop_but_never_while_driving`: dấu được trước Bắt đầu đỗ và sau khi xe
  dừng, không được khi xe đang chạy.
- `test_start_waits_until_the_flash_is_off` (sau review): Bắt đầu đỗ bị từ chối khi ô dấu còn sáng.
- `test_rows_carry_the_run_speed_factor_and_it_is_locked_while_driving` (sau review): cột `time_scale`; ô "tốc độ chạy"
  khóa khi xe đang chạy.
- `test_vehicle_io_rows_carry_the_io_clock_and_a_real_port_is_never_opened`: `t_io`, `io_clock` của liên kết; cổng thật
  không bao giờ bị mở.
- `test_export_writes_sync_file_only_when_marks_exist`: `<tên>_sync_marks.csv` chỉ được ghi khi đã có dấu.
- `tests/test_export_log_ui.py` (4 test): xuất giữa lần chạy chỉ bỏ gói phát lại (SIM và `VEHICLE_IO`); START bị từ chối
  hay lần "Xóa lỗi bo" của liên kết chưa chạy lần nào xuất được.

**Test thêm ngày 02/10/2026, đợt 2.** Cây gộp đợt 2; máy bàn, `.venv`, giao diện offscreen. Số test đếm bằng
`pytest --collect-only` ngày 02/10/2026 trên cây gộp; kết quả chạy trên bản commit ghi ở biên bản của lượt chạy toàn bộ,
không ghi ở đây. Chỉ dùng bo mô phỏng, LiDAR mô phỏng, bo ảo giả, cổng serial giả, trừ một test chạy QEMU thật. Không
test nào mở cổng, camera hay LiDAR thật.

*Bo ảo QEMU trong phiên đỗ.* Mọi test dưới đây, trừ test cuối, chạy với bo ảo giả: `FirmwareModel` (bản tham chiếu
byte-đúng của firmware trong QEMU), `ManualClock`, một client.

- `tests/test_qemu_plant.py` (24: 23 lúc viết mã, 1 thêm sau review): cấu hình, URL, khung trước khi đặt xe; xe bám tham
  chiếu và giữ cờ, xe dừng khi hết lệnh; boot_id lạ; luật ghép; phiên COMPLETED qua bo ảo giả và START lần hai; từ chối
  khi bo chưa chạy hay không mở được socket; LOOP_OVERRUN → Xóa lỗi bo → START; quan sát 0 COMMAND; đóng giữa lần chạy
  gửi enable=0 rồi DISARM; xuất gói và phát lại KHỚP; cổng COM không đổi.
  - Sau review, `test_explicit_qemu_io_link_is_labelled_and_closed_like_qemu_board`: liên kết dựng thẳng với
    `QemuPlantVehicleIO` (lớp bọc quanh `QemuPlantPose`) mang nhãn bo ảo. Lời từ chối LOOP_OVERRUN có gợi ý bo ảo và
    không để kết nối nào mở. "Xóa lỗi bo" báo "bo ảo QEMU socket://…". Lần chạy COMPLETED rồi socket đóng.
- `tests/test_qemu_plant_timing.py` (5, sửa theo review 02/10/2026): mỗi khung của một lần đọc theo tham chiếu của chính
  nó, thời điểm theo đồng hồ bo, kết thúc ở lúc nhận. Mở lại socket không tích phân khoảng socket đóng: "Xóa lỗi bo" sau
  10 phút nghỉ ≤ 50 bước 5 ms thay vì 120 010. Chu kỳ telemetry của `configs/bo_ao_qemu.json` 20..100 ms; 100 ms vẫn
  START được.
- `tests/test_qemu_runner.py` (15: 13 lúc viết mã, 2 thêm sau review):
  - thiếu công cụ thì báo lý do, không chạy QEMU; bo đang chạy là `current_board()`, `bo_ao.json` được ghi;
  - ảnh mới không build, ảnh cũ hay thiếu thì build; ảnh cũ mà không có PlatformIO bị từ chối; lỗi build giữ
    `build.log`;
  - lỗi khởi động giữ thư mục và lời; QEMU tự thoát → FAILED;
  - tắt và đóng cửa sổ xóa `flash.bin`, giữ log; lệnh tắt lúc đang khởi động; dọn `flash.bin` sót;
  - kết quả luồng nền về luồng giao diện; khóa build; `QemuBoard` dựng được mà không chạy QEMU;
  - sau review: "Tắt bo ảo", chọn bo khác hay đóng cửa sổ tới sau lúc QEMU vừa khởi động xong mà trước khi giao diện
    nhận kết quả, thì bo vẫn bị tắt và `bo_ao.json` ghi đúng lý do.
- `tests/test_qemu_board_ui.py` (10): ô chọn bo có bo ảo ở mục thứ hai, chọn không chạy gì; hàng bo ảo chỉ hiện khi
  chọn, khóa khi chạy; nút khởi động, gợi ý và nhãn cockpit nói rõ mô phỏng; máy thiếu công cụ thì khóa nút kèm lý do;
  lần chạy VehicleIO qua bo ảo giả COMPLETED và xuất log; hộp từ chối khi bo chưa chạy; chọn bo khác thì tắt bo ảo; đóng
  cửa sổ đóng phiên trước khi tắt bo ảo; "Kiểm kết nối bo" không hỏi xác nhận; "Xóa lỗi bo" không có hộp thoại ESP32.
- `tests/test_score_run.py::test_qemu_log_is_emulated_and_sim_truth_allowed_only_at_mp`: log bo ảo là log mô phỏng;
  `--sim-truth` chỉ ở cấp MP.
- `tests/test_firmware_qemu.py::test_parking_session_through_qemu_board`: chạy QEMU THẬT
  ([MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md) mục 1). Ngày 02/10/2026, lúc 15:13–15:14: đạt, 6,4 s, QEMU 1,01 lõi. Lúc
  18:14–18:15, sau các sửa theo review, tải CPU 7 % trước khi chạy: cả tệp 14 đạt, 16,9 s; test này 6,4 s, QEMU 0,97
  lõi.

**Ứng dụng với bo ảo QEMU thật, không người bấm** (02/10/2026, 18:58; [MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md) mục
1.1; biên bản: [CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 14).

- Cách chạy: script [`chay_bo_ao_ui.py`](evidence/bo_ao_ui_20261002/chay_bo_ao_ui.py) dựng `MainWindow` của `ui.app`
  (offscreen) từ cây gộp đợt 2. Script chọn nhánh VehicleIO và mục "Bo ảo QEMU", gọi "Khởi động bo ảo" (ảnh đã build
  sẵn: RUNNING sau 0,5 s), lập đường `scenarios/bai_do_xe.json`, "Bắt đầu đỗ" hai lần, để vòng 50 Hz của cửa sổ chạy,
  rồi đóng cửa sổ. Không ai bấm tay: các nút được gọi bằng mã (`qemu_runner.start()`, `plan(sync=True)`, `run()`).
- Kết quả ([ket_qua_bai_do_xe.json](evidence/bo_ao_ui_20261002/ket_qua_bai_do_xe.json)): 2/2 COMPLETED "Đỗ xong", ≈ 21 s
  thật mỗi lần, 0 lần START bị từ chối, 0 hộp thoại. Liên kết `is_qemu`, `virtual_board` = True, `hardware_actuators` =
  False, io `QemuPlantVehicleIO`, nguồn tư thế `qemu_plant_pose`, bằng chứng `qemu_firmware_simulated_vehicle`. Đóng cửa
  sổ → bo ảo STOPPED.
- Mức bằng chứng: bo ẢO (firmware thật trong QEMU) cộng xe MÔ PHỎNG phía laptop, chạy trên máy tính; không phải bo hay
  xe thật.

*Nguồn tư thế LiDAR (T2) và các sửa sau review.*

- `tests/test_session_lidar_pose.py` (11). Tệp dùng `LinkParams.for_lidar(0.25)` như giao diện.
  - Đỗ `VEHICLE_IO` với định vị LiDAR mô phỏng; Quan sát với LiDAR mô phỏng và người lái, 0 COMMAND.
  - Vật chỉ LiDAR thấy → `POSE_LOST`; LiDAR bị che → `POSE_LOST`; LiDAR im → `STALE_POSE` trong giới hạn; lệch giữa lần
    chạy → `POSE_DISAGREE`.
  - Phát lại lần chạy LiDAR khớp; băng cũ không có `status` vẫn phát lại; tuổi tư thế tối đa chỉ áp cho tư thế.
  - Bo serial với nguồn LiDAR sẵn sàng bị từ chối ở `VEHICLE_IO` trước mọi lần mở cổng; Quan sát mở cổng deferred một
    lần và tới `START_CHECK`.
  - Liên kết mô phỏng dựng nguồn LiDAR mới mỗi START, giữ nguồn trước khi bị từ chối.
  - Sau review, `test_step_0a_refusal_names_the_port_state_and_release_port_closes_it`: lời từ chối bước 0a nói "Cổng
    đang mở" khi liên kết giữ cổng; `release_port()` đóng cổng; lời sau đó là "Cổng chưa được mở".
- `tests/test_pose_prediction.py` (9, sau review): dự đoán tư thế thẳng, rẽ trái, lùi rẽ phải; kiểm tuổi thô (tuổi 0,26
  s vẫn `STALE_POSE`, mẫu không OK không dời); mặc định tắt, ghi trong `link.json`; `SimTruthPose` không dời; nguồn trễ
  0,10 s trong phiên được dời tới hiện tại; lần chạy LiDAR mô phỏng có dự đoán COMPLETED, ghi `pred_*`, phát lại khớp.
  "Kiểm kết nối bo" sau một START Quan sát bị từ chối ở `ui.lidar_app` đóng cổng liên kết giữ rồi kiểm được.
- `tests/test_bench_window_feed_and_close.py` (14, sau review):
  - vòng quét không phải của LiDAR thật không bao giờ qua cổng bo thật (4 trường hợp);
  - nhãn `evidence` theo nguồn đang gắn, lần chạy giữ nhãn của nó;
  - nguồn phát lại bị từ chối trước khi mở cổng, kể cả khi đủ điều kiện tiên quyết; bản ghi phát lại không bao giờ khởi
    động bo COM, kể cả ở Quan sát; `--session-replay` được ghi là phát lại;
  - đóng cửa sổ dừng xe trước khi chờ bản ghi cảm biến; đổi xe giữ nguồn điểm xuất phát;
  - meta của bản ghi cảm biến ghi đúng bo (sim, COM, qemu) và giới hạn đổi chiều có hiệu lực;
  - chọn thư mục không phải bản đồ thì báo; lỗi ghi không bị đổ cho hàng đợi đầy.
- `tests/test_vehicle_board_ui.py::test_window_probe_releases_the_port_the_link_holds_open` (sau review): "Kiểm kết nối
  bo" của cửa sổ. Trả lời No thì giữ cổng; Yes thì đóng cổng liên kết giữ, kiểm đạt, thanh trạng thái và báo cáo nói rõ.
- `tests/test_lidar_pose_source.py` (9), `tests/test_pose_source_ui.py` (6): nguồn tư thế LiDAR và ô "Nguồn tư thế"
  ([NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md)).

*Xe nghiệm thu.*

- `tests/test_vehicle_acceptance.py` (10): xe nghiệm thu chỉ khác xe mặc định ở tốc độ; tốc độ hành trình của planner
  không đổi; bo mô phỏng đi cùng chỉ khác ở tệp xe và tốc độ; giới hạn khớp; chọn tệp bo theo tệp xe và các đường lùi;
  liệt kê tệp xe; `Session.set_vehicle`; mục tiêu bị kẹp ở MP; hướng lệch bo/xe.
- `tests/test_vehicle_choice_ui.py` (5): `--vehicle-config`; cửa sổ ghép bo mô phỏng và chạy với xe nghiệm thu; đổi xe
  hủy đường và giữ khi mở kịch bản khác; ô khóa khi chạy và hỏi trước khi xóa log; xe nghiệm thu mà không có tệp bo khớp
  thì START bị từ chối.

### 7.1. Tiêm lỗi có kiểm soát (T6, thêm 02/10/2026)

T6 gây lỗi có chủ đích (camera đứng, tư thế đứng, laptop treo) rồi kiểm phản ứng của phần mềm. Nó chỉ ở mức mô phỏng. Mã
nằm ở [`autopark/safety/fault_injection.py`](../autopark/safety/fault_injection.py); mã sản phẩm không nhập mô-đun này,
và giao diện không có nút tiêm lỗi. Công cụ diễn tập `autopark.evaluation.fault_drill` chạy với bo mô phỏng, camera giả
hay bản ghi phát lại, không mở cổng COM, LiDAR hay camera. Lệnh chạy từ thư mục `autopark`:

```
.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.fault_drill hang --seconds 1 --phases 0 1 2 3 --out runs\fault_drill\<ngày> --name cb5b
.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.fault_drill pose --mode hold --repeat 10 --out runs\fault_drill\<ngày> --name cb6
.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.fault_drill camera --mode stall --repeat 10 --out runs\fault_drill\<ngày> --name cb2
```

Đầu ra và cách ghép log:

- Mỗi lần chạy ghi một thư mục `<out>/<name>_<kk>/` gồm `faults.csv`, `drill.json`, và với `pose`, `hang` thêm tám tệp
  log của liên kết. Cả đợt ghi `<out>/<name>.drill.json`. Thêm `--heartbeat` cho biến thể treo có Heartbeat.
- Mỗi lần gây lỗi và hết lỗi là một dòng `faults.csv`. Tệp có cùng cột với `events.csv`, thêm `t_rig` sau `t_io`, nên
  ghép được theo `t_io`.
- Lớp bọc tư thế mang tên nguồn `sim_truth_pose+fault`. `VehicleLink` bóc lớp bọc (`fault_inner`) để luật `SimTruthPose`
  vẫn áp dụng. Sau review 02/10/2026, việc bóc có giới hạn: tối đa 8 lớp (`unwrap_pose_source`), chỉ qua thuộc tính có
  thật của đối tượng hay của lớp, kể cả property, không qua `__getattr__`. Nhờ vậy Mock hay proxy không còn làm
  `VehicleLink.__init__` chạy mãi, và lớp bọc trỏ vòng thì báo `ValueError`.

Test: `tests/test_fault_injection.py`, 31 test (28 lúc viết mã, 3 thêm sau review), cộng
`tests/test_camera_dock_ui.py::test_frozen_camera_makes_the_ai_stale_then_required_ai_stops_the_run`. Môi trường: bo mô
phỏng, cổng serial giả với `ManualClock` hay theo đồng hồ tường, camera giả, bản ghi phát lại dựng trong test.

- *Log.* `test_fault_log_rows_share_the_events_csv_columns`: cột `faults.csv` = cột `events.csv` thêm `t_rig`; mọi dòng
  có `t_perf`, `call` trống.
- *Camera.* `test_repeat_on_a_usb_camera_is_caught_by_its_own_duplicate_check`,
  `test_repeat_on_other_sources_is_counted_as_a_duplicate_by_the_camera_worker`,
  `test_stall_ends_on_thaw_release_or_the_safety_cap`,
  `test_items_scheduled_during_a_stall_are_dropped_after_the_thaw_not_delivered_late` (sau review),
  `test_frozen_camera_is_stale_and_missing_after_half_a_second_and_the_other_keeps_its_rate[stall/repeat]`.
  - REPEAT bị đếm là khung cũ.
  - STALL hết khi thả, khi `release()` hay khi chạm trần an toàn.
  - Khung lẽ ra ra trong lúc đóng băng bị bỏ, không ra dồn với stamp cũ.
  - Hai camera giả 0,03 s: camera đóng băng thành "cũ" và vào `FrameSet.missing` sau 0,45–0,75 s; camera kia giữ nhịp;
    camera đóng băng quay lại ≤ 0,3 s sau khi thả.
- *Tư thế.* `test_pose_source_that_stops_updating_stops_the_run_with_stale_pose[hold/silent]`,
  `test_fault_wrapper_does_not_hide_the_sim_truth_pose_rule`.
  - `STALE_POSE` trong ≤ 0,175 s (HOLD) hay ≤ 0,025 s (SILENT), không enable nào sau lần dừng.
  - Lớp bọc (cả hai lớp) không che luật `SimTruthPose`; bọc `NoPoseSource` vẫn bị từ chối trước khi gửi byte nào.
- *Treo.* `test_sim_board_pause_host_keeps_bytes_unread_and_skips_the_stale_check`,
  `test_hang_without_heartbeat_on_the_sim_board_matches_the_serial_port[0,3 s/1 s × pha 0–3]`,
  `test_hang_with_heartbeat_keeps_the_link_and_only_the_command_times_out`,
  `test_hang_on_the_fake_serial_port_reads_nothing_while_hung[0,3 s/1 s]`,
  `test_hang_on_a_wall_clock_port_sleeps_with_and_without_the_heartbeat_thread[False/True]`,
  `test_hang_is_refused_outside_a_vehicle_io_run`.
  - Bo mô phỏng treo 0,3 s: bo ARMED (`COMMAND_TIMEOUT`), mã dừng đầu `VEHICLE_STOPPED`. Treo 1 s: bo DISARMED
    (`LINK_TIMEOUT`), mã dừng đầu `VEHICLE_NOT_ARMED`.
  - Ở cả 4 pha: không `TELEMETRY_STALE`, không lệnh nào trong lúc treo, không enable nào sau khi hết treo; cùng mã với
    cổng serial giả.
  - Có Heartbeat: ≥ 8 PING, bo chỉ `COMMAND_TIMEOUT`, mã dừng `VEHICLE_STOPPED`.
- *Công cụ diễn tập.* `test_judge_flags_each_missing_reaction`,
  `test_git_state_reads_the_repo_without_taking_the_index_lock` (sau review),
  `test_drill_pose_and_hang_write_logs_and_pass`,
  `test_drill_camera_on_fake_cameras_reports_when_the_camera_went_stale`,
  `test_drill_camera_stall_on_a_replay_loses_the_frozen_frames_like_a_real_camera` (sau review),
  `test_drill_exit_code_is_one_when_a_reaction_is_missing`. Hàm chấm báo từng phản ứng thiếu; thư mục mỗi lần chạy có đủ
  tám tệp log cộng `faults.csv`, `drill.json`; mã thoát 0/1/2.
- *Giao diện.* `test_frozen_camera_makes_the_ai_stale_then_required_ai_stops_the_run`: camera giả duy nhất thật sự ngừng
  trả khung. AI cũ sau ≈ 0,5 s, có một cảnh báo, xe vẫn chạy. Tích "AI bắt buộc" thì STOPPING
  ([AI_DIEU_KHIEN_XE.md](AI_DIEU_KHIEN_XE.md) mục 8.1).

**Phản ứng dự kiến**, theo docstring của `safety/fault_injection.py`, đo trên mô phỏng ngày 01–02/10/2026. Các giới hạn
ở đây là phép kiểm của công cụ, suy từ tham số hiện tại, KHÔNG phải ngưỡng nghiệm thu: N-T2, N-T4, N-P7 vẫn là đề xuất,
chưa chốt.

- **Camera STALL hoặc REPEAT.**
  - Bộ ảnh bỏ camera đó (`FrameSet.lagging`) sau khoảng L_p (60–63 ms).
  - `camera_stats` báo "cũ", và camera vào `FrameSet.missing` sau 0,5 s cộng tuổi khung tốt cuối. Camera khác giữ nhịp.
  - REPEAT được đếm là khung cũ; với USB, bộ dò của nguồn bắt được.
  - Lớp AI cũ: một cảnh báo mỗi lần chạy, hay dừng khi "AI bắt buộc". Vùng chỉ camera đó thấy thành UNKNOWN, không bao
    giờ FREE.
  - Không có `STALE_DATA`, vì `FreshnessMonitor` mới nối cho LiDAR.
- **Tư thế HOLD hoặc SILENT.** `STALE_POSE` trong ≤ 0,175 s (HOLD) hoặc ≤ 0,025 s (SILENT). Phiên vào STOPPING, gửi
  enable=0 mỗi 20 ms, rồi kết thúc STOPPED + DISARM + `WAIT_REPLAN`. Không enable nào sau đó; tư thế có lại không đổi
  gì.
- **Treo, không Heartbeat (phiên hiện nay).** Bo `COMMAND_TIMEOUT` → ARMED sau 0,15 s; `LINK_TIMEOUT` → DISARMED sau 0,5
  s im lặng. Laptop không thấy gì trong lúc treo nên không có `TELEMETRY_STALE`. Khi tỉnh dậy: `VEHICLE_STOPPED` nếu
  treo dưới 0,5 s, `VEHICLE_NOT_ARMED` nếu trên 0,5 s; gần 0,5 s thì tùy pha. Không enable nào sau đó.
- **Treo, có Heartbeat.** Bo chỉ `COMMAND_TIMEOUT`, telemetry vẫn mới; `VEHICLE_STOPPED` khi tỉnh dậy.

Mất telemetry khi laptop vẫn chạy (`TELEMETRY_STALE`, `STALE_TELEMETRY`) đã có `SimVehicleIO.set_link` và test riêng,
nên T6 không thêm cách tiêm lỗi cho trường hợp đó. Bằng chứng diễn tập trên bản commit (`drill.json` của các lần chạy)
chưa có trong `docs/evidence/`.

## 8. Chưa kiểm và giới hạn

Mục này gom những gì chưa thử, chưa đo hay còn hở. Mỗi gạch nói trạng thái hiện nay trước, diễn biến sau.

- **Chưa chạy với ESP32-S3 hay MN300.** `SerialVehicleIO` mới chỉ nối vào phiên qua cổng serial giả (mục 7), chưa từng
  qua cổng thật. Chưa nạp bo thật ([GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 12).
  - Firmware C++ đã biên dịch cho ESP32-S3 bằng PlatformIO ngày 29/09/2026; cùng ngày lõi `src/core` qua test host, 703
    check, 0 lệch.
  - Ngày 30/09/2026 firmware chạy trong bo ảo QEMU ở mức `VehicleIO`, chỉ là giả lập: `SerialVehicleIO` nói chuyện với
    nó qua `socket://` từ Python/pytest ([MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md)). Khi đó bo ảo chưa được thử qua
    phiên đỗ xe (`Session`/`VehicleLink`) hay giao diện.
  - Từ 02/10/2026 bo ảo chạy qua phiên đỗ và giao diện, với xe mô phỏng phía laptop: bo ảo giả trong test, một test với
    QEMU thật và một lần chạy ứng dụng với QEMU thật mà các nút được gọi bằng mã (mục 7). Vẫn chỉ là mô phỏng; ESP32-S3
    và MN300 chưa thử.
  - Trước bản sửa ngày 24/09/2026, nhánh này chạy phiên ở khoảng 0,4 lần thời gian thực, vì mỗi bước chờ timeout đọc 10
    ms. Vì vậy mọi log qua `SerialVehicleIO` có trước ngày đó (nếu có) không dùng được để đánh giá nhịp điều khiển.
- **Heartbeat song song.** Nếu chạy thêm luồng `Heartbeat` bên cạnh phiên, `poll(block=False)` của vòng điều khiển vẫn
  có thể phải chờ khóa của `VehicleIO` tối đa khoảng một timeout đọc (10 ms), trong lúc luồng nền đang đọc chặn. Phiên
  hiện không dùng `Heartbeat`; chưa đo trường hợp này.
- **Khoảng trống an toàn tìm thấy và đã sửa trong tối 24/09/2026** (chỉ trên mô phỏng; chi tiết và lịch sử ở
  [GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 12).
  - *Điều kiện:* vòng điều khiển treo lâu hơn hạn lệnh 0,15 s, trong khi một thứ khác vẫn đọc telemetry và PING
    (`Heartbeat`; trong test là một vòng giống `Heartbeat`, hoặc `SimVehicleIO.advance`). Khi đó bo về ARMED
    (`COMMAND_TIMEOUT`) mà telemetry vẫn mới, nên chốt `TELEMETRY_STALE` không bật.
  - *Lỗi trước bản sửa:* nếu bước 5 ms đầu tiên sau khi hết treo rơi vào nhịp điều khiển (pha 0), `Session` gửi MỘT
    COMMAND enable=1, đưa bo từ ARMED lên RUNNING lần nữa, trước khi lớp nối lấy `VEHICLE_STOPPED`. Lý do: sự kiện chỉ
    được gom trong `pump()`, chạy SAU nhịp điều khiển. Trên mô hình bo, nếu lệnh dừng tới sau 10/20/40 ms thì effort lên
    107/115/130 ‰; đó là số của mô hình, không phải số đo.
  - *Cách sửa:* hai lớp. `refresh()` chạy đầu mỗi bước, trước nhịp điều khiển; và `command()` không gửi khi còn sự kiện
    dừng chưa lấy (mục 3, mục 4 quy tắc 2). Hai `xfail` ở pha 0 nay đạt, và có 7 test bắt đột biến bỏ `refresh()` (mục
    7).
  - *Còn lại:* `refresh()` chỉ thấy khung đã tới laptop. Bo vừa về ARMED mà khung báo điều đó chưa tới (chu kỳ telemetry
    50 ms cộng trễ USB) thì laptop vẫn có thể gửi enable=1. Điều này suy ra từ mã, chưa có test. Phiên hiện không dùng
    `Heartbeat`; khi không có luồng nào đọc cổng lúc treo, 8 trường hợp trên cổng serial giả đều dừng và không có enable
    nào (`test_realtime_hang_without_heartbeat_never_resumes`). Với bo thật: chưa thử.
- **Nhịp 50 Hz phụ thuộc giao diện.** Với bo thật, nhịp 50 Hz phụ thuộc việc giao diện gọi `advance()` đủ dày (QTimer 16
  ms). Lúc bắt kịp sau một lần treo, phiên có thể chạy dồn tối đa 400 bước (2 s) trong một lần `advance()`.
  - *Giao diện treo lâu hơn hạn lệnh 0,15 s.* Lệnh hết hạn thì bo tự dốc về trung tính và về ARMED (`COMMAND_TIMEOUT`).
    Treo ngắn hơn watchdog liên lạc 0,5 s thì phiên dừng `VEHICLE_STOPPED`. Phiên không dùng `Heartbeat`, nên với bo
    thật không ai đọc cổng hay PING khi giao diện treo; 0,5 s không nhận thông điệp nào thì bo về DISARMED
    (`LINK_TIMEOUT`).
  - *Bằng chứng trên mô phỏng.* Bản 24/09/2026 ghi "đã kiểm" bằng
    `test_vehicle_io_command_timeout_after_freeze_never_resumes` (mục 7). Test đó vẫn đọc telemetry trong lúc treo, và
    lúc viết chỉ phủ một pha của nhịp điều khiển; ở pha 0 có khoảng trống, nay đã sửa (gạch trên).
  - *Treo không ai đọc cổng.* `test_realtime_hang_without_heartbeat_never_resumes` chạy 8 trường hợp trên cổng serial
    giả. Test chỉ kiểm ba điều: mã dừng đầu tiên là một trong `STALE_TELEMETRY`/`VEHICLE_STOPPED`/`VEHICLE_NOT_ARMED`,
    không enable nào tới bo, và cuối cùng bo DISARMED. Một script tạm tối 24/09/2026 (không lưu trong repo, dựng như
    test, máy bàn, `.venv`) cho kết quả cụ thể. Treo 0,3 s: bo ARMED, mã đầu tiên `VEHICLE_STOPPED` ở cả 4 pha. Treo 1
    s: bo DISARMED (`LINK_TIMEOUT`), mã đầu tiên `VEHICLE_NOT_ARMED` ở cả 4 pha, `VEHICLE_STOPPED` tới sau. Sát 0,5 s
    thì mã đầu tiên tùy pha: treo 0,52 s, pha 1 ra `VEHICLE_STOPPED`, pha 0/2/3 ra `VEHICLE_NOT_ARMED`. Vì vậy, sau một
    lần treo dài, log có `VEHICLE_NOT_ARMED` với lý do `LINK_TIMEOUT` là đúng dự kiến, không phải sai lệch. Với bo thật:
    chưa thử.
  - *Đo trên giao diện thật (02/10/2026).* Công cụ `python -X utf8 -m autopark.evaluation.ecoqos_gui do-chay` đo khoảng
    thật giữa hai nhịp điều khiển khi cửa sổ thường, thu nhỏ hay bị che, với SIM và bo mô phỏng
    ([CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 13). Đo cùng ngày, 18:43–18:57, máy bàn, cây gộp đợt 2, kịch bản
    `bai_do_xe.json`; 32/32 lần chạy xong (bằng chứng [tom_tat.txt](evidence/ecoqos_chay_02102026/tom_tat.txt)). Khoảng
    lớn nhất giữa hai nhịp điều khiển 50 Hz là 32 ms khi cửa sổ thường, 46–47 ms khi thu nhỏ, 32–33 ms khi bị che; không
    khoảng nào > 0,15 s; 24 lần chạy hợp lệ đều COMPLETED.
  - *EcoQoS.* Thu nhỏ cửa sổ với mặc định của Windows làm thời gian tính mỗi bước chậm 1,73 lần (SIM) và 1,76 lần
    (VehicleIO, bo mô phỏng) vì EcoQoS. Tắt EcoQoS, như ứng dụng tự làm từ 02/10/2026, thì hết chậm (1,00 / 0,96).
  - *Hệ quả cho bo theo đồng hồ tường* (bo thật, bo ảo QEMU): hạn COMMAND 0,15 s và watchdog 0,5 s (N-T10, đề xuất)
    không bị chạm trong các lần đo này. Đó chỉ là suy ra, chưa đo với bo theo đồng hồ tường. Lần chạy ứng dụng với bo ảo
    QEMU (mục 7) hoàn thành 2/2 với cửa sổ offscreen, không đo khoảng giữa hai nhịp.
- **Nguồn tư thế thật mới ở mức MP và trên bản ghi.** Từ 02/10/2026 (T2) phiên có nguồn tư thế LiDAR
  (`application/lidar_pose_source.py`) và bước mở cổng ở START (bước 0c, mục 3). Nguồn LiDAR mới kiểm ở mức MP (LiDAR mô
  phỏng) và trên bản ghi C1 đứng yên. LiDAR gá trên xe chạy và bo thật chưa thử. Yêu cầu "cùng đồng hồ" (mục 2) chưa
  kiểm được với bo thật. Bắt đầu đỗ ở VehicleIO với bo thật vẫn bị từ chối (`START_POSE_UNVERIFIED`) tới khi gá LiDAR
  được đo và đủ p04, DV-2, DV-1. Chi tiết: [NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md) mục 10.
  - *LiDAR mô phỏng chưa dùng được cho nghiệm thu MP.* Thử với xe nghiệm thu 0,10 m/s và 9 kịch bản
    `scenarios/nghiem_thu`, sau khi thêm dự đoán tư thế: DO-1, DO-2, DO-4a, DO-5, DO-6 hoàn thành; DO-3a, DO-3b, DO-3c,
    DO-4b dừng `POSE_LOST`, do định vị (a) AMBIGUOUS "second_peak" hai vòng liên tiếp. DO-4a chỉ còn 0,08 cm khe hở
    thật, và DO-4b chạm vật 20 ms sau khi dừng. Nguyên nhân: khe hở đường lập (0,71 / 0,80 cm) nhỏ hơn sai số định vị
    LiDAR mô phỏng (tới 2,3 cm). Trước khi có dự đoán, DO-4a va chạm 3/3. Số này từ script tạm của lượt sửa theo review
    02/10/2026, 3 lần mỗi kịch bản, không lưu trong repo; chỉ mô phỏng. Cách sửa đã đề xuất nhưng chưa làm.
  - *Diễn biến.* Ngày 24/09/2026 chỉ có `SimTruthPose` (định vị lý tưởng), chưa có định vị LiDAR. Vì vậy chọn cổng
    serial thật trong giao diện chỉ dùng được cho "Kiểm kết nối bo", còn Bắt đầu đỗ với bo thật luôn bị từ chối
    (`NoPoseSource`, mục 3 bước 0a, mục 6). Kế hoạch lúc đó: truyền nguồn tư thế thật vào
    `VehicleLink.serial_port(..., pose_source=...)`, và thêm bước mở cổng (`reopen()`) trong `begin_run`, vì liên kết
    tạo từ giao diện chưa bao giờ mở cổng; nếu không, START sẽ bị từ chối "Cổng chưa mở" (`START_NO_LINK`).
  - Ngày 25/09/2026 đã có định vị trên bản đồ tĩnh `lidar/localize.py` (commit `b100a5d`,
    [DINH_VI_LIDAR.md](DINH_VI_LIDAR.md)) và odometry khớp scan thử nghiệm `lidar/scan_odometry.py` (commit `a7cec5e`,
    [SO_SANH_DINH_VI_SLAM.md](SO_SANH_DINH_VI_SLAM.md)). Cả hai chạy offline trên bản ghi, chưa có tham chiếu độc lập,
    và chưa là `PoseSource` của `VehicleLink`.
  - Bước `reopen()` trong `begin_run` vẫn chưa có khi đọc mã ở HEAD `54cb3e2`, và khi đọc lại mã ở `ff4a018` ngày
    30/09/2026: `_open_run` chỉ gọi `connect()` khi chưa có phiên, nên cổng tạo bằng `SerialVehicleIO.deferred` mà chưa
    mở sẽ báo "Cổng chưa mở". Bước này có từ 02/10/2026 (bước 0c).
- **Giới hạn của kiểm tra giới hạn bo** (thêm muộn tối 24/09/2026).
  - Kiểm tra so với `VehicleConfig`, không so với đường đã lập. Bo cho góc lái nhỏ hơn `max_steer` là bị từ chối, kể cả
    khi đường cụ thể không dùng tới góc đó.
  - Không so `max_validity_ms` và `link_timeout_ms`, vì không có trường tương ứng. Không so trần effort, vì bo không báo
    trần này trong HELLO_ACK.
  - Cấu hình bo mô phỏng mặc định của giao diện (`configs/vehicle_io_sim.json`) khớp `vehicle_default.json`. Đổi cấu
    hình xe mà không đổi mục `firmware` của tệp bo thì START ở `VEHICLE_IO` với bo mô phỏng cũng bị từ chối (hoặc cảnh
    báo). Đây là hành vi mong muốn, vì hai bên lệch nhau.
  - Từ 02/10/2026 giao diện ghép bo mô phỏng theo tệp xe: dùng tệp `configs/vehicle_io_sim*.json` có `vehicle_config`
    trỏ đúng tệp xe. Muốn đổi xe thì tạo kèm bản sao bo, như `vehicle_io_sim_nghiem_thu.json` cho
    `vehicle_nghiem_thu.json`. Không có tệp khớp thì giao diện dùng `vehicle_io_sim.json`, và START vẫn bị từ chối hay
    cảnh báo như trên.
  - Bo ảo QEMU và ESP32-S3 không có bản sao như vậy: firmware biên dịch cứng 300 mm/s, nên xe nghiệm thu bị từ chối ở
    `VEHICLE_IO`. Bản firmware 100 mm/s chưa làm.
  - Chỉ kiểm với `FirmwareModel`. Giới hạn thật của ESP32-S3 chưa chốt.
- **"Kiểm kết nối bo" chưa thử với bo thật** (thêm muộn tối 24/09/2026). Chưa biết mở cổng có làm ESP32-S3 khởi động lại
  qua DTR/RTS hay không; cần tra theo bo. Nếu có, HELLO_ACK sẽ báo BOOT và lý do reset. Chọn nhầm cổng LiDAR (cổng
  `lidar_port` trong `configs/thiet_bi.json`; COM3 trên máy bàn từ 29/09/2026) thì HELLO sẽ được gửi tới RPLIDAR C1 ở
  115200 baud. Hộp thoại xác nhận chỉ nhắc người dùng, không chặn. Chưa kiểm LiDAR phản ứng thế nào với byte đó. Từ
  02/10/2026 (T2), trong `ui.lidar_app`, ở nhánh VehicleIO và Quan sát, cổng đang ghi ở ô cổng của ngăn LiDAR không được
  nhận làm cổng bo (hộp thoại từ chối, mục 4). Riêng nút "Kiểm kết nối bo" thì vẫn chỉ có hộp thoại xác nhận nhắc người
  dùng.
- **ToF chưa vào phiên** (thêm muộn tối 24/09/2026). `tof_to_near_field` và `NearFieldLayer.add_telemetry` đã có
  ([GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 12), nhưng `VehicleLink` và `Session` chưa đưa ToF vào hợp nhất hay kiểm va
  chạm. Vị trí gá trong `configs/tof_mounts_v0.json` là giả định, chưa đo.
  - Luật hợp lệ của lớp gần xe được sửa muộn tối 24/09/2026 theo rà soát, trước khi ToF vào phiên. Luật cũ "lớp gần xe
    hợp lệ khi MỌI ToF hợp lệ" làm một ToF không thấy gì (bit mặt nạ 0) xóa cung OCCUPIED của các ToF khác khi hợp nhất.
  - Luật mới: với khung telemetry, lớp hợp lệ theo stamp của khung. ToF không dùng được chỉ mất cung của nó và được ghi
    ở `invalid_sensors`. Số đo ≥ tầm tối đa có bit hợp lệ là hợp lệ, không đánh dấu ô nào.
  - Giao thức v1 chưa phân biệt "không có vật trong tầm" với "ToF hỏng"; cả hai là bit 0. ToF chết vì thế trông như
    khoảng trống. Điều này chỉ chấp nhận được vì lớp này không bao giờ đánh dấu FREE. Mặt nạ sức khỏe riêng là đề xuất,
    chưa chốt ([GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 12).
- **Chưa có mã đọc encoder và AS5600.** Bo không báo tốc độ hoặc góc lái thì START bị từ chối. Chưa có chế độ ước lượng
  tốc độ từ định vị.
- **Cách đấu dây ở chế độ quan sát** (ESC nối máy thu RC hay nối ESP32) chưa chốt. `SimHumanDriver` giả định ESC và
  servo theo tay điều khiển RC.
- **Chờ trên luồng giao diện.** `begin_run` với bo thật chặn luồng giao diện trong lúc `connect`, chờ BOOT và chờ 3
  khung telemetry, tối đa vài giây. `end_run` và `close` chờ ACK của DISARM tối đa 0,2 s. Với bo mô phỏng, các lần chờ
  này tiến đồng hồ mô phỏng của bo, nên sau khi kết thúc, bo có thể đi trước đồng hồ phiên ≤ 0,2 s.
- **Va chạm chỉ là kiểm hình học** với vật cản đã biết. Thế giới gương không có cảm biến va chạm.
- **Phát lại lần chạy qua `VehicleIO`** có từ 02/10/2026 (T9, mục 5.1), ở mức MP: bo mô phỏng và cổng serial giả. Bo
  thật chưa thử, và START với bo thật vẫn bị từ chối. Phát lại log chứng minh "cùng đầu vào + mã → cùng quyết định",
  không tái hiện xe. Diễn biến: ngày 24/09/2026 `storage/run_store.replay_run` chưa biết khóa `vehicle_link` trong
  snapshot, nên lần chạy qua `VehicleIO` không replay được, và giao diện không xuất gói replay cho các lần chạy đó. Tối
  24/09/2026 việc này thành từ chối có chủ ý chứ không còn là thiếu sót im lặng: `export_run` và `replay_run` ném
  `ReplayNotSupported` với lời báo tiếng Việt, và `export_run` từ chối trước khi tạo thư mục (mục 5,
  `tests/test_run_store_vehicle.py`). Khi đó bằng chứng của lần chạy qua `VehicleIO` chỉ là log
  `VehicleLink.write_logs`.
- **Giới hạn của phát lại log** (T9, mục 5.1): không chạy lại bước START; khung bị lấy khỏi hàng đợi của `VehicleIO`
  ngoài lớp nối thì phát lại KHÁC; luồng `Heartbeat` song song (phiên chưa dùng) có thể làm `latest()` khác; với đồng hồ
  tường, quyết định sát ngưỡng có thể lật; sai số 1e-9 và 5 ms là đề xuất; log ghi trước T9 bị từ chối.
- **Giới hạn của dòng `session_stop`** (T13).
  - Lúc thêm (đợt 1) mới kiểm với bo mô phỏng và cổng serial giả. Sau đợt 2, bo ảo QEMU chạy qua `Session`: bo ảo giả
    trong test, có lần dừng giữa chừng và phát lại; QEMU thật chỉ ở các lần COMPLETED (mục 7). ESP32-S3 vẫn chưa thử qua
    `Session`.
  - Nhánh SIM không có `events.csv` nên không có `t_perf`. Muốn đổi thời gian của lần chạy SIM sang `perf_counter` thì
    dùng dòng `CLOCK` của tệp dấu đồng bộ (T14, mục 5).
  - Log không tự ghi. Đóng cửa sổ giữa lần chạy, hay mở lần chạy kế tiếp khi chưa "Xuất log CSV…", thì mất các dòng của
    lần đó. Việc tự ghi chờ chốt nơi lưu biên bản.
  - `t_perf` của dòng sự kiện `VehicleIO` là lúc gom, không phải lúc bo phát. Đổi `t_io` sang `perf_counter` bằng
    `clock` chỉ đúng với bo chạy thời gian thực trên đồng hồ mặc định.
  - `fusion/demo.py` gọi `request_stop` mặc định (mất LiDAR, hết bản ghi). Nếu sau này demo chạy qua `VehicleIO` thì
    dòng sẽ thành `USER_STOP`/`user`; hiện demo chỉ chạy nhánh SIM nên không ghi gì.
- **Nút "Xóa lỗi bo" chưa thử với bo thật** (T15).
  - Mở cổng có thể làm ESP32-S3 khởi động lại qua DTR/RTS (chưa kiểm); khi đó FAULT mất vì bo khởi động lại chứ không vì
    CLEAR_FAULT. Để phân biệt: báo cáo và các cột `hello_*` của `board_actions.csv` có `boot_id` và lý do reset của
    HELLO_ACK, các khung có `t_bo`, và từ lần bấm thứ hai có sự kiện `FIRMWARE_RESET` khi `boot_id` đổi.
  - `board_actions.csv` xuất được cùng log của lần chạy qua `VehicleIO`, hoặc (sửa sau review) ngay khi liên kết đang
    chọn chưa chạy lần nào. Đổi nhánh chạy hay cổng thì liên kết bị thay và các dòng chưa xuất bị mất.
  - Chọn nhầm cổng LiDAR: chỉ một HELLO được gửi rồi hết giờ, như "Kiểm kết nối bo". Chặn duy nhất là hộp thoại xác
    nhận.
  - PING rào dùng hạn chờ ACK chung 0,5 s của `VehicleIO`, vì `ping()` chưa có tham số riêng. Vì vậy phần tồn đọng rất
    lớn trong cổng (lượt sửa lỗi ước từ khoảng 600 kB) cho NO_LINK. Bấm lại thì được, vì lần bấm trước đã đọc hết phần
    tồn đọng.
- **Giới hạn số lần đổi chiều** (T12). Mặc định tắt. Con số (N-D6 đề xuất ≤ 2 ở kịch bản rộng, ≤ 7 ở kịch bản hẹp) chưa
  chốt. Lúc viết T12 chưa có giới hạn theo từng kịch bản; cùng ngày 02/10/2026 đã có, qua trường `acceptance` của tệp sa
  bàn (mục 3). Chỉ `run_app.py` và `ui.lidar_app` áp dụng giới hạn này; phát lại và các công cụ khác bỏ qua thẻ. Bản mã
  cũ bỏ qua trường lạ và làm mất thẻ khi Lưu, nên laptop phải cùng commit. Kiểm đặt ở `Session.start_run`, nên bộ lập
  đường không đổi và vẫn có thể trả đường nhiều đổi chiều.
- **Dấu đồng bộ** (T14) mới kiểm offscreen.
  - Độ trễ từ lúc vẽ ô tới lúc ô sáng thật trên màn hình laptop chưa đo.
  - Dòng `CLOCK` ghép `perf_counter` với thời gian phiên trong một nhịp giao diện, ≈ 16 ms, tới 100 ms khi giao diện
    khựng.
  - Ở nhánh SIM và bo mô phỏng, thời gian phiên trôi so với đồng hồ thật, nên đổi sang `perf_counter` phải nội suy giữa
    hai dòng `CLOCK`. Một thử offscreen ngày 01/10/2026 cho ≈ 3,9 %. Ngày 02/10/2026 `ecoqos_gui do-chay` đo tỉ lệ này
    trên giao diện thật, và tách phần trôi do `QElapsedTimer.restart()` trả ms nguyên (cột `troi_lam_tron_pct`) khỏi
    phần mất do chặn 0,1 s (`mat_chan_s`). Kết quả (máy bàn, kịch bản `bai_do_xe.json`, SIM và bo mô phỏng): thời gian
    phiên / thời gian thật 0,969–0,977, tức trôi ≈ 2,5 % do làm tròn ms; mất do chặn 0,1 s bằng 0
    ([tom_tat.txt](evidence/ecoqos_chay_02102026/tom_tat.txt); [CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 13). Vẫn phải
    nội suy giữa hai dòng `CLOCK`.
- **Tái hiện laptop treo trên bo mô phỏng** (T6). `SimVehicleIO.pause_host()`/`resume_host()` tái hiện "laptop treo
  hẳn": byte của bo nằm trong bộ đệm, không kiểm `TELEMETRY_STALE`, và được đọc dồn khi hết treo (đóng dấu lúc đọc).
  Cách này cho cùng mã dừng đầu với cổng serial giả ở 0,3 s (`VEHICLE_STOPPED`) và 1 s (`VEHICLE_NOT_ARMED`), cả 4 pha.
  Bộ đệm phía laptop không giới hạn; giới hạn bộ đệm của cổng thật chưa đo.
- **Khoảng hở log khi xe đã đứng yên lúc sự kiện dừng tới** (T6), ví dụ sau khi treo ≥ 1 s.
  - Lần chạy kết thúc ngay trong bước đó. Nếu bước ấy không phải nhịp điều khiển thì không có lệnh dừng nào được ghi, và
    `end_run` gửi enable=0 + DISARM mà không ghi dòng nào. Vì vậy `commands.csv` có thể không có dòng STOP. Điều này suy
    từ mã; trong lượt diễn tập của người viết mã, 3/4 lần treo 1 s như vậy.
  - Mốc của lần dừng khi đó là dòng `session_stop` (T13) hay `t_io` của sự kiện.
  - Sau một lần treo trên bo mô phỏng, thời gian thế giới của phiên (`t_session` của `commands.csv` và của dòng
    `session_stop`) chậm hơn `t_session` = `t_io − t0` của dòng `stop`/`log` đúng bằng thời lượng treo. Hãy ghép các tệp
    theo `t_io`.
- **Dữ liệu đứng yên mà stamp vẫn mới** (T6), ví dụ định vị kẹt lặp tư thế với stamp mới, hay ảnh đứng mà không trùng
  từng byte: chưa có phản ứng an toàn nào, và T6 không có chế độ tiêm lỗi cho trường hợp này.
- **Bo ảo QEMU** (02/10/2026).
  - Firmware vẫn mạch hở, nên vòng PI, STALL, FEEDBACK_LOST không được thử. Tốc độ, góc lái, tư thế là số của xe mô
    phỏng, không phải số đo.
  - Bo ảo chạy theo thời gian thực nên không tất định; máy bận có thể làm firmware chốt LOOP_OVERRUN.
  - START mở socket, HELLO, đọc 3 khung và ARM trên luồng giao diện; ước lượng < 200 ms, chưa đo trong giao diện.
  - Chỉ mức MP. Giao diện với QEMU thật chưa ai dùng bằng tay: test giao diện dùng bo ảo giả, còn lần chạy ứng dụng với
    QEMU thật gọi các nút bằng mã (mục 7).
  - Với xe nghiệm thu, START ở `VEHICLE_IO` qua bo ảo bị từ chối (`LIMITS_MISMATCH`, firmware 300 mm/s; suy ra từ mã).
    Bản firmware 100 mm/s chưa làm.
- **Nguồn tư thế LiDAR và dự đoán tư thế** (T2, 02/10/2026). Mới kiểm ở mức MP và trên bản ghi C1 đứng yên; LiDAR gá
  trên xe chạy và bo thật chưa thử ([NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md) mục 10). Dự đoán tư thế dùng tốc độ,
  góc lái đo, nên với bo thật chỉ chạy khi firmware đo được (T8, chưa có). Cổng COM giữ mở giữa các lần chạy chỉ được
  kiểm với cổng serial giả; mở cổng có thể làm ESP32-S3 khởi động lại (DTR/RTS, chưa kiểm).
- Các ngưỡng ở mục 9 đều chưa chốt.

## 9. Tham số (`LinkParams`, chưa chốt)

Các tham số của lớp nối nằm trong `LinkParams`. Mọi giá trị dưới đây là mặc định hiện tại và chưa chốt.

| Tham số | Mặc định | Ý nghĩa |
|---|---|---|
| `max_state_age_s` | 0,15 s | Telemetry hay tư thế cũ hơn mức này thì dừng. Bằng `stale_after_s` của GĐ 0 và bằng 3 chu kỳ telemetry 50 ms |
| `standstill_mps` | 0,01 m/s | Ngưỡng "đứng yên" khi tham chiếu của bo = 0 (bằng `standstill_mm_s` của firmware) |
| `start_speed_tolerance_mps`, `start_samples` | 0,02 m/s, 3 khung | Kiểm xe đứng yên trước START |
| `start_position_tolerance_m`, `start_yaw_tolerance_rad` | 3 cm, 5° | Độ lệch cho phép so với điểm xuất phát đã lập đường |
| `stop_confirm_timeout_s` | 2,0 s | Chưa xác nhận đứng yên sau khoảng này thì FAULT `STOP_NOT_CONFIRMED` |
| `command_validity_s` | mặc định của `VehicleIO` (0,15 s) | Thời hạn mỗi COMMAND (bo kẹp ≤ 0,3 s) |
| `connect_timeout_s`, `ready_timeout_s`, `fresh_timeout_s`, `disarm_timeout_s` | 1,0 / 3,0 / 1,0 / 0,2 s | Thời gian chờ khi START và khi kết thúc |
| `max_pose_age_s` *(02/10/2026, T2)* | None (= `max_state_age_s`) | Tuổi tư thế tối đa riêng cho nguồn tư thế; nguồn LiDAR dùng 0,25 s |
| `predict_pose` *(sửa sau review 02/10/2026)* | False | Dời tư thế của mẫu OK tới `io.now()` trước khi vào bộ bám và thế giới gương |

Ghi chú cho hai tham số cuối:

- `max_pose_age_s`: giá trị 0,25 s cho nguồn LiDAR theo N-T2, là đề xuất, chưa chốt (đã quyết làm theo ngày 02/10/2026).
  `pose_age_limit_s` là giá trị đang dùng; telemetry vẫn theo `max_state_age_s`.
- `predict_pose`: tư thế được dời bằng tốc độ, góc lái đo (mô hình xe đạp); kiểm tuổi vẫn trên tuổi thô.
  `LinkParams.for_lidar(max_pose_age_s)` bật nó cùng tuổi tư thế 0,25 s cho nguồn LiDAR của giao diện.
