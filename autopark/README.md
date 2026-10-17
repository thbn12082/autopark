# Cài đặt và chạy AutoPark

AutoPark giúp một xe mô hình tự tìm đường vào chỗ đỗ, đi theo đường đó và dừng khi gặp tình huống không an toàn. Bạn có thể bắt đầu bằng xe và sa bàn mô phỏng hoàn toàn trên máy tính.

**Người mới chỉ cần làm mục 1–4.** Sau đó đọc [hướng dẫn tham gia dự án](../CONTRIBUTING.md) để chọn phần việc đầu tiên. Các mục 5–9 dành cho AI, cảm biến và firmware; chưa cần cài chúng để sửa giao diện, thuật toán hoặc kiểm thử mô phỏng.

[Giới thiệu dự án](../README.md) · [Mục lục tài liệu](docs/README.md) · [Giải thích thuật ngữ](docs/THUAT_NGU.md) · [Lệnh nâng cao](docs/LENH_NANG_CAO.md)

## 1. Chọn môi trường và thư mục

### Cần chuẩn bị gì?

- Windows và PowerShell để làm theo các lệnh trong trang này.
- Python **3.12** được khuyến nghị; dự án yêu cầu từ 3.11 trở lên.
- Mạng Internet khi cài thư viện lần đầu. Git cần khi tải mã và gửi thay đổi.
- Một bản mã nguồn của dự án. Mô phỏng cơ bản chạy bằng CPU, không cần GPU, camera, LiDAR, bo mạch hay dữ liệu huấn luyện.

Trong dự án có ba thư mục cùng tên `autopark`. Chúng có vai trò khác nhau:

```text
autopark/                         ← gốc Git: .git, README.md, CONTRIBUTING.md
└── autopark/                     ← thư mục chạy lệnh trong trang này
    ├── README.md                 ← trang bạn đang đọc
    ├── pyproject.toml            ← thông tin và thư viện Python cần cài
    ├── run_app.py                ← lệnh mở mô phỏng
    ├── .venv/                    ← Python và thư viện riêng của dự án
    ├── autopark/                 ← mã nguồn Python
    ├── configs/                  ← thông số xe, cảm biến, thiết bị
    ├── scenarios/                ← các sa bàn mẫu
    ├── tests/                    ← kiểm thử tự động
    └── firmware/esp32_vehicle/   ← chương trình chạy trên ESP32-S3
```

**Mọi lệnh dưới đây chạy tại thư mục có `pyproject.toml` và `run_app.py`**, trừ nơi ghi rõ khác. Nếu đang đứng ở gốc Git, chạy:

```powershell
cd .\autopark
Test-Path .\pyproject.toml
Test-Path .\run_app.py
```

Cả hai dòng kiểm tra phải trả về `True`. Với thư mục hiện tại trên máy này, có thể đi thẳng tới đó:

```powershell
Set-Location -LiteralPath 'C:\Users\ginno\OneDrive\Desktop\xe tự lái\autopark\autopark'
```

Đường dẫn có dấu hoặc khoảng trắng phải được đặt trong dấu nháy. Người dùng máy khác thay đường dẫn bằng nơi mình lưu dự án.

### Nếu máy chưa có mã nguồn

Nếu đã có bản dự án trên máy, dùng thư mục hiện có theo hướng dẫn phía trên; không clone thêm bên trong nó. Chỉ với máy chưa có mã nguồn: cài Git, mở PowerShell tại thư mục cha muốn lưu dự án rồi chạy:

```powershell
git clone https://github.com/thbn12082/autopark.git
cd .\autopark\autopark
Test-Path .\pyproject.toml
Test-Path .\run_app.py
```

Nếu kho mã là riêng tư, tài khoản GitHub của bạn cần được cấp quyền truy cập. Khi cả hai phép kiểm trả về `True`, bạn đang ở đúng thư mục Python; tiếp tục mục 2 để cài môi trường.

### Chọn đúng môi trường Python

Môi trường ảo là thư mục chứa Python và các thư viện riêng cho dự án. Các lệnh ở đây gọi trực tiếp `python.exe` trong môi trường đó, nên **không cần chạy Activate và không cần đổi chính sách PowerShell**.

| Việc muốn làm | Môi trường | Cần thêm |
|---|---|---|
| Chạy mô phỏng, sửa giao diện hoặc thuật toán | `.venv` | Thư viện cơ bản; thêm nhóm `dev` để chạy test |
| Làm việc với camera hoặc LiDAR | `.venv` | Thư viện cảm biến, thiết bị hoặc bản ghi phù hợp |
| Chạy hoặc huấn luyện AI | `.venv-train` | Mô hình đã huấn luyện hoặc dữ liệu; cấu hình GPU theo mục 5 |
| Viết firmware, thử bo ảo | `.venv` và công cụ C++ | CMake/trình biên dịch; PlatformIO và QEMU khi cần |

## 2. Cài và mở mô phỏng

### Máy chưa có môi trường `.venv`

Kiểm tra Python rồi tạo môi trường:

```powershell
py -3.12 --version
py -3.12 -m venv .venv
```

Dòng đầu phải hiện `Python 3.12.x`. Nếu máy không có lệnh `py`, kiểm tra `python --version`; khi đó dùng `python -m venv .venv` với Python từ 3.11 trở lên.

Nếu thư mục đã có `.venv`, hãy kiểm tra trước và dùng lại khi lệnh sau chạy được:

```powershell
.\.venv\Scripts\python.exe --version
```

Không cần tạo lại môi trường đang dùng tốt. Nếu Python báo `No Python at ...`, xem mục 11.

### Cài thư viện và kiểm tra

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -X utf8 -c "import autopark, PySide6, numpy, shapely; print('Moi truong OK')"
```

`-e` cài dự án ở chế độ chỉnh sửa: sửa mã Python thì lần chạy sau dùng mã mới ngay. `[dev]` thêm pytest và coverage cho người phát triển; nếu chỉ chạy ứng dụng, có thể dùng `pip install -e .`.

**Kết quả cần thấy:** cài đặt kết thúc không có lỗi và dòng kiểm tra in `Moi truong OK`.

Một số môi trường tạo bằng `uv` chưa có pip. Nếu gặp `No module named pip`, bổ sung pip rồi chạy lại lệnh cài:

```powershell
.\.venv\Scripts\python.exe -m ensurepip --upgrade
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Nếu máy đang dùng `uv`, có thể thay hai lệnh trên bằng:

```powershell
uv pip install --python .\.venv\Scripts\python.exe -e ".[dev]"
```

Đây là hai cách thay thế nhau; chỉ cần chọn một. Không xóa `.venv` chỉ vì thiếu pip.

### Mở sa bàn đầu tiên

```powershell
.\.venv\Scripts\python.exe -X utf8 run_app.py scenarios/bai_do_xe.json
```

**Kết quả cần thấy:** cửa sổ **Autopark — hỗ trợ đỗ xe**, một sa bàn có xe, chỗ đỗ và nút **Tìm đường đỗ**. Lệnh giữ PowerShell bận cho tới khi đóng cửa sổ; đó là hành vi bình thường.

Khi đã cài xong, các lần sau chỉ cần lệnh mở ứng dụng. Có thể dùng `chay_app.cmd` với cùng tham số:

```powershell
.\chay_app.cmd scenarios/bai_do_xe.json
```

Nếu bỏ tên kịch bản, ứng dụng mở `scenarios/bai_do_xe_lon_xon.json`, sa bàn nhiều vật cản hơn.

**Về các tệp `.lock`:** `requirements-phase0.lock` ghi phiên bản thư viện của máy tham chiếu; `cai_dat.cmd` cài theo tệp này và thêm nhiều công cụ ngoài mô phỏng cơ bản. Chỉ dùng khi cần tái tạo môi trường đó. Nếu một phiên bản cố định không tải được trên máy của bạn, luồng `pip install -e ".[dev]"` ở trên vẫn là cách bắt đầu; hãy ghi lại khác biệt phiên bản khi báo kết quả kiểm thử.

## 3. Thử một lượt đỗ

Giữ nguyên xe và chỗ đỗ của sa bàn mẫu trong lần đầu. **Phiên đỗ** là một lần từ tìm đường đến xe đỗ xong hoặc bị dừng.

1. Bấm **Tìm đường đỗ**. Chờ đường đi xuất hiện; các đoạn tiến và lùi có màu khác nhau.
2. Bấm **Xem trước** để xem xe dự kiến chạy như thế nào. Bấm **Kết thúc xem trước** để trở lại trạng thái sẵn sàng.
3. Bấm **Bắt đầu đỗ**. Xe mô phỏng bắt đầu di chuyển; nút chính đổi thành **Dừng xe**.
4. Chờ xe tới đích. Khi hoàn tất, nút chính đổi thành **Đỗ lại**. Có thể bấm **Lưu phiên…** để lưu kết quả trước khi thay đổi sa bàn.

Bạn đã chạy được phần cốt lõi khi thấy đủ ba việc: tìm ra đường, xe đi theo đường và kết thúc ở chỗ đỗ.

### Thử hành vi dừng

Chạy lại một lượt, rồi bấm **Vật cản giả** hoặc **Mất dữ liệu** khi xe đang chạy. Ứng dụng tạo một tình huống lỗi để kiểm tra cơ chế dừng. Xe dừng và giao diện nêu lý do; đây là kết quả mong đợi của bài thử.

Sau khi dừng, bấm **Chọn lại vị trí**, chỉnh sa bàn nếu cần rồi tìm đường mới. Nút **Lưu phiên…** dùng khi xe đã dừng. Tệp lưu có thông tin theo thời gian để xem lại điều gì đã xảy ra; loại dữ liệu này thường được gọi là **log**.

### Thay sa bàn và thông số xe

Mở **Sa bàn +** để xem các thẻ thiết lập. Thẻ **Mô phỏng** có ô **Nhánh chạy khi bấm Bắt đầu đỗ**; người mới dùng **Mô phỏng giai đoạn 0 (mặc định)**. Thẻ **Xe** có ô **Cấu hình xe**. Dùng **Lưu thành…** khi muốn tạo sa bàn riêng và giữ lại bản mẫu.

| Muốn thử | Lệnh hoặc tệp |
|---|---|
| Sa bàn nhiều xe, vật cản | `run_app.py scenarios/bai_do_xe_lon_xon.json` |
| Có vùng chưa quan sát, được xem như vật cản | `run_app.py scenarios/giai_doan_0_unknown.json` |
| Một bài nghiệm thu mẫu | `run_app.py scenarios/nghiem_thu/do3b.json` |
| Xe chạy tối đa 0,10 m/s | Thêm `--vehicle-config configs/vehicle_nghiem_thu.json` |
| Chặn đường cần đổi tiến/lùi quá nhiều lần | Thêm `--max-cusps 2` để chỉ cho tối đa 2 lần đổi chiều |

Các lệnh rút gọn trong bảng cần tiền tố `.\.venv\Scripts\python.exe -X utf8`. Ví dụ đầy đủ:

```powershell
.\.venv\Scripts\python.exe -X utf8 run_app.py scenarios/sa_ban_3x2_hai_hop.json --vehicle-config configs/vehicle_nghiem_thu.json
```

`vehicle_default.json` chứa thông số giả định, chưa phải số đo xe thật. Bộ 9 sa bàn trong `scenarios/nghiem_thu/` tự chọn xe nghiệm thu và áp giới hạn riêng. Các ngưỡng nghiệm thu còn là đề xuất; xem [kịch bản nghiệm thu](docs/KICH_BAN_NGHIEM_THU.md) trước khi dùng chúng để kết luận đạt hay không đạt.

## 4. Test, bằng chứng và replay

**Test** là chương trình kiểm tra tự động. **Replay** là chạy lại dữ liệu đã lưu để xem phần mềm có cho cùng kết quả hay không.

### Kiểm tra nhanh sau khi cài hoặc sửa mã

Các test sau chỉ dùng mô phỏng và thư viện cơ bản cùng nhóm `dev`:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_geometry.py tests/test_vehicle_model.py tests/test_ui_smoke.py
Remove-Item Env:QT_QPA_PLATFORM
```

`offscreen` cho phép kiểm tra giao diện mà không mở cửa sổ. **Kết quả cần thấy:** dòng cuối có `passed`, không có `failed` hay `ERROR`. Đọc số test và thời gian từ chính lần chạy của bạn. Lệnh xóa biến ở cuối giúp lần mở ứng dụng tiếp theo hiện cửa sổ bình thường.

Đây là bước kiểm tra môi trường và luồng mô phỏng. Khi sửa một chức năng, chạy thêm các test của chức năng đó theo [hướng dẫn đóng góp](../CONTRIBUTING.md).

### Chạy toàn bộ bộ test

Bộ test đầy đủ còn nhập mã camera và LiDAR. Cài thêm thư viện trước:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,video,lidar]"
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -X utf8 -m pytest
Remove-Item Env:QT_QPA_PLATFORM
```

Các test cần PyTorch hoặc công cụ firmware có thể được bỏ qua (`skipped`) khi chưa có công cụ tương ứng. Lý do bỏ qua xem bằng `pytest -rs`. Chạy toàn bộ có thể mất nhiều phút; không cần làm việc này mỗi lần mở ứng dụng. Test có giới hạn thời gian nên chạy khi máy ít tải.

### Tạo một bộ kết quả và phát lại

Lệnh tạo kết quả dưới đây xuất cả video nên cần nhóm `video` đã cài ở trên. Chọn một thư mục đầu ra mới cho mỗi lần:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.phase0 --out runs/thu_nghiem_moi
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.replay runs/thu_nghiem_moi/obstacle
```

Lệnh đầu tạo năm ca `parking`, `reverse`, `noisy`, `obstacle`, `data_loss` cùng `summary.json`. Ba ca đầu đỗ xong; hai ca cuối dừng do tình huống được cố ý tạo ra. Mỗi ca có kết quả, log và video. Lệnh thứ hai in `Replay OK: ...` nếu phát lại ca vật cản thành công.

Với log qua bo điều khiển, replay so các quyết định của phần mềm với bản ghi. Kết quả khớp không có nghĩa xe thật đã được kiểm chứng. [Lệnh nâng cao](docs/LENH_NANG_CAO.md) có các lệnh JUnit, replay VehicleIO và chấm nghiệm thu. Những báo cáo cũ luôn gắn với ngày, máy và commit cụ thể; xem [báo cáo giai đoạn 0](../BAO_CAO_GIAI_DOAN_0.md) để tra kết quả đã lưu.

## 5. Cài môi trường AI và lấy dữ liệu

Chỉ làm mục này khi cần AI. Phần AI nhận ảnh camera và phân loại từng vùng ảnh, chẳng hạn vùng có thể đi và vật cản. Nó cần thư viện và dữ liệu riêng nên dùng `.venv-train`.

Luồng cài đã có trong dự án dành cho **Python 3.12, GPU NVIDIA và driver hỗ trợ CUDA 12.8**. CUDA là công nghệ để PyTorch dùng GPU. Khi máy đáp ứng cấu hình này, chạy:

```powershell
.\cai_dat_train.cmd
```

Script cài theo `requirements-train.lock` rồi in phiên bản torch, trạng thái `CUDA` và tên GPU. Cần thấy `CUDA True` trước khi dùng các cấu hình huấn luyện GPU. Nếu môi trường cũ thiếu pip, dùng cách `ensurepip` ở mục 2 với đường dẫn `.venv-train`.

**Tải mã bằng Git không tải kèm các tài nguyên sau:**

| Tài nguyên | Dùng để làm gì | Cách chuẩn bị |
|---|---|---|
| `runs/ai_woodscape_rtx4000_v1/best.pt` | Trọng số mô hình đã học, còn gọi là checkpoint | Chép từ máy có mô hình và đối chiếu theo [hướng dẫn chuyển máy](docs/MAY_NOP_DO_AN.md), hoặc huấn luyện lại |
| `datasets/prepared/` | Dữ liệu đã xử lý để huấn luyện | Làm theo [tải và kiểm tra dữ liệu](datasets/TAI_VA_KIEM_TRA.md) |
| `runs/rig_recordings/` | Bản ghi nhiều camera/LiDAR | Chép bản ghi có sẵn hoặc tự ghi ở mục 7 |
| `calibration/`, ngoại tham và ROI đã đo | Đổi ảnh camera thật thành vị trí trên sa bàn | Hiệu chuẩn theo mục 8 |

AI tham chiếu dùng bộ dữ liệu WoodScape. Đọc [giấy phép dữ liệu](docs/GIAY_PHEP_DU_LIEU.md) trước khi tải và dùng. Không cần tải bộ dữ liệu nếu chỉ mở mô phỏng.

## 6. Huấn luyện và suy luận

**Huấn luyện** tạo mô hình từ dữ liệu có nhãn. **Suy luận** dùng mô hình đã học để dự đoán trên ảnh mới.

Nếu đã có checkpoint, bắt đầu bằng một ảnh. Thay `duong_dan_anh.jpg` bằng tệp có thật:

```powershell
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.predict --checkpoint runs/ai_woodscape_rtx4000_v1/best.pt --input duong_dan_anh.jpg --out runs/du_doan_moi --threshold 0.15
```

Kiểm tra ảnh kết quả trong thư mục `--out`. Ngưỡng `0.15` là tham số thử nghiệm, chưa được nghiệm thu trên sa bàn thật.

Để tự huấn luyện, trước hết chuẩn bị dữ liệu theo mục 5, rồi chạy:

```powershell
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.verify_cache
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.train --config configs/train_woodscape_rtx4000_baseline.json --out runs/ai_luot_moi
```

Chỉ chuyển sang huấn luyện khi bước kiểm dữ liệu thành công. Cấu hình ví dụ dành cho máy GPU tham chiếu; đọc [hướng dẫn huấn luyện](../HUAN_LUYEN.md) để chọn cấu hình theo máy, hiểu cách đánh giá và nơi lưu mô hình.

## 7. LiDAR, camera và bàn thử

**LiDAR** đo khoảng cách bằng laser. **Bàn thử** là nơi kiểm tra các cảm biến và phần mềm trước khi lắp lên xe. Thư viện cho các công cụ không dùng AI:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[video,lidar]"
```

Để xem giao diện LiDAR trước khi có thiết bị:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app --no-connect
```

`--no-connect` mở cửa sổ nhưng chưa mở thiết bị. Khi đã cắm RPLIDAR C1, tìm số COM trong Device Manager và sửa `lidar_port` ở [configs/thiet_bi.json](configs/thiet_bi.json). `COM3` trong tệp là cấu hình từ máy trước, có thể khác máy bạn.

Các lệnh kết nối thật, ghi dữ liệu và phát lại nằm trong [lệnh nâng cao](docs/LENH_NANG_CAO.md). Mỗi nhóm đều ghi rõ cần thiết bị hay bản ghi. Tài liệu theo công việc:

- [Bắt đầu với LiDAR](docs/GIAI_DOAN_1_LIDAR.md): đọc vòng quét và kiểm khoảng cách.
- [Ghi và phát lại bàn thử](docs/GHI_PHAT_LAI_BAN_THU.md): camera và LiDAR, kể cả ghi trong phiên đỗ.
- [AI camera trong phiên đỗ](docs/AI_DIEU_KHIEN_XE.md): thêm vật cản từ camera sau khi hiệu chuẩn đạt yêu cầu.

Có checkpoint chưa đủ để AI đặt vật cản đúng chỗ trên sa bàn. Camera thật còn cần hiệu chuẩn ở mục 8; nếu thiếu, ứng dụng báo lý do chặn.

## 8. Chuẩn bị camera và định vị

**Định vị** là xác định xe đang ở đâu và quay về hướng nào. Bộ ba vị trí x, y và góc quay được gọi là **tư thế** của xe.

Với camera, làm theo thứ tự sau:

| Bước | Câu hỏi cần trả lời | Tài liệu |
|---|---|---|
| 1. Hiệu chuẩn nội tham | Ống kính làm ảnh méo thế nào? | [Hiệu chuẩn camera](docs/HIEU_CHUAN_CAMERA.md) |
| 2. Đo ngoại tham và ROI | Camera đặt đâu trên xe? Phần nào của ảnh được dùng? | [Ngoại tham và vùng ảnh sử dụng](docs/NGOAI_THAM_VA_ROI.md) |
| 3. Kiểm ảnh nhìn từ trên xuống (BEV) | Một điểm ảnh được đặt đúng chỗ trên mặt sàn chưa? | [BEV](docs/BEV.md) |
| 4. Nếu cần đánh giá vị trí xe độc lập | Camera trên cao đo tư thế xe ra sao? | [Tham chiếu trên cao](docs/THAM_CHIEU_TREN_CAO.md) |

Với LiDAR, bắt đầu từ [định vị trên bản đồ](docs/DINH_VI_LIDAR.md), rồi tới [dựng bản đồ và cấp tư thế cho phiên đỗ](docs/NGUON_TU_THE_LIDAR.md). Công việc gồm ghi quét ở nhiều vị trí, đo một mốc trên sa bàn, dựng bản đồ, kiểm định vị trên bản ghi rồi mới tích hợp vào phiên.

Các cấu hình mẫu có giá trị giả định. Muốn dùng trên xe thật phải thay bằng số đo và hoàn thành kiểm tra được nêu trong tài liệu tương ứng.

## 9. Chế độ điều khiển, firmware và bo ảo

Trong **Sa bàn +**, thẻ **Mô phỏng** chọn cách chạy; thẻ **Bo điều khiển** chọn nơi nhận lệnh và nguồn tư thế. Đây là hai lựa chọn khác nhau.

| Nhánh chạy | Ý nghĩa | Khi nào dùng |
|---|---|---|
| Mô phỏng giai đoạn 0 (SIM) | Phần mềm tự mô phỏng xe và cảm biến | Bắt đầu học dự án, sửa thuật toán hoặc giao diện |
| VehicleIO | Phần mềm gửi lệnh qua lớp giao tiếp với bo | Kiểm đường đi của lệnh với bo mô phỏng hoặc QEMU |
| Quan sát | Phần mềm tính và ghi lệnh nhưng không gửi COMMAND điều khiển | So lệnh đề xuất với một lần lái; vẫn có trao đổi trạng thái với bo |

**Firmware** là chương trình C++ chạy trên ESP32-S3. **Bo mô phỏng** là mô hình bằng Python. **Bo ảo QEMU** chạy bản firmware ESP32-S3 trong phần mềm giả lập; chiếc xe vẫn được mô phỏng trên máy tính. Các mức thử này giúp kiểm từng phần, chưa thay cho kiểm tra trên bo và xe thật.

Muốn làm firmware, đọc [README firmware](firmware/esp32_vehicle/README.md). Cần CMake và trình biên dịch C++ để kiểm lõi trên máy tính; cần PlatformIO để biên dịch cho ESP32-S3. Muốn chạy bo ảo cần thêm QEMU của Espressif và khai đường dẫn công cụ trong `configs/thiet_bi.json`.

**Các đường dẫn `D:/xetulai/_platformio/...` trong tệp hiện tại thuộc máy trước.** Thay chúng bằng đường dẫn có thật trên máy bạn trước khi chạy QEMU. Có thể kiểm công cụ đã khai bằng:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.transport.qemu_board kiem
```

Lệnh này có thể biên dịch firmware lần đầu, chạy bo ảo, đọc phản hồi rồi tắt. Nếu thiếu công cụ, nó báo lỗi cấu hình. Chi tiết cài đặt và giới hạn: [mô phỏng firmware](docs/MO_PHONG_FIRMWARE.md). Lệnh kiểm C++, biên dịch và chạy bo ảo lâu dài nằm ở [lệnh nâng cao](docs/LENH_NANG_CAO.md).

Khi đã thiết lập xong, chọn **Bo ảo QEMU (firmware xe trong giả lập)**, bấm **Khởi động bo ảo**, rồi dùng nhánh VehicleIO với xe mặc định. Xe nghiệm thu 0,10 m/s có thể bị từ chối do giới hạn firmware chưa khớp (`LIMITS_MISMATCH`); không sửa ngưỡng chỉ để bỏ qua kiểm tra này.

Đường chạy với bo thật còn các điều kiện chưa được xác minh, được mô tả trong [giao thức xe](docs/GIAO_THUC_XE.md), [chế độ quan sát](docs/CHE_DO_QUAN_SAT.md) và [nguồn tư thế LiDAR](docs/NGUON_TU_THE_LIDAR.md). Hồ sơ hiện có chưa chứng minh một chiếc xe thật đã tự đỗ hoàn chỉnh.

## 10. Cấu trúc mã

Để hiểu một lượt đỗ, đọc theo đường đi: `run_app.py` → `autopark/ui/app.py` → `autopark/ui/main_window.py` → `autopark/application/session.py`. `Session` giữ trạng thái của phiên và gọi phần tìm đường, điều khiển, mô phỏng, kiểm tra an toàn.

| Thư mục trong thư mục Python | Nội dung | Ví dụ việc có thể tham gia |
|---|---|---|
| `autopark/domain/` | Kiểu dữ liệu: xe, tư thế, vật cản, sa bàn | Hiểu cấu trúc dữ liệu trước khi thêm tính năng |
| `autopark/ui/` | Cửa sổ và thao tác người dùng | Làm nhãn, thông báo hoặc thao tác dễ hiểu hơn |
| `autopark/application/` | Điều phối một phiên đỗ và nối các thành phần | Sửa luồng trạng thái hoặc điều kiện bắt đầu/dừng |
| `autopark/planning/` | Tìm đường từ vị trí xe đến đích | Cải thiện đường đi hoặc thời gian tìm đường |
| `autopark/control/` | Tính tốc độ, góc lái để xe bám đường | Kiểm sai số và khả năng bám đường |
| `autopark/geometry/`, `autopark/simulation/` | Hình học, va chạm và xe mô phỏng | Tạo tình huống thử mới |
| `autopark/lidar/`, `autopark/video/`, `autopark/perception/` | LiDAR, camera và AI | Làm việc với bản ghi, hiệu chuẩn hoặc nhận thức |
| `autopark/fusion/`, `autopark/rig/` | Kết hợp dữ liệu và bàn thử | Kiểm dữ liệu nhiều cảm biến |
| `autopark/transport/`, `firmware/` | Giao tiếp với bo và firmware | Kiểm giao thức, mô hình bo hoặc mã C++ |
| `autopark/safety/` | Phát hiện dữ liệu cũ, mất dữ liệu và tình huống cần dừng | Thêm kiểm tra cho một lỗi cụ thể |
| `autopark/storage/`, `autopark/evaluation/` | Lưu, phát lại và đánh giá | Tái hiện lỗi từ log hoặc bổ sung cách đo |
| `configs/`, `scenarios/`, `tests/` | Cấu hình, sa bàn và test | Thêm một sa bàn có mục đích rõ ràng và kiểm kết quả |

Trong mã lõi, khoảng cách dùng mét, thời gian dùng giây, góc dùng radian. Gốc tư thế xe ở tâm trục sau; x hướng trước xe, y sang trái, góc dương quay ngược chiều kim đồng hồ. Một số ô giao diện dùng cm hoặc độ theo nhãn hiển thị; kiểm đơn vị trước khi đưa số vào mã.

Chọn việc đầu tiên và cách gửi thay đổi ở [CONTRIBUTING.md](../CONTRIBUTING.md). [Sơ đồ hệ thống](docs/SO_DO_HE_THONG.md) giải thích các phần liên hệ với nhau thế nào.

## 11. Khi không chạy được

| Biểu hiện | Kiểm tra và cách xử lý |
|---|---|
| `py` hoặc `python` không được nhận diện | Cài Python 3.12 rồi mở PowerShell mới; kiểm lại phiên bản trước khi tạo môi trường. |
| Không tìm thấy `run_app.py` hoặc `pyproject.toml` | Kiểm thư mục bằng hai lệnh `Test-Path` ở mục 1. Bạn cần thư mục Python, nằm bên trong gốc Git. |
| `No module named pip` | Dùng `ensurepip` hoặc `uv pip` theo mục 2; môi trường có thể vẫn dùng tốt. |
| `No module named PySide6`, `numpy` hoặc `shapely` | Chạy lại lệnh cài cơ bản bằng chính `.venv\Scripts\python.exe`. |
| `No module named pytest` | Cài `.[dev]` bằng Python của `.venv`. |
| `No module named cv2` hoặc `serial` | Chức năng đang chạy cần thư viện tùy chọn; cài `.[video,lidar]`. |
| `No Python at ...` sau khi chép từ máy khác | Python trong môi trường trỏ tới máy cũ. Giữ lại thư mục cũ bằng một tên dự phòng chưa tồn tại, tạo `.venv` mới rồi cài theo mục 2. `cai_dat.cmd` có cơ chế đổi tên môi trường hỏng trước khi cài bản theo lock. |
| Python chạy nhưng import hỏng sau khi đổi nơi lưu dự án | Trong thư mục có `pyproject.toml`, chạy lại `.\.venv\Scripts\python.exe -m pip install -e . --no-deps`. |
| Không thấy cửa sổ dù chương trình vẫn chạy | Nếu vừa chạy test, xóa biến bằng `Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue`, rồi mở lại. |
| Chữ tiếng Việt lỗi trong terminal | Dùng `-X utf8` như các lệnh mẫu; khi đọc tệp bằng PowerShell dùng `Get-Content -Encoding utf8`. |
| Cài từ `.lock` báo không có phiên bản phù hợp | Kiểm Python và nền tảng. Để bắt đầu mô phỏng, dùng lệnh cài từ `pyproject.toml` ở mục 2; ghi lại môi trường thực tế khi báo kết quả. |
| Tìm đường không ra sau khi kéo đồ vật | Đảm bảo xe và đích không chồng vật cản, không vượt biên. Mở lại sa bàn mẫu để phân biệt vấn đề dữ liệu với vấn đề cài đặt. |
| Thiếu `torch` hoặc `best.pt` | Đang chạy chức năng AI: dùng `.venv-train` và chuẩn bị checkpoint theo mục 5. |
| LiDAR không kết nối | Kiểm dây, driver CP210x, số COM trong Device Manager và `lidar_port`; đóng chương trình khác đang giữ cổng. |
| AI báo thiếu hiệu chuẩn | Hoàn thành nội tham, ngoại tham và ROI theo mục 8, đọc lý do cụ thể trong giao diện. |
| QEMU báo thiếu công cụ | Sửa đường dẫn QEMU/PlatformIO trong `configs/thiet_bi.json`; đường dẫn của máy cũ không tự chuyển theo dự án. |

Khi cần người khác hỗ trợ, gửi **lệnh đã chạy, thư mục đang đứng, phiên bản Python, toàn bộ thông báo lỗi và cách tái hiện**. Với lỗi trong lúc đỗ, gửi thêm tên sa bàn, cấu hình xe, các nút đã bấm và log nếu có.
