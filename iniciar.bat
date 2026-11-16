@echo off
cd /d "%~dp0"
if not exist .venv (
  echo Creando entorno virtual...
  python -m venv .venv || goto :error
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install -r backend\requirements.txt || goto :error
)
cd backend
..\.venv\Scripts\python main.py
pause
exit /b

:error
echo.
echo Hubo un error. Revisa que Python 3.12 este instalado (abre una terminal nueva).
pause
