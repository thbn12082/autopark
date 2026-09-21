"""Download public dataset archives with checked HTTP ranges and resumable chunks.

Run from autopark: python datasets/download_full.py datasets/full_download_jobs.json
Only public URLs are used. Authentication/quota errors are reported, not bypassed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import threading
import time
import zipfile

import requests

CHUNK = 32 * 1024 * 1024
ROOT = Path(__file__).resolve().parent
LOCK = threading.Lock()


def save(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def fetch_chunk(job, start, end, part, state, state_path):
    for attempt in range(5):
        try:
            with requests.get(job["url"], headers={"Range": f"bytes={start}-{end-1}"},
                              stream=True, timeout=(30, 90)) as response:
                if response.status_code in (500, 502, 503, 504):
                    raise requests.ConnectionError(f"HTTP {response.status_code}")
                expected = f"bytes {start}-{end-1}/{job['size']}"
                if response.status_code != 206 or response.headers.get("Content-Range") != expected:
                    raise RuntimeError(f"{job['name']}: range refused, HTTP {response.status_code}, "
                                       f"Content-Range={response.headers.get('Content-Range')}")
                received = 0
                with part.open("r+b") as output:
                    output.seek(start)
                    for data in response.iter_content(1024 * 1024):
                        if received + len(data) > end - start:
                            raise RuntimeError("Response exceeds requested range")
                        output.write(data)
                        received += len(data)
                if received != end - start:
                    raise requests.ConnectionError("Incomplete range body")
            with LOCK:
                state["completed"].append(start)
                state["downloaded_bytes"] += end - start
                state["updated_utc"] = datetime.now(timezone.utc).isoformat()
                save(state_path, state)
            return
        except requests.RequestException:
            if attempt == 4:
                raise
            time.sleep(min(2 ** attempt, 10))


def verify(job, path):
    sha, md5 = hashlib.sha256(), hashlib.md5()
    with path.open("rb") as f:
        while data := f.read(8 * 1024 * 1024):
            sha.update(data)
            md5.update(data)
    if path.stat().st_size != job["size"]:
        raise ValueError("File size mismatch")
    if job.get("md5") and md5.hexdigest() != job["md5"]:
        raise ValueError("Publisher MD5 mismatch")
    report = {**job, "sha256": sha.hexdigest(), "md5": md5.hexdigest(),
              "status": "verified", "verified_utc": datetime.now(timezone.utc).isoformat()}
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad:
                raise ValueError(f"ZIP CRC mismatch: {bad}")
            report["zip_crc_ok"] = True
            report["entries"] = len(archive.infolist())
            report["uncompressed_bytes"] = sum(info.file_size for info in archive.infolist())
    save(path.with_suffix(path.suffix + ".json"), report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("jobs", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    jobs = json.loads(args.jobs.read_text(encoding="utf-8"))
    output = ROOT / "raw/full"
    output.mkdir(parents=True, exist_ok=True)
    pending, states = [], []
    needed = sum(j['size'] for j in jobs if not (output / j['name']).exists()
                 and not (output / (j['name'] + '.part')).exists())
    if needed + 5 * 1024**3 > shutil.disk_usage(output).free:
        raise RuntimeError("Insufficient free space with 5 GiB reserve")
    for job in jobs:
        name = job["name"]
        if Path(name).name != name:
            raise ValueError("Filename must not contain directories")
        final = output / name
        if final.exists():
            print("VERIFY_EXISTING", name, flush=True)
            verify(job, final)
            continue
        part, state_path = output / (name + ".part"), output / (name + ".progress.json")
        if part.exists() and state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if state["url"] != job["url"] or state["size"] != job["size"] or part.stat().st_size != job["size"]:
                raise ValueError("Existing partial file has incompatible metadata")
            if state["downloaded_bytes"] == job["size"]:
                if name.endswith(".zip"):
                    with zipfile.ZipFile(part) as archive:
                        if archive.testzip() is not None:
                            raise ValueError("Completed partial archive has a CRC error")
                part.replace(final)
                verify(job, final)
                print("VERIFIED_RESUMED", name, flush=True)
                continue
        else:
            if part.exists():
                raise ValueError("Partial file has no progress metadata")
            with part.open("wb") as f:
                f.truncate(job["size"])
            state = {**job, "completed": [], "downloaded_bytes": 0, "chunk_bytes": CHUNK}
            save(state_path, state)
        states.append((job, part, state, state_path))
        done = set(state["completed"])
        pending.append([(job, start, min(start + CHUNK, job["size"]), part, state, state_path)
                        for start in range(0, job["size"], CHUNK) if start not in done])
    # Round-robin queues ensure the small annotation archives finish alongside RGB.
    work = []
    while any(pending):
        for queue in pending:
            if queue:
                work.append(queue.pop(0))
    errors = []
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(fetch_chunk, *item): item[0]["name"] for item in work}
        last_print = 0
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                errors.append({"file": futures[future], "error": str(exc)})
                print("ERROR", errors[-1], flush=True)
            now = time.monotonic()
            if now - last_print >= 20:
                total = sum(state['downloaded_bytes'] for _, _, state, _ in states)
                print(f"PROGRESS {total/1e9:.3f} GB; elapsed {now-started:.0f}s", flush=True)
                last_print = now
    reports = []
    for job, part, state, state_path in states:
        if state["downloaded_bytes"] != job["size"]:
            continue
        print("VERIFY", job["name"], flush=True)
        try:
            # Verify before publishing the final filename.
            final = output / job["name"]
            sha, md5 = hashlib.sha256(), hashlib.md5()
            with part.open("rb") as f:
                while data := f.read(8 * 1024 * 1024):
                    sha.update(data); md5.update(data)
            if job.get("md5") and md5.hexdigest() != job["md5"]:
                raise ValueError("Publisher MD5 mismatch")
            if job["name"].endswith(".zip"):
                with zipfile.ZipFile(part) as archive:
                    bad = archive.testzip()
                    if bad:
                        raise ValueError(f"CRC mismatch: {bad}")
                    entries = len(archive.infolist())
                    unpacked = sum(i.file_size for i in archive.infolist())
            else:
                entries, unpacked = 0, 0
            part.replace(final)
            report = {**job, "status": "verified", "sha256": sha.hexdigest(), "md5": md5.hexdigest(),
                      "zip_crc_ok": job['name'].endswith('.zip'), "entries": entries,
                      "uncompressed_bytes": unpacked, "verified_utc": datetime.now(timezone.utc).isoformat()}
            save(final.with_suffix(final.suffix + ".json"), report)
            reports.append(report)
            print("VERIFIED", job["name"], flush=True)
        except Exception as exc:
            errors.append({"file": job["name"], "error": str(exc)})
    save(ROOT / "full_download_result.json", {"verified": reports, "errors": errors})
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
