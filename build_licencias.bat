@echo off
rem Compila el generador de licencias en un .exe (AresaNest-Licencias.exe)
cd /d "%~dp0"

if not exist ".venv\Scripts\pyinstaller.exe" (
    echo Instalando pyinstaller...
    ".venv\Scripts\python.exe" -m pip install pyinstaller
)

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name "AresaNest-Licencias" ^
    --icon "static\icono.ico" ^
    --version-file "version_info.txt" ^
    licencias_app.py

echo.
echo Listo: dist\AresaNest-Licencias.exe
pause
