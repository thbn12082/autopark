# Tham gia phát triển AutoPark

Bạn có thể đóng góp ngay bằng máy tính, chưa cần xe hay cảm biến. Mục tiêu của buổi đầu là **mở được mô phỏng, tự tạo một sa bàn riêng, tìm đúng mã/test và chuẩn bị một thay đổi nhỏ để người khác xem lại**.

Trước khi làm, hoàn thành mục 1–4 trong [hướng dẫn cài đặt và chạy](autopark/README.md). Nếu gặp từ lạ, tra [thuật ngữ](autopark/docs/THUAT_NGU.md); nếu muốn biết các phần nối nhau thế nào, đọc phần 1–3 của [sơ đồ hệ thống](autopark/docs/SO_DO_HE_THONG.md).

## 1. Nhận biết đúng thư mục

```text
autopark/                       ← gốc kho Git
├── README.md                   ← giới thiệu và đường vào tài liệu
├── CONTRIBUTING.md             ← hướng dẫn này
├── TONG_HOP_DU_AN.md            ← tiến độ, việc đã có và còn thiếu
└── autopark/                   ← thư mục chạy Python, có pyproject.toml
    ├── autopark/               ← mã nguồn Python
    │   ├── domain/             ← kiểu dữ liệu: xe, tư thế, sa bàn
    │   ├── application/        ← điều phối phiên đỗ và liên kết bo
    │   ├── planning/           ← tìm đường
    │   ├── control/            ← bám đường
    │   ├── simulation/         ← xe và phản hồi mô phỏng
    │   ├── lidar/, video/      ← đọc, xử lý cảm biến
    │   ├── perception/, fusion/← AI, bản đồ, hợp nhất vật cản
    │   ├── transport/         ← giao thức và I/O với bo
    │   ├── storage/           ← nạp/lưu sa bàn và gói chạy
    │   ├── evaluation/        ← chấm, so sánh, phát lại, thử lỗi
    │   └── ui/                ← giao diện PySide6
    ├── configs/               ← thông số và cấu hình
    ├── scenarios/             ← sa bàn JSON dùng chung
    ├── tests/                 ← kiểm thử Python
    ├── docs/                  ← tài liệu kỹ thuật và bằng chứng
    ├── firmware/esp32_vehicle/← firmware C++
    └── runs/                  ← kết quả thử cá nhân, Git bỏ qua
```

Lệnh `git` có thể chạy từ trong kho. **Các lệnh Python ở hướng dẫn này chạy tại thư mục có `pyproject.toml`**. Nếu đang ở gốc Git:

```powershell
cd .\autopark
Test-Path .\pyproject.toml
.\.venv\Scripts\python.exe --version
```

Kết quả cần thấy là `True` và phiên bản Python. Dùng `python.exe` trong `.venv` để tránh chạy nhầm Python của máy khác; không cần Activate.

## 2. Tạo nhánh riêng trước khi sửa

Trước tiên kiểm tra thay đổi đang có:

```powershell
git status --short
```

Nếu lệnh không in tệp nào, cây làm việc đang sạch. Cập nhật `main`, rồi tạo nhánh cho việc mới:

```powershell
git switch main
git pull --ff-only
git switch -c docs/huong-dan-sa-ban
```

Nếu có tệp đã sửa, xác định chúng thuộc việc nào và lưu công việc đó trước khi cập nhật `main`; không đưa nhầm công việc của người khác vào commit. Nếu `pull --ff-only` báo hai nhánh đã phân kỳ, dừng cập nhật và so các commit với người phụ trách, không dùng lệnh ép ghi đè. Có thể xem bằng `git log --oneline --graph --decorate --all -n 20`.

Tên nhánh có thể là `fix/ten-loi`, `feat/ten-chuc-nang`, `docs/ten-tai-lieu` hoặc `test/ten-tinh-huong`.

Khi cần làm hai việc song song, có thể tạo một thư mục làm việc riêng. Lệnh sau chạy **tại gốc Git** và dùng một đường dẫn chưa tồn tại:

```powershell
git worktree add ..\autopark-thu-sa-ban -b feat/thu-sa-ban
```

Thư mục mới có mã của nhánh riêng; môi trường `.venv` và `runs/` của thư mục cũ không tự chuyển sang. Cài môi trường ở worktree mới theo [README chạy](autopark/README.md). Không cần dùng worktree cho thay đổi nhỏ thông thường.

## 3. Bài đầu tiên: tạo và chạy sa bàn của bạn

Bài này chỉ dùng SIM và dữ liệu trong kho. Mọi kết quả thử đặt trong `runs/`, nên chưa làm thay đổi sa bàn chung.

### Bước 1: tạo bản sao bằng hàm của dự án

Chạy tại thư mục có `pyproject.toml`:

```powershell
@'
from pathlib import Path
from autopark.storage.scenario_store import load_scenario, save_scenario

target = Path("runs/lam_quen/sa_ban_cua_toi.json")
if target.exists():
    raise SystemExit("Da co tep bai tap; dung ten khac hoac tiep tuc tep hien co.")

scenario = load_scenario("scenarios/sa_ban_3x2_hai_hop.json")
scenario.name = "sa_ban_cua_toi"
scenario.notes = "Bai lam quen: xe va kich thuoc deu la mo phong."
save_scenario(scenario, target)

loaded = load_scenario(target)
assert loaded.vehicle_config_path.is_file()
print("Da tao:", target)
print("Cau hinh xe:", loaded.vehicle_config)
'@ | .\.venv\Scripts\python.exe -X utf8 -
```

Kết quả cần có `runs\lam_quen\sa_ban_cua_toi.json` và dòng cấu hình xe `../../configs/vehicle_default.json`. Hàm `save_scenario` tự sửa đường dẫn khi chuyển sa bàn sang thư mục khác. Nếu chỉ sao chép JSON bằng tay, đường dẫn `../configs/...` cũ sẽ trỏ sai.

### Bước 2: hiểu các trường trước khi sửa

Mở tệp vừa tạo bằng trình soạn thảo. Đây là schema đang được `Scenario.from_dict` và `load_scenario` đọc:

| Trường | Nghĩa và đơn vị |
| --- | --- |
| `schema_version` | Hiện là `1`; phiên bản khác sẽ bị từ chối |
| `name`, `notes` | Tên sa bàn và mô tả mục đích |
| `vehicle_config` | Đường dẫn cấu hình xe, tương đối với chính tệp JSON |
| `bounds` | `xmin`, `ymin`, `xmax`, `ymax`: biên sa bàn theo mét |
| `start` | `x`, `y`: tâm trục sau theo mét; `yaw_deg`: hướng xe theo độ |
| `goal` | Tư thế đích; `tolerance_cm` theo cm, `tolerance_deg` theo độ |
| `obstacles` | Các hình chữ nhật: `id`, `cx`, `cy`, `width`, `height`, `yaw_deg` |
| `seed` | Số nguyên giúp tái hiện các thành phần ngẫu nhiên |

`id` vật cản phải khác nhau; `width` và `height` phải dương; các số phải hữu hạn. Một số sa bàn khác có `slot` và `mode`: khi có ô đỗ, chương trình tính lại đích từ ô và chế độ đỗ. Bài đầu tiên dùng tệp không có `slot` để dễ thấy tác dụng của việc đổi `goal`.

Trường `acceptance` chỉ dành cho sa bàn gắn kịch bản nghiệm thu. Chưa cần thêm trường đó trong bài học này; nó sẽ kéo theo quy tắc giới hạn đổi chiều riêng.

### Bước 3: chạy trước, rồi đổi đúng một chi tiết

Đảm bảo biến offscreen không còn trong shell mở ứng dụng:

```powershell
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -X utf8 run_app.py runs\lam_quen\sa_ban_cua_toi.json
```

Trong cửa sổ, chọn **SIM** rồi làm theo thứ tự:

1. Bấm **Tìm đường đỗ** và chờ trạng thái **Sẵn sàng**.
2. Bấm **Xem trước** để xem xe mô phỏng đi theo đường.
3. Bấm **Kết thúc xem trước** để trở về **Sẵn sàng**.
4. Bấm **Bắt đầu đỗ** và theo dõi lý do kết thúc.

Đọc lời giải thích nếu chương trình không tìm được đường. Việc cửa sổ mở đúng sa bàn và báo trạng thái rõ ràng là bước kiểm đầu tiên; tìm được đường còn phụ thuộc đầu bài và hạn tính toán.

Đóng ứng dụng, tăng `width` của `hop_1` từ `0.3` lên `0.4`, rồi mở lại bằng cùng lệnh. So sánh đường đi, số lần đổi chiều và kết quả. Nếu không có đường hợp lệ, giữ thông báo để giải thích thay vì nới dung sai chỉ để màn hình báo đạt.

Ở cuối bài, bạn nên trả lời được: xe đang tránh vật nào, đích đặt ở tâm trục sau hay tâm thân xe, và một lần chạy kết thúc vì tới đích hay vì dừng do lỗi.

### Bước 4: kiểm tra phần nạp/lưu và ghi lại phát hiện

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests\test_scenario_store.py -q
git status --short
```

Test cần có `passed`, không có `FAILED` hay `ERROR`. `runs/lam_quen/` không xuất hiện trong danh sách cần commit vì Git bỏ qua thư mục này. Test trên kiểm logic nạp/lưu; nó không tự chứng minh sa bàn mới đỗ được.

Một đóng góp đầu tiên có thể là sửa một bước hướng dẫn khó hiểu sau khi làm bài. Nếu tìm được lỗi phần mềm, giữ JSON tái hiện, mô tả hành vi mong đợi và thực tế; sau đó thêm test hồi quy phù hợp. Khi sa bàn mới đáng dùng chung, đặt bản đã kiểm vào `scenarios/` bằng `save_scenario` và ghi mục đích rõ ràng.

## 4. Chọn phần việc và test đúng chỗ

Các đường dẫn sau tính từ thư mục có `pyproject.toml`:

| Việc muốn làm | Mã cần đọc | Test nên bắt đầu |
| --- | --- | --- |
| JSON, cấu hình xe | `domain/types.py`, `storage/scenario_store.py` trong gói `autopark/` | `test_scenario_store.py`, `test_vehicle_acceptance.py` |
| Thân xe, biên và va chạm | `autopark/geometry/` | `test_geometry.py`, `test_fast_collision.py` |
| Thuật toán tìm đường | `autopark/planning/parking.py`, `portfolio.py` | `test_planning.py`, `test_portfolio_validation.py`, `test_planner_hard_cases.py` |
| Bám đường và xe mô phỏng | `autopark/control/tracker.py`, `simulation/` | `test_tracker.py`, `test_vehicle_model.py`, `test_phase0.py` |
| Trạng thái phiên, dừng | `autopark/application/session.py` | `test_session.py`, `test_session_run.py`, `test_runtime_safety.py` |
| Giao diện | `autopark/ui/` | `test_ui_smoke.py` và tệp `test_*_ui.py` của ngăn đang sửa |
| LiDAR và tư thế | `autopark/lidar/`, `application/lidar_pose_source.py` | `test_lidar_protocol.py`, `test_lidar_pose_estimator.py`, `test_session_lidar_pose.py` |
| AI thành vật cản | `autopark/fusion/camera_ai.py`, `perception/bev.py` | `test_camera_ai_layer.py`, `test_bev.py`, `test_camera_dock_ui.py` |
| Giao thức/bo | `autopark/transport/`, `firmware/esp32_vehicle/` | `test_transport_protocol.py`, `test_transport_firmware_model.py`, `test_session_vehicle.py` |
| Ghi/phát lại | `autopark/storage/run_store.py`, `rig/` | `test_run_store_vehicle.py`, `test_rig_replay.py`, `test_session_recording.py` |

Tìm tên thật trong mã bằng `rg`, ví dụ:

```powershell
rg -n 'def start_run|class SessionState' autopark\application\session.py
rg -n 'STALE_POSE' autopark tests
```

Theo cách tổ chức đang có: mã chung vào mô-đun tương ứng, test tên `test_*.py` ở `tests/`, dữ liệu thử tạo bằng `tmp_path` hoặc fixture nhỏ. Không đặt thao tác mở thiết bị thật ngay khi import một mô-đun. Tệp cấu hình dùng tên có nghĩa và giữ đơn vị rõ trong khóa; tài liệu tiếng Việt viết UTF-8.

## 5. Chạy kiểm tra và đọc kết quả

Ví dụ kiểm thay đổi hình học/sa bàn:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests\test_geometry.py tests\test_scenario_store.py -q
```

Với test giao diện, đặt offscreen **chỉ trong shell chạy test** và xóa ngay sau đó. `finally` bảo đảm biến được xóa kể cả khi lệnh gặp vấn đề:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
try {
    .\.venv\Scripts\python.exe -X utf8 -m pytest tests\test_ui_smoke.py -q
    $testExitCode = $LASTEXITCODE
} finally {
    Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
}
Write-Host "Ma thoat pytest: $testExitCode"
```

- `passed`: điều kiện test được thỏa mãn; mã thoát mong đợi là `0`.
- `failed`: hành vi không khớp điều kiện test; đọc tên test và assertion đầu tiên.
- `error`: lỗi chuẩn bị/chạy test, chẳng hạn thiếu thư viện.
- `skipped`: test không chạy. Cần đọc lý do, không tính như đã kiểm thành công.

Môi trường cơ bản có thể thiếu torch hoặc QEMU nên một số nhóm sẽ bỏ qua. Để xem lý do bỏ qua, thêm `-rs`. Nhóm `planner_budget` kiểm thời gian thực, không chạy dưới coverage tracing; tránh đo khi máy đang bận. Số test thay đổi theo mã và môi trường, không dùng một tổng số cũ làm mục tiêu.

Khi cần kiểm rộng hơn, dùng quy trình trong [README chạy](autopark/README.md). Nếu lưu báo cáo để review, đặt JUnit vào `runs/`, ví dụ thêm `--junitxml=runs/kiem_tra.xml`, đồng thời ghi mã thoát và đầu ra lỗi. Một báo cáo có nhiều test đạt chưa đủ nếu tiến trình bị crash khi thoát.

Với sửa tài liệu đơn giản, ưu tiên đọc thử các lệnh/đường dẫn liên quan và `git diff --check`; không cần tạo test chỉ để khẳng định văn bản tồn tại. Với sửa lỗi hành vi, test nên tái hiện tình huống gây lỗi và kiểm kết quả người dùng cần.

## 6. Giữ đúng ranh giới của hệ thống

Các quy tắc này ảnh hưởng trực tiếp đến việc xe có được phép chạy:

- `Session` điều phối phiên; giao diện không tự bỏ qua kiểm tra để gửi lệnh ra bo.
- Planner chỉ trả đường dùng được khi qua điều kiện nhận; đường ngoài dung sai không đổi nhãn thành thành công.
- `OBSERVE` tính và ghi lệnh đề xuất, không ARM/COMMAND. QEMU vẫn đi cùng xe mô phỏng.
- Dữ liệu cũ hoặc thiếu không được thay âm thầm bằng giá trị “có vẻ hợp lý”. Nguồn tư thế và số đo phải ghi rõ nguồn.
- Camera thiếu hiệu chuẩn/ROI không được tạo vật cản như dữ liệu đã đo. Camera không được xóa hộp vật cản của LiDAR/người dùng.
- Sau lỗi, không tự chạy tiếp chỉ vì dữ liệu quay lại. Giữ nguyên yêu cầu đánh giá và bắt đầu lại của phiên/bo.

Muốn thay một quy tắc, mô tả tác động và thêm bằng chứng phù hợp trong thay đổi để người review có thể đánh giá. Chi tiết nằm trong [sơ đồ hệ thống](autopark/docs/SO_DO_HE_THONG.md), [giao thức xe](autopark/docs/GIAO_THUC_XE.md) và tài liệu chuyên đề của phần đang sửa.

## 7. Ghi kết quả sao cho người khác kiểm lại được

| Cách viết | Nghĩa đúng |
| --- | --- |
| Đã có mã | Chức năng được cài đặt, chưa nói đã kiểm |
| Đã qua test với nguồn giả | Logic được kiểm trong điều kiện test |
| Đã chạy mô phỏng/QEMU | Có kết quả với xe/bo giả lập, chưa phải xe thật |
| Đã đo bàn thử | Ghi rõ thiết bị thật, máy, cấu hình, ngày và log |
| Đã đạt trên xe | Chỉ dùng khi đủ tiêu chí và bằng chứng thực tế tương ứng |

Tối thiểu ghi: mục đích; commit (`git rev-parse --short HEAD`); cây làm việc có sửa hay không; lệnh; môi trường; cấu hình/seed; kết quả; giới hạn; vị trí log. Ví dụ: “Test nguồn tư thế giả đạt; chưa thử C1 gắn trên xe.”

Kết quả thử cá nhân ở `runs/`. Bằng chứng cần chia sẻ được chọn lọc vào `docs/evidence/` theo cấu trúc đợt đang dùng; giữ cả kết quả hỏng quan trọng để giải thích vấn đề. Không tự đưa toàn bộ video, checkpoint, dữ liệu thô, `.venv` hoặc tệp máy cá nhân vào Git.

`configs/thiet_bi.json` được theo dõi trong kho nhưng chứa cổng/đường dẫn theo máy. Kiểm diff kỹ để không vô tình đổi cấu hình chung sang đường dẫn riêng. Thông số giả định, ngưỡng đề xuất và trạng thái `measured` phải đi cùng căn cứ khi thay đổi.

## 8. Chuẩn bị thay đổi để review

Tại gốc Git, xem phạm vi và lỗi khoảng trắng:

```powershell
git status --short
git diff --stat
git diff --check
git diff
```

Chỉ thêm những tệp thuộc việc đang làm. Ví dụ nếu bạn sửa hướng dẫn này:

```powershell
git add CONTRIBUTING.md
git diff --cached
git commit -m "docs: lam ro bai tap tao sa ban cho nguoi moi"
```

Chỉ chạy `git add` với tên tệp thực tế đã kiểm. Khi sẵn sàng chia sẻ và tài khoản có quyền ghi vào kho, đẩy **nhánh vừa tạo**:

```powershell
git push -u origin docs/huong-dan-sa-ban
```

Thay tên nhánh nếu bạn đã chọn tên khác. Mở kho dự án trên GitHub, chọn **Compare & pull request**, đặt nhánh đích (`base`) là `main` và nhánh nguồn (`compare`) là nhánh của bạn. Điền mô tả rồi tạo PR để nhóm xem lại trước khi hợp nhất.

Nếu chưa có quyền ghi, bạn có thể xin quyền từ chủ kho hoặc chọn **Fork** trên GitHub để có bản sao trong tài khoản của mình. Với cách fork, thêm địa chỉ bản sao bằng `git remote add fork <URL-kho-fork-cua-ban>`, đẩy bằng `git push -u fork docs/huong-dan-sa-ban`, rồi mở PR từ nhánh đó vào `main` của kho gốc. Thay phần `<URL-kho-fork-cua-ban>` bằng URL GitHub thực tế trước khi chạy.

Một PR dễ review cần có:

1. **Vấn đề và kết quả:** người dùng gặp gì, sau thay đổi hành vi thế nào.
2. **Cách kiểm:** lệnh đã chạy và kết quả, kèm ảnh nếu thay giao diện.
3. **Mức bằng chứng:** mô phỏng, nguồn giả, QEMU hay thiết bị thật; phần nào chưa kiểm.
4. **Tài liệu/cấu hình bị ảnh hưởng:** người khác cần đổi bước chạy hay tham số nào.

Nếu đổi hành vi được mô tả trong tài liệu, sửa phần hướng dẫn tương ứng cùng đợt. Dùng từ cụ thể, giải thích thuật ngữ lần đầu và đặt lệnh cạnh kết quả cần thấy. Một người mới phải có thể làm lại các bước mà không cần biết lịch sử cuộc trò chuyện.
