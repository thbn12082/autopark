# Test lõi firmware trên máy tính (không cần bo). Chạy lần đầu 29/09/2026 (g++ 16.1.0, cmake 4.4.1), xem README.md.
#   cmake -S test/host -B build/host -DCMAKE_BUILD_TYPE=Release && cmake --build build/host --config Release
#   ctest --test-dir build/host -C Release --output-on-failure
# (--config/-C cho generator nhiều cấu hình như Visual Studio, mặc định trên Windows khi có VS; Ninja/Makefile bỏ qua.)
cmake_minimum_required(VERSION 3.20)   # ctest --test-dir có từ 3.20
project(esp32_vehicle_host_tests CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
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
# MinGW: liên kết tĩnh libstdc++/libgcc. Không thì exe nạp libstdc++-6.dll đầu tiên trên PATH; trong Git Bash đó là bản
# cũ của Git (C:\Program Files\Git\mingw64\bin), và bản build có tối ưu segfault ngay ở std::ifstream (đo 29/09/2026).
if(MINGW)
  target_link_options(host_tests PRIVATE -static)
endif()

enable_testing()
# Mã thoát: 0 = đạt, 1 = có check lệch, 2 = không mở được tệp vector.
add_test(NAME vectors COMMAND host_tests ${CMAKE_CURRENT_SOURCE_DIR}/../vectors.json)
