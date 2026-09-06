@echo off
cd /d "C:\Users\saiyam miglani\OneDrive\Desktop\Glm 5.3\edge"
"C:\Users\saiyam miglani\AppData\Local\Programs\Python\Python312\python.exe" -X utf8 main.py --vehicle DL01CJ8943 --type bus --video media/route_demo.mp4 --route routes/route_01.json > "%TEMP%\edge_e2e.log" 2>&1
