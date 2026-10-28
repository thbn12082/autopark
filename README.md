# AutoPark — hỗ trợ xoay trở trong chỗ hẹp

AutoPark giúp xe mô hình tự thực hiện thao tác ngắn ở tốc độ thấp. Người lái chọn vị trí và hướng đích gần; xe đánh lái, tiến hoặc lùi rồi dừng. Bước tiếp theo do người lái quyết định từ nơi xe vừa dừng.

Phạm vi gồm cua hẹp, qua cửa, lách cột và chỉnh xe vào khe. Đỗ xe là một ứng dụng gần; tìm ô tự động và dẫn xe tới đích xa nằm ngoài phạm vi.

## Một lượt sử dụng

Chọn đích gần, tính thao tác, xem trước nếu cần rồi xác nhận thực hiện. Người lái có thể yêu cầu dừng bất cứ lúc nào. Muốn tiếp tục phải đợi xe đứng yên và xác nhận một lượt mới.

![Giao diện mô phỏng cảnh cua hẹp](autopark/docs/images/giao-dien-cua-hep.png)

*Ảnh ứng dụng trong mô phỏng: xe đã có đường tiến/lùi và vùng thân xe sẽ quét qua. Đây chưa phải lượt chạy xe thật.*

## Giới hạn thử của hai cảnh mẫu

| Đại lượng | Giá trị |
|---|---|
| Khoảng cách từ điểm xuất phát đến đích | Tối đa 70 cm |
| Vùng thao tác | Khung vuông cạnh 1,5 m quanh điểm xuất phát, chỉ dùng phần nằm trong sa bàn |
| Tổng quãng đường tiến và lùi | Tối đa 1,40 m |
| Số lần đổi chiều | Tối đa 3 |
| Tốc độ | Tối đa 0,10 m/s |

Các giá trị trên dùng cho xe mô hình giả định và có thể điều chỉnh. Toàn thân xe phải nằm trong vùng được phép; khi cua còn phải xét đầu, đuôi và hai sườn xe quét qua đâu.

## Trạng thái hiện tại

Đến ngày 28/10/2026, chặng đánh giá phần mềm trong mô phỏng đã hoàn tất với 44 tình huống. Hệ thống đã có giao diện, tìm và bám đường, xử lý dừng, ghi lại và phát lại lượt chạy.

**Chưa có kết quả thao tác trên xe thật.** Việc tiếp theo là hoàn thiện điều khiển và phản hồi trên bo, đo xe và quãng phanh, hiệu chuẩn cảm biến, rồi thử từng thao tác chậm.

Bộ tài liệu gồm sáu phần: Tổng quan, Kiến trúc, Vận hành, Phần cứng và hiệu chuẩn, Kiểm thử và lộ trình, Dữ liệu và giấy phép.
