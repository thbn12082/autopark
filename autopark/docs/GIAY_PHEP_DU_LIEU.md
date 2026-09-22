# Giấy phép dữ liệu — bảng kiểm, ngày kiểm 22/09/2026

Mỗi dòng ghi giấy phép, câu trích nguyên văn và ngày tự kiểm. Bộ nào chưa đọc được văn bản gốc thì ghi
"chưa xác minh", không suy đoán.

| Bộ | Giấy phép | Câu trích / nguồn | Kiểm ngày |
|---|---|---|---|
| **WoodScape** (đã huấn luyện) | Điều khoản riêng của Valeo, dữ liệu proprietary. MIT của mã KHÔNG áp dụng cho ảnh. | [LICENSE.pdf](https://drive.google.com/file/d/12IrLnGfng6s-NogJLIvUZsCxF1NDA-FA/view): *"You shall use the Dataset only (i) for research purposes ... (ii) teaching, (iii) to perform benchmarking for purposes of academic or applied research publication or (iv) for personal experimentation."* và *"You shall not use the Dataset for commercial purposes ... and notably not use or deploy the Dataset, any models trained on or refined using the Dataset including pre-training or augmentation, in operation of a vehicle or to assist in the operation of vehicle."* | 22/09/2026 |
| **ACDC** | Nghiên cứu phi thương mại, ETH Zürich | `datasets/training/acdc/gt/License.pdf` mục 1.1: *"made freely available to academic and non-academic entities for non-commercial purposes only (such as academic research, teaching, scientific publications, or personal experimentation)"*; mục 2.5 cấm mục đích quân sự. **Không có điều khoản nào về vận hành phương tiện.** | 22/09/2026 |
| **AVM-SS** | KHÔNG có tuyên bố giấy phép | [repo Engro39/avm_dataset](https://github.com/Engro39/avm_dataset) không có file LICENSE; API GitHub trả `license: null`. Không có giấy phép nghĩa là tác giả giữ toàn quyền. | 22/09/2026 |
| **DROW v2** | MIT, riêng phần `reha` giữ CC BY-NC-SA 3.0 | [repo](https://github.com/VisualComputingInstitute/DROW) | 20/09/2026 |
| **RoadObstacle21 / RoadAnomaly21** | Theo benchmark SegmentMeIfYouCan | chưa xác minh văn bản gốc | — |

## Vấn đề cần xử lý trước khi nộp

**WoodScape cấm dùng mô hình huấn luyện trên nó để vận hành hoặc hỗ trợ vận hành phương tiện.** Mô hình
L-RASPP hiện tại huấn luyện trên WoodScape và đầu ra của nó đi vào costmap cho planner. Ba hướng xử lý, chọn
một và ghi rõ trong khóa luận:

1. **Tách vai trò.** Giữ phần WoodScape thuần nghiên cứu nhận thức (đo offline, báo cáo số liệu, đúng mục
   "academic or applied research publication"), và KHÔNG nối mô hình đó vào vòng điều khiển xe. Xe chạy bằng
   LiDAR và, khi có camera, bằng mô hình huấn luyện trên dữ liệu tự thu.
2. **Thay dữ liệu cho mô hình triển khai.** Huấn luyện lại bằng ảnh tự chụp trên sa bàn (không vướng giấy
   phép) và/hoặc ACDC (không có điều khoản về phương tiện). Cách này đồng thời tốt hơn về kỹ thuật vì đúng miền.
3. **Hỏi Valeo.** Email xin xác nhận liệu xe mô hình 1/12 trên sa bàn trong phòng thí nghiệm có nằm trong phạm
   vi "operation of a vehicle" không. Chưa có trả lời thì không coi là được phép.

Ghi công bắt buộc đã được thêm vào đầu `HUAN_LUYEN.md` và `autopark/README.md` theo yêu cầu
*"conspicuously displayed in all public material and website referencing research conducted with the Dataset"*.
