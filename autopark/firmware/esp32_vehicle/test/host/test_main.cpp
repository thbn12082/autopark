// Test trên máy tính (không cần bo, không cần Arduino) cho lõi firmware src/core.
// Đọc test/vectors.json — sinh từ bản tham chiếu Python (python -m autopark.transport.vectors --write) — và kiểm:
//   CRC-16, COBS, mã hóa từng thông điệp, bộ tách khung với luồng lỗi, và từng bước của các kịch bản máy trạng
//   thái (trạng thái, lỗi, lý do dừng, phiên, mục tiêu, effort, số khung bị bỏ vì đầy bộ đệm gửi, TOÀN BỘ byte
//   gửi đi).
//
// Build (từ firmware/esp32_vehicle):
//   mkdir -p build
//   g++ -std=c++17 -O1 -Wall -Wextra -Isrc/core src/core/*.cpp test/host/test_main.cpp -o build/host_tests
//   ./build/host_tests test/vectors.json
// hoặc: cmake -S test/host -B build/host && cmake --build build/host && ./build/host/host_tests test/vectors.json
//
// CHƯA TỪNG ĐƯỢC BIÊN DỊCH: máy phát triển hiện tại không có trình biên dịch C/C++.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

#include "cobs.h"
#include "crc16.h"
#include "protocol.h"
#include "vehicle_core.h"

namespace {

int g_checks = 0;
int g_failures = 0;

#define CHECK(cond, ...)                                              \
  do {                                                                \
    ++g_checks;                                                       \
    if (!(cond)) {                                                    \
      ++g_failures;                                                   \
      std::fprintf(stderr, "FAIL %s:%d: ", __FILE__, __LINE__);       \
      std::fprintf(stderr, __VA_ARGS__);                              \
      std::fprintf(stderr, "\n");                                     \
    }                                                                 \
  } while (0)

[[noreturn]] void die(const std::string& what) {
  std::fprintf(stderr, "fatal: %s\n", what.c_str());
  std::exit(2);
}

// ---- JSON tối giản: object, array, string (ASCII, \uXXXX bị thay bằng '?'), số nguyên, true/false/null ----------
struct Json {
  enum class Kind { Null, Bool, Number, String, Array, Object };
  Kind kind = Kind::Null;
  bool boolean = false;
  long long number = 0;
  std::string text;
  std::vector<Json> items;
  std::vector<std::pair<std::string, Json>> members;

  const Json* find(const std::string& key) const {
    for (const auto& member : members) {
      if (member.first == key) {
        return &member.second;
      }
    }
    return nullptr;
  }
  const Json& at(const std::string& key) const {
    const Json* value = find(key);
    if (value == nullptr) {
      die("missing key " + key);
    }
    return *value;
  }
  long long i() const {
    if (kind == Kind::Bool) {
      return boolean ? 1 : 0;
    }
    if (kind != Kind::Number) {
      die("expected a number");
    }
    return number;
  }
  bool b() const {
    if (kind != Kind::Bool) {
      die("expected a bool");
    }
    return boolean;
  }
  const std::string& s() const {
    if (kind != Kind::String) {
      die("expected a string");
    }
    return text;
  }
};

class JsonReader {
 public:
  explicit JsonReader(const std::string& source) : src_(source) {}

  Json parse() {
    Json value = parse_value();
    skip_ws();
    if (pos_ != src_.size()) {
      fail("trailing characters");
    }
    return value;
  }

 private:
  [[noreturn]] void fail(const char* what) const {
    std::fprintf(stderr, "JSON error at byte %zu: %s\n", pos_, what);
    std::exit(2);
  }
  void skip_ws() {
    while (pos_ < src_.size() &&
           (src_[pos_] == ' ' || src_[pos_] == '\n' || src_[pos_] == '\r' || src_[pos_] == '\t')) {
      ++pos_;
    }
  }
  char peek() {
    skip_ws();
    if (pos_ >= src_.size()) {
      fail("unexpected end");
    }
    return src_[pos_];
  }
  void expect(char c) {
    if (peek() != c) {
      fail("unexpected character");
    }
    ++pos_;
  }
  Json parse_value() {
    const char c = peek();
    if (c == '{') {
      return parse_object();
    }
    if (c == '[') {
      return parse_array();
    }
    if (c == '"') {
      Json value;
      value.kind = Json::Kind::String;
      value.text = parse_string();
      return value;
    }
    if (c == 't' || c == 'f' || c == 'n') {
      return parse_literal();
    }
    return parse_number();
  }
  Json parse_object() {
    expect('{');
    Json value;
    value.kind = Json::Kind::Object;
    if (peek() == '}') {
      ++pos_;
      return value;
    }
    for (;;) {
      if (peek() != '"') {
        fail("expected key");
      }
      std::string key = parse_string();
      expect(':');
      Json member = parse_value();
      value.members.emplace_back(std::move(key), std::move(member));
      const char c = peek();
      ++pos_;
      if (c == '}') {
        return value;
      }
      if (c != ',') {
        fail("expected , or }");
      }
    }
  }
  Json parse_array() {
    expect('[');
    Json value;
    value.kind = Json::Kind::Array;
    if (peek() == ']') {
      ++pos_;
      return value;
    }
    for (;;) {
      value.items.push_back(parse_value());
      const char c = peek();
      ++pos_;
      if (c == ']') {
        return value;
      }
      if (c != ',') {
        fail("expected , or ]");
      }
    }
  }
  std::string parse_string() {
    expect('"');
    std::string out;
    for (;;) {
      if (pos_ >= src_.size()) {
        fail("unterminated string");
      }
      const char c = src_[pos_++];
      if (c == '"') {
        return out;
      }
      if (c != '\\') {
        out += c;
        continue;
      }
      if (pos_ >= src_.size()) {
        fail("bad escape");
      }
      const char e = src_[pos_++];
      switch (e) {
        case '"': out += '"'; break;
        case '\\': out += '\\'; break;
        case '/': out += '/'; break;
        case 'n': out += '\n'; break;
        case 't': out += '\t'; break;
        case 'r': out += '\r'; break;
        case 'b': out += '\b'; break;
        case 'f': out += '\f'; break;
        case 'u':
          if (pos_ + 4 > src_.size()) {
            fail("bad \\u escape");
          }
          pos_ += 4;
          out += '?';  // chỉ mô tả tiếng Việt dùng \u; test không so sánh chúng
          break;
        default: fail("unknown escape");
      }
    }
  }
  Json parse_literal() {
    Json value;
    if (src_.compare(pos_, 4, "true") == 0) {
      value.kind = Json::Kind::Bool;
      value.boolean = true;
      pos_ += 4;
    } else if (src_.compare(pos_, 5, "false") == 0) {
      value.kind = Json::Kind::Bool;
      pos_ += 5;
    } else if (src_.compare(pos_, 4, "null") == 0) {
      pos_ += 4;
    } else {
      fail("bad literal");
    }
    return value;
  }
  Json parse_number() {
    const size_t start = pos_;
    if (src_[pos_] == '-') {
      ++pos_;
    }
    while (pos_ < src_.size() && src_[pos_] >= '0' && src_[pos_] <= '9') {
      ++pos_;
    }
    if (pos_ == start || (pos_ == start + 1 && src_[start] == '-')) {
      fail("bad number");
    }
    if (pos_ < src_.size() && (src_[pos_] == '.' || src_[pos_] == 'e' || src_[pos_] == 'E')) {
      fail("only integers are expected in vectors.json");
    }
    Json value;
    value.kind = Json::Kind::Number;
    value.number = std::stoll(src_.substr(start, pos_ - start));
    return value;
  }

  const std::string& src_;
  size_t pos_ = 0;
};

// ---- tiện ích ---------------------------------------------------------------------------------------------------
std::vector<uint8_t> from_hex(const std::string& hex) {
  if (hex.size() % 2 != 0) {
    die("odd hex length");
  }
  std::vector<uint8_t> out;
  out.reserve(hex.size() / 2);
  for (size_t i = 0; i < hex.size(); i += 2) {
    out.push_back(static_cast<uint8_t>(std::stoi(hex.substr(i, 2), nullptr, 16)));
  }
  return out;
}

std::string to_hex(const uint8_t* data, size_t len) {
  static const char kDigits[] = "0123456789abcdef";
  std::string out;
  out.reserve(len * 2);
  for (size_t i = 0; i < len; ++i) {
    out += kDigits[data[i] >> 4];
    out += kDigits[data[i] & 0x0F];
  }
  return out;
}

std::string to_hex(const std::vector<uint8_t>& data) { return to_hex(data.data(), data.size()); }

std::string framed(const uint8_t* raw, size_t len) {
  uint8_t frame[ap::kMaxFrame];
  const size_t n = ap::frame_from_raw(raw, len, frame, sizeof(frame));
  return to_hex(frame, n);
}

template <typename T>
T get(const Json& fields, const char* key) {
  return static_cast<T>(fields.at(key).i());
}

// ---- CRC, COBS ----------------------------------------------------------------------------------------------------
void test_crc(const Json& root) {
  for (const Json& item : root.at("crc16").items) {
    const std::vector<uint8_t> data = from_hex(item.at("data").s());
    const uint16_t crc = ap::crc16_ccitt_false(data.data(), data.size());
    CHECK(crc == item.at("crc").i(), "crc16(%s) = %u, expected %lld", item.at("data").s().c_str(), crc,
          item.at("crc").i());
  }
}

void test_cobs(const Json& root) {
  for (const Json& item : root.at("cobs").items) {
    const std::vector<uint8_t> decoded = from_hex(item.at("decoded").s());
    std::vector<uint8_t> out(ap::cobs_max_encoded(decoded.size()));
    const size_t n = ap::cobs_encode(decoded.data(), decoded.size(), out.data(), out.size());
    CHECK(to_hex(out.data(), n) == item.at("encoded").s(), "cobs_encode mismatch for %zu bytes", decoded.size());
    const std::vector<uint8_t> encoded = from_hex(item.at("encoded").s());
    std::vector<uint8_t> back(encoded.size() + 1);
    size_t m = 0;
    const bool ok = ap::cobs_decode(encoded.data(), encoded.size(), back.data(), back.size(), &m);
    CHECK(ok && to_hex(back.data(), m) == item.at("decoded").s(), "cobs_decode mismatch for %zu bytes",
          decoded.size());
  }
  uint8_t small[2];
  const uint8_t data[4] = {1, 2, 3, 4};
  CHECK(ap::cobs_encode(data, 4, small, sizeof(small)) == 0, "cobs_encode must refuse a too-small buffer");
  size_t n = 0;
  const uint8_t bad[3] = {0x05, 0x11, 0x22};
  CHECK(!ap::cobs_decode(bad, 3, small, sizeof(small), &n), "cobs_decode must reject a block past the end");
}

// ---- thông điệp -----------------------------------------------------------------------------------------------------
std::string encode_from_fields(int type, const Json& f) {
  uint8_t raw[ap::kMaxRaw];
  size_t n = 0;
  switch (type) {
    case 0x01: {
      ap::Hello m{get<uint32_t>(f, "session_id"), get<uint16_t>(f, "sequence"), get<uint16_t>(f, "telemetry_period_ms"),
                  get<uint32_t>(f, "host_time_ms")};
      n = ap::encode(m, raw);
      break;
    }
    case 0x02: {
      ap::Request m{get<uint32_t>(f, "session_id"), get<uint16_t>(f, "sequence"), get<uint8_t>(f, "action")};
      n = ap::encode(m, raw);
      break;
    }
    case 0x03: {
      ap::Command m{get<uint32_t>(f, "session_id"), get<uint16_t>(f, "sequence"), get<uint16_t>(f, "validity_ms"),
                    get<uint8_t>(f, "flags"), get<int16_t>(f, "speed_mm_s"), get<int16_t>(f, "steer_mrad")};
      n = ap::encode(m, raw);
      break;
    }
    case 0x81: {
      ap::HelloAck m{};
      m.session_id = get<uint32_t>(f, "session_id");
      m.sequence = get<uint16_t>(f, "sequence");
      m.hello_sequence = get<uint16_t>(f, "hello_sequence");
      m.fw_major = get<uint8_t>(f, "fw_major");
      m.fw_minor = get<uint8_t>(f, "fw_minor");
      m.boot_id = get<uint32_t>(f, "boot_id");
      m.reset_reason = get<uint8_t>(f, "reset_reason");
      m.state = get<uint8_t>(f, "state");
      m.telemetry_period_ms = get<uint16_t>(f, "telemetry_period_ms");
      m.limits.max_speed_mm_s = get<uint16_t>(f, "max_speed_mm_s");
      m.limits.max_steer_mrad = get<uint16_t>(f, "max_steer_mrad");
      m.limits.max_steer_rate_mrad_s = get<uint16_t>(f, "max_steer_rate_mrad_s");
      m.limits.max_accel_mm_s2 = get<uint16_t>(f, "max_accel_mm_s2");
      m.limits.max_decel_mm_s2 = get<uint16_t>(f, "max_decel_mm_s2");
      m.limits.stop_decel_mm_s2 = get<uint16_t>(f, "stop_decel_mm_s2");
      m.limits.max_validity_ms = get<uint16_t>(f, "max_validity_ms");
      m.limits.link_timeout_ms = get<uint16_t>(f, "link_timeout_ms");
      n = ap::encode(m, raw);
      break;
    }
    case 0x82: {
      ap::Ack m{get<uint32_t>(f, "session_id"), get<uint16_t>(f, "sequence"), get<uint8_t>(f, "acked_type"),
                get<uint16_t>(f, "acked_sequence"), get<uint8_t>(f, "result"), get<uint8_t>(f, "state"),
                get<uint8_t>(f, "fault")};
      n = ap::encode(m, raw);
      break;
    }
    case 0x83: {
      ap::Telemetry m{};
      m.session_id = get<uint32_t>(f, "session_id");
      m.sequence = get<uint16_t>(f, "sequence");
      m.sample_time_ms = get<uint32_t>(f, "sample_time_ms");
      m.state = get<uint8_t>(f, "state");
      m.fault = get<uint8_t>(f, "fault");
      m.stop_reason = get<uint8_t>(f, "stop_reason");
      m.flags = get<uint8_t>(f, "flags");
      m.last_cmd_seq = get<uint16_t>(f, "last_cmd_seq");
      m.cmd_age_ms = get<uint16_t>(f, "cmd_age_ms");
      m.speed_measured_mm_s = get<int16_t>(f, "speed_measured_mm_s");
      m.steer_measured_mrad = get<int16_t>(f, "steer_measured_mrad");
      m.speed_ref_mm_s = get<int16_t>(f, "speed_ref_mm_s");
      m.steer_ref_mrad = get<int16_t>(f, "steer_ref_mrad");
      m.effort_permille = get<int16_t>(f, "effort_permille");
      m.gyro_z_mrad_s = get<int16_t>(f, "gyro_z_mrad_s");
      m.accel_x_mm_s2 = get<int16_t>(f, "accel_x_mm_s2");
      m.accel_y_mm_s2 = get<int16_t>(f, "accel_y_mm_s2");
      m.tof_valid_mask = get<uint8_t>(f, "tof_valid_mask");
      const Json& tof = f.at("tof_mm");
      if (tof.items.size() != static_cast<size_t>(ap::kNumTof)) {
        die("tof_mm must have 4 values");
      }
      for (int k = 0; k < ap::kNumTof; ++k) {
        m.tof_mm[k] = static_cast<uint16_t>(tof.items[static_cast<size_t>(k)].i());
      }
      m.supply_mv = get<uint16_t>(f, "supply_mv");
      m.rx_errors = get<uint16_t>(f, "rx_errors");
      m.rejects = get<uint16_t>(f, "rejects");
      n = ap::encode(m, raw);
      break;
    }
    case 0x84: {
      ap::FaultMsg m{get<uint32_t>(f, "session_id"), get<uint16_t>(f, "sequence"), get<uint8_t>(f, "fault"),
                     get<uint8_t>(f, "state"), get<uint32_t>(f, "time_ms"), get<uint16_t>(f, "detail")};
      n = ap::encode(m, raw);
      break;
    }
    default:
      die("unknown message type in vectors");
  }
  return to_hex(raw, n);
}

std::string reencode_host(const ap::HostMessage& m) {
  uint8_t raw[ap::kMaxRaw];
  size_t n = 0;
  switch (m.type) {
    case ap::MsgType::Hello: n = ap::encode(m.hello, raw); break;
    case ap::MsgType::Request: n = ap::encode(m.request, raw); break;
    case ap::MsgType::Command: n = ap::encode(m.command, raw); break;
    default: return "<not a host message>";
  }
  return to_hex(raw, n);
}

void test_messages(const Json& root) {
  for (const Json& item : root.at("messages").items) {
    const int type = static_cast<int>(item.at("type").i());
    const std::string& name = item.at("name").s();
    const std::string raw_hex = encode_from_fields(type, item.at("fields"));
    CHECK(raw_hex == item.at("raw").s(), "message %s: raw %s, expected %s", name.c_str(), raw_hex.c_str(),
          item.at("raw").s().c_str());
    const std::vector<uint8_t> raw = from_hex(item.at("raw").s());
    CHECK(framed(raw.data(), raw.size()) == item.at("frame").s(), "message %s: frame mismatch", name.c_str());
    if (type <= 0x03) {
      ap::HostMessage decoded{};
      const ap::FrameError error = ap::decode_host_message(raw.data(), raw.size(), &decoded);
      CHECK(error == ap::FrameError::None && reencode_host(decoded) == item.at("raw").s(),
            "message %s: host decode/re-encode mismatch", name.c_str());
    }
  }
}

void test_streams(const Json& root) {
  for (const Json& item : root.at("streams_to_device").items) {
    const std::string& name = item.at("name").s();
    const std::vector<uint8_t> stream = from_hex(item.at("stream").s());
    ap::FrameParser parser;
    ap::HostMessage msg{};
    std::vector<std::string> got;
    for (uint8_t byte : stream) {
      if (parser.feed(byte, &msg)) {
        got.push_back(reencode_host(msg));
      }
    }
    const Json& expected = item.at("messages");
    bool same = got.size() == expected.items.size();
    for (size_t k = 0; same && k < got.size(); ++k) {
      same = got[k] == expected.items[k].s();
    }
    CHECK(same, "stream %s: got %zu messages, expected %zu", name.c_str(), got.size(), expected.items.size());
    const Json& errors = item.at("errors");
    const ap::ParserStats& st = parser.stats();
    CHECK(st.cobs == errors.at("cobs").i() && st.short_frames == errors.at("short").i() &&
              st.crc == errors.at("crc").i() && st.version == errors.at("version").i() &&
              st.type == errors.at("type").i() && st.length == errors.at("length").i() &&
              st.oversize == errors.at("oversize").i() && st.empty == item.at("empty").i(),
          "stream %s: error counters differ (cobs %u short %u crc %u version %u type %u length %u oversize %u "
          "empty %u)", name.c_str(), st.cobs, st.short_frames, st.crc, st.version, st.type, st.length, st.oversize,
          st.empty);
  }
  // Fuzz: rác ngẫu nhiên (LCG cố định) không được làm hỏng parser; khung hợp lệ sau 0x00 vẫn được nhận.
  ap::FrameParser parser;
  ap::HostMessage msg{};
  uint32_t lcg = 20260924u;
  for (int k = 0; k < 200000; ++k) {
    lcg = lcg * 1664525u + 1013904223u;
    parser.feed(static_cast<uint8_t>(lcg >> 24), &msg);
  }
  uint8_t raw[ap::kMaxRaw];
  const size_t n = ap::encode(ap::Request{0xA1B2C3D4u, 7, 4}, raw);
  uint8_t frame[ap::kMaxFrame];
  const size_t f = ap::frame_from_raw(raw, n, frame, sizeof(frame));
  bool received = false;
  parser.feed(0, &msg);
  for (size_t i = 0; i < f; ++i) {
    received = parser.feed(frame[i], &msg) || received;
  }
  CHECK(received && msg.type == ap::MsgType::Request && msg.request.sequence == 7,
        "valid frame after random garbage was not received");
  CHECK(parser.stats().errors() > 0, "random garbage produced no parser errors");
}

// ---- kịch bản máy trạng thái ----------------------------------------------------------------------------------------
struct IntField {
  const char* name;
  int32_t ap::Config::*member;
};

const IntField kIntFields[] = {
    {"boot_hold_ms", &ap::Config::boot_hold_ms},
    {"max_speed_mm_s", &ap::Config::max_speed_mm_s},
    {"max_steer_mrad", &ap::Config::max_steer_mrad},
    {"max_steer_rate_mrad_s", &ap::Config::max_steer_rate_mrad_s},
    {"max_accel_mm_s2", &ap::Config::max_accel_mm_s2},
    {"max_decel_mm_s2", &ap::Config::max_decel_mm_s2},
    {"stop_decel_mm_s2", &ap::Config::stop_decel_mm_s2},
    {"max_validity_ms", &ap::Config::max_validity_ms},
    {"link_timeout_ms", &ap::Config::link_timeout_ms},
    {"default_telemetry_period_ms", &ap::Config::default_telemetry_period_ms},
    {"min_telemetry_period_ms", &ap::Config::min_telemetry_period_ms},
    {"max_telemetry_period_ms", &ap::Config::max_telemetry_period_ms},
    {"max_tick_gap_ms", &ap::Config::max_tick_gap_ms},
    {"direction_change_hold_ms", &ap::Config::direction_change_hold_ms},
    {"standstill_mm_s", &ap::Config::standstill_mm_s},
    {"ff_permille_per_mps", &ap::Config::ff_permille_per_mps},
    {"deadzone_comp_permille", &ap::Config::deadzone_comp_permille},
    {"kp_permille_per_mps", &ap::Config::kp_permille_per_mps},
    {"ki_permille_per_m", &ap::Config::ki_permille_per_m},
    {"integ_limit_permille", &ap::Config::integ_limit_permille},
    {"max_effort_permille", &ap::Config::max_effort_permille},
    {"stall_effort_permille", &ap::Config::stall_effort_permille},
    {"stall_timeout_ms", &ap::Config::stall_timeout_ms},
    {"min_supply_mv", &ap::Config::min_supply_mv},
    {"tx_capacity", &ap::Config::tx_capacity},
};

ap::Config config_from_json(const Json& j) {
  ap::Config config;
  for (const auto& member : j.members) {
    bool known = false;
    for (const IntField& field : kIntFields) {
      if (member.first == field.name) {
        config.*(field.member) = static_cast<int32_t>(member.second.i());
        known = true;
      }
    }
    if (member.first == "require_speed_feedback") {
      config.require_speed_feedback = member.second.b();
      known = true;
    } else if (member.first == "fw_major") {
      config.fw_major = static_cast<uint8_t>(member.second.i());
      known = true;
    } else if (member.first == "fw_minor") {
      config.fw_minor = static_cast<uint8_t>(member.second.i());
      known = true;
    }
    if (!known) {
      die("unknown config key " + member.first + " (C++ Config out of date?)");
    }
  }
  return config;
}

ap::Inputs inputs_from_json(const Json& j) {
  ap::Inputs in;  // trường vắng mặt = mặc định (giống FirmwareInputs.to_dict chỉ ghi trường khác mặc định)
  for (const auto& member : j.members) {
    const std::string& key = member.first;
    const Json& v = member.second;
    if (key == "estop") in.estop = v.b();
    else if (key == "speed_valid") in.speed_valid = v.b();
    else if (key == "speed_mm_s") in.speed_mm_s = static_cast<int32_t>(v.i());
    else if (key == "steer_valid") in.steer_valid = v.b();
    else if (key == "steer_mrad") in.steer_mrad = static_cast<int32_t>(v.i());
    else if (key == "imu_valid") in.imu_valid = v.b();
    else if (key == "gyro_z_mrad_s") in.gyro_z_mrad_s = static_cast<int32_t>(v.i());
    else if (key == "accel_x_mm_s2") in.accel_x_mm_s2 = static_cast<int32_t>(v.i());
    else if (key == "accel_y_mm_s2") in.accel_y_mm_s2 = static_cast<int32_t>(v.i());
    else if (key == "tof_valid_mask") in.tof_valid_mask = static_cast<uint8_t>(v.i());
    else if (key == "tof_mm") {
      for (int k = 0; k < ap::kNumTof; ++k) {
        in.tof_mm[k] = static_cast<int32_t>(v.items.at(static_cast<size_t>(k)).i());
      }
    } else if (key == "supply_valid") in.supply_valid = v.b();
    else if (key == "supply_mv") in.supply_mv = static_cast<int32_t>(v.i());
    else die("unknown input key " + key);
  }
  return in;
}

void test_scenarios(const Json& root) {
  for (const Json& scenario : root.at("scenarios").items) {
    const std::string& name = scenario.at("name").s();
    ap::VehicleCore core;
    core.begin(config_from_json(scenario.at("config")), static_cast<uint32_t>(scenario.at("boot_ms").i()),
               static_cast<uint32_t>(scenario.at("boot_id").i()),
               static_cast<ap::ResetReason>(scenario.at("reset_reason").i()));
    int index = 0;
    int scenario_failures = 0;
    for (const Json& step : scenario.at("steps").items) {
      const uint32_t t = static_cast<uint32_t>(step.at("t").i());
      const std::vector<uint8_t> rx = from_hex(step.at("rx").s());
      if (!rx.empty()) {
        core.receive(rx.data(), rx.size(), t);
      }
      const ap::Outputs out = core.step(t, inputs_from_json(step.at("in")));
      const std::string tx = to_hex(core.tx_data(), core.tx_size());
      core.tx_clear();
      const Json& e = step.at("expect");
      const bool ok = static_cast<int>(out.state) == e.at("state").i() &&
                      static_cast<int>(core.fault()) == e.at("fault").i() &&
                      static_cast<int>(core.stop_reason()) == e.at("stop_reason").i() &&
                      core.session_id() == static_cast<uint32_t>(e.at("session_id").i()) &&
                      out.speed_ref_mm_s == e.at("speed_ref_mm_s").i() &&
                      out.steer_ref_mrad == e.at("steer_ref_mrad").i() &&
                      out.effort_permille == e.at("effort_permille").i() && tx == e.at("tx").s() &&
                      static_cast<long long>(core.tx_overflow()) == e.at("tx_overflow").i();
      CHECK(ok, "scenario %s step %d t=%u: state %d fault %d reason %d speed %d steer %d effort %d tx_overflow %u "
                "tx %s (expected state %lld speed %lld steer %lld effort %lld tx_overflow %lld tx %s)",
            name.c_str(), index, t, static_cast<int>(out.state), static_cast<int>(core.fault()),
            static_cast<int>(core.stop_reason()), out.speed_ref_mm_s, out.steer_ref_mrad, out.effort_permille,
            static_cast<unsigned>(core.tx_overflow()), tx.c_str(), e.at("state").i(), e.at("speed_ref_mm_s").i(),
            e.at("steer_ref_mrad").i(), e.at("effort_permille").i(), e.at("tx_overflow").i(), e.at("tx").s().c_str());
      if (!ok && ++scenario_failures >= 3) {
        std::fprintf(stderr, "  (stopping scenario %s after 3 failures)\n", name.c_str());
        break;
      }
      ++index;
    }
  }
}

}  // namespace

int main(int argc, char** argv) {
  const char* path = argc > 1 ? argv[1] : "test/vectors.json";
  std::ifstream file(path, std::ios::binary);
  if (!file) {
    std::fprintf(stderr, "cannot open %s\n", path);
    return 2;
  }
  std::stringstream buffer;
  buffer << file.rdbuf();
  const std::string text = buffer.str();
  const Json root = JsonReader(text).parse();
  if (root.at("format").s() != "autopark-vehicle-vectors" || root.at("protocol_version").i() != ap::kProtocolVersion) {
    die("unexpected vectors file format or protocol version");
  }
  test_crc(root);
  test_cobs(root);
  test_messages(root);
  test_streams(root);
  test_scenarios(root);
  std::printf("%d checks, %d failures\n", g_checks, g_failures);
  return g_failures == 0 ? 0 : 1;
}
