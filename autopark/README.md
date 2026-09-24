# AutoPark — mã nguồn xe mô hình tự đỗ theo kế hoạch v3.1

> **Ghi công bắt buộc theo giấy phép dữ liệu:** nghiên cứu nhận thức trong dự án này được thực hiện với **Valeo WoodScape Dataset** (<https://woodscape.valeo.com>, [repo](https://github.com/valeoai/WoodScape)). Điều khoản Valeo yêu cầu hiển thị rõ ghi công này trong mọi tài liệu công bố có nhắc tới nghiên cứu dùng bộ dữ liệu. Bảng giấy phép đầy đủ và vấn đề cần xử lý: [docs/GIAY_PHEP_DU_LIEU.md](docs/GIAY_PHEP_DU_LIEU.md).

Mô phỏng xe đạp động học, đặt/xoay đích, Hybrid A*/Reeds–Shepp, bám quỹ đạo tiến/lùi và dừng khi bản đồ/phản hồi không còn hợp lệ. Đây là phần mềm mô phỏng; thông số trong `configs/vehicle_default.json` **chưa phải số đo MN300**. Các mục từ **Huấn luyện nhận thức** trở xuống là phần làm sau giai đoạn 0: AI, LiDAR và camera thật trên máy bàn, bàn thử giai đoạn 2, hợp nhất cảm biến.

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

Mỗi bước replay đối chiếu kết quả với bản ghi; cùng code/môi trường/seed tái tạo đúng trạng thái cuối. Bộ kiểm thử còn đối chiếu toàn bộ dòng log và sự kiện an toàn. Đây là replay mô phỏng, chưa phải replay camera/LiDAR thực.

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

Hợp nhất cảm biến chuẩn bị cho giai đoạn 3 (lớp bản đồ, hợp nhất, cầu nối vật cản vào phiên, demo LiDAR thật dừng xe ảo): [docs/GIAI_DOAN_3_CHUAN_BI.md](docs/GIAI_DOAN_3_CHUAN_BI.md).
Giao diện bàn thử LiDAR: `python -m autopark.ui.lidar_app --port COM4` (cửa sổ đỗ xe + ngăn LiDAR).

Việc làm được khi chưa đủ thiết bị (24/09/2026), mỗi việc một tài liệu:

- Hiệu chuẩn camera thật: [docs/HIEU_CHUAN_CAMERA.md](docs/HIEU_CHUAN_CAMERA.md). In `calibration/bang_in/ban_co_9x6_20mm_A4.pdf` đúng 100 %, đo ô bằng thước, rồi `python -m autopark.ui.calib_app --port 1`. Tệp ra: `calibration/cam_p<cổng>.json`.
- Gán nhãn ảnh sa bàn: [docs/GAN_NHAN_SA_BAN.md](docs/GAN_NHAN_SA_BAN.md). `python -m autopark.perception.labels import runs/rig_snapshots`, rồi `python -m autopark.ui.label_app`, rồi `python -m autopark.perception.labels export --out datasets/prepared/sa_ban_v1`.
- Giao thức xe và firmware ESP32-S3: [docs/GIAO_THUC_XE.md](docs/GIAO_THUC_XE.md), mã `autopark/transport/`, firmware `firmware/esp32_vehicle/` (máy này không có trình biên dịch C/C++: phần C++ CHƯA biên dịch lần nào).
- Bàn thử không chờ camera chậm: `--max-wait-ms` của `rig.bench`/`rig_app` ([docs/GIAI_DOAN_2_BAN_THU.md](docs/GIAI_DOAN_2_BAN_THU.md) mục 10).

```powershell
# .venv-train (torch)
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.evaluate_external --checkpoint runs/<ten>/best.pt --dataset acdc --split val --out runs/<ten>/eval_acdc_val
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.evaluate --checkpoint runs/<ten>/best.pt --split val --sweep --out runs/<ten>/eval_val_sweep
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.roi build
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.costmap --checkpoint runs/<ten>/best.pt --image datasets/training/woodscape/rgb_images/00007_FV.png --roi configs/roi/woodscape_v1 --out runs/perception_integration/costmap_00007_FV
.\.venv-train\Scripts\python.exe -X utf8 -m autopark.perception.export_onnx --checkpoint runs/<ten>/best.pt --out runs/<ten>/export
# .venv (mô phỏng, PySide6; không cần torch)
.\.venv\Scripts\python.exe -X utf8 -m autopark.lidar.viewer datasets/drow/DROWv2-data/val/run_2015-11-25-10-34-20-a.bag.csv --labels wp
```

Các khối `lidar/`, `video/`, `safety/`, `perception/calibration.py`, `perception/costmap.py` không cần torch và được test trong cả hai môi trường. Chạy toàn bộ bộ test bằng `.venv` (`pytest`; các test cần torch tự bỏ qua) và các test nhận thức bằng `.venv-train` (`pytest tests/test_perception_*.py tests/test_phase1_sources.py`); `.venv-train` không có Shapely nên không chạy được test mô phỏng (từ 23/09 nó có PySide6 và pyserial cho bàn thử giai đoạn 2). Driver RPLIDAR C1 (`lidar/rplidar_c1.py`) đã chạy với thiết bị thật trên COM4 ngày 22/09, và `UsbCameraSource` với bốn camera USB ngày 23/09, cả hai trên máy bàn, chưa trên laptop của xe.

## Cấu trúc chính

| Thư mục | Nội dung |
|---|---|
| `autopark/domain/` | Pose, trạng thái xe, cấu hình, hợp đồng camera/scan/telemetry/costmap/safety |
| `autopark/planning/`, `control/` | Planner, quỹ đạo và controller |
| `autopark/geometry/`, `simulation/` | Thân xe/vùng quét, động học, phản hồi có lỗi |
| `autopark/application/`, `ui/` | Máy trạng thái phiên và giao diện PySide6 |
| `autopark/storage/`, `evaluation/` | Kịch bản, log/snapshot/replay, nghiệm thu/video/audit nhãn |
| `autopark/perception/` | Chuẩn bị/xác minh cache WoodScape (và AVM-SS/ACDC qua `prepare_extra.py`), trainer, benchmark, đánh giá (kể cả ACDC/RoadObstacle21), suy luận (kể cả theo lô trực tiếp, `live.py`), calibration fisheye WoodScape, hiệu chuẩn nội tham camera thật bằng bảng ô vuông (`fisheye_calib.py`, bảng in `calib_board.py`, giao diện chụp `ui/calib_app.py`; mã có từ 24/09, mới kiểm trên ảnh tổng hợp, chưa hiệu chuẩn camera nào), ROI, costmap, xuất ONNX |
| `autopark/lidar/`, `video/`, `safety/` | Driver RPLIDAR C1, ghi/phát lại phiên, phiên đo tĩnh, bản đồ lưới tĩnh, phát lại DROW v2 và hiển thị; nguồn ảnh (thư mục/video/USB, loại khung MJPEG hỏng), phiên đo camera, nhiều camera theo cổng hub; giám sát dữ liệu cũ |
| `autopark/fusion/`, `rig/` | Lớp bản đồ và hợp nhất, cầu nối vật cản vào phiên mô phỏng; bàn thử bốn camera + LiDAR + AI |
| `autopark/transport/`, `firmware/` | Giao thức laptop–ESP32-S3 (khung COBS + CRC), bản tham chiếu Python của firmware, VehicleIO mô phỏng/serial; firmware C++ cho ESP32-S3 (chưa biên dịch) |
| `calibration/` | Bảng ô vuông để in và tệp hiệu chuẩn từng camera (theo cổng hub) |
| `configs/`, `scenarios/`, `tests/` | Tham số giả định, bản đồ và kiểm thử |
| `datasets/`, `docs/`, `runs/` | Dữ liệu, biên bản và bằng chứng từng phiên |

Quy ước: mét, giây, radian; pose tại tâm trục sau; x hướng trước, y trái, yaw dương ngược chiều kim đồng hồ. Timestamps mô phỏng dùng cùng đồng hồ phiên. Khi kết nối cảm biến thật phải xác định chuyển hệ tọa độ và đồng bộ thời gian.

Giới hạn: profile nhiễu là giả định, chưa đo trên xe; preview hiện là rollout lý tưởng. Vật xuất hiện ngay trong thân hoặc quá gần để phanh có thể gây FAULT. Không coi cờ dừng mô phỏng là bằng chứng phanh/E-stop phần cứng.

[Biên bản đối chiếu giai đoạn 0](docs/GIAI_DOAN_0.md).
