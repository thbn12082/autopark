"""A failed Save/Save As must preserve the previous file and active destination."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from autopark.storage import scenario_store


def test_failed_replace_preserves_file_reference_and_removes_temporary_file(scenario, tmp_path, monkeypatch):
    target = tmp_path / "new" / "scenario.json"
    target.parent.mkdir()
    original_bytes = b'{"previous": "scenario"}\n'
    target.write_bytes(original_bytes)
    scenario.vehicle_config_path = tmp_path / "vehicle.json"
    original_reference = scenario.vehicle_config

    def deny_replace(*_args):
        raise PermissionError("destination is locked")

    monkeypatch.setattr(scenario_store.os, "replace", deny_replace)
    with pytest.raises(PermissionError, match="locked"):
        scenario_store.save_scenario(scenario, target)
    assert target.read_bytes() == original_bytes
    assert scenario.vehicle_config == original_reference
    assert list(target.parent.iterdir()) == [target]


def test_serialization_failure_does_not_truncate_previous_scenario(scenario, tmp_path):
    target = tmp_path / "scenario.json"
    original_bytes = b'{"previous": "scenario"}\n'
    target.write_bytes(original_bytes)
    scenario.name = object()
    with pytest.raises(TypeError):
        scenario_store.save_scenario(scenario, target)
    assert target.read_bytes() == original_bytes


def test_failed_save_as_keeps_previous_ui_destination(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from autopark.ui import main_window
    from autopark.ui.app import DEFAULT_SCENARIO, build_window

    app = QApplication.instance() or QApplication([])
    window = build_window(DEFAULT_SCENARIO)
    old_path = window.scenario_path
    attempted = tmp_path / "locked" / "new.json"
    calls, errors = [], []
    monkeypatch.setattr(main_window.QFileDialog, "getSaveFileName", lambda *_a: (str(attempted), "JSON"))
    monkeypatch.setattr(main_window.QMessageBox, "critical", lambda *_a: errors.append(_a[-1]))

    def fail_save(_scenario, path):
        calls.append(path)
        raise PermissionError("destination is locked")

    monkeypatch.setattr(main_window, "save_scenario", fail_save)
    try:
        window._save_scenario_as()
        assert window.scenario_path == old_path
        assert errors and calls == [attempted]
        # Subsequent Save still targets the previously opened scenario.
        window._save_scenario()
        assert calls[-1] == old_path
    finally:
        window.close()
