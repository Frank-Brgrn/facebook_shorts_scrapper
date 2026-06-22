@echo off

cd /d "%~dp0"

echo Facebook Reels Transcriber
echo.
echo Transcribe all Obsidian notes missing a transcript:
echo   run_transcribe.bat
echo.
echo Test on first 5 notes only:
echo   run_transcribe.bat --limit 5
echo.
echo Single URL:
echo   run_transcribe.bat --url "https://www.facebook.com/watch/?v=1443970823862051"
echo.

call "%USERPROFILE%\miniconda3\Scripts\activate.bat"
call conda activate facebook_shorts_scrapper

set PYTHONUNBUFFERED=1
python -m src.transcribe %*

set EXIT_CODE=%ERRORLEVEL%

pause
exit /b %EXIT_CODE%
