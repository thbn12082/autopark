#include "protocol.h"

#include <cstring>

#include "cobs.h"
#include "crc16.h"

namespace ap {
namespace {

struct Writer {
  uint8_t* start;
  uint8_t* p;
  explicit Writer(uint8_t* out) : start(out), p(out) {}
  void u8(uint8_t v) { *p++ = v; }
  void u16(uint16_t v) {
    *p++ = static_cast<uint8_t>(v & 0xFFu);
    *p++ = static_cast<uint8_t>(v >> 8);
  }
  void u32(uint32_t v) {
    u16(static_cast<uint16_t>(v & 0xFFFFu));
    u16(static_cast<uint16_t>(v >> 16));
  }
  void i16(int16_t v) { u16(static_cast<uint16_t>(v)); }
  void header(MsgType type, uint32_t session_id, uint16_t sequence) {
    u8(kProtocolVersion);
    u8(static_cast<uint8_t>(type));
    u32(session_id);
    u16(sequence);
  }
  size_t size() const { return static_cast<size_t>(p - start); }
};

struct Reader {
  const uint8_t* p;
  uint8_t u8() { return *p++; }
  uint16_t u16() {
    const uint16_t v = static_cast<uint16_t>(p[0] | (p[1] << 8));
    p += 2;
    return v;
  }
  uint32_t u32() {
    const uint32_t lo = u16();
    const uint32_t hi = u16();
    return lo | (hi << 16);
  }
  int16_t i16() { return static_cast<int16_t>(u16()); }
};

}  // namespace

size_t encode(const Hello& m, uint8_t* out) {
  Writer w(out);
  w.header(MsgType::Hello, m.session_id, m.sequence);
  w.u16(m.telemetry_period_ms);
  w.u32(m.host_time_ms);
  return w.size();
}

size_t encode(const Request& m, uint8_t* out) {
  Writer w(out);
  w.header(MsgType::Request, m.session_id, m.sequence);
  w.u8(m.action);
  return w.size();
}

size_t encode(const Command& m, uint8_t* out) {
  Writer w(out);
  w.header(MsgType::Command, m.session_id, m.sequence);
  w.u16(m.validity_ms);
  w.u8(m.flags);
  w.i16(m.speed_mm_s);
  w.i16(m.steer_mrad);
  return w.size();
}

size_t encode(const HelloAck& m, uint8_t* out) {
  Writer w(out);
  w.header(MsgType::HelloAck, m.session_id, m.sequence);
  w.u16(m.hello_sequence);
  w.u8(m.fw_major);
  w.u8(m.fw_minor);
  w.u32(m.boot_id);
  w.u8(m.reset_reason);
  w.u8(m.state);
  w.u16(m.telemetry_period_ms);
  w.u16(m.limits.max_speed_mm_s);
  w.u16(m.limits.max_steer_mrad);
  w.u16(m.limits.max_steer_rate_mrad_s);
  w.u16(m.limits.max_accel_mm_s2);
  w.u16(m.limits.max_decel_mm_s2);
  w.u16(m.limits.stop_decel_mm_s2);
  w.u16(m.limits.max_validity_ms);
  w.u16(m.limits.link_timeout_ms);
  return w.size();
}

size_t encode(const Ack& m, uint8_t* out) {
  Writer w(out);
  w.header(MsgType::Ack, m.session_id, m.sequence);
  w.u8(m.acked_type);
  w.u16(m.acked_sequence);
  w.u8(m.result);
  w.u8(m.state);
  w.u8(m.fault);
  return w.size();
}

size_t encode(const Telemetry& m, uint8_t* out) {
  Writer w(out);
  w.header(MsgType::Telemetry, m.session_id, m.sequence);
  w.u32(m.sample_time_ms);
  w.u8(m.state);
  w.u8(m.fault);
  w.u8(m.stop_reason);
  w.u8(m.flags);
  w.u16(m.last_cmd_seq);
  w.u16(m.cmd_age_ms);
  w.i16(m.speed_measured_mm_s);
  w.i16(m.steer_measured_mrad);
  w.i16(m.speed_ref_mm_s);
  w.i16(m.steer_ref_mrad);
  w.i16(m.effort_permille);
  w.i16(m.gyro_z_mrad_s);
  w.i16(m.accel_x_mm_s2);
  w.i16(m.accel_y_mm_s2);
  w.u8(m.tof_valid_mask);
  for (int k = 0; k < kNumTof; ++k) {
    w.u16(m.tof_mm[k]);
  }
  w.u16(m.supply_mv);
  w.u16(m.rx_errors);
  w.u16(m.rejects);
  return w.size();
}

size_t encode(const FaultMsg& m, uint8_t* out) {
  Writer w(out);
  w.header(MsgType::Fault, m.session_id, m.sequence);
  w.u8(m.fault);
  w.u8(m.state);
  w.u32(m.time_ms);
  w.u16(m.detail);
  return w.size();
}

size_t frame_from_raw(const uint8_t* raw, size_t len, uint8_t* out, size_t cap) {
  if (len > kMaxRaw) {
    return 0;
  }
  uint8_t with_crc[kMaxRaw + kCrcSize];
  std::memcpy(with_crc, raw, len);
  const uint16_t crc = crc16_ccitt_false(raw, len);
  with_crc[len] = static_cast<uint8_t>(crc & 0xFFu);
  with_crc[len + 1] = static_cast<uint8_t>(crc >> 8);
  if (cap < 1) {
    return 0;
  }
  const size_t n = cobs_encode(with_crc, len + kCrcSize, out, cap - 1);  // chừa 1 byte cho 0x00
  if (n == 0) {
    return 0;
  }
  out[n] = 0;
  return n + 1;
}

FrameError decode_host_message(const uint8_t* raw, size_t len, HostMessage* out) {
  if (len < kHeaderSize) {
    return FrameError::Short;
  }
  if (raw[0] != kProtocolVersion) {
    return FrameError::Version;
  }
  size_t expected = 0;
  switch (raw[1]) {
    case static_cast<uint8_t>(MsgType::Hello): expected = kSizeHello; break;
    case static_cast<uint8_t>(MsgType::Request): expected = kSizeRequest; break;
    case static_cast<uint8_t>(MsgType::Command): expected = kSizeCommand; break;
    default: return FrameError::Type;
  }
  if (len != expected) {
    return FrameError::Length;
  }
  Reader r{raw + 2};
  const uint32_t session_id = r.u32();
  const uint16_t sequence = r.u16();
  out->type = static_cast<MsgType>(raw[1]);
  switch (out->type) {
    case MsgType::Hello:
      out->hello.session_id = session_id;
      out->hello.sequence = sequence;
      out->hello.telemetry_period_ms = r.u16();
      out->hello.host_time_ms = r.u32();
      break;
    case MsgType::Request:
      out->request.session_id = session_id;
      out->request.sequence = sequence;
      out->request.action = r.u8();
      break;
    case MsgType::Command:
      out->command.session_id = session_id;
      out->command.sequence = sequence;
      out->command.validity_ms = r.u16();
      out->command.flags = r.u8();
      out->command.speed_mm_s = r.i16();
      out->command.steer_mrad = r.i16();
      break;
    default:
      return FrameError::Type;
  }
  return FrameError::None;
}

void FrameParser::reset() {
  len_ = 0;
  overflow_ = false;
}

bool FrameParser::feed(uint8_t byte, HostMessage* out) {
  if (byte != 0) {
    if (overflow_) {
      return false;                        // bỏ tới dấu phân cách kế tiếp
    }
    if (len_ >= kMaxEncoded) {
      overflow_ = true;
      len_ = 0;
      return false;
    }
    buf_[len_++] = byte;
    return false;
  }
  if (overflow_) {
    ++stats_.oversize;
    overflow_ = false;
    len_ = 0;
    return false;
  }
  if (len_ == 0) {
    ++stats_.empty;                        // 0x00 liên tiếp: đồng bộ, không phải lỗi
    return false;
  }
  ++stats_.frames;
  uint8_t decoded[kMaxEncoded];
  size_t n = 0;
  const bool ok = cobs_decode(buf_, len_, decoded, sizeof(decoded), &n);
  len_ = 0;
  if (!ok) {
    ++stats_.cobs;
    return false;
  }
  if (n < kHeaderSize + kCrcSize) {
    ++stats_.short_frames;
    return false;
  }
  const size_t raw_len = n - kCrcSize;
  const uint16_t crc = static_cast<uint16_t>(decoded[raw_len] | (decoded[raw_len + 1] << 8));
  if (crc16_ccitt_false(decoded, raw_len) != crc) {
    ++stats_.crc;
    return false;
  }
  switch (decode_host_message(decoded, raw_len, out)) {
    case FrameError::None:
      ++stats_.messages;
      return true;
    case FrameError::Short: ++stats_.short_frames; break;
    case FrameError::Version: ++stats_.version; break;
    case FrameError::Type: ++stats_.type; break;
    case FrameError::Length: ++stats_.length; break;
    default: ++stats_.cobs; break;          // không xảy ra: decode_host_message không trả các mã còn lại
  }
  return false;
}

}  // namespace ap
