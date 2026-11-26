#include "cobs.h"

namespace ap {

size_t cobs_encode(const uint8_t* in, size_t len, uint8_t* out, size_t cap) {
  if (cap < cobs_max_encoded(len)) {
    return 0;
  }
  size_t o = 1;           // out[0] dành cho mã khối đầu tiên
  size_t code_index = 0;
  bool code_pending = true;
  uint8_t code = 1;
  for (size_t i = 0; i < len; ++i) {
    const uint8_t byte = in[i];
    if (byte != 0) {
      out[o++] = byte;
      ++code;
    }
    if (byte == 0 || code == 0xFF) {
      out[code_index] = code;
      code = 1;
      if (byte == 0 || i + 1 < len) {
        code_index = o++;
        code_pending = true;
      } else {
        code_pending = false;  // khối 254 byte kết thúc đúng ở cuối dữ liệu: không thêm mã
      }
    }
  }
  if (code_pending) {
    out[code_index] = code;
  }
  return o;
}

bool cobs_decode(const uint8_t* in, size_t len, uint8_t* out, size_t cap, size_t* out_len) {
  if (len == 0) {
    return false;
  }
  size_t i = 0;
  size_t o = 0;
  while (i < len) {
    const uint8_t code = in[i];
    if (code == 0) {
      return false;
    }
    const size_t end = i + code;
    if (end > len) {
      return false;
    }
    for (size_t k = i + 1; k < end; ++k) {
      if (in[k] == 0 || o >= cap) {
        return false;
      }
      out[o++] = in[k];
    }
    i = end;
    if (code != 0xFF && i < len) {
      if (o >= cap) {
        return false;
      }
      out[o++] = 0;
    }
  }
  *out_len = o;
  return true;
}

}  // namespace ap
