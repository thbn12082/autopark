# Ghi mỗi 10 s: bộ nhớ của mọi tiến trình python (WorkingSet, PrivateMemory), chỗ trống ổ C và D, bộ nhớ cam kết còn trống.
param([string]$Out = "runs/thiet_bi_20261002/theo_doi.csv", [int]$Seconds = 2100)
"thoi_gian,python_pid,ws_mb,private_mb,c_trong_gb,d_trong_gb,commit_trong_gb" | Out-File -Encoding utf8 $Out
$end = (Get-Date).AddSeconds($Seconds)
while ((Get-Date) -lt $end) {
  $os = Get-CimInstance Win32_OperatingSystem
  $c = [math]::Round((Get-PSDrive C).Free/1GB,2); $d = [math]::Round((Get-PSDrive D).Free/1GB,2)
  $commit = [math]::Round($os.FreeVirtualMemory/1MB,2)
  $t = Get-Date -Format "HH:mm:ss"
  $ps = Get-Process python -ErrorAction SilentlyContinue
  if (-not $ps) { "$t,,,,$c,$d,$commit" | Out-File -Append -Encoding utf8 $Out }
  foreach ($p in $ps) { "$t,$($p.Id),$([math]::Round($p.WorkingSet64/1MB)),$([math]::Round($p.PrivateMemorySize64/1MB)),$c,$d,$commit" | Out-File -Append -Encoding utf8 $Out }
  Start-Sleep -Seconds 10
}
