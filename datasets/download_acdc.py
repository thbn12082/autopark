"""Use the public ACDC package API used by its download page. No account required.

The ACDC server streams ZIPs without Content-Length or range support. Verify the
publisher MD5 before publishing a completed file. A failed stream must restart.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import zipfile

import requests

ROOT = Path(__file__).resolve().parent
API = "https://acdc.vision.ee.ethz.ch/api"
NAMES = {"gt_trainval.zip", "rgb_anon_trainvaltest.zip", "gt_trainval_ref.zip"}


def save(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def download(package):
    output = ROOT / "raw/full"
    output.mkdir(parents=True, exist_ok=True)
    name = "acdc_" + package["name"]
    final = output / name
    partial = output / (name + ".part")
    progress = output / (name + ".progress.json")
    info = {"name": name, "package_id": package["packageId"], "source": "https://acdc.vision.ee.ethz.ch/download",
            "publisher_md5": package["md5"], "description": package["description"], "status": "downloading"}
    if not final.exists():
        for attempt in range(3):
            try:
                link = requests.get(API + "/getPackageUri/" + package["packageId"], timeout=30)
                link.raise_for_status()
                # Ephemeral download tokens are never persisted in manifests.
                url = API + "/downloadPackage/" + link.json()["token"] + "/" + package["downloadTitle"]
                with requests.get(url, stream=True, timeout=(30, 120)) as response:
                    response.raise_for_status()
                    if "zip" not in response.headers.get("Content-Type", ""):
                        raise ValueError("Server did not return a ZIP")
                    count, previous = 0, time.monotonic()
                    with partial.open("wb") as f:
                        for data in response.iter_content(1024 * 1024):
                            if data:
                                f.write(data)
                                count += len(data)
                            now = time.monotonic()
                            if now - previous >= 20:
                                info.update(downloaded_bytes=count, attempt=attempt + 1,
                                            updated_utc=datetime.now(timezone.utc).isoformat())
                                save(progress, info)
                                print(f"ACDC {name}: {count/1e9:.3f} GB", flush=True)
                                previous = now
                    info["downloaded_bytes"] = count
                    save(progress, info)
                break
            except requests.RequestException as exc:
                info.update(status="retrying", error=str(exc), attempt=attempt + 1)
                save(progress, info)
                if attempt == 2:
                    raise
                time.sleep(5)
        path = partial
    else:
        path = final
    info["status"] = "verifying"
    save(progress, info)
    sha, md5 = hashlib.sha256(), hashlib.md5()
    with path.open("rb") as f:
        while data := f.read(8 * 1024 * 1024):
            sha.update(data)
            md5.update(data)
    if md5.hexdigest() != package["md5"]:
        raise ValueError(f"Publisher MD5 mismatch for {name}")
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"ZIP CRC error: {bad}")
        info.update(entries=len(archive.infolist()), uncompressed_bytes=sum(i.file_size for i in archive.infolist()))
    if path == partial:
        partial.replace(final)
    info.update(status="verified", size=final.stat().st_size, sha256=sha.hexdigest(), md5=md5.hexdigest(),
                zip_crc_ok=True, verified_utc=datetime.now(timezone.utc).isoformat())
    save(final.with_suffix(final.suffix + ".json"), info)
    save(progress, info)
    print("VERIFIED", name, info["size"], flush=True)
    return info


if __name__ == "__main__":
    response = requests.get(API + "/packages", timeout=30)
    response.raise_for_status()
    packages = [p for p in response.json()["packages"] if p["name"] in NAMES]
    if len(packages) != len(NAMES):
        raise ValueError("Missing expected public package")
    errors, results = [], []
    def run(package):
        try:
            results.append(download(package))
        except Exception as exc:
            errors.append({"file": package["name"], "error": str(exc)})
            print("ERROR", errors[-1], flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(run, packages))
    save(ROOT / "acdc_download_result.json", {"verified": results, "errors": errors})
    if errors:
        raise SystemExit(1)
