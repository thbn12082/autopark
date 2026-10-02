# calibration/: tệp hiệu chuẩn camera

Thư mục này chứa hiệu chuẩn **nội tham** của từng camera, gọi theo **cổng hub** *(camera không qua hub, thêm
02/10/2026: gọi theo tên, xem bảng dưới)*. Index OpenCV của camera đổi sau khi khởi động lại máy, còn cổng hub thì không
(docs/usb_topology.md). Hướng dẫn in bảng, chụp ảnh, tiêu chí chấp nhận và những gì chưa làm nằm ở
[docs/HIEU_CHUAN_CAMERA.md](../docs/HIEU_CHUAN_CAMERA.md).

## Đặt tên

| Tệp | Nội dung |
|---|---|
| `cam_p<N>.json` | Nội tham camera ở cổng hub N (1..4), mode **640×480**, là mode chạy chung bốn camera |
| `cam_p<N>_<W>x<H>.json` | Nội tham cùng camera đó ở mode khác, ví dụ `cam_p2_1280x720.json`. Đây là một hiệu chuẩn riêng: K của mode này không đem dùng cho mode kia |
| `cam_<tên>.json`, `cam_<tên>_<W>x<H>.json` | *(Thêm 02/10/2026, T11.)* Nội tham camera KHÔNG qua hub 1..4 (camera trên cao), khóa theo tên `--camera-name` (chữ thường không dấu, số, gạch dưới, bắt đầu bằng chữ, tối đa 32 ký tự; không bắt đầu bằng `p<số>`, không kết thúc bằng `_<W>x<H>`). Tạo bằng `calib_app --index N [--camera-name TÊN]` (tên mặc định `tren_cao`; ảnh và bản sao ở `runs/calib/<ngày giờ>_<tên>/`) hay `fisheye_calib calibrate --images <thư mục> --camera-name TÊN` (phải có `--port` hoặc `--camera-name`, không có tên mặc định; không ghi gì vào `runs/calib/`). BEV và AI camera không đọc tệp này; công cụ ngoại tham và ROI từ chối nó với lời báo rõ. Chỉ kiểm offscreen với camera giả |
| `bang_in/ban_co_9x6_20mm_A4.{pdf,png,json}` | Bảng để in, khổ A4, ô danh định 20 mm (tạo bằng `python -m autopark.perception.calib_board`) |
| `bang_in/ban_co_9x6_30mm_A3.{pdf,png,json}` | Như trên, khổ A3, ô 30 mm |

Khi viết README này (24/09/2026), **chưa có tệp `cam_p*.json` nào**: chưa chụp ảnh bảng từ camera thật. Mỗi lần bấm
"Lưu" trong `autopark.ui.calib_app`, công cụ ghi đè `cam_p<N>.json` và cất một bản sao cùng các ảnh đã dùng vào
`runs/calib/<ngày giờ>_p<N>/`. Thư mục `runs/` không nằm trong git, nên bản cam_p<N>.json đã commit mới là bản chính thức.

Nếu chỉnh cỡ ô danh định, dạng tên tệp bảng in sẽ đổi theo: dấu chấm được thay bằng `p`, ví dụ ô 19.5 mm thành
`ban_co_9x6_19p5mm_A4.pdf`.

## Nội dung một tệp `cam_p<N>.json`

Định dạng `"format": "autopark.fisheye_intrinsics/1"`, là JSON thuần, đọc bằng `fisheye_calib.load_calibration()`.

| Khóa | Ý nghĩa |
|---|---|
| `camera.hub_port`, `camera.source_id` | Cổng hub (danh tính của camera) và tên nguồn `cam_pN`. *(02/10/2026, T11: camera ngoài hub có `hub_port` = `null`, thêm `camera.name` và `camera.opencv_index` (index OpenCV lúc chụp, chỉ để tra; `null` khi hiệu chuẩn từ thư mục ảnh), `source_id` = `cam_<tên>`)* |
| `image_size` | [rộng, cao] của ảnh đã hiệu chuẩn. Chỉ dùng K, D cho ảnh đúng cỡ này |
| `model`, `K`, `D` | Mô hình Kannala–Brandt của `cv2.fisheye`: ma trận K 3×3 (skew = 0) và 4 hệ số D. Dùng thẳng với `cv2.fisheye.*` |
| `rms_px`, `opencv_rms`, `max_view_rms_px` | RMS chiếu lại trên mọi góc của các ảnh được dùng; số do OpenCV trả về; RMS của ảnh tệ nhất còn dùng |
| `views[]` | Từng ảnh: có được dùng không, RMS, sai số lớn nhất, lý do bị loại, khoảng cách tới bảng, độ nghiêng bảng, chất lượng lúc chụp |
| `board`, `square_mm_measured` | Bảng (số góc trong, cỡ ô dùng để tính). `square_mm_measured` là `null` nếu người chụp chưa xác nhận đã đo lại cỡ ô bằng thước |
| `coverage` | Lưới phủ 8×6: số góc bảng trong từng ô, tỉ lệ ô có góc, bốn khối góc ảnh có điểm hay không |
| `field_of_view_deg` | Trường nhìn ngang/dọc/chéo **suy từ mô hình**, không phải đo trực tiếp; θ ở bốn góc ảnh; `theta_observed_max_deg` là θ lớn nhất đã thấy bảng (lớn hơn giá trị này là ngoại suy) |
| `woodscape_intrinsic` | Cùng nội tham đó nhưng ở dạng đa thức của dự án (`FisheyeIntrinsics`, cùng khóa với tệp WoodScape: `k1..k4`, `cx_offset`, `cy_offset`, `aspect_ratio`), kèm `theta_max_deg` (θ ở góc ảnh `theta_image_corner_deg`, nâng thêm `theta_max_raise_deg` cho đa thức chạm tới điểm ảnh góc), sai số khớp lớn nhất (px), kết quả kiểm chiếu, `corners_invertible`, `ok` và `reason`. Nạp bằng `fisheye_calib.load_intrinsics()`; hàm này từ chối nếu `ok` là false hoặc cỡ ảnh khác |
| `acceptance` | Các tiêu chí **đề xuất**, chưa kiểm trên camera thật, và kết quả đạt/chưa đạt của từng tiêu chí. Tiêu chí sai số chuyển đổi chỉ đạt khi `woodscape_intrinsic.ok` cũng đúng |
| `extrinsic`, `rig` | Luôn là `null`: tệp này chỉ có nội tham. Ngoại tham (vị trí/hướng so với xe) đo riêng sau khi gá camera, ghi vào `configs/rig/camera_rig_extrinsics_v1.json` (*sửa khuya 24/09/2026:* trước ghi "`camera_rig_extrinsics.yaml`, chưa làm"; công cụ đã có, xem cuối tệp) |
| `images_dir`, `capture` | Nơi lưu ảnh đã dùng (trong `runs/calib/`), công cụ đã tạo ra tệp |
| `created_local`, `software` | Thời điểm tạo; phiên bản OpenCV, numpy, Python |

Kiểm nhanh một tệp:

```
.\.venv\Scripts\python.exe -X utf8 -m autopark.perception.fisheye_calib check calibration/cam_p1.json
```

**Lưu ý:** `perception/calibration.py::CameraCalibration.from_dict` hiện **chưa** đọc thẳng được các tệp này. Hàm đó cần
khối `intrinsic` và khối `extrinsic`, còn tệp ở đây ghi nội tham ở `woodscape_intrinsic` và chưa có ngoại tham
(`extrinsic` là `null`). Hàm đã đọc `theta_max_deg` khi có (từ 24/09/2026; bản đầu của README ghi hàm bỏ qua
`theta_max`). Xem mục 6 của [docs/HIEU_CHUAN_CAMERA.md](../docs/HIEU_CHUAN_CAMERA.md). *(Cập nhật tối 24/09/2026:
BEV từ AI — `perception/bev.py::load_rig` — đã đọc các tệp này qua `fisheye_calib.load_intrinsics` và ghép với ngoại
tham GIẢ ĐỊNH ở `configs/rig/camera_rig_extrinsics_v0.json`; xem [docs/BEV.md](../docs/BEV.md). Chưa có tệp `cam_p*.json`
nào, nên BEV trên camera dự án chưa chạy được.)*

**Ngoại tham và ROI (thêm tối 24/09/2026):** hai thứ này không nằm trong thư mục `calibration/`. Ngoại tham nằm trong
`configs/rig/camera_rig_extrinsics_v1.json`, do `perception/extrinsics_calib.py` ghi. Mặt nạ ROI nằm trong
`configs/roi/rig_v1/roi_p<N>.png`, do `perception/roi_tool.py` ghi. Giao diện chung cho cả hai là `ui/roi_app.py`. Cả hai
công cụ cần tệp `cam_p<N>.json` ở đây trước. Cách làm: [docs/NGOAI_THAM_VA_ROI.md](../docs/NGOAI_THAM_VA_ROI.md). Tới lúc
này chưa có tệp ngoại tham đo hay ROI nào cho camera dự án.
