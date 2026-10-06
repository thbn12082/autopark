# Theo dõi mở rộng khi chạy dài (LD-1, bộ test đầy đủ) — Việc 8, viết 06/10/2026, thay cho theo_doi.ps1 của 02/10/2026.
# Mỗi -Khoang giây ghi:
#   <Ra>\he_thong.csv : chỗ trống MỌI ổ cố định, RAM trống, commit (đã dùng / giới hạn / %), pagefile, CPU toàn máy,
#                       GPU (nvidia-smi: tải, VRAM, nhiệt, công suất, P-state, xung SM, lý do hạ xung)
#   <Ra>\python.csv   : mọi tiến trình python/pythonw: PID, PID cha, WS, private, CPU giây, số luồng, số handle, giờ tạo,
#                       dòng lệnh (cắt 160 ký tự) — để biết tiến trình nào của ai (bài học 02/10: phiên khác giết nhầm)
#   <Ra>\gpu_app.csv  : tiến trình dùng GPU (nvidia-smi --query-compute-apps)
#   <Ra>\su_kien.txt  : tiến trình được canh (-CanhPid / -CanhPidFile) thoát lúc nào, MÃ THOÁT ĐẦY ĐỦ (hex) và nghĩa;
#                       tiến trình powershell/pwsh/taskkill/wmic/cmd đang sống có dòng lệnh chứa Stop-Process/Kill/taskkill;
#                       cuối cùng: sự kiện Application Error/WER/Hang và Display/nvlddmkm/Resource-Exhaustion/WHEA/Popup
#                       trong log Windows từ lúc bắt đầu.
# Bản trong repo (06/10/2026), sửa theo phản biện: dòng lệnh giết chỉ ghi đầy đủ khi nhắm PID đang canh (hay đã canh);
# lệnh giết python theo tên (có chữ python, không nhắm PID canh) chỉ ghi giờ và loại lệnh; lệnh giết khác chỉ ghi giờ;
# để su_kien.txt không chứa lệnh của dự án khác (bản trước ghi đủ cả lệnh có chữ python); sửa ghi chú về độ dài log
# 'Windows PowerShell'. Tệp phải giữ UTF-8 CÓ BOM.
# Riêng tư: python.csv và gpu_app.csv ghi dòng lệnh / tên MỌI tiến trình python, GPU trên máy (cả của dự án khác):
# để <Ra> ngoài git (runs/ hay thư mục tạm), không chép hai tệp này vào docs/evidence.
# Chỉ đọc hệ thống; không cần quyền quản trị; không mở thiết bị. Tải: vài truy vấn CIM + 2 lần nvidia-smi mỗi chu kỳ
# (≈ 0,3–0,6 s CPU một lõi mỗi 10 s, CHƯA ĐO kỹ).
# Giới hạn: tiến trình "giết" sống < 1 chu kỳ (PowerShell Stop-Process ≈ 0,2 s) thường bị lỡ trong danh sách tiến
# trình; log 'Windows PowerShell' (sự kiện 400) bắt được powershell.exe mở bằng dòng lệnh, nhưng KHÔNG thấy lệnh của
# công cụ PowerShell trong Claude Code (lệnh nằm trong biến môi trường), cũng không thấy taskkill hay kill gọi thẳng —
# khi đó tra bản ghi phiên Claude bằng tim_lenh_giet.py. Mã thoát chỉ đọc được nếu tiến trình được canh TRƯỚC khi nó
# thoát.
param(
  [string]$Ra = ".",
  [int]$Giay = 2400,
  [int]$Khoang = 10,
  [int[]]$CanhPid = @(),
  [string]$CanhPidFile = "",
  [switch]$DungKhiHetCanh
)
$ErrorActionPreference = "Continue"
New-Item -ItemType Directory -Force -Path $Ra | Out-Null
$fHT = Join-Path $Ra "he_thong.csv"; $fPy = Join-Path $Ra "python.csv"; $fGpu = Join-Path $Ra "gpu_app.csv"; $fSk = Join-Path $Ra "su_kien.txt"
$batDau = Get-Date
$nvsmi = (Get-Command nvidia-smi -ErrorAction SilentlyContinue)
$o = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3"
$dsO = @($o | ForEach-Object { $_.DeviceID.TrimEnd(':') })
$hdr = "thoi_gian,ram_trong_gb,commit_dung_gb,commit_gioi_han_gb,commit_pct,pagefile_dung_mb,cpu_may_pct," + (($dsO | ForEach-Object { "o_${_}_trong_gb" }) -join ",") + ",gpu_tai_pct,gpu_mem_tai_pct,vram_dung_mb,vram_tong_mb,gpu_nhiet_c,gpu_w,gpu_pstate,gpu_sm_mhz,gpu_ly_do_ha_xung"
if (-not (Test-Path $fHT)) { $hdr | Out-File -Encoding utf8 $fHT }
if (-not (Test-Path $fPy)) { "thoi_gian,pid,pid_cha,ws_mb,private_mb,cpu_s,so_luong,so_handle,gio_tao,dong_lenh" | Out-File -Encoding utf8 $fPy }
if (-not (Test-Path $fGpu)) { "thoi_gian,pid,ten,vram_mb" | Out-File -Encoding utf8 $fGpu }
function Ghi-SuKien([string]$s) { ("{0:yyyy-MM-dd HH:mm:ss.fff} {1}" -f (Get-Date), $s) | Out-File -Append -Encoding utf8 $fSk }
function Nghia-MaThoat([uint32]$m) {
  # so sánh theo chuỗi hex: trong PowerShell 5.1 hằng 0xC0000005 là Int32 ÂM, so với uint32 sẽ sai
  switch ('{0:X8}' -f $m) {
    '00000000' { "thoát bình thường" }
    '00000001' { "lỗi thường (Python có traceback; hoặc taskkill /F, Popen.kill())" }
    '00000002' { "lỗi dòng lệnh (argparse)" }
    '00000003' { "abort() kiểu cũ của CRT" }
    'FFFFFFFF' { "BỊ GIẾT bằng TerminateProcess(-1): Stop-Process -Force / .NET Process.Kill(); Git Bash báo 127" }
    'C0000005' { "ACCESS VIOLATION (Git Bash báo 139)" }
    'C0000409' { "fail-fast: __fastfail / abort() của UCRT / /GS (Git Bash báo 127)" }
    'C0000374' { "HEAP CORRUPTION (Git Bash báo 127)" }
    'C00000FD' { "STACK OVERFLOW (Git Bash báo 127)" }
    'C0000017' { "STATUS_NO_MEMORY (Git Bash báo 138)" }
    'C000012D' { "STATUS_COMMITMENT_LIMIT — hết commit (Git Bash báo 127)" }
    'C000007F' { "STATUS_DISK_FULL (Git Bash báo 127)" }
    'C000001D' { "ILLEGAL INSTRUCTION (Git Bash báo 132)" }
    'C000013A' { "Ctrl+C (Git Bash báo 130)" }
    'E06D7363' { "ngoại lệ C++ không bắt (Git Bash báo 127)" }
    'C06D007F' { "delay-load: không thấy hàm trong DLL (Git Bash báo 127)" }
    '40010004' { "DBG_TERMINATE_PROCESS (trình gỡ lỗi giết)" }
    default { if ([uint64]$m -ge [uint64]3221225472) { "NTSTATUS lỗi khác (Git Bash báo 127)" } else { "mã thường; Git Bash báo byte thấp = $($m -band 255)" } }
  }
}
$canh = @{}   # pid -> Process (đã mở handle)
$daCanh = @{} # mọi pid đã canh, kể cả đã thoát (để lọc dòng lệnh giết)
function Loai-LenhGiet([string]$s) {
  # 'pid': nhắm PID đang/đã canh -> ghi đủ dòng lệnh (chỉ loại này); 'python': có chữ python, không nhắm PID canh
  # (giết python theo tên hay theo cỡ) -> chỉ ghi giờ và loại lệnh; '': lệnh giết khác -> chỉ ghi giờ.
  foreach ($q in @($daCanh.Keys)) { if ($s -match "(?<!\d)$q(?!\d)") { return 'pid' } }
  if ($s -match 'python') { return 'python' }
  return ''
}
function Dong-Giet([string]$s) {
  # loại lệnh giết (Stop-Process, .Kill(, taskkill, Terminate…), không kèm phần còn lại của dòng lệnh
  return [regex]::Match($s, 'Stop-Process|\.Kill\(|taskkill|Terminate\w*', 'IgnoreCase').Value
}
function Them-Canh([int]$p) {
  if ($p -le 0 -or $canh.ContainsKey($p)) { return }
  try {
    $pr = [System.Diagnostics.Process]::GetProcessById($p); $null = $pr.Handle   # mở handle sớm để còn đọc ExitCode
    $canh[$p] = $pr; $daCanh[$p] = 1
    Ghi-SuKien ("canh pid {0} ({1}, tạo {2:HH:mm:ss})" -f $p, $pr.ProcessName, $pr.StartTime)
  } catch { Ghi-SuKien ("không canh được pid {0}: {1}" -f $p, $_.Exception.Message) }
}
foreach ($p in $CanhPid) { Them-Canh $p }
Ghi-SuKien ("bắt đầu theo dõi, {0} s, mỗi {1} s, ổ: {2}" -f $Giay, $Khoang, ($dsO -join " "))
$daThay = @{}
$ketThuc = $batDau.AddSeconds($Giay)
while ((Get-Date) -lt $ketThuc) {
  $t = Get-Date -Format "HH:mm:ss"
  if ($CanhPidFile -and (Test-Path $CanhPidFile)) {
    foreach ($dong in (Get-Content $CanhPidFile -ErrorAction SilentlyContinue)) { $n = 0; if ([int]::TryParse(($dong -split '[ ,;=]')[-1], [ref]$n)) { Them-Canh $n } }
  }
  try {
    $os = Get-CimInstance Win32_OperatingSystem
    $ramTrong = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
    $gh = [math]::Round($os.TotalVirtualMemorySize / 1MB, 2); $dung = [math]::Round(($os.TotalVirtualMemorySize - $os.FreeVirtualMemory) / 1MB, 2)
    $pct = if ($gh -gt 0) { [math]::Round(100 * $dung / $gh, 1) } else { "" }
    $pf = (Get-CimInstance Win32_PageFileUsage | Measure-Object -Property CurrentUsage -Sum).Sum
    $cpu = (Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'").PercentProcessorTime
    $oTrong = @(Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object { [math]::Round($_.FreeSpace / 1GB, 2) })
    $g = ",,,,,,,,"
    if ($nvsmi) {
      $q = & nvidia-smi --query-gpu=utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw,pstate,clocks.sm,clocks_event_reasons.active --format=csv,noheader,nounits 2>$null | Select-Object -First 1
      if ($q) { $g = ($q -split ',\s*') -join ',' }
      & nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits 2>$null | ForEach-Object {
        $c = $_ -split ',\s*'; if ($c.Count -ge 3) { "$t,$($c[0]),$([IO.Path]::GetFileName($c[1])),$($c[2])" | Out-File -Append -Encoding utf8 $fGpu } }
    }
    "$t,$ramTrong,$dung,$gh,$pct,$pf,$cpu," + ($oTrong -join ",") + ",$g" | Out-File -Append -Encoding utf8 $fHT
    foreach ($p in (Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'")) {
      $cl = ""; if ($p.CommandLine) { $cl = ($p.CommandLine -replace '"', "'" -replace ',', ';'); if ($cl.Length -gt 160) { $cl = $cl.Substring(0, 160) } }
      $cpuS = [math]::Round(($p.KernelModeTime + $p.UserModeTime) / 1e7, 1)
      "$t,$($p.ProcessId),$($p.ParentProcessId),$([math]::Round($p.WorkingSetSize/1MB)),$([math]::Round($p.PrivatePageCount/1MB)),$cpuS,$($p.ThreadCount),$($p.HandleCount),$($p.CreationDate.ToString('HH:mm:ss')),""$cl""" | Out-File -Append -Encoding utf8 $fPy
    }
    foreach ($k in (Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='pwsh.exe' OR Name='taskkill.exe' OR Name='wmic.exe' OR Name='cmd.exe'")) {
      if ($k.CommandLine -and $k.CommandLine -match 'Stop-Process|\.Kill\(|taskkill|Terminate' -and -not $daThay.ContainsKey($k.ProcessId) -and $k.CommandLine -notmatch 'theo_doi_mo_rong') {
        $daThay[$k.ProcessId] = 1
        $loai = Loai-LenhGiet $k.CommandLine
        if ($loai -eq 'pid') {
          Ghi-SuKien ("THẤY lệnh giết đang chạy: pid {0} cha {1} tạo {2:HH:mm:ss.fff}: {3}" -f $k.ProcessId, $k.ParentProcessId, $k.CreationDate, $k.CommandLine)
        } elseif ($loai -eq 'python') {
          Ghi-SuKien ("THẤY lệnh giết python theo tên đang chạy: pid {0} tạo {1:HH:mm:ss.fff} ({2}; không nhắm PID đang canh); dòng lệnh không ghi" -f $k.ProcessId, $k.CreationDate, (Dong-Giet $k.CommandLine))
        } else {
          Ghi-SuKien ("THẤY lệnh giết khác đang chạy: pid {0} tạo {1:HH:mm:ss.fff} (không nhắm PID đang canh hay python; không ghi dòng lệnh)" -f $k.ProcessId, $k.CreationDate)
        }
      }
    }
    # Log "Windows PowerShell" ghi sự kiện 400 (HostApplication = dòng lệnh) mỗi lần một powershell.exe khởi động, không
    # cần quyền quản trị; bắt được cả lệnh sống 0,2 s mà vòng hỏi tiến trình lỡ. Log là vòng 15 MB: giữ ≈ 15–33 phút
    # tùy máy bận (đo 06/10/2026), nên đọc mỗi chu kỳ. Lệnh của công cụ PowerShell trong Claude Code nằm trong biến
    # môi trường, không thấy ở đây.
    if (-not $script:psTu) { $script:psTu = $batDau }
    $psMoi = @(Get-WinEvent -FilterHashtable @{LogName='Windows PowerShell'; Id=400; StartTime=$script:psTu} -ErrorAction SilentlyContinue)
    $script:psTu = Get-Date
    foreach ($e in $psMoi) {
      $ha = ([regex]::Match($e.Message, 'HostApplication=([^\r\n]+)')).Groups[1].Value
      $em = [regex]::Match($ha, '-(?:e|ec|en|enc|encodedcommand)\s+([A-Za-z0-9+/=]{8,})', 'IgnoreCase')
      if ($em.Success) { try { $ha += "  [giải mã: " + [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($em.Groups[1].Value)) + "]" } catch { } }
      if ($ha -match 'Stop-Process|\.Kill\(|taskkill|Terminate' -and $ha -notmatch 'theo_doi_mo_rong') {
        $loai = Loai-LenhGiet $ha
        if ($loai -eq 'pid') {
          Ghi-SuKien ("LỆNH GIẾT (log Windows PowerShell, {0:HH:mm:ss.fff}): {1}" -f $e.TimeCreated, $(if ($ha.Length -gt 600) { $ha.Substring(0, 600) } else { $ha }))
        } elseif ($loai -eq 'python') {
          Ghi-SuKien ("lệnh giết python theo tên lúc {0:HH:mm:ss.fff} (log Windows PowerShell; {1}; không nhắm PID đang canh); dòng lệnh không ghi" -f $e.TimeCreated, (Dong-Giet $ha))
        } else {
          Ghi-SuKien ("lệnh giết khác (log Windows PowerShell, {0:HH:mm:ss.fff}): không nhắm PID đang canh hay python; không ghi dòng lệnh" -f $e.TimeCreated)
        }
      }
    }
  } catch { Ghi-SuKien ("lỗi chu kỳ: " + $_.Exception.Message) }
  foreach ($p in @($canh.Keys)) {
    $pr = $canh[$p]
    try {
      if ($pr.HasExited) {
        $m = [uint32]([int64]$pr.ExitCode -band [int64]4294967295)
        Ghi-SuKien ("pid {0} THOÁT lúc {1:HH:mm:ss.fff}, mã 0x{2:X8} ({3}) — {4}" -f $p, $pr.ExitTime, $m, [int]$pr.ExitCode, (Nghia-MaThoat $m))
        $canh.Remove($p)
      }
    } catch { Ghi-SuKien ("pid {0}: không đọc được mã thoát: {1}" -f $p, $_.Exception.Message); $canh.Remove($p) }
  }
  if ($DungKhiHetCanh -and $canh.Count -eq 0 -and ($CanhPid.Count -gt 0 -or ($CanhPidFile -and (Test-Path $CanhPidFile)))) { Start-Sleep -Seconds 15; break }
  Start-Sleep -Seconds $Khoang
}
# log Windows từ lúc bắt đầu (Application: lỗi ứng dụng/WER/treo; System: GPU, bộ nhớ ảo, phần cứng, popup)
try {
  $ev = @(Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='Application Error','Windows Error Reporting','Application Hang'; StartTime=$batDau} -ErrorAction SilentlyContinue)
  $ev += @(Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=$batDau} -ErrorAction SilentlyContinue | Where-Object { $_.ProviderName -match 'nvlddmkm|Display|Resource-Exhaustion|WHEA|Application Popup|Ntfs|disk|volmgr' })
  Ghi-SuKien ("log Windows từ {0:HH:mm:ss}: {1} sự kiện liên quan" -f $batDau, $ev.Count)
  foreach ($e in ($ev | Sort-Object TimeCreated)) { Ghi-SuKien ("  {0:HH:mm:ss} {1} id={2}: {3}" -f $e.TimeCreated, $e.ProviderName, $e.Id, (($e.Message -replace '\s+', ' ') -replace '^(.{0,300}).*', '$1')) }
} catch { Ghi-SuKien ("không đọc được log Windows: " + $_.Exception.Message) }
Ghi-SuKien "kết thúc theo dõi"
