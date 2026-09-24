# Nối `VehicleIO` vào phiên đỗ xe và chế độ quan sát (24/09/2026)

**Kế hoạch đối chiếu:** [v3.1](../../KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) mục 9. Giai đoạn 5 yêu cầu `VehicleIO`
có nhánh mô phỏng và nhánh phần cứng. Giai đoạn 9 yêu cầu chế độ quan sát ("người lái, phần mềm tính đường/lệnh
nhưng không gửi chấp hành") và "trước START kiểm tra lại trạng thái thực". Mục 10 quy định mất liên lạc hay kết
nối lại không được tự chạy tiếp.

**Mức bằng chứng: CHỈ MÔ PHỎNG.** Chưa có ESP32-S3, MN300, encoder hay AS5600, và chưa có định vị LiDAR. Mọi
lần chạy trong tài liệu này đi qua chuỗi `Session` → `VehicleLink` → `SimVehicleIO` → byte giao thức →
`FirmwareModel` (bản tham chiếu Python của firmware) → cơ cấu chấp hành giả định → `SimVehicle`. Tư thế xe lấy
thẳng từ mô phỏng. Riêng các phép thử đồng hồ ở mục 7 dùng `SerialVehicleIO` với cổng serial GIẢ (đầu kia vẫn là
`FirmwareModel`). *(Cập nhật muộn hơn tối 24/09/2026: một số phép thử vòng điều khiển treo ở mục 7 cũng dùng cổng
serial GIẢ này.)* Không số nào dưới đây là số đo trên xe hay trên bo. Giao thức, firmware và `VehicleIO` xem ở
[GIAO_THUC_XE.md](GIAO_THUC_XE.md).

| Thành phần | File |
|---|---|
| Lớp nối, ba chế độ, thế giới gương, log | [`autopark/application/vehicle_link.py`](../autopark/application/vehicle_link.py) |
| Móc vào phiên (chọn nhánh, vòng điều khiển, dừng) | [`autopark/application/session.py`](../autopark/application/session.py) |
| Ô chọn nhánh chạy trong giao diện | [`autopark/ui/main_window.py`](../autopark/ui/main_window.py) (ngăn "Mô phỏng") |
| Test | [`tests/test_session_vehicle.py`](../tests/test_session_vehicle.py) |
| Cấu hình bo mô phỏng mà giao diện dùng | [`configs/vehicle_io_sim.json`](../configs/vehicle_io_sim.json) (toàn số GIẢ ĐỊNH) |

## 1. Ba chế độ

| Chế độ | Lệnh ra xe | Trạng thái đưa vào bộ bám quỹ đạo | Ai lái |
|---|---|---|---|
| `SIM` (mặc định) | không có xe; `SimWorld` chạy thẳng theo lệnh | `SimFeedback` (phản hồi giả của giai đoạn 0) | phần mềm, trong mô phỏng |
| `VEHICLE_IO` | mỗi nhịp điều khiển (50 Hz) một COMMAND enable có thời hạn (mặc định 0,15 s) qua `VehicleIO` | tốc độ và góc lái lấy từ telemetry; tư thế lấy từ nguồn tư thế | phần mềm, qua bo |
| `OBSERVE` (quan sát) | **không gửi COMMAND nào**, kể cả COMMAND enable=0; bo phải ở DISARMED | như `VEHICLE_IO` | người lái |

- **SIM giữ nguyên hành vi giai đoạn 0.** Không chọn gì thì `Session.vehicle_link` là `None`. Khi đó `world` là
  `SimWorld`, còn phản hồi giả, snapshot và replay như cũ. Test giai đoạn 0 chạy lại đều đạt (mục 7).
- Bộ bám `TrajectoryTracker` ra lệnh bằng m/s (có dấu) và rad. Đó cũng là đơn vị của API `VehicleIO`, nên lớp nối
  không đổi đơn vị. Đổi sang mm/s và mrad trên dây là việc của `speed_to_wire` / `steer_to_wire`. Test so từng
  lệnh bo nhận với số của bộ bám.
- Ở `VEHICLE_IO` và `OBSERVE`, `Session.world` là **thế giới gương** (`MirroredWorld`). Nó không tích phân lệnh.
  Mỗi bước 5 ms nó lấy trạng thái từ lớp nối rồi kiểm va chạm hình học với các vật cản đã biết trên sa bàn.
- Xem trước (preview) và lái tay luôn là mô phỏng giai đoạn 0, không đi qua `VehicleIO`.

## 2. Cái gì đo, cái gì mô phỏng

| Đại lượng | Nguồn trong mã | Trên xe thật (khi có) | Hiện nay |
|---|---|---|---|
| Tốc độ, góc lái | telemetry `VehicleIO` (`speed_mps`, `steer_rad`) | encoder, AS5600 qua ESP32-S3: **chưa có mã đọc** | cảm biến giả trong `SimVehicleIO`: trễ 20/10 ms, nhiễu σ 0,01 m/s / 0,3° (giả định) |
| Tư thế x, y, hướng | `PoseSource` tiêm vào lớp nối | định vị LiDAR: **chưa có** | `SimTruthPose`: tư thế **thật** của xe mô phỏng, tức định vị lý tưởng |
| "Xe đứng yên" | \|tốc độ đo\| ≤ 0,01 m/s **và** tham chiếu tốc độ của bo = 0, trên telemetry còn mới | như bên trái | ngưỡng CHƯA CHỐT (bằng `standstill_mm_s` của firmware) |
| Va chạm | hình học: tư thế ước lượng so với vật cản đã biết | không phải cảm biến va chạm | như bên trái |
| Người lái (chỉ `OBSERVE`) | tay điều khiển RC lái ESC/servo, không qua ESP32 | cách đấu dây ở chế độ quan sát **CHƯA CHỐT** | `SimHumanDriver`: xe mô phỏng theo lệnh của người lái; đầu ra của bo bị bỏ qua (và bằng 0) |

`PoseSource` phải đóng dấu thời gian theo **cùng đồng hồ** với `VehicleIO.now()`. Định vị LiDAR sau này phải đáp
ứng điều này trước khi thay `SimTruthPose`.

Mọi kết quả bám đường trong tài liệu này dùng định vị lý tưởng. Chúng không nói gì về sai số định vị thật.

## 3. Một lần chạy

**Trước START** (`VehicleLink.begin_run`, gọi từ `Session.start_run`). Nếu một điều sai, START bị từ chối
(`SessionError`), phiên giữ READY và bo **không** bị bỏ lại ở ARMED:

1. Chưa có phiên thì `connect()`. Chờ bo ra khỏi BOOT.
2. Chờ **3 khung telemetry mới, nhận sau lúc bấm START**. Khung cũ có trước một thao tác vừa làm (ARM,
   CLEAR_FAULT...) không được dùng để quyết định.
3. Kiểm: bo không FAULT, không nhấn E-stop, không BOOT. Ở `VEHICLE_IO`, bo không được đang RUNNING theo lệnh từ nơi
   khác. Phải có tốc độ và góc lái đo được. Trung bình tốc độ đo của 3 khung ≤ 0,02 m/s và tham chiếu tốc độ của
   bo = 0. Có tư thế mới (tuổi từ 0 tới 0,15 s; mẫu "ở tương lai" cũng bị từ chối). Tư thế cách điểm xuất phát
   đã lập đường ≤ 3 cm và ≤ 5°. Tư thế không chạm vật cản. Kết quả kiểm được ghi thành dòng `START_CHECK` (đạt:
   "Đạt: ...", từ chối: "TỪ CHỐI: ...").
4. `VEHICLE_IO`: `arm()`. Đây là thao tác cho phép mới, và nó gỡ chốt `TELEMETRY_STALE` của `VehicleIO`.
   `OBSERVE`: gửi DISARM (đây không phải lệnh chuyển động), rồi chờ một khung telemetry mới báo DISARMED và có góc
   lái đo được.
5. Sau ARM/DISARM (trên bo thật có thể mất vài trăm ms), lớp nối **đọc và kiểm lại tư thế** (mới, gần điểm xuất
   phát, không chạm vật cản). Lỗi ở bước 4–5, kể cả ngoại lệ bất kỳ từ nguồn tư thế, đều thành `SessionError`. Nếu
   đã gửi ARM (kể cả khi ACK hết giờ), lớp nối gửi DISARM trước khi báo lỗi, rồi ghi `START_ABORTED` (và
   `DISARM_FAILED` nếu DISARM không được xác nhận).

**Lần START bị từ chối không xóa bằng chứng của lần chạy trước.** `commands.csv`, `telemetry.csv`, `events.csv`,
kết quả và (ở nhánh mô phỏng của giao diện) bo mô phỏng của lần chạy trước giữ nguyên cho tới khi lần mới đã thật
sự mở (sau ARM ở `VEHICLE_IO`, sau khi nhận DISARMED ở `OBSERVE`, và sau bước 5). Các dòng trước START của lần bị
từ chối (`START_CHECK` "TỪ CHỐI...", `START_NO_LINK`, `START_ABORTED`, sự kiện cũ đã rút khỏi `VehicleIO`...) được
nối vào `start_refusals.csv`. Vì vậy `Session.log` và `run_link` luôn trỏ cùng một lần chạy. `START_CHECK` của lần
đạt nằm trong `events.csv` của chính lần đó.

**Mỗi nhịp điều khiển (20 ms):** lớp nối lấy trạng thái đo (`observe`). Dừng an toàn nếu:

- telemetry cũ hơn 0,15 s (`STALE_TELEMETRY`),
- thiếu tốc độ hoặc góc lái đo (`NO_MEASURED_STATE`),
- tư thế cũ hoặc thiếu (`STALE_POSE`).

Nếu không có lỗi nào ở trên, bộ bám tính lệnh:

- `VEHICLE_IO`: gửi COMMAND. Gửi lỗi thì dừng với mã `SEND_FAILED`.
- `OBSERVE`: chỉ ghi một dòng vào `commands.csv`.

**Sự kiện buộc dừng** (lấy mỗi bước, trước nhịp điều khiển):

*(Cập nhật muộn hơn tối 24/09/2026.)* Câu "trước nhịp điều khiển" chỉ đúng hoàn toàn từ bản sửa tối 24/09. Trước đó
lớp nối chỉ gom sự kiện của `VehicleIO` trong `pump()`, và `pump()` chạy SAU nhịp điều khiển của cùng bước. Vì vậy,
nếu telemetry đã tới trong lúc vòng điều khiển treo (có luồng khác đọc cổng) và bước đầu tiên khi hết treo rơi vào nhịp
điều khiển, lệnh enable của nhịp đó được gửi trước khi sự kiện được xử lý (khoảng trống ở mục 8). Nay, khi phiên đang chạy, `Session` gọi `VehicleLink.refresh()` ở đầu mỗi bước 5 ms. Hàm này
lấy telemetry và sự kiện ĐÃ tới (bo thật: `poll(block=False)`; bo mô phỏng: `take_new()`, không tiến bo mô phỏng),
rồi `Session` mới lấy sự kiện dừng, trước nhịp điều khiển.

- mọi sự kiện `STOP` của `VehicleIO`: `TELEMETRY_STALE`, `SESSION_LOST`, `VEHICLE_FAULT`, `FIRMWARE_RESET`,
  `LINK_ERROR`;
- ở `VEHICLE_IO`, thêm `COMMAND_REJECTED` và `VEHICLE_STOPPED` khi laptop chưa ra lệnh dừng;
- `VEHICLE_NOT_ARMED`: telemetry báo bo đã rời ARMED/RUNNING sau khi nhận lệnh của lần chạy này;
- `OBSERVE_NOT_DISARMED`: ở chế độ quan sát mà bo ARMED/RUNNING. Lớp nối gửi DISARM ngay.

**Dừng:** `STOPPING` gửi COMMAND enable=0 mỗi nhịp; bo dốc về trung tính.

- Kết thúc STOPPED khi có telemetry **mới** báo xe đứng yên.
- Nếu 2,0 s kể từ lệnh dừng vẫn chưa xác nhận được xe đứng yên (mất telemetry, hoặc xe vẫn chạy), phiên kết thúc
  **FAULT** với mã `STOP_NOT_CONFIRMED`. Lý do: không có số đo thì phần mềm không được coi là xe đã dừng.
- Ở `OBSERVE`, phần mềm không điều khiển xe nên kết thúc quan sát ngay, không chờ người lái dừng.

**Kết thúc lần chạy** (COMPLETED / STOPPED / FAULT, hoặc đặt lại khi đang chạy): `VEHICLE_IO` gửi enable=0 rồi
DISARM. `OBSERVE` không gửi gì.

## 4. Quy tắc an toàn

1. **Quan sát không bao giờ gửi COMMAND.** Lớp nối không gọi `send()` hay `stop()` ở chế độ này. Ra khỏi lớp nối
   chỉ có HELLO, DISARM và REQUEST do `VehicleIO` tự gửi. Nếu thấy bo ARMED/RUNNING hoặc cờ `CMD_ACTIVE`, lớp nối
   gửi DISARM và kết thúc quan sát.
2. **Đã dừng thì không chạy tiếp.** Sau sự kiện dừng đầu tiên, lần chạy chỉ gửi enable=0. Có thêm một chốt ở lớp
   nối (`_halted`) chặn lệnh enable kể cả khi `Session` gọi sai. Telemetry có lại không làm chạy tiếp.
   `connect()` lại cũng không: bo về DISARMED.
   *(Cập nhật muộn hơn tối 24/09/2026; trước bản sửa, câu "sau sự kiện dừng đầu tiên" có một ngoại lệ ở pha 0, mục 8.)*
   Cụ thể là sau sự kiện dừng đầu tiên **đã tới laptop**: đầu mỗi bước, trước nhịp điều khiển, lớp nối lấy mọi
   telemetry và sự kiện đã tới (`refresh()`), rồi `Session` chuyển sang dừng. `command()` không gửi enable (trả
   `HALTED`) khi `_halted` hoặc khi còn sự kiện dừng lớp nối đã gom mà `Session` chưa lấy. Sự kiện mà khung telemetry
   báo nó chưa tới laptop thì không chặn được (mục 8).
3. **Chỉ START mới ARM.** Sau dừng an toàn, đường bị hủy (`path_invalidated`). Người dùng phải đặt lại, lập lại
   đường từ chỗ xe đứng rồi bấm Bắt đầu đỗ. Lúc đó `begin_run` kiểm lại trạng thái thật rồi mới `arm()`. Bo đang
   FAULT (ví dụ E-stop) thì START bị từ chối tới khi có người gọi `clear_fault()`. Lớp nối không tự gọi hàm này.
4. **Bo thật chạy theo thời gian thực, và vòng điều khiển không đọc chặn.** Với `VehicleIO` không phải mô phỏng
   (`realtime`), `Session.advance()` không cộng thời gian giao diện và không tua nhanh: thời gian phiên lấy theo
   `io.now() - t0` (`VehicleLink.session_time_now()`). Mỗi bước 5 ms chỉ đọc byte đã có sẵn
   (`poll(block=False)`), không chờ timeout đọc của cổng. Nhờ vậy nhịp điều khiển 50 Hz, hạn xác nhận dừng 2 s,
   `MAX_RUN_TIME` và cột `t_session` của mọi tệp log cùng bám `io.now()`. Đồng hồ mặc định của `SerialVehicleIO` là
   `time.perf_counter()`: trên Windows `time.monotonic()` chỉ đổi mỗi 15,625 ms (đo bằng `time.get_clock_info` trên
   máy bàn, Python 3.12, 24/09/2026). Mới kiểm với cổng serial GIẢ, chưa kiểm với bo thật (mục 7, mục 8).
5. **Đóng phiên hoặc cửa sổ giữa lúc chạy `VEHICLE_IO`** gửi COMMAND enable=0 rồi DISARM trước khi đóng cổng
   (`Session.close()` → `VehicleLink.close()`). Đã kiểm trên `SimVehicleIO` + `FirmwareModel`: bo nhận enable=0 và
   về DISARMED trong 50 ms, trước khi hết hạn lệnh (0,15 s) hay watchdog liên lạc (0,5 s). CHƯA KIỂM trên bo thật.
6. **Lái tay sau một lần chạy qua `VehicleIO`** bỏ liên kết của lần chạy đó khỏi phiên (`run_link = None`). Nút
   "Xuất log CSV…"/"Lưu phiên…" khi ấy chỉ ghi log lái tay, không kèm thư mục `_vehicle_io` của lần chạy trước.
   Giao diện còn kiểm thêm một lớp: chỉ ghi `_vehicle_io` khi snapshot của log hiện tại có khóa `vehicle_link`.
7. Lớp nối không thay được đường cắt động lực phần cứng. Cờ STOP trên laptop không chứng minh xe thật dừng được
   ([GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 0, 12).

## 5. Log

`VehicleLink.write_logs(thư_mục)` ghi năm tệp. Trong giao diện, nút "Xuất log CSV…" ghi thêm thư mục
`<tên>_vehicle_io/` cạnh tệp CSV, chỉ khi log hiện tại là của một lần chạy qua `VehicleIO` (mục 4, quy tắc 6). Lần
chạy qua `VehicleIO` không xuất gói replay, vì `replay_run` chỉ phát lại được nhánh SIM. *(Cập nhật tối 24/09/2026:
`storage/run_store.export_run` nay từ chối rõ ràng lần chạy qua `VehicleIO` (`VEHICLE_IO` và `OBSERVE`) bằng
`ReplayNotSupported` (lớp con của `ValueError`, lời báo tiếng Việt chỉ sang `VehicleLink.write_logs`) trước khi tạo thư
mục nào; `replay_run` từ chối gói có khóa `vehicle_link` trong snapshot. Test:
[`tests/test_run_store_vehicle.py`](../tests/test_run_store_vehicle.py), 4 test, bo mô phỏng.)*

| Tệp | Nội dung |
|---|---|
| `commands.csv` | Mỗi nhịp điều khiển một dòng: `t_session`, `t_io`, `mode`, `kind` (TRACK/STOP), `sent` (1 = đã gửi tới bo, 0 = không gửi), `seq`; mục tiêu tốc độ/góc lái; trạng thái bộ bám (`phase`, `segment`, `index`, `distance_to_end_m`, `lateral_error_m`, `heading_error_deg`, `done`); trạng thái đo đã dùng (`obs_*`); tuổi telemetry; nguồn tư thế; `pose_simulated`; `note` |
| `telemetry.csv` | Mọi khung telemetry nhận được: thời gian (`t_session` âm = nhận trước START), trạng thái, lỗi, lý do dừng, cờ, tốc độ/góc đo (rỗng = không hợp lệ), tham chiếu, effort, `last_cmd_seq`, tuổi lệnh, điện áp, bộ đếm lỗi |
| `events.csv` | Sự kiện `VehicleIO` và của lớp nối trong lần chạy gần nhất đã mở (`START_CHECK` "Đạt...", `OBSERVE_DISARM`...), kèm cách xử lý: `stop`, `log`, `before_start`, `after_run` |
| `start_refusals.csv` | Cùng cột với `events.csv`. Các dòng trước START của **mọi** lần START bị từ chối của liên kết này (`START_CHECK` "TỪ CHỐI...", `START_NO_LINK`, `START_ABORTED`, `DISARM_FAILED`, sự kiện cũ rút khỏi `VehicleIO`). Luôn được tạo; có thể chỉ có dòng tiêu đề |
| `link.json` | Chế độ, loại `VehicleIO`, nguồn tư thế, cờ mô phỏng, tham số, cấu hình bo mô phỏng, kết quả, số lần chạy đã mở (`runs`), số lần START bị từ chối (`refused_starts`), `LinkStats` |

## 6. Giao diện

Ngăn "Mô phỏng" có ô **"Nhánh chạy khi bấm Bắt đầu đỗ"**. Mặc định là "Mô phỏng giai đoạn 0". Ô này chỉ đổi được
khi đang chỉnh hoặc sẵn sàng; từ lúc chạy tới lúc đặt lại thì bị khóa. Dưới ô có dòng giải thích cho từng nhánh.

- **VehicleIO → bo mô phỏng: GỬI lệnh.** Mỗi lần START, giao diện tạo một `SimVehicleIO` mới đặt ở điểm xuất
  phát, theo `configs/vehicle_io_sim.json`. Chỗ này mô phỏng việc người đặt xe vào vị trí.
- **Quan sát: tính lệnh, KHÔNG gửi.** Khi đang quan sát, phím ↑ ↓ ← → lái xe mô phỏng thay người lái, Space
  phanh, 0 trả lái, Esc kết thúc. Nhãn tiến độ hiện lệnh gợi ý "(không gửi)". Thẻ trạng thái đổi thành "Quan sát".
- Giao diện **chưa có** lựa chọn cổng serial tới bo thật. Khi có bo và có định vị, phải thêm lựa chọn này. Lúc đó
  truyền `VehicleLink(mode, SerialVehicleIO.open(...), pose_source=...)`.

## 7. Đã kiểm (chỉ mô phỏng và cổng serial giả, 24/09/2026, máy bàn, `.venv`)

`tests/test_session_vehicle.py`, 34 test (tính cả tham số hóa), đạt 34/34. Mọi test chạy trên `SimVehicleIO` +
`FirmwareModel`, trừ ba test đồng hồ dùng `SerialVehicleIO` với cổng serial GIẢ (`FirmwareSerialLoopback` với
`ManualClock`, hoặc một cổng giả theo đồng hồ tường ngay trong tệp test). Không test nào mở cổng thật.

*(Cập nhật muộn hơn tối 24/09/2026, máy bàn, `.venv`.)* Số 34/34 ở trên là trước khi thêm test tối 24/09. Nay tệp có
**60 test (tính cả tham số hóa), 60 đạt, 0 `xfail`**. Chạy lại riêng tệp này khi sửa tài liệu: 60 passed. Thêm 26
trường hợp (9 hàm test, bảng thứ hai dưới đây). Phần thêm trước bản sửa gồm mất số đo giữa lần chạy, thiếu góc lái lúc
START và treo vòng điều khiển (trong đó có hai `xfail` ở pha 0). Phần còn lại đi cùng bản sửa khoảng trống ở mục 8. Ngoài ba test đồng hồ, 12 trường hợp mới cũng dùng `SerialVehicleIO` với cổng serial GIẢ
(`FirmwareSerialLoopback` + `ManualClock`): `test_realtime_hang_without_heartbeat_never_resumes` (8) và
`test_resume_after_hang_keeps_effort_zero_whatever_the_gap_before_the_stop` (4). Vẫn không test nào mở cổng thật.

| Test | Kiểm |
|---|---|
| `test_sim_is_default_and_keeps_phase0_world` | Mặc định là SIM, `world` là `SimWorld`, snapshot không có khóa `vehicle_link`. Chọn SIM tường minh cho log giống hệt từng dòng |
| `test_sim_link_mode_is_rejected` | `VehicleLink` không nhận chế độ SIM |
| `test_vehicle_io_follows_planned_path_through_the_firmware_model` | Sa bàn `bai_do_xe.json` (có đổi chiều). Kết thúc COMPLETED, sai số < 3 cm / 3°, lệch khỏi quỹ đạo < 5 cm. Bo ARMED lúc START, DISARMED khi xong. Từng lệnh enable bo nhận (mm/s, mrad) bằng `speed_to_wire`/`steer_to_wire` của đúng lệnh bộ bám |
| `test_vehicle_io_stale_telemetry_stops_and_reconnect_never_resumes` | Rút cáp giả khi xe đang chạy. Dừng đầu tiên là `STALE_TELEMETRY` (≤ 0,18 s), có ghi thêm `TELEMETRY_STALE`. Kết thúc FAULT `STOP_NOT_CONFIRMED`. Xe trong bo giả tự dừng. Cắm lại rồi `connect()` lại: bo DISARMED, xe không nhúc nhích, không thêm lệnh enable nào. Chỉ sau khi lập lại đường và START mới chạy tiếp, và kết thúc COMPLETED |
| `test_vehicle_io_fault_stops_and_start_is_refused_until_cleared` | E-stop giả gây `VEHICLE_FAULT`, kết thúc STOPPED. Từ lúc laptop nhận báo lỗi, không lệnh enable nào tới bo. Thả E-stop thì bo vẫn FAULT. START bị từ chối ("FAULT") tới khi `clear_fault()`. Hai lần bị từ chối không đổi `commands.csv`/`telemetry.csv`/`events.csv`/kết quả của lần chạy E-stop, `Session.log` và `run_link` giữ nguyên; `start_refusals` có đúng một dòng `START_CHECK` "TỪ CHỐI" mỗi lần; `write_logs` ghi `start_refusals.csv` và `link.json` có `refused_starts`. Sau `clear_fault()`, START mở lần mới và chỉ lúc đó log cũ mới được thay |
| `test_refused_start_keeps_the_previous_simulated_board_and_logs` | Nhánh mô phỏng của giao diện: START bị từ chối (`START_NO_LINK`) giữ nguyên bo mô phỏng, bộ đếm lệnh, log và kết quả COMPLETED của lần trước. START đạt sau đó mới đóng và thay bo mô phỏng cũ |
| `test_start_is_refused_when_the_real_state_disagrees` | Xe lệch 10 cm so với xuất phát: từ chối, bo không bị ARM. E-stop đang nhấn: từ chối |
| `test_start_refused_heading_off` | Lệch hướng 10° (vị trí đúng): từ chối, bo DISARMED, `runs == 0` |
| `test_start_refused_vehicle_rolling` | Xe còn lăn 0,1 m/s (tư thế báo về vẫn ở điểm xuất phát): từ chối "chuyển động" |
| `test_observe_start_refused_while_board_still_references_speed` | Quan sát: xe đứng yên nhưng bo còn tham chiếu tốc độ ≠ 0: từ chối |
| `test_start_refused_board_already_running` | `VEHICLE_IO`: bo đang RUNNING theo lệnh từ nơi khác (tham chiếu 0): từ chối "RUNNING" |
| `test_start_refused_pose_not_fresh[0.5]`, `[-0.5]` | Tư thế cũ 0,5 s, và tư thế "ở tương lai" 0,5 s (đồng hồ lệch): từ chối |
| `test_start_refused_measured_pose_in_obstacle` | Tư thế đo chạm vật cản: `begin_run` từ chối "chạm vật cản", bo không bị ARM |
| `test_start_refused_without_measured_speed` | Bo không có encoder (`speed_available=False`): từ chối |
| `test_start_fault_refused_by_link_check` | Bo FAULT (E-stop đã thả): lớp nối tự từ chối, không dựa vào việc firmware từ chối ARM |
| `test_pose_lost_after_arm_disarms_and_refuses_start` | Nguồn tư thế có mẫu lúc kiểm, mất mẫu ngay sau ARM: `SessionError` (không phải `AttributeError`), phiên READY, lớp nối không chạy; bo nhận DISARM sau ARM (`HOST_DISARM`) và DISARMED sau 0,1 s, không nhờ watchdog 0,5 s; `start_refusals` = `START_CHECK`, `START_ABORTED` |
| `test_observe_refuses_when_frame_after_disarm_has_no_steer` | Quan sát: khung telemetry sau DISARM không có góc lái: từ chối, không gửi COMMAND |
| `test_stale_pose_source_stops_the_run` | Nguồn tư thế ngừng trả dữ liệu: `STALE_POSE`, kết thúc STOPPED, bo DISARMED |
| `test_vehicle_io_board_disarmed_elsewhere_stops_with_vehicle_not_armed` | DISARM từ nơi khác giữa lần chạy: dừng đầu tiên là `VEHICLE_NOT_ARMED`, không lệnh enable nào sau khi laptop biết |
| `test_vehicle_io_command_timeout_after_freeze_never_resumes` | Laptop "treo" 0,25 s (> hạn lệnh 0,15 s, < watchdog 0,5 s): dừng `VEHICLE_STOPPED` (`COMMAND_TIMEOUT`), không lệnh enable nào sau khi hết treo. *(Cập nhật tối 24/09/2026: test này đạt chỉ vì lúc treo tình cờ rơi vào pha 3; ép pha 0 thì trước bản sửa có một enable=1 tới bo, xem `test_vehicle_io_command_timeout_after_freeze_by_phase` ở bảng dưới và mục 8)* |
| `test_vehicle_io_command_rejected_stops_the_run` | Bo từ chối mọi COMMAND: dừng `COMMAND_REJECTED` |
| `test_drive_mode_cannot_change_while_running` | Không đổi được nhánh khi đang chạy |
| `test_close_while_running_vehicle_io_stops_then_disarms` | `Session.close()` giữa lúc chạy: lệnh cuối bo nhận là enable=0, bo DISARMED sau 50 ms |
| `test_manual_after_vehicle_io_run_drops_old_link` | Lái tay sau lần chạy `VEHICLE_IO`: `run_link` là None; liên kết đang chọn không bị đóng, START sau đó vẫn chạy |
| `test_realtime_link_session_clock_follows_io_clock_without_blocking_reads` | `SerialVehicleIO` + cổng giả `ManualClock`: mỗi 100 ms của bo, `advance(0,016)` đưa thời gian phiên tới `io.now() - t0` (sai ≤ 5 ms; `real_dt` và hệ số tua 4 không có tác dụng), không lần đọc cổng rỗng nào, 45–55 lệnh trong 1 s đồng hồ io |
| `test_realtime_serial_link_does_not_block_the_ui_tick` | Cổng giả theo đồng hồ tường (đọc rỗng chờ 10 ms như pyserial), vòng giao diện 16 ms trong 1 s: thời gian phiên luôn nằm giữa đồng hồ io đầu và cuối `advance()` (trừ ≤ 5 ms), không lần đọc chờ nào, `advance()` trung bình < 12 ms, 45–55 lệnh/s |
| `test_serial_default_clock_is_fine_grained` | Đồng hồ mặc định của `SerialVehicleIO` cho > 50 giá trị khác nhau trong 50 ms (không phải bước 15,625 ms) |
| `test_observe_logs_commands_and_never_enables_the_board` | Người lái mô phỏng làm theo lệnh gợi ý và đỗ xong (COMPLETED). Sau mỗi bước 20 ms bo vẫn DISARMED, effort 0, không có lệnh đang hiệu lực. Bo **không nhận một COMMAND nào**, `commands_sent == 0`. Hơn 200 dòng `commands.csv` có `sent=0` và tốc độ mục tiêu > 0,1 m/s. `telemetry.csv` từ START trở đi toàn DISARMED, effort 0. `start_refusals.csv` có, rỗng |
| `test_observe_disarms_a_board_found_armed` | Bo đang ARMED lúc START: lớp nối DISARM trước khi quan sát. Giữa lúc quan sát có chương trình khác ARM và gửi lệnh: phát hiện `OBSERVE_NOT_DISARMED`; REQUEST duy nhất bo nhận sau đó là DISARM của lớp nối, và ngay lúc kết thúc bo đã DISARMED với lý do `HOST_DISARM` (không phải watchdog 0,5 s) |
| `test_observe_stop_ends_without_waiting_for_the_driver` | Dừng quan sát thì kết thúc ngay dù người lái vẫn chạy. Test căn cho bước STOPPING đầu tiên rơi vào nhịp điều khiển, nên đi qua nhịp dừng (`command_stop`): có dòng STOP `sent=0`, bo không nhận COMMAND nào kể cả enable=0 |
| `test_window_drive_mode_selector` | Giao diện offscreen. Có 3 lựa chọn, mặc định SIM. Quan sát: ô bị khóa khi chạy, phím ↑ chạy xe mô phỏng, bo DISARMED, không gửi lệnh, nhãn "không gửi", xuất log có `commands.csv` và `start_refusals.csv`. VehicleIO: đỗ xong. Đổi về SIM được |
| `test_window_manual_export_after_vehicle_io_run_has_no_old_link_logs` | Giao diện: lái tay sau lần chạy `VEHICLE_IO` rồi "Xuất log CSV…": có `m.csv`, không có `m_vehicle_io/`. Gán lại liên kết cũ vào phiên rồi xuất lần nữa vẫn không có `_vehicle_io` (lớp kiểm snapshot của giao diện) |
| `test_window_close_while_running_vehicle_io_disarms` | Giao diện: đóng cửa sổ giữa lúc tự đỗ `VEHICLE_IO`: lệnh cuối bo nhận là enable=0, bo DISARMED sau 50 ms |

Test thêm tối 24/09/2026 (26 trường hợp; vẫn chỉ bo mô phỏng hoặc cổng serial GIẢ):

| Test | Kiểm |
|---|---|
| `test_measured_speed_lost_mid_run_stops_and_standstill_is_not_assumed` | Bo mô phỏng thôi báo tốc độ giữa lúc chạy: dừng đầu tiên là `NO_MEASURED_STATE`; không có tốc độ đo thì không xác nhận được đã đứng yên nên kết thúc FAULT `STOP_NOT_CONFIRMED`; đường bị hủy; sau lệnh dừng đầu tiên (+15 ms) không lệnh enable nào tới bo; xe mô phỏng đứng yên, bo DISARMED |
| `test_measured_steer_lost_mid_run_stops` | Bo thôi báo góc lái giữa lúc chạy: dừng `NO_MEASURED_STATE`, kết thúc STOPPED (tốc độ vẫn đo được), không enable nào sau lệnh dừng, bo DISARMED |
| `test_start_refused_without_measured_steer[VEHICLE_IO]`, `[OBSERVE]` | Bo không có góc lái đo (AS5600): START bị từ chối "góc lái" trước khi ARM (và trước DISARM của quan sát); 0 COMMAND; `start_refusals` có đúng một `START_CHECK` nhắc AS5600 |
| `test_command_timeout_while_heartbeat_keeps_link_stops_and_never_resumes[0]`…`[3]` | Vòng điều khiển treo 1 s trong khi một vòng giống `Heartbeat` vẫn đọc telemetry và PING (≥ 8 PING): bo về ARMED (`COMMAND_TIMEOUT`), không bị watchdog DISARM, telemetry vẫn mới, không `TELEMETRY_STALE`. Ở cả bốn pha: dừng đầu tiên `VEHICLE_STOPPED` (`COMMAND_TIMEOUT`), kết thúc STOPPED, không ARM lại, **không COMMAND enable=1 nào tới bo sau khi hết treo**. Pha 0 là `xfail(strict=True)` trước bản sửa (mục 8) |
| `test_realtime_hang_without_heartbeat_never_resumes[300/1000 ms × pha 0–3]` | Cổng serial giả, `ManualClock`, KHÔNG có luồng nào đọc cổng hay PING lúc treo (như phiên hiện nay): treo 0,3 s thì bo về ARMED, treo 1 s thì DISARMED. Hết treo, cả 8 trường hợp: dừng đầu tiên là `STALE_TELEMETRY`, `VEHICLE_STOPPED` hoặc `VEHICLE_NOT_ARMED`; kết thúc STOPPED; không enable nào tới bo; bo DISARMED (chạy lại tối 24/09/2026 trên mã hiện tại, script tạm, máy bàn: thực tế là `VEHICLE_STOPPED` khi treo 0,3 s, `VEHICLE_NOT_ARMED` khi treo 1 s, ở cả bốn pha; test chỉ kiểm tập ba mã) |
| `test_vehicle_io_command_timeout_after_freeze_by_phase[0]`…`[3]` | Như `test_vehicle_io_command_timeout_after_freeze_never_resumes` (treo 0,25 s bằng `SimVehicleIO.advance`, laptop vẫn đọc telemetry lúc treo) nhưng ép pha nhịp điều khiển: dừng `VEHICLE_STOPPED` (`COMMAND_TIMEOUT`), không enable=1 nào sau khi hết treo. Pha 0 là `xfail(strict=True)` trước bản sửa |
| `test_resume_after_hang_sends_no_enable_to_the_sim_board` | Bo mô phỏng, pha 0, treo 1 s với vòng giống `Heartbeat` (đồng hồ io đi trước thời gian phiên 0,9–1,1 s): sau khi hết treo, lệnh đầu tiên bo nhận là enable=0, không có enable=1, effort của bo luôn 0. Thay test ghi hành vi lỗi `test_resume_burst_commands_share_sim_clock_ms` |
| `test_resume_after_hang_keeps_effort_zero_whatever_the_gap_before_the_stop[0/10/20/40]` | Cổng serial giả, `ManualClock`, pha 0, treo 1 s trong khi một vòng đọc telemetry và PING; bo chạy thêm 0/10/20/40 ms trước lệnh dừng đầu tiên (thay cho thời gian tính + trễ USB trên máy thật): không enable=1 nào tới bo, effort 0 ở mọi khoảng. Trước bản sửa: một enable=1 tới trước, effort lên 0/107/115/130 ‰ (mô hình bo, đầu vào đứng yên, không phải số đo). Thay `test_resume_burst_effort_grows_with_gap_between_commands` |
| `test_command_refuses_enable_while_a_stop_event_is_pending` | Lớp chặn thứ hai: đặt một sự kiện dừng vào hàng chờ của lớp nối rồi gọi thẳng `command()`: trả `HALTED`, không COMMAND nào được gửi, dòng `commands.csv` có `sent=0` |

**Đột biến để kiểm test.** Đợt đầu (vá tạm trong tiến trình bằng monkeypatch; không sửa tệp nào). Sáu đột biến
đều bị ít nhất một test bắt:

1. Quan sát mà vẫn gửi lệnh.
2. Bỏ qua sự kiện dừng.
3. Bỏ kiểm tuổi telemetry và tư thế.
4. Bỏ kiểm trước START.
5. Không DISARM khi kết thúc.
6. Lúc dừng vẫn gửi lệnh chạy.

Đợt hai, 24/09/2026, sau khi sửa theo rà soát: sửa mã trên **bản sao** trong thư mục tạm (không đụng repo), mỗi
lần một đột biến, chạy lại cả tệp. 27 đột biến đều bị ít nhất một test bắt (bản gốc: 34/34 đạt):

7. Vòng điều khiển đọc cổng có chờ (`poll()` thay vì `poll(block=False)`).
8. Thời gian phiên cộng `real_dt` của giao diện thay vì theo đồng hồ io.
9. `SerialVehicleIO` bỏ qua `block=False`.
10. Đồng hồ mặc định của `SerialVehicleIO` về lại `time.monotonic()`.
11. `observe()` đọc đồng hồ trước khi lấy mẫu tư thế (mẫu vừa đóng dấu bị coi là "ở tương lai", STALE_POSE giả).
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

Đây là đột biến trên mã mô phỏng, chạy trong tiến trình; không nói gì về bo thật.

*(Cập nhật muộn hơn tối 24/09/2026.)* 27 đột biến của đợt hai được chạy với 34 test lúc đó, chưa chạy lại với 60 test
hiện nay. Riêng bản sửa khoảng trống ở mục 8 có hai đột biến. Cách làm: vá trong tiến trình bằng một plugin pytest đặt
ngoài repo, không sửa tệp nào; chạy lại khi viết tài liệu này, máy bàn, `.venv`.

28. Bỏ lời gọi `VehicleLink.refresh()` (lớp chặn thứ hai vẫn giữ): 7 test hỏng, 53 đạt. Bảy test đó là pha 0 của
    `test_command_timeout_while_heartbeat_keeps_link_stops_and_never_resumes` và
    `test_vehicle_io_command_timeout_after_freeze_by_phase`, `test_resume_after_hang_sends_no_enable_to_the_sim_board`,
    và bốn trường hợp của `test_resume_after_hang_keeps_effort_zero_whatever_the_gap_before_the_stop`.
29. Bỏ lớp chặn "còn sự kiện dừng chưa lấy" trong `command()`: chỉ `test_command_refuses_enable_while_a_stop_event_is_pending`
    hỏng, 59 đạt. Lớp này chỉ chặn sự kiện lớp nối ĐÃ gom. Việc chặn khoảng trống ở pha 0 là nhờ `refresh()`.

**Test hiện có chạy lại cùng lúc:** `test_phase0`, `test_session`, `test_session_run`, `test_runtime_safety`,
`test_ui_smoke`, bốn tệp `test_transport_*`, `test_background_work`, `test_fusion`, `test_fusion_demo`,
`test_lidar_dock_ui`, `test_vehicle_editing_ui`, `test_scenario_store`. Tính cả tệp mới: 361 đạt, 0 lỗi
(24/09/2026, sau đợt sửa theo rà soát). *(Cập nhật muộn hơn tối 24/09/2026: số 361 là từ trước khi thêm các test tối
24/09 và bản sửa khoảng trống; khi đó `tests/test_session_vehicle.py` có 34 test. Nay tệp này có 60 test, 60 đạt (chạy
lại riêng khi sửa tài liệu). Bộ test đầy đủ chạy lại cuối tối 24/09/2026 trên máy bàn, `.venv`: 895 đạt, 6 bỏ qua
(mô-đun cần torch), 215 s. Tổng cho đúng nhóm tệp trên thì chưa đếm lại.)*

**Đồng hồ khi chạy qua `SerialVehicleIO`** (script tạm ngày 24/09, không lưu trong repo; cổng serial GIẢ theo đồng
hồ tường, bo là `FirmwareModel`, xe đứng yên; vòng giao diện 16 ms trong 3 s; máy bàn):

| Mã | Thời gian phiên / đồng hồ io | Lệnh/s | `advance()` trung bình | Lần đọc chờ |
|---|---|---|---|---|
| Trước khi sửa (dựng lại trên bản sao) | 0,40 | 20 | ≈ 212 ms (mỗi bước chờ 10 ms) | 191 |
| Sau khi sửa | 1,00 | 50 | ≈ 1,1 ms | 0 |

Đây là cổng giả trên laptop, không phải ESP32-S3: nó chỉ chứng minh vòng điều khiển không chờ cổng và bám đồng
hồ io.

**Số của mô phỏng** (script tạm ngày 24/09, không lưu trong repo; xác định theo seed; bo mô phỏng lấy cấu hình từ
`configs/vehicle_io_sim.json`; sa bàn `bai_do_xe.json`, 2,55 m, 1 lần đổi chiều):

| Lần chạy | Kết quả |
|---|---|
| `VEHICLE_IO` | COMPLETED sau 20,95 s mô phỏng. Sai số cuối 0,60 cm / +1,15°. Lệch lớn nhất khỏi các điểm quỹ đạo 1,25 cm. 1.049 COMMAND. \|effort\| lớn nhất 454 ‰ (mô phỏng dùng trần 1000 ‰) |
| `OBSERVE`, người lái mô phỏng làm đúng lệnh gợi ý | COMPLETED sau 20,61 s. Sai số 0,73 cm / +1,27°. 0 COMMAND. effort luôn 0 |
| Rút cáp giả ở 0,10 m/s (đường thẳng 1,5 m) | Phát hiện `STALE_TELEMETRY` sau 120 ms. Xe mô phỏng dừng sau 0,43 s, trôi 4,1 cm. Phiên kết thúc FAULT `STOP_NOT_CONFIRMED` sau 2,1 s |
| E-stop giả ở 0,10 m/s | Laptop nhận `VEHICLE_FAULT` sau 15 ms. Xe mô phỏng dừng sau 0,18 s, trôi 0,9 cm. Phiên STOPPED sau 0,25 s |

Các số trên là của mô hình giả định (trễ, vùng chết, nhiễu, E-stop cắt động lực ngay), **không phải** quãng dừng
hay độ bám đường của MN300. Thời điểm phát hiện mất telemetry phụ thuộc pha của chu kỳ telemetry 50 ms. Với cấu
hình bo nhanh dùng trong test (`boot_hold_ms` 200), cùng phép thử cho 160 ms.

## 8. Chưa kiểm / giới hạn

- **Chưa chạy với ESP32-S3 hay MN300.** `SerialVehicleIO` mới chỉ nối vào phiên qua cổng serial GIẢ (mục 7), chưa
  từng qua cổng thật. Firmware C++ chưa biên dịch ([GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 12). Trước bản sửa ngày
  24/09/2026, nhánh này chạy phiên ở khoảng 0,4 lần thời gian thực (mỗi bước chờ timeout đọc 10 ms), nên mọi log
  qua `SerialVehicleIO` có trước ngày đó (nếu có) không dùng được để đánh giá nhịp điều khiển.
- Nếu chạy thêm luồng `Heartbeat` bên cạnh phiên, `poll(block=False)` của vòng điều khiển vẫn có thể phải chờ khóa
  của `VehicleIO` tối đa khoảng một timeout đọc (10 ms) trong lúc luồng nền đang đọc chặn. Phiên hiện không dùng
  `Heartbeat`; chưa đo trường hợp này.
- *(Thêm muộn hơn tối 24/09/2026.)* **Khoảng trống an toàn tìm thấy và đã sửa trong tối 24/09 (chỉ trên mô phỏng).**
  Điều kiện: vòng điều khiển treo lâu hơn hạn lệnh 0,15 s trong khi một thứ khác vẫn đọc telemetry và PING (`Heartbeat`;
  trong test là một vòng giống `Heartbeat`, hoặc `SimVehicleIO.advance`). Khi đó bo về ARMED (`COMMAND_TIMEOUT`) mà
  telemetry vẫn mới, nên chốt `TELEMETRY_STALE` không bật. Trước bản sửa, nếu bước 5 ms đầu tiên sau khi hết treo rơi
  vào nhịp điều khiển (pha 0), `Session` gửi MỘT COMMAND enable=1 (bo ARMED → RUNNING lần nữa) trước khi lớp nối lấy
  `VEHICLE_STOPPED`, vì sự kiện chỉ được gom trong `pump()`, chạy SAU nhịp điều khiển. Trên mô hình bo, nếu lệnh dừng tới
  sau 10/20/40 ms thì effort lên 107/115/130 ‰; đó là số của mô hình, không phải số đo. Sửa bằng hai lớp: `refresh()`
  đầu mỗi bước trước nhịp điều khiển, và `command()` không gửi khi còn sự kiện dừng chưa lấy (mục 3, mục 4 quy tắc 2).
  Hai `xfail` ở pha 0 nay đạt, và có 7 test bắt đột biến bỏ `refresh()` (mục 7). Chi tiết và lịch sử:
  [GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 12. Còn lại: `refresh()` chỉ thấy khung đã tới laptop. Bo vừa về ARMED mà khung
  báo điều đó chưa tới (chu kỳ telemetry 50 ms cộng trễ USB) thì laptop vẫn có thể gửi enable=1; điều này suy ra từ mã,
  chưa có test. Phiên hiện không dùng `Heartbeat`, và khi không có luồng nào đọc cổng lúc treo thì 8 trường hợp trên
  cổng serial giả đều dừng, không có enable nào (`test_realtime_hang_without_heartbeat_never_resumes`). Với bo thật:
  CHƯA THỬ.
- Với bo thật, nhịp 50 Hz phụ thuộc giao diện gọi `advance()` đủ dày (QTimer 16 ms). Giao diện bị treo lâu hơn hạn
  lệnh 0,15 s thì bo tự dốc về trung tính (`COMMAND_TIMEOUT`) và phiên dừng `VEHICLE_STOPPED` (đã kiểm trên mô
  phỏng, mục 7); lúc bắt kịp, phiên có thể chạy dồn tối đa 400 bước (2 s) trong một lần `advance()`. *(Cập nhật muộn
  hơn tối 24/09/2026: "đã kiểm" ở đây lúc viết chỉ là một pha của nhịp điều khiển; ở pha 0 có khoảng trống, nay đã sửa,
  xem gạch đầu dòng trên.)* *(Cập nhật muộn hơn tối 24/09/2026, lần 2: câu "bo tự dốc về trung tính (`COMMAND_TIMEOUT`)
  và phiên dừng `VEHICLE_STOPPED`" chỉ đúng khi treo ngắn hơn watchdog liên lạc 0,5 s. Test mục 7 mà câu đó dẫn
  (`test_vehicle_io_command_timeout_after_freeze_never_resumes`) vẫn đọc telemetry trong lúc treo. Phiên không dùng
  `Heartbeat`, nên với bo thật không ai đọc cổng hay PING khi giao diện treo. Lệnh hết hạn 0,15 s thì bo về ARMED
  (`COMMAND_TIMEOUT`); 0,5 s không nhận thông điệp nào thì bo về DISARMED (`LINK_TIMEOUT`).
  `test_realtime_hang_without_heartbeat_never_resumes` chạy 8 trường hợp trên cổng serial GIẢ. Test chỉ kiểm ba điều: mã
  dừng đầu tiên là một trong `STALE_TELEMETRY`/`VEHICLE_STOPPED`/`VEHICLE_NOT_ARMED`, không enable nào tới bo, và cuối
  cùng bo DISARMED. Một script tạm tối 24/09 (không lưu trong repo, dựng như test, máy bàn, `.venv`) cho kết quả sau.
  Treo 0,3 s: bo ARMED, mã đầu tiên `VEHICLE_STOPPED` ở cả 4 pha. Treo 1 s: bo DISARMED (`LINK_TIMEOUT`), mã đầu tiên
  `VEHICLE_NOT_ARMED` ở cả 4 pha, `VEHICLE_STOPPED` tới sau. Sát 0,5 s thì mã đầu tiên tùy pha: treo 0,52 s, pha 1 ra
  `VEHICLE_STOPPED`, pha 0/2/3 ra `VEHICLE_NOT_ARMED`. Vì vậy, sau một lần treo dài, log có `VEHICLE_NOT_ARMED` với lý
  do `LINK_TIMEOUT` là đúng dự kiến, không phải sai lệch. Với bo thật: CHƯA THỬ.)*
- **Chưa có nguồn tư thế thật.** `SimTruthPose` là định vị lý tưởng. Chưa có định vị LiDAR, và chưa kiểm được yêu
  cầu "cùng đồng hồ" với bo thật.
- **Chưa có mã đọc encoder và AS5600.** Bo không báo tốc độ hoặc góc lái thì START bị từ chối; chưa có chế độ ước
  lượng tốc độ từ định vị.
- Cách đấu dây ở chế độ quan sát (ESC nối máy thu RC hay nối ESP32) CHƯA CHỐT. `SimHumanDriver` giả định ESC và
  servo theo tay điều khiển RC.
- `begin_run` với bo thật chặn luồng giao diện trong lúc `connect`, chờ BOOT và chờ 3 khung telemetry (tối đa vài
  giây). `end_run` và `close` chờ ACK của DISARM tối đa 0,2 s. Với bo mô phỏng, các lần chờ này tiến đồng hồ mô
  phỏng của bo (sau khi kết thúc, bo có thể đi trước đồng hồ phiên ≤ 0,2 s).
- Va chạm chỉ là kiểm hình học với vật cản đã biết. Thế giới gương không có cảm biến va chạm.
- `storage/run_store.replay_run` chưa biết khóa `vehicle_link` trong snapshot, nên lần chạy qua `VehicleIO` không
  replay được. Giao diện không xuất gói replay cho các lần chạy đó. *(Cập nhật tối 24/09/2026: nay đây là từ chối có
  chủ ý, không còn là thiếu sót im lặng. `export_run` và `replay_run` ném `ReplayNotSupported` với lời báo tiếng Việt,
  và `export_run` từ chối trước khi tạo thư mục (mục 5, `tests/test_run_store_vehicle.py`). Bằng chứng của lần chạy qua
  `VehicleIO` là log `VehicleLink.write_logs`. Phát lại một lần chạy qua `VehicleIO` vẫn CHƯA CÓ.)*
- Các ngưỡng ở mục 9 đều CHƯA CHỐT.

## 9. Tham số (`LinkParams`, CHƯA CHỐT)

| Tham số | Mặc định | Ý nghĩa |
|---|---|---|
| `max_state_age_s` | 0,15 s | Telemetry hay tư thế cũ hơn mức này thì dừng. Bằng `stale_after_s` của giai đoạn 0 và bằng 3 chu kỳ telemetry 50 ms |
| `standstill_mps` | 0,01 m/s | Ngưỡng "đứng yên" khi tham chiếu của bo = 0 (bằng `standstill_mm_s` của firmware) |
| `start_speed_tolerance_mps`, `start_samples` | 0,02 m/s, 3 khung | Kiểm xe đứng yên trước START |
| `start_position_tolerance_m`, `start_yaw_tolerance_rad` | 3 cm, 5° | Độ lệch cho phép so với điểm xuất phát đã lập đường |
| `stop_confirm_timeout_s` | 2,0 s | Chưa xác nhận đứng yên sau khoảng này thì FAULT `STOP_NOT_CONFIRMED` |
| `command_validity_s` | mặc định của `VehicleIO` (0,15 s) | Thời hạn mỗi COMMAND (bo kẹp ≤ 0,3 s) |
| `connect_timeout_s`, `ready_timeout_s`, `fresh_timeout_s`, `disarm_timeout_s` | 1,0 / 3,0 / 1,0 / 0,2 s | Thời gian chờ khi START và khi kết thúc |
