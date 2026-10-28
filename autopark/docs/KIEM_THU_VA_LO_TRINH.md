# Kiểm thử và lộ trình

Bộ chấm đánh giá chuyển động, sự kiện và hình học toàn thân xe; không chỉ dựa vào thông báo hoàn thành của bộ điều khiển.

## Kết quả chặng 1

Đến ngày 28/10/2026, bộ đánh giá gồm 26 tình huống cơ sở và 18 tình huống có nhiễu, lỗi hoặc thao tác tiếp theo. Ba bộ giá trị ngẫu nhiên cố định tạo thành 132 lượt thử.

| Kỳ vọng của lượt thử | Số lượt đúng kỳ vọng |
|---|---:|
| Đến đích và đứng yên | 90 trên 90 |
| Từ chối đầu bài không hợp lệ | 18 trên 18 |
| Dừng đúng yêu cầu hoặc lỗi đã đặt | 24 trên 24 |
| Tổng | 132 trên 132 |

Ngoài ra, 15 thao tác tiếp theo hoàn thành từ tư thế vừa dừng. Chín lượt thông thường và hai lượt cố ý hết thời gian đều phát lại khớp; hai lượt hết thời gian vẫn được ghi là thất bại và nằm ngoài tổng 132. Nhóm kiểm thử hồi quy liên quan đạt 278 trên 278.

## Phạm vi và cách chấm

Bộ thử bao gồm cua trái/phải, tiến/lùi, cửa hẹp, lách cột, chỉnh vào khe, đầu bài cần từ chối, mất/phục hồi phản hồi và chọn đích tiếp. Kích thước xe, mức nhiễu và ngưỡng chấm được đặt trước khi chạy.

Trạng thái mô phỏng được ghi cách nhau 5 mili giây. Hết thời gian tìm kiếm không chứng minh tình huống không có đường đi. Không kích hoạt được lỗi dự kiến, thiếu dữ liệu hoặc xe tự chạy lại đều không được tính đạt.

![Luồng dừng và xác nhận phản hồi](images/dung-va-phan-hoi.svg)

*Phải phân biệt yêu cầu dừng, quá trình phanh và xác nhận xe đã đứng yên.*

Kết quả chỉ áp dụng cho bộ tình huống và mô hình đã thử, chưa xác nhận cảm biến, cơ cấu hay phanh trên xe thật. Ngưỡng thực nghiệm phải dựa trên số đo và được giữ nguyên khi chấm.

## Sáu chặng của dự án

| Chặng | Trạng thái và việc cần hoàn tất |
|---|---|
| 1. Đánh giá trong mô phỏng | **Đã hoàn tất bản đầu:** bộ tình huống, chấm độc lập, báo cáo và phát lại |
| 2. Điều khiển và kết nối xe | Hoàn thiện đầu ra, phản hồi tốc độ/góc lái và giao tiếp bo thật |
| 3. Đo xe, nguồn và phanh | Đo thông số xe, quãng dừng; kiểm nguồn, dừng khẩn và lỗi |
| 4. Định vị và quan sát sát xe | Hiệu chuẩn, đo sai số và vùng mù bằng tham chiếu độc lập |
| 5. Tích hợp chạy thật | Quan sát rồi thử từng thao tác chậm, giữ đúng vị trí khi chọn bước tiếp |
| 6. Nghiệm thu và bàn giao | Chốt tiêu chí thực, lặp bộ thử, giữ video và cả lượt không đạt |

Chặng 2 đến 6 chưa hoàn tất theo hồ sơ hiện có. Trong khi chuẩn bị thiết bị, tiếp tục duy trì bộ thử mô phỏng và bổ sung tình huống tái hiện mỗi khi phát hiện lỗi mới.
