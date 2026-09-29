# Chuyển sang máy bàn mới (29/09/2026)

**Quyết định của người dùng (29/09/2026):** từ ngày này, máy dưới đây là máy bàn, tức máy phát triển chính của dự án
("chuyển hẳn sang máy này"). Máy bàn cũ là nơi đo mọi số cảm biến, AI và bàn thử tới 25/09/2026 (mô phỏng giai đoạn 0
ngày 20/09 chạy trên laptop). Vai trò của laptop RTX 3050 Ti (mang đi nộp đồ án, [MAY_NOP_DO_AN.md](MAY_NOP_DO_AN.md))
giữ nguyên.

| | Máy bàn cũ (tới 25/09/2026) | Máy bàn mới (từ 29/09/2026) |
|---|---|---|
| Máy | i9-14900 + RTX 4000 Ada 20 GB, RAM 64 GB | Dell Precision 3680, i9-14900, RTX 4000 Ada 20 GB, RAM 63,7 GB, Windows 11 Enterprise 26200 |
| Driver NVIDIA | 596.72 | 596.71 |
| Thư mục repo | `D:\ap` (mã ở `D:\ap\autopark`) | `D:\gấp\autopark` (mã ở `D:\gấp\autopark\autopark`) |
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
đó là hồ sơ của máy cũ, không dùng để chạy lại (`D:\ap\autopark` tương ứng `D:\gấp\autopark\autopark`).

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
[pytest_venv_train_sau_sua_20260929.xml](evidence/chuyen_may_20260929/pytest_venv_train_sau_sua_20260929.xml). Số
test này không gắn với mã commit nào; muốn gắn với một commit thì chạy lại trên commit đó. Với thiết bị thật, sửa đổi
mới chỉ thử một lệnh: `lidar.rplidar_c1 info` KHÔNG có `--port` mở đúng COM3 lấy từ tệp cấu hình, đọc được C1 (cùng
serial, health OK), mã thoát 0; `lidar_port("auto")` cũng ra COM3. `ui.lidar_app`, `fusion.demo`, `rig.bench --lidar`
và camera CHƯA THỬ với thiết bị thật sau sửa đổi; lượt `do_may_moi.cmd` ở mục 2 là mã `9d68257`.

Tài liệu: lệnh cần chạy trong các tệp `.md` bỏ `--port COM4` / đổi `--lidar COM4` thành `--lidar`; câu ghi phiên đo cũ ở COM4
giữ nguyên, có ghi chú ngày khi cần. Tệp `docs/evidence/` không sửa.

## 4. Còn khác máy cũ, chưa làm

- Driver CP210x 11.2.0.167 (máy cũ 11.6.0.420); driver NVIDIA 596.71 (máy cũ 596.72). LiDAR và AI đo được như máy cũ (mục 2).
- Máy này có g++ 16.1.0 và cmake 4.4.1 trên PATH; máy cũ không có trình biên dịch nên test host của firmware
  (`firmware/esp32_vehicle/test/host`) chưa biên dịch lần nào. CHƯA THỬ trên máy này.
- GitHub: đã đăng nhập trên máy này ngày 29/09/2026 bằng Git Credential Manager (đăng nhập mã thiết bị qua Edge); fetch
  được; ngày đó chưa thử push. Sau fetch, `main` tiến nhanh từ `9d68257` lên `2ee2940` của GitHub (hai commit ngày 26/09/2026 chỉ sửa
  tệp `.md`), nên mã nguồn vẫn như lúc đo các số test ở mục 2 và 3.
- Ổ D còn ≈ 30,6 GB trống (29/09/2026, sau khi tạo lại venv và xóa venv cũ ≈ 6,0 GB; trước khi xóa còn ≈ 24,6 GB).
  Kịch bản LD-1 có `--record` của [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) đòi ≥ 30 GB.
- Chưa tải trọng số pretrained của torchvision (`%USERPROFILE%\.cache\torch`): lần train, benchmark hay `--resume` đầu tiên
  cần mạng. Suy luận (AI, bàn thử, AI camera) không cần.
- Test phụ thuộc thời gian thật (`planner_budget`, ví dụ `uturn_w46`) có thể hỏng khi máy bận; chạy lại riêng lúc máy rảnh
  trước khi kết luận.

## 5. Lần sau đổi máy

1. Cài Python 3.12.10 (bản của tệp khóa) và driver CP210x của Silicon Labs.
2. Chạy `autopark\cai_dat.cmd` rồi `autopark\cai_dat_train.cmd`. Venv chép sang mà hỏng sẽ tự được đổi tên và tạo lại.
3. Sửa MỘT dòng `lidar_port` trong `autopark\configs\thiet_bi.json` theo số COM của LiDAR trên máy đó (Device Manager, mục
   "Silicon Labs CP210x USB to UART Bridge (COMx)"), hoặc ghi `"auto"`.
4. Traceback còn hiện đường dẫn máy cũ thì xóa các thư mục `__pycache__` ngoài venv.
5. Chạy toàn bộ bộ test ở cả hai venv, rồi `autopark\do_may_moi.cmd` với LiDAR và bốn camera cắm đúng cổng hub 1–4.
