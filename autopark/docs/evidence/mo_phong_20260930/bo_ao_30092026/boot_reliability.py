"""Boot reliability of the virtual board: default MTTCG vs -accel tcg,thread=single (alternating trials).
Per trial: start (1 attempt), 5 s telemetry, HMP system_reset, reconnect (HELLO_ACK with new boot_id)."""
import json
import sys
import time

from autopark.transport import qemu_board
from autopark.transport.protocol import Fault, State
from autopark.transport.vehicle_io import SerialVehicleIO, VehicleIOError

TRIALS = int(sys.argv[1]) if len(sys.argv) > 1 else 12
MODES = {"mttcg": (), "single": ("-accel", "tcg,thread=single")}
tools = qemu_board.load_tools()
image = qemu_board.image_path()
rows = []
for i in range(TRIALS):
    for mode, args in MODES.items():
        row = {"trial": i, "mode": mode}
        board = qemu_board.QemuBoard(image, tools, attempts=1, qemu_args=args)
        t0 = time.perf_counter()
        try:
            board.start()
            row["boot_s"] = round(time.perf_counter() - t0, 2)
            io = SerialVehicleIO.open(board.url)
            try:
                info = qemu_board.connect_with_retry(io)
                frames = []
                end = io.now() + 5.0
                while io.now() < end:
                    frames += io.poll()
                    if io.connected and io.now() - io.last_tx_time >= 0.1:
                        io.ping()
                steps = [(b.device_time_ms - a.device_time_ms) & 0xFFFFFFFF for a, b in zip(frames, frames[1:])]
                row.update(frames=len(frames), max_step=max(steps) if steps else None,
                           overrun=any(f.state == State.FAULT and f.fault == Fault.LOOP_OVERRUN for f in frames))
                board.reset()
                time.sleep(0.2)
                try:
                    info2 = qemu_board.connect_with_retry(io, attempts=8, timeout_s=1.0)
                    row["reset_ok"] = info2.boot_id != info.boot_id
                except (VehicleIOError, OSError) as exc:
                    row["reset_ok"] = False
                    row["reset_err"] = str(exc)[:80]
                row["alive_after_reset"] = board.running()
            finally:
                io.close()
        except qemu_board.QemuBoardError as exc:
            row["boot_fail"] = str(exc)[:160]
        finally:
            board.stop()
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
for mode in MODES:
    rs = [r for r in rows if r["mode"] == mode]
    print("SUMMARY", mode, json.dumps({
        "trials": len(rs), "boot_fail": sum("boot_fail" in r for r in rs),
        "reset_fail": sum(r.get("reset_ok") is False for r in rs),
        "overrun": sum(bool(r.get("overrun")) for r in rs),
        "max_step": max((r.get("max_step") or 0) for r in rs),
        "min_frames": min((r.get("frames") or 0) for r in rs if "frames" in r) if any("frames" in r for r in rs) else None}))
