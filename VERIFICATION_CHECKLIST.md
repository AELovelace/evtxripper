# ✅ Pre-Launch Verification Checklist

Use this checklist to verify everything is ready before launching the Chainsaw Frontend.

---

## 📋 System Requirements

- [ ] Windows, Linux, or macOS operating system
- [ ] Administrator or sudo access (for elevated operations if needed)
- [ ] Network connectivity to SMB server
- [ ] At least 1 GB free disk space for results

---

## 🐍 Python Environment

- [ ] Python 3.7 or higher installed
  ```PowerShell
  python --version  # Should show 3.7+
  ```
- [ ] Python available in PATH
  ```PowerShell
  where python  # (Windows)
  which python3 # (Linux/macOS)
  ```
- [ ] pip package manager working
  ```PowerShell
  pip --version
  ```

---

## 📦 Dependencies Installation

- [ ] Navigate to project directory
  ```PowerShell
  cd c:\Scripts\evtxripper
  ```
- [ ] Install required packages
  ```PowerShell
  pip install -r requirements.txt
  ```
- [ ] Verify installations
  ```PowerShell
  pip list | grep -E "python-dotenv|pysmb"
  ```

### Verify with Python:
- [ ] Check python-dotenv
  ```PowerShell
  python -c "import dotenv; print('python-dotenv OK')"
  ```
- [ ] Check pysmb
  ```PowerShell
  python -c "import smb; print('pysmb OK')"
  ```

---

## ⚙️ Configuration File (.env)

- [ ] .env file exists in project directory
  ```PowerShell
  Test-Path .\.env  # Should return True
  ```
- [ ] .env file is readable
  ```PowerShell
  Get-Content .\.env | head -10  # Show first 10 lines
  ```

### SMB Configuration
- [ ] `SMB_HOST` is configured
  ```
  Example: 192.168.1.100 or fileserver.company.com
  ```
- [ ] `SMB_PORT` is correct
  ```
  Standard: 445
  ```
- [ ] `SMB_SHARE_NAME` is specified
  ```
  Example: EventLogs, Logs, Share1
  ```
- [ ] `SMB_USERNAME` is set
  ```
  Format: username or DOMAIN\username
  ```
- [ ] `SMB_PASSWORD` is set
  ```
  ⚠️  Ensure file is secured: icacls .\.env /grant:r "%USERNAME%:F"
  ```
- [ ] `SMB_DOMAIN` is set (if using domain accounts)
  ```
  Example: COMPANY.COM or leave empty for local accounts
  ```

### Chainsaw Configuration
- [ ] `CHAINSAW_EXECUTABLE` points to valid Chainsaw binary
  ```PowerShell
  chainsaw --version  # (if in PATH)
  # OR
  C:\path\to\chainsaw --version  # (if full path)
  ```
- [ ] `CHAINSAW_SIGMA_PATH` directory exists
  ```PowerShell
  Test-Path ./chainsaw  # Should return True
  ```
- [ ] `CHAINSAW_MAPPING_FILE` exists
  ```PowerShell
  Test-Path ./chainsaw/mappings/sigma-event-logs-all.yml
  ```
- [ ] `CHAINSAW_RULES_PATH` directory exists
  ```PowerShell
  Test-Path ./chainsaw/rules  # Should return True
  ```

### Output Configuration
- [ ] `OUTPUT_PATH` directory exists or will be created
  ```PowerShell
  mkdir -Force ./chainsaw_results
  ```
- [ ] Write permissions on output directory
  ```PowerShell
  New-Item -Path ./chainsaw_results/test.txt -Force
  Remove-Item -Path ./chainsaw_results/test.txt
  ```

### Logging Configuration
- [ ] `LOG_FILE` path is writable
  ```PowerShell
  New-Item -Path ./evtxripper.log -Force
  Get-Content ./evtxripper.log
  ```

---

## 🔌 Network Connectivity

- [ ] Ping SMB host
  ```PowerShell
  ping <SMB_HOST>  # Replace with your SMB_HOST
  # Should show successful responses
  ```
- [ ] Test SMB port
  ```PowerShell
  Test-NetConnection -ComputerName <SMB_HOST> -Port 445
  # Should show "TcpTestSucceeded : True"
  ```

---

## 🛡️ SMB Access Verification

Run the PowerShell helper to test SMB connectivity:

- [ ] Load and test configuration
  ```PowerShell
  .\ChainsawIntegration.ps1 -LoadEnv
  # Should output: "Loaded X environment variables"
  ```
- [ ] Test all connectivity
  ```PowerShell
  .\ChainsawIntegration.ps1 -TestConnection
  ```
  This should show:
  - [ ] ✓ Network connection successful
  - [ ] ✓ SMB access successful
  - [ ] ✓ Chainsaw found

- [ ] If any test fails, review the output and check:
  - [ ] SMB credentials in .env are correct
  - [ ] SMB host is reachable
  - [ ] Network share exists
  - [ ] Username has permissions to share

---

## 🔧 Chainsaw Verification

- [ ] Chainsaw executable found
  ```PowerShell
  chainsaw --version  # Should show version number
  ```
- [ ] Sigma rules directory accessible
  ```PowerShell
  Get-ChildItem ./chainsaw -Recurse -Filter "*.yml" | Measure-Object
  # Should show multiple .yml files
  ```
- [ ] Mapping file readable
  ```PowerShell
  Get-Content ./chainsaw/mappings/sigma-event-logs-all.yml | Select-Object -First 1
  # Should show YAML content
  ```
- [ ] Custom rules directory exists
  ```PowerShell
  Test-Path ./chainsaw/rules  # Should return True
  Get-ChildItem ./chainsaw/rules | Measure-Object
  # Should show rule files
  ```

---

## 🐛 Application Launch Test

- [ ] No Python syntax errors
  ```PowerShell
  python -m py_compile chainsaw_frontend.py
  # Should complete without errors
  ```
- [ ] Application imports all dependencies
  ```PowerShell
  python -c "from chainsaw_frontend import *; print('Imports OK')"
  ```
- [ ] Test SMB module specifically
  ```PowerShell
  python -c "import smb.SMBConnection; print('SMB module OK')"
  ```

---

## 📝 File Permissions & Security

- [ ] .env file permissions restricted (Windows)
  ```PowerShell
  icacls .env /grant:r "%USERNAME%:F"
  icacls .env /inheritance:r
  ```
- [ ] .env not in version control
  ```PowerShell
  # Check Git ignore if using version control
  ```
- [ ] Python files are readable
  ```PowerShell
  Get-Item chainsaw_frontend.py | Select-Object Name, Length
  Get-Item ChainsawIntegration.ps1 | Select-Object Name, Length
  ```

---

## 💾 Disk Space Check

- [ ] At least 1 GB free space in output directory
  ```PowerShell
  (Get-Volume -DriveLetter C).SizeRemaining / 1GB  # Shows available GB
  ```
- [ ] At least 500 MB free for temporary files
  ```PowerShell
  (Get-Item $env:TEMP).PSPath
  Get-ChildItem $env:TEMP | Measure-Object -Property Length -Sum
  ```

---

## 🎯 Final Launch Verification

### Step 1: Show Configuration
```PowerShell
.\ChainsawIntegration.ps1 -ShowConfig
```
✅ Verify output shows:
- [ ] Correct SMB host
- [ ] Correct share name
- [ ] Correct username
- [ ] Correct Chainsaw paths

### Step 2: Test Connection
```PowerShell
.\ChainsawIntegration.ps1 -TestConnection
```
✅ Should show:
- [ ] ✓ Network connection successful
- [ ] ✓ SMB access successful
- [ ] ✓ Chainsaw found

### Step 3: Launch Application
```PowerShell
python chainsaw_frontend.py
```
✅ Application should:
- [ ] Display without errors
- [ ] Show main menu
- [ ] Respond to keyboard input
- [ ] Allow navigation between menu items

### Step 4: Test Core Functions
In the application:
- [ ] **Option 1**: Browse SMB - Should connect and list files
- [ ] **Option 2**: Hunt - Should show options menu
- [ ] **Option 3**: Search - Should show search options
- [ ] **Option 4**: Configure - Should display settings
- [ ] **ESC/q**: Navigation between menus works

---

## ⚠️ Common Issues & Quick Fixes

| Issue | Quick Fix |
|-------|-----------|
| "Module not found" | `pip install -r requirements.txt --force-reinstall` |
| "Cannot connect to SMB" | Run `.\ChainsawIntegration.ps1 -TestConnection` |
| "Chainsaw not found" | Verify PATH or set full path in `.env` |
| "Connection timeout" | Check network connectivity, verify SMB host |
| "Permission denied" | Check file permissions on `.env`, verify SMB credentials |
| "Python errors" | Verify Python version 3.7+, check logs in `./evtxripper.log` |

For detailed troubleshooting: See SETUP.md

---

## 📋 Checklist Summary

**Before Launch - Count Completed:**

- [ ] System Requirements (1 items)
- [ ] Python Environment (3 items)
- [ ] Dependencies Installation (3 items)
- [ ] Configuration File (11 items)
- [ ] Network Connectivity (2 items)
- [ ] SMB Access Verification (3 items)
- [ ] Chainsaw Verification (4 items)
- [ ] Application Launch Test (3 items)
- [ ] File Permissions & Security (3 items)
- [ ] Disk Space Check (2 items)
- [ ] Final Launch Verification (4 items)

**Total: 43 items**

🎯 **Target: 43/43 items checked** ✅

---

## 🚀 Ready to Launch?

If all items are checked:

```PowerShell
python chainsaw_frontend.py
```

This will launch the Chainsaw Frontend with:
- ✅ Proper SMB connectivity
- ✅ Configured paths and options
- ✅ Verified dependencies
- ✅ Secured credentials
- ✅ Logging enabled

---

## 📞 If Something Doesn't Work

1. **Check the obvious:**
   - Did you edit `.env` with your settings?
   - Is the SMB server reachable? (ping it)
   - Are credentials correct?

2. **Review logs:**
   ```PowerShell
   Get-Content ./evtxripper.log -Tail 20
   ```

3. **Run diagnostics:**
   ```PowerShell
   .\ChainsawIntegration.ps1 -TestConnection
   ```

4. **Reinstall dependencies:**
   ```PowerShell
   pip install -r requirements.txt --force-reinstall
   ```

5. **See detailed help:**
   - Check SETUP.md Troubleshooting section
   - Read README.md for architecture overview
   - Review .env file comments

---

## ✅ Success Indicators

You'll know everything is working when:

1. ✅ `.\ChainsawIntegration.ps1 -TestConnection` shows all checks passed
2. ✅ Application launches without errors: `python chainsaw_frontend.py`
3. ✅ Main menu displays correctly
4. ✅ Can browse SMB share and see files
5. ✅ Can select files and run hunt/search
6. ✅ Results are saved to `./chainsaw_results/`

---

Prepared to proceed? Launch the application and start analyzing! 🔍

For help: Read QUICKSTART.md → SETUP.md → IMPLEMENTATION_SUMMARY.md
