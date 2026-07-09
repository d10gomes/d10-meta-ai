@echo off
cd /d C:\Users\gomes\Downloads\projetos\d10-meta-ai\backend
set PYTHONPATH=C:\Users\gomes\Downloads\projetos\d10-meta-ai\backend
call venv\Scripts\activate
python run.py > uvicorn.log 2>&1
