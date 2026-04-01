[CmdletBinding()]
param(
    [ValidateSet('gui', 'tui', 'both')]
    [string]$Target = 'both',
    [ValidateSet('onefile', 'onedir')]
    [string]$Layout = 'onefile',
    [switch]$Clean,
    [switch]$IncludeEnv,
    [switch]$SkipDependencyInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$distRoot = Join-Path $repoRoot 'dist'
$buildRoot = Join-Path $repoRoot 'build'
$specRoot = Join-Path $buildRoot 'spec'

function Resolve-Python {
    param([string]$Root)

    $venvPython = Join-Path $Root '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $venvPython) {
        return $venvPython
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        return $pythonCmd.Source
    }

    throw 'Python executable not found. Activate your virtual environment or install Python.'
}

function Install-BuildDependencies {
    param(
        [string]$PythonExe,
        [string]$Root
    )

    Write-Host '[1/4] Installing build dependencies...' -ForegroundColor Cyan
    & $PythonExe -m pip install -r (Join-Path $Root 'requirements-build.txt')
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to install build dependencies.'
    }
}

function Invoke-PyInstallerBuild {
    param(
        [string]$PythonExe,
        [string]$Root,
        [string]$EntryScript,
        [string]$AppName,
        [string]$BundleLayout,
        [bool]$Windowed,
        [bool]$DoClean,
        [bool]$BundleEnv
    )

    Write-Host "[2/4] Building $AppName..." -ForegroundColor Cyan

    $separator = ';'
    $chainsawSource = Join-Path $Root 'chainsaw'
    $sigmaSource = Join-Path $Root 'sigma'
    $realtimeEnvSource = Join-Path $Root '.env.realtime.sample'
    $bgImageSource = Join-Path $Root 'bg.jpg'
    $entryScriptPath = Join-Path $Root $EntryScript
    $appDistRoot = Join-Path $distRoot $AppName

    if ($DoClean -and (Test-Path -LiteralPath $appDistRoot)) {
        Remove-Item -LiteralPath $appDistRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $appDistRoot -Force | Out-Null

    $args = @(
        '-m', 'PyInstaller',
        '--noconfirm',
        '--name', $AppName,
        '--distpath', $appDistRoot,
        '--workpath', $buildRoot,
        '--specpath', $specRoot,
        '--add-data', "${chainsawSource}${separator}chainsaw",
        '--add-data', "${sigmaSource}${separator}sigma",
        '--add-data', "${realtimeEnvSource}${separator}.",
        '--add-data', "${bgImageSource}${separator}."
    )

    if ($BundleLayout -eq 'onefile') {
        $args += '--onefile'
    }
    else {
        $args += '--onedir'
    }

    if ($DoClean) {
        $args += '--clean'
    }

    if ($Windowed) {
        $args += '--windowed'
    }
    else {
        $args += '--console'
    }

    if ($BundleEnv -and (Test-Path -LiteralPath (Join-Path $Root '.env'))) {
        $envSource = Join-Path $Root '.env'
        $args += @('--add-data', "${envSource}${separator}.")
    }

    $args += $entryScriptPath

    & $PythonExe @args
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed for $AppName."
    }
}

function Copy-DistributionAssets {
    param(
        [string]$Root,
        [string]$AppName,
        [bool]$BundleEnv
    )

    Write-Host "[3/4] Copying runtime assets for $AppName..." -ForegroundColor Cyan

    $appDir = Join-Path $distRoot $AppName
    $nestedAppDir = Join-Path $appDir $AppName
    if (Test-Path -LiteralPath $nestedAppDir) {
        $appDir = $nestedAppDir
    }

    $itemsToCopy = @(
        'Export-AllEvtx.ps1',
        'Export-AllEvtxRMM.ps1',
        'ChainsawIntegration.ps1',
        'README.md',
        'QUICKSTART.md'
    )

    foreach ($item in $itemsToCopy) {
        $sourcePath = Join-Path $Root $item
        if (Test-Path -LiteralPath $sourcePath) {
            Copy-Item -LiteralPath $sourcePath -Destination $appDir -Force
        }
    }

    if ($BundleEnv -and (Test-Path -LiteralPath (Join-Path $Root '.env'))) {
        Copy-Item -LiteralPath (Join-Path $Root '.env') -Destination $appDir -Force
    }
}

function Write-BuildSummary {
    param([string[]]$BuiltApps)

    Write-Host '[4/4] Build complete.' -ForegroundColor Green
    foreach ($app in $BuiltApps) {
        $path = Join-Path $distRoot $app
        $exePath = Join-Path $path ("{0}.exe" -f $app)
        $nestedExePath = Join-Path (Join-Path $path $app) ("{0}.exe" -f $app)
        if (Test-Path -LiteralPath $exePath) {
            Write-Host "  - $app => $exePath"
        }
        elseif (Test-Path -LiteralPath $nestedExePath) {
            Write-Host "  - $app => $nestedExePath"
        }
        else {
            Write-Host "  - $app => $path"
        }
    }

    Write-Host ''
    if ($Layout -eq 'onefile') {
        Write-Host 'Tip: onefile builds are preferred for UNC/network-share execution because bundled DLLs extract locally before launch.' -ForegroundColor Yellow
    }
    else {
        Write-Host 'Tip: Keep your .env next to the .exe unless you bundled it with -IncludeEnv.' -ForegroundColor Yellow
    }
}

Push-Location $repoRoot
try {
    $pythonExe = Resolve-Python -Root $repoRoot

    if (-not $SkipDependencyInstall) {
        Install-BuildDependencies -PythonExe $pythonExe -Root $repoRoot
    }

    $builtApps = @()

    if ($Target -in @('gui', 'both')) {
        Invoke-PyInstallerBuild -PythonExe $pythonExe -Root $repoRoot -EntryScript 'chainsaw_gui.py' -AppName 'EVTXRipperGUI' -BundleLayout $Layout -Windowed $true -DoClean:$Clean -BundleEnv:$IncludeEnv
        Copy-DistributionAssets -Root $repoRoot -AppName 'EVTXRipperGUI' -BundleEnv:$IncludeEnv
        $builtApps += 'EVTXRipperGUI'
    }

    if ($Target -in @('tui', 'both')) {
        Invoke-PyInstallerBuild -PythonExe $pythonExe -Root $repoRoot -EntryScript 'chainsaw_frontend.py' -AppName 'EVTXRipperTUI' -BundleLayout $Layout -Windowed $false -DoClean:$Clean -BundleEnv:$IncludeEnv
        Copy-DistributionAssets -Root $repoRoot -AppName 'EVTXRipperTUI' -BundleEnv:$IncludeEnv
        $builtApps += 'EVTXRipperTUI'
    }

    Write-BuildSummary -BuiltApps $builtApps
}
finally {
    Pop-Location
}
