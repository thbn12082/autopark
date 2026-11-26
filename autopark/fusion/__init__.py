"""Hợp nhất cảm biến trên bàn thử (kế hoạch mục 7, phần làm được khi chưa có IMU, ToF hoặc ESP32): các lớp bản đồ
`StaticMap`, `LiveLidar`, `CameraSemantic`, `NearField` với trạng thái hợp lệ/cũ, phép hợp nhất ra một `Costmap`
duy nhất, và cầu nối đưa ô bị chặn vào phiên mô phỏng giai đoạn 0 để kích hoạt dừng và lập lại đường."""
