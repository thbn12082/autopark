from dataclasses import replace

import numpy as np
import pytest

pytest.importorskip("cv2")

from autopark.perception import bev
from autopark.perception.surround_view import SurroundViewRenderer


def test_preview_projects_four_directions_and_masks_vehicle(tmp_path):
    renderer = SurroundViewRenderer(extrinsics_path=tmp_path / "missing.json")
    assert renderer.is_preview and "ước lượng" in renderer.notice
    colors = {1: (0, 30, 210), 2: (0, 170, 50), 3: (200, 0, 0), 4: (70, 180, 190)}
    frames = {port: np.full((480, 640, 3), color, dtype=np.uint8) for port, color in colors.items()}
    background = renderer.render({})
    surround = renderer.render(frames)
    assert surround.shape == background.shape == (480, 480, 3)
    assert surround.dtype == np.uint8
    points = {1: (65, 240), 2: (415, 240), 3: (240, 65), 4: (240, 415)}
    for port, at in points.items():
        assert tuple(surround[at]) == colors[port]
    assert np.array_equal(surround[210:269, 223:257], background[210:269, 223:257])

    front_only = renderer.render({1: frames[1], 3: frames[3][::2]})
    assert tuple(front_only[points[1]]) == colors[1]
    for port in (2, 3, 4):
        assert np.array_equal(front_only[points[port]], background[points[port]])


def test_renderer_requires_every_camera_measured_and_accepted(monkeypatch):
    nominal, _ = bev.synthetic_rig()
    cameras = {name: replace(camera, extrinsics_measured=True, acceptance_all_pass=True)
               for name, camera in nominal.items()}
    monkeypatch.setattr(bev, "load_rig", lambda *args, **kwargs: (cameras, None, {}))
    assert not SurroundViewRenderer().is_preview

    cameras["p2"] = replace(cameras["p2"], synthetic=("nội tham",))
    assert SurroundViewRenderer().is_preview
