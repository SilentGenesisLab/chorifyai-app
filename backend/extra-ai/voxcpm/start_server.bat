@echo off
REM VoxCPM2 服务启动脚本
REM 默认用 tor25 环境; 想换环境设 VOXCPM_PYTHON 即可
cd /d %~dp0
if "%VOXCPM_PYTHON%"=="" set "VOXCPM_PYTHON=D:\Anaconda3\envs\tor25\python.exe"
"%VOXCPM_PYTHON%" server.py --host 0.0.0.0 --port 8190 --preload
