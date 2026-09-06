$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Version = "0.4.1"
Write-Host "== DXWeaver $Version Windows build ==" -ForegroundColor Cyan

python -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { throw "pip bootstrap failed with exit code $LASTEXITCODE" }
python -m pip install . pytest pyinstaller
if ($LASTEXITCODE -ne 0) { throw "dependency install failed with exit code $LASTEXITCODE" }
$env:PYTHONPATH = "src"
python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "pytest failed with exit code $LASTEXITCODE" }

Remove-Item -Recurse -Force build, dist, installer-output -ErrorAction SilentlyContinue
python -m PyInstaller --noconfirm --clean --onefile --noconsole `
  --name DXWeaver `
  --paths src `
  --collect-data autoft8 `
  scripts/dxweaver_launcher.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

& ".\dist\DXWeaver.exe" --config "config.example.json" --self-test
if ($LASTEXITCODE -ne 0) { throw "DXWeaver.exe self-test failed with exit code $LASTEXITCODE" }

$IsccFromPath = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
$IsccCandidates = @(
  $(if ($IsccFromPath) { $IsccFromPath.Source }),
  "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
  "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
  "$env:ChocolateyInstall\bin\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) }
$Iscc = $IsccCandidates | Select-Object -First 1
if (-not $Iscc) {
  $SearchRoots = @("${env:ProgramFiles(x86)}", "$env:ProgramFiles", "$env:ChocolateyInstall") | Where-Object { $_ -and (Test-Path $_) }
  foreach ($RootPath in $SearchRoots) {
    $Found = Get-ChildItem -Path $RootPath -Filter "ISCC.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($Found) { $Iscc = $Found.FullName; break }
  }
}
if (-not $Iscc) { throw "Inno Setup 6 / ISCC.exe not found" }
Write-Host "Using Inno Setup compiler: $Iscc" -ForegroundColor Cyan

& $Iscc "installer\DXWeaver.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed with exit code $LASTEXITCODE" }
$Setup = "installer-output\DXWeaver-$Version-Setup.exe"
if (-not (Test-Path $Setup)) { throw "Installer was not produced: $Setup" }

$Hash = Get-FileHash $Setup -Algorithm SHA256
"$($Hash.Hash)  DXWeaver-$Version-Setup.exe" | Set-Content "installer-output\SHA256.txt" -Encoding ascii
Write-Host "Built $Setup" -ForegroundColor Green
Write-Host "SHA256 $($Hash.Hash)" -ForegroundColor Green
