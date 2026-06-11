@echo off
setlocal EnableExtensions

cd /d "%~dp0"

echo [%date% %time:~0,8%] [INFO] FoldersNUsersParser launcher
echo [%date% %time:~0,8%] [INFO] Project root: %CD%

if /i "%~1"=="--check" (
  echo [%date% %time:~0,8%] [INFO] Launcher check mode enabled.
)

if not exist "package.json" (
  echo [%date% %time:~0,8%] [ERROR] package.json not found. Frontend cannot be started.
  exit /b 1
)

if not exist "backend\requirements.txt" (
  echo [%date% %time:~0,8%] [ERROR] backend\requirements.txt not found. Backend cannot be started.
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo [%date% %time:~0,8%] [ERROR] npm not found. Install Node.js and try again.
  exit /b 1
)

where powershell >nul 2>nul
if errorlevel 1 (
  echo [%date% %time:~0,8%] [ERROR] PowerShell not found. It is required to run backend and frontend in one terminal.
  exit /b 1
)

set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3"
if "%PYTHON_CMD%"=="" (
  where python >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=python"
)
if "%PYTHON_CMD%"=="" (
  echo [%date% %time:~0,8%] [ERROR] Python not found. Install Python 3.11+ and try again.
  exit /b 1
)

if not exist "node_modules" (
  echo [%date% %time:~0,8%] [WARN] node_modules not found. Installing frontend dependencies...
  call npm install
  if errorlevel 1 (
    echo [%date% %time:~0,8%] [ERROR] npm install failed.
    exit /b 1
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo [%date% %time:~0,8%] [WARN] Python virtual environment not found. Creating .venv...
  %PYTHON_CMD% -m venv .venv
  if errorlevel 1 (
    echo [%date% %time:~0,8%] [ERROR] Failed to create Python virtual environment.
    exit /b 1
  )
)

echo [%date% %time:~0,8%] [INFO] Installing backend dependencies...
call .venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if errorlevel 1 (
  echo [%date% %time:~0,8%] [ERROR] Backend dependency install failed.
  exit /b 1
)

if /i "%~1"=="--check" (
  echo [%date% %time:~0,8%] [INFO] Launcher check passed.
  exit /b 0
)

echo [%date% %time:~0,8%] [INFO] Preparing backend at http://127.0.0.1:8000
echo [%date% %time:~0,8%] [INFO] Starting frontend at http://127.0.0.1:5173
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = (Get-Location).Path; " ^
  "$api = 'http://127.0.0.1:8000/api/v1/accounts'; " ^
  "$backend = $null; " ^
  "function Test-FnupApi { try { Invoke-WebRequest -Uri $api -UseBasicParsing -TimeoutSec 2 | Out-Null; return $true } catch { return $false } } " ^
  "if (Test-FnupApi) { Write-Host '[BACKEND] Existing FNUP backend detected at http://127.0.0.1:8000; reusing it.' } else { " ^
  "  $listener = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue; " ^
  "  if ($listener) { $pids = ($listener | Select-Object -ExpandProperty OwningProcess -Unique) -join ', '; Write-Host ('[BACKEND] ERROR: port 8000 is busy by PID(s): ' + $pids + ', but FNUP API does not respond. Stop that process and run start.bat again.'); exit 1 } " ^
  "  Write-Host '[BACKEND] Starting backend at http://127.0.0.1:8000'; " ^
  "  $backend = Start-Job -Name FoldersNUsersParserBackend -ScriptBlock { param($root) Set-Location $root; & '.\.venv\Scripts\python.exe' -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 2>&1 } -ArgumentList $root; " ^
  "} " ^
  "$frontend = Start-Process -FilePath 'npm.cmd' -ArgumentList @('run','dev','--','--host','127.0.0.1') -NoNewWindow -PassThru; " ^
  "try { while (-not $frontend.HasExited) { if ($backend) { Receive-Job $backend | ForEach-Object { Write-Host ('[BACKEND] ' + $_) }; if ($backend.State -ne 'Running') { Write-Host '[BACKEND] ERROR: backend stopped. Closing frontend too.'; Stop-Process -Id $frontend.Id -Force -ErrorAction SilentlyContinue; exit 1 } }; Start-Sleep -Milliseconds 250 } if ($backend) { Receive-Job $backend | ForEach-Object { Write-Host ('[BACKEND] ' + $_) } }; exit $frontend.ExitCode } finally { if ($backend) { Stop-Job $backend -ErrorAction SilentlyContinue; Remove-Job $backend -Force -ErrorAction SilentlyContinue } }"
exit /b %errorlevel%
