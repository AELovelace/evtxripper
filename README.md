# EVTX Ripper - Chainsaw Forensic Analysis Suite
## Interactive Frontend for Windows Event Log Analysis

[![PowerShell](https://img.shields.io/badge/PowerShell-5.0+-blue)](https://github.com/PowerShell/PowerShell)
[![Python](https://img.shields.io/badge/Python-3.7+-green)](https://github.com/python/cpython)
[![Chainsaw](https://img.shields.io/badge/Chainsaw-2.x-orange)](https://github.com/WithSecureLabs/chainsaw)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## 🎯 Overview

**EVTX Ripper** is a comprehensive suite for forensic analysis of Windows Event Logs (EVTX). It combines:

- **PowerShell Export Module** - Automated EVTX collection from local machines
- **Chainsaw Frontend** - Interactive ncurses UI for remote EVTX browsing and analysis
- **Centralized Configuration** - Single `.env` file for all settings and credentials
- **Sigma Rule Integration** - Automated threat detection using industry-standard rules

### What It Does

```
Local Machine          Network/SMB Share         Analysis Engine
┌──────────────────┐   ┌──────────────────┐     ┌──────────────────┐
│ Export-AllEvtx   │──▶│ EVTX Repository  │◀────│ Chainsaw Backend │
│ (PowerShell)     │   │ (SMB Share)      │     │ (Hunt/Search)    │
└──────────────────┘   └──────────────────┘     └──────────────────┘
                              ▲                           ▲
                              │                           │
                       ┌───────┴───────┐          ┌──────┴──────┐
                       │ Chainsaw     │          │ Sigma Rules │
                       │ Frontend UI  │          │ Custom Rls  │
                       │ (ncurses)    │          │ Mappings    │
                       └──────────────┘          └─────────────┘
```

---

## 📦 What's Included

### 1. **Configuration System** (`.env`)
Central configuration file for all components:
- SMB/network share credentials
- Chainsaw executable and rules paths
- Output formats and locations
- Logging settings

### 2. **Python Frontend** (`chainsaw_frontend.py`)
Interactive terminal UI with:
- 🔍 SMB share browser for EVTX file discovery
- 🎯 Chainsaw hunt interface (Sigma rule execution)
- 🔎 Chainsaw search interface (pattern matching)
- ⚙️ Configuration viewer
- 💾 Results management

### 3. **PowerShell Integration** (`ChainsawIntegration.ps1`)
Helper script for:
- Verifying environment configuration
- Testing SMB connectivity
- Exporting and syncing EVTX files
- Integration with existing scripts

### 4. **Documentation**
- **QUICKSTART.md** - Get started in 5 minutes ⭐ START HERE
- **SETUP.md** - Comprehensive setup and advanced usage
- **README.md** - This file, architecture overview

---

## 🚀 Quick Start (5 Minutes)

### Step 1: Install Dependencies
```PowerShell
pip install -r requirements.txt
```

### Step 2: Configure SMB Access
Edit `.env` file:
```ini
SMB_HOST=192.168.1.100
SMB_SHARE_NAME=EventLogs
SMB_USERNAME=analyst
SMB_PASSWORD=YourPassword
SMB_DOMAIN=COMPANY
```

### Step 3: Verify Setup
```PowerShell
.\ChainsawIntegration.ps1 -TestConnection
```

### Step 4: Launch Frontend
```PowerShell
python chainsaw_frontend.py
```

**👉 For detailed instructions, see [QUICKSTART.md](QUICKSTART.md)**

---

## 📚 Documentation Structure

```
├─ QUICKSTART.md          ⭐ START HERE (5-min setup)
├─ SETUP.md               📖 Complete reference guide
├─ README.md              📋 This file (architecture)
│
├─ .env                   ⚙️  Configuration file
├─ chainsaw_frontend.py   🐍 Python UI application
├─ ChainsawIntegration.ps1 🔧 PowerShell helper
│
├─ Export-AllEvtx.ps1     📤 EVTX export (existing)
├─ Export-AllEvtxRMM.ps1  📤 RMM integration (existing)
└─ requirements.txt       📦 Python dependencies
```

**Navigation Guide:**
- **New Users**: Start with [QUICKSTART.md](QUICKSTART.md)
- **Detailed Config**: See [SETUP.md](SETUP.md)
- **Architecture**: Continue reading below

---

## 🏗️ System Architecture

### Component Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    EVTX Ripper Suite                         │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │          Configuration Layer (.env file)             │   │
│  │  ┌────────────────────────────────────────────────┐  │   │
│  │  │ SMB Credentials │ Paths │ Options │ Logging    │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  └─────────┬──────────────────────┬────────────┬────────┘   │
│            │                      │            │             │
│  ┌─────────▼──────────┐  ┌───────▼────────┐  │             │
│  │  PowerShell        │  │  Python        │  │             │
│  │  Export Module     │  │  Frontend UI   │  │             │
│  │ ┌────────────────┐ │  │ ┌────────────┐ │  │             │
│  │ │ Export EVTX    │ │  │ │ File Browse│ │  │             │
│  │ │ Upload to SMB  │ │  │ │ Hunt Exec  │ │  │             │
│  │ │ PowerShell API │ │  │ │ Search Exec│ │  │             │
│  │ └────────────────┘ │  │ └────────────┘ │  │             │
│  └────────────────────┘  └────────────────┘  │             │
│            │                      │            │             │
│            └──────────┬───────────┘            │             │
│                       │                        │             │
│  ╔════════════════════╩════════════════════╗  │             │
│  ║   SMB Network I/O Layer                ║  │             │
│  ║ (SMB Handler - Remote Share Access)    ║  │             │
│  ╚═══════════════╦═════════════════════════╝  │             │
│                 │                             │             │
└─────────────────┼─────────────────────────────┼─────────────┘
                  │                             │
        SMB Share (Event Logs)      Chainsaw Binary
        ┌─────────▼─────────┐      ┌────────────▼────────────┐
        │ Remote EVTX Files │      │ Detection Engine        │
        │ (Forensics Data)  │      │ ┌────────────────────┐  │
        │                   │      │ │ Sigma Rules        │  │
        │                   │      │ │ Custom Rules       │  │
        │                   │      │ │ Mapping Files      │  │
        └───────────────────┘      │ └────────────────────┘  │
                                   └────────────────────────┘
                                           │
                                           │ Results (JSON/CSV)
                                           ▼
                                   ./chainsaw_results/
```

### Data Flow

**Export Workflow:**
```
Local System EVTX
    ↓
Export-AllEvtx.ps1 (reads .env)
    ↓
Collects all enabled event logs
    ↓
Exports to: OUTPUT_DIRECTORY (from .env)
    ↓
(If COPY_TO_REMOTE_SHARE=true)
    ↓
Upload to: REMOTE_SHARE_ROOT\REMOTE_DIRECTORY
    ↓
SMB Share (ready for analysis)
```

**Analysis Workflow:**
```
chainsaw_frontend.py starts
    ↓
Loads .env configuration
    ↓
User browses SMB_HOST\SMB_SHARE_NAME
    ↓
Selects EVTX files
    ↓
Chooses Hunt or Search
    ↓
Builds Chainsaw command:
├─ Hunt: Uses --sigma, --mapping, --rules flags
└─ Search: Uses pattern, -e (regex), -t (tau expressions)
    ↓
Executes Chainsaw on selected files
    ↓
Saves results to OUTPUT_PATH
    ↓
User reviews results (CSV/JSON)
```

---

## 🔧 Configuration Deep Dive

### Environment Variables
All configuration is managed through the `.env` file:

| Component | Variables | Purpose |
|-----------|-----------|---------|
| **Export Module** | `OUTPUT_DIRECTORY`, `COPY_TO_REMOTE_SHARE`, `REMOTE_SHARE_ROOT`, `REMOTE_DIRECTORY`, `REMOTE_USERNAME` | Control EVTX export from local machine |
| **SMB Access** | `SMB_HOST`, `SMB_PORT`, `SMB_SHARE_NAME`, `SMB_USERNAME`, `SMB_PASSWORD`, `SMB_DOMAIN` | Configure network share access |
| **Chainsaw** | `CHAINSAW_EXECUTABLE`, `CHAINSAW_SIGMA_PATH`, `CHAINSAW_RULES_PATH`, `CHAINSAW_MAPPING_FILE` | Define detection engine paths |
| **Hunt Options** | `CHAINSAW_OUTPUT_FORMAT`, `CHAINSAW_TIMEZONE`, `CHAINSAW_COLUMN_WIDTH`, `CHAINSAW_SKIP_ERRORS` | Control threat hunting behavior |
| **Output** | `OUTPUT_PATH`, `RESULTS_SUBDIRECTORY_BY_DATE` | Manage where results are saved |
| **Logging** | `LOG_LEVEL`, `LOG_FILE` | Control application logging |

**See `.env` file for detailed comments on each setting.**

---

## 🎮 User Interface Walkthrough

### Main Menu
```
 ╔════════════════════════════════════════════╗
 ║ Chainsaw Forensic Event Log Analysis Frontend ║
 ╠════════════════════════════════════════════╣
 ║ 1. Browse SMB Share & Select EVTX Files   ║
 ║ 2. Run Chainsaw Hunt                      ║
 ║ 3. Run Chainsaw Search                    ║
 ║ 4. Configure Settings                    ║
 ║ 5. View Selected Files                    ║
 ║ 0. Exit                                   ║
 ║                                           ║
 ║ Selected files: 3                         ║
 ║ Press: 1-5 to select, q to quit           ║
 ╚════════════════════════════════════════════╝
```

### Workflow Example: Hunt for Malicious Activity
```
Start Frontend
    │
    ├─→ [1] Browse SMB Share
    │       ├─→ Connect to \\fileserver\logs
    │       ├─→ Navigate folders
    │       ├─→ [Space] Select: Security.evtx
    │       ├─→ [Space] Select: System.evtx
    │       └─→ [ESC] Return to menu
    │
    ├─→ [2] Hunt
    │       ├─→ Configure: Sigma ON, Rules ON
    │       ├─→ Format: CSV
    │       ├─→ [6] Execute
    │       └─→ Results → ./chainsaw_results/hunt_20240115_103000.csv
    │
    └─→ Review results in Excel or PowerShell
```

---

## 📊 Example Analyses

### Hunt Analysis (Sigma Rules)
Detects malicious activity patterns:
```csv
timestamp,detections,Event ID,Computer,Rule,Severity
2024-01-15 10:30:00,Mimikatz Detected,4688,DESKTOP-ABC,T1008,High
2024-01-15 11:45:00,Pass-the-Hash,4776,DESKTOP-XYZ,T1550,Critical
```

### Search Analysis (Pattern Matching)
Finds specific strings or regex patterns:
```json
{
  "results": [
    {
      "timestamp": "2024-01-15T10:30:00Z",
      "pattern_matched": "mimikatz",
      "computer": "DESKTOP-ABC",
      "event_id": 4688,
      "source": "Process Command Line"
    }
  ]
}
```

---

## 🔐 Security Considerations

### Credential Management
- ✅ Store credentials in `.env` file
- ✅ Restrict file permissions: `icacls .env /grant:r "%USERNAME%:F"`
- ✅ Use service accounts with minimal privileges
- ❌ Don't commit `.env` to version control
- ❌ Don't share credentials via email

### Network Security
- Use SMB over VPN for remote access
- Restrict SMB port 445 via firewall
- Use strong domain passwords
- Consider using managed service accounts

### Data Protection
- Store results in secure location
- Don't include sensitive data in logs
- Follow data retention policies
- Audit access to forensic files

---

## 🐛 Troubleshooting

### Common Issues

**SMB Connection Failed**
```PowerShell
.\ChainsawIntegration.ps1 -TestConnection
# Check: SMB_HOST, credentials, network connectivity
```

**Chainsaw Not Found**
```PowerShell
chainsaw --version  # Verify in PATH
# Or set full path: CHAINSAW_EXECUTABLE=C:\tools\chainsaw\chainsaw.exe
```

**Python Module Error**
```PowerShell
pip install -r requirements.txt --force-reinstall
```

**Permission Denied**
- Verify SMB account permissions
- Check file ownership
- Try with elevated privileges

**See: [SETUP.md](SETUP.md#troubleshooting) for detailed troubleshooting guide**

---

## 🚀 Advanced Usage

### Command-Line Integration
```PowerShell
# Direct Chainsaw command (bypass frontend)
chainsaw hunt C:\evtx_files -s sigma/ --mapping sigma-event-logs-all.yml
```

### Scripting & Automation
```PowerShell
# Export and analyze automatically
.\ChainsawIntegration.ps1 -ExportEvtx
# Then: python chainsaw_frontend.py (in automated mode)
```

### Custom Rules
Add `.txt` files to `./chainsaw/rules/` for custom detections.

---

## 📖 Additional Resources

- **Chainsaw Docs**: https://github.com/WithSecureLabs/chainsaw
- **Sigma Rules**: https://github.com/SigmaHQ/sigma
- **Windows Event IDs**: https://www.ultimatewindowssecurity.com/
- **EVTX Format**: https://github.com/omerbenamram/evtx

---

## 🤝 Contributing

Contributions welcome! Areas for enhancement:
- Additional output format support (HTML, PDF)
- Real-time event monitoring
- Custom rule builder UI
- Performance optimization
- Multi-language support

---

## 📝 License

This project is licensed under the MIT License. See LICENSE file for details.

---

## 📞 Support & Issues

**For help:**
1. Check application logs: `./evtxripper.log`
2. Review [SETUP.md](SETUP.md) troubleshooting section
3. Run diagnostic: `.\ChainsawIntegration.ps1 -TestConnection`
4. Verify Chainsaw: `chainsaw --version`
5. Check configuration: `.\ChainsawIntegration.ps1 -ShowConfig`

---

## 🎓 Quick Reference

### Start Here
```PowerShell
# 1. Install
pip install -r requirements.txt

# 2. Configure
notepad .env  # Edit SMB settings

# 3. Test
.\ChainsawIntegration.ps1 -TestConnection

# 4. Run
python chainsaw_frontend.py
```

### File Purposes
| File | Purpose |
|------|---------|
| `.env` | All configuration (edit this!) |
| `chainsaw_frontend.py` | Main interactive UI |
| `ChainsawIntegration.ps1` | PowerShell helper/integration |
| `QUICKSTART.md` | 5-minute setup guide |
| `SETUP.md` | Complete reference manual |

### Common Tasks
```PowerShell
# Export EVTX from this machine
.\ChainsawIntegration.ps1 -ExportEvtx

# Launch frontend to analyze
python chainsaw_frontend.py

# Run hunt directly
chainsaw hunt ./evtx_files -s sigma/ --mapping mapping.yml
```

---

**Next Step**: 👉 **[Read QUICKSTART.md](QUICKSTART.md)** for step-by-step setup

Happy hunting! 🔍
