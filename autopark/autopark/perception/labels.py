"""Gán nhãn ảnh sa bàn: kết quả AI làm nhãn nháp, người tô sửa chỗ sai, chỉ ảnh ĐÃ DUYỆT mới vào cache huấn luyện.

    python -m autopark.perception.labels import runs/rig_snapshots --project datasets/sa_ban_labels
    python -m autopark.perception.labels stats --project datasets/sa_ban_labels
    python -m autopark.perception.labels export --project datasets/sa_ban_labels --out datasets/prepared/sa_ban_v1
    python -m autopark.ui.label_app --project datasets/sa_ban_labels

Quy trình và quy tắc gán nhãn: docs/GAN_NHAN_SA_BAN.md.

**Đầu vào** là thư mục "Chụp bộ ảnh" của bàn thử (`autopark.ui.rig_app`): `cam_p<cổng>.png` (khung gốc BGR),
`prob_blocked_p<cổng>.png` (P(BLOCKED)×255, nhỏ hơn khung nhưng cùng tỉ lệ; không có nếu lúc chụp AI tắt) và
`meta.json`. Bàn thử ghi `meta.json` SAU CÙNG, nên thư mục thiếu nó là lần chụp dở dang: bỏ qua, có báo.

**Dự án gán nhãn** (mặc định `datasets/sa_ban_labels/`), mỗi ảnh một mã `<tên bộ ảnh>_p<cổng>`:

    project.json      loại dự án, ánh xạ nhãn
    images/<mã>.png   bản chép NGUYÊN BYTE của cam_p<cổng>.png (sha256 ghi trong sidecar). Chép vì runs/ không vào
                      git và có thể bị dọn; export kiểm lại sha256 nên ảnh bị đổi sẽ bị phát hiện.
    probs/<mã>.png    P(BLOCKED)×255 làm nháp: chép từ bộ ảnh, hoặc do `LiveSegmenter` sinh khi bộ ảnh không có
    labels/<mã>.png   nhãn uint8 cùng kích thước khung gốc: 0 FREE, 1 BLOCKED, 255 IGNORE
    edited/<mã>.png   1 = pixel do người tô. "Tô lại theo AI" mặc định không đè lên các pixel này
    items/<mã>.json   sidecar: trạng thái (draft / reviewed / rejected), nguồn (bộ ảnh + cổng), sha256 ảnh và nhãn,
                      mô hình + ngưỡng của nháp, kết quả dò khung hỏng, ai sửa/duyệt lúc nào, ghi chú, lịch sử

Mọi file ghi qua file tạm, `fsync` rồi `os.replace`: tiến trình chết giữa chừng không để lại file cụt, và dữ liệu đã
nằm trên đĩa trước khi đổi tên (ghi hỏng thì file tạm bị xóa). Nếu một sidecar vẫn hỏng (sửa tay, đĩa lỗi), mở dự án
báo đúng tên file và dừng, không bỏ qua ảnh đó (bỏ qua thì lần nhập sau có thể đè nhãn đã tô). Ảnh ghi bằng
`cv2.imencode` và đọc bằng `cv2.imdecode(np.fromfile(...))`: `cv2.imwrite/imread` hỏng trên đường dẫn tiếng Việt ở
Windows. Không có khóa: mỗi dự án chỉ nên mở trong MỘT cửa sổ gán nhãn một lúc.

**Nhãn nháp**: xác suất phóng về kích thước khung bằng nội suy tuyến tính (như lớp tô của bàn thử) rồi so ngưỡng,
mặc định 0,5 (argmax); bằng ngưỡng tính là BLOCKED. Xác suất lưu dạng uint8 nên nháp có thể lệch ≤ 1/510 quanh ngưỡng
so với xác suất gốc. Không có xác suất (và không cho chạy mô hình) thì nháp toàn IGNORE: người phải tô hết. Mô hình
nháp huấn luyện trên WoodScape và CHƯA TỪNG được chấm trên sa bàn: nháp là để đỡ công tô, không phải nhãn đúng.

**Khung hỏng**: chạy lại `truncated_rows`/`torn_bands` (bộ dò của nguồn camera) trên khung, cộng
`bottom_repeat_share` > 0,2 (lấy từ meta.json; bộ ảnh cũ không ghi thì tính lại trên khung — cùng hàm bàn thử dùng),
cộng khung CŨ: `age_ms` của meta.json > 2 s (camera treo, bàn thử vẫn ghi khung cuối cùng nó có).
`bottom_repeat_share` là số thô: khung sạch ≤ 0,13, đáy bị bộ giải mã tô ≈ 1, nhưng một đáy phẳng hay cháy sáng cũng
cao, nên lý do được ghi riêng để người xem lại. Khung bị đánh dấu hỏng vào dự án ở trạng thái "rejected" kèm lý do
(hoặc bỏ hẳn với `--skip-damaged`); duyệt nó phải xác nhận riêng (`override_damage`), VÀ vùng hỏng mà bộ dò định vị
được (`truncated_rows` dòng đáy, các dải xé `torn_spans`) phải đã là IGNORE — kiểm khi duyệt và kiểm lại khi export.
Lý do chỉ `bottom_repeat_share` hay chỉ khung cũ thì không định vị được vùng nào: người tự xét. Khung cũ được xếp phiên
theo GIỜ KHUNG (giờ bộ ảnh trừ `age_ms`, `source.frame_captured_local`), không theo giờ bộ ảnh.

**Duyệt** gắn với ĐÚNG nội dung nhãn lúc duyệt (sha256 của mảng nhãn). Sửa nhãn sau khi duyệt thì ảnh về "draft" và
phải duyệt lại. Nhãn toàn IGNORE không duyệt được (ảnh không dùng được thì "Loại").

**Export** chỉ lấy ảnh đã duyệt, từ chối nếu ảnh hay nhãn trên đĩa khác sha256 đã ghi (kiểm hai lần: trước khi dựng
cache, và lại trên đúng mảng được ghi — công cụ gán nhãn có thể tự lưu cùng dự án trong lúc export), và viết cache ĐÚNG
định dạng `prepare_extra.write_cache` (letterbox 512×384, phần đệm là IGNORE, ảnh RGB). Split theo PHIÊN CHỤP: mọi
camera của một bộ ảnh, và các bộ ảnh chụp cách nhau ≤ `session_gap_s` (mặc định 60 s, nối chuỗi), luôn chung một split
— khung chụp liền nhau của cùng một cảnh gần như trùng nhau, để lẫn vào train và val/test là rò rỉ. Chuỗi nối trên MỌI
bộ ảnh đã nhập (kể cả nháp, loại, và bộ ảnh bị bỏ qua lúc nhập — thời điểm của chúng ghi ở `snapshots.json`): một bộ ảnh
chưa duyệt ở giữa không được cắt đôi một phiên. Kèm phép ĐO rò rỉ bằng hash tri giác như AVM-SS.

**Split đóng băng** theo từng ảnh ở `<dự án>/splits.json` từ lần export đầu: lần sau ảnh cũ giữ split, chỉ phiên mới
được chia (cùng luật thiếu hụt của `split_groups`, tính cả phần đã có). Phiên cũ được nhận ra qua MỌI ảnh đã đóng
băng của nó, kể cả ảnh nay đã về nháp hay bị loại: ảnh mới của phiên đó theo split cũ, không bị chia lại như phiên mới.
Ảnh chỉ được dời VỀ train (khi một bộ ảnh mới nối hai phiên khác split thành một), không bao giờ ra khỏi train hay giữa
val/test — nên val ∪ test của lần sau ⊆ val ∪ test của lần trước ∪ ảnh mới, và mô hình/ngưỡng chỉnh trên cache cũ vẫn
sạch khi chấm trên cache mới. `resplit=True` (`--resplit`) chia lại từ đầu và làm mất tính so sánh đó.

**Tách hẳn khỏi cache khác** (`disjoint_from`, `--disjoint-from`): export từ chối nếu một ảnh đã duyệt trùng sha256
ảnh, trùng tên bộ ảnh, hoặc chụp cách một bản ghi của cache đó ≤ `session_gap_s` (cùng phiên, gần trùng mà sha256 không
bắt được). Dùng cho tập chấm của một dự án riêng: nó chỉ sạch khi không chung ảnh/phiên với cache huấn luyện.

`verify_cache` không áp dụng: nó so cache với split đóng băng và file gốc của WoodScape. Thay vào đó export tự kiểm cache
vừa ghi (`check_cache`) trước khi đặt vào chỗ; lỗi giữa chừng thì thư mục dở `<tên>.partial_*` bị xóa.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
import copy
from datetime import datetime, timedelta
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import traceback
from typing import Callable

import cv2
import numpy as np

from autopark.video.sources import bottom_repeat_share, torn_bands, truncated_rows

from .data import letterbox, perceptual_hashes
from .paths import PROJECT
from .prepare_extra import SPLITS, leakage_report, report, write_cache

FREE, BLOCKED, IGNORE = 0, 1, 255
CLASSES = (FREE, BLOCKED, IGNORE)
CLASS_NAMES = {FREE: "FREE", BLOCKED: "BLOCKED", IGNORE: "IGNORE"}
MAPPING = {"0": "FREE", "1": "BLOCKED", "255": "IGNORE"}
STATUSES = ("draft", "reviewed", "rejected")
STATUS_NAMES = {"draft": "nháp", "reviewed": "đã duyệt", "rejected": "loại"}
SCHEMA_VERSION = 1
PROJECT_KIND = "autopark_sa_ban_labels"
DEFAULT_PROJECT = PROJECT / "datasets/sa_ban_labels"
DEFAULT_THRESHOLD = 0.5
BOTTOM_REPEAT_LIMIT = 0.2
# Tuổi khung lúc chụp (age_ms của meta.json) quá mức này thì khung là khung CŨ (camera treo/đứng). Hai bộ ảnh thật
# 23/09 có age_ms 180–341 ms; cận trên theo mã ≈ AI_STALE_S 0,5 s của bàn thử + độ trễ suy luận. KHÔNG dùng cờ `stale`
# (> 0,5 s của bộ nhiều camera): camera khỏe trong chế độ bộ AI vẫn có thể vượt 0,5 s.
FRAME_AGE_LIMIT_MS = 2000.0
SESSION_GAP_S = 60.0
DEFAULT_SEED = 20260924
MAPPING_SHA256 = hashlib.sha256(json.dumps({"scheme": "sa_ban_labels_v1", "mapping": MAPPING},
                                           sort_keys=True).encode("utf-8")).hexdigest()
SNAPSHOT_NAME = re.compile(r"(\d{8})_(\d{6})_(\d{3})")
CAMERA_FILE = re.compile(r"^cam_p(\d+)\.png$", re.IGNORECASE)
SUBDIRS = ("images", "probs", "labels", "edited", "items")
SPLIT_FILE = "splits.json"              # split đóng băng theo mã ảnh, ở gốc dự án
SPLIT_KIND = "autopark_sa_ban_split"
SNAPSHOTS_FILE = "snapshots.json"       # thời điểm chụp của MỌI bộ ảnh đã gặp lúc nhập (kể cả bộ bị bỏ qua)
SPLIT_RULE = ("ảnh đã có split giữ nguyên; phiên bị nối chỉ được dời về train; không bao giờ ra khỏi train hay giữa "
              "val/test")


class LabelError(RuntimeError):
    """Lỗi người dùng sửa được: sai trạng thái, file lệch sha256, thiếu torch, thư mục ra đã có..."""


# ---------------------------------------------------------------- tiện ích
def now_local() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def current_user() -> str:
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 - getuser ném đủ loại lỗi khi thiếu biến môi trường
        return "không rõ"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def array_sha256(array: np.ndarray) -> str:
    """Hash NỘI DUNG mảng (kèm kiểu và kích thước), không phụ thuộc bộ mã hóa PNG của phiên bản OpenCV."""
    a = np.ascontiguousarray(array)
    digest = hashlib.sha256(f"{a.dtype.str}{a.shape}".encode("ascii"))
    digest.update(a.tobytes())
    return digest.hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Ghi bền: file tạm, `fsync` (dữ liệu nằm trên đĩa TRƯỚC khi đổi tên — NTFS ghi nhật ký cho phép đổi tên chứ
    không cho dữ liệu, nên thiếu bước này thì mất điện ngay sau khi lưu có thể để lại file rỗng), rồi `os.replace`.
    Ghi hỏng (hết chỗ, file đích chỉ-đọc/bị khóa) thì xóa file tạm rồi ném lại lỗi."""
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    try:
        with open(temporary, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _atomic_write_json(path: Path, value) -> None:
    """Như `paths.atomic_write_json` nhưng ghi bền (fsync) qua `atomic_write_bytes`; hàm của paths dùng chung với
    nhiều module khác nên không đổi ở đó."""
    atomic_write_bytes(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))


def _read_json_object(path: Path, what: str) -> dict:
    """Đọc một file JSON phải là đối tượng; hỏng (rỗng, cụt, sai UTF-8, không phải đối tượng) thì LabelError nêu đúng
    file — không để JSONDecodeError trần làm sập cả công cụ mà không biết file nào."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:          # JSONDecodeError, UnicodeDecodeError đều là ValueError
        raise LabelError(f"{what} {path} đọc không được ({error})") from error
    if not isinstance(value, dict):
        raise LabelError(f"{what} {path} không phải một đối tượng JSON")
    return value


def encode_png(array: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", array)
    if not ok:
        raise LabelError(f"Không mã hóa được PNG cho mảng {array.shape} {array.dtype}")
    return buffer.tobytes()


def read_png(path: Path, flags=cv2.IMREAD_UNCHANGED) -> np.ndarray:
    path = Path(path)
    if not path.exists():
        raise LabelError(f"Thiếu file {path}")
    image = cv2.imdecode(np.fromfile(path, np.uint8), flags)
    if image is None:
        raise LabelError(f"Không giải mã được {path}")
    return image


def pixel_counts(label: np.ndarray) -> dict:
    return {str(k): int((label == k).sum()) for k in CLASSES}


def check_label(label: np.ndarray, shape: tuple[int, int] | None = None) -> None:
    if not isinstance(label, np.ndarray) or label.dtype != np.uint8 or label.ndim != 2:
        raise LabelError("Nhãn phải là mảng uint8 hai chiều")
    if shape is not None and label.shape != tuple(shape):
        raise LabelError(f"Nhãn {label.shape} khác kích thước ảnh {tuple(shape)}")
    extra = np.setdiff1d(np.unique(label), CLASSES)
    if len(extra):
        raise LabelError(f"Nhãn có giá trị ngoài {{0, 1, 255}}: {extra[:8].tolist()}")


def _check_class(value: int) -> int:
    if int(value) not in CLASSES:
        raise ValueError(f"Lớp phải là 0 FREE, 1 BLOCKED hoặc 255 IGNORE, không phải {value}")
    return int(value)


def draft_from_prob(prob: np.ndarray, size_hw: tuple[int, int], threshold: float = DEFAULT_THRESHOLD) -> np.ndarray:
    """Nhãn nháp 0 FREE / 1 BLOCKED từ bản đồ P(BLOCKED): uint8 (×255 như ảnh chụp) hoặc float trong [0, 1].

    Phóng về (cao, rộng) = `size_hw` bằng nội suy TUYẾN TÍNH trên xác suất (như `rig_app.overlay`), rồi
    BLOCKED khi P ≥ ngưỡng (bằng ngưỡng là BLOCKED, như `evaluate --threshold`)."""
    if not 0.0 < float(threshold) < 1.0:
        raise ValueError("Ngưỡng phải nằm trong (0, 1)")
    p = prob.astype(np.float32) / 255.0 if prob.dtype == np.uint8 else prob.astype(np.float32)
    if p.ndim != 2:
        raise LabelError(f"Bản đồ xác suất phải hai chiều, đang là {p.shape}")
    h, w = int(size_hw[0]), int(size_hw[1])
    if p.shape != (h, w):
        p = cv2.resize(p, (w, h), interpolation=cv2.INTER_LINEAR)
    return (p >= float(threshold)).astype(np.uint8)


def torn_band_spans(image: np.ndarray, period: int = 8, block: int = 8,
                    exclude_bottom_rows: int = 0) -> list[list[int]]:
    """Vị trí các dải xé mà `torn_bands` đếm: mỗi dải là [dòng đầu, dòng cuối + 1, cột đầu] — hàng khối `block` dòng,
    từ cột đầu tới mép phải.

    Hàng khối nào có dải xé do CHÍNH `sources.torn_bands` quyết định (gọi trên từng hàng khối: hàm đó chỉ xét một dòng
    giữa mỗi hàng khối, độc lập với các hàng khác, nên tổng số dải bằng đúng `torn_bands` trên cả ảnh — có test). Cột
    đầu tính lại theo đúng cách `torn_bands` đo đoạn lặp chạy tới mép phải: điểm ảnh trùng điểm cách `period` cột."""
    if image.ndim < 2 or not torn_bands(image, period=period, block=block, exclude_bottom_rows=exclude_bottom_rows):
        return []
    w = image.shape[1]
    spans = []
    for b in range((image.shape[0] - exclude_bottom_rows) // block):
        y0 = b * block
        if not torn_bands(image[y0:y0 + block], period=period, block=block):
            continue
        row = image[y0 + block // 2 - 1]
        same = row[:-period] == row[period:]
        if same.ndim == 2:
            same = same.all(axis=1)
        miss = ~same[::-1]
        run = int(np.argmax(miss)) if miss.any() else len(same)
        spans.append([y0, y0 + block, max(0, w - period - run)])
    return spans


def frame_damage(image: np.ndarray, camera_meta: dict | None = None,
                 bottom_repeat_limit: float = BOTTOM_REPEAT_LIMIT,
                 frame_age_limit_ms: float = FRAME_AGE_LIMIT_MS) -> dict:
    """Khung có dấu hiệu hỏng không, và vì sao. Bốn phép thử độc lập, lý do ghi riêng từng cái:
    `truncated_rows` (đáy do bộ giải mã tô), `torn_bands` (dải xé giữa ảnh, bỏ phần đáy đã tô; vị trí ở `torn_spans`),
    `bottom_repeat_share` > `bottom_repeat_limit` (meta.json; bộ ảnh cũ không ghi thì tính lại trên chính khung), và
    khung CŨ: `age_ms` của meta.json > `frame_age_limit_ms` (bộ ảnh cũ không ghi `age_ms` thì không xét)."""
    rows = int(truncated_rows(image))
    bands = int(torn_bands(image, exclude_bottom_rows=rows))
    spans = torn_band_spans(image, exclude_bottom_rows=rows) if bands else []
    meta = camera_meta or {}
    recorded = meta.get("bottom_repeat_share")
    from_meta = isinstance(recorded, (int, float)) and not isinstance(recorded, bool)
    share = float(recorded) if from_meta else float(bottom_repeat_share(image))
    age = meta.get("age_ms")
    age_known = isinstance(age, (int, float)) and not isinstance(age, bool) and np.isfinite(age)
    reasons = []
    if rows:
        reasons.append(f"khung bị cắt: {rows}/{image.shape[0]} dòng đáy do bộ giải mã tô (truncated_rows)")
    if bands:
        reasons.append(f"{bands} hàng khối có dải xé giữa ảnh (torn_bands)")
    if share > bottom_repeat_limit:
        reasons.append(f"bottom_repeat_share {share:.2f} > {bottom_repeat_limit:.2f}: đáy lặp chu kỳ 8 điểm ảnh "
                       "(đáy bị tô ≈ 1; một đáy phẳng hay cháy sáng cũng cao — xem lại)")
    too_old = bool(age_known and age > frame_age_limit_ms)
    if too_old:
        reasons.append(f"khung cũ {age / 1000:.1f} s lúc chụp (> {frame_age_limit_ms / 1000:.1f} s, age_ms của "
                       f"meta.json; stale={meta.get('stale')}): camera treo/đứng, khung chụp TRƯỚC giờ bộ ảnh nên có "
                       "thể thuộc phiên chụp khác")
    return {"damaged": bool(reasons), "reasons": reasons, "truncated_rows": rows, "torn_bands": bands,
            "torn_spans": spans, "bottom_repeat_share": round(share, 4),
            "bottom_repeat_share_from": "meta.json" if from_meta else "tính lại trên khung",
            "bottom_repeat_limit": float(bottom_repeat_limit),
            "frame_age_ms": float(age) if age_known else None, "frame_age_limit_ms": float(frame_age_limit_ms),
            "frame_too_old": too_old}


def damage_region(damage: dict, shape, image: np.ndarray | None = None) -> np.ndarray:
    """Mặt nạ bool (cao, rộng) của vùng hỏng mà bộ dò ĐỊNH VỊ được: `truncated_rows` dòng đáy và các dải xé (từ cột
    đầu tới mép phải). Lý do chỉ `bottom_repeat_share` hay khung cũ thì không định vị được: vùng rỗng, người tự xét.
    Sidecar cũ (trước khi có `torn_spans`) có dải xé thì tính lại vị trí trên `image` — ảnh chép trong dự án."""
    h, w = int(shape[0]), int(shape[1])
    region = np.zeros((h, w), bool)
    rows = int(damage.get("truncated_rows") or 0)
    if rows:
        region[h - min(rows, h):] = True
    spans = damage.get("torn_spans")
    if spans is None and damage.get("torn_bands"):
        if image is None:
            raise LabelError("sidecar cũ không ghi vị trí dải xé (torn_spans): cần ảnh để tính lại")
        spans = torn_band_spans(image, exclude_bottom_rows=rows)
    for y0, y1, x0 in spans or ():
        region[int(y0):int(y1), int(x0):] = True
    return region


def snapshot_time(folder: Path, meta: dict) -> datetime | None:
    """Thời điểm chụp (giờ máy, không múi giờ): `created_local` của meta.json, không có thì tên thư mục."""
    created = meta.get("created_local")
    if isinstance(created, str):
        try:
            value = datetime.fromisoformat(created)
            return value.astimezone().replace(tzinfo=None) if value.tzinfo else value
        except ValueError:
            pass
    match = SNAPSHOT_NAME.search(folder.name)
    if match:
        try:
            return datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S%f")
        except ValueError:
            return None
    return None


def _parse_time(text: str | None) -> datetime | None:
    """Giờ máy không múi giờ (như `snapshot_time`), để so được với nhau; chuỗi có múi giờ thì đổi về giờ máy."""
    if not text or not isinstance(text, str):
        return None
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        return None
    return value.astimezone().replace(tzinfo=None) if value.tzinfo else value


def session_groups(times: dict[str, datetime | None], gap_s: float = SESSION_GAP_S) -> dict[str, str]:
    """Khóa bộ ảnh -> mã phiên. Hai bộ ảnh chụp cách nhau ≤ `gap_s` giây chung một phiên, NỐI CHUỖI: A–B 50 s và B–C
    50 s thì A, B, C chung phiên dù A–C 100 s. Bộ ảnh không rõ thời điểm là một phiên riêng.

    Đây là giả định bảo thủ chống rò rỉ, không phải phép đo: hai phiên khác giờ vẫn có thể chụp cùng một cảnh sa bàn,
    nên export kèm `leakage_report` (hash tri giác) để ĐO mức gần trùng còn lại."""
    known = sorted(((t, key) for key, t in times.items() if t is not None), key=lambda kv: (kv[0], kv[1]))
    out: dict[str, str] = {}
    label, last, count = None, None, 0
    for t, key in known:
        if last is None or (t - last).total_seconds() > gap_s:
            count += 1
            label = f"sa_ban/phien_{count:03d}_{Path(key).name}"
        out[key] = label
        last = t
    for key in sorted(k for k, t in times.items() if t is None):
        count += 1
        out[key] = f"sa_ban/phien_{count:03d}_{Path(key).name}_khong_ro_gio"
    return out


def split_sessions(members: dict[str, list[int]], ids: list[str], assigned: dict[str, str], seed: int,
                   ratios=(0.70, 0.15, 0.15), session_of: dict[str, str] | None = None
                   ) -> tuple[dict[str, list[int]], dict[str, str], list[str], list[dict]]:
    """Chia phiên vào train/val/test, GIỮ split đã đóng băng của lần export trước.

    `members`: phiên -> chỉ số bản ghi; `ids`: chỉ số -> mã ảnh; `assigned`: mã ảnh -> split đã đóng băng;
    `session_of`: mã ảnh -> phiên của MỌI ảnh trong dự án (không chỉ ảnh đang export). Có nó thì một phiên được nhận ra là
    phiên cũ qua mọi ảnh đã đóng băng của nó, kể cả ảnh nay đã về nháp hay bị loại — thiếu nó, phiên có mọi ảnh cũ không
    còn được duyệt bị coi là phiên mới và ảnh mới của phiên có thể rơi vào split khác ảnh cũ (rò rỉ).
    - phiên có ảnh đã có split, tất cả cùng một split: giữ split đó (ảnh mới trong phiên theo luôn);
    - phiên nối các ảnh đã có split KHÁC nhau (một bộ ảnh mới bắc cầu hai phiên cũ): cả phiên về train — chỉ được dời
      VỀ train, không bao giờ ra khỏi train hay giữa val/test;
    - phiên mới hoàn toàn: chia theo đúng luật thiếu hụt của `prepare_extra.split_groups` (phiên lớn trước, thứ tự
      hoán vị theo `seed`), có tính phần đã đóng băng. Không có gì đóng băng thì kết quả trùng `split_groups`.
    Trả (split -> chỉ số, phiên -> split, phiên mới, phiên bị dời về train)."""
    split_of: dict[str, str] = {}
    new_keys: list[str] = []
    moved: list[dict] = []
    frozen_in: dict[str, set[str]] = defaultdict(set)       # phiên -> ảnh đã đóng băng (mọi trạng thái hiện tại)
    for item_id in assigned:
        key = (session_of or {}).get(item_id)
        if key is not None:
            frozen_in[key].add(item_id)
    for key in sorted(members):
        frozen_ids = {ids[i] for i in members[key] if ids[i] in assigned} | frozen_in.get(key, set())
        old = {assigned[i] for i in frozen_ids}
        if len(old) == 1:
            split_of[key] = old.pop()
        elif old:
            split_of[key] = "train"
            moved.append({"session": key, "from": sorted(old),
                          "items": sorted(i for i in frozen_ids if assigned[i] != "train")})
        else:
            new_keys.append(key)
    total = sum(len(v) for v in members.values())
    have = [sum(len(members[k]) for k, s in split_of.items() if s == name) for name in SPLITS]
    want = [r * total for r in ratios]
    new_keys.sort(key=lambda k: (-len(members[k]), k))
    for position in np.random.default_rng(seed).permutation(len(new_keys)):
        key = new_keys[int(position)]
        target = int(np.argmin([(have[i] - want[i]) / max(1.0, want[i]) for i in range(3)]))
        split_of[key] = SPLITS[target]
        have[target] += len(members[key])
    splits = {name: sorted(i for k, s in split_of.items() if s == name for i in members[k]) for name in SPLITS}
    return splits, split_of, new_keys, moved


def find_snapshots(path) -> tuple[list[Path], list[str]]:
    """Thư mục bộ ảnh dưới `path` (hoặc chính `path` nếu nó là một bộ ảnh). Trả (bộ ảnh dùng được, lý do bỏ qua)."""
    path = Path(path)
    if not path.is_dir():
        raise LabelError(f"Không phải thư mục: {path}")

    def has_cameras(folder: Path) -> bool:
        return any(CAMERA_FILE.match(p.name) for p in folder.iterdir() if p.is_file())

    candidates = [path] if (path / "meta.json").exists() or has_cameras(path) else \
        sorted(p for p in path.iterdir() if p.is_dir())
    found, skipped = [], []
    for folder in candidates:
        if not has_cameras(folder):
            continue
        if not (folder / "meta.json").exists():
            skipped.append(f"{folder.name}: thiếu meta.json (bàn thử ghi meta sau cùng: lần chụp dở dang)")
            continue
        found.append(folder)
    return found, skipped


def load_segmenter(checkpoint, device: str | None = None):
    """`LiveSegmenter` cần torch (chỉ có trong .venv-train): nhập lười để phần còn lại chạy được trong .venv."""
    checkpoint = Path(checkpoint)
    if not checkpoint.exists():
        raise LabelError(f"Không thấy checkpoint {checkpoint}")
    try:
        from .live import LiveSegmenter
    except ImportError as error:
        raise LabelError(f"Không chạy được mô hình vì môi trường này thiếu torch ({error}). Chạy lệnh bằng "
                         ".venv-train\\Scripts\\python.exe, hoặc bỏ --model: ảnh không có xác suất sẽ có nháp toàn "
                         "IGNORE (tô tay).") from error
    return LiveSegmenter(checkpoint, device=device)


def _group_key(item: dict) -> str:
    """Khóa xếp phiên của một ảnh: thư mục bộ ảnh; riêng khung cũ (có `frame_captured_local`, camera treo lúc chụp) là
    `<thư mục>#p<cổng>` mang giờ khung, để nó nối chuỗi với phiên của lúc khung thật sự được chụp."""
    source = item["source"]
    if source.get("frame_captured_local"):
        return f"{source['snapshot_dir']}#p{source['port']}"
    return source["snapshot_dir"]


def _safe_name(folder: Path) -> str:
    base = re.sub(r"[^0-9A-Za-z_.-]+", "_", folder.name).strip("._") or "bo_anh"
    if base != folder.name:                    # tên có ký tự lạ: thêm hash đường dẫn để hai thư mục khác nhau không trùng mã
        base += "_" + sha256_bytes(str(folder.resolve()).encode("utf-8"))[:6]
    return base


# ---------------------------------------------------------------- sửa nhãn (không phụ thuộc Qt)
class LabelEditor:
    """Nhãn một ảnh đang sửa: cọ, đa giác, tô lại theo AI, hoàn tác/làm lại. Không phụ thuộc Qt: giao diện gọi vào
    đây, test gọi trực tiếp.

    Mỗi thao tác (một nét cọ từ lúc nhấn tới lúc nhả, một đa giác, một lần tô lại) là MỘT bước hoàn tác. Bộ nhớ hoàn
    tác chỉ giữ hình chữ nhật bao vùng thật sự đổi (nhãn + mặt nạ pixel đã tô), tối đa `max_undo` bước.
    `edited` = 1 ở pixel người đã tô; "tô lại theo AI" có `keep_edits` chỉ đổi pixel còn 0."""

    def __init__(self, label: np.ndarray, edited: np.ndarray | None = None, prob: np.ndarray | None = None,
                 threshold: float = DEFAULT_THRESHOLD, max_undo: int = 200):
        check_label(label)
        self.label = label.copy()
        self.edited = np.zeros_like(self.label) if edited is None else (edited != 0).astype(np.uint8)
        if self.edited.shape != self.label.shape:
            raise LabelError("Mặt nạ pixel đã tô khác kích thước nhãn")
        self.prob = prob
        self.threshold = float(threshold)
        self.max_undo = max_undo
        self.undo_stack: list[tuple] = []
        self.redo_stack: list[tuple] = []
        self.dirty = False
        self._stroke: dict | None = None

    @property
    def shape(self) -> tuple[int, int]:
        return self.label.shape

    @property
    def stroking(self) -> bool:
        return self._stroke is not None

    def _snapshot(self) -> tuple[np.ndarray, np.ndarray]:
        return self.label.copy(), self.edited.copy()

    def _record(self, before: tuple[np.ndarray, np.ndarray], threshold: tuple[float, float] | None = None) -> bool:
        old_label, old_edited = before
        changed = (old_label != self.label) | (old_edited != self.edited)
        if not changed.any():
            if threshold is not None:
                self.threshold = threshold[1]
            return False
        ys, xs = np.nonzero(changed)
        window = (slice(int(ys.min()), int(ys.max()) + 1), slice(int(xs.min()), int(xs.max()) + 1))
        self.undo_stack.append((window, old_label[window].copy(), old_edited[window].copy(),
                                self.label[window].copy(), self.edited[window].copy(), threshold))
        del self.undo_stack[:-self.max_undo]
        self.redo_stack.clear()
        self.dirty = True
        return True

    def begin_stroke(self, cls: int, radius: float) -> None:
        if self._stroke is not None:
            self.end_stroke()
        self._stroke = {"cls": _check_class(cls), "radius": max(0, int(round(radius))), "last": None,
                        "before": self._snapshot()}

    def stroke_to(self, x: float, y: float) -> None:
        """Nối nét tới pixel (x, y) (tọa độ ảnh; cột, dòng)."""
        stroke = self._stroke
        if stroke is None:
            raise RuntimeError("stroke_to trước begin_stroke")
        point = (int(round(x)), int(round(y)))
        r, last = stroke["radius"], stroke["last"]
        for target, value in ((self.label, stroke["cls"]), (self.edited, 1)):
            if last is not None and last != point:
                cv2.line(target, last, point, int(value), 2 * r + 1, cv2.LINE_8)   # LINE_8: không khử răng cưa,
            cv2.circle(target, point, r, int(value), -1, cv2.LINE_8)               # nên không sinh giá trị lai
        stroke["last"] = point

    def end_stroke(self) -> bool:
        stroke, self._stroke = self._stroke, None
        return False if stroke is None else self._record(stroke["before"])

    def paint(self, points, cls: int, radius: float) -> bool:
        """Một nét cọ qua các điểm (tọa độ ảnh)."""
        self.begin_stroke(cls, radius)
        for x, y in points:
            self.stroke_to(x, y)
        return self.end_stroke()

    def fill_polygon(self, points, cls: int) -> bool:
        cls = _check_class(cls)
        if len(points) < 3:
            raise ValueError("Đa giác cần ít nhất 3 đỉnh")
        if self._stroke is not None:
            self.end_stroke()
        before = self._snapshot()
        polygon = np.round(np.asarray(points, dtype=np.float64)).astype(np.int32).reshape(-1, 1, 2)
        cv2.fillPoly(self.label, [polygon], int(cls), cv2.LINE_8)
        cv2.fillPoly(self.edited, [polygon], 1, cv2.LINE_8)
        return self._record(before)

    def fill_mask(self, mask: np.ndarray, cls: int) -> bool:
        """Tô lớp `cls` lên mọi pixel của mặt nạ (vd. vùng hỏng bộ dò định vị được). Một bước hoàn tác; pixel được
        đánh dấu "đã tô" để "Tô lại theo AI" giữ chỗ đã tô không xóa mất."""
        cls = _check_class(cls)
        mask = np.asarray(mask, bool)
        if mask.shape != self.shape:
            raise LabelError(f"Mặt nạ {mask.shape} khác kích thước nhãn {self.shape}")
        if self._stroke is not None:
            self.end_stroke()
        before = self._snapshot()
        self.label[mask] = cls
        self.edited[mask] = 1
        return self._record(before)

    def regenerate(self, threshold: float, keep_edits: bool = True) -> int:
        """Tô lại nháp từ xác suất AI với ngưỡng mới. `keep_edits`: chỉ pixel người chưa tô; không thì cả ảnh (xóa luôn
        dấu "đã tô"). Trả số pixel nhãn đổi."""
        if self.prob is None:
            raise LabelError("Ảnh này không có xác suất AI (lúc chụp AI tắt và lúc nhập không chạy mô hình)")
        if self._stroke is not None:
            self.end_stroke()
        draft = draft_from_prob(self.prob, self.shape, threshold)
        before = self._snapshot()
        if keep_edits:
            free = self.edited == 0
            self.label[free] = draft[free]
        else:
            self.label[:] = draft
            self.edited[:] = 0
        changed = int((before[0] != self.label).sum())
        self._record(before, (self.threshold, float(threshold)))
        self.threshold = float(threshold)
        return changed

    def undo(self) -> bool:
        if self._stroke is not None:
            self.end_stroke()
        if not self.undo_stack:
            return False
        entry = self.undo_stack.pop()
        window, old_label, old_edited, _, _, threshold = entry
        self.label[window], self.edited[window] = old_label, old_edited
        if threshold is not None:
            self.threshold = threshold[0]
        self.redo_stack.append(entry)
        self.dirty = True
        return True

    def redo(self) -> bool:
        if self._stroke is not None:          # Ctrl+Y giữa nét kéo: đóng nét trước (như undo), không gộp vào bước của nét
            self.end_stroke()
        if not self.redo_stack:
            return False
        entry = self.redo_stack.pop()
        window, _, _, new_label, new_edited, threshold = entry
        self.label[window], self.edited[window] = new_label, new_edited
        if threshold is not None:
            self.threshold = threshold[1]
        self.undo_stack.append(entry)
        self.dirty = True
        return True

    def counts(self) -> dict:
        return pixel_counts(self.label)


# ---------------------------------------------------------------- dự án
class LabelProject:
    """Một thư mục dự án gán nhãn (bố cục ở docstring của module). Sidecar là nguồn sự thật; đọc hết khi mở."""

    def __init__(self, root, *, create: bool = False, who: str | None = None):
        self.root = Path(root)
        self.who = who or current_user()
        info = self.root / "project.json"
        if not info.exists():
            if not create:
                raise LabelError(f"Không thấy dự án gán nhãn ở {self.root} (thiếu project.json). Nhập ảnh trước: "
                                 f"python -m autopark.perception.labels import runs/rig_snapshots --project {self.root}")
            if self.root.exists() and any(self.root.iterdir()):     # gõ nhầm --project vào một thư mục có sẵn dữ liệu
                raise LabelError(f"{self.root} không trống và không phải dự án gán nhãn: chọn thư mục mới hoặc trống")
            self.root.mkdir(parents=True, exist_ok=True)
            _atomic_write_json(info, {
                "schema_version": SCHEMA_VERSION, "kind": PROJECT_KIND, "created_at": now_local(),
                "created_by": self.who, "mapping": MAPPING,
                "note": "Ảnh tự chụp trên sa bàn bằng bàn thử; nhãn 0 FREE / 1 BLOCKED / 255 IGNORE cùng kích thước "
                        "khung gốc. Xem docs/GAN_NHAN_SA_BAN.md."})
        self.info = _read_json_object(info, "project.json")
        if self.info.get("kind") != PROJECT_KIND:
            raise LabelError(f"{info} không phải dự án gán nhãn sa bàn")
        for sub in SUBDIRS:
            (self.root / sub).mkdir(exist_ok=True)
        self._items: dict[str, dict] = {}
        self.reload()

    # ---- đọc
    def reload(self) -> None:
        """Đọc lại mọi sidecar. Sidecar hỏng thì DỪNG, nêu đủ danh sách file hỏng một lần — không bỏ qua ảnh đó: bỏ qua
        thì lần nhập sau coi ảnh là mới và (trước bản sửa 24/09) ghi đè labels/<mã>.png đã tô."""
        items, broken = {}, []
        for path in sorted((self.root / "items").glob("*.json")):
            try:
                item = _read_json_object(path, "sidecar")
            except LabelError as error:
                broken.append(str(error))
                continue
            if not isinstance(item.get("id"), str):
                broken.append(f"sidecar {path} thiếu trường 'id'")
                continue
            items[item["id"]] = item
        if broken:
            raise LabelError(
                f"{len(broken)} sidecar hỏng, không mở dự án:\n  " + "\n  ".join(broken) +
                "\nKhôi phục file từ bản sao lưu; hoặc chuyển nó ra khỏi items/ rồi nhập lại bộ ảnh đó — ảnh nhập lại "
                "mang mã mới (hậu tố sha256) nên không đè labels/ và edited/ cũ của mã này, nhưng nét đã tô trong đó "
                "không tự chuyển sang mã mới.")
        self._items = items

    def ids(self, status: str | None = None) -> list[str]:
        """Theo thời điểm chụp rồi theo mã (cổng 1..4 của một bộ ảnh đi liền nhau)."""
        ordered = sorted(self._items.values(), key=lambda it: (it["source"].get("captured_local") or "", it["id"]))
        return [it["id"] for it in ordered if status is None or it["status"] == status]

    def item(self, item_id: str) -> dict:
        try:
            return self._items[item_id]
        except KeyError:
            raise LabelError(f"Không có ảnh {item_id} trong dự án") from None

    def path(self, item_id: str, kind: str) -> Path:
        if kind not in ("images", "probs", "labels", "edited", "items"):
            raise ValueError(kind)
        return self.root / kind / f"{item_id}.{'json' if kind == 'items' else 'png'}"

    def image(self, item_id: str) -> np.ndarray:
        return read_png(self.path(item_id, "images"), cv2.IMREAD_COLOR)

    def prob(self, item_id: str) -> np.ndarray | None:
        path = self.path(item_id, "probs")
        return read_png(path, cv2.IMREAD_UNCHANGED) if path.exists() else None

    def label(self, item_id: str) -> np.ndarray:
        label = read_png(self.path(item_id, "labels"), cv2.IMREAD_UNCHANGED)
        image = self.item(item_id)["image"]
        check_label(label, (image["height"], image["width"]))
        return label

    def edited(self, item_id: str) -> np.ndarray:
        path = self.path(item_id, "edited")
        if not path.exists():
            return np.zeros_like(self.label(item_id))
        return (read_png(path, cv2.IMREAD_UNCHANGED) != 0).astype(np.uint8)

    def editor(self, item_id: str) -> LabelEditor:
        item = self.item(item_id)
        return LabelEditor(self.label(item_id), self.edited(item_id), self.prob(item_id), item["draft"]["threshold"])

    def damage_region(self, item_id: str) -> np.ndarray:
        """Vùng hỏng bộ dò định vị được của ảnh này (xem hàm `damage_region`); rỗng nếu khung không bị đánh dấu hỏng."""
        item = self.item(item_id)
        damage, shape = item["damage"], (item["image"]["height"], item["image"]["width"])
        if not damage.get("damaged"):
            return np.zeros(shape, bool)
        need_image = damage.get("torn_spans") is None and bool(damage.get("torn_bands"))
        return damage_region(damage, shape, self.image(item_id) if need_image else None)

    def damage_left(self, item_id: str, label: np.ndarray) -> tuple[int, np.ndarray]:
        """(số pixel trong vùng hỏng định vị được mà `label` chưa là IGNORE, vùng hỏng)."""
        region = self.damage_region(item_id)
        return int((label[region] != IGNORE).sum()), region

    # ---- ghi
    def _write_item(self, item: dict) -> None:
        _atomic_write_json(self.path(item["id"], "items"), item)
        self._items[item["id"]] = item

    def _event(self, item: dict, action: str, **extra) -> dict:
        event = {"at": now_local(), "by": self.who, "action": action, **extra}
        item.setdefault("history", []).append(event)
        return event

    def save(self, item_id: str, label: np.ndarray, edited: np.ndarray | None = None, *, notes: str | None = None,
             draft_threshold: float | None = None, action: str = "sửa nhãn") -> bool:
        """Ghi nhãn (và mặt nạ đã tô, ghi chú, ngưỡng nháp) nếu có gì khác trên đĩa. Trả True nếu đã ghi.

        Sidecar LỆCH với nhãn trên đĩa (file nhãn bị sửa ngoài công cụ, hoặc lần ghi trước bị ngắt giữa file nhãn và
        sidecar) cũng là việc phải ghi: sidecar được đồng bộ lại theo đúng nhãn đang lưu, có ghi lịch sử — nên lời
        khuyên "mở lại ảnh và lưu" của `set_status` thật sự gỡ được tình trạng đó.
        Nhãn được ghi khác nhãn lúc duyệt thì ảnh đã duyệt về "draft": lần duyệt cũ không còn ứng với nội dung này."""
        item = copy.deepcopy(self.item(item_id))
        shape = (item["image"]["height"], item["image"]["width"])
        check_label(label, shape)
        edited = np.zeros(shape, np.uint8) if edited is None else (np.asarray(edited) != 0).astype(np.uint8)
        if edited.shape != shape:
            raise LabelError("Mặt nạ pixel đã tô khác kích thước ảnh")
        old_label, old_edited = self.label(item_id), self.edited(item_id)
        disk_sha = array_sha256(old_label)
        stale = disk_sha != item["label"]["sha256"]
        label_changed = not np.array_equal(old_label, label)
        edited_changed = not np.array_equal(old_edited, edited)
        notes_changed = notes is not None and notes != item.get("notes", "")
        threshold_changed = draft_threshold is not None and float(draft_threshold) != item["draft"]["threshold"]
        if not (label_changed or edited_changed or notes_changed or threshold_changed or stale):
            return False
        if label_changed or edited_changed or stale:
            if label_changed or edited_changed:
                atomic_write_bytes(self.path(item_id, "labels"), encode_png(label))
                atomic_write_bytes(self.path(item_id, "edited"), encode_png(edited))
            new_sha = array_sha256(label)
            if stale:
                self._event(item, "đồng bộ lại sidecar", sidecar_sha256=item["label"]["sha256"], disk_sha256=disk_sha)
            item["label"].update({"sha256": new_sha, "pixels": pixel_counts(label),
                                  "edited_fraction": round(float(edited.mean()), 6)})
            if label_changed or edited_changed:
                item["edited_at"], item["edited_by"] = now_local(), self.who
                self._event(item, action, changed_pixels=int((old_label != label).sum()))
            # về nháp khi nhãn được ghi KHÁC nội dung đã duyệt: sửa thường, hoặc file nhãn bị đổi ngoài công cụ
            if item["status"] == "reviewed" and new_sha != item.get("reviewed_label_sha256"):
                item["status"], item["status_reason"] = "draft", "nhãn khác lúc duyệt: duyệt lại"
                item["reviewed_label_sha256"] = None
                self._event(item, "về nháp (sửa sau khi duyệt)")
        if notes_changed:
            item["notes"] = notes
            self._event(item, "sửa ghi chú")
        if threshold_changed:
            item["draft"]["threshold"] = float(draft_threshold)
            self._event(item, "đổi ngưỡng nháp", threshold=float(draft_threshold))
        self._write_item(item)
        return True

    def set_status(self, item_id: str, status: str, *, reason: str | None = None,
                   override_damage: bool = False) -> dict:
        """Đổi trạng thái. "reviewed" chốt sha256 của nhãn ĐANG Ở TRÊN ĐĨA (lưu trước khi duyệt)."""
        if status not in STATUSES:
            raise ValueError(f"Trạng thái phải là một trong {STATUSES}")
        item = copy.deepcopy(self.item(item_id))
        when = now_local()
        if status == "reviewed":
            label = self.label(item_id)
            sha = array_sha256(label)
            if sha != item["label"]["sha256"]:
                raise LabelError(f"{item_id}: nhãn trên đĩa khác sha256 trong sidecar (file bị sửa ngoài công cụ, hoặc "
                                 "lần ghi trước bị ngắt). Mở lại ảnh trong công cụ và lưu trước khi duyệt.")
            if (label == IGNORE).all():
                raise LabelError(f"{item_id}: nhãn toàn IGNORE, không có gì để học. Tô nhãn, hoặc dùng 'Loại' nếu ảnh "
                                 "không dùng được.")
            if item["damage"]["damaged"]:
                if not override_damage:
                    raise LabelError(f"{item_id}: khung bị đánh dấu hỏng ({'; '.join(item['damage']['reasons'])}). "
                                     "Chỉ duyệt khi đã xem kỹ và tô IGNORE mọi vùng hỏng (xác nhận riêng).")
                # bất biến giữ ở đây (và kiểm lại khi export), không ở giao diện: vùng hỏng bộ dò định vị được phải là
                # IGNORE — nháp AI gọi vân khối do bộ giải mã tô là FREE, duyệt nguyên nháp là dạy "vân xám = FREE"
                left, region = self.damage_left(item_id, label)
                if left:
                    damage = item["damage"]
                    raise LabelError(
                        f"{item_id}: {left} pixel trong vùng hỏng bộ dò định vị được ({damage.get('truncated_rows', 0)} "
                        f"dòng đáy, {damage.get('torn_bands', 0)} dải xé) chưa là IGNORE. Tô IGNORE vùng đó (nút 'Tô "
                        "IGNORE vùng hỏng') rồi duyệt.")
                item["damage_override"] = {"at": when, "by": self.who, "damage_region_pixels": int(region.sum())}
            item["reviewed_at"], item["reviewed_by"], item["reviewed_label_sha256"] = when, self.who, sha
        else:
            item["reviewed_label_sha256"] = None
        item["status"], item["status_reason"] = status, reason
        self._event(item, f"trạng thái: {status}", **({"reason": reason} if reason else {}))
        self._write_item(item)
        return item

    # ---- nhập
    def import_snapshots(self, sources, *, threshold: float = DEFAULT_THRESHOLD,
                         make_segmenter: Callable[[], object] | None = None, skip_damaged: bool = False,
                         draft: bool = True, bottom_repeat_limit: float = BOTTOM_REPEAT_LIMIT,
                         frame_age_limit_ms: float = FRAME_AGE_LIMIT_MS, log=print) -> dict:
        """Nhập các bộ ảnh (thư mục gốc chứa nhiều bộ, hoặc một bộ). Nhập lại là an toàn: ảnh trùng sha256 bỏ qua.

        `make_segmenter`: hàm không đối số trả một đối tượng có `infer([ảnh BGR]) -> ([P(BLOCKED) float], _)` (như
        `LiveSegmenter`); chỉ gọi khi gặp ảnh không có xác suất. `draft=False`: không dùng AI (không chép xác suất,
        nháp toàn IGNORE) — cho bộ nhãn không dính tới mô hình huấn luyện trên WoodScape. `frame_age_limit_ms`: khung có
        `age_ms` lớn hơn là khung cũ (camera treo) — đánh dấu hỏng, và giờ khung được ghi riêng để xếp đúng phiên."""
        if not 0.0 < float(threshold) < 1.0:
            raise ValueError("Ngưỡng phải nằm trong (0, 1)")
        if not float(frame_age_limit_ms) > 0.0:
            raise ValueError("Giới hạn tuổi khung phải > 0 ms")
        if isinstance(sources, (str, Path)):
            sources = [sources]
        summary = {"imported": [], "rejected_damaged": [], "skipped": [], "prob_from_model": [], "no_prob": []}
        folders = []
        for source in sources:
            found, skipped = find_snapshots(source)
            folders += found
            summary["skipped"] += skipped
        seen: dict[str, dict] = {}
        try:
            self._import_folders(folders, summary, seen, threshold, make_segmenter, skip_damaged, draft,
                                 bottom_repeat_limit, float(frame_age_limit_ms), log)
        finally:                          # ghi cả khi nhập dở: bộ ảnh đã gặp vẫn được nối chuỗi phiên
            self._remember_snapshots(seen)
        return summary

    def _import_folders(self, folders, summary, seen, threshold, make_segmenter, skip_damaged, draft,
                        bottom_repeat_limit, frame_age_limit_ms, log) -> None:
        by_sha = {it["image"]["sha256"]: it["id"] for it in self._items.values()}
        segmenter = None
        for folder in folders:
            try:
                meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                summary["skipped"].append(f"{folder.name}: meta.json đọc không được ({error})")
                continue
            failed = set(meta.get("failed_writes") or [])
            captured = snapshot_time(folder, meta)
            # thời điểm của MỌI bộ ảnh đọc được meta, kể cả bộ mà mọi khung bị bỏ (--skip-damaged, trùng, lỗi ghi):
            # nó vẫn là một lần chụp trong phiên và phải nối được chuỗi phiên (_session_map)
            seen[str(folder.resolve())] = {
                "snapshot": folder.name,
                "captured_local": captured.isoformat(timespec="milliseconds") if captured else None}
            cameras = sorted(((int(m.group(1)), p) for p in folder.iterdir()
                              if p.is_file() and (m := CAMERA_FILE.match(p.name))), key=lambda kv: kv[0])
            for port, cam_path in cameras:
                where = f"{folder.name}/{cam_path.name}"
                if cam_path.name in failed:
                    summary["skipped"].append(f"{where}: bàn thử ghi lỗi file này (failed_writes)")
                    continue
                raw = cam_path.read_bytes()
                sha = sha256_bytes(raw)
                if sha in by_sha:
                    summary["skipped"].append(f"{where}: đã có trong dự án ({by_sha[sha]})")
                    continue
                image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
                if image is None:
                    summary["skipped"].append(f"{where}: không giải mã được")
                    continue
                cam_meta = (meta.get("cameras") or {}).get(str(port)) or {}
                damage = frame_damage(image, cam_meta, bottom_repeat_limit, frame_age_limit_ms)
                if damage["damaged"] and skip_damaged:
                    summary["skipped"].append(f"{where}: khung hỏng ({'; '.join(damage['reasons'])})")
                    continue
                item_id = f"{_safe_name(folder)}_p{port}"
                # cùng tên bộ ảnh nhưng ảnh khác, hoặc file của mã này còn trên đĩa mà sidecar đã mất: không đè
                if item_id in self._items or self.path(item_id, "images").exists() or \
                        self.path(item_id, "labels").exists():
                    item_id = f"{item_id}_{sha[:8]}"
                # khung cũ: giờ KHUNG = giờ bộ ảnh − tuổi khung; phiên xếp theo giờ này (_group_key), không theo bộ ảnh
                frame_time = None
                if damage["frame_too_old"] and captured is not None:
                    frame_time = (captured - timedelta(milliseconds=damage["frame_age_ms"])).isoformat(
                        timespec="milliseconds")
                h, w = image.shape[:2]
                prob, origin, model, checkpoint, note = None, "none", None, None, None
                prob_path = folder / f"prob_blocked_p{port}.png"
                if draft and prob_path.exists() and prob_path.name not in failed:
                    candidate = cv2.imdecode(np.fromfile(prob_path, np.uint8), cv2.IMREAD_UNCHANGED)
                    if candidate is None or candidate.ndim != 2 or candidate.dtype != np.uint8:
                        note = f"{prob_path.name} không phải ảnh xám uint8: bỏ, không dùng làm nháp"
                    elif abs(candidate.shape[1] / candidate.shape[0] - w / h) > 0.02 * (w / h):
                        note = f"{prob_path.name} {candidate.shape[1]}×{candidate.shape[0]} khác tỉ lệ khung {w}×{h}: bỏ"
                    else:
                        prob, origin = candidate, "snapshot_prob"
                        model, checkpoint = meta.get("model"), meta.get("checkpoint")
                if draft and prob is None and make_segmenter is not None:
                    if segmenter is None:
                        segmenter = make_segmenter()
                    probs, _ = segmenter.infer([image])
                    prob = np.round(np.clip(np.asarray(probs[0], np.float32), 0.0, 1.0) * 255).astype(np.uint8)
                    origin = "live_segmenter"
                    model = getattr(segmenter, "name", None)
                    checkpoint = str(getattr(segmenter, "checkpoint", "")) or None
                    summary["prob_from_model"].append(item_id)
                if prob is None:
                    summary["no_prob"].append(item_id)
                label = draft_from_prob(prob, (h, w), threshold) if prob is not None else np.full((h, w), IGNORE, np.uint8)
                edited = np.zeros((h, w), np.uint8)
                atomic_write_bytes(self.path(item_id, "images"), raw)
                if prob is not None:
                    atomic_write_bytes(self.path(item_id, "probs"), encode_png(prob))
                atomic_write_bytes(self.path(item_id, "labels"), encode_png(label))
                atomic_write_bytes(self.path(item_id, "edited"), encode_png(edited))
                when = now_local()
                status = "rejected" if damage["damaged"] else "draft"
                item = {
                    "schema_version": SCHEMA_VERSION, "id": item_id, "status": status,
                    "status_reason": ("khung hỏng: " + "; ".join(damage["reasons"])) if damage["damaged"] else None,
                    "source": {"snapshot_dir": str(folder.resolve()), "snapshot": folder.name, "port": port,
                               "file": cam_path.name,
                               "captured_local": captured.isoformat(timespec="milliseconds") if captured else None,
                               **({"frame_captured_local": frame_time} if frame_time else {}),
                               "snapshot_source": meta.get("source"), "camera_mode": meta.get("camera_mode"),
                               "camera": cam_meta, "capture_display_threshold": meta.get("threshold"),
                               "ai_note": meta.get("ai_note")},
                    "image": {"file": f"images/{item_id}.png", "sha256": sha, "width": w, "height": h},
                    "draft": {"origin": origin, "model": model, "checkpoint": checkpoint, "threshold": float(threshold),
                              "prob_file": f"probs/{item_id}.png" if prob is not None else None,
                              "prob_size": [int(prob.shape[1]), int(prob.shape[0])] if prob is not None else None,
                              "note": note},
                    "damage": damage, "damage_override": None,
                    "label": {"file": f"labels/{item_id}.png", "edited_file": f"edited/{item_id}.png",
                              "sha256": array_sha256(label), "pixels": pixel_counts(label), "edited_fraction": 0.0},
                    "created_at": when, "created_by": self.who, "edited_at": None, "edited_by": None,
                    "reviewed_at": None, "reviewed_by": None, "reviewed_label_sha256": None, "notes": "",
                    "history": [{"at": when, "by": self.who, "action": "nhập", "draft_origin": origin}],
                }
                self._write_item(item)
                by_sha[sha] = item_id
                summary["imported"].append(item_id)
                if damage["damaged"]:
                    summary["rejected_damaged"].append(item_id)
                if log:
                    log(f"  {item_id}: {STATUS_NAMES[status]}, nháp {origin}"
                        + (f" — {item['status_reason']}" if damage["damaged"] else ""))

    # ---- phiên chụp và split đóng băng
    def known_snapshots(self) -> dict[str, dict]:
        """Bộ ảnh đã gặp lúc nhập (thư mục -> {snapshot, captured_local}), kể cả bộ không có ảnh nào vào dự án."""
        path = self.root / SNAPSHOTS_FILE
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise LabelError(f"{path} đọc không được ({error})") from error
        return dict(value.get("snapshots") or {})

    def _remember_snapshots(self, seen: dict[str, dict]) -> None:
        if not seen:
            return
        known = self.known_snapshots()
        if all(known.get(k) == v for k, v in seen.items()):
            return
        known.update(seen)
        _atomic_write_json(self.root / SNAPSHOTS_FILE, {
            "kind": "autopark_sa_ban_snapshots", "version": 1,
            "note": "thời điểm chụp của mọi bộ ảnh đã gặp lúc nhập, kể cả bộ bị bỏ qua: dùng để nối chuỗi phiên chụp",
            "snapshots": dict(sorted(known.items()))})

    def _session_map(self, session_gap_s: float) -> dict[str, str]:
        """Bộ ảnh -> phiên, nối chuỗi trên MỌI bộ ảnh đã nhập (kể cả nháp/loại) và mọi bộ ảnh đã gặp lúc nhập mà không
        có ảnh nào vào dự án: một bộ ảnh chưa duyệt, bị loại hay bị bỏ qua ở giữa không được cắt đôi một phiên chụp liên
        tục. `statistics` và `export` dùng chung hàm này nên hai con số phiên không thể lệch nhau.
        Khóa là `_group_key(ảnh)`: thư mục bộ ảnh, riêng khung cũ (camera treo) là khóa riêng mang GIỜ KHUNG."""
        times = {folder: _parse_time(v.get("captured_local")) for folder, v in self.known_snapshots().items()}
        for it in self._items.values():
            times[it["source"]["snapshot_dir"]] = _parse_time(it["source"].get("captured_local"))
            if it["source"].get("frame_captured_local"):
                times[_group_key(it)] = _parse_time(it["source"]["frame_captured_local"])
        return session_groups(times, session_gap_s)

    def split_state(self) -> dict:
        """Nội dung `splits.json` ({} nếu dự án chưa export lần nào)."""
        path = self.root / SPLIT_FILE
        if not path.exists():
            return {}
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise LabelError(f"{path} đọc không được ({error}). Không tự chia lại: sửa file, hoặc --resplit.") from error
        assigned = state.get("assigned") if isinstance(state, dict) else None
        bad = {v for v in assigned.values() if v not in SPLITS} if isinstance(assigned, dict) else set()
        if not isinstance(assigned, dict) or state.get("kind") != SPLIT_KIND or bad:
            raise LabelError(f"{path} không phải file split của dự án gán nhãn sa bàn"
                             + (f" (split lạ: {sorted(bad)})" if bad else ""))
        return state

    # ---- thống kê
    def statistics(self, session_gap_s: float = SESSION_GAP_S) -> dict:
        items = [self.item(i) for i in self.ids()]
        by_port: dict[str, Counter] = defaultdict(Counter)
        for it in items:
            by_port[str(it["source"]["port"])][it["status"]] += 1
        reviewed = [it for it in items if it["status"] == "reviewed"]
        sessions = self._session_map(session_gap_s)
        snapshots = {it["source"]["snapshot_dir"] for it in items}
        item_sessions = {sessions[_group_key(it)] for it in items}
        frozen = self.split_state()
        pixels = Counter()
        agree = valid = missed = false_alarm = blocked = free = compared = 0
        for it in reviewed:
            pixels.update({k: int(v) for k, v in it["label"]["pixels"].items()})
            prob = self.prob(it["id"])
            if prob is None:
                continue
            label = self.label(it["id"])
            draft = draft_from_prob(prob, label.shape, it["draft"]["threshold"])
            known = label != IGNORE
            compared += 1
            valid += int(known.sum())
            agree += int((draft[known] == label[known]).sum())
            missed += int(((label == BLOCKED) & (draft == FREE)).sum())
            false_alarm += int(((label == FREE) & (draft == BLOCKED)).sum())
            blocked += int((label == BLOCKED).sum())
            free += int((label == FREE).sum())
        total_pixels = sum(pixels.values()) or 1
        edited = [float(it["label"].get("edited_fraction", 0.0)) for it in reviewed]
        return {
            "items": len(items), "by_status": {s: sum(it["status"] == s for it in items) for s in STATUSES},
            "by_port": {port: dict(counter) for port, counter in sorted(by_port.items())},
            "snapshots": len(snapshots), "sessions": len(item_sessions),
            "reviewed_sessions": len({sessions[_group_key(it)] for it in reviewed}),
            "frozen_split": ({"file": SPLIT_FILE, "items": len(frozen["assigned"]),
                              "by_split": dict(Counter(frozen["assigned"].values())), "seed": frozen.get("seed"),
                              "ratios": frozen.get("ratios"), "session_gap_s": frozen.get("session_gap_s")}
                             if frozen else None),
            "damaged": sum(bool(it["damage"]["damaged"]) for it in items),
            "draft_origin": dict(Counter(it["draft"]["origin"] for it in items)),
            "reviewed_pixels": dict(pixels), "reviewed_share": {k: v / total_pixels for k, v in pixels.items()},
            "reviewed_edited_fraction": {"mean": float(np.mean(edited)) if edited else None,
                                         "median": float(np.median(edited)) if edited else None},
            "draft_vs_reviewed": {
                "items": compared, "valid_pixels": valid, "agreement": agree / valid if valid else None,
                "blocked_drafted_as_free": missed / blocked if blocked else None,
                "free_drafted_as_blocked": false_alarm / free if free else None,
                "note": "KHÔNG phải phép chấm mô hình: người sửa bắt đầu từ chính nháp này nên có thiên lệch neo "
                        "(chỗ không chắc thường giữ nguyên nháp) — con số lạc quan về phía mô hình."},
            "session_gap_s": session_gap_s,
        }

    # ---- export
    def export(self, out, *, seed: int = DEFAULT_SEED, session_gap_s: float = SESSION_GAP_S,
               ratios=(0.70, 0.15, 0.15), height: int = 384, width: int = 512, overwrite: bool = False,
               resplit: bool = False, disjoint_from=(), log=print) -> dict:
        """Ảnh ĐÃ DUYỆT -> cache huấn luyện ở `out`. Split giữ theo `splits.json` của dự án (docstring module);
        `resplit=True` chia lại từ đầu. `splits.json` chỉ được ghi SAU KHI cache đã vào chỗ: export hỏng không đóng
        băng gì, và thư mục dở `<tên>.partial_*` của chính lượt này bị xóa.

        `disjoint_from`: các cache (thư mục hoặc manifest.json) mà cache này phải tách rời — vd. tập chấm của một dự án
        riêng so với cache huấn luyện. Ảnh đã duyệt trùng sha256, trùng bộ ảnh, hoặc chụp cách một bản ghi của cache đó
        ≤ `session_gap_s` thì từ chối export."""
        out = Path(out)
        if out.exists() and not out.is_dir():
            raise LabelError(f"{out} đã có và không phải thư mục")
        if out.exists() and any(out.iterdir()) and not overwrite:
            raise LabelError(f"{out} đã có dữ liệu. Chọn tên mới (vd. sa_ban_v2) — cache cũ có thể đang được một lượt "
                             "huấn luyện dùng — hoặc --overwrite (thư mục cũ được ĐỔI TÊN sang bên, không xóa).")
        ratios = tuple(float(r) for r in ratios)
        if len(ratios) != 3 or min(ratios) < 0 or abs(sum(ratios) - 1.0) > 1e-6:
            raise LabelError("Tỉ lệ train/val/test phải là ba số không âm, tổng 1")
        reviewed = [self.item(i) for i in self.ids("reviewed")]
        if not reviewed:
            raise LabelError("Chưa có ảnh nào ở trạng thái 'đã duyệt'. Export chỉ lấy ảnh đã duyệt (nháp chưa sửa là "
                             "nhãn của mô hình WoodScape, không phải nhãn người).")
        problems = []
        for it in reviewed:
            if sha256_bytes(self.path(it["id"], "images").read_bytes()) != it["image"]["sha256"]:
                problems.append(f"{it['id']}: ảnh trong dự án khác sha256 lúc nhập")
            label = self.label(it["id"])
            if array_sha256(label) != it.get("reviewed_label_sha256"):
                problems.append(f"{it['id']}: nhãn trên đĩa khác nhãn lúc duyệt — duyệt lại")
            elif it["damage"]["damaged"]:              # bắt cả ảnh đã duyệt trước khi set_status kiểm điều này
                left, _ = self.damage_left(it["id"], label)
                if left:
                    problems.append(f"{it['id']}: {left} pixel trong vùng hỏng bộ dò định vị được chưa là IGNORE — tô "
                                    "rồi duyệt lại")
        if problems:
            raise LabelError("Không export:\n  " + "\n  ".join(problems))
        disjoint = [self._check_disjoint(source, reviewed, session_gap_s) for source in (disjoint_from or ())]

        frozen = self.split_state()
        params = {"seed": int(seed), "ratios": list(ratios), "session_gap_s": float(session_gap_s)}
        if frozen and not resplit:
            old = {key: frozen.get(key) for key in params}
            if old != params:
                raise LabelError(
                    f"Split của dự án đã đóng băng ở {self.root / SPLIT_FILE} với seed {old['seed']}, tỉ lệ "
                    f"{old['ratios']}, khoảng phiên {old['session_gap_s']} s; lần này là seed {params['seed']}, tỉ lệ "
                    f"{params['ratios']}, khoảng phiên {params['session_gap_s']} s. Bỏ các tham số đó để giữ split cũ, "
                    "hoặc --resplit nếu thật sự muốn chia lại (cache mới KHÔNG so được với cache cũ: ảnh val/test cũ có "
                    "thể vào train).")
        assigned = {} if resplit else dict(frozen.get("assigned") or {})
        sessions = self._session_map(session_gap_s)
        members: dict[str, list[int]] = defaultdict(list)
        for index, it in enumerate(reviewed):
            members[sessions[_group_key(it)]].append(index)
        keys = sorted(members)
        # phiên của MỌI ảnh trong dự án: phiên cũ nhận ra qua cả ảnh đã đóng băng mà nay là nháp/loại
        session_of = {it["id"]: sessions[_group_key(it)] for it in self._items.values()}
        splits, _, new_keys, moved = split_sessions(dict(members), [it["id"] for it in reviewed], assigned, seed,
                                                    ratios, session_of=session_of)

        warnings = [f"split {name} rỗng: cần thêm phiên chụp đã duyệt (hiện {len(keys)} phiên)"
                    for name, ratio in zip(SPLITS, ratios) if ratio > 0 and not splits[name]]
        for m in moved:
            warnings.append(f"phiên {m['session']} nối các ảnh đã có split khác nhau ({', '.join(m['from'])}): cả phiên "
                            f"dời về train, {len(m['items'])} ảnh val/test cũ vào train ({', '.join(m['items'])}). Mô "
                            "hình huấn luyện trên cache này đã thấy các ảnh đó: đừng chấm nó trên val/test của cache cũ.")
        for d in disjoint:
            if d["unchecked_time"]:
                warnings.append(f"--disjoint-from {d['manifest']}: {d['unchecked_time']} ảnh (của cache này hoặc cache "
                                "đó) không rõ giờ chụp nên không kiểm được khoảng phiên, chỉ kiểm sha256 và tên bộ ảnh")
        origins = Counter(it["draft"]["origin"] for it in reviewed)
        grouping = {"unit": "phiên chụp", "session_gap_s": session_gap_s, "sessions": len(keys),
                    "rule": ("mọi camera của một bộ ảnh, và các bộ ảnh chụp cách nhau ≤ session_gap_s (nối chuỗi trên "
                             "MỌI bộ ảnh đã nhập, kể cả nháp/loại/bị bỏ qua), chung một nhóm; cả nhóm vào cùng một split"),
                    "session_sizes": {key: len(members[key]) for key in keys},
                    "split_assignment": {"file": SPLIT_FILE, "resplit": bool(resplit),
                                         "frozen_items_before": len(assigned),
                                         "inherited_sessions": len(keys) - len(new_keys),
                                         "new_sessions": len(new_keys), "moved_to_train": moved, "rule": SPLIT_RULE}}
        manifest_extra = {
            "seed": seed, "source": "sa_ban (ảnh tự chụp bằng bàn thử, nhãn người duyệt trong autopark.perception.labels)",
            "mapping": MAPPING, "grouping": grouping, "ratios": list(ratios),
            "self_captured": True, "contains_woodscape_images": False,
            "licence_note": ("Ảnh tự chụp trên sa bàn, KHÔNG chứa ảnh WoodScape. Nhãn là nhãn người duyệt; "
                             f"{origins.get('snapshot_prob', 0) + origins.get('live_segmenter', 0)}/{len(reviewed)} "
                             "ảnh có nhãn NHÁP sinh bởi mô hình (xem records[].draft.model; mô hình tham chiếu huấn luyện "
                             "trên WoodScape). Nhãn dẫn xuất từ đầu ra mô hình có chịu điều khoản WoodScape hay không "
                             "CHƯA được đánh giá — xem docs/GIAY_PHEP_DU_LIEU.md và docs/GAN_NHAN_SA_BAN.md."),
            "draft_origins": dict(origins),
            "review_policy": "chỉ ảnh status=reviewed, nhãn trùng sha256 lúc duyệt (kiểm lại trên đúng mảng được ghi)",
            "split_verification": ("check_cache của autopark.perception.labels (kích thước/kiểu mảng, giá trị nhãn, "
                                   "đếm lại pixel, split phủ đúng một lần, nhóm không vắt qua hai split). "
                                   "verify_cache KHÔNG áp dụng: nó chỉ dành cho WoodScape (split đóng băng + file gốc)."),
            "project": str(self.root.resolve()), "exported_at": now_local(), "exported_by": self.who,
            "warnings": list(warnings),
        }
        if disjoint:
            manifest_extra["disjoint_from"] = disjoint

        partial = out.with_name(f"{out.name}.partial_{os.getpid()}_{time.time_ns()}")
        partial.mkdir(parents=True)
        log(f"Export {len(reviewed)} ảnh đã duyệt, {len(keys)} phiên chụp ({len(new_keys)} phiên mới được chia, "
            f"{len(keys) - len(new_keys)} phiên giữ split đóng băng), letterbox về {height}x{width} -> {partial.name}")
        try:
            statistics, check, aside = self._build_and_swap(out, partial, reviewed, sessions, splits, manifest_extra,
                                                            height, width)
        except BaseException as error:
            # frame đã chạy xong trong traceback vẫn giữ memmap: Windows không xóa được file đang mở
            traceback.clear_frames(error.__traceback__)
            shutil.rmtree(partial, ignore_errors=True)            # chỉ thư mục tạm do chính lượt export này tạo
            if partial.exists():
                log(f"CẢNH BÁO: không xóa được thư mục dở {partial} — xóa tay")
            raise
        if aside is not None:
            log(f"Thư mục cũ đổi tên thành {aside.name} (không xóa)")
        failed = self._freeze_splits(frozen, assigned, reviewed, splits, params, out, new_keys, moved, resplit)
        if failed:
            warnings.append(failed)
        report(statistics, {"phiên": len(keys), "nguồn nháp": dict(origins)})
        for warning in warnings:
            log(f"CẢNH BÁO: {warning}")
        return {"out": str(out), "images": len(reviewed), "sessions": len(keys),
                "splits": {name: len(splits[name]) for name in SPLITS}, "statistics": statistics,
                "warnings": warnings, "check": check, "new_sessions": len(new_keys), "moved_to_train": moved,
                "disjoint_from": disjoint}

    def _check_disjoint(self, source, reviewed: list[dict], session_gap_s: float) -> dict:
        """Kiểm ảnh đã duyệt tách rời khỏi cache `source` (thư mục hoặc manifest.json): không trùng sha256 ảnh, không
        trùng tên bộ ảnh (so tên thư mục, không so đường dẫn: bộ ảnh bị chép/dời thì đường dẫn đổi), không chụp cách
        một bản ghi ≤ `session_gap_s` (cùng phiên — khung gần trùng mà sha256 không bắt được). Trùng thì LabelError."""
        path = Path(source)
        manifest_path = path / "manifest.json" if path.is_dir() else path
        if not manifest_path.is_file():
            raise LabelError(f"--disjoint-from: không thấy manifest {manifest_path}")
        manifest = _read_json_object(manifest_path, "manifest")
        records = manifest.get("records")
        if not isinstance(records, list):
            raise LabelError(f"--disjoint-from: {manifest_path} không phải manifest của cache (thiếu 'records')")
        records = [r for r in records if isinstance(r, dict)]
        shas = {r.get("image_sha256") for r in records if r.get("image_sha256")}
        names = {r.get("snapshot") for r in records if r.get("snapshot")}
        times, unchecked = [], 0
        for r in records:
            stamps = [t for t in (_parse_time(r.get("captured_local")), _parse_time(r.get("frame_captured_local")))
                      if t is not None]
            times += stamps
            unchecked += not stamps
        times.sort()

        def nearest_s(t: datetime) -> float | None:
            k = bisect_left(times, t)
            gaps = [abs((times[j] - t).total_seconds()) for j in (k - 1, k) if 0 <= j < len(times)]
            return min(gaps) if gaps else None

        hits = []
        for it in reviewed:
            why = []
            if it["image"]["sha256"] in shas:
                why.append("trùng sha256 ảnh")
            if it["source"].get("snapshot") in names:
                why.append(f"cùng bộ ảnh {it['source']['snapshot']}")
            stamps = [t for t in (_parse_time(it["source"].get("captured_local")),
                                  _parse_time(it["source"].get("frame_captured_local"))) if t is not None]
            unchecked += not stamps
            gaps = [g for g in (nearest_s(t) for t in stamps) if g is not None]
            if gaps and min(gaps) <= session_gap_s:
                why.append(f"chụp cách một ảnh của cache đó {min(gaps):.0f} s (≤ {session_gap_s:g} s: cùng phiên)")
            if why:
                hits.append(f"{it['id']}: " + ", ".join(why))
        if hits:
            shown = hits[:20] + ([f"… và {len(hits) - 20} ảnh khác"] if len(hits) > 20 else [])
            raise LabelError(
                f"Không export: {len(hits)} ảnh đã duyệt trùng với cache {manifest_path.parent.name} ({manifest_path}) — "
                "cache này sẽ không tách rời khỏi nó (vd. chấm trên ảnh/phiên đã dùng để huấn luyện):\n  "
                + "\n  ".join(shown) + "\nBỏ các bộ ảnh đó khỏi dự án này (chụp phiên riêng, cách > "
                f"{session_gap_s:g} s, thư mục riêng), hoặc bỏ --disjoint-from nếu không cần tách rời.")
        return {"manifest": str(manifest_path.resolve()), "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
                "records": len(records), "checked": ["image_sha256", "snapshot", "session_gap"],
                "session_gap_s": float(session_gap_s), "unchecked_time": unchecked}

    def _read_item_file(self, item_id: str) -> dict:
        """Sidecar đọc thẳng từ đĩa (không qua bộ nhớ đệm): tiến trình khác có thể đã ghi nó."""
        return _read_json_object(self.path(item_id, "items"), "sidecar")

    def _build_and_swap(self, out: Path, partial: Path, reviewed: list[dict], sessions: dict[str, str],
                        splits: dict[str, list[int]], manifest_extra: dict, height: int, width: int):
        started = time.perf_counter()
        images = np.lib.format.open_memmap(partial / "images.npy", mode="w+", dtype=np.uint8,
                                           shape=(len(reviewed), height, width, 3))
        masks = np.lib.format.open_memmap(partial / "masks.npy", mode="w+", dtype=np.uint8,
                                          shape=(len(reviewed), height, width))
        records, hashes = [], []
        for index, it in enumerate(reviewed):
            # Đọc MỘT lần và kiểm lại trên đúng mảng sẽ ghi: công cụ gán nhãn (tiến trình khác, không có khóa) có thể
            # tự lưu cùng dự án sau vòng kiểm đầu — nhãn mới vào cache mà manifest vẫn ghi sha256 lúc duyệt.
            raw = self.path(it["id"], "images").read_bytes()
            label = self.label(it["id"])
            on_disk = self._read_item_file(it["id"])
            changed = []
            if sha256_bytes(raw) != it["image"]["sha256"]:
                changed.append("ảnh đổi trong lúc export")
            if array_sha256(label) != it["reviewed_label_sha256"]:
                changed.append("nhãn đổi trong lúc export (bị sửa sau khi duyệt) — duyệt lại")
            if on_disk.get("status") != "reviewed" or on_disk.get("reviewed_label_sha256") != it["reviewed_label_sha256"]:
                changed.append(f"trạng thái trên đĩa thành '{on_disk.get('status')}' trong lúc export")
            if changed:
                raise LabelError("Không export — dự án bị ghi trong lúc export (đóng công cụ gán nhãn rồi chạy lại): "
                                 f"{it['id']}: " + "; ".join(changed))
            image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise LabelError(f"{it['id']}: không giải mã được ảnh")
            prepared, target, box = letterbox(image, label, height, width)
            images[index] = cv2.cvtColor(prepared, cv2.COLOR_BGR2RGB)
            masks[index] = target
            hashes.append(perceptual_hashes(image))
            group = sessions[_group_key(it)]
            records.append({
                "index": index, "id": it["id"], "source": "sa_ban", "sequence": group, "group": group,
                "snapshot": it["source"]["snapshot"], "snapshot_dir": it["source"]["snapshot_dir"],
                "port": it["source"]["port"], "camera": f"p{it['source']['port']}",
                "captured_local": it["source"].get("captured_local"),
                **({"frame_captured_local": it["source"]["frame_captured_local"]}
                   if it["source"].get("frame_captured_local") else {}),
                "image_sha256": it["image"]["sha256"], "label_sha256": it["reviewed_label_sha256"],
                "original_size": [it["image"]["width"], it["image"]["height"]],
                "pixels": {str(k): int((target == k).sum()) for k in CLASSES}, "letterbox": box,
                "reviewed_by": it["reviewed_by"], "reviewed_at": it["reviewed_at"],
                "draft": {"origin": it["draft"]["origin"], "model": it["draft"]["model"],
                          "threshold": it["draft"]["threshold"]},
                "edited_fraction": it["label"].get("edited_fraction"),
                "damage_flagged": bool(it["damage"]["damaged"]), "damage_override": it.get("damage_override")})
        images.flush()
        masks.flush()
        manifest_extra["grouping"]["leakage_min_phash_distance_to_train"] = leakage_report(hashes, splits)
        manifest_extra["preparation_seconds"] = time.perf_counter() - started
        statistics = write_cache(partial, images, masks, records, splits, manifest_extra, MAPPING_SHA256)
        del images, masks                             # nhả memmap: Windows không đổi tên thư mục đang mở file
        check = check_cache(partial)
        aside = None
        if out.exists():
            if any(out.iterdir()):
                aside = _aside_path(out)
                try:
                    os.replace(out, aside)
                except OSError as error:
                    raise LabelError(f"Không đổi tên được cache cũ {out} ({error}). Trên Windows điều này xảy ra khi "
                                     "có file trong đó đang mở — vd. một lượt huấn luyện đang dùng cache. Dừng lượt "
                                     "đó, hoặc export ra tên mới (vd. sa_ban_v2). Cache cũ không bị đụng tới.") from error
            else:
                out.rmdir()
        try:
            os.replace(partial, out)
        except OSError as error:
            if aside is not None:
                os.replace(aside, out)                # trả cache cũ về đúng tên, không bao giờ để nó nằm lệch
            raise LabelError(f"Không đổi tên được {partial.name} thành {out} ({error})") from error
        return statistics, check, aside

    def _freeze_splits(self, frozen: dict, assigned: dict, reviewed: list[dict], splits: dict[str, list[int]],
                       params: dict, out: Path, new_keys: list[str], moved: list[dict], resplit: bool) -> str | None:
        """Ghi `splits.json`: split cũ + split của mọi ảnh vừa export. Trả cảnh báo nếu ghi hỏng (cache đã vào chỗ)."""
        updated = dict(assigned)
        for name in SPLITS:
            for i in splits[name]:
                updated[reviewed[i]["id"]] = name
        for m in moved:                 # ảnh đã đóng băng của phiên bị dời mà nay chưa duyệt cũng ghi là train: khi được
            for item_id in m["items"]:  # duyệt lại nó theo phiên (train), cảnh báo "dời về train" không lặp lại
                updated[item_id] = "train"
        entry = {"exported_at": now_local(), "by": self.who, "out": str(Path(out).resolve()), "images": len(reviewed),
                 "new_sessions": len(new_keys), "moved_to_train": moved, "resplit": bool(resplit)}
        if resplit and frozen:
            entry["discarded_assignments"] = len(frozen.get("assigned") or {})
        state = {"kind": SPLIT_KIND, "version": 1, **params, "rule": SPLIT_RULE,
                 "assigned": dict(sorted(updated.items())), "history": list(frozen.get("history") or []) + [entry]}
        try:
            _atomic_write_json(self.root / SPLIT_FILE, state)
        except OSError as error:
            return (f"cache đã ghi nhưng KHÔNG ghi được {self.root / SPLIT_FILE} ({error}): split chưa đóng băng — lần "
                    "export sau có thể chia khác")
        return None


def _aside_path(out: Path) -> Path:
    base = f"{out.name}.cu_{datetime.now():%Y%m%d_%H%M%S}"
    aside, k = out.with_name(base), 1
    while aside.exists():
        k += 1
        aside = out.with_name(f"{base}_{k}")
    return aside


def check_cache(root) -> dict:
    """Kiểm một cache đã ghi mà KHÔNG cần torch: các điều kiện `dataset.PreparedCache.open` + `check_splits` đòi
    (kích thước và kiểu mảng, split phủ mọi bản ghi đúng một lần, `index`/`split` từng bản ghi khớp, nhóm không vắt qua
    hai split) cộng đếm lại pixel từng bản ghi như `verify_cache.recount_pixels`. Ném LabelError nếu sai.
    (Lặp lại logic vì dataset.py nhập torch ngay đầu module; test trong .venv-train mở cache bằng chính PreparedCache.)"""
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    marker = json.loads((root / "TRANSFER_READY.json").read_text(encoding="utf-8"))
    records, height, width = manifest["records"], manifest["height"], manifest["width"]
    if not marker.get("ready") or marker.get("mapping_sha256") != manifest["mapping_sha256"]:
        raise LabelError("TRANSFER_READY.json không khớp manifest")
    images = np.load(root / "images.npy", mmap_mode="r", allow_pickle=False)
    masks = np.load(root / "masks.npy", mmap_mode="r", allow_pickle=False)
    try:
        if images.shape != (len(records), height, width, 3) or images.dtype != np.uint8:
            raise LabelError(f"images.npy {images.shape} {images.dtype}")
        if masks.shape != (len(records), height, width) or masks.dtype != np.uint8:
            raise LabelError(f"masks.npy {masks.shape} {masks.dtype}")
        seen: set[int] = set()
        for name in SPLITS:
            indices = manifest["splits"][name]
            if len(set(indices)) != len(indices) or seen & set(indices):
                raise LabelError(f"split {name} lặp hoặc chung ảnh với split khác")
            if any(records[i]["index"] != i or records[i]["split"] != name for i in indices):
                raise LabelError(f"split {name} không khớp trường index/split của bản ghi")
            seen |= set(indices)
        if seen != set(range(len(records))):
            raise LabelError("split không phủ mỗi bản ghi đúng một lần")
        owners: dict[str, str] = {}
        for record in records:
            if owners.setdefault(record["group"], record["split"]) != record["split"]:
                raise LabelError(f"nhóm {record['group']} vắt qua hai split (rò rỉ)")
        for record in records:
            mask = np.asarray(masks[record["index"]])
            if not np.isin(mask, CLASSES).all():
                raise LabelError(f"{record['id']}: masks.npy có giá trị ngoài {{0, 1, 255}}")
            if pixel_counts(mask) != record["pixels"]:
                raise LabelError(f"{record['id']}: số pixel khác manifest")
        return {"records": len(records), "groups": len(owners),
                "splits": {name: len(manifest["splits"][name]) for name in SPLITS}}
    finally:
        del images, masks


# ---------------------------------------------------------------- dòng lệnh
def format_statistics(stats: dict) -> str:
    pct = lambda x: "—" if x is None else f"{100 * x:.1f} %".replace(".", ",")
    s = stats["by_status"]
    lines = [f"{stats['items']} ảnh: nháp {s['draft']}, đã duyệt {s['reviewed']}, loại {s['rejected']} "
             f"(khung hỏng {stats['damaged']})",
             f"{stats['snapshots']} bộ ảnh, {stats['sessions']} phiên chụp (cách ≤ {stats['session_gap_s']:g} s nối "
             f"chuỗi); phiên có ảnh đã duyệt: {stats['reviewed_sessions']}",
             "theo cổng: " + ", ".join(f"p{port} {dict(c)}" for port, c in stats["by_port"].items()),
             "nguồn nháp: " + ", ".join(f"{k} {v}" for k, v in stats["draft_origin"].items())]
    frozen = stats.get("frozen_split")
    lines.append(f"split đóng băng ({frozen['file']}): {frozen['items']} ảnh {frozen['by_split']}, seed {frozen['seed']}, "
                 f"tỉ lệ {frozen['ratios']}" if frozen else "split: chưa export lần nào (chưa đóng băng)")
    share = stats["reviewed_share"]
    if stats["reviewed_pixels"]:
        lines.append(f"pixel đã duyệt: FREE {pct(share.get('0'))}, BLOCKED {pct(share.get('1'))}, "
                     f"IGNORE {pct(share.get('255'))}")
        e = stats["reviewed_edited_fraction"]
        lines.append(f"phần ảnh người tô tay (ảnh đã duyệt): trung bình {pct(e['mean'])}, trung vị {pct(e['median'])}")
    d = stats["draft_vs_reviewed"]
    if d["items"]:
        lines.append(f"nháp so với nhãn đã duyệt ({d['items']} ảnh): trùng {pct(d['agreement'])}; BLOCKED bị nháp gọi "
                     f"FREE {pct(d['blocked_drafted_as_free'])}; FREE bị nháp gọi BLOCKED {pct(d['free_drafted_as_blocked'])}")
        lines.append("  " + d["note"])
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("import", help="nhập thư mục ảnh chụp của bàn thử, sinh nhãn nháp")
    a.add_argument("sources", type=Path, nargs="+", help="runs/rig_snapshots hoặc một bộ ảnh cụ thể")
    a.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                   help="ngưỡng P(BLOCKED) của nháp (0,5 = argmax; 0,15 gọi BLOCKED nhiều hơn -> nhiều báo động giả hơn)")
    a.add_argument("--model", type=Path, default=None,
                   help="checkpoint để chạy LiveSegmenter cho ảnh không có xác suất (cần torch: .venv-train)")
    a.add_argument("--device", default=None)
    a.add_argument("--skip-damaged", action="store_true", help="bỏ hẳn khung hỏng thay vì nhập ở trạng thái 'loại'")
    a.add_argument("--no-draft", action="store_true",
                   help="không dùng AI: nháp toàn IGNORE, không chép xác suất (nhãn không dẫn xuất từ mô hình)")
    a.add_argument("--bottom-repeat-limit", type=float, default=BOTTOM_REPEAT_LIMIT)
    a.add_argument("--frame-age-limit-ms", type=float, default=FRAME_AGE_LIMIT_MS,
                   help="khung có age_ms (meta.json) lớn hơn số này là khung cũ — camera treo — và bị đánh dấu hỏng "
                        f"(mặc định {FRAME_AGE_LIMIT_MS:g} ms; bộ ảnh thật 23/09: 180–341 ms)")
    b = sub.add_parser("stats", help="thống kê dự án")
    b.add_argument("--json", action="store_true")
    c = sub.add_parser("export", help="xuất ảnh ĐÃ DUYỆT thành cache huấn luyện")
    c.add_argument("--out", type=Path, required=True)
    c.add_argument("--seed", type=int, default=DEFAULT_SEED)
    c.add_argument("--ratios", type=float, nargs=3, default=(0.70, 0.15, 0.15), metavar=("TRAIN", "VAL", "TEST"))
    c.add_argument("--height", type=int, default=384)
    c.add_argument("--width", type=int, default=512)
    c.add_argument("--overwrite", action="store_true", help="thư mục ra đã có thì đổi tên nó sang bên (không xóa)")
    c.add_argument("--resplit", action="store_true",
                   help="bỏ split đã đóng băng (splits.json) và chia lại từ đầu: cache mới KHÔNG so được với cache cũ")
    c.add_argument("--disjoint-from", type=Path, nargs="+", default=[], metavar="CACHE",
                   help="cache (thư mục hoặc manifest.json) mà cache này phải tách rời: từ chối nếu có ảnh trùng sha256, "
                        "trùng bộ ảnh, hay chụp cách ≤ --session-gap (vd. tập chấm riêng so với cache huấn luyện)")
    for p in (a, b, c):
        p.add_argument("--project", type=Path, default=DEFAULT_PROJECT)
        p.add_argument("--who", default=None, help="tên người làm (mặc định: tài khoản máy)")
    for p in (b, c):
        p.add_argument("--session-gap", type=float, default=SESSION_GAP_S,
                       help="hai bộ ảnh cách nhau ≤ số giây này thuộc cùng phiên (cùng split)")
    args = parser.parse_args(argv)
    # kiểm tham số TRƯỚC khi tạo dự án: parser.error in cách dùng, thoát mã 2 và không đụng tới file nào
    if args.command == "import":
        if not 0.0 < args.threshold < 1.0:                         # cũng loại NaN
            parser.error(f"--threshold phải là phân số trong (0, 1), vd. 0.5 — không phải phần trăm "
                         f"(đang là {args.threshold})")
        if not 0.0 <= args.bottom_repeat_limit <= 1.0:
            parser.error(f"--bottom-repeat-limit phải trong [0, 1] (bottom_repeat_share là tỉ lệ; 1 = tắt phép thử "
                         f"này; đang là {args.bottom_repeat_limit})")
        if not args.frame_age_limit_ms > 0.0:                      # cũng loại NaN; inf = tắt phép thử này
            parser.error(f"--frame-age-limit-ms phải > 0 mili giây (đang là {args.frame_age_limit_ms})")
    elif not args.session_gap >= 0.0:
        parser.error(f"--session-gap phải ≥ 0 giây (đang là {args.session_gap})")
    try:
        if args.command == "import":
            missing = [str(s) for s in args.sources if not s.is_dir()]
            if missing:                                            # báo trước khi tạo dự án rỗng
                raise LabelError("Không phải thư mục: " + ", ".join(missing))
            project = LabelProject(args.project, create=True, who=args.who)
            factory = None
            if args.model is not None and not args.no_draft:
                factory = lambda: load_segmenter(args.model, args.device)   # noqa: E731 - chỉ nạp khi cần
            print(f"Nhập vào {project.root}", flush=True)
            summary = project.import_snapshots(args.sources, threshold=args.threshold, make_segmenter=factory,
                                               skip_damaged=args.skip_damaged, draft=not args.no_draft,
                                               bottom_repeat_limit=args.bottom_repeat_limit,
                                               frame_age_limit_ms=args.frame_age_limit_ms)
            print(f"Đã nhập {len(summary['imported'])} ảnh ({len(summary['rejected_damaged'])} khung hỏng ở trạng thái "
                  f"'loại'); {len(summary['no_prob'])} ảnh không có xác suất AI (nháp toàn IGNORE); "
                  f"{len(summary['prob_from_model'])} ảnh chạy mô hình.")
            for reason in summary["skipped"]:
                print(f"  bỏ qua: {reason}")
            return 0
        project = LabelProject(args.project, who=args.who)
        if args.command == "stats":
            stats = project.statistics(args.session_gap)
            print(json.dumps(stats, ensure_ascii=False, indent=2) if args.json else format_statistics(stats))
            return 0
        result = project.export(args.out, seed=args.seed, session_gap_s=args.session_gap, ratios=tuple(args.ratios),
                                height=args.height, width=args.width, overwrite=args.overwrite, resplit=args.resplit,
                                disjoint_from=args.disjoint_from)
        print(f"Cache: {result['out']} — train {result['splits']['train']}, val {result['splits']['val']}, "
              f"test {result['splits']['test']} ảnh; {result['sessions']} phiên ({result['new_sessions']} phiên mới "
              f"được chia; split đóng băng ở {project.root / SPLIT_FILE})")
        for d in result["disjoint_from"]:
            print(f"  tách rời khỏi {d['manifest']} ({d['records']} bản ghi): không trùng sha256 ảnh, bộ ảnh, hay phiên "
                  f"(≤ {d['session_gap_s']:g} s)")
        return 0
    except LabelError as error:
        print(f"LỖI: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
