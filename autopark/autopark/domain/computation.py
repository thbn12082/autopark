"""Cooperative cancellation and wall-clock budgets for background computations.

A context is local to the current thread/task. Nested computations share the
cancel event and may shorten the deadline. Checkpoints belong in search and
simulation loops, not in the live vehicle's physics step.
"""
from __future__ import annotations

import math
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


class ComputationCancelled(RuntimeError):
    pass


class ComputationTimedOut(RuntimeError):
    pass


@dataclass(frozen=True)
class ComputationControl:
    deadline: float = math.inf
    cancel_event: threading.Event = field(default_factory=threading.Event)

    def cancel(self) -> None:
        self.cancel_event.set()

    def check_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise ComputationCancelled("Đã hủy tính toán")

    def check(self) -> None:
        self.check_cancelled()
        if time.perf_counter() >= self.deadline:
            raise ComputationTimedOut("Đã hết thời gian tính toán")

    def with_timeout(self, seconds: float) -> ComputationControl:
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("Ngân sách thời gian phải hữu hạn và >= 0")
        return ComputationControl(min(self.deadline, time.perf_counter() + seconds), self.cancel_event)


_active: ContextVar[ComputationControl | None] = ContextVar("autopark_computation", default=None)


def current_control() -> ComputationControl | None:
    return _active.get()


def checkpoint() -> None:
    control = _active.get()
    if control is not None:
        control.check()


@contextmanager
def computation_scope(control: ComputationControl | None):
    # None inherits an enclosing scope, so helpers need no repeated parameters.
    if control is None:
        checkpoint()
        yield
        return
    token = _active.set(control)
    try:
        control.check()
        yield
    finally:
        _active.reset(token)
