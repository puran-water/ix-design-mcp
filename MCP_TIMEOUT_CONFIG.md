# MCP Timeout Configuration for IX Design Server

## Problem
The IX Design MCP server runs long PHREEQC simulations that can take 5-10 minutes to complete. The default MCP client timeout of 280 seconds (4.6 minutes) causes these simulations to fail with timeout errors.

## Solution
Configure MCP timeout environment variables before starting Claude Code:

### For Windows (PowerShell):
```powershell
$env:MCP_TIMEOUT = 900        # 15 minutes for server startup
$env:MCP_TOOL_TIMEOUT = 900   # 15 minutes for tool calls
claude
```

### For Linux/Mac (Bash):
```bash
export MCP_TIMEOUT=900         # 15 minutes for server startup
export MCP_TOOL_TIMEOUT=900    # 15 minutes for tool calls
claude
```

### For Permanent Configuration:
Add these environment variables to your system:
- Windows: System Properties → Environment Variables
- Linux/Mac: Add to `~/.bashrc` or `~/.zshrc`

## Timeout Values Explained
- **MCP_TIMEOUT**: Controls the startup timeout for MCP servers (in seconds)
- **MCP_TOOL_TIMEOUT**: Controls the timeout for individual MCP tool calls (in seconds)

## Recommended Values for IX Design Server
- **Minimum**: 600 seconds (10 minutes)
- **Recommended**: 900 seconds (15 minutes)
- **Heavy simulations**: 1800 seconds (30 minutes)

## Server-Side Configuration
The server code has been updated to use 600-second timeouts internally:
- `server.py`: Lines 632 and 979 set `MCP_SIMULATION_TIMEOUT_S=600`
- `direct_phreeqc_engine.py`: Line 616 sets `default_timeout_s=600`

However, the MCP client timeout must also be increased to allow these long-running operations to complete.

## Verification
After setting the environment variables and restarting Claude Code:
1. Run a test simulation with the `simulate_ix_watertap` tool
2. Check that simulations complete without "280 second timeout" errors
3. Monitor actual simulation times in the results

## References
- [Claude Code CHANGELOG v1.0.8](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md) - Fixed MCP timeout environment variable handling
- DeepWiki documentation on MCP timeout configuration