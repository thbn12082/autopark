# Laptop RTX 3050 Ti — máy mang đi nộp đồ án: cài đặt và đo lại

Tài liệu này hướng dẫn chuyển môi trường và mô hình AI sang laptop mang đi nộp và trình diễn đồ án, rồi chạy một lệnh đo
để so laptop với máy bàn. Dùng khi cài laptop lần đầu hoặc trước buổi trình diễn. Đo trên laptop cũng là việc 7 trong
[danh sách việc tại chỗ thiết bị](VIEC_TAI_CHO_THIET_BI.md). Chép cả dự án sang một máy bàn khác thì xem
[biên bản chuyển máy](CHUYEN_MAY_BAN.md).

## Hiện trạng (02/10/2026)

- Lệnh đo (`do_may_moi.cmd`) đã chạy trên máy bàn: hai lần ngày 24/09/2026 trên máy bàn trước (15:25 và 19:08), một lần
  ngày 29/09/2026 lúc 12:59 trên máy bàn hiện tại. Lượt 29/09 là tham chiếu đang dùng (mục 1).
- Trên laptop, lệnh đo chưa chạy. Laptop mới chạy giai đoạn 0 (mô phỏng, 20/09/2026); chưa đo LiDAR, camera hay AI, chưa
  chạy ngăn AI camera.
- Các bản sửa lệnh đo ngày 24–25/09/2026 đã có trên `origin/main`, nên laptop chỉ cần `git pull` (mục 2, bước 1).
- Chưa có ngưỡng nghiệm thu nào được chốt, nên kết quả chỉ được so với máy bàn, không kết luận đạt hay không (mục 4).

## Vai trò hai máy

Người dùng xác nhận vai trò hai máy ngày 24/09/2026:

| Máy | Vai trò |
|---|---|
| Máy bàn i9-14900 + RTX 4000 Ada 20 GB | Máy phát triển chính. Từ 29/09/2026 là Dell Precision 3680 cùng cấu hình, LiDAR ở COM3 |
| Laptop i7-12700H + RTX 3050 Ti Laptop 4 GB | Máy mang đi nộp và trình diễn. Đã chạy giai đoạn 0 (mô phỏng, 20/09); chưa đo LiDAR, camera hay AI trên máy này |

Mọi số đo cảm biến, AI và bàn thử trong các tài liệu tới 25/09/2026 là đo trên máy bàn trước. Việc đổi máy bàn ghi ở
[biên bản chuyển máy](CHUYEN_MAY_BAN.md).

Số dùng cho khóa luận phải đo trên máy trình diễn, vì hai máy khác nhau ở những chỗ ảnh hưởng thẳng tới kết quả:

- **GPU:** laptop có 4 GB VRAM so với 20 GB, và chậm hơn. Thời gian AI phải đo lại.
- **Bộ điều khiển USB và số cổng:** khác máy bàn. Khi bốn camera chạy chung, hiện tượng khung MJPEG bị cắt có thể nhẹ hơn
  hoặc nặng hơn ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 2).
- **Cổng COM của LiDAR:** Windows cấp số COM theo từng máy. Máy bàn tới 25/09/2026 dùng COM4, từ 29/09/2026 dùng COM3.
  Lệnh đo `may_moi` tự tìm cổng. Các lệnh LiDAR khác lấy cổng từ khóa `lidar_port` trong
  [configs/thiet_bi.json](../configs/thiet_bi.json). Vì vậy trên laptop, sửa dòng đó theo số COM của laptop hoặc ghi
  `"auto"` ([chuyển máy](CHUYEN_MAY_BAN.md)).

## 1. Chuẩn bị trên máy bàn (đã làm 24/09)

Laptop cần mô hình AI tham chiếu, mà GitHub không có tệp này. Ngày 24/09/2026, trên máy bàn trước, những thứ laptop cần
được gom vào thư mục `D:\CHUYEN_SANG_LAPTOP\` (ngoài repo):

- `autopark\runs\ai_woodscape_rtx4000_v1\best.pt`, mô hình AI tham chiếu, 38 MB.
- `config_resolved.json` của mô hình đó.
- `SHA256.txt`: mã SHA-256 của best.pt là `0459c3f4bf9a2b2307b4daf7d70f95db453718d6eaafe09d61e3c52d7ef90ccc`.
- `DOC_TRUOC.txt`: tóm tắt các bước ở mục 2.

Thư mục này nằm cùng ổ D với bản gốc, nên **chưa phải bản sao lưu thật**. Phải chép nó sang USB hoặc sang laptop thì mới
có bản thứ hai ở nơi khác. Thư mục đó chỉ có trên máy bàn trước. Trên máy bàn hiện tại (từ 29/09/2026), checkpoint gốc ở
`runs\ai_woodscape_rtx4000_v1\best.pt` trong thư mục `autopark` của repo, và SHA-256 của nó khớp mã trên. Nguồn: kiểm
29/09/2026, [chuyển máy](CHUYEN_MAY_BAN.md) mục 1.

**Tham chiếu máy bàn.** Lệnh đo so số của laptop với một tệp tham chiếu trong thư mục
[evidence/may_ban/](evidence/may_ban/) của repo. Thư mục có ba tệp:

| Tệp | Đo lúc | Mã khi đo | Trạng thái git |
|---|---|---|---|
| [tham_chieu_20260924.json](evidence/may_ban/tham_chieu_20260924.json) | 24/09 15:25, máy bàn trước | quy tắc chờ cũ (ngưỡng theo camera nhanh nhất), chưa làm nóng AI | đã commit (trong `2bd37b6`) |
| [tham_chieu_20260924_toi.json](evidence/may_ban/tham_chieu_20260924_toi.json) | 24/09 19:08, máy bàn trước | mã mới chưa commit trên `2bd37b6`: quy tắc chờ theo nhịp riêng từng camera, làm nóng AI mọi cỡ lô | đã commit trong `bfcbfc2` (20:22 24/09), có trên `origin/main` |
| [tham_chieu_20260929.json](evidence/may_ban/tham_chieu_20260929.json) | 29/09 12:59, máy bàn hiện tại | `9d68257`: quy tắc chờ theo nhịp riêng, làm nóng AI; `digest` có sẵn độ lệch bộ ảnh | vào Git cùng đợt chuyển máy 29/09/2026 |

"Quy tắc chờ theo nhịp riêng từng camera" ứng với `policy.wait_rule = "own_cadence"` trong tệp kết quả.

Lệnh đo lấy tệp đứng cuối theo tên trong thư mục đó, tức tệp 29/09. Người dùng chọn lượt `may_moi` ngày 29/09/2026 trên
máy bàn hiện tại làm tham chiếu, kể cả khi chạy trên laptop ([chuyển máy](CHUYEN_MAY_BAN.md) mục 2). Hai tệp 24/09 được
giữ lại để đối chiếu; ở cả hai lần đó camera nhìn cùng một chỗ tối. Lượt 29/09 không ghi camera nhìn cảnh nào. Vì vậy
dòng khung hỏng ở 720p chỉ so được khi đo lại trên máy bàn và đặt camera laptop nhìn cùng cảnh với lần đo lại đó.

## 2. Trên laptop

Làm lần lượt bảy bước sau.

1. **Lấy mã mới nhất.** Trong cmd:
   ```cmd
   git clone https://github.com/thbn12082/autopark
   ```
   Nếu laptop đã có repo thì chạy `git pull` trong thư mục đó.

   Các bản sửa của lệnh đo đều đã có trên `origin/main`, nên `git pull` là đủ:
   - Quy tắc chờ theo nhịp riêng, làm nóng AI và tệp tham chiếu 19:08 nằm trong commit `bfcbfc2` (20:22 ngày 24/09). Kiểm
     bằng `git branch -r --contains bfcbfc2`.
   - Các dòng mới của `tom_tat.md` (làm nóng AI, quy tắc chờ, độ lệch bộ ảnh, cảnh báo; mục 4) là sửa đổi của
     `autopark/rig/may_moi.py` sau `9bcc30c`. Sửa đổi này nằm trong commit `77eb51f` và đã được push tới ngày 25/09/2026
     (lúc đó `origin/main` = `54cb3e2`). Kiểm bằng `git branch --contains 77eb51f`: lệnh phải in nhánh đang dùng,
     thường là `main`.

   Nếu laptop đã đo bằng mã cũ hơn, mang kết quả về máy bàn rồi tóm tắt lại (mục 4.1).
2. **Chép checkpoint.** Trên máy bàn, lấy `best.pt` và `config_resolved.json` trong `runs\ai_woodscape_rtx4000_v1\` của
   thư mục `autopark` của repo. Chép chúng qua USB vào cùng đường dẫn trong thư mục `autopark` của repo trên laptop. Thư
   mục `D:\CHUYEN_SANG_LAPTOP\` ở mục 1 chỉ có trên máy bàn trước. Kiểm mã băm, chạy trong thư mục `autopark` của repo:
   ```cmd
   certutil -hashfile runs\ai_woodscape_rtx4000_v1\best.pt SHA256
   ```
   Kết quả phải trùng mã ở mục 1.
3. **Cài hai môi trường.** Cần Python 3.12 và mạng Internet.
   - `autopark\cai_dat.cmd` tạo `.venv` (mô phỏng, giao diện, test) theo `requirements-phase0.lock`.
   - `autopark\cai_dat_train.cmd` tạo `.venv-train` (torch CUDA 12.8, bàn thử, hiệu chuẩn, gán nhãn) theo
     `requirements-train.lock`. Cuối lệnh in `CUDA True` và tên GPU. Nếu in `CUDA False` thì cập nhật driver NVIDIA, vì
     torch bản cu128 cần driver hỗ trợ CUDA 12.8. Máy bàn dùng driver 596.71 từ 29/09/2026 (máy bàn trước: 596.72).
   - `requirements-train.lock` có dòng `shapely==2.1.2`, commit trong `b01dea4` ngày 25/09/2026 và có trên
     `origin/main`. Nhờ shapely, phiên đỗ xe, planner và AI camera chạy chung một tiến trình (`ui.lidar_app --camera-ai`,
     [AI_DIEU_KHIEN_XE.md](AI_DIEU_KHIEN_XE.md)). Trên máy bàn, shapely 2.1.2 được cài thêm vào `.venv-train` ngày
     25/09/2026, với sự đồng ý của người dùng; trước đó `.venv-train` không có shapely. Trên laptop chỉ cần `git pull`
     rồi chạy lại `cai_dat_train.cmd`, vì lệnh cài theo tệp khóa cả khi `.venv-train` đã có. Ngăn AI camera trên laptop:
     chưa chạy.
   - Laptop không cần g++, cmake, PlatformIO hay QEMU. Test host của firmware tự bỏ qua khi không có cmake hoặc trình
     biên dịch C++ trên PATH. Test bo ảo QEMU tự bỏ qua khi `configs/thiet_bi.json` không có `qemu_xtensa`,
     `platformio_python`, hoặc đường dẫn ghi ở đó không tồn tại. Ba khóa `qemu_xtensa`, `platformio_python`,
     `platformio_core_dir` (đường dẫn của máy bàn) để nguyên hoặc xóa đều được ([chuyển máy](CHUYEN_MAY_BAN.md) mục 5
     bước 3).
4. **Driver LiDAR.** Nếu Device Manager chưa thấy "Silicon Labs CP210x USB to UART Bridge (COMx)", cài driver cầu nối
   CP210x của Silicon Labs. Máy bàn dùng bản 11.2.0.167 từ 29/09/2026, cài qua Windows Update vì tải từ silabs.com bị
   chặn. Máy bàn trước dùng bản 11.6.0.420 ([chuyển máy](CHUYEN_MAY_BAN.md)).
5. **Cắm thiết bị.** Cắm hub UGREEN với bốn camera ở đúng các cổng 1–4 như máy bàn, và cắm LiDAR thẳng vào laptop. Đóng
   mọi chương trình đang dùng camera. Để camera nhìn **cùng một cảnh** như khi đo trên máy bàn, vì số khung bị cắt ở
   720p phụ thuộc cảnh.
6. **Đo.** Chạy `autopark\do_may_moi.cmd`, mất khoảng 4 phút. Kết quả nằm ở `autopark\runs\may_moi_<ngày giờ>\`; đọc
   `tom_tat.md` trước.
7. **Mang kết quả về.** Chép cả thư mục kết quả về máy bàn, vào `autopark\runs\`, để ghi vào tài liệu.

## 3. Lệnh đo làm gì

`python -m autopark.rig.may_moi` ([mã](../autopark/rig/may_moi.py)) chạy sáu bước. Bước nào lỗi thì lệnh ghi lỗi lại
rồi chạy tiếp bước sau.

| Bước | Đo gì | Tệp ra |
|---|---|---|
| `env` | CPU, RAM, Python, torch, CUDA, GPU, VRAM, driver NVIDIA, OpenCV | `env.json` |
| `usb` | Camera và hub Windows thấy, ghép index với cổng hub | `usb_topology.json` |
| `lidar` | Tự tìm cổng CP210x; thông tin và sức khỏe thiết bị; 15 s quét tĩnh có phân tích | `lidar_info.json`, `lidar/` |
| `ai` | Một lô 4 ảnh 640×480 qua mô hình tham chiếu, 60 lô sau 5 lô khởi động; VRAM đỉnh | `ai_latency.json` |
| `rig480` | Bàn thử bốn camera 640×480 + LiDAR + AI, 120 s | `m01_480p_lidar_ai.rig.json` |
| `cam720` | Bốn camera 1280×720, chỉ camera, 30 s: khung bị cắt | `m02_720p_chi_camera.rig.json` |

`tom_tat.md` đặt từng số của máy đang đo cạnh số của máy bàn. Số máy bàn lấy từ tệp đứng cuối theo tên trong
[evidence/may_ban/](evidence/may_ban/); từ 29/09/2026 đó là
[tham_chieu_20260929.json](evidence/may_ban/tham_chieu_20260929.json) (mục 1).

**Bước `ai` và bước `rig480` đo hai thứ khác nhau:**

- `ai` tự tạo mô hình, chạy 5 lô 4 ảnh để khởi động rồi đo 60 lô 4 ảnh. Bước này không dùng phần làm nóng của bàn thử.
- `rig480` chạy bàn thử. Từ mã tối 24/09/2026, bàn thử làm nóng AI cho mọi cỡ lô 4 / 3 / 2 / 1 ảnh ngay sau khi nạp mô
  hình (`AIWorker.warm_up`), rồi mới tính 5 s làm nóng của phiên. Thời gian từng lô làm nóng ghi ở `ai.warm_up_ms` trong
  `m01_480p_lidar_ai.rig.json`, và `tom_tat.md` in dòng này (mục 4.1). Máy bàn lúc 19:08 ngày 24/09: 1482 / 1448 / 1553
  / 1410 ms, tổng ≈ 5,9 s. Nghĩa là AI sẵn sàng ≈ 6 s sau khi nạp mô hình.

Tùy chọn của lệnh:

- `--dry-run`: chỉ in kế hoạch.
- `--steps ai rig480`: chỉ chạy vài bước.
- `--lidar COM5`: dùng khi tự tìm cổng sai.
- `--seconds 600`: phiên 480p dài hơn.

Camera cắm qua hub thì được chọn theo cổng hub. Camera cắm thẳng vào laptop thì không có số cổng hub, nên lệnh tự mở theo
index DirectShow. Lệnh chỉ lấy camera Sunplus 1BCF:0B09 của dự án, theo mã thiết bị. Vì vậy webcam gắn sẵn của laptop bị
bỏ qua, kể cả khi webcam cũng tên "HD Camera".

## 4. Đọc kết quả

Chưa có ngưỡng nghiệm thu nào được chốt (kế hoạch mục 16.2). Vì vậy `tom_tat.md` chỉ so với máy bàn, không kết luận đạt
hay không đạt. Nên đọc kỹ những điểm sau:

- **AI, một lô 4 ảnh.** Bốn camera ≈ 24 khung/s thì cứ ≈ 42 ms có một bộ ảnh. Lô lâu hơn thế thì AI không theo kịp
  camera, và số bộ AI/s ở `rig480` sẽ thấp hơn ≈ 24.
- **Khung hỏng ở 480p và 720p** trên bộ điều khiển USB của laptop. Muốn so với máy bàn thì phải cùng cảnh.
- **LiDAR:** tốc độ quay ≈ 10 Hz và ≈ 510 tia mỗi vòng như máy bàn. Nếu khác thì xem do máy hay do cáp/cổng.
- **CPU và GPU** của tiến trình, và nhiệt GPU cuối phiên.
- **Làm nóng AI:** dòng "Bàn thử 480p: làm nóng AI theo cỡ lô" và dòng "… tổng làm nóng AI" (mục 3, 4.1). Máy bàn lúc
  19:08 ngày 24/09 tổng ≈ 5,9 s; tham chiếu 29/09 tổng 6,1 s. Laptop có GPU yếu hơn nên có thể lâu hơn; chưa đo.
- **Nhịp từng camera ở 720p.** Có lần mở camera, một camera chạy ≈ 29 khung/s ở phơi sáng tự động, còn các camera kia ≈
  23,85. Camera bị như vậy thay đổi giữa các lần mở:
  - cổng 3 ở s01–s07, t01, t02 (23/09);
  - cổng 1 ở t05 (23/09) và lúc 15:25, 17:56 ngày 24/09;
  - không camera nào lúc 19:08 ngày 24/09 (tệp tham chiếu dùng tới 25/09/2026).

  Vì vậy một camera 29 khung/s trên laptop chưa phải khác biệt do máy. Nếu gặp, xem thêm cột "bộ thiếu camera chậm".
  Trên máy bàn, với quy tắc chờ theo nhịp riêng (o01, 17:56), tình huống này cho 0 bộ bỏ camera khỏe. Quy tắc cũ (15:25)
  bỏ 263 / 855 bộ ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 10.3).

  Chỉ so số bộ khi không có cảnh báo quy tắc chờ (mục 4.1). Cảnh báo này xét cả tên quy tắc, sàn `max_wait_ms`, số chu
  kỳ, `max_skew_ms` và `stale_after_ms`. Hai số cuối không in trong dòng "quy tắc chờ camera chậm", nên thấy hai dòng đó
  giống nhau là chưa đủ.

### 4.1. Làm nóng AI, quy tắc chờ, độ lệch bộ ảnh và các cảnh báo

Mục này giải thích các dòng mà `tom_tat.md` có thêm từ bản `autopark/rig/may_moi.py` sửa khuya 24/09/2026. Bản sửa nằm
trong commit `77eb51f`, đã push tới ngày 25/09/2026 (mục 2, bước 1). Trong bảng dưới, cột máy bàn hiện tại lấy từ tệp
tham chiếu đang dùng ([tham_chieu_20260929.json](evidence/may_ban/tham_chieu_20260929.json), mục 1). Cột 24/09 là tệp
19:08, dùng làm tham chiếu tới 25/09/2026.

| Dòng trong `tom_tat.md` | Lấy từ | Máy bàn hiện tại, 12:59 ngày 29/09 | Máy bàn trước, 19:08 ngày 24/09 |
|---|---|---|---|
| Bàn thử 480p: làm nóng AI theo cỡ lô (ms); … tổng làm nóng AI (s) | `ai.warm_up_ms` của `m01_480p_lidar_ai.rig.json`: một lô cho mỗi cỡ 4, 3, 2, 1 ảnh | 4 ảnh 1522 / 3 ảnh 1469 / 2 ảnh 1658 / 1 ảnh 1414; tổng 6,1 s | 4 ảnh 1482 / 3 ảnh 1448 / 2 ảnh 1553 / 1 ảnh 1410; tổng 5,9 s |
| Bàn thử 480p: quy tắc chờ camera chậm; 720p chỉ camera: quy tắc chờ camera chậm | `policy` của từng `.rig.json` (`wait_rule`, `wait_periods_of_own`, sàn `max_wait_ms`) | nhịp riêng: max(60 ms; 1,5 × chu kỳ của chính từng camera), cả hai bước | như cột trái |
| … độ lệch bộ ảnh trung vị / p95 / max (ms), ở 480p và ở 720p | `sets.skew_ms` của từng `.rig.json` | 480p 17,1 / 32,0 / 35,9; 720p 26,0 / 30,2 / 32,8 | "—": tệp tham chiếu không lưu số này (xem dưới) |

**EcoQoS.** EcoQoS là chế độ tiết kiệm của Windows 11, có thể hạ tốc tiến trình. Từ 02/10/2026, dòng đầu bảng của
`tom_tat.md` là "EcoQoS của tiến trình đo (off = đã tắt)", lấy từ `env.ecoqos` (`env.json`). Cũng từ ngày đó, `may_moi`
tự tắt EcoQoS cho tiến trình đo, kể cả `rig.bench` chạy bên trong; đặt `AUTOPARK_KEEP_ECOQOS=1` thì giữ mặc định của
Windows. Tệp tham chiếu máy bàn ghi trước ngày đó không có trạng thái này, nên cột máy bàn là "—"; không có CẢNH BÁO
mới. `.rig.json` có thêm `resources.ecoqos` (trong digest: `rig480.ecoqos`, `cam720.ecoqos`).

**Tệp tham chiếu lưu số ở đâu.** Tệp 29/09 tạo từ `may_moi.json`, nên `digest` có sẵn cả ba loại số. Tệp tham chiếu
19:08 lưu `policy` và `ai_warm_up_ms` ở tầng ngoài, không trong `digest`; lệnh đo tự đọc cả hai chỗ và không sửa tệp.
Tệp 15:25 ([tham_chieu_20260924.json](evidence/may_ban/tham_chieu_20260924.json)) không lưu cả ba loại số, nên cột máy
bàn là "—". Độ lệch bộ ảnh của hai lần chạy 24/09 chỉ có trong tệp gốc. Tệp gốc bị git bỏ qua và chỉ có trên máy bàn
(đọc 24/09/2026):

| Lần chạy máy bàn | 480p + LiDAR + AI: trung vị / p95 / max (ms) | 720p chỉ camera: trung vị / p95 / max (ms) |
|---|---|---|
| 19:08, nhịp riêng (`runs/may_moi_20260924_toi/`) | 29,1 / 30,1 / 33,9 | 16,6 / 31,8 / 34,4 |
| 15:25, quy tắc cũ (`runs/may_moi_20260924_may_ban/`) | 27,8 / 28,0 / 41,2 | 24,5 / 36,0 / 40,3 |

**Các dòng cảnh báo** in ngay trên bảng:

- **"CẢNH BÁO — quy tắc chờ camera chậm khác nhau hoặc không rõ"**: bước 480p hoặc 720p của máy này dùng quy tắc chờ
  hoặc tham số ghép bộ khác tham chiếu, hoặc một bên không ghi `policy` (tham chiếu 15:25 không ghi). Lệnh so tên quy
  tắc, sàn `max_wait_ms`, số chu kỳ, `max_skew_ms` và `stale_after_ms`; trước bản sửa sau rà soát khuya 24/09/2026, nó
  chỉ so tên quy tắc. Khóa nào khác mà dòng "quy tắc chờ camera chậm" không cho thấy thì cảnh báo nêu tên khóa và hai
  giá trị, ví dụ "(khác `max_skew_ms` 30 / 60)". Khi có cảnh báo này, số bộ ảnh, bộ thiếu camera chậm, số lần bỏ theo
  cổng và độ lệch bộ ảnh của hai cột không so thẳng được.
- **"CẢNH BÁO — tham chiếu có trước khi bàn thử làm nóng AI"**: tệp tham chiếu không có `ai_warm_up_ms` (tham chiếu
  15:25). Ở phiên đó, lô đầu của mỗi cỡ lô phải trả phần khởi tạo trong lúc chạy. Vì vậy số AI của bàn thử 480p ở hai
  cột không cùng điều kiện.
- **"CẢNH BÁO — lần chạy này không có số làm nóng AI"**: `m01_480p_lidar_ai.rig.json` của máy này không có
  `ai.warm_up_ms`. Nghĩa là tệp do mã cũ ghi, từ trước khi bàn thử có làm nóng, hoặc làm nóng bị lỗi (`ai.last_error`).

**Đã thử những gì.** Ngày 24/09/2026, trên máy bàn, các dòng mới được thử offline trên bản sao hai lần chạy máy bàn,
không mở thiết bị:

- lần 19:08 so với tham chiếu 19:08: không cảnh báo;
- lần 19:08 so với tham chiếu 15:25: hai cảnh báo đầu;
- lần 15:25 so với tham chiếu 19:08: cảnh báo quy tắc chờ và "lần chạy này không có số làm nóng AI".

Lần thử đó chạy từ thư mục `autopark`, nên hai dòng LiDAR của bản sao lấy từ thư mục **gốc** trong `runs\` chứ không từ
bản sao. Lý do: mã lúc đó đọc tệp phân tích LiDAR theo đường dẫn lưu trong `may_moi.json`, tương đối với thư mục đứng
lúc đo. Lỗi này được sửa khuya 24/09/2026 (xem phần "Tóm tắt lại" dưới), rồi thử lại trên máy bàn. Lần thử lại dùng bản
sao **đổi tên** của hai lần chạy và chạy lệnh từ một thư mục ngoài repo, nơi đường dẫn lưu không còn trỏ tới đâu; mỗi
bản sao được so với cả hai tệp tham chiếu. Các dòng cảnh báo và cả bảng trùng từng dòng với lần thử trước, và số LiDAR
trùng `may_moi.json` gốc. Với mã trước khi sửa, cùng cách thử trên bản sao đổi tên của lần 19:08 cho hai dòng LiDAR là
"—".

Trên laptop: chưa chạy.

**Tóm tắt lại một thư mục kết quả đã có** (không mở camera, LiDAR hay GPU). Dùng khi mang kết quả laptop về máy bàn,
hoặc khi laptop đã đo bằng mã cũ hơn. `--steps` không kèm tên bước thì không chạy bước nào, chỉ đọc lại các tệp trong
thư mục. Thiếu `--out`, hoặc thư mục chưa có, thì lệnh báo lỗi và không tạo gì. Lệnh ghi đè `tom_tat.md` và
`may_moi.json` của thư mục đó; muốn giữ bản cũ thì chép chúng ra trước. Chạy trong thư mục `autopark`:

```cmd
.venv-train\Scripts\python.exe -X utf8 -m autopark.rig.may_moi --out runs\may_moi_<ngày giờ> --steps
```

Lệnh này không cần torch, nên `.venv\Scripts\python.exe` thay cho `.venv-train\Scripts\python.exe` cũng được.

Từ bản sửa khuya 24/09/2026, số LiDAR luôn đọc từ `<thư mục kết quả>\lidar\l01_tinh.analysis.json`. Nhờ vậy thư mục đã
đổi tên, đã chuyển chỗ (ví dụ `runs\laptop\...`) hay được tóm tắt từ thư mục khác vẫn giữ hai dòng LiDAR. Nếu bước
`lidar` báo xong mà thiếu tệp đó, `tom_tat.md` in một dòng nêu tệp thiếu; ví dụ khi chép thiếu thư mục `lidar\`, hoặc
khi bản ghi 15 s lỗi. Nếu thư mục `--out` không có, lỗi in đường dẫn tuyệt đối đã tìm và thư mục đang đứng.

## 5. Giới hạn

- Lệnh đo **chưa chạy trên laptop**. Trên máy bàn trước, lệnh chạy trọn hai lần ngày 24/09/2026: lúc 15:25 (mã cũ) và
  19:08 (mã mới), mỗi lần tạo một tệp tham chiếu (mục 1). Lần 19:08 cho:
  - 480p + LiDAR + AI, 120 s: bốn camera 23,85 khung/s, 0 khung hỏng, 2.861 bộ, 0 bộ thiếu camera khỏe (15:25: 3), AI
    23,85 bộ/s, lô trung vị 13,2 ms, LiDAR 10,01 Hz;
  - 720p chỉ camera, 30 s: cả bốn ≈ 23,85 khung/s, 716 bộ, 0 bộ bỏ camera (15:25: 263 / 855);
  - bước `ai`: trung vị 10,4 ms, p95 11,4 ms, VRAM 78 MB.
- Tham chiếu 19:08 đo bằng mã chưa commit. Phần mã đó sau vào `bfcbfc2`, nhưng vì lúc 19:08 mã chưa commit nên không
  chứng minh được mã chạy lúc đó trùng từng dòng với `bfcbfc2`. Khi so với tệp này, laptop phải chạy cùng bản mã (sau
  khi commit, push, `git pull`), và ghi mã commit cạnh số của laptop. Dòng "quy tắc chờ camera chậm" trong `tom_tat.md`
  cho thấy laptop có dùng cùng quy tắc chờ với tham chiếu hay không.
- Lúc tạo hai tệp tham chiếu 24/09, camera máy bàn nhìn vào chỗ tối (gầm bàn). Số khung bị cắt ở 720p của các tham
  chiếu đó chỉ đúng cho cảnh này.
- Không đo độ trễ từ sự kiện thật tới lúc khung tới máy; việc này cần LED nháy.
