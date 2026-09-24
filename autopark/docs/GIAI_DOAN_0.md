# Biên bản giai đoạn 0 — kế hoạch v3.1

Ngày: 20/09/2026. **Kết luận: ĐẠT sáu điều kiện chuyển bước ở mức mô phỏng.** Kết quả không chứng nhận xe thật, camera, LiDAR, phanh hay E-stop.

**Bổ sung kiểm thử độ bền:** đã mở rộng lên **220/220 test**, sửa các lỗi biên được tái hiện và chạy **2.880 trường hợp theo seed, không ghi nhận vi phạm bất biến**. Xem [báo cáo kiểm thử mở rộng](KIEM_THU_DO_BEN_GIAI_DOAN_0.md), gồm kết quả dừng/FAULT riêng, độ bao phủ và giới hạn. Các số 169 test và năm phiên bên dưới là bằng chứng của đợt ban đầu; bản chạy sau sửa nằm tại `runs/phase0_after_robustness/`.

## Trước khi sửa

Code có planner, controller tiến/lùi, giao diện sa bàn, footprint và 155 test chạy đạt. Chưa có đủ hợp đồng dữ liệu cảm biến; chưa có fault injection trễ/nhiễu/mất dữ liệu; vật cản chỉ sửa lúc dừng; CSV chưa lưu cấu hình/quỹ đạo để replay. Cấu hình mặc định còn nhắc WPL C24/1:16. Chưa có README, repository Git, bộ video/log nghiệm thu và kiểm tra nhãn dataset theo kế hoạch mới.

## Sáu điều kiện chuyển bước

| Điều kiện | Kết quả / bằng chứng |
|---|---|
| Kéo/xoay đích, từ chối đích trong vật cản | ĐẠT: các test UI kéo/xoay, `GOAL_INVALID`, kiểm tra toàn thân tại đích. |
| Tiến/lùi, giới hạn lái và đổi chiều | ĐẠT: test động học, tracker, planner; các phiên parking/reverse; profile gia tốc/phanh và giới hạn tốc độ đổi lái. |
| Va chạm xét toàn thân | ĐẠT: footprint có nhô đầu/đuôi, vùng quét; thêm nới theo độ võng cung để không bỏ sót góc thân lúc xoay. |
| Vật mới vô hiệu đường cũ, dừng trước lập lại đường | ĐẠT: `MAP_CHANGED → STOPPING → STOPPED → WAIT_REPLAN`; cấm planner/reset trong lúc phanh. Test cả tiến và lùi, lập đường từ pose dừng rồi hoàn thành. |
| Xem trước không phát lệnh phần cứng | ĐẠT: rollout riêng, không tạo world/feedback/log chạy thực thi của Session, chưa có transport phần cứng. |
| Cấu hình/log đủ tái hiện | ĐẠT: snapshot scenario/vehicle/planner/tracker/fault/quỹ đạo, thời gian bước, seed, sự kiện, source, môi trường và kết quả. Replay khớp log/sự kiện trong test và năm phiên mẫu. |

Các mã nguồn chính: `application/session.py`, `simulation/feedback.py`, `domain/sensors.py`, `geometry/footprint.py`, `storage/run_store.py`, `evaluation/phase0.py`, `evaluation/replay.py`, `tests/test_phase0.py`.

## Kiểm chứng thực tế

- **169 test passed**, báo cáo [pytest.xml](evidence/pytest.xml). Có kiểm tra UI offscreen; ảnh dựng bằng Qt Windows để đọc được font tiếng Việt.
- `pip check`: không có dependency lỗi.
- Năm phiên đã chạy và replay khớp; video được mở lại, kiểm tra kích thước và số frame. [Tóm tắt bằng máy](../runs/phase0_final_2026-09-20/summary.json).

| Phiên | Kết quả | Thời gian mô phỏng | Sai số vị trí cuối |
|---|---|---:|---:|
| parking | COMPLETED | 20,265 s | 8,92 mm |
| reverse | COMPLETED | 12,145 s | 8,52 mm |
| noisy | COMPLETED | 12,245 s | 4,78 mm |
| obstacle | STOPPED, không va chạm | 1,345 s | Không đánh giá tới đích vì đã dừng |
| data_loss | STOPPED, không va chạm | 1,490 s | Không đánh giá tới đích vì đã dừng |

Đây là số đo của các ca cụ thể, không phải cam kết sai số trên mọi bản đồ. Profile noisy: trễ 40 ms, nhiễu vị trí σ=2 mm, nhiễu yaw σ=0,2°, xác suất mất mẫu 2%, seed=42. Profile chỉ là giả định phần mềm. Bản ghi thời điểm lỗi nằm trong `events.jsonl`, thời điểm phát hiện/dừng trong `safety_events.json` của từng phiên.

Video đỗ: [simulation.mp4](../runs/phase0_final_2026-09-20/parking/simulation.mp4). Video vật cản mới: [simulation.mp4](../runs/phase0_final_2026-09-20/obstacle/simulation.mp4). Ảnh UI: [đang chạy](evidence/ui_running.png), [đã dừng](evidence/ui_stopped.png).

## Môi trường, dữ liệu và hồ sơ

- Đã khởi tạo `.git`; chưa commit hoặc đẩy remote. Snapshot source mỗi phiên có SHA-256 và `source.zip`. *Cập nhật 24/09/2026: theo `git log`, commit đầu tiên là `bef5695` ngày 21/09/2026; nhánh `main` đã có trên remote `origin`.*
- Python 3.12.10, Windows 11; CPU i7-12700H, GPU RTX 3050 Ti Laptop GPU và Intel Iris Xe; RAM hệ thống báo 68.409.155.584 byte. Đây là thông tin hệ thống, chưa phải benchmark GPU.
- Phiên bản package cố định tại [requirements-phase0.lock](../requirements-phase0.lock); thông tin máy/package từng phiên trong `manifest.json`. Đã thêm OpenCV cho video và công cụ tải dataset; không nâng hàng loạt dependency cũ. PyTorch khai báo tùy chọn cho perception, chưa cài/huấn luyện. *Cập nhật 24/09/2026: PyTorch nằm trong môi trường riêng `.venv-train`; baseline nhận thức huấn luyện ngày 21/09/2026, xem [HUAN_LUYEN.md](../../HUAN_LUYEN.md).*
- Cấu hình xe hiện ghi rõ toàn bộ là giả định, không gắn số đo WPL cho MN300. Bản đồ có loại `unknown`, planner và collision chặn vùng này.
- [Danh mục 44 bộ/nhánh dataset](../datasets/DANH_MUC_DATASET.md); [biên bản tải/kiểm tra](../datasets/TAI_VA_KIEM_TRA.md). Đã kiểm tra nhãn pixel thực tế; không coi nhãn ô đỗ là nhãn vật cản.
- Có hợp đồng `VehicleState`, `GoalPose`, `CameraFrame`, `LidarScan`, `Telemetry`, `Costmap`, `Trajectory`, `SafetyEvent`; metadata nguồn/thời gian/valid. Các hợp đồng cảm biến chưa phải driver hoạt động với phần cứng.

## Giới hạn và bước tiếp theo

Nguồn phản hồi là pose mô phỏng có trễ/nhiễu, chưa mô phỏng quang học bốn camera hoặc scan ray-casting. Preview dùng mô hình lý tưởng; profile lỗi chỉ tác động phiên chạy. Vật được chèn quá gần hoặc đè thân xe có thể gây FAULT; việc force-stop sau va chạm chỉ là cơ chế dừng mô phỏng, không tính là tránh va chạm thành công.

V1 chưa có AI được huấn luyện, mapping LiDAR thật, hiệu chuẩn camera/BEV, liên lạc ESP32 hay kiểm chứng phanh. Giai đoạn 1 tiếp tục nguồn video/scan lưu sẵn và tiếp nhận cảm biến; giữ nguồn giả và replay để tìm lỗi. Không cần mua cảm biến để giải quyết những lỗi phần mềm vừa kiểm chứng.

*Cập nhật 24/09/2026:* sau biên bản này đã có AI huấn luyện trên WoodScape ([HUAN_LUYEN.md](../../HUAN_LUYEN.md)), bản đồ lưới tĩnh từ LiDAR thật đứng yên ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md)) và bàn thử bốn camera + LiDAR + AI ([GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md)). Vẫn chưa có hiệu chuẩn camera/BEV, định vị/SLAM, liên lạc ESP32 hay kiểm chứng phanh. Kết luận của biên bản này (đạt ở mức mô phỏng) không đổi.

*Cập nhật 25/09/2026* (mọi việc tới khuya 24/09 đã commit và push, `origin/main` = `54cb3e2`): câu "vẫn chưa có…" ở trên cần nói rõ hơn. Về phần mềm nay đã có: công cụ hiệu chuẩn nội tham, ngoại tham, ROI và BEV nhiều camera ([HIEU_CHUAN_CAMERA.md](HIEU_CHUAN_CAMERA.md), [NGOAI_THAM_VA_ROI.md](NGOAI_THAM_VA_ROI.md), [BEV.md](BEV.md)), mới kiểm trên ảnh tổng hợp (BEV thêm ảnh WoodScape); định vị LiDAR trên bản đồ tĩnh và odometry khớp scan, chỉ chạy offline trên bản ghi ([DINH_VI_LIDAR.md](DINH_VI_LIDAR.md), [SO_SANH_DINH_VI_SLAM.md](SO_SANH_DINH_VI_SLAM.md)); giao thức laptop–ESP32-S3 và `VehicleIO`, chỉ với bo mô phỏng và cổng serial giả ([GIAO_THUC_XE.md](GIAO_THUC_XE.md)). Vẫn chưa có: hiệu chuẩn của camera thật nào, định vị có tham chiếu độc lập, liên lạc với bo thật (firmware C++ chưa biên dịch), kiểm chứng phanh.
