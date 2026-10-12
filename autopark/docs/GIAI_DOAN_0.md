# Biên bản giai đoạn 0 — kế hoạch v3.1

Biên bản này ghi kết quả nghiệm thu giai đoạn 0 (mô phỏng) theo [kế hoạch v3.1](../../KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) mục 4, lập ngày 20/09/2026. Nó cho biết sáu điều kiện chuyển bước đã được kiểm bằng test, phiên mẫu và tệp nào. Số liệu tổng hợp và cách tự kiểm chứng nằm ở [báo cáo giai đoạn 0](../../BAO_CAO_GIAI_DOAN_0.md). Lỗi biên, chiến dịch theo seed, độ bao phủ và giới hạn nằm ở [báo cáo kiểm thử mở rộng](KIEM_THU_DO_BEN_GIAI_DOAN_0.md).

## Tóm tắt

- **Kết luận ngày 20/09/2026: đạt sáu điều kiện chuyển bước ở mức mô phỏng.** Kết quả không chứng nhận xe thật, camera, LiDAR, phanh hay E-stop.
- Đợt ban đầu có 169 test đạt và năm phiên mẫu. Đó là bằng chứng ghi ở các mục bên dưới.
- Kiểm thử độ bền làm tiếp ngay sau đó: bộ test mở rộng lên **220/220 đạt**, các lỗi biên tái hiện được đã sửa, và **2.880 trường hợp theo seed không ghi nhận vi phạm bất biến**. Kết quả dừng/FAULT riêng, độ bao phủ và giới hạn ở [báo cáo kiểm thử mở rộng](KIEM_THU_DO_BEN_GIAI_DOAN_0.md). Năm phiên mẫu được chạy lại bằng mã sau sửa, lưu tại `runs/phase0_after_robustness/`.
- Sau biên bản, dự án có thêm AI, LiDAR, bàn thử và firmware chạy trong bo ảo QEMU (mục cuối). Tính đến 30/09/2026 vẫn chưa nạp bo, chưa liên lạc với bo thật và chưa kiểm chứng phanh. Kết luận của biên bản không đổi.

## Trước khi sửa

Trước đợt làm giai đoạn 0, mã đã có planner, controller tiến/lùi, giao diện sa bàn, footprint (hình bao thân xe) và 155 test chạy đạt. Cấu hình mặc định khi đó còn nhắc xe WPL C24/1:16. Còn thiếu:

- hợp đồng dữ liệu cảm biến đầy đủ;
- tiêm lỗi (fault injection) trễ, nhiễu, mất dữ liệu;
- sửa vật cản khi đang chạy (vật cản chỉ sửa được lúc dừng);
- lưu cấu hình và quỹ đạo để replay (CSV chưa lưu);
- README, repository Git, bộ video/log nghiệm thu và kiểm tra nhãn dataset theo kế hoạch mới.

## Sáu điều kiện chuyển bước

| Điều kiện | Kết quả / bằng chứng |
|---|---|
| Kéo/xoay đích, từ chối đích trong vật cản | Đạt. Các test UI kéo/xoay, `GOAL_INVALID`, kiểm tra toàn thân tại đích. |
| Tiến/lùi, giới hạn lái và đổi chiều | Đạt. Test động học, tracker, planner; các phiên parking/reverse; profile gia tốc/phanh và giới hạn tốc độ đổi lái. |
| Va chạm xét toàn thân | Đạt. Footprint có nhô đầu/đuôi và vùng quét; thêm nới theo độ võng cung để không bỏ sót góc thân lúc xoay. |
| Vật mới vô hiệu đường cũ, dừng trước khi lập lại đường | Đạt. `MAP_CHANGED → STOPPING → STOPPED → WAIT_REPLAN`; cấm planner/reset trong lúc phanh. Test cả tiến và lùi, lập đường từ pose dừng rồi hoàn thành. |
| Xem trước không phát lệnh phần cứng | Đạt. Rollout riêng, không tạo world/feedback/log chạy thực thi của Session; chưa có transport phần cứng. |
| Cấu hình/log đủ tái hiện | Đạt. Snapshot scenario/vehicle/planner/tracker/fault/quỹ đạo, thời gian bước, seed, sự kiện, source, môi trường và kết quả. Replay khớp log/sự kiện trong test và năm phiên mẫu. |

Các mã nguồn chính: `application/session.py`, `simulation/feedback.py`, `domain/sensors.py`, `geometry/footprint.py`, `storage/run_store.py`, `evaluation/phase0.py`, `evaluation/replay.py`, `tests/test_phase0.py`.

## Kiểm chứng đã chạy (đợt ban đầu)

Các kiểm chứng dưới đây là test phần mềm và phiên mô phỏng, chạy trên máy ghi ở mục "Môi trường, dữ liệu và hồ sơ".

- **169 test passed**, báo cáo [pytest.xml](evidence/pytest.xml). Có kiểm tra UI offscreen; ảnh dựng bằng Qt Windows để đọc được font tiếng Việt.
- `pip check`: không có dependency lỗi.
- Năm phiên đã chạy và replay khớp. Video được mở lại để kiểm kích thước và số frame. Tóm tắt bằng máy: `runs/phase0_final_2026-09-20/summary.json`. Thư mục `runs/` bị git-ignore nên không có trong Git; chỉ có khi chép cả thư mục dự án.

| Phiên | Kết quả | Thời gian mô phỏng | Sai số vị trí cuối |
|---|---|---:|---:|
| parking | COMPLETED | 20,265 s | 8,92 mm |
| reverse | COMPLETED | 12,145 s | 8,52 mm |
| noisy | COMPLETED | 12,245 s | 4,78 mm |
| obstacle | STOPPED, không va chạm | 1,345 s | Không đánh giá tới đích vì đã dừng |
| data_loss | STOPPED, không va chạm | 1,490 s | Không đánh giá tới đích vì đã dừng |

Đây là số đo của các ca cụ thể, không phải cam kết sai số trên mọi bản đồ. Profile noisy gồm trễ 40 ms, nhiễu vị trí σ=2 mm, nhiễu yaw σ=0,2°, xác suất mất mẫu 2%, seed=42; profile này chỉ là giả định phần mềm. Thời điểm lỗi ghi trong `events.jsonl`; thời điểm phát hiện và dừng ghi trong `safety_events.json` của từng phiên.

Video đỗ: `runs/phase0_final_2026-09-20/parking/simulation.mp4`. Video vật cản mới: `runs/phase0_final_2026-09-20/obstacle/simulation.mp4`. Hai video này cũng ngoài Git, như tệp tóm tắt ở trên. Ảnh UI: [đang chạy](evidence/ui_running.png), [đã dừng](evidence/ui_stopped.png).

## Môi trường, dữ liệu và hồ sơ

- **Git.** Lúc lập biên bản mới khởi tạo `.git`, chưa commit hay đẩy lên remote. Snapshot source của mỗi phiên có SHA-256 và `source.zip`. Theo `git log` (kiểm 24/09/2026), commit đầu tiên là `bef5695` ngày 21/09/2026, và nhánh `main` đã có trên remote `origin`.
- **Máy.** Python 3.12.10, Windows 11; CPU i7-12700H, GPU RTX 3050 Ti Laptop GPU và Intel Iris Xe; RAM hệ thống báo 68.409.155.584 byte. Đây là thông tin hệ thống, chưa phải benchmark GPU.
- **Package.** Phiên bản cố định tại [requirements-phase0.lock](../requirements-phase0.lock); thông tin máy và package của từng phiên nằm trong `manifest.json`. Đợt này thêm OpenCV cho video và công cụ tải dataset, không nâng hàng loạt dependency cũ. Lúc đó PyTorch chỉ được khai báo tùy chọn cho phần nhận thức, chưa cài và chưa huấn luyện. Về sau PyTorch nằm trong môi trường riêng `.venv-train`, và baseline nhận thức được huấn luyện ngày 21/09/2026 ([HUAN_LUYEN.md](../../HUAN_LUYEN.md)).
- **Cấu hình xe** ghi rõ toàn bộ là giả định, không gắn số đo WPL cho MN300. Bản đồ có loại `unknown`; planner và kiểm va chạm chặn vùng này.
- **Dataset.** [Danh mục 44 bộ/nhánh dataset](../datasets/DANH_MUC_DATASET.md); [biên bản tải/kiểm tra](../datasets/TAI_VA_KIEM_TRA.md). Đã kiểm tra nhãn pixel thực tế; không coi nhãn ô đỗ là nhãn vật cản.
- **Hợp đồng dữ liệu.** Có `VehicleState`, `GoalPose`, `CameraFrame`, `LidarScan`, `Telemetry`, `Costmap`, `Trajectory`, `SafetyEvent`, kèm metadata nguồn/thời gian/valid. Các hợp đồng cảm biến chưa phải driver hoạt động với phần cứng.

## Giới hạn và bước tiếp theo

Nguồn phản hồi là pose mô phỏng có trễ và nhiễu. Mô phỏng chưa dựng ảnh quang học của bốn camera hay scan bằng ray-casting. Preview dùng mô hình lý tưởng; profile lỗi chỉ tác động lên phiên chạy. Vật được chèn quá gần hoặc đè lên thân xe có thể gây FAULT. Việc force-stop sau va chạm chỉ là cơ chế dừng mô phỏng, không tính là tránh va chạm thành công.

Lúc lập biên bản, V1 (bản đầu cần đạt của dự án) chưa có AI được huấn luyện, mapping LiDAR thật, hiệu chuẩn camera/BEV, liên lạc ESP32 hay kiểm chứng phanh. Bước tiếp theo khi đó: giai đoạn 1 tiếp tục với nguồn video/scan lưu sẵn và tiếp nhận cảm biến, đồng thời giữ nguồn giả và replay để tìm lỗi. Không cần mua cảm biến để giải quyết những lỗi phần mềm vừa kiểm chứng.

### Những gì có thêm sau biên bản

- **Tới 24/09/2026:** AI huấn luyện trên WoodScape ([HUAN_LUYEN.md](../../HUAN_LUYEN.md)); bản đồ lưới tĩnh từ LiDAR thật đứng yên ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md)); bàn thử bốn camera + LiDAR + AI ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md)).
- **Tới 25/09/2026** (mã tại `54cb3e2`, đã có trên `origin/main`), về phần mềm:
  - công cụ hiệu chuẩn nội tham, ngoại tham, ROI và BEV nhiều camera ([HIEU_CHUAN_CAMERA.md](HIEU_CHUAN_CAMERA.md), [NGOAI_THAM_VA_ROI.md](NGOAI_THAM_VA_ROI.md), [BEV.md](BEV.md)), mới kiểm trên ảnh tổng hợp, riêng BEV thêm ảnh WoodScape;
  - định vị LiDAR trên bản đồ tĩnh và odometry khớp scan, chỉ chạy offline trên bản ghi ([DINH_VI_LIDAR.md](DINH_VI_LIDAR.md), [SO_SANH_DINH_VI_SLAM.md](SO_SANH_DINH_VI_SLAM.md));
  - giao thức laptop–ESP32-S3 và `VehicleIO`, chỉ chạy với bo mô phỏng và cổng serial giả ([GIAO_THUC_XE.md](GIAO_THUC_XE.md)).
- **29/09/2026:** firmware biên dịch được cho ESP32-S3 bằng PlatformIO ([nhật ký biên dịch](evidence/chuyen_may_20260929/firmware_esp32_20260929.txt)).
- **30/09/2026:** firmware chạy trong bo ảo QEMU, nói chuyện với `SerialVehicleIO` qua `socket://` ([MO_PHONG_FIRMWARE.md](MO_PHONG_FIRMWARE.md)). Đó là giả lập, không phải bo thật.

Tính đến 30/09/2026 vẫn chưa có: hiệu chuẩn của camera thật nào, định vị có tham chiếu độc lập, nạp bo hay liên lạc với bo thật, kiểm chứng phanh. Kết luận của biên bản này (đạt ở mức mô phỏng) không đổi.
