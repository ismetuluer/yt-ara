@echo off
rem YouTube Gelismis Arama - ilk kurulum / baslatici.
rem Bu dosyayi indirdiginiz zip'ten cikardiktan sonra CIFT TIKLAYIN.
rem Bilgisayarinizda Python kurulu olmasina GEREK YOKTUR; program kendi
rem calisma ortamini otomatik indirir. Yonetici (admin) yetkisi gerekmez;
rem her sey "Belgelerim" klasorune kurulur. Internet baglantisi gereklidir.
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PYVER=3.14.4"
set "TARGET=%USERPROFILE%\Documents\YouTubeSearch"
set "DESKTOP=%USERPROFILE%\Desktop"

title YouTube Gelismis Arama - Kurulum

if exist "%TARGET%\python\pythonw.exe" goto refresh_ve_baslat

echo ============================================================
echo   YouTube Gelismis Arama - Ilk Kurulum
echo ============================================================
echo.
echo   Program dosyalariniz klasorune kuruluyor:
echo     %TARGET%
echo   Gerekli bilesenler internetten indirilecek (bir kac dakika
echo   surebilir, internet hizina baglidir). Lutfen bekleyin...
echo.

echo [1/6] Kurulum klasoru hazirlaniyor...
if not exist "%TARGET%" mkdir "%TARGET%"
if not exist "%TARGET%\python" mkdir "%TARGET%\python"
if errorlevel 1 goto hata

echo [2/6] Uygulama dosyalari kopyalaniyor...
xcopy /e /i /y /q "app" "%TARGET%\app" >nul
if errorlevel 1 goto hata
copy /y "main.py" "%TARGET%\main.py" >nul
if exist "assets" xcopy /e /i /y /q "assets" "%TARGET%\assets" >nul
copy /y "requirements-runtime.txt" "%TARGET%\requirements.txt" >nul
if not exist "%TARGET%\data" mkdir "%TARGET%\data"
if not exist "%TARGET%\logs" mkdir "%TARGET%\logs"
if not exist "%TARGET%\downloads" mkdir "%TARGET%\downloads"

echo [3/6] Calisma ortami (Python) indiriliyor (~15MB)...
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-embed-amd64.zip' -OutFile '%TEMP%\yt_ara_python.zip'"
if errorlevel 1 goto hata_internet
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Expand-Archive -Path '%TEMP%\yt_ara_python.zip' -DestinationPath '%TARGET%\python' -Force"
if errorlevel 1 goto hata
del "%TEMP%\yt_ara_python.zip" >nul 2>&1
powershell -NoProfile -Command "$p='%TARGET%\python\python314._pth'; (Get-Content $p) -replace '#import site','import site' | Set-Content $p; Add-Content $p 'Lib\site-packages'; Add-Content $p '..'"
if errorlevel 1 goto hata

echo [4/6] Kurulum araci (pip) hazirlaniyor...
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%TEMP%\yt_ara_get_pip.py'"
if errorlevel 1 goto hata_internet
"%TARGET%\python\python.exe" "%TEMP%\yt_ara_get_pip.py" --no-warn-script-location
if errorlevel 1 goto hata
del "%TEMP%\yt_ara_get_pip.py" >nul 2>&1

echo [5/6] Gerekli kutuphaneler indiriliyor (birkac dakika surebilir)...
set "PYTHONNOUSERSITE=1"
"%TARGET%\python\python.exe" -m pip install --no-warn-script-location -r "%TARGET%\requirements.txt"
if errorlevel 1 goto hata_internet

echo [6/6] Baslatici ve masaustu kisayolu olusturuluyor...
rem NOT: YouTubeSearch.bat, uygulama ICINDEN kendini guncelleyip yeniden
rem baslatirken kullanilir (bkz. app/services/app_updater.py). Masaustu
rem kisayolu ise KASITLI OLARAK pythonw.exe'yi DOGRUDAN hedefler, .bat/cmd
rem araya girmez -- bazi Windows kurulumlarinda (ozellikle Windows Terminal
rem varsayilan terminal uygulamasiyken) cmd'nin "start" komutuyla baslatilan
rem sureclerin konsol/is (job) nesnesi kapanisina takilip hemen sonlanmasi
rem veya bos bir konsol penceresinin ekranda asili kalmasi gibi sorunlar
rem gorulebiliyor; pythonw.exe zaten konsolsuz oldugu icin dogrudan
rem baslatmak bu sorunlarin hicbirine yol acmaz.
> "%TARGET%\YouTubeSearch.bat" (
    echo @echo off
    echo cd /d "%%~dp0"
    echo set "PYTHONNOUSERSITE=1"
    echo start "" "python\pythonw.exe" main.py
)

powershell -NoProfile -Command ^
    "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%DESKTOP%\YouTube Arama.lnk');" ^
    "$s.TargetPath = '%TARGET%\python\pythonw.exe';" ^
    "$s.Arguments = 'main.py';" ^
    "$s.WorkingDirectory = '%TARGET%';" ^
    "$s.IconLocation = '%TARGET%\assets\icon.ico';" ^
    "$s.Description = 'YouTube Gelismis Arama';" ^
    "$s.Save()"

echo.
echo ============================================================
echo   Kurulum tamamlandi!
echo   Masaustunde "YouTube Arama" kisayolu olusturuldu.
echo   Program simdi aciliyor...
echo ============================================================
timeout /t 3 /nobreak >nul 2>&1
start "" /D "%TARGET%" "%TARGET%\python\pythonw.exe" main.py
exit /b 0

:refresh_ve_baslat
rem Program zaten kurulu: dosyalari gunceller (Kur.bat'i tekrar
rem calistirmak "onar/guncelle" gibi davranir) ve acar.
echo Program zaten kurulu, guncelleniyor ve aciliyor...
xcopy /e /i /y /q "app" "%TARGET%\app" >nul
copy /y "main.py" "%TARGET%\main.py" >nul
if exist "assets" xcopy /e /i /y /q "assets" "%TARGET%\assets" >nul
rem Eski kurulumlarda masaustu kisayolu hala YouTubeSearch.bat'i hedefliyor
rem olabilir; asagidaki komut onu da guncel (dogrudan pythonw.exe hedefli)
rem haline getirir.
powershell -NoProfile -Command ^
    "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%DESKTOP%\YouTube Arama.lnk');" ^
    "$s.TargetPath = '%TARGET%\python\pythonw.exe';" ^
    "$s.Arguments = 'main.py';" ^
    "$s.WorkingDirectory = '%TARGET%';" ^
    "$s.IconLocation = '%TARGET%\assets\icon.ico';" ^
    "$s.Description = 'YouTube Gelismis Arama';" ^
    "$s.Save()"
start "" /D "%TARGET%" "%TARGET%\python\pythonw.exe" main.py
exit /b 0

:hata_internet
echo.
echo ============================================================
echo   HATA: Internetten dosya indirilemedi.
echo   Lutfen internet baglantinizi kontrol edip tekrar deneyin.
echo ============================================================
pause
exit /b 1

:hata
echo.
echo ============================================================
echo   KURULUM BASARISIZ. Yukaridaki hata mesajini kontrol edin.
echo   Sorun devam ederse "%TARGET%\logs" klasorunu ve bu ekrani
echo   paylasarak yardim isteyebilirsiniz.
echo ============================================================
pause
exit /b 1
