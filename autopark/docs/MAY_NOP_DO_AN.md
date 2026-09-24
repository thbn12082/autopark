# Laptop RTX 3050 Ti — máy mang đi nộp đồ án: cài đặt và đo lại (24/09/2026)

**Vai trò hai máy** (người dùng xác nhận 24/09/2026):

| Máy | Vai trò |
|---|---|
| Máy bàn i9-14900 + RTX 4000 Ada 20 GB | Máy phát triển chính. Mọi số đo trong các tài liệu đến 24/09 là trên máy này. |
| Laptop i7-12700H + RTX 3050 Ti Laptop 4 GB | Máy mang đi nộp và trình diễn đồ án. Đã chạy giai đoạn 0 (mô phỏng, 20/09). Chưa đo LiDAR, camera hay AI trực tiếp trên máy này. |

Số dùng cho khóa luận phải đo trên máy trình diễn. Hai máy khác nhau ở những chỗ ảnh hưởng thẳng tới kết quả:

- **GPU:** 4 GB VRAM so với 20 GB, và chậm hơn. Thời gian AI phải đo lại.
- **Bộ điều khiển USB và số cổng:** khác máy bàn. Hiện tượng khung MJPEG bị cắt khi bốn camera chạy chung
  ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 2) có thể nhẹ hơn hoặc nặng hơn.
- **Cổng COM của LiDAR:** Windows cấp số COM theo từng máy (máy bàn là COM4). Lệnh đo tự tìm.

## 1. Chuẩn bị trên máy bàn (đã làm 24/09)

Thư mục `D:\CHUYEN_SANG_LAPTOP\` (ngoài repo) chứa những thứ laptop cần mà GitHub không có:

- `autopark\runs\ai_woodscape_rtx4000_v1\best.pt`, mô hình AI tham chiếu, 38 MB.
- `config_resolved.json` của mô hình đó.
- `SHA256.txt`: mã SHA-256 của best.pt là `0459c3f4bf9a2b2307b4daf7d70f95db453718d6eaafe09d61e3c52d7ef90ccc`.
- `DOC_TRUOC.txt`: tóm tắt các bước dưới đây.

Thư mục này nằm cùng ổ D với bản gốc, nên **chưa phải bản sao lưu thật**. Chép nó sang USB hoặc sang laptop thì mới có
bản thứ hai ở nơi khác.

**Tham chiếu máy bàn** (trong repo, thư mục [evidence/may_ban/](evidence/may_ban/)):

| Tệp | Đo lúc | Mã | Trạng thái git |
|---|---|---|---|
| [tham_chieu_20260924.json](evidence/may_ban/tham_chieu_20260924.json) | 24/09 15:25 | mã lúc đó: quy tắc chờ cũ (ngưỡng theo camera nhanh nhất), chưa làm nóng AI | đã commit (trong `2bd37b6`) |
| [tham_chieu_20260924_toi.json](evidence/may_ban/tham_chieu_20260924_toi.json) *(thêm muộn tối 24/09/2026)* | 24/09 19:08 | mã mới chưa commit trên `2bd37b6`: quy tắc chờ theo nhịp riêng từng camera (`policy.wait_rule = "own_cadence"`), làm nóng AI mọi cỡ lô | **chưa commit** |

Lệnh đo lấy tệp đứng cuối theo tên trong thư mục đó, tức tệp 19:08. Tệp 15:25 giữ lại để đối chiếu. Ở cả hai lần, camera
máy bàn nhìn cùng một chỗ tối.

## 2. Trên laptop

1. **Lấy mã mới nhất.** Trong cmd:
   ```cmd
   git clone https://github.com/thbn12082/autopark
   ```
   Nếu laptop đã có repo thì `git pull` trong thư mục đó.
   *(Cập nhật muộn tối 24/09/2026:)* quy tắc chờ theo nhịp riêng, làm nóng AI và tệp tham chiếu 19:08 **chưa commit**.
   Laptop chỉ có chúng sau khi người dùng commit và push trên máy bàn, rồi chạy lại `git pull` trên laptop. Chưa push thì
   laptop chạy mã `2bd37b6` và so với tham chiếu 15:25, tức cặp mã cũ với tham chiếu cũ.
2. **Chép checkpoint.** Chép thư mục `autopark` trong `D:\CHUYEN_SANG_LAPTOP\` (qua USB) đè vào thư mục `autopark` của repo
   trên laptop. Lệnh này chỉ thêm `runs\ai_woodscape_rtx4000_v1\`. Kiểm mã trong thư mục `autopark` của repo:
   ```cmd
   certutil -hashfile runs\ai_woodscape_rtx4000_v1\best.pt SHA256
   ```
   Kết quả phải trùng mã ở mục 1.
3. **Cài hai môi trường** (cần Python 3.12, mạng Internet):
   - `autopark\cai_dat.cmd` tạo `.venv` (mô phỏng, giao diện, test) theo `requirements-phase0.lock`.
   - `autopark\cai_dat_train.cmd` tạo `.venv-train` (torch CUDA 12.8, bàn thử, hiệu chuẩn, gán nhãn) theo
     `requirements-train.lock`. Cuối lệnh in `CUDA True` và tên GPU. Nếu in `CUDA False`: cập nhật driver NVIDIA. Torch
     bản cu128 cần driver hỗ trợ CUDA 12.8; máy bàn đang dùng driver 596.72.
4. **Driver LiDAR:** cài driver cầu nối CP210x của Silicon Labs nếu Device Manager chưa thấy "Silicon Labs CP210x USB to
   UART Bridge (COMx)". Máy bàn dùng bản 11.6.0.420.
5. **Cắm thiết bị:** hub UGREEN với bốn camera ở đúng các cổng 1–4 như máy bàn, và LiDAR cắm thẳng vào laptop. Đóng mọi
   chương trình đang dùng camera. Để camera nhìn **cùng một cảnh** như khi đo trên máy bàn, vì khung bị cắt ở 720p phụ
   thuộc cảnh.
6. **Đo:** chạy `autopark\do_may_moi.cmd`, khoảng 4 phút. Kết quả nằm ở `autopark\runs\may_moi_<ngày giờ>\`, đọc
   `tom_tat.md` trước.
7. **Mang kết quả về:** chép cả thư mục kết quả về máy bàn, vào `autopark\runs\`, để ghi vào tài liệu.

## 3. Lệnh đo làm gì

`python -m autopark.rig.may_moi` ([mã](../autopark/rig/may_moi.py)) chạy sáu bước. Bước nào lỗi thì ghi lỗi lại rồi chạy
tiếp bước sau.

| Bước | Đo gì | Tệp ra |
|---|---|---|
| `env` | CPU, RAM, Python, torch, CUDA, GPU, VRAM, driver NVIDIA, OpenCV | `env.json` |
| `usb` | Camera và hub Windows thấy, ghép index với cổng hub | `usb_topology.json` |
| `lidar` | Tự tìm cổng CP210x; thông tin và sức khỏe thiết bị; 15 s quét tĩnh có phân tích | `lidar_info.json`, `lidar/` |
| `ai` | Một lô 4 ảnh 640×480 qua mô hình tham chiếu, 60 lô sau 5 lô khởi động; VRAM đỉnh | `ai_latency.json` |
| `rig480` | Bàn thử bốn camera 640×480 + LiDAR + AI, 120 s | `m01_480p_lidar_ai.rig.json` |
| `cam720` | Bốn camera 1280×720, chỉ camera, 30 s: khung bị cắt | `m02_720p_chi_camera.rig.json` |

`tom_tat.md` đặt từng số cạnh số của máy bàn, lấy từ [evidence/may_ban/](evidence/may_ban/) (tệp đứng cuối theo tên; từ
muộn tối 24/09/2026 là [tham_chieu_20260924_toi.json](evidence/may_ban/tham_chieu_20260924_toi.json), mục 1).

*(Thêm muộn tối 24/09/2026)* Bước `ai` và bước `rig480` đo hai thứ khác nhau:

- `ai` tự tạo mô hình, chạy 5 lô 4 ảnh khởi động rồi đo 60 lô 4 ảnh. Nó không dùng phần làm nóng của bàn thử.
- `rig480` chạy bàn thử. Từ mã tối 24/09, bàn thử làm nóng AI cho mọi cỡ lô 4 / 3 / 2 / 1 ảnh ngay sau khi nạp mô hình
  (`AIWorker.warm_up`), rồi mới tính 5 s làm nóng của phiên. Thời gian từng lô làm nóng ghi ở `ai.warm_up_ms` trong
  `m01_480p_lidar_ai.rig.json`; `tom_tat.md` chưa in dòng này. Máy bàn lúc 19:08: 1482 / 1448 / 1553 / 1410 ms, tổng
  ≈ 5,9 s, tức AI sẵn sàng ≈ 6 s sau khi nạp mô hình.

Tùy chọn:

- `--dry-run`: chỉ in kế hoạch.
- `--steps ai rig480`: chỉ chạy vài bước.
- `--lidar COM5`: nếu tự tìm cổng sai.
- `--seconds 600`: phiên 480p dài hơn.

Camera cắm qua hub thì được chọn theo cổng hub. Cắm thẳng vào laptop thì không có số cổng hub, lệnh tự mở theo index
DirectShow. Nó chỉ lấy camera Sunplus 1BCF:0B09 của dự án, theo mã thiết bị, nên webcam gắn sẵn của laptop bị bỏ qua
kể cả khi webcam cũng tên "HD Camera".

## 4. Đọc kết quả

Chưa có ngưỡng nghiệm thu nào được chốt (kế hoạch mục 16.2). Vì vậy `tom_tat.md` chỉ so với máy bàn, không kết luận đạt
hay không đạt. Nên đọc kỹ những điểm sau:

- **AI: một lô 4 ảnh.** Với bốn camera ≈ 24 khung/s, một bộ đến sau mỗi ≈ 42 ms. Lô lâu hơn thế thì AI không theo kịp
  camera, và số bộ AI/s ở `rig480` sẽ thấp hơn ≈ 24.
- **Khung hỏng ở 480p và 720p** trên bộ điều khiển USB của laptop. So với máy bàn thì phải cùng cảnh.
- **LiDAR:** tốc độ quay ≈ 10 Hz và ≈ 510 tia mỗi vòng như máy bàn. Nếu khác thì do máy hay do cáp/cổng.
- **CPU và GPU** của tiến trình, và nhiệt GPU cuối phiên.
- *(Thêm muộn tối 24/09/2026)* **Làm nóng AI** (`ai.warm_up_ms` trong `m01_480p_lidar_ai.rig.json`, mục 3): máy bàn tổng
  ≈ 5,9 s. Laptop GPU yếu hơn nên có thể lâu hơn: CHƯA ĐO.
- *(Thêm muộn tối 24/09/2026)* **Nhịp từng camera ở 720p:** có lần mở camera, một camera chạy ≈ 29 khung/s ở phơi sáng
  tự động, còn các camera kia ≈ 23,85. Camera nào như vậy thay đổi giữa các lần mở: cổng 3 ở s01–s07, t01, t02 (23/09),
  cổng 1 ở t05 (23/09) và lúc 15:25, 17:56 ngày 24/09, không camera nào lúc 19:08 (tham chiếu hiện dùng). Vì vậy một
  camera 29 khung/s trên laptop chưa phải khác biệt do máy. Nếu có, xem thêm cột "bộ thiếu camera chậm": với quy tắc chờ
  theo nhịp riêng, trên máy bàn (o01, 17:56) tình huống này cho 0 bộ bỏ camera khỏe, còn quy tắc cũ (15:25) bỏ 263 / 855
  bộ ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 10.3).

## 5. Giới hạn

- Lệnh đo đã chạy trọn trên máy bàn ngày 24/09 (tạo tệp tham chiếu). Nó **chưa chạy trên laptop**. *(Cập nhật muộn tối
  24/09/2026:)* chạy trọn hai lần trên máy bàn, lúc 15:25 (mã cũ) và 19:08 (mã mới), mỗi lần một tệp tham chiếu (mục 1).
  Lần 19:08: 480p + LiDAR + AI 120 s, bốn camera 23,85 khung/s, 0 khung hỏng, 2.861 bộ, 0 bộ thiếu camera khỏe (15:25: 3),
  AI 23,85 bộ/s, lô trung vị 13,2 ms, LiDAR 10,01 Hz; 720p chỉ camera 30 s, cả bốn ≈ 23,85 khung/s, 716 bộ, 0 bộ bỏ camera
  (15:25: 263 / 855); bước `ai` trung vị 10,4 ms, p95 11,4 ms, VRAM 78 MB. Vẫn chưa chạy trên laptop.
- *(Thêm muộn tối 24/09/2026)* Tham chiếu 19:08 đo bằng mã chưa commit. Khi so, laptop phải chạy cùng bản mã đó (sau khi
  commit, push, `git pull`); ghi mã commit cạnh số của laptop.
- Lúc tạo tham chiếu, camera máy bàn nhìn vào chỗ tối (gầm bàn). Số khung bị cắt ở 720p của tham chiếu chỉ đúng cho cảnh
  đó.
- Không đo độ trễ từ sự kiện thật tới lúc khung tới máy; việc này cần LED nháy.
