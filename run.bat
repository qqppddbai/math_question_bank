@echo off
chcp 65001 >nul
cd /d %~dp0
echo 正在启动数学题库管理系统...
streamlit run app.py
pause