# Kiến trúc

Mỗi lượt đưa xe từ chỗ khó tới một tư thế đích gần rồi dừng. Người lái quyết định đích tiếp theo. Chặng đầu đã hoàn tất trong mô phỏng; xe thật chưa thực hiện thao tác.

![Các khối của thao tác gần](images/toan-canh.svg)

*Luồng chức năng; nhánh xe thật còn thiếu điều kiện. AI bổ sung vật cản, không điều khiển lái.*

## Tìm đường và thực hiện

Bộ lập đường tìm các đoạn tiến, lùi trong vùng thao tác. Đường phải phù hợp tư thế đầu và cuối, giới hạn chiều dài, số lần đổi chiều và khoảng trống cho toàn thân xe.

Đường tìm được còn phải chạy thử với bộ bám trong mô phỏng. Không đạt dung sai thì bị loại. Khi người dùng yêu cầu thực hiện, hệ thống kiểm lại đường, tư thế, phản hồi và điều kiện đứng yên.

![Vùng quét toàn thân từ quỹ đạo lập của cảnh cua hẹp](images/vung-quet-cua-hep.svg)

*Vùng quét từ đường lập của cảnh cua hẹp; chưa cộng sai số cảm biến và phanh của xe thật.*

Bộ bám hiệu chỉnh tốc độ, góc lái theo phản hồi và dừng trước khi đổi chiều. Vật mới, dữ liệu lỗi hoặc sắp vượt phạm vi có thể yêu cầu dừng. Dữ liệu phục hồi không tự làm xe chạy tiếp.

## Cảm nhận và định vị

LiDAR đo vật cản trong mặt quét và đối chiếu bản đồ để ước lượng tư thế. Vật thấp, vùng khuất và cảnh đối xứng có thể gây sai lệch. So sánh các lượt quét giúp kiểm chéo chuyển động nhưng vẫn dùng chung cảm biến.

Camera và AI bổ sung bằng chứng vật cản xuống mặt sàn. Vùng chưa rõ không được coi là trống; camera không xóa vật đã biết từ LiDAR hoặc người dùng. Các nguồn cần cùng hệ tọa độ và thời gian phù hợp.

Vùng che quanh thân xe trong bản đồ ảnh hiện có thể loại nhầm vật cản cách xe tới khoảng 10 cm. Cần kiểm lại phần này trước khi đưa xe vào khoảng hở nhỏ.

## Đánh giá độc lập

Kết quả được chấm lại bằng cách tính hình học riêng, xét tư thế cuối, khoảng hở, quãng đường và hành vi dừng. Có thử phản hồi trễ, nhiễu và mất mẫu. Kết quả này chưa thay thế phép đo trên xe thật.
