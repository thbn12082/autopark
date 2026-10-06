#!/usr/bin/env bash
# Bảng: mã thoát Windows (ExitProcess) -> $? trong Git Bash, qua 3 đường: python gốc, venv launcher, timeout + venv launcher.
# Chỉ tự thoát bằng mã (không ngoại lệ, không WER). Việc 8, 06/10/2026.
# (Bản chép vào repo 06/10/2026: python gốc lấy theo %LOCALAPPDATA% thay vì đường dẫn hồ sơ người dùng viết cứng.)
# Dùng: bash bang_ma_thoat.sh [chinh|bo_sung]
#   chinh (mặc định): 27 mã -> bang_ma_thoat_ket_qua.txt;
#   bo_sung: 20 mã -> bang_ma_thoat_bo_sung.txt (thêm 06/10/2026 tối: bản đầu của tệp đó chỉ đo qua python gốc).
S="$(dirname "$0")"
VENV=/d/xetulai/autopark/autopark/.venv/Scripts/python.exe
BASE="$(cygpath -u "$LOCALAPPDATA")/Programs/Python/Python312/python.exe"
bang() {
printf "%-12s %-34s %6s %6s %8s  %s\n" "ma" "y_nghia" "goc" "venv" "timeout" "stderr_cua_bash"
while read -r code name; do
  [ -z "$code" ] && continue
  e1=$( { "$BASE" "$S/thoat_ma.py" "$code"; echo "rc=$?"; } 2>&1 | tr '\n' ' ')
  r1=$(echo "$e1" | grep -o 'rc=[0-9]*' | cut -d= -f2)
  e2=$( { "$VENV" "$S/thoat_ma.py" "$code"; echo "rc=$?"; } 2>&1 | tr '\n' ' ')
  r2=$(echo "$e2" | grep -o 'rc=[0-9]*' | cut -d= -f2)
  e3=$( { timeout 60 "$VENV" "$S/thoat_ma.py" "$code"; echo "rc=$?"; } 2>&1 | tr '\n' ' ')
  r3=$(echo "$e3" | grep -o 'rc=[0-9]*' | cut -d= -f2)
  extra=$(echo "$e1 | $e2 | $e3" | sed 's/rc=[0-9]*//g' | tr -s ' |' | cut -c1-120)
  printf "%-12s %-34s %6s %6s %8s  %s\n" "$code" "$name" "$r1" "$r2" "$r3" "$extra"
done
}
case "${1:-chinh}" in
chinh) bang <<'EOF'
0 thanh_cong
1 loi_thuong
3 abort_CRT_cu
127 ma_127_truc_tiep
0x17F 383_byte_thap_7F
255 ma_255
0x40000015 STATUS_FATAL_APP_EXIT
0x40010004 DBG_TERMINATE_PROCESS
0x80000003 STATUS_BREAKPOINT
0xBFFFFFFF ngay_duoi_C0000000
0xC0000005 STATUS_ACCESS_VIOLATION
0xC0000006 STATUS_IN_PAGE_ERROR
0xC0000017 STATUS_NO_MEMORY
0xC000001D STATUS_ILLEGAL_INSTRUCTION
0xC000007F STATUS_DISK_FULL
0xC0000094 STATUS_INTEGER_DIVIDE_BY_ZERO
0xC00000FD STATUS_STACK_OVERFLOW
0xC000012D STATUS_COMMITMENT_LIMIT
0xC0000135 STATUS_DLL_NOT_FOUND
0xC000013A STATUS_CONTROL_C_EXIT
0xC0000142 STATUS_DLL_INIT_FAILED
0xC0000374 STATUS_HEAP_CORRUPTION
0xC0000409 STATUS_STACK_BUFFER_OVERRUN_fastfail
0xC0000420 STATUS_ASSERTION_FAILURE
0xC06D007F delay_load_proc_not_found
0xE06D7363 MSVC_Cpp_exception
0xE0434352 CLR_exception
EOF
;;
bo_sung) bang <<'EOF'
0x80000002 STATUS_DATATYPE_MISALIGNMENT
0xC0000008 STATUS_INVALID_HANDLE
0xC0000025 STATUS_NONCONTINUABLE_EXCEPTION
0xC0000026 STATUS_INVALID_DISPOSITION
0xC000008C STATUS_ARRAY_BOUNDS_EXCEEDED
0xC000008D STATUS_FLOAT_DENORMAL_OPERAND
0xC000008E STATUS_FLOAT_DIVIDE_BY_ZERO
0xC000008F STATUS_FLOAT_INEXACT_RESULT
0xC0000090 STATUS_FLOAT_INVALID_OPERATION
0xC0000091 STATUS_FLOAT_OVERFLOW
0xC0000092 STATUS_FLOAT_STACK_CHECK
0xC0000093 STATUS_FLOAT_UNDERFLOW
0xC0000095 STATUS_INTEGER_OVERFLOW
0xC0000096 STATUS_PRIVILEGED_INSTRUCTION
0xC0000194 STATUS_POSSIBLE_DEADLOCK
0xC0000602 STATUS_FAIL_FAST_EXCEPTION
0xC000041D STATUS_FATAL_USER_CALLBACK_EXC
0xFFFFFFFF ma_cua_Stop-Process_-Force
0xC0000001 STATUS_UNSUCCESSFUL
0xDEADBEEF ma_tuy_y
EOF
;;
*) echo "tham số phải là chinh hoặc bo_sung"; exit 2 ;;
esac
