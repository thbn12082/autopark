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
(N-C5 của [NGUONG_NGHIEM_THU_DE_XUAT.md](NGUONG_NGHIEM_THU_DE_XUAT.md)).

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
  ≈ 28 GB sau khi cài PlatformIO, rồi ≈ 62,6 GB khi đọc lại chiều 30/09/2026; mục 7.)*
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
  EcoQoS thì hết.)*
- Bằng chứng: [ecoqos_30092026/](evidence/mo_phong_20260930/ecoqos_30092026/) gồm `do_uturn_w46.txt`,
  `nhom_planner_budget.txt`, JUnit của từng lượt, `linger_probe.log` và các script đo.
- **Đã sửa theo quyết định của người dùng (30/09/2026, 11:53–11:59):** `tests/conftest.py` tắt EcoQoS cho tiến trình
  pytest trên Windows, dùng hàm chung `autopark/power_throttling.py`; `QemuBoard` cũng dùng hàm này thay bản riêng. Hệ
  quả: test có hạn giờ nay đo trong điều kiện "tiến trình không bị Windows hạ tốc", không còn đo đúng điều kiện chạy
  nền mặc định.
  - Muốn đo như cũ thì đặt biến môi trường `AUTOPARK_KEEP_ECOQOS=1`.
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
- Chỉ đo lần lập đường. Vòng điều khiển 50 Hz của lần chạy khi cửa sổ bị thu nhỏ: CHƯA ĐO.
- Cột `ecoqos` của bảng ghi chính sách của tiến trình (`system`), không phải "đang bị hạ"; dấu hiệu hạ tốc là phần CPU
  trên lõi E và thời gian.

CHƯA LÀM, chờ quyết định: ứng dụng tự tắt EcoQoS cho mình (gọi `disable_power_throttling()` của
`autopark/power_throttling.py` lúc khởi động `ui.app` và `ui.lidar_app`, như `tests/conftest.py`), hay giữ mặc định của
Windows và cảnh báo không thu nhỏ cửa sổ khi đang lập đường hay đang chạy.

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
