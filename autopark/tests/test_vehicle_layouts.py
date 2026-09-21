import copy
import math

import pytest
from shapely.geometry import Polygon

from autopark.application.layouts import scatter_parked_cars
from autopark.application.session import Session, SessionError, SessionState
from autopark.domain.types import Bounds
from autopark.geometry.footprint import bounds_polygon, check_pose, obstacle_polygon
from autopark.storage.scenario_store import load_scenario, load_vehicle_config
from tests.conftest import PROJECT_ROOT


@pytest.fixture
def mixed_scene():
    scene = load_scenario(PROJECT_ROOT / "scenarios/bai_do_xe_lon_xon.json")
    cfg = load_vehicle_config(scene.vehicle_config_path)
    scene.sync_goal(cfg)
    return scene, cfg


def assert_valid_placement(scene, cfg, obstacles):
    world = bounds_polygon(scene.bounds)
    shapes = [obstacle_polygon(o) for o in obstacles]
    for i, shape in enumerate(shapes):
        assert world.contains(shape)
        assert not any(shape.intersects(other) for other in shapes[i + 1:])
    assert check_pose(cfg, scene.start, obstacles, scene.bounds).ok
    assert check_pose(cfg, scene.goal.pose, obstacles, scene.bounds).ok


def test_mixed_default_has_six_distinct_angled_cars_and_valid_geometry(mixed_scene):
    scene, cfg = mixed_scene
    cars = [o for o in scene.obstacles if o.kind == "car"]
    assert len(cars) == 6
    assert len({round(o.yaw, 3) for o in cars}) == 6
    assert all(abs(math.sin(2 * o.yaw)) > 0.1 for o in cars)
    assert_valid_placement(scene, cfg, scene.obstacles)


@pytest.mark.parametrize("seed", [0, 1, 2, 8, 42, 173])
def test_scatter_preserves_endpoints_fixed_objects_and_nonoverlap(mixed_scene, seed):
    scene, cfg = mixed_scene
    original = copy.deepcopy(scene.to_dict())
    result = scatter_parked_cars(scene, cfg, seed)
    assert scene.to_dict() == original
    assert [o.id for o in result] == [o.id for o in scene.obstacles]
    assert [o for o in result if o.kind != "car"] == [o for o in scene.obstacles if o.kind != "car"]
    assert_valid_placement(scene, cfg, result)
    assert not any(Polygon(scene.slot.corners()).intersects(obstacle_polygon(o))
                   for o in result if o.kind == "car")


def test_scatter_is_repeatable_by_seed(mixed_scene):
    scene, cfg = mixed_scene
    first = scatter_parked_cars(scene, cfg, 123)
    assert first == scatter_parked_cars(scene, cfg, 123)
    assert first != scatter_parked_cars(scene, cfg, 124)


def test_scatter_failure_does_not_partially_change_the_session(mixed_scene):
    scene, cfg = mixed_scene
    scene.bounds = Bounds(0, 0, 0.15, 0.15)
    session = Session(scene, cfg)
    before = copy.deepcopy(scene.to_dict())
    version = session.plan_version
    with pytest.raises(SessionError):
        session.scatter_cars()
    assert scene.to_dict() == before
    assert session.plan_version == version
    assert session.state == SessionState.EDITING


def test_scatter_is_blocked_while_driving(mixed_scene):
    scene, cfg = mixed_scene
    session = Session(scene, cfg)
    session.start_manual()
    before = copy.deepcopy(scene.to_dict())
    with pytest.raises(SessionError):
        session.scatter_cars()
    assert scene.to_dict() == before
    session.close()
