# Wazuh + Chainsaw Near-Real-Time Supplement

This supplement implements the SOCFortress article pattern in an additive way for this repo.

## Goal

Use scheduled Chainsaw hunts to evaluate fresh Windows logs with Sigma logic, then forward detections to Wazuh as JSON lines.

## What Was Added

1. `ChainsawRealtimeWazuh.ps1`
   - Runs rolling-window hunts (`--from`, `--to`) against local EVTX logs.
   - Optionally updates Sigma repo before each run.
   - Filters by Sigma level (default: `high,critical`).
   - Appends normalized NDJSON records to a Wazuh-monitored file.
   - Maintains a state file to avoid large overlaps/gaps across runs.

2. `wazuh/200050-chainsaw-sigma-rules.xml`
   - Base rule for this integration feed.
   - Severity mapping for high/critical and medium.
   - Example suppression for noisy `driver_load` category.

3. `wazuh/windows-chainsaw-wodle.xml`
   - Command wodle snippet to run the script every 5 minutes.

## Why This Supplements Your Existing System

Your current platform is analyst-driven and investigation-oriented:
- interactive file browsing,
- ad hoc hunt/search,
- report generation.

This supplement adds endpoint-side, recurring detection ingestion for SIEM alerting. It does not replace your existing EVTX export or frontend workflows.

## Configuration

Add these optional variables to `.env`:

```ini
# Realtime Chainsaw + Wazuh supplement
CHAINSAW_UPDATE_SIGMA=false
CHAINSAW_SIGMA_REPO=./sigma
CHAINSAW_REALTIME_EVTX_PATH=C:\Windows\System32\winevt\Logs
CHAINSAW_REALTIME_STATE_PATH=./chainsaw_realtime_state.json
CHAINSAW_WAZUH_OUTPUT_LOG=C:\Program Files (x86)\ossec-agent\active-response\active-responses.log
CHAINSAW_REALTIME_LEVELS=high,critical
CHAINSAW_REALTIME_USE_CUSTOM_RULES=false
```

## Deploy on Wazuh Agent Host (Windows)

1. Copy `ChainsawRealtimeWazuh.ps1` to:
   - `C:\Program Files (x86)\ossec-agent\active-response\bin\`
2. Ensure Chainsaw binary, Sigma path, and mapping path in `.env` are valid on endpoint.
3. Confirm Wazuh monitors the output file as JSON:

```xml
<localfile>
  <location>C:\Program Files (x86)\ossec-agent\active-response\active-responses.log</location>
  <log_format>json</log_format>
</localfile>
```

4. Add the command wodle from `wazuh/windows-chainsaw-wodle.xml` to endpoint `ossec.conf`.
5. Add `wazuh/200050-chainsaw-sigma-rules.xml` to manager rules and restart manager.
6. Restart Wazuh agent service on endpoint.

## Test Procedure

1. Manual run:

```powershell
PowerShell.exe -ExecutionPolicy Bypass -File .\ChainsawRealtimeWazuh.ps1 -EnvPath .\.env
```

2. Verify script output summary includes parsed/written counts.
3. Verify JSON lines are appended to configured output log.
4. Verify Wazuh manager receives alerts with group `sigma,chainsaw`.

## Operational Notes

1. Keep interval and window aligned (for example: `5m` wodle with `WindowMinutes=5`).
2. If alert volume is too high, tighten `CHAINSAW_REALTIME_LEVELS` and add suppressions.
3. Sysmon-heavy environments can be noisy; curate Sigma rules and exclusions early.
4. If running on many endpoints, avoid `CHAINSAW_UPDATE_SIGMA=true` every cycle. Prefer scheduled updates.

## Example Direct Invocation

```powershell
.\ChainsawRealtimeWazuh.ps1 -EnvPath .\.env -WindowMinutes 5 -OverlapSeconds 30
```

## Inputs and Outputs

Input:
- EVTX files under `CHAINSAW_REALTIME_EVTX_PATH`
- Sigma rules in `CHAINSAW_SIGMA_PATH`
- Mapping in `CHAINSAW_MAPPING_FILE`

Output:
- NDJSON lines at `CHAINSAW_WAZUH_OUTPUT_LOG`
- run state in `CHAINSAW_REALTIME_STATE_PATH`
