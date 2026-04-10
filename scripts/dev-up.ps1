param(
  [string]$Dll = "muscles/build/Release/autonomous_fighter_muscles.dll",
  [string]$Yolo = "yolov8n.pt",
  [string]$WindowTitle = "Shadow Fight Arena",
  [string]$Model = ""
)

$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot/.."

if (-not (Test-Path ".venv\Scripts\python.exe")) {
  Write-Error "Virtual environment missing. Run scripts/bootstrap.ps1 first."
}

$backendArgs = @("main.py", "--dll", $Dll, "--yolo", $Yolo)
if ($WindowTitle -ne "") {
  $backendArgs += @("--window-title", $WindowTitle)
}
if ($Model -ne "") {
  $backendArgs += @("--model", $Model)
}

# Start Backend
Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList $backendArgs

# Wait for backend to initialize
Start-Sleep -Seconds 2

# Start Native Desktop UI
Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "ui_app.py"

Write-Host "Backend and Native UI launched."
