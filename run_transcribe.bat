@echo off

cd /d "%~dp0"

echo Facebook Reels Transcriber
echo.
echo Notes with Is Transcribed: 1 and a transcript are always skipped.
echo.
echo Transcribe 10 pending notes:
echo   run_transcribe.bat 10
echo.
echo Transcribe all pending notes:
echo   run_transcribe.bat
echo.
echo Same with --limit:
echo   run_transcribe.bat --limit 10
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
