# BÁO CÁO THỰC HIỆN GIAI ĐOẠN 0 — XE MÔ HÌNH TỰ ĐỖ

**Ngày cập nhật:** 20/09/2026  
**Kế hoạch đối chiếu:** [KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md](KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md), mục 4 — Giai đoạn 0.  
**Mã nguồn:** thư mục [autopark](autopark/README.md).  
**Mức bằng chứng:** phần mềm và mô phỏng trên laptop; chưa kiểm chứng phần cứng.  
**Ghi chú 24/09/2026:** nội dung báo cáo giữ nguyên như ngày 20/09. Những chỗ đã lỗi thời được đánh dấu "Cập nhật 24/09/2026" và trỏ tới tài liệu mới; tình trạng chung của dự án xem [README gốc](README.md) và bảng tiến độ ở mục 17.4 của kế hoạch.

## 1. Kết quả tổng quan

**Giai đoạn 0 đã đạt sáu điều kiện chuyển bước trong phạm vi mô phỏng và các kịch bản đã kiểm tra.** Có giao diện đặt đích, lập đường, xem trước, chạy tiến/lùi, kiểm tra toàn thân xe, xử lý dừng, ghi phiên chạy và replay.

Sau đợt kiểm thử mở rộng:

- **220/220 ca pytest đạt** trong lượt kiểm thử đầy đủ.
- **2.880 trường hợp theo seed** được thực hiện; không ghi nhận vi phạm các điều kiện đã đặt trong chiến dịch.
- **40/40 bài planner** của chiến dịch trả đường hợp lệ và thực thi hoàn thành.
- Năm phiên mẫu sau sửa đều có video, log, cấu hình và **replay khớp**.
- Các lỗi biên phát hiện trong quá trình mở rộng kiểm thử đã được sửa và có test hồi quy.

Không diễn giải các kết quả trên thành “mọi bài đỗ đều giải được”, “phần mềm không còn lỗi” hoặc “xe thật đã an toàn”. Phần chuẩn bị AI được ghi riêng ở mục 9; **chưa có lượt huấn luyện hoàn chỉnh hoặc checkpoint mô hình đã huấn luyện** tại thời điểm lập báo cáo này.

*Cập nhật 24/09/2026:* baseline L-RASPP/MobileNetV3 đã được huấn luyện trên WoodScape ngày 21/09/2026 và có checkpoint; kết quả, đánh giá ngoài miền và giới hạn ở [HUAN_LUYEN.md](HUAN_LUYEN.md). Đó là AI trên ảnh của bộ dữ liệu công khai, không phải kết quả của giai đoạn 0.

## 2. Hiện trạng ban đầu và phần đã bổ sung

Khi bắt đầu đối chiếu kế hoạch, code đã có giao diện sa bàn, planner, controller tiến/lùi và kiểm tra hình học; bộ kiểm thử ban đầu có **155 ca chạy đạt**. Các phần còn thiếu được bổ sung, sau đó bộ thử cơ bản đạt 169 ca. Đợt kiểm thử độ bền tiếp theo nâng tổng số lên 220 ca và tìm ra các lỗi ở những tình huống chưa được bộ thử ban đầu bao phủ.

| Hạng mục | Công việc đã làm |
|---|---|
| Cấu trúc dự án và môi trường | Khởi tạo Git cục bộ; bổ sung README; lưu phiên bản thư viện và cấu hình máy. Chưa commit hoặc đẩy repository lên remote. *Cập nhật 24/09/2026: theo `git log`, commit đầu tiên là `bef5695` ngày 21/09/2026; nhánh `main` đã có trên remote `origin`.* |
| Cấu hình xe | Sửa mô tả cũ còn nhắc WPL C24/1:16. Toàn bộ thông số hiện được ghi rõ là giả định mô phỏng, chưa phải số đo MN300 Tank300 1/12. |
| Hợp đồng dữ liệu | Định nghĩa trạng thái xe, đích, frame camera, scan LiDAR, telemetry, costmap, quỹ đạo và sự kiện an toàn; có thông tin nguồn, thời gian và trạng thái hợp lệ. |
| Bản đồ | Có sa bàn, tường, vật cản, ô đỗ và vùng chưa quan sát `unknown`. Vùng unknown bị chặn khi lập đường/kiểm tra va chạm. |
| Giao diện | Đặt/kéo/xoay đích; kiểm tra đích; tìm đường; xem trước; chạy; dừng; lái tay; chèn vật cản giả; ngắt phản hồi giả; lưu phiên. |
| Planner | Sử dụng kiến trúc hiện có dựa trên Hybrid A*/Reeds–Shepp và danh mục các bộ tìm đường; kiểm chứng đường bằng chạy mô phỏng kín vòng trước khi nhận. |
| Hình học | Kiểm tra thân xe gồm phần nhô đầu/đuôi và vùng quét. Bổ sung nới theo độ võng cung để giảm nguy cơ bỏ sót góc thân xe khi quay. |
| Phản hồi giả | Có trễ, nhiễu vị trí/hướng và mất mẫu theo seed; kiểm tra tuổi dữ liệu và giá trị không hợp lệ. |
| Phản ứng với lỗi | Vật cản mới làm mất hiệu lực đường cũ; xe phanh rồi chờ. Sau dừng an toàn, lập lại đường từ vị trí vừa dừng. |
| Log và replay | Lưu cấu hình, bản đồ, quỹ đạo, sự kiện, trạng thái, kết quả, môi trường và snapshot source; có lệnh chạy lại để đối chiếu kết quả. |
| Kiểm thử mở rộng | Thêm test hồi quy và chiến dịch theo seed; dùng bộ kiểm tra va chạm tham chiếu độc lập; đo coverage và lưu báo cáo. |
| Dữ liệu công khai | Lập danh mục 44 bộ/nhánh dataset, kiểm tra ý nghĩa nhãn, tải các gói ưu tiên và các gói đầy đủ được yêu cầu. |

## 3. Đối chiếu sáu điều kiện chuyển bước

| Điều kiện của kế hoạch v3.1 | Trạng thái | Bằng chứng chính |
|---|---|---|
| Kéo/xoay đích được; từ chối đích trong vật cản | **ĐẠT trong mô phỏng** | Test UI, kiểm tra toàn thân tại đích và kết quả `GOAL_INVALID`. |
| Xe chạy tiến/lùi; tuân thủ giới hạn lái | **ĐẠT trong mô phỏng** | Test động học/controller, phiên tiến/lùi và các cấu hình xe biến đổi. |
| Kiểm tra va chạm xét toàn thân xe | **ĐẠT trong phạm vi thử** | Footprint/vùng quét; đối chiếu thêm bằng bộ kiểm tra độc lập. |
| Vật mới làm đường cũ mất hiệu lực; dừng trước thử đường mới | **ĐẠT trong mô phỏng** | Vô hiệu quỹ đạo, chuyển STOPPING, phanh về 0, chờ; cấm lập đường trong lúc phanh. |
| Xem trước không phát lệnh phần cứng | **ĐẠT** | Rollout riêng; chưa có transport điều khiển phần cứng trong luồng này. |
| Có cấu hình và log đủ để chạy lại kịch bản | **ĐẠT với các phiên đã ghi** | Snapshot, seed, sự kiện, source và replay; các phiên mẫu đối chiếu khớp. |

## 4. Luồng vận hành hiện tại

```text
Chỉnh sa bàn / đặt đích
        ↓
Kiểm tra đích → Lập đường → Kiểm chứng quỹ đạo
        ↓
Xem trước riêng → Người dùng bắt đầu → Chạy mô phỏng kín vòng
        ↓
Vật cản mới / dữ liệu cũ hoặc hỏng / hết thời gian chạy
        ↓
Vô hiệu đường → Phanh → Tốc độ về 0
        ↓
Chờ đánh giá lại → Cập nhật xuất phát từ vị trí vừa dừng → Lập đường mới
```

- Vật cản hoặc phản hồi không hợp lệ không làm xe tự tiếp tục chạy lại.
- Hết thời gian chạy dẫn tới phanh rồi kết thúc `FAULT`, thay vì đóng băng xe khi vẫn còn tốc độ.
- `COMPLETED` chỉ dùng khi đạt dung sai; đi hết danh sách điểm chưa tự đồng nghĩa đỗ đúng.
- Khi đóng phiên, đồng hồ mô phỏng ngừng. Đây không phải một phép thử phanh của xe thật.

## 5. Các lỗi đã tìm thấy và sửa

Lượt test hồi quy mới đầu tiên có **25 trường hợp thất bại và 3 trường hợp đạt**. Nhiều trường hợp cùng thuộc một nhóm lỗi; không coi đó là 25 lỗi độc lập. Một test bổ sung sau đó còn tái hiện việc đổi đoạn khi tốc độ chưa về 0.

| Nhóm lỗi | Hành vi sau sửa |
|---|---|
| Phiên đã đóng vẫn nhận lệnh chạy | Chặn chạy tự động/lái tay; không tiến mô phỏng sau close. |
| Hết thời gian khi xe đang chuyển động | Ghi `RUN_TIMEOUT`, vô hiệu đường và phanh về 0 trước trạng thái kết thúc. |
| Hết giờ cắt ngang quá trình dừng | Hoàn tất phanh và giữ đúng kết quả của yêu cầu dừng. |
| Báo STOPPED khi còn tốc độ nhỏ | Thực hiện bước phanh cuối tới 0. |
| Đổi đoạn tiến/lùi khi còn chuyển động | Chờ tốc độ 0 trước khi chuyển đoạn. |
| NaN/Infinity trong lệnh, nhịp thời gian hoặc phản hồi | Từ chối đầu vào hỏng hoặc phát dừng trước khi dữ liệu tới controller. |
| Vật cản/lỗi thứ hai xuất hiện trong lúc phanh | Tiếp nhận cập nhật trong STOPPING, giữ phanh và lưu đủ sự kiện. |
| Xuất phát đã va chạm nhưng chưa giữ cờ collision | Giữ cờ ngay từ khởi tạo; không cho xe thoát ra rồi coi lượt chạy là hợp lệ. |
| Preview báo hoàn thành ngoài dung sai | Phân biệt `path_finished` với `completed`; planner kiểm chứng theo đúng dung sai được đặt. |
| Tốc độ mục tiêu vượt cấu hình nhỏ | Chặn cả hồ sơ quỹ đạo và đầu ra controller, kể cả creep speed. |

Bằng chứng: [test trước sửa](autopark/docs/evidence/robustness_regressions_before.xml), [test sau sửa](autopark/docs/evidence/robustness_pytest.xml), [bản diff](autopark/review_artifacts/phase0_robustness/changes.patch).

## 6. Kết quả kiểm thử và mức độ bao phủ

### 6.1. Bộ pytest

- Lượt đầy đủ: **220 passed**, khoảng **60,23 giây** tại lần đo đã lưu.
- Lượt đo coverage: **210 passed, 10 deselected**. Mười test có ngân sách thời gian tìm đường được chạy trong lượt đầy đủ không gắn tracer; không bị bỏ khỏi kiểm thử bình thường hoặc được nới thời hạn.
- Một ca quay đầu chật từng TIMEOUT khi chạy cùng chiến dịch tải CPU. Chạy riêng ca đó mất khoảng 3,98 giây; lượt đầy đủ chạy tách đạt 220/220. Khả năng tìm đường trong thời hạn vẫn phụ thuộc tải máy.

### 6.2. Chiến dịch theo seed

| Nhóm | Số trường hợp | Nội dung |
|---|---:|---|
| Tư thế/hình học | 2.000 | Nhiều kích thước, góc xoay, vật cản, lề an toàn và vị trí gần biên. |
| Chuyển động/vùng quét | 600 | Đối chiếu bằng 81 tư thế lấy mẫu độc lập trên mỗi cung. |
| Phiên chạy kín vòng và lỗi giả | 240 | Thẳng, lùi, cua, lùi cua, đổi chiều; trễ/nhiễu/mất mẫu; vật trước/hông/chiếm đích; lỗi đồng thời. |
| Lập đường và thực thi | 40 | Bốn nhóm bài đỗ với cấu hình biến đổi; kiểm tra đường, điểm trung gian và lượt chạy thực thi. |
| **Tổng** | **2.880** | **Không ghi nhận vi phạm các điều kiện đã đặt.** |

Phân biệt kết quả của 240 phiên chạy:

- **25 COMPLETED:** hoàn thành trong dung sai.
- **185 STOPPED:** dừng đúng logic; không tính là hoàn thành đỗ.
- **30 FAULT:** cố tình chèn vật quá gần để phanh; không tính là tránh va chạm thành công.

Ngoài ra, **40/40 ca planner** trong chiến dịch trả đường hợp lệ và thực thi hoàn thành. Đã tái hiện riêng ca `runtime:137` theo seed, đối chiếu khớp toàn bộ bản ghi kết quả và sự kiện.

Miền tham số runtime/hình học được thử: kích thước 0,7–1,4 lần cấu hình; góc lái tối đa 22–38°; tốc độ tối đa 0,06–0,30 m/s; gia tốc 0,15–0,45 m/s²; giảm tốc 0,25–0,90 m/s²; tốc độ đổi lái 35–140°/s; bước vật lý 2,5/5/10 ms. Các số này là miền thử giả định, không phải thông số MN300 đã đo.

### 6.3. Coverage

| Phạm vi tại đợt kiểm thử mô phỏng | Dòng lệnh | Nhánh |
|---|---:|---:|
| 10 module cốt lõi được khai báo trong báo cáo | **93,93%** | **84,25%** |
| Toàn package tại thời điểm đo, gồm UI/công cụ/planner thử nghiệm | **52,52%** | **38,11%** |

Không dùng tỷ lệ của 10 module để đại diện toàn repository. Code chuẩn bị AI thêm sau đợt nghiệm thu không nằm trong kết quả 220 test này. Coverage cao không bảo đảm đã thử đủ giá trị đầu vào: tracker từng được chạy qua mọi nhánh nhưng vẫn có lỗi biên được test mới phát hiện.

Liên kết bằng chứng:

- [Báo cáo kiểm thử độ bền chi tiết](autopark/docs/KIEM_THU_DO_BEN_GIAI_DOAN_0.md).
- [JUnit 220 test](autopark/docs/evidence/robustness_pytest.xml).
- [Coverage HTML](autopark/docs/evidence/coverage_html/index.html), [phạm vi cốt lõi](autopark/docs/evidence/coverage_core.json).
- [Tóm tắt chiến dịch](autopark/runs/robustness_final_2026-09-20/summary.json), [từng trường hợp và seed](autopark/runs/robustness_final_2026-09-20/cases.jsonl), [danh sách vi phạm](autopark/runs/robustness_final_2026-09-20/failures.json).

## 7. Video, log và khả năng tái hiện

Năm phiên sau đợt sửa lỗi nằm trong [phase0_after_robustness](autopark/runs/phase0_after_robustness/summary.json):

| Phiên | Kết quả | Thời gian mô phỏng | Sai số vị trí cuối | Replay |
|---|---|---:|---:|---|
| parking | COMPLETED | 20,265 s | 8,92 mm | Khớp |
| reverse | COMPLETED | 12,145 s | 8,52 mm | Khớp |
| noisy | COMPLETED | 12,265 s | 4,78 mm | Khớp |
| obstacle | STOPPED, không va chạm | 1,345 s | Không đánh giá tới đích | Khớp |
| data_loss | STOPPED, không va chạm | 1,490 s | Không đánh giá tới đích | Khớp |

Profile noisy của phiên mẫu: trễ 40 ms, σ vị trí 2 mm, σ yaw 0,2°, mất mẫu 2%, seed 42. Đây là kết quả của các ca cụ thể, không phải chỉ tiêu đã đạt cho mọi bản đồ.

Mỗi phiên lưu `manifest.json`, `config_snapshot/`, `telemetry.csv`, `events.jsonl`, `safety_events.json`, `result.json`, `source.zip`, ảnh cuối và video. Manifest ghi phiên bản thư viện/máy và SHA-256 source. Replay dùng quỹ đạo đã lưu, không bắt planner tìm lại đường theo một ngân sách thời gian mới.

- [Video đỗ](autopark/runs/phase0_after_robustness/parking/simulation.mp4).
- [Video vật cản mới](autopark/runs/phase0_after_robustness/obstacle/simulation.mp4).
- [Video mất dữ liệu](autopark/runs/phase0_after_robustness/data_loss/simulation.mp4).
- [Ảnh UI đang chạy](autopark/docs/evidence/ui_running.png), [ảnh UI đã dừng](autopark/docs/evidence/ui_stopped.png).

## 8. Dataset đã chuẩn bị

Việc tải/xem dữ liệu và kiểm tra nhãn là một đầu việc của giai đoạn 0; các đợt tải đầy đủ tiếp theo phục vụ nhánh AI.

| Dữ liệu | Trạng thái |
|---|---|
| Danh mục dataset | Đã lập danh mục **44 bộ/nhánh**, ghi nguồn, loại nhãn, mức phù hợp và các hạn chế truy cập. Không coi 44 mục là 44 bộ đã tải. |
| AVM-SS | Đã tải đủ **6.763 cặp ảnh–mask**, kiểm tra kích thước, palette và split gốc 4.057 train / 2.706 test. |
| DROW v2 | Đã tải đủ **464.023 scan**, kiểm tra định dạng CSV v2 và các file nhãn không có scan cùng stem. |
| WoodScape | Đã tải đủ **8.234 cặp RGB–semantic**, kèm instance annotations, calibration và metadata cần thiết. |
| ACDC | Đã tải ảnh, nhãn semantic/invalid masks train/validation và nhãn ảnh tham chiếu. |
| RoadAnomaly21 / RoadObstacle21 | Đã tải dữ liệu công khai và mã benchmark; không có nhãn test giữ kín. |

Đợt bổ sung WoodScape/ACDC/benchmark có **8 archive, tổng 32.916.613.522 byte nén (~32,92 GB)**. Đã đối chiếu checksum/CRC và giải nén. Con số này không cộng AVM/DROW đã tải ở đợt trước và không phải dung lượng sau giải nén.

Những phát hiện được giữ trong tài liệu:

- AVM có **7.071 pixel màu vàng ngoài palette README**; giữ ở UNKNOWN/IGNORE thay vì tự gán thành vùng trống.
- Nhãn điểm/vạch/ô đỗ không thay thế mask pixel vật cản.
- Các nhãn `void`, vùng xe mình và vùng chưa quan sát không mặc định là FREE.
- DROW v2 có 452 cột/scan: ID, thời gian và 450 range; không áp nhầm loader v1. Giá trị N/A không phải bằng chứng vùng trống.

Tài liệu: [danh mục](autopark/datasets/DANH_MUC_DATASET.md), [tải và kiểm tra](autopark/datasets/TAI_VA_KIEM_TRA.md), [báo cáo hoàn tất](autopark/datasets/TRANG_THAI_TAI_DAY_DU.md), [manifest đầy đủ](autopark/datasets/full_dataset_inventory.json).

## 9. Phần AI đã bắt đầu chuẩn bị — chưa phải kết quả huấn luyện

Đây là công việc nối tiếp phục vụ giai đoạn 1, được ghi để bàn giao đúng trạng thái:

- Đã tạo môi trường riêng `.venv-train`, cài PyTorch **2.11.0+cu128**, Torchvision **0.26.0+cu128** và các phụ thuộc liên quan. Môi trường mô phỏng `.venv` được giữ riêng.
- Đã viết mã chuyển polygon WoodScape sang nhãn **FREE_CANDIDATE / OBSTACLE_OR_BLOCKED / IGNORE** và chuẩn bị ảnh **512×384** có giữ tỷ lệ bằng letterbox.
- Đã tạo bộ chia nội bộ **5.764 train / 1.235 validation / 1.235 test**, dùng nhóm timestamp và phát hiện ảnh trùng/gần trùng. Cả ba tập đều có bốn hướng camera.
- Tại phép kiểm tra đã thực hiện, không có nhóm trùng đã phát hiện nằm ở nhiều tập. Tuy nhiên metadata không cung cấp recording ID được xác nhận; **chưa loại trừ hoàn toàn rò rỉ cùng bối cảnh**. Đây không phải split test benchmark chính thức của tác giả.
- **Chưa có module trainer hoàn chỉnh, chưa chạy lượt train cơ sở, chưa có checkpoint hoặc kết quả độ chính xác của mô hình đã huấn luyện.** Không coi việc tải dữ liệu/cài PyTorch là huấn luyện xong.

File liên quan: [mapping nhãn](autopark/configs/woodscape_binary_v1.json), [mã xử lý dữ liệu](autopark/autopark/perception/data.py), [mã chuẩn bị cache](autopark/autopark/perception/prepare.py), [audit bộ dữ liệu đã chuẩn bị](autopark/datasets/prepared/woodscape_binary_v1/audit.json).

*Cập nhật 24/09/2026:* gạch đầu dòng cuối ở trên không còn đúng. Trainer đã hoàn thiện và lượt huấn luyện cơ sở chạy ngày 21/09/2026 trên RTX 4000 Ada, có checkpoint `runs/ai_woodscape_rtx4000_v1/best.pt` và kết quả trên tập test giữ riêng (chấm một lần); ngày 22–23/09 có thêm đánh giá ngoài miền, ba seed và các lượt thêm AVM-SS/ACDC. Tất cả ở [HUAN_LUYEN.md](HUAN_LUYEN.md), phần I–III. Nghiên cứu này dùng **Valeo WoodScape Dataset** (<https://woodscape.valeo.com>); giấy phép WoodScape cấm dùng mô hình huấn luyện trên nó để vận hành hoặc hỗ trợ vận hành phương tiện, xem [GIAY_PHEP_DU_LIEU.md](autopark/docs/GIAY_PHEP_DU_LIEU.md).

## 10. Mã nguồn và môi trường bàn giao

| Thành phần | Vị trí |
|---|---|
| README và cách chạy | [autopark/README.md](autopark/README.md) |
| Cấu hình xe giả định | [vehicle_default.json](autopark/configs/vehicle_default.json) |
| Hợp đồng dữ liệu | [domain/types.py](autopark/autopark/domain/types.py), [domain/sensors.py](autopark/autopark/domain/sensors.py) |
| Máy trạng thái phiên | [application/session.py](autopark/autopark/application/session.py) |
| Xe, thế giới, phản hồi giả | [simulation](autopark/autopark/simulation/) |
| Hình học và oracle | [geometry](autopark/autopark/geometry/), [collision_oracle.py](autopark/autopark/evaluation/collision_oracle.py) |
| Planner và controller | [planning](autopark/autopark/planning/), [control/tracker.py](autopark/autopark/control/tracker.py) |
| Log/snapshot/replay | [storage/run_store.py](autopark/autopark/storage/run_store.py), [evaluation/replay.py](autopark/autopark/evaluation/replay.py) |
| Chiến dịch theo seed | [evaluation/robustness.py](autopark/autopark/evaluation/robustness.py) |
| Bộ test | [tests](autopark/tests/) |
| Khóa phiên bản môi trường mô phỏng | [requirements-phase0.lock](autopark/requirements-phase0.lock) |

Máy được ghi nhận: Windows 11, Python 3.12.10, CPU Intel Core i7-12700H, GPU NVIDIA RTX 3050 Ti Laptop **4 GB VRAM**, RAM hệ thống báo 68.409.155.584 byte. Cấu hình/phiên bản package chi tiết của đợt nghiệm thu ở [environment.json](autopark/docs/evidence/environment.json).

Quy ước tính toán: mét, giây, radian; pose tại tâm trục sau; x hướng đầu xe, y sang trái, yaw dương ngược chiều kim đồng hồ. Timestamps giả dùng cùng đồng hồ mô phỏng.

## 11. Cách tự kiểm chứng

### Giao diện

Trong thư mục `autopark`, chạy `chay_app.cmd`:

1. Kéo/xoay đích vào vật cản: phải báo không hợp lệ và từ chối lập đường.
2. Đặt đích hợp lệ, bấm tìm đường, xem trước, kết thúc xem trước rồi bắt đầu đỗ.
3. Khi xe đang chạy, bấm **Vật cản giả**: đường cũ mất hiệu lực, xe phanh và dừng.
4. Bấm **Chọn lại vị trí**, đánh giá lại bản đồ và lập đường từ vị trí vừa dừng.
5. Trong lượt chạy mới, bấm **Mất dữ liệu**: hệ thống phát hiện phản hồi cũ và dừng.
6. Thử profile trễ/nhiễu trong thiết lập mô phỏng; dùng **Lưu phiên…** trước khi reset nếu cần giữ hồ sơ chạy.

### Lệnh PowerShell

Mở PowerShell tại thư mục `xe tự lái`:

```powershell
Set-Location ".\autopark"

# Chạy tuần tự, không chạy cùng lúc với benchmark có giới hạn thời gian.
.\.venv\Scripts\python.exe -X utf8 -m pytest

$robustDir = "runs/robustness_" + (Get-Date -Format "yyyyMMdd_HHmmss")
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.robustness --out $robustDir

$caseDir = "runs/reproduce_" + (Get-Date -Format "yyyyMMdd_HHmmss")
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.robustness --out $caseDir --case runtime:137

$videoDir = "runs/phase0_" + (Get-Date -Format "yyyyMMdd_HHmmss")
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.phase0 --out $videoDir
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.replay "$videoDir/obstacle"
```

Đo coverage riêng:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m coverage run --branch --source=autopark -m pytest -m "not planner_budget"
.\.venv\Scripts\python.exe -X utf8 -m coverage html
```

Đường dẫn đầu ra mới tránh ghi đè bằng chứng cũ. Replay chính xác đòi hỏi cùng code/cấu hình/môi trường; snapshot source và lockfile được giữ để đối chiếu.

## 12. Giới hạn và công việc tiếp theo

### Chưa được chứng minh ở giai đoạn 0

- Độ chính xác và độ trễ của camera/LiDAR thật; hiệu chuẩn bốn camera và BEV trên gá thực.
- Phanh, khoảng dừng, E-stop, nguồn, ESC/servo hoặc watchdog của ESP32.
- Độ chính xác của AI trên ảnh sa bàn/MN300; hiện chưa huấn luyện xong AI.
- Mô phỏng quang học camera, scan ray-casting đầy đủ, trượt lốp, biến dạng cơ khí và động lực học thực.
- Không va chạm trong mọi trường hợp: vật chèn ngay vào thân hoặc quá gần để phanh có thể gây FAULT. Force-stop sau va chạm chỉ là cơ chế của mô phỏng.
- Vô nghiệm hình học chỉ từ TIMEOUT/NO_PATH; va chạm liên tục được chứng minh toán học chỉ từ oracle lấy mẫu.

### Công việc nối tiếp

1. Hoàn thiện trainer, kiểm tra GPU bằng lượt nhỏ, đo tốc độ/bộ nhớ rồi huấn luyện mô hình cơ sở có checkpoint.
2. Đánh giá trên tập giữ riêng; theo dõi đặc biệt vật cản bị nhận thành vùng trống. Xử lý vùng IGNORE/không quan sát riêng, không coi chúng là lớp vật lạ đã học được.
3. Viết nguồn camera/video và nguồn scan phát lại, rồi tiếp nhận camera mẫu/LiDAR khi có thiết bị.
4. Giữ bộ test và replay mô phỏng làm kiểm thử hồi quy khi tích hợp các khối thật.

*Cập nhật 24/09/2026 — tình trạng các việc trên:* (1) xong: baseline có checkpoint ngày 21/09 ([HUAN_LUYEN.md](HUAN_LUYEN.md) phần I), nên câu "hiện chưa huấn luyện xong AI" ở phần giới hạn không còn đúng; độ chính xác trên ảnh sa bàn/MN300 thì vẫn chưa đo. (2) Đã đánh giá trên tập test giữ riêng và ngoài miền, đo riêng tỉ lệ vật cản bị gọi thành FREE (HUAN_LUYEN.md phần I–III). (3) Nguồn phát lại ảnh/video/scan có từ 22/09 ([GIAI_DOAN_1_CHUAN_BI.md](autopark/docs/GIAI_DOAN_1_CHUAN_BI.md)); LiDAR C1 đọc được trên máy bàn ngày 22/09 ([GIAI_DOAN_1_LIDAR.md](autopark/docs/GIAI_DOAN_1_LIDAR.md)); bốn camera USB đo trên máy bàn ngày 23/09 ([GIAI_DOAN_1_CAMERA.md](autopark/docs/GIAI_DOAN_1_CAMERA.md), [GIAI_DOAN_2_BAN_THU.md](autopark/docs/GIAI_DOAN_2_BAN_THU.md)). Các mục "chưa được chứng minh" khác ở trên vẫn đúng: camera chưa hiệu chuẩn, chưa có BEV trên gá thực, sai số khoảng cách LiDAR chưa đo, chưa có phanh/E-stop/ESP32.

**Trạng thái bàn giao:** phần mô phỏng giai đoạn 0 đã có chức năng, kiểm thử và hồ sơ tái hiện; nhánh dữ liệu/AI đã được chuẩn bị và đang chuyển sang công việc giai đoạn 1. Chưa nghiệm thu hệ thống tự đỗ trên xe thật.
