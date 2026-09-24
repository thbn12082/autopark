# Giấy phép dữ liệu — bảng kiểm, ngày kiểm 22/09/2026

Mỗi dòng ghi giấy phép, câu trích nguyên văn và ngày tự kiểm. Bộ nào chưa đọc được văn bản gốc thì ghi
"chưa xác minh", không suy đoán.

*Cập nhật tối 24/09/2026:* thêm link tới toàn văn điều khoản WoodScape có sẵn trong repo và địa chỉ trang bộ dữ liệu mà
văn bản đó ghi; thêm dòng trọng số pretrained của torchvision dùng làm điểm khởi đầu huấn luyện (kể cả khả năng backbone
đã qua ImageNet, cần tra); thêm yêu cầu ghi công của DROW. Chi tiết ở mục "Kiểm tối 24/09/2026" cuối tệp.

| Bộ | Giấy phép | Câu trích / nguồn | Kiểm ngày |
|---|---|---|---|
| **WoodScape** (đã huấn luyện) | Điều khoản riêng của Valeo, dữ liệu proprietary. MIT của mã KHÔNG áp dụng cho ảnh. | [LICENSE.pdf](https://drive.google.com/file/d/12IrLnGfng6s-NogJLIvUZsCxF1NDA-FA/view): *"You shall use the Dataset only (i) for research purposes ... (ii) teaching, (iii) to perform benchmarking for purposes of academic or applied research publication or (iv) for personal experimentation."* và *"You shall not use the Dataset for commercial purposes ... and notably not use or deploy the Dataset, any models trained on or refined using the Dataset including pre-training or augmentation, in operation of a vehicle or to assist in the operation of vehicle."* *Thêm tối 24/09/2026:* toàn văn (2 trang) có trong repo: [datasets/woodscape_metadata/LICENSE.pdf](../datasets/woodscape_metadata/LICENSE.pdf) (đã commit, không bị git-ignore). Hai câu trích ở trên khớp văn bản đọc từ tệp này. Tệp ghi bộ dữ liệu có tại `woodscape.valeo.ai`, xem mục cuối. | 22/09/2026; toàn văn trong repo đọc lại tối 24/09/2026 |
| **ACDC** | Nghiên cứu phi thương mại, ETH Zürich | `datasets/training/acdc/gt/License.pdf` mục 1.1: *"made freely available to academic and non-academic entities for non-commercial purposes only (such as academic research, teaching, scientific publications, or personal experimentation)"*; mục 2.5 cấm mục đích quân sự. **Không có điều khoản nào về vận hành phương tiện.** | 22/09/2026 |
| **AVM-SS** | KHÔNG có tuyên bố giấy phép | [repo Engro39/avm_dataset](https://github.com/Engro39/avm_dataset) không có file LICENSE; API GitHub trả `license: null`. Không có giấy phép nghĩa là tác giả giữ toàn quyền. | 22/09/2026 |
| **DROW v2** | MIT, riêng phần `reha` giữ CC BY-NC-SA 3.0 | [repo](https://github.com/VisualComputingInstitute/DROW). *Thêm tối 24/09/2026:* README của tác giả (bản sao `datasets/drow/README_source.md`, git-ignore) yêu cầu trích **cả hai** bài DROW khi dùng bất cứ thứ gì trong repo, và giải thích MIT là dùng được nếu ghi công tác giả. Hình nào dựng từ DROW mà đưa vào khóa luận thì phải trích hai bài đó, xem mục cuối. | 20/09/2026; ghi công kiểm tối 24/09/2026 |
| **Trọng số khởi tạo torchvision** `LRASPP_MobileNet_V3_Large_Weights.COCO_WITH_VOC_LABELS_V1` (điểm bắt đầu của mọi lượt huấn luyện đã chạy: 12 lượt chính `runs/ai_*/run_manifest.json` và 2 lượt kiểm tra thử `runs/ai_woodscape_rtx4000_v1_checks/smoke`, `overfit32`, tổng 14 `run_manifest.json` trong `runs/`; thêm tối 24/09/2026) | Mã torchvision: BSD. **Điều khoản riêng của tệp trọng số: cần tra** | Mô tả trong torchvision 0.26.0: huấn luyện trên một phần COCO, chỉ dùng 20 lớp có trong Pascal VOC. Tức là ảnh COCO với bộ nhãn VOC, không phải ảnh VOC. *Thêm tối 24/09/2026:* mô tả đó không nói backbone khởi tạo từ đâu. Hàm dựng `lraspp_mobilenet_v3_large` trong cùng tệp mặc định `weights_backbone=MobileNet_V3_Large_Weights.IMAGENET1K_V1`, và meta của trọng số trỏ tới một công thức huấn luyện (`references/segmentation`, chưa đọc: không có trong gói đã cài). Vì vậy backbone nhiều khả năng đã được huấn luyện trước trên ImageNet rồi mới huấn luyện trên COCO: **cần tra**. Mục "Pre-trained Model License" trong METADATA của gói nói trọng số có thể mang điều khoản riêng theo dữ liệu huấn luyện, người dùng tự kiểm. Với tệp này gói không nêu điều khoản cụ thể nào. Điều khoản COCO (ảnh và nhãn) và điều khoản ImageNet: **cần tra**, chưa đọc văn bản gốc | 24/09/2026 |
| **RoadObstacle21** (đang dùng để chấm ngoài miền: [HUAN_LUYEN.md](../../HUAN_LUYEN.md) mục 8, 10, 16) | chưa xác minh | Gói tải `datasets/training/road_obstacle/dataset_ObstacleTrack` chỉ có `image-sources.txt` ghi nguồn theo cảnh (BUW, EPFL), không kèm văn bản giấy phép. Điều khoản trên trang SegmentMeIfYouCan chưa đọc. | 24/09/2026 |
| **RoadAnomaly21** (chưa dùng trong kết quả nào lúc kiểm; *cập nhật 25/09/2026:* từ muộn tối 24/09 đã chấm 10 ảnh `validation*` có nhãn, kết quả ở [HUAN_LUYEN.md](../../HUAN_LUYEN.md) mục 8, mã ở commit `77eb51f`) | Giấy phép theo từng ảnh | `datasets/training/road_anomaly/dataset_AnomalyTrack/LICENSE.txt` ghi tác giả, giấy phép và nguồn từng ảnh: CC BY 2.0–4.0, CC BY-SA 1.0–4.0, CC0, public domain, giấy phép Pixabay/Pexels/Unsplash; riêng `toy_car0000.jpg` ghi "subject to copyright". Tệp không nói gì về nhãn/mask. | 24/09/2026 |

## Vấn đề cần xử lý trước khi nộp

**WoodScape cấm dùng mô hình huấn luyện trên nó để vận hành hoặc hỗ trợ vận hành phương tiện.** Mô hình
L-RASPP hiện tại huấn luyện trên WoodScape và theo thiết kế đầu ra của nó sẽ đi vào costmap cho planner.
*Cập nhật 24/09/2026:* tới nay chưa nối: `CameraSemanticLayer` trong `fusion/layers.py` chưa được nơi nào khởi tạo,
`perception/costmap.py` mới chạy trên ảnh WoodScape lưu sẵn, còn trên bàn thử giai đoạn 2 lớp tô AI chỉ để quan sát. *Cập nhật 25/09/2026:* vẫn đúng ở `54cb3e2`. BEV nhiều camera
(`perception/bev.py`, commit `1d2b857`, [BEV.md](BEV.md)) là đường đưa xác suất AI xuống costmap, nhưng cũng chưa được
nối vào hợp nhất hay planner, và chưa chạy với hiệu chuẩn thật trên camera dự án ([BEV.md](BEV.md) mục 6).
Ba hướng xử lý, chọn một và ghi rõ trong khóa luận:

1. **Tách vai trò.** Giữ phần WoodScape thuần nghiên cứu nhận thức (đo offline, báo cáo số liệu, đúng mục
   "academic or applied research publication"), và KHÔNG nối mô hình đó vào vòng điều khiển xe. Xe chạy bằng
   LiDAR và, khi có camera, bằng mô hình huấn luyện trên dữ liệu tự thu.
2. **Thay dữ liệu cho mô hình triển khai.** Huấn luyện lại bằng ảnh tự chụp trên sa bàn (ảnh không vướng giấy
   phép; nhãn xem ghi chú dưới) và/hoặc ACDC (không có điều khoản về phương tiện). Cách này đồng thời tốt hơn về kỹ
   thuật vì đúng miền.
   *Cập nhật 24/09/2026:* công cụ gán nhãn sa bàn ([GAN_NHAN_SA_BAN.md](GAN_NHAN_SA_BAN.md)) mặc định lấy nhãn nháp
   từ mô hình huấn luyện trên WoodScape. Chưa đánh giá nhãn đã sửa từ nháp đó có chịu điều khoản Valeo hay không
   (manifest cache ghi `draft_origins` và `licence_note`). Muốn chắc chắn đi đúng hướng này: nhập ảnh bằng `--no-draft`,
   khởi tạo từ trọng số pretrained chính thức của torchvision (như lượt nền), không khởi tạo từ checkpoint WoodScape
   và không ghép cache WoodScape (GAN_NHAN_SA_BAN.md mục 2 và mục 4).
3. **Hỏi Valeo.** Email xin xác nhận liệu xe mô hình 1/12 trên sa bàn trong phòng thí nghiệm có nằm trong phạm
   vi "operation of a vehicle" không. Chưa có trả lời thì không coi là được phép.

**Quyết định của người làm khóa luận (22/09/2026):** chọn cách hiểu rằng xe mô hình 1/12 chạy trên sa bàn trong
phòng, không ra đường công cộng, thuộc phạm vi "personal experimentation" và "academic research" mà điều khoản
cho phép, nên tiếp tục dùng mô hình huấn luyện trên WoodScape. Ghi nhận để minh bạch: văn bản Valeo viết
"operation of a vehicle" mà không kèm điều kiện đường công cộng, nên cách hiểu này chưa được Valeo xác nhận.
Nếu sau này sản phẩm được thương mại hóa hoặc đưa lên phương tiện thật thì phải huấn luyện lại bằng dữ liệu khác.

Ghi công bắt buộc đã được thêm vào đầu `HUAN_LUYEN.md` và `autopark/README.md` theo yêu cầu
*"conspicuously displayed in all public material and website referencing research conducted with the Dataset"*.

*Cập nhật 24/09/2026:* cùng khối ghi công đã được thêm vào đầu `README.md` gốc, trang đầu của repo trên GitHub (commit
356752e), và vào ghi chú 24/09 ở mục 9 của `BAO_CAO_GIAI_DOAN_0.md`. Một số tài liệu trong `autopark/docs/` nhắc tới
mô hình hoặc lượt huấn luyện WoodScape nhưng chưa có dòng ghi công riêng (ví dụ `GIAI_DOAN_1_CHUAN_BI.md`,
`GIAI_DOAN_2_BAN_THU.md`, `HIEU_CHUAN_CAMERA.md`, `GAN_NHAN_SA_BAN.md`). Chưa quyết định có cần thêm ghi công vào các
tài liệu này trước khi công bố khóa luận hay không.

## Kiểm tối 24/09/2026

Chỉ đọc tệp có sẵn trên máy bàn, không tải gì, không mở trang web nào.

### WoodScape: toàn văn trong repo và địa chỉ trang bộ dữ liệu

- Tệp: [datasets/woodscape_metadata/LICENSE.pdf](../datasets/woodscape_metadata/LICENSE.pdf), 372.396 byte, 2 trang, SHA-256
  `64843e0d8fec1b67057acfb43b022af2b27608e96e2288306810c8a3987a85f4`. Siêu dữ liệu PDF ghi tạo ngày 11/02/2021 bằng
  Microsoft Word. Tệp đã commit từ commit đầu `bef5695`. Thư mục `datasets/` chỉ bị git-ignore một phần (`raw/`, `drow/`,
  `training/`, …), `woodscape_metadata/` không nằm trong danh sách đó. Mục WoodScape của
  [datasets/TAI_VA_KIEM_TRA.md](../datasets/TAI_VA_KIEM_TRA.md) (nguồn: repo Valeo và Drive chính thức) ghi tệp được tải
  thêm cùng `calibration.zip`. Chưa đối chiếu tệp này với bản trên Drive mà README của repo WoodScape trỏ tới (link ở bảng
  trên).
- Cách đọc: máy không có `pypdf` hay PyMuPDF, nên dùng một script tạm (giải nén luồng zlib, dịch mã chữ qua bảng
  ToUnicode của phông; không lưu trong repo). Văn bản đọc ra liền mạch, hai câu trích ở bảng trên có đủ trong đó.
- **Địa chỉ:** định nghĩa "Dataset" trong tệp ghi bộ dữ liệu có tại `woodscape.valeo.ai`. Trong tệp **không có** chuỗi
  `woodscape.valeo.com` và không có liên kết web nào (URI) tới Valeo. Dòng đầu README của repo WoodScape (bản sao
  `datasets/woodscape_metadata/README.md`) lại ghi `https://woodscape.valeo.com`. Các khối ghi công trong dự án đang dùng
  `.com` (README gốc, `autopark/README.md`, `HUAN_LUYEN.md`, `TONG_HOP_DU_AN.md`, `BAO_CAO_GIAI_DOAN_0.md`, `BEV.md`,
  `DAN_Y_KHOA_LUAN.md`; *cập nhật 25/09/2026:* thêm `KICH_BAN_NGHIEM_THU.md` và `NGUONG_NGHIEM_THU_DE_XUAT.md` từ commit `54cb3e2`; ngoài tài liệu, chuỗi `license` mà `perception/bev.py` ghi vào tệp ra khi chạy BEV trên ảnh WoodScape cũng dùng `.com`). Điều khoản buộc ghi công kèm link tới trang web của bộ dữ liệu; địa chỉ duy nhất văn bản nêu là
  `woodscape.valeo.ai`. Hiện địa chỉ nào còn chạy và là trang chính: **cần tra** (tối 24/09 không mở trang nào). Tệp này không sửa các khối ghi
  công ở tài liệu khác.
- Tệp còn ghi Valeo có thể sửa điều khoản bất cứ lúc nào và người dùng phải tự xem bản đang có hiệu lực. Bản trong repo
  là bản tải về lúc chuẩn bị dữ liệu, không chắc là bản mới nhất: **cần tra** lại trước khi nộp.

### Trọng số pretrained của torchvision (điểm bắt đầu huấn luyện)

- Mã: `autopark/perception/model.py` dùng `LRASPP_MobileNet_V3_Large_Weights.COCO_WITH_VOC_LABELS_V1` khi
  `initialization = torchvision_official_pretrained_weights`. `run_manifest.json` của **cả 14** lượt huấn luyện trong
  `runs/` (git-ignore), gồm 12 lượt chính `runs/ai_*/run_manifest.json` và 2 lượt kiểm tra thử
  `runs/ai_woodscape_rtx4000_v1_checks/smoke`, `overfit32` (21/09), ghi đúng một tệp trọng số
  `lraspp_mobilenet_v3_large-d234d4ea.pth`, SHA-256 bắt đầu `d234d4eae9d5`; torch 2.11.0+cu128, torchvision 0.26.0+cu128.
  *(Sửa tối 24/09/2026: bản trước đếm "cả 12" vì chỉ tìm ở `runs/ai_*/`; kết luận cùng một điểm bắt đầu không đổi.)*
- Dữ liệu huấn luyện của trọng số này, theo mô tả trong mã torchvision đã cài: ảnh **COCO**, chỉ giữ 20 lớp có trong
  **Pascal VOC**. Tên "COCO_WITH_VOC_LABELS" vì thế nghĩa là ảnh COCO với bộ nhãn VOC. Không có ảnh VOC trong đó theo mô tả
  này. Số đo torchvision công bố cho trọng số: mIoU 57,9 trên COCO val2017 với nhãn VOC.
- *Thêm tối 24/09/2026:* chuỗi mô tả `_docs` chỉ nói COCO. Trong `torchvision/models/segmentation/lraspp.py` đã cài có
  hai chỗ khác: meta có khóa `recipe` trỏ tới
  `https://github.com/pytorch/vision/tree/main/references/segmentation#lraspp_mobilenet_v3_large`, và hàm dựng mặc định
  `weights_backbone=MobileNet_V3_Large_Weights.IMAGENET1K_V1` (theo meta trong `mobilenetv3.py`, trọng số này được huấn
  luyện từ đầu trên ImageNet). Suy ra: backbone MobileNetV3 của trọng số COCO nhiều khả năng đã khởi tạo từ ImageNet trước
  khi huấn luyện trên COCO. Đây mới là suy luận từ mã: công thức huấn luyện không có trong gói, chưa đọc (**cần tra**). Mã
  dự án không tự tải trọng số ImageNet: `perception/model.py` truyền `weights_backbone=None`, hàm dựng cũng bỏ backbone
  khi đã có `weights`, và cache torch hub trên máy bàn chỉ có `lraspp_mobilenet_v3_large-d234d4ea.pth`. ImageNet, nếu có,
  chỉ đi vào qua lịch sử huấn luyện của tệp trọng số COCO. Điều này không mâu thuẫn với ghi chú ở
  [GAN_NHAN_SA_BAN.md](GAN_NHAN_SA_BAN.md) mục 2 rằng trainer không có tùy chọn khởi tạo chỉ từ ImageNet.
- Giấy phép: METADATA của gói torchvision ghi mã là BSD. Mục "Pre-trained Model License" ghi trọng số có thể mang điều
  khoản riêng theo dữ liệu đã dùng để huấn luyện, và người dùng tự xác định mình có được phép hay không. Mục đó chỉ nêu
  riêng mô hình SWAG (CC BY-NC 4.0). Với trọng số L-RASPP này, gói không nêu điều khoản cụ thể nào.
- **Cần tra:** điều khoản sử dụng của COCO cho ảnh (ảnh lấy từ Flickr, mỗi ảnh có giấy phép riêng) và cho nhãn, và điều
  khoản đó có áp dụng cho trọng số huấn luyện trên COCO hay không. Chưa đọc văn bản gốc nào của COCO. METADATA của
  torchvision không có câu nào cấm dùng trọng số này trên phương tiện, nhưng như vậy **không** có nghĩa là đã được phép.
  Thêm (tối 24/09/2026): công thức huấn luyện ở link `recipe` có dùng backbone ImageNet hay không, và nếu có thì điều khoản
  truy cập ImageNet (chưa đọc văn bản gốc, **cần tra**) có ràng buộc trọng số dẫn xuất hay không.
- Hướng 2 ở trên (huấn luyện lại bằng ảnh sa bàn) vẫn khởi tạo từ trọng số này, nên kết quả tra ở đây cũng áp dụng cho mô
  hình triển khai sau này.

### DROW: ghi công khi dùng hình

- README của tác giả (bản sao `datasets/drow/README_source.md`, git-ignore cùng `datasets/drow/`): mục "Citations and
  Thanks" yêu cầu trích **cả hai** bài; mục "License" nói toàn bộ bộ dữ liệu theo MIT, trừ phần `reha` giữ CC BY-NC-SA
  3.0. Tệp MIT (bản sao `datasets/drow/LICENSE_source.txt`, bản quyền 2016 Visual Computing Institute) buộc giữ thông báo
  bản quyền và giấy phép trong mọi bản sao của phần mềm.
- Hai bài phải trích (theo dòng trích dẫn của README; BibTeX trong README ghi năm 2016 cho bài đầu, và ghi Beyer, Hermans
  đóng góp ngang nhau):
  - Beyer, L., Hermans, A., Leibe, B. (2017). *DROW: Real-Time Deep Learning-Based Wheelchair Detection in 2-D Range
    Data.* IEEE Robotics and Automation Letters, 2(2), 585–592.
  - Beyer, L., Hermans, A., Linder, T., Arras, K. O., Leibe, B. (2018). *Deep Person Detection in 2D Range Data.* IEEE
    Robotics and Automation Letters, 3(3), 2726–2733.
- Hình trong repo dựng từ DROW: [drow_odom_map.png](evidence/lidar/drow_odom_map.png),
  [drow_odom_mirror_map.png](evidence/lidar/drow_odom_mirror_map.png), [drow_fixed_map.png](evidence/lidar/drow_fixed_map.png)
  ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 5), và `runs/perception_integration/drow_scan_person.png`
  (git-ignore). Cả bốn dựng từ bản ghi val `run_2015-11-25-10-34-20-a`. *(Cập nhật 25/09/2026: commit `a7cec5e` thêm
  bốn hình DROW nữa trong `evidence/lidar/`:
  [odometry_khop_scan_drow_10-34-20-a_scan_to_map.png](evidence/lidar/odometry_khop_scan_drow_10-34-20-a_scan_to_map.png),
  [odometry_khop_scan_drow_10-34-20-a_scan_to_scan.png](evidence/lidar/odometry_khop_scan_drow_10-34-20-a_scan_to_scan.png),
  [odometry_khop_scan_drow_13-47-42_scan_to_map.png](evidence/lidar/odometry_khop_scan_drow_13-47-42_scan_to_map.png) và
  [odometry_khop_scan_drow_13-47-42_scan_to_map_khoa_cung_truoc_sua.png](evidence/lidar/odometry_khop_scan_drow_13-47-42_scan_to_map_khoa_cung_truoc_sua.png).
  Theo tên tệp, hai hình đầu cũng từ bản ghi val `run_2015-11-25-10-34-20-a`; hai hình sau từ bản ghi test
  `run_t_2015-11-26-13-47-42` (lệnh chạy ghi trong `evidence/lidar/odometry_khop_scan_20260924.json`). Ghi công ở
  [SO_SANH_DINH_VI_SLAM.md](SO_SANH_DINH_VI_SLAM.md) mục "Ghi công dữ liệu". Câu về `reha` dưới đây cũng áp dụng cho
  bốn hình này: kiểm lại 25/09/2026 vẫn 0 tệp.)* Trong `datasets/drow/` không có tệp nào tên chứa
  `reha` (kiểm tối 24/09/2026: 0 tệp), nên các hình này theo MIT. Hình nào đưa vào khóa luận thì chú thích hình ghi nguồn
  DROW v2 và trích hai bài trên. Nếu sau này dùng phần `reha` thì theo CC BY-NC-SA 3.0 (phi thương mại, chia sẻ cùng
  giấy phép).
