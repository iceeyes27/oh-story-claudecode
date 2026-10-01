@echo off
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" <nul >nul 2>&1
if not errorlevel 1 goto use_py
python -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" <nul >nul 2>&1
if not errorlevel 1 goto use_python
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" <nul >nul 2>&1
if not errorlevel 1 goto use_python3
echo novel-kit requires Python 3.9+ in PATH. 1>&2
exit /b 127
:use_py
py -3 %*
exit /b %errorlevel%
:use_python
python %*
exit /b %errorlevel%
:use_python3
python3 %*
exit /b %errorlevel%
