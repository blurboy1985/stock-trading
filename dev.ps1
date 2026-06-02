# Launches the StockSim backend and frontend together.
# Usage:  .\dev.ps1
$root = $PSScriptRoot

# Free the dev ports first. Re-running this script (or npm run dev) without
# stopping the old servers leaves multiple uvicorn instances bound to :8000
# via SO_REUSEADDR; Windows then routes connections across them and any stale
# one hangs requests, which shows up in the UI as infinite "loading...".
function Stop-Port($port) {
    $pids = (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue).OwningProcess |
        Sort-Object -Unique
    foreach ($processId in $pids) {
        if ($processId) {
            Write-Host "  freeing port $port (PID $processId)" -ForegroundColor DarkGray
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }
}
Write-Host "Freeing dev ports (8000, 5173)..." -ForegroundColor Cyan
Stop-Port 8000
Stop-Port 5173

Write-Host "Starting backend (uvicorn :8000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    '-NoExit', '-Command',
    "cd '$root\backend'; .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"
)

Write-Host "Starting frontend (vite :5173)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    '-NoExit', '-Command',
    "cd '$root\frontend'; npm run dev"
)

Write-Host "Both servers launching in separate windows. App: http://localhost:5173" -ForegroundColor Green
