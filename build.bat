@echo off
rem YouTube Gelismis Arama - portable EXE uretir
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo HATA: Python bulunamadi. Lutfen https://www.python.org adresinden Python 3.10+ kurun.
    pause
    exit /b 1
)

echo [1/5] Kutuphaneler kontrol ediliyor...
python -m pip install -r requirements.txt
if errorlevel 1 goto hata

echo [2/5] EXE derleniyor (birkac dakika surebilir)...
python -m PyInstaller --noconfirm --clean YouTubeSearch.spec
if errorlevel 1 goto hata
echo [3/5] Portable klasor hazirlaniyor...
if exist "portable\YouTubeSearch" rmdir /s /q "portable\YouTubeSearch"
xcopy /e /i /y /q "dist\YouTubeSearch" "portable\YouTubeSearch" >nul
if errorlevel 1 goto hata
mkdir "portable\YouTubeSearch\data"
mkdir "portable\YouTubeSearch\config"
mkdir "portable\YouTubeSearch\logs"
mkdir "portable\YouTubeSearch\downloads"

echo [4/5] FFmpeg kontrol ediliyor...
if exist "tools\ffmpeg\ffmpeg.exe" (
    mkdir "portable\YouTubeSearch\tools\ffmpeg"
    copy /y "tools\ffmpeg\ffmpeg.exe" "portable\YouTubeSearch\tools\ffmpeg\ffmpeg.exe" >nul
    if exist "tools\ffmpeg\ffprobe.exe" (
        copy /y "tools\ffmpeg\ffprobe.exe" "portable\YouTubeSearch\tools\ffmpeg\ffprobe.exe" >nul
    )
    echo   FFmpeg portable klasore kopyalandi.
) else (
    echo   UYARI: tools\ffmpeg\ffmpeg.exe bulunamadi.
    echo   Video indirme ve goruntu cikarma icin FFmpeg gerekir.
    echo   FFmpeg'i https://www.gyan.dev/ffmpeg/builds/ adresinden indirip
    echo   tools\ffmpeg\ klasorune koyun ve build'i tekrar calistirin.
)

echo [5/5] Tamamlandi.
echo.
echo Portable uygulama hazir:
echo   %cd%\portable\YouTubeSearch\YouTubeSearch.exe
echo Bu klasoru oldugu gibi istediginiz yere kopyalayabilirsiniz.
echo.
echo NOT: Windows'un "guvenilir olmayan uygulama" korumasi, imzasiz EXE
echo kopyalarini engelleyebilir. Boyle bir durumda:
echo   - Windows Guvenlik - Uygulama ve tarayici denetimi - Guvenilirlik
echo     tabanli koruma ayarini gecici kapatin, VEYA
echo   - EXE'yi kod imzalama sertifikasi ile imzalayin.
pause
exit /b 0

:hata
echo.
echo BUILD BASARISIZ. Yukaridaki hata mesajini kontrol edin.
pause
exit /b 1
