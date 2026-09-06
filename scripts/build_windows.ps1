$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Version = "0.5.1"
$PinnedMshv = "8f93eb3e25056f0cb18699ef6c3bef3998c52cdf"
$Patcher = "mshv/apply_dxweaver_v051_patch.py"

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

# Product code must never carry the operator callsign as configuration.
$Hardcoded = Select-String -Path "src\native\mshv_bridge\DxwMshvBridge.h","src\native\mshv_bridge\DxwMshvBridge.cpp",$Patcher -SimpleMatch '"PU2BRU"' -ErrorAction SilentlyContinue
if ($Hardcoded) { throw "Hardcoded station identity detected in product integration" }

# UI source gate: production widgets themselves may not use absolute panel
# geometry/z-order. The patcher intentionally contains those token strings in
# its own fail-closed verifier, so it is validated after application below.
$UiSources = @(
    "src\native\mshv_bridge\DxwControlPanel.cpp",
    "src\native\mshv_bridge\DxwCandidateMatrix.cpp"
)
$AbsolutePanelLayout = Select-String -Path $UiSources -Pattern "dxwPanel->setGeometry|dxwPanel->move\(|dxwPanel->raise\(" -ErrorAction SilentlyContinue
if ($AbsolutePanelLayout) { throw "Absolute DXWeaver panel geometry/z-order detected" }
if (-not (Test-Path "src\native\mshv_bridge\DxTheme.qss")) { throw "DxTheme.qss source is missing" }

# 2. Clone audited radio/DSP foundation and inject DXWeaver in-process core.
Remove-Item -Recurse -Force mshv-upstream -ErrorAction SilentlyContinue
git clone --filter=blob:none https://github.com/LZ2HV/MSHV.git mshv-upstream
Assert-LastExit "MSHV clone"
git -C mshv-upstream checkout $PinnedMshv
Assert-LastExit "MSHV pinned checkout"
$Actual = (git -C mshv-upstream rev-parse HEAD).Trim()
if ($Actual -ne $PinnedMshv) { throw "Unexpected MSHV source $Actual" }

& $Python -m py_compile $Patcher
Assert-LastExit "DXWeaver patch syntax"
& $Python $Patcher mshv-upstream
Assert-LastExit "DXWeaver native integration patch"
git -C mshv-upstream diff --check
Assert-LastExit "Patched source diff check"

$ProText = Get-Content "mshv-upstream\MSHV_WIN64.pro" -Raw
if ($ProText -notmatch [regex]::Escape("QMAKE_CXXFLAGS += -std=gnu++11 -pedantic-errors")) {
    throw "Legacy MSHV gnu++11 dialect gate failed"
}
if ($ProText -match "gnu\+\+17") { throw "C++17 leaked into legacy MSHV project" }
Write-Host "PASS: legacy radio/DSP remains gnu++11; dxw_core is strict C++11" -ForegroundColor Green

# Structural UI gate against the fully patched upstream source. This catches a
# build that compiles but floats the DXWeaver controls behind the waterfall.
$PatchedMain = Get-Content "mshv-upstream\src\main_ms.cpp" -Raw
foreach ($requiredLayout in @(
    "V_l->insertWidget(0, dxwPanel);",
    "V_l->insertWidget(1, dxwCandidates);",
    "candidateMatrixChanged(QStringList,QString)",
    "DxwControlPanel::applyGlobalTheme(App_Path)",
    "dsty = true; // DXWeaver owns a single dark visual identity."
)) {
    if ($PatchedMain -notmatch [regex]::Escape($requiredLayout)) { throw "UI hierarchy contract missing: $requiredLayout" }
}
if ($PatchedMain -match "dxwPanel->setGeometry|dxwPanel->raise\(") { throw "Patched main window still contains floating DXWeaver panel geometry" }
$PatchedTheme = "mshv-upstream\bin\settings\resources\dxweaver\DxTheme.qss"
if (-not (Test-Path $PatchedTheme)) { throw "Patched upstream theme resource missing" }
$ThemeText = Get-Content $PatchedTheme -Raw
foreach ($token in @("#0B0F14", "#111821", "#263341", "#E6EDF3", "#B63A3A", "QTableWidget#dxwCandidatesTable")) {
    if ($ThemeText -notmatch [regex]::Escape($token)) { throw "DXWeaver design-system token missing: $token" }
}
Write-Host "PASS: DXWeaver layout, Candidate Matrix and dark-theme contracts" -ForegroundColor Green

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
# Never ship the upstream author's sample log into the user's history index.
Remove-Item -Recurse -Force "$Pkg\log", "$Pkg\AllTxtMonthly" -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force "$Pkg\log" | Out-Null
Get-ChildItem $Pkg -Recurse -File -Include *.ttf,*.otf,*.woff,*.woff2 -ErrorAction SilentlyContinue | Remove-Item -Force

if (-not (Test-Path "$Pkg\settings\database\cty.dat")) { throw "cty.dat missing from package" }
if (-not (Test-Path "$Pkg\settings\resources\dxweaver\DxTheme.qss")) { throw "DxTheme.qss missing from package" }

$windeployqt = (Get-Command windeployqt.exe -ErrorAction Stop).Source
& $windeployqt --release --compiler-runtime --no-translations --dir $Pkg "$Pkg\DXWeaver.exe"
if ($LASTEXITCODE -ne 0) {
    Write-Warning "windeployqt returned $LASTEXITCODE; validating and completing runtime explicitly"
}

$qtBin = Split-Path -Parent $qmake
$qtRoot = Split-Path -Parent $qtBin
$qtPlugins = Join-Path $qtRoot "plugins"
$mingwBin = Split-Path -Parent $make
foreach ($dll in @("Qt5Core.dll","Qt5Gui.dll","Qt5Network.dll","Qt5WebSockets.dll","Qt5Widgets.dll","Qt5Sql.dll")) {
    if (-not (Test-Path "$Pkg\$dll")) { Copy-Item (Join-Path $qtBin $dll) $Pkg -Force }
}
New-Item -ItemType Directory -Force "$Pkg\platforms" | Out-Null
if (-not (Test-Path "$Pkg\platforms\qwindows.dll")) {
    Copy-Item (Join-Path $qtPlugins "platforms\qwindows.dll") "$Pkg\platforms\qwindows.dll" -Force
}
New-Item -ItemType Directory -Force "$Pkg\sqldrivers" | Out-Null
if (-not (Test-Path "$Pkg\sqldrivers\qsqlite.dll")) {
    Copy-Item (Join-Path $qtPlugins "sqldrivers\qsqlite.dll") "$Pkg\sqldrivers\qsqlite.dll" -Force
}
foreach ($dll in @("libgcc_s_seh-1.dll","libstdc++-6.dll","libwinpthread-1.dll")) {
    if (-not (Test-Path "$Pkg\$dll")) { Copy-Item (Join-Path $mingwBin $dll) $Pkg -Force }
}
foreach ($required in @(
    "DXWeaver.exe",
    "Qt5Core.dll",
    "Qt5Widgets.dll",
    "Qt5Sql.dll",
    "platforms\qwindows.dll",
    "sqldrivers\qsqlite.dll",
    "settings\database\cty.dat",
    "settings\resources\dxweaver\DxTheme.qss"
)) {
    if (-not (Test-Path (Join-Path $Pkg $required))) { throw "Packaged runtime missing: $required" }
}

# GPL/attribution stays with the derivative product even though its visual identity is DXWeaver.
Copy-Item "mshv-upstream\COPYING.txt" "$Pkg\COPYING-GPL-3.0.txt" -Force
@"
DXWeaver $Version
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
Write-Host "PASS: packaged GUI smoke test" -ForegroundColor Green

# 6. Corresponding source archive for GPL compliance/reproducibility.
cmd /c "git -C mshv-upstream diff --binary > dxweaver-package\DXWeaver-$Version-MSHV.patch"
Assert-LastExit "Export native patch"
$SourceStage = Join-Path $Root "source-stage"
Remove-Item -Recurse -Force $SourceStage -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force "$SourceStage\dxweaver\src" | Out-Null
Copy-Item "src\native" "$SourceStage\dxweaver\src\native" -Recurse -Force
Copy-Item $Patcher "$SourceStage\dxweaver\" -Force
Copy-Item "CMakeLists.txt" "$SourceStage\dxweaver\" -Force
Copy-Item "mshv-upstream" "$SourceStage\mshv-upstream" -Recurse -Force
Remove-Item -Recurse -Force "$SourceStage\mshv-upstream\.git", "$SourceStage\mshv-upstream\build", "$SourceStage\mshv-upstream\bin" -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force installer-output | Out-Null
tar.exe -a -c -f "installer-output\DXWeaver-$Version-Source.zip" -C $SourceStage .
Assert-LastExit "Source archive"
if (-not (Test-Path "installer-output\DXWeaver-$Version-Source.zip")) { throw "GPL source archive missing" }

# 7. Per-user installer.
$Iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $Iscc) {
    foreach ($candidate in @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $candidate) { $Iscc = $candidate; break }
    }
}
if (-not $Iscc) { throw "Inno Setup 6 / ISCC.exe not found" }
& $Iscc "installer\DXWeaver-$Version.iss"
Assert-LastExit "Inno Setup"

$Setup = "installer-output\DXWeaver-$Version-Setup.exe"
if (-not (Test-Path $Setup)) { throw "Installer was not produced: $Setup" }
$Hash = Get-FileHash $Setup -Algorithm SHA256
"$($Hash.Hash)  DXWeaver-$Version-Setup.exe" | Set-Content "installer-output\DXWeaver-$Version-SHA256.txt" -Encoding ascii
Write-Host "PASS: $Setup" -ForegroundColor Green
Write-Host "SHA256 $($Hash.Hash)" -ForegroundColor Green
