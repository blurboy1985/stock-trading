# Launches the StockSim backend and frontend together.
# Usage:  .\dev.ps1
$root = $PSScriptRoot

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
