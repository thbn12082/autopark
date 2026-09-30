"""PlatformIO, post-script của env `esp32s3_qemu`: ghép bootloader + bảng phân vùng + boot_app0 + firmware thành MỘT ảnh
flash cho QEMU, `.pio/build/esp32s3_qemu/qemu_flash.bin`, đúng cỡ flash của bo (8 MB; QEMU chỉ nhận ảnh 2/4/8/16 MB).

Offset và đường dẫn lấy từ builder của PlatformIO (FLASH_EXTRA_IMAGES, ESP32_APP_OFFSET; với ESP32-S3 là 0x0, 0x8000,
0xe000, 0x10000), không ghi tay; esptool là bản của nền tảng ($OBJCOPY). Header chế độ/tần số/cỡ flash giữ như lúc
build (merge_bin mặc định "keep"). Ảnh là một mục tiêu SCons: thiếu hoặc đầu vào đổi thì build lại.
Xem docs/MO_PHONG_FIRMWARE.md.
"""
Import("env")  # noqa: F821 - SCons cung cấp

board = env.BoardConfig()  # noqa: F821
flash_size = board.get("upload.flash_size", "4MB")
images = list(env.get("FLASH_EXTRA_IMAGES", [])) + [("$ESP32_APP_OFFSET", "$BUILD_DIR/${PROGNAME}.bin")]  # noqa: F821
command = ['"$PYTHONEXE"', '"$OBJCOPY"', "--chip", board.get("build.mcu"), "merge_bin",
           "--fill-flash-size", flash_size, "-o", '"$TARGET"']
for offset, path in images:
    command += [offset, '"%s"' % path]

merged = env.Command(  # noqa: F821
    "$BUILD_DIR/qemu_flash.bin",
    [path for _, path in images],
    env.VerboseAction(" ".join(command), "Ghép ảnh flash cho QEMU: $TARGET"),  # noqa: F821
)
env.Default(merged)  # noqa: F821
