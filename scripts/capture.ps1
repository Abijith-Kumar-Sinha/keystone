# Headless Chrome screenshot. Usage: scripts\capture.ps1 -Url http://127.0.0.1:8000/ -Out .impeccable\review\hero-repro.png -W 1536 -H 864 [-Motion]
# Default forces prefers-reduced-motion so the page is captured in its settled state.
param([string]$Url = "http://127.0.0.1:8000/", [string]$Out = ".impeccable\review\hero-repro.png", [int]$W = 1536, [int]$H = 864, [switch]$Motion, [int]$Budget = 5000)
$chrome = @("C:\Program Files\Google\Chrome\Application\chrome.exe", "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
$abs = [System.IO.Path]::GetFullPath((Join-Path (Get-Location).Path $Out))
New-Item -ItemType Directory -Force -Path (Split-Path $abs) | Out-Null
if (Test-Path $abs) { [System.IO.File]::Delete($abs) }
$ud = Join-Path $env:TEMP ("keystone-chrome-" + [guid]::NewGuid().ToString("N").Substring(0, 8))   # fresh profile: no stale cached JS/CSS between captures
New-Item -ItemType Directory -Force -Path $ud | Out-Null
$a = @("--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--window-size=$W,$H", "--virtual-time-budget=$Budget", "--user-data-dir=`"$ud`"", "--screenshot=`"$abs`"")
if (-not $Motion) { $a += "--force-prefers-reduced-motion" }
$a += $Url
$p = Start-Process -FilePath $chrome -ArgumentList $a -PassThru -Wait -WindowStyle Hidden
if (Test-Path $abs) { "captured $Out ($W x $H, exit $($p.ExitCode))" } else { "capture FAILED (exit $($p.ExitCode))" }
