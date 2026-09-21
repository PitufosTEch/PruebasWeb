@echo off
REM ejecutar_snapshot_directo.bat
REM Genera y publica el snapshot del dashboard sin depender de CORS.
REM Llamar desde Task Scheduler cada 15-30 minutos.

cd /d "C:\Users\rodri\PruebasWeb"

REM Fetch + rebase para no pisar cambios del repo
git fetch origin --quiet 2>nul

REM Ejecutar el script principal
"C:\Program Files\Python314\python.exe" -X utf8 SCRaices-LLM\app\snapshot_directo.py >> SCRaices-LLM\app\snapshot_directo.log 2>&1

echo [%date% %time%] Snapshot ejecutado >> SCRaices-LLM\app\snapshot_directo.log
