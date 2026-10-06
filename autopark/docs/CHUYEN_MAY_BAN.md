# Chuyển sang máy bàn mới (29/09/2026)

**Quyết định của người dùng (29/09/2026):** từ ngày này, máy dưới đây là máy bàn, tức máy phát triển chính của dự án
("chuyển hẳn sang máy này"). Máy bàn cũ là nơi đo mọi số cảm biến, AI và bàn thử tới 25/09/2026 (mô phỏng giai đoạn 0
ngày 20/09 chạy trên laptop). Vai trò của laptop RTX 3050 Ti (mang đi nộp đồ án, [MAY_NOP_DO_AN.md](MAY_NOP_DO_AN.md))
giữ nguyên.

| | Máy bàn cũ (tới 25/09/2026) | Máy bàn mới (từ 29/09/2026) |
|---|---|---|
| Máy | i9-14900 + RTX 4000 Ada 20 GB, RAM 64 GB | Dell Precision 3680, i9-14900, RTX 4000 Ada 20 GB, RAM 63,7 GB, Windows 11 Enterprise 26200 |
| Driver NVIDIA | 596.72 | 596.71 |
| Thư mục repo | `D:\ap` (mã ở `D:\ap\autopark`) | `D:\gấp\autopark` (mã ở `D:\gấp\autopark\autopark`); **chiều 29/09/2026 người dùng đổi tên `D:\gấp` thành `D:\xetulai`, nên repo nay ở `D:\xetulai\autopark`** (mục 6) |
| Python gốc | `%LOCALAPPDATA%\Python\pythoncore-3.12-64` (3.12.10) | `%LOCALAPPDATA%\Programs\Python\Python312` (3.12.10, winget, bộ cài python.org, cài cho một người dùng) |
| LiDAR C1 (bộ chuyển CP2102N) | COM4, driver CP210x 11.6.0.420 | **COM3**, driver CP210x 11.2.0.167 (Windows Update) |
| Hub UGREEN của bốn camera | cổng gốc 5 của PC | cổng gốc 8 (HS08); số cổng trên hub vẫn 1–4 |

Cùng một thiết bị: C1 serial `f57ffc8bc6e598d1b59598f976dd5762` như máy cũ; bốn camera 1BCF:0B09 không có serial, nên
danh tính là cổng hub chúng cắm vào ([usb_topology.md](usb_topology.md)).

Bằng chứng của đợt này: [evidence/chuyen_may_20260929/](evidence/chuyen_may_20260929/).

## 1. Chép nguyên thư mục thì hỏng gì

Người dùng chép nguyên thư mục dự án (kể cả `.venv`, `.venv-train`, `runs/`, `datasets/`, checkpoint) từ máy cũ. Kiểm ngày
29/09/2026:

| Hỏng | Vì sao | Xử lý 29/09/2026 |
|---|---|---|
| Máy chưa có Python (chỉ có bản giả của WindowsApps) | máy mới | Cài Python 3.12.10 bằng `winget install --id Python.Python.3.12 --version 3.12.10 --scope user` |
| `.venv`, `.venv-train` báo `No Python at 'C:\Users\<người dùng máy cũ>\...'` | `pyvenv.cfg` và launcher trỏ về Python của máy cũ; bản `autopark` dạng editable trỏ về `D:\ap\autopark` | Dời hai venv sang `D:\gấp\_venv_cu_tu_may_cu\` (≈ 6,0 GB), tạo lại theo tệp khóa; người dùng đồng ý xóa thư mục đó, đã xóa cùng ngày |
| `cai_dat.cmd`, `cai_dat_train.cmd` không tự sửa được | chỉ tạo venv khi CHƯA có `python.exe`, mà venv chép sang vẫn có tệp đó | Sửa: `kiem_venv.cmd` chạy thử python của venv; không chạy thì đổi tên thành `<venv>.hong-tu-may-cu` rồi tạo mới (mục 3) |
| LiDAR không có cổng COM | bộ chuyển CP2102N báo lỗi 28 (chưa có driver) | Cài driver từ Windows Update (Silicon Labs Ports 11.2.0.167). Tải từ silabs.com bị chặn (HTTP 403) |
| LiDAR ở COM3, mặc định và tài liệu ghi COM4 | Windows cấp số COM theo từng máy | Sửa: số COM của LiDAR đặt ở MỘT chỗ, `configs/thiet_bi.json` (mục 3) |
| Traceback và tên test hiện đường dẫn `D:\ap\...` | 20 thư mục `__pycache__` chép sang có `.pyc` mang đường dẫn máy cũ; bản chép giữ thời gian sửa tệp nên Python coi `.pyc` còn hợp lệ | Xóa 20 thư mục `__pycache__` và `.pytest_cache` (bị git-ignore, tự sinh lại) |
| `cv2.imread` trả None, `cv2.imwrite` trả False (không báo lỗi) với đường dẫn có dấu | bảng mã ANSI của máy là 1252, không có chữ "ấ" trong "gấp"; máy cũ ở `D:\ap` (ASCII) | Sửa: `autopark/image_io.py` (mục 3). Đo 29/09/2026 (OpenCV 5.0.0): `VideoWriter`/`VideoCapture` không bị |
| `.venv` dựng lại theo `requirements-phase0.lock` thiếu pyserial | `.venv` cũ có pyserial 3.5 (cài qua extra `[lidar]`) nhưng tệp khóa không ghi | Sửa: thêm `pyserial==3.5` vào tệp khóa |

Không hỏng: checkpoint `runs/ai_woodscape_rtx4000_v1/best.pt` trùng SHA-256 ghi ở [MAY_NOP_DO_AN.md](MAY_NOP_DO_AN.md) mục 1;
`datasets/` (≈ 69 GB) và `runs/` đủ. Các tệp trong `runs/ai_*` và `runs/do_nhay_xe/` còn ghi đường dẫn `D:\ap\autopark\...`:
đó là hồ sơ của máy cũ, không dùng để chạy lại (`D:\ap\autopark` tương ứng `D:\gấp\autopark\autopark`). *(Cập nhật
30/09/2026: nay tương ứng `D:\xetulai\autopark\autopark`, mục 6.)*

## 2. Kiểm trên máy mới (29/09/2026)

**Toàn bộ bộ test ở `9d68257`** (mã y như máy cũ, trước mọi sửa đổi của mục 3), offscreen, máy gần rảnh:

| Môi trường | Kết quả | Máy cũ, lần cuối (25/09/2026) |
|---|---|---|
| `.venv` | **1315 đạt, 7 bỏ qua** (cần torch), 0 hỏng, 374 s | 1315 đạt, 7 bỏ qua, 325 s |
| `.venv-train` | **1376 đạt**, 0 bỏ qua, 0 hỏng, 389 s | 1376 đạt, 354 s |

Tệp: [pytest_venv_9d68257.xml](evidence/chuyen_may_20260929/pytest_venv_9d68257.xml),
[pytest_venv_train_9d68257.xml](evidence/chuyen_may_20260929/pytest_venv_train_9d68257.xml). Lần `.venv` chạy trước khi xóa
`__pycache__`, nên tên tệp của các dòng bỏ qua trong xml là `..\..\..\ap\autopark\tests\...` (mục 1).

**Lệnh kiểm máy mới** `do_may_moi.cmd` (= `rig.may_moi`, sáu bước, 202 s, chạm LiDAR và bốn camera thật), không bước nào
lỗi: [tom_tat.md](evidence/chuyen_may_20260929/may_moi/tom_tat.md) và các tệp chi tiết cạnh nó (bản gốc trong
`runs/may_moi_20260929_may_moi_chep/`, git-ignore). So với tham chiếu máy bàn cũ 24/09 19:08:

| Số đo | Máy bàn mới | Máy bàn cũ |
|---|---|---|
| LiDAR: cổng, tốc độ quay, tia/vòng (trung vị) | COM3, 10,00 Hz, 508 | COM4, 9,99 Hz, 508 |
| AI: một lô 4 ảnh 480p, trung vị / p95 (ms), VRAM đỉnh | 10,8 / 12,1, 78 MB | 10,4 / 11,4, 78 MB |
| Bàn thử 480p + LiDAR + AI 120 s: bộ ảnh, khung hỏng, bộ AI/s | 2861, 0, 23,85 | 2861, 0, 23,85 |
| … tổng làm nóng AI | 6,1 s | 5,9 s |
| 720p chỉ camera 30 s: bộ ảnh, khung hỏng | 715, 0 | 716, 0 |

Giới hạn: camera nhìn cảnh nào lúc đo **không ghi lại**; tham chiếu cũ nhìn chỗ tối dưới gầm bàn. Số khung hỏng ở 720p
phụ thuộc cảnh, nên dòng 720p chỉ so được khi cùng cảnh. Chưa thử khởi động lại máy để kiểm danh tính camera theo cổng hub
(N-C5 của [NGUONG_NGHIEM_THU_DE_XUAT.md](NGUONG_NGHIEM_THU_DE_XUAT.md)). *(Cập nhật 02/10/2026: vẫn chưa thử, kể cả ở lượt
thiết bị ngày đó (mục 12); việc 1 của [VIEC_TAI_CHO_THIET_BI.md](VIEC_TAI_CHO_THIET_BI.md).)*

**Tham chiếu `may_moi` mới (người dùng quyết định 29/09/2026):** lượt đo này là tham chiếu máy bàn,
[evidence/may_ban/tham_chieu_20260929.json](evidence/may_ban/tham_chieu_20260929.json) (nguyên `digest` của `may_moi.json`
trên, kèm ghi chú máy, mã và giới hạn). Lệnh lấy tệp đứng cuối theo tên, nên `may_moi` (kể cả trên laptop) nay so với tệp
này; cột tham chiếu có đủ quy tắc chờ, làm nóng AI và độ lệch bộ ảnh, không còn cảnh báo hay ô "—" nào khi so hai lượt
cùng quy tắc. Hai tệp 24/09 của máy bàn cũ giữ để đối chiếu. Test: `tests/test_may_moi.py`
(`test_reference_20260929_shipped_in_repo_renders_every_cell`).

**Các lệnh cùng dạng lệnh trong README, chạy trên máy này** *(thêm 30/09/2026 từ hồ sơ `runs/kiem_may_20260929/`; hồ sơ
không ghi ai chạy và vì sao)* (29/09/2026 15:08–15:19, mã `b37e9ee`, tức đã có các sửa đổi ở mục 3):
mô phỏng giai đoạn 0, ghi LiDAR 10 s ở COM3, kiểm bộ dữ liệu đã chuẩn bị (`verify_cache`), chấm AI trên val, dự đoán,
train thử 1 epoch, bàn thử bốn camera + LiDAR + AI có ghi phiên rồi phát lại, một lượt `may_moi` nữa và ba lượt lặp
AI. Lệnh, giờ và số chính của từng lượt: [kiem_may_20260929.md](evidence/chuyen_may_20260929/kiem_may_20260929.md); tệp
gốc ở `runs/kiem_may_20260929/` (git-ignore).

## 3. Sửa đổi để lần sau đổi máy chỉ sửa một chỗ (29/09/2026)

**Cổng LiDAR: một chỗ duy nhất, [configs/thiet_bi.json](../configs/thiet_bi.json), khóa `lidar_port`.** Hiện là `"COM3"`.
Ghi `"auto"` thì tự tìm bộ chuyển CP210x (VID 10C4, PID EA60; lấy cổng CP210x đầu tiên, nên đừng dùng khi cắm thêm một bo
khác cũng qua CP210x). Mã đọc: `autopark/lidar/port.py`. Các lệnh đọc tệp này khi không có `--port`:

| Lệnh | Trước 29/09/2026 | Từ 29/09/2026 |
|---|---|---|
| `ui.lidar_app`, ngăn LiDAR | mặc định `COM4`; ô cổng trống cũng là COM4 | ô cổng điền sẵn giá trị của tệp; ô trống lấy lại từ tệp |
| `fusion.demo`, `lidar.live_view` | bắt buộc `--port` hoặc `--recording` | không có cả hai: mở LiDAR ở cổng của tệp |
| `lidar.bench record`, `lidar.rplidar_c1 info/stream` | bắt buộc `--port` | `--port` tùy chọn |
| `rig.bench`, `ui.rig_app` | `--lidar COMx`; không có `--lidar` = không LiDAR | thêm `--lidar` KHÔNG kèm giá trị = cổng của tệp; còn lại như cũ |
| `rig.may_moi` | tự tìm CP210x | như cũ (máy mới chưa biết số COM); dùng chung hàm tìm với `lidar/port.py` |

`--port COMx` (hay `--port auto`) vẫn ghi đè cho một lần chạy. Tệp hỏng hay thiếu thì lệnh báo lỗi rõ và thoát TRƯỚC khi mở
thiết bị nào (`rig.bench` kiểm cổng LiDAR trước khi tra cổng hub và dựng camera). Tệp lưu bằng Notepad hay
`Set-Content -Encoding UTF8` của PowerShell 5.1 (có BOM) vẫn đọc được. `rig.may_moi --lidar auto` đổi `auto` ra COMx trước
khi gọi lệnh con, nên không thấy CP210x thì chỉ bước `lidar` lỗi, các bước sau vẫn chạy. Test: `tests/test_lidar_port.py`
(30 mục) và một test mới trong `tests/test_may_moi.py`, cổng giả, không mở thiết bị.

**Đọc/ghi ảnh chịu được đường dẫn có dấu: `autopark/image_io.py`** (`imread`, `imwrite`, cùng hợp đồng như cv2: imread
trả None khi hỏng; imwrite trả False khi không ghi được và ném `cv2.error` ở đúng những chỗ `cv2.imwrite` ném).
Dùng ở `perception/roi.py`, `perception/costmap.py`, `perception/prepare_extra.py`, `lidar/bench.py`, `lidar/occupancy.py`,
`video/camera_bench.py`, `evaluation/phase0.py`: những chỗ còn gọi thẳng `cv2.imread/imwrite` lúc 29/09. Ví dụ hỏng trước khi
sửa: `perception.costmap` mặc định đọc ROI ở `PROJECT/configs/roi/woodscape_v1`, tức đường dẫn tuyệt đối `D:\gấp\...`. Các
mô-đun khác đã có hàm riêng tương đương từ trước (`bev.py`, `fisheye_calib.py`, `labels.py`, `roi_tool.py`, `rig_app.py`...),
chưa gộp về `image_io.py`. Test: `tests/test_image_io.py`, 8 mục (thư mục tên tiếng Việt trong `tmp_path`, vì `%TEMP%` chỉ
có ký tự ASCII nên test cũ không bắt được lỗi này; một mục cần torch).

Các sửa đổi trên được một tác tử khác soát lại (chỉ đọc) ngày 29/09/2026. Nó tìm ra ba lỗi, đều đã sửa: tệp cấu hình có
BOM bị coi là hỏng; `may_moi --lidar auto` không thấy CP210x thì `SystemExit` làm dừng cả lệnh, không ghi tóm tắt;
`image_io.imwrite` nuốt `cv2.error` mà `cv2.imwrite` gốc vẫn ném.

**Cài đặt:** `kiem_venv.cmd` (gọi từ `cai_dat.cmd` và `cai_dat_train.cmd`) chạy thử `python.exe` của venv; venv chép từ máy
khác thì đổi tên thành `.venv.hong-tu-may-cu` / `.venv-train.hong-tu-may-cu` (không xóa, git-ignore) rồi tạo mới; nếu tên đó
đã có thì dừng và báo. Thử 29/09/2026 trên bản sao venv hỏng của máy cũ và trên hai venv thật (không đổi). `cai_dat.cmd` ghi
lại bằng CRLF: bản trong cây làm việc trước đó chỉ có LF, trái với `.gitattributes` (`*.cmd text eol=crlf`).
`requirements-phase0.lock` có thêm `pyserial==3.5`.

**Docstring:** "chạy trong `D:/ap/autopark`" ở `evaluation/phase0.py`, `robustness.py`, `sensitivity.py` đổi thành "thư mục
`autopark` của repo (thư mục có pyproject.toml)"; ví dụ lệnh trong docstring của các lệnh LiDAR bỏ `--port COM4`. Câu lịch
sử giữ nguyên (ví dụ `lidar/rplidar_c1.py`: "Đã kiểm chứng ... ngày 22/09/2026 (COM4, ...)").

**Toàn bộ bộ test sau các sửa đổi** (máy bàn mới, 29/09/2026, offscreen, mã sau sửa đổi của đợt này, dựng trên `9d68257`):
`.venv` **1353 đạt, 8 bỏ qua** (7 như trước cộng test ROI mới, đều cần torch), 0 hỏng, 342 s; `.venv-train` **1415 đạt**,
0 bỏ qua, 0 hỏng, 395 s (1376 cũ + 39 mới). Tệp: [pytest_venv_sau_sua_20260929.xml](evidence/chuyen_may_20260929/pytest_venv_sau_sua_20260929.xml),
[pytest_venv_train_sau_sua_20260929.xml](evidence/chuyen_may_20260929/pytest_venv_train_sau_sua_20260929.xml). Lượt
này chạy trên cây làm việc trước khi commit. **Chạy lại trên commit `38f64bb`** (cây làm việc sạch, cùng máy, cùng ngày,
offscreen): `.venv` **1354 đạt, 8 bỏ qua**, 0 hỏng, 336 s; `.venv-train` **1416 đạt**, 0 hỏng, 370 s. Mỗi môi trường thêm
đúng một test so với lượt trên (tệp tham chiếu `may_moi` 29/09, mục 2). Tệp:
[pytest_venv_38f64bb.xml](evidence/chuyen_may_20260929/pytest_venv_38f64bb.xml),
[pytest_venv_train_38f64bb.xml](evidence/chuyen_may_20260929/pytest_venv_train_38f64bb.xml). Với thiết bị thật, sửa đổi
mới chỉ thử một lệnh: `lidar.rplidar_c1 info` KHÔNG có `--port` mở đúng COM3 lấy từ tệp cấu hình, đọc được C1 (cùng
serial, health OK), mã thoát 0; `lidar_port("auto")` cũng ra COM3. `ui.lidar_app`, `fusion.demo`, `rig.bench --lidar`
và camera CHƯA THỬ với thiết bị thật sau sửa đổi; lượt `do_may_moi.cmd` ở mục 2 là mã `9d68257`. *(Cập nhật 30/09/2026:
chiều 29/09/2026 (15:08–15:19, mã `b37e9ee`, sau các sửa đổi này) đã chạy với thiết bị thật: `rig.bench --lidar` 30 s
với bốn camera, LiDAR ở cổng lấy từ tệp cấu hình (COM3) và AI, có ghi phiên rồi phát lại; cùng đợt còn ghi LiDAR 10 s
ở COM3 (không lưu argv, không biết lấy cổng từ tệp cấu hình hay từ `--port`) và một lượt `may_moi` nữa (lệnh này không
đọc tệp cấu hình: tự tìm CP210x hoặc dùng `--lidar` được truyền, argv của nó không lưu; lệnh con nhận `--lidar COM3`)
([kiem_may_20260929.md](evidence/chuyen_may_20260929/kiem_may_20260929.md), mục 2). `ui.lidar_app` và
`fusion.demo` vẫn chưa thử với thiết bị thật.)*
*(Cập nhật 02/10/2026: `fusion.demo` đã chạy 30 s với C1 thật, không có `--port` nên cổng lấy từ tệp cấu hình (COM3);
`ui.lidar_app` vẫn chưa thử với thiết bị thật. Mục 12.)*

Tài liệu: lệnh cần chạy trong các tệp `.md` bỏ `--port COM4` / đổi `--lidar COM4` thành `--lidar`; câu ghi phiên đo cũ ở COM4
giữ nguyên, có ghi chú ngày khi cần. Tệp `docs/evidence/` không sửa.

## 4. Còn khác máy cũ, chưa làm

- Driver CP210x 11.2.0.167 (máy cũ 11.6.0.420); driver NVIDIA 596.71 (máy cũ 596.72). LiDAR và AI đo được như máy cũ (mục 2).
- Máy này có g++ 16.1.0 và cmake 4.4.1 trên PATH; máy cũ không có trình biên dịch nên test host của firmware
  (`firmware/esp32_vehicle/test/host`) chưa biên dịch lần nào. *(Làm 29/09/2026, mục 6: lõi `src/core` biên dịch và
  qua test host, 703 check, 0 lệch; chiều cùng ngày cài PlatformIO, cả firmware biên dịch cho ESP32-S3, mục 7.)*
- GitHub: đã đăng nhập trên máy này ngày 29/09/2026 bằng Git Credential Manager (đăng nhập mã thiết bị qua Edge); fetch
  và push được: các commit của đợt này push lên `origin/main` ngày 29/09/2026. Sau fetch, `main` tiến nhanh từ `9d68257` lên `2ee2940` của GitHub (hai commit ngày 26/09/2026 chỉ sửa
  tệp `.md`), nên mã nguồn vẫn như lúc đo các số test ở mục 2 và 3.
- Ổ D còn ≈ 30,6 GB trống (29/09/2026, sau khi tạo lại venv và xóa venv cũ ≈ 6,0 GB; trước khi xóa còn ≈ 24,6 GB).
  Kịch bản LD-1 có `--record` của [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) đòi ≥ 30 GB. *(Cập nhật 30/09/2026:
  ≈ 28 GB sau khi cài PlatformIO, rồi ≈ 62,6 GB khi đọc lại chiều 30/09/2026; mục 7.)* *(Cập nhật 02/10/2026: 62,1 GB lúc
  14:08, 38,5 GB sau LD-1 lần 3 lúc 17:54; LD-1 lần 2 và lần 3, mỗi lượt 30 phút có `--record`, ghi 8344 MB và 7995 MB ở
  cảnh lúc đó; mục 12.)*
- Trọng số pretrained của torchvision: lúc chuyển máy chưa có; đã có trong `%USERPROFILE%\.cache\torch\hub\checkpoints`
  (`lraspp_mobilenet_v3_large-d234d4ea.pth`) từ 29/09/2026 15:09, tải khi chạy train thử 1 epoch (mục 2), SHA-256 bắt
  đầu bằng `d234d4eae9d5`, trùng tệp mà `run_manifest.json` của các lượt train cũ ghi. Máy nào chưa có tệp này thì lần
  train, benchmark hay `--resume` đầu tiên cần mạng. Suy luận (AI, bàn thử, AI camera) không cần.
- Test phụ thuộc thời gian thật (`planner_budget`, ví dụ `uturn_w46`) có thể hỏng khi máy bận; chạy lại riêng lúc máy rảnh
  trước khi kết luận. *(30/09/2026: `uturn_w46` hỏng cả khi máy gần rảnh, với tiến trình pytest không có cửa sổ để
  Windows tự quyết EcoQoS; từ trưa 30/09 `tests/conftest.py` tắt EcoQoS cho tiến trình pytest, mục 8.)*

## 5. Lần sau đổi máy

1. Cài Python 3.12.10 (bản của tệp khóa) và driver CP210x của Silicon Labs.
2. Chạy `autopark\cai_dat.cmd` rồi `autopark\cai_dat_train.cmd`. Venv chép sang mà hỏng sẽ tự được đổi tên và tạo lại.
3. Sửa MỘT dòng `lidar_port` trong `autopark\configs\thiet_bi.json` theo số COM của LiDAR trên máy đó (Device Manager, mục
   "Silicon Labs CP210x USB to UART Bridge (COMx)"), hoặc ghi `"auto"`. Cùng tệp (từ 30/09/2026): `qemu_xtensa`,
   `platformio_python`, `platformio_core_dir` cho bo ảo QEMU ([MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md)); máy không có
   QEMU thì xóa ba khóa đó hoặc để nguyên (test bo ảo tự bỏ qua khi đường dẫn không tồn tại).
4. Nếu cần firmware hoặc bo ảo *(thêm 30/09/2026)*: cài g++, cmake và Ninja nếu máy chưa có (máy bàn hiện tại có bản
   WinLibs MinGW-w64 UCRT: g++ 16.1.0, cmake 4.4.1, Ninja, cài bằng winget cho người dùng nên nằm trong
   `%LOCALAPPDATA%\Microsoft\WinGet\Packages\` trên ổ C; mục 4, 6); cài PlatformIO trong một venv riêng và đặt
   `PLATFORMIO_CORE_DIR` sang ổ còn trống trước lần chạy đầu (mục 7); tải QEMU của Espressif 9.2.2
   ([MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md) mục 2.1, 6); ghi các đường dẫn vào `configs\thiet_bi.json` (bước 3).
   Rồi chạy `pio run -e esp32s3` trong `firmware\esp32_vehicle` và
   `.venv\Scripts\python.exe -X utf8 -m autopark.transport.qemu_board kiem` trong thư mục `autopark`.
5. Traceback còn hiện đường dẫn máy cũ thì xóa các thư mục `__pycache__` ngoài venv.
6. Chạy toàn bộ bộ test ở cả hai venv, rồi `autopark\do_may_moi.cmd` với LiDAR và bốn camera cắm đúng cổng hub 1–4.
   Máy có cmake và g++ thì bộ test tự build và chạy test host của firmware (mục 6); không có thì hai test đó bỏ qua.

Chỉ đổi tên hay dời thư mục repo trên cùng máy (venv vẫn chạy nên `kiem_venv.cmd` không bắt được): chạy
`.venv\Scripts\python.exe -m pip install -e . --no-deps` và như vậy với `.venv-train` (mục 6).

## 6. Đổi tên thư mục repo, biên dịch test host firmware (chiều 29/09/2026)

**Đổi tên `D:\gấp` → `D:\xetulai`** (người dùng làm). Đường dẫn repo nay chỉ có ký tự ASCII. Kiểm sau khi đổi:

| Hỏng | Vì sao | Xử lý |
|---|---|---|
| `import autopark` hỏng khi chạy ngoài thư mục repo (trong thư mục repo vẫn chạy vì thư mục hiện hành nằm trên `sys.path`) | bản cài editable ở cả hai venv trỏ về `D:\gấp\autopark\autopark\autopark` | `pip install -e . --no-deps` ở `.venv` và `.venv-train`; `import autopark` từ `C:\` ra `D:\xetulai\...` |
| Các launcher `.venv\Scripts\*.exe` (`pytest.exe`, `pip.exe`, `pyside6-*.exe`...) và `activate` còn ghi `D:\gấp\...` | pip ghi đường dẫn tuyệt đối của python venv vào launcher lúc cài | **Chưa sửa.** Mọi tệp `.cmd` của dự án gọi `.venv\Scripts\python.exe -m ...`, không dùng launcher. Cần launcher thì tạo lại venv (đổi tên venv cũ rồi chạy `cai_dat*.cmd`) |

Traceback và cảnh báo của pytest còn hiện `D:\gấp\...`: 18 thư mục `__pycache__` ngoài venv có `.pyc` cũ (như mục 1);
đã xóa cùng `.pytest_cache`. Đường dẫn `D:\gấp\...` còn trong tài liệu và trong `.pyc` của venv là hồ sơ lúc viết; `autopark/image_io.py` (mục 3)
vẫn cần vì thư mục dữ liệu hay đường dẫn khác có thể có dấu.

**Test host của firmware** (`firmware/esp32_vehicle/test/host`, g++ 16.1.0 MinGW-w64 UCRT của WinLibs, cmake 4.4.1,
Ninja): lõi `src/core` biên dịch lần đầu không sửa dòng nào và khớp bản tham chiếu Python, `703 checks, 0 failures`;
bảy đột biến vector đều bị bắt. Chi tiết: [README firmware](../firmware/esp32_vehicle/README.md) mục "Cách kiểm trên
máy tính"; bằng chứng: [firmware_host_20260929.txt](evidence/chuyen_may_20260929/firmware_host_20260929.txt).
Sửa kèm:
- `test/host/CMakeLists.txt`: với MinGW liên kết tĩnh (`-static`). Lý do: exe liên kết động chạy trong Git Bash nạp
  `libstdc++-6.dll` cũ của Git (`C:\Program Files\Git\mingw64\bin` đứng trước WinLibs trên PATH của Git Bash), và bản
  `-O1`/`-O2` segfault ngay ở `std::ifstream`; cùng exe chạy trong PowerShell thì đạt. Thêm `ctest` (test `vectors`).
- Xóa một overload `to_hex` không dùng trong `test_main.cpp` (cảnh báo `-Wunused-function` duy nhất).
- Thêm `tests/test_transport_firmware_host.py` (2 test): build bằng cmake vào thư mục tạm, chạy trên `vectors.json`;
  vector sai một bit phải làm exe thoát 1. Bỏ qua khi không có cmake hoặc trình biên dịch C++ trên PATH (laptop).

**Toàn bộ bộ test sau đợt này** (máy bàn, 29/09/2026, `D:\xetulai`, offscreen, `b37e9ee` + sửa đổi chưa commit của mục
này): `.venv` **1356 đạt, 8 bỏ qua** (như trước, đều cần torch), 0 hỏng, 414 s; `.venv-train` **1418 đạt**, 0 bỏ qua,
0 hỏng, 427 s. Mỗi môi trường thêm đúng hai test so với lượt `38f64bb` (mục 3), là hai test host firmware, và cả hai
chạy thật (không bỏ qua). Tệp: [pytest_venv_firmware_host_20260929.xml](evidence/chuyen_may_20260929/pytest_venv_firmware_host_20260929.xml),
[pytest_venv_train_firmware_host_20260929.xml](evidence/chuyen_may_20260929/pytest_venv_train_firmware_host_20260929.xml).
Lượt `.venv-train` chạy trước khi xóa `__pycache__`, nên một cảnh báo torch trong đầu ra ghi đường dẫn `D:\gấp\...`.

## 7. Cài PlatformIO, biên dịch firmware ESP32-S3 (chiều 29/09/2026)

Người dùng yêu cầu cài PlatformIO và chạy `pio run -e esp32s3`. Ổ C chỉ còn ≈ 11 GB trống, nên mọi thứ đặt trên ổ D,
ngoài repo:

| Gì | Ở đâu |
|---|---|
| PlatformIO Core 6.2.0 | venv riêng `D:\xetulai\_platformio\penv` (Python 3.12.10 của máy; không đụng `.venv`, `.venv-train`) |
| Nền tảng, toolchain, framework (≈ 3 GB) | `D:\xetulai\_platformio\core`, qua biến môi trường người dùng `PLATFORMIO_CORE_DIR` (đặt cố định, để `pio` hay extension VS Code không tải lại vào ổ C) |
| Bản sao tạm để kiểm PWM bật và Arduino 3.x | `D:\xetulai\_platformio\kiem_*` (không phải cấu hình thật, xóa được) |

Kết quả: cả firmware biên dịch, 0 lỗi, 0 cảnh báo, không sửa dòng mã nào, với Arduino-ESP32 2.0.17 (`platformio.ini`,
nay khóa `platform = espressif32 @ 7.1.3`) và 3.3.12; mỗi bản cả PWM tắt lẫn bật với chân giả. Tìm ra một lỗi trong chú
thích: với 3.x qua PlatformIO phải GIỮ cờ `-Wl,--wrap=esp_panic_handler`, không thì móc panic không bao giờ chạy. Đã sửa
chú thích `main.cpp`, `platformio.ini`, README firmware. Chi tiết: [README firmware](../firmware/esp32_vehicle/README.md)
mục "Biên dịch cho ESP32-S3"; bằng chứng: [firmware_esp32_20260929.txt](evidence/chuyen_may_20260929/firmware_esp32_20260929.txt).
Chưa nạp, chưa chạy trên bo nào (chưa có bo).

Ổ D sau đợt này: ≈ 28 GB trống (trước ≈ 31 GB); `D:\xetulai\_platformio` chiếm ≈ 3,0 GB (core 2,9 GB; phần pioarduino
đã xóa khỏi core sau khi kiểm 3.x). Kịch bản LD-1 có `--record` đòi ≥ 30 GB (mục 4): nay thiếu ≈ 2 GB. *(Cập nhật
30/09/2026: đọc lại bằng `Get-PSDrive` chiều 30/09/2026 (15:18 và 15:23), ổ D còn ≈ 62,6 GB; không lưu log, hồ sơ không
ghi vì sao tăng. Số này đổi theo thời gian: đọc lại ngay trước khi chạy LD-1 có `--record`
([GHI_PHAT_LAI_BAN_THU.md](GHI_PHAT_LAI_BAN_THU.md) mục 5, [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) kịch bản
LD-1).)*

Nhắc thêm cho mục 5 (lần sau đổi máy): cài PlatformIO rồi `pio run -e esp32s3` trong `firmware\esp32_vehicle`; ổ hệ thống
mà chật thì đặt `PLATFORMIO_CORE_DIR` sang ổ khác trước lần chạy đầu.

## 8. Bo ảo QEMU, số test, dọn ổ C (30/09/2026)

Ngày 30/09/2026 người dùng yêu cầu làm cả ba việc: ghi kết quả khảo sát mô phỏng thành tài liệu có bằng chứng, đưa bo
ảo QEMU vào repo (kèm sửa `SerialVehicleIO` qua `socket://` và chú thích watchdog), dọn ổ C. Phần kỹ thuật ở
[MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md); mục này ghi phần gắn với máy.

**Cài thêm, đều trên ổ D ngoài repo** (bảng đủ ở [MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md) mục 6): QEMU của Espressif
9.2.2 ở `D:\xetulai\_platformio\qemu`, fork a159x36 ở `a159_qemu`, bản sao các lượt thử ở `kiem_*`, mã nguồn các bản thử
giữ lại ở `giu_lai`. Đường dẫn QEMU và PlatformIO nằm trong `configs/thiet_bi.json` (khóa `qemu_xtensa`,
`platformio_python`, `platformio_core_dir`; mục 5 bước 3). `platformio.ini` có thêm env `esp32s3_qemu`, chỉ dùng cho bo
ảo, không nạp vào xe.

**Toàn bộ bộ test** (máy bàn, 30/09/2026, offscreen, chạy từ shell của tác tử nên tiến trình không có cửa sổ). Mã:
`b37e9ee` cộng sửa đổi chưa commit tính tới 10:21 (mục 6–7, bo ảo QEMU, sửa `SerialVehicleIO`). Tức là CHƯA có các
thay đổi lúc 11:53–11:59 ở dưới: `autopark/power_throttling.py`, `tests/conftest.py` tắt EcoQoS, 4 test mới,
`QemuBoard` dùng hàm chung, `tmp_path_retention_policy`. Lượt chạy trên commit có các thay đổi đó (`ebbec83`, 0 hỏng):
cuối mục này.

| Lượt (giờ bắt đầu) | Kết quả | Thời gian | Tệp |
|---|---|---|---|
| `.venv` (10:21) | **1376 đạt, 8 bỏ qua** (cần torch), 0 hỏng | 451 s | [pytest_venv_30092026.xml](evidence/mo_phong_20260930/pytest_venv_30092026.xml) |
| `.venv-train` lượt 1 (10:29) | 1437 đạt, **1 hỏng**: `uturn_w46` | 561 s | [pytest_venv_train_30092026.xml](evidence/mo_phong_20260930/pytest_venv_train_30092026.xml) |
| `.venv-train` lượt 2 (10:40) | 1437 đạt, **1 hỏng**: `uturn_w46` | 539 s | [pytest_venv_train_30092026_lan2.xml](evidence/mo_phong_20260930/pytest_venv_train_30092026_lan2.xml) |

Mỗi môi trường có thêm đúng 20 test so với lượt ở mục 6: 13 test của `tests/test_firmware_qemu.py` (ở cả ba lượt cả 13
đều chạy, không bỏ qua; 6 trong đó chạy firmware thật trong QEMU) và 7 test mới của
`tests/test_transport_vehicle_io.py`. Trong các lượt này máy còn chạy việc khác (một crawler 12 luồng từ 10:25).

**Vì sao `uturn_w46` hỏng** (`tests/test_planner_hard_cases.py`, dấu `planner_budget`, hạn 8 s; docstring ghi số đo
3,70 s ngày 08/09):
- Không do sửa đổi của đợt này. Mã lập kế hoạch không đổi so với `b37e9ee`. Test bo ảo chạy trước nó cũng không để lại
  gì: khi chạy `test_firmware_qemu.py` rồi `test_planner_hard_cases.py`, trước mỗi test lập kế hoạch không còn tiến trình
  QEMU nào, và chỉ còn luồng `MainThread`.
- Đo riêng ca này lúc 10:54–10:57, tải CPU 0–12 %. Khi để Windows tự quyết, lần gọi đầu trong mỗi tiến trình đạt (3/3,
  4,55–4,57 s), còn các lần gọi sau trong cùng tiến trình hỏng TRACKING_FAILED ở 8,00 s (5/5). Khi tiến trình tự tắt
  EcoQoS (`SetProcessInformation`, `ProcessPowerThrottling`): đạt 8/8, 3,61–3,64 s.
- Nhóm `planner_budget` (15 test), `.venv-train`, 11:23–11:28, bốn lượt xen kẽ:
  - Tiến trình pytest tự tắt EcoQoS: cả 2 lượt đạt đủ 15/15, tổng 36 s và 40 s (theo JUnit).
  - Để Windows tự quyết: cả 2 lượt có test hỏng.
    - Lượt 1 hỏng 3 test, cả ba đều TIMEOUT, tổng 103 s: `uturn_w46`, `test_khong_hoi_quy_o_cac_ca_de`,
      `test_nhat_ky_leo_thang_ghi_lai_tung_nac`.
    - Lượt 2 hỏng `uturn_w46`, tổng 55 s.
  - Ví dụ cùng một test, `test_ca_cot_chan_cua_o_giai_duoc_nhanh`: 0,99 s và 1,05 s khi tắt EcoQoS; 3,39 s và 2,06 s khi
    để Windows tự quyết.
- Vậy các test ngân sách thời gian đo cả cách Windows xếp lịch tiến trình, không chỉ thuật toán. Còn CHƯA rõ:
  - cơ chế cụ thể (dồn sang lõi E hay hạ xung);
  - vì sao lượt `.venv` lúc 10:21 thì `uturn_w46` đạt.
- CHƯA THỬ: chạy từ một cửa sổ terminal đang hiện, cách người dùng hay chạy.
- CHƯA ĐO: ứng dụng thật gọi bộ lập kế hoạch có hạn giờ trong tiến trình giao diện. Khi cửa sổ đó bị thu nhỏ hay bị
  che, Windows có thể hạ tiến trình tương tự. *(Cập nhật 02/10/2026: đã đo, mục 10. Cửa sổ thu nhỏ thì Windows hạ tốc
  tiến trình giao diện và lập đường `uturn_w46` hết hạn 8 s ở cả 4/4 lượt; bị che thì không chậm; tiến trình tự tắt
  EcoQoS thì hết.)* *(Cập nhật 02/10/2026, lần 2: vòng điều khiển 50 Hz của lần chạy trong tiến trình giao diện đã đo,
  mục 13: cửa sổ thu nhỏ làm thời gian tính mỗi bước chậm 1,73–1,76 lần, tiến trình tự tắt EcoQoS thì hết; khoảng lớn nhất
  giữa hai nhịp điều khiển 46–47 ms, không lần nào quá 0,15 s; chỉ với SIM và bo mô phỏng.)*
- Bằng chứng: [ecoqos_30092026/](evidence/mo_phong_20260930/ecoqos_30092026/) gồm `do_uturn_w46.txt`,
  `nhom_planner_budget.txt`, JUnit của từng lượt, `linger_probe.log` và các script đo.
- **Đã sửa theo quyết định của người dùng (30/09/2026, 11:53–11:59):** `tests/conftest.py` tắt EcoQoS cho tiến trình
  pytest trên Windows, dùng hàm chung `autopark/power_throttling.py`; `QemuBoard` cũng dùng hàm này thay bản riêng. Hệ
  quả: test có hạn giờ nay đo trong điều kiện "tiến trình không bị Windows hạ tốc", không còn đo đúng điều kiện chạy
  nền mặc định.
  - Muốn đo như cũ thì đặt biến môi trường `AUTOPARK_KEEP_ECOQOS=1`.
  - *(Cập nhật 02/10/2026: `tests/conftest.py` nay dùng hàm chung `apply_ecoqos_policy` của
    `autopark/power_throttling.py`, cùng quy tắc, dòng đầu báo cáo và thuộc tính JUnit. `evaluation/fault_drill.py` nay
    theo `AUTOPARK_KEEP_ECOQOS` (lỗi ẩn đã sửa): trước đó nó tắt EcoQoS cho tiến trình của mình bất kể biến này, nên lượt
    test đầy đủ với `AUTOPARK_KEEP_ECOQOS=1` chạy `fault_drill.main` trước `tests/test_power_throttling.py` thì tiến trình
    pytest đã bị tắt, và test mong `system` sẽ hỏng. Mục 10.1.)*
  - Trạng thái đọc lại sau khi đặt được ghi vào tệp JUnit (thuộc tính `ecoqos` của testsuite: `off`, `system`, `on`
    hoặc `unknown`) và vào đầu báo cáo khi chạy `-v`.
  - Test: `tests/test_power_throttling.py` (4 test). Test kiểm chính tiến trình pytest đã tắt; tiến trình con mở sau đó
    không thừa hưởng trạng thái này, nhưng tắt được theo pid.
  - Kết quả: nhóm `planner_budget` chạy bằng lệnh pytest thường từ shell của tác tử đạt 15/15 ở cả 3/3 lượt,
    29,7–30,2 s ([nhom_planner_budget.txt](evidence/mo_phong_20260930/ecoqos_30092026/nhom_planner_budget.txt),
    `planner_budget_conftest_*.xml`).

**Một lượt đầy đủ `.venv-train` thứ ba (10:57, tiến trình pytest tự tắt EcoQoS) KHÔNG dùng được:**
- Lỗi: script bọc của tác tử thiếu chặn `if __name__ == "__main__"`. Tiến trình con mà `ProcessPoolExecutor` (spawn) của
  `test_scan_odometry.py` mở ra chạy lại tệp đó, nên chạy lại cả bộ test bên trong. Test mở các tiến trình con đó hỏng.
- Tác tử dừng lượt này lúc 11:19 và xóa tệp JUnit mà một lượt lồng đã ghi.
- Kiểm lại sau đó:
  - Trong repo chỉ đổi các tệp tác tử sửa có chủ ý.
  - Ảnh flash của bo ảo không đổi (cùng SHA-256); `qemu_board kiem` đạt (58 khung tính từ lúc kết nối, gồm cả khung
    nhận lúc chờ bo ra khỏi BOOT, xem cuối mục này; QEMU khởi động 1 lần; đầu ra console, không lưu log).
- Script đã sửa: [pytest_noeco.py](evidence/mo_phong_20260930/ecoqos_30092026/pytest_noeco.py).

**Dọn ổ C**:

| Thời điểm | Ổ C còn trống | Ghi chú |
|---|---|---|
| sáng 30/09 | 16,15 GB | |
| 10:58 | 13,89 GB | |
| 11:30, ngay trước khi dọn | 7,00 GB | thêm ≈ 6,2 GB thư mục tạm của các lượt lồng ở trên |
| 11:31, sau khi dọn | **19,51 GB** | |

Đã xóa:

| Xóa | Dung lượng | Là gì |
|---|---|---|
| Nội dung thư mục tạm của phiên tác tử này (`%TEMP%\claude\d--xetulai\<phiên>\scratchpad`, 182 mục) | ≈ 2,1 GB | bản tải và bản build các trình giả lập, bản thử lớp giả, tài liệu tham khảo của đợt khảo sát. Phần cần giữ đã chép sang `D:\xetulai\_platformio\giu_lai` và `docs/evidence/mo_phong_20260930/` trước khi xóa |
| Năm thư mục trong `%TEMP%\pytest-of-<người dùng>`: `pytest-9` (29/09), `pytest-129` (lượt đầy đủ bị dừng), `pytest-131`–`133` (các lượt lồng) | ≈ 10,4 GB | thư mục `tmp_path` của các lượt test autopark. Cả năm còn tệp `.lock` của tiến trình đã chết, nên pytest giữ chúng 3 ngày chứ không tự xóa |

Trước thay đổi ở cuối mục này, mỗi lượt `.venv-train` để lại ≈ 2,1 GB trong thư mục tạm của pytest. Trong đó ≈ 1 GB là
ba thư mục của `test_labels.py::test_a_frozen_session_keeps_its_split_when_its_frozen_images_are_no_longer_reviewed`.
Mặc định pytest giữ thư mục của 3 lượt gần nhất.

`%TEMP%\pytest-of-<người dùng>` dùng chung cho mọi lượt pytest của tài khoản Windows này, kể cả của phiên tác tử của dự
án khác. Vì vậy không xóa cả thư mục khi có thể có pytest khác đang chạy.

Không đụng tới:
- thư mục tạm của phiên tác tử của một dự án khác trên máy, vì tiến trình của dự án đó đang dùng nó;
- ba thư mục pytest nhỏ mới nhất, để pytest tự xoay vòng;
- WSL: esp-emulator chạy trong WSL từ bản sao ở `/tmp`, và kiểm 30/09 thì bản sao đó đã không còn;
- bộ nhớ đệm pip, vì lúc kiểm nó gần như rỗng.

**Đã làm theo quyết định của người dùng (30/09/2026, 11:53–11:59):** `pyproject.toml` có
`tmp_path_retention_policy = "failed"` (pytest 9.1.1): pytest xóa thư mục `tmp_path` của mỗi test đạt ngay khi test
xong; lượt đạt hết thì xóa cả thư mục của lượt đó. Lượt có test hỏng thì còn thư mục của test hỏng và của các fixture
dùng chung (`tmp_path_factory`). Đã thử với một tệp test tạm ngoài repo (một test đạt, một test hỏng; rồi một lượt đạt
hết).

Thư mục của test đạt không còn để xem lại sau lượt chạy. Cần giữ thì chạy thêm `-o tmp_path_retention_policy=all`.

**Chạy lại trên commit `ebbec83`** (mã có đủ các thay đổi 11:53–11:59 và các sửa theo review trước khi commit; cây
làm việc sạch, cùng máy, 30/09/2026 13:47–14:02, offscreen, từ shell của tác tử). Script:
[chay_tren_commit.py](evidence/mo_phong_20260930/chay_tren_commit.py); tóm tắt:
[chay_tren_commit_ebbec83.txt](evidence/mo_phong_20260930/chay_tren_commit_ebbec83.txt).

| Lượt (giờ bắt đầu, tải CPU) | Kết quả | Thời gian | Tệp |
|---|---|---|---|
| `.venv` (13:49, 3 %) | **1380 đạt, 8 bỏ qua** (cần torch, như trước), 0 hỏng | 365 s | [pytest_venv_ebbec83.xml](evidence/mo_phong_20260930/pytest_venv_ebbec83.xml) |
| `.venv-train` (13:55, 5 %) | **1442 đạt**, 0 bỏ qua, 0 hỏng (kể cả `uturn_w46`) | 400 s | [pytest_venv_train_ebbec83.xml](evidence/mo_phong_20260930/pytest_venv_train_ebbec83.xml) |

- Cả hai tệp JUnit ghi `ecoqos=off`.
- Mỗi môi trường có thêm đúng 4 test so với các lượt 10:21–10:40, là 4 test của `tests/test_power_throttling.py`.
- Thời gian ngắn hơn các lượt buổi sáng (451 s; 539–561 s). Tuy vậy, buổi sáng máy còn chạy việc khác, và EcoQoS lúc
  đó do Windows tự quyết, nên không tách được phần nào do yếu tố nào.
- Bo ảo trên cùng commit:
  - `kiem` đạt: 55 khung tính từ lúc kết nối (≈ 16 khung chờ bo ra khỏi BOOT + ≈ 39 khung trong 2 s), QEMU khởi động 1
    lần ([kiem_bo_ao_ebbec83.txt](evidence/mo_phong_20260930/bo_ao_30092026/kiem_bo_ao_ebbec83.txt)). Bản `kiem` lúc đó
    đếm gộp cả khung nhận trong lúc kết nối và chờ bo ra khỏi BOOT, nên tệp ghi "55 khung trong 2 s". Bản đếm tách
    riêng (≈ 15:00 cùng ngày, mã `ff4a018` + sửa cách đếm, chưa commit lúc chạy) cho 40 và 39 khung trong 2 s (≈ 20 Hz),
    cộng 16 khung trước đó
    ([kiem_bo_ao_dem_rieng.txt](evidence/mo_phong_20260930/bo_ao_30092026/kiem_bo_ao_dem_rieng.txt);
    [MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md) mục 1).
  - Chạy lặp `tests/test_firmware_qemu.py` 10 lượt: 10/10 lượt đạt cả 13 test (6 trong đó chạy firmware thật trong
    QEMU), không có cảnh báo #175 hay LOOP_OVERRUN
    ([chay_lap_test_bo_ao_ebbec83.txt](evidence/mo_phong_20260930/bo_ao_30092026/chay_lap_test_bo_ao_ebbec83.txt)).

## 9. Đợt biên tập tài liệu, chạy lại trên commit `c03ff94` (01/10/2026)

Commit `c03ff94` (01/10/2026, đã push lên `origin/main`) gồm đợt viết lại tài liệu ngày 30/09/2026 sau hai vòng kiểm
lại các chỗ sửa, cùng các sửa chữ trong mã (docstring, chú thích, một tooltip, mô tả gói; không đổi hành vi) và cách
đếm khung của `python -m autopark.transport.qemu_board kiem` ([mục lục kỹ thuật](README.md), đoạn "Các đợt biên
tập"). Mã chỉ khác `ebbec83` ở các chỗ đó, nên lượt này là kiểm lại, không có test mới.

Chạy trên commit đó, cây làm việc sạch, cùng máy, 01/10/2026 19:07–19:21, offscreen, từ shell của tác tử, bằng bản sửa của
script ở mục 8 (ngày lấy lúc chạy, thư mục kết quả là tham số):
[chay_tren_commit.py](evidence/bien_tap_20261001/chay_tren_commit.py); tóm tắt:
[chay_tren_commit_c03ff94.txt](evidence/bien_tap_20261001/chay_tren_commit_c03ff94.txt).

| Lượt (giờ bắt đầu, tải CPU) | Kết quả | Thời gian | Tệp |
|---|---|---|---|
| `.venv` (19:09, 2 %) | **1380 đạt, 8 bỏ qua** (cần torch), 0 hỏng | 349 s | [pytest_venv_c03ff94.xml](evidence/bien_tap_20261001/pytest_venv_c03ff94.xml) |
| `.venv-train` (19:15, 2 %) | **1442 đạt**, 0 bỏ qua, 0 hỏng | 370 s | [pytest_venv_train_c03ff94.xml](evidence/bien_tap_20261001/pytest_venv_train_c03ff94.xml) |

- Cả hai tệp JUnit ghi `ecoqos=off`. Số test trùng lượt trên `ebbec83` (mục 8).
- Bo ảo trên cùng commit, lần đầu chạy cách đếm khung tách riêng trên mã đã commit: `kiem` đạt, 39 khung
  trong 2 s (≈ 19,5 Hz), cộng 16 khung nhận trước đó lúc kết nối và chờ bo ra khỏi BOOT, QEMU khởi động
  1 lần ([kiem_bo_ao_c03ff94.txt](evidence/bien_tap_20261001/kiem_bo_ao_c03ff94.txt)).
- Chạy lặp `tests/test_firmware_qemu.py` 10 lượt (19:07–19:09): 10/10 lượt đạt cả 13 test (6 trong đó
  chạy firmware thật trong QEMU), không có cảnh báo #175 hay LOOP_OVERRUN
  ([chay_lap_test_bo_ao_c03ff94.txt](evidence/bien_tap_20261001/chay_lap_test_bo_ao_c03ff94.txt)).
- Chạy được trong bo ảo không chứng minh gì về bo thật ([MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md) mục 1).

## 10. Đo EcoQoS của ứng dụng giao diện (02/10/2026)

Đo câu "CHƯA ĐO" ở mục 8: bộ lập đường có hạn 8 s chạy trong tiến trình giao diện; cửa sổ bị thu nhỏ hay bị che thì
Windows có hạ tốc tiến trình đó không. Công cụ: `python -X utf8 -m autopark.evaluation.ecoqos_gui do` (thêm 02/10/2026,
[hướng dẫn chạy](../README.md) mục 4). Công cụ mở giao diện thật (không offscreen), đặt cửa sổ thường, thu nhỏ hoặc bị
một màn che kín, rồi gọi lập đường ca `uturn_w46` như nút "Tìm đường đỗ". Hai đối chứng: cùng giao diện nhưng tiến
trình tự tắt EcoQoS (`gui_off`), và tiến trình không cửa sổ (`khong_cua_so`). Mỗi lượt ghi thời gian, kết quả, tải nền,
phần CPU bận thêm rơi vào lõi E (chỉ báo, bộ đếm toàn máy) và cửa sổ nào ở trước.

Điều kiện: máy bàn hiện tại (i9-14900, 32 bộ xử lý logic, lõi E là LP 16–31), Windows 11 26200, kế hoạch nguồn High
performance, cắm điện; ở cả hai lần đo, 42/42 lượt có phiên Windows không khóa và màn hình bật, không ai dùng máy. Mã:
commit `3148014` cộng các sửa đổi chưa commit của đợt công cụ nghiệm thu (các sửa đổi đó nay ở commit `d3e1555`,
mục 11). Chạy từ shell của tác tử.

| Lần đo | Kết quả | Bằng chứng |
|---|---|---|
| Lần 1 (02:54–03:00) | Không đủ để kết luận: 15/16 lượt "thu nhỏ" và "bị che" bị loại vì cửa sổ giao diện vẫn ở trước (khóa cửa sổ ở trước của Windows chặn tiến trình đo đưa cửa sổ khác ra trước). Lượt hợp lệ duy nhất (thu nhỏ, để Windows tự quyết): TRACKING_FAILED ở 8,00 s, 79 % phần CPU bận thêm trên lõi E | [ecoqos_giao_dien_02102026/](evidence/ecoqos_giao_dien_02102026/) |
| Lần 2 (03:40–03:46), sau khi sửa cách đưa cửa sổ ra trước: cửa sổ đang ở trước cấp quyền `AllowSetForegroundWindow`; "thu nhỏ" là giao diện thu nhỏ trong khi một cửa sổ trung tính nhỏ của công cụ ở trước | Mọi lần đổi trạng thái kiểm lại được (28/28); bảng dưới | [ecoqos_giao_dien_02102026_lan2/](evidence/ecoqos_giao_dien_02102026_lan2/) |

Lần 2, chỉ lượt hợp lệ (thời gian: trung vị, giây, từ lúc bấm tới khi bộ lập kế hoạch trả về; tải nền 0,5–5,3 %):

| Biến thể | Thường | Thu nhỏ | Bị che |
|---|---|---|---|
| Để Windows tự quyết EcoQoS (`gui_system`) | 4/4 OK, 3,60 s | **0/4 OK: TRACKING_FAILED ở 8,00 s**, 100 % phần CPU bận thêm trên lõi E | 4/4 OK, 3,62 s |
| Giao diện tự tắt EcoQoS (`gui_off`) | 4/4 OK, 3,61 s | 4/4 OK, 3,59 s | 4/4 OK, 3,62 s |
| Tiến trình không cửa sổ (`khong_cua_so`) | 12/12 OK, 3,60 s | | |

Kết luận (`tom_tat.txt` của lần 2): cửa sổ thu nhỏ thì Windows hạ tốc tiến trình giao diện (dồn sang lõi E) và lập đường
`uturn_w46` hết hạn ở cả 4/4 lượt; tiến trình tự tắt EcoQoS thì hết (4/4 OK, cùng thời gian như cửa sổ thường); bị che
thì không chậm. Khác ngày 30/09/2026: lúc đo, tiến trình không cửa sổ KHÔNG bị hạ tốc (kế hoạch nguồn ngày 30/09 không
được ghi).

Giới hạn:
- 4 lượt hợp lệ mỗi trạng thái, một ca (`uturn_w46`), một máy, một kế hoạch nguồn (High performance); Balanced CHƯA ĐO.
- Chỉ đo lần lập đường. Vòng điều khiển 50 Hz của lần chạy khi cửa sổ bị thu nhỏ: CHƯA ĐO. *(Cập nhật 02/10/2026: đã đo
  với SIM và bo mô phỏng, mục 13.)*
- Cột `ecoqos` của bảng ghi chính sách của tiến trình (`system`), không phải "đang bị hạ"; dấu hiệu hạ tốc là phần CPU
  trên lõi E và thời gian.

CHƯA LÀM, chờ quyết định: ứng dụng tự tắt EcoQoS cho mình (gọi `disable_power_throttling()` của
`autopark/power_throttling.py` lúc khởi động `ui.app` và `ui.lidar_app`, như `tests/conftest.py`), hay giữ mặc định của
Windows và cảnh báo không thu nhỏ cửa sổ khi đang lập đường hay đang chạy. *(Cập nhật 02/10/2026: ĐÃ LÀM theo đề xuất ở
đây, người dùng giao quyết định 02/10/2026 ('làm hết'): ứng dụng và các công cụ đo tự tắt EcoQoS cho tiến trình của mình
lúc khởi động, bằng `apply_ecoqos_policy` ở câu lệnh đầu của `main()` của 27 điểm vào; `AUTOPARK_KEEP_ECOQOS=1` giữ mặc
định của Windows. Biến thể `gui_system` của công cụ đo nay đặt biến này cho tiến trình con giao diện và kiểm EcoQoS đọc
lại là `system`. Mục 10.1.)*

### 10.1. Ứng dụng và công cụ tự tắt EcoQoS (02/10/2026)

Người dùng giao quyết định 02/10/2026 ('làm hết'), theo đề xuất ở mục 10: mọi tiến trình có hành vi thời gian thực tự tắt
EcoQoS cho chính nó; `AUTOPARK_KEEP_ECOQOS=1` giữ mặc định của Windows. Không đặt ngưỡng mới nào. Mã:
`autopark/power_throttling.py` (`apply_ecoqos_policy`, `ecoqos_state`, `EcoQoSPolicy`); nhãn ở thanh trạng thái:
`autopark/ui/process_status.py`.

**Quy tắc.** `main()` gọi `apply_ecoqos_policy("<mô-đun>")` ở câu lệnh đầu, trước khi đọc dòng lệnh, khi tiến trình (a)
mở thiết bị chạy liên tục (camera, LiDAR, cổng serial, bo ảo), (b) chạy theo hạn giờ đồng hồ thật (hạn lập đường, hạn dữ
liệu cũ, vòng điều khiển), hoặc (c) ghi số đo thời gian để so với ngân sách thời gian thực (độ trễ, khung/s, Hz, ms mỗi
vòng quét). Hàm `build_window` của giao diện KHÔNG gọi: biến thể `gui_system` của `evaluation.ecoqos_gui` dựng cửa sổ qua
đó. Hàm không in gì và không ném lỗi; không tắt được thì nhãn đỏ hay dòng "CẢNH BÁO: không tắt được EcoQoS …", chương
trình vẫn chạy. Không cần quyền admin. Không đổi ưu tiên tiến trình, kế hoạch nguồn, số luồng hay tiến trình con. Tệp kết
quả chỉ ghi một khóa chuỗi `ecoqos` (`off`, `system`, `on`, `unknown`, cùng tập giá trị với thuộc tính JUnit), đọc lại lúc
ghi. Tiến trình pytest (`tests/conftest.py`) dùng cùng hàm: quy tắc, dòng đầu báo cáo và thuộc tính JUnit không đổi.

| Điểm vào (27) | Trạng thái ghi ở đâu / in gì |
|---|---|
| `ui.app` (`run_app.py`, `chay_app.cmd`), `ui.lidar_app` | nhãn ở thanh trạng thái; `manifest.json` của gói xuất (`environment.ecoqos`); `link.json` của log `VehicleIO`; ở `ui.lidar_app` thêm `meta.json` của ngăn "Ghi cảm biến" (`session_recording.ecoqos_start`, `ecoqos_stop`) |
| `ui.rig_app` | nhãn; dòng TÀI NGUYÊN của bảng số đo ("EcoQoS off"); `meta.json` của "Ghi phiên" |
| `ui.calib_app`, `ui.roi_app` | nhãn |
| `lidar.live_view` | nhãn; meta của `--record` |
| `rig.bench` | `.rig.json` → `resources.ecoqos` (và từng mẫu tài nguyên 1 Hz); dòng đầu "EcoQoS: off"; dòng "tài nguyên" của tóm tắt; `meta.json` của `--record` |
| `rig.may_moi` | `env.json`, `may_moi.json` (`digest.env.ecoqos`, `digest.rig480.ecoqos`, `digest.cam720.ecoqos`); dòng đầu bảng và một ghi chú trong `tom_tat.md`; in dòng EcoQoS sau "Các bước" |
| `video.camera_bench` | `.measure.json`, `.traps.json`, `.source.json`, json của `record`; dòng "tổng" của `measure` |
| `lidar.bench` | meta `.json` của bản ghi |
| `lidar.rplidar_c1` | không ghi, không in thêm (`rig.may_moi` đọc stdout của `info` như JSON) |
| `lidar.scan_odometry` | `odometry.json` (`ecoqos`, và `results[*].ecoqos` của tiến trình đã chạy từng việc; tiến trình con `--workers` tự tắt qua `initializer`) |
| `lidar.localize` | `localize.json` |
| `fusion.demo` | khóa `ecoqos` trong dòng JSON duy nhất ở stdout |
| `transport.qemu_board` | `kiem` in "EcoQoS: tiến trình này …, QEMU …" |
| `evaluation.bench`, `evaluation.compare` | `--json` (khóa `ecoqos`; ở `compare` đứng cạnh tên các bộ lập đường); in dòng EcoQoS |
| `evaluation.render`, `evaluation.hard_cases` | in dòng EcoQoS (tệp đường chứng không đổi) |
| `evaluation.phase0`, `evaluation.robustness` | `manifest.json` (`environment.ecoqos`); `phase0` in dòng EcoQoS |
| `evaluation.sensitivity` | `ket_qua.json`: `manifest.ecoqos`, `manifest.ecoqos_rows` (đếm theo trạng thái), `rows[*].ecoqos`; tiến trình con `--workers` tự tắt qua `initializer`; dòng đầu `bang_do_nhay.md` |
| `evaluation.fault_drill` | `<tên>.drill.json` (`ecoqos`, như trước) và dòng đầu |
| `perception.bev` | `bench.json` và dòng in của `bench` |
| `perception.export_onnx` | `export_report.json` |
| `ui.overhead_app`, `video.overhead_record` (T4) | nhãn (`ui.overhead_app`); `<tên>.json` của lần ghi video: `ecoqos` đọc lại mỗi lần ghi JSON, `ecoqos_start` lúc bắt đầu ghi, `ecoqos_policy` là chính sách áp lúc tiến trình khởi động; dòng tóm tắt cuối của `overhead_record` in EcoQoS |

**Không gọi** (29 điểm vào), kèm lý do:
- `evaluation.ecoqos_gui`: công cụ đo EcoQoS, tự đặt EcoQoS theo từng biến thể (`gui_system` phải ở mặc định của Windows).
- `evaluation.score_run`, `evaluation.dataset_audit`: ngoại tuyến.
- `evaluation.replay`: phát lại không chạy theo đồng hồ thật.
- `evaluation.acceptance_scenarios`: sinh tệp sa bàn nghiệm thu, không chạy planner.
- `evaluation.overhead_ref`: tính tham chiếu R1 từ video đã ghi (T4).
- `lidar.map_builder`, `lidar.repeatability`, `lidar.occupancy`: ngoại tuyến.
- `lidar.pose_estimator`: định vị lại một bản ghi, không theo đồng hồ thật (T2).
- `perception.aruco_sheet`: in tờ ArUco (T4).
- `ui.label_app`: gán nhãn ảnh tĩnh.
- `lidar.viewer`: chỉ xem lại bản ghi DROW.
- `perception.costmap`, `calib_board`, `fisheye_calib`, `extrinsics_calib`, `roi`, `roi_tool`, `evaluate`,
  `evaluate_external`, `labels`, `prepare`, `prepare_extra`, `verify_cache`, `predict`: ngoại tuyến.
- `perception.benchmark`, `perception.train`: việc GPU của huấn luyện, không phải ngân sách thời gian thực.
- `transport.vectors`: sinh vector thử.

Test `test_every_main_is_classified` (`tests/test_ecoqos_policy.py`) buộc mọi `main()` mới được xếp vào một trong hai
nhóm; lúc gộp đợt 2 có 56 `main()`: 27 gọi, 29 không gọi.

**Giao diện.** Nhãn cố định ở góc phải thanh trạng thái của bảy cửa sổ (`ui.app`, `ui.lidar_app`, `ui.rig_app`,
`ui.calib_app`, `ui.roi_app`, `lidar.live_view`, `ui.overhead_app`), ba dạng:
- "EcoQoS: tắt";
- chữ vàng "EcoQoS: Windows tự quyết (AUTOPARK_KEEP_ECOQOS=1)";
- chữ đỏ "EcoQoS: KHÔNG tắt được (Windows báo: …)".

Hai dạng sau kèm lời báo 15 s "… đừng thu nhỏ cửa sổ khi đang lập đường hay đang chạy". Chú thích của nhãn nói lý do và
cách giữ mặc định. Tiêu đề cửa sổ không đổi, không có hộp thoại. Bật "Efficiency mode" trong Task Manager sau khi mở ứng
dụng thì nhãn không đổi; tệp kết quả vẫn ghi đúng vì đọc lúc ghi.

**Giữ mặc định của Windows** (chỉ để đo đúng điều kiện đó): đặt biến trước khi chạy ứng dụng, công cụ hay pytest; chỉ đúng
giá trị `1` có tác dụng.
- cmd: `set AUTOPARK_KEEP_ECOQOS=1`
- PowerShell: `$env:AUTOPARK_KEEP_ECOQOS = "1"`

Biến này không áp vào QEMU của bo ảo: `QemuBoard(boost=True)` vẫn tắt theo pid.

**Kiểm** (02/10/2026, chỉ offscreen; mọi test đổi biến môi trường dùng lớp Win32 giả): `tests/test_ecoqos_policy.py` kiểm
hàm chung và chữ từng mức; kiểm tĩnh rằng mọi điểm vào gọi ở đầu `main()`, mọi `main()` được xếp loại, `build_window` và
các điểm vào loại trừ không gọi, chỉ `power_throttling.py` tắt cho chính tiến trình; mỗi điểm vào, với cả hai giá trị biến
môi trường, dừng ngay ở lần đọc trạng thái, trước argparse hay thiết bị; nhãn theo mức; `ui.app.main` dựng cửa sổ có nhãn;
khóa `ecoqos` trong các tệp kết quả; `initializer` của `sensitivity` và `scan_odometry`; `fault_drill` theo
`AUTOPARK_KEEP_ECOQOS=1`. Thêm test ở `tests/test_may_moi.py`; tệp ghi video của `video.overhead_record` kiểm ở
`tests/test_overhead_record.py`. Một tiến trình thật trên máy bàn đã chạy chính sách: `rig.bench` của LD-1 lần 3 in
"EcoQoS: off" và ghi `resources.ecoqos` = off (mục 12).

**CHƯA THỬ / CHƯA ĐO:**
- Cửa sổ thật của ứng dụng: CHƯA THỬ (chưa đọc trạng thái của tiến trình `run_app.py` thật từ tiến trình khác); suy ra
  từ biến thể `gui_off` ngày 02/10/2026, cùng lời gọi SetProcessInformation.
- Laptop nộp đồ án: CHƯA THỬ. Kế hoạch nguồn Balanced: CHƯA ĐO. Laptop chạy pin (giữ tiến trình khỏi lõi tiết kiệm tốn
  điện và nhiệt hơn): CHƯA ĐO.
- Vòng điều khiển 50 Hz khi cửa sổ thu nhỏ: đo ngày 02/10/2026 với SIM và bo mô phỏng (mục 13): để Windows tự quyết thì
  chậm, tắt EcoQoS thì hết; với bo theo đồng hồ tường: CHƯA ĐO. Windows 11 còn có thể bỏ qua yêu cầu độ phân giải bộ định
  thời của cửa sổ thu nhỏ hay bị che (PROCESS_POWER_THROTTLING_IGNORE_TIMER_RESOLUTION); mã chỉ tắt EXECUTION_SPEED. Lượt
  đo ở mục 13 không thấy nhịp giao diện thưa khi đã tắt EcoQoS, nên biến thể `gui_off_dh` (tắt cả phần này) không chạy.
- Số đo thời gian trước 02/10/2026 đo dưới mặc định của Windows và không ghi EcoQoS ("—"), kể cả các lệnh của lượt thiết
  bị ngày 02/10/2026 trước LD-1 lần 3 (mã `63017a5`, mục 12). Gồm: `rig.bench` 23–24/09, tham chiếu `may_moi`,
  `camera_bench`, `sensitivity`, `time_ms` của `scan_odometry`/`localize`, BEV bench. Không kết luận nhanh hơn khi chưa
  có lượt A/B.

**Nghĩa của hai biến thể của `evaluation.ecoqos_gui` từ 02/10/2026:**
- `gui_system` = giao diện ở mặc định của Windows, tức ứng dụng trước 02/10/2026 hay ứng dụng chạy với
  `AUTOPARK_KEEP_ECOQOS=1`. Tiến trình con dựng cửa sổ qua `ui.app.build_window`, không qua `main()`; công cụ đặt
  `AUTOPARK_KEEP_ECOQOS=1` cho tiến trình con này và loại khối khi EcoQoS đọc lại không phải `system` (không đọc được thì
  giữ dòng, kèm cảnh báo).
- `gui_off` = ứng dụng từ 02/10/2026: cùng lời gọi mà ứng dụng nay tự làm cho mình (công cụ tắt theo pid).

## 11. Đợt công cụ nghiệm thu, chạy lại trên commit `d3e1555` (02/10/2026)

Commit `d3e1555` (02/10/2026, đã push lên `origin/main`) gồm các công cụ nghiệm thu T5, T6, T9–T15
([kịch bản nghiệm thu](KICH_BAN_NGHIEM_THU.md) mục 7), công cụ và kết quả đo EcoQoS của giao diện (mục 10) cùng tài
liệu. Bộ test có thêm 265 test so với lượt trên `c03ff94` (mục 9): đó là test của các công cụ mới.

Chạy trên commit đó, cây làm việc sạch, cùng máy, 02/10/2026 13:46–14:04, offscreen, từ shell của tác tử, bằng bản sửa của
script ở mục 9: [chay_tren_commit.py](evidence/cong_cu_20261002/chay_tren_commit.py); tóm tắt:
[chay_tren_commit_d3e1555.txt](evidence/cong_cu_20261002/chay_tren_commit_d3e1555.txt).

| Lượt (giờ bắt đầu, tải CPU) | Kết quả | Thời gian | Tệp |
|---|---|---|---|
| `.venv` (13:48, 7 %) | **1645 đạt, 8 bỏ qua** (cần torch), 0 hỏng | 469 s | [pytest_venv_d3e1555.xml](evidence/cong_cu_20261002/pytest_venv_d3e1555.xml) |
| `.venv-train` (13:55, 10 %) | **1707 đạt**, 0 bỏ qua, 0 hỏng | 483 s | [pytest_venv_train_d3e1555.xml](evidence/cong_cu_20261002/pytest_venv_train_d3e1555.xml) |

- Cả hai tệp JUnit ghi `ecoqos=off`. Thời gian dài hơn lượt trên `c03ff94` (349 s, 370 s): bộ test lớn hơn, và trong
  lúc chạy máy còn có các tác tử thiết kế đợt sau đọc mã (tải CPU lúc bắt đầu ghi trong bảng).
- Bo ảo trên cùng commit: `kiem` đạt, 39 khung trong 2 s (≈ 19,5 Hz), cộng 18 khung nhận trước đó
  lúc kết nối và chờ bo ra khỏi BOOT, QEMU khởi động 1 lần
  ([kiem_bo_ao_d3e1555.txt](evidence/cong_cu_20261002/kiem_bo_ao_d3e1555.txt)). Chạy lặp `tests/test_firmware_qemu.py` 10 lượt
  (13:46–13:48): 10/10 lượt đạt cả 13 test (6 trong đó chạy firmware thật trong QEMU), lượt 6 có 2 cảnh báo QEMU tự thoát lúc khởi động (#175), `QemuBoard` khởi động lại và lượt vẫn đạt; không có LOOP_OVERRUN
  ([chay_lap_test_bo_ao_d3e1555.txt](evidence/cong_cu_20261002/chay_lap_test_bo_ao_d3e1555.txt)).
- Các công cụ mới chưa chạy với thiết bị thật; chạy được trong bo ảo không chứng minh gì về bo thật
  ([MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md) mục 1).

## 12. Lượt chạy thiết bị ngày 02/10/2026 và lỗi xả bộ đệm cổng LiDAR

Máy bàn, 02/10/2026 14:08–17:54, không ai ở cạnh thiết bị. Người dùng giao quyết định 02/10/2026 ('làm hết'), theo đề
xuất: được chạy LiDAR và camera khi không có người trông; ảnh cảnh sa bàn chỉ lưu cục bộ trong `runs/` (git bỏ qua),
không commit. Lệnh chạy bằng các script trong thư mục bằng chứng, từ thư mục `autopark` của repo; cổng LiDAR lấy từ
`configs/thiet_bi.json` (COM3).

Bằng chứng: [evidence/thiet_bi_20261002/](evidence/thiet_bi_20261002/):
- nhật ký `nhat_ky.txt`; lệnh `chay.sh`, `ld1_lan2.sh`, `ld1_lan3.sh`; theo dõi bộ nhớ và ổ đĩa mỗi 10 s `theo_doi.ps1`;
- đầu ra `camera_list.txt`, `camera_measure.txt`, `m_4cam_480p_auto.measure.json`, `fusion_demo.txt`, `ld1_thu_ghi.txt`;
  đầu ra rút gọn của LD-1 `ld1_rut_gon.txt`, `ld1_lan2_rut_gon.txt`, `ld1_lan3_rut_gon.txt` (giữ 6 dòng trạng thái đầu và
  6 dòng cuối); tóm tắt `*.tom_tat.json` (rút từ `.rig.json`, bỏ chuỗi theo thời gian);
- chẩn đoán LiDAR `chan_doan_lidar.txt` và ba script thử `thu_purge.py`, `thu_lidar_ket.py`, `thu_flush.py`.

Bản ghi phiên, `.rig.json` đầy đủ, đầu ra gốc và tệp theo dõi `theo_doi_ld1_lan2.csv`, `theo_doi_ld1_lan3.csv` nằm ở
`runs/` (git bỏ qua).

Mã: các lệnh từ 14:08 tới 17:00 chạy trên cây chính ở commit `63017a5`, tức trước đợt 2: `rig.bench` chưa tự tắt EcoQoS,
driver C1 chưa có bản sửa ở mục 12.2. LD-1 lần 3 chạy trên cây gộp đợt 2 (`63017a5` cộng các thay đổi chưa commit), có
bản sửa đó *(các thay đổi đó, cùng các sửa sau đó, nay ở commit `470abb3`, mục 15)*.
`camera_bench` và `fusion.demo` chạy bằng `.venv`; `rig.bench` bằng `.venv-train`.

### 12.1. Các lượt chạy

| Giờ | Việc | Kết quả |
|---|---|---|
| 14:08 | `video.camera_bench list` | 4 camera; cổng hub → index OpenCV: 1 → 0, 2 → 2, 3 → 1, 4 → 3 |
| 14:09 | `camera_bench measure`, bốn camera 640×480, 60 s | mỗi camera 23,8 khung/s thật; 0 khung bị cắt, xé, cũ hay đọc hỏng; khoảng giữa hai khung mới trung vị 48 ms, p95 48–49 ms, lớn nhất 55–62 ms; `read()` 47 ms; tổng 95,4 khung/s; CPU tiến trình 0,21 lõi |
| 14:09 | `fusion.demo --seconds 30 --warmup 4.5`, C1 thật | COMPLETED; 166 vòng, 0 lỗi đọc; bỏ 23 vòng khởi động mô-tơ (vòng nền đầu ở 4,55 s); nền từ 10 vòng, 500–512 tia mỗi vòng; 18 vật có sẵn; 4 vật mới ngoài đường đi (không dừng); không va chạm |
| 14:09–14:11 | `rig.bench` ghi thử 60 s (`--record`) | 5,31 MB/s (5865 khung, 318,49 MB; LiDAR 601 vòng, 10,014 Hz, 0 lỗi); ước LD-1 30 phút ≈ 11,7 GB (đã cộng 25 %) |
| 14:11–14:29 | LD-1 lần 1: `rig.bench --ports 1 2 3 4 --lidar --seconds 1800 --record …` | tiến trình CHẾT ở t ≈ 1050 s, mã thoát 127, không traceback, không có `.rig.json` *(Cập nhật 06/10/2026: bị một phiên tác tử Claude khác trên cùng máy (dự án khác) dừng bằng `Stop-Process -Force`; mã Windows là 0xFFFFFFFF (mã của `Stop-Process -Force`; mã 32 bit của lượt 02/10 không được ghi), Git Bash báo 127; kiểm trên máy tính, mục 16.3)* |
| 16:29–17:00 | LD-1 lần 2: cùng lệnh, theo dõi bộ nhớ và ổ đĩa mỗi 10 s | chạy đủ 1800 s; LiDAR 0 vòng, 8151 lỗi "bad response descriptor"; mã thoát 1 |
| 17:23–17:54 | LD-1 lần 3: cùng lệnh, cây gộp đợt 2, driver C1 đã sửa | chạy đủ 1800 s, mã thoát 0, 0 lỗi LiDAR; số đo ở bảng dưới |

**LD-1 lần 1.** Tới t = 1050 s (12 dòng trạng thái 5 s giữ lại trong `ld1_rut_gon.txt`): cổng 2 29,2–29,5 khung/s, ba cổng
kia 23,7–24,0 khung/s; LiDAR 10,0 Hz; AI 23,6–23,9 bộ/s; đã ghi 105 329 khung, bỏ 0. Không có sự kiện nào trong
Application/System log 14:15–14:40; ổ D còn 55,8 GB lúc 14:29; chỗ trống ổ C lúc đó không ghi. Nguyên nhân CHƯA RÕ: 127 là
byte thấp của mã thoát Windows; giả thuyết STATUS_DISK_FULL (0xC000007F) CHƯA KIỂM. RAM tiến trình ở lần 2 và 3 ổn định
≈ 1,57 GB và cả hai chạy đủ 30 phút. `theo_doi.ps1` (bộ nhớ của mọi tiến trình python, chỗ trống ổ C và D, bộ nhớ cam kết
còn trống, mỗi 10 s) đã chạy ở lần 2, 3 và dùng lại được. Tiến trình chết khi C1 đang quét, không gửi STOP; đó là gốc lỗi
của lần 2 (mục 12.2).
*(Cập nhật 06/10/2026: nguyên nhân đã rõ, kiểm trên máy tính. Lúc 14:29:12 một phiên tác tử Claude khác trên cùng máy
(dự án khác) chạy `Stop-Process -Id 26456 -Force`, tưởng đó là tiến trình treo của chính nó; 26456 là python gốc của
`rig.bench` theo loại trừ trên hai bảng tiến trình mà phiên đó in lúc 14:25 và 14:29 (phía autopark không ghi PID). Câu
"127 là byte thấp của mã thoát Windows" SAI: Git Bash báo 127 cho mọi mã ≥ 0xC0000000 trừ bốn mã, kể cả mã 0xFFFFFFFF
của `Stop-Process -Force`; giả thuyết STATUS_DISK_FULL bị bác. Log Application/System trống đúng như dự kiến khi bị
dừng bằng TerminateProcess (dừng từ ngoài không sinh sự kiện WER, kể cả với ErrorMode 0x8001:
[thu_dau_cuoi/](evidence/su_co_thoat_20261006/thu_dau_cuoi/)). Vì tiến trình mở từ Git Bash (ErrorMode 0x3), log
trống cũng không loại được một crash. Mục 16.)*

**LD-1 lần 2** (máy có việc khác: tải CPU 76 % lúc bắt đầu, GPU dùng chung với một ứng dụng Omniverse lúc đầu, nhiệt GPU
tới 80 °C): bốn camera 23,77–25,79 khung/s TB, 0 khung cắt, xé, cũ hay đọc hỏng, nhưng khoảng dài nhất không có khung tốt
609–649 ms ở cả bốn camera; 32 431 bộ ảnh, độ lệch trung vị 18,8 / p95 32,5 / lớn nhất 293,7 ms; AI 18,0 bộ/s TB, một lô
trung vị 23,3 / p95 44,4 / lớn nhất 1026 ms; ghi 175 800 khung, 8344 MB, 4,64 MB/s, bỏ 0; RAM tiến trình ≈ 1,57 GB; LiDAR 0
vòng, 8151 lỗi "ProtocolError: bad response descriptor 0112f57ffc8bc6", mã thoát 1. Vì tải máy, số camera và AI của lần
này không dùng để so.

**LD-1 lần 3** (17:23–17:54; tải CPU 30 % lúc bắt đầu, 12 % lúc xong; ổ D 46,9 GB trước, 38,5 GB sau; lệnh
[ld1_lan3.sh](evidence/thiet_bi_20261002/ld1_lan3.sh), có `--checkpoint` trỏ mô hình AI tham chiếu):

| Đại lượng | Số đo (`ld1_lan3_rut_gon.txt`, `ld1_lan3.tom_tat.json`) |
|---|---|
| Bốn camera | mỗi camera 23,85 khung/s TB; 0 khung cũ, cắt, xé hay đọc hỏng; khoảng dài nhất không có khung tốt 87–118 ms |
| Bộ ảnh | 42 751 bộ, 0 bỏ vì lệch, 0 thiếu camera; độ lệch trung vị 25,1 / p95 31,7 / lớn nhất 54,1 ms |
| LiDAR | 18 015 vòng, 10,008 Hz TB, 0 lỗi, khoảng dài nhất 176,5 ms |
| AI | 23,75 bộ/s TB; một lô trung vị 25,3 / p95 39,7 / lớn nhất 202,3 ms; tuổi kết quả so với khung cũ nhất trung vị 51,3 ms, p95 74,9 ms |
| Tài nguyên | CPU tiến trình 1,21 lõi (lớn nhất 2,56), CPU máy 35,4 %; RAM 1,57 GB; GPU 62,6 % (VRAM 7,26 GB, có tiến trình khác dùng GPU); nhiệt GPU lớn nhất 79 °C; EcoQoS off (tiến trình tự tắt) |
| Ghi phiên | 171 702 khung JPEG, LiDAR 18 015 vòng, 7995 MB, 4,44 MB/s, bỏ 0 |

**Chưa kiểm ở lượt này** (không phải lượt nghiệm thu LD-1):
- Đây là máy bàn, không phải laptop nộp đồ án; LD-1 trên laptop RTX 3050 Ti: CHƯA ĐO.
- Không ai ở cạnh: camera nhìn gì không ai kiểm, nên điều kiện "camera nhìn sa bàn thật" của LD-1 CHƯA KIỂM; máy không
  khởi động lại, nên "camera đúng hướng sau mỗi lần khởi động lại" (N-C5) CHƯA KIỂM.
- Không có LED đo trễ sự kiện → khung (N-C4): dụng cụ CHƯA CÓ.
- Ngưỡng của LD-1 (N-C1 … N-C5, N-T3 … N-T6, N-T8) vẫn ĐỀ XUẤT – CHỜ CHỐT; lượt này không chấm theo ngưỡng.
- Nguyên nhân mã thoát 127 của lần 1: CHƯA RÕ. *(Cập nhật 06/10/2026: đã rõ, kiểm trên máy tính — bị một phiên tác tử
  Claude khác trên cùng máy dừng bằng `Stop-Process -Force`; mục 16.3.)*
- Việc cần người ở cạnh thiết bị, xếp theo thứ tự nên làm: [VIEC_TAI_CHO_THIET_BI.md](VIEC_TAI_CHO_THIET_BI.md).

### 12.2. Lỗi xả bộ đệm cổng LiDAR và bản sửa driver C1

**Đo** (`thu_purge.py`, [chan_doan_lidar.txt](evidence/thiet_bi_20261002/chan_doan_lidar.txt)): trên cổng CP210x của máy
bàn (COM3, Silicon Labs, VID:PID 10C4:EA60), `reset_input_buffer()` (PurgeComm) KHÔNG xóa byte nào. Với ba câu trả lời
GET_INFO chưa đọc: 81 byte trước và 81 byte sau khi gọi; khi đang quét: 23 303 byte trước và sau.

**Hệ quả 1: C1 bị bỏ lại đang quét.** LD-1 lần 1 chết khi C1 đang quét, không gửi STOP. Từ đó mọi lần `start()` trong CÙNG
một cổng đều hỏng: mỗi lần driver chỉ đọc 7 byte làm mô tả trả lời, rơi vào giữa một câu trả lời cũ, còn phần ứ tăng thêm
20 byte mỗi lần (GET_INFO trả 27 byte). Luồng LiDAR của `rig.bench` thử lại mỗi 0,2 s trên cùng cổng suốt 30 phút, nên
LD-1 lần 2 có 8151 lỗi. Làm lại được (`chan_doan_lidar.txt` mục 3, 5): giết một tiến trình `rplidar_c1 stream` đang quét
rồi chạy lại ngay thì hỏng "bad response descriptor"; với `thu_lidar_ket.py`, thử lại trong cùng cổng 10 lần không hồi
phục; đóng rồi mở lại cổng, hay RESET một lần sau lần hỏng đầu, thì `start()` đạt.

**Hệ quả 2: `flush()` không xả gì.** `fusion.demo` gọi `flush()` của driver sau khi lập đường để bỏ phần ứ; trên máy này,
trước bản sửa, nó không xả được gì, nên vòng cũ mang stamp mới. Lượt `fusion.demo` lúc 14:09 ở mục 12.1 chạy bằng driver
cũ.

**Sửa** (`autopark/lidar/rplidar_c1.py`): `_discard_input` ĐỌC BỎ byte cũ: sau STOP, đọc tới khi cổng im 0,05 s (tối đa
1,5 s); trước mỗi lệnh hỏi, trước SCAN và trong `flush()`, đọc phần đang chờ lúc gọi. Lệnh hỏi info/health hỏng thì RESET
một lần rồi hỏi lại. Bỏ vòng đầu tiên sau `flush()` (cắt giữa một nút cho một "vòng" giả 4 tia trên C1 thật). `stats()`
có thêm `discarded_bytes`, `skipped_after_flush`. Test: `tests/test_lidar_protocol.py` (cổng giả mà PurgeComm không xóa
gì).

**Thử trên C1 thật** (02/10/2026, trước LD-1 lần 3): giết tiến trình đang quét rồi mở lại: đạt 2/2, đọc bỏ 58 và 60 byte,
không cần RESET. `flush()` (`thu_flush.py`) sau 0,5 s và 1,0 s không đọc: bỏ 12 736 và 25 536 byte đang chờ trong
0,1–0,2 ms, vòng kế đủ 452 và 516 tia. LD-1 lần 3: 0 lỗi LiDAR trong 30 phút.

**Chưa thử:** cổng USB CDC của bo ESP32-S3 (chưa có bo); `SerialVehicleIO` không gọi `reset_input_buffer`.

### 12.3. Kiểm tĩnh nguồn tư thế LiDAR (T2) trên C1 thật

21:00, cây chính đã có mã đợt 2 (chưa commit lúc đó; nay là commit `470abb3`, mục 15), driver C1 đã sửa; C1 đứng
yên trên bàn, nhìn phòng (chưa có sa bàn thật); không ai ở cạnh. Lệnh và số trong
[t2_kiem_tinh.tom_tat.json](evidence/thiet_bi_20261002/t2_kiem_tinh.tom_tat.json):
`lidar.bench record` 20 s (bản đồ) rồi 30 s (kiểm), cùng chỗ; `lidar.map_builder --anchor 0 0 0` (một chỗ đặt: ok,
session_ready); `lidar.pose_estimator --sensor-frame --initial 0 0 0` trên bản ghi kiểm.

| Đại lượng | Kết quả |
|---|---|
| Vòng quét | 271: 2 INIT, 269 OK, 0 dừng (POSE_LOST, POSE_DISAGREE, POSE_UNCHECKED: 0) |
| Tư thế cảm biến các vòng OK, dao động (max − min) | x 2,99 mm, y 2,64 mm, hướng 0,06° |
| Độ lệch chuẩn | x 0,52 mm, y 0,46 mm, hướng 0,01° |
| Kiểm chéo (b) − (a), dao động | 13,9 mm, 20,5 mm, 0,81° (độ lệch chuẩn 2,6 mm, 3,1 mm, 0,16°) |
| Thời gian một vòng | (a) trung vị 26,4 ms, p95 31,8 ms; (b) trung vị 17,1 ms, p95 22,2 ms (máy đang chạy bộ test) |

Giới hạn: bản đồ và bản kiểm cùng một chỗ đặt, nên đây là độ LẶP LẠI tĩnh của bộ ghép trên C1 thật, không phải độ
chính xác so với thước (DV-1) hay so với tham chiếu độc lập; chưa có sa bàn thật, chưa có gá trên xe, chưa qua
`ui.lidar_app` (định vị trong phiên). Bo thật ở VehicleIO vẫn bị từ chối (START_POSE_UNVERIFIED) tới khi đủ điều kiện
tiên quyết ([NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md) mục 6).

## 13. Đo vòng điều khiển 50 Hz khi cửa sổ thu nhỏ (02/10/2026)

Đo câu "CHƯA ĐO" ở mục 10 (Giới hạn). Vòng điều khiển 50 Hz chạy trong luồng giao diện: QTimer 16 ms gọi
`MainWindow._on_tick`; `real_dt` đọc từ `QElapsedTimer` theo ms nguyên, chặn 0,1 s; `Session.advance` chạy bước 5 ms, cứ
4 bước một nhịp điều khiển. Người dùng giao quyết định 02/10/2026 ('làm hết'), theo đề xuất.

**Công cụ.** `python -X utf8 -m autopark.evaluation.ecoqos_gui do-chay` (mã ở `autopark/evaluation/ecoqos_chay.py`;
[hướng dẫn chạy](../README.md) mục 4). Công cụ dùng lại cách đặt cửa sổ thường / thu nhỏ / bị che của mục 10. Mỗi lượt
bấm "Bắt đầu đỗ" (`MainWindow.run()`, hàm nút gọi) và ghi từng nhịp giao diện, từng nhịp điều khiển của một lần chạy SIM
hoặc VehicleIO với bo MÔ PHỎNG; trong lúc xe chạy, công cụ lấy mẫu trạng thái cửa sổ mỗi giây, lượt có mẫu sai bị loại.
Không cổng COM, camera, LiDAR; không sửa mã ứng dụng.

Biến thể:
- `gui_system`: tiến trình con có `AUTOPARK_KEEP_ECOQOS=1`, đọc lại EcoQoS phải là `system`; không đọc được (Windows
  trước bản 22000) thì các dòng vẫn được giữ và công cụ in CẢNH BÁO "không đọc được EcoQoS"; chế độ lập đường `do` cũng
  vậy.
- `gui_off`: tắt EcoQoS theo pid, cùng lời gọi mà ứng dụng dùng khi tự tắt.
- `gui_off_dh`: tắt EcoQoS và luôn tôn trọng độ phân giải đồng hồ của tiến trình; chỉ chạy khi `gui_off` vẫn thưa nhịp lúc
  thu nhỏ.

Mặc định: kịch bản `scenarios/bai_do_xe.json`; nhánh SIM và VEHICLE_IO (bo mô phỏng); biến thể `gui_system` và `gui_off`;
mỗi cặp (biến thể, nhánh) 2 khối, mỗi khối 1 lượt khởi động (cửa sổ thường) và 3 lượt (thường, thu nhỏ, bị che); giữ chuỗi
nhịp thô (`nhip/*.json.gz`).

Mỗi lượt ghi một dòng `ket_qua.jsonl`: khoảng giữa hai nhịp giao diện (p50/p95/p99/max), số nhịp bị chặn 0,1 s và giây
phiên mất vì chặn, phần trôi do `QElapsedTimer` trả ms nguyên, thời gian tính mỗi bước 5 ms (chỉ báo tốc độ CPU), khoảng
giữa hai nhịp điều khiển (lớn nhất, số khoảng > 0,15 s và > 0,5 s), trễ nhịp điều khiển so với lịch lý tưởng theo đồng hồ
thật, thời gian phiên / đồng hồ thật, EcoQoS và độ phân giải đồng hồ hệ thống lúc bấm, kết quả lần chạy và có giống lượt
khởi động cùng tiến trình không (SIM và bo mô phỏng chạy bước cố định nên phải giống).

*(Sửa sau rà soát 02/10/2026.)* Một lần chạy không dừng được (không có kết quả cả sau khi công cụ bấm Dừng) làm công cụ
bỏ phần còn lại của khối đó và sang khối sau. Mã thoát vẫn 0, nhưng `may.json` ghi `khoi_bo_do` (khối, biến thể, nhánh,
lần, trạng thái, số lượt bỏ) và `tom_tat.txt` có dòng CẢNH BÁO nêu lần chạy đó (kể cả khi là lượt khởi động) cùng số lượt
có dòng trên số lượt dự kiến. `khoi_tien_trinh[].chinh_sach_doi_chieu` của `may.json` là giới hạn đổi chiều có hiệu lực
lúc Bắt đầu đỗ (`Session.cusp_limit()`, gồm giới hạn của tệp sa bàn gắn nghiệm thu), không chỉ cờ dòng lệnh.

Công cụ được kiểm bằng test offscreen (`tests/test_ecoqos_chay.py` và các test thêm vào `tests/test_ecoqos_gui.py`; chạy
lại SIM và bo mô phỏng ra cùng kết quả).

**Lượt đo 02/10/2026 18:43:10–18:57:27.** Bằng chứng: [evidence/ecoqos_chay_02102026/](evidence/ecoqos_chay_02102026/)
(`tom_tat.txt`, `may.json`, `ket_qua.jsonl`, `nhat_ky.txt`, `powercfg_bo_xu_ly.txt`, kịch bản đã dùng
`kich_ban_bai_do_xe.json`, chuỗi nhịp thô `nhip/*.json.gz`).
- Lệnh `python -X utf8 -m autopark.evaluation.ecoqos_gui do-chay --ra docs/evidence/ecoqos_chay_02102026`, tham số mặc
  định, từ cây gộp đợt 2 (commit `63017a5` cộng 151 tệp chưa commit; các thay đổi đó, cùng các sửa sau đó, nay ở
  commit `470abb3`, mục 15), chạy từ shell của tác tử.
- Máy bàn (i9-14900, 32 bộ xử lý logic, lõi E là LP 16–31), Windows 11 26200, kế hoạch nguồn High performance, cắm điện,
  màn hình không tự tắt khi cắm điện. Ở cả 32 lần bấm phiên Windows mở và màn hình bật; không ai dùng máy. Tải nền
  1,7–20,3 % (một ứng dụng Omniverse của người dùng chạy cùng lúc).
- 32/32 lần chạy xong; 8 lượt khởi động bị loại khỏi phép so; 656 mẫu trạng thái cửa sổ, 0 sai; đưa cửa sổ ra trước kiểm
  lại được ở mọi lần đổi trạng thái (giao diện 16/16, cửa sổ trung tính 8/8, màn che 8/8); không khối nào bị bỏ dở.
- EcoQoS đọc lại: `gui_system` là `system` ở cả 4 khối, `gui_off` là `off` (tắt theo pid) ở cả 4 khối. Độ phân giải đồng
  hồ hệ thống lúc bấm (`gui_system`): 0,5 ms ở cả ba trạng thái cửa sổ (toàn máy, chỉ báo).
- Một lần chạy dài 20,3 s thời gian phiên ở SIM, 20,9 s ở VEHICLE_IO.

Chỉ lượt hợp lệ; mỗi ô có 2 lượt hợp lệ, ở trạng thái thường còn 2 lượt khởi động bị loại. Nhịp giao diện: trung vị các
lượt của p50 và p95, lớn nhất của max. Tính mỗi bước và phiên / thật: trung vị.

| Nhánh | Biến thể | Cửa sổ | Kết quả | Nhịp giao diện p50 / p95 / lớn nhất (ms) | Tính mỗi bước 5 ms (µs) | Khoảng lớn nhất giữa hai nhịp điều khiển (ms) | Phiên / thật |
|---|---|---|---|---|---|---|---|
| SIM | `gui_system` | thường | COMPLETED 2/2 | 16,0 / 16,5 / 17 | 240,5 | 32 | 0,977 |
| SIM | `gui_system` | thu nhỏ | COMPLETED 2/2 | 15,5 / 16,3 / 32 | 415,9 | 47 | 0,969 |
| SIM | `gui_system` | bị che | COMPLETED 2/2 | 16,0 / 16,5 / 17 | 235,2 | 32 | 0,975 |
| SIM | `gui_off` | thường | COMPLETED 2/2 | 16,0 / 16,6 / 17 | 234,2 | 32 | 0,977 |
| SIM | `gui_off` | thu nhỏ | COMPLETED 2/2 | 15,5 / 16,2 / 31 | 234,8 | 46 | 0,969 |
| SIM | `gui_off` | bị che | COMPLETED 2/2 | 16,0 / 16,6 / 17 | 242,2 | 32 | 0,975 |
| VEHICLE_IO | `gui_system` | thường | COMPLETED 2/2 | 16,0 / 16,6 / 17 | 285,7 | 32 | 0,975 |
| VEHICLE_IO | `gui_system` | thu nhỏ | COMPLETED 2/2 | 15,5 / 16,3 / 32 | 502,0 | 46 | 0,969 |
| VEHICLE_IO | `gui_system` | bị che | COMPLETED 2/2 | 16,0 / 16,6 / 17 | 297,0 | 33 | 0,974 |
| VEHICLE_IO | `gui_off` | thường | COMPLETED 2/2 | 16,0 / 16,5 / 17 | 288,8 | 33 | 0,977 |
| VEHICLE_IO | `gui_off` | thu nhỏ | COMPLETED 2/2 | 15,5 / 16,2 / 36 | 276,3 | 47 | 0,969 |
| VEHICLE_IO | `gui_off` | bị che | COMPLETED 2/2 | 16,0 / 16,5 / 17 | 290,0 | 33 | 0,976 |

Ở mọi ô: 0 khoảng giữa hai nhịp điều khiển > 0,15 s, 0,00 s phiên mất vì chặn 0,1 s, 0 nhịp `lagging`.

Kết luận của công cụ (`tom_tat.txt`; ngưỡng mô tả, không phải ngưỡng nghiệm thu; mốc là `gui_system` thường cùng nhánh):
- Thu nhỏ, để Windows tự quyết (`gui_system`): "chậm rõ" ở thời gian tính mỗi bước, hệ số 1,73 (SIM) và 1,76
  (VEHICLE_IO). Nguyên nhân là Windows hạ tốc tiến trình (EcoQoS): tắt EcoQoS (`gui_off`, cách ứng dụng làm từ 02/10/2026)
  thì hết, hệ số 1,00 và 0,96 so với `gui_off` thường.
- Bị che: không thấy chậm (hệ số 0,98 và 1,04).
- Nhịp giao diện p95 gần như không đổi (16,2–16,6 ms, hệ số 0,98–1,00). Khi thu nhỏ, khoảng lớn nhất giữa hai nhịp giao
  diện tăng từ 17 lên 31–36 ms và giữa hai nhịp điều khiển từ 32–33 lên 46–47 ms, ở cả hai biến thể (tắt EcoQoS không đổi
  điều này). Không khoảng nào giữa hai nhịp điều khiển quá 0,15 s. Mọi lần chạy COMPLETED và giống lượt khởi động cùng tiến
  trình (24/24).
- Thời gian phiên / thời gian thật 0,969–0,977: phiên chậm hơn đồng hồ thật ≈ 2,5 % (trung vị mọi lượt hợp lệ 2,52 %) vì
  `QElapsedTimer` trả ms nguyên. Trễ của nhịp điều khiển so với lịch lý tưởng theo đồng hồ thật (p95 461–654 ms) theo định
  nghĩa gồm cả phần trôi tích lũy này.
- Hệ quả cho bo theo đồng hồ tường (bo thật, bo ảo QEMU): hạn COMMAND 0,15 s và watchdog liên lạc 0,5 s (N-T10, ĐỀ XUẤT –
  CHỜ CHỐT) chưa bị chạm trong các lần đo này. Đây là SUY RA: SIM và bo mô phỏng chạy theo thời gian phiên; với bo theo
  đồng hồ tường: CHƯA ĐO.
- Khác mục 10: ở đó LẬP ĐƯỜNG khi cửa sổ thu nhỏ (planner hỏng 0/4 với `uturn_w46`); ở đây đường được lập lúc cửa sổ
  thường, chỉ lần chạy ở trạng thái thu nhỏ hay bị che.
- Biến thể `gui_off_dh` không chạy: theo luật của công cụ, nó chỉ cần khi `gui_off` vẫn thưa nhịp lúc thu nhỏ, mà lượt này
  không thấy.
- Chỉ báo (không phải phép đo trực tiếp), `gui_system`: CPU của tiến trình / thời gian thật 0,37 khi thường, 0,13 khi thu
  nhỏ, 0,38 khi bị che.

Giới hạn:
- Công cụ bấm "Bắt đầu đỗ" khi cửa sổ đã thu nhỏ hay bị che (người dùng không làm vậy được): chỉ đo trạng thái ổn định;
  người dùng thu nhỏ cửa sổ GIỮA lần chạy: CHƯA ĐO.
- SIM và bo mô phỏng chạy theo thời gian phiên, nên nhịp thưa không làm hỏng lần chạy; hệ quả với bo theo đồng hồ tường
  (bo thật, bo ảo QEMU: lệnh hết hạn sau 0,15 s, watchdog liên lạc 0,5 s) chỉ SUY RA từ khoảng nhịp đo được, CHƯA ĐO.
- Một máy (máy bàn i9-14900), kế hoạch nguồn High performance, cắm điện; Balanced và laptop nghiệm thu: CHƯA ĐO.
- Chỉ tải của giao diện với SIM hay bo mô phỏng: không camera, LiDAR, AI, ghi cảm biến (T3), luồng định vị LiDAR (T2) hay
  QEMU; nhịp 50 Hz khi có các tải đó: CHƯA ĐO. Trong lúc đo có một ứng dụng Omniverse của người dùng chạy (tải nền tới
  20,3 %).
- 2 lượt hợp lệ mỗi ô, đúng số tối thiểu để công cụ so.
- Độ phân giải đồng hồ ghi được là của toàn máy (`NtQueryTimerResolution`), không phải của riêng tiến trình giao diện.
- Cột `trang_thai_bo` (VehicleIO) là trạng thái trong khung telemetry cuối nhận được trước khi lệnh DISARM được xác nhận
  (với bo mô phỏng thường là RUNNING), không phải trạng thái sau DISARM.
- Tiến trình con dựng cửa sổ bằng `build_window`, không qua `ui.app.main()`, nên không chạy chính sách EcoQoS lúc khởi động
  của ứng dụng; biến thể `gui_off` tắt theo pid.

## 14. Ứng dụng với bo ảo QEMU thật, không người bấm (02/10/2026)

Từ đợt 2, thẻ "Bo điều khiển" có mục "Bo ảo QEMU (firmware xe trong giả lập)" và nút "Khởi động bo ảo"; cả phiên đỗ chạy
được qua bo ảo, với tốc độ, góc lái, tư thế lấy từ một xe MÔ PHỎNG phía laptop ([MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md)
mục 1.1). Người dùng giao quyết định 02/10/2026 ('làm hết'), theo đề xuất. Mã: `autopark/transport/qemu_plant.py`
(`QemuPlantVehicleIO`, xe mô phỏng `LaptopPlant`), `autopark/ui/qemu_runner.py` (`QemuBoardRunner`), tham số GIẢ ĐỊNH
`configs/bo_ao_qemu.json`. Mọi lần build env `esp32s3_qemu` (pytest, dòng lệnh, giao diện) chạy lần lượt qua khóa
`.pio/autopark_esp32s3_qemu.lock`. Mỗi lần khởi động bo ảo có một thư mục log `runs/bo_ao_qemu/<YYYYmmdd_HHMMSS>/` (git bỏ
qua); bản `flash.bin` 8 MB bị xóa khi tắt.

Luật khi gộp đợt 2: bo ảo QEMU chỉ đi với nguồn tư thế "xe mô phỏng" (`sim_truth`); chọn bo ảo cùng "LiDAR mô phỏng" hay
"LiDAR thật" thì hộp thoại từ chối và ba ô trở về liên kết đang dùng. Liên kết bo ảo có `virtual_board` = True (không phải
phần cứng chấp hành). Chỉ bo ảo đóng socket sau mỗi lần chạy (QEMU chỉ phục vụ một client); cổng COM của bo thật giữ mở
giữa các lần chạy.

*(Sửa sau rà soát 02/10/2026.)* Xe mô phỏng phía laptop tiến theo thời điểm của từng khung trong một lần đọc cổng (đồng hồ
bo); mở lại socket thì neo lại thời gian, nên "Xóa lỗi bo" sau một lúc nghỉ không còn tích phân cả lúc nghỉ trên luồng giao
diện; chu kỳ telemetry trong `configs/bo_ao_qemu.json` chỉ nhận 20..100 ms; runner không còn bỏ mất lệnh tắt tới đúng lúc
QEMU vừa khởi động xong; liên kết dựng thẳng với `QemuPlantVehicleIO` cũng mang nhãn bo ảo.

Hai lượt `tests/test_firmware_qemu.py` với QEMU thật trong lúc làm (đầu ra console, không lưu log): 15:13–15:14 ở worktree
của nhánh (tải CPU 7 % trước khi chạy; build env `esp32s3_qemu` trong thư mục worktree mới ≈ 10 s; không có cảnh báo #175
hay LOOP_OVERRUN) và 18:14:43–18:15:00 ở cây gộp sau các bản sửa (EcoQoS off). Ở cả hai,
`test_parking_session_through_qemu_board` chạy 6,4 s, QEMU dùng trung bình 1,01 và 0,97 lõi.

**Lượt chạy ứng dụng 02/10/2026 18:58.** Bằng chứng: [evidence/bo_ao_ui_20261002/](evidence/bo_ao_ui_20261002/): script
`chay_bo_ao_ui.py`, kết quả `ket_qua_bai_do_xe.json`, `bo_ao.json` của runner. Script dựng `MainWindow` của `ui.app`
(offscreen, qua `build_window`) từ cây gộp đợt 2, chọn nhánh VehicleIO và mục "Bo ảo QEMU (firmware xe trong giả lập)",
gọi `qemu_runner.start()` như nút "Khởi động bo ảo", lập đường `scenarios/bai_do_xe.json` (`plan(sync=True)`), gọi `run()`
như nút "Bắt đầu đỗ" hai lần, để vòng 50 Hz của cửa sổ chạy tới khi phiên xong, rồi đóng cửa sổ. Hộp thoại nếu có được trả
lời tự động và ghi lại.

| | Kết quả |
|---|---|
| Bo ảo | ảnh `esp32s3_qemu` đã build sẵn (không build lại; SHA-256 bắt đầu bằng `91fbeba0f0af`); RUNNING sau 0,5 s; HELLO: firmware 1.0, lý do reset POWER_ON |
| Lập đường | 2,55 m, 1 lần đổi chiều; 0,58 s và 1,33 s |
| Hai lần Bắt đầu đỗ | COMPLETED "Đỗ xong" 2/2; 20,98 s và 20,78 s thật; 0 lần START bị từ chối; sự kiện duy nhất trong log là `START_CHECK`; 0 hộp thoại |
| Liên kết | `is_qemu`, `virtual_board` = True, `hardware_actuators` = False; io `QemuPlantVehicleIO`; nguồn tư thế `qemu_plant_pose`; bằng chứng `qemu_firmware_simulated_vehicle` |
| Đóng cửa sổ | bo ảo STOPPED sau 0,01 s (lý do `window_close`, mã thoát QEMU 0); QEMU chạy 45,7 s, thời gian CPU 46,3 s (≈ 1,01 lõi trung bình, gồm lúc khởi động) |

Mức bằng chứng: kiểm trên máy tính với bo ẢO (firmware thật trong QEMU) và xe MÔ PHỎNG phía laptop; không phải bo hay xe
thật. Không ai bấm tay: các nút được gọi bằng mã (`qemu_runner.start()`, `plan(sync=True)`, `run()`), cửa sổ offscreen
không hiện trên màn hình.

Giới hạn:
- Lái bằng tay trên cửa sổ thật với QEMU: CHƯA THỬ.
- Script dựng cửa sổ qua `build_window`, không qua `main()`, nên chính sách EcoQoS của ứng dụng không chạy; trạng thái
  EcoQoS của tiến trình script không được ghi. Cửa sổ thu nhỏ với bo ảo (theo đồng hồ tường): CHƯA ĐO (mục 13 chỉ đo SIM và
  bo mô phỏng).
- Firmware của bo ảo chạy mạch hở (chưa đọc cảm biến, SPEED_VALID = 0): vòng PI, STALL, FEEDBACK_LOST không được thử; không
  có xung ESC/servo, E-stop hay watchdog phần cứng ([MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md) mục 1.1).
- Kịch bản dùng xe `vehicle_default.json`. Firmware biên dịch cứng `max_speed_mm_s` = 300, nên với xe nghiệm thu
  `configs/vehicle_nghiem_thu.json` (0,10 m/s) bo ảo và ESP32-S3 bị TỪ CHỐI ở VEHICLE_IO (LIMITS_MISMATCH, an toàn); với bo
  ảo chưa chạy thử, suy ra từ mã. Bản firmware 100 mm/s: CHƯA LÀM.
- Chạy được trong bo ảo không chứng minh gì về bo thật ([MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md) mục 1).

## 15. Đợt 2, chạy lại trên commit `470abb3` (06/10/2026)

Commit `470abb3` (06/10/2026, đã push lên `origin/main`) gồm mã, tài liệu và bằng chứng của đợt 2 (mục 10.1, 12–14;
người dùng giao quyết định 02/10/2026 ('làm hết'), theo đề xuất). Bộ test có thêm 462 test ở mỗi venv so với lượt trên
`d3e1555` (mục 11): test của các phần mới trong đợt 2.

Chạy trên commit đó, cây làm việc sạch, cùng máy, 06/10/2026 14:43–15:08, offscreen, từ shell của tác tử, bằng script
của mục 11 ([chay_tren_commit.py](evidence/cong_cu_20261002/chay_tren_commit.py)); tóm tắt:
[chay_tren_commit_470abb3.txt](evidence/dot2_20261006/chay_tren_commit_470abb3.txt). Trong lúc chạy, máy còn có các tác
tử thiết kế đợt sau đọc mã và chạy thí nghiệm nhỏ (tải CPU lúc bắt đầu ghi trong bảng).

| Lượt (giờ bắt đầu, tải CPU) | Kết quả | Thời gian | Tệp |
|---|---|---|---|
| `.venv` (14:46, 10 %) | **2105 đạt, 10 bỏ qua** (cần torch), 0 hỏng; tiến trình thoát mã **0xC0000005** sau khi chạy hết | 640 s | [pytest_venv_470abb3.xml](evidence/dot2_20261006/pytest_venv_470abb3.xml) |
| `.venv-train` (14:57, 42 %) | **2168 đạt, 1 hỏng** (`test_parking_session_through_qemu_board`), 0 bỏ qua | 683 s | [pytest_venv_train_470abb3.xml](evidence/dot2_20261006/pytest_venv_train_470abb3.xml) |

- Cả hai tệp JUnit ghi `ecoqos=off`.
- `.venv`: tệp JUnit đủ 2115 test, 0 hỏng, nhưng tiến trình pytest thoát mã 3221225477 = 0xC0000005 (vi phạm truy cập)
  thay vì 0, sau khi đã ghi JUnit (có lẽ lúc tắt Python; script không giữ stdout lẫn stderr của pytest nên không xác
  định được bước nào). Nhật ký Application và System của Windows không có sự kiện nào lúc 14:56–14:58. Đây là lần thứ
  hai: ngày 02/10/2026 một lượt toàn bộ test `.venv` trên cây gộp đợt 2 chạy hết 100 % rồi Git Bash báo mã thoát 139
  (theo ghi chép phiên làm việc, không có tệp bằng chứng); 139 = 128 + 11 là cách Git Bash báo mã Windows 0xC0000005
  (kiểm trên máy tính 06/10/2026), tức cùng loại lỗi. Các lượt toàn bộ khác hôm đó không gặp lỗi này (lần đó chưa ghi
  vào tài liệu). Nguyên nhân CHƯA RÕ; lượt sau sẽ giữ stdout, stderr và bật faulthandler.
  *(Cập nhật 06/10/2026: điều tra ở mục 16.4. Nhật ký trống vì script chạy từ shell của tác tử (Git Bash): tiến trình
  con mang ErrorMode 0x3 nên Windows Error Reporting không ghi sự kiện hay minidump. Ba lượt `.venv` chạy lại có theo
  dõi cùng ngày (15:47–16:20) đều thoát 0; thủ phạm vẫn CHƯA RÕ. Bản mới của script,
  [chay_tren_commit.py](evidence/su_co_thoat_20261006/chay_tren_commit.py), giữ stdout và stderr, bật faulthandler,
  đặt ErrorMode 0x8001 và chép dump mới.)*
- `.venv-train`: `test_parking_session_through_qemu_board` hỏng sau 0,159 s: START bị từ chối "Xe đang chuyển động
  (trung bình +0.007 m/s trên 3 khung, tham chiếu của bo +0.004 m/s)". Điều tra cùng ngày trên bo ảo (101 lượt, kiểm
  trên máy tính; [dua_start_bo_ao/README.txt](evidence/dot2_20261006/dua_start_bo_ao/README.txt)): cổng START từ chối
  ĐÚNG. Test ngay trước dừng xe ở 0,1 m/s rồi trả về ngay; firmware còn dốc tham chiếu tốc độ về 0 (≈ 167 ms ở
  600 mm/s²); test đỗ chỉ chờ bước lập đường (≈ 109–135 ms khi chạy đúng chuỗi của test), nên khi lập đường nhanh hơn
  ≈ 95–100 ms thì khung START cuối còn tham chiếu khác 0. Đúng chuỗi của test, không tải: 0/20 lượt hỏng, nhưng 14/20
  lượt có khung START mang tham chiếu khác 0. Khi lập đường trước rồi START ngay sau lúc dừng (thí nghiệm B), START
  hỏng 12 lần, 2 lần đúng nguyên văn câu lỗi. Vì sao chính lượt `.venv-train` này hỏng: SUY LUẬN (lập đường lượt đó
  ≈ 85–95 ms), không đo. Không phải khung telemetry cũ: khung của phiên trước bị lọc (12/101 lượt có một khung như
  thế, 0 khung lọt vào mẫu START). Sửa ở test (chờ bo đứng yên trước START): vào đợt mã sau, chưa có trong `470abb3`.
- Bo ảo trên cùng commit: `kiem` đạt, 39 khung trong 2 s (≈ 19,5 Hz), cộng 15 khung nhận trước đó lúc kết nối và chờ bo
  ra khỏi BOOT, QEMU khởi động 1 lần ([kiem_bo_ao_470abb3.txt](evidence/dot2_20261006/kiem_bo_ao_470abb3.txt)). Chạy lặp
  `tests/test_firmware_qemu.py` 10 lượt (14:43–14:46): 10/10 lượt đạt cả 14 test (7 trong đó chạy firmware thật trong
  QEMU), không có cảnh báo QEMU tự thoát (#175) hay LOOP_OVERRUN
  ([chay_lap_test_bo_ao_470abb3.txt](evidence/dot2_20261006/chay_lap_test_bo_ao_470abb3.txt)).
- Chạy được trong bo ảo không chứng minh gì về bo thật ([MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md) mục 1).

## 16. Hai kiểu thoát bất thường: điều tra 06/10/2026

Hai kiểu thoát chưa rõ nguyên nhân: (a) LD-1 lần 1 ngày 02/10/2026 dừng ở t ≈ 1050 s, Git Bash ghi `exit=127` (mục
12.1); (b) tiến trình pytest của `.venv` thoát mã 0xC0000005 sau khi chạy hết test, ngày 02/10/2026 và 06/10/2026 (mục
15). Người dùng giao 06/10/2026 ('làm đi'), theo đề xuất. Cách làm: đọc log Windows, khóa registry (chỉ đọc), dấu thời
gian tệp và bản ghi phiên Claude Code trên máy; thí nghiệm nhỏ trên tiến trình vô hại của chính mình; ba lượt bộ test
`.venv` chạy lại có theo dõi. Không đổi registry, không chạy lại LD-1, không dùng thiết bị. Mức bằng chứng của cả mục:
kiểm trên máy tính. Bằng chứng, công cụ và cách chạy lại:
[evidence/su_co_thoat_20261006/](evidence/su_co_thoat_20261006/) (`README.txt`).

### 16.1. Git Bash đổi mã thoát Windows thế nào

Đo 06/10/2026 (Git Bash 5.3.15, MSYS 3.6.9): một tiến trình python tự gọi `ExitProcess(mã)`, qua ba đường (python
gốc, trình khởi chạy venv, `timeout` cộng trình khởi chạy venv); 47 mã, ba đường cho cùng kết quả ở cả 47 mã: 27 mã ở
[bang_ma_thoat_ket_qua.txt](evidence/su_co_thoat_20261006/bang_ma_thoat_ket_qua.txt); 20 mã bổ sung ở
[bang_ma_thoat_bo_sung.txt](evidence/su_co_thoat_20261006/bang_ma_thoat_bo_sung.txt) (lần đầu, 15:33, chỉ đo qua
python gốc; đo lại qua đủ ba đường lúc 18:27 bằng `bang_ma_thoat.sh bo_sung`, cột python gốc trùng lần đầu).

| Mã Windows (32 bit) | `$?` trong Git Bash |
|---|---|
| < 0xC0000000 | byte thấp: 0x17F → 127, 0x40000015 → 21, 0x80000003 → 3, 0xBFFFFFFF → 255 |
| 0xC0000005 (vi phạm truy cập) | 139; bash in "Segmentation fault" |
| 0xC0000017 (hết bộ nhớ) | 138 |
| 0xC000001D (lệnh máy không hợp lệ) | 132 |
| 0xC000013A (Ctrl+C) | 130 |
| 32 mã ≥ 0xC0000000 khác đã thử, gồm 0xC000007F (STATUS_DISK_FULL), 0xC0000409, 0xC0000374, 0xC00000FD, 0xC000012D, 0xE06D7363 và 0xFFFFFFFF (mã của `Stop-Process -Force`) | 127, không in gì |

Hệ quả: 127 không phải "byte thấp của mã thoát Windows"; Git Bash cho 127 với mọi mã ≥ 0xC0000000 trừ bốn mã ở bảng,
nên 127 gom gần như mọi kiểu chết bất thường, kể cả bị dừng bằng `Stop-Process -Force`. 139 thì chỉ có thể là
0xC0000005. Trình khởi chạy venv (`.venv*\Scripts\python.exe`) trả nguyên mã 32 bit của python gốc.

### 16.2. ErrorMode và Windows Error Reporting

- Tiến trình mở từ Git Bash (công cụ Bash của tác tử, `chay.sh`, kể cả qua `timeout`) mang ErrorMode 0x3
  (SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX); mở từ PowerShell, hay qua `chay_co_theo_doi.py`, là 0x8001
  ([kiem_job_ket_qua.txt](evidence/su_co_thoat_20261006/kiem_job_ket_qua.txt)). Với 0x3, một lần crash KHÔNG có sự
  kiện Application Error 1000/1001 và KHÔNG có minidump, dù LocalDumps đã bật trên máy bàn (khóa
  `HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps` có sẵn; dump vào `%LOCALAPPDATA%\CrashDumps`,
  giữ 10 tệp).
- Vì vậy các câu "log Application/System … không có sự kiện nào" ở mục 12.1 và mục 15 đúng nhưng không loại được một
  crash: LD-1 lần 1 và hai lượt pytest đều mở từ Git Bash. ErrorMode chỉ quyết định WER có ghi sự kiện vào log
  Application hay không, không ảnh hưởng log System. Bị dừng từ ngoài (TerminateProcess) thì không có ngoại lệ nên
  không có sự kiện WER, kể cả với ErrorMode 0x8001 ([thu_dau_cuoi/](evidence/su_co_thoat_20261006/thu_dau_cuoi/): mã
  0xFFFFFFFF, 0 sự kiện).
- Đối chứng tự nhiên ngày 29/09/2026: cùng một exe `ht_dynamic.exe` crash hai lần cách nhau khoảng 1 s, một lần chạy
  thẳng trong Git Bash, một lần qua `powershell.exe`; log chỉ có đúng một Application Error (15:30:59). Ngày 06/10/2026,
  lượt 3 của vòng chạy lại có theo dõi (mục 16.4, ErrorMode 0x8001) có sự kiện WER cho một lần QEMU crash (0xC0000005,
  16:12:03; giờ khởi động ghi trong sự kiện là 16:12:02,715, tức crash chưa tới 1,3 s sau khi khởi động); có lẽ đó là
  lỗi QEMU tự thoát lúc khởi động espressif/qemu#175 (suy luận).

### 16.3. (a) LD-1 lần 1: dòng thời gian và kết luận

Giờ máy, ngày 02/10/2026. "Phiên kia" là một phiên tác tử Claude khác trên cùng máy, làm dự án khác; bản ghi phiên của
nó nằm ngoài repo và không chép vào đây.

| Giờ | Sự kiện | Nguồn |
|---|---|---|
| 14:11:16 | `chay.sh` (chạy nền bằng công cụ Bash của tác tử, ErrorMode 0x3) bắt đầu bước 5: `rig.bench … --seconds 1800 --record runs/rig_recordings/20261002_ld1` | [nhat_ky.txt](evidence/thiet_bi_20261002/nhat_ky.txt) |
| 14:11:39,03 | t = 0 của phiên ghi | `meta.json` của bản ghi (`runs/`, git bỏ qua) |
| 14:25:20 | Phiên kia liệt kê mọi tiến trình tên python: PID 26456 là 1552 MB, 33860 là 4 MB, ba tiến trình khác ≤ 151 MB | bản ghi phiên kia |
| 14:29:06 | Liệt kê lại: 26456 là 1554 MB, 1469,4 s CPU; 33860 là 4 MB, 0 s CPU; ba tiến trình khác ≤ 238 MB | bản ghi phiên kia |
| 14:29:09,04 | Dòng trạng thái cuối của `rig.bench` (t = 1050,0 s) | giờ sửa tệp `ld1.txt` (`runs/`) |
| 14:29:12,569 | Phiên kia chạy `powershell -NoProfile -Command "Stop-Process -Id 26456 -Force -ErrorAction SilentlyContinue"`, tưởng đó là tiến trình treo của chính nó | bản ghi phiên kia; tìm lại bằng `tim_lenh_giet.py --pid` ([kiem_cong_cu.txt](evidence/su_co_thoat_20261006/kiem_cong_cu.txt) mục 3) |
| 14:29:13,24–13,26 | Khung ảnh cuối của bốn camera; không có khung kế (lẽ ra sau 33–48 ms) | `frames.csv` của bản ghi (`runs/`): stamp và giờ sửa tệp |
| 14:29:14 | `chay.sh` ghi `exit=127` | [nhat_ky.txt](evidence/thiet_bi_20261002/nhat_ky.txt) |

Kết luận (kiểm trên máy tính): LD-1 lần 1 không dừng vì lỗi của autopark mà vì bị phiên kia dừng bằng
`Stop-Process -Force`.
- Đúng giờ: khung cuối đến 0,67–0,69 s sau lúc phiên kia gọi lệnh. Đo 06/10/2026, từ lúc gọi `powershell` với
  `Stop-Process` tới lúc tiến trình bị dừng mất 0,175–0,193 s (3 lần); phần còn lại có lẽ là lúc công cụ của phiên kia
  dựng bash (suy luận), không đo được cho ngày 02/10.
- Đúng mã: `Stop-Process -Force` cho mã 0xFFFFFFFF, Git Bash báo 127 (tái hiện 3/3,
  [thu_stop_process_ket_qua.txt](evidence/su_co_thoat_20261006/thu_stop_process_ket_qua.txt)).
- Đúng tiến trình, theo LOẠI TRỪ (phía autopark không ghi PID): LD-1 gồm trình khởi chạy venv (≈ 4 MB) và python gốc.
  Ở cả hai bảng, 26456 là python duy nhất ≥ 1 GB và 33860 có 4 MB. Bảng 14:25:20 không có cột CPU và có thêm 17016 =
  8 MB; ở bảng 14:29:06, 33860 là tiến trình duy nhất có 0 s CPU (17016 có 174,6 s CPU nên không phải trình khởi chạy).
  1469,4 s CPU sau ≈ 1070 s chạy là ≈ 1,37 lõi trung bình (12 dòng trạng thái giữ trong `ld1_rut_gon.txt` ghi 1,08–1,58
  lõi); bộ nhớ WS của `rig.bench` ở LD-1 lần 3 là 1544–1592 MB (≈ 1560 MB cùng thời điểm tính từ lúc mở;
  `runs/thiet_bi_20261002/theo_doi_ld1_lan3.csv`).
- Đúng dấu vết của việc bị dừng từ ngoài (TerminateProcess): không traceback, không `.rig.json`, `meta.json` của bản ghi
  kẹt ở "đang ghi", C1 bị bỏ lại đang quét (gốc lỗi của LD-1 lần 2, mục 12.2), không có sự kiện WER (không phân biệt
  được với crash vì ErrorMode 0x3).
- Giả thuyết STATUS_DISK_FULL bị bác: ổ D còn 55,8 GB lúc 14:29, và 127 không đặc trưng cho mã này (mục 16.1). Crash
  native khác cho 127, hết bộ nhớ hay lỗi GPU: rất thấp; trùng giờ với lệnh dừng trong vòng một phần giây, hết bộ nhớ
  (0xC0000017) sẽ cho 138, log System ngày 02/10 không có sự kiện Display, nvlddmkm hay WHEA.
- Hệ quả: lý do (e) "nguyên nhân lần 1 CHƯA RÕ" ở [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 5.8 đã rõ; LD-1
  vẫn chưa tính là đạt vì các lý do (a)–(d) ở đó.

### 16.4. (b) pytest `.venv` thoát 0xC0000005 lúc tắt

| Lượt | Cách chạy | Kết quả |
|---|---|---|
| 02/10/2026 19:00:39–19:10:53, `.venv`, cây gộp đợt 2 | công cụ Bash của tác tử (ErrorMode 0x3): `timeout 3000 … python -X utf8 -m pytest -p no:cacheprovider -q -o faulthandler_timeout=300 -rfE`, đầu ra vào tệp, không JUnit (bản ghi phiên và tệp đầu ra ngoài repo) | chạy tới "[100%]"; bash in "Segmentation fault", `$?` = 139, tức 0xC0000005; tệp đầu ra không có "Windows fatal exception" hay "Fatal Python error" |
| 06/10/2026 14:46–14:57, `.venv`, commit `470abb3` (mục 15) | `chay_tren_commit.py` bản cũ, từ shell của tác tử (ErrorMode 0x3); không `-X faulthandler`; stdout và stderr bị bỏ | JUnit đủ 2115 test, 0 hỏng; mã 3221225477 = 0xC0000005 |
| 06/10/2026 15:47–16:20, `.venv`, 3 lượt, cây chính (mã như commit `470abb3`) | qua `chay_co_theo_doi.py` (ErrorMode 0x8001), `-X faulthandler`, plugin `ghi_dau_tat`, `-q -rfE -o faulthandler_timeout=300`, JUnit | 3/3 thoát 0x00000000; mỗi lượt 2115 test, 0 hỏng, 10 bỏ qua (cần torch); 681, 640, 612 s theo JUnit ([pytest_lap/](evidence/su_co_thoat_20261006/pytest_lap/)) |

Tỉ lệ (người phản biện đếm các lượt toàn bộ test ghi trong bản ghi phiên làm việc, suy venv từ giờ chạy): `.venv` 2/9
lượt trước điều tra, `.venv-train` 0/6; cộng ba lượt có theo dõi thì `.venv` 2/12. Hai venv có cùng Python 3.12.10,
PySide6 6.11.2, opencv-python 5.0.0.93, numpy 2.5.2 và pytest 9.1.1 nhưng không chỉ khác torch (đọc bằng
`importlib.metadata` 06/10/2026: `.venv` 31 gói, `.venv-train` 39): `.venv-train` có thêm torch, torchvision, onnx,
onnxruntime, onnxscript, psutil, pillow, nvidia-ml-py, sympy, networkx …; `.venv` có coverage, gdown, requests, tqdm …
mà `.venv-train` không có. Vì có psutil và nvidia-ml-py, `ResourceMonitor` trong
[autopark/rig/core.py](../autopark/rig/core.py) chạy nhánh khác ở `.venv-train`; `.venv-train` còn chạy thêm 54 test
(2169 so với 2115 trên commit `470abb3`). Số lượt quá ít để nói venv nào hay gặp hơn.

Tiến trình chết lúc nào (đọc mã pytest 9.1.1 và thí nghiệm nhỏ; suy luận có căn cứ):
- Plugin faulthandler của pytest bật faulthandler ở `pytest_configure` và TẮT ở `pytest_unconfigure`, chỉ bật lại nếu
  có `-X faulthandler`. Hook đó chạy trước `pytest_unconfigure` của plugin unraisableexception, plugin này gọi
  `gc.collect()` toàn phần; lúc dọn "cleanup stack" của config, `gc.collect()` chạy lần nữa; sau đó là đường ra của
  pytest và pha tắt của Python: `threading._shutdown`, atexit (gồm `PySide6.QtCore.__moduleShutdown`,
  [kiem_atexit_ket_qua.txt](evidence/su_co_thoat_20261006/kiem_atexit_ket_qua.txt)), dọn module, DLL detach.
- Thí nghiệm của người phản biện ([thu_thu_tu/](evidence/su_co_thoat_20261006/thu_thu_tu/), chạy lại 06/10/2026 cho
  cùng đầu ra): không `-X faulthandler` thì `faulthandler.is_enabled()` là False ở cả hai lần `gc.collect()`; có thì
  True.
- Vì vậy lượt 02/10 chết SAU khi faulthandler đã bị tắt trong `pytest_unconfigure` (crash trước đó sẽ in "Windows fatal
  exception"); lượt 06/10 14:46 chết sau khi đã ghi JUnit (JUnit ghi ở `pytest_sessionfinish`), stderr bị bỏ nên không
  biết thêm. Dòng "N passed" vắng ở lượt 02/10 không phải dấu hiệu chết sớm: `-q` của lệnh cộng `-q` trong `addopts`
  làm pytest không in dòng tổng kết.

Ba lượt có theo dõi: plugin ghi đủ sáu dấu đúng thứ tự, dấu cuối `atexit_cuoi`; tệp traceback của faulthandler rỗng.
Lúc kết thúc phiên (`phien_xong`) QApplication còn 1325 cửa sổ top-level và 47 028 widget; chỉ còn luồng Python
`MainThread` nhưng tiến trình có 70–71 luồng hệ điều hành, còn 65–66 sau atexit. DLL lạ trong tiến trình: `uvh64.dll`
(hook của UltraViewer) và `MpOav.dll` (Windows Defender). Lượt 3 có một lần QEMU crash (16:12:03, chưa tới 1,3 s sau
khi khởi động; có lẽ #175, suy luận), WER ghi được vì ErrorMode 0x8001; không có dump python mới.

| # | Giả thuyết | Khả năng | Ủng hộ | Yếu hoặc bác |
|---|---|---|---|---|
| 1 | Vi phạm truy cập khi hủy đối tượng native lúc tắt: QApplication, QObject còn sống bị hủy trong `PySide6.QtCore.__moduleShutdown`, hoặc wrapper Qt/OpenCV bị giải phóng trong hai lần `gc.collect()` của pytest hay lúc dọn module | trung bình | 0xC0000005; chết sau khi faulthandler tắt; 1325 cửa sổ top-level và 47 028 widget còn sống lúc kết thúc phiên; các tệp test cuối là test giao diện | chưa có dump; 3 lượt có theo dõi thoát 0 |
| 2 | Đua lúc DLL_PROCESS_DETACH với luồng native còn sống (65–66 luồng hệ điều hành sau atexit: Qt, OpenCV, OpenBLAS; DLL chèn `uvh64.dll`, `MpOav.dll`) | trung bình – thấp | hiếm, phụ thuộc thời điểm; faulthandler không bắt được pha này | chưa có dump |
| 3 | Luồng daemon Python còn chạy lúc kết thúc trình thông dịch (`ScanReader` của LiDAR dừng mà không join) | thấp | luồng daemon có thật trong các test LiDAR | kiểu này in "Fatal Python error" (lượt 02/10 không có); cuối 3 lượt có theo dõi chỉ còn `MainThread` |
| 4 | Cờ `-o faulthandler_timeout=300` | bác, ít nhất như điều kiện cần | — | lượt 06/10 14:46 không có cờ này vẫn crash |
| 5 | Bên ngoài: bị dừng, hết bộ nhớ, phần cứng | rất thấp | — | bị dừng thì mã là 0xFFFFFFFF (Git Bash 127), không phải 0xC0000005 (139) |

Mức bằng chứng: thời điểm chết là suy luận có căn cứ; thủ phạm CHƯA RÕ, CẦN ĐO (cần minidump của một lần crash).

### 16.5. Công cụ

Trong [evidence/su_co_thoat_20261006/](evidence/su_co_thoat_20261006/), bản đã sửa theo phản biện và đã kiểm nhỏ
06/10/2026 ([kiem_cong_cu.txt](evidence/su_co_thoat_20261006/kiem_cong_cu.txt)):
- `chay_co_theo_doi.py`: chạy một lệnh dài với ErrorMode 0x8001; ghi PID, đầu ra, mã 32 bit (hex, nghĩa, `$?` mà Git
  Bash sẽ báo); `--het-gio S` (quá hạn thì `taskkill /T /F` cả cây tiến trình, ghi "HẾT GIỜ"); chép dump mới vào
  `<ra>/dump/`; khi mã ≥ 0xC0000000 thì tìm trong bản ghi phiên Claude trên máy lệnh dừng nhắm PID của mình (ghi
  nguyên câu lệnh chỉ khi nhắm đúng PID đó; lệnh giết python theo tên chỉ ghi giờ và loại lệnh);
  `--theo-doi` chạy `theo_doi_mo_rong.ps1` (ổ trống, bộ nhớ, CPU, GPU, mọi tiến trình python, lệnh dừng tiến trình
  thấy được, log Windows; dòng lệnh của lệnh dừng chỉ ghi khi nhắm PID đang canh, lệnh giết python theo tên chỉ ghi giờ
  và loại lệnh). `theo_doi/python.csv`, `theo_doi/gpu_app.csv` và `lenh_giet.txt` có thể chứa dòng lệnh hay tên của
  tiến trình khác trên máy: để `<ra>` ngoài git, không chép ba tệp đó vào `docs/evidence`.
- `ghi_dau_tat.py`: plugin pytest ghi dấu các pha tắt; `GHI_DAU_TAT_DEM_WIDGET=0` tắt đếm widget.
- `lap_pytest.sh`: lặp bộ test `.venv` qua wrapper, hạn giờ 3000 s mỗi lượt; chế độ `day_du` (như ba lượt ở trên
  nhưng bỏ `-o faulthandler_timeout=300`, vì lượt crash 06/10 14:46 không có cờ này) hay `chi_wrapper` (không
  `-X faulthandler`, không plugin: đúng điều kiện hai lần crash, vẫn có minidump).
- `chay_tren_commit.py`: bản mới của script chạy lại trên commit (mục 9, 11, 15; bản cũ giữ nguyên): ErrorMode 0x8001,
  pytest với `-X faulthandler`, đầu ra từng lượt ra tệp, mã hex kèm nghĩa, dump mới chép sang `runs/dump/`, hạn giờ,
  ghi HEAD và độ sạch của cây; `--chi-test` để kiểm script trong vài giây.
- `doc_minidump.py` (đọc minidump không cần WinDbg) và `tim_lenh_giet.py` (tìm lệnh dừng tiến trình trong bản ghi phiên
  Claude theo khoảng giờ; `--pid` chỉ in nguyên câu lệnh nhắm PID đó, lệnh giết python theo tên chỉ in giờ và loại lệnh
  ("lệnh giết python theo tên (…); dòng lệnh không ghi"), không in lệnh nào khác; kiểm lại sau lần sửa này:
  [kiem_cong_cu.txt](evidence/su_co_thoat_20261006/kiem_cong_cu.txt) mục 9).

### 16.6. Bước tiếp

- (b): chạy `lap_pytest.sh` chế độ `chi_wrapper` vài lượt khi máy rảnh (mỗi lượt ≈ 10–12 phút, nặng CPU), sau khi sao
  lưu `%LOCALAPPDATA%\CrashDumps`; có dump thì đọc bằng `doc_minidump.py` (module và offset chỗ lỗi). CHƯA CHẠY.
  *(Cập nhật 06/10/2026: đã chạy 6 lượt `chi_wrapper` lúc 17:53–18:56 trên mã `ea78327` (= mã `470abb3`), máy có các
  tác tử khác chạy song song: 0/6 lượt Python thoát 0xC0000005; lượt 2–6 đạt 2115 test, thoát 0. Lượt 1 thoát 1
  vì một test bo ảo hỏng (`test_chip_reset_is_seen_as_firmware_reset`): QEMU tự crash trong lúc test reset chip
  (dump QEMU 17:55:30, trong khoảng 17:55:25–17:55:31 của test). Với ErrorMode 0x8001, tiến trình QEMU còn sống
  lúc WER ghi dump, nên `on_board` thấy bo "vẫn chạy", kiểm LOOP_OVERRUN bằng một kết nối mới và kết nối hết hạn
  2 s thay vì chạy lại; mở từ Git Bash (0x3) thì QEMU thoát ngay và test tự khởi động lại bo ảo. Sửa ở test trong
  đợt mã sau. Tính cả các lượt này, lỗi thoát 0xC0000005 của `.venv` là 2/18 lượt toàn bộ; kết quả: [chi_wrapper_20261006/](evidence/su_co_thoat_20261006/chi_wrapper_20261006/).)*
- (b), ĐỀ XUẤT – CHỜ CHỐT, CHƯA THỬ: dọn cửa sổ Qt mà test để lại (đóng và `deleteLater()` các cửa sổ top-level sau mỗi
  test giao diện, ví dụ bằng một fixture chung trong `tests/conftest.py`) như một hướng giảm crash lúc tắt, vì lúc kết
  thúc phiên còn 1325 cửa sổ top-level và 47 028 widget. Chưa biết đây có phải nguyên nhân.
- Lượt chạy lại trên commit sau: dùng `chay_tren_commit.py` bản mới.
- (a), ĐỀ XUẤT – CHỜ CHỐT: lần LD-1 tới chạy qua wrapper (hay ít nhất mở từ PowerShell) để có PID, mã 32 bit và dump;
  trước đó báo các phiên tác tử khác trên máy không dừng tiến trình python theo tên hay theo cỡ bộ nhớ
  ([VIEC_TAI_CHO_THIET_BI.md](VIEC_TAI_CHO_THIET_BI.md) việc 1 bước 5, việc 7 bước 7). Không cần chạy lại LD-1 chỉ để
  tìm nguyên nhân lần 1.

### 16.7. Giới hạn

- (a) dựa trên bản ghi phiên Claude của dự án khác và dấu thời gian tệp; không có log kiểm toán của hệ điều hành (sự
  kiện kết thúc tiến trình Security 4689 cần bật kiểm toán và quyền quản trị; log 'Windows PowerShell' là vòng 15 MB,
  giữ ≈ 15–33 phút). PID khớp theo loại trừ. Bản trích bản ghi phiên kia không đưa vào repo.
- (b) chưa tái hiện (0/3 lượt có theo dõi). Ba lượt đó đổi điều kiện so với hai lần crash: `-X faulthandler`, plugin đếm
  47 028 widget ngay trước pha tắt. Chế độ `chi_wrapper` CHƯA CHẠY. *(Cập nhật 06/10/2026: đã chạy 6 lượt, 0/6 tái
  hiện; mục 16.6.)*
- *(Thêm 06/10/2026.)* Chạy qua wrapper hay `chay_tren_commit.py` bản mới (ErrorMode 0x8001) làm lần QEMU tự crash
  kéo dài (WER ghi dump trong lúc tiến trình còn sống): test bo ảo có thể hỏng cho tới khi `on_board` chờ QEMU thoát
  hẳn rồi chạy lại (sửa trong đợt mã sau; mục 16.6).
- Với ErrorMode 0x8001, WER ghi cả các lần QEMU crash trong test (có lẽ #175, suy luận); mỗi dump mới làm WER xóa dump
  cũ nhất khi thư mục đã có 10 tệp. Kiểm được: bản sao lưu lúc 15:46 ngày 06/10/2026 có đủ 10 dump trước đó
  (`runs/crashdumps_sao_luu_20261006/`, git bỏ qua); lúc 17:31 `CrashDumps` còn 9 tệp
  ([kiem_cong_cu.txt](evidence/su_co_thoat_20261006/kiem_cong_cu.txt) mục 6); lúc 18:31 có 10 tệp, dump QEMU
  30/09/2026 10:23 không còn, thêm một dump QEMU 06/10/2026 17:55:30. Dump 30/09 mất lúc nào và vì sao: CHƯA RÕ.
- Bộ theo dõi không thấy lệnh do công cụ PowerShell của Claude Code chạy (lệnh nằm trong biến môi trường), không thấy
  `taskkill` hay `kill` gọi thẳng; `tim_lenh_giet.py` chỉ thấy lệnh do phiên Claude Code chạy. Tải CPU của bộ theo dõi
  CHƯA ĐO. Trên laptop, LocalDumps (dump của WER) CHƯA KIỂM.
