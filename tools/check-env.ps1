#Requires -Version 5.1
$ErrorActionPreference = "Continue"

Write-Host "=== Montage environment check (Windows) ===" -ForegroundColor Cyan

function Test-Cmd($name, $args = @("--version")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $cmd) { return @{ ok = $false; detail = "not found" } }
    try {
        $out = & $cmd.Source @args 2>&1 | Select-Object -First 1
        return @{ ok = $true; detail = "$($cmd.Source) :: $out" }
    } catch {
        return @{ ok = $false; detail = $_.Exception.Message }
    }
}

$checks = @(
    @{ label = "winget"; fn = { Test-Cmd "winget" @("-v") } },
    @{ label = "node (v22+)"; fn = {
        $r = Test-Cmd "node" @("-v")
        if ($r.ok -and $r.detail -match "v(\d+)") {
            $major = [int]$Matches[1]
            if ($major -lt 22) { $r.ok = $false; $r.detail += " (need v22+)" }
        }
        $r
    }},
    @{ label = "npm"; fn = { Test-Cmd "npm" @("-v") } },
    @{ label = "ffmpeg"; fn = { Test-Cmd "ffmpeg" @("-version") } },
    @{ label = "ffprobe"; fn = { Test-Cmd "ffprobe" @("-version") } },
    @{ label = "whisper-cli"; fn = {
        $r = Test-Cmd "whisper-cli" @("--help")
        if (-not $r.ok) { $r = Test-Cmd "whisper-cli.exe" @("--help") }
        $r
    }},
    @{ label = "hyperframes"; fn = {
        $r = Test-Cmd "hyperframes" @("--version")
        if (-not $r.ok) { $r = Test-Cmd "npx" @("hyperframes", "--version") }
        $r
    }},
    @{ label = "python 3.12+"; fn = {
        $py = Get-Command "py" -ErrorAction SilentlyContinue
        if (-not $py) { return @{ ok = $false; detail = "py launcher not found" } }
        $ver = & py -3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>&1
        $r = @{ ok = $true; detail = "py -3 :: $ver" }
        if ($ver -match "^(\d+)\.(\d+)") {
            if ([int]$Matches[1] -lt 3 -or ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -lt 10)) {
                $r.ok = $false
            }
        }
        $r
    }},
    @{ label = "numpy + Pillow"; fn = {
        $out = & py -3 -c "import numpy, PIL; print(numpy.__version__, PIL.__version__)" 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0) { return @{ ok = $false; detail = $out.Trim() } }
        @{ ok = $true; detail = $out.Trim() }
    }}
)

$failed = 0
foreach ($c in $checks) {
    $r = & $c.fn
    if ($r.ok) {
        Write-Host ("  [OK]   {0,-18} {1}" -f $c.label, $r.detail) -ForegroundColor Green
    } else {
        Write-Host ("  [FAIL] {0,-18} {1}" -f $c.label, $r.detail) -ForegroundColor Red
        $failed++
    }
}

Write-Host ""
Write-Host "Running hyperframes doctor..." -ForegroundColor Cyan
npx hyperframes doctor 2>&1 | Select-String "Version|Node|FFmpeg|FFprobe|whisper|Chrome|Docker|TTS|BGM"

if ($failed -gt 0) {
    Write-Host "`n$failed check(s) failed." -ForegroundColor Yellow
    exit 1
}
Write-Host "`nAll local checks passed." -ForegroundColor Green
