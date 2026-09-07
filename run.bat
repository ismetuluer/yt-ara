@echo off
rem YouTube Gelismis Arama - gelistirme ortaminda calistirma
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo HATA: Python bulunamadi. Lutfen https://www.python.org adresinden Python 3.10+ kurun.
    pause
    exit /b 1
)

python -c "import PySide6, requests, yt_dlp" >nul 2>&1
if errorlevel 1 (
    echo Gerekli kutuphaneler yukleniyor, lutfen bekleyin...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo HATA: Kutuphaneler yuklenemedi.
        pause
        exit /b 1
    )
)

python main.py
