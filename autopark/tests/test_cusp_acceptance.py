"""Giới hạn số lần đổi chiều theo kịch bản nghiệm thu (T12 theo kịch bản, thêm 02/10/2026; người dùng giao quyết định
02/10/2026 ('làm hết') theo đề xuất N-D6 (b), các số vẫn ĐỀ XUẤT – CHỜ CHỐT).

Tệp sa bàn có trường `acceptance` → giới hạn của kịch bản đó trong configs/nguong_nghiem_thu.json (cùng số mà score_run
dùng cho N-D6 (b)); --max-cusps chỉ siết thêm; phát lại và công cụ không đưa tệp ngưỡng nên bỏ qua thẻ; bộ tệp sinh sẵn
scenarios/nghiem_thu. Không chạy planner (đường thử dựng thẳng bằng build_trajectory như tests/test_cusp_policy.py),
không mở cổng hay camera nào: bo MÔ PHỎNG, giao diện offscreen, `ui.lidar_app` với port COM9 không kết nối.
"""
import copy
from dataclasses import replace
import hashlib
import json
import os
import re

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from autopark.application.cusp_policy import (ACCEPTANCE_THRESHOLDS, THRESHOLD_STATUSES,  # noqa: E402
                                              AcceptanceCuspRule, AcceptanceTagError, CuspCheck, CuspPolicy,
                                              check_cusps, read_acceptance_rule, resolve_cusp_limit)
from autopark.application.session import Session, SessionError, SessionState  # noqa: E402
from autopark.application.vehicle_link import DriveMode, VehicleLink  # noqa: E402
from autopark.domain.types import ACCEPTANCE_CODE_RE, AcceptanceTag, ParkingGoal, Pose  # noqa: E402
from autopark.storage.scenario_store import (ACCEPTANCE_VEHICLE_CONFIG, load_scenario,  # noqa: E402
                                            load_vehicle_config, save_scenario)
from tests.conftest import PROJECT_ROOT  # noqa: E402
from tests.test_cusp_policy import SIM_CFG, apply_path, read_rows  # noqa: E402

SA_BAN = PROJECT_ROOT / "scenarios" / "thao_tac_cua_hep.json"
SHA = hashlib.sha256(ACCEPTANCE_THRESHOLDS.read_bytes()).hexdigest()
BASIS = "N-D6 (b) đề xuất, CHƯA CHỐT"
FAKE_SHA = "0" * 64


def rule(code: str, variant: str = "", max_cusps: int | None = None, status: str = "DE_XUAT_CHO_CHOT"):
    tag = AcceptanceTag(code, variant)
    return AcceptanceCuspRule(tag, tag.label, max_cusps, status, "configs/nguong_nghiem_thu.json", FAKE_SHA)


def tagged_file(tmp_path, code: str, variant: str = "", name: str | None = None, source=SA_BAN):
    """Bản sao của `source` gắn thẻ, ghi trong tmp_path (tệp xe vẫn trỏ về configs/ của dự án)."""
    scenario = load_scenario(source)
    scenario.start = Pose(.5, 1, 0)
    scenario.goal = ParkingGoal(Pose(.8, 1, 0))
    scenario.obstacles = []
    scenario.acceptance = AcceptanceTag(code, variant)
    return save_scenario(scenario, tmp_path / (name or f"{code}{variant}.json".lower()))


def tagged(scenario, code: str, variant: str = ""):
    copied = copy.deepcopy(scenario)
    copied.acceptance = AcceptanceTag(code, variant)
    return copied


@pytest.fixture
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialogs(monkeypatch):
    """Hộp thoại QMessageBox bị thay bằng hàm ghi lại (tiêu đề ở args[1], nội dung ở args[2])."""
    from PySide6.QtWidgets import QMessageBox
    seen = {"warning": [], "critical": []}

    def record(kind):
        def show(*args, **kwargs):
            seen[kind].append(args)
            return QMessageBox.StandardButton.Ok
        return show

    monkeypatch.setattr(QMessageBox, "warning", record("warning"))
    monkeypatch.setattr(QMessageBox, "critical", record("critical"))
    return seen


def open_dialog(monkeypatch, path) -> None:
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(path), "JSON (*.json)")))


# ---------------------------------------------------------------- đọc tệp ngưỡng

N_D6_B = [  # (mã, biến thể, khóa, giới hạn): N-D6 (b) của NGUONG mục 1, khóa tìm như Thresholds.rule
    ("DO-1", "", "DO-1", 2), ("DO-2", "p3", "DO-2", 2), ("DO-3", "a", "DO-3a", 2), ("DO-4", "a", "DO-4a", 2),
    ("DO-3", "b", "DO-3b", 7), ("DO-4", "b", "DO-4b", 7), ("DO-5", "", "DO-5", 7), ("DO-6", "", "DO-6", 7),
    ("DO-3", "c", "DO-3c", None), ("VC-5", "do", "VC-5do", 2), ("VC-1", "", "VC-1", None), ("DI-2", "b", "DI-2", None),
]


@pytest.mark.parametrize("code,variant,key,limit", N_D6_B, ids=[f"{c}{v}" for c, v, _, _ in N_D6_B])
def test_thresholds_file_gives_the_n_d6_b_limits(code, variant, key, limit):
    got = read_acceptance_rule(AcceptanceTag(code, variant))
    assert (got.key, got.max_cusps) == (key, limit)
    assert got.tag == AcceptanceTag(code, variant) and got.status == "DE_XUAT_CHO_CHOT" and got.basis == BASIS
    assert got.path == "configs/nguong_nghiem_thu.json" and got.sha256 == SHA
    assert got.to_dict() == {"acceptance": AcceptanceTag(code, variant).to_dict(), "key": key, "max_cusps": limit,
                             "thresholds": {"path": "configs/nguong_nghiem_thu.json", "sha256": SHA,
                                            "status": "DE_XUAT_CHO_CHOT"}}


def test_n_d6_b_thresholds_for_historical_scenarios():
    """Kiểm giới hạn N-D6 (b) trong nguồn cấu hình cho các ca lịch sử."""
    from autopark.evaluation.score_run import load_thresholds

    expected = {"DO-1": 2, "DO-2": 2, "DO-3a": 2, "DO-4a": 2, "DO-3b": 7, "DO-4b": 7, "DO-5": 7, "DO-6": 7,
                "DO-3c": None}
    scenarios = load_thresholds().scenarios
    assert {key for key in scenarios if key.startswith("DO-")} == set(expected)
    assert {key: scenarios[key].max_cusps for key in expected} == expected


def test_reader_agrees_with_score_run_for_every_key():
    from autopark.evaluation import score_run

    assert ACCEPTANCE_THRESHOLDS == score_run.DEFAULT_THRESHOLDS
    assert THRESHOLD_STATUSES == score_run.THRESHOLD_STATUSES
    assert ACCEPTANCE_CODE_RE.pattern == score_run.CODE_RE.pattern
    thresholds = score_run.load_thresholds()
    assert thresholds.sha256 == SHA and len(thresholds.scenarios) > 30
    for key in thresholds.scenarios:
        code = ACCEPTANCE_CODE_RE.match(key).group(0)
        variant = key[len(code):]
        mine, theirs = read_acceptance_rule(AcceptanceTag(code, variant)), thresholds.rule(code, variant)
        assert (mine.key, mine.max_cusps) == (theirs.key, theirs.max_cusps), key
    assert read_acceptance_rule(AcceptanceTag("DO-2", "p3")).key == thresholds.rule("DO-2", "p3").key == "DO-2"


def _set(*keys_and_value):
    *keys, value = keys_and_value

    def mutate(data):
        target = data
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = value
    return mutate


BROKEN = {  # tên: (cách hỏng, thẻ, đoạn phải có trong thông điệp)
    "thieu_tep": ("thiếu", AcceptanceTag("DO-1"), "không đọc được"),
    "khong_phai_json": ("{khong phai json", AcceptanceTag("DO-1"), "không phải JSON"),
    "schema_2": (_set("schema_version", 2), AcceptanceTag("DO-1"), "schema_version 2"),
    "status_la": (_set("status", "TAM"), AcceptanceTag("DO-1"), "status 'TAM'"),
    "max_am": (_set("scenarios", "DO-1", "max_cusps", -1), AcceptanceTag("DO-1"), "scenarios.DO-1.max_cusps"),
    "max_bool": (_set("scenarios", "DO-1", "max_cusps", True), AcceptanceTag("DO-1"), "đang là True"),
    "max_chuoi": (_set("scenarios", "DO-1", "max_cusps", "2"), AcceptanceTag("DO-1"), "đang là '2'"),
    "khoa_DO-9": (None, AcceptanceTag("DO-9"),
                  "các khóa DO: DO-1, DO-2, DO-3a, DO-3b, DO-3c, DO-4a, DO-4b, DO-5, DO-6"),
    "VC-5_thieu_bien_the": (None, AcceptanceTag("VC-5"), "các khóa VC-5: VC-5do, VC-5dung"),
}


@pytest.mark.parametrize("case", list(BROKEN))
def test_broken_thresholds_or_unknown_key_is_refused(tmp_path, case):
    how, tag, fragment = BROKEN[case]
    path, label = ACCEPTANCE_THRESHOLDS, "configs/nguong_nghiem_thu.json"
    if how is not None:
        path, label = tmp_path / "nguong_hong.json", "nguong_hong.json"
        if isinstance(how, str) and how != "thiếu":
            path.write_text(how, encoding="utf-8")
        elif callable(how):
            data = json.loads(ACCEPTANCE_THRESHOLDS.read_text(encoding="utf-8"))
            how(data)
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(AcceptanceTagError) as info:
        read_acceptance_rule(tag, path)
    message = str(info.value)
    assert isinstance(info.value, ValueError) and message.startswith("Tệp ngưỡng ")
    assert label in message and fragment in message and tag.label in message, message


# ---------------------------------------------------------------- thứ tự ưu tiên: cờ chỉ siết thêm

DO3B, DO3C = rule("DO-3", "b", 7), rule("DO-3", "c", None)
PRECEDENCE = {  # tên: (chính sách cờ, luật kịch bản, max, nguồn, cờ bị bỏ, summary, short, origin)
    "khong_gan": (CuspPolicy(), None, None, "mac_dinh", False,
                  "Đổi chiều: không chặn (T12, giới hạn CHƯA CHỐT); cảnh báo khi hơn 7", "", ""),
    "khong_gan_co": (CuspPolicy(2), None, 2, "dong_lenh", False,
                     "Đổi chiều tối đa 2 theo --max-cusps; cảnh báo khi hơn 7", "", ""),
    "gan": (CuspPolicy(), DO3B, 7, "nghiem_thu", False, f"Nghiệm thu DO-3b: đổi chiều tối đa 7 ({BASIS})",
            "tối đa 7 (DO-3b)", f"của DO-3b ({BASIS})"),
    "gan_co_nho_hon": (CuspPolicy(1), DO3B, 1, "dong_lenh", False,
                       "Nghiệm thu DO-3b: đổi chiều tối đa 1 theo --max-cusps (kịch bản cho phép 7)",
                       "tối đa 1 (--max-cusps; DO-3b)", "theo --max-cusps (kịch bản DO-3b cho phép 7)"),
    "gan_co_bang": (CuspPolicy(7), DO3B, 7, "nghiem_thu", False, f"Nghiệm thu DO-3b: đổi chiều tối đa 7 ({BASIS})",
                    "tối đa 7 (DO-3b)", f"của DO-3b ({BASIS})"),
    "gan_co_lon_hon": (CuspPolicy(9), DO3B, 7, "nghiem_thu", True,
                       f"Nghiệm thu DO-3b: đổi chiều tối đa 7 ({BASIS}); --max-cusps 9 lớn hơn nên không dùng",
                       "tối đa 7 (DO-3b)", f"của DO-3b ({BASIS})"),
    "gan_chi_bao_so": (CuspPolicy(), DO3C, None, "nghiem_thu", False,
                       f"Nghiệm thu DO-3c: đổi chiều chỉ báo số, không chặn ({BASIS}); cảnh báo khi hơn 7",
                       "DO-3c: chỉ báo số", f"của DO-3c ({BASIS})"),
    "gan_chi_bao_so_co": (CuspPolicy(3), DO3C, 3, "dong_lenh", False,
                          "Nghiệm thu DO-3c: đổi chiều tối đa 3 theo --max-cusps (kịch bản chỉ báo số)",
                          "tối đa 3 (--max-cusps; DO-3c)", "theo --max-cusps (kịch bản DO-3c: chỉ báo số)"),
}


@pytest.mark.parametrize("case", list(PRECEDENCE))
def test_precedence_flags_only_tighten_an_acceptance_limit(case):
    base, acceptance, top, source, ignored, summary, short, origin = PRECEDENCE[case]
    limit = resolve_cusp_limit(base, acceptance)
    assert (limit.policy.max_cusps, limit.policy.warn_cusps) == (top, 7)
    assert (limit.source, limit.cli_ignored) == (source, ignored)
    assert (limit.summary(), limit.short(), limit.origin) == (summary, short, origin)
    assert limit.rule is acceptance and limit.cli_max_cusps == base.max_cusps
    if top is not None:                                     # câu từ chối nêu giới hạn từ đâu
        refusal = CuspCheck(top + 1, top, 7, limit.origin).describe()
        assert refusal == (f"Đường có {top + 1} lần đổi chiều, vượt giới hạn {top} "
                           f"{origin or '(N-D6, CHƯA CHỐT)'}: không đem chạy; đổi vị trí xuất phát/ô đỗ rồi tìm "
                           "đường lại")


def test_warn_level_and_snapshot_dict_of_a_limit():
    limit = resolve_cusp_limit(CuspPolicy(9, 3), DO3B)                 # --warn-cusps luôn của cờ
    assert (limit.policy.max_cusps, limit.policy.warn_cusps) == (7, 3)
    assert limit.to_dict() == {"source": "nghiem_thu", "max_cusps": 7, "warn_cusps": 3, "cli_max_cusps": 9,
                               "acceptance": {"code": "DO-3", "variant": "b"}, "key": "DO-3b", "rule_max_cusps": 7,
                               "thresholds": {"path": "configs/nguong_nghiem_thu.json", "sha256": FAKE_SHA,
                                              "status": "DE_XUAT_CHO_CHOT"}}
    quiet = resolve_cusp_limit(CuspPolicy(None, None), DO3C)
    assert quiet.summary() == f"Nghiệm thu DO-3c: đổi chiều chỉ báo số, không chặn ({BASIS}); không cảnh báo"
    assert resolve_cusp_limit(CuspPolicy(None, None), None).summary() == ("Đổi chiều: không chặn (T12, giới hạn CHƯA "
                                                                          "CHỐT); không cảnh báo")
    final = resolve_cusp_limit(CuspPolicy(), rule("DO-1", max_cusps=2, status="CHOT"))
    assert final.summary() == "Nghiệm thu DO-1: đổi chiều tối đa 2 (N-D6 (b), đã chốt)"


def test_untagged_texts_are_unchanged(scenario, cfg):
    assert CuspCheck(3, 2, 1).describe() == ("Đường có 3 lần đổi chiều, vượt giới hạn 2 (N-D6, CHƯA CHỐT): không đem "
                                             "chạy; đổi vị trí xuất phát/ô đỗ rồi tìm đường lại")
    assert CuspCheck(3, 2, 1, "của DO-1 (x)").to_dict() == CuspCheck(3, 2, 1).to_dict()   # origin không vào snapshot
    for policy in (CuspPolicy(), CuspPolicy(2), CuspPolicy(1, None)):
        session = Session(copy.deepcopy(scenario), cfg, cusp_policy=policy, acceptance_thresholds=ACCEPTANCE_THRESHOLDS)
        try:
            assert session.acceptance_rule is None and session.cusp_check() is None
            apply_path(session, 3)
            limit = session.cusp_limit()
            assert session.cusp_check() == check_cusps(session.trajectory, limit.policy, origin=limit.origin)
            assert limit.policy.max_cusps == min(3, policy.max_cusps if policy.max_cusps is not None else 3)
        finally:
            session.close()


# ---------------------------------------------------------------- phiên

def test_tagged_session_refuses_before_board_io_and_records_the_rule(tmp_path):
    scenario = load_scenario(tagged_file(tmp_path, "DO-1"))
    link = VehicleLink.simulated(DriveMode.VEHICLE_IO,
                                 replace(SIM_CFG, firmware=replace(SIM_CFG.firmware, max_speed_mm_s=100)))
    session = Session(scenario, load_vehicle_config(scenario.vehicle_config_path),
                      acceptance_thresholds=ACCEPTANCE_THRESHOLDS)
    session.set_vehicle_link(link)
    try:
        assert session.acceptance_rule.key == "DO-1" and session.cusp_limit().policy.max_cusps == 2
        apply_path(session, 3)
        with pytest.raises(SessionError, match=re.escape(f"3 lần đổi chiều, vượt giới hạn 2 của DO-1 ({BASIS})")):
            session.start_run()
        assert link.io is None and link.runs == 0 and link.refused_starts == 1      # chưa dựng hay mở bo nào
        assert session.state == SessionState.READY and session.world is None and session.run_snapshot is None
        rows = read_rows(link.write_logs(tmp_path / "lan_1")["start_refusals.csv"])
        assert [r["code"] for r in rows] == ["START_TOO_MANY_CUSPS"] and "của DO-1" in rows[0]["message"]
        apply_path(session, 2)
        session.start_run()
        assert session.state == SessionState.RUNNING and link.runs == 1
        snapshot = session.run_snapshot
        assert snapshot["cusps"] == {"planned": 2, "max_cusps": 2, "warn_cusps": 7, "refused": False, "warned": False}
        assert snapshot["cusp_rule"] == {"source": "nghiem_thu", "max_cusps": 2, "warn_cusps": 7, "cli_max_cusps": None,
                                         "acceptance": {"code": "DO-1"}, "key": "DO-1", "rule_max_cusps": 2,
                                         "thresholds": {"path": "configs/nguong_nghiem_thu.json", "sha256": SHA,
                                                        "status": "DE_XUAT_CHO_CHOT"}}
        assert snapshot["scenario"]["acceptance"] == {"code": "DO-1"}
        assert list(snapshot)[-2:] == ["cusp_rule", "vehicle_link"]
    finally:
        session.close()


def test_flag_tightens_but_never_loosens_in_a_session(scenario, cfg):
    session = Session(tagged(scenario, "DO-3", "b"), cfg, cusp_policy=CuspPolicy(9),
                      acceptance_thresholds=ACCEPTANCE_THRESHOLDS)
    try:
        apply_path(session, 8)
        limit = session.cusp_limit()
        assert (limit.policy.max_cusps, limit.source, limit.cli_ignored) == (3, "thao_tac_gan", True)
        with pytest.raises(SessionError, match="3 lần đổi chiều"):
            session.start_run()
        assert session.state == SessionState.READY and session.world is None
    finally:
        session.close()
    session = Session(tagged(scenario, "DO-3", "b"), cfg, cusp_policy=CuspPolicy(1),
                      acceptance_thresholds=ACCEPTANCE_THRESHOLDS)
    try:
        apply_path(session, 2)
        refusal = "vượt giới hạn 1 theo --max-cusps (kịch bản DO-3b cho phép 7)"
        with pytest.raises(SessionError, match=re.escape(refusal)):
            session.start_run()
    finally:
        session.close()
    session = Session(tagged(scenario, "DO-3", "c"), cfg, acceptance_thresholds=ACCEPTANCE_THRESHOLDS)
    try:
        apply_path(session, 3)
        assert not session.cusp_check().refused
        session.start_run()
        assert session.state == SessionState.RUNNING and session.run_snapshot["cusps"]["warned"] is False
        assert session.run_snapshot["cusp_rule"]["max_cusps"] == 3
        assert session.run_snapshot["cusp_rule"]["source"] == "thao_tac_gan"
    finally:
        session.close()


SNAPSHOT_KEYS = ["scenario", "vehicle", "planner", "tracker", "feedback", "trajectory", "physics_dt", "control_every",
                 "max_run_time", "cusps", "start_source"]      # start_source: T2 (02/10/2026)
SCENARIO_KEYS = ["schema_version", "name", "notes", "vehicle_config", "bounds", "start", "goal", "obstacles", "seed", "maneuver"]


def test_sessions_without_a_thresholds_path_ignore_tags_and_never_read_files(scenario, cfg, tmp_path, monkeypatch):
    from autopark.application import session as session_module

    def no_read(*args, **kwargs):
        raise AssertionError("không được đọc tệp ngưỡng")

    monkeypatch.setattr(session_module, "read_acceptance_rule", no_read)
    session = Session(tagged(scenario, "DO-1"), cfg)
    try:
        assert session.acceptance_thresholds is None and session.acceptance_rule is None
        apply_path(session, 3)
        session.start_run()
        assert session.state == SessionState.RUNNING and list(session.run_snapshot) == SNAPSHOT_KEYS
        assert session.run_snapshot["scenario"]["acceptance"] == {"code": "DO-1"}
    finally:
        session.close()
    session = Session(copy.deepcopy(scenario), cfg, acceptance_thresholds=tmp_path / "khong_co.json")
    try:
        assert session.acceptance_rule is None
        apply_path(session, 3)
        session.start_run()
        assert session.state == SessionState.RUNNING and list(session.run_snapshot) == SNAPSHOT_KEYS
        assert list(session.run_snapshot["scenario"]) == SCENARIO_KEYS               # gói SIM như trước, từng khóa
    finally:
        session.close()


def test_replace_scenario_switches_the_rule_and_keeps_the_session_on_error(scenario, cfg, monkeypatch):
    session = Session(tagged(scenario, "DO-1"), cfg, acceptance_thresholds=ACCEPTANCE_THRESHOLDS)
    try:
        assert session.cusp_limit().policy.max_cusps == 2
        session.replace_scenario(tagged(scenario, "DO-6"), cfg)
        assert session.acceptance_rule.key == "DO-6" and session.cusp_limit().policy.max_cusps == 3
        session.replace_scenario(copy.deepcopy(scenario), cfg)
        assert session.acceptance_rule is None and session.cusp_limit().policy.max_cusps == 3
        session.replace_scenario(tagged(scenario, "DO-6"), cfg)
        apply_path(session, 3)
        before = (session.scenario, session.acceptance_rule, session.state, session.trajectory, session.plan_version)
        with pytest.raises(AcceptanceTagError, match="'DO-9'"):
            session.replace_scenario(tagged(scenario, "DO-9"), cfg)
        after = (session.scenario, session.acceptance_rule, session.state, session.trajectory, session.plan_version)
        assert all(a is b for a, b in zip(before, after)) and session.state == SessionState.READY
        # Đổi xe (ô "Cấu hình xe") đưa lại chính kịch bản đang mở: giữ giới hạn, không đọc lại tệp ngưỡng.
        from autopark.application import session as session_module

        monkeypatch.setattr(session_module, "read_acceptance_rule", lambda *a, **k: pytest.fail("đọc lại tệp ngưỡng"))
        rule_before = session.acceptance_rule
        session.set_vehicle(cfg)
        assert session.acceptance_rule is rule_before and session.trajectory is None
    finally:
        session.close()


def test_replay_session_ignores_acceptance_tags(scenario, cfg, tmp_path):
    from autopark.storage.run_store import _session_from_snapshot, export_run

    session = Session(tagged(scenario, "DO-6"), cfg, acceptance_thresholds=ACCEPTANCE_THRESHOLDS)
    try:
        apply_path(session, 3)
        session.start_run()
        assert session.state == SessionState.RUNNING
        package = export_run(session, tmp_path / "goi")
    finally:
        session.close()
    run = json.loads((package / "config_snapshot" / "run.json").read_text(encoding="utf-8"))
    assert run["scenario"]["acceptance"] == {"code": "DO-6"} and run["cusp_rule"]["key"] == "DO-6"
    saved = json.loads((package / "config_snapshot" / "scenario.json").read_text(encoding="utf-8"))
    assert saved["acceptance"] == {"code": "DO-6"}
    replayed = _session_from_snapshot(run)
    try:
        assert replayed.scenario.acceptance == AcceptanceTag("DO-6")
        assert replayed.acceptance_rule is None and replayed.cusp_limit().policy.max_cusps == 3
        replayed.start_run()
        assert replayed.state == SessionState.RUNNING and "cusp_rule" not in replayed.run_snapshot
    finally:
        replayed.close()


# ---------------------------------------------------------------- giao diện và điểm vào

def test_window_applies_the_limit_of_the_opened_file(qapp, tmp_path, monkeypatch, dialogs):
    from PySide6.QtWidgets import QFileDialog

    from autopark.ui import theme
    from autopark.ui.app import build_window

    do1, do6 = tagged_file(tmp_path, "DO-1", name="do1.json"), tagged_file(tmp_path, "DO-6", name="do6.json")
    do9 = tagged_file(tmp_path, "DO-9", name="do9.json")
    window = build_window(do1)
    s = window.session
    try:
        summary = f"Nghiệm thu DO-1: đổi chiều tối đa 2 ({BASIS})"
        assert window.lbl_cusp_limit.text() == summary and window.statusBar().currentMessage() == summary
        tip = window.lbl_cusp_limit.toolTip()
        assert "configs/nguong_nghiem_thu.json" in tip and SHA[:12] in tip and "mở lại kịch bản" in tip
        window._after_plan(apply_path(s, 2))
        assert "2 lần đổi chiều  ·  tối đa 2 (DO-1)" in window.lbl_plan.text() and "<span" not in window.lbl_plan.text()
        assert summary in window.lbl_plan.toolTip()
        window._after_plan(apply_path(s, 3))
        assert "vượt giới hạn 2 của DO-1: không chạy" in window.lbl_plan.text()
        assert window.primary_action.isEnabled()
        window.run()
        assert [args[1] for args in dialogs["warning"]] == ["Không bắt đầu được"]
        assert f"vượt giới hạn 2 của DO-1 ({BASIS})" in dialogs["warning"][0][2]
        assert s.state == SessionState.READY and s.world is None
        open_dialog(monkeypatch, do6)
        window._open_scenario()
        assert window.scenario_path == do6 and s.cusp_limit().policy.max_cusps == 3
        assert window.lbl_cusp_limit.text() == "Thao tác gần: đổi chiều tối đa 3"
        assert window.statusBar().currentMessage().endswith(" · Thao tác gần: đổi chiều tối đa 3")
        open_dialog(monkeypatch, do9)
        window._open_scenario()
        assert [args[1] for args in dialogs["critical"]] == ["Không mở được kịch bản"]
        assert "'DO-9'" in dialogs["critical"][0][2]
        assert window.scenario_path == do6 and s.acceptance_rule.key == "DO-6"
        assert s.scenario.acceptance == AcceptanceTag("DO-6")
        saved = tmp_path / "luu" / "ban_sao.json"
        monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(saved), "JSON (*.json)")))
        window._save_scenario_as()
        assert json.loads(saved.read_text(encoding="utf-8"))["acceptance"] == {"code": "DO-6"}   # Lưu thành… giữ thẻ
    finally:
        window.close()
    window = build_window(do1, cusp_policy=CuspPolicy(9))
    try:
        text = window.lbl_cusp_limit.text()
        assert f"color:{theme.WARN}" in text and "--max-cusps 9 lớn hơn nên không dùng" in text
    finally:
        window.close()
    window = build_window(SA_BAN)                                   # tệp không gắn: như trước
    try:
        assert "<span" not in window.lbl_cusp_limit.text() and "tối đa 3" in window.lbl_cusp_limit.text()
        assert "--max-cusps" in window.lbl_cusp_limit.toolTip()
        window._after_plan(apply_path(window.session, 2))
        assert "2 lần đổi chiều" in window.lbl_plan.text()
    finally:
        window.close()
    from autopark.ui import lidar_app

    window, dock = lidar_app.build_window(do1, port="COM9", recording=None)
    try:
        assert window.session.cusp_limit().source == "nghiem_thu" and dock.source is None   # không mở cổng nào
    finally:
        dock.timer.stop()
        window._timer.stop()
        dock.shutdown()
        window.close()


def test_entry_points_exit_2_on_an_unresolvable_tag(qapp, tmp_path, monkeypatch, capsys):
    from autopark.ui import app, lidar_app
    from autopark.ui.main_window import MainWindow

    def must_not_show(*args, **kwargs):
        raise AssertionError("không được hiện cửa sổ khi tệp ngưỡng không cho được giới hạn")

    monkeypatch.setattr(MainWindow, "show", must_not_show)            # BenchWindow kế thừa
    for module in (app, lidar_app):                                   # không đổi EcoQoS của tiến trình pytest
        monkeypatch.setattr(module, "apply_ecoqos_policy", lambda component: None)
    bad = tagged_file(tmp_path, "DO-9", name="do9.json")
    assert app.main(["run_app.py", str(bad)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("run_app.py: lỗi: Tệp ngưỡng configs/nguong_nghiem_thu.json") and "'DO-9'" in err
    with pytest.raises(SystemExit) as info:
        lidar_app.main(["--no-connect", "--scenario", str(bad)])
    assert info.value.code == 2 and "'DO-9'" in capsys.readouterr().err


def test_planner_and_simulation_never_read_the_acceptance_tag():
    """Thẻ chỉ đổi giới hạn lúc Bắt đầu đỗ: planner, mô phỏng và bộ bám không đọc nó, nên kết quả và thời gian lập đường
    không đổi."""
    package = PROJECT_ROOT / "autopark"
    checked, offenders = 0, []
    for folder in ("planning", "simulation", "control"):
        for path in sorted((package / folder).rglob("*.py")):
            checked += 1
            if "acceptance" in path.read_text(encoding="utf-8"):
                offenders.append(path.relative_to(package).as_posix())
    assert checked > 5 and offenders == []
