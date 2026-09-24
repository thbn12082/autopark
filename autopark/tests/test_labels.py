"""Gán nhãn sa bàn: nhập bộ ảnh của bàn thử, nháp từ xác suất AI, khung hỏng bị loại, cọ/đa giác/hoàn tác, lưu/đọc,
duyệt gắn với đúng nội dung nhãn, export ra cache đúng định dạng huấn luyện và chia split theo phiên chụp."""
from datetime import datetime, timedelta
import json
import shutil
import sys

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from autopark.perception import labels as L  # noqa: E402
from autopark.perception.data import letterbox  # noqa: E402
from autopark.perception.labels import (BLOCKED, FREE, IGNORE, LabelEditor, LabelError, LabelProject,  # noqa: E402
                                        array_sha256, check_cache, draft_from_prob, session_groups)
from autopark.perception.prepare_extra import split_groups  # noqa: E402
from autopark.video.sources import bottom_repeat_share, torn_bands, truncated_rows  # noqa: E402

W, H = 160, 90                     # 16:9 như 720p -> letterbox 512x384 có dải đệm 48 dòng trên và dưới
PW, PH = 80, 45                    # xác suất nhỏ hơn, cùng tỉ lệ (như prob_size của bàn thử)


def write_png(path, array):
    ok, buffer = cv2.imencode(".png", array)
    assert ok
    path.write_bytes(buffer.tobytes())


def noise_image(seed):
    return np.random.default_rng(seed).integers(0, 256, (H, W, 3), dtype=np.uint8)


def truncate(image, rows=24, seed=5):
    """Đuôi khung MJPEG bị cắt: bộ giải mã tô một vân khối 8x8 xám lặp lại (như thấy trên hub, 23/09/2026)."""
    tile = np.random.default_rng(seed).integers(0, 256, (8, 8), dtype=np.uint8)
    out = image.copy()
    out[H - rows:] = np.tile(tile, (rows // 8 + 1, W // 8 + 1))[:rows, :W, None]
    return out


def tear(image, row0=40, col0=60, seed=6):
    """Dải xé giữa ảnh: một hàng khối được tô vân lặp từ cột col0 tới mép phải, đáy vẫn nguyên."""
    tile = np.random.default_rng(seed).integers(0, 256, (8, 8), dtype=np.uint8)
    out = image.copy()
    band = np.tile(tile, (1, W // 8 + 1))[:, :W - col0]
    out[row0:row0 + 8, col0:] = band[..., None]
    return out


def ramp_prob():
    """P(BLOCKED) tăng dần theo cột, cộng nhiễu để nội suy tuyến tính khác hẳn lân cận gần nhất."""
    rng = np.random.default_rng(3)
    base = np.linspace(0, 255, PW)[None, :] + rng.normal(0, 40, (PH, PW))
    return np.clip(np.round(base), 0, 255).astype(np.uint8)


def write_snapshot(root, when: datetime, ports=(1, 2), *, damaged=(), torn=(), meta_share=None, missing_prob=(),
                   probs=None, seed=0, name=None, with_meta=True):
    """Một thư mục "Chụp bộ ảnh" giống bàn thử (autopark.ui.rig_app.RigWindow.snapshot)."""
    folder = root / (name or when.strftime("%Y%m%d_%H%M%S_%f")[:-3])
    folder.mkdir(parents=True)
    meta = {"created_local": when.isoformat(timespec="milliseconds"), "threshold": 0.15, "source": "ai_set",
            "model": "mo_hinh_gia", "checkpoint": "runs\\mo_hinh_gia\\best.pt", "ai_note": None,
            "camera_mode": {"width": W, "height": H, "fps": 30.0, "fourcc": "MJPG", "exposure": None},
            "cameras": {}, "failed_writes": [], "missing_ports": []}
    for port in ports:
        image = noise_image(seed * 10 + port)
        if port in damaged:
            image = truncate(image)
        if port in torn:
            image = tear(image)
        write_png(folder / f"cam_p{port}.png", image)
        prob = (probs or {}).get(port, ramp_prob())
        if port not in missing_prob:
            write_png(folder / f"prob_blocked_p{port}.png", prob)
        share = bottom_repeat_share(image)
        if meta_share and port in meta_share:
            share = meta_share[port]
        meta["cameras"][str(port)] = {"stamp_s": 1.0, "age_ms": 30.0, "stale": False, "width": W, "height": H,
                                      "index": port - 1, "bottom_repeat_share": share, "source_rejects_damaged": True,
                                      "truncated_frames_so_far": 0, "torn_frames_so_far": 0,
                                      "prob_size": [PW, PH], "blocked_fraction_at_threshold": 0.5}
    if with_meta:
        (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return folder


T0 = datetime(2026, 9, 23, 10, 0, 0)


@pytest.fixture
def snap_root(tmp_path):
    return tmp_path / "ảnh sa bàn" / "rig_snapshots"


def test_import_draft_is_linear_resized_prob_thresholded_into_unicode_project(snap_root, tmp_path):
    folder = write_snapshot(snap_root, T0)
    project = LabelProject(tmp_path / "dự án nhãn", create=True, who="người thử")
    summary = project.import_snapshots(snap_root, threshold=0.5, log=None)
    assert summary["imported"] == [f"{folder.name}_p1", f"{folder.name}_p2"] and not summary["skipped"]
    prob = ramp_prob().astype(np.float32) / 255.0
    linear = cv2.resize(prob, (W, H), interpolation=cv2.INTER_LINEAR)
    nearest = cv2.resize(prob, (W, H), interpolation=cv2.INTER_NEAREST)
    item_id = f"{folder.name}_p1"
    expected = (linear >= 0.5).astype(np.uint8)
    assert not np.array_equal(expected, (nearest >= 0.5).astype(np.uint8))      # phép thử phân biệt được hai cách
    assert np.array_equal(project.label(item_id), expected)
    item = project.item(item_id)
    raw = (folder / "cam_p1.png").read_bytes()
    assert project.path(item_id, "images").read_bytes() == raw                    # chép nguyên byte
    assert item["image"]["sha256"] == L.sha256_bytes(raw) and item["status"] == "draft"
    assert item["source"]["port"] == 1 and item["source"]["snapshot"] == folder.name
    assert item["source"]["snapshot_dir"] == str(folder.resolve())
    assert item["draft"] == {"origin": "snapshot_prob", "model": "mo_hinh_gia", "checkpoint": "runs\\mo_hinh_gia\\best.pt",
                             "threshold": 0.5, "prob_file": f"probs/{item_id}.png", "prob_size": [PW, PH], "note": None}
    assert item["created_by"] == "người thử" and item["source"]["captured_local"] == "2026-09-23T10:00:00.000"
    assert item["label"]["sha256"] == array_sha256(expected) and not item["damage"]["damaged"]
    assert project.edited(item_id).sum() == 0

    other = LabelProject(tmp_path / "ngưỡng thấp", create=True)
    other.import_snapshots(snap_root, threshold=0.3, log=None)
    low = other.label(item_id)
    assert np.array_equal(low, (linear >= 0.3).astype(np.uint8)) and low.sum() > expected.sum()
    assert other.item(item_id)["draft"]["threshold"] == 0.3
    assert draft_from_prob(np.array([[127, 128]], np.uint8), (1, 2), 128 / 255).tolist() == [[0, 1]]  # bằng ngưỡng = BLOCKED
    assert not list(tmp_path.rglob("*.tmp"))


def test_damaged_frames_are_rejected_with_reasons_or_skipped(snap_root, tmp_path):
    folder = write_snapshot(snap_root, T0, ports=(1, 2, 3, 4), damaged=(1,), torn=(4,), meta_share={2: 0.5})
    write_snapshot(snap_root, T0 + timedelta(seconds=5), with_meta=False, name="lan_chup_do_dang")
    project = LabelProject(tmp_path / "p", create=True)
    summary = project.import_snapshots(snap_root, log=None)
    p = {port: project.item(f"{folder.name}_p{port}") for port in (1, 2, 3, 4)}
    assert p[1]["status"] == "rejected" and "truncated_rows" in p[1]["status_reason"] and p[1]["damage"]["truncated_rows"] >= 24
    assert p[2]["status"] == "rejected" and "bottom_repeat_share" in p[2]["status_reason"]
    assert p[2]["damage"]["bottom_repeat_share_from"] == "meta.json" and p[2]["damage"]["truncated_rows"] == 0
    assert p[4]["status"] == "rejected" and "torn_bands" in p[4]["status_reason"] and p[4]["damage"]["truncated_rows"] == 0
    assert p[3]["status"] == "draft" and not p[3]["damage"]["damaged"]
    assert sorted(summary["rejected_damaged"]) == sorted(f"{folder.name}_p{k}" for k in (1, 2, 4))
    assert any("lan_chup_do_dang" in s and "meta.json" in s for s in summary["skipped"])
    with pytest.raises(LabelError, match="hỏng"):
        project.set_status(p[1]["id"], "reviewed")
    rows = p[1]["damage"]["truncated_rows"]
    assert (project.label(p[1]["id"])[-rows:] != IGNORE).any()          # nháp AI tô cả đáy do bộ giải mã tô
    with pytest.raises(LabelError, match="vùng hỏng"):                  # xác nhận thôi chưa đủ: đáy phải là IGNORE
        project.set_status(p[1]["id"], "reviewed", override_damage=True)
    label = project.label(p[1]["id"])
    label[-rows:] = IGNORE
    project.save(p[1]["id"], label)
    item = project.set_status(p[1]["id"], "reviewed", override_damage=True)
    assert item["status"] == "reviewed" and item["damage_override"]["by"] == project.who
    assert item["damage_override"]["damage_region_pixels"] == rows * W
    assert p[4]["damage"]["torn_spans"] == [[40, 48, 60]] and p[4]["damage"]["torn_bands"] == 1   # đúng chỗ tear()
    with pytest.raises(LabelError, match="vùng hỏng"):
        project.set_status(p[4]["id"], "reviewed", override_damage=True)
    label = project.label(p[4]["id"])
    label[40:48, 60:] = IGNORE
    project.save(p[4]["id"], label)
    assert project.set_status(p[4]["id"], "reviewed", override_damage=True)["status"] == "reviewed"
    assert not project.damage_region(p[2]["id"]).any()                # chỉ bottom_repeat_share: không định vị được
    assert project.set_status(p[2]["id"], "reviewed", override_damage=True)["status"] == "reviewed"

    skipping = LabelProject(tmp_path / "q", create=True)
    summary = skipping.import_snapshots(snap_root, skip_damaged=True, log=None)
    assert summary["imported"] == [f"{folder.name}_p3"] and sum("khung hỏng" in s for s in summary["skipped"]) == 3

    old = snap_root.parent / "cu"                    # bộ ảnh cũ không ghi bottom_repeat_share: tính lại trên khung
    folder_old = write_snapshot(old, T0, ports=(1,), damaged=(1,))
    meta = json.loads((folder_old / "meta.json").read_text(encoding="utf-8"))
    del meta["cameras"]["1"]["bottom_repeat_share"]
    (folder_old / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    third = LabelProject(tmp_path / "r", create=True)
    third.import_snapshots(folder_old, log=None)                       # một bộ ảnh cụ thể cũng nhập được
    damage = third.item(f"{folder_old.name}_p1")["damage"]
    assert damage["bottom_repeat_share_from"] == "tính lại trên khung" and damage["bottom_repeat_share"] > 0.9


def test_reimport_is_idempotent_and_failed_writes_are_skipped(snap_root, tmp_path):
    folder = write_snapshot(snap_root, T0)
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    meta["failed_writes"] = ["cam_p2.png"]
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    project = LabelProject(tmp_path / "p", create=True)
    assert project.import_snapshots(snap_root, log=None)["imported"] == [f"{folder.name}_p1"]
    again = project.import_snapshots(snap_root, log=None)
    assert again["imported"] == [] and any("đã có" in s for s in again["skipped"])
    assert len(LabelProject(tmp_path / "p").ids()) == 1
    with pytest.raises(LabelError, match="không trống"):                   # gõ nhầm --project vào thư mục ảnh chụp
        LabelProject(snap_root, create=True)
    assert not (snap_root / "project.json").exists() and not (snap_root / "items").exists()


class FakeSegmenter:
    name, checkpoint, calls = "gia_lap", "runs/gia_lap/best.pt", 0

    def infer(self, images, out_size=None):
        FakeSegmenter.calls += 1
        h, w = images[0].shape[:2]
        return [np.tile(np.linspace(0.0, 1.0, w, dtype=np.float32), (h, 1))], None


def test_missing_prob_gives_ignore_draft_or_runs_the_model(snap_root, tmp_path, monkeypatch):
    folder = write_snapshot(snap_root, T0, missing_prob=(1, 2))
    plain = LabelProject(tmp_path / "p", create=True)
    summary = plain.import_snapshots(snap_root, log=None)
    item_id = f"{folder.name}_p1"
    assert sorted(summary["no_prob"]) == [item_id, f"{folder.name}_p2"]
    assert (plain.label(item_id) == IGNORE).all() and plain.item(item_id)["draft"]["origin"] == "none"
    assert plain.prob(item_id) is None
    with pytest.raises(LabelError, match="xác suất"):
        plain.editor(item_id).regenerate(0.5)
    with pytest.raises(LabelError, match="IGNORE"):
        plain.set_status(item_id, "reviewed")                    # nhãn toàn IGNORE không duyệt được

    FakeSegmenter.calls = 0
    made = []
    model = LabelProject(tmp_path / "m", create=True)
    summary = model.import_snapshots(snap_root, make_segmenter=lambda: made.append(1) or FakeSegmenter(), log=None)
    assert len(made) == 1 and FakeSegmenter.calls == 2 and len(summary["prob_from_model"]) == 2
    prob = np.round(np.tile(np.linspace(0.0, 1.0, W, dtype=np.float32), (H, 1)) * 255).astype(np.uint8)
    assert np.array_equal(model.prob(item_id), prob)
    assert np.array_equal(model.label(item_id), draft_from_prob(prob, (H, W), 0.5))
    assert model.item(item_id)["draft"]["origin"] == "live_segmenter" and model.item(item_id)["draft"]["model"] == "gia_lap"

    clean = LabelProject(tmp_path / "khong_ai", create=True)                      # --no-draft: không dính tới mô hình
    write_snapshot(snap_root.parent / "co_prob", T0)
    clean.import_snapshots(snap_root.parent / "co_prob", draft=False, make_segmenter=lambda: FakeSegmenter(), log=None)
    for i in clean.ids():
        assert (clean.label(i) == IGNORE).all() and clean.prob(i) is None and clean.item(i)["draft"]["origin"] == "none"

    with pytest.raises(LabelError, match="checkpoint"):
        L.load_segmenter(tmp_path / "khong_co.pt")
    checkpoint = tmp_path / "best.pt"
    checkpoint.write_bytes(b"")
    monkeypatch.setitem(sys.modules, "autopark.perception.live", None)              # như môi trường không có torch
    with pytest.raises(LabelError, match="torch"):
        L.load_segmenter(checkpoint)


def test_editor_brush_polygon_regenerate_undo_redo():
    prob = np.tile(np.linspace(0, 255, 80).round().astype(np.uint8), (60, 1))
    start = draft_from_prob(prob, (60, 80), 0.5)
    editor = LabelEditor(start, prob=prob, threshold=0.5)
    assert editor.paint([(5, 10), (30, 10)], BLOCKED, 3)
    assert editor.label[10, 20] == BLOCKED and editor.label[13, 20] == BLOCKED and editor.label[17, 20] == FREE
    assert editor.edited[10, 20] == 1 and editor.edited[17, 20] == 0 and editor.dirty
    assert editor.fill_polygon([(50, 40), (70, 40), (70, 55), (50, 55)], IGNORE)
    assert editor.label[45, 60] == IGNORE and editor.label[35, 60] == BLOCKED and editor.edited[45, 60] == 1
    after_paint = editor.label.copy()
    changed = editor.regenerate(0.8, keep_edits=True)
    draft08 = draft_from_prob(prob, (60, 80), 0.8)
    free = editor.edited == 0
    assert changed == int((after_paint != editor.label).sum()) > 0 and editor.threshold == 0.8
    assert np.array_equal(editor.label[free], draft08[free])
    assert np.array_equal(editor.label[~free], after_paint[~free])            # chỗ đã tô tay giữ nguyên
    final = editor.label.copy()
    assert editor.undo() and editor.threshold == 0.5 and np.array_equal(editor.label, after_paint)
    assert editor.undo() and editor.undo() and not editor.undo()
    assert np.array_equal(editor.label, start) and editor.edited.sum() == 0
    assert editor.redo() and editor.redo() and editor.redo() and not editor.redo()
    assert np.array_equal(editor.label, final) and editor.threshold == 0.8
    editor.undo()
    editor.paint([(1, 1)], FREE, 1)                                           # thao tác mới xóa nhánh làm lại
    assert not editor.redo_stack and not editor.redo()
    editor.regenerate(0.8, keep_edits=False)
    assert np.array_equal(editor.label, draft08) and editor.edited.sum() == 0
    same = int(editor.label[1, 1])
    assert editor.paint([(1, 1)], same, 0) and editor.edited[1, 1] == 1 and editor.label[1, 1] == same   # "đã tô" cũng là thay đổi
    assert not editor.paint([(1, 1)], same, 0)                                # tô lại y hệt: không thêm bước hoàn tác
    with pytest.raises(ValueError):
        editor.paint([(1, 1)], 2, 1)
    small = LabelEditor(start, max_undo=3)
    for k in range(6):
        small.paint([(k * 10, 5)], BLOCKED if k % 2 else IGNORE, 2)
    assert len(small.undo_stack) == 3


def test_save_load_round_trip_and_review_is_bound_to_label_content(snap_root, tmp_path):
    folder = write_snapshot(snap_root, T0)
    project = LabelProject(tmp_path / "p", create=True, who="An")
    project.import_snapshots(snap_root, log=None)
    item_id = f"{folder.name}_p1"
    editor = project.editor(item_id)
    editor.paint([(10, 20), (60, 20)], IGNORE, 4)
    assert project.save(item_id, editor.label, editor.edited, notes="chân bàn ở góc")
    assert not project.save(item_id, editor.label, editor.edited, notes="chân bàn ở góc")        # không đổi: không ghi
    reopened = LabelProject(tmp_path / "p", who="Bình")
    assert np.array_equal(reopened.label(item_id), editor.label)
    assert np.array_equal(reopened.edited(item_id), editor.edited)
    item = reopened.item(item_id)
    assert item["edited_by"] == "An" and item["edited_at"] and item["notes"] == "chân bàn ở góc"
    assert item["label"]["sha256"] == array_sha256(editor.label) and item["label"]["edited_fraction"] > 0
    assert item["label"]["pixels"] == {str(k): int((editor.label == k).sum()) for k in (0, 1, 255)}
    assert [e["action"] for e in item["history"]][:2] == ["nhập", "sửa nhãn"]

    reviewed = reopened.set_status(item_id, "reviewed")
    assert reviewed["reviewed_by"] == "Bình" and reviewed["reviewed_label_sha256"] == array_sha256(editor.label)
    changed = editor.label.copy()
    changed[0, 0] = BLOCKED if changed[0, 0] != BLOCKED else FREE
    reopened.save(item_id, changed, editor.edited)
    assert reopened.item(item_id)["status"] == "draft" and reopened.item(item_id)["reviewed_label_sha256"] is None

    with pytest.raises(LabelError, match="ngoài"):
        reopened.save(item_id, np.full((H, W), 7, np.uint8))
    with pytest.raises(LabelError, match="kích thước"):
        reopened.save(item_id, np.zeros((H, W + 1), np.uint8))
    write_png(reopened.path(item_id, "labels"), np.zeros((H, W), np.uint8))       # sửa file ngoài công cụ
    with pytest.raises(LabelError, match="sha256"):
        reopened.set_status(item_id, "reviewed")
    with pytest.raises(ValueError):
        reopened.set_status(item_id, "xong")


def test_session_groups_chain_within_gap_and_keep_unknown_apart():
    times = {"/a": T0, "/b": T0 + timedelta(seconds=40), "/c": T0 + timedelta(seconds=90),
             "/d": T0 + timedelta(minutes=10), "/e": None}
    groups = session_groups(times, 60)
    assert groups["/a"] == groups["/b"] == groups["/c"] != groups["/d"]            # 40 s và 50 s: nối chuỗi
    assert groups["/e"] not in (groups["/a"], groups["/d"]) and len(set(groups.values())) == 3
    strict = session_groups(times, 45)
    assert strict["/a"] == strict["/b"] != strict["/c"]


def _project_with_sessions(snap_root, tmp_path):
    whens = [T0, T0 + timedelta(seconds=40), T0 + timedelta(seconds=90)]          # một phiên, ba bộ ảnh
    whens += [T0 + timedelta(hours=k) for k in range(1, 7)]                         # sáu phiên một bộ
    folders = [write_snapshot(snap_root, when, seed=k) for k, when in enumerate(whens)]
    project = LabelProject(tmp_path / "dự án", create=True, who="Chi")
    project.import_snapshots(snap_root, log=None)
    return project, folders


def test_export_writes_training_cache_and_splits_by_session(snap_root, tmp_path):
    project, folders = _project_with_sessions(snap_root, tmp_path)
    draft_id, rejected_id = f"{folders[-1].name}_p2", f"{folders[-2].name}_p2"
    for item_id in project.ids():
        if item_id not in (draft_id, rejected_id):
            project.set_status(item_id, "reviewed")
    project.set_status(rejected_id, "rejected", reason="mờ")
    out = tmp_path / "prepared" / "sa_ban_v1"
    result = project.export(out, log=lambda *_: None)
    assert out.is_dir() and not list(out.parent.glob("*.partial_*"))

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    images, masks = np.load(out / "images.npy"), np.load(out / "masks.npy")
    n = len(project.ids()) - 2
    assert result["images"] == n == len(manifest["records"])
    assert images.shape == (n, 384, 512, 3) and images.dtype == np.uint8
    assert masks.shape == (n, 384, 512) and masks.dtype == np.uint8
    assert set(np.unique(masks).tolist()) <= {0, 1, 255}
    assert (masks[:, :48] == 255).all() and (masks[:, -48:] == 255).all()        # đệm letterbox là IGNORE
    assert (masks[:, 48:-48] != 255).any() and (images[:, :48] == 0).all()
    ids = [r["id"] for r in manifest["records"]]
    assert draft_id not in ids and rejected_id not in ids
    record = manifest["records"][3]
    image_rgb, target, _ = letterbox(project.image(record["id"]), project.label(record["id"]), 384, 512)
    assert np.array_equal(images[3], cv2.cvtColor(image_rgb, cv2.COLOR_BGR2RGB))   # ảnh RGB, đúng khung và nhãn
    assert np.array_equal(masks[3], target) and record["pixels"] == {str(k): int((target == k).sum()) for k in (0, 1, 255)}
    assert manifest["mapping"] == {"0": "FREE", "1": "BLOCKED", "255": "IGNORE"}
    assert manifest["self_captured"] is True and manifest["contains_woodscape_images"] is False
    assert "WoodScape" in manifest["licence_note"] and manifest["draft_origins"] == {"snapshot_prob": n}
    assert record["label_sha256"] == array_sha256(project.label(record["id"])) and record["reviewed_by"] == "Chi"
    assert json.loads((out / "TRANSFER_READY.json").read_text(encoding="utf-8"))["mapping_sha256"] == manifest["mapping_sha256"]

    split_of = {r["id"]: r["split"] for r in manifest["records"]}
    first_session = [i for i in ids if any(i.startswith(f.name) for f in folders[:3])]
    assert len(first_session) == 6 and len({split_of[i] for i in first_session}) == 1       # 3 bộ ảnh x 2 camera
    groups = {r["group"] for r in manifest["records"]}
    assert len(groups) == 7 == manifest["grouping"]["sessions"]
    for group in groups:
        assert len({r["split"] for r in manifest["records"] if r["group"] == group}) == 1
    assert all(manifest["splits"][name] for name in ("train", "val", "test")) and not result["warnings"]
    assert check_cache(out)["records"] == n

    with pytest.raises(LabelError, match="đã có"):
        project.export(out, log=lambda *_: None)
    project.export(out, overwrite=True, log=lambda *_: None)
    assert len(list(out.parent.glob("sa_ban_v1.cu_*"))) == 1 and (out / "manifest.json").exists()

    write_png(project.path(ids[0], "images"), noise_image(99))                      # ảnh bị đổi sau khi duyệt
    with pytest.raises(LabelError, match="sha256"):
        project.export(tmp_path / "prepared" / "sa_ban_v2", log=lambda *_: None)


def test_check_cache_catches_a_group_split_across_splits(snap_root, tmp_path):
    project, _ = _project_with_sessions(snap_root, tmp_path)
    for item_id in project.ids():
        project.set_status(item_id, "reviewed")
    out = tmp_path / "c"
    project.export(out, log=lambda *_: None)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    records = manifest["records"]
    moved = next(r for r in records if r["split"] == "train")
    other = next(r for r in records if r["group"] == moved["group"] and r is not moved)
    target = next(name for name in ("val", "test") if manifest["splits"][name])
    manifest["splits"]["train"].remove(moved["index"])
    manifest["splits"][target] = sorted(manifest["splits"][target] + [moved["index"]])
    moved["split"] = target
    assert other["split"] == "train"
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(LabelError, match="vắt qua"):
        check_cache(out)


def test_exported_cache_opens_with_prepared_cache(snap_root, tmp_path):
    pytest.importorskip("torch")
    from autopark.perception.dataset import PreparedCache

    project, _ = _project_with_sessions(snap_root, tmp_path)
    for item_id in project.ids():
        project.set_status(item_id, "reviewed")
    out = tmp_path / "prepared" / "sa_ban_v1"
    project.export(out, log=lambda *_: None)
    cache = PreparedCache.open(out / "manifest.json", require_verified=False)
    assert cache.images.shape == (18, 384, 512, 3) and cache.masks.shape == (18, 384, 512)
    assert sum(len(cache.indices(name)) for name in ("train", "val", "test")) == 18
    assert PreparedCache.open(out / "manifest.json").manifest["mapping_sha256"] == L.MAPPING_SHA256


def test_statistics_compare_reviewed_labels_with_the_draft(snap_root, tmp_path):
    folder = write_snapshot(snap_root, T0, ports=(1, 2, 3), damaged=(3,))
    project = LabelProject(tmp_path / "p", create=True)
    project.import_snapshots(snap_root, log=None)
    first, second = f"{folder.name}_p1", f"{folder.name}_p2"
    project.set_status(first, "reviewed")                                       # nháp được chấp nhận nguyên
    editor = project.editor(second)
    region = editor.label == FREE
    editor.paint([(5, 45), (40, 45)], BLOCKED, 6)                               # người thấy vật cản ở nơi nháp gọi FREE
    project.save(second, editor.label, editor.edited)
    project.set_status(second, "reviewed")
    stats = project.statistics()
    assert stats["items"] == 3 and stats["by_status"] == {"draft": 0, "reviewed": 2, "rejected": 1}
    assert stats["damaged"] == 1 and stats["snapshots"] == 1 and stats["sessions"] == 1
    d = stats["draft_vs_reviewed"]
    missed = int((region & (editor.label == BLOCKED)).sum())
    assert d["items"] == 2 and missed > 0 and d["agreement"] == pytest.approx(1 - missed / (2 * H * W))
    assert d["blocked_drafted_as_free"] > 0 and d["free_drafted_as_blocked"] == 0 and "thiên lệch" in d["note"]
    assert "đã duyệt 2" in L.format_statistics(stats)


def test_command_line_import_stats_export(snap_root, tmp_path, capsys):
    project_dir = tmp_path / "dự án"
    write_snapshot(snap_root, T0)
    assert L.main(["stats", "--project", str(project_dir)]) == 2                    # chưa có dự án
    assert "import" in capsys.readouterr().err
    assert L.main(["import", str(snap_root), "--project", str(project_dir), "--threshold", "0.4", "--who", "Dũng"]) == 0
    assert "Đã nhập 2 ảnh" in capsys.readouterr().out
    assert L.main(["stats", "--project", str(project_dir), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["by_status"]["draft"] == 2
    assert L.main(["export", "--project", str(project_dir), "--out", str(tmp_path / "cache")]) == 2
    assert "đã duyệt" in capsys.readouterr().err
    project = LabelProject(project_dir)
    assert project.item(project.ids()[0])["created_by"] == "Dũng"
    for item_id in project.ids():
        project.set_status(item_id, "reviewed")
    assert L.main(["export", "--project", str(project_dir), "--out", str(tmp_path / "cache")]) == 0
    out = capsys.readouterr().out
    assert "train" in out and (tmp_path / "cache" / "manifest.json").exists()
    assert "CẢNH BÁO: split val rỗng" in out                                     # một phiên: val/test rỗng, có báo
    only_val = ["export", "--project", str(project_dir), "--out", str(tmp_path / "chi_val"), "--ratios", "0", "1", "0"]
    assert L.main(only_val) == 2                                                   # split đã đóng băng ở lần export đầu
    assert "đóng băng" in capsys.readouterr().err and not (tmp_path / "chi_val").exists()
    assert L.main(only_val + ["--resplit"]) == 0                                   # tập chấm riêng: mọi phiên vào val
    assert "CẢNH BÁO" not in capsys.readouterr().out
    manifest = json.loads((tmp_path / "chi_val" / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["splits"]["val"]) == 2 and not manifest["splits"]["train"] and not manifest["warnings"]
    assert manifest["grouping"]["split_assignment"]["resplit"] is True
    assert "split đóng băng" in L.format_statistics(LabelProject(project_dir).statistics())


def QUIET(*_):
    pass


def review_all(project):
    for item_id in project.ids("draft"):
        project.set_status(item_id, "reviewed")


def split_of(out):
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    return {r["id"]: r["split"] for r in manifest["records"]}, manifest


def test_split_is_frozen_per_image_across_exports(snap_root, tmp_path):
    for k in range(8):                                                           # 8 phiên một bộ ảnh x 2 camera
        write_snapshot(snap_root, T0 + timedelta(hours=k), seed=k)
    project = LabelProject(tmp_path / "dự án", create=True)
    project.import_snapshots(snap_root, log=None)
    review_all(project)
    v1 = tmp_path / "prepared" / "sa_ban_v1"
    project.export(v1, log=QUIET)
    first, m1 = split_of(v1)
    assert len(first) == 16 and (project.root / L.SPLIT_FILE).exists()
    groups = sorted({r["group"] for r in m1["records"]})                          # lần đầu: y như split_groups
    assert m1["splits"] == split_groups({k: [r["index"] for r in m1["records"] if r["group"] == g]
                                         for k, g in enumerate(groups)}, L.DEFAULT_SEED)

    later = [T0 + timedelta(hours=k) for k in (8, 9, 10)] + [T0 + timedelta(hours=3, minutes=30)]   # 3 sau, 1 xen giữa
    for k, when in enumerate(later):
        write_snapshot(snap_root, when, seed=20 + k)
    project.import_snapshots(snap_root, log=None)
    review_all(project)
    v2 = tmp_path / "prepared" / "sa_ban_v2"
    result = project.export(v2, log=QUIET)
    second, m2 = split_of(v2)
    assert len(second) == 24 and {i: second[i] for i in first} == first            # không ảnh cũ nào đổi split
    new = set(second) - set(first)
    assert {i for i, s in second.items() if s != "train"} <= {i for i, s in first.items() if s != "train"} | new
    assignment = m2["grouping"]["split_assignment"]
    assert assignment["inherited_sessions"] == 8 and assignment["new_sessions"] == 4 == result["new_sessions"]
    assert assignment["moved_to_train"] == [] and assignment["resplit"] is False and assignment["file"] == L.SPLIT_FILE
    state = json.loads((project.root / L.SPLIT_FILE).read_text(encoding="utf-8"))
    assert state["assigned"] == second and len(state["history"]) == 2 and state["history"][1]["new_sessions"] == 4
    assert check_cache(v2)["records"] == 24

    project.export(tmp_path / "prepared" / "chia_lai", resplit=True, log=QUIET)   # chia lại từ đầu: ảnh cũ đổi split,
    third, _ = split_of(tmp_path / "prepared" / "chia_lai")                         # tức phép thử trên phân biệt được
    assert any(third[i] != first[i] for i in first)


def test_bridging_snapshot_moves_merged_sessions_to_train_only(snap_root, tmp_path):
    whens = [T0, T0 + timedelta(seconds=100)] + [T0 + timedelta(hours=k) for k in range(1, 7)]
    folders = [write_snapshot(snap_root, when, seed=k) for k, when in enumerate(whens)]
    a, c = folders[0].name, folders[1].name
    project = LabelProject(tmp_path / "p", create=True)
    project.import_snapshots(snap_root, log=None)
    review_all(project)
    for seed in range(60):                                   # tìm seed đặt hai phiên A, C (cách 100 s) vào hai split khác
        project.export(tmp_path / f"v1_{seed}", seed=seed, resplit=True, log=QUIET)
        first, _ = split_of(tmp_path / f"v1_{seed}")
        if first[f"{a}_p1"] != first[f"{c}_p1"]:
            break
    else:
        pytest.fail("không có seed nào chia A và C vào hai split khác nhau")
    bridge = write_snapshot(snap_root, T0 + timedelta(seconds=50), seed=99)        # bộ ảnh mới nối A-B-C thành một phiên
    project.import_snapshots(snap_root, log=None)
    review_all(project)
    result = project.export(tmp_path / "v2", seed=seed, log=QUIET)
    second, manifest = split_of(tmp_path / "v2")
    merged = [i for i in second if i.startswith((a, c, bridge.name))]
    assert len(merged) == 6 and {second[i] for i in merged} == {"train"}
    assert len({r["group"] for r in manifest["records"] if r["id"] in merged}) == 1
    moved = manifest["grouping"]["split_assignment"]["moved_to_train"]
    assert len(moved) == 1 and moved[0]["from"] == sorted({first[f"{a}_p1"], first[f"{c}_p1"]})
    assert moved[0]["items"] == sorted(i for i in merged if i in first and first[i] != "train")
    assert result["moved_to_train"] == moved and any("dời về train" in w for w in manifest["warnings"])
    for item_id, split in first.items():                                          # chỉ được dời VỀ train
        assert second[item_id] in (split, "train")
    assert check_cache(tmp_path / "v2")["records"] == len(second)


def test_split_parameters_are_frozen_unless_resplit(snap_root, tmp_path):
    project, _ = _project_with_sessions(snap_root, tmp_path)
    review_all(project)
    project.export(tmp_path / "v1", log=QUIET)
    before = (project.root / L.SPLIT_FILE).read_bytes()
    for kwargs in ({"seed": 1}, {"ratios": (0.6, 0.2, 0.2)}, {"session_gap_s": 30.0}):
        with pytest.raises(LabelError, match="đóng băng"):
            project.export(tmp_path / "v2", log=QUIET, **kwargs)
    assert not (tmp_path / "v2").exists() and not list(tmp_path.glob("v2.partial_*"))
    assert (project.root / L.SPLIT_FILE).read_bytes() == before
    project.export(tmp_path / "v2", seed=1, resplit=True, log=QUIET)
    _, manifest = split_of(tmp_path / "v2")
    assert manifest["grouping"]["split_assignment"]["resplit"] is True
    assert manifest["grouping"]["split_assignment"]["frozen_items_before"] == 0
    state = json.loads((project.root / L.SPLIT_FILE).read_text(encoding="utf-8"))
    assert state["seed"] == 1 and [h["resplit"] for h in state["history"]] == [False, True]
    assert state["history"][1]["discarded_assignments"] == 18
    project.export(tmp_path / "v3", seed=1, log=QUIET)                              # tham số mới đã đóng băng
    (project.root / L.SPLIT_FILE).write_text(json.dumps({"kind": "khac", "assigned": {}}), encoding="utf-8")
    with pytest.raises(LabelError, match="không phải file split"):
        project.export(tmp_path / "v4", seed=1, log=QUIET)


@pytest.mark.parametrize("middle", ["rejected", "draft", "skipped"])
def test_session_chain_runs_over_snapshots_that_are_not_exported(snap_root, tmp_path, middle):
    """A (0 s), B (50 s), C (100 s): B không vào cache (bị loại, còn nháp, hay bị bỏ lúc nhập) vẫn nối A với C."""
    a = write_snapshot(snap_root, T0, seed=1)
    b = write_snapshot(snap_root, T0 + timedelta(seconds=50), seed=2, damaged=() if middle == "draft" else (1, 2))
    c = write_snapshot(snap_root, T0 + timedelta(seconds=100), seed=3)
    for k in range(1, 5):
        write_snapshot(snap_root, T0 + timedelta(hours=k), seed=10 + k)
    for seed in range(5):                            # một seed có thể tình cờ đặt A và C chung split; nhóm thì không
        project = LabelProject(tmp_path / f"p{seed}", create=True)
        project.import_snapshots(snap_root, skip_damaged=middle == "skipped", log=None)
        known = project.root / L.SNAPSHOTS_FILE
        assert str(b.resolve()) in json.loads(known.read_text(encoding="utf-8"))["snapshots"]
        if middle != "skipped":          # B là ảnh trong dự án: tự nó phải nối chuỗi, không nhờ snapshots.json
            known.unlink()               # (như dự án nhập bằng bản trước khi có file này)
        middle_ids = [i for i in project.ids() if i.startswith(b.name)]
        assert len(middle_ids) == (0 if middle == "skipped" else 2)
        assert all(project.item(i)["status"] == ("draft" if middle == "draft" else "rejected") for i in middle_ids)
        for item_id in project.ids("draft"):
            if item_id not in middle_ids:
                project.set_status(item_id, "reviewed")
        stats = project.statistics()
        project.export(tmp_path / f"out{seed}", seed=seed, log=QUIET)
        _, manifest = split_of(tmp_path / f"out{seed}")
        records = {r["id"]: r for r in manifest["records"]}
        ends = [records[f"{name}_p{port}"] for name in (a.name, c.name) for port in (1, 2)]
        assert len({r["group"] for r in ends}) == 1 and len({r["split"] for r in ends}) == 1
        assert manifest["grouping"]["sessions"] == stats["reviewed_sessions"] == stats["sessions"] == 5


def test_save_resyncs_a_stale_sidecar_so_review_works_again(snap_root, tmp_path, monkeypatch):
    folder = write_snapshot(snap_root, T0, ports=(1, 2, 3))
    project = LabelProject(tmp_path / "p", create=True)
    project.import_snapshots(snap_root, log=None)
    outside, crashed, reviewed = (f"{folder.name}_p{k}" for k in (1, 2, 3))
    changed = project.label(outside)                                  # 1) file nhãn bị sửa ngoài công cụ
    changed[:10] = IGNORE
    write_png(project.path(outside, "labels"), changed)
    editor = project.editor(crashed)                                  # 2) ghi bị ngắt giữa file nhãn và sidecar
    editor.paint([(20, 20), (60, 20)], IGNORE, 4)

    def power_cut(_item):
        raise OSError(5, "mất điện giả lập")

    monkeypatch.setattr(project, "_write_item", power_cut)
    with pytest.raises(OSError):
        project.save(crashed, editor.label, editor.edited)
    monkeypatch.undo()
    project.set_status(reviewed, "reviewed")                          # 3) ảnh đã duyệt, file nhãn bị đổi ngoài công cụ
    other = project.label(reviewed)
    other[-10:] = IGNORE
    write_png(project.path(reviewed, "labels"), other)

    reopened = LabelProject(project.root)
    for item_id in (outside, crashed, reviewed):
        with pytest.raises(LabelError, match="sha256"):
            reopened.set_status(item_id, "reviewed")
        ed = reopened.editor(item_id)
        assert reopened.save(item_id, ed.label, ed.edited)           # "mở lại ảnh và lưu" thật sự đồng bộ sidecar
        assert not reopened.save(item_id, ed.label, ed.edited)
        item = reopened.item(item_id)
        assert item["label"]["sha256"] == array_sha256(ed.label)
        assert "đồng bộ lại sidecar" in [e["action"] for e in item["history"]]
    assert np.array_equal(reopened.label(crashed), editor.label) and np.array_equal(reopened.label(outside), changed)
    item = reopened.item(reviewed)
    assert item["status"] == "draft" and item["reviewed_label_sha256"] is None      # khác nội dung lúc duyệt
    for item_id in (outside, crashed, reviewed):
        assert reopened.set_status(item_id, "reviewed")["reviewed_label_sha256"] == array_sha256(reopened.label(item_id))
    same = reopened.editor(outside)                                   # sidecar khớp: chỉ đổi "đã tô" thì vẫn đã duyệt
    same.edited[0, 0] = 1
    assert reopened.save(outside, same.label, same.edited) and reopened.item(outside)["status"] == "reviewed"


def test_export_aborts_if_the_project_changes_while_it_runs(snap_root, tmp_path, monkeypatch):
    project, _ = _project_with_sessions(snap_root, tmp_path)
    review_all(project)
    victim = project.ids()[-1]
    out = tmp_path / "prepared" / "sa_ban_v1"
    real_sessions, real_letterbox, done = L.session_groups, L.letterbox, []

    def edit_meanwhile(*args, **kwargs):             # cửa sổ gán nhãn tự lưu sau vòng kiểm đầu, trước khi ghi cache
        if not done:
            done.append(1)
            gui = LabelProject(project.root, who="cửa sổ khác")
            label = gui.label(victim)
            label[:5] = IGNORE
            assert gui.save(victim, label)
        return real_sessions(*args, **kwargs)

    monkeypatch.setattr(L, "session_groups", edit_meanwhile)
    with pytest.raises(LabelError, match="trong lúc export"):
        project.export(out, log=QUIET)
    assert not out.exists() and not list(out.parent.glob("*.partial_*"))
    assert not (project.root / L.SPLIT_FILE).exists()                 # export hỏng không đóng băng gì
    monkeypatch.undo()

    project = LabelProject(project.root)
    project.set_status(victim, "reviewed")
    reviewed_label = project.label(victim)
    done.clear()

    def overwrite_meanwhile(*args, **kwargs):        # file nhãn bị ghi đè thẳng (sidecar vẫn "đã duyệt", sha256 cũ)
        if not done:
            done.append(1)
            changed = reviewed_label.copy()
            changed[-5:] = IGNORE
            write_png(project.path(victim, "labels"), changed)
        return real_sessions(*args, **kwargs)

    monkeypatch.setattr(L, "session_groups", overwrite_meanwhile)
    with pytest.raises(LabelError, match="nhãn đổi trong lúc export"):
        project.export(out, log=QUIET)
    assert not out.exists() and not list(out.parent.glob("*.partial_*"))
    monkeypatch.undo()
    write_png(project.path(victim, "labels"), reviewed_label)        # trả lại đúng nhãn đã duyệt
    done.clear()

    def reject_meanwhile(*args, **kwargs):           # loại ảnh (nhãn không đổi) giữa lúc đang ghi cache
        if not done:
            done.append(1)
            LabelProject(project.root, who="cửa sổ khác").set_status(victim, "rejected", reason="mờ")
        return real_letterbox(*args, **kwargs)

    monkeypatch.setattr(L, "letterbox", reject_meanwhile)
    with pytest.raises(LabelError, match="rejected"):
        project.export(out, log=QUIET)
    assert not out.exists() and not list(out.parent.glob("*.partial_*"))


def test_failed_export_removes_its_partial_folder(snap_root, tmp_path, monkeypatch):
    project, _ = _project_with_sessions(snap_root, tmp_path)
    review_all(project)
    real, calls = L.letterbox, []

    def broken(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("lỗi giữa chừng")
        return real(*args, **kwargs)

    monkeypatch.setattr(L, "letterbox", broken)
    out = tmp_path / "prepared" / "sa_ban_v1"
    with pytest.raises(RuntimeError, match="giữa chừng"):
        project.export(out, log=QUIET)
    assert not out.exists() and list(out.parent.iterdir()) == []      # memmap đã nhả, thư mục dở bị xóa
    assert not (project.root / L.SPLIT_FILE).exists()


def test_overwrite_refuses_while_the_old_cache_is_open(snap_root, tmp_path, capsys):
    project, _ = _project_with_sessions(snap_root, tmp_path)
    review_all(project)
    out = tmp_path / "prepared" / "sa_ban_v1"
    args = ["export", "--project", str(project.root), "--out", str(out), "--overwrite"]
    assert L.main(args) == 0
    capsys.readouterr()
    manifest = (out / "manifest.json").read_bytes()
    held = np.load(out / "images.npy", mmap_mode="r")                 # như PreparedCache trong lúc huấn luyện
    try:
        code = L.main(args)
        err = capsys.readouterr().err
        if sys.platform == "win32":                                    # POSIX cho đổi tên thư mục có file đang mở
            assert code == 2 and "đang mở" in err and "huấn luyện" in err
            assert sorted(p.name for p in out.parent.iterdir()) == ["sa_ban_v1"]   # không .partial_*, không .cu_*
            assert (out / "manifest.json").read_bytes() == manifest
    finally:
        del held
    assert L.main(args) == 0
    assert (out / "manifest.json").exists() and not list(out.parent.glob("*.partial_*"))
    assert list(out.parent.glob("sa_ban_v1.cu_*"))


@pytest.mark.parametrize("extra", [["--threshold", "15"], ["--threshold", "0"], ["--threshold", "nan"],
                                   ["--bottom-repeat-limit", "-0.1"], ["--bottom-repeat-limit", "1.5"],
                                   ["--frame-age-limit-ms", "0"], ["--frame-age-limit-ms", "nan"]])
def test_cli_rejects_bad_import_arguments_without_creating_a_project(tmp_path, capsys, extra):
    project, source = tmp_path / "proj", tmp_path / "src"
    source.mkdir()
    with pytest.raises(SystemExit) as exc:
        L.main(["import", str(source), "--project", str(project), *extra])
    assert exc.value.code == 2 and not project.exists() and extra[0] in capsys.readouterr().err


def test_cli_missing_source_or_negative_gap_creates_nothing(tmp_path, capsys):
    project = tmp_path / "proj"
    assert L.main(["import", str(tmp_path / "không có"), "--project", str(project)]) == 2
    assert "Không phải thư mục" in capsys.readouterr().err and not project.exists()
    with pytest.raises(SystemExit) as exc:
        L.main(["stats", "--project", str(project), "--session-gap", "-5"])
    assert exc.value.code == 2 and not project.exists()


def test_redo_or_undo_during_a_stroke_closes_the_stroke_first():
    editor = LabelEditor(np.zeros((20, 20), np.uint8))
    editor.paint([(2, 2)], BLOCKED, 1)
    assert editor.undo() and editor.redo_stack
    editor.begin_stroke(IGNORE, 1)
    editor.stroke_to(10, 10)
    assert not editor.redo()                     # nét mới đóng thành một bước, xóa nhánh làm lại; không gộp vào nét
    assert not editor.stroking and editor.label[10, 10] == IGNORE and editor.label[2, 2] == FREE
    assert len(editor.undo_stack) == 1 and editor.undo() and (editor.label == FREE).all()


# ---------------------------------------------------------------- phiên đóng băng nhận ra qua ảnh không còn duyệt
def test_split_sessions_recognises_a_frozen_session_through_images_not_exported_now():
    splits, split_of, new_keys, moved = L.split_sessions({"S": [0]}, ["B"], {"A": "val"}, 0,
                                                         session_of={"A": "S", "B": "S"})
    assert splits["val"] == [0] and split_of == {"S": "val"} and new_keys == [] and moved == []
    splits, _, _, moved = L.split_sessions({"S": [0, 1]}, ["B", "C"], {"A": "val", "C": "test"}, 0,
                                           session_of={"A": "S", "B": "S", "C": "S"})
    assert splits["train"] == [0, 1] and moved == [{"session": "S", "from": ["test", "val"], "items": ["A", "C"]}]
    splits, _, new_keys, _ = L.split_sessions({"S": [0]}, ["B"], {"A": "val"}, 0)         # không có session_of: như cũ
    assert new_keys == ["S"]


@pytest.mark.parametrize("demote", ["edit", "draft", "rejected"])
def test_a_frozen_session_keeps_its_split_when_its_frozen_images_are_no_longer_reviewed(snap_root, tmp_path, demote):
    """A (p1, T0) được export; sau đó A về nháp (sửa sau duyệt, 'Về nháp') hay bị loại. B chụp 30 s sau A (cùng phiên)
    được duyệt ở lần export sau: B phải theo split đóng băng của A, không được chia lại như phiên mới (rò rỉ)."""
    a = write_snapshot(snap_root, T0, ports=(1,), seed=1)
    for k in range(1, 7):
        write_snapshot(snap_root, T0 + timedelta(hours=k), ports=(1,), seed=10 + k)
    later = snap_root.parent / "chup_sau"
    b = write_snapshot(later, T0 + timedelta(seconds=30), ports=(1,), seed=2)
    for k in range(7, 10):
        write_snapshot(later, T0 + timedelta(hours=k), ports=(1,), seed=10 + k)
    a_id, b_id = f"{a.name}_p1", f"{b.name}_p1"
    template = LabelProject(tmp_path / "mau", create=True)
    template.import_snapshots(snap_root, log=None)
    for seed in range(15):
        root = tmp_path / f"p{seed}"
        shutil.copytree(template.root, root)
        project = LabelProject(root)
        review_all(project)
        project.export(tmp_path / f"v1_{seed}", seed=seed, log=QUIET)
        frozen = project.split_state()["assigned"]
        if demote == "edit":                                     # sửa sau khi duyệt: save tự đưa về nháp
            label = project.label(a_id)
            label[0, 0] = IGNORE if label[0, 0] != IGNORE else FREE
            project.save(a_id, label)
        else:
            project.set_status(a_id, demote)
        assert project.item(a_id)["status"] == ("rejected" if demote == "rejected" else "draft")
        project.import_snapshots(later, log=None)
        for item_id in project.ids("draft"):
            if item_id != a_id:
                project.set_status(item_id, "reviewed")
        result = project.export(tmp_path / f"v2_{seed}", seed=seed, log=QUIET)
        second, manifest = split_of(tmp_path / f"v2_{seed}")
        assert a_id not in second
        assert second[b_id] == frozen[a_id], f"seed {seed}: B vào {second[b_id]}, A đã đóng băng ở {frozen[a_id]}"
        assert result["moved_to_train"] == [] and not any("dời về train" in w for w in manifest["warnings"])
        project.set_status(a_id, "reviewed")                     # A duyệt lại: không có gì phải dời
        result = project.export(tmp_path / f"v3_{seed}", seed=seed, log=QUIET)
        third, _ = split_of(tmp_path / f"v3_{seed}")
        assert result["moved_to_train"] == [] and third[a_id] == third[b_id] == frozen[a_id]


def test_moved_session_records_its_unreviewed_frozen_images_as_train(snap_root, tmp_path):
    """Phiên bị dời về train: ảnh đã đóng băng của phiên mà nay chưa duyệt cũng được ghi train trong splits.json, để
    khi duyệt lại nó không kéo theo cảnh báo 'dời về train' lần nữa."""
    whens = [T0, T0 + timedelta(seconds=100)] + [T0 + timedelta(hours=k) for k in range(1, 7)]
    folders = [write_snapshot(snap_root, when, ports=(1, 2), seed=k) for k, when in enumerate(whens)]
    a, c = folders[0].name, folders[1].name
    template = LabelProject(tmp_path / "mau", create=True)
    template.import_snapshots(snap_root, log=None)
    for seed in range(60):
        root = tmp_path / f"p{seed}"
        shutil.copytree(template.root, root)
        project = LabelProject(root)
        review_all(project)
        project.export(tmp_path / f"v1_{seed}", seed=seed, log=QUIET)
        first = project.split_state()["assigned"]
        if first[f"{a}_p1"] != first[f"{c}_p1"] and "train" not in (first[f"{a}_p1"], first[f"{c}_p1"]):
            break
    else:
        pytest.fail("không có seed nào đặt A và C vào val và test")
    project.set_status(f"{a}_p2", "draft")                      # một ảnh val/test của phiên A về nháp
    bridge = write_snapshot(snap_root, T0 + timedelta(seconds=50), ports=(1, 2), seed=99)
    project.import_snapshots(snap_root, log=None)
    for item_id in project.ids("draft"):
        if item_id != f"{a}_p2":
            project.set_status(item_id, "reviewed")
    result = project.export(tmp_path / "v2", seed=seed, log=QUIET)
    moved = result["moved_to_train"]
    assert len(moved) == 1 and f"{a}_p2" in moved[0]["items"]
    assert project.split_state()["assigned"][f"{a}_p2"] == "train"
    project.set_status(f"{a}_p2", "reviewed")
    result = project.export(tmp_path / "v3", seed=seed, log=QUIET)
    third, _ = split_of(tmp_path / "v3")
    assert result["moved_to_train"] == [] and third[f"{a}_p2"] == third[f"{bridge.name}_p1"] == "train"


# ---------------------------------------------------------------- tập chấm tách rời khỏi cache huấn luyện
def hand_label_all(project):
    """Như người tô tay từ đầu trên dự án --no-draft: nháp toàn IGNORE -> tô FREE rồi duyệt."""
    for item_id in project.ids("draft"):
        label = project.label(item_id)
        label[:] = FREE
        project.save(item_id, label)
        project.set_status(item_id, "reviewed")


def test_export_disjoint_from_refuses_images_snapshots_or_sessions_of_the_training_cache(snap_root, tmp_path, capsys):
    for k in range(4):
        write_snapshot(snap_root, T0 + timedelta(hours=k), seed=k)
    train = LabelProject(tmp_path / "huấn luyện", create=True)
    train.import_snapshots(snap_root, log=None)                       # bước 2 cũ: nhập cả runs/rig_snapshots
    review_all(train)
    v1 = tmp_path / "prepared" / "sa_ban_v1"
    train.export(v1, log=QUIET)

    same = LabelProject(tmp_path / "chấm chung", create=True)         # bước 7 cũ: nhập lại 2 bộ ảnh cuối của cùng thư mục
    same.import_snapshots(sorted(snap_root.iterdir())[-2:], draft=False, log=None)
    hand_label_all(same)
    with pytest.raises(LabelError) as caught:
        same.export(tmp_path / "prepared" / "cham_chung", ratios=(0, 1, 0), disjoint_from=[v1], log=QUIET)
    message = str(caught.value)
    assert "4 ảnh đã duyệt trùng" in message and "trùng sha256 ảnh" in message and "cùng bộ ảnh" in message
    assert not (tmp_path / "prepared" / "cham_chung").exists() and not (same.root / L.SPLIT_FILE).exists()

    near = snap_root.parent / "rig_snapshots_cham_gan"                # thư mục riêng nhưng chụp 30 s sau một bộ huấn luyện
    write_snapshot(near, T0 + timedelta(hours=3, seconds=30), seed=50)
    close = LabelProject(tmp_path / "chấm gần", create=True)
    close.import_snapshots(near, draft=False, log=None)
    hand_label_all(close)
    with pytest.raises(LabelError, match="cùng phiên") as caught:
        close.export(tmp_path / "prepared" / "cham_gan", ratios=(0, 1, 0), disjoint_from=[v1 / "manifest.json"],
                     log=QUIET)
    assert "sha256" not in str(caught.value).split("\n")[1] and "cùng bộ ảnh" not in str(caught.value)

    apart = snap_root.parent / "rig_snapshots_cham"                   # phiên chấm riêng: thư mục riêng, cách > 60 s
    for k in (10, 11):
        write_snapshot(apart, T0 + timedelta(hours=k), seed=60 + k)
    clean = tmp_path / "chấm riêng"
    assert L.main(["import", str(apart), "--project", str(clean), "--no-draft"]) == 0
    hand_label_all(LabelProject(clean))
    out = tmp_path / "prepared" / "cham_rieng"
    assert L.main(["export", "--project", str(clean), "--out", str(out), "--ratios", "0", "1", "0",
                   "--disjoint-from", str(v1)]) == 0
    assert "tách rời khỏi" in capsys.readouterr().out
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    (entry,) = manifest["disjoint_from"]
    assert entry["manifest_sha256"] == L.sha256_bytes((v1 / "manifest.json").read_bytes())
    assert entry["checked"] == ["image_sha256", "snapshot", "session_gap"] and entry["unchecked_time"] == 0
    assert len(manifest["splits"]["val"]) == 4 and not manifest["warnings"]
    assert L.main(["export", "--project", str(same.root), "--out", str(tmp_path / "x"), "--ratios", "0", "1", "0",
                   "--disjoint-from", str(v1)]) == 2
    assert "trùng" in capsys.readouterr().err
    with pytest.raises(LabelError, match="không thấy manifest"):
        LabelProject(clean).export(tmp_path / "y", ratios=(0, 1, 0), disjoint_from=[tmp_path / "khong_co"], log=QUIET)


# ---------------------------------------------------------------- khung cũ (camera treo)
def set_camera_meta(folder, port, **values):
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    meta["cameras"][str(port)].update(values)
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")


def test_stale_frame_is_flagged_by_age_and_grouped_by_the_frame_time(snap_root, tmp_path):
    """Camera p1 treo lúc 10:00:10; bộ ảnh 10:30 ghi lại khung đó (age_ms ≈ 1,79e6, stale=True). Khung đó là của phiên
    10:00, không phải phiên 10:30: bị đánh dấu hỏng, và nếu vẫn duyệt thì xếp chung phiên 10:00."""
    s1 = write_snapshot(snap_root, T0, seed=1)
    s2 = write_snapshot(snap_root, T0 + timedelta(seconds=5), seed=2)
    s3 = write_snapshot(snap_root, T0 + timedelta(minutes=30), seed=3)
    set_camera_meta(s3, 1, age_ms=1.79e6, stale=True)
    others = [write_snapshot(snap_root, T0 + timedelta(hours=k), seed=10 + k) for k in range(1, 6)]
    set_camera_meta(others[0], 2, age_ms=700.0, stale=True)          # chế độ bộ AI: > 0,5 s nhưng camera khỏe
    project = LabelProject(tmp_path / "p", create=True)
    project.import_snapshots(snap_root, log=None)
    stale_id = f"{s3.name}_p1"
    item = project.item(stale_id)
    assert item["status"] == "rejected" and "khung cũ" in item["status_reason"] and item["damage"]["frame_too_old"]
    assert item["damage"]["frame_age_ms"] == 1.79e6 and item["damage"]["truncated_rows"] == 0
    assert item["source"]["frame_captured_local"] == "2026-09-23T10:00:10.000"
    fine = project.item(f"{others[0].name}_p2")
    assert fine["status"] == "draft" and not fine["damage"]["damaged"] and fine["damage"]["frame_age_ms"] == 700.0
    with pytest.raises(LabelError, match="hỏng"):
        project.set_status(stale_id, "reviewed")
    assert not project.damage_region(stale_id).any()                   # không có vùng nào để tô
    project.set_status(stale_id, "reviewed", override_damage=True)
    review_all(project)
    stats = project.statistics()
    out = tmp_path / "cache"
    project.export(out, log=QUIET)
    _, manifest = split_of(out)
    record = {r["id"]: r for r in manifest["records"]}
    assert record[stale_id]["group"] == record[f"{s2.name}_p1"]["group"] == record[f"{s1.name}_p2"]["group"]
    assert record[stale_id]["group"] != record[f"{s3.name}_p2"]["group"]
    assert record[stale_id]["split"] == record[f"{s1.name}_p1"]["split"]
    assert record[stale_id]["frame_captured_local"] == "2026-09-23T10:00:10.000"
    assert manifest["grouping"]["sessions"] == stats["reviewed_sessions"] == stats["sessions"] == 7

    old = LabelProject(tmp_path / "q", create=True)                    # bộ ảnh cũ không ghi age_ms: không xét
    folder = write_snapshot(snap_root.parent / "cu", T0, ports=(1,))
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    del meta["cameras"]["1"]["age_ms"]
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    old.import_snapshots(folder, log=None)
    assert old.item(f"{folder.name}_p1")["damage"]["frame_age_ms"] is None
    assert old.item(f"{folder.name}_p1")["status"] == "draft"
    loose = LabelProject(tmp_path / "r", create=True)                  # giới hạn nới ra: khung đó không bị đánh dấu
    loose.import_snapshots(s3, frame_age_limit_ms=2e6, log=None)
    assert loose.item(stale_id)["status"] == "draft" and "frame_captured_local" not in loose.item(stale_id)["source"]


# ---------------------------------------------------------------- vùng hỏng phải là IGNORE khi duyệt/export
def test_torn_band_spans_count_exactly_what_torn_bands_counts():
    images = [noise_image(1), tear(noise_image(2)), tear(tear(noise_image(3), row0=16, col0=20), row0=64, col0=80),
              truncate(tear(noise_image(4), row0=8, col0=40)), np.full((H, W, 3), 128, np.uint8)]
    real = sorted((L.PROJECT / "runs" / "rig_snapshots").glob("*/cam_p*.png"))   # bộ ảnh thật nếu có (chỉ đọc)
    images += [L.read_png(p, cv2.IMREAD_COLOR) for p in real]
    for image in images:
        rows = truncated_rows(image)
        spans = L.torn_band_spans(image, exclude_bottom_rows=rows)
        assert len(spans) == torn_bands(image, exclude_bottom_rows=rows)
    assert L.torn_band_spans(images[2]) == [[16, 24, 20], [64, 72, 80]]
    region = L.damage_region(L.frame_damage(images[3]), (H, W))
    assert region[-24:].all() and region[8:16, 40:].all() and not region[8:16, :40].any() and not region[:8].any()


def test_export_refuses_a_reviewed_damaged_frame_whose_damage_is_not_ignore(snap_root, tmp_path):
    """Ảnh hỏng được duyệt bằng bản cũ (chỉ cần xác nhận): export vẫn phải bắt vùng hỏng còn FREE/BLOCKED."""
    folder = write_snapshot(snap_root, T0, ports=(1, 2), damaged=(1,))
    project = LabelProject(tmp_path / "p", create=True)
    project.import_snapshots(snap_root, log=None)
    damaged, clean = f"{folder.name}_p1", f"{folder.name}_p2"
    project.set_status(clean, "reviewed")
    sidecar = json.loads(project.path(damaged, "items").read_text(encoding="utf-8"))
    sidecar.update({"status": "reviewed", "reviewed_label_sha256": sidecar["label"]["sha256"],
                    "damage_override": {"at": "2026-09-24T09:00:00+07:00", "by": "bản cũ"}})
    del sidecar["damage"]["torn_spans"]                                 # sidecar của bản trước khi có torn_spans
    project.path(damaged, "items").write_text(json.dumps(sidecar, ensure_ascii=False), encoding="utf-8")
    project = LabelProject(project.root)
    with pytest.raises(LabelError, match="vùng hỏng") as caught:
        project.export(tmp_path / "cache", log=QUIET)
    assert damaged in str(caught.value) and not (tmp_path / "cache").exists()
    rows = sidecar["damage"]["truncated_rows"]
    label = project.label(damaged)
    label[-rows:] = IGNORE
    project.save(damaged, label)                                        # về nháp; duyệt lại qua đường kiểm mới
    project.set_status(damaged, "reviewed", override_damage=True)
    project.export(tmp_path / "cache", log=QUIET)
    manifest = json.loads((tmp_path / "cache" / "manifest.json").read_text(encoding="utf-8"))
    index = next(r["index"] for r in manifest["records"] if r["id"] == damaged)
    mask = np.load(tmp_path / "cache" / "masks.npy")[index]
    _, target, _ = letterbox(project.image(damaged), label, 384, 512)
    assert np.array_equal(mask, target)
    scale = 512 / W                                                     # 160x90 -> 512x288, đệm 48 dòng trên/dưới
    assert (mask[48 + int(np.ceil((H - rows) * scale)) + 1:] == IGNORE).all()


def test_fill_mask_is_one_undo_step_and_marks_pixels_as_edited():
    prob = np.tile(np.linspace(0, 255, 20).round().astype(np.uint8), (10, 1))
    editor = LabelEditor(draft_from_prob(prob, (10, 20)), prob=prob)
    mask = np.zeros((10, 20), bool)
    mask[-3:] = True
    assert editor.fill_mask(mask, IGNORE) and (editor.label[-3:] == IGNORE).all() and editor.edited[-3:].all()
    assert not editor.fill_mask(mask, IGNORE)                          # không đổi gì: không thêm bước
    editor.regenerate(0.3, keep_edits=True)
    assert (editor.label[-3:] == IGNORE).all()                          # "Tô lại theo AI" giữ chỗ đã tô
    assert editor.undo() and editor.undo() and (editor.label[-3:] != IGNORE).any()
    with pytest.raises(LabelError):
        editor.fill_mask(np.zeros((5, 5), bool), IGNORE)


def test_real_truncated_frame_needs_its_bottom_ignored_before_review(tmp_path):
    """Bộ ảnh thật 20260923_145753_910 (chỉ đọc): cổng 1 bị cắt 352/720 dòng, nháp AI gọi phần lớn đáy đó là FREE."""
    folder = L.PROJECT / "runs" / "rig_snapshots" / "20260923_145753_910"
    if not (folder / "meta.json").exists():
        pytest.skip("không có bộ ảnh thật (runs/ không vào git)")
    project = LabelProject(tmp_path / "p", create=True)
    project.import_snapshots(folder, log=None)
    item_id = f"{folder.name}_p1"
    damage = project.item(item_id)["damage"]
    rows = damage["truncated_rows"]
    assert rows == 352 and damage["damaged"]
    assert (project.label(item_id)[-rows:] == FREE).sum() > 400_000
    with pytest.raises(LabelError, match="vùng hỏng"):
        project.set_status(item_id, "reviewed", override_damage=True)
    editor = project.editor(item_id)
    editor.fill_mask(project.damage_region(item_id), IGNORE)
    project.save(item_id, editor.label, editor.edited)
    assert project.set_status(item_id, "reviewed", override_damage=True)["damage_override"]["damage_region_pixels"] \
        == rows * 1280


# ---------------------------------------------------------------- file hỏng, ghi bền
@pytest.mark.parametrize("content", [b"", b"[]", b"\xff", b'{"khong_co_id": 1}'])
def test_a_broken_sidecar_stops_the_project_and_names_the_file(snap_root, tmp_path, capsys, content):
    folder = write_snapshot(snap_root, T0, ports=(1, 2, 3))
    project = LabelProject(tmp_path / "p", create=True)
    project.import_snapshots(snap_root, log=None)
    broken = project.path(f"{folder.name}_p2", "items")
    broken.write_bytes(content)
    with pytest.raises(LabelError, match="1 sidecar hỏng") as caught:
        LabelProject(project.root)
    assert broken.name in str(caught.value)
    assert L.main(["stats", "--project", str(project.root)]) == 2
    err = capsys.readouterr().err
    assert broken.name in err and "Traceback" not in err
    if content in (b"", b"[]", b"\xff"):                                 # export đọc lại sidecar từ đĩa: cũng báo tên file
        with pytest.raises(LabelError, match="sidecar"):
            project._read_item_file(f"{folder.name}_p2")
    (project.root / "project.json").write_bytes(b"")
    with pytest.raises(LabelError, match="project.json"):
        LabelProject(project.root)


def test_reimport_after_a_lost_sidecar_does_not_overwrite_the_painted_label(snap_root, tmp_path):
    folder = write_snapshot(snap_root, T0, ports=(1,))
    project = LabelProject(tmp_path / "p", create=True)
    project.import_snapshots(snap_root, log=None)
    item_id = f"{folder.name}_p1"
    editor = project.editor(item_id)
    editor.paint([(10, 20), (90, 20)], IGNORE, 6)
    project.save(item_id, editor.label, editor.edited)
    painted = project.path(item_id, "labels").read_bytes()
    project.path(item_id, "items").unlink()                            # sidecar mất (hỏng, bị chuyển ra ngoài)
    again = LabelProject(project.root)
    summary = again.import_snapshots(snap_root, log=None)
    sha = L.sha256_bytes((folder / "cam_p1.png").read_bytes())
    assert summary["imported"] == [f"{item_id}_{sha[:8]}"]              # mã mới, không đè file của mã cũ
    assert project.path(item_id, "labels").read_bytes() == painted


def test_writes_are_fsynced_and_a_failed_write_leaves_no_temp_file(snap_root, tmp_path, monkeypatch):
    synced, real_fsync, real_replace = [], L.os.fsync, L.os.replace
    monkeypatch.setattr(L.os, "fsync", lambda fd: synced.append(fd) or real_fsync(fd))
    target = tmp_path / "a.bin"
    L.atomic_write_bytes(target, b"abc")
    assert synced and target.read_bytes() == b"abc"
    folder = write_snapshot(snap_root, T0, ports=(1,))
    project = LabelProject(tmp_path / "p", create=True)
    project.import_snapshots(snap_root, log=None)
    item_id = f"{folder.name}_p1"
    editor = project.editor(item_id)
    editor.paint([(5, 5)], IGNORE, 2)
    synced.clear()
    project.save(item_id, editor.label, editor.edited)
    assert len(synced) == 3                                             # nhãn, mặt nạ đã tô, sidecar

    def denied(*_args):
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(L.os, "replace", denied)
    with pytest.raises(PermissionError):
        L.atomic_write_bytes(target, b"xyz")
    editor.paint([(50, 50)], IGNORE, 2)
    with pytest.raises(PermissionError):
        project.save(item_id, editor.label, editor.edited)
    monkeypatch.setattr(L.os, "replace", real_replace)
    assert target.read_bytes() == b"abc" and not list(tmp_path.rglob("*.tmp"))


# ---------------------------------------------------------------- import --exclude: không nhập ảnh đã dùng ở nơi khác
def _eval_project(tmp_path, snap_root):
    """Dự án chấm tô tay từ đầu: một bộ ảnh 2 camera lúc T0 + 10 h, trong thư mục riêng rig_snapshots_cham."""
    cham = snap_root.parent / "rig_snapshots_cham"
    folder = write_snapshot(cham, T0 + timedelta(hours=10), seed=70)
    project = LabelProject(tmp_path / "chấm", create=True)
    project.import_snapshots(cham, draft=False, log=None)
    return project, folder


def test_import_exclude_skips_each_kind_of_reuse_separately_and_keeps_the_rest(snap_root, tmp_path):
    """Mỗi bộ ảnh nguồn trùng dự án chấm theo ĐÚNG MỘT cách (sha256 / tên bộ ảnh / giờ bộ ảnh / giờ khung cũ), để
    bỏ riêng từng phép so thì test hỏng. Ảnh không trùng vẫn vào; export sau đó qua được --disjoint-from của dự án chấm."""
    cham, eval_folder = _eval_project(tmp_path, snap_root)
    t_eval = T0 + timedelta(hours=10)
    only_sha = write_snapshot(snap_root, T0 + timedelta(hours=5), seed=81)     # p1 chép nguyên byte ảnh chấm p1
    shutil.copyfile(eval_folder / "cam_p1.png", only_sha / "cam_p1.png")
    only_name = write_snapshot(snap_root, T0 + timedelta(hours=3), seed=82, name=eval_folder.name)
    only_gap = write_snapshot(snap_root, t_eval + timedelta(seconds=30), seed=83)
    old = write_snapshot(snap_root, t_eval + timedelta(minutes=10), seed=84)   # p1 treo: khung chụp 20 s sau ảnh chấm
    set_camera_meta(old, 1, age_ms=(10 * 60 - 20) * 1000.0, stale=True)
    clean = write_snapshot(snap_root, T0, seed=85)

    train = LabelProject(tmp_path / "huấn luyện", create=True)
    summary = train.import_snapshots(snap_root, exclude=[cham.root], log=None)
    excluded = {line.split(":")[0]: line for line in summary["excluded"]}
    assert set(excluded) == {f"{only_sha.name}/cam_p1.png", f"{only_name.name}/cam_p1.png",
                             f"{only_name.name}/cam_p2.png", f"{only_gap.name}/cam_p1.png",
                             f"{only_gap.name}/cam_p2.png", f"{old.name}/cam_p1.png"}
    assert "trùng sha256 ảnh" in excluded[f"{only_sha.name}/cam_p1.png"]
    assert "cùng bộ ảnh" in excluded[f"{only_name.name}/cam_p2.png"]
    assert "sha256" not in excluded[f"{only_name.name}/cam_p2.png"] and "phiên" not in excluded[f"{only_name.name}/cam_p2.png"]
    assert "30 s" in excluded[f"{only_gap.name}/cam_p1.png"] and "cùng phiên" in excluded[f"{only_gap.name}/cam_p1.png"]
    assert "20 s" in excluded[f"{old.name}/cam_p1.png"]                            # theo GIỜ KHUNG, không theo giờ bộ ảnh
    assert sorted(summary["imported"]) == sorted([f"{only_sha.name}_p2", f"{old.name}_p2", f"{clean.name}_p1",
                                                  f"{clean.name}_p2"])
    assert not train.path(f"{only_gap.name}_p1", "images").exists()                # không ghi gì cho khung bị loại trừ
    (source,) = summary["exclude_sources"]
    assert source["kind"] == "label_project" and source["images"] == 2 and source["snapshots"] == 1
    assert summary["already_in_project_excluded"] == []
    seen = {v["snapshot"] for v in train.known_snapshots().values()}                # bộ bị loại trừ vẫn nối chuỗi phiên
    assert {only_gap.name, only_name.name} <= seen

    review_all(train)
    v1 = tmp_path / "prepared" / "sa_ban_v1"
    train.export(v1, log=QUIET)
    hand_label_all(cham)
    result = cham.export(tmp_path / "prepared" / "cham_v1", ratios=(0, 1, 0), disjoint_from=[v1], log=QUIET)
    assert result["splits"]["val"] == 2                                            # --exclude lúc nhập => export tách rời

    control = LabelProject(tmp_path / "không loại trừ", create=True)               # đối chứng: không --exclude thì nhập hết
    assert len(control.import_snapshots(snap_root, log=None)["imported"]) == 10


def test_import_exclude_reads_a_cache_and_only_warns_about_images_already_in_the_project(snap_root, tmp_path):
    for k in range(3):
        write_snapshot(snap_root, T0 + timedelta(hours=k), seed=k)
    train = LabelProject(tmp_path / "huấn luyện", create=True)
    train.import_snapshots(snap_root, log=None)
    review_all(train)
    v1 = tmp_path / "prepared" / "sa_ban_v1"
    train.export(v1, log=QUIET)

    mixed = snap_root.parent / "lẫn"                                               # thư mục chấm lỡ chứa một bộ huấn luyện
    shutil.copytree(sorted(snap_root.iterdir())[0], mixed / sorted(snap_root.iterdir())[0].name)
    fresh = write_snapshot(mixed, T0 + timedelta(hours=20), seed=90)
    cham = LabelProject(tmp_path / "chấm", create=True)
    summary = cham.import_snapshots(mixed, draft=False, exclude=v1 / "manifest.json", log=None)
    assert sorted(summary["imported"]) == [f"{fresh.name}_p1", f"{fresh.name}_p2"] and len(summary["excluded"]) == 2
    assert summary["exclude_sources"][0]["kind"] == "cache" and summary["exclude_sources"][0]["images"] == 6

    before = {i: train.item(i)["status"] for i in train.ids()}                     # nhập lại vào CHÍNH dự án huấn luyện
    again = train.import_snapshots(snap_root, exclude=[cham.root], log=None)       # với nguồn là dự án chấm: ảnh sẵn có
    assert again["imported"] == [] and again["already_in_project_excluded"] == []  # không trùng => không cảnh báo
    later = LabelProject(tmp_path / "sau", create=True)
    later.import_snapshots(mixed, draft=False, log=None)                           # dự án đã lỡ có ảnh của cache huấn luyện
    warned = later.import_snapshots(snap_root, exclude=[v1], log=None)
    assert len(warned["already_in_project_excluded"]) == 2 and "trùng sha256 ảnh" in warned["already_in_project_excluded"][0]
    assert all(later.item(i)["status"] == "draft" for i in later.ids())            # chỉ cảnh báo, không đổi trạng thái
    assert {i: train.item(i)["status"] for i in train.ids()} == before
    with pytest.raises(LabelError, match="chính dự án"):
        train.import_snapshots(snap_root, exclude=[train.root], log=None)


def test_import_exclude_source_problems_stop_before_anything_is_written(snap_root, tmp_path, capsys):
    write_snapshot(snap_root, T0)
    project_dir = tmp_path / "dự án"
    assert L.main(["import", str(snap_root), "--project", str(project_dir), "--exclude", str(tmp_path / "khong_co")]) == 2
    assert "--exclude" in capsys.readouterr().err and not project_dir.exists()
    with pytest.raises(SystemExit) as exc:
        L.main(["import", str(snap_root), "--project", str(project_dir), "--exclude", str(tmp_path),
                "--session-gap", "-1"])
    assert exc.value.code == 2 and "--session-gap" in capsys.readouterr().err and not project_dir.exists()

    cham = LabelProject(tmp_path / "chấm", create=True)
    cham.import_snapshots(snap_root, draft=False, log=None)
    (cham.root / "items" / "hong.json").write_bytes(b"{")                          # sidecar hỏng: loại trừ thiếu = lọt ảnh
    assert L.main(["import", str(snap_root), "--project", str(project_dir), "--exclude", str(cham.root)]) == 2
    err = capsys.readouterr().err
    assert "hong.json" in err and not project_dir.exists()
    (cham.root / "items" / "hong.json").unlink()
    files_before = {p: p.read_bytes() for p in cham.root.rglob("*") if p.is_file()}
    assert L.main(["import", str(snap_root), "--project", str(project_dir), "--exclude", str(cham.root)]) == 0
    out = capsys.readouterr().out
    assert "Đã nhập 0 ảnh" in out and "không nhập vì --exclude: 2 khung" in out and "loại trừ theo" in out
    assert {p: p.read_bytes() for p in cham.root.rglob("*") if p.is_file()} == files_before   # nguồn chỉ được đọc


# ---------------------------------------------------------------- import --exclude, thêm sau rà soát (tối 24/09/2026):
# từng phép so với nguồn là cache hay dự án, --session-gap của lệnh, cảnh báo ảnh sẵn có chỉ trùng tên/giờ
def _training_with_stale_frame(snap_root, tmp_path):
    """Dự án huấn luyện 4 bộ ảnh T0 + k giờ; bộ T0 + 1 h có p1 treo, giờ khung = T0 + 30 phút (chỉ có ở
    frame_captured_local). Mọi ảnh đã duyệt (khung cũ duyệt với override_damage) để export ra cache được."""
    folders = [write_snapshot(snap_root, T0 + timedelta(hours=k), seed=100 + k) for k in range(4)]
    set_camera_meta(folders[1], 1, age_ms=30 * 60 * 1000.0, stale=True)
    train = LabelProject(tmp_path / "huấn luyện", create=True)
    train.import_snapshots(snap_root, log=None)
    train.set_status(f"{folders[1].name}_p1", "reviewed", override_damage=True)
    review_all(train)
    return train, folders


@pytest.mark.parametrize("kind", ["cache", "label_project"])
def test_import_exclude_each_comparison_alone_for_cache_and_project_sources(snap_root, tmp_path, kind):
    """Nguồn loại trừ là cache đã export hoặc dự án gán nhãn. Mỗi bộ ảnh chấm trùng nguồn theo ĐÚNG MỘT cách: tên bộ
    ảnh; chụp 25 s TRƯỚC một bản ghi; 40 s SAU một bản ghi; 50 s sau GIỜ KHUNG cũ của nguồn (xa mọi giờ bộ ảnh). sha256
    không trùng ở bộ nào. Bỏ riêng việc gom tên bộ ảnh / giờ bộ ảnh / giờ khung của nguồn thì test hỏng."""
    train, folders = _training_with_stale_frame(snap_root, tmp_path)
    source = train.root
    if kind == "cache":
        source = tmp_path / "prepared" / "sa_ban_v1"
        train.export(source, log=QUIET)
    cham_dir = snap_root.parent / "rig_snapshots_cham"
    only_name = write_snapshot(cham_dir, T0 + timedelta(hours=10), seed=91, name=folders[2].name)
    before = write_snapshot(cham_dir, T0 + timedelta(hours=2, seconds=-25), seed=92)
    after = write_snapshot(cham_dir, T0 + timedelta(hours=3, seconds=40), seed=93)
    near_frame = write_snapshot(cham_dir, T0 + timedelta(minutes=30, seconds=50), seed=94)
    clean = write_snapshot(cham_dir, T0 + timedelta(hours=20), seed=95)

    cham = LabelProject(tmp_path / "chấm", create=True)
    summary = cham.import_snapshots(cham_dir, draft=False, exclude=[source], log=None)
    excluded = {line.split(":")[0]: line for line in summary["excluded"]}
    assert set(excluded) == {f"{f.name}/cam_p{p}.png" for f in (only_name, before, after, near_frame) for p in (1, 2)}
    assert all("sha256" not in line for line in excluded.values())
    name_line = excluded[f"{only_name.name}/cam_p1.png"]
    assert "cùng bộ ảnh" in name_line and "phiên" not in name_line
    assert "25 s" in excluded[f"{before.name}/cam_p1.png"] and "cùng bộ ảnh" not in excluded[f"{before.name}/cam_p1.png"]
    assert "40 s" in excluded[f"{after.name}/cam_p2.png"]
    assert "50 s" in excluded[f"{near_frame.name}/cam_p1.png"]              # chỉ trùng giờ KHUNG cũ của nguồn
    assert sorted(summary["imported"]) == [f"{clean.name}_p1", f"{clean.name}_p2"]
    (info,) = summary["exclude_sources"]
    assert info["kind"] == kind and info["images"] == 8 and info["snapshots"] == 4 and info["unchecked_time"] == 0


def test_import_exclude_command_line_uses_the_given_session_gap(snap_root, tmp_path, capsys):
    """--session-gap của lệnh import phải tới được phép so: ảnh chụp 30 s sau nguồn vào được với --session-gap 10,
    bị loại với --session-gap 40 (mặc định 60 s cũng loại, nên chuyển thiếu tham số là test hỏng)."""
    write_snapshot(snap_root, T0, seed=1)
    cham = LabelProject(tmp_path / "chấm", create=True)
    cham.import_snapshots(snap_root, draft=False, log=None)
    other = snap_root.parent / "rig_snapshots_2"
    write_snapshot(other, T0 + timedelta(seconds=30), seed=2)
    loose = tmp_path / "gap10"
    assert L.main(["import", str(other), "--project", str(loose), "--exclude", str(cham.root),
                   "--session-gap", "10"]) == 0
    out = capsys.readouterr().out
    assert "Đã nhập 2 ảnh" in out and "không nhập vì --exclude: 0 khung" in out and len(LabelProject(loose).ids()) == 2
    strict = tmp_path / "gap40"
    assert L.main(["import", str(other), "--project", str(strict), "--exclude", str(cham.root),
                   "--session-gap", "40"]) == 0
    out = capsys.readouterr().out
    assert "Đã nhập 0 ảnh" in out and "không nhập vì --exclude: 2 khung" in out and "30 s" in out


def test_import_exclude_warns_about_images_in_the_project_by_snapshot_or_time_alone(snap_root, tmp_path):
    """Ảnh ĐÃ có trong dự án trùng nguồn chỉ theo tên bộ ảnh, chỉ theo giờ bộ ảnh, hay chỉ theo giờ khung cũ của ảnh
    trong dự án: vẫn phải được cảnh báo (không đổi trạng thái), không chỉ khi trùng sha256."""
    train, folders = _training_with_stale_frame(snap_root, tmp_path)
    v1 = tmp_path / "prepared" / "sa_ban_v1"
    train.export(v1, log=QUIET)
    lan = snap_root.parent / "lẫn"
    same_name = write_snapshot(lan, T0 + timedelta(hours=10), seed=71, name=folders[3].name)
    near = write_snapshot(lan, T0 + timedelta(hours=2, seconds=35), seed=72)
    stale = write_snapshot(lan, T0 + timedelta(hours=12), seed=73)          # p1 treo: giờ khung = T0 + 2 h + 45 s
    set_camera_meta(stale, 1, age_ms=(10 * 3600 - 45) * 1000.0, stale=True)
    far = write_snapshot(lan, T0 + timedelta(hours=30), seed=74)
    later = LabelProject(tmp_path / "sau", create=True)
    later.import_snapshots(lan, draft=False, log=None)
    status = {i: later.item(i)["status"] for i in later.ids()}
    assert later.item(f"{stale.name}_p1")["source"]["frame_captured_local"] == "2026-09-23T12:00:45.000"

    warned = later.import_snapshots(lan, exclude=[v1], log=None)
    lines = {line.split(" ")[0]: line for line in warned["already_in_project_excluded"]}
    assert set(lines) == {f"{same_name.name}_p1", f"{same_name.name}_p2", f"{near.name}_p1", f"{near.name}_p2",
                          f"{stale.name}_p1"}
    assert "cùng bộ ảnh" in lines[f"{same_name.name}_p1"] and "sha256" not in lines[f"{same_name.name}_p1"]
    assert "35 s" in lines[f"{near.name}_p2"] and "cùng bộ ảnh" not in lines[f"{near.name}_p2"]
    assert "45 s" in lines[f"{stale.name}_p1"]                               # theo giờ KHUNG của ảnh trong dự án
    assert not any(far.name in line for line in lines)
    assert warned["imported"] == [] and {i: later.item(i)["status"] for i in later.ids()} == status
