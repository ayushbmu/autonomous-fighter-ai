$ErrorActionPreference = "Stop"

Set-Location "$PSScriptRoot/.."

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outDir = Join-Path "releases" "AutonomousFighter-$timestamp"
New-Item -ItemType Directory -Path $outDir -Force | Out-Null

$items = @("api", "brain", "common", "muscles", "perception", "scripts", "tests", "ui", "main.py", "README.md", "requirements.txt", ".env.example")
foreach ($item in $items) {
  Copy-Item -Path $item -Destination $outDir -Recurse -Force
}

Compress-Archive -Path "$outDir\*" -DestinationPath "$outDir.zip" -Force
Write-Host "Release package created: $outDir.zip"
