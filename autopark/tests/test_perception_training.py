"""Loss/metrics with IGNORE, model heads, checkpoints and exact resume of the perception trainer (CPU, offline)."""
import json

import pytest

np = pytest.importorskip("numpy")
torch = pytest.importorskip("torch")
pytest.importorskip("torchvision")

from autopark.perception.checkpoint import atomic_save, load_checkpoint, restore_rng_state, rng_state  # noqa: E402
from autopark.perception.dataset import CacheError, PreparedCache, SplitData  # noqa: E402
from autopark.perception.engine import evaluate_split  # noqa: E402
from autopark.perception.metrics import confusion_matrices, segmentation_loss, summarize  # noqa: E402
from autopark.perception.model import build_model, parameter_groups  # noqa: E402
from autopark.perception.train import DEFAULTS, StopRequested, Trainer, load_config, lr_factor, main  # noqa: E402

CAMERAS = ("FV", "MVL", "MVR", "RV")


def test_loss_ignores_255_pixels():
    torch.manual_seed(0)
    logits = torch.randn(2, 2, 6, 6)
    target = torch.randint(0, 2, (2, 6, 6), dtype=torch.uint8)
    target[:, :2] = 255
    loss, valid = segmentation_loss(logits, target)
    changed = logits.clone()
    changed[:, :, :2] += 50.0                         # only ignored pixels change
    assert int(valid) == 2 * 4 * 6
    assert torch.allclose(loss, segmentation_loss(changed, target)[0])


def test_all_ignore_batch_gives_finite_zero_loss_and_gradients():
    logits = torch.randn(2, 2, 5, 5, requires_grad=True)
    loss, valid = segmentation_loss(logits, torch.full((2, 5, 5), 255, dtype=torch.uint8))
    loss.backward()
    assert int(valid) == 0 and float(loss) == 0.0
    assert torch.isfinite(logits.grad).all() and not logits.grad.any()


def test_class_weighted_loss_is_a_weighted_mean():
    logits = torch.zeros(1, 2, 1, 2)                   # uniform prediction: every pixel costs ln 2
    loss, _ = segmentation_loss(logits, torch.tensor([[[0, 1]]], dtype=torch.uint8),
                                class_weights=torch.tensor([1.0, 3.0]))
    assert float(loss) == pytest.approx(float(np.log(2)))


def test_confusion_matrices_per_image_with_ignore():
    target = torch.tensor([[[0, 0, 1, 1, 255]], [[1, 1, 1, 255, 255]]], dtype=torch.uint8)
    pred = torch.tensor([[[0, 1, 1, 0, 0]], [[1, 1, 0, 0, 1]]])
    matrices = confusion_matrices(pred, target)
    assert matrices[0].tolist() == [[1, 1], [1, 1]]
    assert matrices[1].tolist() == [[0, 0], [1, 2]]
    report = summarize(matrices.sum(0))
    assert report["valid_pixels"] == 7
    assert report["iou_blocked"] == pytest.approx(3 / 6)      # TP 3, FP 1, FN 2
    assert report["iou_free"] == pytest.approx(1 / 4)
    assert report["mIoU"] == pytest.approx((3 / 6 + 1 / 4) / 2)
    assert report["blocked_as_free_rate"] == pytest.approx(2 / 5)
    assert report["predicted_free_that_is_blocked"] == pytest.approx(2 / 3)
    assert report["blocked_recall"] == pytest.approx(3 / 5) and report["blocked_precision"] == pytest.approx(3 / 4)


def test_metrics_are_none_not_zero_when_undefined():
    only_free = summarize(torch.tensor([[10, 0], [0, 0]]))
    assert only_free["iou_free"] == 1.0 and only_free["iou_blocked"] is None
    assert only_free["blocked_recall"] is None and only_free["mIoU"] == 1.0
    empty = summarize(confusion_matrices(torch.zeros((1, 2, 2), dtype=torch.long),
                                         torch.full((1, 2, 2), 255, dtype=torch.uint8)).sum(0))
    assert empty["valid_pixels"] == 0 and empty["mIoU"] is None and empty["pixel_accuracy"] is None


def test_per_image_table_handles_errors_and_all_ignore_images():
    pytest.importorskip("PIL")
    from autopark.perception.evaluate import per_image_rows

    target = torch.tensor([[[0, 0, 1, 1]], [[255, 255, 255, 255]]], dtype=torch.uint8)
    pred = torch.tensor([[[0, 1, 1, 0]], [[0, 1, 0, 1]]])
    rows = per_image_rows([{"id": "a_FV", "camera": "FV"}, {"id": "b_RV", "camera": "RV"}],
                          confusion_matrices(pred, target))
    assert rows[0]["valid_pixels"] == 4 and rows[0]["error_rate"] == pytest.approx(0.5)
    assert rows[0]["blocked_as_free_rate"] == pytest.approx(0.5)
    assert rows[1]["valid_pixels"] == 0 and rows[1]["error_rate"] is None and rows[1]["iou_free"] is None


def test_model_replaces_both_heads_and_outputs_two_classes():
    model = build_model(2, pretrained=False).eval()
    assert model.classifier.low_classifier.out_channels == 2
    assert model.classifier.high_classifier.out_channels == 2
    with torch.no_grad():
        out = model(torch.zeros(2, 3, 64, 96))["out"]
    assert out.shape == (2, 2, 64, 96)
    groups = parameter_groups(model, 1e-4, 1e-3)
    assert [g["name"] for g in groups] == ["backbone", "head"]
    assert sum(len(g["params"]) for g in groups) == len(list(model.parameters()))


def test_lr_schedule_warms_up_then_decays_to_zero():
    assert lr_factor(0, 100, 10, 0.9) == pytest.approx(0.1)
    assert lr_factor(9, 100, 10, 0.9) == pytest.approx(1.0)
    assert lr_factor(10, 100, 10, 0.9) == pytest.approx(1.0)
    assert 0 < lr_factor(99, 100, 10, 0.9) < lr_factor(50, 100, 10, 0.9) < 1
    assert lr_factor(100, 100, 10, 0.9) == 0.0


def test_checkpoint_is_atomic_and_loads_with_restricted_unpickler(tmp_path):
    state = {"model": {"w": torch.arange(4.0)}, "epoch": 3, "config": {"a": [1, None, "x"]}, "rng": rng_state()}
    path = tmp_path / "latest.pt"
    atomic_save(state, path)
    assert not (tmp_path / "latest.pt.tmp").exists()
    loaded = load_checkpoint(path)                     # weights_only=True inside
    assert torch.equal(loaded["model"]["w"], state["model"]["w"]) and loaded["config"] == state["config"]
    expected = torch.rand(3)
    restore_rng_state(loaded["rng"])
    assert torch.equal(torch.rand(3), expected)


def _make_cache(root, train=16, val=4, test=4, height=64, width=64, verified=True):
    rng = np.random.default_rng(5)
    count = train + val + test
    # 16-pixel blocks: a stride-16 backbone cannot resolve per-pixel noise, so the rule must be spatially coarse.
    blocks = rng.integers(0, 2, (count, height // 16, width // 16, 3)) * 200 + 25
    images = np.kron(blocks, np.ones((1, 16, 16, 1), dtype=np.int64))
    images = np.clip(images + rng.integers(-20, 21, images.shape), 0, 255).astype(np.uint8)
    masks = (images[..., 0] > 127).astype(np.uint8)    # learnable: BLOCKED where the red block is bright
    masks[:, :6] = 255
    names = ["train"] * train + ["val"] * val + ["test"] * test
    records = [{"index": i, "id": f"{i:05d}_{CAMERAS[i % 4]}", "camera": CAMERAS[i % 4], "split": names[i],
                "group": i} for i in range(count)]
    splits = {name: [i for i, owner in enumerate(names) if owner == name] for name in ("train", "val", "test")}
    train_masks = masks[:train]
    manifest = {"height": height, "width": width, "mapping_sha256": "test-mapping", "records": records,
                "splits": splits, "handoff_split_verified": verified,
                "statistics": {"train": {"pixels": {str(v): int((train_masks == v).sum()) for v in (0, 1, 255)}}}}
    root.mkdir(parents=True)
    np.save(root / "images.npy", images)
    np.save(root / "masks.npy", masks)
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if verified:
        (root / "TRANSFER_READY.json").write_text(json.dumps({"ready": True, "mapping_sha256": "test-mapping"}),
                                                  encoding="utf-8")
    return root / "manifest.json"


def _config(manifest_path, **changes):
    return {**DEFAULTS, "prepared_manifest": str(manifest_path), "height": 64, "width": 64,
            "initialization": "random", "device": "cpu", "allow_cpu": True, "amp": False, "batch_size": 2,
            "grad_accum_steps": 2, "eval_batch_size": 4, "epochs": 2, "early_stopping_patience": 0,
            "warmup_updates": 2, "checkpoint_every_optimizer_steps": 1, "log_every_optimizer_steps": 1, **changes}


def test_unverified_cache_is_refused(tmp_path):
    manifest = _make_cache(tmp_path / "cache", verified=False)
    with pytest.raises(CacheError):
        PreparedCache.open(manifest)
    assert len(PreparedCache.open(manifest, require_verified=False).indices("train")) == 16


def test_batches_follow_a_seeded_order_and_keep_pairs_aligned(tmp_path):
    cache = PreparedCache.open(_make_cache(tmp_path / "cache"))
    data = SplitData(cache, "train")
    assert np.array_equal(data.order(3, 1, True), data.order(3, 1, True))
    assert not np.array_equal(data.order(3, 1, True), data.order(3, 2, True))
    assert sorted(data.order(3, 1, True).tolist()) == list(range(16))
    images, masks = data.batch([5, 0], torch.device("cpu"))
    assert torch.equal(images[0], torch.from_numpy(np.asarray(cache.images[5])))
    assert torch.equal(masks[1], torch.from_numpy(np.asarray(cache.masks[0])))
    assert len(SplitData(cache, "train", limit=4)) == 4


def test_per_camera_reports_add_up_to_the_overall_matrix(tmp_path):
    cache = PreparedCache.open(_make_cache(tmp_path / "cache"))
    result = evaluate_split(build_model(2, pretrained=False), SplitData(cache, "val"), batch_size=3,
                            device=torch.device("cpu"), amp=False)
    report = result["report"]
    total = np.sum([c["confusion_matrix"] for c in report["per_camera"].values()], axis=0)
    assert total.tolist() == report["confusion_matrix"] == result["per_image"].sum(0).tolist()
    assert report["images"] == 4 and np.isfinite(report["loss"])


def test_resumed_run_matches_an_uninterrupted_run_exactly(tmp_path):
    cfg = _config(_make_cache(tmp_path / "cache"))
    (tmp_path / "full").mkdir()
    full = Trainer(cfg, tmp_path / "full")
    assert full.updates_per_epoch == 4
    full.run()

    (tmp_path / "part").mkdir()
    part = Trainer(cfg, tmp_path / "part")
    check = part._check_stop

    def stop_after_three_updates():
        if part.global_update >= 3:
            part.stop_flag = True
        check()
    part._check_stop = stop_after_three_updates
    with pytest.raises(StopRequested):
        part.run()
    state = load_checkpoint(tmp_path / "part/latest.pt")
    assert (state["epoch"], state["update_in_epoch"], state["global_update"]) == (0, 3, 3)   # mid-epoch

    resumed = Trainer(cfg, tmp_path / "part", resume_state=state)
    resumed.run()
    assert resumed.global_update == full.global_update == 8
    expected, actual = full.model.state_dict(), resumed.model.state_dict()
    assert all(torch.equal(expected[name], actual[name]) for name in expected)
    assert [h["validation"]["mIoU"] for h in resumed.history] == [h["validation"]["mIoU"] for h in full.history]
    assert resumed.history[0]["train_loss"] == pytest.approx(full.history[0]["train_loss"])


def test_resume_refuses_a_different_split(tmp_path):
    cfg = _config(_make_cache(tmp_path / "cache"), epochs=1)
    (tmp_path / "run").mkdir()
    trainer = Trainer(cfg, tmp_path / "run")
    trainer.run()
    state = load_checkpoint(tmp_path / "run/latest.pt")
    state["split_sha256"] = "another-split"
    with pytest.raises(ValueError):
        Trainer(cfg, tmp_path / "run", resume_state=state)


def test_training_learns_a_trivially_learnable_rule(tmp_path):
    cfg = _config(_make_cache(tmp_path / "cache"), epochs=12, validation_split="train", head_lr=5e-3,
                  backbone_lr=1e-3, grad_accum_steps=1, augment={**DEFAULTS["augment"], "enabled": False})
    (tmp_path / "run").mkdir()
    trainer = Trainer(cfg, tmp_path / "run")
    trainer.run()
    losses = [h["train_loss"] for h in trainer.history]
    assert losses[-1] < 0.7 * losses[0]


def test_cli_writes_run_files_and_guards_against_overwrite(tmp_path):
    cfg = _config(_make_cache(tmp_path / "cache"), epochs=1)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(cfg), encoding="utf-8")
    run = tmp_path / "run"
    assert main(["--config", str(config_path), "--out", str(run)]) == 0
    status = json.loads((run / "status.json").read_text(encoding="utf-8"))
    assert status["state"] == "completed" and status["best_epoch"] == 1
    for name in ("latest.pt", "best.pt", "run_manifest.json", "config_resolved.json", "epochs.jsonl",
                 "training_summary.json", "train_steps.jsonl", "train.log", "source.zip"):
        assert (run / name).exists(), name
    manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["data"]["test_split_read"] is False
    with pytest.raises(SystemExit):
        main(["--config", str(config_path), "--out", str(run)])


def test_config_without_measured_batch_size_or_with_test_split_is_rejected(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"batch_size": None}), encoding="utf-8")
    with pytest.raises(ValueError, match="batch_size"):
        load_config(path)
    with pytest.raises(ValueError, match="validation_split"):
        load_config(path, ["batch_size=8", "validation_split=\"test\""])
    assert load_config(path, ["batch_size=8", "augment.enabled=false"])["augment"]["enabled"] is False
