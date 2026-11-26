"""Thử bàn ESC + servo qua firmware AutoPark (env esp32s3_16mb_pwm), chạy trên Pi nối USB với ESP32.

Thử khi bánh xe nhấc khỏi sàn. Ctrl+C: gửi DISARM rồi thoát.

    python3 thu_ban_pwm.py --port /dev/ttyACM0 ket_noi        # HELLO, xem trạng thái, không ARM
    python3 thu_ban_pwm.py servo                              # lái trái / giữa / phải, ga 0
    python3 thu_ban_pwm.py tien --toc-do 0.05 --giay 2        # bánh quay tiến 2 s rồi dừng
    python3 thu_ban_pwm.py lui  --toc-do 0.05 --giay 2
    python3 thu_ban_pwm.py mat_lenh                           # tiến 1,5 s rồi NGỪNG gửi: bo phải tự về trung tính

Lệnh lái gửi 50 lần/giây, mỗi lệnh có hạn 200 ms: script dừng gửi (treo, mất USB) thì bo tự về trung tính. Cần
`protocol.py` (autopark/transport/protocol.py) đặt cùng thư mục, hoặc chạy trong repo.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import random
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import protocol as P
except ImportError:
    from autopark.transport import protocol as P

import serial

VALIDITY_MS = 200
PERIOD_S = 0.02


class Link:
    def __init__(self, port: str):
        self.ser = serial.Serial(port, 115200, timeout=0.005, write_timeout=0.1)
        self.parser = P.FrameParser(accept_types=P.DEVICE_TO_HOST)
        self.session = random.randint(1, 0xFFFFFFFF)
        self.seq = 0
        self.tele: P.TelemetryMsg | None = None
        self.last_print = 0.0

    def _next(self) -> int:
        self.seq = (self.seq + 1) & 0xFFFF or 1
        return self.seq

    def send(self, msg) -> None:
        self.ser.write(P.encode_frame(msg))

    def pump(self, seconds: float = 0.0) -> list:
        out, end = [], time.monotonic() + seconds
        while True:
            data = self.ser.read(self.ser.in_waiting or 1)
            for m in self.parser.feed(data):
                out.append(m)
                if isinstance(m, P.TelemetryMsg):
                    self.tele = m
                elif isinstance(m, P.Ack) and m.result != P.Result.OK:
                    print(f"  ! bo từ chối {P.MsgType(m.acked_type).name}: {P.Result(m.result).name}")
                elif isinstance(m, P.FaultMsg):
                    print(f"  ! LỖI CHỐT: {P.Fault(m.fault).name} (detail={m.detail})")
            if time.monotonic() >= end:
                return out

    def hello(self) -> P.HelloAck:
        self.ser.reset_input_buffer()
        seq = self._next()
        for _ in range(20):
            self.send(P.Hello(self.session, seq, 50, int(time.monotonic() * 1000) & 0xFFFFFFFF))
            for m in self.pump(0.1):
                if isinstance(m, P.HelloAck) and m.hello_sequence == seq:
                    return m
            seq = self._next()
        raise SystemExit("Không nhận được HELLO_ACK: kiểm cổng USB và firmware.")

    def request(self, action: P.Action) -> P.Ack | None:
        seq = self._next()
        self.send(P.Request(self.session, seq, int(action)))
        for _ in range(10):
            for m in self.pump(0.05):
                if isinstance(m, P.Ack) and m.acked_sequence == seq:
                    return m
        return None

    def command(self, speed_mps: float, steer_rad: float, enable: bool = True) -> None:
        flags = P.COMMAND_FLAG_ENABLE if enable else 0
        self.send(P.Command(self.session, self._next(), VALIDITY_MS, flags,
                            int(round(speed_mps * 1000)), int(round(steer_rad * 1000))))

    def show(self, label: str = "", force: bool = False) -> None:
        t = self.tele
        now = time.monotonic()
        if t is None or (not force and now - self.last_print < 0.2):
            return
        self.last_print = now
        esc_us = 1500 + t.effort_permille * 500 // 1000           # theo kEscSpanUs, kServoUsPerRad của main.cpp
        servo_us = min(1800, max(1200, 1500 + t.steer_ref_mrad))  # env esp32s3_16mb_pwm: 1200–1800 µs
        print(f"  {label:<10} {P.State(t.state).name:<9} lỗi={P.Fault(t.fault).name:<5} "
              f"dừng={P.StopReason(t.stop_reason).name:<15} v_ref={t.speed_ref_mm_s:>4} mm/s "
              f"effort={t.effort_permille:>4}‰ ESC≈{esc_us} µs | lái_ref={t.steer_ref_mrad:>5} mrad servo≈{servo_us} µs")


def hold(link: Link, label: str, speed: float, steer: float, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        t0 = time.monotonic()
        link.command(speed, steer)
        link.pump(0.0)
        link.show(label)
        time.sleep(max(0.0, PERIOD_S - (time.monotonic() - t0)))


def neutral(link: Link, seconds: float, label: str = "trung tính") -> None:
    hold(link, label, 0.0, 0.0, seconds)


def arm(link: Link) -> None:
    ack = link.request(P.Action.ARM)
    for _ in range(30):                       # bo vừa khởi động còn ở BOOT (giữ 1 s): chờ rồi thử lại
        if ack is None or ack.result != P.Result.NOT_READY:
            break
        link.pump(0.1)
        ack = link.request(P.Action.ARM)
    if ack is None or ack.result != P.Result.OK:
        if ack is not None and ack.result == P.Result.FAULT_ACTIVE:
            link.request(P.Action.CLEAR_FAULT)
            ack = link.request(P.Action.ARM)
        if ack is None or ack.result != P.Result.OK:
            raise SystemExit(f"ARM thất bại: {None if ack is None else P.Result(ack.result).name}")
    print("  ARMED")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("buoc", choices=["ket_noi", "servo", "tien", "lui", "mat_lenh"])
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--toc-do", type=float, default=0.05, help="m/s, tối đa 0.3 (bo kẹp ga ở 250‰ = ±125 µs)")
    ap.add_argument("--giay", type=float, default=2.0)
    ap.add_argument("--goc", type=float, default=0.25, help="rad góc lái khi thử servo (1 mrad ≈ 1 µs)")
    a = ap.parse_args()
    if not 0 < a.toc_do <= 0.3:
        ap.error("--toc-do phải trong (0, 0.3]")

    link = Link(a.port)
    ha = link.hello()
    print(f"HELLO_ACK: fw {ha.fw_major}.{ha.fw_minor} boot_id={ha.boot_id:08x} "
          f"reset={P.ResetReason(ha.reset_reason).name} state={P.State(ha.state).name} "
          f"max_validity={ha.limits.max_validity_ms} ms link_timeout={ha.limits.link_timeout_ms} ms")
    link.pump(0.3)
    link.show("hiện tại", force=True)
    if a.buoc == "ket_noi":
        return 0

    try:
        arm(link)
        neutral(link, 1.0)
        if a.buoc == "servo":
            for label, g in (("trái", a.goc), ("giữa", 0.0), ("phải", -a.goc), ("giữa", 0.0)):
                hold(link, label, 0.0, g, 2.0)
        elif a.buoc in ("tien", "lui"):
            v = a.toc_do if a.buoc == "tien" else -a.toc_do
            hold(link, a.buoc, v, 0.0, a.giay)
            neutral(link, 1.5, "dừng")
        elif a.buoc == "mat_lenh":
            hold(link, "tiến", a.toc_do, 0.0, 1.5)
            print("  NGỪNG GỬI LỆNH. Bo phải về trung tính trong ≈ 200 ms:")
            t_stop = time.monotonic()
            while time.monotonic() - t_stop < 1.0:
                link.pump(0.02)
                if link.tele is not None:
                    link.show(f"+{int((time.monotonic() - t_stop) * 1000)} ms", force=True)
    except KeyboardInterrupt:
        print("\n  Ctrl+C")
    finally:
        try:
            link.command(0.0, 0.0, enable=False)
            link.request(P.Action.DISARM)
            link.pump(0.2)
            link.show("kết thúc", force=True)
        finally:
            link.ser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
