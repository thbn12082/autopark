# Kiểm máy mới — 2026-09-29T12:59:49

Máy: Intel64 Family 6 Model 183 Stepping 1, GenuineIntel, 32 luồng, RAM 63.7 GB, Windows-11-10.0.26200-SP0. GPU: NVIDIA RTX 4000 Ada Generation (20.0 GB), driver 596.71, torch 2.11.0+cu128 CUDA 12.8, OpenCV 5.0.0, Python 3.12.10.

Bước lỗi: không có.

| Số đo | Máy này | Máy bàn (tham chiếu) |
|---|---|---|
| Camera thấy qua DirectShow / có số cổng hub | 4 | 4 |
| … trong đó có số cổng hub | 4 | 4 |
| LiDAR: cổng COM | COM3 | COM4 |
| LiDAR: tốc độ quay (Hz) | 10,00 | 9,99 |
| LiDAR: số tia mỗi vòng (trung vị) | 508 | 508 |
| AI: một lô 4 ảnh 480p, trung vị (ms) | 10,8 | 10,4 |
| AI: một lô, p95 (ms) | 12,1 | 11,4 |
| AI: VRAM đỉnh (MB) | 78 | 78 |
| Bàn thử 480p: khung tốt/s từng camera | 23,85 / 24,37 / 23,85 / 23,84 | 23,85 / 23,85 / 23,85 / 23,84 |
| Bàn thử 480p: khung hỏng từng camera | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| Bàn thử 480p: bộ AI/s | 23,85 | 23,85 |
| Bàn thử 480p: một lô AI, trung vị (ms) | 14,1 | 13,2 |
| Bàn thử 480p: làm nóng AI theo cỡ lô (ms) | 4 ảnh 1522 / 3 ảnh 1469 / 2 ảnh 1658 / 1 ảnh 1414 | 4 ảnh 1482 / 3 ảnh 1448 / 2 ảnh 1553 / 1 ảnh 1410 |
| … tổng làm nóng AI (s) | 6,1 | 5,9 |
| Bàn thử 480p: tuổi kết quả AI, trung vị (ms) | 35,9 | 44,6 |
| Bàn thử 480p: LiDAR (Hz) | 10,01 | 10,01 |
| Bàn thử 480p: CPU tiến trình (lõi) | 0,81 | 0,77 |
| Bàn thử 480p: GPU (%) | 23 | 24 |
| Bàn thử 480p: quy tắc chờ camera chậm | nhịp riêng: max(60 ms; 1,5 × chu kỳ của chính từng camera) | nhịp riêng: max(60 ms; 1,5 × chu kỳ của chính từng camera) |
| Bàn thử 480p: số bộ ảnh | 2861 | 2861 |
| … bộ thiếu camera chậm | 0 | 0 |
| … độ lệch bộ ảnh trung vị / p95 / max (ms) | 17,1 / 32,0 / 35,9 | — |
| 720p chỉ camera: khung tốt/s | 23,83 / 23,83 / 23,87 / 23,83 | 23,83 / 23,87 / 23,87 / 23,87 |
| 720p chỉ camera: khung hỏng | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| 720p chỉ camera: quy tắc chờ camera chậm | nhịp riêng: max(60 ms; 1,5 × chu kỳ của chính từng camera) | nhịp riêng: max(60 ms; 1,5 × chu kỳ của chính từng camera) |
| 720p chỉ camera: bộ ảnh | 715 | 716 |
| … bộ thiếu camera chậm | 0 | 0 |
| … số lần từng cổng bị bỏ vì chậm | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| … độ lệch bộ ảnh trung vị / p95 / max (ms) | 26,0 / 30,2 / 32,8 | — |

Ghi chú:
- Khung hỏng ở 720p phụ thuộc cảnh camera nhìn (cảnh nhiều chi tiết cho khung JPEG lớn hơn): so hai máy thì đặt camera nhìn cùng một cảnh.
- Ô '—': không có số (bước lỗi, hoặc tệp tham chiếu không lưu số đó — cả hai tệp tham chiếu 24/09/2026 đều không lưu độ lệch bộ ảnh; tệp 15:25 không lưu cả quy tắc chờ lẫn làm nóng AI).
- Tham chiếu máy bàn (`tham_chieu_20260924_toi.json`): máy bàn i9-14900 + RTX 4000 Ada, 24/09/2026 19:08 (tối), lệnh may_moi đầy đủ, mã CHƯA COMMIT trên HEAD 2bd37b6: quy tắc chờ theo nhịp RIÊNG từng camera (policy.wait_rule = own_cadence) và làm nóng AI mọi cỡ lô (warm_up_ms [1482.4, 1447.6, 1552.9, 1410.4]); camera vẫn nhìn chỗ tối như lúc 15:25 nên khung bị cắt ở 720p chỉ đúng cho cảnh đó. Lần này ở 720p cả bốn camera ≈ 23,85 khung/s (lúc 15:25 và 17:56 cổng 1 chạy 29,3): nhịp camera nhanh đổi giữa các lần mở. Bộ bỏ camera khỏe 0 ở 480p (2861 bộ) và 720p (716 bộ). Tệp cũ tham_chieu_20260924.json (15:25, quy tắc cũ, chưa làm nóng) giữ lại để đối chiếu; may_moi dùng tệp đứng cuối theo tên, tức tệp này.
- Chi tiết từng bước: `may_moi.json`, `*.rig.json`, `lidar/`, `ai_latency.json`, `usb_topology.json`.
