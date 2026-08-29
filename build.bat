@echo off
rem PickTrans build script: produce single-file dist\PickTrans.exe
rem IMPORTANT: keep this file ASCII-only with CRLF line endings.
rem cmd parses batch files in the ANSI/OEM codepage (GBK on zh-CN systems);
rem UTF-8 Chinese comments or LF-only endings corrupt the commands below
rem (see the old build log: 'taller' is not recognized as a command).
cd /d "%~dp0"

pip show pyinstaller >nul 2>&1 || pip install pyinstaller

pyinstaller --noconsole --onefile --name PickTrans --icon assets\icon.ico --add-data "assets;assets" --collect-data rapidocr_onnxruntime --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 --hidden-import winsdk.windows.globalization --hidden-import winsdk.windows.graphics.imaging --hidden-import winsdk.windows.media.ocr --hidden-import winsdk.windows.storage.streams --exclude-module PyQt5 --exclude-module PySide2 --exclude-module PySide6 --exclude-module shiboken2 --exclude-module shiboken6 main.py
if errorlevel 1 (
  echo BUILD FAILED - see build\pyinstaller.log
  exit /b 1
)

echo.
echo Build done: dist\PickTrans.exe
