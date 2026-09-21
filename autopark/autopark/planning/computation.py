"""Map cooperative planner interruption to explicit PlanResult statuses."""
from __future__ import annotations

import inspect
import time
from functools import wraps

from autopark.domain.computation import (
    ComputationCancelled, ComputationControl, ComputationTimedOut,
    computation_scope, current_control,
)


def controlled_plan(default_time_limit: float):
    """Accept optional ``control=`` on a planner, including all nested stages."""
    def decorate(func):
        signature = inspect.signature(func)

        @wraps(func)
        def run(*args, control: ComputationControl | None = None, **kwargs):
            # Local import avoids a cycle: PlanResult lives in hybrid_astar.
            from autopark.planning.hybrid_astar import PlanResult

            bound = signature.bind(*args, **kwargs)
            params = bound.arguments.get("params")
            limit = bound.arguments.get("time_limit")
            if limit is None:
                limit = getattr(params, "time_limit", default_time_limit)
            parent = control or current_control() or ComputationControl()
            budget = parent.with_timeout(limit)
            started = time.perf_counter()
            try:
                with computation_scope(budget):
                    result = func(*args, **kwargs)
                    budget.check_cancelled()
                    return result
            except ComputationCancelled:
                return PlanResult("CANCELLED", "Đã hủy tính đường", elapsed=time.perf_counter() - started)
            except ComputationTimedOut:
                return PlanResult("TIMEOUT", "Đã hết thời gian tìm đường và kiểm chứng",
                                  elapsed=time.perf_counter() - started)

        return run
    return decorate
