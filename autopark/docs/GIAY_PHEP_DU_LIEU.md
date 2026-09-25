# Giấy phép dữ liệu — bảng kiểm, ngày kiểm 22/09/2026 (cập nhật 24/09 và 25/09/2026)

Mỗi dòng ghi giấy phép, câu trích nguyên văn và ngày tự kiểm. Bộ nào chưa đọc được văn bản gốc thì ghi
"chưa xác minh", không suy đoán.

*Cập nhật tối 24/09/2026:* thêm link tới toàn văn điều khoản WoodScape có sẵn trong repo và địa chỉ trang bộ dữ liệu mà
văn bản đó ghi; thêm dòng trọng số pretrained của torchvision dùng làm điểm khởi đầu huấn luyện (kể cả khả năng backbone
đã qua ImageNet, cần tra); thêm yêu cầu ghi công của DROW. Chi tiết ở mục "Kiểm tối 24/09/2026" cuối tệp.

*Cập nhật 25/09/2026:* người làm khóa luận **quyết định dùng mô hình huấn luyện trên WoodScape trong vòng điều khiển xe**
(AI camera là một nguồn vật cản cho planner), thay cho hướng "KHÔNG nối mô hình đó vào vòng điều khiển xe" (hướng 1,
ghi 22/09) mà tới 24/09 vẫn là hiện trạng. Mục mới "WoodScape trong vòng điều khiển: quyết định 25/09/2026" ngay dưới
bảng ghi: toàn văn câu điều khoản và hai cách đọc; việc các tài liệu trước tóm tắt câu đó thành "cấm" là mạnh hơn văn
bản; kết quả kiểm trên web ngày 25/09; cách hỏi Valeo; đề xuất sửa link ghi công; điều khóa luận nên viết và phương án
dự phòng. **Valeo chưa xác nhận cách đọc mà dự án chọn.** Các đoạn viết 22/09 và 24/09 giữ nguyên làm lịch sử, chỗ nào
không còn là kế hoạch hiện tại có ghi chú 25/09/2026 ngay tại chỗ.
*Sửa sau rà soát (25/09/2026):* bảng các chỗ viết "cấm" thêm một chỗ sót (`DAN_Y_KHOA_LUAN.md` dòng 1467) và ghi rõ
bằng chứng 24/09 cố ý giữ nguyên; thêm bảng các chỗ còn ghi "chờ quyết định giấy phép"; sửa câu nói toàn văn điều khoản
"khớp nguyên văn bản ghi 22/09" (bản 22/09 có lược); chép đủ bình luận ở issue #14 thay vì một câu; tách
`woodscape.valeo.com/dataset` khỏi địa chỉ ghi trong README (địa chỉ đó là website ở khung About của repo GitHub); ghi
rõ quyết định chưa nói gì về nhãn nháp khi gán nhãn sa bàn.

| Bộ | Giấy phép | Câu trích / nguồn | Kiểm ngày |
|---|---|---|---|
| **WoodScape** (đã huấn luyện) | Điều khoản riêng của Valeo, dữ liệu proprietary. MIT của mã KHÔNG áp dụng cho ảnh. | [LICENSE.pdf](https://drive.google.com/file/d/12IrLnGfng6s-NogJLIvUZsCxF1NDA-FA/view): *"You shall use the Dataset only (i) for research purposes ... (ii) teaching, (iii) to perform benchmarking for purposes of academic or applied research publication or (iv) for personal experimentation."* và *"You shall not use the Dataset for commercial purposes ... and notably not use or deploy the Dataset, any models trained on or refined using the Dataset including pre-training or augmentation, in operation of a vehicle or to assist in the operation of vehicle."* *Thêm tối 24/09/2026:* toàn văn (2 trang) có trong repo: [datasets/woodscape_metadata/LICENSE.pdf](../datasets/woodscape_metadata/LICENSE.pdf) (đã commit, không bị git-ignore). Hai câu trích ở trên khớp văn bản đọc từ tệp này. Tệp ghi bộ dữ liệu có tại `woodscape.valeo.ai`, xem mục cuối. *Thêm 25/09/2026:* câu thứ hai (ở ô này có lược "...") được trích đủ, kèm hai cách đọc và quyết định dùng mô hình trong vòng điều khiển: mục "WoodScape trong vòng điều khiển" ngay dưới bảng. | 22/09/2026; toàn văn trong repo đọc lại tối 24/09/2026 và 25/09/2026 |
| **ACDC** | Nghiên cứu phi thương mại, ETH Zürich | `datasets/training/acdc/gt/License.pdf` mục 1.1: *"made freely available to academic and non-academic entities for non-commercial purposes only (such as academic research, teaching, scientific publications, or personal experimentation)"*; mục 2.5 cấm mục đích quân sự. **Không có điều khoản nào về vận hành phương tiện.** | 22/09/2026 |
| **AVM-SS** | KHÔNG có tuyên bố giấy phép | [repo Engro39/avm_dataset](https://github.com/Engro39/avm_dataset) không có file LICENSE; API GitHub trả `license: null`. Không có giấy phép nghĩa là tác giả giữ toàn quyền. | 22/09/2026 |
| **DROW v2** | MIT, riêng phần `reha` giữ CC BY-NC-SA 3.0 | [repo](https://github.com/VisualComputingInstitute/DROW). *Thêm tối 24/09/2026:* README của tác giả (bản sao `datasets/drow/README_source.md`, git-ignore) yêu cầu trích **cả hai** bài DROW khi dùng bất cứ thứ gì trong repo, và giải thích MIT là dùng được nếu ghi công tác giả. Hình nào dựng từ DROW mà đưa vào khóa luận thì phải trích hai bài đó, xem mục cuối. | 20/09/2026; ghi công kiểm tối 24/09/2026 |
| **Trọng số khởi tạo torchvision** `LRASPP_MobileNet_V3_Large_Weights.COCO_WITH_VOC_LABELS_V1` (điểm bắt đầu của mọi lượt huấn luyện đã chạy: 12 lượt chính `runs/ai_*/run_manifest.json` và 2 lượt kiểm tra thử `runs/ai_woodscape_rtx4000_v1_checks/smoke`, `overfit32`, tổng 14 `run_manifest.json` trong `runs/`; thêm tối 24/09/2026) | Mã torchvision: BSD. **Điều khoản riêng của tệp trọng số: cần tra** | Mô tả trong torchvision 0.26.0: huấn luyện trên một phần COCO, chỉ dùng 20 lớp có trong Pascal VOC. Tức là ảnh COCO với bộ nhãn VOC, không phải ảnh VOC. *Thêm tối 24/09/2026:* mô tả đó không nói backbone khởi tạo từ đâu. Hàm dựng `lraspp_mobilenet_v3_large` trong cùng tệp mặc định `weights_backbone=MobileNet_V3_Large_Weights.IMAGENET1K_V1`, và meta của trọng số trỏ tới một công thức huấn luyện (`references/segmentation`, chưa đọc: không có trong gói đã cài). Vì vậy backbone nhiều khả năng đã được huấn luyện trước trên ImageNet rồi mới huấn luyện trên COCO: **cần tra**. Mục "Pre-trained Model License" trong METADATA của gói nói trọng số có thể mang điều khoản riêng theo dữ liệu huấn luyện, người dùng tự kiểm. Với tệp này gói không nêu điều khoản cụ thể nào. Điều khoản COCO (ảnh và nhãn) và điều khoản ImageNet: **cần tra**, chưa đọc văn bản gốc | 24/09/2026 |
| **RoadObstacle21** (đang dùng để chấm ngoài miền: [HUAN_LUYEN.md](../../HUAN_LUYEN.md) mục 8, 10, 16) | chưa xác minh | Gói tải `datasets/training/road_obstacle/dataset_ObstacleTrack` chỉ có `image-sources.txt` ghi nguồn theo cảnh (BUW, EPFL), không kèm văn bản giấy phép. Điều khoản trên trang SegmentMeIfYouCan chưa đọc. | 24/09/2026 |
| **RoadAnomaly21** (chưa dùng trong kết quả nào lúc kiểm; *cập nhật 25/09/2026:* từ muộn tối 24/09 đã chấm 10 ảnh `validation*` có nhãn, kết quả ở [HUAN_LUYEN.md](../../HUAN_LUYEN.md) mục 8, mã ở commit `77eb51f`) | Giấy phép theo từng ảnh | `datasets/training/road_anomaly/dataset_AnomalyTrack/LICENSE.txt` ghi tác giả, giấy phép và nguồn từng ảnh: CC BY 2.0–4.0, CC BY-SA 1.0–4.0, CC0, public domain, giấy phép Pixabay/Pexels/Unsplash; riêng `toy_car0000.jpg` ghi "subject to copyright". Tệp không nói gì về nhãn/mask. | 24/09/2026 |

## WoodScape trong vòng điều khiển: quyết định 25/09/2026

Tài liệu này ghi lại quyết định và cơ sở của nó, không phải ý kiến pháp lý. Điều khoản WoodScape theo luật Pháp, tranh
chấp thuộc tòa án Paris (hai đoạn cuối LICENSE.pdf); dự án không đánh giá được cách đọc nào đứng vững theo luật đó.

### Quyết định

- **Ngày 25/09/2026 người làm khóa luận quyết định dùng mô hình phân đoạn huấn luyện trên WoodScape trong vòng điều
  khiển của xe mô hình 1/12.** Luồng dự kiến: xác suất AI của bốn camera fisheye → BEV (`perception/bev.py`) → lớp
  camera (`CameraSemanticLayer`, `fusion/layers.py`) → hợp nhất (`fusion/fuse.py`) → `ObstacleBridge`
  (`fusion/bridge.py`) → phiên đỗ xe và planner. AI camera là một nguồn vật cản bên cạnh LiDAR. Lý do người làm khóa
  luận nêu: điều khoản cho phép dùng phi thương mại, và đồ án không thương mại (cách đọc A dưới).
- Quyết định này thay hướng 1 ở mục "Vấn đề cần xử lý trước khi nộp" (không nối mô hình WoodScape vào vòng điều khiển).
  Hướng 1 và 2 chuyển thành phương án dự phòng (mục "Khóa luận nên viết gì" dưới). Quyết định 22/09 (coi xe 1/12 trên
  sa bàn là "personal experimentation" và "academic research") vẫn giữ; ngày 25/09 thêm cơ sở từ cấu trúc câu điều
  khoản, và chuyển từ "được dùng" sang nối thật vào vòng điều khiển. Việc cần quyết định "Hướng giấy phép WoodScape" ở
  [TONG_HOP_DU_AN.md](../../TONG_HOP_DU_AN.md) mục 5.1 nay đã quyết ở vế nối AI vào costmap/planner; vế nháp AI khi gán
  nhãn thì chưa (gạch "Phạm vi" dưới). Các tài liệu còn ghi "chờ quyết định giấy phép" liệt kê ở bảng "Chỗ ghi quyết
  định giấy phép WoodScape là việc còn chờ" dưới.
- Hiện trạng mã lúc ghi (kiểm 25/09/2026 bằng `git grep "CameraSemanticLayer(" 89cd58f`): lớp camera mới được khởi tạo
  trong test (`tests/test_bev.py`, `tests/test_nearfield_tof.py`), chưa có mã nào đưa AI camera vào phiên đỗ xe. Việc
  nối làm ở nhóm việc khác trong cùng đợt 25/09; trạng thái sau đợt đó xem [TONG_HOP_DU_AN.md](../../TONG_HOP_DU_AN.md).
  Hai giới hạn kỹ thuật không đổi: BEV chưa chạy với hiệu chuẩn thật (chưa có tệp nội tham, ngoại tham, ROI cho camera
  dự án, [BEV.md](BEV.md) mục 6), và AI chưa được chấm trên ảnh sa bàn có nhãn.
- **Phạm vi:** quyết định chỉ nói về điều khoản WoodScape.
  - Checkpoint có dùng ảnh AVM-SS vướng thêm chuyện khác: AVM-SS không có giấy phép nào (bảng trên). Kiểm thô 25/09/2026
    (chuỗi "avm" trong `run_manifest.json`): 8 trong 12 lượt `runs/ai_*` có AVM-SS (`ai_avm_only`, `ai_ws_avm`,
    `ai_ws_avm_acdc`, và năm lượt `ai_ws_avm_*` seed/weighted); 4 lượt chỉ WoodScape (`ai_woodscape_rtx4000_v1`, hai
    lượt `_seed2026092x`, `_weighted`). Quyết định này **không** phủ các checkpoint có AVM-SS. ĐỀ XUẤT – CHỜ CHỐT: vòng
    điều khiển chỉ dùng lượt nền `runs/ai_woodscape_rtx4000_v1/best.pt` (đứng đầu danh sách của `list_checkpoints`
    trong `perception/live.py`, mặc định của `rig/bench.py`) hoặc một lượt chỉ WoodScape. Bàn thử
    (`ui/rig_app.py`) hiện liệt kê mọi `runs/*/best.pt`, kể cả các lượt có AVM-SS.
  - Trọng số khởi tạo torchvision (COCO, có thể cả ImageNet) vẫn **cần tra** như dòng bảng trên. Quyết định này không
    thay đổi điều đó.
  - Nhãn nháp khi gán nhãn sa bàn: quyết định 25/09/2026 chỉ nói về dùng mô hình trong vòng điều khiển, **chưa** quyết
    vế thứ hai của việc cần quyết định ở [TONG_HOP_DU_AN.md](../../TONG_HOP_DU_AN.md) mục 5.1 ("có dùng nháp AI khi gán
    nhãn hay không"). Công cụ gán nhãn mặc định lấy nháp từ đầu ra AI (tham số `draft=True` mặc định của
    `import_snapshots` trong `perception/labels.py`, tắt bằng `--no-draft`; [GAN_NHAN_SA_BAN.md](GAN_NHAN_SA_BAN.md) mục
    2), mô hình nháp huấn luyện trên WoodScape (GAN_NHAN_SA_BAN.md mục 4). Nhãn sửa từ nháp đó có chịu điều khoản Valeo
    không thì vẫn **chưa đánh giá** (ghi chú 24/09 ở hướng 2, mục "Vấn đề cần xử lý trước khi nộp"). Đề xuất: xem
    "Phương án dự phòng", hướng 2.

### Toàn văn câu điều khoản và hai cách đọc

Nguồn: [datasets/woodscape_metadata/LICENSE.pdf](../datasets/woodscape_metadata/LICENSE.pdf), SHA-256
`64843e0d…a85f4` như mục cuối. Đọc lại 25/09/2026 bằng một script tạm mới (giải nén luồng Flate, giải mã cả phông
WinAnsi lẫn phông Identity-H qua bảng ToUnicode; không lưu trong repo): toàn văn hai trang ra đủ, không còn ký tự nào
không giải mã được. Câu dưới đây khớp văn bản giải mã từ tệp đó (so bỏ khoảng trắng; kiểm lại lúc sửa sau rà soát bằng
một script tạm khác, cùng kết quả). Bản ghi 22/09 (ô WoodScape ở bảng trên) chỉ chép hai đoạn của câu và lược phần định
nghĩa thương mại bằng "..."; hai đoạn đó khớp nguyên văn câu dưới, còn phần "i.e. primarily intended for or directed
towards commercial advantage or monetary compensation," đến 25/09/2026 mới được chép đủ (ở commit `89cd58f` không tài
liệu nào có chuỗi "primarily intended"):

> "You shall not use the Dataset for commercial purposes i.e. primarily intended for or directed towards commercial
> advantage or monetary compensation, and notably not use or deploy the Dataset, any models trained on or refined using
> the Dataset including pre-training or augmentation, in operation of a vehicle or to assist in the operation of
> vehicle."

Ngay trước câu này là câu liệt kê bốn mục đích được phép (trích ở bảng trên): (i) nghiên cứu, gồm dự án nội bộ chưa
công bố và nghiên cứu, công bố công khai mà người đọc không phải trả phí; (ii) giảng dạy; (iii) benchmark cho công bố
học thuật hoặc nghiên cứu ứng dụng; (iv) thử nghiệm cá nhân. Câu ngay sau là yêu cầu ghi công (mục "Ghi công" dưới).

Cấu trúc câu: một chủ ngữ "You shall not", hai vế nối bằng "and notably". Vế 1 cấm dùng bộ dữ liệu cho mục đích thương
mại và định nghĩa thương mại. Vế 2 nói về dùng hoặc triển khai bộ dữ liệu và mọi mô hình huấn luyện trên nó trong vận
hành phương tiện.

- **Cách đọc A (người làm khóa luận):** "notably" ("nhất là", "đặc biệt là") nêu một trường hợp tiêu biểu của việc
  dùng thương mại vừa định nghĩa. Vậy câu cấm đưa mô hình lên phương tiện *như một dạng khai thác thương mại*. Dùng phi
  thương mại trên xe mô hình của khóa luận không bị câu này cấm, miễn là việc dùng nằm trong bốn mục đích (i)–(iv). Chỗ
  dựa: vế 2 nằm trong cùng câu với vế thương mại, nối bằng "and notably", chứ không phải một câu "You shall not" riêng;
  "notably" thường dẫn ra một phần của điều vừa nói. **Cách đọc A bảo vệ được từ cấu trúc câu.**
- **Cách đọc B:** vế 2 là một lệnh cấm riêng, áp dụng dù có thương mại hay không ("and [you shall] notably not use or
  deploy …"). Chỗ dựa: vế 2 có chữ "not" và động từ riêng ("use or deploy"); vế 2 không lặp lại điều kiện "for
  commercial purposes"; và vế 2 mở rộng đối tượng ra "any models trained on or refined using the Dataset", vượt khỏi
  chủ đề của vế 1 là "use the Dataset". Suy đoán, không có bằng chứng: Valeo là nhà cung cấp cho ngành ô tô, nên có thể
  muốn chặn mọi việc đưa mô hình lên phương tiện. **Cách đọc B không loại trừ được**, và người đọc thận trọng (ví dụ hội
  đồng chấm) có thể nghiêng về B.
- Văn bản không tự phân định hai cách đọc. **Valeo chưa xác nhận cách nào.** Câu trả lời ở issue #14 (mục "Kiểm trên
  web" dưới) nói giới hạn là phi thương mại, nhưng câu hỏi ở đó là MIT hay điều khoản riêng, không hỏi về phương tiện,
  nên không dùng làm xác nhận cho cách đọc A được.
- Câu hỏi phụ, đọc theo cách nào cũng còn: xe mô hình 1/12 (khoảng 0,31 m) chạy trên sa bàn trong phòng có phải
  "vehicle" theo nghĩa điều khoản không. Văn bản không định nghĩa "vehicle". Ghi chú ngày 22/09 đã nêu điểm này.

**Tự sửa của dự án (25/09/2026):** từ 22/09, nhiều tài liệu trong dự án tóm tắt câu trên thành một lệnh cấm thẳng
("WoodScape **cấm** dùng mô hình huấn luyện trên nó để vận hành hoặc hỗ trợ vận hành phương tiện"), tức là mặc nhiên
theo cách đọc B. Cách tóm tắt đó **mạnh hơn văn bản**: văn bản không nói vế phương tiện có độc lập với vế thương mại hay
không. Các chỗ đang viết như vậy (grep ngày 25/09/2026 ở commit `89cd58f`, bổ sung sau rà soát bằng
`git grep -n -i -E "cấm.{0,80}(phương tiện|vận hành)" 89cd58f`; tệp này không sửa chúng):

| Tệp (đường dẫn từ gốc repo) | Chỗ |
|---|---|
| `autopark/docs/GIAY_PHEP_DU_LIEU.md` (tệp này) | câu in đậm đầu mục "Vấn đề cần xử lý trước khi nộp", giữ làm lịch sử, có ghi chú 25/09 ngay dưới |
| `README.md` | dòng 15, bảng tài liệu, ô mô tả GIAY_PHEP_DU_LIEU.md |
| `TONG_HOP_DU_AN.md` | dòng 236, đoạn "Giấy phép" |
| `BAO_CAO_GIAI_DOAN_0.md` | dòng 196, ghi chú 24/09 |
| `KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md` | dòng 746, bảng trạng thái, dòng giai đoạn 0 |
| `autopark/datasets/DANH_MUC_DATASET.md` | dòng 5, ghi chú 24/09 đầu tệp |
| `autopark/docs/DAN_Y_KHOA_LUAN.md` | dòng 150, điểm 4 ("Giấy phép WoodScape cấm …"); dòng 1467, bảng dữ liệu, hàng D1 WoodScape, ô giấy phép ("cấm dùng mô hình để vận hành phương tiện (GIAY_PHEP_DU_LIEU)") |
| `autopark/docs/KICH_BAN_NGHIEM_THU.md` | dòng 4, khối ghi công đầu tệp |
| `autopark/autopark/perception/bev.py` | dòng 1430–1431, chuỗi `license` ghi vào tệp ra của lệnh BEV trên ảnh WoodScape |

Grep cũng thấy `autopark/docs/evidence/ke_hoach/kiem_toan_ke_hoach_20260924.json` dòng 166 và 1972 viết "giấy phép
WoodScape cấm dùng mô hình … để vận hành phương tiện". Đó là bản chụp bằng chứng có ngày 24/09/2026, **cố ý giữ nguyên**
như lịch sử, không sửa và không đưa vào danh sách cần viết lại. Các kết quả grep còn lại không nói về WoodScape
(`perception/prepare_extra.py` dòng 264 là ghi chú giấy phép ACDC; hai dòng của chính tệp này ở `89cd58f` là hàng ACDC
của bảng đầu và gạch về trọng số torchvision).

Cách viết đề xuất thay cho các chỗ đó (ĐỀ XUẤT – CHỜ CHỐT): "Điều khoản WoodScape chỉ cho dùng phi thương mại (nghiên
cứu, giảng dạy, benchmark, thử nghiệm cá nhân) và có câu không cho dùng mô hình huấn luyện trên nó trong vận hành phương
tiện. Dự án đọc câu đó là ví dụ của việc dùng thương mại (quyết định 25/09/2026); Valeo chưa xác nhận." Riêng ô giấy phép
hàng D1 (`DAN_Y_KHOA_LUAN.md` dòng 1467), đề xuất thay đoạn cuối ô bằng: "…bắt buộc ghi công; điều khoản chỉ cho dùng phi
thương mại và có câu không cho dùng mô hình trong vận hành phương tiện; dự án đọc câu đó là ví dụ của dùng thương mại
(quyết định 25/09/2026), Valeo chưa xác nhận (GIAY_PHEP_DU_LIEU)".

**Chỗ ghi quyết định giấy phép WoodScape là việc còn chờ** (git grep ngày 25/09/2026 ở `89cd58f`, mẫu
`quyết định (về )?giấy phép|giấy phép WoodScape|hướng giấy phép` rồi đọc từng dòng; tệp này không sửa chúng). Phần giấy
phép nay đã có quyết định 25/09/2026: dùng theo cách đọc A, Valeo chưa xác nhận. Các điều kiện khác của nhóm AI vẫn
còn: hiệu chuẩn nội tham, ngoại tham, ROI thật ([BEV.md](BEV.md) mục 8) và tập chấm sa bàn có nhãn. ĐỀ XUẤT: hướng 1
(chạy chỉ bằng LiDAR) giữ làm phương án dự phòng, nên nghiệm thu cũng nên có kết quả khi tắt lớp AI.

| Tệp (đường dẫn từ gốc repo) | Dòng ở `89cd58f` | Loại | Cách sửa đề xuất (ĐỀ XUẤT – CHỜ CHỐT) |
|---|---|---|---|
| `TONG_HOP_DU_AN.md` | 49, 242, 598 | hiện trạng "chờ quyết định giấy phép" / "chốt hướng giấy phép trước khi nối AI" | đổi thành "giấy phép: đã quyết định 25/09/2026 (GIAY_PHEP_DU_LIEU.md); còn chờ hiệu chuẩn thật, chấm sa bàn" |
| `TONG_HOP_DU_AN.md` | 676; 685 (hàng mục 5.1) | quyết định còn mở | vế nối AI vào costmap/planner: đã quyết định 25/09/2026, dẫn tới mục "WoodScape trong vòng điều khiển"; giữ ghi chú Valeo chưa xác nhận. Vế nháp AI khi gán nhãn: vẫn chờ chốt (gạch "Phạm vi" ở mục "Quyết định") |
| `KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md` | 756 (dòng giai đoạn 10, ô việc còn mở: "giấy phép WoodScape (xem dòng giai đoạn 0)") | việc còn mở | ghi đã quyết định 25/09/2026, Valeo chưa xác nhận |
| `autopark/docs/KICH_BAN_NGHIEM_THU.md` | 14–15 | hiện trạng "chờ quyết định giấy phép WoodScape" | như hàng TONG_HOP 49 |
| `autopark/docs/KICH_BAN_NGHIEM_THU.md` | 81 (ĐK-AI) | điều kiện | ghi phần giấy phép đạt từ 25/09/2026 (cách đọc A); giữ hai điều kiện còn lại |
| `autopark/docs/KICH_BAN_NGHIEM_THU.md` | 599–600 | câu điều kiện "nếu hướng giấy phép … không cho nối AI" | chuyển thành phương án dự phòng (hướng 1) |
| `autopark/docs/KICH_BAN_NGHIEM_THU.md` | 978 | quyết định còn mở | đã quyết định 25/09/2026 |
| `autopark/docs/NGUONG_NGHIEM_THU_DE_XUAT.md` | 16 | hiện trạng | như hàng TONG_HOP 49 |
| `autopark/docs/NGUONG_NGHIEM_THU_DE_XUAT.md` | 177–178, 247 | điều kiện áp dụng mục 8 / N-A1…N-A4 | mục 8 nay áp dụng về phía giấy phép; còn điều kiện tập chấm sa bàn |
| `autopark/docs/NGUONG_NGHIEM_THU_DE_XUAT.md` | 277 | quyết định còn mở | đã quyết định 25/09/2026 |
| `autopark/docs/BEV.md` | 137, 610 | hiện trạng / việc còn lại | bỏ "chờ quyết định giấy phép"; giữ phần chờ hiệu chuẩn thật |
| `autopark/docs/NGOAI_THAM_VA_ROI.md` | 253 | hiện trạng | như hàng BEV.md 137 |
| `autopark/docs/DAN_Y_KHOA_LUAN.md` | 152 ("Hướng xử lý cho khóa luận chưa chốt"), 614, 1319, 1568 | hiện trạng / việc còn mở | đã chốt 25/09/2026 (cách đọc A, Valeo chưa xác nhận); 1568 còn giữ việc hỏi GVHD về in ảnh WoodScape |
| `autopark/autopark/perception/bev.py` | 43 (docstring), 1155 (chuỗi `caveats`) | mã: "giấy phép WoodScape chưa chốt cho việc nối AI" | cây làm việc lúc sửa (25/09/2026) đã đổi cả hai chỗ sang hằng `WOODSCAPE_LICENCE_NOTE` (nhóm việc AI camera); chỉ cần kiểm lại khi đồng bộ |
| `autopark/docs/evidence/ke_hoach/kiem_toan_ke_hoach_20260924.json` | 95, 167, 299, 1973 ("Rủi ro giấy phép WoodScape vẫn mở", "cần người dùng quyết định về giấy phép") | bằng chứng lịch sử 24/09 | không sửa |

Số dòng lấy ở `89cd58f`; tệp được sửa thì số dòng có thể lệch. Mẫu grep trên còn ra ba nhóm dòng không đưa vào bảng này:
các dòng đã có ở bảng chữ "cấm" (`BAO_CAO_GIAI_DOAN_0.md` 196, `KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md` 746,
`DAN_Y_KHOA_LUAN.md` 150); `kiem_toan_ke_hoach_20260924.json` 166 và 1972 (bằng chứng 24/09, đã ghi ở trên); và
`autopark/datasets/DANH_MUC_DATASET.md` dòng 111 ("Giấy phép WoodScape hạn chế dùng mô hình huấn luyện trên nó để vận
hành phương tiện", kèm link tới tệp này). Chữ "hạn chế" không mạnh hơn văn bản và không ghi việc còn chờ, nên không cần
sửa.

### Kiểm trên web ngày 25/09/2026

Kiểm ba lần trong ngày: một lần trước khi giao việc sửa tệp này, một lần khi viết tệp này, một lần khi sửa sau rà soát
(chỉ đọc lại API bình luận issue #14, README trực tuyến, trang repo và API `repos/valeoai/WoodScape`, trang issue #14).
Hai lần sau dùng công cụ đọc trang web, công cụ này trả nội dung đã qua xử lý chứ không phải bản chụp nguyên văn. Vì
vậy bình luận chép dưới đây lấy từ API JSON của GitHub (qua cùng công cụ, yêu cầu trả nguyên văn chuỗi JSON), và câu
giữa của nó khớp với câu ghi ở lần kiểm đầu. Không tải tệp nào; không mở lại LICENSE.pdf trên Google Drive.

| Địa chỉ | Kết quả 25/09/2026 |
|---|---|
| `https://woodscape.valeo.ai` (địa chỉ ghi trong LICENSE.pdf) | Trả 301, chuyển tới `https://woodscape.valeo.com/` |
| `https://woodscape.valeo.com` (địa chỉ ghi ở dòng đầu README, bản trực tuyến và bản sao trong repo) | Trang có tiêu đề "Shares4U" trên tên miền của Valeo, không có nội dung nào về WoodScape, điều khoản hay liên hệ |
| `https://woodscape.valeo.com/dataset` (trường website ở khung "About" của repo GitHub valeoai/WoodScape, API `repos/valeoai/WoodScape` trường `homepage`; **không** có trong README, LICENSE.pdf hay chỗ nào trong repo dự án; kiểm lại khi sửa sau rà soát 25/09/2026) | Như hàng trên: trang "Shares4U", không có nội dung về WoodScape. Không dùng địa chỉ này trong khối ghi công; nếu trích thì ghi nguồn là khung About của repo GitHub, không phải README |
| LICENSE.pdf bản trong repo (đọc toàn văn như trên) | Không có email, không có địa chỉ web nào ngoài `woodscape.valeo.ai`, không có liên kết URI |
| [github.com/valeoai/WoodScape](https://github.com/valeoai/WoodScape), README (bản trực tuyến và bản sao `datasets/woodscape_metadata/README.md`) | Không có email hay hướng dẫn liên hệ. Mục "License for the data" trỏ tới cùng tệp Drive `12IrLnGfng6s-NogJLIvUZsCxF1NDA-FA` như bảng trên. Dòng đầu vẫn ghi `https://woodscape.valeo.com` |
| [valeoai.github.io](https://valeoai.github.io) | Không có email hay form liên hệ, không nhắc WoodScape |
| [Issue #14](https://github.com/valeoai/WoodScape/issues/14) | Xem dưới |

**Issue #14** (API `repos/valeoai/WoodScape/issues/14` và `/comments`): tiêu đề "What is the license for using the
data? Readme says MIT but PDF file in Google Drive is very different", người mở `plaut`, 15/03/2021, đã đóng cùng ngày,
một bình luận. Bình luận của tài khoản `G453`, GitHub gắn nhãn `COLLABORATOR` của repo (nghĩa là có quyền trên repo;
chưa xác minh người này là ai hay có thẩm quyền trả lời thay Valeo về pháp lý), 15/03/2021 (`created_at`
`2021-03-15T18:26:56Z`). Toàn bộ trường `body` của bình luận, chép đúng chuỗi JSON mà API trả ngày 25/09/2026 (qua công
cụ đọc web như trên), giữ nguyên ký tự thoát `\r\n` và `\"`, hai dấu cách sau "use." và dấu cách cuối chuỗi:

```
"Hi Plaut, \r\n\r\nDataset has a proprietary license and strictly for non-commercial use.  Scripts are \" PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND\". "
```

Tức là ba phần: lời chào "Hi Plaut,", câu về dữ liệu, và câu về mã (scripts) được cung cấp "AS IS". Công cụ đọc web có
thể chuẩn hóa khoảng trắng, nên số dấu cách không phải bằng chứng chắc; phần chữ khớp với chuỗi mà lần rà soát cùng
ngày ghi lại. Câu thứ hai nói về mã, khớp với ý ở mục "Toàn văn câu điều khoản và hai cách đọc" trên: trao đổi này tách
mã (README ghi MIT) khỏi dữ liệu (điều khoản riêng), không nói gì về phương tiện.

Tìm trong issue của repo bằng API tìm kiếm GitHub (`license OR licence OR commercial OR vehicle`): 16 kết quả, theo tiêu
đề chỉ #14 hỏi về giấy phép; không issue nào hỏi riêng câu về phương tiện.

Hệ quả: trả lời câu "cần tra" ở mục "Kiểm tối 24/09/2026" dưới: **không địa chỉ nào trong hai địa chỉ cũ còn là trang
bộ dữ liệu**. Bản điều khoản "đang có hiệu lực" mà LICENSE.pdf bảo người dùng tự xem lại không có trang nào để xem ngoài
tệp Drive mà README trỏ tới (chưa đối chiếu với bản trong repo, vì phải tải tệp).

### Nếu muốn hỏi Valeo

Người làm khóa luận quyết định không chờ trả lời. Nếu muốn có xác nhận thì có hai kênh, cả hai do người làm khóa luận tự
gửi:

1. **Mở issue công khai** trên [github.com/valeoai/WoodScape/issues](https://github.com/valeoai/WoodScape/issues) (trang
   mở được ngày 25/09/2026, issue đang bật). Cần tài khoản GitHub, và nội dung ai cũng đọc được. Issue #14 năm 2021 được
   trả lời sau khoảng 11 phút (mở 18:16, trả lời 18:26 UTC). Không có số liệu nào về tốc độ trả lời hiện nay.
2. **Tác giả bài báo WoodScape** (Yogamani và cs., ICCV 2019, danh sách tác giả ở README). Email trong bài báo **chưa
   kiểm**, và chưa kiểm tác giả nào còn làm ở Valeo. Dự án không thu thập email của ai.

Nháp nội dung (tiếng Anh, ĐỀ XUẤT; người làm khóa luận sửa và tự gửi):

> Title: Licence question: non-commercial thesis using a WoodScape-trained model on a 1/12-scale indoor model car
>
> Hello. For a non-commercial university thesis I trained a semantic segmentation model on WoodScape. I would like to
> use its output as one obstacle source, together with a 2D LiDAR, on a 1/12-scale model car that parks itself on an
> indoor table-top mock-up (no public roads, no payment, no commercial use). The terms say "You shall not use the
> Dataset for commercial purposes […], and notably not use or deploy […] any models trained on […] the Dataset […] in
> operation of a vehicle". Is the vehicle part an example of commercial use, or a separate prohibition that also covers
> a non-commercial research model car like this one? Also, woodscape.valeo.com and woodscape.valeo.ai now lead to an
> unrelated page: which link should be used for the attribution notice the terms require? Thank you.

Có trả lời thì chép nguyên văn vào tệp này, kèm ngày và người trả lời. Nếu trả lời theo cách đọc B thì chuyển sang
phương án dự phòng (mục "Khóa luận nên viết gì").

### Ghi công: link tới trang bộ dữ liệu

Điều khoản buộc mọi tài liệu và website công khai nhắc tới nghiên cứu dùng bộ dữ liệu phải hiển thị rõ rằng nghiên cứu
dùng Valeo WoodScape Dataset, **kèm link tới trang web của bộ dữ liệu**. Cả hai địa chỉ cũ đều dẫn tới trang không liên
quan (kiểm 25/09/2026). ĐỀ XUẤT – CHỜ CHỐT: link chính là <https://github.com/valeoai/WoodScape>, repo của tổ chức
valeoai trên GitHub, nơi README tự giới thiệu là repo chứa công cụ và thông tin về bộ dữ liệu và trỏ tới điều khoản; ghi
địa chỉ cũ dạng chữ, không làm link, để lưu vết. Valeo chưa xác nhận đây là "Dataset website". Mẫu khối ghi công:

> **Ghi công bắt buộc theo giấy phép dữ liệu:** nghiên cứu nhận thức trong dự án này được thực hiện với **Valeo
> WoodScape Dataset** (<https://github.com/valeoai/WoodScape>; địa chỉ cũ `woodscape.valeo.com` / `woodscape.valeo.ai`,
> kiểm 25/09/2026 dẫn tới một trang không có nội dung WoodScape). Giới hạn sử dụng: GIAY_PHEP_DU_LIEU.md.

Tệp cần đổi dòng ghi công (tệp này không sửa; bước đồng bộ tổng hợp và nhóm việc AI camera sẽ sửa). Hiện tất cả dùng
`https://woodscape.valeo.com`:

| Tệp (đường dẫn từ gốc repo) | Chỗ | Ghi chú |
|---|---|---|
| `README.md` | dòng 5 | đã có link repo, bỏ hoặc đổi link `.com` |
| `autopark/README.md` | dòng 3 | như trên |
| `HUAN_LUYEN.md` | dòng 3 | như trên |
| `TONG_HOP_DU_AN.md` | dòng 3 | như trên |
| `BAO_CAO_GIAI_DOAN_0.md` | dòng 196, giữa ghi chú 24/09 | chỉ có link `.com`; cùng chỗ có chữ "cấm" (bảng trên) |
| `autopark/docs/BEV.md` | dòng 3–4 | chỉ có link `.com` |
| `autopark/docs/DAN_Y_KHOA_LUAN.md` | dòng 3–6; và dòng 1438–1441 ("link đưa vào khóa luận: **cần tra**") | câu "cần tra" nay trả lời được bằng mục "Kiểm trên web" |
| `autopark/docs/KICH_BAN_NGHIEM_THU.md` | dòng 3–5 | chỉ có link `.com`; cùng khối có chữ "cấm" |
| `autopark/docs/NGUONG_NGHIEM_THU_DE_XUAT.md` | dòng 3–4 | chỉ có link `.com` |
| `autopark/autopark/perception/bev.py` | dòng 1430–1431, chuỗi `license` | đề xuất: `"Valeo WoodScape Dataset (https://github.com/valeoai/WoodScape): chỉ dùng phi thương mại; câu về vận hành phương tiện và cách hiểu của dự án (25/09/2026, Valeo chưa xác nhận): docs/GIAY_PHEP_DU_LIEU.md"` |

Số dòng lấy ở commit `89cd58f` (25/09/2026), có thể lệch khi tệp được sửa. *Lúc viết xong mục này (25/09/2026), cây
làm việc đã có thay đổi chưa commit của nhóm việc AI camera ở `perception/bev.py`: chuỗi cũ được thay bằng hai hằng
`WOODSCAPE_ATTRIBUTION` (ghi cả `woodscape.valeo.ai`, `woodscape.valeo.com` và repo GitHub, địa chỉ `.ai` đứng đầu) và
`WOODSCAPE_LICENCE_NOTE` (nêu cả hai cách đọc). Nội dung khớp mục này, trừ thứ tự link: đề xuất ở đây là repo GitHub
đứng đầu, địa chỉ cũ chỉ để lưu vết. Cần thống nhất khi đồng bộ.* Các tệp `GIAI_DOAN_1_CHUAN_BI.md`,
`GIAI_DOAN_2_BAN_THU.md`, `HIEU_CHUAN_CAMERA.md`, `GAN_NHAN_SA_BAN.md` vẫn chưa có dòng ghi công riêng (ghi chú 24/09
dưới); tài liệu mới về AI camera trong vòng điều khiển thì nên có ngay từ đầu.

### Khóa luận nên viết gì (ĐỀ XUẤT – CHỜ CHỐT)

Nên báo giảng viên hướng dẫn về quyết định này và về hai cách đọc trước khi viết. Đoạn đề xuất cho mục dữ liệu và giấy
phép của khóa luận:

> Mô hình phân đoạn ảnh được huấn luyện trên Valeo WoodScape Dataset (https://github.com/valeoai/WoodScape). Điều khoản
> sử dụng bộ dữ liệu chỉ cho phép dùng phi thương mại: nghiên cứu, giảng dạy, benchmark cho công bố học thuật, thử
> nghiệm cá nhân. Cùng câu cấm dùng thương mại, điều khoản có vế không cho dùng bộ dữ liệu hay mô hình huấn luyện trên
> nó trong vận hành phương tiện. Khóa luận dùng mô hình này làm một nguồn vật cản cho xe mô hình tỉ lệ 1/12 chạy trên sa
> bàn trong phòng, trong khuôn khổ nghiên cứu và thử nghiệm cá nhân: không thương mại, không thu phí, không chạy trên
> đường công cộng. Khóa luận hiểu vế về phương tiện là ví dụ của việc dùng thương mại bị cấm ("and notably"). Cách đọc
> này chưa được Valeo xác nhận, và vế đó cũng có thể được hiểu là một lệnh cấm riêng. Mô hình không dùng cho phương tiện
> thật. Nếu phát triển tiếp theo hướng thương mại hoặc trên phương tiện thật thì phải huấn luyện lại bằng dữ liệu khác.

Kèm theo: dòng ghi công như mục trên ở đầu khóa luận, và ở mọi slide, poster, video, trang web công khai có nhắc tới
phần nhận thức.

**Phương án dự phòng** nếu cách đọc bị phản bác (Valeo trả lời theo cách đọc B, giảng viên hướng dẫn hoặc hội đồng yêu
cầu, hoặc Valeo đổi điều khoản):

- **Hướng 1** (mục dưới): tắt AI camera trong vòng điều khiển, xe chạy bằng LiDAR; phần WoodScape chỉ còn là nghiên cứu
  nhận thức đo offline. ĐỀ XUẤT: để hướng này dùng được ngay, phần mềm nên giữ cách chạy phiên đỗ xe không có lớp AI
  camera, và các kịch bản nghiệm thu nên có kết quả cả khi tắt lớp đó.
- **Hướng 2** (mục dưới): huấn luyện lại mô hình triển khai bằng ảnh sa bàn tự chụp (nhập bằng `--no-draft`) và/hoặc
  ACDC, không khởi tạo từ checkpoint WoodScape. Trọng số khởi tạo torchvision vẫn phải tra như bảng trên.
  ĐỀ XUẤT – CHỜ CHỐT: để hướng này dùng được ngay, bộ ảnh sa bàn dùng huấn luyện nên nhập bằng `--no-draft` ngay từ đầu.
  Tập chấm vốn đã phải tô tay từ đầu ([GAN_NHAN_SA_BAN.md](GAN_NHAN_SA_BAN.md) mục 4,
  [TONG_HOP_DU_AN.md](../../TONG_HOP_DU_AN.md) mục 4.7). Nếu vẫn dùng nháp cho đỡ công thì ghi rõ trong dự án gán nhãn
  rằng bộ nhãn đó sẽ phải bỏ và gán lại khi chuyển sang hướng 2. Manifest cache có ghi `draft_origins`
  (`perception/labels.py`), nên tách được ảnh nào có nháp. Tới 25/09/2026 chưa gán nhãn ảnh thật nào (TONG_HOP_DU_AN.md
  mục 4.7; trong `datasets/` không có dự án gán nhãn sa bàn nào), nên chưa có nhãn nào phải bỏ.

## Vấn đề cần xử lý trước khi nộp

**WoodScape cấm dùng mô hình huấn luyện trên nó để vận hành hoặc hỗ trợ vận hành phương tiện.** Mô hình
L-RASPP hiện tại huấn luyện trên WoodScape và theo thiết kế đầu ra của nó sẽ đi vào costmap cho planner.
*Cập nhật 24/09/2026:* tới nay chưa nối: `CameraSemanticLayer` trong `fusion/layers.py` chưa được nơi nào khởi tạo,
`perception/costmap.py` mới chạy trên ảnh WoodScape lưu sẵn, còn trên bàn thử giai đoạn 2 lớp tô AI chỉ để quan sát. *Cập nhật 25/09/2026:* vẫn đúng ở `54cb3e2`. BEV nhiều camera
(`perception/bev.py`, commit `1d2b857`, [BEV.md](BEV.md)) là đường đưa xác suất AI xuống costmap, nhưng cũng chưa được
nối vào hợp nhất hay planner, và chưa chạy với hiệu chuẩn thật trên camera dự án ([BEV.md](BEV.md) mục 6).
*Ghi chú 25/09/2026:* mục này viết 22/09 và cập nhật 24/09, giữ nguyên làm lịch sử. Câu in đậm đầu mục là cách tóm tắt
mạnh hơn văn bản: văn bản không nói rõ vế phương tiện có độc lập với vế thương mại không (mục "WoodScape trong vòng điều
khiển" ở trên). Kế hoạch hiện tại là nối mô hình WoodScape vào vòng điều khiển (quyết định 25/09/2026); câu "tới nay chưa
nối" vẫn đúng ở `89cd58f`.
Ba hướng xử lý, chọn một và ghi rõ trong khóa luận:

1. **Tách vai trò.** Giữ phần WoodScape thuần nghiên cứu nhận thức (đo offline, báo cáo số liệu, đúng mục
   "academic or applied research publication"), và KHÔNG nối mô hình đó vào vòng điều khiển xe. Xe chạy bằng
   LiDAR và, khi có camera, bằng mô hình huấn luyện trên dữ liệu tự thu.
   *(25/09/2026: không còn là kế hoạch; nay là phương án dự phòng, xem "Khóa luận nên viết gì" ở trên.)*
2. **Thay dữ liệu cho mô hình triển khai.** Huấn luyện lại bằng ảnh tự chụp trên sa bàn (ảnh không vướng giấy
   phép; nhãn xem ghi chú dưới) và/hoặc ACDC (không có điều khoản về phương tiện). Cách này đồng thời tốt hơn về kỹ
   thuật vì đúng miền.
   *Cập nhật 24/09/2026:* công cụ gán nhãn sa bàn ([GAN_NHAN_SA_BAN.md](GAN_NHAN_SA_BAN.md)) mặc định lấy nhãn nháp
   từ mô hình huấn luyện trên WoodScape. Chưa đánh giá nhãn đã sửa từ nháp đó có chịu điều khoản Valeo hay không
   (manifest cache ghi `draft_origins` và `licence_note`). Muốn chắc chắn đi đúng hướng này: nhập ảnh bằng `--no-draft`,
   khởi tạo từ trọng số pretrained chính thức của torchvision (như lượt nền), không khởi tạo từ checkpoint WoodScape
   và không ghép cache WoodScape (GAN_NHAN_SA_BAN.md mục 2 và mục 4).
3. **Hỏi Valeo.** Email xin xác nhận liệu xe mô hình 1/12 trên sa bàn trong phòng thí nghiệm có nằm trong phạm
   vi "operation of a vehicle" không. Chưa có trả lời thì không coi là được phép.
   *(25/09/2026: câu "chưa có trả lời thì không coi là được phép" không còn là quy tắc của dự án. Người làm khóa luận
   quyết định dùng theo cách đọc A mà không chờ trả lời. Không tìm thấy email liên hệ công khai nào; kênh hỏi còn lại
   xem "Nếu muốn hỏi Valeo" ở trên.)*

**Quyết định của người làm khóa luận (22/09/2026):** chọn cách hiểu rằng xe mô hình 1/12 chạy trên sa bàn trong
phòng, không ra đường công cộng, thuộc phạm vi "personal experimentation" và "academic research" mà điều khoản
cho phép, nên tiếp tục dùng mô hình huấn luyện trên WoodScape. Ghi nhận để minh bạch: văn bản Valeo viết
"operation of a vehicle" mà không kèm điều kiện đường công cộng, nên cách hiểu này chưa được Valeo xác nhận.
Nếu sau này sản phẩm được thương mại hóa hoặc đưa lên phương tiện thật thì phải huấn luyện lại bằng dữ liệu khác.
*(25/09/2026: quyết định này vẫn giữ và được mở rộng thành nối mô hình vào vòng điều khiển, với cơ sở thêm là cách đọc A
của câu điều khoản; xem mục "WoodScape trong vòng điều khiển" ở trên.)*

Ghi công bắt buộc đã được thêm vào đầu `HUAN_LUYEN.md` và `autopark/README.md` theo yêu cầu
*"conspicuously displayed in all public material and website referencing research conducted with the Dataset"*.

*Cập nhật 24/09/2026:* cùng khối ghi công đã được thêm vào đầu `README.md` gốc, trang đầu của repo trên GitHub (commit
356752e), và vào ghi chú 24/09 ở mục 9 của `BAO_CAO_GIAI_DOAN_0.md`. Một số tài liệu trong `autopark/docs/` nhắc tới
mô hình hoặc lượt huấn luyện WoodScape nhưng chưa có dòng ghi công riêng (ví dụ `GIAI_DOAN_1_CHUAN_BI.md`,
`GIAI_DOAN_2_BAN_THU.md`, `HIEU_CHUAN_CAMERA.md`, `GAN_NHAN_SA_BAN.md`). Chưa quyết định có cần thêm ghi công vào các
tài liệu này trước khi công bố khóa luận hay không.

*Cập nhật 25/09/2026:* link `woodscape.valeo.com` trong các khối ghi công nay dẫn tới trang không liên quan. Đề xuất link
thay và danh sách tệp cần đổi: mục "Ghi công: link tới trang bộ dữ liệu" ở trên.

## Kiểm tối 24/09/2026

Chỉ đọc tệp có sẵn trên máy bàn, không tải gì, không mở trang web nào.

### WoodScape: toàn văn trong repo và địa chỉ trang bộ dữ liệu

- Tệp: [datasets/woodscape_metadata/LICENSE.pdf](../datasets/woodscape_metadata/LICENSE.pdf), 372.396 byte, 2 trang, SHA-256
  `64843e0d8fec1b67057acfb43b022af2b27608e96e2288306810c8a3987a85f4`. Siêu dữ liệu PDF ghi tạo ngày 11/02/2021 bằng
  Microsoft Word. Tệp đã commit từ commit đầu `bef5695`. Thư mục `datasets/` chỉ bị git-ignore một phần (`raw/`, `drow/`,
  `training/`, …), `woodscape_metadata/` không nằm trong danh sách đó. Mục WoodScape của
  [datasets/TAI_VA_KIEM_TRA.md](../datasets/TAI_VA_KIEM_TRA.md) (nguồn: repo Valeo và Drive chính thức) ghi tệp được tải
  thêm cùng `calibration.zip`. Chưa đối chiếu tệp này với bản trên Drive mà README của repo WoodScape trỏ tới (link ở bảng
  trên).
- Cách đọc: máy không có `pypdf` hay PyMuPDF, nên dùng một script tạm (giải nén luồng zlib, dịch mã chữ qua bảng
  ToUnicode của phông; không lưu trong repo). Văn bản đọc ra liền mạch, hai câu trích ở bảng trên có đủ trong đó.
- **Địa chỉ:** định nghĩa "Dataset" trong tệp ghi bộ dữ liệu có tại `woodscape.valeo.ai`. Trong tệp **không có** chuỗi
  `woodscape.valeo.com` và không có liên kết web nào (URI) tới Valeo. Dòng đầu README của repo WoodScape (bản sao
  `datasets/woodscape_metadata/README.md`) lại ghi `https://woodscape.valeo.com`. Các khối ghi công trong dự án đang dùng
  `.com` (README gốc, `autopark/README.md`, `HUAN_LUYEN.md`, `TONG_HOP_DU_AN.md`, `BAO_CAO_GIAI_DOAN_0.md`, `BEV.md`,
  `DAN_Y_KHOA_LUAN.md`; *cập nhật 25/09/2026:* thêm `KICH_BAN_NGHIEM_THU.md` và `NGUONG_NGHIEM_THU_DE_XUAT.md` từ commit `54cb3e2`; ngoài tài liệu, chuỗi `license` mà `perception/bev.py` ghi vào tệp ra khi chạy BEV trên ảnh WoodScape cũng dùng `.com`). Điều khoản buộc ghi công kèm link tới trang web của bộ dữ liệu; địa chỉ duy nhất văn bản nêu là
  `woodscape.valeo.ai`. Hiện địa chỉ nào còn chạy và là trang chính: **cần tra** (tối 24/09 không mở trang nào). Tệp này không sửa các khối ghi
  công ở tài liệu khác. *(Trả lời 25/09/2026: `.ai` chuyển 301 tới `.com`, và `.com` là trang "Shares4U" không có nội
  dung WoodScape; không địa chỉ nào còn là trang bộ dữ liệu. Chi tiết và đề xuất link ở mục "Kiểm trên web ngày
  25/09/2026" và "Ghi công" phía trên.)*
- Tệp còn ghi Valeo có thể sửa điều khoản bất cứ lúc nào và người dùng phải tự xem bản đang có hiệu lực. Bản trong repo
  là bản tải về lúc chuẩn bị dữ liệu, không chắc là bản mới nhất: **cần tra** lại trước khi nộp. *(25/09/2026: README
  trực tuyến vẫn trỏ cùng tệp Drive như bảng trên; trang web bộ dữ liệu không còn nên không có chỗ nào khác để xem bản
  "controlling version". Bản trên Drive chưa đối chiếu với bản trong repo vì phải tải tệp: vẫn **cần tra**.)*

### Trọng số pretrained của torchvision (điểm bắt đầu huấn luyện)

- Mã: `autopark/perception/model.py` dùng `LRASPP_MobileNet_V3_Large_Weights.COCO_WITH_VOC_LABELS_V1` khi
  `initialization = torchvision_official_pretrained_weights`. `run_manifest.json` của **cả 14** lượt huấn luyện trong
  `runs/` (git-ignore), gồm 12 lượt chính `runs/ai_*/run_manifest.json` và 2 lượt kiểm tra thử
  `runs/ai_woodscape_rtx4000_v1_checks/smoke`, `overfit32` (21/09), ghi đúng một tệp trọng số
  `lraspp_mobilenet_v3_large-d234d4ea.pth`, SHA-256 bắt đầu `d234d4eae9d5`; torch 2.11.0+cu128, torchvision 0.26.0+cu128.
  *(Sửa tối 24/09/2026: bản trước đếm "cả 12" vì chỉ tìm ở `runs/ai_*/`; kết luận cùng một điểm bắt đầu không đổi.)*
- Dữ liệu huấn luyện của trọng số này, theo mô tả trong mã torchvision đã cài: ảnh **COCO**, chỉ giữ 20 lớp có trong
  **Pascal VOC**. Tên "COCO_WITH_VOC_LABELS" vì thế nghĩa là ảnh COCO với bộ nhãn VOC. Không có ảnh VOC trong đó theo mô tả
  này. Số đo torchvision công bố cho trọng số: mIoU 57,9 trên COCO val2017 với nhãn VOC.
- *Thêm tối 24/09/2026:* chuỗi mô tả `_docs` chỉ nói COCO. Trong `torchvision/models/segmentation/lraspp.py` đã cài có
  hai chỗ khác: meta có khóa `recipe` trỏ tới
  `https://github.com/pytorch/vision/tree/main/references/segmentation#lraspp_mobilenet_v3_large`, và hàm dựng mặc định
  `weights_backbone=MobileNet_V3_Large_Weights.IMAGENET1K_V1` (theo meta trong `mobilenetv3.py`, trọng số này được huấn
  luyện từ đầu trên ImageNet). Suy ra: backbone MobileNetV3 của trọng số COCO nhiều khả năng đã khởi tạo từ ImageNet trước
  khi huấn luyện trên COCO. Đây mới là suy luận từ mã: công thức huấn luyện không có trong gói, chưa đọc (**cần tra**). Mã
  dự án không tự tải trọng số ImageNet: `perception/model.py` truyền `weights_backbone=None`, hàm dựng cũng bỏ backbone
  khi đã có `weights`, và cache torch hub trên máy bàn chỉ có `lraspp_mobilenet_v3_large-d234d4ea.pth`. ImageNet, nếu có,
  chỉ đi vào qua lịch sử huấn luyện của tệp trọng số COCO. Điều này không mâu thuẫn với ghi chú ở
  [GAN_NHAN_SA_BAN.md](GAN_NHAN_SA_BAN.md) mục 2 rằng trainer không có tùy chọn khởi tạo chỉ từ ImageNet.
- Giấy phép: METADATA của gói torchvision ghi mã là BSD. Mục "Pre-trained Model License" ghi trọng số có thể mang điều
  khoản riêng theo dữ liệu đã dùng để huấn luyện, và người dùng tự xác định mình có được phép hay không. Mục đó chỉ nêu
  riêng mô hình SWAG (CC BY-NC 4.0). Với trọng số L-RASPP này, gói không nêu điều khoản cụ thể nào.
- **Cần tra:** điều khoản sử dụng của COCO cho ảnh (ảnh lấy từ Flickr, mỗi ảnh có giấy phép riêng) và cho nhãn, và điều
  khoản đó có áp dụng cho trọng số huấn luyện trên COCO hay không. Chưa đọc văn bản gốc nào của COCO. METADATA của
  torchvision không có câu nào cấm dùng trọng số này trên phương tiện, nhưng như vậy **không** có nghĩa là đã được phép.
  Thêm (tối 24/09/2026): công thức huấn luyện ở link `recipe` có dùng backbone ImageNet hay không, và nếu có thì điều khoản
  truy cập ImageNet (chưa đọc văn bản gốc, **cần tra**) có ràng buộc trọng số dẫn xuất hay không.
- Hướng 2 ở trên (huấn luyện lại bằng ảnh sa bàn) vẫn khởi tạo từ trọng số này, nên kết quả tra ở đây cũng áp dụng cho mô
  hình triển khai sau này.

### DROW: ghi công khi dùng hình

- README của tác giả (bản sao `datasets/drow/README_source.md`, git-ignore cùng `datasets/drow/`): mục "Citations and
  Thanks" yêu cầu trích **cả hai** bài; mục "License" nói toàn bộ bộ dữ liệu theo MIT, trừ phần `reha` giữ CC BY-NC-SA
  3.0. Tệp MIT (bản sao `datasets/drow/LICENSE_source.txt`, bản quyền 2016 Visual Computing Institute) buộc giữ thông báo
  bản quyền và giấy phép trong mọi bản sao của phần mềm.
- Hai bài phải trích (theo dòng trích dẫn của README; BibTeX trong README ghi năm 2016 cho bài đầu, và ghi Beyer, Hermans
  đóng góp ngang nhau):
  - Beyer, L., Hermans, A., Leibe, B. (2017). *DROW: Real-Time Deep Learning-Based Wheelchair Detection in 2-D Range
    Data.* IEEE Robotics and Automation Letters, 2(2), 585–592.
  - Beyer, L., Hermans, A., Linder, T., Arras, K. O., Leibe, B. (2018). *Deep Person Detection in 2D Range Data.* IEEE
    Robotics and Automation Letters, 3(3), 2726–2733.
- Hình trong repo dựng từ DROW: [drow_odom_map.png](evidence/lidar/drow_odom_map.png),
  [drow_odom_mirror_map.png](evidence/lidar/drow_odom_mirror_map.png), [drow_fixed_map.png](evidence/lidar/drow_fixed_map.png)
  ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 5), và `runs/perception_integration/drow_scan_person.png`
  (git-ignore). Cả bốn dựng từ bản ghi val `run_2015-11-25-10-34-20-a`. *(Cập nhật 25/09/2026: commit `a7cec5e` thêm
  bốn hình DROW nữa trong `evidence/lidar/`:
  [odometry_khop_scan_drow_10-34-20-a_scan_to_map.png](evidence/lidar/odometry_khop_scan_drow_10-34-20-a_scan_to_map.png),
  [odometry_khop_scan_drow_10-34-20-a_scan_to_scan.png](evidence/lidar/odometry_khop_scan_drow_10-34-20-a_scan_to_scan.png),
  [odometry_khop_scan_drow_13-47-42_scan_to_map.png](evidence/lidar/odometry_khop_scan_drow_13-47-42_scan_to_map.png) và
  [odometry_khop_scan_drow_13-47-42_scan_to_map_khoa_cung_truoc_sua.png](evidence/lidar/odometry_khop_scan_drow_13-47-42_scan_to_map_khoa_cung_truoc_sua.png).
  Theo tên tệp, hai hình đầu cũng từ bản ghi val `run_2015-11-25-10-34-20-a`; hai hình sau từ bản ghi test
  `run_t_2015-11-26-13-47-42` (lệnh chạy ghi trong `evidence/lidar/odometry_khop_scan_20260924.json`). Ghi công ở
  [SO_SANH_DINH_VI_SLAM.md](SO_SANH_DINH_VI_SLAM.md) mục "Ghi công dữ liệu". Câu về `reha` dưới đây cũng áp dụng cho
  bốn hình này: kiểm lại 25/09/2026 vẫn 0 tệp.)* Trong `datasets/drow/` không có tệp nào tên chứa
  `reha` (kiểm tối 24/09/2026: 0 tệp), nên các hình này theo MIT. Hình nào đưa vào khóa luận thì chú thích hình ghi nguồn
  DROW v2 và trích hai bài trên. Nếu sau này dùng phần `reha` thì theo CC BY-NC-SA 3.0 (phi thương mại, chia sẻ cùng
  giấy phép).
