# BEV chiếm chỗ từ AI nhiều camera (giai đoạn 2, bước 7) — 24/09/2026

> **Ghi công theo giấy phép dữ liệu:** mô hình AI và bài minh họa ở đây dùng **Valeo WoodScape Dataset**
> (<https://github.com/valeoai/WoodScape>; địa chỉ cũ `woodscape.valeo.com` / `woodscape.valeo.ai`, kiểm 25/09/2026 dẫn
> tới một trang không có nội dung WoodScape). Giới hạn sử dụng: [GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md).
> *(Đổi link 25/09/2026 theo đề xuất ở GIAY_PHEP_DU_LIEU.md mục "Ghi công: link tới trang bộ dữ liệu", CHỜ CHỐT.)*

**Tình trạng (24/09/2026):** đã có phần mềm và kiểm thử trên rig tổng hợp. **Chưa chạy được trên camera của dự án**,
vì ba thứ còn thiếu:

- chưa camera nào được hiệu chuẩn (`calibration/cam_p*.json` chưa có);
- ngoại tham trong `configs/rig/camera_rig_extrinsics_v0.json` là **GIẢ ĐỊNH — CHƯA ĐO**;
- chưa có mặt nạ ROI cho camera dự án.

*(Kiểm lại 25/09/2026 ở `54cb3e2`: ba điều trên vẫn đúng. Không có `calibration/cam_p*.json`, `configs/rig/` chỉ
có tệp v0, `configs/roi/` chỉ có `woodscape_v1`. Công cụ đo ngoại tham và dựng ROI thì đã có và đã commit
(`65b7127`, [NGOAI_THAM_VA_ROI.md](NGOAI_THAM_VA_ROI.md)), còn chờ nội tham và gá camera. BEV vẫn chưa nối vào bàn
thử, hợp nhất cảm biến hay planner.)*

*(Cập nhật 25/09/2026, mã ở `b01dea4`:)* BEV nay được nối vào phiên đỗ xe như **một nguồn vật cản** qua
`fusion/camera_ai.py` và ngăn "AI camera" (`ui/camera_dock.py`, `lidar_app --camera-ai`), sau quyết định giấy phép
ngày 25/09/2026 của người làm khóa luận. Valeo chưa xác nhận cách đọc điều khoản. Chỉ BEV **dùng được** (mục 2,
quy tắc 9) mới tạo vật cản, nên với ba điều còn thiếu ở trên, AI chưa tạo vật cản nào trên bàn thật. Chi tiết, mức
bằng chứng và giới hạn: [AI_DIEU_KHIEN_XE.md](AI_DIEU_KHIEN_XE.md).

Mọi con số dưới đây là của rig tổng hợp hoặc ảnh WoodScape. Không con số nào là số đo sai số BEV trên sa bàn. Điều kiện
"vật mẫu xuất hiện tại vị trí có thể đối chiếu trên BEV" của kế hoạch mục 6 **chưa kiểm**.

*(Tối 24/09/2026:)* BEV đã được tăng tốc, và kết quả trùng từng bit với bản cũ. Ở mặc định, 4 camera mất ≈ 7–12 ms trên
máy bàn, trước đây ≈ 60–115 ms. Laptop nộp đồ án chưa đo. Chi tiết ở mục 6b.

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
2. **Chiếu xuống mặt sàn** theo đúng phép tính của `costmap.project_labels`, mô-đun này không bị sửa
   ([costmap.py](../autopark/perception/costmap.py)). *(Tối 24/09/2026:)* `bev.py` không gọi `project_labels` mỗi khung
   nữa. Phần chỉ phụ thuộc hình học được dựng một lần rồi nhớ, và kết quả trùng từng bit với bản cũ (mục 6b).
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
- *(thêm 25/09/2026)* ngoại tham hay nội tham là dữ liệu TỔNG HỢP: tệp rig (hay camera trong đó) ghi `"synthetic": true`
  — do `extrinsics_calib --allow-synthetic` ghi —, hoặc tệp nội tham mang dấu TỔNG HỢP. Lý do: "ngoại tham/nội tham là dữ
  liệu TỔNG HỢP — không phải số đo", kể cả khi tệp ghi `"measured": true`. Test:
  `tests/test_extrinsics_calib.py::test_bev_projects_board_corners_where_the_camera_saw_them`.

Ngoài ra còn các trường hợp: không camera nào có dữ liệu, dữ liệu tổng hợp, ảnh WoodScape. Hiện nay **mọi** BEV từ tệp rig
v0 đều không dùng được. *(Cập nhật 25/09/2026:)* việc nối AI vào lập đường không còn chờ quyết định giấy phép. Người làm
khóa luận đã quyết định dùng mô hình WoodScape trong vòng điều khiển; Valeo chưa xác nhận cách đọc điều khoản
([GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md)). `stats.json` của lệnh `snapshot` ghi ghi chú giấy phép ở `caveats` và
dòng ghi công ở `attribution` (hằng `WOODSCAPE_LICENCE_NOTE`, `WOODSCAPE_ATTRIBUTION`), không tự chặn. Việc chặn nằm ở
nguồn vật cản `fusion/camera_ai.py`: chỉ BEV có `stamp.valid` như trên mới được tạo vật cản, và nguồn đó chặt hơn ở hai
chỗ. Tệp nội tham không có `acceptance.all_pass` bị chặn. Khung khác cỡ ảnh đã hiệu chuẩn cũng bị chặn
([AI_DIEU_KHIEN_XE.md](AI_DIEU_KHIEN_XE.md) mục 3). Cũng từ 25/09/2026, `load_rig` đọc `acceptance.all_pass` qua
`acceptance_flag`: chỉ `true` của JSON mới là đạt; chuỗi `"false"`, số `1` hay khối `acceptance` không phải object thành
"chưa đạt" (trước đó `bool("false")` là đạt). Điều này áp cho cả lệnh `bev` lẫn nguồn vật cản; kiểm bằng tệp viết tay
trong `tests/test_camera_ai_layer.py`.

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

Chạy từ `autopark/`. Mỗi lệnh viết trên một dòng, dán được vào cmd.exe hay PowerShell; không dùng dấu nối dòng.

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

# 4) (thêm tối 24/09/2026) Đo thời gian build_bev trên rig tổng hợp: lần đầu (gồm dựng bảng) và 15 lần sau.
#    Không cần dữ liệu, không cần thiết bị. Ghi runs/bev/bench_<ngày_giờ>/bench.json. Dùng để đo trên laptop nộp đồ án.
#    Tùy chọn: --supersample, --grid, --max-range, --repeat, --out.
.\.venv\Scripts\python.exe -X utf8 -m autopark.perception.bev bench
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

*(25/09/2026)* `--max-range` phải là số hữu hạn > 0. NaN, ±inf, 0, số âm hay chữ bị từ chối ngay lúc đọc tham số: lệnh
in dòng `error: argument --max-range: …` của argparse (không phải `LỖI: …`), thoát mã 2, chưa tính gì và không ghi thư
mục ra. Trước đó `--max-range nan` tính xong BEV rồi mới hỏng khi ghi JSON. Qua API (`build_bev`, `project_camera`,
`view_geometry`, `bev_from_snapshot`), `max_range` là `None` (không giới hạn) hoặc số > 0; +inf được nhận và cho kết quả
như `None`, nhưng `stats.json` không ghi được inf, nên muốn ghi tệp thì dùng `None`.

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
- **Thời gian `build_bev` của bản TRƯỚC khi tăng tốc** (chiều 24/09; số sau khi tăng tốc ở mục 6b), 4 camera, lưới
  6 × 6 m ô 5 cm, không kiểm tải máy lúc đo. "Lần đầu" gồm việc dựng bảng pixel → ô con của lượt gỡ FREE. Bảng này chỉ
  phụ thuộc hiệu chuẩn, lưới và tầm, nên được nhớ giữa các khung (`lru_cache`, 8 mục, ≈ 2,5 MB mỗi camera 640×480).
  "Tốt nhất / trung vị" là của 7 lần sau đó:

  | supersample | lần đầu | tốt nhất | trung vị | bản trước (tốt nhất / trung vị) |
  |---:|---:|---:|---:|---:|
  | 1 | 261,5 ms | 26,1 ms | 27,7 ms | 29,5 / 30,7 ms |
  | 2 (mặc định) | 318,5 ms | 67,9 ms | 69,5 ms | 81,9 / 84,1 ms |
  | 3 | 381,7 ms | 131,4 ms | 135,8 ms | 136,6 / 148,4 ms |

  Ô 10 cm, tốt nhất: 13,0 / 20,2 / 32,5 ms ở supersample 1 / 2 / 3 (bản trước: 13,8 / 22,2 / 38,2 ms). Lượt gỡ FREE, khi
  bảng đã có sẵn, không làm chậm thấy được. Chênh lệch với bản trước nằm trong dao động giữa các lần đo, vì tải máy
  không được kiểm. Ở supersample 2 bản này **chậm hơn một chu kỳ khung** (≈ 42 ms ở 24 khung/s): mỗi camera chiếu hai
  lượt và tính vùng nhìn riêng. Lệnh dòng lệnh chỉ chạy một lần, nên thời gian nó in gồm cả việc dựng bảng
  (`synthetic`: 365,8 ms). *(Tối 24/09/2026: đã tăng tốc, xem mục 6b.)*
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

## 6b. Tăng tốc (tối 24/09/2026, máy bàn i9-14900, `.venv`)

**Kết quả:** ở mặc định (4 camera 640×480, lưới 6 × 6 m ô 5 cm, supersample 2, tầm 2 m), `build_bev` với bảng đã dựng
mất **≈ 7,4–8,8 ms** (lần nhanh nhất) và **≈ 11,8–12,0 ms** (trung vị). Bản cũ, đo xen kẽ trong cùng tiến trình, mất
87–104 ms (lần nhanh nhất) và ≈ 114–115 ms (trung vị). Như vậy nhanh hơn ≈ 12 lần theo lần nhanh nhất, ≈ 10 lần theo
trung vị, và dưới một chu kỳ khung (≈ 42 ms ở 24 khung/s). **Kết quả không đổi:** mọi mảng trùng từng bit với bản cũ,
nên không cần dung sai (phần kiểm ở cuối mục này). (Áp dụng cho `max_range` là `None` hoặc > 0. Từ 25/09/2026
`max_range` NaN/≤ 0 bị từ chối. Trước đó NaN làm `in_view_fine`/`in_view_by`/`category` khác bản cũ, và ở cả hai bản NaN
bỏ giới hạn tầm và tắt lượt gỡ FREE vật mảnh; chi tiết ở cuối mục này.)

Mọi số ở mục này đo trên **rig tổng hợp** hoặc trên **hiệu chuẩn WoodScape với bản đồ xác suất ngẫu nhiên**, không phải
khung camera thật. Lúc đo, **các tác tử khác đang chạy song song** trên cùng máy: 10–20 tiến trình Python, CPU cả máy
13–40 %. Tải máy **không kiểm soát được**, nên số dao động. Chẳng hạn, lần profile đầu tối 24/09 (trước khi sửa, giờ
chính xác không ghi; tải lúc 21:08 là 13 %) đo bản cũ 59,5 ms tốt nhất / 71,5 ms trung vị, còn lúc 21:17 bản cũ mất
87–104 ms. **Laptop RTX 3050 Ti (máy nộp đồ án): CHƯA ĐO.** Đo bằng lệnh 4 ở mục 5.

**Đo trước khi sửa** (cProfile, 10 lần `build_bev` ở mặc định, bản cũ):

- phần lớn thời gian nằm ở `ground_to_pixel`: 46 % tổng. Hàm này chạy ba lần mỗi camera mỗi khung (hai lượt
  `project_labels` và phần vùng nhìn), dù kết quả chỉ phụ thuộc hiệu chuẩn và lưới;
- phần còn lại của `project_labels` (khoảng cách, phương vị, che khuất) ≈ 1,2 ms mỗi lượt;
- `evidence_labels` ≈ 1,1 ms mỗi camera; `merge_views` ≈ 3,7 ms mỗi khung (phép `reshape(...).any(axis=(1, 3))` chậm).

**Cách làm.** Không đổi quy tắc nào:

1. **Bảng hình học dựng sẵn** (`view_geometry`). Bảng được nhớ bằng `lru_cache` 8 mục, khóa gồm hiệu chuẩn (nội tham
   gồm cỡ ảnh, ngoại tham, tên), lưới mịn, tầm và bin phương vị. Bảng chỉ giữ các ô con "trong vùng", tức tâm chiếu hợp
   lệ vào ảnh và nằm trong tầm; mọi ô con khác luôn UNKNOWN. Mỗi ô con trong vùng có: pixel ở tâm, khoảng cách, bin
   phương vị, dải bin của bóng che nếu ô là OCCUPIED. Các biểu thức, kiểu dữ liệu và thứ tự phép tính chép từ `project_labels`.
   Bảng pixel → ô con của lượt gỡ FREE (tâm và bốn góc pixel, tầm nới một cạnh ô con như cũ) được xếp theo ô con, bỏ
   cặp trùng.
2. **Mỗi khung** chỉ còn các bước sau:
   - đọc nhãn pixel tại tâm các ô con trong vùng (4 908–5 786 ô con mỗi camera của rig), đổi sang trạng thái bằng
     bảng tra;
   - che khuất bằng `np.minimum.at` chỉ trên các ô OCCUPIED;
   - gỡ FREE bằng `np.logical_or.reduceat` theo ô con;
   - "thấy" và "vùng hình học" lấy từ cùng lần đọc.

   Lượt chiếu thứ hai của bản cũ (pixel không chắc coi như FREE) không cần nữa. Tập OCCUPIED của hai lượt như nhau,
   nên phép che khuất cũng như nhau.
3. **Bằng chứng:** khi bản đồ không có NaN/±inf và mọi giá trị trong [0, 1] (kiểm bằng `min`/`max`, hai lượt rút gọn),
   mỗi pixel được gán mã (p > t_free) + (p ≥ t_blocked) + 4·(ngoài ROI) rồi tra bảng bằng `cv2.LUT`. Các phép so sánh
   float32 giống bản cũ. Có NaN/±inf thì chạy đúng công thức cũ. Hai ngưỡng trùng nhau sau khi làm tròn về float32 (ví
   dụ 0,5 và 0,5 + 1e-9) cũng chạy công thức cũ. Trường hợp này lộ ra khi rà lại mã; lúc đó mã một lượt gọi pixel
   p = 0,5 là "không chắc", còn bản cũ gọi là BLOCKED. Đã có test. P×255 → P tra bảng 256 giá trị, cùng phép tính từng
   phần tử với `astype(float32) / 255`.
4. **Gộp khối k × k** bằng OR/AND của k² lát cắt bước k, thay cho `reshape(...).any(axis=(1, 3))`. Kết quả như nhau,
   nhanh hơn ≈ 10 lần ở k = 2 (mảng 240 × 240). `merge_views` so sánh trạng thái một lần mỗi camera và bỏ qua camera
   không có ô OCCUPIED khi tìm cặp xung đột.

**Đo trước / sau trong cùng một tiến trình.** Bản cũ là bản chép của `bev.py` ở commit 9bcc30c. Hai bản chạy xen kẽ,
15 lần mỗi bản sau lần đầu. Đầu vào: bản đồ P×255 cỡ 480×360 của cảnh `synthetic`, tầm 2 m. "Lần đầu" là lần gọi đầu
sau khi xóa bộ nhớ đệm, nên gồm cả việc dựng bảng. Hai lần chạy lúc 21:17:15 và 21:17:52 (tải CPU 16–30 %). Số dưới đây
là lần nhanh nhất / trung vị, tính bằng ms:

| Lưới | supersample | Lần đầu: cũ / mới | Bản cũ | Bản mới | Nhanh hơn (lần nhanh nhất) |
|---|---:|---|---|---|---:|
| ô 5 cm | 1 | 301 / 316; 284 / 310 | 28,9 / 33,9; 22,8 / 28,5 | 5,0 / 7,2; 4,5 / 5,7 | 5,8×; 5,1× |
| ô 5 cm | **2 (mặc định)** | 555 / 491; 450 / 438 | 103,9 / 114,4; 86,9 / 114,9 | **8,8 / 12,0; 7,4 / 11,8** | **11,9×; 11,8×** |
| ô 5 cm | 3 | 628 / 524; 657 / 525 | 168,0 / 209,2; 152,6 / 178,2 | 10,1 / 14,5; 9,7 / 15,2 | 16,6×; 15,7× |
| ô 10 cm | 1 | 389 / 422; 361 / 387 | 22,8 / 26,2; 15,7 / 25,6 | 6,5 / 7,7; 4,6 / 7,8 | 3,5×; 3,4× |
| ô 10 cm | 2 | 425 / 429; 367 / 418 | 26,3 / 40,5; 25,1 / 32,3 | 5,4 / 9,0; 4,7 / 6,2 | 4,9×; 5,3× |
| ô 10 cm | 3 | 459 / 456; 452 / 509 | 53,0 / 60,6; 54,1 / 70,8 | 5,7 / 10,0; 8,7 / 10,9 | 9,2×; 6,2× |
| WoodScape, 3 ảnh 1280×966, lưới 25 × 20 m ô 0,1 m, tầm 12 m | 2 | 1 681 / 1 817; 1 510 / 1 767 | 297,9 / 344,4; 345,7 / 382,4 | 33,9 / 48,7; 38,7 / 53,2 | 8,8×; 8,9× |

Mỗi ô ghi hai lần chạy, cách nhau bằng dấu chấm phẩy. Lần chạy `bench` lúc 21:20 (tải CPU ≈ 40 %, 20 tiến trình
Python) cho kết quả mặc định: lần đầu 397 ms; tốt nhất 8,4 ms, trung vị 9,5 ms, chậm nhất 10,6 ms. Ở mặc định, mỗi
camera mất ≈ 1,2–2,7 ms và phần hợp nhất ≈ 1,0–1,4 ms (số của từng lần chạy).

**Chưa nhanh hơn: khung đầu tiên.** Khung đầu vẫn mất ≈ 0,3–0,5 s cho 4 camera, ngang bản cũ, vì phải dựng bảng. Mỗi
camera 640×480 mất ≈ 80–110 ms. Trong đó ≈ 61–67 ms là bước chiếu ≈ 615 000 tâm và góc pixel xuống sàn
(`pixel_to_ground` của `calibration.py`, mô-đun đó không bị sửa). Khi nối vào bàn thử, bảng phải được dựng lúc khởi
động, trước khung đầu, bằng cách gọi `build_bev` hay `view_geometry` một lần. **Việc này chưa làm**, vì BEV chưa nối
vào bàn thử. Bảng phải dựng lại khi đổi hiệu chuẩn, lưới, supersample, tầm hay cỡ ảnh.
*(Cập nhật 30/09/2026: từ `b01dea4` (25/09/2026), nguồn vật cản AI camera dựng trước bảng bằng
`CameraObstacleMapper.warm_up()` (gọi `build_bev` một lần) khi ngăn AI camera bật và nguồn vật cản không bị chặn. Khi
phát lại o03 với rig TỔNG HỢP trên máy bàn trước ngày 25/09/2026, bước này mất 297 ms
([AI_DIEU_KHIEN_XE.md](AI_DIEU_KHIEN_XE.md) mục 8.2). `rig.bench` và `ui.rig_app` không chạy BEV.)*

**Bộ nhớ** (tính từ `ViewGeometry.nbytes()`):

- rig 640×480, tầm 2 m, supersample 2: 2,83–3,21 MB mỗi camera (bản cũ ≈ 2,5 MB);
- WoodScape 1280×966, tầm 12 m: 13,5 MB (`00000_FV`), 14,4 MB (`00028_RV`), 20,9 MB (`00140_MVL`).

Bộ nhớ đệm giữ tối đa 8 bảng. Bản nháp đầu giữ bảng dạng (pixel × 5) chiếm 7–8 MB mỗi camera rig và 23–31 MB mỗi ảnh
WoodScape, nên đã được thay bằng bảng xếp theo ô con.

**Kiểm rằng kết quả không đổi:**

- Test `test_fast_path_matches_reference_bit_for_bit_on_random_inputs` giữ bản cũ ngay trong tệp test. Bản cũ đó gọi
  thẳng `costmap.project_labels`. Test so dtype, cỡ và từng phần tử của mọi mảng (`state_fine`, `seen_fine`,
  `in_view_fine`, `state`, `states`, `category`, bốn bitmask, `conflict`), tỉ lệ pixel, và cặp xung đột kể cả thứ tự.
  Các trường hợp:
  - 45 cấu hình ngẫu nhiên: 1–4 camera, nội tham, tư thế, ROI ngẫu nhiên, ảnh 97×73–160×120;
  - bản đồ bốn kiểu: nhiễu đều, cảnh hộp, khối có NaN, P×255; thêm +inf, giá trị đúng bằng ngưỡng, float64, cỡ 0,5–1,5
    lần;
  - ngưỡng, ô 4–10 cm, supersample 1–3, tầm (không giới hạn / 1 / 2 / 3,5 m), bin 0,25–2°, hộp thân xe, camera thiếu dữ
    liệu;
  - 3 lần trên rig 640×480;
  - camera nhìn gần thẳng xuống từ đúng tâm một ô con, mọi pixel BLOCKED: ô chứa camera che mọi phương vị;
  - hai trường hợp từ chối (xác suất 1,5; ROI sai cỡ), phải cùng thông báo.
- Test đó cũng so `evidence_labels` với bản cũ khi hai ngưỡng trùng nhau sau khi làm tròn về float32.
- Ngoài repo, bản cũ là bản chép trong thư mục tạm. Đã chạy 10 seed × 80 cấu hình ngẫu nhiên, tổng 1 743 lần chiếu một
  camera: 6 seed trước lần sửa cuối (chặn hai ngưỡng trùng), 4 seed sau. Thêm 3 ảnh WoodScape × 4 bản đồ ngẫu nhiên, và
  mọi ô của bảng đo trên. **Tất cả trùng từng bit.**
- **Ngoại lệ đã gặp khi rà lại (25/09/2026): `max_range` NaN.** Các phép so ở trên chỉ dùng tầm `None` hoặc > 0. Với
  NaN, bản cũ tính `hypot <= nan` (toàn False, vùng nhìn rỗng) còn `view_geometry` tính `~(distance > nan)` (toàn
  True). Trên rig tổng hợp với bản đồ P×255 mặc định (máy bàn, tối 24/09, bản chép của 9bcc30c trong thư mục tạm):
  `states` trùng, nhưng `in_view_fine` khác 11 431–16 428 ô con mỗi camera, `in_view_by` khác 12 422 ô, `category` khác
  1 240 ô. Ở **cả hai** bản, NaN bỏ giới hạn tầm (FREE tới chân trời) và tắt lượt gỡ FREE vật mảnh (`pixel_to_ground`
  nhận tầm NaN + cạnh ô con và loại mọi pixel). Sửa: hàm `check_max_range` từ chối NaN, ≤ 0 và giá trị không phải số ở
  `build_bev` (trước khi chiếu camera nào), `project_camera`, `view_geometry` và `bev_from_snapshot` (trước khi đọc thư
  mục). 0 và số âm trước đây cho vùng nhìn rỗng ở cả hai bản (trùng nhau), nay cũng bị từ chối vì không có nghĩa dùng.
  Kiểm lại sau khi sửa: NaN, 0, −1 → `ValueError`; +inf, `None`, 2 m vẫn trùng từng bit với bản cũ trên rig tổng hợp.

## 7. Kiểm thử

*(Cập nhật tối 24/09/2026, sau khi tăng tốc và sửa `max_range` NaN.)* `tests/test_bev.py` có **38 test**: 32 test cũ
giữ nguyên, không nới, cộng 6 test mới. Lần chạy cuối lúc 21:58–22:04 tối 24/09 trên máy bàn, trong khi các tác tử khác
đang sửa một số tệp mã và test liên quan:

- `.venv`: 38 đạt. Cùng `test_perception_calibration`, `test_fisheye_calib`, `test_fusion`, `test_fusion_demo`,
  `test_lidar_bench_map`, `test_labels`, `test_phase1_sources`, `test_roi_tool`, `test_extrinsics_calib` (hai tệp sau
  gọi `build_bev`): 205 đạt, 1 bỏ qua (test cần torch của `test_labels`), 0 lỗi (21:58–22:00).
- `.venv-train`: 38 đạt. Cùng `test_perception_calibration`, `test_fisheye_calib`, `test_labels`,
  `test_phase1_sources`: 137 đạt, 0 lỗi (22:03–22:04).
- Ghi để khỏi hiểu nhầm: lần chạy `.venv-train` lúc 22:00–22:01 có thêm `test_roi_tool` và `test_extrinsics_calib` được
  162 đạt, **6 lỗi**, cả sáu ở hai tệp đó; chạy lại hai tệp bằng `.venv` lúc 22:02 cũng 6 lỗi. Nguyên nhân là
  `extrinsics_calib.py` do tác tử khác sửa lúc 22:00:55 (lỗi `ExtrinsicsError`: nội tham TỔNG HỢP không được ghi như số
  đo), không phải `bev.py`: trước lúc đó cùng các test ấy đạt với `bev.py` hiện tại.
  *(Cập nhật 25/09/2026: ở mã đã commit `54cb3e2`, ba tệp `test_bev`, `test_extrinsics_calib`, `test_roi_tool`
  chạy bằng `.venv` được 86 đạt (38 + 29 + 19), 0 lỗi. Lần chạy đủ bộ test ngày 25/09 trên máy bàn: `.venv` 1 242
  đạt, 7 bỏ qua; `.venv-train` 386 đạt (các tệp cần torch, cùng test nhãn, bàn thử, kiểm máy, hiệu chuẩn, ngoại
  tham, ROI); 0 lỗi.)* *(Cập nhật 01/10/2026: 386 là nhóm chọn của `.venv-train`, không phải toàn bộ bộ test
  ([TONG_HOP_DU_AN.md](../../TONG_HOP_DU_AN.md) mục 7); các lượt toàn bộ sau đó:
  [CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 8, 9, 11, 15.)*

Sáu test mới:

- `test_fast_path_matches_reference_bit_for_bit_on_random_inputs`: đường nhanh trùng từng bit với bản cũ (mục 6b).
- `test_blocked_pixel_just_beyond_range_still_removes_free_of_a_cell_inside_range`: ô con có tâm trong tầm, nhưng pixel
  BLOCKED rơi vào phần ô nằm ngoài tầm. Ô đó phải không còn FREE, vì bảng pixel → ô con nới tầm thêm một cạnh ô con.
  Test này đạt cả trên bản cũ. Nó được thêm vì kiểm đột biến cho thấy phép so ngẫu nhiên không gặp trường hợp này.
- `test_geometry_tables_are_built_once_and_read_only`: khung thứ hai không dựng lại bảng (4 lần trúng bộ nhớ đệm, 0 lần
  dựng). Đổi tầm hay bin phương vị thì ra bảng khác. Bảng chỉ đọc và nhỏ hơn 8 MB mỗi camera.
- `test_fast_path_speedup_over_reference` (dấu `planner_budget`, nên không chạy trong lượt coverage): đo trên cùng máy,
  xen kẽ hai bản, lấy lần nhanh nhất của 5 lần. Bản mới phải nhanh hơn bản cũ **≥ 3 lần** và mất dưới 0,25 s. Đo tối
  24/09 được ≈ 8–12 lần. Ngưỡng 3 lần để trừ hao máy yếu hay bận. Test cận trên 1 s cũ vẫn giữ.
- `test_bench_cli_writes_timing_report`: lệnh `bench` ghi `bench.json` đủ trường; `--repeat 0` thì báo `LỖI`, mã 2.
- `test_invalid_max_range_is_rejected_at_every_entry_point` *(25/09/2026)*: `max_range` NaN (ba kiểu: `float("nan")`,
  `math.nan`, `np.float32` NaN), 0, −1 và chữ → `ValueError` nhắc `max_range` ở `build_bev` (cả khi không camera nào có
  bản đồ), `project_camera` (cả khi bản đồ sai cỡ: kiểm tầm trước), `view_geometry` (gọi hai lần, lỗi không bị bộ nhớ
  đệm giữ) và `bev_from_snapshot` (thư mục không tồn tại vẫn ra lỗi tầm). `None` và +inf vẫn nhận, +inf cho đúng kết
  quả như `None` và vùng nhìn rộng hơn tầm 2 m. Dòng lệnh `bench`/`synthetic` với `--max-range` nan, ±inf, 0, −2, chữ:
  thoát mã 2 lúc đọc tham số, không ghi thư mục ra. Kiểm đột biến trên bản chép trong thư mục tạm (tối 24/09): **8/8 bị
  bắt** — bỏ kiểm ở từng lối vào trong bốn lối, nhận NaN, nhận 0, dòng lệnh dùng `type=float`, dòng lệnh nhận inf.

**Kiểm đột biến cho phần tăng tốc** (tối 24/09/2026). Các đột biến sửa `bev.py` của một **bản chép** trong thư mục tạm,
không sửa repo. Bản chép không có `datasets/`, nên test WoodScape bị bỏ qua ở đó. Lượt đầu có 19 đột biến, 18 bị bắt.
Đột biến lọt là "bảng pixel → ô con không nới tầm thêm một cạnh ô con". Test mới ở trên bắt được nó. Lượt cuối chạy với
mã và tệp test cuối cùng, có thêm đột biến "bỏ chặn hai ngưỡng trùng float32": **20/20 bị bắt**. Bản chép chưa đột biến
đạt 36 test, bỏ qua 1. Danh sách đột biến:

- bỏ che khuất; che cả chính ô OCCUPIED; bỏ trường hợp ô chứa vị trí camera;
- bỏ gỡ FREE; gỡ FREE chỉ theo tâm pixel; gỡ FREE thành OCCUPIED; bảng gỡ FREE không nới tầm;
- "thấy" bỏ qua che khuất; vùng hình học lấy từ "thấy";
- ngưỡng FREE thành `>=`; coi bản đồ có NaN là "sạch" (NaN thành FREE); bỏ chặn hai ngưỡng trùng float32; bỏ ROI ở
  nhánh nhanh; P×255 chia 256;
- gộp khối `_any` thành AND; `_all` thành OR;
- bộ nhớ đệm chỉ theo tên camera (bảng cũ dùng cho lưới/tầm khác); bỏ bộ nhớ đệm. Riêng test tỉ lệ tăng tốc cũng bắt
  được đột biến này;
- tỉ lệ pixel "không có bằng chứng" sai; bỏ nhầm cặp xung đột.

**Lần chạy trước khi tăng tốc** (24/09, 32 test):

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
- thời gian 4 camera trên lưới 6 × 6 m ô 5 cm: cận trên 1 s, lỏng để chạy được trên máy yếu. Số đo ở mục 6 và 6b.

**Kiểm đột biến (chiều 24/09, trước khi tăng tốc).** Mỗi đột biến được nạp như một bản mã đã sửa trong bộ nhớ của tiến
trình kiểm; tệp `bev.py` trên đĩa không bị sửa. Lần chạy lại ngày 24/09 sau bản sửa có 23 đột biến, **cả 23 bị bắt**.
Đột biến "bỏ quy tắc che khuất" ở đây thay `project_labels`. Từ tối 24/09 phép che khuất nằm trong `bev.py`, và đột
biến tương ứng ở lượt tối 24/09 bên trên.

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
2. **Gá camera, chốt gán cổng → hướng, đo ngoại tham.** Chưa có công cụ. *(Cập nhật 25/09/2026: nay đã có và đã
   commit trong `65b7127`: `perception/extrinsics_calib.py` và giao diện `ui/roi_app.py`, cách làm ở
   [NGOAI_THAM_VA_ROI.md](NGOAI_THAM_VA_ROI.md). Mới kiểm trên ảnh TỔNG HỢP; đo thật còn chờ nội tham (việc 1) và
   gá camera. Tệp ra dự kiến `configs/rig/camera_rig_extrinsics_v1.json`, chưa có.)* Một hướng là
   `cv2.fisheye.solvePnP` với bảng đặt trên sàn ở vị trí đo được, nay đã cài trong `perception/extrinsics_calib.py`
   ([NGOAI_THAM_VA_ROI.md](NGOAI_THAM_VA_ROI.md); ý gốc ở TONG_HOP_DU_AN.md mục 5.4 bản `9d68257`). Ghi kết quả vào một
   tệp rig mới với `"measured": true` và `quaternion_xyzw`; giữ v0 làm hồ sơ.
3. **Mặt nạ ROI cho camera dự án** (`roi_p<cổng>.png`): loại thân xe, dây, viền ống kính. *(Cập nhật 25/09/2026:
   công cụ dựng ROI đã có, `perception/roi_tool.py` và thẻ "ROI" của `ui/roi_app.py` (`65b7127`,
   NGOAI_THAM_VA_ROI.md mục 6); chưa có mặt nạ nào cho camera dự án, thư mục `configs/roi/rig_v1` chưa có.)*
4. **Đo sai số BEV** (kế hoạch mục 6, bước 8): đặt vật mẫu ở vị trí đo bằng thước ở trước, sau, hông và vùng giáp ranh;
   so với BEV; lập báo cáo sai số và sơ đồ vùng quan sát.
5. Chọn và đánh giá phương pháp **biên tiếp xúc** của vật cao (mục 3). Chọn **tiêu chí độ phân giải** thay cho
   `max_range` cố định.
6. **Tốc độ** *(cập nhật tối 24/09/2026, mục 6b)*. Ở mặc định, 4 camera mất ≈ 7,4–8,8 ms (lần nhanh nhất) và
   ≈ 9,5–12 ms (trung vị) khi bảng đã dựng. Trước khi tăng tốc là ≈ 60–104 ms. Số này đo trên máy bàn, rig tổng hợp,
   khi các tác tử khác đang chạy song song. Còn thiếu:
   - **Laptop RTX 3050 Ti: CHƯA ĐO.** Chạy lệnh `bench` (mục 5, lệnh 4) trên laptop, rồi chép `bench.json` vào hồ sơ.
     *(Cập nhật 25/09/2026: lệnh `bench` đã commit và push trong `65b7127`; laptop có nó sau `git pull`.)*
   - **Khung đầu** vẫn mất ≈ 0,3–0,5 s để dựng bảng. Phải dựng bảng lúc khởi động khi nối vào bàn thử: CHƯA LÀM.
     *(Cập nhật 30/09/2026: đã làm ở nguồn vật cản AI camera: `CameraObstacleMapper.warm_up()` dựng bảng khi bật, từ
     `b01dea4`; xem mục 6b.)*
   - Chưa đo trên khung camera thật có ROI. Chưa đo khi BEV chạy cùng bàn thử (bốn luồng camera, AI, giao diện) trong
     một tiến trình.
     *(Cập nhật 30/09/2026: đã đo một phần khi phát lại o03 qua ngăn AI camera với rig TỔNG HỢP (Rig, AI và ngăn chạy
     offscreen trong một tiến trình, script gọi `tick()` thay timer; máy bàn trước, 25/09/2026): BEV 4 camera trung vị
     5,6 ms, p95 8,0–8,1 ms; mỗi `tick()` trung vị 10,9–11,0 ms ([AI_DIEU_KHIEN_XE.md](AI_DIEU_KHIEN_XE.md) mục 8.2).
     Chưa đo với camera thật đang chạy, ROI thật hay trên laptop.)*
   - BEV chưa chạy song song giữa các camera. Chưa cần, vì mỗi camera ≈ 1,2–2,7 ms.
7. **Nối vào bàn thử / hợp nhất** (`CameraSemanticLayer`, kế hoạch giai đoạn 3): chưa làm. Chờ các mục trên, và chờ
   quyết định giấy phép WoodScape cho việc nối AI vào lập đường. *(Cập nhật 25/09/2026: phần mềm đã làm, `b01dea4`,
   [AI_DIEU_KHIEN_XE.md](AI_DIEU_KHIEN_XE.md). Quyết định giấy phép đã có, Valeo chưa xác nhận. Có lọc 2/3 lô trong hệ
   bản đồ. Còn chờ mục 1–4 thì AI mới tạo được vật cản trên bàn thật. Chỉ kiểm bằng nguồn giả, rig tổng hợp và bản ghi
   phát lại.)*
8. Lọc theo thời gian, bù chuyển động xe giữa các camera: chưa có. Mọi stamp là lúc khung tới máy, không phải lúc phơi
   sáng.
   *(Cập nhật 30/09/2026: lọc theo thời gian đã có ở nguồn vật cản AI camera, ≥ 2 trong 3 lô, trong hệ bản đồ
   (`fusion/camera_ai.py`, từ `b01dea4`); `bev.py` tự nó không lọc. Bù chuyển động xe giữa các camera và nội suy tư thế
   về lúc chụp: chưa có.)*
9. AI **chưa từng được chấm trên ảnh sa bàn**. Hai ngưỡng 0,15 / 0,50 chưa kiểm trên sa bàn. Mọi lỗi của mô hình đi
   thẳng vào BEV.
