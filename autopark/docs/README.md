# Đọc AutoPark theo bài toán và ý tưởng

Bộ tài liệu này giải thích cách một chiếc xe mô hình tự đỗ: **vấn đề cần giải quyết → ý tưởng của thuật toán → lý do lựa chọn → điều kiện áp dụng → giới hạn cần kiểm**.

Nếu mới tiếp cận, bắt đầu bằng [ý tưởng toàn dự án](../../README.md), rồi đi theo một lượt đỗ ở [bài giải thích tổng thể](../README.md). Sau đó chọn phần khiến bạn muốn hiểu sâu hơn.

## Lộ trình đọc

| Câu hỏi của người đọc | Tài liệu nên đọc |
|---|---|
| Tại sao tự đỗ khó hơn nối hai điểm? | [Giới thiệu bài toán](../../README.md) |
| Các phần phối hợp ra sao trong một lần đỗ? | [Một lần đỗ xe](../README.md) |
| Xe biết có vật cản và biết mình ở đâu bằng cách nào? | [Cảm nhận và định vị](CAM_NHAN_VA_DINH_VI.md) |
| Vì sao cần nhiều cách tìm đường, rồi còn phải kiểm bám? | [Thuật toán đường đi](THUAT_TOAN_DUONG_DI.md) |
| AI làm phần nào và vì sao chọn mô hình/ngưỡng hiện tại? | [AI trong bài toán đỗ xe](../../HUAN_LUYEN.md) |
| Muốn xem hệ thống bằng hình thay vì đọc liên tục? | [Bộ lưu đồ hệ thống](SO_DO_HE_THONG.md) |
| Những lựa chọn này đã được chứng minh tới đâu? | [Tổng hợp lựa chọn và giới hạn](../../TONG_HOP_DU_AN.md) |
| Làm thế nào đóng góp một cải tiến có căn cứ? | [Cách tham gia giải quyết bài toán](../../CONTRIBUTING.md) |

[Từ điển thuật ngữ](THUAT_NGU.md) dùng các ví dụ trong bài toán đỗ xe để giải thích những tên gọi thường gặp.

## Toàn cảnh trong một hình

![Các phần cảm nhận, định vị, lập đường và điều khiển nối thành một vòng phản hồi](images/toan-canh.svg)

Một thay đổi ở phần cảm nhận có thể làm thay đổi đường đi; một sai số điều khiển có thể khiến khoảng hở hình học không còn đủ. Khi đọc từng thuật toán, hãy giữ mối liên hệ này thay vì xem các phần như những lời giải độc lập.

<a id="lidar-va-vi-tri-xe"></a>
## Cảm nhận và định vị: thông tin nào đáng tin để xe hành động?

Bài chính là [Cảm nhận và định vị](CAM_NHAN_VA_DINH_VI.md). Nó giải thích lưới chiếm chỗ, khớp vòng quét với bản đồ, dự đoán chuyển động và cách nhận ra ước lượng mơ hồ.

| Muốn tra sâu hơn | Hồ sơ chuyên đề |
|---|---|
| LiDAR C1 đã đo và thử những gì? | [Thử LiDAR](GIAI_DOAN_1_LIDAR.md) |
| Cách chấm một tư thế ứng viên | [Định vị trên bản đồ](DINH_VI_LIDAR.md) |
| Đưa vị trí ước lượng vào vòng điều khiển | [Nguồn tư thế LiDAR](NGUON_TU_THE_LIDAR.md) |
| Vì sao chưa dùng SLAM đầy đủ? | [So sánh các cách định vị](SO_SANH_DINH_VI_SLAM.md) |
| Vì sao thời gian và cùng hệ tọa độ quan trọng? | [Hợp nhất cảm biến](GIAI_DOAN_3_CHUAN_BI.md), [bàn thử](GIAI_DOAN_2_BAN_THU.md) |

<a id="camera-va-ai"></a>
## Camera và AI: từ ảnh tới thông tin vật cản

Bài chính là [AI trong bài toán đỗ xe](../../HUAN_LUYEN.md). Nó đặt câu hỏi vì sao phân đoạn ảnh phù hợp, mô hình học điều gì, chọn ngưỡng thay đổi hành vi ra sao và vì sao phải đánh giá lại trên sa bàn.

| Muốn tra sâu hơn | Hồ sơ chuyên đề |
|---|---|
| Vì sao pixel chưa có khoảng cách đáng tin? | [Hiệu chuẩn camera](HIEU_CHUAN_CAMERA.md), [ngoại tham và ROI](NGOAI_THAM_VA_ROI.md) |
| Chuyển ảnh về mặt sàn và xử lý che khuất | [BEV](BEV.md) |
| Khi nào dự đoán ảnh được phép ảnh hưởng đến đường đi? | [AI tạo vật cản](AI_DIEU_KHIEN_XE.md) |
| Nhãn đánh giá cần độc lập với mô hình như thế nào? | [Gán nhãn sa bàn](GAN_NHAN_SA_BAN.md) |
| Ảnh thật khác dữ liệu huấn luyện ở đâu? | [Thử camera](GIAI_DOAN_1_CAMERA.md), [danh mục dữ liệu](../datasets/DANH_MUC_DATASET.md) |
| Phạm vi sử dụng dữ liệu và mô hình | [Hồ sơ giấy phép](GIAY_PHEP_DU_LIEU.md) |

## Tìm đường và điều khiển: hình học phải đi cùng khả năng thực hiện

Bài chính là [Thuật toán đường đi](THUAT_TOAN_DUONG_DI.md). Nên hiểu mô hình chuyển động trước khi đọc Hybrid A*, Reeds–Shepp, RRT-Connect và cách thử nhiều bộ tìm đường.

| Muốn tra sâu hơn | Hồ sơ chuyên đề |
|---|---|
| Vì sao kích thước/góc lái thay đổi khả năng vào ô? | [Độ nhạy kích thước xe](DO_NHAY_KICH_THUOC_XE.md) |
| Những tình huống làm bộ tìm đường gặp khó | [Kiểm thử độ bền](KIEM_THU_DO_BEN_GIAI_DOAN_0.md) |
| Các kết quả mô phỏng ban đầu | [Báo cáo giai đoạn 0](../../BAO_CAO_GIAI_DOAN_0.md), [đối chiếu giai đoạn 0](GIAI_DOAN_0.md) |
| Vì sao lệnh gửi đi cần phản hồi và hạn sử dụng? | [Giao thức xe](GIAO_THUC_XE.md), [các chế độ điều khiển](CHE_DO_QUAN_SAT.md) |
| Giả lập firmware chứng minh được điều gì? | [Mô phỏng firmware](MO_PHONG_FIRMWARE.md) |

## An toàn, đánh giá và lộ trình

Bắt đầu ở mục 7–9 của [Lưu đồ hệ thống](SO_DO_HE_THONG.md). Sau đó dùng các hồ sơ dưới đây để phân biệt ý tưởng, tiêu chí và bằng chứng.

| Câu hỏi | Tài liệu |
|---|---|
| Vì sao dừng cần nhiều lớp? | [Nguồn và dừng](GIAI_DOAN_6_CHUAN_BI.md) |
| Vì sao phải đo lại mô hình xe? | [Đo xe MN300](GIAI_DOAN_4_CHUAN_BI.md) |
| Đỗ “được” cần đo những gì? | [Kịch bản nghiệm thu](KICH_BAN_NGHIEM_THU.md), [ngưỡng đề xuất](NGUONG_NGHIEM_THU_DE_XUAT.md) |
| Làm sao biết hệ thống định vị đúng? | [Tham chiếu từ camera trên cao](THAM_CHIEU_TREN_CAO.md) |
| Vì sao các phần phải được chứng minh theo thứ tự? | [Lộ trình triển khai](../../KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) |
| Trình bày nghiên cứu thành một lập luận thế nào? | [Dàn ý khóa luận](DAN_Y_KHOA_LUAN.md) |

## Tra hình theo ý tưởng

Các hình là SVG, có thể mở lớn mà vẫn rõ chữ. Mỗi hình được đặt cạnh phần giải thích trong bài liên quan.

| Nhóm | Hình |
|---|---|
| Hệ thống | [Toàn cảnh](images/toan-canh.svg), [một lượt đỗ](images/luong-do-xe.svg) |
| Ràng buộc xe | [Thân xe và vùng quét](images/xe-va-rang-buoc.svg) |
| Tìm đường | [Tìm đường](images/lap-duong.svg), [thứ tự các bộ tìm](images/thu-tu-tim-duong.svg), [kiểm bám](images/kiem-duong.svg) |
| Điều khiển | [Vòng sửa sai](images/bam-duong.svg), [quyết định dừng](images/an-toan.svg) |
| Cảm biến | [Hai nguồn thông tin](images/cam-nhan.svg), [định vị](images/dinh-vi.svg), [hiệu chuẩn và BEV](images/hieu-chuan-bev.svg), [hợp nhất](images/hop-nhat.svg) |
| AI | [Từ ảnh tới vật cản](images/ai-vat-can.svg), [đánh giá mô hình](images/danh-gia-ai.svg) |
| Nghiên cứu | [Các mức bằng chứng](images/bang-chung.svg), [lộ trình tích hợp](images/lo-trinh.svg), [chu trình cải tiến](images/chu-trinh-cai-tien.svg) |

## Hồ sơ kết quả

[Thư mục bằng chứng](evidence/) giữ các phép thử theo từng đợt. [Biên bản chuyển máy](CHUYEN_MAY_BAN.md) và [kiểm kê phần cứng](hardware_inventory.md) cho biết điều kiện thử và thiết bị ở thời điểm ghi. [Ghi và phát lại](GHI_PHAT_LAI_BAN_THU.md) giải thích việc giữ cùng dữ liệu để so các phương án.

Các hồ sơ có ngày dùng để kiểm lại một nhận định, không nên suy rộng số đo của một máy hay một tình huống thành kết luận cho toàn bộ xe tự đỗ. Khi các bài cũ trích số mục đã đổi, tra bản tài liệu tại thời điểm được dẫn.
