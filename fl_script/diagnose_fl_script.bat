@echo off
echo ============================================
echo  DAWMind FL Studio Script Diagnose-Tool
echo ============================================
echo.

REM Check standard user data folder
set "DEFAULT_PATH=%USERPROFILE%\Documents\Image-Line\FL Studio\Settings\Hardware"
set "ALT_PATH1=%USERPROFILE%\Documents\Image-Line Data\FL Studio\Settings\Hardware"

echo [1] Pruefe Standard-Pfade...
echo.

if exist "%DEFAULT_PATH%" (
    echo    GEFUNDEN: %DEFAULT_PATH%
    echo    Inhalt:
    dir /b /ad "%DEFAULT_PATH%" 2>nul
    echo.
    
    if exist "%DEFAULT_PATH%\DAWMind" (
        echo    [OK] DAWMind Ordner existiert
        echo    Dateien im DAWMind Ordner:
        dir /b "%DEFAULT_PATH%\DAWMind" 2>nul
        echo.
        
        if exist "%DEFAULT_PATH%\DAWMind\device_DAWMind.py" (
            echo    [OK] device_DAWMind.py gefunden
            echo    Erste Zeile:
            set /p FIRSTLINE=<"%DEFAULT_PATH%\DAWMind\device_DAWMind.py"
            echo    %FIRSTLINE%
        ) else (
            echo    [FEHLER] device_DAWMind.py NICHT gefunden!
        )
        
        if exist "%DEFAULT_PATH%\DAWMind\device_DAWMind_minimal.py" (
            echo    [OK] device_DAWMind_minimal.py gefunden
        ) else (
            echo    [INFO] device_DAWMind_minimal.py nicht vorhanden
        )
    ) else (
        echo    [FEHLER] Kein DAWMind Ordner unter %DEFAULT_PATH%
        echo    Vorhandene Ordner:
        dir /b /ad "%DEFAULT_PATH%" 2>nul
    )
) else (
    echo    Standard-Pfad NICHT gefunden: %DEFAULT_PATH%
)

echo.

if exist "%ALT_PATH1%" (
    echo    Alternativer Pfad GEFUNDEN: %ALT_PATH1%
    echo    ACHTUNG: FL Studio benutzt moeglicherweise diesen Pfad!
    dir /b /ad "%ALT_PATH1%" 2>nul
) else (
    echo    Alternativer Pfad nicht vorhanden: %ALT_PATH1%
)

echo.
echo [2] Suche nach ALLEN Hardware-Ordnern auf dem System...
echo    (kann einen Moment dauern)
echo.

for /f "delims=" %%i in ('dir /b /s /ad "%USERPROFILE%\Documents\Image-Line*" 2^>nul ^| findstr /i "Hardware"') do (
    echo    Gefunden: %%i
    dir /b "%%i" 2>nul
    echo.
)

echo.
echo [3] Pruefe FL Studio Installation...
echo.

if exist "C:\Program Files\Image-Line\FL Studio" (
    echo    [OK] FL Studio gefunden: C:\Program Files\Image-Line\FL Studio
    if exist "C:\Program Files\Image-Line\FL Studio\FL64.exe" (
        echo    [OK] FL64.exe vorhanden (64-bit)
    )
) else if exist "C:\Program Files (x86)\Image-Line\FL Studio" (
    echo    [OK] FL Studio gefunden: C:\Program Files (x86)\Image-Line\FL Studio
) else (
    echo    [WARNUNG] FL Studio Standardpfad nicht gefunden
)

echo.
echo [4] Pruefe Shared Python Lib...
echo.

if exist "C:\Program Files\Image-Line\Shared\Python\Lib" (
    echo    [OK] Shared Python Lib: C:\Program Files\Image-Line\Shared\Python\Lib
) else if exist "C:\Program Files (x86)\Image-Line\Shared\Python\Lib" (
    echo    [OK] Shared Python Lib: C:\Program Files (x86)\Image-Line\Shared\Python\Lib
) else (
    echo    [INFO] Shared Python Lib nicht am Standardpfad
)

echo.
echo ============================================
echo  EMPFOHLENE SCHRITTE:
echo  1. Oeffne FL Studio
echo  2. Options ^> File Settings
echo  3. Notiere den "User data folder" Pfad
echo  4. Stelle sicher dass DAWMind-Ordner DORT liegt
echo  5. Restart FL Studio (F10 ^> MIDI Settings)
echo ============================================
echo.
pause
