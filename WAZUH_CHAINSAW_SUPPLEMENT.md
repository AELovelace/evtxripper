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
3. Confirm Wazuh already monitors the output file. The default Windows agent `ossec.conf` has this entry; do **not** add a second `<localfile>` for the same file, or every line is read and alerted twice:

```xml
<localfile>
  <location>active-response\active-responses.log</location>
  <log_format>syslog</log_format>
</localfile>
```

Check with:

```powershell
Select-String -Path 'C:\Program Files (x86)\ossec-agent\ossec.conf','C:\Program Files (x86)\ossec-agent\shared\agent.conf' -Pattern 'active-responses.log'
```

Exactly one match is correct. The Wazuh decoder picks up the JSON lines from the syslog-format entry.

> Time windows: Chainsaw reads `--from`/`--to` as UTC. Always build them from `(Get-Date).ToUniversalTime()`. A local-time `--from` on a Pacific-time PC makes a "last 5 minutes" hunt cover about 8 hours, and one event re-alerts on every run (seen 2026-11-11 on Win2019SRVR and EH-OPI).

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

## Checking the 5-minute hunt (rules 200056 / 200057)

The active-response `chainsaw.ps1` writes one status line per run to `active-responses.log`:

| Rule | Level | Meaning | Shows in Wazuh alerts? |
|---|---|---|---|
| 200056 | 1 | Hunt completed | **No** (below the alert log level) |
| 200057 | 13 | Hunt failed (`exit code N`, or files missing) | Yes |

So a healthy agent is **silent**: no 200057 for 10+ minutes while the PC is on = working.
A quiet night can just mean the PC was off.

- **Check in Wazuh (Mnemerynne API):** *Alerts* with `agent=<PC>`, `rule_group=chainsaw`, `hours=1`; or *Alert timeline* with `rule_id=200055,200057`.
- **See the real error:** `chainsaw.ps1` discards Chainsaw's own output, so Wazuh only shows the exit code.
  Run `ps/Test-ChainsawHunt.ps1` via Atera as System on the PC. It runs the same hunt with stderr
  captured, lists the required files and the Sigma rule count, and changes nothing.
- **Known cause (2026-11-17, DESKTOP-GGFHLBU):** one unreadable log
  (`Intel-SST-DVD%4DVD_ETW_Telemetry.evtx`) made Chainsaw abort with exit 1 ("An error occurred while
  trying to deserialize evtx stream"). `chainsaw.ps1` now passes `--skip-errors`, so a bad file is
  skipped and the rest of the hunt still runs.
- **After changing `chainsaw.ps1` or `sigma-update.ps1`:** run `python python/build_atera_update.py`
  to re-embed them (base64 + SHA256) in `ps/Atera-ChainsawUpdate.ps1`, then push that via Atera.

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
