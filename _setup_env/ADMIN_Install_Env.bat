@echo off
cd /d "%~dp0"

REM Initialize conda in script context
call "%USERPROFILE%\miniconda3\Scripts\activate.bat"

REM Create the conda environment with Python 3.13
call conda create --name facebook_shorts_scrapper python=3.13 -y

REM Activate the environment
call conda activate facebook_shorts_scrapper

REM Ensure pip is available and working
call conda install pip -y
call python -m ensurepip --upgrade

REM Clear pip cache to avoid permission issues
call python -m pip cache purge

call python -m pip install -r requirements.txt

REM ffmpeg is required for audio transcription (yt-dlp / faster-whisper)
call conda install ffmpeg -y -c conda-forge

REM If the above fails, try with --user flag
if errorlevel 1 (
    echo Trying with --user flag...
    call python -m pip install --user -r requirements.txt
)

pause
