"""reset_input_buffer() (PurgeComm) có xóa được byte đang chờ của cổng CP210x (COM3) không? 02/10/2026."""
import sys
import time

sys.path.insert(0, r"D:\xetulai\autopark\autopark")
import serial  # noqa: E402

from autopark.lidar.rplidar_protocol import CMD_GET_INFO, CMD_SCAN, CMD_STOP, request  # noqa: E402

s = serial.Serial("COM3", 460800, timeout=0.05)
s.write(request(CMD_STOP))
time.sleep(0.05)
print("sau STOP, in_waiting:", s.in_waiting)
s.read(s.in_waiting or 1)
# 1) khi máy không gửi gì: GET_INFO 3 lần, không đọc; xóa; xem còn bao nhiêu
for _ in range(3):
    s.write(request(CMD_GET_INFO))
    time.sleep(0.05)
print("3 x GET_INFO chưa đọc, in_waiting:", s.in_waiting)
s.reset_input_buffer()
print("ngay sau reset_input_buffer:", s.in_waiting)
time.sleep(0.05)
print("50 ms sau:", s.in_waiting)
left = s.read(s.in_waiting) if s.in_waiting else b""
print("đọc ra:", left[:30].hex())
# 2) khi đang quét
s.write(request(CMD_SCAN))
time.sleep(3.0)
print("quét 3 s, in_waiting:", s.in_waiting)
s.reset_input_buffer()
print("ngay sau reset_input_buffer:", s.in_waiting)
s.write(request(CMD_STOP))
time.sleep(0.05)
s.reset_input_buffer()
print("STOP + 50 ms + reset:", s.in_waiting)
time.sleep(0.2)
print("200 ms sau:", s.in_waiting)
s.read(s.in_waiting or 1)
s.close()
