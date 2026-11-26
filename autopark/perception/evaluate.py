r"""Evaluate a checkpoint on a frozen split: overall / per-camera metrics, per-image table, qualitative panels.

    .venv-train\Scripts\python.exe -X utf8 -m autopark.perception.evaluate --checkpoint runs/<name>/best.pt --split val --out runs/<name>/eval_val
    .venv-train\Scripts\python.exe -X utf8 -m autopark.perception.evaluate --checkpoint runs/<name>/best.pt --split test --final-test --out runs/<name>/eval_test

The test split is for one report after model selection. Every test evaluation is appended to
`test_evaluations.jsonl` next to the checkpoint, so tuning against it would be visible.
Panels show the RAW argmax prediction everywhere; ground truth is never used to hide model errors.

Chặn chấm trên ảnh đã huấn luyện (thêm 24/09/2026): trước khi chấm, mọi ảnh của split được chấm được so với split
TRAIN của manifest mà checkpoint được huấn luyện trên đó (`config.prepared_manifest`, phải còn đúng sha256
`manifest_sha256` ghi trong checkpoint). Trùng — hoặc không kiểm được vì thiếu/đổi manifest huấn luyện — thì mặc định
TỪ CHỐI (`--train-overlap refuse`); `--train-overlap warn` chấm tiếp nhưng in cảnh báo và ghi `train_overlap` vào
metrics.json. Chỉ cần `manifest.json` của cache huấn luyện, không cần `images.npy`. Phép so tùy cache được chấm (sửa
sau rà soát, tối 24/09/2026 — bản đầu so bốn phép với khoảng phiên cố định 60 s ở cả hai trường hợp):
- chấm CHÍNH cache huấn luyện (không `--manifest`, hay `--manifest` trỏ đúng cache đó): sha256 ảnh gốc, mã ảnh kèm
  cache gốc, và nhóm chống rò rỉ (`group`). Tức là tin phân nhóm mà cache đã ghi và `check_splits` đã kiểm (nhóm không
  vắt qua hai split): với cache sa bàn đó là phiên chụp theo `labels export --session-gap` người dùng chọn, khung cũ
  xếp theo giờ khung. Bản đầu so lại tên bộ ảnh và giờ chụp ≤ 60 s nên từ chối nhầm val/test của cache chia với
  `--session-gap` < 60 s, hay có khung cũ đã duyệt nằm khác split với các camera cùng bộ ảnh (tái hiện trên dữ liệu
  giả);
- chấm cache KHÁC (`--manifest`, chấm chéo — trước 24/09 bỏ qua mọi phép kiểm split): bốn phép như `labels export
  --disjoint-from` và `import --exclude` cộng mã ảnh: sha256 ảnh, mã ảnh kèm cache gốc (`cache` của cache ghép, không
  có thì tên thư mục cache), tên bộ ảnh bàn thử, giờ chụp (giờ bộ ảnh VÀ giờ khung cũ) cách ≤ khoảng phiên. Khoảng
  phiên: của `--disjoint-from` nếu cache chấm đã được export tách rời khỏi đúng manifest huấn luyện này (khớp sha256);
  không thì `grouping.session_gap_s` của manifest huấn luyện; không có (WoodScape, ACDC, cache ghép) thì 60 s. Khoảng
  phiên riêng của cache chấm không được dùng: nó chỉ nói cách chia chính cache đó.
Giới hạn: ảnh gần trùng mà khác sha256 chỉ bắt được qua bộ ảnh/giờ chụp của cache sa bàn; cache công khai (ACDC,
AVM-SS không ghi sha256) chỉ so theo mã ảnh + cache gốc; cache ghép từ một cache ghép khác mất tên cache gốc tầng trong
(combine ghi đè trường `cache`); cache ghép không ghi khoảng phiên của cache sa bàn con nên chấm chéo dùng 60 s.
"""
import argparse
from bisect import bisect_left
import csv
from datetime import datetime
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import torch

from .checkpoint import atomic_write_json, load_checkpoint
from .dataset import CAMERAS, PreparedCache, SplitData, file_sha256
from .engine import decide, evaluate_split
from .metrics import summarize
from .model import build_model
from .train import PROJECT, utc_now

FREE_COLOR, BLOCKED_COLOR, IGNORE_COLOR = (0, 170, 0), (220, 40, 40), (110, 110, 110)
DANGER_COLOR, FALSE_ALARM_COLOR = (255, 0, 255), (255, 200, 0)
TITLES = ("Ảnh vào", "Nhãn gốc (xám = IGNORE)", "Dự đoán thô của mô hình", "Lỗi: tím = vật cản→FREE, vàng = FREE→vật cản")
ASCII_TITLES = ("Input", "Ground truth (gray = IGNORE)", "Raw model prediction", "Errors: magenta = blocked->FREE, yellow = FREE->blocked")
# Cùng giá trị labels.SESSION_GAP_S (test kiểm hai số bằng nhau). Chỉ là khoảng phiên DỰ PHÒNG khi chấm chéo mà không
# manifest nào ghi khoảng phiên (xem cross_cache_session_gap). Không nhập từ labels.py để module chấm không kéo theo mã
# camera (autopark.video.sources).
SESSION_GAP_S = 60.0
OVERLAP_POLICIES = ("refuse", "warn")
OVERLAP_CHECKS = ("image_sha256", "cache_id", "snapshot", "session_gap")    # chấm cache khác (chấm chéo)
# Chấm chính cache huấn luyện: phân nhóm đã kiểm (check_splits) là chuẩn, không so lại bộ ảnh/giờ chụp (24/09/2026).
OWN_CACHE_CHECKS = ("image_sha256", "cache_id", "group")
OVERLAP_EXAMPLES = 20


def _font(size=15):
    for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size), TITLES
        except OSError:
            continue
    return ImageFont.load_default(), ASCII_TITLES


def _overlay(image, labels, with_ignore):
    colors = np.zeros_like(image)
    colors[labels == 0], colors[labels == 1] = FREE_COLOR, BLOCKED_COLOR
    out = (0.5 * image + 0.5 * colors).astype(np.uint8)
    if with_ignore:
        out[labels == 255] = IGNORE_COLOR
    return out


def panel(image, truth, pred, caption) -> Image.Image:
    errors = (0.35 * image).astype(np.uint8)
    errors[(truth == 1) & (pred == 0)] = DANGER_COLOR
    errors[(truth == 0) & (pred == 1)] = FALSE_ALARM_COLOR
    errors[truth == 255] = IGNORE_COLOR
    tiles = [image, _overlay(image, truth, True), _overlay(image, pred, False), errors]
    height, width = image.shape[:2]
    font, titles = _font()
    canvas = Image.new("RGB", (width * 4 + 15, height + 48), (20, 20, 20))
    draw = ImageDraw.Draw(canvas)
    for i, (tile, title) in enumerate(zip(tiles, titles)):
        canvas.paste(Image.fromarray(tile), (i * (width + 5), 24))
        draw.text((i * (width + 5) + 4, 3), title, fill=(235, 235, 235), font=font)
    draw.text((4, height + 27), caption, fill=(200, 200, 200), font=font)
    return canvas


def f_beta(precision, recall, beta):
    if precision is None or recall is None or precision + recall == 0:
        return None
    b2 = beta * beta
    return (1 + b2) * precision * recall / (b2 * precision + recall)


def threshold_sweep_report(sweep: dict, checkpoint: Path) -> dict:
    """Per-threshold metrics on validation plus two explicit selection rules (no test data involved)."""
    rows = []
    for t, m in sorted(sweep.items()):
        rows.append({"threshold": t, "mIoU": m["mIoU"], "iou_free": m["iou_free"], "iou_blocked": m["iou_blocked"],
                     "blocked_precision": m["blocked_precision"], "blocked_recall": m["blocked_recall"],
                     "blocked_as_free_rate": m["blocked_as_free_rate"], "free_as_blocked_rate": m["free_as_blocked_rate"],
                     "blocked_f2": f_beta(m["blocked_precision"], m["blocked_recall"], 2.0)})
    def best(key):
        defined = [r for r in rows if r[key] is not None]
        return max(defined, key=lambda r: r[key])["threshold"] if defined else None   # never "select" on no evidence

    return {"created_utc": utc_now(), "checkpoint": str(checkpoint), "split": "val", "rows": rows,
            "selection": {"max_mIoU": best("mIoU"), "max_blocked_F2": best("blocked_f2")},
            "rule": "F2 weights BLOCKED recall twice as much as precision: for a parking robot a missed obstacle "
                    "(blocked -> FREE) is the dangerous error, a false alarm only costs a stop. The chosen "
                    "threshold must be fixed here before any test evaluation."}


def per_image_rows(records, matrices):
    """`matrices` is the (N, C, C) tensor from evaluate_split; an all-ignore image gets error_rate None."""
    rows = []
    for record, matrix in zip(records, matrices):
        report = summarize(matrix)
        valid, counts = report["valid_pixels"], report["confusion_matrix"]
        wrong = counts[0][1] + counts[1][0]
        rows.append({"id": record["id"], "camera": record.get("camera", record.get("source", "-")), "valid_pixels": valid,
                     "error_rate": wrong / valid if valid else None,
                     "iou_free": report["iou_free"], "iou_blocked": report["iou_blocked"],
                     "blocked_as_free_rate": report["blocked_as_free_rate"]})
    return rows


def cache_name(manifest_path) -> str:
    """Tên cache = tên thư mục chứa manifest.json (như trường `cache` mà `prepare_extra combine` ghi)."""
    return Path(manifest_path).resolve().parent.name


def _local_time(text):
    """Giờ máy không múi giờ (như `labels._parse_time`), để so được giờ chụp của hai cache."""
    if not isinstance(text, str) or not text:
        return None
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        return None
    return value.astimezone().replace(tzinfo=None) if value.tzinfo else value


def _capture_times(record: dict) -> list:
    return [t for t in (_local_time(record.get("captured_local")), _local_time(record.get("frame_captured_local")))
            if t is not None]


def find_overlap(eval_records, eval_cache: str, reference_records, reference_cache: str,
                 session_gap_s: float = SESSION_GAP_S, max_examples: int = OVERLAP_EXAMPLES,
                 checks=OVERLAP_CHECKS) -> dict:
    """Ảnh chấm nào trùng một ảnh tham chiếu (thường là split train của checkpoint), và vì sao. Chỉ chạy các phép có
    trong `checks` (mặc định `OVERLAP_CHECKS`: bốn phép đầu dưới đây, không có `group`).

    - `image_sha256`: sha256 file ảnh gốc (WoodScape và cache sa bàn ghi; ACDC, AVM-SS thì không);
    - `cache_id`: mã ảnh kèm cache gốc — trường `cache` của cache ghép, không có thì tên thư mục cache (`eval_cache`,
      `reference_cache`); bắt được ảnh ACDC/AVM-SS nằm trong cả một cache lẫn cache ghép chứa nó;
    - `snapshot`: cùng tên bộ ảnh bàn thử (cache sa bàn);
    - `session_gap`: giờ chụp (`captured_local`, `frame_captured_local`) cách một ảnh tham chiếu ≤ `session_gap_s` —
      cùng phiên, gần trùng mà sha256 không bắt được (cache sa bàn; cache công khai không ghi giờ nên không xét).
      So cả giờ bộ ảnh lẫn giờ khung cũ, và tên bộ ảnh trần, như `labels._check_disjoint` / `Exclusion` (chặt hơn cách
      export xếp phiên khung cũ — theo giờ khung, khóa `<bộ ảnh>#p<cổng>` — nên chỉ dùng giữa hai cache khác nhau);
    - `group`: cùng nhóm chống rò rỉ (trường `group`). Tên nhóm chỉ có nghĩa trong MỘT cache (hai dự án sa bàn khác nhau
      có thể cùng tên `sa_ban/phien_001_...`), nên chỉ dùng khi chấm chính cache huấn luyện (`OWN_CACHE_CHECKS`).
    Trả số ảnh chấm bị trùng, số theo từng phép so, và tối đa `max_examples` ví dụ (mã ảnh + lý do)."""
    unknown = set(checks) - set(OVERLAP_CHECKS) - {"group"}
    if unknown:
        raise ValueError(f"Phép so lạ: {sorted(unknown)}")
    groups = {r["group"] for r in reference_records if r.get("group") is not None}
    shas = {r["image_sha256"] for r in reference_records if r.get("image_sha256")}
    ids = {(r.get("cache") or reference_cache, str(r["id"])) for r in reference_records}
    snapshots = {r["snapshot"] for r in reference_records if r.get("snapshot")}
    times = sorted(t for r in reference_records for t in _capture_times(r))
    by_check = dict.fromkeys(checks, 0)
    examples, hits = [], 0
    for record in eval_records:
        why = []
        if "image_sha256" in checks and record.get("image_sha256") and record["image_sha256"] in shas:
            why.append("image_sha256")
        if "cache_id" in checks and (record.get("cache") or eval_cache, str(record["id"])) in ids:
            why.append("cache_id")
        if "group" in checks and record.get("group") is not None and record["group"] in groups:
            why.append("group")
        if "snapshot" in checks and record.get("snapshot") and record["snapshot"] in snapshots:
            why.append("snapshot")
        if "session_gap" in checks:
            gaps = [abs((times[j] - t).total_seconds()) for t in _capture_times(record)
                    for k in (bisect_left(times, t),) for j in (k - 1, k) if 0 <= j < len(times)]
            if gaps and min(gaps) <= session_gap_s:
                why.append("session_gap")
        if why:
            hits += 1
            for check in why:
                by_check[check] += 1
            if len(examples) < max_examples:
                examples.append({"id": record["id"], "cache": record.get("cache") or eval_cache, "matched_by": why})
    return {"evaluated_images": len(eval_records), "reference_images": len(reference_records),
            "overlapping_images": hits, "by_check": by_check, "examples": examples}


def _gap_seconds(value) -> float | None:
    """Khoảng phiên ghi trong manifest: số ≥ 0 (không nhận bool, NaN, chuỗi), không hợp lệ thì None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not value >= 0.0:
        return None
    return float(value)


def cross_cache_session_gap(train_manifest: dict, train_manifest_sha256: str, eval_manifest: dict) -> tuple[float, str]:
    """Khoảng phiên cho phép so `session_gap` khi chấm một cache KHÁC cache huấn luyện. Trả (số giây, nguồn của số đó):
    1. cache chấm có mục `disjoint_from` (do `labels export --disjoint-from` ghi) khớp sha256 ĐÚNG manifest huấn luyện
       này: khoảng phiên của phép kiểm đó. Phép kiểm đó đã so mọi bản ghi của cache huấn luyện, nên chốt không chặn điều
       export đã cho qua (vd. cả hai cùng `--session-gap 30`, hai bộ ảnh cách 45 s);
    2. không thì `grouping.session_gap_s` của manifest huấn luyện: khoảng phiên mà chính val/test của nó được coi là
       chưa học (`labels export --session-gap`);
    3. không có (WoodScape, ACDC, cache ghép) thì SESSION_GAP_S.
    Khoảng phiên riêng của cache chấm (không kèm `disjoint_from`) KHÔNG được dùng: nó chỉ nói cách chia cache đó, nên
    một cache chấm export với `--session-gap` nhỏ mà quên `--disjoint-from` không nới được chốt."""
    for entry in eval_manifest.get("disjoint_from") or ():
        if isinstance(entry, dict) and entry.get("manifest_sha256") == train_manifest_sha256:
            gap = _gap_seconds(entry.get("session_gap_s"))
            if gap is not None:
                return gap, "disjoint_from của cache chấm (export --disjoint-from đúng manifest huấn luyện này)"
    grouping = train_manifest.get("grouping")
    gap = _gap_seconds(grouping.get("session_gap_s") if isinstance(grouping, dict) else None)
    if gap is not None:
        return gap, "grouping.session_gap_s của manifest huấn luyện"
    return SESSION_GAP_S, "mặc định (manifest huấn luyện không ghi grouping.session_gap_s)"


def train_overlap_report(state: dict, eval_records, eval_manifest_path, *, eval_split: str, cross_domain: bool,
                         policy: str, project: Path = PROJECT, eval_manifest: dict | None = None) -> dict:
    """So ảnh chấm với split train của manifest huấn luyện của checkpoint. `status`:
    - "clean": đã so, không ảnh nào trùng;
    - "overlap": có ảnh trùng (số và ví dụ trong báo cáo);
    - "unverifiable": không thấy manifest huấn luyện, hoặc nó khác sha256 checkpoint đã ghi (cache bị ghi lại sau khi
      huấn luyện — vd. `labels export --overwrite`), nên không dựng lại được đúng tập train.
    Dùng cả split train (bỏ qua `limit_train` nếu có: tập so lớn hơn tập thật sự đã học, tức thận trọng hơn). Kèm phép
    so với split chọn mô hình (`validation_split`) khi chấm chéo miền hoặc chấm test: chỉ cảnh báo, không chặn.
    Phép so: `OWN_CACHE_CHECKS` khi chấm chính cache huấn luyện (`cross_domain` False), `OVERLAP_CHECKS` với khoảng
    phiên của `cross_cache_session_gap` khi chấm cache khác (docstring module). `eval_manifest`: manifest cache chấm
    đã đọc (không có thì đọc từ `eval_manifest_path`, chỉ khi chấm chéo)."""
    cfg = state["config"]
    train_manifest = Path(project) / cfg["prepared_manifest"]
    checks = OVERLAP_CHECKS if cross_domain else OWN_CACHE_CHECKS
    report = {"policy": policy, "train_manifest": str(train_manifest), "checks": list(checks), "session_gap_s": None,
              "evaluated_manifest": str(eval_manifest_path), "evaluated_split": eval_split,
              "evaluated_images": len(eval_records), "limit_train": cfg.get("limit_train")}
    if not train_manifest.is_file():
        return {**report, "status": "unverifiable",
                "reason": f"không thấy manifest huấn luyện {train_manifest} (chỉ cần manifest.json của cache đó)"}
    sha = file_sha256(train_manifest)
    if state.get("manifest_sha256") != sha:
        return {**report, "status": "unverifiable", "train_manifest_sha256": sha,
                "checkpoint_manifest_sha256": state.get("manifest_sha256"),
                "reason": "manifest huấn luyện trên đĩa khác sha256 checkpoint ghi lúc huấn luyện (cache bị ghi lại?): "
                          "không dựng lại được đúng tập train"}
    manifest = json.loads(train_manifest.read_text(encoding="utf-8"))
    records = manifest["records"]
    train = [records[i] for i in manifest["splits"]["train"]]
    gap = None
    if cross_domain:
        if eval_manifest is None:
            eval_manifest = json.loads(Path(eval_manifest_path).read_text(encoding="utf-8"))
        gap, source = cross_cache_session_gap(manifest, sha, eval_manifest)
        report.update({"session_gap_s": gap, "session_gap_source": source})
    else:
        report["session_gap_source"] = ("không so giờ chụp: chấm chính cache huấn luyện, tin phân nhóm `group` mà "
                                        "cache ghi và check_splits đã kiểm")

    def compare(reference):
        return find_overlap(eval_records, cache_name(eval_manifest_path), reference, cache_name(train_manifest),
                            checks=checks, **({"session_gap_s": gap} if gap is not None else {}))

    overlap = compare(train)
    report.update({"status": "overlap" if overlap["overlapping_images"] else "clean", "train_manifest_sha256": sha,
                   "train_images": len(train), **{k: v for k, v in overlap.items() if k != "reference_images"}})
    selection = cfg.get("validation_split", "val")
    if selection != "train" and (cross_domain or eval_split != selection):
        chosen = compare([records[i] for i in manifest["splits"][selection]])
        report["selection_split"] = selection
        report["selection_overlap"] = {k: chosen[k] for k in ("overlapping_images", "by_check", "examples")}
    return report


def overlap_message(report: dict) -> str | None:
    """Câu báo cho người chạy lệnh; None nếu sạch và không trùng split chọn mô hình."""
    lines = []
    if report["status"] == "unverifiable":
        lines.append(f"KHÔNG KIỂM ĐƯỢC ảnh chấm có nằm trong train của checkpoint không: {report['reason']}.")
    elif report["status"] == "overlap":
        shown = ", ".join(f"{e['id']} ({'+'.join(e['matched_by'])})" for e in report["examples"][:8])
        counts = ", ".join(f"{k} {v}" for k, v in report["by_check"].items() if v)
        lines.append(f"{report['overlapping_images']}/{report['evaluated_images']} ảnh chấm ({report['evaluated_split']} "
                     f"của {report['evaluated_manifest']}) TRÙNG ảnh train của checkpoint ({report['train_manifest']}): "
                     f"{counts}. Ví dụ: {shown}. Số chấm trên các ảnh này là số trên ảnh đã học, không phải tổng quát hóa.")
    selection = report.get("selection_overlap")
    if selection and selection["overlapping_images"]:
        lines.append(f"{selection['overlapping_images']} ảnh chấm trùng ảnh split '{report['selection_split']}' mà "
                     "checkpoint đã dùng để chọn mô hình (chỉ cảnh báo, không chặn).")
    return " ".join(lines) or None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--split", choices=("val", "test"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--final-test", action="store_true",
                        help="required for --split test: confirms model selection is finished")
    parser.add_argument("--examples", type=int, default=3, help="best / typical / worst panels per camera")
    parser.add_argument("--threshold", type=float, default=0.5, help="BLOCKED probability threshold (ties -> BLOCKED)")
    parser.add_argument("--manifest", type=Path, default=None,
                        help="score against ANOTHER prepared cache (chấm chéo miền). Dùng cache này thay cache mà "
                             "checkpoint được huấn luyện trên đó; khi đó bỏ qua phép kiểm split/mapping vì hai bộ "
                             "vốn khác nhau (phép so ảnh chấm với ảnh train, --train-overlap, VẪN chạy), và kết quả "
                             "PHẢI được ghi rõ là chấm chéo, không phải val của chính nó.")
    parser.add_argument("--sweep", action="store_true",
                        help="validation only: score every threshold in 0.05..0.95 and write threshold_sweep.json")
    parser.add_argument("--train-overlap", choices=OVERLAP_POLICIES, default="refuse",
                        help="ảnh chấm trùng ảnh train của checkpoint, hoặc không kiểm được vì thiếu/đổi manifest huấn "
                             "luyện: 'refuse' (mặc định) dừng, 'warn' chấm tiếp, in cảnh báo và ghi train_overlap vào "
                             "metrics.json. Chấm chính cache huấn luyện: so sha256 ảnh, mã ảnh + cache gốc, nhóm (group). "
                             "Chấm cache khác: sha256 ảnh, mã ảnh + cache gốc, bộ ảnh, giờ chụp cách ≤ khoảng phiên "
                             "(của --disjoint-from nếu cache chấm đã tách rời khỏi đúng cache huấn luyện; không thì "
                             "grouping.session_gap_s của cache huấn luyện; không có thì 60 s)")
    args = parser.parse_args(argv)
    if args.sweep and args.split != "val":
        parser.error("--sweep is a model-selection step and runs on the validation split only")
    if args.split == "test" and not args.final_test:
        parser.error("The test split is held out. Select the model on validation first, then pass --final-test.")

    state = load_checkpoint(args.checkpoint)
    cfg = state["config"]
    manifest_path = args.manifest or (PROJECT / cfg["prepared_manifest"])
    cache = PreparedCache.open(manifest_path, cfg["require_handoff_split_verified"])
    cross_domain = args.manifest is not None and str(Path(args.manifest).resolve()) != str((PROJECT / cfg["prepared_manifest"]).resolve())
    if not cross_domain:
        if state["split_sha256"] != cache.split_sha256 or state["mapping_sha256"] != cache.manifest["mapping_sha256"]:
            raise SystemExit("Checkpoint was trained on a different split or label mapping; refusing to evaluate.")
    elif cache.manifest["height"] != cfg["height"] or cache.manifest["width"] != cfg["width"]:
        raise SystemExit("Cross-domain evaluation needs the same input size as training.")
    # Chặn chấm trên ảnh đã huấn luyện, TRƯỚC khi cần GPU: từ chối thì báo ngay, trên cả máy không có CUDA.
    evaluated = [cache.manifest["records"][i] for i in cache.indices(args.split)]
    overlap = train_overlap_report(state, evaluated, manifest_path, eval_split=args.split, cross_domain=cross_domain,
                                   policy=args.train_overlap, eval_manifest=cache.manifest)
    warning = overlap_message(overlap)
    if overlap["status"] != "clean" and args.train_overlap == "refuse":
        raise SystemExit(f"Từ chối chấm: {warning} Muốn chấm tiếp thì thêm --train-overlap warn (metrics.json sẽ ghi "
                         f"train_overlap.status = {overlap['status']!r}).")
    if warning:
        print(f"CẢNH BÁO: {warning}", file=sys.stderr, flush=True)
    if not torch.cuda.is_available():
        raise SystemExit("CUDA unavailable; evaluation does not fall back to CPU silently.")
    device = torch.device("cuda")
    model = build_model(cfg["num_classes"], pretrained=False)
    model.load_state_dict(state["model"])
    model.to(device)

    data = SplitData(cache, args.split)
    predictions = np.empty((len(data), cfg["height"], cfg["width"]), np.uint8)

    def keep(positions, _images, _masks, logits):
        predictions[positions] = decide(logits, args.threshold).to(torch.uint8).cpu().numpy()

    sweep_thresholds = [round(0.05 * i, 2) for i in range(1, 20)] if args.sweep else None
    result = evaluate_split(model, data, batch_size=cfg["eval_batch_size"], device=device, amp=cfg["amp"],
                            num_classes=cfg["num_classes"], ignore_index=cfg["ignore_index"], on_batch=keep,
                            threshold=args.threshold, sweep_thresholds=sweep_thresholds)
    report = result["report"]
    if args.sweep:
        args.out.mkdir(parents=True, exist_ok=True)
        atomic_write_json(args.out / "threshold_sweep.json", threshold_sweep_report(result["sweep"], args.checkpoint))
    matrix = np.asarray(report["confusion_matrix"], dtype=np.float64)
    checkpoint_sha = file_sha256(args.checkpoint)
    args.out.mkdir(parents=True, exist_ok=True)
    atomic_write_json(args.out / "metrics.json", {
        "created_utc": utc_now(), "checkpoint": str(args.checkpoint), "checkpoint_sha256": checkpoint_sha,
        "checkpoint_epoch": state["epoch"], "selected_by": cfg["select_checkpoint_by"], "threshold": args.threshold,
        "class_names": {"0": "FREE_CANDIDATE", "1": "OBSTACLE_OR_BLOCKED"},
        "confusion_matrix_layout": "rows = ground truth, columns = prediction, IGNORE (255) excluded",
        "confusion_matrix_row_normalized": (matrix / np.maximum(matrix.sum(1, keepdims=True), 1)).tolist(),
        "resolution": [cfg["height"], cfg["width"]], "split_sha256": cache.split_sha256,
        "evaluated_manifest": str(manifest_path), "cross_domain": cross_domain, "train_overlap": overlap, **report})

    rows = per_image_rows(data.records, result["per_image"])
    with (args.out / "per_image.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    chosen = []
    for camera in CAMERAS:
        ranked = sorted((i for i, row in enumerate(rows) if row["camera"] == camera and row["valid_pixels"]),
                        key=lambda i: rows[i]["error_rate"])
        middle = len(ranked) // 2
        picks = {"best": ranked[:args.examples], "worst": ranked[::-1][:args.examples],
                 "typical": ranked[max(0, middle - args.examples // 2):][:args.examples]}
        for kind, indices in picks.items():
            for rank, i in enumerate(indices, 1):
                row = rows[i]
                danger = row["blocked_as_free_rate"]
                caption = (f"{row['id']} | {kind} #{rank} of {camera} | pixel error {row['error_rate']:.2%} | "
                           f"blocked->FREE {'n/a' if danger is None else format(danger, '.2%')}")
                name = f"{camera}_{kind}_{rank}_{row['id']}.png"
                panel(data.images[i].numpy(), data.masks[i].numpy(), predictions[i], caption).save(args.out / name)
                chosen.append({"file": name, "kind": kind, **row})
    atomic_write_json(args.out / "examples.json", {
        "selection": "per camera, ranked by per-image pixel error over non-ignored pixels", "examples": chosen})

    if args.split == "test":
        with (args.checkpoint.parent / "test_evaluations.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"utc": utc_now(), "checkpoint_sha256": checkpoint_sha, "epoch": state["epoch"],
                                "threshold": args.threshold, "mIoU": report["mIoU"], "out": str(args.out),
                                "train_overlap": overlap["status"]}) + "\n")
    fmt = lambda v: "n/a" if v is None else f"{v:.4f}"
    flag = "" if overlap["status"] == "clean" else f"[CẢNH BÁO train_overlap = {overlap['status']}] "
    print(f"{flag}{args.split}: mIoU {fmt(report['mIoU'])} | IoU free {fmt(report['iou_free'])} blocked "
          f"{fmt(report['iou_blocked'])} | blocked recall {fmt(report['blocked_recall'])} precision "
          f"{fmt(report['blocked_precision'])} | blocked->FREE {fmt(report['blocked_as_free_rate'])} | "
          f"{report['images']} images -> {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
