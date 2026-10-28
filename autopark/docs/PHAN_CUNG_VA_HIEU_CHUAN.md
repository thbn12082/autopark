# Phần cứng và hiệu chuẩn

Chặng đầu đã hoàn tất trong mô phỏng. Xe thật chưa chạy thao tác; đầu ra chuyển động trên bo mặc định tắt và phần mềm chưa đọc tốc độ, góc lái thực. Kết quả mô phỏng không mở các điều kiện đang chặn xe thật.

## Đo xe và hệ tọa độ

![Hệ tọa độ và kích thước xe mô hình giả định từ cấu hình](images/he-truc-va-kich-thuoc.svg)

*Kích thước và giới hạn trong hình là giả định cho mô phỏng, không phải số đo hay ngưỡng nghiệm thu.*

Tư thế đặt tại tâm trục sau: trục x hướng trước, trục y hướng trái. Cần đo chiều dài cơ sở, bề rộng, phần nhô, vòng quay, trễ đánh lái, tốc độ thấp và quãng phanh. Ghi điều kiện pin, sàn, tải, dụng cụ và độ phân tán qua nhiều lần đo.

LiDAR phải được gá cố định, đo vị trí so với xe và kiểm hướng trái, phải bằng vật thật. Bản đồ cần được neo vào cùng hệ tọa độ.

## Hiệu chuẩn camera

1. Đo kích thước ô trên bảng chuẩn; chụp đúng chế độ camera, nhiều góc và vị trí, phủ cả mép ảnh.
2. Kiểm sai số và ảnh sau hiệu chỉnh; giữ ảnh gốc cùng kết quả.
3. Đo vị trí, hướng gá camera; kiểm phép chiếu bằng vật có vị trí đo trên sàn. Đổi gá phải đo lại.
4. Loại thân xe, viền và vùng không tin cậy khỏi ảnh dùng để suy luận; kiểm nguy cơ che mất vật sát xe.

Camera trên cao dùng để chấm phải có mốc sàn độc lập, vị trí dấu trên xe đã đo và đồng bộ thời gian. Không dùng cùng dữ liệu vừa hiệu chuẩn để kết luận độ chính xác.

## Bo điều khiển, nguồn và dừng

Hoàn thiện phản hồi tốc độ, góc lái và tư thế sống trước khi chạy. Lệnh chuyển động có hạn; mất lệnh hoặc phản hồi phải dẫn tới dừng. Kết nối lại không tự chạy tiếp. Bo ảo chỉ kiểm phần mềm và giao tiếp.

Chọn nguồn, dây, cầu chì theo dòng đo thực; tách nguồn động lực và logic. Dừng khẩn cấp cần phần tử ngắt động lực độc lập.

Thử khi chưa cấp động lực, rồi kê bánh, sau đó mới kiểm phanh trên sàn. Thử mất liên lạc, mất cảm biến, khởi động lại và đứt dây dừng; giữ bản ghi cùng quãng dừng đo được.
