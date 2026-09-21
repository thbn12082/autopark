"""Label mapping, polygon conversion, letterbox, frozen split and augmentation of the perception pipeline."""
import copy
import json

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")
torch = pytest.importorskip("torch")

from autopark.perception.augment import AugmentConfig, augment, step_generator  # noqa: E402
from autopark.perception.data import label_lookup, letterbox, polygon_mask  # noqa: E402
from autopark.perception.dataset import CacheError, check_splits  # noqa: E402
from tests.conftest import PROJECT_ROOT  # noqa: E402

MAPPING = PROJECT_ROOT / "configs/woodscape_binary_v1.json"
FROZEN = PROJECT_ROOT / "datasets/frozen_splits/woodscape_binary_v1/manifest.json"


def _square(tag, z_order, x0, y0, x1, y1):
    return {"tags": [tag] if isinstance(tag, str) else tag, "z_order": z_order,
            "segmentation": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}


def test_project_mapping_assigns_every_class_once():
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    lookup = label_lookup(mapping)
    assert set(lookup.values()) == {0, 1, 255}
    assert len(lookup) == len(mapping["free"]) + len(mapping["blocked"]) + len(mapping["ignore"])
    assert lookup["road_surface"] == 0 and lookup["person"] == 1
    # Unverified or unobservable regions must not be trained as FREE.
    assert all(lookup[name] == 255 for name in ("free_space", "void", "ego_vehicle", "sky"))


def test_duplicate_class_mapping_is_rejected():
    with pytest.raises(ValueError):
        label_lookup({"free": ["road"], "blocked": ["road"], "ignore": []})


def test_polygon_mask_respects_z_order_and_never_invents_free():
    lookup = {"road": 0, "car": 1}
    annotation = {"image_height": 40, "image_width": 60, "annotation": [
        _square("car", 5, 10, 10, 30, 30),          # drawn last although listed first
        _square("road", 1, 0, 0, 59, 39),
        _square("mystery", 9, 40, 0, 50, 10),       # unmapped tag
        _square(["road", "car"], 10, 0, 30, 10, 39),  # ambiguous multi-tag polygon is skipped
    ]}
    mask, unknown, skipped = polygon_mask(annotation, lookup)
    assert mask[20, 20] == 1 and mask[35, 50] == 0
    assert mask[5, 45] == 255 and unknown == ["mystery"]
    assert skipped == 1 and mask[35, 5] == 0          # skipped polygon leaves the road underneath


def test_unannotated_pixels_stay_ignore():
    mask, _, _ = polygon_mask({"image_height": 20, "image_width": 20,
                               "annotation": [_square("road", 0, 0, 0, 5, 5)]}, {"road": 0})
    assert mask[15, 15] == 255


def test_letterbox_keeps_aspect_and_marks_bars_ignore():
    image = np.full((100, 200, 3), 200, np.uint8)
    mask = np.zeros((100, 200), np.uint8)
    output, target, transform = letterbox(image, mask, 384, 512)
    assert output.shape == (384, 512, 3) and target.shape == (384, 512)
    assert (transform["width"], transform["height"], transform["y"]) == (512, 256, 64)
    assert (target[:64] == 255).all() and (target[320:] == 255).all() and (output[:64] == 0).all()
    assert (target[64:320] == 0).all()


def test_letterbox_rejects_mismatched_pair():
    with pytest.raises(ValueError):
        letterbox(np.zeros((10, 10, 3), np.uint8), np.zeros((10, 12), np.uint8), 384, 512)


@pytest.fixture(scope="module")
def frozen_manifest():
    if not FROZEN.exists():
        pytest.skip("frozen split manifest not present")
    return json.loads(FROZEN.read_text(encoding="utf-8"))


def test_frozen_split_is_a_partition_without_group_leakage(frozen_manifest):
    check_splits(frozen_manifest)
    sizes = {name: len(indices) for name, indices in frozen_manifest["splits"].items()}
    assert sizes == {"train": 5764, "val": 1235, "test": 1235}
    for name in sizes:
        cameras = {frozen_manifest["records"][i]["camera"] for i in frozen_manifest["splits"][name]}
        assert cameras == {"FV", "MVL", "MVR", "RV"}


def test_split_check_detects_overlap_and_group_leakage(frozen_manifest):
    overlapping = copy.deepcopy(frozen_manifest)
    overlapping["splits"]["val"][0] = overlapping["splits"]["train"][0]
    with pytest.raises(CacheError):
        check_splits(overlapping)
    leaking = copy.deepcopy(frozen_manifest)
    train_index, test_index = leaking["splits"]["train"][0], leaking["splits"]["test"][0]
    leaking["records"][test_index]["group"] = leaking["records"][train_index]["group"]
    with pytest.raises(CacheError):
        check_splits(leaking)


def _batch(height=48, width=64):
    masks = torch.zeros((4, height, width), dtype=torch.uint8)
    masks[:, 10:30, 20:50] = 1
    masks[:, :4] = 255
    images = torch.zeros((4, 3, height, width))
    images[:, 0] = (masks == 1).float()              # red channel encodes the BLOCKED region
    return images, masks


def test_augmentation_disabled_is_identity():
    images, masks = _batch()
    out_images, out_masks = augment(images, masks, AugmentConfig(enabled=False), step_generator("cpu", 1, 0, 0))
    assert torch.equal(out_images, images) and torch.equal(out_masks, masks)


def test_augmentation_is_reproducible_per_step():
    images, masks = _batch()
    cfg = AugmentConfig()
    first = augment(images, masks, cfg, step_generator("cpu", 7, 2, 5))
    again = augment(images, masks, cfg, step_generator("cpu", 7, 2, 5))
    other = augment(images, masks, cfg, step_generator("cpu", 7, 2, 6))
    assert torch.equal(first[0], again[0]) and torch.equal(first[1], again[1])
    assert not torch.equal(first[1], other[1])


def test_zoom_out_fills_the_frame_with_ignore_not_free():
    images, masks = _batch()
    masks = torch.ones_like(masks)                   # no FREE pixel exists in the source at all
    cfg = AugmentConfig(scale_min=0.5, scale_max=0.5, hflip=0.0, brightness=0, contrast=0, saturation=0)
    _, out = augment(images, masks, cfg, step_generator("cpu", 3, 0, 0))
    assert set(out.unique().tolist()) == {1, 255}
    assert (out == 255).float().mean() > 0.5         # a half-size image covers a quarter of the frame


def test_geometry_moves_image_and_mask_together():
    images, masks = _batch()
    cfg = AugmentConfig(scale_min=0.8, scale_max=1.3, hflip=0.5, brightness=0, contrast=0, saturation=0)
    for step in range(6):
        out_images, out_masks = augment(images, masks, cfg, step_generator("cpu", 11, 0, step))
        assert set(out_masks.unique().tolist()) <= {0, 1, 255}
        valid = out_masks != 255
        agreement = ((out_images[:, 0] > 0.5) == (out_masks == 1))[valid].float().mean()
        assert agreement > 0.97                       # only bilinear edge pixels may disagree
