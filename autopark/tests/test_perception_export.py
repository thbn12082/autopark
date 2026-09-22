"""ONNX export parity on CPU at a small size, plus predict_image thresholds and the evaluate CLI guards."""
import pytest

np = pytest.importorskip("numpy")
torch = pytest.importorskip("torch")
pytest.importorskip("cv2")

from autopark.perception.model import build_model  # noqa: E402
from autopark.perception.predict import predict_image  # noqa: E402


def test_predict_image_returns_input_size_and_monotone_thresholds():
    model = build_model(2, pretrained=False).eval()
    image = np.random.default_rng(1).integers(0, 256, (37, 100, 3), dtype=np.uint8)   # wide 16:9-ish input
    labels, prob = predict_image(model, image, 64, 96, torch.device("cpu"), amp=False)
    assert labels.shape == (37, 100) and prob.shape == (37, 100) and labels.dtype == np.uint8
    assert np.array_equal(labels, (prob >= 0.5).astype(np.uint8))
    low, _ = predict_image(model, image, 64, 96, torch.device("cpu"), amp=False, threshold=0.05)
    high, _ = predict_image(model, image, 64, 96, torch.device("cpu"), amp=False, threshold=0.95)
    assert (low >= labels).all() and (labels >= high).all()          # lowering the threshold never frees a pixel


def test_onnx_export_matches_torch_on_cpu(tmp_path):
    onnx = pytest.importorskip("onnx")
    ort = pytest.importorskip("onnxruntime")
    from autopark.perception.export_onnx import LogitsOnly

    torch.manual_seed(0)
    wrapped = LogitsOnly(build_model(2, pretrained=False)).eval()
    example = torch.randn(1, 3, 64, 96)
    path = tmp_path / "model.onnx"
    torch.onnx.export(wrapped, (example,), str(path), input_names=["image"], output_names=["logits"],
                      opset_version=17, dynamo=False)
    onnx.checker.check_model(onnx.load(str(path)))
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    x = torch.randn(2, 3, 64, 96)
    with torch.no_grad():
        reference = torch.cat([wrapped(x[i:i + 1]) for i in range(2)]).numpy()
    out = np.concatenate([session.run(None, {"image": x[i:i + 1].numpy()})[0] for i in range(2)])
    assert out.shape == (2, 2, 64, 96)
    assert np.abs(out - reference).max() < 1e-3 and (out.argmax(1) == reference.argmax(1)).mean() > 0.999


def test_evaluate_cli_guards_run_before_any_gpu_work(tmp_path):
    from autopark.perception.evaluate import main

    with pytest.raises(SystemExit):
        main(["--checkpoint", str(tmp_path / "x.pt"), "--split", "test", "--out", str(tmp_path)])      # no --final-test
    with pytest.raises(SystemExit):
        main(["--checkpoint", str(tmp_path / "x.pt"), "--split", "test", "--final-test", "--sweep", "--out", str(tmp_path)])
