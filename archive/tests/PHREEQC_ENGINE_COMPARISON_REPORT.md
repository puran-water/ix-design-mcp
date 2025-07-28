# PHREEQC Engine Implementation Comparison Report

Generated: 2025-07-23 12:16:45

## Summary

          Implementation           Status  Import Success  Init Success Test Success %
phreeqc_transport_engine          success            True          True            100
         phreeqpy_engine all_tests_failed            True          True            N/A


## Detailed Results


### phreeqc_transport_engine
**Description:** PHREEQC transport engine in watertap_ix_transport
**Status:** success

**Features:**
- Initialization method: Direct class: PhreeqPython
- PHREEQC classes: PhreeqPython, PhreeqcTransportEngine, add_trace_metal_selectivity_to_phreeqc

**Test Results:**

_Typical groundwater:_
- Status: success
- Species calculated: 30
  - CO2: 3.00e-05 mol/L
  - CO3-2: 3.78e-06 mol/L
  - Ca+2: 1.86e-03 mol/L
- Phases calculated: 13
- pH: 7.800
- pe: 4.000
- I: 0.011

_High hardness water:_
- Status: success
- Species calculated: 30
  - CO2: 1.09e-04 mol/L
  - CO3-2: 4.09e-06 mol/L
  - Ca+2: 4.58e-03 mol/L
- Phases calculated: 13
- pH: 7.500
- pe: 4.000
- I: 0.025

_Low pH water:_
- Status: success
- Species calculated: 30
  - CO2: 3.29e-04 mol/L
  - CO3-2: 9.61e-09 mol/L
  - Ca+2: 1.20e-03 mol/L
- Phases calculated: 13
- pH: 6.000
- pe: 4.000
- I: 0.007

### phreeqpy_engine
**Description:** PhreeqPython-based engine in watertap_ix_transport
**Status:** all_tests_failed

**Features:**
- Initialization method: Direct class: PhreeqPyEngine
- PHREEQC classes: PHREEQPY_AVAILABLE, PhreeqPyEngine, create_phreeqpy_engine, phreeqpython, run_phreeqc_simulation

**Test Results:**

_Typical groundwater:_
- Status: failed
- Errors:
  - Test failed: Could not create solution with any method

_High hardness water:_
- Status: failed
- Errors:
  - Test failed: Could not create solution with any method

_Low pH water:_
- Status: failed
- Errors:
  - Test failed: Could not create solution with any method


## Performance Comparison

          Implementation Test Success Rate Avg Species Count Avg Phase Count Property Coverage
phreeqc_transport_engine              100%                30              13               4/4


## Recommendations for Production Selection

### Working Implementations:

**phreeqc_transport_engine**
- Status: success
- Test success rate: 100%
- Average species calculated: 30
- Note: Custom implementation

### Usage Recommendations:
1. For production use, select the implementation that:
   - Has the highest test success rate
   - Provides the most complete speciation data
   - Has IX-specific functionality if needed
   - Has acceptable dependencies (phreeqpython vs custom)
2. Consider performance requirements:
   - PhreeqPython may be more accurate but requires external dependency
   - Custom implementations may be faster but less feature-complete