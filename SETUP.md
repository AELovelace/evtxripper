# Chainsaw Frontend - Setup & Usage Guide

## Overview

This is an interactive ncurses-based frontend for **Chainsaw**, a forensic event log analysis tool. It provides:

- **SMB Share Browser** - Browse and select EVTX files from remote SMB shares
- **Credential Management** - Securely store SMB credentials in `.env` file
- **Hunt Interface** - Run Chainsaw hunt operations with configurable options
- **Search Interface** - Run Chainsaw search operations
- **Configuration Management** - Central `.env` file for all settings

## Prerequisites

### System Requirements
- **Windows/Linux/macOS** with Python 3.7+
- **Chainsaw binary** (precompiled or built from source)
- **SMB access** to network share containing EVTX files
- **Sigma rules** and mapping files (included in `chainsaw/` folder)

### Python Dependencies
```
python-dotenv==1.0.0      # Load configuration from .env file
pysmb==1.2.8              # SMB protocol support
```

## Installation

### 1. Install Python Dependencies

```PowerShell
pip install -r requirements.txt
```

Or with venv:

```PowerShell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure the `.env` File

Edit the `.env` file in the root directory with your SMB credentials and Chainsaw configuration:

```ini
# SMB Connection Settings
SMB_HOST=192.168.1.100
SMB_PORT=445
SMB_SHARE_NAME=Logs
SMB_USERNAME=analyst
SMB_PASSWORD=YourPassword
SMB_DOMAIN=MYDOMAIN

# Chainsaw Paths
CHAINSAW_EXECUTABLE=./chainsaw
CHAINSAW_SIGMA_PATH=./chainsaw/mappings
CHAINSAW_RULES_PATH=./chainsaw/rules
CHAINSAW_MAPPING_FILE=./chainsaw/mappings/sigma-event-logs-all.yml

# Output Settings
OUTPUT_PATH=./chainsaw_results
CHAINSAW_OUTPUT_FORMAT=csv
CHAINSAW_TIMEZONE=UTC

# Additional Chainsaw Options
CHAINSAW_SKIP_ERRORS=false
CHAINSAW_LOAD_UNKNOWN=false
CHAINSAW_COLUMN_WIDTH=50

# Logging
LOG_LEVEL=INFO
LOG_FILE=./evtxripper.log
```

> **⚠️ Security Warning**: The `.env` file contains plaintext passwords. Ensure proper file permissions and access controls. For production environments, consider using keyring or secrets management solutions.

## Running the Application

### On Windows

```PowerShell
python chainsaw_frontend.py
```

### On Linux/macOS

```bash
python3 chainsaw_frontend.py
```

## User Interface Guide

### Main Menu

```
┌─────────────────────────────────────────────┐
│  Chainsaw Forensic Event Log Analysis Frontend │
├─────────────────────────────────────────────┤
│ 1. Browse SMB Share & Select EVTX Files      │
│ 2. Run Chainsaw Hunt                         │
│ 3. Run Chainsaw Search                       │
│ 4. Configure Settings                        │
│ 5. View Selected Files                       │
│ 0. Exit                                      │
└─────────────────────────────────────────────┘
```

### Option 1: Browse SMB Share

1. Select **Option 1** to connect to the SMB share
2. Files and folders are displayed
3. Using **Space** to toggle selection (selected files show `*SELECTED*`)
4. **'d'** to download selected files to local directory
5. **ESC** or **'q'** to return to main menu

> **Note**: Downloads are saved to `./downloaded_evtx/` by default

### Option 2: Run Chainsaw Hunt

1. First, select files using **Option 1**
2. Select **Option 2** to configure hunt options:
   - Use Sigma Rules (ON/OFF)
   - Use Custom Rules (ON/OFF)
   - Output Format (CSV, JSON, LOG)
   - Full Output (includes all event fields)
   - Include Metadata
3. Press **'6'** to execute the hunt
4. Results are saved to `./chainsaw_results/hunt_YYYYMMDD_HHMMSS.csv`

### Option 3: Run Chainsaw Search

1. First, select files using **Option 1**
2. Select **Option 3** to configure search options:
   - Enter Search Pattern (string or regex)
   - Enter Regex Pattern (override string pattern)
   - Enter TAU Expression (advanced queries)
   - Ignore Case (case-insensitive search)
   - Output Format (CSV, JSON)
3. Press **'6'** to execute the search
4. Results are saved to `./chainsaw_results/search_YYYYMMDD_HHMMSS.json`

### Option 4: Configure Settings

View current configuration settings. To modify:
- Edit the `.env` file directly
- Restart the application to load new settings

### Option 5: View Selected Files

Display all currently selected EVTX files

## Command-Line Examples

### Hunt with Sigma Rules Only

```PowerShell
python chainsaw_frontend.py
# Then: 1 -> select files -> 2 -> adjust options -> 6
```

### Hunt with Both Sigma and Custom Rules

From CLI, after downloading files:

```batch
chainsaw hunt ./downloaded_evtx -s sigma/ --mapping sigma-event-logs-all.yml -r rules/ --csv
```

### Search for Suspicious Keywords

```batch
chainsaw search "mimikatz|psexec|secretsdump" ./downloaded_evtx -i --json
```

### Hunt with Time Range Filtering

```batch
chainsaw hunt ./downloaded_evtx -s sigma/ --mapping sigma-event-logs-all.yml ^
    --from "2024-01-01T00:00:00" --to "2024-01-31T23:59:59" --csv
```

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `SMB_HOST` | - | SMB server hostname or IP |
| `SMB_PORT` | 445 | SMB port (usually 445) |
| `SMB_SHARE_NAME` | - | Network share name (e.g., `Logs`, `Share1`) |
| `SMB_USERNAME` | - | Username for SMB authentication |
| `SMB_PASSWORD` | - | Password for SMB authentication |
| `SMB_DOMAIN` | - | Domain name (for domain accounts) |
| `CHAINSAW_EXECUTABLE` | chainsaw | Path to chainsaw binary |
| `CHAINSAW_SIGMA_PATH` | ./chainsaw | Path to Sigma rules directory |
| `CHAINSAW_RULES_PATH` | ./chainsaw/rules | Path to Chainsaw rules directory |
| `CHAINSAW_MAPPING_FILE` | ./chainsaw/mappings/sigma-event-logs-all.yml | Mapping file for Sigma rules |
| `CHAINSAW_OUTPUT_FORMAT` | csv | Output format (csv, json) |
| `CHAINSAW_TIMEZONE` | UTC | Timezone for timestamp display |
| `CHAINSAW_COLUMN_WIDTH` | 50 | Column width for tabular output |
| `CHAINSAW_SKIP_ERRORS` | false | Continue on errors |
| `CHAINSAW_LOAD_UNKNOWN` | false | Load unknown file types |
| `OUTPUT_PATH` | ./chainsaw_results | Directory for results |
| `LOG_LEVEL` | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `LOG_FILE` | ./evtxripper.log | Path to log file |

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1-5` | Select menu option |
| `Space` | Toggle file selection (in file browser) |
| `d` | Download selected files (in file browser) |
| `ESC` or `q` | Return to previous menu |
| `q` | Quit application (from main menu) |

## Troubleshooting

### SMB Connection Failed

**Problem**: "Failed to connect to SMB share"

**Solutions**:
- Verify SMB credentials in `.env` file
- Check if SMB server is reachable: `ping <SMB_HOST>`
- Verify SMB port (usually 445): `Test-NetConnection -ComputerName <host> -Port 445`
- Check firewall rules allowing SMB traffic
- Verify share name is correct
- For domain accounts, ensure `SMB_DOMAIN` is set

### Chainsaw Not Found

**Problem**: "chainsaw: command not found"

**Solutions**:
- Ensure `chainsaw` binary is in PATH
- Or provide full path in `.env`: `CHAINSAW_EXECUTABLE=/path/to/chainsaw`
- Verify chainsaw is executable:
  - Windows: `where chainsaw`
  - Linux/macOS: `which chainsaw`

### Permission Denied on Files

**Problem**: Cannot download files from SMB share

**Solutions**:
- Verify SMB username has read permissions
- Check share-level permissions
- Verify NTFS permissions on remote files
- Try with domain\username format: `DOMAIN\analyst`

### Python Module Not Found

**Problem**: `ModuleNotFoundError: No module named 'smb'`

**Solution**:
```PowerShell
pip install -r requirements.txt
# Or specifically:
pip install pysmb python-dotenv
```

### File Encoding Issues

**Problem**: EVTX files show encoding errors

**Solution**:
- Update Chainsaw to latest version
- Enable `CHAINSAW_LOAD_UNKNOWN=true` in `.env`
- Check if files are actually EVTX format

## Integration with PowerShell Scripts

The `.env` file can be used by PowerShell scripts for consistent configuration:

```PowerShell
# Load environment variables in PowerShell
$envFile = '.\.env'
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([^=]+)=(.*)$') {
        $key = $Matches[1].Trim()
        $value = $Matches[2].Trim()
        [Environment]::SetEnvironmentVariable($key, $value)
    }
}
```

## Advanced Usage

### Custom Sigma Rules

Place custom Sigma rules in the `chainsaw/rules/` directory. The frontend will automatically include them in hunt operations.

### Output Filtering

Results can be post-processed using PowerShell:

```PowerShell
# Filter CSV results for specific severity
$results = Import-Csv "./chainsaw_results/hunt_*.csv"
$results | Where-Object { $_.Severity -eq "High" } | Export-Csv filtered_results.csv
```

### Scheduled Analysis

Create a scheduled task to run periodic analysis:

```PowerShell
$action = New-ScheduledTaskAction -Execute "python" -Argument "chainsaw_frontend.py"
$trigger = New-ScheduledTaskTrigger -Daily -At 2am
Register-ScheduledTask -Action $action -Trigger $trigger -TaskName "ChainsawAnalysis"
```

## Logging

Application logs are written to the file specified in `LOG_FILE` (default: `./evtxripper.log`).

View logs:
```PowerShell
Get-Content ./evtxripper.log -Tail 50
```

Set log level:
```ini
LOG_LEVEL=DEBUG    # For detailed troubleshooting
LOG_LEVEL=INFO     # Standard logging
LOG_LEVEL=WARNING  # Only warnings and errors
LOG_LEVEL=ERROR    # Only errors
```

## Security Considerations

1. **Credentials Storage**: The `.env` file contains plaintext credentials. Protect with appropriate file permissions.
2. **Network**: Use VPN or secure network for SMB connections.
3. **Firewall**: Restrict SMB access to authorized hosts.
4. **Logging**: Review logs regularly for security events.
5. **Passwords**: Change default/test passwords immediately.

## Contributing & Support

For issues or feature requests:
1. Check logs in `./evtxripper.log`
2. Verify `.env` configuration
3. Ensure Chainsaw binary is up-to-date
4. Review Chainsaw documentation: https://github.com/WithSecureLabs/chainsaw

## References

- [Chainsaw GitHub Repository](https://github.com/WithSecureLabs/chainsaw)
- [Sigma Rule Format](https://github.com/SigmaHQ/sigma)
- [Windows Event IDs](https://www.ultimatewindowssecurity.com/securitylog/encyclopedia/)
- [EVTX Format](https://github.com/mozilla/rust-evtx)
