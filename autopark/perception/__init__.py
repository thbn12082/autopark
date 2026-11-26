"""Nhận thức: huấn luyện và chấm mô hình phân đoạn (offline), suy luận trực tiếp trên camera bàn thử (`live`), hiệu chuẩn
camera thật (`fisheye_calib`, `calib_board`), gán nhãn ảnh sa bàn (`labels`), chiếu nhãn xuống costmap (`costmap`).
Từ 25/09/2026 đầu ra AI vào phiên đỗ xe qua `fusion/camera_ai.py` (ngăn AI camera của `ui.lidar_app --camera-ai`), chỉ
như nguồn vật cản thêm vào, và bị chặn khi chưa có hiệu chuẩn thật; chưa thử với camera đã hiệu chuẩn hay trên xe."""
