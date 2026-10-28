"""Adapter mô phỏng, USB serial, mạng. Tên gói tránh trùng `io` của Python (mục 5.1).

Laptop ↔ ESP32-S3 (giai đoạn 5, docs/PHAN_CUNG_VA_HIEU_CHUAN.md): `protocol` (khung, thông điệp), `firmware_model` (bản
tham chiếu logic firmware), `vehicle_io` (`SimVehicleIO`, `SerialVehicleIO`), `loopback` (cổng giả nối bản tham
chiếu), `vectors` (vector mẫu chung với firmware C++), `socket_port` (`SocketPort`: cổng kiểu pyserial trên TCP cho
URL `socket://`), `qemu_board` (bo ảo: firmware thật của env `esp32s3_qemu` chạy trong QEMU, 30/09/2026),
`qemu_plant` (bo ảo trong phiên đỗ: `QemuPlantVehicleIO` với xe mô phỏng phía laptop, 02/10/2026).
"""
