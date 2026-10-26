@echo off
title Smart PDF Renamer Launcher
cd /d "%~dp0"

echo Membuka Smart PDF Renamer...
start "" pythonw app.py || python app.py
