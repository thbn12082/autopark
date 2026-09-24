# Ghi và phát lại phiên bàn thử — bốn camera + LiDAR (24/09/2026)

**Trạng thái (tối 24/09/2026):** phần mềm và test với nguồn giả xong. Đã ghi **một** phiên thật trên máy bàn: bốn camera
480p + LiDAR + AI, 60 s, 0 khung bị bỏ, 4,98 MB/s. Phát lại phiên đó cho đúng số bộ và độ lệch như lúc ghi. Chi tiết ở
mục 7. Số ở mục 5 là số đo trên ảnh đã lưu từ ngày 23/09, hoặc là ước lượng suy ra; mỗi số ghi rõ thuộc loại nào. Chưa
có bản ghi nào có camera lỡ nhịp thật. Chưa chạy gì trên laptop.

**Để làm gì.** Bàn thử (`rig.bench`, `ui/rig_app.py`) cần bốn camera, LiDAR và cổng COM. Ghi một phiên một lần, sau đó:

- chạy lại cả bàn thử từ bản ghi (ghép bộ ảnh, chờ camera chậm, AI, LiDAR so với bộ ảnh, giao diện) mà không cắm gì;
- chạy **hai quy tắc khác nhau trên cùng một dữ liệu**, ví dụ `--max-wait-ms 60` và `--max-wait-ms 0`. Trên phần cứng, hai
  phiên chạy hai quy tắc không bao giờ có cùng dữ liệu;
- dùng dữ liệu thật trong test và demo, và để phát triển các phần khác (BEV từ AI, định vị LiDAR) trên cùng một bản ghi.

Mã: [`autopark/rig/recording.py`](../autopark/rig/recording.py) (ghi),
[`autopark/rig/replay.py`](../autopark/rig/replay.py) (phát lại), cách nối vào `Rig` ở
[`autopark/rig/core.py`](../autopark/rig/core.py). Test: [`tests/test_rig_replay.py`](../tests/test_rig_replay.py).

## 1. Ghi

Mỗi lệnh viết trên một dòng, dán được vào cmd.exe lẫn PowerShell (sửa tối 24/09: trước đó ngắt dòng bằng dấu backtick của
PowerShell, cmd không hiểu). Dòng `#` là chú thích, đừng dán vào cmd.

```powershell
# lệnh đo không giao diện: ghi đúng phần đo (sau --warmup), cùng lúc ghi g01.rig.json như mọi phiên
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --ports 1 2 3 4 --lidar COM4 --seconds 120 --name g01 --out runs/rig_bench/20260925 --record runs/rig_recordings/g01

# giao diện: nút "Ghi phiên" bật/tắt; mỗi lần bật ghi vào thư mục --record-root, mỗi lần một thư mục con theo giờ
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.ui.rig_app --lidar COM4 --record-root runs/rig_recordings
```

- `--record-format png` để có ảnh không mất mát. PNG lớn hơn JPEG khoảng 4,5 lần và mã hóa chậm hơn khoảng 10 lần (mục 5),
  nên chỉ hợp với đoạn ngắn. `--jpeg-quality` mặc định 95.
- Thư mục ghi phải chưa có hoặc đang rỗng. Bộ ghi không ghi đè một bản ghi cũ. Từ 24/09, `rig.bench` kiểm `--record`
  (thư mục đã có dữ liệu, hay là một tệp) và `--jpeg-quality` (phải trong 1..100) **ngay khi đọc dòng lệnh**, trước khi
  mở camera, quay LiDAR, nạp AI và làm nóng: sai thì thoát mã 2 kèm câu lỗi, không có traceback sau vài chục giây khởi
  động. Giao diện kiểm `--jpeg-quality` cũng lúc khởi động.
- Mỗi lúc chỉ có **một** bản ghi chưa xong. Tắt "Ghi phiên" khi hàng đợi còn nhiều khung thì bản ghi đó "đang ghi nốt";
  trong lúc ấy nút bị làm mờ, và `Rig.start_recording` từ chối ghi phiên mới ("bản ghi trước … còn đang ghi nốt", không
  tạo thư mục mới). Đóng cửa sổ hay `Rig.stop()` chờ bản ghi ghi nốt xong (tối đa 60 s, quá thì báo `rig-recorder` là
  luồng chưa dừng). Trước bản sửa 24/09, bật lại "Ghi phiên" trong lúc ghi nốt rồi đóng cửa sổ thì bản ghi đầu bị cắt âm
  thầm: mất khung còn trong hàng đợi, mất phần LiDAR trong RAM, `meta.json` kẹt ở `đang ghi`.
- Ghi những gì: **mọi khung tốt** mà nguồn camera trả cho luồng camera, tức là sau khi `UsbCameraSource` đã loại khung cũ,
  khung bị cắt và khung xé. Mỗi lần đọc hỏng được ghi thành **sự kiện** có stamp và nguyên văn thông báo, không kèm ảnh.
  Ghi thêm mọi vòng LiDAR, lỗi đọc LiDAR và `meta.json`.
- **Không ghi:** kết quả AI (phát lại sẽ chạy lại AI), bộ ảnh đã ghép, số đo tài nguyên. Những thứ đó nằm trong `.rig.json`
  của phiên.
- Tắt ghi thì bộ ghi ngừng nhận ngay. Phần còn trong hàng đợi được ghi nốt ở nền, nên giao diện không bị đứng. Trên bảng số
  đo, mục "GHI PHIÊN" hiện trạng thái (`đang ghi`, `đang ghi nốt`, `xong` hoặc `LỖI`), số khung đã ghi, số khung bị bỏ,
  MB đã ghi, MB/s và số khung đang chờ ghi.
- Lỗi không bị bỏ qua im lặng:
  - Hàng đợi đầy (đĩa chậm): khung bị **bỏ**, được đếm (`dropped`) và để lại một dòng `record_dropped` trong `events.csv`.
    Giao diện ghi "GHI THIẾU".
  - Lỗi ghi (đĩa đầy, mất quyền…): trạng thái chuyển thành `LỖI`, câu lỗi được giữ nguyên văn, và mọi khung sau đó bị bỏ
    và đếm. Giao diện ghi "LỖI GHI: …".
  - `rig.bench` trả mã 1 và in "CẢNH BÁO: bản ghi … không trọn" khi bản ghi có lỗi, có khung bị bỏ, hoặc chưa ghi nốt xong.

## 2. Phát lại

```powershell
# cả bàn thử từ bản ghi, không mở thiết bị nào; phần đo phủ trọn bản ghi rồi tự dừng
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --replay runs/rig_recordings/g01 --name g01_phat_lai --out runs/rig_bench/phat_lai
# cùng bản ghi, quy tắc cũ (chờ mọi camera), để so
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --replay runs/rig_recordings/g01 --max-wait-ms 0 --name g01_phat_lai_tat_cho --out runs/rig_bench/phat_lai
# giao diện; --replay-speed 2 = nhanh gấp đôi; --ports 1 2 = chỉ hai camera trong bản ghi; --no-ai chạy được trong .venv
.\.venv\Scripts\python.exe -X utf8 -m autopark.ui.rig_app --replay runs/rig_recordings/g01 --no-ai
```

- `--replay` không dùng cùng `--index` hay `--lidar`. `--ports` chọn cổng có trong bản ghi.
- Mode camera (kích thước, fps yêu cầu) lấy từ bản ghi, không lấy từ `--width/--height`. Quy tắc ghép bộ (`--max-skew-ms`,
  `--max-wait-ms`) và AI (`--checkpoint`, `--no-ai`) lấy từ dòng lệnh.
- Đồng hồ phát lại chỉ chạy **sau khi AI nạp xong mô hình và làm nóng mọi cỡ lô** (hoặc nạp lỗi), để AI thấy bản ghi từ
  khung đầu (làm nóng: thêm tối 24/09, mục 7). Trong bench, thứ tự là: nạp mô hình → làm nóng → `--warmup` (mặc định 0 khi
  phát lại) → đặt lại số đo → bắt đầu phát. Vì vậy số khung trong
  `.rig.json` bằng đúng số khung trong bản ghi. Khối `replay` trong json ghi `finished` và độ trễ thực của từng camera so
  với lịch (`late_ms`).
- Giao diện: tiêu đề và bảng số đo ghi "PHÁT LẠI"; chưa bắt đầu thì ô camera ghi "phát lại chưa bắt đầu (chờ AI nạp mô
  hình)". Bộ ảnh chụp bằng "Chụp bộ ảnh" trong lúc phát lại có khóa `replay` trong `meta.json`, để không bị lẫn với ảnh camera
  thật khi đem đi gán nhãn.
- Dùng trong mã (test, công cụ khác):

```python
from autopark.rig.core import Rig, RigConfig
from autopark.rig.replay import ReplaySession, load_lidar
from autopark.video.multicam import MultiCameraManager

session = ReplaySession("runs/rig_recordings/g01", speed=1.0)
cams = MultiCameraManager(session.camera_specs(), open_source=session.open_camera)
rig = Rig(cams, RigConfig(ai=False), open_lidar=session.open_lidar if session.has_lidar else None, replay=session)
rig.start()                      # không có AI: phát ngay; có AI: phát khi mô hình nạp xong
...
rig.stop()                       # đánh thức mọi nguồn đang chờ

recording, lidar_errors = load_lidar("runs/rig_recordings/g01")   # mọi vòng LiDAR, dạng lidar.recording.Recording
```

Mỗi `lidar/part_XXXX.npz` cũng là một bản ghi LiDAR đầy đủ theo định dạng của
[GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) (`read_recording`, bản đồ lưới tĩnh…), nhưng stamp của nó là đồng hồ bàn thử
(mục 4).

## 3. Định dạng thư mục (`format_version` 1)

| Tệp | Nội dung |
|---|---|
| `meta.json` | `format`, `format_version`, `status` (`đang ghi` → `xong` / `lỗi`; bản ghi bị ngắt giữa chừng giữ `đang ghi`), `created_utc`/`created_local`, `t_start_s`/`t_stop_s`, `clock` (tên, độ phân giải), `git_commit`, `host`, `opencv`, `image` (định dạng, chất lượng), `config` và `policy` của Rig, `camera_mode`, `cameras` (cổng, index, instance_id, `source_rejects_damaged`, lỗi mở), `cameras_at_stop` (bộ đếm từng camera lúc dừng, gồm lỗi mở), `lidar_source` (cổng, `describe()` của driver), `lidar_at_stop`, `per_port` (khung thấy / đã ghi / bị bỏ, số sự kiện theo loại, stamp đầu/cuối), `lidar` (các phần, số vòng), `replay_of` (khi ghi trong lúc phát lại), `notes`, `error`, `errors` |
| `cam_p<cổng>/frames.csv` | `seq, t_s, width, height, file, bytes`: một dòng cho mỗi khung tốt **đã ghi xuống đĩa**. `seq` đếm mọi khung tốt đã thấy, từ 1; chỗ `seq` nhảy cóc là khung bị bỏ |
| `cam_p<cổng>/events.csv` | `t_s, kind, after_seq, message`: `kind` ∈ `duplicate`, `truncated`, `torn`, `read_failed`, `exception` (như nguồn báo, phân loại giống `CameraWorker`) hoặc `record_dropped` (bộ ghi bỏ khung). `after_seq` = khung tốt cuối cùng trước sự kiện, dùng để giữ đúng thứ tự khi phát lại |
| `cam_p<cổng>/0000001.jpg` | ảnh BGR mã hóa bằng `cv2.imencode` (JPEG q95, hoặc PNG nén mức 1); ghi bằng `write_bytes` vì `cv2.imwrite` không ghi được vào đường dẫn tiếng Việt |
| `lidar/part_0000.npz` + `.json` | tối đa 600 vòng (≈ 60 s) mỗi phần, định dạng `ScanRecorder`: `t` (cuối vòng), `t_first` (đầu vòng), `n_beams`, `angles`, `ranges` (NaN = không phản hồi), `quality` |
| `lidar/events.csv` | `t_s, message`: lỗi đọc LiDAR |

Mọi `t_s` là đồng hồ bàn thử `time.perf_counter` tính bằng giây: camera là lúc `read()` trả khung (đã gồm giải mã),
LiDAR là lúc byte cuối của vòng tới máy. Stamp LiDAR được đổi từ giờ phiên của driver sang đồng hồ bàn thử bằng `t0`, cùng
phép đổi mà `LidarWorker` dùng. `created_utc` ứng với `t_start_s`, nên từ đó suy được giờ thật của từng stamp (sai số bằng
độ lệch giữa hai lần đọc đồng hồ, cỡ micro giây).

## 4. Phát lại xử lý thời gian thế nào

- **Stamp được đổi gốc:** t_phát = t_bắt_đầu + (t_ghi − t_gốc) / speed, trong đó t_gốc là điểm sớm nhất của bản ghi.
  Khoảng cách giữa các khung của một camera, giữa các camera, và giữa camera với LiDAR được giữ nguyên (chia cho speed).
  Giá trị tuyệt đối thì đổi. Test so stamp tương đối của bản ghi gốc và của chính phiên phát lại được ghi lại: trùng tới
  1 µs.
- `read()` **chặn** tới đúng thời điểm của khung. Ảnh được giải mã trước khi chờ, nên khung ra gần đúng stamp. Độ trễ thực
  so với lịch được đo (`late_ms`). Trong test trên máy bàn với ảnh 64×48, trung vị là 0,2–0,3 ms. Với ảnh 640×480 thật và
  AI chạy cùng thì **chưa đo**. Máy bận thì khung ra muộn hơn lịch, nhưng stamp vẫn là giờ theo lịch.
- Sự kiện khung hỏng được **ném lại** đúng lúc và đúng nguyên văn (`FrameReadError` có `t`). Vì vậy `duplicates`,
  `truncated`, `torn`, `read_failures` và nhịp khung đo trên `CameraWorker.arrivals` (gồm cả khung cắt/xé) ra như lúc ghi.
  Test kiểm tra điều này qua bộ đếm của `MultiCameraManager`.
- Camera không mở được lúc ghi thì lúc phát lại cũng không mở được. Lỗi ghi là "lúc ghi camera cổng N không mở được: …".
- Bản ghi có stamp nằm ngoài cửa sổ ghi [`t_start_s` − 5 s; `t_stop_s` + 5 s] bị từ chối (`ReplayError`, "các nguồn không
  cùng một đồng hồ?"). Nếu không từ chối, phát lại sẽ lặng lẽ "chờ" hàng giờ giữa hai nguồn. Bản ghi bị ngắt giữa chừng
  không có `t_stop_s` nên không được kiểm điều này.
- **Hết bản ghi:**
  - Nguồn ngừng trả khung: `read()` chặn tới khi được yêu cầu dừng, không trả `None` và không ném lỗi liên tục. Có ba cách
    dừng: `session.stop()`, `close()`, hoặc luồng camera/LiDAR đang gọi nó bị yêu cầu dừng. Khi dừng, nó mới báo
    "hết bản ghi phát lại".
  - Sau 0,5 s (`STALE_AFTER_S`) camera chuyển thành "cũ", không còn bộ ảnh mới, AI ngừng. `session.finished` thành True.
  - `rig.bench` tự dừng: chờ thêm 0,3 s cho AI chấm nốt bộ cuối rồi chốt số. Giao diện ghi "HẾT BẢN GHI phát lại" ở đầu
    mọi ô (báo đỏ) và trên bảng số đo. Bench còn có hạn cứng: độ dài bản ghi / speed + 10 s. Từ 24/09, phát lại không có
    `--seconds` mà chạy tới hạn cứng vẫn chưa hết bản ghi (một nguồn kẹt) thì bench in "CẢNH BÁO: phát lại chạy tới hạn
    cứng …" và trả mã 1. Có `--seconds` ngắn hơn bản ghi thì dừng trước khi hết là đúng ý, không tính là lỗi.
  - **Không lặp lại.**

## 5. Giới hạn — đọc trước khi dùng số của một phiên phát lại

1. **Stamp đã đổi gốc sang đồng hồ phát lại** (mục 4). Không so giá trị tuyệt đối với phiên gốc. Khoảng cách và độ lệch
   thì so được.
2. **JPEG mã hóa lại làm pixel đổi một chút.** Đo 24/09 trên 8 ảnh thật chụp ngày 23/09 (`runs/rig_snapshots/`) với
   `cv2.imencode` q95:
   - sai khác trung bình 0,85–1,24 mức xám;
   - lớn nhất 10–18 mức xám ở 480p, 13–17 ở hai khung 720p nguyên vẹn. Hai khung 720p còn lại là khung bị cắt (chụp trước
     khi có bộ dò; `truncated_rows` = 352 và 328 khi kiểm lại ngày 24/09) và có chỗ lệch tới 162–194.

   AI chấm trên ảnh hơi khác ảnh gốc, nên kết quả AI khi phát lại **không** trùng từng bit với lúc chạy trực tiếp. Cần trùng
   từng pixel thì ghi PNG.
3. **Bộ dò khung hỏng đã chạy lúc ghi.** Bản ghi chỉ chứa ảnh của khung tốt; khung cũ, bị cắt hay xé chỉ còn là sự kiện, không
   có ảnh. Phát lại vì vậy không thử lại được bộ dò (`truncated_rows`, `torn_bands`). Khung hỏng mà bộ dò bỏ sót lúc ghi thì
   nằm trong bản ghi như khung tốt.
4. **Phát lại không tái tạo phần cứng.** Không có tranh chấp băng thông USB, không có DirectShow, không có giải mã MJPEG
   của driver; thay vào đó là giải mã JPEG từ đĩa, ≈ 1,4 ms/khung 480p (đo trên ảnh 23/09). Vì vậy CPU, GPU và thời gian AI
   trong `.rig.json` của phiên phát lại không thay được số đo trực tiếp.
5. **speed ≠ 1:** nhịp đo được (fps, chu kỳ khung, ngưỡng chờ L) đổi theo speed. Các ngưỡng tuyệt đối (0,5 s để coi là "cũ",
   `max_skew` 60 ms, sàn chờ 60 ms, hạn AI 0,5 s) thì không đổi, nên kết quả ghép bộ ở speed ≠ 1 **không** so được với
   phiên gốc. Để so quy tắc thì dùng speed 1.
6. **Cỡ bản ghi và tải ghi** (đo 24/09 trên máy bàn i9-14900 bằng 8 ảnh thật đã lưu, không phải một phiên ghi thật):

   | Ảnh | JPEG q95 (KB/khung) | Mã hóa JPEG (ms) | PNG (KB/khung) | Mã hóa PNG (ms) |
   |---|---|---|---|---|
   | 640×480 | 150–174 | 0,7 | 692–749 | 7,5–8,0 |
   | 1280×720 | 430–435 (hai khung nguyên vẹn); 506–524 (hai khung bị cắt) | 2,2–2,3 | 1.781–2.083 | 17–23 |

   Ảnh chụp camera nằm trên bàn nhìn thảm hoa văn. Cảnh ít chi tiết cho tệp nhỏ hơn. Ước lượng ban đầu "vài chục KB/khung"
   **sai** với cảnh này.

   Suy ra, **chưa đo trong phiên thật**:
   - 4 camera × 23,85 khung tốt/s (số đo 23/09) × ≈ 163 KB ≈ **15 MB/s ≈ 0,9 GB/phút ≈ 55 GB/giờ** ở 480p JPEG.
   - PNG ≈ 65 MB/s. Mã hóa PNG khoảng 7,7 ms × 95 khung/s, gần trọn một lõi cho một luồng ghi, nên PNG chỉ dùng cho đoạn ngắn.
   - Số tệp: ≈ 95 tệp ảnh/s, tức 57.000 tệp cho 10 phút.
   - Ổ D: của máy bàn còn trống 75 GB (đo 24/09), đủ ≈ 80 phút ở 480p JPEG.
   - LiDAR: ≈ 510 tia × 9 byte × 10 Hz ≈ 46 KB/s trước khi nén.
7. **Hàng đợi và RAM.**
   - Hàng đợi ghi giới hạn 192 MB ảnh chưa mã hóa (≈ 2 s của bốn camera 480p; ≈ 0,7 s ở 720p). Đầy thì khung bị bỏ và đếm
     (mục 1).
   - LiDAR giữ trong RAM tối đa một phần (600 vòng ≈ 2,8 MB).
   - Nếu tiến trình chết: ảnh và dòng CSV đã ghi vẫn còn (CSV được flush sau mỗi lô; có test kiểm dòng tới đĩa trong lúc
     còn đang ghi). Mất phần LiDAR đang dở (≤ 60 s) và `meta.json` cuối (`status` còn `đang ghi`).
   - Dòng CSV hỏng: lượt xem xét ngày 24/09 giết tiến trình 36 lần và chỉ thấy dòng nguyên vẹn (số của lượt xem xét, lượt
     sửa này không đo lại). Nhưng bộ đệm 8 KB của tệp có thể đẩy nửa dòng xuống đĩa giữa một lô lớn (hàng đợi dồn vì đĩa
     chậm), và mất điện hay hệ điều hành sập có thể để lại đuôi byte NUL. Hai trường hợp này chỉ được **giả lập** trong
     test (cắt dòng, thêm NUL); trên máy thật **CHƯA THỬ**.
   - Phát lại (sửa 24/09): dòng `frames.csv` thiếu cột, có cột rỗng hay có số không đọc được — kể cả dòng cuối bị cắt
     ngay sau `t_s` và dòng có byte NUL — bị bỏ và đếm ở `bad_rows`. Khung có tệp ảnh không đọc hay không giải mã được
     (tệp thiếu, tệp rác, tên hỏng) thành `decode_errors`: nguồn ném "phát lại không đọc/giải mã được …" (camera đếm ở
     `read_failures`) rồi đi tiếp tới hết bản ghi. Trước bản sửa, một dòng cắt ngay sau `t_s` thành một khung không có
     tệp; nguồn đọc lại mục đó mãi, phát lại không bao giờ tới "HẾT BẢN GHI" và bench chạy tới hạn cứng mà vẫn trả mã 0.
   - Một luồng ghi có theo kịp 4 × 24 khung/s không, trên máy bàn hay trên laptop RTX 3050 Ti, thì **CHƯA ĐO**.
8. **Cửa sổ ghi:**
   - Bench ghi từ lúc đặt lại số đo (sau phần làm nóng) tới lúc chốt số. `.rig.json` của phiên ghi và bản ghi có thể lệch
     nhau vài khung ở hai mép; test cho phép tối đa 3 khung.
   - Nút giao diện ghi từ lúc bấm tới lúc bấm lại.
   - `t_start_s` là lúc bộ ghi bắt đầu nhận dữ liệu. Mọi khung tốt có stamp ≥ `t_start_s` được ghi, hoặc được đếm là bị
     bỏ (có test). Trước bản sửa 24/09, `Rig` chỉ đưa bộ ghi cho lớp bọc nguồn sau khi `start()` ghi xong `meta.json`
     đầu (3–80 ms, đo lúc xem xét trên máy bàn), nên khung tới trong khoảng đó bị mất mà không được đếm.
9. **Đồng hồ:** `perf_counter` tính từ lúc máy khởi động. Stamp của hai bản ghi qua hai lần khởi động máy không so trực
   tiếp được; dùng `created_utc` + `t_start_s`.
10. Ghi trong lúc phát lại được, và meta có `replay_of`. Bản ghi mới khi đó là JPEG mã hóa lần hai.
11. **Lỗi LiDAR và ngoại lệ thường của camera khi phát lại** (hạn chế đã biết, 24/09). Phát lại ném lại chúng dưới dạng
    `RuntimeError` mang nguyên văn đã ghi ("ValueError: …"). Vì vậy:
    - `last_error` lúc phát lại là "RuntimeError: ValueError: …", khác lúc chạy trực tiếp ("ValueError: …"); số lần lỗi
      (`read_failures`, `errors` của LiDAR) thì bằng lúc ghi;
    - ghi lại một phiên phát lại thì thông báo của các lỗi này có thêm một tiền tố "RuntimeError: ". Khung cũ, bị cắt, xé
      và đọc lỗi (`FrameReadError`) thì không bị, vì chúng được ném lại đúng lớp và đúng nguyên văn.

## 6. Kiểm thử (24/09/2026)

`tests/test_rig_replay.py`, 27 hàm (14 hàm ban đầu, 12 hàm thêm sau lượt xem xét 24/09, 1 hàm làm nóng AI thêm tối
24/09 sau phiên thật, mục 7), dùng nguồn giả trong
`tests/rig_fakes.py` (camera có vân, giữ mọi khung đã trả; khung cũ mỗi 11 lần đọc, khung cắt mỗi 7 lần; LiDAR giả có chất
lượng từng tia). Các test kiểm:

- **Bản ghi đúng với nguồn:**
  - đúng dãy khung tốt nguồn đã trả, không thiếu khung giữa chừng, đúng từng pixel (PNG), đúng stamp;
  - mỗi sự kiện nằm giữa đúng hai khung;
  - LiDAR có stamp trên đồng hồ bàn thử, có `t_first` và `quality`;
  - thư mục có tên tiếng Việt.
- **Ghi → phát lại qua `Rig` đầy đủ → ghi lại chính phiên phát lại:**
  - cùng số khung, cùng ảnh từng pixel;
  - stamp tương đối trùng tới 1 µs, sự kiện trùng loại, thứ tự và nguyên văn;
  - bộ đếm khung cũ/khung cắt của `MultiCameraManager` bằng lúc ghi;
  - LiDAR trùng mảng tia, chất lượng và stamp đầu/cuối vòng;
  - chạy theo thời gian thật, khung ra trễ trung vị < 15 ms.
- **JPEG mặc định:** ảnh gần đúng (sai khác trung bình < 3, lớn nhất ≤ 40 trên ảnh có nhiễu), không trùng khít. Ở tốc độ
  gấp đôi: thời gian và khoảng stamp chia đôi. Hết bản ghi thì `read()` chặn tới khi `stop()` rồi mới báo.
- **Hết bản ghi và dừng:**
  - hết bản ghi thì camera "cũ" và không còn bộ ảnh; `Rig.stop()` sạch;
  - dừng giữa chừng (chỉ bằng `MultiCameraManager.stop()`, hoặc bằng `Rig.stop()`) thì nguồn đang chờ lịch trả về ngay;
  - camera không mở được lúc ghi thì cũng không mở được lúc phát lại.
- **Lỗi được báo:**
  - hàng đợi đầy: khung bị bỏ, được đếm, có dòng `record_dropped`; phát lại bỏ qua chỗ trống và đếm nó;
  - đĩa đầy (OSError 28 giả lập): trạng thái `LỖI` ở `status()`, `meta.json`, `.rig.json` và bảng số đo; `rig.bench` trả mã 1;
  - thư mục có sẵn dữ liệu bị từ chối;
  - bản ghi có nguồn dùng đồng hồ khác bị từ chối khi phát lại.
- **bench:** `--record`, rồi `--replay` bằng `build_rig` thật với AI giả:
  - `.rig.json` có số khung bằng đúng bản ghi, số khung cắt bằng số sự kiện, số vòng LiDAR bằng bản ghi;
  - AI chấm được, `replay.finished`;
  - `--ports` chọn cổng; `--lidar` cùng `--replay` bị từ chối.
- **Giao diện offscreen:**
  - nút "Ghi phiên" ghi ra một bản ghi `xong`;
  - `build_window(["--replay", …])` hiện ảnh có lớp tô, tiêu đề "PHÁT LẠI"; ảnh chụp có khóa `replay`;
  - hết bản ghi thì mọi ô ghi "HẾT BẢN GHI" và báo đỏ.
- **Thêm sau lượt xem xét 24/09** (đĩa chậm giả bằng cách làm chậm `RigRecorder._write_bytes`):
  - bản ghi trước còn ghi nốt thì `start_recording` từ chối, không tạo thư mục; `Rig.stop()` chờ nó xong (`meta.json`
    thành `xong`, có phần LiDAR); giao diện làm mờ nút, bấm lại thì báo "LỖI: không bắt đầu ghi được … ghi nốt", đóng cửa
    sổ thì chờ ghi nốt;
  - `Rig.stop()` không gọi `stop_recording` trước vẫn chờ hàng đợi ghi hết;
  - `meta.json` đầu chậm 50 ms: mọi khung tốt có stamp ≥ `t_start_s` vẫn có trong bản ghi (4 camera, 200 khung/s mỗi
    camera);
  - `frames.csv` có dòng cuối cắt ngay sau `t_s`, dòng có đuôi NUL, dòng toàn NUL: mỗi loại đếm đúng 1 ở `bad_rows`, phát
    lại qua `MultiCameraManager` tới `finished`, không có `read_failures`;
  - tệp ảnh rác, mục không có tệp, tên tệp có NUL, tên trỏ vào thư mục: thành `decode_errors`, nguồn đi tiếp tới hết;
  - bench: `--record` vào thư mục có dữ liệu hay vào một tệp, `--jpeg-quality 0` thoát mã 2 mà không mở thiết bị nào
    (`build_rig` bị thay bằng hàm báo lỗi nếu bị gọi); giao diện với `--jpeg-quality 101` cũng vậy; bench trả mã 1 khi
    phát lại tới hạn cứng mà chưa hết bản ghi, mã 0 khi `--seconds` ngắn hơn bản ghi; bench trả mã 1 khi bản ghi chỉ bị
    bỏ khung (không có lỗi ghi);
  - lỗi đọc LiDAR được ghi (`lidar/events.csv`) và phát lại qua `Rig` (đúng số lần, stamp tương đối lệch < 50 ms);
    ngoại lệ thường của camera được ghi thành `exception` và phát lại thành lỗi KHÔNG phải `FrameReadError`;
  - dòng CSV đã tới đĩa trong lúc bộ ghi còn chạy (flush sau mỗi lô).

Đột biến mã (24/09, trong một bản sao cô lập của mã): thử 12 đột biến, **cả 12 đều làm ít nhất một test hỏng**. Đó là:
bỏ sự kiện khi phát lại, không đổi gốc stamp, không chờ lịch, hết bản ghi trả `None`, không đếm khung bị bỏ, nuốt lỗi ghi,
đảo loại sự kiện, `Rig` không bọc nguồn, stamp LiDAR không đổi sang đồng hồ bàn thử, giao diện không báo hết bản ghi,
hàng đợi không giới hạn, và bench bắt đầu phát trước khi đặt lại số đo.

Ở lượt đầu, đột biến "stamp LiDAR không đổi đồng hồ" chỉ bị bắt vì test treo tới hạn 600 s. Sau đó test được thêm phép
kiểm độ dài bản ghi, và `ReplaySession` từ chối bản ghi có stamp nằm ngoài cửa sổ ghi quá 5 s. Chạy lại, đột biến này làm
6 test hỏng trong 9 s.

Lượt xem xét 24/09 chỉ ra 7 đột biến **lọt** qua 14 test ban đầu. Sau khi thêm 12 test, chạy lại 15 đột biến trong bản sao
cô lập (mỗi đột biến chỉ chạy các test liên quan): **cả 15 bị bắt**, và đã xem lý do hỏng của từng cái là đúng phép kiểm
nhắm tới. Gồm 8 đột biến gỡ từng bản sửa của lượt này: bỏ phép chặn bộ ghi đang ghi nốt, gán bộ ghi cho lớp bọc sau
`start()`, bỏ kiểm cột `frames.csv`, chỉ bắt `OSError` khi đọc ảnh, bench không báo phát lại kẹt, bench và giao diện bỏ
kiểm tham số ghi sớm, giao diện không làm mờ nút. Và 7 đột biến từng lọt: lớp bọc LiDAR không ghi lỗi, phát lại bỏ qua lỗi
LiDAR, lớp bọc camera không ghi `exception`, phát lại `exception` thành `FrameReadError`, `Rig.stop()` không chờ bộ ghi,
bench chỉ xét lỗi ghi mà bỏ qua khung bị bỏ, và không flush CSV sau mỗi lô.

## 7. Phiên thật đầu tiên (tối 24/09/2026, máy bàn)

Bốn camera 640×480 ở cổng hub 1–4 và LiDAR COM4, AI bật, 60 s đo sau 5 s làm nóng. Camera nhìn chỗ tối như phiên
`may_moi` lúc 15:25. Tệp gốc (git-ignore): bản ghi `runs/rig_recordings/o03_20260924/`, số đo
`runs/rig_bench/20260924_own/o03…o06`. Bản rút gọn trong git:
[evidence/rig/cho_nhip_rieng_ghi_phat_lai_20260924.json](evidence/rig/cho_nhip_rieng_ghi_phat_lai_20260924.json).

```powershell
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --ports 1 2 3 4 --lidar COM4 --seconds 60 --name o03_480p_ghi --out runs/rig_bench/20260924_own --record runs/rig_recordings/o03_20260924
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --replay runs/rig_recordings/o03_20260924 --name o06_phat_lai_o03_lam_nong_moi_co --out runs/rig_bench/20260924_own
```

**Ghi (o03):**

- 5724 khung JPEG q95 (1431 mỗi camera), **0 khung bị bỏ**, 601 vòng LiDAR, trạng thái `xong`.
- 298,6 MB trong 60 s, tức **4,98 MB/s**, ≈ 52 KB/khung. Ước lượng ở mục 5 (≈ 163 KB/khung, 15 MB/s) làm trên ảnh nhìn thảm
  hoa văn. Cảnh tối ít chi tiết nên tệp nhỏ hơn ba lần. Cảnh sa bàn thật sẽ ở giữa hay trên, **chưa đo**.
- CPU tiến trình trung bình 0,78 lõi (max 1,02), so với 0,68 lõi ở phiên cùng cấu hình không ghi (o02, 120 s). Chênh lệch
  ≈ 0,1 lõi này gồm cả luồng ghi và nhiễu giữa hai phiên, chưa tách riêng.
- Ghi không ảnh hưởng thấy được tới bàn thử: AI 23,85 bộ/s, lô trung vị 12,3 ms, 0 bộ bỏ camera, LiDAR 10,0 Hz, 0 lỗi.

**Phát lại cùng bản ghi, cùng quy tắc (bench `--replay`, AI thật trên GPU):**

| | Phiên thật o03 | o04: phát lại, chưa làm nóng | o05: làm nóng lô 4 ảnh | **o06: làm nóng mọi cỡ lô** |
|---|---|---|---|---|
| Bộ ảnh | 1432 | 1364 | 1403 | **1432** |
| Khung không vào bộ nào (cổng 1/2/3/4) | 0/0/0/0 | 34/34/67/34 | 0/0/29/0 | **0/0/0/0** |
| Bộ thiếu camera (`sets.sets_partial`; khác `sets_partial_wait` ghi trong tệp bằng chứng, là 0 ở o04) | 0 | 1 | 1 | 1 (cổng 3, ở giây đầu) |
| Độ lệch bộ trung vị / p95 / max (ms) | 26,0 / 42,1 / 44,8 | 26,8 / 27,0 / 30,4 | 26,0 / 42,1 / 44,8 | **26,0 / 42,1 / 44,8** |
| LiDAR − mốc bộ, trung vị (ms) | −19,8 | −23,4 | −19,7 | −19,6 |
| Lô AI: trung vị / max (ms) | 12,3 / 18,4 | 11,8 / **1457** | 12,1 / **1272** | 12,1 / 19,7 |
| Khung ra muộn so với lịch, trung vị | — | 0,3 ms | 0,3 ms | 0,3 ms |

- **Lỗi tìm ra nhờ phiên thật, đã sửa.** Đồng hồ phát lại bắt đầu ngay khi mô hình nạp xong. Nhưng lần đầu gặp mỗi cỡ lô
  (4, 3, 2, 1 ảnh), AI mất 1,2–1,7 s để khởi tạo (đo ở [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 10.3). Vì
  vậy phần đầu bản ghi trôi qua không được chấm (o04). Chỉ làm nóng lô 4 ảnh thì còn một lần đứng 1,27 s ở bộ thiếu camera
  đầu tiên (o05). **Sửa:** `AIWorker` chạy một lô ảnh đen cho mỗi cỡ lô trước khi báo sẵn sàng, ở cả phiên thật lẫn phát
  lại. Test: `test_replay_starts_after_the_ai_warm_up_batch_so_the_first_frames_reach_a_set`. Bỏ làm nóng thì test này
  hỏng: 14 lô thay vì 27.
- **Sau sửa (o06), phát lại cho đúng số bộ và đúng phân bố độ lệch như phiên thật.** Độ lệch bộ trùng tới 0,1 ms ở trung vị,
  p95 và max. Còn khác: một bộ thiếu cổng 3 ở giây đầu, khi chưa đo được nhịp camera; lô AI chậm nhất 19,7 ms so với
  18,4 ms. Kết quả AI **không** trùng từng bit vì ảnh JPEG đã mã hóa lại (mục 5).
- **Chưa thử:** bản ghi có camera bị cắt/xé khung thật, nên chưa so được hai quy tắc chờ trên cùng dữ liệu có camera lỡ
  nhịp; giao diện `--replay` với bản ghi thật (mới chạy với nguồn giả); phát lại ở speed ≠ 1 trên bản ghi thật.

## 8. Việc tiếp theo

- Ghi một phiên có camera lỡ nhịp thật (khung bị cắt/xé, thường thấy ở 720p khi camera nhìn cảnh sáng, nhiều chi tiết).
  Sau đó chạy cùng bản ghi với `--max-wait-ms 60` và `--max-wait-ms 0`. Đây là phép so hai quy tắc trên cùng dữ liệu thật.
- Ghi một phiên nhìn sa bàn thật để biết MB/s ở cảnh có chi tiết.
- Làm lại trên laptop RTX 3050 Ti (máy nộp đồ án): luồng ghi có theo kịp không, đĩa của laptop có đủ chỗ không, làm nóng AI
  mất bao lâu.
