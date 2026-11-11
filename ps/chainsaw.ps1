################################
### Script to execute Chainsaw - Identify Malicious activity recorded in WinEvtLogs using Sigma Rules
### Based on the SOCFortress LLP script (info@socfortress.co)
###
### 2026-11-10: Sigma repo updates moved to a daily scheduled task (sigma-update.ps1,
### task "Chainsaw Sigma Update"). This script only hunts, every 5 minutes, and
### reports whether the hunt itself worked.
################################

##########
# Chainsaw will be run against all event logs found in the default location
# Output converted to JSON and appended to active-responses.log
##########

$ErrorActionPreference = "SilentlyContinue"

$base         = "C:\Program Files\socfortress\chainsaw"
$windows_path = "$base\sigma\rules\windows"
$mapping      = "$base\mappings\sigma-event-logs-all.yml"
$file         = "C:\Program Files (x86)\ossec-agent\active-response\active-responses.log"

# Append a status line Wazuh can alert on (rules 200056 / 200057)
function Write-Status($status, $message) {
    $payload = @{
        group   = 'Sigma'
        status  = $status
        message = $message
    } | ConvertTo-Json -Compress
    Write-Output $payload
    $payload | Out-File -Append -Encoding ascii $file
}

if (!(Test-Path "$base\chainsaw.exe") -or !(Test-Path $windows_path) -or !(Test-Path $mapping)) {
    Write-Status 'failure' 'Chainsaw hunt failed: chainsaw.exe, Sigma rules or mapping file missing.'
    exit 1
}

# Analyse events recorded in last 5 Minutes.
# Chainsaw reads --from as UTC (event timestamps are UTC), so build it in UTC.
# Local time here made every 5-minute hunt cover ~8 hours on Pacific-time PCs.
$from = (Get-Date).ToUniversalTime().AddMinutes(-5).ToString('yyyy-MM-ddTHH:mm:ss')

# Create Chainsaw Output Folder if it doesn't exist
$chainsaw_output = "$env:TMP\chainsaw_output"
If(!(test-path $chainsaw_output)) {
    New-Item -ItemType Directory -Force -Path $chainsaw_output | Out-Null
}

# Run Chainsaw and store JSONs in TMP folder
& "$base\chainsaw.exe" hunt C:\Windows\System32\winevt -s $windows_path --mapping $mapping --from $from --output "$chainsaw_output\results.json" --json --level high --level critical
$hunt_exit = $LASTEXITCODE

# Convert JSON to new line entry for every 'group'
function Convert-JsonToNewLine($json) {
    foreach($document in $json) {
        $document.document | ConvertTo-Json -Compress -Depth 99 | foreach-object {
            [pscustomobject]@{
                group = $document.group
                kind = $document.kind
                document = $_
                event = $document.document.data.Event.EventData
                path = $document.document.path
                system = $document.document.data.Event.System
                name = $document.name
                timestamp = $document.timestamp
                authors = $document.authors
                level = $document.level
                source = $document.source
                status = $document.status
                falsepositives = $document.falsepositives
                id = $document.id
                logsource = $document.logsource
                references = $document.references
                tags = $document.tags
            } | ConvertTo-Json -Compress
        }
    }
}

# Convert JSONs to new line entry and append to active-responses.log
Get-ChildItem $chainsaw_output -Filter *.json | Foreach-Object {
    $Chainsaw_Array = Get-Content $_.FullName | ConvertFrom-Json
    Convert-JsonToNewLine $Chainsaw_Array | Out-File -Append -Encoding ascii $file
}

# Remove TMP JSON Folder
Remove-Item -Recurse -Force $chainsaw_output

# Report the hunt result (not the Sigma update; that is sigma-update.ps1)
if ($hunt_exit -eq 0) {
    Write-Status 'success' 'Chainsaw hunt completed.'
}
else {
    Write-Status 'failure' "Chainsaw hunt failed (exit code $hunt_exit)."
}
