################################
### Daily Sigma rule update for Chainsaw
### Run by scheduled task "Chainsaw Sigma Update" (SYSTEM, daily ~03:00 + random delay).
### Reports to Wazuh via active-responses.log (rules 200054 success / 200055 failure).
################################

$ErrorActionPreference = "SilentlyContinue"

$repo_path = "C:\Program Files\socfortress\chainsaw\sigma"
$file      = "C:\Program Files (x86)\ossec-agent\active-response\active-responses.log"

$git = "C:\Program Files\Git\cmd\git.exe"
if (!(Test-Path $git)) { $git = (Get-Command git -ErrorAction SilentlyContinue).Source }

$ok = $false
if ($git) {
    if (Test-Path "$repo_path\.git") {
        # safe.directory: the repo may be owned by whoever ran the installer, not SYSTEM
        & $git -c safe.directory=* -C $repo_path pull --ff-only --quiet
        $ok = ($LASTEXITCODE -eq 0)
    }
    elseif (!(Test-Path $repo_path)) {
        & $git clone --quiet https://github.com/SigmaHQ/sigma.git $repo_path
        $ok = ($LASTEXITCODE -eq 0)
    }
}

if ($ok) {
    $payload = @{ group = 'Sigma'; status = 'success'; message = 'Sigma rules were updated successfully.' }
}
else {
    $payload = @{ group = 'Sigma'; status = 'failure'; message = 'Failed to update Sigma rules.' }
}
$payload | ConvertTo-Json -Compress | Out-File -Append -Encoding ascii $file
