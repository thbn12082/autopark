"""Kiểm số lần đổi chiều của đường trước khi cho chạy (T12, thêm 02/10/2026): chính sách (mặc định không chặn, cảnh báo
khi hơn 7), từ chối ở `Session.start_run` trước mọi I/O với bo (đường và trạng thái READY giữ nguyên), dòng
START_TOO_MANY_CUSPS trong start_refusals.csv của bo MÔ PHỎNG, cờ dòng lệnh, nhãn đường và hộp thoại của giao diện
(offscreen). Không mở cổng nào, không cần bo; không đụng tới bộ lập đường (đường thử dựng thẳng bằng build_trajectory)."""
import argparse
import csv
from dataclasses import replace
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from autopark.application.cusp_policy import (CUSP_WARN_DEFAULT, CuspCheck, CuspPolicy, add_cusp_args,  # noqa: E402
                                              check_cusps, cusp_policy_from_args)
from autopark.application.session import Session, SessionError, SessionState  # noqa: E402
from autopark.application.vehicle_link import EVENT_FIELDS, DriveMode, VehicleLink  # noqa: E402
from autopark.domain.types import Pose  # noqa: E402
from autopark.planning.hybrid_astar import PlanResult  # noqa: E402
from autopark.planning.trajectory import build_trajectory  # noqa: E402
from autopark.transport.vehicle_io import SIM_FIRMWARE_DEFAULT, SimIOConfig  # noqa: E402

SIM_CFG = SimIOConfig(firmware=replace(SIM_FIRMWARE_DEFAULT, boot_hold_ms=200))


def zigzag(n_cusps, start, goal, cfg):
    """Đường có đúng `n_cusps` lần đổi chiều (cách dựng của test_portfolio_validation: mỗi cặp điểm một chiều)."""
    raw = [(Pose(start.x + 0.02 * k, start.y, start.yaw), (-1) ** (k // 2), 0.0) for k in range(2 * (n_cusps + 1))]
    trajectory = build_trajectory(raw, goal, cfg, 0.15, 0.08)
    assert trajectory.n_cusps == n_cusps
    return trajectory


def apply_path(session, n_cusps):
    """Như một lần lập đường xong (`Session.poll_plan`): đường thử thành đường của phiên, phiên sang READY."""
    s = session
    return s._apply_plan(PlanResult("OK", "đường thử", zigzag(n_cusps, s.scenario.start, s.scenario.goal.pose, s.cfg)),
                         s.plan_version)


def ready_session(scenario, cfg, n_cusps, policy=None, link=None) -> Session:
    session = Session(scenario, cfg, cusp_policy=policy)
    if link is not None:
        session.set_vehicle_link(link)
    assert apply_path(session, n_cusps).ok and session.state == SessionState.READY
    return session


def read_rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_policy_defaults_never_refuse_and_warn_only_above_seven():
    policy = CuspPolicy()
    assert (policy.max_cusps, policy.warn_cusps) == (None, CUSP_WARN_DEFAULT) == (None, 7)
    assert policy.to_dict() == {"max_cusps": None, "warn_cusps": 7}
    for n in (0, 1, 7):
        check = CuspCheck(n, policy.max_cusps, policy.warn_cusps)
        assert not check.refused and not check.warned and check.describe() == f"Đường có {n} lần đổi chiều"
    eight = CuspCheck(8, None, 7)
    assert eight.warned and not eight.refused
    assert eight.describe() == ("Đường có 8 lần đổi chiều, nhiều hơn mức cảnh báo 7 (N-D6 đề xuất ≤ 2 ở kịch bản rộng, "
                                "≤ 7 ở kịch bản hẹp; CHƯA CHỐT); vẫn chạy được")
    three = CuspCheck(3, 2, 1)                                  # quá giới hạn: từ chối, không tính là cảnh báo nữa
    assert three.refused and not three.warned
    assert three.describe() == ("Đường có 3 lần đổi chiều, vượt giới hạn 2 (N-D6, CHƯA CHỐT): không đem chạy; đổi vị "
                                "trí xuất phát/ô đỗ rồi tìm đường lại")
    assert three.to_dict() == {"planned": 3, "max_cusps": 2, "warn_cusps": 1, "refused": True, "warned": False}
    assert not CuspCheck(2, 2, None).refused                    # "hơn N" lần, không phải "từ N"
    assert not CuspCheck(9, None, None).warned                  # warn_cusps None: không cảnh báo


@pytest.mark.parametrize("bad", [-1, 1.5, True, "2"])
def test_policy_rejects_negative_bool_or_fractional_limits(bad):
    with pytest.raises(ValueError):
        CuspPolicy(max_cusps=bad)
    with pytest.raises(ValueError):
        CuspPolicy(warn_cusps=bad)


def test_start_is_refused_above_the_limit_and_the_path_stays_ready(scenario, cfg):
    session = ready_session(scenario, cfg, 3, CuspPolicy(max_cusps=2))
    try:
        trajectory = session.trajectory
        assert session.cusp_check() == check_cusps(trajectory, session.cusp_policy) and session.cusp_check().refused
        with pytest.raises(SessionError, match="3 lần đổi chiều, vượt giới hạn 2") as exc:
            session.start_run()
        assert str(exc.value).startswith("Không bắt đầu được: ")
        assert session.state == SessionState.READY and session.world is None and session.run_link is None
        assert session.trajectory is trajectory and trajectory.valid and session.run_snapshot is None
        session.begin_preview_async()                           # xem trước vẫn được
        assert session.state == SessionState.PREPARING_PREVIEW
        session.end_preview()
        session.cusp_policy = CuspPolicy(max_cusps=3)
        session.start_run()
        assert session.state == SessionState.RUNNING
        assert session.run_snapshot["cusps"] == {"planned": 3, "max_cusps": 3, "warn_cusps": 7, "refused": False,
                                                 "warned": False}
    finally:
        session.close()


def test_default_policy_still_runs_a_path_with_many_reversals(scenario, cfg):
    session = ready_session(scenario, cfg, 9)
    try:
        assert session.cusp_check().warned and not session.cusp_check().refused
        session.start_run()
        assert session.state == SessionState.RUNNING
        assert session.run_snapshot["cusps"]["planned"] == 9 and session.run_snapshot["cusps"]["warned"] is True
    finally:
        session.close()


def test_refusal_through_a_vehicle_link_is_logged_before_any_board_io(scenario, cfg, tmp_path):
    link = VehicleLink.simulated(DriveMode.VEHICLE_IO, SIM_CFG)
    session = ready_session(scenario, cfg, 2, CuspPolicy(max_cusps=1), link=link)
    try:
        with pytest.raises(SessionError, match="2 lần đổi chiều, vượt giới hạn 1"):
            session.start_run()
        assert link.io is None and link.runs == 0 and link.refused_starts == 1    # chưa dựng hay mở bo nào
        assert session.state == SessionState.READY and session.run_link is None
        written = link.write_logs(tmp_path / "lan_1")
        rows = read_rows(written["start_refusals.csv"])
        assert len(rows) == 1
        row = rows[0]
        assert (row["code"], row["handling"], row["source"], row["action"]) == ("START_TOO_MANY_CUSPS", "before_start",
                                                                               "session", "LOG")
        assert row["t_session"] == "" and row["t_io"] == "" and "2 lần đổi chiều" in row["message"]
        # Sau review 02/10/2026: dòng dựng bằng cùng bộ dựng với events.csv (_event_row): đủ khóa, đúng thứ tự, có
        # t_perf. csv.DictWriter để trống cột thiếu mà không báo lỗi, nên kiểm cả dòng trong bộ nhớ lẫn ô t_perf trong
        # tệp.
        assert list(link.start_refusals[0]) == EVENT_FIELDS and isinstance(link.start_refusals[0]["t_perf"], float)
        assert float(row["t_perf"]) > 0 and row["call"] == ""
        assert written["events.csv"].read_text(encoding="utf-8").strip() == ",".join(EVENT_FIELDS)   # chỉ tiêu đề
        session.cusp_policy = CuspPolicy(max_cusps=2)
        session.start_run()
        assert session.state == SessionState.RUNNING and link.runs == 1 and link.io is not None
        assert [r["code"] for r in link.start_refusals] == ["START_TOO_MANY_CUSPS"] and link.refused_starts == 1
        assert session.run_snapshot["cusps"]["planned"] == 2 and session.run_snapshot["vehicle_link"]["mode"] == "VEHICLE_IO"
        rows = read_rows(link.write_logs(tmp_path / "lan_2")["start_refusals.csv"])
        assert [r["code"] for r in rows] == ["START_TOO_MANY_CUSPS"]                 # dòng từ chối vẫn còn
        # Liên kết đã có io (sau START): t_io của dòng từ chối là io.now(), như mọi dòng before_start.
        link.record_refused_start("START_TOO_MANY_CUSPS", "thử khi đã có io")
        again = link.start_refusals[-1]
        assert list(again) == EVENT_FIELDS and again["t_io"] == link.io.now() and again["t_session"] == ""
        assert isinstance(again["t_perf"], float) and again["call"] == "" and link.refused_starts == 2
    finally:
        session.close()


def test_cli_flags_build_the_policy(monkeypatch):
    p = argparse.ArgumentParser()
    add_cusp_args(p)
    assert cusp_policy_from_args(p, p.parse_args(["--max-cusps", "2", "--warn-cusps", "1"])) == CuspPolicy(2, 1)
    assert cusp_policy_from_args(p, p.parse_args([])) == CuspPolicy()
    assert cusp_policy_from_args(p, p.parse_args(["--warn-cusps", "0"])) == CuspPolicy(None, 0)
    for argv in (["--max-cusps", "-1"], ["--warn-cusps", "-3"], ["--max-cusps", "1.5"]):
        with pytest.raises(SystemExit) as exc:
            cusp_policy_from_args(p, p.parse_args(argv))
        assert exc.value.code == 2, argv
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from autopark.ui import app, lidar_app
    QApplication.instance() or QApplication([])
    args = app.parse_args(["run_app.py", "scenarios/bai_do_xe.json", "--max-cusps", "3"])
    assert args.scenario == Path("scenarios/bai_do_xe.json") and args.cusp_policy == CuspPolicy(3, 7)
    args = app.parse_args(["run_app.py"])
    assert args.scenario == app.DEFAULT_SCENARIO and args.cusp_policy == CuspPolicy()
    for argv in (["run_app.py", "--max-cusps", "-1"], ["run_app.py", "a.json", "b.json"], ["run_app.py", "--la"]):
        with pytest.raises(SystemExit) as exc:
            app.parse_args(argv)
        assert exc.value.code == 2, argv

    class NoWindow(Exception):
        pass

    seen = {}

    def no_window(*args, **kwargs):
        seen.update(kwargs)
        raise NoWindow

    monkeypatch.setattr(lidar_app, "build_window", no_window)
    with pytest.raises(NoWindow):
        lidar_app.main(["--no-connect", "--max-cusps", "2"])
    assert seen["cusp_policy"] == CuspPolicy(2, CUSP_WARN_DEFAULT)
    seen.clear()
    with pytest.raises(SystemExit) as exc:
        lidar_app.main(["--no-connect", "--max-cusps", "-1"])
    assert exc.value.code == 2 and seen == {}                                       # trước khi dựng cửa sổ


def test_window_warns_about_many_reversals_and_refuses_above_the_limit(monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QMessageBox

    from autopark.ui.app import DEFAULT_SCENARIO, build_window
    QApplication.instance() or QApplication([])
    seen = []

    def warning(*args, **kwargs):
        seen.append(args)
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "warning", warning)
    window = build_window(DEFAULT_SCENARIO, cusp_policy=CuspPolicy(max_cusps=2, warn_cusps=1))
    s = window.session
    try:
        window._after_plan(apply_path(s, 2))
        assert "2 lần đổi chiều" in window.lbl_plan.text() and "nhiều đổi chiều (&gt; 1)" in window.lbl_plan.text()
        assert "mức cảnh báo 1" in window.statusBar().currentMessage() and "mức cảnh báo 1" in window.lbl_plan.toolTip()
        window._after_plan(apply_path(s, 3))
        assert "vượt giới hạn 2: không chạy" in window.lbl_plan.text()
        assert "vượt giới hạn 2" in window.statusBar().currentMessage()
        assert window.primary_action.isEnabled()                # vẫn bấm được: từ chối ở START như mọi lý do khác
        window.run()
        assert len(seen) == 1 and seen[0][1] == "Không bắt đầu được" and "3 lần đổi chiều" in seen[0][2]
        assert s.state == SessionState.READY and s.world is None
        window._after_plan(apply_path(s, 1))
        assert "1 lần đổi chiều" in window.lbl_plan.text() and "<span" not in window.lbl_plan.text()
    finally:
        window.close()
