# Dataset cho dự án MN300 tự đỗ

Ngày khảo sát: **20/09/2026**. Phạm vi: laptop, bốn camera USB quanh xe, LiDAR 2D, free-space/vật cản, BEV và định vị. Đây là danh mục các nguồn phù hợp tìm được, không khẳng định bao quát mọi dataset trên Internet. Bộ chỉ mới công bố trong paper được tách khỏi bộ đã có đường tải. Trạng thái tải thực tế nằm trong [TAI_VA_KIEM_TRA.md](TAI_VA_KIEM_TRA.md).

**Chọn ban đầu:** AVM-SS cho pipeline phân đoạn quanh xe; WoodScape cho ảnh fisheye thật; DROW và các log 2D SLAM cho LiDAR. Dataset ô đỗ đứng sau vì V1 cho người dùng tự đặt đích. Mức ưu tiên bên dưới là đánh giá cho dự án này, không phải xếp hạng của tác giả.

## 1. Camera quanh xe, free-space và fisheye

| ID / ưu tiên | Dataset, nguồn chính thức và đường tải | Nhãn thực có | Cách dùng và giới hạn | Truy cập / giấy phép dữ liệu |
|---|---|---|---|---|
| A01 / 1 | **AVM-SS / avm_seg_db** — [repo](https://github.com/Engro39/avm_dataset), [Google Drive của tác giả](https://drive.google.com/drive/folders/1izgXSHUisjdJMMLz43B8vjI9-JjqTDQL) | 6.763 ảnh 320×160; mask free space, marker, vehicle, other objects; ego bị bỏ qua. | Phù hợp nhất để làm loader, chuyển nhãn và baseline bãi đỗ. Ảnh AVM đã chiếu/ghép, không thay được hiệu chuẩn bốn camera USB. | Link công khai; README chưa nêu giấy phép dữ liệu rõ ràng. Đã kiểm tra cặp mẫu, xem mục 7. |
| A02 / 1 | **WoodScape** — [repo](https://github.com/valeoai/WoodScape), [Drive](https://drive.google.com/drive/folders/1X5JOMEfVlaXfdNy24P8VA-jMs0yzf_HR) | Semantic 10 lớp gồm void; instance polygon hơn 40 lớp; calibration và các task khác tùy gói phát hành. | Nguồn fisheye thật quan trọng. Bản công khai có khoảng 8,2k ảnh có nhãn; không giả định bốn hướng đều có nhãn đồng thời. | Dữ liệu proprietary; MIT của code không áp dụng cho data. [Điều khoản](https://drive.google.com/file/d/12IrLnGfng6s-NogJLIvUZsCxF1NDA-FA/view). |
| A03 / 2 | **SynWoodScape** — [paper tác giả](https://arxiv.org/abs/2203.05056), [đầu mối WoodScape](https://github.com/valeoai/WoodScape) | Dữ liệu tổng hợp bốn fisheye, semantic/depth/flow và nhiều task; paper nêu 80k ảnh. | Hợp để thử hình học nhiều camera/BEV. Phân biệt bộ tổng hợp với WoodScape thật; cần xác nhận gói tải thực tế. | Chưa xác nhận đường tải toàn bộ ổn định và license riêng trong lần khảo sát; chưa coi là đã tải. |
| A04 / 2 | **FishEye8K / FE-DETRAC** — [repo](https://github.com/MoyoG/FishEye8K), [cổng dữ liệu](https://scidm.nchc.org.tw/en/dataset/fisheye8k) | 8.000 ảnh; bounding box 5 lớp: người, xe đạp, ô tô, xe tải, bus. | Dùng detector vật thể trên ảnh méo; camera giám sát trên cao, khác camera gắn sát xe. Không có mask free-space đầy đủ. | Cổng hiện dùng tên FE-DETRAC; điều khoản công bố CC BY-NC-SA 4.0. Chọn nhãn cập nhật 01/2024 theo repo. |
| A05 / 3 | **PAIR360** — [trang nhóm AIRLAB](https://airlabkhu.github.io/PAIR-360-Dataset/) | Panorama/fisheye, LiDAR 32 kênh, IMU/GPS, map; nhãn/depth có thành phần sinh bằng mô hình. | Tham khảo chiếu LiDAR–camera và 360°. Không coi pseudo-label là ground truth độc lập; không giống LiDAR 2D. | ODbL theo trang dự án; tải cần xin mật khẩu qua email. Chưa tải, chưa gửi email. |

## 2. Phân đoạn đường, vật nhỏ và vùng không chắc chắn

| ID / ưu tiên | Dataset và nguồn chính thức | Nhãn / ứng dụng | Giới hạn và cách tải / giấy phép |
|---|---|---|---|
| B01 / 2 | **Cityscapes** — [overview](https://www.cityscapes-dataset.com/dataset-overview/), [tải](https://www.cityscapes-dataset.com/downloads/) | Semantic/instance/panoptic; road, sidewalk, người, xe, tường, cột. 5k fine + 20k coarse. | Đăng ký và điều khoản nghiên cứu riêng; camera đường phố. `parking` thuộc nhóm không tính đánh giá, thường thành void trong train IDs; không được mặc định có lớp ô đỗ huấn luyện. |
| B02 / 2 | **BDD100K** — [repo](https://github.com/bdd100k/bdd100k), [tài liệu](https://doc.bdd100k.com/) | Drivable-area, lane, detection, semantic/instance và tracking, tùy tập con. | Chọn gói ảnh + nhãn của đúng task, không tải mọi video; không phải toàn bộ 100k video đều có semantic mask. Trang tải/điều khoản BDD100K cần kiểm tra lúc đăng ký. |
| B03 / 2 | **Mapillary Vistas** — [cổng dataset](https://www.mapillary.com/dataset/vistas), [evaluation repo](https://github.com/mapillary/mapillary_vistas) | Semantic/instance nhiều loại mặt đường, vật và cảnh. | Tốt cho đa dạng cảnh; chuyển schema theo phiên bản. Cổng yêu cầu đăng nhập trong lần kiểm tra; cần điều khoản dữ liệu riêng, không lấy license scripts làm license ảnh. |
| B04 / 2 | **CamVid** — [Cambridge](https://mi.eng.cam.ac.uk/research/projects/VideoRec/CamVid/) | Hơn 700 ảnh được kiểm tra nhãn pixel 32 lớp, gồm road/parking block/pole/vehicle. | Nhỏ, hợp chạy baseline; bản 11 lớp là phép gộp riêng. Trang có ảnh/nhãn và bảng màu; một số link lưu trữ cũ có thể hỏng. Chưa xác minh license chuẩn hóa của toàn bộ ảnh. |
| B05 / 2 | **KITTI Road** — [benchmark và tải](https://www.cvlibs.net/datasets/kitti/eval_road.php) | 289 train, 290 test; mask road/ego-lane, calibration; gói cơ sở khoảng 0,5 GB. | Hợp kiểm tra road segmentation/BEV; không phải nhãn toàn bộ vật cản. Tải qua tài khoản; điều khoản KITTI, kiểm tra trên cổng. |
| B06 / 2 | **ACDC** — [ETH](https://acdc.vision.ee.ethz.ch/) | 4.006 ảnh sương mù, đêm, mưa, tuyết; 19 lớp, ảnh điều kiện thường tương ứng và invalid masks. | Hợp kiểm thử bất định/thiếu sáng. Invalid mask không tự tương đương lớp UNKNOWN vận hành. Điều khoản riêng, cho nghiên cứu/thử nghiệm phi thương mại. |
| B07 / 2 | **Lost and Found** — [nguồn gốc](http://www.6d-vision.com/lostandfounddataset), [paper](https://arxiv.org/abs/1609.04653) | Vật nhỏ trên đường, nhãn obstacle/free-space và stereo. | Hữu ích cho hộp/vật thấp. Máy chủ cũ chưa xác minh tải thành công; cần giữ điều khoản nguồn gốc. Không dùng test để huấn luyện. |
| B08 / 2 | **Fishyscapes** — [trang benchmark](https://fishyscapes.com/) | Nhãn anomaly pixel; gồm dữ liệu thật dựa trên Lost and Found và anomaly tổng hợp. | Đánh giá khả năng báo vùng lạ, không thay tập train semantic chính. Có phần benchmark giữ kín; điều khoản ảnh gốc và nhãn có thể khác nhau. |
| B09 / 2 | **RoadAnomaly21** — [Segment Me If You Can](https://segmentmeifyoucan.com/) | Nhãn anomaly trên cảnh đường cho benchmark. | Dùng kiểm thử lỗi vật bị nhận nhầm thành nền; cần bộ đánh giá/download theo trang tác giả và giữ split. License chưa xác minh độc lập. |
| B10 / 2 | **RoadObstacle21** — [Segment Me If You Can](https://segmentmeifyoucan.com/) | Benchmark vật cản trên vùng đường. | Bổ sung vật thấp/lạ; không suy độ chính xác khoảng cách thật chỉ từ mask. License và truy cập theo benchmark, chưa tải. |

## 3. Ô đỗ và tình trạng trống/bận — tính năng mở rộng

| ID / ưu tiên | Dataset và nguồn chính thức | Nhãn / phạm vi | Truy cập / giấy phép và hạn chế |
|---|---|---|---|
| C01 / 3 | **AVM-PS / avm_ps_db** — [repo](https://github.com/Engro39/avm_dataset), [Drive](https://drive.google.com/drive/folders/1izgXSHUisjdJMMLz43B8vjI9-JjqTDQL) | 21.581 frame, 35.889 chỗ đỗ theo README. | Gói khác AVM-SS; không thay nhãn free-space. Link công khai, license dữ liệu chưa rõ; chưa ưu tiên tải. |
| C02 / 3 | **Tongji PS2.0** — [DeepPS](https://cslinzhang.github.io/deepps/) | 9.827 train + 2.338 test; hình học điểm/ô đỗ trong AVM. | Tải `ps2.0.zip` trên trang tác giả; cần đọc format MAT/tool gán nhãn. Không có mask pixel mọi vật cản. License dữ liệu chưa xác minh. |
| C03 / 3 | **PSV** — [paper gốc](https://arxiv.org/abs/1804.07027), [đầu mối tải qua tác giả VPS-Net](https://github.com/weili1457355863/VPS-Net) | Segmentation vạch/ô đỗ panoramic surround view. | Không phải segmentation vật cản tổng quát; link Tongji cũ cần kiểm tra. License dữ liệu chưa rõ. |
| C04 / 3 | **PIL-park / SNU** — [repo tác giả](https://github.com/dohoseok/context-based-parking-slot-detect) | Vị trí, góc, kiểu, khả dụng của ô đỗ trong ảnh AVM. | Repo có train/test Drive riêng; tên SNU/PIL-park không phải hai bộ độc lập. Chưa xác minh license ảnh. |
| C05 / 3 | **ParkScape** — [repo tác giả](https://github.com/Vipermdl/ParkScape) | 10.000 ảnh fisheye, nhãn góc ô đỗ. | Link Baidu; README ghi license không rõ (`no License`). Không coi là bộ tự do sử dụng; không có mask obstacle/free-space. |
| C06 / 3 | **VPS-Net extra annotations** — [repo tác giả](https://github.com/weili1457355863/VPS-Net) | Bổ sung nhãn ô trống cho PS2.0/PSV. | Đây là phần mở rộng nhãn, không phải nguồn ảnh mới; tránh đếm trùng và rò rỉ train/test. License cần kiểm tra cả ảnh gốc và nhãn bổ sung. |
| C07 / 3 | **PKLot** — [UFPR](https://web.inf.ufpr.br/vri/databases/parking-lot-database/) | 12.417 ảnh bãi, XML tọa độ và nhãn occupied/vacant; khoảng 695.900 crop. | Camera cố định trên cao; hợp phân loại ô, ít sát V1. Trang nguồn ghi CC BY 4.0. |
| C08 / 3 | **CNRPark+EXT** — [trang tác giả](https://cnrpark.it/) | Khoảng 150k crop occupied/vacant và thông tin vị trí ô. | Góc camera cố định; không có dense obstacle mask. Trang tải có gói crop nhỏ; một lần truy cập trả 502, không đồng nghĩa ngừng cung cấp. Cần xem license hiện hành khi tải. |

## 4. LiDAR 2D, định vị và dữ liệu robot

| ID / ưu tiên | Dataset và nguồn chính thức | Dữ liệu / mục đích | Truy cập / giới hạn |
|---|---|---|---|
| D01 / 1 | **Bộ log 2D SLAM cổ điển** — [StachnissLab](https://www.ipb.uni-bonn.de/datasets/), [bản chuyển đổi IR-MCL](https://github.com/PRBonn/ir-mcl/blob/main/PREPARE_DATA.md) | Intel Lab, MIT CSAIL, Freiburg, Seattle, MIT corridor và các log khác; laser/odometry dạng CARMEN/GFS. | Hợp scanner/map/định vị 2D trước RPLIDAR. Phân biệt raw và corrected, corrected pose không phải ground truth độc lập. License từng log cần kiểm tra; không mặc định chung MIT. |
| D02 / 1 | **DROW v2** — [repo và license](https://github.com/VisualComputingInstitute/DROW), [ZIP chính thức](https://github.com/VisualComputingInstitute/DROW/releases/download/v2/DROWv2-data.zip) | Laser 2D, odometry và nhãn người/xe lăn/dụng cụ hỗ trợ đi lại, theo sequence. | Gói 197.970.996 byte theo GitHub API. MIT trừ `reha` giữ CC BY-NC-SA 3.0; không biến 29.96 N/A thành vùng trống. Không phải ground truth free-space camera. |
| D03 / 2 | **OpenLORIS-Scene** — [trang tác giả](https://lifelong-robotic-vision.github.io/dataset/scene) | Camera RGB-D/fisheye, IMU, odometry, laser scan, quỹ đạo tham chiếu. | Gần mô hình robot trong nhà; office có motion capture, nhiều cảnh khác dùng offline LiDAR SLAM. Market có cấu hình khác: đọc metadata từng scene. Drive/Baidu; license cần xác minh theo gói. |
| D04 / 2 | **MIT Stata Center** — [MIT](https://projects.csail.mit.edu/stata/) | Log robot với camera/laser/odometry, phục vụ mapping dài hạn. | Hợp replay/mapping, dung lượng lớn; tải từng ngày/sequence. Không mặc định cảm biến/tham chiếu giống sa bàn; đọc điều khoản nguồn. |
| D05 / 3 | **Oxford RobotCar** — [Oxford](https://robotcar-dataset.robots.ox.ac.uk/) | Camera, laser và dữ liệu định vị lặp lại cùng tuyến. | Dùng relocalization/thay đổi môi trường; quy mô và cảm biến khác MN300. Tải chọn sequence, license theo trang tác giả. |
| D06 / 3 | **TUM RGB-D** — [TUM](https://cvg.cit.tum.de/data/datasets/rgbd-dataset) | RGB-D và quỹ đạo tham chiếu cho visual SLAM. | Chỉ bổ sung kiểm thử ước lượng; bốn USB RGB không tự có depth như Kinect. Download từng sequence; license theo nguồn. |
| D07 / 3 | **EuRoC MAV** — [ETH ASL](https://projects.asl.ethz.ch/datasets/doku.php?id=kmavvisualinertialdatasets) | Stereo/IMU và tham chiếu, cho visual-inertial odometry. | Dữ liệu phương tiện bay; hữu ích kiểm tra đồng bộ/ước lượng, không học tự đỗ. Trang cũ thông báo chuyển địa chỉ; theo liên kết mới và điều khoản ETH. |

## 5. Camera–LiDAR 3D, BEV và tiền huấn luyện bổ sung

| ID / ưu tiên | Dataset và nguồn chính thức | Có thể dùng cho | Điều kiện / điểm không tương đương |
|---|---|---|---|
| E01 / 2 | **KITTI-360** — [trang tác giả](https://www.cvlibs.net/datasets/kitti-360/) | 2D/3D semantic, instance, pose, camera phối cảnh và fisheye. | CC BY-NC-SA 3.0; đăng ký. Không suy mọi fisheye đều có dense label như camera phối cảnh; SICK dạng pushbroom không giống scan ngang C1. |
| E02 / 2 | **nuScenes + lidarseg/panoptic/map** — [devkit tác giả](https://github.com/nutonomy/nuscenes-devkit), [tải](https://www.nuscenes.org/download) | Hợp nhất nhiều cảm biến, quỹ đạo, map; nhãn point cloud trong expansion riêng. | Cần tài khoản/Terms of Use; chọn mini trước. Nhãn map/3D không tự là pixel free-space. Không chuyển thuật toán yêu cầu LiDAR 3D sang C1 bằng cách đổi tên input. |
| E03 / 3 | **nuImages** — [devkit và setup](https://github.com/nutonomy/nuscenes-devkit#nuimages) | Nhãn ảnh cho nhận thức 2D; cùng hệ sinh thái nuScenes. | Là bộ ảnh riêng; cần samples + metadata đúng split; không giả định có chuỗi đồng bộ đa cảm biến đầy đủ. Tài khoản/điều khoản nuScenes. |
| E04 / 3 | **SemanticKITTI** — [dataset](https://www.semantic-kitti.org/dataset.html) | Semantic point cloud, động/tĩnh; nghiên cứu vật cản LiDAR. | Nhãn LiDAR 3D, không phải mask USB; cần tải scan KITTI và nhãn tương ứng. License theo nguồn KITTI/SemanticKITTI. |
| E05 / 3 | **Argoverse 2 Sensor / Lidar** — [trang chính thức](https://www.argoverse.org/av2.html) | Sensor có ảnh/cuboid/pose/map; bộ Lidar riêng chứa sequence không nhãn. | Chọn Sensor nếu cần giám sát; map polygon drivable không phải nhãn ảnh. Creative Commons share-alike theo Terms of Use; kiểm tra phiên bản cụ thể. |
| E06 / 3 | **Waymo Open Perception** — [cổng chính thức](https://waymo.com/open/) | Detection/segmentation cảm biến xe thật tùy release. | Tải cần đăng nhập Google và license Waymo. Chỉ chọn Perception phù hợp; Motion/End-to-End không thay dense free-space cho dự án. |
| E07 / 3 | **A2D2** — [cổng Audi](https://www.a2d2.audi/a2d2/en.html), [paper tác giả](https://arxiv.org/abs/2004.06320) | Camera/LiDAR, semantic và calibration. | Nguồn tham khảo fusion xe lớn. Cổng tải không truy cập được bằng công cụ trong lần này; chưa coi là tải được. Xác minh license của bản phát hành trước dùng. |
| E08 / 3 | **JRDB / JRDB-PanoTrack** — [cổng hiện hành](https://jrdb.erc.monash.edu/) | Robot quanh người, nhãn người 2D/3D; PanoTrack bổ sung panoptic. | Hợp test người gần robot, không có sẵn mọi loại vật thấp. Đăng nhập; nhãn của từng nhánh riêng, đọc điều khoản. |
| E09 / 3 | **COCO** — [API tác giả](https://github.com/cocodataset/cocoapi), [tải](https://cocodataset.org/#download) | Detector/instance segmentation các vật phổ biến. | Chỉ tiền huấn luyện hoặc thêm vật thể; bounding box/instance không phải dense free-space. Giấy phép nhãn và ảnh Flickr khác nhau; xem metadata/license gốc. |
| E10 / 3 | **Open Images V7** — [Google](https://storage.googleapis.com/openimages/web/index.html) | Detection/segmentation vật thể theo lớp/tập con. | Chỉ tải lớp/ảnh cần dùng; không phải nhãn nền đi được. Kiểm tra license ảnh và nhãn, tránh tải toàn kho cho baseline. |

## 6. Nguồn tổng hợp hoặc chưa xác nhận truy cập đầy đủ

| ID / ưu tiên | Nguồn | Lợi ích có thể có | Trạng thái thực tế |
|---|---|---|---|
| F01 / chờ | **FPD — Fisheye Parking Dataset** — [paper tác giả](https://arxiv.org/abs/2212.04111) | Perception fisheye trong bãi đỗ, gần bài toán. | Tìm thấy paper; chưa xác nhận endpoint tải công khai và license. Không đưa vào danh sách đã sẵn sàng huấn luyện. |
| F02 / chờ | **PPD — Parking Pedestrian Dataset** — [paper tác giả](https://arxiv.org/abs/2309.11002) | Người nhiều tư thế/che khuất trong bãi đỗ fisheye. | Tìm thấy paper; chưa xác nhận gói tải và license. |
| F03 / 3 | **SYNTHIA** — [trang tác giả](https://synthia-dataset.net/) | Dữ liệu tổng hợp có semantic để nghiên cứu chuyển miền. | Cổng chưa truy cập được trong lần kiểm tra; cần chọn release/đọc license. Nhãn tổng hợp không thay kiểm thử ảnh sa bàn. |
| F04 / 3 | **Virtual KITTI 2** — [NAVER LABS](https://europe.naverlabs.com/proxy-virtual-worlds-vkitti-2/) | RGB, semantic/instance/depth và biến đổi điều kiện tổng hợp. | Phù hợp thử độ bền thuật toán, không phải bốn fisheye bãi đỗ. Tải và license theo NAVER LABS. |

## 7. Kiểm tra nhãn đã thực hiện

Đã tải và xem **ảnh RGB + mask AVM-SS** do tác giả đặt trong repo, không phải ảnh tự tạo. [Nguồn ảnh](https://github.com/Engro39/avm_dataset/tree/master/images). Cặp mẫu nằm tại `samples/avm/image.jpg` và `samples/avm/gt.png`, có nguồn và SHA-256 trong `provenance.json`. Báo cáo bằng máy: [audit.json](samples/avm/audit.json).

| Nhãn gốc (RGB) | Nhãn dùng trong dự án | Số pixel trong mẫu |
|---|---|---:|
| Free space (0,0,255) | FREE = 0 | 34.923 |
| Marker (255,255,255) | FREE = 0 khi là vạch trên mặt nền | 4.060 |
| Vehicle (255,0,0) | OBSTACLE = 1 | 2.714 |
| Other (0,255,0) | OBSTACLE = 1 | 3.440 |
| Ego (0,0,0) | UNKNOWN/IGNORE = 255 | 6.063 |

Đây là **đề xuất ánh xạ nhãn cho dự án**. Khi train, 255 là ignore index; khi đưa sang costmap, vùng không hợp lệ/chưa quan sát bị chặn. Không coi UNKNOWN là một lớp đã được mô hình học nhận ra mọi vật lạ. Đọc mask bằng OpenCV phải đổi BGR→RGB trước đối chiếu bảng màu; resize mask dùng nearest-neighbor.

Với WoodScape, đã đọc [config mapping chính thức](https://github.com/valeoai/WoodScape/blob/master/scripts/configs/semantic_mapping_9_classes.json) và lưu tại `samples/woodscape/semantic_mapping_9_classes.json`: ID 1=road, 2=lanemarks, 3=curb, 4=person, 5=rider, 6=vehicles, 7=bicycle, 8=motorcycle, 9=traffic_sign; void không tự là free-space. File màu dùng **BGR**. Phải xác nhận đúng loại ảnh mask trong gói tải trước chuyển đổi.

Kết luận kiểm tra nhãn: **AVM-SS phù hợp trực tiếp** để thử free-space/obstacle; **WoodScape phù hợp có chuyển nhãn và kiểm tra vùng void**; **PS2.0/PSV/ParkScape/PIL-park không đủ nhãn pixel vật cản**. Không suy từ tên “parking dataset” rằng bộ đó giải quyết perception quanh xe.

## 8. Quy trình dùng dữ liệu cho dự án

1. Giữ bản gốc bất biến; ghi nguồn, ngày tải, tên release, giấy phép, dung lượng, SHA-256 và tình trạng giải nén. Không đưa ảnh đầy đủ lên Git; không tải trọng số `.pkl`/`.pth` rồi thực thi trong bước khảo sát dữ liệu.
2. Lập manifest các cặp ảnh–nhãn. Kiểm tra số lượng, kích thước, palette, giá trị lạ, file thiếu và mẫu đại diện; không chỉ xem thumbnail.
3. Giữ split của tác giả. Nếu cần chia mới, chia theo sequence/ngày/bãi/camera; ảnh liên tiếp hoặc ảnh gốc của bộ mở rộng không được rơi vào cả train và test.
4. Chọn AVM-SS làm baseline nhỏ; WoodScape bổ sung sau khi xác nhận camera USB 130° là phối cảnh hay fisheye và model hiệu chuẩn. Không tự dùng thông số camera dataset cho camera thật.
5. Test riêng vật thấp, hộp giấy, dây, mép sa bàn, phản chiếu, vật chưa có trong train. Theo dõi **obstacle bị dự đoán thành FREE** bên cạnh IoU; threshold phải được đo và chốt, chưa có kết quả AI trong giai đoạn này.
6. Camera thấp trên MN300, sàn phòng và vật cản mô hình khác xe thật ngoài đường. Ở giai đoạn cảm biến, thu tập dữ liệu đúng gá/ánh sáng/khoảng cách và nhãn bằng tay để đánh giá chuyển miền.
7. LiDAR 3D, depth suy ra từ AI và mask 2D không tự cung cấp khoảng cách an toàn của C1. Chỉ đưa kết quả vào costmap sau khi kiểm tra thời gian, frame, hình học và vùng không chắc chắn.

Các bộ dữ liệu ở đây phục vụ từng khối thuật toán. Không bộ nào tự chứng minh phanh, E-stop, độ chính xác BEV, khoảng dừng hay khả năng tự đỗ của MN300 thật.
