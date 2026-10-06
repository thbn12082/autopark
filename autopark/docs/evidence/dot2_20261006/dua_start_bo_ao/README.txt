Đua ở cổng START của test bo ảo QEMU (06/10/2026, máy bàn, commit 470abb3; kiểm trên máy tính với bo ảo QEMU,
firmware thật trong QEMU, xe mô phỏng phía laptop)

Hiện tượng: lượt toàn bộ test .venv-train trên commit 470abb3 (06/10/2026, bắt đầu 14:57, tải CPU 42 % vì các tác tử
thiết kế đợt sau chạy cùng lúc) hỏng đúng một test, tests/test_firmware_qemu.py::test_parking_session_through_qemu_board,
sau 0,159 s: "Không bắt đầu được (VehicleIO: gửi lệnh tới bo): Xe đang chuyển động (trung bình +0.007 m/s trên 3 khung,
tham chiếu của bo +0.004 m/s): chỉ bắt đầu khi xe đứng yên". Cùng commit, 10 lượt chạy lặp riêng tệp này (14:43–14:46) và
lượt .venv (bắt đầu 14:46) đều đạt cả 14 test.

Kết luận (101 lượt trên bo ảo, script thi_nghiem.py; bảng ở các tệp .txt, dữ liệu thô .jsonl.gz):
- Cổng START từ chối ĐÚNG; mã sản phẩm không sai. Test ngay trước (test_nonblocking_control_loop_keeps_up_with_telemetry)
  chạy 0,1 m/s rồi stop + DISARM và trả về ngay; firmware còn dốc tham chiếu tốc độ về 0 theo stop_decel 600 mm/s²
  (≈ 167 ms; HELLO của phiên mới không xóa tham chiếu, vehicle_core.cpp). Test đỗ lập đường (≈ 109–135 ms) rồi lấy 3
  khung START (chu kỳ 20 ms của xe mô phỏng phía laptop); khi lập đường nhanh hơn ≈ 95–100 ms, khung START cuối còn
  speed_ref ≠ 0 nên START bị từ chối. Thí nghiệm B (lập đường trước, START ngay sau khi dừng + d) tái hiện đúng câu
  lỗi 2 lần (B#4, B#13: speed_ref 28/16/4 mm/s, xe mô phỏng 6/12/4 mm/s).
- Không phải khung telemetry cũ: firmware ghi session_id vào khung lúc dựng khung; laptop bỏ khung khác phiên, khung
  tới trước HELLO_ACK và khung có số thứ tự cũ (autopark/transport/vehicle_io.py). 12/101 lượt nhận đúng 1 khung của
  phiên trước làm thông điệp đầu tiên trên kết nối mới; cả 12 bị lọc (foreign_session), 0 khung như thế lọt vào mẫu
  START. Độ trễ của 303 khung START: 4,0–7,8 ms (khung mới).
- Tải CPU không phải nguyên nhân trực tiếp: tải nhân tạo (8 tiến trình bận, tải 50–59 %) làm lập đường chậm đi nên
  START không hỏng lần nào (C: 0/15). Chuỗi như test, không tải: 0/20 lượt hỏng nhưng 14/20 lượt có ít nhất một khung
  START mang speed_ref ≠ 0 (qua được nhờ khung cuối). Lập đường ghim vào lõi P: trung vị 97–109 ms, thấp nhất 93 ms
  (i9-14900: 8 lõi P + 16 lõi E; do_lap_duong_loi.py, đầu ra console, không lưu). Vì sao đúng lượt .venv-train hỏng: SUY LUẬN (lập đường lượt đó ≈ 85–95 ms), không đo.
- Sửa: chỉ sửa test (sua_test_bo_ao_dung_yen.diff): hàm wait_board_at_rest chờ bo dốc xong về 0 trước START, và một test
  bo giả chạy ở mọi máy. Với bản vá (E): 12/12 START đạt ở các mức trễ trước đó hỏng; tệp test đã vá chạy với QEMU
  3 lượt, mỗi lượt 15/15 đạt (ban_va_qemu_lan1..3.xml, tên lớp đã bỏ đường dẫn thư mục nháp). Bản vá chưa có trong 470abb3; vào đợt mã sau.

| Thí nghiệm | n | START hỏng | stop→HELLO (ms) | Δτ khung START cuối (ms) | lập đường (ms) |
|---|---|---|---|---|---|
| A: như test, d = 0 | 6 | 0 | 111–160 | 180–230 | 109–135 |
| A: d = 0,05 / 0,1 / 0,2 / 0,4 | 24 | 0 | 175–559 | 250–630 | 107–149 |
| D: như test, d = 0, ghim lõi P | 14 | 0 | 112–167 | 180–240 | 109–147 |
| C: 8 tiến trình bận, d = 0 / 0,05 | 10 / 5 | 0 / 0 | 162–248 | 230–340 | 136–200 |
| B: lập đường trước, START sau dừng + d, d = 0 / 0,04 / 0,06 | 3 mỗi mức | 3 / 3 / 3 | 2–80 | 70–150 | — |
| B: d = 0,08 / 0,09 | 3 mỗi mức | 2 / 1 | 83–110 | 160–180 | — |
| B: d = 0,10 tới 0,20 (5 mức) | 15 | 0 | 102–222 | 170–290 | — |
| E: như B (d = 0 / 0,04) + bản vá | 12 | 0 | 165–226 | 240–290 | — |

Δτ: τ khung START cuối − τ khung RUNNING cuối của phiên trước, theo đồng hồ của bo.

Chạy lại (trong thư mục autopark của repo; cần QEMU và ảnh esp32s3_qemu như tests/test_firmware_qemu.py; script dùng
đường dẫn D:/xetulai/autopark/autopark của máy bàn):
  .venv\Scripts\python.exe -X utf8 <thư mục này>\thi_nghiem.py --out ket_qua.jsonl --delays 0,0.05,0.1,0.2,0.4 --reps 4
  thêm --load 8 (tải nhân tạo), --preplan (lập đường trước, như B), --affinity <mặt nạ hex> (ghim CPU), --fix (bản vá)
  .venv\Scripts\python.exe -X utf8 <thư mục này>\tom_tat.py ket_qua.jsonl
Phụ: thong_ke_phu.py (khung đầu trên kết nối mới, trễ HELLO→ACK), do_lap_duong.py, do_lap_duong_loi.py (thời gian lập
đường, ghim lõi), kiem_bo_gia.py (bo giả có tái hiện dốc còn dở không).
