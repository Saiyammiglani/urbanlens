# Launch ANPR plate-detector training (detached, GPU). ~1-1.5h.
$ErrorActionPreference = "SilentlyContinue"
$PY = "C:\Users\saiyam miglani\AppData\Local\Programs\Python\Python312\python.exe"
Start-Process -FilePath $PY -ArgumentList "-X","utf8","train_plate.py" `
    -WorkingDirectory "C:\Users\saiyam miglani\OneDrive\Desktop\Glm 5.3\ml" -WindowStyle Hidden `
    -RedirectStandardOutput "$env:TEMP\plate_train.log" -RedirectStandardError "$env:TEMP\plate_train_err.log"
Write-Host "plate detector training launched (GPU)"
