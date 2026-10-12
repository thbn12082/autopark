# Việc cần người ở cạnh thiết bị

Danh sách này gom các việc chỉ làm được khi có người ở cạnh máy bàn, bốn camera và LiDAR C1, hoặc khi có thêm thiết bị
chưa ở bàn hay chưa có: laptop nộp đồ án, camera trên cao, xe MN300, bo ESP32-S3. Các việc xếp theo thứ tự nên làm ở lần
tới có người ở bàn thử. Danh sách viết ngày 02/10/2026; trạng thái của từng việc tính tới ngày đó. Vài ghi chú có ngày
06/10/2026: cách chạy lệnh dài (việc 1 và việc 7) và việc push mã của đợt 2 (việc 7).

Mỗi việc ghi: mục đích và kịch bản nghiệm thu mà nó mở khóa, điều kiện trước, các bước kèm lệnh, thời gian dự kiến, nơi
ghi kết quả và trạng thái. Kịch bản nghiệm thu ở [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md); các điều kiện của V1
ở [NGUONG_NGHIEM_THU_DE_XUAT.md](NGUONG_NGHIEM_THU_DE_XUAT.md) mục 11.2. Lệnh được chép từ tài liệu chi tiết liên kết ở
từng việc và đã đối chiếu với mã ngày 02/10/2026; giải thích đầy đủ nằm ở tài liệu đó.

**Viết tắt dùng trong tệp:**

- V1: bản đầu cần đạt, gồm 10 điều kiện.
- MP, BT, XT: ba mức thử, lần lượt là mô phỏng, bàn thử (LiDAR và camera thật, xe ảo) và xe thật.
- DO, DI, VC, NT, CB, AT, DV, LD: mã kịch bản nghiệm thu; N-…: mã ngưỡng; T1–T15: công cụ nghiệm thu (kịch bản nghiệm
  thu mục 7).
- R1, R3, R7: phương pháp đo độc lập, lần lượt là camera trên cao, video có thước trong khung, đồng bộ video với log.
  TC-1: kiểm tham chiếu trên cao bằng xe giả.
- ĐK-AI, ĐK-XT: nhóm điều kiện trước dùng chung, cho kịch bản dựa vào camera/AI và cho mọi lần chạy có động lực trên sàn
  (kịch bản nghiệm thu mục 1.3).
- GVHD: giảng viên hướng dẫn. EcoQoS: chế độ tiết kiệm của Windows 11, có thể hạ tốc tiến trình.

**Vì sao các việc này cần người.** Ngày 02/10/2026 người dùng đồng ý làm theo đề xuất: được chạy LiDAR và camera khi
không có người trông, còn ảnh cảnh sa bàn chỉ lưu cục bộ trong `runs/` (git bỏ qua), không commit. Ngày đó các việc
chạy được từ xa đã làm. Các việc dưới đây cần tay người (khởi động lại máy, quay camera, in và dán, đo bằng thước, đặt
hay kéo vật, rút cáp) hoặc cần thiết bị chưa có.

**Đã làm từ xa ngày 02/10/2026, không cần làm lại** ([CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 12–14):

- `camera_bench measure` bốn camera 640×480, 60 s: mỗi camera 23,8 khung/s thật, 0 khung hỏng.
- `fusion.demo` 30 s với C1 thật: COMPLETED, 0 lỗi đọc. Lần chạy này dùng driver cũ.
- LD-1 trên máy bàn: lần 3 chạy đủ 30 phút có ghi phiên. Bốn camera 23,85 khung/s, LiDAR 10,008 Hz và 0 lỗi, AI 23,75
  bộ/s, ghi 4,44 MB/s, bỏ 0. Đây chưa phải lượt nghiệm thu LD-1, vì còn thiếu hai điều kiện của việc 1 và chưa chạy
  trên laptop (việc 7).
- Bản sửa driver C1, đã thử trên C1 thật. Driver nay đọc bỏ byte cũ ở cổng CP210x, nơi `reset_input_buffer()` không xóa
  gì.
- Đo vòng điều khiển 50 Hz khi cửa sổ thu nhỏ, với SIM và bo mô phỏng. Để Windows tự quyết thì thời gian tính mỗi bước
  chậm 1,73–1,76 lần; ứng dụng tự tắt EcoQoS thì hết chậm.
- Ứng dụng chạy hai lần đỗ qua bo ảo QEMU thật: firmware thật chạy trong QEMU, xe mô phỏng phía laptop, không ai bấm.
- Kiểm tĩnh nguồn tư thế LiDAR (T2) trên C1 thật đứng yên trên bàn, nhìn cảnh phòng chứ chưa phải sa bàn. Bản đồ một
  chỗ đặt `--anchor 0 0 0`; sau khởi tạo 269/269 vòng OK; tư thế dao động trong 3,0 mm / 2,6 mm / 0,06°. Đây là độ lặp
  lại tĩnh, không phải độ chính xác so với thước (mục 12.3 của [CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md)).

**Còn làm được từ xa, không thuộc danh sách này:**

- đọc trạng thái EcoQoS của cửa sổ `run_app.py` thật từ một tiến trình khác (chưa thử,
  [CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 10.1);
- chạy lại LD-1 khi việc 1 đã quay camera nhìn sa bàn.

**Quy ước.**

- Mỗi lệnh một dòng, chạy trong thư mục `autopark` của repo (thư mục có pyproject.toml), dán được vào cmd.exe. Thay
  `<ngay>` (yyyymmdd), `<ten>`, `<lan>`… bằng giá trị thật, tên không dấu.
- Lệnh mở camera, LiDAR hay cổng COM là lệnh chạm thiết bị, nên người ở bàn chạy. Cổng LiDAR lấy từ
  `configs/thiet_bi.json` (máy bàn: COM3); `--port COMx` ghi đè cho một lần.
- Mã phải có các thay đổi của đợt 2 (02/10/2026), nhất là bản sửa driver C1 ([CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục
  12.2).
- Ảnh và video camera (sa bàn, phòng, xe) chỉ để trong `runs/`. Vào `docs/evidence/` chỉ chép tệp chữ, JSON, CSV. Git
  chỉ giữ tệp CSV khi nó nằm thẳng trong `docs/evidence/`, không trong thư mục con
  ([KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 2.3).
- Thời gian dự kiến là ước tính khi không ghi nguồn: chưa ai làm các việc này với thiết bị thật.

## Tóm tắt và thứ tự

Sơ đồ dưới cho thấy việc nào mở khóa việc nào và mở khóa kịch bản nghiệm thu nào. Mũi tên đi từ một việc tới điều mà việc
đó mở khóa.

```mermaid
flowchart TD
    DA["Đã đo 02/10/2026 trên máy bàn: LD-1 30 phút, driver C1 đã sửa"]
    MP["Đã chạy ở mức mô phỏng: phiên đỗ qua bo mô phỏng và bo ảo QEMU"]
    XE["Xe MN300 có cảm biến gá cứng"]
    V1["1. Bốn camera: danh tính sau khởi động lại, nhìn sa bàn"]
    V2["2. LiDAR trên bàn: bảy lần đặt hộp, DV-2, DV-1"]
    V3["3. Điều kiện tiên quyết T2: bản đồ, gá LiDAR, tệp cấu hình"]
    V4["4. Nội tham bốn camera"]
    V5["5. ui.lidar_app với thiết bị thật, ghi cảm biến T3"]
    V6["6. Bàn thử: CB-1, CB-3, VC-1, VC-2, VC-3, VC-6"]
    V7["7. Laptop nộp đồ án: do_may_moi, LD-1"]
    V8["8. T14 trên màn hình laptop, độ trễ hiển thị L"]
    V9["9. Camera trên cao: T11, T4, TC-1"]
    V10["10. Ngoại tham và ROI"]
    V11["11. Bo ESP32-S3: nạp, kiểm kết nối, E-stop"]
    LD1["LD-1 trên máy nghiệm thu, N-C5"]
    DV["DV-1, DV-2: điều kiện V1 số 1"]
    AI["ĐK-AI: NT-1 tới NT-5"]
    XT["Kịch bản trên xe thật: DO, DI, VC, CB, AT, DV-3"]
    DA --> LD1
    V1 --> LD1
    V7 --> LD1
    V2 --> DV
    V2 --> V3
    V1 --> V4
    V4 --> V10
    V10 --> AI
    V1 --> V5
    V5 --> V6
    V8 -->|R7| V6
    V3 --> XT
    V9 -->|R1 và TC-1| XT
    V11 --> XT
    MP --> V11
    XE -.-> V3
    XE -.-> V10
    XE -.-> XT
    classDef daco fill:#dff0d8,stroke:#3c763d,color:#1b3a1b
    classDef giaLap fill:#fcf8e3,stroke:#8a6d3b,color:#4d3b12
    classDef chuaLam fill:#f2dede,stroke:#a94442,color:#4d1a1a,stroke-dasharray: 4 3
    class DA daco
    class MP giaLap
    class XE,V1,V2,V3,V4,V5,V6,V7,V8,V9,V10,V11,LD1,DV,AI,XT chuaLam
```

Màu ô: xanh là đã có và đã kiểm/đo; vàng là chỉ trong mô phỏng/giả lập; đỏ viền đứt là chưa làm hoặc chưa thử trên thiết
bị. Mũi tên đứt là chỗ cần xe MN300 có cảm biến gá, hiện chưa có.

| Thứ tự | Việc | Cần có | Mở khóa | Trạng thái 02/10/2026 |
|---|---|---|---|---|
| 1 | Bốn camera: danh tính và hướng sau khởi động lại; nhìn sa bàn thật | máy bàn, bốn camera, sa bàn | hai điều kiện trước phiên của LD-1 (N-C5); điều kiện V1 số 2 | **Chưa kiểm** |
| 2 | LiDAR trên bàn: bảy lần đặt hộp (p04), DV-2, DV-1 | C1, thước, hộp, xe giả có thước thẳng ≥ 0,65 m | DV-1, DV-2 (N-L0 … N-L4); ba điều kiện tiên quyết của T2; điều kiện V1 số 1 | **Chưa thử** |
| 3 | Điều kiện tiên quyết T2: bản đồ phiên, gá LiDAR, tệp cấu hình | việc 2; sa bàn thật; xe MN300 (phần gá) | VehicleIO với bo thật (mọi kịch bản XT), CB-6, DV-3 | gá GIẢ ĐỊNH – CHƯA ĐO; bản đồ phiên **Chưa làm** |
| 4 | Nội tham bốn camera | bảng in dán phẳng, thước | việc 10; ĐK-AI (NT-1 … NT-5); điều kiện V1 số 2, 3 | **Chưa làm** |
| 5 | `ui.lidar_app` với C1 và camera thật, ngăn "Ghi cảm biến" (T3) | việc 1; `.venv-train` | bản ghi cảm biến GD3 của mọi kịch bản; DV-3; MB/s cảnh sa bàn | **Chưa thử** |
| 6 | Bàn thử cần tay: CB-1, CB-3, VC-1, VC-6, VC-2, VC-3 | việc 5; hộp có dây kéo | phần BT của các kịch bản đó (điều kiện V1 số 8, mức BT) | **Chưa thử** |
| 7 | Laptop nộp đồ án: `do_may_moi`, LD-1 | laptop, hub với bốn camera, C1 | LD-1 trên máy nghiệm thu; số N-C, N-T trên máy đó | **Chưa đo** |
| 8 | T14 trên màn hình laptop, độ trễ hiển thị L | laptop; một camera quay màn hình | R7 của VC-1, VC-2, VC-3, CB-1, CB-3 và mọi kịch bản dùng R7 | **Chưa thử**; L **chưa đo** |
| 9 | Camera trên cao: T11, T4, TC-1 | camera trên cao (chưa chốt), giá, tờ ArUco in, thước, xe giả | R1 và TC-1 (thuộc ĐK-XT); chấm DO-1 … DO-6, DV-3, NT-2 | **Chưa thử** |
| 10 | Ngoại tham và ROI | việc 4; xe MN300 có camera gá cứng | ĐK-AI (NT-1 … NT-5), N-G1, N-G2; điều kiện V1 số 2, 3 | **Chưa làm** |
| 11 | Bo ESP32-S3: nạp, "Kiểm kết nối bo", CLEAR_FAULT, E-stop; firmware 100 mm/s | bo ESP32-S3 | T1 với bo thật; ĐK-XT; AT-1 … AT-5, CB-4, CB-5, DI trên xe và mọi kịch bản XT; điều kiện V1 số 6, 9 | **Chưa làm** (chưa có bo) |

Thứ tự đề xuất cho lần tới:

- Với thiết bị đang có ở bàn: 1 → 2 → 4 → 5 → 6, và bản đồ của việc 3 khi sa bàn thật đã dựng.
- Mang laptop tới: 7, 8.
- Có camera trên cao: 9. In tờ ArUco và đo mốc sàn làm được trước.
- Có xe: phần gá của việc 3 và việc 10.
- Có bo: 11.

## 1. Bốn camera: danh tính và hướng sau khởi động lại, nhìn sa bàn thật

**Mục đích và việc mở khóa.** Việc này kiểm hai điều kiện trước phiên của LD-1 mà lượt 02/10/2026 chưa kiểm
([KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 5.8; [CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 12.1):

- camera nhìn sa bàn thật;
- khởi động lại máy 3 lần, mỗi lần chụp một bộ ảnh để kiểm từng camera đúng hướng theo cổng hub. Đây là N-C5: tuyệt đối
  4/4 đúng ở mỗi lần, ít nhất 3 lần ([NGUONG_NGHIEM_THU_DE_XUAT.md](NGUONG_NGHIEM_THU_DE_XUAT.md) mục 6), thuộc điều kiện
  V1 số 2.

Camera nhìn sa bàn thật còn cần cho MB/s của cảnh sa bàn (bước 5, việc 5) và cho ảnh sa bàn để gán nhãn tập chấm
([GAN_NHAN_SA_BAN.md](GAN_NHAN_SA_BAN.md)).

**Điều kiện trước.** Hub UGREEN với bốn camera ở cổng hub 1–4 ([usb_topology.md](usb_topology.md)); sa bàn đã dựng, ít
nhất là mặt sàn. Cổng nào là hướng trước, sau, trái, phải thì chưa chốt; sẽ ghi theo cổng khi có gá trên xe. Tới lúc đó,
chỉ cần kiểm rằng mỗi cổng hub vẫn là đúng camera, đúng cảnh.

**Các bước.**

1. Quay bốn camera nhìn sa bàn thật, mỗi camera một phía. Ghi lại cổng hub nào nhìn phía nào; gợi ý: đặt trong khung mỗi
   camera một tờ giấy ghi số cổng.
2. Ghi bảng cổng hub → index OpenCV và InstanceId. Lệnh tự tạo thư mục:
   ```cmd
   .venv\Scripts\python.exe -X utf8 -m autopark.video.camera_bench list --out docs\evidence\thiet_bi_<ngay>\usb_topology_lan0.json
   ```
3. Chụp một bộ ảnh. Mở lệnh dưới, bấm "Chụp bộ ảnh", rồi đóng cửa sổ. Ảnh gốc từng camera, tên theo cổng hub, vào
   `runs\rig_snapshots\<ngày_giờ>\cam_p<N>.png`.
   ```cmd
   .venv-train\Scripts\python.exe -X utf8 -m autopark.ui.rig_app --ports 1 2 3 4 --no-ai
   ```
4. Khởi động lại máy, lặp bước 2 (tệp `usb_topology_lan<k>.json`) và bước 3. So với lần trước: InstanceId của từng cổng
   không đổi; ảnh `cam_p<N>` của mỗi cổng vẫn đúng camera, đúng cảnh. Làm 3 lần.
5. Khi camera đã nhìn sa bàn, chạy lại LD-1; bước này không cần người ở cạnh
   ([KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 5.8). Trước hết ghi thử 60 s để có MB/s của cảnh sa bàn:
   ```cmd
   .venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 60 --name ld1_thu_ghi --out runs\rig_bench\<ngay> --record runs\rig_recordings\<ngay>_ld1_thu_ghi
   ```
   Sau đó chạy 30 phút, khi ổ còn trống ít nhất MB/s × 1800 cộng phần dư. Thư mục `--record` phải chưa có hoặc rỗng.
   ```cmd
   .venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 1800 --name ld1 --out runs\rig_bench\<ngay> --record runs\rig_recordings\<ngay>_ld1
   ```
   Cách chạy hai lệnh trên, đề xuất ngày 06/10/2026, chưa chốt:
   - Chạy qua wrapper `chay_co_theo_doi.py` để có PID, mã thoát 32 bit, minidump nếu crash và hạn giờ. Dùng `--het-gio`
     300 s cho lệnh 60 s, 2400 s cho lệnh 30 phút. Ví dụ:
     ```cmd
     .venv\Scripts\python.exe -X utf8 docs\evidence\su_co_thoat_20261006\chay_co_theo_doi.py --ra runs\thiet_bi_<ngay>\ld1 --het-gio 2400 --theo-doi -- .venv-train\Scripts\python.exe -X utf8 -X faulthandler -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 1800 --name ld1 --out runs\rig_bench\<ngay> --record runs\rig_recordings\<ngay>_ld1
     ```
   - Không dùng wrapper thì mở lệnh từ PowerShell, không từ Git Bash. Tiến trình mở từ Git Bash mang ErrorMode 0x3, nên
     Windows Error Reporting không ghi sự kiện hay minidump khi crash.
   - Trước khi chạy, báo các phiên tác tử Claude khác trên máy không dừng tiến trình python theo tên hay theo cỡ bộ nhớ.
     Ngày 02/10/2026 một phiên như thế đã dừng nhầm LD-1 lần 1 ([CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 16).
   - Tải CPU của `--theo-doi`: chưa đo.
   - Để `--ra` ngoài git (`runs\`). **Không** chép `theo_doi\python.csv`, `theo_doi\gpu_app.csv` hay `lenh_giet.txt` của
     wrapper vào `docs\evidence`. Các tệp đó có thể chứa dòng lệnh hay tên của tiến trình khác trên máy, kể cả của dự án
     khác.

**Thời gian.** ≈ 30 phút cho ba lần khởi động lại. Chạy lại LD-1 mất thêm ≈ 32 phút, không cần người.

**Ghi kết quả.** Các tệp `usb_topology_lan<k>.json` và một bảng "4/4 đúng hay không" cho từng lần đặt ở
`docs\evidence\thiet_bi_<ngay>\`; ảnh chỉ ở `runs\rig_snapshots\`. Kết luận ghi vào [usb_topology.md](usb_topology.md)
(mục "Điều chưa làm" có việc này) và một mục mới có ngày trong [CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md).

**Trạng thái 02/10/2026.** Chưa kiểm trên máy bàn hiện tại. Lần kiểm khởi động lại duy nhất là ngày 23/09/2026 trên máy
bàn cũ: InstanceId từng cổng giữ nguyên, index OpenCV đổi ([usb_topology.md](usb_topology.md)). Ngày 02/10/2026, cổng →
index là 1 → 0, 2 → 2, 3 → 1, 4 → 3 ([camera_list.txt](evidence/thiet_bi_20261002/camera_list.txt)); camera nhìn gì thì
chưa ai kiểm.

## 2. LiDAR trên bàn: bảy lần đặt hộp, DV-2, DV-1

**Mục đích và việc mở khóa.** Việc này mở khóa DV-1 (N-L0 … N-L3, N-T7) và DV-2 (N-L4) ở
[KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 5.7. Hai kịch bản này cùng DV-3 (cần xe) thuộc điều kiện V1 số 1.
Ba điều kiện tiên quyết của T2 cho bo thật (việc 3) cũng đến từ đây:

- dấu góc trái/phải của C1, chốt bằng lần đặt hộp bên trái p04. Dấu này chưa xác minh bằng vật thật
  ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 6b);
- nguyên nhân lệch hướng +4,3° giữa hai lần bật (DV-2);
- định vị tĩnh so với thước (DV-1).

**Điều kiện trước.** C1 ở cổng ghi trong `configs/thiet_bi.json`; mã có bản sửa driver C1. Dụng cụ:

- thước thép ≥ 3 m, thước kẹp, băng dính; hộp mặt trắng mờ rộng ≥ 30 cm và một hộp đen;
- cho DV-1: "xe giả" mang C1, có dấu tâm quay và một thước thẳng cứng ≥ 0,65 m (nên 1 m) gắn song song trục hướng
  ([KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 3.2). Vạch 0,25 m hay thước đo góc không đủ cho N-L2, vì N-L2 cần
  tham chiếu hướng ≤ 0,67°.

**Các bước.**

1. Bảy lần đặt hộp ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 6). Dán C1 cố định trên bàn phẳng, đánh dấu tâm
   quay, đo bằng thước từ tâm quay tới mặt hộp. Lần đầu làm nóng 2 phút:
   ```cmd
   .venv\Scripts\python.exe -X utf8 -m autopark.lidar.bench record --out runs\lidar_bench\<ngay> --name p01_truoc_0.5m --seconds 15 --warmup 120 --expected-distance 0.50 --expected-angle 0
   ```
   Sáu lần sau dùng cùng lệnh, bỏ `--warmup 120` và đổi ba tham số:

   | Lần | `--name` | `--expected-distance` | `--expected-angle` |
   |---|---|---|---|
   | p02 | `p02_truoc_1m` | 1.00 | 0 |
   | p03 | `p03_truoc_2m` | 2.00 | 0 |
   | p04 | `p04_trai_1m` | 1.00 | 90 |
   | p05 | `p05_phai_1m` | 1.00 | -90 |
   | p06 | `p06_sau_1m` | 1.00 | 180 |
   | p08 | `p08_den_truoc_1m` (hộp đen; thêm `--note "hop den"`) | 1.00 | 0 |

   Lập bảng kết quả:
   ```cmd
   .venv\Scripts\python.exe -X utf8 -m autopark.lidar.bench report runs\lidar_bench\<ngay>
   ```
   Ngưỡng đạt đề xuất (N-L0): sai số ≤ 30 mm, hướng lệch ≤ 5°, 8–12 Hz, số tia mỗi vòng trong ±5 % của 5 kHz ÷ tần số,
   không trống quá 3 chu kỳ. Nếu p04 cho góc âm thì dấu góc ngược: thêm `--mirror` và ghi lại lý do.
2. DV-2, 5 cặp phiên. Dán C1 cố định, không chạm vào. Dán dấu băng dính quanh đế, chụp ảnh đế trước và sau; ảnh chỉ để
   trong `runs\`. Phiên một:
   ```cmd
   .venv\Scripts\python.exe -X utf8 -m autopark.lidar.bench record --out runs\lidar_bench\<ngay> --name dv2_c1_a --seconds 20 --warmup 5
   ```
   Chờ lệnh xong (mô-tơ dừng), rồi chạy phiên hai với `--name dv2_c1_b`; mỗi cặp một tên riêng. Dựng bản đồ từ phiên một,
   rồi định vị phiên hai:
   ```cmd
   .venv\Scripts\python.exe -X utf8 -m autopark.lidar.occupancy --recording runs\lidar_bench\<ngay>\dv2_c1_a.npz --out runs\lidar_bench\<ngay>\map_dv2
   .venv\Scripts\python.exe -X utf8 -m autopark.lidar.localize --map runs\lidar_bench\<ngay>\map_dv2 --recording runs\lidar_bench\<ngay>\dv2_c1_b.npz --out runs\nghiem_thu\<ngay>\dv2_b --skip-seconds 3
   ```
   N-L4 (đề xuất): |Δθ| ≤ 0,2° giữa hai phiên liên tiếp.
3. DV-1, ≥ 6 tư thế × 2 loạt, mỗi loạt một bản đồ mới, làm cùng buổi với bước 1. Đặt xe giả trên sàn sa bàn; ghi bản đồ
   ở gốc:
   ```cmd
   .venv\Scripts\python.exe -X utf8 -m autopark.lidar.bench record --out runs\lidar_bench\<ngay> --name dv1_goc --seconds 20 --warmup 5
   .venv\Scripts\python.exe -X utf8 -m autopark.lidar.occupancy --recording runs\lidar_bench\<ngay>\dv1_goc.npz --out runs\lidar_bench\<ngay>\map_dv1
   ```
   Dời xe giả tới từng tư thế, ví dụ (+0,20; 0), (0; +0,20), (+0,30; −0,20) m với hướng 0°, +10°, −20°. Đo tọa độ hai
   đầu thước bằng thước thép so với mốc sàn, rồi chạy:
   ```cmd
   .venv\Scripts\python.exe -X utf8 -m autopark.lidar.bench record --out runs\lidar_bench\<ngay> --name dv1_d01 --seconds 15 --warmup 5
   .venv\Scripts\python.exe -X utf8 -m autopark.lidar.localize --map runs\lidar_bench\<ngay>\map_dv1 --recording runs\lidar_bench\<ngay>\dv1_d01.npz --out runs\nghiem_thu\<ngay>\dv1_d01 --skip-seconds 3
   ```
   So `summary.ok_pose_median` của `localize.json` với số đo thước; hướng so theo hiệu đã quấn về ±180°. Tư thế ngoài bản
   đồ phải ra FAILED hay AMBIGUOUS, không được OK sai (N-L3).

**Thời gian.** Bảy lần đặt hộp ≈ 30–45 phút; DV-2 ≈ 20 phút; DV-1 hai loạt ≈ 1–1,5 giờ; tổng ≈ 2–3 giờ.

**Ghi kết quả.**

- Bản ghi ở `runs\lidar_bench\<ngay>\` và `runs\nghiem_thu\<ngay>\` (git bỏ qua).
- Bước 1: `*.analysis.json`, hình vòng quét `*.png` và `report.md` vào `docs/evidence/lidar/`; cập nhật
  [gate_01.md](gate_01.md) ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 6).
- DV-1, DV-2: `localize.json` vào `docs\evidence\thiet_bi_<ngay>\`; biên bản thước dạng CSV đặt thẳng trong
  `docs\evidence\`, ví dụ `docs\evidence\dv1_thuoc_<ngay>.csv`. Trạng thái DV-1, DV-2 ghi vào
  [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 4 và 5.7. Nếu đạt thì điền điều kiện tiên quyết ở việc 3, bước 4.

**Trạng thái 02/10/2026.** Bảy lần đặt hộp chưa làm; DV-1, DV-2 chưa thử.

## 3. Điều kiện tiên quyết T2 cho bo thật: bản đồ phiên, gá LiDAR, tệp cấu hình

**Mục đích và việc mở khóa.** Hiện nay, Bắt đầu đỗ ở VehicleIO với bo thật luôn bị từ chối trước mọi I/O
(START_POSE_UNVERIFIED). Lệnh chỉ được nhận khi `configs/dinh_vi_lidar_v0.json` ghi gá LiDAR đã đo và ba điều kiện tiên
quyết đã đạt, có bằng chứng ([NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md) mục 1, 6). Việc này mở đường cho mọi kịch bản
trên xe thật dùng nguồn tư thế LiDAR (DO, DI, VC, CB, AT), cho CB-6 và DV-3; nó thuộc điều kiện V1 số 1. Sau việc này
vẫn còn hai chỗ chặn: T8 (firmware chưa đọc tốc độ, góc lái, nên START_CHECK từ chối) và việc 11.

**Điều kiện trước.** Việc 2 xong. Sa bàn thật đã dựng, hệ tọa độ sa bàn đã kiểm vuông
([KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 3.3). Riêng phần gá cần xe MN300 có C1 gá cứng; xe chưa có.

**Các bước.**

1. Dựng bản đồ của phiên trên sa bàn thật, từ nhiều chỗ đặt. Bước này làm được trước khi có xe
   ([NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md) mục 2). Mỗi chỗ đặt là một bản ghi C1 đứng yên, ví dụ:
   ```cmd
   .venv\Scripts\python.exe -X utf8 -m autopark.lidar.bench record --out runs\lidar_bench\<ngay> --name cho_1 --seconds 20 --warmup 5
   ```
   Chỗ đặt 1 là mốc neo: tâm quay C1 đo bằng thước trong hệ sa bàn, hướng neo đo bằng thước thẳng ≥ 0,65 m. Dựng bản đồ:
   ```cmd
   .venv\Scripts\python.exe -X utf8 -m autopark.lidar.map_builder --placement runs\lidar_bench\<ngay>\cho_1.npz --anchor X Y YAW_DEG --placement runs\lidar_bench\<ngay>\cho_2.npz --scenario scenarios\sa_ban_3x2_hai_hop.json --out runs\lidar_maps\<ngay>_<ten>
   ```
   `--scenario` là tệp sa bàn ứng với sa bàn thật. Thêm `--pose K X Y YAW_DEG` cho chỗ đặt có số đo thước. Nếu bị từ
   chối thì chỉ có `map_build.json` với `ok` = false, và lệnh thoát mã 1.
2. Thử nguồn tư thế với C1 đứng yên (mức BT):
   ```cmd
   .venv\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app --pose-source lidar_real --lidar-map runs\lidar_maps\<ngay>_<ten>
   ```
   Rồi xem nhãn "Định vị LiDAR: …" (làm mới 5 Hz) ở thẻ "Bo điều khiển". "LiDAR thật" chỉ đi với bo COM. Bắt đầu đỗ với
   bo COM vẫn bị từ chối (START_POSE_UNVERIFIED) cho tới bước 4.
3. Khi có xe: đo gá LiDAR bằng thước, tức tâm quay C1 trong hệ xe. Hệ xe có gốc ở tâm trục sau, x hướng tiến, y sang
   trái, yaw ngược chiều kim đồng hồ.
4. Ghi vào `configs/dinh_vi_lidar_v0.json`. Đây là tệp mã đọc mặc định; mã đọc chặt, khóa lạ là lỗi.
   - Gá: `mount.x_m`, `y_m`, `yaw_deg`, `z_m`, `measured: true`, `measured_on`, `evidence` (đường dẫn tệp trong
     `docs/evidence/`).
   - Với `prerequisites.dau_goc_p04`, `huong_goc_dv2`, `dinh_vi_tinh_dv1`: `ok: true` kèm `evidence`. Ghi `ok` mà thiếu
     `evidence` vẫn tính là chưa đạt.

**Thời gian.** Bản đồ 3–5 chỗ đặt ≈ 30–60 phút; đo gá ≈ 15 phút khi có xe.

**Ghi kết quả.** Bản đồ ở `runs\lidar_maps\<ngay>_<ten>\` (`costmap.json`, `map_build.json`, `placements.csv`…; git bỏ
qua). Bằng chứng gá và các điều kiện vào `docs/evidence/`, trong thư mục có ngày. Tệp cấu hình ghi như bước 4. Cập nhật
[NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md) mục 6, 9.

**Trạng thái 02/10/2026.** Gá GIẢ ĐỊNH – CHƯA ĐO: `measured` false, x 0,095 m, y 0, yaw 0°, nằm giữa hai trục của xe giả
định. Ba điều kiện có `ok` false. Bản đồ phiên trên sa bàn thật chưa làm. Nguồn tư thế LiDAR mới kiểm ở mức MP và trên
bản ghi C1 đứng yên (offline).

## 4. Hiệu chuẩn nội tham bốn camera

**Mục đích và việc mở khóa.** Tạo `calibration/cam_p1.json` … `cam_p4.json`; hiện chưa có tệp nào. Nội tham cần cho
ngoại tham và ROI (việc 10), cho BEV, và để ngăn AI camera được tạo vật cản (ĐK-AI của NT-1 … NT-5). Việc này thuộc điều
kiện V1 số 2, 3.

**Điều kiện trước.**

- In `calibration/bang_in/ban_co_9x6_30mm_A3.pdf` (nên dùng nếu in được A3) hoặc `ban_co_9x6_20mm_A4.pdf`. In 100 %
  ("Actual size", tắt "Fit to page") rồi dán lên tấm phẳng cứng.
- Đo lại cỡ ô bằng thước: lấy 8 ô một hàng chia 8, 5 ô một cột chia 5. Hai số lệch nhau quá 0,5 % thì in lại.
- Bốn camera ở cổng hub 1–4, mode 640×480 MJPG. Đủ đèn, tránh lóa.
- Camera chưa gá thì cố định bảng trên tường và cầm camera di chuyển; về hình học hai cách tương đương.

**Các bước**, mỗi camera một lần ([HIEU_CHUAN_CAMERA.md](HIEU_CHUAN_CAMERA.md) mục 2–4):

1. Mở công cụ, đổi cổng 1..4 cho từng camera:
   ```cmd
   .venv\Scripts\python.exe -X utf8 -m autopark.ui.calib_app --port 1 --square-mm 19.95
   ```
   Cỡ ô là số **đo được**; đánh dấu "Đã đo cỡ ô bằng thước".
2. Chụp 20–30 ảnh, bằng tay hay bằng "Tự chụp". Ảnh phải phủ kín khung hình, nhất là mép và bốn góc (lưới phủ chuyển từ
   đỏ sang xanh). Nghiêng bảng 20–45° quanh cả hai trục, thêm vài ảnh nhìn thẳng ở giữa; giữ yên khi chụp.
3. Bấm "Hiệu chuẩn" (cần ≥ 8 ảnh). Đọc các tiêu chí đề xuất: RMS ≤ 0,5 px, ảnh tệ nhất ≤ 1,0 px, ≥ 15 ảnh được dùng, phủ
   ≥ 70 % và đủ bốn khối góc, ≥ 4 ảnh nghiêng ≥ 20°, sai số chuyển đổi ≤ 0,5 px và `woodscape_intrinsic.ok`. Xem ảnh nắn:
   cạnh bảng phải thẳng ở mọi vị trí. Bấm "Lưu".
4. Kiểm tệp, rồi so fx của bốn camera với nhau:
   ```cmd
   .venv\Scripts\python.exe -X utf8 -m autopark.perception.fisheye_calib check calibration\cam_p1.json
   ```

**Thời gian.** ≈ 20–30 phút mỗi camera, ≈ 1,5–2 giờ cho bốn camera.

**Ghi kết quả.** `calibration/cam_p<N>.json` được commit; bản đã commit là bản chính thức. Ảnh và bản sao ở
`runs/calib/<ngày giờ>_p<N>/` (git bỏ qua). Cập nhật [HIEU_CHUAN_CAMERA.md](HIEU_CHUAN_CAMERA.md) mục 6 và
[calibration/README.md](../calibration/README.md).

**Trạng thái 02/10/2026.** Chưa làm: chưa in bảng, chưa có ảnh bảng nào từ camera thật. Công cụ mới kiểm trên ảnh tổng
hợp.

## 5. `ui.lidar_app` với LiDAR và camera thật, ngăn "Ghi cảm biến" (T3)

**Mục đích và việc mở khóa.** Ghi cảm biến trong phiên đỗ (T3) mới kiểm offscreen với nguồn giả. Cần thử với thiết bị
thật trước khi dùng bản ghi cho nghiệm thu. Bản ghi này cần cho: bản ghi cảm biến GD3 của mỗi lần chạy
([KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 2.2), DV-3 (tái định vị offline từ bản ghi) và phân tích lỗi. Đây
cũng là lần đầu `ui.lidar_app` chạy với C1 và camera thật. Số cần lấy:

- MB/s của cảnh sa bàn, khung bị bỏ, `ecoqos_start`/`ecoqos_stop`;
- ảnh hưởng lên vòng 50 Hz khi bật và tắt ghi, khi cửa sổ thu nhỏ.

**Điều kiện trước.** Việc 1 xong, tức camera nhìn sa bàn thật. Có `.venv-train`, vì AI camera cần torch. Ổ chứa
`runs\session_recordings` còn ≥ 5 GB. Chưa có nội tham, ngoại tham đo và ROI nên ngăn AI camera không tạo vật cản; việc
ghi không phụ thuộc điều đó.

**Các bước** ([GHI_PHAT_LAI_BAN_THU.md](GHI_PHAT_LAI_BAN_THU.md) mục 9):

1. Mở ứng dụng:
   ```cmd
   .venv-train\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app --camera-ai --cam-ports 1 2 3 4 --record-root runs/session_recordings --record-format jpg --jpeg-quality 95 --record-min-free-gb 5
   ```
2. Bật AI camera, kết nối LiDAR. Ở ngăn "Ghi cảm biến": điền Tên (ví dụ `t3_sa_ban`) → "Bắt đầu ghi" → F8 (dấu đầu) →
   Tìm đường đỗ, Bắt đầu đỗ (xe ảo) → xe dừng → F8 (dấu cuối) → "Dừng ghi" → chờ dòng "XONG" → "Xuất log CSV…". Ghi
   khoảng 60 s.
3. Lặp lại một lần với cửa sổ thu nhỏ trong lúc ghi, và một lần chạy không ghi để so.
4. Đọc `meta.json` của bản ghi: MB/s, khung bị bỏ, `session_recording.ecoqos_start`, `ecoqos_stop`; đọc cột `window` của
   `session/clock.csv`.
5. Phát lại thử, không mở thiết bị:
   ```cmd
   .venv-train\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app --camera-ai --session-replay runs/session_recordings/<thư mục>
   ```

`ui.lidar_app` chưa có công cụ đo vòng 50 Hz khi bật và tắt ghi hay khi thu nhỏ. `ecoqos_gui do-chay` chỉ dựng cửa sổ của
`ui.app` với SIM hay bo mô phỏng, không có camera, LiDAR hay ngăn ghi ([CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 13).
Tới khi có công cụ, giữ cửa sổ phóng to khi chạy.

**Thời gian.** ≈ 30–60 phút.

**Ghi kết quả.** Bản ghi ở `runs\session_recordings\` (git bỏ qua; ảnh camera không commit). Số đo (MB/s, khung bỏ,
EcoQoS, trạng thái cửa sổ) ghi vào một mục mới có ngày trong [CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) và vào
[GHI_PHAT_LAI_BAN_THU.md](GHI_PHAT_LAI_BAN_THU.md) mục 9.

**Trạng thái 02/10/2026.** T3 chưa thử với thiết bị thật. MB/s của cảnh sa bàn chưa đo. LD-1 ngày 02/10/2026 đo được
4,44–5,31 MB/s bằng `rig.bench`, nhưng ở cảnh không ai kiểm.

## 6. Bàn thử cần tay người: CB-1, CB-3, VC-1, VC-6, VC-2, VC-3

**Mục đích và việc mở khóa.** Việc này là tiền nghiệm thu mức BT (LiDAR, camera thật; xe ảo) của các kịch bản trên
([KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 5.3, 5.5, 6). Nó phục vụ điều kiện V1 số 8 ở mức BT. Chỉ phần phát
hiện là của cảm biến thật, còn quãng dừng là của xe ảo, nên không thay được mức XT.

**Điều kiện trước.**

- Việc 5 xong. Một hộp ≈ 20 cm nối dây, kéo từ ngoài sa bàn.
- Muốn có hiệu mốc video − mốc log (R7) thì quay video R3 có màn hình trong khung và bấm F8 (T14, việc 8). Không có R7
  thì hiệu đó ghi "CHƯA ĐO ĐƯỢC".
- Chính sách sau vật cản, và việc mất camera có làm xe dừng không, vẫn chưa chốt. Vì vậy chỉ ghi hành vi quan sát được,
  không chấm đạt.
- Muốn xe ảo chạy 0,10 m/s như xe nghiệm thu thì thêm `--vehicle-config configs\vehicle_nghiem_thu.json` vào lệnh
  `ui.lidar_app`.

**Các bước.** Lệnh lấy từ [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 5.3, 5.5. Trong các lần chạy
`ui.lidar_app`, bật ngăn "Ghi cảm biến" của việc 5 để có bản ghi.

- **CB-3**, rút cáp LiDAR khi xe ảo đang chạy, cắm lại sau 10 s:
  ```cmd
  .venv\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app
  ```
  Chép nguyên dòng lỗi (`LidarTransportError` hay `ScanReadError`). Xe ảo không được tự chạy lại. Kiểm thêm việc kết nối
  lại sau khi cắm; đây là lần đầu thử với driver đã sửa. Thêm một lần với lệnh dưới, kỳ vọng mã thoát 1 mà vẫn còn
  `.npz` và `.analysis.json`:
  ```cmd
  .venv\Scripts\python.exe -X utf8 -m autopark.lidar.bench record --out runs\lidar_bench\<ngay> --name cb3_rut_cap --seconds 30
  ```
- **VC-1**, vật chắn phía trước khi đang tiến. Mở `ui.lidar_app` (Kết nối → Tìm đường đỗ → Bắt đầu đỗ), rồi kéo hộp vào
  trước LiDAR, cách ≥ 40 cm:
  ```cmd
  .venv\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app
  ```
  Hoặc dùng lệnh dưới, nhưng lệnh này không có T14:
  ```cmd
  .venv\Scripts\python.exe -X utf8 -m autopark.fusion.demo --seconds 30
  ```
- **VC-6**, vật mới ngoài hành lang thân xe ≥ 20 cm: làm như VC-1 nhưng đặt vật ngoài đường của xe ảo. Xe ảo không được
  dừng.
- **VC-2**, vật sau đuôi khi đang lùi:
  ```cmd
  .venv\Scripts\python.exe -X utf8 -m autopark.ui.lidar_app --scenario scenarios\sa_ban_3x2_hai_hop.json
  ```
  Xem đoạn lùi đã lập trên màn hình. Đánh dấu trên sàn một điểm của đoạn lùi còn lại, cách LiDAR ≥ 40 cm. Đoạn lùi nằm
  phía trước–phải LiDAR, nên **không** đặt vật "phía sau LiDAR": ở đó là ngoài hành lang, thành VC-6. Kéo vật vào khi xe
  ảo đang lùi, sau đuôi ≥ 30 cm.
- **VC-3**, vật bên hông vùng thân xe quét qua ở đoạn cong: dùng cùng lệnh với VC-2. Đặt hộp cạnh quỹ đạo, trong vùng
  thân xe quét qua, không trên đường tâm, cách LiDAR ≥ 40 cm.
- **CB-1**, rút một camera rồi rút cả hub giữa phiên:
  ```cmd
  .venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 60 --name cb1 --out runs\rig_bench\<ngay> --record runs\rig_recordings\cb1
  ```
  Mỗi lần dùng một `--name` và một thư mục `--record` mới. Thêm `--sync-mark` để có dấu T14; khi đó màn hình máy chạy
  bàn thử phải nằm trong khung R3. Không nhấn Enter đúng lúc rút cáp để làm mốc.

Chấm điểm (tùy chọn): chạy `score_run --level BT --sim-truth` trên gói SIM của "Xuất log CSV…", như ghi chú của VC-1 ở
[KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 5.3.

**Thời gian.** Vài lần mỗi kịch bản mất ≈ 1–2 giờ. Đủ số lần theo [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 4
(CB-1 10, CB-3 10, VC-1 10, VC-2 10, VC-3 10, VC-6 5) mất ≈ nửa ngày.

**Ghi kết quả.** Thư mục ở `runs\` (`lidar_bench`, `rig_bench`, `rig_recordings`, `session_recordings`; git bỏ qua),
cùng log và gói của "Xuất log CSV…". Dòng biên bản mức BT tạo bằng `score_run`; nơi lưu biên bản chưa chốt
([KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 2.3, 8). Trạng thái từng kịch bản ghi vào
[KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 4, 5.

**Trạng thái 02/10/2026.** Chưa thử, kể cả bản BT. CB-3 mới có test với cổng serial giả. VC-6 có 0 lần dừng giả trong
202 vòng với LiDAR đứng yên ngày 22/09/2026.

## 7. Laptop nộp đồ án: `do_may_moi`, LD-1

**Mục đích và việc mở khóa.** Số cho khóa luận phải đo trên máy trình diễn ([MAY_NOP_DO_AN.md](MAY_NOP_DO_AN.md)). LD-1
cần "1 lần mỗi máy", mà laptop RTX 3050 Ti chưa đo. N-C1 … N-C3, N-T4 … N-T7 phải đo lại trên máy nghiệm thu
([NGUONG_NGHIEM_THU_DE_XUAT.md](NGUONG_NGHIEM_THU_DE_XUAT.md) mục 12). Máy chạy khi nghiệm thu do người dùng chọn
([KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 8). Việc này thuộc điều kiện V1 số 2.

**Điều kiện trước.** Laptop có mã của đợt 2 (`git pull`); đợt 2 là commit `470abb3`, đã push ngày 06/10/2026. Checkpoint
`runs\ai_woodscape_rtx4000_v1\best.pt` chép từ máy bàn. Python 3.12. Mạng Internet để cài.

**Các bước** ([MAY_NOP_DO_AN.md](MAY_NOP_DO_AN.md) mục 2):

1. `git pull` trong repo trên laptop, hoặc `git clone https://github.com/thbn12082/autopark`.
2. Chép `best.pt` và `config_resolved.json` vào `runs\ai_woodscape_rtx4000_v1\` của thư mục `autopark`. Kiểm mã băm; kết
   quả phải trùng mã ở [MAY_NOP_DO_AN.md](MAY_NOP_DO_AN.md) mục 1:
   ```cmd
   certutil -hashfile runs\ai_woodscape_rtx4000_v1\best.pt SHA256
   ```
3. Chạy `autopark\cai_dat.cmd`, rồi `autopark\cai_dat_train.cmd`. Cuối lệnh thứ hai in `CUDA True` và tên GPU.
4. Cài driver CP210x nếu Device Manager chưa thấy cổng. Sửa `lidar_port` trong `configs\thiet_bi.json` theo số COM của
   laptop, hoặc ghi `"auto"`.
5. Cắm hub với bốn camera ở cổng 1–4, cắm LiDAR thẳng vào laptop. Để camera nhìn cùng cảnh như lúc đo trên máy bàn. Cắm
   sạc, vì laptop chạy pin và kế hoạch nguồn Balanced thì chưa đo.
6. Chạy `autopark\do_may_moi.cmd`, mất ≈ 4 phút theo [MAY_NOP_DO_AN.md](MAY_NOP_DO_AN.md). Kết quả ở
   `autopark\runs\may_moi_<ngày giờ>\tom_tat.md`.
7. LD-1: ghi thử 60 s rồi chạy 30 phút, như việc 1 bước 5:
   ```cmd
   .venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 60 --name ld1_thu_ghi --out runs\rig_bench\<ngay> --record runs\rig_recordings\<ngay>_ld1_thu_ghi
   .venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 1800 --name ld1 --out runs\rig_bench\<ngay> --record runs\rig_recordings\<ngay>_ld1
   ```
   Máy bàn ngày 02/10/2026 ghi 7995–8344 MB cho 30 phút, nên trên laptop đọc lại chỗ trống trước.

   Cách chạy, đề xuất ngày 06/10/2026, chưa chốt, giống việc 1 bước 5:
   - chạy qua `chay_co_theo_doi.py` (`--het-gio 2400` cho lệnh 30 phút), hoặc ít nhất mở từ PowerShell;
   - báo các phiên tác tử khác trên laptop không dừng tiến trình python theo tên hay theo cỡ bộ nhớ;
   - LocalDumps (minidump của WER) trên laptop: chưa kiểm;
   - **không** chép `theo_doi\python.csv`, `theo_doi\gpu_app.csv` hay `lenh_giet.txt` của wrapper vào `docs\evidence`,
     vì chúng có thể chứa dòng lệnh hay tên của tiến trình khác.
8. Tùy chọn, khi không ai chạm laptop ≈ 15 phút: đo vòng 50 Hz khi thu nhỏ trên laptop. Thư mục `--ra` phải mới
   ([CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 13).
   ```cmd
   .venv\Scripts\python.exe -X utf8 -m autopark.evaluation.ecoqos_gui do-chay --ra docs\evidence\ecoqos_chay_<ngay>_laptop
   ```

**Thời gian.** Cài đặt ≈ 30–60 phút, tùy mạng; `do_may_moi` ≈ 4 phút; LD-1 ≈ 32 phút; `do-chay` ≈ 15 phút (máy bàn ngày
02/10/2026: 14 phút).

**Ghi kết quả.** Chép cả `runs\may_moi_<ngày giờ>\` và các `.rig.json` về máy bàn, vào `autopark\runs\`
([MAY_NOP_DO_AN.md](MAY_NOP_DO_AN.md) mục 2 bước 7). Tóm tắt vào [MAY_NOP_DO_AN.md](MAY_NOP_DO_AN.md) trong một mục có
ngày, và vào `docs\evidence\` trong thư mục có ngày, chỉ tệp chữ và JSON.

**Trạng thái 02/10/2026.** Laptop mới chạy giai đoạn 0 (20/09/2026). LiDAR, camera, AI và LD-1 trên laptop chưa đo.

## 8. T14 trên màn hình laptop thật, độ trễ hiển thị L

**Mục đích và việc mở khóa.** R7 (đồng bộ video với log) dùng dấu T14, nên cần màn hình laptop nằm trong khung video R3.
Sai số mỗi dấu là ± một khung cộng độ trễ hiển thị L, mà L chưa đo ([KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục
2.5, 6). Việc này mở khóa phần thời gian video − log của VC-1, VC-2, VC-3, CB-1, CB-3 và mọi kịch bản dùng R7 (N-P1,
N-P7 … N-P9).

**Điều kiện trước.** Laptop (máy nghiệm thu). Một camera quay màn hình laptop; chọn camera nào và đặt ra sao thì chưa
chốt. Tắt khóa màn hình khi chạy dài.

**Các bước.**

1. Mở ứng dụng, phóng to cửa sổ và quay màn hình:
   ```cmd
   .venv\Scripts\python.exe -X utf8 run_app.py scenarios\sa_ban_3x2_hai_hop.json
   ```
   Bấm F8 (nút "Dấu đồng bộ · F8") vài lần, cách nhau ≥ 1 s. Dấu ghi vào `runs\sync_marks\<giờ>_ui_app.csv`. Xem lại
   video: ô trắng có số phải hiện đủ 0,5 s và đọc được số.
2. Chạy bàn thử có dấu đồng bộ:
   ```cmd
   .venv-train\Scripts\python.exe -X utf8 -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 60 --name t14_thu --out runs\rig_bench\<ngay> --sync-mark
   ```
   Lệnh tự đặt dấu ở đầu và 1 s trước khi hết, và thêm một dấu mỗi lần nhấn Enter trong cửa sổ lệnh. Kiểm trên màn hình
   thật: cửa sổ nháy không lấy tiêu điểm của cửa sổ lệnh; thanh tác vụ hay khóa màn hình không che ô.
3. Đo L: cách đo chưa chốt, chưa có lệnh đo L riêng. Công cụ T4 ghi một cận trên của "trễ chụp + hiển thị"
   (`source.flash_offsets`). Cận này có khi trích tư thế từ video `overhead_record` quay trên chính laptop có ô nháy trong
   khung (`overhead_ref track --flash-roi … --sync-marks …`; [THAM_CHIEU_TREN_CAO.md](THAM_CHIEU_TREN_CAO.md) mục 10).

**Thời gian.** ≈ 30 phút.

**Ghi kết quả.** Video và tệp dấu ở `runs\`; video có màn hình và phòng nên không commit. Kết luận (ô hiện đủ không, đọc
được số không, L nếu đo) ghi vào [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 2.5, 6.

**Trạng thái 02/10/2026.** T14 mới kiểm offscreen, chưa thử với màn hình và camera thật. L chưa đo.

## 9. Camera trên cao: T11, T4, TC-1

**Mục đích và việc mở khóa.** Việc này dựng tham chiếu độc lập R1 và phép kiểm nó, TC-1
([KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 3; [THAM_CHIEU_TREN_CAO.md](THAM_CHIEU_TREN_CAO.md)). TC-1 đạt là một
phần của ĐK-XT. R1 dùng để chấm DO-1 … DO-6 (quỹ đạo, tư thế cuối), DV-3, NT-2. Chưa có TC-1 thì công cụ chấm T5 ghi
"không kiểm được". Nếu đặt C1 lên xe giả trong cùng buổi thì có luôn tham chiếu cho DV-1 (KICH_BAN mục 3.7).

**Điều kiện trước.**

- Chọn camera trên cao và máy ghi nó; việc này chưa chốt ([KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 8). Đề
  xuất: ghi trên chính laptop chạy phiên, camera ở cổng gốc riêng, không qua hub của bốn camera xe. Giá treo cứng ở H ≈
  2 m.
- Sa bàn đã dựng.
- In 100 % `calibration/bang_in/aruco/aruco_DICT_4X4_50_100mm_A4_id0-47.pdf` (48 trang A4, một mốc sàn mỗi trang) và
  `aruco_DICT_4X4_50_80mm_A4_id48-49.pdf` (marker xe: mã 48 sau, 49 trước). Dán phẳng; đo lại cạnh bằng thước kẹp.
- Thước thép, ê-ke; xe giả có thước thẳng ≥ 0,65 m (nên 1 m).

**Các bước** ([THAM_CHIEU_TREN_CAO.md](THAM_CHIEU_TREN_CAO.md) mục 2–9; [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md)
mục 3.3–3.8):

1. Dựng hệ tọa độ sa bàn, kiểm vuông bằng tam giác 0,6 / 0,8 / 1,0 m. Tạo tệp mốc:
   ```cmd
   .venv\Scripts\python.exe -X utf8 -m autopark.evaluation.overhead_ref survey-template --size 3.0x2.0 --step 0.5 --check 8 --out docs\evidence\moc_sa_ban_<ngay>.csv
   ```
   Dán mốc theo mã mà lệnh in ra. Đo tâm từng marker bằng thước từ hai cạnh đã kiểm vuông; tâm là giao của hai đường nối
   các vạch giữa cạnh đối diện. Điền `x_m`, `y_m`, `nguoi_do`, `ngay`.
2. Tra index camera, rồi hiệu chuẩn nội tham (T11), ra tệp `calibration\cam_tren_cao_1280x720.json`:
   ```cmd
   .venv\Scripts\python.exe -X utf8 -m autopark.video.camera_bench list
   .venv\Scripts\python.exe -X utf8 -m autopark.ui.calib_app --index N --camera-name tren_cao --size 1280x720
   ```
3. Quay sàn trống:
   ```cmd
   .venv\Scripts\python.exe -X utf8 -m autopark.video.overhead_record --index N --size 1280x720 --seconds 20 --out runs\tren_cao\<ngay> --name san_trong
   ```
4. Khớp mặt sàn:
   ```cmd
   .venv\Scripts\python.exe -X utf8 -m autopark.evaluation.overhead_ref floor --intrinsics calibration\cam_tren_cao_1280x720.json --survey docs\evidence\moc_sa_ban_<ngay>.csv --video runs\tren_cao\<ngay>\san_trong.avi --out docs\evidence\nghiem_thu\mat_san_<ngay>.json
   ```
   Lệnh ghi thêm ảnh xem `mat_san_<ngay>_xem.jpg` cạnh tệp JSON. Đó là ảnh sa bàn, nên không `git add` tệp ảnh này; hoặc
   ghi `--out` vào `runs\tren_cao\<ngay>\` rồi chỉ chép tệp JSON.
5. Đo vị trí, độ cao hai marker trên xe giả và hai đầu thước. Ghi `configs\tham_chieu\xe_gia_v1.json` từ mẫu GIẢ ĐỊNH
   `xe_gia_v0.json`, với `measured: true`.
6. TC-1: ≥ 10 tư thế xe giả, gồm các góc sa bàn và ≥ 3 hướng cách nhau ≥ 20°. Mỗi tư thế quay một đoạn 5–10 s bằng
   `overhead_record` và đo hai đầu thước bằng thước thép. Ghi bảng `docs\evidence\tc1_<ngay>.csv`, rồi chạy:
   ```cmd
   .venv\Scripts\python.exe -X utf8 -m autopark.evaluation.overhead_ref tc1 --floor docs\evidence\nghiem_thu\mat_san_<ngay>.json --markers configs\tham_chieu\xe_gia_v1.json --poses docs\evidence\tc1_<ngay>.csv --kind full --out docs\evidence\nghiem_thu\tham_chieu_tren_cao_<ngay>.json
   ```
7. Kiểm nhanh mọi tệp:
   ```cmd
   .venv\Scripts\python.exe -X utf8 -m autopark.evaluation.overhead_ref check <tệp>
   ```

**Thời gian.** In 49 trang; dán và đo 43 mốc ≈ 2–3 giờ; nội tham camera trên cao ≈ 30 phút; TC-1 với ≥ 10 tư thế ≈ 1–2
giờ.

**Ghi kết quả.**

- Tệp mốc `docs\evidence\moc_sa_ban_<ngay>.csv` và bảng tư thế `docs\evidence\tc1_<ngay>.csv`; CSV nằm thẳng trong
  `docs\evidence\`.
- Khớp mặt sàn và biên bản TC-1 (JSON) ở `docs\evidence\nghiem_thu\`.
- Cấu hình marker `configs\tham_chieu\xe_gia_v1.json`.
- Video ở `runs\tren_cao\<ngay>\`, không commit.
- Cập nhật [THAM_CHIEU_TREN_CAO.md](THAM_CHIEU_TREN_CAO.md) và [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 3.

**Trạng thái 02/10/2026.** Chưa thử. Phần mềm có, nhưng mới kiểm trên ảnh tổng hợp. Chưa chọn camera, chưa in marker,
chưa đo mốc, chưa làm TC-1.

## 10. Ngoại tham và ROI

**Mục đích và việc mở khóa.** Việc này tạo `configs/rig/camera_rig_extrinsics_v1.json` (vị trí, hướng camera so với xe)
và `configs/roi/rig_v1/roi_p<N>.png`. BEV chỉ đánh dấu costmap "dùng được cho lập đường" khi mọi camera được dùng có
ngoại tham đo, có ROI và có nội tham đạt tiêu chí; khi đó ngăn AI camera mới tạo vật cản. Việc này mở khóa ĐK-AI (NT-1 …
NT-5), N-G1, N-G2, thuộc điều kiện V1 số 2, 3.

**Điều kiện trước.**

- Việc 4 xong (`calibration/cam_p<N>.json`).
- Camera gá **cứng** lên xe MN300, đã chốt cổng nào là hướng nào. Hiện chưa có xe.
- Sàn phẳng, cứng. Bảng in 9×6 (nên dùng A3 ô 30 mm) dán trên tấm phẳng; đo độ dày tấm (`board_z_m`).
- Vạch hệ xe bằng băng dính: gốc trên sàn ngay dưới tâm trục sau, trục x, trục y và các vạch phụ
  ([NGOAI_THAM_VA_ROI.md](NGOAI_THAM_VA_ROI.md) mục 3).
- Không chạm xe và camera trong suốt buổi đo.

**Các bước** ([NGOAI_THAM_VA_ROI.md](NGOAI_THAM_VA_ROI.md) mục 4–6):

1. Mở công cụ, thẻ "Ngoại tham":
   ```cmd
   .venv\Scripts\python.exe -X utf8 -m autopark.ui.roi_app --port 1 --live
   ```
   Mỗi camera ≥ 2 lần đặt bảng, nên 3–4 lần: trái, giữa, phải, xoay ±15°. Bảng nằm sát xe, trước camera. Đo tọa độ O, A
   (nên thêm B, C) trong hệ xe tới 1 mm. Bấm "Thêm lần đặt (ảnh hiện tại)" → "Tính ngoại tham" → kiểm bằng mắt rằng lưới
   hệ xe nằm đúng vạch băng dính → "Ghi tệp rig".
2. Thẻ "ROI": mở ảnh của camera đã gá (640×480), vẽ đa giác "Loại" theo mép thân xe, dây, viền ống kính → "Lưu ROI". Tệp
   xem `roi_p<N>_xem.jpg` cạnh mặt nạ là ảnh camera, nên không commit.
3. Kiểm ngoại tham và ROI:
   ```cmd
   .venv\Scripts\python.exe -X utf8 -m autopark.perception.extrinsics_calib check configs\rig\camera_rig_extrinsics_v1.json
   .venv\Scripts\python.exe -X utf8 -m autopark.perception.roi_tool check configs\roi\rig_v1\roi_p1.png --image runs\rig_snapshots\<ngày_giờ>\cam_p1.png --intrinsics calibration\cam_p1.json
   ```
   Chạy BEV trên một bộ ảnh thật. Bộ ảnh phải chụp bằng `ui.rig_app` có bật AI, vì lệnh đọc `prob_blocked_p*.png`:
   ```cmd
   .venv\Scripts\python.exe -X utf8 -m autopark.perception.bev snapshot runs\rig_snapshots\<ngày_giờ> --extrinsics configs\rig\camera_rig_extrinsics_v1.json --roi-dir configs\roi\rig_v1
   ```

**Thời gian.** ≈ 30–45 phút mỗi camera cho ngoại tham, cộng thời gian vẽ ROI.

**Ghi kết quả.** `configs/rig/camera_rig_extrinsics_v1.json`, `configs/roi/rig_v1/roi_p<N>.png` (và `.json`). Phiên đo
(ảnh, `dat_bang_p<N>.json`, `ket_qua.json`) ở `runs/extrinsics/<ngày_giờ>_p<N>/` (git bỏ qua). Cập nhật
[NGOAI_THAM_VA_ROI.md](NGOAI_THAM_VA_ROI.md) và [BEV.md](BEV.md) mục 8.

**Trạng thái 02/10/2026.** Chưa làm: chưa có nội tham, chưa có xe, chưa gá camera. Công cụ mới kiểm trên ảnh tổng hợp.

## 11. Bo ESP32-S3 (khi có bo)

**Mục đích và việc mở khóa.** Việc này mở mọi đường dùng bo thật: T1 với bo thật, ĐK-XT, AT-1 … AT-5, CB-4, CB-5, DI
trên xe và mọi kịch bản XT; điều kiện V1 số 6, 9. Firmware mới biên dịch, chưa nạp, chưa chạy trên bo nào
([README firmware](../firmware/esp32_vehicle/README.md)).

**Điều kiện trước.**

- Có bo.
- Chốt loại bo: `board` trong `firmware/esp32_vehicle/platformio.ini`, hiện là `esp32-s3-devkitc-1`, chưa chốt.
- Chốt cổng USB nào là `Serial`, và các chân ESC, servo, E-stop; `kPinEsc`, `kPinServo`, `kPinEstop` đang là -1.
- Bản nạp đầu giữ `AP_ENABLE_PWM_OUTPUTS=0`; bo chỉ cắm USB.
- PlatformIO trên máy bàn ở `D:\xetulai\_platformio\penv` ([CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 7).

**Các bước** (README firmware, mục "Trình tự thử trên bo"):

1. Nạp firmware, chạy trong `firmware\esp32_vehicle`. Lệnh này chưa chạy lần nào vì chưa có bo.
   ```cmd
   D:\xetulai\_platformio\penv\Scripts\python.exe -m platformio run -e esp32s3 -t upload
   ```
2. Mở ứng dụng, vào thẻ "Bo điều khiển". Chọn cổng COM của bo, không phải cổng của LiDAR, rồi bấm "Kiểm kết nối bo".
   Giao diện hỏi xác nhận trước khi mở cổng thật. Phép kiểm gửi HELLO, so giới hạn bo với cấu hình xe và đọc vài khung
   telemetry; nó không ARM, không gửi lệnh.
   ```cmd
   .venv\Scripts\python.exe -X utf8 run_app.py
   ```
3. Thử ARM, lệnh, hết hạn lệnh, rút cáp, cắm lại, reset: gọi `SerialVehicleIO` từ Python như README firmware. Ghi log; đo
   `stats.ack_rtt_s`, `stats.cmd_echo_s` thật.
4. E-stop, khi đã chốt `kPinEstop`. Rút đầu nối thì telemetry có `ESTOP_INPUT = 1` và bo vào FAULT. CLEAR_FAULT bị từ
   chối (`ESTOP_ACTIVE`) cho tới khi cắm lại. Nút trên giao diện không gửi CLEAR_FAULT khi `ESTOP_INPUT` = 1, nên muốn
   thấy lời từ chối thì gọi `io.clear_fault()` từ Python. Cắm lại rồi bấm "Xóa lỗi bo (CLEAR_FAULT)".
5. Sau đó làm các bước đo chân xung bằng máy hiện sóng, rồi servo, ESC với bánh kê cao, theo README firmware.

**Hai điểm còn mở về bo:**

- Firmware biên dịch cứng `max_speed_mm_s` = 300. Vì vậy Bắt đầu đỗ ở VEHICLE_IO với `configs/vehicle_nghiem_thu.json`
  (0,10 m/s) bị từ chối với LIMITS_MISMATCH; đây là hành vi an toàn. Xe nghiệm thu cần một bản firmware 100 mm/s, hiện
  chưa làm.
- Cổng USB CDC của bo có bị lỗi "PurgeComm không xóa gì" như cổng CP210x của C1 không thì chưa thử. `SerialVehicleIO`
  không gọi `reset_input_buffer` ([CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 12.2).

**Thời gian.** Nạp và "Kiểm kết nối bo" ≈ 30 phút; các bước sau mất nhiều buổi.

**Ghi kết quả.** Đầu ra nạp, log `SerialVehicleIO`, `board_actions.csv` vào `docs\evidence\`, trong thư mục có ngày;
riêng CSV đặt thẳng trong `docs\evidence\`. Cập nhật [README firmware](../firmware/esp32_vehicle/README.md),
[GIAO_THUC_XE.md](GIAO_THUC_XE.md) và [CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) mục 6.

**Trạng thái 02/10/2026.** Chưa làm vì chưa có bo. Mọi đường bo thật chưa thử; bản firmware 100 mm/s chưa làm. Phần mềm
phía laptop đã chạy cả phiên đỗ qua bo ảo QEMU ([CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 14), nhưng điều đó không
chứng minh gì về bo thật.

## Sau mỗi buổi

- Ghi một mục mới có ngày trong [CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md): giờ, lệnh, mã (commit), ai ở bàn, kết quả, giới
  hạn, theo mẫu mục 12 của tệp đó. Tệp chữ vào `docs\evidence\thiet_bi_<ngay>\` (như
  [thiet_bi_20261002](evidence/thiet_bi_20261002/)); ảnh, video để ở `runs\`.
- Sửa trạng thái ở tài liệu chi tiết của việc đó và ở [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 4; sửa cột
  "Trạng thái" của bảng ở đầu tệp này.
- Mọi ngưỡng vẫn là đề xuất, chưa chốt, cho tới khi người dùng và GVHD chốt
  ([NGUONG_NGHIEM_THU_DE_XUAT.md](NGUONG_NGHIEM_THU_DE_XUAT.md) mục 12). Vì vậy chỉ ghi số đo, không ghi "đạt nghiệm thu".
