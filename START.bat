@echo off
title D10 META AI - Startup
color 0A
echo.
echo  ██████╗  ██╗ ██████╗     ███╗   ███╗███████╗████████╗ █████╗      █████╗ ██╗
echo  ██╔══██╗███║██╔═████╗    ████╗ ████║██╔════╝╚══██╔══╝██╔══██╗    ██╔══██╗██║
echo  ██║  ██║╚██║██║██╔██║    ██╔████╔██║█████╗     ██║   ███████║    ███████║██║
echo  ██║  ██║ ██║████╔╝██║    ██║╚██╔╝██║██╔══╝     ██║   ██╔══██║    ██╔══██║██║
echo  ██████╔╝ ██║╚██████╔╝    ██║ ╚═╝ ██║███████╗   ██║   ██║  ██║    ██║  ██║██║
echo  ╚═════╝  ╚═╝ ╚═════╝     ╚═╝     ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝    ╚═╝  ╚═╝╚═╝
echo.
echo  Plataforma Inteligente de Gestao de Meta Ads
echo  ================================================
echo.

REM Verifica Redis (Laragon)
echo [1/3] Verificando Redis...
redis-cli ping >nul 2>&1
if %errorlevel% neq 0 (
    echo  AVISO: Redis nao responde. Inicie o Laragon primeiro!
) else (
    echo  Redis OK
)

REM Inicia Backend
echo [2/3] Iniciando Backend FastAPI...
start "D10 Backend" cmd /k "cd /d C:\Users\gomes\Downloads\projetos\d10-meta-ai\backend && set PYTHONPATH=C:\Users\gomes\Downloads\projetos\d10-meta-ai\backend && call venv\Scripts\activate && python run.py"
timeout /t 5 /nobreak >nul

REM Inicia Frontend
echo [3/3] Iniciando Frontend Next.js...
start "D10 Frontend" cmd /k "cd /d C:\Users\gomes\Downloads\projetos\d10-meta-ai\frontend && npx next dev --port 3000"
timeout /t 8 /nobreak >nul

REM Abre o browser
echo.
echo  Abrindo browser...
start "" "http://localhost:3000/login"

echo.
echo  ============================================
echo   D10 META AI INICIADO COM SUCESSO!
echo  ============================================
echo.
echo   Frontend:  http://localhost:3000
echo   Backend:   http://localhost:8000
echo   API Docs:  http://localhost:8000/docs
echo.
echo   Login: admin@d10.ai / d10admin123
echo.
pause
