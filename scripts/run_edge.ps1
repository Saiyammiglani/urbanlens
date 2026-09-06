$ErrorActionPreference = "SilentlyContinue"
$PY = "C:\Users\saiyam miglani\AppData\Local\Programs\Python\Python312\python.exe"
Start-Process -FilePath $PY -ArgumentList "-X","utf8","main.py","--vehicle","DL01CJ8943","--type","bus","--video","media/route_demo.mp4","--route","routes/route_01.json" `
    -WorkingDirectory "C:\Users\saiyam miglani\OneDrive\Desktop\Glm 5.3\edge" -WindowStyle Hidden `
    -RedirectStandardOutput "$env:TEMP\edge_run.log" -RedirectStandardError "$env:TEMP\edge_run_err.log"
Write-Host "edge agent launched"
