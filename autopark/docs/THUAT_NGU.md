# Thuật ngữ AutoPark — hiểu qua tình huống đỗ xe

Trang này giải thích những từ thường gặp khi tìm hiểu ý tưởng và thuật toán. Không cần nhớ hết từ đầu: chọn nhóm ứng với phần bạn đang đọc. Ví dụ đều xoay quanh một xe mô hình phải lùi vào ô đỗ giữa hai vật cản.

## 1. Mô tả xe và không gian

| Thuật ngữ | Hiểu đơn giản | Ví dụ hoặc điều cần nhớ |
| --- | --- | --- |
| Sa bàn | Khu vực thử có ranh giới, xe, ô đỗ và vật cản | Thay khoảng cách giữa hai hộp là thay một điều kiện của bài toán |
| Tư thế — pose | Vị trí **và** hướng của xe | Đúng chỗ nhưng thân xe nằm chéo vẫn chưa phải đỗ đúng |
| Góc hướng — yaw | Góc quay của thân xe khi nhìn từ trên xuống | Xe hướng sang phải và xe hướng lên trên có hai góc hướng khác nhau |
| Hệ tọa độ | Quy ước về gốc, hướng trục và đơn vị để mô tả vị trí | LiDAR thấy hộp cách mình một đoạn; cần đổi về hệ bản đồ để đặt hộp đúng trong sa bàn |
| Chiều dài cơ sở | Khoảng cách giữa trục bánh trước và trục bánh sau | Cùng góc lái, xe có chiều dài cơ sở lớn hơn thường cần vòng quay rộng hơn |
| Bán kính quay | Bán kính của vòng xe đi theo khi giữ góc lái | Bán kính nhỏ giúp xoay xở trong ô hẹp, nhưng bị giới hạn bởi cơ khí |
| Độ cong — curvature | Mức độ đường uốn cong; bằng nghịch đảo bán kính ở một cung tròn | Đoạn thẳng có độ cong bằng không; cua gắt có độ cong lớn |
| Mô hình động học — kinematic model | Liên hệ tốc độ, góc lái và chuyển động mà chưa mô tả chi tiết lực | Dùng để dự đoán xe đi đâu sau một bước tiến hoặc lùi |
| Mô hình xe đạp — bicycle model | Gộp hai bánh cùng trục thành một bánh đại diện | Cách đơn giản hóa phù hợp để nghiên cứu chuyển động chậm khi bỏ qua trượt ngang |
| Ràng buộc không trượt ngang — nonholonomic constraint | Xe không thể tùy ý dịch sang bên; hướng di chuyển bị bánh xe ràng buộc | Muốn sang ô bên cạnh, xe phải tiến/lùi và quay, không thể trượt ngang như kéo một hình trên giấy |
| Dấu chân thân xe — footprint | Hình chiếm chỗ của toàn thân xe tại một tư thế | Tâm xe không chạm hộp nhưng góc cản trước vẫn có thể chạm |
| Vùng quét thân xe — swept footprint | Hợp của các vùng thân xe chiếm trong suốt chuyển động | Khi lùi và quay, đầu xe có thể văng ra phía bên ngoài đường của đuôi xe |
| Khoảng hở dự phòng | Phần khoảng trống dành thêm cho sai số | Khoảng hở quá ít dễ phụ thuộc vào số đo lý tưởng; quá nhiều có thể khiến không còn đường vào ô |

AutoPark lấy **tâm trục sau** làm điểm mô tả tư thế. Đây là quy ước để tính chuyển động; khi kiểm va chạm vẫn phải xét toàn thân xe.

## 2. Tìm một đường đi được

| Thuật ngữ | Hiểu đơn giản | Vai trò trong bài toán |
| --- | --- | --- |
| Lập đường — planning | Tìm cách đưa xe từ tư thế đầu tới tư thế đích | Phải tránh vật cản và tôn trọng giới hạn quay của xe |
| Trạng thái tìm kiếm | Một tình huống của xe mà thuật toán đang cân nhắc | Cùng một vị trí nhưng quay hai hướng khác nhau có thể cần hai cách đỗ khác nhau |
| Chuyển động mẫu — motion primitive | Một đoạn tiến hoặc lùi với cách đánh lái đã xác định | Ghép nhiều đoạn ngắn thành một phương án đỗ |
| Lattice | Tìm đường bằng mạng các trạng thái nối bằng chuyển động mẫu | Tổ chức việc thử phương án; mật độ trạng thái ảnh hưởng tốc độ tìm và khả năng luồn qua khe |
| A* | Tìm kiếm ưu tiên những hướng có tổng chi phí đã đi và chi phí ước lượng còn lại thấp | Giúp tránh xét mọi phương án theo cùng mức ưu tiên |
| Heuristic | Ước lượng còn khó hoặc xa đích bao nhiêu | Hướng việc tìm kiếm tới vùng có triển vọng; chất lượng và tính chất ước lượng ảnh hưởng kết quả |
| Hybrid A* | Thử chuyển động liên tục của xe nhưng gom trạng thái gần nhau để tìm kiếm hữu hạn | Giữ được ý nghĩa góc hướng và bán kính quay trong khi tìm đường |
| Reeds–Shepp | Các tổ hợp đoạn thẳng, cung trái, cung phải cho xe có thể tiến và lùi | Nối hai tư thế theo giới hạn quay; đường nối vẫn cần kiểm có xuyên vật cản không |
| RRT | Xây một cây chuyển động bằng cách lấy mẫu rồi mở rộng tới vùng mới | Hữu ích khi không gian tìm kiếm phức tạp; một lần chưa tìm thấy chưa chứng minh không tồn tại đường |
| RRT-Connect | Mở rộng hai cây từ hai đầu và thử nối chúng | Tìm một kết nối khả thi giữa tư thế đầu và đích |
| Portfolio | Thử một nhóm cách tìm đường theo thứ tự và thời gian cho phép | Phương án nhanh giải ca dễ trước, phương án khác xử lý ca khó hơn |
| Đường đi và quỹ đạo | Đường mô tả xe đi qua đâu; quỹ đạo còn có thông tin thực hiện như chiều tiến/lùi và tốc độ | Cùng một đường nhưng tốc độ khác nhau có thể tạo sai số bám khác nhau |
| Điểm đổi chiều — cusp | Chỗ xe chuyển giữa tiến và lùi | Bộ bám cần cho xe dừng hẳn trước khi chuyển sang đoạn tiếp theo |

**Tìm được một đường hợp lệ** và **tìm được đường tốt nhất có thể** là hai kết luận khác nhau. AutoPark dùng nhiều chiến lược để tăng cơ hội tìm được đường phù hợp trong thời gian giới hạn. Xem [thuật toán tìm và bám đường](THUAT_TOAN_DUONG_DI.md).

## 3. Bám đường và điều khiển

| Thuật ngữ | Hiểu đơn giản | Ví dụ trong AutoPark |
| --- | --- | --- |
| Giá trị tham chiếu | Giá trị mong muốn tại một điểm trên quỹ đạo | Hướng xe cần có, tốc độ cần chạy hoặc góc lái dự kiến |
| Bám đường — tracking | Điều chỉnh chuyển động để xe thực tế đi gần quỹ đạo đã chọn | Xe lệch sang bên thì bộ bám tính lại góc lái |
| Điều khiển kín vòng — closed loop | Ra lệnh, đo kết quả, so với mong muốn rồi sửa | Chuyển động tiếp theo phụ thuộc số đo mới của xe |
| Điều khiển hở vòng — open loop | Phát lệnh mà không sửa theo kết quả đo được | Giữ lái và ga theo một lịch định sẵn dù xe có thể trượt hoặc chậm hơn dự kiến |
| Thành phần dự kiến — feedforward | Tính trước lệnh từ chuyển động muốn thực hiện | Biết sắp đi theo cung cong nên đặt góc lái phù hợp trước khi sai số lớn |
| Thành phần phản hồi — feedback | Sửa lệnh dựa trên chênh lệch đã đo | Thêm phần sửa vì xe đang lệch ngang hoặc lệch hướng |
| Sai số ngang | Độ lệch sang bên so với đường tham chiếu | Xe song song với đường nhưng nằm bên trái nó |
| Sai số hướng | Độ lệch góc giữa hướng xe và hướng tham chiếu | Xe đứng đúng trên đường nhưng đầu xe quay lệch |
| Hệ số điều khiển — gain | Mức phản ứng của bộ điều khiển với sai số | Tăng quá mạnh có thể làm xe sửa qua sửa lại, nhất là khi dữ liệu trễ |
| Độ trễ — latency | Thời gian từ sự kiện tới số đo hoặc hành động tương ứng | Xe đã đi thêm một đoạn trước khi bộ điều khiển nhận tư thế vừa đo |
| Dao động | Sai số đổi qua đổi lại thay vì giảm ổn định | Xe liên tục lái trái, phải quanh đường cần đi |
| Pure Pursuit | Chọn một điểm phía trước trên đường rồi tính cung để hướng xe tới đó | Là phương án để so sánh; bộ bám hiện tại của AutoPark dùng góc lái dự kiến cộng sửa sai ngang và hướng |

Thành phần dự kiến xử lý hình dạng đường; phản hồi xử lý phần thực tế lệch khỏi dự kiến. Hai phần bổ sung nhau, nhưng vẫn phụ thuộc độ đúng và độ mới của tư thế xe.

## 4. Cảm nhận, bản đồ và định vị

| Thuật ngữ | Hiểu đơn giản | Vì sao cần hoặc giới hạn |
| --- | --- | --- |
| LiDAR | Cảm biến đo khoảng cách theo nhiều hướng bằng laser | Thấy hình học trong mặt phẳng quét; có thể bỏ sót vật thấp hơn mặt phẳng đó |
| Vòng quét — scan | Một tập số đo khoảng cách theo các hướng của LiDAR | Dùng để dựng hình môi trường hoặc so với bản đồ |
| Bản đồ ô lưới — occupancy grid | Chia mặt bằng thành nhiều ô, ghi bằng chứng có vật hoặc trống | Độ phân giải mịn giữ chi tiết tốt hơn nhưng cần nhiều xử lý hơn |
| Costmap | Bản đồ thể hiện mức cản trở hoặc chi phí di chuyển | Trong dự án, các lớp bản đồ phân biệt trống, có vật và chưa biết |
| Định vị — localization | Ước lượng tư thế xe trong một bản đồ đã biết | Cần đúng cả vị trí và góc hướng để bám đường |
| Odometry | Ước lượng thay đổi vị trí và hướng theo chuyển động | Có thể suy từ bánh xe hoặc khớp quét; sai số có thể tích lũy |
| Khớp quét — scan matching | Dịch và xoay một tập điểm để khớp với cảnh đã biết | Giúp suy ra xe đã dịch và quay bao nhiêu |
| ICP | Lặp lại việc ghép các điểm hoặc đường gần nhau rồi điều chỉnh tư thế cho khớp hơn | Có thể tinh chỉnh tốt khi ước lượng đầu đủ gần; dễ khó khăn với cảnh lặp hoặc ít đặc trưng |
| Khớp tương quan — correlative matching | Thử nhiều vị trí và góc rồi chấm mức phù hợp của quét với bản đồ | Giúp tìm các tư thế có triển vọng thay vì chỉ sửa từ một dự đoán duy nhất |
| Trường khả năng — likelihood field | Một cách chấm điểm: điểm đo gần vùng vật cản đã biết được coi là phù hợp hơn | Dùng để so các tư thế ứng viên; điểm cao không tự chứng minh vị trí chắc chắn đúng |
| Nhánh và cận — branch and bound | Chia vùng tìm; bỏ vùng mà ngay cả kết quả tốt nhất có thể cũng không đủ tốt | Tăng tốc tìm kiếm khi cận được lập đúng |
| Tinh chỉnh cục bộ | Bắt đầu từ một nghiệm gần đúng rồi điều chỉnh những lượng nhỏ | Có thể làm tư thế mịn hơn độ chia ô; không bảo đảm sửa được một nghiệm ban đầu rất sai |
| Suy biến | Cảnh không đủ thông tin để phân biệt một hướng chuyển động | Trong hành lang dài, biết khoảng cách tới tường nhưng khó biết đã đi dọc hành lang bao xa |
| Mơ hồ — ambiguity | Nhiều tư thế khác nhau cùng giải thích được số đo | Hai góc phòng giống nhau có thể khớp gần tốt như nhau |
| SLAM | Vừa lập bản đồ vừa định vị khi di chuyển | Luồng định vị hiện tại của AutoPark dựa trên bản đồ cố định, chưa phải SLAM hoàn chỉnh |
| Đóng vòng — loop closure | Nhận ra đã quay lại nơi từng đi qua để hiệu chỉnh sai lệch tích lũy | Thường thuộc hệ SLAM; khác với vòng phản hồi điều khiển |
| Hiệu chuẩn nội tham | Đo đặc tính quang học như tiêu cự, tâm ảnh và độ méo | Để giải thích đúng vị trí các điểm trong ảnh |
| Ngoại tham | Vị trí và hướng của cảm biến so với xe hoặc mặt sàn | Dịch gá camera làm phép đổi tọa độ cũ không còn đúng |
| ROI | Vùng ảnh được chọn để sử dụng | Loại phần thân xe hoặc vùng không phù hợp để suy ra mặt đất |
| BEV — bird’s-eye view | Biểu diễn nhìn từ trên xuống | Đưa thông tin camera lên mặt bằng để đặt cạnh số đo LiDAR |
| Hợp nhất — fusion | Kết hợp bằng chứng từ nhiều nguồn | Cần chung tọa độ, thời gian và cách hiểu chất lượng dữ liệu |
| Dấu thời gian — timestamp | Thời điểm dữ liệu được ghi nhận | Kiểm dữ liệu còn mới và tránh ghép các sự kiện khác thời điểm |
| Phát lại — replay | Dùng dữ liệu đã ghi để quan sát lại cùng một tình huống | Giúp so sánh hai phương án trên đầu vào giống nhau |

Ví dụ: camera nhận ra chiếc hộp trong ảnh. Hiệu chuẩn và phép chiếu giúp đặt bằng chứng đó lên bản đồ, nhưng độ cao của vật, che khuất và sai số gá vẫn ảnh hưởng kết quả. Xem [cảm nhận và định vị](CAM_NHAN_VA_DINH_VI.md).

## 5. AI và cách đánh giá

| Thuật ngữ | Hiểu đơn giản |
| --- | --- |
| Phân đoạn ảnh — segmentation | Gán nhãn cho từng điểm ảnh, chẳng hạn vùng trống hoặc vật cản |
| FREE / BLOCKED / IGNORE | Nhãn vùng trống / vùng có vật / vùng không dùng khi học hoặc chấm |
| UNKNOWN | Chưa đủ bằng chứng để gọi một vùng là trống hoặc có vật |
| Tập dữ liệu — dataset | Các quan sát và thông tin đi kèm, chẳng hạn ảnh cùng nhãn đúng |
| Học / chọn phương án / đánh giá cuối | Ba mục đích của tập train, validation và test; cần tách để tránh tự chấm trên cảnh đã dùng chọn mô hình |
| Đường cơ sở — baseline | Phương án làm mốc để so sánh lợi ích của một cải tiến |
| Ngưỡng — threshold | Mức dùng để chuyển điểm dự đoán thành quyết định |
| Precision vật cản | Trong số điểm ảnh được báo là vật cản, tỷ lệ thực sự đúng |
| Recall vật cản | Trong số điểm ảnh vật cản thật, tỷ lệ được phát hiện |
| F2 | Điểm phối hợp precision và recall, nhấn mạnh recall hơn F1 |
| IoU | Diện tích giao giữa vùng dự đoán và nhãn đúng chia cho diện tích hợp |
| mIoU | Trung bình IoU của các lớp được đánh giá |
| Lệch miền dữ liệu — domain shift | Điều kiện dữ liệu mới khác dữ liệu đã học, như đường phố ngoài trời so với sa bàn trong nhà |
| Rò rỉ dữ liệu — data leakage | Thông tin của tập đánh giá lọt vào quá trình chọn phương án, làm điểm số lạc quan |
| Phân tích bỏ từng thành phần — ablation | Bỏ hoặc thay đúng một thành phần để xem nó đóng góp gì |

Hạ ngưỡng vật cản có thể giảm bỏ sót và tăng báo nhầm. Điểm đánh giá trên ảnh chưa trả lời xe có dừng kịp hay không; còn cần vị trí vật trên bản đồ, độ trễ và quãng dừng.

## 6. Cơ cấu xe, dừng và bằng chứng

| Thuật ngữ | Hiểu đơn giản |
| --- | --- |
| Cơ cấu chấp hành — actuator | Bộ phận biến yêu cầu điều khiển thành chuyển động, như động cơ và servo |
| ESC / servo | Bộ điều tốc động cơ / cơ cấu điều chỉnh góc lái |
| Encoder | Cảm biến đo chuyển động quay, dùng suy ra tốc độ hoặc quãng đường khi biết cơ cấu truyền |
| IMU | Cụm đo chuyển động quán tính như gia tốc và tốc độ quay |
| ToF | Cảm biến suy ra khoảng cách từ thời gian ánh sáng đi và trở về |
| Firmware | Chương trình chạy trên bo điều khiển gần cơ cấu xe |
| Telemetry | Thông tin trạng thái và số đo bo gửi về máy tính |
| Watchdog | Bộ giám sát phát hiện khi một hoạt động không được cập nhật đúng hạn |
| Hạn lệnh | Khoảng thời gian lệnh còn được coi là có giá trị; quá hạn cần xử lý theo quy tắc dừng |
| E-stop | Dừng khẩn; thiết kế mục tiêu có đường ngắt động lực bằng phần cứng |
| Mô phỏng | Dùng mô hình giả định thay một phần hoặc toàn bộ xe và môi trường |
| Bo ảo | Chạy chương trình bo trong trình giả lập; chưa kiểm phản ứng điện và cơ của thiết bị thật |
| Bàn thử | Đo thiết bị thật trong bố trí kiểm soát trước khi tích hợp lên xe |
| Tham chiếu độc lập | Hệ đo dùng chấm kết quả mà không lấy chính đầu ra cần chấm làm đáp án |
| p50 / p95 | Trung vị / mức mà 95% số đo không vượt quá; giúp thấy cả phần thường gặp lẫn các lần chậm |
| Điều kiện chuyển bước | Những điều cần có bằng chứng đạt trước khi làm bước phụ thuộc |
| V1 | Phiên bản mục tiêu đầu tiên với phạm vi và điều kiện nghiệm thu cụ thể |

“Đã gửi yêu cầu dừng”, “đã xác nhận đứng yên” và “đã đo quãng dừng trên xe thật” là ba loại thông tin khác nhau. Xem [hệ thống qua sơ đồ](SO_DO_HE_THONG.md) hoặc [cách tham gia](../../CONTRIBUTING.md) để đặt các thuật ngữ vào một tình huống hoàn chỉnh.
