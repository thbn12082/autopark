# Thuật ngữ AutoPark

Trang này giải thích các từ thường gặp khi đọc mã và tài liệu. Ví dụ dùng xe trên sa bàn; các thông số minh họa giúp hiểu cách hoạt động.

## Xe đang ở đâu và phải đi thế nào?

| Từ trong tài liệu/mã | Hiểu đơn giản | Ví dụ trong dự án |
|---|---|---|
| Sa bàn / scenario | Mô tả khu vực chạy: biên, vị trí xuất phát, chỗ đỗ và vật cản | Một tệp JSON trong `scenarios/` |
| Tư thế / pose | Vị trí **và** hướng của xe | `x=0.6`, `y=1.45`, `yaw_deg=0`: tâm trục sau ở vị trí đó, đầu xe hướng theo chiều +x |
| Yaw | Góc quay của thân xe khi nhìn từ trên xuống | `yaw_deg=90` là quay ngược chiều kim đồng hồ 90° từ +x |
| Hệ tọa độ | Cách chọn gốc và chiều của các trục để ghi vị trí | Hệ xe có x hướng tới đầu xe, y sang trái; hệ bản đồ dùng để đặt xe và vật cản cùng một chỗ |
| Planner / lập đường | Tìm một lộ trình tránh vật cản mà xe có thể đi theo | Các mô-đun trong `planning/` |
| Hybrid A* | Thuật toán thử các chuyển động ngắn của xe để tìm đường | Có tính tới hướng xe và giới hạn đánh lái |
| Reeds–Shepp | Các dạng đường cho xe có thể tiến, lùi và bị giới hạn bán kính quay | Dùng trong các bước tìm hoặc nối đường |
| Portfolio | Thử nhiều cách tìm đường theo thứ tự và ngân sách thời gian | Cách nhanh trước; nếu chưa tìm được thì thử cách tiếp theo |
| Quỹ đạo / trajectory | Đường đi kèm thông tin cần để điều khiển xe dọc đường | Có đoạn tiến, đoạn lùi và tốc độ tham chiếu |
| Cusp / điểm đổi chiều | Chỗ xe chuyển từ tiến sang lùi hoặc ngược lại | Một lần phải dừng rồi lùi vào ô đỗ tạo ra điểm đổi chiều |
| Tracker / bám đường | Liên tục tính tốc độ và góc lái để xe đi theo quỹ đạo | Nhận tư thế hiện tại rồi sửa lệnh ở nhịp tiếp theo |
| Kín vòng / closed loop | Ra lệnh, nhận phản hồi, rồi điều chỉnh lệnh | Xe lệch khỏi đường thì bộ bám đường sửa góc lái |
| Vùng quét thân xe / swept footprint | Toàn bộ diện tích thân xe chiếm trong lúc di chuyển | Tâm xe tránh hộp nhưng đầu xe vẫn có thể quệt hộp khi quay |

**Quy ước cần nhớ khi sửa mã:** tính toán dùng mét, giây và radian. Giao diện thường hiển thị cm và độ. Góc trong JSON dùng hậu tố `_deg`. Tư thế xe lấy tại **tâm trục sau**, không phải tâm hình chữ nhật vẽ xe. Xem [`domain/types.py`](../autopark/domain/types.py).

## LiDAR, camera và bản đồ

| Từ | Hiểu đơn giản | Vì sao cần? |
|---|---|---|
| LiDAR | Cảm biến đo khoảng cách theo nhiều hướng bằng laser | Biết hình dạng vật xung quanh |
| Scan / vòng quét | Một bộ điểm khoảng cách của LiDAR | Là đầu vào để vẽ vật cản hoặc ước lượng vị trí |
| Định vị / localization | So dữ liệu đang đo với bản đồ đã có để tìm vị trí | Xe cần biết đang ở đâu để bám đường |
| Odometry | Ước lượng xe đã dịch chuyển và quay bao nhiêu | Có thể lấy từ encoder hoặc so hai vòng quét LiDAR; sai số có thể tích lũy |
| SLAM | Vừa dựng bản đồ vừa ước lượng vị trí khi di chuyển | Nguồn tư thế LiDAR hiện có của AutoPark dùng bản đồ tĩnh và chưa phải một hệ SLAM hoàn chỉnh |
| Hiệu chuẩn nội tham | Đo đặc tính ống kính: tiêu cự, tâm ảnh, độ méo | Để giải thích đúng vị trí trên ảnh |
| Ngoại tham | Vị trí và hướng của camera/cảm biến so với xe hoặc mặt sàn | Để chuyển kết quả về cùng hệ tọa độ |
| ROI | Phần ảnh được chọn để sử dụng | Loại vùng không phù hợp như thân xe hoặc phần ngoài khu vực quan tâm |
| BEV | Biểu diễn mặt bằng nhìn từ trên xuống (*bird's-eye view*) | Đưa thông tin từ camera lên mặt sàn để ghép với bản đồ |
| Costmap / bản đồ chi phí | Lưới cho biết vùng nào trống, bị chắn hoặc chưa rõ | Giúp kiểm đường có đi qua vùng nguy hiểm không |
| Fusion / hợp nhất | Kết hợp thông tin nhiều nguồn | Vật cản từ LiDAR và camera được đưa về cùng hệ tọa độ |
| Timestamp / dấu thời gian | Thời điểm dữ liệu được ghi nhận | Kiểm dữ liệu còn mới và ghép các nguồn đúng thời điểm |
| Replay / phát lại | Đọc bản ghi cũ như một nguồn dữ liệu | Tái hiện lỗi khi không có thiết bị bên cạnh |

Ví dụ: camera nhìn thấy một chiếc hộp. AI tìm các pixel của hộp; hiệu chuẩn và phép chiếu giúp đặt vùng đó lên bản đồ. Chỉ biết pixel thuộc lớp vật cản chưa đủ để biết hộp cách xe bao nhiêu mét.

## AI và cách đo mô hình

| Từ | Hiểu đơn giản |
|---|---|
| Phân đoạn ảnh / segmentation | Gán một lớp cho từng pixel trong ảnh |
| FREE / BLOCKED / IGNORE | Nhãn vùng trống / vùng bị chắn / bỏ qua khi học hoặc chấm |
| UNKNOWN | Hệ thống chưa đủ thông tin để kết luận vùng đó trống hay bị chắn |
| Dataset | Bộ dữ liệu, thường gồm ảnh và nhãn đúng để học hoặc chấm |
| Train / validation / test | Ba phần dữ liệu: học / chọn mô hình và tham số / đánh giá cuối sau khi chốt |
| Checkpoint | Tệp trọng số mô hình đã lưu, ví dụ `best.pt` |
| Baseline | Mô hình làm mốc để so với các thử nghiệm mới |
| Epoch / batch | Một lượt qua tập train / một nhóm ảnh xử lý cùng lúc |
| Seed | Giá trị khởi tạo ngẫu nhiên; đổi seed giúp xem kết quả có ổn định không |
| IoU / mIoU | Độ trùng giữa vùng dự đoán và nhãn đúng / trung bình độ trùng các lớp |
| Recall vật cản | Trong các pixel vật cản thật, tỷ lệ được nhận ra |
| Precision vật cản | Trong các pixel bị gọi là vật cản, tỷ lệ thực sự đúng |
| F2 | Điểm kết hợp precision và recall, đặt nặng việc giảm bỏ sót hơn F1 |
| Threshold / ngưỡng | Mức xác suất dùng để ra quyết định phân lớp |
| ONNX | Định dạng mô hình để chạy bằng công cụ khác ngoài PyTorch |

Ví dụ: hạ ngưỡng BLOCKED có thể giúp bắt thêm vật cản, đồng thời làm nhiều vùng trống bị báo nhầm. Vì vậy cần xem cả bỏ sót và báo nhầm. Điểm cao trên ảnh đường phố cũng cần được kiểm lại trên ảnh sa bàn. Xem [Huấn luyện AI](../../HUAN_LUYEN.md).

## Laptop, bo và xe

| Từ | Hiểu đơn giản |
|---|---|
| Firmware | Chương trình chạy trên bo điều khiển |
| ESP32-S3 | Bo/vi điều khiển dự kiến nhận lệnh laptop và điều khiển phần cứng xe |
| ESC / servo | Bộ điều khiển động cơ / cơ cấu điều chỉnh góc lái |
| VehicleIO | Lớp phần mềm gửi lệnh và nhận phản hồi xe; tên xuất hiện trong mã Python |
| Telemetry | Bản tin phản hồi của bo: trạng thái và các giá trị theo giao thức |
| Heartbeat | Tín hiệu định kỳ giúp biết phía laptop còn hoạt động |
| Watchdog | Cơ chế phát hiện một tác vụ ngừng hoạt động đúng hạn và xử lý lỗi |
| ARM / DISARM | Cho phép / khóa khả năng điều khiển động lực theo trạng thái firmware |
| Bo mô phỏng | Bản Python mô tả hành vi firmware, chạy trong máy tính |
| Bo ảo QEMU | Firmware C++ chạy trong trình giả lập; xe chuyển động vẫn được mô phỏng phía laptop |
| E-stop | Nút dừng khẩn; thiết kế mục tiêu cắt động lực bằng phần cứng |

Ba chế độ trong ứng dụng:

| Chế độ | Dùng để làm gì? |
|---|---|
| `SIM` | Chạy xe hoàn toàn trong mô phỏng; phù hợp lần đầu |
| `VEHICLE_IO` | Đi qua lớp giao tiếp bo; cần chọn đúng loại bo và nguồn tư thế |
| `OBSERVE` | Đọc/quan sát bo mà không phát lệnh lái; xem quy tắc kết nối trong [Chế độ quan sát](CHE_DO_QUAN_SAT.md) |

## Những thông báo dễ gặp

| Thông báo | Ý nghĩa và hướng kiểm tra |
|---|---|
| `POSE_LOST` | Không có vị trí xe đủ tin cậy. Kiểm nguồn tư thế, dữ liệu LiDAR và bản đồ |
| `POSE_DISAGREE` | Các cách ước lượng chuyển động không khớp nhau. Xem log nguồn tư thế |
| `LIMITS_MISMATCH` | Giới hạn xe cấu hình trên laptop khác giới hạn bo báo về. Đối chiếu cả hai trước khi chạy |
| `UNKNOWN` trên bản đồ | Vùng chưa rõ. Kiểm vùng nhìn, hiệu chuẩn và tuổi dữ liệu |
| START bị từ chối | Một điều kiện trước khi chạy chưa đạt. Đọc lý do trên giao diện; có thể do trạng thái bo, nguồn tư thế hoặc cấu hình |

Các tên này là gợi ý tìm đúng chỗ kiểm tra. Quy tắc đầy đủ ở [Nguồn tư thế LiDAR](NGUON_TU_THE_LIDAR.md) và [VehicleIO](CHE_DO_QUAN_SAT.md).

## Làm việc với mã và kết quả

| Từ | Hiểu đơn giản |
|---|---|
| `.venv` | Thư mục chứa Python và thư viện riêng của dự án |
| Test tự động / pytest | Chương trình kiểm một hành vi có đúng điều mong đợi không / công cụ chạy test Python |
| Smoke test | Nhóm kiểm ngắn để biết một luồng cơ bản có hoạt động |
| Offscreen | Chạy kiểm giao diện mà không hiện cửa sổ; biến `QT_QPA_PLATFORM=offscreen` điều khiển việc này |
| Test host | Biên dịch và chạy lõi firmware C++ trên máy tính |
| JUnit XML | Tệp kết quả test để lưu số đạt, hỏng, bỏ qua và lỗi |
| Commit | Một mốc thay đổi đã lưu trong Git, có mã nhận diện |
| Pull request / PR | Đề nghị gộp thay đổi lên kho chung để người khác xem và góp ý |
| EcoQoS | Chế độ tiết kiệm năng lượng của Windows có thể làm chương trình chạy chậm; ứng dụng có chính sách xử lý riêng |
| MP | Nhãn mô phỏng/giả lập thường dùng trong hồ sơ nghiệm thu |
| V1 / điều kiện chuyển bước | Phiên bản mục tiêu đầu tiên / những điều phải đo và đạt trước khi sang giai đoạn tiếp theo |

Các mã `T1`–`T15`, `LD-1`, `N-V1`, `R1` hay `TC-1` là tên mục trong bộ hồ sơ nghiệm thu. Tra chúng trong [Kịch bản nghiệm thu](KICH_BAN_NGHIEM_THU.md), [Ngưỡng đề xuất](NGUONG_NGHIEM_THU_DE_XUAT.md) và [Tham chiếu trên cao](THAM_CHIEU_TREN_CAO.md) khi làm đúng phép thử đó.

Tiếp theo: [Hướng dẫn chạy](../README.md) hoặc [Hướng dẫn tham gia](../../CONTRIBUTING.md).
