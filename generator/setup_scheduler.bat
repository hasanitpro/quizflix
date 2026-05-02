@echo off
:: AZ Quiz Hub — Register Windows Task Scheduler job
:: Edit the /st time below (HH:MM in 24-hour format) before running.
:: Run this script as Administrator.

set TASK_NAME=QuizFlixDailyUpload
set SCRIPT_PATH=D:\xampp\htdocs\quizflix\generator\run_daily.py
set RUN_TIME=09:00

:: Detect python path
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: python not found in PATH. Install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)
for /f "delims=" %%i in ('where python') do set PYTHON_PATH=%%i

echo Creating scheduled task: %TASK_NAME%
echo   Script : %SCRIPT_PATH%
echo   Time   : %RUN_TIME% daily
echo   Python : %PYTHON_PATH%
echo.

schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "\"%PYTHON_PATH%\" \"%SCRIPT_PATH%\"" ^
    /sc daily ^
    /st %RUN_TIME% ^
    /f

if %errorlevel% equ 0 (
    echo.
    echo Task registered successfully!
    echo To change the time: schtasks /change /tn "%TASK_NAME%" /st HH:MM
    echo To run now:         schtasks /run /tn "%TASK_NAME%"
    echo To delete:          schtasks /delete /tn "%TASK_NAME%" /f
) else (
    echo.
    echo Failed to create task. Try running this script as Administrator.
)

pause
