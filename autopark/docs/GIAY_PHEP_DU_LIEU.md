# Giấy phép dữ liệu — bảng kiểm, ngày kiểm 22/09/2026

Mỗi dòng ghi giấy phép, câu trích nguyên văn và ngày tự kiểm. Bộ nào chưa đọc được văn bản gốc thì ghi
"chưa xác minh", không suy đoán.

| Bộ | Giấy phép | Câu trích / nguồn | Kiểm ngày |
|---|---|---|---|
| **WoodScape** (đã huấn luyện) | Điều khoản riêng của Valeo, dữ liệu proprietary. MIT của mã KHÔNG áp dụng cho ảnh. | [LICENSE.pdf](https://drive.google.com/file/d/12IrLnGfng6s-NogJLIvUZsCxF1NDA-FA/view): *"You shall use the Dataset only (i) for research purposes ... (ii) teaching, (iii) to perform benchmarking for purposes of academic or applied research publication or (iv) for personal experimentation."* và *"You shall not use the Dataset for commercial purposes ... and notably not use or deploy the Dataset, any models trained on or refined using the Dataset including pre-training or augmentation, in operation of a vehicle or to assist in the operation of vehicle."* | 22/09/2026 |
| **ACDC** | Nghiên cứu phi thương mại, ETH Zürich | `datasets/training/acdc/gt/License.pdf` mục 1.1: *"made freely available to academic and non-academic entities for non-commercial purposes only (such as academic research, teaching, scientific publications, or personal experimentation)"*; mục 2.5 cấm mục đích quân sự. **Không có điều khoản nào về vận hành phương tiện.** | 22/09/2026 |
| **AVM-SS** | KHÔNG có tuyên bố giấy phép | [repo Engro39/avm_dataset](https://github.com/Engro39/avm_dataset) không có file LICENSE; API GitHub trả `license: null`. Không có giấy phép nghĩa là tác giả giữ toàn quyền. | 22/09/2026 |
| **DROW v2** | MIT, riêng phần `reha` giữ CC BY-NC-SA 3.0 | [repo](https://github.com/VisualComputingInstitute/DROW) | 20/09/2026 |
| **RoadObstacle21** (đang dùng để chấm ngoài miền: [HUAN_LUYEN.md](../../HUAN_LUYEN.md) mục 8, 10, 16) | chưa xác minh | Gói tải `datasets/training/road_obstacle/dataset_ObstacleTrack` chỉ có `image-sources.txt` ghi nguồn theo cảnh (BUW, EPFL), không kèm văn bản giấy phép. Điều khoản trên trang SegmentMeIfYouCan chưa đọc. | 24/09/2026 |
| **RoadAnomaly21** (chưa dùng trong kết quả nào) | Giấy phép theo từng ảnh | `datasets/training/road_anomaly/dataset_AnomalyTrack/LICENSE.txt` ghi tác giả, giấy phép và nguồn từng ảnh: CC BY 2.0–4.0, CC BY-SA 1.0–4.0, CC0, public domain, giấy phép Pixabay/Pexels/Unsplash; riêng `toy_car0000.jpg` ghi "subject to copyright". Tệp không nói gì về nhãn/mask. | 24/09/2026 |

## Vấn đề cần xử lý trước khi nộp

**WoodScape cấm dùng mô hình huấn luyện trên nó để vận hành hoặc hỗ trợ vận hành phương tiện.** Mô hình
L-RASPP hiện tại huấn luyện trên WoodScape và theo thiết kế đầu ra của nó sẽ đi vào costmap cho planner.
*Cập nhật 24/09/2026:* tới nay chưa nối: `CameraSemanticLayer` trong `fusion/layers.py` chưa được nơi nào khởi tạo,
`perception/costmap.py` mới chạy trên ảnh WoodScape lưu sẵn, còn trên bàn thử giai đoạn 2 lớp tô AI chỉ để quan sát.
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
