"""Fisheye calibration model and ground-plane costmap projection (CPU, synthetic rigs; no dataset needed)."""
import math

import pytest

np = pytest.importorskip("numpy")

from autopark.domain.sensors import Costmap  # noqa: E402
from autopark.perception.calibration import (CameraCalibration, Extrinsics, FisheyeIntrinsics,  # noqa: E402
                                             matrix_to_quaternion, quaternion_to_matrix)
from autopark.perception.costmap import FREE, OCCUPIED, UNKNOWN, GridSpec, project_labels, to_costmap  # noqa: E402

WOODSCAPE_FV = {"extrinsic": {"quaternion": [0.5941767906169857, -0.5878843193897473, 0.3873184109007999,
                                             -0.3890121040340926], "translation": [3.7484, 0.0, 0.66017]},
                "intrinsic": {"aspect_ratio": 1.0, "cx_offset": 3.942, "cy_offset": -3.093, "height": 966.0,
                              "k1": 339.749, "k2": -31.988, "k3": 48.275, "k4": -7.201, "model": "radial_poly",
                              "poly_order": 4, "width": 1280.0}, "name": "FV"}


def pitched_rig(pitch_deg=45.0, height=1.0, f=300.0, width=640, image_height=480):
    """Camera at (0, 0, height) looking forward and down by pitch_deg, equidistant fisheye rho = f * theta."""
    c, s = math.cos(math.radians(pitch_deg)), math.sin(math.radians(pitch_deg))
    x_axis = np.array([0.0, -1.0, 0.0])            # camera right = vehicle right (-y)
    z_axis = np.array([c, 0.0, -s])                # optical axis: forward and down
    y_axis = np.cross(z_axis, x_axis)              # camera down
    rotation = np.column_stack([x_axis, y_axis, z_axis])
    return CameraCalibration("test", FisheyeIntrinsics(width, image_height, (f, 0.0, 0.0, 0.0)),
                             Extrinsics.from_matrix(rotation, (0.0, 0.0, height)))


def test_quaternion_matrix_round_trip():
    q = (0.5941767906169857, -0.5878843193897473, 0.3873184109007999, -0.3890121040340926)
    m = quaternion_to_matrix(*q)
    assert np.allclose(m @ m.T, np.eye(3)) and np.linalg.det(m) == pytest.approx(1.0)
    back = matrix_to_quaternion(m)
    assert np.allclose(quaternion_to_matrix(*back), m)


def test_woodscape_front_camera_convention():
    calib = CameraCalibration.from_dict(WOODSCAPE_FV)
    axis = calib.extrinsics.rotation @ np.array([0.0, 0.0, 1.0])
    down = calib.extrinsics.rotation @ np.array([0.0, 1.0, 0.0])
    assert axis[0] > 0.9 and axis[2] < 0                       # forward, pitched down
    assert down[2] < -0.9                                      # image down points to the ground
    assert calib.intrinsics.cx == pytest.approx(639.5 + 3.942) and calib.intrinsics.cy == pytest.approx(482.5 - 3.093)
    u, v, ok = calib.ground_to_pixel([[10.0, 0.0]])
    assert ok[0] and abs(u[0] - calib.intrinsics.cx) < 15 and v[0] < calib.intrinsics.cy   # far ahead: near the centre column, above the principal point
    u, v, ok = calib.ground_to_pixel([[5.0, 2.0]])
    assert ok[0] and u[0] < calib.intrinsics.cx                # +y (left) appears on the left of the image
    xy, valid = calib.pixel_to_ground(*calib.ground_to_pixel([[6.0, -1.5]])[:2])
    assert valid[0] and np.allclose(xy[0], [6.0, -1.5], atol=1e-6)


def test_rays_above_the_horizon_do_not_hit_the_ground():
    calib = pitched_rig()
    xy, valid = calib.pixel_to_ground([calib.intrinsics.cx], [0.0])   # top row looks above the horizon at 45 deg pitch
    assert not valid[0]
    _, _, ok = calib.ground_to_pixel([[-3.0, 0.0]])                    # behind the camera
    assert not ok[0]
    _, _, ok = calib.intrinsics.project([[0.0, 0.0, 0.0]])            # the camera centre itself has no direction
    assert not ok[0]
    # a ray just below the horizon "hits" the plane far away: max_range rejects it
    far_xy, far_valid = calib.pixel_to_ground([calib.intrinsics.cx], [calib.intrinsics.cy - 280.0], max_range=50.0)
    assert not far_valid[0]


def test_woodscape_loader_and_lens_edge():
    import json
    import zipfile
    from autopark.perception.calibration import load_woodscape_calibration
    calib = CameraCalibration.from_dict(WOODSCAPE_FV)
    _, valid = calib.pixel_to_ground([0.0, 1279.0], [965.0, 965.0])      # corners lie outside the calibrated circle
    assert not valid.any()
    with pytest.raises(ValueError):
        CameraCalibration.from_dict({**WOODSCAPE_FV, "intrinsic": {**WOODSCAPE_FV["intrinsic"], "model": "pinhole"}})
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        archive = f"{tmp}/calibration.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("calibration/00007_FV.json", json.dumps(WOODSCAPE_FV))
        loaded = load_woodscape_calibration(archive, "00007_FV")
    assert loaded.name == "FV" and loaded.intrinsics.k == calib.intrinsics.k


def test_intrinsics_reject_non_monotonic_polynomial():
    with pytest.raises(ValueError):
        FisheyeIntrinsics(640, 480, (300.0, 0.0, 0.0, -400.0))


@pytest.mark.parametrize("tall", [False, True])
def test_costmap_projection_marks_free_occupied_occluded_and_unknown(tall):
    calib = pitched_rig()
    grid = GridSpec(-2.0, 8.0, -3.0, 3.0, 0.25)
    labels = np.zeros((480, 640), np.uint8)                    # everything the camera sees is FREE
    u, v, ok = calib.ground_to_pixel([[3.0, 0.0]])
    assert ok[0]
    top = 0 if tall else int(v[0]) - 6                         # tall: a column reaching the top of the image
    labels[top:int(v[0]) + 7, int(u[0]) - 12:int(u[0]) + 13] = 1
    states = project_labels(labels, calib, grid, max_range=6.0)
    assert states.shape == grid.shape
    row = grid.index(0.0, 0.0)[0]                              # the row of cells straddling y = 0
    xs = grid.x_min + (np.arange(grid.shape[1]) + 0.5) * grid.resolution
    line = states[row]
    # ground contact = the cell containing the ground point of the blob's bottom row
    (bottom_xy,), (bottom_ok,) = calib.pixel_to_ground([u[0]], [int(v[0]) + 6])
    assert bottom_ok
    expected_col = grid.index(bottom_xy[0], 0.0)[1]
    assert np.flatnonzero(line == OCCUPIED).tolist() == [expected_col]   # exactly one cell, whatever the height
    assert (line[(xs > 0.5) & (xs < xs[expected_col])] == FREE).all()          # visible ground in front of it
    assert (line[(xs > xs[expected_col]) & (xs < 6.0)] == UNKNOWN).all()       # hidden behind it, not FREE
    assert states[grid.index(3.0, 2.0)] == FREE               # different azimuth, still visible
    assert states[grid.index(-1.5, 0.0)] == UNKNOWN           # behind the camera
    assert states[grid.index(7.5, 0.0)] == UNKNOWN            # beyond max_range
    assert set(np.unique(states).tolist()) <= {UNKNOWN, FREE, OCCUPIED}


def test_cells_outside_the_image_are_unknown_even_when_every_pixel_is_free():
    calib = pitched_rig()
    grid = GridSpec(-2.0, 8.0, -3.0, 3.0, 0.25)
    states = project_labels(np.zeros((480, 640), np.uint8), calib, grid)
    gx, gy = grid.centers()
    _, _, ok = calib.ground_to_pixel(np.column_stack([gx.ravel(), gy.ravel()]))
    assert not ok.all() and (states.ravel()[~ok] == UNKNOWN).all() and (states.ravel()[ok] == FREE).all()
    with pytest.raises(ValueError):
        project_labels(np.zeros((384, 512), np.uint8), calib, grid)        # letterbox-sized mask is refused


def test_camera_away_from_the_origin_shadows_from_its_own_position():
    """Camera at (3.75, 0) like WoodScape FV: cells between the vehicle origin and the camera are unknown,
    and a cell that contains the camera position shadows everything."""
    c, s = math.cos(math.radians(45)), math.sin(math.radians(45))
    rotation = np.column_stack([np.array([0.0, -1.0, 0.0]), np.cross(np.array([c, 0.0, -s]), np.array([0.0, -1.0, 0.0])),
                                np.array([c, 0.0, -s])])
    calib = CameraCalibration("fv", FisheyeIntrinsics(640, 480, (300.0, 0.0, 0.0, 0.0)),
                              Extrinsics.from_matrix(rotation, (3.75, 0.0, 1.0)))
    grid = GridSpec(-2.0, 10.0, -3.0, 3.0, 0.25)
    states = project_labels(np.zeros((480, 640), np.uint8), calib, grid)
    assert states[grid.index(1.0, 0.0)] == UNKNOWN and states[grid.index(6.0, 0.0)] == FREE
    labels = np.ones((480, 640), np.uint8)                     # the model calls the ground under the camera BLOCKED
    states = project_labels(labels, calib, grid)
    assert (states != FREE).all()


def test_grid_spec_rejects_non_aligned_extents_and_clamps_edges():
    with pytest.raises(ValueError):
        GridSpec(0.0, 1.0, 0.0, 1.0, 0.3)
    grid = GridSpec(0.0, 1.0, -0.5, 0.5, 0.5)
    assert grid.index(1.0, 0.5) == (1, 1) and grid.index(0.0, -0.5) == (0, 0)
    with pytest.raises(ValueError):
        grid.index(1.5, 0.0)


def test_ignore_pixels_and_outside_image_become_unknown_never_free():
    calib = pitched_rig()
    grid = GridSpec(0.0, 6.0, -2.0, 2.0, 0.5)
    labels = np.full((480, 640), 255, np.uint8)
    states = project_labels(labels, calib, grid)
    assert (states == UNKNOWN).all()


def test_costmap_contract_is_filled_with_the_documented_layout():
    grid = GridSpec(0.0, 1.0, -0.5, 0.5, 0.5)
    states = np.array([[FREE, OCCUPIED], [UNKNOWN, FREE]], np.int8)
    from autopark.domain.sensors import SourceStamp
    costmap = to_costmap(states, grid, SourceStamp("test", 1.0))
    assert isinstance(costmap, Costmap) and costmap.origin.x == 0.0 and costmap.origin.y == -0.5
    assert costmap.cells == ((0, 1), (-1, 0))
    assert costmap.blocked(0, 1) and costmap.blocked(1, 0) and not costmap.blocked(0, 0)


def test_axis_adjacent_occupied_cell_shadows_its_whole_wedge():
    """Camera on a cell centre, OCCUPIED neighbour one cell ahead: every cell whose sight line crosses that
    square (azimuths up to 45 deg) must be UNKNOWN; the old perpendicular-diagonal cone stopped at 35 deg."""
    c, s = math.cos(math.radians(60)), math.sin(math.radians(60))
    x_axis = np.array([0.0, -1.0, 0.0])
    z_axis = np.array([c, 0.0, -s])                                  # steep pitch: sees the ground right ahead
    rotation = np.column_stack([x_axis, np.cross(z_axis, x_axis), z_axis])
    calib = CameraCalibration("t", FisheyeIntrinsics(640, 480, (300.0, 0.0, 0.0, 0.0)),
                              Extrinsics.from_matrix(rotation, (0.05, 0.05, 1.0)))
    grid = GridSpec(-1.0, 3.0, -2.0, 2.0, 0.1)
    labels = np.zeros((480, 640), np.uint8)
    u, v, ok = calib.ground_to_pixel([[0.15, 0.05]])                # centre of the cell just ahead of the camera
    assert ok[0]
    labels[int(v[0]) - 1:int(v[0]) + 2, int(u[0]) - 1:int(u[0]) + 2] = 1   # 3x3 px: the centre lands on the principal column
    states = project_labels(labels, calib, grid)
    assert states[grid.index(0.15, 0.05)] == OCCUPIED
    for x, y in ((0.45, 0.35), (0.55, 0.45), (1.05, 0.95), (1.05, -0.95)):   # azimuths 37-45 deg, behind the cell
        assert states[grid.index(x, y)] == UNKNOWN, (x, y)
    assert states[grid.index(0.55, 0.85)] == FREE                    # ~58 deg: outside the wedge, still visible
