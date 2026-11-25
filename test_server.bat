@echo off
REM Chinese Chess Server Test Script
REM Run this AFTER starting the server

echo ============================================================
echo Chinese Chess Server - API Test
echo ============================================================
echo.
echo This script will test all server API endpoints
echo.
echo Make sure the server is running in another window!
echo Start it with: start_server.bat
echo.
pause

echo.
echo Testing server...
python test_server.py

echo.
pause
