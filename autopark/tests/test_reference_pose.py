"""Tệp tư thế tham chiếu (evaluation/reference_pose.py): hợp đồng giữa T4 (trích tư thế từ video) và T5 (chấm).

Mọi tệp sinh trong tmp_path (CSV bị git bỏ qua nên không có tệp mẫu commit sẵn). Thêm 02/10/2026.
"""
import json
import math

import pytest

from autopark.domain.types import Pose
from autopark.evaluation.reference_pose import (CSV_FIELDS, ReferenceAccuracy, ReferenceMeta, ReferenceSample,
                                                SIM_TRUTH_SOURCE, SyncPair, read_reference, reference_from_sim_rows,
                                                sidecar_path, static_reference, write_reference)


def sample_meta(**overrides) -> ReferenceMeta:
    values = dict(method="R1", clock="video",
                  accuracy=ReferenceAccuracy(0.008, 0.9, "TC-1 01/10/2026 docs/evidence/nghiem_thu/tc1.json",
                                             pos_median_m=0.004, yaw_median_deg=0.5),
                  sync=(SyncPair(12.3, 5.0, "session", "dấu đầu"), SyncPair(40.0, 2, "mark")),
                  sync_error_s=0.05, notes="xe giả", source={"video": "r1.mp4", "markers": [3, 7]}, tool="test")
    values.update(overrides)
    return ReferenceMeta(**values)


def five_samples() -> list[ReferenceSample]:
    return [ReferenceSample(0.0333, Pose(1.0, 0.5, 0.1), 1, 2, 0.0012),
            ReferenceSample(0.0667, Pose(1.00123456, 0.5, 0.1), 2, 2, 0.0011),
            ReferenceSample(0.1, None, 3, 0, None),
            ReferenceSample(0.1333, Pose(1.01, 0.51, math.radians(-179.5)), 4, 1, None),
            ReferenceSample(0.1667, Pose(1.02, 0.52, math.radians(179.9)), None, None, 0.002)]


def test_round_trip_keeps_samples_meta_and_sidecar_name(tmp_path):
    csv_path, json_path = write_reference(tmp_path / "lan1" / "tu_the_tham_chieu.csv", five_samples(), sample_meta())
    assert json_path == sidecar_path(csv_path) == tmp_path / "lan1" / "tu_the_tham_chieu.json"
    assert csv_path.read_bytes()[:3] != b"\xef\xbb\xbf"                     # UTF-8 không BOM
    assert csv_path.read_text(encoding="utf-8").splitlines()[0] == ",".join(CSV_FIELDS)
    track = read_reference(csv_path)
    assert track.meta == sample_meta() and track.path == csv_path
    assert len(track.samples) == 5 and len(track.valid_samples) == 4 and track.has_trajectory
    for got, want in zip(track.samples, five_samples()):
        assert got.t == pytest.approx(want.t, abs=5e-5)
        assert (got.frame, got.n_markers) == (want.frame, want.n_markers)
        assert (got.residual_m is None) == (want.residual_m is None)
        if want.pose is None:
            assert got.pose is None
            continue
        assert got.pose.x == pytest.approx(want.pose.x, abs=5e-6)
        assert got.pose.y == pytest.approx(want.pose.y, abs=5e-6)
        assert math.degrees(got.pose.yaw) == pytest.approx(math.degrees(want.pose.yaw), abs=5e-4)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["sync"][1] == {"t_ref_s": 40.0, "mark": 2, "note": ""}       # dấu T14 lưu bằng số thứ tự


def _broken(tmp_path, problem: str):
    """Ghi một tệp hợp lệ rồi làm hỏng đúng một chỗ."""
    csv_path, json_path = write_reference(tmp_path / "ref.csv", five_samples(), sample_meta())
    meta = json.loads(json_path.read_text(encoding="utf-8"))
    lines = csv_path.read_text(encoding="utf-8").splitlines()
    if problem == "missing_sidecar":
        json_path.unlink()
    elif problem in ("schema_version", "kind", "method", "clock", "extra_key", "two_sides"):
        if problem == "schema_version":
            meta["schema_version"] = 2
        elif problem == "kind":
            meta["kind"] = "track"
        elif problem == "method":
            meta["method"] = "R9"
        elif problem == "clock":
            meta["clock"] = "gps"
        elif problem == "extra_key":
            meta["camera"] = "C920"
        else:
            meta["sync"][0]["t_io_s"] = 3.0
        json_path.write_text(json.dumps(meta), encoding="utf-8")
    elif problem == "not_increasing":
        lines[3] = lines[3].replace("0.1000", "0.0500", 1)
    elif problem == "empty_x":
        lines[1] = lines[1].replace("1.00000", "", 1)
    elif problem == "nan_yaw":
        parts = lines[2].split(",")
        parts[4] = "nan"
        lines[2] = ",".join(parts)
    elif problem == "missing_valid":
        lines = [",".join(line.split(",")[:-1]) for line in lines]
    elif problem == "no_valid_row":
        lines = [lines[0]] + [",".join(line.split(",")[:-1] + ["0"]) for line in lines[1:]]
    if problem in ("not_increasing", "empty_x", "nan_yaw", "missing_valid", "no_valid_row"):
        csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return csv_path


@pytest.mark.parametrize("problem, words", [
    ("missing_sidecar", "thiếu tệp mô tả"), ("schema_version", "schema_version"), ("kind", "kind"),
    ("method", "R9"), ("clock", "gps"), ("not_increasing", "tăng ngặt"), ("empty_x", "x_m"), ("nan_yaw", "yaw_deg"),
    ("missing_valid", "thiếu cột valid"), ("no_valid_row", "không có dòng hợp lệ"), ("extra_key", "khóa lạ camera"),
    ("two_sides", "đúng một")])
def test_reader_rejects_malformed_files(tmp_path, problem, words):
    path = _broken(tmp_path, problem)
    with pytest.raises(ValueError) as info:
        read_reference(path)
    message = str(info.value)
    assert message.startswith(f"Tệp tham chiếu {path}") and words in message


def test_yaw_is_wrapped_and_unknown_columns_are_ignored(tmp_path):
    path = tmp_path / "ref.csv"
    path.write_text("t_s,x_m,y_m,yaw_deg,valid,ghi_chu_cua_t4\n0.0,1.0,2.0,270.0,1,abc\n0.5,1.0,2.0,-450,1,\n",
                    encoding="utf-8")
    sidecar_path(path).write_text(json.dumps(sample_meta(sync=(), clock="t_session").to_dict()), encoding="utf-8")
    track = read_reference(path)
    assert [round(math.degrees(s.pose.yaw), 6) for s in track.samples] == [-90.0, -90.0]
    assert track.samples[0].frame is None and track.samples[0].n_markers is None


def test_static_reference_has_one_sample_and_no_trajectory():
    track = static_reference(Pose(2.2, 0.26, math.pi / 2), ReferenceAccuracy(0.0051, 0.16, "R2"))
    assert len(track.samples) == 1 and track.samples[0].t == 0.0
    assert track.meta.method == "R2" and not track.has_trajectory


def test_reference_from_sim_rows_adds_standstill_tail_only_when_stopped():
    rows = [{"t": f"{0.02 * i:.2f}", "x": 0.5 + 0.002 * i, "y": 1.0, "yaw_deg": 0.0, "speed": 0.1} for i in range(10)]
    rows.append({"t": "0.205", "x": 0.52, "y": 1.0, "yaw_deg": 0.0, "speed": "0.0"})
    track = reference_from_sim_rows(rows)
    assert track.meta.method == "MP" and track.meta.clock == "t_session"
    assert track.meta.accuracy == ReferenceAccuracy(0.0, 0.0, SIM_TRUTH_SOURCE)
    tail = track.samples[11:]
    assert len(tail) == 50 and all(s.pose == track.samples[10].pose for s in tail)
    assert tail[-1].t == pytest.approx(0.205 + 1.0) and "không phải dữ liệu ghi" in track.meta.notes
    moving = reference_from_sim_rows(rows[:10])                         # dòng cuối còn chạy: không thêm đuôi
    assert len(moving.samples) == 10 and "Thêm" not in moving.meta.notes
    with pytest.raises(ValueError, match="tăng ngặt"):
        reference_from_sim_rows(rows[:3] + rows[1:2])
