# Ngoại tham camera và mặt nạ ROI cho camera của dự án: công cụ và cách làm (24/09/2026)

**Kế hoạch đối chiếu:** v3.1 mục 6, "Khi đủ bốn camera", bước 4
([bản `9d68257`](https://github.com/thbn12082/autopark/blob/9d68257/KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md); bản hiện tại:
mục 6, đoạn "Có đồ"): *"Hiệu chuẩn riêng từng camera; gắn lên rig rồi xác định vị trí/hướng của camera so với rig."*
Đầu ra cần có gồm `camera_rig_extrinsics.yaml`; dự án dùng JSON (`configs/rig/camera_rig_extrinsics_v1.json`) vì cả
hai môi trường Python không có thư viện YAML. Công cụ ở đây là việc mục 5.4 của TONG_HOP_DU_AN.md bản `9d68257` ("Công
cụ ngoại tham camera … Công cụ dựng mặt nạ ROI cho camera dự án"); việc đo thật nay ở
[TONG_HOP_DU_AN.md](../../TONG_HOP_DU_AN.md) mục 5.2 (việc "Hiệu chuẩn camera, đo ngoại tham, tạo ROI"). Cũng là mục
8, việc 2–3, của [BEV.md](BEV.md).

**Mức bằng chứng:** công cụ mới chỉ được kiểm trên **ảnh TỔNG HỢP** và trên nguồn camera giả trong test (mục 7). **Chưa
chạy với camera thật nào.** Chưa làm thật được, vì:

- chưa camera nào được hiệu chuẩn nội tham: `calibration/cam_p*.json` chưa có. Ngoại tham không có nghĩa khi chưa có nội
  tham, và công cụ từ chối chạy nếu thiếu tệp đó ([HIEU_CHUAN_CAMERA.md](HIEU_CHUAN_CAMERA.md));
- chưa có xe MN300, chưa gá camera, gán cổng hub → hướng CHƯA CHỐT ([usb_topology.md](usb_topology.md)).

Mọi ngưỡng dưới đây là **ĐỀ XUẤT – CHỜ CHỐT**, chưa kiểm trên camera thật.

**Thứ tự bắt buộc:**

1. Nội tham từng camera ([HIEU_CHUAN_CAMERA.md](HIEU_CHUAN_CAMERA.md)) → `calibration/cam_p<N>.json` (mode 640×480).
   *(Thêm 02/10/2026, T11: tệp `cam_<tên>.json` của camera không qua hub 1..4, như camera trên cao, không dùng được ở
   đây: `load_camera_intrinsics` từ chối nó ("… là nội tham của camera ngoài hub …: ngoại tham và ROI chỉ dành cho camera
   xe theo cổng hub 1..4"), cả ở dòng lệnh lẫn giao diện `roi_app`; test
   `test_intrinsics_of_a_camera_outside_the_hub_are_refused_for_extrinsics`.)*
2. Gá camera **cứng** lên xe, chốt cổng nào là hướng nào.
3. Ngoại tham (mục 2–5 ở đây) → `configs/rig/camera_rig_extrinsics_v1.json`.
4. ROI (mục 6) → `configs/roi/rig_v1/roi_p<N>.png`.
5. BEV trên bộ ảnh thật với tệp rig mới và ROI (mục 5.4), rồi đặt vật mẫu ở vị trí đo bằng thước để kiểm BEV (BEV.md mục 8).

Gá lại camera, hay xe bị va, thì phải đo lại ngoại tham và dựng lại ROI của camera đó.

## 1. Công cụ

| Việc | Mã | Kiểm (không cần thiết bị) |
|---|---|---|
| Ngoại tham: tư thế bảng từ số đo thước, dò và đánh số góc bảng, giải tư thế camera, gộp nhiều lần đặt, loại lần đặt lệch, các phép kiểm, ghi/đọc tệp rig, ảnh kiểm (lưới hệ xe và hộp thân xe chiếu lên ảnh), dòng lệnh, bộ thử tổng hợp | `perception/extrinsics_calib.py` | `tests/test_extrinsics_calib.py` (29 test; *02/10/2026: 35 mục khi đếm bằng `--collect-only`, gồm test từ chối tệp nội tham của camera ngoài hub, T11*) |
| ROI: đa giác → mặt nạ PNG, nới vùng loại, ghi/đọc, kiểm một mặt nạ, dòng lệnh | `perception/roi_tool.py` | `tests/test_roi_tool.py` (phần ROI, 9 test) |
| Giao diện hai thẻ "Ngoại tham" và "ROI": mở ảnh, bộ ảnh bàn thử, hoặc camera sống theo cổng hub | `ui/roi_app.py` | `tests/test_roi_tool.py` (phần giao diện, 10 test, offscreen; camera sống là nguồn giả) |

Giao diện:

```
.venv\Scripts\python.exe -X utf8 -m autopark.ui.roi_app --port 1
.venv\Scripts\python.exe -X utf8 -m autopark.ui.roi_app --port 1 --snapshot runs\rig_snapshots\<ngày_giờ>
.venv\Scripts\python.exe -X utf8 -m autopark.ui.roi_app --port 1 --live
```

`--live` mở **camera thật** ở cổng hub đó (640×480 MJPG, như `calib_app`). Mở giao diện không có `--live` thì không đụng
tới camera nào, cho tới khi tích ô "Camera sống".

Thử công cụ khi chưa có camera (dữ liệu **tổng hợp**, không phải số đo):

```
.venv\Scripts\python.exe -X utf8 -m autopark.perception.extrinsics_calib synthetic --out runs\extrinsics\tong_hop
.venv\Scripts\python.exe -X utf8 -m autopark.ui.roi_app --port 1 --image runs\extrinsics\tong_hop\dat_01.png --intrinsics runs\extrinsics\tong_hop\calibration\cam_p1.json
.venv\Scripts\python.exe -X utf8 -m autopark.perception.extrinsics_calib solve --placements runs\extrinsics\tong_hop\dat_bang_p1.json --out runs\extrinsics\tong_hop\camera_rig_tong_hop.json --allow-synthetic
```

Lệnh `synthetic` in kèm tư thế thật của camera ảo để so với kết quả.

**Kết quả tổng hợp không bao giờ thành "số đo"** (sửa tối 24/09/2026). Tệp nội tham của bộ thử mang `"synthetic": true` và
`device` = "TỔNG HỢP". Kết quả giải bằng nội tham đó:

- không có `--allow-synthetic` thì bị từ chối ghi (mã 2); lệnh `solve` không có `--out` chỉ gợi ý ghi vào thư mục bộ thử;
- có `--allow-synthetic` thì ghi được, nhưng camera và cả tệp mang `"synthetic": true`, `basis` / `status` mở đầu bằng
  "TỔNG HỢP — KHÔNG PHẢI SỐ ĐO", và lệnh `check` in nhãn đó cho camera thay vì "ĐO";
- tệp ra nằm trong `configs\` hay `calibration\` của dự án thì **luôn** bị từ chối, kể cả khi có cờ; lệnh `synthetic`
  cũng từ chối thư mục ra nào làm tệp nội tham ảo rơi vào `calibration\` hay `configs\` của dự án;
- tệp gốc (`--base`, ô "Chép từ") có camera tổng hợp thì cũng cần cờ, và cũng không được ghi vào `configs\`;
- giao diện: nạp nội tham tổng hợp thì ô "Ghi vào" tự chuyển từ `configs\rig\camera_rig_extrinsics_v1.json` sang
  `<bộ thử>\camera_rig_tong_hop.json`.

`"measured": true` vẫn giữ trong tệp tổng hợp để thử nối trọn BEV trên ảnh tổng hợp. *(Sửa 25/09/2026:)* `bev.py` nay đọc
khóa `synthetic` (ở camera hay cả tệp) và cả dấu TỔNG HỢP của tệp nội tham: camera đó mang lý do "ngoại tham/nội tham là
dữ liệu TỔNG HỢP — không phải số đo", nên BEV không bao giờ thành "dùng được" với dữ liệu tổng hợp. Nhãn và chỗ ghi vẫn
ngăn nhầm như trước (mục 8).

## 2. Hệ tọa độ và các góc bảng phải đo

**Hệ xe** (giống `configs/rig/camera_rig_extrinsics_v0.json` và `perception/bev.py`): x hướng trước, y sang trái, z lên.
Gốc nằm **trên mặt sàn, ngay dưới tâm trục sau**, tức trung điểm của hai điểm chạm sàn của hai bánh sau. Đơn vị mét.

**Bảng:** dùng bảng in sẵn 9×6 góc trong. Cầm tờ in xoay ngang sao cho dòng chữ in ở phía trên và đọc xuôi được:

```
      dòng chữ in (đọc xuôi)
   ┌───┬───┬───┬ … ┬───┬───┐
   │ ■ │   │ ■ │   │ ■ │   │      ■ = ô đen. Ô góc trên-trái luôn ĐEN.
   ├───O───┼───┼ … ┼───A───┤      O = góc trong đầu tiên, sát ô đen góc trên-trái
   │   │ ■ │   │   │   │ ■ │      A = góc trong cuối của cùng hàng (thứ 9, bên phải)
   ├───┼───┼───┼ … ┼───┼───┤      B = góc trong cuối của cùng cột với O (thứ 6, đi xuống)
   ⋮                       ⋮      C = góc trong đối diện O
   ├───B───┼───┼ … ┼───C───┤
   │ ■ │   │ ■ │   │ ■ │   │
   └───┴───┴───┴ … ┴───┴───┘
```

- Trục x của bảng đi từ O sang A; trục y đi từ O xuống B. Khi bảng nằm ngửa trên sàn và nhìn từ trên xuống, **B nằm bên
  PHẢI của hướng O → A** (quay 90° theo chiều kim đồng hồ). Thấy B nằm bên trái thì đang nhầm góc.
- Giao diện vẽ chữ O, A, B, C lên ảnh ngay khi thấy bảng: **đo đúng các góc giao diện chỉ**. Công cụ xác định O bằng màu
  ô, không dựa vào thứ tự OpenCV trả về. Trên ảnh tổng hợp bảng nằm trên sàn, OpenCV trả thứ tự ngược ở mọi ảnh đã thử.
- Góc trong là điểm hai ô đen chạm nhau: một điểm rõ, đặt đầu thước vào đó được.

**Góc của camera** chỉ để đọc. Tệp rig lưu `quaternion_xyzw` (camera → xe, giống WoodScape). Báo cáo in thêm `yaw_deg`
(hướng trục quang chiếu xuống sàn, đo từ +x, dương ngược chiều kim đồng hồ), `pitch_down_deg` (góc chúc xuống) và
`roll_deg`, theo đúng quy ước của tệp v0.

## 3. Chuẩn bị (một lần cho cả bốn camera)

1. **Bảng.** Nên dùng `calibration/bang_in/ban_co_9x6_30mm_A3.pdf`: *kỳ vọng* ô to hơn thì dò được xa hơn, nhưng CHƯA ĐO —
   phép thử tổng hợp ở mục 7 cho cùng vùng 0,05–0,30 m với cả A4 ô 20 mm lẫn A3 ô 30 mm *(sửa 25/09/2026)*. In 100 %, dán lên tấm
   phẳng và cứng, đo cỡ ô bằng thước như [HIEU_CHUAN_CAMERA.md](HIEU_CHUAN_CAMERA.md) mục 2, và nhập **cỡ ô ĐO ĐƯỢC**.
   Đo độ dày tấm dán: đó là **độ cao mặt in trên sàn** (`board_z_m`, ví dụ 0,005 m với tấm xốp 5 mm). Quên nhập thì camera
   bị tính thấp đi đúng chừng đó (có test, mục 7).
2. **Sàn** phẳng, cứng (không trải thảm), đủ sáng, không lóa trên bảng.
3. **Xe** đứng yên, bánh trước để thẳng. **Không chạm vào xe và camera trong suốt buổi đo**: mọi lần đặt bảng phải thấy
   cùng một tư thế camera.
4. **Vạch hệ xe trên sàn** bằng băng dính:
   - đánh dấu điểm chạm sàn của hai bánh sau, lấy trung điểm: đó là gốc. Làm như vậy với hai bánh trước;
   - trục x: một đường thẳng qua hai trung điểm, chiều dương hướng về đầu xe, kéo dài ra trước và sau xe;
   - trục y: một đường vuông góc với trục x (dùng ê-ke) đi qua gốc, kéo dài ra hai bên xe;
   - vì phần dưới gầm xe khó đặt thước, dán thêm **vạch phụ** song song với các trục, ở tọa độ đã đo từ gốc: ví dụ một
     vạch ngang trước đầu xe ở x = X_trước, một vạch sau đuôi, và hai vạch dọc hai bên ở y = ±Y_bên. Khi đó tọa độ của
     một góc bảng = tọa độ vạch phụ + khoảng cách vuông góc từ góc bảng tới vạch đó.
   - Ghi lại tọa độ các vạch phụ. Sai số ở bước này đi thẳng vào ngoại tham của **mọi** camera, và CHƯA ĐO.

## 4. Đặt bảng và thu ảnh (từng camera)

**Đặt ở đâu.** Camera trên xe 1/12 rất thấp, nên bảng nằm trên sàn bị dẹt mạnh trên ảnh. Trên ảnh **tổng hợp** (camera
cao 0,12 m chúc 30°, và cao 0,15 m chúc 45°), bảng chỉ dò được khi **hàng góc trong gần nhất cách điểm trên sàn ngay dưới
camera khoảng 0,05–0,30 m** (0,35 m với camera 0,15 m / 45°). Xa hơn thì ô quá dẹt và OpenCV không dò được (script tạm ngày
24/09/2026 trên máy bàn, không lưu trong repo). Đặt bảng nằm ngang trước camera, sát xe. Nếu giao diện báo "không thấy
đủ 9×6 góc trong" thì dời bảng lại gần.

**Bao nhiêu lần.** Ít nhất 2 lần đặt, vì công cụ từ chối khi chỉ có 1. Nên 3–4 lần ở các chỗ và góc xoay khác nhau: bên
trái, giữa, bên phải, xoay ±15°. Có từ 3 lần trở lên thì công cụ loại được một lần đo sai; với 2 lần, nếu chúng không khớp
thì công cụ chỉ từ chối được.

**Mỗi lần đặt:**

1. Đặt bảng, chờ giao diện vẽ O, A, B, C lên ảnh (nếu chưa nạp nội tham thì giao diện báo "chưa biết góc nào là O").
2. Đo tọa độ (x, y) trong hệ xe của **O và A**, nên đo thêm **B** và **C** (tích "Dùng B", "Dùng C"). Đo tới 1 mm bằng
   thước thép và ê-ke. Đo càng nhiều góc thì hướng bảng càng chính xác. Công cụ khớp các điểm đo với cỡ bảng: lệch quá
   5 mm thì từ chối lần đặt đó ("số đo thước không khớp cỡ bảng").
3. Nhập số đo, bấm **"Thêm lần đặt (ảnh hiện tại)"**. Công cụ giải ngay lần đặt đó và hiện RMS cùng độ cao camera suy ra
   từ riêng nó. Không xê dịch bảng giữa lúc chụp và lúc đo.

**Nguồn ảnh:**

- **Camera sống** trong giao diện (`--live`, hoặc tích "Camera sống"): "Thêm lần đặt" dùng khung sống ngay lúc bấm. Ảnh
  được lưu vào thư mục phiên khi ghi tệp rig.
- **Bộ ảnh của bàn thử**: đặt bảng, bấm "Chụp bộ ảnh" trong `rig_app` (ghi `runs/rig_snapshots/<ngày_giờ>/cam_p<N>.png` của
  cả bốn camera), rồi trong `roi_app` bấm "Mở bộ ảnh…". Khi bảng nằm trong vùng hai camera cùng thấy, cùng một bộ ảnh và
  cùng số đo dùng được cho cả hai camera. Đổi cổng thì giao diện tự lấy `cam_p<cổng mới>.png` của cùng bộ ảnh (cách này
  CHƯA THỬ trên phần cứng).
- **Dòng lệnh**, không cần giao diện, với một tệp danh sách lần đặt (giao diện tự ghi tệp này vào thư mục phiên):

```json
{"format": "autopark.extrinsics_placements/1", "port": 1,
 "board": {"cols": 9, "rows": 6, "square_mm": 29.9, "square_mm_measured": true, "board_z_m": 0.005},
 "placements": [
  {"name": "dat_01", "snapshot": "runs/rig_snapshots/20260925_101010_123", "points_xy_m": {"O": [0.61, 0.13], "A": [0.61, -0.109], "B": [0.46, 0.13]}},
  {"name": "dat_02", "image": "anh/dat_02.png", "points_xy_m": {"O": [0.58, 0.20], "A": [0.642, -0.031]}}]}
```

```
.venv\Scripts\python.exe -X utf8 -m autopark.perception.extrinsics_calib solve --placements runs\extrinsics\dat_bang_p1.json --out configs\rig\camera_rig_extrinsics_v1.json
```

Một lần đặt ngắn gọn cũng nhập được trên dòng lệnh: `--port 1 --square-mm 29.9 --place <ảnh> OX OY AX AY` (lặp `--place`
cho mỗi lần đặt). Số viết dấu chấm hay dấu phẩy thập phân đều được (`0.60` hay `0,60`, `--square-mm 29,9`,
`--board-z-m 0,005`); số sai (ví dụ `--square-mm 0`) bị báo lỗi tiếng Việt, mã 2.

## 5. Tính, đọc kết quả, ghi tệp rig

### 5.1. Cách tính (chi tiết ở docstring của `extrinsics_calib.py`)

1. Tư thế bảng → xe: khớp cứng 2D các điểm đo thước với vị trí danh định của chúng trên bảng.
2. Dò góc bằng đúng bộ dò của hiệu chuẩn nội tham (`fisheye_calib.detect_corners`, có `cornerSubPix`); khung MJPEG hỏng
   bị loại.
3. Đánh số góc. Thử 4 cách đánh số. Loại cách nào đặt camera dưới mặt bảng, rồi chọn theo màu ô: ô góc trên-trái phải
   đen. Cần cả hai phép kiểm, vì với bảng 9×6 màu ô không đổi khi lật thứ tự hàng.
4. Giải tư thế bảng → camera: khởi tạo bằng `cv2.fisheye.solvePnP` (có trong OpenCV 5.0.0 của cả hai môi trường, kiểm
   24/09/2026) và IPPE trên điểm đã khử méo, rồi tinh chỉnh để cực tiểu sai số chiếu lại **tính bằng điểm ảnh**.
5. Camera → xe cho từng lần đặt; rồi giải **chung** một tư thế trên mọi lần đặt, loại dần lần đặt lệch (khi còn ≥ 3 lần).
6. Kiểm chéo bằng mô hình đa thức của dự án (`FisheyeIntrinsics`), đúng mô hình mà BEV dùng để chiếu.

### 5.2. Các phép kiểm (ĐỀ XUẤT – CHỜ CHỐT)

| Kiểm | Ngưỡng | Không đạt thì |
|---|---|---|
| Số đo thước khớp cỡ bảng | lệch ≤ 5 mm mỗi điểm sau khớp | loại lần đặt: sai góc O/A/B, sai cỡ ô, bảng xê dịch |
| RMS chiếu lại của một lần đặt (tư thế riêng) | ≤ 1,0 px | loại lần đặt: bảng cong, ảnh mờ, nội tham không khớp |
| Khoảng cách camera → tâm bảng | 0,08–2,5 m | loại lần đặt: kiểm cỡ ô (mm) |
| Độ cao camera suy ra | 0,02–1,0 m | loại lần đặt: kiểm `board_z_m`, cỡ ô, nội tham |
| Bảng cách mép ảnh | ≥ 3 px | loại lần đặt |
| Tương phản ô trắng − ô đen | ≥ 30 | loại lần đặt: không xác định được góc O |
| Số lần đặt dùng được | ≥ 2 | từ chối kết quả |
| Độ lệch của một lần đặt so với tư thế chung | ≤ 2 cm và ≤ 1° | loại lần lệch nhất (khi ≥ 3 lần), không loại được thì từ chối |
| RMS chiếu lại dưới tư thế chung | ≤ 4 px | từ chối: số đo thước giữa các lần đặt không nhất quán |

RMS dưới tư thế chung chủ yếu phản ánh sai số thước. Trên ảnh tổng hợp, nhiễu thước ±2,5 mm cho RMS trung vị 1,30 px, lớn
nhất 2,18 px (20 lần bốc thăm). Lệch 6–10 mm ở mỗi lần đặt thì vượt 4 px và bị từ chối, dù độ lệch tư thế giữa các lần đặt
vẫn dưới 2 cm / 1° (mục 7).

**Cảnh báo, không chặn:** nội tham chưa đạt tiêu chí đề xuất (BEV vẫn đánh dấu costmap không dùng được); góc bảng ở θ lớn
hơn θ lớn nhất đã thấy bảng lúc hiệu chuẩn nội tham (ngoại suy); roll > 10°; cỡ ô chưa xác nhận là cỡ đo được; có lần
đặt bị loại.

**Ảnh lật gương** (driver bật mirror/flip): một lần đặt KHÔNG phát hiện được, vì bảng phản chiếu vẫn khớp một khung bảng
hợp lệ. Nhiều lần đặt ở vị trí và hướng khác nhau thì các tư thế suy ra không khớp nhau và kết quả bị từ chối (mục 7).
Thêm một lý do để đặt bảng ít nhất 3 lần, xoay khác nhau.

### 5.3. Kiểm bằng mắt

Sau "Tính ngoại tham", ảnh của lần đặt đang chọn hiện **lưới mặt sàn của hệ xe** chiếu qua tư thế vừa đo: đường xám cách
nhau 0,1 m, trục x của xe (đường y = 0) màu đỏ, trục y của xe (đường x = 0) màu xanh lá — cùng quy ước màu với mũi tên
trục x (đỏ) / y (xanh lá) của bảng. Góc bảng dự đoán hiện thành vòng tròn tím. **Lưới phải nằm đúng lên vạch băng dính
trên sàn**, và vòng tím phải trùng góc bảng. Dòng lệnh ghi cùng ảnh này thành `xem_<lần đặt>.jpg` trong thư mục báo cáo
(`runs/extrinsics/<ngày_giờ>_p<N>/`).

**Hộp thân xe màu trắng** lấy từ `vehicle_assumed` của tệp "Chép từ" (dòng lệnh: `--base`, mặc định v0): đó là kích thước
xe **GIẢ ĐỊNH – CHƯA ĐO**, đã nới thêm `ego_margin_m` (0,02 m ở v0), nên không dùng hộp trắng để kiểm ngoại tham. Hộp chỉ
hiện khi cạnh của nó nằm trong ảnh: với camera tổng hợp của bộ thử (cao 0,125 m, gá ở mép trước xe x = 0,33 m, chúc 31°)
hộp nằm ngoài ảnh nên không thấy. (Trước bản sửa tối 24/09/2026, hộp này không được vẽ dù tài liệu đã hứa; màu hai trục cũng ngược
với mũi tên của bảng.)

### 5.4. Ghi tệp rig, kiểm, đưa vào BEV

- Giao diện: "Ghi tệp rig". Công cụ lưu phiên (ảnh, `dat_bang_p<N>.json`, `ket_qua.json`, ảnh kiểm) vào
  `runs/extrinsics/<ngày_giờ>_p<N>/`, rồi ghi tệp rig. Dòng lệnh: thêm `--out`.
- **Đổi thông số sau khi tính thì phải tính lại.** Đổi số góc, cỡ ô, ô "Đã đo cỡ ô", hay nạp lại nội tham sau "Tính ngoại
  tham" thì kết quả cũ mất hiệu lực: nút "Ghi tệp rig" tắt, các lần đặt được phân tích lại theo thông số mới, phải bấm
  "Tính ngoại tham" lại. Phiên lưu ghi đúng thông số đã dùng để tính, nên chạy lại bằng dòng lệnh cho cùng tư thế đã ghi
  (có test). Độ cao mặt in (`board_z_m`) lưu theo từng lần đặt lúc bấm "Thêm lần đặt": đổi ô này chỉ áp dụng cho các lần
  đặt thêm sau. Bảng có cols + rows chẵn bị báo lỗi ngay trên giao diện. (Sửa tối 24/09/2026; trước đó đổi cỡ ô sau khi tính
  vẫn ghi được tư thế cũ, và đổi số góc làm giao diện lỗi khi vẽ lại.)
- **Không ghi đè im lặng.** Tệp ra đã có thì bị từ chối, trừ khi tích "cho phép ghi đè" (dòng lệnh: `--overwrite`). Bản cũ
  được sao lưu thành `<tên>.bak_<ngày_giờ_micro giây>[_NNN].json`; tên sao lưu được giữ chỗ độc quyền, nên hai lần ghi đè
  trong cùng một giây (bấm đúp) không đè bản sao lưu của nhau. Đo thêm camera thứ hai vào cùng tệp: đặt "Chép từ" bằng chính tệp ra
  (dòng lệnh: `--base configs\rig\camera_rig_extrinsics_v1.json --overwrite`). Nếu chép từ tệp khác mà làm **mất** số đo
  của một camera đã đo trong tệp ra, công cụ từ chối và nói tên cổng bị mất.
- Không bao giờ ghi vào tệp v0. v0 là hồ sơ giả định, giữ nguyên.
- Nội dung mỗi camera đã đo: `"measured": true`, `position_m`, `quaternion_xyzw`, `direction` (suy từ yaw đo được),
  `angles_deg_derived` (chỉ để đọc), `basis`, và `provenance` (ngày giờ, đường dẫn và ngày của tệp nội tham, bảng, từng lần
  đặt: ảnh, số đo, khớp thước, RMS, độ lệch; các phép kiểm, cảnh báo, ngưỡng; khối camera cũ bị thay). Camera chưa đo
  giữ nguyên số **GIẢ ĐỊNH** của tệp gốc với `"measured": false`. `status` ghi cổng nào đã đo. Khối `vehicle_assumed` (hộp
  thân xe) vẫn là giả định cho tới giai đoạn 4.
- Sau khi ghi, công cụ đọc lại tệp bằng chính `bev.load_rig_extrinsics` và so từng số với kết quả vừa tính.

```
.venv\Scripts\python.exe -X utf8 -m autopark.perception.extrinsics_calib check configs\rig\camera_rig_extrinsics_v1.json
.venv\Scripts\python.exe -X utf8 -m autopark.perception.bev snapshot runs\rig_snapshots\<ngày_giờ> --extrinsics configs\rig\camera_rig_extrinsics_v1.json --roi-dir configs\roi\rig_v1
```

BEV chỉ đánh dấu costmap "dùng được cho lập đường" khi mọi camera được dùng có ngoại tham đo, có ROI, và nội tham đạt tiêu
chí đề xuất. Việc nối AI vào lập đường không còn chờ quyết định giấy phép WoodScape (lúc viết, 24/09/2026, còn chờ).
Ngày 25/09/2026 người làm khóa luận quyết định dùng mô hình WoodScape trong vòng điều khiển (Valeo chưa xác nhận cách
đọc; [GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md)), và từ `b01dea4` AI camera là một nguồn vật cản của phiên đỗ xe qua
`fusion/camera_ai.py`. Nguồn đó chỉ tạo vật cản từ BEV dùng được theo điều kiện ở câu trên, nên hiện trên bàn thật AI
chưa tạo vật cản nào ([AI_DIEU_KHIEN_XE.md](AI_DIEU_KHIEN_XE.md) mục 3).

## 6. Mặt nạ ROI

**Để làm gì.** Trên thân xe, dây, viền ống kính, kết quả AI vô nghĩa. Pixel ngoài ROI không có bằng chứng và không bao giờ
thành FREE trong BEV. ROI WoodScape `roi_MVL.png` còn sót pixel sát thân xe và gây ra một vệt OCCUPIED/bị che sai
(BEV.md mục 6), nên với camera dự án phải vẽ kỹ ở mép thân xe.

**Định dạng** (đúng thứ `bev.load_rig(..., roi_dir=...)` đọc): `<thư mục>/roi_p<N>.png`, ảnh xám 8 bit ở **cỡ gốc của
khung** (cỡ đã hiệu chuẩn nội tham, mặc định 640×480). 255 là dùng được, 0 là loại. Khác cỡ thì BEV từ chối camera đó. Thư
mục đề xuất: `configs/roi/rig_v1`. Cạnh tệp PNG có `roi_p<N>.json` (các đa giác, cỡ ảnh, ảnh nguồn, ngày) để sửa lại sau,
và `roi_p<N>_xem.jpg` (vùng loại tô đỏ).

**Cách làm (thẻ "ROI" của `roi_app`):**

1. Mở ảnh của camera **đã gá trên xe**, đúng mode 640×480: một bộ ảnh của bàn thử, hoặc camera sống rồi "Chụp khung". Nên
   chụp khi sàn sáng màu, để mép thân xe dễ thấy.
2. Chọn "Loại". Bấm chuột trái theo mép thân xe (và dây, viền đen nếu có) để thêm đỉnh. Chuột phải hoặc Enter đóng đa
   giác, Backspace bỏ đỉnh cuối, Esc huỷ đa giác đang vẽ. Có thể đặt nhãn cho đa giác ("thân xe"). "Giữ" dùng khi dễ vẽ
   vùng dùng được hơn vùng loại. Có đa giác "Giữ" thì chỉ phần trong chúng được dùng, và "Loại" luôn thắng. Các đa giác
   cùng kiểu được **hợp** lại: vẽ đa giác "bánh xe" hay "dây" chồng lên đa giác "thân xe" vẫn loại cả hai (trước bản
   sửa tối 24/09/2026, chỗ chồng nhau bị đục lỗ thành dùng được). Vẽ đa giác không tự cắt (đa giác tự cắt tô theo chẵn-lẻ).
3. Vùng loại tô đỏ ngay trên ảnh, đã nới thêm `margin_px` điểm ảnh (mặc định 2, ĐỀ XUẤT – CHỜ CHỐT), vì pixel sát mép
   thân xe trộn màu thân xe với sàn. Ô báo cáo cạnh ảnh cho tỉ lệ dùng được, số mảnh rời, và cảnh báo khi không loại gì.
4. "Lưu ROI". Tệp đã có thì bị từ chối, trừ khi tích "cho phép ghi đè"; bản cũ được đổi tên thành
   `.bak_<ngày_giờ_micro giây>[_NNN]` (không bao giờ đè một bản sao lưu khác).
   Công cụ đọc lại PNG bằng `bev.read_gray` và so từng pixel. "Mở ROI đã có" nạp lại các đa giác để sửa.

**Dòng lệnh:**

```
.venv\Scripts\python.exe -X utf8 -m autopark.perception.roi_tool check configs\roi\rig_v1\roi_p1.png --image runs\rig_snapshots\<ngày_giờ>\cam_p1.png --intrinsics calibration\cam_p1.json
.venv\Scripts\python.exe -X utf8 -m autopark.perception.roi_tool build configs\roi\rig_v1\roi_p1.json --overwrite
```

`check` báo lỗi khi mặt nạ khác cỡ khung, có nhiều kênh, hay loại hết mọi pixel. Nó cảnh báo khi có giá trị khác 0/255
(BEV coi mọi giá trị > 0 là dùng được), khi không loại pixel nào, khi vùng dùng được dưới 20 % hay bị chia thành nhiều mảnh.
Có `--image` thì ghi thêm ảnh xem trước `<mặt nạ>_kiem.jpg`. `build` dựng lại PNG từ tệp đa giác, ví dụ sau khi sửa tay.

## 7. Đã kiểm gì (chỉ ảnh TỔNG HỢP, máy bàn, 24/09/2026)

Ảnh dựng bằng cách dò tia qua một camera Kannala–Brandt đã biết (K, D như `tests/test_fisheye_calib.py`, ảnh 640×480). Camera
cao 0,125 m, chúc 31°, yaw 2°, roll −1,2° (dựng bằng `bev.rig_rotation`). Bảng 9×6 ô 30 mm nằm trên sàn. Góc bảng "thật"
được tính tay trong test (y của bảng bên phải x khi nhìn từ trên xuống), độc lập với mô-đun.

| Phép thử | Kết quả |
|---|---|
| Góc đã đánh số so với góc thật chiếu bằng `cv2.fisheye.projectPoints`, 4 ảnh | lệch < 0,35 px; OpenCV trả thứ tự ngược ở cả 4 ảnh, bước đánh số theo màu sửa lại |
| 3 lần đặt, số đo thước đúng | vị trí lệch 0,04 mm, hướng 0,009°, RMS 0,075 px (qua mô hình đa thức của dự án 0,080 px) |
| 4 lần đặt, nhiễu thước đều ±2,5 mm trên O, A, B (hạt giống của test) | vị trí lệch 1,07 mm, hướng 0,15°, RMS chung 1,33 px |
| Như trên, 20 lần bốc thăm (script tạm, không lưu trong repo) | 20/20 nhận; vị trí lệch trung vị 1,52 mm, lớn nhất 3,33 mm; hướng trung vị 0,28°, **lớn nhất 0,93°**; một lần đặt riêng lẻ lệch tới 3,88 mm |
| 4 lần đặt, một lần số đo dời 4 cm | lần đó bị loại (lệch 4,0 cm), kết quả như khi đo đúng |
| 2 lần đặt, một lần dời 4 cm | từ chối, không lấy trung bình |
| 3 lần đặt, mỗi lần dời 6 mm theo một hướng | từ chối vì RMS chung ≈ 5,7 px > 4 px, dù độ lệch tư thế < 2 cm / 1° |
| Mặt in cao 5 mm | nhập đúng: độ cao camera lệch < 1 mm; quên nhập: thấp đi đúng 5 mm |
| Ảnh lật gương, 4 lần đặt | một lần đặt riêng lẻ vẫn được nhận; 4 lần hay 2 lần đặt không khớp nhau (3,3–11,1 cm, 11,6–32,2°) nên bị từ chối |
| Ảnh sai cỡ, khung bị cắt, ảnh không có bảng, thiếu/khác cổng nội tham, chỉ một lần đặt, camera "quá cao" | từng trường hợp bị từ chối với lý do tiếng Việt |
| Từng phép loại lần đặt của bảng mục 5.2 (thêm tối 24/09/2026) | nội tham lệch f_x 10 %: RMS riêng 2,44 / 2,29 px > 1 px, cả hai lần đặt bị loại; ảnh xám mờ: tương phản 20 < 30, "không xác định được góc O"; lề mép ảnh, khoảng cách bảng, độ cao tối thiểu: kiểm bằng cách hẹp ngưỡng trên ảnh chuẩn (ảnh tổng hợp khó chạm đúng một phép mà không chạm phép khác). Góc bảng tới θ 39,5° / 46,1°: nội tham ghi θ đã thấy nhỏ hơn thì có cảnh báo ngoại suy, lớn hơn thì không |
| Kết quả tổng hợp | không cờ: từ chối ghi; có cờ: nhãn `"synthetic": true` ở camera và tệp; `configs\` / `calibration\` luôn bị từ chối; tệp gốc có camera tổng hợp bị từ chối; kết quả "thật" (nội tham không có dấu tổng hợp) vẫn ghi được, basis "ĐO (…)" |
| Dòng lệnh với số kiểu Việt | `--place … 0,60 …`, `--square-mm 30,0`, `--board-z-m 0,0` cho đúng cùng tư thế như khi viết dấu chấm; `--square-mm 0` báo lỗi tiếng Việt, mã 2 |
| Ghi đè hai lần trong cùng một thời điểm (đồng hồ bị giữ cố định trong test) | tệp rig và ROI: mỗi bản cũ có một bản sao lưu riêng, không bản nào bị đè |
| Ảnh kiểm | hộp thân xe (từ v0) vẽ trắng khi nằm trong ảnh (camera thử nhìn về phía sau, đặt trước xe); trục x của xe đỏ, trục y xanh lá |
| Tệp rig ghi ra → `bev.load_rig_extrinsics` | tư thế trùng từng số; camera chưa đo và hộp thân xe chép nguyên từ v0 |
| Nội tham + tệp rig mới + ROI → `bev.load_rig` → `CameraCalibration.ground_to_pixel` của BEV chiếu góc bảng | lệch < 0,6 px so với góc thấy trên ảnh; lý do "ngoại tham giả định" không còn |
| Tinh chỉnh theo điểm ảnh so với `cv2.fisheye.solvePnP` | RMS giảm rất ít (0,5802 → 0,5799 px với nhiễu góc 0,4 px); lợi ích ở θ lớn CHƯA ĐO |
| Vùng dò được (script tạm, không lưu trong repo) | camera 0,12 m / 30° và 0,15 m / 45°, bảng A4 ô 20 mm và A3 ô 30 mm: dò được khi hàng góc gần cách chân camera 0,05–0,30 m (0,35 m với camera 0,15 m). Sai số một lần đặt ≤ 0,5 mm độ cao, ≤ 1,7 mm vị trí, ≤ 0,11° chúc |
| ROI: đa giác → PNG → `bev.read_gray` / `bev.load_rig` | trùng từng pixel; ROI sai cỡ bị BEV từ chối |
| ROI: đa giác cùng kiểu chồng nhau / lồng nhau (thêm tối 24/09/2026) | là hợp: chỗ chồng của hai đa giác loại vẫn bị loại; "bánh xe" lồng trong "thân xe" vẫn loại cả thân xe khi lưu |
| ROI trong BEV: mọi pixel báo FREE, loại nửa dưới ảnh | không ô FREE nào có tâm chiếu vào phần bị loại |
| Giao diện offscreen | vẽ đa giác bằng chuột (toạ độ khứ hồi đúng), lưu, từ chối ghi đè, mở lại; đổi cổng bỏ ảnh và đa giác cũ; luồng ngoại tham trọn vẹn, phiên lưu chạy lại được bằng dòng lệnh cho cùng tư thế; từ chối khi thiếu nội tham; camera sống là nguồn giả |
| Giao diện: đổi thông số sau khi tính (thêm tối 24/09/2026) | đổi cỡ ô / "Đã đo cỡ ô" / số góc hay nạp lại nội tham: nút ghi tắt, ghi bị từ chối, phiên lưu đúng thông số đã tính; đổi số góc (7×6, 6×9) trên ảnh tĩnh và camera sống giả: dò lại theo bảng mới, không dùng lại góc cũ, không mở lại camera; bảng 9×5: báo "LỖI … cols + rows chẵn", không thoát slot; lưu ROI khi còn đa giác vẽ dở hay khác cỡ nội tham: từ chối; ảnh đổi cỡ thì nạp lại nội tham theo cỡ mới; nội tham tổng hợp: ô "Ghi vào" không trỏ vào configs\ |

**Kiểm đột biến** (24/09/2026, trên bản sao ở thư mục tạm, không sửa repo): **28 đột biến** vào ba tệp mã, **27 bị test
bắt**. Ví dụ: đảo quy ước trục y của bảng, bỏ bước chọn theo màu, bỏ lọc "camera trên mặt bảng", ghép sai phép quay, bỏ
loại lần đặt lệch, bỏ kiểm RMS chung, bỏ tinh chỉnh theo điểm ảnh, bỏ độ dày tấm, bỏ chặn mất số đo, ghi quaternion sai
thứ tự, ghi đè im lặng (tệp rig và ROI), đảo thứ tự include/exclude, ghi mặt nạ ngược, lệch nửa điểm ảnh khi đổi toạ độ
chuột, giao diện ghi kết quả cũ, giữ ảnh của cổng trước. Đột biến sống sót duy nhất là tương đương. Nó ép cờ ghi đè của
thư viện, nhưng giao diện đã từ chối ghi đè trước khi gọi thư viện, nên hành vi không đổi. Bỏ cả hai chỗ thì test bắt được.

**Kiểm đột biến lần hai** (tối 24/09/2026, sau bản sửa rà soát, bản sao ở thư mục tạm, không sửa repo): **39 đột biến**,
**39 bị test bắt** (38 trong một lượt; đột biến thứ 39 — lệnh `check` in "ĐO" cho camera tổng hợp — chạy riêng trên mã
cuối). Gồm: tô mọi đa giác cùng kiểu bằng một lần `fillPoly` (lỗi cũ), tên sao lưu theo giây không giữ chỗ
(tệp rig và ROI), không vẽ hộp thân xe (ảnh giao diện và `xem_*.jpg`), đổi lại màu trục, bỏ từng chốt chặn kết quả tổng
hợp (mặc định, `configs\`, tệp gốc, nhãn camera, nhãn tệp, bộ thử trong `calibration\`), bỏ đọc dấu phẩy thập phân, bỏ bắt
lỗi cỡ bảng trên dòng lệnh, bỏ từng phép loại lần đặt (RMS riêng, khoảng cách, lề mép, tương phản, độ cao tối thiểu) và
cảnh báo θ, bỏ nối từng ô thông số bảng, khoá đánh số góc không có thông số bảng, không báo cỡ bảng mới cho camera sống,
dùng khung sống còn dò theo bảng cũ, bỏ bắt lỗi khi Tính, nạp lại nội tham không làm kết quả mất hiệu lực, vẽ nhãn theo
bảng cũ, không phân tích lại lần đặt, bỏ đổi ô "Ghi vào" khi nội tham tổng hợp, bỏ chặn lưu ROI khi còn đa giác vẽ dở /
khác cỡ nội tham, không nạp lại nội tham khi ảnh đổi cỡ, báo nhầm "bản cũ". Ba chốt chặn thứ hai của giao diện (so thông số
bảng của kết quả trong `write_rig`, trong nút ghi, và trong `save_session`) là tương đương khi các ô số đã làm kết quả mất
hiệu lực, nên không có đột biến riêng.

## 8. Chưa kiểm, giới hạn

- **Chưa chạy với camera thật**, ảnh MJPEG thật, ánh sáng và sàn thật. Chưa có `calibration/cam_p*.json` nào. Giao diện
  chưa từng mở camera thật; nhánh camera sống chỉ chạy với nguồn giả.
- **Sai số thước là nguồn sai số lớn nhất và CHƯA ĐO.** Trên ảnh tổng hợp, ±2,5 mm trên mỗi điểm đã cho sai số hướng camera
  tới 0,93° (20 lần bốc thăm). Muốn nhỏ hơn: đo cả bốn góc O, A, B, C, đặt bảng nhiều lần hơn, đo tới 1 mm. Sai số của
  vạch hệ xe (gốc dưới tâm trục sau, hướng trục x) đi thẳng vào mọi camera, và cũng CHƯA ĐO.
- Giả định sàn phẳng, bảng phẳng. Bảng cong hay sàn nghiêng làm sai tư thế mà RMS chưa chắc lộ ra.
- Camera thấp nên bảng chỉ dò được trong khoảng rất gần. Góc trục quang đo được chủ yếu từ vùng sàn gần, nên sai số ở xa
  (tới 2 m, tầm của BEV) phải kiểm bằng vật mẫu (BEV.md mục 8).
- Ảnh lật gương chỉ bị bắt nhờ nhiều lần đặt không khớp nhau, không có phép kiểm riêng.
- Không tự phát hiện camera bị xê dịch sau khi đo; đo lại sau mỗi lần gá lại hay va chạm.
- `vehicle_assumed` (kích thước xe, hộp thân xe) vẫn là giả định; ROI thân xe phải vẽ theo ảnh thật, không suy từ hộp này.
- Tệp rig TỔNG HỢP vẫn có `"measured": true`. *(Sửa 25/09/2026:)* `perception/bev.py` nay đọc khóa `synthetic` và dấu
  TỔNG HỢP của tệp nội tham, rồi ghi lý do "không dùng được" cho camera đó (test
  `test_bev_projects_board_corners_where_the_camera_saw_them`). Thêm vào đó vẫn có nhãn và việc cấm ghi vào `configs\` /
  `calibration\`.
- Nhánh camera sống khi đổi số góc chỉ chạy với nguồn giả; với camera thật CHƯA THỬ.
- Mọi ngưỡng (5 mm, 1 px, 4 px, 2 cm, 1°, lề ROI 2 px…) là ĐỀ XUẤT – CHỜ CHỐT.
- Chưa chạy gì trên laptop RTX 3050 Ti (máy nộp đồ án).
