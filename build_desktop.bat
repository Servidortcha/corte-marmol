@echo off
rem Compila la app de escritorio en un .exe (LaPuntualMarmoleria.exe)
cd /d "%~dp0"

if not exist ".venv\Scripts\pyinstaller.exe" (
    echo Instalando dependencias de compilacion...
    ".venv\Scripts\python.exe" -m pip install pyinstaller pywebview
)

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name "LaPuntualMarmoleria" ^
    --add-data "static;static" ^
    --collect-submodules webview ^
    --hidden-import uvicorn.logging ^
    --hidden-import uvicorn.loops.auto ^
    --hidden-import uvicorn.protocols.http.auto ^
    --hidden-import uvicorn.protocols.websockets.auto ^
    --hidden-import uvicorn.lifespan.on ^
    --hidden-import uvicorn.lifespan.off ^
    --hidden-import uvicorn.middleware.proxy_headers ^
    --hidden-import uvicorn.middleware.message_logger ^
    desktop.py

echo.
echo Listo: dist\LaPuntualMarmoleria.exe
pause
