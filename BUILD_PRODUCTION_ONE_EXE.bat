@echo off
cd /d "%~dp0"
if not exist ".venv" (py -3.12 -m venv .venv 2>nul || py -m venv .venv)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements.txt
pyinstaller --noconfirm --clean --onefile --windowed --name VideoWallpaper --collect-all imageio_ffmpeg --collect-all PySide6.QtMultimedia main.py
if errorlevel 1 (echo BUILD THAT BAI & pause & exit /b 1)
echo XONG: %CD%\dist\VideoWallpaper.exe
pause
