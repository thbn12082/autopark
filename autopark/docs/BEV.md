# BEV chiếm chỗ từ AI nhiều camera (giai đoạn 2, bước 7) — 24/09/2026

> **Ghi công theo giấy phép dữ liệu:** mô hình AI và bài minh họa ở đây dùng **Valeo WoodScape Dataset**
> (<https://woodscape.valeo.com>). Giới hạn sử dụng: [GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md).

**Tình trạng (24/09/2026):** đã có phần mềm và kiểm thử trên rig tổng hợp. **Chưa chạy được trên camera của dự án**,
vì ba thứ còn thiếu:

- chưa camera nào được hiệu chuẩn (`calibration/cam_p*.json` chưa có);
- ngoại tham trong `configs/rig/camera_rig_extrinsics_v0.json` là **GIẢ ĐỊNH — CHƯA ĐO**;
- chưa có mặt nạ ROI cho camera dự án.

Mọi con số dưới đây là của rig tổng hợp hoặc ảnh WoodScape. Không con số nào là số đo sai số BEV trên sa bàn. Điều kiện
"vật mẫu xuất hiện tại vị trí có thể đối chiếu trên BEV" của kế hoạch mục 6 **chưa kiểm**.

Mã: [autopark/perception/bev.py](../autopark/perception/bev.py). Tệp rig:
[configs/rig/camera_rig_extrinsics_v0.json](../configs/rig/camera_rig_extrinsics_v0.json). Kiểm thử:
[tests/test_bev.py](../tests/test_bev.py).

## 1. Mô-đun làm gì

Mô-đun nhận kết quả AI của từng camera, tức bản đồ xác suất P(BLOCKED). Nó chiếu các bản đồ đó xuống mặt sàn quanh xe
và hợp nhất thành một `Costmap` trong hệ xe (x hướng trước, y sang trái, gốc trên sàn dưới tâm trục sau). Mỗi ô của
costmap có một trong ba giá trị UNKNOWN / FREE / OCCUPIED.

Mô-đun **không** làm các việc sau:

- không nối vào bàn thử, vào hợp nhất cảm biến hay vào planner;
- không lọc theo thời gian;
- không dựng ảnh ghép đẹp cho giao diện. Kế hoạch bước 7 tách ảnh ghép thành một đầu ra riêng; `bev.png` ở đây là ảnh để
  kiểm quy tắc và tọa độ.

**Đầu vào mỗi camera:**

- Bản đồ P(BLOCKED), độ phân giải bất kỳ nhưng **cùng tỉ lệ khung** với ảnh đã hiệu chuẩn. Bàn thử ghi
  `prob_blocked_p<cổng>.png` = P×255 ở cỡ hiển thị. Nếu tỉ lệ khác quá 1 % thì mô-đun từ chối, vì đó là mode camera khác.
- Một `CameraCalibration`: nội tham + ngoại tham trong hệ xe.
- Mặt nạ ROI (tùy chọn).

Mọi camera dùng chung một `GridSpec`.

**Đầu ra** (lệnh dòng lệnh ghi vào `runs/bev/<tên>/`):

| Tệp | Nội dung |
|---|---|
| `costmap.json` | Khóa `costmap`: đúng định dạng `costmap_to_dict`, đọc được bằng `fusion.layers.read_costmap_json`. Khóa `provenance`: bitmask nguồn gốc từng ô. Khóa `category`: phân loại từng ô. Thêm `usable_for_planning` và `unusable_reasons` |
| `stats.json` | Tham số, quy tắc, số ô theo loại, chồng lấn và xung đột giữa camera, từng camera (tư thế, nguồn nội tham, ROI, tỉ lệ pixel theo loại bằng chứng, số ô, thời gian, lý do bị bỏ), giả định |
| `bev.png` | Ô trái: phân loại ô. Ô phải: số camera thấy mỗi ô. Lệnh `synthetic` thêm ô "sự thật" bên trái. Trên ảnh, x hướng trước ở trên, y trái ở bên trái. Chữ trên ảnh là ASCII vì cv2 không vẽ được dấu |

## 2. Quy tắc

1. **Xác suất → bằng chứng, theo hai ngưỡng.** p ≤ `t_free` → FREE; p ≥ `t_blocked` → OCCUPIED; ở giữa → **không
   chắc chắn**, thành UNKNOWN. Pixel ngoài ROI hoặc NaN không có bằng chứng. Bằng ngưỡng thì được tính: p = t_free là FREE,
   p = t_blocked là OCCUPIED. Xác suất được phóng về cỡ ảnh đã hiệu chuẩn **trước** khi so ngưỡng: nội suy tuyến tính khi
   phóng to, INTER_AREA khi thu nhỏ. PNG lưu P×255 nên giá trị quanh ngưỡng có thể lệch tới 1/510.
   - Mặc định `t_free = 0,15`: ngưỡng thiên về an toàn chọn trên val WoodScape theo F2
     ([HUAN_LUYEN.md](../../HUAN_LUYEN.md) mục 10). Chỉ pixel mà mô hình cho P(BLOCKED) ≤ 0,15 mới được gọi là trống.
   - Mặc định `t_blocked = 0,50`: argmax.
   - Cả hai ngưỡng **chưa kiểm trên ảnh sa bàn**.
2. **Chiếu xuống mặt sàn** bằng `costmap.project_labels`, mô-đun này không bị sửa ([costmap.py](../autopark/perception/costmap.py)).
   - Tâm mỗi ô được chiếu vào ảnh, không nghịch đảo đa thức.
   - Nhìn từ camera theo từng phương vị, mọi ô **sau** ô OCCUPIED đầu tiên là UNKNOWN (bị che).
   - Ô xa camera hơn `max_range` là UNKNOWN.
3. **Lưới mịn.** Mỗi ô ra được chia thành `supersample × supersample` ô con (mặc định 2 × 2) và chiếu ở lưới mịn đó.
   Vì `project_labels` chỉ lấy một pixel cho một tâm ô, lưới mịn giảm khả năng một pixel quyết định cả ô.
   - **Gỡ FREE theo chiều ngược (thêm 24/09 sau rà soát).** Chỉ đọc pixel ở tâm ô con thì chưa đủ. Một vật mảnh nằm
     giữa các tâm có thể để ô của nó FREE dù camera thấy rõ vật. Ví dụ: cột 2 cm cách camera 0,25 m, rộng ≈ 25 px trong
     ảnh. Vệt OCCUPIED khi đó rơi sang ô xa hơn một ô. Vì vậy có thêm một lượt pixel → sàn. Mỗi pixel BLOCKED hoặc
     không chắc (trong ROI, không NaN) được chiếu xuống sàn ở tâm và bốn góc pixel. Ô con nào có một điểm như vậy rơi
     vào thì **không được FREE ở camera đó**, mà thành UNKNOWN.
   - Lượt này **không** đặt OCCUPIED. Điểm sàn của một pixel là điểm xa nhất tia của nó có thể chạm, nên nó không chứng
     minh được có vật ở đó. Pixel mặt bên của vật cao mà đặt OCCUPIED thì sẽ kéo vệt theo tia. Tập OCCUPIED và phép che
     khuất của `project_labels` vì vậy giữ nguyên.
   - Mỗi camera chỉ gỡ FREE của chính nó (xem quy tắc 4).
   - Kết quả quét cột mảnh trong ô tâm (0,575; 0,025) trước camera p1, 75 vị trí mỗi cỡ, bản đồ xác suất cỡ gốc:
     số lần ô chứa cột vẫn FREE **trước bản sửa: 5/75 (cột 2 cm), 14/75 (1,5 cm), 44/75 (1 cm); sau: 0/75 cả ba cỡ**.
   - Cái giá: FREE co lại tối đa nửa pixel quanh mọi vùng BLOCKED/không chắc. Trên rig tổng hợp, FREE giảm từ 4 185 xuống
     4 113 ô (−1,7 %). Chỉ gỡ theo tâm pixel thì còn 4 173 ô, nhưng khi đó pixel nằm vắt qua biên ô con không gỡ được FREE
     ở ô con bên kia.
4. **Hợp nhất camera, ở lưới mịn rồi mới gộp.**
   - Ô con là OCCUPIED nếu **có** camera nói OCCUPIED. Ô con là FREE nếu có camera thấy trống chắc chắn và **không**
     camera nào nói OCCUPIED.
   - Ô ra là OCCUPIED nếu có ô con OCCUPIED, FREE chỉ khi **mọi** ô con FREE, còn lại UNKNOWN.
   - Có hai hệ quả. Ô mà một camera thấy trống nhưng camera khác nói có vật thì là OCCUPIED. Ô nằm trên biên trường nhìn
     của hai camera, mỗi camera thấy một phần và mọi phần đều trống, thì vẫn là FREE. Bản đầu gộp từng camera trước khi
     hợp nhất; khi đó các ô này thành UNKNOWN thừa, thấy rõ trên ảnh tổng hợp.
   - "Không chắc" của một camera **không** phủ quyết FREE chắc chắn của camera khác.
5. **Camera thiếu dữ liệu** (không có xác suất, khung nghi hỏng, lệch thời gian, chưa hiệu chuẩn khi chạy
   `--skip-uncalibrated`) không góp gì. Vùng chỉ nó thấy giữ UNKNOWN, **không bao giờ mặc định FREE**. Lý do bị bỏ ghi ở
   `stats.json`.
6. **Dưới thân xe** luôn là UNKNOWN. Hộp thân xe lấy từ `vehicle_assumed` của tệp rig, nới thêm `ego_margin_m`.
7. **Nguồn gốc từng ô:** bốn bitmask uint16, bit i là `cameras[i]`. Camera không dùng vẫn giữ bit của mình, và bit đó
   luôn bằng 0.
   - `seen_by`: camera thấy ít nhất một ô con của ô đó, không bị che.
   - `free_by`: camera nói FREE ở ít nhất một ô con.
   - `occupied_by`: camera nói OCCUPIED ở ít nhất một ô con.
   - `in_view_by`: ô nằm trong trường nhìn, trong tầm và trong ROI của camera, kể cả khi bị che.

   Xung đột được tính riêng. Đó là ô con mà một camera nói OCCUPIED, camera khác nói FREE. Số xung đột đếm theo từng cặp
   camera ở `stats.json` → `overlap.conflicts_by_pair`. Nhiều ô xung đột dọc biên chồng lấn thường là dấu hiệu ngoại tham
   hoặc nội tham lệch.
8. **Phân loại ô** (chỉ để thống kê và vẽ; với lập đường, mọi loại UNKNOWN đều bị chặn):

| Loại | Giá trị costmap | Nghĩa |
|---|---|---|
| free | FREE | ít nhất một camera thấy trống chắc chắn ở mọi ô con (không pixel BLOCKED/không chắc nào của camera đó rơi vào), không camera nào nói OCCUPIED |
| occupied | OCCUPIED | có camera có pixel p ≥ t_blocked chiếu vào ô (chỉ phía chân vật hướng về camera, xem mục 3) |
| uncertain | UNKNOWN | có camera thấy ô nhưng không đủ chắc, hoặc chỉ thấy một phần ô |
| occluded | UNKNOWN | ô trong trường nhìn, tầm và ROI của camera nhưng bị vật OCCUPIED gần hơn che |
| unseen | UNKNOWN | ngoài trường nhìn, quá tầm, ngoài ROI của mọi camera, hoặc camera thấy nó thiếu dữ liệu |
| ego | UNKNOWN | dưới thân xe |

**Khi nào costmap bị đánh dấu không dùng được:** khi đó `usable_for_planning = false` và `stamp.valid = false`, nên
`Costmap.blocked` chặn mọi ô. Điều này xảy ra khi có camera được dùng mà:

- ngoại tham chưa có `"measured": true`;
- chưa có ROI;
- nội tham có `acceptance.all_pass = false`. Test `test_failed_intrinsics_acceptance_alone_blocks_planning` kiểm riêng
  lý do này. Nửa đối chứng: ngoại tham ghi đo + ROI + `all_pass` true thì `stamp.valid` là true. Nửa kia: chỉ đổi
  `all_pass` của một camera thành false thì costmap bị chặn, với đúng một lý do.

Ngoài ra còn các trường hợp: không camera nào có dữ liệu, dữ liệu tổng hợp, ảnh WoodScape. Hiện nay **mọi** BEV từ tệp rig
v0 đều không dùng được. Việc nối AI vào lập đường còn chờ quyết định về giấy phép WoodScape
([GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md)). `stats.json` ghi điều đó ở `caveats`, không tự chặn.

## 3. Giả định mặt sàn phẳng và giới hạn với vật cao

Phép chiếu giả định mặt sàn phẳng z = 0 trong hệ xe, nên **chỉ đúng cho điểm thuộc mặt sàn** (kế hoạch mục 6, "lưu ý cần
kiểm chứng").

- **Pixel của vật cao** (mặt bên, nóc) chiếu xuống sàn sẽ rơi **xa hơn** chân vật, dọc theo tia nhìn. Quy tắc che khuất
  giữ ô OCCUPIED gần camera nhất theo mỗi phương vị và cắt phần kéo dài phía sau thành UNKNOWN. Kết quả trên rig tổng hợp:
  hộp cao 0,15 m chỉ có cạnh chân hướng về camera là OCCUPIED; lòng hộp và phần sau là UNKNOWN (bị che). Test
  `test_occupied_only_at_the_box_base_not_a_smear` kiểm rằng không ô OCCUPIED nào nằm ngoài hộp quá 1 ô. Đột biến bỏ quy
  tắc che khuất làm test này hỏng.
- **Đó không phải footprint chính xác.** Các trường hợp sau vẫn sai:
  - vật nhô ra như mặt bàn hay cản xe: biên OCCUPIED rơi ở chỗ tia chạm phần thấp nhất nhìn thấy, không phải chân vật;
  - chân vật bị che bởi vật khác;
  - vật mà mô hình chỉ gọi BLOCKED một phần;
  - sàn nghiêng, mép thảm, cáp nằm trên sàn;
  - vật mảnh ở xa, nơi một pixel phủ hơn hai ô con (từ ≈ 1,5 m trên rig giả định). Lượt gỡ FREE chỉ chiếu tâm và bốn
    góc pixel, nên có thể sót ô con ở giữa. Khi đó tâm ô con thường đọc chính pixel ấy, nhưng điều này chưa kiểm bằng
    test.

  Phương pháp xác định biên tiếp xúc, độ sâu hay vùng không chắc chắn **CHƯA CHỌN, CHƯA ĐÁNH GIÁ**.
- **Độ phân giải mặt sàn giảm nhanh theo khoảng cách.** Bảng dưới là số **tính** trên rig giả định với ống kính danh
  định (ρ = f·θ, 130° chéo trên 640×480). **Chưa đo** trên camera thật.

| Khoảng cách dọc hướng nhìn | 0,5 m | 1,0 m | 1,5 m | 2,0 m | 3,0 m |
|---|---:|---:|---:|---:|---:|
| Camera trước/sau (cao 0,12 m, chúc 30°): cm mặt sàn theo bán kính / pixel | 0,6 | 2,4 | 5,4 | 9,5 | 21,3 |
| Camera hông (cao 0,15 m, chúc 45°) | 0,5 | 1,9 | ngoài ảnh | ngoài ảnh | ngoài ảnh |

  Vì vậy `max_range` mặc định là 2 m cho rig (lưới 6 × 6 m, ô 5 cm). Ở 2 m một pixel đã phủ gần hai ô. Test xung đột gặp
  đúng giới hạn này: ở ≈ 1,6 m, một vết BLOCKED phẳng rộng 5 cm có thể rơi sang ô bên cạnh. Mô-đun chưa có tiêu chí
  "độ phân giải tối thiểu" cho từng ô, chỉ có `max_range`.

## 4. Tệp ngoại tham v0 và bộ nạp rig

`configs/rig/camera_rig_extrinsics_v0.json` (`"format": "autopark.camera_rig_extrinsics/0"`) có
`"status": "GIẢ ĐỊNH — CHƯA ĐO"`. Mỗi camera có `"measured": false` và một dòng `basis` giải thích con số.

Các số đó đặt tay cho một xe 1/12 ≈ 0,40 × 0,20 m, ống kính 130° (số nhà bán). Kích thước xe này **khác**
`configs/vehicle_default.json` (0,31 × 0,14 m). Cả hai đều là giả định; chưa có số đo MN300.

| Cổng | Hướng (CHƯA CHỐT) | Vị trí x, y, z (m) | yaw | chúc xuống | Ghi chú |
|---|---|---|---:|---:|---|
| 1 | trước | 0,33; 0; 0,12 | 0° | 30° | mép trước thân xe giả định |
| 2 | sau | −0,07; 0; 0,12 | 180° | 30° | mép sau |
| 3 | trái | 0,13; 0,10; 0,15 | 90° | 45° | giữa sườn trái |
| 4 | phải | 0,13; −0,10; 0,15 | −90° | 45° | giữa sườn phải |

- **Gán cổng → hướng CHƯA CHỐT.** [usb_topology.md](usb_topology.md) ghi rằng việc gán hướng sẽ làm theo cổng khi có
  gá. Thứ tự trong bảng chỉ là chỗ giữ chỗ.
- **Quy ước góc.** Góc yaw là hướng trục quang chiếu xuống sàn, dương ngược chiều kim đồng hồ. Góc chúc đo dưới mặt phẳng
  ngang. Góc roll quay quanh trục quang. Khi có số đo, camera có thể ghi thẳng `quaternion_xyzw` (camera → xe, giống
  WoodScape) thay cho ba góc. `rig_rotation` được kiểm theo cùng quy ước với phép kiểm WoodScape của
  `test_perception_calibration.py`.
- Kế hoạch gọi tệp này là `camera_rig_extrinsics.yaml`. Dự án dùng JSON vì `.venv` và `.venv-train` không có thư viện
  YAML (kiểm 24/09/2026).
- **Bộ nạp** `load_rig()` ghép nội tham `calibration/cam_p<cổng>.json` (hoặc `cam_p<cổng>_<W>x<H>.json` cho mode khác,
  qua `fisheye_calib.load_intrinsics`) với ngoại tham của tệp rig. Cỡ khung lấy từ `meta.json` của bộ ảnh. Nếu **thiếu
  tệp nội tham, hoặc tệp không nạp được, bộ nạp từ chối và liệt kê mọi tệp thiếu**: không có nội tham giả định cho
  camera thật. Tùy chọn `--skip-uncalibrated` bỏ camera đó; vùng của nó thành UNKNOWN và lý do được ghi lại.

## 5. Cách chạy

Chạy từ `autopark/`. Mỗi lệnh viết trên một dòng để dán được vào PowerShell; dấu nối dòng `^` chỉ dùng được trong
cmd.exe.

```powershell
# 1) Rig tổng hợp: 4 camera ảo (tư thế của tệp rig v0, ống kính danh định), hai hộp và một dải "không chắc".
#    Không cần dữ liệu. Thử camera thiếu: thêm --drop 2 (số cổng) hoặc --drop p2; tên lạ bị từ chối.
.\.venv\Scripts\python.exe -X utf8 -m autopark.perception.bev synthetic

# 2) Bộ ảnh bàn thử (nút "Chụp bộ ảnh" của rig_app): prob_blocked_p*.png + cam_p*.png + meta.json.
#    Từ chối khi chưa có calibration/cam_p*.json. Đó là tình trạng ngày 24/09/2026.
#    Tùy chọn: --extrinsics configs/rig/camera_rig_extrinsics_v0.json, --calibration-dir calibration,
#    --roi-dir <thư mục có roi_p<cổng>.png>, --max-skew-ms 100, --skip-uncalibrated, --out runs/bev/<tên>.
.\.venv\Scripts\python.exe -X utf8 -m autopark.perception.bev snapshot runs/rig_snapshots/<ngày_giờ>

# 3) Ảnh WoodScape với hiệu chuẩn riêng của từng ảnh (datasets/woodscape_metadata/calibration.zip) và ROI
#    configs/roi/woodscape_v1. Chạy mô hình cần torch (.venv-train); hoặc đưa --prob (P×255, cùng thứ tự).
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.bev woodscape --image datasets/training/woodscape/rgb_images/00000_FV.png --checkpoint runs/ai_woodscape_rtx4000_v1/best.pt
```

`<ngày_giờ>` là tên thư mục bộ ảnh, ví dụ `20260923_165138_661`. Cấu hình sai thì lệnh in `LỖI: …` và thoát mã 2, không
in traceback. Các trường hợp: tệp ngoại tham thiếu hay sai khối `vehicle_assumed`; mã ảnh WoodScape không có trong
`calibration.zip` (ảnh sa bàn phải dùng lệnh `snapshot`); kho hiệu chuẩn không có hoặc không phải zip; `--drop` có tên
lạ.

**Tùy chọn chung:**

| Tùy chọn | Mặc định rig | Mặc định WoodScape |
|---|---|---|
| `--grid XMIN XMAX YMIN YMAX RES` | −3 3 −3 3 0,05 | −10 15 −10 10 0,1 |
| `--t-free` | 0,15 | 0,15 |
| `--t-blocked` | 0,50 | 0,50 |
| `--max-range` (m) | 2 | 12 |
| `--supersample` | 2 | 2 |

**Riêng với bộ ảnh bàn thử:**

- **Khung hỏng thì camera bị bỏ.** Lý do: khung bị cắt mà tới được AI thì vùng hỏng bị gọi gần hết là FREE, ở cả
  ngưỡng 0,5 và 0,15 ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 2.4, cập nhật 24/09). Đó là lỗi theo hướng
  không an toàn. Từ bản sửa 24/09, phép kiểm chạy trên chính `cam_p<cổng>.png`, cùng bộ dò với nguồn camera và
  `labels.frame_damage`. Camera bị bỏ khi có một trong các dấu hiệu:
  - `truncated_rows`: đáy khung do bộ giải mã tô;
  - `torn_bands`: dải xé giữa ảnh, trong khi đáy có thể nguyên vẹn;
  - `bottom_repeat_share` > 0,2. Số này lấy từ `meta.json`. Bộ ảnh trước 24/09 không ghi nó, nên được tính lại trên khung
    bằng cùng hàm bàn thử dùng.

  Nếu không có ảnh (hoặc không giải mã được) **và** `meta.json` cũng không ghi `bottom_repeat_share`, thì không kiểm được
  gì. Khi đó camera bị bỏ, không mặc định "khung tốt". Có số trong `meta.json` mà không có ảnh thì chỉ xét được số đó.
  Trường hợp này ghi `image_checked: false` ở `stats.json` → `frame_damage_check`, và không phát hiện được dải xé.
  Bản trước chỉ đọc `bottom_repeat_share` của `meta.json`: bộ ảnh cũ không có khóa đó thì camera được giữ mà không xét
  gì (mục 6).
- Mô-đun giữ nhóm camera đông nhất có mọi stamp nằm trong cửa sổ `--max-skew-ms` và bỏ các camera còn lại. Nếu hai nhóm
  đông bằng nhau thì lấy nhóm mới hơn.
- Stamp của costmap là khung **cũ nhất** trong các camera được dùng, trên đồng hồ `perf_counter` của bàn thử.

**WoodScape có một giới hạn riêng.** Mỗi mã khung chỉ có **một** camera (kiểm 24/09: 8 234 mã, mỗi mã một tệp). Vì vậy
không có bộ bốn camera đồng bộ. Lệnh `woodscape` nhận nhiều ảnh, nhưng khi đó ghi rõ đó là các khung khác thời điểm, và
costmap bị đánh dấu không dùng được.

## 6. Đã chạy gì (24/09/2026, máy bàn i9-14900, `.venv` / `.venv-train`)

Thư mục ra của các lần chạy này nằm ngoài repo, vì `runs/` bị git-ignore. Chạy lại bằng các lệnh ở mục 5.

Các số dưới đây đo lại sau bản sửa 24/09 (gỡ FREE theo chiều ngược, mục 2). Số của bản trước ghi trong ngoặc.

- **Rig tổng hợp** (`synthetic`, lưới 120 × 120 ô):
  - đủ 4 camera: free 4 113 (4 185), occupied 18, uncertain 553 (481), occluded 708, unseen 8 972, ego 36;
  - bỏ p2 (camera sau, `--drop 2`): free 2 939 (2 953); vùng sau xe thành unseen (10 390).
  - Trên ảnh `bev.png`:
    - hộp trước (chỉ camera trước thấy): chỉ cạnh chân gần camera là OCCUPIED, phía sau là một nêm occluded kéo tới
      tầm 2 m;
    - dải xác suất 0,30 sau xe: uncertain;
    - các vệt uncertain chéo gần bốn góc xe: ô chỉ được thấy một phần, vì giữa trường nhìn trước và hông có một nêm mù
      hẹp (ô unseen sát góc xe);
    - chỉ 164 ô được hai camera cùng thấy. Với tư thế giả định, vùng chồng lấn rất hẹp.
- **Thời gian `build_bev`**, 4 camera, lưới 6 × 6 m ô 5 cm, không kiểm tải máy lúc đo. "Lần đầu" gồm việc dựng bảng
  pixel → ô con của lượt gỡ FREE. Bảng này chỉ phụ thuộc hiệu chuẩn, lưới và tầm, nên được nhớ giữa các khung
  (`lru_cache`, 8 mục, ≈ 2,5 MB mỗi camera 640×480). "Tốt nhất / trung vị" là của 7 lần sau đó:

  | supersample | lần đầu | tốt nhất | trung vị | bản trước (tốt nhất / trung vị) |
  |---:|---:|---:|---:|---:|
  | 1 | 261,5 ms | 26,1 ms | 27,7 ms | 29,5 / 30,7 ms |
  | 2 (mặc định) | 318,5 ms | 67,9 ms | 69,5 ms | 81,9 / 84,1 ms |
  | 3 | 381,7 ms | 131,4 ms | 135,8 ms | 136,6 / 148,4 ms |

  Ô 10 cm, tốt nhất: 13,0 / 20,2 / 32,5 ms ở supersample 1 / 2 / 3 (bản trước: 13,8 / 22,2 / 38,2 ms). Lượt gỡ FREE, khi
  bảng đã có sẵn, không làm chậm thấy được. Chênh lệch với bản trước nằm trong dao động giữa các lần đo, vì tải máy
  không được kiểm. Ở supersample 2 vẫn **chậm hơn một chu kỳ khung** (≈ 42 ms ở 24 khung/s). Mã chưa tối ưu: mỗi camera
  chiếu hai lượt và tính vùng nhìn riêng. Lệnh dòng lệnh chỉ chạy một lần, nên thời gian nó in gồm cả việc dựng bảng
  (`synthetic`: 365,8 ms). Chưa đo trên laptop RTX 3050 Ti (máy nộp đồ án).
- **WoodScape `00000_FV`** với checkpoint tham chiếu `ai_woodscape_rtx4000_v1` (lưới 200 × 250 ô 0,1 m, tầm 12 m):
  - free 7 904 (bản trước 8 055), occupied 64, uncertain 3 424 (3 273), occluded 9 108, unseen 29 500;
  - phần BEV, không tính suy luận: 345,9 ms cho lần chạy duy nhất. Con số này gồm việc dựng bảng pixel → ô con cho ảnh
    1280×966. Bản trước đo 86 ms. Thời gian khi bảng đã có sẵn chưa đo trên ảnh này;
  - nhìn bằng mắt: mặt đường phía trước là FREE, xe phía trước và vỉa hè cắt vùng FREE, phía sau chúng là occluded.

  Đây là minh họa trên xe của Valeo. Nó **không** phải phép đo sai số BEV: không có nhãn mặt sàn để so.
- **WoodScape ba ảnh khác thời điểm** (`00000_FV`, `00028_RV`, `00140_MVL`): chạy được, và costmap bị đánh dấu không đồng
  bộ. **Có một lỗi thấy được:** ảnh MVL cho một đường cong mảnh OCCUPIED/occluded ở phía phải xe, tức phía sau mặt phẳng
  ảnh của camera trái, ở θ gần 90–100°. Đó là các pixel sát biên ROI thân xe mà `configs/roi/woodscape_v1/roi_MVL.png`
  không loại hết. Chưa sửa. Với camera dự án, ROI phải dựng kỹ ở mép thân xe. Demo WoodScape cũng **không có hộp thân
  xe**: `vehicle_info.zip` chứa ảnh, không chứa kích thước xe.
- **Bộ ảnh thật** `runs/rig_snapshots/20260923_165138_661`: lệnh `snapshot` **từ chối**, liệt kê bốn tệp
  `calibration/cam_p1..4.json` còn thiếu, thoát mã 2 và không ghi tệp nào. Đúng như thiết kế: chưa có hiệu chuẩn.
- **Bộ lọc khung hỏng trên hai bộ ảnh thật.** Để thấy camera nào bị bỏ, lần chạy này dùng nội tham **danh định** đặt
  trong thư mục tạm, ngoài repo. Đó không phải hiệu chuẩn, và BEV ra từ lần chạy này không có nghĩa gì.
  - `20260923_145753_910` (1280×720, qua hub, trước khi `meta.json` ghi `bottom_repeat_share`): **bỏ p1 và p4**. p1 có
    352/720 dòng đáy do bộ giải mã tô, p4 có 328/720; `bottom_repeat_share` tính lại trên khung là 1,0. p2 (0,058) và
    p3 (0,012) được dùng. Bản trước dùng cả bốn camera và không ghi lý do gì.
  - `20260923_165138_661` (640×480, có số trong `meta.json`): cả bốn camera qua được kiểm. Không có dòng bị tô, không có
    dải xé, số lấy từ `meta.json` (0,026–0,080).

## 7. Kiểm thử

`tests/test_bev.py` có 32 test (22 của bản đầu, thêm 10 sau đợt rà soát 24/09). Chạy ngày 24/09 sau bản sửa:

- `.venv`: 32 đạt. Cùng các test liên quan `test_perception_calibration`, `test_fisheye_calib`, `test_fusion`,
  `test_fusion_demo`, `test_lidar_bench_map`: 92 đạt, 0 lỗi. Thêm `test_labels` và `test_phase1_sources` (hai tệp chứa
  bộ dò khung hỏng mà BEV nay dùng lại): tổng 151 đạt, 1 bỏ qua (test cần torch của `test_labels`), 0 lỗi.
- `.venv-train`: 32 đạt. Cùng `test_perception_calibration`, `test_fisheye_calib`, `test_labels`,
  `test_phase1_sources`: 128 đạt, 0 lỗi.

Rig tổng hợp dùng tư thế của tệp v0 và ống kính danh định. Mỗi camera có bản đồ xác suất dựng bằng cách chiếu **sự thật**
của cảnh vào ảnh: tia qua từng pixel được xét xem chạm hộp hay chạm mặt sàn trước. Cảnh có hai hộp và một dải
p = 0,30, và bản đồ ở cỡ hiển thị 480×360. Hướng tính này ngược với BEV (tâm ô → pixel). Test cũng có phép kiểm tầm nhìn
độc lập: đoạn thẳng từ camera tới điểm sàn có cắt hộp không. Các test kiểm:

- hai ngưỡng và giá trị đúng bằng ngưỡng; NaN và ROI không phải "không chắc"; từ chối ngưỡng sai;
- xác suất ở cỡ bất kỳ cùng tỉ lệ: kết quả trùng > 98 % ô với cỡ gốc; khác tỉ lệ thì từ chối;
- OCCUPIED chỉ trong hộp ± 1 ô; mặt hộp hướng về camera ≥ 80 % ô OCCUPIED; không ô FREE nào trong hộp;
- FREE chỉ ở chỗ trống thật và có camera thấy (± 1 ô); vùng trống thấy rõ ≥ 95 % là FREE;
- ô nửa trống nửa không chắc thì là UNKNOWN (FREE chỉ khi mọi ô con FREE); dải không chắc chắn là UNKNOWN/uncertain;
- **(mới)** cột 2 × 2 cm cao 20 cm nằm giữa các tâm ô con, cách camera 0,25 m: ô chứa cột không FREE (uncertain), ô
  sau nó OCCUPIED, hai ô cạnh ngang vẫn FREE. Quét thêm 12 vị trí với cột 1 / 1,5 / 2 cm: không lần nào FREE;
- **(mới)** một pixel BLOCKED duy nhất có tâm trong ô con A, góc gần rơi sang ô con B: B không còn FREE dù tâm của B đọc
  một pixel trống; ô con lệch ngang 3 ô vẫn FREE; gỡ tối đa 5 ô con;
- ô sau hộp là occluded (sự thật độc lập: không camera nào thấy); dưới xe là ego; ngoài tầm là unseen;
- **(mới)** hộp thân xe giả đặt nơi p1 thấy sàn trống: mọi ô trong hộp thành UNKNOWN/ego, phần còn lại không đổi. Với
  tư thế v0 không camera nào thấy trọn một ô dưới thân xe, nên test cũ không kiểm được quy tắc này;
- thiếu camera sau: vùng sau xe từ FREE thành unseen, phần còn lại không đổi;
- xung đột chồng lấn: p1 báo nhầm một mảng phẳng, p3 thấy trống → OCCUPIED, có nguồn gốc và cặp xung đột;
- **(mới)** quy tắc hợp nhất trên hai camera dựng tay, không qua phép chiếu: OCCUPIED thắng FREE; "không chắc" không phủ
  quyết FREE; hai nửa thấy trống bởi hai camera → FREE; thiếu một ô con → UNKNOWN; cặp xung đột và bitmask;
- bitmask nguồn gốc khớp trạng thái; hợp đồng `Costmap`; đặt vào `CameraSemanticLayer`; stamp không hợp lệ thì mọi ô bị
  chặn;
- tệp rig v0 ghi GIẢ ĐỊNH — CHƯA ĐO ở mọi camera;
- bộ nạp từ chối khi thiếu nội tham, liệt kê đủ bốn tệp, và mode khác thì tìm tệp `_WxH`;
- lệnh `snapshot` từ đầu đến cuối: bộ ảnh giả với bốn `cam_p*.json` sinh bằng `fisheye_calib.woodscape_intrinsics`. Kiểm
  việc bỏ camera hỏng, lệch thời gian, thiếu xác suất; kiểm từ chối khi thiếu hiệu chuẩn hoặc thiếu `meta.json`;
- **(mới)** khung hỏng xét trên ảnh: bộ ảnh kiểu cũ (meta không ghi `bottom_repeat_share`), khung nhiễu ngẫu nhiên, đáy
  p3 tô bằng khối 8×8 lặp → bỏ p3 (`truncated_rows`, số tính lại trên khung); xóa `cam_p2.png` → bỏ p2 ("không kiểm
  được"). Dải xé giữa ảnh p2 với số trong meta thấp (0,05) → bỏ p2 (`torn_bands`);
- **(mới)** chỉ riêng `acceptance.all_pass = false` của một camera đủ để chặn lập đường, có đối chứng dùng được;
- lệnh `synthetic`, **(mới)** `--drop 2` và `--drop p2` cho cùng kết quả, số FREE nhỏ hơn khi đủ bốn camera; tên lạ →
  mã 2;
- **(mới)** lỗi cấu hình thành `LỖI: …` mã 2, không traceback, không ghi thư mục ra: khối `vehicle_assumed` thiếu
  trường / là danh sách / có chữ / có số âm; tệp rig không phải đối tượng; mã ảnh không có trong `calibration.zip`, tệp
  hiệu chuẩn thiếu trường, kho không có, kho không phải zip (dùng zip tạm, không cần dataset);
- **(mới)** không lệnh nào trong tài liệu này và docstring mô-đun dùng dấu nối dòng `^`;
- lệnh `woodscape` với `--prob` trên hiệu chuẩn thật của `00000_FV`: ô FREE nằm trong θ ≤ 100° và trong tầm, rơi vào
  vùng dùng được của ROI; bỏ ROI thì thêm ô "trống" giả. Test này bỏ qua nếu thiếu dữ liệu;
- thời gian 4 camera trên lưới 6 × 6 m ô 5 cm: cận trên 1 s, lỏng để chạy được trên máy yếu. Số đo ở mục 6.

**Kiểm đột biến.** Mỗi đột biến được nạp như một bản mã đã sửa trong bộ nhớ của tiến trình kiểm; tệp `bev.py` trên đĩa
không bị sửa. Lần chạy lại ngày 24/09 sau bản sửa có 23 đột biến, **cả 23 bị bắt**.

Mười một đột biến của bản đầu, chạy lại trên mã mới:

- "không chắc" thành FREE;
- FREE thắng OCCUPIED khi hợp nhất;
- ô unseen thành FREE;
- bỏ quy tắc che khuất: thay `project_labels` bằng bản không che khuất, trong mô-đun đột biến;
- FREE khi chỉ một ô con FREE;
- bỏ hộp thân xe;
- bỏ lọc lệch thời gian;
- bỏ lọc khung hỏng;
- bỏ kiểm tỉ lệ khung;
- không báo thiếu ROI;
- camera thiếu thì mặc định FREE.

Lần chạy lại lộ ra hai đột biến **lọt** qua bộ test cũ:

- "FREE thắng OCCUPIED". Sau bản sửa, các ô xung đột trong test xung đột không còn được p3 thấy trống ở mọi ô con, nên
  đột biến không tạo ra ô FREE nào để bắt.
- "bỏ hộp thân xe" trong dạng giữ nhãn ego nhưng không đặt UNKNOWN. Với tư thế v0, không camera nào thấy trọn một ô dưới
  thân xe.

Hai test mới bắt cả hai: test hợp nhất dựng tay, và test hộp thân xe giả.

Mười hai đột biến mới:

- không gỡ FREE;
- gỡ FREE chỉ theo tâm pixel;
- gỡ FREE thành OCCUPIED;
- lọc khung hỏng chỉ theo số của meta như bản cũ;
- không xét dải xé;
- không xét đáy bị tô;
- không tính lại số trên khung;
- không kiểm được vẫn giữ camera;
- bỏ lý do `acceptance`;
- `--drop` không chuẩn hóa;
- WoodScape để lộ traceback;
- khối `vehicle_assumed` để lộ traceback.

## 8. Còn thiếu (theo thứ tự cần làm)

1. **Hiệu chuẩn nội tham bốn camera** ([HIEU_CHUAN_CAMERA.md](HIEU_CHUAN_CAMERA.md)). Không có thì lệnh `snapshot`
   không chạy.
2. **Gá camera, chốt gán cổng → hướng, đo ngoại tham.** Chưa có công cụ. Một hướng là `cv2.fisheye.solvePnP` với bảng
   đặt trên sàn ở vị trí đo được ([TONG_HOP_DU_AN.md](../../TONG_HOP_DU_AN.md) mục 5.4). Ghi kết quả vào một tệp rig mới
   với `"measured": true` và `quaternion_xyzw`; giữ v0 làm hồ sơ.
3. **Mặt nạ ROI cho camera dự án** (`roi_p<cổng>.png`): loại thân xe, dây, viền ống kính.
4. **Đo sai số BEV** (kế hoạch mục 6, bước 8): đặt vật mẫu ở vị trí đo bằng thước ở trước, sau, hông và vùng giáp ranh;
   so với BEV; lập báo cáo sai số và sơ đồ vùng quan sát.
5. Chọn và đánh giá phương pháp **biên tiếp xúc** của vật cao (mục 3). Chọn **tiêu chí độ phân giải** thay cho
   `max_range` cố định.
6. **Tốc độ:** ≈ 68–70 ms cho 4 camera ở mặc định (đo lại 24/09; bản trước 82 ms, không kiểm tải máy) vẫn chậm hơn một
   chu kỳ khung. Khung đầu tiên thêm ≈ 250–380 ms để dựng bảng pixel → ô con. Cần tối ưu, hoặc chạy supersample 1 / ô
   lớn hơn, trước khi đưa vào bàn thử. Chưa đo trên laptop RTX 3050 Ti.
7. **Nối vào bàn thử / hợp nhất** (`CameraSemanticLayer`, kế hoạch giai đoạn 3): chưa làm. Chờ các mục trên, và chờ
   quyết định giấy phép WoodScape cho việc nối AI vào lập đường.
8. Lọc theo thời gian, bù chuyển động xe giữa các camera: chưa có. Mọi stamp là lúc khung tới máy, không phải lúc phơi
   sáng.
9. AI **chưa từng được chấm trên ảnh sa bàn**. Hai ngưỡng 0,15 / 0,50 chưa kiểm trên sa bàn. Mọi lỗi của mô hình đi
   thẳng vào BEV.
