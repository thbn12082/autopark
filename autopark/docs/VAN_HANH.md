# Vận hành

Mỗi lượt thực hiện một chuyển động gần. Trước khi bắt đầu, xe cần đứng yên, biết đúng vị trí và có khu vực thao tác xác định.

## Trình tự thao tác

1. Chọn tình huống, kiểm vị trí xe và vật cản.
2. Đặt vị trí và hướng đích gần.
3. Tính thao tác; sửa đầu bài nếu bị từ chối.
4. Xem trước nếu muốn kiểm đường và vùng quét.
5. Xác nhận thực hiện; yêu cầu dừng khi cần.
6. Đợi xe đứng yên rồi chọn đích tiếp.

![Luồng của một lượt thao tác gần](images/luong-do-xe.svg)

*Xem trước là mô phỏng, chưa làm xe thật chuyển động. Yêu cầu dừng bắt đầu quá trình phanh và chờ phản hồi xác nhận đứng yên.*

![Mô phỏng xe đã lùi vào khe](images/giao-dien-lui-vao-khe.png)

*Lần mô phỏng trong ảnh đã dừng tại đích; đường lập dài 40 cm, sai số vị trí cuối khoảng 0,9 cm.*

## Các chế độ

| Chế độ | Ý nghĩa |
|---|---|
| Mô phỏng | Xe và phản hồi được tạo trên máy tính |
| Điều khiển qua bo | Phần mềm gửi yêu cầu chuyển động và nhận số đo từ liên kết điều khiển |
| Quan sát | Người lái điều khiển; phần mềm chỉ tính toán và ghi nhận |

Nhánh sử dụng xe thật còn thiếu điều kiện phản hồi và đo đạc. Thay xe, đích hoặc vật cản làm phương án cũ không còn đủ điều kiện để tiếp tục dùng.

## Đọc kết quả đánh giá

Bộ thử chạy nhiều tình huống hoặc một tình huống riêng. Báo cáo giữ đầu bài, cấu hình và mọi kết quả, kể cả lượt không đạt.

| Kết quả | Cách hiểu |
|---|---|
| Hoàn thành | Xe đến đích trong sai số cho phép và đứng yên |
| Từ chối đúng | Đầu bài vi phạm điều kiện, xe chưa được phép chuyển động |
| Dừng đúng | Xe dừng theo đúng yêu cầu hoặc nguyên nhân lỗi và trong giới hạn đã đặt |
| Không đạt | Kết quả thực tế không đáp ứng kỳ vọng của tình huống |
| Chưa có số đo | Thiếu thông tin hoặc đại lượng không áp dụng; không được hiểu là bằng không |

Không gộp dừng và từ chối thành đến đích thành công. Thời gian chuyển động trong mô phỏng khác thời gian máy tính dùng để tính toán.

## Lưu và phát lại

Bản ghi giữ vị trí, hướng, tốc độ, góc lái và sự kiện. Khi lưu thất bại, bản cũ được giữ; nơi lưu chỉ đổi sau khi ghi thành công.

Phát lại đối chiếu đường và sự kiện đã ghi, kể cả một lượt thất bại. Tìm đường lại từ đầu bài cũ là phép thử mới, có thể cho kết quả khác.

Bản ghi camera và LiDAR được phát lại riêng; cần giữ đúng cấu hình và mốc thời gian. Dữ liệu xuất hiện trở lại sau lỗi không tự cho phép xe chạy tiếp.
