// CRC-16/CCITT-FALSE: đa thức 0x1021, khởi tạo 0xFFFF, không đảo bit, không XOR cuối.
// Giá trị kiểm tra: crc16_ccitt_false("123456789", 9) == 0x29B1.
// Bản tham chiếu: autopark/transport/protocol.py (crc16_ccitt_false). C++17 thuần, không dùng Arduino.
#pragma once

#include <cstddef>
#include <cstdint>

namespace ap {

uint16_t crc16_ccitt_false(const uint8_t* data, size_t len, uint16_t crc = 0xFFFF);

}  // namespace ap
