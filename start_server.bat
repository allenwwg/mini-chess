@echo off
cd /d "%~dp0"
set "PYTHONPATH=e:\works\chess\_deps"
"e:\works\stocker\.venv\Scripts\python.exe" chess_server.py
pause
