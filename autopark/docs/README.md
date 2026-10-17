# Tìm tài liệu AutoPark

Chọn tài liệu theo việc bạn đang làm. Mỗi nhóm dưới đây có một điểm bắt đầu và các tài liệu để tra sâu hơn.

## Lộ trình cho người mới

| Thứ tự | Tài liệu | Đọc xong bạn làm được gì? |
|---|---|---|
| 1 | [Giới thiệu dự án](../../README.md) | Hiểu mục tiêu và biết phần nào đã chạy được |
| 2 | [Cài đặt và chạy, mục 1–3](../README.md) | Tự chạy một lượt đỗ trên máy tính |
| 3 | [Sơ đồ hệ thống, mục 1–3](SO_DO_HE_THONG.md) | Lần từ thao tác trên giao diện tới tệp mã xử lý |
| 4 | [Hướng dẫn tham gia](../../CONTRIBUTING.md) | Sửa một sa bàn, kiểm kết quả và chuẩn bị thay đổi để gửi |
| Tra khi cần | [Thuật ngữ](THUAT_NGU.md) | Hiểu tên viết tắt và các thông báo thường gặp |

Sau lượt chạy đầu tiên, chọn một mảng ở dưới để học tiếp. [Tổng quan dự án](../../TONG_HOP_DU_AN.md) cho biết các việc còn mở; [kế hoạch](../../KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) giải thích thứ tự triển khai.

## Cài đặt, chạy và chuyển máy

| Tài liệu | Khi nào dùng? |
|---|---|
| [Hướng dẫn chạy](../README.md) | Cài môi trường, mở mô phỏng, chạy test, xử lý lỗi thường gặp |
| [Lệnh nâng cao](LENH_NANG_CAO.md) | Đã chạy được mô phỏng và cần tra lệnh đánh giá, cảm biến hoặc bo ảo |
| [Chuyển máy bàn](CHUYEN_MAY_BAN.md) | Tra lịch sử đổi máy, cấu hình COM, QEMU, EcoQoS và các lỗi đã điều tra |
| [Máy nộp đồ án](MAY_NOP_DO_AN.md) | Chuẩn bị laptop trình diễn, chuyển dữ liệu AI và đo lại hiệu năng |
| [Việc tại chỗ thiết bị](VIEC_TAI_CHO_THIET_BI.md) | Có người ở cạnh cảm biến và cần danh sách việc đo, hiệu chuẩn, kiểm tra |
| [Kiểm kê phần cứng](hardware_inventory.md) | Biết thiết bị đã nhận và thiết bị còn thiếu theo ngày ghi |
| [Điều kiện kết thúc giai đoạn 1](gate_01.md) | Kiểm còn thiếu phép đo nào trước khi chuyển bước |

Các biên bản chuyển máy ghi điều đã xảy ra trên một máy cụ thể. Để cài máy mới, dùng hướng dẫn chạy trước; chỉ mở biên bản khi cần đối chiếu một lỗi hoặc một số đo.

## Mô phỏng, tìm đường và bám đường

**Bắt đầu:** [Sơ đồ hệ thống, mục 2–3](SO_DO_HE_THONG.md). Phần này giải thích một phiên đỗ và chỉ tới mã trong `application/`, `planning/`, `control/`, `simulation/`.

| Tài liệu | Nội dung |
|---|---|
| [Báo cáo giai đoạn 0](../../BAO_CAO_GIAI_DOAN_0.md) | Kết quả mô phỏng ngày 20/09/2026 và điều kiện đã đạt |
| [Đối chiếu giai đoạn 0](GIAI_DOAN_0.md) | Kiểm từng điều kiện chuyển bước |
| [Kiểm thử độ bền](KIEM_THU_DO_BEN_GIAI_DOAN_0.md) | Các ca khó, lỗi biên và cách tìm lỗi |
| [Độ nhạy kích thước xe](DO_NHAY_KICH_THUOC_XE.md) | Vì sao thay chiều dài, bề rộng hoặc góc lái làm kết quả tìm đường thay đổi |

<a id="lidar-va-vi-tri-xe"></a>
## LiDAR và vị trí xe

**Bắt đầu:** [Thử LiDAR C1](GIAI_DOAN_1_LIDAR.md). LiDAR đo khoảng cách; phần định vị dùng các khoảng cách đó để ước lượng xe ở đâu trên bản đồ.

| Tài liệu | Nội dung |
|---|---|
| [Thử LiDAR C1](GIAI_DOAN_1_LIDAR.md) | Kết nối, đọc, ghi, đo độ lặp lại và lỗi driver đã gặp |
| [Định vị trên bản đồ](DINH_VI_LIDAR.md) | Tìm vị trí và hướng của LiDAR bằng cách so một vòng quét với bản đồ |
| [Nguồn tư thế LiDAR](NGUON_TU_THE_LIDAR.md) | Đưa vị trí ước lượng vào phiên đỗ; điều kiện dùng và lý do từ chối |
| [So sánh các cách định vị](SO_SANH_DINH_VI_SLAM.md) | Phân biệt bản đồ cố định, odometry và SLAM; phương án đã chọn cho dự án |

Cổng LiDAR nằm trong [configs/thiet_bi.json](../configs/thiet_bi.json). Phép đo trên bàn và định vị xe đang di chuyển có yêu cầu khác nhau; trạng thái của từng phần được ghi riêng trong các tài liệu trên.

<a id="camera-va-ai"></a>
## Camera và AI

**Bắt đầu:** chọn [thử camera](GIAI_DOAN_1_CAMERA.md) nếu làm thiết bị, hoặc [huấn luyện AI](../../HUAN_LUYEN.md) nếu làm mô hình. Luồng đưa camera vào phiên đỗ là: có ảnh ổn định → hiệu chuẩn → xác định vị trí camera → chiếu về mặt sàn → kiểm kết quả AI.

| Tài liệu | Nội dung |
|---|---|
| [Thử camera USB](GIAI_DOAN_1_CAMERA.md) | Độ phân giải, tốc độ khung hình và kiểm ảnh hỏng |
| [Sơ đồ USB](usb_topology.md), [chế độ ảnh](camera_modes.csv) | Xác định camera/cổng và cấu hình đã thử |
| [Hiệu chuẩn camera](HIEU_CHUAN_CAMERA.md) | Đo đặc tính ống kính để xử lý méo ảnh |
| [Thư mục hiệu chuẩn](../calibration/README.md) | Bảng in, marker và nơi lưu tệp kết quả |
| [Ngoại tham và ROI](NGOAI_THAM_VA_ROI.md) | Vị trí camera so với xe và phần ảnh được phép sử dụng |
| [BEV](BEV.md) | Chuyển thông tin từ ảnh camera sang mặt bằng nhìn từ trên xuống |
| [AI tạo vật cản](AI_DIEU_KHIEN_XE.md) | Điều kiện đưa kết quả AI vào phiên đỗ và cách dừng khi dữ liệu không dùng được |
| [Gán nhãn sa bàn](GAN_NHAN_SA_BAN.md) | Tạo nhãn để đo mô hình đúng/sai trên ảnh của dự án |
| [Huấn luyện AI](../../HUAN_LUYEN.md) | Dữ liệu, mô hình tham chiếu, các kết quả đã đo và lệnh chạy lại |
| [Chuẩn bị phần cảm biến](GIAI_DOAN_1_CHUAN_BI.md) | Các nguồn dữ liệu giả/phát lại, ROI, bản đồ vật cản và công cụ đã có |

## Kết hợp cảm biến và lưu phiên

| Tài liệu | Nội dung |
|---|---|
| [Bàn thử bốn camera + LiDAR + AI](GIAI_DOAN_2_BAN_THU.md) | Chạy các nguồn cùng nhau và đo tốc độ, độ trễ |
| [Ghi và phát lại](GHI_PHAT_LAI_BAN_THU.md) | Lưu dữ liệu để tái hiện vấn đề khi không có thiết bị bên cạnh; mục 9 nói về ghi ngay trong phiên đỗ |
| [Hợp nhất cảm biến](GIAI_DOAN_3_CHUAN_BI.md) | Đưa vật cản từ các nguồn về cùng hệ tọa độ |

## Xe, bo điều khiển và nguồn điện

**Bắt đầu:** [Sơ đồ hệ thống, mục 6](SO_DO_HE_THONG.md), rồi chọn tài liệu phù hợp. Trong hồ sơ hiện có, firmware đã chạy trên máy tính và QEMU; phần xe/bo thật còn chờ thiết bị.

| Tài liệu | Nội dung |
|---|---|
| [VehicleIO và chế độ quan sát](CHE_DO_QUAN_SAT.md) | Các chế độ chạy, kiểm trước START, dừng, lỗi bo và log |
| [Giao thức laptop–bo](GIAO_THUC_XE.md) | Byte, bản tin, lệnh và phản hồi; dùng khi sửa giao tiếp |
| [README firmware](../firmware/esp32_vehicle/README.md) | Cấu trúc C++, test trên máy tính và biên dịch bằng PlatformIO |
| [Bo ảo QEMU](MO_PHONG_FIRMWARE.md) | Chạy firmware trong giả lập; điều kiện cài và giới hạn phép thử |
| [Đo xe MN300](GIAI_DOAN_4_CHUAN_BI.md), [phiếu kiểm kê](mn300_inventory.md) | Đo thông số xe và thay các giá trị giả định |
| [Nguồn điện và dừng khẩn](GIAI_DOAN_6_CHUAN_BI.md) | Thiết kế dự kiến và các phép thử cần làm trên phần cứng |

## Đánh giá kết quả và viết khóa luận

| Tài liệu | Nội dung |
|---|---|
| [Kịch bản nghiệm thu](KICH_BAN_NGHIEM_THU.md) | 37 kịch bản dự kiến, cách đo và công cụ; chín sa bàn đỗ mẫu ở `scenarios/nghiem_thu/` |
| [Ngưỡng nghiệm thu đề xuất](NGUONG_NGHIEM_THU_DE_XUAT.md) | Các mức đạt/chưa đạt cần thống nhất trước khi đo |
| [Tham chiếu từ camera trên cao](THAM_CHIEU_TREN_CAO.md) | Đo vị trí xe độc lập để so với kết quả của hệ thống |
| [Dàn ý khóa luận](DAN_Y_KHOA_LUAN.md) | Chương, hình, bảng và những kết luận cần bằng chứng |
| [Bằng chứng đã lưu](evidence/) | Log, kết quả test, hình và báo cáo rút gọn theo từng đợt |

## Dữ liệu và giấy phép

| Tài liệu | Nội dung |
|---|---|
| [Danh mục dataset](../datasets/DANH_MUC_DATASET.md) | Các bộ ảnh, nhãn và mục đích sử dụng |
| [Tải và kiểm dữ liệu](../datasets/TAI_VA_KIEM_TRA.md) | Chuẩn bị các tệp lớn nằm ngoài Git |
| [Biên bản tải dữ liệu](../datasets/TRANG_THAI_TAI_DAY_DU.md) | Kết quả trên máy đã tải tại ngày ghi; dùng để đối chiếu |
| [Metadata WoodScape](../datasets/woodscape_metadata/README.md) | Thông tin gốc đi cùng bộ dữ liệu |
| [Hồ sơ giấy phép](GIAY_PHEP_DU_LIEU.md) | Điều khoản, quyết định sử dụng và những điểm chưa được xác nhận |

## Cách tìm bằng chứng của một kết quả

Các tệp trong [evidence/](evidence/) được nhóm theo lần thử. Đầu tiên tìm con số trong [Tổng quan, mục 7](../../TONG_HOP_DU_AN.md), sau đó mở đúng thư mục nguồn:

| Nhóm thư mục | Loại kết quả |
|---|---|
| Gốc `evidence/`, `hard_cases/` | Mô phỏng giai đoạn 0 |
| `camera/`, `lidar/`, `rig/`, `may_ban/`, `ke_hoach/` | Thử cảm biến, bàn thử và đối chiếu kế hoạch |
| `chuyen_may_20260929/` | Kiểm máy sau khi chuyển |
| `mo_phong_20260930/`, `bien_tap_20261001/`, `cong_cu_20261002/`, `dot2_20261006/` | Kiểm mã ở từng commit |
| `ecoqos_giao_dien_02102026/`, `ecoqos_giao_dien_02102026_lan2/`, `ecoqos_chay_02102026/` | Ảnh hưởng chế độ tiết kiệm năng lượng của Windows |
| `thiet_bi_20261002/`, `bo_ao_ui_20261002/` | Chạy bàn thử và giao diện với bo ảo |
| `su_co_thoat_20261006/` | Điều tra tiến trình bị dừng hoặc thoát bất thường |

Bản ghi đầy đủ, video và trọng số AI thường nằm trong `runs/` ngoài Git. Một đường dẫn `runs/...` trong báo cáo là tên dữ liệu cần xin hoặc tạo lại. Hướng dẫn của phép thử sẽ cho biết cách tạo dữ liệu tương ứng.

## Khi bạn sửa tài liệu

Viết để người kế tiếp làm được việc: nói mục đích trước, đưa các bước thực hiện, mô tả kết quả mong đợi, rồi chỉ chỗ xử lý lỗi. Ghi rõ thư mục chạy lệnh và tệp cần có. Giải thích thuật ngữ ở lần xuất hiện đầu hoặc dẫn tới [bảng thuật ngữ](THUAT_NGU.md).

Khi ghi kết quả, kèm ngày, mã commit, máy/môi trường, lệnh chạy và nguồn dữ liệu. Ghi rõ đó là thử phần mềm, mô phỏng, giả lập bo hay đo thiết bị thật. Nếu chỉ chạy một nhóm test, ghi tên nhóm.

Giữ số mục của tài liệu đã được mã hoặc tài liệu khác trích dẫn. Đặc biệt, các dòng `| N-` trong [bảng ngưỡng](NGUONG_NGHIEM_THU_DE_XUAT.md) và bảng mục 4 của [kịch bản nghiệm thu](KICH_BAN_NGHIEM_THU.md) được test đọc trực tiếp; sửa những bảng này cần kiểm test liên quan.

Tệp đo gốc trong `evidence/` là hồ sơ của lần thử. Khi có kết quả mới, lưu bằng chứng mới và cập nhật phần diễn giải. Các bản tài liệu trước có thể tra trong lịch sử Git: `8be69fb` trước lần biên tập này, `ff4a018` trước đợt 30/09, `9d68257` trước đợt 26/09. Biên bản cũ dẫn tên bước không còn ở hiện tại có thể tra lại đúng bản đó.
