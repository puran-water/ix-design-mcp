# IX Design MCP Server - Project Status & Onboarding

## Overview
The IX Design MCP Server is a Model Context Protocol (MCP) server for designing and simulating ion exchange (IX) water treatment systems. It integrates WaterTAP's process models with PHREEQC's geochemical engine for accurate multi-component ion exchange modeling.

## Current Status (as of 2025-07-25)

### What's Working
1. **Stateless Model Construction** (`ix_cli.py`)
   - Successfully builds Pyomo models without hidden state
   - Implements proper mole fraction fixing to avoid MCAS defaults
   - Deactivates pressure constraints to avoid infeasibility
   - Achieves DOF=0 and solver convergence

2. **Process Isolation**
   - CLI-based architecture prevents module conflicts
   - Notebook execution via papermill for MCP integration
   - Clean subprocess execution for testing

3. **Testing Infrastructure**
   - Comprehensive test workflow (`test_mcp_workflow.py`)
   - PowerShell integration for Windows environments
   - SOPs documented in CLAUDE.md

### Critical Issues

#### 1. Negative Ion Removal Rates
**Symptom**: Ca removal shows -5455.6% instead of expected ~60%
**Root Cause**: PHREEQC is not finding breakthrough data
```
WARNING - No breakthrough data for Ca_2+ in PHREEQC results
INFO - Set default breakthrough volume for Ca_2+ to 200 BV and fixed
```
**Impact**: Model uses default 0.95 removal fraction but mass balance calculations produce negative removal rates

#### 2. Mass Balance Error
**Symptom**: 7191.7% mass balance error (should be <1%)
**Root Cause**: Outlet concentrations are much higher than inlet
**Related**: Water mole fraction drops to 0.5 after IX calculations

#### 3. MCP Tool Integration
**Status**: Direct tool test fails while direct model test passes
**Issue**: Notebook execution path doesn't benefit from ix_cli.py fixes
**Solution Attempted**: Created CLI wrapper notebook but still experiencing issues

## Technical Details

### Key Files
- `ix_cli.py`: Core CLI with all fixes (pressure constraints, mole fractions)
- `tools/ix_simulation.py`: MCP tool that executes notebooks via papermill
- `notebooks/ix_simulation_cli_wrapper.ipynb`: Wrapper to use CLI from notebook
- `test_mcp_workflow.py`: Comprehensive test suite
- `CLAUDE.md`: Project-specific instructions and SOPs

### Important Fixes Applied
1. **Pressure Constraint Deactivation** (prevents infeasibility)
   ```python
   # Deactivate to avoid IDAES control volume conflicts
   ix_unit.eq_pressure_drop.deactivate()
   ix_unit.eq_deltaP.deactivate()
   ix_unit.control_volume.pressure_balance.deactivate()
   ```

2. **Mole Fraction Fixing** (prevents 10,000 mg/L defaults)
   ```python
   from watertap_ix_transport.utilities.property_calculations import fix_mole_fractions
   fix_mole_fractions(feed.properties[0])
   ```

3. **Mass Flow Calculation** (corrected unit conversion)
   ```python
   # Fixed: was 1e-9, now 1e-3
   mass_flow_kg_s = conc_mg_L * flow_rate_m3s * 1e-3
   ```

## Current ToDo List

### High Priority - Pending
- [ ] Replace hard-coded 0.95 removal with actual formula (P1) - #403
- [ ] Fix ion_removal_rate bounds to [-1, 1] if dimensionless (P1) - #404
- [ ] Add mass balance and species name regression tests (P2) - #405
- [ ] Fix solver convergence issues - #311
- [ ] Create MCP server integration tests - #305
- [ ] Create end-to-end workflow tests - #306
- [ ] Create regression test suite with core assertions - #307
- [ ] Document error resolutions from DeepWiki queries - #308

### Medium Priority - Pending
- [ ] Refactor ix_flowsheet_builder for stateless construction - #204
- [ ] Add structured JSON logging for diagnostics - #206
- [ ] Implement iterative charge balance for pH accuracy - #207
- [ ] Expose solver options via config schema - #208
- [ ] Create Pydantic config schema - #209

### Low Priority - Pending
- [ ] Package restructuring to namespace structure - #210

### Completed Tasks (30 items)
See full list in todo tracking system - includes fixes for DOF issues, mole fractions, pressure constraints, test infrastructure, and documentation.

## Next Steps

### Immediate Priority
1. **Debug PHREEQC Integration**: Why is PHREEQC not returning breakthrough data?
   - Check PHREEQC input file generation
   - Verify SELECTED_OUTPUT configuration
   - Test PHREEQC execution independently

2. **Fix Mass Balance**: Investigate why ion_removal_rate calculations produce negative values
   - Check sign conventions in mass transfer equations
   - Verify removal fraction application
   - Debug outlet flow calculations

3. **Stabilize MCP Integration**: Ensure notebook execution uses fixed model
   - Consider direct model execution instead of notebook
   - Or ensure notebook properly imports and uses ix_cli.py

## Environment Setup

### Windows PowerShell with venv312
```powershell
powershell.exe -Command "cd C:\Users\hvksh\mcp-servers\ix-design-mcp; C:\Users\hvksh\mcp-servers\venv312\Scripts\python.exe script.py"
```

### Key Dependencies
- WaterTAP (IDAES framework)
- PHREEQC 3.x (geochemical engine)
- phreeqpython (Python wrapper)
- papermill (notebook execution)
- MCP SDK

## Known Issues & Workarounds

1. **Unicode on Windows**: Add UTF-8 encoding setup to scripts
2. **Module Conflicts**: Use subprocess isolation for PHREEQC calls
3. **Pressure Constraints**: Must be deactivated to avoid infeasibility
4. **MCAS Defaults**: Must fix mole fractions immediately after setting flows

## Contact & Resources
- DeepWiki SOPs documented in CLAUDE.md
- Use repositories:
  - IDAES/idaes-pse (framework issues)
  - watertap-org/watertap (unit models)
  - usgs-coupled/phreeqc3 (chemistry)
  - Vitens/phreeqpython (wrapper)