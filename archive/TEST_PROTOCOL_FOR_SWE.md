# IX Design MCP Server Test Protocol for Software Engineers

## Overview

This document provides a comprehensive testing protocol for software engineers (SWEs) who are being onboarded to work with the IX Design MCP Server. The protocol ensures that both direct PHREEQC integration and the full MCP server workflow (using papermill-Jupyter) are functioning correctly.

## Prerequisites

1. **Environment Setup**:
   ```bash
   # Create and activate virtual environment
   python -m venv venv312
   conda activate venv312  # or source venv312/bin/activate
   
   # Install dependencies
   pip install -r requirements.txt
   ```

2. **PHREEQC Installation**:
   - Windows: Install PHREEQC from USGS website
   - Linux/Mac: `sudo apt-get install phreeqc` or compile from source
   - Verify: `phreeqc --version` or check for phreeqc.bat

3. **MCP Server Dependencies**:
   ```bash
   pip install fastmcp papermill jupyter watertap idaes
   ```

## Test Protocol Structure

### Phase 1: Unit Tests - Core Components

#### 1.1 Test DirectPhreeqcEngine (Isolated)
**File**: `test_direct_phreeqc_simple.py`

**Purpose**: Verify PHREEQC executable integration works correctly without WaterTAP

**What to check**:
- ✓ PHREEQC executable is found and runs
- ✓ Input files are created correctly
- ✓ Output parsing works
- ✓ Hardness removal is calculated (Ca, Mg reduction)
- ✓ Mass balance is maintained

**Expected output**:
```
Testing SAC resin with DirectPhreeqc...
✓ Simulation successful
  Initial effluent (after BV 0):
    Ca: 0.0 mg/L (feed: 80.0 mg/L)
    Mg: 0.0 mg/L (feed: 24.0 mg/L)
✓ Ion exchange is working - hardness is being removed!
```

**Common issues**:
- PHREEQC not found: Check PATH or update `phreeqc_exe` location
- Permission errors: Run as administrator or check file permissions
- Output parsing fails: Check PHREEQC version compatibility

#### 1.2 Test MCAS Property Package
**File**: `debug_mcas_issue.py`

**Purpose**: Verify MCAS doesn't default to 10,000 mg/L concentrations

**What to check**:
- ✓ Initial concentrations show 10,000 mg/L warning
- ✓ After fixing mole fractions, concentrations are correct
- ✓ Water mole fraction is ~0.99 (not 0.5)

**Expected output**:
```
Concentrations after initialization:
  Ca_2+: 10000.0 mg/L
    ⚠ WARNING: Defaulted to 10,000 mg/L!
  
Concentrations AFTER fixing mole fractions:
  Ca_2+: 80.0 mg/L
Water mole fraction after fix: 0.998573
```

### Phase 2: Integration Tests - WaterTAP Models

#### 2.1 Test Simple IX Model
**File**: `test_simple_mcp.py`

**Purpose**: Test basic IonExchangeTransport0D model

**What to check**:
- ✓ Model builds without errors
- ✓ Initialization completes
- ✓ Removal rates are non-zero
- ✓ Mass balance is satisfied

**Known issues** (current state):
```
Outlet conditions:
  Ca: 212920.6 mg/L  # Should be < 80 mg/L
  Mg: 208516.1 mg/L  # Should be < 24 mg/L
✗ Ion exchange NOT working - no hardness removal!
```

#### 2.2 Test Mass Balance
**File**: `debug_mass_balance.py`

**Purpose**: Debug mass transfer term linking

**What to check**:
- ✓ Mass transfer terms should be non-zero
- ✓ Balance error should be near zero
- ✓ Outlet = Inlet + Transfer

**Current issue**:
```
Ca_2+:
  Transfer term: 0.000000e+00 kg/s  # Should be negative (removal)
  Balance error: 3.804007e+04 kg/s  # Should be ~0
```

### Phase 3: Full MCP Server Tests

#### 3.1 Test MCP Tool Functions
**File**: `test_mcp_tools.py` (create this)

```python
#!/usr/bin/env python
"""Test MCP server tools directly"""

import sys
sys.path.insert(0, 'C:\\Users\\hvksh\\mcp-servers\\ix-design-mcp')

from tools.schemas import IXConfigurationInput, MCASWaterComposition
from tools.ix_configuration import optimize_ix_configuration

def test_configuration_tool():
    """Test the configuration optimization tool"""
    water = MCASWaterComposition(
        flow_m3_hr=100.0,
        temperature_celsius=25.0,
        pressure_bar=4.0,
        pH=7.5,
        ion_concentrations_mg_L={
            'Ca_2+': 80.0,
            'Mg_2+': 24.0,
            'Na_+': 838.9,
            'Cl_-': 1435.0
        }
    )
    
    config_input = IXConfigurationInput(
        water_analysis=water,
        treatment_goals=['remove_hardness'],
        max_vessels_per_train=3
    )
    
    result = optimize_ix_configuration(config_input)
    assert len(result.configurations) > 0
    print(f"✓ Configuration tool: {len(result.configurations)} configs generated")
    return result

if __name__ == "__main__":
    test_configuration_tool()
```

#### 3.2 Test Papermill Execution
**File**: `test_mcp_simulation.py`

**Purpose**: Test full MCP simulation via papermill

**What to check**:
- ✓ Notebook executes without errors
- ✓ All flowsheet types complete
- ✓ Hardness removal > 80%
- ✓ Sodium increases (ion exchange)
- ✓ Breakthrough curves generated

**Expected output** (when working):
```
Testing sac_na_wac_degasser flowsheet
✓ Simulation completed in 43.9 seconds
  Hardness removal: 85.2%
    Feed: 299 mg/L as CaCO3
    Product: 44 mg/L as CaCO3
  Na+ change: +156 mg/L
✓ sac_na_wac_degasser: Ion exchange working correctly!
```

#### 3.3 Test MCP Server API
**File**: `test_mcp_server_api.py` (create this)

```python
#!/usr/bin/env python
"""Test MCP server API endpoints"""

import json
import asyncio
from server import create_server

async def test_server():
    """Test server endpoints"""
    server = create_server()
    
    # Test tool listing
    tools = await server.list_tools()
    assert any(t.name == "ix_simulation" for t in tools)
    print("✓ Server tools listed correctly")
    
    # Test simulation endpoint
    water_data = {
        "flow_m3_hr": 100.0,
        "temperature_celsius": 25.0,
        "pressure_bar": 4.0,
        "pH": 7.5,
        "ion_concentrations_mg_L": {
            "Ca_2+": 80.0,
            "Mg_2+": 24.0,
            "Na_+": 838.9,
            "Cl_-": 1435.0
        }
    }
    
    # Test configuration
    config_args = {
        "water_analysis": water_data,
        "treatment_goals": ["remove_hardness"]
    }
    
    config_result = await server.call_tool("ix_configuration", config_args)
    print(f"✓ Configuration generated: {len(config_result.configurations)} options")
    
    # Test simulation
    sim_args = {
        "configuration": config_result.configurations[0],
        "water_analysis": water_data,
        "breakthrough_criteria": {"hardness_mg_L_CaCO3": 5.0}
    }
    
    sim_result = await server.call_tool("ix_simulation", sim_args)
    print(f"✓ Simulation status: {sim_result.status}")

if __name__ == "__main__":
    asyncio.run(test_server())
```

### Phase 4: Validation Tests

#### 4.1 Physical Reasonableness Checks

Create `test_physical_validation.py`:

```python
def validate_ix_results(feed_water, treated_water, resin_type):
    """Validate IX results are physically reasonable"""
    
    # Mass balance
    total_feed = sum(feed_water.ion_concentrations_mg_L.values())
    total_treated = sum(treated_water.ion_concentrations_mg_L.values())
    assert abs(total_feed - total_treated) / total_feed < 0.1, "Mass balance error > 10%"
    
    # Hardness removal
    feed_hardness = feed_water.get_total_hardness_mg_L_CaCO3()
    treated_hardness = treated_water.get_total_hardness_mg_L_CaCO3()
    assert treated_hardness < feed_hardness * 0.2, "Insufficient hardness removal"
    
    # Counter-ion release
    if resin_type == "SAC":
        na_increase = (treated_water.ion_concentrations_mg_L['Na_+'] - 
                      feed_water.ion_concentrations_mg_L['Na_+'])
        assert na_increase > 50, "No sodium release detected"
    
    # pH changes
    if resin_type == "WAC_H":
        assert treated_water.pH < feed_water.pH - 1, "No pH reduction for H-WAC"
    
    print("✓ All physical validation checks passed")
```

#### 4.2 Regression Tests

Create test cases with known good results:

```python
# test_regression.py
KNOWN_GOOD_CASES = [
    {
        "name": "Standard municipal water",
        "feed": {"Ca_2+": 80, "Mg_2+": 24, "Na_+": 100},
        "expected_removal": {"Ca_2+": 0.95, "Mg_2+": 0.92},
        "expected_bv": 250
    },
    {
        "name": "High hardness water", 
        "feed": {"Ca_2+": 200, "Mg_2+": 80, "Na_+": 50},
        "expected_removal": {"Ca_2+": 0.90, "Mg_2+": 0.85},
        "expected_bv": 100
    }
]

def test_regression():
    for case in KNOWN_GOOD_CASES:
        result = run_ix_simulation(case["feed"])
        
        # Check removal within 10% of expected
        for ion, expected in case["expected_removal"].items():
            actual = result.removal_fractions[ion]
            assert abs(actual - expected) < 0.1, f"{ion} removal off by >10%"
        
        # Check breakthrough within 20% of expected
        assert abs(result.breakthrough_bv - case["expected_bv"]) / case["expected_bv"] < 0.2
```

### Phase 5: Performance Tests

#### 5.1 Execution Time Benchmarks

```python
import time

def benchmark_simulation():
    """Benchmark simulation performance"""
    
    start = time.time()
    result = simulate_ix_system(standard_config)
    execution_time = time.time() - start
    
    print(f"Execution time: {execution_time:.2f} seconds")
    assert execution_time < 60, "Simulation too slow (>60s)"
    
    # Check papermill execution
    start = time.time()
    run_papermill_notebook()
    notebook_time = time.time() - start
    
    print(f"Notebook execution: {notebook_time:.2f} seconds")
    assert notebook_time < 120, "Notebook too slow (>2 min)"
```

### Test Execution Order

1. **Initial Setup Validation**:
   ```bash
   python test_direct_phreeqc_simple.py  # Verify PHREEQC works
   python debug_mcas_issue.py            # Check MCAS configuration
   ```

2. **Component Tests**:
   ```bash
   python test_simple_mcp.py             # Basic IX model
   python debug_mass_balance.py          # Mass balance debugging
   python debug_constraints.py           # Constraint checking
   ```

3. **Integration Tests**:
   ```bash
   python test_mcp_tools.py              # Test individual tools
   python test_mcp_simulation.py         # Full simulation test
   ```

4. **Server Tests**:
   ```bash
   python server.py                      # Start server in one terminal
   python test_mcp_server_api.py        # Run API tests
   ```

5. **Validation & Performance**:
   ```bash
   python test_physical_validation.py    # Physical checks
   python test_regression.py             # Known cases
   python benchmark_simulation.py        # Performance
   ```

### Troubleshooting Guide

#### Common Issues and Solutions

1. **PHREEQC not found**:
   - Check installation: `where phreeqc` (Windows) or `which phreeqc` (Linux)
   - Update path in DirectPhreeqcEngine
   - Set environment variable: `PHREEQC_PATH`

2. **MCAS 10,000 mg/L issue**:
   - Always call `fix_mole_fractions()` after initialization
   - Check water mole fraction > 0.99
   - Verify all components have mass flows set

3. **Mass balance errors**:
   - Check `has_mass_transfer=True` in control volume
   - Verify `eq_mass_transfer` constraint is active
   - Debug with `debug_mass_balance.py`

4. **Papermill failures**:
   - Check all parameters are JSON-serializable
   - Verify notebook kernel matches environment
   - Check for hardcoded paths in notebook

5. **MCP server issues**:
   - Verify FastMCP version compatibility
   - Check all schemas are properly defined
   - Test tools individually before full workflow

### Success Criteria

A new SWE should be able to:

1. ✓ Run all Phase 1 unit tests successfully
2. ✓ Identify and document any failing integration tests
3. ✓ Execute a full MCP simulation via papermill
4. ✓ Validate results are physically reasonable
5. ✓ Benchmark performance is acceptable

### Reporting Issues

When reporting test failures, include:

1. Full error traceback
2. Environment details: `pip list > requirements_actual.txt`
3. PHREEQC version: `phreeqc --version`
4. Test script output with `-v` flag
5. Any modifications made to the code

### Next Steps After Testing

1. If all tests pass: Ready for development work
2. If unit tests pass but integration fails: Focus on debugging integration layer
3. If PHREEQC tests fail: Check installation and paths
4. If MCP tests fail: Review server configuration and schemas

This protocol ensures systematic validation of the entire IX Design MCP Server stack and helps quickly identify where issues occur in the workflow.