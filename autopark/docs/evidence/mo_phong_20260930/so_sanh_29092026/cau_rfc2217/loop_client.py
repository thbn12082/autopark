"""Non-blocking control loop like the app: SerialVehicleIO over a pyserial URL, 20 Hz send + poll(block=False)."""
import sys, time
sys.path.insert(0, r"D:\xetulai\autopark\autopark")
import serial
from autopark.transport.vehicle_io import SerialVehicleIO

url, secs = sys.argv[1], float(sys.argv[2])
t0 = time.time()
while True:
    try:
        kw = {} if url.startswith("rfc2217://") else {"write_timeout": 0.05}  # pyserial 3.5 rfc2217: write_timeout unsupported
        port = serial.serial_for_url(url, timeout=0.01, **kw)
        break
    except Exception as e:  # noqa: BLE001
        if time.time() - t0 > 30:
            raise
        time.sleep(0.3)
io = SerialVehicleIO(port)
for attempt in range(8):
    try:
        info = io.connect(timeout_s=1.5)
        break
    except Exception as e:  # noqa: BLE001
        print("connect attempt", attempt, "failed:", str(e)[:60])
else:
    raise SystemExit("no HELLO_ACK")
print("connected:", info.describe() if hasattr(info, "describe") else info)
io.arm()
print("armed")
n_tel, sends, send_err = 0, 0, 0
t_end = time.time() + secs
next_send = time.time()
while time.time() < t_end:
    now = time.time()
    if now >= next_send:
        next_send += 0.05
        try:
            io.send(0.1, 0.0)
            sends += 1
        except Exception as e:  # noqa: BLE001
            send_err += 1
    n_tel += len(io.poll(block=False))
    io.check()
    time.sleep(0.002)
ev = io.events()
codes = {}
for e in ev:
    codes[e.code] = codes.get(e.code, 0) + 1
print(f"url={url} seconds={secs} telemetry={n_tel} (expected ~{int(secs*20)}) sends_ok={sends} send_errors={send_err} events={codes}")
print("in_waiting type check:", type(port).__module__)
io.close()
