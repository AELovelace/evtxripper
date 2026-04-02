#Requires -Version 5.0
<#!
.SYNOPSIS
    Run Chainsaw hunts on a short rolling window and append JSON output for Wazuh ingestion.

.DESCRIPTION
    This script supplements the EVTX Ripper workflow with a near-real-time mode inspired by
    the SOCFortress Wazuh + Chainsaw approach. It runs Chainsaw on local EVTX logs, filters
    Sigma levels, and appends normalized JSON lines to a Wazuh-monitored log file.

.NOTES
    Designed to run from Wazuh command wodle every 5 minutes.
#>

[CmdletBinding()]
param(
    [string]$EnvPath = '.\.env',
    [int]$WindowMinutes = 5,
    [int]$OverlapSeconds = 30,
    [string]$OutputLogPath,
    [string]$StateFilePath,
    [string]$EvtxPath,
    [switch]$UpdateSigma
)

$ErrorActionPreference = 'Stop'

function Load-EnvFile {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Environment file not found: $Path"
    }

    $envVars = @{}

    foreach ($line in (Get-Content -LiteralPath $Path -ErrorAction Stop)) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        if ($line.TrimStart().StartsWith('#')) {
            continue
        }

        if ($line -notmatch '^\s*([^#=]+?)\s*=\s*(.*)$') {
            continue
        }

        $key = $Matches[1].Trim()
        $value = $Matches[2].Trim()

        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        $envVars[$key] = $value
        [Environment]::SetEnvironmentVariable($key, $value, 'Process')
    }

    return $envVars
}

function Resolve-ConfigPath {
    param(
        [string]$Value,
        [string]$BasePath
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $null
    }

    if ([System.IO.Path]::IsPathRooted($Value)) {
        return $Value
    }

    return [System.IO.Path]::GetFullPath((Join-Path -Path $BasePath -ChildPath $Value))
}

function Ensure-ParentDirectory {
    param([string]$FilePath)

    $parent = Split-Path -Path $FilePath -Parent
    if (-not [string]::IsNullOrWhiteSpace($parent) -and -not (Test-Path -LiteralPath $parent)) {
        $null = New-Item -ItemType Directory -Path $parent -Force
    }
}

function Update-SigmaRepository {
    param(
        [string]$SigmaRepoPath
    )

    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) {
        Write-Warning 'Git not found. Skipping Sigma repo update.'
        return
    }

    if (-not (Test-Path -LiteralPath $SigmaRepoPath)) {
        & $git.Source clone https://github.com/SigmaHQ/sigma.git $SigmaRepoPath | Out-Null
        return
    }

    if (-not (Test-Path -LiteralPath (Join-Path -Path $SigmaRepoPath -ChildPath '.git'))) {
        Write-Warning "Sigma path exists but is not a git repo: $SigmaRepoPath"
        return
    }

    & $git.Source -C $SigmaRepoPath pull --ff-only | Out-Null
}

function Get-WindowStartUtc {
    param(
        [datetime]$ToUtc,
        [int]$DefaultMinutes,
        [int]$Overlap,
        [string]$StatePath
    )

    $fallback = $ToUtc.AddMinutes(-1 * [Math]::Abs($DefaultMinutes))

    if (-not (Test-Path -LiteralPath $StatePath)) {
        return $fallback
    }

    try {
        $payload = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json -ErrorAction Stop
        if ($payload.LastToUtc) {
            $lastTo = [datetime]::Parse($payload.LastToUtc).ToUniversalTime()
            if ($lastTo -lt $ToUtc) {
                return $lastTo.AddSeconds(-1 * [Math]::Abs($Overlap))
            }
        }
    }
    catch {
        Write-Warning "Could not parse state file. Falling back to default window. Error: $_"
    }

    return $fallback
}

function Parse-LevelFilter {
    param([string]$Raw)

    if ([string]::IsNullOrWhiteSpace($Raw)) {
        return @('high', 'critical')
    }

    return ($Raw -split ',' | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
}

$scriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$envVars = Load-EnvFile -Path $EnvPath

$chainsawExe = Resolve-ConfigPath -Value ($envVars['CHAINSAW_EXECUTABLE']) -BasePath $scriptRoot
if ([string]::IsNullOrWhiteSpace($chainsawExe) -or -not (Test-Path -LiteralPath $chainsawExe)) {
    throw "Chainsaw executable not found: $chainsawExe"
}

$sigmaRepoPath = Resolve-ConfigPath -Value ($envVars['CHAINSAW_SIGMA_REPO']) -BasePath $scriptRoot
if ([string]::IsNullOrWhiteSpace($sigmaRepoPath)) {
    $sigmaRepoPath = Resolve-ConfigPath -Value '.\sigma' -BasePath $scriptRoot
}

$updateSigmaEnabled = $UpdateSigma.IsPresent -or (($envVars['CHAINSAW_UPDATE_SIGMA'] + '').ToLowerInvariant() -eq 'true')
if ($updateSigmaEnabled) {
    Update-SigmaRepository -SigmaRepoPath $sigmaRepoPath
}

$sigmaPathValue = $envVars['CHAINSAW_SIGMA_PATH']
if ([string]::IsNullOrWhiteSpace($sigmaPathValue)) {
    $sigmaPathValue = '.\sigma\rules\windows'
}
$sigmaPath = Resolve-ConfigPath -Value $sigmaPathValue -BasePath $scriptRoot

$mappingPathValue = $envVars['CHAINSAW_MAPPING_FILE']
if ([string]::IsNullOrWhiteSpace($mappingPathValue)) {
    $mappingPathValue = '.\chainsaw\mappings\sigma-event-logs-all.yml'
}
$mappingPath = Resolve-ConfigPath -Value $mappingPathValue -BasePath $scriptRoot

$rulesPath = Resolve-ConfigPath -Value ($envVars['CHAINSAW_RULES_PATH']) -BasePath $scriptRoot
$useCustomRules = (($envVars['CHAINSAW_REALTIME_USE_CUSTOM_RULES'] + '').ToLowerInvariant() -eq 'true')

$effectiveEvtxPath = $EvtxPath
if ([string]::IsNullOrWhiteSpace($effectiveEvtxPath)) {
    $effectiveEvtxPath = $envVars['CHAINSAW_REALTIME_EVTX_PATH']
}
if ([string]::IsNullOrWhiteSpace($effectiveEvtxPath)) {
    $effectiveEvtxPath = 'C:\Windows\System32\winevt\Logs'
}

$effectiveOutputLogPath = $OutputLogPath
if ([string]::IsNullOrWhiteSpace($effectiveOutputLogPath)) {
    $effectiveOutputLogPath = $envVars['CHAINSAW_WAZUH_OUTPUT_LOG']
}
if ([string]::IsNullOrWhiteSpace($effectiveOutputLogPath)) {
    $effectiveOutputLogPath = 'C:\Program Files (x86)\ossec-agent\active-response\active-responses.log'
}

$effectiveStateFilePath = $StateFilePath
if ([string]::IsNullOrWhiteSpace($effectiveStateFilePath)) {
    $effectiveStateFilePath = $envVars['CHAINSAW_REALTIME_STATE_PATH']
}
if ([string]::IsNullOrWhiteSpace($effectiveStateFilePath)) {
    $effectiveStateFilePath = Join-Path -Path $scriptRoot -ChildPath 'chainsaw_realtime_state.json'
}
$effectiveStateFilePath = Resolve-ConfigPath -Value $effectiveStateFilePath -BasePath $scriptRoot

if (-not (Test-Path -LiteralPath $sigmaPath)) {
    throw "Sigma path not found: $sigmaPath"
}
if (-not (Test-Path -LiteralPath $mappingPath)) {
    throw "Mapping file not found: $mappingPath"
}
if (-not (Test-Path -LiteralPath $effectiveEvtxPath)) {
    throw "EVTX source path not found: $effectiveEvtxPath"
}

Ensure-ParentDirectory -FilePath $effectiveOutputLogPath
Ensure-ParentDirectory -FilePath $effectiveStateFilePath

$timezone = $envVars['CHAINSAW_TIMEZONE']
if ([string]::IsNullOrWhiteSpace($timezone)) {
    $timezone = 'UTC'
}

$toUtc = (Get-Date).ToUniversalTime()
$fromUtc = Get-WindowStartUtc -ToUtc $toUtc -DefaultMinutes $WindowMinutes -Overlap $OverlapSeconds -StatePath $effectiveStateFilePath
$fromIso = $fromUtc.ToString('yyyy-MM-ddTHH:mm:ssZ')
$toIso = $toUtc.ToString('yyyy-MM-ddTHH:mm:ssZ')

$tempOutput = Join-Path -Path $env:TEMP -ChildPath ("chainsaw-realtime-{0}.json" -f ([Guid]::NewGuid().ToString('N')))

$cmdArgs = @(
    'hunt',
    $effectiveEvtxPath,
    '-s', $sigmaPath,
    '-m', $mappingPath,
    '--json',
    '--from', $fromIso,
    '--to', $toIso,
    '--timezone', $timezone,
    '--skip-errors',
    '-o', $tempOutput
)

if ($useCustomRules -and $rulesPath -and (Test-Path -LiteralPath $rulesPath)) {
    $cmdArgs += @('-r', $rulesPath)
}

$cmdResult = & $chainsawExe @cmdArgs 2>&1
if ($LASTEXITCODE -ne 0) {
    $cmdText = ($cmdResult | Out-String).Trim()
    if ($LASTEXITCODE -eq -1073741515) {
        throw "Chainsaw failed to start with exit code $LASTEXITCODE (0xC0000135). The Windows host is likely missing the Microsoft Visual C++ Redistributable x64 runtime required by the Chainsaw MSVC build. Install vc_redist.x64.exe, then rerun the hunt."
    }
    throw "Chainsaw hunt failed with exit code $LASTEXITCODE. Output: $cmdText"
}

if (-not (Test-Path -LiteralPath $tempOutput)) {
    throw "Chainsaw completed but output file was not created: $tempOutput"
}

$levelFilter = Parse-LevelFilter -Raw ($envVars['CHAINSAW_REALTIME_LEVELS'])
$eventsWritten = 0
$totalParsed = 0

try {
    foreach ($line in (Get-Content -LiteralPath $tempOutput -ErrorAction Stop)) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        $evt = $null
        try {
            $evt = $line | ConvertFrom-Json -ErrorAction Stop
        }
        catch {
            continue
        }

        $totalParsed += 1
        $eventLevel = (($evt.level + '') + '').ToLowerInvariant()
        if ($levelFilter.Count -gt 0 -and $eventLevel -and ($levelFilter -notcontains $eventLevel)) {
            continue
        }

        $enriched = [ordered]@{
            integration = 'chainsaw-sigma'
            source = 'evtxripper-realtime'
            host = $env:COMPUTERNAME
            collected_utc = (Get-Date).ToUniversalTime().ToString('o')
            chainsaw_window_from_utc = $fromIso
            chainsaw_window_to_utc = $toIso
            event = $evt
        }

        $jsonLine = $enriched | ConvertTo-Json -Depth 16 -Compress
        Add-Content -LiteralPath $effectiveOutputLogPath -Value $jsonLine -Encoding UTF8
        $eventsWritten += 1
    }
}
finally {
    Remove-Item -LiteralPath $tempOutput -Force -ErrorAction SilentlyContinue
}

$state = [ordered]@{
    LastFromUtc = $fromIso
    LastToUtc = $toIso
    LastRunUtc = (Get-Date).ToUniversalTime().ToString('o')
    LastParsedCount = $totalParsed
    LastWrittenCount = $eventsWritten
}
$state | ConvertTo-Json | Set-Content -LiteralPath $effectiveStateFilePath -Encoding UTF8

Write-Output ("Chainsaw realtime run complete. Parsed={0}; Written={1}; Window={2}..{3}" -f $totalParsed, $eventsWritten, $fromIso, $toIso)
