"""Safely extract verified dataset archives and record a usable inventory.

Only archives with a verified checksum/CRC sidecar are accepted. Never execute
code from an archive. Re-running checks already extracted files by ZIP CRC.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
import zlib

ROOT = Path(__file__).resolve().parent
ARCHIVES = {
    "woodscape_rgb_images.zip": "woodscape",
    "woodscape_semantic_annotations.zip": "woodscape",
    "woodscape_instance_annotations.zip": "woodscape",
    "dataset_AnomalyTrack.zip": "road_anomaly",
    "dataset_ObstacleTrack.zip": "road_obstacle",
    "acdc_rgb_anon_trainvaltest.zip": "acdc/rgb",
    "acdc_gt_trainval.zip": "acdc/gt",
    "acdc_gt_trainval_ref.zip": "acdc/gt_ref",
}


def save(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def unpack(name, folder):
    archive_path = ROOT / "raw/full" / name
    sidecar = archive_path.with_suffix(".zip.json")
    if not archive_path.exists() or not sidecar.exists():
        return {"archive": name, "status": "pending_download"}
    metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    if metadata.get("status") != "verified" or not metadata.get("zip_crc_ok"):
        return {"archive": name, "status": "pending_verification"}
    target = (ROOT / "training" / folder).resolve()
    target.mkdir(parents=True, exist_ok=True)
    marker = target / (name + ".extracted.json")
    if marker.exists():
        previous = json.loads(marker.read_text(encoding="utf-8"))
        if previous.get("archive_sha256") == metadata["sha256"]:
            return previous
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        required = sum(m.file_size for m in members if not (target / m.filename).exists())
        if required + 5 * 1024**3 > shutil.disk_usage(target).free:
            return {"archive": name, "status": "insufficient_space_to_extract", "needed_bytes": required}
        for member in members:
            path = (target / member.filename).resolve()
            if not path.is_relative_to(target):
                raise ValueError("Archive path escapes destination")
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Symlinks in archives are not extracted")
        count = 0
        for member in members:
            path = target / member.filename
            if member.is_dir():
                path.mkdir(parents=True, exist_ok=True)
                continue
            if path.exists():
                crc = 0
                with path.open("rb") as f:
                    while chunk := f.read(1024 * 1024):
                        crc = zlib.crc32(chunk, crc)
                if path.stat().st_size != member.file_size or crc != member.CRC:
                    raise ValueError(f"Existing file differs; preserved: {path}")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                partial = path.with_suffix(path.suffix + ".extracting")
                with archive.open(member) as source, partial.open("wb") as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
                partial.replace(path)
            count += 1
    report = {"archive": name, "status": "extracted", "directory": str(target.relative_to(ROOT)),
              "files": count, "archive_sha256": metadata["sha256"],
              "completed_utc": datetime.now(timezone.utc).isoformat()}
    save(marker, report)
    print("EXTRACTED", name, count, flush=True)
    return report


def inventory():
    training = ROOT / "training"
    wood = training / "woodscape"
    rgb = {p.name for p in (wood / "rgb_images").glob("*.png")}
    semantic = {p.name for p in (wood / "semantic_annotations/gtLabels").glob("*.png")}
    report = {"woodscape": {"rgb": len(rgb), "semantic": len(semantic),
                             "paired": len(rgb & semantic), "missing_masks": sorted(rgb - semantic)}}
    for key, folder in (("acdc", training / "acdc"), ("road_anomaly", training / "road_anomaly"),
                        ("road_obstacle", training / "road_obstacle")):
        report[key] = {"png": sum(1 for _ in folder.rglob("*.png")),
                       "jpg": sum(1 for _ in folder.rglob("*.jpg")),
                       "json": sum(1 for _ in folder.rglob("*.json"))}
    return report


if __name__ == "__main__":
    reports = [unpack(name, folder) for name, folder in ARCHIVES.items()]
    result = {"archives": reports, "inventory": inventory(),
              "complete": all(r["status"] == "extracted" for r in reports)}
    save(ROOT / "full_dataset_inventory.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
