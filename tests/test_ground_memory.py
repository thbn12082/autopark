"""Ảnh nhớ mặt sàn: dán ảnh BEV theo tư thế xe rồi đọc lại ở tư thế khác phải khớp mặt sàn thật."""
import math

import numpy as np
import pytest

pytest.importorskip("cv2")

from autopark.perception import ground_memory as gm  # noqa: E402

N, RES, CX = 240, 1.0 / 240, 0.1


def floor(wx, wy):
    """Mặt sàn tổng hợp: vân sin hai hướng, đủ để thấy lệch vài mm."""
    v = 127 + 60 * np.sin(wx * 40) + 50 * np.cos(wy * 33 + wx * 7)
    return np.clip(np.stack([v, 255 - v, (v * 0.5 + 60)], axis=-1), 0, 255).astype(np.uint8)


def canvas_at(pose):
    c, r = np.meshgrid(np.arange(N), np.arange(N))
    x = CX - (r + 0.5 - N / 2) * RES
    y = -(c + 0.5 - N / 2) * RES
    cs, sn = math.cos(pose[2]), math.sin(pose[2])
    return floor(pose[0] + cs * x - sn * y, pose[1] + sn * x + cs * y)


def test_recall_matches_floor_after_moving_and_turning():
    mem = gm.GroundMemory(N, RES, CX, res_m=0.002, size_m=3.0)
    pose0 = np.array([0.0, 0.0, 0.0])
    visible = np.zeros((N, N), bool)
    visible[:100] = True                                    # chỉ nửa trước nhìn thấy
    mem.update(canvas_at(pose0), visible, pose0, t=0.0)
    pose1 = np.array([0.15, 0.03, math.radians(12)])        # tiến 15 cm, sang trái 3 cm, quay 12°
    image, valid = mem.recall(pose1, t=1.0)
    truth = canvas_at(pose1)
    assert valid.sum() > 3000
    inner = valid & np.pad(np.ones((N - 8, N - 8), bool), 4)
    err = np.abs(image[inner].astype(int) - truth[inner].astype(int)).mean()
    assert err < 12                                         # khớp tới vài mức xám (nội suy hai lần)


def test_old_memory_expires_and_recenter_keeps_content():
    mem = gm.GroundMemory(N, RES, CX, res_m=0.004, size_m=2.4, max_age_s=5.0)
    visible = np.ones((N, N), bool)
    pose = np.array([0.0, 0.0, 0.0])
    mem.update(canvas_at(pose), visible, pose, t=0.0)
    assert mem.recall(pose, t=4.0)[1].any() and not mem.recall(pose, t=6.0)[1].any()
    far = np.array([0.5, 0.0, 0.0])                          # gần mép tấm 2,4 m: dời gốc, ảnh cũ vẫn còn
    mem.update(canvas_at(far), np.zeros((N, N), bool), far, t=1.0)
    image, valid = mem.recall(np.array([0.3, 0.0, 0.0]), t=2.0)
    assert valid.sum() > 1000


def test_vehicle_pose_from_sensor_pose():
    sensor = np.array([1.0, 2.0, math.pi / 2])
    v = gm.vehicle_pose_from_sensor(sensor, (0.18, 0.03))
    back = gm.compose_pose(v, np.array([0.18, 0.03, 0.0]))
    assert np.allclose(back, sensor)
