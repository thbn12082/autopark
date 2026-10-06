# Huấn luyện và đánh giá AI nhận thức

**Kết luận hiện tại (30/09/2026):** checkpoint tham chiếu vẫn là `runs/ai_woodscape_rtx4000_v1/best.pt`. Mô hình có kết quả tốt trên WoodScape nội bộ, nhưng bỏ sót vật nhỏ, yếu ở cảnh tối và chưa được chấm bằng ảnh sa bàn có nhãn. Ngày 29/09/2026 checkpoint được chấm lại trên máy bàn hiện tại và cho cùng số val tới bốn chữ số thập phân (mục 2.1).

Biên tập 30/09/2026 theo mã tại `ff4a018` (mã giống `ebbec83`); bản 26/09/2026 dựng từ hồ sơ tại `9d68257`. Số liệu thuộc các đợt 21–24/09/2026 trên máy bàn trước, trừ các lượt kiểm lại ngày 29/09/2026 ở mục 2.1; lần biên tập không huấn luyện hay đo lại. Hai số đọc sai từ hồ sơ đã sửa theo tệp kết quả: báo nhầm ở ngưỡng 0,15 trên test (mục 10) và ảnh test tệ nhất (mục 2.8).

Nghiên cứu sử dụng **[Valeo WoodScape Dataset](https://github.com/valeoai/WoodScape)**. Quyết định dùng mô hình trong vòng điều khiển ngày 25/09 là quyết định của người làm khóa luận; Valeo chưa xác nhận cách diễn giải điều khoản. Không áp dụng quyết định này cho checkpoint dùng AVM-SS hoặc nhãn nháp AI. [Hồ sơ giấy phép](autopark/docs/GIAY_PHEP_DU_LIEU.md).

## Cách đọc báo cáo

- **FREE:** pixel được dự đoán là vùng trống; chưa bảo đảm thân xe đi qua được.
- **BLOCKED:** pixel vật cản/vùng bị chặn.
- **IGNORE = 255:** không tính vào loss và chỉ số.
- **mIoU:** trung bình mức trùng khớp của hai lớp; càng cao càng tốt.
- **Recall vật cản:** tỷ lệ pixel vật cản được phát hiện.
- **Vật cản → FREE:** tỷ lệ bỏ sót pixel vật cản; cần theo dõi cùng từng loại vật.
- **FREE → vật cản:** báo nhầm vùng trống; làm hệ thống thận trọng hơn nhưng có thể dừng không cần thiết.
- **Seed:** giá trị điều khiển ngẫu nhiên khi huấn luyện. Trung bình ± độ lệch chuẩn ở đây phản ánh dao động giữa các seed, không phải sai số do cỡ tập ảnh.

Các mục 1–19 giữ số thứ tự để tài liệu kỹ thuật khác tiếp tục tham chiếu được. Muốn chạy lại, xem mục 4 và 19.

## 1. Kết quả baseline

Mô hình: **L-RASPP + MobileNetV3-Large**, hai lớp, đầu vào 512×384, 30 epoch.

| Tập nội bộ | Số ảnh | mIoU | IoU FREE | IoU BLOCKED | Recall vật cản | Precision vật cản | Vật cản → FREE |
|---|---:|---:|---:|---:|---:|---:|---:|
| Validation | 1.235 | 0,9700 | 0,9741 | 0,9659 | 0,9830 | 0,9824 | 1,70% |
| Test | 1.235 | 0,9692 | 0,9735 | 0,9650 | 0,9825 | 0,9818 | 1,75% |

Các số này ở ngưỡng 0,50. Tập test của checkpoint nền được chấm ở 0,50 ngày 21/09 và thêm ở 0,15 ngày 22/09. Không mô tả toàn bộ lịch sử là “chỉ chấm test một lần”.

Đây là split nội bộ, không phải test chính thức WoodScape. Nhóm ảnh được suy ra từ timestamp/ảnh gần trùng, chưa có recording ID xác nhận; không loại trừ cùng tuyến phố xuất hiện ở nhiều tập. Kết quả chưa chứng minh khả năng tổng quát hóa sang sa bàn.

## 2. Dữ liệu, cấu hình và quá trình huấn luyện

**Từ dữ liệu tới checkpoint tham chiếu và các phép chấm.** Sơ đồ theo đúng các lệnh trong `autopark/perception/`; số chi tiết ở các mục 2.2–2.7, 8–12 và 15–18.

```mermaid
flowchart TD
    WS["WoodScape: 8.234 ảnh fisheye và polygon, ngoài Git"] --> MAP["Ánh xạ nhãn woodscape_binary_v1.json: FREE 0, BLOCKED 1, IGNORE 255"]
    MAP --> PREP["prepare.py: letterbox 512×384, nhóm chống rò rỉ theo timestamp và ảnh gần trùng"]
    PREP --> FRZ["Split đóng băng trong Git: 5.764 / 1.235 / 1.235 ảnh"]
    FRZ --> VER["verify_cache: băm lại ảnh gốc, dựng lại 256 mẫu, ghi TRANSFER_READY.json"]
    VER --> BEN["benchmark.py: thử batch 8 / 16 / 32, chọn 16"]
    BEN --> TRN["train.py: L-RASPP MobileNetV3, khởi tạo torchvision COCO_WITH_VOC_LABELS_V1, AMP, 30 epoch, không đọc test"]
    TRN --> CK["best.pt tham chiếu ai_woodscape_rtx4000_v1, SHA-256 0459c3f4…0ccc, ngoài Git"]
    VER --> XTR["11 lượt khác: 2 seed, 1 trọng số lớp, 8 lượt có AVM-SS qua prepare_extra"]
    XTR --> CMP{"Có lượt nào vượt nền trên ACDC và RO21 chưa dùng để học?"}
    CMP -->|Không| CK
    CK --> VAL["evaluate val, --sweep: 0,50 theo mIoU, 0,15 theo F2"]
    VAL --> TST["evaluate test --final-test: 2 lần, ghi test_evaluations.jsonl"]
    CK --> EXT["evaluate_external: ACDC, RoadObstacle21, RoadAnomaly21"]
    CK --> ONX["export_onnx: opset 17, 12,9 MB, khớp PyTorch, chưa dùng khi chạy"]
    CK --> RE["29/09/2026 máy bàn hiện tại: chấm lại val mIoU 0,9700, train thử 1 epoch"]
    CK -.-> SAB["Chấm trên ảnh sa bàn tô tay"]
    CK -.-> LAP["Đo AI trên laptop RTX 3050 Ti"]
    classDef daco fill:#dff0d8,stroke:#3c763d,color:#1b3a1b
    classDef giaLap fill:#fcf8e3,stroke:#8a6d3b,color:#4d3b12
    classDef chuaLam fill:#f2dede,stroke:#a94442,color:#4d1a1a,stroke-dasharray: 4 3
    class WS,MAP,PREP,FRZ,VER,BEN,TRN,CK,XTR,CMP,VAL,TST,EXT,ONX,RE daco
    class SAB,LAP chuaLam
```

Xanh: đã có và đã kiểm/đo · Vàng: chỉ trong mô phỏng/giả lập · Đỏ viền đứt: chưa làm hoặc chưa thử trên thiết bị.

Mọi ô xanh là việc trên máy tính với ảnh lưu sẵn, không phải trên xe. Validation và test không cập nhật gradient; trainer không đọc test. Tập test của checkpoint nền được chấm đúng hai lần (mục 1), sau khi đã chốt mô hình; không dùng kết quả test để chỉnh ngược lại mô hình hay ngưỡng (mục 4). Hai ô đỏ là việc chưa làm (mục 6). Xem thêm sơ đồ 5.1 trong [Sơ đồ hệ thống](autopark/docs/SO_DO_HE_THONG.md).

### 2.1. Môi trường

Các lượt huấn luyện, đánh giá và đo độ trễ của tài liệu này (21–24/09/2026) chạy trên máy bàn trước, dùng tới 25/09/2026: i9-14900, RTX 4000 Ada 20 GB, RAM 64 GB, Windows 11; Python 3.12.10. Máy bàn hiện tại (từ 29/09/2026, Dell Precision 3680) có cùng CPU, GPU và RAM. Trên máy này chưa chạy lại lượt huấn luyện đủ 30 epoch, chưa chấm test và chưa đo lại độ trễ của mục 12; các số của tài liệu là của máy bàn trước, trừ bảng dưới. [Biên bản chuyển máy](autopark/docs/CHUYEN_MAY_BAN.md).

**Kiểm lại trên máy bàn hiện tại, 29/09/2026 15:08–15:19** (mã `b37e9ee`; hồ sơ gốc `autopark/runs/kiem_may_20260929/`, ngoài Git; [tóm tắt](autopark/docs/evidence/chuyen_may_20260929/kiem_may_20260929.md)):

| Lệnh | Kết quả | Đối chiếu |
|---|---|---|
| `verify_cache` | Đạt trong 29,9 s: manifest trùng bản đóng băng, 8.234 cặp ảnh và nhãn gốc đúng SHA-256, dựng lại 256 mẫu trùng từng bit | Như mục 2.2 |
| `evaluate` val, checkpoint tham chiếu, ngưỡng 0,50 | mIoU 0,9700, bỏ sót 1,70%, báo nhầm 1,33%; không ảnh nào trùng tập train | Trùng mục 1 tới bốn chữ số thập phân; trùng từng pixel với lần chấm val ngày 22/09/2026 trên máy bàn trước. Lệch 2 trên 113.096.842 pixel chỉ khi so với lần 21/09, lúc còn chấm bằng argmax (trước khi đổi quy tắc hòa 0,5, mục 13); [tóm tắt](autopark/docs/evidence/chuyen_may_20260929/kiem_may_20260929.md) mục 2.4 |
| `predict` một ảnh (`00000_FV.png`), ngưỡng 0,15 | Chạy được trên CUDA | Chỉ kiểm lệnh |
| `train --set epochs=1`, cấu hình lượt nền | 360 update, 102,7 s, val mIoU 0,9505; VRAM đỉnh 1,92 / 2,55 GB; không đọc test | Chỉ kiểm pipeline, không phải kết quả mô hình |
| `rig.bench`, bốn camera thật + LiDAR + AI, 640×480, 30 s | 716 lô AI, 23,86 bộ/s, lô trung vị 15,3 ms, 0 khung hỏng | Cùng máy, cùng ngày, lượt `may_moi` 15:15 (120 s): 23,87 bộ/s, lô trung vị 15,3 ms ([tóm tắt](autopark/docs/evidence/chuyen_may_20260929/kiem_may_20260929.md) mục 2.9). Máy bàn trước, phiên u01 ngày 23/09 (120 s, trước khi đổi quy tắc chờ camera ngày 24/09): 23,8 bộ/s, 16,4 ms ([bàn thử](autopark/docs/GIAI_DOAN_2_BAN_THU.md) mục 3.3) |
| Bước `ai` của `rig.may_moi`: lô 4 ảnh ngẫu nhiên 640×480 | Lượt 15:15: trung vị 12,7 ms, p95 21,8 ms. Ba lần lặp 15:19: trung vị 11,0 / 10,8 / 10,8 ms | Lượt 12:59 cùng ngày, tham chiếu `may_moi`: 10,8 / 12,1 ms ([biên bản chuyển máy](autopark/docs/CHUYEN_MAY_BAN.md) mục 2) |

Cài bằng `autopark\cai_dat_train.cmd` theo [hướng dẫn môi trường AI](autopark/README.md) và `requirements-train.lock`, không chép nguyên venv từ máy khác. `.venv-train` chép sang mà không chạy được thì script đổi tên thành `.venv-train.hong-tu-may-cu` rồi tạo mới. Máy chưa có trọng số pretrained của Torchvision trong `%USERPROFILE%\.cache\torch` thì lần train, benchmark hay `--resume` đầu tiên cần mạng; máy bàn hiện tại đã có tệp này từ lượt train thử ngày 29/09/2026.

### 2.2. Dữ liệu đã xác minh

WoodScape có 8.234 ảnh dùng trong cache: **5.764 train / 1.235 val / 1.235 test**. Kiểm manifest, hash ảnh/nhãn, split không giao nhau theo nhóm, mapping và giá trị mask. Đã dựng lại 256 mẫu khớp cache từng bit.

Pixel train: FREE 27,4%, BLOCKED 18,0%, IGNORE 54,6%; trong pixel hợp lệ, tỷ lệ khoảng 60:40. [Manifest đóng băng](autopark/datasets/frozen_splits/woodscape_binary_v1/manifest.json), [mapping](autopark/configs/woodscape_binary_v1.json).

### 2.3. Pipeline

Nạp trọng số phân đoạn chính thức Torchvision; thay cả hai đầu phân lớp thành hai lớp. Augment ảnh/mask dùng cùng biến đổi, vùng ngoài ảnh thành IGNORE.

Trainer dùng AMP, AdamW, checkpoint nguyên tử; chọn `best.pt` theo validation mIoU. Trainer không đọc test. `latest.pt` phục vụ tiếp tục chạy; `status.json` phân biệt running/stopped/failed/completed.

### 2.4. Kiểm thử pipeline

Hồ sơ 21/09 ghi 29 test đạt cho dữ liệu/huấn luyện, gồm resume giữa epoch khớp trọng số trên CPU, loss toàn IGNORE, mapping và tách tập. Đến `54cb3e2` hai tệp liên quan có 30 test. Đây là số theo từng thời điểm.

### 2.5. Chọn batch bằng phép đo

Trên GPU tham chiếu, batch 8/16/32 đạt tương ứng 200/247/226 ảnh train mỗi giây. Chọn **batch 16**, đỉnh VRAM giữ chỗ 2,38 GB trong phép benchmark đó.

`channels_last` từng làm train chậm trên tổ hợp phần mềm của máy bàn trước và đã bỏ. Không suy rộng kết quả đó sang mọi GPU/phần mềm.

### 2.6. Kiểm trước lượt dài

Đã thử overfit 32 ảnh, STOP/resume trên GPU và xem ảnh dự đoán để kiểm luồng. Các phép thử này kiểm pipeline, không dùng làm độ chính xác mô hình.

### 2.7. Lượt chính

Seed 20260920; batch 16; AdamW backbone LR 1e-4/head LR 1e-3, weight decay 1e-4; warmup 300 update rồi poly 0,9; clip 10; AMP fp16; patience 8.

30 epoch, 10.800 update, 901 giây; epoch tốt nhất 30. Đỉnh VRAM 1,92 GB cấp phát / 2,76 GB giữ chỗ. Một update bị AMP bỏ qua, không ghi loss vô hạn.

[Cấu hình trong repo](autopark/configs/train_woodscape_rtx4000_baseline.json). Cấu hình đã giải đầy đủ nằm ở `config_resolved.json` của run.

### 2.8. Khác biệt giữa các camera

Test @0,50: mIoU FV 0,9757; RV 0,9706; MVL 0,9593; MVR 0,9590. Bỏ sót vật cản tương ứng 1,21 / 1,76 / 2,52 / 2,52%. Ảnh test tệ nhất (00105_RV) sai 35,06% pixel và bỏ sót 46,9% pixel vật cản. Nguyên nhân chính là nhãn gốc: ảnh này là 1 trong 2 ảnh RV (trên 1.986) không có polygon `ego_vehicle`, nên thân xe và viền ảnh bị gán là vật cản. Số trung bình không đại diện cho mọi ảnh. Nguồn: `runs/ai_woodscape_rtx4000_v1/eval_test/per_image.csv` (ngoài Git).

## 3. Giới hạn

Dữ liệu huấn luyện là đường phố từ camera fisheye trên ô tô, không phải camera USB của xe mô hình. FREE có thể gồm mặt phẳng xe không nên đi vào; vật nhỏ hoặc tối dễ bị bỏ sót. Độ chính xác pixel chưa bao gồm sai số hiệu chuẩn, phép chiếu, vị trí xe và độ trễ.

## 4. Chạy lại baseline

Từ thư mục `autopark` chứa `pyproject.toml`, sau khi có dataset/cache:

```powershell
./.venv-train/Scripts/python.exe -X utf8 -m autopark.perception.verify_cache
./.venv-train/Scripts/python.exe -X utf8 -m autopark.perception.benchmark --config configs/train_woodscape_rtx4000_baseline.json --out runs/ai_luot_moi/benchmark.json
./.venv-train/Scripts/python.exe -X utf8 -m autopark.perception.train --config configs/train_woodscape_rtx4000_baseline.json --out runs/ai_luot_moi
./.venv-train/Scripts/python.exe -X utf8 -m autopark.perception.evaluate --checkpoint runs/ai_luot_moi/best.pt --split val --out runs/ai_luot_moi/eval_val
```

Chỉ chấm test sau khi chốt mô hình; lệnh yêu cầu `--split test --final-test` và ghi lịch sử chấm. Không dùng kết quả test để chỉnh tiếp mô hình/ngưỡng.

Dừng có kiểm soát: tạo tệp rỗng `STOP` trong thư mục run; bỏ tệp STOP trước khi tiếp tục:

```powershell
./.venv-train/Scripts/python.exe -X utf8 -m autopark.perception.train --out runs/ai_luot_moi --resume runs/ai_luot_moi/latest.pt
```

Dùng thư mục mới cho lượt mới; trainer từ chối ghi đè run đã có `status.json`.

## 5. Sản phẩm cần bàn giao

`best.pt`, `latest.pt`, `config_resolved.json`, `run_manifest.json`, `status.json`, `source.zip`, lịch sử đánh giá test, metrics và ảnh lỗi. Các tệp run/checkpoint không nằm trong Git.

## 6. Chưa làm

Chưa chấm trên ảnh sa bàn có nhãn; chưa đo hiệu năng AI trực tiếp trên laptop trình diễn; chưa nghiệm thu AI tạo vật cản trên camera/gá thật.

## 7. Bước tiếp theo

Thu ảnh đúng góc/độ cao camera dự án, gán nhãn tập đánh giá độc lập, chấm các checkpoint/ngưỡng rồi mới chọn cho sa bàn. [Quy trình nhãn](autopark/docs/GAN_NHAN_SA_BAN.md).

## 8. Đánh giá trên dữ liệu khác

Baseline @0,50, chấm tại độ phân giải nhãn gốc:

| Tập | Ảnh | mIoU | Vật cản → FREE |
|---|---:|---:|---:|
| ACDC val_ref, trời quang | 203 | 0,966 | 1,59% |
| ACDC val, thời tiết xấu | 406 | 0,908 | 4,42% |
| ACDC ban đêm | 106 | 0,899 | 8,38% |
| RoadObstacle21 val | 30 | 0,520 | 31,7% |

ACDC mapping để sidewalk/terrain và vùng invalid ở IGNORE. Vì thế bảng không chứng minh mô hình phân biệt được vỉa hè với đường. Khi coi sidewalk/terrain là BLOCKED, lỗi bỏ sót ACDC val tăng lên 14,5%.

Ở ACDC thời tiết xấu, baseline bỏ sót pixel xe 12,4%, người 6,4%, xe hai bánh khoảng 19%. Chỉ số gộp 4,42% che khác biệt giữa loại vật.

RoadObstacle21 có vật nhỏ: baseline không thấy vật trong 11/30 ảnh. Không suy rộng kết quả trời quang sang mọi miền ảnh.

**RoadAnomaly21:** chấm 10 ảnh validation có nhãn; 100 ảnh test không có nhãn công khai chỉ được đếm. Nhãn nền không có nghĩa FREE nên chỉ chấm recall của vật bất thường:

| Ngưỡng | Recall, trung bình ± độ lệch chuẩn ba seed | Vật bất thường → FREE |
|---|---:|---:|
| 0,50 | 89,6 ± 1,2% | 10,4 ± 1,2% |
| 0,15 | 94,5 ± 0,4% | 5,5 ± 0,4% |

Không định nghĩa mIoU/precision/báo động giả theo cách chấm này; không so với bảng xếp hạng SMIYC. Recall cao trên vật lớn không chứng minh phát hiện tốt vật nhỏ. Kết quả đợt này được ghi ở thư mục tạm, chưa lưu đủ hồ sơ vào `runs/`.

`evaluate.py` mặc định `--train-overlap refuse`: từ chối khi trùng tập train hoặc không kiểm được nguồn manifest. Đổi sang `warn` phải giữ cảnh báo trong kết quả. Kiểm không trùng train vẫn không biến một tập từng dùng chọn checkpoint thành tập đánh giá độc lập.

## 9. Độ dao động giữa seed

| Seed | Val mIoU tốt nhất | Test mIoU | Test vật cản → FREE |
|---|---:|---:|---:|
| 20260920 | 0,9700 | 0,9692 | 1,75% |
| 20260921 | 0,9706 | 0,9693 | 1,79% |
| 20260922 | 0,9702 | 0,9693 | 1,77% |

Ngưỡng 0,50. Trung bình test mIoU 0,9693 ± 0,0001. Khi so mô hình, cần nhiều seed và xem cả lỗi theo lớp; không kết luận từ một cải thiện nhỏ của một lượt.

## 10. Ngưỡng quyết định

**Một pixel được phân loại như thế nào?**

```mermaid
flowchart TD
    I["Ảnh đầu vào"] --> P["Mạng trả xác suất BLOCKED"]
    P --> Q{"Xác suất lớn hơn hoặc bằng ngưỡng?"}
    Q -->|Có| B["BLOCKED: dự đoán vật cản"]
    Q -->|Không| F["FREE: ứng viên vùng trống"]
    B --> E["So với nhãn thật để tính bỏ sót / báo nhầm"]
    F --> E
```

Sơ đồ mô tả phân lớp ảnh. Vật cản trên bản đồ còn cần hiệu chuẩn, ROI, phép chiếu BEV và kiểm thời gian dữ liệu; FREE trên ảnh chưa cho phép xe đi qua.

Quét ngưỡng trên validation (22/09/2026) và chọn theo F2 của BLOCKED, ưu tiên recall, cho **0,15**; trên val ở 0,15, bỏ sót 0,63% và báo nhầm 3,10% (`eval_val_sweep/threshold_sweep.json` và `eval_val_thr015/metrics.json` trong `runs/ai_woodscape_rtx4000_v1/`, ngoài Git). Chọn theo mIoU cho 0,50.

| Tập, checkpoint nền | Bỏ sót @0,50 → @0,15 | Báo nhầm FREE @0,50 → @0,15 |
|---|---:|---:|
| WoodScape test | 1,75% → 0,69% | 1,37% → 3,09% |
| ACDC val | 4,42% → 2,28% | 3,47% → 7,70% |
| RoadObstacle21 | 31,7% → 18,2% | 4,57% → 7,79% |

Cột báo nhầm là tỷ lệ pixel FREE bị gọi là vật cản. Trên WoodScape test ở 0,15 là 2.001.596 / 64.749.995 pixel = 3,09% (`runs/ai_woodscape_rtx4000_v1/eval_test_thr015/metrics.json`, ngoài Git). Các bản trước ngày 30/09/2026 ghi 3,97%: đó là 1 − precision BLOCKED, không phải tỷ lệ này.

Hạ ngưỡng giảm bỏ sót nhưng tăng báo nhầm. Đây chưa là ngưỡng nghiệm thu sa bàn. Ngăn AI camera dùng 0,15 làm ngưỡng BLOCKED; không nhầm với `t_free=0,15` của cấu hình BEV mặc định, nơi ý nghĩa khác. [AI camera](autopark/docs/AI_DIEU_KHIEN_XE.md).

**Ngưỡng nào được dùng ở đâu?** Mỗi công cụ có ngưỡng mặc định riêng. Xác suất đúng bằng ngưỡng BLOCKED (`--threshold`, `t_blocked`) luôn tính là BLOCKED; riêng `t_free` (lệnh `bev`, `camera_ai`) thì xác suất đúng bằng `t_free` tính là FREE.

```mermaid
flowchart LR
    SW["evaluate --sweep trên val WoodScape, 22/09/2026"] --> MI["Tối đa mIoU: 0,50, tức argmax"]
    SW --> F2["Tối đa F2 của BLOCKED: 0,15, ưu tiên ít bỏ sót"]
    MI --> EVP["evaluate, predict, evaluate_external: mặc định 0,50"]
    MI --> OVL["rig_app lớp tô: mặc định 0,50, nút 0,15, chỉ để nhìn"]
    MI --> LBL["labels import, nhãn nháp: mặc định 0,5"]
    F2 --> CAI["camera_ai trong phiên đỗ: t_blocked 0,15, t_free 0,05"]
    BEVC["Lệnh bev: t_free 0,15, t_blocked 0,50, ở đây 0,15 là ngưỡng FREE"]
    CAI --> UNC["Giữa t_free và t_blocked là UNKNOWN, không bao giờ FREE"]
    BEVC --> UNC
    CAI -.-> ACC["Ngưỡng nghiệm thu trên sa bàn: CHƯA CHỐT, cần tập chấm tô tay"]
    classDef daco fill:#dff0d8,stroke:#3c763d,color:#1b3a1b
    classDef giaLap fill:#fcf8e3,stroke:#8a6d3b,color:#4d3b12
    classDef chuaLam fill:#f2dede,stroke:#a94442,color:#4d1a1a,stroke-dasharray: 4 3
    class SW,MI,F2,EVP,OVL,LBL daco
    class CAI,BEVC,UNC giaLap
    class ACC chuaLam
```

Xanh: đã có và đã kiểm/đo · Vàng: chỉ trong mô phỏng/giả lập · Đỏ viền đứt: chưa làm hoặc chưa thử trên thiết bị.

Ô vàng: ngăn AI camera mới chạy với nguồn giả, rig tổng hợp và bản ghi phát lại (chưa có hiệu chuẩn camera thật, mục 18); lệnh `bev` mới chạy trên rig tổng hợp và ảnh WoodScape ([BEV.md](autopark/docs/BEV.md)). Mã: `perception/engine.py` (`decide`), `fusion/camera_ai.py`, `perception/bev.py`, `ui/rig_app.py`, `perception/labels.py`. Ngưỡng nghiệm thu đề xuất: [NGUONG_NGHIEM_THU_DE_XUAT.md](autopark/docs/NGUONG_NGHIEM_THU_DE_XUAT.md). Xem thêm sơ đồ 5.7 trong [Sơ đồ hệ thống](autopark/docs/SO_DO_HE_THONG.md).

## 11. Loss có trọng số lớp

Lượt WoodScape có trọng số khoảng 0,83/1,26 giảm bỏ sót validation từ 1,70% xuống 1,35% ở ngưỡng 0,50. Baseline hạ ngưỡng về 0,40 cho 1,36%, gần tương đương. Lượt này chưa tạo lý do thay checkpoint nền; không chấm test cho nó.

## 12. Độ trễ và ONNX

Đã xuất ONNX opset 17, 12,9 MB; đối chiếu 16 ảnh val, lệch logit tối đa 7×10⁻⁵ và argmax trùng 99,9999%.

p50 sau làm nóng (200 lượt; riêng Torch CPU 40 lượt, đầu-cuối 1280×966 là 100 lượt), đo ngày 22/09/2026 trên máy bàn trước i9/RTX 4000 Ada (dùng tới 25/09/2026) khi GPU rảnh:

| Cách chạy | Thời gian/ảnh |
|---|---:|
| ONNX Runtime CPU fp32 | 7,6 ms |
| Torch CPU fp32 | 23,6 ms |
| Torch CUDA fp32 | 4,4 ms |
| Torch CUDA fp16 | 5,5 ms |
| Tiền xử lý → mạng fp16 → softmax về CPU, ảnh 1280×966 | 7,8 ms |

Đây không phải độ trễ từ sự kiện ngoài đời tới quyết định xe. Chưa đo trên laptop RTX 3050 Ti; tải GPU làm số thay đổi. [Đo máy trình diễn](autopark/docs/MAY_NOP_DO_AN.md). Trên máy bàn hiện tại chưa chạy lại phép đo này; chỉ có độ trễ lô 4 ảnh 640×480 của lệnh kiểm máy mới và bàn thử (mục 2.1), là phép đo khác.

## 13. Kiểm thử và các sửa đổi sau baseline

Hồ sơ 22/09 ghi 260 test đạt, 4 bỏ qua ở môi trường mô phỏng và 65 test nhận thức đạt. Đó là lượt lịch sử, không phải tổng hiện tại.

Các nhóm sửa gồm che khuất costmap, kích thước mask/calibration, xác suất hòa 0,5, timestamp/ảnh cũ, mirror nhãn, giá trị scan và phân tích theo lớp. Môi trường AI hiện đã có PySide6 và Shapely; nhận xét cũ “không chạy được mô phỏng vì thiếu Shapely” đã lỗi thời.

## 14. Kết luận đánh giá mở rộng

Baseline dùng được làm mốc so sánh. Cảnh tối, vỉa hè và vật nhỏ là điểm yếu đã thấy. Hạ ngưỡng là một cách đánh đổi bỏ sót/báo nhầm, không giải quyết sai miền dữ liệu. Cần ảnh sa bàn để quyết định cho dự án.

## 15. Thử thêm AVM-SS và ACDC

| Cache | Train / val / test | Điều cần biết |
|---|---:|---|
| WoodScape | 5.764 / 1.235 / 1.235 | Split nội bộ theo nhóm suy ra |
| AVM-SS | 4.713 / 1.050 / 1.000 | Chia lại theo khối 50 ID; vẫn còn dấu hiệu ảnh gần trùng |
| ACDC | 1.600 / 406 / 0 | Train/val có thể cùng chuỗi GoPro |
| WoodScape + AVM | 10.477 / 2.285 / 2.235 | Val ghép dùng chọn checkpoint |
| WoodScape + AVM + ACDC | 12.077 / 2.691 / 2.235 | ACDC val không còn là đánh giá ngoài miền độc lập |

Giữ kiến trúc/augment, chỉ thay dữ liệu hoặc trọng số lớp như ghi trong từng lượt.

## 16. Kết quả các nhóm mô hình

Ngưỡng 0,50; ba seed ghi trung bình ± độ lệch chuẩn. Các lượt một seed không có ước lượng dao động.

| Nhóm | Seed | ACDC val mIoU | ACDC vật cản → FREE | RO21 recall |
|---|---:|---:|---:|---:|
| WoodScape nền | 3 | 0,914 ± 0,005 | 4,1 ± 0,4% | 67,0 ± 2,3% |
| AVM riêng | 1 | 0,209 | 82,7% | 34,1% |
| WoodScape + AVM | 3 | 0,781 ± 0,021 | 13,5 ± 2,8% | 63,0 ± 1,6% |
| WoodScape + AVM + ACDC | 1 | 0,983* | 0,5%* | 48,8% |
| WoodScape + AVM, trọng số | 3 | 0,790 ± 0,105 | 11,2 ± 9,2% | 69,6 ± 3,1% |

*Lượt học ACDC có liên hệ chuỗi với ACDC val; không trích số này như tổng quát hóa ngoài miền. AVM val của lượt trộn cũng đã dùng chọn checkpoint, không phải tập kiểm tra cuối độc lập.

### 16.1. Kết quả theo loại vật

Trộn AVM làm lỗi trên ACDC tăng ở tường, nhà, cây và xe lớn. Dùng trọng số giảm bỏ sót người/ô tô nhưng làm báo nhầm và dao động cao. Bảng theo 11 lớp và từng seed được giữ trong [báo cáo gốc, mục 16](https://github.com/thbn12082/autopark/blob/9d68257/HUAN_LUYEN.md).

## 17. Diễn giải

AVM giúp với ảnh nhìn từ trên xuống của chính miền AVM, nhưng các lượt trộn làm kết quả ACDC xấu hơn baseline. Chênh recall RO21 giữa một số nhóm còn nhỏ so với dao động và cỡ tập 30 ảnh; chưa đủ kết luận cải thiện chung.

### 17.1. Đổi ngưỡng và trọng số có khắc phục được không?

Ở 0,15, bỏ sót ACDC của nền là 2,2 ± 0,2%, trộn là 7,1 ± 1,5%, trộn có trọng số là 6,5 ± 6,1%. Trọng số không ổn định giữa seed; chưa giải quyết tác động dữ liệu khác miền.

Không kết luận từ riêng seed đầu cho ban đêm hoặc từ recall gộp.

## 18. Checkpoint tham chiếu và giới hạn sử dụng

Giữ **`runs/ai_woodscape_rtx4000_v1/best.pt`**. Không lượt thêm dữ liệu nào chứng minh vượt nền trên cả ACDC và RO21 chưa dùng để học/chọn mô hình.

Khi có ảnh sa bàn, so các nhóm bằng tập tô tay từ đầu, tách khỏi huấn luyện. Không dùng nhãn sửa từ dự đoán nền để kết luận nền tốt hơn mô hình khác.

AI đã chạy trực tiếp để quan sát trên bàn thử: trên máy bàn trước từ 23/09/2026, trên máy bàn hiện tại ngày 29/09/2026 (mục 2.1). Nhánh AI tạo vật cản trong phiên đỗ mới kiểm bằng nguồn giả/rig tổng hợp/replay; chưa có hiệu chuẩn camera thật nên vẫn bị chặn.

## 19. Chạy lại thử nghiệm mở rộng

Cần dữ liệu thô tương ứng và môi trường AI. Lệnh PowerShell, từ thư mục có `pyproject.toml`:

```powershell
./.venv-train/Scripts/python.exe -X utf8 -m autopark.perception.prepare_extra avm --out datasets/prepared/avm_ss_binary_v1
./.venv-train/Scripts/python.exe -X utf8 -m autopark.perception.prepare_extra acdc --out datasets/prepared/acdc_binary_v1
./.venv-train/Scripts/python.exe -X utf8 -m autopark.perception.prepare_extra combine --caches datasets/prepared/woodscape_binary_v1 datasets/prepared/avm_ss_binary_v1 --out datasets/prepared/ws_avm_v1
./.venv-train/Scripts/python.exe -X utf8 -m autopark.perception.train --config configs/train_woodscape_rtx4000_baseline.json --out runs/ai_ws_avm_moi --set prepared_manifest=datasets/prepared/ws_avm_v1/manifest.json --set seed=20260922
./.venv-train/Scripts/python.exe -X utf8 -m autopark.perception.evaluate_external --checkpoint runs/ai_ws_avm_moi/best.pt --dataset acdc --split val --out runs/ai_ws_avm_moi/eval_acdc
./.venv-train/Scripts/python.exe -X utf8 -m autopark.perception.evaluate_external --checkpoint runs/ai_ws_avm_moi/best.pt --dataset road_obstacle --out runs/ai_ws_avm_moi/eval_ro21
```

Thêm `--threshold 0.15` và chọn thư mục kết quả khác để chấm ngưỡng thấp. Với RoadAnomaly21 dùng `--dataset road_anomaly`. Với lượt trọng số dùng `--set class_weights=train_inverse_frequency` và thư mục run mới.

**Lưu ý tái hiện ACDC:** chuỗi `purpose` trong mapping cũ ghi “EVALUATION ONLY” đã lỗi thời vì tệp còn được dùng tạo cache train. Không sửa tùy tiện nội dung/kiểu xuống dòng của [mapping](autopark/configs/acdc_cityscapes_to_binary_v1.json): hash dựa trên nguyên byte, gồm LF/CRLF; thay đổi có thể làm cache/checkpoint không khớp dù ánh xạ lớp giống nhau. Hồ sơ gốc được dựng từ checkout CRLF.

[Báo cáo trước đợt biên tập 26/09](https://github.com/thbn12082/autopark/blob/9d68257/HUAN_LUYEN.md) giữ bảng đầy đủ theo camera/lớp/seed, đường dẫn các lượt, chẩn đoán hiệu năng và lịch sử sửa lỗi. Bản ngay trước đợt biên tập 30/09: [ff4a018](https://github.com/thbn12082/autopark/blob/ff4a018/HUAN_LUYEN.md).
