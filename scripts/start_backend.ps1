# Start backend only — free-tier safe (Supabase tx pooler, NullPool, no prepared stmts)
$ErrorActionPreference = "SilentlyContinue"
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "app.main:app" } |
    ForEach-Object { taskkill /F /PID $_.ProcessId /T }
Start-Sleep -Seconds 3

$PY = "C:\Users\saiyam miglani\AppData\Local\Programs\Python\Python312\Scripts\uvicorn.exe"
Start-Process -FilePath $PY -ArgumentList "app.main:app","--host","0.0.0.0","--port","8000" `
    -WorkingDirectory "C:\Users\saiyam miglani\OneDrive\Desktop\Glm 5.3\backend" -WindowStyle Hidden `
    -RedirectStandardOutput "$env:TEMP\be_out.log" -RedirectStandardError "$env:TEMP\be_err.log"
Start-Sleep -Seconds 12
$health = (Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/health" -UseBasicParsing -TimeoutSec 15).Content
Write-Host "backend: $health"
