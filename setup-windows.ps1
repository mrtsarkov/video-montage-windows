#Requires -Version 5.1
<#
.SYNOPSIS
  Bootstrap video montage stack on Windows (HyperFrames + whisper.cpp + Python).
#>
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

Write-Host "=== Video montage stack setup (Windows) ===" -ForegroundColor Cyan

function Test-Cmd($name) { $null -ne (Get-Command $name -ErrorAction SilentlyContinue) }

# Node 22+
if (-not (Test-Cmd node)) {
    Write-Host "Installing Node.js LTS..."
    winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
} else {
    $v = node -v
    Write-Host "Node: $v"
    if ($v -match "v(\d+)" -and [int]$Matches[1] -lt 22) {
        winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
    }
}

# FFmpeg
if (-not (Test-Cmd ffmpeg)) {
    Write-Host "Installing FFmpeg..."
    winget install Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
}

# Python
if (-not (Test-Cmd py)) {
    Write-Host "Installing Python 3.12..."
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
}

# Refresh PATH
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

# HyperFrames
if (-not (Test-Cmd hyperframes)) {
    Write-Host "Installing HyperFrames..."
    npm install -g hyperframes
}

# whisper-cli — bundled in repo or download
$whisperBin = Join-Path $Root "tools\whisper-cpp\Release"
if (-not (Test-Path (Join-Path $whisperBin "whisper-cli.exe"))) {
    Write-Host "Downloading whisper.cpp b5130 x64..."
    New-Item -ItemType Directory -Force -Path $whisperBin | Out-Null
    $zip = "$env:TEMP\whisper-bin-x64.zip"
    Invoke-WebRequest -Uri "https://github.com/ggml-org/whisper.cpp/releases/download/b5130/whisper-bin-x64.zip" -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath "$env:TEMP\whisper-unpack" -Force
    Copy-Item "$env:TEMP\whisper-unpack\Release\*" $whisperBin -Recurse -Force
}

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$whisperBin*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$whisperBin", "User")
    $env:Path += ";$whisperBin"
    Write-Host "Added whisper-cli to user PATH: $whisperBin"
}

# Python deps
Write-Host "Installing Python packages..."
py -3 -m pip install --upgrade pip --quiet
py -3 -m pip install numpy pillow --quiet

# HyperFrames skills (clear broken proxy if set)
$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
$env:http_proxy = ""
$env:https_proxy = ""
Write-Host "Installing HyperFrames skills..."
$env:HTTP_PROXY = ""; $env:HTTPS_PROXY = ""
npx hyperframes skills 2>&1 | Out-Null
npx hyperframes skills check 2>&1

Write-Host ""
Write-Host "=== Doctor ===" -ForegroundColor Cyan
npx hyperframes doctor 2>&1

Write-Host ""
Write-Host "Next: .\tools\download-whisper-model.ps1  (~3 GB)" -ForegroundColor Yellow
Write-Host "Then:  .\tools\check-env.ps1" -ForegroundColor Yellow
