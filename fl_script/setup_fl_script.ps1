# DAWMind FL Studio Script Setup
# Findet automatisch den richtigen FL Studio User Data Ordner
# und kopiert die Scripts dorthin.

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " DAWMind FL Studio Script Setup" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Mögliche Pfade für FL Studio User Data
$possiblePaths = @(
    "$env:USERPROFILE\Documents\Image-Line\FL Studio\Settings\Hardware",
    "$env:USERPROFILE\Documents\Image-Line Data\FL Studio\Settings\Hardware",
    "$env:USERPROFILE\OneDrive\Documents\Image-Line\FL Studio\Settings\Hardware",
    "$env:USERPROFILE\OneDrive\Dokumente\Image-Line\FL Studio\Settings\Hardware",
    "$env:USERPROFILE\Dokumente\Image-Line\FL Studio\Settings\Hardware"
)

$hardwarePath = $null

# Finde den richtigen Pfad
foreach ($path in $possiblePaths) {
    if (Test-Path $path) {
        $hardwarePath = $path
        Write-Host "[OK] Hardware-Ordner gefunden: $path" -ForegroundColor Green
        break
    }
}

if (-not $hardwarePath) {
    Write-Host "[WARNUNG] Kein Standard-Pfad gefunden." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Bitte oeffne FL Studio -> Options -> File Settings" -ForegroundColor Yellow
    Write-Host "und kopiere den 'User data folder' Pfad hierher:" -ForegroundColor Yellow
    $customPath = Read-Host "User data folder"
    $hardwarePath = Join-Path $customPath "FL Studio\Settings\Hardware"
    
    if (-not (Test-Path $hardwarePath)) {
        Write-Host "[FEHLER] Pfad existiert nicht: $hardwarePath" -ForegroundColor Red
        Write-Host "Erstelle Ordner..." -ForegroundColor Yellow
        New-Item -ItemType Directory -Path $hardwarePath -Force | Out-Null
    }
}

# DAWMind Ordner erstellen
$dawmindPath = Join-Path $hardwarePath "DAWMind"
if (-not (Test-Path $dawmindPath)) {
    New-Item -ItemType Directory -Path $dawmindPath -Force | Out-Null
    Write-Host "[OK] DAWMind Ordner erstellt: $dawmindPath" -ForegroundColor Green
} else {
    Write-Host "[OK] DAWMind Ordner existiert bereits: $dawmindPath" -ForegroundColor Green
}

# Script-Dateien finden (relativ zum Script-Speicherort)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$filesToCopy = @(
    "device_DAWMind.py",
    "device_DAWMind_minimal.py",
    "ipc_handler.py"
)

Write-Host ""
Write-Host "Kopiere Dateien..." -ForegroundColor Cyan

foreach ($file in $filesToCopy) {
    $source = Join-Path $scriptDir $file
    $dest = Join-Path $dawmindPath $file
    
    if (Test-Path $source) {
        Copy-Item $source $dest -Force
        Write-Host "  [OK] $file -> $dawmindPath" -ForegroundColor Green
    } else {
        Write-Host "  [SKIP] $file nicht gefunden in $scriptDir" -ForegroundColor Yellow
    }
}

# Verifiziere
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Verifikation" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

$mainScript = Join-Path $dawmindPath "device_DAWMind.py"
if (Test-Path $mainScript) {
    $firstLine = Get-Content $mainScript -First 1
    Write-Host "Erste Zeile von device_DAWMind.py: $firstLine" -ForegroundColor White
    
    if ($firstLine -eq "# name=DAWMind") {
        Write-Host "[OK] Name-Header korrekt!" -ForegroundColor Green
    } else {
        Write-Host "[WARNUNG] Erste Zeile sieht nicht korrekt aus!" -ForegroundColor Red
        Write-Host "  Erwartet: # name=DAWMind" -ForegroundColor Yellow
    }
    
    # Prüfe Encoding
    $bytes = [System.IO.File]::ReadAllBytes($mainScript)
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        Write-Host "[WARNUNG] Datei hat UTF-8 BOM! Das kann Probleme machen." -ForegroundColor Red
        Write-Host "  Loesung: In VS Code oeffnen -> Encoding: UTF-8 (ohne BOM) waehlen" -ForegroundColor Yellow
    } else {
        Write-Host "[OK] Kein BOM erkannt" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " NAECHSTE SCHRITTE:" -ForegroundColor Cyan
Write-Host " 1. FL Studio (neu)starten" -ForegroundColor White
Write-Host " 2. F10 -> MIDI Settings" -ForegroundColor White
Write-Host " 3. Controller type Dropdown oeffnen" -ForegroundColor White
Write-Host " 4. 'DAWMind (user)' sollte erscheinen" -ForegroundColor White
Write-Host " 5. Wenn nicht: VIEW -> Script output pruefen" -ForegroundColor White
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Read-Host "Druecke Enter zum Beenden"
