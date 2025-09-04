# Ion Exchange Design MCP Server
### PHREEQC-Based Breakthrough Prediction with WaterTAP Economic Costing

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://github.com/anthropics/mcp)

## Technical Overview

### Ion Exchange Process Modeling

This MCP server implements rigorous ion exchange system design through direct PHREEQC geochemical modeling, providing accurate breakthrough prediction for Strong Acid Cation (SAC) and Weak Acid Cation (WAC) resins. The server integrates multi-ion competition effects, pH-dependent selectivity, and counter-current regeneration optimization to deliver industrial-grade vessel sizing and operational parameters.

Key technical capabilities:
- **Multi-ion PHREEQC modeling** - Direct integration with PHREEQC v3 for accurate ion competition and selectivity
- **Breakthrough prediction** - Cell-based transport modeling with 8-cell discretization for sharp breakthrough curves
- **WaterTAP economic costing** - EPA-WBS correlations via WaterTAP/IDAES for capital and operating costs
- **Counter-current regeneration** - Optimized regenerant dosing with staged concentration profiles
- **Unified results schema** - Consistent JSON output across all simulation engines

### Architecture

The server employs a hybrid architecture combining PHREEQC's geochemical accuracy with WaterTAP's process economics:

1. **Configuration Layer** - Hydraulic sizing based on industry standards (16 BV/hr service, 25 m/hr linear velocity)
2. **Simulation Layer** - PHREEQC cell-based transport for service and regeneration cycles
3. **Economic Layer** - WaterTAP flowsheet construction with EPA-WBS costing correlations
4. **Process Isolation** - Subprocess execution prevents WaterTAP import conflicts

## Features

### MCP Tools Available

#### Configuration Tools
- `configure_sac_ix` - Size SAC vessels for hardness removal with N+1 redundancy
- `configure_wac_ix` - Size WAC vessels (Na-form or H-form) for alkalinity control

#### Simulation Tool
- `simulate_ix_watertap` - Unified simulation with PHREEQC chemistry and WaterTAP costing
  - Handles SAC, WAC Na-form, and WAC H-form resins
  - Provides complete economic analysis (CAPEX, OPEX, LCOW)
  - Generates detailed breakthrough curves and performance metrics

### Technical Specifications

#### Water Analysis Parameters
- Flow rate: 1-1000 m³/hr
- Hardness: Ca²⁺, Mg²⁺ (0-500 mg/L each)
- Monovalent ions: Na⁺, K⁺, NH₄⁺
- Anions: Cl⁻, SO₄²⁻, HCO₃⁻, NO₃⁻
- pH range: 4.0-10.0
- Temperature: 5-40°C

#### Resin Performance
- **SAC capacity**: 2.0-2.2 eq/L (Na-form)
- **WAC capacity**: 3.5-4.5 eq/L (pH-dependent)
- **Service flow**: 8-40 BV/hr (design: 16 BV/hr)
- **Regeneration efficiency**: 90-95% with counter-current flow

#### Economic Metrics
- Capital cost accuracy: ±20% (EPA-WBS correlations)
- Operating costs include: regenerant, resin replacement, energy, waste disposal
- LCOW calculation: 20-year lifetime, 8% discount rate

## Requirements

- Python 3.8+ (3.12 recommended for WaterTAP compatibility)
- PHREEQC v3.8+ executable on PATH or via PHREEQC_EXE environment variable
- Virtual environment for dependency isolation

## Installation

### Method 1: Standard Installation
```bash
# Clone repository
git clone https://github.com/puran-water/ix-design-mcp.git
cd ix-design-mcp

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set PHREEQC path (if not on PATH)
export PHREEQC_EXE=/path/to/phreeqc  # Windows: set PHREEQC_EXE=C:\path\to\phreeqc.exe
```

### Method 2: MCP Client Configuration

#### Claude Desktop
Add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "ix-design-mcp": {
      "command": "python",
      "args": ["/path/to/ix-design-mcp/server.py"],
      "env": {
        "PHREEQC_EXE": "/path/to/phreeqc"
      }
    }
  }
}
```

## Usage

### SAC Configuration Example
```python
{
  "water_analysis": {
    "flow_m3_hr": 100,
    "ca_mg_l": 120,
    "mg_mg_l": 40,
    "na_mg_l": 838.9,
    "hco3_mg_l": 122,
    "cl_mg_l": 1435,
    "pH": 7.8
  },
  "target_hardness_mg_l_caco3": 5.0
}
```

### Simulation Example (Unified Schema)
```python
{
  "schema_version": "1.0.0",
  "resin_type": "SAC",
  "water": {
    "flow_m3h": 100,
    "ions_mg_l": {
      "Ca_2+": 120,
      "Mg_2+": 40,
      "Na_1+": 838.9,
      "HCO3_1-": 122,
      "Cl_1-": 1435
    }
  },
  "vessel": {
    "diameter_m": 2.3,
    "bed_depth_m": 1.5
  },
  "targets": {
    "hardness_mg_l_caco3": 5.0
  },
  "cycle": {
    "regenerant_type": "NaCl",
    "regenerant_dose_g_per_l": 125
  },
  "engine": "watertap_hybrid"
}
```

## Output Schema

### Unified Results Structure
```json
{
  "schema_version": "1.0.0",
  "status": "success",
  "performance": {
    "service_bv_to_target": 205.1,
    "service_hours": 12.8,
    "capacity_utilization_percent": 95.2
  },
  "economics": {
    "capital_cost_usd": 297436,
    "operating_cost_usd_year": 41191,
    "lcow_usd_m3": 0.090
  },
  "breakthrough_data": {
    "bed_volumes": [...],
    "hardness_mg_l": [...]
  }
}
```

## Technical Implementation Details

### PHREEQC Integration
- Uses phreeqpython wrapper for direct PHREEQC execution
- 8-cell discretization for transport modeling
- Automatic charge balancing for ionic solutions
- Temperature-corrected equilibrium constants

### WaterTAP Integration
- Subprocess isolation prevents import conflicts
- EPA-WBS cost correlations for vessels, pumps, and auxiliaries
- Automatic flowsheet construction from vessel parameters
- IDAES solver configuration for robust convergence

### Process Isolation
The server uses subprocess.Popen with timeout protection for WaterTAP operations, preventing:
- Import graph conflicts with MCP server
- Solver hangs from difficult convergence
- Memory leaks from repeated flowsheet construction

## Performance Characteristics

- Configuration response: <100ms
- PHREEQC simulation: 2-5 seconds (typical)
- WaterTAP costing: 5-10 seconds (with subprocess overhead)
- Maximum timeout: 60 seconds (configurable)

## Validation

The models have been validated against:
- Industrial operational data for SAC softening
- Literature values for multi-ion selectivity
- EPA cost estimates for water treatment systems
- PHREEQC benchmark cases for ion exchange

## License

MIT License - See LICENSE file for details

## Citation

If using this software for academic work, please cite:
```
Ion Exchange Design MCP Server (2024). 
PHREEQC-Based Breakthrough Prediction with WaterTAP Economic Costing.
GitHub: https://github.com/puran-water/ix-design-mcp
```

## Support

For technical issues or questions, please open an issue on GitHub.