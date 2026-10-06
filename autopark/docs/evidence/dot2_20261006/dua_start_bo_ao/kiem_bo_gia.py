"""Bo giả (FirmwareModel) có tái hiện "phiên mới thấy speed_ref còn dốc" không: nếu có, test đơn vị của bản vá có nghĩa."""
import os
import sys

REPO = r"D:/xetulai/autopark/autopark"
sys.path.insert(0, REPO)
sys.path.insert(0, REPO + "/tests")
os.chdir(REPO)
import test_firmware_qemu as T  # noqa: E402  (bản GỐC, chưa vá)

board = T.LoopbackBoard()
io = T.fresh_io(board)
io.arm()
for _ in range(50):
    io.send(0.1, 0.0, enable=True, validity_s=0.15)
    io.poll()
print("trước khi dừng: speed_ref", io.latest().speed_ref_mps)
io.stop()
io.disarm()
io.close()
io = T.fresh_io(board)          # phiên mới NGAY sau đó, không chờ
refs = [io.latest().speed_ref_mps]
for _ in range(6):
    refs += [t.speed_ref_mps for t in io.poll()]
print("phiên mới ngay sau đó, speed_ref các khung:", refs)
io.close()
