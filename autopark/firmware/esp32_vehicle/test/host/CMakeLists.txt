# Test lõi firmware trên máy tính (không cần bo). CHƯA TỪNG CHẠY: máy phát triển hiện tại không có trình biên dịch.
#   cmake -S test/host -B build/host && cmake --build build/host && ./build/host/host_tests test/vectors.json
cmake_minimum_required(VERSION 3.16)
project(esp32_vehicle_host_tests CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CORE ${CMAKE_CURRENT_SOURCE_DIR}/../../src/core)
add_executable(host_tests
  test_main.cpp
  ${CORE}/crc16.cpp
  ${CORE}/cobs.cpp
  ${CORE}/protocol.cpp
  ${CORE}/vehicle_core.cpp)
target_include_directories(host_tests PRIVATE ${CORE})
if(MSVC)
  target_compile_options(host_tests PRIVATE /W4)
else()
  target_compile_options(host_tests PRIVATE -Wall -Wextra)
endif()
