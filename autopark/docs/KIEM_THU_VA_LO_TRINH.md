# Kiểm thử và lộ trình

Mỗi lần thử là một thao tác tới đích gần do người lái chọn, kết thúc đứng yên rồi mới chọn bước tiếp. [Cách chạy kiểm thử](VAN_HANH.md).

## Tình huống cần kiểm

| Tình huống | Biến thể | Điều cần đo |
|---|---|---|
| Cua hẹp | Trái/phải, tiến/lùi | Đầu/đuôi quét, khoảng hở, sai số cuối |
| Qua cửa | Lệch tâm hoặc lệch hướng | Hở hai sườn, khả năng chỉnh lái |
| Lách cột | Cột cạnh đầu/đuôi | Vùng quét giữa mẫu, vật trong vùng mù |
| Chỉnh vào khe | Tiến/lùi, đổi chiều | Dừng trước đổi chiều, số nhịp, tư thế cuối |
| Đầu bài không đạt | Xa, vượt vùng/đường, không đủ hở | Từ chối trước chuyển động |
| Lỗi trong lượt | Vật mới, mất tư thế/cảm biến/telemetry | Thời gian/quãng dừng, không tự chạy lại |
| Bước tiếp | Sau hoàn thành hoặc dừng | Giữ đúng tư thế vừa dừng, tính lại đường |

Hai cảnh JSON hiện có là mẫu, chưa phải bộ nghiệm thu đầy đủ. `TIMEOUT` không chứng minh tình huống không có nghiệm.

## Ghi và chấm

Trước thử ghi bố trí, xe/giới hạn, nguồn tư thế, seed, mã nguồn, máy/thiết bị và số lần. Giữ video/log, sự kiện, tham chiếu và can thiệp của người. Đo sai số vị trí/hướng cuối, hở toàn thân nhỏ nhất, tổng đường, đổi chiều, thời gian tính/thực hiện, tốc độ và quãng dừng.

Báo riêng hoàn thành, dừng đúng yêu cầu, từ chối, thất bại và lần không tính kèm lý do; không bỏ lượt hỏng khỏi thống kê. Tách **TH** tổng hợp, **MP** mô phỏng, **BT** bàn thử, **XT** xe thật. Truth mô phỏng chỉ để chấm; độ lặp lại cảm biến không phải độ chính xác.

Công cụ còn dùng: `evaluation.score_run` chấm log, `evaluation.fault_drill` diễn tập lỗi, `evaluation.replay` đối chiếu runtime. Chúng không tự chứng minh thiết bị thật đạt.

## Ngưỡng

[nguong_nghiem_thu.json](../configs/nguong_nghiem_thu.json) giữ bộ N-…/DO-/VC-/AT-/DV- lịch sử với `DE_XUAT_CHO_CHOT`; score_run ghi SHA-256 bộ đã dùng. Bộ chấm chưa bao phủ hoàn chỉnh các tình huống gần mới, không tự gán mã rồi coi đã chấm đủ.

Cần chốt riêng dung sai, khoảng hở, tốc độ/quãng dừng, tuổi dữ liệu, số đổi chiều, số lần lặp và tỷ lệ đạt dựa phép đo. [Giới hạn mẫu](../../README.md) không phải ngưỡng nghiệm thu. Chốt phải có căn cứ, phạm vi và người duyệt; đồng bộ cấu hình/công cụ, không nâng ngưỡng để hợp thức hóa lượt hỏng.

## Thứ tự làm tiếp

1. Hoàn thiện ca mô phỏng gần, đặc biệt vùng quét, sai số bám và dừng.
2. Đo xe/cơ cấu, xác minh phản hồi, nguồn và E-stop.
3. Hiệu chuẩn cảm biến, đo định vị/vùng mù sát xe bằng tham chiếu độc lập.
4. Quan sát trên thiết bị, rồi một thao tác tốc độ thấp mỗi lượt.
5. Lặp bộ tình huống, chốt tiêu chí và báo cả kết quả không đạt.

Các bước cần tay người theo [phần cứng/hiệu chuẩn](PHAN_CUNG_VA_HIEU_CHUAN.md). Khi chờ thiết bị có thể chấm bản ghi, gán nhãn, kiểm fault/replay và hoàn thiện ca tái hiện.

Khóa luận trình bày ngắn: bài toán/phạm vi → cơ sở → thiết kế/xây dựng → thực nghiệm có mức bằng chứng → giới hạn/việc tiếp. Không đổi số tự đỗ cũ thành kết quả thao tác gần. [Hồ sơ và nguồn](DU_LIEU_VA_GIAY_PHEP.md).
