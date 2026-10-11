# Local module recovery change

The tray host polls desired-running modules every five seconds. Unexpected exits
and launch failures retry with exponential delay capped at five minutes. A stable
five-minute run resets the delay. Explicit module stops clear recovery state;
recovery never changes persistent autostart configuration. Failed initial starts
remain eligible for retry and do not prevent other modules from starting.

Run dependency-free regressions with:

```powershell
python tests/test_recovery_standalone.py
```

Five synthetic policy tests passed on 2026-10-11. They cover crash restart,
testing-mode propagation, deliberate stops, launch failures with another module,
crash loops and stable-run reset. These are not Qt GUI or installed-host tests.

The inspected Windows installation has a valid login shortcut targeting aw-qt
and autostart entries for server, AFK, window, calendar, VPN and Teams. All seven
processes were running at inspection. This does not establish whether they were
launched automatically after the reported hard restart or started manually.

This source change has not been built or installed. The available bundled Python
lacks aw-core, PyQt6, tomlkit and PyInstaller. Packaging and an isolated host test
must precede replacement of the installed tray. The installed host remains
unchanged. AW tray crashes themselves require OS/launcher recovery; this patch
only supervises child modules while the tray is running. Login startup runs after
sign-in, not before sign-in. Downtime cannot be reconstructed as observed activity.
