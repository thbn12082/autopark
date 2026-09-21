"""Keep a live inventory and extract each archive once its download is verified."""
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from prepare_full_downloads import ROOT, ARCHIVES, unpack, inventory, save


def status():
    rows = []
    for name, folder in ARCHIVES.items():
        final = ROOT / "raw/full" / name
        sidecar = final.with_suffix(".zip.json")
        progress = final.with_suffix(".zip.progress.json")
        row = {"archive": name, "status": "pending", "downloaded_bytes": 0}
        if progress.exists():
            data = json.loads(progress.read_text(encoding="utf-8"))
            row.update(status=data.get("status", "downloading"),
                       downloaded_bytes=data.get("downloaded_bytes", 0), size=data.get("size"))
        if final.exists() and sidecar.exists():
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            if data.get("status") == "verified":
                row.update(unpack(name, folder))
                row.update(downloaded_bytes=final.stat().st_size, size=final.stat().st_size,
                           sha256=data["sha256"], zip_crc_ok=data["zip_crc_ok"])
        rows.append(row)
    result = {"updated_utc": datetime.now(timezone.utc).isoformat(), "archives": rows,
              "complete": all(r["status"] == "extracted" for r in rows), "inventory": inventory()}
    save(ROOT / "full_dataset_inventory.json", result)
    lines = ["# Trạng thái tải bộ dữ liệu huấn luyện", "", "Cập nhật UTC: " + result["updated_utc"], "",
             "**Hoàn tất tải và giải nén: " + ("CÓ" if result["complete"] else "CHƯA") + "**", "",
             "| Gói | Trạng thái | Đã nhận (GB thập phân) | Tổng (GB) |", "|---|---|---:|---:|"]
    for row in rows:
        size = f"{row['size']/1e9:.3f}" if row.get("size") else "server không báo"
        lines.append(f"| {row['archive']} | {row['status']} | {row['downloaded_bytes']/1e9:.3f} | {size} |")
    lines += ["", "Archive: `raw/full/`. Dữ liệu giải nén: `training/`.", "",
              "Mỗi archive chỉ được công bố hoàn tất sau khi kiểm tra SHA-256 và ZIP CRC; "
              "ACDC/Zenodo còn đối chiếu MD5 của nhà cung cấp.", "",
              "Không dùng nhãn test giữ kín để train. File `.part` có thể đã đặt trước kích thước; "
              "hãy xem số byte trong báo cáo này để biết tiến độ thật.", "",
              "Nguồn: [WoodScape](https://github.com/valeoai/WoodScape), "
              "[ACDC](https://acdc.vision.ee.ethz.ch/download), "
              "[RoadAnomaly21/RoadObstacle21](https://segmentmeifyoucan.com/datasets)."]
    (ROOT / "TRANG_THAI_TAI_DAY_DU.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    while True:
        result = status()
        print("STATUS", round(sum(r['downloaded_bytes'] for r in result['archives']) / 1e9, 3),
              "GB; extracted", sum(r['status'] == 'extracted' for r in result['archives']),
              "/", len(ARCHIVES), flush=True)
        if result["complete"]:
            print("ALL DOWNLOADS VERIFIED AND EXTRACTED", flush=True)
            break
        time.sleep(30)
