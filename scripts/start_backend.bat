@echo off
cd /d "C:\Users\saiyam miglani\OneDrive\Desktop\Glm 5.3\backend"
"C:\Users\saiyam miglani\AppData\Local\Programs\Python\Python312\Scripts\uvicorn.exe" app.main:app --host 0.0.0.0 --port 8000 > "C:\Users\saiyam miglani\AppData\Local\Temp\backend_live.log" 2>&1
