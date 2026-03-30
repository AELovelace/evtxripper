# Quick Start Guide - Chainsaw Frontend

## 🚀 What's New

This package now includes:
- **`.env` file** - Centralized configuration for all variables
- **`chainsaw_frontend.py`** - Interactive ncurses UI for Chainsaw
- **`ChainsawIntegration.ps1`** - PowerShell helper for integration
- **`requirements.txt`** - Python dependencies

## 📋 Prerequisites

```
✓ Python 3.7+
✓ Chainsaw binary (in PATH or specified in .env)
✓ Sigma rules (included in ./chainsaw/)
✓ Access to SMB share with EVTX files
✓ Network connectivity to SMB server
```

## ⚡ 5-Minute Setup

### Step 1: Install Python Dependencies
```PowerShell
pip install -r requirements.txt
```

### Step 2: Configure the .env File
Edit `.env` and set your SMB credentials:
```ini
SMB_HOST=192.168.1.100           # Your SMB server
SMB_SHARE_NAME=EventLogs         # Share name
SMB_USERNAME=analyst             # Your username
SMB_PASSWORD=YourPassword123     # Your password
SMB_DOMAIN=MYCOMPANY             # Your domain
```

### Step 3: Verify Configuration
```PowerShell
.\ChainsawIntegration.ps1 -TestConnection
```

### Step 4: Launch the Frontend
```PowerShell
python chainsaw_frontend.py
```

## 🎮 Using the Interface

### Main Menu Options

```
1. Browse SMB Share & Select EVTX Files
   ├── Connect to remote SMB share
   ├── Browse folders and files
   ├── Select files (Space to toggle)
   └── Download to local directory

2. Run Chainsaw Hunt
   ├── Configure hunt options
   ├── Choose output format (CSV/JSON)
   ├── Enable Sigma and/or custom rules
   └── Execute hunt on selected files

3. Run Chainsaw Search
   ├── Enter search pattern
   ├── Optional: regex or TAU expressions
   ├── Configure output format
   └── Execute search on selected files

4. Configure Settings
   └── View current .env settings

5. View Selected Files
   └── Display all selected EVTX files

0. Exit
   └── Quit application
```

## 📚 Workflow Examples

### Example 1: Hunt for Malicious Activity

```
1. Main menu → Option 1 (Browse SMB)
2. Select multiple EVTX files (use Space)
3. Return to main menu
4. Option 2 (Hunt)
5. Configure:
   - Use Sigma Rules: ON
   - Use Custom Rules: ON
   - Output Format: CSV
6. Execute (press 6)
7. Results saved to ./chainsaw_results/hunt_*.csv
```

### Example 2: Search for Specific Keywords

```
1. Main menu → Option 1 (Browse SMB)
2. Select EVTX files
3. Return to main menu
4. Option 3 (Search)
5. Enter pattern: "mimikatz|psexec|secretsdump"
6. Configure:
   - Ignore Case: ON
   - Output: JSON
7. Execute
8. Results saved to ./chainsaw_results/search_*.json
```

### Example 3: Automated Export + Analysis

```PowerShell
# Step 1: Export local EVTX and upload to share
.\ChainsawIntegration.ps1 -ExportEvtx

# Step 2: Launch frontend to analyze
python chainsaw_frontend.py
# Then browse and select the newly uploaded files
```

## 🔧 Configuration Guide

### SMB Settings (Required for file browser)
```ini
SMB_HOST=192.168.1.100          # SMB server IP or hostname
SMB_PORT=445                    # Standard SMB port
SMB_SHARE_NAME=Logs             # Share name to browse
SMB_USERNAME=analyst            # Username
SMB_PASSWORD=password           # Password
SMB_DOMAIN=COMPANY              # Active Directory domain
```

### Chainsaw Paths
```ini
CHAINSAW_EXECUTABLE=chainsaw                                    # Binary path
CHAINSAW_SIGMA_PATH=./chainsaw/mappings                         # Sigma rules
CHAINSAW_RULES_PATH=./chainsaw/rules                            # Custom rules
CHAINSAW_MAPPING_FILE=./chainsaw/mappings/sigma-event-logs-all.yml
```

### Output Options
```ini
CHAINSAW_OUTPUT_FORMAT=csv      # csv, json, or log
CHAINSAW_TIMEZONE=UTC           # Timezone for timestamps
CHAINSAW_COLUMN_WIDTH=50        # Table column width
OUTPUT_PATH=./chainsaw_results  # Results directory
```

## 🎯 Common Tasks

### Update SMB Credentials
```ini
# Edit .env file
SMB_USERNAME=newuser
SMB_PASSWORD=newpassword
# Restart the application
```

### Change Output Format
```ini
# Edit .env
CHAINSAW_OUTPUT_FORMAT=json    # Changed from csv
# Option 2 (Hunt) will now use JSON output
```

### Enable All Rule Detections
```ini
CHAINSAW_SKIP_ERRORS=true
CHAINSAW_LOAD_UNKNOWN=true
```

### Set Custom Timezone
```ini
CHAINSAW_TIMEZONE=America/New_York    # or any IANA timezone
```

## 🐛 Troubleshooting

### Can't Connect to SMB Share

**Check 1**: Verify SMB is accessible
```PowerShell
.\ChainsawIntegration.ps1 -TestConnection
```

**Check 2**: Verify credentials in .env
- Username format: `domain\username` or just `username`
- Password must be correct
- Domain field may be required

**Check 3**: Test network
```PowerShell
ping 192.168.1.100           # Replace with your host
Test-NetConnection -ComputerName 192.168.1.100 -Port 445
```

### Chainsaw Not Found

**Solution 1**: Add to PATH
```PowerShell
$env:Path += ";C:\path\to\chainsaw"
```

**Solution 2**: Specify full path in .env
```ini
CHAINSAW_EXECUTABLE=C:\tools\chainsaw\chainsaw.exe
```

### Python Module Errors

```PowerShell
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall

# Verify installation
python -c "import smb; print('OK')"
```

### Permission Denied on Download

- Verify SMB username has read permissions
- Check share-level permissions
- Try account with higher privilege
- Check file ownership

## 📊 Understanding Results

### Hunt Results
Hunt operations analyze EVTX files against Sigma and custom rules.

Output example (CSV):
```
timestamp,detections,Event ID,Computer,Rule Name
2024-01-15 10:30:00,"Process-related detection",4688,DESKTOP-ABC,New Process Creation
```

### Search Results
Search operations look for string patterns in event logs.

Output example (JSON):
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "pattern": "mimikatz",
  "computer": "DESKTOP-ABC",
  "event_id": 4688,
  "event_data": {...}
}
```

## 🛡️ Security Notes

⚠️ **Important**:
- `.env` file contains plaintext passwords
- Restrict file permissions: `icacls .env /grant:r "%USERNAME%:F"`
- Don't commit `.env` to version control
- Use accounts with minimal required permissions
- Consider using group managed service accounts for automation

## 📖 Additional Resources

- **Chainsaw Docs**: https://github.com/WithSecureLabs/chainsaw
- **Sigma Rules**: https://github.com/SigmaHQ/sigma
- **Windows Event IDs**: https://www.ultimatewindowssecurity.com/
- **Full Setup Guide**: See `SETUP.md`

## 🔄 Integration with PowerShell Scripts

The existing `Export-AllEvtx.ps1` now works with `.env` configuration:

```PowerShell
# Load environment and export EVTX
.\ChainsawIntegration.ps1 -ExportEvtx

# Or directly with PowerShell
$env = @{}
Get-Content .\.env | % { if ($_ -match '^\s*([^=]+)=(.*)$') { 
    $env[$Matches[1]] = $Matches[2] 
}}
.\Export-AllEvtx.ps1 -CopyToRemoteShare -RemoteShareRoot $env['REMOTE_SHARE_ROOT']
```

## 🎓 Tips & Tricks

### Tip 1: Keep Files Downloaded
Download files once, reuse for multiple hunts:
```
1. Browse & download EVTX files
2. Files saved in ./downloaded_evtx/
3. Can run multiple analyses without re-downloading
```

### Tip 2: Save Frequently Used Searches
Create bash/PowerShell scripts for common searches:
```PowerShell
# common_hunt.ps1
python chainsaw_frontend.py
# Then manually select common files and run
```

### Tip 3: Chain Results
Use hunt results as input for further searches:
```PowerShell
# Export high-priority events
$hunt = Import-Csv "hunt_results.csv"
$hunt | Where { $_.Severity -eq "High" } | export-csv filtered.csv
```

### Tip 4: Automate with Task Scheduler
```PowerShell
# Run weekly analysis
$action = New-ScheduledTaskAction -Execute "python" `
    -Argument "chainsaw_frontend.py"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 2am
Register-ScheduledTask -Action $action -Trigger $trigger -TaskName "ChainsawAnalysis"
```

## 📞 Support

For issues:
1. Check `./evtxripper.log` for error messages
2. Run diagnostics: `.\ChainsawIntegration.ps1 -TestConnection`
3. Verify `.env` configuration
4. Check Chainsaw version: `chainsaw --version`
5. Review full documentation in `SETUP.md`

---

**Next Steps**: 
1. ✅ Run setup: `pip install -r requirements.txt`
2. ✅ Configure: Edit `.env` file
3. ✅ Test: `.\ChainsawIntegration.ps1 -TestConnection`
4. ✅ Launch: `python chainsaw_frontend.py`

Happy hunting! 🔍
