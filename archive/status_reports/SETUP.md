# IX Design MCP Server - Setup Guide

## Prerequisites

### System Requirements
- Python 3.8 or higher
- 4GB RAM minimum
- Windows, macOS, or Linux

### Required Software
- Git
- Python with pip
- Text editor or IDE (VS Code recommended)

## Installation Steps

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/ix-design-mcp.git
cd ix-design-mcp
```

### 2. Create Virtual Environment

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**macOS/Linux:**
```bash
python -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

If you encounter issues, install core dependencies individually:
```bash
pip install fastmcp
pip install phreeqpython
pip install papermill
pip install pydantic
```

### 4. Configure PHREEQC Database

The server uses PHREEQC for geochemical calculations. The database is typically included with phreeqpython, but if you need to specify a custom path:

**Windows:**
```bash
set PHREEQC_DATABASE_PATH=C:\path\to\phreeqc\database
```

**macOS/Linux:**
```bash
export PHREEQC_DATABASE_PATH=/path/to/phreeqc/database
```

## Verification

### 1. Test Basic Functionality

```bash
python -c "from watertap_ix_transport.production_models import ProductionPhreeqcEngine; print('PHREEQC Engine OK')"
```

### 2. Run Unit Tests

```bash
python tests/test_phase4_mcp_configuration.py
python tests/test_phase4_mcp_simulation.py
```

### 3. Run Integration Tests

```bash
python tests/test_mcp_server_integration.py
```

Expected output:
```
✅ ALL MCP SERVER INTEGRATION TESTS PASSED! ✅
```

### 4. Start the Server

```bash
python server.py
```

You should see:
```
Starting Ion Exchange Design MCP Server...
Available tools:
  - optimize_ix_configuration
  - simulate_ix_system
```

## Troubleshooting

### Common Issues

#### 1. ModuleNotFoundError
If you see import errors, ensure your virtual environment is activated:
```bash
# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

#### 2. PHREEQC Database Error
If PHREEQC can't find its database:
```python
# Add to your environment or script
import os
os.environ['PHREEQC_DATABASE_PATH'] = r'C:\path\to\phreeqc.dat'
```

#### 3. Memory Issues
For large simulations, increase Python's memory limit:
```bash
# Windows
set PYTHONMAXMEMORYMB=4096

# macOS/Linux
export PYTHONMAXMEMORYMB=4096
```

#### 4. Permission Errors
On Unix systems, you may need to make the server executable:
```bash
chmod +x server.py
```

## Configuration Files

### Optional: Create settings.json

```json
{
  "max_vessel_diameter_m": 3.0,
  "min_runtime_hours": 8,
  "default_temperature_c": 25,
  "phreeqc_database": "phreeqc.dat"
}
```

### Optional: Configure Logging

Create `logging.conf`:
```ini
[loggers]
keys=root

[handlers]
keys=fileHandler,consoleHandler

[formatters]
keys=simpleFormatter

[logger_root]
level=INFO
handlers=fileHandler,consoleHandler

[handler_fileHandler]
class=FileHandler
formatter=simpleFormatter
args=('ix_design_mcp.log',)

[handler_consoleHandler]
class=StreamHandler
formatter=simpleFormatter
args=(sys.stderr,)

[formatter_simpleFormatter]
format=%(asctime)s - %(name)s - %(levelname)s - %(message)s
```

## Integration with MCP Clients

### Using with Claude Desktop

1. Add to Claude's configuration:
```json
{
  "mcpServers": {
    "ix-design": {
      "command": "python",
      "args": ["path/to/ix-design-mcp/server.py"]
    }
  }
}
```

2. Restart Claude Desktop

### Using with Other MCP Clients

The server uses STDIO protocol and can be integrated with any MCP-compatible client:
```bash
# Direct STDIO connection
python server.py

# With explicit Python path
/usr/bin/python3 /path/to/server.py
```

## Validation Checklist

- [ ] Virtual environment created and activated
- [ ] All dependencies installed successfully
- [ ] PHREEQC database accessible
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Server starts without errors
- [ ] Tools are registered and visible
- [ ] Can process example water analysis

## Next Steps

1. Review the README.md for usage examples
2. Check the `/examples` folder for sample requests
3. Read the AI_SYSTEM_PROMPT.md for agent integration
4. Start designing IX systems!

## Support

If you encounter issues not covered here:

1. Check the GitHub Issues page
2. Review the test files for working examples
3. Enable debug logging:
   ```bash
   export IX_DEBUG=true
   python server.py
   ```
4. Create a detailed issue report with:
   - Python version (`python --version`)
   - OS and version
   - Full error traceback
   - Steps to reproduce