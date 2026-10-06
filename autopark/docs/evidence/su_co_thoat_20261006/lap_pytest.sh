#!/usr/bin/env bash
# Việc 8 (b), 06/10/2026: lặp bộ test đầy đủ .venv qua chay_co_theo_doi.py (ErrorMode 0x8001 -> crash có minidump WER),
# để bắt lại lần pytest thoát 0xC0000005 lúc tắt.
# Bản trong repo (06/10/2026), sửa theo phản biện so với bản nháp đã chạy 3 lượt lúc 15:47–16:20:
# - hai chế độ:
#   day_du      : -X faulthandler + plugin ghi_dau_tat (dấu các pha tắt) + -q -rfE (như 3 lượt 06/10/2026, bỏ
#                 -o faulthandler_timeout=300: lượt crash 06/10/2026 14:46 không có cờ này);
#   chi_wrapper : chỉ wrapper, KHÔNG -X faulthandler, KHÔNG plugin — đúng điều kiện hai lần crash (lệnh như lượt
#                 06/10/2026 14:46 của chay_tren_commit.py); vẫn có minidump nhờ ErrorMode 0x8001;
# - hạn giờ mỗi lượt 3000 s (--het-gio của wrapper; lượt đầy đủ ≈ 10–12 phút);
# - đầu ra của chính wrapper vào wrapper.txt (bản nháp ghi đè lên dau_ra.txt của lệnh);
# - thư mục repo lấy theo vị trí script; kết quả ở thư mục tham số 2 (mặc định runs/su_co_thoat/<ngày giờ>, git bỏ qua).
# Dừng trước lượt kế nếu có tệp <thư mục kết quả>/DUNG. Nặng CPU: chỉ chạy khi máy rảnh.
# Trước khi chạy: sao lưu %LOCALAPPDATA%\CrashDumps (DumpCount 10: dump mới đẩy dump cũ nhất ra).
# Dùng (Git Bash): bash lap_pytest.sh [số lượt, mặc định 5] [thư mục kết quả] [day_du|chi_wrapper]
# Biến môi trường: GHI_DAU_TAT_DEM_WIDGET=0 tắt đếm widget của plugin (xem ghi_dau_tat.py).
N="$(cd "$(dirname "$0")" && pwd)"            # thư mục bằng chứng này
A="$(cd "$N/../../.." && pwd)"                # thư mục autopark của repo
LUOT="${1:-5}"
OUT="${2:-$A/runs/su_co_thoat/$(date +%Y%m%d_%H%M%S)}"
CHE_DO="${3:-day_du}"
case "$CHE_DO" in day_du|chi_wrapper) ;; *) echo "chế độ phải là day_du hoặc chi_wrapper"; exit 2 ;; esac
mkdir -p "$OUT" || exit 2
OUT="$(cd "$OUT" && pwd -W)"                  # đường dẫn kiểu C:/… để MSYS không đổi giá trị --env
P="$OUT/plugin"                               # chỉ chứa ghi_dau_tat.py (không đưa script khác vào PYTHONPATH)
mkdir -p "$P" && cp -f "$N/ghi_dau_tat.py" "$P/"
cd "$A" || exit 2
echo "$(date '+%d/%m/%Y %T') bắt đầu: $LUOT lượt, chế độ $CHE_DO, HEAD $(git rev-parse --short HEAD 2>/dev/null)" \
  | tee -a "$OUT/ket_qua.txt"
for i in $(seq 1 "$LUOT"); do
  if [ -f "$OUT/DUNG" ]; then echo "$(date +%T) dừng theo tệp DUNG trước lượt $i" | tee -a "$OUT/ket_qua.txt"; break; fi
  R="$OUT/lan_$i"
  mkdir -p "$R"
  echo "$(date +%T) bắt đầu lượt $i ($CHE_DO)" | tee -a "$OUT/ket_qua.txt"
  if [ "$CHE_DO" = day_du ]; then
    .venv/Scripts/python.exe -X utf8 "$N/chay_co_theo_doi.py" --ra "$R" --het-gio 3000 --cho-wer 20 \
       --env QT_QPA_PLATFORM=offscreen --env PYTHONPATH="$P" --env GHI_DAU_TAT="$R/ghi_dau_tat.txt" -- \
       .venv/Scripts/python.exe -X utf8 -X faulthandler -m pytest -p no:cacheprovider -p ghi_dau_tat -q -rfE \
       --junitxml="$R/junit.xml" > "$R/wrapper.txt" 2>&1
  else
    .venv/Scripts/python.exe -X utf8 "$N/chay_co_theo_doi.py" --ra "$R" --het-gio 3000 --cho-wer 20 \
       --env QT_QPA_PLATFORM=offscreen -- \
       .venv/Scripts/python.exe -X utf8 -m pytest -p no:cacheprovider --junitxml="$R/junit.xml" \
       > "$R/wrapper.txt" 2>&1
  fi
  rc=$?
  ma=$(grep -o '"ma_python": "[^"]*"' "$R/tom_tat.json" 2>/dev/null | cut -d'"' -f4)
  hg=$(grep -q '"HẾT GIỜ' "$R/tom_tat.json" 2>/dev/null && echo "; HẾT GIỜ")
  dau=$(tail -1 "$R/ghi_dau_tat.txt" 2>/dev/null | cut -c1-160)
  echo "$(date +%T) lượt $i: exit=$rc, mã python gốc ${ma:-?}$hg; dấu cuối: ${dau:-(không có plugin)}" \
    | tee -a "$OUT/ket_qua.txt"
done
echo "$(date +%T) xong; kết quả ở $OUT" | tee -a "$OUT/ket_qua.txt"
