# Kiểm thử mở rộng giai đoạn 0

Ngày 20/09/2026. Phạm vi: **phần mềm mô phỏng**. Kết luận sau sửa: bộ pytest **220/220 đạt**; chiến dịch **2.880 trường hợp không ghi nhận vi phạm các bất biến đã kiểm tra**. Đây không phải chứng minh mọi tình huống đều an toàn hoặc mọi bài đỗ đều giải được. *(Ghi chú 25/09/2026: 220 là số của ngày 20/09; số của bộ test hiện nay ở mục 2.)*

## 1. Lỗi đã tái hiện và sửa

Test hồi quy mới ban đầu cho **25 ca thất bại / 3 ca đạt**. Nhiều ca tham số hóa cùng kiểm tra một nhóm lỗi, không diễn giải thành 25 lỗi độc lập. [Báo cáo trước sửa](evidence/robustness_regressions_before.xml). Snapshot code trước sửa (`source_before.zip`) và bản diff (`changes.patch`) nằm trong `review_artifacts/phase0_robustness/`; thư mục này bị `.gitignore` bỏ qua nên chỉ có trên máy làm việc, không có trên GitHub (ghi chú 24/09/2026).

| Nhóm lỗi | Sửa và điều kiện kiểm tra |
|---|---|
| Phiên đã đóng vẫn chạy được | Chặn chạy tự động/lái tay sau close; advance không tiến đồng hồ của phiên đã đóng. Close là kết thúc mô phỏng, không tính như thử phanh. |
| Hết thời gian chạy làm FAULT khi tốc độ còn khác 0 | Phát `RUN_TIMEOUT`, vô hiệu đường và phanh qua STOPPING; chỉ kết thúc FAULT sau khi tốc độ bằng 0. |
| Hết giờ cắt ngang một yêu cầu dừng đang thực hiện | Xe tiếp tục phanh tới 0; giữ đúng kết quả STOPPED của yêu cầu dừng. |
| STOPPED nhưng còn tốc độ nhỏ | Không dùng ngưỡng 1 mm/s để đóng băng trạng thái; mô hình tiếp tục bước phanh cuối tới 0. |
| Đổi đoạn tiến/lùi khi vẫn đang chuyển động | Thêm test tái hiện tốc độ còn 0,003 m/s; tracker chờ tốc độ 0 trước khi chuyển đoạn. |
| NaN/Infinity lọt vào lệnh, nhịp thời gian hoặc phản hồi | Từ chối lệnh/dt không hữu hạn trước khi thay đổi trạng thái. Phản hồi hỏng/từ tương lai bị chặn trước controller và dẫn tới dừng. |
| Vật cản/lỗi thứ hai đến trong lúc phanh bị từ chối | Cho cập nhật vật cản và mất phản hồi trong STOPPING; giữ phanh, lưu sự kiện và replay được. |
| Xuất phát đã va chạm nhưng SimWorld chưa giữ cờ collision | Đặt cờ va chạm từ kiểm tra ban đầu; không cho xe chạy thoát ra rồi coi lượt chạy là hợp lệ. |
| Preview báo xong khi xe còn ngoài dung sai | Tách `path_finished` khỏi `completed`; hoàn thành phải thỏa dung sai. Portfolio truyền đúng dung sai người dùng vào rollout, giữ `TRACKING_FAILED` để chẩn đoán đường bám không đạt. |
| Quỹ đạo/controller vượt tốc độ cấu hình nhỏ | Giới hạn tốc độ mục tiêu cả trong quỹ đạo và đầu ra controller, kể cả creep speed. |

Test bổ sung có trường hợp vật cản ở hai phía khoảng phanh, cả tiến và lùi; đích bị chiếm sau khi dừng; reset không dùng lại đường cũ; kết hợp mất dữ liệu với hai vật cản và replay chính xác.

## 2. Kết quả chạy

### Pytest và kiểm tra từng nhánh

- **220 passed**, khoảng 60,23 s: [JUnit](evidence/robustness_pytest.xml), [phân bố test theo module](evidence/robustness_test_inventory.json).
- Tăng 51 ca pytest so với bộ 169 ca ban đầu: kiểm tra runtime/an toàn, oracle hình học và xác nhận dung sai của planner.
- Khi đo coverage: **210 passed, 10 deselected**. Mười test `planner_budget` được chạy trong lượt pytest đầy đủ không gắn tracer. Không nới thời hạn hoặc bỏ chúng khỏi lượt kiểm thử bình thường. [JUnit coverage](evidence/robustness_coverage_pytest.xml).
- *(Ghi chú 25/09/2026: các số trên là của ngày 20/09. Ở `54cb3e2`, `pytest --collect-only` bằng `.venv` thu được 1.243 test, trong đó 15 test mang dấu `planner_budget`; lần chạy đủ ngày 25/09 trên máy bàn: `.venv` 1.242 đạt, 7 bỏ qua (sáu mô-đun cần torch bị bỏ qua cả mô-đun nên không nằm trong 1.243, cộng một test trong `tests/test_labels.py` cần torch; 1.242 + 1 = 1.243), 0 lỗi. Chạy lại theo mục 5 nay ra số khác 220 / 210.)*

### Chiến dịch theo seed

[Tóm tắt bằng máy](../runs/robustness_final_2026-09-20/summary.json), [từng trường hợp](../runs/robustness_final_2026-09-20/cases.jsonl), [danh sách vi phạm](../runs/robustness_final_2026-09-20/failures.json). *(Ghi chú 25/09/2026: `runs/` bị `.gitignore` bỏ qua, nên ba liên kết này chỉ mở được trên máy làm việc, không có trên GitHub hay trên laptop sau `git pull`.)*

| Loại | Số trường hợp | Điều được kiểm tra |
|---|---:|---|
| Tư thế/hình học | 2.000 | So sánh Shapely và FastCollisionChecker với oracle độc lập; xe/vật xoay, nhiều kích thước, biên sa bàn và lề an toàn. |
| Chuyển động/vùng quét | 600 | So sánh vùng quét với 81 tư thế lấy mẫu trên cung độc lập; không bỏ sót va chạm mà oracle lấy mẫu phát hiện. |
| Phiên kín vòng + lỗi | 240 | Thẳng, lùi, cua, lùi cua, đổi chiều; vật phía trước/hông/chiếm đích; mất mẫu, lỗi đồng thời, chèn sát khoảng phanh và tại điểm đổi chiều. |
| Lập đường + thực thi | 40 | Bốn nhóm bài đỗ với kích thước/giới hạn xe biến đổi; kiểm tra đường và tư thế xen giữa bằng oracle, sau đó chạy kín vòng. |

**Kết quả được phân biệt:** 240 phiên runtime gồm **25 COMPLETED, 185 STOPPED và 30 FAULT**. Ba mươi FAULT là các ca cố tình chèn vật quá gần để phanh; chúng không được tính là đỗ thành công. Năm ca STOPPED là dữ liệu trễ ngay từ đầu; các ca dừng còn lại có sự kiện chủ động. **40/40 ca planner của chiến dịch trả đường hợp lệ và thực thi hoàn thành.** Tổng vi phạm bất biến: **0**. Thời gian chiến dịch cuối khoảng **65,06 s**.

Mỗi dòng có loại, index, seed, cấu hình và kết quả. Manifest lưu môi trường, tham số và SHA-256 source; `source.zip` giữ code/tests/lockfile tại thời điểm chạy. Đã tái hiện riêng `runtime:137` và so sánh **toàn bộ dòng kết quả, trạng thái cuối và sự kiện** với bản ghi gốc: khớp chính xác.

### Các bất biến

- Trạng thái/lệnh hữu hạn; tốc độ và góc lái không vượt cấu hình.
- Tốc độ đổi lái, gia tốc/phanh trong giới hạn; khi đổi dấu tốc độ phải đủ thời gian phanh qua 0.
- Không nhảy vị trí vượt quãng tối đa của một bước vật lý.
- Vật cản mới làm mất hiệu lực đường, không cho lập đường trong lúc phanh.
- Các trạng thái kết thúc chạy phải có tốc độ 0; không báo COMPLETED sau một yêu cầu dừng bảo vệ.
- COMPLETED phải đúng dung sai và không có va chạm do oracle phát hiện.
- Reset sau dừng an toàn giữ vị trí vừa dừng và bỏ đường cũ.

## 3. Phạm vi tham số đã quét

Đây là tham số giả định của chiến dịch, chưa phải thông số MN300 đã đo:

| Tham số | Miền kiểm tra |
|---|---|
| Kích thước xe runtime/hình học | 0,7–1,4 lần cấu hình mặc định |
| Góc lái tối đa | 22–38° |
| Tốc độ tối đa | 0,06–0,30 m/s |
| Gia tốc / giảm tốc | 0,15–0,45 / 0,25–0,90 m/s² |
| Tốc độ đổi lái | 35–140°/s |
| Bước vật lý | 2,5 / 5 / 10 ms; chu kỳ controller 20 ms |
| Profile nhẹ | Trễ 40 ms; σ vị trí 2 mm; σ yaw 0,2°; mất mẫu 2% |
| Profile vừa | Trễ 80 ms; σ vị trí 5 mm; σ yaw 0,5°; mất mẫu 5% |
| Profile dữ liệu cũ từ đầu | Trễ 250 ms, vượt hạn 150 ms; phải giữ dừng |

Các bài đỗ có planner dùng bốn nhóm `parallel_160`, `perp_aisle_170`, `reverse_long_corridor`, `lateral_shift`, với footprint/tốc độ/phanh biến đổi và ngân sách 6 s mỗi bài. Bộ ca khó có ngân sách 8 s vẫn được kiểm tra riêng trong pytest.

## 4. Độ bao phủ và giới hạn của phép đo

[Báo cáo HTML đầy đủ](evidence/coverage_html/index.html) (chỉ có trên máy làm việc, không có trên GitHub: coverage.py tự tạo `.gitignore` bỏ qua cả thư mục này; ghi chú 24/09/2026), [JSON toàn bộ](evidence/coverage_robustness.json), [phạm vi cốt lõi](evidence/coverage_core.json).

| Phạm vi | Dòng lệnh đã chạy | Nhánh đã chạy |
|---|---:|---:|
| 10 module vận hành cốt lõi được liệt kê trong `coverage_core.json` | **1.052/1.120 = 93,93%** | **246/292 = 84,25%** |
| Toàn package, gồm UI, công cụ đánh giá và nhiều planner thử nghiệm | **6.041/11.503 = 52,52%** | **1.372/3.600 = 38,11%** |

Không dùng phần trăm của nhóm cốt lõi để đại diện cho toàn repository. Coverage này đo trên pytest, không cộng lượt campaign không gắn tracer. Baseline từng đạt 100% dòng/nhánh trong tracker vẫn bỏ sót lỗi giới hạn tốc độ và đổi chiều; coverage không đo đầy đủ không gian giá trị.

Một lần chạy pytest đồng thời với campaign khiến ca `uturn_w46` hết ngân sách 8 s; chạy riêng ca này tìm được đường đã kiểm chứng trong khoảng 3,98 s, và lượt đầy đủ chạy tách đạt 220/220. Lượt baseline có coverage tracer cũng gặp lỗi ngân sách. Các bằng chứng thất bại được giữ tại `robustness_concurrent_load_pytest.xml` và `robustness_baseline_pytest.xml`. Điều này cho thấy **khả năng tìm đường trong thời hạn phụ thuộc tải CPU**; TIMEOUT không được coi là vô nghiệm hình học.

Oracle dùng biến đổi số phức và SAT tổng quát, không gọi Shapely, FastCollisionChecker, body_corners hoặc bộ tích phân của xe để quyết định va chạm tham chiếu. Tuy vậy, kiểm tra chuyển động vẫn là **lấy mẫu**, không phải chứng minh liên tục cho mọi chuyển động. Biến đổi hình học 2D không bao phủ biến dạng lốp, trượt, vật 3D hoặc ngoại lai cảm biến thật.

## 5. Chạy lại

Trong thư mục `autopark`, chạy tuần tự:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest
.\.venv\Scripts\python.exe -X utf8 -m coverage run --branch --source=autopark -m pytest -m "not planner_budget"
.\.venv\Scripts\python.exe -X utf8 -m coverage html

$robustDir = "runs/robustness_" + (Get-Date -Format "yyyyMMdd_HHmmss")
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.robustness --out $robustDir

$caseDir = "runs/reproduce_" + (Get-Date -Format "yyyyMMdd_HHmmss")
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.robustness --out $caseDir --case runtime:137
```

Có thể đổi `--seed`, `--poses`, `--motions`, `--runs`, `--plans`. `--case KIND:INDEX` tái tạo đúng input theo seed và phiên bản code. Với planner có deadline theo thời gian thực, input được tái tạo nhưng đường tìm được có thể khác theo tải máy; không hứa replay thuật toán tìm kiếm sẽ giống từng nút.

Năm video/log của giai đoạn 0 đã được tạo lại bằng code sau sửa tại `runs/phase0_after_robustness/`; từng phiên đều phải replay khớp trước khi được coi là bằng chứng. Vẫn cần kiểm thử cảm biến, phản hồi thực và dừng phần cứng ở những giai đoạn tiếp theo.

## 6. Ghi chú 24/09/2026: kiểm lại nhãn `expected` của bộ ca khó

**Vì sao kiểm lại.** Tối 24/09/2026, một lượt `plan_parking` trên máy bàn (20 s mỗi ca, [GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md) mục 1.1) cho hai kết quả trái nhãn. `parallel_122` mang nhãn `infeasible` nhưng trả OK qua nấc 'ngẫu nhiên', với 86 lần đổi chiều (con số do tác tử chạy lượt đó báo lại; tài liệu kia không ghi con số này). `zigzag_corridor` mang nhãn `feasible` nhưng trả NO_PATH. Cần biết nhãn sai hay planner sai.

**Nhãn cũ nghĩa là gì, ai dùng.** Nhãn ghi theo nhật ký 08/09/2026. Ca được ghi `infeasible` khi duyệt rộng hai chiều trên một đồ thị chuyển động **rời rạc** không cho hai mặt sóng gặp nhau. Kho mã không có chương trình để tái chạy phép duyệt này. Nơi đọc nhãn:
- `evaluation/bench.py`: cột "kỳ vọng" trong bảng kết quả;
- `evaluation/render.py`: tiêu đề ảnh;
- `evaluation/sensitivity.py` (tệp mới, chưa commit; cập nhật 25/09/2026: đã commit trong `10a4735`): chỉ hiển thị;
- `tests/test_planner_hard_cases.py::test_ca_vo_nghiem_khong_bao_thanh_cong_gia`: khẳng định hai ca 122/115 là `infeasible` và không giải được trong 4 s. *(Sửa 25/09/2026: đổi tên thành `test_ca_rat_chat_khong_bao_thanh_cong_gia`; nay khẳng định nhãn `feasible`, cho phép OK/TIMEOUT/NO_PATH, và nếu planner báo OK thì đường phải qua phép kiểm va chạm độc lập `path_ok`.)*

`compare.py` và `robustness.py` không đọc nhãn.

Ghi chú 24/09/2026 (vòng sửa sau rà soát): còn ba tài liệu viện dẫn nhãn cũ, không thuộc phần việc này, đã CŨ sau khi đổi nhãn và cần chủ tệp cập nhật:
- `docs/evidence/ke_hoach/kiem_toan_ke_hoach_20260924.json`, mục [233], [239], [260]: lấy "các ca hard_cases 'infeasible' trả về không có đường" làm bằng chứng mô phỏng cho "không có đường phù hợp thì giữ dừng". Từ 24/09/2026 không ca nào mang nhãn `infeasible`, nên bằng chứng đó không còn;
- `docs/KICH_BAN_NGHIEM_THU.md` (dòng ~446, biến thể (b)): còn ghi `parallel_115` chỉ có đường 279 lần đổi chiều, "có nghiệm nhưng không thực dụng". Nay đã có đường chứng 13 lần (xem dưới);
- `docs/GIAI_DOAN_4_CHUAN_BI.md` mục 5.1: còn ghi "Nhãn `expected` (feasible / infeasible)".

*(Cập nhật 25/09/2026, kiểm ở `54cb3e2`: [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) (biến thể (b)) và [GIAI_DOAN_4_CHUAN_BI.md](GIAI_DOAN_4_CHUAN_BI.md) mục 5.1 đã có ghi chú ngày 25/09 về nhãn mới; ba mục [233], [239], [260] của tệp JSON kiểm toán vẫn giữ nguyên như ngày 24/09.)*

**Định nghĩa mới** (đầu tệp `autopark/evaluation/hard_cases.py`): nhãn nói về sự **tồn tại** của đường trong mô hình mà các planner dùng. Mô hình gồm: xe Reeds–Shepp, tiến và lùi; |độ cong| ≤ tan(δ_max)/L; đổi góc lái tức thời; thân chữ nhật; lề 0; tới đúng tư thế đích (lệch ≤ 1 mm, ≤ 0,1°).
- `feasible`: có đường chứng đã kiểm độc lập.
- `infeasible`: chỉ dùng khi có chứng minh hình học.
- `unknown`: chưa có cả hai.

Nhãn không nói đường có dùng được trên xe thật hay không.

**Cách kiểm độc lập.** Test mới: [tests/test_hard_cases_labels.py](../tests/test_hard_cases_labels.py). Test không chạy planner nên không phụ thuộc tải CPU. Mỗi đường chứng là một dãy cung (quãng có dấu, độ cong). Test tích phân lại bằng `collision_oracle.arc_pose`, rồi kiểm va chạm bằng `collision_oracle.pose_ok` (SAT số phức; không dùng Shapely hay bộ kiểm của planner). Bước mẫu h = 0,5 mm. Tại mỗi mẫu, thân xe phải hở ít nhất (1 + κ_max·r_max)·h/2 ≈ 0,45 mm. Giữa hai mẫu, mọi điểm trên thân xe đi không quá (1 + κ_max·r_max)·h. Vì vậy phép kiểm cho kết luận **không va chạm liên tục** trong mô hình thân chữ nhật, không chỉ tại các mẫu. Kết quả: cả 16/16 ca có đường chứng hợp lệ. Nguồn đường chứng:
- 15 ca lấy từ các lần chạy planner, lưu ở [witness_20260924.json](evidence/hard_cases/witness_20260924.json);
- 4 ca đỗ song song còn có thêm đường dựng giải tích (`parallel_shuffle_witness`);
- ghi chú 24/09/2026 (vòng sửa sau rà soát): `parallel_122` và `parallel_115` còn có đường chứng ngắn dựng riêng, lưu ở [witness_ngan_song_song_20260924.json](evidence/hard_cases/witness_ngan_song_song_20260924.json), tách khỏi tệp đường planner. Vì vậy `parallel_115` không còn "chỉ có đường giải tích"; planner vẫn chưa ra đường nào cho ca này.

Ghi chú 24/09/2026 (vòng sửa sau rà soát): công thức lề mẫu và ngưỡng lệch đích 1 mm / 0,1° nay được test chốt riêng: bổ đề "đi h/2 thì mọi góc thân xe dời không quá (1 + κ_max·r_max)·h/2" (và ở κ_max thì dời hơn 1,3·h/2, nên không bỏ được số hạng κ·r), một va chạm chỉ xảy ra giữa hai mẫu, và đích lệch hướng 0,2° hoặc lệch 2 mm. Kiểm đột biến trên bản sao (không sửa kho mã): lề h/4, lề h/2 không có κ·r, bước thô với lề cố định, lề 0, chỉ kiểm hai đầu cung, bỏ kiểm hướng, nới dung sai hướng lên 1° hay dung sai vị trí lên 5 cm — mỗi đột biến làm hỏng ít nhất một test. Tổng cộng 19 đột biến, gồm cả các đột biến ở hàm đổi quỹ đạo ra dãy cung, ở lệnh sinh đường chứng, ở tệp đường chứng ngắn và ở nhãn; bản không đột biến: 44 passed.

| Ca | Nhãn | Bằng chứng (24/09/2026) | Planner khi tái chạy (tải nặng, xem dưới) |
|---|---|---|---|
| `parallel_122` | `infeasible` → **`feasible`** | Đường OK của portfolio (40 s, nấc 'ngẫu nhiên'): 104 lần đổi chiều, 3,97 m. Mỗi bước là cung tròn đúng (sai lệch ≤ 1 µm; đo lại 24/09/2026 bằng `hard_cases._pair_fit_error` trên các điểm quỹ đạo đã lưu ở thư mục nháp: 0,91 µm, và `trajectory_to_arcs` trong kho mã cho lại đúng 154 cung đã lưu). Góc lái lớn nhất 25,5° = 0,85·δ_max; không va chạm; lệch đích 0,11 mm / 0,02°. Nhịp ngắn nhất 1,4 cm; 47/105 nhịp ngắn hơn 2 cm. Đây là đường thật, không phải lỗi bộ kiểm; chính ĐƯỜNG NÀY không thực dụng. Có thêm đường dựng giải tích: 60 chu kỳ, 121 lần đổi chiều. Ghi chú 24/09/2026 (vòng sửa sau rà soát): có đường chứng ngắn dựng riêng, 5 lần đổi chiều, 1,23 m, lái ≤ 27,46° (0,90·κ_max), hở Euclid nhỏ nhất ≈ 1,6 mm; các nhịp sau đoạn tiếp cận dài 2,1 / 4,2 / 4,1 / 5,7 / 3,3 cm ([ảnh](evidence/hard_cases/parallel_122_ngan_20260924.png)). | portfolio 8 s: TIMEOUT. 20 s với 4 hạt giống RRT: TIMEOUT cả 4. 40 s: OK, 104 lần. Nấc RRT riêng, 20 s, hạt giống mặc định: OK, 136 lần; hạt giống 5: TIMEOUT. Hạt giống 7, 60 s: OK, 150 lần. Chạy lại bằng lệnh mới (24/09/2026, vòng sửa): portfolio 30 s TIMEOUT; nấc RRT riêng, hạt giống 7, 60 s: OK nhưng 146 lần. |
| `parallel_115` | `infeasible` → **`feasible`** | Đường dựng giải tích: lùi chữ S, lùi thẳng, 139 chu kỳ nhích ngang (1,08 mm/chu kỳ), tiến thẳng. Tổng 279 lần đổi chiều, 9,08 m; lái ≤ 0,85·δ_max. Ghi chú 24/09/2026 (vòng sửa sau rà soát): có đường chứng ngắn dựng riêng, 13 lần đổi chiều, 1,32 m, lái ≤ 27,46°, hở Euclid nhỏ nhất ≈ 1,75 mm; vẫn có nhiều nhịp chỉ dài 0,95–1,7 cm ([ảnh](evidence/hard_cases/parallel_115_ngan_20260924.png)). | Lưới gộp riêng 60 s: NO_PATH (vét cạn lưới ở chặng le-hep-cuoi, 39.391 nút). RRT riêng 60 s: TIMEOUT. Lệnh mới, portfolio 30 s: TIMEOUT. |
| `zigzag_corridor` | `feasible` (giữ nguyên) | Đường của `cand_lattice_macro` chạy riêng 30 s (chặng le-hep-cuoi): 16 lần đổi chiều, 4,91 m, góc lái lớn nhất 29,1°, hở nhỏ nhất ≈ 2,4 mm. | portfolio 20 s với 3 hạt giống: TIMEOUT. 60 s: NO_PATH. Nấc 'gộp-kỹ' tìm ra đường nhưng bám mô phỏng va chạm tường t4; nấc 'ngẫu nhiên' hết giờ; nấc 'lưới mịn' vét cạn lưới rồi báo NO_PATH, và portfolio báo lại trạng thái đó. Lệnh mới (24/09/2026, vòng sửa): nấc 'gộp-kỹ' riêng 30 s ra đúng đường đã lưu; portfolio 30 s: NO_PATH. |

Ảnh: [zigzag_corridor](evidence/hard_cases/zigzag_corridor_20260924.png), [parallel_122](evidence/hard_cases/parallel_122_20260924.png), [parallel_115](evidence/hard_cases/parallel_115_20260924.png); đường chứng ngắn: [parallel_122_ngan](evidence/hard_cases/parallel_122_ngan_20260924.png), [parallel_115_ngan](evidence/hard_cases/parallel_115_ngan_20260924.png) (vẽ lại 24/09/2026; chú thích ảnh 122 nay nói "đường này không thực dụng", không gán cho ca). Các lần tái chạy planner của lượt đầu được liệt kê ở [reproduce_runs_20260924.json](evidence/hard_cases/reproduce_runs_20260924.json); tệp đó chỉ chứa lần chạy planner. Lần tái bám mô phỏng đường 104 lần nằm ở [rollout_parallel_122_20260924.json](evidence/hard_cases/rollout_parallel_122_20260924.json), các lần chạy bằng lệnh sinh đường chứng mới nằm ở [chay_lai_lenh_moi_20260924.json](evidence/hard_cases/chay_lai_lenh_moi_20260924.json). Các lần chạy planner của lượt đầu chạy 5–10 tiến trình song song, cùng lúc với tác tử khác, tải CPU đo được tới 97 %; các lần chạy bằng lệnh mới chạy 3 tiến trình cùng lúc, cũng cùng lúc với tác tử khác. Vì vậy thời gian chạy, và việc một nấc kịp hay hết giờ, **không phải số đo**; chỉ dùng làm bằng chứng định tính.

**Luận cứ cho đỗ song song (vì sao nhãn cũ sai).** Xét chu kỳ bốn cung cùng độ dài φ/κ: tiến lái phải, tiến lái trái, lùi lái phải, lùi lái trái. Tích phân đúng cho thấy sau chu kỳ, vị trí dọc và hướng xe trở về như cũ, còn xe dịch ngang đúng 4(1 − cos φ)/κ. Trong chu kỳ, trục sau chỉ đi trong đoạn dài 2·sin φ/κ, và hướng xe lệch không quá φ. Test `test_chu_ky_nhich_ngang_dung_cong_thuc` chốt công thức này.

Hệ quả: nếu ô dài hơn thân xe một khoảng dương, đích cách lề đường một khoảng dương, và làn đủ chỗ để lùi chữ S xuống sát hàng xe, thì luôn có đường. Ca `parallel_case` luôn chừa 2 cm tới lề; `parallel_shuffle_witness` báo lỗi khi `to_curb` ≤ 0. Điều kiện cách lề là cần. Nếu mép dưới thân xe ở đích nằm đúng trên lề, mọi cung tới đích với hướng θ ≠ 0 đẩy một góc thân xe xuống quá lề: góc đó lệch cỡ back·θ hoặc front·θ, còn trục sau chỉ nâng cỡ θ². Vì vậy ca đó vô nghiệm dù ô dài bao nhiêu (suy luận hình học, 24/09/2026; chưa có test riêng). Ô càng ngắn thì φ càng nhỏ và số lần đổi chiều của cách dựng này càng tăng (đây là số của cách dựng, không phải cận dưới; xem ghi chú đường chứng ngắn ở trên). Ở đây ô 122 dài 37,8 cm, ô 115 dài 35,7 cm, xe dài 31 cm (giả định). Phép vét cạn ngày 08/09 chỉ chứng minh không có đường trên đồ thị rời rạc của nó. Nguyên nhân có thể là nhịp ngắn nhất của đồ thị đó lớn hơn chỗ dư dọc ô (≈ 6,8 cm ở ô 122, ≈ 4,7 cm ở ô 115). Đây chỉ là phỏng đoán, CHƯA KIỂM ĐƯỢC, vì kho mã không còn chương trình này; nhật ký chỉ ghi mặt sóng từ đích nở vài chục trạng thái. Hệ quả nêu đầu đoạn là trường hợp riêng của một kết quả đã biết cho xe tiến–lùi được (Laumond và cộng sự; cần tra trích dẫn chính xác). Kết quả đó nói rằng nếu có đường "trượt tự do" với khoảng hở dương thì có đường khả thi cho xe. Ở đây không dựa vào trích dẫn, vì đã có đường dựng cụ thể và đã kiểm.

**Zigzag: nhãn đúng, planner có giới hạn.** Khe giữa đầu tường t3 (x = 1,23 m) và tường t2 (x = 1,40 m) rộng 17 cm; xe rộng 14 cm (giả định). Theo tọa độ tường, hành lang dưới và ngách trái chỉ thông ra phần còn lại qua khe này: t4 nối t3 với t1, t1 chặn đỉnh ngách trái, t2 chạy từ dưới biên lên y = 0,82 m. Đây là suy luận từ tọa độ, không có test riêng. Khi tâm thân xe đi qua đường giữa khe, dây cung qua tâm dài ít nhất bằng bề rộng xe, nên ở khe mỗi bên hở không quá 1,5 cm. `test_khe_zigzag_chan_moi_le_tim_kiem_tu_15_cm` chốt phần cục bộ này: nới thân xe 1,55 cm thì mọi tư thế có tâm trên đường giữa khe đều chạm, nới 1,40 cm thì có tư thế lọt.

Hệ quả với portfolio (đọc mã 24/09/2026, không sửa planner):
- nấc 'ngẫu nhiên' dùng lề tìm kiếm min(3 cm, nửa khoảng hở ở xuất phát/đích) = 3 cm, nên không thể ra đường, dù được nửa ngân sách;
- ba chặng đầu của lưới gộp dùng lề 3 / 3 / 1,5 cm. Lề 1,5 cm vừa khít khe, không còn chỗ, nên cả ba chặng cũng không thể;
- 'lưới mịn' dùng lề 1,2 cm, nhưng lưới 2,5 cm / 5° vét cạn mà không thấy đường;
- chỉ chặng le-hep-cuoi (lề 0,8 cm) ra đường. Chặng này bắt đầu muộn nhất sau 16 % ngân sách của nấc (sớm hơn nếu các chặng trước vét cạn sớm). Đường nó trả về chỉ hở ≈ 2,4 mm giữa các mẫu, dù thông báo ghi "lề 0,8 cm". Bộ bám mô phỏng lệch nhiều hơn thế, nên va chạm t4 và portfolio loại đường này.

Kết luận: NO_PATH ở ca này là giới hạn của planner (chia ngân sách, lề tìm kiếm, đường quá sát cho bộ bám), không phải bằng chứng vô nghiệm. `pocket_exit_park` cho thấy cùng hiện tượng. Lưới gộp tìm ra đường 6 lần đổi chiều, hở ≈ 1,0 mm, nhưng bám mô phỏng chạm `ngach_trai`. Portfolio 60 s rốt cuộc nhận một đường RRT 133 lần đổi chiều.

**Đỗ song song 122/115: cũng là giới hạn của planner** (ghi chú 24/09/2026, vòng sửa sau rà soát; đọc mã, không sửa planner). Portfolio TIMEOUT ở 8, 20 và 30 s trên `parallel_122`, các đường RRT 104–150 lần đổi chiều, và lưới gộp NO_PATH trên `parallel_115` là giới hạn của planner, không phải bản chất của ca: hai ca đều có đường chứng 5 / 13 lần đổi chiều. Hai ràng buộc đẩy các đường ngắn đó ra khỏi không gian tìm kiếm:
- lề tìm kiếm: ở hai ca này đích chỉ cách lề đường 2 cm. RRT dùng min(3 cm, nửa khoảng hở ở xuất phát/đích) = 1 cm (`planning/cand_rrt_rs.py` dòng 624). Lưới gộp dùng trần 3 / 3 / 1,5 / 0,8 cm, cũng bị chặn ở nửa khoảng hở, tức 1 / 1 / 1 / 0,8 cm. 'Lưới mịn' dùng min(1,2 cm, 0,4 × khoảng hở) = 0,8 cm (`planning/cand_reference.py` dòng 291–294). Đường chứng ngắn chỉ hở ≈ 1,6–1,75 mm, nên nằm ngoài mọi mức lề đó;
- trần góc lái: RRT và chặng đầu của lưới gộp dùng 0,85·δ_max, các chặng giữa và 'lưới mịn' dùng 0,90·δ_max, chặng le-hep-cuoi dùng 0,97·δ_max. Đường chứng ngắn lái 27,46° = 0,915·δ_max, vượt trần của mọi bộ trừ chặng le-hep-cuoi.

Cùng cách dựng, ở lái 25,5° (0,85·δ_max, mức của RRT) với hở thiết kế 1,5 mm, cho 9 lần (122) / 17 lần (115) đổi chiều. Ở hở 8–10 mm, bước "gỡ xe khỏi ô" tham lam của cách dựng thất bại ngay (máy bàn, 24/09/2026, script nháp). Vì vậy việc có tồn tại đường ít lần đổi chiều ở đúng lề 0,8–1 cm của planner hay không là CHƯA BIẾT. Ngoài ra RRT (ngẫu nhiên, có hạn giờ) và lưới rời rạc đều không đầy đủ, nên kể cả khi đường như vậy tồn tại thì cũng không chắc tìm ra. Không sửa planner trong phần việc này.

**Giới hạn và việc còn mở.**
- Mô hình cho phép đổi góc lái tức thời. Tốc độ đánh lái (90°/s, giả định) và việc phải dừng để đánh lái CHƯA XÉT. Mọi kích thước xe là giả định của `configs/vehicle_default.json`, chưa phải số đo MN300.
- Đường chứng chỉ đúng cho xe mặc định. Với `bench --config` hay phép thử độ nhạy, nhãn không tự đúng theo.
- Có nghiệm khác với dùng được. Sửa ngày 24/09/2026 (vòng sửa sau rà soát; bản trước ghi sai là hai ca "chỉ có đường với từ khoảng 100 lần đổi chiều trở lên"). Các đường planner tìm được hoặc dựng giải tích cho hai ca này có 79–279 lần đổi chiều:
  - `parallel_122`: RRT 104 / 136 / 150 lần, trong đó chỉ đường 104 lần được lưu và kiểm độc lập; dựng giải tích 121 lần với tham số mặc định, 79 lần khi lái đủ δ_max và hở thiết kế 1 mm;
  - `parallel_115`: chỉ có đường dựng giải tích, 279 lần với tham số mặc định, 145 lần khi lái đủ δ_max và hở 1 mm.

  Đó là số của từng đường, không phải cận dưới: đã có đường chứng 5 lần (122) / 13 lần (115), và số lần đổi chiều tối thiểu CHƯA BIẾT. Nhịp dưới 2 cm nhiều ở đường RRT 104 lần (47/105 nhịp) và ở đường ngắn của 115 (7/14 nhịp, dài 0,95–1,7 cm; đường ngắn của 122 thì không có nhịp nào dưới 2 cm); các đường dựng giải tích gần như không có (122: 0/122; 115: 1/280). Với đường 104 lần, tái bám trên máy bàn (24/09/2026, lấy mẫu lại 2 cm, bộ bám mặc định, [rollout_parallel_122_20260924.json](evidence/hard_cases/rollout_parallel_122_20260924.json)): xe mô phỏng chỉ đi 2,24 m so với 3,97 m của đường, dừng cách đích 3,4 cm / +0,4° (lấy mẫu 1 cm: 3,9 cm / +2,9°), vẫn trong dung sai; nghĩa là bộ bám không tái hiện các nhịp siêu ngắn. Số này là mô phỏng, CHƯA THỬ trên xe. ĐỀ XUẤT – CHỜ CHỐT: thêm tiêu chí "thực dụng" riêng cho ĐƯỜNG planner trả về (ví dụ trần số lần đổi chiều và độ dài nhịp tối thiểu theo ESC/servo thật), tách khỏi nhãn tồn tại của ca. Lưu ý: ngay cả đường 13 lần của 115 vẫn có nhịp 0,95–1,7 cm, nên có thể không qua tiêu chí đó.
- `tests/test_planner_hard_cases.py::test_ca_vo_nghiem_khong_bao_thanh_cong_gia` vẫn khẳng định nhãn cũ, nên 2 tham số của nó hỏng sau khi đổi nhãn (chạy lại 24/09/2026: 2 failed). Tệp đó không thuộc phần việc này và cần chủ tệp cập nhật: bỏ khẳng định `infeasible`, và chỉ đòi rằng nếu planner báo OK thì đường phải qua kiểm độc lập. Đối chứng âm có chứng minh có thể dùng ô bị đậy kín bằng tường, vì khi đó vùng đích tách rời vùng xuất phát. *(Đã sửa 25/09/2026 đúng theo cách đó: test đổi tên `test_ca_rat_chat_khong_bao_thanh_cong_gia`; `tests/test_planner_hard_cases.py` + `tests/test_planning.py`: 17 đạt, máy bàn, `.venv`. Đối chứng âm đã có sẵn: `tests/test_planning.py::test_walled_off_goal_reports_no_path` — một bức tường chia đôi sa bàn nên đích tách rời xuất phát; test chỉ đòi planner không báo thành công (NO_PATH hoặc TIMEOUT), chưa đòi NO_PATH.)*

Chạy lại (trong thư mục `autopark`):

```
.venv\Scripts\python.exe -X utf8 -m pytest tests/test_hard_cases_labels.py
.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.bench --time-limit 40 --cases parallel_122,parallel_115,zigzag_corridor
```

Ghi chú 24/09/2026 (vòng sửa sau rà soát): sinh lại đường chứng từ planner. Trước đây việc đổi quỹ đạo planner ra dãy cung chỉ nằm trong script nháp. Nay nó nằm trong `autopark/evaluation/hard_cases.py` (`trajectory_to_arcs`, `main`), và test `test_doi_quy_dao_ra_day_cung_tai_tich_phan_dung` chốt rằng dãy cung tái tích phân khớp mọi điểm mẫu trong 1 µm (kiểm đột biến trên bản sao: bỏ hệ số (Δθ/2)/sin(Δθ/2), bỏ dấu theo chiều chạy, hay bỏ bước gộp cung đều làm hỏng test). Test `test_lenh_sinh_duong_chung_ghi_tep_ma_test_chap_nhan` chạy lệnh với planner giả: đường hợp lệ được ghi và qua bộ kiểm của test, đường lệch đích hay ca không có đường thì không ghi, `--merge` giữ ca cũ. Mỗi lệnh một dòng:

```
.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.hard_cases --witness-out runs\witness_moi.json --time-limit 30
.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.hard_cases --witness-out runs\witness_rrt7.json --cases parallel_122 --rung ngau-nhien --seed 7 --time-limit 60 --merge
.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.hard_cases --witness-out runs\witness_zigzag.json --cases zigzag_corridor --rung gop-ky --time-limit 30
```

- `--rung` nhận `portfolio` (mặc định, như `plan_parking`, có bám mô phỏng) hoặc tên ASCII của một nấc: `gop-nhanh`, `gop-ky`, `ngau-nhien`, `luoi-min` (chạy riêng bộ lập đường của nấc, không bám mô phỏng). `--seed` chỉ đổi hạt giống của nấc 'ngẫu nhiên'.
- Lệnh in trạng thái, thời gian và nhật ký từng nấc, kiểm lại dãy cung bằng `collision_oracle` với cùng ngưỡng như test, và chỉ ghi đường đạt. Ca không ra đường thì không được ghi; nếu ca đó không còn đường chứng nào khác thì nhãn phải về `unknown`. Mã thoát 1 khi có ca không ghi được.
- Planner có hạn giờ theo đồng hồ thật, nên chạy lại dưới tải khác có thể ra đường khác (vẫn hợp lệ) hoặc TIMEOUT. Test chỉ đọc hai tệp trong `docs/evidence/hard_cases/`, không đọc tệp mới sinh.
- Chạy thử tối 24/09/2026 trên máy bàn, dưới tải, ghi ở [chay_lai_lenh_moi_20260924.json](evidence/hard_cases/chay_lai_lenh_moi_20260924.json): lệnh thứ ba ra đúng đường zigzag đã lưu; lệnh thứ hai ra đường 146 lần (lượt đầu 150); lệnh thứ nhất ra 12/16 ca. Các hàng còn lại của `reproduce_runs_20260924.json` (từng hạt giống, portfolio 8/20/40 s) sinh bằng script nháp và CHƯA CHẠY LẠI bằng lệnh mới.
- Đường chứng ngắn của 122/115 không sinh bằng lệnh này. Script dựng chúng là script nháp, không có trong kho mã; cách dựng được ghi trong trường `cach_dung` của tệp JSON.
