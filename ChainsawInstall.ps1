#Requires -Version 5.1
<#!
.SYNOPSIS
    Install Git (optional), sync Sigma from git, and install Chainsaw from GitHub releases.

.DESCRIPTION
    - Ensures Git is available (installs Git for Windows if missing).
    - Clones or updates Sigma from SigmaHQ/sigma.
    - Downloads Chainsaw Windows release zip and extracts chainsaw.exe.

.EXAMPLE
    .\ChainsawInstall.ps1

.EXAMPLE
    .\ChainsawInstall.ps1 -ChainsawVersion v2.11.0
#>

[CmdletBinding()]
param(
    [string]$BaseFolder = 'C:\Program Files\socfortress\chainsaw',
    [string]$SigmaRepoUrl = 'https://github.com/SigmaHQ/sigma.git',
    [string]$SigmaDestinationFolder,
    [string]$ChainsawRepoApi = 'https://api.github.com/repos/WithSecureLabs/chainsaw/releases',
    [string]$ChainsawVersion = 'latest',
    [switch]$ForceReinstallChainsaw,
    [switch]$SkipGitInstall,
    [switch]$InstallVcRedist
)

$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.IO.Compression.FileSystem

function Ensure-Directory {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        $null = New-Item -Path $Path -ItemType Directory -Force
    }
}

function Expand-ZipArchive {
    param(
        [Parameter(Mandatory = $true)][string]$ZipPath,
        [Parameter(Mandatory = $true)][string]$DestinationPath,
        [string[]]$IncludeEntryPrefixes
    )

    if (Test-Path -LiteralPath $DestinationPath) {
        Remove-Item -LiteralPath $DestinationPath -Recurse -Force
    }

    $null = New-Item -Path $DestinationPath -ItemType Directory -Force

    $archive = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        foreach ($entry in $archive.Entries) {
            if ([string]::IsNullOrWhiteSpace($entry.FullName)) {
                continue
            }

            $entryPath = $entry.FullName.Replace('\\', '/')

            if ($IncludeEntryPrefixes -and $IncludeEntryPrefixes.Count -gt 0) {
                $matchesPrefix = $false
                foreach ($prefix in $IncludeEntryPrefixes) {
                    if ([string]::IsNullOrWhiteSpace($prefix)) {
                        continue
                    }

                    $normalizedPrefix = $prefix.Replace('\\', '/').Trim('/').ToLowerInvariant()
                    $normalizedEntry = $entryPath.Trim('/').ToLowerInvariant()

                    if ($normalizedEntry.StartsWith($normalizedPrefix + '/')) {
                        $matchesPrefix = $true
                        break
                    }
                }

                if (-not $matchesPrefix) {
                    continue
                }
            }

            $targetPath = Join-Path -Path $DestinationPath -ChildPath $entryPath
            $targetFullPath = [System.IO.Path]::GetFullPath($targetPath)
            $destinationFullPath = [System.IO.Path]::GetFullPath($DestinationPath)

            # Guard against zip-slip by ensuring extraction stays under destination root.
            if (-not $targetFullPath.StartsWith($destinationFullPath, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Refusing to extract path outside destination: $($entry.FullName)"
            }

            if ([string]::IsNullOrEmpty($entry.Name)) {
                $null = New-Item -Path $targetFullPath -ItemType Directory -Force
                continue
            }

            $parent = Split-Path -Path $targetFullPath -Parent
            if (-not (Test-Path -LiteralPath $parent)) {
                $null = New-Item -Path $parent -ItemType Directory -Force
            }

            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $targetFullPath, $true)
        }
    }
    finally {
        if ($archive) {
            $archive.Dispose()
        }
    }
}

function Ensure-Git {
    param([switch]$SkipInstall)

    $gitCmd = Get-Command git -ErrorAction SilentlyContinue
    if ($gitCmd) {
        return $gitCmd.Source
    }

    if ($SkipInstall) {
        throw 'Git is not installed and -SkipGitInstall was requested.'
    }

    $downloadLink = 'https://github.com/git-for-windows/git/releases/download/v2.40.0.windows.1/Git-2.40.0-64-bit.exe'
    $gitInstaller = Join-Path -Path $env:TEMP -ChildPath 'git-latest-windows.exe'

    Write-Host 'Git not found. Downloading Git for Windows...'
    Invoke-WebRequest -Uri $downloadLink -OutFile $gitInstaller -UseBasicParsing

    Write-Host 'Installing Git for Windows...'
    Start-Process -FilePath $gitInstaller -ArgumentList '/VERYSILENT', '/NORESTART', '/LOG=git_install.log' -NoNewWindow -Wait

    Remove-Item -Path $gitInstaller -Force -ErrorAction SilentlyContinue

    $gitBinPath = "${env:ProgramFiles}\Git\cmd"
    $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')

    if ($machinePath -notlike "*$gitBinPath*") {
        [Environment]::SetEnvironmentVariable('Path', "$machinePath;$gitBinPath", 'Machine')
    }

    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine')

    $gitCmd = Get-Command git -ErrorAction SilentlyContinue
    if (-not $gitCmd) {
        throw 'Git installation completed, but git is still not available in PATH.'
    }

    return $gitCmd.Source
}

function Test-VcRedistInstalled {
    $registryPaths = @(
        'HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64'
    )

    foreach ($path in $registryPaths) {
        $item = Get-ItemProperty -Path $path -ErrorAction SilentlyContinue
        if ($item -and $item.Installed -eq 1) {
            return $true
        }
    }

    return $false
}

function Ensure-VcRedist {
    param([switch]$Install)

    if (Test-VcRedistInstalled) {
        return
    }

    if (-not $Install) {
        Write-Warning 'Microsoft Visual C++ Redistributable x64 does not appear to be installed.'
        Write-Warning 'Chainsaw Windows MSVC builds may fail with exit code -1073741515 (0xC0000135) until the VC++ runtime is installed.'
        Write-Warning 'Rerun this installer with -InstallVcRedist or install vc_redist.x64.exe separately.'
        return
    }

    $vcUrl = 'https://aka.ms/vs/17/release/vc_redist.x64.exe'
    $vcInstaller = Join-Path -Path $env:TEMP -ChildPath 'vc_redist.x64.exe'

    Write-Host 'Downloading Microsoft Visual C++ Redistributable x64...'
    Invoke-WebRequest -Uri $vcUrl -OutFile $vcInstaller -UseBasicParsing

    try {
        Write-Host 'Installing Microsoft Visual C++ Redistributable x64...'
        Start-Process -FilePath $vcInstaller -ArgumentList '/install', '/quiet', '/norestart' -Wait -NoNewWindow
    }
    finally {
        Remove-Item -LiteralPath $vcInstaller -Force -ErrorAction SilentlyContinue
    }

    if (-not (Test-VcRedistInstalled)) {
        throw 'VC++ Redistributable installation did not verify successfully.'
    }
}

function Clone-OrUpdateRepo {
    param(
        [Parameter(Mandatory = $true)][string]$RepoUrl,
        [Parameter(Mandatory = $true)][string]$Destination,
        [Parameter(Mandatory = $true)][string]$GitExe
    )

    if (Test-Path -LiteralPath $Destination) {
        if (Test-Path -LiteralPath (Join-Path -Path $Destination -ChildPath '.git')) {
            Write-Host "Updating existing repo: $Destination"
            & $GitExe -C $Destination pull --ff-only
            return
        }

        throw "Destination exists but is not a git repository: $Destination"
    }

    Write-Host "Cloning repo: $RepoUrl -> $Destination"
    & $GitExe clone $RepoUrl $Destination
}

function Resolve-ChainsawRelease {
    param(
        [Parameter(Mandatory = $true)][string]$ApiRoot,
        [Parameter(Mandatory = $true)][string]$Version
    )

    if ($Version -eq 'latest') {
        $release = Invoke-RestMethod -Uri "$ApiRoot/latest" -UseBasicParsing
    }
    else {
        $allReleases = Invoke-RestMethod -Uri $ApiRoot -UseBasicParsing
        $release = $allReleases | Where-Object { $_.tag_name -eq $Version } | Select-Object -First 1
        if (-not $release) {
            throw "Could not find Chainsaw release tag: $Version"
        }
    }

    $exeAsset = $release.assets | Where-Object {
        $_.name -match 'chainsaw.*x86_64-pc-windows-msvc.*\.zip$'
    } | Select-Object -First 1

    if (-not $exeAsset) {
        throw "No Windows x64 zip asset found in release: $($release.tag_name)"
    }

    $contentAsset = $release.assets | Where-Object {
        $_.name -eq 'chainsaw_all_platforms+rules+examples.zip'
    } | Select-Object -First 1

    if (-not $contentAsset) {
        $contentAsset = $release.assets | Where-Object {
            $_.name -eq 'chainsaw_all_platforms+rules.zip'
        } | Select-Object -First 1
    }

    if (-not $contentAsset) {
        throw "No Chainsaw rules/mappings package found in release: $($release.tag_name)"
    }

    return [pscustomobject]@{
        Tag = $release.tag_name
        ExeAssetName = $exeAsset.name
        ExeAssetUrl = $exeAsset.browser_download_url
        ContentAssetName = $contentAsset.name
        ContentAssetUrl = $contentAsset.browser_download_url
    }
}

function Copy-ReleaseContentFolder {
    param(
        [Parameter(Mandatory = $true)][string]$ExtractRoot,
        [Parameter(Mandatory = $true)][string]$FolderName,
        [Parameter(Mandatory = $true)][string]$InstallFolder
    )

    $source = Get-ChildItem -Path $ExtractRoot -Directory -Recurse |
        Where-Object { $_.Name -ieq $FolderName } |
        Select-Object -First 1

    if (-not $source) {
        throw "Folder '$FolderName' was not found in extracted release package."
    }

    $target = Join-Path -Path $InstallFolder -ChildPath $FolderName
    if (-not (Test-Path -LiteralPath $target)) {
        $null = New-Item -Path $target -ItemType Directory -Force
    }

    Copy-Item -Path (Join-Path -Path $source.FullName -ChildPath '*') -Destination $target -Recurse -Force
    return $target
}

function Install-ChainsawBinary {
    param(
        [Parameter(Mandatory = $true)][string]$InstallFolder,
        [Parameter(Mandatory = $true)][string]$ApiRoot,
        [Parameter(Mandatory = $true)][string]$Version,
        [switch]$Force
    )

    Ensure-Directory -Path $InstallFolder

    $chainsawExe = Join-Path -Path $InstallFolder -ChildPath 'chainsaw.exe'
    if ((Test-Path -LiteralPath $chainsawExe) -and (-not $Force)) {
        Write-Host "Chainsaw already present: $chainsawExe"
        Write-Host 'Use -ForceReinstallChainsaw to force download and replace.'
        return $chainsawExe
    }

    $release = Resolve-ChainsawRelease -ApiRoot $ApiRoot -Version $Version
    Write-Host "Downloading Chainsaw release $($release.Tag): $($release.ExeAssetName)"
    Write-Host "Downloading Chainsaw content package: $($release.ContentAssetName)"

    $exeZipPath = Join-Path -Path $env:TEMP -ChildPath $release.ExeAssetName
    $contentZipPath = Join-Path -Path $env:TEMP -ChildPath $release.ContentAssetName
    $exeExtractRoot = Join-Path -Path $env:TEMP -ChildPath ("chainsaw-exe-extract-" + [guid]::NewGuid().ToString('N'))
    $contentExtractRoot = Join-Path -Path $env:TEMP -ChildPath ("chainsaw-content-extract-" + [guid]::NewGuid().ToString('N'))
    $contentPrefixes = @('chainsaw/mappings', 'chainsaw/rules', 'mappings', 'rules')

    try {
        Invoke-WebRequest -Uri $release.ExeAssetUrl -OutFile $exeZipPath -UseBasicParsing
        Invoke-WebRequest -Uri $release.ContentAssetUrl -OutFile $contentZipPath -UseBasicParsing

        Expand-ZipArchive -ZipPath $exeZipPath -DestinationPath $exeExtractRoot
        Expand-ZipArchive -ZipPath $contentZipPath -DestinationPath $contentExtractRoot -IncludeEntryPrefixes $contentPrefixes

        $foundExe = Get-ChildItem -Path $exeExtractRoot -Filter 'chainsaw.exe' -Recurse -File | Select-Object -First 1
        if (-not $foundExe) {
            throw 'chainsaw.exe was not found in extracted release archive.'
        }

        Copy-Item -LiteralPath $foundExe.FullName -Destination $chainsawExe -Force
        Write-Host "Installed Chainsaw binary: $chainsawExe"

        $mappingsPath = Copy-ReleaseContentFolder -ExtractRoot $contentExtractRoot -FolderName 'mappings' -InstallFolder $InstallFolder
        $rulesPath = Copy-ReleaseContentFolder -ExtractRoot $contentExtractRoot -FolderName 'rules' -InstallFolder $InstallFolder
        Write-Host "Installed mappings: $mappingsPath"
        Write-Host "Installed rules: $rulesPath"

        return $chainsawExe
    }
    finally {
        Remove-Item -LiteralPath $exeZipPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $contentZipPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $exeExtractRoot -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $contentExtractRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-ChainsawExecutable {
    param([Parameter(Mandatory = $true)][string]$ChainsawExe)

    $versionOutput = & $ChainsawExe --version 2>&1
    $exitCode = $LASTEXITCODE

    if ($exitCode -eq -1073741515) {
        throw 'Chainsaw failed to start with exit code -1073741515 (0xC0000135). This usually means the Microsoft Visual C++ Redistributable x64 runtime is missing.'
    }

    if ($exitCode -ne 0) {
        $text = ($versionOutput | Out-String).Trim()
        throw "Chainsaw executable test failed with exit code $exitCode. Output: $text"
    }

    $text = ($versionOutput | Out-String).Trim()
    if ($text) {
        Write-Host "Chainsaw verification OK: $text"
    }
}

if ([string]::IsNullOrWhiteSpace($SigmaDestinationFolder)) {
    $SigmaDestinationFolder = Join-Path -Path $BaseFolder -ChildPath 'sigma'
}

$chainsawInstallFolder = $BaseFolder

Ensure-Directory -Path $BaseFolder

$gitExe = Ensure-Git -SkipInstall:$SkipGitInstall
Ensure-VcRedist -Install:$InstallVcRedist
Clone-OrUpdateRepo -RepoUrl $SigmaRepoUrl -Destination $SigmaDestinationFolder -GitExe $gitExe
$installedChainsaw = Install-ChainsawBinary -InstallFolder $chainsawInstallFolder -ApiRoot $ChainsawRepoApi -Version $ChainsawVersion -Force:$ForceReinstallChainsaw
Test-ChainsawExecutable -ChainsawExe $installedChainsaw

$gitCmdPath = "${env:ProgramFiles}\Git\cmd"
$machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
if ($machinePath -notlike "*$chainsawInstallFolder*") {
    [Environment]::SetEnvironmentVariable('Path', "$machinePath;$chainsawInstallFolder", 'Machine')
}
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine')

Write-Host ''
Write-Host 'Setup complete:' -ForegroundColor Green
Write-Host "- Sigma repo: $SigmaDestinationFolder"
Write-Host "- Chainsaw exe: $installedChainsaw"
Write-Host "- Git cmd path: $gitCmdPath"
