"""Thí nghiệm test đỗ qua bo ảo hỏng thất thường (06/10/2026, commit 470abb3). KHÔNG sửa repo: chỉ monkeypatch trong
tiến trình này để ghi log.

Mỗi lượt: thân test_nonblocking_control_loop_keeps_up_with_telemetry (chép từ tests/test_firmware_qemu.py, thêm mốc
thời gian) qua `on_board` của test → chờ d giây → parking_run (chép, thêm mốc thời gian) tới khi START có kết quả; START
đạt thì đóng phiên ngay (session.close(): enable=0 + DISARM + đóng socket), không chạy hết 6 s.

Ghi: mọi thông điệp vào/ra của mọi io (perf_counter, session_id, seq, sample_time_ms, state, speed_ref), các mốc
thời gian, 3 khung START, kết quả START, tải CPU hệ thống (GetSystemTimes) trong lượt.

Dùng: python -X utf8 thi_nghiem.py --out ket_qua.jsonl --delays 0,0.05,0.1,0.2,0.4 --reps 4 [--load 8]
"""
import argparse
import ctypes
from ctypes import wintypes
import json
import math
import os
import statistics
import subprocess
import sys
import time
import warnings

REPO = r"D:/xetulai/autopark/autopark"
sys.path.insert(0, REPO)
sys.path.insert(0, REPO + "/tests")
os.chdir(REPO)

from autopark.power_throttling import apply_ecoqos_policy  # noqa: E402

ECOQOS = apply_ecoqos_policy("pytest").state                 # như tests/conftest.py (pytest_configure)

import test_firmware_qemu as T  # noqa: E402  (fresh_io, on_board, BoardSource của chính tệp test)
from autopark.application.session import Session, SessionError  # noqa: E402
from autopark.application.vehicle_link import DriveMode, VehicleLink  # noqa: E402
from autopark.domain.types import Bounds, Obstacle, ParkingGoal, Pose, Scenario, VehicleConfig  # noqa: E402
from autopark.transport import qemu_board  # noqa: E402
from autopark.transport.protocol import Ack, Command, Hello, HelloAck, Request, State, TelemetryMsg  # noqa: E402
from autopark.transport.qemu_plant import QemuPlantVehicleIO  # noqa: E402
from autopark.transport.vehicle_io import VehicleIO  # noqa: E402

perf = time.perf_counter
LOG: list[dict] = []          # mọi thông điệp vào/ra
CUR: dict = {}                # mốc của lượt đang chạy
FIX = None                    # --fix: wait_board_at_rest của bản sao test đã vá (patched/tests/test_firmware_qemu.py)


def _state_name(v):
    try:
        return State(v).name
    except ValueError:
        return str(v)


# ---- móc ghi log (chỉ trong tiến trình này) ------------------------------------------------------------------------
_orig_on_message = VehicleIO._on_message


def _on_message(self, msg, t):
    rec = {"p": perf(), "io": id(self), "dir": "rx", "type": type(msg).__name__, "sid": msg.session_id,
           "my_sid": self.session_id, "sid_ok": msg.session_id == self.session_id and self.session_id != 0,
           "seq": msg.sequence, "before_ack": self._last_dev_seq is None}
    if isinstance(msg, TelemetryMsg):
        rec.update(tau=msg.sample_time_ms, st=_state_name(msg.state), sr=msg.stop_reason, ref=msg.speed_ref_mm_s,
                   cmd_age=msg.cmd_age_ms, last_cmd=msg.last_cmd_seq)
    elif isinstance(msg, Ack):
        rec.update(acked=msg.acked_sequence, res=msg.result, st=_state_name(msg.state))
    elif isinstance(msg, HelloAck):
        rec.update(hello_seq=msg.hello_sequence, st=_state_name(msg.state), period=msg.telemetry_period_ms)
    LOG.append(rec)
    return _orig_on_message(self, msg, t)


VehicleIO._on_message = _on_message

_orig_send = VehicleIO._send_message


def _send_message(self, msg):
    rec = {"p": perf(), "io": id(self), "dir": "tx", "type": type(msg).__name__, "sid": msg.session_id,
           "seq": msg.sequence}
    if isinstance(msg, Command):
        rec.update(enable=msg.flags & 1, speed=msg.speed_mm_s)
    elif isinstance(msg, Request):
        rec.update(action=msg.action)
    elif isinstance(msg, Hello):
        rec.update(period=msg.telemetry_period_ms)
    LOG.append(rec)
    return _orig_send(self, msg)


VehicleIO._send_message = _send_message

_orig_reopen = QemuPlantVehicleIO.reopen


def _reopen(self):
    CUR["p_reopen0"] = perf()
    CUR["park_io"] = id(self)
    try:
        return _orig_reopen(self)
    finally:
        CUR["p_reopen1"] = perf()


QemuPlantVehicleIO.reopen = _reopen

_orig_connect = QemuPlantVehicleIO.connect


def _connect(self, timeout_s=1.0):
    CUR["p_connect0"] = perf()
    try:
        return _orig_connect(self, timeout_s)
    finally:
        CUR["p_connect1"] = perf()


QemuPlantVehicleIO.connect = _connect

_orig_wait_ready = VehicleIO.wait_ready


def _wait_ready(self, timeout_s=3.0):
    try:
        return _orig_wait_ready(self, timeout_s)
    finally:
        if isinstance(self, QemuPlantVehicleIO):
            CUR["p_ready1"] = perf()


VehicleIO.wait_ready = _wait_ready

_orig_new_tel = VehicleLink._new_telemetry


def _new_telemetry(self, after, count):
    p0 = perf()
    samples = _orig_new_tel(self, after, count)
    CUR.setdefault("new_tel", []).append({
        "p_call": p0, "p_ret": perf(), "count": count,
        "samples": [{"t": s.stamp.t, "tau": s.device_time_ms, "seq": s.sequence, "st": s.state.name,
                     "ref": s.speed_ref_mps, "v": s.speed_mps} for s in samples]})
    return samples


VehicleLink._new_telemetry = _new_telemetry

_orig_sp = VehicleLink._start_problems


def _start_problems(self, samples, scenario, cfg):
    problems, summary = _orig_sp(self, samples, scenario, cfg)
    CUR["start_problems"] = problems
    CUR["start_summary"] = summary
    CUR["p_check"] = perf()
    return problems, summary


VehicleLink._start_problems = _start_problems


# ---- fixture của conftest (chép) -----------------------------------------------------------------------------------
def make_cfg() -> VehicleConfig:
    return VehicleConfig(name="xe_test", wheelbase=0.19, width=0.14, front_overhang=0.06, rear_overhang=0.06,
                         max_steer=math.radians(30), max_speed=0.3, max_accel=0.3, max_decel=0.6,
                         max_steer_rate=math.radians(90))


def make_scenario() -> Scenario:
    sc = Scenario(name="test", bounds=Bounds(0.0, 0.0, 3.0, 2.0), start=Pose(0.5, 1.0, 0.0),
                  goal=ParkingGoal(Pose(2.4, 0.4, math.pi / 2)),
                  obstacles=[Obstacle("hop_1", 1.2, 1.0, 0.2, 0.2, 0.0)])
    # như đầu test_parking_session_through_qemu_board
    sc.obstacles = []
    sc.start, sc.goal = Pose(0.5, 1.0, 0.0), ParkingGoal(Pose(1.1, 1.0, 0.0))
    return sc


# ---- thân test nonblocking (chép, thêm mốc) ------------------------------------------------------------------------
def nonblocking_body(io, marks):
    io.arm()
    io.take_new()                                                # bỏ khung đã nhận trong fresh_io/arm
    missed0 = io.stats.device_messages_missed
    got = []
    end = time.perf_counter() + 2.0
    while time.perf_counter() < end:
        t = time.perf_counter()
        got += io.poll(block=False)
        io.send(0.1, 0.0, enable=True, validity_s=0.15)
        rest = 0.02 - (time.perf_counter() - t)
        if rest > 0:
            time.sleep(rest)
    marks["nb_io"] = id(io)
    marks["nb_sid"] = io.session_id
    marks["p_stop"] = perf()
    io.stop()
    io.disarm()
    marks["p_disarm_ret"] = perf()
    marks["nb_frames"] = len(got)
    assert len(got) >= 36                                        # ≈ 40 khung trong 2 s
    assert io.stats.device_messages_missed == missed0            # không mất số thứ tự nào
    assert "TELEMETRY_STALE" not in [e.code for e in io.events()]


# ---- tải CPU hệ thống ----------------------------------------------------------------------------------------------
class CpuMeter:
    def __init__(self):
        self.k32 = ctypes.WinDLL("kernel32")
        self.k32.GetSystemTimes.argtypes = [ctypes.POINTER(wintypes.FILETIME)] * 3

    def read(self):
        idle, kernel, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
        self.k32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
        f = lambda x: (x.dwHighDateTime << 32) | x.dwLowDateTime  # noqa: E731
        return f(idle), f(kernel), f(user)

    @staticmethod
    def load(a, b):
        di, dk, du = (b[0] - a[0]), (b[1] - a[1]), (b[2] - a[2])
        total = dk + du
        return 100.0 * (1 - di / total) if total > 0 else math.nan


# ---- phân tích một lượt ---------------------------------------------------------------------------------------------
def analyze(log, marks):
    nb_io, park_io = marks.get("nb_io"), marks.get("park_io")
    nb_tel = [r for r in log if r["io"] == nb_io and r["dir"] == "rx" and r["type"] == "TelemetryMsg" and r["sid_ok"]]
    out = {}
    if nb_tel:
        offset = min(r["p"] - r["tau"] / 1000.0 for r in nb_tel)      # perf − đồng hồ bo, trễ nhỏ nhất
        out["offset_jitter_ms"] = round(1000 * (statistics.median(r["p"] - r["tau"] / 1000.0 for r in nb_tel) - offset), 2)
        before = [r for r in nb_tel if r["p"] < marks["p_stop"]]
        after = [r for r in nb_tel if r["p"] >= marks["p_stop"]]
        if before:
            last = before[-1]
            out["nb_last_before_stop"] = {"tau": last["tau"], "st": last["st"], "ref": last["ref"]}
        out["nb_after_stop"] = [{"tau": r["tau"], "st": r["st"], "ref": r["ref"],
                                 "dp_ms": round(1000 * (r["p"] - marks["p_stop"]), 1)} for r in after]
        # thời điểm bo xử lý lệnh dừng, ước bằng ánh xạ đồng hồ: τ_stop ≈ (p_stop − offset)·1000
        tau_stop_est = (marks["p_stop"] - offset) * 1000.0
        out["tau_stop_est"] = round(tau_stop_est, 1)
        ramp = [r["tau"] - (100 - r["ref"]) / 0.6 for r in after if 0 < r["ref"] < 100]
        out["tau0_from_nb_ramp"] = round(statistics.median(ramp), 1) if ramp else None
        running = [r for r in nb_tel if r["st"] == "RUNNING"]
        out["tau_last_running"] = running[-1]["tau"] if running else None
        out["ref_last_running"] = running[-1]["ref"] if running else None
    else:
        offset = None
    park = [r for r in log if r["io"] == park_io and r["dir"] == "rx"]
    park_ramp = [r["tau"] - (100 - r["ref"]) / 0.6 for r in park
                 if r["type"] == "TelemetryMsg" and r["sid_ok"] and 0 < r["ref"] < 100]
    out["tau0_from_park_ramp"] = round(statistics.median(park_ramp), 1) if park_ramp else None
    out["park_rx_total"] = len(park)
    out["park_foreign"] = [{"type": r["type"], "sid_is_nb": r["sid"] == marks.get("nb_sid"), "tau": r.get("tau"),
                            "ref": r.get("ref"), "st": r.get("st"),
                            "dp_ms": round(1000 * (r["p"] - marks["p_stop"]), 1)} for r in park if not r["sid_ok"]]
    out["park_before_ack"] = sum(1 for r in park if r["sid_ok"] and r["before_ack"] and r["type"] != "HelloAck")
    if park:
        f = park[0]
        out["park_first_rx"] = {"type": f["type"], "sid_ok": f["sid_ok"], "tau": f.get("tau"), "ref": f.get("ref"),
                                "st": f.get("st"), "dp_ms": round(1000 * (f["p"] - marks["p_stop"]), 1)}
        ft = [r for r in park if r["type"] == "TelemetryMsg" and r["sid_ok"]]
        if ft:
            out["park_first_tel"] = {"tau": ft[0]["tau"], "ref": ft[0]["ref"], "st": ft[0]["st"],
                                     "dp_ms": round(1000 * (ft[0]["p"] - marks["p_stop"]), 1)}
    nt = marks.get("new_tel")
    if nt:
        rows = []
        tau0 = out.get("tau0_from_nb_ramp") or out.get("tau_stop_est")
        by_seq = {r["seq"]: r for r in park if r["type"] == "TelemetryMsg" and r["sid_ok"]}
        for s in nt[0]["samples"]:
            r = by_seq.get(s["seq"])
            row = {"tau": s["tau"], "seq": s["seq"], "st": s["st"], "ref_mm_s": round(s["ref"] * 1000),
                   "v_mm_s": None if s["v"] is None else round(s["v"] * 1000)}
            if r is not None:
                row["dp_stop_ms"] = round(1000 * (r["p"] - marks["p_stop"]), 1)
                if offset is not None:
                    row["latency_ms"] = round(1000 * (r["p"] - r["tau"] / 1000.0 - offset), 1)
            if tau0 is not None:
                row["dtau_ms"] = round(s["tau"] - tau0, 1)
                row["ref_pred_mm_s"] = round(max(0.0, 100 - 0.6 * (s["tau"] - tau0)), 1)
            if out.get("tau_last_running") is not None:
                # khung RUNNING cuối của nonblocking dựng trước khi bo xử lý lệnh dừng: dốc bắt đầu trong (τ_run, τ_run + 10]
                row["dtau_run_ms"] = s["tau"] - out["tau_last_running"]
            rows.append(row)
        out["start_samples"] = rows
    return out


def run_iteration(board, d, cpu, *, keep_full=False, preplan=False):
    LOG.clear()
    CUR.clear()
    marks = CUR
    c0 = cpu.read()
    q0 = board.cpu_seconds()
    p_iter0 = perf()
    with warnings.catch_warnings(record=True) as wlist:
        warnings.simplefilter("always")
        if preplan:
            # Biến thể liều lượng: lập đường TRƯỚC thân nonblocking, nên START đến ngay sau lệnh dừng + d.
            cfg, scenario = make_cfg(), make_scenario()
            session = Session(scenario, cfg)
            t0 = perf()
            marks["plan_ok"] = session.plan_sync().ok
            marks["plan_ms_pre"] = round(1000 * (perf() - t0), 1)
            link = VehicleLink.qemu_board(DriveMode.VEHICLE_IO, T.BoardSource(board))
            session.set_vehicle_link(link)
        try:
            T.on_board(board, lambda io: nonblocking_body(io, marks))
            marks["nb_result"] = "ok"
        except Exception as exc:  # noqa: BLE001
            marks["nb_result"] = repr(exc)[:300]
        marks["p_nb_end"] = perf()
        if d > 0:
            time.sleep(d)
        # ---- parking_run (chép), dừng sau START
        marks["p_park_begin"] = perf()
        if not preplan:
            cfg, scenario = make_cfg(), make_scenario()
            session = Session(scenario, cfg)
            marks["p_session"] = perf()
            ok = session.plan_sync().ok
            marks["p_plan_done"] = perf()
            marks["plan_ok"] = ok
            link = VehicleLink.qemu_board(DriveMode.VEHICLE_IO, T.BoardSource(board))
            session.set_vehicle_link(link)
        else:
            marks["p_plan_done"] = perf()
        if FIX is not None:
            marks["waited_at_rest_s"] = round(FIX(board), 3)        # bản sửa đề xuất (bản sao test đã vá)
            marks["p_rest_done"] = perf()
        marks["p_start_call"] = perf()
        try:
            session.start_run()
            marks["start"] = "ĐẠT"
        except SessionError as exc:
            marks["start"] = "HỎNG: " + str(exc)[:400]
        marks["p_start_ret"] = perf()
        session.close()
        marks["p_closed"] = perf()
        marks["warnings"] = [str(w.message)[:200] for w in wlist]
    c1 = cpu.read()
    q1 = board.cpu_seconds()
    marks["cpu_load_pct"] = round(CpuMeter.load(c0, c1), 1)
    marks["qemu_cores"] = round((q1 - q0) / (perf() - p_iter0), 3) if q0 is not None and q1 is not None else None
    res = {k: v for k, v in marks.items() if not k.startswith("p_") and k not in ("new_tel",)}
    ps = marks["p_stop"] if "p_stop" in marks else None
    if ps is not None:
        res["t_ms"] = {k[2:]: round(1000 * (v - ps), 1) for k, v in marks.items() if k.startswith("p_")}
    res["new_tel"] = marks.get("new_tel")
    if ps is not None:
        res["analysis"] = analyze(LOG, marks)
    if keep_full:
        res["log"] = list(LOG)
    return res


def busy_load(n, seconds):
    code = f"import time\ne=time.perf_counter()+{seconds}\nwhile time.perf_counter()<e: pass\n"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return [subprocess.Popen([sys.executable, "-c", code], creationflags=flags) for _ in range(n)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--delays", default="0,0.05,0.1,0.2,0.4")
    ap.add_argument("--reps", type=int, default=4)
    ap.add_argument("--load", type=int, default=0, help="số tiến trình python vòng lặp bận")
    ap.add_argument("--load-seconds", type=int, default=600)
    ap.add_argument("--full-log-first", action="store_true")
    ap.add_argument("--preplan", action="store_true", help="lập đường trước thân nonblocking (quét khoảng hở)")
    ap.add_argument("--affinity", default="", help="mặt nạ CPU (hex) cho tiến trình này, đặt SAU khi QEMU đã chạy")
    ap.add_argument("--fix", action="store_true", help="gọi wait_board_at_rest (bản vá) ngay trước START")
    args = ap.parse_args()
    if args.fix:
        import importlib.util
        global FIX
        here = os.path.dirname(os.path.abspath(__file__))
        spec = importlib.util.spec_from_file_location("test_firmware_qemu_va",
                                                      os.path.join(here, "patched", "tests", "test_firmware_qemu.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        FIX = mod.wait_board_at_rest
    delays = [float(x) for x in args.delays.split(",")]
    tools = qemu_board.load_tools()
    image = qemu_board.image_path()
    assert not qemu_board.firmware_sources_newer(image), "ảnh cũ hơn mã nguồn: không chạy (không build ở đây)"
    cpu = CpuMeter()
    procs = []
    print(f"EcoQoS tiến trình: {ECOQOS}; python {sys.executable}; tải nhân tạo {args.load}", flush=True)
    t_all = perf()
    try:
        c0 = cpu.read()
        time.sleep(1.0)
        print(f"tải CPU trước khi chạy: {CpuMeter.load(c0, cpu.read()):.1f} %", flush=True)
        if args.load:
            procs = busy_load(args.load, args.load_seconds)
            time.sleep(1.0)
            c0 = cpu.read()
            time.sleep(1.0)
            print(f"tải CPU sau khi bật {args.load} tiến trình bận: {CpuMeter.load(c0, cpu.read()):.1f} %", flush=True)
        with qemu_board.QemuBoard(image, tools) as board, open(args.out, "a", encoding="utf-8") as f:
            print(f"QEMU pid {board.proc.pid}, {board.url}, khởi động {board.starts} lần", flush=True)
            if args.affinity:
                k32 = ctypes.WinDLL("kernel32")
                k32.GetCurrentProcess.restype = ctypes.c_void_p
                k32.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
                ok = k32.SetProcessAffinityMask(k32.GetCurrentProcess(), int(args.affinity, 16))
                print(f"mặt nạ CPU của tiến trình test: {args.affinity} ({'được' if ok else 'KHÔNG được'}); QEMU giữ "
                      f"mặc định", flush=True)
            order = [d for _ in range(args.reps) for d in delays]          # xen kẽ các d
            for i, d in enumerate(order):
                res = run_iteration(board, d, cpu, keep_full=(args.full_log_first and i == 0), preplan=args.preplan)
                res.update(i=i, d=d, load_procs=args.load, python=sys.executable, preplan=args.preplan,
                           affinity=args.affinity, fix=args.fix)
                f.write(json.dumps(res, ensure_ascii=False) + "\n")
                f.flush()
                a = res.get("analysis", {})
                ss = a.get("start_samples") or []
                tm = res.get("t_ms", {})
                plan_ms = tm.get("plan_done", math.nan) - tm.get("park_begin", math.nan)
                park_ms = tm.get("start_ret", math.nan) - tm.get("park_begin", math.nan)
                print(f"#{i:02d} d={d:.2f} START {res.get('start', '?')[:4]} refs={[s['ref_mm_s'] for s in ss]} "
                      f"v={[s['v_mm_s'] for s in ss]} dp_stop={[s.get('dp_stop_ms') for s in ss]} "
                      f"dtau_run={[s.get('dtau_run_ms') for s in ss]} tau0_park={a.get('tau0_from_park_ramp')} "
                      f"tau_run={a.get('tau_last_running')} lat={[s.get('latency_ms') for s in ss]} "
                      f"plan={plan_ms:.0f}ms park→ret={park_ms:.0f}ms "
                      f"foreign={len(a.get('park_foreign', []))} cpu={res.get('cpu_load_pct')}% "
                      f"nb={res.get('nb_result', '?')[:20]} warn={len(res.get('warnings', []))}", flush=True)
                if not board.running():
                    print("QEMU đã thoát; dừng", flush=True)
                    break
    finally:
        for p in procs:
            p.kill()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
    print(f"xong sau {perf() - t_all:.0f} s", flush=True)


if __name__ == "__main__":
    main()
