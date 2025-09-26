# Ion Exchange Design MCP Server
### PHREEQC-Based Breakthrough Prediction with WaterTAP Economic Costing

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://github.com/anthropics/mcp)

## Technical Overview

### Ion Exchange Process Modeling

This MCP server implements rigorous ion exchange system design through a **three-tier modeling approach**, providing fast configuration, detailed validation, and benchmark accuracy for Strong Acid Cation (SAC) and Weak Acid Cation (WAC) resins.

Key technical capabilities:
- **Knowledge-based configuration** - USEPA Gaines-Thomas equilibrium solver for <1 sec SAC sizing
- **pH-dependent WAC modeling** - Henderson-Hasselbalch capacity for WAC-H alkalinity removal
- **PHREEQC transport modeling** - Cell-based breakthrough prediction with 8-cell discretization
- **WaterTAP economic costing** - EPA-WBS correlations via WaterTAP/IDAES for CAPEX/OPEX/LCOW
- **Multi-ion competition** - Accurate Ca²⁺/Mg²⁺/Na⁺ selectivity from literature (Helfferich)
- **Unified results schema** - Consistent JSON output across all simulation engines

### Three-Tier Architecture

**Tier 1: Fast Configuration (<1 sec)**
- USEPA Gaines-Thomas equilibrium solver for SAC hardness leakage
- Henderson-Hasselbalch pH floor model for WAC-H alkalinity removal
- Literature-based capacity derating and selectivity coefficients
- Ideal for parametric studies and optimization loops

**Tier 2: Detailed Validation (10-60 sec)**
- PHREEQC cell-based transport with mass transfer effects
- Full breakthrough curves and regeneration cycle modeling
- WaterTAP flowsheet construction with economic costing
- Recommended for final design validation

**Tier 3: Benchmark Accuracy (Future)**
- USEPA HSDMIX full transport model (pore + film diffusion)
- Cross-validation against PHREEQC for quality assurance
- Research-grade accuracy for complex waters

### Process Flow

1. **Configuration Layer** - Hydraulic sizing (16 BV/hr service, 25 m/hr linear velocity, L/D = 1.5-2.0)
2. **Performance Prediction** - Knowledge-based models or PHREEQC simulation
3. **Economic Analysis** - WaterTAP costing with EPA-WBS correlations
4. **Report Generation** - Professional HTML reports with breakthrough curves

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
  - Includes full regeneration cycle modeling with proper mass balance

#### Report Generation Tool
- `generate_ix_report` - Professional HTML report generation from simulation artifacts
  - Resin-specific report templates for SAC, WAC_Na, and WAC_H
  - Hydraulic design calculations with verification checks
  - Interactive breakthrough curve visualizations
  - Mass balance and regeneration sequence details
  - Economic analysis with cost breakdown

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
- **WAC Na-form**: Two-step regeneration (HCl elution + NaOH conversion)
- **WAC H-form**: Single-step acid regeneration with CO₂ generation
- **Bed expansion**: 50% (WAC Na-form), 100% (WAC H-form)

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

### WAC Configuration Example
```python
{
  "water_analysis": {
    "flow_m3_hr": 100,
    "ca_mg_l": 80,
    "mg_mg_l": 24,
    "na_mg_l": 840,
    "hco3_mg_l": 122,
    "cl_mg_l": 1435,
    "pH": 7.8
  },
  "target_hardness_mg_l_caco3": 5.0,
  "target_alkalinity_mg_l_caco3": 5.0,
  "resin_type": "WAC_Na"
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

## Recent Improvements (September 2025)

### SAC Leakage Model Overhaul
Replaced fundamentally flawed dose-based leakage model with **USEPA Gaines-Thomas equilibrium solver**:

**Before (Wrong)**:
```python
# Hardcoded leakage tiers based on regeneration dose only
if regen_dose >= 150: leakage = 0.5 mg/L
elif regen_dose >= 120: leakage = 1.0 mg/L
```
- Ignored feed water composition (Na/Ca/Mg ratios)
- Violated mass action equilibrium principles

**After (Correct)**:
```python
# Gaines-Thomas equilibrium from feed composition
K_GT = (y_Ca × X_Na²) / (y_Na² × X_Ca)
leakage = f(Ca, Mg, Na, K_Ca_Na, K_Mg_Na, f_active)
```
- Mass action law from Helfferich (1962)
- Accounts for multi-ion competition
- Parameterized with `f_active` (0.08-0.15) for mass transfer zone
- Extracted from USEPA Water Treatment Models (public domain)

**Key Benefits**:
- ✅ Physics-based predictions from feed water chemistry
- ✅ Regeneration dose now correctly controls capacity, not leakage
- ✅ Validated to ±0.001% on Gaines-Thomas relationship
- ✅ <1 ms computation time for parametric studies

### WAC-H pH Floor Model
Implemented Henderson-Hasselbalch capacity model where **target alkalinity drives pH floor**:
```python
pH_floor = f(target_alkalinity)  # e.g., 10 mg/L → pH 4.4
alpha = 1 / (1 + 10^(pKa - pH_floor))  # Fraction of active sites
operating_capacity = total_capacity × alpha
```

### Code Quality Improvements
- Removed 49 development artifacts (test scripts, debug files, dead code)
- 32% reduction in tools/ directory size
- All MCP tools tested and verified functional
- Comprehensive test suite with 9 equilibrium physics tests

## Technical Implementation Details

### Knowledge-Based Configuration (Tier 1)
**SAC Model** (`tools/equilibrium_leakage.py`):
- USEPA Gaines-Thomas equilibrium solver
- Iterative composition solver with mass balance normalization
- `f_active` parameterization for mass transfer effects
- Calibration function for PHREEQC tuning

**WAC-H Model** (`tools/breakthrough_calculator.py`):
- pH-dependent capacity via Henderson-Hasselbalch
- CO₂ generation stoichiometry
- Alkalinity removal limits

**Capacity Derating** (`tools/capacity_derating.py`):
- Regeneration efficiency from literature (Helfferich Ch. 9)
- Selectivity coefficient corrections
- Incomplete utilization factors

**Selectivity Data** (`tools/selectivity_coefficients.py`):
- K_Ca_Na = 5.16, K_Mg_Na = 3.29 (8% DVB SAC)
- Literature-sourced values for accuracy

### PHREEQC Integration (Tier 2)
- Uses phreeqpython wrapper for direct PHREEQC execution
- 8-cell discretization for transport modeling
- SURFACE complexation for WAC weak acid groups
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
- WAC performance data for temporary hardness removal
- Two-step regeneration sequences for WAC Na-form

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