# HUẤN LUYỆN AI NHẬN THỨC — BASELINE WOODSCAPE FREE / BLOCKED

> **Ghi công bắt buộc theo giấy phép dữ liệu:** nghiên cứu nhận thức trong dự án này được thực hiện với **Valeo WoodScape Dataset** (<https://woodscape.valeo.com>, [repo](https://github.com/valeoai/WoodScape)). Điều khoản Valeo yêu cầu hiển thị rõ ghi công này trong mọi tài liệu công bố có nhắc tới nghiên cứu dùng bộ dữ liệu.

**Ngày thực hiện:** 21/09/2026 (phần I) và 22/09/2026 (phần II — đánh giá mở rộng, từ mục 8)
**Máy:** Intel Core i9-14900, NVIDIA RTX 4000 Ada 20 GB (driver 596.72), Windows 11, RAM 64 GB
**Mã nguồn:** [autopark/autopark/perception](autopark/autopark/perception/) · **Hồ sơ lượt chạy:** [autopark/runs/ai_woodscape_rtx4000_v1](autopark/runs/ai_woodscape_rtx4000_v1/)
**Mức bằng chứng:** AI trên ảnh lưu sẵn của bộ dữ liệu công khai. Chưa có ảnh sa bàn/MN300, chưa nối vào planner hay phần cứng.

## 1. Kết quả tóm tắt

Đã huấn luyện xong một baseline phân đoạn hai lớp (**0 FREE_CANDIDATE / 1 OBSTACLE_OR_BLOCKED**, 255 = IGNORE) bằng L-RASPP + MobileNetV3-Large, 30 epoch, 15 phút trên GPU.

| Tập (1.235 ảnh mỗi tập) | mIoU | IoU FREE | IoU BLOCKED | Recall vật cản | Precision vật cản | **Vật cản bị đoán thành FREE** |
|---|---:|---:|---:|---:|---:|---:|
| Validation (dùng để chọn mô hình) | 0,9700 | 0,9741 | 0,9659 | 0,9830 | 0,9824 | 1,70% |
| **Test giữ riêng (đánh giá đúng một lần)** | **0,9692** | 0,9735 | 0,9650 | 0,9825 | 0,9818 | **1,75%** |

Trên test, trong các pixel mô hình gọi là FREE có 1,32% thực ra là vật cản; 1,37% pixel FREE bị gọi nhầm thành vật cản. Pixel accuracy 98,47% — không dùng làm chỉ số chính vì lớp mất cân bằng và 55% pixel là IGNORE.

**Cách đọc các con số này — quan trọng:**

- Đây là hiệu năng **trong phân phối** trên split nội bộ. mIoU đã đạt 0,95 ngay sau epoch 1. Việc chia tập dùng heuristic timestamp + ảnh gần trùng (1.261 nhóm, nhóm lớn nhất 4.108 ảnh), **không có recording ID được xác nhận**, nên không loại trừ val/test cùng tuyến phố với train. Không diễn giải thành khả năng tổng quát hóa.
- Không phải split test chính thức của tác giả WoodScape, nên không so sánh được với số công bố.
- Ảnh WoodScape là camera fisheye trên ô tô thật ngoài phố. Kết quả **không nói gì** về ảnh camera USB 130° trên sa bàn của MN300.
- Pixel FREE là *ứng viên* trên ảnh, chưa chứng minh xe đi qua được.

## 2. Đã làm những gì, theo thứ tự

### 2.1. Dựng lại môi trường

`D:\ap` là bản copy nguyên thư mục dự án từ máy cũ, nên `.venv` và `.venv-train` đều hỏng (`pyvenv.cfg` trỏ về `C:\Users\ginno\...`). Máy chỉ có Python 3.14.

1. Cài **Python 3.12.10** bằng Python install manager (`py install 3.12`) — đúng bản của máy nguồn.
2. Đổi tên venv hỏng thành `.venv-train.hong-tu-may-cu` (không xóa), tạo `.venv-train` mới.
3. Cài đúng phiên bản dự án đã ghim: `torch==2.11.0+cu128`, `torchvision==0.26.0+cu128`, `numpy==2.5.2`, `opencv-python==5.0.0.93`, `pillow==12.3.0`, `pytest==9.1.1`; `pip check` sạch.
4. Kiểm tra CUDA thật: phép nhân ma trận trên GPU hữu hạn, nhận đúng RTX 4000 Ada 19,99 GB, compute capability 8.9, cuDNN 9.19.

Sai khác so với máy nguồn: **pip 25.0.1 → 26.2.1**. Lý do: file torch 2,75 GB bị timeout khi tải lần đầu; pip mới có `--resume-retries` để tải tiếp, lần hai thành công.

### 2.2. Xác minh dữ liệu (không dựng lại cache)

Cache gốc 512×384 (`images.npy` 4,86 GB, `masks.npy` 1,62 GB) đã được copy sang cùng dự án, nhưng thiếu `TRANSFER_READY.json` mà quy trình bàn giao yêu cầu. Thay vì dựng lại, đã viết [verify_cache.py](autopark/autopark/perception/verify_cache.py) để kiểm tra bản copy, chạy 21,5 giây, tất cả đạt:

- Manifest của cache **trùng khớp** manifest đóng băng trên cả 8.234 bản ghi (ID, SHA ảnh/annotation, pixel counts, split, group); mapping SHA-256 khớp file cấu hình.
- Split **5.764 / 1.235 / 1.235**, không giao nhau, phủ đủ, không nhóm nào nằm ở hai tập, cả ba tập có đủ bốn camera.
- Đếm lại pixel từng ảnh từ `masks.npy`: khớp manifest; mask chỉ chứa {0, 1, 255}.
- SHA-256 của toàn bộ 8.234 ảnh gốc và 8.234 annotation: khớp.
- Dựng lại 256 ảnh (64 mỗi camera) từ dữ liệu gốc bằng đúng hàm của `prepare.py`: **giống cache tới từng bit** cả ảnh lẫn mask.

Manifest đóng băng đã được copy vào [datasets/frozen_splits](autopark/datasets/frozen_splits/woodscape_binary_v1/) (trước đó chỉ nằm trong gói bàn giao). Phân bố lớp tập train: FREE 27,4% / BLOCKED 18,0% / IGNORE 54,6% số pixel; trong phần hợp lệ FREE 60% – BLOCKED 40%, nên dùng cross-entropy không trọng số.

### 2.3. Viết pipeline huấn luyện

Trước đó chỉ có mã chuẩn bị dữ liệu. Các module mới trong `autopark/perception/`:

| Module | Vai trò |
|---|---|
| `dataset.py` | Mở cache bằng memory-map chỉ đọc, từ chối cache chưa xác minh, kiểm tra split/nhóm; thứ tự batch là hàm của (seed, epoch) |
| `augment.py` | Augment trên GPU: lật ngang, zoom 0,75–1,35 + dịch, đổi sáng/tương phản/bão hòa. Ảnh và mask dùng **chung một lưới lấy mẫu**, mask lấy mẫu nearest; vùng ngoài ảnh gốc thành **255, không bao giờ thành FREE** |
| `model.py` | L-RASPP MobileNetV3-Large, trọng số pretrained chính thức của Torchvision (COCO); thay **cả hai** đầu phân lớp (`low_classifier`, `high_classifier`) về 2 lớp |
| `metrics.py` | Loss bỏ qua 255, batch toàn IGNORE cho loss 0 hữu hạn (không NaN); ma trận nhầm lẫn theo từng ảnh; chỉ số không xác định trả `None`, không phải 0 |
| `checkpoint.py` | Ghi file nguyên tử (ghi tạm rồi `os.replace`); checkpoint nạp được bằng `weights_only=True` |
| `train.py` | CLI `--config --out --resume --set`; AMP fp16 + GradScaler, clip gradient, AdamW hai nhóm LR, warmup + poly; `latest.pt` mỗi 200 update và cuối epoch, `best.pt` theo val mIoU; dừng bằng file `STOP`/Ctrl+C; `status.json` phân biệt running / stopped / failed / completed; `run_manifest.json` + `source.zip` có SHA-256 |
| `benchmark.py`, `evaluate.py`, `predict.py` | Đo throughput/VRAM trên batch thật; đánh giá theo camera + hình minh họa; suy luận ảnh gốc |

Thiết kế đáng chú ý: toàn bộ ngẫu nhiên (thứ tự batch, augment) suy ra từ **(seed, epoch, step)**, nên resume giữa epoch lặp lại đúng dữ liệu mà không phụ thuộc trạng thái RNG đã lưu. Trainer không bao giờ đọc tập test; `evaluate.py` chỉ chấp nhận test khi có cờ `--final-test` và ghi mỗi lần vào `test_evaluations.jsonl`.

### 2.4. Test

[29 test](autopark/tests/) (`test_perception_data.py`, `test_perception_training.py`) **đạt 29/29** trong `.venv-train`: mapping nhãn, z-order polygon, letterbox, split thật không giao nhau và phát hiện rò rỉ khi bị sửa, augment đồng bộ ảnh–mask, loss/metrics với IGNORE và các ca không có lớp/toàn IGNORE, thay đủ hai đầu phân lớp, checkpoint nguyên tử, **dừng giữa epoch rồi resume cho trọng số trùng khít từng bit với lượt chạy liền** (CPU), CLI và các lớp chặn cấu hình. Trong môi trường mô phỏng không có torch, các test này tự bỏ qua.

### 2.5. Benchmark GPU — và một lỗi của chính pipeline

Lần benchmark đầu cho kết quả bất thường: **~50 ảnh/s ở mọi batch size** (8: 54,0 · 16: 49,9 · 32: 46,7) trong khi suy luận đạt 725 ảnh/s. Đo tách pha (forward / backward / optimizer) với bốn biến thể cho thấy nguyên nhân:

| Batch 16 | ảnh/s | forward | backward |
|---|---:|---:|---:|
| fp16 AMP + `channels_last` | 51,5 | 116 ms | 190 ms |
| **fp16 AMP + NCHW** | **282** | 14,7 ms | 38 ms |
| fp32 + `channels_last` | 40,7 | 149 ms | 240 ms |
| fp32 + NCHW | 161 | 31 ms | 64,5 ms |

`channels_last` được thêm vào bản đầu của trainer như một giả định tăng tốc **chưa đo**; trên tổ hợp torch 2.11 + cuDNN 9.19 + Windows này nó làm chế độ train chậm ~5,5 lần. Đã bỏ khỏi toàn pipeline (memory format chỉ đổi cách chọn kernel, không đổi phép toán). Chưa xác định toán tử nào rơi vào đường chậm. Bằng chứng giữ nguyên: [benchmark_initial_channels_last.json](autopark/runs/ai_woodscape_rtx4000_v1/benchmark_initial_channels_last.json), [diagnosis_channels_last.json](autopark/runs/ai_woodscape_rtx4000_v1/diagnosis_channels_last.json).

Đo lại trên batch thật có augment, AMP, 512×384, 15 bước warm-up + 60 bước đo ([benchmark.json](autopark/runs/ai_woodscape_rtx4000_v1/benchmark.json)):

| Batch | Train ảnh/s | s/batch | Đỉnh VRAM cấp phát / giữ chỗ | Ước lượng s/epoch |
|---:|---:|---:|---:|---:|
| 8 | 200 | 0,040 | 0,99 / 1,24 GB | 30,5 |
| **16** | **247** | 0,065 | 1,91 / 2,38 GB | **25,0** |
| 32 | 226 | 0,141 | 3,76 / 4,65 GB | 27,2 |

Không OOM. Chọn **batch 16**: throughput đo được cao nhất, dùng 2,4/20 GB trên GPU còn chạy desktop. Nạp dữ liệu + augment chiếm ~12% thời gian bước. `batch_size` trong [cấu hình](autopark/configs/train_woodscape_rtx4000_baseline.json) chỉ được đổi từ `null` sang 16 sau phép đo này.

### 2.6. Kiểm tra trước lượt dài

Chi tiết trong [preflight_checks.json](autopark/runs/ai_woodscape_rtx4000_v1/preflight_checks.json). **Không số nào ở mục này là độ chính xác của mô hình.**

- **Overfit 32 ảnh** (tắt augment, đánh giá trên chính 32 ảnh đó): loss 0,638 → 0,022, mIoU 0,76 → 0,973 sau 80 update; không có loss vô hạn. Kết luận: loss, gradient, loader, AMP hoạt động trên dữ liệu thật.
- **Smoke + STOP + resume trên GPU** (640 ảnh train): file `STOP` dừng đúng giữa epoch (update 22/40), `latest.pt` được lưu, `--resume` tiếp tục đúng từ update 22 và kết thúc ở 120 update = 3 × 40. *Chưa kiểm chứng:* mã thoát 3 của tiến trình bị dừng không bắt được do hạn chế của `Start-Process`; chỉ xác nhận qua `status.json`.
- **Suy luận ảnh gốc** (4 ảnh train, mỗi camera một ảnh): ảnh đầu 1,5 s (khởi động CUDA), sau đó 10–14 ms/ảnh gồm cả tiền/hậu xử lý. Xem overlay bằng mắt: không tráo kênh màu, không lệch khung.

### 2.7. Lượt huấn luyện chính

Cấu hình: 30 epoch, seed 20260920, batch 16, AdamW (backbone 1e-4, head 1e-3, weight decay 1e-4), warmup 300 update rồi poly 0,9, clip 10, AMP fp16, early-stopping patience 8, chọn theo validation mIoU. Cấu hình đầy đủ: [config_resolved.json](autopark/runs/ai_woodscape_rtx4000_v1/config_resolved.json).

- **10.800 update, 901 giây** (~28 s/epoch, ~239 ảnh/s); đỉnh VRAM 1,92 GB cấp phát / 2,76 GB giữ chỗ.
- 1 update bị AMP bỏ qua, 0 loss vô hạn, 0 batch toàn IGNORE; `stderr` rỗng. Chi phí khởi động ~40 s do cuDNN dò kernel.
- Validation mIoU: 0,9498 (epoch 1) → 0,9670 (10) → 0,9693 (20) → **0,9700 (30)**. Train loss cuối 0,0305, val loss 0,0409. Early stopping không kích hoạt; **epoch tốt nhất là epoch cuối**, nhưng từ epoch ~12 mức tăng chỉ ở chữ số thập phân thứ tư và LR đã giảm về 0 theo lịch.
- Trainer không đọc tập test (`test_split_read: false` trong manifest).

### 2.8. Đánh giá

Lần chạy `evaluate.py` đầu tiên **hỏng trên val** do lỗi của chính mã đánh giá (truyền list thay vì tensor); tập test chưa bị đụng tới nhờ lớp chặn. Đã sửa, thêm test hồi quy, chạy lại val rồi mới chạy test **một lần** ([test_evaluations.jsonl](autopark/runs/ai_woodscape_rtx4000_v1/test_evaluations.jsonl) có đúng một dòng). Sau khi xem test không chỉnh gì thêm ở mô hình.

Theo camera trên test:

| Camera | Ảnh | mIoU | IoU BLOCKED | Vật cản → FREE |
|---|---:|---:|---:|---:|
| FV (trước) | 406 | 0,9757 | 0,9768 | 1,21% |
| RV (sau) | 342 | 0,9706 | 0,9684 | 1,76% |
| MVL (hông trái) | 229 | 0,9593 | 0,9444 | 2,52% |
| MVR (hông phải) | 258 | 0,9590 | 0,9460 | 2,52% |

Lỗi theo từng ảnh trên test: trung vị 1,27%, p90 2,46%, p99 6,56%, **tệ nhất 35,06%**. Trung bình đẹp che một đuôi dài. Mỗi thư mục [eval_val](autopark/runs/ai_woodscape_rtx4000_v1/eval_val/) / [eval_test](autopark/runs/ai_woodscape_rtx4000_v1/eval_test/) có `metrics.json`, `per_image.csv` và 36 hình (tốt / trung bình / xấu nhất × 4 camera). Hình vẽ **dự đoán thô** của mô hình trên toàn ảnh, không dùng nhãn gốc để che lỗi.

## 3. Lỗi và giới hạn đã quan sát

1. **Ngược nắng / lóa ống kính — lỗi thật, loại nguy hiểm.** Ảnh [07447_FV](autopark/runs/ai_woodscape_rtx4000_v1/eval_test/FV_worst_2_07447_FV.png): mô hình gọi cả dải bó vỉa và bồn cây là FREE (18,7% pixel vật cản của ảnh).
2. **Vùng IGNORE cho đầu ra vô nghĩa.** Mô hình chỉ có hai lớp: nắp capô xe mình thường bị tô FREE, bầu trời bị tô BLOCKED. Ai dùng đầu ra cho planner **bắt buộc** có mặt nạ ROI che xe mình/bầu trời/viền fisheye. IGNORE không phải lớp "vật lạ" mô hình học được.
3. **Nhãn gốc không nhất quán ở vài ảnh.** Ảnh tệ nhất [00105_RV](autopark/runs/ai_woodscape_rtx4000_v1/eval_test/RV_worst_1_00105_RV.png) (lỗi 35%, 46,9% vật cản → FREE) là 1 trong 2 ảnh RV (trên 1.986) **không có polygon `ego_vehicle`**, nên thân xe và viền ảnh bị gán thành vật cản; phần cảnh đường trong ảnh được đoán tốt. Chưa rà soát có hệ thống các bất thường nhãn khác.
4. **Camera hông kém hơn** trước/sau khoảng 1,6 điểm mIoU và gấp đôi tỷ lệ vật cản → FREE.
5. **Rò rỉ bối cảnh chưa loại trừ** (mục 1); chưa đánh giá trên ACDC (điều kiện khó), RoadAnomaly21/RoadObstacle21 (vật lạ) dù dữ liệu đã có sẵn.
6. Chỉ một seed, một lượt chạy: chưa có khoảng dao động giữa các lần huấn luyện. Huấn luyện có seed nhưng **không tái lập từng bit** trên GPU (kernel AMP tự dò của cuDNN).
7. Chưa đo độ trễ suy luận đầu-cuối cho bốn luồng camera đồng thời; con số 10–14 ms là một ảnh, một tiến trình.

## 4. Cách chạy lại

Từ thư mục `autopark`, dùng `.venv-train` (lệnh đầy đủ trong [README](autopark/README.md#huấn-luyện-nhận-thức-woodscape-free--blocked)):

```powershell
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.verify_cache
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.train --config configs/train_woodscape_rtx4000_baseline.json --out runs/<ten_moi>
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.train --out runs/<ten> --resume runs/<ten>/latest.pt
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.predict --checkpoint runs/ai_woodscape_rtx4000_v1/best.pt --input <anh> --out <thu_muc>
```

Dừng có kiểm soát: tạo file rỗng `STOP` trong thư mục run. Nếu `status.json` ghi `running` nhưng `updated_utc` cũ và tiến trình không còn, lượt chạy đã bị tắt ngang — resume từ `latest.pt`.

## 5. Sản phẩm

| File trong `runs/ai_woodscape_rtx4000_v1/` | Nội dung |
|---|---|
| `best.pt` (SHA-256 `0459c3f4…0ccc`), `latest.pt` | Checkpoint epoch 30; gồm model, optimizer, scheduler, scaler, cấu hình, hash split/mapping |
| `run_manifest.json`, `config_resolved.json`, `source.zip` | Môi trường, phiên bản, driver, hash trọng số pretrained, hash dữ liệu, mã nguồn đã dùng |
| `epochs.jsonl`, `train_steps.jsonl`, `train.log`, `status.json`, `training_summary.json` | Nhật ký và trạng thái |
| `benchmark*.json`, `diagnosis_channels_last.json`, `preflight_checks.json` | Số đo và các bước kiểm tra trước khi chạy |
| `eval_val/`, `eval_test/`, `test_evaluations.jsonl` | Chỉ số, bảng theo ảnh, hình minh họa, sổ ghi lần đánh giá test |

Thư mục `runs/` và `datasets/prepared/` nằm trong `.gitignore`: **checkpoint không được git theo dõi**, cần sao lưu riêng nếu muốn giữ. Thư mục `runs/ai_woodscape_rtx4000_v1_checks/` chỉ chứa các lượt kiểm tra thử.

## 6. Chưa làm

- Môi trường mô phỏng `.venv` vẫn hỏng trên máy này; **220 test giai đoạn 0 chưa được chạy lại ở đây**. Mã mô phỏng (planner/controller/UI) không bị sửa.
- Repo git vẫn chưa có commit nào; chưa commit mã mới.
- Dọn dẹp cùng ngày: 11 file ZIP gốc trong `datasets/raw` (31 GB, đã đối chiếu CRC32 khớp 100% với bản giải nén) và hai venv hỏng từ máy cũ (5,3 GB) được gom vào `D:\ap\_CHO_XOA` chờ xóa; xem `DOC_TRUOC_KHI_XOA.md` trong đó. Môi trường mô phỏng cần dựng lại bằng `autopark/cai_dat.cmd`.

## 7. Việc nối tiếp đề xuất

1. Đánh giá `best.pt` trên ACDC và RoadObstacle21 với mapping/split riêng để đo đúng điểm yếu đã thấy (lóa, điều kiện khó, vật lạ).
2. Tạo mặt nạ ROI xe mình/bầu trời theo từng camera trước khi đưa đầu ra vào bất kỳ costmap nào; giữ vùng ngoài ROI là `UNKNOWN`.
3. Thử loss có trọng số hoặc ngưỡng quyết định thiên về BLOCKED để giảm tỷ lệ vật cản → FREE, chấp nhận tăng báo động giả; chọn trên val, không trên test.
4. Khi có camera mẫu (giai đoạn 1): thu ảnh sa bàn, gán nhãn một tập nhỏ và đo lại — đó mới là phép thử có ý nghĩa cho dự án.


---

# PHẦN II — ĐÁNH GIÁ MỞ RỘNG (22/09/2026)

Cùng checkpoint `best.pt` của phần I (SHA-256 `0459c3f4…0ccc`), cùng máy. Mục 7 phần I đề xuất bốn việc; ba việc đầu làm ở đây, việc thứ tư (ảnh sa bàn) vẫn chờ camera. Mã: `autopark/perception/evaluate_external.py`, `evaluate.py --sweep/--threshold`, `engine.decide`. Hồ sơ: các thư mục `eval_*` trong `autopark/runs/ai_woodscape_rtx4000_v1/` và ba thư mục run thêm.

## 8. Ra khỏi vùng quen thuộc: ACDC và RoadObstacle21

Cả hai bộ đều là camera thường (pinhole) 16:9, khác nước, khác xe; ảnh 1920×1080 đi qua đúng đường triển khai của `predict.py` (letterbox về 512×384 → mạng → trả về kích thước gốc) và được chấm ở **độ phân giải nhãn gốc**. ACDC: nhãn Cityscapes 34 lớp → FREE (road, parking) / BLOCKED (nhà, tường, rào, cột, biển, cây, người, xe…) / IGNORE (sidewalk, terrain, ground, static, dynamic, sky, ego, unlabeled, và mọi pixel ACDC đánh dấu *invalid*) theo [acdc_cityscapes_to_binary_v1.json](autopark/configs/acdc_cityscapes_to_binary_v1.json); sidewalk/terrain để IGNORE vì WoodScape không có lớp tương ứng — mô hình chưa từng được dạy chúng là gì. Mô hình **không** được huấn luyện hay chọn theo bất kỳ ảnh nào của hai bộ này.

| Tập | Ảnh | mIoU | IoU BLOCKED | Recall vật cản | **Vật cản → FREE** | FREE → vật cản |
|---|---:|---:|---:|---:|---:|---:|
| WoodScape test (phần I) | 1.235 | 0,969 | 0,965 | 98,3 % | 1,75 % | 1,37 % |
| ACDC val_ref — cùng cảnh, trời quang | 203 | 0,966 | 0,977 | 98,4 % | 1,59 % | 1,49 % |
| ACDC val — sương / đêm / mưa / tuyết | 406 | **0,908** | 0,942 | 95,6 % | **4,42 %** | 3,47 % |
| — fog | 100 | 0,950 | 0,973 | 97,9 % | 2,11 % | 1,69 % |
| — night | 106 | 0,899 | 0,900 | 91,6 % | **8,38 %** | 1,98 % |
| — rain | 100 | 0,886 | 0,939 | 95,2 % | 4,83 % | 4,16 % |
| — snow | 100 | 0,880 | 0,942 | 96,3 % | 3,75 % | **7,60 %** |
| ACDC train / train_ref (chưa từng dùng, 1.600 / 800 ảnh) | | 0,913 / 0,961 | | | 4,31 % / 1,56 % | 3,77 % / 2,33 % |
| RoadObstacle21 validation (vật lạ nhỏ trên đường) | 30 | 0,520 | **0,088** | **68,3 %** | **31,7 %** | 4,57 % |

Đọc kết quả:

- **Đổi nước, đổi ống kính, đổi xe gần như không mất gì** khi trời quang (0,966 trên ACDC val_ref ≈ 0,969 trên WoodScape). Điều làm mô hình yếu là *điều kiện*, không phải miền ảnh.
- **Ban đêm là điểm yếu nguy hiểm nhất**: 8,4 % pixel vật cản bị gọi là FREE; ảnh tệ nhất ([night worst](autopark/runs/ai_woodscape_rtx4000_v1/eval_acdc_val/night_worst_1_night_GOPR0356_GOPR0356_frame_000391_rgb_anon.png)) sai 49 % vật cản: tường hầm và lan can tối màu bị coi là mặt đường. **Tuyết** thì ngược lại — nhiều báo động giả (7,6 %): mặt đường phủ tuyết bị coi là vật cản, lỗi này chỉ làm xe dừng.
- **Vỉa hè bị coi là FREE.** Biến thể chấm với sidewalk/terrain = BLOCKED kéo ACDC val xuống mIoU 0,768 và vật cản → FREE lên 14,5 %. Mô hình học "mặt phẳng lát" = FREE, không học "đường xe chạy"; với sa bàn phẳng điều này không gây hại, với đường thật thì có.
- **Vật lạ nhỏ hầu như vô hình.** RoadObstacle21 có vật cỡ trung vị 2.240 pixel (0,1 % ảnh); 11/30 ảnh mô hình không thấy gì, 12/30 thấy ≥ một nửa vật. AP pixel 0,12 (các phương pháp chuyên vật lạ trên bảng xếp hạng đạt 0,7–0,9). Một phần do độ phân giải 512×288 hữu dụng sau letterbox, phần lớn do mô hình chỉ biết hai lớp và chưa từng thấy các vật đó. Đây là số đo đúng cho cảnh báo "không cam kết phát hiện mọi vật bất ngờ" của kế hoạch.

- **Con số gộp che giấu lớp nguy hiểm.** Trên ACDC, pixel BLOCKED gồm 33 % cây cối, 29 % nhà/tường/rào và chỉ 5,4 % xe, 0,3 % người. Tách theo lớp gốc (`per_source_class` trong metrics.json), tỉ lệ *bị gọi là FREE* trong thời tiết xấu là: **xe 12,4 %, người 6,4 %, xe hai bánh 19 %** — so với cây 2,7 %, nhà 4,7 %. Trời quang cùng cảnh: xe 3,5 %, người 3,7 %. Ở ngưỡng 0,15 (mục 10): xe 6,3 %, người 2,7 %. Khi báo cáo "vật cản → FREE" cho xe tự đỗ phải dùng các con số theo lớp này, không dùng con số gộp 4,4 %.

Phân biệt hai loại lỗi ở mọi bảng: *vật cản → FREE* (nguy hiểm, có thể đâm) và *FREE → vật cản* (chỉ tốn một lần dừng).

## 9. Độ dao động theo seed

Ba lượt cùng cấu hình, chỉ đổi seed (thứ tự batch, augment, khởi tạo hai đầu phân lớp):

| Seed | Val mIoU tốt nhất (epoch) | Val vật cản → FREE | Test mIoU | Test vật cản → FREE |
|---|---:|---:|---:|---:|
| 20260920 (phần I) | 0,9700 (30) | 1,70 % | 0,9692 | 1,75 % |
| 20260921 | 0,9706 (27) | 1,68 % | 0,9693 | 1,79 % |
| 20260922 | 0,9702 (29) | 1,72 % | 0,9693 | 1,77 % |

Trung bình val 0,9703 ± 0,0003, test 0,9693 ± 0,0001. **Mọi khác biệt dưới 0,001 mIoU giữa các thí nghiệm sau này là nhiễu.** Mỗi checkpoint chấm test đúng một lần, ghi trong `test_evaluations.jsonl` của run tương ứng. Hai lượt thêm chạy song song với việc khác nên chậm hơn (939 s và 1.024 s).

## 10. Ngưỡng quyết định thiên về an toàn

Quét ngưỡng xác suất BLOCKED 0,05 → 0,95 trên **validation** ([threshold_sweep.json](autopark/runs/ai_woodscape_rtx4000_v1/eval_val_sweep/threshold_sweep.json)). Quy tắc chọn được ghi trước khi nhìn test: tối đa F2 của lớp BLOCKED (recall nặng gấp đôi precision) → **ngưỡng 0,15**; quy tắc tối đa mIoU giữ 0,50.

| Ngưỡng | Val mIoU | Recall vật cản | Vật cản → FREE | FREE → vật cản |
|---:|---:|---:|---:|---:|
| 0,50 (argmax) | 0,9700 | 98,30 % | 1,70 % | 1,33 % |
| 0,30 | 0,9671 | 98,94 % | 1,06 % | 2,08 % |
| **0,15** | 0,9595 | 99,37 % | **0,63 %** | 3,10 % |
| 0,05 | 0,9434 | 99,69 % | 0,31 % | 4,82 % |

Chấm lại ở 0,15 (mỗi tập một lần):

| Tập | Vật cản → FREE @0,50 → @0,15 | FREE → vật cản @0,50 → @0,15 | mIoU @0,50 → @0,15 |
|---|---:|---:|---:|
| WoodScape test | 1,75 % → **0,69 %** | 1,37 % → 3,97 % | 0,969 → 0,959 |
| ACDC val (thời tiết xấu) | 4,42 % → **2,28 %** | 3,47 % → 7,70 % | 0,908 → 0,911 |
| — night | 8,38 % → 5,41 % | 1,98 % → 5,24 % | |
| — snow | 3,75 % → 1,47 % | 7,60 % → 15,23 % | |
| RoadObstacle21 | 31,7 % → **18,2 %** (ảnh thấy ≥ ½ vật: 12 → 19/30) | 4,57 % → 7,79 % | |

Đổi ngưỡng không tốn thêm tính toán và giảm lỗi nguy hiểm 2–2,5 lần trên mọi bộ, đổi lại gấp 2–3 lần báo động giả (tuyết: 15 % mặt đường bị coi là vật cản). Đây là một tham số vận hành, nên chốt theo khoảng hở và chính sách dừng của giai đoạn 9, không phải hằng số của mô hình. `predict.py`, `evaluate.py`, `evaluate_external.py` và `costmap.py` đều nhận `--threshold`.

## 11. Loss có trọng số lớp

Một lượt cùng cấu hình, chỉ đổi `class_weights = train_inverse_frequency` (trọng số tính từ tỉ lệ pixel **của tập train**: FREE 60 % / BLOCKED 40 % → trọng số ≈ 0,83 / 1,26). Run: `autopark/runs/ai_woodscape_rtx4000_v1_weighted/`.

| Mô hình | Ngưỡng | Val mIoU | Recall vật cản | Vật cản → FREE | FREE → vật cản |
|---|---:|---:|---:|---:|---:|
| Baseline | 0,50 | 0,9700 | 98,30 % | 1,70 % | 1,33 % |
| Loss có trọng số | 0,50 | 0,9694 | 98,65 % | 1,35 % | 1,66 % |
| Loss có trọng số | 0,60 | 0,9702 | 98,31 % | 1,69 % | 1,33 % |
| Baseline | 0,40 | 0,9692 | 98,64 % | 1,36 % | 1,66 % |

Trọng số lớp **chỉ dịch điểm làm việc**, không đổi đường cong đánh đổi: loss có trọng số ở ngưỡng 0,60 trùng baseline ở 0,50 tới ba chữ số (recall, báo động giả, mIoU), và baseline ở 0,40 trùng loss có trọng số ở 0,50. Với cùng dữ liệu và mô hình, mọi khác biệt còn lại nằm trong độ dao động theo seed (±0,0003). Kết luận: **không cần train lại để thiên về an toàn — đổi ngưỡng là đủ và rẻ hơn** (không tốn 15 phút GPU, không thêm checkpoint phải quản lý). Không chấm test cho lượt này vì không chọn nó.

## 12. Độ trễ và ONNX

`python -m autopark.perception.export_onnx` xuất `best.pt` sang ONNX (opset 17, exporter TorchScript, 12,9 MB) và đối chiếu với PyTorch trên 16 ảnh val bằng onnxruntime CPU: lệch logit tối đa 7·10⁻⁵, trùng argmax 99,9999 %. Độ trễ một ảnh, đo khi GPU rảnh (p50 của 200 lượt sau warm-up, [export_report.json](autopark/runs/ai_woodscape_rtx4000_v1/export/export_report.json)):

| Đường chạy | Máy này (i9-14900 / RTX 4000 Ada) |
|---|---:|
| onnxruntime CPU fp32, 512×384 | 7,6 ms |
| torch CPU fp32 | 23,6 ms |
| torch CUDA fp32 | 4,4 ms |
| torch CUDA fp16 (autocast) | 5,5 ms — chậm hơn fp32 vì batch 1 bị giới hạn bởi khởi động kernel, không phải tính toán |
| Đầu-cuối từ ảnh 1280×966: letterbox → mạng fp16 → softmax về CPU | 7,8 ms |

Bốn camera ở 30 FPS cần 120 ảnh/s ≈ 8,3 ms/ảnh: trên máy này đủ, kể cả chỉ dùng CPU. **Laptop RTX 3050 Ti của xe chưa đo** — script chạy được không cần dataset (tự sinh ảnh nhiễu khi thiếu cache), chỉ cần chép `best.pt` và chạy cùng lệnh trên đó. Kết quả lúc GPU đang bận huấn luyện (đo lần đầu) cao gấp 2–3 lần, nên mọi số độ trễ phải kèm điều kiện tải của máy.

## 13. Kiểm thử và review độc lập (22/09)

- Bộ test mô phỏng (`.venv`, PySide6/Shapely, không torch): **260 đạt, 4 bỏ qua** (bốn module cần torch) trong 45 s, gồm 220 test giai đoạn 0 (kể cả 10 test ngân sách thời gian planner) và các test mới không cần torch. Bộ test nhận thức (`.venv-train`, torch): **65 đạt**. Hai môi trường cố ý tách nhau: `.venv-train` không có Shapely/PySide6 nên không chạy được test mô phỏng, `.venv` không có torch nên bỏ qua test trainer.
- Một vòng review đối kháng bằng 4 agent theo 4 lăng kính (hình học, ngữ nghĩa nhãn, nguồn dữ liệu, độ phủ test) đưa ra **46 phát hiện**, mỗi phát hiện được 2 agent hoài nghi độc lập cố bác bỏ (92 phán quyết). Các lỗi thật đã sửa trước khi vòng xác minh kết thúc: nón che khuất của costmap quá hẹp khi ô sát camera; `project_labels` không kiểm tra kích thước mask so với calibration; hòa 0,5 nghiêng về FREE; dấu thời gian camera USB lấy sau khi giải mã; mẫu đã cũ ngay lúc đến vẫn được nhận; sắp xếp tên file theo chuỗi; cờ `mirror` không áp cho nhãn; hợp đồng `LidarScan` nhận range âm; ví dụ minh họa chọn từ cửa sổ 400 ảnh; thiếu phân tích theo lớp gốc trên ACDC. Các phát hiện còn lại là yêu cầu thêm test (đã thêm) hoặc bị bác bỏ.

## 14. Kết luận phần II

- Baseline **ổn định** (±0,0003 theo seed) và **chuyển miền tốt khi trời quang**, nhưng **yếu về đêm, yếu với vật lạ nhỏ, và không phân biệt vỉa hè với đường**.
- Ngưỡng 0,15 là đòn bẩy rẻ nhất để giảm lỗi nguy hiểm; giá phải trả là dừng nhiều hơn.
- Các số này vẫn là ảnh đường phố thật; câu hỏi "trên sa bàn thì sao" chỉ trả lời được khi có camera. Việc hạ tầng để nối đầu ra AI vào costmap (ROI, calibration, phép chiếu) ghi ở [GIAI_DOAN_1_CHUAN_BI.md](autopark/docs/GIAI_DOAN_1_CHUAN_BI.md).
