# Lệnh nâng cao

Trang này dành cho người đã chạy được mô phỏng theo [hướng dẫn cài đặt](../README.md). Chọn đúng phần việc; không cần chạy lần lượt mọi lệnh.

**Thư mục chạy lệnh:** thư mục Python có `pyproject.toml` và `run_app.py`, tức thư mục cha của `docs/`. Chỉ các lệnh CMake và PlatformIO dưới đây chuyển sang `firmware/esp32_vehicle`.

Các tên như `phien_moi`, `cho_1.npz`, `anh_thu.jpg` là ví dụ. Thay bằng dữ liệu của bạn; chọn thư mục đầu ra mới cho mỗi lượt để giữ kết quả trước. Có thể xem tham số của công cụ bằng cách thêm `--help`, sau khi đã cài thư viện của công cụ đó.

## 1. Kiểm thử, lưu kết quả và phát lại

Cần `.venv` có nhóm thư viện `dev,video,lidar`. Kiểm nhanh cách cài ở README trước khi chạy toàn bộ:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -X utf8 -m pytest --junitxml runs/kiem_thu_moi/pytest.xml
Remove-Item Env:QT_QPA_PLATFORM
```

JUnit là tệp XML chứa kết quả từng test, tiện lưu và so giữa các lần. Khi dùng làm bằng chứng chính thức, ghi mã commit (`git rev-parse HEAD`), trạng thái mã (`git status --short`), môi trường, lệnh và mã thoát. Muốn kết luận cho một commit, chạy trên đúng commit đó với cây làm việc sạch. Không lấy tổng số test từ báo cáo của commit khác.

Bộ kiểm mở rộng cho mô phỏng:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.robustness --out runs/kiem_thu_mo_rong_moi
```

Phát lại một gói đã xuất bằng **Lưu phiên…**:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.replay runs/goi_phien_da_luu
```

Thay đường dẫn bằng **thư mục gói**, không phải tệp CSV đơn lẻ. Với gói SIM, đầu ra thành công bắt đầu bằng `Replay OK`. Với gói VehicleIO, công cụ so lệnh và sự kiện trên đầu vào đã ghi; mã thoát là 0 = khớp, 1 = khác, 2 = không hỗ trợ/thiếu dữ liệu để phát lại, 3 = lỗi bất ngờ. Log cũ chưa có băng phát lại không đủ dữ liệu cho công cụ này.

Lưu ý hiệu năng: ứng dụng và pytest tự xử lý chế độ tiết kiệm CPU EcoQoS trên Windows. Chỉ khi chủ động nghiên cứu ảnh hưởng của nó mới đặt `$env:AUTOPARK_KEEP_ECOQOS = "1"`. Chi tiết lịch sử và các script kiểm trên một commit: [biên bản chuyển máy](CHUYEN_MAY_BAN.md).

## 2. Chấm nghiệm thu và tạo tình huống lỗi

Cần đọc [kịch bản nghiệm thu](KICH_BAN_NGHIEM_THU.md), có log của lần chạy và chọn đúng mức thử. `MP` là mô phỏng. Các ngưỡng trong `configs/nguong_nghiem_thu.json` còn là đề xuất.

Ví dụ chấm một log DO-1 ở mức mô phỏng, dùng tư thế thật của xe mô phỏng làm tham chiếu:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.score_run --scenario DO-1 --attempt 1 --level MP --log runs/nghiem_thu/mo_phong/do1_l01/lan_chay_vehicle_io --sim-truth --layout scenarios/nghiem_thu/do1.json --report runs/nghiem_thu/mo_phong/bien_ban_mo_phong.csv
```

Thay `--log` bằng thư mục log có thật và `--layout` bằng đúng sa bàn đã dùng. Công cụ ghi biên bản cùng tệp chi tiết; nó đề xuất kết quả dựa trên dữ liệu. `--sim-truth` chỉ có ý nghĩa khi chiếc xe được mô phỏng, kể cả khi firmware chạy trong QEMU. Với xe thật cần nguồn tham chiếu độc lập qua `--reference` hoặc `--r2-points` theo tài liệu.

Diễn tập lỗi bằng nguồn mô phỏng, không cần cảm biến hay bo thật:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.fault_drill pose --mode hold --repeat 10 --out runs/fault_drill/thu_moi --name cb6
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.fault_drill hang --seconds 1 --phases 0 1 2 3 --out runs/fault_drill/thu_moi --name cb5b
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.fault_drill camera --mode stall --repeat 10 --out runs/fault_drill/thu_moi --name cb2
```

Ba lệnh lần lượt giữ nguyên dữ liệu tư thế, làm treo bên gửi lệnh và ngừng nguồn camera giả. Đọc báo cáo đạt/không đạt cùng lý do, không chỉ kiểm chương trình có chạy xong.

Sinh một bộ sa bàn nghiệm thu vào thư mục mới:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.acceptance_scenarios --out runs/sa_ban_nghiem_thu_moi --vehicle-config configs/vehicle_nghiem_thu.json
```

`--force` ghi đè các tệp đã có; chỉ thêm khi có chủ ý thay chúng. Có thể dùng `--dry-run` để xem danh sách mà chưa ghi.

## 3. AI: đánh giá một mô hình đã có

Cần `.venv-train`, checkpoint và dữ liệu đã chuẩn bị. Mục 5–6 của [README](../README.md) giải thích cách có các tài nguyên này.

```powershell
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.verify_cache
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.evaluate --checkpoint runs/ai_woodscape_rtx4000_v1/best.pt --split val --out runs/cham_val_moi
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.predict --checkpoint runs/ai_woodscape_rtx4000_v1/best.pt --input anh_thu.jpg --out runs/du_doan_moi --threshold 0.15
```

`val` là tập kiểm định đã tách khỏi dữ liệu huấn luyện. Đánh giá tốt trên WoodScape chưa chứng minh mô hình tốt với camera trên xe; xem [huấn luyện](../../HUAN_LUYEN.md) và [gán nhãn sa bàn](GAN_NHAN_SA_BAN.md).

## 4. LiDAR, camera: mở thiết bị thật hoặc dùng bản ghi

### Đọc LiDAR thật

Cần RPLIDAR C1, driver CP210x, thư viện `lidar` và số COM đúng trong `configs/thiet_bi.json`. Hai lệnh sau **mở cổng thiết bị**; lệnh thứ hai kết nối LiDAR khi mở giao diện:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.lidar.rplidar_c1 info
.\.venv\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app
```

Đọc được thông tin C1 là bước kiểm kết nối. Nếu nhiều thiết bị cùng dùng CP210x, khai đúng COM thay vì dùng `auto`.

### Ghi bàn thử có AI

Cần `.venv-train`, checkpoint, các camera đã nhận đúng cổng hub và LiDAR đã cấu hình. Lệnh này **mở bốn camera và LiDAR**, chạy AI trong 60 giây rồi lưu số đo và bản ghi:

```powershell
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 60 --name phien_moi --out runs/rig_bench/phien_moi --record runs/rig_recordings/phien_moi
```

`--ports` là cổng hub theo cấu hình của dự án, không phải các số camera chọn tùy ý. `--lidar` lấy COM từ tệp thiết bị; bỏ tùy chọn này nếu không dùng LiDAR. Thêm `--sync-mark` nếu cần dấu nháy đầu/cuối để đồng bộ với video bên ngoài; `--sync-every 30` thêm một dấu mỗi 30 giây.

### Phát lại bản ghi

Cần bản ghi có thật ở đường dẫn ví dụ. Lệnh đầu chạy AI bằng `.venv-train`; lệnh thứ hai chỉ mở giao diện xem và cần thư viện `video,lidar` trong `.venv`. Cả hai dùng bản ghi, không mở cảm biến:

```powershell
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --replay runs/rig_recordings/phien_moi --name phat_lai --out runs/rig_bench/phat_lai
.\.venv\Scripts\python.exe -X utf8 -m autopark.ui.rig_app --replay runs/rig_recordings/phien_moi --no-ai
```

### Ghi hoặc phát lại cảm biến trong phiên đỗ

Lệnh mở giao diện dưới đây **mở camera và LiDAR thật**. Cần cùng điều kiện với bàn thử AI; để AI cung cấp vật cản cho phiên còn cần hiệu chuẩn hợp lệ. Bắt đầu ghi bằng ngăn **Ghi cảm biến** khi xe chưa chạy:

```powershell
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app --camera-ai --cam-ports 1 2 3 4 --record-root runs/session_recordings --record-format jpg
```

Phát lại camera và LiDAR trên cùng đồng hồ bằng bản ghi vừa tạo; thay `phien_da_ghi` bằng tên thư mục thật:

```powershell
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app --camera-ai --session-replay runs/session_recordings/phien_da_ghi
```

Chỉ xem LiDAR của bản ghi:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app --recording runs/session_recordings/phien_da_ghi
```

Không ghép `--cam-replay` và `--recording` để giả định chúng đồng bộ; dùng `--session-replay` khi cần cùng một cảnh theo thời gian. Chi tiết định dạng, dung lượng và hạn chế ở [ghi/phát lại](GHI_PHAT_LAI_BAN_THU.md).

## 5. Hiệu chuẩn và định vị

### Camera trên cao

Cần camera, nhóm `video` và bảng hiệu chuẩn theo [hướng dẫn camera](HIEU_CHUAN_CAMERA.md). Liệt kê thiết bị trước:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.video.camera_bench list
```

Sau khi xác định đúng index, đặt biến rồi mở công cụ. `0` dưới đây chỉ là ví dụ, phải thay theo kết quả vừa liệt kê. Cả hiệu chuẩn và ghi video đều **mở camera thật**:

```powershell
$cameraIndex = 0
.\.venv\Scripts\python.exe -X utf8 -m autopark.ui.calib_app --index $cameraIndex --camera-name tren_cao --size 1280x720
.\.venv\Scripts\python.exe -X utf8 -m autopark.video.overhead_record --index $cameraIndex --size 1280x720 --seconds 20 --out runs/tren_cao/thu_moi --name san_trong
```

Công cụ hiệu chuẩn lưu `calibration/cam_tren_cao_1280x720.json`. Độ phân giải khi ghi phải khớp hiệu chuẩn. Chuỗi tiếp theo là tạo bảng marker, đo mốc sàn, khớp mặt sàn, kiểm độ chính xác TC-1, rồi trích tư thế xe. Lệnh tạo mẫu:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.perception.aruco_sheet --ids 0-47 --size-mm 100 --out calibration/bang_in/aruco
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.overhead_ref survey-template --size 3.0x2.0 --step 0.5 --check 8 --out runs/tren_cao/thu_moi/moc_sa_ban.csv
```

Mẫu CSV cần điền số đo thật. Lệnh `floor`, `tc1`, `track` cùng đầu vào tương ứng ở [tham chiếu trên cao](THAM_CHIEU_TREN_CAO.md); không thể bỏ bước đo và kiểm rồi coi tư thế xuất ra là tham chiếu đạt chuẩn.

### Dựng bản đồ LiDAR và kiểm định vị bằng bản ghi

Cần nhóm `lidar`, các tệp quét `.npz` có thật và tọa độ mốc đã đo. Ví dụ dưới đây dùng mốc `(0.5, 1.0, 0°)`; thay bằng số đo của **tâm LiDAR** trong hệ sa bàn. Tọa độ tính bằng mét, góc dòng lệnh tính bằng độ:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.lidar.map_builder --placement runs/lidar/cho_1.npz --anchor 0.5 1.0 0 --placement runs/lidar/cho_2.npz --scenario scenarios/sa_ban_3x2_hai_hop.json --out runs/lidar_maps/thu_moi
.\.venv\Scripts\python.exe -X utf8 -m autopark.lidar.pose_estimator --map runs/lidar_maps/thu_moi --recording runs/lidar/kiem_dinh_vi.npz --out runs/lidar_pose/thu_moi --initial 0.5 1.0 0
```

Tư thế `--initial` mặc định là của xe; cần cấu hình vị trí gá LiDAR đúng. Với bản ghi cảm biến đứng riêng trên bàn, xem tùy chọn `--sensor-frame` trước khi dùng cùng số đo như ví dụ.

Nếu dựng bản đồ bị từ chối, `map_build.json` có `ok: false`; đọc lý do và sửa dữ liệu đo. Bản đồ dùng cho phiên phải có mốc neo vào hệ sa bàn. Đọc [nguồn tư thế LiDAR](NGUON_TU_THE_LIDAR.md) trước khi tích hợp. Để chỉ xem lựa chọn LiDAR mô phỏng trong giao diện, chưa mở cảm biến thật:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app --no-connect --pose-source lidar_sim
```

## 6. Firmware và bo ảo QEMU

### Kiểm bộ dữ liệu mẫu chung Python/C++

Chạy trong thư mục Python; chưa cần CMake, PlatformIO hay bo:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.transport.vectors --check
```

Kết quả mong đợi có `vectors.json is up to date`. `--write` thay đổi tệp mẫu; chỉ dùng khi đã quyết định thay đổi hành vi tham chiếu, không dùng để che một lỗi lệch kết quả.

### Kiểm lõi C++ trên máy tính

Cần CMake và trình biên dịch C++ nằm trong PATH. `Push-Location` chuyển vào thư mục firmware; `Pop-Location` trở lại thư mục Python:

```powershell
Push-Location .\firmware\esp32_vehicle
cmake -S test/host -B build/host -DCMAKE_BUILD_TYPE=Release
cmake --build build/host --config Release
ctest --test-dir build/host -C Release --output-on-failure
Pop-Location
```

Chỉ chuyển bước khi lệnh trước thành công. Kết quả ctest phải báo không có test thất bại. Số phép kiểm thay đổi theo phiên bản mã.

### Biên dịch firmware ESP32-S3

Cần PlatformIO trong môi trường công cụ riêng và các phụ thuộc được mô tả trong [README firmware](../firmware/esp32_vehicle/README.md). Nếu lệnh `pio` đã có trên PATH:

```powershell
Push-Location .\firmware\esp32_vehicle
pio run -e esp32s3
Pop-Location
```

Đây là lệnh biên dịch, chưa nạp firmware vào bo. Lần đầu cần tải nền tảng và bộ công cụ. Bản `esp32s3_qemu` dành riêng cho giả lập, không dùng để nạp lên xe.

### Chạy bo ảo

Cần QEMU của Espressif, PlatformIO và các đường dẫn hợp lệ trong `configs/thiet_bi.json`; cài thêm nhóm Python `lidar` để có pyserial. Chạy từ thư mục Python:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.transport.qemu_board kiem
```

Lệnh tự biên dịch nếu cần, khởi động bo ảo, đọc phản hồi rồi tắt. Mã thoát 0 khi nhận đủ khung trong cửa sổ đo, 1 khi thiếu khung, 2 khi thiếu công cụ hoặc không khởi động được. Cần máy đã cấu hình đúng trước khi chạy:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.transport.qemu_board chay
```

`chay` giữ bo ảo chạy tới khi nhấn Ctrl+C. Mặc định giao tiếp qua `socket://127.0.0.1:5555`; thêm `--help` sau `chay` để xem cách đổi cổng. Test chuyên biệt:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_firmware_qemu.py
```

QEMU không mô phỏng đầy đủ cảm biến và đầu ra điện của xe. Các kết quả ở đây là kiểm phần mềm; giới hạn chi tiết ở [mô phỏng firmware](MO_PHONG_FIRMWARE.md).

## 7. Đo hiệu năng giao diện

Cần nhóm `dev,video,lidar` và máy Windows dùng để đo. Các công cụ này mở/chạy giao diện, có thể mất nhiều phút; chỉ dùng khi đang điều tra ảnh hưởng EcoQoS hoặc nhịp điều khiển:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.ecoqos_gui do --ra runs/ecoqos_giao_dien_moi
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.ecoqos_gui tom-tat --ra runs/ecoqos_giao_dien_moi
```

Thử ngắn một cấu hình khi xe mô phỏng đang chạy:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.ecoqos_gui do-chay --ra runs/ecoqos_chay_moi --nhanh SIM --bien-the gui_system --khoi 1 --lap 1 --cho 2
```

Giữ lại điều kiện máy, cấu hình và đầu ra khi so kết quả. Xem [biên bản chuyển máy](CHUYEN_MAY_BAN.md) để hiểu các phép đo trước đây.
