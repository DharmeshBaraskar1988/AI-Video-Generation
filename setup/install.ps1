# D-Storify POC - installer (Windows PowerShell 5.1+)
# Installs free prerequisites, the Python environment, the embedding model,
# tests the English + Qatari Arabic voices, downloads sample PDFs and writes .env.
# Safe to run again: it skips anything already done.
# Run:  double-click setup\install.bat

param(
    [switch]$SkipPrereqs,   # skip winget installs (Node, Python, FFmpeg, Git)
    [switch]$SkipModel,     # skip pre-downloading the embedding model
    [switch]$SkipVoiceTest
)

# Continue (not Stop): in Windows PowerShell 5.1, Stop turns harmless stderr output
# from pip / edge-tts into fatal errors. Failures are checked explicitly instead.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($n, $text) { Write-Host ""; Write-Host "[$n] $text" -ForegroundColor Cyan }
function Ok($text) { Write-Host "    OK  $text" -ForegroundColor Green }
function Warn($text) { Write-Host "    !!  $text" -ForegroundColor Yellow }
function Has($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
function Winget-Install($id, $name) {
    Write-Host "    installing $name ($id)..."
    winget install --id $id -e --silent --accept-source-agreements --accept-package-agreements | Out-Host
    Refresh-Path
}

Write-Host "D-Storify POC installer" -ForegroundColor Cyan
Write-Host "Project folder: $root"

# ---------- 1. Prerequisites ----------
Step 1 "Free prerequisites (Node.js LTS, Python 3.12, FFmpeg, Git)"
if ($SkipPrereqs) { Warn "skipped (-SkipPrereqs)" }
elseif (-not (Has "winget")) { Warn "winget not found. Install 'App Installer' from Microsoft Store, or install Node.js, Python 3.12, FFmpeg and Git manually, then rerun." }
else {
    $nodeOk = $false
    if (Has "node") { $v = (node --version) -replace "v", ""; if ([int]($v.Split(".")[0]) -ge 20) { $nodeOk = $true } }
    if ($nodeOk) { Ok "Node.js $(node --version)" } else { Winget-Install "OpenJS.NodeJS.LTS" "Node.js LTS" }

    $pyOk = $false
    if (Has "py") { $o = (& py -3.12 --version 2>&1 | Out-String); if ($o -match "Python 3\.12") { $pyOk = $true } }
    if ($pyOk) { Ok "Python 3.12 (py launcher)" } else { Winget-Install "Python.Python.3.12" "Python 3.12" }

    if (Has "ffmpeg") { Ok "FFmpeg" } else { Winget-Install "Gyan.FFmpeg" "FFmpeg" }
    if (Has "git") { Ok "Git" } else { Winget-Install "Git.Git" "Git" }
}
Refresh-Path

# pick a Python 3.12 interpreter
$py = $null
if (Has "py") { $o = (& py -3.12 --version 2>&1 | Out-String); if ($o -match "Python 3\.12") { $py = @("py", "-3.12") } }
if (-not $py -and (Has "python")) { $o = (& python --version 2>&1 | Out-String); if ($o -match "Python 3\.1[12]") { $py = @("python") } }
if (-not $py) { Warn "Python 3.12 not found on PATH yet. Close this window, open a new one and run install.bat again."; exit 1 }
Ok ("using " + ($py -join " "))

# ---------- 2. Python environment ----------
Step 2 "Python environment (backend\.venv) and AI libraries"
$venvPy = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    if ($py.Count -gt 1) { & $py[0] $py[1] -m venv backend\.venv } else { & $py[0] -m venv backend\.venv }
}
& $venvPy -m pip install --upgrade pip --quiet
Write-Host "    installing packages from backend\requirements.txt (first run takes 5-10 minutes)..."
& $venvPy -m pip install -r backend\requirements.txt
if ($LASTEXITCODE -ne 0) { Warn "pip reported an error. Scroll up for the failing package, then rerun."; exit 1 }
Ok "Python packages installed"

# ---------- 3. .env and Gemini ----------
Step 3 "Settings file (.env) and Gemini API key"
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env"; Ok "created .env from .env.example" } else { Ok ".env already exists" }
$envText = Get-Content ".env" -Raw
if ($envText -match "GEMINI_API_KEY=\s*(\r?\n|$)") {
    Write-Host "    Get a free key at https://aistudio.google.com/apikey"
    $key = Read-Host "    Paste your Gemini API key (or press Enter to add it later)"
    if ($key) {
        $envText = $envText -replace "GEMINI_API_KEY=.*", ("GEMINI_API_KEY=" + $key.Trim())
        Set-Content ".env" $envText -NoNewline -Encoding UTF8
        Ok "key saved to .env"
    } else { Warn "no key yet - add GEMINI_API_KEY to .env before step 3 of the build" }
}
& $venvPy setup\pick_gemini_model.py
if ($LASTEXITCODE -ne 0) { Warn "Gemini check did not pass (see message above). You can rerun: backend\.venv\Scripts\python setup\pick_gemini_model.py" }

# ---------- 4. Embedding model ----------
Step 4 "Embedding model (sentence-transformers, multilingual, ~470 MB, one time)"
if ($SkipModel) { Warn "skipped (-SkipModel)" }
else {
    & $venvPy -c "from sentence_transformers import SentenceTransformer as S; m=S('intfloat/multilingual-e5-small'); v=m.encode(['passage: test']); print('    vector size', v.shape[1])"
    if ($LASTEXITCODE -eq 0) { Ok "embedding model ready (cached in your user folder)" } else { Warn "model download failed; it will retry on first use" }
}

# ---------- 5. Voice test ----------
Step 5 "Voice test: English + Qatari Arabic (Edge TTS, free)"
if ($SkipVoiceTest) { Warn "skipped (-SkipVoiceTest)" }
else {
    $vt = Join-Path $root "outputs\voice_test"
    New-Item -ItemType Directory -Force -Path $vt | Out-Null
    $edge = Join-Path $root "backend\.venv\Scripts\edge-tts.exe"
    $tests = @(
        @{ voice = "en-US-GuyNeural";   file = "en_guy" ;  text = "setup\voice_test_en.txt" },
        @{ voice = "en-GB-SoniaNeural"; file = "en_sonia"; text = "setup\voice_test_en.txt" },
        @{ voice = "ar-QA-MoazNeural";  file = "ar_moaz" ; text = "setup\voice_test_ar.txt" },
        @{ voice = "ar-QA-AmalNeural";  file = "ar_amal" ; text = "setup\voice_test_ar.txt" }
    )
    foreach ($t in $tests) {
        $mp3 = Join-Path $vt ($t.file + ".mp3"); $vtt = Join-Path $vt ($t.file + ".vtt")
        & $edge --voice $t.voice --file $t.text --write-media $mp3 --write-subtitles $vtt 2>&1 | Out-Null
        if ((Test-Path $mp3) -and ((Get-Item $mp3).Length -gt 1000)) { Ok "$($t.voice) -> outputs\voice_test\$($t.file).mp3" }
        else { Warn "$($t.voice) failed (voice name may have changed). List voices with: backend\.venv\Scripts\edge-tts --list-voices" }
    }
}

# ---------- 6. Sample documents ----------
Step 6 "Sample results PDFs (Industries Qatar 2026, demo data for RAG)"
$docs = Join-Path $root "data\documents"
New-Item -ItemType Directory -Force -Path $docs | Out-Null
$pdfs = [ordered]@{
    "iq_financial_statements_h1_2026.pdf" = "https://www.iq.com.qa/media/4zsjkey5/iq-financial-statements-h1-2026-english.pdf"
    "iq_financial_statements_q1_2026.pdf" = "https://www.iq.com.qa/media/eyihh2yi/iq-financial-statements-march-2026-english.pdf"
    "iq_investor_presentation_h1_2026.pdf" = "https://www.iq.com.qa/media/k1fm0m3u/iq-ir-presentation-h1-2026-english.pdf"
}
foreach ($name in $pdfs.Keys) {
    $dest = Join-Path $docs $name
    if (Test-Path $dest) { Ok "$name already downloaded"; continue }
    try {
        Invoke-WebRequest -Uri $pdfs[$name] -OutFile $dest -UseBasicParsing -UserAgent "Mozilla/5.0" -TimeoutSec 120
        Ok "$name"
    } catch { Warn "could not download $name - open the link in a browser and save it to data\documents: $($pdfs[$name])" }
}

# ---------- 7. Folders ----------
Step 7 "Output folders"
foreach ($d in @("outputs\audio", "outputs\videos", "outputs\scripts", "backend\app\store", "data\music")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $root $d) | Out-Null
}
Ok "outputs\, backend\app\store\, data\music\ ready"

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "  1. Listen to outputs\voice_test\*.mp3 and pick your voices."
Write-Host "  2. Put 1-2 royalty-free music tracks (mp3) in data\music\."
Write-Host "  3. Open this folder in VS Code, start Claude Code, and follow docs\BUILD_STEPS.md from Step 1."
Write-Host "     (Frontend and video npm packages are installed by Claude Code in Steps 1 and 6.)"
