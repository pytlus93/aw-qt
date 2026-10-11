"""Dependency-free recovery regressions; no live AW processes are touched."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "recovery", Path(__file__).parents[1] / "aw_qt" / "recovery.py"
)
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class Module:
    name = "synthetic-watcher"
    def __init__(self):
        self.started = True
        self.alive = False
        self.launches = 0
        self.fail = False
        self.testing = None
    def is_alive(self):
        return self.alive
    def stop(self):
        self.started = False
        self.alive = False
    def start(self, testing):
        self.launches += 1
        self.testing = testing
        if self.fail:
            raise OSError("synthetic launch failure")
        self.started = True
        self.alive = True


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.policy = recovery.ModuleRecovery(lambda: self.now)
        self.module = Module()
    def test_crash_restarts_once_and_preserves_profile(self):
        self.assertEqual(self.policy.check([self.module], True), [self.module])
        self.policy.check([self.module], True)
        self.assertEqual(self.module.launches, 1)
        self.assertTrue(self.module.testing)
    def test_manual_stop_stays_stopped(self):
        self.module.stop()
        self.policy.check([self.module])
        self.assertEqual(self.module.launches, 0)
    def test_launch_failure_does_not_block_other_modules(self):
        self.module.fail = True
        other = Module()
        with self.assertLogs("recovery", level="ERROR"):
            self.policy.check([self.module, other])
        self.assertTrue(self.module.started)
        self.assertTrue(other.alive)
        self.policy.check([self.module])
        self.assertEqual(self.module.launches, 1)
        self.module.fail = False
        self.now = 5
        self.policy.check([self.module])
        self.assertTrue(self.module.alive)
    def test_crash_loop_keeps_retrying_with_bounded_backoff(self):
        for attempt in range(10):
            self.module.alive = False
            self.policy.check([self.module])
            delay = self.policy.retry_at[self.module] - self.now
            self.assertLessEqual(delay, 300)
            self.assertGreaterEqual(delay, 5)
            self.now += delay
        self.assertEqual(self.module.launches, 10)
    def test_stable_run_resets_backoff(self):
        self.policy.check([self.module])
        self.now = 301
        self.policy.check([self.module])
        self.module.alive = False
        self.policy.check([self.module])
        self.assertEqual(self.policy.retry_at[self.module], 306)


if __name__ == "__main__":
    unittest.main()
