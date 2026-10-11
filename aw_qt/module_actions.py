"""Optional, server-independent module action manifest and helper lifecycle."""

import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .profile import validate_profile

logger = logging.getLogger(__name__)
ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
MAX_BYTES = 65536


@dataclass(frozen=True)
class ModuleAction:
    id: str
    label: str
    args: Tuple[str, ...]
    requires_running: bool = False


def manifest_path(executable: Path) -> Path:
    # Per-executable name also avoids collisions between PATH-installed modules.
    return executable.with_name(executable.name + ".actions.json")


def _text(value: object, limit: int) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= limit
        and not any(ord(c) < 32 or ord(c) == 127 for c in value)
    )


def load_actions(name: str, executable: Path) -> List[ModuleAction]:
    """Missing/invalid manifests never prevent normal module operation."""
    path = manifest_path(executable)
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("manifest exceeds 64 KiB")
        body = json.loads(raw.decode("utf-8"))
        if not isinstance(body, dict) or set(body) != {
            "schema_version",
            "module",
            "actions",
        }:
            raise ValueError("invalid manifest fields")
        if type(body["schema_version"]) is not int or body["schema_version"] != 1:
            raise ValueError("unsupported manifest version")
        if body["module"] != name:
            raise ValueError("module identity mismatch")
        items = body["actions"]
        if not isinstance(items, list) or len(items) > 20:
            raise ValueError("expected at most 20 actions")
        result = []
        seen = set()
        for item in items:
            if not isinstance(item, dict) or set(item) - {
                "id",
                "label",
                "args",
                "requires_running",
            }:
                raise ValueError("invalid action fields")
            action_id, label, args = item.get("id"), item.get("label"), item.get("args")
            running = item.get("requires_running", False)
            if (
                not isinstance(action_id, str)
                or not ID.fullmatch(action_id)
                or action_id in seen
            ):
                raise ValueError("invalid or duplicate action ID")
            if not _text(label, 100) or "&" in label:
                raise ValueError("invalid action label")
            if (
                not isinstance(args, list)
                or not 1 <= len(args) <= 32
                or not all(_text(arg, 1024) for arg in args)
            ):
                raise ValueError("expected 1 to 32 literal arguments")
            if type(running) is not bool:
                raise ValueError("requires_running must be boolean")
            seen.add(action_id)
            result.append(ModuleAction(action_id, label, tuple(args), running))
        return result
    except FileNotFoundError:
        return []
    except (OSError, UnicodeError, ValueError, RecursionError):
        # No manifest contents/arguments in logs: they may contain private data.
        logger.warning("Ignoring invalid action manifest for %s", name)
        return []


class ActionRunner:
    """One active helper per module/action; never changes watcher desired state."""

    def __init__(self) -> None:
        self.processes: Dict[Tuple[Path, str], subprocess.Popen] = {}

    def poll(self) -> List[Tuple[str, int]]:
        failures = []
        for key, process in list(self.processes.items()):
            code = process.poll()
            if code is not None:
                del self.processes[key]
                if code:
                    failures.append((key[1], code))
        return failures

    def active(self, executable: Path, action: ModuleAction) -> bool:
        process = self.processes.get((executable.resolve(), action.id))
        return process is not None and process.poll() is None

    def launch(
        self, module, action: ModuleAction, profile: str, testing: bool, root_url: str
    ) -> bool:
        executable = module.path.resolve()
        if sys.platform == "win32" and executable.suffix.lower() != ".exe":
            raise ValueError(
                "Windows actions require a native .exe, not a shell wrapper"
            )
        # Revalidate at click time, rather than executing stale menu arguments.
        if action not in load_actions(module.name, module.path):
            raise ValueError("action manifest changed; reopen the Modules menu")
        if action.requires_running and not module.is_alive():
            raise ValueError("module must be running")
        if self.active(executable, action):
            return False
        env = dict(os.environ)
        profile = validate_profile(profile)
        if profile == "default":
            env.pop("AW_PROFILE", None)
        else:
            env["AW_PROFILE"] = profile
        env["AW_MODULE_ACTION"] = action.id
        env["AW_MODULE_ACTION_PROTOCOL"] = "1"
        env["AW_TESTING"] = "1" if testing else "0"
        env["AW_SERVER_URL"] = root_url
        startupinfo: Optional[object] = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        # Same executable; no shell, interpolation, remote endpoint or manifest-selected helper.
        process = subprocess.Popen(
            [str(executable), *action.args],
            env=env,
            cwd=str(executable.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            startupinfo=startupinfo,
        )
        self.processes[(executable, action.id)] = process
        return True

    def close(self) -> None:
        for process in self.processes.values():
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                logger.warning("Could not finish stopping a module action helper")
        self.processes.clear()
