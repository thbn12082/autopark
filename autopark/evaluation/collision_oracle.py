"""Independent sampled collision oracle for offline validation.

Does not import Shapely, body_corners, FastCollisionChecker or integrate_bicycle.
Uses complex-number transforms, generic polygon SAT and a signed-distance arc.
Sampling is evidence, not a proof of continuous collision freedom.
"""
import cmath
import math

from autopark.domain.types import Pose


def rectangle(x, y, yaw, left, right, bottom, top):
    rotation, origin = cmath.rect(1, yaw), complex(x, y)
    return tuple(origin + complex(a, b) * rotation
                 for a, b in ((left, bottom), (right, bottom), (right, top), (left, top)))


def vehicle_rectangle(cfg, pose, margin=0):
    return rectangle(pose.x, pose.y, pose.yaw, -cfg.rear_overhang - margin,
                     cfg.wheelbase + cfg.front_overhang + margin,
                     -cfg.width / 2 - margin, cfg.width / 2 + margin)


def overlaps(a, b):
    # A generic SAT implementation, deliberately not the optimized 4-axis formula.
    for polygon in (a, b):
        for p, q in zip(polygon, polygon[1:] + polygon[:1]):
            axis = (q - p) * 1j
            pa = [(v * axis.conjugate()).real for v in a]
            pb = [(v * axis.conjugate()).real for v in b]
            if max(pa) < min(pb) or max(pb) < min(pa):
                return False
    return True


def pose_ok(cfg, pose, obstacles, bounds, margin=0):
    body = vehicle_rectangle(cfg, pose, margin)
    if any(p.real < bounds.xmin or p.real > bounds.xmax or p.imag < bounds.ymin or p.imag > bounds.ymax
           for p in body):
        return False
    for obs in obstacles:
        box = rectangle(obs.cx, obs.cy, obs.yaw, -obs.width / 2, obs.width / 2,
                        -obs.height / 2, obs.height / 2)
        if overlaps(body, box):
            return False
    return True


def arc_pose(start, signed_distance, steer, wheelbase):
    angle = signed_distance * math.tan(steer) / wheelbase
    half = angle / 2
    sinc = math.sin(half) / half if abs(half) > 1e-12 else 1.0
    point = complex(start.x, start.y) + cmath.rect(signed_distance * sinc, start.yaw + half)
    yaw = math.atan2(math.sin(start.yaw + angle), math.cos(start.yaw + angle))
    return Pose(point.real, point.imag, yaw)


def arc_ok(cfg, start, signed_distance, steer, obstacles, bounds, samples=51):
    return all(pose_ok(cfg, arc_pose(start, signed_distance * i / (samples - 1), steer, cfg.wheelbase),
                       obstacles, bounds) for i in range(samples))
