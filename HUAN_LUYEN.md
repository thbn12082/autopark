# HUẤN LUYỆN AI NHẬN THỨC — BASELINE WOODSCAPE FREE / BLOCKED

> **Ghi công bắt buộc theo giấy phép dữ liệu:** nghiên cứu nhận thức trong dự án này được thực hiện với **Valeo WoodScape Dataset** (<https://woodscape.valeo.com>, [repo](https://github.com/valeoai/WoodScape)). Điều khoản Valeo yêu cầu hiển thị rõ ghi công này trong mọi tài liệu công bố có nhắc tới nghiên cứu dùng bộ dữ liệu.

**Ngày thực hiện:** 21/09/2026 (phần I), 22/09/2026 (phần II — đánh giá mở rộng, từ mục 8) và đêm 22 → 23/09/2026 kèm sáng 23/09 (phần III — thêm dữ liệu AVM-SS và ACDC, từ mục 15)
**Máy:** Intel Core i9-14900, NVIDIA RTX 4000 Ada 20 GB (driver 596.72), Windows 11, RAM 64 GB
**Mã nguồn:** [autopark/autopark/perception](autopark/autopark/perception/) · **Hồ sơ lượt chạy:** [autopark/runs/ai_woodscape_rtx4000_v1](autopark/runs/ai_woodscape_rtx4000_v1/) (git-ignored: mọi link tới `autopark/runs/` trong tài liệu này chỉ mở được trên máy có dữ liệu, trên GitHub không có)
**Mức bằng chứng:** AI trên ảnh lưu sẵn của bộ dữ liệu công khai. Chưa có ảnh sa bàn/MN300, chưa nối vào planner hay phần cứng.  
*Cập nhật 24/09/2026:* từ 23/09 checkpoint nền chạy trực tiếp trên bốn camera USB của bàn thử giai đoạn 2 ([GIAI_DOAN_2_BAN_THU.md](autopark/docs/GIAI_DOAN_2_BAN_THU.md)): đo được thời gian suy luận, còn lớp tô chỉ để quan sát. Chưa chấm trên ảnh sa bàn có nhãn, chưa nối vào planner. Từ 24/09 có công cụ gán nhãn ảnh sa bàn và quy trình chấm checkpoint trên cache sa bàn (`evaluate --manifest`, tập chấm tô tay `--no-draft`): [GAN_NHAN_SA_BAN.md](autopark/docs/GAN_NHAN_SA_BAN.md) mục 2, bước 7. Đến 24/09 chưa có ảnh sa bàn nào được gán nhãn.

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

Lần chạy `evaluate.py` đầu tiên **hỏng trên val** do lỗi của chính mã đánh giá (truyền list thay vì tensor); tập test chưa bị đụng tới nhờ lớp chặn. Đã sửa, thêm test hồi quy, chạy lại val rồi mới chạy test **một lần** ([test_evaluations.jsonl](autopark/runs/ai_woodscape_rtx4000_v1/test_evaluations.jsonl) có đúng một dòng tại 21/09; dòng thứ hai là lần chấm ở ngưỡng 0,15 ngày 22/09, phần II mục 10). Sau khi xem test không chỉnh gì thêm ở mô hình.

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
7. Chưa đo độ trễ suy luận đầu-cuối cho bốn luồng camera đồng thời; con số 10–14 ms là một ảnh, một tiến trình. *Cập nhật 24/09/2026: ngày 23/09 bàn thử giai đoạn 2 đã đo suy luận theo lô bốn ảnh 640×480 (fp16) từ bốn camera USB, trên chính máy này, chạy chung với LiDAR ([GIAI_DOAN_2_BAN_THU.md](autopark/docs/GIAI_DOAN_2_BAN_THU.md) mục 3.3). Một lô trung vị 16,4 ms (mạng 11,6 ms), 23,8 bộ/s ở phiên 120 s (u01); 15,6 ms, 23,1 bộ/s ở phiên 10 phút (u04). Kết quả có mặt 34,8 ms (u01) và 65,5 ms (u04) trung vị sau khi khung cũ nhất trong bộ tới máy; hai số khác nhau do pha giữa các camera. Vẫn chưa đo độ trễ từ sự kiện thật tới lúc khung tới máy (cần LED nháy), và chưa đo trên máy nào khác.*

*Cập nhật 24/09/2026:* một phần của ý 5 và ý 6 đã được làm ở phần II ngày 22/09. ACDC và RoadObstacle21 đã chấm ở mục 8 (và ở ngưỡng 0,15 trong mục 10). Ba seed đã chạy ở mục 9: val 0,9703 ± 0,0003, test 0,9693 ± 0,0001. Vẫn còn mở: RoadAnomaly21 chưa chấm (dữ liệu có trong `autopark/datasets/training/road_anomaly`, nhưng `evaluate_external` chỉ nhận `acdc` và `road_obstacle`); rò rỉ bối cảnh trong split WoodScape chưa loại trừ; huấn luyện vẫn không tái lập từng bit.

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

- Môi trường mô phỏng `.venv` vẫn hỏng trên máy này; **220 test giai đoạn 0 chưa được chạy lại ở đây**. Mã mô phỏng (planner/controller/UI) không bị sửa. *Cập nhật 24/09/2026: `.venv` đã được dựng lại ngày 22/09 (ngày tạo `pyvenv.cfg`); một lượt chạy toàn bộ test trên máy này ngày 22/09 cho 284 đạt, 4 bỏ qua (có lẽ trên cây làm việc trước khi hoàn tất commit `6dba1a6`; không còn nhật ký của lượt đó); chạy lại đúng bản `6dba1a6` ngày 24/09 cho 292 đạt, 4 bỏ qua ([GIAI_DOAN_3_CHUAN_BI.md](autopark/docs/GIAI_DOAN_3_CHUAN_BI.md) mục 1). Cả hai lượt đều gồm các test giai đoạn 0.*
- Repo git vẫn chưa có commit nào; chưa commit mã mới. *Cập nhật 24/09/2026: theo `git log`, commit đầu tiên `bef5695` được tạo ngày 21/09/2026 lúc 18:11 và đã chứa tệp này; nhánh `main` đã có trên remote `origin`.*
- Dọn dẹp cùng ngày: 11 file ZIP gốc trong `datasets/raw` (31 GB, đã đối chiếu CRC32 khớp 100% với bản giải nén) và hai venv hỏng từ máy cũ (5,3 GB) được gom vào `D:\ap\_CHO_XOA` chờ xóa; xem `DOC_TRUOC_KHI_XOA.md` trong đó. Môi trường mô phỏng cần dựng lại bằng `autopark/cai_dat.cmd`. *Cập nhật 24/09/2026: thư mục `D:\ap\_CHO_XOA` không còn trong `D:\ap`; `autopark/datasets/raw/` chỉ còn các tệp `.zip.json` ghi SHA-256, nên bản giải nén là bản dữ liệu duy nhất trên máy này.*

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

*Thêm muộn tối 24/09/2026 — RoadAnomaly21 đã chấm; `evaluate.py` chặn chấm trên ảnh đã học (mã chưa commit, máy bàn).*

- **Dữ liệu và cách chấm.** `evaluate_external --dataset road_anomaly` đọc bản giải nén có sẵn trong máy, `autopark/datasets/training/road_anomaly/dataset_AnomalyTrack` (SegmentMeIfYouCan, nhánh AnomalyTrack; không tải thêm gì). Kiểm trên chính các tệp đó ngày 24/09: 10 ảnh `validation*.jpg` 1280×720 có nhãn, giá trị nhãn đúng {0, 1, 255}; 100 ảnh còn lại là tập test, không có nhãn công khai, chỉ được đếm. Nhãn 0 là *mọi thứ không phải vật bất thường* (đường, nhà, cây, trời), nên **không** coi được là FREE. Vì vậy chỉ pixel vật bất thường (1 → BLOCKED) được chấm; 0 và 255 là IGNORE. mIoU, IoU, precision và báo động giả không định nghĩa được (ghi `None`). AP, FPR95, sIoU của SMIYC cần một điểm bất thường theo pixel, mà mô hình chỉ cho P(BLOCKED), nên không tính: **các số dưới đây không so được với bảng xếp hạng SMIYC**. Nhãn có giá trị ngoài {0, 1, 255} thì lệnh dừng.
- **Kết quả**, ba seed lượt nền (`ai_woodscape_rtx4000_v1` SHA-256 `0459c3f4…`, `_seed20260921`, `_seed20260922`), trung bình ± độ lệch chuẩn theo seed. Chạy trên máy bàn khi có agent khác cùng dùng máy; điều đó chỉ ảnh hưởng thời gian, không ảnh hưởng số.

  | Ngưỡng | Recall vật bất thường | **Vật bất thường → FREE** | Ảnh thấy ≥ ½ vật /10 | Pixel nền bị gọi BLOCKED (tham khảo, **không** phải báo động giả) |
  |---:|---:|---:|---:|---:|
  | 0,50 | 89,6 ± 1,2 % (89,3 / 88,6 / 91,0) | **10,4 ± 1,2 %** | 9 · 9 · 9 | 61,8 ± 4,3 % |
  | 0,15 | 94,5 ± 0,4 % (94,8 / 94,1 / 94,6) | **5,5 ± 0,4 %** | 9 · 9 · 9 | 67,2 ± 3,3 % |

  Ở seed nền, gần hết lỗi dồn vào một ảnh. `validation0000` (một con hươu đang băng qua đường, xem bằng mắt ảnh minh họa): 73 % pixel con hươu bị gọi FREE ở ngưỡng 0,50, 50 % ở 0,15. `validation0009` (vật nhỏ nhất, 15.288 pixel) có recall 74 % / 88 %. Tám ảnh còn lại ≥ 88,6 % ở ngưỡng 0,50. Ở 0,15, recall của `validation0000` là 49,997 %, vừa dưới một nửa, nên ảnh này vẫn không được tính vào cột "thấy ≥ ½ vật".
- **Cách đọc.** Vật trong RoadAnomaly21 lớn (trung vị 85.768 pixel, ≈ 9 % ảnh; tổng 1.317.063 pixel trên 10 ảnh), còn vật của RoadObstacle21 nhỏ (trung vị 2.240 pixel), nên recall 89,6 % ở đây không mâu thuẫn với 68,3 % của RO21. Mô hình cũng gọi BLOCKED 62 % pixel nền, tức phần lớn những gì không phải mặt đường. Recall cao vì thế **không** phải bằng chứng mô hình "nhận ra" vật lạ. Với 10 ảnh, độ lệch chuẩn trên chỉ phản ánh dao động theo seed, không phản ánh sai số do mẫu nhỏ. Tỉ lệ recall ở mọi ngưỡng 0,05…0,95 được tính lại từ histogram, lưu ở `anomaly.anomaly_recall_by_threshold` của metrics.json. Giá trị ở 0,15 tính từ lần chạy 0,50 trùng với lần chạy 0,15 riêng (0,94754).
- **Chưa có hồ sơ trong `runs/`.** Các lần chạy trên ghi vào thư mục tạm của phiên làm việc, chưa chép vào `runs/`. Muốn có hồ sơ thì chạy lại (mỗi lệnh một dòng, cmd):

  `.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.evaluate_external --checkpoint runs/ai_woodscape_rtx4000_v1/best.pt --dataset road_anomaly --out runs/ai_woodscape_rtx4000_v1/eval_road_anomaly`

  `.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.evaluate_external --checkpoint runs/ai_woodscape_rtx4000_v1/best.pt --dataset road_anomaly --out runs/ai_woodscape_rtx4000_v1/eval_road_anomaly_thr015 --threshold 0.15`
- **Kiểm hồi quy khi tách mã.** Phần chấm của `evaluate_external` được tách thành hàm `evaluate_items` để test chạy được không cần GPU. Chạy lại RO21 và ACDC val trên checkpoint nền: mọi số trong metrics.json trùng bản 22/09 (`eval_road_obstacle`, `eval_acdc_val`), `per_image.csv` trùng từng byte; chỉ thêm khóa `label_values_seen`.
- **`evaluate.py` chặn chấm trên ảnh đã học** (`--train-overlap refuse`, mặc định). Trước khi chấm, ảnh của split được chấm được so với split train của manifest mà checkpoint đã học: sha256 ảnh, mã ảnh kèm cache gốc, tên bộ ảnh, giờ chụp ≤ 60 s. Trùng, hoặc không kiểm được (thiếu manifest huấn luyện, hoặc manifest khác `manifest_sha256` trong checkpoint), thì lệnh từ chối. `--train-overlap warn` cho chấm tiếp, nhưng in cảnh báo và ghi `train_overlap` vào metrics.json. Thử trên dữ liệu thật tối 24/09:
  - WoodScape val với checkpoint nền: sạch (5.764 ảnh train, 0 trùng). Số đo khớp `eval_val` ngày 21/09 tới 1e-5 tương đối (2 pixel khác trên 47,8 triệu; GPU không tái lập từng bit).
  - `ai_ws_avm` chấm "chéo" trên AVM-SS val (`--manifest avm_ss_binary_v1`, số 0,913 / 8,7 % ở bảng mục 16): không trùng train, nhưng **cả 1.050/1.050 ảnh nằm trong split val mà chính lượt đó dùng để chọn checkpoint**. Con số đó là val của chính mô hình, không phải tập chưa chạm; công cụ in cảnh báo, không chặn.
  - Giới hạn: `evaluate_external` chưa có phép so này. Ví dụ, chấm ACDC `--split train` bằng `ai_ws_avm_acdc` là chấm trên ảnh đã học mà không bị chặn. Phép so cũng không bắt được rò rỉ theo chuỗi GoPro của ACDC (mục 15), vì khác ảnh.
  - *Sửa sau rà soát (tối 24/09/2026, mã chưa commit):* "giờ chụp ≤ 60 s" không còn cố định. Chấm **chính** cache huấn luyện thì chỉ so sha256 ảnh, mã ảnh + cache gốc và nhóm `group`, tức tin phân nhóm mà cache đã ghi và `check_splits` đã kiểm. Bản đầu so lại bộ ảnh và giờ ≤ 60 s, nên từ chối nhầm val/test của cache sa bàn chia với `--session-gap` < 60 s, hay có khung cũ đã duyệt (tái hiện trên dữ liệu giả). Chấm cache **khác** (`--manifest`) vẫn so bốn phép. Khoảng phiên lấy theo thứ tự: của `--disjoint-from` nếu cache chấm đã được export tách rời khỏi đúng manifest huấn luyện đó; rồi `grouping.session_gap_s` của cache huấn luyện; không có thì 60 s. Đã đọc năm manifest trong `datasets/prepared` (WoodScape, ACDC, AVM-SS, hai cache ghép; máy bàn, tối 24/09): không cái nào ghi `session_gap_s`, giờ chụp hay tên bộ ảnh. Đã chạy lại riêng phần so manifest (`train_overlap_report`, không chấm lại mô hình, không cần GPU) bằng mã đã sửa, cho hai lần thử trên. Kết quả không đổi: WoodScape val với checkpoint nền sạch (5.764 ảnh train, 0 trùng; nay so sha256, mã ảnh, nhóm). `ai_ws_avm` trên AVM-SS val: 0 ảnh trùng train, 1.050/1.050 trùng split chọn mô hình (theo mã ảnh + cache gốc).

## 9. Độ dao động theo seed

Ba lượt cùng cấu hình, chỉ đổi seed (thứ tự batch, augment, khởi tạo hai đầu phân lớp):

| Seed | Val mIoU tốt nhất (epoch) | Val vật cản → FREE | Test mIoU | Test vật cản → FREE |
|---|---:|---:|---:|---:|
| 20260920 (phần I) | 0,9700 (30) | 1,70 % | 0,9692 | 1,75 % |
| 20260921 | 0,9706 (27) | 1,68 % | 0,9693 | 1,79 % |
| 20260922 | 0,9702 (29) | 1,72 % | 0,9693 | 1,77 % |

Trung bình val 0,9703 ± 0,0003, test 0,9693 ± 0,0001. **Mọi khác biệt dưới 0,001 mIoU giữa các thí nghiệm sau này là nhiễu.** Mỗi checkpoint chấm test đúng một lần ở mỗi ngưỡng, ghi trong `test_evaluations.jsonl` của run tương ứng: hai seed thêm chỉ chấm ở 0,50; checkpoint nền có thêm một lần ở ngưỡng 0,15 ngày 22/09 (mục 10), nên file của nó có hai dòng. *(Sửa 24/09/2026: câu cũ ghi "đúng một lần" không tính lần chấm ở 0,15.)* Hai lượt thêm chạy song song với việc khác nên chậm hơn (939 s và 1.024 s).

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

Bốn camera ở 30 FPS cần 120 ảnh/s ≈ 8,3 ms/ảnh: trên máy này đủ, kể cả chỉ dùng CPU. **Chưa đo trên laptop RTX 3050 Ti** (máy mang đi nộp đồ án, người dùng xác nhận 24/09/2026) — script chạy được không cần dataset (tự sinh ảnh nhiễu khi thiếu cache), chỉ cần chép `best.pt` và chạy cùng lệnh trên đó. Kết quả lúc GPU đang bận huấn luyện (đo lần đầu) cao gấp 2–3 lần, nên mọi số độ trễ phải kèm điều kiện tải của máy.

*Cập nhật 24/09/2026:* laptop i7-12700H + RTX 3050 Ti nói trên là máy đã ghi biên bản giai đoạn 0 ([BAO_CAO_GIAI_DOAN_0.md](BAO_CAO_GIAI_DOAN_0.md) mục 10) và là máy mang đi nộp đồ án (người dùng xác nhận 24/09/2026); máy bàn là máy phát triển chính. Độ trễ vẫn chỉ đo trên máy bàn i9-14900. Mốc 30 FPS là mode camera công bố, dùng làm cận trên: camera thật đo được thường ≈ 23,85 khung/s ở phơi sáng tự động và 29,3 khung/s ở phơi sáng thủ công (một camera, 720p; [GIAI_DOAN_1_CAMERA.md](autopark/docs/GIAI_DOAN_1_CAMERA.md) mục 4.1); camera cổng 1 và cổng 3 đã có phiên chạy ≈ 29 khung/s cả ở phơi sáng tự động, đều trên máy bàn: cổng 3 ở t01, t02 (23/09, 720p, 28,9 / 29,0 khung/s, số gồm cả khung bị cắt) và cả bảy phiên s01–s07 (23/09, 29,0–29,3 khung/s, đọc từ `runs/rig_bench/20260923/*.rig.json`, git-ignore; loạt chạy trước khi có bộ dò khung hỏng); cổng 1 ở t05 (23/09, 640×480 cùng LiDAR + AI, 29,3, số này cũng đếm cả khung có thể bị cắt) và m02, o01 (24/09, 720p chỉ camera, 29,3 khung tốt/s); nguyên nhân chưa rõ; [GIAI_DOAN_2_BAN_THU.md](autopark/docs/GIAI_DOAN_2_BAN_THU.md) mục 5 (t01, t02, t05), mục 10.1 và 10.3 (m02, o01); thêm tối 24/09/2026, cùng tối bổ sung cổng 3 và sửa trích dẫn (bản trước ghi "riêng camera cổng 1" và chỉ trích mục 10.3). Mọi số đo đều dưới 30 khung/s, nên 120 ảnh/s vẫn là cận trên hợp lệ.

## 13. Kiểm thử và review độc lập (22/09)

- Bộ test mô phỏng (`.venv`, PySide6/Shapely, không torch): **260 đạt, 4 bỏ qua** (bốn module cần torch) trong 45 s, gồm 220 test giai đoạn 0 (kể cả 10 test ngân sách thời gian planner) và các test mới không cần torch. Bộ test nhận thức (`.venv-train`, torch): **65 đạt**. Hai môi trường cố ý tách nhau: `.venv-train` không có Shapely/PySide6 nên không chạy được test mô phỏng, `.venv` không có torch nên bỏ qua test trainer.
- Một vòng review đối kháng bằng 4 agent theo 4 lăng kính (hình học, ngữ nghĩa nhãn, nguồn dữ liệu, độ phủ test) đưa ra **46 phát hiện**, mỗi phát hiện được 2 agent hoài nghi độc lập cố bác bỏ (92 phán quyết). Các lỗi thật đã sửa trước khi vòng xác minh kết thúc: nón che khuất của costmap quá hẹp khi ô sát camera; `project_labels` không kiểm tra kích thước mask so với calibration; hòa 0,5 nghiêng về FREE; dấu thời gian camera USB lấy sau khi giải mã; mẫu đã cũ ngay lúc đến vẫn được nhận; sắp xếp tên file theo chuỗi; cờ `mirror` không áp cho nhãn; hợp đồng `LidarScan` nhận range âm; ví dụ minh họa chọn từ cửa sổ 400 ảnh; thiếu phân tích theo lớp gốc trên ACDC. Các phát hiện còn lại là yêu cầu thêm test (đã thêm) hoặc bị bác bỏ.

## 14. Kết luận phần II

- Baseline **ổn định** (±0,0003 theo seed) và **chuyển miền tốt khi trời quang**, nhưng **yếu về đêm, yếu với vật lạ nhỏ, và không phân biệt vỉa hè với đường**.
- Ngưỡng 0,15 là đòn bẩy rẻ nhất để giảm lỗi nguy hiểm; giá phải trả là dừng nhiều hơn.
- Các số này vẫn là ảnh đường phố thật; câu hỏi "trên sa bàn thì sao" chỉ trả lời được khi có camera. Việc hạ tầng để nối đầu ra AI vào costmap (ROI, calibration, phép chiếu) ghi ở [GIAI_DOAN_1_CHUAN_BI.md](autopark/docs/GIAI_DOAN_1_CHUAN_BI.md).

# PHẦN III — THÊM DỮ LIỆU: AVM-SS VÀ ACDC (đêm 22 → 23/09/2026, bổ sung sáng 23/09)

Câu hỏi: **thêm hai bộ dữ liệu mới có làm mô hình tốt hơn không, và tốt hơn theo thước nào?** Chưa có ảnh sa bàn, nên "tốt hơn" chỉ đo được bằng ba loại tập: val của chính miền đã học, val của miền kia (chấm chéo), và hai tập chưa lượt nào chạm tới — ACDC val (thời tiết xấu, camera thường) và RoadObstacle21 (vật lạ nhỏ). Mã mới: `autopark/perception/prepare_extra.py` (dựng cache AVM-SS, ACDC, trộn), `evaluate.py --manifest` (chấm chéo miền), `engine.evaluate_split` có `per_subset`. Hồ sơ: các thư mục `autopark/runs/ai_avm_only`, `ai_ws_avm`, `ai_ws_avm_seed20260923`, `ai_ws_avm_seed20260924`, `ai_ws_avm_acdc`, `ai_ws_avm_weighted`, `ai_ws_avm_weighted_seed20260923`, `ai_ws_avm_weighted_seed20260924` (git-ignored), log hàng đợi trong scratchpad của phiên.

Giấy phép của hai bộ mới ghi ở [GIAY_PHEP_DU_LIEU.md](autopark/docs/GIAY_PHEP_DU_LIEU.md), kèm quyết định ngày 22/09 của người làm khóa luận về phạm vi sử dụng.

## 15. Dữ liệu và cách chia

| Cache | Nguồn | train / val / test (ảnh) | Pixel FREE : BLOCKED (train, bỏ IGNORE) | Cách chia và điều cần biết |
|---|---|---:|---:|---|
| `woodscape_binary_v1` | WoodScape fisheye (phần I) | 5.764 / 1.235 / 1.235 | 60 : 40 | như phần I |
| `avm_ss_binary_v1` | AVM-SS, ảnh ghép nhìn từ trên xuống trong bãi đỗ | 4.713 / 1.050 / 1.000 | 91 : 9 | **Bỏ split của tác giả** vì chia ngẫu nhiên theo từng khung hình: 62,8 % ảnh train của tác giả có khung liền kề nằm trong test (chiều ngược lại 82,7 %). Chia lại theo khối 50 id liên tiếp (70/15/15), đo rò rỉ còn lại bằng phash (22/09; mẫu 400 ảnh mỗi tập, khoảng cách nhỏ nhất tới ảnh train; manifest `grouping.leakage_min_phash_distance_to_train`): val 3/400 trùng hash, 9/400 cách ≤ 2 bit; test 8/400 trùng, 19/400 ≤ 2 bit. Chỉ đo, không lọc bỏ, nên số AVM val có thể hơi lạc quan; ảnh AVM phần lớn là mặt nền đồng màu (91 % pixel có nhãn là FREE) nên trùng hash chưa chắc là cùng cảnh. |
| `acdc_binary_v1` | ACDC train / val, camera thường, sương–đêm–mưa–tuyết | 1.600 / 406 / 0 | 33 : 67 | Giữ split chính thức để so được với phần II. **Split chính thức để cùng một chuỗi GoPro nằm cả train lẫn val** (ví dụ fog/GOPR0476), nên mọi lượt có ACDC train trong dữ liệu học **không được** chấm trên ACDC val như một phép đo tổng quát hóa. |
| `ws_avm_v1` | WoodScape + AVM-SS | 10.477 / 2.285 / 2.235 | 75 : 25 | ghép hai cache, nhóm giữ tiền tố tên cache |
| `ws_avm_acdc_v1` | + ACDC train | 12.077 / 2.691 / 2.235 | 71 : 29 | val của ACDC = ACDC val chính thức → rò rỉ như trên |

Cấu hình huấn luyện **giữ nguyên phần I** (L-RASPP + MobileNetV3-Large, 384×512, batch 16, AMP, 30 epoch, cùng augment), chỉ đổi manifest; trọng số lớp chỉ bật ở lượt ghi rõ. Thời gian một lượt trên RTX 4000 Ada: AVM riêng 13 phút, trộn hai bộ 26–27 phút (22–28 phút khi có trọng số lớp), trộn ba bộ 30 phút. Tổng cộng tám lượt huấn luyện mới (sáu trong đêm, hai seed trọng số thêm sáng 23/09) và 40 lần chấm ngoài miền, chưa kể chấm chéo.

## 16. Bảng kết quả — mọi số của nhóm ba seed là trung bình ± độ lệch chuẩn

"Vật cản → FREE" là tỉ lệ pixel vật cản bị gọi thành đường trống (lỗi có thể đâm). Ngưỡng 0,50 trừ khi ghi khác.

| Lượt (số seed) | Val riêng mIoU | WoodScape val mIoU / vật cản→FREE | AVM val mIoU / vật cản→FREE | **ACDC val mIoU** | **ACDC vật cản→FREE** | ACDC đêm vật cản→FREE | **RO21 recall vật lạ** | RO21 ảnh thấy ≥ ½ vật /30 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| WoodScape nền (3) | 0,970 | 0,970 / 1,7 % | 0,473 / 35,3 % ¹ | **0,914 ± 0,005** | **4,1 ± 0,4 %** | 8,4 ± 0,4 % | **67,0 ± 2,3 %** | 12 · 12 · 13 |
| AVM-SS riêng (1) | 0,910 | 0,487 / 49,8 % | 0,910 / 9,0 % | 0,209 | 82,7 % | 78,6 % | 34,1 % | 8 |
| WoodScape + AVM (3) | 0,958 | 0,970 / 1,8 % ¹ | 0,913 / 8,7 % ¹ | **0,781 ± 0,021** | **13,5 ± 2,8 %** | 13,5 ± 7,2 % | **63,0 ± 1,6 %** | 11 · 12 · 11 |
| WoodScape + AVM + ACDC train (1) | 0,966 | 0,970 / 1,8 % | 0,915 / 8,3 % | 0,983 ² | 0,5 % ² | 1,0 % ² | 48,8 % | 11 |
| WoodScape + AVM, trọng số lớp (3) | 0,955 | 0,965 / 1,1 % | 0,912 / 5,6 % | 0,790 ± 0,105 | **11,2 ± 9,2 %** | 9,3 ± 7,8 % | 69,6 ± 3,1 % | 13 · 14 · 14 |
| WoodScape nền, trọng số lớp (1, phần II §11) | 0,969 | — | — | 0,905 | 4,4 % | 8,4 % | 67,5 % | 12 |

¹ chấm chéo chỉ làm cho seed đầu của nhóm (nhóm trọng số chấm chéo cả ba seed). ² **rò rỉ**: lượt này học ACDC train, chung chuỗi GoPro với ACDC val (mục 15) — con số chỉ chứng minh mô hình học được ACDC, không phải tổng quát hóa; **không được trích dẫn** như kết quả ngoài miền.

Giá trị từng seed để ai cũng kiểm lại được: WoodScape nền — ACDC vật cản→FREE 4,42 / 3,60 / 4,17 %, RO21 recall 68,3 / 68,4 / 64,4 %. WoodScape + AVM — ACDC 10,95 / 13,01 / 16,46 %, ACDC đêm 5,9 / 20,3 / 14,3 %, RO21 62,2 / 64,8 / 62,0 %. Val riêng của ba seed trộn: 0,9584 / 0,9585 / 0,9585. WoodScape + AVM có trọng số lớp — ACDC 7,94 / 21,63 / 4,17 %, ACDC đêm 4,3 / 18,3 / 5,5 %, RO21 67,7 / 67,9 / 73,2 %; val riêng 0,9556 / 0,9556 / 0,9541.

### 16.1. Tách theo lớp gốc trên ACDC val (% pixel của lớp bị gọi FREE, ngưỡng 0,50, trung bình ± độ lệch chuẩn 3 seed)

| Lớp gốc | WoodScape nền | WoodScape + AVM | WS + AVM trọng số (3 seed) |
|---|---:|---:|---:|
| car | 10,8 ± 0,9 | 9,5 ± 2,8 | 5,4 ± 0,8 |
| person | 6,7 ± 0,1 | 6,8 ± 1,7 | 2,6 ± 1,6 |
| bicycle | 25,0 ± 2,5 | 12,5 ± 2,6 | 5,5 ± 4,7 |
| motorcycle | 3,9 ± 0,4 | 2,7 ± 1,4 | 0,5 ± 0,5 |
| truck | 16,8 ± 5,9 | 32,9 ± 4,0 | 21,1 ± 12,0 |
| bus | 13,2 ± 4,1 | 35,3 ± 2,9 | 32,5 ± 8,1 |
| wall | 26,0 ± 3,8 | 40,2 ± 3,2 | 28,1 ± 8,9 |
| fence | 17,2 ± 1,7 | 25,4 ± 3,7 | 21,2 ± 5,4 |
| pole | 6,6 ± 0,9 | 15,7 ± 4,7 | 11,8 ± 9,6 |
| building | 1,6 ± 0,2 | 11,5 ± 1,6 | 9,2 ± 8,3 |
| vegetation | 2,2 ± 0,4 | 11,9 ± 3,7 | 11,0 ± 11,2 |

## 17. Đọc kết quả

- **AVM-SS riêng vô dụng ngoài AVM.** Trên ACDC 82,7 % vật cản bị gọi là đường trống; trên WoodScape mIoU 0,49. Ảnh nhìn từ trên xuống không có tường, nhà, cây, xe tải — mô hình chưa từng thấy chúng.
- **Trộn WoodScape + AVM không mất gì trong hai miền đã học**: WoodScape 0,970 (bằng nền), AVM 0,913 (bằng lượt học riêng AVM 0,910). Nếu ảnh trên xe giống AVM (nhìn từ trên), đây là lượt xử lý được cả hai loại ảnh mà không rò rỉ tập chấm.
- **Nhưng trộn làm hỏng miền thứ ba, và đó là kết quả thật, không phải nhiễu.** ACDC vật cản→FREE tăng 4,1 → 13,5 % (chênh 9,4 điểm, độ lệch chuẩn lớn nhất 2,8; cả ba seed trộn đều tệ hơn cả ba seed nền). mIoU giảm 0,914 → 0,781. Tách theo lớp cho thấy thiệt hại **tập trung ở những thứ AVM không có**: tường 26 → 40 %, xe buýt 13 → 35 %, xe tải 17 → 33 %, nhà 1,6 → 11,5 %, cây 2,2 → 11,9 %; trong khi ô tô, người, xe máy không xấu đi và xe đạp còn tốt hơn (25 → 12,5 %). Giải thích hợp lý nhất, chưa kiểm chứng riêng: 91 % pixel có nhãn của AVM là FREE và phần lớn là mặt phẳng lát lớn, nên mô hình học "mảng lớn, đều" = đường trống rồi áp lên mặt tường, thành xe buýt trong ảnh camera thường.
- **Hai kết luận ghi ở bản nháp lúc rạng sáng là sai và đã rút lại.** (1) "Trộn AVM cải thiện ban đêm 8,4 → 5,9 %" — chỉ đúng với một seed; hai seed sau cho 20,3 % và 14,3 %, trung bình 13,5 ± 7,2 %: **xấu hơn và rất bất ổn**. (2) "Thêm dữ liệu làm giảm recall vật lạ RO21 67 → 63 %" — chênh 4 điểm khi độ lệch chuẩn theo seed là 2,3 và 1,6 điểm, chỉ 30 ảnh: **chưa đủ để kết luận theo chiều nào**. Bài học giữ lại: không báo cáo bất kỳ khác biệt nào giữa hai lượt huấn luyện khi chưa có ít nhất ba seed mỗi bên.
- **Lượt trộn ba bộ (có ACDC train)** đạt 0,983 trên ACDC val nhưng đó là rò rỉ (mục 15). Số duy nhất còn dùng được của lượt này là RO21 recall 48,8 %, thấp nhất trong các lượt có WoodScape trong dữ liệu học (chỉ AVM-SS riêng thấp hơn, 34,1 %) — chỉ một seed nên chỉ là dấu hiệu.

### 17.1. Hai cách gỡ đã thử

| Cách | ACDC vật cản→FREE | ACDC FREE→vật cản (báo động giả) | ACDC đêm vật cản→FREE | RO21 recall |
|---|---:|---:|---:|---:|
| WoodScape nền @0,50 (3 seed) | 4,1 ± 0,4 % | 3,4 ± 0,6 % | 8,4 ± 0,4 % | 67,0 ± 2,3 % |
| WoodScape nền @0,15 (3 seed) | 2,2 ± 0,2 % | 7,6 ± 1,2 % | 5,4 ± 0,5 % | 79,9 ± 3,2 % |
| WS + AVM @0,50 (3 seed) | 13,5 ± 2,8 % | 5,6 ± 2,0 % | 13,5 ± 7,2 % | 63,0 ± 1,6 % |
| WS + AVM @0,15 (3 seed) | 7,1 ± 1,5 % | 12,9 ± 2,6 % | 8,4 ± 4,9 % | 72,8 ± 1,1 % |
| WS + AVM trọng số @0,50 (3 seed) | 11,2 ± 9,2 % | 9,7 ± 1,6 % | 9,3 ± 7,8 % | 69,6 ± 3,1 % |
| WS + AVM trọng số @0,15 (3 seed) | 6,5 ± 6,1 % | 19,2 ± 1,2 % | 5,4 ± 5,4 % | 77,0 ± 2,8 % |

- **Hạ ngưỡng xuống 0,15** kéo lỗi nguy hiểm của lượt trộn xuống một nửa (13,5 → 7,1 %) nhưng lượt nền ở cùng ngưỡng còn 2,2 %: khoảng cách vẫn hơn ba lần, và báo động giả của lượt trộn lên 12,9 %. Đổi ngưỡng không bù được dữ liệu sai miền.
- **Trọng số lớp nghịch tần suất** trên cache trộn là 0,66 / 2,04 (mạnh hơn nhiều so với 0,83 / 1,26 trên WoodScape ở phần II §11, vì AVM kéo tỉ lệ FREE lên 75 %). Seed đầu (20260922) trông như sửa đúng chỗ đau: vật cản→FREE trên ACDC 7,9 %, ban đêm 4,3 %. **Hai seed thêm sáng 23/09 bác bỏ điều đó**: cùng cấu hình, seed 20260923 cho 21,6 % và seed 20260924 cho 4,2 %; trung bình 11,2 ± 9,2 %, độ lệch chuẩn gấp 3,3 lần nhóm không trọng số, và trung bình đó không khác 13,5 ± 2,8 % của nhóm không trọng số một cách có ý nghĩa (chênh 2,2 điểm, nhỏ hơn độ lệch chuẩn). So từng cặp cùng seed với lượt trộn không trọng số (cùng seed nên cùng thứ tự batch và cùng phép augment theo mã `train.py`; riêng cặp 20260924 lượt trọng số dừng sớm ở epoch 25 với `best.pt` epoch 17, còn lượt trộn chạy đủ 30 epoch): −3,0 / +8,6 / −12,3 điểm — trọng số không có chiều nhất quán trên ACDC. Tách theo lớp: ô tô, người, xe máy, xe đạp giảm lỗi ở cả ba cặp và thấp hơn mọi seed nền (ô tô 5,4 ± 0,8 %, người 2,6 ± 1,6 %); tường cũng giảm ở cả ba cặp (−12,8 / −3,9 / −19,9 điểm, 40,2 → 28,1 %) nhưng dao động 22–38 % và chỉ hai trong ba seed về mức nền; còn xe buýt, xe tải, nhà, cây thì đổi chiều tùy seed (nhà 6,6 / 18,4 / 2,4 %, cây 7,0 / 23,8 / 2,4 %). Hai điều nhất quán ở cả ba cặp, đều so với lượt trộn cùng seed: recall vật lạ RO21 tăng (+5,5 / +3,2 / +11,2 điểm; nhóm 69,6 ± 3,1 % so với 63,0 ± 1,6 % của lượt trộn, nhưng chỉ hơn nền 67,0 ± 2,3 % có 2,6 điểm, chưa phân biệt được) và báo động giả trên ACDC tăng 3,5–4,7 điểm (9,7 ± 1,6 % so với 5,6 ± 2,0 % của lượt trộn; so với nền 3,4 ± 0,6 % là cao hơn 6,3 điểm). Điều thứ ba mới so được với một seed: bỏ sót trên chính WoodScape / AVM của cả ba seed trọng số (1,01 / 1,06 / 1,12 % và 5,88 / 5,66 / 5,33 %) đều thấp hơn seed đầu nhóm không trọng số (1,8 % / 8,7 %; hai seed trộn sau chưa chấm chéo), đổi lấy mIoU thấp hơn một chút (0,965 / 0,912). Kết luận: trọng số lớp **không phải cách gỡ** thiệt hại do AVM trên ảnh đường phố; nó dịch mô hình về phía thận trọng với người và xe, với giá là báo động giả, và không làm mô hình ổn định hơn. Run: `runs/ai_ws_avm_weighted`, `_seed20260923`, `_seed20260924`.

## 18. Kết luận phần III và checkpoint tham chiếu

- **Không lượt nào trong đêm vượt lượt nền WoodScape trên cả hai tập chưa chạm.** `runs/ai_woodscape_rtx4000_v1/best.pt` vẫn là checkpoint tham chiếu của dự án; ngưỡng vận hành 0,15 vẫn là đòn bẩy rẻ nhất (phần II §10).
- **Thêm dữ liệu công khai khác miền không phải đường đi tự động tốt.** AVM giúp đúng một việc: nhìn được ảnh từ trên xuống. Nếu camera trên xe thực sự cho góc nhìn đó, dùng `ai_ws_avm` và chấp nhận giá đã đo ở tường, xe lớn, nhà; nếu không, đừng dùng.
- Câu trả lời cuối cùng vẫn nằm ở ảnh sa bàn tự thu, đúng như kết luận phần II §14: không bộ nào trong số này là camera của xe mô hình. Khi có 100–200 ảnh sa bàn có nhãn, phép chấm đầu tiên là chạy ba checkpoint (nền, trộn, trộn có trọng số — mỗi loại đủ ba seed) ở cả hai ngưỡng 0,50 và 0,15 trên chúng. *Cập nhật 24/09/2026:* quy trình chụp, gán nhãn, xuất cache và chấm ảnh sa bàn ở [GAN_NHAN_SA_BAN.md](autopark/docs/GAN_NHAN_SA_BAN.md). Nhãn nháp ở đó lấy từ chính lượt nền (`ai_woodscape_rtx4000_v1`), nên nhãn sửa từ nháp lạc quan về phía lượt nền (thiên lệch neo, mục 4 của tài liệu đó); phép so ba checkpoint ở trên phải dùng tập tô tay từ đầu (`--no-draft`, dự án riêng, `export --disjoint-from`, bước 7). Quan sát đầu tiên trên ảnh camera thật, một bộ bốn ảnh ngày 23/09 (`runs/rig_snapshots/20260923_165138_661`, camera đặt trên bàn nhìn xuống thảm hoa văn, chưa có nhãn): lượt nền gọi BLOCKED 11 / 31 / 39 / 60 % pixel của cổng 1–4 ở ngưỡng 0,50 và 21 / 56 / 55 / 72 % ở ngưỡng 0,15; nhìn bằng mắt, ở cổng 2–4 phần lớn vùng đó là thảm, tức báo động giả. Đây chưa phải số đo so với nhãn.
- **Trọng số lớp đã kiểm đủ ba seed và không phải cách gỡ** (17.1). So với lượt trộn cùng seed nó cho nhất quán ba điều: bớt bỏ sót người và ô tô trên ACDC, tăng recall vật lạ RO21 (69,6 ± 3,1 % so với 63,0 ± 1,6 %), và tăng báo động giả (9,7 ± 1,6 % so với 5,6 ± 2,0 %). So với nền thì RO21 recall chưa phân biệt được (67,0 ± 2,3 %), còn lỗi vật cản→FREE trên ACDC không có chiều nhất quán.
- Chưa làm: seed thứ hai và ba cho lượt ba bộ; chấm chéo WoodScape / AVM cho hai seed trộn sau; ảnh minh họa lỗi theo lớp cho lượt trộn.

## 19. Cách chạy lại

Từ thư mục `autopark`, trong `.venv-train`:

```powershell
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.prepare_extra avm     --out datasets/prepared/avm_ss_binary_v1
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.prepare_extra acdc    --out datasets/prepared/acdc_binary_v1
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.prepare_extra combine --caches datasets/prepared/woodscape_binary_v1 datasets/prepared/avm_ss_binary_v1 --out datasets/prepared/ws_avm_v1
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.prepare_extra combine --caches datasets/prepared/woodscape_binary_v1 datasets/prepared/avm_ss_binary_v1 datasets/prepared/acdc_binary_v1 --out datasets/prepared/ws_avm_acdc_v1
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.train --config configs/train_woodscape_rtx4000_baseline.json --out runs/ai_ws_avm --set prepared_manifest=datasets/prepared/ws_avm_v1/manifest.json --set seed=20260922
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.train --config configs/train_woodscape_rtx4000_baseline.json --out runs/ai_ws_avm_weighted --set prepared_manifest=datasets/prepared/ws_avm_v1/manifest.json --set class_weights=train_inverse_frequency --set seed=20260922
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.evaluate --checkpoint runs/ai_ws_avm/best.pt --split val --manifest datasets/prepared/avm_ss_binary_v1/manifest.json --out runs/ai_ws_avm/eval_cross_avm --examples 0
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.evaluate_external --checkpoint runs/ai_ws_avm/best.pt --dataset acdc --split val --out runs/ai_ws_avm/eval_acdc
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.evaluate_external --checkpoint runs/ai_ws_avm/best.pt --dataset acdc --split val --out runs/ai_ws_avm/eval_acdc_thr015 --threshold 0.15
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.evaluate_external --checkpoint runs/ai_ws_avm/best.pt --dataset road_obstacle --out runs/ai_ws_avm/eval_ro21
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.evaluate_external --checkpoint runs/ai_ws_avm/best.pt --dataset road_obstacle --out runs/ai_ws_avm/eval_ro21_thr015 --threshold 0.15
```

Các lệnh `prepare_extra` kiểm tra tham số của mình; xem `--help` để biết đường dẫn dữ liệu thô mặc định. `train.py` từ chối `--out` đã có `status.json` ("already holds a run; pick a new --out or use --resume"), nên khi chạy lại phải đổi sang `runs/<ten_moi>`. Ngưỡng mặc định của `evaluate_external` là 0,50: thư mục `eval_acdc` / `eval_ro21` là ngưỡng 0,50 (bảng mục 16), `*_thr015` là ngưỡng 0,15 (bảng 17.1); chạy `--threshold 0.15` vào thư mục thường sẽ ghi đè metrics.json của ngưỡng 0,50.

*Cập nhật 24/09/2026:* dòng `combine` thứ hai (ba cache, đúng thứ tự woodscape → avm → acdc như `combined_from` trong manifest của `ws_avm_acdc_v1`) được thêm vào khối lệnh trên; trước đó khối lệnh thiếu bước dựng cache của lượt `ai_ws_avm_acdc`. Trường `purpose` trong [acdc_cityscapes_to_binary_v1.json](autopark/configs/acdc_cityscapes_to_binary_v1.json) vẫn ghi "EVALUATION ONLY. Nothing is trained on ACDC with this file", nhưng từ 22/09 tệp này cũng là ánh xạ mặc định của `prepare_extra acdc` để dựng cache huấn luyện `acdc_binary_v1` cho lượt `ai_ws_avm_acdc`, nên câu đó đã lỗi thời. **Cố ý không sửa chữ trong tệp:** `prepare_extra` băm nguyên byte tệp làm `mapping_sha256` của cache (bản checkout CRLF của commit `960efd2` cho `d91f14cc…`, khớp manifest của `acdc_binary_v1` và 25 tệp `metrics.json` chấm ACDC trong `runs/`), bước `combine` băm tiếp các hash con thành `933fe354…` của `ws_avm_acdc_v1`, và `runs/ai_ws_avm_acdc/best.pt` lưu đúng `933fe354…`. Đổi một byte (đã thử ngày 24/09: sửa riêng chuỗi `purpose` cho `cadbc18a…`, cache ghép sẽ thành `fa69be80…`) thì trên cache dựng lại ở đúng đường dẫn cũ `evaluate --split val` sẽ từ chối checkpoint ("different split or label mapping") và `train --resume` sẽ báo "mapping_sha256 differs", dù ánh xạ lớp không đổi (suy từ mã `evaluate.py`, `train.py`; chưa chạy thử vì phải dựng lại cache). Hash cũng phụ thuộc kiểu xuống dòng: bản LF của cùng tệp cho `aa2504a2…` (cache ghép `32d0ff0b…`), nên muốn tái hiện đúng hash phải dựng từ bản checkout CRLF (`core.autocrlf=true` như máy này) hoặc truyền `--mapping` trỏ tới bản CRLF đó.
