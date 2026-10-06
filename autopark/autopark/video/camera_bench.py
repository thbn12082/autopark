"""Phiên đo camera USB (UVC) trên bàn thử — bước "Khi nhận một camera" và "Khi đủ bốn camera" của kế hoạch.

Mọi con số ở đây là số đo, không phải thông số bán hàng:

- `list`    : thiết bị Windows thấy (PnP: cổng hub, đường USB) và thiết bị DirectShow thấy (tên, thứ tự index).
- `modes`   : media type camera tự công bố qua DirectShow (định dạng, kích thước, FPS min/max) → `camera_modes.csv`.
              Cần gói `pygrabber` (Windows); không có thì báo rõ, không đoán.
- `measure` : mở 1..N camera cùng lúc ở một mode, đọc trong T giây, ghi FPS THẬT (chỉ đếm khung khác khung trước),
              số lần driver trả lại khung cũ, số lần đọc hỏng, khoảng cách giữa hai khung mới (trung vị / p95 / max),
              thời gian một lần `read()`, độ sáng trung bình và CPU của tiến trình → `*.measure.json`.
- `record`  : ghi video MJPG + ảnh tĩnh định kỳ từ một camera, kèm json mô tả mode và FPS thật của chính đoạn ghi.
- `report`  : gom các `*.measure.json` trong một thư mục thành `report.md`.

Ba điều đã kiểm với OpenCV 5.0 + DirectShow ngày 23/09/2026 và được mã này tuân theo:
  1. Kích thước và MJPG phải đưa vào NGAY LÚC MỞ (`params` của `cv2.VideoCapture`); đặt sau khi mở thì backend rơi
     về YUY2 và 720p/1080p chỉ còn 10/5 fps.
  2. `grab()` không chờ khung mới (trả về ngay, hàng triệu lần/giây); phải dùng `read()`, hàm này chặn tới khung kế.
  3. `CAP_PROP_FOURCC` và `CAP_PROP_FPS` đọc lại chỉ là tiếng vọng của yêu cầu (luôn YUY2 / đúng số đã đặt), nên
     định dạng thật lấy từ `modes`, còn FPS thật phải đo.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from autopark.image_io import imwrite
from autopark.power_throttling import apply_ecoqos_policy, ecoqos_state
from autopark.video.sources import torn_bands, truncated_rows

DEFAULT_FOURCC = "MJPG"
SNAPSHOT_EXT = ".png"


# ----------------------------------------------------------------------------------------------- liệt kê thiết bị

_PNP_SCRIPT = r"""
$devs = Get-PnpDevice -PresentOnly | Where-Object { $_.Class -in @('Camera','Image') }
$rows = foreach ($d in $devs) {
  $p = Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName 'DEVPKEY_Device_Parent','DEVPKEY_Device_LocationPaths','DEVPKEY_Device_LocationInfo' -ErrorAction SilentlyContinue
  $parent = ($p | Where-Object KeyName -eq 'DEVPKEY_Device_Parent').Data
  $paths = ($p | Where-Object KeyName -eq 'DEVPKEY_Device_LocationPaths').Data
  $pp = $null
  if ($parent) { $pp = (Get-PnpDeviceProperty -InstanceId $parent -KeyName 'DEVPKEY_Device_Parent','DEVPKEY_Device_LocationInfo' -ErrorAction SilentlyContinue) }
  [pscustomobject]@{
    instance_id = $d.InstanceId; friendly_name = $d.FriendlyName; status = "$($d.Status)"
    location_info = "$(($p | Where-Object KeyName -eq 'DEVPKEY_Device_LocationInfo').Data)"
    parent = "$parent"
    parent_location = "$(($pp | Where-Object KeyName -eq 'DEVPKEY_Device_LocationInfo').Data)"
    hub = "$(($pp | Where-Object KeyName -eq 'DEVPKEY_Device_Parent').Data)"
    location_paths = @($paths) -join ' | '
  }
}
$hubs = Get-PnpDevice -PresentOnly -Class USB | Where-Object { $_.FriendlyName -match 'Hub' -and $_.InstanceId -notmatch '^USB\\ROOT_HUB' }
$hubrows = foreach ($h in $hubs) {
  $q = Get-PnpDeviceProperty -InstanceId $h.InstanceId -KeyName 'DEVPKEY_Device_Parent','DEVPKEY_Device_LocationInfo','DEVPKEY_Device_LocationPaths','DEVPKEY_Device_BusReportedDeviceDesc' -ErrorAction SilentlyContinue
  [pscustomobject]@{
    instance_id = $h.InstanceId; friendly_name = $h.FriendlyName; status = "$($h.Status)"
    bus_reported_desc = "$(($q | Where-Object KeyName -eq 'DEVPKEY_Device_BusReportedDeviceDesc').Data)"
    parent = "$(($q | Where-Object KeyName -eq 'DEVPKEY_Device_Parent').Data)"
    location_info = "$(($q | Where-Object KeyName -eq 'DEVPKEY_Device_LocationInfo').Data)"
    location_paths = @(($q | Where-Object KeyName -eq 'DEVPKEY_Device_LocationPaths').Data) -join ' | '
  }
}
[pscustomobject]@{ cameras = @($rows); hubs = @($hubrows) } | ConvertTo-Json -Compress -Depth 4
"""


def _port_of(location: str) -> int | None:
    if "Port_#" in (location or ""):
        try:
            return int(location.split("Port_#")[1].split(".")[0])
        except ValueError:
            return None
    return None


def parse_pnp_json(text: str) -> list[dict]:
    """Camera từ JSON của PowerShell. Nhận cả dạng cũ (mảng/object camera) lẫn dạng mới ({cameras, hubs}).
    Cổng hub: camera composite (InstanceId có `&MI_`) lấy từ LocationInfo của thiết bị cha; camera đơn lấy từ chính nó."""
    text = text.strip()
    if not text:
        return []
    data = json.loads(text)
    if isinstance(data, dict) and "cameras" in data:
        data = data["cameras"]
    rows = data if isinstance(data, list) else [data]
    out = []
    for row in rows:
        instance_id = row.get("instance_id", "") or ""
        composite = "&MI_" in instance_id.upper()
        own, parent_loc = row.get("location_info") or "", row.get("parent_location") or ""
        loc = parent_loc if composite else (own or parent_loc)   # dạng cũ không có location_info → dùng của cha
        out.append({"instance_id": instance_id, "friendly_name": row.get("friendly_name", ""),
                    "status": row.get("status", ""), "parent": row.get("parent", ""), "hub": row.get("hub", ""),
                    "hub_port": _port_of(loc), "parent_location": row.get("parent_location", "") or "",
                    "location_info": row.get("location_info", "") or "", "location_paths": row.get("location_paths", "")})
    return sorted(out, key=lambda r: (r["hub"], r["hub_port"] if r["hub_port"] is not None else 999, r["instance_id"]))


def parse_pnp_hubs(text: str) -> list[dict]:
    """Hub USB (không tính root hub) từ JSON dạng mới; dạng cũ không có hub → rỗng."""
    text = text.strip()
    if not text:
        return []
    data = json.loads(text)
    if not isinstance(data, dict) or "hubs" not in data:
        return []
    hubs = data["hubs"]
    hubs = hubs if isinstance(hubs, list) else [hubs]
    return [{"instance_id": h.get("instance_id", ""), "friendly_name": h.get("friendly_name", ""),
             "bus_reported_desc": h.get("bus_reported_desc", ""), "parent": h.get("parent", ""),
             "location_info": h.get("location_info", ""), "root_port": _port_of(h.get("location_info", "")),
             "location_paths": h.get("location_paths", "")} for h in hubs]


def _pnp_json() -> str:
    if sys.platform != "win32":
        return ""
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PNP_SCRIPT],
                            capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"PowerShell Get-PnpDevice failed: {result.stderr.strip()[:300]}")
    return result.stdout


def pnp_cameras() -> list[dict]:
    """Camera mà Windows thấy, kèm hub và cổng (chỉ Windows; nơi khác trả về rỗng)."""
    return parse_pnp_json(_pnp_json())


def pnp_hubs() -> list[dict]:
    """Hub USB mà Windows thấy (chỉ Windows; nơi khác trả về rỗng)."""
    return parse_pnp_hubs(_pnp_json())


def _filter_graph():
    try:
        from pygrabber.dshow_graph import FilterGraph
    except ImportError as exc:                      # pragma: no cover - depends on the environment
        raise RuntimeError("cần gói pygrabber (pip install pygrabber) để hỏi DirectShow; chỉ có trên Windows") from exc
    return FilterGraph


def dshow_devices() -> list[str]:
    """Tên các thiết bị video DirectShow theo đúng thứ tự index mà OpenCV dùng."""
    return list(_filter_graph()().get_input_devices())


def instance_key_from_path(device_path: str) -> str:
    r"""DevicePath DirectShow `\\?\usb#vid_1bcf&pid_0b09&mi_00#7&56b40fb&0&0000#{guid}\global`
    → khóa PnP `USB\VID_1BCF&PID_0B09&MI_00\7&56B40FB&0&0000` (khớp InstanceId của Get-PnpDevice)."""
    path = device_path.strip()
    if path.startswith("\\\\?\\"):
        path = path[4:]
    path = path.split("#{")[0]
    return path.replace("#", "\\").upper()


def dshow_device_paths() -> list[dict]:
    """Thiết bị video DirectShow theo thứ tự index (= index OpenCV) kèm DevicePath, để ghép index ↔ cổng hub."""
    try:
        from comtypes import GUID
        from comtypes.persist import IPropertyBag
        from pygrabber.dshow_graph import SystemDeviceEnum
        from pygrabber.dshow_ids import DeviceCategories
    except ImportError as exc:                      # pragma: no cover - depends on the environment
        raise RuntimeError("cần gói pygrabber/comtypes để hỏi DirectShow; chỉ có trên Windows") from exc
    enumerator = SystemDeviceEnum().system_device_enum.CreateClassEnumerator(GUID(DeviceCategories.VideoInputDevice), dwFlags=0)
    rows: list[dict] = []
    try:
        moniker, count = enumerator.Next(1)
    except ValueError:                              # pragma: no cover - no device at all
        return rows
    while count > 0:
        bag = moniker.BindToStorage(0, 0, IPropertyBag._iid_).QueryInterface(IPropertyBag)
        name = str(bag.Read("FriendlyName", pErrorLog=None))
        try:
            path = str(bag.Read("DevicePath", pErrorLog=None))
        except Exception:                           # pragma: no cover - virtual devices have no path
            path = ""
        rows.append({"index": len(rows), "name": name, "device_path": path, "instance_key": instance_key_from_path(path)})
        moniker, count = enumerator.Next(1)
    return rows


def join_index_to_port(dshow_rows: list[dict], pnp_rows: list[dict]) -> list[dict]:
    """Mỗi index DirectShow → cổng hub (qua instance id). Không khớp thì hub_port = None, không đoán."""
    by_key = {row["instance_id"].upper(): row for row in pnp_rows}
    out = []
    for row in dshow_rows:
        pnp = by_key.get(row["instance_key"])
        out.append({"index": row["index"], "name": row["name"], "instance_id": pnp["instance_id"] if pnp else None,
                    "hub": pnp["hub"] if pnp else None, "hub_port": pnp["hub_port"] if pnp else None,
                    "device_path": row["device_path"]})
    return out


def dshow_formats(index: int) -> list[dict]:
    """Media type camera công bố; mỗi dòng: index, fourcc, width, height, fps_min, fps_max."""
    graph = _filter_graph()()
    graph.add_video_input_device(index)
    try:
        formats = graph.get_input_device().get_formats()
    finally:
        graph.remove_filters()
    rows = []
    for fmt in formats:
        rows.append({"index": int(fmt["index"]), "fourcc": str(fmt["media_type_str"]), "width": int(fmt["width"]),
                     "height": int(fmt["height"]), "fps_min": float(fmt.get("min_framerate", 0.0)),
                     "fps_max": float(fmt.get("max_framerate", 0.0))})
    return rows


def unique_modes(rows: list[dict]) -> list[dict]:
    """Bỏ các dòng trùng (fourcc, w, h, fps) — DirectShow hay công bố cùng một mode dưới nhiều index."""
    seen, out = set(), []
    for row in sorted(rows, key=lambda r: (r["fourcc"], -r["width"] * r["height"], -r["fps_max"])):
        key = (row["fourcc"], row["width"], row["height"], round(row["fps_min"], 3), round(row["fps_max"], 3))
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out


def write_modes_csv(path: Path, per_camera: dict[int, list[dict]], device_names: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["camera_index", "device_name", "fourcc", "width", "height", "fps_min", "fps_max"])
        for index, rows in sorted(per_camera.items()):
            name = device_names[index] if index < len(device_names) else ""
            for row in unique_modes(rows):
                writer.writerow([index, name, row["fourcc"], row["width"], row["height"], f"{row['fps_min']:g}", f"{row['fps_max']:g}"])


# ----------------------------------------------------------------------------------------------- mở camera

def open_capture(index: int, width: int | None, height: int | None, fourcc: str | None = DEFAULT_FOURCC,
                 fps: float | None = 30.0):
    """Mở camera với mode đưa vào ngay lúc mở (điều 1 ở đầu file). DirectShow trên Windows, mặc định ở nơi khác."""
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    params: list = []
    if fourcc:
        params += [cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc)]
    if width:
        params += [cv2.CAP_PROP_FRAME_WIDTH, int(width)]
    if height:
        params += [cv2.CAP_PROP_FRAME_HEIGHT, int(height)]
    if fps:
        params += [cv2.CAP_PROP_FPS, int(round(fps))]     # params chỉ nhận int; float làm VideoCapture ném lỗi
    capture = cv2.VideoCapture(index, backend, params) if params else cv2.VideoCapture(index, backend)
    if not capture.isOpened():
        raise ValueError(f"không mở được camera index {index}")
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return capture


def apply_exposure(capture, exposure: float | None) -> dict:
    """None → phơi sáng tự động; số → thủ công (DirectShow: log2 giây, -5 ≈ 1/32 s, -6 ≈ 1/64 s)."""
    if exposure is None:
        ok = bool(capture.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75))
        return {"auto": True, "set_ok": ok, "readback": capture.get(cv2.CAP_PROP_EXPOSURE)}
    ok1 = bool(capture.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25))
    ok2 = bool(capture.set(cv2.CAP_PROP_EXPOSURE, float(exposure)))
    return {"auto": False, "requested": float(exposure), "set_ok": ok1 and ok2, "readback": capture.get(cv2.CAP_PROP_EXPOSURE)}


def actual_size(capture) -> tuple[int, int]:
    return int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))


# ----------------------------------------------------------------------------------------------- đo

@dataclass
class StreamStats:
    index: int
    seconds: float
    reads: int = 0
    new_frames: int = 0
    duplicate_reads: int = 0          # read() trả về khung trùng byte với khung trước: driver không có khung mới
    read_failures: int = 0            # read() trả về False / None
    truncated_frames: int = 0         # TRONG new_frames: khung MJPEG bị cắt cụt, đáy do bộ giải mã tô (sources.truncated_rows);
                                      # vẫn tính là khung mới để số đo giai đoạn 1 (trước 23/09 chiều, chưa có cột này) so được
    torn_frames: int = 0              # TRONG new_frames, không bị cắt đáy nhưng có dải xé giữa ảnh (sources.torn_bands)
    fps_real: float = 0.0             # khung MỚI mỗi giây
    gap_ms_mean: float = 0.0          # khoảng cách trung bình giữa hai khung mới (= 1000 / fps_real khi không rớt)
    gap_ms_median: float = 0.0        # trung vị: khác trung bình nhiều tức nhịp khung không đều
    gap_ms_p95: float = 0.0
    gap_ms_max: float = 0.0
    gaps_under_40ms: int = 0          # số khoảng cách ngắn hơn 40 ms (nhịp 30 fps ≈ 33 ms; nhịp 24 fps ≈ 42 ms)
    read_ms_median: float = 0.0       # thời gian một lần read() (chặn tới khung kế + giải mã)
    read_ms_p95: float = 0.0
    mean_intensity: float | None = None
    width: int = 0
    height: int = 0
    notes: list[str] = field(default_factory=list)
    gaps_ms: list[float] = field(default_factory=list)   # từng khoảng cách (0,1 ms) để xem phân bố; ~10 KB/phút


def percentile(values, q: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(np.asarray(values, dtype=float), q))


def summarize_gaps(gaps_s: list[float], reads_s: list[float], stats: StreamStats) -> StreamStats:
    gaps = [g * 1000.0 for g in gaps_s]
    reads = [r * 1000.0 for r in reads_s]
    stats.gap_ms_mean = float(statistics.fmean(gaps)) if gaps else 0.0
    stats.gaps_ms = [round(g, 1) for g in gaps]
    stats.gaps_under_40ms = sum(1 for g in stats.gaps_ms if g < 40.0)
    stats.gap_ms_median = float(statistics.median(gaps)) if gaps else 0.0
    stats.gap_ms_p95 = percentile(gaps, 95)
    stats.gap_ms_max = max(gaps) if gaps else 0.0
    stats.read_ms_median = float(statistics.median(reads)) if reads else 0.0
    stats.read_ms_p95 = percentile(reads, 95)
    stats.fps_real = stats.new_frames / stats.seconds if stats.seconds > 0 else 0.0
    return stats


def measure_stream(capture, seconds: float, index: int = 0, clock=time.perf_counter, warmup_frames: int = 5) -> StreamStats:
    """Đọc `seconds` giây, chỉ đếm khung khác khung trước. `capture` cần read() (chặn) như cv2.VideoCapture."""
    prev = None
    for _ in range(warmup_frames):                  # bỏ vài khung đầu: phơi sáng/khuếch đại tự động đang ổn định
        ok, image = capture.read()
        if ok and image is not None:
            prev = image
    stats = StreamStats(index=index, seconds=seconds)
    gaps, reads = [], []
    t0 = clock()
    last_new = t0
    last_image = prev
    intensity_sum, intensity_n = 0.0, 0
    while True:
        now = clock()
        if now - t0 >= seconds:
            break
        t_read = clock()
        ok, image = capture.read()
        reads.append(clock() - t_read)
        stats.reads += 1
        if not ok or image is None:
            stats.read_failures += 1
            continue
        if last_image is not None and image.shape == last_image.shape and np.array_equal(image, last_image):
            stats.duplicate_reads += 1
            continue
        t_new = clock()
        stats.new_frames += 1
        if truncated_rows(image):
            stats.truncated_frames += 1
        elif torn_bands(image):
            stats.torn_frames += 1
        gaps.append(t_new - last_new)
        last_new = t_new
        last_image = image
        if stats.new_frames % 10 == 1:
            intensity_sum += float(image.mean())
            intensity_n += 1
        stats.width, stats.height = int(image.shape[1]), int(image.shape[0])
    stats.seconds = clock() - t0
    stats.mean_intensity = intensity_sum / intensity_n if intensity_n else None
    return summarize_gaps(gaps, reads, stats)


def measure_many(indices: list[int], width: int, height: int, seconds: float, fourcc: str = DEFAULT_FOURCC,
                 exposure: float | None = None, fps: float = 30.0) -> dict:
    """Mở tất cả camera trước, rồi đọc song song (mỗi camera một luồng). Kết quả có CPU của tiến trình này."""
    captures = {}
    try:
        for index in indices:
            captures[index] = open_capture(index, width, height, fourcc, fps)
        exposures = {index: apply_exposure(cap, exposure) for index, cap in captures.items()}
        sizes = {index: actual_size(cap) for index, cap in captures.items()}
        results: dict[int, StreamStats] = {}

        def run_one(i: int) -> None:
            try:
                results[i] = measure_stream(captures[i], seconds, i)
            except Exception as exc:            # luồng chết không được im lặng: ghi vào kết quả, không đoán
                stats = StreamStats(index=i, seconds=seconds)
                stats.notes.append(f"measure_stream thất bại: {exc!r}")
                results[i] = stats

        threads = [threading.Thread(target=run_one, args=(i,), name=f"cam{i}") for i in indices]
        cpu0, wall0 = time.process_time(), time.perf_counter()
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        cpu_fraction = (time.process_time() - cpu0) / max(1e-9, time.perf_counter() - wall0)
    finally:
        for cap in captures.values():
            cap.release()
    missing = [i for i in indices if i not in results]
    if missing:
        raise RuntimeError(f"thiếu kết quả đo cho camera {missing}")
    streams = [asdict(results[i]) for i in indices]
    failed = [i for i in indices if results[i].notes]
    return {"created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "opencv": cv2.__version__, "platform": sys.platform,
            "requested": {"indices": indices, "width": width, "height": height, "fourcc": fourcc, "fps": fps, "exposure": exposure},
            "actual_sizes": {str(i): sizes[i] for i in indices}, "exposure": {str(i): exposures[i] for i in indices},
            "seconds": seconds, "process_cpu_cores": round(cpu_fraction, 3), "failed_indices": failed,
            "total_fps_real": round(sum(s["fps_real"] for s in streams), 2), "streams": streams}


# ----------------------------------------------------------------------------------------------- ghi

def record(index: int, width: int, height: int, seconds: float, out_dir: Path, name: str, fourcc: str = DEFAULT_FOURCC,
           exposure: float | None = None, snapshot_every: float = 2.0, fps: float = 30.0) -> dict:
    """Ghi video AVI (MJPG) và ảnh PNG định kỳ. Trước khi ghi có 5 khung khởi động và tối đa 2 s thăm dò để chọn FPS
    của file (FPS thật làm tròn); các khung này KHÔNG nằm trong video. `seconds`/`frames_written`/`fps_real` trong json
    chỉ tính đoạn ghi. Khung cũ (read() trả lại khung trước) bị bỏ, không ghi, nên thời gian trong AVI chỉ đều khi
    duplicate_reads = 0; thời điểm thật của từng khung ghi ở `<name>.frames.csv`. Video là ảnh BGR đã giải mã rồi được
    OpenCV nén JPEG lại — kích thước file KHÔNG phải số byte camera gửi qua USB."""
    out_dir.mkdir(parents=True, exist_ok=True)
    capture = open_capture(index, width, height, fourcc, fps)
    writer = None
    try:
        exposure_info = apply_exposure(capture, exposure)
        probe = measure_stream(capture, min(2.0, seconds), index)
        if probe.new_frames == 0 or probe.width == 0 or probe.height == 0:
            raise RuntimeError(f"camera {index}: không có khung mới trong {probe.seconds:.1f} s thăm dò "
                               f"(đọc {probe.reads}, khung cũ {probe.duplicate_reads}, đọc hỏng {probe.read_failures}) — không ghi video")
        file_fps = max(1.0, float(round(probe.fps_real)))
        video_path = out_dir / f"{name}.avi"
        writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"MJPG"), file_fps, (probe.width, probe.height))
        if not writer.isOpened():
            raise RuntimeError("OpenCV không ghi được MJPG AVI trên máy này")
        snapshots = []
        frame_times: list[float] = []
        prev = None
        t0 = time.perf_counter()
        last_snapshot = -1e9
        frames = duplicates = failures = truncated = torn = 0
        while time.perf_counter() - t0 < seconds:
            ok, image = capture.read()
            t_frame = time.perf_counter() - t0
            if not ok or image is None:
                failures += 1
                continue
            if prev is not None and np.array_equal(image, prev):
                duplicates += 1
                continue
            prev = image
            if truncated_rows(image):                      # vẫn ghi vào video, chỉ đếm
                truncated += 1
            elif torn_bands(image):
                torn += 1
            writer.write(image)
            frames += 1
            frame_times.append(t_frame)
            if t_frame - last_snapshot >= snapshot_every:
                snap = out_dir / f"{name}_{t_frame:05.1f}s{SNAPSHOT_EXT}"
                imwrite(snap, image)
                snapshots.append(snap.name)
                last_snapshot = t_frame
        elapsed = time.perf_counter() - t0
    finally:
        if writer is not None:
            writer.release()
        capture.release()
    with open(out_dir / f"{name}.frames.csv", "w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows([["frame_index", "t_s"]] + [[k, f"{t:.4f}"] for k, t in enumerate(frame_times)])
    info = {"created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "camera_index": index,
            "requested": {"width": width, "height": height, "fourcc": fourcc, "fps": fps, "exposure": exposure},
            "actual": {"width": probe.width, "height": probe.height}, "exposure": exposure_info,
            "probe_seconds": round(probe.seconds, 2), "probe_new_frames": probe.new_frames,
            "probe_duplicate_reads": probe.duplicate_reads, "probe_fps_real": round(probe.fps_real, 2),
            "video": video_path.name, "video_fps": file_fps, "frame_times": f"{name}.frames.csv",
            "frames_written": frames, "truncated_frames": truncated, "torn_frames": torn, "duplicate_reads": duplicates, "read_failures": failures,
            "seconds": round(elapsed, 2), "fps_real": round(frames / elapsed, 2) if elapsed else 0.0, "snapshots": snapshots,
            "ecoqos": ecoqos_state()}       # EcoQoS của tiến trình đo lúc ghi (02/10/2026)
    (out_dir / f"{name}.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return info


# ----------------------------------------------------------------------------------------------- báo cáo

def damaged(stream: dict) -> str:
    if "truncated_frames" not in stream:
        return "chưa đo"                      # json giai đoạn 1 đo trước khi có bộ dò
    return f"{stream['truncated_frames']} / {stream.get('torn_frames', 'chưa đo')}"


def report_markdown(measurements: list[dict]) -> str:
    lines = ["| Phiên | Camera | Mode yêu cầu | Kích thước thật | FPS thật | Trong đó khung bị cắt / xé | Khung cũ trả lại | Đọc hỏng | Khoảng cách khung trung vị / p95 / max (ms) | Độ sáng TB | CPU tiến trình (lõi) |",
             "|---|---:|---|---|---:|---:|---:|---:|---|---:|---:|"]
    for m in measurements:
        req = m["requested"]
        mode = f"{req['fourcc']} {req['width']}×{req['height']}@{req['fps']:g}" + ("" if req.get("exposure") is None else f", exposure {req['exposure']:g}")
        for s in m["streams"]:
            intensity = "—" if s["mean_intensity"] is None else f"{s['mean_intensity']:.0f}"
            lines.append(f"| {m.get('name', m['created_utc'])} | {s['index']} | {mode} | {s['width']}×{s['height']} | {s['fps_real']:.1f} | "
                         f"{damaged(s)} | {s['duplicate_reads']} | {s['read_failures']} | {s['gap_ms_median']:.0f} / {s['gap_ms_p95']:.0f} / {s['gap_ms_max']:.0f} | "
                         f"{intensity} | {m['process_cpu_cores']:.2f} |")
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------------------------- CLI

def probe_traps(index: int, seconds: float = 2.0) -> dict:
    """Ghi lại ba bẫy (đầu file) thành hồ sơ trên một camera thật: tốc độ `grab()` với mode mặc định, FPS thật khi đặt
    mode SAU khi mở so với đưa vào lúc mở (720p và 1080p MJPG), và backend MSMF có mở được không."""
    out: dict = {"created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "opencv": cv2.__version__,
                 "index": index, "seconds_per_probe": seconds}
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if cap.isOpened():
        cap.read()
        n, t0 = 0, time.perf_counter()
        while time.perf_counter() - t0 < seconds:
            if cap.grab():
                n += 1
        out["grab_calls_per_s_default_mode"] = round(n / (time.perf_counter() - t0), 1)
        out["default_mode"] = {"width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}
    else:
        out["grab_calls_per_s_default_mode"] = None
    cap.release()
    for (w, h) in ((1280, 720), (1920, 1080)):
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*DEFAULT_FOURCC))
        cap.set(cv2.CAP_PROP_FPS, 30)
        code = int(cap.get(cv2.CAP_PROP_FOURCC))
        stats = measure_stream(cap, seconds, index, warmup_frames=2)
        cap.release()
        out[f"set_after_open_{w}x{h}"] = {"fps_real": round(stats.fps_real, 1), "width": stats.width, "height": stats.height,
                                          "fourcc_readback": "".join(chr((code >> (8 * i)) & 0xFF) for i in range(4))}
        cap = open_capture(index, w, h)
        code = int(cap.get(cv2.CAP_PROP_FOURCC))
        stats = measure_stream(cap, seconds, index, warmup_frames=2)
        cap.release()
        out[f"params_at_open_{w}x{h}"] = {"fps_real": round(stats.fps_real, 1), "width": stats.width, "height": stats.height,
                                          "fourcc_readback": "".join(chr((code >> (8 * i)) & 0xFF) for i in range(4))}
    cap = cv2.VideoCapture(index, cv2.CAP_MSMF)
    out["msmf_opened"] = bool(cap.isOpened())
    cap.release()
    return out


def source_smoke(index: int, width: int, height: int, frames: int, fourcc: str = DEFAULT_FOURCC,
                 exposure: float | None = None) -> dict:
    """Chạy `UsbCameraSource` (nguồn dùng trong mã vận hành) trên camera thật: mode(), cờ set(), N lần read() và stamp."""
    from autopark.video.sources import FrameReadError, UsbCameraSource
    source = UsbCameraSource(index, width=width, height=height, fps=30, fourcc=fourcc, exposure=exposure)
    info: dict = {"created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "index": index,
                  "requested": source.requested, "mode": source.mode(), "mode_mismatch": source.mode_mismatch,
                  "buffer_size_applied": source.buffer_size_applied, "exposure_applied": source.exposure_applied}
    stamps: list[float] = []
    errors: list[str] = []
    try:
        for _ in range(frames):
            try:
                stamps.append(source.read().meta.stamp.t)
            except FrameReadError as exc:
                errors.append(str(exc))
    finally:
        source.close()
    gaps = [1000.0 * (b - a) for a, b in zip(stamps, stamps[1:])]
    info.update({"frames_ok": len(stamps), "read_errors": len(errors), "read_error_samples": errors[:5],
                 "stamps_strictly_increasing": all(b > a for a, b in zip(stamps, stamps[1:])),
                 "stamp_gap_ms_mean": round(statistics.fmean(gaps), 2) if gaps else None,
                 "stamp_gap_ms_median": round(statistics.median(gaps), 2) if gaps else None,
                 "stamp_gap_ms_max": round(max(gaps), 2) if gaps else None})
    return info


def _cmd_list(args) -> int:
    print("== Windows PnP (Camera/Image) ==")
    hubs: list[dict] = []
    try:
        text = _pnp_json()
        rows, hubs = parse_pnp_json(text), parse_pnp_hubs(text)
    except RuntimeError as exc:
        rows, err = [], str(exc)
        print("  không hỏi được:", err)
    for row in rows:
        print(f"  {row['friendly_name']} | hub {row['hub'] or '-'} cổng {row['hub_port'] if row['hub_port'] is not None else '-'} | {row['instance_id']}")
    print("== Hub USB (ngoài root hub) ==")
    for hub in hubs:
        print(f"  {hub['friendly_name']} ({hub['bus_reported_desc']}) | {hub['location_info']} | {hub['instance_id']}")
    print("== DirectShow (thứ tự = index OpenCV) → cổng hub ==")
    mapping: list[dict] = []
    try:
        mapping = join_index_to_port(dshow_device_paths(), rows)
        for m in mapping:
            port = "cổng ?" if m["hub_port"] is None else f"cổng {m['hub_port']}"
            print(f"  [{m['index']}] {m['name']} → {port} | {m['instance_id'] or 'không khớp PnP'}")
    except RuntimeError as exc:
        print("  không hỏi được:", exc)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"pnp": rows, "hubs": hubs, "dshow_index_to_port": mapping,
                                        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                                       ensure_ascii=False, indent=2), encoding="utf-8")
        print("đã ghi", args.out)
    return 0


def _cmd_modes(args) -> int:
    names = dshow_devices()
    indices = args.index if args.index else list(range(len(names)))
    per_camera = {i: dshow_formats(i) for i in indices}
    for i in indices:
        print(f"[{i}] {names[i] if i < len(names) else ''}")
        for row in unique_modes(per_camera[i]):
            print(f"   {row['fourcc']} {row['width']}×{row['height']} {row['fps_min']:g}–{row['fps_max']:g} fps")
    if args.out:
        write_modes_csv(args.out, per_camera, names)
        print("đã ghi", args.out)
    return 0


def _cmd_measure(args) -> int:
    result = measure_many(args.index, args.width, args.height, args.seconds, args.fourcc, args.exposure, args.fps)
    result["name"] = args.name
    result["ecoqos"] = ecoqos_state()
    for s in result["streams"]:
        print(f"  cam {s['index']}: {s['width']}×{s['height']} {s['fps_real']:.1f} fps thật (trong đó bị cắt {s['truncated_frames']}, xé {s['torn_frames']}) | "
              f"khung cũ {s['duplicate_reads']} | "
              f"đọc hỏng {s['read_failures']} | khoảng cách {s['gap_ms_median']:.0f}/{s['gap_ms_p95']:.0f}/{s['gap_ms_max']:.0f} ms | "
              f"read() {s['read_ms_median']:.0f} ms | sáng {s['mean_intensity'] if s['mean_intensity'] is None else round(s['mean_intensity'])}")
    print(f"  tổng {result['total_fps_real']:.1f} khung/s, CPU tiến trình {result['process_cpu_cores']:.2f} lõi, "
          f"EcoQoS {result['ecoqos']}")
    for s in result["streams"]:
        for note in s["notes"]:
            print(f"  cam {s['index']} LỖI: {note}")
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        path = args.out / f"{args.name}.measure.json"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("đã ghi", path)
    return 1 if result["failed_indices"] else 0


def _cmd_record(args) -> int:
    info = record(args.index, args.width, args.height, args.seconds, args.out, args.name, args.fourcc, args.exposure,
                  args.snapshot_every, args.fps)
    print(f"  {info['video']} : {info['frames_written']} khung, {info['fps_real']} fps thật, {len(info['snapshots'])} ảnh tĩnh")
    return 0


def _cmd_traps(args) -> int:
    result = probe_traps(args.index, args.seconds)
    result["name"] = args.name
    result["ecoqos"] = ecoqos_state()
    for key, value in result.items():
        print(f"  {key}: {value}")
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        path = args.out / f"{args.name}.traps.json"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("đã ghi", path)
    return 0


def _cmd_source(args) -> int:
    result = source_smoke(args.index, args.width, args.height, args.frames, args.fourcc, args.exposure)
    result["name"] = args.name
    result["ecoqos"] = ecoqos_state()
    print(f"  mode {result['mode']} | buffer_size_applied {result['buffer_size_applied']} | exposure_applied {result['exposure_applied']}")
    print(f"  {result['frames_ok']} khung, {result['read_errors']} lỗi đọc, stamp tăng nghiêm ngặt {result['stamps_strictly_increasing']}, "
          f"khoảng cách stamp trung bình {result['stamp_gap_ms_mean']} ms, max {result['stamp_gap_ms_max']} ms")
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        path = args.out / f"{args.name}.source.json"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("đã ghi", path)
    return 0


def _cmd_report(args) -> int:
    if not args.directory.is_dir():
        raise SystemExit(f"không có thư mục {args.directory}")
    measurements = []
    for path in sorted(args.directory.glob("*.measure.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("name", path.stem.replace(".measure", ""))
        measurements.append(data)
    text = report_markdown(measurements)
    (args.directory / "report.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("list", help="thiết bị Windows và DirectShow thấy")
    p.add_argument("--out", type=Path, default=None, help="ghi json (ví dụ docs/usb_topology.json)")
    p.set_defaults(func=_cmd_list)
    p = sub.add_parser("modes", help="media type camera công bố")
    p.add_argument("--index", type=int, nargs="*", default=None)
    p.add_argument("--out", type=Path, default=None, help="csv (ví dụ docs/camera_modes.csv)")
    p.set_defaults(func=_cmd_modes)
    for name, fn in (("measure", _cmd_measure), ("record", _cmd_record)):
        p = sub.add_parser(name)
        if name == "measure":
            p.add_argument("--index", type=int, nargs="+", required=True)
        else:
            p.add_argument("--index", type=int, required=True)
        p.add_argument("--width", type=int, default=1280)
        p.add_argument("--height", type=int, default=720)
        p.add_argument("--fourcc", default=DEFAULT_FOURCC)
        p.add_argument("--fps", type=float, default=30.0)
        p.add_argument("--exposure", type=float, default=None, help="thủ công, log2 giây (-5 ≈ 1/32 s); bỏ trống = tự động")
        p.add_argument("--seconds", type=float, default=30.0)
        p.add_argument("--name", required=True)
        p.add_argument("--out", type=Path, default=None if name == "measure" else Path("runs/camera_bench"))
        if name == "record":
            p.add_argument("--snapshot-every", type=float, default=2.0)
        p.set_defaults(func=fn)
    p = sub.add_parser("traps", help="ghi hồ sơ ba bẫy OpenCV/DirectShow trên một camera (mở/đóng camera nhiều lần)")
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--seconds", type=float, default=2.0)
    p.add_argument("--name", required=True)
    p.add_argument("--out", type=Path, default=None)
    p.set_defaults(func=_cmd_traps)
    p = sub.add_parser("source", help="chạy UsbCameraSource (nguồn của mã vận hành) trên camera thật")
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--fourcc", default=DEFAULT_FOURCC)
    p.add_argument("--exposure", type=float, default=None)
    p.add_argument("--frames", type=int, default=100)
    p.add_argument("--name", required=True)
    p.add_argument("--out", type=Path, default=None)
    p.set_defaults(func=_cmd_source)
    p = sub.add_parser("report", help="gom *.measure.json thành report.md")
    p.add_argument("directory", type=Path)
    p.set_defaults(func=_cmd_report)
    return parser


def main(argv=None) -> int:
    apply_ecoqos_policy("video.camera_bench")         # trước mọi việc khác (power_throttling.py)
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
