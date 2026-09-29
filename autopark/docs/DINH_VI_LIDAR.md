# Định vị LiDAR trên bản đồ tĩnh đã lưu (giai đoạn 1, bước 6) — 24/09/2026

**Kế hoạch đối chiếu:** [v3.1 mục 5 "Khi nhận LiDAR"](../../KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md), bước 6: *"Nạp lại
bản đồ, thử định vị tại các vị trí có tham chiếu độc lập. Tách 'đọc scan được', 'tạo map được' và 'định vị lại được'
thành ba kết quả."* Điều kiện chuyển bước liên quan: *"Có dữ liệu và phép thử lưu/nạp bản đồ; phần định vị chưa đạt
được báo riêng."*

**Mức bằng chứng:** chỉ có dữ liệu tổng hợp (test) và ba bản ghi thật có sẵn từ ngày 22/09 và 24/09. Ngày 24/09 không
chạy thiết bị nào *(cập nhật 25/09/2026: câu này chỉ nói phần việc định vị, chạy offline. Ngày 24/09 vẫn có phiên
thiết bị: k01 ghi trên máy bàn ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 3b), và phiên bàn thử o03 tối
24/09 có LiDAR ([GHI_PHAT_LAI_BAN_THU.md](GHI_PHAT_LAI_BAN_THU.md) mục 7))*. **Chưa có tham chiếu độc lập**:
không có lần nào LiDAR được đặt ở vị trí đo bằng thước. Vì vậy mọi con số ở mục 5 là độ **nhất quán** (cùng chỗ thì
ra cùng tư thế, khác chỗ thì báo hỏng), không phải độ **đúng** so với thực tế. Mọi ngưỡng chấp nhận là giá trị tạm,
**CHƯA CHỐT**.

**Không phải:** SLAM (bản đồ không được cập nhật khi định vị), odometry (không cộng dồn chuyển động), định vị trên xe
thật (chưa có xe). *(Cập nhật 25/09/2026: odometry khớp scan nay là mô-đun riêng `lidar/scan_odometry.py`
(`a7cec5e`); so sánh các phương án định vị ở [SO_SANH_DINH_VI_SLAM.md](SO_SANH_DINH_VI_SLAM.md).)*

Mã: [`autopark/lidar/localize.py`](../autopark/lidar/localize.py). Test:
[`tests/test_lidar_localize.py`](../tests/test_lidar_localize.py). Bản đồ do
[`autopark/lidar/occupancy.py`](../autopark/lidar/occupancy.py) dựng ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 5).

## 1. Ba kết quả tách riêng

| Kết quả | Công cụ | Trạng thái 24/09/2026 |
|---|---|---|
| Đọc scan được | `lidar/rplidar_c1.py`, `lidar/recording.py` | Có, trên máy bàn, 22/09 và 24/09 ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 3, 3b) |
| Tạo map được | `lidar/occupancy.py` → `costmap.json` | MỘT PHẦN (như [gate_01.md](gate_01.md)): `map_p07` là bản đồ lưới tĩnh từ bản ghi p07 (22/09) ở một vị trí cố định, không phải SLAM, chưa đo sai số bản đồ. Dựng lại ngày 24/09 bằng mã hiện tại (tầm 8 m và 12 m) cho lưới giống hệt từng ô. *(Sửa tối 24/09/2026: trước ghi "Có".)* |
| Định vị lại được | `lidar/localize.py` (tài liệu này) | Có công cụ. Trên bản ghi thật: nhất quán ở cùng chỗ, báo hỏng ở chỗ khác (mục 5). **Chưa đạt** theo nghĩa của kế hoạch vì chưa có vị trí tham chiếu độc lập (mục 7) |

## 2. Cách làm

Đầu vào: một bản đồ `costmap.json` (lưới UNKNOWN / FREE / OCCUPIED, ô 5 cm, cùng bố cục với costmap camera) và một vòng
quét (góc theo quy ước dự án, NaN = không phản hồi). Đầu ra: tư thế tâm quay LiDAR `(x, y, θ)` trong hệ bản đồ, kèm trạng
thái OK / AMBIGUOUS / FAILED và lý do. Với bản đồ `occupancy.py` dựng khi cảm biến đứng yên, hệ bản đồ chính là hệ cảm
biến lúc ghi bản đồ, nên "cùng chỗ, cùng hướng" nghĩa là tư thế ≈ (0, 0, 0°).

1. **Trường khoảng cách và trường khả năng.** Tính khoảng cách Euclid từ tâm mỗi ô tới tâm ô OCCUPIED gần nhất
   (`cv2.distanceTransform`, mặt nạ chính xác). Mỗi điểm chạm nhận `exp(-d²/2σ²)`. Nếu điểm rơi vào ô FREE cách vật cản
   quá `match_dist_m` thì nhận `-free_penalty`, vì lúc dựng bản đồ tia đã đi xuyên qua ô đó. Ô UNKNOWN và vùng ngoài lưới
   nhận 0: không có bằng chứng theo hướng nào.
2. **Khớp tương quan trên lưới rời rạc.** Tìm trong cửa sổ `±wx, ±wy, ±wθ` quanh tư thế ban đầu. Bước tịnh tiến bằng một
   ô. Bước góc chọn sao cho điểm xa nhất dịch không quá một ô (≈ 0,36° với điểm xa 8 m). Dùng nhánh-cận nhiều mức theo
   cách của Cartographer: ở mức k, trường đã lấy max theo khối 2^k × 2^k, nên điểm của một khối là cận trên đúng cho mọi
   tư thế con. Cắt nhánh vì thế không làm mất nghiệm; `test_branch_and_bound_equals_exhaustive_search` so với duyệt
   hết. Có hai pha. Pha 1 chỉ tìm đỉnh nhất. Pha 2 liệt kê đủ mọi tư thế có điểm ≥ `keep_ratio` × đỉnh nhất để tìm
   **đỉnh thứ hai**, tức đỉnh cách đỉnh nhất hơn 15 cm hoặc 5°. Pha 2 được bỏ qua khi tư thế đã hỏng vì không khớp bản
   đồ: kết quả đằng nào cũng FAILED, mà cảnh không khớp làm mặt điểm phẳng nên phép liệt kê rất chậm.
3. **Tinh chỉnh cục bộ.** Gauss-Newton có giảm chấn Levenberg-Marquardt và trọng số Cauchy, trên trường khoảng cách nội
   suy song tuyến. Kết quả là tư thế dưới một ô và ma trận Hessian `JᵀWJ`. Hiệp phương sai lấy là `s²·(JᵀWJ)⁻¹`.
4. **Kiểm từng tia ở tư thế tìm được:**
   - *khớp*: điểm chạm cách ô OCCUPIED không quá `match_dist_m`;
   - *mâu thuẫn ngắn*: điểm chạm rơi vào ô FREE, do vật mới hoặc tư thế sai;
   - *mâu thuẫn xuyên tường*: tia đi qua lõi một ô OCCUPIED của bản đồ, trước điểm chạm hơn 15 cm, tức bản đồ có vật ở
     đó mà tia vẫn đi qua. Lõi là vùng có khoảng cách nội suy dưới ¼ ô, để tia sượt mép tường không bị tính. Hai ô
     OCCUPIED chéo nhau (chỉ chạm góc) được nối bằng đoạn giữa hai tâm, và tia được lấy mẫu mỗi ¼ ô. Phép kiểm bắt
     đầu từ `min_range_m`. *Sửa 24/09/2026:* bản đầu lấy mẫu mỗi ½ ô và không nối ô chéo. Ở góc chung của hai ô chéo,
     khoảng cách nội suy là ½ ô, nên tường chéo (bậc thang 8-liên thông) có khe. Đo lại ngày 24/09 bằng script tạm: tia
     qua tường 45° dựng tay (ô chỉ chạm góc) chỉ bị bắt 15 %. Với tường dựng bằng đường bản đồ thật cách gốc 1,513 m,
     tường 45° bị bắt 52 %, tường 30° và 60° bị bắt 90–96 %, tường 0° và 10° bị bắt 100 %. Cùng tường 45° đặt ở 1,50 m thì
     bị bắt 100 %, nên kết quả tùy vị trí tường so với lưới. Mã mới bắt 100 % ở mọi ca trên. Tường chéo xảy ra thật: hệ bản đồ là
     hệ cảm biến lúc ghi, nên LiDAR đặt xiên so với phòng cho tường chéo. Hai test tường 45° giữ bản sửa (mục 4). Trên
     ba bản ghi thật, bản sửa không đổi kết luận vòng nào (mục 5). Chưa có ca nào cho thấy lỗi cũ từng làm ra một kết
     quả OK sai, vì `low_match_fraction` vẫn bắt được các ca thử;
   - *không kiểm được*: điểm chạm ở ô UNKNOWN hoặc ngoài lưới mà không xuyên tường.

   Tỉ lệ khớp tính trên **mọi tia hợp lệ**, kể cả tia ra ngoài bản đồ. Nhờ vậy không thể đẩy điểm ra ngoài bản đồ để
   có tỉ lệ đẹp. Ban đầu mẫu số chỉ gồm tia có điểm chạm trong lưới. Khi đó phép tìm toàn cục đặt một hội trường tròn
   lên bản đồ phòng và trả **OK** (110 tia khớp / 157 tia trong lưới). Lỗi này được sửa trước khi viết tài liệu, và
   `test_scan_from_another_room_fails_even_with_global_search` giữ cho nó không quay lại.

### Quy tắc kết luận (ngưỡng tạm, CHƯA CHỐT)

| Lý do | Điều kiện | Kết luận |
|---|---|---|
| `too_few_beams` | < 50 tia hợp lệ (0,25–8 m) | FAILED, không tìm |
| `no_overlap` | không tia nào kiểm được với bản đồ (khớp + mâu thuẫn = 0), ví dụ `--initial` sai hẳn hoặc nhầm bản đồ. *Thêm 24/09/2026* | FAILED, dù nới mọi ngưỡng khác |
| `few_matched` | < 50 tia khớp | FAILED |
| `low_match_fraction` | tia khớp / tia hợp lệ < 0,6 | FAILED |
| `conflicts_with_map` | mâu thuẫn / (khớp + mâu thuẫn) > 0,25. Khi khớp + mâu thuẫn = 0 thì tỉ lệ lấy là 0 và lý do là `no_overlap`. *Sửa 24/09/2026:* trước đó tỉ lệ lấy là 1,0, nên ca "không chồng lên bản đồ" bị báo `conflicts_with_map` trong khi có 0 mâu thuẫn | FAILED |
| `window_edge` | đỉnh rời rạc nằm ở mép cửa sổ (x, y hoặc θ): nghiệm thật có thể ở ngoài | FAILED |
| `second_peak` | đỉnh thứ hai / đỉnh nhất ≥ 0,9 | AMBIGUOUS |
| `degenerate` | độ lệch chuẩn Hessian: trục lớn của (x, y) > 5 cm, hoặc θ > 2° (kể cả khi suy biến hẳn) | AMBIGUOUS |
| `search_truncated` | một mức có quá 300.000 ứng viên, phải cắt bớt, nên không còn bảo đảm tìm đủ | AMBIGUOUS |
| `refine_unstable` | tinh chỉnh rời đỉnh rời rạc quá 15 cm hoặc 5° (giữ lại đỉnh rời rạc) | AMBIGUOUS |

Chỉ tư thế **OK** mới được dùng tiếp. Tư thế AMBIGUOUS và FAILED vẫn được ghi ra để chẩn đoán.

### Tham số (`LocalizeConfig`)

| Tham số | Mặc định | Ghi chú |
|---|---|---|
| `sigma_m` | 0,05 m | Độ rộng Gauss của trường khả năng, bằng một ô |
| `free_penalty` | 0,5 | Phạt điểm chạm trong ô FREE (chỉ dùng khi tìm) |
| `match_dist_m` | 0,10 m | Ngưỡng "khớp" |
| `min_range_m` / `max_range_m` | 0,25 / 8 m | Bỏ phản hồi sát cảm biến: bản ghi thật có tia 0,09–0,17 m ở −70…−22°, nghi là dây ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 3b). Tia này gắn liền với cảm biến nên sẽ "khớp" ở gốc bất kể cảm biến ở đâu |
| cửa sổ | ±0,5 m, ±0,5 m, ±30° | `--window`; `--global` = cả bản đồ, 360°. Ba giá trị phải hữu hạn và ≥ 0: DTHETA 0 = chỉ một hướng, ≥ 180° = cả vòng. Giá trị âm, NaN hoặc vô hạn bị từ chối: CLI thoát mã 2 trước khi nạp gì, hàm Python ném `ValueError` (thêm 24/09/2026; trước đó DX/DY âm hỏng giữa chừng với lỗi numpy, DTHETA âm lặng lẽ tắt phép tìm góc) |
| `levels` | 4 (khối 1–8 ô); `--global`: 5 | |
| `keep_ratio` | 0,8 | Mọi đỉnh ≥ 0,8 × đỉnh nhất đều được liệt kê |
| `peak_sep_m` / `peak_sep_deg` | 0,15 m / 5° | Thế nào là "một đỉnh khác" |

## 3. Lệnh

Chạy trong `autopark`, bằng `.venv` (cần numpy, opencv; không cần torch hay shapely). Chạy được cả bằng `.venv-train`.
Mỗi lệnh nằm trên một dòng, dán được nguyên vào cả cmd.exe lẫn PowerShell (*sửa 24/09/2026:* bản trước xuống dòng
bằng `\` của bash và gọi `python` trần, dán vào cmd.exe hay PowerShell đều hỏng).

```
.\.venv\Scripts\python.exe -X utf8 -m autopark.lidar.occupancy --recording runs/lidar_bench/20260922/p07_nen_phong.npz --out <thư mục bản đồ>
.\.venv\Scripts\python.exe -X utf8 -m autopark.lidar.localize --map runs/lidar_bench/20260922/map_p07 --recording runs/lidar_bench/20260922/live_headless.npz --out <thư mục kết quả>
```

Thay `<...>` bằng thư mục thật trước khi chạy. Tùy chọn thêm vào cuối lệnh: `--initial X Y THETA_DEG`,
`--window DX DY DTHETA_DEG` hoặc `--global`, `--track`, `--skip-seconds S`, `--every N`, `--limit N`, `--levels L`,
`--min-range M`, `--max-range M`. `--window` nhận giá trị ≥ 0 (mục 2, bảng tham số).

Mỗi vòng quét được định vị độc lập quanh `--initial`. Với `--track`, tâm cửa sổ là tư thế OK của vòng trước; vòng
AMBIGUOUS hay FAILED không dời tâm. Thư mục kết quả có `track.csv` (mỗi vòng một dòng), `localize.json` (tham số,
commit git, tóm tắt, toàn bộ track) và `overlay.png`.

Trong `localize.json`, `summary.ok_pose_median` và `summary.ok_pose_spread` chỉ tính trên các vòng OK. Hướng là đại
lượng vòng: trung vị, độ lệch chuẩn và khoảng max−min của hướng được tính trên độ lệch đã quấn quanh hướng trung bình
vòng. *Sửa 24/09/2026:* bản đầu tính tuyến tính trên θ thô. Khi hướng thật ≈ 180° (θ của các vòng mang hai dấu, ví dụ
cảm biến quay ngược so với lúc dựng bản đồ), bản đầu báo trung vị ≈ 0° và độ lệch ≈ 160° cho một cảm biến ổn định tới
0,02°. Khi các hướng không nằm quanh ±180°, kết quả như cũ.

Trong `overlay.png`: nền là bản đồ (xám UNKNOWN, xanh lá FREE, đỏ OCCUPIED); chấm xanh lơ lớn là gốc (0, 0) của bản
đồ, không phải một tư thế. Điểm vẽ là của vòng OK cuối cùng; nếu không có vòng OK nào (ví dụ k01) thì là của vòng
cuối, đặt theo tư thế **không được chấp nhận** của vòng đó, và dòng chữ ghi `(no OK scan: pose NOT accepted)`. Dòng
`points: scan #… <trạng thái>` trên ảnh ghi số vòng và trạng thái. Điểm vàng = khớp, tím = mâu thuẫn, trắng = không kiểm
được. Tư thế mọi vòng: chấm xanh dương viền đen (OK), chấm cam viền đen (AMBIGUOUS), dấu X đen (FAILED); vạch = hướng
+x cảm biến. Chữ trên ảnh không dấu vì phông Hershey của OpenCV không vẽ được dấu tiếng Việt. *Sửa 24/09/2026:* bản
đầu vẽ OK màu xanh lơ, gần trùng chấm gốc bản đồ; vẽ FAILED màu đỏ, trùng ô OCCUPIED; và không ghi điểm là của vòng
nào. Nhìn ảnh k01 (151/151 FAILED) khi đó dễ tưởng có một vòng OK. Mọi `overlay.png` tạo trước ngày sửa dùng màu cũ,
**không dán nguyên vào khóa luận**: tạo lại bằng lệnh ở trên.

## 4. Kiểm bằng dữ liệu tổng hợp

Phòng tổng hợp là một đa giác không đối xứng 6,2 × 4,4 m, có ba vật cố định, tường cố ý không nằm trên biên ô 5 cm. Bản
đồ dựng đúng như đường dữ liệu thật: tia cắt đoạn thẳng, rồi `OccupancyCounts`, rồi `costmap.json`. Vòng quét để định vị
có nhiễu 1 cm, 10 % tia mất phản hồi và 3 vật di động (đường kính 30 cm) không có trong bản đồ.

| Test | Kiểm gì |
|---|---|
| `test_recovers_known_poses_inside_window_with_noise_dropouts_and_movers` | 6 tư thế đã biết, lệch tới 0,38 m mỗi trục và 26° so với tâm cửa sổ, cộng một tư thế quay 95° với tâm cửa sổ khác: OK, sai số < 2 cm và < 1° |
| `test_true_pose_outside_the_window_is_not_reported_ok` | Tư thế thật ngoài cửa sổ (1,5 m; 70° với cửa sổ ±20°; ngay ngoài mép 10 cm) → không OK. Ca ngoài mép 10 cm chỉ bị `window_edge` bắt, vì tỉ lệ khớp vẫn > 0,6 |
| `test_symmetric_corridor_is_flagged_ambiguous` | Hành lang hai tường song song: `second_peak` (tỉ số > 0,95). Hessian cho σx > 5σy. Với hành lang lý tưởng (tường liền theo lưới), Hessian suy biến hẳn, thêm `degenerate` |
| `test_scan_from_another_room_fails_even_with_global_search` | Vòng quét từ một hội trường tròn, tìm trên cả bản đồ phòng: không OK |
| `test_scene_changed_near_the_sensor_fails_on_conflicts` | Một vật lớn mới đặt trước cảm biến: tư thế vẫn đúng trong 2 cm nhưng FAILED chỉ vì `conflicts_with_map` |
| `test_matched_fraction_counts_beams_that_leave_the_map` | Bản đồ nhỏ hơn tầm quét: mẫu số gồm cả tia ra ngoài; FAILED chỉ vì `low_match_fraction` |
| `test_beams_through_mapped_walls_and_into_free_space_are_conflicts` | Phân loại khớp / ngắn / xuyên tường trên một bức tường dựng tay |
| `test_mirrored_scan_is_not_accepted` | Đảo dấu góc của vòng quét (lỗi quy ước trái/phải) → không OK |
| `test_global_search_finds_a_pose_far_from_the_initial_guess` | Tìm cả bản đồ ra tư thế (−1,62; −1,21; −140°) trong 2 cm và 1° |
| `test_branch_and_bound_equals_exhaustive_search`, `test_pyramid_levels_are_upper_bounds` | Nhánh-cận cho đúng kết quả của duyệt hết (tư thế, điểm, đỉnh thứ hai, số lá) và duyệt ít hơn 5 lần |
| `test_cli_localizes_every_revolution_and_writes_track_summary_overlay`, `test_track_mode_follows_a_moving_sensor` | CLI trên bản ghi `.npz` (tên thư mục có dấu); `--track` bám theo cảm biến đi 1,05 m và quay 44°, còn cửa sổ cố định thì không bám được |
| *Thêm 24/09/2026 sau đợt rà soát:* | |
| `test_summary_heading_statistics_are_circular`, `test_heading_near_180_localizes_and_summarises_on_the_circle` | Tóm tắt hướng tính trên vòng tròn: θ hai dấu quanh ±180° cho trung vị ≈ 180°, độ lệch < 0,05°; 8 vòng quanh 180,06° (θ mang hai dấu) đều OK và tóm tắt lệch < 0,2°; xa ±180° thì như thống kê tuyến tính |
| `test_beams_through_a_diagonal_staircase_wall_are_conflicts`, `test_beams_through_a_45_degree_mapped_wall_are_conflicts` | Mọi tia qua tường 45° đều là xuyên tường: tường dựng tay (ô chỉ chạm góc) và tường dựng bằng đường bản đồ thật |
| `test_negative_or_non_finite_window_is_rejected` | Cửa sổ âm, NaN, vô hạn hoặc thiếu thành phần bị từ chối ở `localize`, `search`, `run` (trước khi nạp gì) và ở CLI (mã 2, không tạo thư mục kết quả); `--initial` NaN cũng bị từ chối; DTHETA 0 vẫn hợp lệ |
| `test_sensor_off_the_map_is_no_overlap_not_a_conflict` | Cảm biến ngoài bản đồ: FAILED với `no_overlap`, 0 mâu thuẫn, tỉ lệ mâu thuẫn 0, không có `conflicts_with_map`; vẫn FAILED khi nới hết ngưỡng khớp |
| `test_overlay_pose_colours_differ_from_the_map_and_failed_scans_are_labelled` | Màu tư thế khác màu ô bản đồ và chấm gốc; ảnh toàn FAILED không có điểm ảnh màu OK và vẽ dấu X; dòng chữ ghi số vòng và trạng thái của vòng có điểm vẽ |
| `test_track_mode_recentres_only_on_ok_poses` | `--track`: một vòng FAILED (vòng quét từ phòng khác, tư thế khác hẳn) không dời tâm cửa sổ của vòng sau |
| `test_cli_every_and_limit_pick_revolutions`, `test_cli_converts_degrees_and_global_search_uses_five_levels` | `--skip-seconds`, `--every`, `--limit` chọn đúng vòng; `--initial` và `--window` đổi độ sang radian đúng một lần; `--levels`, `--min-range`, `--max-range` vào cấu hình; `--global` mặc định 5 mức |
| `test_orientation_just_outside_the_window_is_caught_only_by_window_edge` | Hướng thật 24° với cửa sổ ±20°, mọi tia vẫn khớp: chỉ phần θ của `window_edge` bắt được |
| `test_each_remaining_check_fires_on_its_own` | `few_matched`, phần θ của `degenerate`, `search_truncated`, `refine_unstable` (tinh chỉnh bị ép chạy xa 30 cm; giữ đỉnh rời rạc): mỗi kiểm tự nó đổi kết luận |

Số đo trên máy bàn (i9-14900), phiên bản mã cuối ngày 24/09. Sai số trên 6 tư thế của test là 0,4–0,7 cm và
0,004–0,10°. Phần 0,5–0,6 cm có hệ thống đến từ việc bản đồ lượng tử hóa tường về tâm ô (mục 6). Thời gian mỗi vòng
với cửa sổ mặc định: trung vị 16,8 ms, p95 19,1 ms trên 30 tư thế ngẫu nhiên; một lần chạy khác trên 6 tư thế của test
cho 21–26 ms. Test chỉ đặt ngân sách rộng (trung vị < 300 ms) để không hỏng trên máy chậm hơn. Các số thời gian này
đo trước bản sửa kiểm xuyên tường (mục 2), chưa đo lại trên dữ liệu tổng hợp; chi phí thêm đo trên bản ghi thật ở
mục 5. Bản sửa không đổi tư thế trả về, vì kiểm xuyên tường chỉ dùng ở bước đánh giá.

**Kiểm đột biến (24/09, bản sao mã trong thư mục tạm):** gây lần lượt 12 lỗi vào `localize.py`: đảo dấu góc; bỏ đỉnh
thứ hai; bỏ mép cửa sổ; tháp không lấy max; bỏ tinh chỉnh; bỏ kiểm xuyên tường; bỏ phạt ô FREE; mẫu số chỉ gồm tia
trong lưới; bỏ kiểm suy biến; bỏ `--track`; bỏ ngưỡng mâu thuẫn; bỏ ngưỡng tỉ lệ khớp. Lỗi nào cũng làm ít nhất một
test hỏng (chạy lại trên mã cuối).

*Kiểm đột biến bổ sung (24/09/2026, sau đợt rà soát):* đợt rà soát chỉ ra 7 đột biến vẫn cho 17/17 test đạt: `--track`
bám cả tư thế không OK; bỏ phần θ của `window_edge`; bỏ `few_matched`; bỏ qua `--every`; bỏ qua `--limit`; không bao giờ
báo `search_truncated`; bỏ phần θ của kiểm suy biến. Thêm hai đột biến của `refine_unstable`: bỏ lý do, và nhận bước
tinh chỉnh chạy xa thay vì giữ đỉnh rời rạc. Thêm năm đột biến của CLI: `--initial` và `--window` không đổi độ sang
radian; `--global` dùng 4 mức; bỏ qua `--levels`; bỏ qua `--min-range`/`--max-range`. Mỗi bản sửa của đợt rà soát cũng
được gỡ ra thử (15 đột biến, cộng một đột biến đổi màu nền dải chữ của overlay):
- tóm tắt hướng tuyến tính;
- kiểm xuyên tường cũ, chỉ nối ô chéo, chỉ lấy mẫu ¼ ô;
- bỏ kiểm cửa sổ ở từng chỗ (cả bốn chỗ, riêng CLI, riêng `localize`, riêng `run`, riêng `search`);
- bỏ kiểm `--initial`;
- trả tỉ lệ mâu thuẫn 1,0 như cũ, bỏ lý do `no_overlap`;
- màu overlay cũ, bỏ dấu X của FAILED, dòng chữ không ghi số vòng.

Tổng cộng 30 đột biến này, cộng 12 đột biến ở trên chạy lại trên mã đã sửa. Đột biến nào cũng làm ít nhất một trong 29
test hỏng, trừ một: đổi màu nền dải chữ của overlay thành đen. Màu nền này chỉ là thẩm mỹ, không có test.

## 5. Kết quả trên bản ghi thật (24/09/2026, chạy offline trên máy bàn)

Bản ghi nằm trong `runs/lidar_bench/` và không có trong git. Kết quả chạy được ghi ra thư mục tạm của phiên làm việc,
**chưa chép vào `docs/evidence/lidar/`**. Muốn tạo lại thì chạy các lệnh ở mục 3. *(Cập nhật tối 24/09/2026: bản rút gọn của lần chạy lại sau đợt rà soát đã được chép vào `docs/evidence/lidar/` (chưa commit; cập nhật 25/09/2026: đã commit và push trong `b100a5d`):
[dinh_vi_p07_tren_p07.png](evidence/lidar/dinh_vi_p07_tren_p07.png),
[dinh_vi_live_headless_tren_p07.png](evidence/lidar/dinh_vi_live_headless_tren_p07.png),
[dinh_vi_k01_tren_p07.png](evidence/lidar/dinh_vi_k01_tren_p07.png),
[dinh_vi_k01_global_tren_p07.png](evidence/lidar/dinh_vi_k01_global_tren_p07.png) và tóm tắt
[dinh_vi_tren_p07_20260924.json](evidence/lidar/dinh_vi_tren_p07_20260924.json); xem [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md)
mục 8. Tệp `.npz` và `map_p07` vẫn không có trong git. Kết quả vẫn chỉ là độ nhất quán, chưa có tham chiếu độc lập.)*

*Chạy lại ngày 24/09/2026 sau các bản sửa của đợt rà soát* (kiểm xuyên tường nối ô chéo, `no_overlap`, cửa sổ, tóm
tắt hướng, màu overlay), trên cùng bản đồ và cùng sáu cách chạy trong bảng dưới: **không vòng nào đổi trạng thái**, tư
thế từng vòng giống hệt (chênh 0,00 mm và 0,0000°), trung vị và độ lệch trong bảng giữ nguyên. Chỉ số tia bị tính
"xuyên tường" tăng trên k01: trung vị mỗi vòng 88 → 94 (cửa sổ mặc định) và 83 → 88 (`--global --every 5`). Vì vậy tỉ
lệ mâu thuẫn của k01 khi tìm toàn cục thành 0,46–0,50, thay cho 0,44–0,49 ghi trong bảng. Không vòng nào có
`no_overlap`. Trên p07 và live_headless, số tia xuyên tường vẫn là 0–1 mỗi vòng.

**Bản đồ.** `runs/lidar_bench/20260922/map_p07/costmap.json`, dựng từ p07 (181 vòng, cảm biến đứng yên trên bàn,
22/09 06:10 UTC). Lưới 8 × 8 m, ô 5 cm: 230 ô OCCUPIED, 5.657 ô FREE, còn lại UNKNOWN. Cảnh là bàn làm việc nhiều vật
lặt vặt. 34,6 % tia không phản hồi.

| Bản ghi | Quan hệ với bản đồ | Chế độ | Kết quả |
|---|---|---|---|
| p07 (22/09, 181 vòng) | Chính dữ liệu dựng bản đồ, **không độc lập** | cửa sổ mặc định | 181/181 OK. Trung vị (−1,3 mm; −3,3 mm; +0,008°). Độ lệch chuẩn giữa các vòng 1,4 / 1,8 mm, 0,047°. Khoảng max−min 9 / 11 mm, 0,29° |
| live_headless (22/09 06:12 UTC, 60 vòng, 2,5 phút sau p07) | Bản ghi khác, dự kiến cùng chỗ | cửa sổ mặc định | 60/60 OK. Trung vị (−1,1 mm; −6,8 mm; **+4,33°**). Độ lệch chuẩn 2,6 / 2,7 mm, 0,068°. Khoảng max−min 18 / 13 mm, 0,34°. Tỉ lệ khớp trung vị 0,84; fit 0,79 |
| live_headless | như trên | `--track` | 60/60 OK, giống hệt trong 0,3 mm và 0,01° |
| live_headless | như trên | `--global` (cả bản đồ, 360°) | 60/60 OK, cùng tư thế: phép tìm toàn cục không bị một đỉnh khác kéo đi |
| k01 (24/09, 151 vòng) | LiDAR đã dời sang chỗ khác, vị trí mới không ghi lại | cửa sổ mặc định | **151/151 FAILED**: `low_match_fraction` 151, `conflicts_with_map` 151, `window_edge` 119. Tỉ lệ khớp trung vị 0,24; fit 0,17 |
| k01 | như trên | `--global --every 5` (31 vòng) | **31/31 FAILED**: `low_match_fraction` và `conflicts_with_map` ở mọi vòng. Tỉ lệ khớp trung vị 0,27, mâu thuẫn 0,44–0,49 |

**live_headless quay +4,3° so với lúc dựng bản đồ.** Vị trí gần như không đổi (dưới 1 cm, trong giới hạn ô 5 cm) nhưng
hướng lệch ổn định +4,3…+4,5° ở cả 60 vòng. Để chắc đây không phải lỗi của bộ định vị, tôi kiểm lại bằng một cách
không dùng bản đồ (script tạm ngày 24/09, không lưu trong repo). Cách kiểm: lấy trung vị khoảng cách theo từng ô góc
0,25° (bỏ 3 s đầu của p07, 1 s đầu của live_headless), rồi dịch vòng hồ sơ góc của live_headless để tìm độ dịch khớp
nhất với p07. Kết quả: dịch −4,25…−4,5° thì 87–88 % ô góc chênh dưới 5 cm, trung vị |chênh| 5–7 mm. Vật ở góc φ trong
p07 hiện ở φ − 4,4° trong live_headless, tức cảm biến đã quay +4,4° ngược chiều kim đồng hồ. Kết quả này khớp với bộ
định vị. Mã chuyển đổi góc của `bench` và `live_view` là một (`revolution_to_scan`, `mirror = False` ở cả hai). Còn hai
khả năng, **chưa phân biệt được**:
(a) thiết bị bị xoay nhẹ trên bàn giữa hai lần ghi, chẳng hạn lúc cắm lại cáp;
(b) gốc góc của thiết bị lệch giữa hai lần khởi động mô-tơ.
Nếu là (b) thì hướng của LiDAR so với xe sẽ đổi sau mỗi lần bật, và phải hiệu chuẩn lại hướng mỗi lần. Cách phân biệt:
ghi hai phiên liên tiếp mà không chạm vào thiết bị, dừng rồi khởi động lại mô-tơ giữa hai phiên (mục 7, bước 1).
Ngoài ra, 12 vòng trong 1 s đầu của live_headless (lúc mô-tơ vừa khởi động, số tia mỗi vòng còn thay đổi) cho
+4,38…+4,57°. 48 vòng sau đó cho +4,23…+4,42°, trung vị +4,31°. Chênh ≈ 0,15° này chưa rõ nguyên nhân.

**k01 bị báo hỏng đúng như mong đợi.** Cảnh đã khác nên không vòng nào OK. Kiểm không dùng bản đồ cũng cho kết quả tương
tự: không có độ dịch góc nào làm quá 8 % ô góc của k01 khớp p07 trong 5 cm. Kết quả này chỉ cho thấy bộ định vị **không
nhận bừa**. Nó không cho biết LiDAR đã được dời đi bao xa. Cần lưu ý: khi tìm toàn cục, cả 31 vòng đều cho **cùng một**
đỉnh tốt nhất (−0,70; −0,10; +54,8°, lệch dưới 1 cm và 0,6° giữa các vòng), vậy mà đỉnh đó sai (chỉ 27 % tia khớp,
gần một nửa số tia kiểm được mâu thuẫn với bản đồ). Cảm biến đứng yên thì các vòng gần như giống nhau, nên phép tìm cho
ra cùng một cực đại dù cực đại đó sai. Vì vậy **tư thế ổn định qua các vòng không phải bằng chứng là tư thế đúng**; chỉ
các phép kiểm trên từng vòng (tỉ lệ khớp, mâu thuẫn, đỉnh thứ hai, mép cửa sổ) mới là căn cứ.

**Dịch có chủ đích trên vòng quét thật** (script tạm ngày 24/09, không lưu trong repo). Mỗi vòng của live_headless được
biến đổi cứng theo một dịch/quay ngẫu nhiên đã biết (±0,4 m, ±25°), 3 lần mỗi vòng, tổng 180 lần. Kỳ vọng là tư thế của
vòng gốc hợp với phép dịch. Kết quả: 180/180 OK. Sai số trung vị 3,8 mm và 0,038°, p95 7,7 mm và 0,11°, lớn nhất 17 mm
và 0,24°. Phép thử này đo khả năng **tìm lại** trên cảnh thật lộn xộn, không đo độ đúng: vòng quét chỉ được dịch cứng,
không phải quét lại từ chỗ khác, nên che khuất không đổi. Trong lần chạy đầu có 3/180 lần AMBIGUOUS với lý do
`refine_unstable`. Nguyên nhân là ngưỡng cũ "2 bước lưới" quá chặt: đỉnh rời rạc có thể lệch 3 cm và 0,9° vì tịnh tiến
và quay bù nhau. Ngưỡng được nới thành 15 cm và 5°.

**Thời gian mỗi vòng** (máy bàn i9-14900, numpy, đo 24/09 khi không có tác vụ nặng nào khác chạy):

| Trường hợp | Trung vị | p95 | Lớn nhất |
|---|---|---|---|
| live_headless, cửa sổ mặc định (60 vòng) | 10,6 ms | 12,4 ms | 14,1 ms |
| p07, cửa sổ mặc định (181 vòng) | 11,1 ms | 13,1 ms | 16,7 ms |
| k01, cửa sổ mặc định: cảnh không khớp, cắt nhánh kém hơn (151 vòng) | 84,6 ms | 103,7 ms | 109,7 ms |
| live_headless, `--global` (20 vòng) | 534 ms | 569 ms | 581 ms |
| k01, `--global --every 5` (31 vòng) | 5,4 s | 6,0 s | 6,0 s |

Bảng trên đo trước bản sửa kiểm xuyên tường. *Đo thêm 24/09/2026 sau bản sửa:* chạy mã cũ và mã mới xen kẽ trong cùng
một tiến trình (script tạm, không lưu trong repo), trên máy bàn khi đang có tác vụ khác chạy song song, nên chỉ nên so
hai cột với nhau, không so với bảng trên:

| Trường hợp (cửa sổ mặc định) | Riêng kiểm xuyên tường, trung vị cũ → mới | Cả vòng định vị, trung vị cũ → mới |
|---|---|---|
| live_headless (60 vòng; cả vòng đo trên 20 vòng) | 1,1 → 3,0 ms | 11,8 → 13,3 ms |
| k01 (151 vòng; cả vòng đo trên 51 vòng) | 2,1 → 8,1 ms | 88,5 → 93,7 ms |

Với LiDAR 10 Hz, cửa sổ mặc định trên cảnh khớp dùng khoảng 11–13 % thời gian của một vòng. Khi cảnh không khớp, thời
gian gần bằng một vòng. Tìm toàn cục chỉ hợp để chạy offline hoặc để khởi tạo một lần, không chạy mỗi vòng. **Chưa đo
trên laptop RTX 3050 Ti** (máy nộp đồ án).

## 6. Giới hạn

- **Chưa có tham chiếu độc lập.** Chưa lần nào LiDAR được đặt ở vị trí và hướng đo bằng thước, nên chưa có sai số thật.
  Số ở mục 5 chỉ là độ nhất quán.
- **Dấu trái/phải không kiểm được bằng định vị.** Bản đồ và vòng quét dùng cùng quy ước góc. Nếu dấu góc của driver sai
  thì định vị vẫn nhất quán, chỉ là trong một thế giới bị lật gương. Vẫn cần lần đặt hộp bên trái (p04,
  [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 6, 6b).
- **Bản đồ chỉ giữ ô, không giữ điểm.** Mỗi bức tường có thể lệch tới ±½ ô (2,5 cm) so với vị trí thật. Trên dữ liệu tổng
  hợp, phần lệch có hệ thống này là 0,5–0,6 cm. Muốn chính xác hơn thì dựng bản đồ ô nhỏ hơn, với điều kiện tia đủ dày.
- **Độ lệch chuẩn Hessian quá lạc quan** (1–4 mm trên dữ liệu thật): nó không tính sai số của bản đồ và của mô hình. Chỉ
  dùng nó để phát hiện hướng suy biến. Trên hành lang có lỗ ở tường, nó còn không vượt ngưỡng (mục 4); khi đó `second_peak`
  mới là thứ bắt được.
- **Kiểm xuyên tường chỉ làm ở bước đánh giá**, không làm ở bước tìm. Phép tìm toàn cục vì thế có thể chọn một tư thế
  xuyên tường rồi bị loại, thay vì chọn tư thế đúng có điểm thấp hơn một chút. Trường hợp đó ra FAILED chứ không ra kết
  quả sai. *Ghi chú 24/09/2026:* từ bản sửa nối ô chéo (mục 2), phép kiểm này tốn thêm ≈ 2 ms mỗi vòng trên
  live_headless và ≈ 6 ms trên k01 (mục 5). Nó chỉ nối hai ô OCCUPIED chạm góc nhau. Tường mà bản đồ có lỗ thật (một ô
  FREE hoặc UNKNOWN chen giữa) vẫn để tia đi qua lỗ mà không tính mâu thuẫn, và như vậy là đúng với những gì bản đồ biết.
- **Bản đồ p07 là một góc nhìn từ một chỗ trên bàn**, nhiều UNKNOWN. Chưa thử định vị khi cảm biến di chuyển trong cảnh
  thật, vì chưa có bản ghi nào như vậy (LiDAR chưa gá, chưa có xe).
- **Ngưỡng tạm, CHƯA CHỐT:** 0,6 (tỉ lệ khớp), 0,25 (mâu thuẫn), 0,9 (đỉnh thứ hai), 5 cm và 2° (Hessian). Các ngưỡng
  này mới chọn theo dữ liệu tổng hợp và ba bản ghi ở mục 5. Đặc biệt, `low_match_fraction` sẽ loại cả tư thế đúng khi
  phần lớn tầm quét nằm ngoài bản đồ, vì mẫu số gồm cả tia ra ngoài. Cách xử lý đó an toàn, nhưng có thể quá chặt khi
  xe chạy ra mép bản đồ.
- Chỉ lưới thẳng trục (`origin.yaw = 0`). Costmap có `stamp.valid = False` bị từ chối.

## 7. Việc cần làm để có tham chiếu độc lập (cần người và thiết bị)

1. **Hướng gốc có ổn định giữa các lần bật không:** dán cố định C1 trên bàn và không chạm vào nó. Ghi hai phiên 20 s,
   giữa hai phiên dừng mô-tơ (thoát chương trình) rồi chạy lại. Dựng bản đồ từ phiên 1, định vị phiên 2. Nếu θ ≠ 0
   (vượt độ lặp lại ~0,1°) thì gốc góc của thiết bị đổi theo lần khởi động: khả năng (b) ở mục 5.
2. **Vị trí đo bằng thước:** dán băng dính đánh dấu tâm quay và một vạch hướng. Đặt C1 ở gốc, ghi bản đồ. Sau đó dời
   đến các điểm đo bằng thước, ví dụ (+0,20; 0), (0; +0,20), (+0,30; −0,20) m, và quay 0°, +10°, −20° theo thước đo
   góc. *(Lưu ý 25/09/2026: thước đo góc thường không đủ chính xác để kiểm ngưỡng hướng đề xuất N-L2; tham chiếu hướng
   nên dùng thước thẳng ≥ 0,65 m đặt dọc vạch hướng, xem [NGUONG_NGHIEM_THU_DE_XUAT.md](NGUONG_NGHIEM_THU_DE_XUAT.md)
   dòng N-L2.)* Mỗi điểm ghi 10–15 s. So `ok_pose_median` với số đo thước để có sai số vị trí/hướng (hướng trong tóm tắt là
   thống kê vòng, mục 3; so hướng theo hiệu đã quấn về ±180°). Lệnh ghi dùng
   `.venv\Scripts\python.exe -X utf8 -m autopark.lidar.bench record --out runs/lidar_bench/<ngày> --name d01_... --seconds 15`
   (thay `<ngày>` bằng ngày thật trước khi dán vào cmd)
   (theo [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 6).
   Cổng LiDAR lấy từ `configs/thiet_bi.json`; thêm `--port COMx` để ghi đè ([chuyển máy](CHUYEN_MAY_BAN.md)).
3. Làm cùng buổi với 7 lần đặt hộp (mục 6 của tài liệu đó) để chốt dấu góc trái/phải.
4. Sau đó chốt các ngưỡng ở mục 6 và ghi vào bảng 16.2 của kế hoạch (dòng "Định vị").
