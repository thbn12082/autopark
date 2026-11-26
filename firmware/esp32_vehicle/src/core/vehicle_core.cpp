#include "vehicle_core.h"

#include <cstring>

namespace ap {
namespace {

inline uint32_t elapsed_ms(uint32_t now, uint32_t then) { return now - then; }  // quay vòng uint32 đúng nghĩa

inline int64_t sign64(int64_t x) { return (x > 0) - (x < 0); }
inline int64_t abs64(int64_t x) { return x < 0 ? -x : x; }
inline int64_t min64(int64_t a, int64_t b) { return a < b ? a : b; }
inline int64_t clamp64(int64_t x, int64_t lo, int64_t hi) { return x < lo ? lo : (x > hi ? hi : x); }
inline int16_t sat16(int64_t x) { return static_cast<int16_t>(clamp64(x, -32768, 32767)); }
inline uint16_t satu16(int64_t x) { return static_cast<uint16_t>(clamp64(x, 0, 65535)); }

// Một bước dốc (giống FirmwareModel._ramp): về 0 hoặc đổi chiều thì giảm độ lớn tới 0, không vượt qua 0.
int64_t ramp(int64_t ref, int64_t target, int64_t up, int64_t down) {
  if (ref != 0 && sign64(target) != sign64(ref)) {
    int64_t magnitude = abs64(ref) - down;
    if (magnitude < 0) {
      magnitude = 0;
    }
    return sign64(ref) * magnitude;
  }
  if (abs64(target) >= abs64(ref)) {
    return ref + sign64(target) * min64(abs64(target) - abs64(ref), up);
  }
  return ref - sign64(ref) * min64(abs64(ref) - abs64(target), down);
}

}  // namespace

void VehicleCore::begin(const Config& config, uint32_t now_ms, uint32_t boot_id, ResetReason reset_reason) {
  *this = VehicleCore();
  cfg_ = config;
  boot_ms_ = now_ms;
  boot_id_ = boot_id;
  reset_reason_ = static_cast<uint8_t>(reset_reason);
  last_rx_ms_ = now_ms;
  cmd_rx_ms_ = now_ms;
  zero_since_valid_ = true;
  zero_since_ms_ = now_ms;
  telemetry_period_ms_ = cfg_.default_telemetry_period_ms;
}

void VehicleCore::tx_consume(size_t n) {
  if (n >= tx_len_) {
    tx_len_ = 0;
    return;
  }
  std::memmove(tx_, tx_ + n, tx_len_ - n);
  tx_len_ -= n;
}

void VehicleCore::queue(const uint8_t* raw, size_t len) {
  uint8_t frame[kMaxFrame];
  const size_t n = frame_from_raw(raw, len, frame, sizeof(frame));
  tx_seq_ = static_cast<uint16_t>(tx_seq_ + 1);  // tăng cả khi khung bị bỏ: laptop thấy khoảng hở số thứ tự
  size_t capacity = kTxBufferSize;
  if (cfg_.tx_capacity > 0 && static_cast<size_t>(cfg_.tx_capacity) < capacity) {
    capacity = static_cast<size_t>(cfg_.tx_capacity);
  }
  if (n == 0 || tx_len_ + n > capacity) {
    ++tx_overflow_;
    return;
  }
  std::memcpy(tx_ + tx_len_, frame, n);
  tx_len_ += n;
}

void VehicleCore::ack(MsgType type, uint32_t session_id, uint16_t sequence, Result result) {
  if (result != Result::Ok) {
    ++rejects_;
  }
  Ack a{};
  a.session_id = session_id;
  a.sequence = tx_seq_;
  a.acked_type = static_cast<uint8_t>(type);
  a.acked_sequence = sequence;
  a.result = static_cast<uint8_t>(result);
  a.state = static_cast<uint8_t>(state_);
  a.fault = static_cast<uint8_t>(fault_);
  uint8_t raw[kMaxRaw];
  queue(raw, encode(a, raw));
}

void VehicleCore::clear_cmd() {
  cmd_active_ = false;
  cmd_speed_mm_s_ = 0;
  cmd_steer_mrad_ = 0;
}

void VehicleCore::disarm(StopReason reason) {
  state_ = State::Disarmed;
  stop_reason_ = reason;
  clear_cmd();
}

void VehicleCore::latch_fault(Fault code, int64_t detail, uint32_t now) {
  if (state_ == State::Fault) {
    return;  // giữ lỗi đầu tiên (nguyên nhân gốc)
  }
  state_ = State::Fault;
  fault_ = code;
  stop_reason_ = StopReason::Fault;
  clear_cmd();
  speed_ref_um_ = 0;
  effort_permille_ = 0;
  integ_ = 0;
  if (session_id_ != 0) {
    FaultMsg f{};
    f.session_id = session_id_;
    f.sequence = tx_seq_;
    f.fault = static_cast<uint8_t>(code);
    f.state = static_cast<uint8_t>(State::Fault);
    f.time_ms = now;
    f.detail = satu16(detail);
    uint8_t raw[kMaxRaw];
    queue(raw, encode(f, raw));
  }
}

// ---- nhận ----------------------------------------------------------------------------------------------------------
void VehicleCore::receive(const uint8_t* data, size_t len, uint32_t now_ms) {
  HostMessage msg{};
  for (size_t i = 0; i < len; ++i) {
    if (parser_.feed(data[i], &msg)) {
      handle(msg, now_ms);
    }
  }
}

Result VehicleCore::check_link(uint32_t session_id, uint16_t sequence) const {
  if (session_id_ == 0) {
    return Result::NoSession;
  }
  if (session_id != session_id_) {
    return Result::WrongSession;
  }
  const uint16_t diff = static_cast<uint16_t>(sequence - last_rx_seq_);
  if (diff == 0) {
    return Result::Duplicate;
  }
  if (diff >= 0x8000u) {
    return Result::OutOfOrder;
  }
  return Result::Ok;
}

void VehicleCore::handle(const HostMessage& msg, uint32_t now) {
  if (msg.type == MsgType::Hello) {
    handle_hello(msg.hello, now);
    return;
  }
  const bool is_request = msg.type == MsgType::Request;
  const uint32_t session_id = is_request ? msg.request.session_id : msg.command.session_id;
  const uint16_t sequence = is_request ? msg.request.sequence : msg.command.sequence;
  const Result result = check_link(session_id, sequence);
  if (result != Result::Ok) {
    ack(msg.type, session_id, sequence, result);
    return;
  }
  last_rx_seq_ = sequence;
  last_rx_ms_ = now;
  if (is_request) {
    handle_request(msg.request);
  } else {
    handle_command(msg.command, now);
  }
}

void VehicleCore::handle_hello(const Hello& msg, uint32_t now) {
  if (msg.session_id == 0) {
    ack(MsgType::Hello, msg.session_id, msg.sequence, Result::BadField);
    return;
  }
  session_id_ = msg.session_id;
  last_rx_seq_ = msg.sequence;
  last_rx_ms_ = now;
  int64_t period = msg.telemetry_period_ms != 0 ? msg.telemetry_period_ms : cfg_.default_telemetry_period_ms;
  telemetry_period_ms_ = static_cast<int32_t>(clamp64(period, cfg_.min_telemetry_period_ms,
                                                      cfg_.max_telemetry_period_ms));
  if (state_ == State::Armed || state_ == State::Running) {
    disarm(StopReason::NewSession);
  }
  has_cmd_ = false;
  last_cmd_seq_ = 0;
  telemetry_sent_ = false;

  HelloAck a{};
  a.session_id = session_id_;
  a.sequence = tx_seq_;
  a.hello_sequence = msg.sequence;
  a.fw_major = cfg_.fw_major;
  a.fw_minor = cfg_.fw_minor;
  a.boot_id = boot_id_;
  a.reset_reason = reset_reason_;
  a.state = static_cast<uint8_t>(state_);
  a.telemetry_period_ms = static_cast<uint16_t>(telemetry_period_ms_);
  a.limits.max_speed_mm_s = static_cast<uint16_t>(cfg_.max_speed_mm_s);
  a.limits.max_steer_mrad = static_cast<uint16_t>(cfg_.max_steer_mrad);
  a.limits.max_steer_rate_mrad_s = static_cast<uint16_t>(cfg_.max_steer_rate_mrad_s);
  a.limits.max_accel_mm_s2 = static_cast<uint16_t>(cfg_.max_accel_mm_s2);
  a.limits.max_decel_mm_s2 = static_cast<uint16_t>(cfg_.max_decel_mm_s2);
  a.limits.stop_decel_mm_s2 = static_cast<uint16_t>(cfg_.stop_decel_mm_s2);
  a.limits.max_validity_ms = static_cast<uint16_t>(cfg_.max_validity_ms);
  a.limits.link_timeout_ms = static_cast<uint16_t>(cfg_.link_timeout_ms);
  uint8_t raw[kMaxRaw];
  queue(raw, encode(a, raw));
}

void VehicleCore::handle_request(const Request& msg) {
  Result result = Result::Ok;
  switch (msg.action) {
    case static_cast<uint8_t>(Action::Arm):
      if (state_ == State::Boot) {
        result = Result::NotReady;
      } else if (state_ == State::Fault) {
        result = Result::FaultActive;
      } else if (inputs_.estop) {
        result = Result::EstopActive;
      } else if (state_ == State::Disarmed) {
        state_ = State::Armed;
        clear_cmd();
      }
      break;
    case static_cast<uint8_t>(Action::Disarm):
      if (state_ == State::Armed || state_ == State::Running) {
        disarm(StopReason::HostDisarm);
      }
      break;
    case static_cast<uint8_t>(Action::ClearFault):
      if (state_ != State::Fault) {
        result = Result::Ok;
      } else if (inputs_.estop) {
        result = Result::EstopActive;
      } else if (fault_ == Fault::SupplyLow && cfg_.min_supply_mv != 0 &&
                 (!inputs_.supply_valid || inputs_.supply_mv < cfg_.min_supply_mv)) {
        result = Result::FaultActive;
      } else {
        state_ = boot_done_ ? State::Disarmed : State::Boot;
        fault_ = Fault::None;
      }
      break;
    case static_cast<uint8_t>(Action::Ping):
      break;
    default:
      result = Result::BadField;
      break;
  }
  ack(MsgType::Request, msg.session_id, msg.sequence, result);
}

void VehicleCore::handle_command(const Command& msg, uint32_t now) {
  Result result = Result::Ok;
  if ((msg.flags & static_cast<uint8_t>(~kCommandFlagEnable)) != 0 || msg.validity_ms == 0) {
    result = Result::BadField;
  } else if (state_ == State::Boot) {
    result = Result::NotReady;
  } else if (state_ == State::Fault) {
    result = Result::FaultActive;
  } else if (state_ == State::Disarmed) {
    result = Result::BadState;
  } else {
    last_cmd_seq_ = msg.sequence;
    cmd_rx_ms_ = now;
    has_cmd_ = true;
    if ((msg.flags & kCommandFlagEnable) != 0) {
      cmd_active_ = true;
      cmd_speed_mm_s_ = msg.speed_mm_s;
      cmd_steer_mrad_ = msg.steer_mrad;
      cmd_validity_ms_ = msg.validity_ms < cfg_.max_validity_ms ? msg.validity_ms : cfg_.max_validity_ms;
      state_ = State::Running;
    } else {
      if (state_ == State::Running) {
        stop_reason_ = StopReason::EnableCleared;
      }
      state_ = State::Armed;
      clear_cmd();
    }
    return;  // lệnh được nhận: không ACK (telemetry báo last_cmd_seq)
  }
  ack(MsgType::Command, msg.session_id, msg.sequence, result);
}

// ---- chu kỳ điều khiển ---------------------------------------------------------------------------------------------
Outputs VehicleCore::step(uint32_t now_ms, const Inputs& in) {
  const uint32_t now = now_ms;
  const uint32_t gap = ticked_ ? elapsed_ms(now, last_tick_ms_) : 0u;
  const uint32_t max_gap = static_cast<uint32_t>(cfg_.max_tick_gap_ms);
  const int32_t dt = static_cast<int32_t>(gap > max_gap ? max_gap : gap);
  ticked_ = true;
  last_tick_ms_ = now;
  inputs_ = in;

  if (gap > max_gap) {
    latch_fault(Fault::LoopOverrun, gap, now);
  }
  if (in.estop) {
    latch_fault(Fault::Estop, 0, now);
  }
  if (cfg_.min_supply_mv != 0 && in.supply_valid && in.supply_mv < cfg_.min_supply_mv) {
    latch_fault(Fault::SupplyLow, in.supply_mv, now);
  }
  if (cfg_.require_speed_feedback && state_ == State::Running && !in.speed_valid) {
    latch_fault(Fault::FeedbackLost, 0, now);
  }

  if (!boot_done_ && elapsed_ms(now, boot_ms_) >= static_cast<uint32_t>(cfg_.boot_hold_ms)) {
    boot_done_ = true;
  }
  if (state_ == State::Boot && boot_done_) {
    state_ = State::Disarmed;
  }
  if ((state_ == State::Armed || state_ == State::Running) &&
      elapsed_ms(now, last_rx_ms_) >= static_cast<uint32_t>(cfg_.link_timeout_ms)) {
    disarm(StopReason::LinkTimeout);
  }
  if (state_ == State::Running && elapsed_ms(now, cmd_rx_ms_) >= static_cast<uint32_t>(cmd_validity_ms_)) {
    state_ = State::Armed;
    stop_reason_ = StopReason::CommandTimeout;
    clear_cmd();
  }

  update_references(dt, now);
  update_speed_loop(dt);
  check_stall(now);
  const uint32_t period = static_cast<uint32_t>(telemetry_period_ms_);
  if (session_id_ != 0 && (!telemetry_sent_ || elapsed_ms(now, last_telemetry_ms_) >= period)) {
    send_telemetry(now);
    // Lịch theo hạn trước, không theo now (giống FirmwareModel.step): chu kỳ trung bình = giá trị trong HELLO_ACK
    // kể cả khi nó không là bội của chu kỳ điều khiển; tụt quá một chu kỳ thì bắt nhịp lại, không gửi dồn.
    if (!telemetry_sent_) {
      last_telemetry_ms_ = now;
    } else {
      last_telemetry_ms_ += period;  // uint32: quay vòng đúng như `& U32` phía Python
      if (elapsed_ms(now, last_telemetry_ms_) >= period) {
        last_telemetry_ms_ = now;
      }
    }
    telemetry_sent_ = true;
  }
  return outputs();
}

bool VehicleCore::reverse_gate_open(uint32_t now) const {
  if (!zero_since_valid_ ||
      elapsed_ms(now, zero_since_ms_) < static_cast<uint32_t>(cfg_.direction_change_hold_ms)) {
    return false;
  }
  return !inputs_.speed_valid || abs64(inputs_.speed_mm_s) <= cfg_.standstill_mm_s;
}

void VehicleCore::update_references(int32_t dt, uint32_t now) {
  if (state_ == State::Fault) {
    speed_ref_um_ = 0;
  } else {
    int64_t target = 0;
    int64_t decel = cfg_.stop_decel_mm_s2;
    if (state_ == State::Running) {
      target = clamp64(cmd_speed_mm_s_, -cfg_.max_speed_mm_s, cfg_.max_speed_mm_s) * 1000;
      decel = cfg_.max_decel_mm_s2;
    }
    if (speed_ref_um_ == 0 && target != 0 && last_dir_ != 0 && sign64(target) != last_dir_ &&
        !reverse_gate_open(now)) {
      target = 0;  // đổi chiều: đứng ở 0 đủ lâu (và đã dừng nếu đo được) mới đi tiếp
    }
    speed_ref_um_ = ramp(speed_ref_um_, target, static_cast<int64_t>(cfg_.max_accel_mm_s2) * dt, decel * dt);
  }
  if (speed_ref_um_ == 0) {
    if (!zero_since_valid_) {
      zero_since_valid_ = true;
      zero_since_ms_ = now;
    }
  } else {
    zero_since_valid_ = false;
    last_dir_ = static_cast<int32_t>(sign64(speed_ref_um_));
  }

  const int64_t step = static_cast<int64_t>(cfg_.max_steer_rate_mrad_s) * dt;
  int64_t target = 0;
  if (state_ == State::Running) {
    target = clamp64(cmd_steer_mrad_, -cfg_.max_steer_mrad, cfg_.max_steer_mrad) * 1000;
  } else if (state_ != State::Fault && speed_ref_um_ == 0) {
    target = 0;  // đã về 0 thì mới trả lái về giữa; đang giảm tốc thì giữ góc
  } else {
    return;
  }
  steer_ref_urad_ += clamp64(target - steer_ref_urad_, -step, step);
}

void VehicleCore::update_speed_loop(int32_t dt) {
  const int64_t ref = speed_ref_um_;
  loop_closed_ = false;
  if (state_ == State::Fault || ref == 0) {
    effort_permille_ = 0;
    integ_ = 0;
    return;
  }
  const int64_t ff = sign64(ref) * (cfg_.deadzone_comp_permille +
                                    static_cast<int64_t>(cfg_.ff_permille_per_mps) * abs64(ref) / 1000000);
  const int64_t cap = cfg_.max_effort_permille;  // trần |effort| cho cả mạch hở lẫn vòng kín
  if (!inputs_.speed_valid) {
    integ_ = 0;
    effort_permille_ = static_cast<int32_t>(clamp64(ff, -cap, cap));
    return;
  }
  loop_closed_ = true;
  const int64_t error_um = ref - static_cast<int64_t>(sat16(inputs_.speed_mm_s)) * 1000;
  int64_t u = ff + static_cast<int64_t>(cfg_.kp_permille_per_mps) * error_um / 1000000 + integ_ / 1000000000;
  bool sat_hi = u > cap;  // chống bão hòa tích phân theo đúng trần đang dùng
  bool sat_lo = u < -cap;
  u = clamp64(u, -cap, cap);
  if (ref > 0 && u < 0) {
    u = 0;
    sat_lo = true;  // không đẩy ngược chiều (phanh/lùi của ESC là CHƯA CHỐT)
  } else if (ref < 0 && u > 0) {
    u = 0;
    sat_hi = true;
  }
  if (!((sat_hi && error_um > 0) || (sat_lo && error_um < 0))) {
    const int64_t limit = static_cast<int64_t>(cfg_.integ_limit_permille) * 1000000000LL;
    integ_ = clamp64(integ_ + static_cast<int64_t>(cfg_.ki_permille_per_m) * error_um * dt, -limit, limit);
  }
  effort_permille_ = static_cast<int32_t>(u);
}

// Kiểm hợp lý vòng kín (giống FirmwareModel._check_stall): |effort| >= stall_effort_permille mà số đo không đi theo
// chiều mục tiêu (encoder kẹt 0 với cờ hợp lệ, encoder đảo dấu, bánh kẹt) liên tục >= stall_timeout_ms -> FAULT Stall.
// Chạy mạch hở (không có phản hồi) thì không kiểm được; khi đó chỉ còn trần effort.
void VehicleCore::check_stall(uint32_t now) {
  const bool stalled = cfg_.stall_timeout_ms > 0 && loop_closed_ &&
                       abs64(effort_permille_) >= cfg_.stall_effort_permille &&
                       abs64(speed_ref_um_) > static_cast<int64_t>(cfg_.standstill_mm_s) * 1000 &&
                       sign64(speed_ref_um_) * sat16(inputs_.speed_mm_s) <= cfg_.standstill_mm_s;  // kẹt 0 hoặc đảo dấu
  if (!stalled) {
    stall_active_ = false;
    return;
  }
  if (!stall_active_) {
    stall_active_ = true;
    stall_since_ms_ = now;
    return;
  }
  if (elapsed_ms(now, stall_since_ms_) >= static_cast<uint32_t>(cfg_.stall_timeout_ms)) {
    stall_active_ = false;
    latch_fault(Fault::Stall, abs64(effort_permille_), now);
  }
}

void VehicleCore::send_telemetry(uint32_t now) {
  const Inputs& i = inputs_;
  Telemetry t{};
  t.session_id = session_id_;
  t.sequence = tx_seq_;
  t.sample_time_ms = now;
  t.state = static_cast<uint8_t>(state_);
  t.fault = static_cast<uint8_t>(fault_);
  t.stop_reason = static_cast<uint8_t>(stop_reason_);
  uint8_t flags = 0;
  if (i.estop) flags |= tflag::kEstopInput;
  if (session_id_ != 0 && elapsed_ms(now, last_rx_ms_) < static_cast<uint32_t>(cfg_.link_timeout_ms)) {
    flags |= tflag::kLinkOk;
  }
  if (cmd_active_) flags |= tflag::kCmdActive;
  if (i.speed_valid) flags |= tflag::kSpeedValid;
  if (i.steer_valid) flags |= tflag::kSteerValid;
  if (i.imu_valid) flags |= tflag::kImuValid;
  if (i.supply_valid) flags |= tflag::kSupplyValid;
  if (loop_closed_) flags |= tflag::kSpeedLoopClosed;
  t.flags = flags;
  t.last_cmd_seq = last_cmd_seq_;
  if (has_cmd_) {
    const uint32_t age = elapsed_ms(now, cmd_rx_ms_);
    t.cmd_age_ms = static_cast<uint16_t>(age < 0xFFFEu ? age : 0xFFFEu);
  } else {
    t.cmd_age_ms = kNoCommandAge;
  }
  t.speed_measured_mm_s = i.speed_valid ? sat16(i.speed_mm_s) : 0;
  t.steer_measured_mrad = i.steer_valid ? sat16(i.steer_mrad) : 0;
  t.speed_ref_mm_s = sat16(speed_ref_mm_s());
  t.steer_ref_mrad = sat16(steer_ref_mrad());
  t.effort_permille = sat16(effort_permille_);
  t.gyro_z_mrad_s = i.imu_valid ? sat16(i.gyro_z_mrad_s) : 0;
  t.accel_x_mm_s2 = i.imu_valid ? sat16(i.accel_x_mm_s2) : 0;
  t.accel_y_mm_s2 = i.imu_valid ? sat16(i.accel_y_mm_s2) : 0;
  const uint8_t mask = static_cast<uint8_t>(i.tof_valid_mask & ((1u << kNumTof) - 1u));
  t.tof_valid_mask = mask;
  for (int k = 0; k < kNumTof; ++k) {
    t.tof_mm[k] = (mask & (1u << k)) != 0 ? satu16(i.tof_mm[k]) : 0;  // không hợp lệ: 0, KHÔNG phải "xa"
  }
  t.supply_mv = i.supply_valid ? satu16(i.supply_mv) : 0;
  t.rx_errors = satu16(parser_.stats().errors());
  t.rejects = satu16(rejects_);
  uint8_t raw[kMaxRaw];
  queue(raw, encode(t, raw));
}

Outputs VehicleCore::outputs() const {
  return Outputs{state_, speed_ref_mm_s(), steer_ref_mrad(), effort_permille_};
}

}  // namespace ap
