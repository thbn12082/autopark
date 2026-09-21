# Trạng thái tải bộ dữ liệu huấn luyện

Cập nhật UTC: 2026-09-19T20:18:31.527448+00:00

**Hoàn tất tải và giải nén: CÓ**

| Gói | Trạng thái | Đã nhận (GB thập phân) | Tổng (GB) |
|---|---|---:|---:|
| woodscape_rgb_images.zip | extracted | 15.221 | 15.221 |
| woodscape_semantic_annotations.zip | extracted | 0.198 | 0.198 |
| woodscape_instance_annotations.zip | extracted | 0.304 | 0.304 |
| dataset_AnomalyTrack.zip | extracted | 0.053 | 0.053 |
| dataset_ObstacleTrack.zip | extracted | 0.208 | 0.208 |
| acdc_rgb_anon_trainvaltest.zip | extracted | 16.742 | 16.742 |
| acdc_gt_trainval.zip | extracted | 0.133 | 0.133 |
| acdc_gt_trainval_ref.zip | extracted | 0.057 | 0.057 |

Archive: `raw/full/`. Dữ liệu giải nén: `training/`.

**Dọn dẹp 21/09/2026:** các file ZIP trong `raw/` và `raw/full/` (gồm cả AVM và DROW, 31 GB) đã được chuyển ra `D:\ap\_CHO_XOA\datasets_raw_zip\` để xóa, sau khi đối chiếu kích thước + CRC32 của toàn bộ 75.640 file bên trong với bản giải nén: khớp 100% ([biên bản](download_metadata/raw_vs_extracted_crc_2026-09-21.json)). Các file `.zip.json` ghi SHA-256 của từng archive được giữ lại trong `raw/`. Bản giải nén nay là bản duy nhất trên máy này. **Không chạy lại `prepare_full_downloads.py`** khi không còn ZIP: nó sẽ ghi đè `full_dataset_inventory.json` thành "pending_download".

Mỗi archive chỉ được công bố hoàn tất sau khi kiểm tra SHA-256 và ZIP CRC; ACDC/Zenodo còn đối chiếu MD5 của nhà cung cấp.

Không dùng nhãn test giữ kín để train. File `.part` có thể đã đặt trước kích thước; hãy xem số byte trong báo cáo này để biết tiến độ thật.

Nguồn: [WoodScape](https://github.com/valeoai/WoodScape), [ACDC](https://acdc.vision.ee.ethz.ch/download), [RoadAnomaly21/RoadObstacle21](https://segmentmeifyoucan.com/datasets).
