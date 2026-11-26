"""Suy luận trực tiếp theo lô phải cho đúng kết quả của `predict.predict_image` trên cùng ảnh (cần torch)."""
import pytest

torch = pytest.importorskip("torch")
np = pytest.importorskip("numpy")
pytest.importorskip("torchvision")

from autopark.perception.live import LiveSegmenter, list_checkpoints  # noqa: E402
from autopark.perception.model import build_model  # noqa: E402
from autopark.perception.predict import predict_image  # noqa: E402


@pytest.fixture(scope="module")
def checkpoint(tmp_path_factory):
    torch.manual_seed(0)
    model = build_model(2, pretrained=False).eval()
    path = tmp_path_factory.mktemp("ck") / "tiny" / "best.pt"
    path.parent.mkdir(parents=True)
    torch.save({"config": {"height": 96, "width": 128, "num_classes": 2, "amp": False}, "model": model.state_dict(),
                "epoch": 3}, path)
    return path, model


def test_batched_live_inference_matches_predict_image(checkpoint):
    path, model = checkpoint
    seg = LiveSegmenter(path, device="cpu")
    rng = np.random.default_rng(1)
    a = rng.integers(0, 256, (120, 200, 3), dtype=np.uint8)       # 5:3 như camera 16:9 → có dải letterbox
    b = rng.integers(0, 256, (90, 90, 3), dtype=np.uint8)
    probs, timing = seg.infer([a, b])
    for image, prob in ((a, probs[0]), (b, probs[1])):
        _, expected = predict_image(model, image, 96, 128, torch.device("cpu"), amp=False)
        assert prob.shape == image.shape[:2] and np.allclose(prob, expected, atol=1e-5)
    assert timing.batch == 2 and timing.total_ms >= timing.model_ms > 0
    small, _ = seg.infer([a], out_size=(50, 30))
    assert small[0].shape == (30, 50) and 0.0 <= small[0].min() and small[0].max() <= 1.0
    assert seg.infer([])[0] == [] and seg.name == "tiny" and seg.epoch == 3


def test_list_checkpoints_puts_reference_run_first(tmp_path):
    for name in ("ai_ws_avm", "ai_woodscape_rtx4000_v1", "a_first_alphabetically"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "best.pt").write_bytes(b"")
    names = [p.parent.name for p in list_checkpoints(tmp_path)]
    assert names[0] == "ai_woodscape_rtx4000_v1" and sorted(names[1:]) == ["a_first_alphabetically", "ai_ws_avm"]
