"""Tóm tắt các tệp jsonl của thi_nghiem.py: bảng theo d, khung lạ trên kết nối mới, mốc thời gian."""
import json
import statistics
import sys
from collections import defaultdict


def load(paths):
    rows = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                r["_file"] = p.split("/")[-1].split("\\")[-1]
                rows.append(r)
    return rows


def main():
    rows = load(sys.argv[1:])
    groups = defaultdict(list)
    for r in rows:
        groups[(r["_file"], r.get("preplan", False), r.get("load_procs", 0), r["d"])].append(r)
    print("tệp | preplan | tải | d (s) | n | START hỏng | Δτ khung START cuối từ khung RUNNING cuối (ms) | ref khung cuối "
          "(mm/s) | lập đường (ms) | p_stop→HELLO (ms) | tải CPU %")
    for key in sorted(groups):
        g = groups[key]
        fails = sum(1 for r in g if r.get("start", "").startswith("HỎNG"))
        dl, refs, plans, hello, cpu = [], [], [], [], []
        for r in g:
            ss = (r.get("analysis") or {}).get("start_samples") or []
            if ss:
                dl.append(ss[-1].get("dtau_run_ms"))
                refs.append(ss[-1]["ref_mm_s"])
            tm = r.get("t_ms", {})
            if "plan_done" in tm and "park_begin" in tm and not r.get("preplan"):
                plans.append(tm["plan_done"] - tm["park_begin"])
            if r.get("plan_ms_pre") is not None:
                plans.append(r["plan_ms_pre"])
            if "connect0" in tm:
                hello.append(tm["connect0"])
            cpu.append(r.get("cpu_load_pct"))
        rng = lambda xs: f"{min(xs)}–{max(xs)}" if xs else "-"  # noqa: E731
        print(f"{key[0]} | {key[1]} | {key[2]} | {key[3]} | {len(g)} | {fails} | {rng(dl)} (trung vị "
              f"{statistics.median(dl) if dl else '-'}) | {rng(refs)} | {rng([round(x) for x in plans])} | "
              f"{rng([round(x) for x in hello])} | {rng(cpu)}")
    print()
    print("Khung lạ (session_id khác) trên kết nối mới, khung trước HELLO_ACK, khung đầu tiên:")
    n_foreign = 0
    for r in rows:
        a = r.get("analysis") or {}
        if a.get("park_foreign") or a.get("park_before_ack"):
            n_foreign += 1
            print(f"  {r['_file']} #{r['i']} d={r['d']}: foreign={a.get('park_foreign')} "
                  f"before_ack={a.get('park_before_ack')} first_rx={a.get('park_first_rx')}")
    print(f"  ({n_foreign} lượt có khung lạ trên {len(rows)} lượt)")
    print()
    print("Lượt START hỏng:")
    for r in rows:
        if r.get("start", "").startswith("HỎNG"):
            a = r.get("analysis") or {}
            ss = a.get("start_samples") or []
            print(f"  {r['_file']} #{r['i']} d={r['d']} preplan={r.get('preplan')}: {r['start'][:160]}")
            print(f"     mẫu: {[(s['tau'], s['st'], s['ref_mm_s'], s['v_mm_s'], s.get('dtau_run_ms'), s.get('latency_ms')) for s in ss]}"
                  f" τ0(dốc, kết nối mới)={a.get('tau0_from_park_ramp')} τ_RUNNING_cuối={a.get('tau_last_running')}")


if __name__ == "__main__":
    main()
