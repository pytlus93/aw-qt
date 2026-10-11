# aw-qt

[![GitHub Actions badge](https://github.com/ActivityWatch/aw-qt/workflows/Build/badge.svg)](https://github.com/ActivityWatch/aw-qt/actions)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Typechecking: Mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)

A service manager and tray icon managing aw-server and watchers, built with Qt.

Use `--profile NAME` to run an isolated named instance. Enabling **Start at login**
from that instance's tray registers the same profile-specific launch command.

For instructions how to build, see `Makefile`.

Optional module-specific tray submenus are documented in
[`docs/module-actions.md`](docs/module-actions.md). They are independent of the
Python/Rust server choice and preserve start/stop for modules without a manifest.
