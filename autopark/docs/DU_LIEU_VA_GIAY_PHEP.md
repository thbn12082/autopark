# Dữ liệu, giấy phép và bằng chứng

Dữ liệu gồm tình huống mô phỏng, chuyển động, ảnh camera, vòng quét LiDAR và kết quả kiểm tra. Mỗi bộ cần giữ ngày, cấu hình, điều kiện thu và phiên bản phần mềm.

## Bằng chứng hiện tại

Bộ đánh giá ngày 28/10/2026 giữ đầu bài, quỹ đạo, sự kiện và kết quả từng lượt. Đến đích, từ chối và dừng được thống kê riêng; lượt thất bại cũng được giữ để phát lại.

Đây là dữ liệu tổng hợp và mô phỏng. Các bản ghi camera, LiDAR và bo ảo trước đó là hồ sơ lịch sử, không được đổi tên thành kết quả xe thật thực hiện thao tác gần.

![Ảnh gốc bàn thử bốn camera và LiDAR](evidence/rig/giao_dien_480p_thr015.jpg)

*Bốn camera đang nhìn sàn và thảm; ảnh có lớp tô dự đoán của AI cùng vòng quét LiDAR. Đây là bàn thử cảm biến, chưa phải lượt xe tự di chuyển.*

## Dữ liệu cần bổ sung

Mô hình hiện học chủ yếu từ ảnh đường phố. Cần thêm ảnh sa bàn có vật thấp, mép tường, cột, khe và vùng sát xe dưới nhiều điều kiện ánh sáng. Tách theo phiên/cảnh, kiểm ảnh trùng và dùng nhãn duyệt độc lập. Đo cả bỏ sót, báo nhầm, sai lệch vị trí và độ trễ phát hiện.

## Quyền sử dụng dữ liệu

Trạng thái dưới đây phản ánh hồ sơ rà soát tháng 9/2026, không phải xác nhận điều khoản mới.

| Nguồn | Điều kiện hoặc điểm còn chưa rõ |
|---|---|
| Valeo WoodScape | Dữ liệu có điều khoản riêng, giới hạn phi thương mại và có nội dung về vận hành phương tiện; giấy phép mã không bao phủ ảnh |
| ACDC | Nghiên cứu phi thương mại, cấm mục đích quân sự; hồ sơ chưa thấy điều khoản vận hành phương tiện |
| AVM-SS | Chưa có tuyên bố giấy phép rõ ràng |
| DROW | Mã theo MIT; phần dữ liệu reha theo CC BY-NC-SA 3.0; cần ghi công hai bài nghiên cứu của tác giả |
| Trọng số mô hình có sẵn | Điều khoản dữ liệu tiền huấn luyện còn phải kiểm riêng |
| RoadObstacle21 | Chưa xác minh điều khoản |
| RoadAnomaly21 | Quyền với ảnh phụ thuộc từng ảnh; quyền với nhãn còn chưa rõ |

Cách hiểu điều khoản vận hành phương tiện trong quyết định dùng WoodScape ngày 25/09/2026 **chưa được Valeo xác nhận**. Quyết định đó không bao phủ các bộ dữ liệu hoặc trọng số khác.

Giữ nguyên giấy phép gốc, thông báo bản quyền và tên nguồn khi dùng dữ liệu. Không xem việc tải được dữ liệu hay chạy được mô hình là bằng chứng đã có đầy đủ quyền sử dụng.

## Đọc các số đo lịch sử

Số đo cũ chỉ có ý nghĩa trong điều kiện đã ghi. Độ lặp lại của LiDAR không phải độ chính xác vị trí; kết quả bo ảo không phải phép đo phanh hoặc dừng khẩn trên xe.

Ảnh, bản ghi và biên bản gốc được giữ riêng. Khi thiếu tham chiếu độc lập hoặc chưa thử trên thiết bị, kết luận phải ghi đúng phần chưa kiểm chứng.
