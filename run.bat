@echo off
chcp 65001 >nul
title הפקת קבלות - חשבונית ירוקה
cd /d "%~dp0"
REM מפעיל את סקריפט ההכנה (PowerShell) עם התקנה אוטומטית ופס התקדמות
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
if errorlevel 1 pause
