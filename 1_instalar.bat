@echo off
echo ===================================================
echo   Instalando Bot Citas iCITA - JPD Abogados
echo ===================================================
echo.

REM Comprobar Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python no esta instalado.
    echo.
    echo Por favor:
    echo 1. Ve a https://www.python.org/downloads/
    echo 2. Descarga Python 3.11 o superior
    echo 3. Durante la instalacion marca "Add Python to PATH"
    echo 4. Vuelve a ejecutar este archivo
    pause
    exit /b 1
)

echo Python encontrado. Instalando dependencias...
python -m pip install --upgrade pip
python -m pip install playwright requests

echo.
echo Instalando navegador Chromium...
python -m playwright install chromium
python -m playwright install-deps chromium

echo.
echo ===================================================
echo   Instalacion completada correctamente!
echo   Ahora ejecuta:  2_iniciar_bot.bat
echo ===================================================
pause
