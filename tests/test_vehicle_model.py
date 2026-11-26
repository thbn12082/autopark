import math

from pytest import approx

from autopark.domain.types import Pose, VehicleState, wrap_angle
from autopark.simulation.vehicle import SimVehicle, integrate_bicycle

DT = 0.005


def run(vehicle: SimVehicle, steps: int, target_speed: float, target_steer: float) -> VehicleState:
    state = vehicle.state
    for _ in range(steps):
        state = vehicle.step(DT, target_speed, target_steer)
    return state


def test_straight_line_at_constant_speed(cfg):
    vehicle = SimVehicle(cfg, VehicleState(Pose(0.0, 0.0, 0.0), 0.1, 0.0, 0.0))
    state = run(vehicle, 2000, 0.1, 0.0)  # 10 s
    assert state.t == approx(10.0)
    assert state.pose.x == approx(1.0, abs=1e-9)
    assert state.pose.y == approx(0.0, abs=1e-12)
    assert state.pose.yaw == approx(0.0)


def test_constant_steer_traces_circle_of_bicycle_radius(cfg):
    delta = math.radians(20)
    radius = cfg.wheelbase / math.tan(delta)
    vehicle = SimVehicle(cfg, VehicleState(Pose(0.0, 0.0, 0.0), 0.1, delta, 0.0))
    state = run(vehicle, 1000, 0.1, delta)  # 5 s, không có quá độ vì trạng thái đầu = mục tiêu
    theta = 0.1 * math.tan(delta) / cfg.wheelbase * 5.0
    assert state.pose.yaw == approx(wrap_angle(theta), abs=1e-9)
    assert state.pose.x == approx(radius * math.sin(theta), abs=1e-9)
    assert state.pose.y == approx(radius * (1 - math.cos(theta)), abs=1e-9)
    # Tâm quay bên trái tại (0, R)
    assert math.hypot(state.pose.x, state.pose.y - radius) == approx(radius, abs=1e-9)


def test_reverse_with_left_steer_turns_clockwise(cfg):
    delta = math.radians(20)
    vehicle = SimVehicle(cfg, VehicleState(Pose(0.0, 0.0, 0.0), -0.1, delta, 0.0))
    state = run(vehicle, 200, -0.1, delta)
    assert state.pose.x < 0
    assert state.pose.yaw < 0


def test_accel_limit_from_rest(cfg):
    vehicle = SimVehicle(cfg, VehicleState(Pose(0.0, 0.0, 0.0), 0.0, 0.0, 0.0))
    state = vehicle.step(DT, 0.3, 0.0)
    assert state.speed == approx(cfg.max_accel * DT)


def test_steer_rate_limit(cfg):
    vehicle = SimVehicle(cfg, VehicleState(Pose(0.0, 0.0, 0.0), 0.0, 0.0, 0.0))
    state = vehicle.step(DT, 0.0, math.radians(30))
    assert state.steer == approx(cfg.max_steer_rate * DT)


def test_direction_change_brakes_first(cfg):
    vehicle = SimVehicle(cfg, VehicleState(Pose(0.0, 0.0, 0.0), 0.1, 0.0, 0.0))
    state = vehicle.step(DT, -0.1, 0.0)
    assert state.speed == approx(0.1 - cfg.max_decel * DT)


def test_direction_change_crosses_zero_within_a_step(cfg):
    vehicle = SimVehicle(cfg, VehicleState(Pose(0.0, 0.0, 0.0), 0.001, 0.0, 0.0))
    state = vehicle.step(DT, -0.1, 0.0)
    # 0,001/0,6 = 1,667 ms để về 0; 3,333 ms còn lại tăng tốc 0,3 m/s² theo chiều lùi
    assert state.speed == approx(-0.3 * (DT - 0.001 / 0.6))


def test_speed_and_steer_saturate(cfg):
    vehicle = SimVehicle(cfg, VehicleState(Pose(0.0, 0.0, 0.0), 0.0, 0.0, 0.0))
    state = run(vehicle, 2000, 5.0, math.radians(80))
    assert state.speed == approx(cfg.max_speed)
    assert state.steer == approx(cfg.max_steer)


def test_speed_never_overshoots_target(cfg):
    vehicle = SimVehicle(cfg, VehicleState(Pose(0.0, 0.0, 0.0), 0.0, 0.0, 0.0))
    for _ in range(400):
        state = vehicle.step(DT, 0.1, 0.0)
        assert state.speed <= 0.1 + 1e-12
    assert state.speed == approx(0.1)


def test_integrate_tiny_steer_matches_straight():
    pose = Pose(0.0, 0.0, 0.3)
    straight = integrate_bicycle(pose, 0.1, 0.0, DT, 0.19)
    tiny = integrate_bicycle(pose, 0.1, 1e-7, DT, 0.19)
    assert tiny.x == approx(straight.x, abs=1e-9)
    assert tiny.y == approx(straight.y, abs=1e-9)
