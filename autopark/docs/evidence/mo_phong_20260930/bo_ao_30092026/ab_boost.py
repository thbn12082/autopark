"""A/B: QemuBoard boost=False vs True under the current host load; 20 s telemetry watch per round.

(Cập nhật 30/09/2026: lượt ≈ 08:47 trong ab_boost.out gọi hàm riêng lúc đó `qemu_board._disable_power_throttling`;
từ 11:53 hàm này là `autopark.power_throttling.disable_power_throttling`, cùng giá trị trả về, và QemuBoard(boost=True)
tự gọi nó trong `_launch`. Dòng gọi dưới đã đổi theo để script chạy lại được.)"""
import json
import sys
import time

from autopark.power_throttling import disable_power_throttling
from autopark.transport import qemu_board
from autopark.transport.protocol import Fault, State
from autopark.transport.vehicle_io import SerialVehicleIO

ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0

tools = qemu_board.load_tools()
image = qemu_board.image_path()
results = []
for r in range(ROUNDS):
    for boost in (False, True):
        board = qemu_board.QemuBoard(image, tools, boost=boost)
        board.start()
        pt = disable_power_throttling(board.proc.pid) if boost else None
        io = SerialVehicleIO.open(board.url)
        overruns = 0
        errors = []
        frames = []
        try:
            qemu_board.connect_with_retry(io)
            io.wait_ready()
            end = io.now() + SECONDS
            last_fault = None
            while io.now() < end:
                for tel in io.poll():
                    frames.append(tel)
                    if tel.state == State.FAULT and tel.fault == Fault.LOOP_OVERRUN and last_fault is None:
                        overruns += 1
                        last_fault = tel
                try:
                    if last_fault is not None and io.connected:
                        io.clear_fault()
                        last_fault = None
                    if io.connected and io.now() - io.last_tx_time >= 0.1:
                        io.ping()
                except Exception as exc:
                    errors.append(type(exc).__name__)
                    if not io.connected:
                        qemu_board.connect_with_retry(io)
        finally:
            io.close()
            board.stop()
        steps = [(b.device_time_ms - a.device_time_ms) & 0xFFFFFFFF for a, b in zip(frames, frames[1:])]
        host = [(b.stamp.t - a.stamp.t) * 1000 for a, b in zip(frames, frames[1:])]
        res = {"round": r, "boost": boost, "power_throttling_off": pt, "frames": len(frames), "overruns": overruns,
               "max_dev_step_ms": max(steps) if steps else None, "max_host_gap_ms": round(max(host), 1) if host else None,
               "stale_events": sum(1 for e in io.events() if e.code == "TELEMETRY_STALE"), "errors": len(errors)}
        results.append(res)
        print(json.dumps(res), flush=True)
print("SUMMARY", json.dumps({b: {"overruns": sum(x["overruns"] for x in results if x["boost"] == b),
                                 "max_dev_step_ms": max(x["max_dev_step_ms"] or 0 for x in results if x["boost"] == b),
                                 "stale": sum(x["stale_events"] for x in results if x["boost"] == b)}
                             for b in (False, True)}))
