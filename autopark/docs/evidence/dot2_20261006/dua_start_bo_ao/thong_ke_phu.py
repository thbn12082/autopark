"""Thống kê phụ: khung đầu tiên trên kết nối mới, trễ HELLO→ACK, độ trễ khung START, τ0 so với khung RUNNING cuối."""
import json
import statistics
import sys
from collections import Counter

first, rtt, lat, anchor, mean_v, nb_after = Counter(), [], [], Counter(), [], Counter()
n = 0
for path in sys.argv[1:]:
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            a = r.get("analysis") or {}
            n += 1
            fr = a.get("park_first_rx") or {}
            first[(fr.get("type"), fr.get("sid_ok"))] += 1
            t = r.get("t_ms", {})
            if "connect0" in t and "connect1" in t:
                rtt.append(t["connect1"] - t["connect0"])
            for s in a.get("start_samples") or []:
                if s.get("latency_ms") is not None:
                    lat.append(s["latency_ms"])
            if a.get("tau0_from_park_ramp") is not None and a.get("tau_last_running") is not None:
                anchor[round(a["tau0_from_park_ramp"] - a["tau_last_running"])] += 1
            if r.get("start", "").startswith("HỎNG"):
                ss = a.get("start_samples") or []
                mean_v.append(sum(s["v_mm_s"] for s in ss) / len(ss))
            nb_after[len(a.get("nb_after_stop") or [])] += 1
print("số lượt", n)
print("thông điệp đầu tiên trên kết nối mới (loại, đúng phiên):", dict(first))
print(f"HELLO→HELLO_ACK: trung vị {statistics.median(rtt):.1f} ms, {min(rtt):.1f}–{max(rtt):.1f} ms")
print(f"độ trễ khung START so với ánh xạ trễ nhỏ nhất: {min(lat):.1f}–{max(lat):.1f} ms (n={len(lat)})")
print("τ0 (dốc, tính từ khung của kết nối mới) − τ khung RUNNING cuối của phiên trước, ms → số lượt:", dict(anchor))
print("tốc độ đo trung bình (mm/s) của các lượt START hỏng:", mean_v)
print("số khung telemetry nonblocking nhận sau lệnh dừng (trước khi đóng):", dict(nb_after))
