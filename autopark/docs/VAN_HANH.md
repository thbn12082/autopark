# Vận hành và phát triển

Các lệnh dưới chạy từ thư mục `autopark/`. Luồng giao diện và hai cảnh mẫu ở [README](../../README.md).

## Cài đặt

Windows có `cai_dat.cmd`, `chay_app.cmd`; cài thủ công với Python 3.11 trở lên:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-phase0.lock
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
```

Gói cơ bản: PySide6, NumPy, Shapely. Extras `".[dev]"` cho pytest, `".[lidar]"` cho C1, `".[video]"` cho camera, `".[rig]"` cho bàn thử có AI. Nhánh AI dùng `.venv-train` qua `cai_dat_train.cmd`, cần checkpoint riêng; mô phỏng không cần PyTorch.

Đổi máy: tạo lại venv, mang dữ liệu ngoài Git theo manifest, kiểm `configs/thiet_bi.json` (COM/camera/QEMU). `do_may_moi.cmd` đo bàn thử; dùng `autopark.rig.may_moi --steps` để xem các bước. Ứng dụng tự tắt EcoQoS; `AUTOPARK_KEEP_ECOQOS=1` giữ chính sách Windows khi cần đối chiếu. Số máy bàn không thay kết quả laptop.

## Kịch bản

`schema_version: 1`; các trường chính là `name`, `bounds`, `start`, `goal`, `maneuver`. `vehicle_config` và `obstacles` có mặc định. Đường tệp xe tương đối với kịch bản. [Mẫu](../scenarios/thao_tac_cua_hep.json).

Nội bộ dùng m, s, rad; JSON dùng `yaw_deg`, `tolerance_cm`, `tolerance_deg`. `maneuver` có `max_goal_distance_m`, `area_half_extent_m`, `max_path_length_m` (hữu hạn >0) và `max_cusps` (nguyên ≥0). `maneuver: {}` nhận mặc định.

`Scenario(...)` trong Python tự có giới hạn. JSON thiếu/null `maneuver` cho `None` để nhận diện lịch sử. Parser vẫn hiểu `slot`; Session/planner từ chối kịch bản đó, kể cả khi thêm giới hạn. Đổi xe/đích/vật cản cần tính đường lại.

## Chế độ và cảm biến

| Chế độ | Lệnh tới bo | Trạng thái |
|---|---|---|
| SIM | Không | Mô hình và phản hồi giả |
| VEHICLE_IO | COMMAND có hạn | Telemetry + nguồn tư thế |
| OBSERVE | Không COMMAND, kể cả enable=0 | Người lái, bo DISARMED; phần mềm tính/ghi |

Xem trước vẫn mô phỏng. Bo Python, QEMU và COM là ba mức thử riêng. START kiểm đường, tư thế, phản hồi, đứng yên và giới hạn bo; [điều kiện thiết bị](PHAN_CUNG_VA_HIEU_CHUAN.md).

```powershell
.\.venv\Scripts\python.exe -m autopark.ui.lidar_app
.\.venv\Scripts\python.exe -m autopark.ui.lidar_app --pose-source lidar_sim --no-connect
.\.venv-train\Scripts\python.exe -m autopark.ui.lidar_app --camera-ai --cam-ports 1 2 3 4
```

LiDAR lấy cổng từ cấu hình; `--port COMx` ghi đè. `--recording` dùng scan đã ghi. AI có `--checkpoint`, `--calibration-dir`, `--extrinsics`, `--roi-dir`; xem `--help`.

## Ghi và phát lại

Gói runtime lưu kịch bản/xe/đường/log; `evaluation.replay` chạy lại quyết định. Gói lịch sử thiếu `maneuver` hoặc có `slot` bị `ReplayNotSupported` (CLI mã 2); vẫn đọc/chấm log được.

Bản ghi cảm biến là luồng riêng, vẫn phát lại bình thường. Ngăn **Ghi cảm biến** của `ui.lidar_app` ghi camera/scan cùng đồng hồ log; bắt đầu khi xe đứng yên. Liên kết ghi `events.csv` với mã/nguồn `session_stop`, tư thế, telemetry và đồng hồ.

```powershell
.\.venv-train\Scripts\python.exe -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 120 --name g01 --out runs/rig_bench --record runs/rig_recordings/g01
.\.venv\Scripts\python.exe -m autopark.ui.rig_app --replay runs/rig_recordings/g01 --no-ai
.\.venv-train\Scripts\python.exe -m autopark.ui.lidar_app --camera-ai --session-replay runs/session_recordings/PHIEN
```

Thay `PHIEN` bằng thư mục thật. `--session-replay` dùng một đồng hồ cho hai nguồn; `--cam-replay` và `--recording` mở riêng không bảo đảm cùng mốc. JPEG/tải máy có thể làm kết quả phát lại khác từng bit; giữ meta và số mẫu bỏ.

## Phát triển

Mã ở `autopark/`: `application` quản lý phiên; `planning/geometry/control/simulation` xử lý chuyển động; `lidar/perception/fusion/rig` xử lý cảm biến; `transport` nối firmware; `storage/evaluation/ui` lưu, chấm và giao diện.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_maneuver.py tests/test_maneuver_rollout_limits.py tests/test_runtime_safety.py
.\.venv\Scripts\python.exe -m autopark.evaluation.replay --help
.\.venv\Scripts\python.exe -m autopark.evaluation.score_run --help
```

Đóng góp bắt đầu từ ca tái hiện, sửa đúng phần và kiểm nhóm liên quan; test PyTorch/QEMU/thiết bị cần môi trường tương ứng. Giữ kết quả không đạt, không sửa dữ liệu gốc. [Cách đánh giá](KIEM_THU_VA_LO_TRINH.md).
