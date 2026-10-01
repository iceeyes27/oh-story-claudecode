@echo off
setlocal
call "%~dp0..\scripts\py.cmd" "%~dp0scene_gate.py"
if errorlevel 3 goto denied
if errorlevel 2 exit /b 2
if errorlevel 1 goto denied
exit /b 0
:denied
echo novel-kit write guard failed; write blocked. Install Python 3.9+ and run doctor. 1>&2
exit /b 2
