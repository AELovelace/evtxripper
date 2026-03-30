[CmdletBinding()]
param(
    [string]$OutputDirectory = 'C:\temp',
    [switch]$CopyToRemoteShare,
    [string]$RemoteShareRoot = '(your SMB share root, e.g. \\server\share)',
    [string]$RemoteDirectory = 'logdump',
    [string]$Username = 'helper',
    [string]$AteraInputPassword = '{[HelperPassword]}',
    [SecureString]$Password
)

$ErrorActionPreference = 'Stop'

function New-StructuredQuery {
    param(
        [Parameter(Mandatory)]
        [string[]]$LogNames
    )

    $builder = [System.Text.StringBuilder]::new()
    [void]$builder.AppendLine('<QueryList>')

    for ($index = 0; $index -lt $LogNames.Count; $index++) {
        $escapedLogName = [System.Security.SecurityElement]::Escape($LogNames[$index])
        [void]$builder.AppendLine(('  <Query Id="{0}" Path="{1}">' -f $index, $escapedLogName))
        [void]$builder.AppendLine(('    <Select Path="{0}">*</Select>' -f $escapedLogName))
        [void]$builder.AppendLine('  </Query>')
    }

    [void]$builder.Append('</QueryList>')
    $builder.ToString()
}

function Export-WithWevtutil {
    param(
        [Parameter(Mandatory)]
        [string]$Query,

        [Parameter(Mandatory)]
        [string]$TargetFilePath
    )

    $queryFilePath = Join-Path -Path $env:TEMP -ChildPath ("evtxripper-{0}.xml" -f [guid]::NewGuid().ToString('N'))

    try {
        Set-Content -LiteralPath $queryFilePath -Value $Query -Encoding UTF8

        $exportOutput = & wevtutil epl $queryFilePath $TargetFilePath /sq:true 2>&1
        if ($LASTEXITCODE -ne 0) {
            $message = if ($exportOutput) { ($exportOutput | Out-String).Trim() } else { 'wevtutil export failed.' }
            throw $message
        }
    }
    finally {
        if (Test-Path -LiteralPath $queryFilePath) {
            Remove-Item -LiteralPath $queryFilePath -Force -ErrorAction SilentlyContinue
        }
    }
}

function Resolve-SharePassword {
    param(
        [string]$AteraPassword,
        [SecureString]$ProvidedPassword,
        [string]$ShareUsername
    )

    if (-not [string]::IsNullOrWhiteSpace($AteraPassword)) {
        return ConvertTo-SecureString -String $AteraPassword -AsPlainText -Force
    }

    if ($ProvidedPassword) {
        return $ProvidedPassword
    }

    if ($env:ATERA_INPUT_PASSWORD) {
        return ConvertTo-SecureString -String $env:ATERA_INPUT_PASSWORD -AsPlainText -Force
    }

    if ($env:ATERA_PASSWORD) {
        return ConvertTo-SecureString -String $env:ATERA_PASSWORD -AsPlainText -Force
    }

    if ($env:EVTXRIPPER_SHARE_PASSWORD) {
        return ConvertTo-SecureString -String $env:EVTXRIPPER_SHARE_PASSWORD -AsPlainText -Force
    }

    return Read-Host -Prompt ("Enter password for {0}" -f $ShareUsername) -AsSecureString
}

function Copy-ToRemoteShare {
    param(
        [Parameter(Mandatory)]
        [string]$LocalFilePath,

        [Parameter(Mandatory)]
        [string]$ShareRoot,

        [Parameter(Mandatory)]
        [string]$ShareDirectory,

        [Parameter(Mandatory)]
        [string]$ShareUsername,

        [string]$AteraPassword,
        [SecureString]$ProvidedPassword
    )

    $resolvedPassword = Resolve-SharePassword -AteraPassword $AteraPassword -ProvidedPassword $ProvidedPassword -ShareUsername $ShareUsername
    $credential = [pscredential]::new($ShareUsername, $resolvedPassword)
    $driveName = 'Z'

    try {
        $existingDrive = Get-PSDrive -Name $driveName -ErrorAction SilentlyContinue
        if ($existingDrive) {
            Remove-PSDrive -Name $driveName -Force -ErrorAction SilentlyContinue
        }

        $null = New-PSDrive -Name $driveName -PSProvider FileSystem -Root $ShareRoot -Credential $credential -Scope Script

        $remoteOutputDirectory = '{0}:\{1}' -f $driveName, $ShareDirectory
        if (-not (Test-Path -LiteralPath $remoteOutputDirectory)) {
            $null = New-Item -Path $remoteOutputDirectory -ItemType Directory -Force
        }

        $remoteFilePath = Join-Path -Path $remoteOutputDirectory -ChildPath (Split-Path -Path $LocalFilePath -Leaf)
        Copy-Item -LiteralPath $LocalFilePath -Destination $remoteFilePath -Force

        return $remoteFilePath
    }
    finally {
        if (Get-PSDrive -Name $driveName -ErrorAction SilentlyContinue) {
            Remove-PSDrive -Name $driveName -Force -ErrorAction SilentlyContinue
        }
    }
}

if (-not (Test-Path -LiteralPath $OutputDirectory)) {
    $null = New-Item -Path $OutputDirectory -ItemType Directory -Force
}

$hostname = $env:COMPUTERNAME
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$outputPath = Join-Path -Path $OutputDirectory -ChildPath ("{0}-{1}.evtx" -f $hostname, $timestamp)

if (Test-Path -LiteralPath $outputPath) {
    throw "Output file already exists: $outputPath"
}

$logNames = Get-WinEvent -ListLog * -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.IsEnabled -and -not [string]::IsNullOrWhiteSpace($_.LogName) } |
    Select-Object -ExpandProperty LogName

if (-not $logNames) {
    throw 'No enabled event logs were found to export.'
}

$query = New-StructuredQuery -LogNames $logNames

Export-WithWevtutil -Query $query -TargetFilePath $outputPath

if ($CopyToRemoteShare) {
    $remotePath = Copy-ToRemoteShare -LocalFilePath $outputPath -ShareRoot $RemoteShareRoot -ShareDirectory $RemoteDirectory -ShareUsername $Username -AteraPassword $AteraInputPassword -ProvidedPassword $Password
    Write-Output $remotePath
}

Write-Output $outputPath