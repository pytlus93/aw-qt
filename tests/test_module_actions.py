import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from aw_qt.manager import Module
from aw_qt.module_actions import ActionRunner, load_actions, manifest_path


def manifest(target_module, actions=None, **changes):
    body = {
        "schema_version": 1,
        "module": target_module.name,
        "actions": (
            actions
            if actions is not None
            else [{"id": "configure", "label": "Configure…", "args": ["configure"]}]
        ),
    }
    body.update(changes)
    manifest_path(target_module.path).write_text(json.dumps(body), encoding="utf-8")


@pytest.fixture
def module(tmp_path):
    path = tmp_path / "aw-synthetic.exe"
    path.touch()
    return Module("aw-synthetic", path, "bundled")


def test_missing_and_valid_manifest(module):
    assert load_actions(module.name, module.path) == []
    manifest(module)
    action = load_actions(module.name, module.path)[0]
    assert action.id == "configure" and action.args == ("configure",)


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": 2},
        {"schema_version": True},
        {"module": "aw-other"},
        {"executable": "powershell.exe"},
        {"actions": "bad"},
        {"actions": [{"id": "x", "label": "X", "args": []}]},
        {"actions": [{"id": "x", "label": "X", "args": ["a\u0000b"]}]},
        {"actions": [{"id": "x", "label": "X", "args": ["a"], "requires_running": 1}]},
        {"actions": [{"id": "x", "label": "X", "args": ["a"]}] * 2},
    ],
)
def test_invalid_manifests_are_isolated(module, changes):
    manifest(module, **changes)
    assert load_actions(module.name, module.path) == []


@pytest.mark.parametrize(
    "raw", [b"{", b"\xff", b"x" * 65537], ids=["json", "encoding", "size"]
)
def test_bad_encoding_json_and_size(module, raw):
    manifest_path(module.path).write_bytes(raw)
    assert load_actions(module.name, module.path) == []


@pytest.mark.parametrize(
    "profile,testing", [("default", False), ("testing", True), ("research", False)]
)
def test_literal_launch_context_and_no_watcher_state(
    module, monkeypatch, profile, testing
):
    monkeypatch.setenv("AW_PROFILE", "wrong")
    manifest(
        module,
        actions=[
            {
                "id": "configure",
                "label": "Configure",
                "args": ["configure", "literal & $(value)"],
            }
        ],
    )
    action = load_actions(module.name, module.path)[0]
    process = MagicMock()
    process.poll.return_value = None
    runner = ActionRunner()
    with patch("aw_qt.module_actions.subprocess.Popen", return_value=process) as spawn:
        assert runner.launch(module, action, profile, testing, "http://localhost:5678")
        assert not runner.launch(
            module, action, profile, testing, "http://localhost:5678"
        )
    args, kwargs = spawn.call_args
    assert args[0] == [str(module.path.resolve()), "configure", "literal & $(value)"]
    assert kwargs["shell"] is False
    assert kwargs["env"].get("AW_PROFILE") == (
        None if profile == "default" else profile
    )
    assert kwargs["env"]["AW_TESTING"] == ("1" if testing else "0")
    assert kwargs["env"]["AW_SERVER_URL"] == "http://localhost:5678"
    assert kwargs["env"]["AW_MODULE_ACTION_PROTOCOL"] == "1"
    assert not module.started and module._process is None
    process.poll.return_value = 7
    assert runner.poll() == [("configure", 7)]
    assert runner.poll() == []


def test_stopped_changed_manifest_and_batch_rejected(module, monkeypatch):
    manifest(
        module,
        actions=[
            {"id": "sync", "label": "Sync", "args": ["sync"], "requires_running": True}
        ],
    )
    action = load_actions(module.name, module.path)[0]
    runner = ActionRunner()
    with pytest.raises(ValueError, match="running"):
        runner.launch(module, action, "default", False, "http://localhost:5600")
    manifest(module)
    with pytest.raises(ValueError, match="changed"):
        runner.launch(module, action, "default", False, "http://localhost:5600")
    module.path = module.path.with_suffix(".cmd")
    monkeypatch.setattr("aw_qt.module_actions.sys.platform", "win32")
    with pytest.raises(ValueError, match="native"):
        runner.launch(module, action, "default", False, "http://localhost:5600")


def test_shutdown_terminates_and_bounds_wait(module):
    process = MagicMock()
    process.poll.return_value = None
    process.wait.side_effect = [subprocess.TimeoutExpired("synthetic", 2), 0]
    runner = ActionRunner()
    runner.processes[(module.path, "configure")] = process
    runner.close()
    process.terminate.assert_called_once()
    process.kill.assert_called_once()
    assert runner.processes == {}


def test_launch_failure_does_not_change_module_state(module):
    manifest(module)
    action = load_actions(module.name, module.path)[0]
    runner = ActionRunner()
    with patch(
        "aw_qt.module_actions.subprocess.Popen", side_effect=OSError("synthetic")
    ):
        with pytest.raises(OSError):
            runner.launch(module, action, "default", False, "http://localhost:5600")
    assert not runner.processes and not module.started


def test_shutdown_failure_does_not_abandon_other_helpers(module):
    first, second = MagicMock(), MagicMock()
    first.poll.return_value = second.poll.return_value = None
    first.terminate.side_effect = OSError("synthetic")
    runner = ActionRunner()
    runner.processes[(module.path, "first")] = first
    runner.processes[(module.path, "second")] = second
    runner.close()
    second.terminate.assert_called_once()
    assert runner.processes == {}


def test_real_helper_receives_context_and_exits(tmp_path):
    # Run a disposable synthetic helper through the real subprocess path.
    module = Module("aw-synthetic", Path(sys.executable), "system")
    output = tmp_path / "context.json"
    script = (
        "import os,json,pathlib; pathlib.Path("
        + repr(str(output))
        + ").write_text(json.dumps({k:os.environ.get(k) for k in ['AW_PROFILE','AW_TESTING','AW_SERVER_URL','AW_MODULE_ACTION']}))"
    )
    # Keep the manifest in the test directory; never write beside Python itself.
    body_module = Module("aw-synthetic", tmp_path / "aw-synthetic.exe", "bundled")
    manifest(
        body_module,
        actions=[{"id": "configure", "label": "Configure", "args": ["-c", script]}],
    )
    action = load_actions(body_module.name, body_module.path)[0]
    runner = ActionRunner()
    with patch("aw_qt.module_actions.load_actions", return_value=[action]):
        runner.launch(module, action, "research", True, "http://localhost:5666")
    process = next(iter(runner.processes.values()))
    assert process.wait(timeout=10) == 0
    assert json.loads(output.read_text()) == {
        "AW_PROFILE": "research",
        "AW_TESTING": "1",
        "AW_SERVER_URL": "http://localhost:5666",
        "AW_MODULE_ACTION": "configure",
    }
    assert runner.poll() == [] and not runner.processes


def test_qt_menu_keeps_legacy_toggle_and_action_state(module, tmp_path):
    from PyQt6.QtWidgets import QApplication, QMenu
    from aw_qt.trayicon import TrayIcon

    app = QApplication.instance() or QApplication([])
    legacy = Module("aw-legacy", tmp_path / "aw-legacy.exe", "bundled")
    manifest(
        module,
        actions=[
            {
                "id": "sync",
                "label": "Sync now",
                "args": ["sync"],
                "requires_running": True,
            }
        ],
    )
    tray = SimpleNamespace(
        manager=SimpleNamespace(modules_bundled=[legacy, module], modules_system=[]),
        _action_runner=ActionRunner(),
        _on_module_clicked=MagicMock(),
        _on_module_action=MagicMock(),
        showMessage=MagicMock(),
    )
    tray._refresh_module_actions = lambda: TrayIcon._refresh_module_actions(tray)
    menu = QMenu()
    TrayIcon._build_modulemenu(tray, menu)
    legacy_item = next(a for a in menu.actions() if a.text() == "aw-legacy")
    assert legacy_item.isCheckable() and legacy_item.menu() is None
    submenu = next(a.menu() for a in menu.actions() if a.text() == "aw-synthetic")
    assert submenu.actions()[0].text() == "Running"
    action_item = next(a for a in submenu.actions() if a.text() == "Sync now")
    assert not action_item.isEnabled()
    module.is_alive = lambda: True
    tray._refresh_module_actions()
    assert action_item.isEnabled() and submenu.actions()[0].isChecked()
    action_item.trigger()
    tray._on_module_action.assert_called_once_with(
        module, load_actions(module.name, module.path)[0]
    )
    legacy_item.trigger()
    tray._on_module_clicked.assert_called_once_with(legacy)
    # Bad replacement falls back to a normal toggle on next opening.
    manifest(module, schema_version=99)
    TrayIcon._build_modulemenu(tray, menu)
    assert next(a for a in menu.actions() if a.text() == "aw-synthetic").menu() is None
    app.processEvents()
