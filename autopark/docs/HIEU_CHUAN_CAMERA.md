# Hiệu chuẩn nội tham từng camera (giai đoạn 2, bước 4): công cụ và cách làm (24/09/2026)

**Kế hoạch đối chiếu:** v3.1 mục 6, "Khi đủ bốn camera", bước 4
([bản `9d68257`](https://github.com/thbn12082/autopark/blob/9d68257/KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md); bản hiện tại:
mục 6, đoạn "Có đồ"): *"Hiệu chuẩn riêng từng camera; gắn lên rig rồi xác định vị trí/hướng của camera so với rig."*
Đầu ra cần có: *"bốn tệp calibration, `camera_rig_extrinsics.yaml`"*.

**Mức bằng chứng:** công cụ mới chỉ được kiểm trên ảnh tổng hợp và trên nguồn camera giả trong test. Riêng giao diện đã
mở camera thật cổng 2 một lần, khoảng 6 s, ngày 24/09 (xem cuối mục 5), nhưng không chụp ảnh nào. Chưa có ảnh bảng nào
chụp từ camera thật, và bảng chưa được in. Con số 130° là số người bán quảng cáo, chưa ai đo. Mọi ngưỡng chấp nhận dưới
đây là **đề xuất**, chưa được kiểm trên camera thật. *(Cập nhật 02/10/2026, T11: thêm cách hiệu chuẩn camera không qua
hub 1–4, như camera trên cao, cuối mục 3; chỉ kiểm offscreen với camera giả và ảnh tổng hợp.)*

**Phần này làm ra gì:** bốn tệp `calibration/cam_p1.json` … `cam_p4.json`, mỗi tệp là **nội tham** của một camera, gọi
theo cổng hub. Chưa có **ngoại tham**, tức vị trí và hướng của camera so với xe (xem mục 6).

## 1. Công cụ

| Việc | Mã | Kiểm (không cần thiết bị) |
|---|---|---|
| Bảng ô vuông để in: PDF vector đúng khổ A4/A3, PNG ở một DPI cho trước (có khối pHYs), JSON mô tả bảng | `perception/calib_board.py`; tệp in sẵn trong `calibration/bang_in/` | Đọc MediaBox và các hình chữ nhật trong PDF; vẽ lại PDF bằng pdfium (QtPdf) rồi dò bảng: ô 78,7 px ở 100 DPI, sai lệch dưới 1 %; đếm điểm ảnh của ô trong PNG |
| Dò góc bảng, kiểm từng ảnh, bản đồ phủ, hiệu chuẩn `cv2.fisheye`, loại ảnh ngoại lai, trường nhìn, chuyển sang mô hình đa thức của dự án, nắn ảnh, đọc/ghi tệp, dòng lệnh | `perception/fisheye_calib.py` | `tests/test_fisheye_calib.py`: ảnh dựng qua một camera Kannala–Brandt đã biết (mục 5); *(02/10/2026, T11)* camera ngoài hub khóa theo tên an toàn, dòng lệnh `calibrate --camera-name` (`test_camera_outside_the_hub_is_keyed_by_a_safe_name`, `test_cli_calibrate_a_camera_outside_the_hub_by_name`) |
| Giao diện: chọn camera theo cổng hub, xem trực tiếp có vẽ góc bảng và lưới phủ, chụp tay hoặc tự chụp, hiệu chuẩn chạy nền, xem ảnh nắn cạnh ảnh sống, lưu | `ui/calib_app.py` | `tests/test_calib_app_ui.py`: chạy offscreen với camera giả phát ảnh tổng hợp. Kiểm: chụp tay, tự chụp (không chụp lại tư thế cũ, giữ khoảng cách thời gian giữa hai lần chụp), khung hỏng bị đếm và không được chụp, khung khác cỡ không được chụp; lưới phủ và ảnh nắn so từng điểm ảnh với `draw_coverage` / `undistort_image`; không lưu khi danh sách ảnh hoặc cỡ ô đổi sau hiệu chuẩn; ô "Đã đo cỡ ô" quyết định `square_mm_measured`; đổi cổng/mode bỏ ảnh và kết quả, kể cả kết quả của lần hiệu chuẩn đang chạy; phím cách chụp cả khi ô nhập số giữ focus; lưu vào thư mục tên tiếng Việt; *(02/10/2026, T11)* camera ngoài hub 1–4 (`--index N --camera-name TÊN`): mở theo index, lưu theo tên, ô cổng khóa, không bao giờ ghi `cam_p*.json` (`test_camera_outside_the_hub_opens_by_index_and_saves_under_its_name`, `test_build_window_parses_port_or_index_without_opening_a_camera`); `--port N` bị từ chối chứ không đoán khi hai hub cùng có camera ở cổng số N (`test_hub_port_shared_with_a_camera_outside_the_hub_is_refused_not_guessed`) |

Mô hình ống kính là Kannala–Brandt của `cv2.fisheye` với 4 hệ số, skew cố định bằng 0. Mô hình này chỉ biểu diễn được
tia lệch trục quang dưới 90°. Như vậy là đủ nếu ống kính đúng như quảng cáo là 130° (tức 65° mỗi bên), nhưng chưa ai đo.
Mã cũ `perception/calibration.py` đọc hiệu chuẩn của WoodScape. Mã mới chỉ sửa một chỗ trong tệp đó (24/09/2026):
`CameraCalibration.from_dict` đọc `theta_max_deg` nếu khối nội tham có khóa này, còn tệp WoodScape không có khóa này nên
vẫn dùng 100°.

## 2. In bảng

Có sẵn hai bản in trong `calibration/bang_in/`:

| Tệp | Bảng | Cỡ ô danh định | Khi nào dùng |
|---|---|---|---|
| `ban_co_9x6_20mm_A4.pdf` | 9×6 góc trong (10×7 ô) | 20 mm | Dễ in |
| `ban_co_9x6_30mm_A3.pdf` | 9×6 góc trong | 30 mm | Nên chọn nếu in được A3: bảng to thì cầm xa hơn được, ảnh nét hơn với ống kính lấy nét cố định |

Muốn bảng khác thì chạy `.\.venv\Scripts\python.exe -X utf8 -m autopark.perception.fisheye_calib board --paper A3 --square-mm 28`.
Nếu bảng cùng viền trắng một ô không vừa trang, lệnh sẽ báo lỗi kèm cỡ ô lớn nhất còn vừa.

1. **In 100 %, không co giãn.** Trong hộp thoại in, chọn "Actual size" và tắt "Fit to page". Tệp PDF có ghi gợi ý
   `/PrintScaling /None` cho trình đọc, nhưng nhiều trình đọc bỏ qua gợi ý này, nên vẫn phải tự chọn. Nên in lên giấy
   mờ: giấy bóng dễ bị lóa.
2. **Dán lên một tấm phẳng và cứng** như bìa foam, gỗ hay kính. Không để giấy phồng, nhất là ở các góc. Bảng cong làm sai
   hiệu chuẩn, mà RMS chưa chắc đã cho thấy.
3. **Đo lại bằng thước.** Đo từ góc trong đầu tiên tới góc trong cuối cùng **của một hàng** (8 ô), chia cho 8. Đo thêm
   một cột (5 ô), chia cho 5. Nếu hai con số lệch nhau quá 0,5 % thì máy in đã co giãn không đều theo hai chiều, cần in
   lại, vì bảng ô vuông giả định mọi ô đều vuông. Nếu cả hai con số cùng nhỏ hơn danh định (ví dụ 150 mm thay vì 160 mm,
   tức 94 %) thì máy in đã chạy "vừa trang". Khi đó hoặc in lại, hoặc cứ nhập cỡ ô đo được.
4. **Nhập cỡ ô ĐO ĐƯỢC** khi hiệu chuẩn, không nhập cỡ danh định. Trong giao diện, điền ô "cỡ ô ĐO ĐƯỢC" và đánh dấu "Đã
   đo cỡ ô bằng thước". Ở dòng lệnh, dùng `--square-mm`.

**Cỡ ô không ảnh hưởng tới K, D.** Phóng to cả bảng lẫn khoảng cách theo cùng một tỉ lệ thì ảnh chụp được không đổi, nên
cỡ ô chỉ quyết định khoảng cách bảng tính ra (`distance_m`) và sau này là ngoại tham. Độ phẳng của bảng và độ vuông của
từng ô thì có ảnh hưởng tới K, D.

## 3. Chụp

```
.\.venv\Scripts\python.exe -X utf8 -m autopark.ui.calib_app --port 1 --square-mm 19.95
```

- **Mỗi lần một camera.** Chọn camera theo cổng hub; khi mở, công cụ hỏi Windows cổng đó đang ứng với index OpenCV nào
  (`resolve_ports`, cần pygrabber). Mode mặc định là **640×480 MJPG**, là mode chạy chung bốn camera. Cũng chọn được
  1280×720, nhưng đó là một hiệu chuẩn **riêng** cho mode ấy, lưu vào `cam_pN_1280x720.json`. Mode 16:9 có thể lấy một
  phần khác của cảm biến, nên không đem K của mode này dùng cho mode kia. Việc này chưa kiểm. *(02/10/2026: camera không
  qua hub 1–4, như camera trên cao, mở theo index; xem cuối mục này.)*
- **Số ảnh:** 20–30 ảnh, để sau khi loại ngoại lai còn ít nhất 15.
- **Phủ kín ảnh, nhất là mép và bốn góc.** Mép và góc là nơi méo nhiều nhất và quyết định hệ số D. Lưới phủ trên ảnh
  sống tô **đỏ** những ô chưa có góc bảng nào của các ảnh đã chụp, và tô **xanh** đậm dần theo số góc. Chụp tới khi gần
  hết ô chuyển xanh, cả bốn khối góc đều có điểm. Ở mép ảnh mắt cá, bảng trông nhỏ và cong: đưa bảng lại gần camera
  hơn, nhưng vẫn phải thấy trọn bảng.
- **Nghiêng bảng** khoảng 20–45° quanh cả hai trục, và xoay trong mặt phẳng ảnh một ít. Nếu chỉ chụp bảng nhìn thẳng
  thì tiêu cự và độ méo khó tách khỏi nhau. Nên có vài ảnh nhìn thẳng ở giữa ảnh.
- **Khoảng cách:** với bảng A4, giữa ảnh có thể để bảng chiếm từ 1/4 đến 1/2 bề ngang ảnh. Ống kính loại này thường lấy
  nét cố định. Nếu số "nét" trên dòng trạng thái tăng khi đưa bảng lại gần, bạn đang ở gần hơn tầm nét: lùi ra, hoặc
  dùng bảng A3.
- **Giữ yên.** Camera tự phơi sáng và chạy khoảng 24 khung/s. Phòng tối thì thời gian phơi dài, ảnh dễ nhòe khi bảng di
  chuyển. Hãy bật đủ đèn và tránh đèn chiếu thẳng gây lóa trên giấy. "Tự chụp" chỉ chụp khi bảng đạt chất lượng, các góc
  dịch trung bình không quá 0,8 px/khung trong 0,5 s, và tư thế khác mọi ảnh đã chụp. Khi camera chưa gá, có thể cố
  định bảng trên tường rồi cầm camera di chuyển; về hình học thì cách này tương đương.
- **Dòng trạng thái** cho biết: có thấy đủ 54 góc không; "nét" là độ rộng vùng chuyển đen→trắng, tính bằng px, nhỏ là
  tốt (OpenCV khuyên dưới khoảng 3 px; ngưỡng này chỉnh được trên giao diện); tương phản; bảng cách mép ảnh bao xa;
  khung có hỏng không; bảng có đứng yên không; tư thế khác ảnh gần nhất bao nhiêu. Khung MJPEG bị cắt cụt hay có dải xé
  (`truncated_rows`/`torn_bands`, xem [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 2) không bao giờ được chụp.
  Nguồn USB đã loại những khung này và dòng dưới đếm lại chúng.
- "Chụp" (hoặc phím cách) chỉ nhận khung đạt. Phím cách vẫn là "Chụp" khi ô cỡ ô hoặc ô ngưỡng mờ đang giữ focus, kể cả
  khi vừa gõ cỡ ô mà chưa Enter (giá trị đang gõ đã được nhận). Ảnh chụp giữ nguyên ảnh gốc, chưa vẽ gì lên, và được ghi
  dưới dạng PNG không mất thông tin khi bấm "Lưu".

**Camera không qua hub 1–4** (camera trên cao của [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 3.4; thêm
02/10/2026, T11; chỉ kiểm offscreen với camera giả, camera trên cao thật CHƯA THỬ):

```
.\.venv\Scripts\python.exe -X utf8 -m autopark.video.camera_bench list
.\.venv\Scripts\python.exe -X utf8 -m autopark.ui.calib_app --index 4 --camera-name tren_cao --size 1280x720
```

- Mở theo index OpenCV (cột `[index]` ở phần DirectShow của `camera_bench list`), không tra cổng hub. Index đổi sau khi
  khởi động lại hay cắm lại nên phải tra lại mỗi lần; tệp khóa theo TÊN nên index đổi không làm lẫn tệp.
- Tên (`--camera-name`, mặc định `tren_cao`): chữ thường không dấu, số, gạch dưới, bắt đầu bằng chữ, tối đa 32 ký tự;
  không bắt đầu bằng `p<số>` (trùng tệp camera xe), không kết thúc bằng `_<rộng>x<cao>`.
- Lưu ra `calibration/cam_<tên>[_<W>x<H>].json` và `runs/calib/<ngày giờ>_<tên>/`; bản ghi có `camera.hub_port` null,
  `camera.name`, `camera.opencv_index` (index lúc chụp, chỉ để tra). Ô cổng bị khóa; đổi mode vẫn được. BEV, AI camera,
  công cụ ngoại tham và ROI không dùng tệp này: chúng chỉ dành cho camera xe theo cổng hub.
- Từ cùng ngày, nếu camera trên cao cắm vào cổng gốc của máy có SỐ trùng cổng hub của camera xe cần hiệu chuẩn (ví dụ
  cổng gốc 2 và cổng hub 2), thì `calib_app --port 2` báo lỗi chứ không đoán, kể cả khi ba camera xe kia đang cắm. Muốn
  hiệu chuẩn camera xe cổng 2 thì cắm camera trên cao vào cổng gốc có số khác 2, hay rút nó ra; camera trên cao thì mở
  bằng `--index`. Laptop có webcam gắn sẵn mang số cổng gốc 1–4 cũng chặn `--port` số đó (CHƯA gặp: sơ đồ USB của
  laptop chưa đo, hai máy bàn đã đo chỉ có bốn camera xe): tắt webcam trong Device Manager lúc hiệu chuẩn, hay hiệu
  chuẩn ở máy bàn. Lời gọi nhiều cổng (`rig.bench --ports 1 2 3 4`) vẫn chọn được: cổng trùng số lấy camera trên hub
  chung của các cổng không trùng số.
- Bộ dò khung hỏng của `UsbCameraSource` và mô hình mắt cá được chọn cho camera Sunplus của xe; camera trên cao khác loại
  có thể bị loại khung (xem bộ đếm trên dòng trạng thái) hay cần mô hình ống kính khác (việc của công cụ T4,
  [KICH_BAN_NGHIEM_THU.md](KICH_BAN_NGHIEM_THU.md) mục 7). *(Cập nhật 02/10/2026: T4 dùng tệp Kannala–Brandt của T11,
  chưa thêm mô hình lỗ kim; bộ đọc của `overhead_ref` chỉ nhận định dạng `autopark.fisheye_intrinsics/1`, từ chối
  tệp của camera cổng hub và phân nhánh theo khóa `format` để thêm mô hình sau. Khớp mặt sàn báo xu hướng sai số theo
  bán kính ảnh và mốc ngoại suy, còn TC-1 cho biết mô hình có hợp với camera trên cao không; chưa chọn camera trên
  cao, CHƯA THỬ. Bộ ghi video của T4 cũng đọc qua `UsbCameraSource`: khung hỏng không vào video, chỉ ghi ở
  `.events.csv`. [THAM_CHIEU_TREN_CAO.md](THAM_CHIEU_TREN_CAO.md) mục 4, 5, 6.)*

## 4. Hiệu chuẩn, đọc kết quả, lưu

Khi có ít nhất 8 ảnh thì bấm được "Hiệu chuẩn". Công cụ gọi `cv2.fisheye.calibrate` với cờ CALIB_RECOMPUTE_EXTRINSIC |
CALIB_FIX_SKEW, và thử thêm CALIB_CHECK_COND. Nếu OpenCV báo một ảnh làm ma trận suy biến thì ảnh đó bị bỏ. Sau mỗi lần
hiệu chuẩn, nếu RMS riêng của ảnh tệ nhất lớn hơn max(1 px, 3 × trung vị) thì ảnh đó bị bỏ và hiệu chuẩn lại, miễn là
vẫn còn ít nhất 8 ảnh. Ảnh bị bỏ được chấm lại dưới mô hình cuối và được ghi lý do. Ô bên phải hiện ảnh sống đã nắn sang
phối cảnh. Kéo "balance" từ 0 (cắt hết viền đen) tới 1 (giữ cả trường nhìn). Cạnh bảng phải thẳng ở **mọi** vị trí
trong ảnh.

Trong lúc hiệu chuẩn chạy, ô chọn cổng và mode bị khoá. Nếu camera/mode vẫn bị đổi (hàm `reopen` gọi từ mã), kết quả
của lần chạy đó bị bỏ khi xong, kể cả khi đã quay lại đúng cổng/mode cũ: ảnh của lần mở trước đã bị bỏ, nên kết quả
không còn ứng với ảnh nào. Số liệu và ảnh nắn trên màn hình vì thế luôn thuộc camera đang mở.

**Tiêu chí đề xuất** (có trong tệp, mục `acceptance`; công cụ không tự chặn việc lưu theo các tiêu chí này):

| Tiêu chí | Đề xuất | Lý do |
|---|---|---|
| RMS chiếu lại, tính trên mọi góc | ≤ 0,5 px | Trên ảnh tổng hợp đạt 0,07 px. Ảnh thật (nén MJPEG, mờ, bảng không phẳng hẳn) sẽ cao hơn, chưa biết bao nhiêu |
| RMS của ảnh tệ nhất còn dùng | ≤ 1,0 px | Một ảnh lệch hẳn thường là dò sai hoặc bảng cong |
| Số ảnh dùng | ≥ 15 | |
| Phủ lưới 8×6 | ≥ 70 % số ô, **và** cả bốn khối góc có điểm | Ngoài vùng đã thấy bảng, mô hình là ngoại suy |
| Ảnh bảng nghiêng ≥ 20° | ≥ 4 | Tách tiêu cự khỏi độ méo |
| Sai số khi chuyển sang mô hình dự án | ≤ 0,5 px **và** chuyển đổi đạt (`woodscape_intrinsic.ok`: đa thức tăng đơn điệu, góc ảnh nằm trong vùng KB nghịch đảo được và nghịch đảo được bằng đa thức) | Xem dưới. Sai số khớp nhỏ chưa đủ: với D gập lại trước góc ảnh (thử D = (−0,0958; −0,0376; 0,0171; −0,0047) trên K tổng hợp), sai số khớp chỉ 0,29 px nhưng `load_intrinsics()` từ chối tệp; tiêu chí này khi đó ghi CHƯA kèm lý do |

Cần xem thêm hai điều mà công cụ không chấm điểm:

- **θ lớn nhất đã thấy bảng, so với θ ở góc ảnh.** Bản tóm tắt in cả hai con số. Phần giữa hai số này là **ngoại suy**.
  Trên ảnh tổng hợp của test, bảng chỉ phủ tới θ = 59,8°, trong khi góc ảnh ở θ = 68,4°. Sai số mô hình ở vùng góc ảnh
  vì thế lên tới 0,49 px, trong khi trung vị toàn ảnh chỉ 0,05 px.
- **So sánh bốn camera với nhau.** Bốn camera cùng loại đáng lẽ có K gần nhau. Nếu một camera có fx lệch hẳn so với ba
  camera kia thì nên chụp lại camera đó. Đây là đề xuất; chưa có số liệu để biết thế nào là "lệch hẳn".

**Chuyển sang mô hình của dự án.** `FisheyeIntrinsics` (trong `perception/calibration.py`, dạng WoodScape) dùng đa thức
ρ(θ) = k1·θ + k2·θ² + k3·θ³ + k4·θ⁴. Công cụ khớp đa thức này vào fx·θ_d(θ) trên đoạn θ ∈ [0, θ ở góc ảnh], bắt đầu bằng
bình phương tối thiểu rồi lặp Lawson để hạ sai số **lớn nhất**. Trên camera tổng hợp, sai số lớn nhất là 0,077 px với
bình phương tối thiểu thường và 0,035 px sau khi lặp Lawson. Các tham số còn lại: `aspect_ratio` = fy/fx, `cx_offset` =
cx − (W/2 − 0,5), `cy_offset` tính tương tự. Kết quả còn được kiểm chéo bằng chính `FisheyeIntrinsics.project`, so với
`cv2.fisheye.projectPoints`.

Nghiệm minimax có thể **hụt ở đầu đoạn**: ρ_poly(θ ở góc ảnh) nhỏ hơn bán kính thật của điểm ảnh góc, và điểm ảnh đó
nghịch đảo ra NaN. Điều này có thật trên kết quả hiệu chuẩn 21 ảnh tổng hợp (không phải trên K, D thật của camera tổng
hợp, nơi đa thức tình cờ vượt lên): ρ_poly = 405,506 px trong khi góc (0, 479) ở bán kính 405,522 px. Vì vậy
`theta_max_deg` được **nâng** vừa đủ để ρ_poly chạm bán kính góc ảnh xa nhất (ở đây nâng 0,003°, ghi ở
`theta_max_raise_deg`; `theta_image_corner_deg` là θ ở góc ảnh trước khi nâng), làm tròn lên, và sai số khớp được tính
trên đoạn đã nâng. Công cụ kiểm lại bốn góc ảnh bằng chính `FisheyeIntrinsics.unproject` (`corners_invertible`).

Khối `woodscape_intrinsic` bị đánh `ok: false`, và `load_intrinsics()` từ chối nạp, khi có một trong các điều sau: sai
số khớp vượt 0,5 px; đa thức không tăng đơn điệu tới `theta_max`; góc ảnh vượt vùng mô hình KB nghịch đảo được; góc ảnh
không nghịch đảo được bằng đa thức. `reason` liệt kê mọi điều vi phạm.

**Lưu:** bấm "Lưu" sẽ ghi `calibration/cam_p<cổng>.json`. Ảnh đã chụp, `captures.json` (vị trí góc và chất lượng từng
ảnh) và một bản sao tệp hiệu chuẩn được ghi vào `runs/calib/<ngày giờ>_p<cổng>/`. *(02/10/2026, T11: camera ngoài hub
ghi `calibration/cam_<tên>.json`, ảnh ở `runs/calib/<ngày giờ>_<tên>/`.)* Công cụ không cho lưu nếu danh sách ảnh hoặc
cỡ ô đã thay đổi sau lần hiệu chuẩn. Có thể hiệu chuẩn lại từ thư mục ảnh đó mà không cần camera:

```
.\.venv\Scripts\python.exe -X utf8 -m autopark.perception.fisheye_calib calibrate --images runs/calib/<thư mục> --cols 9 --rows 6 --square-mm 19.95 --port 1
.\.venv\Scripts\python.exe -X utf8 -m autopark.perception.fisheye_calib check calibration/cam_p1.json --image runs/calib/<thư mục>/cap_000.png
.\.venv\Scripts\python.exe -X utf8 -m autopark.perception.fisheye_calib calibrate --images runs/calib/<thư mục> --square-mm 19.95 --camera-name tren_cao
```

Lệnh `check` in bản tóm tắt. Nếu có `--image`, lệnh ghi thêm ảnh gốc và ảnh nắn đặt cạnh nhau. *(Thêm 02/10/2026, T11:)*
dòng cuối hiệu chuẩn lại camera ngoài hub; `--port` và `--camera-name` loại trừ nhau, bắt buộc một trong hai; ra
`calibration/cam_tren_cao.json` khi ảnh 640×480, `calibration/cam_tren_cao_<W>x<H>.json` ở mode khác (ảnh chụp bằng
lệnh `--size 1280x720` ở mục 3 cho `cam_tren_cao_1280x720.json`); `camera.opencv_index` là null vì không chụp từ
camera.

## 5. Đã kiểm gì trên ảnh tổng hợp, và các phép kiểm đó chưa chứng minh gì

Ảnh được dựng qua một camera Kannala–Brandt **đã biết**: 640×480, fx = 351,0, fy = 349,2, cx = 324,3, cy = 236,8,
D = (−0,035; 0,018; −0,009; 0,0015). Với mỗi điểm ảnh con (siêu lấy mẫu 3×3), tia nhìn lấy từ
`cv2.fisheye.undistortPoints`, tức không đi qua mã đang kiểm. Tia được cắt với mặt phẳng bảng rồi tô màu theo ô. Sau đó
ảnh được làm mờ (σ = 0,6 px) và thêm nhiễu (σ = 2). Bảng 9×6 với ô 25 mm, được đặt ở 21 tư thế khắp ảnh, kể cả bốn góc,
nghiêng tới ±40° và cách camera 0,18–0,98 m.

| Đại lượng | Thật | Tìm được |
|---|---|---|
| fx / fy | 351,0 / 349,2 | 351,03 / 349,23 |
| cx / cy | 324,3 / 236,8 | 324,29 / 236,76 |
| RMS chiếu lại | — | 0,071 px (số OpenCV trả về trùng số tự tính) |
| Sai lệch mô hình: tia thật qua mỗi điểm của lưới 65×49 trên ảnh, chiếu lại bằng mô hình tìm được | — | trung vị 0,05 px, lớn nhất 0,49 px (ở góc ảnh, vùng ngoại suy) |
| Trường nhìn ngang / dọc / chéo suy từ mô hình | 106,8° / 79,9° / 135,2° | 106,8° / 79,8° / 135,1° |
| Chuyển sang đa thức dự án | — | sai số lớn nhất 0,017 px |

Test cũng kiểm:
- một ảnh có nửa số góc lệch vài px bị loại đúng, còn nếu tắt việc loại ngoại lai thì RMS tăng hơn 3 lần;
- khung bị cắt cụt hoặc có dải xé bị loại trước khi dò, và giao diện đếm lại chúng;
- ảnh mờ bị cờ "mờ", bảng sát mép ảnh bị cờ riêng;
- tự chụp không chụp lại một tư thế đã có;
- sau khi nắn, các hàng góc thẳng lại (độ cong còn dưới 1/5 so với trước);
- thư mục ảnh do giao diện lưu, khi hiệu chuẩn lại bằng dòng lệnh, cho ra cùng K;
- với K, D **tìm được**, mọi điểm ảnh 640×480 nghịch đảo được bằng `FisheyeIntrinsics` (qua cả tệp và
  `load_intrinsics`), tia lệch tia của OpenCV dưới 0,05°;
- tiêu chí chấp nhận lấy đúng số liệu: độ nghiêng bảng của từng ảnh khớp tư thế thật đã dựng ảnh trong 0,5°, θ lớn nhất
  đã thấy bảng khớp mô hình thật trong 0,2°; siết một ngưỡng thì hỏng đúng tiêu chí đó, ngưỡng bằng giá trị thì đạt;
  khối chuyển đổi không đạt thì tiêu chí sai số chuyển đổi hỏng dù sai số khớp nhỏ.

Trong lúc viết công cụ có hai phát hiện, cả hai đều **trên ảnh tổng hợp**:

1. **Góc do `findChessboardCornersSB` trả về lệch có hệ thống**, kể cả khi bật ACCURACY: trung bình 0,12 px, lớn nhất
   1,5 px trên bảng nhỏ ở góc ảnh. Độ lệch này làm fx ra 352,07 thay vì 351,0 (lệch 0,3 %), và mô hình sai tới 2,3 px ở
   góc ảnh. Khi tinh chỉnh thêm bằng `cornerSubPix`, góc chỉ còn lệch trung bình 0,06 px và fx ra 351,03. Vì vậy công
   cụ **luôn** tinh chỉnh bằng `cornerSubPix`, và test sẽ hỏng nếu bỏ bước này. Chế độ SB nhanh cộng `cornerSubPix` cho
   kết quả tốt ngang SB kỹ cộng `cornerSubPix`, mà chỉ mất khoảng 15 ms/khung thay vì 38 ms trên máy bàn i9. Chưa biết
   độ lệch này còn không trên ảnh MJPEG thật.
2. `estimateChessboardSharpness` trả về giá trị 9999, tương phản 0, khi ô trên ảnh chỉ khoảng 8 px. Công cụ coi đó là
   "không đo được độ nét", không coi là "mờ".

**Các phép kiểm này chưa chứng minh:** ống kính thật khớp tốt với mô hình 4 hệ số (camera tổng hợp dùng đúng mô hình
đó nên luôn khớp); ảnh nén MJPEG, rolling shutter, phơi sáng tự động và độ mờ thật không làm lệch góc; máy in in đúng tỉ
lệ; bảng dán đủ phẳng; và công cụ chụp, hiệu chuẩn được với camera thật.

*Đính chính 24/09/2026:* bản đầu của mục này ghi giao diện chưa từng mở camera thật và `usb_camera_factory` chưa chạy lần
nào. Thực ra sáng 24/09 (khoảng 10:55, trước khi commit), giao diện đã mở camera thật một lần: cổng 2, 640×480, khoảng
6 s, qua `usb_camera_factory` (tức `resolve_ports`, `UsbCameraSource` và kiểm `mode_mismatch` đã chạy, không báo lệch
mode). Lần này chạy bằng một script thử tạm gọi thẳng `CalibWindow`, không phải lệnh `python -m autopark.ui.calib_app`.
Ảnh sống hiện lên; dòng trạng thái ghi 20,7 khung dò/s, 0 khung hỏng (cắt 0, xé 0), 0 khung cũ, 0 lỗi đọc. Không có bảng
trước camera (chưa in bảng) nên không dò được góc, và không chụp ảnh nào. Lần chạy chỉ để lại ảnh chụp màn hình trong thư
mục tạm của phiên làm việc, không lưu vào `runs/` (không có `runs/calib/`). Chưa hiệu chuẩn camera nào; ba cổng còn lại
chưa mở bằng công cụ này.

## 6. Chưa làm

- **Ngoại tham và rig.** Chưa có `camera_rig_extrinsics.yaml`, và chưa có vị trí/hướng camera so với xe. Việc này cần gá
  cứng và một cách đo, chẳng hạn đặt bảng trên sàn ở vị trí đo được rồi dùng `cv2.fisheye.solvePnP` với nội tham ở đây,
  hoặc đo tay rồi kiểm lại bằng vật mẫu trên BEV. Chưa chọn cách nào, chưa làm *(cập nhật 25/09/2026: công cụ theo cách thứ nhất, bảng in đặt trên sàn ở vị trí
  đo bằng thước, đã có từ commit `65b7127`; tệp ra là `configs/rig/camera_rig_extrinsics_v1.json`, không phải `.yaml`;
  xem mục 7. Chưa đo ngoại tham camera nào)*. Mỗi tệp nội tham có
  `"extrinsic": null`, `"rig": null` và một câu ghi chú nói rõ điều này.
- **Nối vào costmap.** `CameraCalibration.from_dict` (trong `perception/calibration.py`) đọc `theta_max_deg` khi khối
  nội tham có khóa này (sửa trong cùng commit 014dcdd, 24/09/2026; tệp WoodScape không có khóa này nên vẫn dùng 100°).
  Điều này cần vì đa thức khớp ở đây chỉ bảo đảm tăng đơn điệu tới θ ở góc ảnh (khoảng 68° trên camera tổng hợp). Nhưng
  hàm vẫn chưa nạp thẳng được `calibration/cam_p*.json`: nó đọc nội tham ở khóa `intrinsic` và bắt buộc có khối
  `extrinsic`, còn các tệp này ghi nội tham ở khóa `woodscape_intrinsic` và có `"extrinsic": null`. Hiện chỉ nạp được
  nội tham bằng `fisheye_calib.load_intrinsics(...)`, trả về `FisheyeIntrinsics` với `theta_max` đúng. Muốn đưa vào
  `CameraCalibration` thì cần ngoại tham, và một bước ghép khối `woodscape_intrinsic` với ngoại tham thành dạng
  `from_dict` đọc được. Cả hai việc này chưa làm. *(Cập nhật 25/09/2026: công cụ đo ngoại tham đã có từ commit
  `65b7127`; bước ghép làm bằng `bev.load_rig()` (commit `1d2b857`): hàm này dựng thẳng `CameraCalibration` từ
  `fisheye_calib.load_intrinsics` và tệp ngoại tham rig, không qua `from_dict`; xem mục 7. `from_dict` vẫn chưa đọc
  được `cam_p*.json`, và chưa đo ngoại tham camera nào.)* *(Sửa 24/09/2026: bản đầu ghi `from_dict` bỏ qua `theta_max` và
  `calibration.py` chưa sửa; thực ra chính commit thêm công cụ này đã sửa.)*
- **Mặt nạ ROI** cho camera của dự án (thân xe, viền ống kính) chưa dựng. *(Cập nhật 25/09/2026: công cụ đã có, mục 7;
  vẫn chưa dựng ROI cho camera nào.)*
- **Kiểm trên ảnh thật:** RMS trên các ảnh để riêng không dùng để hiệu chuẩn, độ thẳng của đường thẳng thật sau khi nắn,
  so sánh bốn camera với nhau, và độ ổn định khi rút/cắm lại hoặc khi camera nóng lên. Tất cả đều chưa làm.

## 7. Bước tiếp theo: ngoại tham và mặt nạ ROI (thêm tối 24/09/2026)

Sau khi có `calibration/cam_p<N>.json`, bước tiếp theo là gá camera lên xe rồi đo **ngoại tham** (vị trí, hướng camera so
với xe) và vẽ **mặt nạ ROI** (loại thân xe, dây, viền ống kính). Cách làm từng bước ở
[NGOAI_THAM_VA_ROI.md](NGOAI_THAM_VA_ROI.md). Công cụ ngoại tham đặt bảng in của mục 2 nằm trên sàn ở vị trí đo bằng thước
và dùng chính nội tham ở đây. Nó từ chối chạy khi thiếu tệp nội tham của camera đó, hoặc khi tệp là của cổng khác.
*(02/10/2026, T11: cũng từ chối tệp `cam_<tên>.json` của camera ngoài hub, mục 3.)*

Công cụ:

- ngoại tham: `perception/extrinsics_calib.py`, ghi `configs/rig/camera_rig_extrinsics_v1.json`;
- ROI: `perception/roi_tool.py`, ghi `configs/roi/rig_v1/roi_p<N>.png`;
- giao diện: `ui/roi_app.py`, hai thẻ "Ngoại tham" và "ROI".

Như vậy gạch đầu dòng "Ngoại tham và rig" và "Mặt nạ ROI" của mục 6 nay đã có công cụ. Nhưng công cụ **mới chỉ kiểm trên
ảnh tổng hợp** (NGOAI_THAM_VA_ROI.md mục 7), và chưa đo ngoại tham hay dựng ROI cho camera nào, vì chưa có nội tham, chưa
có xe, chưa gá camera. Ghép nội tham với ngoại tham cho BEV đã có sẵn trong `bev.load_rig()`, không cần sửa
`CameraCalibration.from_dict`.
