# Module tray actions, protocol 1

Feature branch: `codex/module-tray-actions`. This extension belongs to **aw-qt**,
not either server. No new server endpoints, event fields or bucket types are used.
The same enhanced tray can launch the original Python server or original Rust
server. Modules without a manifest retain their existing checkable menu entry.

An original, unmodified aw-qt still starts/stops the same module and ignores the
JSON sidecar. It cannot display new actions until the tray host is upgraded.
Keep action commands usable directly as the fallback. aw-tauri has a different
tray implementation and does not yet consume this protocol. No installed-host,
reboot, macOS/Linux or original-server runtime validation is claimed here.

## Add support to a watcher

Package a UTF-8 JSON file beside the executable with its **complete filename**
plus `.actions.json`: `aw-example.exe.actions.json` on Windows, or
`aw-example.actions.json` on Unix. Do not name helpers `aw-*` executables that
the old tray would discover as additional watchers. Installation must copy the
sidecar with its matching executable and remove it if rolling back to a version
that lacks these commands.

```json
{
  "schema_version": 1,
  "module": "aw-example",
  "actions": [
    {"id": "configure", "label": "Configure…", "args": ["configure"]},
    {"id": "logs", "label": "Open logs", "args": ["open-logs"]},
    {"id": "status", "label": "Connection status…", "args": ["status-ui"]},
    {"id": "refresh", "label": "Refresh now", "args": ["refresh"], "requires_running": true}
  ]
}
```

These example commands must be implemented by the module; the tray does not
magically provide config/status dialogs. Labels/actions are ordered as declared.
Modules with actions appear as **Modules → module name → Running / Configure…**.
Running is the existing host-owned checkable start/stop action and retains its
autostart/recovery semantics. Stopped modules can still expose configuration.
`requires_running` disables actions until the producer is alive; it does not
provide IPC or launch a second watcher. For Refresh now, use the module's own
local IPC to request work from the running instance, then exit.

Implement action dispatch **before acquiring the watcher singleton lock or
starting collection**. A management helper may have its own dialog singleton.
Unknown commands must fail without falling through to the watcher loop. Keep
configuration paths and migration logic shared with normal startup. For editor
plugins, configuration remains in the editor; this protocol addresses executable
AW modules and must not deploy editor plugins as independent producers.

## Launch context and compatibility

The host launches the same discovered executable by absolute path, with literal
argument arrays, `shell=False`, and its containing directory as the working
directory. On Windows, custom actions require `.exe`; `.cmd`/`.bat` modules retain
normal start/stop but must not opt into actions. No command strings, executable
overrides, substitutions, URLs or Python imports are interpreted from manifests.

Environment for action helpers:

| Variable | Meaning |
|---|---|
| `AW_MODULE_ACTION_PROTOCOL=1` | Host action context protocol |
| `AW_MODULE_ACTION` | Stable selected action ID |
| `AW_PROFILE` | Named/testing profile; absent for default, matching module startup |
| `AW_TESTING=1` or `0` | Explicit testing flag; action dispatcher must consume it |
| `AW_SERVER_URL` | Tray's configured HTTP server root, including its port |

No flags are appended to custom arguments: legacy CLIs have differing subcommand
parsers. New action handlers should read these variables. Without the action
protocol variable, retain their original CLI behavior (including `--testing`).
Explicit CLI config/port options may take precedence when invoked manually.
Configuration comes from the module's existing profile-specific path resolver;
the tray does not guess or transmit private config contents. Existing modules
that do not read `AW_TESTING` in management commands need an adapter before opting
in; for example, the current VPN `manage` command must not be advertised as fully
testing-aware without that change. Named-profile isolation also requires support
in the module itself; exporting an environment variable cannot add it to old code.

Keep the usual AW HTTP transport unchanged, including handling existing-bucket
creation status 304 and retrying delivery after server outages. The actions
protocol has no dependency on project-tracking or modified server capabilities.
Opening config must work with the server stopped. A connection-status action
should display server unavailability rather than treating it as a successful test.

The host prevents duplicate concurrent launches of each module/action, polls exits,
reports nonzero exit status, and terminates owned direct helpers at AW exit with
bounded waits. Helpers must not detach unmanaged descendants; subprocess trees
are not automatically supervised by this protocol. Watcher start/stop and recovery
remain separate. A helper exiting never triggers watcher recovery. Output is not
captured by the tray; helpers should show a dialog and write privacy-safe module
logs. Launch exceptions produce a tray notice without logging arguments or config.

Manifests are trusted installed module code, not downloaded dynamic configuration.
The size limit is 64 KiB, at most 20 actions, 32 arguments/action, 1,024 characters
per argument. Labels are at most 100 characters, IDs lowercase letters/digits,
hyphens/underscores, starting with a letter, at most 64 characters, unique.
Control characters and label mnemonic `&` are rejected. Unknown versions/fields,
bad JSON and identity mismatches reject the entire manifest and preserve the
ordinary module toggle. The host reloads on opening Modules and revalidates on
click; changed actions must be selected again. There is no remote registration.

## Suggested actions

- Common: Configure…, Open logs, Connection status…, About/version.
- VPN: Name connections…, Ignored VPNs…, Payload/privacy settings….
- Calendar: Configure sources…, Last sync status…, Refresh now (through IPC).
- Collection modules: Pause for 15 minutes / Resume, only with explicit module
  support that records gaps and exposes paused state. Running is process state,
  not proof that collection is enabled.

Prefer a small submenu. Do not add destructive Reset/Delete history or cloud
uploads as one-click actions. Keep confirmations and secrets inside module UI.
Start/stop remains host-owned; a module manifest must not substitute its own
independently supervised watcher process.

## Local validation

Use Python 3.12 (the repository supports Python 3.8–3.13) with dependencies from
`pyproject.toml`, plus pytest and Black. No GitHub Actions are added or required.

```powershell
./scripts/validate-module-actions.ps1 -Python 'path/to/python.exe'
```

For a runtime whose dependencies are in a separate local directory, use
`-DependencyDirectory local/test-deps`. The script runs action, manager, recovery,
profile/config and persistent-toggle regressions with offscreen Qt, then checks
formatting of changed files. Existing Linux autostart tests that split XDG paths
on `:` fail for Windows drive-letter paths and are separate from this feature.
Run those on Linux when validating that platform. Native helper tests are
synthetic and do not start watchers, touch real AW config or require a server.

Windows evidence (2026-10-11): Python 3.12.14, aw-core 0.5.18, PyQt6/Qt 6.5.3.
The feature validation script passed 118 tests with one existing skip, including
23 new manifest/helper/Qt tests; formatting passed. The wider suite passed 189
tests with one skip and the three Windows-incompatible Linux autostart cases
deselected. A stale existing tray-toggle fixture was updated to include the
recovery object already required by the baseline implementation. Real subprocess
evidence covers action context and successful exit only; dialogs on an installed
tray and actual Python/Rust-server combinations remain to be validated.
