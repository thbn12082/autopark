"""Giám sát đường, dữ liệu và lệnh: cho chạy/giới hạn/dừng.

Hiện gói chỉ có `freshness`: giám sát dữ liệu cũ/mất/không hợp lệ cho mọi nguồn trên cùng đồng hồ phiên. Nó chỉ phát
`SafetyEvent`; hành động dừng là của máy trạng thái phiên. Giám sát đường và lệnh chưa có mã trong gói này: việc vô
hiệu đường khi có vật cản mới hiện nằm ở `application/session.py` (MAP_CHANGED) và `fusion/bridge.py`."""
