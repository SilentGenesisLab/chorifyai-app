@echo off
REM VoxCPM2 模型下载 (默认 ModelScope, 国内直连免代理)
REM 默认用 tor25 环境; 想换环境设 VOXCPM_PYTHON 即可
cd /d %~dp0
if "%VOXCPM_PYTHON%"=="" set "VOXCPM_PYTHON=D:\Anaconda3\envs\tor25\python.exe"
"%VOXCPM_PYTHON%" download_model.py %*
pause
