# Các dataset ưu tiên đã tải và cách dùng

Ngày: 20/09/2026. Theo yêu cầu tải các bộ dùng ngay, lựa chọn là **AVM-SS đầy đủ**, **DROW v2 đầy đủ** và **WoodScape tập con ghép cặp**. Danh mục rộng hơn có [44 bộ/nhánh](DANH_MUC_DATASET.md), cùng [bản JSON](catalog.json).

**Đợt tải bổ sung theo yêu cầu “tải hết”:** đang tải WoodScape RGB/semantic/instance đầy đủ, ACDC RGB + semantic/invalid masks train/val + semantic nhánh ảnh tham chiếu, và RoadAnomaly21/RoadObstacle21 cùng mã benchmark. Xem [trạng thái cập nhật tự động](TRANG_THAI_TAI_DAY_DU.md); chỉ coi hoàn tất khi báo cáo ghi **Hoàn tất tải và giải nén: CÓ**. Không suy dung lượng `.part` thành số byte đã tải vì file lớn có thể được đặt trước kích thước.

*Cập nhật 24/09/2026:* đợt tải bổ sung đã xong — [TRANG_THAI_TAI_DAY_DU.md](TRANG_THAI_TAI_DAY_DU.md) ghi **Hoàn tất tải và giải nén: CÓ** (cập nhật UTC 2026-09-19T20:18), đủ 8 gói ở trạng thái `extracted`, và dữ liệu nằm trong `training/` (`woodscape`, `acdc`, `road_obstacle`, `road_anomaly`). Ngày 21/09 các ZIP trong `raw/` và `raw/full/` (gồm cả AVM-SS và DROW) đã được chuyển ra ngoài để xóa sau khi đối chiếu CRC32 với bản giải nén; hai thư mục này nay chỉ còn các tệp `.zip.json`/`.progress.json` ghi SHA-256 và tiến trình. Các đường dẫn archive trong tài liệu này là vị trí lúc tải; bản giải nén là bản duy nhất trên máy. Tiến trình giám sát tải ở đoạn dưới không còn cần chạy.

Tiến trình nền `supervise_downloads.py` giám sát lượt tải, thử chạy lại worker bị ngắt với số lần giới hạn, và bộ theo dõi kiểm tra/giải nén các archive đã đạt checksum. Nó hoạt động khi máy đang bật; không phải dịch vụ tự khởi động cùng Windows. Trạng thái tiến trình nằm ở `download_metadata/supervisor_state.json`. Kho ảnh ACDC không hỗ trợ HTTP Range nên phải tải lại từ đầu nếu stream bị đứt; WoodScape và Zenodo có checkpoint theo khối.

Archive bổ sung nằm trong `raw/full/`; dữ liệu đã kiểm tra và giải nén nằm trong `training/`; metadata/calibration/license WoodScape nằm trong `woodscape_metadata/`; mã benchmark đã tải nhưng chưa cài hoặc chạy nằm trong `benchmark_tools/`. Nhãn test giữ kín của ACDC/benchmark không được tạo giả hoặc đưa vào train.

## AVM Semantic Segmentation — đầy đủ

- Nguồn: [repo tác giả](https://github.com/Engro39/avm_dataset), [Drive của tác giả](https://drive.google.com/drive/folders/1izgXSHUisjdJMMLz43B8vjI9-JjqTDQL).
- Archive: `raw/avm_seg_db.zip`, **252.992.120 byte**, đã kiểm tra ZIP CRC và giải nén tại `avm_ss/`.
- SHA-256: `b9a8f70fcb9f57bb1c8360034cbf09b06277b2361453edfa5039960cd33c52ef`.
- Đã đọc toàn bộ **6.763 ảnh và 6.763 mask**, cùng kích thước 320×160, không thiếu cặp. Có polygon YAML gốc.
- Split gốc: **4.057 train / 2.706 test**; không trùng ID hoặc SHA-256 ảnh giữa hai tập. Chưa kiểm tra ảnh gần trùng/sequence leakage.
- Manifest từng cặp và split: [avm_pairs.json](avm_pairs.json). Báo cáo: [download_audit.json](download_audit.json).

**Phát hiện cần giữ lại:** ngoài 5 màu ghi trong README, toàn bộ mask có **7.071 pixel RGB (255,255,0)**. Chưa xác minh ý nghĩa lớp màu vàng; bộ chuyển `avm_to_project()` giữ mọi màu lạ ở **255 UNKNOWN/IGNORE**, không biến thành FREE. Không sửa mask gốc. Khi đánh giá mô hình cần công bố số pixel bị ignore.

Nhãn vùng xe mình màu đen cũng là ignore. RGB xanh dương là free-space, trắng là marker trên mặt nền, đỏ là xe, xanh lá là vật khác. Đây là AVM đã chiếu/ghép, không phải bốn ảnh camera thô. License dữ liệu chưa được nêu rõ trong README/gói đã xem; không nhầm việc tải công khai với license MIT.

## DROW v2 — đầy đủ

- Nguồn: [repo](https://github.com/VisualComputingInstitute/DROW), [release ZIP](https://github.com/VisualComputingInstitute/DROW/releases/download/v2/DROWv2-data.zip).
- Archive: `raw/DROWv2-data.zip`, **197.970.996 byte**, đã kiểm tra CRC và giải nén tại `drow/DROWv2-data/`.
- SHA-256: `1537422ab02e14de0cbd60dfde60ca9efb354e9d48e4d7bcca5ecfcdbe0df227`.
- Có **113 file scan, 464.023 dòng scan**, chia như sau:

| Split | File scan | Dòng scan |
|---|---:|---:|
| train | 78 | 341.147 |
| val | 30 | 74.745 |
| test | 5 | 48.131 |

Đã kiểm tra mọi dòng CSV đều có **452 cột**. Đối chiếu [loader v2 của tác giả](https://github.com/VisualComputingInstitute/DROW/blob/master/v2/utils/__init__.py): cột 0 là sequence ID, cột 1 là thời gian, 450 cột còn lại là range. Đừng áp mô tả/loader v1 vào v2.

`.wp` là nhãn người, `.wc` xe lăn, `.wa` dụng cụ hỗ trợ đi lại, `.odom2` odometry. Ghép bằng **tên recording + sequence ID**, không chỉ ID trên toàn bộ dataset. Vắng annotation khác với một frame được gán nhãn danh sách rỗng. Giá trị range `29.96` là N/A theo tác giả, không mặc định là vùng trống.

Trong val có `run_2015-11-25-11-18-12-d.bag.wc` và `.wa` không có file `.csv` cùng stem: bỏ qua khi ghép, giữ nguyên bản gốc. Chưa kiểm tra độ chính xác hình học hay mọi annotation bằng mắt. README, license và bản tham chiếu loader được lưu trong `drow/`.

Dữ liệu DROW dùng MIT; phần `reha` giữ CC BY-NC-SA 3.0 theo tác giả. Đây là laser 2D ở cấu hình khác C1, không phải dữ liệu kiểm chứng RPLIDAR hay nhãn pixel camera.

## WoodScape — tập con phục vụ kiểm tra pipeline

Nguồn: [repo Valeo](https://github.com/valeoai/WoodScape), [Drive chính thức](https://drive.google.com/drive/folders/1X5JOMEfVlaXfdNy24P8VA-jMs0yzf_HR).

Đã tải và kiểm tra **64 cặp**, gồm **16 cặp mỗi hướng FV/MVL/MVR/RV**, ghép đúng basename từ RGB và `semantic_annotations/gtLabels`. Cả 64 cặp đọc được, không lệch kích thước, class ID nằm trong 0–9 và CRC khớp ZIP nguồn. Đây là subset kỹ thuật, **không phải train/val/test benchmark chính thức**, và các hướng không mặc định cùng timestamp. Mỗi cặp lưu tên member ZIP, kích thước và SHA-256 trong `woodscape_subset/manifest.json`; kết quả trong [download_audit.json](download_audit.json).

Ảnh có kích thước **1280×966**, nhãn grayscale class ID. Đã tải thêm `woodscape_subset/calibration.zip` (3.331.622 byte, CRC đạt) và `LICENSE.pdf` (372.396 byte); trích đúng **64 JSON calibration cùng tên** vào `woodscape_subset/calibration/`. Giấy phép dữ liệu là điều khoản riêng của Valeo; MIT của code không bao phủ ảnh.

Kho RGB đầy đủ được server công bố **15.220.809.344 byte**; kho semantic **198.490.338 byte**. Script tải tập con dùng HTTP Range và ZIP CRC, không tải toàn bộ kho ảnh, không vượt đăng nhập/quota. Giữ bộ đầy đủ ở đợt tải tiếp theo khi cần train quy mô lớn. Class mapping tham khảo ở `samples/woodscape/semantic_mapping_9_classes.json`; không coi void=FREE.

## Tải lại và kiểm tra lại

Chạy trong thư mục `autopark`, với môi trường đã cài theo README:

```powershell
# AVM-SS đầy đủ
.\.venv\Scripts\python.exe -m gdown 'https://drive.google.com/uc?id=1LmFKoZiG_00Z2VZ3_Q0ikiFf1oDcg6hk' -O datasets/raw/avm_seg_db.zip

# DROW v2 đầy đủ
.\.venv\Scripts\python.exe -m gdown 'https://github.com/VisualComputingInstitute/DROW/releases/download/v2/DROWv2-data.zip' -O datasets/raw/DROWv2-data.zip

# WoodScape ghép cặp 16 ảnh mỗi hướng
.\.venv\Scripts\python.exe -X utf8 datasets/download_woodscape_subset.py --per-camera 16

# Kiểm tra các thư mục đã giải nén, không huấn luyện
.\.venv\Scripts\python.exe -X utf8 datasets/verify_downloads.py
```

Hai archive đầy đủ hiện đã giải nén. Khi tải lại, đối chiếu SHA-256 trước khi dùng; không ghi đè dữ liệu đã tự gán nhãn. Có thể dùng 7-Zip/Explorer giải nén vào các thư mục tương ứng. Với script tự giải nén phải kiểm tra member không thoát thư mục đích.

Đọc ảnh/mask khi đường dẫn Windows có dấu:

```python
from pathlib import Path
import cv2
import numpy as np
from autopark.evaluation.dataset_audit import avm_to_project

root = Path("datasets/avm_ss")
image = cv2.imdecode(np.frombuffer((root / "images/00000001.jpg").read_bytes(), np.uint8), cv2.IMREAD_COLOR)
mask_bgr = cv2.imdecode(np.frombuffer((root / "gt/00000001.png").read_bytes(), np.uint8), cv2.IMREAD_COLOR)
labels = avm_to_project(cv2.cvtColor(mask_bgr, cv2.COLOR_BGR2RGB))
# labels: 0 FREE, 1 OBSTACLE, 255 IGNORE; không resize bằng bilinear.
```

## Các việc chưa làm

Chưa tải toàn bộ 44 nguồn, chưa đăng ký tài khoản dataset, chưa gửi email xin dữ liệu và chưa train model. *Cập nhật 24/09/2026: đã huấn luyện baseline trên WoodScape ngày 21/09 và thử thêm AVM-SS/ACDC ngày 22–23/09, xem [HUAN_LUYEN.md](../../HUAN_LUYEN.md); giấy phép từng bộ ở [GIAY_PHEP_DU_LIEU.md](../docs/GIAY_PHEP_DU_LIEU.md).* Một lần thử tải log Intel từ máy chủ Freiburg bị từ chối kết nối; dùng DROW đã tải cho bước đọc scan trước, giữ Intel/IR-MCL trong danh mục.

Độ đúng nhãn chưa được chứng nhận chỉ bằng kiểm tra file/palette. Dữ liệu sa bàn với gá camera MN300 vẫn cần thu và gán nhãn ở giai đoạn sau. Toàn bộ raw/archive được loại khỏi Git; các file metadata và tài liệu được giữ để tái hiện.
