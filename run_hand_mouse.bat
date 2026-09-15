@echo off
chcp 932 > nul
cd /d "%~dp0"
uv run scripts\hand_mouse.py %*
if errorlevel 1 pause
