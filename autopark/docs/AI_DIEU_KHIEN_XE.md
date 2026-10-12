# AI camera trong vòng điều khiển xe

> **Ghi công bắt buộc theo giấy phép dữ liệu:** mô hình AI dùng ở đây được huấn luyện trên **Valeo WoodScape Dataset**
> (<https://github.com/valeoai/WoodScape>; địa chỉ cũ `woodscape.valeo.com` / `woodscape.valeo.ai`, kiểm 25/09/2026 dẫn
> tới một trang không có nội dung WoodScape). Giới hạn sử dụng và quyết định dùng trong vòng điều khiển:
> [GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md).

Tài liệu này mô tả cách AI camera được nối vào phiên đỗ xe làm nguồn vật cản thứ hai bên cạnh LiDAR: AI làm gì, khi nào
bị chặn, tham số, cách chạy, mức bằng chứng và giới hạn. Nó dành cho người chạy bàn thử, người chuẩn bị hiệu chuẩn
camera và người viết phần AI của khóa luận. Phần mềm viết ngày 25/09/2026 (mã ở `b01dea4`) và được bổ sung ngày
02/10/2026 bằng các công cụ nghiệm thu T3, T3b, T6, T13 ([kịch bản nghiệm thu](KICH_BAN_NGHIEM_THU.md) mục 7).

## Tóm tắt (tới 02/10/2026)

- **Đã có:** phần mềm nối AI của các camera vào phiên đỗ xe như **một nguồn vật cản thứ hai bên cạnh LiDAR**, theo đúng
  khuôn của ngăn LiDAR. AI chỉ thêm vật cản, không bao giờ xóa vật cản của nguồn khác (mục 1).
- **Đã kiểm:** bằng nguồn giả, rig tổng hợp và bản ghi phát lại (mục 8). Lệnh dừng của ngăn đã chạy qua `VehicleIO` với
  bo mô phỏng và camera giả trong test (02/10/2026).
- **Trên bàn thật AI hiện không tạo vật cản nào**, vì chưa camera nào được hiệu chuẩn; ngăn chỉ hiện lý do bị chặn
  (mục 3). Phát lại bản ghi thật `o03_20260924` với mô hình thật trên máy bàn: 1163/1163 lô bị chặn, 0 vật cản (mục 8.2).
- **Chưa thử** với camera thật đang chạy, chưa thử trên xe, chưa qua bo thật. AI chưa từng được chấm trên ảnh sa bàn.
- Mọi tham số (ngưỡng 0,15, lọc 2/3, tuổi 0,5 s, lề 5 cm) là đề xuất, chưa chốt (mục 4, 10).

Mã: [autopark/fusion/camera_ai.py](../autopark/fusion/camera_ai.py) (nguồn vật cản, không Qt),
[autopark/ui/camera_dock.py](../autopark/ui/camera_dock.py) (ngăn "AI camera"),
[autopark/ui/lidar_app.py](../autopark/ui/lidar_app.py) (tùy chọn `--camera-ai`). Kiểm thử:
[tests/test_camera_ai_layer.py](../tests/test_camera_ai_layer.py), [tests/test_camera_dock_ui.py](../tests/test_camera_dock_ui.py).

## 1. AI làm gì trong vòng điều khiển

Mỗi lô AI đi qua chuỗi dưới đây. Lô chỉ tới được phiên đỗ xe khi BEV dùng được (mục 3).

```
4 camera (hay bản ghi phiên) → Rig: luồng camera + luồng AI (rig/core.py) → lô AI mới nhất (P(BLOCKED) từng camera)
  → [chặn: BEV dùng được?] → BEV hệ xe (perception/bev.py) → đặt vào lưới sa bàn theo tư thế → lọc 2/3 lô
  → CameraSemanticLayer (fusion/layers.py) → fuse → ObstacleBridge tiền tố "camera_ai" (fusion/bridge.py) → phiên đỗ xe
```

- **Chỉ THÊM vật cản.** AI có `ObstacleBridge` riêng (id `camera_ai_<số>`). Nó không bao giờ xóa hay sửa vật cản của
  LiDAR (`lidar_…`), của người dùng hay của kịch bản. Planner chỉ dùng các hình chữ nhật vật cản, nên ô FREE của camera
  **không có tác dụng gì lên lập đường**: camera nói "trống" không mở đường qua chỗ LiDAR hay người dùng đã chặn.
- **Đang chỉnh sa bàn (EDITING)**, khi ô "Vật cản bám theo AI" bật (mặc định): sau mỗi lô dùng được, hộp AI nào không
  còn thì bỏ, hộp mới thì thêm (`sync_incremental`, chỉ hộp CỦA AI), như ngăn LiDAR. Planner lập đường tránh các hộp đó.
  - Tắt ô đó thì hộp AI đứng yên. Nút "Xóa vật AI" chỉ xóa hộp AI.
  - Ngay sau khi cửa sổ lọc bị xóa (đổi cấu hình, lô bị chặn, hai lô cách nhau > 0,5 s), cửa sổ chưa đủ `min_hits` lô
    nên chưa ô nào có thể là vật cản. Lúc đó hộp AI được **giữ**, không bị bỏ rồi hiện lại với id mới (sửa 25/09/2026).
- **Thân xe không bao giờ thành vật cản AI.** Mặt nạ thân xe là thân xe của phiên nới 5 cm, gộp với hộp
  `vehicle_assumed` của tệp rig. Mặt nạ được áp hai lần: trên BEV hệ xe, và trong **hệ bản đồ cho từng lô, ở tư thế của
  lô đó**. Lần thứ hai cần vì đặt BEV vào lưới sa bàn làm ô vật cản phình tối đa một ô (mục 4). Trước 25/09/2026 chỉ có
  lần thứ nhất, nên hộp AI có thể chờm vào thân xe tới vài cm khi xe không thẳng lưới. Lúc đó chỗ xuất phát bị tính là
  va chạm và không lập được đường (người rà tái hiện được).
- **Sẵn sàng (READY)**: bản đồ giữ cố định để lập đường và xem trước.
- **Đang chạy (RUNNING)**: hộp AI MỚI (không nằm trong vật cản đã biết nới một ô) chạm hành lang thân xe dọc phần quỹ
  đạo còn lại (nới 10 cm) thì ngăn gọi `inject_obstacle`. Phiên phát MAP_CHANGED, xe dừng và chờ lập lại đường. Đây là
  đường dừng sẵn có của giai đoạn 0, không có đường nào khác. Hộp mới ngoài hành lang chỉ được ghi nhớ.
- **Không liên hệ phần cứng chấp hành.** Ngăn chỉ đọc camera, chạy AI và chèn vật cản vào phiên. Khi có xe, xe sẽ dừng
  qua đường dừng của phiên (`VehicleIO`), như với vật cản LiDAR. Hiện đường này chỉ chạy với bo mô phỏng; với bo thật,
  START bị từ chối vì chưa có nguồn tư thế thật ([CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) mục 3). Chưa thử trên xe.

## 2. Giấy phép: quyết định 25/09/2026

Người làm khóa luận quyết định dùng mô hình huấn luyện trên WoodScape trong vòng điều khiển xe mô hình 1/12. Cơ sở,
toàn văn câu điều khoản, hai cách đọc, kết quả kiểm trên web và phương án dự phòng ở
[GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md), mục "WoodScape trong vòng điều khiển: quyết định 25/09/2026". Tóm tắt:

- Điều khoản chỉ cho dùng phi thương mại. Cùng câu cấm dùng thương mại có vế *"and notably not use or deploy the
  Dataset, any models trained on or refined using the Dataset ... in operation of a vehicle or to assist in the
  operation of vehicle"*. Dự án đọc vế này là ví dụ của việc dùng thương mại bị cấm (cách đọc A). Cách đọc B: đây là một
  lệnh cấm riêng, bất kể thương mại hay không.
- **Valeo chưa xác nhận cách đọc nào.** Kiểm 25/09/2026: hai địa chỉ trang bộ dữ liệu dẫn tới một trang Valeo khác;
  LICENSE.pdf và repo GitHub không có email liên hệ. Ở issue #14 của repo, một cộng tác viên Valeo trả lời rằng bộ dữ
  liệu có giấy phép riêng và chỉ dùng phi thương mại. Câu trả lời đó không nói gì về vế phương tiện.
- Chuỗi ghi công và ghi chú giấy phép nằm ở một chỗ: `WOODSCAPE_ATTRIBUTION`, `WOODSCAPE_LICENCE_NOTE` trong
  `perception/bev.py`. Ngăn AI camera hiện ghi công ở đầu ngăn. `CameraObstacleMapper.describe()` và tệp ra của lệnh
  `bev` (`snapshot`, `woodscape`) cũng ghi hai chuỗi này.
- **Dự phòng (hướng 1 của GIAY_PHEP_DU_LIEU.md):** chạy `lidar_app` không có `--camera-ai`. Khi đó cửa sổ đúng như
  trước 25/09/2026: không có ngăn camera, không nhập torch, chạy được trong `.venv`. Test
  `test_lidar_app_without_camera_options_is_unchanged` kiểm điều này.
- Checkpoint mặc định của ngăn là `runs/ai_woodscape_rtx4000_v1/best.pt`, lượt chỉ WoodScape. Quyết định 25/09 không
  phủ các checkpoint có AVM-SS (GIAY_PHEP_DU_LIEU.md mục "Phạm vi"). Tuy vậy ô "Mô hình" của ngăn vẫn nhận mọi tệp, và
  ngăn **không** kiểm checkpoint có AVM-SS hay không (mục 10).

## 3. Chặn: vì sao AI chưa làm gì trên xe thật

Chỉ BEV **dùng được cho lập đường** mới được tạo vật cản. Hiện chưa camera nào có hiệu chuẩn, nên trên bàn thật mọi lô
đều bị chặn. Mỗi lô AI mới bị chặn nếu có một trong các điều sau:

| Điều kiện | Lý do hiện ra (sau "AI chưa được dùng để điều khiển vì: ") |
|---|---|
| Thiếu tệp ngoại tham | `chưa có tệp ngoại tham đã đo … — bước 2, sau nội tham: đo theo docs/NGOAI_THAM_VA_ROI.md mục 1–5`, kèm các tệp còn thiếu khác (xem dưới bảng) |
| Hỏng tệp ngoại tham (JSON sai, sai `format`) | `không đọc được tệp ngoại tham …` |
| Camera đã chọn thiếu tệp nội tham `calibration/cam_p<cổng>.json` | `chưa có tệp nội tham … hiệu chuẩn trước (docs/HIEU_CHUAN_CAMERA.md)…`, kèm `chưa có ROI của …` nếu ROI cũng thiếu |
| Tệp hiệu chuẩn hỏng kiểu lạ (sửa tay, ví dụ `"camera": 5`) | `tệp hiệu chuẩn/ngoại tham/ROI hỏng (TypeError: …)`. Hàm nạp không bao giờ ném: lỗi lạ cũng thành lý do chặn |
| Cổng đã chọn không có trong tệp ngoại tham | `p<N>: cổng N không có trong tệp ngoại tham …` |
| Ngoại tham chưa `"measured": true` | `p<N>: ngoại tham GIẢ ĐỊNH — CHƯA ĐO` |
| Chưa có ROI `roi_p<cổng>.png` | `p<N>: chưa có ROI …` |
| Nội tham `acceptance.all_pass` không phải `true` của JSON | `p<N>: nội tham chưa đạt tiêu chí đề xuất …` (`bev.acceptance_flag`, xem dưới bảng) |
| Tệp nội tham không có `acceptance.all_pass` (**chặt hơn** `bev.unusable_reasons`) | `p<N>: tệp nội tham không có kết quả tiêu chí …` |
| Ngoại tham hay nội tham mang dấu TỔNG HỢP | `p<N>: … là dữ liệu TỔNG HỢP — không phải số đo` |
| Khung khác cỡ ảnh đã hiệu chuẩn (mode camera khác, kể cả cùng tỉ lệ) | `p<N>: khung W×H khác cỡ ảnh đã hiệu chuẩn …` |
| Xác suất khác tỉ lệ khung của hiệu chuẩn | `không dựng được BEV: …` |
| Rig TỔNG HỢP với camera thật | `rig camera TỔNG HỢP … không bao giờ với camera thật` |

Ghi chú cho bảng:

- **Thiếu tệp ngoại tham:** lý do đi kèm các dòng tệp còn thiếu khác của MỌI camera đã chọn, theo trình tự nội tham →
  ngoại tham → ROI: `chưa có nội tham của p1, p2, … — bước 1 …`, `chưa có ROI của p1, p2, … — bước 3 …`. Cách báo này có
  từ 25/09/2026; trước đó ngăn chỉ hiện lỗi hệ điều hành của tệp ngoại tham.
- **`acceptance.all_pass` không phải `true`:** gồm false, chuỗi `"false"`/`"true"`, số `1`, và khối `acceptance` không
  phải object. Sửa ngày 25/09/2026; trước đó `bool("false")` được tính là đạt.

Lô bị chặn không thêm ô OCCUPIED nào. Lớp bản đồ bị đánh dấu không hợp lệ và cửa sổ lọc thời gian bị xóa, nên bằng
chứng không được cộng qua một lô bị chặn. Lý do hiện ở ngăn và được ghi log mỗi khi nó đổi.

**Trình tự để AI bắt đầu tạo vật cản trên bàn thật** (làm cho mỗi camera sẽ dùng):

1. Nội tham: `fisheye_calib`, ra `calibration/cam_p<cổng>.json` có `acceptance.all_pass` = true
   ([HIEU_CHUAN_CAMERA.md](HIEU_CHUAN_CAMERA.md)).
2. Gá camera, đo ngoại tham bằng bảng trên sàn, ra `configs/rig/camera_rig_extrinsics_v1.json` có `"measured": true`
   ([NGOAI_THAM_VA_ROI.md](NGOAI_THAM_VA_ROI.md) mục 1–5).
3. Mặt nạ ROI loại thân xe, dây, viền ống kính: `configs/roi/rig_v1/roi_p<cổng>.png`
   ([NGOAI_THAM_VA_ROI.md](NGOAI_THAM_VA_ROI.md) mục 6).

**Hiện trạng kiểm ngày 25/09/2026:** `calibration/` chỉ có `README.md` và `bang_in/`, `configs/rig/` chỉ có tệp v0 (GIẢ
ĐỊNH), không có `configs/roi/rig_v1/`. Phát lại bản ghi thật `o03_20260924` qua ngăn với mô hình thật (mục 8.2) cho
**1163 lô bị chặn, 0 lô dùng được, 0 vật cản**.

- Lý do hiện ra **lúc chạy lần đó**, trước khi sửa câu lý do cùng ngày, là "không đọc được tệp ngoại tham
  …camera_rig_extrinsics_v1.json: [Errno 2] …".
- Với mã hiện nay, cùng các đường dẫn mặc định cho ra ba dòng: chưa có nội tham của p1–p4 (bước 1), chưa có tệp ngoại
  tham đã đo (bước 2), chưa có ROI của p1–p4 (bước 3). Ba dòng này được kiểm bằng test với thư mục tạm (mục 8.1). Lần
  chạy lại sau các bản sửa (bảng thứ hai ở mục 8.2) cũng liệt kê đủ ba bước này.

Nút **"Nạp lại hiệu chuẩn"** có hai chế độ:

- Khi AI đang tắt, nút chỉ **kiểm** tệp của các cổng trong ô "Cổng" ở cỡ 640×480 và hiện lý do chặn biết trước (tệp
  thiếu/hỏng, ngoại tham chưa đo, thiếu ROI, nội tham chưa đạt). Nó không mở camera nào. Trước 25/09/2026 nút này bật mà
  bấm không làm gì khi AI tắt.
- Khi AI đang bật (xe không chạy), nút đọc lại tệp và dựng lại nguồn vật cản.

**Rig TỔNG HỢP** (`--camera-ai-test-rig`: camera ảo của `bev.synthetic_rig`, tư thế tệp v0, nội tham danh định) là
ngoại lệ duy nhất, chỉ để thử phần mềm. Nó chỉ chạy với bản ghi phát lại (hay nguồn giả trong test) và luôn mang nhãn
TỔNG HỢP: ở tiêu đề cửa sổ, dòng đỏ đầu ngăn, dòng trạng thái và log. Với camera thật nó bị từ chối ở ba chỗ:

- dòng lệnh báo lỗi mã 2 khi thiếu `--cam-replay`;
- ngăn từ chối bật, không mở camera nào, khi ô "Bản ghi" trống;
- nguồn vật cản chặn mọi lô khi nguồn là "live".

## 4. Tham số (mọi số là đề xuất, chưa chốt, chưa kiểm trên sa bàn)

| Tham số | Giá trị | Vì sao |
|---|---|---|
| `t_blocked` (ô ngăn "vật cản khi P ≥") | **0,15** | Ngưỡng an toàn của [HUAN_LUYEN.md](../../HUAN_LUYEN.md) mục 10 (xem dưới bảng) |
| `t_free` | 0,05 | Không đổi tập OCCUPIED (test `test_ai_threshold_maps_the_safe_015_to_t_blocked_and_t_free_does_not_change_occupied`). FREE của camera không được planner dùng |
| Lọc thời gian | ≥ 2 trong 3 lô | Như quy tắc 2/3 của LiDAR. Với AI **chưa đo** |
| Tuổi tối đa | 0,5 s | Tính từ khung CŨ nhất của lô mới nhất |
| Lề thân xe | 5 cm | Hộp thân xe của phiên nới lề, gộp với hộp `vehicle_assumed` của tệp rig |
| Hành lang quỹ đạo | 10 cm | Như ngăn LiDAR |
| Lưới BEV / tầm | ±3 m, ô 5 cm, 2 m | Mặc định của `bev` (BEV.md mục 4) |

Giải thích thêm cho từng tham số:

- **`t_blocked` = 0,15.** Ngưỡng an toàn của HUAN_LUYEN.md mục 10 là quy tắc "pixel là vật cản khi P(BLOCKED) ≥ 0,15"
  (tối đa F2 trên val WoodScape). Nguồn vật cản chỉ dùng ô OCCUPIED, nên ngưỡng này phải là `t_blocked`. Nếu giữ mặc
  định của lệnh `bev` (0,15 là `t_free`, `t_blocked` = 0,50) thì ngưỡng an toàn không còn tác dụng gì lên vật cản: vật
  cản chỉ còn từ p ≥ 0,50.
  - Cái giá: trên WoodScape test, 3,09 % pixel trống bị gọi vật cản ở 0,15 (1,37 % ở 0,50); trên ACDC tuyết là 15 %.
    Trên sa bàn **chưa đo**.
  - Số 3,97 % ghi trước ngày 30/09/2026 là nhầm: đó là 1 − precision của lớp BLOCKED, không phải tỉ lệ này.
- **Lọc 2/3:** quy tắc của LiDAR được đo trên LiDAR thật ngày 22/09 (một lần chạm gây ô chớp tắt). Ô "lần thấy" không
  vượt được ô "lô gộp": bớt số lô gộp thì số lần thấy giảm theo trên màn hình. Trước 25/09/2026 ô vẫn hiện 2 trong khi
  luật thật là 1/1.
- **Tuổi tối đa:** ngăn đọc đồng hồ **sau** khi lấy lô, nên tuổi không bao giờ âm dù luồng giao diện đứng giữa hai bước.
- **Lề thân xe:** áp trên BEV hệ xe và trong hệ bản đồ ở tư thế của từng lô (mục 1). Ô sa bàn có phần trong chung với
  hộp thân xe nới lề, hay chạm thân xe, thành UNKNOWN.
  - Bảo đảm, **kiểm bằng rig tổng hợp** ngày 25/09/2026: hộp AI không có phần trong chung với thân xe nới lề, tại tư thế
    của lô, ở 14 tư thế thử (12 ngẫu nhiên + 2 tư thế người rà dùng để tái hiện lỗi) và khi xe di chuyển giữa ba lô.
  - Với lề 0, hộp AI không chạm cả biên thân xe.

**Đặt BEV vào lưới sa bàn.** Mỗi ô sa bàn lấy mẫu 3 × 3 điểm, và là OCCUPIED nếu có điểm rơi vào ô OCCUPIED của BEV. Nhờ
vậy ô vật cản không bị mất khi xoay; đổi lại vật có thể phình tối đa một ô. `CameraSemanticLayer.set_vehicle_frame`
lấy mẫu một điểm gần nhất, và ở góc 45° có thể làm mất một ô vật cản lẻ: test
`test_one_occupied_cell_survives_any_rotation_where_nearest_sampling_can_lose_it` chỉ ra đúng một tư thế như vậy.
Vì thế `camera_ai` không dùng hàm đó (mục 10).

## 5. AI cũ hay không dùng được trong lúc xe chạy

- **Mặc định: cảnh báo, giữ vật cản đã có, xe chạy tiếp.** Mỗi loại sự cố (chưa có kết quả / quá cũ / bị chặn / lỗi bất
  ngờ khi xử lý lô) chỉ cảnh báo một lần trong một lần chạy, kể cả khi AI cũ, mới lại rồi cũ lại. Dòng trạng thái của
  ngăn vẫn hiện "CŨ" mỗi lúc. Trước 25/09/2026 mỗi đợt cũ cảnh báo lại một lần, trái với quy tắc này (người rà tái hiện
  3 đợt → 3 cảnh báo).
- **Lỗi bất ngờ không làm mất nguồn vật cản.** Tệp hiệu chuẩn hỏng kiểu lạ (ví dụ `"camera": 5`, hay gõ sai tên tệp
  ngoại tham của rig tổng hợp) thành lý do chặn thay vì ngoại lệ. Lỗi bất ngờ trong một nhịp (dựng nguồn vật cản, đọc
  lô, xử lý lô) được coi là "AI không dùng được".
  - Trước 25/09/2026 những lỗi này làm ngăn giữ một Rig đang chạy mà không có nguồn vật cản. Mọi nhịp đều ném lỗi, và
    "AI bắt buộc" không bao giờ dừng được xe.
  - Lệnh `lidar_app --camera-ai --cam-replay … --camera-ai-test-rig --extrinsics <gõ sai>` khi đó còn đổ ngay lúc khởi
    động.
- **Ô "AI bắt buộc"** được tích thì ngăn làm như ngăn LiDAR với dữ liệu cũ: yêu cầu dừng xe với lý do "AI camera không
  dùng được (…) và 'AI bắt buộc' đang bật". Tắt AI camera giữa lần chạy cũng dừng.
- **Lý do chọn mặc định này:** AI là nguồn phụ, chưa từng được chấm trên ảnh sa bàn, và có thể dừng vì những chuyện
  không liên quan tới cảnh (GPU bận, nạp mô hình, bản ghi hết). LiDAR vẫn là nguồn bắt buộc và vẫn dừng xe khi cũ. Ai
  cần AI làm nguồn bắt buộc thì bật rõ ràng. Chính sách này là đề xuất, chưa chốt.
- **Lúc chỉnh sa bàn, AI cũ không xóa hộp AI nào.** Lớp camera là lớp bắt buộc trong phép hợp nhất riêng của ngăn, nên
  bản đồ không hợp lệ và việc đồng bộ không làm gì. Lô dùng được đầu tiên sau đó cũng không xóa hộp AI khi cửa sổ lọc
  chưa đủ `min_hits` lô (test `test_filter_window_reset_while_editing_keeps_the_ai_boxes`).
- **Đổi cấu hình giữa lần chạy thì dừng xe.** Đổi ngưỡng, cửa sổ lọc, lề, cách đặt camera hay nạp lại hiệu chuẩn làm bản
  đồ đang dùng không còn là bản đồ đã lập đường. Các ô này bị khóa khi xe chạy; dừng xe là chốt chặn cuối.
- **Mã dừng trong `events.csv`** (thêm ngày 02/10/2026, T13; chỉ kiểm với bo mô phỏng và camera giả). Qua `VehicleIO`,
  mỗi yêu cầu dừng của ngăn là một dòng `session_stop` trong `events.csv`, nguồn `camera_dock`, với mã:
  - `CAMERA_AI_CONFIG_CHANGED`: đổi cấu hình lúc chạy;
  - `CAMERA_AI_DISABLED`: tắt AI;
  - `CAMERA_AI_STALE`, `CAMERA_AI_NO_RESULT`, `CAMERA_AI_BLOCKED`, `CAMERA_AI_ERROR`: AI không dùng được;
  - `CAMERA_AI_UNUSABLE`: loại "không dùng được" chưa có mã riêng (thêm sau review).

  Mọi mã trừ `CAMERA_AI_CONFIG_CHANGED` chỉ có khi tích "AI bắt buộc". Cách đọc dòng này:
  [CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) mục 5.

## 6. Hai cách đặt camera

- **"Camera cố định trên bàn"** (mặc định): hệ xe của BEV đặt ở tư thế xuất phát của sa bàn lúc còn chỉnh, rồi giữ nguyên
  khi chạy, như LiDAR đặt trên bàn. Xe ảo chạy đi nhưng camera không đi theo.
- **"Camera gắn trên xe"**: khi xe chạy (hay đã dừng sau lần chạy), ngăn dùng tư thế xe của phiên. Tư thế đó là của mô
  phỏng, hoặc của thế giới gương của `VehicleIO`; hiện chỉ có với bo mô phỏng và `SimTruthPose`.
  - Trên xe thật chế độ này chưa thử, vì cần nguồn tư thế thật. Từ 02/10/2026 đã có nguồn tư thế LiDAR (T2,
    [NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md)), nhưng mới ở mức mô phỏng và trên bản ghi C1 đứng yên; chế độ này
    chưa thử với nó.
  - Tư thế là tư thế **lúc ngăn xử lý lô**, không nội suy về lúc chụp. Sai số vị trí ≈ tốc độ xe × tuổi lô. Ví dụ tính:
    0,3 m/s × 0,1 s = 3 cm; tuổi lô đo khi phát lại ở mục 8.2 có trung vị 75 ms, p95 97 ms. Trên xe **chưa đo**.

## 7. Cách chạy (mỗi lệnh một dòng, cmd.exe, từ thư mục `autopark`)

Lệnh 1 mở LiDAR ở cổng ghi trong `configs/thiet_bi.json`; thêm `--port COMx` để ghi đè ([chuyển máy](CHUYEN_MAY_BAN.md)).

```
.venv-train\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app --camera-ai --cam-ports 1 2 3 4
.venv-train\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app --no-connect --camera-ai --cam-replay runs\rig_recordings\o03_20260924
.venv-train\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app --no-connect --camera-ai --cam-replay runs\rig_recordings\o03_20260924 --camera-ai-test-rig
.venv-train\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app --camera-ai --session-replay runs\session_recordings\<thư mục>
```

- **Lệnh 1:** bàn thử LiDAR và bốn camera thật. Ngăn "AI camera" nằm thành thẻ cạnh ngăn LiDAR. Chưa hiệu chuẩn thì
  ngăn chỉ hiện lý do bị chặn (mục 3).
  - Tùy chọn: `--checkpoint`, `--calibration-dir`, `--extrinsics`, `--roi-dir`. Ô trong ngăn đổi được trước khi bật.
  - Nút "Nạp lại hiệu chuẩn" đọc lại tệp khi xe không chạy. Khi AI còn tắt, nút đó chỉ kiểm tệp và hiện lý do chặn
    (mục 3), không mở camera nào. Dùng nút này để xem đã hiệu chuẩn đủ chưa trước khi bật.
- **Lệnh 2:** AI từ một bản ghi phiên (`rig.bench --record` hay nút "Ghi phiên" của `rig_app`), không mở camera nào; tự
  bật kể cả khi có `--no-connect`. Bản ghi chỉ cấp ảnh camera. LiDAR của bản ghi không được phát lại, nên LiDAR (cổng COM
  hay `--recording`) và AI từ bản ghi **không cùng một cảnh**. Từ 02/10/2026, `--recording <thư mục>` phát lại LiDAR
  của cùng bản ghi, nhưng trên đồng hồ riêng.
- **Lệnh 3:** như lệnh 2, với rig TỔNG HỢP. Vật cản có vị trí **vô nghĩa** với bản ghi thật (tư thế camera giả định);
  lệnh này dùng để xem luồng và đo thời gian.
- **Lệnh 4** (`--session-replay`, T3b, thêm ngày 02/10/2026): cho cả hai ngăn MỘT `ReplaySession` và một đồng hồ, nên
  LiDAR và AI cùng một cảnh. Lệnh này luôn tự bật, không dùng cùng `--recording`, `--cam-replay`, `--port`, và nhận cả
  `--camera-ai-test-rig`. Mới chỉ kiểm offscreen.
- **Môi trường:** cần `.venv-train`, vì AI dùng torch. Trong `.venv`, nút "Bật AI camera" báo "AI camera cần torch" và
  không làm gì. `--camera-ai-test-rig` không kèm `--cam-replay`, hay tùy chọn camera không kèm `--camera-ai`, bị từ chối
  với mã 2 trước khi mở cửa sổ.
- **Trình tự trên màn hình:** bật AI → hộp AI hiện trên sa bàn khi BEV dùng được → "Tìm đường đỗ" → "Bắt đầu đỗ" → vật
  mới trên đường làm xe dừng (MAP_CHANGED).
- **Ghi lại phiên** (T3, 02/10/2026): ngăn "Ghi cảm biến" ghi camera của ngăn này cùng LiDAR, kèm bảng quyết định AI
  theo lô ([GHI_PHAT_LAI_BAN_THU.md](GHI_PHAT_LAI_BAN_THU.md) mục 9).

## 8. Mức bằng chứng

Mọi kết quả dưới đây là kiểm trên máy tính: bằng test với nguồn giả, hoặc phát lại bản ghi. Chưa có kết quả nào với
camera thật đang chạy hay trên xe (mục 8.3).

### 8.1. Kiểm thử (nguồn giả, rig tổng hợp, bản ghi của nguồn giả; không thiết bị)

`tests/test_camera_ai_layer.py`, 21 hàm test (pytest đếm 45 mục, kể cả tham số hóa), không Qt:

- hộp tổng hợp 20 × 20 cm trước xe thành vật cản trong hộp ± 10 cm, có mặt hộp hướng về camera. Cần hai lô, một lô chưa
  đủ;
- camera gắn trên xe: vật cản đặt theo tư thế xe (quay 90°);
- ngưỡng: vệt sàn p = 0,30 là vật cản ở 0,15, không ở 0,50; `t_free` không đổi tập OCCUPIED;
- thân xe và lề không thành vật cản;
- lọc 2/3 (có–không–có → có; thêm hai lô trống → mất), cùng số lô không tính hai lần;
- stamp là khung cũ nhất; quá 0,5 s thì không tươi; hai lô cách 10 s thì cửa sổ lọc xóa; đếm lô bị bỏ qua;
- mặt nạ thân xe trong hệ bản đồ (thêm 25/09/2026):
  - P(BLOCKED) = 0,9 ở mọi pixel của cả bốn camera, 14 tư thế (12 ngẫu nhiên + (1,5125; 1,0125; 0) + (1,23; 0,87;
    0,4)): còn vật cản AI, không hộp nào chạm thân xe, phần giao với thân xe nới 5 cm có diện tích < 1e-9 m²;
  - lề 0 và tệp rig không có hộp thân xe, xe thẳng lưới: hộp AI không chạm cả biên thân xe;
  - xe di chuyển giữa ba lô (10 lần): 0 hộp chạm thân xe;
  - hai tường cách hông xe 5 cm, qua `ObstacleBridge` vào `Session`: chỗ xuất phát vẫn hợp lệ ở 4 tư thế. Ở ba tư thế
    không thẳng lưới AI thấy tường, ở tư thế thẳng lưới thì không (giới hạn, mục 9);
- rig "thật" viết tay (không dấu tổng hợp) đủ điều kiện thì tạo vật cản cả với nguồn "live". Tám biến thể thiếu một
  điều kiện (ROI, đo, `all_pass` = false, `all_pass` là chuỗi `"false"`, chuỗi `"true"`, số `1`, không có `acceptance`,
  tổng hợp) thì bị chặn, đúng lý do, 0 ô OCCUPIED. Khối `acceptance` là chuỗi: không ném, bị chặn "chưa đạt";
- rig không nạp được (thiếu tệp ngoại tham, thiếu nội tham, cổng không có trong tệp) bị chặn với lý do của tệp:
  - thiếu hết: ba dòng đúng trình tự nội tham → ngoại tham → ROI, không có "Errno";
  - tệp ngoại tham hỏng: "không đọc được tệp ngoại tham";
  - rig tổng hợp gõ sai tên tệp, và tệp nội tham có `"camera": 5` (TypeError): hàm nạp không ném, mọi lô bị chặn;
- lý do biết trước khi có lô AI (`preflight_reasons`, cho nút "Nạp lại hiệu chuẩn" lúc AI tắt): rig đủ → rỗng; thiếu ROI,
  `all_pass` chuỗi, không có `acceptance` → đúng lý do; rig tổng hợp với "live" → từ chối;
- bản đồ xác suất 16:9 (khác tỉ lệ hiệu chuẩn) và khung 320×240 (cùng 4:3, khác cỡ hiệu chuẩn) bị chặn, cửa sổ lọc bắt
  đầu lại;
- rig tổng hợp bị từ chối với "live", được phép với "replay"/"fake" kèm nhãn TỔNG HỢP;
- đặt BEV vào lưới: 150 tư thế ngẫu nhiên, một ô vật cản không bao giờ mất và phình tối đa một ô; lấy mẫu gần nhất
  làm mất nó ở tư thế 45° đã chọn.

`tests/test_camera_dock_ui.py`, offscreen. Lúc viết ngày 25/09/2026 tệp có 20 hàm test (23 mục). Ngày 02/10/2026 thêm ba
hàm (T6, T13 và một hàm sau review), lên 23 hàm, 30 mục; sau đó thêm một hàm của T3, nay 24 hàm, 31 mục (đếm bằng
`--collect-only`). Các phép kiểm:

- phát lại một phiên ghi từ camera giả (Rig thật, PNG 640×480) với rig tổng hợp: hộp AI hiện trên sa bàn lúc chỉnh, đúng
  chỗ. Hộp LiDAR và hộp người dùng ở chỗ camera thấy sàn trống không bị đụng tới. Hết bản ghi thì ngăn ghi "CŨ", hộp
  AI được giữ. "Xóa vật AI" chỉ xóa hộp AI;
- camera giả chạy liên tục: hộp đã biết lúc lập đường không làm dừng xe. Hộp mới đặt lên đường lúc chạy làm phiên
  STOPPING, có MAP_CHANGED, rồi xe dừng hẳn không va chạm;
- AI cũ lúc chạy: mặc định một cảnh báo, xe vẫn chạy, giữ hộp. Tích "AI bắt buộc" thì dừng, lý do nêu "AI camera" và
  "AI bắt buộc";
- (thêm 02/10/2026, T6) camera giả duy nhất THẬT SỰ ngừng trả khung (STALL của `FreezeSwitch`, cài trước khi dựng Rig,
  không dời đồng hồ như test trên): AI cũ sau ≈ 0,5 s, một cảnh báo, xe vẫn chạy, giữ hộp; tích "AI bắt buộc" thì
  STOPPING, lý do "AI camera … quá cũ" (`test_frozen_camera_makes_the_ai_stale_then_required_ai_stops_the_run`);
- (thêm 02/10/2026, T13) qua `VehicleIO` (bo mô phỏng), yêu cầu dừng của ngăn là dòng `session_stop` đầu tiên của
  `events.csv`, với đúng mã và nguồn `camera_dock`: AI quá cũ, tắt AI, lỗi bất ngờ khi xử lý lô, đổi cấu hình lúc chạy.
  Sau review thêm ca loại "không dùng được" chưa có trong bảng mã, dừng với `CAMERA_AI_UNUSABLE`; trước đó ca này gây
  `KeyError` trong timer và xe không dừng (`test_ai_stop_in_vehicle_io_is_logged_with_its_code`, 5 mục);
- (thêm 02/10/2026, sau review) mọi loại "không dùng được" mà ngăn truyền đi đều có mã dừng riêng
  (`test_every_unusable_kind_used_by_the_dock_has_its_own_stop_code`);
- rig tổng hợp: không có bản ghi thì từ chối bật, không gọi `resolve_ports`; nguồn khai "live" thì chặn mọi lô, 0 hộp;
- rig thật không có tệp hiệu chuẩn: 0 hộp, lý do hiện ở ngăn và log, theo trình tự HIEU_CHUAN_CAMERA → NGOAI_THAM_VA_ROI
  mục 1 → mục 6, không có "Errno";
- (thêm 25/09/2026) rig camera hỏng lúc bật (rig tổng hợp gõ sai tên tệp ngoại tham; tệp nội tham `"camera": 5`; hàm nạp
  ném lỗi bất ngờ): `attach_rig` không ném, nguồn vật cản bị chặn, nút ghi "Tắt AI camera", lý do hiện ở ngăn. Chạy với
  "AI bắt buộc" thì phiên STOPPING;
- lỗi bất ngờ khi xử lý lô lúc chạy: cảnh báo đúng một lần, xe vẫn chạy; tích "AI bắt buộc" thì STOPPING;
- luồng giao diện "đứng" giữa lúc lấy lô và lúc đọc đồng hồ (lô mới có khung chụp sau lúc gọi): lô không bị coi là cũ,
  xe không dừng dù "AI bắt buộc" đang bật;
- cửa sổ lọc bị xóa lúc chỉnh sa bàn (giao diện đứng 0,7 s; đổi ngưỡng): hộp AI giữ nguyên id qua 8 nhịp; vật mất thật
  thì hộp AI vẫn được bỏ;
- cảnh báo: AI cũ → mới → cũ ba đợt trong một lần chạy chỉ cho một cảnh báo; loại khác (lỗi) cảnh báo riêng một lần;
- ô "lần thấy" không vượt ô "lô gộp" và hiện đúng luật đang dùng;
- hai cách đặt camera: xe đi hơn 40 cm rồi đặt hộp mới trước camera. "Camera gắn trên xe": hộp theo tư thế xe, không theo
  chỗ xuất phát; "Camera cố định trên bàn": ngược lại. Cả hai dừng xe qua MAP_CHANGED;
- tắt AI camera giữa lần chạy: mặc định xe chạy tiếp, giữ hộp; với "AI bắt buộc" thì dừng. Các ô cấu hình và hiệu chuẩn,
  nút "Nạp lại hiệu chuẩn" bị khóa khi chạy;
- bỏ "Vật mới trên đường làm xe dừng": hộp mới trên đường không dừng xe; bật lại thì dừng;
- bỏ "Vật cản bám theo AI": hộp AI đứng yên khi AI thấy vật ở chỗ khác; bật lại thì bám theo;
- nhãn đỏ TỔNG HỢP nằm trong bố cục ngay sau dòng ghi công;
- bật AI thật khi không có torch → "AI camera cần torch"; có torch mà thiếu tệp mô hình → "Không có tệp mô hình …". Cả
  hai không dựng Rig, không mở nguồn nào (giả `find_spec` nên chạy được hai nhánh trong cả `.venv` lẫn `.venv-train`);
- "Nạp lại hiệu chuẩn" lúc AI tắt: kiểm tệp, hiện lý do (thiếu ROI; đủ và đạt; thiếu tệp ngoại tham), không dựng Rig,
  không mở camera;
- `lidar_app` không có tùy chọn camera: không có ngăn camera, không nhập torch, `camera_dock` hay `camera_ai`. Dùng sai
  tùy chọn trả mã 2 trước khi mở cửa sổ;
- tùy chọn camera: ngăn xếp thành thẻ cạnh ngăn LiDAR, tiêu đề ghi RIG TỔNG HỢP, đường dẫn mặc định đúng;
- (02/10/2026, T3) `test_on_batch_hook_runs_after_safety_decisions_and_its_errors_stay_in_the_dock`: móc `on_batch` của
  bản ghi cảm biến chạy sau mọi quyết định an toàn, mỗi lô một lần. Lỗi trong móc chỉ để lại một dòng nhật ký, vật cản
  AI vẫn được chèn và xe vẫn dừng. Hai phép kiểm bố cục ngăn đổi có chủ đích, vì có thêm ngăn "Ghi cảm biến" xếp thẻ
  cạnh ngăn LiDAR. Phát lại chung một đồng hồ được kiểm ở `tests/test_session_replay_ui.py`.

**Đột biến.** Ngày 25/09/2026, sau các bản sửa ở trên, chạy thử đột biến trên **bản sao** trong thư mục tạm bằng
`.venv-train`: **46/46** đột biến làm test hỏng. Script nằm trong thư mục tạm của phiên, không nằm trong repo.

- 20 đột biến cũ, chuỗi cập nhật theo mã mới: bỏ từng điều kiện chặn, cho rig tổng hợp chạy với camera thật, bỏ kiểm cỡ
  khung, lọc 1/3, bỏ xóa cửa sổ (cách quãng dài / lô bị chặn), stamp = khung mới nhất, lấy mẫu gần nhất, bỏ mặt nạ thân
  xe của phiên, ngưỡng 0,50, dừng xe mặc định khi AI cũ, "AI bắt buộc" không dừng, không chèn khi chạy, cầu nối dùng
  tiền tố `lidar`, không đồng bộ lúc chỉnh, rig tổng hợp mở camera thật, lớp camera tùy chọn, `lidar_app` nhập ngăn
  camera ngay đầu mô-đun, `--camera-ai-test-rig` không cần `--cam-replay`.
- 26 đột biến mới: bỏ mặt nạ hệ bản đồ; bỏ luật "chạm thân xe"; dùng `intersects` trần cho hộp nới lề; `bool()` cho
  `all_pass`; khối `acceptance` không phải object thì ném; hàm nạp rig thật chỉ bắt ba loại lỗi; rig tổng hợp ném khi
  thiếu tệp; bỏ danh sách tệp còn thiếu; ngăn nạp rig không bắt lỗi; nhịp không bắt lỗi; đọc đồng hồ trước khi lấy lô;
  đồng bộ cả khi cửa sổ lọc chưa đủ lô; cảnh báo lại mỗi đợt; ô "lần thấy" không bị giới hạn; "Nạp lại hiệu chuẩn" không
  làm gì khi AI tắt; trạng thái hiện trước khi đồng bộ; bỏ chế độ "camera gắn trên xe"; chế độ bàn thử cũng theo xe; tắt
  AI không bao giờ / luôn luôn dừng xe; bỏ qua ô "Vật mới trên đường làm xe dừng"; bỏ qua ô "Vật cản bám theo AI"; không
  khóa ô hiệu chuẩn khi chạy; nhãn TỔNG HỢP không trong bố cục; bỏ kiểm torch; bỏ kiểm tệp mô hình.

### 8.2. Phát lại bản ghi thật với mô hình thật (máy bàn, 25/09/2026)

Phép đo này chạy ngăn với mô hình thật trên một bản ghi thật của bàn thử, không mở thiết bị nào.

- Bản ghi `runs/rig_recordings/o03_20260924`: 4 camera 640×480, 60 s, camera nhìn chỗ tối
  ([GHI_PHAT_LAI_BAN_THU.md](GHI_PHAT_LAI_BAN_THU.md) mục 7), không phải sa bàn.
- Ngăn chạy offscreen trong `.venv-train`, mô hình `ai_woodscape_rtx4000_v1` trên CUDA.
- Timer 50 ms của ngăn được thay bằng một vòng gọi `tick()` rồi ngủ 50 ms (script tạm, không nằm trong repo).

Lần chạy đầu: máy có các tác tử khác chạy song song, tải máy không được kiểm soát. Số đo **trước** các bản sửa cùng ngày ở
mục 1, 3, 5 (mặt nạ thân xe trong hệ bản đồ, câu lý do thiếu tệp, thứ tự đọc đồng hồ…).

| | Rig thật (đường dẫn mặc định) | Rig TỔNG HỢP (`--camera-ai-test-rig`) |
|---|---|---|
| Lô AI của Rig | 1431 (23,8 lô/s) | 1431 (23,8 lô/s) |
| Lô ngăn xét / bị chặn / dùng được | 1163 / 1163 / 0 | 969 / 0 / 969 |
| Lô ra giữa hai lần xét (bỏ qua) | 267 | 462 |
| Vật cản AI trên sa bàn | 0 | tối đa 22 hộp, vị trí **vô nghĩa** |
| BEV 4 camera (trung vị / p95 / max) | — | 5,6 / 8,0 / 11,7 ms |
| Một `tick()` (trung vị / p95 / max) | 1,1 / 1,8 / 11,6 ms | 10,9 / 14,5 / 17,8 ms |
| Tuổi lô lúc ngăn dùng (trung vị / p95) | — | 75 / 97 ms |
| Dựng bảng hình học BEV lúc bật | — | 297 ms |

Chạy lại sau các bản sửa, cùng ngày 25/09/2026: cùng máy, cùng script, máy không còn tác tử nào khác chạy; `.venv-train`,
mã chưa commit trên `89cd58f`. Số gần như không đổi:

| | Rig thật (đường dẫn mặc định) | Rig TỔNG HỢP |
|---|---|---|
| Lô AI của Rig | 1431 (23,8 lô/s), một lô trung vị 12,4 ms | 1431 (23,8 lô/s), một lô trung vị 12,9 ms |
| Lô ngăn xét / bị chặn / dùng được | 1163 / 1163 / 0 | 967 / 0 / 967 |
| Lô ra giữa hai lần xét (bỏ qua) | 268 (18,7 %) | 464 (32,4 %) |
| Vật cản AI trên sa bàn | 0 | tối đa 19 hộp, cuối phiên 17, vị trí **vô nghĩa** |
| BEV 4 camera (trung vị / p95 / max) | — | 5,6 / 8,1 / 10,4 ms |
| Một `tick()` (trung vị / p95 / max) | 1,2 / 1,8 / 9,2 ms | 11,0 / 14,7 / 19,1 ms |
| Tuổi lô lúc ngăn dùng (trung vị / p95) | — | 76,5 / 97,7 ms |

Lý do chặn với rig thật ở lần chạy lại liệt kê đủ ba bước còn thiếu theo thứ tự: nội tham của p1–p4 (bước 1,
HIEU_CHUAN_CAMERA.md), tệp ngoại tham đo `configs/rig/camera_rig_extrinsics_v1.json` (bước 2), ROI của p1–p4 (bước 3,
NGOAI_THAM_VA_ROI.md).

Đọc kết quả:

- Luồng chạy trọn với mô hình thật. Trên dữ liệu thật hiện nay, AI bị chặn, đúng như thiết kế.
- Mặt nạ hệ bản đồ (`camera_ai.ego_cells`) đo tách riêng trên máy bàn ngày 25/09/2026: trung vị 0,30 ms, p95 0,39 ms mỗi
  lô (200 lần, sa bàn 3 × 2 m). Sa bàn 10 × 10 m cũng ≈ 0,3 ms, vì chỉ xét các ô quanh xe.
- Ngăn chỉ xét lô mới nhất ở mỗi nhịp. Với 23,8 lô/s, ≈ 19 % lô (rig thật) và ≈ 32 % lô (rig TỔNG HỢP, vì mỗi lần xét
  lâu hơn) không được xét. Script phát lại ngủ 50 ms sau mỗi `tick()` thay cho timer, nên tỉ lệ với timer thật của giao
  diện **chưa đo**. "2 trong 3 lô" vì thế là 2 trong 3 lô ngăn đã xét, không phải 3 lô liên tiếp của AI.
- 22 hộp ở cột tổng hợp là pixel mà mô hình gọi BLOCKED (p ≥ 0,15) trong cảnh tối, chiếu bằng tư thế GIẢ ĐỊNH. Chúng không
  nói được gì về độ đúng; chỉ cho thấy mô hình có gọi vật cản trên ảnh bàn thử thật.
- Laptop RTX 3050 Ti: **chưa đo**.

### 8.3. Chưa thử, chưa đo

- Chưa chạy với camera thật đang mở. Chưa chạy trên xe.
- Lệnh dừng của ngăn mới chạy qua `VehicleIO` với bo mô phỏng và camera giả trong test (02/10/2026, mục 8.1); với bo thật
  chưa thử.
- Chưa có camera nào được hiệu chuẩn.
- Chưa đo sai số vị trí vật cản AI trên sa bàn.
- Chưa đo tỉ lệ báo động giả hay bỏ sót của AI trên ảnh sa bàn.
- Chưa đo độ trễ từ lúc vật xuất hiện tới lúc xe dừng.

## 9. Giới hạn

- **BEV giả định mặt sàn phẳng** (BEV.md mục 3). Chỉ mặt vật hướng về camera là OCCUPIED, phần sau bị che. Vật nhô ra
  (mặt bàn, cản xe) bị lệch.
- **AI chưa từng được chấm trên ảnh sa bàn.** Mô hình học trên đường phố WoodScape. Ảnh sa bàn là miền khác hẳn: tỉ lệ
  1/12, sàn, ánh sáng trong phòng, camera rẻ. Số của HUAN_LUYEN.md mục 10 không chuyển sang được.
- **Vật cản giả làm xe dừng giả.** Đây là hướng an toàn, nhưng có thể làm xe không đỗ được. Ngưỡng 0,15 được chọn để ít
  bỏ sót, đổi lại nhiều báo giả hơn (mục 4).
- **Bỏ sót không được AI bù.** AI chỉ thêm vật cản. Chỗ AI gọi trống hay không thấy thì chỉ LiDAR bảo vệ. Camera thiếu
  trong một lô thì vùng chỉ nó thấy là UNKNOWN, không thành vật cản.
- **Vật trong lề quanh xe là vô hình với AI.** Mặt vật hướng về camera nằm trong lề (5 cm) bị bỏ, và phần sau bị chính
  mặt đó che (test `test_car_body_and_margin_never_become_obstacles`).
  - Mặt nạ trong hệ bản đồ làm việc theo ô 5 cm: ô sa bàn nào có phần trong chung với vùng lề đều bị che. Vì vậy, tùy tư
    thế xe so với lưới, mặt vật cách thân xe tới **lề + một ô (khoảng 10 cm, hơn chút khi xe xiên)** có thể bị che.
  - Ví dụ đã kiểm (rig tổng hợp, 25/09/2026): xe thẳng lưới ở (0,5; 1,0), hai tường dọc hông xe cách đúng 5 cm → AI
    không thấy tường. Ở ba tư thế không thẳng lưới AI thấy tường, và hộp AI không làm chỗ xuất phát "va chạm" (test
    `test_walls_five_cm_beside_the_car_do_not_put_the_start_in_collision`).
  - Sát xe chỉ LiDAR bảo vệ. Hướng sai này là **bỏ sót**, đổi lấy việc AI không bao giờ tự chặn chỗ xe đang đứng.
- **Tư thế không nội suy về lúc chụp** (mục 6). Lọc 2/3 làm trong hệ bản đồ, nên sai số tư thế trên xe chạy có thể làm ô
  không đủ 2 lần thấy. **Chưa đo.**
- BEV chạy trên luồng giao diện: ≈ 11 ms mỗi nhịp có lô mới trên máy bàn (mục 8.2).
- Stamp là lúc khung tới máy, không phải lúc phơi sáng (như bàn thử).
- Lúc chỉnh sa bàn, hộp AI bám theo AI: hộp AI biến mất khi AI không còn thấy vật ở ≥ 2 trong 3 lô. Điều này chỉ áp cho
  hộp AI; hộp của nguồn khác không bao giờ bị động tới. Sau khi cửa sổ lọc bị xóa (đổi cấu hình, lô bị chặn, hai lô cách
  nhau > 0,5 s), hộp AI được giữ nguyên tới khi cửa sổ có đủ `min_hits` lô, không biến mất một lô rồi hiện lại với id
  mới (test `test_filter_window_reset_while_editing_keeps_the_ai_boxes`).
- Mặt nạ thân xe trong hệ bản đồ chỉ áp ở tư thế của **từng lô**, như ngăn LiDAR chỉ che theo từng scan. Với camera trên
  xe đang chạy, ô của lô cũ trong cửa sổ lọc không bị che lại theo tư thế mới. Thử bằng rig tổng hợp (xoay 0,25 rad và
  tịnh tiến 4 cm mỗi lô, 10 tư thế): 0 hộp chạm thân xe. Che thêm theo tư thế hiện tại có thể giấu bằng chứng về một vật
  thật xe vừa chạm tới, nên việc này để lại làm đề xuất, chưa chốt (mục 10).
- (02/10/2026, T3) Bản ghi cảm biến lưu QUYẾT ĐỊNH của ngăn theo lô (`session/ai_batches.csv`: dùng được hay bị chặn, lý
  do, số hộp AI, số vật đã chèn), không lưu bản đồ xác suất. Khe hở của `batch_id` là các lô mà timer 50 ms không kịp
  xét. Phát lại chạy lại AI trên ảnh JPEG đã mã hóa lại, nên kết quả không trùng từng bit.

## 10. Đề xuất (chưa chốt)

1. Chốt `t_blocked` = 0,15, lọc 2/3, tuổi 0,5 s, lề 5 cm sau khi chấm AI trên ảnh sa bàn có nhãn
   ([GAN_NHAN_SA_BAN.md](GAN_NHAN_SA_BAN.md)).
2. Chốt chính sách "AI bắt buộc" (mặc định tắt). Nếu kịch bản nghiệm thu dựa vào AI thì phải bật.
3. Ngăn kiểm checkpoint: chỉ nhận lượt chỉ WoodScape. Quyết định giấy phép 25/09 không phủ AVM-SS.
4. `CameraSemanticLayer.set_vehicle_frame` (`fusion/layers.py`): đổi sang lấy mẫu bảo thủ như
   `camera_ai.vehicle_states_to_map`, hoặc ghi rõ giới hạn trong docstring. `camera_ai` không dùng hàm đó.
5. Trên xe: nội suy tư thế theo stamp khung khi có lịch sử tư thế; lọc 2/3 chịu lệch một ô.
6. Xét mọi lô AI (hàng đợi, hay chạy BEV trong luồng AI) thay vì lô mới nhất mỗi 50 ms. Đo trên laptop trước.
7. Ghép camera và LiDAR của cùng một bản ghi phiên khi phát lại. **Đã làm ngày 02/10/2026:** `ui.lidar_app
   --session-replay` (T3b, mục 7, lệnh 4) dùng một `ReplaySession`, một đồng hồ cho cả hai ngăn; mới chỉ kiểm offscreen.
8. Camera trên xe đang chạy: có che thêm cửa sổ lọc theo tư thế hiện tại của xe hay không (mục 9). Hiện không che.
