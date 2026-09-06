# UrbanLens demo-day startup — run this ONE script after a fresh reboot.
# Usage:  Right-click -> Run with PowerShell   (or:  powershell -ExecutionPolicy Bypass -File start_demo.ps1)

$ErrorActionPreference = "SilentlyContinue"
$ROOT  = "C:\Users\saiyam miglani\OneDrive\Desktop\Glm 5.3"
$PY    = "C:\Users\saiyam miglani\AppData\Local\Programs\Python\Python312\python.exe"
$UVI   = "C:\Users\saiyam miglani\AppData\Local\Programs\Python\Python312\Scripts\uvicorn.exe"
$LOGS  = "$env:TEMP\urbanlens"

New-Item -ItemType Directory -Force -Path $LOGS | Out-Null
Write-Host "== UrbanLens demo startup ==" -ForegroundColor Cyan

# ---- kill any stale copies ----
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "uvicorn|vite" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Seconds 2

# ---- 1. backend ----
Write-Host "[1/3] starting backend (FastAPI + Supabase)..." -ForegroundColor Yellow
Start-Process -FilePath $UVI -ArgumentList "app.main:app","--host","0.0.0.0","--port","8000" `
    -WorkingDirectory "$ROOT\backend" -WindowStyle Hidden `
    -RedirectStandardOutput "$LOGS\backend.log" -RedirectStandardError "$LOGS\backend_err.log"
Start-Sleep -Seconds 8
$health = (Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/health" -UseBasicParsing -TimeoutSec 10).Content
Write-Host "      backend: $health" -ForegroundColor Green

# ---- 2. dashboard ----
Write-Host "[2/3] starting dashboard (Vite)..." -ForegroundColor Yellow
Start-Process -FilePath "node" -ArgumentList "node_modules/vite/bin/vite.js","--host" `
    -WorkingDirectory "$ROOT\dashboard" -WindowStyle Hidden `
    -RedirectStandardOutput "$LOGS\vite.log" -RedirectStandardError "$LOGS\vite_err.log"
Start-Sleep -Seconds 6
Write-Host "      dashboard: http://localhost:5173" -ForegroundColor Green

# ---- 3. edge agent (fleet vehicle, v3 model, Delhi route) ----
Write-Host "[3/3] starting edge agent (bus DL01CJ8943, v3 model)..." -ForegroundColor Yellow
Start-Process -FilePath $PY -ArgumentList "-X","utf8","main.py","--vehicle","DL01CJ8943",`
    "--type","bus","--video","media/route_demo.mp4","--route","routes/route_01.json" `
    -WorkingDirectory "$ROOT\edge" -WindowStyle Hidden `
    -RedirectStandardOutput "$LOGS\edge.log" -RedirectStandardError "$LOGS\edge_err.log"
Write-Host "      agent running (30s clip -> incidents appear on map, then stops)" -ForegroundColor Green

# ---- open browser ----
Start-Sleep -Seconds 3
Start-Process "http://localhost:5173"

Write-Host ""
Write-Host "== ALL LIVE ==" -ForegroundColor Cyan
Write-Host "  Dashboard : http://localhost:5173"
Write-Host "  Backend   : http://localhost:8000/docs  (interactive API)"
Write-Host "  Logs      : $LOGS"
Write-Host ""
Write-Host "Demo flow: Live Map -> Traffic -> Incidents (click card) -> Analytics -> Live Cam"
Write-Host "To restart the bus agent during the demo, re-run this script's step 3 or:"
Write-Host "  cd '$ROOT\edge'; $PY -X utf8 main.py --vehicle DL01CJ8943 --video media/route_demo.mp4 --route routes/route_01.json"
