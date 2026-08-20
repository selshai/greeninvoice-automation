# -*- coding: utf-8 -*-
# הכנה והפעלה אוטומטית של אפליקציית הפקת הקבלות.
# מתקין Python (אם חסר), יוצר סביבה וירטואלית, מתקין ספריות, ומפעיל את השרת.
#
# הודעות הקונסולה באנגלית בכוונה: הטרמינל של Windows לא תומך בטקסט דו-כיווני
# (microsoft/terminal#538), ולכן עברית מוצגת בו הפוך. ממשק המשתמש עצמו בדפדפן ובעברית.
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location -Path $PSScriptRoot

$TOTAL = 4
function Show-Stage($num, $text) {
    $pct = [int]((($num - 1) / $TOTAL) * 100)
    Write-Progress -Id 0 -Activity "Setup and launch" -Status "Step $num/$TOTAL - $text" -PercentComplete $pct
    Write-Host ""
    Write-Host ("===== Step {0}/{1} - {2} =====" -f $num, $TOTAL, $text) -ForegroundColor Cyan
}
function Fail($msg) {
    Write-Host ""
    Write-Host "[STOPPED] $msg" -ForegroundColor Red
    Write-Progress -Id 0 -Activity "Setup and launch" -Completed
    Read-Host "Press Enter to close"
    exit 1
}

function Find-PythonExe {
    $c = Get-Command python -ErrorAction SilentlyContinue
    if ($c -and $c.Source -notlike '*WindowsApps*') { return $c.Source }
    $c = Get-Command py -ErrorAction SilentlyContinue
    if ($c) {
        try {
            $exe = (& py -3 -c "import sys; print(sys.executable)" 2>$null)
            if ($LASTEXITCODE -eq 0 -and $exe) { return $exe.Trim() }
        } catch {}
    }
    foreach ($base in @("$env:LocalAppData\Programs\Python", "$env:ProgramFiles\Python", "C:\Python312", "C:\Python311", "C:\Python310")) {
        if (Test-Path $base) {
            $f = Get-ChildItem $base -Filter python.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($f) { return $f.FullName }
        }
    }
    return $null
}

function Refresh-Path {
    $m = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $u = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = ($m, $u | Where-Object { $_ }) -join ';'
}

# ===================== שלב 1: Python =====================
Show-Stage 1 "Checking Python"
$python = Find-PythonExe
if ($python) {
    Write-Host "Python found: $python" -ForegroundColor Green
} else {
    Write-Host "Python is not installed - starting automatic installation (no admin rights needed)." -ForegroundColor Yellow

    # ניסיון 1: winget
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Installing via winget... (may take a few minutes)"
        Write-Progress -Id 1 -ParentId 0 -Activity "Installing Python" -Status "winget" -PercentComplete 30
        winget install -e --id Python.Python.3.12 --scope user --silent `
            --accept-package-agreements --accept-source-agreements | Out-Null
        Refresh-Path
        $python = Find-PythonExe
    }

    # ניסיון 2: הורדה ישירה מהאתר הרשמי
    if (-not $python) {
        $url = 'https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe'
        $out = Join-Path $env:TEMP 'python-3.12.4-amd64.exe'
        Write-Host "Downloading the Python installer from python.org..."
        try {
            Write-Progress -Id 1 -ParentId 0 -Activity "Installing Python" -Status "Downloading..." -PercentComplete 40
            Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing
        } catch {
            Fail "Python download failed. Check your internet connection, or install manually from https://www.python.org/downloads/"
        }
        Write-Host "Running silent installation..."
        Write-Progress -Id 1 -ParentId 0 -Activity "Installing Python" -Status "Installing..." -PercentComplete 70
        Start-Process -FilePath $out -Wait -ArgumentList '/quiet', 'InstallAllUsers=0', 'PrependPath=1', 'Include_pip=1', 'Include_launcher=1'
        Refresh-Path
        $python = Find-PythonExe
    }

    Write-Progress -Id 1 -ParentId 0 -Activity "Installing Python" -Completed
    if (-not $python) {
        Fail "Automatic Python installation did not complete. Install manually from https://www.python.org/downloads/ (check 'Add to PATH') and run again."
    }
    Write-Host "Python installed: $python" -ForegroundColor Green
}

# ===================== שלב 2: סביבה וירטואלית =====================
Show-Stage 2 "Creating virtual environment"
$venvPy = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    & $python -m venv .venv
    if (-not (Test-Path $venvPy)) { Fail "Failed to create the virtual environment." }
    Write-Host "Environment created." -ForegroundColor Green
} else {
    Write-Host "Environment already exists - skipping." -ForegroundColor Green
}

# ===================== שלב 3: התקנת ספריות =====================
Show-Stage 3 "Installing packages"
& $venvPy -m pip install --upgrade pip --quiet --disable-pip-version-check 2>$null
$reqs = @(Get-Content 'requirements.txt' | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith('#') })
$idx = 0
foreach ($pkg in $reqs) {
    $idx++
    $pct = [int](($idx / $reqs.Count) * 100)
    Write-Progress -Id 1 -ParentId 0 -Activity "Installing packages" -Status "Installing: $pkg" -PercentComplete $pct
    Write-Host ("  -> {0}" -f $pkg)
    & $venvPy -m pip install $pkg --quiet --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { Fail "Failed to install package '$pkg'." }
}
Write-Progress -Id 1 -ParentId 0 -Activity "Installing packages" -Completed
Write-Host "All packages installed." -ForegroundColor Green

# יצירת .env אם חסר (המפתחות מוזנים דרך דף ההגדרות)
if (-not (Test-Path '.env')) {
    if (Test-Path '.env.example') { Copy-Item '.env.example' '.env' }
    else { '# מפתחות API — ניתן להזין דרך דף ההגדרות' | Out-File '.env' -Encoding utf8 }
}

# ===================== שלב 4: הפעלה =====================
Show-Stage 4 "Starting the server and opening the browser"
Write-Progress -Id 0 -Activity "Setup and launch" -Status "Ready" -PercentComplete 100
Write-Host ""
Write-Host "Server starting at http://localhost:8501 - the browser will open automatically." -ForegroundColor Green
Write-Host "To stop: close this window or press Ctrl+C." -ForegroundColor DarkGray
Write-Progress -Id 0 -Activity "Setup and launch" -Completed

& $venvPy -m streamlit run app.py
Read-Host "Server stopped. Press Enter to close"
