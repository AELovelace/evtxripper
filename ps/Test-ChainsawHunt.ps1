### Test-ChainsawHunt.ps1 - one-off diagnostic for a failing Chainsaw hunt (rule 200057).
### Runs the SAME hunt as active-response\bin\chainsaw.ps1, but keeps Chainsaw's own
### output and errors so we can see WHY it exits 1. Read-only: does not write to
### active-responses.log (so Wazuh gets no extra alerts) and changes nothing.
### Run via Atera as System on the affected PC; read the output in the Atera result.

$base         = "C:\Program Files\socfortress\chainsaw"            # where Atera-ChainsawUpdate.ps1 installs Chainsaw
$windows_path = "$base\sigma\rules\windows"                        # Sigma rules the hunt uses
$mapping      = "$base\mappings\sigma-event-logs-all.yml"          # Sigma -> event log field mapping
$out          = Join-Path $env:TEMP "chainsaw_diag"                # scratch folder for this test only

# --- 1. Do the files the hunt needs exist? ---------------------------------
"== Files"
foreach ($p in "$base\chainsaw.exe", $windows_path, $mapping) {
    "{0,-6} {1}" -f (Test-Path $p), $p                              # True/False next to each path
}
"Sigma rule files: " + (Get-ChildItem $windows_path -Recurse -Filter *.yml -ErrorAction SilentlyContinue | Measure-Object).Count   # 0 = rules missing or empty

# --- 2. Chainsaw itself --------------------------------------------------
"`n== Version"
& "$base\chainsaw.exe" --version 2>&1                               # 2>&1 keeps stderr so errors show
"exit code: $LASTEXITCODE"

# --- 3. The real hunt, same arguments as chainsaw.ps1, errors kept ----------
New-Item -ItemType Directory -Force -Path $out | Out-Null           # make the scratch folder
$from = (Get-Date).ToUniversalTime().AddMinutes(-5).ToString('yyyy-MM-ddTHH:mm:ss')   # same 5-minute UTC window as the job
"`n== Hunt (from $from UTC)"
$log = & "$base\chainsaw.exe" hunt C:\Windows\System32\winevt -s $windows_path --mapping $mapping --from $from --output "$out\results.json" --json --level high --level critical 2>&1   # capture stdout + stderr
$code = $LASTEXITCODE                                               # Chainsaw's exit code (0 = OK)
$log | Select-Object -Last 40                                       # last 40 lines: the error is usually at the end
"hunt exit code: $code"

# --- 4. Tidy up the scratch folder ------------------------------------------
Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue      # leave nothing behind
