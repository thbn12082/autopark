Hai kiểu thoát bất thường: điều tra 06/10/2026 (Việc 8, đợt 3; máy bàn; kiểm trên máy tính, không dùng thiết bị)
Tài liệu: autopark/docs/CHUYEN_MAY_BAN.md mục 16. Người dùng giao 06/10/2026 ('làm đi'), theo đề xuất.

Kết luận ngắn
(a) LD-1 lần 1 (02/10/2026 14:11–14:29, rig.bench 30 phút, Git Bash ghi exit=127 ở t ≈ 1050 s): tiến trình bị một phiên
    tác tử Claude khác trên cùng máy (dự án khác) dừng bằng Stop-Process -Force. Mức bằng chứng: kiểm trên máy tính.
    - Lệnh powershell -NoProfile -Command "Stop-Process -Id 26456 -Force -ErrorAction SilentlyContinue" có trong bản ghi
      phiên kia lúc 14:29:12,569 (tìm lại bằng tim_lenh_giet.py --pid, kiem_cong_cu.txt mục 3); khung ảnh cuối của bốn
      camera 14:29:13,24–13,26, không có khung kế; chay.sh ghi exit=127 lúc 14:29:14.
    - PID 26456 là python gốc của rig.bench theo LOẠI TRỪ trên hai bảng tiến trình mà phiên kia in lúc 14:25:20 và
      14:29:06 (phía autopark không ghi PID): ở cả hai bảng 26456 là python duy nhất ≥ 1 GB (1552 và 1554 MB; 1469,4 s
      CPU lúc 14:29:06). 33860 có 4 MB ở cả hai bảng; bảng 14:25:20 không có cột CPU và còn 17016 = 8 MB; ở bảng
      14:29:06, 33860 là tiến trình duy nhất có 0 s CPU (17016 có 174,6 s CPU nên không phải trình khởi chạy venv).
    - Stop-Process -Force cho mã 0xFFFFFFFF, Git Bash báo 127 (tái hiện 3/3, thu_stop_process_ket_qua.txt). Câu "127 là
      byte thấp của mã thoát Windows" trong tài liệu cũ là SAI; giả thuyết STATUS_DISK_FULL bị bác.
(b) Tiến trình pytest .venv thoát 0xC0000005 (vi phạm truy cập) sau khi chạy hết test: 02/10/2026 19:00–19:10 (Git Bash
    139, cây gộp đợt 2) và 06/10/2026 14:46–14:57 (lượt .venv trên commit 470abb3, JUnit đủ 2115 test, 0 hỏng). Thủ phạm
    CHƯA RÕ.
    - Theo đếm của phản biện: .venv 2/9 lượt đầy đủ, .venv-train 0/6. Hai venv cùng PySide6, OpenCV, numpy, pytest
      nhưng không chỉ khác torch (importlib.metadata, 06/10/2026: .venv 31 gói, .venv-train 39): .venv-train thêm
      torch/torchvision, onnx/onnxruntime, psutil, nvidia-ml-py, pillow, sympy …, .venv có coverage, gdown, requests,
      tqdm … mà .venv-train không có; .venv-train chạy thêm 54 test (2169 so với 2115 trên commit 470abb3).
    - 3 lượt chạy lại có theo dõi 06/10/2026 15:47–16:20 (pytest_lap/): 3/3 thoát 0.
    - Lượt 02/10: chết sau khi plugin faulthandler của pytest đã tắt faulthandler trong pytest_unconfigure (suy luận có
      căn cứ: tệp đầu ra không có "Windows fatal exception"; sau đó còn hai lần gc.collect() toàn phần, rồi pha tắt của
      Python). Lượt 06/10 14:46: chỉ biết chết sau khi đã ghi JUnit (stderr bị bỏ). Không có dump vì cả hai lượt mở từ
      Git Bash.
Chung (kiểm trên máy tính):
    - Git Bash đổi mọi mã ≥ 0xC0000000 thành 127, trừ 0xC0000005 -> 139, 0xC0000017 -> 138, 0xC000001D -> 132,
      0xC000013A -> 130 (47 mã đo bằng ExitProcess, mỗi mã qua ba đường).
    - Tiến trình mở từ Git Bash mang ErrorMode 0x3 (SEM_NOGPFAULTERRORBOX): crash không có sự kiện Windows Error
      Reporting (WER) hay minidump, nên log Application trống không loại được một crash (ErrorMode không ảnh hưởng log
      System). Mở từ PowerShell, hay qua chay_co_theo_doi.py, thì ErrorMode 0x8001 và WER ghi được (LocalDumps đã bật
      trên máy bàn: %LOCALAPPDATA%\CrashDumps, DumpCount 10). Bị dừng từ ngoài (TerminateProcess) thì không có sự kiện
      WER, kể cả với ErrorMode 0x8001 (thu_dau_cuoi/: mã 0xFFFFFFFF, 0 sự kiện).

Tệp
- Bảng mã: bang_ma_thoat.sh + thoat_ma.py -> bang_ma_thoat_ket_qua.txt (27 mã qua ba đường: python gốc, trình khởi chạy
  venv, timeout + trình khởi chạy venv), bang_ma_thoat_bo_sung.txt (20 mã; bản đầu 15:33 chỉ đo qua python gốc, đo lại
  qua đủ ba đường lúc 18:27 bằng "bang_ma_thoat.sh bo_sung", cùng kết quả ở cả ba đường).
- Stop-Process: thu_stop_process.sh + con_ngu.py -> thu_stop_process_ket_qua.txt (bash $? 127 ba lần, mã đầy đủ của
  trình khởi chạy 0xFFFFFFFF, độ trễ 0,175–0,193 s từ lúc gọi powershell tới lần ghi cuối của tiến trình bị dừng).
- Thử đầu–cuối bộ theo dõi (bản nháp, 06/10/2026 15:29): thu_dau_cuoi.sh -> thu_dau_cuoi/ (dau_ra.txt, pids.txt,
  tom_tat.json, lenh_giet.txt, theo_doi/su_kien.txt). python.csv và gpu_app.csv của lần đó không chép: có dòng lệnh của
  dự án khác.
- Lượt chạy lại có theo dõi (06/10/2026 15:47–16:20, mã như commit 470abb3, .venv, bản nháp của lap_pytest.sh: wrapper,
  -X faulthandler, plugin ghi_dau_tat, -q -rfE, -o faulthandler_timeout=300): pytest_lap/ket_qua.txt và lan_1..3/
  (tom_tat.json, ghi_dau_tat.txt, junit.xml). Không chép dau_ra.txt: bản nháp ghi đè đầu ra của wrapper lên đầu ra của
  pytest (đã sửa: wrapper.txt). Tệp .faulthandler.txt của cả ba lượt rỗng.
- Thí nghiệm thứ tự tắt của người phản biện: thu_thu_tu/ (conftest.py ghi faulthandler.is_enabled() mỗi lần gc bắt đầu
  sau pytest_sessionfinish; ket_qua_khong_X.txt: False ở cả hai lần gc.collect() trong pytest_unconfigure và cleanup;
  ket_qua_co_X.txt: True khi có -X faulthandler). Chạy trong thu_thu_tu/: <python .venv> -X utf8 [-X faulthandler] -m
  pytest -p no:cacheprovider -q test_trivial.py; chạy lại 06/10/2026 ≈ 17:35 cho đầu ra giống hệt hai tệp kết quả.
- Công cụ (bản trong repo, sửa theo phản biện so với bản nháp đã dùng cho các kết quả trên):
  chay_co_theo_doi.py  chạy một lệnh dài với ErrorMode 0x8001; ghi PID (pids.txt), đầu ra (dau_ra.txt), mã 32 bit (hex,
                       nghĩa, "$? Git Bash sẽ báo"); --het-gio S (quá hạn thì taskkill /T /F cả cây, ghi "HẾT GIỜ");
                       chép dump mới vào <ra>/dump/; sự kiện và báo cáo WER mới (ReportArchive, ReportQueue); khi mã
                       ≥ 0xC0000000 thì tìm lệnh giết nhắm PID của mình (tim_lenh_giet.py --pid); --theo-doi chạy
                       theo_doi_mo_rong.ps1; tự thoát bằng đúng mã của lệnh.
  theo_doi_mo_rong.ps1 mỗi --khoang giây: ổ trống, RAM, commit, CPU, GPU (he_thong.csv), mọi tiến trình python
                       (python.csv), tiến trình dùng GPU (gpu_app.csv), PID được canh thoát lúc nào và mã gì, lệnh giết
                       thấy được (su_kien.txt; chỉ ghi đủ dòng lệnh khi nhắm PID đang canh; lệnh giết python theo tên
                       chỉ ghi giờ và loại lệnh, lệnh giết khác chỉ ghi giờ), cuối cùng là sự kiện lỗi trong log
                       Windows. Phải giữ UTF-8 CÓ BOM (PowerShell 5.1).
  ghi_dau_tat.py       plugin pytest ghi dấu các pha tắt (đọc dấu cuối: xem docstring); GHI_DAU_TAT_DEM_WIDGET=0 tắt
                       đếm widget Qt (đếm làm đổi điều kiện), =phien_xong chỉ đếm ở cuối phiên.
  lap_pytest.sh        lặp bộ test .venv qua wrapper, hạn giờ 3000 s mỗi lượt; chế độ day_du (như 3 lượt ở trên, bỏ
                       faulthandler_timeout) hay chi_wrapper (không -X faulthandler, không plugin: đúng điều kiện hai
                       lần crash, vẫn có minidump).
  chay_tren_commit.py  bản mới của script "chạy lại trên commit" (bản cũ: cong_cu_20261002/chay_tren_commit.py, giữ
                       nguyên): ErrorMode 0x8001, pytest với -X faulthandler, đầu ra từng lượt ra tệp *.dau_ra.txt, mã
                       hex kèm nghĩa, dump mới chép sang runs/dump/…, hạn giờ, ghi HEAD và độ sạch của cây;
                       --chi-test <test> để kiểm script trong vài giây.
  doc_minidump.py      đọc minidump không cần WinDbg: mã, module + offset, luồng, quét ngăn xếp, module nạp và đã gỡ.
                       Kết quả trên dump python ngày 02/10/2026 00:27 (một kiểu crash khác, của tiến trình con trong
                       test ecoqos_gui): doc_minidump_28980.txt.
  tim_lenh_giet.py     tìm lệnh giết tiến trình trong bản ghi phiên Claude Code trên máy, theo khoảng giờ UTC; --pid chỉ
                       in nguyên câu lệnh nhắm PID đó, lệnh giết python theo tên chỉ in giờ và loại lệnh ("lệnh giết
                       python theo tên (…); dòng lệnh không ghi"). KHÔNG có --pid thì in cả lệnh của dự án khác: đừng
                       chép kết quả đó vào repo.
  kiem_job.py          in ErrorMode, job object (LimitFlags), tiến trình cha của chính nó; kết quả kiem_job_ket_qua.txt:
                       mở từ Git Bash (kể cả qua timeout) 0x3, qua wrapper hay từ PowerShell 0x8001. Bản trong repo sửa
                       dòng IsProcessInJob (bản nháp in False sai vì không khai báo kiểu handle).
  kiem_atexit.py       liệt kê hàm atexit / threading._register_atexit mà các gói đăng ký trong .venv; kết quả
                       kiem_atexit_ket_qua.txt (logging.shutdown, PySide6.QtCore.__moduleShutdown,
                       multiprocessing.util._exit_function; _python_exit của concurrent.futures process và thread).
  ngu_roi_thoat.py, thoat_ma.py, con_ngu.py, test_nho_ghi_dau.py: tiến trình và test vô hại dùng khi thử công cụ.
- kiem_cong_cu.txt: kiểm nhỏ các công cụ bản trong repo (06/10/2026 17:28–17:34; mục 9: kiểm lại sau khi sửa
  tim_lenh_giet.py, theo_doi_mo_rong.ps1 và bang_ma_thoat.sh, 18:27–18:41, gồm một lần thử đầu–cuối).

Cách chạy lại (Git Bash, trong thư mục autopark của repo; E=docs/evidence/su_co_thoat_20261006)
- Bảng mã: bash $E/bang_ma_thoat.sh        (≈ 10 s; python gốc lấy theo %LOCALAPPDATA%; thêm tham số bo_sung cho 20 mã
  của bang_ma_thoat_bo_sung.txt)
- Stop-Process: bash $E/thu_stop_process.sh
- Thử đầu–cuối: bash $E/thu_dau_cuoi.sh [thư mục kết quả mới]      (≈ 40 s)
- Lặp bộ test .venv (NẶNG CPU, ≈ 10–12 phút mỗi lượt; chỉ khi máy rảnh; sao lưu %LOCALAPPDATA%\CrashDumps trước):
    bash $E/lap_pytest.sh 5 runs/su_co_thoat/<ngày> chi_wrapper
  Đọc: <ra>/ket_qua.txt; lan_i/tom_tat.json ("ma_python", "dump_moi_da_chep"); có dump thì
    .venv/Scripts/python.exe -X utf8 $E/doc_minidump.py <ra>/lan_i/dump/python.exe.<pid>.dmp
- Lệnh dài bất kỳ (LD-1 …): .venv/Scripts/python.exe -X utf8 $E/chay_co_theo_doi.py --ra runs/<…> --het-gio <S>
    --theo-doi -- <lệnh>    (lệnh LD-1: autopark/docs/VIEC_TAI_CHO_THIET_BI.md việc 1 bước 5)
- Chạy lại trên commit: .venv/Scripts/python.exe -X utf8 $E/chay_tren_commit.py <commit> docs/evidence/<đợt>
  (kiểm script: thêm --chi-test tests/test_geometry.py và một thư mục tạm).

Riêng tư
- Trong repo chỉ ghi "một phiên tác tử Claude khác trên cùng máy (dự án khác)". Bản trích bản ghi phiên kia và danh sách
  lệnh giết của mọi dự án nằm ngoài repo (thư mục nháp của phiên điều tra), không chép vào đây.
- Đường dẫn hồ sơ người dùng và thư mục nháp trong các tệp chép vào đây đã thay bằng %USERPROFILE% hay <nháp>. Tìm tên
  người dùng trong junit.xml sẽ khớp vài tên test của repo (chữ "nguyên" viết không dấu trong tên hàm), không phải
  đường dẫn.
- Để <ra> của wrapper ngoài git (runs/ hay thư mục tạm): dau_ra.txt, dump/, lenh_giet.txt, theo_doi/python.csv và
  theo_doi/gpu_app.csv có thể chứa đường dẫn riêng của máy hay dòng lệnh, tên của tiến trình khác; KHÔNG chép
  lenh_giet.txt, python.csv, gpu_app.csv vào docs/evidence; dump chứa bộ nhớ tiến trình, không commit.

Giới hạn
- (a) dựa trên bản ghi phiên Claude của dự án khác và dấu thời gian tệp; không có log kiểm toán của hệ điều hành
  (Security 4689 cần quyền quản trị; log 'Windows PowerShell' là vòng 15 MB, giữ ≈ 15–33 phút). PID khớp theo loại trừ.
- (b) chưa tái hiện; các lượt có theo dõi đổi điều kiện (-X faulthandler, plugin đếm 47 028 widget ngay trước pha tắt).
  Chế độ chi_wrapper CHƯA CHẠY. (Cập nhật 06/10/2026: đã chạy 6 lượt lúc 17:53–18:56, 0/6 tái hiện; lượt 1 hỏng một
  test bo ảo vì QEMU tự crash và WER giữ tiến trình QEMU lúc ghi dump; kết quả đã lọc ở chi_wrapper_20261006/;
  CHUYEN_MAY_BAN.md mục 16.6.)
- Với ErrorMode 0x8001, WER ghi cả các lần QEMU crash trong test (lượt 3: 16:12:03, chưa tới 1,3 s sau khi QEMU khởi
  động theo giờ khởi động trong sự kiện; có lẽ espressif/qemu#175, suy luận); mỗi dump mới làm WER xóa dump cũ nhất
  khi thư mục đã có 10. Kiểm được: bản sao lưu lúc 15:46 ngày 06/10/2026 có đủ 10 dump trước đó
  (runs/crashdumps_sao_luu_20261006/, git bỏ qua); lúc 17:31 CrashDumps còn 9 tệp (kiem_cong_cu.txt mục 6); lúc 18:31
  có 10 tệp, dump qemu 30/09/2026 10:23 không còn, thêm một dump qemu 06/10/2026 17:55:30. Dump 30/09 mất lúc nào và
  vì sao: CHƯA RÕ.
- Bộ theo dõi không thấy lệnh do công cụ PowerShell của Claude Code chạy (lệnh nằm trong biến môi trường), cũng không
  thấy taskkill hay kill gọi thẳng; tim_lenh_giet.py chỉ thấy lệnh do phiên Claude Code chạy. Tải CPU của bộ theo dõi
  CHƯA ĐO.
