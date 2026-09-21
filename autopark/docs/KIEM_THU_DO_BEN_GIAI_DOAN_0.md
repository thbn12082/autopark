# Kiểm thử mở rộng giai đoạn 0

Ngày 20/09/2026. Phạm vi: **phần mềm mô phỏng**. Kết luận sau sửa: bộ pytest **220/220 đạt**; chiến dịch **2.880 trường hợp không ghi nhận vi phạm các bất biến đã kiểm tra**. Đây không phải chứng minh mọi tình huống đều an toàn hoặc mọi bài đỗ đều giải được.

## 1. Lỗi đã tái hiện và sửa

Test hồi quy mới ban đầu cho **25 ca thất bại / 3 ca đạt**. Nhiều ca tham số hóa cùng kiểm tra một nhóm lỗi, không diễn giải thành 25 lỗi độc lập. [Báo cáo trước sửa](evidence/robustness_regressions_before.xml). Snapshot code trước sửa và bản diff nằm trong `review_artifacts/phase0_robustness/`.

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

### Chiến dịch theo seed

[Tóm tắt bằng máy](../runs/robustness_final_2026-09-20/summary.json), [từng trường hợp](../runs/robustness_final_2026-09-20/cases.jsonl), [danh sách vi phạm](../runs/robustness_final_2026-09-20/failures.json).

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

[Báo cáo HTML đầy đủ](evidence/coverage_html/index.html), [JSON toàn bộ](evidence/coverage_robustness.json), [phạm vi cốt lõi](evidence/coverage_core.json).

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
