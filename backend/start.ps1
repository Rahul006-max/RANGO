# ─────────────────────────────────────────────────────────────────
#  RAG Pipeline Optimizer — Backend Starter
#  Kills any stale process on port 8002, then starts uvicorn.
# ─────────────────────────────────────────────────────────────────

$PORT = 8002
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $SCRIPT_DIR

Write-Host "Checking for processes on port $PORT..." -ForegroundColor Cyan

# Kill any process currently holding port 8002
$stale = netstat -ano | Select-String ":$PORT\s.*LISTENING"
if ($stale) {
    $stale | ForEach-Object {
        $stalePid = ($_ -split '\s+')[-1]
        if ($stalePid -match '^\d+$' -and $stalePid -ne '0') {
            Write-Host "  Killing PID $stalePid (was holding port $PORT)" -ForegroundColor Yellow
            Stop-Process -Id $stalePid -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Seconds 1
}

Write-Host "Starting backend on port $PORT..." -ForegroundColor Green
& .\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port $PORT --reload
