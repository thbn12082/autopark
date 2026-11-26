"""Tải mẫu ghép cặp WoodScape từ ZIP công khai bằng HTTP Range.

Không tải toàn bộ RGB 15,22 GB. Không vượt đăng nhập/quota; chỉ chấp nhận HTTP 206.
Đây là subset kiểm tra pipeline, không phải split đánh giá chính thức.
"""
import argparse
from collections import defaultdict
import hashlib
import io
import json
from pathlib import Path
import zipfile
import time
import zlib

import requests

ARCHIVES = {
    "rgb": ("1xQ5J4huNmyK9WPoipHTnuZ7lw_J0xhvL", 15220809344),
    "semantic": ("1CBwi0fpDE2G99hHiINTI-AXlOMQSUnb-", 198490338),
}


class RemoteFile(io.RawIOBase):
    def __init__(self, url, size):
        self.url, self.size, self.pos = url, size, 0
        self.session = requests.Session()

    def seekable(self):
        return True

    def seek(self, offset, whence=0):
        self.pos = offset if whence == 0 else (self.pos + offset if whence == 1 else self.size + offset)
        if self.pos < 0:
            raise ValueError("Negative seek")
        return self.pos

    def tell(self):
        return self.pos

    def read(self, size=-1):
        end = self.size if size < 0 else min(self.pos + size, self.size)
        if end <= self.pos:
            return b""
        chunks = []
        while self.pos < end:
            stop = min(end, self.pos + 1024 * 1024)
            expected = f"bytes {self.pos}-{stop - 1}/{self.size}"
            for attempt in range(3):
                with self.session.get(self.url, headers={"Range": f"bytes={self.pos}-{stop - 1}"},
                                      timeout=60, stream=True) as r:
                    if r.status_code not in (500, 502, 503, 504):
                        if r.status_code != 206 or r.headers.get("Content-Range") != expected:
                            raise RuntimeError(f"Server không trả đúng Range: HTTP {r.status_code}")
                        data = r.content
                        if len(data) != stop - self.pos:
                            raise RuntimeError("Range body không đủ byte")
                        break
                time.sleep(attempt + 1)
            else:
                raise RuntimeError(f"Server không trả đúng Range: HTTP {r.status_code}")
            chunks.append(data)
            self.pos = stop
        return b"".join(chunks)

    def close(self):
        self.session.close()
        super().close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-camera", type=int, default=16)
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("datasets/woodscape_subset"))
    args = parser.parse_args()
    if args.per_camera < 1:
        parser.error("per-camera phải > 0")
    from contextlib import ExitStack
    with ExitStack() as stack:
        archives = {}
        for name, (key, size) in ARCHIVES.items():
            url = f"https://drive.usercontent.google.com/download?id={key}&export=download&confirm=t"
            remote = stack.enter_context(RemoteFile(url, size))
            archives[name] = stack.enter_context(zipfile.ZipFile(remote))
        for name, z in archives.items():
            print(name, "entries", len(z.infolist()), z.namelist()[:8], flush=True)
        if args.list_only:
            return
        rgb = {Path(i.filename).name: i for i in archives["rgb"].infolist()
               if i.filename.lower().endswith(".png")}
        masks = {Path(i.filename).name: i for i in archives["semantic"].infolist()
                 if "gtlabels" in i.filename.lower() and i.filename.lower().endswith(".png")}
        if not masks:
            raise ValueError("Không tìm thấy gtLabels; kiểm tra schema trước khi tải")
        groups = defaultdict(list)
        for name in sorted(rgb.keys() & masks.keys()):
            groups[Path(name).stem.split("_")[-1]].append(name)
        records = []
        args.out.mkdir(parents=True, exist_ok=True)
        for camera, names in sorted(groups.items()):
            for name in names[:args.per_camera]:
                record = {"name": name, "camera": camera, "files": {}}
                for kind, index in (("rgb", rgb), ("semantic", masks)):
                    destination = args.out / kind / name
                    destination.parent.mkdir(exist_ok=True)
                    info = index[name]
                    data = destination.read_bytes() if destination.exists() else b""
                    if len(data) != info.file_size or zlib.crc32(data) != info.CRC:
                        data = archives[kind].read(info)  # ZIP CRC kiểm tra ở đây.
                        partial = destination.with_suffix(destination.suffix + ".part")
                        partial.write_bytes(data)
                        partial.replace(destination)
                    record["files"][kind] = {"member": index[name].filename, "bytes": len(data),
                                              "sha256": hashlib.sha256(data).hexdigest()}
                records.append(record)
                print("Downloaded pair", name, flush=True)
        if not records:
            raise ValueError("Không tìm thấy cặp ảnh/mask cùng tên")
        report = {"source": "https://github.com/valeoai/WoodScape", "archives": ARCHIVES,
                  "subset_only": True, "selection": "first N sorted paired samples per camera",
                  "not_official_evaluation_split": True, "pairs": records}
        (args.out / "manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
