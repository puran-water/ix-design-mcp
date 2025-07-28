# Archived Implementations

This directory contains implementations that were evaluated but not selected for production use during the consolidation effort on 2025-07-23.

## Selection Process

All implementations were tested comprehensively with the following criteria:
- Import success
- Build success
- Feature completeness
- Performance metrics
- Code maturity

## Archived Components

### Degasser Implementations

**Selected for Production**: `degasser_tower_0D_phreeqc_final.py`

**Archived**:
1. `degasser_tower_0D.py` - Original 0D tower model with detailed chemistry
   - Issue: Missing required species in property package
   - Status: Build failed

2. `degasser_tower_0D_simple.py` - Simplified 0D tower model
   - Issue: Port connection incompatibility
   - Status: Build failed

3. `degasser_tower_0D_phreeqc.py` - Original PHREEQC implementation
   - Issue: Most feature-complete but port access issues
   - Status: Initialization failed
   - Note: Had costing methods that could be extracted if needed

4. `degasser_tower_0D_phreeqc_simple.py` - Simplified PHREEQC version
   - Issue: Port connection incompatibility
   - Status: Build failed

5. `degasser_phreeqc_direct.py` - Direct PHREEQC implementation
   - Not tested in final round

### PHREEQC Engine Implementations

**Selected for Production**: `phreeqc_transport_engine.py`

**Archived**:
1. `phreeqpy_engine.py` - PhreeqPython wrapper
   - Issue: API mismatch, could not create solutions
   - Status: 0% test success rate

## Usage

These implementations are preserved for reference and potential future use:
- Some contain useful code patterns or algorithms
- The original PHREEQC degasser has costing methods
- May be useful for understanding evolution of the codebase

To use any archived implementation, copy it back to the main codebase and resolve the documented issues.

## Test Results

Detailed test results are available in:
- `/tests/degasser_comparison_results.json`
- `/tests/phreeqc_engine_comparison_results.json`
- `/tests/mature_degasser_test_results.json`