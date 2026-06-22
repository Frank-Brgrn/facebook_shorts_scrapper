@echo off

cd /d "%~dp0"

echo Facebook Reels Importer
echo.
echo Reads the newest HTML file from the "html dumps" folder.
echo.
echo To refresh: open Saved Reels in Chrome, scroll to load all reels,
echo save the page HTML into html dumps with a date in the name, e.g.:
echo   html dumps\20260621 - Facebook Reels.html
echo.
echo New videos also get a publish date lookup via Chrome in background.
echo Use --no-fetch-dates to skip that step.
echo.

call "%USERPROFILE%\miniconda3\Scripts\activate.bat"
call conda activate facebook_shorts_scrapper

set PYTHONUNBUFFERED=1
python -m src.main %*

set EXIT_CODE=%ERRORLEVEL%

pause
exit /b %EXIT_CODE%
