@echo off

cd /d "%~dp0"

echo Facebook Reels Publish Date Backfill
echo.
echo Fetches missing Published Date values for Obsidian notes via Chrome.
echo.
echo Test first 5 notes:
echo   run_backfill_dates.bat --limit 5
echo.
echo Preview all missing:
echo   run_backfill_dates.bat --dry-run
echo.

call "%USERPROFILE%\miniconda3\Scripts\activate.bat"
call conda activate facebook_shorts_scrapper

set PYTHONUNBUFFERED=1
python -m src.backfill_publish_dates %*

set EXIT_CODE=%ERRORLEVEL%

pause
exit /b %EXIT_CODE%
