@echo off
rem YouTube Gelismis Arama - gomulu Python ile "bat" tabanli portable klasor uretir.
rem PyInstaller EXE'si yerine, kurumsal antivirus'un yeni/imzasiz EXE'leri
rem engelleyebilmesi durumunda kullanilacak alternatif dagitim yontemi:
rem taninan/guvenilir python.exe ile calisir, ayrica derlenmis bir EXE uretmez.
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PYVER=3.14.4"
set "APPDIR=portable\YouTubeSearch"
set "PYDIR=%APPDIR%\python"

echo [1/7] Onceki portable klasor temizleniyor...
if exist "%APPDIR%" rmdir /s /q "%APPDIR%"
mkdir "%PYDIR%"
if errorlevel 1 goto hata

echo [2/7] Gomulu Python indiriliyor (~15MB, python.org)...
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-embed-amd64.zip' -OutFile 'python-embed.zip'"
if errorlevel 1 goto hata

echo [3/7] Python cikartiliyor...
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Expand-Archive -Path 'python-embed.zip' -DestinationPath '%PYDIR%' -Force"
if errorlevel 1 goto hata
del python-embed.zip

echo [4/7] site-packages etkinlestiriliyor...
rem _pth dosyasindaki yollar python.exe'nin bulundugu klasore (python\)
rem gore cozumlenir; uygulama kodu (main.py, app\) bir ust klasorde
rem (..) oldugu icin o da eklenmeli, yoksa "No module named 'app'" hatasi
rem alinir.
powershell -NoProfile -Command "$p='%PYDIR%\python314._pth'; (Get-Content $p) -replace '#import site','import site' | Set-Content $p; Add-Content $p 'Lib\site-packages'; Add-Content $p '..'"
if errorlevel 1 goto hata

echo [5/7] pip kuruluyor...
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile 'get-pip.py'"
if errorlevel 1 goto hata
"%PYDIR%\python.exe" get-pip.py --no-warn-script-location
if errorlevel 1 goto hata
del get-pip.py

echo [6/7] Bagimliliklar kuruluyor (PySide6-Essentials, requests, yt-dlp - birkac dakika surebilir)...
rem PYTHONNOUSERSITE: gomulu Python'un ayni surum numarali sistem Python'unun
rem %%APPDATA%%\Python\PythonXY\site-packages klasorunu paylasmasini engeller;
rem aksi halde "portable" klasor gercekte sistem paketlerine bagimli kalir.
rem PySide6-Essentials (tam "PySide6" degil): uygulama yalnizca Core/Gui/
rem Widgets kullaniyor; tam paket Qt WebEngine (Chromium, ~200MB) gibi hic
rem kullanilmayan moduller yuzunden portable boyutunu ~600MB buyutuyordu.
set "PYTHONNOUSERSITE=1"
"%PYDIR%\python.exe" -m pip install --no-warn-script-location "PySide6-Essentials>=6.5" "requests>=2.28" "yt-dlp>=2024.1.1"
if errorlevel 1 goto hata

echo [7/7] Uygulama dosyalari ve baslatici hazirlaniyor...
> build_portable_exclude.txt echo __pycache__
xcopy /e /i /y /q /exclude:build_portable_exclude.txt app "%APPDIR%\app" >nul
if errorlevel 1 goto hata
del build_portable_exclude.txt
copy /y main.py "%APPDIR%\main.py" >nul
if exist "assets" xcopy /e /i /y /q "assets" "%APPDIR%\assets" >nul
mkdir "%APPDIR%\data"
mkdir "%APPDIR%\config"
mkdir "%APPDIR%\logs"
mkdir "%APPDIR%\downloads"

if exist "tools\ffmpeg\ffmpeg.exe" (
    mkdir "%APPDIR%\tools\ffmpeg"
    copy /y "tools\ffmpeg\ffmpeg.exe" "%APPDIR%\tools\ffmpeg\ffmpeg.exe" >nul
    if exist "tools\ffmpeg\ffprobe.exe" (
        copy /y "tools\ffmpeg\ffprobe.exe" "%APPDIR%\tools\ffmpeg\ffprobe.exe" >nul
    )
    echo   FFmpeg portable klasore kopyalandi.
) else (
    echo   UYARI: tools\ffmpeg\ffmpeg.exe bulunamadi.
)

> "%APPDIR%\YouTubeSearch.bat" (
    echo @echo off
    echo cd /d "%%~dp0"
    echo set "PYTHONNOUSERSITE=1"
    echo start "" "python\pythonw.exe" main.py
)

echo.
echo Tamamlandi.
echo   %cd%\%APPDIR%\YouTubeSearch.bat
echo Bu klasoru oldugu gibi istediginiz yere kopyalayabilirsiniz.
echo Derlenmis bir EXE uretmedigi icin antivirus'un "bilinmeyen yeni EXE"
echo engellemesine takilma ihtimali cok daha dusuktur.
pause
exit /b 0

:hata
echo.
echo BUILD BASARISIZ. Yukaridaki hata mesajini kontrol edin.
pause
exit /b 1
