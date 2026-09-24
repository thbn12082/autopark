# AutoPark — mã nguồn xe mô hình tự đỗ theo kế hoạch v3.1

> **Ghi công bắt buộc theo giấy phép dữ liệu:** nghiên cứu nhận thức trong dự án này được thực hiện với **Valeo WoodScape Dataset** (<https://woodscape.valeo.com>, [repo](https://github.com/valeoai/WoodScape)). Điều khoản Valeo yêu cầu hiển thị rõ ghi công này trong mọi tài liệu công bố có nhắc tới nghiên cứu dùng bộ dữ liệu. Bảng giấy phép đầy đủ và vấn đề cần xử lý: [docs/GIAY_PHEP_DU_LIEU.md](docs/GIAY_PHEP_DU_LIEU.md).

Mô phỏng xe đạp động học, đặt/xoay đích, Hybrid A*/Reeds–Shepp, bám quỹ đạo tiến/lùi và dừng khi bản đồ/phản hồi không còn hợp lệ. Đây là phần mềm mô phỏng; thông số trong `configs/vehicle_default.json` **chưa phải số đo MN300**. Các mục từ **Huấn luyện nhận thức** trở xuống là phần làm sau giai đoạn 0: AI, LiDAR và camera thật trên máy bàn, bàn thử giai đoạn 2, hợp nhất cảm biến; từ 24/09/2026 thêm công cụ hiệu chuẩn camera, gán nhãn ảnh sa bàn và giao thức xe (firmware C++ chưa biên dịch). *Cập nhật tối 24/09/2026 (chưa commit):* quy tắc chờ camera theo nhịp riêng và làm nóng AI (đo lại trên máy bàn), ghi/phát lại phiên bàn thử (một phiên thật), BEV từ AI (mới kiểm trên rig tổng hợp), định vị LiDAR trên bản đồ tĩnh (chạy offline trên bản ghi có sẵn, chưa có tham chiếu độc lập), `VehicleIO` trong phiên đỗ xe và chế độ quan sát (chỉ mô phỏng). *Sửa khuya 24/09/2026:* các việc đó đã commit và push lúc 20:22 (`bfcbfc2` … `9bcc30c`). *Cập nhật khuya 24/09/2026 (chưa commit, nằm trên `9bcc30c`; không phiên đo thiết bị nào):* công cụ ngoại tham và ROI (ảnh tổng hợp), BEV nhanh ≈ 10 lần, độ nhạy theo kích thước xe và nhãn ca khó (mô phỏng), odometry khớp scan và độ lặp lại LiDAR (offline), thẻ "Bo điều khiển" và cầu nối ToF (cổng serial giả), chấm RoadAnomaly21; lệnh ở mục "Việc làm khuya 24/09/2026" dưới.

## Chạy trên Windows

Trong thư mục `autopark`, chạy `cai_dat.cmd` rồi `chay_app.cmd`. Hoặc dùng PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-phase0.lock
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
.\.venv\Scripts\python.exe -X utf8 run_app.py
```

Môi trường đã kiểm tra dùng Python 3.12.10. Các phiên bản thực tế được cố định trong `requirements-phase0.lock` và ghi vào manifest của phiên chạy. PyTorch không thuộc môi trường mô phỏng; phần nhận thức dùng môi trường riêng `.venv-train` (xem mục **Huấn luyện nhận thức** bên dưới).

## Thử giai đoạn 0

1. Kéo và xoay ô đỗ/đích. Đích đè vật cản hoặc thân xe vượt sa bàn bị báo không hợp lệ và không được lập đường.
2. Bấm **Tìm đường đỗ**, **Xem trước**, rồi kết thúc xem trước và **Bắt đầu đỗ**. Xem trước dùng một rollout riêng; không có kết nối phần cứng.
3. Khi đang chạy, bấm **Vật cản giả** hoặc **Mất dữ liệu** bên phải sa bàn. Đường cũ bị vô hiệu; xe phanh, dừng rồi chờ. Với mất dữ liệu, cờ dừng xuất hiện khi mẫu vượt hạn 150 ms, kiểm tra theo chu kỳ điều khiển 20 ms.
4. Sau khi dừng, bấm **Chọn lại vị trí**, đánh giá bản đồ/đích rồi lập đường lại. Với sự kiện an toàn, xuất phát mới là vị trí xe thực sự vừa dừng. Không tự tiếp tục chạy.
5. Trong thiết lập mô phỏng có profile **Trễ 40 ms + nhiễu 2 mm / 0,2°**. Mất mẫu ngẫu nhiên có thể cấu hình qua `FeedbackConfig` trong API. Seed lấy từ kịch bản.
6. Bấm **Lưu phiên…** trước khi đặt lại phiên. Ngoài CSV, lượt chạy tự động được lưu thành thư mục có cấu hình, quỹ đạo, sự kiện, kết quả, môi trường và snapshot source. Chế độ lái tay chỉ xuất CSV.
7. *(Từ tối 24/09/2026.)* Ngăn "Mô phỏng" có ô **Nhánh chạy khi bấm Bắt đầu đỗ**: "Mô phỏng giai đoạn 0" (mặc định, như các bước trên), "VehicleIO → bo mô phỏng" (gửi lệnh qua giao thức xe tới bo mô phỏng) và "Quan sát" (tính lệnh nhưng không gửi; phím mũi tên lái xe mô phỏng thay người lái). Hai nhánh sau ghi thêm `commands.csv`, `telemetry.csv`, `events.csv` khi xuất log. Tư thế lấy thẳng từ mô phỏng; chưa có lựa chọn cổng serial tới bo thật. Chi tiết: [docs/CHE_DO_QUAN_SAT.md](docs/CHE_DO_QUAN_SAT.md). *(Cập nhật khuya 24/09/2026, mã chưa commit:)* nhãn nhánh thứ hai nay là "VehicleIO: GỬI lệnh tới bo", gửi tới bo chọn ở thẻ **"Bo điều khiển"** ngay dưới ngăn "Mô phỏng"; mặc định "Bo mô phỏng (mặc định)", hành vi như trước. Thẻ này liệt kê cổng COM khi mở danh sách (không mở cổng) và có nút **"Kiểm kết nối bo"** (HELLO, so giới hạn bo với cấu hình xe, đọc 5 khung telemetry, đóng cổng; không bao giờ ARM hay gửi COMMAND; hỏi xác nhận trước khi mở cổng thật, đừng chọn cổng LiDAR). Chọn cổng thật rồi bấm Bắt đầu đỗ thì **luôn bị từ chối** vì chưa có nguồn tư thế thật. Mới kiểm với cổng serial giả; chưa có ESP32-S3.

Kịch bản `scenarios/giai_doan_0_unknown.json` minh họa vùng chưa quan sát: vẽ gạch chéo và chặn như vật cản. Có thể thêm loại **chưa quan sát** trong mục Vật cản.

## Kiểm thử, bằng chứng và replay

Đợt kiểm thử mở rộng của giai đoạn 0 (20/09/2026): **220 ca pytest** và chiến dịch **2.880 trường hợp theo seed**. Xem [báo cáo, các lỗi đã sửa và giới hạn](docs/KIEM_THU_DO_BEN_GIAI_DOAN_0.md). Bộ test hiện nay nhiều hơn 220 ca vì có thêm các khối nhận thức, LiDAR, camera, hợp nhất và bàn thử; số đếm của từng đợt ghi trong biên bản của đợt đó. Chạy bộ đo theo thời hạn riêng với campaign/coverage để tránh làm sai kết quả thời gian.

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.phase0 --out runs/thu_nghiem_moi
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.replay runs/thu_nghiem_moi/obstacle
```

Kiểm thử diện rộng: `python -m autopark.evaluation.robustness --out runs/kiem_thu_moi`.
Tái hiện một input: thêm `--case runtime:137` và dùng thư mục đầu ra mới.

Lệnh tạo bằng chứng cần OpenCV, dùng thư mục đầu ra mới. Mỗi ca có `simulation.mp4`, `final_frame.png`, `telemetry.csv`, `events.jsonl`, `safety_events.json`, `result.json`, `manifest.json`, `source.zip` và `config_snapshot/`. Quỹ đạo và tham số controller/fault được lưu trong `config_snapshot/run.json`. Replay dùng chính quỹ đạo đã lưu để tránh khác biệt do time budget của planner.

Mỗi bước replay đối chiếu kết quả với bản ghi; cùng code/môi trường/seed tái tạo đúng trạng thái cuối. Bộ kiểm thử còn đối chiếu toàn bộ dòng log và sự kiện an toàn. Đây là replay mô phỏng, chưa phải replay camera/LiDAR thực. *(Cập nhật tối 24/09/2026:)* phát lại bản ghi camera/LiDAR thật của bàn thử là công cụ riêng, xem [docs/GHI_PHAT_LAI_BAN_THU.md](docs/GHI_PHAT_LAI_BAN_THU.md). Lần chạy qua `VehicleIO` chưa replay được bằng `autopark.evaluation.replay`. *(Cập nhật muộn tối 24/09/2026: `export_run`/`replay_run` nay từ chối rõ các lần chạy đó bằng `ReplayNotSupported`, `tests/test_run_store_vehicle.py`.)*

## Dữ liệu công khai

- [Danh mục dataset, nhãn, nguồn tải và điều kiện sử dụng](datasets/DANH_MUC_DATASET.md).
- [Các bộ đã tải, kiểm tra và cách dùng](datasets/TAI_VA_KIEM_TRA.md).
- Kiểm tra lại mẫu AVM: `python -m autopark.evaluation.dataset_audit`.
- Kiểm tra các bộ đã giải nén: `python datasets/verify_downloads.py`.

## Huấn luyện nhận thức (WoodScape, FREE / BLOCKED)

Baseline L-RASPP/MobileNetV3 đã được huấn luyện ngày 21/09/2026 trên RTX 4000 Ada; quá trình, kết quả và giới hạn ghi tại [HUAN_LUYEN.md](../HUAN_LUYEN.md). Mô hình mới được chấm trên ảnh lưu sẵn của bộ dữ liệu công khai. Từ 23/09 nó chạy trực tiếp trên bốn camera của bàn thử giai đoạn 2, nhưng lớp tô ở đó chỉ để quan sát: chưa chấm trên ảnh sa bàn có nhãn, và chưa nối vào planner. Chạy trong `.venv-train` (Python 3.12, torch 2.11.0+cu128), từ thư mục `autopark`:

```powershell
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.verify_cache      # bắt buộc trước khi train
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.benchmark --config configs/train_woodscape_rtx4000_baseline.json --out runs/<ten>/benchmark.json
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.train --config configs/train_woodscape_rtx4000_baseline.json --out runs/<ten>
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.train --out runs/<ten> --resume runs/<ten>/latest.pt
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.evaluate --checkpoint runs/<ten>/best.pt --split val --out runs/<ten>/eval_val
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.predict --checkpoint runs/<ten>/best.pt --input <anh_hoac_thu_muc> --out runs/<ten>/predict --threshold 0.15
.\.venv-train\Scripts\python.exe -X utf8 -m pytest tests/test_perception_data.py tests/test_perception_training.py
```

Dừng có kiểm soát: tạo file rỗng `STOP` trong thư mục run; trainer lưu `latest.pt` rồi kết thúc ở trạng thái `stopped` (xem `status.json`). Tập test chỉ đánh giá được với `--split test --final-test`, mỗi lần đều ghi vào `test_evaluations.jsonl`.

## Giai đoạn 1 khi chưa đủ thiết bị — phát lại, ROI, costmap, ONNX

Chi tiết và giới hạn ở [docs/GIAI_DOAN_1_CHUAN_BI.md](docs/GIAI_DOAN_1_CHUAN_BI.md). Đánh giá ngoài miền (ACDC, RoadObstacle21), độ dao động theo seed, loss có trọng số và ngưỡng an toàn ở [HUAN_LUYEN.md](../HUAN_LUYEN.md) phần II. Thử thêm dữ liệu AVM-SS và ACDC (cache `prepare_extra`, chấm chéo miền, ba seed mỗi nhóm) ở phần III: không lượt nào vượt lượt nền trên hai tập chưa chạm; lượt nền vẫn là checkpoint tham chiếu.

Nhánh LiDAR thật (driver RPLIDAR C1 qua COM, ghi/phát lại phiên, phiên đo tĩnh, bản đồ lưới tĩnh, màn hình trực tiếp): [docs/GIAI_DOAN_1_LIDAR.md](docs/GIAI_DOAN_1_LIDAR.md); cổng chuyển bước giai đoạn 1: [docs/gate_01.md](docs/gate_01.md); kiểm kê thiết bị: [docs/hardware_inventory.md](docs/hardware_inventory.md). Cần `pip install -e .[lidar]` (pyserial). Nhánh camera thật (bốn camera USB 130° theo nhà bán qua hub UGREEN: liệt kê mode, ghép index với cổng hub, đo FPS/mất hình một và bốn luồng, ghi mẫu): [docs/GIAI_DOAN_1_CAMERA.md](docs/GIAI_DOAN_1_CAMERA.md), sơ đồ cổng [docs/usb_topology.md](docs/usb_topology.md); cần `pip install -e .[video]` (pygrabber trên Windows). Bàn thử giai đoạn 2 (bốn camera + LiDAR + AI chạy chung, giao diện trực tiếp có lớp tô AI, đo suy luận/độ trễ/đồng bộ, phát hiện khung MJPEG bị cắt khi chạy chung qua hub): [docs/GIAI_DOAN_2_BAN_THU.md](docs/GIAI_DOAN_2_BAN_THU.md); chạy trong `.venv-train` (`pip install -e .[rig]`).

Hợp nhất cảm biến chuẩn bị cho giai đoạn 3 (lớp bản đồ, hợp nhất, cầu nối vật cản vào phiên, demo với LiDAR thật đứng yên: xe ảo lập đường quanh đồ trên bàn và đỗ xong): [docs/GIAI_DOAN_3_CHUAN_BI.md](docs/GIAI_DOAN_3_CHUAN_BI.md).
Giao diện bàn thử LiDAR: `python -m autopark.ui.lidar_app --port COM4` (cửa sổ đỗ xe + ngăn LiDAR).

Việc làm được khi chưa đủ thiết bị (24/09/2026), mỗi việc một tài liệu:

- Hiệu chuẩn camera thật: [docs/HIEU_CHUAN_CAMERA.md](docs/HIEU_CHUAN_CAMERA.md). In `calibration/bang_in/ban_co_9x6_20mm_A4.pdf` đúng 100 %, đo ô bằng thước, rồi `python -m autopark.ui.calib_app --port 1`. Tệp ra: `calibration/cam_p<cổng>.json`.
- Gán nhãn ảnh sa bàn: [docs/GAN_NHAN_SA_BAN.md](docs/GAN_NHAN_SA_BAN.md). `python -m autopark.perception.labels import runs/rig_snapshots`, rồi `python -m autopark.ui.label_app`, rồi `python -m autopark.perception.labels export --out datasets/prepared/sa_ban_v1`.
- Laptop RTX 3050 Ti mang đi nộp đồ án: [docs/MAY_NOP_DO_AN.md](docs/MAY_NOP_DO_AN.md). Chạy `cai_dat_train.cmd` rồi `do_may_moi.cmd` trên laptop; kết quả so với tham chiếu máy bàn ở `docs/evidence/may_ban/`. *(Cập nhật muộn tối 24/09/2026:)* tham chiếu mới [docs/evidence/may_ban/tham_chieu_20260924_toi.json](docs/evidence/may_ban/tham_chieu_20260924_toi.json) đo lúc 19:08 bằng mã mới (quy tắc chờ theo nhịp riêng, làm nóng AI); lệnh đo lấy tệp đứng cuối theo tên, tức tệp này; tệp 15:25 giữ để đối chiếu. Tệp mới và mã mới chưa commit: laptop chỉ có chúng sau khi commit, push rồi `git pull`. *(Khuya 24/09/2026: đã vào `bfcbfc2` và push; `git pull` là đủ. Các dòng mới của `tom_tat.md` — làm nóng AI, quy tắc chờ, độ lệch bộ ảnh, cảnh báo — là sửa đổi khuya chưa commit, [docs/MAY_NOP_DO_AN.md](docs/MAY_NOP_DO_AN.md) mục 4.1.)*
- Giao thức xe và firmware ESP32-S3: [docs/GIAO_THUC_XE.md](docs/GIAO_THUC_XE.md), mã `autopark/transport/`, firmware `firmware/esp32_vehicle/`, hướng dẫn và các mục CHƯA CHỐT ở [firmware/esp32_vehicle/README.md](firmware/esp32_vehicle/README.md) (máy này không có trình biên dịch C/C++: phần C++ CHƯA biên dịch lần nào).
- Bàn thử không chờ camera chậm: `--max-wait-ms` của `rig.bench`/`rig_app` ([docs/GIAI_DOAN_2_BAN_THU.md](docs/GIAI_DOAN_2_BAN_THU.md) mục 10). *Cập nhật tối 24/09/2026:* ngưỡng chờ nay tính theo nhịp của **chính từng camera** (mục 10.1–10.2; json ghi `policy.wait_rule = "own_cadence"`). Đo lại trên máy bàn: 0 bộ bỏ camera khỏe ở 720p (cổng 1 29,3 khung/s, cổng 2–4 23,85 khung/s) và ở 480p + LiDAR + AI (mục 10.3). *(Cập nhật muộn tối 24/09/2026:)* camera chạy ≈ 29 khung/s không cố định một cổng: cổng 3 ở s01–s07, t01, t02 (23/09), cổng 1 ở t05 (23/09) và lúc 15:25, 17:56 ngày 24/09, không camera nào lúc 19:08 (lần `may_moi` đo lại, cả bốn ≈ 23,85 khung/s). Giới hạn: camera nhìn chỗ tối, hai phiên không có khung hỏng nào, nên nhánh bỏ camera lỡ nhịp (khung cắt/xé hay camera treo) mới kiểm bằng mô phỏng và test; đổi lại, ở 720p độ lệch trong bộ lớn hơn (trung vị 28,5 so với 24,5 ms, max 52,8 so với 40,3 ms). AI chạy một lô ảnh đen cho mỗi cỡ lô trước bộ ảnh đầu (`ai.warm_up_ms`), vì lô đầu mỗi cỡ mất 1,2–1,7 s.
- *(Tối 24/09/2026)* Ghi và phát lại phiên bàn thử: [docs/GHI_PHAT_LAI_BAN_THU.md](docs/GHI_PHAT_LAI_BAN_THU.md). `rig.bench --record <thư mục>` hoặc nút "Ghi phiên" của `rig_app` (`--record-root`); `rig.bench --replay <thư mục>` hoặc `rig_app --replay <thư mục>`. Một phiên thật 60 s đã ghi và phát lại trên máy bàn.
- *(Tối 24/09/2026)* BEV từ AI nhiều camera: [docs/BEV.md](docs/BEV.md), mã `autopark/perception/bev.py`, tệp ngoại tham `configs/rig/camera_rig_extrinsics_v0.json` (GIẢ ĐỊNH — CHƯA ĐO). Lệnh `snapshot` trên bộ ảnh thật từ chối cho tới khi có `calibration/cam_p*.json`.
- *(Tối 24/09/2026)* Định vị LiDAR trên bản đồ tĩnh (không phải SLAM): [docs/DINH_VI_LIDAR.md](docs/DINH_VI_LIDAR.md), mã `autopark/lidar/localize.py`. Chạy offline trên bản ghi `.npz`; chưa có vị trí tham chiếu độc lập.
- *(Tối 24/09/2026)* Nối `VehicleIO` vào phiên đỗ xe và chế độ quan sát: [docs/CHE_DO_QUAN_SAT.md](docs/CHE_DO_QUAN_SAT.md), mã `autopark/application/vehicle_link.py`. Chỉ mô phỏng và cổng serial giả; có một khoảng trống an toàn đã biết, chưa sửa ([docs/GIAO_THUC_XE.md](docs/GIAO_THUC_XE.md) mục 12, test xfail ở dưới). *(Cập nhật muộn tối 24/09/2026: đã sửa, cũng chỉ kiểm trên mô phỏng và cổng serial giả; không còn test xfail, xem đoạn dưới.)* *(Khuya 24/09/2026: chốt phía firmware sau `COMMAND_TIMEOUT` để đóng khoảng hở còn lại đang chờ người dùng duyệt, CHƯA LÀM.)*
- *(Tối 24/09/2026)* Bản nháp khi chưa có phần cứng, không có số đo: giai đoạn 4 [docs/GIAI_DOAN_4_CHUAN_BI.md](docs/GIAI_DOAN_4_CHUAN_BI.md) và phiếu kiểm kê [docs/mn300_inventory.md](docs/mn300_inventory.md); giai đoạn 6 [docs/GIAI_DOAN_6_CHUAN_BI.md](docs/GIAI_DOAN_6_CHUAN_BI.md); dàn ý khóa luận [docs/DAN_Y_KHOA_LUAN.md](docs/DAN_Y_KHOA_LUAN.md).

```powershell
# .venv-train (torch)
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.evaluate_external --checkpoint runs/<ten>/best.pt --dataset acdc --split val --out runs/<ten>/eval_acdc_val
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.evaluate --checkpoint runs/<ten>/best.pt --split val --sweep --out runs/<ten>/eval_val_sweep
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.roi build
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.costmap --checkpoint runs/<ten>/best.pt --image datasets/training/woodscape/rgb_images/00007_FV.png --roi configs/roi/woodscape_v1 --out runs/perception_integration/costmap_00007_FV
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.export_onnx --checkpoint runs/<ten>/best.pt --out runs/<ten>/export
# .venv (mô phỏng, PySide6; không cần torch)
.\.venv\Scripts\python.exe -X utf8 -m autopark.lidar.viewer datasets/drow/DROWv2-data/val/run_2015-11-25-10-34-20-a.bag.csv --labels wp
# từ tối 24/09/2026; mỗi lệnh một dòng, dán được vào cmd.exe và PowerShell; thay <...> trước khi chạy
.\.venv\Scripts\python.exe -X utf8 -m autopark.perception.bev synthetic
.\.venv\Scripts\python.exe -X utf8 -m autopark.lidar.localize --map runs/lidar_bench/20260922/map_p07 --recording runs/lidar_bench/20260922/live_headless.npz --out <thư mục kết quả>
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --ports 1 2 3 4 --lidar COM4 --seconds 60 --name <tên> --out runs/rig_bench/<ngày> --record runs/rig_recordings/<tên>
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --replay runs/rig_recordings/<tên> --name <tên>_phat_lai --out runs/rig_bench/phat_lai
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --replay runs/rig_recordings/<tên> --max-wait-ms 0 --name <tên>_phat_lai_tat_cho --out runs/rig_bench/phat_lai
.\.venv\Scripts\python.exe -X utf8 -m autopark.ui.rig_app --replay runs/rig_recordings/<tên> --no-ai
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_bev.py tests/test_lidar_localize.py tests/test_session_vehicle.py
.\.venv-train\Scripts\python.exe -X utf8 -m pytest tests/test_rig_replay.py
```

Lệnh `--record` mở bốn camera và LiDAR thật; các lệnh `--replay`, `bev synthetic`, `lidar.localize` và hai dòng pytest không mở thiết bị nào. Test giao diện chạy không cửa sổ khi đặt biến môi trường `QT_QPA_PLATFORM=offscreen`.

Các khối `lidar/`, `video/`, `safety/`, `perception/calibration.py`, `perception/costmap.py` không cần torch và được test trong cả hai môi trường. Chạy toàn bộ bộ test bằng `.venv` (`pytest`; các test cần torch tự bỏ qua) và các test nhận thức bằng `.venv-train` (`pytest tests/test_perception_*.py tests/test_phase1_sources.py tests/test_labels.py`; từ 24/09 `test_labels.py` có một test mở cache sa bàn bằng `PreparedCache.open`, cần torch); `.venv-train` không có Shapely nên không chạy được test mô phỏng (từ 23/09 nó có PySide6 và pyserial cho bàn thử giai đoạn 2). Driver RPLIDAR C1 (`lidar/rplidar_c1.py`) đã chạy với thiết bị thật trên COM4 ngày 22/09, và `UsbCameraSource` với bốn camera USB ngày 23/09, cả hai trên máy bàn, chưa trên laptop RTX 3050 Ti (máy nộp đồ án). *(Tối 24/09/2026:)* `tests/test_bev.py`, `tests/test_lidar_localize.py`, `tests/test_session_vehicle.py` chạy trong `.venv` (test phiên cần Shapely); lần chạy tối 24/09 (18:41, máy bàn): 110 đạt + 1 xfail (32 + 29 + 49 đạt + 1 xfail strict; lần chạy trước đó, khi tệp test phiên còn 34 test, là 95 = 32 + 29 + 34). Test xfail ghi một khoảng trống an toàn chưa sửa, chỉ thấy trên mô phỏng: vòng điều khiển treo quá hạn lệnh trong khi `Heartbeat` vẫn PING thì phiên có thể gửi thêm một COMMAND enable=1 trước khi thấy `VEHICLE_STOPPED` ([docs/GIAO_THUC_XE.md](docs/GIAO_THUC_XE.md) mục 12). pytest báo `1 xfailed` là kết quả đúng. *(Cập nhật muộn tối 24/09/2026, sau bản sửa khoảng trống an toàn:)* ba tệp trên nay 121 đạt (32 + 29 + 60), không còn test xfail nào trong `tests/`; câu "`1 xfailed` là kết quả đúng" ở trên chỉ đúng cho bản trước khi sửa. Cách sửa: `VehicleLink.refresh()` lấy telemetry và sự kiện đã tới **trước** nhịp điều khiển, và `VehicleLink.command()` không gửi lệnh chạy khi còn sự kiện dừng chưa xử lý (chi tiết ở [../TONG_HOP_DU_AN.md](../TONG_HOP_DU_AN.md) mục 4.9). Còn một khoảng hở suy ra từ mã, chưa có test: `refresh()` chỉ thấy khung đã tới laptop, nên nếu khung báo bo vừa về ARMED chưa tới thì vẫn có thể gửi một enable=1 ([docs/GIAO_THUC_XE.md](docs/GIAO_THUC_XE.md) mục 12). Toàn bộ bộ test chạy lại trên máy bàn cùng tối: `.venv` 895 đạt, 6 bỏ qua (mô-đun cần torch), 215 s; `.venv-train` (sáu mô-đun cần torch cùng `test_labels.py`, `test_rig_replay.py`, `test_multicam_rig.py`, `test_rig_app_ui.py`, `test_may_moi.py`) 248 đạt. Rút cáp LiDAR giữa chừng (driver, demo hợp nhất, `lidar.bench record`): `tests/test_lidar_unplug.py`, 13 test, cổng serial giả; rút cáp C1 thật chưa thử. `tests/test_rig_replay.py` dùng camera/LiDAR giả, cần numpy, OpenCV và PySide6.

### Việc làm khuya 24/09/2026 (chưa commit, nằm trên `9bcc30c`)

Không việc nào dưới đây có phiên đo mới trên thiết bị; mức bằng chứng ghi ở từng dòng. Tóm tắt và các việc còn mở:
[../TONG_HOP_DU_AN.md](../TONG_HOP_DU_AN.md) (khối "Cập nhật khuya" đầu tệp, mục 4.15).

- Ngoại tham camera và mặt nạ ROI cho camera dự án: [docs/NGOAI_THAM_VA_ROI.md](docs/NGOAI_THAM_VA_ROI.md). Chỉ kiểm trên
  ảnh tổng hợp; cần `calibration/cam_p<N>.json` và camera đã gá cứng trên xe trước khi đo thật. Giao diện `ui.roi_app`
  không mở camera nào nếu không có `--live` hay ô "Camera sống".
- BEV nhanh ≈ 10 lần, trùng từng bit với bản cũ; lệnh `bench` đo thời gian trên rig tổng hợp, không cần dữ liệu hay
  thiết bị: [docs/BEV.md](docs/BEV.md) mục 5, 6b.
- Độ nhạy planner theo kích thước xe với sa bàn cố định, và `--vehicle-config` cho `robustness`, `phase0`, `ui.lidar_app`
  (chỉ mô phỏng): [docs/DO_NHAY_KICH_THUOC_XE.md](docs/DO_NHAY_KICH_THUOC_XE.md). Tệp `configs/vehicle_measured.json` chưa
  có; định dạng CHƯA CHỐT.
- Nhãn 16 ca khó và đường chứng (mô phỏng): [docs/KIEM_THU_DO_BEN_GIAI_DOAN_0.md](docs/KIEM_THU_DO_BEN_GIAI_DOAN_0.md) mục 6.
- Odometry khớp scan và so sánh phương án định vị (offline): [docs/SO_SANH_DINH_VI_SLAM.md](docs/SO_SANH_DINH_VI_SLAM.md).
- Độ lặp lại khoảng cách LiDAR (offline): [docs/GIAI_DOAN_1_LIDAR.md](docs/GIAI_DOAN_1_LIDAR.md) mục 3c.
- RoadAnomaly21, `evaluate.py --train-overlap`, `labels import --exclude`: [../HUAN_LUYEN.md](../HUAN_LUYEN.md) cuối mục 8,
  [docs/GAN_NHAN_SA_BAN.md](docs/GAN_NHAN_SA_BAN.md) mục 2 bước 7.
- Thẻ "Bo điều khiển", "Kiểm kết nối bo", so giới hạn bo; cầu nối ToF → `NearFieldReading` với bảng gá GIẢ ĐỊNH
  `configs/tof_mounts_v0.json` (cổng serial giả): [docs/CHE_DO_QUAN_SAT.md](docs/CHE_DO_QUAN_SAT.md) mục 3, 6–8,
  [docs/GIAO_THUC_XE.md](docs/GIAO_THUC_XE.md) mục 7, 10, 12.
- Demo hợp nhất bỏ ≥ 22 vòng khởi động, `--warmup` (nguồn giả): [docs/GIAI_DOAN_3_CHUAN_BI.md](docs/GIAI_DOAN_3_CHUAN_BI.md) mục 2.
- `may_moi` tóm tắt lại một thư mục kết quả đã có (không mở thiết bị): [docs/MAY_NOP_DO_AN.md](docs/MAY_NOP_DO_AN.md) mục 4.1.
- Kịch bản và ngưỡng nghiệm thu nháp (CHỜ CHỐT): [docs/KICH_BAN_NGHIEM_THU.md](docs/KICH_BAN_NGHIEM_THU.md),
  [docs/NGUONG_NGHIEM_THU_DE_XUAT.md](docs/NGUONG_NGHIEM_THU_DE_XUAT.md).

Lệnh, chạy trong thư mục `autopark`, mỗi lệnh một dòng, dán được vào cmd.exe; thay `<...>` trước khi chạy. Các lệnh
trong khối này không mở camera, LiDAR hay cổng COM nào (trong `roi_app` không bấm "Camera sống"):

```
.venv\Scripts\python.exe -X utf8 -m autopark.ui.roi_app --port 1
.venv\Scripts\python.exe -X utf8 -m autopark.perception.extrinsics_calib synthetic --out runs\extrinsics\tong_hop
.venv\Scripts\python.exe -X utf8 -m autopark.perception.bev bench
.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.sensitivity --list
.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.sensitivity --scenes parallel_160,uturn_w55 --params width --levels 10 --combos none --out runs\do_nhay_xe\thu_nhanh
.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.hard_cases --witness-out runs\witness_moi.json --time-limit 30
.venv\Scripts\python.exe -X utf8 -m autopark.lidar.scan_odometry --recording runs/lidar_bench/20260922/p07_nen_phong.npz --skip-seconds 3 --mode both --out <thư mục kết quả>
.venv\Scripts\python.exe -X utf8 -m autopark.lidar.repeatability runs/lidar_bench/20260922/p07_nen_phong.npz runs/lidar_bench/20260922/live_headless.npz runs/lidar_bench/20260924_kiem/k01_kiem_suc_khoe.npz --out runs/lidar_bench/do_lap_lai
.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.evaluate_external --checkpoint runs/ai_woodscape_rtx4000_v1/best.pt --dataset road_anomaly --out runs/ai_woodscape_rtx4000_v1/eval_road_anomaly
.venv\Scripts\python.exe -X utf8 -m autopark.perception.labels import runs/rig_snapshots --project datasets/sa_ban_labels --exclude datasets/sa_ban_cham
.venv\Scripts\python.exe -X utf8 -m autopark.rig.may_moi --out runs\may_moi_<ngày giờ> --steps
```

**Chạm thiết bị, chỉ người thao tác chạy:** `fusion.demo --port COM4` mở LiDAR C1, `roi_app --live` mở camera thật.

```
.venv\Scripts\python.exe -X utf8 -m autopark.fusion.demo --port COM4 --seconds 30 --warmup 4.5
.venv\Scripts\python.exe -X utf8 -m autopark.ui.roi_app --port 1 --live
```

Nút "Kiểm kết nối bo" nằm trong giao diện chính (`chay_app.cmd`), thẻ "Bo điều khiển";
với cổng COM thật nó mở cổng đó sau khi hỏi xác nhận.

Test của đợt này (máy bàn, đếm bằng `--collect-only` khuya 24/09/2026): `test_extrinsics_calib` 29, `test_roi_tool` 19,
`test_bev` 38, `test_vehicle_sensitivity` 56, `test_hard_cases_labels` 44, `test_scan_odometry` 32,
`test_lidar_repeatability` 20, `test_vehicle_board_ui` 30, `test_nearfield_tof` 54, `test_transport_vehicle_io` 64,
`test_fusion_demo` 17, `test_may_moi` 21, `test_labels` 55; cần torch: `test_evaluate_external_ra21` 7,
`test_perception_evaluation` 18. Số đạt/hỏng của từng tệp ghi ở tài liệu của việc đó; không có lần chạy toàn bộ bộ test
nào sau đợt này. **Hỏng đã biết:** `tests/test_planner_hard_cases.py::test_ca_vo_nghiem_khong_bao_thanh_cong_gia` hai
trường hợp `parallel_122`, `parallel_115` vẫn khẳng định nhãn `infeasible` cũ (chạy lại khuya 24/09/2026, `.venv`: 2
failed); chờ sửa tệp test, nên tệp đó cố ý không có trong hai lệnh dưới. Test giao diện chạy không cửa sổ: trong cmd.exe
gõ `set QT_QPA_PLATFORM=offscreen` trước:

```
.venv\Scripts\python.exe -X utf8 -m pytest tests/test_extrinsics_calib.py tests/test_roi_tool.py tests/test_bev.py tests/test_vehicle_sensitivity.py tests/test_hard_cases_labels.py tests/test_scan_odometry.py tests/test_lidar_repeatability.py tests/test_vehicle_board_ui.py tests/test_nearfield_tof.py tests/test_fusion_demo.py tests/test_transport_vehicle_io.py tests/test_may_moi.py
.venv-train\Scripts\python.exe -X utf8 -m pytest tests/test_evaluate_external_ra21.py tests/test_perception_evaluation.py tests/test_labels.py
```

Chạy lại đúng hai lệnh trên sau khi thêm `test_transport_vehicle_io`, `test_may_moi` (khuya 24/09/2026, máy bàn,
offscreen, cây làm việc chưa commit trên `9bcc30c`, các tác tử khác chạy song song): `.venv` 424 đạt, `.venv-train`
80 đạt, khớp tổng số đếm ở trên. Đây không phải lần chạy toàn bộ bộ test. *(Cập nhật 25/09/2026, sau khi các tác tử dừng, máy bàn rảnh, cây làm việc chưa commit trên `9bcc30c`:)* đã sửa `tests/test_planner_hard_cases.py` theo nhãn mới (đổi tên thành `test_ca_rat_chat_khong_bao_thanh_cong_gia`: nhãn `feasible`, cho phép OK/TIMEOUT/NO_PATH, báo OK thì đường phải qua kiểm độc lập), cùng vài sửa nhỏ (TONG_HOP_DU_AN.md mục 5.4). **Chạy lại toàn bộ bộ test:** `.venv` **1242 đạt, 7 bỏ qua** (bảy mô-đun cần torch), 334 s, 0 hỏng; `.venv-train` (bảy mô-đun cần torch cùng test gán nhãn, bàn thử, `may_moi`, hiệu chuẩn, ngoại tham, ROI) **386 đạt**. `uturn_w46` đạt ở lần chạy này (máy rảnh); nó vẫn phụ thuộc thời gian thật như ghi ở trên.

## Cấu trúc chính

| Thư mục | Nội dung |
|---|---|
| `autopark/domain/` | Pose, trạng thái xe, cấu hình, hợp đồng camera/scan/telemetry/costmap/safety |
| `autopark/planning/`, `control/` | Planner, quỹ đạo và controller |
| `autopark/geometry/`, `simulation/` | Thân xe/vùng quét, động học, phản hồi có lỗi |
| `autopark/application/`, `ui/` | Máy trạng thái phiên và giao diện PySide6; từ tối 24/09/2026 `application/vehicle_link.py` nối `VehicleIO` vào phiên, chế độ quan sát (chỉ mô phỏng) |
| `autopark/storage/`, `evaluation/` | Kịch bản, log/snapshot/replay, nghiệm thu/video/audit nhãn; *khuya 24/09/2026:* `evaluation/sensitivity.py` (độ nhạy theo kích thước xe, sa bàn cố định), đường chứng và kiểm độc lập cho nhãn ca khó trong `evaluation/hard_cases.py` |
| `autopark/perception/` | Chuẩn bị/xác minh cache WoodScape (và AVM-SS/ACDC qua `prepare_extra.py`), trainer, benchmark, đánh giá (kể cả ACDC/RoadObstacle21), suy luận (kể cả theo lô trực tiếp, `live.py`), calibration fisheye WoodScape, hiệu chuẩn nội tham camera thật bằng bảng ô vuông (`fisheye_calib.py`, bảng in `calib_board.py`, giao diện chụp `ui/calib_app.py`; mã có từ 24/09, mới kiểm trên ảnh tổng hợp, chưa hiệu chuẩn camera nào), gán nhãn ảnh sa bàn (`labels.py`, giao diện `ui/label_app.py`; mã có từ 24/09, mới nhập thử hai bộ ảnh chụp ngày 23/09, chưa gán nhãn ảnh thật nào), ROI, costmap, xuất ONNX; BEV từ AI nhiều camera (`bev.py`; tối 24/09, mới kiểm trên rig tổng hợp, chưa chạy trên camera dự án); *khuya 24/09/2026:* ngoại tham camera (`extrinsics_calib.py`) và mặt nạ ROI (`roi_tool.py`), giao diện `ui/roi_app.py`, chỉ kiểm trên ảnh tổng hợp |
| `autopark/lidar/`, `video/`, `safety/` | Driver RPLIDAR C1, ghi/phát lại phiên, phiên đo tĩnh, bản đồ lưới tĩnh, định vị trên bản đồ tĩnh (`localize.py`, tối 24/09), odometry khớp scan (`scan_odometry.py`) và độ lặp lại khoảng cách (`repeatability.py`, cả hai khuya 24/09, offline), phát lại DROW v2 và hiển thị; nguồn ảnh (thư mục/video/USB, loại khung MJPEG hỏng), phiên đo camera, nhiều camera theo cổng hub; giám sát dữ liệu cũ |
| `autopark/fusion/`, `rig/` | Lớp bản đồ và hợp nhất, cầu nối vật cản vào phiên mô phỏng; bàn thử bốn camera + LiDAR + AI; ghi/phát lại phiên bàn thử (`rig/recording.py`, `rig/replay.py`, tối 24/09); *khuya 24/09/2026:* cầu nối ToF → `NearFieldReading` trong `fusion/layers.py` |
| `autopark/transport/`, `firmware/` | Giao thức laptop–ESP32-S3 (khung COBS + CRC), bản tham chiếu Python của firmware, VehicleIO mô phỏng/serial; firmware C++ cho ESP32-S3 (chưa biên dịch) |
| [`calibration/`](calibration/README.md) | Bảng ô vuông để in và tệp hiệu chuẩn từng camera (theo cổng hub) |
| `configs/`, `scenarios/`, `tests/` | Tham số giả định, bản đồ và kiểm thử; `configs/rig/camera_rig_extrinsics_v0.json` là ngoại tham camera GIẢ ĐỊNH — CHƯA ĐO (tối 24/09); *khuya 24/09/2026:* `configs/tof_mounts_v0.json` là vị trí gá ToF GIẢ ĐỊNH — CHƯA ĐO; `configs/rig/camera_rig_extrinsics_v1.json` và `configs/roi/rig_v1/` là nơi công cụ ngoại tham/ROI sẽ ghi, **chưa có** |
| `datasets/`, `docs/`, `runs/` | Dữ liệu, biên bản và bằng chứng từng phiên |

Quy ước: mét, giây, radian; pose tại tâm trục sau; x hướng trước, y trái, yaw dương ngược chiều kim đồng hồ. Timestamps mô phỏng dùng cùng đồng hồ phiên. Khi kết nối cảm biến thật phải xác định chuyển hệ tọa độ và đồng bộ thời gian.

Giới hạn: profile nhiễu là giả định, chưa đo trên xe; preview hiện là rollout lý tưởng. Vật xuất hiện ngay trong thân hoặc quá gần để phanh có thể gây FAULT. Không coi cờ dừng mô phỏng là bằng chứng phanh/E-stop phần cứng.

[Biên bản đối chiếu giai đoạn 0](docs/GIAI_DOAN_0.md).
