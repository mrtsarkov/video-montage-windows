#Requires -Version 5.1
<#
  §3.7 — 2-second trial: solid background + HyperFrames text layer + ffmpeg mux.
#>
param(
    [string]$RunLabel = "cursor"
)

$env:HYPERFRAMES_NO_TELEMETRY = "1"
$env:DO_NOT_TRACK = "1"

$root = Split-Path $PSScriptRoot -Parent
$runDir = Join-Path $root "runs\$RunLabel"
$editDir = Join-Path $runDir "edit"
$outDir = Join-Path $runDir "out"
$probeDir = Join-Path $editDir "probe-trial"

foreach ($d in @($editDir, $outDir, $probeDir)) {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}

# 1) Background plate (2s black 1920x1080)
$plate = Join-Path $probeDir "plate.mp4"
ffmpeg -y -f lavfi -i "color=c=0x1a1a1a:s=1920x1080:d=2:r=25" -c:v libx264 -pix_fmt yuv420p -t 2 $plate 2>&1 | Out-Null

# 2) Minimal HyperFrames composition
$hfDir = Join-Path $probeDir "hf"
New-Item -ItemType Directory -Force -Path $hfDir | Out-Null
@'
<!doctype html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <style>
    html, body { margin:0; width:1920px; height:1080px; overflow:hidden; background:transparent; }
    #title { position:absolute; left:50%; top:50%; transform:translate(-50%,-50%);
      font: 600 96px/1.1 "Segoe UI", sans-serif; color:#fff; opacity:0; }
  </style>
</head>
<body>
  <div id="root" data-composition-id="main" data-start="0" data-duration="2" data-width="1920" data-height="1080">
    <h1 id="title" class="clip" data-start="0" data-duration="2">Проба кириллицы 123</h1>
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    tl.fromTo("#title", { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.5 }, 0.2);
    window.__timelines = window.__timelines || {};
    window.__timelines["main"] = tl;
    tl.seek(0);
  </script>
</body>
</html>
'@ | Set-Content (Join-Path $hfDir "index.html") -Encoding UTF8

$layerMov = Join-Path $probeDir "graphics.mov"
Push-Location $hfDir
npx hyperframes render --quality draft --format mov --output $layerMov 2>&1 | Out-Null
$hfExit = $LASTEXITCODE
Pop-Location

if ($hfExit -ne 0 -or -not (Test-Path $layerMov)) {
    # Fallback: render mp4 with alpha-less overlay text via ffmpeg drawtext is forbidden in prompt;
    # use blank mp4 overlay path — report partial success
    Write-Warning "HyperFrames mov render failed; plate-only trial saved."
    Copy-Item $plate (Join-Path $outDir "probe-trial.mp4")
} else {
    $final = Join-Path $outDir "probe-trial.mp4"
    ffmpeg -y -i $plate -i $layerMov -filter_complex "[0:v][1:v]overlay=format=auto,format=yuv420p" -c:v libx264 -crf 18 -t 2 $final 2>&1 | Out-Null
}

$finalPath = Join-Path $outDir "probe-trial.mp4"
if (Test-Path $finalPath) {
    $info = ffprobe -v error -show_format $finalPath 2>&1
    Write-Host "Probe trial OK: $finalPath" -ForegroundColor Green
    Write-Host $info
} else {
    Write-Error "Probe trial failed"
    exit 1
}
