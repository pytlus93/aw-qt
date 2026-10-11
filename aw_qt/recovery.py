"""Host-owned recovery that preserves manual stops and retries launch failures."""

import logging
from time import monotonic

logger = logging.getLogger(__name__)


class ModuleRecovery:
    def __init__(self, clock=monotonic):
        self.clock = clock
        self.failures = {}
        self.retry_at = {}
        self.running_since = {}

    def check(self, modules, testing=False):
        recovered = []
        now = self.clock()
        for module in modules:
            if not module.started:
                self.forget(module)
                continue
            try:
                if module.is_alive():
                    since = self.running_since.setdefault(module, now)
                    if now - since >= 300:
                        self.failures.pop(module, None)
                        self.retry_at.pop(module, None)
                    continue
                self.running_since.pop(module, None)
                if now < self.retry_at.get(module, 0):
                    continue
                attempt = self.failures.get(module, 0) + 1
                self.failures[module] = attempt
                self.retry_at[module] = now + min(300, 5 * 2 ** min(attempt - 1, 6))
                # stop clears the old child reference; keep desired state on
                # failure so the next poll retries instead of abandoning it.
                module.stop()
                module.start(testing)
                self.running_since[module] = now
                recovered.append(module)
            except Exception:
                module.started = True
                self.running_since.pop(module, None)
                self.retry_at.setdefault(module, now + 5)
                logger.exception("Unable to recover module %s; will retry", module.name)
        return recovered

    def forget(self, module):
        for state in (self.failures, self.retry_at, self.running_since):
            state.pop(module, None)
