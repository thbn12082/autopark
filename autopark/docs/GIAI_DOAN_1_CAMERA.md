# Giai đoạn 1 — nhánh camera: nhận bốn camera USB 130° (theo nhà bán, chưa đo) và hub UGREEN (23/09/2026)

Máy: máy bàn i9-14900, Windows 11, OpenCV 5.0.0 (`.venv`), **chưa phải laptop RTX 3050 Ti mang đi nộp đồ án**. Kế hoạch nói thử một camera
trước rồi mới nhân bốn; đồ về là bốn chiếc cùng lúc, nên bài thử đơn camera (mục 4.1) làm trước, rồi mới tới bốn
luồng (mục 4.2). Sơ đồ cổng và danh tính camera: [usb_topology.md](usb_topology.md). Mode camera công bố:
[camera_modes.csv](camera_modes.csv).

**Mọi con số trong tài liệu này đều có file** trong `runs/camera_bench/20260923/` (git-ignored; bản sao json/báo cáo
ở [evidence/camera/](evidence/camera/)): `mNN_*.measure.json` (phiên đo, kể cả danh sách khoảng cách từng khung),
`traps_cam0.traps.json`, `source_cam0_720p.source.json`, `r0N_*.json` + `.avi` + ảnh PNG, `report.md`,
`usb_topology.json`, `nNN_*_nofilm.measure.json` (sau khi lột phim bảo vệ, mục 4.4), `qNN_*_replug.measure.json` (sau khi rút/cắm lại camera, mục 4.5), `usb_topology_replug1/2.json`. Phiên chính thức chạy lại lúc 10:36–10:44 ngày 23/09 (giờ máy, UTC+7; `created_utc` 03:36:17Z ở `usb_topology.json` tới 03:44:07Z ở `r02_cam2_720p.json`) sau khi công cụ được sửa theo vòng kiểm tra đối kháng (mục 8); các lần thử tay trước đó (10:03–10:09, file đã bị ghi đè) không còn được trích dẫn.

## 1. Tiếp nhận thiết bị

| Mục | Giá trị | Nguồn |
|---|---|---|
| Camera | 4 × "HD Camera", VID 1BCF (Sunplus Innovation) PID 0B09, UVC composite (giao diện video MI_00), **không có serial** | `usb_topology.json` (Get-PnpDevice + DirectShow DevicePath) |
| Hub | UGREEN 4 cổng, chip Genesys Logic: "USB3.1 Hub" 05E3:0626 ở cổng gốc 24 và "USB2.1 Hub" 05E3:0610 ở cổng gốc 5; **cả bốn camera ở nhánh USB 2.0, cổng 1–4** | `usb_topology.json` khóa `hubs`, `pnp` |
| Mode camera công bố | MJPG 640×480 / 1280×720 / 1920×1080 đều 30 fps; YUY2 640×480 30 fps, 1280×720 **10** fps, 1920×1080 **5** fps | `camera_modes.csv` (media type DirectShow) |
| Nguồn hub | **bus-powered trong mọi phiên** ngày 23/09 (hub có cổng nguồn ngoài theo người dùng, chưa cắm); dòng camera **chưa đo** | người dùng |
| Góc nhìn 130°, nhãn/hộp, dòng tiêu thụ | **chưa ghi / chưa đo** | |

## 2. Đã viết gì

| Việc | Mã | Kiểm |
|---|---|---|
| Phiên đo camera: `list` (PnP + hub + DirectShow, ghép index ↔ cổng hub), `modes` (media type → csv), `measure` (1..N camera cùng lúc: FPS thật, khung cũ trả lại, đọc hỏng, khoảng cách khung — trung bình/trung vị/p95/max và từng khoảng, thời gian read(), độ sáng, CPU tiến trình; luồng lỗi được ghi vào kết quả và mã thoát ≠ 0), `record` (AVI MJPG + ảnh tĩnh + thời điểm từng khung), `traps` (hồ sơ ba bẫy mục 3), `source` (chạy `UsbCameraSource` trên camera thật), `report` | `video/camera_bench.py` | 13 test không cần phần cứng (`tests/test_camera_bench.py`) |
| Sửa nguồn camera trực tiếp theo mục 3; thêm `exposure`; `mode()` ghi kích thước thực và fourcc đọc lại, fps chỉ là yêu cầu | `video/sources.py::UsbCameraSource` | test giả lập VideoCapture; chạy trên camera thật (`source_cam0_720p.source.json`); bộ mô phỏng 300 đạt / 4 bỏ qua |
| `pygrabber` (DirectShow qua comtypes, chỉ Windows) vào extra `video` và lock; ngoại lệ `.gitignore` cho `docs/camera_modes.csv` | `pyproject.toml`, `requirements-phase0.lock`, `.gitignore` | |

## 3. Ba cái bẫy của OpenCV 5 + DirectShow, có hồ sơ (`traps_cam0.traps.json`, camera index 0, 3 s mỗi phép)

1. **Mode phải đưa vào ngay lúc mở.** Đặt kích thước/`CAP_PROP_FOURCC` *sau* khi mở: 720p còn **9,5 fps**, 1080p còn
   **4,2 fps**, fourcc đọc lại YUY2 — đúng hai mode YUY2 10/5 fps camera công bố. Đưa cùng các tham số vào
   `cv2.VideoCapture(index, CAP_DSHOW, [CAP_PROP_FOURCC, …])`: 720p và 1080p đều **23,8 fps**, fourcc đọc lại MJPG.
   Tham số trong danh sách phải là số nguyên; số thực làm `VideoCapture` ném lỗi.
2. **`grab()` không chờ khung mới.** Ở mode mặc định 640×480, `grab()` trả về **3.778.017 lần/giây**; đếm FPS bằng
   `grab()` vô nghĩa và nguồn dùng `grab()+retrieve()` sẽ thấy toàn khung trùng. `read()` thì chặn tới khung kế
   (m01: thời gian `read()` trung vị 46 ms).
3. **Readback: fourcc tin được, fps thì không.** `CAP_PROP_FOURCC` đọc lại phản ánh định dạng đã thương lượng (YUY2 khi
   rơi về, MJPG khi đưa vào lúc mở) nên dùng được để phát hiện rơi về YUY2; `CAP_PROP_FPS` trả về −1 hoặc đúng số
   vừa đặt, FPS thật phải đo. Backend MSMF của bản OpenCV này **không mở được** camera (`msmf_opened = false`).
   `CAP_PROP_BUFFERSIZE` DirectShow không nhận (`buffer_size_applied = false` trong `source_cam0_720p.source.json`).

`UsbCameraSource` chạy trên camera 0 ở 720p MJPG (`source_cam0_720p.source.json`): 120 khung, 0 lỗi đọc, stamp tăng
nghiêm ngặt, khoảng cách stamp trung bình 42,0 ms, trung vị 47,0 ms, max 63,0 ms; `mode_mismatch` rỗng.

## 4. Số đo trên bàn

Báo cáo gộp: [evidence/camera/report_20260923.md](evidence/camera/report_20260923.md) (bản sao nguyên văn `report.md`
do công cụ sinh lúc 12:23 ngày 23/09, trước khi có bộ dò khung MJPEG bị cắt cụt. *Ghi chú 24/09/2026:* báo cáo không
kiểm khung bị cắt, nên cột "FPS thật" đếm mọi khung mới dù có bị cắt hay không, "Đọc hỏng" chỉ đếm `read()` thất bại, và
các dòng q* 0 khung cũ ở 720p/1080p không có nghĩa là bốn camera dùng được ở các mode đó — xem đính chính mục 4.6).
Mọi phiên MJPG, yêu cầu 30 fps,
phơi sáng tự động trừ khi ghi khác. "Khung cũ" = số lần `read()` trả về đúng khung trước (driver không có khung mới).
Ánh sáng: phòng làm việc buổi sáng, đèn trần, camera nằm trên bàn (chưa gá). **Các phiên m01–m13, r01, r02 đo khi ống kính còn lớp phim bảo vệ**; mục 4.4 là phiên chạy lại sau khi lột. CPU = lõi CPU của tiến trình đo, gồm
giải mã MJPG và phép so khung trùng của bench.

### 4.1. Một camera

| Phiên | Mode | FPS thật | Khung cũ | Khoảng cách khung trung bình / trung vị / p95 / max (ms) | Độ sáng TB (0–255) | CPU |
|---|---|---:|---:|---|---:|---:|
| m01, 30 s | 720p | 23,9 (716 khung) | 0 | 41,9 / 47,1 / 51 / 55 | 91 | 0,16 lõi |
| m02, 20 s | 720p, **phơi sáng thủ công −6** (≈ 1/64 s) | **29,3** | 0 | 34,2 / 32,1 / 49 / 52 | **3** (ảnh gần đen) | 0,18 lõi |
| m11, 10 s × 3 | 720p, phơi sáng −5 / −7 / −8 | 29,3 / 29,3 / 29,3 | 0 | trung vị 32 ở cả ba | 13 / 2 / 2 | 0,15–0,17 lõi |
| m03, 20 s | 1080p | 23,8 | 0 | 41,9 / 47 / 51 / 55 | 91 | 0,34 lõi |
| m08, 20 s | 720p, camera cổng 4 (index 2) | 23,8 | 0 | 41,9 / 47 / 50 / 53 | 98 | 0,15 lõi |
| m13, 20 s | 1080p, camera cổng 4 (index 2) | 23,8 | 0 | 41,9 / 47 / 50 / 53 | 94 | 0,33 lõi |

- **Phơi sáng tự động: 23,85 fps, nhịp khung không đều nhưng có cấu trúc.** m01: 716 khung trong 30,0 s, khoảng cách trung bình 41,9 ms nhưng trung vị 47,1 ms; 272/716 khoảng (38 %) ngắn hơn 40 ms. Phân bố (`gaps_ms` trong json, bin 8 ms): 24–32 ms: 170; 32–40: 102; 40–48: 182; 48–56: 262. Ở bin 1 ms hai đỉnh nằm ở ≈ 31 ms (31 ms: 80; chỉ 45/716 khoảng ngắn hơn 30 ms; nhóm ngắn trung bình 31,4 ms) và ≈ 48 ms (48 ms: 129; nhóm dài trung bình 48,3 ms), tỉ lệ ≈ 2:3 — không phải "mỗi khung 47 ms". Chuỗi khoảng cách không ngẫu nhiên (ngưỡng 40 ms): chuyển tiếp ngắn→dài 272, dài→ngắn 271, dài→dài 172, ngắn→ngắn 0 — một khoảng ngắn luôn được nối bằng một khoảng dài. Cùng dạng ở m03, m04, m05, m08 (trung bình 41,9–42,1 ms, 62–62 % khoảng ≥ 40 ms, ngắn→ngắn = 0 ở mọi luồng đã xem).
- **Phơi sáng thủ công ≤ −5: 29,3 fps, nhịp gần đều** (trung vị 32 ms, m02/m11) nhưng vẫn còn khoảng ≈ 48 ms rải rác: m02 79/586 khoảng (13,5 %) ≥ 40 ms, trung bình 48,4 ms; m11 −5/−7/−8: 39 / 39 / 39 trên 293 / 294 / 293 khoảng; không có hai khoảng dài liền nhau; 587 khung/20 s so với 600 nếu 30 fps đều. Ảnh tối (độ sáng 13 ở −5, 2–3 từ −6 trở xuống; không chỉnh gain). Khoảng ≈ 48 ms có ở cả hai chế độ; chế độ tự động không sinh ra nó mà làm nó chiếm ≈ 62 % số khoảng thay vì ≈ 13 % — đó là nguyên nhân gần của 24 fps. **Cơ chế chưa xác định**: thời gian phơi sáng dài hơn 33 ms hay chính sách tốc độ khung riêng của chế độ tự động; mọi giải thích phải tạo ra hai độ dài rời rạc ≈ 31 / ≈ 48 ms và không cho hai khoảng ngắn liền nhau. Chưa có phiên nào đổi ánh sáng hay đặt exposure thủ công kèm `CAP_PROP_GAIN`; readback exposure ở chế độ tự động (−6) không tin được. Câu "đủ ánh sáng trên sa bàn thì 30 fps" vì thế là giả thuyết chưa thử. Thiết kế tạm lấy **24 fps, nhịp không đều** làm số vận hành và phải đo lại dưới đèn của sa bàn. *(Cập nhật tối 24/09/2026: ở các phiên bốn camera sau đó, **một** camera đôi khi chạy ≈ 29 fps dù vẫn phơi sáng tự động (`exposure: null` trong `.rig.json`), và không cố định một cổng: cổng 3 ở s01–s07 và t01/t02 ngày 23/09 (28,9–29,3 fps, số khung gồm cả khung bị cắt), cổng 1 ở t05 (23/09), m02 (15:25 ngày 24/09) và o01 (tối 24/09, 29,27 fps). Nguyên nhân chưa rõ. Vì vậy quy tắc chờ camera chậm xét mỗi camera theo nhịp của chính nó, không giả định bốn camera cùng 24 fps: [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 10.1–10.3.)*
- Độ trễ đầu-cuối (từ sự kiện thật tới khung về tới Python), thời gian suy luận, tải GPU, nhiệt: **chưa đo** (bước 3
  "Khi nhận một camera" yêu cầu; cần LED nháy hoặc đồng hồ trên màn hình, và phiên chạy AI). *Cập nhật 24/09/2026:*
  thời gian suy luận, độ trễ trong máy, tải GPU và nhiệt GPU đã đo chiều 23/09 ở phiên bốn camera 640×480 + LiDAR + AI
  trên máy bàn ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 3.3–3.4), không phải ở phiên một camera này; độ trễ
  từ sự kiện thật và nhiệt CPU vẫn chưa đo.

### 4.2. Bốn camera cùng lúc, mỗi camera một luồng (chỉ số camera là index OpenCV; index 2 = cổng 4 của hub)

| Phiên | Mode | FPS thật index 0 / 1 / 2 / 3 | Khung cũ (max khoảng cách) | Tổng khung/s | CPU |
|---|---|---|---|---:|---:|
| m04, 30 s | 640×480 | 23,9 / 23,9 / 23,9 / 23,9 | 0 / 0 / 0 / 0 | 95,4 | 0,26 lõi |
| m05, 60 s | 1280×720 | 23,8 / 23,8 / 23,8 / 23,8 | 0 / 0 / **4** (96 ms) / 0 | 95,3 | 0,62 lõi |
| m12a, 10 s | 1280×720 | 23,8 / 23,8 / **18,6** / 23,9 | 0 / 0 / **52** (97 ms) / 0 | 90,2 | 0,60 lõi |
| m12b, 10 s | 1280×720 | 23,9 / 23,9 / **22,3** / 23,9 | 0 / 0 / **15** (97 ms) / 0 | 93,9 | 0,61 lõi |
| m12c, 10 s | 1280×720 | 23,9 / 23,8 / **3,9** / 23,9 | 0 / 0 / **200** (1.008 ms) / 0 | 75,4 | 0,52 lõi |
| m06, 30 s, mở 0-1-2-3 | 1920×1080 | 23,8 / 23,8 / **22,5** / 23,8 | 0 / 0 / **40** (129 ms) / 0 | 94,0 | 1,37 lõi |
| m09, 20 s, mở 2-0-1-3 | 1920×1080 | 23,9 / **22,3** / **13,1** / 23,8 | 0 / 31 (96) / **214** (304 ms) / 0 | 83,1 | 1,24 lõi |
| m10, 20 s, mở 3-2-1-0 | 1920×1080 | 23,8 / **22,7** / **18,7** / 23,8 | 0 / 23 (97) / **102** (176 ms) / 0 | 89,1 | 1,31 lõi |
| m07, 30 s, chỉ 0, 1, 3 | 1920×1080 | 23,9 / **20,0** / — / 23,8 | 0 / **116** (101 ms) / — / 0 | 67,7 | 0,98 lõi |

- **Camera ở cổng 4 của hub (index 2) rớt khung khi chạy chung từ 720p trở lên**: ở cả ba thứ tự mở 1080p đã ghi (m06, m09, m10) và ở 720p (m05, m12a–c); ở 640×480 (m04, 30 s) **không rớt** (0 khung cũ, khoảng cách max 51,4 ms). Mức rớt dao động mạnh giữa các lần: 4 khung cũ trong 60 s (m05) tới 200 khung cũ trong 10 s với khoảng cách 1 s (m12c); quy về mỗi giây, 720p (0,07–20 khung cũ/s) và 1080p (1,3–10,7 khung cũ/s) chồng lấn nhau, nên chỉ nói được "480p không rớt, từ 720p có rớt", chưa nói được rớt tăng đều theo độ phân giải. Một mình nó chạy đủ 23,8 fps ở cả 720p lẫn 1080p (m08, m13), nên không hỏng khi chạy đơn. **Nguyên nhân khi có tranh chấp chưa xác định.** Sau khi rút/cắm lại các camera (mục 4.5), 0 khung cũ trong 7 phiên cùng cấu hình — nhưng chưa biết rút/cắm đã đổi gì. Giả thuyết: thiếu nguồn của hub bus-powered (chưa thử nguồn ngoài); chia băng thông trên nhánh USB 2.0 chung (cả bốn camera qua cổng gốc 5; việc 480p không rớt hợp với cả hai giả thuyết); chiếc camera/dây này yếu hơn khi tranh chấp; đường nội bộ cổng 4 của hub; thứ tự SetInterface lúc mở — riêng thứ tự mở không làm hết rớt, kể cả khi cổng 4 được mở đầu tiên (m09: 13,1 fps, 214 khung cũ), nhưng mỗi thứ tự chỉ có một phiên trong khi cùng một thứ tự đã cho 15–200 khung cũ (m12b/c), nên chưa xếp hạng được các thứ tự. Phép thử nguồn ngoài và đổi chỗ cắm (mục 6, việc 1) sẽ giúp phân biệt; chưa làm.
- **720p × 4 chưa đủ bằng chứng để nói ổn định.** Phiên 60 s chỉ rớt 4 khung, nhưng ba phiên 10 s liền sau đó cho
  18,6 / 22,3 / 3,9 fps ở camera cổng 4. Ba camera còn lại không rớt khung nào trong mọi phiên 720p.
- **1080p với ba hoặc bốn camera không đạt (trước khi rút/cắm lại)**: cổng 4 rớt ở cả ba phiên bốn camera 1080p (m06, m09, m10); cổng 3 (index 1) cũng rớt (22,3–22,7
  fps) ở hai thứ tự mở và rớt nặng (20,0 fps, 116 khung cũ) khi chỉ chạy ba camera (m07). Trước khi rút/cắm lại, 1080p
  chỉ chắc chắn cho một camera (m03, m13); **hai camera 1080p chưa thử**. Sau khi rút/cắm lại các camera, bốn camera 1080p chạy sạch hai phiên (mục 4.5) — nguyên nhân chưa rõ.
- **Băng thông USB thật chưa đo.** Cỡ khung trong AVI (r01: 45,6 MB / 478 khung ≈ 95 KB; r02: 23,7 MB / 239 khung
  ≈ 99 KB) là JPEG do OpenCV **mã hóa lại** từ ảnh BGR đã giải mã, không phải số byte camera đẩy qua USB. Payload thật
  và băng thông đẳng thời mỗi camera đặt trước theo alt-setting của mode cần `CAP_PROP_CONVERT_RGB=0`, USB Device
  Tree Viewer hoặc USBPcap — chưa làm. Vì thế chưa có cơ sở số để nói nguyên nhân rớt khung.
- CPU tiến trình: 0,16 lõi (một camera 720p), 0,34 (một camera 1080p), 0,26 (4 × 480p), 0,52–0,62 (4 × 720p),
  1,24–1,37 (4 × 1080p) trên i9-14900; laptop RTX 3050 Ti (máy nộp đồ án) chưa đo (*Cập nhật 24/09/2026, người dùng xác nhận:* máy bàn i9-14900 + RTX 4000 Ada là máy phát triển chính; laptop i7-12700H + RTX 3050 Ti (4 GB VRAM) là máy mang đi nộp và trình diễn đồ án. Mọi số đo đến nay là trên máy bàn; số dùng cho khóa luận phải đo lại trên laptop.)
- ~~Chưa làm ở giai đoạn 2: chạy bốn camera đồng thời với LiDAR và AI (bước 2), kiểm nhận dạng sau rút/cắm và khởi động
  lại (bước 3), đồng bộ phần mềm và ghi sai lệch thời gian giữa bốn luồng (bước 5)~~; `record` đã ghi thời điểm từng
  khung (`*.frames.csv`) để phục vụ bước 5 sau này. **Cập nhật 24/09/2026:** câu gạch ở trên viết sáng 23/09 và đã cũ.
  - **Bước 2 và 5:** chiều 23/09, trên máy bàn (chưa phải laptop RTX 3050 Ti mang đi nộp đồ án), camera chưa gá, bốn camera 640×480 đã chạy
    đồng thời với LiDAR và AI (phiên u01 120 s, u04 600 s). Sai lệch thời gian trong bộ ảnh và giữa LiDAR với bộ ảnh đã
    được ghi lại (bước 5). Chi tiết ở [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 3–4.
  - **Bước 3:** nhận dạng sau rút/cắm cùng cổng (một lần có hồ sơ, mục 4.5) và sau khởi động lại máy (mục 5,
    [usb_topology.md](usb_topology.md)) đã kiểm. Đổi cổng, nguồn hub và gán camera vào hướng thì chưa làm.
  - **Chưa đo:** độ trễ từ sự kiện thật tới lúc khung về máy (phần còn thiếu của bước 2), độ lệch lúc phơi sáng (stamp
    hiện là lúc khung tới máy), và mọi số trên laptop RTX 3050 Ti (máy nộp đồ án).

### 4.3. Ảnh mẫu

Hai ảnh thu nhỏ trong [evidence/camera/](evidence/camera/) (bản gốc PNG 720p trong thư mục run; r01 20 s và r02 10 s,
478 và 239 khung, 23,87 fps, 0 khung cũ). Ảnh chụp mặt bàn và ghế ở cự ly gần, không có bia thử, **còn lớp phim bảo vệ** (r03 ở mục 4.4 đã lột): nhận xét bằng mắt là
ảnh tĩnh không kéo vệt, méo thùng rõ ở mép. **Chưa có ảnh ở độ cao và góc chúc dự kiến trên xe**, nên chưa nói được
"đủ nét trong vùng làm việc".

### 4.4. Sau khi lột lớp bảo vệ ống kính (phiên n01–n06, r03; `created_utc` 04:02:58Z–04:04:31Z)

**Mọi phiên m01–m13 và r01/r02 ở trên được đo khi ống kính còn dán lớp phim bảo vệ** (người dùng phát hiện và lột
lúc ≈ 11:15). Chạy lại các phiên chính để xem điều đó đổi gì:

| Phiên (đã lột phim) | Mode | FPS thật | Khung cũ (max khoảng cách) | Tổng khung/s | Độ sáng TB | CPU |
|---|---|---|---|---:|---:|---:|
| n01, 30 s, một camera | 720p | 23,9 | 0 | — | 97 (m01 còn phim: 91) | 0,16 lõi |
| n02, 10 s, một camera, phơi sáng −6 | 720p | 29,3 | 0 | — | **15** (m02 còn phim: 3) | 0,18 lõi |
| n06, 20 s, bốn camera | 640×480 | 23,9 / 23,8 / 23,8 / 23,8 | 0 / 0 / 0 / 0 | 95,4 | 87–90 | 0,20 lõi |
| n03, 60 s, bốn camera | 1280×720 | 23,8 / 23,8 / 23,8 / 23,8 | 0 / 0 / 0 / 0 | 95,4 | 92–98 | 0,68 lõi |
| n04, 30 s, bốn camera | 1920×1080 | 23,8 / 23,9 / 19,0 / 23,9 | 0 / 0 / 147 (129 ms) / 0 | 90,5 | 89–95 | 1,40 lõi |
| n05, 20 s, ba camera 0, 1, 3 | 1920×1080 | 23,8 / 23,8 / 23,8 | 0 / 0 / 0 | 71,5 | 89–93 | 1,11 lõi |

- **Lớp phim làm tối ảnh rõ rệt**: ở cùng phơi sáng thủ công −6, độ sáng trung bình 3 → 15
  (≈ 5 lần). Ở chế độ tự động, camera tự bù nên độ sáng chỉ đổi 91 → 97.
- **Nhịp khung không đổi**: n01 23,9 fps, trung bình 41,9 ms, trung vị 47,8 ms,
  62 % khoảng ≥ 40 ms, ngắn→ngắn = 0 — y hệt m01. Vậy 24 fps của chế độ tự động **không phải do lớp phim làm
  tối**; các kết luận ở mục 4.1 giữ nguyên, ảnh mẫu r01/r02 (còn phim) thì phải xem là tối hơn thật.
- **Bốn camera 720p (n03, 60 s): không rớt khung nào**, kể cả cổng 4. Cùng với m05 (4 khung cũ/60 s) và m12a–c (18,6 / 22,3 / 3,9 fps
  trong 10 s), điều này khẳng định rớt ở 720p là **thất thường**, không đoán được từ một phiên; chưa có bằng chứng lớp phim liên quan.
- **1080p**: bốn camera vẫn rớt ở cổng 4 (n04: 19,0 fps, 147 khung cũ); ba camera lần này
  sạch (n05: 0 khung cũ, khác m07 có 116) — cũng thất thường.
- r03 (10 s, còn ảnh tĩnh `r03_cam0_720p_nofilm_*.png`): 240 khung, 23,99 fps, 0 khung cũ.

### 4.5. Rút/cắm lại camera — phép thử vô tình (phiên q*, `created_utc` 04:59:50Z–05:08:19Z, tức ≈ 11:59–12:08 giờ máy)

**Đính chính:** bản đầu của mục này (commit 849fc5b) gọi đây là phép thử nguồn ngoài cho hub và kết luận "thiếu nguồn là giả
thuyết được ủng hộ nhất". Sai tiền đề: người dùng **không** cắm adapter nguồn; lúc ≈ 11:45 họ **rút và cắm lại các camera**
(cùng cổng). Các file đã được đổi tên từ `p*_power` thành `q*_replug`, kết luận về nguồn rút lại. **Hub vẫn chạy bus-powered
trong mọi phiên của ngày 23/09; phép thử nguồn ngoài chưa làm.**

Điều thực sự đã xảy ra: (1) ≈ 11:55 người dùng rút/cắm lại các camera (*đính chính 24/09/2026:* bản trước, và câu
"lúc ≈ 11:45" ở đoạn trên, ghi ≈ 11:45; theo nhật ký phiên làm việc (ngoài repo), 11:53 người dùng còn đang hỏi về
nguồn hub và 11:57 báo đã cắm xong; lần rút/cắm lại camera cổng 3 ở bước (3) rơi vào khoảng 12:01–12:04); (2) sau đó camera **cổng 3** (index 1) từ chối mở
(`VideoCapture.isOpened() = False`) dù Windows báo OK và DirectShow vẫn liệt kê đủ bốn, ba chiếc kia mở bình thường — bảy lệnh
đo bốn camera đầu tiên thất bại vì thế; không có quyền admin để khởi động lại thiết bị bằng phần mềm; (3) ≈ 12:00 người dùng rút/cắm
lại camera cổng 3 lần nữa, cả bốn mở được; (4) chạy lại đúng các cấu hình từng rớt khung:

| Cấu hình | TRƯỚC khi rút/cắm (m*, n*) | SAU khi rút/cắm (q*) |
|---|---|---|
| 4 × 720p, 10 s × 3 | m12a: 52 khung cũ (cam2 18,6 fps, max 97 ms); m12b: 15 khung cũ (cam2 22,3 fps, max 97 ms); m12c: 200 khung cũ (cam2 3,9 fps, max 1008 ms) | q12a: 0 khung cũ; q12b: 0 khung cũ; q12c: 0 khung cũ |
| 4 × 720p, 60 s | m05: 4 khung cũ (cam2 23,8 fps, max 96 ms); n03: 0 khung cũ | q05: 0 khung cũ |
| 4 × 1080p, mở 0-1-2-3, 30 s | m06: 40 khung cũ (cam2 22,5 fps, max 129 ms); n04: 147 khung cũ (cam2 19,0 fps, max 129 ms) | q06: 0 khung cũ |
| 4 × 1080p, mở 2-0-1-3, 20 s | m09: 245 khung cũ (cam2 13,1 fps, max 304 ms) | q09: 0 khung cũ |
| 3 × 1080p (cổng 1, 3, 2), 20–30 s | m07: 116 khung cũ (cam1 20,0 fps, max 101 ms); n05: 0 khung cũ | q07: 0 khung cũ |

- **Sau khi rút/cắm lại: 0 khung cũ trong cả 7 phiên** (≈ 3 phút, kể cả bốn camera 1080p ở hai thứ tự mở), so với
  8/10 phiên cùng cấu hình rớt trước đó, tổng 819 khung cũ. Bốn camera 1080p chưa từng sạch trong
  bốn phiên trước (m06, n04, m09, m10), nay sạch cả hai phiên. Việc rút/cắm đã đổi *một thứ gì đó*, nhưng **chưa biết là gì**: đầu nối
  hay dây của camera cổng 4 được cắm chắc hơn; bộ điều khiển USB cấp phát lại băng thông đẳng thời theo thứ tự cắm mới; trạng thái
  bên trong camera được reset. Cũng chưa loại trừ trùng hợp, vì rớt ở 720p vốn thất thường (n03 từng sạch 60 s), dù ở 1080p thì 4/4
  phiên trước đều rớt. Chưa có bằng chứng nào về nguồn: hub chưa bao giờ được cấp nguồn ngoài.
- Ba biến số khác cũng đổi giữa hai lô: ánh sáng/khung cảnh (độ sáng trung bình lô q 35–65 so với ≈ 90 ở
  lô m/n); ba phiên q12a–c chạy ngay sau khi cắm lại (12:05) cho FPS 24,5–29,2 với nhiều khoảng ngắn liền
  nhau và độ sáng dao động 44–94, tức phơi sáng tự động chưa ổn định — số FPS của ba phiên
  đó không so được với m12a–c, chỉ số khung cũ (0) là so được; từ q05 trở đi nhịp khung trở lại đúng dạng 23,8 fps / 38 % khoảng ngắn.
- Sau rút/cắm, ba camera gồm cả cổng 4 (q08 1080p, q10 720p) và camera cổng 4 một mình (q13) đều 0 khung cũ; CPU bốn camera 1080p
  1,40 lõi. *(Ghi chú 24/09/2026: q08/q10/q13 ghi lúc 04:59:50Z–05:00:25Z (≈ 12:00), sớm hơn bảy phiên ở bảng
  (05:05:30Z–05:08:19Z) và sớm hơn `usb_topology_20260923_replug2.json` (05:04:59Z). Cả ba đều không mở index 1 (cổng 3):
  theo giờ ghi, và theo nhật ký phiên làm việc ngoài repo, chúng chạy lúc camera cổng 3 còn treo, trước lần cắm lại thứ
  hai. Vì vậy chúng chỉ nói về ba camera sau lần rút/cắm thứ nhất.)*
- **Bài học vận hành:** rút/cắm camera có thể để lại một camera ở trạng thái "PnP OK, DirectShow liệt kê, nhưng không mở được"; mã vận
  hành phải coi mở thất bại là trạng thái cần người can thiệp, và phiên thử trên xe phải bắt đầu bằng một lượt mở thử cả bốn camera.

**Hồ sơ rút/cắm (giai đoạn 2, bước 3):** hai bản `list`
[`usb_topology_20260923_replug2.json`](evidence/camera/usb_topology_20260923_replug2.json) (`created_utc` 05:04:59Z) và
[`usb_topology_20260923_replug1.json`](evidence/camera/usb_topology_20260923_replug1.json) (05:05:17Z) đều cho **cùng**
bảng index ↔ cổng ↔ InstanceId với bản 10:36 (0→1, 1→3, 2→4, 3→2): danh tính theo cổng và index DirectShow giữ nguyên
sau rút/cắm cùng cổng (≈ 11:55 các camera, ≈ 12:01–12:04 camera cổng 3). *Đính chính 24/09/2026:* bản trước ghi
`replug1` là lúc camera cổng 3 còn treo. Theo `created_utc`, cả hai bản đều ghi sau lần cắm lại cổng 3 (sau q13
05:00:25Z, ngay trước q12a 05:05:30Z mở đủ bốn camera), cách nhau 18 s, và `replug1` ghi sau `replug2` (tên không theo
thứ tự thời gian). Bản `list` chụp lúc camera cổng 3 còn treo (≈ 11:58) đã bị ghi đè cùng đường dẫn; bảng lúc đó chỉ còn
trong nhật ký console ngoài repo (cũng cùng bảng), không tính là bằng chứng lưu trữ. Vì vậy nhận dạng sau rút/cắm mới có
hồ sơ **một lần**, sau cả hai lần rút/cắm. Đổi cổng vẫn chưa thử; khởi động lại máy đã thử lúc 12:35 (mục 5).

**Phép thử nguồn ngoài (chưa làm):** rút cả bốn camera, cắm adapter nguồn cho hub, cắm lại camera, chạy lại bốn camera 1080p 30 s
và ba phiên 720p 10 s. Nếu muốn tách riêng tác dụng của việc rút/cắm, chạy trước một lượt rút/cắm không đổi gì khác.

### 4.6. Đính chính (23/09 chiều): "sạch" ở mục 4.2–4.5 chỉ có nghĩa là không có khung cũ

Mọi số FPS và chữ "sạch" ở mục 4.2–4.5 chỉ đếm **khung cũ** (driver trả lại đúng khung trước). Lúc đó công cụ chưa
kiểm được một kiểu hỏng khác: **khung MJPEG bị cắt cụt trên đường USB**. Phần ảnh thiếu được bộ giải mã tô bằng một vân
khối 8×8 xám lặp lại, thường có vệt xé ngang ở phía trên. Kiểu hỏng này được thấy lần đầu trên ảnh giao diện bàn thử giai
đoạn 2. Từ nay `camera_bench measure` và `record` đếm nó ở cột `truncated_frames`, nằm trong số khung mới. Bộ dò là
`video/sources.py::truncated_rows`, và `UsbCameraSource` loại những khung này.

Đo lại chiều 23/09, sau khởi động lại máy, cùng hub bus-powered, camera nằm trên bàn nhìn xuống thảm có hoa văn dày
(mọi dòng trừ dòng cuối: `runs/rig_bench/20260923_v3/raw/`, 8–15 s mỗi phiên, chỉ đọc camera, không AI; dòng cuối gộp
các phiên khác, xem ghi chú trong dòng):

| Camera chạy cùng lúc | Độ phân giải | Khung bị cắt: cổng 1 / 2 / 3 / 4 |
|---|---|---|
| cổng 1 một mình (hai lần) | 720p | 0 % / — / — / — |
| cổng 2 một mình | 720p | — / 0 % / — / — |
| cổng 1 + 2 | 720p | 1 % / 0 % / — / — |
| cổng 1 + 2 + 3 | 720p | 97 % / 0 % / 9 % / — |
| cả bốn (ba lần, hai thứ tự mở) | 720p | 99–100 % / 0 % / 0–70 % / 81–100 % |
| cổng 2 + 3 + 4 | 720p | — / 0 % / 1 % / 67 % |
| cả bốn | 1080p | 99 % / 13 % / 100 % / 100 % |
| cả bốn (phiên 15 s) | 640×480 | 0 % / 0 % / 0 % / 0 % |
| cả bốn, cộng 18 phiên 15–600 s từ 16:06 tới 16:50 (khác các dòng trên: gồm cả phiên chạy cùng LiDAR + AI (u01, u04), cùng LiDAR (a03, a06) và cùng bốn tiến trình bận CPU (a02, a05); bảng từng phiên ở [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 2.4) | 640×480 | 4,6 % (1418 / 31142 khung, gần hết trong hai đợt 26 % và 36 %) / 0 % / 0 % / < 0,1 % (6 khung) |

Hệ quả cho mục 4.2–4.5:

- **Khung bị cắt là do chạy chung, không phải do từng camera hỏng.** Chạy một mình thì camera nào cũng nguyên vẹn. Càng
  nhiều camera ở 720p/1080p thì càng nhiều khung bị cắt. Ở 640×480 thì phần lớn thời gian không khung nào bị cắt, nhưng
  camera cổng 1 có những đợt 26–36 % khung hỏng, chưa rõ nguyên nhân (GIAI_DOAN_2_BAN_THU.md mục 2.4). Điều này hợp với giả
  thuyết thiếu băng thông USB 2.0 dùng chung qua hub, nhưng **chưa chứng minh** được. OpenCV/DirectShow trên máy này không
  trả byte MJPEG thô, dù đã đặt `CAP_PROP_CONVERT_RGB = 0`, nên chưa đo được kích thước khung hay dấu kết thúc ảnh.
- **Camera cổng 2 chưa từng bị cắt ở 720p**, ở mọi tổ hợp và thứ tự mở. Chưa biết vì sao. Có thể do khung cảnh nó nhìn
  cho ảnh JPEG nhỏ hơn, hoặc do cách nó được cấp băng thông.
- **Các chữ "sạch" sau khi rút/cắm lại (mục 4.5) không có nghĩa là ảnh nguyên vẹn.** Các phiên q* không kiểm khung bị cắt,
  và khung cảnh lúc đó cũng khác (tối hơn). Chiều 23/09, cùng hub, 720p × 4 và 1080p × 4 cho phần lớn khung bị cắt ở hai
  hoặc ba camera. Kết luận dùng được: **bốn camera qua hub này chỉ dùng được ở 640×480**, và ngay cả ở 480p vẫn phải
  bật bộ dò để loại khung hỏng. *Cập nhật 24/09/2026:* trên bàn thử, hai phiên 4 × 720p 60 s (w03/w04,
  `runs/rig_bench/20260924_wait/`) cho 0 khung bị cắt/xé ở cả bốn cổng, nhưng lúc đó camera nhìn chỗ tối (cổng 2 gần
  đen). Đây là thêm một dấu hiệu khung bị cắt phụ thuộc cảnh (kích thước JPEG). Nó không phải bằng chứng 720p đã dùng
  được, nên kết luận 640×480 giữ nguyên ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 10).
- Các ảnh tĩnh r01–r03 (một camera) và `source_cam0_720p` (một camera) không bị ảnh hưởng. Bộ dò chạy lại trên chín ảnh
  PNG của r01–r03 cho 0 khung bị cắt.
- Việc cần làm ở mục 6 đổi thứ tự: thử **tách camera ra hai cổng gốc khác nhau** của máy (hai camera qua hub, hai camera
  cắm thẳng) và thử nguồn ngoài cho hub, với cột khung bị cắt. Chi tiết và phiên chạy chung với LiDAR + AI ở
  [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md).

## 5. Đối chiếu với kế hoạch

- Bước 1–2 "Khi nhận một camera": bước 1 xong phần biến thể theo VID/PID (1BCF:0B09) và giao tiếp (UVC qua DirectShow), có hồ sơ; góc nhìn 130° là số nhà bán ghi, chưa đo (mục 1); chiều dài/loại dây camera **chưa ghi** (tiền đề "dùng dây ngắn trước" chưa có hồ sơ; cần ghi vào hardware_inventory.md để bước 9 giai đoạn 2 có cấu hình "ngắn" đối chiếu). Bước 2 (mode thật): xong, có hồ sơ (`camera_modes.csv`). Bước 3 (một phiên đo FPS, thời gian suy luận, độ trễ, mất hình, CPU/GPU, nhiệt): **có** FPS, mất hình (khung cũ), CPU; **chưa** độ trễ, thời gian suy luận, GPU, nhiệt (tính tới sáng 23/09). *Cập nhật 24/09/2026:* thời gian suy luận, độ trễ trong máy (tuổi kết quả AI), tải GPU và nhiệt GPU đã đo chiều 23/09 trên bàn thử bốn camera + LiDAR + AI ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 3.3–3.4); vẫn chưa đo độ trễ từ sự kiện thật tới lúc khung tới máy, nhiệt CPU, và chưa đo trên laptop RTX 3050 Ti (máy nộp đồ án). Bước 4 (ảnh ở độ cao/góc chúc/khoảng cách dự kiến): chưa. Bước 5 (hiệu chuẩn): chưa (từ 24/09 có công cụ, [HIEU_CHUAN_CAMERA.md](HIEU_CHUAN_CAMERA.md); chưa hiệu chuẩn camera nào). Bước 6 (AI trên ảnh thật): chưa.
- Giai đoạn 2 "Khi đủ bốn camera": bước 1 (bốn camera cùng mode chung) làm xong về phép đo: mốc đề xuất 720p30 MJPEG đạt về mode nhưng thực tế là **720p ≈ 24 fps**; camera cổng 4 rớt thất thường và 1080p × 4 không đạt trước khi rút/cắm lại, sau khi rút/cắm lại các camera cả 720p × 4 lẫn 1080p × 4 không còn khung cũ (mục 4.5) — **nhưng đính chính mục 4.6: tính cả khung MJPEG bị cắt cụt thì bốn camera qua hub chỉ dùng được ở 640×480 (vẫn có đợt khung hỏng ở cổng 1); ở 720p hai–ba camera bị cắt phần lớn khung**; tiền đề "trên dây ngắn" chưa ghi (dây camera chưa kiểm kê). Bước 3 gồm bốn phần: sơ đồ cổng USB — xong ([usb_topology.md](usb_topology.md)); nguồn hub — **chưa ghi** (bus-powered, chưa thử adapter); cách gán camera vào hướng — chưa (sẽ ghi theo cổng khi có gá); kiểm nhận dạng sau rút/cắm — **xong một lần** (sau cả hai lần rút/cắm; hai bản `list` liền nhau 18 s, cùng bảng, `usb_topology_20260923_replug1/2.json`; đính chính 24/09/2026, trước ghi "hai lần", xem mục 4.5); sau khởi động lại — **xong**: InstanceId theo cổng giữ nguyên, index OpenCV đổi (cổng 2 và 4 hoán index; `usb_topology_20260923_after_reboot.json`). Bước 2, 4, 5, 6, 7, 8, 9: chưa (tình trạng sáng 23/09). **Cập nhật 24/09/2026:** bước 2 và 5 đã làm một phần trên máy bàn chiều 23/09, ở 640×480, camera chưa gá ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 3–4 và 10). Đã ghi khung tốt/s, khung bị cắt/xé và khung cũ riêng từng camera khi chạy đồng thời với LiDAR và AI. Bộ ảnh được ghép theo thời gian; độ lệch trong bộ ở 480p có trung vị 15,0 ms, p95 24,1 ms (u01), và độ lệch giữa LiDAR với bộ ảnh đã ghi. Các độ lệch này tính theo lúc khung tới máy, không phải lúc phơi sáng. Chưa đo độ trễ từ sự kiện thật, chưa chạy trên laptop RTX 3050 Ti (máy nộp đồ án). Bước 4 mới có công cụ nội tham ([HIEU_CHUAN_CAMERA.md](HIEU_CHUAN_CAMERA.md), mới kiểm trên ảnh tổng hợp): chưa hiệu chuẩn camera nào, chưa gá rig. Bước 6: AI đã chạy trên từng camera, nhưng quy đổi về cùng hệ tọa độ và hợp nhất thì chưa. Bước 7, 8, 9: chưa.
- Danh tính camera = cổng hub (không serial); index OpenCV không theo thứ tự cổng (0→1, 1→3, 2→4, 3→2) → mã vận hành
  phải chọn theo InstanceId.
- Điều kiện chuyển bước gate 1 phần camera ghi ở [gate_01.md](gate_01.md): "nhận ổn ở mode đã ghi rõ" đạt trên máy
  bàn cho một camera 720p MJPG (24 fps, 0 khung cũ trong 30 s); "đủ nét trong vùng làm việc, hiệu chuẩn được, chạy AI
  trên ảnh thật" chưa; "có số đo" có cho FPS/khung cũ/CPU, chưa cho độ trễ/suy luận/GPU/nhiệt (sáng 23/09).
  *Cập nhật 24/09/2026:* các phiên chạy chung bốn camera 640×480 + LiDAR + AI trên máy bàn chiều 23/09 (u01, u04;
  [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 3) đã cho thêm khung bị cắt/xé, thời gian suy luận (u01:
  16,4 ms/lô bốn ảnh), độ trễ trong máy, độ lệch camera–LiDAR, tải GPU (u01: TB 26 %) và nhiệt GPU (u01: 41 → 46 °C),
  khớp với [gate_01.md](gate_01.md); vẫn chưa đo độ trễ từ sự kiện thật tới lúc khung tới máy, nhiệt CPU, và mọi số trên
  laptop RTX 3050 Ti (máy nộp đồ án).

## 6. Việc còn lại — cần người

0. **Tách camera ra nhiều cổng gốc** (mới, theo mục 4.6): hai camera qua hub, hai camera cắm thẳng vào cổng gốc khác của máy,
   rồi chạy lại bốn camera 720p và đọc cột khung bị cắt. Nếu hết bị cắt thì nguyên nhân là băng thông dùng chung qua hub.
   Phải chạy với cảnh sáng, nhiều chi tiết như chiều 23/09, vì cảnh tối cho 0 khung bị cắt kể cả khi cả bốn camera qua
   hub (w03/w04, 24/09; mục 4.6).
1. **Phép thử nguồn ngoài** (chưa làm, nay phải đọc thêm cột khung bị cắt): rút cả bốn camera, cắm adapter nguồn cho hub, cắm lại camera, mở thử cả bốn, rồi chạy
   `measure --index 0 1 2 3 --width 1920 --height 1080 --seconds 30` và ba phiên 720p 10 s. Trước đó nên chạy một lượt rút/cắm không
   đổi gì khác để biết riêng tác dụng của rút/cắm (mục 4.5). Nếu muốn tách "camera hay cổng": đổi chỗ cắm camera cổng 4 rồi chạy lại.
2. ~~Khởi động lại máy~~ — đã làm 12:35 ngày 23/09: InstanceId giữ nguyên, index đổi. Mã vận hành phải chọn camera theo cổng/InstanceId.
3. **Đặt camera ở độ cao và góc chúc dự kiến trên xe**, bày hộp/thành/xe mô hình, chụp bằng nút "Chụp bộ ảnh" của bàn
   thử (`autopark.ui.rig_app`, 640×480, bật AI để bộ ảnh có xác suất làm nháp) — ảnh sa bàn đầu tiên cho nhánh AI
   (HUAN_LUYEN.md phần III, mục 18); nhập và gán nhãn theo [GAN_NHAN_SA_BAN.md](GAN_NHAN_SA_BAN.md). *(Sửa 24/09/2026:
   bản 23/09 ghi "ghi ảnh bằng `record`"; đầu ra của `camera_bench record` (AVI + PNG, không có `meta.json` hay
   `cam_p<cổng>.png`) không nhập được vào công cụ gán nhãn.)*
4. **In bảng ô vuông** có kích thước đo được để hiệu chuẩn 130°; mã hiệu chuẩn cho ống kính thật đã có từ 24/09 (`perception/fisheye_calib.py`, giao diện `ui/calib_app.py`, bảng in sẵn trong `calibration/bang_in/`, hướng dẫn [HIEU_CHUAN_CAMERA.md](HIEU_CHUAN_CAMERA.md)), mới kiểm trên ảnh tổng hợp, chưa hiệu chuẩn camera nào
   (nội tham của camera thật nạp bằng `fisheye_calib.load_intrinsics`; `CameraCalibration` trong
   `perception/calibration.py` còn cần ngoại tham, chưa có — sửa 24/09/2026, trước ghi tệp đó "chỉ đọc mô hình fisheye
   của WoodScape").
5. Xác nhận nguồn hub, đo dòng camera; ghi chiều dài/loại dây camera vào kiểm kê; thử trên laptop RTX 3050 Ti (máy nộp đồ án); thử cáp kéo dài — theo thứ tự kế hoạch.
6. Chạy AI trên ảnh thật và lưu cả lỗi (bước 6 "Khi nhận một camera").
7. Một phiên đo đủ bước 3 trên laptop RTX 3050 Ti (máy nộp đồ án): FPS, độ trễ (LED/đồng hồ), mất hình, thời gian suy luận, CPU/GPU, nhiệt.
8. ~~Bốn camera chạy cùng LiDAR + AI, ghi sai lệch thời gian giữa các luồng (giai đoạn 2, bước 2 và 5)~~ — ghi chú
   24/09/2026: đã làm trên máy bàn chiều 23/09 ở 640×480 (u01 120 s, u04 600 s; `runs/rig_bench/20260923_v3/`,
   [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 3–4). Còn lại: độ trễ từ sự kiện thật (LED nháy, việc 7), và
   chạy lại trên laptop RTX 3050 Ti (máy nộp đồ án).
9. Thử ánh sáng: cùng camera dưới đèn sa bàn, và phơi sáng thủ công kèm `CAP_PROP_GAIN`, để biết 30 fps có đạt với ảnh
   đủ sáng không.

## 7. Cách chạy lại

Từ thư mục `autopark`, trong `.venv` (cần `pip install -e .[video]`; `pygrabber` chỉ trên Windows):

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.video.camera_bench list --out runs/camera_bench/<ngay>/usb_topology.json
.\.venv\Scripts\python.exe -X utf8 -m autopark.video.camera_bench modes --out docs/camera_modes.csv
.\.venv\Scripts\python.exe -X utf8 -m autopark.video.camera_bench traps --index 0 --seconds 3 --name traps_cam0 --out runs/camera_bench/<ngay>
.\.venv\Scripts\python.exe -X utf8 -m autopark.video.camera_bench source --index 0 --width 1280 --height 720 --frames 120 --name source_cam0_720p --out runs/camera_bench/<ngay>
.\.venv\Scripts\python.exe -X utf8 -m autopark.video.camera_bench measure --index 0 --width 1280 --height 720 --seconds 30 --name m01_cam0_720p_auto --out runs/camera_bench/<ngay>
.\.venv\Scripts\python.exe -X utf8 -m autopark.video.camera_bench measure --index 0 1 2 3 --width 1280 --height 720 --seconds 60 --name m05_4cam_720p_auto --out runs/camera_bench/<ngay>
.\.venv\Scripts\python.exe -X utf8 -m autopark.video.camera_bench measure --index 0 --width 1280 --height 720 --seconds 20 --exposure -6 --name m02_cam0_720p_exp-6 --out runs/camera_bench/<ngay>
.\.venv\Scripts\python.exe -X utf8 -m autopark.video.camera_bench record --index 0 --width 1280 --height 720 --seconds 20 --name r01_cam0_720p --out runs/camera_bench/<ngay> --snapshot-every 4
.\.venv\Scripts\python.exe -X utf8 -m autopark.video.camera_bench report runs/camera_bench/<ngay>
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_camera_bench.py tests/test_phase1_sources.py
```

`measure --index 2 0 1 3` mở camera theo đúng thứ tự đó và ghi vào `requested.indices`. Mở một camera theo index
OpenCV để thử nhanh (index đổi sau khởi động lại, mục 5):
`open_source("usb:0", width=1280, height=720, fourcc="MJPG", fps=30)`; phơi sáng thủ công thêm `exposure=-6`. *Cập nhật 24/09/2026:* mã vận hành bốn camera (bàn thử giai đoạn 2,
`rig.bench`) chọn camera theo cổng hub qua `video/multicam.py::resolve_ports` + `MultiCameraManager`, mặc định 640×480
MJPG (`rig.bench`, `RigConfig`; lớp `MultiCameraManager` tự nó vẫn để mặc định 1280×720) — theo mục 4.6 và
[GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 2.4.

## 8. Kiểm tra độc lập

Bản đầu của tài liệu này và công cụ đo qua một vòng review đối kháng 15 agent (3 lăng kính: mã, số liệu, kế hoạch;
mỗi phát hiện một agent hoài nghi cố bác bỏ). 12 phát hiện được xác nhận và đã sửa: luồng đo chết bị bỏ qua im lặng;
`record` để lại file hỏng khi camera không có khung mới; docstring `UsbCameraSource` mâu thuẫn; các số "thử nhanh"
không có hồ sơ (nay đã chạy lại thành phiên có file: `traps`, m09–m13); "mỗi khung 47 ms" sai vì trung bình là 41,9 ms
(nay có phân bố từng khoảng); 100 KB/khung là JPEG mã hóa lại, không phải payload USB; các bước kế hoạch chưa làm bị
bỏ sót (độ trễ, suy luận, GPU, nhiệt, đồng bộ, chạy cùng LiDAR/AI); khẳng định danh tính theo cổng chưa có bằng chứng.
