"""Giám sát dữ liệu cũ/mất cho mọi nguồn (camera, LiDAR, telemetry) trên cùng đồng hồ phiên.

Mỗi nguồn có một chính sách: tuổi tối đa và (tùy chọn) chu kỳ mong đợi. `observe()` nhận stamp mới,
`check(now)` trả về các `SafetyEvent` cần phát: chưa từng có dữ liệu, dữ liệu quá cũ, stamp không hợp lệ,
thời gian lùi, hoặc stamp ở tương lai (lệch đồng hồ). Bộ giám sát chỉ báo; hành động dừng là của máy trạng
thái phiên. Cùng logic với kiểm tra phản hồi mô phỏng ở giai đoạn 0, mở rộng cho nhiều nguồn.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

from autopark.domain.sensors import SafetyEvent, SourceStamp

MONITOR_ID = "freshness_monitor"


@dataclass(frozen=True)
class SourcePolicy:
    max_age_s: float
    expected_period_s: float | None = None     # for drop counting only
    future_tolerance_s: float = 0.0
    required: bool = True                       # a required source that never reports blocks the run

    def __post_init__(self):
        if not math.isfinite(self.max_age_s) or self.max_age_s <= 0:
            raise ValueError("max_age_s must be finite and > 0")
        if self.expected_period_s is not None and (not math.isfinite(self.expected_period_s) or self.expected_period_s <= 0):
            raise ValueError("expected_period_s must be finite and > 0")
        if not math.isfinite(self.future_tolerance_s) or self.future_tolerance_s < 0:
            raise ValueError("future_tolerance_s must be finite and >= 0")


@dataclass
class SourceRecord:
    last: SourceStamp | None = None
    count: int = 0
    rejected: int = 0
    drops: int = 0
    gaps: list[float] = field(default_factory=list)


class FreshnessMonitor:
    def __init__(self, policies: dict[str, SourcePolicy]):
        if not policies:
            raise ValueError("At least one source policy is required")
        self.policies = dict(policies)
        self.records: dict[str, SourceRecord] = {name: SourceRecord() for name in policies}

    def observe(self, stamp: SourceStamp, now: float | None = None) -> list[SafetyEvent]:
        """Register a new sample. Returns events for samples that must not be used.

        Pass `now` (session clock) whenever it is known: only then can a sample that is already too old on
        arrival or one stamped in the future be rejected. Without `now` only validity and ordering are checked.
        """
        policy = self.policies.get(stamp.source_id)
        if policy is None:
            raise KeyError(f"No policy for source {stamp.source_id!r}")
        if now is not None and not (math.isfinite(now) and now >= 0):
            raise ValueError("now must be finite and >= 0")
        record = self.records[stamp.source_id]
        events: list[SafetyEvent] = []
        when = stamp.t if now is None else now
        if not stamp.valid:
            record.rejected += 1
            events.append(self._event(when, "INVALID_DATA", f"{stamp.source_id}: sample flagged invalid by its source"))
            return events
        if record.last is not None and stamp.t < record.last.t:
            record.rejected += 1
            events.append(self._event(when, "STAMP_REGRESSION",
                                      f"{stamp.source_id}: timestamp went backwards ({stamp.t:.3f} < {record.last.t:.3f})"))
            return events
        if now is not None and stamp.t > now + policy.future_tolerance_s:
            record.rejected += 1
            events.append(self._event(when, "CLOCK_SKEW",
                                      f"{stamp.source_id}: sample is {stamp.t - now:.3f} s in the future"))
            return events
        if now is not None and now - stamp.t > policy.max_age_s:
            record.rejected += 1
            events.append(self._event(when, "STALE_ON_ARRIVAL",
                                      f"{stamp.source_id}: sample already {now - stamp.t:.3f} s old on arrival "
                                      f"(limit {policy.max_age_s:.3f} s)"))
            return events
        if record.last is not None:
            gap = stamp.t - record.last.t
            record.gaps.append(gap)
            if policy.expected_period_s is not None and gap > 1.5 * policy.expected_period_s:
                record.drops += int(round(gap / policy.expected_period_s)) - 1
        record.last = stamp
        record.count += 1
        return events

    def fresh(self, source_id: str, now: float) -> bool:
        record, policy = self.records[source_id], self.policies[source_id]
        return record.last is not None and record.last.fresh(now, policy.max_age_s)

    def check(self, now: float) -> list[SafetyEvent]:
        """Events for every required source that is missing or stale at `now`."""
        if not (math.isfinite(now) and now >= 0):
            raise ValueError("now must be finite and >= 0")
        events: list[SafetyEvent] = []
        for name, policy in self.policies.items():
            if not policy.required:
                continue
            record = self.records[name]
            if record.last is None:
                events.append(self._event(now, "NO_DATA", f"{name}: no valid sample received yet"))
            elif record.last.t > now + policy.future_tolerance_s:
                events.append(self._event(now, "CLOCK_SKEW",
                                          f"{name}: last sample is {record.last.t - now:.3f} s in the future"))
            elif not record.last.fresh(now, policy.max_age_s):
                events.append(self._event(now, "STALE_DATA",
                                          f"{name}: last sample is {now - record.last.t:.3f} s old (limit {policy.max_age_s:.3f} s)"))
        return events

    def status(self, now: float) -> dict[str, dict]:
        out = {}
        for name, record in self.records.items():
            out[name] = {"count": record.count, "rejected": record.rejected, "drops": record.drops,
                         "age_s": None if record.last is None else now - record.last.t,
                         "fresh": self.fresh(name, now),
                         "max_gap_s": max(record.gaps) if record.gaps else None}
        return out

    @staticmethod
    def _event(t: float, code: str, message: str) -> SafetyEvent:
        return SafetyEvent(SourceStamp(MONITOR_ID, t), code, message, "STOP")
