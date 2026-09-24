"""ToF trong telemetry xe → `NearFieldReading` → `NearFieldLayer` (thêm 24/09/2026).

Vị trí gá trong `configs/tof_mounts_v0.json` là GIẢ ĐỊNH – CHƯA ĐO. Số đo ToF ở đây do test đặt (trực tiếp, hoặc qua
ngõ vào của `FirmwareModel` sau cổng serial GIẢ); chưa có VL53L1X thật nào được đọc.
"""
from dataclasses import replace
import json
import math
import random

import pytest

np = pytest.importorskip("numpy")

from autopark.domain.sensors import SourceStamp  # noqa: E402
from autopark.domain.types import Pose  # noqa: E402
from autopark.fusion.fuse import fuse  # noqa: E402
from autopark.fusion.layers import (MAP_FRAME, CameraSemanticLayer, NearFieldLayer, NearFieldMount,  # noqa: E402
                                    NearFieldReading, TofMountConfig, TofSensorMount, tof_to_near_field,
                                    unmapped_tof_indices)
from autopark.perception.costmap import FREE, OCCUPIED, UNKNOWN, GridSpec, to_costmap  # noqa: E402
from autopark.transport.firmware_model import FirmwareInputs, FirmwareModel  # noqa: E402
from autopark.transport.loopback import FirmwareSerialLoopback, ManualClock  # noqa: E402
from autopark.transport.protocol import N_TOF, State, TelemetryFlag, TelemetryMsg  # noqa: E402
from autopark.transport.vehicle_io import SIM_FIRMWARE_DEFAULT, SerialVehicleIO, VehicleTelemetry  # noqa: E402
from tests.conftest import PROJECT_ROOT  # noqa: E402

CONFIG_PATH = PROJECT_ROOT / "configs" / "tof_mounts_v0.json"
GRID = GridSpec(0.0, 3.0, 0.0, 2.0, 0.05)
FAST_FW = replace(SIM_FIRMWARE_DEFAULT, boot_hold_ms=200)


def telemetry(tof_mm=(0, 0, 0, 0), mask=0, t=2.0, source_id="esp32_vehicle") -> VehicleTelemetry:
    """Một khung telemetry đi qua đúng phép đổi đơn vị của VehicleIO (mm → m, bit mặt nạ = 0 → None)."""
    msg = TelemetryMsg(1, 5, 1234, int(State.DISARMED), 0, 0, int(TelemetryFlag.LINK_OK), 0, 0xFFFF, 0, 0, 0, 0, 0,
                       0, 0, 0, mask, tuple(tof_mm), 0, 0, 0)
    return VehicleTelemetry.from_message(msg, t, source_id)


def mm(value_m: float) -> int:
    return int(round(value_m * 1000))


@pytest.fixture
def config() -> TofMountConfig:
    return TofMountConfig.load(CONFIG_PATH)


# ---- tệp cấu hình ---------------------------------------------------------------------------------------------------
def test_config_file_maps_every_wire_index_and_says_it_is_assumed(config):
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    assert "GIẢ ĐỊNH – CHƯA ĐO" in raw["notes"] and "ĐỀ XUẤT – CHỜ CHỐT" in raw["notes"]
    assert sorted(config.by_index()) == list(range(N_TOF))
    ids = [s.sensor_id for s in config.sensors]
    assert ids == ["tof_front", "tof_rear", "tof_left", "tof_right"]
    front = config.by_index()[0]
    assert front.mount == NearFieldMount(0.25, 0.0, 0.0, 27.0) and (front.min_range_m, front.max_range_m) == (0.04, 1.3)
    assert config.by_index()[1].mount.yaw == pytest.approx(math.pi)
    assert set(config.near_field_mounts()) == set(ids) and config.source == str(CONFIG_PATH)


def _valid_dict():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("mutate, match", [
    (lambda d: d.update(extra=1), "khóa lạ"),
    (lambda d: d.update(schema_version=2), "schema_version"),
    (lambda d: d["sensors"][0].pop("x_m"), "thiếu"),
    (lambda d: d["sensors"][0].update(z_m=0.1), "khóa lạ"),
    (lambda d: d["sensors"][1].update(index=0), "khác nhau"),
    (lambda d: d["sensors"][1].update(sensor_id="tof_front"), "khác nhau"),
    (lambda d: d["sensors"][0].update(index=N_TOF), "index"),
    (lambda d: d["sensors"][0].update(index=True), "index"),
    (lambda d: d["sensors"][0].update(index=1.0), "index"),
    (lambda d: d["sensors"][0].update(min_range_m=1.3), "min_range_m"),
    (lambda d: d["sensors"][0].update(fov_deg=180.0), "fov_deg"),
    (lambda d: d["sensors"][0].update(x_m=float("nan")), "hữu hạn"),
    # Sửa theo rà soát (muộn tối 24/09/2026): null/chuỗi/bool/danh sách → ValueError nêu cảm biến và khóa, không phải
    # TypeError hay lỗi tiếng Anh của float().
    (lambda d: d["sensors"][0].update(x_m=None), "tof_front: x_m phải là số"),
    (lambda d: d["sensors"][0].update(x_m="0,25"), "tof_front: x_m phải là số"),
    (lambda d: d["sensors"][0].update(x_m="0.25"), "tof_front: x_m phải là số"),
    (lambda d: d["sensors"][0].update(yaw_deg="90"), "tof_front: yaw_deg phải là số"),
    (lambda d: d["sensors"][0].update(fov_deg=True), "tof_front: fov_deg phải là số"),
    (lambda d: d["sensors"][0].update(max_range_m=[1.3]), "tof_front: max_range_m phải là số"),
    (lambda d: d["sensors"][0].update(sensor_id=None), "sensor_id phải là chuỗi"),
    (lambda d: d["sensors"][0].update(sensor_id=""), "sensor_id phải là chuỗi"),
    (lambda d: d["sensors"][0].update(sensor_id=None, x_m="0,25"), "sensor_id phải là chuỗi"),   # báo tên sai trước
    (lambda d: d.update(sensors=[]), "ít nhất"),
    (lambda d: d.update(sensors={}), "danh sách"),
])
def test_config_rejects_bad_or_unknown_entries(mutate, match):
    data = _valid_dict()
    mutate(data)
    with pytest.raises(ValueError, match=match):
        TofMountConfig.from_dict(data)


@pytest.mark.parametrize("sensor_id", ["", None, 7])
def test_config_constructor_rejects_bad_sensor_id(sensor_id):
    """Dựng thẳng `TofMountConfig` (không qua JSON) cũng kiểm sensor_id."""
    with pytest.raises(ValueError, match="sensor_id"):
        TofMountConfig((TofSensorMount(0, sensor_id, NearFieldMount(0.25, 0.0, 0.0, 27.0), 0.04, 1.3),))


# ---- đổi telemetry → NearFieldReading ------------------------------------------------------------------------------
def test_valid_readings_keep_value_stamp_and_sensor(config):
    tel = telemetry((300, 200, 150, 1000), mask=0b1111, t=2.5)
    readings = tof_to_near_field(tel, config)
    assert [r.sensor_id for r in readings] == ["tof_front", "tof_rear", "tof_left", "tof_right"]
    assert [r.range_m for r in readings] == pytest.approx([0.3, 0.2, 0.15, 1.0])
    for r in readings:
        assert r.valid and r.note == "" and r.max_range_m == 1.3
        assert r.stamp == SourceStamp("esp32_vehicle", 2.5, True, r.sensor_id)


@pytest.mark.parametrize("value, note", [
    (None, "mặt nạ"),
    (math.nan, "hữu hạn"),
    (math.inf, "hữu hạn"),
    (0.0, "≤ 0"),
    (-0.1, "≤ 0"),
    (0.02, "tối thiểu"),
    ("0.5", "kiểu lạ"),
])
def test_unusable_values_become_invalid_never_a_safe_distance(config, value, note):
    tel = replace(telemetry((300, 0, 0, 0), mask=0b0001), tof_m=(value, None, None, None))
    front = tof_to_near_field(tel, config)[0]
    assert not front.valid and not front.stamp.valid and math.isnan(front.range_m) and note in front.note


@pytest.mark.parametrize("value", [1.3, 5.0])
def test_values_at_or_beyond_max_range_are_valid_but_mark_nothing(config, value):
    """Sửa theo rà soát (muộn tối 24/09/2026): số đo ≥ tầm tối đa có bit hợp lệ là số đo HỢP LỆ không đánh dấu ô nào
    (hợp đồng cũ của `NearFieldLayer`, ca `far` của tests/test_fusion.py), không phải lỗi làm cả lớp mất hợp lệ."""
    tel = replace(telemetry((300, 0, 0, 0), mask=0b0001), tof_m=(value, None, None, None))
    front = tof_to_near_field(tel, config)[0]
    assert front.valid and front.stamp.valid and front.range_m == pytest.approx(value)
    assert "ngoài tầm" in front.note and "tối đa" in front.note
    layer = NearFieldLayer.from_tof_config(GRID, config)
    costmap = layer.add_telemetry(tel, Pose(1.0, 1.0, 0.0), config)
    states = np.array(costmap.cells)
    assert costmap.stamp.valid and (states == OCCUPIED).sum() == 0 and (states == FREE).sum() == 0
    assert "tof_front" not in layer.invalid_sensors and "ngoài tầm" in layer.sensor_notes["tof_front"]


def test_boundary_values_inside_the_range_are_kept(config):
    tel = replace(telemetry(), tof_m=(0.04, 1.299, None, None))
    front, rear = tof_to_near_field(tel, config)[:2]
    assert front.valid and front.range_m == pytest.approx(0.04)
    assert rear.valid and rear.range_m == pytest.approx(1.299)


def test_invalid_frame_stamp_invalidates_every_reading(config):
    tel = telemetry((300, 300, 300, 300), mask=0b1111)
    tel = replace(tel, stamp=replace(tel.stamp, valid=False))
    readings = tof_to_near_field(tel, config)
    assert not any(r.valid for r in readings) and all("khung" in r.note for r in readings)


def test_unmapped_indices_are_dropped_and_reported():
    only_front = TofMountConfig((TofSensorMount(0, "tof_front", NearFieldMount(0.25, 0.0, 0.0, 27.0), 0.04, 1.3),))
    tel = telemetry((300, 0, 400, 0), mask=0b0101)
    readings = tof_to_near_field(tel, only_front)
    assert [r.sensor_id for r in readings] == ["tof_front"] and readings[0].range_m == pytest.approx(0.3)
    assert unmapped_tof_indices(tel, only_front) == [2]
    assert unmapped_tof_indices(telemetry((300, 0, 0, 0), mask=0b0001), only_front) == []


# ---- NearFieldLayer ------------------------------------------------------------------------------------------------
def occupied_cells(costmap) -> set[tuple[int, int]]:
    states = np.array(costmap.cells)
    return {tuple(ix) for ix in np.argwhere(states == OCCUPIED)}


def test_layer_marks_each_sensor_at_its_mount_and_never_free(config):
    layer = NearFieldLayer.from_tof_config(GRID, config, required=True)
    pose = Pose(1.0, 1.0, 0.0)
    tel = telemetry((mm(0.3), mm(0.2), mm(0.1), mm(0.1)), mask=0b1111, t=2.0)
    costmap = layer.add_telemetry(tel, pose, config)
    states = np.array(costmap.cells)
    assert states[GRID.index(1.55, 1.0)] == OCCUPIED              # mũi 0,25 m + 0,3 m, nhìn trước
    assert states[GRID.index(0.74, 1.0)] == OCCUPIED              # đuôi -0,06 m − 0,2 m, nhìn sau
    assert states[GRID.index(1.095, 1.17)] == OCCUPIED            # hông trái y 0,07 + 0,1 m
    assert states[GRID.index(1.095, 0.83)] == OCCUPIED            # hông phải
    assert states[GRID.index(1.4, 1.0)] == UNKNOWN and (states == FREE).sum() == 0
    assert costmap.stamp.valid and costmap.stamp.t == 2.0 and fuse([layer], GRID, now=2.1).valid
    assert layer.updates == 1                                     # cả khung dựng bản đồ một lần


def test_layer_follows_vehicle_heading(config):
    layer = NearFieldLayer.from_tof_config(GRID, config)
    costmap = layer.add_telemetry(telemetry((mm(0.3), 0, 0, 0), mask=0b0001), Pose(1.0, 0.5, math.pi / 2), config)
    states = np.array(costmap.cells)
    assert states[GRID.index(1.0, 1.05)] == OCCUPIED              # quay 90°: cảm biến trước nhìn +y


FRONT_CELL = GRID.index(1.55, 1.0)          # xe ở (1, 1, 0): mũi 0,25 m + 0,3 m, nhìn trước
REAR_CELL = GRID.index(0.64, 1.0)           # đuôi -0,06 m − 0,3 m, nhìn sau


def test_unusable_tof_drops_only_its_own_arc(config):
    """Sửa theo rà soát (muộn tối 24/09/2026). Trước: một ToF mặt nạ 0 làm cả lớp không hợp lệ, `fuse()` bỏ luôn
    cung OCCUPIED của ToF khác (lớp tùy chọn: mất vật cản im lặng; lớp bắt buộc: chặn cả bản đồ)."""
    layer = NearFieldLayer.from_tof_config(GRID, config, required=True)
    pose = Pose(1.0, 1.0, 0.0)
    good = layer.add_telemetry(telemetry((mm(0.3),) * 4, mask=0b1111, t=2.0), pose, config)
    assert good.stamp.valid and len(occupied_cells(good)) > 0 and layer.invalid_sensors == {}
    # front mặt nạ 0 (không có vật trong tầm hoặc lỗi), các cảm biến khác vẫn đo
    partial = layer.add_telemetry(telemetry((0, mm(0.3), mm(0.3), mm(0.3)), mask=0b1110, t=2.2), pose, config)
    states = np.array(partial.cells)
    assert partial.stamp.valid
    assert states[FRONT_CELL] == UNKNOWN and states[REAR_CELL] == OCCUPIED and (states == FREE).sum() == 0
    result = fuse([layer], GRID, now=2.25)
    assert result.valid and result.counts()["occupied"] > 0 and result.states[REAR_CELL] == OCCUPIED
    assert set(layer.invalid_sensors) == {"tof_front"} and "mặt nạ" in layer.sensor_notes["tof_front"]
    assert result.layers["near_field"]["invalid_sensors"] == layer.invalid_sensors
    # 5 m có bit hợp lệ: không phải "xa, an toàn" (không FREE), cũng không làm lớp mất hợp lệ, không có cung
    out_of_range = layer.add_telemetry(telemetry((mm(5.0), mm(0.3), mm(0.3), mm(0.3)), mask=0b1111, t=2.3), pose,
                                       config)
    states = np.array(out_of_range.cells)
    assert out_of_range.stamp.valid and states[FRONT_CELL] == UNKNOWN and states[REAR_CELL] == OCCUPIED
    assert (states == FREE).sum() == 0 and layer.invalid_sensors == {}
    assert "tối đa" in layer.sensor_notes["tof_front"]


def test_invalid_frame_stamp_makes_the_layer_invalid(config):
    layer = NearFieldLayer.from_tof_config(GRID, config, required=True)
    tel = telemetry((mm(0.3),) * 4, mask=0b1111, t=2.0)
    costmap = layer.add_telemetry(replace(tel, stamp=replace(tel.stamp, valid=False)), Pose(1.0, 1.0, 0.0), config)
    assert not costmap.stamp.valid and len(occupied_cells(costmap)) == 0
    assert set(layer.invalid_sensors) == {"tof_front", "tof_rear", "tof_left", "tof_right"}
    result = fuse([layer], GRID, now=2.05)
    assert not result.valid and result.reasons == ["near_field: nguồn báo không hợp lệ"]


def free_camera_layer(t: float = 2.0) -> CameraSemanticLayer:
    """Camera nói FREE khắp lưới (ví dụ vật cản thấp camera không thấy)."""
    cam = CameraSemanticLayer(GRID)
    cam.set(to_costmap(np.full(GRID.shape, FREE, np.int8), GRID, SourceStamp("camera", t, True, MAP_FRAME)))
    return cam


@pytest.mark.parametrize("required", [False, True])
def test_one_tof_obstacle_survives_fusion_when_the_others_see_nothing(config, required):
    """Cảnh thường gặp: chỉ ToF trước thấy vật, ba ToF kia mặt nạ 0. Ô của vật phải OCCUPIED trong bản đồ hợp nhất,
    kể cả khi camera nói FREE ở đó. Trước bản sửa: lớp ToF không hợp lệ → ô FREE (lớp tùy chọn) hoặc cả bản đồ bị
    chặn (lớp bắt buộc)."""
    layer = NearFieldLayer.from_tof_config(GRID, config, required=required)
    layer.add_telemetry(telemetry((mm(0.3), 0, 0, 0), mask=0b0001, t=2.0), Pose(1.0, 1.0, 0.0), config)
    result = fuse([free_camera_layer(), layer], GRID, now=2.05)
    assert result.valid and result.states[FRONT_CELL] == OCCUPIED


def test_open_space_all_masks_zero_keeps_a_required_layer_valid(config):
    """Mọi ToF mặt nạ 0 (không có gì trong 1,3 m): lớp bắt buộc vẫn hợp lệ, không chặn cả bản đồ, không thêm ô nào."""
    layer = NearFieldLayer.from_tof_config(GRID, config, required=True)
    costmap = layer.add_telemetry(telemetry(mask=0), Pose(1.0, 1.0, 0.0), config)
    assert costmap.stamp.valid and len(occupied_cells(costmap)) == 0 and len(layer.invalid_sensors) == 4
    result = fuse([free_camera_layer(), layer], GRID, now=2.05)
    assert result.valid and result.states[FRONT_CELL] == FREE        # FREE là của camera, không phải của ToF


@pytest.mark.parametrize("tof_mm, mask, lost", [
    ((300, 1400, 300, 300), 0b1111, set()),                      # đuôi 1,4 m ≥ tầm tối đa: hợp lệ, không đánh dấu
    ((300, 1400, 0, 0), 0b0011, {"tof_left", "tof_right"}),
    ((300, 0, 0, 0), 0b0001, {"tof_rear", "tof_left", "tof_right"}),
])
def test_mixed_frames_keep_the_front_obstacle_in_the_fused_map(config, tof_mm, mask, lost):
    layer = NearFieldLayer.from_tof_config(GRID, config)                # mặc định: lớp tùy chọn
    layer.add_telemetry(telemetry(tof_mm, mask=mask, t=2.0), Pose(1.0, 1.0, 0.0), config)
    result = fuse([layer], GRID, now=2.05)
    assert result.valid and result.states[FRONT_CELL] == OCCUPIED and result.counts()["free"] == 0
    assert set(layer.invalid_sensors) == lost and set(result.layers["near_field"]["invalid_sensors"]) == lost


def test_required_sensors_invalidate_the_layer_when_that_sensor_is_unusable(config):
    """`required_sensors` (tùy chọn, mặc định rỗng; CHƯA NÊN BẬT với giao thức v1 vì mặt nạ 0 cũng là "không có vật").
    Cảm biến bắt buộc mất → lớp không hợp lệ; cảm biến khác mất → không sao."""
    with pytest.raises(ValueError, match="required_sensors"):
        NearFieldLayer.from_tof_config(GRID, config, required_sensors={"tof_roof"})
    layer = NearFieldLayer.from_tof_config(GRID, config, required=True, required_sensors={"tof_front"})
    pose = Pose(1.0, 1.0, 0.0)
    nose_lost = layer.add_telemetry(telemetry((0, mm(0.3), 0, 0), mask=0b0010, t=2.0), pose, config)
    assert not nose_lost.stamp.valid and layer.status(2.05)["required_sensors"] == ["tof_front"]
    result = fuse([layer], GRID, now=2.05)
    assert not result.valid and result.reasons == ["near_field: nguồn báo không hợp lệ"]
    nose_ok = layer.add_telemetry(telemetry((mm(0.3), 0, 0, 0), mask=0b0001, t=2.1), pose, config)
    assert nose_ok.stamp.valid and fuse([layer], GRID, now=2.15).valid
    # đường nguồn chung: cảm biến bắt buộc chưa có số đo nào → không hợp lệ
    generic = NearFieldLayer.from_tof_config(GRID, config, required_sensors={"tof_rear"})
    only_front = generic.add_reading(NearFieldReading(SourceStamp("esp32", 2.0), "tof_front", 0.3, 1.3), pose)
    assert not only_front.stamp.valid and generic.invalid_sensors == {"tof_rear": "chưa có số đo"}


def test_generic_readings_stay_valid_while_one_reading_is_valid(config):
    """Đường không có khung (`add_readings` không `frame_stamp`): lớp hợp lệ khi còn ít nhất một số đo hợp lệ; hết số
    đo hợp lệ thì không hợp lệ (như ca một cảm biến của tests/test_fusion.py)."""
    layer = NearFieldLayer.from_tof_config(GRID, config)
    pose = Pose(1.0, 1.0, 0.0)
    stamp = SourceStamp("esp32", 2.0)
    mixed = layer.add_readings([NearFieldReading(stamp, "tof_front", 0.3, 1.3),
                                NearFieldReading(stamp, "tof_rear", math.nan, 1.3, valid=False, note="lỗi I2C")], pose)
    assert mixed.stamp.valid and np.array(mixed.cells)[FRONT_CELL] == OCCUPIED
    assert layer.invalid_sensors == {"tof_rear": "lỗi I2C"}
    none_valid = layer.add_readings([NearFieldReading(stamp, "tof_front", math.nan, 1.3, valid=False)], pose)
    assert not none_valid.stamp.valid and set(layer.invalid_sensors) == {"tof_front", "tof_rear"}


def test_add_readings_rejects_unknown_sensor_without_partial_update(config):
    layer = NearFieldLayer.from_tof_config(GRID, config)
    stamp = SourceStamp("esp32_vehicle", 1.0)
    with pytest.raises(KeyError):
        layer.add_readings([NearFieldReading(stamp, "tof_front", 0.3, 1.3),
                            NearFieldReading(stamp, "tof_roof", 0.3, 1.3)], Pose(1.0, 1.0, 0.0))
    assert layer.readings == {} and layer.costmap is None
    with pytest.raises(ValueError):
        layer.add_readings([], Pose(1.0, 1.0, 0.0))


# ---- qua dây: FirmwareModel → cổng serial giả → VehicleTelemetry → NearFieldReading -----------------------------
def test_tof_over_the_wire_reaches_the_near_field_layer(config):
    clock = ManualClock()
    inputs = FirmwareInputs(tof_valid_mask=0b0101, tof_mm=(300, 777, 150, 5000))   # bit 1, 3 = 0: bo gửi 0
    loop = FirmwareSerialLoopback(FirmwareModel(FAST_FW, boot_id=1), clock, inputs=lambda t_ms: inputs)
    io = SerialVehicleIO(loop, clock=clock, rng=random.Random(2))
    io.connect()
    frames = []
    while len(frames) < 2:
        frames += io.poll()
    tel = frames[-1]
    assert tel.tof_m[1] is None and tel.tof_m[3] is None                  # 777 và 5000 không qua dây (bit = 0)
    assert tel.tof_m[0] == pytest.approx(0.3) and tel.tof_m[2] == pytest.approx(0.15)
    readings = {r.sensor_id: r for r in tof_to_near_field(tel, config)}
    assert readings["tof_front"].valid and readings["tof_front"].range_m == pytest.approx(0.3)
    assert readings["tof_left"].valid and readings["tof_left"].range_m == pytest.approx(0.15)
    assert not readings["tof_rear"].valid and not readings["tof_right"].valid
    assert readings["tof_front"].stamp.t == tel.stamp.t and readings["tof_front"].stamp.source_id == "esp32_vehicle"
    layer = NearFieldLayer.from_tof_config(GRID, config)
    costmap = layer.add_telemetry(tel, Pose(1.0, 1.0, 0.0), config)
    # Sửa theo rà soát (muộn tối 24/09/2026): hai ToF mặt nạ 0 không làm lớp mất hợp lệ, cung trước vẫn vào fuse().
    assert np.array(costmap.cells)[GRID.index(1.55, 1.0)] == OCCUPIED and costmap.stamp.valid
    assert set(layer.status(tel.stamp.t)["invalid_sensors"]) == {"tof_rear", "tof_right"}
    assert fuse([layer], GRID, now=tel.stamp.t + 0.05).states[GRID.index(1.55, 1.0)] == OCCUPIED
    # Bit hợp lệ nhưng số đo vượt tầm: 5 m qua dây là số đo hợp lệ ngoài tầm, không đánh dấu, không bao giờ FREE.
    loop.inputs = lambda t_ms: FirmwareInputs(tof_valid_mask=0b0001, tof_mm=(5000, 0, 0, 0))
    frames = []
    while len(frames) < 2:
        frames += io.poll()
    assert frames[-1].tof_m[0] == pytest.approx(5.0)
    front = tof_to_near_field(frames[-1], config)[0]
    assert front.valid and "ngoài tầm" in front.note
    far = layer.add_telemetry(frames[-1], Pose(1.0, 1.0, 0.0), config)
    assert len(occupied_cells(far)) == 0 and (np.array(far.cells) == FREE).sum() == 0
    io.close()
