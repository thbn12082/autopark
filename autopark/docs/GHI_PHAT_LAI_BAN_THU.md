# Ghi và phát lại phiên bàn thử — bốn camera + LiDAR (24/09/2026)

Tài liệu này hướng dẫn ghi một phiên bàn thử (bốn camera + LiDAR) xuống đĩa, rồi phát lại phiên đó mà không cần cắm
thiết bị. Nó cũng ghi định dạng thư mục, các giới hạn của phát lại, các test và phiên thật đầu tiên. Mục 9 mô tả cách ghi
cùng định dạng ngay trong phiên đỗ xe của `ui.lidar_app`. Bàn thử được mô tả ở
[GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md).

Một số phần dưới đây mang mã công cụ nghiệm thu T1–T15 ([KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 7): T3 là
ghi cảm biến trong phiên đỗ, T9 là phát lại lần chạy qua `VehicleIO`, T10 là trường khoảng hở của từng camera, T13 là
ghi sự kiện dừng của phiên vào log `VehicleIO`, T14 là dấu đồng bộ video–log.

## Hiện trạng

- **Tối 24/09/2026:** phần mềm và test với nguồn giả xong. Đã ghi **một** phiên thật trên máy bàn: bốn camera 480p +
  LiDAR + AI, 60 s, 0 khung bị bỏ, 4,98 MB/s. Phát lại phiên đó cho đúng số bộ và độ lệch như lúc ghi (mục 7).
- Số ở mục 5 là số đo trên ảnh đã lưu từ ngày 23/09, hoặc là ước lượng suy ra; mỗi số ghi rõ thuộc loại nào.
- **Từ 02/10/2026 (T3):** ghi cùng định dạng có ngay trong phiên đỗ xe của `ui.lidar_app` (ngăn "Ghi cảm biến", mục 9).
  Mọi phần LiDAR của một thư mục bản ghi phát lại được trong các công cụ LiDAR (mục 2). Phần này chỉ kiểm offscreen với
  nguồn giả, chưa thử với thiết bị thật.
- **Các lượt ghi sau trên máy bàn hiện tại:** ngày 29/09/2026 một phiên 30 s được ghi rồi phát lại đủ 3.026 khung và
  301 vòng LiDAR ([kiem_may_20260929.md](evidence/chuyen_may_20260929/kiem_may_20260929.md)). Ngày 02/10/2026 phép chạy
  dài LD-1 ghi 30 phút, 4,44 MB/s, không bỏ khung ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) cuối mục 3.5).
- **Chưa có:** bản ghi nào có camera lỡ nhịp thật. Chưa chạy gì trên laptop.

## Để làm gì

Bàn thử (`rig.bench`, `ui/rig_app.py`) cần bốn camera, LiDAR và cổng COM. Ghi một phiên một lần, sau đó có thể:

- chạy lại cả bàn thử từ bản ghi (ghép bộ ảnh, chờ camera chậm, AI, LiDAR so với bộ ảnh, giao diện) mà không cắm gì;
- chạy **hai quy tắc khác nhau trên cùng một dữ liệu**, ví dụ `--max-wait-ms 60` và `--max-wait-ms 0`. Trên phần cứng,
  hai phiên chạy hai quy tắc không bao giờ có cùng dữ liệu;
- dùng dữ liệu thật trong test và demo, và để phát triển các phần khác (BEV từ AI, định vị LiDAR) trên cùng một bản ghi.

Mã: [`autopark/rig/recording.py`](../autopark/rig/recording.py) (ghi),
[`autopark/rig/replay.py`](../autopark/rig/replay.py) (phát lại), cách nối vào `Rig` ở
[`autopark/rig/core.py`](../autopark/rig/core.py). Test: [`tests/test_rig_replay.py`](../tests/test_rig_replay.py).

## 1. Ghi

Có hai cách ghi: lệnh đo `rig.bench --record` và nút "Ghi phiên" của giao diện. Mỗi lệnh viết trên một dòng, dán được vào
cmd.exe lẫn PowerShell. Dòng `#` là chú thích, đừng dán vào cmd.

```powershell
# lệnh đo không giao diện: ghi đúng phần đo (sau --warmup), cùng lúc ghi g01.rig.json như mọi phiên
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 120 --name g01 --out runs/rig_bench/20260925 --record runs/rig_recordings/g01

# giao diện: nút "Ghi phiên" bật/tắt; mỗi lần bật ghi vào thư mục --record-root, mỗi lần một thư mục con theo giờ
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.ui.rig_app --lidar --record-root runs/rig_recordings
```

`--lidar` không kèm giá trị thì dùng cổng LiDAR trong `configs/thiet_bi.json`; `--lidar COMx` ghi đè
([chuyển máy](CHUYEN_MAY_BAN.md)).

- **Định dạng ảnh:** `--record-format png` cho ảnh không mất mát. PNG lớn hơn JPEG khoảng 4,5 lần và mã hóa chậm hơn
  khoảng 10 lần (mục 5), nên chỉ hợp với đoạn ngắn. `--jpeg-quality` mặc định 95.
- **Thư mục ghi** phải chưa có hoặc đang rỗng; bộ ghi không ghi đè một bản ghi cũ. Từ 24/09, `rig.bench` kiểm `--record`
  (thư mục đã có dữ liệu, hay là một tệp) và `--jpeg-quality` (phải trong 1..100) **ngay khi đọc dòng lệnh**. Việc kiểm
  này chạy trước khi mở camera, quay LiDAR, nạp AI và làm nóng. Sai thì lệnh thoát mã 2 kèm câu lỗi, không có traceback
  sau vài chục giây khởi động. Giao diện cũng kiểm `--jpeg-quality` lúc khởi động.
- **Mỗi lúc chỉ có một bản ghi chưa xong.** Tắt "Ghi phiên" khi hàng đợi còn nhiều khung thì bản ghi đó "đang ghi nốt".
  Trong lúc ấy nút bị làm mờ, và `Rig.start_recording` từ chối ghi phiên mới ("bản ghi trước … còn đang ghi nốt", không
  tạo thư mục mới). Đóng cửa sổ hay `Rig.stop()` chờ bản ghi ghi nốt xong, tối đa 60 s; quá thì báo `rig-recorder` là
  luồng chưa dừng. Trước bản sửa ngày 24/09, bật lại "Ghi phiên" trong lúc ghi nốt rồi đóng cửa sổ thì bản ghi đầu bị
  cắt âm thầm: mất khung còn trong hàng đợi, mất phần LiDAR trong RAM, `meta.json` kẹt ở `đang ghi`.
- **Ghi những gì:** **mọi khung tốt** mà nguồn camera trả cho luồng camera, tức là sau khi `UsbCameraSource` đã loại khung
  cũ, khung bị cắt và khung xé. Mỗi lần đọc hỏng được ghi thành **sự kiện** có stamp và nguyên văn thông báo, không kèm
  ảnh. Ghi thêm mọi vòng LiDAR, lỗi đọc LiDAR và `meta.json`.
- **Không ghi:** kết quả AI (phát lại sẽ chạy lại AI), bộ ảnh đã ghép, số đo tài nguyên. Những thứ đó nằm trong
  `.rig.json` của phiên. Bản ghi trong phiên đỗ (mục 9) có thêm bảng quyết định AI theo lô `session/ai_batches.csv`, nhưng
  vẫn không có xác suất.
- **Tắt ghi** thì bộ ghi ngừng nhận ngay. Phần còn trong hàng đợi được ghi nốt ở nền, nên giao diện không bị đứng. Trên
  bảng số đo, mục "GHI PHIÊN" hiện trạng thái (`đang ghi`, `đang ghi nốt`, `xong` hoặc `LỖI`), số khung đã ghi, số khung
  bị bỏ, MB đã ghi, MB/s và số khung đang chờ ghi.
- **Lỗi không bị bỏ qua im lặng:**
  - Hàng đợi đầy (đĩa chậm): khung bị **bỏ**, được đếm (`dropped`) và để lại một dòng `record_dropped` trong
    `events.csv`. Giao diện ghi "GHI THIẾU".
  - Lỗi ghi (đĩa đầy, mất quyền…): trạng thái chuyển thành `LỖI`, câu lỗi được giữ nguyên văn, và mọi khung sau đó bị bỏ
    và đếm. Giao diện ghi "LỖI GHI: …".
  - `rig.bench` trả mã 1 và in "CẢNH BÁO: bản ghi … không trọn" khi bản ghi có lỗi, có khung bị bỏ, hoặc chưa ghi nốt xong.
- **Dấu đồng bộ video–log không nằm trong thư mục bản ghi** (T14, thêm 02/10/2026; chỉ kiểm offscreen, chưa thử trên màn
  hình thật).
  - `rig.bench --sync-mark` ghi dấu vào `<out>/<name>.sync.csv` cạnh `<name>.rig.json`, và vào khóa `sync_marks` trong
    `.rig.json`.
  - Nút "Dấu đồng bộ (F8)" của `ui.rig_app` ghi vào `runs/sync_marks/<giờ>_ui_rig_app.csv`; cột `state` = `recording`
    khi đang ghi phiên.
  - Cột `t_perf` của dấu là `perf_counter`, cùng đồng hồ với mọi `t_s` của bản ghi (mục 3). Vì vậy đặt được dấu lên trục
    thời gian của bản ghi khi cùng máy và cùng lần khởi động máy.
  - Không dùng với `--replay`: bench từ chối, nút của `rig_app` khóa khi phát lại.

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
- Mode camera (kích thước, fps yêu cầu) lấy từ bản ghi, không lấy từ `--width/--height`. Quy tắc ghép bộ
  (`--max-skew-ms`, `--max-wait-ms`) và AI (`--checkpoint`, `--no-ai`) lấy từ dòng lệnh.
- Đồng hồ phát lại chỉ chạy **sau khi AI nạp xong mô hình và làm nóng mọi cỡ lô** (hoặc nạp lỗi), để AI thấy bản ghi từ
  khung đầu. Phần làm nóng được thêm tối 24/09 (mục 7). Trong bench, thứ tự là: nạp mô hình → làm nóng → `--warmup` (mặc
  định 0 khi phát lại) → đặt lại số đo → bắt đầu phát. Vì vậy số khung trong `.rig.json` bằng đúng số khung trong bản
  ghi. Khối `replay` trong json ghi `finished` và độ trễ thực của từng camera so với lịch (`late_ms`).
- Giao diện: tiêu đề và bảng số đo ghi "PHÁT LẠI"; chưa bắt đầu thì ô camera ghi "phát lại chưa bắt đầu (chờ AI nạp mô
  hình)". Bộ ảnh chụp bằng "Chụp bộ ảnh" trong lúc phát lại có khóa `replay` trong `meta.json`, để không bị lẫn với ảnh
  camera thật khi đem đi gán nhãn.
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

**Phần LiDAR trong các công cụ LiDAR** (T3, thêm 02/10/2026; chỉ kiểm bằng test). Mọi phần LiDAR của một thư mục bản ghi
đọc được như MỘT bản ghi (`lidar.recording.read_lidar_any`, dùng `rig.replay.load_lidar`). Các lệnh nhận thư mục này:

- `ui.lidar_app --recording <thư mục>`;
- `lidar.live_view --recording <thư mục>`;
- `lidar.localize --recording <thư mục>`;
- `lidar.pose_estimator --recording <thư mục>` ([NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md) mục 3).

Bản ghi không có camera (chỉ LiDAR) phát lại được bằng `rig.bench --replay <thư mục> --no-ai`. Nếu có AI thì bench từ
chối ngay (mã 2, "bản ghi không có camera …: thêm --no-ai …").

## 3. Định dạng thư mục (`format_version` 1)

| Tệp | Nội dung |
|---|---|
| `meta.json` | thông tin chung của bản ghi; danh sách khóa ở ngay dưới bảng |
| `cam_p<cổng>/frames.csv` | `seq, t_s, width, height, file, bytes`: một dòng cho mỗi khung tốt **đã ghi xuống đĩa**. `seq` đếm mọi khung tốt đã thấy, từ 1; chỗ `seq` nhảy cóc là khung bị bỏ |
| `cam_p<cổng>/events.csv` | `t_s, kind, after_seq, message`; các giá trị `kind` và ý nghĩa `after_seq` ở dưới bảng |
| `cam_p<cổng>/0000001.jpg` | ảnh BGR mã hóa bằng `cv2.imencode` (JPEG q95, hoặc PNG nén mức 1); ghi bằng `write_bytes` vì `cv2.imwrite` không ghi được vào đường dẫn tiếng Việt |
| `lidar/part_0000.npz` + `.json` | tối đa 600 vòng (≈ 60 s) mỗi phần, định dạng `ScanRecorder`: `t` (cuối vòng), `t_first` (đầu vòng), `n_beams`, `angles`, `ranges` (NaN = không phản hồi), `quality` |
| `lidar/events.csv` | `t_s, message`: lỗi đọc LiDAR |
| `session/clock.csv` | *(chỉ bản ghi trong phiên đỗ, T3, 02/10/2026)* mốc ghép `perf_counter` với thời gian phiên và đồng hồ `VehicleIO`, mục 9 |
| `session/ai_batches.csv` | *(T3, khi ghi camera và bật "Kết quả AI theo lô")* một dòng cho mỗi lô AI ngăn AI camera đã xét, mục 9 |
| `session/sync_marks.csv` | *(T3)* bản sao dấu đồng bộ của cửa sổ lúc dừng ghi, cột `SYNC_FIELDS` |

**Khóa của `meta.json`:**

- `format`, `format_version`;
- `status`: `đang ghi` → `xong` / `lỗi`; bản ghi bị ngắt giữa chừng giữ `đang ghi`;
- `created_utc`/`created_local`, `t_start_s`/`t_stop_s`, `clock` (tên, độ phân giải), `git_commit`, `host`;
- `ecoqos`: trạng thái EcoQoS của tiến trình ghi lúc ghi meta (thêm 02/10/2026);
- `opencv`, `image` (định dạng, chất lượng), `config` và `policy` của Rig, `camera_mode`;
- `cameras`: cổng, index, instance_id, `source_rejects_damaged`, lỗi mở; `cameras_at_stop`: bộ đếm từng camera lúc dừng,
  gồm lỗi mở;
- `lidar_source` (cổng, `describe()` của driver), `lidar_at_stop`;
- `per_port`: khung thấy / đã ghi / bị bỏ, số sự kiện theo loại, stamp đầu/cuối;
- `lidar`: các phần, số vòng;
- `replay_of` (khi ghi trong lúc phát lại), `notes`, `error`, `errors`;
- từ 02/10/2026 (T3), mọi bản ghi thêm `tables` (bảng phụ: cột, số dòng), `files` (tệp CSV trọn vẹn đã ghi), `warnings`,
  `lidar.out_of_order_dropped`; bản ghi trong phiên đỗ thêm khóa `session_recording` (mục 9).

**`events.csv` của camera:** `kind` ∈ `duplicate`, `truncated`, `torn`, `read_failed`, `exception` (như nguồn báo, phân
loại giống `CameraWorker`) hoặc `record_dropped` (bộ ghi bỏ khung). `after_seq` là khung tốt cuối cùng trước sự kiện,
dùng để giữ đúng thứ tự khi phát lại.

**Đồng hồ.** Mọi `t_s` là đồng hồ bàn thử `time.perf_counter` tính bằng giây. Với camera, đó là lúc `read()` trả khung
(đã gồm giải mã); với LiDAR, là lúc byte cuối của vòng tới máy. Stamp LiDAR được đổi từ giờ phiên của driver sang đồng hồ
bàn thử bằng `t0`, cùng phép đổi mà `LidarWorker` dùng. `created_utc` ứng với `t_start_s`, nên từ đó suy được giờ thật
của từng stamp; sai số bằng độ lệch giữa hai lần đọc đồng hồ, cỡ micro giây.

Vòng LiDAR có stamp sớm hơn vòng đã ghi trước nó bị bỏ và đếm (`lidar.out_of_order_dropped`, `warnings`); trạng thái vẫn
`xong`. Trước 02/10/2026 (T3), trường hợp này làm cả bản ghi thành `lỗi`. Lý do đổi: nguồn LiDAR của ngăn LiDAR có thể
được nối lại giữa lúc ghi.

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
  Test kiểm điều này qua bộ đếm của `MultiCameraManager`.
- Camera không mở được lúc ghi thì lúc phát lại cũng không mở được. Lỗi ghi là "lúc ghi camera cổng N không mở được: …".
- Bản ghi có stamp nằm ngoài cửa sổ ghi [`t_start_s` − 5 s; `t_stop_s` + 5 s] bị từ chối (`ReplayError`, "các nguồn
  không cùng một đồng hồ?"). Nếu không từ chối, phát lại sẽ lặng lẽ "chờ" hàng giờ giữa hai nguồn. Bản ghi bị ngắt giữa
  chừng không có `t_stop_s`, nên không được kiểm điều này.
- **Hết bản ghi:**
  - Nguồn ngừng trả khung: `read()` chặn tới khi được yêu cầu dừng, không trả `None` và không ném lỗi liên tục. Có ba
    cách dừng: `session.stop()`, `close()`, hoặc luồng camera/LiDAR đang gọi nó bị yêu cầu dừng. Khi dừng, nó mới báo
    "hết bản ghi phát lại".
  - Sau 0,5 s (`STALE_AFTER_S`) camera chuyển thành "cũ", không còn bộ ảnh mới, AI ngừng. `session.finished` thành True.
  - `rig.bench` tự dừng: chờ thêm 0,3 s cho AI chấm nốt bộ cuối rồi chốt số. Giao diện ghi "HẾT BẢN GHI phát lại" ở đầu
    mọi ô (báo đỏ) và trên bảng số đo.
  - Bench còn có hạn cứng: độ dài bản ghi / speed + 10 s. Từ 24/09, nếu phát lại không có `--seconds` mà chạy tới hạn
    cứng vẫn chưa hết bản ghi (một nguồn kẹt), bench in "CẢNH BÁO: phát lại chạy tới hạn cứng …" và trả mã 1. Có
    `--seconds` ngắn hơn bản ghi thì dừng trước khi hết là đúng ý, không tính là lỗi.
  - **Không lặp lại.**

## 5. Giới hạn — đọc trước khi dùng số của một phiên phát lại

1. **Stamp đã đổi gốc sang đồng hồ phát lại** (mục 4). Không so giá trị tuyệt đối với phiên gốc. Khoảng cách và độ lệch
   thì so được.
2. **JPEG mã hóa lại làm pixel đổi một chút.** Đo ngày 24/09 trên 8 ảnh thật chụp ngày 23/09 (`runs/rig_snapshots/`) với
   `cv2.imencode` q95:
   - sai khác trung bình 0,85–1,24 mức xám;
   - lớn nhất 10–18 mức xám ở 480p, 13–17 ở hai khung 720p nguyên vẹn. Hai khung 720p còn lại là khung bị cắt (chụp
     trước khi có bộ dò; `truncated_rows` = 352 và 328 khi kiểm lại ngày 24/09) và có chỗ lệch tới 162–194.

   AI chấm trên ảnh hơi khác ảnh gốc, nên kết quả AI khi phát lại **không** trùng từng bit với lúc chạy trực tiếp. Cần
   trùng từng pixel thì ghi PNG.
3. **Bộ dò khung hỏng đã chạy lúc ghi.** Bản ghi chỉ chứa ảnh của khung tốt; khung cũ, bị cắt hay xé chỉ còn là sự kiện,
   không có ảnh. Vì vậy phát lại không thử lại được bộ dò (`truncated_rows`, `torn_bands`). Khung hỏng mà bộ dò bỏ sót lúc
   ghi thì nằm trong bản ghi như khung tốt.
4. **Phát lại không tái tạo phần cứng.** Không có tranh chấp băng thông USB, không có DirectShow, không có giải mã MJPEG
   của driver. Thay vào đó là giải mã JPEG từ đĩa, ≈ 1,4 ms/khung 480p (đo trên ảnh 23/09). Vì vậy CPU, GPU và thời gian
   AI trong `.rig.json` của phiên phát lại không thay được số đo trực tiếp.
5. **speed ≠ 1:** nhịp đo được (fps, chu kỳ khung, ngưỡng chờ L) đổi theo speed. Các ngưỡng tuyệt đối thì không đổi:
   0,5 s để coi là "cũ", `max_skew` 60 ms, sàn chờ 60 ms, hạn AI 0,5 s. Vì vậy kết quả ghép bộ ở speed ≠ 1 **không** so
   được với phiên gốc. Để so quy tắc thì dùng speed 1.
6. **Cỡ bản ghi và tải ghi.** Bảng dưới đo ngày 24/09 trên máy bàn i9-14900 bằng 8 ảnh thật đã lưu, không phải một phiên
   ghi thật:

   | Ảnh | JPEG q95 (KB/khung) | Mã hóa JPEG (ms) | PNG (KB/khung) | Mã hóa PNG (ms) |
   |---|---|---|---|---|
   | 640×480 | 150–174 | 0,7 | 692–749 | 7,5–8,0 |
   | 1280×720 | 430–435 (hai khung nguyên vẹn); 506–524 (hai khung bị cắt) | 2,2–2,3 | 1.781–2.083 | 17–23 |

   Ảnh chụp camera nằm trên bàn nhìn thảm hoa văn; cảnh ít chi tiết cho tệp nhỏ hơn. Ước lượng ban đầu "vài chục
   KB/khung" **sai** với cảnh này.

   Suy ra từ bảng, **chưa đo trong phiên thật**:
   - 4 camera × 23,85 khung tốt/s (số đo 23/09) × ≈ 163 KB ≈ **15 MB/s ≈ 0,9 GB/phút ≈ 55 GB/giờ** ở 480p JPEG.
   - PNG ≈ 65 MB/s. Mã hóa PNG khoảng 7,7 ms × 95 khung/s, gần trọn một lõi cho một luồng ghi, nên PNG chỉ dùng cho đoạn
     ngắn.
   - Số tệp: ≈ 95 tệp ảnh/s, tức 57.000 tệp cho 10 phút.
   - Ổ D: máy bàn dùng tới 25/09/2026 còn trống 75 GB (đo 24/09), đủ ≈ 80 phút ở 480p JPEG. Trên máy bàn từ 29/09/2026:
     - ≈ 30,6 GB, đo 29/09/2026 ([chuyển máy](CHUYEN_MAY_BAN.md) mục 4);
     - ≈ 28 GB sau khi cài PlatformIO chiều cùng ngày (mục 7 của biên bản đó);
     - 62,58 GB khi đo lại bằng `Get-PSDrive` lúc 15:23 ngày 30/09/2026, đủ ≈ 70 phút ở 480p JPEG với cảnh nhiều chi tiết
       như trên. Lần đo này không lưu log, và chưa ghi vì sao ổ trống thêm.

     Đo lại trước mỗi phiên ghi dài.
   - LiDAR: ≈ 510 tia × 9 byte × 10 Hz ≈ 46 KB/s trước khi nén.
7. **Hàng đợi và RAM.**
   - Hàng đợi ghi giới hạn 192 MB ảnh chưa mã hóa (≈ 2 s của bốn camera 480p; ≈ 0,7 s ở 720p). Đầy thì khung bị bỏ và
     đếm (mục 1).
   - LiDAR giữ trong RAM tối đa một phần (600 vòng ≈ 2,8 MB).
   - Nếu tiến trình chết: ảnh và dòng CSV đã ghi vẫn còn (CSV được flush sau mỗi lô; có test kiểm dòng tới đĩa trong lúc
     còn đang ghi). Mất phần LiDAR đang dở (≤ 60 s) và `meta.json` cuối (`status` còn `đang ghi`).
   - Dòng CSV hỏng: lượt xem xét ngày 24/09 giết tiến trình 36 lần và chỉ thấy dòng nguyên vẹn (số của lượt xem xét, lượt
     sửa sau đó không đo lại). Nhưng bộ đệm 8 KB của tệp có thể đẩy nửa dòng xuống đĩa giữa một lô lớn (hàng đợi dồn vì
     đĩa chậm), và mất điện hay hệ điều hành sập có thể để lại đuôi byte NUL. Hai trường hợp này chỉ được **giả lập** trong
     test (cắt dòng, thêm NUL); trên máy thật chưa thử.
   - Phát lại (sửa 24/09): dòng `frames.csv` thiếu cột, có cột rỗng hay có số không đọc được bị bỏ và đếm ở `bad_rows`,
     kể cả dòng cuối bị cắt ngay sau `t_s` và dòng có byte NUL. Khung có tệp ảnh không đọc hay không giải mã được (tệp
     thiếu, tệp rác, tên hỏng) thành `decode_errors`: nguồn ném "phát lại không đọc/giải mã được …" (camera đếm ở
     `read_failures`) rồi đi tiếp tới hết bản ghi. Trước bản sửa, một dòng cắt ngay sau `t_s` thành một khung không có
     tệp; nguồn đọc lại mục đó mãi, phát lại không bao giờ tới "HẾT BẢN GHI", và bench chạy tới hạn cứng mà vẫn trả mã 0.
   - Một luồng ghi có theo kịp 4 × 24 khung/s không, trên máy bàn hay trên laptop RTX 3050 Ti, thì **chưa đo**.
8. **Cửa sổ ghi:**
   - Bench ghi từ lúc đặt lại số đo (sau phần làm nóng) tới lúc chốt số. `.rig.json` của phiên ghi và bản ghi có thể lệch
     nhau vài khung ở hai mép; test cho phép tối đa 3 khung.
   - Nút giao diện ghi từ lúc bấm tới lúc bấm lại.
   - `t_start_s` là lúc bộ ghi bắt đầu nhận dữ liệu. Mọi khung tốt có stamp ≥ `t_start_s` được ghi, hoặc được đếm là bị
     bỏ (có test). Trước bản sửa ngày 24/09, `Rig` chỉ đưa bộ ghi cho lớp bọc nguồn sau khi `start()` ghi xong `meta.json`
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
12. **Khoảng hở cuối của camera khi phát lại** (T10, thêm 02/10/2026; chỉ kiểm với nguồn giả).
    - Từ T10, `gap_max_ms` của từng camera trong `.rig.json` tính cả khoảng hở còn mở lúc chốt số (`gap_end_ms`); nghĩa
      cũ nằm ở `gap_closed_max_ms`.
    - Khi phát lại, `gap_end_ms` (và `gap_max_ms` tính từ nó) đo tới cuối bản ghi, không tới lúc bench chốt số, vì hết
      bản ghi không phải là camera ngừng. Cuối bản ghi là max(mục cuối, `t_stop_s` của `meta.json`), đổi sang đồng hồ phát
      lại (`ReplaySession.end_t`).
    - Nếu đo tới lúc chốt số thì mọi camera có một khoảng hở giả bằng lúc chờ sau mục cuối. Bench chờ
      `REPLAY_END_GRACE_S` = 0,3 s; lượt viết mã T10 ngày 02/10/2026 thử thấy ≈ 0,3–0,6 s, không lưu log.
    - `--seconds` ngắn hơn bản ghi thì mốc là lúc chốt số.
    - Ở mọi phiên, khoảng hở đi qua lúc hết phần làm nóng được tính đủ cả phần trước đó. Vì vậy camera ngừng trong lúc làm
      nóng có `gap_max_ms` lớn hơn `--seconds` (`video/multicam.py`, `camera_stats`).
    - Test: `test_replay_measures_the_open_gap_to_the_end_of_the_recording_not_to_now`.

## 6. Kiểm thử (24/09/2026)

`tests/test_rig_replay.py` dùng nguồn giả trong `tests/rig_fakes.py`: camera có vân, giữ mọi khung đã trả; khung cũ mỗi
11 lần đọc, khung cắt mỗi 7 lần; LiDAR giả có chất lượng từng tia. Tới 02/10/2026 tệp có 29 hàm:

- 14 hàm ban đầu;
- 12 hàm thêm sau lượt xem xét ngày 24/09;
- 1 hàm làm nóng AI, thêm tối 24/09 sau phiên thật (mục 7);
- 1 hàm khoảng hở cuối khi phát lại (T10, 02/10/2026; mục 5 ý 12);
- 1 hàm `test_rig_never_stops_or_waits_for_an_external_recorder` (T3, 02/10/2026): bộ ghi ngoài gắn vào Rig chỉ được
  gỡ, không bị dừng hay chờ; `stop_recording`/`stop()` gọi `on_detach` một lần; bộ ghi của Rig như cũ.

Test của bản ghi trong phiên đỗ nằm ở mục 9. Các test kiểm:

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
  - đĩa đầy (OSError 28 giả lập): trạng thái `LỖI` ở `status()`, `meta.json`, `.rig.json` và bảng số đo; `rig.bench` trả
    mã 1;
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
- **Thêm sau lượt xem xét ngày 24/09** (đĩa chậm giả bằng cách làm chậm `RigRecorder._write_bytes`):
  - bản ghi trước còn ghi nốt thì `start_recording` từ chối, không tạo thư mục; `Rig.stop()` chờ nó xong (`meta.json`
    thành `xong`, có phần LiDAR); giao diện làm mờ nút, bấm lại thì báo "LỖI: không bắt đầu ghi được … ghi nốt", đóng
    cửa sổ thì chờ ghi nốt;
  - `Rig.stop()` không gọi `stop_recording` trước vẫn chờ hàng đợi ghi hết;
  - `meta.json` đầu chậm 50 ms: mọi khung tốt có stamp ≥ `t_start_s` vẫn có trong bản ghi (4 camera, 200 khung/s mỗi
    camera);
  - `frames.csv` có dòng cuối cắt ngay sau `t_s`, dòng có đuôi NUL, dòng toàn NUL: mỗi loại đếm đúng 1 ở `bad_rows`,
    phát lại qua `MultiCameraManager` tới `finished`, không có `read_failures`;
  - tệp ảnh rác, mục không có tệp, tên tệp có NUL, tên trỏ vào thư mục: thành `decode_errors`, nguồn đi tiếp tới hết;
  - bench: `--record` vào thư mục có dữ liệu hay vào một tệp, `--jpeg-quality 0` thoát mã 2 mà không mở thiết bị nào
    (`build_rig` bị thay bằng hàm báo lỗi nếu bị gọi); giao diện với `--jpeg-quality 101` cũng vậy; bench trả mã 1 khi
    phát lại tới hạn cứng mà chưa hết bản ghi, mã 0 khi `--seconds` ngắn hơn bản ghi; bench trả mã 1 khi bản ghi chỉ bị
    bỏ khung (không có lỗi ghi);
  - lỗi đọc LiDAR được ghi (`lidar/events.csv`) và phát lại qua `Rig` (đúng số lần, stamp tương đối lệch < 50 ms);
    ngoại lệ thường của camera được ghi thành `exception` và phát lại thành lỗi KHÔNG phải `FrameReadError`;
  - dòng CSV đã tới đĩa trong lúc bộ ghi còn chạy (flush sau mỗi lô).

**Kiểm đột biến** (24/09, trong một bản sao cô lập của mã). Thử 12 đột biến, **cả 12 đều làm ít nhất một test hỏng**:
bỏ sự kiện khi phát lại, không đổi gốc stamp, không chờ lịch, hết bản ghi trả `None`, không đếm khung bị bỏ, nuốt lỗi
ghi, đảo loại sự kiện, `Rig` không bọc nguồn, stamp LiDAR không đổi sang đồng hồ bàn thử, giao diện không báo hết bản
ghi, hàng đợi không giới hạn, và bench bắt đầu phát trước khi đặt lại số đo.

Ở lượt đầu, đột biến "stamp LiDAR không đổi đồng hồ" chỉ bị bắt vì test treo tới hạn 600 s. Sau đó test được thêm phép
kiểm độ dài bản ghi, và `ReplaySession` từ chối bản ghi có stamp nằm ngoài cửa sổ ghi quá 5 s. Chạy lại, đột biến này làm
6 test hỏng trong 9 s.

Lượt xem xét ngày 24/09 chỉ ra 7 đột biến **lọt** qua 14 test ban đầu. Sau khi thêm 12 test, chạy lại 15 đột biến trong
bản sao cô lập (mỗi đột biến chỉ chạy các test liên quan): **cả 15 bị bắt**, và đã xem lý do hỏng của từng cái là đúng
phép kiểm nhắm tới. Mười lăm đột biến gồm:

- 8 đột biến gỡ từng bản sửa của lượt này: bỏ phép chặn bộ ghi đang ghi nốt, gán bộ ghi cho lớp bọc sau `start()`, bỏ
  kiểm cột `frames.csv`, chỉ bắt `OSError` khi đọc ảnh, bench không báo phát lại kẹt, bench và giao diện bỏ kiểm tham số
  ghi sớm, giao diện không làm mờ nút;
- 7 đột biến từng lọt: lớp bọc LiDAR không ghi lỗi, phát lại bỏ qua lỗi LiDAR, lớp bọc camera không ghi `exception`,
  phát lại `exception` thành `FrameReadError`, `Rig.stop()` không chờ bộ ghi, bench chỉ xét lỗi ghi mà bỏ qua khung bị
  bỏ, và không flush CSV sau mỗi lô.

## 7. Phiên thật đầu tiên (tối 24/09/2026, máy bàn)

Bốn camera 640×480 ở cổng hub 1–4 và LiDAR COM4, AI bật, đo 60 s sau 5 s làm nóng. Camera nhìn chỗ tối như phiên
`may_moi` lúc 15:25. Tệp gốc (git-ignore): bản ghi `runs/rig_recordings/o03_20260924/`, số đo
`runs/rig_bench/20260924_own/o03…o06`. Bản rút gọn trong git:
[evidence/rig/cho_nhip_rieng_ghi_phat_lai_20260924.json](evidence/rig/cho_nhip_rieng_ghi_phat_lai_20260924.json).

```powershell
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --ports 1 2 3 4 --lidar COM4 --seconds 60 --name o03_480p_ghi --out runs/rig_bench/20260924_own --record runs/rig_recordings/o03_20260924
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --replay runs/rig_recordings/o03_20260924 --name o06_phat_lai_o03_lam_nong_moi_co --out runs/rig_bench/20260924_own
```

**Ghi (o03):**

- 5724 khung JPEG q95 (1431 mỗi camera), **0 khung bị bỏ**, 601 vòng LiDAR, trạng thái `xong`.
- 298,6 MB trong 60 s, tức **4,98 MB/s**, ≈ 52 KB/khung. Ước lượng ở mục 5 (≈ 163 KB/khung, 15 MB/s) làm trên ảnh nhìn
  thảm hoa văn. Cảnh tối ít chi tiết nên tệp nhỏ hơn ba lần. Cảnh sa bàn thật sẽ ở giữa hay cao hơn thì **chưa đo**.
- CPU tiến trình trung bình 0,78 lõi (max 1,02), so với 0,68 lõi ở phiên cùng cấu hình không ghi (o02, 120 s). Chênh lệch
  ≈ 0,1 lõi này gồm cả luồng ghi và nhiễu giữa hai phiên, chưa tách riêng.
- Ghi không ảnh hưởng thấy được tới bàn thử: AI 23,85 bộ/s, lô trung vị 12,3 ms, 0 bộ bỏ camera, LiDAR 10,0 Hz, 0 lỗi.

**Phát lại cùng bản ghi, cùng quy tắc** (bench `--replay`, AI thật trên GPU):

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
  vậy phần đầu bản ghi trôi qua không được chấm (o04). Chỉ làm nóng lô 4 ảnh thì còn một lần đứng 1,27 s ở bộ thiếu
  camera đầu tiên (o05).
  - **Sửa:** `AIWorker` chạy một lô ảnh đen cho mỗi cỡ lô trước khi báo sẵn sàng, ở cả phiên thật lẫn phát lại.
  - Test: `test_replay_starts_after_the_ai_warm_up_batch_so_the_first_frames_reach_a_set`. Bỏ làm nóng thì test này hỏng:
    14 lô thay vì 27.
- **Sau sửa (o06), phát lại cho đúng số bộ và đúng phân bố độ lệch như phiên thật.** Độ lệch bộ trùng tới 0,1 ms ở trung
  vị, p95 và max. Còn khác: một bộ thiếu cổng 3 ở giây đầu, khi chưa đo được nhịp camera; lô AI chậm nhất 19,7 ms so với
  18,4 ms. Kết quả AI **không** trùng từng bit vì ảnh JPEG đã mã hóa lại (mục 5).
- **Chưa thử:**
  - bản ghi có camera bị cắt/xé khung thật, nên chưa so được hai quy tắc chờ trên cùng dữ liệu có camera lỡ nhịp;
  - giao diện `--replay` với bản ghi thật (mới chạy với nguồn giả);
  - phát lại ở speed ≠ 1 trên bản ghi thật.

## 8. Việc tiếp theo

- Ghi một phiên có camera lỡ nhịp thật (khung bị cắt/xé, thường thấy ở 720p khi camera nhìn cảnh sáng, nhiều chi tiết).
  Sau đó chạy cùng bản ghi với `--max-wait-ms 60` và `--max-wait-ms 0`. Đây là phép so hai quy tắc trên cùng dữ liệu
  thật.
- Ghi một phiên nhìn sa bàn thật để biết MB/s ở cảnh có chi tiết.
- Làm lại trên laptop RTX 3050 Ti (máy nộp đồ án): luồng ghi có theo kịp không, đĩa của laptop có đủ chỗ không, làm nóng
  AI mất bao lâu.
- Khi có người ở bàn: ghi bằng ngăn "Ghi cảm biến" (T3) khoảng 60 s nhìn sa bàn, với bốn camera và C1 thật. Đo MB/s, số
  khung bị bỏ, `ecoqos_start`/`ecoqos_stop` và ảnh hưởng lên vòng điều khiển 50 Hz (cửa sổ thường và thu nhỏ). Tới khi đó
  T3 vẫn chưa thử với thiết bị thật.

## 9. Ghi trong phiên đỗ xe (T3, thêm 02/10/2026)

Ngăn **"Ghi cảm biến"** của `ui.lidar_app` (thẻ cạnh ngăn LiDAR) ghi mọi khung tốt của các camera ở ngăn AI camera và mọi
vòng quét của ngăn LiDAR vào **một** thư mục. Bản ghi dùng cùng đồng hồ `perf_counter` với log `VehicleIO` (T13) và dấu
đồng bộ (T14). Ngăn không gửi gì tới bo, không yêu cầu dừng xe, không chặn Bắt đầu đỗ và không mở thiết bị nào: nó chỉ
gắn vào nguồn mà hai ngăn kia đã mở. Mã: [`autopark/rig/session_recording.py`](../autopark/rig/session_recording.py)
(không Qt), [`autopark/ui/record_dock.py`](../autopark/ui/record_dock.py).

**Mức bằng chứng:** chỉ kiểm offscreen với camera giả, LiDAR giả và bản ghi phát lại; chưa thử với camera, LiDAR và màn
hình thật. Test: `tests/test_session_recording.py` (18 hàm), `tests/test_record_dock_ui.py` (9),
`tests/test_session_replay_ui.py` (3), cùng các test sửa sau review trong `tests/test_bench_window_feed_and_close.py`.
Các mặc định dưới đây là mặc định an toàn của thiết kế; ngày 02/10/2026 người dùng đồng ý làm theo đề xuất này. Ngưỡng
đĩa vẫn là đề xuất, chưa chốt.

```powershell
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app --camera-ai --cam-ports 1 2 3 4 --record-root runs/session_recordings --record-format jpg --jpeg-quality 95 --record-min-free-gb 5
```

**Trình tự** ([KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 2.4):

1. bật AI camera, kết nối LiDAR;
2. điền **Tên** (mã lần chạy, ví dụ `do1_l3`);
3. **Bắt đầu ghi**, rồi F8 (dấu đầu);
4. Tìm đường đỗ, Bắt đầu đỗ;
5. xe dừng, rồi F8 (dấu cuối);
6. **Dừng ghi**, chờ dòng trạng thái "XONG";
7. "Xuất log CSV…".

**Khóa và đóng cửa sổ:**

- "Bắt đầu ghi" bị khóa trong ba trường hợp:
  - xe đang chạy (RUNNING/STOPPING): luồng giao diện là vòng điều khiển 50 Hz, mà bắt đầu ghi phải ghi `meta.json` trên
    luồng đó;
  - chưa có nguồn nào ("Bật AI camera hoặc kết nối LiDAR trước");
  - bản ghi trước còn ghi nốt.
- "Dừng ghi" luôn dùng được và không chặn; luồng ghi ghi nốt rồi báo "XONG". Cài đặt bị khóa khi đang ghi.
- Huy hiệu đỏ "● ĐANG GHI" ở thanh trên, cạnh nút dấu đồng bộ, chỉ hiện khi đang ghi.
- Đóng cửa sổ: dừng ghi (không chờ), rồi dừng xe (enable=0 + DISARM qua liên kết VehicleIO, tắt bo ảo QEMU), rồi tắt các
  ngăn và chờ ghi nốt tối đa 60 s (quá thì in cảnh báo ra stderr). Thứ tự này sửa ngày 02/10/2026 sau review gộp đợt 2;
  trước đó lệnh dừng + DISARM đi sau lần chờ ghi nốt, trong lúc vòng 50 Hz đứng.

**Nguồn:**

- Camera: bộ ghi gắn **ngoài** vào `Rig` của ngăn AI camera (`Rig.attach_recorder`). Rig chỉ đưa khung vào, không bao
  giờ dừng hay chờ nó; `Rig.stop_recording()`/`Rig.stop()` chỉ gỡ nó.
- LiDAR: luồng đọc của ngăn bọc nguồn bằng `LidarTap`. Vòng quét chỉ vào bản ghi khi nguồn mở với `RIG_CLOCK` và có `t0`,
  và chỉ từ luồng đọc hiện hành. Driver C1 và phát lại `.npz` ×1 của ngăn nay mở như vậy, thay cho `time.monotonic`.
  Nguồn khác bị loại, lý do hiện ở chú thích ô chọn.
- Nguồn tắt/bật giữa chừng:
  - tắt AI camera → camera rời bản ghi (mốc `camera_detached`), LiDAR vẫn ghi;
  - LiDAR ngắt rồi kết nối lại → vòng quét tiếp tục vào cùng bản ghi (`lidar_detached`, `lidar_attached`);
  - nguồn bật sau khi bắt đầu ghi (kể cả Rig camera bật lại) không được thêm (báo một lần);
  - không còn nguồn nào → tự dừng (`no_sources`).

**Đĩa và lỗi ghi:**

- Không bắt đầu khi ổ còn < 5 GB (`--record-min-free-gb`, phải > 2); tự dừng khi < 2 GB (`disk_guard`).
- Cảnh báo một lần khi chỉ còn < 10 phút ghi theo MB/s hiện tại. GB ở đây là 2^30 byte, như Windows Explorer.
- Không đọc được dung lượng trống thì vẫn ghi, kèm cảnh báo.
- Lỗi ghi → tự dừng, dòng đỏ "LỖI GHI: …". Hàng đợi đầy → khung bị bỏ và đếm, dòng vàng "GHI THIẾU".
- Có lỗi ghi thì không có dòng GHI THIẾU, vì bộ ghi đếm chung khung bỏ vì hàng đợi đầy và khung bỏ sau lỗi ghi. Số khung
  bị bỏ nằm cuối dòng LỖI GHI ("· N khung bị bỏ"). Cách báo này sửa ngày 02/10/2026 sau review gộp đợt 2.
- Thư mục gốc nằm trong kho git mà ngoài `autopark/runs/` → cảnh báo "ảnh camera có thể lọt vào git".

**Ghi lại từ nguồn phát lại** (`--cam-replay`, `--recording`) được phép nhưng có nhãn vàng "GHI LẠI TỪ BẢN GHI PHÁT LẠI"
(rig tổng hợp: "RIG TỔNG HỢP"). LiDAR của `--session-replay` không ghi được, vì chưa có `t0` lúc gắn.

**Thư mục** là `<gốc>/<yyyymmdd_hhmmss_mmm>[_<tên>]/`. Gốc mặc định là `runs/session_recordings` (git bỏ qua); đổi khi đã
chốt chỗ lưu dữ liệu nghiệm thu (KICH_BAN_NGHIEM_THU.md mục 2.3). Định dạng vẫn là `autopark.rig_recording` v1 (mục 3):
`cam_p<cổng>/` của các camera của Rig lúc bắt đầu ghi, `lidar/` của ngăn LiDAR, và thêm:

| Tệp | Nội dung |
|---|---|
| `session/clock.csv` | mốc ghép `perf_counter` với giờ thật, thời gian phiên và đồng hồ `VehicleIO`; các cột ở dưới bảng |
| `session/ai_batches.csv` | khi ghi camera và bật "Kết quả AI theo lô": một dòng cho mỗi lô AI ngăn AI camera đã xét; các cột ở dưới bảng |
| `session/sync_marks.csv` | bản sao dấu đồng bộ của cửa sổ lúc dừng ghi, cột `SYNC_FIELDS`, ghi trước `meta.json` cuối |

- **`session/clock.csv`**, các cột:
  - `t_perf` (9 chữ số), `t_wall`;
  - `trigger` ∈ `start`, `periodic` (mỗi 1 s), `state_change`, `window_state` (cửa sổ thu nhỏ/hiện lại),
    `camera_detached`, `lidar_detached`, `lidar_attached`, `disk_warning`, `disk_guard`, `stop`;
  - `state`; `run` (số lần vào RUNNING kể từ lúc bắt đầu ghi); `t_session` (mỗi khi phiên có `world`);
  - `t_io`, `io_clock`, `time_scale` (như dòng dấu đồng bộ T14);
  - `window` (`normal`/`minimized`/`hidden`); `note` (nhánh chạy/cổng + bước chuyển và lý do dừng).

  Lỗi ghi không có mốc: sau lỗi ghi bộ ghi không ghi thêm dòng nào; lỗi nằm ở `meta.json`.
- **`session/ai_batches.csv`** được ghi SAU mọi quyết định an toàn của lô. Các cột:
  `t_perf, batch_id, t_done, anchor_t, skew_ms, frames, lagging, deferred, carried, checkpoint, usable, reasons, notes, cameras_used, occupied_batch, occupied_filtered, window_fill, bev_ms, ai_boxes, injected, state`.
  - `frames` = `cổng:t_s;…`, cùng định dạng `%.9f` với `t_s` của `frames.csv`, nên nối được bằng stamp.
  - Khe hở của `batch_id` là lô timer 50 ms của ngăn không kịp xét (`ai.batches_skipped` trong meta).
  - Không có bản đồ xác suất (phát lại chạy lại AI).
- **`session/sync_marks.csv`** chứa mọi dòng SYNC_MARK và CLOCK từ lúc mở cửa sổ. Bản ghi không bao giờ thêm dòng vào
  nhật ký dấu đồng bộ của cửa sổ, vì `score_run` tách lần chạy ở mỗi dòng CLOCK có state RUNNING.

**`meta.json`:**

- Như mục 3: khối camera lấy từ `Rig.recording_meta()`; không ghi camera thì `config`/`policy` null và `cameras` rỗng.
  `lidar_source` là nguồn của ngăn LiDAR (`port`, `kind` live/replay/other, `recording`, `describe`, `clock` =
  `perf_counter`). Có thêm `cameras_at_stop` và `lidar_at_stop`.
- Khóa `session_recording` lúc bắt đầu:
  - `version` 1, `app`, `name`, `clock`;
  - `sources`: camera/LiDAR có ghi không, loại nguồn, cổng, lý do không ghi;
  - `session`: kịch bản, tệp xe, nhánh chạy, bo (`sim` là bo mô phỏng, `qemu` là bo ảo QEMU, hoặc tên cổng COM), giới
    hạn đổi chiều có hiệu lực `cusp_policy`, và trạng thái lúc bắt đầu;
  - `cusp_policy` = `Session.cusp_limit().to_dict()`: `source`, `max_cusps`, `warn_cusps`, `cli_max_cusps`; tệp sa bàn
    gắn nghiệm thu thêm `acceptance`, `key`, `rule_max_cusps`, `thresholds` (đường dẫn, sha256, trạng thái). Trước bản
    sửa ngày 02/10/2026 (sau review gộp đợt 2), bo ảo QEMU ghi `sim` và `cusp_policy` chỉ chép cờ dòng lệnh;
  - `camera_ai` (cấu hình ngăn AI camera), `lidar_dock` (cấu hình ngăn LiDAR), `sync_marks_live_file`, `ecoqos_start`,
    `window_start`;
  - `disk`: gốc, GB trống lúc bắt đầu, hai ngưỡng;
  - `align`: quy tắc đổi đồng hồ ở dưới.
- `session_recording` thêm lúc dừng:
  - `stopped_by` (`user`, `disk_guard`, `write_error`, `no_sources`, `window_closed`), `stopped_wall`, `ecoqos_stop`,
    `free_gb_stop`;
  - `detached`, `ignored_late`, `runs`, `ai` (`rows`, `batches_skipped`), `sync_rows`, `warnings`, `hook_errors`;
  - mỗi mục của `runs` là một lần chạy trong lúc ghi: `t_perf_start`, `t_perf_end` (null nếu dừng ghi giữa lần chạy),
    `t_session_end`, `end_state`, `stop_reason`.

**Đổi đồng hồ.** Mọi `t_s` và mọi `t_perf` của `session/*.csv` là `perf_counter` của máy ghi. Chúng chỉ so được trong
cùng máy và cùng lần khởi động; `created_utc` ứng với `t_start_s`. Stamp là lúc dữ liệu tới máy, không phải lúc phơi
sáng.

- (a) `VehicleIO` thời gian thực: `t_io = t_perf − (t_perf − t_io)`, hiệu lấy từ bất kỳ mốc nào của liên kết đó hay từ
  khóa `clock` của `link.json`.
- (b) SIM hay bo mô phỏng: `t_session` nội suy giữa hai mốc của cùng lần chạy ở hai phía (cách ≤ 1 s, thêm một mốc mỗi
  lần đổi trạng thái). Sai số ≤ một nhịp giao diện (≈ 16 ms, tới 100 ms khi khựng) × `time_scale`. Không cộng
  `t_session` vào giờ START.
- (c) Video R1/R3: qua dòng SYNC_MARK của `session/sync_marks.csv`.
- (d) Dấu T13/T14 so thẳng.
- Trong mã: `read_session_clock(thư_mục)` → `SessionClock` với `realtime_offset()`, `to_io(t_perf)` và
  `to_session(t_perf)`; `to_session` trả None ngoài lần chạy.

**Xuất log.** "Xuất log CSV…"/"Lưu phiên…" (vẫn khóa khi xe chạy) ghi thêm `<tên>_sensor_recordings.json` cạnh tệp CSV,
và `sensor_recordings.json` trong gói phát lại nếu có gói.

- Mỗi bản ghi của cửa sổ là một mục: `folder`, `status`, `t_start_s`, `t_stop_s`, `overlap_s` và `covers_run` so với lần
  chạy gần nhất, số khung, số vòng LiDAR, `meta_sha256` (khi đã xong).
- Bản ghi KHÔNG được chép vào gói T9 (phát lại lần chạy qua `VehicleIO`).
- Xuất lúc còn đang ghi vẫn được: `status` là `đang ghi`, không có SHA.
- Với nguồn tư thế LiDAR thật, bản ghi này còn dùng để tái hiện từng vòng định vị của lần chạy
  (`lidar.pose_estimator --recording <thư mục> --same-scans-as localization.csv`,
  [NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md) mục 3). Muốn vậy thì bắt đầu ghi trước khi bấm Bắt đầu đỗ.

**Phát lại** (không mở thiết bị):

```powershell
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --replay runs/session_recordings/<thư mục> --name t3_phat_lai --out runs/rig_bench/phat_lai
.\.venv\Scripts\python.exe -X utf8 -m autopark.ui.rig_app --replay runs/session_recordings/<thư mục> --no-ai
.\.venv\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app --recording runs/session_recordings/<thư mục>
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app --camera-ai --session-replay runs/session_recordings/<thư mục>
```

`rig.bench --replay` và phát lại phiên đã kiểm bằng test với thư mục T3. `ui.rig_app --replay` (lệnh 2) và
`ui.lidar_app --camera-ai --cam-replay` chưa chạy với thư mục T3 nào; cùng định dạng, nhưng chưa thử.

Lệnh cuối (T3b) cho cả ngăn LiDAR lẫn ngăn AI camera MỘT `ReplaySession`, một đồng hồ phát lại, nên khung và vòng quét
giữ đúng độ lệch như lúc ghi:

- đồng hồ bắt đầu khi AI nạp xong; không có `--camera-ai` thì ngay khi gắn LiDAR;
- không dùng cùng `--recording`, `--cam-replay`, `--port`;
- luôn tự bật cả hai ngăn;
- phát lại một lần: tắt AI camera là dừng phát lại cho cả hai ngăn.

`--cam-replay <thư mục>` vẫn chỉ cấp ảnh, `--recording <thư mục>` chỉ cấp LiDAR, mỗi cái một đồng hồ riêng.

**Số đo offscreen** (02/10/2026, máy bàn đang có việc khác chạy; nguồn giả: bốn camera 640×480 ở 25 khung/s, LiDAR
10 Hz; script tạm, không lưu trong repo):

- nhịp 1 s của ngăn (kiểm + làm mới): trung vị 0,56 ms, lớn nhất 0,80 ms;
- một mốc đổi trạng thái: 0,05 ms;
- "Bắt đầu ghi": 33–40 ms;
- "Dừng ghi": 1,4–4,5 ms.

Với thiết bị và màn hình thật: chưa đo. MB/s của cảnh sa bàn: chưa đo.

**Giới hạn:**

- Chưa thử với thiết bị thật.
- Ảnh hưởng của việc ghi lên vòng điều khiển 50 Hz (cửa sổ thường và thu nhỏ): chưa đo.
- Cửa sổ thu nhỏ có thể bị EcoQoS (chế độ tiết kiệm của Windows 11) làm chậm ([CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md)
  mục 10). Từ 02/10/2026 ứng dụng tự tắt EcoQoS cho chính nó, trừ khi đặt `AUTOPARK_KEEP_ECOQOS=1`. Ghi khi cửa sổ thu
  nhỏ chưa đo, nên giữ cửa sổ phóng to khi đang ghi và chạy. Cột `window` và `ecoqos_start`/`ecoqos_stop` ghi lại điều
  kiện này.
- Ảnh camera có thể có người và phòng: giữ trong `runs/`, không commit.
- Rig camera bật lại giữa chừng không được gắn lại.
