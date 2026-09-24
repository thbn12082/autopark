# Độ nhạy của planner theo kích thước xe, với sa bàn cố định (24/09/2026)

**Kế hoạch đối chiếu:** [v3.1](../../KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) mục 8 (giai đoạn 4, "Khi chưa có xe": để
hình học xe với nhãn `CHƯA ĐO` và thử độ nhạy planner theo kích thước giả định). Đề xuất phép thử và lý do cần nó:
[GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md) mục 5.1 và 5.3.

**Mức bằng chứng: CHỈ MÔ PHỎNG.** Mọi kết quả dưới đây là planner + bộ bám quỹ đạo + xe động học lý tưởng trong mô
phỏng, trên máy bàn i9-14900, tối 24/09/2026. Xe tham chiếu là `configs/vehicle_default.json` (dài 0,31 m, rộng
0,14 m, chiều dài cơ sở 0,19 m, nhô trước/sau 0,06/0,06 m, lái tối đa 30°): **mọi giá trị trong tệp đó là GIẢ ĐỊNH –
CHƯA ĐO**, không phải thông số MN300. Chưa nhận MN300; chưa có số đo nào của xe thật. Kết quả không nói xe thật đỗ được
hay không; nó chỉ nói planner hiện tại phản ứng thế nào khi kích thước xe lệch khỏi giả định trên một sa bàn giữ nguyên.

| Thành phần | Tệp |
|---|---|
| Công cụ | [`autopark/evaluation/sensitivity.py`](../autopark/evaluation/sensitivity.py) |
| Test | [`tests/test_vehicle_sensitivity.py`](../tests/test_vehicle_sensitivity.py) |
| Kết quả lượt A (ngân sách 8 s) | `runs/do_nhay_xe/20260924_toi_sa_ban_co_dinh/` (`ket_qua.json`, `bang_do_nhay.md`) |
| Kết quả lượt B (ngân sách 20 s) | `runs/do_nhay_xe/20260924_toi_sa_ban_co_dinh_20s/` (`ket_qua.json`, `bang_do_nhay.md`) |

Thư mục `runs/` không có trong git; các bảng dưới đây chép từ hai tệp `bang_do_nhay.md` đó.

## 1. Vì sao cần một công cụ riêng

`bench`, `compare` và `render` dựng bộ 16 ca khó bằng `build_cases(cfg)` với **chính** cấu hình dùng để lập đường. Đổi
cỡ xe thì ô đỗ song song (1,15–1,60 × chiều dài xe), lối đi đỗ vuông góc (1,15–1,70 × chiều dài xe), độ sâu/bề rộng ô
và các xe đỗ bên cạnh cũng đổi theo. Như vậy một xe to hơn chỉ được thử trong một sa bàn cũng to hơn. Sa bàn thật thì
không co giãn theo xe. Chiến dịch độ bền 20/09 cũng có một phần như vậy (GIAI_DOAN_4_CHUAN_BI.md mục 5.1).

Ví dụ (mô phỏng, kiểm lại bằng test `test_xe_to_hon_nhieu_hong_ca_chat_ma_xe_mac_dinh_qua`): ca `perp_aisle_135` với
xe phóng đều 1,3 lần. Nếu sa bàn dựng lại theo xe (cách của `bench`), xe đỗ được. Nếu giữ sa bàn dựng từ xe tham
chiếu, ô sâu 0,40 m ngắn hơn thân xe 0,403 m, và `plan_parking` trả `GOAL_INVALID` ngay.

## 2. Công cụ làm gì

1. **Dựng sa bàn một lần** từ cấu hình tham chiếu (`--reference-config`, mặc định `configs/vehicle_default.json`):
   16 ca của `evaluation/hard_cases.py` và bốn tệp `scenarios/*.json` (tên `kb_<tệp>`). Tệp
   `hard_cases.py` không bị sửa; công cụ chỉ gọi `build_cases(tham_chiếu)`.
2. **Giữ nguyên** vùng sa bàn, vật cản, các xe đỗ bên cạnh, ô đỗ và tư thế xuất phát (tâm trục sau) cho mọi biến thể.
   Mỗi lần chạy có `scene_digest` (sha256 của phần cố định); mọi biến thể của một sa bàn phải có cùng giá trị, và test
   kiểm điều đó.
3. **Đích:** sa bàn có ô đỗ thì đích tính lại cho xe đang thử sao cho thân xe nằm giữa **cùng ô đó**
   (`Scenario.sync_goal`, như ứng dụng làm). Sa bàn không có ô đỗ (quay đầu, hành lang, dịch ngang, chữ Z, hai kịch bản
   `kb_giai_doan_0_unknown`, `kb_sa_ban_3x2_hai_hop`) thì đích tâm trục sau giữ nguyên. Đây là quy ước của công cụ
   (ĐỀ XUẤT – CHỜ CHỐT): với đích cho bằng tư thế, xe dài hơn thì đuôi/mũi xe ở đích nhô xa hơn.
4. **Lập đường** qua `plan_parking` (đường ứng dụng gọi: thang portfolio có kiểm chứng bám đường). Ngân sách mặc định
   bằng `PlannerParams().time_limit` = 8 s của ứng dụng; `--time-limit` đổi được. Hạt giống RRT cố định
   (`--rrt-seed`, mặc định 20260907 = `cand_rrt_rs.DEFAULT_SEED`), đặt qua `AUTOPARK_RRT_SEED` trong lúc chạy rồi trả
   lại.
5. **Chấm độc lập với planner**, bằng cấu hình xe đang thử: kiểm vùng quét `check_motion` giữa mọi cặp điểm liên tiếp;
   kiểm lấy mẫu `collision_oracle` (không dùng Shapely) ở mọi điểm và ba điểm giữa mỗi cặp; góc lái không vượt
   `max_steer`; cho xe mô phỏng bám đường kín vòng (`rollout`, 240 s mô phỏng) và yêu cầu tới đích trong dung sai của
   sa bàn (5 cm / 5°). "Giải được" = đạt cả bốn. Planner báo OK mà kiểm độc lập không đạt thì ghi là **vi phạm** và
   công cụ thoát mã 1.

   *(Sửa muộn 24/09/2026, sau hai lượt A/B:)* sai số cuối giờ tính tới **đích của sa bàn**, không tới đích mà planner
   tự ghi trong quỹ đạo (trước đó một planner dừng sớm rồi khai đích là chỗ dừng sẽ được chấm "giải được"). Bộ bám
   không đọc đích của quỹ đạo, và mọi planner của ứng dụng dựng quỹ đạo bằng đúng đích được yêu cầu (đọc mã; kiểm thêm
   14 lần lập đường OK trên 7 sa bàn × {`goc`, `length+10`}: đích quỹ đạo trùng đích sa bàn ở cả 14), nên sửa này
   không đổi kết quả của `plan_parking` trong hai lượt A/B; nó chỉ chặn planner lạ nạp qua `--planner`. Cũng từ lúc
   này `--recheck-time-limit` từ chối `nan`/`inf`/số âm ngay khi đọc tham số (trước đó `nan` chạy hết lượt rồi mới đổ
   khi ghi JSON, mất toàn bộ kết quả).
6. **Ghi**: trạng thái, thời gian lập đường, độ dài, số lần đổi chiều, khoảng hở nhỏ nhất của đường lập (tới vật cản
   hoặc mép sa bàn, `check_pose.min_clearance`), khoảng hở nhỏ nhất khi xe mô phỏng chạy, sai số cuối, xuất phát/đích
   có còn trống với xe đang thử, ô có vừa xe không. Ca "lật" = giải được với xe tham chiếu nhưng không giải được với
   biến thể (và ngược lại). `--recheck-time-limit` chạy lại các ca lật OK → hỏng (trừ `START_INVALID`/`GOAL_INVALID`)
   với ngân sách dài hơn, để tách hết giờ khỏi thất bại khác.

Biến thể mặc định (43 cấu hình, kể cả xe tham chiếu):

| Nhóm | Thay đổi | Mức |
|---|---|---|
| `length` | nhô sau, chiều dài cơ sở, nhô trước cùng một hệ số (cả xe dài ra; bán kính quay đổi theo) | ±5, ±10, ±20 % |
| `width` | bề rộng | ±5, ±10, ±20 % |
| `overhangs` | nhô trước và nhô sau (chiều dài cơ sở giữ nguyên) | ±5, ±10, ±20 % |
| `wheelbase` | chiều dài cơ sở (phần nhô giữ nguyên) | ±5, ±10, ±20 % |
| `max_steer` | góc lái lớn nhất (30° → 24°…36°) | ±5, ±10, ±20 % |
| `kich_thuoc` | phóng đều footprint (dài và rộng), giữ góc lái | ±5, ±10, ±20 % |
| `lon_lai_kem` | footprint +p %, góc lái −p % (phía bất lợi) | p = 5, 10, 20 |
| `nho_lai_gat` | footprint −p %, góc lái +p % (phía thuận lợi) | p = 5, 10, 20 |

Tốc độ, gia tốc, tốc độ đổi lái giữ như xe tham chiếu. Có thêm `front_overhang`, `rear_overhang` riêng (`--params`) và
`--plan-config <tệp>` để đặt một cấu hình từ tệp (ví dụ xe đã đo) lên cùng sa bàn.

## 3. Lệnh (chạy trong `D:\ap\autopark`, mỗi lệnh một dòng)

Xem danh sách sa bàn và biến thể:

```
.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.sensitivity --list
```

Chạy thử nhanh vài ca:

```
.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.sensitivity --scenes parallel_160,uturn_w55 --params width --levels 10 --combos none --out runs\do_nhay_xe\thu_nhanh
```

Hai lượt của tài liệu này (lượt A, lượt B):

```
.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.sensitivity --workers 6 --recheck-time-limit 20 --out runs\do_nhay_xe\20260924_toi_sa_ban_co_dinh
```

```
.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.sensitivity --time-limit 20 --workers 4 --recheck-time-limit 60 --out runs\do_nhay_xe\20260924_toi_sa_ban_co_dinh_20s
```

Khi có số đo MN300 (tệp `configs/vehicle_measured.json` chưa có; định dạng CHƯA CHỐT, GIAI_DOAN_4_CHUAN_BI.md mục 4.1):

```
.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.sensitivity --params none --combos none --plan-config configs\vehicle_measured.json --time-limit 20 --recheck-time-limit 60
```

Tệp cấu hình hỏng (không có, JSON sai, thiếu khóa, kích thước ≤ 0, góc lái ngoài (0°, 89°)) thì công cụ báo rõ tệp nào,
lý do, và thoát mã 2 trước khi chạy gì. Thư mục `--out` đã có dữ liệu thì cũng từ chối, để không ghi đè bằng chứng cũ.

Cùng đợt này, ba công cụ khác nhận `--vehicle-config` (mặc định vẫn `configs/vehicle_default.json`; tệp hỏng thì thoát
mã 2 trước khi làm gì):

```
.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.robustness --out runs\robustness_xe_do --vehicle-config configs\vehicle_measured.json
```

```
.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.phase0 --out runs\phase0_xe_do --vehicle-config configs\vehicle_measured.json
```

```
.venv\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app --port COM4 --vehicle-config configs\vehicle_measured.json
```

- `robustness`: ghi đường dẫn và sha256 của tệp xe vào `manifest.json`. Các ca planner của chiến dịch này
  (`planner_case`) **vẫn** dựng sa bàn theo xe đã đổi cỡ như trước; phép thử sa bàn cố định là `sensitivity`.
  - **Chỉ một phần xe lấy từ tệp** (đọc mã `robustness.py`, 24/09/2026). Ca pose/swept/runtime (`varied_config`): giữ
    TỈ LỆ footprint của tệp (chiều dài cơ sở, bề rộng, nhô trước/sau) nhưng nhân chung hệ số ngẫu nhiên 0,7–1,4; còn
    `max_steer` (22–38°), `max_speed` (0,06–0,30 m/s), `max_accel` (0,15–0,45 m/s²), `max_decel` (0,25–0,90 m/s²),
    `max_steer_rate` (35–140°/s) rút từ khoảng TUYỆT ĐỐI, KHÔNG theo tệp. Ca planner (`planner_case`): bề rộng và
    chiều dài cơ sở của tệp nhân 0,85–1,15; nhô trước/sau, `max_steer`, `max_accel`, `max_steer_rate` giữ theo tệp;
    `max_speed` (0,10–0,30 m/s) và `max_decel` (0,40–0,90 m/s²) rút từ khoảng tuyệt đối. `base_vehicle` trong
    `manifest.json` là xe gốc trước khi đổi, không phải xe của từng ca (xem `input.vehicle` trong `cases.jsonl`).
  - Tức là `--vehicle-config` KHÔNG làm chiến dịch thử giới hạn lái/tốc độ/gia tốc đo được của MN300 ở ca
    pose/swept/runtime; xe đo có `max_steer` < 22° hoặc > 38° không bao giờ xuất hiện ở ba loại ca này. Kiểm bằng đọc mã
    và chạy `--case swept:0` với tệp nháp (24/09/2026, mô phỏng): manifest ghi 20°, ca chạy dùng 29,6°. Test
    `test_robustness_varied_config_chi_giu_ti_le_footprint_cua_tep` ghim hành vi này; đổi hành vi thì sửa cả mục này.
- `phase0`: ghi `vehicle_config_used.json` vào thư mục ra; năm ca dùng cấu hình này, sa bàn giữ kích thước tuyệt đối.
- `ui/lidar_app`: thay cấu hình xe của sa bàn mặc định, hoặc của kịch bản khi có `--scenario`, và **vẫn giữ** khi mở
  kịch bản khác bằng nút "Mở kịch bản" trong cửa sổ (không dùng tệp xe của kịch bản đó; thanh trạng thái báo điều này;
  tệp xe của kịch bản thiếu hay hỏng cũng không chặn việc mở). Không có tùy chọn thì như cũ. Tùy chọn này chỉ kiểm
  bằng test offscreen (không mở cổng COM, 24/09/2026); **CHƯA THỬ** với LiDAR thật.
- `fusion/demo.py` vẫn cố định `vehicle_default.json` (không thuộc đợt sửa này).

## 4. Điều kiện của hai lượt chạy (24/09/2026, máy bàn)

| | Lượt A | Lượt B |
|---|---|---|
| Thời gian | 20:56:53 → 21:07:32 (639 s) | 21:07:58 → 21:38:32 (1835 s) |
| Ngân sách lập đường mỗi ca | 8 s (bằng ứng dụng) | 20 s (bằng mặc định của `bench`/`render`) |
| Chạy lại các ca lật | 20 s | 60 s |
| Số tiến trình song song | 6 | 4 |
| Hạt giống RRT | 20260907 | 20260907 |
| Mã nguồn | git `9bcc30c` + thay đổi chưa commit (của đợt này và của các agent khác). *(Cập nhật 25/09/2026: các thay đổi đó nay đã commit và push trong đợt khuya `65b7127` … `54cb3e2`; công cụ `sensitivity.py` ở `10a4735`. Mã lúc chạy không trùng hẳn một commit nào: bản sửa cách chấm ở mục 2 bước 5 làm sau hai lượt.)* | như lượt A |
| Số lần chạy | 20 sa bàn × 43 biến thể = 860 | 860 |

**Thời gian trong hai lượt bị nhiễu, và nhiễu này đổi kết quả.** Cả hai lượt chạy nhiều tiến trình cùng lúc, trong khi
các agent khác cũng chạy việc (test, script) trên cùng máy. Planner có ngân sách theo đồng hồ thật, nên tải máy đổi được
kết quả. Cùng xe tham chiếu, cùng mã, tối 24/09/2026 trên cùng máy, năm lần chạy cho hai sa bàn nhạy nhất:

| Lần chạy | Ngân sách | Tiến trình | Xe tham chiếu giải được | `parallel_135` | `uturn_w46` | Thư mục trong `runs/do_nhay_xe/` |
|---|---:|---:|---:|---|---|---|
| 20:53:24 → 20:54:17 | 8 s | 1 | 16/20 | 1,80 s | 3,77 s | `20260924_2053_goc_1_tien_trinh_8s` (chạy lúc 20:53 vào thư mục tạm `scratchpad/wf10/sens/baseline1` bằng bản công cụ trước khi thêm `source_sha256` vào manifest, rồi chép nguyên tệp sang `runs/` lúc 21:43 — vì vậy `manifest.argv` vẫn ghi `--out` là thư mục tạm; mã chấm lúc đó **CHƯA kiểm được bằng sha256**. Kiểm lại (24/09/2026): `scene_digest`/hình học 20 sa bàn và cấu hình `goc` trùng lượt A; `verdict` của 20 dòng suy lại đúng từ `path_ok`/`oracle_ok`/`steer_ok`/`tracked` theo mã hiện tại — không chứng minh phần kiểm va chạm/bám đường giống hệt) |
| Lượt A | 8 s | 6 | 15/20 | 7,12 s | TRACKING_FAILED (xe mô phỏng dừng cách đích 5,1 cm / +12,6°) | `20260924_toi_sa_ban_co_dinh` |
| Lượt B | 20 s | 4 | 16/20 | 7,66 s | 8,78 s | `20260924_toi_sa_ban_co_dinh_20s` |
| 21:39:13 → 21:40:48 | 8 s | 1 | 15/20 | 4,02 s | TIMEOUT | `20260924_toi_goc_1_tien_trinh_8s` |
| 21:40:51 → 21:43:11 | 20 s | 1 | 16/20 | 9,15 s | 9,80 s | `20260924_toi_goc_1_tien_trinh_20s` |

Tải CPU đọc bằng `Win32_Processor.LoadPercentage` ngay trước lần 21:39 là 53 % (các agent khác đang chạy); các lần
khác không ghi tải. Bốn ca xe tham chiếu không giải được ở mọi lần là `parallel_122`, `parallel_115`, `zigzag_corridor`,
`pocket_exit_park` (hết giờ).

Vì vậy mọi ô "T" (hết giờ) và các ca lật chỉ vì hết giờ phải đọc là "không tìm được trong ngân sách **ở tải máy lúc
đó**", không phải "vô nghiệm". Số giây trong bảng chỉ để so trong cùng một lượt.

## 5. Kết quả lượt A (ngân sách 8 s, 6 tiến trình)

Tổng: 660/860 lần chạy giải được. Trạng thái: OK 660, TIMEOUT 181, TRACKING_FAILED 12, START_INVALID 4,
GOAL_INVALID 3. **0 vi phạm**: không có đường nào planner báo OK mà kiểm độc lập thấy chạm hoặc góc lái vượt giới hạn.
Xe tham chiếu giải được 15/20 sa bàn. Năm ca không giải được: `parallel_122`, `parallel_115`, `zigzag_corridor`,
`pocket_exit_park` (hết giờ) và `uturn_w46` (TRACKING_FAILED; cùng xe này giải được khi chạy một tiến trình lúc
20:53, mục 4).

Ký hiệu trong ma trận: ✓ giải được; T hết giờ; ✗ thất bại khác (NO_PATH, xuất phát/đích chạm, ô nhỏ hơn xe, bám hỏng). Mỗi ô xếp các mức từ giảm nhiều nhất tới tăng nhiều nhất, hai phía cách nhau bằng `/`: `−20 −10 −5 / +5 +10 +20`. Hai cột `lon_lai_kem`, `nho_lai_gat` chỉ có một phía: `+5 +10 +20`. Trong bảng ca lật: ✓ giải được, T hết giờ, TF TRACKING_FAILED (có đường nhưng xe mô phỏng dừng ngoài dung sai), NP NO_PATH.

| Sa bàn | gốc | length | width | overhangs | wheelbase | max_steer | kich_thuoc | lon_lai_kem | nho_lai_gat |
|---|---|---|---|---|---|---|---|---|---|
| `parallel_160` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓T` | `✓✓T` | `✓✓✓` |
| `parallel_135` | ✓ | `✓✓✓/TTT` | `✓✓✓/✓✓T` | `✓✓✓/✓✓✓` | `✓✓✓/✗TT` | `✓✓✓/✓✓✓` | `✓✓✓/✓TT` | `TTT` | `✓✓✓` |
| `parallel_122` | T | `✓✓✓/TTT` | `T✗T/TTT` | `✓TT/TTT` | `✓✓T/TTT` | `TTT/TTT` | `✓✓✓/TTT` | `TTT` | `✗✓✓` |
| `parallel_115` | T | `✓TT/TT✗` | `TTT/TTT` | `TTT/TTT` | `✗TT/TTT` | `TTT/TTT` | `✓✗T/TT✗` | `TT✗` | `TT✓` |
| `perp_aisle_170` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓` | `✓✓✓` |
| `perp_aisle_135` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓` | `✓✓✓` |
| `perp_aisle_115` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓T` | `✓✓✓/✓✓✓` | `✓✓✓/✓TT` | `✓TT` | `✓✓✓` |
| `uturn_w70` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓` | `✓✓✓` |
| `uturn_w55` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓` | `✓✓✓` |
| `uturn_w46` | ✗ | `✓✓✓/TTT` | `✓✗✓/TTT` | `✓✓✓/TTT` | `✓✓✓/TTT` | `TTT/✗✓✓` | `✓✓✓/TTT` | `TTT` | `✓✓✓` |
| `reverse_long_corridor` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓` | `✓✓✓` |
| `lateral_shift` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓` | `✓✓✓` |
| `zigzag_corridor` | T | `TTT/TTT` | `TTT/TTT` | `TTT/TTT` | `TTT/TTT` | `TTT/TTT` | `TTT/TTT` | `TTT` | `TTT` |
| `deadend_turn_park` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓` | `✓✓✓` |
| `pocket_exit_park` | T | `✓✗T/TT✗` | `TTT/TTT` | `TTT/TTT` | `TTT/TT✗` | `TTT/TTT` | `✓✓T/TT✗` | `TT✗` | `T✓✗` |
| `pillar_at_slot_mouth` | ✓ | `✓✓✓/✓✓✗` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓T` | `✓✓✗` | `✓✓✓` |
| `kb_bai_do_xe` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓` | `✓✓✓` |
| `kb_bai_do_xe_lon_xon` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓` | `✓✓✓` |
| `kb_giai_doan_0_unknown` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓` | `✓✓✓` |
| `kb_sa_ban_3x2_hai_hop` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓` | `✓✓✓` |

Ca lật OK → hỏng, và kết quả chạy lại với 20 s (chạy lại cũng 6 tiến trình song song):

| Sa bàn | Số ca lật | Biến thể lật (kết quả lượt chính → chạy lại 20 s) |
|---|---:|---|
| `parallel_160` | 2 | `kich_thuoc+20` (T → T), `lon_lai_kem+20` (T → T) |
| `parallel_135` | 12 | `length+5` (T → ✓), `length+10` (T → ✓), `length+20` (T → T), `width+20` (T → T), `wheelbase+5` (TF → ✓), `wheelbase+10` (T → ✓), `wheelbase+20` (T → TF), `kich_thuoc+10` (T → ✓), `kich_thuoc+20` (T → T), `lon_lai_kem+5` (T → TF), `lon_lai_kem+10` (T → ✓), `lon_lai_kem+20` (T → T) |
| `perp_aisle_115` | 5 | `wheelbase+20` (T → T), `kich_thuoc+10` (T → T), `kich_thuoc+20` (T → T), `lon_lai_kem+10` (T → T), `lon_lai_kem+20` (T → T) |
| `pillar_at_slot_mouth` | 3 | `length+20` (TF → ✓), `kich_thuoc+20` (T → T), `lon_lai_kem+20` (TF → TF) |

| Sa bàn (xe tham chiếu không giải được) | Số biến thể giải được | Biến thể |
|---|---:|---|
| `parallel_122` (T) | 11 | `length-5`, `length-10`, `length-20`, `overhangs-20`, `wheelbase-10`, `wheelbase-20`, `kich_thuoc-5`, `kich_thuoc-10`, `kich_thuoc-20`, `nho_lai_gat+10`, `nho_lai_gat+20` |
| `parallel_115` (T) | 3 | `length-20`, `kich_thuoc-20`, `nho_lai_gat+20` |
| `uturn_w46` (TF) | 19 | `length-5`, `length-10`, `length-20`, `width-5`, `width-20`, `overhangs-5`, `overhangs-10`, `overhangs-20`, `wheelbase-5`, `wheelbase-10`, `wheelbase-20`, `max_steer+10`, `max_steer+20`, `kich_thuoc-5`, `kich_thuoc-10`, `kich_thuoc-20`, `nho_lai_gat+5`, `nho_lai_gat+10`, `nho_lai_gat+20` |
| `pocket_exit_park` (T) | 4 | `length-20`, `kich_thuoc-10`, `kich_thuoc-20`, `nho_lai_gat+10` |

## 6. Kết quả lượt B (ngân sách 20 s, 4 tiến trình)

Thời gian 21:07:58 → 21:38:32 (1835 s). Tổng: 679/860 lần chạy giải được. Trạng thái: OK 679, TIMEOUT 137,
TRACKING_FAILED 27, NO_PATH 10, START_INVALID 4, GOAL_INVALID 3. **0 vi phạm.** Xe tham chiếu giải được 16/20 sa bàn
(`uturn_w46` giải được, 8,78 s, 19 lần đổi chiều). Bốn ca không giải được: `parallel_122`, `parallel_115`,
`zigzag_corridor`, `pocket_exit_park` (hết giờ 20 s).

| Sa bàn | gốc | length | width | overhangs | wheelbase | max_steer | kich_thuoc | lon_lai_kem | nho_lai_gat |
|---|---|---|---|---|---|---|---|---|---|
| `parallel_160` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓T` | `✓✓T` | `✓✓✓` |
| `parallel_135` | ✓ | `✓✓✓/✓✓T` | `✓✓✓/✗✓T` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✗T` | `✗✓T` | `✓✓✓` |
| `parallel_122` | T | `✓✓✓/TTT` | `T✗T/TTT` | `✓✓✓/TTT` | `✓✓✓/TTT` | `TTT/TTT` | `✓✓✓/TTT` | `TTT` | `✓✓✓` |
| `parallel_115` | T | `✓✗T/TT✗` | `TTT/TTT` | `TTT/TTT` | `✓TT/TTT` | `TTT/TTT` | `✓✓T/TT✗` | `TT✗` | `T✓✓` |
| `perp_aisle_170` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓` | `✓✓✓` |
| `perp_aisle_135` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓` | `✓✓✓` |
| `perp_aisle_115` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓T` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓T` | `✓TT` | `✓✓✓` |
| `uturn_w70` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓` | `✓✓✓` |
| `uturn_w55` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓` | `✓✓✓` |
| `uturn_w46` | ✓ | `✓✓✓/TT✗` | `✓✗✓/✗✗✓` | `✓✓✓/TTT` | `✓✓✓/TTT` | `T✓✓/✓✓✗` | `✓✓✓/TT✗` | `TT✗` | `✓✓✓` |
| `reverse_long_corridor` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓` | `✓✓✓` |
| `lateral_shift` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓` | `✓✓✓` |
| `zigzag_corridor` | T | `TTT/T✗✗` | `TTT/TTT` | `TTT/TTT` | `TTT/TT✗` | `TTT/TTT` | `TTT/T✗✗` | `T✗✗` | `TTT` |
| `deadend_turn_park` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓` | `✓✓✓` |
| `pocket_exit_park` | T | `✓✓✗/TT✗` | `✗✗✗/✗✗T` | `✗TT/T✗T` | `✗✗T/✗T✗` | `T✗T/✗T✗` | `✓✓✓/TT✗` | `TT✗` | `✗✓✗` |
| `pillar_at_slot_mouth` | ✓ | `✓✓✓/✓✓✗` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓T` | `✓✓✗` | `✓✓✓` |
| `kb_bai_do_xe` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓` | `✓✓✓` |
| `kb_bai_do_xe_lon_xon` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓` | `✓✓✓` |
| `kb_giai_doan_0_unknown` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓` | `✓✓✓` |
| `kb_sa_ban_3x2_hai_hop` | ✓ | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓/✓✓✓` | `✓✓✓` | `✓✓✓` |

Ca lật OK → hỏng, và kết quả chạy lại với 60 s (4 tiến trình song song):

| Sa bàn | Số ca lật | Biến thể lật (kết quả lượt chính → chạy lại 60 s) |
|---|---:|---|
| `parallel_160` | 2 | `kich_thuoc+20` (T → T), `lon_lai_kem+20` (T → ✓) |
| `parallel_135` | 7 | `length+20` (T → T), `width+5` (TF → TF), `width+20` (T → ✓), `kich_thuoc+10` (TF → ✓), `kich_thuoc+20` (T → T), `lon_lai_kem+5` (TF → ✓), `lon_lai_kem+20` (T → T) |
| `perp_aisle_115` | 4 | `wheelbase+20` (T → T), `kich_thuoc+20` (T → NP), `lon_lai_kem+10` (T → T), `lon_lai_kem+20` (T → T) |
| `uturn_w46` | 20 | `length+5` (T → T), `length+10` (T → T), `length+20` (NP → NP), `width+5` (TF → TF), `width-10` (TF → ✓), `width+10` (TF → TF), `overhangs+5` (T → TF), `overhangs+10` (T → TF), `overhangs+20` (T → TF), `wheelbase+5` (T → T), `wheelbase+10` (T → ✓), `wheelbase+20` (T → T), `max_steer-20` (T → ✓), `max_steer+20` (TF → ✓), `kich_thuoc+5` (T → TF), `kich_thuoc+10` (T → T), `kich_thuoc+20` (NP → NP), `lon_lai_kem+5` (T → ✓), `lon_lai_kem+10` (T → T), `lon_lai_kem+20` (NP → NP) |
| `pillar_at_slot_mouth` | 3 | `length+20` (TF → ✓), `kich_thuoc+20` (T → T), `lon_lai_kem+20` (TF → TF) |

| Sa bàn (xe tham chiếu không giải được) | Số biến thể giải được | Biến thể |
|---|---:|---|
| `parallel_122` (T) | 15 | `length-5`, `length-10`, `length-20`, `overhangs-5`, `overhangs-10`, `overhangs-20`, `wheelbase-5`, `wheelbase-10`, `wheelbase-20`, `kich_thuoc-5`, `kich_thuoc-10`, `kich_thuoc-20`, `nho_lai_gat+5`, `nho_lai_gat+10`, `nho_lai_gat+20` |
| `parallel_115` (T) | 6 | `length-20`, `wheelbase-20`, `kich_thuoc-10`, `kich_thuoc-20`, `nho_lai_gat+10`, `nho_lai_gat+20` |
| `pocket_exit_park` (T) | 6 | `length-10`, `length-20`, `kich_thuoc-5`, `kich_thuoc-10`, `kich_thuoc-20`, `nho_lai_gat+10` |

Mức lật đầu tiên (lượt B). Mỗi ô là mức nhỏ nhất (theo độ lớn) mà từ đó ca không còn giải được; `—` là không lật trong
các mức đã chạy; `*` là không đơn điệu (một mức lớn hơn lại giải được). Chỉ gồm các sa bàn xe tham chiếu giải được.
Bảng này tính trên lượt chính (20 s), chưa tính kết quả chạy lại 60 s:

| Sa bàn | length | width | overhangs | wheelbase | max_steer | kich_thuoc | lon_lai_kem | nho_lai_gat |
|---|---|---|---|---|---|---|---|---|
| `parallel_160` | — | — | — | — | — | +20 % | +20 % | — |
| `parallel_135` | +20 % | +5 %* | — | — | — | +10 % | +5 %* | — |
| `perp_aisle_170` | — | — | — | — | — | — | — | — |
| `perp_aisle_135` | — | — | — | — | — | — | — | — |
| `perp_aisle_115` | — | — | — | +20 % | — | +20 % | +10 % | — |
| `uturn_w70` | — | — | — | — | — | — | — | — |
| `uturn_w55` | — | — | — | — | — | — | — | — |
| `uturn_w46` | +5 % | +5 %*, -10 %* | +5 % | +5 % | +20 %, -20 % | +5 % | +5 % | — |
| `reverse_long_corridor` | — | — | — | — | — | — | — | — |
| `lateral_shift` | — | — | — | — | — | — | — | — |
| `deadend_turn_park` | — | — | — | — | — | — | — | — |
| `pillar_at_slot_mouth` | +20 % | — | — | — | — | +20 % | +20 % | — |
| `kb_bai_do_xe` | — | — | — | — | — | — | — | — |
| `kb_bai_do_xe_lon_xon` | — | — | — | — | — | — | — | — |
| `kb_giai_doan_0_unknown` | — | — | — | — | — | — | — | — |
| `kb_sa_ban_3x2_hai_hop` | — | — | — | — | — | — | — | — |

## 7. Đọc kết quả

Chỉ ghi điều hai lượt cùng cho thấy. Tất cả là mô phỏng, quanh xe giả định, ở mức ±5/10/20 %.

1. **Mười một sa bàn giải được với cả 43 biến thể, ở cả hai lượt:** `perp_aisle_170`, `perp_aisle_135`, `uturn_w70`,
   `uturn_w55`, `reverse_long_corridor`, `lateral_shift`, `deadend_turn_park` và cả bốn kịch bản 3 × 2 m trong
   `scenarios/` (`kb_bai_do_xe`, `kb_bai_do_xe_lon_xon`, `kb_giai_doan_0_unknown`, `kb_sa_ban_3x2_hai_hop`). Trong
   khoảng ±20 % quanh xe giả định, không biến thể nào làm các ca này hết đỗ được trong mô phỏng. Với bốn kịch bản
   `kb_*`, khoảng hở nhỏ nhất của đường lập nằm trong 0,9–18,4 cm tùy biến thể, lập đường chậm nhất 3,4 s (lượt A)
   và 2,5 s (lượt B).
2. **Mười cặp (sa bàn, biến thể) hỏng ở cả hai lượt, kể cả khi chạy lại** (8 s → 20 s ở lượt A, 20 s → 60 s ở lượt B).
   Cả mười đều là xe **dài hơn** 10–20 %:
   - `parallel_135` với `length+20`, `kich_thuoc+20`, `lon_lai_kem+20`. Ô cố định dài 1,35 × 0,31 = 0,42 m; xe dài
     0,31 × 1,2 = 0,372 m, tức ô chỉ còn 1,125 lần thân xe. Tỉ lệ đó chật hơn `parallel_115` (1,15 lần), ca mà xe tham
     chiếu cũng chưa giải được trong 20 s.
   - `perp_aisle_115` với `wheelbase+20`, `kich_thuoc+20`, `lon_lai_kem+10`, `lon_lai_kem+20`. Lối đi cố định
     1,15 × 0,31 = 0,357 m.
   - `pillar_at_slot_mouth` với `kich_thuoc+20`, `lon_lai_kem+20`.
   - `parallel_160` với `kich_thuoc+20`.

   Như vậy, trên bộ sa bàn này, phía nguy hiểm là xe **dài hơn** giả định (chiều dài thân, chiều dài cơ sở), nhất là khi
   đồng thời lái kém hơn. Ngoài `uturn_w46` (điểm 4), riêng bề rộng, riêng phần nhô, hay riêng góc lái (±20 %) không
   tạo cặp hỏng nào ở cả hai lượt.
   Đây là kết quả của planner hiện tại trong ngân sách đã cho, không phải chứng minh vô nghiệm.
3. **Nhiều ca lật chỉ do hết giờ.** Ở lượt A, 6/12 ca lật của `parallel_135` giải được khi chạy lại 20 s. Ở lượt B,
   `parallel_135` với `width+20`, `kich_thuoc+10`, `lon_lai_kem+5`, `parallel_160` với `lon_lai_kem+20` và
   `pillar_at_slot_mouth` với `length+20` giải được khi chạy lại 60 s. Kết quả không đơn điệu cũng có: lượt B,
   `parallel_135` hỏng ở `width+5` (TRACKING_FAILED cả khi chạy lại 60 s) nhưng giải được ở `width+10`. Vì vậy một ô
   "hỏng" đơn lẻ trong ma trận không đủ để kết luận; chỉ nên tin các mẫu lặp lại qua nhiều mức và cả hai lượt.
4. **`uturn_w46` (hành lang 0,46 m) nằm sát biên với chính xe tham chiếu.** Cùng xe tham chiếu, tối 24/09/2026: một
   tiến trình lúc 20:53 giải được trong 3,77 s (lần chạy không có sha256 mã nguồn, xem ghi chú bảng mục 4); lượt A
   không giải được (TRACKING_FAILED); một tiến trình lúc 21:39 (ngân sách 8 s, tải CPU 53 % lúc bắt đầu) hết giờ;
   lượt B và một tiến trình lúc 21:40 (20 s) giải được trong 8,78 s và 9,80 s. Ở lượt chính của B (20 s), mọi biến thể dài hơn (`length`, `overhangs`, `wheelbase`, `kich_thuoc` phía +,
   và `lon_lai_kem`) đều hỏng; ba biến thể +20 % (`length+20`, `kich_thuoc+20`, `lon_lai_kem+20`) trả NO_PATH (nấc
   cuối vét hết lưới của nó); chạy lại 60 s thì `wheelbase+10` và `lon_lai_kem+5` giải được. Các biến thể ngắn hơn
   (`length`, `overhangs`, `wheelbase`, `kich_thuoc` phía −, và `nho_lai_gat`) giải được ở cả hai lượt. Kết quả theo
   bề rộng và góc lái thì lẫn lộn, không đơn điệu.
   Kết luận được: nếu MN300 dài hơn giả định thì bài quay đầu trong hành lang 0,46 m có thể không còn dùng được; chưa
   khoanh được ngưỡng bằng dữ liệu này.
5. **Xe nhỏ hơn giải được các ca mà xe tham chiếu chưa giải được** trong ngân sách: `parallel_122` (từ `length-5`,
   cả hai lượt), `parallel_115` (`length-20`, `kich_thuoc-20`, `nho_lai_gat+20`, cả hai lượt), `pocket_exit_park`
   (`length-20`, `kich_thuoc-10`, `kich_thuoc-20`, `nho_lai_gat+10`, cả hai lượt). Các đường này có thể rất nhiều lần
   đổi chiều (lượt B có đường tới 98 lần, `parallel_122` / `overhangs-5`), tức "giải được" trong mô phỏng chưa có nghĩa
   là dùng được trên xe thật (số lần đổi chiều chấp nhận được CHƯA CHỐT). *(Ngày 24/09/2026 một agent khác đã đổi nhãn
   `expected` của `parallel_122` và `parallel_115` sang `feasible` kèm đường chứng, xem
   [KIEM_THU_DO_BEN_GIAI_DOAN_0.md](KIEM_THU_DO_BEN_GIAI_DOAN_0.md) mục 6; hình học của cả 16 ca không đổi — `scene_digest`
   của 860 lần chạy lượt A khớp với hình học dựng lại sau khi đổi nhãn.)*
6. **Không có ca hỏng vì hình học không đặt được xe** ở các sa bàn xe tham chiếu giải được. `START_INVALID` và
   `GOAL_INVALID` chỉ xuất hiện ở hai sa bàn xe tham chiếu cũng không giải được: `parallel_115` (ô 1,15 × 0,31 m ngắn
   hơn thân xe dài thêm 20 %) và `pocket_exit_park` (xe dài thêm 20 % hoặc chiều dài cơ sở +20 % không còn nằm trong
   ngách lúc xuất phát).
7. **Khoảng hở rất nhỏ.** Trong các lần giải được, khoảng hở nhỏ nhất của đường lập xuống tới 0,26 cm, và khi xe mô
   phỏng chạy theo đường thì xuống tới 0,05 cm (lượt A, `perp_aisle_115`, xe tham chiếu) và 0,14 cm (lượt B). Lượt A
   có 29 lần chạy, lượt B có 33 lần, mà xe mô phỏng đi cách vật cản hoặc mép sa bàn dưới 5 mm. Khoảng hở không đổi đơn
   điệu theo cỡ xe, vì mỗi lần planner chọn một đường khác. Trên xe thật, sai số định vị và bám đường nhiều khả năng lớn hơn các
   khoảng này (CHƯA ĐO), nên "giải được trong mô phỏng" với khoảng hở vài mm không phải bằng chứng xe thật đi qua được.

## 8. Giới hạn

- **Chỉ mô phỏng.** Xe động học lý tưởng, không trượt, không trễ cơ cấu chấp hành; bộ bám và planner là bản hiện tại.
  Không có số nào là số đo MN300.
- **Xe tham chiếu là giả định.** Sa bàn của 16 ca khó được thiết kế quanh xe 0,31 × 0,14 m giả định; "±20 %" là quanh
  giả định đó. Nếu MN300 thật lệch xa hơn 20 % thì phải chạy lại với `--plan-config` (hoặc với `--levels` lớn hơn).
- **Một hạt giống RRT, một lần chạy mỗi ô.** Nấc `ngẫu nhiên` của portfolio phụ thuộc hạt giống và thời gian; chưa chạy
  nhiều hạt giống để có tỉ lệ.
- **Tải máy** (mục 4). Muốn số thời gian dùng được cho khóa luận thì chạy lại khi máy rảnh, `--workers 1`, và ghi rõ
  điều kiện. CHƯA LÀM.
- **Mức thô.** Chỉ có 5/10/20 %; "mức lật đầu tiên" chỉ khoanh ngưỡng trong khoảng giữa hai mức, không phải ngưỡng
  chính xác.
- **Hết giờ ≠ vô nghiệm; giải được ≠ an toàn trên xe thật.** Khoảng hở nhỏ nhất vài mm trong mô phỏng (mục 7) không còn
  ý nghĩa khi có sai số định vị và bám đường thật.
- **Quy ước đích** cho sa bàn không có ô đỗ (mục 2, bước 3) là lựa chọn của công cụ, CHƯA CHỐT.
- **Nhãn `expected`** của `hard_cases.py` được đặt cho xe mặc định (GIAI_DOAN_4_CHUAN_BI.md mục 5.1). Công cụ in nhãn
  đó nhưng không dựa vào nó để chấm.
- Chưa kiểm trên laptop RTX 3050 Ti (máy nộp đồ án).

## 9. Việc tiếp theo

1. Khi có số đo B1/B2 của MN300 (GIAI_DOAN_4_CHUAN_BI.md mục 3): lập `configs/vehicle_measured.json` rồi chạy lệnh
   `--plan-config` ở mục 3, ngân sách 20 s, khi máy rảnh. Đặt kết quả cạnh bảng ở đây.
2. Chạy lại một lượt khi máy rảnh, `--workers 1`, để có số thời gian sạch cho khóa luận.
3. Nếu cần ngưỡng mịn hơn cho một ca (ví dụ `parallel_135`): `--scenes parallel_135 --params length --levels 1,2,3,4,5`.
4. Sa bàn thật của đồ án chưa dựng; khi dựng, thêm nó vào `scenarios/` để công cụ tự chạy trên nó.
