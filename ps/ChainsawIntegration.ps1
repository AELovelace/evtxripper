#Requires -Version 5.0
<#
.SYNOPSIS
    Integration helper for Chainsaw frontend with PowerShell scripts
    
.DESCRIPTION
    Loads configuration from .env file and sets up environment for Chainsaw analysis pipeline
    
.PARAMETER EnvPath
    Path to the .env file (default: .\.env)
    
.PARAMETER Action
    Action to perform: LoadEnv, TestConnection, ExportEvtx, ExtractToShare
    
.EXAMPLE
    .\ChainsawIntegration.ps1 -LoadEnv
    .\ChainsawIntegration.ps1 -TestConnection
    .\ChainsawIntegration.ps1 -ExportEvtx
#>

[CmdletBinding()]
param(
    [string]$EnvPath = '.\.env',
    [ValidateSet('LoadEnv', 'TestConnection', 'ExportEvtx', 'ExtractToShare', 'ShowConfig')]
    [string]$Action = 'LoadEnv'
)

$ErrorActionPreference = 'Stop'

function Load-EnvFile {
    <#
    .SYNOPSIS
        Load environment variables from .env file
    #>
    param(
        [string]$Path
    )
    
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Environment file not found: $Path"
    }
    
    $envVars = @{}
    
    Get-Content -LiteralPath $Path -ErrorAction Stop |
        Where-Object { $_ -match '^\s*([^#=]+)\s*=\s*(.*)$' -and -not $_.StartsWith('#') } |
        ForEach-Object {
            $key = $Matches[1].Trim()
            $value = $Matches[2].Trim()
            $envVars[$key] = $value
            [Environment]::SetEnvironmentVariable($key, $value, 'Process')
        }
    
    Write-Host "Loaded $($envVars.Count) environment variables from $Path" -ForegroundColor Green
    return $envVars
}

function Test-SMBConnection {
    <#
    .SYNOPSIS
        Test connection to SMB share
    #>
    param(
        [hashtable]$EnvVars
    )
    
    $host = $EnvVars['SMB_HOST']
    $port = $EnvVars['SMB_PORT']
    $share = $EnvVars['SMB_SHARE_NAME']
    $username = $EnvVars['SMB_USERNAME']
    
    Write-Host "`n=== Testing SMB Connection ===" -ForegroundColor Cyan
    
    # Test network connectivity
    Write-Host "Testing network connection to $host`:$port..." -ForegroundColor Yellow
    if (Test-NetConnection -ComputerName $host -Port $port -WarningAction SilentlyContinue | 
        Where-Object { $_.TcpTestSucceeded }) {
        Write-Host "✓ Network connection successful" -ForegroundColor Green
    } else {
        Write-Host "✗ Failed to connect to $host`:$port" -ForegroundColor Red
        return $false
    }
    
    # Test SMB access
    Write-Host "Testing SMB share access: \\$host\$share" -ForegroundColor Yellow
    try {
        $credential = New-Object System.Management.Automation.PSCredential(
            $username,
            (ConvertTo-SecureString $EnvVars['SMB_PASSWORD'] -AsPlainText -Force)
        )
        
        $drive = New-PSDrive -Name ChainSawTest -PSProvider FileSystem -Root "\\$host\$share" `
            -Credential $credential -ErrorAction Stop
        
        $items = Get-ChildItem -Path "ChainSawTest:\" -ErrorAction Stop
        Write-Host "✓ SMB access successful" -ForegroundColor Green
        Write-Host "  Found $($items.Count) items in share"
        
        Remove-PSDrive -Name ChainSawTest -Force
        return $true
    } catch {
        Write-Host "✗ Failed to access SMB share: $_" -ForegroundColor Red
        return $false
    }
}

function Get-ChainsawStatus {
    <#
    .SYNOPSIS
        Check if Chainsaw binary is available
    #>
    param(
        [hashtable]$EnvVars
    )
    
    Write-Host "`n=== Checking Chainsaw ===" -ForegroundColor Cyan
    
    $chainsawExe = $EnvVars['CHAINSAW_EXECUTABLE']
    Write-Host "Looking for Chainsaw: $chainsawExe" -ForegroundColor Yellow
    
    try {
        $result = & $chainsawExe --version 2>&1
        Write-Host "✓ Chainsaw found: $result" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "✗ Chainsaw not found in PATH" -ForegroundColor Red
        return $false
    }
}

function Show-Configuration {
    <#
    .SYNOPSIS
        Display loaded configuration
    #>
    param(
        [hashtable]$EnvVars
    )
    
    Write-Host "`n=== Current Configuration ===" -ForegroundColor Cyan
    
    Write-Host "`n[SMB Settings]" -ForegroundColor Yellow
    Write-Host "  Host: $($EnvVars['SMB_HOST'])"
    Write-Host "  Port: $($EnvVars['SMB_PORT'])"
    Write-Host "  Share: $($EnvVars['SMB_SHARE_NAME'])"
    Write-Host "  Username: $($EnvVars['SMB_USERNAME'])"
    Write-Host "  Domain: $($EnvVars['SMB_DOMAIN'])"
    
    Write-Host "`n[Chainsaw Settings]" -ForegroundColor Yellow
    Write-Host "  Executable: $($EnvVars['CHAINSAW_EXECUTABLE'])"
    Write-Host "  Sigma Path: $($EnvVars['CHAINSAW_SIGMA_PATH'])"
    Write-Host "  Rules Path: $($EnvVars['CHAINSAW_RULES_PATH'])"
    Write-Host "  Mapping File: $($EnvVars['CHAINSAW_MAPPING_FILE'])"
    Write-Host "  Output Format: $($EnvVars['CHAINSAW_OUTPUT_FORMAT'])"
    Write-Host "  Timezone: $($EnvVars['CHAINSAW_TIMEZONE'])"
    
    Write-Host "`n[Output Settings]" -ForegroundColor Yellow
    Write-Host "  Output Path: $($EnvVars['OUTPUT_PATH'])"
    Write-Host "  Log File: $($EnvVars['LOG_FILE'])"
    Write-Host "  Log Level: $($EnvVars['LOG_LEVEL'])"
}

function Export-EvtxAndSync {
    <#
    .SYNOPSIS
        Export EVTX files and sync to SMB share using configuration
    #>
    param(
        [hashtable]$EnvVars
    )
    
    Write-Host "`n=== EVTX Export and Sync ===" -ForegroundColor Cyan
    
    $outputDir = $EnvVars['OUTPUT_DIRECTORY']
    $copyToShare = $EnvVars['COPY_TO_REMOTE_SHARE']
    
    Write-Host "Exporting EVTX from this machine..." -ForegroundColor Yellow
    
    if (Test-Path -LiteralPath (Join-Path -Path $PSScriptRoot -ChildPath 'Export-AllEvtx.ps1')) {
        $params = @{
            OutputDirectory = $outputDir
            CopyToRemoteShare = ($copyToShare -eq 'true')
            RemoteShareRoot = $EnvVars['REMOTE_SHARE_ROOT']
            RemoteDirectory = $EnvVars['REMOTE_DIRECTORY']
            Username = $EnvVars['REMOTE_USERNAME']
        }
        
        & (Join-Path -Path $PSScriptRoot -ChildPath 'Export-AllEvtx.ps1') @params
        Write-Host "✓ EVTX export completed" -ForegroundColor Green
    } else {
        Write-Host "! Export-AllEvtx.ps1 not found in script directory" -ForegroundColor Yellow
    }
}

# Main execution
try {
    Write-Host "Chainsaw Frontend Integration Script" -ForegroundColor Cyan
    Write-Host "====================================`n" -ForegroundColor Cyan
    
    $envVars = Load-EnvFile -Path $EnvPath
    
    switch ($Action) {
        'LoadEnv' {
            Write-Host "Environment variables loaded successfully" -ForegroundColor Green
            Show-Configuration -EnvVars $envVars
        }
        'TestConnection' {
            Show-Configuration -EnvVars $envVars
            Test-SMBConnection -EnvVars $envVars | Out-Null
            Get-ChainsawStatus -EnvVars $envVars | Out-Null
        }
        'ExportEvtx' {
            Export-EvtxAndSync -EnvVars $envVars
        }
        'ExtractToShare' {
            Export-EvtxAndSync -EnvVars $envVars
        }
        'ShowConfig' {
            Show-Configuration -EnvVars $envVars
        }
    }
    
    Write-Host "`n✓ Operation completed successfully" -ForegroundColor Green
}
catch {
    Write-Host "`n✗ Error: $_" -ForegroundColor Red
    exit 1
}
