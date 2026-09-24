#Requires -Version 5.1
param(
    [string]$TakesDir = (Join-Path (Split-Path $PSScriptRoot -Parent) "takes")
)

if (-not (Test-Path $TakesDir)) {
    Write-Error "Takes directory not found: $TakesDir"
    exit 1
}

$ext = @(".mp4", ".mov", ".mkv", ".webm", ".m4v")
$files = Get-ChildItem $TakesDir -File | Where-Object { $ext -contains $_.Extension.ToLower() }

if ($files.Count -eq 0) {
    Write-Host "No video files in $TakesDir"
    exit 0
}

Write-Host "=== Takes inventory ===" -ForegroundColor Cyan
foreach ($f in $files) {
    $probe = ffprobe -v quiet -print_format json -show_format -show_streams $f.FullName | ConvertFrom-Json
    $v = $probe.streams | Where-Object { $_.codec_type -eq "video" } | Select-Object -First 1
    $a = $probe.streams | Where-Object { $_.codec_type -eq "audio" } | Select-Object -First 1
    Write-Host ""
    Write-Host $f.Name -ForegroundColor Yellow
    Write-Host ("  duration: {0:N2}s" -f [double]$probe.format.duration)
    if ($v) {
        Write-Host ("  video:    {0}x{1} @ {2} fps, {3}, {4}/{5}" -f $v.width, $v.height, $v.avg_frame_rate, $v.codec_name, $v.color_range, $v.color_space)
    }
    if ($a) {
        Write-Host ("  audio:    {0}, {1} Hz, {2} ch" -f $a.codec_name, $a.sample_rate, $a.channels)
    }
}
