// Logic firmware không phụ thuộc phần cứng: máy trạng thái, kiểm tra phiên/số thứ tự, watchdog liên lạc, hết hạn
// lệnh, giới hạn và dốc, khóa đổi chiều, vòng tốc độ PI số nguyên có trần effort, kiểm STALL, chốt lỗi, telemetry.
//
// Bản tham chiếu: autopark/transport/firmware_model.py. Hai bên phải cho cùng byte trên cùng kịch bản; kiểm bằng
// test/host/test_main.cpp với test/vectors.json (sinh từ Python). Mọi phép tính là số nguyên: tốc độ trong µm/s,
// góc trong µrad, thời gian ms uint32 có quay vòng; phép chia số có dấu cắt về 0 (đúng như tdiv phía Python).
//
// Thứ tự trong một chu kỳ (phải giữ đúng): receive() các byte đã tới, rồi step(now, inputs).
// CHƯA CHỐT theo bo thực: không có gì về chân GPIO hay độ rộng xung ở đây; xem main.cpp.
#pragma once

#include <cstddef>
#include <cstdint>

#include "protocol.h"

namespace ap {

struct Config {
  int32_t boot_hold_ms = 1000;
  int32_t max_speed_mm_s = 300;
  int32_t max_steer_mrad = 524;
  int32_t max_steer_rate_mrad_s = 1571;
  int32_t max_accel_mm_s2 = 300;
  int32_t max_decel_mm_s2 = 600;
  int32_t stop_decel_mm_s2 = 600;
  int32_t max_validity_ms = 300;
  int32_t link_timeout_ms = 500;
  int32_t default_telemetry_period_ms = 50;
  int32_t min_telemetry_period_ms = 20;
  int32_t max_telemetry_period_ms = 1000;
  int32_t max_tick_gap_ms = 100;
  int32_t direction_change_hold_ms = 300;
  int32_t standstill_mm_s = 10;
  int32_t ff_permille_per_mps = 2000;
  int32_t deadzone_comp_permille = 100;
  int32_t kp_permille_per_mps = 500;
  int32_t ki_permille_per_m = 4000;
  int32_t integ_limit_permille = 300;
  // Trần |effort| độc lập với max_speed_mm_s (kẹp max_speed chỉ áp lên mục tiêu). CHƯA CHỐT, thận trọng.
  int32_t max_effort_permille = 250;
  int32_t stall_effort_permille = 200;   // vòng kín: |effort| >= ngưỡng này mà xe không đi theo chiều mục tiêu ...
  int32_t stall_timeout_ms = 1000;       // ... liên tục ngần này ms -> FAULT Stall (0 = tắt; CHƯA CHỐT)
  int32_t min_supply_mv = 0;
  bool require_speed_feedback = false;
  uint8_t fw_major = 1;
  uint8_t fw_minor = 0;
  int32_t tx_capacity = 512;
};

// Một lần lấy mẫu ngõ vào. *_valid = false: không có số đo dùng được; giá trị đi kèm bị bỏ qua.
struct Inputs {
  bool estop = false;
  bool speed_valid = false;
  int32_t speed_mm_s = 0;
  bool steer_valid = false;
  int32_t steer_mrad = 0;
  bool imu_valid = false;
  int32_t gyro_z_mrad_s = 0;
  int32_t accel_x_mm_s2 = 0;
  int32_t accel_y_mm_s2 = 0;
  uint8_t tof_valid_mask = 0;
  int32_t tof_mm[kNumTof] = {0, 0, 0, 0};
  bool supply_valid = false;
  int32_t supply_mv = 0;
};

struct Outputs {
  State state;
  int32_t speed_ref_mm_s;
  int32_t steer_ref_mrad;
  int32_t effort_permille;   // |effort| <= Config::max_effort_permille (<= 1000); ánh xạ sang xung: CHƯA CHỐT (main.cpp)
};

class VehicleCore {
 public:
  // Phải bằng firmware_model.TX_BUFFER_SIZE: Python từ chối tx_capacity lớn hơn giá trị này để hai bên bỏ cùng khung.
  // min() trong queue() vẫn giữ làm chốt chặn khi Config.tx_capacity <= 0 hoặc vượt giới hạn.
  static constexpr size_t kTxBufferSize = 1024;

  void begin(const Config& config, uint32_t now_ms, uint32_t boot_id, ResetReason reset_reason);
  void receive(const uint8_t* data, size_t len, uint32_t now_ms);
  Outputs step(uint32_t now_ms, const Inputs& inputs);

  const uint8_t* tx_data() const { return tx_; }
  size_t tx_size() const { return tx_len_; }
  void tx_consume(size_t n);
  void tx_clear() { tx_len_ = 0; }

  State state() const { return state_; }
  Fault fault() const { return fault_; }
  StopReason stop_reason() const { return stop_reason_; }
  uint32_t session_id() const { return session_id_; }
  int32_t speed_ref_mm_s() const { return static_cast<int32_t>(speed_ref_um_ / 1000); }
  int32_t steer_ref_mrad() const { return static_cast<int32_t>(steer_ref_urad_ / 1000); }
  int32_t effort_permille() const { return effort_permille_; }
  uint32_t tx_overflow() const { return tx_overflow_; }
  const ParserStats& parser_stats() const { return parser_.stats(); }

 private:
  void handle(const HostMessage& msg, uint32_t now);
  void handle_hello(const Hello& msg, uint32_t now);
  void handle_request(const Request& msg);
  void handle_command(const Command& msg, uint32_t now);
  Result check_link(uint32_t session_id, uint16_t sequence) const;
  void ack(MsgType type, uint32_t session_id, uint16_t sequence, Result result);
  void queue(const uint8_t* raw, size_t len);
  void clear_cmd();
  void disarm(StopReason reason);
  void latch_fault(Fault code, int64_t detail, uint32_t now);
  bool reverse_gate_open(uint32_t now) const;
  void update_references(int32_t dt, uint32_t now);
  void update_speed_loop(int32_t dt);
  void check_stall(uint32_t now);
  void send_telemetry(uint32_t now);
  Outputs outputs() const;

  Config cfg_{};
  uint32_t boot_ms_ = 0;
  uint32_t boot_id_ = 0;
  uint8_t reset_reason_ = 0;
  bool boot_done_ = false;
  State state_ = State::Boot;
  Fault fault_ = Fault::None;
  StopReason stop_reason_ = StopReason::Boot;

  uint32_t session_id_ = 0;
  uint16_t last_rx_seq_ = 0;
  uint32_t last_rx_ms_ = 0;
  int32_t telemetry_period_ms_ = 50;
  bool telemetry_sent_ = false;
  uint32_t last_telemetry_ms_ = 0;
  uint16_t tx_seq_ = 0;
  uint8_t tx_[kTxBufferSize] = {};
  size_t tx_len_ = 0;
  uint32_t tx_overflow_ = 0;
  uint32_t rejects_ = 0;
  FrameParser parser_;

  bool cmd_active_ = false;
  int32_t cmd_speed_mm_s_ = 0;
  int32_t cmd_steer_mrad_ = 0;
  uint32_t cmd_rx_ms_ = 0;
  int32_t cmd_validity_ms_ = 0;
  bool has_cmd_ = false;
  uint16_t last_cmd_seq_ = 0;

  int64_t speed_ref_um_ = 0;
  int64_t steer_ref_urad_ = 0;
  int32_t last_dir_ = 0;
  bool zero_since_valid_ = true;
  uint32_t zero_since_ms_ = 0;
  int64_t integ_ = 0;               // ‰ × 1e9
  int32_t effort_permille_ = 0;
  bool loop_closed_ = false;
  bool stall_active_ = false;       // điều kiện STALL đang đúng liên tục từ stall_since_ms_ (Python: stall_since_ms)
  uint32_t stall_since_ms_ = 0;

  Inputs inputs_{};
  bool ticked_ = false;
  uint32_t last_tick_ms_ = 0;
};

}  // namespace ap
