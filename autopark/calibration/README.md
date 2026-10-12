# calibration/: tệp hiệu chuẩn camera

Thư mục này chứa hiệu chuẩn **nội tham** của từng camera. Camera của xe được gọi theo **cổng hub**, vì index OpenCV của camera đổi sau khi khởi động lại máy, còn cổng hub thì không ([docs/usb_topology.md](../docs/usb_topology.md)). Từ 02/10/2026, camera không qua hub, như camera trên cao, được gọi theo tên (bảng dưới). Hướng dẫn in bảng, chụp ảnh, tiêu chí chấp nhận và những gì chưa làm nằm ở [docs/HIEU_CHUAN_CAMERA.md](../docs/HIEU_CHUAN_CAMERA.md).

## Hiện trạng

- Lúc viết README này (24/09/2026), **chưa có tệp `cam_p*.json` nào**, vì chưa chụp ảnh bảng từ camera thật. Lần kiểm ngày 30/09/2026 ghi trong [tổng hợp dự án](../../TONG_HOP_DU_AN.md) vẫn chưa có tệp nào.
- Ngoại tham đo và ROI cho camera dự án cũng chưa có (cuối tệp).

## Đặt tên

| Tệp | Nội dung |
|---|---|
| `cam_p<N>.json` | Nội tham camera ở cổng hub N (1..4), mode **640×480**, là mode chạy chung bốn camera |
| `cam_p<N>_<W>x<H>.json` | Nội tham cùng camera đó ở mode khác, ví dụ `cam_p2_1280x720.json`. Đây là một hiệu chuẩn riêng: K của mode này không đem dùng cho mode kia |
| `cam_<tên>.json`, `cam_<tên>_<W>x<H>.json` | Nội tham camera KHÔNG qua hub 1..4 (camera trên cao), khóa theo tên `--camera-name`; thêm 02/10/2026 (T11), chi tiết dưới bảng |
| `bang_in/ban_co_9x6_20mm_A4.{pdf,png,json}` | Bảng để in, khổ A4, ô danh định 20 mm (tạo bằng `python -m autopark.perception.calib_board`) |
| `bang_in/ban_co_9x6_30mm_A3.{pdf,png,json}` | Như trên, khổ A3, ô 30 mm |
| `bang_in/aruco/aruco_DICT_4X4_50_100mm_A4_id0-47.{pdf,json}` | Tờ marker ArUco cho mốc sàn của tham chiếu trên cao; thêm 02/10/2026 (T4), chi tiết dưới bảng |
| `bang_in/aruco/aruco_DICT_4X4_50_80mm_A4_id48-49.{pdf,json}` | Như trên cho hai marker xe (48 = sau, 49 = trước, cạnh 80 mm, một trang A4 ngang). Tạo bằng `--ids 48,49 --size-mm 80` |

T4 và T11 là hai trong các công cụ nghiệm thu T1–T15 ([docs/KICH_BAN_NGHIEM_THU.md](../docs/KICH_BAN_NGHIEM_THU.md) mục 7).

**Camera không qua hub (`cam_<tên>.json`).**

- Tên đặt bằng `--camera-name`: chữ thường không dấu, số, gạch dưới, bắt đầu bằng chữ, tối đa 32 ký tự. Tên không bắt đầu bằng `p<số>` và không kết thúc bằng `_<W>x<H>`.
- Tạo bằng `calib_app --index N [--camera-name TÊN]`. Tên mặc định là `tren_cao`; ảnh và bản sao ở `runs/calib/<ngày giờ>_<tên>/`.
- Hoặc tạo bằng `fisheye_calib calibrate --images <thư mục> --camera-name TÊN`. Lệnh này phải có `--port` hoặc `--camera-name`, không có tên mặc định, và không ghi gì vào `runs/calib/`.
- BEV và AI camera không đọc tệp này. Công cụ ngoại tham và ROI từ chối nó với lời báo rõ.
- Chỉ công cụ tham chiếu trên cao T4 (`evaluation/overhead_ref.py`, `ui/overhead_app.py`) đọc `cam_tren_cao_*.json`, và công cụ đó từ chối tệp của camera cổng hub ([docs/THAM_CHIEU_TREN_CAO.md](../docs/THAM_CHIEU_TREN_CAO.md) mục 4).
- Phần này mới chỉ được kiểm offscreen với camera giả.

**Tờ marker ArUco (`bang_in/aruco/`).** Tờ mốc sàn có mã 0–47, cạnh 100 mm, 48 trang A4, mỗi trang một mốc có vạch giữa cạnh để đo tâm. Tạo bằng lệnh dưới; PNG (`--png`) chỉ để xem, không commit. Cách in và đo tâm: [docs/THAM_CHIEU_TREN_CAO.md](../docs/THAM_CHIEU_TREN_CAO.md) mục 2.

```
python -m autopark.perception.aruco_sheet --ids 0-47 --size-mm 100 --out calibration/bang_in/aruco
```

**Lưu và bản chính thức.** Mỗi lần bấm "Lưu" trong `autopark.ui.calib_app`, công cụ ghi đè `cam_p<N>.json` và cất một bản sao cùng các ảnh đã dùng vào `runs/calib/<ngày giờ>_p<N>/`. Thư mục `runs/` không nằm trong git, nên bản `cam_p<N>.json` đã commit mới là bản chính thức.

**Tên tệp bảng in.** Nếu chỉnh cỡ ô danh định, tên tệp bảng in đổi theo; dấu chấm được thay bằng `p`. Ví dụ ô 19.5 mm thành `ban_co_9x6_19p5mm_A4.pdf`.

## Nội dung một tệp `cam_p<N>.json`

Định dạng `"format": "autopark.fisheye_intrinsics/1"`, là JSON thuần, đọc bằng `fisheye_calib.load_calibration()`.

| Khóa | Ý nghĩa |
|---|---|
| `camera.hub_port`, `camera.source_id` | Cổng hub (danh tính của camera) và tên nguồn `cam_pN`. Camera ngoài hub khác một chút (dưới bảng) |
| `image_size` | [rộng, cao] của ảnh đã hiệu chuẩn. Chỉ dùng K, D cho ảnh đúng cỡ này |
| `model`, `K`, `D` | Mô hình Kannala–Brandt của `cv2.fisheye`: ma trận K 3×3 (skew = 0) và 4 hệ số D. Dùng thẳng với `cv2.fisheye.*` |
| `rms_px`, `opencv_rms`, `max_view_rms_px` | RMS chiếu lại trên mọi góc của các ảnh được dùng; số do OpenCV trả về; RMS của ảnh tệ nhất còn dùng |
| `views[]` | Từng ảnh: có được dùng không, RMS, sai số lớn nhất, lý do bị loại, khoảng cách tới bảng, độ nghiêng bảng, chất lượng lúc chụp |
| `board`, `square_mm_measured` | Bảng (số góc trong, cỡ ô dùng để tính). `square_mm_measured` là `null` nếu người chụp chưa xác nhận đã đo lại cỡ ô bằng thước |
| `coverage` | Lưới phủ 8×6: số góc bảng trong từng ô, tỉ lệ ô có góc, bốn khối góc ảnh có điểm hay không |
| `field_of_view_deg` | Trường nhìn ngang/dọc/chéo **suy từ mô hình**, không phải đo trực tiếp; θ ở bốn góc ảnh; `theta_observed_max_deg` là θ lớn nhất đã thấy bảng (lớn hơn giá trị này là ngoại suy) |
| `woodscape_intrinsic` | Cùng nội tham đó ở dạng đa thức của dự án (`FisheyeIntrinsics`), chi tiết dưới bảng. Nạp bằng `fisheye_calib.load_intrinsics()` |
| `acceptance` | Các tiêu chí **đề xuất**, chưa kiểm trên camera thật, và kết quả đạt/chưa đạt của từng tiêu chí. Tiêu chí sai số chuyển đổi chỉ đạt khi `woodscape_intrinsic.ok` cũng đúng |
| `extrinsic`, `rig` | Luôn là `null`: tệp này chỉ có nội tham. Ngoại tham đo riêng sau khi gá camera, ghi vào `configs/rig/camera_rig_extrinsics_v1.json` (cuối tệp) |
| `images_dir`, `capture` | Nơi lưu ảnh đã dùng (trong `runs/calib/`), công cụ đã tạo ra tệp |
| `created_local`, `software` | Thời điểm tạo; phiên bản OpenCV, numpy, Python |

Ghi chú cho bảng:

- **Camera ngoài hub** (từ 02/10/2026, T11) có `hub_port` = `null`, thêm `camera.name` và `camera.opencv_index`, và `source_id` = `cam_<tên>`. `camera.opencv_index` là index OpenCV lúc chụp, chỉ để tra; nó là `null` khi hiệu chuẩn từ thư mục ảnh.
- **`woodscape_intrinsic`** dùng cùng khóa với tệp WoodScape: `k1..k4`, `cx_offset`, `cy_offset`, `aspect_ratio`. Khối này còn có `theta_max_deg` (θ ở góc ảnh `theta_image_corner_deg`, nâng thêm `theta_max_raise_deg` cho đa thức chạm tới điểm ảnh góc), sai số khớp lớn nhất (px), kết quả kiểm chiếu, `corners_invertible`, `ok` và `reason`. `load_intrinsics()` từ chối nếu `ok` là false hoặc cỡ ảnh khác.

Kiểm nhanh một tệp:

```
.\.venv\Scripts\python.exe -X utf8 -m autopark.perception.fisheye_calib check calibration/cam_p1.json
```

**Lưu ý về `CameraCalibration.from_dict`.** Hàm `perception/calibration.py::CameraCalibration.from_dict` hiện **chưa** đọc thẳng được các tệp này. Hàm đó cần khối `intrinsic` và khối `extrinsic`, còn tệp ở đây ghi nội tham ở `woodscape_intrinsic` và chưa có ngoại tham (`extrinsic` là `null`). Hàm đã đọc `theta_max_deg` khi có, từ 24/09/2026. Xem mục 6 của [docs/HIEU_CHUAN_CAMERA.md](../docs/HIEU_CHUAN_CAMERA.md).

BEV không cần hàm này. Từ tối 24/09/2026, BEV từ AI (`perception/bev.py::load_rig`) đọc các tệp này qua `fisheye_calib.load_intrinsics` và ghép với ngoại tham giả định ở `configs/rig/camera_rig_extrinsics_v0.json` ([docs/BEV.md](../docs/BEV.md)). Vì chưa có tệp `cam_p*.json` nào, BEV trên camera dự án chưa chạy được.

## Ngoại tham và ROI

Hai thứ này không nằm trong thư mục `calibration/`:

- Ngoại tham nằm trong `configs/rig/camera_rig_extrinsics_v1.json`, do `perception/extrinsics_calib.py` ghi.
- Mặt nạ ROI nằm trong `configs/roi/rig_v1/roi_p<N>.png`, do `perception/roi_tool.py` ghi.
- Giao diện chung cho cả hai là `ui/roi_app.py`.

Cả hai công cụ cần tệp `cam_p<N>.json` ở đây trước. Cách làm: [docs/NGOAI_THAM_VA_ROI.md](../docs/NGOAI_THAM_VA_ROI.md). Tới tối 24/09/2026, khi các công cụ này được thêm, chưa có tệp ngoại tham đo hay ROI nào cho camera dự án.
