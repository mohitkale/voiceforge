"""In-process request counters — lightweight observability without Prometheus."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class ServiceMetrics:
    started_at: float = field(default_factory=time.monotonic)
    voices_created: int = 0
    voices_ready: int = 0
    voices_failed: int = 0
    synth_requests: int = 0
    synth_errors: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def inc(self, name: str, amount: int = 1) -> None:
        with self._lock:
            setattr(self, name, getattr(self, name) + amount)

    def snapshot(self) -> dict:
        with self._lock:
            uptime_s = round(time.monotonic() - self.started_at, 1)
            return {
                "uptimeSeconds": uptime_s,
                "voicesCreated": self.voices_created,
                "voicesReady": self.voices_ready,
                "voicesFailed": self.voices_failed,
                "synthRequests": self.synth_requests,
                "synthErrors": self.synth_errors,
            }


_metrics = ServiceMetrics()


def get_metrics() -> ServiceMetrics:
    return _metrics
