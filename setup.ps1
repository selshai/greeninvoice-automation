# -*- coding: utf-8 -*-
# הכנה והפעלה אוטומטית של אפליקציית הפקת הקבלות.
# מתקין Python (אם חסר), יוצר סביבה וירטואלית, מתקין ספריות, ומפעיל את השרת.
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location -Path $PSScriptRoot

$TOTAL = 4
function Show-Stage($num, $text) {
    $pct = [int]((($num - 1) / $TOTAL) * 100)
    Write-Progress -Id 0 -Activity "הכנה והפעלה" -Status "שלב $num/$TOTAL — $text" -PercentComplete $pct
    Write-Host ""
    Write-Host ("===== שלב {0}/{1} — {2} =====" -f $num, $TOTAL, $text) -ForegroundColor Cyan
}
function Fail($msg) {
    Write-Host ""
    Write-Host "[עצירה] $msg" -ForegroundColor Red
    Write-Progress -Id 0 -Activity "הכנה והפעלה" -Completed
    Read-Host "הקש Enter לסגירה"
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
Show-Stage 1 "בדיקת Python"
$python = Find-PythonExe
if ($python) {
    Write-Host "נמצא Python: $python" -ForegroundColor Green
} else {
    Write-Host "Python לא מותקן — מתחיל התקנה אוטומטית (ללא צורך בהרשאות מנהל)." -ForegroundColor Yellow

    # ניסיון 1: winget
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "מתקין באמצעות winget... (עשוי להימשך מספר דקות)"
        Write-Progress -Id 1 -ParentId 0 -Activity "התקנת Python" -Status "winget" -PercentComplete 30
        winget install -e --id Python.Python.3.12 --scope user --silent `
            --accept-package-agreements --accept-source-agreements | Out-Null
        Refresh-Path
        $python = Find-PythonExe
    }

    # ניסיון 2: הורדה ישירה מהאתר הרשמי
    if (-not $python) {
        $url = 'https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe'
        $out = Join-Path $env:TEMP 'python-3.12.4-amd64.exe'
        Write-Host "מוריד את מתקין Python מהאתר הרשמי..."
        try {
            Write-Progress -Id 1 -ParentId 0 -Activity "התקנת Python" -Status "מוריד..." -PercentComplete 40
            Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing
        } catch {
            Fail "הורדת Python נכשלה. בדוק חיבור אינטרנט או התקן ידנית מ- https://www.python.org/downloads/"
        }
        Write-Host "מריץ התקנה שקטה..."
        Write-Progress -Id 1 -ParentId 0 -Activity "התקנת Python" -Status "מתקין..." -PercentComplete 70
        Start-Process -FilePath $out -Wait -ArgumentList '/quiet', 'InstallAllUsers=0', 'PrependPath=1', 'Include_pip=1', 'Include_launcher=1'
        Refresh-Path
        $python = Find-PythonExe
    }

    Write-Progress -Id 1 -ParentId 0 -Activity "התקנת Python" -Completed
    if (-not $python) {
        Fail "התקנת Python האוטומטית לא הושלמה. התקן ידנית מ- https://www.python.org/downloads/ (סמן Add to PATH) והפעל שוב."
    }
    Write-Host "Python הותקן: $python" -ForegroundColor Green
}

# ===================== שלב 2: סביבה וירטואלית =====================
Show-Stage 2 "יצירת סביבה וירטואלית"
$venvPy = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    & $python -m venv .venv
    if (-not (Test-Path $venvPy)) { Fail "יצירת הסביבה הווירטואלית נכשלה." }
    Write-Host "הסביבה נוצרה." -ForegroundColor Green
} else {
    Write-Host "סביבה קיימת — מדלג." -ForegroundColor Green
}

# ===================== שלב 3: התקנת ספריות =====================
Show-Stage 3 "התקנת ספריות"
& $venvPy -m pip install --upgrade pip --quiet --disable-pip-version-check 2>$null
$reqs = @(Get-Content 'requirements.txt' | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith('#') })
$idx = 0
foreach ($pkg in $reqs) {
    $idx++
    $pct = [int](($idx / $reqs.Count) * 100)
    Write-Progress -Id 1 -ParentId 0 -Activity "התקנת ספריות" -Status "מתקין: $pkg" -PercentComplete $pct
    Write-Host ("  → {0}" -f $pkg)
    & $venvPy -m pip install $pkg --quiet --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { Fail "התקנת החבילה '$pkg' נכשלה." }
}
Write-Progress -Id 1 -ParentId 0 -Activity "התקנת ספריות" -Completed
Write-Host "כל הספריות הותקנו." -ForegroundColor Green

# יצירת .env אם חסר (המפתחות מוזנים דרך דף ההגדרות)
if (-not (Test-Path '.env')) {
    if (Test-Path '.env.example') { Copy-Item '.env.example' '.env' }
    else { '# מפתחות API — ניתן להזין דרך דף ההגדרות' | Out-File '.env' -Encoding utf8 }
}

# ===================== שלב 4: הפעלה =====================
Show-Stage 4 "הפעלת השרת ופתיחת הדפדפן"
Write-Progress -Id 0 -Activity "הכנה והפעלה" -Status "מוכן" -PercentComplete 100
Write-Host ""
Write-Host "השרת עולה בכתובת http://localhost:8501 — הדפדפן ייפתח אוטומטית." -ForegroundColor Green
Write-Host "לעצירה: סגור חלון זה או הקש Ctrl+C." -ForegroundColor DarkGray
Write-Progress -Id 0 -Activity "הכנה והפעלה" -Completed

& $venvPy -m streamlit run app.py
Read-Host "השרת נעצר. הקש Enter לסגירה"
