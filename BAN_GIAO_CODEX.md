# Bàn giao AutoPark cho Codex tiếp quản

Ngày lập: **08/11/2026**. Tài liệu này tổng hợp trạng thái repository, bằng chứng đã lưu và ngữ cảnh của phiên bàn giao để một Codex ở tài khoản khác có thể tiếp tục làm việc.

- Repository: <https://github.com/thbn12082/autopark>
- Nhánh đang làm: `main`.
- Mốc trước đợt dọn mã: `f1dec0d75128ff71c374c4e4371ccff0ea30e01b` — `docs: rewrite guides as concise Vietnamese prose`, ngày 28/10/2026 lúc 16:14:55, múi giờ UTC+7.
- Trong phiên bàn giao ngày 08/11/2026, commit trên máy đã được đối chiếu trực tiếp với GitHub và trùng nhau. Trước khi tạo file này, thư mục làm việc sạch.
- File bàn giao được lưu cùng mã nguồn sau đợt dọn ngày 08/11/2026. Xem lịch sử Git để xác định commit chứa đợt dọn và những cập nhật về sau; mốc nêu trên là phiên bản trước khi dọn.

Đây là ảnh chụp trạng thái tại thời điểm bàn giao. Khi tiếp quản, kiểm tra commit mới và thay đổi chưa commit trước khi áp dụng nội dung. Những ý tưởng chưa có trong repository hoặc phiên hội thoại hiện có không được tự suy diễn thành quyết định đã chốt.

## Cập nhật dọn mã ngày 08/11/2026

- Bỏ cơ chế đọc giới hạn đổi chiều từ bảng nghiệm thu đỗ xe cũ trong phiên chạy và giao diện. Giới hạn hiện tại lấy từ `scenario.maneuver.max_cusps`; `--max-cusps` chỉ siết thêm. Trường `acceptance` được giữ làm metadata để đọc/lưu dữ liệu lịch sử, không điều khiển phiên.
- Bỏ bộ lập đường Hybrid A* đời đầu và Reeds–Shepp rút gọn không còn nằm trong portfolio. Các thuật toán đang dùng trong portfolio vẫn được giữ. Kiểu `PlannerParams`/`PlanResult` chuyển sang `autopark/planning/types.py`, heuristic lưới dùng chung chuyển sang `autopark/planning/heuristic.py` (đường dẫn tính từ thư mục dự án Python).
- Giữ cấu trúc `PlannerParams` để đọc và phát lại snapshot cũ. Luồng thao tác gần dùng `time_limit` của đối tượng này; từng nấc portfolio có cấu hình riêng.
- Bỏ package `estimation` trống. Định vị thực tế vẫn nằm trong `autopark/lidar/` và nguồn tư thế ở `autopark/application/lidar_pose_source.py`.
- Thư mục `scenarios/` chỉ còn hai cảnh thao tác gần. Các cảnh nghiệm thu đỗ xe cũ đã bỏ; hai mẫu cần cho kiểm thử đọc dữ liệu lịch sử được chuyển vào `tests/fixtures/legacy_parking.json` và `legacy_layout.json`.
- Bỏ các kiểu/hàm không còn nơi dùng (`GoalPose`, `DriveCommand`, `shortest_norm`, `sample_word`, `hline`, `pnp_hubs`) và màu giao diện ô đỗ không còn sử dụng. Cập nhật các đầu bài test cũ về đích gần, vị trí vật cản và cấu hình bo phù hợp; dùng hàm ghi ảnh hỗ trợ đường dẫn có dấu của dự án.
- Đưa lệnh `evaluation.maneuver_bench` vào nhóm kiểm tra chính sách hiệu năng; áp dụng chính sách ngay đầu hàm `main` như các điểm vào thời gian thực khác.
- Bộ chấm dữ liệu lịch sử, công cụ cảm biến/hiệu chuẩn, firmware và hồ sơ bằng chứng vẫn phục vụ việc kiểm chứng và lộ trình phần cứng. Số liệu 132/132 và 278/278 bên dưới vẫn là bằng chứng của ngày 28/10, không tự trở thành kết quả kiểm thử sau khi dọn.

Kết quả kiểm tra đợt dọn ngày 08/11/2026:

| Lượt kiểm tra | Kết quả |
|---|---|
| Toàn bộ suite, lượt đầu | 1.976 đạt, 31 lỗi, 29 bỏ qua; các lỗi được xử lý trong đợt dọn |
| Chạy lại 31 ca lỗi và kiểm tra bổ sung | 55/55 đạt |
| Hồi quy cuối trên 32 file bị ảnh hưởng và nhóm liên quan | **701 đạt, 2 bỏ qua do thiếu Torch, không lỗi** |
| Phát lại bản ghi `turn_left_forward_seed_0` của chiến dịch 28/10 | Khớp chuyển động, sự kiện và kết quả hoàn thành |
| Phát lại bản ghi `fault_data_loss_recovery_seed_0` của chiến dịch 28/10 | Khớp chuyển động, sự kiện và kết quả dừng |
| Kiểm tra tĩnh | Cú pháp/import nội bộ của 270 file Python hợp lệ; `git diff --check` đạt |

Báo cáo hồi quy cuối ở `autopark/review_artifacts/cleanup_20261108_final2.xml`; báo cáo phát lại ở hai thư mục `autopark/review_artifacts/cleanup_replay_20261108_turn_left_forward/` và `cleanup_replay_20261108_fault_data_loss_recovery/`. Đây là kết quả cục bộ, bị Git bỏ qua. Hai bản phát lại báo `source_changed: true`, đúng vì mã đã được dọn, nhưng đều có `match: true`. Chưa chạy lại toàn bộ chiến dịch mô phỏng 132 lượt sau khi dọn.

## 1. Chúng ta đang làm gì?

AutoPark hỗ trợ **xe mô hình xoay trở ngắn trong chỗ hẹp ở tốc độ thấp**. Người lái chọn một vị trí và hướng đích gần; hệ thống tính đường, đánh lái, tiến/lùi rồi dừng. Người lái quyết định thao tác tiếp theo từ tư thế xe vừa dừng.

Các tình huống chính là cua hẹp, qua cửa, lách cột và chỉnh xe vào khe. Đỗ xe là một ứng dụng gần. Tự tìm ô đỗ và dẫn xe tới đích xa nằm ngoài phạm vi hiện tại.

Luồng sử dụng đã xác định:

1. Kiểm tra vị trí xe, vật cản và vùng thao tác.
2. Chọn vị trí cùng hướng đích gần.
3. Tính thao tác; từ chối nếu đầu bài hoặc đường không đạt điều kiện.
4. Xem trước trong mô phỏng nếu cần.
5. Người dùng xác nhận thực hiện.
6. Xe dừng ở đích hoặc dừng khi có yêu cầu/lỗi; chờ xác nhận đứng yên.
7. Người dùng chọn và xác nhận lượt mới. Phục hồi dữ liệu hay kết nối không tự cho xe chạy tiếp.

**Trạng thái cốt lõi: đã hoàn tất bản đầu của chặng đánh giá phần mềm trong mô phỏng; chưa có kết quả xe thật thực hiện thao tác.**

## 2. Những quyết định cần giữ khi tiếp quản

| Nội dung | Quyết định và ý nghĩa |
|---|---|
| Phạm vi sản phẩm | Tập trung vào từng thao tác gần, do người lái chọn đích và xác nhận. Các tài liệu/cảnh đỗ xe cũ không tự mở rộng phạm vi hiện tại. |
| Đường đi | Có thể gồm tiến và lùi. Kiểm toàn thân xe và vùng quét khi quay; chỉ kiểm một điểm đại diện là chưa đủ. |
| Chấp nhận đường | Đường hình học hợp lệ còn phải được kiểm tra khả năng bám trong mô phỏng trước khi nhận. |
| Trước khi thực hiện | Kiểm lại quỹ đạo, tư thế xuất phát/đích, phản hồi, giới hạn và điều kiện đứng yên. Thay xe, đích hoặc vật cản phải làm phương án cũ mất hiệu lực khi cần. |
| Dừng | Phân biệt yêu cầu dừng, quá trình phanh và phản hồi xác nhận đứng yên. Dừng trước khi đổi chiều. |
| Vai trò AI | Camera/AI bổ sung bằng chứng vật cản; AI không trực tiếp thay bộ lập đường và bộ điều khiển lái. |
| Dữ liệu chưa rõ | Không coi vùng chưa quan sát rõ là trống. Camera không được xóa vật cản đã biết từ LiDAR hoặc người dùng. |
| Chấm kết quả | Tách hoàn thành, từ chối đúng và dừng đúng. Không báo toàn bộ lượt PASS là đến đích thành công. |
| Tài liệu | Bộ hướng dẫn hiện tại dùng tiếng Việt ngắn gọn, có hình và số liệu kiểm chứng. Lệnh kỹ thuật trong file bàn giao này phục vụ người tiếp quản. |

Giới hạn của **hai cảnh mẫu hiện tại**, dùng thông số giả định cho mô phỏng:

| Đại lượng | Giá trị |
|---|---:|
| Khoảng cách từ điểm xuất phát tới đích | Tối đa 0,70 m |
| Vùng thao tác | Khung vuông cạnh 1,50 m quanh điểm xuất phát, cắt theo biên sa bàn |
| Tổng quãng đường tiến/lùi | Tối đa 1,40 m |
| Số lần đổi chiều | Tối đa 3 |
| Tốc độ | Tối đa 0,10 m/s |
| Dung sai đích trong hai file cảnh mẫu | 3 cm và 5 độ |

Đây không phải số đo xe thật hoặc ngưỡng nghiệm thu phần cứng đã chốt. Mỗi tình huống đánh giá có cấu hình riêng; đọc cấu hình thay vì mặc định mọi ca dùng đúng bảng trên.

## 3. Cấu trúc repository và tài liệu cần đọc

Cần phân biệt thư mục gốc Git với thư mục dự án Python nằm bên trong:

```text
<repo-root>/
  README.md
  BAN_GIAO_CODEX.md
  autopark/                       # Thư mục chạy/cài dự án Python
    pyproject.toml
    run_app.py
    requirements-phase0.lock
    requirements-train.lock
    autopark/                     # Package Python
    tests/
    configs/
    scenarios/
    firmware/esp32_vehicle/
    docs/
    runs/                         # Kết quả chạy cục bộ, bị Git bỏ qua
```

Các đường dẫn trong bảng dưới tính từ gốc Git:

| Tài liệu | Mục đích |
|---|---|
| `README.md` | Mục tiêu, phạm vi và trạng thái hiện tại |
| `autopark/docs/KIEN_TRUC.md` | Lập đường, bám đường, cảm nhận, định vị và đánh giá độc lập |
| `autopark/docs/VAN_HANH.md` | Trình tự sử dụng, các chế độ, đọc kết quả, lưu/phát lại |
| `autopark/docs/PHAN_CUNG_VA_HIEU_CHUAN.md` | Điều kiện còn thiếu trên xe thật, đo xe, camera, nguồn và dừng |
| `autopark/docs/KIEM_THU_VA_LO_TRINH.md` | Kết quả mô phỏng và sáu chặng triển khai |
| `autopark/docs/DU_LIEU_VA_GIAY_PHEP.md` | Nguồn bằng chứng, dữ liệu còn thiếu và hồ sơ quyền sử dụng |
| `autopark/docs/evidence/maneuver_suite_stage1_20261028.json` | Bằng chứng tổng hợp có cấu trúc của chặng 1 |

Tại thời điểm bàn giao, repository chưa có `AGENTS.md`. Hãy đọc file này theo yêu cầu của người dùng; không mặc định một file tên `BAN_GIAO_CODEX.md` sẽ được mọi phiên Codex tự động nạp.

## 4. Bản đồ mã nguồn

Trong bảng này, đường dẫn tính từ thư mục dự án Python `<repo-root>/autopark/`.

| Khối | Nơi đọc đầu tiên | Vai trò |
|---|---|---|
| Giao diện | `run_app.py`, `autopark/ui/app.py`, `autopark/ui/main_window.py` | Ứng dụng desktop PySide6, chọn cảnh/đích và điều khiển lượt chạy |
| Phiên thao tác | `autopark/application/session.py` | Điều phối kế hoạch, thực hiện, dừng, bản ghi và trạng thái |
| Đầu bài thao tác gần | `autopark/planning/maneuver.py`, `autopark/planning/maneuver_planner.py` | Giới hạn vùng/quãng đường/đổi chiều, kiểm yêu cầu và quỹ đạo |
| Bộ lập đường | `autopark/planning/portfolio.py` | Thử nhiều cấu hình và kiểm chứng đường bằng mô phỏng bám kín vòng |
| Bám đường | `autopark/control/tracker.py`, `autopark/application/cusp_policy.py` | Tốc độ, góc lái, xử lý chuyển tiến/lùi |
| Hình học và mô phỏng | `autopark/geometry/`, `autopark/simulation/`, `autopark/domain/types.py` | Thân xe, va chạm, động học, trạng thái và cấu hình |
| Chấm độc lập | `autopark/evaluation/maneuver_score.py`, `autopark/evaluation/collision_oracle.py` | Đối chiếu chuyển động và hình học riêng với kết quả điều khiển |
| Bộ thử thao tác | `autopark/evaluation/maneuver_bench.py`, `maneuver_cases.py`, `maneuver_robustness.py`, `maneuver_suite_spec.py` cùng thư mục | Sinh ca, chạy theo seed, báo cáo và phát lại |
| LiDAR và nguồn tư thế | `autopark/lidar/`, `autopark/application/lidar_pose_source.py` | Đo vật cản, định vị theo bản đồ và cung cấp phản hồi tư thế |
| Camera/AI/hợp nhất | `autopark/perception/`, `autopark/fusion/`, `autopark/rig/` | Hiệu chuẩn, phân đoạn, chiếu xuống sàn, hợp nhất và bàn thử cảm biến |
| Liên kết xe | `autopark/application/vehicle_link.py`, `autopark/transport/` | Giao thức, phản hồi, mô hình bo và QEMU |
| Firmware | `firmware/esp32_vehicle/src/main.cpp`, `firmware/esp32_vehicle/src/core/` | Đầu vào/ra phần cứng và lõi điều khiển ESP32 |
| Lưu trữ | `autopark/storage/` | Kịch bản và bản ghi lượt chạy |

Thang tìm đường mặc định trong `portfolio.py` gồm các nấc lưới có thao tác gộp, RRT-Connect với Reeds–Shepp, rồi lưới mịn. Mỗi ứng viên phải qua kiểm chứng bám đường. Lý do kiến trúc được ghi trong mã: góc lái, khoảng hở và khả năng bám tạo ra các đánh đổi; một đường tồn tại chưa chắc xe bám tới đích được.

Một số tên lớp, chú thích, kịch bản và bằng chứng vẫn mang thuật ngữ đỗ xe của giai đoạn trước. Dùng luồng thao tác gần và tài liệu hiện tại để xác định hành vi cần duy trì.

## 5. Kết quả đã có và giới hạn của bằng chứng

Nguồn chính là `autopark/docs/evidence/maneuver_suite_stage1_20261028.json`, ghi rõ `domain: simulation_only` và `hardware_acceptance: false`.

| Hạng mục | Kết quả đã lưu ngày 28/10/2026 |
|---|---:|
| Tình huống cơ sở | 26 |
| Tình huống nhiễu/lỗi/thao tác tiếp | 18 |
| Tổng tình huống cho một seed | 44 |
| Seed | 0, 1, 2 |
| Đến đích và đứng yên | 90/90 |
| Từ chối đúng | 18/18 |
| Dừng đúng | 24/24 |
| Tổng lượt đúng kỳ vọng | 132/132 |
| Thao tác tiếp theo hoàn thành | 15/15, thống kê riêng |
| Nhóm test hồi quy liên quan | 278/278, không lỗi, không bỏ qua |
| Phát lại các ca trong bộ thử | 9 lượt khớp |
| Thử cố ý hết thời gian | 2 lượt FAIL, phát lại vẫn khớp và vẫn là FAIL; ngoài tổng 132 |

Các trạng thái mô phỏng được lấy mẫu cách nhau 0,005 giây. Hồ sơ ghi `continuous_collision_proof: false`: kết quả lấy mẫu không phải chứng minh hình học liên tục cho mọi thời điểm. Hết thời gian tìm đường cũng không chứng minh đầu bài vô nghiệm.

Con số 278 là nhóm hồi quy được ghi trong chiến dịch đó, không phải khẳng định tổng số test toàn repository hiện nay. Các số trên là kết quả lịch sử đã đọc lại; không được ghi thành kết quả mới chạy ngày 08/11/2026.

Môi trường chiến dịch được ghi là Windows, Python 3.12.10, NumPy 2.5.3, Shapely 2.1.2, pytest 9.1.1, PySide6 6.11.2 và EcoQoS tắt. `requirements-phase0.lock` hiện ghi NumPy 2.5.2, nên cài từ lock chưa tái lập chính xác toàn bộ môi trường chiến dịch. Khi so sánh hiệu năng hoặc kết quả, ghi lại phiên bản thực và điều kiện máy.

## 6. Cài, chạy và kiểm tra trên máy tiếp quản

Dự án khai báo Python từ 3.11 trở lên; môi trường đã lưu dùng 3.12.10. Các lệnh dưới dành cho PowerShell trên Windows. Đây là hướng dẫn thao tác từ mã hiện có, không phải báo cáo đã cài mới hoặc chạy toàn bộ test trong phiên bàn giao.

Nếu chưa có bản clone:

```powershell
git clone https://github.com/thbn12082/autopark.git
Set-Location autopark
git status --short --branch
git log -5 --oneline
```

Từ **gốc Git**, đi vào thư mục dự án Python:

```powershell
Set-Location autopark
```

Các lệnh còn lại trong mục này đều chạy tại `<repo-root>/autopark/`. Với bản clone mới, tạo môi trường riêng và cài theo file lock:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-phase0.lock
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
```

Nếu máy không có launcher `py`, dùng đường dẫn Python 3.12 đã cài. Nếu đã có `.venv`, kiểm tra môi trường trước khi quyết định tạo lại. Có thể cài tương tác bằng `cai_dat.cmd`. Các nhánh huấn luyện, AI và thiết bị có dependency riêng trong `pyproject.toml`, `requirements-train.lock` và `cai_dat_train.cmd`; đọc trước khi cài cho công việc tương ứng.

Mở giao diện mô phỏng với từng cảnh mẫu:

```powershell
.\.venv\Scripts\python.exe -X utf8 run_app.py scenarios/thao_tac_cua_hep.json
.\.venv\Scripts\python.exe -X utf8 run_app.py scenarios/thao_tac_lui_vao_khe.json
```

Chạy từng lệnh mở ứng dụng riêng. Đây là ứng dụng desktop; không cần tạo web server để dùng luồng chính.

Xem danh sách tình huống và chạy lại bộ đánh giá mô phỏng:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.maneuver_bench list --seeds 0
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.maneuver_bench run --seeds 0,1,2 --out runs/ban_giao_20261108
```

Dùng thư mục kết quả mới cho mỗi chiến dịch để giữ bằng chứng cũ. Muốn thử một ca, thêm `--case turn_left_forward` và chọn seed phù hợp.

Phát lại một ca từ chiến dịch vừa chạy:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.maneuver_bench replay runs/ban_giao_20261108/cases/turn_left_forward_seed_0
```

`replay` mặc định dùng quyết định, quỹ đạo và thời điểm kích hoạt lỗi đã đóng băng. Thêm `--replan` là chạy lại đầu bài qua bộ lập đường hiện tại; đó là phép thử mới, không được báo thành phát lại nguyên vẹn. Ca bị từ chối hoặc hết thời gian trước chuyển động có thể chỉ phát lại quyết định.

Ví dụ kiểm thử tập trung cho các thay đổi ở thao tác và bộ chấm:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_maneuver.py tests/test_maneuver_validation.py tests/test_maneuver_rollout_limits.py tests/test_maneuver_cases.py tests/test_maneuver_bench.py tests/test_maneuver_evaluation_independent.py tests/test_maneuver_score.py tests/test_maneuver_suite_spec.py
```

Lệnh chạy toàn bộ test khi cần kiểm tra rộng và đã có dependency phù hợp:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Test có marker `planner_budget` phụ thuộc ngân sách thời gian thực; cấu hình dự án yêu cầu chạy nhóm này không có coverage tracing. `tests/conftest.py` có chính sách EcoQoS cho Windows. Không nới ngưỡng chấm chỉ để che một kết quả không đạt; kiểm tra thay đổi code và điều kiện chạy.

Khi lập bản bàn giao ban đầu, đã kiểm tra thành công CLI `maneuver_bench --help` và `list --seeds 0`; danh sách trả về đủ 44 ca. Kết quả kiểm thử sau đợt dọn mã được ghi riêng ở phần cập nhật đầu tài liệu.

## 7. Những gì clone từ GitHub chưa mang theo

GitHub chứa mã nguồn, cấu hình, cảnh thử, tài liệu và bằng chứng tổng hợp được theo dõi. File `autopark/.gitignore` bỏ qua `.venv/`, `.venv-train/`, `runs/`, `models/`, nhiều thư mục dữ liệu thô/đã chuẩn bị, log và các sản phẩm chạy cục bộ.

Đặc biệt, hồ sơ chặng 1 ghi:

```text
raw_artifacts.campaign = runs/maneuver_suite_stage1_final_v2_20261028
raw_artifacts.tracked_in_git = false
```

Thư mục này tồn tại trên máy nguồn tại lúc bàn giao, nhưng phiên này chưa kiểm lại toàn bộ nội dung hoặc hash của dữ liệu thô. Muốn phát lại chính xác chiến dịch cũ trên máy khác, cần chuyển riêng cả thư mục chiến dịch và đối chiếu các hash đã ghi trong JSON bằng chứng. Chạy lại suite chỉ tạo một chiến dịch mới.

Tương tự, checkpoint mô hình, dữ liệu camera/LiDAR, video và dữ liệu huấn luyện phải được kiểm tra thực tế; không mặc định chúng có trong bản clone. Khi chưa có chúng, vẫn có thể tiếp nhận phần mã và làm việc với mô phỏng trong phạm vi dependency đã cài.

## 8. Phần chưa hoàn tất và thứ tự tiếp theo

Lộ trình hiện tại có sáu chặng:

| Chặng | Trạng thái và việc cần làm |
|---|---|
| 1. Đánh giá trong mô phỏng | Đã hoàn tất bản đầu; duy trì hồi quy và thêm ca tái hiện khi có lỗi mới |
| 2. Điều khiển và kết nối xe | Hoàn thiện đầu ra, phản hồi tốc độ/góc lái và giao tiếp bo thật |
| 3. Đo xe, nguồn và phanh | Đo thông số xe, quãng dừng, nguồn, dừng khẩn và hành vi lỗi |
| 4. Định vị và quan sát sát xe | Hiệu chuẩn và đo sai số/vùng mù bằng tham chiếu độc lập |
| 5. Tích hợp chạy thật | Quan sát trước, sau đó từng thao tác chậm; chọn bước tiếp từ tư thế vừa dừng |
| 6. Nghiệm thu và bàn giao | Chốt tiêu chí thực, lặp bộ thử, giữ video và cả lượt không đạt |

Chặng 2–6 chưa hoàn tất theo hồ sơ hiện có. Một số điểm cụ thể để bắt đầu điều tra:

- `firmware/esp32_vehicle/platformio.ini` đang đặt `AP_ENABLE_PWM_OUTPUTS=0`. Loại bo và chân điều khiển còn phải đối chiếu với thiết bị thật; không coi cấu hình mẫu là cấu hình đã nghiệm thu.
- `firmware/esp32_vehicle/src/main.cpp`, hàm `read_inputs()`, còn thiếu phần đọc cảm biến tốc độ, góc lái, IMU, ToF và điện áp; các cờ dữ liệu tương ứng vẫn chưa hợp lệ. Không biến giá trị giả thành số đo thật.
- Phải đo chiều dài cơ sở, bề rộng, phần nhô, vòng quay, trễ lái và quãng phanh. Tư thế xe đặt tại tâm trục sau, trục x hướng trước và trục y hướng trái.
- Tài liệu kiến trúc ghi vùng che quanh thân xe trong bản đồ ảnh có thể loại nhầm vật cản cách xe tới khoảng 10 cm. Đây là vấn đề cần kiểm trước khi dùng ở khoảng hở nhỏ; chưa có xác nhận đã xử lý.
- Phản hồi và cảm biến phục hồi không tự mở lại chuyển động. Cần giữ cơ chế dừng, chờ đứng yên và xác nhận lượt mới.
- Camera/AI hiện học chủ yếu từ ảnh đường phố. Cần dữ liệu sa bàn, vật thấp, mép tường, cột và vùng sát xe, có nhãn kiểm độc lập và tách theo phiên/cảnh.
- Các ghi chú giấy phép trong tài liệu dữ liệu là hồ sơ rà soát tháng 9/2026. Không diễn giải thành xác nhận điều khoản hiện hành; nếu cần quyết định sử dụng nguồn dữ liệu mới, kiểm lại nguồn gốc tương ứng.

Hướng tiếp theo hợp lý theo lộ trình là làm rõ điều khiển/phản hồi bo và phép đo trên xe. **Phiên bàn giao này chưa giao một nhiệm vụ triển khai cụ thể cho chặng 2.** Codex tiếp quản cần tóm tắt hiện trạng và xác định đầu việc với người dùng trước khi tự chọn một thay đổi lớn.

## 9. Lịch sử gần đây để hiểu sự chuyển hướng

| Commit | Nội dung chính |
|---|---|
| `1098c50` — 28/10/2026 | Thu hẹp AutoPark vào thao tác gần; bổ sung giới hạn/kiểm tra và hai cảnh mẫu, loại bỏ nhiều nhánh/tài liệu cũ |
| `cf87bb1` — 28/10/2026 | Củng cố kiểm tra quỹ đạo trước chạy, vùng quét khi dừng, dừng tức thời theo yêu cầu, lỗi nguồn tư thế và lưu cảnh; thêm hình minh họa |
| `b35fead` — 28/10/2026 | Thêm bộ 44 tình huống, chấm độc lập, báo cáo JSON/CSV, phát lại và bằng chứng 132 lượt |
| `f1dec0d` — 28/10/2026 | Viết lại sáu phần hướng dẫn bằng văn xuôi tiếng Việt ngắn gọn, giữ hình và kết quả đã kiểm chứng |

Khi cần thông tin kỹ thuật đã bị rút khỏi tài liệu, có thể đọc lịch sử Git để hiểu nguồn gốc; sau đó phải đối chiếu với mã hiện tại. Các công cụ hoặc trang hướng dẫn đã bị xóa không mặc nhiên còn dùng được.

## 10. Yêu cầu dành cho Codex nhận bàn giao

Hãy dùng file này cùng repository để tiếp nhận công việc:

1. Kiểm tra remote, nhánh, commit và thay đổi chưa commit; bảo toàn công việc đang có.
2. Đọc README, năm tài liệu trong `autopark/docs/` nêu ở mục 3 và JSON bằng chứng chặng 1.
3. Đối chiếu phần code liên quan; không xem file bàn giao là bằng chứng thay thế mọi mã nguồn hoặc kết quả chạy.
4. Tóm tắt lại mục tiêu, luồng hoạt động, kết quả mô phỏng, điều kiện còn thiếu trên xe thật và phần dữ liệu cục bộ chưa nhận được.
5. Nếu chưa có nhiệm vụ tiếp theo, đề xuất một đầu việc cụ thể dựa trên lộ trình và nêu thông tin thiết bị còn cần. Nếu người dùng đã giao việc, thực hiện trong phạm vi đó.
6. Với thay đổi code, kiểm thử phần bị tác động, giữ riêng các loại kết quả và báo rõ điều gì đã/chưa được chạy trên môi trường hiện tại.
7. Trao đổi và viết tài liệu bằng tiếng Việt rõ ràng. Phân biệt hiện trạng đã xác minh, kết quả lịch sử, giả định và đề xuất mới.

Phiên nguồn đã kiểm tra đồng bộ GitHub, chuẩn bị tài liệu bàn giao rồi dọn mã theo yêu cầu người dùng. Khi tiếp quản, đọc commit dọn mã, kết quả kiểm thử đi kèm và các thay đổi cục bộ nếu có. Mục tiêu của lượt tiếp nhận là hiểu đúng dự án rồi tiếp tục từ bằng chứng và yêu cầu thực tế của người dùng.
