@echo off
chcp 65001 >nul
set "TEMP=D:\RoboMaster\temp"
set "TMP=D:\RoboMaster\temp"
"D:\RoboMaster\venv\Scripts\python.exe" -X utf8 "%~dp002_sta_check.py" %*
pause
