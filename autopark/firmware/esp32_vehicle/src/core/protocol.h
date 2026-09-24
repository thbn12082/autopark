// Giao thức laptop <-> ESP32-S3 phiên bản 1 (docs/GIAO_THUC_XE.md). Bản tham chiếu: autopark/transport/protocol.py.
//
// Khung trên dây: COBS(thông điệp || CRC-16/CCITT-FALSE little-endian) || 0x00. Mọi số nguyên little-endian.
// Phần đầu 8 byte: version u8, type u8, session_id u32, sequence u16. Thân có độ dài CỐ ĐỊNH theo loại.
// C++17 thuần, không Arduino, không cấp phát động, không ngoại lệ.
#pragma once

#include <cstddef>
#include <cstdint>

namespace ap {

constexpr uint8_t kProtocolVersion = 1;
constexpr size_t kHeaderSize = 8;
constexpr size_t kCrcSize = 2;
constexpr size_t kMaxRaw = 64;                 // thông điệp dài nhất (TELEMETRY) là 51 byte
constexpr size_t kMaxEncoded = 80;             // byte COBS tối đa của một khung nhận, không kể 0x00
constexpr size_t kMaxFrame = 72;               // khung gửi dài nhất: COBS(64 + 2) + 0x00 = 68
constexpr int kNumTof = 4;
constexpr uint8_t kCommandFlagEnable = 0x01;
constexpr uint16_t kNoCommandAge = 0xFFFF;

constexpr size_t kSizeHello = 14;
constexpr size_t kSizeRequest = 9;
constexpr size_t kSizeCommand = 15;
constexpr size_t kSizeHelloAck = 36;
constexpr size_t kSizeAck = 14;
constexpr size_t kSizeTelemetry = 51;
constexpr size_t kSizeFault = 16;

enum class MsgType : uint8_t {
  Hello = 0x01, Request = 0x02, Command = 0x03,
  HelloAck = 0x81, Ack = 0x82, Telemetry = 0x83, Fault = 0x84,
};
enum class State : uint8_t { Boot = 0, Disarmed = 1, Armed = 2, Running = 3, Fault = 4 };
enum class Fault : uint8_t { None = 0, Estop = 1, LoopOverrun = 2, SupplyLow = 3, FeedbackLost = 4, Stall = 5 };
enum class StopReason : uint8_t {
  None = 0, Boot = 1, HostDisarm = 2, CommandTimeout = 3, LinkTimeout = 4, NewSession = 5, EnableCleared = 6,
  Fault = 7,
};
enum class Result : uint8_t {
  Ok = 0, NoSession = 1, WrongSession = 2, Duplicate = 3, OutOfOrder = 4, BadState = 5, FaultActive = 6,
  EstopActive = 7, BadField = 8, NotReady = 9,
};
enum class Action : uint8_t { Arm = 1, Disarm = 2, ClearFault = 3, Ping = 4 };
enum class ResetReason : uint8_t { Unknown = 0, PowerOn = 1, Software = 2, Watchdog = 3, Brownout = 4, Other = 5 };

namespace tflag {
constexpr uint8_t kEstopInput = 0x01;
constexpr uint8_t kLinkOk = 0x02;
constexpr uint8_t kCmdActive = 0x04;
constexpr uint8_t kSpeedValid = 0x08;
constexpr uint8_t kSteerValid = 0x10;
constexpr uint8_t kImuValid = 0x20;
constexpr uint8_t kSupplyValid = 0x40;
constexpr uint8_t kSpeedLoopClosed = 0x80;
}  // namespace tflag

struct Hello {
  uint32_t session_id;
  uint16_t sequence;
  uint16_t telemetry_period_ms;
  uint32_t host_time_ms;
};

struct Request {
  uint32_t session_id;
  uint16_t sequence;
  uint8_t action;
};

struct Command {
  uint32_t session_id;
  uint16_t sequence;
  uint16_t validity_ms;
  uint8_t flags;
  int16_t speed_mm_s;
  int16_t steer_mrad;
};

struct Limits {
  uint16_t max_speed_mm_s;
  uint16_t max_steer_mrad;
  uint16_t max_steer_rate_mrad_s;
  uint16_t max_accel_mm_s2;
  uint16_t max_decel_mm_s2;
  uint16_t stop_decel_mm_s2;
  uint16_t max_validity_ms;
  uint16_t link_timeout_ms;
};

struct HelloAck {
  uint32_t session_id;
  uint16_t sequence;
  uint16_t hello_sequence;
  uint8_t fw_major;
  uint8_t fw_minor;
  uint32_t boot_id;
  uint8_t reset_reason;
  uint8_t state;
  uint16_t telemetry_period_ms;
  Limits limits;
};

struct Ack {
  uint32_t session_id;
  uint16_t sequence;
  uint8_t acked_type;
  uint16_t acked_sequence;
  uint8_t result;
  uint8_t state;
  uint8_t fault;
};

struct Telemetry {
  uint32_t session_id;
  uint16_t sequence;
  uint32_t sample_time_ms;
  uint8_t state;
  uint8_t fault;
  uint8_t stop_reason;
  uint8_t flags;
  uint16_t last_cmd_seq;
  uint16_t cmd_age_ms;
  int16_t speed_measured_mm_s;
  int16_t steer_measured_mrad;
  int16_t speed_ref_mm_s;
  int16_t steer_ref_mrad;
  int16_t effort_permille;
  int16_t gyro_z_mrad_s;
  int16_t accel_x_mm_s2;
  int16_t accel_y_mm_s2;
  uint8_t tof_valid_mask;
  uint16_t tof_mm[kNumTof];
  uint16_t supply_mv;
  uint16_t rx_errors;
  uint16_t rejects;
};

struct FaultMsg {
  uint32_t session_id;
  uint16_t sequence;
  uint8_t fault;
  uint8_t state;
  uint32_t time_ms;
  uint16_t detail;
};

// Thông điệp laptop gửi tới bo sau khi giải mã; chỉ trường ứng với `type` có nghĩa.
struct HostMessage {
  MsgType type;
  Hello hello;
  Request request;
  Command command;
};

// Mã hóa thành byte thông điệp (chưa CRC/COBS). `out` phải có ít nhất kMaxRaw byte. Trả số byte.
size_t encode(const Hello& m, uint8_t* out);
size_t encode(const Request& m, uint8_t* out);
size_t encode(const Command& m, uint8_t* out);
size_t encode(const HelloAck& m, uint8_t* out);
size_t encode(const Ack& m, uint8_t* out);
size_t encode(const Telemetry& m, uint8_t* out);
size_t encode(const FaultMsg& m, uint8_t* out);

// Byte thông điệp -> khung trên dây (CRC, COBS, 0x00). Trả độ dài khung, hoặc 0 nếu không đủ chỗ.
size_t frame_from_raw(const uint8_t* raw, size_t len, uint8_t* out, size_t cap);

enum class FrameError : uint8_t { None, Cobs, Short, Crc, Version, Type, Length, Oversize };

// Byte thông điệp đã bỏ CRC -> thông điệp laptop->bo. Loại bo->laptop bị coi là loại lạ (FrameError::Type).
FrameError decode_host_message(const uint8_t* raw, size_t len, HostMessage* out);

struct ParserStats {
  uint32_t frames;
  uint32_t messages;
  uint32_t empty;
  uint32_t cobs;
  uint32_t short_frames;
  uint32_t crc;
  uint32_t version;
  uint32_t type;
  uint32_t length;
  uint32_t oversize;
  uint32_t errors() const { return cobs + short_frames + crc + version + type + length + oversize; }
};

// Tách khung phía bo: chịu rác, khung cụt, khung quá dài, sai CRC/phiên bản/loại/độ dài; không bao giờ lỗi.
class FrameParser {
 public:
  // Nạp một byte. Trả true khi *out vừa nhận một thông điệp hợp lệ.
  bool feed(uint8_t byte, HostMessage* out);
  void reset();
  const ParserStats& stats() const { return stats_; }

 private:
  uint8_t buf_[kMaxEncoded] = {};
  size_t len_ = 0;
  bool overflow_ = false;
  ParserStats stats_ = {};
};

}  // namespace ap
