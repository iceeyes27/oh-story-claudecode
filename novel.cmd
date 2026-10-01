@echo off
setlocal
call "%~dp0.novel-kit\scripts\py.cmd" "%~dp0novel.py" %*
exit /b %errorlevel%
