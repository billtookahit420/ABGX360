@echo off
rem Launch abgx360 GUI on Windows. On first run, create the
rem bundled virtual environment and install the app's deps.
rem NOTE: the GUI itself runs on Windows, but it drives a
rem prebuilt abgx360.exe which is NOT bundled -- download
rem abgx360 v1.0.7 from http://abgx360.hadzz.com and place
rem abgx360.exe in the engine folder the app names on first
rem run. The Windows path is unverified -- see README.md.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo First run: setting up the Python environment...
    python -m venv .venv || (
        echo Could not create the environment. Install Python 3.10+
        echo from python.org, tick "Add python.exe to PATH", retry.
        exit /b 1
    )
)
.venv\Scripts\python.exe -c "import PySide6" 2>nul
if errorlevel 1 (
    echo Installing Python dependencies...
    .venv\Scripts\python.exe -m pip install -r requirements.txt || (
        echo Dependency install failed - check connection, re-run.
        exit /b 1
    )
)
set "ABGX360_GUI_DATA_DIR=%LOCALAPPDATA%\abgx360-gui"
set "ABGX360_GUI_ENGINE_DIR=%LOCALAPPDATA%\abgx360-gui\engine"
.venv\Scripts\python.exe app\main.py %*
