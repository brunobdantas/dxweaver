$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Version = "0.3.0"
Write-Host "== DXWeaver $Version Windows build ==" -ForegroundColor Cyan

python -m pip install --upgrade pip setuptools wheel
python -m pip install . pytest pyinstaller
$env:PYTHONPATH = "src"
python -m pytest -q

Remove-Item -Recurse -Force build, dist, installer-output -ErrorAction SilentlyContinue
python -m PyInstaller --noconfirm --clean --onefile --noconsole `
  --name DXWeaver `
  --paths src `
  --collect-data autoft8 `
  src/autoft8/__main__.py

$IsccCandidates = @(
  "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
  "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)
$Iscc = $IsccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Iscc) { throw "Inno Setup 6 / ISCC.exe not found" }

& $Iscc "installer\DXWeaver.iss"
$Setup = "installer-output\DXWeaver-$Version-Setup.exe"
if (-not (Test-Path $Setup)) { throw "Installer was not produced: $Setup" }

$Hash = Get-FileHash $Setup -Algorithm SHA256
"$($Hash.Hash)  DXWeaver-$Version-Setup.exe" | Set-Content "installer-output\SHA256.txt" -Encoding ascii
Write-Host "Built $Setup" -ForegroundColor Green
Write-Host "SHA256 $($Hash.Hash)" -ForegroundColor Green
