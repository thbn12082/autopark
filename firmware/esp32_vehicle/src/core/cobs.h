// COBS (Cheshire & Baker 1999), cùng kết quả với autopark/transport/protocol.py (cobs_encode / cobs_decode):
// khối 254 byte khác 0 ở cuối dữ liệu KHÔNG kèm mã 0x01 thừa. Không cấp phát động, không ghi quá `cap`.
#pragma once

#include <cstddef>
#include <cstdint>

namespace ap {

// Độ dài tối đa của kết quả mã hóa `len` byte (không kể dấu phân cách 0x00).
constexpr size_t cobs_max_encoded(size_t len) { return len + len / 254 + 1; }

// Trả số byte đã ghi, hoặc 0 nếu `cap` < cobs_max_encoded(len). Kết quả không chứa byte 0.
size_t cobs_encode(const uint8_t* in, size_t len, uint8_t* out, size_t cap);

// Giải chặt: rỗng, byte 0 bên trong, khối chạy quá cuối hoặc thiếu chỗ trong `out` đều trả false.
bool cobs_decode(const uint8_t* in, size_t len, uint8_t* out, size_t cap, size_t* out_len);

}  // namespace ap
