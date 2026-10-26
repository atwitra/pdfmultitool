@echo off
title Build Smart PDF Suite ke EXE
cd /d "%~dp0"

echo ========================================================
echo       BUILD SMART PDF SUITE KE STANDALONE EXE
echo ========================================================
echo.

echo [1/3] Memeriksa & Menginstall Dependencies...
python -m pip install --upgrade pyinstaller customtkinter pypdf pillow reportlab pypdfium2
if %errorlevel% neq 0 (
    echo [ERROR] Gagal menginstall dependencies. Silakan periksa koneksi internet atau python.
    pause
    exit /b %errorlevel%
)

echo.
echo [2/3] Memulai Kompilasi ke Single EXE dengan PyInstaller...
python -m PyInstaller --noconsole --onefile --name "SmartPDFSuite" --clean --icon "icon.ico" --add-data "icon.ico;." --add-data "icon.png;." --collect-all customtkinter --collect-all reportlab --collect-all PIL --collect-all pypdfium2 app.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Kompilasi gagal! Silakan periksa pesan error di atas.
    pause
    exit /b %errorlevel%
)

echo.
echo ========================================================
echo [3/3] BERHASIL!
echo File EXE Anda berada di folder:
echo %~dp0dist\SmartPDFSuite.exe
echo ========================================================
echo.
echo Membuka folder dist di File Explorer...
start "" explorer "%~dp0dist"
pause

