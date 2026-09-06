$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Version = "0.5.0"
$PinnedMshv = "8f93eb3e25056f0cb18699ef6c3bef3998c52cdf"

function Assert-LastExit([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed with exit code $LASTEXITCODE" }
}

$Python = if ($env:Python_ROOT_DIR) { Join-Path $env:Python_ROOT_DIR "python.exe" } else { (Get-Command python.exe -ErrorAction Stop).Source }
if (-not (Test-Path $Python)) { throw "Python executable not found: $Python" }
& $Python -c "import sys; print(sys.executable); print(sys.version); assert sys.version_info >= (3,10)"
Assert-LastExit "Python >=3.10 validation"

Write-Host "== DXWeaver $Version native Windows build ==" -ForegroundColor Cyan

# 1. Mission-critical native core: Release build + mandatory CTest.
Remove-Item -Recurse -Force build-native -ErrorAction SilentlyContinue
cmake -S . -B build-native -G "MinGW Makefiles" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
Assert-LastExit "CMake configure"
cmake --build build-native --config Release -j 2
Assert-LastExit "CMake native core build"
ctest --test-dir build-native -C Release --output-on-failure --timeout 120
Assert-LastExit "CTest native QA"

# 2. Clone audited radio/DSP foundation and inject DXWeaver in-process core.
Remove-Item -Recurse -Force mshv-upstream -ErrorAction SilentlyContinue
git clone --filter=blob:none https://github.com/LZ2HV/MSHV.git mshv-upstream
Assert-LastExit "MSHV clone"
git -C mshv-upstream checkout $PinnedMshv
Assert-LastExit "MSHV pinned checkout"
$Actual = (git -C mshv-upstream rev-parse HEAD).Trim()
if ($Actual -ne $PinnedMshv) { throw "Unexpected MSHV source $Actual" }

& $Python -m py_compile mshv/apply_dxweaver_v050_patch.py
Assert-LastExit "DXWeaver patch syntax"
& $Python mshv/apply_dxweaver_v050_patch.py mshv-upstream
Assert-LastExit "DXWeaver native integration patch"
git -C mshv-upstream diff --check
Assert-LastExit "Patched source diff check"

# 3. Build the single native DXWeaver executable using the upstream Qt/qmake project.
$qmake = (Get-Command qmake.exe -ErrorAction Stop).Source
$make = (Get-Command mingw32-make.exe -ErrorAction Stop).Source
Push-Location mshv-upstream
& $qmake MSHV_WIN64.pro "CONFIG+=release"
Assert-LastExit "qmake"
& $make -j2
Assert-LastExit "DXWeaver Qt build"
Pop-Location

$Exe = Join-Path $Root "mshv-upstream\bin\DXWeaver.exe"
if (-not (Test-Path $Exe)) { throw "DXWeaver.exe was not produced" }

# 4. Stage application resources and runtime.
$Pkg = Join-Path $Root "dxweaver-package"
Remove-Item -Recurse -Force $Pkg -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $Pkg | Out-Null
Copy-Item "mshv-upstream\bin\*" $Pkg -Recurse -Force
Remove-Item -Recurse -Force "$Pkg\log", "$Pkg\AllTxtMonthly" -ErrorAction SilentlyContinue
Get-ChildItem $Pkg -Recurse -File -Include *.ttf,*.otf,*.woff,*.woff2 -ErrorAction SilentlyContinue | Remove-Item -Force

$windeployqt = (Get-Command windeployqt.exe -ErrorAction Stop).Source
& $windeployqt --release --compiler-runtime --no-translations --dir $Pkg "$Pkg\DXWeaver.exe"
if ($LASTEXITCODE -ne 0) {
    Write-Warning "windeployqt returned $LASTEXITCODE; validating and completing runtime explicitly"
}

$qtBin = Split-Path -Parent $qmake
$qtRoot = Split-Path -Parent $qtBin
$qtPlugins = Join-Path $qtRoot "plugins"
$mingwBin = Split-Path -Parent $make
foreach ($dll in @("Qt5Core.dll","Qt5Gui.dll","Qt5Network.dll","Qt5WebSockets.dll","Qt5Widgets.dll")) {
    if (-not (Test-Path "$Pkg\$dll")) { Copy-Item (Join-Path $qtBin $dll) $Pkg -Force }
}
New-Item -ItemType Directory -Force "$Pkg\platforms" | Out-Null
if (-not (Test-Path "$Pkg\platforms\qwindows.dll")) {
    Copy-Item (Join-Path $qtPlugins "platforms\qwindows.dll") "$Pkg\platforms\qwindows.dll" -Force
}
foreach ($dll in @("libgcc_s_seh-1.dll","libstdc++-6.dll","libwinpthread-1.dll")) {
    if (-not (Test-Path "$Pkg\$dll")) { Copy-Item (Join-Path $mingwBin $dll) $Pkg -Force }
}

# GPL/attribution stays with the derivative product even though its visual identity is DXWeaver.
Copy-Item "mshv-upstream\COPYING.txt" "$Pkg\COPYING-GPL-3.0.txt" -Force
@"
DXWeaver 0.5.0
Native FT8 automation and cockpit project.

The radio/DSP foundation is derived from MSHV and distributed under GPL-3.0.
Official upstream: https://github.com/LZ2HV/MSHV
Pinned upstream commit: $PinnedMshv
DXWeaver source: https://github.com/brunobdantas/dxweaver
"@ | Set-Content "$Pkg\DXWEAVER-SOURCE-NOTICE.txt" -Encoding UTF8

# 5. Smoke-test packaged GUI. Loader/startup failure is a build failure.
$p = Start-Process -FilePath "$Pkg\DXWeaver.exe" -WorkingDirectory $Pkg -PassThru
Start-Sleep -Seconds 6
if ($p.HasExited) {
    if ($p.ExitCode -ne 0) { throw "DXWeaver packaged smoke test exited with code $($p.ExitCode)" }
} else {
    Stop-Process -Id $p.Id -Force
}

# 6. Corresponding source archive for GPL compliance/reproducibility.
cmd /c "git -C mshv-upstream diff --binary > dxweaver-package\DXWeaver-0.5.0-MSHV.patch"
Assert-LastExit "Export native patch"
$SourceStage = Join-Path $Root "source-stage"
Remove-Item -Recurse -Force $SourceStage -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force "$SourceStage\dxweaver\src" | Out-Null
Copy-Item "src\native" "$SourceStage\dxweaver\src\native" -Recurse -Force
Copy-Item "mshv\apply_dxweaver_v050_patch.py" "$SourceStage\dxweaver\" -Force
Copy-Item "CMakeLists.txt" "$SourceStage\dxweaver\" -Force
Copy-Item "mshv-upstream" "$SourceStage\mshv-upstream" -Recurse -Force
Remove-Item -Recurse -Force "$SourceStage\mshv-upstream\.git", "$SourceStage\mshv-upstream\build", "$SourceStage\mshv-upstream\bin" -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force installer-output | Out-Null
tar.exe -a -c -f "installer-output\DXWeaver-0.5.0-Source.zip" -C $SourceStage .
Assert-LastExit "Source archive"

# 7. Per-user installer.
$Iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $Iscc) {
    foreach ($candidate in @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $candidate) { $Iscc = $candidate; break }
    }
}
if (-not $Iscc) { throw "Inno Setup 6 / ISCC.exe not found" }
& $Iscc "installer\DXWeaver-0.5.0.iss"
Assert-LastExit "Inno Setup"

$Setup = "installer-output\DXWeaver-0.5.0-Setup.exe"
if (-not (Test-Path $Setup)) { throw "Installer was not produced: $Setup" }
$Hash = Get-FileHash $Setup -Algorithm SHA256
"$($Hash.Hash)  DXWeaver-0.5.0-Setup.exe" | Set-Content "installer-output\DXWeaver-0.5.0-SHA256.txt" -Encoding ascii
Write-Host "PASS: $Setup" -ForegroundColor Green
Write-Host "SHA256 $($Hash.Hash)" -ForegroundColor Green
