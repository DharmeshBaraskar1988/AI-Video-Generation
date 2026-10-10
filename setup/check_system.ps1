# D-Storify POC - system check (Windows PowerShell 5.1+)
# Checks hardware, required software and network access. Changes nothing.
# Run:  double-click setup\check_system.bat   (or)   powershell -ExecutionPolicy Bypass -File setup\check_system.ps1

$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $PSScriptRoot
$report = @()
$problems = 0

function Add-Row($area, $item, $status, $detail) {
    $script:report += [pscustomobject]@{ Area = $area; Item = $item; Status = $status; Detail = $detail }
    if ($status -eq "MISSING" -or $status -eq "UPGRADE" -or $status -eq "BLOCKED") { $script:problems++ }
}

function Get-CmdVersion($cmd, $argList) {
    $c = Get-Command $cmd -ErrorAction SilentlyContinue
    if (-not $c) { return $null }
    $out = & $cmd $argList 2>&1 | Select-Object -First 1
    return ($out | Out-String).Trim()
}

function Get-Num($text) {
    if ($text -match '(\d+)\.(\d+)') { return [version]("{0}.{1}" -f $matches[1], $matches[2]) }
    return $null
}

Write-Host ""
Write-Host "D-Storify POC - checking this computer..." -ForegroundColor Cyan
Write-Host ""

# ---------- Hardware ----------
$os = Get-CimInstance Win32_OperatingSystem
$cs = Get-CimInstance Win32_ComputerSystem
$ramGB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
$drive = (Get-Item $root).PSDrive
$freeGB = [math]::Round($drive.Free / 1GB, 1)
$cores = (Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum

Add-Row "Hardware" "Windows" "OK" ("{0} ({1})" -f $os.Caption, $os.OSArchitecture)
if ($ramGB -ge 8) { Add-Row "Hardware" "Memory" "OK" "$ramGB GB" } else { Add-Row "Hardware" "Memory" "UPGRADE" "$ramGB GB (8 GB+ recommended for video rendering)" }
if ($freeGB -ge 10) { Add-Row "Hardware" "Free disk ($($drive.Name):)" "OK" "$freeGB GB" } else { Add-Row "Hardware" "Free disk ($($drive.Name):)" "UPGRADE" "$freeGB GB (10 GB+ needed)" }
Add-Row "Hardware" "CPU threads" "OK" "$cores"

# ---------- Software ----------
$wg = Get-CmdVersion "winget" @("--version")
if ($wg) { Add-Row "Software" "winget (installer)" "OK" $wg } else { Add-Row "Software" "winget (installer)" "MISSING" "Install 'App Installer' from Microsoft Store" }

$node = Get-CmdVersion "node" @("--version")
$nv = Get-Num $node
if (-not $node) { Add-Row "Software" "Node.js 20+" "MISSING" "install.ps1 will install Node.js LTS" }
elseif ($nv.Major -lt 20) { Add-Row "Software" "Node.js 20+" "UPGRADE" "$node found; install.ps1 will install LTS" }
else { Add-Row "Software" "Node.js 20+" "OK" $node }

$npm = Get-CmdVersion "npm" @("--version")
if ($npm) { Add-Row "Software" "npm" "OK" $npm } else { Add-Row "Software" "npm" "MISSING" "comes with Node.js" }

$py312 = $null
$pyl = Get-Command "py" -ErrorAction SilentlyContinue
if ($pyl) { $py312 = (& py -3.12 --version 2>&1 | Out-String).Trim(); if ($py312 -notmatch "Python 3\.12") { $py312 = $null } }
$py = Get-CmdVersion "python" @("--version")
$pv = Get-Num $py
if ($py312) { Add-Row "Software" "Python 3.12" "OK" "$py312 (via py launcher)" }
elseif ($py -and $pv -ge [version]"3.11" -and $pv -lt [version]"3.13") { Add-Row "Software" "Python 3.11/3.12" "OK" $py }
elseif ($py) { Add-Row "Software" "Python 3.12" "UPGRADE" "$py found; 3.12 recommended (AI libraries). install.ps1 adds 3.12 alongside" }
else { Add-Row "Software" "Python 3.12" "MISSING" "install.ps1 will install Python 3.12" }

$ff = Get-CmdVersion "ffmpeg" @("-version")
if ($ff) { Add-Row "Software" "FFmpeg" "OK" (($ff -split " ")[0..2] -join " ") } else { Add-Row "Software" "FFmpeg" "MISSING" "install.ps1 will install FFmpeg" }

$git = Get-CmdVersion "git" @("--version")
if ($git) { Add-Row "Software" "Git" "OK" $git } else { Add-Row "Software" "Git" "MISSING" "install.ps1 will install Git" }

$code = Get-Command "code" -ErrorAction SilentlyContinue
if ($code) { Add-Row "Software" "VS Code" "OK" "found" } else { Add-Row "Software" "VS Code" "INFO" "not on PATH (fine if installed)" }

$claude = Get-Command "claude" -ErrorAction SilentlyContinue
if ($claude) { Add-Row "Software" "Claude Code CLI" "OK" "found" } else { Add-Row "Software" "Claude Code CLI" "INFO" "not on PATH (fine if you use the VS Code extension)" }

# ---------- Network ----------
$hosts = [ordered]@{
    "npm packages"          = "https://registry.npmjs.org/"
    "Python packages"       = "https://pypi.org/simple/"
    "Embedding model (HF)"  = "https://huggingface.co/"
    "Gemini API"            = "https://generativelanguage.googleapis.com/"
    "Edge TTS voices"       = "https://speech.platform.bing.com/"
    "Stock prices (Yahoo)"  = "https://query1.finance.yahoo.com/"
    "Sample PDFs (IQ site)" = "https://www.iq.com.qa/"
}
foreach ($k in $hosts.Keys) {
    $code = $null
    try {
        $r = Invoke-WebRequest -Uri $hosts[$k] -Method Head -TimeoutSec 10 -UseBasicParsing -ErrorAction Stop
        $code = [int]$r.StatusCode
    } catch {
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
    }
    if ($code) { Add-Row "Network" $k "OK" "reachable (HTTP $code)" }
    else { Add-Row "Network" $k "BLOCKED" "cannot reach $($hosts[$k]) - check VPN/proxy/firewall" }
}

# ---------- Project files ----------
foreach ($f in @("CLAUDE.md", "backend\requirements.txt", "data\quarters\iqcd_2026.json", ".env.example")) {
    if (Test-Path (Join-Path $root $f)) { Add-Row "Project" $f "OK" "present" } else { Add-Row "Project" $f "MISSING" "unzip the full pack into one folder" }
}
if (Test-Path (Join-Path $root ".env")) { Add-Row "Project" ".env" "OK" "present" } else { Add-Row "Project" ".env" "INFO" "install.ps1 creates it and asks for your Gemini key" }

# ---------- Output ----------
$report | Format-Table -AutoSize | Out-String -Width 200 | Write-Host
$txt = Join-Path $PSScriptRoot "system_report.txt"
$report | Format-Table -AutoSize | Out-String -Width 200 | Set-Content -Path $txt -Encoding UTF8

if ($problems -eq 0) {
    Write-Host "All checks passed. Next: run setup\install.bat" -ForegroundColor Green
} else {
    Write-Host "$problems item(s) need attention. MISSING/UPGRADE software is handled by setup\install.bat." -ForegroundColor Yellow
    Write-Host "BLOCKED network items must be fixed first (VPN, proxy or firewall)." -ForegroundColor Yellow
}
Write-Host "Report saved to setup\system_report.txt"
